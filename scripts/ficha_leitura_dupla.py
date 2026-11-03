"""Leitura dupla cega de fichas do poste: comparação, regiões de conferência e consolidação.

Dois leitores (A e B) leem a mesma folha sem ver um ao outro. ``comparar_leituras`` casa as duas
fichas com as regras do avaliador (``scripts.ficha_poste_avaliador``) e lista cada divergência com
a página e a caixa a reler; ``regioes_de_conferencia`` funde essas caixas por página no que o
terceiro leitor (C) recebe: só ``id``, ``pagina`` e ``bbox``, nunca valores. Os ids de divergência
seguem a ficha A; poste que só B traz aparece como ``prefixo_so_b(...) + id``: ``"b-"``, repetido
(``"b-b-"``, …) até nenhum id só de B prefixado coincidir com id de A; o prefixo escolhido vale
para todos os postes só de B daquela comparação, e assim os ids continuam inequívocos.

``consolidar`` monta a ficha de referência a partir de A, B e (opcional) C sem palpite: o que A e
B concordam entra; o que divergem só entra quando C confirma um só dos dois (C que confirma A e B
ao mesmo tempo, dentro da tolerância, deixa o valor pendente); o resto fica pendente (campo) ou
sai do escopo (zona excluída). A consolidação não lê ids da comparação: recalcula os
postes casados, o prefixo dos postes só de B e a ordem dos vãos de cada par com as mesmas funções
(``prefixo_so_b`` e ``vaos_do_par_em_ordem``), e recusa uma comparação que não seja a das
leituras recebidas; assim os ids e índices da comparação e da referência coincidem.
Puro, sem E/S, e independente da ordem das listas de entrada.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Final

from scripts.ficha_poste import validar_ficha
from scripts.ficha_poste_avaliador import (
    CAMPOS_DO_POSTE,
    atributo_do_vao_acerta,
    avaliar,
    campo_acerta,
    casar_postes,
    casar_simbolos,
    casar_vaos_do_par,
    normalizar_texto,
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


def prefixo_so_b(ids_a: Iterable[str], ids_so_b: Iterable[str]) -> str:
    """Menor repetição de ``"b-"`` que, aplicada a todo id só de B, não coincide com id de A."""
    ocupados = set(ids_a)
    candidatos = list(ids_so_b)
    prefixo = PREFIXO_SO_B
    while any(prefixo + id_b in ocupados for id_b in candidatos):
        prefixo += PREFIXO_SO_B
    return prefixo


class _Leituras:
    """Postes de A e B casados, indexados pelo id no espaço de A.

    Poste casado usa o id de A; poste só de B usa ``prefixo + id``, com o prefixo de
    ``prefixo_so_b`` (``"b-"``, repetido o mínimo para não coincidir com nenhum id de A). O
    mesmo prefixo vale para todos os postes só de B, de modo que as chaves continuam únicas.
    """

    def __init__(self, a: Registro, b: Registro) -> None:
        self.casados = casar_postes(a["postes"], b["postes"])
        self.por_a = {poste["id"]: poste for poste in a["postes"]}
        self.por_b = {poste["id"]: poste for poste in b["postes"]}
        self.b_para_a = {id_b: id_a for id_a, id_b, _ in self.casados}
        self.prefixo_so_b = prefixo_so_b(self.por_a, self.so_b())
        a_para_b = {id_a: id_b for id_a, id_b, _ in self.casados}
        self.postes: dict[str, list[Registro]] = {}
        for id_a, poste in self.por_a.items():
            par = [self.por_b[a_para_b[id_a]]] if id_a in a_para_b else []
            self.postes[id_a] = [poste, *par]
        for id_b in self.so_b():
            self.postes[self.chave_de_b(id_b)] = [self.por_b[id_b]]

    def chave_de_b(self, id_b: str) -> str:
        return self.b_para_a.get(id_b, self.prefixo_so_b + id_b)

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
        chave = leituras.chave_de_b(id_b)
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


def _ordem_vao(vao: Registro) -> tuple[str, str, str, str, tuple[str, ...]]:
    return (
        vao["de"],
        vao["para"],
        repr(vao["comprimento_m"]),
        vao["cabo"] or "",
        tuple(sorted(vao["pendentes"])),
    )


VaosEmOrdem = tuple[list[tuple[Registro, Registro]], list[Registro], list[Registro]]


def vaos_do_par_em_ordem(refs: Sequence[Registro], preds: Sequence[Registro]) -> VaosEmOrdem:
    """Vãos de um par de postes na ordem dos índices: ``(casados, sobra_refs, sobra_preds)``.

    ``casados`` segue a ordem de ``casar_vaos_do_par`` e o índice de um vão casado é a posição
    nessa lista. As sobras de cada lado vêm numa ordem determinística única e o índice de uma
    sobra é ``len(casados) + posição`` na sua lista. ``comparar_leituras`` e ``consolidar`` usam
    esta função, de modo que um índice aponta o mesmo vão nos dois.
    """
    casados = casar_vaos_do_par(refs, preds)
    usados_refs = {id(ref) for ref, _ in casados}
    usados_preds = {id(pred) for _, pred in casados}
    sobra_refs = sorted((v for v in refs if id(v) not in usados_refs), key=_ordem_vao)
    sobra_preds = sorted((v for v in preds if id(v) not in usados_preds), key=_ordem_vao)
    return casados, sobra_refs, sobra_preds


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
            if _diverge(atributo, va, vb, atributo_do_vao_acerta(atributo, va, vb))
        ]

    def comparar(self, refs: Sequence[Registro], preds: Sequence[Registro]) -> list[dict[str, Any]]:
        casados, sobra_a, sobra_b = vaos_do_par_em_ordem(refs, preds)
        divergencias = self.atributos(casados)
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


# --- consolidação --------------------------------------------------------------------------------

ZONA_POSTE_DISPUTADO: Final = "poste_disputado"
ZONA_VAO_DISPUTADO: Final = "vao_disputado"
ZONA_ILEGIVEL: Final = "ilegivel"
MOTIVOS_DE_ZONA: Final = (ZONA_ILEGIVEL, ZONA_POSTE_DISPUTADO, ZONA_VAO_DISPUTADO)
_PAGINA_INTEIRA: Final[Caixa] = (0.0, 0.0, 1.0, 1.0)

Acerta = Callable[[str, Registro, Registro], bool]
Zona = tuple[int, Caixa, str]


def _simbolos_acertam(_campo: str, x: Registro, y: Registro) -> bool:
    """Os símbolos dos dois postes casam por inteiro (``casar_simbolos``)."""
    donos = casar_simbolos(x["simbolos"], y["simbolos"])
    return len(donos) == len(x["simbolos"]) == len(y["simbolos"])


_REGRA_DO_CAMPO: Final[Mapping[str, Acerta]] = {
    **dict.fromkeys(CAMPOS_DO_POSTE, campo_acerta),
    "simbolos": _simbolos_acertam,
    **dict.fromkeys(ATRIBUTOS_DO_VAO, atributo_do_vao_acerta),
}
_CAMPOS_CONSOLIDADOS_DO_POSTE: Final = (*CAMPOS_DO_POSTE, "simbolos")


def _valor_nulo(campo: str) -> Any:
    return [] if campo in ("estruturas", "simbolos") else None


def _centro(poste: Registro) -> tuple[float, float]:
    x0, y0, x1, y1 = poste["bbox"]
    return (x0 + x1) / 2, (y0 + y1) / 2


def _no_retangulo(ponto: tuple[float, float], caixa: Sequence[float]) -> bool:
    return caixa[0] <= ponto[0] <= caixa[2] and caixa[1] <= ponto[1] <= caixa[3]


def _em_alguma(poste: Registro, regioes: Iterable[Registro]) -> bool:
    centro = _centro(poste)
    return any(
        int(regiao["pagina"]) == int(poste["pagina"]) and _no_retangulo(centro, regiao["bbox"])
        for regiao in regioes
    )


def _regioes_ilegiveis(leitura: Registro) -> list[Registro]:
    extras = leitura.get("atributos_extras") or {}
    metadados = extras.get("leitura") or {}
    return list(metadados.get("regioes_ilegiveis") or [])


class _Terceiro:
    """Leitura C casada às leituras A e B: poste e vãos de C por chave, e cobertura de C.

    C casa primeiro com A (``casar_postes``); os postes de C que sobram casam com os de B ainda
    sem C. ``cobre`` vale para postes cujos centros estão numa região de C e fora das
    ``regioes_ilegiveis`` de C; sem C, nada é coberto.
    """

    def __init__(self, c: Registro | None, leituras: _Leituras) -> None:
        self.existe = c is not None
        self.poste: dict[str, Registro] = {}
        self.vaos: dict[tuple[str, ...], list[Registro]] = {}
        self.regioes: list[Registro] = []
        self.ilegiveis: list[Registro] = []
        self.completo = False
        if c is not None:
            self._casar(c, leituras)
            escopo = c["escopo_anotacao"]
            self.completo = escopo["tipo"] == "completo"
            self.regioes = list(escopo.get("regioes") or [])
            self.ilegiveis = _regioes_ilegiveis(c)

    def _casar(self, c: Registro, leituras: _Leituras) -> None:
        por_c = {poste["id"]: poste for poste in c["postes"]}
        for id_a, id_c, _ in casar_postes(list(leituras.por_a.values()), c["postes"]):
            self.poste[id_a] = por_c[id_c]
        usados = {poste["id"] for poste in self.poste.values()}
        restantes_b = [
            poste
            for poste in leituras.por_b.values()
            if leituras.chave_de_b(poste["id"]) not in self.poste
        ]
        restantes_c = [poste for poste in c["postes"] if poste["id"] not in usados]
        for id_b, id_c, _ in casar_postes(restantes_b, restantes_c):
            self.poste[leituras.chave_de_b(id_b)] = por_c[id_c]
        chave_de_c = {poste["id"]: chave for chave, poste in self.poste.items()}
        vaos = [v for v in c["vaos"] if v["de"] in chave_de_c and v["para"] in chave_de_c]
        self.vaos = _agrupar_vaos(vaos, chave_de_c.__getitem__)

    def cobre(self, *postes: Registro) -> bool:
        return self.existe and all(
            (self.completo or _em_alguma(poste, self.regioes))
            and not _em_alguma(poste, self.ilegiveis)
            for poste in postes
        )


class _Consolidacao:
    """Aplica as regras de consolidação e acumula as contagens e as zonas excluídas."""

    def __init__(self, a: Registro, b: Registro, c: Registro | None) -> None:
        self.leituras = _Leituras(a, b)
        self.terceiro = _Terceiro(c, self.leituras)
        self.contagem = dict.fromkeys(
            ("resolvidas_por_c", "pendentes", "descartadas_por_maioria", "nao_cobertas_por_c"), 0
        )
        self.zonas: set[Zona] = set()
        self.postes: dict[str, dict[str, Any]] = {}
        self.de_b = {id(poste) for poste in b["postes"]}
        self.prefixo_simbolos_b = prefixo_so_b(
            (s["id"] for poste in a["postes"] for s in poste["simbolos"]),
            [s["id"] for poste in b["postes"] for s in poste["simbolos"]],
        )

    # regras 1 e 2: de quem vem o valor do campo (None = pendente)
    def _origem(
        self, campo: str, x: Registro, y: Registro, terceiro: Registro | None, cobre: bool
    ) -> Registro | None:
        acerta = _REGRA_DO_CAMPO[campo]
        if campo in x["pendentes"] and campo in y["pendentes"]:
            return None
        if not _diverge(campo, x, y, acerta(campo, x, y)):
            return x
        if cobre and terceiro is not None and campo not in terceiro["pendentes"]:
            confirmadas = [
                leitura
                for leitura in (x, y)
                if campo not in leitura["pendentes"] and acerta(campo, leitura, terceiro)
            ]
            if len(confirmadas) == 1:  # C que confirma os dois (tolerância, IoU) não desempata
                self.contagem["resolvidas_por_c"] += 1
                return confirmadas[0]
        self.contagem["pendentes"] += 1
        if not cobre:
            self.contagem["nao_cobertas_por_c"] += 1
        return None

    def _valor(self, campo: str, origem: Registro) -> Any:
        if campo != "simbolos":
            return copy.deepcopy(origem[campo])
        prefixo = self.prefixo_simbolos_b if id(origem) in self.de_b else ""
        simbolos = [{**copy.deepcopy(s), "id": prefixo + s["id"]} for s in origem["simbolos"]]
        return sorted(simbolos, key=lambda simbolo: str(simbolo["id"]))

    def _resolvido(
        self,
        campos: Sequence[str],
        x: Registro,
        y: Registro,
        terceiro: Registro | None,
        cobre: bool,
    ) -> dict[str, Any]:
        registro = copy.deepcopy(dict(x))
        pendentes: list[str] = []
        for campo in campos:
            origem = self._origem(campo, x, y, terceiro, cobre)
            if origem is None:
                registro[campo] = _valor_nulo(campo)
                pendentes.append(campo)
            else:
                registro[campo] = self._valor(campo, origem)
        registro["pendentes"] = pendentes
        return registro

    def _excluir(self, poste: Registro, motivo: str) -> None:
        caixa = _com_margem(_envolvente([poste["bbox"]]), MARGEM_CONFERENCIA)
        self.zonas.add((int(poste["pagina"]), _envolvente([caixa]), motivo))

    # regra 3: postes
    def _poste(
        self, chave: str, x: Registro, y: Registro, terceiro: Registro | None, cobre: bool
    ) -> None:
        poste = self._resolvido(_CAMPOS_CONSOLIDADOS_DO_POSTE, x, y, terceiro, cobre)
        poste["id"] = chave
        self.postes[chave] = poste

    def _poste_de_um_leitor(self, chave: str, x: Registro) -> None:
        poste_c = self.terceiro.poste.get(chave)
        if poste_c is not None:
            self._poste(chave, x, poste_c, None, True)
        elif self.terceiro.cobre(x):
            self.contagem["descartadas_por_maioria"] += 1
        else:
            self._excluir(x, ZONA_POSTE_DISPUTADO)

    def consolidar_postes(self) -> None:
        leituras = self.leituras
        for id_a, id_b, _ in leituras.casados:
            pa = leituras.por_a[id_a]
            terceiro = self.terceiro.poste.get(id_a)
            self._poste(id_a, pa, leituras.por_b[id_b], terceiro, self.terceiro.cobre(pa))
        for id_a in leituras.so_a():
            self._poste_de_um_leitor(id_a, leituras.por_a[id_a])
        for id_b in leituras.so_b():
            self._poste_de_um_leitor(leituras.chave_de_b(id_b), leituras.por_b[id_b])

    # regra 4: vãos
    def _parceiros_em_c(
        self, chave: tuple[str, ...], vaos_a: Sequence[Registro], sobra_b: Sequence[Registro]
    ) -> dict[int, Registro]:
        """Vão de C casado a cada vão de A e, entre os vãos de C que sobram, a cada sobra de B."""
        vaos_c = self.terceiro.vaos.get(chave, [])
        parceiros = {id(va): vc for va, vc in casar_vaos_do_par(vaos_a, vaos_c)}
        usados = {id(vc) for vc in parceiros.values()}
        restantes = [vc for vc in vaos_c if id(vc) not in usados]
        parceiros.update({id(vb): vc for vb, vc in casar_vaos_do_par(sobra_b, restantes)})
        return parceiros

    def _vao(
        self,
        extremos: tuple[str, str],
        x: Registro,
        y: Registro,
        terceiro: Registro | None,
        cobre: bool,
    ) -> dict[str, Any]:
        vao = self._resolvido(ATRIBUTOS_DO_VAO, x, y, terceiro, cobre)
        vao["de"], vao["para"] = extremos
        return vao

    def _vaos_do_par(
        self, chave: tuple[str, ...], vaos_a: Sequence[Registro], vaos_b: Sequence[Registro]
    ) -> list[dict[str, Any]]:
        casados, sobra_a, sobra_b = vaos_do_par_em_ordem(vaos_a, vaos_b)
        parceiros = self._parceiros_em_c(chave, vaos_a, sobra_b)
        postes = [self.postes[extremo] for extremo in chave]
        cobre = self.terceiro.cobre(*postes)
        traduzir = self.leituras.chave_de_b
        vaos = [
            self._vao((va["de"], va["para"]), va, vb, parceiros.get(id(va)), cobre)
            for va, vb in casados
        ]
        sobras = [((v["de"], v["para"]), v) for v in sobra_a]
        sobras.extend(((traduzir(v["de"]), traduzir(v["para"])), v) for v in sobra_b)
        for extremos, vao in sobras:
            vao_c = parceiros.get(id(vao))
            if vao_c is not None:
                vaos.append(self._vao(extremos, vao, vao_c, None, True))
            elif cobre:
                self.contagem["descartadas_por_maioria"] += 1
            else:
                for poste in postes:
                    self._excluir(poste, ZONA_VAO_DISPUTADO)
        return vaos

    def consolidar_vaos(self, a: Registro, b: Registro) -> list[dict[str, Any]]:
        grupos_a = _agrupar_vaos(a["vaos"], lambda id_a: id_a)
        grupos_b = _agrupar_vaos(b["vaos"], self.leituras.chave_de_b)
        vaos: list[dict[str, Any]] = []
        for chave in sorted(set(grupos_a) | set(grupos_b)):
            if all(extremo in self.postes for extremo in chave):
                vaos_a, vaos_b = grupos_a.get(chave, []), grupos_b.get(chave, [])
                vaos.extend(self._vaos_do_par(chave, vaos_a, vaos_b))
        return vaos

    # regra 5: regiões ilegíveis de A e B
    def excluir_ilegiveis(self, *leituras: Registro) -> None:
        for leitura in leituras:
            for regiao in _regioes_ilegiveis(leitura):
                caixa = _envolvente([[float(v) for v in regiao["bbox"]]])
                self.zonas.add((int(regiao["pagina"]), caixa, ZONA_ILEGIVEL))


def _subtrair(caixa: Caixa, zona: Caixa) -> list[Caixa]:
    """``caixa`` menos ``zona``: até 4 retângulos disjuntos (esquerda, direita, acima, abaixo)."""
    if not _sobrepoe(caixa, zona):
        return [caixa]
    x0, y0, x1, y1 = caixa
    z0, w0, z1, w1 = zona
    meio0, meio1 = max(x0, z0), min(x1, z1)
    pedacos = [(x0, y0, z0, y1), (z1, y0, x1, y1), (meio0, y0, meio1, w0), (meio0, w1, meio1, y1)]
    return [p for p in pedacos if p[0] < p[2] and p[1] < p[3]]


def _escopo(zonas: Sequence[Zona], paginas: int) -> dict[str, Any]:
    """Regra 6: sem zonas, ``completo``; com zonas, cada página menos as zonas dela."""
    if not zonas:
        return {"tipo": "completo"}
    regioes: list[dict[str, Any]] = []
    for pagina in range(1, paginas + 1):
        pedacos = [_PAGINA_INTEIRA]
        for pagina_da_zona, caixa, _ in zonas:
            if pagina_da_zona == pagina:
                pedacos = [p for pedaco in pedacos for p in _subtrair(pedaco, caixa)]
        regioes.extend({"pagina": pagina, "bbox": list(p)} for p in sorted(pedacos))
    return {"tipo": "regional", "regioes": regioes}


def _recusar_folha_sem_area_anotavel(escopo: Registro, zonas: Sequence[Zona]) -> None:
    """Zonas que cobrem todas as páginas: a folha não tem referência (nenhuma região mínima)."""
    if escopo["tipo"] != "regional" or escopo["regioes"]:
        return
    motivos = Counter(motivo for _, _, motivo in zonas)
    contagem = ", ".join(f"{motivo}={motivos[motivo]}" for motivo in MOTIVOS_DE_ZONA)
    raise ValueError(
        f"folha sem área anotável: as zonas excluídas cobrem todas as páginas ({contagem})"
    )


def _validar_entradas(
    a: Registro, b: Registro, c: Registro | None, comparacao: Registro, paginas: int
) -> None:
    if isinstance(paginas, bool) or not isinstance(paginas, int) or paginas < 1:
        raise ValueError("paginas: deve ser um inteiro positivo")
    if comparar_leituras(a, b) != comparacao:  # também valida A e B e o mesmo pdf_sha256
        raise ValueError("a comparação não corresponde às leituras a e b recebidas")
    if c is None:
        return
    erros = validar_ficha(c)
    if erros:
        raise ValueError("leitura c: " + "; ".join(erros))
    if c["pdf_sha256"] != a["pdf_sha256"]:
        raise ValueError("leitura c: pdf_sha256 difere do das leituras a e b")


def _fora_das_zonas(postes: Mapping[str, Registro], zonas: Sequence[Zona]) -> set[str]:
    """Regra 6: postes cujo centro cai numa zona excluída."""
    return {
        chave
        for chave, poste in postes.items()
        if any(
            pagina == int(poste["pagina"]) and _no_retangulo(_centro(poste), caixa)
            for pagina, caixa, _ in zonas
        )
    }


def consolidar(
    a: Mapping[str, Any],
    b: Mapping[str, Any],
    c: Mapping[str, Any] | None,
    comparacao: Mapping[str, Any],
    *,
    paginas: int,
) -> dict[str, Any]:
    """Ficha de referência consolidada de A, B e (opcional) C, sem palpite.

    Campo igual em A e B entra com o valor de A; divergente só entra quando C, cobrindo o poste
    (ou os dois extremos do vão), confirma o valor de A ou o de B, e não os dois; senão vai a
    ``pendentes`` com valor nulo. Poste ou vão de um só leitor entra se C o tem, sai se C cobre
    e não o tem e, sem decisão de C, vira zona excluída do escopo, como as ``regioes_ilegiveis``
    de A e B. As contagens e as zonas ficam em ``atributos_extras.consolidacao``. Se as zonas
    cobrem todas as páginas, a folha não tem referência: ``ValueError`` com a contagem de zonas
    por motivo.
    """
    _validar_entradas(a, b, c, comparacao, paginas)
    consolidacao = _Consolidacao(a, b, c)
    consolidacao.consolidar_postes()
    vaos = consolidacao.consolidar_vaos(a, b)
    consolidacao.excluir_ilegiveis(a, b)
    zonas = sorted(consolidacao.zonas)
    escopo = _escopo(zonas, paginas)
    _recusar_folha_sem_area_anotavel(escopo, zonas)
    fora = _fora_das_zonas(consolidacao.postes, zonas)
    extras = {k: v for k, v in (a.get("atributos_extras") or {}).items() if k != "leitura"}
    referencia = copy.deepcopy(dict(a))
    referencia["tipo"] = "referencia"
    referencia["escopo_anotacao"] = escopo
    referencia["postes"] = [
        poste for chave, poste in sorted(consolidacao.postes.items()) if chave not in fora
    ]
    referencia["vaos"] = [v for v in vaos if v["de"] not in fora and v["para"] not in fora]
    referencia["atributos_extras"] = {
        **copy.deepcopy(extras),
        "consolidacao": {
            **consolidacao.contagem,
            "excluidas": [
                {"pagina": pagina, "bbox": list(caixa), "motivo": motivo}
                for pagina, caixa, motivo in zonas
            ],
        },
    }
    erros = validar_ficha(referencia)
    if erros:
        raise ValueError("referência consolidada inválida: " + "; ".join(erros))
    return referencia
