from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from tests.interpretation_factories import image_evidence, text_evidence, vector_evidence

from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.interpretation.rule_based import AnalisadorEstruturaMt
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
    TipoGeometria,
)
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao


class FailingPoleAnalyzer:
    nome = "poste-failure"
    versao = "1"
    categoria = CategoriaElemento.POSTE

    def analisar(self, _request, _rule):  # type: ignore[no-untyped-def]
        raise RuntimeError("falha localizada")


def _request(catalog: CatalogoTecnico):  # type: ignore[no-untyped-def]
    source_execution_id = uuid4()
    semantic_execution_id = uuid4()
    page_id = uuid4()
    compatibility = catalog.compatibilidades[0]
    item_by_id = {item.id: item for item in catalog.itens}
    codes = {
        CategoriaElemento.POSTE: catalog.itens_ativos(CategoriaElemento.POSTE)[0].codigo,
        CategoriaElemento.ESTRUTURA_MT: item_by_id[compatibility.tipo_estrutura_id].codigo,
        CategoriaElemento.ESTRUTURA_BT: catalog.itens_ativos(CategoriaElemento.ESTRUTURA_BT)[
            0
        ].codigo,
        CategoriaElemento.CABO: item_by_id[compatibility.tipo_cabo_id].codigo,
        CategoriaElemento.EQUIPAMENTO: catalog.itens_ativos(CategoriaElemento.EQUIPAMENTO)[
            0
        ].codigo,
    }
    evidence = (
        text_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="pole",
            text=f"POSTE {codes[CategoriaElemento.POSTE]}",
            x="0.10",
            y="0.10",
            color="#008000",
        ),
        text_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="mt",
            text=codes[CategoriaElemento.ESTRUTURA_MT],
            x="0.10",
            y="0.10",
            color="#008000",
            rotation="90",
        ),
        text_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="bt",
            text=codes[CategoriaElemento.ESTRUTURA_BT],
            x="0.11",
            y="0.10",
            color="#FF0000",
        ),
        text_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="cable-label",
            text=codes[CategoriaElemento.CABO],
            x="0.45",
            y="0.45",
        ),
        vector_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="cable-line",
            points=(("0.10", "0.10"), ("0.80", "0.80")),
            color="#008000",
        ),
        text_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="equipment",
            text=codes[CategoriaElemento.EQUIPAMENTO],
            x="0.80",
            y="0.80",
        ),
        image_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="equipment-image",
            x="0.80",
            y="0.80",
        ),
        text_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="false-positive",
            text="RUA1",
            x="0.95",
            y="0.95",
        ),
    )
    registry = carregar_registro_regras_inicial()
    return SolicitacaoInterpretacao(
        projeto_id=uuid4(),
        execucao_id=semantic_execution_id,
        execucao_extracao_id=source_execution_id,
        catalogo=catalog,
        evidencias=evidence,
        registro=registry,
    )


