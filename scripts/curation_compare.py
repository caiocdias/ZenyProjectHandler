"""Comparador regional da curadoria: inferência congelada contra referência congelada.

Uso:
    python -m scripts.curation_compare --rodada DIR (--onda K | --pdf ID ...)
        [--inferencia vNNN] [--referencia vNNN]

Para cada PDF, lê a referência congelada (por padrão a vigente do checkpoint) e a inferência
concluída (por padrão a do marco ``inferido``), confere os SHA-256 registrados e o SHA-256 do PDF
nos dois lados e mede só dentro das regiões revisadas: uma predição entra no escopo quando o
centro da bbox cai num tile revisado da mesma página e camada e fora de ``regioes_ilegiveis``;
as demais ficam em ``fora_do_escopo`` com o motivo. O casamento 1:1 é o do protocolo
``symbols-e02-v1`` (``scripts/symbol_benchmark_evaluator.py``: ``geometry_match`` e o casamento
de cardinalidade máxima por documento/página/camada/classe), em dois níveis: classe/grupo visual
e ID exato do inventário. O resultado vai para ``pdfs/ID/comparacao-vNNN.json`` (versões nunca
sobrescritas) com TP_IA/FP_IA/FN_IA por método, por família e para a união, denominadores e
divergências rastreáveis; o checkpoint avança para ``comparado`` quando as versões comparadas são
as vigentes. Em escopo regional não há revocação global. A referência é de desenvolvimento gerada
por IA: as métricas são TP_IA/FP_IA/FN_IA, não acurácia de campo.

Classes suportadas (``curadoria-comparacao-v2``): cada método é medido contra a referência
restrita às classes que ele declara em ``supported_classes`` (``predictions.json``). Ocorrências
operacionais de outras classes não entram em FN_IA, nas divergências ``fn``, nos denominadores
nem na revocação daquele método, nos níveis classe e ID exato (``ocorrencias_fora_do_suporte``
conta quantas saíram; ``classes_suportadas`` registra o conjunto). Negativos, provisórias e
demais incertas continuam inteiros, e FP_IA conta todas as predições do método (predição de
classe não suportada é FP comum, com ``detalhe.classe_suportada = false``). Método sem
``supported_classes`` ou com lista vazia mantém a medição contra todas as ocorrências
(``classes_suportadas = null``) e gera o alerta ``metodo_sem_classes_suportadas`` em
``alertas``; para a cobertura ele conta como suportando todas as classes. A união não muda:
FN_IA da união segue sobre todas as ocorrências avaliáveis. O FN da união cuja classe nenhum
método medido cobre vira divergência própria (``tipo: fn``, ``nivel: uniao``,
``method_id: uniao``, ``sem_metodo: true``, ``detalhe.motivo: classe_sem_metodo``): é lacuna de
cobertura, não defeito de método. As demais divergências trazem ``sem_metodo: false``.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from hashlib import sha256
from math import dist
from pathlib import Path
from typing import Any

from scripts.curation_reference import (
    DIRETORIO_REFERENCIA,
    FAMILIA_LOCAL,
    _criar_exclusivo,
    _dentro,
    _indice_vigente,
)
from scripts.curation_round import (
    RodadaError,
    _trava,
    carregar_checkpoint,
    diretorio_pdf,
    hash_arquivo,
    hash_diretorio,
    json_canonico,
    ler_json,
    selecionar_pdfs,
    transicionar,
    validar_transicao,
)
from scripts.symbol_benchmark_evaluator import (
    PROTOCOL,
    _geometry,
    _group_metrics,
    _measure,
    _union,
    geometry_match,
)

# v2: métricas por método restritas a ``supported_classes``, ``alertas``, ``sem_metodo`` nas
# divergências e divergências ``nivel: uniao`` para classe sem método.
ESQUEMA_COMPARACAO = "curadoria-comparacao-v2"
PREFIXO_COMPARACAO = "comparacao-v"
NOME_COMPARACAO = re.compile(r"comparacao-v(\d{3,})\.json")
VERSAO_INFERENCIA = re.compile(r"v\d{3,}")
VERSAO_REFERENCIA = re.compile(r"v\d{3}")
# Métodos que informam ``provenance.variant_id`` (ID exato do inventário) nas predições.
METODOS_COM_ID_EXATO = frozenset({"declarative-vector-packages"})
CONTEXTO_POR_PAPEL: Mapping[str, str] = {
    "operacional": "operational",
    "informativo": "informative",
    "negativo": "negative",
}
CATEGORIAS_INCERTAS = ("provisorio", "papel_desconhecido", "ilegivel", "local")
ESTADO_DESCARTADO = "descartado_branco"
# Método que só emite ``local_candidates`` (fora das métricas por família do protocolo).
ESCOPO_LOCAL = "local_candidates"
MOTIVO_EXCLUSAO_LOCAL = "emite só local_candidates; fora das métricas por família"
# ``method_id`` das divergências do nível ``uniao`` (não é um método).
METODO_UNIAO = "uniao"
# ``detalhe.motivo`` do FN da união cuja classe nenhum método declara suportar.
MOTIVO_SEM_METODO = "classe_sem_metodo"
# Alerta de método sem ``supported_classes`` utilizável (mede contra todas as ocorrências).
ALERTA_SEM_CLASSES = "metodo_sem_classes_suportadas"
LIMITACOES = (
    "Referência de desenvolvimento gerada por IA: TP_IA/FP_IA/FN_IA não são gabarito, "
    "confirmação humana nem acurácia de campo.",
    "Métricas valem só dentro dos tiles revisados e fora das regiões ilegíveis; com escopo "
    "regional não há revocação global (revocacao_global = null).",
    "Observações provisórias, de papel desconhecido, ilegíveis ou sem família no inventário não "
    "entram nos denominadores; predições que só casam com elas ficam em nao_resolvidas.",
    "Observação com alternativas conta como TP de classe e nunca como TP de ID exato.",
    "ID exato só é medido para métodos que informam a variante do inventário.",
    "A união é a do protocolo symbols-e02-v1: equivalência geométrica exata entre métodos, "
    "duplicatas internas de um método mantidas.",
    "FN_IA e revocação de cada método valem só para as classes que ele declara em "
    "supported_classes; a união mede todas, e o FN de classe sem método é lacuna de cobertura "
    "(sem_metodo = true), não defeito de método.",
)

Registro = dict[str, Any]
Caixa = tuple[float, float, float, float]
Local = tuple[int, str]


class ComparacaoRecusadaError(RodadaError):
    """Comparação recusada antes de qualquer escrita; checkpoint e comparações intactos."""


# --- escopo regional --------------------------------------------------------------------


def _caixa(valores: Sequence[float]) -> Caixa:
    return float(valores[0]), float(valores[1]), float(valores[2]), float(valores[3])


def _centro(bbox: Sequence[float]) -> tuple[float, float]:
    return (float(bbox[0]) + float(bbox[2])) / 2, (float(bbox[1]) + float(bbox[3])) / 2


@dataclass
class Escopo:
    """Tiles revisados (inclusive gêmeos da camada anotada) e regiões ilegíveis por página."""

    paginas: frozenset[int]
    tiles: Mapping[Local, list[Registro]]
    declarados: frozenset[str]
    revisados: frozenset[str]
    ilegiveis: Mapping[Local, list[Caixa]]

    def _contem(self, local: Local, x: float, y: float) -> list[Registro]:
        return [tile for tile in self.tiles.get(local, []) if _dentro(x, y, _caixa(tile["bbox"]))]

    def motivo_fora(self, pagina: Any, camada: Any, bbox: Sequence[float]) -> str | None:
        """``None`` se o centro está no escopo; senão o motivo de ficar fora."""
        if pagina not in self.paginas:
            return "pagina_fora_do_indice"
        x, y = _centro(bbox)
        contem = self._contem((pagina, camada), x, y)
        if any(tile["id"] in self.revisados for tile in contem):
            ilegiveis = self.ilegiveis.get((pagina, camada), [])
            return "regiao_ilegivel" if any(_dentro(x, y, c) for c in ilegiveis) else None
        if contem and all(tile["estado"] == ESTADO_DESCARTADO for tile in contem):
            return "tile_descartado"
        return "tile_nao_revisado"

    def tile_evidencia(self, pagina: int, camada: str, bbox: Sequence[float]) -> str | None:
        """Tile revisado que contém o centro, o de centro mais próximo em caso de sobreposição."""
        x, y = _centro(bbox)
        candidatos = [t for t in self._contem((pagina, camada), x, y) if t["id"] in self.revisados]
        if not candidatos:
            return None
        escolhido = min(candidatos, key=lambda t: (dist((x, y), _centro(t["bbox"])), t["id"]))
        return str(escolhido["id"])


def montar_escopo(indice: Registro, referencia: Registro) -> Escopo:
    """Escopo da referência sobre o índice; tiles declarados precisam existir no índice."""
    por_id = {str(tile["id"]): tile for tile in indice["tiles"]}
    declarados = frozenset(str(item) for item in referencia["tiles_revisados"])
    ausentes = sorted(declarados - por_id.keys())
    if ausentes:
        raise ValueError(f"tiles revisados ausentes do índice vigente: {', '.join(ausentes)}")
    iguais = {
        int(pagina["pagina"])
        for pagina in indice["paginas"]
        if pagina.get("camada_anotada_igual_base")
    }
    gemeos = {(t["pagina"], t["camada"], t["linha"], t["coluna"]): i for i, t in por_id.items()}
    revisados = set(declarados)
    for tile_id in declarados:
        tile = por_id[tile_id]
        if tile["camada"] == "base" and tile["pagina"] in iguais:
            gemeo = gemeos.get((tile["pagina"], "annotation", tile["linha"], tile["coluna"]))
            if gemeo is not None:
                revisados.add(gemeo)
    tiles: dict[Local, list[Registro]] = defaultdict(list)
    for tile in indice["tiles"]:
        tiles[(tile["pagina"], tile["camada"])].append(tile)
    ilegiveis: dict[Local, list[Caixa]] = defaultdict(list)
    for regiao in referencia["regioes_ilegiveis"]:
        caixa = _caixa(regiao["bbox"])
        ilegiveis[(regiao["pagina"], regiao["camada"])].append(caixa)
        if regiao["camada"] == "base" and regiao["pagina"] in iguais:
            ilegiveis[(regiao["pagina"], "annotation")].append(caixa)
    return Escopo(
        paginas=frozenset(int(pagina["pagina"]) for pagina in indice["paginas"]),
        tiles=dict(tiles),
        declarados=declarados,
        revisados=frozenset(revisados),
        ilegiveis=dict(ilegiveis),
    )


# --- conversão para o protocolo do avaliador ------------------------------------------------


def _categoria(observacao: Registro) -> str:
    if observacao["familia"] == FAMILIA_LOCAL:
        return "local"
    if observacao["estado"] == "ilegivel":
        return "ilegivel"
    if observacao["estado"] == "provisorio":
        return "provisorio"
    if observacao["papel"] == "desconhecido":
        return "papel_desconhecido"
    return "operacional" if observacao["papel"] == "operacional" else "negativo"


def _chave_exata(classe: str, ids: Sequence[str]) -> str:
    return f"{classe}#{'|'.join(ids)}"


def _ocorrencia(observacao: Registro, document_id: str, *, exato: bool) -> Registro:
    """Observação da referência no formato de ocorrência do avaliador ``symbols-e02-v1``."""
    categoria = _categoria(observacao)
    avaliabilidade = {"operacional": "confirmed", "negativo": "confirmed"}.get(
        categoria, "unassessable" if categoria in {"ilegivel", "local"} else "ambiguous"
    )
    classe = str(observacao["class_id"])
    if exato and categoria == "operacional":
        if observacao.get("id_inventario"):
            classe = _chave_exata(classe, [observacao["id_inventario"]])
        else:
            categoria, avaliabilidade = "ambigua", "ambiguous"
    item: Registro = {
        "id": observacao["id"],
        "document_id": document_id,
        "page": observacao["pagina"],
        "layer": observacao["camada"],
        "family": observacao["familia"],
        "class_id": classe,
        "bbox": list(observacao["bbox"]),
        "context": CONTEXTO_POR_PAPEL.get(observacao["papel"], "operational"),
        "evaluability": avaliabilidade,
        "strata": [categoria],
    }
    if observacao.get("trace"):
        item["trace"] = observacao["trace"]
    return item


def variantes(predicao: Registro) -> list[str]:
    """IDs do inventário informados pela predição (ou pelos membros de uma candidata da união)."""
    membros = predicao.get("observations") or [predicao]
    encontrados = set()
    for membro in membros:
        variante = (membro.get("provenance") or {}).get("variant_id")
        if isinstance(variante, str) and variante:
            encontrados.add(variante)
    return sorted(encontrados)


def _operacional(predicao: Registro) -> bool:
    return bool(predicao.get("context", "operational") == "operational")


def _validar_predicao(predicao: Registro, document_id: str, metodos: set[str]) -> None:
    identidade = predicao.get("id")
    if not isinstance(identidade, str) or not identidade:
        raise ValueError("predição sem id")
    if predicao.get("document_id") != document_id:
        raise ValueError(f"{identidade}: predição de outro documento")
    if predicao.get("method_id") not in metodos:
        raise ValueError(f"{identidade}: método desconhecido {predicao.get('method_id')}")
    if predicao.get("layer") not in {"base", "annotation"}:
        raise ValueError(f"{identidade}: camada desconhecida")
    pagina = predicao.get("page")
    if not isinstance(pagina, int) or isinstance(pagina, bool):
        raise ValueError(f"{identidade}: página inválida")
    if not isinstance(predicao.get("class_id"), str) or not isinstance(predicao.get("family"), str):
        raise ValueError(f"{identidade}: família ou classe inválida")
    _geometry(predicao)


# --- métricas --------------------------------------------------------------------------------


def _metricas(tp: int, fp: int, fn: int, *, completo: bool) -> Registro:
    revocacao = tp / (tp + fn) if tp + fn else None
    return {
        "tp_ia": tp,
        "fp_ia": fp,
        "fn_ia": fn,
        "precisao": tp / (tp + fp) if tp + fp else None,
        "revocacao_regional": revocacao,
        "revocacao_global": revocacao if completo else None,
    }


def _por_familia(resultado: Registro, familias: Iterable[str], *, completo: bool) -> Registro:
    grupos = _group_metrics(resultado, familias, lambda item: [item["family"]])
    return {
        familia: {
            **_metricas(valor["tp"], valor["fp"], valor["fn"], completo=completo),
            "ocorrencias": valor["reference_count"],
            "predicoes": valor["prediction_count"],
        }
        for familia, valor in grupos.items()
    }


def _nao_resolvidas(resultado: Registro, categorias: Sequence[str]) -> Registro:
    contagem: Counter[str] = Counter(
        item["matches"][0]["reference"]["strata"][0] for item in resultado["unresolved"]
    )
    return {"total": len(resultado["unresolved"]), **{c: contagem[c] for c in categorias}}


@dataclass
class Avaliacao:
    """Resultado de um conjunto de predições (um método ou a união) nos dois níveis."""

    classe: Registro
    exato: Registro | None
    bloco: Registro = field(default_factory=dict)


@dataclass
class _Base:
    document_id: str
    completo: bool
    ocorrencias: list[Registro]
    ocorrencias_exatas: list[Registro]
    familias: list[str]
    observacoes: Mapping[str, Registro]


def _bloco_classe(resultado: Registro, base: _Base) -> Registro:
    micro = resultado["micro"]
    return {
        **_metricas(micro["tp"], micro["fp"], micro["fn"], completo=base.completo),
        "predicoes_avaliadas": micro["tp"] + micro["fp"] + len(resultado["unresolved"]),
        "duplicatas": len(resultado["duplicates"]),
        "papel_errado": sum(
            item["reason"] == "nonoperational_context" for item in resultado["false_positives"]
        ),
        "nao_resolvidas": _nao_resolvidas(resultado, CATEGORIAS_INCERTAS),
        "nao_operacionais": len(resultado["nonoperational_predictions"]),
    }


def _ids_errados(resultado_classe: Registro, base: _Base) -> list[Registro]:
    errados = []
    for par in resultado_classe["matches"]:
        esperado = base.observacoes[par["reference_id"]].get("id_inventario")
        preditas = variantes(par["prediction"])
        if esperado and preditas and preditas != [esperado]:
            errados.append({**par, "id_inventario": esperado, "variantes_preditas": preditas})
    return errados


def _bloco_exato(
    predicoes: Sequence[Registro], resultado_classe: Registro, base: _Base, *, aplicavel: bool
) -> tuple[Registro, Registro | None, list[Registro]]:
    operacionais = [item for item in predicoes if _operacional(item)]
    com_id = [item for item in operacionais if variantes(item)]
    positivas = [o for o in base.ocorrencias_exatas if o["evaluability"] == "confirmed"]
    bloco: Registro = {
        "aplicavel": aplicavel,
        "ocorrencias_com_id": sum(o["context"] == "operational" for o in positivas),
        "ocorrencias_ambiguas": sum(o["strata"] == ["ambigua"] for o in base.ocorrencias_exatas),
        "predicoes_com_id": len(com_id),
        "predicoes_sem_id": len(operacionais) - len(com_id),
    }
    if not aplicavel:
        vazio = {"tp_ia": None, "fp_ia": None, "fn_ia": None, "precisao": None}
        vazio.update(revocacao_regional=None, revocacao_global=None)
        bloco.update(vazio, id_errado=None, nao_resolvidas=None, por_familia={})
        return bloco, None, []
    candidatas = []
    for item in com_id:
        copia = copy.deepcopy(item)
        copia["class_id"] = _chave_exata(str(item["class_id"]), variantes(item))
        candidatas.append(copia)
    resultado = _measure(candidatas, base.ocorrencias_exatas)
    micro = resultado["micro"]
    errados = _ids_errados(resultado_classe, base)
    bloco.update(
        _metricas(micro["tp"], micro["fp"], micro["fn"], completo=base.completo),
        id_errado=len(errados),
        nao_resolvidas=_nao_resolvidas(resultado, (*CATEGORIAS_INCERTAS, "ambigua")),
        por_familia=_por_familia(resultado, base.familias, completo=base.completo),
    )
    return bloco, resultado, errados


def _avaliar(predicoes: Sequence[Registro], base: _Base, *, aplicavel_exato: bool) -> Avaliacao:
    classe = _measure(list(predicoes), base.ocorrencias)
    bloco_exato, exato, errados = _bloco_exato(predicoes, classe, base, aplicavel=aplicavel_exato)
    avaliacao = Avaliacao(classe=classe, exato=exato)
    avaliacao.bloco = {
        "classe": _bloco_classe(classe, base),
        "id_exato": bloco_exato,
        "por_familia": _por_familia(classe, base.familias, completo=base.completo),
    }
    avaliacao.classe["ids_errados"] = errados
    return avaliacao


Suporte = frozenset[str] | None


def classes_suportadas(
    predicoes: Registro, metodos: Iterable[str]
) -> tuple[dict[str, Suporte], list[Registro]]:
    """``supported_classes`` de cada método medido e os alertas de quem não declara.

    Ausente ou vazia → ``None`` (mede contra todas as ocorrências) e alerta
    ``metodo_sem_classes_suportadas`` com ``motivo`` ``ausente`` ou ``vazia``; lista com item que
    não é ``class_id`` (texto não vazio) é recusada.
    """
    declarados = {str(item["id"]): item for item in predicoes["methods"]}
    suportadas: dict[str, Suporte] = {}
    alertas: list[Registro] = []
    for metodo in metodos:
        valor = declarados[metodo].get("supported_classes")
        if valor is None or valor == []:
            suportadas[metodo] = None
            motivo = "ausente" if valor is None else "vazia"
            alertas.append({"tipo": ALERTA_SEM_CLASSES, "method_id": metodo, "motivo": motivo})
            continue
        if not isinstance(valor, list) or not all(isinstance(c, str) and c for c in valor):
            raise ValueError(f"{metodo}: supported_classes precisa ser uma lista de class_id")
        suportadas[metodo] = frozenset(valor)
    return suportadas, alertas


def _restringir(base: _Base, suportadas: Suporte) -> tuple[_Base, int]:
    """Base sem as ocorrências operacionais de classe fora de ``suportadas`` (e quantas saíram).

    Negativos, provisórias, ilegíveis e de papel desconhecido ficam: explicam FP e não resolvidas
    como antes. ``None`` devolve a base inteira.
    """
    if suportadas is None:
        return base, 0
    fora = {
        identidade
        for identidade, observacao in base.observacoes.items()
        if _categoria(observacao) == "operacional" and observacao["class_id"] not in suportadas
    }
    restrita = replace(
        base,
        ocorrencias=[o for o in base.ocorrencias if str(o["id"]) not in fora],
        ocorrencias_exatas=[o for o in base.ocorrencias_exatas if str(o["id"]) not in fora],
    )
    return restrita, len(fora)


def _cobertas(suportadas: Mapping[str, Suporte]) -> Suporte:
    """Classes cobertas por algum método medido; ``None`` se algum não declara (cobre todas)."""
    conjuntos = list(suportadas.values())
    if any(conjunto is None for conjunto in conjuntos):
        return None
    return frozenset().union(*(c for c in conjuntos if c is not None))


# --- divergências ----------------------------------------------------------------------------


def _melhor(item: Registro, alvos: Iterable[Registro], *, mesma_classe: bool) -> Registro | None:
    """Alvo de mesma página/camada que casa pela geometria do protocolo (maior IoU, menor id)."""
    opcoes = []
    for alvo in alvos:
        if (alvo["page"], alvo["layer"]) != (item["page"], item["layer"]):
            continue
        if (alvo["class_id"] == item["class_id"]) != mesma_classe:
            continue
        geometria = geometry_match(item, alvo)
        if geometria["eligible"]:
            opcoes.append((-geometria["iou"], str(alvo["id"]), alvo))
    return min(opcoes, key=lambda opcao: opcao[:2])[2] if opcoes else None


@dataclass
class _Contexto:
    escopo: Escopo
    observacoes: Mapping[str, Registro]
    positivas: list[Registro]
    perdidas_pela_uniao: frozenset[str]
    suportadas: Mapping[str, Suporte] = field(default_factory=dict)


def _divergencia(
    contexto: _Contexto,
    *,
    tipo: str,
    nivel: str,
    conta_em: str | None,
    metodo: str,
    observacao_id: str | None,
    predicao: Registro | None,
    detalhe: Registro,
    sem_metodo: bool = False,
) -> Registro:
    observacao = contexto.observacoes.get(observacao_id) if observacao_id else None
    origem = predicao if predicao is not None and tipo != "fn" else None
    if origem is not None:
        pagina, camada, bbox = origem["page"], origem["layer"], list(origem["bbox"])
        familia, classe = origem["family"], origem["class_id"]
    else:
        assert observacao is not None
        pagina, camada, bbox = observacao["pagina"], observacao["camada"], list(observacao["bbox"])
        familia, classe = observacao["familia"], observacao["class_id"]
    tile = observacao["tile_evidencia"] if observacao is not None else None
    if tile is None:
        tile = contexto.escopo.tile_evidencia(pagina, camada, bbox)
    predicao_id = predicao["id"] if predicao is not None else None
    chave = json_canonico([nivel, tipo, metodo, observacao_id, predicao_id])
    return {
        "id": "div-" + sha256(chave.encode()).hexdigest()[:16],
        "tipo": tipo,
        "nivel": nivel,
        "conta_em": conta_em,
        "method_id": metodo,
        "observacao_id": observacao_id,
        "predicao_id": predicao_id,
        "pagina": pagina,
        "camada": camada,
        "familia": familia,
        "class_id": classe,
        "bbox": bbox,
        "tile_evidencia": tile,
        "perdida_pela_uniao": (observacao_id in contexto.perdidas_pela_uniao)
        if tipo == "fn"
        else None,
        "sem_metodo": sem_metodo,
        "detalhe": detalhe,
    }


def _de_falso_positivo(contexto: _Contexto, metodo: str, item: Registro) -> Registro:
    razao = item["reason"]
    if razao == "duplicate":
        return _divergencia(
            contexto,
            tipo="duplicata",
            nivel="classe",
            conta_em="fp_ia",
            metodo=metodo,
            observacao_id=item["reference_ids"][0],
            predicao=item,
            detalhe={"motivo": "duplicata", "observacoes_casaveis": item["reference_ids"]},
        )
    if razao == "nonoperational_context":
        controle = item["context_matches"][0]
        return _divergencia(
            contexto,
            tipo="papel_errado",
            nivel="classe",
            conta_em="fp_ia",
            metodo=metodo,
            observacao_id=controle["reference_id"],
            predicao=item,
            detalhe={
                "motivo": "controle_nao_operacional",
                "contexto_referencia": controle["reference"]["context"],
                "criterio": controle["criterion"],
            },
        )
    confundida = _melhor(item, contexto.positivas, mesma_classe=False)
    suportadas = contexto.suportadas.get(metodo)
    return _divergencia(
        contexto,
        tipo="fp",
        nivel="classe",
        conta_em="fp_ia",
        metodo=metodo,
        observacao_id=confundida["id"] if confundida else None,
        predicao=item,
        detalhe={
            "motivo": "classe_divergente" if confundida else "sem_ocorrencia",
            "classe_referencia": confundida["class_id"] if confundida else None,
            # ``None`` quando o método não declara supported_classes.
            "classe_suportada": None if suportadas is None else item["class_id"] in suportadas,
        },
    )


def _de_falso_negativo(
    contexto: _Contexto, metodo: str, item: Registro, candidatas: Sequence[Registro]
) -> Registro:
    confundida = _melhor(item, candidatas, mesma_classe=False)
    return _divergencia(
        contexto,
        tipo="fn",
        nivel="classe",
        conta_em="fn_ia",
        metodo=metodo,
        observacao_id=item["id"],
        predicao=confundida,
        detalhe={
            "motivo": "classe_divergente" if confundida else "sem_predicao",
            "classe_predita": confundida["class_id"] if confundida else None,
        },
    )


def _divergencias_metodo(
    contexto: _Contexto, metodo: str, predicoes: Sequence[Registro], avaliacao: Avaliacao
) -> list[Registro]:
    resultado = avaliacao.classe
    candidatas = [item for item in predicoes if _operacional(item)]
    itens = [_de_falso_positivo(contexto, metodo, fp) for fp in resultado["false_positives"]]
    itens.extend(
        _de_falso_negativo(contexto, metodo, fn, candidatas) for fn in resultado["false_negatives"]
    )
    for item in resultado["nonoperational_predictions"]:
        alvo = _melhor(item, contexto.positivas, mesma_classe=True)
        if alvo is not None:
            itens.append(
                _divergencia(
                    contexto,
                    tipo="papel_errado",
                    nivel="classe",
                    conta_em=None,
                    metodo=metodo,
                    observacao_id=alvo["id"],
                    predicao=item,
                    detalhe={
                        "motivo": "predicao_nao_operacional",
                        "contexto_predito": item.get("context"),
                    },
                )
            )
    for par in resultado["ids_errados"]:
        itens.append(
            _divergencia(
                contexto,
                tipo="id_errado",
                nivel="id_exato",
                conta_em=None,
                metodo=metodo,
                observacao_id=par["reference_id"],
                predicao=par["prediction"],
                detalhe={
                    "motivo": "id_inventario_divergente",
                    "id_inventario": par["id_inventario"],
                    "variantes_preditas": par["variantes_preditas"],
                },
            )
        )
    return itens


def _lacunas_da_uniao(
    contexto: _Contexto, uniao: Avaliacao, candidatas: Sequence[Registro]
) -> list[Registro]:
    """FN da união de classe que nenhum método medido cobre (``sem_metodo``)."""
    cobertas = _cobertas(contexto.suportadas)
    if cobertas is None:
        return []
    operacionais = [item for item in candidatas if _operacional(item)]
    itens = []
    for falta in uniao.classe["false_negatives"]:
        if falta["class_id"] in cobertas:
            continue
        confundida = _melhor(falta, operacionais, mesma_classe=False)
        itens.append(
            _divergencia(
                contexto,
                tipo="fn",
                nivel="uniao",
                conta_em="fn_ia",
                metodo=METODO_UNIAO,
                observacao_id=falta["id"],
                predicao=None,
                detalhe={
                    "motivo": MOTIVO_SEM_METODO,
                    "classe_predita": confundida["class_id"] if confundida else None,
                    "predicoes_confundidas": list(confundida["observation_ids"])
                    if confundida
                    else [],
                },
                sem_metodo=True,
            )
        )
    return itens


# --- comparação de um PDF --------------------------------------------------------------------


def _execucao(predicoes: Registro, document_id: str, metodo: str, locais: set[Local]) -> Registro:
    execucoes = [
        item
        for item in predicoes.get("executions", [])
        if item.get("document_id") == document_id
        and item.get("method_id") == metodo
        and (item.get("page"), item.get("layer")) in locais
    ]
    falhas = sorted(
        (
            {"pagina": item["page"], "camada": item["layer"]}
            for item in execucoes
            if item.get("status") == "failed"
        ),
        key=lambda item: (item["pagina"], item["camada"]),
    )
    status = "falha" if falhas else "executado" if execucoes else "sem_registro"
    return {
        "status": status,
        "por_status": dict(sorted(Counter(str(i.get("status")) for i in execucoes).items())),
        "falhas": falhas,
    }


def _denominadores_tiles(indice: Registro, escopo: Escopo) -> Registro:
    tiles = indice["tiles"]
    estados = {str(tile["id"]): tile["estado"] for tile in tiles}
    return {
        "indice": len(tiles),
        "a_revisar": sum(estado == "a_revisar" for estado in estados.values()),
        "descartado_branco": sum(estado == ESTADO_DESCARTADO for estado in estados.values()),
        "revisados": len(escopo.declarados),
        "revisados_por_gemeo": len(escopo.revisados - escopo.declarados),
        "revisados_descartados": sum(estados[t] == ESTADO_DESCARTADO for t in escopo.declarados),
        "a_revisar_nao_revisados": sum(
            estado == "a_revisar" and tile_id not in escopo.revisados
            for tile_id, estado in estados.items()
        ),
    }


def _denominadores_observacoes(
    observacoes: Sequence[Registro], em_escopo: Sequence[Registro]
) -> Registro:
    categorias = Counter(_categoria(item) for item in em_escopo)
    positivas = [item for item in em_escopo if _categoria(item) == "operacional"]
    return {
        "total": len(observacoes),
        "em_escopo": len(em_escopo),
        "fora_do_escopo": len(observacoes) - len(em_escopo),
        "operacionais_avaliaveis": categorias["operacional"],
        "negativos": categorias["negativo"],
        "provisorias": categorias["provisorio"],
        "ilegiveis": categorias["ilegivel"],
        "papel_desconhecido": categorias["papel_desconhecido"],
        "locais": categorias["local"],
        "ambiguas": sum(not item.get("id_inventario") for item in positivas),
        "com_id_inventario": sum(bool(item.get("id_inventario")) for item in positivas),
    }


def _separar(
    itens: Iterable[Registro], localizar: Callable[[Registro], str | None]
) -> tuple[list[Registro], list[tuple[Registro, str]]]:
    dentro, fora = [], []
    for item in itens:
        motivo = localizar(item)
        if motivo is None:
            dentro.append(item)
        else:
            fora.append((item, motivo))
    return dentro, fora


def _fora_do_escopo(
    predicoes: Sequence[tuple[Registro, str]], observacoes: Sequence[tuple[Registro, str]]
) -> Registro:
    return {
        "total": len(predicoes),
        "por_motivo": dict(sorted(Counter(motivo for _, motivo in predicoes).items())),
        "por_metodo": dict(sorted(Counter(p["method_id"] for p, _ in predicoes).items())),
        "predicoes": sorted(
            (
                {
                    "predicao_id": item["id"],
                    "method_id": item["method_id"],
                    "pagina": item["page"],
                    "camada": item["layer"],
                    "motivo": motivo,
                }
                for item, motivo in predicoes
            ),
            key=lambda item: item["predicao_id"],
        ),
        "observacoes": sorted(
            ({"observacao_id": item["id"], "motivo": motivo} for item, motivo in observacoes),
            key=lambda item: item["observacao_id"],
        ),
    }


def _predicoes_do_documento(
    predicoes: Registro, document_id: str
) -> tuple[list[Registro], list[str], list[str]]:
    """Predições validadas, métodos medidos e métodos só de candidatos locais (excluídos)."""
    metodos = [str(item["id"]) for item in predicoes["methods"]]
    if len(set(metodos)) != len(metodos):
        raise ValueError("predictions.json com métodos repetidos")
    itens = list(predicoes["predictions"])
    for item in itens:
        _validar_predicao(item, document_id, set(metodos))
    if len({item["id"] for item in itens}) != len(itens):
        raise ValueError("predictions.json com ids de predição repetidos")
    com_predicao = {item["method_id"] for item in itens}
    locais = sorted(
        str(item["id"])
        for item in predicoes["methods"]
        if str(item.get("evaluation_scope", "")).startswith(ESCOPO_LOCAL)
        and item["id"] not in com_predicao
    )
    return itens, sorted(set(metodos) - set(locais)), locais


def _base(
    document_id: str,
    referencia: Registro,
    obs_dentro: Sequence[Registro],
    pred_dentro: Sequence[Registro],
) -> _Base:
    familias = {o["familia"] for o in obs_dentro if o["familia"] != FAMILIA_LOCAL}
    return _Base(
        document_id=document_id,
        completo=referencia["escopo"] == "completo",
        ocorrencias=[_ocorrencia(o, document_id, exato=False) for o in obs_dentro],
        ocorrencias_exatas=[_ocorrencia(o, document_id, exato=True) for o in obs_dentro],
        familias=sorted(familias | {p["family"] for p in pred_dentro}),
        observacoes={str(o["id"]): o for o in obs_dentro},
    )


def _chave_divergencia(item: Registro) -> tuple[Any, ...]:
    return (
        item["method_id"],
        item["pagina"],
        item["camada"],
        item["tipo"],
        item["observacao_id"] or "",
        item["predicao_id"] or "",
    )


def _todas_divergencias(
    contexto: _Contexto,
    por_metodo: Mapping[str, Sequence[Registro]],
    avaliacoes: Mapping[str, Avaliacao],
    lacunas: Sequence[Registro],
) -> list[Registro]:
    divergencias = [
        item
        for metodo, itens in por_metodo.items()
        for item in _divergencias_metodo(contexto, metodo, itens, avaliacoes[metodo])
    ]
    divergencias.extend(lacunas)
    if len({item["id"] for item in divergencias}) != len(divergencias):
        raise ValueError("ids de divergência repetidos")
    return sorted(divergencias, key=_chave_divergencia)


def _locais_revisados(escopo: Escopo) -> set[Local]:
    return {
        (tile["pagina"], tile["camada"])
        for grupo in escopo.tiles.values()
        for tile in grupo
        if tile["id"] in escopo.revisados
    }


def _denominadores_predicoes(
    predicoes: Registro,
    document_id: str,
    todas: Sequence[Registro],
    pred_dentro: Sequence[Registro],
) -> Registro:
    locais = [
        item
        for item in predicoes.get("local_candidates", [])
        if item.get("document_id") == document_id
    ]
    return {
        "total": len(todas),
        "em_escopo": len(pred_dentro),
        "fora_do_escopo": len(todas) - len(pred_dentro),
        "nao_operacionais_em_escopo": sum(not _operacional(p) for p in pred_dentro),
        "candidatos_locais_ignorados": len(locais),
    }


def comparar(
    *, referencia: Registro, predicoes: Registro, indice: Registro, metadados: Registro
) -> Registro:
    """Comparação determinística (sem horários nem caminhos absolutos) de um PDF."""
    document_id = str(metadados["document_id"])
    todas, metodos, excluidos = _predicoes_do_documento(predicoes, document_id)
    escopo = montar_escopo(indice, referencia)
    observacoes = list(referencia["observacoes"])
    obs_dentro, obs_fora = _separar(
        observacoes, lambda o: escopo.motivo_fora(o["pagina"], o["camada"], o["bbox"])
    )
    pred_dentro, pred_fora = _separar(
        todas, lambda p: escopo.motivo_fora(p["page"], p["layer"], p["bbox"])
    )
    base = _base(document_id, referencia, obs_dentro, pred_dentro)
    suportadas, alertas = classes_suportadas(predicoes, metodos)
    informam_id = {p["method_id"] for p in todas if variantes(p)} | set(METODOS_COM_ID_EXATO)
    por_metodo = {m: [p for p in pred_dentro if p["method_id"] == m] for m in metodos}
    restritas = {m: _restringir(base, suportadas[m]) for m in metodos}
    avaliacoes = {
        m: _avaliar(itens, restritas[m][0], aplicavel_exato=m in informam_id)
        for m, itens in por_metodo.items()
    }
    candidatas_uniao = _union(pred_dentro)
    uniao = _avaliar(candidatas_uniao, base, aplicavel_exato=bool(informam_id & set(metodos)))
    contexto = _Contexto(
        escopo=escopo,
        observacoes=base.observacoes,
        positivas=[o for o in base.ocorrencias if o["strata"] == ["operacional"]],
        perdidas_pela_uniao=frozenset(item["id"] for item in uniao.classe["false_negatives"]),
        suportadas=suportadas,
    )
    lacunas = _lacunas_da_uniao(contexto, uniao, candidatas_uniao)
    locais = _locais_revisados(escopo)
    blocos = {
        m: {
            **avaliacoes[m].bloco,
            "classes_suportadas": _lista_suporte(suportadas[m]),
            "ocorrencias_fora_do_suporte": restritas[m][1],
            "execucao": _execucao(predicoes, document_id, m, locais),
        }
        for m in metodos
    }
    return {
        "schema_version": ESQUEMA_COMPARACAO,
        **metadados,
        "escopo": referencia["escopo"],
        "protocolo": {
            "id": PROTOCOL["id"],
            "sha256": sha256(json_canonico(PROTOCOL).encode()).hexdigest(),
        },
        "denominadores": {
            "tiles": _denominadores_tiles(indice, escopo),
            "regioes_ilegiveis": len(referencia["regioes_ilegiveis"]),
            "observacoes": _denominadores_observacoes(observacoes, obs_dentro),
            "predicoes": _denominadores_predicoes(predicoes, document_id, todas, pred_dentro),
        },
        "metodos": blocos,
        "metodos_com_falha": [m for m in metodos if blocos[m]["execucao"]["status"] == "falha"],
        "metodos_excluidos": dict.fromkeys(excluidos, MOTIVO_EXCLUSAO_LOCAL),
        "uniao": {
            **uniao.bloco,
            "candidatas": len(candidatas_uniao),
            "observacoes_entrada": len(pred_dentro),
            "fn_sem_metodo": len(lacunas),
            "classes_sem_metodo": sorted({str(item["class_id"]) for item in lacunas}),
        },
        "divergencias": _todas_divergencias(contexto, por_metodo, avaliacoes, lacunas),
        "fora_do_escopo": _fora_do_escopo(pred_fora, obs_fora),
        "alertas": alertas,
        "limitacoes": list(LIMITACOES),
    }


def _lista_suporte(suportadas: Suporte) -> list[str] | None:
    return None if suportadas is None else sorted(suportadas)


# --- entradas congeladas ----------------------------------------------------------------------


@dataclass
class Entradas:
    """Referência, inferência e índice conferidos de um PDF, prontos para ``comparar``."""

    pdf_id: str
    referencia: Registro
    predicoes: Registro
    indice: Registro
    metadados: Registro

    @property
    def vigente(self) -> bool:
        return bool(self.metadados["vigente"])

    def argumentos(self) -> dict[str, Any]:
        return {
            "referencia": self.referencia,
            "predicoes": self.predicoes,
            "indice": self.indice,
            "metadados": self.metadados,
        }


def _registros(checkpoint: Registro, fase: str, caminho: str) -> list[tuple[Registro, Registro]]:
    """(evento, artefato) de todas as entradas na fase que registraram ``caminho``."""
    return [
        (evento, artefato)
        for evento in checkpoint["historico"]
        if evento["para"] == fase
        for artefato in evento["artefatos"]
        if artefato["caminho"] == caminho
    ]


def _referencia_escolhida(
    raiz: Path, checkpoint: Registro, versao: str | None
) -> tuple[Registro, Registro]:
    pdf_id = checkpoint["pdf_id"]
    vigente = checkpoint.get("referencia")
    if vigente is None or "referencia_congelada" not in checkpoint["marcos"]:
        raise ComparacaoRecusadaError(
            f"{pdf_id} não tem referência congelada; rode curation_reference congelar"
        )
    nome = vigente["versao"] if versao is None else f"referencia-{versao}.json"
    caminho = f"pdfs/{pdf_id}/{DIRETORIO_REFERENCIA}/{nome}"
    registros = _registros(checkpoint, "referencia_congelada", caminho)
    if not registros:
        raise ComparacaoRecusadaError(
            f"{nome} de {pdf_id} não foi congelada (sem registro no checkpoint)"
        )
    evento, artefato = registros[-1]
    arquivo = raiz / caminho
    if not arquivo.is_file() or hash_arquivo(arquivo) != artefato["sha256"]:
        raise ComparacaoRecusadaError(
            f"SHA-256 de {nome} de {pdf_id} difere do registrado no congelamento"
        )
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    if not isinstance(dados, dict) or not isinstance(dados.get("congelamento"), dict):
        raise ComparacaoRecusadaError(f"{nome} de {pdf_id} não traz o bloco congelamento")
    bloco = dados["congelamento"]
    info = {
        "versao": nome,
        "arquivo": caminho,
        "sha256": artefato["sha256"],
        "origem": bloco.get("origem"),
        "reutilizada": evento["dados"].get("origem") == "reuso",
        "exposicao_predicoes": bloco.get("exposicao_predicoes"),
        "vigente": caminho == vigente["arquivo"],
    }
    return dados, info


def _inferencia_escolhida(
    raiz: Path, checkpoint: Registro, versao: str | None
) -> tuple[Registro, Registro]:
    pdf_id = checkpoint["pdf_id"]
    marco = checkpoint["marcos"].get("inferido")
    vigente = marco["artefatos"][0]["caminho"] if marco and marco["artefatos"] else None
    if versao is None and vigente is None:
        raise ComparacaoRecusadaError(
            f"{pdf_id} não tem inferência concluída (marco inferido); rode curation_infer"
        )
    caminho = vigente if versao is None else f"pdfs/{pdf_id}/inferencia-{versao}"
    assert caminho is not None
    nome = Path(caminho).name
    registros = _registros(checkpoint, "inferido", caminho)
    if not registros:
        raise ComparacaoRecusadaError(
            f"{nome} de {pdf_id} não é uma inferência concluída registrada no checkpoint"
        )
    _, artefato = registros[-1]
    pasta = raiz / caminho
    if not pasta.is_dir() or hash_diretorio(pasta) != artefato["sha256"]:
        raise ComparacaoRecusadaError(
            f"SHA-256 de {nome} de {pdf_id} difere do registrado no marco inferido"
        )
    arquivo = pasta / "simbolos" / "predictions.json"
    predicoes = ler_json(arquivo)
    if not isinstance(predicoes, dict):
        raise ComparacaoRecusadaError(f"predictions.json de {nome} não é um objeto JSON")
    info = {
        "versao": nome,
        "arquivo": caminho,
        "sha256": artefato["sha256"],
        "predictions_sha256": hash_arquivo(arquivo),
        "vigente": caminho == vigente,
    }
    return predicoes, info


def _conferir_identidade(
    checkpoint: Registro, referencia: Registro, predicoes: Registro, document_id: str
) -> None:
    pdf_id, sha_pdf = checkpoint["pdf_id"], checkpoint["sha256"]
    sha_referencia = referencia.get("pdf", {}).get("sha256")
    if sha_referencia != sha_pdf:
        raise ComparacaoRecusadaError(
            f"SHA-256 do PDF na referência de {pdf_id} difere do checkpoint da rodada"
        )
    documentos = [d for d in predicoes.get("documents", []) if d.get("id") == document_id]
    if len(documentos) != 1:
        raise ComparacaoRecusadaError(f"predictions.json não traz exatamente {document_id}")
    sha_inferencia = documentos[0].get("sha256")
    if sha_inferencia != sha_referencia:
        raise ComparacaoRecusadaError(
            f"SHA-256 do PDF difere entre referência ({str(sha_referencia)[:12]}) e inferência "
            f"({str(sha_inferencia)[:12]}) de {pdf_id}"
        )


def carregar_entradas(
    rodada_dir: Path,
    pdf_id: str,
    *,
    inferencia: str | None = None,
    referencia: str | None = None,
) -> Entradas:
    """Lê e confere as versões pedidas (padrão: vigentes); recusa sem escrever nada."""
    raiz = Path(rodada_dir).resolve()
    checkpoint = carregar_checkpoint(raiz, pdf_id)
    dados_referencia, info_referencia = _referencia_escolhida(raiz, checkpoint, referencia)
    predicoes, info_inferencia = _inferencia_escolhida(raiz, checkpoint, inferencia)
    vigente = bool(info_referencia["vigente"] and info_inferencia["vigente"])
    if vigente:
        validar_transicao(checkpoint, "comparado")
    document_id = "example:" + str(checkpoint["caminho_relativo"])
    _conferir_identidade(checkpoint, dados_referencia, predicoes, document_id)
    indice, indice_sha = _indice_vigente(raiz, pdf_id, checkpoint)
    congelado = dados_referencia["congelamento"].get("indice_tiles_sha256")
    if congelado != indice_sha and not info_referencia["reutilizada"]:
        raise ComparacaoRecusadaError(
            f"índice de tiles de {pdf_id} difere do usado no congelamento de "
            f"{info_referencia['versao']}"
        )
    metadados = {
        "pdf_id": pdf_id,
        "document_id": document_id,
        "sha256_pdf": checkpoint["sha256"],
        "vigente": vigente,
        "referencia": info_referencia,
        "inferencia": info_inferencia,
        "indice_tiles": {
            "sha256": indice_sha,
            "sha256_no_congelamento": congelado,
            "igual_ao_congelamento": congelado == indice_sha,
        },
    }
    return Entradas(pdf_id, dados_referencia, predicoes, indice, metadados)


# --- gravação e checkpoint ---------------------------------------------------------------------


def _versoes(pasta_pdf: Path) -> list[int]:
    return sorted(
        int(achado.group(1))
        for item in pasta_pdf.iterdir()
        if (achado := NOME_COMPARACAO.fullmatch(item.name))
    )


def _gravar(pasta_pdf: Path, conteudo: bytes) -> Path:
    with _trava(pasta_pdf / "comparacao"):
        numero = max(_versoes(pasta_pdf), default=0) + 1
        destino = pasta_pdf / f"{PREFIXO_COMPARACAO}{numero:03d}.json"
        _criar_exclusivo(destino, conteudo)
    return destino


def _resumo_uniao(comparacao: Registro) -> Registro:
    classe = comparacao["uniao"]["classe"]
    return {campo: classe[campo] for campo in ("tp_ia", "fp_ia", "fn_ia")}


def comparar_pdf(
    rodada_dir: Path,
    pdf_id: str,
    *,
    inferencia: str | None = None,
    referencia: str | None = None,
    agora: str | None = None,
) -> Registro:
    """Compara um PDF, grava ``comparacao-vNNN.json`` e avança para ``comparado`` se vigente."""
    try:
        entradas = carregar_entradas(
            rodada_dir, pdf_id, inferencia=inferencia, referencia=referencia
        )
        comparacao = comparar(**entradas.argumentos())
    except ComparacaoRecusadaError:
        raise
    except (RodadaError, ValueError, KeyError, TypeError) as erro:
        raise ComparacaoRecusadaError(f"{pdf_id}: {erro}") from erro
    raiz = Path(rodada_dir).resolve()
    pasta = diretorio_pdf(raiz, pdf_id)
    destino = _gravar(pasta, json_canonico(comparacao).encode("utf-8"))
    resumo = _resumo_uniao(comparacao)
    if entradas.vigente:
        dados = {
            "versao": destino.name,
            "inferencia": entradas.metadados["inferencia"]["versao"],
            "referencia": entradas.metadados["referencia"]["versao"],
            "escopo": comparacao["escopo"],
            "uniao": resumo,
            "divergencias": len(comparacao["divergencias"]),
            "metodos_com_falha": comparacao["metodos_com_falha"],
        }
        try:
            transicionar(raiz, pdf_id, "comparado", artefatos=[destino], dados=dados, agora=agora)
        except BaseException:
            destino.unlink(missing_ok=True)
            raise
    return {
        "pdf_id": pdf_id,
        "status": "sucesso",
        "versao": destino.name,
        "arquivo": destino.relative_to(raiz).as_posix(),
        "vigente": entradas.vigente,
        "checkpoint_avancado": entradas.vigente,
        "uniao": resumo,
        "divergencias": len(comparacao["divergencias"]),
        "metodos_com_falha": comparacao["metodos_com_falha"],
        "alertas": comparacao["alertas"],
        "falhas": [],
    }


# --- CLI --------------------------------------------------------------------------------------


def _versao(padrao: re.Pattern[str]) -> Callable[[str], str]:
    def converter(valor: str) -> str:
        if not padrao.fullmatch(valor):
            raise argparse.ArgumentTypeError(f"versão inválida: {valor} (use vNNN)")
        return valor

    return converter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--rodada", type=Path, required=True)
    parser.add_argument("--onda", type=int)
    parser.add_argument("--pdf", dest="pdfs", action="append", metavar="ID")
    parser.add_argument(
        "--inferencia",
        type=_versao(VERSAO_INFERENCIA),
        help="versão da inferência (vNNN); padrão: a do marco inferido",
    )
    parser.add_argument(
        "--referencia",
        type=_versao(VERSAO_REFERENCIA),
        help="versão congelada da referência (vNNN); padrão: a vigente do checkpoint",
    )
    return parser


def _comparar_um(args: argparse.Namespace, pdf_id: str) -> Registro:
    try:
        return comparar_pdf(
            args.rodada, pdf_id, inferencia=args.inferencia, referencia=args.referencia
        )
    except ComparacaoRecusadaError as erro:
        return {"pdf_id": pdf_id, "status": "recusado", "falhas": [str(erro)]}
    except Exception as erro:  # falha isolada: os outros PDFs da onda continuam
        return {"pdf_id": pdf_id, "status": "falha", "falhas": [f"{type(erro).__name__}: {erro}"]}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        pdf_ids = selecionar_pdfs(args.rodada, onda=args.onda, pdf_ids=args.pdfs or ())
    except RodadaError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    pdfs = [_comparar_um(args, pdf_id) for pdf_id in pdf_ids]
    totais = Counter(item["status"] for item in pdfs)
    resultado = {
        "pdfs": pdfs,
        "totais": {status: totais[status] for status in ("sucesso", "recusado", "falha")},
    }
    print(json_canonico(resultado), end="")
    return 0 if totais["sucesso"] == len(pdfs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
