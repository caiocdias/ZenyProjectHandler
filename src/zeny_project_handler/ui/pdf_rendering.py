"""Agendamento e cache do raster progressivo, sem dependência de widgets Qt."""

from __future__ import annotations

import heapq
import math
from collections import OrderedDict, deque
from collections.abc import Hashable
from dataclasses import dataclass
from threading import Condition, Event, Lock
from typing import Generic, TypeVar
from uuid import UUID

from PySide6.QtCore import QThread

from zeny_project_handler.adapters.pdf.errors import PdfError
from zeny_project_handler.logging_config import operation_logger
from zeny_project_handler.ports.pdf import (
    VIEWER_BYTES_PER_PIXEL_ESTIMATE,
    OrcamentoRenderizacaoPdf,
    PdfRectangle,
    PlanoRenderizacaoPdf,
    SessaoLeituraPdfPort,
)

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


@dataclass(frozen=True, slots=True)
class IdentidadeDocumentoRenderizacao:
    """Identidade forte da sessão, complementada pelos metadados verificados."""

    documento_id: UUID
    sha256: str
    tamanho_bytes: int
    modificado_em_ns: int


@dataclass(frozen=True, slots=True)
class ChaveCacheRenderizacao:
    documento: IdentidadeDocumentoRenderizacao
    pagina: int
    rotacao: int
    zoom: float
    device_pixel_ratio: float
    regiao: PdfRectangle
    dpi: int
    previa: bool


@dataclass(frozen=True, slots=True)
class SolicitacaoRenderizacao:
    """Identifica integralmente uma resposta que pode chegar fora de sequência."""

    geracao: int
    documento: IdentidadeDocumentoRenderizacao
    pagina: int
    rotacao: int
    zoom: float
    device_pixel_ratio: float
    regiao: PdfRectangle
    dpi: int
    previa: bool

    @property
    def chave_cache(self) -> ChaveCacheRenderizacao:
        return ChaveCacheRenderizacao(
            documento=self.documento,
            pagina=self.pagina,
            rotacao=self.rotacao,
            zoom=self.zoom,
            device_pixel_ratio=self.device_pixel_ratio,
            regiao=self.regiao,
            dpi=self.dpi,
            previa=self.previa,
        )


class CancelamentoRenderizacao:
    """Token simples que permite descartar trabalho entre tiles independentes."""

    def __init__(self) -> None:
        self._event = Event()

    @property
    def cancelado(self) -> bool:
        return self._event.is_set()

    def cancelar(self) -> None:
        self._event.set()


@dataclass(frozen=True, slots=True)
class TrabalhoRenderizacao:
    solicitacao: SolicitacaoRenderizacao
    sessao: SessaoLeituraPdfPort
    orcamento: OrcamentoRenderizacaoPdf
    prioridade: int
    cancelamento: CancelamentoRenderizacao


@dataclass(frozen=True, slots=True)
class RasterRgbRenderizado:
    """Raster RGB proprietário, seguro para atravessar a fronteira da thread."""

    pagina_numero: int
    rotacao_adicional_graus: int
    largura_pixels: int
    altura_pixels: int
    stride: int
    dados_rgb: bytes
    plano: PlanoRenderizacaoPdf


@dataclass(frozen=True, slots=True)
class ResultadoRenderizacao:
    solicitacao: SolicitacaoRenderizacao
    pagina: RasterRgbRenderizado | None = None
    erro: Exception | None = None

    def __post_init__(self) -> None:
        if (self.pagina is None) == (self.erro is None):
            raise ValueError("O resultado deve conter exatamente uma página ou um erro")


class CacheLruBytes(Generic[K, V]):
    """LRU com limite estrito pelo custo informado de cada valor."""

    def __init__(self, limite_bytes: int) -> None:
        if limite_bytes <= 0:
            raise ValueError("O limite do cache deve ser positivo")
        self._limite_bytes = limite_bytes
        self._bytes_usados = 0
        self._values: OrderedDict[K, tuple[V, int]] = OrderedDict()

    @property
    def limite_bytes(self) -> int:
        return self._limite_bytes

    @property
    def bytes_usados(self) -> int:
        return self._bytes_usados

    def __len__(self) -> int:
        return len(self._values)

    def obter(self, key: K) -> V | None:
        stored = self._values.get(key)
        if stored is None:
            return None
        self._values.move_to_end(key)
        return stored[0]

    def armazenar(self, key: K, value: V, *, tamanho_bytes: int) -> bool:
        if tamanho_bytes <= 0:
            raise ValueError("O tamanho da entrada do cache deve ser positivo")
        if tamanho_bytes > self._limite_bytes:
            return False
        previous = self._values.pop(key, None)
        if previous is not None:
            self._bytes_usados -= previous[1]
        while self._values and self._bytes_usados + tamanho_bytes > self._limite_bytes:
            _old_key, (_old_value, old_size) = self._values.popitem(last=False)
            self._bytes_usados -= old_size
        self._values[key] = (value, tamanho_bytes)
        self._bytes_usados += tamanho_bytes
        return True

    def limpar(self) -> None:
        self._values.clear()
        self._bytes_usados = 0


