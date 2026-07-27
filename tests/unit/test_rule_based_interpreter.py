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
        text_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="point-label-1",
            text="P1",
            x="0.10",
            y="0.08",
        ),
        text_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="point-label-2",
            text="P2",
            x="0.80",
            y="0.78",
        ),
        text_evidence(
            execution_id=source_execution_id,
            page_id=page_id,
            key="span-label-1-2",
            text="V1-2",
            x="0.45",
            y="0.43",
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
    assert dict(cable.atributos_sugeridos)["evidencia_rotulo_id"] == str(request.evidencias[3].id)
    identifiers = {
        item.categoria: dict(item.atributos_sugeridos)["identificador_operacional"]
        for item in result.elementos
    }
    assert identifiers == {
        CategoriaElemento.POSTE: "P1",
        CategoriaElemento.ESTRUTURA_MT: "P1",
        CategoriaElemento.ESTRUTURA_BT: "P1",
        CategoriaElemento.CABO: "V1-2",
        CategoriaElemento.EQUIPAMENTO: "P2",
    }
    image = next(item for item in request.evidencias if item.tipo.value == "IMAGEM")
    assert image.id in equipment.evidencia_ids
    assert {item.tipo_relacao for item in result.relacoes} >= {
        "INSTALADA_EM",
        "CONECTA",
        "SUPORTADO_POR",
    }
    assert all(item.evidencia_ids for item in result.elementos)
    assert all(item.evidencia_ids for item in result.relacoes)


def test_cable_length_annotation_is_attached_to_the_detected_line(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    annotation = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=request.evidencias[0].pagina_id,
        key="span-length",
        text="Vão: 42,5 m",
        x="0.45",
        y="0.42",
    )
    request = replace(request, evidencias=(*request.evidencias, annotation))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    cable = next(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    attributes = dict(cable.atributos_sugeridos)
    assert attributes["comprimento_m"] == Decimal("42.5")
    assert attributes["comprimento_origem"] == "anotacao_desenho"
    assert attributes["evidencia_comprimento_id"] == str(annotation.id)
    assert annotation.id in cable.evidencia_ids


def test_cable_uses_solid_path_between_same_situation_poles(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    page_id = request.evidencias[0].pagina_id
    pole_code = request.evidencias[0].conteudo_bruto
    cable_code = request.evidencias[3].conteudo_bruto
    assert pole_code is not None
    assert cable_code is not None
    second_cable_code = next(
        item.codigo
        for item in catalogo_inicial.itens_ativos(CategoriaElemento.CABO)
        if item.codigo != cable_code
    )
    installed_first = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="installed-first-pole",
        text=pole_code,
        x="0.20",
        y="0.50",
        color="#008000",
    )
    installed_second = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="installed-second-pole",
        text=pole_code,
        x="0.80",
        y="0.50",
        color="#008000",
    )
    removed_nearer = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="removed-nearer-pole",
        text=pole_code,
        x="0.245",
        y="0.48",
        color="#FF0000",
    )
    label = replace(
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="installed-cable-label",
            text=cable_code,
            x="0.50",
            y="0.45",
            color="#008000",
        ),
        tipo=TipoEvidencia.OCR,
        atributos_extraidos=(
            ("cor_preenchimento", "#008000"),
            ("motor_ocr", "tesseract-rotulo-linear-retificado"),
        ),
    )
    second_label = replace(
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="second-installed-cable-label",
            text=second_cable_code,
            x="0.50",
            y="0.455",
            color="#008000",
        ),
        tipo=TipoEvidencia.OCR,
        atributos_extraidos=(
            ("cor_preenchimento", "#008000"),
            ("motor_ocr", "tesseract-rotulo-linear-retificado"),
        ),
    )
    nearby_short_vector = vector_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="nearby-short-vector",
        points=(("0.49", "0.45"), ("0.51", "0.45")),
        color="#008000",
    )
    solid_path = vector_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="solid-cable-path",
        points=(("0.24", "0.48"), ("0.76", "0.48")),
        color="#008000",
    )
    dashed_path = replace(
        vector_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="dashed-cable-path",
            points=(("0.24", "0.47"), ("0.76", "0.47")),
            color="#008000",
        ),
        atributos_extraidos=(
            ("cor_contorno", "#008000"),
            ("tracejado", "[ 4.61 4.61 ] 0"),
        ),
    )
    length = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="solid-cable-length",
        text="55m",
        x="0.50",
        y="0.44",
    )
    request = replace(
        request,
        evidencias=(
            installed_first,
            installed_second,
            removed_nearer,
            label,
            second_label,
            nearby_short_vector,
            solid_path,
            dashed_path,
            length,
            text_evidence(
                execution_id=request.execucao_extracao_id,
                page_id=page_id,
                key="point-label-first",
                text="P1",
                x="0.20",
                y="0.52",
            ),
            text_evidence(
                execution_id=request.execucao_extracao_id,
                page_id=page_id,
                key="point-label-second",
                text="P2",
                x="0.80",
                y="0.52",
            ),
            text_evidence(
                execution_id=request.execucao_extracao_id,
                page_id=page_id,
                key="span-label",
                text="V1-2",
                x="0.50",
                y="0.43",
            ),
        ),
    )

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    cables = tuple(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    assert len(cables) == 2
    assert all(item.geometria == solid_path.geometria for item in cables), [
        (item.codigo_observado, item.geometria, dict(item.atributos_sugeridos)) for item in cables
    ]
    assert all(dict(item.atributos_sugeridos)["comprimento_m"] == Decimal("55") for item in cables)
    assert all(solid_path.id in item.evidencia_ids for item in cables)
    assert all(dashed_path.id not in item.evidencia_ids for item in cables)
    assert {dict(item.atributos_sugeridos)["geometria_cabo_origem"] for item in cables} == {
        "vetor_ligando_postes",
        "vetor_compartilhado_do_vao",
    }
    installed_pole_ids = {
        item.id
        for item in result.elementos
        if item.categoria is CategoriaElemento.POSTE
        and item.situacao_projeto is SituacaoProjeto.INSTALAR
    }
    proposals_by_id = {item.id: item for item in result.elementos}
    for cable in cables:
        connected_pole_ids = {
            relation.destino_referencia_id
            for relation in result.relacoes
            if relation.origem_referencia_id == cable.id
            and relation.tipo_relacao == "CONECTA"
            and proposals_by_id[relation.destino_referencia_id].categoria is CategoriaElemento.POSTE
        }
        assert connected_pole_ids == installed_pole_ids


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


def test_header_rows_are_not_interpreted_as_project_equipment(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = request.evidencias[0]
    header_line = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="header-device",
        text="Dispositivo: CH.FACA 99146-630A",
        x="0.70",
        y="0.82",
    )
    split_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="header-device-label",
        text="Dispositivo:",
        x="0.70",
        y="0.86",
    )
    split_value = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="header-device-value",
        text="-630A",
        x="0.79",
        y="0.86",
    )
    drawing_equipment = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="drawing-equipment",
        text="-630A",
        x="0.92",
        y="0.95",
    )
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="drawing-point-label",
        text="P3",
        x="0.92",
        y="0.93",
    )
    request = replace(
        request,
        evidencias=(header_line, split_label, split_value, drawing_equipment, point_label),
    )

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    assert result.elementos[0].categoria is CategoriaElemento.EQUIPAMENTO
    assert drawing_equipment.id in result.elementos[0].evidencia_ids


