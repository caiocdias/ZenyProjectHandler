"""Inferência congelada dos PDFs de uma onda da curadoria, em processos paralelos.

Uso:
    python -m scripts.curation_infer --rodada DIR (--onda K | --pdf ID ...) [--jobs N]
        [--metodos METODO ...] [--pipeline] [--native-only]

Cada PDF roda num subprocesso ``benchmark_symbols examples --root RAIZ --pdf ARQUIVO`` (sem
cópia para uma pasta isolada; o ``document_id`` continua ``example:`` + caminho relativo à
raiz do corpus) com todos os métodos opcionais por padrão e, com ``--pipeline``, também
``benchmark_network_pdf``. No máximo N PDFs são inferidos ao mesmo tempo (padrão 3, máximo 5);
as etapas de um mesmo PDF rodam em série. Cada execução grava uma versão nova
``pdfs/ID/inferencia-vNNN/`` (nunca sobrescrita) com ``execucao.json`` (checkpoint de código,
comandos, durações, códigos de saída, pico de memória Python do runner e falhas). A falha de um
PDF não interrompe os demais; só em sucesso (total ou parcial) o checkpoint do PDF avança para
``inferido``.

Sucesso parcial (``sucesso_parcial``): o runner de símbolos saiu com código diferente de zero,
mas gravou ``predictions.json`` e ``manifest.json`` válidos, toda falha do manifesto é de um
método (``method_id``) e também aparece como ``status: failed`` em ``executions`` das
predições, e ao menos um método executou. Os demais métodos ficam medidos; as falhas vão para
``falhas_metodos`` ([{method_id, pagina, motivo}]) no resumo, no ``execucao.json`` e nos dados
do evento ``inferido``, e o comparador as trata como falha, nunca como zero. Qualquer outro
código diferente de zero continua sendo falha do PDF.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Protocol

from scripts.curation_round import (
    ROOT,
    RodadaError,
    caminho_pdf_fonte,
    carregar_checkpoint,
    carregar_rodada,
    checkpoint_codigo,
    diretorio_pdf,
    escrever_json_atomico,
    hash_arquivo,
    json_canonico,
    raiz_corpus,
    selecionar_pdfs,
    transicionar,
    validar_transicao,
)

ESQUEMA_EXECUCAO = "curadoria-inferencia-v1"
JOBS_PADRAO = 3
JOBS_MAXIMO = 5
# Métodos opcionais do runner; o método vetorial legado sempre roda. OCR fica fora do padrão.
METODOS = ("transformers", "guys", "packages", "raster", "structural", "legend")
PREFIXO_VERSAO = "inferencia-v"
NOME_VERSAO = re.compile(r"inferencia-v(\d{3,})")
ARQUIVO_EXECUCAO = "execucao.json"
PYTHON_REGISTRADO = "python"
# O pico nativo do subprocesso não é medido: no Windows o python.exe do venv é um lançador que
# cria o interpretador real fora do alcance de um Job Object. Fica o pico do próprio runner.
ESCOPO_MEMORIA = (
    "maior memory.python_peak_bytes do manifest.json do runner (tracemalloc por documento); "
    "exclui alocações nativas do MuPDF e RSS"
)

Registro = dict[str, Any]


@dataclass(frozen=True)
class ResultadoComando:
    codigo_saida: int


class Executor(Protocol):
    """Executa um comando com saída padrão e de erro no ``log``; injetável nos testes."""

    def __call__(self, comando: Sequence[str], *, cwd: Path, log: Path) -> ResultadoComando: ...


# --- execução de processos --------------------------------------------------------------


def executar_subprocesso(comando: Sequence[str], *, cwd: Path, log: Path) -> ResultadoComando:
    """Executor padrão: subprocesso com saídas padrão e de erro gravadas no ``log``."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with (
        log.open("wb") as saida,
        subprocess.Popen(
            list(comando), cwd=cwd, stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.STDOUT
        ) as processo,
    ):
        try:
            codigo = processo.wait()
        except BaseException:
            processo.kill()
            raise
    return ResultadoComando(codigo_saida=codigo)


