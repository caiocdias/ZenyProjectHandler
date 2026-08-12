# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QTreeWidget
from pytestqt.qtbot import QtBot
from sqlalchemy import Engine, update
from sqlalchemy.exc import IntegrityError

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer, TesseractCliOcr
from zeny_project_handler.adapters.compliance import carregar_registro_conformidade_inicial
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.adapters.persistence.compliance_analysis_repository import (
    SqlComplianceAnalysisRepository,
)
from zeny_project_handler.adapters.persistence.domain_json import dumps_domain
from zeny_project_handler.adapters.persistence.schema import compliance_executions
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.errors import AnaliseConformidadeCanceladaError
from zeny_project_handler.application.human_review import ServicoRevisaoHumana, SessaoRevisao
from zeny_project_handler.domain.analysis import EvidenciaDocumento, ExecucaoAnalise
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.compliance import ExecucaoConformidade
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise, TipoEvidencia
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.project_metadata import MetadadosProjeto
from zeny_project_handler.domain.values import (
    CaixaPagina,
    GeometriaDocumento,
    PontoNormalizado,
)
from zeny_project_handler.ui.documentation_panel import DocumentationPanelWidget
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 8, 12, 15, tzinfo=UTC)


def _page(width: str, height: str) -> PaginaDocumento:
    width_value = Decimal(width)
    height_value = Decimal(height)
    box = CaixaPagina(Decimal(0), Decimal(0), width_value, height_value)
    return PaginaDocumento(
        id=uuid4(),
        numero=1,
        largura_pontos=width_value,
        altura_pontos=height_value,
        rotacao_graus=0,
        media_box=box,
        crop_box=box,
    )


def _document(name: str, digest: str, page: PaginaDocumento) -> DocumentoProjeto:
    return DocumentoProjeto(
        id=uuid4(),
        nome_arquivo=name,
        sha256=digest * 64,
        paginas=(page,),
        tamanho_bytes=100,
    )


def _prepare_context(
    tmp_path: Path,
    catalog: CatalogoTecnico,
) -> tuple[
    Engine,
    UUID,
    ExecutarAnaliseConformidade,
    ServicoRegistroRegrasConformidade,
]:
    engine = create_sqlite_engine(tmp_path / "compliance.sqlite3")
    upgrade_database(engine)

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    a4 = _document("a4.pdf", "a", _page("595", "842"))
    unknown = _document("sem-formato.pdf", "b", _page("700", "1000"))
    project = Projeto(
        id=uuid4(),
        nome="Projeto sintético divergente",
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        documentos=(a4, unknown),
        metadados=MetadadosProjeto(tipo_servico="Rede urbana"),
    )
    semantic_run = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=project.id,
        metodo="interpretador-sintetico",
        versao_metodo="1",
        parametros=(("execucao_extracao_id", str(uuid4())),),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=_NOW,
        finalizada_em=_NOW,
    )
    evidence = tuple(
        EvidenciaDocumento(
            id=uuid4(),
            execucao_id=semantic_run.id,
            pagina_id=document.paginas[0].id,
            tipo=TipoEvidencia.TEXTO,
            geometria=GeometriaDocumento.ponto(
                document.paginas[0].id,
                PontoNormalizado(Decimal("0.1"), Decimal("0.9")),
            ),
            metodo="fixture",
            versao_metodo="1",
            parametros=(),
            conteudo_bruto="CABEÇALHO SEM NÚMERO DE PROJETO",
            criada_em=_NOW,
        )
        for document in project.documentos
    )
    with unit_of_work() as work:
        work.catalogos.salvar(catalog)
        work.projetos.salvar(project)
        work.execucoes_analise.salvar(semantic_run)
        for item in evidence:
            work.evidencias.salvar(item)
        work.commit()
    registry_service = ServicoRegistroRegrasConformidade(
        unit_of_work,
        diretorio_dados=tmp_path / "data",
        relogio=lambda: _NOW,
    )
    registry_service.inicializar(carregar_registro_conformidade_inicial())
    registry_service.definir_regra_ativa("nd31.desenho.escala", ativa=True)
    review_service = ServicoRevisaoHumana(unit_of_work)
    analysis_service = ExecutarAnaliseConformidade(
        unit_of_work,
        review_service.carregar_sessao_semantica,
        relogio=lambda: _NOW,
    )
    return engine, project.id, analysis_service, registry_service


def test_execution_is_deterministic_preserves_history_and_survives_restart(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, service, registry_service = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )

    first = service.executar(project_id)
    repeated = service.executar(project_id)

    assert repeated.id == first.id
    assert dumps_domain(repeated) == dumps_domain(first)
    assert len(service.listar_historico(project_id)) == 1
    by_result = {item.resultado.value for item in first.achados}
    assert by_result == {"CONFORME", "DIVERGENCIA", "NAO_AVALIAVEL"}
    divergent = next(item for item in first.achados if item.resultado.value == "DIVERGENCIA")
    assert "Valor observado: ausente" in divergent.mensagem
    assert "esperado: projeto.nota_servico presente" in divergent.mensagem
    assert divergent.avaliacoes_condicoes
    assert len(divergent.fato_ids) == 1

    with (
        pytest.raises(IntegrityError, match="execucao de conformidade imutavel"),
        engine.begin() as connection,
    ):
        connection.execute(
            update(compliance_executions)
            .where(compliance_executions.c.id == str(first.id))
            .values(rule_version="revisao-adulterada")
        )

    registry_service.remover_regra("nd31.desenho.numero-projeto")
    second = service.executar(project_id)
    history = service.listar_historico(project_id)

    assert second.id != first.id
    assert history == (first, second)
    assert any(item.regra_id == "nd31.desenho.numero-projeto" for item in first.achados)
    assert all(item.regra_id != "nd31.desenho.numero-projeto" for item in second.achados)
    assert service.resultado_desatualizado(first)
    assert not service.resultado_desatualizado(second)

    database_path = tmp_path / "compliance.sqlite3"
    engine.dispose()
    reopened_engine = create_sqlite_engine(database_path)

    def reopened_unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(reopened_engine)

    reopened_review = ServicoRevisaoHumana(reopened_unit_of_work)
    reopened_service = ExecutarAnaliseConformidade(
        reopened_unit_of_work,
        reopened_review.carregar_sessao_semantica,
    )
    assert reopened_service.obter_ultima(project_id) == second
    assert reopened_service.listar_historico(project_id) == history
    reopened_engine.dispose()


