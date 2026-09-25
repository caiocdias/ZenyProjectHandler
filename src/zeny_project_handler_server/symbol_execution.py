"""Opt-in, fail-closed server execution of the approved E12 symbol union."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import asdict
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

import pymupdf
from PIL import __version__ as pillow_version

from zeny_project_handler._atomic_files import sibling_temporary_file
from zeny_project_handler.adapters.analysis import (
    declarative_symbols,
    legacy_symbols,
    legend_symbols,
    pymupdf_guys,
    pymupdf_transformers,
    raster_symbols,
)
from zeny_project_handler.adapters.analysis.pymupdf_analyzer import (
    _open_document,
    _verify_source,
)
from zeny_project_handler.adapters.analysis.raster_symbols import SymbolScanCancelledError
from zeny_project_handler.adapters.persistence.domain_json import dumps_domain, loads_domain
from zeny_project_handler.adapters.persistence.errors import DomainCodecError
from zeny_project_handler.application import symbol_reconciliation
from zeny_project_handler.application.errors import FluxoMvpCanceladoError
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    SymbolReconciliation,
    reconcile_symbols,
)
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import ResultadoMetodoSimbolos
from zeny_project_handler.ports.pdf import ReferenciaFontePdf

from .config import ServerSettings

_VERSION = "e15-server-symbol-composition-1"
_COMPLETE = frozenset(
    {
        EstadoMetodoSimbolos.CONCLUIDO,
        EstadoMetodoSimbolos.NAO_DETECCAO,
        EstadoMetodoSimbolos.FORA_DOMINIO,
    }
)


class SymbolCompositionError(RuntimeError):
    """An enabled symbol method did not complete its declared coverage."""


class SymbolCompositionRunner:
    """One verified PDF at a time; partial journal is never an integral cache."""

    def __init__(
        self,
        settings: ServerSettings,
        *,
        templates: tuple[raster_symbols.TemplateRasterVerificado, ...] | None = None,
        packages: tuple[declarative_symbols.Package, ...] | None = None,
        calibration: CalibrationPolicy | None = None,
    ) -> None:
        self._settings = settings
        self._templates = (
            raster_symbols.carregar_templates_raster() if templates is None else tuple(templates)
        )
        self._packages = (
            declarative_symbols.carregar_pacotes() if packages is None else tuple(packages)
        )
        self._calibration = calibration or CalibrationPolicy()
        self._raster_config = raster_symbols.ConfiguracaoDetectorRaster(
            dpi=settings.symbol_raster_dpi,
            tile_pixels=settings.symbol_tile_pixels,
            sobreposicao_pixels=min(96, settings.symbol_tile_pixels // 4),
            limite_bytes=settings.symbol_tile_max_bytes,
        )
        self._legend_config = legend_symbols.ConfiguracaoLegenda(
            dpi=settings.symbol_raster_dpi,
            tile_pixels=settings.symbol_tile_pixels,
            sobreposicao_pixels=min(128, settings.symbol_tile_pixels // 4),
            limite_pixels_pagina=max(1, settings.symbol_tile_max_bytes // 20),
        )
        self.partial_directory = settings.data_directory / "symbol_partial_runs"
        self.cache_directory = settings.core_settings().analysis_cache_directory / "symbols"
        self._model_identity = _model_identity(settings.symbol_model_path)
        profiles = [
            legacy_symbols.perfil_simbolos_legados(),
            pymupdf_transformers.perfil_transformadores(),
            pymupdf_guys.perfil_estais(),
            declarative_symbols.perfil_pacotes(self._packages),
        ]
        if settings.symbol_profile == "balanced":
            # E08 Hough is explicitly disabled; only the verified template result is used.
            profiles.append(
                raster_symbols.perfis_simbolos_raster(
                    templates=self._templates, configuracao=self._raster_config
                )[0]
            )
        self._profiles = tuple(profiles)
        payload = {
            "version": _VERSION,
            "profile": settings.symbol_profile,
            "methods": [profile.assinatura() for profile in self._profiles],
            "templates": [
                (item.id, item.classe, item.fonte_referencia, item.sha256)
                for item in self._templates
            ]
            if settings.symbol_profile == "balanced"
            else None,
            "legend": asdict(self._legend_config)
            if settings.symbol_profile == "balanced"
            else None,
            "calibration": repr(self._calibration),
            "calibration_version": settings.symbol_calibration_version,
            "model": self._model_identity,
            "render": asdict(self._raster_config)
            if settings.symbol_profile == "balanced"
            else None,
            "pymupdf": pymupdf.VersionBind,
            "pillow": pillow_version,
            "implementation": {
                module.__name__: _module_digest(module)
                for module in (
                    legacy_symbols,
                    pymupdf_transformers,
                    pymupdf_guys,
                    declarative_symbols,
                    raster_symbols,
                    legend_symbols,
                    symbol_reconciliation,
                )
            },
            "orchestrator_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "disabled_methods": ("raster-hough-generalizado", "structural-graph", "e11-neural"),
        }
        self.signature = sha256(
            json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()

    def run(
        self,
        document: DocumentoProjeto,
        source: ReferenciaFontePdf,
        *,
        senha: str | None = None,
        cancelado: Callable[[], bool] | None = None,
        progresso: Callable[[int, int, str], None] | None = None,
    ) -> SymbolReconciliation:
        attempt_id = uuid4()
        journal: dict[str, Any] = {
            "schema_version": 1,
            "attempt_id": str(attempt_id),
            "document_id": str(document.id),
            "source_sha256": source.sha256,
            "signature": self.signature,
            "status": "running",
            "results": [],
            "error": None,
            "cache_status": "miss",
        }
        self._write_journal(attempt_id, journal)
        try:
            if document.id != source.documento_id or document.sha256 != source.sha256:
                raise ValueError("Fonte PDF não pertence ao documento solicitado")
            if self._settings.symbol_model_path is not None:
                raise SymbolCompositionError(
                    "Modelo E11 não aprovado para operação; remova ZENY_SERVER_SYMBOL_MODEL_PATH"
                )
            if self._settings.symbol_profile == "balanced" and not self._templates:
                raise SymbolCompositionError("Nenhum template E08 verificado está disponível")
            self._check_cancelled(cancelado)
            pdf = source.caminho_canonico.expanduser().resolve(strict=True)
            _verify_source(pdf, source.sha256, source.tamanho_bytes)
            cached = self._read_cache(document)
            if cached is not None:
                self._check_cancelled(cancelado)
                _verify_source(pdf, source.sha256, source.tamanho_bytes)
                composed = reconcile_symbols(cached, self._calibration)
                if progresso is not None:
                    progresso(1000, 1000, "Símbolos: cache integral reutilizado")
                self._check_cancelled(cancelado)
                journal.update(status="cache_hit", cache_status="hit")
                self._write_journal(attempt_id, journal)
                return composed
            results: list[ResultadoMetodoSimbolos] = []
            opened = _open_document(pdf, senha)
            try:
                if opened.page_count != len(document.paginas):
                    raise ValueError("Quantidade de páginas diverge do documento importado")
                methods_per_page = len(self._profiles)
                total = opened.page_count * methods_per_page + (
                    1 if self._settings.symbol_profile == "balanced" else 0
                )
                completed = 0
                for page_index in range(opened.page_count):
                    self._check_cancelled(cancelado)
                    page = opened.load_page(page_index)
                    completed_ref = [completed]
                    tiles_ref = [0]

                    def tile_progress(
                        current: int,
                        total_tiles: int,
                        page_number: int = page_index + 1,
                        ref: list[int] = completed_ref,
                        tile_counter: list[int] = tiles_ref,
                    ) -> None:
                        tile_counter[0] = current
                        _tile_progress(progresso, ref[0], total, page_number, current, total_tiles)

                    method_started = perf_counter()
                    for result in self._observe_page(
                        page,
                        document_id=str(document.id),
                        document_sha256=document.sha256,
                        page_number=page_index + 1,
                        cancelado=cancelado,
                        progresso=tile_progress,
                    ):
                        self._record_result(
                            journal,
                            result,
                            tiles_completed=tiles_ref[0],
                            seconds=perf_counter() - method_started,
                        )
                        tiles_ref[0] = 0
                        method_started = perf_counter()
                        self._write_journal(attempt_id, journal)
                        self._require_complete(result)
                        results.append(result)
                        completed += 1
                        completed_ref[0] = completed
                        if progresso is not None:
                            progresso(
                                completed * 1000,
                                total * 1000,
                                f"Símbolos: página {page_index + 1}, {result.perfil.metodo_id}",
                            )
                    del page
                if self._settings.symbol_profile == "balanced":
                    self._check_cancelled(cancelado)
                    legend_tiles = [0]

                    def legend_progress(current: int, total_tiles: int) -> None:
                        legend_tiles[0] += 1
                        if progresso is not None:
                            progresso(
                                completed * 1000 + min(999, legend_tiles[0]),
                                total * 1000,
                                f"Símbolos: legenda, tile {current}/{total_tiles}",
                            )

                    legend_started = perf_counter()
                    legend = legend_symbols.observar_legenda_documental(
                        opened,
                        documento_id=str(document.id),
                        documento_sha256=document.sha256,
                        configuracao=self._legend_config,
                        cancelado=cancelado,
                        progresso=legend_progress,
                    )
                    self._record_result(
                        journal,
                        legend.resultado,
                        tiles_completed=legend_tiles[0],
                        seconds=perf_counter() - legend_started,
                    )
                    self._write_journal(attempt_id, journal)
                    self._require_complete(legend.resultado)
                    results.append(legend.resultado)
                    contextualized = legend_symbols.contextualizar_resultados(
                        tuple(results),
                        legend.regioes_legenda,
                        legend.pares,
                        {
                            index + 1: (
                                float(opened[index].rect.width),
                                float(opened[index].rect.height),
                            )
                            for index in range(opened.page_count)
                        },
                    )
                    id_mapping = {
                        original.id: updated.id
                        for before, after in zip(results, contextualized, strict=True)
                        for original, updated in zip(
                            before.observacoes, after.observacoes, strict=True
                        )
                    }
                    for recorded in journal["results"]:
                        for observation in recorded["observations"]:
                            observation["id"] = id_mapping.get(observation["id"], observation["id"])
                    journal["legend_contextualized"] = sum(
                        original != updated for original, updated in id_mapping.items()
                    )
                    results = list(contextualized)
                    self._write_journal(attempt_id, journal)
                    completed += 1
                    if progresso is not None:
                        progresso(completed * 1000, total * 1000, "Símbolos: legenda documental")
            finally:
                opened.close()
            self._check_cancelled(cancelado)
            _verify_source(pdf, source.sha256, source.tamanho_bytes)
            aggregated = _aggregate_by_method(results)
            composed = reconcile_symbols(aggregated, self._calibration)
            try:
                self._write_cache(document, aggregated)
                journal["cache_status"] = "stored"
            except OSError:
                journal["cache_status"] = "write_failed"
        except (FluxoMvpCanceladoError, SymbolScanCancelledError) as error:
            journal.update(status="cancelled", error=str(error))
            self._write_journal(attempt_id, journal)
            if isinstance(error, SymbolScanCancelledError):
                raise FluxoMvpCanceladoError(str(error)) from error
            raise
        except Exception as error:
            journal.update(status="failed", error=f"{type(error).__name__}: {error}")
            self._write_journal(attempt_id, journal)
            raise
        journal.update(status="completed", error=None)
        self._write_journal(attempt_id, journal)
        return composed

    def _observe_page(
        self,
        page: Any,
        *,
        document_id: str,
        document_sha256: str,
        page_number: int,
        cancelado: Callable[[], bool] | None,
        progresso: Callable[[int, int], None] | None,
    ) -> Iterator[ResultadoMetodoSimbolos]:
        for detector in (
            legacy_symbols.observar_simbolos_legados,
            pymupdf_transformers.observar_transformadores,
            pymupdf_guys.observar_estais,
        ):
            self._check_cancelled(cancelado)
            yield detector(
                page,
                documento_id=document_id,
                documento_sha256=document_sha256,
                pagina_numero=page_number,
            )
        self._check_cancelled(cancelado)
        yield declarative_symbols.observar_pacotes(
            page,
            documento_id=document_id,
            documento_sha256=document_sha256,
            pagina_numero=page_number,
            pacotes=self._packages,
        )
        if self._settings.symbol_profile == "balanced":
            self._check_cancelled(cancelado)
            template, _disabled_hough = raster_symbols.observar_simbolos_raster(
                page,
                documento_id=document_id,
                documento_sha256=document_sha256,
                pagina_numero=page_number,
                templates=self._templates,
                configuracao=self._raster_config,
                cancelado=cancelado,
                progresso=progresso,
                hough_enabled=False,
            )
            yield template

    @staticmethod
    def _check_cancelled(cancelado: Callable[[], bool] | None) -> None:
        if cancelado is not None and cancelado():
            raise FluxoMvpCanceladoError(
                "Composição de símbolos cancelada em ponto seguro; nova tentativa reprocessa o PDF"
            )

    @staticmethod
    def _require_complete(result: ResultadoMetodoSimbolos) -> None:
        for coverage in result.coberturas:
            if coverage.estado not in _COMPLETE:
                raise SymbolCompositionError(
                    f"Motor {result.perfil.metodo_id} incompleto na página "
                    f"{coverage.fonte.pagina_numero}: {coverage.estado.value}: "
                    f"{coverage.motivo or 'sem motivo'}"
                )

    @staticmethod
    def _record_result(
        journal: dict[str, Any],
        result: ResultadoMetodoSimbolos,
        *,
        tiles_completed: int,
        seconds: float,
    ) -> None:
        journal["results"].append(
            {
                "method_id": result.perfil.metodo_id,
                "method_signature": result.perfil.assinatura(),
                "tiles_completed": tiles_completed,
                "seconds": round(seconds, 6),
                "coverage": [
                    {
                        "page": item.fonte.pagina_numero,
                        "layer": item.fonte.camada,
                        "status": item.estado.value,
                        "reason": item.motivo,
                    }
                    for item in result.coberturas
                ],
                "observations": [
                    {
                        "id": item.id,
                        "page": item.fonte.pagina_numero,
                        "layer": item.fonte.camada,
                        "classes": [alternative.classe for alternative in item.alternativas],
                        "geometry": [
                            [str(point.x), str(point.y)]
                            for point in item.geometria.pontos_normalizados
                        ],
                        "raw_score": str(item.score_bruto)
                        if item.score_bruto is not None
                        else None,
                    }
                    for item in result.observacoes
                ],
            }
        )

    def _write_journal(self, attempt_id: UUID, journal: dict[str, Any]) -> None:
        self.partial_directory.mkdir(parents=True, exist_ok=True)
        target = self.partial_directory / f"{attempt_id}.json"
        with sibling_temporary_file(target) as temporary:
            temporary.write_text(
                json.dumps(journal, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(target)

    def _cache_target(self, document: DocumentoProjeto) -> Path:
        key = sha256(f"{document.id}:{document.sha256}:{self.signature}".encode()).hexdigest()
        return self.cache_directory / f"{key}.json"

    def _read_cache(self, document: DocumentoProjeto) -> tuple[ResultadoMetodoSimbolos, ...] | None:
        try:
            envelope = json.loads(self._cache_target(document).read_text(encoding="utf-8"))
            if (
                envelope.get("schema_version") != 1
                or envelope.get("source_sha256") != document.sha256
                or envelope.get("document_id") != str(document.id)
                or envelope.get("signature") != self.signature
            ):
                return None
            payload = envelope["results"]
            if sha256(payload.encode()).hexdigest() != envelope.get("results_sha256"):
                return None
            results = loads_domain(payload, tuple)
            if not all(isinstance(item, ResultadoMetodoSimbolos) for item in results):
                return None
            if not self._cache_complete(results, document):
                return None
            return results
        except (OSError, ValueError, TypeError, KeyError, DomainCodecError):
            return None

    def _cache_complete(
        self, results: tuple[ResultadoMetodoSimbolos, ...], document: DocumentoProjeto
    ) -> bool:
        expected_count = len(self._profiles) + (
            1 if self._settings.symbol_profile == "balanced" else 0
        )
        if len(results) != expected_count:
            return False
        if len({item.perfil.assinatura() for item in results}) != expected_count:
            return False
        expected_signatures = {profile.assinatura() for profile in self._profiles}
        observed_signatures = {item.perfil.assinatura() for item in results}
        if not expected_signatures <= observed_signatures:
            return False
        if self._settings.symbol_profile == "balanced":
            legends = [item for item in results if item.perfil.metodo_id == "document-local-legend"]
            if len(legends) != 1:
                return False
            legend = legends[0]
            if legend.perfil.perfil_referencia != f"documento:{document.id}:{document.sha256}":
                return False
            parameters = dict(legend.perfil.parametros)
            expected_legend = asdict(self._legend_config)
            if any(
                parameters.get(key) != (Decimal(str(value)) if isinstance(value, float) else value)
                for key, value in expected_legend.items()
            ):
                return False
        pages = set(range(1, len(document.paginas) + 1))
        for result in results:
            if any(coverage.estado not in _COMPLETE for coverage in result.coberturas):
                return False
            if len(result.coberturas) != len(pages):
                return False
            if {coverage.fonte.pagina_numero for coverage in result.coberturas} != pages:
                return False
            if any(
                coverage.fonte.documento_id != str(document.id)
                or coverage.fonte.documento_sha256 != document.sha256
                for coverage in result.coberturas
            ):
                return False
            if any(
                observation.fonte.documento_id != str(document.id)
                or observation.fonte.documento_sha256 != document.sha256
                or observation.fonte.pagina_numero not in pages
                for observation in result.observacoes
            ):
                return False
        return True

    def _write_cache(
        self, document: DocumentoProjeto, results: tuple[ResultadoMetodoSimbolos, ...]
    ) -> None:
        if not self._cache_complete(results, document):
            raise SymbolCompositionError("Cobertura incompleta não pode entrar no cache integral")
        payload = dumps_domain(results)
        envelope = {
            "schema_version": 1,
            "document_id": str(document.id),
            "source_sha256": document.sha256,
            "signature": self.signature,
            "results_sha256": sha256(payload.encode()).hexdigest(),
            "results": payload,
        }
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        target = self._cache_target(document)
        with sibling_temporary_file(target) as temporary:
            temporary.write_text(
                json.dumps(envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(target)


def _model_identity(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    identity = {"path": str(path), "status": "missing"}
    if path.is_file():
        digest = sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        identity.update({"status": "present", "sha256": digest.hexdigest()})
    return identity


def _module_digest(module: Any) -> str:
    path = Path(module.__file__)
    return sha256(path.read_bytes()).hexdigest()


def _aggregate_by_method(
    results: list[ResultadoMetodoSimbolos],
) -> tuple[ResultadoMetodoSimbolos, ...]:
    grouped: dict[str, list[ResultadoMetodoSimbolos]] = {}
    for result in results:
        grouped.setdefault(result.perfil.assinatura(), []).append(result)
    return tuple(
        ResultadoMetodoSimbolos(
            perfil=items[0].perfil,
            coberturas=tuple(coverage for item in items for coverage in item.coberturas),
            observacoes=tuple(observation for item in items for observation in item.observacoes),
        )
        for items in grouped.values()
    )


def _tile_progress(
    progress: Callable[[int, int, str], None] | None,
    completed: int,
    total: int,
    page_number: int,
    current: int,
    total_tiles: int,
) -> None:
    if progress is not None:
        progress(
            completed * 1000 + min(999, current * 1000 // max(1, total_tiles)),
            total * 1000,
            f"Símbolos: página {page_number}, tile {current}/{total_tiles}",
        )