# --- comandos e versões -----------------------------------------------------------------


def comandos_inferencia(
    raiz: Path,
    fonte: Path,
    versao_dir: Path,
    *,
    metodos: Sequence[str],
    pipeline: bool,
    native_only: bool,
    python: str = sys.executable,
) -> list[tuple[str, list[str]]]:
    """Etapas ``(nome, comando)`` de inferência de um PDF, na ordem de execução."""
    desconhecidos = sorted(set(metodos) - set(METODOS))
    if desconhecidos:
        raise RodadaError(f"métodos desconhecidos: {', '.join(desconhecidos)}")
    simbolos = [
        python,
        "-m",
        "scripts.benchmark_symbols",
        "examples",
        "--root",
        str(raiz),
        "--pdf",
        str(fonte),
        "--output",
        str(versao_dir / "simbolos"),
        *(f"--include-{metodo}" for metodo in METODOS if metodo in metodos),
    ]
    etapas = [("simbolos", simbolos)]
    if pipeline:
        rede = [
            python,
            "-m",
            "scripts.benchmark_network_pdf",
            str(fonte),
            "--output",
            str(versao_dir / "pipeline.json"),
            *(["--native-only"] if native_only else []),
        ]
        etapas.append(("pipeline", rede))
    return etapas


def reservar_versao(pdf_dir: Path) -> Path:
    """Cria ``inferencia-vNNN`` seguinte à maior existente; ``mkdir`` exclusivo evita reuso."""
    numeros = [
        int(achado.group(1))
        for item in pdf_dir.iterdir()
        if (achado := NOME_VERSAO.fullmatch(item.name))
    ]
    numero = max(numeros, default=0) + 1
    while True:
        candidato = pdf_dir / f"{PREFIXO_VERSAO}{numero:03d}"
        try:
            candidato.mkdir()
        except FileExistsError:
            numero += 1
            continue
        return candidato


def _registrado(argumento: str, rodada_dir: Path, python: str) -> str:
    """Forma gravada de um argumento: sem executável local e com caminhos relativos à rodada."""
    if argumento == python:
        return PYTHON_REGISTRADO
    if not Path(argumento).is_absolute():
        return argumento
    try:
        return Path(os.path.relpath(argumento, rodada_dir)).as_posix()
    except ValueError:
        return Path(argumento).name


# --- inferência de um PDF ---------------------------------------------------------------


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Contexto:
    rodada_dir: Path
    raiz: Path
    jobs: int
    metodos: tuple[str, ...]
    pipeline: bool
    native_only: bool
    executor: Executor
    cwd: Path
    codigo: Registro
    agora: Callable[[], str]
    python: str = sys.executable
    entradas: dict[str, Registro] = field(default_factory=dict)


def _falhas_das_saidas(nome: str, versao_dir: Path, document_id: str, sha256: str) -> list[str]:
    if nome == "pipeline":
        if not (versao_dir / "pipeline.json").is_file():
            return ["pipeline: pipeline.json não foi gerado"]
        return []
    simbolos = versao_dir / "simbolos"
    ausentes = [n for n in ("predictions.json", "manifest.json") if not (simbolos / n).is_file()]
    if ausentes:
        return [f"simbolos: {', '.join(ausentes)} não foi gerado"]
    try:
        predicoes = json.loads((simbolos / "predictions.json").read_text(encoding="utf-8"))
        documentos = [(item["id"], item["sha256"]) for item in predicoes["documents"]]
    except (OSError, ValueError, KeyError, TypeError) as erro:
        return [f"simbolos: predictions.json ilegível ({type(erro).__name__})"]
    if documentos != [(document_id, sha256)]:
        return [
            f"simbolos: predictions.json deveria conter só {document_id} com o SHA-256 do "
            f"checkpoint; encontrado {documentos}"
        ]
    return []


