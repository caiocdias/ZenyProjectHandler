from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import pytest
from tests.interpretation_factories import image_evidence, text_evidence, vector_evidence
from tests.pdf_fixtures import (
    create_e01_span_change_pdf,
    create_e01_structure_occurrences_pdf,
    create_e01_switch_bags_pdf,
)

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.interpretation.rule_based import AnalisadorEstruturaMt
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.analysis import EvidenciaDocumento, OrigemObjetoPdf
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
    TipoGeometria,
    TipoOrigemPdf,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.analysis import SolicitacaoAnaliseDocumento
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao
from zeny_project_handler.ports.pdf import ReferenciaFontePdf


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


@pytest.mark.parametrize(
    "text",
    (
        "H.N=6,3m",
        "Altura nominal: 11 m",
        "Engastamento 1,6 m",
        "Área: 20 m",
    ),
)
def test_post_and_area_measurements_are_not_attached_as_span_lengths(
    catalogo_inicial: CatalogoTecnico,
    text: str,
) -> None:
    request = _request(catalogo_inicial)
    measurement = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=request.evidencias[0].pagina_id,
        key=f"non-span-measurement-{text}",
        text=text,
        x="0.45",
        y="0.42",
    )
    request = replace(request, evidencias=(*request.evidencias, measurement))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    cable = next(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    assert "comprimento_m" not in dict(cable.atributos_sugeridos)


def test_native_review_annotations_do_not_create_project_elements_or_lengths(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    page_id = request.evidencias[0].pagina_id
    review_comment = replace(
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="commissioner-review-comment",
            text="Vão: 137 m",
            x="0.45",
            y="0.42",
        ),
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.ANOTACAO,
            numero_objeto=123,
            indice_anotacao=0,
            subtipo_anotacao="FreeText",
        ),
    )
    review_appearance = replace(
        vector_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="commissioner-review-appearance",
            points=(("0.10", "0.10"), ("0.80", "0.80")),
            color="#FF0000",
        ),
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.APARENCIA_ANOTACAO,
            numero_objeto=124,
            indice_anotacao=0,
            subtipo_anotacao="FreeText",
        ),
    )
    request = replace(
        request,
        evidencias=(*request.evidencias, review_comment, review_appearance),
    )

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert all(review_comment.id not in item.evidencia_ids for item in result.elementos)
    assert all(review_appearance.id not in item.evidencia_ids for item in result.elementos)
    cable = next(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    assert "comprimento_m" not in dict(cable.atributos_sugeridos)


def test_autocad_shx_annotation_is_preserved_as_technical_drawing_content(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    page_id = request.evidencias[0].pagina_id
    technical_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="autocad-shx-span-label",
        text="V1-2=52 m",
        x="0.45",
        y="0.42",
    )
    technical_label = replace(
        technical_label,
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.ANOTACAO,
            numero_objeto=125,
            indice_anotacao=0,
            subtipo_anotacao="Square",
        ),
        atributos_extraidos=(
            *technical_label.atributos_extraidos,
            ("titulo", "AutoCAD SHX Text"),
            ("anotacao_tecnica", True),
        ),
    )
    request = replace(request, evidencias=(*request.evidencias, technical_label))

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    cable = next(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    assert dict(cable.atributos_sugeridos)["comprimento_m"] == Decimal("52")
    assert technical_label.id in cable.evidencia_ids


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

    interpreter = InterpretadorRegrasExplicitas(request.registro)
    result = interpreter.interpretar(request)
    repeated = interpreter.interpretar(request)

    cables = tuple(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    repeated_cables = tuple(
        item for item in repeated.elementos if item.categoria is CategoriaElemento.CABO
    )
    assert [item.id for item in cables] == [item.id for item in repeated_cables]
    assert [item.evidencia_ids for item in cables] == [
        item.evidencia_ids for item in repeated_cables
    ]
    assert len(cables) == 2
    assert all(item.geometria == solid_path.geometria for item in cables), [
        (item.codigo_observado, item.geometria, dict(item.atributos_sugeridos)) for item in cables
    ]
    assert all(dict(item.atributos_sugeridos)["comprimento_m"] == Decimal("55") for item in cables)
    assert all(solid_path.id in item.evidencia_ids for item in cables)
    assert all(dashed_path.id not in item.evidencia_ids for item in cables)
    assert {dict(item.atributos_sugeridos)["geometria_cabo_origem"] for item in cables} == {
        "vetor_associado_geometricamente"
    }
    assert all(item.evidencia_ids == tuple(sorted(item.evidencia_ids, key=str)) for item in cables)
    assert all(
        item.justificativa is not None
        and "O identificador V1-2 fixou as extremidades em P1 e P2." in item.justificativa
        for item in cables
    )
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


def test_e04_span_reduction_keeps_current_length_and_does_not_capture_service_drop_label(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request, evidence = _e04_span_change_request(catalogo_inicial)
    interpreter = InterpretadorRegrasExplicitas(request.registro)

    result = interpreter.interpretar(request)
    repeated = interpreter.interpretar(request)
    permuted = interpreter.interpretar(
        replace(request, evidencias=tuple(reversed(request.evidencias)))
    )

    assert result == repeated
    assert result == permuted
    cables = tuple(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    assert len(cables) == 2
    cable = next(
        item
        for item in cables
        if dict(item.atributos_sugeridos).get("alteracao_cabo") == "REDUCAO_COMPRIMENTO"
    )
    attributes = dict(cable.atributos_sugeridos)
    assert cable.situacao_projeto is SituacaoProjeto.ALTERAR
    assert attributes["comprimento_m"] == Decimal("269")
    assert attributes["comprimento_substituido_m"] == Decimal("321")
    assert attributes["alteracao_cabo"] == "REDUCAO_COMPRIMENTO"
    assert attributes["evidencia_comprimento_id"] == str(evidence["current_length"].id)
    assert attributes["evidencia_comprimento_substituido_id"] == str(
        evidence["superseded_length"].id
    )
    assert attributes["evidencia_supersessao_id"] == str(evidence["strike"].id)
    assert "identificador_operacional" not in attributes
    assert "evidencia_identificador_id" not in attributes
    assert evidence["span_identifier"].id not in cable.evidencia_ids
    assert evidence["service_drop"].id not in cable.evidencia_ids
    assert cable.geometria == GeometriaDocumento.polilinha(
        evidence["main_path"].pagina_id,
        tuple(reversed(evidence["main_path"].geometria.pontos)),
    )
    assert {
        evidence["main_path"].id,
        evidence["current_length"].id,
        evidence["superseded_length"].id,
        evidence["strike"].id,
    }.issubset(cable.evidencia_ids)
    connected_labels = {
        dict(element.atributos_sugeridos).get("identificador_operacional")
        for relation in result.relacoes
        if relation.origem_referencia_id == cable.id and relation.tipo_relacao == "CONECTA"
        for element in result.elementos
        if element.id == relation.destino_referencia_id
    }
    assert connected_labels == {"P1", "P2"}
    service_drop_cable = next(item for item in cables if item.id != cable.id)
    service_drop_attributes = dict(service_drop_cable.atributos_sugeridos)
    assert service_drop_cable.geometria == evidence["service_drop"].geometria
    assert service_drop_attributes["identificador_operacional"] == "V1-2"
    assert service_drop_attributes["evidencia_identificador_id"] == str(
        evidence["span_identifier"].id
    )
    assert "comprimento_m" not in service_drop_attributes


def test_e04_extracted_span_change_fixture_preserves_supersession_evidence(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    fixture_path = create_e01_span_change_pdf(tmp_path / "e04-span-change.pdf")
    inspection = PyMuPdfReader().inspecionar(fixture_path)
    project_id = uuid4()
    extraction_id = uuid4()
    extraction = PyMuPdfDocumentAnalyzer().analisar(
        SolicitacaoAnaliseDocumento(
            projeto_id=project_id,
            documento=inspection.documento,
            fonte=ReferenciaFontePdf(
                documento_id=inspection.documento.id,
                projeto_id=project_id,
                caminho_canonico=fixture_path,
                sha256=inspection.documento.sha256,
                tamanho_bytes=inspection.tamanho_bytes,
                modificado_em_ns=inspection.modificado_em_ns,
            ),
            execucao_id=extraction_id,
            criada_em=datetime(2026, 9, 1, 22, tzinfo=UTC),
        )
    )
    registry = carregar_registro_regras_inicial()
    result = InterpretadorRegrasExplicitas(registry).interpretar(
        SolicitacaoInterpretacao(
            projeto_id=project_id,
            execucao_id=uuid4(),
            execucao_extracao_id=extraction_id,
            catalogo=catalogo_inicial,
            evidencias=extraction.evidencias,
            registro=registry,
        )
    )

    cable = next(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    attributes = dict(cable.atributos_sugeridos)
    evidence_by_content = {
        item.conteudo_bruto: item
        for item in extraction.evidencias
        if item.conteudo_bruto in {"321 m", "269 m"}
    }
    assert cable.situacao_projeto is SituacaoProjeto.ALTERAR
    assert attributes["comprimento_m"] == Decimal("269")
    assert attributes["comprimento_substituido_m"] == Decimal("321")
    assert attributes["evidencia_comprimento_id"] == str(evidence_by_content["269 m"].id)
    assert attributes["evidencia_comprimento_substituido_id"] == str(
        evidence_by_content["321 m"].id
    )
    assert evidence_by_content["269 m"].id in cable.evidencia_ids
    assert evidence_by_content["321 m"].id in cable.evidencia_ids
    supersession_id = UUID(str(attributes["evidencia_supersessao_id"]))
    supersession = next(item for item in extraction.evidencias if item.id == supersession_id)
    assert dict(supersession.atributos_extraidos).get("cor_contorno") == "#8C0033"


@pytest.mark.parametrize("case", ("parallel", "crossing"))
def test_e04_ambiguous_parallel_or_crossing_paths_do_not_capture_cable_label(
    catalogo_inicial: CatalogoTecnico,
    case: str,
) -> None:
    request, label = _e04_ambiguous_paths_request(catalogo_inicial, case)

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    cable = next(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    attributes = dict(cable.atributos_sugeridos)
    assert cable.geometria == label.geometria
    assert "evidencia_geometria_id" not in attributes
    assert "identificador_operacional" not in attributes


def test_e04_ambiguous_span_labels_leave_geometrically_valid_cable_unidentified(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request, path = _e04_ambiguous_identifier_request(catalogo_inicial)

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    cable = next(item for item in result.elementos if item.categoria is CategoriaElemento.CABO)
    attributes = dict(cable.atributos_sugeridos)
    assert cable.geometria == path.geometria
    assert attributes["evidencia_geometria_id"] == str(path.id)
    assert "identificador_operacional" not in attributes
    assert "evidencia_identificador_id" not in attributes


def _e04_span_change_request(
    catalog: CatalogoTecnico,
) -> tuple[SolicitacaoInterpretacao, dict[str, EvidenciaDocumento]]:
    request = _request(catalog)
    page_id = request.evidencias[0].pagina_id
    pole_code = request.evidencias[0].conteudo_bruto
    cable_code = request.evidencias[3].conteudo_bruto
    assert pole_code is not None and cable_code is not None
    cable_label = replace(
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-cable-label",
            text=cable_code,
            x="0.52",
            y="0.47",
            color="#008000",
        ),
        tipo=TipoEvidencia.OCR,
        atributos_extraidos=(
            ("cor_preenchimento", "#008000"),
            ("motor_ocr", "tesseract-rotulo-linear-retificado"),
            ("rotacao_graus", Decimal(0)),
        ),
    )
    service_drop_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="e04-service-drop-cable-label",
        text=cable_code,
        x="0.89",
        y="0.58",
    )
    main_path = vector_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="e04-main-path-reversed",
        points=(("0.82", "0.50"), ("0.18", "0.50")),
        color="#008000",
    )
    service_drop = vector_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="e04-service-drop",
        points=(("0.82", "0.50"), ("0.95", "0.68")),
    )
    superseded_length = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="e04-superseded-length",
        text="321 m",
        x="0.40",
        y="0.47",
    )
    current_length = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="e04-current-length",
        text="269 m",
        x="0.62",
        y="0.47",
    )
    strike = vector_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="e04-local-strike",
        points=(("0.37", "0.47"), ("0.43", "0.47")),
        color="#8C0033",
    )
    span_identifier = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="e04-service-drop-identifier",
        text="V1-2",
        x="0.90",
        y="0.61",
    )
    evidence = (
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-pole-1",
            text=pole_code,
            x="0.18",
            y="0.50",
            color="#008000",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-pole-2",
            text=pole_code,
            x="0.82",
            y="0.50",
            color="#008000",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-point-1",
            text="P1",
            x="0.18",
            y="0.48",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-point-2",
            text="P2",
            x="0.82",
            y="0.48",
        ),
        cable_label,
        service_drop_label,
        main_path,
        service_drop,
        superseded_length,
        current_length,
        strike,
        span_identifier,
    )
    return replace(request, evidencias=evidence), {
        "main_path": main_path,
        "service_drop": service_drop,
        "superseded_length": superseded_length,
        "current_length": current_length,
        "strike": strike,
        "span_identifier": span_identifier,
    }


