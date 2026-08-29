# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QLabel, QPushButton, QTreeWidget
from pytestqt.qtbot import QtBot
from sqlalchemy import Engine, update
from sqlalchemy.exc import IntegrityError
from tests.market_fakes import FakeClassificadorMercado, FakeVerificadorAcoesConcluidas
from tests.remote_gateways import SynchronousDocumentationGateway

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer, TesseractCliOcr
from zeny_project_handler.adapters.compliance import (
    carregar_registro_conformidade_inicial,
    registro_conformidade_de_dict,
)
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
from zeny_project_handler.application.compliance_analysis import (
    VERSAO_METODO_CONFORMIDADE,
    ExecutarAnaliseConformidade,
)
from zeny_project_handler.application.compliance_callouts import (
    OrigemAncoraCallout,
    projetar_callouts_conformidade,
)
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.errors import AnaliseConformidadeCanceladaError
from zeny_project_handler.application.human_review import ServicoRevisaoHumana, SessaoRevisao
from zeny_project_handler.domain.analysis import EvidenciaDocumento, ExecucaoAnalise
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.compliance import ExecucaoConformidade, ResultadoConformidade
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise, TipoEvidencia
from zeny_project_handler.domain.market import DescricaoAcao, Mercado
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.project_metadata import MetadadosProjeto
from zeny_project_handler.domain.values import (
    CaixaPagina,
    GeometriaDocumento,
    PontoNormalizado,
)
from zeny_project_handler.ports.market import DependenciaAcoesError, DependenciaMercadoError
from zeny_project_handler_client.ui.documentation_panel import DocumentationPanelWidget
from zeny_project_handler_client.ui.pdf_viewer import PdfViewerWidget
from zeny_project_handler_contracts.enums import ComplianceStatus


class _ViewerStub(QObject):
    compliance_callout_selected = Signal(str)

    def definir_callouts_conformidade(self, _callouts: tuple[object, ...]) -> None:
        pass


pytestmark = pytest.mark.integration

_NOW = datetime(2026, 8, 12, 15, tzinfo=UTC)