def _ler_json(arquivo: Path) -> Any:
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _falhas_do_manifesto(simbolos: Path, document_id: str) -> list[Registro]:
    """Falhas por método do manifesto; ``RodadaError`` se alguma não for de um método."""
    try:
        documentos = _ler_json(simbolos / "manifest.json")["documents"]
        brutas = [(d["id"], falha) for d in documentos for falha in d.get("failures") or []]
    except (OSError, ValueError, KeyError, TypeError) as erro:
        raise RodadaError(f"manifest.json ilegível ({type(erro).__name__})") from erro
    falhas: list[Registro] = []
    for documento, falha in brutas:
        metodo = falha.get("method_id") if isinstance(falha, dict) else None
        if documento != document_id or not isinstance(metodo, str) or not metodo:
            raise RodadaError(f"falha do runner não atribuída a um método: {falha}")
        falhas.append(
            {"method_id": metodo, "motivo": falha.get("reason"), "pagina": falha.get("page")}
        )
    if not falhas:
        raise RodadaError("manifest.json não registra falha de método")
    return falhas


def _conferir_execucoes(simbolos: Path, document_id: str, falhas: list[Registro]) -> None:
    """Exige um método executado e cada falha marcada em ``executions`` para o comparador."""
    try:
        execucoes = [
            (item["method_id"], item.get("page"), item["status"])
            for item in _ler_json(simbolos / "predictions.json").get("executions") or []
            if item.get("document_id") == document_id
        ]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as erro:
        raise RodadaError(
            f"executions ilegível em predictions.json ({type(erro).__name__})"
        ) from erro
    if not any(status == "executed" for _, _, status in execucoes):
        raise RodadaError("nenhum método executou")
    for falha in falhas:
        if (falha["method_id"], falha["pagina"], "failed") not in execucoes:
            raise RodadaError(
                f"falha de {falha['method_id']} (página {falha['pagina']}) ausente de "
                "executions em predictions.json"
            )


def _falhas_parciais(versao_dir: Path, registro: Registro) -> list[Registro]:
    """Falhas de método de um runner com código não zero; ``RodadaError`` se o PDF falhou."""
    saidas = _falhas_das_saidas("simbolos", versao_dir, registro["document_id"], registro["sha256"])
    if saidas:
        raise RodadaError("; ".join(saidas))
    simbolos = versao_dir / "simbolos"
    falhas = _falhas_do_manifesto(simbolos, registro["document_id"])
    _conferir_execucoes(simbolos, registro["document_id"], falhas)
    return falhas


def _memoria_python(simbolos: Path) -> Registro:
    """Pico de alocações Python registrado pelo runner, quando o manifesto o traz."""
    try:
        manifesto = json.loads((simbolos / "manifest.json").read_text(encoding="utf-8"))
        picos = [
            int(documento["memory"]["python_peak_bytes"]) for documento in manifesto["documents"]
        ]
    except (OSError, ValueError, KeyError, TypeError):
        picos = []
    return {
        "escopo_memoria": ESCOPO_MEMORIA,
        "memoria_python_pico_bytes": max(picos) if picos else None,
    }


def _executar_etapas(
    contexto: Contexto, fonte: Path, versao_dir: Path, registro: Registro
) -> list[str]:
    etapas = comandos_inferencia(
        contexto.raiz,
        fonte,
        versao_dir,
        metodos=contexto.metodos,
        pipeline=contexto.pipeline,
        native_only=contexto.native_only,
        python=contexto.python,
    )
    for nome, comando in etapas:
        log = versao_dir / f"{nome}.log"
        inicio = perf_counter()
        resultado = contexto.executor(comando, cwd=contexto.cwd, log=log)
        registro["etapas"].append(
            {
                "codigo_saida": resultado.codigo_saida,
                "comando": [_registrado(a, contexto.rodada_dir, contexto.python) for a in comando],
                "duracao_s": round(perf_counter() - inicio, 3),
                "log": log.name,
                "nome": nome,
            }
        )
        if resultado.codigo_saida != 0:
            erro = f"{nome}: terminou com código {resultado.codigo_saida} (ver {log.name})"
            if nome != "simbolos":
                return [erro]
            try:
                registro["falhas_metodos"] = _falhas_parciais(versao_dir, registro)
            except RodadaError as motivo:
                return [f"{erro}; sem sucesso parcial: {motivo}"]
        else:
            falhas = _falhas_das_saidas(
                nome, versao_dir, registro["document_id"], registro["sha256"]
            )
            if falhas:
                return falhas
        if nome == "simbolos":
            registro["etapas"][-1].update(_memoria_python(versao_dir / "simbolos"))
    return []


