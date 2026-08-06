from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from threading import Event, get_ident
from typing import cast
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from pytestqt.qtbot import QtBot
from tests.pdf_fixtures import TEST_RENDER_BUDGET, create_feature_pdf, create_golden_pdf

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.pdf import (
    InspecaoPdf,
    LeitorPdfPort,
    OrcamentoRenderizacaoPdf,
    PaginaPdfRenderizada,
    PdfRectangle,
    PlanoRenderizacaoPdf,
    SessaoLeituraPdfPort,
)
from zeny_project_handler.ui.pdf_rendering import CacheLruBytes, regioes_tiles_priorizadas
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget

SMALL_TILE_BUDGET = OrcamentoRenderizacaoPdf(
    limite_pixels=40_000,
    limite_bytes=280_000,
)


@dataclass(frozen=True, slots=True)
class _RenderCall:
    pagina: int
    dpi: int
    rotacao: int
    regiao: PdfRectangle | None
    thread_id: int


class _ControlledSession:
    def __init__(
        self,
        inner: SessaoLeituraPdfPort,
        *,
        block_first: bool,
        entered: Event,
        release: Event,
    ) -> None:
        self._inner = inner
        self._block_first = block_first
        self._entered = entered
        self._release = release
        self.calls: list[_RenderCall] = []
        self.closed = False

    @property
    def inspecao(self) -> InspecaoPdf:
        return self._inner.inspecao

    def planejar_renderizacao(
        self,
        pagina_numero: int,
        *,
        dpi: int,
        orcamento: OrcamentoRenderizacaoPdf,
        rotacao_adicional_graus: int = 0,
        recorte_normalizado: PdfRectangle | None = None,
    ) -> PlanoRenderizacaoPdf:
        return self._inner.planejar_renderizacao(
            pagina_numero,
            dpi=dpi,
            orcamento=orcamento,
            rotacao_adicional_graus=rotacao_adicional_graus,
            recorte_normalizado=recorte_normalizado,
        )

    def renderizar_pagina(
        self,
        pagina_numero: int,
        *,
        dpi: int,
        orcamento: OrcamentoRenderizacaoPdf,
        rotacao_adicional_graus: int = 0,
        recorte_normalizado: PdfRectangle | None = None,
    ) -> PaginaPdfRenderizada:
        self.calls.append(
            _RenderCall(
                pagina=pagina_numero,
                dpi=dpi,
                rotacao=rotacao_adicional_graus,
                regiao=recorte_normalizado,
                thread_id=get_ident(),
            )
        )
        if self._block_first and len(self.calls) == 1:
            self._entered.set()
            if not self._release.wait(timeout=5):
                raise RuntimeError("O teste não liberou a rasterização controlada")
        return self._inner.renderizar_pagina(
            pagina_numero,
            dpi=dpi,
            orcamento=orcamento,
            rotacao_adicional_graus=rotacao_adicional_graus,
            recorte_normalizado=recorte_normalizado,
        )

    def fechar(self) -> None:
        self.closed = True
        self._inner.fechar()


class _ControlledReader:
    def __init__(self, *, block_first: bool = False) -> None:
        self._delegate = PyMuPdfReader()
        self._block_first = block_first
        self.entered = Event()
        self.release = Event()
        self.sessions: list[_ControlledSession] = []

    def abrir_sessao(
        self,
        caminho: Path,
        *,
        senha: str | None = None,
        documento_id: UUID | None = None,
        sha256_esperado: str | None = None,
    ) -> SessaoLeituraPdfPort:
        session = _ControlledSession(
            self._delegate.abrir_sessao(
                caminho,
                senha=senha,
                documento_id=documento_id,
                sha256_esperado=sha256_esperado,
            ),
            block_first=self._block_first and not self.sessions,
            entered=self.entered,
            release=self.release,
        )
        self.sessions.append(session)
        return session


