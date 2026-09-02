from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from threading import Event, get_ident
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from pytestqt.qtbot import QtBot
from tests.pdf_fixtures import TEST_RENDER_BUDGET, create_feature_pdf, create_golden_pdf
from tests.viewer_gateway import LocalTestPdfViewerGateway

from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf
from zeny_project_handler_client.ui.pdf_gateway import PdfViewerGateway, RemoteRaster
from zeny_project_handler_client.ui.pdf_rendering import (
    CacheLruBytes,
    PdfRectangle,
    regioes_tiles_priorizadas,
)
from zeny_project_handler_client.ui.pdf_viewer import PdfViewerWidget
from zeny_project_handler_contracts.base import PageId, ProposalId
from zeny_project_handler_contracts.common import NormalizedBoxDto, NormalizedPointDto
from zeny_project_handler_contracts.enums import (
    ElementCategory,
    ElementSituation,
    ReviewGeometryKind,
    ReviewState,
)
from zeny_project_handler_contracts.review import ReviewGeometryDto, ReviewOverlayDto
from zeny_project_handler_contracts.viewer import (
    CloseViewerSessionResponse,
    CreateViewerSessionResponse,
    UnlockViewerPdfResponse,
    ViewerDocumentDto,
    ViewerPageDto,
    ViewerProjectResponse,
)

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


class _ControlledGateway:
    def __init__(self, *, block_first: bool = False) -> None:
        self._delegate = LocalTestPdfViewerGateway(budget=TEST_RENDER_BUDGET)
        self._block_first = block_first
        self.entered = Event()
        self.release = Event()
        self.calls: list[_RenderCall] = []
        self.created_session_ids: list[UUID] = []
        self.closed_session_ids: list[UUID] = []
        self._page_numbers: dict[UUID, int] = {}

    def create_session(
        self,
        paths: tuple[Path, ...],
        *,
        idempotency_key: str,
    ) -> CreateViewerSessionResponse:
        response = self._delegate.create_session(paths, idempotency_key=idempotency_key)
        self.created_session_ids.append(response.viewer_session_id.root)
        for document in response.documents:
            for page in document.pages:
                self._page_numbers[page.page_id.root] = page.source_page_number
        return response

    def unlock_session_pdf(
        self,
        session_id: UUID,
        upload_id: UUID,
        password: str,
    ) -> UnlockViewerPdfResponse:
        response = self._delegate.unlock_session_pdf(session_id, upload_id, password)
        for document in response.documents:
            for page in document.pages:
                self._page_numbers[page.page_id.root] = page.source_page_number
        return response

    def close_session(self, session_id: UUID) -> CloseViewerSessionResponse:
        response = self._delegate.close_session(session_id)
        if response.closed:
            self.closed_session_ids.append(session_id)
        return response

    def get_project(self, project_id: UUID) -> ViewerProjectResponse:
        return self._delegate.get_project(project_id)

    def get_page(self, page_id: UUID) -> ViewerPageDto:
        return self._delegate.get_page(page_id)

    def unlock_project_document(
        self,
        document_id: UUID,
        password: str,
    ) -> ViewerDocumentDto:
        return self._delegate.unlock_project_document(document_id, password)

    def render_preview(self, page_id: UUID, *, dpi: int, rotation: int) -> RemoteRaster:
        self._record(page_id, dpi=dpi, rotation=rotation, region=None)
        return self._delegate.render_preview(page_id, dpi=dpi, rotation=rotation)

    def render_tile(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        clip: NormalizedBoxDto,
    ) -> RemoteRaster:
        x = float(clip.x)
        y = float(clip.y)
        region = (x, y, x + float(clip.width), y + float(clip.height))
        self._record(page_id, dpi=dpi, rotation=rotation, region=region)
        return self._delegate.render_tile(
            page_id,
            dpi=dpi,
            rotation=rotation,
            clip=clip,
        )

    def close(self) -> None:
        self._delegate.close()

    def _record(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        region: PdfRectangle | None,
    ) -> None:
        self.calls.append(
            _RenderCall(
                pagina=self._page_numbers[page_id],
                dpi=dpi,
                rotacao=rotation,
                regiao=region,
                thread_id=get_ident(),
            )
        )
        if self._block_first and len(self.calls) == 1:
            self.entered.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("O teste não liberou a rasterização controlada")


