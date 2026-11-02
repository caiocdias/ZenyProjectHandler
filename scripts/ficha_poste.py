"""Ficha do poste: formato versionado da leitura por poste de uma folha e sua validação.

A ficha (referência humana ou predição do analisador) é descrita por
``docs/schemas/ficha-poste.schema.json``. ``validar_ficha`` aplica o esquema e as regras que ele
não expressa: ids únicos, vãos entre postes existentes, geometria das bbox, classes do inventário
de simbologia, escopo regional e exigências da predição. ``carregar_ficha`` lê um JSON UTF-8 e
levanta ``ValueError`` quando a ficha é inválida.

Coordenadas na convenção ``symbols-e02-v1``: página exibida, valores em [0, 1], origem no canto
superior esquerdo, bbox ``[x0, y0, x1, y1]``. Regra R5: ``null`` (ou lista vazia) significa
ausente na folha; o que não foi possível determinar vai em ``pendentes``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any

from scripts.curation_reference import carregar_inventario, validar_esquema
from scripts.curation_round import ROOT

CAMINHO_ESQUEMA = ROOT / "docs" / "schemas" / "ficha-poste.schema.json"
# O poste é o próprio poste, não um símbolo associado a ele. As ESTRUTURA_POSTE_* são promovidas
# a Poste pelo analisador; "_POSTE_" no nome não serve, pois pegaria estais (*_CRUZETA_POSTE*).
CLASSES_DO_POSTE = frozenset({"POSTE", "POSTE_AT", "ESTRUTURA_POSTE_MT", "ESTRUTURA_POSTE_AT"})
CLASSE_RASCUNHO_DE_POSTE = re.compile(r"^RASCUNHO_[A-Z]+_POSTE_[A-Z_]+$")

PADRAO_SHA256 = re.compile(r"[0-9a-f]{64}")

Ficha = Mapping[str, Any]
Caixa = tuple[float, float, float, float]


@cache
def _esquema() -> dict[str, Any]:
    dados = json.loads(CAMINHO_ESQUEMA.read_text(encoding="utf-8"))
    assert isinstance(dados, dict)
    return dados


@cache
def _classes_do_inventario() -> frozenset[str]:
    return frozenset().union(*carregar_inventario().classes_por_familia.values())


def _repetidos(valores: Sequence[str]) -> list[str]:
    return sorted(valor for valor, vezes in Counter(valores).items() if vezes > 1)


def _erros_bbox(rotulo: str, bbox: Sequence[float], *, com_area: bool) -> list[str]:
    x0, y0, x1, y1 = bbox
    if x0 > x1 or y0 > y1:
        return [f"{rotulo}.bbox: invertida (exige x0 <= x1 e y0 <= y1)"]
    if com_area and (x0 == x1 or y0 == y1):
        return [f"{rotulo}.bbox: símbolo exige área positiva (x0 < x1 e y0 < y1)"]
    return []


def _erros_pendentes(rotulo: str, pendentes: Sequence[str]) -> list[str]:
    return [f"{rotulo}.pendentes: valor repetido: {valor}" for valor in _repetidos(list(pendentes))]


def _erro_classe(rotulo: str, classe: str) -> str | None:
    if classe not in _classes_do_inventario():
        return f"{rotulo}.classe: {classe!r} não existe no inventário de simbologia"
    if classe in CLASSES_DO_POSTE or CLASSE_RASCUNHO_DE_POSTE.match(classe):
        return f"{rotulo}.classe: {classe!r} é classe do próprio poste, não de símbolo associado"
    return None


def _erros_simbolo(rotulo: str, simbolo: Ficha) -> list[str]:
    erros = _erros_bbox(rotulo, simbolo["bbox"], com_area=True)
    erro_classe = _erro_classe(rotulo, simbolo["classe"])
    return [*erros, erro_classe] if erro_classe else erros


def _erros_poste(posicao: int, poste: Ficha) -> list[str]:
    rotulo = f"postes[{posicao}] (id {poste['id']})"
    erros = _erros_bbox(rotulo, poste["bbox"], com_area=False)
    erros.extend(_erros_pendentes(rotulo, poste["pendentes"]))
    for item, simbolo in enumerate(poste["simbolos"]):
        erros.extend(_erros_simbolo(f"{rotulo}.simbolos[{item}] (id {simbolo['id']})", simbolo))
    return erros


def _erros_ids(ficha: Ficha) -> list[str]:
    ids_poste = [poste["id"] for poste in ficha["postes"]]
    ids_simbolo = [simbolo["id"] for poste in ficha["postes"] for simbolo in poste["simbolos"]]
    return [
        *(f"postes: id de poste repetido: {valor}" for valor in _repetidos(ids_poste)),
        *(f"postes: id de símbolo repetido: {valor}" for valor in _repetidos(ids_simbolo)),
    ]


def _erros_vao(posicao: int, vao: Ficha, ids: frozenset[str]) -> list[str]:
    rotulo = f"vaos[{posicao}]"
    erros = _erros_pendentes(rotulo, vao["pendentes"])
    erros.extend(
        f"{rotulo}.{ponta}: poste inexistente: {vao[ponta]}"
        for ponta in ("de", "para")
        if vao[ponta] not in ids
    )
    if vao["de"] == vao["para"]:
        erros.append(f"{rotulo}: de e para devem ser postes diferentes (laço em {vao['de']})")
    return erros


def _erros_escopo(ficha: Ficha) -> list[str]:
    escopo = ficha["escopo_anotacao"]
    regioes = escopo.get("regioes")
    erros = []
    if escopo["tipo"] == "regional" and not regioes:
        erros.append("escopo_anotacao.regioes: escopo regional exige ao menos 1 região")
    if escopo["tipo"] == "completo" and regioes is not None:
        erros.append("escopo_anotacao.regioes: escopo completo não aceita regioes")
    for posicao, regiao in enumerate(regioes or []):
        erros.extend(
            _erros_bbox(f"escopo_anotacao.regioes[{posicao}]", regiao["bbox"], com_area=False)
        )
    if ficha["tipo"] == "predicao":
        if escopo["tipo"] != "completo":
            erros.append("tipo: predição exige escopo_anotacao completo")
        if "gerador" not in ficha:
            erros.append("gerador: predição exige gerador")
    return erros


def _centro_na_regiao(poste: Ficha, regiao: Ficha) -> bool:
    x0, y0, x1, y1 = poste["bbox"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx0, ry0, rx1, ry1 = regiao["bbox"]
    return bool(poste["pagina"] == regiao["pagina"] and rx0 <= cx <= rx1 and ry0 <= cy <= ry1)


def _erros_postes_nas_regioes(ficha: Ficha) -> list[str]:
    escopo = ficha["escopo_anotacao"]
    if ficha["tipo"] != "referencia" or escopo["tipo"] != "regional":
        return []
    regioes = escopo.get("regioes") or []
    return [
        f"postes (id {poste['id']}): centro fora das regiões anotadas da página {poste['pagina']}"
        for poste in ficha["postes"]
        if not any(_centro_na_regiao(poste, regiao) for regiao in regioes)
    ]


def _erros_sha256(ficha: Ficha) -> list[str]:
    # O esquema usa re.search, em que "$" casa antes de um "\n" final: fullmatch fecha a brecha.
    if PADRAO_SHA256.fullmatch(ficha["pdf_sha256"]):
        return []
    return ["pdf_sha256: deve ter exatamente 64 hexadecimais minúsculos"]


def _em_branco(rotulo: str, valor: Any) -> list[str]:
    # Texto só de espaços viraria None na normalização do avaliador e se confundiria com null.
    if isinstance(valor, str) and not valor.strip():
        return [f"{rotulo}: texto em branco"]
    return []


def _erros_em_branco_poste(posicao: int, poste: Ficha) -> list[str]:
    rotulo = f"postes[{posicao}]"
    erros = _em_branco(f"{rotulo}.id", poste["id"])
    erros.extend(_em_branco(f"{rotulo}.identificador", poste["identificador"]))
    erros.extend(_em_branco(f"{rotulo}.poste", poste["poste"]))
    for item, estrutura in enumerate(poste["estruturas"]):
        erros.extend(_em_branco(f"{rotulo}.estruturas[{item}]", estrutura))
    for item, simbolo in enumerate(poste["simbolos"]):
        erros.extend(_em_branco(f"{rotulo}.simbolos[{item}].id", simbolo["id"]))
        erros.extend(_em_branco(f"{rotulo}.simbolos[{item}].classe", simbolo["classe"]))
    return erros


def _erros_em_branco_vao(posicao: int, vao: Ficha) -> list[str]:
    rotulo = f"vaos[{posicao}]"
    return [
        erro
        for campo in ("de", "para", "cabo")
        for erro in _em_branco(f"{rotulo}.{campo}", vao[campo])
    ]


def _erros_em_branco(ficha: Ficha) -> list[str]:
    erros: list[str] = []
    for posicao, poste in enumerate(ficha["postes"]):
        erros.extend(_erros_em_branco_poste(posicao, poste))
    for posicao, vao in enumerate(ficha["vaos"]):
        erros.extend(_erros_em_branco_vao(posicao, vao))
    return erros


def validar_ficha(dados: Mapping[str, Any]) -> list[str]:
    """Erros da ficha (lista vazia = válida), em português e com o caminho do campo.

    Erros de esquema interrompem as regras semânticas, que pressupõem a estrutura válida.
    """
    erros = validar_esquema(dados, _esquema())
    if erros:
        return erros
    ids = frozenset(poste["id"] for poste in dados["postes"])
    erros = _erros_sha256(dados)
    erros.extend(_erros_em_branco(dados))
    erros.extend(_erros_ids(dados))
    for posicao, poste in enumerate(dados["postes"]):
        erros.extend(_erros_poste(posicao, poste))
    for posicao, vao in enumerate(dados["vaos"]):
        erros.extend(_erros_vao(posicao, vao, ids))
    erros.extend(_erros_escopo(dados))
    erros.extend(_erros_postes_nas_regioes(dados))
    return erros


def carregar_ficha(caminho: Path) -> dict[str, Any]:
    """Lê a ficha (UTF-8), valida e devolve o dicionário; ``ValueError`` lista os erros."""
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise ValueError(f"ficha inválida em {Path(caminho).name}: a raiz deve ser um objeto")
    erros = validar_ficha(dados)
    if erros:
        raise ValueError("; ".join(erros))
    return dados
