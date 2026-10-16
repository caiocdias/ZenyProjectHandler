"""Auditoria da referência visual por dupla leitura amostral: amostra estratificada e concordância.

Uso:
    python -m scripts.curation_audit amostrar --rodada DIR (--onda K | --pdf ID ...)
        [--fracao 0.15] [--minimo 4] [--semente 0] [--incluir-descartados 0.05] [--ampliar]
    python -m scripts.curation_audit concordancia --rodada DIR --pdf ID --auditoria JSON
        [--amostra vNNN] [--limiar 0.90]

``amostrar`` sorteia, só a partir do índice de tiles vigente e da semente, uma amostra
estratificada por página e faixa de ocupação (tercis dos tiles ``a_revisar`` da página), com
ao menos um tile por estrato, nunca menos que ``--minimo`` e uma fração de tiles
``descartado_branco`` para conferir a triagem. Em página cuja camada anotada é igual à base, só
a base entra. A amostra (``pdfs/ID/auditoria/amostra-vNNN.json``) traz apenas ids e caminhos de
tiles e contagens por estrato; nunca lê nem copia a referência principal, e é o único arquivo
entregue ao auditor. ``--ampliar`` dobra fração, mínimo e descartados da amostra auditada,
mantendo a semente e todos os tiles dela.

``concordancia`` valida a leitura do auditor com as regras da referência restritas aos tiles
amostrados, casa as observações dele com as da referência principal vigente pelo critério
geométrico do protocolo ``symbols-e02-v1`` (primeiro na mesma classe, depois entre classes) só
onde as duas leituras revisaram, mede a concordância de classe e de ID exato com denominadores e
decide: ``referencia_confiavel`` (concordância de classe >= limiar; o checkpoint avança para
``auditado``), ``ampliar_amostra`` (abaixo do limiar na amostra de nível 1) ou
``encerrar_com_pendencia`` (abaixo do limiar na amostra ampliada). Observação do auditor num tile
descartado é listada como ``falha_triagem``. O relatório vai para
``pdfs/ID/concordancia-vNNN.json`` (fora de ``auditoria/``, para que um novo auditor não o veja).
A concordância mede consistência entre duas leituras de IA, não confirmação humana nem norma.

Conjunto avaliado (esquema ``curadoria-concordancia-v2``). A bbox (e o traço) de cada
observação é recortada à envoltória dos tiles amostrados contíguos da mesma página/camada que ela
toca (se tocar grupos não contíguos, ao grupo que contém a maior parte dela); recorte vazio é
fora da amostra. Entram na comparação as observações cujo centro da bbox recortada está num tile
amostrado revisado pelas duas leituras, fora das regiões ilegíveis e com estado diferente de
``ilegivel``; o casamento usa as bboxes recortadas. Avaliável da
referência é a observação operacional, sustentada e com família do inventário (a mesma regra dos
denominadores de ``curation_compare``); casável do auditor é a operacional com família do
inventário em qualquer estado. O casamento é em etapas:

1. avaliáveis da referência x casáveis do auditor: mesma classe concorda, classe diferente diverge
   (motivo ``classe``); o estado do auditor não pesa (diferença só de estado vira o diagnóstico
   ``estado_divergente``, fora da medida);
2. avaliáveis da referência sem par x demais observações do auditor (não operacionais ou
   ``local-unknown``) no mesmo lugar: diverge (``papel_divergente``, motivo ``papel_ou_familia``);
3. observações sustentadas, operacionais e com família do auditor sem par x observações não
   avaliáveis da referência (provisórias, locais ou não operacionais): com mesma classe, papel e
   família (só a referência provisória) é o diagnóstico ``estado_divergente``, fora da medida;
   senão diverge (``papel_divergente``, motivo ``papel_estado_ou_familia``);
4. sobras avaliáveis da referência são ``so_referencia``; sobras sustentadas, operacionais e com
   família do auditor são ``so_auditoria``. As demais sobras (as duas leituras incertas, ou só uma
   incerta sem par confiante do outro lado) ficam fora do denominador, listadas em
   ``fora_do_denominador`` com contagem por motivo.

Classes lineares (``CLASSES_LINEARES``) ficam fora das etapas 1:1 e são comparadas por cobertura
de comprimento, só contra lineares de mesma classe, página e camada do outro lado. A linha de uma
observação é o traço recortado; sem traço, a linha central da bbox se o lado maior for >= 4 vezes
o menor, senão a melhor das duas diagonais. Cobertura de A por B é a fração de
``PONTOS_COBERTURA`` pontos ao longo de A a até ``TOLERANCIA_LINEAR`` de alguma geometria de B
(polilinha, ou o retângulo da bbox sem traço). Com ``COBERTURA_MINIMA``: avaliável da referência
coberta pelas casáveis do auditor concorda, senão é ``so_referencia``; incerta da referência coberta
por sustentada do auditor é ``estado_divergente`` (diagnóstico); observação do auditor coberta pela
referência não conta de novo; sustentada do auditor sem cobertura é ``so_auditoria`` e as demais
sem cobertura ficam fora do denominador. ID exato não é medido para lineares (não há pares 1:1).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from fractions import Fraction
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from typing import Any

from scripts.curation_compare import Escopo, _categoria, montar_escopo
from scripts.curation_reference import (
    FAMILIA_LOCAL,
    Inventario,
    ReferenciaInvalidaError,
    _criar_exclusivo,
    _dentro,
    _indice_vigente,
    _intersecta,
    carregar_referencia_vigente,
    validar_arquivo,
)
from scripts.curation_round import (
    FASES_TERMINAIS,
    RodadaError,
    _trava,
    carregar_checkpoint,
    diretorio_pdf,
    hash_arquivo,
    json_canonico,
    ler_json,
    selecionar_pdfs,
    transicionar,
    validar_transicao,
)
from scripts.symbol_benchmark_evaluator import _pairs

ESQUEMA_AMOSTRA = "curadoria-amostra-auditoria-v1"
# v2: conjunto avaliado, divergência de papel/família no denominador e recorte à amostra.
ESQUEMA_CONCORDANCIA = "curadoria-concordancia-v2"
DIRETORIO_AUDITORIA = "auditoria"
NOME_AMOSTRA = re.compile(r"amostra-v(\d{3})\.json")
NOME_CONCORDANCIA = re.compile(r"concordancia-v(\d{3})\.json")
VERSAO_AMOSTRA = re.compile(r"v\d{3}")
VERSAO_MAXIMA = 999
ESTADO_REVISAR = "a_revisar"
ESTADO_DESCARTADO = "descartado_branco"
FAIXAS_OCUPACAO = 3
NIVEL_BASE = 1
NIVEL_AMPLIADO = 2
LIMIAR_PADRAO = 0.90
CONFIAVEL = "referencia_confiavel"
AMPLIAR = "ampliar_amostra"
ENCERRAR = "encerrar_com_pendencia"
DECISOES = (CONFIAVEL, AMPLIAR, ENCERRAR)
# Motivos de ``Escopo.motivo_fora`` que significam "centro fora dos tiles revisados".
FORA_DOS_TILES = frozenset({"tile_nao_revisado", "tile_descartado", "pagina_fora_do_indice"})
MOTIVO_CLASSE = "classe"
MOTIVO_PAPEL = "papel_ou_familia"
MOTIVO_PAPEL_ESTADO = "papel_estado_ou_familia"
MOTIVOS_DIVERGENCIA = (MOTIVO_CLASSE, MOTIVO_PAPEL_ESTADO, MOTIVO_PAPEL)
LIMITACOES = (
    "a concordância mede consistência entre duas leituras de IA; não é confirmação humana, "
    "gabarito nem norma, e leituras do mesmo modelo podem errar de forma correlacionada",
    "a bbox (e o traço) de cada observação das duas leituras é recortada à envoltória dos tiles "
    "amostrados contíguos da mesma página e camada que ela toca (grupos não contíguos: vale o que "
    "contém a maior parte da bbox); o casamento usa as bboxes recortadas",
    "só entram observações cujo centro da bbox recortada está num tile amostrado revisado pelas "
    "duas leituras e fora das regiões ilegíveis de ambas; objeto que atravessa grupos de tiles "
    "amostrados não contíguos é comparado só no grupo maior",
    "casamento pelo critério geométrico do protocolo symbols-e02-v1, primeiro na mesma classe "
    "(class_id) e depois entre classes; o limiar se aplica à concordância de classe",
    "denominador: avaliáveis da referência (operacionais, sustentadas, com família do inventário) "
    "e observações do auditor operacionais com família do inventário (provisória do auditor só "
    "pesa quando casa); papel ou família divergente no mesmo lugar conta como divergência; "
    "observações incertas dos dois lados ficam em fora_do_denominador; referência provisória "
    "com a mesma classe e papel de uma sustentada do auditor é só diagnóstico (estado_divergente)",
    "classes lineares (CABO_AEREO) são comparadas por cobertura de comprimento com tolerância e "
    "cobertura mínima fixas (classe.lineares), não por casamento 1:1; linear de um lado e não "
    "linear do outro no mesmo lugar não são comparados, e ID exato não é medido para lineares",
    "em página cuja camada anotada é igual à base, observações da camada annotation são "
    "comparadas como base",
)

Registro = dict[str, Any]


class AuditoriaRecusadaError(RodadaError):
    """Amostragem ou concordância recusada antes de qualquer escrita."""


# --- parâmetros -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ParametrosAmostra:
    fracao: float = 0.15
    minimo: int = 4
    semente: int = 0
    incluir_descartados: float = 0.05

    def validar(self) -> None:
        if not (math.isfinite(self.fracao) and 0 < self.fracao <= 1):
            raise RodadaError(f"--fracao {self.fracao} fora de (0, 1]")
        if self.minimo < 1:
            raise RodadaError(f"--minimo {self.minimo} deve ser >= 1")
        if self.semente < 0:
            raise RodadaError(f"--semente {self.semente} deve ser >= 0")
        if not (math.isfinite(self.incluir_descartados) and 0 <= self.incluir_descartados <= 1):
            raise RodadaError(f"--incluir-descartados {self.incluir_descartados} fora de [0, 1]")

    def ampliada(self) -> ParametrosAmostra:
        return replace(
            self,
            fracao=min(1.0, self.fracao * 2),
            minimo=self.minimo * 2,
            incluir_descartados=min(1.0, self.incluir_descartados * 2),
        )

    def registro(self) -> Registro:
        return asdict(self)


def _parametros_de(registro: Mapping[str, Any]) -> ParametrosAmostra:
    return ParametrosAmostra(
        fracao=float(registro["fracao"]),
        minimo=int(registro["minimo"]),
        semente=int(registro["semente"]),
        incluir_descartados=float(registro["incluir_descartados"]),
    )


def _teto(valor: float) -> int:
    """Teto tolerante a ruído de ponto flutuante (0,2 x 15 = 3, não 4)."""
    return math.ceil(round(valor, 9))


# --- população, estratos e sorteio -----------------------------------------------------------


def populacao(indice: Registro) -> list[Registro]:
    """Tiles amostráveis: todos, exceto os anotados idênticos à base.

    Fica fora a camada anotada de página igual à base e, nas demais páginas, cada tile anotado
    com os mesmos bytes do gêmeo da base (mesma página, linha e coluna): a leitura registra uma
    vez, na base, o que as duas camadas mostram igual.
    """
    iguais = {
        int(pagina["pagina"])
        for pagina in indice["paginas"]
        if pagina.get("camada_anotada_igual_base")
    }
    base = {
        (tile["pagina"], tile.get("linha"), tile.get("coluna")): tile.get("sha256")
        for tile in indice["tiles"]
        if tile["camada"] == "base"
    }
    return [tile for tile in indice["tiles"] if not _anotado_identico(tile, iguais, base)]


def _anotado_identico(
    tile: Registro, iguais: set[int], base: dict[tuple[Any, Any, Any], Any]
) -> bool:
    if tile["camada"] != "annotation":
        return False
    if tile["pagina"] in iguais:
        return True
    gemeo = base.get((tile["pagina"], tile.get("linha"), tile.get("coluna")))
    return gemeo is not None and gemeo == tile.get("sha256")


def _tercis(tiles: Sequence[Registro]) -> list[list[Registro]]:
    ordenados = sorted(tiles, key=lambda tile: (float(tile["ocupacao"]), str(tile["id"])))
    faixas = min(FAIXAS_OCUPACAO, len(ordenados))
    total = len(ordenados)
    return [ordenados[n * total // faixas : (n + 1) * total // faixas] for n in range(faixas)]


def estratos(indice: Registro) -> dict[str, list[Registro]]:
    """Estratos ``pNNN-ocupacao-K`` (tercis de ocupação dos ``a_revisar``) e ``pNNN-descartados``.

    A ocupação de cada faixa é medida sobre a população da página (``populacao``).
    """
    por_pagina: dict[int, list[Registro]] = defaultdict(list)
    for tile in populacao(indice):
        por_pagina[int(tile["pagina"])].append(tile)
    grupos: dict[str, list[Registro]] = {}
    for pagina, tiles in sorted(por_pagina.items()):
        revisar = [tile for tile in tiles if tile["estado"] == ESTADO_REVISAR]
        for faixa, membros in enumerate(_tercis(revisar), start=1):
            grupos[f"p{pagina:03d}-ocupacao-{faixa}"] = membros
        descartados = [tile for tile in tiles if tile["estado"] == ESTADO_DESCARTADO]
        if descartados:
            grupos[f"p{pagina:03d}-descartados"] = descartados
    return grupos


def _chave_sorteio(semente: int, sha256_pdf: str, tile_id: str) -> str:
    return sha256(f"{semente}\0{sha256_pdf}\0{tile_id}".encode()).hexdigest()


def _alocar(tamanhos: Mapping[str, int], total: int) -> dict[str, int]:
    """Um tile por estrato e o restante proporcional ao tamanho (maior resto; empate por nome)."""
    alocacao = dict.fromkeys(tamanhos, 1)
    populacao_total = sum(tamanhos.values())
    while sum(alocacao.values()) < total:
        candidatos = [nome for nome in tamanhos if alocacao[nome] < tamanhos[nome]]
        escolhido = min(
            candidatos,
            key=lambda nome: (
                alocacao[nome] - Fraction(tamanhos[nome] * total, populacao_total),
                nome,
            ),
        )
        alocacao[escolhido] += 1
    return alocacao


def _quantidades(grupos: Mapping[str, Sequence[Registro]], p: ParametrosAmostra) -> dict[str, int]:
    revisar = {nome: len(m) for nome, m in grupos.items() if not nome.endswith("-descartados")}
    populacao_revisar = sum(revisar.values())
    total = min(populacao_revisar, max(p.minimo, _teto(p.fracao * populacao_revisar), len(revisar)))
    quantidades = _alocar(revisar, total) if revisar else {}
    for nome, membros in grupos.items():
        if nome.endswith("-descartados"):
            quantidades[nome] = min(len(membros), _teto(p.incluir_descartados * len(membros)))
    return quantidades


def sortear(
    indice: Registro, parametros: ParametrosAmostra, *, obrigatorios: Collection[str] = ()
) -> list[str]:
    """Ids sorteados na ordem do índice; dependem só do índice, dos parâmetros e da semente.

    Em cada estrato os tiles são ordenados por SHA-256 de (semente, SHA-256 do PDF, id) e os
    primeiros entram. ``obrigatorios`` (amostra anterior, na ampliação) entram sempre.
    """
    grupos = estratos(indice)
    quantidades = _quantidades(grupos, parametros)
    escolhidos = set(obrigatorios)
    for nome, membros in grupos.items():
        ordem = sorted(
            membros,
            key=lambda t: _chave_sorteio(parametros.semente, indice["sha256_pdf"], str(t["id"])),
        )
        escolhidos.update(str(tile["id"]) for tile in ordem[: quantidades[nome]])
    return [str(tile["id"]) for tile in indice["tiles"] if tile["id"] in escolhidos]


def montar_amostra(
    indice: Registro,
    indice_sha256: str,
    parametros: ParametrosAmostra,
    *,
    versao: str,
    nivel: int = NIVEL_BASE,
    anterior: Registro | None = None,
) -> Registro:
    """Conteúdo do arquivo de amostra: só ids/caminhos de tiles e contagens por estrato."""
    obrigatorios = [str(tile["id"]) for tile in anterior["tiles"]] if anterior else []
    ids = sortear(indice, parametros, obrigatorios=obrigatorios)
    por_id = {str(tile["id"]): tile for tile in indice["tiles"]}
    escolhidos = set(ids)
    grupos = estratos(indice)
    return {
        "amostra_anterior": (
            {"arquivo": anterior["_arquivo"], "sha256": anterior["_sha256"]} if anterior else None
        ),
        "estratos": [
            {
                "amostrados": sum(str(t["id"]) in escolhidos for t in membros),
                "estrato": nome,
                "populacao": len(membros),
            }
            for nome, membros in grupos.items()
        ],
        "indice_tiles_sha256": indice_sha256,
        "nivel": nivel,
        "parametros": parametros.registro(),
        "pdf_id": indice["pdf_id"],
        "schema_version": ESQUEMA_AMOSTRA,
        "sha256_pdf": indice["sha256_pdf"],
        "tiles": [
            {
                "arquivo": por_id[i]["arquivo"],
                "camada": por_id[i]["camada"],
                "id": i,
                "pagina": por_id[i]["pagina"],
            }
            for i in ids
        ],
        "totais": {"populacao": sum(len(m) for m in grupos.values()), "tiles": len(ids)},
        "versao": versao,
    }


# --- arquivos da auditoria --------------------------------------------------------------------


def _versoes(pasta: Path, padrao: re.Pattern[str]) -> list[int]:
    if not pasta.is_dir():
        return []
    return sorted(
        int(encontrado.group(1))
        for item in pasta.iterdir()
        if (encontrado := padrao.fullmatch(item.name))
    )


def _proxima(numeros: Sequence[int], rotulo: str) -> int:
    numero = max(numeros, default=0) + 1
    if numero > VERSAO_MAXIMA:
        raise AuditoriaRecusadaError(f"limite de {VERSAO_MAXIMA} versões de {rotulo}")
    return numero


def _relativo(rodada_dir: Path, caminho: Path) -> str:
    return caminho.resolve().relative_to(Path(rodada_dir).resolve()).as_posix()


def carregar_amostra(
    rodada_dir: Path, pdf_id: str, versao: str | None = None
) -> tuple[Registro, Path]:
    """Amostra ``vNNN`` ou ``amostra-vNNN`` (padrão: a de maior número), esquema e ``pdf_id``."""
    pasta = diretorio_pdf(rodada_dir, pdf_id) / DIRETORIO_AUDITORIA
    if versao is None:
        numeros = _versoes(pasta, NOME_AMOSTRA)
        if not numeros:
            raise AuditoriaRecusadaError(f"{pdf_id} não tem amostra; rode amostrar antes")
        versao = f"v{numeros[-1]:03d}"
    versao = versao.removeprefix("amostra-")
    if not VERSAO_AMOSTRA.fullmatch(versao):
        raise AuditoriaRecusadaError(f"versão de amostra inválida: {versao} (use vNNN)")
    caminho = pasta / f"amostra-{versao}.json"
    if not caminho.is_file():
        raise AuditoriaRecusadaError(f"{pdf_id}: amostra-{versao}.json não existe")
    dados = ler_json(caminho)
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_AMOSTRA:
        raise AuditoriaRecusadaError(f"amostra-{versao}.json com esquema desconhecido")
    if dados.get("pdf_id") != pdf_id:
        raise AuditoriaRecusadaError(f"amostra-{versao}.json é de outro PDF")
    return dados, caminho


def _relatorios(pasta_pdf: Path) -> list[Registro]:
    """Relatórios de concordância já gravados, em ordem de versão (nunca sobrescritos)."""
    relatorios = []
    for numero in _versoes(pasta_pdf, NOME_CONCORDANCIA):
        dados = ler_json(pasta_pdf / f"concordancia-v{numero:03d}.json")
        if not isinstance(dados, dict) or dados.get("decisao") not in DECISOES:
            raise AuditoriaRecusadaError(f"concordancia-v{numero:03d}.json ilegível ou sem decisão")
        relatorios.append(dados)
    return relatorios


def _bloqueio(relatorios: Sequence[Registro]) -> str | None:
    decisoes = {relatorio["decisao"] for relatorio in relatorios}
    if ENCERRAR in decisoes:
        return ENCERRAR
    if AMPLIAR in decisoes:
        return AMPLIAR
    return None


# --- amostrar --------------------------------------------------------------------------------


def _base_da_ampliacao(rodada_dir: Path, relatorios: Sequence[Registro]) -> Registro:
    if not relatorios or relatorios[-1]["decisao"] != AMPLIAR:
        raise AuditoriaRecusadaError(
            f"--ampliar exige que a última concordância tenha decidido {AMPLIAR}"
        )
    registro = relatorios[-1]["amostra"]
    caminho = Path(rodada_dir).resolve() / registro["arquivo"]
    if not caminho.is_file() or hash_arquivo(caminho) != registro["sha256"]:
        raise AuditoriaRecusadaError("amostra auditada difere da registrada na concordância")
    base = ler_json(caminho)
    if base.get("nivel") != NIVEL_BASE:
        raise AuditoriaRecusadaError("só a amostra de nível 1 pode ser ampliada")
    return {**base, "_arquivo": registro["arquivo"], "_sha256": registro["sha256"]}


def _gravar_amostra(
    pasta: Path, conteudo: Registro, existentes: Sequence[int]
) -> tuple[Path, bool]:
    """Reaproveita a última versão se for byte a byte igual; senão cria a próxima versão."""
    if existentes:
        ultima = pasta / f"amostra-v{existentes[-1]:03d}.json"
        mesma = json_canonico({**conteudo, "versao": f"amostra-v{existentes[-1]:03d}"}).encode()
        if ultima.read_bytes() == mesma:
            return ultima, True
    numero = _proxima(existentes, "amostra")
    destino = pasta / f"amostra-v{numero:03d}.json"
    pasta.mkdir(exist_ok=True)
    _criar_exclusivo(destino, json_canonico({**conteudo, "versao": destino.stem}).encode())
    return destino, False


def amostrar_pdf(
    rodada_dir: Path,
    pdf_id: str,
    parametros: ParametrosAmostra | None = None,
    *,
    ampliar: bool = False,
) -> Registro:
    """Sorteia e grava a amostra de um PDF; recusa (``RodadaError``) sem escrever nada."""
    parametros = parametros or ParametrosAmostra()
    parametros.validar()
    pasta_pdf = diretorio_pdf(rodada_dir, pdf_id)
    pasta = pasta_pdf / DIRETORIO_AUDITORIA
    with _trava(pasta):
        checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
        if checkpoint["fase"] in FASES_TERMINAIS:
            raise AuditoriaRecusadaError(f"{pdf_id} está em fase terminal ({checkpoint['fase']})")
        indice, indice_sha = _indice_vigente(rodada_dir, pdf_id, checkpoint)
        relatorios = _relatorios(pasta_pdf)
        base = None
        if ampliar:
            base = _base_da_ampliacao(rodada_dir, relatorios)
            parametros = _parametros_de(base["parametros"]).ampliada()
        elif _bloqueio(relatorios) is not None:
            raise AuditoriaRecusadaError(
                f"{pdf_id}: uma concordância anterior decidiu {_bloqueio(relatorios)}; nova "
                "amostra de nível 1 não é permitida (use --ampliar quando pedido)"
            )
        conteudo = montar_amostra(
            indice,
            indice_sha,
            parametros,
            versao="",
            nivel=NIVEL_AMPLIADO if base else NIVEL_BASE,
            anterior=base,
        )
        destino, reutilizada = _gravar_amostra(pasta, conteudo, _versoes(pasta, NOME_AMOSTRA))
    ids = set(sortear_ids(conteudo))
    estados = Counter(tile["estado"] for tile in indice["tiles"] if tile["id"] in ids)
    return {
        "a_revisar": estados[ESTADO_REVISAR],
        "arquivo": _relativo(rodada_dir, destino),
        "descartados": estados[ESTADO_DESCARTADO],
        "falhas": [],
        "nivel": conteudo["nivel"],
        "pdf_id": pdf_id,
        "reutilizada": reutilizada,
        "status": "sucesso",
        "tiles": conteudo["totais"]["tiles"],
        "versao": destino.stem,
    }


def sortear_ids(amostra: Registro) -> list[str]:
    """Ids dos tiles de um conteúdo de amostra."""
    return [str(tile["id"]) for tile in amostra["tiles"]]


def amostrar(
    rodada_dir: Path,
    pdf_ids: Sequence[str],
    *,
    parametros: ParametrosAmostra | None = None,
    ampliar: bool = False,
) -> Registro:
    """Amostra cada PDF; recusas ficam isoladas no PDF (``recusado``), sem tocar os demais."""
    parametros = parametros or ParametrosAmostra()
    parametros.validar()
    pdfs = []
    for pdf_id in pdf_ids:
        try:
            pdfs.append(amostrar_pdf(rodada_dir, pdf_id, parametros, ampliar=ampliar))
        except RodadaError as erro:
            pdfs.append({"falhas": [str(erro)], "pdf_id": pdf_id, "status": "recusado"})
        except Exception as erro:  # falha inesperada isolada no PDF
            pdfs.append(
                {"falhas": [f"{type(erro).__name__}: {erro}"], "pdf_id": pdf_id, "status": "falha"}
            )
    totais = Counter(item["status"] for item in pdfs)
    return {
        "pdfs": pdfs,
        "totais": {status: totais.get(status, 0) for status in ("sucesso", "recusado", "falha")},
    }


# --- concordância ---------------------------------------------------------------------------


Caixa = tuple[float, float, float, float]
Ponto = tuple[float, float]


@dataclass(frozen=True)
class _Lados:
    escopo_referencia: Escopo
    escopo_auditoria: Escopo
    iguais: frozenset[int]
    # Caixas dos tiles amostrados por (página, camada de comparação).
    amostrados: Mapping[tuple[int, str], list[Caixa]]


def _avaliavel_referencia(observacao: Mapping[str, Any]) -> bool:
    """Operacional, sustentada e com família do inventário (regra de ``curation_compare``)."""
    return _categoria(dict(observacao)) == "operacional"


def _casavel_auditoria(observacao: Mapping[str, Any]) -> bool:
    """Observação do auditor que casa como positiva: operacional, com família, não ilegível."""
    return bool(
        observacao["papel"] == "operacional"
        and observacao["familia"] != FAMILIA_LOCAL
        and observacao["estado"] != "ilegivel"
    )


def _motivo_incerteza(observacao: Mapping[str, Any]) -> str:
    """Por que uma observação não é avaliável: ``local``, ``provisorio`` ou ``papel_<papel>``."""
    if observacao["familia"] == FAMILIA_LOCAL:
        return "local"
    if observacao["estado"] != "sustentado_por_evidencia":
        return str(observacao["estado"])
    return f"papel_{observacao['papel']}"


# --- recorte à amostra ----------------------------------------------------------------------


def _grupos_contiguos(tiles: Sequence[Caixa]) -> list[list[Caixa]]:
    """Componentes de tiles ligados por sobreposição ou adjacência, em ordem determinística."""
    restantes = sorted(tiles)
    grupos: list[list[Caixa]] = []
    while restantes:
        grupo = [restantes.pop(0)]
        for tile in grupo:  # ``grupo`` cresce durante a varredura (busca em largura)
            vizinhos = [outro for outro in restantes if _intersecta(tile, outro)]
            restantes = [outro for outro in restantes if outro not in vizinhos]
            grupo.extend(vizinhos)
        grupos.append(grupo)
    return grupos


def _intersecao_com_envoltoria(bbox: Caixa, tiles: Sequence[Caixa]) -> Caixa | None:
    x0 = max(bbox[0], min(tile[0] for tile in tiles))
    y0 = max(bbox[1], min(tile[1] for tile in tiles))
    x1 = min(bbox[2], max(tile[2] for tile in tiles))
    y1 = min(bbox[3], max(tile[3] for tile in tiles))
    return (x0, y0, x1, y1) if x0 <= x1 and y0 <= y1 else None


def _tamanho(caixa: Caixa) -> tuple[float, float]:
    """Área e, para desempatar bboxes finas (área nula), o maior lado."""
    largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    return largura * altura, max(largura, altura)


def _recorte(bbox: Caixa, tiles: Sequence[Caixa]) -> Caixa | None:
    """Interseção da bbox com a envoltória dos tiles contíguos que ela toca; ``None`` se vazia.

    Se os tiles tocados formam grupos não contíguos, vale o grupo que contém a maior parte da
    bbox (maior área; empate pelo maior lado, depois pela ordem dos grupos).
    """
    tocados = [tile for tile in tiles if _intersecta(bbox, tile)]
    recortes = [
        caixa
        for grupo in _grupos_contiguos(tocados)
        if (caixa := _intersecao_com_envoltoria(bbox, grupo)) is not None
    ]
    if not recortes:
        return None
    return max(recortes, key=_tamanho)


def _recortar_segmento(p: Ponto, q: Ponto, caixa: Caixa) -> tuple[Ponto, Ponto] | None:
    """Trecho do segmento ``pq`` dentro da caixa (Liang-Barsky); ``None`` se não há."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    inicio, fim = 0.0, 1.0
    for direcao, folga in (
        (-dx, p[0] - caixa[0]),
        (dx, caixa[2] - p[0]),
        (-dy, p[1] - caixa[1]),
        (dy, caixa[3] - p[1]),
    ):
        if direcao == 0:
            if folga < 0:
                return None
            continue
        razao = folga / direcao
        if direcao < 0:
            inicio = max(inicio, razao)
        else:
            fim = min(fim, razao)
        if inicio > fim:
            return None
    return (p[0] + inicio * dx, p[1] + inicio * dy), (p[0] + fim * dx, p[1] + fim * dy)