def test_active_rule_revision_is_captured_before_loading_the_semantic_session(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, _service, registry_service = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    captured_revision = registry_service.obter_revisao_ativa()
    review_service = ServicoRevisaoHumana(unit_of_work)

    def load_after_registry_changes(identifier: UUID) -> SessaoRevisao:
        registry_service.remover_regra("nd31.desenho.numero-projeto")
        return review_service.carregar_sessao_semantica(identifier)

    service = ExecutarAnaliseConformidade(
        unit_of_work,
        load_after_registry_changes,
        relogio=lambda: _NOW,
    )

    execution = service.executar(project_id)

    assert execution.revisao_regras_id == captured_revision.id
    assert execution.assinatura_regras == captured_revision.assinatura
    assert any(item.regra_id == "nd31.desenho.numero-projeto" for item in execution.achados)
    assert service.resultado_desatualizado(execution)
    engine.dispose()


@pytest.mark.parametrize("failure", ["exception", "cancellation"])
def test_failure_or_cancellation_rolls_back_the_complete_snapshot(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    engine, project_id, service, _registry_service = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )
    if failure == "exception":
        original_save = SqlComplianceAnalysisRepository.salvar

        def fail_after_insert(
            repository: SqlComplianceAnalysisRepository,
            execution: ExecucaoConformidade,
        ) -> None:
            original_save(repository, execution)
            raise RuntimeError("falha depois do insert")

        monkeypatch.setattr(SqlComplianceAnalysisRepository, "salvar", fail_after_insert)
        with pytest.raises(RuntimeError, match="depois do insert"):
            service.executar(project_id)
    else:
        checks = 0

        def cancel_after_insert() -> bool:
            nonlocal checks
            checks += 1
            return checks == 4

        with pytest.raises(AnaliseConformidadeCanceladaError):
            service.executar(project_id, cancelado=cancel_after_insert)

    assert service.obter_ultima(project_id) is None
    assert service.listar_historico(project_id) == ()
    engine.dispose()


def test_panel_loads_latest_marks_stale_and_reapplies_without_ocr(
    qtbot: QtBot,
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, project_id, service, registry_service = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )
    first = service.executar(project_id)

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    review_service = ServicoRevisaoHumana(unit_of_work)
    panel = DocumentationPanelWidget(
        service=review_service,
        registry_service=registry_service,
        analysis_service=service,
        viewer=cast(PdfViewerWidget, object()),
    )
    qtbot.addWidget(panel)
    panel.show()
    panel.abrir_projeto(project_id)

    findings = panel.findChild(QTreeWidget, "complianceFindingsTree")
    rules = panel.findChild(QTreeWidget, "complianceRulesTree")
    status = panel.findChild(QLabel, "complianceExecutionStatusLabel")
    toggle = panel.findChild(QPushButton, "complianceRulesToggleButton")
    analyze = panel.findChild(QPushButton, "complianceAnalyzeButton")
    assert findings is not None and rules is not None and status is not None
    assert toggle is not None and analyze is not None
    first_row = findings.topLevelItem(0)
    assert first_row is not None
    assert first_row.text(0) == "Possível divergência"
    assert "ausente" in first_row.text(3)
    assert "presente" in first_row.text(4)
    assert "CEMIG ND-3.1" in first_row.text(6)
    assert first.versao_regras in first_row.text(7)
    assert first_row.text(8) == "Sem localização no PDF"

    number_rule = next(
        item
        for index in range(rules.topLevelItemCount())
        if (item := rules.topLevelItem(index)) is not None
        and item.text(3) == "nd31.desenho.numero-projeto"
    )
    rules.setCurrentItem(number_rule)
    qtbot.mouseClick(toggle, Qt.MouseButton.LeftButton)

    assert "Resultado desatualizado" in status.text()
    assert service.listar_historico(project_id) == (first,)

    def forbidden_call(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Reaplicação não pode chamar PyMuPDF nem OCR")

    monkeypatch.setattr(PyMuPdfDocumentAnalyzer, "analisar", forbidden_call)
    monkeypatch.setattr(TesseractCliOcr, "reconhecer", forbidden_call)
    qtbot.mouseClick(analyze, Qt.MouseButton.LeftButton)

    assert "Resultado atual" in status.text()
    history = service.listar_historico(project_id)
    assert len(history) == 2
    assert history[0] == first
    for index in range(findings.topLevelItemCount()):
        item = findings.topLevelItem(index)
        assert item is not None
        assert item.text(2) != "Número do projeto com 10 dígitos"
    panel.close()
    engine.dispose()