def _import_rule_state(
    service: ServicoRegistroRegrasConformidade,
    rule_id: str,
    *,
    enabled: bool,
) -> None:
    payload = deepcopy(service.obter_revisao_ativa().registro.para_dict())
    registry = payload["registry"]
    rules = payload["rules"]
    assert isinstance(registry, dict) and isinstance(rules, list)
    registry["id"] = str(uuid4())
    registry["version"] = f"fixture-{rule_id}-{enabled}"
    rule = next(item for item in rules if isinstance(item, dict) and item.get("id") == rule_id)
    rule["enabled"] = enabled
    imported = registro_conformidade_de_dict(payload)
    service.importar(service.preparar_importacao(imported))


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
    *,
    codigos_servico: tuple[str, ...] = (),
    extra_evidence: tuple[tuple[str, str, str], ...] = (),
    action_verifier: FakeVerificadorAcoesConcluidas | None = None,
) -> tuple[
    Engine,
    UUID,
    ExecutarAnaliseConformidade,
    ServicoRegistroRegrasConformidade,
    FakeClassificadorMercado,
]:
    engine = create_sqlite_engine(tmp_path / "compliance.sqlite3")
    upgrade_database(engine)

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    a4 = _document("a4.pdf", "a", _page("595", "842"))
    unknown = _document("sem-formato.pdf", "b", _page("700", "1000"))
    project = Projeto(
        id=uuid4(),
        nome="0012345678",
        catalogo_versao_id=catalog.id,
        criado_em=_NOW,
        codigos_servico=codigos_servico,
        documentos=(a4, unknown),
        metadados=MetadadosProjeto(tipo_servico="Rede rural"),
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
    evidence = (
        *evidence,
        *(
            EvidenciaDocumento(
                id=uuid4(),
                execucao_id=semantic_run.id,
                pagina_id=a4.paginas[0].id,
                tipo=TipoEvidencia.TEXTO,
                geometria=GeometriaDocumento.ponto(
                    a4.paginas[0].id,
                    PontoNormalizado(Decimal(x), Decimal(y)),
                ),
                metodo="fixture",
                versao_metodo="1",
                parametros=(),
                conteudo_bruto=text,
                criada_em=_NOW,
            )
            for text, x, y in extra_evidence
        ),
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
    _import_rule_state(registry_service, "nd31.desenho.escala", enabled=True)
    review_service = ServicoRevisaoHumana(unit_of_work)
    market_classifier = FakeClassificadorMercado(Mercado.URBANO)
    analysis_service = ExecutarAnaliseConformidade(
        unit_of_work,
        review_service.carregar_sessao_semantica,
        classificador_mercado=market_classifier,
        verificador_acoes=action_verifier or FakeVerificadorAcoesConcluidas(),
        relogio=lambda: _NOW,
    )
    return engine, project.id, analysis_service, registry_service, market_classifier


def test_execution_is_deterministic_preserves_history_and_survives_restart(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, service, registry_service, market_classifier = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )

    first = service.executar(project_id)
    repeated = service.executar(project_id)

    assert VERSAO_METODO_CONFORMIDADE == "9"
    assert first.versao_metodo == VERSAO_METODO_CONFORMIDADE
    assert repeated.id == first.id
    assert dumps_domain(repeated) == dumps_domain(first)
    assert len(service.listar_historico(project_id)) == 1
    assert market_classifier.consultas == ["0012345678", "0012345678"]
    persisted = service.obter_ultima(project_id)
    assert persisted is not None
    assert "projeto.documentacao_gd_identificada" in {item.chave for item in persisted.fatos}
    assert "projeto.documentacao_gd_identificada" in dumps_domain(persisted)
    by_result = {item.resultado.value for item in first.achados}
    assert by_result == {"CONFORME", "DIVERGENCIA"}
    divergent = next(item for item in first.achados if item.regra_id == "nd31.desenho.escala")
    assert "Valor observado: ausente" in divergent.mensagem
    assert "esperado: projeto.escala em 1:1000, 1:500" in divergent.mensagem
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

    _import_rule_state(registry_service, "nd31.desenho.escala", enabled=False)
    second = service.executar(project_id)
    history = service.listar_historico(project_id)

    assert second.id != first.id
    assert history == (first, second)
    assert any(item.regra_id == "nd31.desenho.escala" for item in first.achados)
    assert all(item.regra_id != "nd31.desenho.escala" for item in second.achados)
    assert service.resultado_desatualizado(first)
    assert not service.resultado_desatualizado(second)
    assert service.resultado_desatualizado(replace(second, versao_metodo="7"))

    database_path = tmp_path / "compliance.sqlite3"
    engine.dispose()
    reopened_engine = create_sqlite_engine(database_path)

    def reopened_unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(reopened_engine)

    reopened_review = ServicoRevisaoHumana(reopened_unit_of_work)
    reopened_service = ExecutarAnaliseConformidade(
        reopened_unit_of_work,
        reopened_review.carregar_sessao_semantica,
        classificador_mercado=FakeClassificadorMercado(Mercado.URBANO),
    )
    assert reopened_service.obter_ultima(project_id) == second
    assert reopened_service.listar_historico(project_id) == history
    reopened_engine.dispose()


def test_market_change_creates_new_snapshot_identity_and_same_market_is_idempotent(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, service, _registry_service, market_classifier = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )

    urban = service.executar(project_id)
    market_classifier.mercado = Mercado.RURAL
    rural = service.executar(project_id)
    repeated_rural = service.executar(project_id)

    assert rural.id != urban.id
    assert repeated_rural.id == rural.id
    assert service.listar_historico(project_id) == (urban, rural)
    assert market_classifier.consultas == ["0012345678"] * 3
    assert {item.chave for item in urban.fatos if item.chave.startswith("rede.contexto_")} == {
        "rede.contexto_urbano"
    }
    assert {item.chave for item in rural.fatos if item.chave.startswith("rede.contexto_")} == {
        "rede.contexto_rural"
    }
    engine.dispose()


def test_external_market_failure_does_not_persist_compliance_snapshot(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, service, _registry_service, market_classifier = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )
    market_classifier.erro = DependenciaMercadoError(
        "O cadastro externo de mercado não pôde ser consultado"
    )

    with pytest.raises(DependenciaMercadoError):
        service.executar(project_id)

    assert market_classifier.consultas == ["0012345678"]
    assert service.obter_ultima(project_id) is None
    assert service.listar_historico(project_id) == ()
    engine.dispose()


def test_actions_without_documentary_trigger_are_not_queried_or_evaluated(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    verifier = FakeVerificadorAcoesConcluidas(resultado=True)
    engine, project_id, service, _registry, _market = _prepare_context(
        tmp_path,
        catalogo_inicial,
        codigos_servico=("0007",),
        action_verifier=verifier,
    )

    execution = service.executar(project_id)

    assert verifier.consultas == []
    assert not {"bi.acoes.impacto-ambiental", "bi.acoes.falta-servidao"}.intersection(
        item.regra_id for item in execution.achados
    )
    engine.dispose()


def test_trigger_without_service_codes_publishes_explained_false_requirement(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    verifier = FakeVerificadorAcoesConcluidas(resultado=True)
    engine, project_id, service, _registry, _market = _prepare_context(
        tmp_path,
        catalogo_inicial,
        extra_evidence=(("Impacto Ambiental: Sim", "0.70", "0.88"),),
        action_verifier=verifier,
    )

    execution = service.executar(project_id)
    finding = next(
        item for item in execution.achados if item.regra_id == "bi.acoes.impacto-ambiental"
    )
    requirement = next(
        item
        for item in execution.fatos
        if item.chave == "projeto.acao_avaliar_impacto_ambiental_concluida"
    )

    assert verifier.consultas == []
    assert finding.resultado is ResultadoConformidade.DIVERGENCIA
    assert finding.titulo == "IMPACTO AMBIENTAL PENDENTE"
    assert requirement.valor is False
    assert requirement.geometria is None
    assert "não possui códigos de serviço" in requirement.origem
    engine.dispose()


def test_two_action_triggers_query_once_preserve_evidence_and_anchor_callouts(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    verifier = FakeVerificadorAcoesConcluidas(resultado=False)
    engine, project_id, service, _registry, _market = _prepare_context(
        tmp_path,
        catalogo_inicial,
        codigos_servico=("0007", "0123"),
        extra_evidence=(
            ("Impacto Ambiental: SIM", "0.70", "0.91"),
            ("FAIXA DE SERVIDÃO", "0.25", "0.25"),
            ("Impacto Ambiental: Sim", "0.70", "0.84"),
        ),
        action_verifier=verifier,
    )

    execution = service.executar(project_id)
    findings = {
        item.regra_id: item
        for item in execution.achados
        if item.regra_id in {"bi.acoes.impacto-ambiental", "bi.acoes.falta-servidao"}
    }
    assert verifier.consultas == [
        (
            "0012345678",
            ("0007", "0123"),
            DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL,
        ),
        ("0012345678", ("0007", "0123"), DescricaoAcao.FALTA_SERVIDAO),
    ]
    assert set(findings) == {"bi.acoes.impacto-ambiental", "bi.acoes.falta-servidao"}
    assert all(item.resultado is ResultadoConformidade.DIVERGENCIA for item in findings.values())
    assert {item.valor for item in execution.fatos if item.chave == "projeto.codigo_servico"} == {
        "0007",
        "0123",
    }

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    session = ServicoRevisaoHumana(unit_of_work).carregar_sessao_semantica(project_id)
    impact_evidence = tuple(
        item
        for item in session.evidencias
        if (item.conteudo_bruto or "").startswith("Impacto Ambiental")
    )
    impact_finding = findings["bi.acoes.impacto-ambiental"]
    assert {item.id for item in impact_evidence} <= set(impact_finding.evidencia_ids)
    callouts = {
        item.id: item
        for item in projetar_callouts_conformidade(
            execution,
            evidencias=session.evidencias,
            paginas=tuple(
                page for document in session.projeto.documentos for page in document.paginas
            ),
        )
    }
    impact_callout = callouts[impact_finding.id]
    first_impact = min(
        impact_evidence,
        key=lambda item: tuple(point.y for point in item.geometria.pontos),
    )
    assert impact_callout.ancoras[0].origem is OrigemAncoraCallout.EVIDENCIA
    assert impact_callout.ancoras[0].referencia_id == first_impact.id
    assert len(callouts) >= 2
    engine.dispose()


def test_completed_action_is_conformant_and_has_no_callout(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    verifier = FakeVerificadorAcoesConcluidas(
        resultados={DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL: True}
    )
    engine, project_id, service, _registry, _market = _prepare_context(
        tmp_path,
        catalogo_inicial,
        codigos_servico=("0001",),
        extra_evidence=(("Impacto Ambiental: Sim", "0.70", "0.88"),),
        action_verifier=verifier,
    )

    execution = service.executar(project_id)
    finding = next(
        item for item in execution.achados if item.regra_id == "bi.acoes.impacto-ambiental"
    )

    assert finding.resultado is ResultadoConformidade.CONFORME
    assert len(verifier.consultas) == 1

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    session = ServicoRevisaoHumana(unit_of_work).carregar_sessao_semantica(project_id)
    assert finding.id not in {
        item.id
        for item in projetar_callouts_conformidade(
            execution,
            evidencias=session.evidencias,
            paginas=tuple(
                page for document in session.projeto.documentos for page in document.paginas
            ),
        )
    }
    engine.dispose()


@pytest.mark.parametrize("failure", ["dependency", "cancellation"])
def test_action_failure_or_cancellation_between_queries_publishes_no_snapshot(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    failure: str,
) -> None:
    verifier = FakeVerificadorAcoesConcluidas(resultado=False)
    if failure == "dependency":
        verifier.erros[DescricaoAcao.FALTA_SERVIDAO] = DependenciaAcoesError(
            "O cadastro externo de ações não pôde ser consultado"
        )
    engine, project_id, service, _registry, _market = _prepare_context(
        tmp_path,
        catalogo_inicial,
        codigos_servico=("0001",),
        extra_evidence=(
            ("Impacto Ambiental: Sim", "0.70", "0.88"),
            ("SERVIDÃO", "0.25", "0.25"),
        ),
        action_verifier=verifier,
    )

    if failure == "dependency":
        with pytest.raises(DependenciaAcoesError):
            service.executar(project_id)
        assert len(verifier.consultas) == 2
    else:
        with pytest.raises(AnaliseConformidadeCanceladaError):
            service.executar(
                project_id,
                cancelado=lambda: len(verifier.consultas) == 1,
            )
        assert verifier.consultas == [
            (
                "0012345678",
                ("0001",),
                DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL,
            )
        ]
    assert service.obter_ultima(project_id) is None
    assert service.listar_historico(project_id) == ()
    engine.dispose()


def test_ns_and_service_changes_mark_stale_and_create_auditable_history(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    verifier = FakeVerificadorAcoesConcluidas(resultado=True)
    engine, project_id, service, _registry, _market = _prepare_context(
        tmp_path,
        catalogo_inicial,
        codigos_servico=("0001",),
        extra_evidence=(("Impacto Ambiental: Sim", "0.70", "0.88"),),
        action_verifier=verifier,
    )
    first = service.executar(project_id)

    with SqlAlchemyUnitOfWork(engine) as work:
        project = work.projetos.obter(project_id)
        assert project is not None
        work.projetos.salvar(replace(project, codigos_servico=("0002",)))
        work.commit()
    assert service.resultado_desatualizado(first)
    second = service.executar(project_id)
    assert second.id != first.id
    assert second.assinatura_sessao != first.assinatura_sessao
    assert not service.resultado_desatualizado(second)

    with SqlAlchemyUnitOfWork(engine) as work:
        project = work.projetos.obter(project_id)
        assert project is not None
        work.projetos.salvar(replace(project, nome="0098765432"))
        work.commit()
    assert service.resultado_desatualizado(second)
    third = service.executar(project_id)

    assert third.id not in {first.id, second.id}
    assert third.assinatura_sessao != second.assinatura_sessao
    assert service.listar_historico(project_id) == (first, second, third)
    assert [
        tuple(item.valor for item in execution.fatos if item.chave == "projeto.codigo_servico")
        for execution in (first, second, third)
    ] == [("0001",), ("0002",), ("0002",)]
    assert [item[0] for item in verifier.consultas] == [
        "0012345678",
        "0012345678",
        "0098765432",
    ]
    engine.dispose()


def test_remote_dtos_preserve_baseline_semantics_for_all_41_active_rules(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, service, registry_service, _market_classifier = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )
    execution = service.executar(project_id)

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    gateway = SynchronousDocumentationGateway(
        engine=engine,
        data_directory=tmp_path / "data",
        review_service=ServicoRevisaoHumana(unit_of_work),
        analysis_service=service,
        registry_service=registry_service,
    )
    registry = gateway.get_active_registry()
    remote = gateway.get_latest_compliance(project_id)

    assert registry.rule_count == registry.active_rule_count == 41
    assert remote is not None
    expected_status = {
        ResultadoConformidade.CONFORME: ComplianceStatus.COMPLIANT,
        ResultadoConformidade.DIVERGENCIA: ComplianceStatus.DIVERGENCE,
        ResultadoConformidade.NAO_AVALIAVEL: ComplianceStatus.NOT_EVALUABLE,
    }
    domain_findings = {item.id: item for item in execution.achados}
    dto_findings = {item.finding_id.root: item for item in remote.findings}
    assert dto_findings.keys() == domain_findings.keys()
    for finding_id, finding in domain_findings.items():
        dto = dto_findings[finding_id]
        assert dto.rule_id == finding.regra_id
        assert dto.status is expected_status[finding.resultado]
        assert dto.rule_registry_revision == finding.versao_regras
        assert dto.source_reference == f"{finding.fonte.documento} · {finding.fonte.item}"
        if dto.callout is not None:
            assert dto.callout.finding_id == dto.finding_id
            assert dto.callout.navigation == dto.navigation
            assert dto.callout.anchors
    engine.dispose()


def test_active_rule_revision_is_captured_before_loading_the_semantic_session(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project_id, _service, registry_service, _market_classifier = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    captured_revision = registry_service.obter_revisao_ativa()
    review_service = ServicoRevisaoHumana(unit_of_work)

    def load_after_registry_changes(identifier: UUID) -> SessaoRevisao:
        _import_rule_state(registry_service, "nd31.desenho.escala", enabled=False)
        return review_service.carregar_sessao_semantica(identifier)

    service = ExecutarAnaliseConformidade(
        unit_of_work,
        load_after_registry_changes,
        classificador_mercado=FakeClassificadorMercado(Mercado.URBANO),
        relogio=lambda: _NOW,
    )

    execution = service.executar(project_id)

    assert execution.revisao_regras_id == captured_revision.id
    assert execution.assinatura_regras == captured_revision.assinatura
    assert any(item.regra_id == "nd31.desenho.escala" for item in execution.achados)
    assert service.resultado_desatualizado(execution)
    engine.dispose()


@pytest.mark.parametrize("failure", ["exception", "cancellation"])
def test_failure_or_cancellation_rolls_back_the_complete_snapshot(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    engine, project_id, service, _registry_service, market_classifier = _prepare_context(
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
            return checks == 5

        with pytest.raises(AnaliseConformidadeCanceladaError):
            service.executar(project_id, cancelado=cancel_after_insert)

    assert service.obter_ultima(project_id) is None
    assert service.listar_historico(project_id) == ()
    assert market_classifier.consultas == ["0012345678"]
    engine.dispose()


def test_panel_loads_latest_marks_stale_and_reapplies_without_ocr(
    qtbot: QtBot,
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, project_id, service, registry_service, _market_classifier = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )
    first = service.executar(project_id)

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    review_service = ServicoRevisaoHumana(unit_of_work)
    gateway = SynchronousDocumentationGateway(
        engine=engine,
        data_directory=tmp_path / "data",
        review_service=review_service,
        analysis_service=service,
        registry_service=registry_service,
    )
    panel = DocumentationPanelWidget(
        gateway=gateway,
        viewer=cast(PdfViewerWidget, _ViewerStub()),
    )
    qtbot.addWidget(panel)
    panel.show()
    panel.abrir_projeto(project_id)

    findings = panel.findChild(QTreeWidget, "complianceFindingsTree")
    rules = panel.findChild(QTreeWidget, "complianceRulesTree")
    status = panel.findChild(QLabel, "complianceExecutionStatusLabel")
    toggle = panel.findChild(QPushButton, "complianceRulesToggleButton")
    remove = panel.findChild(QPushButton, "complianceRulesRemoveButton")
    analyze = panel.findChild(QPushButton, "complianceAnalyzeButton")
    assert findings is not None and rules is not None and status is not None
    assert toggle is None and remove is None and analyze is not None
    first_row = findings.topLevelItem(0)
    assert first_row is not None
    assert first_row.text(0) == "Divergência"
    assert "ausente" in first_row.text(3).casefold()
    assert "presente" in first_row.text(4).casefold()
    assert "CEMIG ND-3.1" in first_row.text(6)
    assert first.versao_regras in first_row.text(7)
    assert first_row.text(8) == "Sem localização no PDF"

    number_rule = next(
        item
        for index in range(rules.topLevelItemCount())
        if (item := rules.topLevelItem(index)) is not None
        and item.data(0, Qt.ItemDataRole.UserRole) == "nd31.desenho.numero-projeto"
    )
    rules.setCurrentItem(number_rule)
    _import_rule_state(registry_service, "nd31.desenho.numero-projeto", enabled=False)
    panel._refresh_registry(gateway.get_active_registry())

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


def test_panel_marks_a_previous_compliance_method_as_stale(
    qtbot: QtBot,
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, project_id, service, registry_service, _market_classifier = _prepare_context(
        tmp_path,
        catalogo_inicial,
    )
    legacy_execution = replace(service.executar(project_id), versao_metodo="2")
    monkeypatch.setattr(service, "obter_ultima", lambda _project_id: legacy_execution)

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    gateway = SynchronousDocumentationGateway(
        engine=engine,
        data_directory=tmp_path / "data",
        review_service=ServicoRevisaoHumana(unit_of_work),
        analysis_service=service,
        registry_service=registry_service,
    )
    panel = DocumentationPanelWidget(
        gateway=gateway,
        viewer=cast(PdfViewerWidget, _ViewerStub()),
    )
    qtbot.addWidget(panel)
    panel.abrir_projeto(project_id)

    status = panel.findChild(QLabel, "complianceExecutionStatusLabel")
    assert status is not None
    assert "Resultado desatualizado" in status.text()
    panel.close()
    engine.dispose()