def _viewer(
    qtbot: QtBot,
    gateway: PdfViewerGateway,
    *,
    dpi: int = 600,
    budget: OrcamentoRenderizacaoPdf = SMALL_TILE_BUDGET,
    cache_limit: int = 128 * 1024 * 1024,
) -> PdfViewerWidget:
    viewer = PdfViewerWidget(
        gateway=gateway,
        dpi=dpi,
        limite_pixels_tile=min(budget.limite_pixels, budget.limite_bytes // 7),
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
        lambda: (
            viewer._current_preview is not None
            and viewer.folha_atual == page
            and viewer._current_preview.plano.rotacao_adicional_graus == rotation
        ),
        timeout=5_000,
    )


@pytest.mark.integration
def test_rendering_is_responsive_and_never_rasterizes_on_ui_thread(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_feature_pdf(tmp_path / "responsivo.pdf")
    gateway = _ControlledGateway(block_first=True)
    viewer = _viewer(qtbot, gateway, dpi=72, budget=TEST_RENDER_BUDGET)
    ui_thread = get_ident()
    event_loop_ran: list[bool] = []

    assert viewer.carregar_pdf(source)
    assert gateway.entered.wait(timeout=1)
    QTimer.singleShot(0, lambda: event_loop_ran.append(True))

    qtbot.waitUntil(lambda: bool(event_loop_ran))
    assert viewer.view.scene().items() == []
    gateway.release.set()
    _wait_preview(qtbot, viewer)

    assert gateway.calls[0].thread_id != ui_thread


@pytest.mark.integration
def test_old_page_result_is_discarded_after_out_of_order_navigation(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_feature_pdf(tmp_path / "fora-de-sequencia.pdf")
    gateway = _ControlledGateway(block_first=True)
    viewer = _viewer(qtbot, gateway, dpi=72, budget=TEST_RENDER_BUDGET)

    assert viewer.carregar_pdf(source)
    assert gateway.entered.wait(timeout=1)
    viewer.ir_para_folha(2)
    gateway.release.set()
    _wait_preview(qtbot, viewer, page=2)

    assert [call.pagina for call in gateway.calls[:2]] == [1, 2]
    assert viewer._current_preview is not None
    assert viewer.folha_atual == 2
    assert viewer._current_transformer is not None
    assert viewer._current_transformer.pagina.source_page_number == 2


@pytest.mark.integration
def test_document_exchange_clears_cache_and_upload_copy_isolated_from_client_source(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    first = create_feature_pdf(tmp_path / "primeiro.pdf")
    second = create_golden_pdf(tmp_path / "segundo.pdf")
    gateway = LocalTestPdfViewerGateway()
    viewer = _viewer(qtbot, gateway)

    assert viewer.carregar_pdf(first)
    _wait_preview(qtbot, viewer)
    assert viewer._render_cache.bytes_usados > 0

    assert viewer.carregar_pdf(second)
    assert viewer._render_cache.bytes_usados == 0
    _wait_preview(qtbot, viewer)
    second.write_bytes(second.read_bytes() + b"\n")
    viewer.view.definir_zoom(4.0)

    qtbot.waitUntil(lambda: viewer._render_queue.esta_ociosa(), timeout=5_000)
    assert viewer.inspecao is not None
    assert viewer._render_cache.bytes_usados > 0


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
    viewer = _viewer(
        qtbot,
        LocalTestPdfViewerGateway(budget=SMALL_TILE_BUDGET),
        cache_limit=cache_limit,
    )

    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    viewer.view.definir_zoom(4.0)
    qtbot.waitUntil(
        lambda: len(viewer._render_cache) >= 1,
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
        limite_pixels_tile=min(budget.limite_pixels, budget.limite_bytes // 7),
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
    viewer = _viewer(
        qtbot,
        LocalTestPdfViewerGateway(budget=TEST_RENDER_BUDGET),
        dpi=72,
        budget=TEST_RENDER_BUDGET,
    )
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    page_id = viewer.inspecao.pages[0].page_id.root
    geometry = GeometriaDocumento.polilinha(
        page_id,
        (
            PontoNormalizado(Decimal("0.2"), Decimal("0.3")),
            PontoNormalizado(Decimal("0.7"), Decimal("0.6")),
        ),
    )
    proposal_id = ProposalId(uuid4())
    geometry_dto = ReviewGeometryDto(
        page_id=PageId(page_id),
        kind=ReviewGeometryKind.POLYLINE,
        points=tuple(
            NormalizedPointDto(x=str(point.x), y=str(point.y)) for point in geometry.pontos
        ),
    )
    proposal = ReviewOverlayDto(
        proposal_id=proposal_id,
        geometry=geometry_dto,
        link_geometry=geometry_dto,
        label="Poste",
        category=ElementCategory.POLE,
        situation=ElementSituation.CHANGE,
        situation_label="A alterar",
        review_state=ReviewState.PENDING,
        confidence="0.9",
    )
    viewer.definir_propostas_revisao((proposal,))
    marker = viewer.view._review_items[str(proposal_id.root)]
    assert "A alterar" in marker.toolTip()

    for rotation in (90, 180, 270, 0):
        viewer._rotate_page()
        _wait_preview(qtbot, viewer, rotation=rotation)
        transformer = viewer._current_transformer
        assert transformer is not None
        marker = viewer.view._review_items[str(proposal_id.root)]
        pixels = tuple(transformer.normalizado_para_pixel(point) for point in geometry.pontos)
        expected_left = min(point.x for point in pixels)
        expected_bottom = min(
            float(transformer.altura_pixels) - 2,
            max(point.y for point in pixels) + 5,
        )
        path_start = marker.path().elementAt(0)
        assert path_start.x == pytest.approx(expected_left)
        assert path_start.y == pytest.approx(expected_bottom)

    marker = viewer.view._review_items[str(proposal_id.root)]
    target = viewer.view.mapFromScene(marker.mapToScene(marker.path().pointAtPercent(0.5)))
    with qtbot.waitSignal(viewer.proposal_selected, timeout=1_000) as selected:
        qtbot.mouseClick(  # type: ignore[no-untyped-call]
            viewer.view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=QPoint(target.x(), target.y()),
        )
    assert selected.args == [str(proposal_id.root)]


@pytest.mark.integration
def test_closing_stops_render_thread_and_closes_verified_sessions(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_feature_pdf(tmp_path / "fechamento.pdf")
    gateway = _ControlledGateway(block_first=True)
    viewer = _viewer(qtbot, gateway)

    assert viewer.carregar_pdf(source)
    assert gateway.entered.wait(timeout=1)
    assert not viewer._render_queue.esta_ociosa()
    gateway.release.set()
    viewer.close()

    assert not viewer._render_queue.isRunning()
    assert gateway.closed_session_ids == gateway.created_session_ids
    assert viewer._render_cache.bytes_usados == 0


@pytest.mark.integration
def test_restore_preparation_is_bounded_and_only_closes_sessions_after_render_releases(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_feature_pdf(tmp_path / "restauracao-com-render-bloqueado.pdf")
    gateway = _ControlledGateway(block_first=True)
    viewer = _viewer(qtbot, gateway, dpi=72, budget=TEST_RENDER_BUDGET)

    assert viewer.carregar_pdf(source)
    assert gateway.entered.wait(timeout=1)

    assert not viewer.preparar_para_restauracao(timeout_ms=10)
    assert viewer.inspecao is not None
    assert not gateway.closed_session_ids

    gateway.release.set()

    assert viewer.preparar_para_restauracao(timeout_ms=1_000)
    assert viewer._render_queue.esta_ociosa()
    assert viewer.inspecao is None
    assert gateway.closed_session_ids == gateway.created_session_ids
    assert viewer._render_cache.bytes_usados == 0
