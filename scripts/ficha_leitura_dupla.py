"""Leitura dupla cega de fichas do poste: comparação das leituras A e B e regiões de conferência.

Dois leitores (A e B) leem a mesma folha sem ver um ao outro. ``comparar_leituras`` casa as duas
fichas com as regras do avaliador (``scripts.ficha_poste_avaliador``) e lista cada divergência com
a página e a caixa a reler; ``regioes_de_conferencia`` funde essas caixas por página no que o
terceiro leitor (C) recebe: só ``id``, ``pagina`` e ``bbox``, nunca valores. Os ids de divergência
seguem a ficha A; poste que só B traz aparece como ``"b-" + id`` (a mesma regra da consolidação).
Puro, sem E/S, e independente da ordem das listas de entrada.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Final

from scripts.ficha_poste_avaliador import (
    CAMPOS_DO_POSTE,
    PROTOCOLO_FICHA,
    avaliar,
    campo_acerta,
    casar_postes,
    casar_simbolos,
    casar_vaos_do_par,
    normalizar_texto,
    numeros_iguais,
)
from scripts.symbol_benchmark_evaluator import geometry_match

ESQUEMA_COMPARACAO: Final = "curadoria-ficha-comparacao-v1"
MARGEM_CONFERENCIA: Final = 0.02
MARGEM_CONFERENCIA_CAMPO: Final = 0.04
PREFIXO_SO_B: Final = "b-"
TIPOS_DE_DIVERGENCIA: Final = (
    "poste_so_a",
    "poste_so_b",
    "campo",
    "simbolos",
    "vao_so_a",
    "vao_so_b",
    "vao_atributo",
)
ATRIBUTOS_DO_VAO: Final = ("comprimento_m", "cabo")

Registro = Mapping[str, Any]
Caixa = tuple[float, float, float, float]


# --- caixas --------------------------------------------------------------------------------------


def _envolvente(caixas: Iterable[Sequence[float]]) -> Caixa:
    lista = list(caixas)
    return (
        min(c[0] for c in lista),
        min(c[1] for c in lista),
        max(c[2] for c in lista),
        max(c[3] for c in lista),
    )


def _com_margem(caixa: Caixa, margem: float) -> list[float]:
    x0, y0, x1, y1 = caixa
    return [
        max(0.0, x0 - margem),
        max(0.0, y0 - margem),
        min(1.0, x1 + margem),
        min(1.0, y1 + margem),
    ]


def _sobrepoe(c1: Sequence[float], c2: Sequence[float]) -> bool:
    return c1[0] < c2[2] and c2[0] < c1[2] and c1[1] < c2[3] and c2[1] < c1[3]


# --- leituras casadas ----------------------------------------------------------------------------


class _Leituras:
    """Postes de A e B casados, indexados pelo id no espaço de A (``"b-" + id`` só em B)."""

    def __init__(self, a: Registro, b: Registro) -> None:
        self.casados = casar_postes(a["postes"], b["postes"])
        self.por_a = {poste["id"]: poste for poste in a["postes"]}
        self.por_b = {poste["id"]: poste for poste in b["postes"]}
        self.b_para_a = {id_b: id_a for id_a, id_b, _ in self.casados}
        a_para_b = {id_a: id_b for id_a, id_b, _ in self.casados}
        self.postes: dict[str, list[Registro]] = {}
        for id_a, poste in self.por_a.items():
            par = [self.por_b[a_para_b[id_a]]] if id_a in a_para_b else []
            self.postes[id_a] = [poste, *par]
        for id_b, poste in self.por_b.items():
            if id_b not in self.b_para_a:
                self.postes[PREFIXO_SO_B + id_b] = [poste]

    def chave_de_b(self, id_b: str) -> str:
        return self.b_para_a.get(id_b, PREFIXO_SO_B + id_b)

    def so_a(self) -> list[str]:
        casados = {id_a for id_a, _, _ in self.casados}
        return sorted(i for i in self.por_a if i not in casados)

    def so_b(self) -> list[str]:
        return sorted(i for i in self.por_b if i not in self.b_para_a)

    def caixas(self, chaves: Iterable[str]) -> list[Sequence[float]]:
        return [poste["bbox"] for chave in chaves for poste in self.postes[chave]]

    def pagina(self, chave: str) -> int:
        return int(self.postes[chave][0]["pagina"])


def _divergencia(
    tipo: str,
    pagina: int,
    bbox: list[float],
    *,
    a: str | None = None,
    b: str | None = None,
    campo: str | None = None,
) -> dict[str, Any]:
    return {"tipo": tipo, "pagina": pagina, "bbox": bbox, "a": a, "b": b, "campo": campo}


def _diverge(campo: str, x: Registro, y: Registro, iguais: bool) -> bool:
    """Pendente em só um lado diverge; pendente nos dois não; senão vale ``iguais``."""
    pendente_x, pendente_y = campo in x["pendentes"], campo in y["pendentes"]
    if pendente_x or pendente_y:
        return pendente_x != pendente_y
    return not iguais


# --- postes e símbolos ---------------------------------------------------------------------------


def _divergencias_de_postes(leituras: _Leituras) -> list[dict[str, Any]]:
    divergencias = [
        _divergencia(
            "poste_so_a",
            leituras.pagina(id_a),
            _com_margem(_envolvente(leituras.caixas([id_a])), MARGEM_CONFERENCIA),
            a=id_a,
        )
        for id_a in leituras.so_a()
    ]
    for id_b in leituras.so_b():
        chave = PREFIXO_SO_B + id_b
        caixa = _com_margem(_envolvente(leituras.caixas([chave])), MARGEM_CONFERENCIA)
        divergencias.append(_divergencia("poste_so_b", leituras.pagina(chave), caixa, b=id_b))
    return divergencias


def _divergencias_de_campos(pa: Registro, pb: Registro) -> list[dict[str, Any]]:
    caixa = _com_margem(_envolvente([pa["bbox"], pb["bbox"]]), MARGEM_CONFERENCIA_CAMPO)
    return [
        _divergencia("campo", int(pa["pagina"]), caixa, a=pa["id"], b=pb["id"], campo=campo)
        for campo in CAMPOS_DO_POSTE
        if _diverge(campo, pa, pb, campo_acerta(campo, pa, pb))
    ]


def _so_geometria(pa: Registro, pb: Registro, donos: Mapping[str, str]) -> int:
    """Símbolos de mesma classe, um de cada leitor, que sobraram sem casar por IoU no par."""
    casados_a = set(donos.values())

    def classes(simbolos: Iterable[Registro], casados: Iterable[str]) -> Counter[str | None]:
        usados = set(casados)
        return Counter(normalizar_texto(s["classe"]) for s in simbolos if s["id"] not in usados)

    sobra_a = classes(pa["simbolos"], casados_a)
    sobra_b = classes(pb["simbolos"], donos)
    return sum(min(quantidade, sobra_b[classe]) for classe, quantidade in sobra_a.items())


def _simbolos_do_par(pa: Registro, pb: Registro) -> tuple[bool, list[float], int]:
    """``(diverge, IoU dos casados, símbolos só de geometria)`` dos símbolos do par."""
    pendente_a, pendente_b = "simbolos" in pa["pendentes"], "simbolos" in pb["pendentes"]
    if pendente_a or pendente_b:
        return pendente_a != pendente_b, [], 0
    donos = casar_simbolos(pa["simbolos"], pb["simbolos"])
    simbolos_a = {s["id"]: s for s in pa["simbolos"]}
    ious = [
        float(geometry_match(simbolos_a[id_a], simbolo)["iou"])
        for simbolo in pb["simbolos"]
        if (id_a := donos.get(simbolo["id"])) is not None
    ]
    diverge = len(donos) != len(pa["simbolos"]) or len(donos) != len(pb["simbolos"])
    return diverge, ious, _so_geometria(pa, pb, donos)


def _divergencia_de_simbolos(pa: Registro, pb: Registro) -> dict[str, Any]:
    caixas = [pa["bbox"], pb["bbox"]]
    caixas.extend(s["bbox"] for s in [*pa["simbolos"], *pb["simbolos"]])
    caixa = _com_margem(_envolvente(caixas), MARGEM_CONFERENCIA)
    return _divergencia("simbolos", int(pa["pagina"]), caixa, a=pa["id"], b=pb["id"])


# --- vãos ----------------------------------------------------------------------------------------


def _atributo_igual(atributo: str, va: Registro, vb: Registro) -> bool:
    if atributo == "cabo":
        return normalizar_texto(va["cabo"]) == normalizar_texto(vb["cabo"])
    x, y = va["comprimento_m"], vb["comprimento_m"]
    if x is None or y is None:
        return x is None and y is None
    return numeros_iguais(x, y, PROTOCOLO_FICHA["tolerancia_comprimento_m"])


def _ordem_vao(vao: Registro) -> tuple[str, str, str, str, tuple[str, ...]]:
    return (
        vao["de"],
        vao["para"],
        repr(vao["comprimento_m"]),
        vao["cabo"] or "",
        tuple(sorted(vao["pendentes"])),
    )


def _agrupar_vaos(
    vaos: Iterable[Registro], traduzir: Callable[[str], str]
) -> dict[tuple[str, ...], list[Registro]]:
    grupos: dict[tuple[str, ...], list[Registro]] = {}
    for vao in vaos:
        chave = tuple(sorted((traduzir(vao["de"]), traduzir(vao["para"]))))
        grupos.setdefault(chave, []).append(vao)
    return grupos


class _VaosDoPar:
    """Divergências dos vãos de um par de postes (chave no espaço de ids de A)."""

    def __init__(self, leituras: _Leituras, chave: tuple[str, ...]) -> None:
        self.leituras = leituras
        self.pagina = min(leituras.pagina(extremo) for extremo in chave)
        self.caixa = _com_margem(_envolvente(leituras.caixas(chave)), MARGEM_CONFERENCIA)

    def divergencia(
        self,
        tipo: str,
        indice: int,
        extremos: tuple[str, str],
        cabos: tuple[str | None, str | None],
        campo: str | None = None,
    ) -> dict[str, Any]:
        return {
            **_divergencia(tipo, self.pagina, list(self.caixa), campo=campo),
            "de": extremos[0],
            "para": extremos[1],
            "indice": indice,
            "cabo_a": cabos[0],
            "cabo_b": cabos[1],
        }

    def atributos(self, casados: Sequence[tuple[Registro, Registro]]) -> list[dict[str, Any]]:
        return [
            self.divergencia(
                "vao_atributo", indice, (va["de"], va["para"]), (va["cabo"], vb["cabo"]), atributo
            )
            for indice, (va, vb) in enumerate(casados)
            for atributo in ATRIBUTOS_DO_VAO
            if _diverge(atributo, va, vb, _atributo_igual(atributo, va, vb))
        ]

    def comparar(self, refs: Sequence[Registro], preds: Sequence[Registro]) -> list[dict[str, Any]]:
        casados = casar_vaos_do_par(refs, preds)
        divergencias = self.atributos(casados)
        usados_a = {id(va) for va, _ in casados}
        usados_b = {id(vb) for _, vb in casados}
        sobra_a = sorted((v for v in refs if id(v) not in usados_a), key=_ordem_vao)
        sobra_b = sorted((v for v in preds if id(v) not in usados_b), key=_ordem_vao)
        traduzir = self.leituras.chave_de_b
        divergencias.extend(
            self.divergencia("vao_so_a", len(casados) + j, (v["de"], v["para"]), (v["cabo"], None))
            for j, v in enumerate(sobra_a)
        )
        divergencias.extend(
            self.divergencia(
                "vao_so_b",
                len(casados) + j,
                (traduzir(v["de"]), traduzir(v["para"])),
                (None, v["cabo"]),
            )
            for j, v in enumerate(sobra_b)
        )
        return divergencias


def _divergencias_de_vaos(leituras: _Leituras, a: Registro, b: Registro) -> list[dict[str, Any]]:
    grupos_a = _agrupar_vaos(a["vaos"], lambda id_a: id_a)
    grupos_b = _agrupar_vaos(b["vaos"], leituras.chave_de_b)
    divergencias: list[dict[str, Any]] = []
    for chave in sorted(set(grupos_a) | set(grupos_b)):
        par = _VaosDoPar(leituras, chave)
        divergencias.extend(par.comparar(grupos_a.get(chave, []), grupos_b.get(chave, [])))
    return divergencias


# --- comparação ----------------------------------------------------------------------------------


def _como_predicao(b: Registro) -> dict[str, Any]:
    predicao = copy.deepcopy(dict(b))
    predicao["tipo"] = "predicao"
    predicao["gerador"] = {"leitor": "b"}
    return predicao


def comparar_leituras(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    """Comparação determinística das leituras A e B da mesma folha (ver docstring do módulo)."""
    concordancia = avaliar(a, _como_predicao(b))  # valida as duas fichas e o mesmo pdf_sha256
    leituras = _Leituras(a, b)
    divergencias = _divergencias_de_postes(leituras)
    ious: list[float] = []
    so_geometria = 0
    for id_a, id_b, _ in leituras.casados:
        pa, pb = leituras.por_a[id_a], leituras.por_b[id_b]
        divergencias.extend(_divergencias_de_campos(pa, pb))
        diverge, ious_do_par, so_geometria_do_par = _simbolos_do_par(pa, pb)
        ious.extend(ious_do_par)
        so_geometria += so_geometria_do_par
        if diverge:
            divergencias.append(_divergencia_de_simbolos(pa, pb))
    divergencias.extend(_divergencias_de_vaos(leituras, a, b))
    return {
        "schema_version": ESQUEMA_COMPARACAO,
        "pdf_sha256": a["pdf_sha256"],
        "pares": [{"a": i, "b": j, "distancia": d} for i, j, d in leituras.casados],
        "concordancia": concordancia,
        "divergencias": [
            {"id": f"d{numero:03d}", **divergencia}
            for numero, divergencia in enumerate(divergencias, start=1)
        ],
        "distancias_casamento": sorted(d for _, _, d in leituras.casados),
        "iou_simbolos": sorted(ious),
        "simbolos_so_geometria": so_geometria,
    }


# --- regiões de conferência ----------------------------------------------------------------------


def _fundir(caixas: Iterable[Caixa]) -> list[Caixa]:
    """Funde caixas que se sobrepõem, repetindo até nenhuma sobrepor outra."""
    atuais = sorted(caixas)
    while True:
        par = next(
            (
                (i, j)
                for i in range(len(atuais))
                for j in range(i + 1, len(atuais))
                if _sobrepoe(atuais[i], atuais[j])
            ),
            None,
        )
        if par is None:
            return atuais
        nova = _envolvente([atuais[par[0]], atuais[par[1]]])
        atuais = sorted([c for k, c in enumerate(atuais) if k not in par] + [nova])


def regioes_de_conferencia(comparacao: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Caixas das divergências fundidas por página; cada região só traz id, página e bbox."""
    por_pagina: dict[int, list[Caixa]] = {}
    for divergencia in comparacao["divergencias"]:
        por_pagina.setdefault(int(divergencia["pagina"]), []).append(
            _envolvente([divergencia["bbox"]])
        )
    regioes = [
        (pagina, caixa) for pagina in sorted(por_pagina) for caixa in _fundir(por_pagina[pagina])
    ]
    return [
        {"id": f"r{numero:03d}", "pagina": pagina, "bbox": list(caixa)}
        for numero, (pagina, caixa) in enumerate(regioes, start=1)
    ]
