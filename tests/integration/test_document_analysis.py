from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Never
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from tests.factories import complete_project
from tests.pdf_fixtures import create_analysis_pdf

from zeny_project_handler.adapters.analysis import JsonAnalysisCache, PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.document_analysis import ExecutarAnaliseDocumento
from zeny_project_handler.application.errors import (
    AnaliseDocumentoError,
    DocumentoNaoEncontradoError,
    OrigemPdfNaoEncontradaError,
    ProjetoNaoEncontradoError,
)
from zeny_project_handler.application.pdf_import import ImportarPdfNoProjeto
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise, TipoEvidencia
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.ports.analysis import SolicitacaoAnaliseDocumento

pytestmark = pytest.mark.integration


class FailingAnalyzer:
    nome = "falha-controlada"
    versao = "1"
    assinatura_capacidade = "falha-controlada-capacidade-v1"

    def analisar(self, _request: SolicitacaoAnaliseDocumento) -> Never:
        raise RuntimeError("decodificador indisponível")


@pytest.fixture
def analysis_project(
    tmp_path: Path, catalogo_inicial: CatalogoTecnico
) -> Iterator[tuple[Engine, Projeto]]:
    engine = create_sqlite_engine(tmp_path / "analysis.sqlite3")
    upgrade_database(engine)
    project = complete_project(catalogo_inicial)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.commit()
    try:
        yield engine, project
    finally:
        engine.dispose()


def test_analysis_use_case_persists_evidence_and_reuses_derived_cache(
    tmp_path: Path, analysis_project: tuple[Engine, Projeto]
) -> None:
    engine, original = analysis_project
    source = create_analysis_pdf(tmp_path / "network-project.pdf")
    imported = ImportarPdfNoProjeto(PyMuPdfReader(), lambda: SqlAlchemyUnitOfWork(engine)).executar(
        original.id, source
    )
    document = imported.inspecao.documento
    use_case = ExecutarAnaliseDocumento(
        PyMuPdfDocumentAnalyzer(cache=JsonAnalysisCache(tmp_path / "analysis-cache")),
        lambda: SqlAlchemyUnitOfWork(engine),
    )

    first = use_case.executar(original.id, document.id)
    second = use_case.executar(original.id, document.id)

    assert first.execucao.estado is EstadoExecucaoAnalise.CONCLUIDA
    assert first.evidencias
    assert not first.cache_utilizado
    assert second.cache_utilizado
    assert (
        dict(first.execucao.parametros)["assinatura_capacidade_analisador"]
        == use_case.assinatura_analisador
    )
    assert all(
        dict(item.parametros)["assinatura_capacidade_analisador"] == use_case.assinatura_analisador
        for item in first.evidencias
    )
    assert {item.tipo for item in first.evidencias} >= {
        TipoEvidencia.TEXTO,
        TipoEvidencia.VETOR,
        TipoEvidencia.IMAGEM,
    }
    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.execucoes_analise.obter(first.execucao.id) == first.execucao
        assert work.evidencias.listar_da_execucao(first.execucao.id) == first.evidencias
        assert len(work.execucoes_analise.listar_do_projeto(original.id)) == 2


def test_fatal_analysis_failure_is_persisted_and_context_errors_are_specific(
    tmp_path: Path,
    analysis_project: tuple[Engine, Projeto],
    app_log_capture: pytest.LogCaptureFixture,
) -> None:
    engine, original = analysis_project
    source = create_analysis_pdf(tmp_path / "failure.pdf")
    imported = ImportarPdfNoProjeto(PyMuPdfReader(), lambda: SqlAlchemyUnitOfWork(engine)).executar(
        original.id, source
    )
    use_case = ExecutarAnaliseDocumento(
        FailingAnalyzer(),
        lambda: SqlAlchemyUnitOfWork(engine),
    )

    with pytest.raises(AnaliseDocumentoError, match="registrada"):
        use_case.executar(original.id, imported.inspecao.documento.id)
    with SqlAlchemyUnitOfWork(engine) as work:
        execution = work.execucoes_analise.listar_do_projeto(original.id)[0]
    assert execution.estado is EstadoExecucaoAnalise.FALHOU
    assert execution.erro == "decodificador indisponível"

    with pytest.raises(OrigemPdfNaoEncontradaError):
        use_case.executar(original.id, original.documentos[0].id)
    with pytest.raises(DocumentoNaoEncontradoError):
        use_case.executar(original.id, uuid4())
    with pytest.raises(ProjetoNaoEncontradoError):
        use_case.executar(uuid4(), imported.inspecao.documento.id)

    analysis_failures = [
        record
        for record in app_log_capture.records
        if getattr(record, "operation", None) == "pdf.analysis"
        and getattr(record, "status", None) == "failed"
    ]
    unexpected = next(
        record
        for record in analysis_failures
        if getattr(record, "error_code", None) == "RuntimeError"
    )
    assert unexpected.levelno == logging.ERROR
    assert unexpected.exc_info is not None
    expected = [record for record in analysis_failures if record is not unexpected]
    assert expected
    assert all(record.levelno == logging.WARNING for record in expected)
    assert all(record.exc_info is None for record in expected)
    assert all(getattr(record, "correlation_id", None) for record in analysis_failures)
    assert all(getattr(record, "execution_id", None) for record in analysis_failures)
