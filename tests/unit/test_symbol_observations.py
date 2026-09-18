"""Contrato E03: procedência, scores brutos e silêncio sem evidência negativa."""

from dataclasses import replace
from decimal import Decimal

import pytest

from zeny_project_handler.adapters.persistence.domain_json import dumps_domain, loads_domain
from zeny_project_handler.domain.analysis import OrigemObjetoPdf
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, TipoGeometria, TipoOrigemPdf
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    FonteObservacaoSimbolo,
    GeometriaObservacaoSimbolo,
    HipoteseSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    PrimitivaObservadaSimbolo,
    RegistroMetodosSimbolos,
    ResultadoMetodoSimbolos,
    TransformacaoSimbolo,
)
from zeny_project_handler.domain.values import PontoNormalizado


def _profile() -> PerfilMetodoSimbolos:
    return PerfilMetodoSimbolos(
        metodo_id="motor-autoral",
        versao="1.2",
        familia="formas",
        dominio_aplicacao="vetores e recortes do desenho",
        classes_suportadas=("ESTAI", "SIMBOLO_INFORMATIVO"),
        camadas_suportadas=("base", "anotacao"),
        fontes_compartilhadas=("recorte-fonte-v1",),
        perfil_referencia="perfil-autoral@3",
        parametros=(("dpi", 144), ("limiar", Decimal("-2.50"))),
        modelo="modelo@7:sha256:autoral",
        template="template@4:sha256:autoral",
    )


def _observation(profile: PerfilMetodoSimbolos | None = None) -> ObservacaoSimbolo:
    selected = profile or _profile()
    return ObservacaoSimbolo(
        fonte=FonteObservacaoSimbolo(
            documento_id="documento-autoral",
            documento_sha256="a" * 64,
            pagina_numero=2,
            camada="anotacao",
            origem_pdf=OrigemObjetoPdf(
                tipo=TipoOrigemPdf.APARENCIA_ANOTACAO,
                numero_objeto=42,
                indice_anotacao=3,
                subtipo_anotacao="Stamp",
                nome_recurso="Fm2",
            ),
        ),
        metodo_assinatura=selected.assinatura(),
        geometria=GeometriaObservacaoSimbolo(
            tipo=TipoGeometria.CAIXA,
            pontos_originais=((Decimal("110"), Decimal("220")), (Decimal("210"), Decimal("420"))),
            pontos_normalizados=(
                PontoNormalizado(Decimal("0.1"), Decimal("0.1")),
                PontoNormalizado(Decimal("0.2"), Decimal("0.2")),
            ),
            transformacao=TransformacaoSimbolo(
                normalizada_para_original=(
                    Decimal(1000),
                    Decimal(0),
                    Decimal(0),
                    Decimal(2000),
                    Decimal(10),
                    Decimal(20),
                ),
                sistema_original="pdf-points-cropbox",
            ),
        ),
        alternativas=(
            AlternativaClasseSimbolo(
                classe="ESTAI", subtipo="ancora", score_bruto=Decimal("-3.1250")
            ),
            AlternativaClasseSimbolo(classe="SIMBOLO_INFORMATIVO", score_bruto=Decimal("12.00")),
            AlternativaClasseSimbolo(),
        ),
        score_bruto=Decimal("-3.1250"),
        primitivas=(
            PrimitivaObservadaSimbolo(
                indice="drawing:19",
                camada="Rede MT",
                pontos_originais=((Decimal(110), Decimal(220)), (Decimal(210), Decimal(420))),
            ),
        ),
        raster_sha256="b" * 64,
        modelo=selected.modelo,
        template=selected.template,
        atributos=(("origem", "teste autoral"), ("escala", Decimal("1.250"))),
        chave_legada="pagina:2:primitive:19",
        conteudo_bruto="símbolo sem catálogo",
    )


