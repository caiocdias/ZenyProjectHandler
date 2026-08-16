"""Textos amigáveis para a apresentação de regras e achados de conformidade."""

from __future__ import annotations

import re
from decimal import Decimal

from zeny_project_handler.domain.catalog import JsonPrimitive
from zeny_project_handler.domain.compliance import (
    AchadoConformidade,
    AlvoConformidade,
    AvaliacaoCondicaoConformidade,
    CondicaoConformidade,
    GrupoCondicaoConformidade,
    OperadorCondicao,
    QuantificadorCondicao,
    ResultadoCondicaoConformidade,
    ResultadoConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.compliance_facts import fato_conformidade_por_chave

_OPERADORES = {
    OperadorCondicao.EXISTE: "presente",
    OperadorCondicao.AUSENTE: "ausente",
    OperadorCondicao.IGUAL: "igual a",
    OperadorCondicao.DIFERENTE: "diferente de",
    OperadorCondicao.MENOR: "menor que",
    OperadorCondicao.MENOR_OU_IGUAL: "menor ou igual a",
    OperadorCondicao.MAIOR: "maior que",
    OperadorCondicao.MAIOR_OU_IGUAL: "maior ou igual a",
    OperadorCondicao.EM: "entre os valores",
    OperadorCondicao.NAO_EM: "fora dos valores",
    OperadorCondicao.CONTEM: "contém",
}
_QUANTIFICADORES = {
    QuantificadorCondicao.TODOS: "todos os valores",
    QuantificadorCondicao.QUALQUER: "qualquer valor",
}
_ESCOPOS = {
    TipoEscopoConformidade.PROJETO: "Projeto",
    TipoEscopoConformidade.DOCUMENTO: "Documento",
    TipoEscopoConformidade.PAGINA: "Página",
    TipoEscopoConformidade.REGIAO: "Região",
    TipoEscopoConformidade.ELEMENTO: "Elemento",
}
_SIGLAS = frozenset({"BT", "CA", "CAA", "GD", "MT", "NS", "OCR", "PDF", "PRORDR"})
_PALAVRAS_ENUMERACAO = {"FUSIVEL": "fusível", "NAO": "não"}
_UNIDADES = (
    ("_kva", " kVA"),
    ("_dan", " daN"),
    ("_graus", "°"),
    ("_m", " m"),
)
_ROTULO_PAGINA = re.compile(r"^(?P<documento>.+?)\s*·\s*página\s+(?P<pagina>.+)$", re.I)
_ROTULO_POSTE = re.compile(r"^P\s*\d+[A-Z]?$", re.I)


def rotulo_fato_conformidade(chave: str) -> str:
    """Resolva uma chave pelo catálogo sem reproduzir seu vocabulário na UI."""
    definition = fato_conformidade_por_chave(chave)
    if definition is None:
        return _capitalizar(chave.rsplit(".", maxsplit=1)[-1].replace("_", " "))
    description = definition.descricao.rstrip().removesuffix(".")
    if description.startswith("Indica "):
        description = description.removeprefix("Indica ")
    return _capitalizar(description)


def formatar_valor_fato(chave: str, valor: JsonPrimitive) -> str:
    """Formate um valor sem alterar o valor mantido no domínio."""
    if valor is None:
        return "Ausente"
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, (int, Decimal)):
        rendered = str(valor)
        unit = next((label for suffix, label in _UNIDADES if chave.endswith(suffix)), "")
        return f"{rendered}{unit}"
    return _formatar_enumeracao(valor)


def formatar_operador(operador: OperadorCondicao) -> str:
    return _OPERADORES[operador]


def formatar_quantificador(quantificador: QuantificadorCondicao) -> str:
    return _QUANTIFICADORES[quantificador]


def formatar_escopo(escopo: TipoEscopoConformidade) -> str:
    return _ESCOPOS[escopo]


def formatar_alvo(alvo: AlvoConformidade) -> str:
    """Acrescente o tipo natural sem expor enumerações ou caminhos internos."""
    label = alvo.rotulo.strip()
    if alvo.tipo is TipoEscopoConformidade.PAGINA:
        match = _ROTULO_PAGINA.fullmatch(label)
        if match is not None:
            return f"Página {match.group('pagina')} · Documento {match.group('documento')}"
    if alvo.tipo is TipoEscopoConformidade.REGIAO and _ROTULO_POSTE.fullmatch(label):
        return f"Poste {label.upper().replace(' ', '')}"
    natural = _formatar_rotulo_tecnico(label)
    if alvo.tipo is TipoEscopoConformidade.ELEMENTO:
        return natural
    prefix = formatar_escopo(alvo.tipo)
    if natural.casefold().startswith((f"{prefix} ".casefold(), f"{prefix} ·".casefold())):
        return natural
    return f"{prefix} {natural}"