def test_unknown_abcn_nomenclature_is_kept_as_removed_cable_for_review(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = request.evidencias[0]
    label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="unknown-abcn",
        text="ABCN-4(4)",
        x="0.40",
        y="0.42",
        color="#FF0000",
        rotation="70",
    )
    removed_line = vector_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="unknown-abcn-line",
        points=(("0.25", "0.25"), ("0.55", "0.55")),
        color="#FF0000",
    )
    span_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="unknown-span-label",
        text="V3-4",
        x="0.40",
        y="0.40",
    )
    request = replace(request, evidencias=(label, removed_line, span_label))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    cable = result.elementos[0]
    assert cable.categoria is CategoriaElemento.CABO
    assert cable.codigo_observado == "ABCN-4(4)"
    assert cable.tipo_catalogo_sugerido_id is None
    assert cable.situacao_projeto is SituacaoProjeto.REMOVER
    assert cable.estado_revisao is EstadoRevisao.CONFLITANTE
    assert cable.geometria == removed_line.geometria


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
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="dimension-point-label",
        text="P7",
        x="0.10",
        y="0.08",
    )
    request = replace(request, evidencias=(dimensions, point_label))

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
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="coordinate-point-label",
        text="P8",
        x="0.10",
        y="0.08",
    )
    request = replace(request, evidencias=(pole, east, north, point_label))

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
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=source.pagina_id,
            key="installed-point-label",
            text="P9",
            x="0.11",
            y="0.08",
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
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="format-point-label",
        text="P10",
        x="0.10",
        y="0.08",
    )
    request = replace(request, evidencias=(source, point_label))

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
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="class-point-label",
        text="P11",
        x="0.10",
        y="0.08",
    )
    request = replace(request, evidencias=(source, point_label))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    equipment = result.elementos[0]
    assert equipment.categoria is CategoriaElemento.EQUIPAMENTO
    assert equipment.tipo_catalogo_sugerido_id is None
    assert dict(equipment.atributos_sugeridos)["classe_equipamento"] == ("CHAVE FUSIVEL REPETIDORA")