def _e04_ambiguous_paths_request(
    catalog: CatalogoTecnico,
    case: str,
) -> tuple[SolicitacaoInterpretacao, EvidenciaDocumento]:
    request = _request(catalog)
    page_id = request.evidencias[0].pagina_id
    pole_code = request.evidencias[0].conteudo_bruto
    cable_code = request.evidencias[3].conteudo_bruto
    assert pole_code is not None and cable_code is not None
    paths = (
        (
            (("0.20", "0.47"), ("0.80", "0.47")),
            (("0.20", "0.53"), ("0.80", "0.53")),
        )
        if case == "parallel"
        else (
            (("0.20", "0.30"), ("0.80", "0.70")),
            (("0.20", "0.70"), ("0.80", "0.30")),
        )
    )
    endpoint_coordinates = tuple(point for path in paths for point in path)
    pole_evidence = tuple(
        item
        for index, (x, y) in enumerate(endpoint_coordinates, start=1)
        for item in (
            text_evidence(
                execution_id=request.execucao_extracao_id,
                page_id=page_id,
                key=f"e04-{case}-pole-{index}",
                text=pole_code,
                x=x,
                y=y,
                color="#008000",
            ),
            text_evidence(
                execution_id=request.execucao_extracao_id,
                page_id=page_id,
                key=f"e04-{case}-point-{index}",
                text=f"P{index}",
                x=x,
                y=str(Decimal(y) - Decimal("0.02")),
            ),
        )
    )
    label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key=f"e04-{case}-cable-label",
        text=cable_code,
        x="0.50",
        y="0.50",
        color="#008000",
    )
    path_evidence = tuple(
        vector_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key=f"e04-{case}-path-{index}",
            points=points,
            color="#008000",
        )
        for index, points in enumerate(paths, start=1)
    )
    return replace(request, evidencias=(*pole_evidence, label, *path_evidence)), label


