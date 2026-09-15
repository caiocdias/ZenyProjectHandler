"""Benchmark local opt-in; relatórios contêm dados privados e devem ficar em tmp/."""

from __future__ import annotations

import argparse
import json
import platform
from collections import Counter
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer, TesseractCliOcr
from zeny_project_handler.adapters.analysis.tesseract_runtime import inspect_tesseract_runtime
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.interpretation.category_analyzers import (
    AnalisadorCabo,
    AnalisadorEquipamento,
    AnalisadorEstruturaBt,
    AnalisadorEstruturaMt,
    AnalisadorPoste,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.analysis_regions import agrupar_regioes_da_analise
from zeny_project_handler.application.document_analysis import ExecutarAnaliseDocumento
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.application.interpretation_pipeline import ExecutarPipelineInterpretacao
from zeny_project_handler.application.spans import detectar_vaos
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.interpretation import RegraReconhecimento
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.analysis import (
    ConfiguracaoAnaliseDocumento,
    MotorOcrPort,
    PaginaRasterOcr,
    TrechoTextoOcr,
)
from zeny_project_handler.ports.interpretation import (
    AnalisadorCategoriaPort,
    SolicitacaoInterpretacao,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf


def json_value(value: Any) -> Any:
    """Serialize snapshots completos, sem descartar geometria ou proveniência."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, UUID | Path | Decimal | datetime):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Tipo não serializável: {type(value).__name__}")


def verify_ocr(engine: MotorOcrPort) -> None:
    """Exija reconhecimento funcional; --list-langs sozinho não valida a saída TSV."""
    picture = Image.new("RGB", (650, 100), "white")
    ImageDraw.Draw(picture).text(
        (20, 20), "TESTE 12345", fill="black", font=ImageFont.load_default(size=48)
    )
    result = engine.reconhecer(
        PaginaRasterOcr(
            pagina_numero=1,
            largura_pixels=650,
            altura_pixels=100,
            stride=1950,
            dados_rgb=picture.tobytes(),
            dpi=300,
        )
    )
    if not any("12345" in item.texto for item in result):
        raise RuntimeError("OCR não passou o controle sintético; verifique configs/tsv e stderr")


class TimedTesseract(TesseractCliOcr):
    """Instrumentação opt-in no ponto comum aos cinco métodos, sem mudar capacidade."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.calls: list[dict[str, Any]] = []

    def _recognize(
        self,
        pagina: PaginaRasterOcr,
        *,
        page_segmentation_mode: int,
        character_whitelist: str | None = None,
        technical_glyphs: bool = False,
    ) -> tuple[TrechoTextoOcr, ...]:
        started = perf_counter()
        call: dict[str, Any] = {
            "page": pagina.pagina_numero,
            "width": pagina.largura_pixels,
            "height": pagina.altura_pixels,
            "dpi": pagina.dpi,
            "psm": page_segmentation_mode,
            "whitelist": character_whitelist,
            "technical_glyphs": technical_glyphs,
            "completed": False,
        }
        try:
            result = super()._recognize(
                pagina,
                page_segmentation_mode=page_segmentation_mode,
                character_whitelist=character_whitelist,
                technical_glyphs=technical_glyphs,
            )
            call.update(completed=True, segments=len(result))
            return result
        finally:
            call["seconds"] = perf_counter() - started
            self.calls.append(call)


def profile_annotations(source: Path) -> list[dict[str, Any]]:
    """Meça renderização separada a 150 DPI, abrindo a fonte a cada modo; sem OCR."""
    measurements = []
    for enabled in (False, True):
        with pymupdf.open(source) as document:  # type: ignore[no-untyped-call]
            for page in document:
                started = perf_counter()
                pixmap = page.get_pixmap(dpi=150, annots=enabled)
                seconds = perf_counter() - started
                measurements.append(
                    {
                        "page": page.number + 1,
                        "annotations": enabled,
                        "dpi": 150,
                        "seconds": seconds,
                        "raster_bytes": len(pixmap.samples),
                        "raster_sha256": sha256(pixmap.samples).hexdigest(),
                        "annotation_count": len(tuple(page.annots() or ())),
                    }
                )
    return measurements


@dataclass
class CategoryRecorder:
    """Observe a saída real dos analisadores antes do filtro de identificadores."""

    delegate: AnalisadorCategoriaPort
    proposals: list[PropostaElemento] = field(default_factory=list)
    categoria: CategoriaElemento = field(init=False)
    nome: str = field(init=False)
    versao: str = field(init=False)

    def __post_init__(self) -> None:
        self.categoria = self.delegate.categoria
        self.nome = self.delegate.nome
        self.versao = self.delegate.versao

    def analisar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        regra: RegraReconhecimento,
    ) -> tuple[PropostaElemento, ...]:
        result = self.delegate.analisar(solicitacao, regra)
        self.proposals.extend(result)
        return result


def run_variant(
    source: Path,
    directory: Path,
    *,
    ocr: MotorOcrPort | None,
    telemetry: bool = False,
    complementary: bool = False,
) -> dict[str, Any]:
    """Use uma base nova por variante, sem cache nem consulta de conformidade/SQL."""
    started = perf_counter()
    inspection = PyMuPdfReader().inspecionar(source)
    identity = uuid5(NAMESPACE_URL, f"benchmark:{inspection.documento.sha256}")
    document = replace(
        inspection.documento,
        id=uuid5(identity, "document"),
        paginas=tuple(
            replace(page, id=uuid5(identity, f"page:{page.numero}"))
            for page in inspection.documento.paginas
        ),
    )
    inspection = replace(inspection, documento=document)
    catalog = carregar_catalogo_inicial()
    registry = carregar_registro_regras_inicial()
    project = Projeto(
        id=identity,
        nome="Benchmark local",
        catalogo_versao_id=catalog.id,
        criado_em=datetime.now(UTC),
        documentos=(inspection.documento,),
    )
    engine = create_sqlite_engine(directory / "benchmark.sqlite3")
    try:
        upgrade_database(engine)

        def work() -> SqlAlchemyUnitOfWork:
            return SqlAlchemyUnitOfWork(engine)

        with work() as unit:
            unit.catalogos.salvar(catalog)
            unit.projetos.salvar(project)
            unit.fontes_pdf.salvar(
                ReferenciaFontePdf(
                    documento_id=inspection.documento.id,
                    projeto_id=project.id,
                    caminho_canonico=source,
                    sha256=inspection.documento.sha256,
                    tamanho_bytes=inspection.tamanho_bytes,
                    modificado_em_ns=inspection.modificado_em_ns,
                )
            )
            unit.commit()
        configuration = ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=ocr is not None)
        from zeny_project_handler.adapters.analysis.rapid_evidence import RapidEvidenceExtractor

        analyzer = PyMuPdfDocumentAnalyzer(
            motor_ocr=ocr, complementar=RapidEvidenceExtractor() if complementary else None
        )
        extraction_started = perf_counter()
        extraction = ExecutarAnaliseDocumento(analyzer, work).executar(
            project.id,
            inspection.documento.id,
            configuracao=configuration,
            execucao_id=uuid5(identity, "ocr" if ocr is not None else "native"),
        )
        extraction_seconds = perf_counter() - extraction_started
        recorders = tuple(
            CategoryRecorder(item)
            for item in (
                AnalisadorPoste(),
                AnalisadorEstruturaMt(),
                AnalisadorEstruturaBt(),
                AnalisadorCabo(),
                AnalisadorEquipamento(),
            )
        )
        interpreter = InterpretadorRegrasExplicitas(registry, analisadores=recorders)
        interpretation_started = perf_counter()
        semantic = ExecutarPipelineInterpretacao(interpreter, registry, work).executar(
            project.id,
            extraction.execucao.id,
        )
        interpretation_seconds = perf_counter() - interpretation_started
        projection_started = perf_counter()
        with work() as unit:
            promoted = unit.projetos.obter(project.id)
            assert promoted is not None
            decisions = tuple(
                unit.decisoes_revisao.obter_da_proposta(item.id) for item in semantic.elementos
            ) + tuple(
                unit.decisoes_revisao.obter_da_proposta(relation.id)
                for relation in semantic.relacoes
            )
        regions = agrupar_regioes_da_analise(
            (*semantic.elementos, *semantic.relacoes),
            extraction.evidencias,
            project.documentos,
        )
        spans = detectar_vaos(promoted)
        projection_seconds = perf_counter() - projection_started
        semantic_total = perf_counter() - started
        export_started = perf_counter()
        # Mesma sessão e projeções usadas pelo servidor, sem SQL operacional nem HTTP.
        from xml.etree import ElementTree
        from zipfile import ZipFile

        from zeny_project_handler_server.deliverable_exports import _results_sheets
        from zeny_project_handler_server.review_api import _session_dto
        from zeny_project_handler_server.xlsx_export import write_xlsx

        session = ServicoRevisaoHumana(work).carregar_sessao_semantica(project.id)
        dto = _session_dto(session, project_version=1)
        sheets = tuple(_results_sheets(dto))
        documentation: dict[str, Any] = {}
        if telemetry:
            # Apenas os insumos documentais puros, sem assumir mercado nem executar SQL.
            from zeny_project_handler.application.project_compliance import (
                _document_compliance_inputs,
                _metadata_values,
                _targets,
                detectar_notas_servico_cabecalho,
            )
            from zeny_project_handler.domain.compliance import TipoEscopoConformidade
            from zeny_project_handler_server.compliance_api import _documentation_response
            from zeny_project_handler_server.deliverable_exports import _documentation_sheet

            targets = {
                item.referencia_id: item
                for item in _targets(session)
                if item.tipo is TipoEscopoConformidade.DOCUMENTO and item.referencia_id is not None
            }
            _, document_items, _ = _document_compliance_inputs(
                session,
                targets,
                detectar_notas_servico_cabecalho(session),
                _metadata_values(session),
            )
            document_dto = _documentation_response(session, dto.semantic_signature, document_items)
            documentation = {
                "items": document_items,
                "dto": document_dto.model_dump(mode="json"),
                "scope": "document inputs only; no compliance execution or SQL",
            }
            sheets = (*sheets, _documentation_sheet(document_dto))
        exported = write_xlsx(directory / "results.xlsx", sheets)
        with ZipFile(exported) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Exportação XLSX inválida")
            for index, sheet in enumerate(sheets, start=1):
                root = ElementTree.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
                rows = root.findall("{*}sheetData/{*}row")
                actual_rows = tuple(
                    tuple(
                        cell.findtext("{*}is/{*}t") or cell.findtext("{*}v") or ""
                        for cell in row.findall("{*}c")
                    )
                    for row in rows
                )
                expected_rows = tuple(
                    tuple(str(value) if value is not None else "" for value in row)
                    for row in (sheet.headers, *sheet.rows)
                )
                if actual_rows != expected_rows:
                    raise RuntimeError("Exportação diverge da sessão de Resultados")
        results_export_seconds = perf_counter() - export_started
        raw = tuple(item for recorder in recorders for item in recorder.proposals)
        return {
            "configuration": configuration,
            "analyzer": {"version": analyzer.versao, "signature": analyzer.assinatura_capacidade},
            "interpreter_version": interpreter.versao,
            "registry_signature": registry.assinatura(),
            "seconds": {
                "extraction_persistence": extraction_seconds,
                "interpretation_promotion_persistence": interpretation_seconds,
                "regions_spans": projection_seconds,
                "total": semantic_total,
                "results_export": results_export_seconds,
                "including_results_export": perf_counter() - started,
            },
            "counts": {
                "evidence": len(extraction.evidencias),
                "evidence_types": dict(Counter(e.tipo.value for e in extraction.evidencias)),
                "raw_proposals": len(raw),
                "proposals": len(semantic.elementos),
                "relations": len(semantic.relacoes),
                "confirmed": len(promoted.elementos),
                "regions": len(regions),
                "spans": len(spans),
                "diagnostics": len(extraction.execucao.diagnosticos)
                + len(semantic.execucao.diagnosticos),
            },
            "extraction": extraction,
            "raw_proposals": raw,
            "semantic": semantic,
            "project": promoted,
            "decisions": decisions,
            "regions": regions,
            "spans": spans,
            "results": dto.model_dump(mode="json"),
            **({"documentation": documentation} if telemetry else {}),
            "export": {
                "sheets": sheets,
                "bytes": exported.stat().st_size,
                "sha256": sha256(exported.read_bytes()).hexdigest(),
                "verified": True,
            },
        }
    finally:
        engine.dispose()