def formatar_condicao(condicao: CondicaoConformidade) -> str:
    label = rotulo_fato_conformidade(condicao.chave_fato)
    operator = formatar_operador(condicao.operador)
    if condicao.operador in {OperadorCondicao.EXISTE, OperadorCondicao.AUSENTE}:
        return f"{label}: {operator}"
    expected = _formatar_valores(condicao.chave_fato, condicao.valores_esperados)
    quantifier = formatar_quantificador(condicao.quantificador)
    return f"{label}: {operator} {expected} ({quantifier})"


def formatar_lista_condicoes(
    condicoes: tuple[CondicaoConformidade, ...],
    *,
    vazio: str,
) -> str:
    return "; ".join(formatar_condicao(item) for item in condicoes) or vazio


def formatar_valores_achado(
    avaliacoes: tuple[AvaliacaoCondicaoConformidade, ...],
    resultado: ResultadoConformidade,
) -> tuple[str, str]:
    """Produza as colunas Observado e Esperado a partir da mesma seleção decisiva."""
    selected = _avaliacoes_decisivas(avaliacoes, resultado)
    observed = "; ".join(_formatar_observado(item) for item in selected)
    expected = "; ".join(_formatar_esperado(item) for item in selected)
    return observed or "—", expected or "—"


def formatar_texto_achado(
    achado: AchadoConformidade,
    alvo: AlvoConformidade,
) -> str:
    """Use no tooltip e no callout exatamente os valores mostrados na tabela."""
    observed, expected = formatar_valores_achado(
        achado.avaliacoes_condicoes,
        achado.resultado,
    )
    return f"{achado.titulo} — {formatar_alvo(alvo)}. Observado: {observed}. Esperado: {expected}."


def _avaliacoes_decisivas(
    avaliacoes: tuple[AvaliacaoCondicaoConformidade, ...],
    resultado: ResultadoConformidade,
) -> tuple[AvaliacaoCondicaoConformidade, ...]:
    desired = {
        ResultadoConformidade.DIVERGENCIA: ResultadoCondicaoConformidade.NAO_ATENDE,
        ResultadoConformidade.NAO_AVALIAVEL: ResultadoCondicaoConformidade.DESCONHECIDO,
        ResultadoConformidade.CONFORME: ResultadoCondicaoConformidade.ATENDE,
    }[resultado]
    requirements = tuple(
        item for item in avaliacoes if item.grupo is GrupoCondicaoConformidade.REQUISITO
    )
    selected = tuple(item for item in requirements if item.resultado is desired) or requirements
    return selected or tuple(item for item in avaliacoes if item.resultado is desired)


def _formatar_observado(avaliacao: AvaliacaoCondicaoConformidade) -> str:
    values = _formatar_valores(avaliacao.chave_fato, avaliacao.valores_observados)
    return f"{rotulo_fato_conformidade(avaliacao.chave_fato)}: {values}"


def _formatar_esperado(avaliacao: AvaliacaoCondicaoConformidade) -> str:
    label = rotulo_fato_conformidade(avaliacao.chave_fato)
    operator = formatar_operador(avaliacao.operador)
    if avaliacao.operador in {OperadorCondicao.EXISTE, OperadorCondicao.AUSENTE}:
        return f"{label}: {operator}"
    values = _formatar_valores(avaliacao.chave_fato, avaliacao.valores_esperados)
    quantifier = formatar_quantificador(avaliacao.quantificador)
    return f"{label}: {operator} {values} ({quantifier})"


def _formatar_valores(chave: str, valores: tuple[JsonPrimitive, ...]) -> str:
    return ", ".join(formatar_valor_fato(chave, item) for item in valores) or "Ausente"


def _formatar_rotulo_tecnico(value: str) -> str:
    return " ".join(_formatar_enumeracao(item) for item in value.split())


def _formatar_enumeracao(value: str) -> str:
    if not value or not value.isupper():
        return value
    if not value.replace("_", "").isalnum():
        return value
    words = []
    for token in value.split("_"):
        if token in _SIGLAS or any(character.isdigit() for character in token):
            words.append(token)
        else:
            words.append(_PALAVRAS_ENUMERACAO.get(token, token.casefold()))
    return _capitalizar(" ".join(words))


def _capitalizar(value: str) -> str:
    return value[:1].upper() + value[1:] if value else value