def _coverage(
    observation: ObservacaoSimbolo, state: EstadoMetodoSimbolos
) -> CoberturaMetodoSimbolos:
    return CoberturaMetodoSimbolos(
        fonte=observation.fonte,
        regiao_normalizada=(
            PontoNormalizado(Decimal(0), Decimal(0)),
            PontoNormalizado(Decimal(1), Decimal(1)),
        ),
        classes_avaliadas=("ESTAI", "SIMBOLO_INFORMATIVO"),
        estado=state,
        motivo="estado registrado pelo motor",
    )


def test_observation_round_trip_preserves_all_provenance_and_raw_geometry() -> None:
    observation = _observation()
    restored = loads_domain(dumps_domain(observation), ObservacaoSimbolo)

    assert restored == observation
    assert restored.id == observation.id
    assert restored.fonte.documento_sha256 == "a" * 64
    assert restored.fonte.pagina_numero == 2
    assert restored.fonte.camada == "anotacao"
    assert restored.fonte.origem_pdf.numero_objeto == 42
    assert restored.primitivas[0].camada == "Rede MT"
    assert restored.raster_sha256 == "b" * 64
    assert restored.geometria.transformacao.sistema_original == "pdf-points-cropbox"
    a, b, c, d, e, f = restored.geometria.transformacao.normalizada_para_original
    for point, original in zip(
        restored.geometria.pontos_normalizados, restored.geometria.pontos_originais, strict=True
    ):
        assert (a * point.x + c * point.y + e, b * point.x + d * point.y + f) == original
    assert str(restored.score_bruto) == "-3.1250"
    assert str(restored.alternativas[1].score_bruto) == "12.00"
    assert restored.alternativas[2].classe is None
    assert restored.situacao is None
    assert dumps_domain(restored) == dumps_domain(observation)


@pytest.mark.parametrize("score", [Decimal("-12345.1250"), Decimal("4.20"), Decimal("0.001")])
def test_raw_scores_do_not_become_probabilities(score: Decimal) -> None:
    observation = replace(_observation(), score_bruto=score)
    restored = loads_domain(dumps_domain(observation), ObservacaoSimbolo)
    assert restored.score_bruto == score
    assert str(restored.score_bruto) == str(score)


