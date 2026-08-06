from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine
from tests.pdf_fixtures import create_catalog_pdf, create_feature_pdf, create_golden_pdf

from zeny_project_handler.adapters.analysis import JsonAnalysisCache, PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.pdf import PdfArquivoInvalidoError, PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.document_analysis import ExecutarAnaliseDocumento
from zeny_project_handler.application.errors import FluxoMvpCanceladoError
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.application.interpretation_pipeline import ExecutarPipelineInterpretacao
from zeny_project_handler.application.managed_files import GerenciadorArquivosGerenciados
from zeny_project_handler.application.mvp_workflow import ServicoFluxoMvp
from zeny_project_handler.application.operation_coordinator import (
    CoordenadorOperacoes,
    TipoOperacao,
)
from zeny_project_handler.application.pdf_import import ImportarPdfsNoProjeto
from zeny_project_handler.domain.analysis import DecisaoRevisao, PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, SituacaoProjeto
from zeny_project_handler.domain.project import FotoElemento, Poste, Projeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

pytestmark = pytest.mark.integration


def _service(
    engine: Engine,
    catalog: CatalogoTecnico,
    cache_directory: Path,
    coordinator: CoordenadorOperacoes | None = None,
) -> ServicoFluxoMvp:
    reader = PyMuPdfReader()

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    registry = carregar_registro_regras_inicial()

    def list_projects() -> tuple[Projeto, ...]:
        with unit_of_work() as work:
            return work.projetos.listar()

    return ServicoFluxoMvp(
        unit_of_work,
        catalogo_inicial_id=catalog.id,
        importador=ImportarPdfsNoProjeto(
            reader,
            unit_of_work,
            coordenador=coordinator,
        ),
        extrator=ExecutarAnaliseDocumento(
            PyMuPdfDocumentAnalyzer(cache=JsonAnalysisCache(cache_directory)),
            unit_of_work,
        ),
        interpretador=ExecutarPipelineInterpretacao(
            InterpretadorRegrasExplicitas(registry),
            registry,
            unit_of_work,
        ),
        gerenciador_arquivos=GerenciadorArquivosGerenciados(
            cache_directory.parent,
            list_projects,
        ),
        coordenador=coordinator,
    )