def _registro_inicial(contexto: Contexto, pdf_id: str, versao_dir: Path) -> Registro:
    entrada = contexto.entradas[pdf_id]
    return {
        "caminho_relativo": entrada["caminho_relativo"],
        "checkpoint_codigo": contexto.codigo,
        "document_id": "example:" + str(entrada["caminho_relativo"]),
        "etapas": [],
        "falhas": [],
        "falhas_metodos": [],
        "iniciado_em": contexto.agora(),
        "jobs": contexto.jobs,
        "metodos": list(contexto.metodos),
        "native_only": contexto.native_only,
        "pdf_id": pdf_id,
        "pipeline": contexto.pipeline,
        "schema_version": ESQUEMA_EXECUCAO,
        "sha256": entrada["sha256"],
        "status": "em_execucao",
        "versao": versao_dir.name,
    }


def _concluir(registro: Registro, versao_dir: Path, falhas: list[str], inicio: float) -> None:
    registro["falhas"] = falhas
    if falhas:
        registro["status"] = "falha"
    else:
        registro["status"] = "sucesso_parcial" if registro["falhas_metodos"] else "sucesso"
    registro["duracao_s"] = round(perf_counter() - inicio, 3)
    escrever_json_atomico(versao_dir / ARQUIVO_EXECUCAO, registro)


def inferir_pdf(contexto: Contexto, pdf_id: str) -> Registro:
    """Infere um PDF numa versão nova; qualquer erro vira falha registrada só deste PDF."""
    try:
        validar_transicao(carregar_checkpoint(contexto.rodada_dir, pdf_id), "inferido")
        pdf_dir = diretorio_pdf(contexto.rodada_dir, pdf_id)
    except RodadaError as erro:
        return {
            "falhas": [str(erro)],
            "falhas_metodos": [],
            "pdf_id": pdf_id,
            "status": "recusado",
            "versao": None,
        }
    inicio = perf_counter()
    versao_dir = reservar_versao(pdf_dir)
    registro = _registro_inicial(contexto, pdf_id, versao_dir)
    falhas: list[str] = []
    try:
        fonte = caminho_pdf_fonte(contexto.rodada_dir, pdf_id)
        if not fonte.is_file():
            falhas = [f"PDF fonte ausente: {registro['caminho_relativo']}"]
        elif hash_arquivo(fonte) != registro["sha256"]:
            falhas = ["PDF fonte alterado desde init: SHA-256 difere do checkpoint"]
        else:
            falhas = _executar_etapas(contexto, fonte, versao_dir, registro)
    except Exception as erro:  # falha isolada: os outros PDFs da onda continuam
        falhas = [f"{type(erro).__name__}: {erro}"]
    registro["concluido_em"] = contexto.agora()
    _concluir(registro, versao_dir, falhas, inicio)
    if not falhas:
        relativo = versao_dir.relative_to(Path(contexto.rodada_dir).resolve()).as_posix()
        dados: Registro = {"execucao": f"{relativo}/{ARQUIVO_EXECUCAO}", "versao": versao_dir.name}
        if registro["falhas_metodos"]:
            dados.update(falhas_metodos=registro["falhas_metodos"], status=registro["status"])
        try:
            transicionar(
                contexto.rodada_dir, pdf_id, "inferido", artefatos=[versao_dir], dados=dados
            )
        except RodadaError as erro:
            falhas = [f"checkpoint não avançou: {erro}"]
            _concluir(registro, versao_dir, falhas, inicio)
    return {
        "duracao_s": registro["duracao_s"],
        "falhas": falhas,
        "falhas_metodos": registro["falhas_metodos"],
        "pdf_id": pdf_id,
        "status": registro["status"],
        "versao": versao_dir.name,
    }


