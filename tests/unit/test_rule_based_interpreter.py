from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from tests.interpretation_factories import image_evidence, text_evidence, vector_evidence

from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.interpretation.rule_based import AnalisadorEstruturaMt
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    SituacaoProjeto,
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
