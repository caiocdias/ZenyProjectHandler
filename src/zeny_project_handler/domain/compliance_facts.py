"""Vocabulário explícito e validação semântica dos fatos de conformidade."""

from __future__ import annotations

from decimal import Decimal

from zeny_project_handler.domain.compliance import (
    CondicaoConformidade,
    DefinicaoFatoConformidade,
    DisponibilidadeProvedorFato,
    OperadorCondicao,
    RegistroRegrasConformidade,
    TipoEscopoConformidade,
    TipoValorFato,
)
from zeny_project_handler.domain.errors import DomainValidationError

_PRESENCA = frozenset({OperadorCondicao.EXISTE, OperadorCondicao.AUSENTE})
_IGUALDADE = frozenset(
    {
        OperadorCondicao.IGUAL,
        OperadorCondicao.DIFERENTE,
        OperadorCondicao.EM,
        OperadorCondicao.NAO_EM,
    }
)
_ORDEM = frozenset(
    {
        OperadorCondicao.MENOR,
        OperadorCondicao.MENOR_OU_IGUAL,
        OperadorCondicao.MAIOR,
        OperadorCondicao.MAIOR_OU_IGUAL,
    }
)
_TEXTO = _PRESENCA | _IGUALDADE | {OperadorCondicao.CONTEM}
_NUMERO = _PRESENCA | _IGUALDADE | _ORDEM
_BOOLEANO = _PRESENCA | _IGUALDADE


def _fact(
    key: str,
    scopes: tuple[TipoEscopoConformidade, ...],
    value_type: TipoValorFato,
    operators: frozenset[OperadorCondicao],
    description: str,
    *,
    available: bool = True,
) -> DefinicaoFatoConformidade:
    return DefinicaoFatoConformidade(
        chave=key,
        escopos=frozenset(scopes),
        tipo_valor=value_type,
        operadores=operators,
        descricao=description,
        disponibilidade=(
            DisponibilidadeProvedorFato.DISPONIVEL
            if available
            else DisponibilidadeProvedorFato.PLANEJADO
        ),
    )


_PROJECT = (TipoEscopoConformidade.PROJETO,)
_DOCUMENT = (TipoEscopoConformidade.DOCUMENTO,)
_REGION = (TipoEscopoConformidade.REGIAO,)
_PROJECT_REGION = (TipoEscopoConformidade.PROJETO, TipoEscopoConformidade.REGIAO)

CATALOGO_FATOS_CONFORMIDADE = (
    _fact(
        "rede.contexto_urbano",
        _PROJECT_REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica contexto urbano confirmado para o projeto ou região.",
    ),
    _fact(
        "rede.contexto_rural",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica contexto rural confirmado para a região.",
    ),
    _fact(
        "projeto.nota_servico",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Nota de Serviço ou número confirmado do projeto.",
    ),
    _fact(
        "projeto.escala",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Escala declarada no projeto.",
    ),
    _fact(
        "projeto.formato_folha",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Formato de folha consolidado para o projeto.",
    ),
    _fact(
        "projeto.numero_folha",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Número de folha identificado no projeto.",
    ),
    _fact(
        "projeto.data_projeto",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Data do projeto em representação textual normalizada.",
    ),
    _fact(
        "projeto.circuito",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Circuito ou alimentador identificado no projeto.",
    ),
    _fact(
        "documento.nota_servico",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Nota de Serviço encontrada no documento.",
    ),
    _fact(
        "documento.escala",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Escala encontrada no documento.",
    ),
    _fact(
        "documento.formato_folha",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Formato informado ou inferido pelas dimensões do documento.",
    ),
    _fact(
        "documento.numero_folha",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Número de folha encontrado no documento.",
    ),
    _fact(
        "documento.data_projeto",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Data do projeto encontrada no documento.",
    ),
    _fact(
        "documento.circuito",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Circuito ou alimentador encontrado no documento.",
    ),
    _fact(
        "documento.servidao_mencionada",
        _DOCUMENT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica menção positiva a servidão ou faixa de domínio.",
    ),
    _fact(
        "documento.carimbo_candidato_quantidade",
        _DOCUMENT,
        TipoValorFato.INTEIRO,
        _NUMERO,
        "Quantidade de anotações PDF candidatas a carimbo.",
    ),
    _fact(
        "documento.assinatura_pdf_preenchida",
        _DOCUMENT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica campo PDF de assinatura positivamente preenchido.",
    ),
    _fact(
        "regiao.equipamento_instalar",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica equipamento a instalar reconhecido na região.",
    ),
    _fact(
        "regiao.equipamento_classe",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Classe catalogada do equipamento reconhecido na região.",
    ),
    _fact(
        "regiao.risco_abalroamento_avaliado",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica evidência positiva de avaliação de risco de abalroamento.",
    ),
    _fact(
        "cabo.tecnologia",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Tecnologia catalogada do cabo reconhecido na região.",
    ),
    _fact(
        "cabo.instalar_tecnologia",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Tecnologia catalogada de cada cabo reconhecido como instalação na região.",
    ),
    _fact(
        "regiao.estrutura_mt_instalar_codigo",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Código da única estrutura de MT reconhecida como instalação na região.",
    ),
    _fact(
        "regiao.poste_ativo_formato",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Formato do único poste reconhecido e não marcado para remoção na região.",
    ),
    _fact(
        "conexao.angulo_graus",
        _REGION,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Deflexão calculada da conexão, em graus.",
        available=False,
    ),
    _fact(
        "vao.comprimento_m",
        _REGION,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Comprimento rastreável do vão, em metros.",
    ),
    _fact(
        "vao.aplicabilidade_excecao_45_60_resolvida",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica que a aplicabilidade da faixa excepcional de 45 m a 60 m foi resolvida.",
    ),
    _fact(
        "vao.excecao_45_60_demonstrada",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica demonstração positiva da exceção de vão entre 45 m e 60 m.",
    ),
)

