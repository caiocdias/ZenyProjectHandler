"""Optional local neural evidence, streamed by bounded tiles and distinct layers."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any

from zeny_project_handler.application.method_reconciliation import (
    COMPOSITION_VERSION,
    READING_KEY,
    reading_identity,
)
from zeny_project_handler.domain.analysis import DiagnosticoAnalise, OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    ExtracaoDocumentoNormalizada,
    GeometriaNormalizada,
    PaginaRasterOcr,
    SolicitacaoAnaliseDocumento,
)

from .pymupdf_analyzer import _open_document
from .rapid_ocr import RapidLocalOcr, map_quad


@dataclass(frozen=True, slots=True)
class LeituraOcrLegenda:
    """OCR opcional em pontos da página; não é hipótese de símbolo."""

    pagina_numero: int
    texto: str
    caixa: tuple[float, float, float, float]
    confianca: float


def extrair_leituras_ocr_legenda(
    document: Any,
    *,
    factory: Callable[[], RapidLocalOcr] = RapidLocalOcr,
    dpi: int = 144,
    limite_pixels: int = 8_000_000,
) -> tuple[tuple[LeituraOcrLegenda, ...], tuple[str, ...]]:
    """Lê páginas independentemente de ROIs; falha de OCR preserva outros motores.

    A implementação neural é opcional. O chamador registra diagnósticos e
    continua com o texto nativo quando ela não está instalada ou uma página falha.
    """
    try:
        engine = factory()
    except Exception as error:
        return (), (f"OCR de legenda indisponível: {type(error).__name__}",)
    readings: list[LeituraOcrLegenda] = []
    diagnostics: list[str] = []
    for page in document:
        number = page.number + 1
        try:
            scale = dpi / 72
            if (page.rect.width * scale + 2) * (page.rect.height * scale + 2) > limite_pixels:
                raise ValueError("página excede o limite de pixels do OCR")
            pix = page.get_pixmap(dpi=dpi, annots=False, alpha=False)
            if pix.width * pix.height > limite_pixels:
                raise ValueError("página excede o limite de pixels do OCR")
            raster = PaginaRasterOcr(
                pagina_numero=number,
                largura_pixels=pix.width,
                altura_pixels=pix.height,
                stride=pix.stride,
                dados_rgb=pix.samples,
                dpi=dpi,
            )
            for row in engine.recognize_quads(raster):
                points = [
                    ((float(x) + pix.x) / scale, (float(y) + pix.y) / scale) for x, y in row["quad"]
                ]
                readings.append(
                    LeituraOcrLegenda(
                        pagina_numero=number,
                        texto=str(row["text"]),
                        caixa=(
                            min(x for x, _ in points),
                            min(y for _, y in points),
                            max(x for x, _ in points),
                            max(y for _, y in points),
                        ),
                        confianca=float(row["confidence"]),
                    )
                )
        except Exception as error:
            diagnostics.append(f"OCR de legenda p{number}: {type(error).__name__}")
        finally:
            try:
                engine.calls.clear()
            except Exception as error:
                diagnostics.append(f"OCR de legenda p{number}: limpeza {type(error).__name__}")
    return tuple(readings), tuple(diagnostics)


class RapidEvidenceExtractor:
    """Lazy runtime: unavailable engines produce incomplete evidence, never fallback success."""

    def __init__(self, factory: Callable[[], RapidLocalOcr] = RapidLocalOcr) -> None:
        self._factory = factory
        self._engine: RapidLocalOcr | None = None

    def _runtime(self) -> RapidLocalOcr:
        if self._engine is None:
            self._engine = self._factory()
        return self._engine

    @property
    def assinatura_capacidade(self) -> str:
        try:
            runtime = self._runtime().capability.assinatura()
        except Exception:
            runtime = "unavailable"
        return sha256(
            json.dumps(
                {
                    "composition": COMPOSITION_VERSION,
                    "runtime": runtime,
                    "grid": [3, 4],
                    "overlap": 0.02,
                    "dpi": 600,
                    "layers": ["base", "appearance"],
                    "max_pixels": 8_000_000,
                    "max_readings": 10000,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()

    def extrair(self, solicitacao: SolicitacaoAnaliseDocumento) -> ExtracaoDocumentoNormalizada:
        candidates: list[CandidatoEvidenciaDocumento] = []
        diagnostics: list[DiagnosticoAnalise] = []
        try:
            engine = self._runtime()
        except Exception as error:
            return ExtracaoDocumentoNormalizada(
                candidatos=(), diagnosticos=(_diagnostic("unavailable", type(error).__name__),)
            )
        signature = self.assinatura_capacidade
        document = _open_document(solicitacao.fonte.caminho_canonico, solicitacao.senha)
        completed = 0
        total = document.page_count * 24
        try:
            for page in document:
                for annotations in (False, True):
                    for row in range(4):
                        for column in range(3):
                            if solicitacao.cancelado and solicitacao.cancelado():
                                return ExtracaoDocumentoNormalizada(
                                    candidatos=tuple(candidates),
                                    diagnosticos=(
                                        *diagnostics,
                                        _diagnostic("cancelled", "Cancelamento solicitado"),
                                    ),
                                )
                            tile = f"p{page.number + 1}-{annotations}-{row}-{column}"
                            try:
                                candidates.extend(
                                    self._tile(
                                        engine,
                                        page,
                                        annotations,
                                        row,
                                        column,
                                        tile,
                                        solicitacao.fonte.sha256,
                                        signature,
                                    )
                                )
                            except Exception as error:
                                diagnostics.append(
                                    _diagnostic("failed", f"{tile}: {type(error).__name__}")
                                )
                            engine.calls.clear()
                            if len(candidates) > 10000:
                                return ExtracaoDocumentoNormalizada(
                                    candidatos=tuple(candidates[:10000]),
                                    diagnosticos=(
                                        *diagnostics,
                                        _diagnostic(
                                            "capacity",
                                            "Limite de 10000 leituras; cobertura incompleta",
                                        ),
                                    ),
                                )
                            completed += 1
                            if solicitacao.progresso:
                                solicitacao.progresso(
                                    completed,
                                    total,
                                    f"Verificação neural {completed}/{total}; "
                                    f"falhas {len(diagnostics)}",
                                )
        finally:
            document.close()
            engine.calls.clear()
        return ExtracaoDocumentoNormalizada(
            candidatos=tuple(candidates), diagnosticos=tuple(diagnostics)
        )

    def _tile(
        self,
        engine: RapidLocalOcr,
        page: object,
        annotations: bool,
        row: int,
        column: int,
        tile: str,
        source: str,
        signature: str,
    ) -> tuple[CandidatoEvidenciaDocumento, ...]:
        # PyMuPDF's dynamic page API is isolated at the adapter boundary.
        from typing import Any, cast

        import pymupdf

        pdf_page = cast(Any, page)
        clip = pymupdf.Rect(  # type: ignore[no-untyped-call]
            max(0, column / 3 - 0.02) * pdf_page.rect.width,
            max(0, row / 4 - 0.02) * pdf_page.rect.height,
            min(1, (column + 1) / 3 + 0.02) * pdf_page.rect.width,
            min(1, (row + 1) / 4 + 0.02) * pdf_page.rect.height,
        )
        if (clip.width * 600 / 72 + 2) * (clip.height * 600 / 72 + 2) > 8_000_000:
            raise ValueError("Tile exceeds 8 MP memory budget")
        pix = pdf_page.get_pixmap(dpi=600, clip=clip, annots=annotations, alpha=False)
        raster = PaginaRasterOcr(
            pagina_numero=pdf_page.number + 1,
            largura_pixels=pix.width,
            altura_pixels=pix.height,
            stride=pix.stride,
            dados_rgb=pix.samples,
            dpi=600,
        )
        raster_hash = sha256(raster.dados_rgb).hexdigest()
        rows = engine.recognize_quads(raster)
        result = []
        for index, reading in enumerate(rows):
            quad = map_quad(
                reading["quad"],
                raster_origin=(pix.x, pix.y),
                scale=600 / 72,
                page_size=(pdf_page.rect.width, pdf_page.rect.height),
            )
            layer = "appearance" if annotations else "base"
            identity = reading_identity(
                source, pdf_page.number + 1, layer, signature, quad, reading["text"]
            )
            provenance = {
                "identity": identity,
                "source_sha256": source,
                "page": pdf_page.number + 1,
                "layer": layer,
                "tile": tile,
                "literal": reading["text"],
                "geometry": quad,
                "method": engine.nome,
                "version": engine.versao,
                "models": engine.models,
                "capability_signature": signature,
                "raw_score": reading["confidence"],
                "score_is_probability": False,
                "raster_sha256": raster_hash,
                "transform": {
                    "origin": [pix.x, pix.y],
                    "scale": 600 / 72,
                    "page_size": [pdf_page.rect.width, pdf_page.rect.height],
                },
            }
            result.append(
                CandidatoEvidenciaDocumento(
                    chave_estavel=f"aux:{tile}:{index}:{identity}",
                    pagina_numero=pdf_page.number + 1,
                    tipo=TipoEvidencia.OCR,
                    geometria=GeometriaNormalizada(
                        tipo=TipoGeometria.POLIGONO,
                        pontos=tuple(
                            PontoNormalizado(Decimal(str(x)), Decimal(str(y))) for x, y in quad
                        ),
                    ),
                    origem_pdf=OrigemObjetoPdf(nome_recurso=f"render:{layer}:{tile}"),
                    atributos_extraidos=(
                        (READING_KEY, json.dumps(provenance, ensure_ascii=False)),
                    ),
                )
            )
        return tuple(result)


def _diagnostic(reason: str, detail: str) -> DiagnosticoAnalise:
    return DiagnosticoAnalise(
        codigo=f"analysis.complementary.{reason}",
        mensagem=f"Verificação complementar incompleta; evidências preservadas. {detail}",
        extrator="rapidocr-db-svtr",
    )