def _viewer(
    qtbot: QtBot,
    reader: LeitorPdfPort,
    *,
    dpi: int = 600,
    budget: OrcamentoRenderizacaoPdf = SMALL_TILE_BUDGET,
    cache_limit: int = 128 * 1024 * 1024,
) -> PdfViewerWidget:
    viewer = PdfViewerWidget(
        leitor=reader,
        dpi=dpi,
        orcamento=budget,
        cache_limite_bytes=cache_limit,
    )
    qtbot.addWidget(viewer)
    viewer.resize(800, 600)
    viewer.show()
    return viewer


def _wait_preview(
    qtbot: QtBot,
    viewer: PdfViewerWidget,
    *,
    page: int = 1,
    rotation: int = 0,
) -> None:
    qtbot.waitUntil(
        lambda: viewer._current_preview is not None
        and viewer._current_preview.plano.pagina_numero == page
        and viewer._current_preview.plano.rotacao_adicional_graus == rotation,
        timeout=5_000,
    )


@pytest.mark.integration
def test_rendering_is_responsive_and_never_rasterizes_on_ui_thread(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_feature_pdf(tmp_path / "responsivo.pdf")
    reader = _ControlledReader(block_first=True)
    viewer = _viewer(qtbot, cast(LeitorPdfPort, reader), dpi=72, budget=TEST_RENDER_BUDGET)
    ui_thread = get_ident()
    event_loop_ran: list[bool] = []

    assert viewer.carregar_pdf(source)
    assert reader.entered.wait(timeout=1)
    QTimer.singleShot(0, lambda: event_loop_ran.append(True))

    qtbot.waitUntil(lambda: bool(event_loop_ran))
    assert viewer.view.scene().items() == []
    reader.release.set()
    _wait_preview(qtbot, viewer)

    assert reader.sessions[0].calls[0].thread_id != ui_thread


@pytest.mark.integration
def test_old_page_result_is_discarded_after_out_of_order_navigation(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_feature_pdf(tmp_path / "fora-de-sequencia.pdf")
    reader = _ControlledReader(block_first=True)
    viewer = _viewer(qtbot, cast(LeitorPdfPort, reader), dpi=72, budget=TEST_RENDER_BUDGET)

    assert viewer.carregar_pdf(source)
    assert reader.entered.wait(timeout=1)
    viewer.ir_para_folha(2)
    reader.release.set()
    _wait_preview(qtbot, viewer, page=2)

    assert [call.pagina for call in reader.sessions[0].calls[:2]] == [1, 2]
    assert viewer._current_preview is not None
    assert viewer._current_preview.plano.pagina_numero == 2
    assert viewer._current_transformer is not None
    assert viewer._current_transformer.pagina.numero == 2


@pytest.mark.integration
def test_document_exchange_and_source_change_clear_the_tile_cache(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    first = create_feature_pdf(tmp_path / "primeiro.pdf")
    second = create_golden_pdf(tmp_path / "segundo.pdf")
    viewer = _viewer(qtbot, PyMuPdfReader())

    assert viewer.carregar_pdf(first)
    _wait_preview(qtbot, viewer)
    assert viewer._render_cache.bytes_usados > 0

    assert viewer.carregar_pdf(second)
    assert viewer._render_cache.bytes_usados == 0
    _wait_preview(qtbot, viewer)
    second.write_bytes(second.read_bytes() + b"\n")
    viewer.view.definir_zoom(4.0)

    qtbot.waitUntil(lambda: viewer.inspecao is None, timeout=5_000)
    assert viewer._render_cache.bytes_usados == 0
    assert viewer.view.scene().items() == []


def test_byte_lru_evicts_least_recently_used_entry_at_exact_limit() -> None:
    cache: CacheLruBytes[str, str] = CacheLruBytes(10)
    assert cache.armazenar("a", "A", tamanho_bytes=4)
    assert cache.armazenar("b", "B", tamanho_bytes=4)
    assert cache.obter("a") == "A"

    assert cache.armazenar("c", "C", tamanho_bytes=6)

    assert cache.bytes_usados == 10
    assert cache.obter("b") is None
    assert cache.obter("a") == "A"
    assert cache.obter("c") == "C"
    assert not cache.armazenar("oversized", "X", tamanho_bytes=11)
    assert cache.bytes_usados == 10


@pytest.mark.integration
def test_viewer_cache_never_exceeds_configured_byte_limit(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_feature_pdf(tmp_path / "cache-limitado.pdf")
    cache_limit = 180_000
    viewer = _viewer(qtbot, PyMuPdfReader(), cache_limit=cache_limit)

    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    viewer.view.definir_zoom(4.0)
    qtbot.waitUntil(
        lambda: viewer._render_queue.esta_ociosa() and len(viewer._render_cache) >= 1,
        timeout=10_000,
    )

    assert 0 < viewer._render_cache.bytes_usados <= cache_limit


def test_tile_priority_and_rotation_map_viewport_back_to_canonical_region() -> None:
    budget = OrcamentoRenderizacaoPdf(
        limite_pixels=10_404,
        limite_bytes=10_404 * 7,
    )

    planned = regioes_tiles_priorizadas(
        largura_pagina_pixels=100,
        altura_pagina_pixels=100,
        dpi_previa=100,
        dpi_detalhe=200,
        viewport_normalizado=(0.0, 0.0, 0.4, 0.4),
        rotacao=90,
        orcamento=budget,
    )

    assert planned[0] == (5_000, (0.0, 0.5, 0.5, 1.0))
    assert all(priority >= planned[0][0] for priority, _region in planned)
    assert len(planned) < 16


@pytest.mark.integration
def test_rotated_overlays_remain_aligned_and_review_link_is_clickable(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_feature_pdf(tmp_path / "rotacao-overlay.pdf")
    viewer = _viewer(qtbot, PyMuPdfReader(), dpi=72, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    page_id = viewer.inspecao.documento.paginas[0].id
    geometry = GeometriaDocumento.polilinha(
        page_id,
        (
            PontoNormalizado(Decimal("0.2"), Decimal("0.3")),
            PontoNormalizado(Decimal("0.7"), Decimal("0.6")),
        ),
    )
    proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=uuid4(),
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(uuid4(),),
        geometria=geometry,
        confianca=Decimal("0.9"),
    )
    viewer.definir_propostas_revisao((proposal,))

    for rotation in (90, 180, 270, 0):
        viewer._rotate_page()
        _wait_preview(qtbot, viewer, rotation=rotation)
        transformer = viewer._current_transformer
        assert transformer is not None
        marker = viewer.view._review_items[str(proposal.id)]
        pixels = tuple(transformer.normalizado_para_pixel(point) for point in geometry.pontos)
        expected_left = min(point.x for point in pixels)
        expected_bottom = min(
            float(transformer.altura_pixels) - 2,
            max(point.y for point in pixels) + 5,
        )
        path_start = marker.path().elementAt(0)
        assert path_start.x == pytest.approx(expected_left)
        assert path_start.y == pytest.approx(expected_bottom)

    marker = viewer.view._review_items[str(proposal.id)]
    target = viewer.view.mapFromScene(marker.mapToScene(marker.path().pointAtPercent(0.5)))
    with qtbot.waitSignal(viewer.proposal_selected, timeout=1_000) as selected:
        qtbot.mouseClick(  # type: ignore[no-untyped-call]
            viewer.view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=QPoint(target.x(), target.y()),
        )
    assert selected.args == [str(proposal.id)]


@pytest.mark.integration
def test_closing_stops_render_thread_and_closes_verified_sessions(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_feature_pdf(tmp_path / "fechamento.pdf")
    reader = _ControlledReader(block_first=True)
    viewer = _viewer(qtbot, cast(LeitorPdfPort, reader))

    assert viewer.carregar_pdf(source)
    assert reader.entered.wait(timeout=1)
    assert not viewer._render_queue.esta_ociosa()
    reader.release.set()
    viewer.close()

    assert not viewer._render_queue.isRunning()
    assert all(session.closed for session in reader.sessions)
    assert viewer._render_cache.bytes_usados == 0