@pytest.mark.parametrize(
    ("symbol", "equipment_class", "situation"),
    [
        ("ATERRAMENTO", "ATERRAMENTO", SituacaoProjeto.EXISTENTE),
        ("PARA RAIOS MT", "PARA_RAIOS_MT", SituacaoProjeto.INSTALAR),
        ("PARA RAIOS BT", "PARA_RAIOS_BT", SituacaoProjeto.REMOVER),
    ],
)
def test_symbol_only_equipment_is_proposed_with_type_and_situation(
    catalogo_inicial: CatalogoTecnico,
    symbol: str,
    equipment_class: str,
    situation: SituacaoProjeto,
) -> None:
    request = _request(catalogo_inicial)
    source = replace(
        request.evidencias[0],
        id=uuid4(),
        tipo=TipoEvidencia.VETOR,
        conteudo_bruto=symbol,
        atributos_extraidos=(
            ("classe_equipamento", equipment_class),
            ("confianca", Decimal("0.88")),
            ("origem_simbologia", "SIMBOLOGIA.pdf"),
            ("reconhecido_por_simbologia", True),
            ("situacao_projeto_forcada", situation.value),
        ),
    )
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key=f"symbol-point-label-{equipment_class}",
        text="P13",
        x="0.10",
        y="0.08",
    )
    request = replace(request, evidencias=(source, point_label))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    equipment = result.elementos[0]
    assert equipment.categoria is CategoriaElemento.EQUIPAMENTO
    assert equipment.situacao_projeto is situation
    assert equipment.confianca == Decimal("0.88")
    assert equipment.codigo_observado == symbol
    assert equipment.tipo_catalogo_sugerido_id is None
    assert dict(equipment.atributos_sugeridos)["classe_equipamento"] == equipment_class
    assert dict(equipment.atributos_sugeridos)["reconhecido_por_simbologia"] is True
    assert "assinatura vetorial" in (equipment.justificativa or "")


@pytest.mark.parametrize(
    ("observed", "catalog_code"),
    [
        ("3-150", "-3-150"),
        ("1-37.5 KVA", "-1-37,5"),
        ("100A/10KA/2H", "100A-10KA-2H"),
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
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="equipment-point-label",
        text="P12",
        x="0.10",
        y="0.08",
    )
    request = replace(request, evidencias=(source, point_label))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    equipment = next(
        item for item in result.elementos if item.categoria is CategoriaElemento.EQUIPAMENTO
    )
    item = catalogo_inicial.item_por_id(equipment.tipo_catalogo_sugerido_id)  # type: ignore[arg-type]
    assert item is not None
    assert item.codigo == catalog_code


def test_unknown_struck_equipment_nomenclature_is_preserved_as_removal(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = replace(
        request.evidencias[0],
        id=uuid4(),
        tipo=TipoEvidencia.OCR,
        conteudo_bruto="100A/2KA/2H",
        atributos_extraidos=(("situacao_projeto_forcada", "REMOVER"),),
    )
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="unknown-equipment-point-label",
        text="P13",
        x="0.10",
        y="0.08",
    )
    request = replace(request, evidencias=(source, point_label))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    equipment = next(
        item for item in result.elementos if item.categoria is CategoriaElemento.EQUIPAMENTO
    )
    assert equipment.codigo_observado == "100A-2KA-2H"
    assert equipment.tipo_catalogo_sugerido_id is None
    assert equipment.situacao_projeto is SituacaoProjeto.REMOVER
    assert equipment.estado_revisao is EstadoRevisao.CONFLITANTE
    assert dict(equipment.atributos_sugeridos)["catalogo_nao_localizado"] is True


def test_dark_red_bubble_forces_installation_regardless_of_equipment_text_color(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=request.evidencias[0].pagina_id,
        key="black-equipment-inside-bubble",
        text="100A/10KA/2H",
        x="0.24",
        y="0.20",
        color="#000000",
    )
    bubble = replace(
        vector_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=source.pagina_id,
            key="installation-bubble",
            points=(
                ("0.18", "0.18"),
                ("0.30", "0.18"),
                ("0.30", "0.22"),
                ("0.18", "0.22"),
            ),
            color="#800000",
        ),
        atributos_extraidos=(
            ("cor_contorno", "#800000"),
            ("operacoes", "qu"),
        ),
    )
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="bubble-equipment-point-label",
        text="P13",
        x="0.24",
        y="0.17",
    )
    request = replace(request, evidencias=(source, bubble, point_label))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    equipment = next(
        item for item in result.elementos if item.categoria is CategoriaElemento.EQUIPAMENTO
    )
    assert equipment.situacao_projeto is SituacaoProjeto.INSTALAR
    assert bubble.id in equipment.evidencia_ids
    assert dict(equipment.atributos_sugeridos)["situacao_inferida_bolha"] is True


