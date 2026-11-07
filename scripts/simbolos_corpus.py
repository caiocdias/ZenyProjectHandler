"""Corpus do benchmark de símbolos: saneamento, guarda do conjunto cego, pool e cobertura."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any, Final

from scripts.curation_round import RodadaError
from scripts.ficha_poste import carregar_ficha
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import CoberturaMetodoSimbolos

COMPONENTE_CEGO: Final = "avaliacao-cega"
LIMITE_ERRO: Final = 300

Registro = dict[str, Any]

_ESTADOS_SEM_FALHA: Final = frozenset(
    {EstadoMetodoSimbolos.CONCLUIDO, EstadoMetodoSimbolos.NAO_DETECCAO}
)


class FolhaError(Exception):
    """Falha esperada de uma folha, com mensagem já saneada."""


# --- saneamento -------------------------------------------------------------------------

# Dentro de um caminho do Windows os componentes podem ter espaço; o último pode ter espaço até
# a extensão (nome de PDF com espaços) ou termina no primeiro espaço, se não houver extensão.
_RESTO_WINDOWS = (
    r"(?:[^\\/:*?\"<>|\r\n]+[\\/])*"
    r"(?:[^\\/:*?\"<>|\r\n']*?\.[A-Za-z0-9]{1,5}\b|[^\s\\/:*?\"<>|']*)"
)
_CAMINHO_WINDOWS = re.compile(r"(?:\\\\[?.][\\/])?[A-Za-z]:[\\/]" + _RESTO_WINDOWS)
_CAMINHO_UNC = re.compile(r"\\\\[^\\/\s'\"]+(?:[\\/]" + _RESTO_WINDOWS + ")?")
_CAMINHO_POSIX = re.compile(r"(?<![\w.:])/(?:[\w.\-~]+/)+[\w.\-~]*")
_NOME_PDF = re.compile(r"[^\s'\"\\/]+\.pdf", re.IGNORECASE)


def sanear(texto: str, ocultar: Iterable[str] = ()) -> str:
    """Primeira linha do erro, sem caminho absoluto nem nome de PDF."""
    for trecho in sorted({item for item in ocultar if item}, key=len, reverse=True):
        texto = re.sub(re.escape(trecho), "<oculto>", texto, flags=re.IGNORECASE)
    linha = next((item for item in texto.splitlines() if item.strip()), "")
    for padrao in (_CAMINHO_WINDOWS, _CAMINHO_UNC, _CAMINHO_POSIX, _NOME_PDF):
        linha = padrao.sub("<caminho>", linha)
    return " ".join(linha.split())[:LIMITE_ERRO]


def falha(erro: str) -> Registro:
    return {"situacao": "falha", "erro": erro}


def falha_da_cobertura(cobertura: CoberturaMetodoSimbolos) -> str | None:
    """Motivo da falha; só ``CONCLUIDO`` e ``NAO_DETECCAO`` não são falha (lista branca)."""
    if cobertura.estado in _ESTADOS_SEM_FALHA:
        return None
    return cobertura.motivo or cobertura.estado.value


# --- guarda do conjunto cego e localização do PDF ---------------------------------------


def _componente_equivalente(parte: str) -> str:
    """Nome equivalente no Windows: sem fluxo ``:x``, sem pontos/espaços finais, sem caixa."""
    return parte.split(":", 1)[0].rstrip(". ").casefold()


def _componentes(*caminhos: str) -> set[str]:
    partes: set[str] = set()
    for caminho in caminhos:
        partes.update(_componente_equivalente(parte) for parte in re.split(r"[\\/]+", caminho))
    return partes


def caminho_cego(*caminhos: str) -> bool:
    return COMPONENTE_CEGO in _componentes(*caminhos)


_caminho_cego = caminho_cego


def recusar_rodada_cega(rodada: Path) -> None:
    """Antes de ler o rodada.json ou qualquer referência: rodada na pasta cega não se abre."""
    absoluta = str(Path(rodada).absolute())
    if caminho_cego(absoluta, os.path.normpath(absoluta)):
        raise RodadaError(f"rodada recusada: o diretório tem o componente {COMPONENTE_CEGO}")


def localizar_pdf(rodada: Path, raiz_corpus: str, caminho_relativo: str) -> Path:
    """Caminho do PDF; recusa o componente ``avaliacao-cega`` antes de qualquer acesso a disco.

    A guarda é lexical: compara os componentes do diretório da rodada, de ``raiz_corpus`` e de
    ``caminho_relativo``, e os do caminho normalizado dos três (``..`` incluído). Não pega nome
    curto 8.3, symlink nem junction para a pasta cega; a proteção real é o protocolo da curadoria.
    """
    normalizado = os.path.normpath(os.path.join(raiz_corpus, caminho_relativo))
    completo = os.path.normpath(os.path.join(str(rodada), raiz_corpus, caminho_relativo))
    if caminho_cego(str(rodada), raiz_corpus, caminho_relativo, normalizado, completo):
        raise FolhaError(f"caminho recusado: componente {COMPONENTE_CEGO}")
    return rodada / raiz_corpus / caminho_relativo


# --- pool e referência ------------------------------------------------------------------


def medir_em_paralelo(
    funcao: Callable[[Any], Registro],
    tarefas: Sequence[Any],
    efetivos: int,
    executor: type[ProcessPoolExecutor],
) -> list[Registro]:
    """Resultados na ordem das tarefas; folha sem resultado por pool quebrado vira falha."""
    if efetivos <= 1 or len(tarefas) <= 1:
        return [funcao(tarefa) for tarefa in tarefas]
    resultados: list[Registro] = []
    try:
        with executor(max_workers=efetivos) as pool:
            resultados.extend(pool.map(funcao, tarefas))
    except BrokenProcessPool:
        pass
    resultados.extend(
        falha("processo do pool encerrado antes de medir a folha")
        for _ in tarefas[len(resultados) :]
    )
    return resultados


_PDF_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def carregar_referencia(rodada: Path, pdf_id: str) -> Registro:
    """Ficha da folha, ``{"situacao": "sem_referencia"}`` ou uma falha saneada."""
    if not _PDF_ID.fullmatch(pdf_id):
        return falha("pdf_id inválido no rodada.json")
    caminho = rodada / "pdfs" / pdf_id / "ficha" / "referencia.json"
    if not caminho.is_file():
        return {"situacao": "sem_referencia"}
    try:
        ficha = carregar_ficha(caminho)
    except (ValueError, OSError) as erro:
        return falha(sanear(f"{type(erro).__name__}: {erro}", [str(rodada), rodada.as_posix()]))
    if ficha["tipo"] != "referencia":
        return falha("a ficha não é do tipo referencia")
    return {"situacao": "ok", "ficha": ficha}
