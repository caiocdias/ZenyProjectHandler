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


def run_variant(source: Path, directory: Path, *, ocr: MotorOcrPort | None) -> dict[str, Any]:
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
        analyzer = PyMuPdfDocumentAnalyzer(motor_ocr=ocr)
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
                "total": perf_counter() - started,
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
        }
    finally:
        engine.dispose()


def benchmark(
    source: Path, output: Path, runtime_directory: Path, *, native_only: bool = False
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
        ocr = TesseractCliOcr(
            runtime.executavel,
            language="+".join(runtime.idiomas_selecionados),
            tessdata_directory=runtime.diretorio_tessdata,
        )
        verify_ocr(ocr)
    report: dict[str, Any] = {
        "schema": 1,
        "source_sha256": before[2],
        "source_bytes": before[0],
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pymupdf": pymupdf.VersionBind,
        "runtime": runtime,
        "ocr_capability": ocr.consultar_capacidade() if ocr is not None else None,
        "native_only": native_only,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    for name, motor in (("native", None), ("ocr", ocr)):
        if name == "ocr" and native_only:
            continue
        print(f"Iniciando {name}", flush=True)
        with TemporaryDirectory(prefix=f"benchmark-{name}-", dir=output.parent) as temporary:
            report[name] = run_variant(source, Path(temporary), ocr=motor)
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
    options = parser.parse_args(arguments)
    benchmark(
        options.source, options.output, options.runtime_directory, native_only=options.native_only
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
