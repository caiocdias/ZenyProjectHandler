from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from zeny_project_handler.application.analysis_regions import agrupar_regioes_da_analise
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
)
from zeny_project_handler.domain.values import (
    CaixaPagina,
    GeometriaDocumento,
    PontoNormalizado,
)


def _document(page_id: UUID) -> DocumentoProjeto:
    page = PaginaDocumento(
        id=page_id,
        numero=1,
        largura_pontos=Decimal(1000),
        altura_pontos=Decimal(700),
        rotacao_graus=0,
        media_box=CaixaPagina(Decimal(0), Decimal(0), Decimal(1000), Decimal(700)),
        crop_box=CaixaPagina(Decimal(0), Decimal(0), Decimal(1000), Decimal(700)),
    )
    return DocumentoProjeto(
        id=uuid4(),
        nome_arquivo="regioes.pdf",
        sha256="a" * 64,
        paginas=(page,),
    )


def _element(
    execution_id: UUID,
    evidence_id: UUID,
    page_id: UUID,
    *,
    category: CategoriaElemento,
    situation: SituacaoProjeto,
    code: str,
    x: str,
    y: str,
) -> PropostaElemento:
    return PropostaElemento(
        id=uuid4(),
        execucao_id=execution_id,
        categoria=category,
        situacao_projeto=situation,
        estado_revisao=EstadoRevisao.CONFIRMADA,
        evidencia_ids=(evidence_id,),
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal(x), Decimal(y)),
        ),
        codigo_observado=code,
        confianca=Decimal("0.90"),
    )


@pytest.mark.parametrize(
    ("kind", "coordinate_text"),
    [
        (TipoEvidencia.TEXTO, "0280653\n7683008"),
        (TipoEvidencia.TEXTO, "0280653:7683008"),
        (TipoEvidencia.OCR, "0280653/7683008"),
    ],
)
def test_groups_occurrences_by_pdf_region_and_reads_coordinate_variants(
    kind: TipoEvidencia,
    coordinate_text: str,
) -> None:
    page_id = uuid4()
    execution_id = uuid4()
    evidence_id = uuid4()
    coordinate_evidence = EvidenciaDocumento(
        id=evidence_id,
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=kind,
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal("0.18"), Decimal("0.24")),
        ),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto=coordinate_text,
        criada_em=datetime(2026, 7, 22, tzinfo=UTC),
    )
    removed_pole = _element(
        execution_id,
        evidence_id,
        page_id,
        category=CategoriaElemento.POSTE,
        situation=SituacaoProjeto.REMOVER,
        code="10-150",
        x="0.15",
        y="0.15",
    )
    installed_pole = _element(
        execution_id,
        evidence_id,
        page_id,
        category=CategoriaElemento.POSTE,
        situation=SituacaoProjeto.INSTALAR,
        code="11-300",
        x="0.18",
        y="0.18",
    )
    transformer = _element(
        execution_id,
        evidence_id,
        page_id,
        category=CategoriaElemento.EQUIPAMENTO,
        situation=SituacaoProjeto.INSTALAR,
        code="-1-10",
        x="0.21",
        y="0.20",
    )
    distant_existing_pole = _element(
        execution_id,
        evidence_id,
        page_id,
        category=CategoriaElemento.POSTE,
        situation=SituacaoProjeto.EXISTENTE,
        code="10-300",
        x="0.80",
        y="0.75",
    )
    relation = PropostaRelacao(
        id=uuid4(),
        execucao_id=execution_id,
        origem_referencia_id=transformer.id,
        destino_referencia_id=installed_pole.id,
        tipo_relacao="INSTALADO_EM",
        evidencia_ids=(evidence_id,),
        estado_revisao=EstadoRevisao.CONFIRMADA,
        confianca=Decimal("0.85"),
    )

    regions = agrupar_regioes_da_analise(
        (removed_pole, installed_pole, transformer, distant_existing_pole, relation),
        (coordinate_evidence,),
        (_document(page_id),),
    )

    assert len(regions) == 2
    occurrence, existing = regions
    assert set(occurrence.elemento_ids) == {
        removed_pole.id,
        installed_pole.id,
        transformer.id,
    }
    assert occurrence.vinculo_ids == (relation.id,)
    assert occurrence.coordenada is not None
    assert occurrence.coordenada.leste == Decimal(280653)
    assert occurrence.coordenada.norte == Decimal(7683008)
    assert existing.elemento_ids == (distant_existing_pole.id,)
    assert existing.coordenada is None


