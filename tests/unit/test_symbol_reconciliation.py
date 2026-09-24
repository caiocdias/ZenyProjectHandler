"""Independent E12 policy cases over E03 observations, with no benchmark truth input."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationEntry,
    CalibrationPolicy,
    SymbolOccurrence,
    reconcile_symbols,
)
from zeny_project_handler.domain.analysis import OrigemObjetoPdf
from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.enums import (
    EstadoMetodoSimbolos,
    SituacaoProjeto,
    TipoGeometria,
    TipoOrigemPdf,
)
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

CLASSES = ("ATERRAMENTO", "ESTAI", "PARA_RAIOS", "TRANSFORMADOR", "TR_ID_1", "TR_ID_2")


def _profile(name: str, *, family: str | None = None, variant: int = 1) -> PerfilMetodoSimbolos:
    return PerfilMetodoSimbolos(
        metodo_id=name,
        versao="1",
        familia=family or name,
        dominio_aplicacao="desenho e legenda",
        classes_suportadas=CLASSES,
        camadas_suportadas=("base", "anotacao"),
        fontes_compartilhadas=(f"fonte-{family or name}",),
        perfil_referencia="fixture-e12",
        parametros=(("variant", variant),),
    )


def _source(*, page: int = 1, layer: str = "base", document: str = "doc") -> FonteObservacaoSimbolo:
    return FonteObservacaoSimbolo(
        documento_id=document,
        documento_sha256="a" * 64,
        pagina_numero=page,
        camada=layer,
        origem_pdf=OrigemObjetoPdf(),
    )


def _point(value: str | float | Decimal) -> Decimal:
    return Decimal(str(value))


def _observation(
    profile: PerfilMetodoSimbolos,
    class_code: str,
    *,
    x: str = "0.10",
    y: str = "0.10",
    width: str = "0.08",
    height: str = "0.08",
    page: int = 1,
    layer: str = "base",
    document: str = "doc",
    primitive: str | None = "drawing:1",
    raw_score: str = "0.20",
    alternatives: tuple[str, ...] = (),
    attributes: ExtraAttributes = (),
    situation: SituacaoProjeto | None = None,
) -> ObservacaoSimbolo:
    left, top = _point(x), _point(y)
    right, bottom = left + _point(width), top + _point(height)
    original = ((left * 1000, top * 1000), (right * 1000, bottom * 1000))
    return ObservacaoSimbolo(
        fonte=_source(page=page, layer=layer, document=document),
        metodo_assinatura=profile.assinatura(),
        geometria=GeometriaObservacaoSimbolo(
            tipo=TipoGeometria.CAIXA,
            pontos_originais=original,
            pontos_normalizados=(PontoNormalizado(left, top), PontoNormalizado(right, bottom)),
            transformacao=TransformacaoSimbolo(
                normalizada_para_original=(
                    Decimal(1000),
                    Decimal(0),
                    Decimal(0),
                    Decimal(1000),
                    Decimal(0),
                    Decimal(0),
                ),
                sistema_original="fixture-pdf-points",
            ),
        ),
        alternativas=tuple(
            AlternativaClasseSimbolo(classe=code, score_bruto=_point(raw_score))
            for code in (class_code, *alternatives)
        ),
        score_bruto=_point(raw_score),
        situacao=situation,
        primitivas=(
            PrimitivaObservadaSimbolo(indice=primitive, camada="rede", pontos_originais=original),
        )
        if primitive is not None
        else (),
        atributos=attributes,
    )


def _result(
    profile: PerfilMetodoSimbolos,
    *observations: ObservacaoSimbolo,
    state: EstadoMetodoSimbolos = EstadoMetodoSimbolos.CONCLUIDO,
    page: int = 1,
    layer: str = "base",
    document: str = "doc",
) -> ResultadoMetodoSimbolos:
    sources = {item.fonte for item in observations} or {
        _source(page=page, layer=layer, document=document)
    }
    return ResultadoMetodoSimbolos(
        perfil=profile,
        coberturas=tuple(
            CoberturaMetodoSimbolos(
                fonte=source,
                regiao_normalizada=(
                    PontoNormalizado(Decimal(0), Decimal(0)),
                    PontoNormalizado(Decimal(1), Decimal(1)),
                ),
                classes_avaliadas=profile.classes_suportadas,
                estado=state,
                motivo="estado registrado na fixture"
                if state is not EstadoMetodoSimbolos.CONCLUIDO
                else None,
            )
            for source in sorted(
                sources, key=lambda item: (item.documento_id, item.pagina_numero, item.camada)
            )
        ),
        observacoes=observations,
    )


def _policy(*entries: tuple[PerfilMetodoSimbolos, str, str, int]) -> CalibrationPolicy:
    return CalibrationPolicy(
        entries=tuple(
            CalibrationEntry(
                method_signature=profile.assinatura(),
                class_code=class_code,
                stratum="default",
                probability=Decimal(probability),
                sample_size=sample_size,
            )
            for profile, class_code, probability, sample_size in entries
        )
    )


def _classes(occurrence: SymbolOccurrence) -> set[str]:
    return {item.classe for item in occurrence.alternatives if item.classe is not None}


def _ids(occurrence: SymbolOccurrence) -> set[str]:
    return {item.id for item in occurrence.observations}


def test_calibrated_exclusive_can_be_eligible_despite_silent_methods_and_low_raw_score() -> None:
    a, b, c = _profile("A"), _profile("B"), _profile("C")
    correct = _observation(a, "TRANSFORMADOR", raw_score="0.04")
    composed = reconcile_symbols(
        (
            _result(a, correct),
            _result(b, state=EstadoMetodoSimbolos.NAO_DETECCAO),
            _result(c, state=EstadoMetodoSimbolos.ABSTENCAO),
        ),
        _policy((a, "TRANSFORMADOR", "0.995", 80)),
    )
    assert len(composed.occurrences) == 1
    occurrence = composed.occurrences[0]
    assert _ids(occurrence) == {correct.id}
    assert occurrence.decision == "eligible"
    assert occurrence.calibrated_probability == Decimal("0.995")
    assert occurrence.raw_scores == ((a.assinatura(), Decimal("0.04")),)
    assert occurrence.support == (a.assinatura(),)
    states = {row.method_signature: row.state for row in composed.method_matrix}
    assert states[a.assinatura()] == "support"
    assert states[b.assinatura()] == "non_detection"
    assert states[c.assinatura()] == "abstention"


def test_disjoint_valid_exclusives_survive_union_and_shared_detection_is_one_occurrence() -> None:
    a, b = _profile("A"), _profile("B")
    only_a = _observation(a, "TRANSFORMADOR", x="0.10", primitive="drawing:1")
    shared_a = _observation(a, "ESTAI", x="0.40", primitive="drawing:2")
    only_b = _observation(b, "ATERRAMENTO", x="0.70", primitive="drawing:3")
    shared_b = _observation(b, "ESTAI", x="0.40", primitive="drawing:2")
    composed = reconcile_symbols(
        (_result(a, only_a, shared_a), _result(b, only_b, shared_b)),
        _policy(),
    )
    assert {frozenset(_ids(item)) for item in composed.occurrences} == {
        frozenset((only_a.id,)),
        frozenset((only_b.id,)),
        frozenset((shared_a.id, shared_b.id)),
    }
    assert len(composed.occurrences) == 3
    shared = next(item for item in composed.occurrences if shared_a.id in _ids(item))
    assert shared.geometry in {shared_a.geometria, shared_b.geometria}
    assert len(shared.observations) == 2


def test_incompatible_classes_are_alternatives_and_correlated_majority_cannot_win() -> None:
    variants = tuple(_profile("A", family="one-engine", variant=n) for n in (1, 2, 3))
    b = _profile("B", family="independent")
    wrong = tuple(
        _observation(profile, "ATERRAMENTO", primitive="drawing:9", raw_score="0.98")
        for profile in variants
    )
    correct = _observation(b, "PARA_RAIOS", primitive="drawing:9", raw_score="0.21")
    results = tuple(_result(profile, item) for profile, item in zip(variants, wrong, strict=True))
    composed = reconcile_symbols(
        (*results, _result(b, correct)),
        _policy(
            *((profile, "ATERRAMENTO", "0.20", 90) for profile in variants),
            (b, "PARA_RAIOS", "0.995", 90),
        ),
    )
    assert len(composed.occurrences) == 1
    occurrence = composed.occurrences[0]
    assert _ids(occurrence) == {*(item.id for item in wrong), correct.id}
    assert _classes(occurrence) == {"ATERRAMENTO", "PARA_RAIOS"}
    assert occurrence.decision == "review"
    assert len(occurrence.raw_scores) == 4
    assert occurrence.geometry in {item.geometria for item in (*wrong, correct)}
    states = {row.method_signature: row.state for row in composed.method_matrix}
    assert states[b.assinatura()] in {"support", "conflict"}
    assert all(states[profile.assinatura()] in {"support", "conflict"} for profile in variants)


@pytest.mark.parametrize(
    "state,expected",
    [
        (EstadoMetodoSimbolos.NAO_DETECCAO, "non_detection"),
        (EstadoMetodoSimbolos.FORA_DOMINIO, "not_applicable"),
        (EstadoMetodoSimbolos.FALHA, "failure"),
        (EstadoMetodoSimbolos.INDISPONIVEL, "failure"),
    ],
)
def test_silence_outside_domain_and_failure_do_not_contradict_exclusive(
    state: EstadoMetodoSimbolos, expected: str
) -> None:
    a, b = _profile("A"), _profile("B")
    candidate = _observation(a, "ESTAI", primitive="drawing:1")
    result = reconcile_symbols((_result(a, candidate), _result(b, state=state)), _policy())
    assert len(result.occurrences) == 1
    assert _ids(result.occurrences[0]) == {candidate.id}
    assert result.occurrences[0].decision == "review"  # No calibration sample.
    row = next(row for row in result.method_matrix if row.method_signature == b.assinatura())
    assert row.state == expected


def test_method_without_class_capability_is_not_applicable_to_exclusive() -> None:
    a = _profile("A")
    b = replace(_profile("B"), classes_suportadas=("TRANSFORMADOR",))
    candidate = _observation(a, "ESTAI")
    result = reconcile_symbols((_result(a, candidate), _result(b)), _policy())
    assert len(result.occurrences) == 1
    assert _ids(result.occurrences[0]) == {candidate.id}
    row = next(item for item in result.method_matrix if item.method_signature == b.assinatura())
    assert row.state == "not_applicable"


def test_overlapping_neighbors_are_distinct_when_primitive_identity_differs() -> None:
    a, b = _profile("A"), _profile("B")
    left = _observation(a, "ESTAI", x="0.10", primitive="drawing:left")
    right = _observation(b, "ESTAI", x="0.14", primitive="drawing:right")
    result = reconcile_symbols((_result(a, left), _result(b, right)), _policy())
    assert len(result.occurrences) == 2
    assert {frozenset(_ids(item)) for item in result.occurrences} == {
        frozenset((left.id,)),
        frozenset((right.id,)),
    }


@pytest.mark.parametrize("different", ["page", "layer", "document"])
def test_same_drawing_on_other_page_layer_or_document_is_not_merged(different: str) -> None:
    a, b = _profile("A"), _profile("B")
    first = _observation(a, "ESTAI", primitive="drawing:1")
    second = _observation(
        b,
        "ESTAI",
        primitive="drawing:1",
        page=2 if different == "page" else 1,
        layer="anotacao" if different == "layer" else "base",
        document="other" if different == "document" else "doc",
    )
    result = reconcile_symbols((_result(a, first), _result(b, second)), _policy())
    assert len(result.occurrences) == 2
    assert all(len(item.observations) == 1 for item in result.occurrences)


def test_same_physical_symbol_from_distinct_pdf_objects_can_be_associated() -> None:
    a, b = _profile("A"), _profile("B")
    content = _observation(a, "TRANSFORMADOR", primitive="drawing:1")
    xobject = _observation(b, "TRANSFORMADOR", primitive="drawing:1")
    xobject = replace(
        xobject,
        fonte=replace(
            xobject.fonte,
            origem_pdf=OrigemObjetoPdf(tipo=TipoOrigemPdf.FORM_XOBJECT, numero_objeto=12),
        ),
    )
    result = reconcile_symbols((_result(a, content), _result(b, xobject)), _policy())
    assert len(result.occurrences) == 1
    assert _ids(result.occurrences[0]) == {content.id, xobject.id}


def test_same_primitive_shape_with_method_local_indices_is_one_occurrence() -> None:
    a, b = _profile("A"), _profile("B")
    from_a = _observation(a, "TRANSFORMADOR", primitive="vector:17")
    from_b = _observation(b, "TRANSFORMADOR", primitive="contour:901")
    result = reconcile_symbols((_result(a, from_a), _result(b, from_b)), _policy())
    assert len(result.occurrences) == 1
    assert _ids(result.occurrences[0]) == {from_a.id, from_b.id}


def test_visually_indistinguishable_ids_remain_one_occurrence_with_alternatives() -> None:
    a = _profile("A")
    candidate = _observation(a, "TR_ID_1", alternatives=("TR_ID_2",), primitive="drawing:1")
    result = reconcile_symbols((_result(a, candidate),), _policy((a, "TR_ID_1", "0.999", 100)))
    assert len(result.occurrences) == 1
    occurrence = result.occurrences[0]
    assert _classes(occurrence) == {"TR_ID_1", "TR_ID_2"}
    assert _ids(occurrence) == {candidate.id}
    assert occurrence.decision == "review"


def test_e07_same_shape_variant_collision_keeps_both_reference_ids_unresolved() -> None:
    a, b = _profile("A"), _profile("B")
    from_a = _observation(
        a,
        "TRANSFORMADOR",
        primitive="drawing:1",
        attributes=(("variante_inventario", "cemig-eo-r3-s19-v001"),),
    )
    from_b = _observation(
        b,
        "TRANSFORMADOR",
        primitive="drawing:1",
        attributes=(("variante_inventario", "cemig-eo-r3-s19-v002"),),
    )
    result = reconcile_symbols(
        (_result(a, from_a), _result(b, from_b)),
        _policy((a, "TRANSFORMADOR", "0.995", 90), (b, "TRANSFORMADOR", "0.995", 90)),
    )
    assert len(result.occurrences) == 1
    occurrence = result.occurrences[0]
    assert _ids(occurrence) == {from_a.id, from_b.id}
    assert _classes(occurrence) == {"TRANSFORMADOR"}
    assert occurrence.reference_ids == (
        "cemig-eo-r3-s19-v001",
        "cemig-eo-r3-s19-v002",
    )
    assert occurrence.decision == "review"
    assert "ambiguous_reference_id" in occurrence.reasons


def test_possible_references_json_list_preserves_unresolved_ids_without_variant_field() -> None:
    a = _profile("A")
    candidate = _observation(
        a,
        "TRANSFORMADOR",
        attributes=(("referencias_possiveis", '["id-a", "id-b"]'),),
    )
    result = reconcile_symbols((_result(a, candidate),), _policy((a, "TRANSFORMADOR", "0.999", 90)))
    assert len(result.occurrences) == 1
    occurrence = result.occurrences[0]
    assert _ids(occurrence) == {candidate.id}
    assert occurrence.reference_ids == ("id-a", "id-b")
    assert occurrence.decision == "review"
    assert "ambiguous_reference_id" in occurrence.reasons


@pytest.mark.parametrize("context", ["legenda", "legend"])
def test_legend_reference_stays_review_while_operational_occurrence_can_be_eligible(
    context: str,
) -> None:
    a, b = _profile("A"), _profile("B")
    legend = _observation(
        a,
        "TRANSFORMADOR",
        x="0.10",
        primitive="drawing:1",
        attributes=(("contexto", context),),
    )
    operational = _observation(b, "TRANSFORMADOR", x="0.10", primitive="drawing:1")
    result = reconcile_symbols(
        (_result(a, legend), _result(b, operational)),
        _policy((a, "TRANSFORMADOR", "0.995", 90), (b, "TRANSFORMADOR", "0.995", 90)),
    )
    by_observation = {next(iter(_ids(item))): item for item in result.occurrences}
    assert len(by_observation) == 2
    assert by_observation[legend.id].decision == "review"
    assert by_observation[operational.id].decision == "eligible"


def test_agreeing_detectors_do_not_manufacture_calibrated_probability() -> None:
    a, b = _profile("A"), _profile("B")
    from_a = _observation(a, "TRANSFORMADOR", raw_score="0.99")
    from_b = _observation(b, "TRANSFORMADOR", raw_score="0.01")
    result = reconcile_symbols((_result(a, from_a), _result(b, from_b)), _policy())
    assert len(result.occurrences) == 1
    occurrence = result.occurrences[0]
    assert occurrence.decision == "review"
    assert occurrence.calibrated_probability is None
    assert set(occurrence.raw_scores) == {
        (a.assinatura(), Decimal("0.99")),
        (b.assinatura(), Decimal("0.01")),
    }
    assert set(occurrence.support) == {a.assinatura(), b.assinatura()}


def test_text_power_and_situation_disagreement_remain_unresolved() -> None:
    a, b = _profile("A"), _profile("B")
    from_a = _observation(
        a,
        "TRANSFORMADOR",
        situation=SituacaoProjeto.INSTALAR,
        attributes=(("potencia_kva", 45),),
    )
    from_b = _observation(
        b,
        "TRANSFORMADOR",
        situation=SituacaoProjeto.EXISTENTE,
        attributes=(("potencia_kva", 75),),
    )
    result = reconcile_symbols(
        (_result(a, from_a), _result(b, from_b)),
        _policy((a, "TRANSFORMADOR", "0.995", 90), (b, "TRANSFORMADOR", "0.995", 90)),
    )
    assert len(result.occurrences) == 1
    occurrence = result.occurrences[0]
    assert _ids(occurrence) == {from_a.id, from_b.id}
    assert occurrence.decision == "review"
    assert "situation_conflict" in occurrence.reasons
    assert "attribute_conflict:potencia_kva" in occurrence.reasons


def test_pending_variant_is_not_recognized_by_calibration_alone() -> None:
    a = _profile("A")
    candidate = _observation(a, "TR_ID_1", attributes=(("status", "pending"),))
    result = reconcile_symbols((_result(a, candidate),), _policy((a, "TR_ID_1", "0.999", 90)))
    assert len(result.occurrences) == 1
    assert result.occurrences[0].decision == "review"


def test_e07_informative_role_stays_review_despite_sufficient_calibration() -> None:
    a = _profile("A")
    candidate = _observation(
        a,
        "TRANSFORMADOR",
        attributes=(
            ("variante_inventario", "cemig-eo-r3-s19-informative"),
            ("papel", "informative"),
        ),
    )
    result = reconcile_symbols((_result(a, candidate),), _policy((a, "TRANSFORMADOR", "0.999", 90)))
    assert len(result.occurrences) == 1
    occurrence = result.occurrences[0]
    assert _ids(occurrence) == {candidate.id}
    assert occurrence.reference_ids == ("cemig-eo-r3-s19-informative",)
    assert occurrence.decision == "review"
    assert "informative_context" in occurrence.reasons


def test_insufficient_sample_and_wrong_stratum_do_not_promote_raw_score() -> None:
    a = _profile("A")
    candidate = _observation(a, "TRANSFORMADOR", raw_score="0.999999")
    for policy in (
        _policy(),
        _policy((a, "TRANSFORMADOR", "0.999", 2)),
        CalibrationPolicy(
            entries=(
                CalibrationEntry(
                    method_signature=a.assinatura(),
                    class_code="TRANSFORMADOR",
                    stratum="different-stratum",
                    probability=Decimal("0.999"),
                    sample_size=100,
                ),
            )
        ),
    ):
        result = reconcile_symbols((_result(a, candidate),), policy)
        occurrence = result.occurrences[0]
        assert occurrence.decision == "review"
        assert occurrence.calibrated_probability is None
        assert occurrence.raw_scores == ((a.assinatura(), Decimal("0.999999")),)


def test_ablation_records_unique_contribution_without_erasing_other_method() -> None:
    a, b = _profile("A"), _profile("B")
    only_a = _observation(a, "ESTAI", x="0.10", primitive="drawing:1")
    only_b = _observation(b, "TRANSFORMADOR", x="0.70", primitive="drawing:2")
    result = reconcile_symbols(
        (_result(a, only_a), _result(b, only_b)),
        _policy((a, "ESTAI", "0.995", 90), (b, "TRANSFORMADOR", "0.995", 90)),
    )
    before = {next(iter(_ids(item))): item.id for item in result.occurrences}
    ablations = {item.method_signature: item for item in result.ablations}
    assert set(ablations) == {a.assinatura(), b.assinatura()}
    assert before[only_a.id] in ablations[a.assinatura()].lost_occurrence_ids
    assert before[only_b.id] not in ablations[a.assinatura()].lost_occurrence_ids
    assert before[only_b.id] in ablations[b.assinatura()].lost_occurrence_ids
    assert before[only_a.id] not in ablations[b.assinatura()].lost_occurrence_ids
    assert ablations[a.assinatura()].eligible_before == 2
    assert ablations[a.assinatura()].eligible_after == 1
    assert ablations[b.assinatura()].eligible_before == 2
    assert ablations[b.assinatura()].eligible_after == 1