def test_rule_interpreter_proposes_all_categories_situations_and_relations(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    interpreter = InterpretadorRegrasExplicitas(request.registro)

    result = interpreter.interpretar(request)

    assert {item.categoria for item in result.elementos} == set(CategoriaElemento)
    pole = next(item for item in result.elementos if item.categoria is CategoriaElemento.POSTE)
    bt = next(item for item in result.elementos if item.categoria is CategoriaElemento.ESTRUTURA_BT)
    cable = next(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    equipment = next(
        item for item in result.elementos if item.categoria is CategoriaElemento.EQUIPAMENTO
    )
    assert pole.situacao_projeto is SituacaoProjeto.INSTALAR
    assert bt.situacao_projeto is SituacaoProjeto.REMOVER
    assert cable.geometria.tipo is TipoGeometria.POLILINHA
    assert cable.situacao_projeto is SituacaoProjeto.INSTALAR
    image = next(item for item in request.evidencias if item.tipo.value == "IMAGEM")
    assert image.id in equipment.evidencia_ids
    assert {item.tipo_relacao for item in result.relacoes} >= {
        "INSTALADA_EM",
        "CONECTA",
        "SUPORTADO_POR",
    }
    assert all(item.evidencia_ids for item in result.elementos)
    assert all(item.evidencia_ids for item in result.relacoes)


def test_rule_interpreter_is_deterministic_and_does_not_match_code_as_substring(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    interpreter = InterpretadorRegrasExplicitas(request.registro)

    first = interpreter.interpretar(request)
    second = interpreter.interpretar(request)

    assert first == second
    false_positive = next(item for item in request.evidencias if item.conteudo_bruto == "RUA1")
    assert not any(false_positive.id in item.evidencia_ids for item in first.elementos)


def test_dense_overlapping_page_remains_bounded_and_analyzer_failure_is_local(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = request.evidencias[0]
    noise = tuple(
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=source.pagina_id,
            key=f"noise-{index}",
            text=f"RUA{index} U1X",
            x="0.5",
            y="0.5",
        )
        for index in range(200)
    )
    dense = replace(request, evidencias=(*request.evidencias, *noise))
    interpreter = InterpretadorRegrasExplicitas(
        request.registro,
        analisadores=(FailingPoleAnalyzer(), AnalisadorEstruturaMt()),
    )

    result = interpreter.interpretar(dense)

    assert result.elementos
    assert all(item.categoria is CategoriaElemento.ESTRUTURA_MT for item in result.elementos)
    assert len(result.elementos) < 10
    assert result.diagnosticos[0].codigo == "interpretacao.analisador_falhou"


@pytest.mark.parametrize("pole_text", ("11 / 300", "11:300", "11\n300"))
def test_pole_nomenclature_from_native_text_or_ocr_is_recognized_and_cataloged(
    catalogo_inicial: CatalogoTecnico,
    pole_text: str,
) -> None:
    request = _request(catalogo_inicial)
    source = request.evidencias[0]
    dimensions = replace(
        source,
        id=uuid4(),
        tipo=TipoEvidencia.OCR,
        conteudo_bruto=pole_text,
        atributos_extraidos=(("confianca", Decimal("0.91")),),
    )
    request = replace(request, evidencias=(dimensions,))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    pole = result.elementos[0]
    assert pole.categoria is CategoriaElemento.POSTE
    assert pole.codigo_observado == "11-300"
    assert pole.tipo_catalogo_sugerido_id is not None
    catalog_item = catalogo_inicial.item_por_id(pole.tipo_catalogo_sugerido_id)
    assert catalog_item is not None
    assert catalog_item.codigo == "P-11M-300DAN-CIRCULAR"
    assert pole.estado_revisao is EstadoRevisao.PROPOSTA
    attributes = dict(pole.atributos_sugeridos)
    assert attributes["altura_m"] == "11"
    assert attributes["resistencia_dan"] == 300
    assert attributes["catalogo_inferido"] is True


def test_pole_collects_nearby_coordinates_from_native_text_and_ocr(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = request.evidencias[0]
    pole = replace(source, id=uuid4(), conteudo_bruto="11-300")
    east = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="coordinate-east",
        text="0465702",
        x="0.11",
        y="0.10",
    )
    north = replace(
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=source.pagina_id,
            key="coordinate-north",
            text="7772468",
            x="0.12",
            y="0.10",
        ),
        tipo=TipoEvidencia.OCR,
    )
    request = replace(request, evidencias=(pole, east, north))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    proposal = result.elementos[0]
    attributes = dict(proposal.atributos_sugeridos)
    assert attributes["coordenada_leste"] == 465702
    assert attributes["coordenada_norte"] == 7772468
    assert attributes["coordenada_origem"] == "texto_ou_ocr"
    assert {east.id, north.id} <= set(proposal.evidencia_ids)


def test_installed_assets_are_related_to_installed_pole_instead_of_nearer_removed_pole(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = request.evidencias[0]
    structure_code = next(
        item.codigo
        for item in catalogo_inicial.itens_ativos(CategoriaElemento.ESTRUTURA_MT)
        if item.codigo == "U3"
    )
    evidence = (
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=source.pagina_id,
            key="removed-pole",
            text="10-150",
            x="0.10",
            y="0.10",
            color="#FF0000",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=source.pagina_id,
            key="installed-pole",
            text="11-300",
            x="0.12",
            y="0.10",
            color="#008000",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=source.pagina_id,
            key="installed-structure",
            text=structure_code,
            x="0.105",
            y="0.10",
            color="#008000",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=source.pagina_id,
            key="installed-transformer",
            text="100A-10KA-2H",
            x="0.105",
            y="0.11",
            color="#008000",
        ),
    )
    request = replace(request, evidencias=evidence)

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    installed_pole = next(
        item
        for item in result.elementos
        if item.categoria is CategoriaElemento.POSTE and item.codigo_observado == "11-300"
    )
    installed_dependents = {
        item.id
        for item in result.elementos
        if item.categoria in {CategoriaElemento.ESTRUTURA_MT, CategoriaElemento.EQUIPAMENTO}
    }
    related = {
        relation.origem_referencia_id: relation.destino_referencia_id
        for relation in result.relacoes
        if relation.origem_referencia_id in installed_dependents
        and relation.tipo_relacao in {"INSTALADA_EM", "INSTALADO_EM"}
    }
    assert related
    assert set(related) == installed_dependents
    assert set(related.values()) == {installed_pole.id}


def test_pole_format_resolves_dimension_to_exact_catalog_item(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = replace(
        request.evidencias[0],
        id=uuid4(),
        conteudo_bruto="POSTE CIRCULAR 11-300",
    )
    request = replace(request, evidencias=(source,))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    pole = result.elementos[0]
    item = catalogo_inicial.item_por_id(pole.tipo_catalogo_sugerido_id)  # type: ignore[arg-type]
    assert item is not None
    assert item.codigo == "P-11M-300DAN-CIRCULAR"
    assert pole.estado_revisao is EstadoRevisao.PROPOSTA


def test_equipment_class_phrase_is_proposed_for_human_disambiguation(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = replace(
        request.evidencias[0],
        id=uuid4(),
        conteudo_bruto="CHAVE FUSÍVEL REPETIDORA",
    )
    request = replace(request, evidencias=(source,))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    equipment = result.elementos[0]
    assert equipment.categoria is CategoriaElemento.EQUIPAMENTO
    assert equipment.tipo_catalogo_sugerido_id is None
    assert dict(equipment.atributos_sugeridos)["classe_equipamento"] == ("CHAVE FUSIVEL REPETIDORA")


@pytest.mark.parametrize(
    ("observed", "catalog_code"),
    [
        ("3-150", "-3-150"),
        ("1-37.5 KVA", "-1-37,5"),
    ],
)
def test_equipment_nomenclature_variants_from_plan_are_cataloged(
    catalogo_inicial: CatalogoTecnico,
    observed: str,
    catalog_code: str,
) -> None:
    request = _request(catalogo_inicial)
    source = replace(
        request.evidencias[0],
        id=uuid4(),
        tipo=TipoEvidencia.OCR,
        conteudo_bruto=observed,
    )
    request = replace(request, evidencias=(source,))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    equipment = next(
        item for item in result.elementos if item.categoria is CategoriaElemento.EQUIPAMENTO
    )
    item = catalogo_inicial.item_por_id(equipment.tipo_catalogo_sugerido_id)  # type: ignore[arg-type]
    assert item is not None
    assert item.codigo == catalog_code