# --- onda -------------------------------------------------------------------------------


def _validar_opcoes(jobs: int, metodos: Iterable[str], pipeline: bool, native_only: bool) -> None:
    if not 1 <= jobs <= JOBS_MAXIMO:
        raise RodadaError(f"--jobs deve estar entre 1 e {JOBS_MAXIMO}: {jobs}")
    if native_only and not pipeline:
        raise RodadaError("--native-only só se aplica com --pipeline")
    desconhecidos = sorted(set(metodos) - set(METODOS))
    if desconhecidos:
        raise RodadaError(f"métodos desconhecidos: {', '.join(desconhecidos)}")


def inferir(
    rodada_dir: Path,
    pdf_ids: Sequence[str],
    *,
    jobs: int = JOBS_PADRAO,
    metodos: Sequence[str] = METODOS,
    pipeline: bool = False,
    native_only: bool = False,
    executor: Executor = executar_subprocesso,
    raiz_repositorio: Path = ROOT,
    codigo: Registro | None = None,
    agora: Callable[[], str] = _agora,
) -> Registro:
    """Infere ``pdf_ids`` com no máximo ``jobs`` PDFs simultâneos; resultado na ordem pedida."""
    _validar_opcoes(jobs, metodos, pipeline, native_only)
    rodada = carregar_rodada(rodada_dir)
    contexto = Contexto(
        rodada_dir=Path(rodada_dir).resolve(),
        raiz=raiz_corpus(rodada_dir),
        jobs=jobs,
        metodos=tuple(metodo for metodo in METODOS if metodo in metodos),
        pipeline=pipeline,
        native_only=native_only,
        executor=executor,
        cwd=ROOT,
        codigo=codigo if codigo is not None else checkpoint_codigo(raiz_repositorio),
        agora=agora,
        entradas={str(item["pdf_id"]): dict(item) for item in rodada["pdfs"]},
    )
    with ThreadPoolExecutor(max_workers=jobs, thread_name_prefix="inferencia") as pool:
        resultados = list(pool.map(lambda pdf_id: inferir_pdf(contexto, pdf_id), pdf_ids))
    totais = {"falha": 0, "recusado": 0, "sucesso": 0, "sucesso_parcial": 0}
    for item in resultados:
        totais[item["status"]] += 1
    return {"jobs": jobs, "pdfs": resultados, "totais": totais}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rodada", type=Path, required=True)
    selecao = parser.add_mutually_exclusive_group(required=True)
    selecao.add_argument("--onda", type=int)
    selecao.add_argument("--pdf", dest="pdfs", nargs="+", metavar="ID")
    parser.add_argument("--jobs", type=int, default=JOBS_PADRAO)
    parser.add_argument(
        "--metodos",
        nargs="*",
        choices=METODOS,
        default=list(METODOS),
        help="métodos opcionais do runner (padrão: todos); o método legado sempre roda",
    )
    parser.add_argument("--pipeline", action="store_true", help="roda também benchmark_network_pdf")
    parser.add_argument("--native-only", action="store_true", help="pipeline sem OCR")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    executor: Executor = executar_subprocesso,
    raiz_repositorio: Path = ROOT,
) -> int:
    args = _parser().parse_args(argv)
    try:
        _validar_opcoes(args.jobs, args.metodos, args.pipeline, args.native_only)
        pdf_ids = selecionar_pdfs(args.rodada, onda=args.onda, pdf_ids=args.pdfs or ())
        resultado = inferir(
            args.rodada,
            pdf_ids,
            jobs=args.jobs,
            metodos=args.metodos,
            pipeline=args.pipeline,
            native_only=args.native_only,
            executor=executor,
            raiz_repositorio=raiz_repositorio,
        )
    except RodadaError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    print(json_canonico(resultado), end="")
    totais = resultado["totais"]
    return 0 if totais["sucesso"] + totais["sucesso_parcial"] == len(resultado["pdfs"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