class FilaRenderizacao(QThread):
    """Fila serial priorizada; toda rasterização ocorre em sua thread dedicada."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("pdfRenderThread")
        self._condition = Condition(Lock())
        self._queue: list[tuple[int, int, TrabalhoRenderizacao]] = []
        self._results: deque[ResultadoRenderizacao] = deque()
        self._sequence = 0
        self._active = False
        self._active_cancellation: CancelamentoRenderizacao | None = None
        self._stopping = False
        self._started = False

    def enviar(self, work: TrabalhoRenderizacao) -> bool:
        with self._condition:
            if self._stopping:
                return False
            self._sequence += 1
            heapq.heappush(self._queue, (work.prioridade, self._sequence, work))
            self._condition.notify()
            should_start = not self._started
            self._started = True
        if should_start:
            self.start()
        return True

    def encerrar(self) -> None:
        with self._condition:
            self._stopping = True
            if self._active_cancellation is not None:
                self._active_cancellation.cancelar()
            for _priority, _sequence, work in self._queue:
                work.cancelamento.cancelar()
            self._queue.clear()
            self._condition.notify_all()

    def cancelar_e_aguardar_ociosa(self, timeout_ms: int) -> bool:
        """Cancele trabalhos e espere, com limite, a rasterização ativa liberar a sessão."""
        if timeout_ms < 0:
            raise ValueError("O tempo limite para liberar a renderização não pode ser negativo")
        with self._condition:
            if self._active_cancellation is not None:
                self._active_cancellation.cancelar()
            for _priority, _sequence, work in self._queue:
                work.cancelamento.cancelar()
            self._queue.clear()
            self._condition.notify_all()
            return self._condition.wait_for(
                lambda: not self._active and not self._queue,
                timeout=timeout_ms / 1000,
            )

    def esta_ociosa(self) -> bool:
        with self._condition:
            return not self._active and not self._queue

    def retirar_resultados(self) -> tuple[ResultadoRenderizacao, ...]:
        with self._condition:
            results = tuple(self._results)
            self._results.clear()
        return results

    def run(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._stopping:
                    self._condition.wait()
                if self._stopping:
                    self._active = False
                    self._active_cancellation = None
                    self._condition.notify_all()
                    break
                _priority, _sequence, work = heapq.heappop(self._queue)
                self._active = True
                self._active_cancellation = work.cancelamento
            try:
                self._executar(work)
            finally:
                with self._condition:
                    self._active = False
                    self._active_cancellation = None
                    self._condition.notify_all()

    def _executar(self, work: TrabalhoRenderizacao) -> None:
        if work.cancelamento.cancelado:
            return
        request = work.solicitacao
        observation = operation_logger(
            "pdf.viewer.render",
            document_id=request.documento.documento_id,
        )
        with observation.context():
            observation.started()
            try:
                rendered = work.sessao.renderizar_pagina(
                    request.pagina,
                    dpi=request.dpi,
                    orcamento=work.orcamento,
                    rotacao_adicional_graus=request.rotacao,
                    recorte_normalizado=None if request.previa else request.regiao,
                )
            except Exception as error:
                if work.cancelamento.cancelado:
                    observation.cancelled()
                    return
                observation.failed(error, expected=isinstance(error, PdfError))
                with self._condition:
                    self._results.append(ResultadoRenderizacao(solicitacao=request, erro=error))
                return
            if work.cancelamento.cancelado:
                observation.cancelled()
                return
            raster = RasterRgbRenderizado(
                pagina_numero=rendered.pagina_numero,
                rotacao_adicional_graus=rendered.rotacao_adicional_graus,
                largura_pixels=rendered.largura_pixels,
                altura_pixels=rendered.altura_pixels,
                stride=rendered.stride,
                dados_rgb=bytes(rendered.dados_rgb),
                plano=rendered.plano,
            )
            # O Pixmap nativo do PyMuPDF nasceu nesta thread e também deve ser
            # liberado aqui. Somente o buffer Python proprietário segue para a UI.
            del rendered
            if work.cancelamento.cancelado:
                observation.cancelled()
                return
            observation.succeeded()
            with self._condition:
                self._results.append(ResultadoRenderizacao(solicitacao=request, pagina=raster))


def regioes_tiles_priorizadas(
    *,
    largura_pagina_pixels: int,
    altura_pagina_pixels: int,
    dpi_previa: int,
    dpi_detalhe: int,
    viewport_normalizado: PdfRectangle,
    rotacao: int,
    orcamento: OrcamentoRenderizacaoPdf,
) -> tuple[tuple[int, PdfRectangle], ...]:
    """Planeje apenas viewport e uma margem de um tile, com visíveis primeiro."""
    if min(largura_pagina_pixels, altura_pagina_pixels, dpi_previa, dpi_detalhe) <= 0:
        raise ValueError("Dimensões e DPIs de tiles devem ser positivos")
    target_width = max(1, round(largura_pagina_pixels * dpi_detalhe / dpi_previa))
    target_height = max(1, round(altura_pagina_pixels * dpi_detalhe / dpi_previa))
    pixel_capacity = min(
        orcamento.limite_pixels,
        orcamento.limite_bytes // VIEWER_BYTES_PER_PIXEL_ESTIMATE,
    )
    if pixel_capacity <= 0:
        raise ValueError("O orçamento não comporta nem um pixel do visualizador")
    edge = max(1, math.isqrt(pixel_capacity) - 2)
    columns = max(1, math.ceil(target_width / edge))
    rows = max(1, math.ceil(target_height / edge))
    visible = _clamped_rectangle(viewport_normalizado)
    first_column, last_column = _covered_indices(visible[0], visible[2], columns)
    first_row, last_row = _covered_indices(visible[1], visible[3], rows)
    visible_center = ((visible[0] + visible[2]) / 2, (visible[1] + visible[3]) / 2)
    planned: list[tuple[int, PdfRectangle]] = []
    for row in range(max(0, first_row - 1), min(rows - 1, last_row + 1) + 1):
        for column in range(max(0, first_column - 1), min(columns - 1, last_column + 1) + 1):
            visual_region = _grid_region(column, row, columns, rows)
            visible_tile = first_column <= column <= last_column and first_row <= row <= last_row
            center = (
                (visual_region[0] + visual_region[2]) / 2,
                (visual_region[1] + visual_region[3]) / 2,
            )
            distance = round(
                ((center[0] - visible_center[0]) ** 2 + (center[1] - visible_center[1]) ** 2)
                * 1_000_000
            )
            priority = distance if visible_tile else 1_000_000 + distance
            planned.append((priority, _visual_para_canonico(visual_region, rotacao)))
    planned.sort(key=lambda item: (item[0], item[1]))
    return tuple(planned)


def _covered_indices(start: float, end: float, count: int) -> tuple[int, int]:
    first = min(count - 1, max(0, math.floor(start * count)))
    last = min(count - 1, max(first, math.ceil(end * count) - 1))
    return first, last


def _grid_region(column: int, row: int, columns: int, rows: int) -> PdfRectangle:
    return _rounded_rectangle(
        (column / columns, row / rows, (column + 1) / columns, (row + 1) / rows)
    )


def _visual_para_canonico(region: PdfRectangle, rotation: int) -> PdfRectangle:
    x0, y0, x1, y1 = region
    corners = (
        _unrotate(x0, y0, rotation),
        _unrotate(x1, y0, rotation),
        _unrotate(x0, y1, rotation),
        _unrotate(x1, y1, rotation),
    )
    return _rounded_rectangle(
        (
            min(point[0] for point in corners),
            min(point[1] for point in corners),
            max(point[0] for point in corners),
            max(point[1] for point in corners),
        )
    )


def _unrotate(x: float, y: float, rotation: int) -> tuple[float, float]:
    if rotation == 90:
        return y, 1 - x
    if rotation == 180:
        return 1 - x, 1 - y
    if rotation == 270:
        return 1 - y, x
    if rotation == 0:
        return x, y
    raise ValueError("Rotação deve ser 0, 90, 180 ou 270 graus")


def _clamped_rectangle(region: PdfRectangle) -> PdfRectangle:
    x0, y0, x1, y1 = region
    return (
        min(1.0, max(0.0, x0)),
        min(1.0, max(0.0, y0)),
        min(1.0, max(0.0, x1)),
        min(1.0, max(0.0, y1)),
    )


def _rounded_rectangle(region: PdfRectangle) -> PdfRectangle:
    return tuple(round(value, 12) for value in region)  # type: ignore[return-value]