@pytest.mark.parametrize("score", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_nonfinite_raw_scores_are_rejected(score: Decimal) -> None:
    with pytest.raises(DomainValidationError, match="finito"):
        replace(_observation(), score_bruto=score)
    with pytest.raises(DomainValidationError, match="finito"):
        AlternativaClasseSimbolo(classe="ESTAI", score_bruto=score)


def test_method_signature_covers_version_model_template_profile_and_configuration() -> None:
    profile = _profile()
    variants = (
        profile,
        replace(profile, versao="1.3"),
        replace(profile, modelo="modelo@8"),
        replace(profile, template="template@5"),
        replace(profile, perfil_referencia="perfil-autoral@4"),
        replace(profile, parametros=(("dpi", 300),)),
        replace(profile, classes_suportadas=("ESTAI",)),
        replace(profile, camadas_suportadas=("base",)),
    )
    assert len({variant.assinatura() for variant in variants}) == len(variants)
    assert len({_observation(variant).id for variant in variants}) == len(variants)
    reordered = replace(
        profile,
        parametros=tuple(reversed(profile.parametros)),
        classes_suportadas=tuple(reversed(profile.classes_suportadas)),
    )
    assert reordered.assinatura() == profile.assinatura()
    assert _observation(reordered).id == _observation(profile).id


def test_signature_preserves_parameter_types() -> None:
    variants = tuple(
        replace(_profile(), parametros=(("threshold", value),))
        for value in (Decimal("1"), "1", 1, True, None)
    )
    assert len({variant.assinatura() for variant in variants}) == 5


def test_identity_distinguishes_source_page_layer_and_primitive_provenance() -> None:
    original = _observation()
    variants = (
        original,
        replace(original, fonte=replace(original.fonte, documento_sha256="c" * 64)),
        replace(original, fonte=replace(original.fonte, documento_id="outro-documento")),
        replace(original, fonte=replace(original.fonte, pagina_numero=3)),
        replace(original, fonte=replace(original.fonte, camada="base")),
        replace(original, primitivas=(replace(original.primitivas[0], indice="drawing:20"),)),
        replace(
            original,
            geometria=replace(
                original.geometria,
                pontos_originais=(
                    (Decimal(111), Decimal(220)),
                    (Decimal(211), Decimal(420)),
                ),
            ),
        ),
    )
    assert len({variant.id for variant in variants}) == len(variants)
    assert original.id == _observation().id
    hypothesis = HipoteseSimbolo(
        hipotese_id="ocorrencia-fisica-revisada-42", observacoes_ids=(original.id, variants[-1].id)
    )
    assert hypothesis.hipotese_id not in hypothesis.observacoes_ids
    assert loads_domain(dumps_domain(hypothesis), HipoteseSimbolo) == hypothesis


def test_registry_preserves_correlated_variants_without_claiming_independence() -> None:
    original = _profile()
    same_family = replace(original, parametros=(("dpi", 300),), fontes_compartilhadas=())
    shared_source = replace(original, metodo_id="outro", familia="rede-treinada")
    undeclared = replace(shared_source, fontes_compartilhadas=())
    assert original.possui_origem_correlacionada(same_family)
    assert original.possui_origem_correlacionada(shared_source)
    assert not original.possui_origem_correlacionada(undeclared)
    registry = RegistroMetodosSimbolos(metodos=(original, same_family, shared_source, undeclared))
    restored = loads_domain(dumps_domain(registry), RegistroMetodosSimbolos)
    assert restored == registry
    assert len(restored.metodos) == 4
    assert restored.obter(same_family.assinatura()) == same_family
    assert RegistroMetodosSimbolos(metodos=tuple(reversed(registry.metodos))).assinatura() == (
        registry.assinatura()
    )
    with pytest.raises(DomainValidationError, match="registrado"):
        RegistroMetodosSimbolos(metodos=(original, original))
    with pytest.raises(KeyError):
        registry.obter("f" * 64)


@pytest.mark.parametrize("state", tuple(EstadoMetodoSimbolos))
def test_method_silence_never_erases_an_exclusive_observation(state: EstadoMetodoSimbolos) -> None:
    observation = _observation()
    successful = ResultadoMetodoSimbolos(
        perfil=_profile(),
        coberturas=(_coverage(observation, EstadoMetodoSimbolos.CONCLUIDO),),
        observacoes=(observation,),
    )
    silent = ResultadoMetodoSimbolos(
        perfil=replace(_profile(), metodo_id="motor-silencioso"),
        coberturas=(_coverage(observation, state),),
    )
    restored = loads_domain(dumps_domain((successful, silent)), tuple)
    assert restored[0].observacoes == (observation,)
    assert restored[1].observacoes == ()
    assert restored[1].coberturas[0].estado is state
    assert not restored[1].coberturas[0].estado.comprova_ausencia
    assert restored[0].observacoes[0].score_bruto == Decimal("-3.1250")


def test_failure_preserves_partial_evidence_and_is_not_complete() -> None:
    observation = _observation()
    partial = ResultadoMetodoSimbolos(
        perfil=_profile(),
        coberturas=(_coverage(observation, EstadoMetodoSimbolos.FALHA),),
        observacoes=(observation,),
    )
    restored = loads_domain(dumps_domain(partial), ResultadoMetodoSimbolos)
    assert restored.observacoes == (observation,)
    assert not restored.completo


@pytest.mark.parametrize(
    "state",
    [
        EstadoMetodoSimbolos.FORA_DOMINIO,
        EstadoMetodoSimbolos.INDISPONIVEL,
        EstadoMetodoSimbolos.ABSTENCAO,
        EstadoMetodoSimbolos.NAO_DETECCAO,
    ],
)
def test_nonexecuted_coverage_cannot_claim_a_detection(state: EstadoMetodoSimbolos) -> None:
    observation = _observation()
    with pytest.raises(DomainValidationError, match="cobertura executada"):
        ResultadoMetodoSimbolos(
            perfil=_profile(),
            coberturas=(_coverage(observation, state),),
            observacoes=(observation,),
        )


def test_result_rejects_mismatched_method_source_and_duplicate_observations() -> None:
    observation = _observation()
    coverage = _coverage(observation, EstadoMetodoSimbolos.CONCLUIDO)
    with pytest.raises(DomainValidationError, match="Assinatura"):
        ResultadoMetodoSimbolos(
            perfil=replace(_profile(), versao="2"),
            coberturas=(coverage,),
            observacoes=(observation,),
        )
    with pytest.raises(DomainValidationError, match="mesma fonte"):
        ResultadoMetodoSimbolos(
            perfil=_profile(),
            observacoes=(observation,),
            coberturas=(replace(coverage, fonte=replace(coverage.fonte, pagina_numero=3)),),
        )
    with pytest.raises(DomainValidationError, match="duplicadas"):
        ResultadoMetodoSimbolos(
            perfil=_profile(), coberturas=(coverage,), observacoes=(observation, observation)
        )


def test_clipped_and_degenerate_geometry_is_preserved_without_repair() -> None:
    original = _observation()
    geometry = replace(
        original.geometria,
        pontos_originais=((Decimal(-10), Decimal(200)), (Decimal(-10), Decimal(240))),
        pontos_normalizados=(
            PontoNormalizado(Decimal(0), Decimal("0.1")),
            PontoNormalizado(Decimal(0), Decimal("0.11")),
        ),
        normalizacao_limitada=True,
    )
    restored = loads_domain(dumps_domain(replace(original, geometria=geometry)), ObservacaoSimbolo)
    assert restored.geometria == geometry
    assert restored.geometria.normalizacao_limitada
    assert restored.geometria.pontos_originais[0][0] == Decimal(-10)
    assert (
        restored.geometria.pontos_normalizados[0].x == restored.geometria.pontos_normalizados[1].x
    )


def test_coverage_rejects_unsupported_executed_class_and_layer() -> None:
    observation = _observation()
    coverage = _coverage(observation, EstadoMetodoSimbolos.CONCLUIDO)
    invalid = (
        replace(coverage, classes_avaliadas=("TRANSFORMADOR",)),
        replace(coverage, fonte=replace(coverage.fonte, camada="nao-suportada")),
    )
    for item in invalid:
        with pytest.raises(DomainValidationError, match="capacidades declaradas"):
            ResultadoMetodoSimbolos(perfil=_profile(), coberturas=(item,))
        unavailable = replace(
            item, estado=EstadoMetodoSimbolos.FORA_DOMINIO, motivo="classe ou camada não suportada"
        )
        result = ResultadoMetodoSimbolos(perfil=_profile(), coberturas=(unavailable,))
        assert not result.coberturas[0].estado.comprova_ausencia


def test_detection_requires_its_region_and_classes_to_have_been_evaluated() -> None:
    observation = _observation()
    coverage = _coverage(observation, EstadoMetodoSimbolos.CONCLUIDO)
    invalid = (
        replace(coverage, classes_avaliadas=("ESTAI",)),
        replace(
            coverage,
            regiao_normalizada=(
                PontoNormalizado(Decimal("0.5"), Decimal("0.5")),
                PontoNormalizado(Decimal(1), Decimal(1)),
            ),
        ),
    )
    for item in invalid:
        with pytest.raises(DomainValidationError, match="cobertura executada"):
            ResultadoMetodoSimbolos(
                perfil=_profile(), coberturas=(item,), observacoes=(observation,)
            )
    with pytest.raises(DomainValidationError, match="contradiz"):
        ResultadoMetodoSimbolos(
            perfil=_profile(),
            observacoes=(observation,),
            coberturas=(coverage, replace(coverage, estado=EstadoMetodoSimbolos.NAO_DETECCAO)),
        )