def test_unidentified_electrical_references_are_not_project_elements(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    references_only = replace(request, evidencias=request.evidencias[:-3])

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(references_only)

    assert result.elementos == ()
    assert result.relacoes == ()


def test_coordinate_identifies_pole_and_nearby_structure_without_point_label(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    coordinate = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=request.evidencias[0].pagina_id,
        key="field-coordinate",
        text="405402:7804568",
        x="0.10",
        y="0.12",
    )
    request = replace(
        request,
        evidencias=(request.evidencias[0], request.evidencias[1], coordinate),
    )

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert {item.categoria for item in result.elementos} == {
        CategoriaElemento.POSTE,
        CategoriaElemento.ESTRUTURA_MT,
    }
    pole = next(item for item in result.elementos if item.categoria is CategoriaElemento.POSTE)
    assert dict(pole.atributos_sugeridos)["coordenada_leste"] == 405402
    assert dict(pole.atributos_sugeridos)["coordenada_norte"] == 7804568


def test_operational_identifiers_can_share_text_with_the_catalog_nomenclature(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    pole = replace(
        request.evidencias[0],
        id=uuid4(),
        conteudo_bruto="P013 POSTE CIRCULAR 11-300",
    )
    cable = replace(
        request.evidencias[3],
        id=uuid4(),
        conteudo_bruto=f"V003-004 {request.evidencias[3].conteudo_bruto}",
    )
    request = replace(request, evidencias=(pole, cable))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert {
        (item.categoria, dict(item.atributos_sugeridos)["identificador_operacional"])
        for item in result.elementos
    } == {
        (CategoriaElemento.POSTE, "P13"),
        (CategoriaElemento.CABO, "V3-4"),
    }


def test_point_reference_inside_instruction_does_not_identify_nearby_asset(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    structure = request.evidencias[1]
    instruction = replace(
        structure,
        id=uuid4(),
        conteudo_bruto="Realocar chave p/ trafo no P13",
    )
    request = replace(request, evidencias=(structure, instruction))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert result.elementos == ()
    assert result.relacoes == ()


def test_targeted_operational_ocr_consolidates_duplicate_structure_at_same_point(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    source = request.evidencias[2]
    general = replace(
        source,
        id=uuid4(),
        tipo=TipoEvidencia.OCR,
        conteudo_bruto=f"{source.conteudo_bruto}|",
        atributos_extraidos=(
            ("confianca", Decimal("0.40")),
            ("motor_ocr", "tesseract-cli"),
        ),
    )
    targeted = replace(
        source,
        id=uuid4(),
        tipo=TipoEvidencia.OCR,
        atributos_extraidos=(
            ("confianca", Decimal("0.95")),
            ("motor_ocr", "tesseract-rotulo-operacional-localizado"),
        ),
    )
    point_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=source.pagina_id,
        key="targeted-point-label",
        text="P7",
        x="0.11",
        y="0.08",
    )
    request = replace(request, evidencias=(general, targeted, point_label))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    structure = result.elementos[0]
    assert structure.categoria is CategoriaElemento.ESTRUTURA_BT
    assert structure.codigo_observado == source.conteudo_bruto
    assert {general.id, targeted.id} <= set(structure.evidencia_ids)
