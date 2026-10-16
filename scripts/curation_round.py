"""Rodada de curadoria de simbologia: corpus, ondas, reuso de referência e checkpoints por PDF.

Uso:
    python -m scripts.curation_round init --rodada DIR --raiz examples --concorrencia N
        [--anterior DIR] [--reusar-referencias | --sem-reuso]
    python -m scripts.curation_round status --rodada DIR [--onda K] [--json]
    python -m scripts.curation_round avancar --rodada DIR --pdf ID --fase FASE
        [--artefato CAMINHO ...] [--nota TEXTO]

A rodada vive inteira no diretório indicado (normalmente em ``tmp/curadoria-simbologia/``,
fora do Git). ``rodada.json`` só é escrito por ``init`` e pelo orquestrador; cada PDF tem o
próprio ``pdfs/ORDEM-HASH12/checkpoint.json``, escrito de forma atômica e sob trava, para que
agentes e CLIs paralelos não disputem o mesmo arquivo. Caminhos gravados são relativos ao
diretório da rodada. Os demais CLIs da curadoria importam as funções públicas deste módulo.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
ESQUEMA_RODADA = "curadoria-rodada-v1"
ESQUEMA_CHECKPOINT = "curadoria-checkpoint-v1"
PACOTES_SIMBOLOGIA = "src/zeny_project_handler/adapters/analysis/symbol_packages"
CONCORRENCIA_MINIMA = 1
CONCORRENCIA_MAXIMA = 5
INDISPONIVEL = "indisponivel"
ARQUIVO_RODADA = "rodada.json"
ARQUIVO_CHECKPOINT = "checkpoint.json"
PRIMEIRA_REFERENCIA = "referencia-v001.json"
NOME_REFERENCIA = re.compile(r"referencia-v\d{3}\.json")
ESPERA_TRAVA_S = 30.0

FASES = (
    "preparado",
    "renderizado",
    "inferido",
    "referencia_congelada",
    "comparado",
    "auditado",
    "em_correcao",
    "fechado",
    "encerrado_com_pendencias",
)
FASES_TERMINAIS = frozenset({"fechado", "encerrado_com_pendencias"})
# Marcos válidos exigidos para entrar em cada fase. ``preparado`` só é atribuído por ``init``.
REQUISITOS: Mapping[str, tuple[str, ...]] = {
    "renderizado": (),
    "inferido": (),
    "referencia_congelada": ("renderizado",),
    "comparado": ("inferido", "referencia_congelada"),
    "auditado": ("renderizado", "referencia_congelada"),
    "em_correcao": ("comparado",),
    "fechado": ("comparado", "auditado"),
    "encerrado_com_pendencias": (),
}
# Marcos que deixam de valer ao entrar na fase: nova inferência, nova versão da referência ou
# correção em andamento exigem nova comparação antes de fechar; nova versão da referência exige
# também nova concordância da auditoria (medida contra a versão anterior).
INVALIDA: Mapping[str, tuple[str, ...]] = {
    "inferido": ("comparado",),
    "referencia_congelada": ("comparado", "auditado"),
    "em_correcao": ("comparado",),
}
MARCOS_PARA_FECHAR = ("renderizado", "inferido", "referencia_congelada", "comparado", "auditado")
ORIGENS_REFERENCIA_AVANCAR = frozenset({"leitura", "revisao"})

Registro = dict[str, Any]


class RodadaError(Exception):
    """Erro de uso ou de integridade da rodada; a CLI termina com código diferente de zero."""


class TransicaoInvalidaError(RodadaError):
    """Transição de fase recusada; o checkpoint permanece inalterado."""


# --- utilitários de arquivo -------------------------------------------------------------


def json_canonico(valor: Any) -> str:
    """Mesma serialização canônica do runner de benchmark (chaves ordenadas, sem NaN)."""
    texto = json.dumps(valor, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    return texto + "\n"


def _substituir(origem: Path, destino: Path) -> None:
    """``os.replace`` com novas tentativas curtas: no Windows um leitor pode segurar o destino."""
    for tentativa in range(50):
        try:
            os.replace(origem, destino)
            return
        except PermissionError:
            if tentativa == 49:
                raise
            time.sleep(0.02)


def escrever_bytes_atomico(destino: Path, conteudo: bytes) -> None:
    """Grava num temporário do mesmo diretório e troca com ``os.replace``."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    descritor, nome = tempfile.mkstemp(
        prefix=f".{destino.name}.", suffix=".tmp", dir=destino.parent
    )
    temporario = Path(nome)
    try:
        with os.fdopen(descritor, "wb") as fluxo:
            fluxo.write(conteudo)
            fluxo.flush()
            os.fsync(fluxo.fileno())
        _substituir(temporario, destino)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise


def escrever_json_atomico(destino: Path, valor: Any) -> None:
    """Serializa antes de tocar o disco; falha de serialização não deixa resíduo."""
    escrever_bytes_atomico(destino, json_canonico(valor).encode("utf-8"))


def ler_json(caminho: Path) -> Any:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RodadaError(f"arquivo não encontrado: {caminho.name}") from None
    except json.JSONDecodeError as erro:
        raise RodadaError(f"JSON inválido em {caminho.name}: {erro}") from None


def hash_arquivo(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as fluxo:
        for bloco in iter(lambda: fluxo.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def _arquivos_de(pasta: Path, *, ignorar_cache: bool = False) -> list[tuple[str, Path]]:
    itens = []
    for caminho in pasta.rglob("*"):
        relativo = caminho.relative_to(pasta).as_posix()
        if not caminho.is_file():
            continue
        if ignorar_cache and ("__pycache__" in caminho.parts or caminho.suffix == ".pyc"):
            continue
        itens.append((relativo, caminho))
    return sorted(itens)


def hash_diretorio(pasta: Path, *, ignorar_cache: bool = False) -> str:
    """Digest determinístico de (caminho relativo, SHA-256) de todos os arquivos da pasta."""
    resumo = hashlib.sha256()
    for relativo, caminho in _arquivos_de(pasta, ignorar_cache=ignorar_cache):
        resumo.update(f"{relativo}\0{hash_arquivo(caminho)}\n".encode())
    return resumo.hexdigest()


def hash_artefato(caminho: Path) -> str:
    return hash_diretorio(caminho) if caminho.is_dir() else hash_arquivo(caminho)


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _relativo(alvo: Path, base: Path) -> str:
    try:
        return Path(os.path.relpath(alvo, base)).as_posix()
    except ValueError:
        raise RodadaError(
            "a rodada e o caminho referenciado estão em unidades diferentes; "
            "use diretórios na mesma unidade"
        ) from None


@contextmanager
def _trava(arquivo: Path, espera_s: float = ESPERA_TRAVA_S) -> Iterator[None]:
    """Trava exclusiva por checkpoint (arquivo ``.lock`` criado com ``O_EXCL``)."""
    trava = arquivo.with_name(arquivo.name + ".lock")
    limite = time.monotonic() + espera_s
    while True:
        try:
            os.close(os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            if time.monotonic() >= limite:
                raise RodadaError(
                    f"checkpoint travado por outro processo: {trava.name}; "
                    "remova a trava só se nenhum CLI da rodada estiver em execução"
                ) from None
            time.sleep(0.02)
    try:
        yield
    finally:
        trava.unlink(missing_ok=True)


# --- checkpoint de código ---------------------------------------------------------------


def _sanitizar(texto: str, raiz: Path) -> str:
    linha = (texto.strip().splitlines() or ["sem detalhe"])[0]
    for marca in {str(raiz), raiz.as_posix()}:
        linha = linha.replace(marca, "<repositorio>")
    return linha[:300]


def _git_write_tree(raiz: Path, git: str) -> str:
    """Snapshot da árvore de trabalho com índice temporário; o índice real não é tocado."""

    def executar(*argumentos: str, ambiente: Mapping[str, str] | None = None) -> str:
        concluido = subprocess.run(
            [git, *argumentos],
            cwd=raiz,
            capture_output=True,
            text=True,
            check=True,
            env=None if ambiente is None else dict(ambiente),
            timeout=600,
        )
        return concluido.stdout.strip()

    indice = Path(executar("rev-parse", "--git-path", "index"))
    indice = indice if indice.is_absolute() else raiz / indice
    with tempfile.TemporaryDirectory(prefix="zeny-curadoria-indice-") as pasta:
        temporario = Path(pasta) / "index"
        if indice.is_file():
            shutil.copyfile(indice, temporario)
        ambiente = {**os.environ, "GIT_INDEX_FILE": str(temporario)}
        executar("add", "-A", ambiente=ambiente)
        return executar("write-tree", ambiente=ambiente)


def checkpoint_codigo(raiz_repositorio: Path = ROOT, *, git_executavel: str = "git") -> Registro:
    """Árvore ``git write-tree`` + digest dos pacotes; indisponibilidade vira motivo, não erro."""
    raiz = Path(raiz_repositorio).resolve()
    motivos: list[str] = []
    arvore = INDISPONIVEL
    if not raiz.is_dir():
        motivos.append("git write-tree: diretório do repositório inexistente")
    else:
        try:
            arvore = _git_write_tree(raiz, git_executavel)
        except subprocess.CalledProcessError as erro:
            motivos.append(f"git write-tree: {_sanitizar(erro.stderr or '', raiz)}")
        except (OSError, subprocess.SubprocessError) as erro:
            motivos.append(f"git write-tree: {type(erro).__name__}")
    pacotes = raiz / PACOTES_SIMBOLOGIA
    digest = INDISPONIVEL
    if pacotes.is_dir():
        digest = hash_diretorio(pacotes, ignorar_cache=True)
    else:
        motivos.append("digest de pacotes: diretório de pacotes inexistente")
    resultado: Registro = {
        "caminho_pacotes": PACOTES_SIMBOLOGIA,
        "digest_pacotes": digest,
        "git_write_tree": arvore,
    }
    if motivos:
        resultado["motivo"] = "; ".join(motivos)
    return resultado


# --- corpus e manifesto -----------------------------------------------------------------


def descobrir_pdfs(raiz: Path) -> list[Path]:
    """PDFs recursivos (inclusive ``.PDF``), ordenados pelo caminho relativo sem caixa."""
    if not raiz.is_dir():
        raise RodadaError(f"raiz do corpus inexistente: {raiz.name}")
    fontes = [p for p in raiz.rglob("*") if p.is_file() and p.suffix.casefold() == ".pdf"]

    def chave(caminho: Path) -> tuple[str, str]:
        relativo = caminho.relative_to(raiz).as_posix()
        return relativo.casefold(), relativo

    ordenadas = sorted(fontes, key=chave)
    if not ordenadas:
        raise RodadaError(f"nenhum PDF encontrado em {raiz.name}")
    return ordenadas


def _contar_paginas(caminho: Path) -> tuple[int | None, str | None]:
    try:
        with pymupdf.open(caminho) as documento:  # type: ignore[no-untyped-call]
            return int(documento.page_count), None
    except Exception as erro:  # PDF ilegível vira registro explícito, não zero páginas
        return None, f"{type(erro).__name__}: PDF não pôde ser aberto pelo PyMuPDF"


def _validar_concorrencia(concorrencia: int) -> None:
    if not CONCORRENCIA_MINIMA <= concorrencia <= CONCORRENCIA_MAXIMA:
        raise RodadaError(
            f"concorrência {concorrencia} fora do intervalo "
            f"{CONCORRENCIA_MINIMA}-{CONCORRENCIA_MAXIMA}"
        )


def _validar_destino_livre(destino: Path) -> None:
    if (destino / ARQUIVO_RODADA).exists():
        raise RodadaError(f"a rodada já existe ({ARQUIVO_RODADA} presente em {destino.name})")
    if destino.exists() and (not destino.is_dir() or any(destino.iterdir())):
        raise RodadaError(f"diretório da rodada não está vazio: {destino.name}")


def _pdf_id(ordem: int, total: int, sha256: str) -> str:
    largura = max(3, len(str(total)))
    return f"{ordem:0{largura}d}-{sha256[:12]}"


def _entradas(raiz: Path, fontes: Sequence[Path], concorrencia: int) -> list[Registro]:
    entradas = []
    for indice, fonte in enumerate(fontes):
        sha256 = hash_arquivo(fonte)
        paginas, erro = _contar_paginas(fonte)
        entradas.append(
            {
                "bytes": fonte.stat().st_size,
                "caminho_relativo": fonte.relative_to(raiz).as_posix(),
                "erro_paginas": erro,
                "estado_frente_anterior": "novo",
                "onda": indice // concorrencia + 1,
                "ordem": indice + 1,
                "paginas": paginas,
                "pdf_id": _pdf_id(indice + 1, len(fontes), sha256),
                "reuso_referencia": False,
                "sha256": sha256,
            }
        )
    return entradas


def _duplicatas(entradas: Sequence[Registro]) -> list[Registro]:
    grupos: dict[str, list[Registro]] = {}
    for entrada in entradas:
        grupos.setdefault(entrada["sha256"], []).append(entrada)
    return [
        {
            "caminhos": [item["caminho_relativo"] for item in grupo],
            "pdf_ids": [item["pdf_id"] for item in grupo],
            "sha256": sha256,
        }
        for sha256, grupo in grupos.items()
        if len(grupo) > 1
    ]


def _ondas(entradas: Sequence[Registro]) -> list[Registro]:
    ondas: dict[int, list[str]] = {}
    for entrada in entradas:
        ondas.setdefault(entrada["onda"], []).append(entrada["pdf_id"])
    return [{"numero": numero, "pdfs": ids} for numero, ids in sorted(ondas.items())]


# --- rodada anterior e reuso ------------------------------------------------------------


def _marcar_estado(entradas: Sequence[Registro], anterior: Registro) -> None:
    por_caminho = {item["caminho_relativo"]: item for item in anterior["pdfs"]}
    for entrada in entradas:
        previo = por_caminho.get(entrada["caminho_relativo"])
        if previo is None:
            entrada["estado_frente_anterior"] = "novo"
        elif previo["sha256"] == entrada["sha256"]:
            entrada["estado_frente_anterior"] = "inalterado"
        else:
            entrada["estado_frente_anterior"] = "modificado"


def _plano_reuso(entrada: Registro, previo: Registro, pasta_anterior: Path) -> Registro | None:
    """Lê e confere a referência congelada anterior; hash divergente aborta o ``init``."""
    checkpoint = carregar_checkpoint(pasta_anterior, previo["pdf_id"])
    referencia = checkpoint.get("referencia")
    if not referencia:
        return None
    caminho = entrada["caminho_relativo"]
    if checkpoint["sha256"] != entrada["sha256"]:
        raise RodadaError(f"checkpoint anterior de {caminho} registra outro SHA-256 do PDF")
    arquivo = (pasta_anterior / referencia["arquivo"]).resolve()
    if not arquivo.is_relative_to(pasta_anterior) or not arquivo.is_file():
        raise RodadaError(
            f"referência congelada de {caminho} na rodada anterior não existe: "
            f"{referencia['arquivo']}"
        )
    conteudo = arquivo.read_bytes()
    encontrado = hashlib.sha256(conteudo).hexdigest()
    if encontrado != referencia["sha256"]:
        raise RodadaError(
            f"SHA-256 da referência congelada de {caminho} na rodada anterior diverge do "
            f"checkpoint (registrado {referencia['sha256'][:12]}, encontrado {encontrado[:12]}); "
            "corrija a rodada anterior ou use --sem-reuso"
        )
    return {
        "conteudo": conteudo,
        "fase_anterior": checkpoint["fase"],
        "origem_anterior": referencia["origem"],
        "pdf_id": previo["pdf_id"],
        "arquivo": referencia["arquivo"],
        "sha256": encontrado,
    }


def _planejar_reusos(
    entradas: Sequence[Registro], anterior: Registro, pasta_anterior: Path
) -> dict[str, Registro]:
    por_caminho = {item["caminho_relativo"]: item for item in anterior["pdfs"]}
    planos: dict[str, Registro] = {}
    for entrada in entradas:
        if entrada["estado_frente_anterior"] != "inalterado":
            continue
        plano = _plano_reuso(entrada, por_caminho[entrada["caminho_relativo"]], pasta_anterior)
        if plano is not None:
            entrada["reuso_referencia"] = True
            planos[entrada["pdf_id"]] = plano
    return planos


# --- checkpoints ------------------------------------------------------------------------


def _evento(
    de: str | None,
    para: str,
    horario: str,
    artefatos: Sequence[Registro] = (),
    nota: str | None = None,
    dados: Mapping[str, Any] | None = None,
) -> Registro:
    return {
        "artefatos": list(artefatos),
        "dados": dict(dados or {}),
        "de": de,
        "horario": horario,
        "nota": nota,
        "para": para,
    }


def _checkpoint_inicial(entrada: Registro, horario: str) -> Registro:
    return {
        "caminho_relativo": entrada["caminho_relativo"],
        "fase": "preparado",
        "historico": [_evento(None, "preparado", horario)],
        "marcos": {"preparado": {"artefatos": [], "horario": horario}},
        "onda": entrada["onda"],
        "ordem": entrada["ordem"],
        "pdf_id": entrada["pdf_id"],
        "referencia": None,
        "schema_version": ESQUEMA_CHECKPOINT,
        "sha256": entrada["sha256"],
    }


def _aplicar_reuso(
    checkpoint: Registro, plano: Registro, caminho_anterior: str, horario: str
) -> Registro:
    arquivo = f"pdfs/{checkpoint['pdf_id']}/referencia/{PRIMEIRA_REFERENCIA}"
    registro = {
        "bytes": len(plano["conteudo"]),
        "caminho": arquivo,
        "sha256": plano["sha256"],
        "tipo": "arquivo",
    }
    checkpoint["referencia"] = {
        "arquivo": arquivo,
        "horario": horario,
        "origem": "reuso",
        "rodada_anterior": {
            "arquivo": plano["arquivo"],
            "caminho": caminho_anterior,
            "fase_final": plano["fase_anterior"],
            "origem": plano["origem_anterior"],
            "pdf_id": plano["pdf_id"],
            "sha256": plano["sha256"],
        },
        "sha256": plano["sha256"],
        "versao": PRIMEIRA_REFERENCIA,
    }
    checkpoint["marcos"]["referencia_congelada"] = {"artefatos": [registro], "horario": horario}
    checkpoint["historico"].append(
        _evento(
            "preparado",
            "referencia_congelada",
            horario,
            [registro],
            "referência congelada reutilizada da rodada anterior (mesmo SHA-256)",
            {"origem": "reuso"},
        )
    )
    checkpoint["fase"] = "referencia_congelada"
    return checkpoint


def _materializar(
    destino: Path,
    manifesto: Registro,
    entradas: Sequence[Registro],
    reusos: Mapping[str, Registro],
) -> None:
    """Monta a rodada num diretório irmão temporário e só então a publica no destino."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    preparo = Path(tempfile.mkdtemp(prefix=f".{destino.name}.init-", dir=destino.parent))
    horario = manifesto["criada_em"]
    anterior = (manifesto.get("rodada_anterior") or {}).get("caminho", "")
    try:
        for entrada in entradas:
            checkpoint = _checkpoint_inicial(entrada, horario)
            plano = reusos.get(entrada["pdf_id"])
            pasta = preparo / "pdfs" / entrada["pdf_id"]
            if plano is not None:
                _aplicar_reuso(checkpoint, plano, anterior, horario)
                copia = preparo / checkpoint["referencia"]["arquivo"]
                escrever_bytes_atomico(copia, plano["conteudo"])
                if hash_arquivo(copia) != plano["sha256"]:
                    raise RodadaError(
                        f"cópia da referência de {entrada['caminho_relativo']} diverge"
                    )
            escrever_json_atomico(pasta / ARQUIVO_CHECKPOINT, checkpoint)
        escrever_json_atomico(preparo / ARQUIVO_RODADA, manifesto)
        if destino.exists():
            destino.rmdir()
        os.rename(preparo, destino)
    except BaseException:
        shutil.rmtree(preparo, ignore_errors=True)
        raise


def iniciar_rodada(
    rodada_dir: Path,
    raiz: Path,
    *,
    concorrencia: int,
    anterior: Path | None = None,
    reusar_referencias: bool = True,
    raiz_repositorio: Path = ROOT,
    agora: str | None = None,
) -> Registro:
    """Cria ``rodada.json`` e um checkpoint por PDF; nada é gravado se alguma conferência falhar."""
    _validar_concorrencia(concorrencia)
    destino = Path(rodada_dir).resolve()
    _validar_destino_livre(destino)
    raiz_corpus = Path(raiz).resolve()
    entradas = _entradas(raiz_corpus, descobrir_pdfs(raiz_corpus), concorrencia)
    previa: Registro | None = None
    reusos: dict[str, Registro] = {}
    if anterior is not None:
        pasta_anterior = Path(anterior).resolve()
        if pasta_anterior == destino:
            raise RodadaError("a rodada anterior não pode ser a própria rodada")
        dados_anteriores = carregar_rodada(pasta_anterior)
        _marcar_estado(entradas, dados_anteriores)
        if reusar_referencias:
            reusos = _planejar_reusos(entradas, dados_anteriores, pasta_anterior)
        previa = {
            "caminho": _relativo(pasta_anterior, destino),
            "checkpoint_codigo": dados_anteriores["checkpoint_codigo"],
            "criada_em": dados_anteriores["criada_em"],
        }
    duplicatas = _duplicatas(entradas)
    ondas = _ondas(entradas)
    manifesto: Registro = {
        "checkpoint_codigo": checkpoint_codigo(raiz_repositorio),
        "concorrencia": concorrencia,
        "criada_em": agora or _agora(),
        "duplicatas": duplicatas,
        "ondas": ondas,
        "pdfs": entradas,
        "raiz_corpus": _relativo(raiz_corpus, destino),
        "reuso_referencias": reusar_referencias,
        "rodada_anterior": previa,
        "schema_version": ESQUEMA_RODADA,
        "totais": {
            "grupos_duplicados": len(duplicatas),
            "ondas": len(ondas),
            "pdfs_em_duplicata": sum(len(grupo["caminhos"]) for grupo in duplicatas),
            "pdfs": len(entradas),
            "por_estado": dict(
                sorted(Counter(e["estado_frente_anterior"] for e in entradas).items())
            ),
            "referencias_reutilizadas": len(reusos),
        },
    }
    _materializar(destino, manifesto, entradas, reusos)
    return manifesto


# --- leitura da rodada ------------------------------------------------------------------


def carregar_rodada(rodada_dir: Path) -> Registro:
    pasta = Path(rodada_dir)
    if not (pasta / ARQUIVO_RODADA).is_file():
        raise RodadaError(f"{ARQUIVO_RODADA} não encontrado em {pasta.name}")
    dados = ler_json(pasta / ARQUIVO_RODADA)
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_RODADA:
        raise RodadaError(f"{ARQUIVO_RODADA} com esquema desconhecido em {pasta.name}")
    return dados


def _entrada_pdf(rodada: Registro, pdf_id: str) -> Registro:
    for entrada in rodada["pdfs"]:
        if entrada["pdf_id"] == pdf_id:
            return dict(entrada)
    raise RodadaError(f"PDF desconhecido na rodada: {pdf_id}")


def diretorio_pdf(rodada_dir: Path, pdf_id: str) -> Path:
    """Diretório ``pdfs/ID`` de um PDF existente na rodada (ID validado contra o manifesto)."""
    _entrada_pdf(carregar_rodada(rodada_dir), pdf_id)
    return Path(rodada_dir).resolve() / "pdfs" / pdf_id


def raiz_corpus(rodada_dir: Path) -> Path:
    pasta = Path(rodada_dir).resolve()
    relativo = str(carregar_rodada(pasta)["raiz_corpus"])
    return (pasta / relativo).resolve()


def caminho_pdf_fonte(rodada_dir: Path, pdf_id: str) -> Path:
    """Caminho absoluto do PDF original no corpus (resolvido, nunca gravado)."""
    entrada = _entrada_pdf(carregar_rodada(rodada_dir), pdf_id)
    relativo = str(entrada["caminho_relativo"])
    return (raiz_corpus(rodada_dir) / relativo).resolve()


def pdfs_da_onda(rodada: Registro, numero: int) -> list[str]:
    for onda in rodada["ondas"]:
        if onda["numero"] == numero:
            return list(onda["pdfs"])
    raise RodadaError(f"onda inexistente na rodada: {numero}")


def selecionar_pdfs(
    rodada_dir: Path, *, onda: int | None = None, pdf_ids: Sequence[str] = ()
) -> list[str]:
    """Seleção ``(--onda K | --pdf ID ...)`` comum aos CLIs da curadoria."""
    if (onda is None) == (not pdf_ids):
        raise RodadaError("informe exatamente uma seleção: --onda K ou --pdf ID")
    rodada = carregar_rodada(rodada_dir)
    if onda is not None:
        return pdfs_da_onda(rodada, onda)
    selecionados: list[str] = []
    for pdf_id in pdf_ids:
        _entrada_pdf(rodada, pdf_id)
        if pdf_id not in selecionados:
            selecionados.append(pdf_id)
    return selecionados


def _validar_checkpoint(dados: Any, pdf_id: str) -> Registro:
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_CHECKPOINT:
        raise RodadaError(f"checkpoint com esquema desconhecido: {pdf_id}")
    if dados.get("pdf_id") != pdf_id or dados.get("fase") not in FASES:
        raise RodadaError(f"checkpoint inconsistente: {pdf_id}")
    if not isinstance(dados.get("marcos"), dict) or not isinstance(dados.get("historico"), list):
        raise RodadaError(f"checkpoint sem marcos ou histórico: {pdf_id}")
    return dados


def carregar_checkpoint(rodada_dir: Path, pdf_id: str) -> Registro:
    arquivo = diretorio_pdf(rodada_dir, pdf_id) / ARQUIVO_CHECKPOINT
    return _validar_checkpoint(ler_json(arquivo), pdf_id)


# --- máquina de fases -------------------------------------------------------------------


def validar_transicao(checkpoint: Registro, fase: str, *, nota: str | None = None) -> None:
    """Recusa com ``TransicaoInvalidaError`` toda transição fora das regras de ``REQUISITOS``."""
    atual = checkpoint["fase"]
    pdf_id = checkpoint["pdf_id"]
    prefixo = f"transição {atual} -> {fase} recusada para {pdf_id}"
    if fase not in FASES:
        raise TransicaoInvalidaError(f"{prefixo}: fase desconhecida (válidas: {', '.join(FASES)})")
    if atual in FASES_TERMINAIS:
        raise TransicaoInvalidaError(f"{prefixo}: {atual} é fase terminal")
    if fase == "preparado":
        raise TransicaoInvalidaError(f"{prefixo}: preparado só é atribuído por init")
    marcos = checkpoint["marcos"]
    faltando = [requisito for requisito in REQUISITOS[fase] if requisito not in marcos]
    if faltando:
        raise TransicaoInvalidaError(f"{prefixo}: faltam os marcos {', '.join(faltando)}")
    if fase == "renderizado" and {"renderizado", "referencia_congelada"} <= marcos.keys():
        raise TransicaoInvalidaError(
            f"{prefixo}: renderizado de novo depois de congelar a referência invalidaria os "
            "tiles citados por ela; inicie outra rodada"
        )
    if fase == "encerrado_com_pendencias" and not (nota or "").strip():
        raise TransicaoInvalidaError(
            f"{prefixo}: encerrado_com_pendencias exige --nota com a pendência"
        )


def registrar_artefato(rodada_dir: Path, caminho: Path) -> Registro:
    """Hash e caminho relativo à rodada de um arquivo ou diretório dentro dela."""
    raiz = Path(rodada_dir).resolve()
    alvo = Path(caminho).resolve()
    if not alvo.is_relative_to(raiz):
        raise RodadaError(f"artefato fora da rodada: {Path(caminho).name}")
    relativo = alvo.relative_to(raiz).as_posix()
    if not alvo.exists():
        raise RodadaError(f"artefato não existe: {relativo}")
    if alvo.is_dir():
        arquivos = _arquivos_de(alvo)
        return {
            "arquivos": len(arquivos),
            "bytes": sum(item.stat().st_size for _, item in arquivos),
            "caminho": relativo,
            "sha256": hash_diretorio(alvo),
            "tipo": "diretorio",
        }
    return {
        "bytes": alvo.stat().st_size,
        "caminho": relativo,
        "sha256": hash_arquivo(alvo),
        "tipo": "arquivo",
    }


def _referencia_da_transicao(
    checkpoint: Registro, registros: Sequence[Registro], origem: str, horario: str
) -> Registro:
    pdf_id = checkpoint["pdf_id"]
    if origem not in ORIGENS_REFERENCIA_AVANCAR:
        raise TransicaoInvalidaError(f"origem de referência inválida para {pdf_id}: {origem}")
    if len(registros) != 1 or registros[0]["tipo"] != "arquivo":
        raise TransicaoInvalidaError(
            f"referência congelada de {pdf_id} exige exatamente um arquivo como artefato"
        )
    registro = registros[0]
    caminho = Path(registro["caminho"])
    esperado = Path("pdfs", pdf_id, "referencia")
    if caminho.parent != esperado or not NOME_REFERENCIA.fullmatch(caminho.name):
        raise TransicaoInvalidaError(
            f"referência congelada de {pdf_id} deve estar em "
            f"{esperado.as_posix()}/referencia-vNNN.json"
        )
    return {
        "arquivo": registro["caminho"],
        "horario": horario,
        "origem": origem,
        "sha256": registro["sha256"],
        "versao": caminho.name,
    }


def _aplicar_transicao(
    checkpoint: Registro, fase: str, evento: Registro, referencia: Registro | None
) -> Registro:
    novo = json.loads(json.dumps(checkpoint))
    for invalidado in INVALIDA.get(fase, ()):
        novo["marcos"].pop(invalidado, None)
    novo["marcos"][fase] = {"artefatos": evento["artefatos"], "horario": evento["horario"]}
    if referencia is not None:
        novo["referencia"] = referencia
    novo["historico"].append(evento)
    novo["fase"] = fase
    return dict(novo)


def transicionar(
    rodada_dir: Path,
    pdf_id: str,
    fase: str,
    *,
    artefatos: Iterable[Path] = (),
    nota: str | None = None,
    dados: Mapping[str, Any] | None = None,
    origem_referencia: str = "leitura",
    agora: str | None = None,
) -> Registro:
    """Valida e aplica uma transição, gravando hash dos artefatos e evento com horário.

    Qualquer recusa ocorre antes da escrita, e o checkpoint permanece byte a byte igual.
    """
    raiz = Path(rodada_dir).resolve()
    arquivo = diretorio_pdf(raiz, pdf_id) / ARQUIVO_CHECKPOINT
    with _trava(arquivo):
        checkpoint = _validar_checkpoint(ler_json(arquivo), pdf_id)
        validar_transicao(checkpoint, fase, nota=nota)
        registros = [registrar_artefato(raiz, Path(item)) for item in artefatos]
        horario = agora or _agora()
        referencia = None
        if fase == "referencia_congelada":
            referencia = _referencia_da_transicao(checkpoint, registros, origem_referencia, horario)
        evento = _evento(checkpoint["fase"], fase, horario, registros, nota, dados)
        novo = _aplicar_transicao(checkpoint, fase, evento, referencia)
        escrever_json_atomico(arquivo, novo)
    return novo


# --- status -----------------------------------------------------------------------------


def _pendencias(checkpoint: Registro) -> list[str]:
    if checkpoint["fase"] == "fechado":
        return []
    if checkpoint["fase"] == "encerrado_com_pendencias":
        return [str(checkpoint["historico"][-1].get("nota") or "pendência sem nota")]
    return [marco for marco in MARCOS_PARA_FECHAR if marco not in checkpoint["marcos"]]


def resumo_status(rodada_dir: Path, *, onda: int | None = None) -> list[Registro]:
    rodada = carregar_rodada(rodada_dir)
    ids = pdfs_da_onda(rodada, onda) if onda is not None else [e["pdf_id"] for e in rodada["pdfs"]]
    linhas = []
    for pdf_id in ids:
        entrada = _entrada_pdf(rodada, pdf_id)
        checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
        referencia = checkpoint.get("referencia") or {}
        linhas.append(
            {
                "caminho_relativo": entrada["caminho_relativo"],
                "estado_frente_anterior": entrada["estado_frente_anterior"],
                "fase": checkpoint["fase"],
                "onda": entrada["onda"],
                "pdf_id": pdf_id,
                "pendencias": _pendencias(checkpoint),
                "referencia": referencia.get("origem"),
            }
        )
    return linhas


def _tabela(linhas: Sequence[Registro]) -> str:
    cabecalho = ("pdf_id", "onda", "fase", "estado", "referencia", "pendencias")
    corpo = [
        (
            linha["pdf_id"],
            str(linha["onda"]),
            linha["fase"],
            linha["estado_frente_anterior"],
            linha["referencia"] or "-",
            ", ".join(linha["pendencias"]) or "-",
        )
        for linha in linhas
    ]
    larguras = [max(len(item[i]) for item in [cabecalho, *corpo]) for i in range(len(cabecalho))]
    formatar = "  ".join(f"{{:<{largura}}}" for largura in larguras)
    return "\n".join(formatar.format(*item).rstrip() for item in [cabecalho, *corpo])


def _contagem_por_fase(linhas: Sequence[Registro]) -> dict[str, int]:
    contagem = Counter(linha["fase"] for linha in linhas)
    return {fase: contagem.get(fase, 0) for fase in FASES}


# --- CLI --------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    init = sub.add_parser("init", help="descobre o corpus e cria a rodada")
    init.add_argument("--rodada", type=Path, required=True)
    init.add_argument("--raiz", type=Path, required=True)
    init.add_argument("--concorrencia", type=int, required=True)
    init.add_argument("--anterior", type=Path)
    reuso = init.add_mutually_exclusive_group()
    reuso.add_argument("--reusar-referencias", dest="reusar", action="store_true", default=True)
    reuso.add_argument("--sem-reuso", dest="reusar", action="store_false")
    status = sub.add_parser("status", help="fases e pendências dos PDFs")
    status.add_argument("--rodada", type=Path, required=True)
    status.add_argument("--onda", type=int)
    status.add_argument("--json", action="store_true")
    avancar = sub.add_parser("avancar", help="transição validada de fase de um PDF")
    avancar.add_argument("--rodada", type=Path, required=True)
    avancar.add_argument("--pdf", required=True)
    avancar.add_argument("--fase", required=True, choices=FASES)
    avancar.add_argument("--artefato", type=Path, action="append", default=[])
    avancar.add_argument("--nota")
    return parser


def _executar(args: argparse.Namespace) -> None:
    if args.comando == "init":
        manifesto = iniciar_rodada(
            args.rodada,
            args.raiz,
            concorrencia=args.concorrencia,
            anterior=args.anterior,
            reusar_referencias=args.reusar,
        )
        print(json.dumps(manifesto["totais"], ensure_ascii=False, sort_keys=True))
    elif args.comando == "status":
        linhas = resumo_status(args.rodada, onda=args.onda)
        if args.json:
            print(json_canonico({"pdfs": linhas, "por_fase": _contagem_por_fase(linhas)}), end="")
        else:
            contagem = _contagem_por_fase(linhas)
            print(_tabela(linhas))
            print("por fase: " + ", ".join(f"{f}={n}" for f, n in contagem.items() if n))
    else:
        checkpoint = transicionar(
            args.rodada, args.pdf, args.fase, artefatos=args.artefato, nota=args.nota
        )
        print(f"{checkpoint['pdf_id']}: {checkpoint['fase']}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _executar(args)
    except RodadaError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