@pytest.fixture
def workflow(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> Iterator[tuple[Engine, ServicoFluxoMvp]]:
    engine = create_sqlite_engine(tmp_path / "mvp.sqlite3")
    upgrade_database(engine)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.commit()
    try:
        yield engine, _service(engine, catalogo_inicial, tmp_path / "cache")
    finally:
        engine.dispose()


def _first_automatic_decision(
    engine: Engine,
    project_id: UUID,
) -> DecisaoRevisao:
    with SqlAlchemyUnitOfWork(engine) as work:
        proposals = tuple(
            proposal
            for run in work.execucoes_analise.listar_do_projeto(project_id)
            for proposal in work.propostas.listar_da_execucao(run.id)
            if isinstance(proposal, PropostaElemento)
        )
        assert proposals
        decision = work.decisoes_revisao.obter_da_proposta(proposals[0].id)
    assert decision is not None
    return decision


def test_multiple_pdf_import_is_atomic_and_preserves_order(
    workflow: tuple[Engine, ServicoFluxoMvp],
    tmp_path: Path,
) -> None:
    engine, service = workflow
    project = service.criar_projeto("Projeto com folhas")
    first = create_feature_pdf(tmp_path / "folha-01.pdf")
    second = create_golden_pdf(tmp_path / "folha-02.pdf")
    corrupt = tmp_path / "corrompido.pdf"
    corrupt.write_bytes(b"%PDF invalid")

    with pytest.raises(PdfArquivoInvalidoError):
        service.importar_pdfs(project.projeto.id, (first, corrupt))
    assert service.abrir_projeto(project.projeto.id).projeto.documentos == ()

    service.importar_pdfs(project.projeto.id, (first, second))
    reopened = service.abrir_projeto(project.projeto.id)

    assert [document.nome_arquivo for document in reopened.projeto.documentos] == [
        "folha-01.pdf",
        "folha-02.pdf",
    ]
    assert [source.caminho_canonico for source in reopened.fontes_pdf] == [
        first.resolve(),
        second.resolve(),
    ]
    engine.dispose()


def test_project_page_order_can_interleave_pdfs_and_is_persisted(
    workflow: tuple[Engine, ServicoFluxoMvp],
    tmp_path: Path,
) -> None:
    engine, service = workflow
    created = service.criar_projeto("Projeto reordenável")
    first = create_feature_pdf(tmp_path / "primeira.pdf")
    second = create_golden_pdf(tmp_path / "segunda.pdf")
    service.importar_pdfs(created.projeto.id, (first, second))
    session = service.abrir_projeto(created.projeto.id)
    first_document, second_document = session.projeto.documentos
    first_page, second_page, third_page, fourth_page = session.projeto.ordem_leitura_paginas

    reordered = service.reordenar_paginas(
        created.projeto.id,
        (fourth_page, first_page, third_page, second_page),
    )
    reopened = service.abrir_projeto(created.projeto.id)

    assert reordered.projeto.documentos == (first_document, second_document)
    assert reopened.projeto.ordem_leitura_paginas == (
        fourth_page,
        first_page,
        third_page,
        second_page,
    )
    assert [source.caminho_canonico for source in reopened.fontes_pdf] == [
        first.resolve(),
        second.resolve(),
    ]
    engine.dispose()


def test_cancel_and_resume_pipeline_reuses_completed_work_without_duplicates(
    workflow: tuple[Engine, ServicoFluxoMvp],
    tmp_path: Path,
) -> None:
    engine, service = workflow
    project = service.criar_projeto("Projeto retomável")
    first = create_feature_pdf(tmp_path / "primeira.pdf")
    second = create_golden_pdf(tmp_path / "segunda.pdf")
    service.importar_pdfs(project.projeto.id, (first, second))
    cancellation = Event()

    def progress(current: int, _total: int, _message: str) -> None:
        if current == 2:
            cancellation.set()

    with pytest.raises(FluxoMvpCanceladoError, match="Retomar"):
        service.executar_pipeline(
            project.projeto.id,
            progresso=progress,
            cancelado=cancellation.is_set,
        )

    resumed = service.executar_pipeline(project.projeto.id)
    repeated = service.executar_pipeline(project.projeto.id)

    assert resumed.execucoes_interpretacao == repeated.execucoes_interpretacao
    assert resumed.documentos_processados == 2
    with SqlAlchemyUnitOfWork(engine) as work:
        runs = work.execucoes_analise.listar_do_projeto(project.projeto.id)
        assert len(runs) == 4
        assert len({run.id for run in runs}) == 4
    summary = service.abrir_projeto(project.projeto.id).resumo
    assert summary.documentos == 2
    assert summary.paginas == 4
    engine.dispose()


def test_cancelled_analysis_releases_shared_coordinator(
    workflow: tuple[Engine, ServicoFluxoMvp],
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, _default_service = workflow
    coordinator = CoordenadorOperacoes()
    service = _service(
        engine,
        catalogo_inicial,
        tmp_path / "coordinated-cache",
        coordinator,
    )
    project = service.criar_projeto("Projeto cancelado coordenado")
    source = create_golden_pdf(tmp_path / "cancelado.pdf")
    service.importar_pdfs(project.projeto.id, (source,))

    with pytest.raises(FluxoMvpCanceladoError):
        service.executar_pipeline(project.projeto.id, cancelado=lambda: True)

    assert coordinator.operacao_em_andamento is None
    with coordinator.adquirir(TipoOperacao.BACKUP):
        assert coordinator.operacao_em_andamento is TipoOperacao.BACKUP


def test_review_session_consolidates_latest_results_from_every_pdf(
    workflow: tuple[Engine, ServicoFluxoMvp],
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, service = workflow
    created = service.criar_projeto("Projeto consolidado")
    code = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].codigo
    first = create_catalog_pdf(tmp_path / "primeiro.pdf", code)
    second = create_catalog_pdf(tmp_path / "segundo.pdf", code)
    service.importar_pdfs(created.projeto.id, (first, second))
    project = service.abrir_projeto(created.projeto.id).projeto
    first_page, second_page = project.ordem_leitura_paginas
    service.reordenar_paginas(created.projeto.id, (second_page, first_page))
    service.executar_pipeline(created.projeto.id)

    review = ServicoRevisaoHumana(lambda: SqlAlchemyUnitOfWork(engine))
    session = review.carregar_sessao(created.projeto.id)

    assert len(session.execucoes) == 2
    proposal_page_ids = {
        item.geometria.pagina_id for item in session.propostas if isinstance(item, PropostaElemento)
    }
    assert proposal_page_ids == {
        first_page,
        second_page,
    }
    region_page_order = tuple(dict.fromkeys(region.pagina_id for region in session.regioes))
    assert region_page_order == (second_page, first_page)
    engine.dispose()


def test_remove_pdf_prunes_only_dependent_data_and_project_can_be_deleted(
    workflow: tuple[Engine, ServicoFluxoMvp],
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, service = workflow
    created = service.criar_projeto("Projeto removível")
    catalog_code = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].codigo
    first = create_catalog_pdf(tmp_path / "remover.pdf", catalog_code)
    second = create_golden_pdf(tmp_path / "preservar.pdf")
    service.importar_pdfs(created.projeto.id, (first, second))
    session = service.abrir_projeto(created.projeto.id)
    first_document, second_document = session.projeto.documentos
    photo_payload = b"managed-document-photo"
    photo_digest = sha256(photo_payload).hexdigest()
    photo = FotoElemento(
        id=uuid4(),
        caminho_relativo=f"photos/{photo_digest}.png",
        sha256=photo_digest,
        tipo_mime="image/png",
        tamanho_bytes=len(photo_payload),
    )
    pole = Poste(
        id=uuid4(),
        tipo_catalogo_id=catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].id,
        situacao=SituacaoProjeto.EXISTENTE,
        geometria=GeometriaDocumento.ponto(
            first_document.paginas[0].id,
            PontoNormalizado(Decimal("0.2"), Decimal("0.3")),
        ),
        fotos=(photo,),
    )
    managed_photo = tmp_path / "project-files" / str(created.projeto.id) / photo.caminho_relativo
    managed_photo.parent.mkdir(parents=True)
    managed_photo.write_bytes(photo_payload)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.projetos.salvar(replace(session.projeto, elementos=(pole,)))
        work.commit()
    service.executar_pipeline(created.projeto.id)
    decision = _first_automatic_decision(engine, created.projeto.id)

    result = service.remover_documentos(created.projeto.id, (first_document.id,))

    assert result.documentos_removidos == ("remover.pdf",)
    assert result.elementos_removidos == 2
    assert result.arquivos_gerenciados_removidos == 1
    assert not result.limpeza_pendente
    assert not managed_photo.exists()
    assert result.sessao.projeto.documentos == (second_document,)
    assert result.sessao.projeto.elementos == ()
    assert [source.caminho_canonico for source in result.sessao.fontes_pdf] == [second.resolve()]
    with SqlAlchemyUnitOfWork(engine) as work:
        remaining_runs = work.execucoes_analise.listar_do_projeto(created.projeto.id)
        removed_decision = work.decisoes_revisao.obter(decision.id)
    assert len(remaining_runs) == 2
    assert removed_decision is None

    assert service.excluir_projeto(created.projeto.id)
    assert all(item.projeto_id != created.projeto.id for item in service.listar_projetos())
    assert first.is_file() and second.is_file()
    engine.dispose()


def test_delete_project_with_confirmed_review_removes_dependents_in_safe_order(
    workflow: tuple[Engine, ServicoFluxoMvp],
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, service = workflow
    created = service.criar_projeto("Projeto com aceite")
    catalog_code = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].codigo
    source = create_catalog_pdf(tmp_path / "projeto-revisado.pdf", catalog_code)
    service.importar_pdfs(created.projeto.id, (source,))
    service.executar_pipeline(created.projeto.id)
    decision = _first_automatic_decision(engine, created.projeto.id)

    managed_root = tmp_path / "project-files" / str(created.projeto.id)
    managed_root.mkdir(parents=True)
    (managed_root / "local-copy.bin").write_bytes(b"managed")

    result = service.excluir_projeto(created.projeto.id)

    assert result
    assert result.arquivos_gerenciados_removidos == 1
    assert not result.limpeza_pendente
    assert not managed_root.exists()
    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.projetos.obter(created.projeto.id) is None
        assert work.execucoes_analise.listar_do_projeto(created.projeto.id) == ()
        assert work.decisoes_revisao.obter(decision.id) is None
    assert source.is_file()
    engine.dispose()


def test_delete_project_restores_tombstone_when_database_commit_rolls_back(
    workflow: tuple[Engine, ServicoFluxoMvp],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, service = workflow
    created = service.criar_projeto("Projeto com rollback")
    managed_root = tmp_path / "project-files" / str(created.projeto.id)
    managed_root.mkdir(parents=True)
    managed_file = managed_root / "rollback.bin"
    managed_file.write_bytes(b"restore-me")
    original_commit = SqlAlchemyUnitOfWork.commit

    def fail_commit(_work: SqlAlchemyUnitOfWork) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(SqlAlchemyUnitOfWork, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="commit failed"):
        service.excluir_projeto(created.projeto.id)
    monkeypatch.setattr(SqlAlchemyUnitOfWork, "commit", original_commit)

    assert managed_file.read_bytes() == b"restore-me"
    assert service.abrir_projeto(created.projeto.id).projeto.id == created.projeto.id
    assert service.coordenador.operacao_em_andamento is None
    engine.dispose()