def _recortar_traco(traco: Sequence[Sequence[float]], caixa: Caixa) -> list[list[float]] | None:
    """Polilinha recortada à caixa (trechos dentro dela, em ordem); ``None`` se sobra < 2 pontos."""
    pontos: list[Ponto] = []
    for p, q in pairwise(traco):
        trecho = _recortar_segmento((float(p[0]), float(p[1])), (float(q[0]), float(q[1])), caixa)
        for ponto in trecho or ():
            if not pontos or pontos[-1] != ponto:
                pontos.append(ponto)
    return [list(ponto) for ponto in pontos] if len(pontos) >= 2 else None


def _motivo_exclusao(observacao: Registro, lados: _Lados, bbox: Caixa) -> str | None:
    """``None`` se a observação entra na comparação; senão o motivo de ficar de fora.

    ``bbox`` é a caixa recortada à amostra: é o centro dela que decide a entrada.
    """
    pagina, camada = observacao["pagina"], observacao["camada"]
    auditoria = lados.escopo_auditoria.motivo_fora(pagina, camada, bbox)
    if auditoria in FORA_DOS_TILES:
        return "fora_da_amostra"
    if auditoria == "regiao_ilegivel":
        return "regiao_ilegivel_auditoria"
    referencia = lados.escopo_referencia.motivo_fora(pagina, camada, bbox)
    if referencia == "regiao_ilegivel":
        return "regiao_ilegivel_referencia"
    if referencia is not None:
        return "tile_nao_revisado_pela_referencia"
    if observacao["estado"] == "ilegivel":
        return "estado_ilegivel"
    return None


