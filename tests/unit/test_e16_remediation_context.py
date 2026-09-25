"""Authorial controls for legend context without benchmark or reserve labels."""

from __future__ import annotations

from decimal import Decimal

from zeny_project_handler.adapters.analysis.legend_symbols import (
    ParLegenda,
    RegiaoLegenda,
    contextualizar_resultados,
)
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationEntry,
    CalibrationPolicy,
    reconcile_symbols,
)
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, TipoGeometria
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    FonteObservacaoSimbolo,
    GeometriaObservacaoSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    PrimitivaObservadaSimbolo,
    ResultadoMetodoSimbolos,
    TransformacaoSimbolo,
)
from zeny_project_handler.domain.values import PontoNormalizado


def _profile() -> PerfilMetodoSimbolos:
    return PerfilMetodoSimbolos(
        metodo_id="author-vector",
        versao="1",
        familia="author-vector-geometry",
        dominio_aplicacao="desenho e legenda",
        classes_suportadas=("ATERRAMENTO",),
        camadas_suportadas=("base",),
        fontes_compartilhadas=("authorial-lines",),
        perfil_referencia="e16-context-test",
    )


def _observation(
    profile: PerfilMetodoSimbolos, key: str, *, x: int, y: int, size: int = 80
) -> ObservacaoSimbolo:
    box = ((Decimal(x), Decimal(y)), (Decimal(x + size), Decimal(y + size)))
    normalized = (
        PontoNormalizado(Decimal(x) / 1000, Decimal(y) / 1000),
        PontoNormalizado(Decimal(x + size) / 1000, Decimal(y + size) / 1000),
    )
    return ObservacaoSimbolo(
        fonte=FonteObservacaoSimbolo(
            documento_id="author-document",
            documento_sha256="a" * 64,
            pagina_numero=1,
            camada="base",
        ),
        metodo_assinatura=profile.assinatura(),
        geometria=GeometriaObservacaoSimbolo(
            tipo=TipoGeometria.CAIXA,
            pontos_originais=box,
            pontos_normalizados=normalized,
            transformacao=TransformacaoSimbolo(
                normalizada_para_original=(
                    Decimal(1000),
                    Decimal(0),
                    Decimal(0),
                    Decimal(1000),
                    Decimal(0),
                    Decimal(0),
                ),
                sistema_original="authorial-pdf-points",
            ),
        ),
        alternativas=(AlternativaClasseSimbolo(classe="ATERRAMENTO"),),
        score_bruto=Decimal("0.8"),
        primitivas=(PrimitivaObservadaSimbolo(indice=key, camada="base", pontos_originais=box),),
        chave_legada=key,
    )


def _result(*observations: ObservacaoSimbolo) -> ResultadoMetodoSimbolos:
    profile = _profile()
    return ResultadoMetodoSimbolos(
        perfil=profile,
        coberturas=(
            CoberturaMetodoSimbolos(
                fonte=observations[0].fonte,
                regiao_normalizada=(
                    PontoNormalizado(Decimal(0), Decimal(0)),
                    PontoNormalizado(Decimal(1), Decimal(1)),
                ),
                classes_avaliadas=profile.classes_suportadas,
                estado=EstadoMetodoSimbolos.CONCLUIDO,
            ),
        ),
        observacoes=observations,
    )


def _region() -> RegiaoLegenda:
    # E10's search window is intentionally much taller than its actual first row.
    return RegiaoLegenda(
        pagina_numero=1,
        caixa=(50.0, 20.0, 500.0, 500.0),
        titulo="LEGENDA",
        origem="texto-nativo",
    )


def _pair() -> ParLegenda:
    return ParLegenda(
        id="author-pair",
        pagina_numero=1,
        caixa_exemplar=(100.0, 100.0, 180.0, 180.0),
        caixa_descricao=(200.0, 100.0, 350.0, 180.0),
        descricao="ATERRAMENTO",
        origem="texto-nativo",
        revisao=None,
        pareamento_incerto=False,
        template_sha256="b" * 64,
        dados_png=b"authorial-sample",
    )


def _by_key(result: ResultadoMetodoSimbolos) -> dict[str, ObservacaoSimbolo]:
    return {item.chave_legada or "": item for item in result.observacoes}


def _assert_preserved(before: ResultadoMetodoSimbolos, after: ResultadoMetodoSimbolos) -> None:
    assert after.perfil == before.perfil
    assert after.coberturas == before.coberturas
    assert len(after.observacoes) == len(before.observacoes)
    assert set(_by_key(after)) == set(_by_key(before))
    for key, original in _by_key(before).items():
        classified = _by_key(after)[key]
        assert classified.fonte == original.fonte
        assert classified.geometria == original.geometria
        assert classified.alternativas == original.alternativas
        assert classified.primitivas == original.primitivas
        assert classified.score_bruto == original.score_bruto
        assert classified.metodo_assinatura == original.metodo_assinatura


def test_confirmed_exemplar_is_informative_and_operational_candidate_outside_row_survives() -> None:
    profile = _profile()
    exemplar = _observation(profile, "exemplar", x=100, y=100)
    operational = _observation(profile, "operational", x=100, y=350)
    before = _result(exemplar, operational)

    (after,) = contextualizar_resultados((before,), (_region(),), (_pair(),), {1: (1000.0, 1000.0)})

    _assert_preserved(before, after)
    by_key = _by_key(after)
    assert dict(by_key["exemplar"].atributos)["contexto"] == "legenda"
    assert dict(by_key["exemplar"].atributos)["papel"] == "informative"
    assert dict(by_key["operational"].atributos).get("contexto") != "legenda"
    assert dict(by_key["operational"].atributos).get("papel") != "informative"
    assert by_key["exemplar"].id != exemplar.id
    assert by_key["operational"].id == operational.id

    policy = CalibrationPolicy(
        entries=(
            CalibrationEntry(
                method_signature=profile.assinatura(),
                class_code="ATERRAMENTO",
                stratum="default",
                probability=Decimal("0.999"),
                sample_size=90,
            ),
        )
    )
    composed = reconcile_symbols((after,), policy)
    assert len(composed.occurrences) == 2
    decisions = {item.observations[0].chave_legada: item for item in composed.occurrences}
    assert decisions["exemplar"].decision == "review"
    assert "legend_reference" in decisions["exemplar"].reasons
    assert decisions["operational"].decision == "eligible"


def test_title_without_pair_marks_only_initial_60_point_strip() -> None:
    profile = _profile()
    near_title = _observation(profile, "near-title", x=100, y=25, size=40)
    below_strip = _observation(profile, "below-strip", x=100, y=350)
    before = _result(near_title, below_strip)

    (after,) = contextualizar_resultados((before,), (_region(),), (), {1: (1000.0, 1000.0)})

    _assert_preserved(before, after)
    by_key = _by_key(after)
    assert dict(by_key["near-title"].atributos)["contexto"] == "legenda"
    assert dict(by_key["near-title"].atributos)["papel"] == "informative"
    assert dict(by_key["below-strip"].atributos).get("contexto") != "legenda"
    assert dict(by_key["below-strip"].atributos).get("papel") != "informative"
    assert by_key["near-title"].id != near_title.id
    assert by_key["below-strip"].id == below_strip.id


def test_no_legend_title_keeps_all_observations_unchanged() -> None:
    profile = _profile()
    before = _result(_observation(profile, "only-operational", x=100, y=100))

    (after,) = contextualizar_resultados((before,), (), (), {1: (1000.0, 1000.0)})

    assert after == before
    assert after.observacoes[0].id == before.observacoes[0].id
