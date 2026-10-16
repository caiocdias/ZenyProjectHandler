"""Referência visual regional da curadoria: validação, congelamento e versões preservadas.

Uso:
    python -m scripts.curation_reference validar --rodada DIR --pdf ID --arquivo JSON
    python -m scripts.curation_reference congelar --rodada DIR --pdf ID --arquivo JSON
    python -m scripts.curation_reference revisar --rodada DIR --pdf ID --arquivo JSON
        --motivo TEXTO --exposicao {sim,nao}

A referência é a leitura visual que um leitor (IA) faz dos tiles de ``render/`` de um PDF, no
formato de ``docs/schemas/referencia-visual-curadoria.schema.json``. ``validar`` aplica o esquema
e as regras que dependem do índice de tiles vigente e do inventário: bbox dentro dos tiles
revisados da mesma página/camada, tile de evidência revisado, família/classe/ID existentes em
``docs/data/inventario-simbologia-v1.json``, ID exato e alternativas mutuamente exclusivos, ids
únicos, relações para ids existentes e, com ``escopo = completo``, todo tile ``a_revisar``
revisado ou coberto por ``regioes_ilegiveis``.

``congelar`` grava a primeira versão em ``pdfs/ID/referencia/referencia-v001.json`` (JSON
canônico da entrada mais o bloco ``congelamento``) e avança o checkpoint para
``referencia_congelada`` com o SHA-256 e o horário; registra, por transparência, as pastas
``inferencia-vNNN`` já presentes. ``revisar`` cria a próxima versão livre, nunca sobrescreve as
anteriores e registra o motivo e se quem revisou viu predições (``exposicao_predicoes``). A
referência é de desenvolvimento gerada por IA: não é gabarito, confirmação humana nem norma.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any

from scripts.curation_render import (
    ARQUIVO_INDICE,
    DIRETORIO_RENDER,
    caminho_indice,
    carregar_indice,
)
from scripts.curation_round import (
    ROOT,
    RodadaError,
    _trava,
    carregar_checkpoint,
    diretorio_pdf,
    hash_arquivo,
    json_canonico,
    transicionar,
    validar_transicao,
)

ESQUEMA_REFERENCIA = "curadoria-referencia-visual-v1"
CAMINHO_ESQUEMA = ROOT / "docs" / "schemas" / "referencia-visual-curadoria.schema.json"
CAMINHO_INVENTARIO = ROOT / "docs" / "data" / "inventario-simbologia-v1.json"
# Mesmo par do método de legenda local do runner: elemento sem família no inventário.
FAMILIA_LOCAL = "local-unknown"
CLASSE_LOCAL = "UNKNOWN_LOCAL"
DIRETORIO_REFERENCIA = "referencia"
VERSAO_MAXIMA = 999
NOME_VERSAO = re.compile(r"referencia-v(\d{3})\.json")
NOME_INFERENCIA = re.compile(r"inferencia-v\d{3,}")
# Folga para bbox estimada que encosta na borda de um tile revisado (coordenadas em [0,1]).
TOLERANCIA_BBOX = 1e-6
FONTES_COM_LOCALIZADOR = frozenset({"legenda_local", "nota_documento", "norma"})
EXPOSICAO = {"sim": True, "nao": False}
PALAVRAS_ESQUEMA = frozenset(
    {
        "$schema",
        "$id",
        "$defs",
        "$ref",
        "title",
        "description",
        "type",
        "const",
        "enum",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minLength",
        "pattern",
        "minimum",
        "maximum",
    }
)
_TIPOS_SIMPLES: Mapping[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}

Registro = dict[str, Any]
Caixa = tuple[float, float, float, float]
Chave = tuple[int, str]


class ReferenciaInvalidaError(RodadaError):
    """Referência recusada pelo esquema ou pelas regras semânticas; nada foi gravado."""

    def __init__(self, pdf_id: str, erros: Sequence[str]) -> None:
        self.erros = list(erros)
        super().__init__(f"referência de {pdf_id} inválida: " + "; ".join(self.erros))


# --- esquema (subconjunto do Draft 2020-12 usado pelo arquivo do esquema) -----------------


def carregar_esquema(caminho: Path = CAMINHO_ESQUEMA) -> Registro:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise RodadaError(f"esquema inválido: {Path(caminho).name}")
    return dados


def _tem_tipo(valor: Any, nome: str) -> bool:
    if nome == "integer":
        return isinstance(valor, int) and not isinstance(valor, bool)
    if nome == "number":
        return (
            isinstance(valor, int | float) and not isinstance(valor, bool) and math.isfinite(valor)
        )
    if nome not in _TIPOS_SIMPLES:
        raise ValueError(f"tipo de esquema não suportado: {nome}")
    return isinstance(valor, _TIPOS_SIMPLES[nome])


def _numero(valor: Any) -> bool:
    return isinstance(valor, int | float) and not isinstance(valor, bool)


def _rotulo(caminho: str) -> str:
    return caminho or "(raiz)"


def _resolver(raiz: Registro, referencia: str) -> Registro:
    prefixo = "#/$defs/"
    if not referencia.startswith(prefixo) or referencia[len(prefixo) :] not in raiz.get(
        "$defs", {}
    ):
        raise ValueError(f"$ref não suportada: {referencia}")
    definicao = raiz["$defs"][referencia[len(prefixo) :]]
    assert isinstance(definicao, dict)
    return definicao


def _erro_tipo(valor: Any, esquema: Registro, caminho: str) -> str | None:
    if "type" not in esquema:
        return None
    tipos = esquema["type"] if isinstance(esquema["type"], list) else [esquema["type"]]
    if any(_tem_tipo(valor, tipo) for tipo in tipos):
        return None
    return f"{_rotulo(caminho)}: tipo inválido (esperado {' ou '.join(tipos)})"


def _erros_escalares(valor: Any, esquema: Registro, caminho: str) -> list[str]:
    rotulo = _rotulo(caminho)
    erros = []
    if "const" in esquema and valor != esquema["const"]:
        erros.append(f"{rotulo}: valor deve ser {esquema['const']!r}")
    if "enum" in esquema and valor not in esquema["enum"]:
        erros.append(f"{rotulo}: valor {valor!r} fora de {esquema['enum']}")
    if _numero(valor) and "minimum" in esquema and valor < esquema["minimum"]:
        erros.append(f"{rotulo}: valor {valor} abaixo do mínimo {esquema['minimum']}")
    if _numero(valor) and "maximum" in esquema and valor > esquema["maximum"]:
        erros.append(f"{rotulo}: valor {valor} acima do máximo {esquema['maximum']}")
    if isinstance(valor, str) and len(valor) < esquema.get("minLength", 0):
        erros.append(f"{rotulo}: texto vazio ou curto demais")
    if isinstance(valor, str) and "pattern" in esquema and not re.search(esquema["pattern"], valor):
        erros.append(f"{rotulo}: {valor!r} fora do padrão {esquema['pattern']}")
    return erros


def _erros_objeto(valor: Registro, esquema: Registro, raiz: Registro, caminho: str) -> list[str]:
    rotulo = _rotulo(caminho)
    propriedades = esquema.get("properties", {})
    erros = [
        f"{rotulo}: campo obrigatório ausente: {campo}"
        for campo in esquema.get("required", [])
        if campo not in valor
    ]
    if esquema.get("additionalProperties", True) is False:
        erros.extend(
            f"{rotulo}: campo não permitido: {campo}"
            for campo in sorted(valor)
            if campo not in propriedades
        )
    for campo, subesquema in propriedades.items():
        if campo in valor:
            filho = f"{caminho}.{campo}" if caminho else campo
            erros.extend(validar_esquema(valor[campo], subesquema, raiz=raiz, caminho=filho))
    return erros


def _erros_lista(valor: list[Any], esquema: Registro, raiz: Registro, caminho: str) -> list[str]:
    rotulo = _rotulo(caminho)
    erros = []
    if len(valor) < esquema.get("minItems", 0):
        erros.append(f"{rotulo}: exige ao menos {esquema['minItems']} itens")
    if "maxItems" in esquema and len(valor) > esquema["maxItems"]:
        erros.append(f"{rotulo}: aceita no máximo {esquema['maxItems']} itens")
    if "items" in esquema:
        for posicao, item in enumerate(valor):
            filho = f"{caminho}[{posicao}]"
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                filho += f" (id {item['id']})"
            erros.extend(validar_esquema(item, esquema["items"], raiz=raiz, caminho=filho))
    return erros


def validar_esquema(
    valor: Any, esquema: Registro, *, raiz: Registro | None = None, caminho: str = ""
) -> list[str]:
    """Erros de ``valor`` frente a ``esquema``; palavra-chave fora do subconjunto é recusada.

    Implementa só as palavras de ``PALAVRAS_ESQUEMA``, com a semântica do Draft 2020-12
    (``$ref`` local em ``#/$defs``, aplicada junto das palavras irmãs). Não é um validador geral.
    """
    raiz = esquema if raiz is None else raiz
    desconhecidas = sorted(set(esquema) - PALAVRAS_ESQUEMA)
    if desconhecidas:
        raise ValueError(f"palavras de esquema não suportadas: {', '.join(desconhecidas)}")
    erros = []
    if "$ref" in esquema:
        definicao = _resolver(raiz, esquema["$ref"])
        erros.extend(validar_esquema(valor, definicao, raiz=raiz, caminho=caminho))
    tipo = _erro_tipo(valor, esquema, caminho)
    if tipo is not None:
        return [*erros, tipo]
    erros.extend(_erros_escalares(valor, esquema, caminho))
    if isinstance(valor, dict):
        erros.extend(_erros_objeto(valor, esquema, raiz, caminho))
    elif isinstance(valor, list):
        erros.extend(_erros_lista(valor, esquema, raiz, caminho))
    return erros


# --- inventário ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Inventario:
    """Famílias, variantes (id -> família, class_code) e classes por família do inventário."""

    familias: frozenset[str]
    variantes: Mapping[str, tuple[str, str]]
    classes_por_familia: Mapping[str, frozenset[str]]


def carregar_inventario(caminho: Path = CAMINHO_INVENTARIO) -> Inventario:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    familias = frozenset(str(item["id"]) for item in dados["families"])
    variantes: dict[str, tuple[str, str]] = {}
    classes: dict[str, set[str]] = defaultdict(set)
    for variante in dados["variants"]:
        familia, classe = str(variante["family_id"]), str(variante["class_code"])
        variantes[str(variante["id"])] = (familia, classe)
        classes[familia].add(classe)
    return Inventario(
        familias=familias,
        variantes=variantes,
        classes_por_familia={familia: frozenset(classes[familia]) for familia in familias},
    )


# --- regras semânticas --------------------------------------------------------------------


def _caixa(valores: Sequence[float]) -> Caixa:
    return float(valores[0]), float(valores[1]), float(valores[2]), float(valores[3])


def _erro_geometria(caixa: Caixa) -> str | None:
    x0, y0, x1, y1 = caixa
    if x0 > x1 or y0 > y1:
        return "bbox invertida (exige x0 <= x1 e y0 <= y1)"
    if x0 == x1 and y0 == y1:
        return "bbox degenerada num ponto"
    return None


def _amostras(inicio: float, fim: float, cortes: Iterable[float]) -> list[float]:
    if fim <= inicio:
        return [inicio]
    pontos = sorted({inicio, fim, *(corte for corte in cortes if inicio < corte < fim)})
    return [(a + b) / 2 for a, b in pairwise(pontos)]


def _dentro(x: float, y: float, caixa: Caixa) -> bool:
    folga = TOLERANCIA_BBOX
    return caixa[0] - folga <= x <= caixa[2] + folga and caixa[1] - folga <= y <= caixa[3] + folga


def contida_na_uniao(caixa: Caixa, retangulos: Sequence[Caixa]) -> bool:
    """``caixa`` está inteira na união de ``retangulos`` (todos na mesma página/camada)?

    As bordas dos retângulos cortam a caixa em células; cada célula está inteira dentro de um
    retângulo ou fora de todos, então basta testar o centro de cada célula.
    """
    x0, y0, x1, y1 = caixa
    folga = TOLERANCIA_BBOX
    relevantes = [
        r
        for r in retangulos
        if r[0] <= x1 + folga and r[2] >= x0 - folga and r[1] <= y1 + folga and r[3] >= y0 - folga
    ]
    if not relevantes:
        return False
    xs = _amostras(x0, x1, (v for r in relevantes for v in (r[0], r[2])))
    ys = _amostras(y0, y1, (v for r in relevantes for v in (r[1], r[3])))
    return all(any(_dentro(x, y, r) for r in relevantes) for x in xs for y in ys)


def _intersecta(a: Caixa, b: Caixa) -> bool:
    folga = TOLERANCIA_BBOX
    return (
        a[0] <= b[2] + folga
        and b[0] <= a[2] + folga
        and a[1] <= b[3] + folga
        and (b[1] <= a[3] + folga)
    )


@dataclass
class _Contexto:
    tiles: Mapping[str, Registro]
    gemeos: Mapping[tuple[int, str, int, int], str]
    paginas: Mapping[int, Registro]
    revisados: set[str]
    caixas_revisadas: Mapping[Chave, list[Caixa]]
    caixas_ilegiveis: Mapping[Chave, list[Caixa]]
    observacoes: set[str]


def _contexto(
    referencia: Registro, indice: Registro, tiles_permitidos: Collection[str] | None
) -> tuple[_Contexto, list[str]]:
    tiles = {str(tile["id"]): tile for tile in indice["tiles"]}
    erros: list[str] = []
    revisados: set[str] = set()
    revisadas: dict[Chave, list[Caixa]] = defaultdict(list)
    contagem: Counter[str] = Counter(referencia["tiles_revisados"])
    for tile_id, vezes in contagem.items():
        if vezes > 1:
            erros.append(f"tiles_revisados: tile {tile_id} repetido")
        if tile_id not in tiles:
            erros.append(f"tiles_revisados: tile {tile_id} inexistente no índice de tiles")
        elif tiles_permitidos is not None and tile_id not in tiles_permitidos:
            erros.append(f"tiles_revisados: tile {tile_id} fora dos tiles permitidos")
        else:
            tile = tiles[tile_id]
            revisados.add(tile_id)
            revisadas[(tile["pagina"], tile["camada"])].append(_caixa(tile["bbox"]))
    ilegiveis: dict[Chave, list[Caixa]] = defaultdict(list)
    for regiao in referencia["regioes_ilegiveis"]:
        ilegiveis[(regiao["pagina"], regiao["camada"])].append(_caixa(regiao["bbox"]))
    contexto = _Contexto(
        tiles=tiles,
        gemeos={(t["pagina"], t["camada"], t["linha"], t["coluna"]): i for i, t in tiles.items()},
        paginas={int(pagina["pagina"]): pagina for pagina in indice["paginas"]},
        revisados=revisados,
        caixas_revisadas=revisadas,
        caixas_ilegiveis=ilegiveis,
        observacoes={str(item["id"]) for item in referencia["observacoes"]},
    )
    return contexto, erros


def _erros_pdf(
    pdf: Registro, pdf_id: str, indice: Registro, checkpoint: Registro | None
) -> list[str]:
    esperado = {
        "pdf_id": pdf_id,
        "sha256": indice["sha256_pdf"],
        "caminho_relativo": indice["caminho_relativo"],
    }
    if checkpoint is not None:
        for campo, origem in (("sha256", "sha256"), ("caminho_relativo", "caminho_relativo")):
            if checkpoint[origem] != esperado[campo]:
                return [f"pdf.{campo}: índice de tiles e checkpoint divergem para {pdf_id}"]
    return [
        f"pdf.{campo}: {pdf[campo]!r} difere do PDF da rodada ({valor!r})"
        for campo, valor in esperado.items()
        if pdf[campo] != valor
    ]


def _erros_ids(referencia: Registro) -> list[str]:
    ids = [item["id"] for item in (*referencia["observacoes"], *referencia["regioes_ilegiveis"])]
    return [
        f"id {identidade} duplicado entre observações e regiões ilegíveis"
        for identidade, vezes in Counter(ids).items()
        if vezes > 1
    ]


def _erros_regiao(regiao: Registro, contexto: _Contexto) -> list[str]:
    prefixo = f"região ilegível {regiao['id']}"
    erros = []
    if regiao["pagina"] not in contexto.paginas:
        erros.append(f"{prefixo}: página {regiao['pagina']} inexistente no índice de tiles")
    geometria = _erro_geometria(_caixa(regiao["bbox"]))
    if geometria:
        erros.append(f"{prefixo}: {geometria}")
    return erros


def _erros_id_exato(
    prefixo: str, exato: str, familia: str, classe: str, inv: Inventario
) -> list[str]:
    if exato not in inv.variantes:
        return [f"{prefixo}: id_inventario {exato} não existe no inventário"]
    familia_id, classe_id = inv.variantes[exato]
    if (familia_id, classe_id) != (familia, classe):
        return [
            f"{prefixo}: id_inventario {exato} ({familia_id}/{classe_id}) contradiz "
            f"familia/class_id {familia}/{classe}"
        ]
    return []


def _erros_alternativas(
    prefixo: str, alternativas: Registro, familia: str, classe: str, inv: Inventario
) -> list[str]:
    ids = list(alternativas["ids_inventario"])
    repetidas = sorted(item for item, vezes in Counter(ids).items() if vezes > 1)
    erros = [f"{prefixo}: alternativas repetidas: {', '.join(repetidas)}"] if repetidas else []
    erros.extend(
        f"{prefixo}: alternativa {item} não existe no inventário"
        for item in dict.fromkeys(ids)
        if item not in inv.variantes
    )
    if not erros and (familia, classe) not in {inv.variantes[item] for item in ids}:
        erros.append(
            f"{prefixo}: nenhuma das alternativas pertence a familia/class_id {familia}/{classe}"
        )
    return erros


def _erros_inventario(observacao: Registro, inv: Inventario) -> list[str]:
    prefixo = f"observação {observacao['id']}"
    familia, classe = observacao["familia"], observacao["class_id"]
    exato, alternativas = observacao.get("id_inventario"), observacao.get("alternativas")
    if familia == FAMILIA_LOCAL:
        erros = []
        if classe != CLASSE_LOCAL:
            erros.append(f"{prefixo}: família {FAMILIA_LOCAL} exige class_id {CLASSE_LOCAL}")
        if exato is not None or alternativas is not None:
            erros.append(
                f"{prefixo}: família {FAMILIA_LOCAL} não aceita id_inventario nem alternativas"
            )
        return erros
    if familia not in inv.familias:
        return [f"{prefixo}: família {familia} não existe no inventário"]
    if classe not in inv.classes_por_familia[familia]:
        return [f"{prefixo}: class_id {classe} não pertence à família {familia} no inventário"]
    if exato is not None and alternativas is not None:
        return [
            f"{prefixo}: id_inventario e alternativas são exclusivos; ambiguidade não vira ID "
            "exato (deixe id_inventario nulo ou remova as alternativas)"
        ]
    if exato is not None:
        return _erros_id_exato(prefixo, exato, familia, classe, inv)
    if alternativas is not None:
        return _erros_alternativas(prefixo, alternativas, familia, classe, inv)
    if observacao["papel"] == "negativo" or observacao["estado"] == "ilegivel":
        return []
    return [f"{prefixo}: informe id_inventario (ID distinguível) ou alternativas com motivo"]


def _erros_evidencia(observacao: Registro, caixa: Caixa, contexto: _Contexto) -> list[str]:
    prefixo = f"observação {observacao['id']}"
    tile_id = observacao["tile_evidencia"]
    if tile_id not in contexto.revisados:
        return [f"{prefixo}: tile de evidência {tile_id} não está entre os tiles revisados"]
    tile = contexto.tiles[tile_id]
    if (tile["pagina"], tile["camada"]) != (observacao["pagina"], observacao["camada"]):
        return [f"{prefixo}: tile de evidência {tile_id} é de outra página ou camada"]
    if not _intersecta(caixa, _caixa(tile["bbox"])):
        return [f"{prefixo}: tile de evidência {tile_id} não contém nenhuma parte da bbox"]
    return []


def _erros_relacoes(observacao: Registro, contexto: _Contexto) -> list[str]:
    prefixo = f"observação {observacao['id']}"
    erros = []
    for relacao in observacao.get("relacoes", []):
        alvo = relacao["alvo"]
        if alvo == observacao["id"]:
            erros.append(f"{prefixo}: relação {relacao['tipo']} aponta para si mesma")
        elif alvo not in contexto.observacoes:
            erros.append(f"{prefixo}: relação {relacao['tipo']} aponta para id inexistente {alvo}")
    return erros


def _erros_atributos(observacao: Registro) -> list[str]:
    prefixo = f"observação {observacao['id']}"
    erros = []
    estado = observacao["estado"]
    if estado != "sustentado_por_evidencia" and not observacao.get("motivo_estado"):
        erros.append(f"{prefixo}: estado {estado} exige motivo_estado")
    fonte = observacao["fonte_significado"]
    if fonte["tipo"] in FONTES_COM_LOCALIZADOR and not (fonte["localizador"] or "").strip():
        erros.append(f"{prefixo}: fonte_significado {fonte['tipo']} exige localizador")
    return erros


def _erros_observacao(observacao: Registro, contexto: _Contexto, inv: Inventario) -> list[str]:
    prefixo = f"observação {observacao['id']}"
    pagina, camada = observacao["pagina"], observacao["camada"]
    caixa = _caixa(observacao["bbox"])
    erros = _erros_inventario(observacao, inv)
    erros.extend(_erros_relacoes(observacao, contexto))
    erros.extend(_erros_atributos(observacao))
    if pagina not in contexto.paginas:
        return [*erros, f"{prefixo}: página {pagina} inexistente no índice de tiles"]
    geometria = _erro_geometria(caixa)
    if geometria:
        return [*erros, f"{prefixo}: {geometria}"]
    if not contida_na_uniao(caixa, contexto.caixas_revisadas.get((pagina, camada), [])):
        erros.append(
            f"{prefixo}: bbox fora dos tiles revisados da página {pagina}, camada {camada}"
        )
    erros.extend(_erros_evidencia(observacao, caixa, contexto))
    return erros


def _tile_coberto(tile: Registro, contexto: _Contexto) -> bool:
    if tile["id"] in contexto.revisados:
        return True
    pagina, camada = tile["pagina"], tile["camada"]
    if camada == "annotation" and contexto.paginas[pagina].get("camada_anotada_igual_base"):
        gemeo = contexto.gemeos.get((pagina, "base", tile["linha"], tile["coluna"]))
        if gemeo in contexto.revisados:
            return True
    ilegiveis = contexto.caixas_ilegiveis.get((pagina, camada), [])
    return contida_na_uniao(_caixa(tile["bbox"]), ilegiveis)


def _erros_cobertura(contexto: _Contexto) -> list[str]:
    return [
        f"escopo completo: tile a_revisar {tile_id} não foi revisado nem está coberto por "
        "regioes_ilegiveis"
        for tile_id, tile in contexto.tiles.items()
        if tile["estado"] == "a_revisar" and not _tile_coberto(tile, contexto)
    ]


def validar_referencia(
    referencia: Any,
    *,
    indice: Registro,
    inventario: Inventario,
    esquema: Registro | None = None,
    checkpoint: Registro | None = None,
    tiles_permitidos: Collection[str] | None = None,
) -> list[str]:
    """Lista de erros (vazia se válida) da referência frente ao índice de tiles e ao inventário.

    Erros de esquema interrompem as regras semânticas, que pressupõem a estrutura válida.
    ``tiles_permitidos`` restringe os tiles que podem ser declarados revisados (auditoria).
    """
    erros = validar_esquema(referencia, esquema or carregar_esquema())
    if erros:
        return erros
    contexto, erros = _contexto(referencia, indice, tiles_permitidos)
    erros = _erros_pdf(referencia["pdf"], str(indice["pdf_id"]), indice, checkpoint) + erros
    erros.extend(_erros_ids(referencia))
    for regiao in referencia["regioes_ilegiveis"]:
        erros.extend(_erros_regiao(regiao, contexto))
    for observacao in referencia["observacoes"]:
        erros.extend(_erros_observacao(observacao, contexto, inventario))
    if referencia["escopo"] == "completo":
        erros.extend(_erros_cobertura(contexto))
    return erros


# --- arquivos, rodada e versões -----------------------------------------------------------


@dataclass(frozen=True)
class ResultadoValidacao:
    referencia: Any
    erros: list[str]
    indice_sha256: str
    entrada_sha256: str

    @property
    def valida(self) -> bool:
        return not self.erros


def _constante_proibida(nome: str) -> Any:
    raise ValueError(f"constante {nome} não é permitida (NaN/Infinity)")


def _ler_entrada(arquivo: Path) -> tuple[Any, bytes]:
    try:
        bruto = Path(arquivo).read_bytes()
    except FileNotFoundError:
        raise RodadaError(f"arquivo de referência não encontrado: {Path(arquivo).name}") from None
    try:
        dados = json.loads(bruto.decode("utf-8-sig"), parse_constant=_constante_proibida)
    except (UnicodeDecodeError, ValueError) as erro:
        raise RodadaError(f"JSON inválido em {Path(arquivo).name}: {erro}") from None
    return dados, bruto


def _indice_vigente(rodada_dir: Path, pdf_id: str, checkpoint: Registro) -> tuple[Registro, str]:
    marco = checkpoint["marcos"].get("renderizado")
    if marco is None:
        raise RodadaError(
            f"{pdf_id} não tem marco renderizado; rode curation_render antes da referência"
        )
    sufixo = f"/{DIRETORIO_RENDER}/{ARQUIVO_INDICE}"
    registrados = [a["sha256"] for a in marco["artefatos"] if a["caminho"].endswith(sufixo)]
    atual = hash_arquivo(caminho_indice(rodada_dir, pdf_id))
    if registrados != [atual]:
        raise RodadaError(f"índice de tiles de {pdf_id} difere do registrado no marco renderizado")
    return carregar_indice(rodada_dir, pdf_id), atual


def _validar_lida(
    rodada_dir: Path,
    pdf_id: str,
    dados: Any,
    bruto: bytes,
    *,
    inventario: Inventario | None,
    tiles_permitidos: Collection[str] | None,
) -> ResultadoValidacao:
    checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
    indice, indice_sha = _indice_vigente(rodada_dir, pdf_id, checkpoint)
    erros = validar_referencia(
        dados,
        indice=indice,
        inventario=inventario or carregar_inventario(),
        checkpoint=checkpoint,
        tiles_permitidos=tiles_permitidos,
    )
    return ResultadoValidacao(dados, erros, indice_sha, sha256(bruto).hexdigest())


def validar_arquivo(
    rodada_dir: Path,
    pdf_id: str,
    arquivo: Path,
    *,
    inventario: Inventario | None = None,
    tiles_permitidos: Collection[str] | None = None,
) -> ResultadoValidacao:
    """Valida um arquivo de referência contra o índice vigente e o checkpoint do PDF."""
    carregar_checkpoint(rodada_dir, pdf_id)
    dados, bruto = _ler_entrada(arquivo)
    return _validar_lida(
        rodada_dir, pdf_id, dados, bruto, inventario=inventario, tiles_permitidos=tiles_permitidos
    )


def versoes_existentes(pasta_referencia: Path) -> list[int]:
    """Números de todas as versões ``referencia-vNNN.json`` presentes, registradas ou não."""
    if not pasta_referencia.is_dir():
        return []
    return sorted(
        int(encontrado.group(1))
        for item in pasta_referencia.iterdir()
        if (encontrado := NOME_VERSAO.fullmatch(item.name))
    )


def inferencias_presentes(pasta_pdf: Path) -> list[str]:
    return sorted(
        item.name
        for item in pasta_pdf.iterdir()
        if item.is_dir() and NOME_INFERENCIA.fullmatch(item.name)
    )


def carregar_referencia_vigente(rodada_dir: Path, pdf_id: str) -> tuple[Registro, Path]:
    """Versão vigente registrada no checkpoint, conferida pelo SHA-256 registrado."""
    checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
    registro = checkpoint.get("referencia")
    if registro is None:
        raise RodadaError(f"{pdf_id} não tem referência congelada")
    caminho = Path(rodada_dir).resolve() / registro["arquivo"]
    if not caminho.is_file() or hash_arquivo(caminho) != registro["sha256"]:
        raise RodadaError(
            f"SHA-256 da referência vigente de {pdf_id} ({registro['versao']}) difere do "
            "registrado no checkpoint"
        )
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise RodadaError(f"referência vigente de {pdf_id} não é um objeto JSON")
    return dados, caminho


def _criar_exclusivo(destino: Path, conteudo: bytes) -> None:
    """Cria ``destino`` com ``conteudo`` de forma atômica; nunca substitui arquivo existente."""
    descritor, nome = tempfile.mkstemp(
        prefix=f".{destino.name}.", suffix=".tmp", dir=destino.parent
    )
    temporario = Path(nome)
    try:
        with os.fdopen(descritor, "wb") as fluxo:
            fluxo.write(conteudo)
            fluxo.flush()
            os.fsync(fluxo.fileno())
        try:
            os.link(temporario, destino)
        except FileExistsError:
            raise RodadaError(
                f"{destino.name} já existe; versões de referência nunca são sobrescritas"
            ) from None
        except OSError:
            with destino.open("xb") as fluxo:
                fluxo.write(conteudo)
    finally:
        temporario.unlink(missing_ok=True)


def _entrada_validada(
    rodada_dir: Path,
    pdf_id: str,
    arquivo: Path,
    inventario: Inventario | None,
) -> ResultadoValidacao:
    dados, bruto = _ler_entrada(arquivo)
    if isinstance(dados, dict) and "congelamento" in dados:
        raise RodadaError(
            "a entrada não pode conter o bloco congelamento; ele é escrito por congelar/revisar"
        )
    resultado = _validar_lida(
        rodada_dir, pdf_id, dados, bruto, inventario=inventario, tiles_permitidos=None
    )
    if not resultado.valida:
        raise ReferenciaInvalidaError(pdf_id, resultado.erros)
    return resultado


def _gravar_versao(
    rodada_dir: Path,
    pdf_id: str,
    resultado: ResultadoValidacao,
    bloco: Registro,
    *,
    agora: str | None,
) -> Registro:
    pasta = diretorio_pdf(rodada_dir, pdf_id) / DIRETORIO_REFERENCIA
    pasta.mkdir(exist_ok=True)
    destino = pasta / f"referencia-v{bloco['versao']:03d}.json"
    referencia = dict(resultado.referencia)
    _criar_exclusivo(destino, json_canonico({**referencia, "congelamento": bloco}).encode())
    anterior = bloco["versao_anterior"]
    dados = {
        "escopo": referencia["escopo"],
        "exposicao_predicoes": bloco["exposicao_predicoes"],
        "indice_tiles_sha256": bloco["indice_tiles_sha256"],
        "inferencias_presentes": bloco["inferencias_presentes"],
        "motivo": bloco["motivo"],
        "observacoes": len(referencia["observacoes"]),
        "tiles_revisados": len(referencia["tiles_revisados"]),
        "versao": destino.name,
        "versao_anterior": Path(anterior["arquivo"]).name if anterior else None,
    }
    try:
        return transicionar(
            rodada_dir,
            pdf_id,
            "referencia_congelada",
            artefatos=[destino],
            dados=dados,
            origem_referencia=bloco["origem"],
            agora=agora,
        )
    except BaseException:
        destino.unlink(missing_ok=True)
        raise


def _bloco(
    resultado: ResultadoValidacao,
    pasta_pdf: Path,
    *,
    versao: int,
    origem: str,
    exposicao: bool,
    motivo: str | None,
    anterior: Registro | None,
) -> Registro:
    return {
        "exposicao_predicoes": exposicao,
        "indice_tiles_sha256": resultado.indice_sha256,
        "inferencias_presentes": inferencias_presentes(pasta_pdf),
        "motivo": motivo,
        "origem": origem,
        "sha256_entrada": resultado.entrada_sha256,
        "versao": versao,
        "versao_anterior": anterior,
    }


def congelar(
    rodada_dir: Path,
    pdf_id: str,
    arquivo: Path,
    *,
    inventario: Inventario | None = None,
    agora: str | None = None,
) -> Registro:
    """Congela a primeira versão da referência; recusa se já houver versão, sem alterar nada."""
    pasta_pdf = diretorio_pdf(rodada_dir, pdf_id)
    with _trava(pasta_pdf / DIRETORIO_REFERENCIA):
        checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
        validar_transicao(checkpoint, "referencia_congelada")
        if checkpoint.get("referencia") is not None:
            raise RodadaError(
                f"{pdf_id} já tem referência congelada ({checkpoint['referencia']['versao']}); "
                "use revisar para criar nova versão"
            )
        existentes = versoes_existentes(pasta_pdf / DIRETORIO_REFERENCIA)
        if existentes:
            nomes = ", ".join(f"referencia-v{numero:03d}.json" for numero in existentes)
            raise RodadaError(
                f"{pdf_id}: {nomes} já existe sem registro no checkpoint; congelar não sobrescreve"
            )
        resultado = _entrada_validada(rodada_dir, pdf_id, arquivo, inventario)
        bloco = _bloco(
            resultado,
            pasta_pdf,
            versao=1,
            origem="leitura",
            exposicao=False,
            motivo=None,
            anterior=None,
        )
        return _gravar_versao(rodada_dir, pdf_id, resultado, bloco, agora=agora)


def revisar(
    rodada_dir: Path,
    pdf_id: str,
    arquivo: Path,
    *,
    motivo: str,
    exposicao_predicoes: bool,
    inventario: Inventario | None = None,
    agora: str | None = None,
) -> Registro:
    """Cria a próxima versão livre da referência, com motivo e exposição a predições."""
    if not motivo.strip():
        raise RodadaError("revisar exige motivo não vazio")
    pasta_pdf = diretorio_pdf(rodada_dir, pdf_id)
    with _trava(pasta_pdf / DIRETORIO_REFERENCIA):
        checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
        validar_transicao(checkpoint, "referencia_congelada")
        if checkpoint.get("referencia") is None:
            raise RodadaError(
                f"{pdf_id} não tem referência congelada; use congelar para a primeira versão"
            )
        _, vigente = carregar_referencia_vigente(rodada_dir, pdf_id)
        resultado = _entrada_validada(rodada_dir, pdf_id, arquivo, inventario)
        versao = max(versoes_existentes(pasta_pdf / DIRETORIO_REFERENCIA), default=0) + 1
        if versao > VERSAO_MAXIMA:
            raise RodadaError(f"{pdf_id}: limite de {VERSAO_MAXIMA} versões de referência")
        anterior = {"arquivo": checkpoint["referencia"]["arquivo"], "sha256": hash_arquivo(vigente)}
        bloco = _bloco(
            resultado,
            pasta_pdf,
            versao=versao,
            origem="revisao",
            exposicao=exposicao_predicoes,
            motivo=motivo.strip(),
            anterior=anterior,
        )
        return _gravar_versao(rodada_dir, pdf_id, resultado, bloco, agora=agora)


# --- CLI ----------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    for nome, ajuda in (
        ("validar", "valida a referência sem gravar nada"),
        ("congelar", "congela a primeira versão (referencia-v001.json)"),
        ("revisar", "cria nova versão com motivo e exposição a predições"),
    ):
        comando = sub.add_parser(nome, help=ajuda)
        comando.add_argument("--rodada", type=Path, required=True)
        comando.add_argument("--pdf", required=True)
        comando.add_argument("--arquivo", type=Path, required=True)
        if nome == "revisar":
            comando.add_argument("--motivo", required=True)
            comando.add_argument(
                "--exposicao",
                required=True,
                choices=sorted(EXPOSICAO),
                help="sim se quem revisou viu predições, comparações ou auditorias do PDF",
            )
    return parser


def _resumo(checkpoint: Registro) -> Registro:
    evento = checkpoint["historico"][-1]
    return {
        "exposicao_predicoes": evento["dados"]["exposicao_predicoes"],
        "inferencias_presentes": evento["dados"]["inferencias_presentes"],
        "origem": checkpoint["referencia"]["origem"],
        "pdf_id": checkpoint["pdf_id"],
        "sha256": checkpoint["referencia"]["sha256"],
        "versao": checkpoint["referencia"]["versao"],
    }


def _executar(args: argparse.Namespace) -> int:
    if args.comando == "validar":
        resultado = validar_arquivo(args.rodada, args.pdf, args.arquivo)
        if not resultado.valida:
            for erro in resultado.erros:
                print(f"erro: {erro}", file=sys.stderr)
            return 1
        referencia = resultado.referencia
        print(
            f"{args.pdf}: referência válida ({len(referencia['observacoes'])} observações, "
            f"{len(referencia['tiles_revisados'])} tiles revisados, escopo {referencia['escopo']})"
        )
        return 0
    if args.comando == "congelar":
        checkpoint = congelar(args.rodada, args.pdf, args.arquivo)
    else:
        checkpoint = revisar(
            args.rodada,
            args.pdf,
            args.arquivo,
            motivo=args.motivo,
            exposicao_predicoes=EXPOSICAO[args.exposicao],
        )
    print(json_canonico(_resumo(checkpoint)), end="")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _executar(args)
    except ReferenciaInvalidaError as erro:
        for item in erro.erros:
            print(f"erro: {item}", file=sys.stderr)
        return 1
    except RodadaError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