def test_distinct_point_labels_prevent_nearby_occurrences_from_merging() -> None:
    page_id = uuid4()
    execution_id = uuid4()
    created_at = datetime(2026, 7, 23, tzinfo=UTC)

    def point_evidence(text: str, x: str, y: str) -> EvidenciaDocumento:
        return EvidenciaDocumento(
            id=uuid4(),
            execucao_id=execution_id,
            pagina_id=page_id,
            tipo=TipoEvidencia.TEXTO,
            geometria=GeometriaDocumento.ponto(
                page_id,
                PontoNormalizado(Decimal(x), Decimal(y)),
            ),
            metodo="fixture",
            versao_metodo="1",
            parametros=(),
            conteudo_bruto=text,
            criada_em=created_at,
        )

    p5_anchor = point_evidence("P5", "0.40", "0.18")
    p4_anchor = point_evidence("P4", "0.40", "0.32")
    explanatory_text = point_evidence(
        "TRAFO REALOCADO NO PONTO P5",
        "0.58",
        "0.31",
    )
    p5_removed_pole = _element(
        execution_id,
        p5_anchor.id,
        page_id,
        category=CategoriaElemento.POSTE,
        situation=SituacaoProjeto.REMOVER,
        code="10-300",
        x="0.40",
        y="0.21",
    )
    p5_installed_pole = _element(
        execution_id,
        p5_anchor.id,
        page_id,
        category=CategoriaElemento.POSTE,
        situation=SituacaoProjeto.INSTALAR,
        code="11-300",
        x="0.42",
        y="0.23",
    )
    p4_existing_pole = _element(
        execution_id,
        p4_anchor.id,
        page_id,
        category=CategoriaElemento.POSTE,
        situation=SituacaoProjeto.EXISTENTE,
        code="10-150",
        x="0.40",
        y="0.29",
    )
    p4_transformer = _element(
        execution_id,
        p4_anchor.id,
        page_id,
        category=CategoriaElemento.EQUIPAMENTO,
        situation=SituacaoProjeto.INSTALAR,
        code="TR-37",
        x="0.42",
        y="0.31",
    )

    regions = agrupar_regioes_da_analise(
        (
            p5_removed_pole,
            p5_installed_pole,
            p4_existing_pole,
            p4_transformer,
        ),
        (p5_anchor, p4_anchor, explanatory_text),
        (_document(page_id),),
    )

    assert len(regions) == 2
    by_label = {region.rotulo_ponto: set(region.elemento_ids) for region in regions}
    assert by_label == {
        "P5": {p5_removed_pole.id, p5_installed_pole.id},
        "P4": {p4_existing_pole.id, p4_transformer.id},
    }


def test_distant_unlabeled_structure_is_not_absorbed_by_labeled_point_region() -> None:
    page_id = uuid4()
    execution_id = uuid4()
    anchor = EvidenciaDocumento(
        id=uuid4(),
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=TipoEvidencia.OCR,
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal("0.40"), Decimal("0.18")),
        ),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto="P12",
        criada_em=datetime(2026, 7, 25, tzinfo=UTC),
    )
    p12_pole = replace(
        _element(
            execution_id,
            anchor.id,
            page_id,
            category=CategoriaElemento.POSTE,
            situation=SituacaoProjeto.EXISTENTE,
            code="11-300",
            x="0.40",
            y="0.13",
        ),
        atributos_sugeridos=(("identificador_operacional", "P12"),),
    )
    remote_u1 = _element(
        execution_id,
        uuid4(),
        page_id,
        category=CategoriaElemento.ESTRUTURA_MT,
        situation=SituacaoProjeto.EXISTENTE,
        code="U1",
        x="0.40",
        y="0.05",
    )

    regions = agrupar_regioes_da_analise(
        (p12_pole, remote_u1),
        (anchor,),
        (_document(page_id),),
    )

    assert len(regions) == 2
    p12_region = next(region for region in regions if region.rotulo_ponto == "P12")
    unlabeled_region = next(region for region in regions if region.rotulo_ponto is None)
    assert p12_region.elemento_ids == (p12_pole.id,)
    assert unlabeled_region.elemento_ids == (remote_u1.id,)


def test_preserves_recognized_point_without_associated_elements() -> None:
    page_id = uuid4()
    execution_id = uuid4()
    p11_anchor = EvidenciaDocumento(
        id=uuid4(),
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=TipoEvidencia.OCR,
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal("0.44"), Decimal("0.52")),
        ),
        metodo="tesseract-identificador",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto="P11",
        criada_em=datetime(2026, 7, 24, tzinfo=UTC),
    )

    regions = agrupar_regioes_da_analise(
        (),
        (p11_anchor,),
        (_document(page_id),),
    )

    assert len(regions) == 1
    assert regions[0].rotulo_ponto == "P11"
    assert regions[0].elemento_ids == ()
    assert regions[0].geometria == p11_anchor.geometria