def _camada_comparada(observacao: Registro, lados: _Lados) -> str:
    """Camada anotada de página igual à base é comparada como base."""
    return "base" if observacao["pagina"] in lados.iguais else str(observacao["camada"])


def _caixa_recortada(observacao: Registro, lados: _Lados) -> Caixa | None:
    """Bbox recortada aos tiles amostrados da mesma página/camada; ``None`` se vazia."""
    local = (observacao["pagina"], _camada_comparada(observacao, lados))
    return _recorte(_caixa(observacao["bbox"]), lados.amostrados.get(local, []))


def _item(observacao: Registro, origem: str, lados: _Lados, caixa: Caixa) -> Registro:
    """Observação no formato de ocorrência do avaliador, com a bbox ``caixa`` recortada."""
    camada = _camada_comparada(observacao, lados)
    original = _caixa(observacao["bbox"])
    item: Registro = {
        "bbox": list(caixa),
        "class_id": observacao["class_id"],
        "document_id": "pdf",
        "id": f"{origem}:{observacao['id']}",
        "layer": camada,
        "page": observacao["pagina"],
        "recortada": caixa != original,
    }
    traco = observacao.get("trace")
    if traco:
        traco = _recortar_traco(traco, caixa) if item["recortada"] else traco
    if traco:
        item["trace"] = traco
    return item