def benchmark(
    source: Path,
    output: Path,
    runtime_directory: Path,
    *,
    native_only: bool = False,
    telemetry: bool = False,
    complementary: bool = False,
) -> dict[str, Any]:
    source = source.resolve(strict=True)
    if output.resolve() == source:
        raise ValueError("Relatório não pode substituir a origem")
    before = (
        source.stat().st_size,
        source.stat().st_mtime_ns,
        sha256(source.read_bytes()).hexdigest(),
    )
    runtime = inspect_tesseract_runtime(runtime_directory) if not native_only else None
    if runtime is not None and not runtime.portugues_pronto:
        raise RuntimeError(f"OCR português obrigatório: {runtime.diagnostico}")
    ocr = None
    if runtime is not None:
        assert runtime.executavel is not None and runtime.diretorio_tessdata is not None
        ocr_class = TimedTesseract if telemetry else TesseractCliOcr
        ocr = ocr_class(
            runtime.executavel,
            language="+".join(runtime.idiomas_selecionados),
            tessdata_directory=runtime.diretorio_tessdata,
        )
        verify_ocr(ocr)
    report: dict[str, Any] = {
        "schema": 1,
        "source_sha256": before[2],
        "source_bytes": before[0],
        "source_mtime_ns": before[1],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pymupdf": pymupdf.VersionBind,
        "runtime": runtime,
        "ocr_capability": ocr.consultar_capacidade() if ocr is not None else None,
        "native_only": native_only,
        "complementary": complementary,
    }
    if telemetry:
        report["annotation_rendering"] = profile_annotations(source)
        if isinstance(ocr, TimedTesseract):
            report["ocr_control_calls"] = list(ocr.calls)
            ocr.calls.clear()
    output.parent.mkdir(parents=True, exist_ok=True)
    for name, motor in (("native", None), ("ocr", ocr)):
        if name == "ocr" and native_only:
            continue
        print(f"Iniciando {name}", flush=True)
        with TemporaryDirectory(prefix=f"benchmark-{name}-", dir=output.parent) as temporary:
            report[name] = run_variant(
                source,
                Path(temporary),
                ocr=motor,
                telemetry=telemetry,
                complementary=complementary and (name == "ocr" or native_only),
            )
        if isinstance(motor, TimedTesseract):
            report[name]["ocr_calls"] = list(motor.calls)
        output.write_text(
            json.dumps(report, default=json_value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps({name: report[name]["counts"], "seconds": report[name]["seconds"]}),
            flush=True,
        )
    after = (
        source.stat().st_size,
        source.stat().st_mtime_ns,
        sha256(source.read_bytes()).hexdigest(),
    )
    if before != after:
        raise RuntimeError("Origem mudou durante o benchmark")
    report["source_unchanged"] = True
    output.write_text(
        json.dumps(report, default=json_value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-directory", type=Path, default=Path("tmp/benchmark-runtime"))
    parser.add_argument("--native-only", action="store_true")
    parser.add_argument("--telemetry", action="store_true")
    parser.add_argument("--complementary-ocr", action="store_true")
    options = parser.parse_args(arguments)
    benchmark(
        options.source,
        options.output,
        options.runtime_directory,
        native_only=options.native_only,
        telemetry=options.telemetry,
        complementary=options.complementary_ocr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
