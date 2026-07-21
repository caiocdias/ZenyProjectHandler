from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoAnotacao,
    EstadoConjuntoAvaliacao,
    EstadoCriteriosAvaliacao,
    PapelAnotacao,
    ParticaoAvaliacao,
    SituacaoProjeto,
    TipoGeometria,
)
from zeny_project_handler.domain.evaluation import (
    AmostraAvaliacao,
    AnotacaoAmostra,
    CriteriosRegressaoAvaliacao,
    GeometriaAvaliacao,
    LimiteCategoriaAvaliacao,
    ManifestoAvaliacao,
    RotuloElementoAvaliacao,
    RotuloRelacaoAvaliacao,
)
from zeny_project_handler.domain.values import PontoNormalizado

FIXED_TIME = datetime(2026, 7, 21, tzinfo=UTC)


def make_sample(
    *,
    sample_id: str = "amostra-001",
    digest: str = "a" * 64,
    partition: ParticaoAvaliacao = ParticaoAvaliacao.TESTE,
    double_annotation: bool = False,
) -> AmostraAvaliacao:
    return AmostraAvaliacao(
        id=sample_id,
        sha256=digest,
        tamanho_bytes=10,
        total_paginas=1,
        particao=partition,
        escala="1:1000",
        formato="A4",
        orientacao="RETRATO",
        qualidade="NATIVO",
        densidade="MEDIA",
        dupla_anotacao=double_annotation,
    )


def make_manifest(
    *,
    test_sample: AmostraAvaliacao | None = None,
    state: EstadoConjuntoAvaliacao = EstadoConjuntoAvaliacao.CONGELADO,
) -> ManifestoAvaliacao:
    development = make_sample(
        sample_id="amostra-dev",
        digest="b" * 64,
        partition=ParticaoAvaliacao.DESENVOLVIMENTO,
    )
    sample = test_sample or make_sample()
    return ManifestoAvaliacao(
        schema_version=1,
        conjunto_id="conjunto-teste",
        versao="1.0",
        estado=state,
        politica_acesso="privada",
        criado_em=FIXED_TIME,
        congelado_em=FIXED_TIME if state is EstadoConjuntoAvaliacao.CONGELADO else None,
        amostras=(development, sample),
    )


def make_criteria(
    *, state: EstadoCriteriosAvaliacao = EstadoCriteriosAvaliacao.APROVADO
) -> CriteriosRegressaoAvaliacao:
    return CriteriosRegressaoAvaliacao(
        schema_version=1,
        versao="1.0",
        estado=state,
        limites_categoria=tuple(
            LimiteCategoriaAvaliacao(
                categoria=category,
                precisao_minima=Decimal("0.8"),
                recall_minimo=Decimal("0.8"),
            )
            for category in CategoriaElemento
        ),
        precisao_relacoes_minima=Decimal("0.8"),
        recall_relacoes_minimo=Decimal("0.8"),
        taxa_falhas_extracao_maxima=Decimal("0.05"),
        latencia_p95_ms_maxima=Decimal("30000"),
        memoria_python_pico_bytes_maxima=1024 * 1024 * 1024,
        divergencia_humana_maxima=Decimal("0.15"),
        tolerancia_ponto=Decimal("0.02"),
        tolerancia_polilinha=Decimal("0.02"),
        iou_area_minimo=Decimal("0.5"),
    )


def make_element(
    *,
    element_id: str = "poste-001",
    category: CategoriaElemento = CategoriaElemento.POSTE,
    situation: SituacaoProjeto = SituacaoProjeto.EXISTENTE,
    x: str = "0.25",
    y: str = "0.50",
) -> RotuloElementoAvaliacao:
    return RotuloElementoAvaliacao(
        id=element_id,
        categoria=category,
        situacao=situation,
        geometria=GeometriaAvaliacao(
            pagina_numero=1,
            tipo=TipoGeometria.PONTO,
            pontos=(PontoNormalizado(Decimal(x), Decimal(y)),),
        ),
    )


def make_relation(
    *,
    relation_id: str = "relacao-001",
    source_id: str = "poste-001",
    target_id: str = "equipamento-001",
) -> RotuloRelacaoAvaliacao:
    return RotuloRelacaoAvaliacao(
        id=relation_id,
        origem_id=source_id,
        destino_id=target_id,
        tipo_relacao="SUPORTA",
    )


def make_annotation(
    *,
    sample: AmostraAvaliacao | None = None,
    role: PapelAnotacao = PapelAnotacao.CONSENSO,
    annotator_id: str = "anotador-01",
    elements: tuple[RotuloElementoAvaliacao, ...] | None = None,
    relations: tuple[RotuloRelacaoAvaliacao, ...] = (),
) -> AnotacaoAmostra:
    selected_sample = sample or make_sample()
    selected_elements = elements or (make_element(),)
    frozen = role is PapelAnotacao.CONSENSO
    return AnotacaoAmostra(
        schema_version=1,
        id=f"anotacao-{role.value.lower()}",
        conjunto_id="conjunto-teste",
        conjunto_versao="1.0",
        amostra_id=selected_sample.id,
        documento_sha256=selected_sample.sha256,
        papel=role,
        estado=EstadoAnotacao.CONGELADA if frozen else EstadoAnotacao.REVISADA,
        anotador_id=annotator_id,
        criada_em=FIXED_TIME,
        revisada_em=FIXED_TIME,
        revisor_id="revisor-01",
        elementos=selected_elements,
        relacoes=relations,
    )
