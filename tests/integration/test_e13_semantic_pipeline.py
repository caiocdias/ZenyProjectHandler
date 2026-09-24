"""Integração E12→E13: proposta revisável, fonte, cache e história humana."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from tests.factories import complete_project
from tests.interpretation_factories import text_evidence
from tests.unit.test_symbol_reconciliation import _observation, _policy, _profile, _result

from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.errors import InterpretacaoProjetoError
from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.application.interpretation_pipeline import (
    ExecutarPipelineInterpretacao,
    ResultadoExecucaoInterpretacao,
)
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    SymbolReconciliation,
    reconcile_symbols,
)
from zeny_project_handler.domain.analysis import ExecucaoAnalise, PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico, ExtraAttributes, TipoEquipamento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoMetodoSimbolos,
    EstadoRevisao,
    SituacaoProjeto,
)
from zeny_project_handler.domain.project import Equipamento, Projeto
from zeny_project_handler.domain.symbols import (
    FonteObservacaoSimbolo,
    ObservacaoSimbolo,
    ResultadoMetodoSimbolos,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def semantic_context(
    tmp_path: Path, catalogo_inicial: CatalogoTecnico
) -> Iterator[tuple[Engine, Projeto, ExecucaoAnalise]]:
    project = complete_project(catalogo_inicial)
    page = project.documentos[0].paginas[0]
    next_page = replace(page, id=uuid4(), numero=2)
    document = replace(project.documentos[0], paginas=(page, next_page))
    project = replace(
        project,
        documentos=(document,),
        ordem_leitura_paginas=(page.id, next_page.id),
    )
    engine = create_sqlite_engine(tmp_path / "e13-semantic.sqlite3")
    upgrade_database(engine)
    source = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=project.id,
        metodo="fixture-e13-source",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 9, 24, 9, tzinfo=UTC),
        finalizada_em=datetime(2026, 9, 24, 9, 1, tzinfo=UTC),
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.execucoes_analise.salvar(source)
        work.commit()
    try:
        yield engine, project, source
    finally:
        engine.dispose()


def _runner(engine: Engine) -> ExecutarPipelineInterpretacao:
    registry = carregar_registro_regras_inicial()
    return ExecutarPipelineInterpretacao(
        InterpretadorRegrasExplicitas(registry),
        registry,
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 9, 24, 10, tzinfo=UTC),
    )


def _symbol(
    project: Projeto,
    method: str,
    class_code: str,
    *,
    page: int = 1,
    layer: str = "base",
    x: str = "0.10",
    score: str = "0.20",
    alternatives: tuple[str, ...] = (),
    attributes: ExtraAttributes = (),
    situation: SituacaoProjeto | None = SituacaoProjeto.INSTALAR,
) -> tuple[ResultadoMetodoSimbolos, ObservacaoSimbolo]:
    profile = _profile(method)
    observation = _observation(
        profile,
        class_code,
        page=page,
        layer=layer,
        x=x,
        raw_score=score,
        alternatives=alternatives,
        attributes=attributes,
        situation=situation,
        primitive=f"{layer}:{page}:{x}",
    )
    document = project.documentos[0]
    observation = replace(
        observation,
        fonte=FonteObservacaoSimbolo(
            documento_id=str(document.id),
            documento_sha256=document.sha256,
            pagina_numero=page,
            camada=layer,
            origem_pdf=observation.fonte.origem_pdf,
        ),
    )
    return _result(profile, observation), observation


def _reconciled(
    results: tuple[ResultadoMetodoSimbolos, ...],
    *,
    calibrated_class: str | None = None,
) -> SymbolReconciliation:
    policy = (
        _policy((results[0].perfil, calibrated_class, "0.995", 90))
        if calibrated_class is not None
        else CalibrationPolicy()
    )
    return reconcile_symbols(results, policy)


def _symbol_proposals(result: ResultadoExecucaoInterpretacao) -> tuple[PropostaElemento, ...]:
    return tuple(
        item
        for item in result.elementos
        if dict(item.atributos_sugeridos).get("origem_simbolo_ocorrencia_id")
    )


def test_exclusive_low_score_symbol_survives_other_method_non_detection_and_reopens(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source = semantic_context
    first, observation = _symbol(
        project,
        "visual-a",
        "TRANSFORMADOR",
        attributes=(("situacao_validada", True), ("quantidade_ativos", 1)),
    )
    silent_profile = _profile("silent-b")
    silent = _result(silent_profile, state=EstadoMetodoSimbolos.NAO_DETECCAO)
    silent = replace(
        silent,
        coberturas=(replace(silent.coberturas[0], fonte=observation.fonte),),
    )
    symbols = _reconciled((first, silent), calibrated_class="TRANSFORMADOR")
    assert len(symbols.occurrences) == 1
    assert symbols.occurrences[0].decision == "eligible"
    assert symbols.occurrences[0].raw_scores[0][1] == Decimal("0.20")

    result = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    proposals = _symbol_proposals(result)
    assert len(proposals) == 1
    proposal = proposals[0]
    attrs = dict(proposal.atributos_sugeridos)
    assert proposal.categoria is CategoriaElemento.EQUIPAMENTO
    assert attrs["origem_simbolo_ocorrencia_id"] == symbols.occurrences[0].id
    assert attrs["simbolo_decisao_e12"] == "eligible"
    assert Decimal(str(attrs["simbolo_probabilidade_calibrada"])) == Decimal("0.995")
    assert attrs["simbolo_classe"] == "TRANSFORMADOR"
    assert observation.id in str(attrs["simbolo_observacao_ids"])
    assert _runner(engine).executar(project.id, source.id, simbolos=symbols).resultado_reutilizado
    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.propostas.obter(proposal.id) == proposal
        assert work.execucoes_analise.obter(result.execucao.id) == result.execucao
        stored_evidence = work.evidencias.listar_da_execucao(source.id)
        assert stored_evidence
        assert set(proposal.evidencia_ids) <= {item.id for item in stored_evidence}
        assert all(work.evidencias.obter(item_id) is not None for item_id in proposal.evidencia_ids)


@pytest.mark.parametrize(
    ("class_code", "alternatives", "attributes"),
    (
        ("TRANSFORMADOR", ("PARA_RAIOS",), ()),
        ("TRANSFORMADOR", (), (("referencias_possiveis", '["id-a", "id-b"]'),)),
        ("TRANSFORMADOR", (), (("status", "pending"),)),
        ("TRANSFORMADOR", (), (("contexto", "legenda"),)),
        ("ESTAI", (), ()),
        ("TR_ID_1", (), ()),
    ),
)
def test_ambiguous_legend_pending_and_guy_are_one_visible_non_promoted_occurrence(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
    class_code: str,
    alternatives: tuple[str, ...],
    attributes: ExtraAttributes,
) -> None:
    engine, project, source = semantic_context
    method, _ = _symbol(
        project,
        "visual-a",
        class_code,
        alternatives=alternatives,
        attributes=attributes,
    )
    symbols = _reconciled((method,), calibrated_class=class_code)
    result = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    proposals = _symbol_proposals(result)
    assert len(proposals) == 1
    proposal = proposals[0]
    attrs = dict(proposal.atributos_sugeridos)
    assert proposal.categoria is CategoriaElemento.EQUIPAMENTO
    assert proposal.estado_revisao is not EstadoRevisao.CONFIRMADA
    assert proposal.tipo_catalogo_sugerido_id is None
    assert attrs["origem_simbolo_ocorrencia_id"] == symbols.occurrences[0].id
    if class_code == "ESTAI":
        assert attrs["simbolo_papel"] == "suporte"
        assert attrs["simbolo_ativo_elegivel"] is False
    if class_code == "TR_ID_1":
        assert attrs["simbolo_familia_nao_suportada"] is True
    with SqlAlchemyUnitOfWork(engine) as work:
        persisted = work.projetos.obter(project.id)
        assert persisted is not None
        assert persisted.elementos == project.elementos
        assert work.propostas.obter(proposal.id) == proposal


def test_nearby_symbols_and_different_pages_keep_separate_proposals(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source = semantic_context
    observations = tuple(
        _symbol(project, f"visual-{index}", "ESTAI", page=page, x=x)[0]
        for index, (page, x) in enumerate(((1, "0.10"), (1, "0.12"), (2, "0.10")))
    )
    symbols = _reconciled(observations)
    assert len(symbols.occurrences) == 3
    result = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    proposals = _symbol_proposals(result)
    assert len(proposals) == 3
    assert (
        len({dict(item.atributos_sugeridos)["origem_simbolo_ocorrencia_id"] for item in proposals})
        == 3
    )
    assert {item.geometria.pagina_id for item in proposals} == {
        page.id for page in project.documentos[0].paginas
    }
    assert all(item.tipo_catalogo_sugerido_id is None for item in proposals)


def test_known_class_keeps_quantity_situation_and_support_unresolved(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source = semantic_context
    method, _ = _symbol(
        project,
        "visual-a",
        "TRANSFORMADOR",
        situation=None,
        attributes=(),
    )
    symbols = _reconciled((method,), calibrated_class="TRANSFORMADOR")
    proposal = _symbol_proposals(_runner(engine).executar(project.id, source.id, simbolos=symbols))[
        0
    ]
    attrs = dict(proposal.atributos_sugeridos)
    assert attrs["simbolo_classe_resolvida"] is True
    assert attrs["simbolo_situacao_resolvida"] is False
    assert attrs["simbolo_quantidade_resolvida"] is False
    assert attrs["simbolo_associacao_resolvida"] is False
    assert attrs["situacao_pendente"] is True
    assert attrs["quantidade_pendente"] is True
    assert attrs["associacao_pendente"] is True
    assert proposal.estado_revisao is not EstadoRevisao.CONFIRMADA


def test_visual_situation_hint_survives_reopen_without_becoming_effective_situation(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source = semantic_context
    method, observation = _symbol(
        project,
        "color-only-visual",
        "TRANSFORMADOR",
        situation=SituacaoProjeto.INSTALAR,
        attributes=(("cor", "#008000"),),
    )
    symbols = _reconciled((method,), calibrated_class="TRANSFORMADOR")
    initial = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    proposal = _symbol_proposals(initial)[0]
    attrs = dict(proposal.atributos_sugeridos)
    readings = json.loads(str(attrs["simbolo_situacoes_observadas"]))
    assert len(readings) == 1
    assert readings[0]["observacao_id"] == observation.id
    assert readings[0]["situacao"] == SituacaoProjeto.INSTALAR.value
    assert readings[0]["metodo_assinatura"] == observation.metodo_assinatura
    assert readings[0]["camada"] == "base"
    assert readings[0]["indicio"] == "cor=#008000"
    assert attrs["simbolo_situacao_resolvida"] is False
    assert attrs["situacao_pendente"] is True
    assert proposal.estado_revisao is not EstadoRevisao.CONFIRMADA

    reopened = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    assert reopened.resultado_reutilizado
    assert _symbol_proposals(reopened) == (proposal,)
    with SqlAlchemyUnitOfWork(engine) as work:
        stored = work.propostas.obter(proposal.id)
        assert stored == proposal
        evidence = work.evidencias.obter(proposal.evidencia_ids[0])
        assert evidence is not None
        evidence_attrs = dict(evidence.atributos_extraidos)
        assert evidence_attrs["simbolo_observacao_id"] == observation.id
        assert evidence_attrs["simbolo_situacao_observada"] == SituacaoProjeto.INSTALAR.value
        assert evidence_attrs["simbolo_situacao_indicio"] == "cor=#008000"


def test_equally_near_documented_poles_do_not_guess_symbol_support(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project, source = semantic_context
    page = project.documentos[0].paginas[0].id
    pole_code = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].codigo
    pole_codes = tuple(
        text_evidence(
            execution_id=source.id,
            page_id=page,
            key=f"support-code-{index}",
            text=pole_code,
            x=x,
            y="0.14",
        )
        for index, x in enumerate(("0.12", "0.16"))
    )
    labels = tuple(
        text_evidence(
            execution_id=source.id,
            page_id=page,
            key=f"support-label-{index}",
            text=f"P{index + 1}",
            x=x,
            y="0.14",
        )
        for index, x in enumerate(("0.12", "0.16"))
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        for evidence in (*pole_codes, *labels):
            work.evidencias.salvar(evidence)
        work.commit()
    first, first_observation = _symbol(
        project,
        "visual-a",
        "TRANSFORMADOR",
        situation=SituacaoProjeto.INSTALAR,
        attributes=(("quantidade_ativos", 1), ("cor", "#008000")),
    )
    second, second_observation = _symbol(
        project,
        "visual-b",
        "TRANSFORMADOR",
        situation=SituacaoProjeto.REMOVER,
        attributes=(("quantidade_ativos", 2), ("cor", "#800000")),
    )
    symbols = _reconciled((first, second), calibrated_class="TRANSFORMADOR")
    assert len(symbols.occurrences) == 1
    result = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    poles = [item for item in result.elementos if item.categoria is CategoriaElemento.POSTE]
    assert len(poles) == 2
    symbol = _symbol_proposals(result)[0]
    attrs = dict(symbol.atributos_sugeridos)
    assert attrs["associacao_pendente"] is True
    assert attrs["quantidade_pendente"] is True
    assert attrs["situacao_pendente"] is True
    assert attrs["suporte_proposta_id"] is None
    situations = json.loads(str(attrs["simbolo_situacoes_observadas"]))
    assert {item["observacao_id"]: item["situacao"] for item in situations} == {
        first_observation.id: SituacaoProjeto.INSTALAR.value,
        second_observation.id: SituacaoProjeto.REMOVER.value,
    }
    quantities = json.loads(str(attrs["simbolo_quantidades_observadas"]))
    assert {item["observacao_id"]: item["quantidade_ativos"] for item in quantities} == {
        first_observation.id: 1,
        second_observation.id: 2,
    }
    candidates = json.loads(str(attrs["simbolo_suportes_candidatos"]))
    assert {item["proposta_id"] for item in candidates} == {str(pole.id) for pole in poles}
    assert {item["pagina_id"] for item in candidates} == {str(page)}
    assert all(item["distancia_normalizada"] <= 0.025 for item in candidates)
    assert not any(
        relation.origem_referencia_id == symbol.id and relation.tipo_relacao == "INSTALADO_EM"
        for relation in result.relacoes
    )
    reopened = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    assert reopened.resultado_reutilizado
    assert _symbol_proposals(reopened) == (symbol,)
    with SqlAlchemyUnitOfWork(engine) as work:
        persisted = work.projetos.obter(project.id)
        assert persisted is not None
        before = sum(isinstance(item, Equipamento) for item in project.elementos)
        assert sum(isinstance(item, Equipamento) for item in persisted.elementos) == before
        stored = work.propostas.obter(symbol.id)
        assert stored == symbol
        stored_evidence = tuple(
            work.evidencias.obter(evidence_id) for evidence_id in symbol.evidencia_ids
        )
        assert all(item is not None for item in stored_evidence)
        evidence_by_observation = {
            dict(item.atributos_extraidos)["simbolo_observacao_id"]: item
            for item in stored_evidence
            if item is not None
        }
        assert set(evidence_by_observation) == {first_observation.id, second_observation.id}
        assert {
            observation_id: dict(evidence.atributos_extraidos)["simbolo_quantidade_observada"]
            for observation_id, evidence in evidence_by_observation.items()
        } == {first_observation.id: 1, second_observation.id: 2}


def test_exclusive_with_explicit_catalog_situation_quantity_and_unique_support_can_promote(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
    catalogo_inicial: CatalogoTecnico,
) -> None:
    engine, project, source = semantic_context
    page = project.documentos[0].paginas[0].id
    pole_code = catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)[0].codigo
    transformer_class_id = next(
        option.id
        for group in catalogo_inicial.grupos_opcao
        if group.chave == "classe_equipamento"
        for option in group.opcoes
        if option.codigo == "TRANSFORMADOR"
    )
    equipment = next(
        item
        for item in catalogo_inicial.itens_ativos(CategoriaElemento.EQUIPAMENTO)
        if isinstance(item, TipoEquipamento)
        and item.classe_equipamento_opcao_id == transformer_class_id
    )
    support = text_evidence(
        execution_id=source.id,
        page_id=page,
        key="unique-support-code",
        text=pole_code,
        x="0.14",
        y="0.14",
    )
    support_label = text_evidence(
        execution_id=source.id,
        page_id=page,
        key="unique-support-label",
        text="P1",
        x="0.14",
        y="0.14",
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.evidencias.salvar(support)
        work.evidencias.salvar(support_label)
        work.commit()
    method, _ = _symbol(
        project,
        "visual-a",
        "TRANSFORMADOR",
        score="0.20",
        attributes=(
            ("tipo_catalogo_id", str(equipment.id)),
            ("situacao_validada", True),
            ("quantidade_ativos", 1),
        ),
    )
    symbols = _reconciled((method,), calibrated_class="TRANSFORMADOR")
    result = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    proposal = _symbol_proposals(result)[0]
    attrs = dict(proposal.atributos_sugeridos)
    assert attrs["simbolo_associacao_resolvida"] is True
    assert attrs["simbolo_catalogo_resolvido"] is True
    assert proposal.tipo_catalogo_sugerido_id == equipment.id
    assert proposal.estado_revisao is EstadoRevisao.CONFIRMADA
    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.decisoes_revisao.obter_da_proposta(proposal.id) is not None


def test_base_and_annotation_stay_separate_and_annotation_requires_review(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source = semantic_context
    base, _ = _symbol(project, "base-method", "TRANSFORMADOR", layer="base")
    annotation, _ = _symbol(project, "annotation-method", "TRANSFORMADOR", layer="anotacao")
    symbols = _reconciled((base, annotation), calibrated_class="TRANSFORMADOR")
    assert len(symbols.occurrences) == 2
    result = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    proposals = _symbol_proposals(result)
    assert len(proposals) == 2
    assert (
        len({dict(item.atributos_sugeridos)["origem_simbolo_ocorrencia_id"] for item in proposals})
        == 2
    )
    annotation_observation = annotation.observacoes[0]
    marked = next(
        item
        for item in proposals
        if annotation_observation.id
        in str(dict(item.atributos_sugeridos)["simbolo_observacao_ids"])
    )
    attrs = dict(marked.atributos_sugeridos)
    assert attrs["revisao_tecnica_pendente"] is True
    assert attrs["simbolo_ativo_elegivel"] is False
    assert marked.estado_revisao is not EstadoRevisao.CONFIRMADA


def test_reanalysis_keeps_rejection_and_current_result_pending(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source = semantic_context
    first_method, _ = _symbol(project, "visual-a", "ESTAI", layer="base")
    first_symbols = _reconciled((first_method,))
    initial = _runner(engine).executar(project.id, source.id, simbolos=first_symbols)
    old = _symbol_proposals(initial)[0]
    review = ServicoRevisaoHumana(lambda: SqlAlchemyUnitOfWork(engine))
    decision = review.rejeitar(old.id, revisor="Revisor E13", motivo="Camada conferida")
    revised_method, _ = _symbol(project, "visual-a", "ESTAI", layer="anotacao")
    revised_symbols = _reconciled((revised_method,))
    current = _runner(engine).executar(project.id, source.id, simbolos=revised_symbols)
    assert current.execucao.id != initial.execucao.id
    new = _symbol_proposals(current)[0]
    assert new.id != old.id
    assert new.estado_revisao is not EstadoRevisao.CONFIRMADA
    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.decisoes_revisao.obter_da_proposta(old.id) == decision
        stored_old = work.propostas.obter(old.id)
        assert isinstance(stored_old, PropostaElemento)
        assert stored_old.estado_revisao is EstadoRevisao.REJEITADA
        assert work.propostas.obter(new.id) == new


def test_source_page_mismatch_does_not_materialize_network_proposal(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source = semantic_context
    method, observation = _symbol(project, "visual-a", "TRANSFORMADOR")
    untrusted = replace(
        observation,
        fonte=replace(observation.fonte, documento_sha256="f" * 64),
    )
    method = _result(method.perfil, untrusted)
    symbols = _reconciled((method,), calibrated_class="TRANSFORMADOR")
    with pytest.raises(InterpretacaoProjetoError):
        _runner(engine).executar(project.id, source.id, simbolos=symbols)
    with SqlAlchemyUnitOfWork(engine) as work:
        executions = work.execucoes_analise.listar_do_projeto(project.id)
        failed = [item for item in executions if item.estado is EstadoExecucaoAnalise.FALHOU]
        assert len(failed) == 1
        assert work.propostas.listar_da_execucao(failed[0].id) == ()


def test_text_literal_alone_does_not_gain_symbol_provenance(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source = semantic_context
    evidence = text_evidence(
        execution_id=source.id,
        page_id=project.documentos[0].paginas[0].id,
        key="isolated-transformer-label",
        text="TRANSFORMADOR",
        x="0.42",
        y="0.38",
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.evidencias.salvar(evidence)
        work.commit()
    result = _runner(engine).executar(project.id, source.id)
    assert not _symbol_proposals(result)
    assert all(
        dict(item.atributos_sugeridos).get("reconhecido_por_simbologia") is not True
        for item in result.elementos
    )


def test_non_detection_is_coverage_without_a_positive_proposal(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise],
) -> None:
    engine, project, source = semantic_context
    detector = _profile("silent-a")
    result = _result(detector, state=EstadoMetodoSimbolos.NAO_DETECCAO)
    document = project.documentos[0]
    coverage_source = replace(
        result.coberturas[0].fonte,
        documento_id=str(document.id),
        documento_sha256=document.sha256,
    )
    result = replace(result, coberturas=(replace(result.coberturas[0], fonte=coverage_source),))
    symbols = _reconciled((result,))
    assert symbols.occurrences == ()
    analyzed = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    assert not _symbol_proposals(analyzed)
    with SqlAlchemyUnitOfWork(engine) as work:
        reopened = work.projetos.obter(project.id)
        assert reopened is not None and reopened.elementos == project.elementos
