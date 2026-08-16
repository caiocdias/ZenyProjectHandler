from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from zeny_project_handler.domain.compliance import (
    AlvoConformidade,
    CondicaoConformidade,
    OperadorCondicao,
    QuantificadorCondicao,
    TipoEscopoConformidade,
)
from zeny_project_handler.ui.compliance_presentation import (
    formatar_alvo,
    formatar_condicao,
    formatar_operador,
    formatar_quantificador,
    formatar_valor_fato,
    rotulo_fato_conformidade,
)


def test_fact_catalog_drives_friendly_labels_and_primitive_values() -> None:
    label = rotulo_fato_conformidade("projeto.documentacao_gd_identificada")

    assert label == "Documento de acesso, conexão ou comissionamento de GD no pacote"
    assert "projeto.documentacao_gd_identificada" not in label
    assert formatar_valor_fato("projeto.documentacao_gd_identificada", True) == "Sim"
    assert formatar_valor_fato("projeto.documentacao_gd_identificada", False) == "Não"
    assert formatar_valor_fato("projeto.escala", "1:500") == "1:500"
    assert formatar_valor_fato("vao.comprimento_m", Decimal("45.5")) == "45.5 m"
    assert formatar_valor_fato("conexao.angulo_graus", 30) == "30°"
    assert formatar_valor_fato("projeto.escala", None) == "Ausente"
    assert formatar_valor_fato("cabo.tecnologia", "CONVENCIONAL_CA_CAA") == ("Convencional CA CAA")


def test_operators_quantifiers_and_conditions_are_presented_in_portuguese() -> None:
    condition = CondicaoConformidade(
        chave_fato="cabo.tecnologia",
        operador=OperadorCondicao.EM,
        valores_esperados=("PROTEGIDA", "ISOLADA"),
        quantificador=QuantificadorCondicao.QUALQUER,
    )

    rendered = formatar_condicao(condition)

    assert formatar_operador(OperadorCondicao.MENOR_OU_IGUAL) == "menor ou igual a"
    assert formatar_quantificador(QuantificadorCondicao.TODOS) == "todos os valores"
    assert "entre os valores Protegida, Isolada" in rendered
    assert "qualquer valor" in rendered
    assert "cabo.tecnologia" not in rendered
    assert "MENOR_OU_IGUAL" not in rendered


def test_targets_receive_natural_scope_labels_without_uppercase_enumerations() -> None:
    targets = (
        AlvoConformidade(
            id=uuid4(),
            tipo=TipoEscopoConformidade.PROJETO,
            rotulo="Expansão solar",
        ),
        AlvoConformidade(
            id=uuid4(),
            tipo=TipoEscopoConformidade.DOCUMENTO,
            rotulo="desenho.pdf",
        ),
        AlvoConformidade(
            id=uuid4(),
            tipo=TipoEscopoConformidade.PAGINA,
            rotulo="desenho.pdf · página 2",
        ),
        AlvoConformidade(
            id=uuid4(),
            tipo=TipoEscopoConformidade.REGIAO,
            rotulo="P2",
        ),
        AlvoConformidade(
            id=uuid4(),
            tipo=TipoEscopoConformidade.ELEMENTO,
            rotulo="ESTRUTURA_MT CE1",
        ),
    )

    assert tuple(formatar_alvo(item) for item in targets) == (
        "Projeto Expansão solar",
        "Documento desenho.pdf",
        "Página 2 · Documento desenho.pdf",
        "Poste P2",
        "Estrutura MT CE1",
    )
