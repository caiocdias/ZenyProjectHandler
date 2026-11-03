"""Avaliador determinístico de fichas por poste (referência humana contra predição).

Compara duas fichas (``scripts.ficha_poste``) do mesmo PDF e devolve um relatório com postes,
campos, vãos e símbolos. Nada aqui depende da ordem de entrada: todo empate é resolvido por
ordenação explícita. Regra R5: ``null`` na referência conta como "ausente na folha"; o que o
autor não determinou fica em ``pendentes`` e sai do denominador (referência) ou é contado à parte
(predição).
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Final

from scripts.ficha_poste import validar_ficha
from scripts.symbol_benchmark_evaluator import geometry_match

PROTOCOLO_FICHA: Final[Mapping[str, Any]] = {
    "id": "ficha-poste-v1",
    "espaco_distancia": "normalizado-pagina-exibida",
    "distancia_max": 0.02,
    "distancia_max_mesmo_identificador": 0.05,
    "tolerancia_coordenada_m": 0.01,
    "tolerancia_comprimento_m": 0.1,
    "casamento_postes": "guloso-identificador-distancia",
    "casamento_simbolos": "cardinalidade-maxima",
    "inventario": "inventario-simbologia-v1",
}

CAMPOS_DO_POSTE: Final = ("identificador", "estruturas", "poste", "coordenada")
_CASAS_DECIMAIS = 9  # absorve o ruído de ponto flutuante na comparação com a tolerância

Registro = Mapping[str, Any]


def normalizar_texto(valor: str | None) -> str | None:
    """``strip``, espaços internos colapsados, maiúsculas; vazio vira ``None``."""
    if valor is None:
        return None
    texto = " ".join(valor.split()).upper()
    return texto or None


def _taxa(numerador: int, denominador: int) -> float | None:
    return numerador / denominador if denominador else None


def _contagem(tp: int, fp: int, fn: int) -> dict[str, Any]:
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precisao": _taxa(tp, tp + fp),
        "recall": _taxa(tp, tp + fn),
    }


def _centro(item: Registro) -> tuple[float, float]:
    x0, y0, x1, y1 = item["bbox"]
    return (x0 + x1) / 2, (y0 + y1) / 2


# --- casamento de postes -------------------------------------------------------------------------


def _pares_elegiveis(
    referencia: Sequence[Registro], predicao: Sequence[Registro]
) -> list[tuple[tuple[int, float, str, str], str, str, float]]:
    limites = PROTOCOLO_FICHA
    elegiveis = []
    for ref in referencia:
        ident_ref = normalizar_texto(ref["identificador"])
        for pred in predicao:
            if ref["pagina"] != pred["pagina"]:
                continue
            distancia = math.dist(_centro(ref), _centro(pred))
            ident_pred = normalizar_texto(pred["identificador"])
            igual = ident_ref is not None and ident_ref == ident_pred
            limite = limites["distancia_max_mesmo_identificador" if igual else "distancia_max"]
            if round(distancia, _CASAS_DECIMAIS) <= limite:
                chave = (0 if igual else 1, distancia, ref["id"], pred["id"])
                elegiveis.append((chave, ref["id"], pred["id"], distancia))
    return sorted(elegiveis, key=lambda item: item[0])


def casar_postes(
    referencia: Sequence[Mapping[str, Any]], predicao: Sequence[Mapping[str, Any]]
) -> list[tuple[str, str, float]]:
    """Casamento guloso um-para-um: ``(id_ref, id_pred, distancia)``, por id de referência."""
    usados_ref: set[str] = set()
    usados_pred: set[str] = set()
    pares = []
    for _, id_ref, id_pred, distancia in _pares_elegiveis(referencia, predicao):
        if id_ref in usados_ref or id_pred in usados_pred:
            continue
        usados_ref.add(id_ref)
        usados_pred.add(id_pred)
        pares.append((id_ref, id_pred, distancia))
    return sorted(pares)


# --- escopo --------------------------------------------------------------------------------------


def _na_regiao(poste: Registro, regioes: Sequence[Registro]) -> bool:
    cx, cy = _centro(poste)
    return any(
        poste["pagina"] == regiao["pagina"]
        and regiao["bbox"][0] <= cx <= regiao["bbox"][2]
        and regiao["bbox"][1] <= cy <= regiao["bbox"][3]
        for regiao in regioes
    )


def _restringir_ao_escopo(
    referencia: Registro, predicao: Registro
) -> tuple[list[Registro], list[Registro]]:
    """Postes e vãos preditos que entram na métrica (regional descarta o que está fora)."""
    escopo = referencia["escopo_anotacao"]
    if escopo["tipo"] != "regional":
        return list(predicao["postes"]), list(predicao["vaos"])
    regioes = escopo.get("regioes") or []
    postes = [poste for poste in predicao["postes"] if _na_regiao(poste, regioes)]
    ids = {poste["id"] for poste in postes}
    vaos = [vao for vao in predicao["vaos"] if vao["de"] in ids and vao["para"] in ids]
    return postes, vaos


# --- campos --------------------------------------------------------------------------------------


def numeros_iguais(a: float, b: float, tolerancia: float) -> bool:
    """``|a - b| <= tolerancia`` em decimal exato."""
    # Decimais exatos dos reprs: northing UTM (~7,8e6) perde precisão em float na subtração.
    return abs(Decimal(repr(a)) - Decimal(repr(b))) <= Decimal(repr(tolerancia))


_numeros_iguais = numeros_iguais


def _coordenada_acerta(ref: Registro | None, pred: Registro | None) -> bool:
    if ref is None or pred is None:
        return ref is None and pred is None
    tolerancia = PROTOCOLO_FICHA["tolerancia_coordenada_m"]
    return numeros_iguais(ref["leste"], pred["leste"], tolerancia) and numeros_iguais(
        ref["norte"], pred["norte"], tolerancia
    )


def _estruturas(poste: Registro) -> list[str]:
    return sorted(str(normalizar_texto(item)) for item in poste["estruturas"])


def campo_acerta(campo: str, ref: Registro, pred: Registro) -> bool:
    """O campo do poste tem o mesmo valor nos dois lados (pelas regras do ``PROTOCOLO_FICHA``)."""
    if campo == "estruturas":
        return _estruturas(ref) == _estruturas(pred)
    if campo == "coordenada":
        return _coordenada_acerta(ref["coordenada"], pred["coordenada"])
    return normalizar_texto(ref[campo]) == normalizar_texto(pred[campo])


_campo_acerta = campo_acerta


def _bloco_vazio() -> dict[str, Any]:
    return {"acertos": 0, "total": 0, "erros_com_pendencia": 0, "erros_sem_pendencia": 0}


def _registrar(bloco: dict[str, Any], acertou: bool, com_pendencia: bool) -> None:
    bloco["total"] += 1
    if acertou:
        bloco["acertos"] += 1
    else:
        bloco["erros_com_pendencia" if com_pendencia else "erros_sem_pendencia"] += 1


def _fechar_bloco(bloco: dict[str, Any]) -> dict[str, Any]:
    return {
        "acertos": bloco["acertos"],
        "total": bloco["total"],
        "taxa": _taxa(bloco["acertos"], bloco["total"]),
        "erros_com_pendencia": bloco["erros_com_pendencia"],
        "erros_sem_pendencia": bloco["erros_sem_pendencia"],
    }


def _avaliar_campos(
    pares: Sequence[tuple[Registro, Registro, float]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    blocos = {campo: _bloco_vazio() for campo in CAMPOS_DO_POSTE}
    relatorio_pares = []
    for ref, pred, distancia in pares:
        resultado: dict[str, bool | None] = {}
        for campo in CAMPOS_DO_POSTE:
            if campo in ref["pendentes"]:
                resultado[campo] = None
                continue
            acertou = campo_acerta(campo, ref, pred)
            _registrar(blocos[campo], acertou, campo in pred["pendentes"])
            resultado[campo] = acertou
        relatorio_pares.append(
            {
                "referencia": ref["id"],
                "predicao": pred["id"],
                "distancia": distancia,
                "campos": resultado,
            }
        )
    return {campo: _fechar_bloco(bloco) for campo, bloco in blocos.items()}, relatorio_pares


# --- vãos ----------------------------------------------------------------------------------------


def _chave_vao(vao: Registro) -> tuple[bool, float, str, str, str, tuple[str, ...]]:
    comprimento = vao["comprimento_m"]
    return (
        comprimento is None,
        0.0 if comprimento is None else comprimento,
        normalizar_texto(vao["cabo"]) or "",
        vao["de"],
        vao["para"],
        tuple(sorted(vao["pendentes"])),
    )


def casar_vaos_do_par(
    refs: Sequence[Registro], preds: Sequence[Registro]
) -> list[tuple[Registro, Registro]]:
    """Dentro do mesmo par de postes: primeiro cabo igual e não nulo, depois o restante em ordem."""
    refs_ord = sorted(refs, key=_chave_vao)
    preds_ord = sorted(preds, key=_chave_vao)
    casados: list[tuple[Registro, Registro]] = []
    sobra_ref: list[Registro] = []
    sobra_pred = list(preds_ord)
    for ref in refs_ord:
        cabo = normalizar_texto(ref["cabo"])
        achado = next(
            (
                pred
                for pred in sobra_pred
                if cabo is not None and normalizar_texto(pred["cabo"]) == cabo
            ),
            None,
        )
        if achado is None:
            sobra_ref.append(ref)
        else:
            sobra_pred.remove(achado)
            casados.append((ref, achado))
    casados.extend(zip(sobra_ref, sobra_pred, strict=False))
    return casados


_casar_vaos_do_par = casar_vaos_do_par


def _agrupar_por_par(
    vaos: Sequence[Registro], mapa: Mapping[str, str] | None
) -> dict[frozenset[str], list[Registro]]:
    grupos: dict[frozenset[str], list[Registro]] = {}
    for vao in vaos:
        if mapa is None:
            extremos = (vao["de"], vao["para"])
        else:
            if vao["de"] not in mapa or vao["para"] not in mapa:
                continue
            extremos = (mapa[vao["de"]], mapa[vao["para"]])
        grupos.setdefault(frozenset(extremos), []).append(vao)
    return grupos


def _avaliar_vaos(
    vaos_ref: Sequence[Registro], vaos_pred: Sequence[Registro], mapa: Mapping[str, str]
) -> dict[str, Any]:
    grupos_ref = _agrupar_por_par(vaos_ref, mapa)
    grupos_pred = _agrupar_por_par(vaos_pred, None)
    comprimento, cabo = _bloco_vazio(), _bloco_vazio()
    tp = 0
    for chave, refs in grupos_ref.items():
        for ref, pred in casar_vaos_do_par(refs, grupos_pred.get(chave, [])):
            tp += 1
            _avaliar_atributos_do_vao(ref, pred, comprimento, cabo)
    return {
        **_contagem(tp, len(vaos_pred) - tp, len(vaos_ref) - tp),
        "comprimento": _fechar_bloco(comprimento),
        "cabo": _fechar_bloco(cabo),
    }


def atributo_do_vao_acerta(atributo: str, ref: Registro, pred: Registro) -> bool:
    """``comprimento_m`` (ou ``cabo``) igual nos dois vãos, pelas regras do ``PROTOCOLO_FICHA``."""
    if atributo == "cabo":
        return normalizar_texto(ref["cabo"]) == normalizar_texto(pred["cabo"])
    a, b = ref["comprimento_m"], pred["comprimento_m"]
    if a is None or b is None:
        return a is None and b is None
    return numeros_iguais(a, b, PROTOCOLO_FICHA["tolerancia_comprimento_m"])


def _avaliar_atributos_do_vao(
    ref: Registro, pred: Registro, comprimento: dict[str, Any], cabo: dict[str, Any]
) -> None:
    for atributo, bloco in (("comprimento_m", comprimento), ("cabo", cabo)):
        if atributo not in ref["pendentes"]:
            acertou = atributo_do_vao_acerta(atributo, ref, pred)
            _registrar(bloco, acertou, atributo in pred["pendentes"])


# --- símbolos ------------------------------------------------------------------------------------


def _candidatos(ref: Registro, preds: Sequence[Registro]) -> list[str]:
    classe = normalizar_texto(ref["classe"])
    achados = []
    for pred in preds:
        if normalizar_texto(pred["classe"]) != classe:
            continue
        geometria = geometry_match({"bbox": ref["bbox"]}, {"bbox": pred["bbox"]})
        if geometria["eligible"]:
            achados.append((-geometria["iou"], pred["id"]))
    return [identificador for _, identificador in sorted(achados)]


def casar_simbolos(refs: Sequence[Registro], preds: Sequence[Registro]) -> dict[str, str]:
    """Cardinalidade máxima por caminhos aumentantes; devolve ``{id_pred: id_ref}``."""
    refs_ord = sorted(refs, key=lambda item: item["id"])
    arestas = {ref["id"]: _candidatos(ref, preds) for ref in refs_ord}
    donos: dict[str, str] = {}

    def aumentar(id_ref: str, visitados: set[str]) -> bool:
        for id_pred in arestas[id_ref]:
            if id_pred in visitados:
                continue
            visitados.add(id_pred)
            if id_pred not in donos or aumentar(donos[id_pred], visitados):
                donos[id_pred] = id_ref
                return True
        return False

    for ref in refs_ord:
        aumentar(ref["id"], set())
    return donos


_casar_simbolos = casar_simbolos


def _avaliar_simbolos(
    pares: Sequence[tuple[Registro, Registro, float]],
    refs_sem_par: Sequence[Registro],
    preds_sem_par: Sequence[Registro],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    tp = 0
    fp_ids: list[str] = []
    fn_ids: list[str] = []
    for ref, pred, _ in pares:
        if "simbolos" in ref["pendentes"]:
            continue
        donos = casar_simbolos(ref["simbolos"], pred["simbolos"])
        tp += len(donos)
        fp_ids.extend(s["id"] for s in pred["simbolos"] if s["id"] not in donos)
        casados_ref = set(donos.values())
        fn_ids.extend(s["id"] for s in ref["simbolos"] if s["id"] not in casados_ref)
    for ref in refs_sem_par:
        if "simbolos" not in ref["pendentes"]:
            fn_ids.extend(s["id"] for s in ref["simbolos"])
    for pred in preds_sem_par:
        fp_ids.extend(s["id"] for s in pred["simbolos"])
    return _contagem(tp, len(fp_ids), len(fn_ids)), {
        "referencia": sorted(fn_ids),
        "predicao": sorted(fp_ids),
    }


# --- avaliação -----------------------------------------------------------------------------------


def _validar_par(referencia: Registro, predicao: Registro) -> None:
    erros = [f"referencia: {erro}" for erro in validar_ficha(referencia)]
    erros.extend(f"predicao: {erro}" for erro in validar_ficha(predicao))
    if erros:
        raise ValueError("; ".join(erros))
    if referencia["tipo"] != "referencia":
        raise ValueError("referencia: tipo deve ser 'referencia'")
    if predicao["tipo"] != "predicao":
        raise ValueError("predicao: tipo deve ser 'predicao'")
    if referencia["pdf_sha256"] != predicao["pdf_sha256"]:
        raise ValueError("pdf_sha256 diferente entre referência e predição")


def avaliar(referencia: Mapping[str, Any], predicao: Mapping[str, Any]) -> dict[str, Any]:
    """Relatório determinístico da predição contra a referência (ver ``PROTOCOLO_FICHA``)."""
    _validar_par(referencia, predicao)
    postes_pred, vaos_pred = _restringir_ao_escopo(referencia, predicao)
    postes_ref = list(referencia["postes"])
    casados = casar_postes(postes_ref, postes_pred)
    por_ref = {poste["id"]: poste for poste in postes_ref}
    por_pred = {poste["id"]: poste for poste in postes_pred}
    pares = [(por_ref[r], por_pred[p], d) for r, p, d in casados]
    mapa = {r: p for r, p, _ in casados}
    ref_sem_par = [poste for poste in postes_ref if poste["id"] not in mapa]
    pred_casados = set(mapa.values())
    pred_sem_par = [poste for poste in postes_pred if poste["id"] not in pred_casados]
    campos, relatorio_pares = _avaliar_campos(pares)
    simbolos, simbolos_nao_casados = _avaliar_simbolos(pares, ref_sem_par, pred_sem_par)
    return {
        "schema_version": 1,
        "protocolo": copy.deepcopy(dict(PROTOCOLO_FICHA)),
        "pdf_sha256": referencia["pdf_sha256"],
        "escopo": referencia["escopo_anotacao"]["tipo"],
        "gerador_predicao": copy.deepcopy(predicao.get("gerador")),
        "postes": _contagem(len(casados), len(pred_sem_par), len(ref_sem_par)),
        "campos": campos,
        "vaos": _avaliar_vaos(referencia["vaos"], vaos_pred, mapa),
        "simbolos": simbolos,
        "pares": relatorio_pares,
        "nao_casados": {
            "referencia": sorted(poste["id"] for poste in ref_sem_par),
            "predicao": sorted(poste["id"] for poste in pred_sem_par),
        },
        "simbolos_nao_casados": simbolos_nao_casados,
    }