def _e04_ambiguous_identifier_request(
    catalog: CatalogoTecnico,
) -> tuple[SolicitacaoInterpretacao, EvidenciaDocumento]:
    request = _request(catalog)
    page_id = request.evidencias[0].pagina_id
    pole_code = request.evidencias[0].conteudo_bruto
    cable_code = request.evidencias[3].conteudo_bruto
    assert pole_code is not None and cable_code is not None
    path = vector_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="e04-ambiguous-identifier-path",
        points=(("0.20", "0.50"), ("0.80", "0.50")),
        color="#008000",
    )
    evidence = (
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-ambiguous-identifier-pole",
            text=pole_code,
            x="0.20",
            y="0.50",
            color="#008000",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-ambiguous-identifier-point",
            text="P1",
            x="0.20",
            y="0.48",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-ambiguous-identifier-cable",
            text=cable_code,
            x="0.50",
            y="0.47",
            color="#008000",
        ),
        path,
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-ambiguous-identifier-v12",
            text="V1-2",
            x="0.50",
            y="0.46",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e04-ambiguous-identifier-v13",
            text="V1-3",
            x="0.50",
            y="0.46",
        ),
    )
    return replace(request, evidencias=evidence), path


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


def test_e01_structure_fixture_preserves_physical_occurrences_and_qualifiers(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    fixture_path = create_e01_structure_occurrences_pdf(tmp_path / "e01-structures.pdf")
    inspection = PyMuPdfReader().inspecionar(fixture_path)
    project_id = uuid4()
    extraction_id = uuid4()
    extraction = PyMuPdfDocumentAnalyzer().analisar(
        SolicitacaoAnaliseDocumento(
            projeto_id=project_id,
            documento=inspection.documento,
            fonte=ReferenciaFontePdf(
                documento_id=inspection.documento.id,
                projeto_id=project_id,
                caminho_canonico=fixture_path,
                sha256=inspection.documento.sha256,
                tamanho_bytes=inspection.tamanho_bytes,
                modificado_em_ns=inspection.modificado_em_ns,
            ),
            execucao_id=extraction_id,
            criada_em=datetime(2026, 9, 1, 20, tzinfo=UTC),
        )
    )
    page_id = inspection.documento.paginas[0].id
    point_labels = tuple(
        text_evidence(
            execution_id=extraction_id,
            page_id=page_id,
            key=f"e02-point-{identifier}",
            text=identifier,
            x=x,
            y=y,
        )
        for identifier, x, y in (
            ("P1", "0.08", "0.34"),
            ("P2", "0.37", "0.34"),
            ("P3", "0.66", "0.36"),
            ("P4", "0.08", "0.67"),
        )
    )
    fixture_text = {
        item.conteudo_bruto: item
        for item in extraction.evidencias
        if item.tipo is TipoEvidencia.TEXTO and item.conteudo_bruto != "S3R"
    }
    physical_s3r = sorted(
        (
            item
            for item in extraction.evidencias
            if item.tipo is TipoEvidencia.TEXTO and item.conteudo_bruto == "S3R"
        ),
        key=lambda item: min(point.y for point in item.geometria.pontos),
    )
    duplicate_s3r = replace(
        physical_s3r[0],
        id=uuid5(extraction_id, "e02-duplicate-s3r-ocr"),
        tipo=TipoEvidencia.OCR,
        metodo="fixture-ocr-duplicado",
        atributos_extraidos=(
            ("confianca", Decimal("0.96")),
            ("motor_ocr", "tesseract-rotulo-operacional-localizado"),
        ),
    )
    evidence = (*extraction.evidencias, duplicate_s3r, *point_labels)
    registry = carregar_registro_regras_inicial()
    request = SolicitacaoInterpretacao(
        projeto_id=project_id,
        execucao_id=uuid4(),
        execucao_extracao_id=extraction_id,
        catalogo=catalogo_inicial,
        evidencias=evidence,
        registro=registry,
    )
    interpreter = InterpretadorRegrasExplicitas(registry)

    first = interpreter.interpretar(request)
    repeated = interpreter.interpretar(request)
    permuted = interpreter.interpretar(replace(request, evidencias=tuple(reversed(evidence))))

    assert first == repeated == permuted
    structures = tuple(
        item
        for item in first.elementos
        if item.categoria in {CategoriaElemento.ESTRUTURA_MT, CategoriaElemento.ESTRUTURA_BT}
    )
    assert len(structures) == 5, [
        (
            item.codigo_observado,
            dict(item.atributos_sugeridos).get("qualificador_estrutura"),
            dict(item.atributos_sugeridos).get("identificador_operacional"),
        )
        for item in structures
    ]
    n_structures = tuple(item for item in structures if item.codigo_observado == "N")
    assert len(n_structures) == 1
    assert dict(n_structures[0].atributos_sugeridos)["qualificador_estrutura"] == "2"
    assert dict(n_structures[0].atributos_sugeridos)["token_estrutura"] == "N(2)"
    assert fixture_text["N(2)"].id in n_structures[0].evidencia_ids
    assert not any(
        fixture_text[negative].id in item.evidencia_ids
        for item in structures
        for negative in ("N-(4 CAA)", "NEGATIVO: NOTA COM N ISOLADO")
    )
    cm3 = tuple(item for item in structures if item.codigo_observado == "CM3")
    assert len(cm3) == 2
    assert {dict(item.atributos_sugeridos)["qualificador_estrutura"] for item in cm3} == {
        "1",
        "2",
    }
    s3r = tuple(item for item in structures if item.codigo_observado == "S3R")
    assert len(s3r) == 2
    duplicate_occurrence = next(item for item in s3r if duplicate_s3r.id in item.evidencia_ids)
    assert physical_s3r[0].id in duplicate_occurrence.evidencia_ids
    assert any(physical_s3r[1].id in item.evidencia_ids for item in s3r)
    assert len({item.id for item in structures}) == len(structures)
    assert all("identidade_ocorrencia" in dict(item.atributos_sugeridos) for item in structures)


def test_e03_switch_bags_apply_only_to_the_geometrically_linked_full_nomenclature(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    fixture_path = create_e01_switch_bags_pdf(tmp_path / "e03-switches.pdf")
    inspection = PyMuPdfReader().inspecionar(fixture_path)
    project_id = uuid4()
    extraction_id = uuid4()
    extraction = PyMuPdfDocumentAnalyzer().analisar(
        SolicitacaoAnaliseDocumento(
            projeto_id=project_id,
            documento=inspection.documento,
            fonte=ReferenciaFontePdf(
                documento_id=inspection.documento.id,
                projeto_id=project_id,
                caminho_canonico=fixture_path,
                sha256=inspection.documento.sha256,
                tamanho_bytes=inspection.tamanho_bytes,
                modificado_em_ns=inspection.modificado_em_ns,
            ),
            execucao_id=extraction_id,
            criada_em=datetime(2026, 9, 1, 21, tzinfo=UTC),
        )
    )
    technical_labels = tuple(
        sorted(
            (
                item
                for item in extraction.evidencias
                if item.tipo is TipoEvidencia.TEXTO
                and item.conteudo_bruto
                in {
                    "100A-10KA-2H",
                    "100A-10KA-5H",
                    "280835-300A-12T",
                    "321 m",
                }
            ),
            key=lambda item: (
                min(point.y for point in item.geometria.pontos),
                min(point.x for point in item.geometria.pontos),
                item.conteudo_bruto or "",
            ),
        )
    )
    point_labels = tuple(
        text_evidence(
            execution_id=extraction_id,
            page_id=item.pagina_id,
            key=f"e03-point-{index}",
            text=f"P{20 + index}",
            x=str(
                (
                    min(point.x for point in item.geometria.pontos)
                    + max(point.x for point in item.geometria.pontos)
                )
                / 2
            ),
            y=str(
                (
                    min(point.y for point in item.geometria.pontos)
                    + max(point.y for point in item.geometria.pontos)
                )
                / 2
            ),
        )
        for index, item in enumerate(technical_labels)
    )
    registry = carregar_registro_regras_inicial()
    request = SolicitacaoInterpretacao(
        projeto_id=project_id,
        execucao_id=uuid4(),
        execucao_extracao_id=extraction_id,
        catalogo=catalogo_inicial,
        evidencias=(*extraction.evidencias, *point_labels),
        registro=registry,
    )

    result = InterpretadorRegrasExplicitas(registry).interpretar(request)

    equipment = tuple(
        item for item in result.elementos if item.categoria is CategoriaElemento.EQUIPAMENTO
    )
    assert [item.codigo_observado for item in equipment].count("100A-10KA-2H") == 2
    assert [item.codigo_observado for item in equipment].count("100A-10KA-5H") == 2
    assert {item.codigo_observado for item in equipment} == {
        "100A-10KA-2H",
        "100A-10KA-5H",
    }
    assert [item.situacao_projeto for item in equipment].count(SituacaoProjeto.INSTALAR) == 2
    assert [item.situacao_projeto for item in equipment].count(SituacaoProjeto.EXISTENTE) == 2
    installed = tuple(
        item for item in equipment if item.situacao_projeto is SituacaoProjeto.INSTALAR
    )
    assert {item.codigo_observado for item in installed} == {
        "100A-10KA-2H",
        "100A-10KA-5H",
    }
    assert all(
        dict(item.atributos_sugeridos)["situacao_inferida_bolha"] is True for item in installed
    )
    negative_ids = {
        item.id for item in technical_labels if item.conteudo_bruto in {"280835-300A-12T", "321 m"}
    }
    assert not any(negative_ids & set(item.evidencia_ids) for item in equipment)
    burgundy_vectors = {
        item.id
        for item in extraction.evidencias
        if item.tipo is TipoEvidencia.VETOR
        and dict(item.atributos_extraidos).get("cor_contorno") == "#8C0033"
    }
    used_bags = burgundy_vectors & {
        evidence_id for item in installed for evidence_id in item.evidencia_ids
    }
    assert len(used_bags) == 2
    assert len(burgundy_vectors - used_bags) == 2
    unlinked_bags = tuple(
        item
        for item in extraction.evidencias
        if item.id in burgundy_vectors - used_bags
        and dict(item.atributos_extraidos).get("operacoes") == "l,l,l"
    )
    assert len(unlinked_bags) == 1
    unlinked_x = [point.x for point in unlinked_bags[0].geometria.pontos]
    unlinked_y = [point.y for point in unlinked_bags[0].geometria.pontos]
    assert Decimal("0.0005") <= min(
        max(unlinked_x) - min(unlinked_x), max(unlinked_y) - min(unlinked_y)
    )
    assert max(max(unlinked_x) - min(unlinked_x), max(unlinked_y) - min(unlinked_y)) <= Decimal(
        "0.20"
    )


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


def test_e05_delivery_cluster_cannot_receive_structures_or_equipment(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    page_id = request.evidencias[0].pagina_id
    pole_code = request.evidencias[0].conteudo_bruto or "11-300"
    structure_code = request.evidencias[1].conteudo_bruto or "U3"
    equipment_code = request.evidencias[5].conteudo_bruto or "TR-37"
    evidence = (
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e05-real-pole",
            text=pole_code,
            x="0.74",
            y="0.40",
            color="#008000",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e05-delivery-symbol",
            text=pole_code,
            x="0.80",
            y="0.40",
            color="#008000",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e05-structure",
            text=structure_code,
            x="0.78",
            y="0.40",
            color="#008000",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e05-equipment",
            text=equipment_code,
            x="0.78",
            y="0.41",
            color="#008000",
        ),
        image_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e05-equipment-image",
            x="0.78",
            y="0.41",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e05-real-label",
            text="P4",
            x="0.74",
            y="0.38",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e05-delivery-label",
            text="P5",
            x="0.80",
            y="0.38",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e05-standard-marker",
            text="PADRÃO",
            x="0.82",
            y="0.40",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="e05-standard-legend-negative",
            text="LEGENDA: PADRAO DE COR",
            x="0.50",
            y="0.10",
        ),
    )

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(
        replace(request, evidencias=evidence)
    )

    poles = tuple(item for item in result.elementos if item.categoria is CategoriaElemento.POSTE)
    real_pole = next(
        item
        for item in poles
        if dict(item.atributos_sugeridos).get("identificador_operacional") == "P4"
    )
    delivery_symbol = next(
        item
        for item in poles
        if dict(item.atributos_sugeridos).get("identificador_operacional") == "P5"
    )
    assert dict(delivery_symbol.atributos_sugeridos)["tipo_ponto_rede"] == "ENTREGA"
    assert "tipo_ponto_rede" not in dict(real_pole.atributos_sugeridos)
    dependents = {
        item.id
        for item in result.elementos
        if item.categoria in {CategoriaElemento.ESTRUTURA_MT, CategoriaElemento.EQUIPAMENTO}
    }
    installation_relations = tuple(
        relation
        for relation in result.relacoes
        if relation.origem_referencia_id in dependents
        and relation.tipo_relacao in {"INSTALADA_EM", "INSTALADO_EM"}
    )
    assert dependents
    assert {relation.origem_referencia_id for relation in installation_relations} == dependents
    assert {relation.destino_referencia_id for relation in installation_relations} == {real_pole.id}
    assert all(relation.destino_referencia_id != delivery_symbol.id for relation in result.relacoes)


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


def test_unidentified_cable_with_valid_trace_remains_without_span_identifier(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    references_only = replace(request, evidencias=request.evidencias[:-3])

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(references_only)

    assert len(result.elementos) == 1
    cable = result.elementos[0]
    assert cable.categoria is CategoriaElemento.CABO
    assert cable.geometria.tipo is TipoGeometria.POLILINHA
    assert "identificador_operacional" not in dict(cable.atributos_sugeridos)
    assert result.relacoes == ()


def test_point_identifier_selects_one_occurrence_and_discards_reference_grounding(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    page_id = request.evidencias[0].pagina_id
    reference_grounding = replace(
        vector_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="reference-grounding",
            points=(("0.125", "0.095"), ("0.135", "0.105")),
        ),
        conteudo_bruto="ATERRAMENTO",
        atributos_extraidos=(
            ("classe_equipamento", "ATERRAMENTO"),
            ("confianca", Decimal("0.88")),
            ("origem_simbologia", "SIMBOLOGIA.pdf"),
            ("reconhecido_por_simbologia", True),
            ("situacao_projeto_forcada", SituacaoProjeto.EXISTENTE.value),
        ),
    )
    changed_pole = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="changed-pole",
        text=request.evidencias[0].conteudo_bruto or "11-300",
        x="0.13",
        y="0.22",
        color="#008000",
    )
    installed_grounding = replace(
        reference_grounding,
        id=uuid4(),
        geometria=GeometriaDocumento.polilinha(
            page_id,
            (
                PontoNormalizado(Decimal("0.135"), Decimal("0.225")),
                PontoNormalizado(Decimal("0.145"), Decimal("0.235")),
            ),
        ),
        atributos_extraidos=(
            ("classe_equipamento", "ATERRAMENTO"),
            ("confianca", Decimal("0.88")),
            ("origem_simbologia", "SIMBOLOGIA.pdf"),
            ("reconhecido_por_simbologia", True),
            ("situacao_projeto_forcada", SituacaoProjeto.INSTALAR.value),
        ),
    )
    native_label = text_evidence(
        execution_id=request.execucao_extracao_id,
        page_id=page_id,
        key="native-point-label-between-occurrences",
        text="P1",
        x="0.03",
        y="0.19",
    )
    targeted_label = replace(
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="targeted-point-label-at-project-pole",
            text="P1",
            x="0.13",
            y="0.22",
        ),
        tipo=TipoEvidencia.OCR,
        atributos_extraidos=(
            ("confianca", Decimal("0.94")),
            ("motor_ocr", "tesseract-identificador-localizado"),
        ),
    )
    native_only_request = replace(
        request,
        evidencias=(
            reference_grounding,
            changed_pole,
            installed_grounding,
            native_label,
        ),
    )
    interpreter = InterpretadorRegrasExplicitas(request.registro)

    native_only_result = interpreter.interpretar(native_only_request)
    result = interpreter.interpretar(
        replace(
            native_only_request,
            evidencias=(*native_only_request.evidencias, targeted_label),
        )
    )

    assert len(native_only_result.elementos) == 2
    assert not any(
        reference_grounding.id in item.evidencia_ids for item in native_only_result.elementos
    )
    assert len(result.elementos) == 2
    assert {item.situacao_projeto for item in result.elementos} == {SituacaoProjeto.INSTALAR}
    assert all(
        dict(item.atributos_sugeridos)["identificador_operacional"] == "P1"
        for item in result.elementos
    )
    assert all(
        dict(item.atributos_sugeridos)["evidencia_identificador_id"] == str(targeted_label.id)
        for item in result.elementos
    )
    assert not any(reference_grounding.id in item.evidencia_ids for item in result.elementos)