_FACTS_BY_KEY = {item.chave: item for item in CATALOGO_FATOS_CONFORMIDADE}


def fato_conformidade_por_chave(chave: str) -> DefinicaoFatoConformidade | None:
    return _FACTS_BY_KEY.get(chave)


def validar_semantica_registro(
    registro: RegistroRegrasConformidade,
) -> tuple[str, ...]:
    """Recuse declarações incompatíveis e avise sobre provedores ainda planejados."""
    warnings: list[str] = []
    for rule in registro.regras:
        planned_keys: set[str] = set()
        for group_name, conditions in (
            ("when", rule.aplicabilidade),
            ("unless", rule.excecoes),
            ("must", rule.requisitos),
        ):
            for index, condition in enumerate(conditions, start=1):
                definition = _FACTS_BY_KEY.get(condition.chave_fato)
                field = f"{group_name}[{index}]"
                if definition is None:
                    raise _semantic_error(rule.id, field, "fact", "chave de fato desconhecida")
                if rule.escopo not in definition.escopos:
                    raise _semantic_error(
                        rule.id,
                        field,
                        "fact",
                        f"fato não está disponível no escopo {rule.escopo.value}",
                    )
                _validate_condition(rule.id, field, condition, definition)
                if definition.disponibilidade is DisponibilidadeProvedorFato.PLANEJADO:
                    planned_keys.add(definition.chave)
        if planned_keys:
            warnings.append(
                f"Regra {rule.id}: provedor planejado para " + ", ".join(sorted(planned_keys))
            )
    return tuple(warnings)


def _validate_condition(
    rule_id: str,
    field: str,
    condition: CondicaoConformidade,
    definition: DefinicaoFatoConformidade,
) -> None:
    if condition.operador not in definition.operadores:
        raise _semantic_error(
            rule_id,
            field,
            "operator",
            f"operador {condition.operador.value} incompatível com {definition.tipo_valor.value}",
        )
    for value_index, value in enumerate(condition.valores_esperados):
        if not _matches_type(value, definition.tipo_valor):
            raise _semantic_error(
                rule_id,
                field,
                f"expected[{value_index}]",
                f"valor incompatível com {definition.tipo_valor.value}",
            )


def _matches_type(value: object, expected: TipoValorFato) -> bool:
    if expected is TipoValorFato.TEXTO:
        return isinstance(value, str)
    if expected is TipoValorFato.BOOLEANO:
        return isinstance(value, bool)
    if expected is TipoValorFato.INTEIRO:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, (int, Decimal)) and not isinstance(value, bool)


def _semantic_error(
    rule_id: str,
    condition: str,
    field: str,
    reason: str,
) -> DomainValidationError:
    return DomainValidationError(f"Regra '{rule_id}' · campo {condition}.{field}: {reason}")