def _separar(
    observacoes: Sequence[Registro], origem: str, lados: _Lados
) -> tuple[list[Registro], Registro]:
    comparaveis: list[Registro] = []
    motivos: Counter[str] = Counter()
    for observacao in observacoes:
        caixa = _caixa_recortada(observacao, lados)
        motivo = "fora_da_amostra" if caixa is None else _motivo_exclusao(observacao, lados, caixa)
        if motivo is None and caixa is not None:
            comparaveis.append(_item(observacao, origem, lados, caixa))
        else:
            motivos[motivo or "fora_da_amostra"] += 1
    fora = motivos.pop("fora_da_amostra", 0)
    resumo = {
        "comparaveis": len(comparaveis),
        "excluidas": dict(sorted(motivos.items())),
        "fora_da_amostra": fora,
        "recortadas": sum(item["recortada"] for item in comparaveis),
        "total": len(observacoes),
    }
    return comparaveis, resumo


def _casar(
    auditoria: list[Registro], referencia: list[Registro]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[str], list[str]]:
    """Pares de mesma classe, pares de classe divergente e sobras de cada lado (ids prefixados)."""
    mesma, _ = _pairs(auditoria, referencia)
    usados = {p["prediction_id"] for p in mesma} | {p["reference_id"] for p in mesma}
    resto_auditoria = [item for item in auditoria if item["id"] not in usados]
    resto_referencia = [item for item in referencia if item["id"] not in usados]
    divergentes, _ = _pairs(resto_auditoria, resto_referencia, classify=False)
    usados |= {p["prediction_id"] for p in divergentes} | {p["reference_id"] for p in divergentes}
    return (
        [(p["reference_id"], p["prediction_id"]) for p in mesma],
        [(p["reference_id"], p["prediction_id"]) for p in divergentes],
        sorted(item["id"] for item in referencia if item["id"] not in usados),
        sorted(item["id"] for item in auditoria if item["id"] not in usados),
    )


Par = tuple[str, str]