def test_coordinates_do_not_identify_electrical_references_without_numbered_point(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    request = _request(catalogo_inicial)
    page_id = request.evidencias[0].pagina_id
    electrical_references = (
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="unscoped-mt-structure",
            text="U3",
            x="0.10",
            y="0.10",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="unscoped-bt-structure",
            text="S3R",
            x="0.10",
            y="0.11",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="unscoped-pole",
            text="10-300",
            x="0.10",
            y="0.12",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="unscoped-coordinate-east",
            text="505097",
            x="0.10",
            y="0.13",
        ),
        text_evidence(
            execution_id=request.execucao_extracao_id,
            page_id=page_id,
            key="unscoped-coordinate-north",
            text="7754806",
            x="0.10",
            y="0.14",
        ),
    )
    request = replace(request, evidencias=electrical_references)

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert result.elementos == ()
    assert result.relacoes == ()


def test_numbered_point_keeps_pole_coordinates_as_auxiliary_attributes(
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
        evidencias=(request.evidencias[0], coordinate, request.evidencias[8]),
    )

    result = InterpretadorRegrasExplicitas(request.registro).interpretar(request)

    assert len(result.elementos) == 1
    pole = result.elementos[0]
    assert pole.categoria is CategoriaElemento.POSTE
    assert dict(pole.atributos_sugeridos)["identificador_operacional"] == "P1"
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

    assert len(result.elementos) == 1
    assert result.elementos[0].categoria is CategoriaElemento.POSTE
    assert dict(result.elementos[0].atributos_sugeridos)["identificador_operacional"] == "P13"


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
