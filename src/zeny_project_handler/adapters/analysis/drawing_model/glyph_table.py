"""Tabela versionada de glifos (JSON) e resolução de uma assinatura contra ela.

O mesmo desenho em caixa alta e em caixa baixa ("O"/"o", "V"/"v", "Z"/"z"; "I"/"l" na Arial)
só se distingue pela altura relativa a h. Por isso a altura tem tolerância própria,
`TOLERANCIA_ALTURA`, menor que a da caixa: nas folhas reais, 99,5 % dos casamentos ficam a até
0,053 h em altura, e a forma do outro caso fica a 0,058 h ou mais. A altura só reprova: entre
os candidatos de altura compatível, o melhor tem de ser do mesmo caractere que o melhor pela
forma; se não for (ou se não houver), o glifo fica desconhecido, e um candidato de outro
caractere nunca é promovido por ela. A base segue só a tolerância
da caixa: um limite próprio nela anulava algarismos legítimos sem separar caso nenhum. O h é o
do trecho (não o das entradas casadas), então a condição não se ajusta à leitura. Quando outro
caractere candidato tem o contorno tão próximo quanto o do melhor (até `margem_ambiguidade` a
mais), só a caixa decidiria: a resolução é ambígua (falha fechada).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import Any, Final, Literal, NoReturn

from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import (
    PONTOS_POR_SUBCAMINHO,
    AssinaturaGlifo,
    diferenca_caixa,
    distancia_assinaturas,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Ponto

VERSAO_TABELA_GLIFOS: Final = "tabela-glifos-v1"
_PACOTE_DADOS: Final = "zeny_project_handler.adapters.analysis.data"
_ARQUIVO: Final = "tabela-glifos-v1.json"
_LIMITE_COORDENADA: Final = 4.0
_CASAS: Final = 4
# Diferença máxima de altura (em h) entre o glifo e a entrada casada.
TOLERANCIA_ALTURA: Final = 0.055


@dataclass(frozen=True, slots=True)
class EntradaGlifo:
    id: str
    caractere: str | None
    assinatura: AssinaturaGlifo


@dataclass(frozen=True, slots=True)
class TabelaGlifos:
    versao: str
    sha256: str
    tolerancia: float
    margem_ambiguidade: float
    espaco: float
    quebra: float
    glifos: tuple[EntradaGlifo, ...]


@dataclass(frozen=True, slots=True)
class Resolucao:
    situacao: Literal["reconhecido", "ignorar", "desconhecido", "ambiguo"]
    caractere: str | None
    distancia: float


def _altura_compativel(entrada: AssinaturaGlifo, assinatura: AssinaturaGlifo) -> bool:
    return abs(entrada.caixa[1] - assinatura.caixa[1]) <= TOLERANCIA_ALTURA


def _distancia_contorno(entrada: AssinaturaGlifo, assinatura: AssinaturaGlifo) -> float:
    """Distância só do desenho: a caixa da entrada igualada à do glifo."""
    return distancia_assinaturas(replace(entrada, caixa=assinatura.caixa), assinatura)


def _candidatos(
    tabela: TabelaGlifos, assinatura: AssinaturaGlifo
) -> tuple[list[tuple[float, EntradaGlifo]], float]:
    candidatos: list[tuple[float, EntradaGlifo]] = []
    menor = math.inf
    for entrada in tabela.glifos:
        if entrada.assinatura.subcaminhos != assinatura.subcaminhos:
            continue
        if diferenca_caixa(entrada.assinatura, assinatura) > tabela.tolerancia:
            continue
        distancia = distancia_assinaturas(entrada.assinatura, assinatura)
        menor = min(menor, distancia)
        if distancia <= tabela.tolerancia:
            candidatos.append((distancia, entrada))
    candidatos.sort(key=lambda c: (c[0], c[1].id))
    return candidatos, menor


def resolver_glifo(tabela: TabelaGlifos, assinatura: AssinaturaGlifo) -> Resolucao:
    pela_forma, menor = _candidatos(tabela, assinatura)
    if not pela_forma:
        return Resolucao("desconhecido", None, menor)
    candidatos = [c for c in pela_forma if _altura_compativel(c[1].assinatura, assinatura)]
    # a altura só reprova: se o melhor pela forma não tem altura compatível, nenhum candidato de
    # outro caractere é promovido no lugar dele
    if not candidatos or candidatos[0][1].caractere != pela_forma[0][1].caractere:
        return Resolucao("desconhecido", None, pela_forma[0][0])
    melhor_distancia, melhor = candidatos[0]
    contorno_melhor: float | None = None
    for distancia, entrada in candidatos[1:]:
        if entrada.caractere == melhor.caractere:
            continue
        if distancia <= melhor_distancia + tabela.margem_ambiguidade:
            return Resolucao("ambiguo", None, melhor_distancia)
        if contorno_melhor is None:
            contorno_melhor = _distancia_contorno(melhor.assinatura, assinatura)
        contorno = _distancia_contorno(entrada.assinatura, assinatura)
        if contorno <= contorno_melhor + tabela.margem_ambiguidade:
            return Resolucao("ambiguo", None, melhor_distancia)
    if melhor.caractere is None:
        return Resolucao("ignorar", None, melhor_distancia)
    return Resolucao("reconhecido", melhor.caractere, melhor_distancia)


def _arredondar(valor: float) -> float:
    return round(valor, _CASAS) + 0.0


def serializar_tabela_glifos(
    *,
    tolerancia: float,
    margem_ambiguidade: float,
    espaco: float,
    quebra: float,
    glifos: Sequence[EntradaGlifo],
) -> str:
    dados = {
        "schema_version": 1,
        "versao": VERSAO_TABELA_GLIFOS,
        "tolerancia": _arredondar(tolerancia),
        "margem_ambiguidade": _arredondar(margem_ambiguidade),
        "espaco": _arredondar(espaco),
        "quebra": _arredondar(quebra),
        "glifos": [
            {
                "id": glifo.id,
                "caractere": glifo.caractere,
                "assinatura": {
                    "subcaminhos": glifo.assinatura.subcaminhos,
                    "caixa": [_arredondar(v) for v in glifo.assinatura.caixa],
                    "contornos": [
                        [[_arredondar(x), _arredondar(y)] for x, y in contorno]
                        for contorno in glifo.assinatura.contornos
                    ],
                },
            }
            for glifo in sorted(glifos, key=lambda g: g.id)
        ],
    }
    return json.dumps(dados, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"


def _invalida(motivo: str) -> NoReturn:
    raise ValueError(f"Tabela de glifos inválida: {motivo}.")


def _constante_proibida(nome: str) -> NoReturn:
    _invalida(f"constante {nome} não é permitida")


def _sem_chaves_repetidas(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    objeto: dict[str, Any] = {}
    for chave, valor in pares:
        if chave in objeto:
            _invalida(f"chave repetida {chave!r}")
        objeto[chave] = valor
    return objeto


def _numero(valor: Any, nome: str) -> float:
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        _invalida(f"{nome} deve ser número finito")
    try:
        numero = float(valor)
    except OverflowError:
        _invalida(f"{nome} deve ser número finito")
    if not math.isfinite(numero):
        _invalida(f"{nome} deve ser número finito")
    return numero


def _objeto(valor: Any, chaves: set[str], nome: str) -> dict[str, Any]:
    if not isinstance(valor, dict) or set(valor) != chaves:
        _invalida(f"{nome} deve ter exatamente as chaves {sorted(chaves)}")
    return valor


def _contorno(valor: Any, nome: str) -> tuple[Ponto, ...]:
    if not isinstance(valor, list) or len(valor) != PONTOS_POR_SUBCAMINHO:
        _invalida(f"{nome} deve ter {PONTOS_POR_SUBCAMINHO} pontos")
    pontos: list[Ponto] = []
    for par in valor:
        if not isinstance(par, list) or len(par) != 2:
            _invalida(f"{nome} deve conter pares [x, y]")
        x, y = _numero(par[0], nome), _numero(par[1], nome)
        if abs(x) > _LIMITE_COORDENADA or abs(y) > _LIMITE_COORDENADA:
            _invalida(f"{nome} tem coordenada fora de ±{_LIMITE_COORDENADA}")
        pontos.append((x, y))
    return tuple(pontos)


def _assinatura(valor: Any, nome: str) -> AssinaturaGlifo:
    dados = _objeto(valor, {"subcaminhos", "caixa", "contornos"}, nome)
    subcaminhos = dados["subcaminhos"]
    contornos = dados["contornos"]
    caixa = dados["caixa"]
    if isinstance(subcaminhos, bool) or not isinstance(subcaminhos, int) or subcaminhos < 1:
        _invalida(f"{nome}.subcaminhos deve ser inteiro positivo")
    if not isinstance(contornos, list) or len(contornos) != subcaminhos:
        _invalida(f"{nome}.subcaminhos deve ser igual ao número de contornos")
    if not isinstance(caixa, list) or len(caixa) != 3:
        _invalida(f"{nome}.caixa deve ter 3 números")
    return AssinaturaGlifo(
        subcaminhos=subcaminhos,
        caixa=(
            _numero(caixa[0], f"{nome}.caixa"),
            _numero(caixa[1], f"{nome}.caixa"),
            _numero(caixa[2], f"{nome}.caixa"),
        ),
        contornos=tuple(_contorno(c, f"{nome}.contornos") for c in contornos),
    )


def _entrada(valor: Any, indice: int) -> EntradaGlifo:
    nome = f"glifos[{indice}]"
    dados = _objeto(valor, {"id", "caractere", "assinatura"}, nome)
    identificador, caractere = dados["id"], dados["caractere"]
    if not isinstance(identificador, str) or not identificador:
        _invalida(f"{nome}.id deve ser texto não vazio")
    if caractere is not None and (
        not isinstance(caractere, str) or len(caractere) != 1 or caractere.isspace()
    ):
        _invalida(f"{nome}.caractere deve ser null ou um caractere sem espaço")
    return EntradaGlifo(
        identificador, caractere, _assinatura(dados["assinatura"], f"{nome}.assinatura")
    )


def _ler_bytes(caminho: Path | None) -> bytes:
    try:
        if caminho is None:
            return files(_PACOTE_DADOS).joinpath(_ARQUIVO).read_bytes()
        return caminho.read_bytes()
    except (OSError, ModuleNotFoundError) as erro:
        raise ValueError(f"Tabela de glifos indisponível: {erro}.") from erro


def carregar_tabela_glifos(caminho: Path | None = None) -> TabelaGlifos:
    """Carrega a tabela (None = a empacotada). `sha256` é dos bytes com CRLF normalizado para LF,
    para que a identidade não dependa do fim de linha do checkout."""
    conteudo = _ler_bytes(caminho).replace(b"\r\n", b"\n")
    try:
        bruto = json.loads(
            conteudo.decode("utf-8"),
            parse_constant=_constante_proibida,
            object_pairs_hook=_sem_chaves_repetidas,
        )
    except RecursionError as erro:
        raise ValueError("Tabela de glifos inválida: aninhamento excessivo.") from erro
    except ValueError as erro:
        if str(erro).startswith("Tabela de glifos"):
            raise
        raise ValueError(f"Tabela de glifos inválida: JSON ilegível ({erro}).") from erro
    dados = _objeto(
        bruto,
        {
            "schema_version",
            "versao",
            "tolerancia",
            "margem_ambiguidade",
            "espaco",
            "quebra",
            "glifos",
        },
        "tabela",
    )
    version = dados["schema_version"]
    if type(version) is not int or version != 1:
        _invalida("schema_version deve ser 1")
    if dados["versao"] != VERSAO_TABELA_GLIFOS:
        _invalida(f"versao deve ser {VERSAO_TABELA_GLIFOS}")
    if not isinstance(dados["glifos"], list):
        _invalida("glifos deve ser lista")
    parametros = {
        nome: _numero(dados[nome], nome)
        for nome in ("tolerancia", "margem_ambiguidade", "espaco", "quebra")
    }
    if any(valor <= 0 for valor in parametros.values()):
        _invalida("parâmetros devem ser positivos")
    glifos = tuple(_entrada(valor, i) for i, valor in enumerate(dados["glifos"]))
    if len({glifo.id for glifo in glifos}) != len(glifos):
        _invalida("ids de glifo repetidos")
    return TabelaGlifos(
        versao=VERSAO_TABELA_GLIFOS,
        sha256=hashlib.sha256(conteudo).hexdigest(),
        glifos=glifos,
        **parametros,
    )