@dataclass
class _Casamento:
    """Resultado das etapas de casamento (pares como ``(id_referencia, id_auditoria)``)."""

    concordantes: list[Par]
    divergentes: dict[str, list[Par]]
    so_referencia: list[str]
    so_auditoria: list[str]
    fora_referencia: list[str]
    fora_auditoria: list[str]
    # Etapa 3 de mesma classe e papel: incerta da referência x sustentada do auditor.
    so_estado: list[Par] = field(default_factory=list)


def _so_estado(originais: Mapping[str, Registro], par: Par) -> bool:
    """O par difere só no estado (mesma classe, papel e família)?"""
    referencia, auditoria = originais[par[0]], originais[par[1]]
    return all(referencia[chave] == auditoria[chave] for chave in ("class_id", "papel", "familia"))


def _todos_os_pares(auditoria: list[Registro], referencia: list[Registro]) -> list[Par]:
    mesma, divergentes, _, _ = _casar(auditoria, referencia)
    return sorted(mesma + divergentes)


def _casar_em_etapas(
    itens_ref: list[Registro],
    itens_aud: list[Registro],
    originais: Mapping[str, Registro],
) -> _Casamento:
    """Casamento do conjunto avaliado (etapas descritas no cabeçalho do módulo)."""

    def filtrar(
        itens: list[Registro], regra: Callable[[Mapping[str, Any]], bool], valor: bool = True
    ) -> list[Registro]:
        return [item for item in itens if regra(originais[item["id"]]) is valor]

    ref_aval = filtrar(itens_ref, _avaliavel_referencia)
    ref_incertas = filtrar(itens_ref, _avaliavel_referencia, False)
    # Etapa 1: avaliáveis da referência x casáveis do auditor (qualquer estado).
    mesma, classe, sobra_ref, sobra_aud = _casar(filtrar(itens_aud, _casavel_auditoria), ref_aval)
    # Etapa 2: avaliável da referência sem par x não operacional ou local do auditor.
    restantes_ref = [item for item in ref_aval if item["id"] in set(sobra_ref)]
    papel = _todos_os_pares(filtrar(itens_aud, _casavel_auditoria, False), restantes_ref)
    # Etapa 3: sustentada operacional do auditor sem par x incerta da referência.
    restantes_aud = [item for item in itens_aud if item["id"] in set(sobra_aud)]
    confiantes = filtrar(restantes_aud, _avaliavel_referencia)
    pares_estado = _todos_os_pares(confiantes, ref_incertas)
    so_estado = [par for par in pares_estado if _so_estado(originais, par)]
    papel_estado = [par for par in pares_estado if par not in so_estado]
    usados = {i for par in mesma + classe + papel + pares_estado for i in par}
    ids_confiantes = {item["id"] for item in confiantes}
    return _Casamento(
        concordantes=mesma,
        divergentes={MOTIVO_CLASSE: classe, MOTIVO_PAPEL: papel, MOTIVO_PAPEL_ESTADO: papel_estado},
        so_referencia=sorted(i for i in sobra_ref if i not in usados),
        so_auditoria=sorted(i for i in ids_confiantes if i not in usados),
        fora_referencia=sorted(item["id"] for item in ref_incertas if item["id"] not in usados),
        fora_auditoria=sorted(
            item["id"]
            for item in itens_aud
            if item["id"] not in usados and item["id"] not in ids_confiantes
        ),
        so_estado=so_estado,
    )


# --- objetos lineares: cobertura de comprimento --------------------------------------------

# Classes que os leitores segmentam de modo diferente (por vão entre postes, por trecho visível
# no tile): comparadas por cobertura de comprimento, fora do casamento geométrico 1:1.
CLASSES_LINEARES = frozenset({"CABO_AEREO"})
# 0,006 da diagonal da página no espaço normalizado [0,1] x [0,1] (diagonal = raiz de 2).
TOLERANCIA_LINEAR = 0.006 * math.sqrt(2)
COBERTURA_MINIMA = 0.5
# Pontos amostrados ao longo da linha (meios de trechos de comprimento igual).
PONTOS_COBERTURA = 50
# bbox sem traço com lado maior >= 4 x lado menor: linha central ao longo do lado maior; senão
# a linha é ambígua e valem a melhor das duas diagonais.
RAZAO_ASPECTO_LINEAR = 4.0

Linha = list[Ponto]


def _e_linear(item: Registro) -> bool:
    return item["class_id"] in CLASSES_LINEARES


def _linhas_candidatas(item: Registro) -> list[Linha]:
    """Polilinha do traço; sem traço, a linha central da bbox ou as duas diagonais."""
    if item.get("trace"):
        return [[(float(p[0]), float(p[1])) for p in item["trace"]]]
    x0, y0, x1, y1 = _caixa(item["bbox"])
    largura, altura = x1 - x0, y1 - y0
    if max(largura, altura) >= RAZAO_ASPECTO_LINEAR * min(largura, altura):
        if largura >= altura:
            return [[(x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)]]
        return [[((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)]]
    return [[(x0, y0), (x1, y1)], [(x0, y1), (x1, y0)]]


def _pontos_ao_longo(linha: Linha) -> list[Ponto]:
    """``PONTOS_COBERTURA`` pontos nos meios de trechos de comprimento igual da polilinha."""
    segmentos = list(pairwise(linha))
    comprimentos = [math.dist(p, q) for p, q in segmentos]
    total = sum(comprimentos)
    if total == 0:
        return [linha[0]]
    pontos: list[Ponto] = []
    indice, acumulado = 0, 0.0
    for n in range(PONTOS_COBERTURA):
        alvo = (n + 0.5) / PONTOS_COBERTURA * total
        while indice < len(segmentos) - 1 and acumulado + comprimentos[indice] < alvo:
            acumulado += comprimentos[indice]
            indice += 1
        (px, py), (qx, qy) = segmentos[indice]
        t = (alvo - acumulado) / comprimentos[indice] if comprimentos[indice] else 0.0
        pontos.append((px + t * (qx - px), py + t * (qy - py)))
    return pontos


def _distancia_segmento(ponto: Ponto, p: Ponto, q: Ponto) -> float:
    dx, dy = q[0] - p[0], q[1] - p[1]
    quadrado = dx * dx + dy * dy
    projecao = ((ponto[0] - p[0]) * dx + (ponto[1] - p[1]) * dy) / quadrado if quadrado else 0.0
    t = min(1.0, max(0.0, projecao))
    return math.dist(ponto, (p[0] + t * dx, p[1] + t * dy))


def _distancia(ponto: Ponto, alvo: Registro) -> float:
    """Distância à polilinha do alvo; sem traço, ao retângulo da bbox (zero dentro dele)."""
    if alvo.get("trace"):
        linha = _linhas_candidatas(alvo)[0]
        return min(_distancia_segmento(ponto, p, q) for p, q in pairwise(linha))
    x0, y0, x1, y1 = _caixa(alvo["bbox"])
    return math.hypot(
        max(x0 - ponto[0], 0.0, ponto[0] - x1), max(y0 - ponto[1], 0.0, ponto[1] - y1)
    )


def _cobertura(item: Registro, alvos: Sequence[Registro]) -> float:
    """Fração dos pontos de ``item`` a até ``TOLERANCIA_LINEAR`` de um alvo de mesma classe.

    Alvos de outra página, camada ou classe não cobrem; com duas diagonais candidatas, vale a
    de maior cobertura.
    """
    local = (item["page"], item["layer"], item["class_id"])
    mesmos = [alvo for alvo in alvos if (alvo["page"], alvo["layer"], alvo["class_id"]) == local]
    if not mesmos:
        return 0.0
    melhor = 0.0
    for linha in _linhas_candidatas(item):
        pontos = _pontos_ao_longo(linha)
        cobertos = sum(
            any(_distancia(ponto, alvo) <= TOLERANCIA_LINEAR for alvo in mesmos) for ponto in pontos
        )
        melhor = max(melhor, cobertos / len(pontos))
    return melhor


@dataclass
class _Lineares:
    """Classificação das observações lineares por cobertura (ids prefixados)."""

    concordantes: list[str] = field(default_factory=list)
    so_referencia: list[str] = field(default_factory=list)
    so_auditoria: list[str] = field(default_factory=list)
    so_estado: list[str] = field(default_factory=list)
    fora_referencia: list[str] = field(default_factory=list)
    fora_auditoria: list[str] = field(default_factory=list)
    cobertura: dict[str, float] = field(default_factory=dict)


def _cobrir_lineares(
    itens_ref: list[Registro], itens_aud: list[Registro], originais: Mapping[str, Registro]
) -> _Lineares:
    """Regras de cobertura (cabeçalho do módulo); lineares não entram no casamento 1:1."""
    resultado = _Lineares()
    casaveis = [item for item in itens_aud if _casavel_auditoria(originais[item["id"]])]
    confiantes = [item for item in casaveis if _avaliavel_referencia(originais[item["id"]])]
    for item in itens_ref:
        avaliavel = _avaliavel_referencia(originais[item["id"]])
        cobertura = _cobertura(item, casaveis if avaliavel else confiantes)
        resultado.cobertura[item["id"]] = cobertura
        coberto, descoberto = (
            (resultado.concordantes, resultado.so_referencia)
            if avaliavel
            else (resultado.so_estado, resultado.fora_referencia)
        )
        (coberto if cobertura >= COBERTURA_MINIMA else descoberto).append(item["id"])
    for item in itens_aud:
        cobertura = _cobertura(item, itens_ref)
        resultado.cobertura[item["id"]] = cobertura
        if cobertura >= COBERTURA_MINIMA:
            continue  # já contado pelo lado da referência, ou só diferença de estado
        if _avaliavel_referencia(originais[item["id"]]):
            resultado.so_auditoria.append(item["id"])
        else:
            resultado.fora_auditoria.append(item["id"])
    return resultado


def _proporcao(concordantes: int, total: int) -> float | None:
    return concordantes / total if total else None


def decidir(concordantes: int, total: int, *, limiar: float, nivel: int) -> tuple[str, str]:
    """Decisão sobre a concordância de classe (comparação exata, sem ruído de ponto flutuante)."""
    if total and Fraction(concordantes, total) >= Fraction(str(limiar)):
        return CONFIAVEL, f"concordância de classe {concordantes}/{total} >= limiar {limiar}"
    medida = (
        f"concordância de classe {concordantes}/{total} abaixo do limiar {limiar}"
        if total
        else "amostra sem observações comparáveis nas duas leituras"
    )
    if nivel < NIVEL_AMPLIADO:
        return AMPLIAR, f"{medida}; amostrar --ampliar e auditar de novo"
    return ENCERRAR, f"{medida} também na amostra ampliada; encerrar o PDF com pendência"


@dataclass
class _Medicao:
    referencia: Mapping[str, Registro]
    auditoria: Mapping[str, Registro]
    lados: _Lados
    discordancias: list[Registro]
    # Bbox recortada à amostra de cada observação comparável (ids prefixados).
    recortes: dict[str, list[float]] = field(default_factory=dict)


def _campos_lado(observacao: Registro | None, sufixo: str) -> Registro:
    chaves = ("class_id", "id_inventario", "papel", "estado", "familia")
    nomes = ("class", "id_inventario", "papel", "estado", "familia")
    return {
        f"{nome}_{sufixo}": observacao.get(chave) if observacao else None
        for nome, chave in zip(nomes, chaves, strict=True)
    }


def _discordancia(
    medicao: _Medicao,
    tipo: str,
    ref_id: str | None,
    aud_id: str | None,
    conta_em: str | None,
    *,
    motivo: str | None = None,
) -> Registro:
    referencia = medicao.referencia.get(ref_id or "")
    auditoria = medicao.auditoria.get(aud_id or "")
    base = referencia or auditoria
    assert base is not None
    obs_ref = ref_id.split(":", 1)[1] if ref_id else None
    obs_aud = aud_id.split(":", 1)[1] if aud_id else None
    caixa: Sequence[float] = medicao.recortes.get(ref_id or aud_id or "") or base["bbox"]
    return {
        **_campos_lado(auditoria, "auditoria"),
        **_campos_lado(referencia, "referencia"),
        "camada": base["camada"],
        "conta_em": conta_em,
        "id": "disc-" + sha256(json.dumps([tipo, obs_ref, obs_aud]).encode()).hexdigest()[:16],
        "motivo": motivo,
        "observacao_auditoria": obs_aud,
        "observacao_referencia": obs_ref,
        "pagina": base["pagina"],
        "tile": medicao.lados.escopo_auditoria.tile_evidencia(
            base["pagina"], base["camada"], caixa
        ),
        "tipo": tipo,
    }


def _bloco_id_exato(medicao: _Medicao, pares: Sequence[tuple[str, str]]) -> Registro:
    concordantes = divergentes = sem_id = 0
    for ref_id, aud_id in pares:
        exato_ref = medicao.referencia[ref_id].get("id_inventario")
        exato_aud = medicao.auditoria[aud_id].get("id_inventario")
        if exato_ref is None and exato_aud is None:
            sem_id += 1
        elif exato_ref == exato_aud:
            concordantes += 1
        else:
            divergentes += 1
            medicao.discordancias.append(
                _discordancia(
                    medicao, "id_divergente", ref_id, aud_id, "id_exato", motivo="id_inventario"
                )
            )
    aplicaveis = concordantes + divergentes
    return {
        "aplicaveis": aplicaveis,
        "concordancia": _proporcao(concordantes, aplicaveis),
        "concordantes": concordantes,
        "divergentes": divergentes,
        "sem_id_exato": sem_id,
    }


def _caixa(valores: Sequence[Any]) -> tuple[float, float, float, float]:
    return float(valores[0]), float(valores[1]), float(valores[2]), float(valores[3])


def _falhas_triagem(indice: Registro, amostra: Registro, auditoria: Registro) -> list[Registro]:
    """Observações do auditor vistas em tile descartado (evidência ou centro só em descartados)."""
    por_id = {str(tile["id"]): tile for tile in indice["tiles"]}
    descartados = {i for i in sortear_ids(amostra) if por_id[i]["estado"] == ESTADO_DESCARTADO}
    falhas = []
    for observacao in auditoria["observacoes"]:
        x0, y0, x1, y1 = _caixa(observacao["bbox"])
        centro = ((x0 + x1) / 2, (y0 + y1) / 2)
        contem = [
            tile
            for tile in indice["tiles"]
            if (tile["pagina"], tile["camada"]) == (observacao["pagina"], observacao["camada"])
            and _dentro(*centro, _caixa(tile["bbox"]))
        ]
        tile_id = observacao["tile_evidencia"]
        if tile_id not in descartados:
            vistos = [t for t in contem if t["id"] in descartados]
            if not vistos or any(t["estado"] == ESTADO_REVISAR for t in contem):
                continue
            tile_id = str(vistos[0]["id"])
        tile = por_id[tile_id]
        falhas.append(
            {
                "camada": tile["camada"],
                "class_id": observacao["class_id"],
                "ocupacao": tile["ocupacao"],
                "observacao_id": observacao["id"],
                "pagina": tile["pagina"],
                "tile_id": tile_id,
            }
        )
    return falhas


def _amostrados(indice: Registro, amostra: Registro) -> dict[tuple[int, str], list[Caixa]]:
    """Caixas dos tiles amostrados por (página, camada); a amostra já usa a base nas páginas
    cuja camada anotada é igual à base."""
    ids = set(sortear_ids(amostra))
    caixas: dict[tuple[int, str], list[Caixa]] = defaultdict(list)
    for tile in indice["tiles"]:
        if tile["id"] in ids:
            caixas[(int(tile["pagina"]), str(tile["camada"]))].append(_caixa(tile["bbox"]))
    return dict(caixas)


def _medicao(
    referencia: Registro, auditoria: Registro, indice: Registro, amostra: Registro
) -> _Medicao:
    iguais = frozenset(
        int(pagina["pagina"])
        for pagina in indice["paginas"]
        if pagina.get("camada_anotada_igual_base")
    )
    try:
        lados = _Lados(
            escopo_referencia=montar_escopo(indice, referencia),
            escopo_auditoria=montar_escopo(indice, auditoria),
            iguais=iguais,
            amostrados=_amostrados(indice, amostra),
        )
    except ValueError as erro:
        raise AuditoriaRecusadaError(
            f"referência principal fora do índice vigente: {erro}"
        ) from None
    return _Medicao(
        referencia={f"ref:{o['id']}": o for o in referencia["observacoes"]},
        auditoria={f"aud:{o['id']}": o for o in auditoria["observacoes"]},
        lados=lados,
        discordancias=[],
    )


TIPO_POR_MOTIVO = {
    MOTIVO_CLASSE: "classe_divergente",
    MOTIVO_PAPEL: "papel_divergente",
    MOTIVO_PAPEL_ESTADO: "papel_divergente",
}


def _registrar_discordancias(medicao: _Medicao, casamento: _Casamento) -> None:
    """Discordâncias que contam na classe e o diagnóstico de estado (fora da medida)."""
    registrar = medicao.discordancias.append
    for motivo, pares in sorted(casamento.divergentes.items()):
        for ref_id, aud_id in pares:
            tipo = TIPO_POR_MOTIVO[motivo]
            registrar(_discordancia(medicao, tipo, ref_id, aud_id, "classe", motivo=motivo))
    for ref_id in casamento.so_referencia:
        registrar(_discordancia(medicao, "so_referencia", ref_id, None, "classe"))
    for aud_id in casamento.so_auditoria:
        registrar(_discordancia(medicao, "so_auditoria", None, aud_id, "classe"))
    for ref_id, aud_id in casamento.concordantes + casamento.so_estado:
        if medicao.referencia[ref_id]["estado"] != medicao.auditoria[aud_id]["estado"]:
            registrar(
                _discordancia(medicao, "estado_divergente", ref_id, aud_id, None, motivo="estado")
            )


def _registrar_lineares(medicao: _Medicao, lineares: _Lineares) -> None:
    def registrar(tipo: str, ref_id: str | None, aud_id: str | None, conta_em: str | None) -> None:
        motivo = "linear" if conta_em else "estado"
        discordancia = _discordancia(medicao, tipo, ref_id, aud_id, conta_em, motivo=motivo)
        discordancia["cobertura"] = lineares.cobertura[ref_id or aud_id or ""]
        medicao.discordancias.append(discordancia)

    for ref_id in lineares.so_referencia:
        registrar("so_referencia", ref_id, None, "classe")
    for aud_id in lineares.so_auditoria:
        registrar("so_auditoria", None, aud_id, "classe")
    for ref_id in lineares.so_estado:
        registrar("estado_divergente", ref_id, None, None)


def _bloco_classe(casamento: _Casamento, lineares: _Lineares) -> Registro:
    """Medida de classe: casamento 1:1 mais lineares por cobertura (o total fecha)."""
    por_motivo = {motivo: len(pares) for motivo, pares in sorted(casamento.divergentes.items())}
    concordantes = len(casamento.concordantes) + len(lineares.concordantes)
    divergentes = sum(por_motivo.values())
    so_ref = len(casamento.so_referencia) + len(lineares.so_referencia)
    so_aud = len(casamento.so_auditoria) + len(lineares.so_auditoria)
    total = concordantes + divergentes + so_ref + so_aud
    return {
        "concordancia": _proporcao(concordantes, total),
        "concordantes": concordantes,
        "divergentes": divergentes,
        "divergentes_por_motivo": por_motivo,
        "lineares": {
            "classes_lineares": sorted(CLASSES_LINEARES),
            "cobertura_minima": COBERTURA_MINIMA,
            "concordantes": len(lineares.concordantes),
            "so_auditoria": len(lineares.so_auditoria),
            "so_referencia": len(lineares.so_referencia),
            "tol": TOLERANCIA_LINEAR,
        },
        "so_auditoria": so_aud,
        "so_referencia": so_ref,
        "total": total,
    }


def _fora_do_denominador(originais: Mapping[str, Registro], ids: Sequence[str]) -> Registro:
    """Observações incertas sem par confiante do outro lado (informativo)."""
    observacoes = [
        {"motivo": _motivo_incerteza(originais[i]), "observacao": i.split(":", 1)[1]} for i in ids
    ]
    return {
        "observacoes": observacoes,
        "por_motivo": dict(sorted(Counter(item["motivo"] for item in observacoes).items())),
        "total": len(observacoes),
    }


def medir_concordancia(
    *,
    referencia: Registro,
    auditoria: Registro,
    amostra: Registro,
    indice: Registro,
    limiar: float = LIMIAR_PADRAO,
) -> Registro:
    """Concordância (pura e determinística) entre a referência principal e a leitura do auditor."""
    medicao = _medicao(referencia, auditoria, indice, amostra)
    itens_ref, resumo_ref = _separar(referencia["observacoes"], "ref", medicao.lados)
    itens_aud, resumo_aud = _separar(auditoria["observacoes"], "aud", medicao.lados)
    medicao.recortes.update((item["id"], item["bbox"]) for item in itens_ref + itens_aud)
    originais = {**medicao.referencia, **medicao.auditoria}
    casamento = _casar_em_etapas(
        [i for i in itens_ref if not _e_linear(i)],
        [i for i in itens_aud if not _e_linear(i)],
        originais,
    )
    lineares = _cobrir_lineares(
        [i for i in itens_ref if _e_linear(i)], [i for i in itens_aud if _e_linear(i)], originais
    )
    _registrar_discordancias(medicao, casamento)
    _registrar_lineares(medicao, lineares)
    id_exato = _bloco_id_exato(medicao, casamento.concordantes)
    classe = _bloco_classe(casamento, lineares)
    decisao, motivo = decidir(
        classe["concordantes"], classe["total"], limiar=limiar, nivel=int(amostra["nivel"])
    )
    falhas = _falhas_triagem(indice, amostra, auditoria)
    fora_ref = sorted(casamento.fora_referencia + lineares.fora_referencia)
    fora_aud = sorted(casamento.fora_auditoria + lineares.fora_auditoria)
    return {
        "classe": classe,
        "decisao": decisao,
        "fora_do_denominador": {
            "auditoria": _fora_do_denominador(medicao.auditoria, fora_aud),
            "referencia": _fora_do_denominador(medicao.referencia, fora_ref),
        },
        "discordancias": sorted(
            medicao.discordancias,
            key=lambda d: (
                d["pagina"],
                d["camada"],
                d["tipo"],
                str(d["observacao_referencia"]),
                str(d["observacao_auditoria"]),
            ),
        ),
        "falhas_triagem": falhas,
        "id_exato": id_exato,
        "limiar": limiar,
        "motivo_decisao": motivo,
        "observacoes": {"auditoria": resumo_aud, "referencia": resumo_ref},
        "pendencias": (
            [
                f"falha_triagem: {len(falhas)} observação(ões) do auditor em tile(s) descartado(s) "
                "como branco; revisar o limiar de ocupação da renderização"
            ]
            if falhas
            else []
        ),
    }


def _tiles_da_amostra(amostra: Registro, indice: Registro, referencia: Registro) -> Registro:
    por_id = {str(tile["id"]): tile for tile in indice["tiles"]}
    escopo = montar_escopo(indice, referencia)
    ids = sortear_ids(amostra)
    return {
        "a_revisar": sum(por_id[i]["estado"] == ESTADO_REVISAR for i in ids),
        "descartados": sum(por_id[i]["estado"] == ESTADO_DESCARTADO for i in ids),
        "nao_revisados_pela_referencia": [i for i in ids if i not in escopo.revisados],
        "total": len(ids),
    }


@dataclass(frozen=True)
class _Entradas:
    checkpoint: Registro
    indice: Registro
    indice_sha256: str
    referencia: Registro
    caminho_referencia: Path
    amostra: Registro
    caminho_amostra: Path
    leitura: Registro
    leitura_sha256: str


def _conferir_amostra(amostra: Registro, indice_sha: str, checkpoint: Registro) -> None:
    if amostra.get("indice_tiles_sha256") != indice_sha:
        raise AuditoriaRecusadaError("a amostra foi sorteada sobre outro índice de tiles")
    if amostra.get("sha256_pdf") != checkpoint["sha256"]:
        raise AuditoriaRecusadaError("a amostra é de outro PDF (SHA-256 divergente)")


def _conferir_historico(pasta_pdf: Path, amostra: Registro) -> None:
    bloqueio = _bloqueio(_relatorios(pasta_pdf))
    if bloqueio == ENCERRAR:
        raise AuditoriaRecusadaError(
            "uma concordância anterior já decidiu encerrar_com_pendencia; encerre o PDF"
        )
    if bloqueio == AMPLIAR and amostra["nivel"] < NIVEL_AMPLIADO:
        raise AuditoriaRecusadaError(
            "a auditoria anterior pediu amostra ampliada; rode amostrar --ampliar e audite a nova"
        )


def _ler_leitura(
    rodada_dir: Path, pdf_id: str, arquivo: Path, amostra: Registro, inv: Inventario | None
) -> tuple[Registro, str]:
    bruto = ler_json(Path(arquivo))
    if isinstance(bruto, dict) and "congelamento" in bruto:
        raise AuditoriaRecusadaError(
            "a leitura do auditor tem bloco congelamento: é uma referência congelada, não uma "
            "leitura independente da amostra"
        )
    ids = sortear_ids(amostra)
    resultado = validar_arquivo(rodada_dir, pdf_id, arquivo, inventario=inv, tiles_permitidos=ids)
    if not resultado.valida:
        raise ReferenciaInvalidaError(pdf_id, resultado.erros)
    faltando = sorted(set(ids) - set(resultado.referencia["tiles_revisados"]))
    if faltando:
        raise AuditoriaRecusadaError(
            f"a leitura do auditor não revisou todos os tiles amostrados: {', '.join(faltando)}"
        )
    return dict(resultado.referencia), resultado.entrada_sha256


def _carregar_entradas(
    rodada_dir: Path,
    pdf_id: str,
    arquivo: Path,
    *,
    versao_amostra: str | None,
    inventario: Inventario | None,
) -> _Entradas:
    checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
    validar_transicao(checkpoint, "auditado")
    referencia, caminho_referencia = carregar_referencia_vigente(rodada_dir, pdf_id)
    if referencia.get("pdf", {}).get("sha256") != checkpoint["sha256"]:
        raise AuditoriaRecusadaError("a referência principal é de outro PDF (SHA-256 divergente)")
    indice, indice_sha = _indice_vigente(rodada_dir, pdf_id, checkpoint)
    amostra, caminho_amostra = carregar_amostra(rodada_dir, pdf_id, versao_amostra)
    _conferir_amostra(amostra, indice_sha, checkpoint)
    _conferir_historico(diretorio_pdf(rodada_dir, pdf_id), amostra)
    leitura, leitura_sha = _ler_leitura(rodada_dir, pdf_id, arquivo, amostra, inventario)
    return _Entradas(
        checkpoint=checkpoint,
        indice=indice,
        indice_sha256=indice_sha,
        referencia=referencia,
        caminho_referencia=caminho_referencia,
        amostra=amostra,
        caminho_amostra=caminho_amostra,
        leitura=leitura,
        leitura_sha256=leitura_sha,
    )


def _arquivo_leitura(rodada_dir: Path, arquivo: Path) -> str:
    """Caminho relativo à rodada; fora dela, só o nome (caminhos absolutos não são gravados)."""
    caminho = Path(arquivo).resolve()
    raiz = Path(rodada_dir).resolve()
    return caminho.relative_to(raiz).as_posix() if caminho.is_relative_to(raiz) else caminho.name


def _relatorio(rodada_dir: Path, arquivo: Path, entradas: _Entradas, medida: Registro) -> Registro:
    registro_ref = entradas.checkpoint["referencia"]
    return {
        **medida,
        "amostra": {
            "arquivo": _relativo(rodada_dir, entradas.caminho_amostra),
            "nivel": entradas.amostra["nivel"],
            "sha256": hash_arquivo(entradas.caminho_amostra),
            "tiles": _tiles_da_amostra(entradas.amostra, entradas.indice, entradas.referencia),
            "versao": entradas.amostra["versao"],
        },
        "auditoria": {
            "arquivo": _arquivo_leitura(rodada_dir, arquivo),
            "modelo": entradas.leitura["revisor"]["modelo"],
            "observacoes": len(entradas.leitura["observacoes"]),
            "sha256": entradas.leitura_sha256,
            "tiles_revisados": len(entradas.leitura["tiles_revisados"]),
        },
        "indice_tiles_sha256": entradas.indice_sha256,
        "leitura_auditoria": entradas.leitura,
        "limitacoes": list(LIMITACOES),
        "pdf_id": entradas.checkpoint["pdf_id"],
        "referencia": {
            "arquivo": registro_ref["arquivo"],
            "origem": registro_ref["origem"],
            "sha256": registro_ref["sha256"],
            "versao": registro_ref["versao"],
        },
        "schema_version": ESQUEMA_CONCORDANCIA,
        "sha256_pdf": entradas.checkpoint["sha256"],
    }


def _dados_evento(relatorio: Registro) -> Registro:
    return {
        "amostra": {k: relatorio["amostra"][k] for k in ("versao", "sha256", "nivel")},
        "concordancia_classe": relatorio["classe"]["concordancia"],
        "concordancia_id_exato": relatorio["id_exato"]["concordancia"],
        "decisao": relatorio["decisao"],
        "falhas_triagem": len(relatorio["falhas_triagem"]),
        "limiar": relatorio["limiar"],
        "referencia": {k: relatorio["referencia"][k] for k in ("versao", "sha256")},
        "total_classe": relatorio["classe"]["total"],
        "versao": relatorio["versao"],
    }


def _validar_limiar(limiar: float) -> None:
    if not (math.isfinite(limiar) and 0 < limiar <= 1):
        raise AuditoriaRecusadaError(f"--limiar {limiar} fora de (0, 1]")


def concordancia(
    rodada_dir: Path,
    pdf_id: str,
    arquivo: Path,
    *,
    versao_amostra: str | None = None,
    limiar: float = LIMIAR_PADRAO,
    inventario: Inventario | None = None,
    agora: str | None = None,
) -> Registro:
    """Mede a concordância, grava ``concordancia-vNNN.json`` e, se confiável, audita o PDF."""
    _validar_limiar(limiar)
    pasta_pdf = diretorio_pdf(rodada_dir, pdf_id)
    with _trava(pasta_pdf / DIRETORIO_AUDITORIA):
        entradas = _carregar_entradas(
            rodada_dir, pdf_id, arquivo, versao_amostra=versao_amostra, inventario=inventario
        )
        medida = medir_concordancia(
            referencia=entradas.referencia,
            auditoria=entradas.leitura,
            amostra=entradas.amostra,
            indice=entradas.indice,
            limiar=limiar,
        )
        relatorio = _relatorio(rodada_dir, arquivo, entradas, medida)
        numero = _proxima(_versoes(pasta_pdf, NOME_CONCORDANCIA), "concordância")
        destino = pasta_pdf / f"concordancia-v{numero:03d}.json"
        relatorio["versao"] = destino.stem
        _criar_exclusivo(destino, json_canonico(relatorio).encode())
        avancado = False
        if relatorio["decisao"] == CONFIAVEL:
            try:
                transicionar(
                    rodada_dir,
                    pdf_id,
                    "auditado",
                    artefatos=[destino],
                    dados=_dados_evento(relatorio),
                    agora=agora,
                )
            except BaseException:
                destino.unlink(missing_ok=True)
                raise
            avancado = True
    return {
        "arquivo": _relativo(rodada_dir, destino),
        "checkpoint_avancado": avancado,
        "concordancia_classe": relatorio["classe"]["concordancia"],
        "concordancia_id_exato": relatorio["id_exato"]["concordancia"],
        "decisao": relatorio["decisao"],
        "falhas_triagem": len(relatorio["falhas_triagem"]),
        "motivo_decisao": relatorio["motivo_decisao"],
        "pdf_id": pdf_id,
        "total_classe": relatorio["classe"]["total"],
        "versao": destino.stem,
    }


# --- CLI ------------------------------------------------------------------------------------


def _versao(valor: str) -> str:
    if not VERSAO_AMOSTRA.fullmatch(valor):
        raise argparse.ArgumentTypeError(f"versão inválida: {valor} (use vNNN)")
    return valor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    amostra = sub.add_parser("amostrar", help="sorteia a amostra estratificada de tiles")
    amostra.add_argument("--rodada", type=Path, required=True)
    amostra.add_argument("--onda", type=int)
    amostra.add_argument("--pdf", action="append", default=[])
    amostra.add_argument("--fracao", type=float)
    amostra.add_argument("--minimo", type=int)
    amostra.add_argument("--semente", type=int)
    amostra.add_argument("--incluir-descartados", dest="incluir_descartados", type=float)
    amostra.add_argument(
        "--ampliar",
        action="store_true",
        help="dobra fração, mínimo e descartados da amostra auditada (após ampliar_amostra)",
    )
    medir = sub.add_parser("concordancia", help="mede a concordância e decide")
    medir.add_argument("--rodada", type=Path, required=True)
    medir.add_argument("--pdf", required=True)
    medir.add_argument("--auditoria", type=Path, required=True)
    medir.add_argument("--amostra", type=_versao)
    medir.add_argument("--limiar", type=float, default=LIMIAR_PADRAO)
    return parser


def _parametros_cli(args: argparse.Namespace) -> ParametrosAmostra:
    explicitos = {
        campo: getattr(args, campo)
        for campo in ("fracao", "minimo", "semente", "incluir_descartados")
        if getattr(args, campo) is not None
    }
    if args.ampliar and explicitos:
        raise RodadaError(
            "--ampliar usa os parâmetros da amostra auditada, dobrados; não os informe"
        )
    return ParametrosAmostra(**explicitos)


def _executar(args: argparse.Namespace) -> int:
    if args.comando == "amostrar":
        parametros = _parametros_cli(args)
        pdf_ids = selecionar_pdfs(args.rodada, onda=args.onda, pdf_ids=args.pdf)
        resultado = amostrar(args.rodada, pdf_ids, parametros=parametros, ampliar=args.ampliar)
        for item in resultado["pdfs"]:
            for falha in item["falhas"]:
                print(f"erro: {item['pdf_id']}: {falha}", file=sys.stderr)
        print(json_canonico(resultado), end="")
        return 0 if resultado["totais"]["sucesso"] == len(pdf_ids) else 1
    resumo = concordancia(
        args.rodada, args.pdf, args.auditoria, versao_amostra=args.amostra, limiar=args.limiar
    )
    if resumo["falhas_triagem"]:
        print(
            f"alerta: falha_triagem: {resumo['falhas_triagem']} observação(ões) do auditor em "
            "tile(s) descartado(s); veja falhas_triagem no relatório",
            file=sys.stderr,
        )
    print(json_canonico(resumo), end="")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _executar(args)
    except RodadaError as erro:
        erros = getattr(erro, "erros", None) or [str(erro)]
        for item in erros:
            print(f"erro: {item}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
