"""Leituras de ficha do poste da curadoria: validação e congelamento.

Uso:
    python -m scripts.curation_ficha validar --rodada DIR --pdf ID --leitor {a,b,c} --arquivo JSON
    python -m scripts.curation_ficha congelar --rodada DIR --pdf ID --leitor {a,b,c} --arquivo JSON
    python -m scripts.curation_ficha comparar --rodada DIR --pdf ID
    python -m scripts.curation_ficha consolidar --rodada DIR --pdf ID [--sem-terceiro --motivo T]
    python -m scripts.curation_ficha baseline --rodada DIR [--pdf ID ...] [--native-only]
        [--runtime-directory DIR] [--parcial] [--versao-extracao VERSAO] [--processos N]
    python -m scripts.curation_ficha amostra --rodada DIR --tamanho N --semente S [--ampliar]
    python -m scripts.curation_ficha responder --rodada DIR --versao N --arquivo ARQ
    python -m scripts.curation_ficha taxa --rodada DIR

Cada leitor (IA) lê os tiles de ``render/`` de um PDF e grava uma ficha no formato de
``docs/schemas/ficha-poste.schema.json`` (``tipo = referencia``), com os metadados da leitura em
``atributos_extras.leitura``: ``leitor``, ``modelo``, ``origem`` (``revisao_ia``),
``tiles_revisados`` e ``regioes_ilegiveis``. Os leitores ``a`` e ``b`` leem a folha inteira
(escopo ``completo``, com todo tile ``a_revisar`` revisado ou coberto por região ilegível); o
leitor ``c`` lê só as regiões de conferência (escopo ``regional``), que precisam estar nos tiles
que ele declarou ter aberto.

``validar`` não grava nada. ``congelar`` valida e grava a cópia imutável
``pdfs/ID/ficha/leitura-LEITOR.json`` e registra o SHA-256 em ``ficha/congelamento.json``; nunca
sobrescreve uma leitura congelada e recusa leituras novas depois de ``ficha/referencia.json``
(consolidação). A leitura é de desenvolvimento, gerada por IA: não é gabarito nem confirmação
humana.

``comparar`` carrega as leituras ``a`` e ``b`` congeladas e grava ``ficha/comparacao.json``
(divergências, só para o orquestrador e a consolidação) e ``ficha/regioes-conferencia.json`` (só
página e bbox, o que o leitor ``c`` recebe); nunca sobrescreve uma comparação existente.

``consolidar`` exige ``comparacao.json`` e consolida as leituras ``a``, ``b`` e (se congelada)
``c`` em ``ficha/referencia.json`` (``scripts.ficha_leitura_dupla.consolidar``), com o número de
páginas da entrada do PDF em ``rodada.json``, e registra o SHA-256 em ``congelamento.json`` com
``leitor = consolidada``. Havendo regiões de conferência sem a leitura ``c``, só consolida com
``--sem-terceiro`` e ``--motivo`` (gravado em ``consolidacao.motivo_sem_terceiro``). Nunca refaz
uma referência consolidada.

``baseline`` mede o analisador vigente (``scripts.benchmark_ficha_poste``) contra a
``referencia.json`` de cada PDF selecionado (por padrão, todos da rodada) e grava a próxima versão
livre: ``pdfs/ID/ficha/baseline-vNNN/`` (``ficha-predita.json`` e ``avaliacao.json``) e
``fichas/baseline-vNNN-resumo.json``/``.md`` com o agregado por PDF e no total, sempre com os
denominadores (taxas recalculadas das somas). Recusa PDF sem referência, salvo ``--parcial``, e
referência cujo SHA-256 difere do registrado em ``congelamento.json``. Sem ``--native-only``,
confere o OCR português antes do primeiro PDF. Falha do analisador num PDF fica registrada como
``falha`` (não é zero) e o comando termina com código 1 depois de gravar o resumo.
``--versao-extracao`` escolhe a fonte da ficha predita (``projeto-promovido-v1``, o padrão, ou
``propostas-v1``) e fica em ``opcoes.versao_extracao``. ``--processos N`` mede os PDFs em até N
processos (no máximo 61, o limite do Windows, e nunca mais que os PDFs com referência); o resumo
JSON é igual ao serial, e o número de processos aparece só no ``.md``. A chave ``pendencia`` separa,
nos 4 campos do poste, os acertos afirmados dos acertos de campo que a predição declara pendente;
vãos e símbolos ficam sem essa separação.

``amostra`` sorteia postes das referências (rodízio entre PDFs, semente fixa) e grava
``fichas/amostra-humana/amostra-vNNN/`` (``amostra.json``, ``amostra.md`` e um recorte ``NN.png``
por item), sem caminho nem nome do PDF; ``--ampliar`` cria a próxima versão sem repetir itens.
``responder`` valida e grava ``respostas.json`` da amostra (uma única vez). ``taxa`` exige
respostas de todas as amostras e grava ``taxa-vNNN.json`` (taxa de postes com erro com intervalo
de Wilson, omissões e erros por campo).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import shutil
import sys
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import pymupdf

from scripts.benchmark_ficha_poste import VERSAO_EXTRACAO, VERSOES_EXTRACAO
from scripts.benchmark_ficha_poste import executar as executar_benchmark
from scripts.curation_reference import contida_na_uniao, tiles_nao_cobertos
from scripts.curation_render import carregar_indice
from scripts.curation_round import (
    RodadaError,
    caminho_pdf_fonte,
    carregar_rodada,
    diretorio_pdf,
    escrever_bytes_atomico,
    escrever_json_atomico,
    hash_arquivo,
    ler_json,
    selecionar_pdfs,
    trava,
)
from scripts.ficha_leitura_dupla import (
    TIPOS_DE_DIVERGENCIA,
    comparar_leituras,
    consolidar,
    regioes_de_conferencia,
)
from scripts.ficha_poste import validar_ficha
from scripts.ficha_poste_avaliador import CAMPOS_DO_POSTE as CAMPOS_COM_PENDENCIA
from zeny_project_handler.adapters.analysis.tesseract_runtime import inspect_tesseract_runtime

LEITORES = ("a", "b", "c")
ESQUEMA_CONGELAMENTO = "curadoria-ficha-congelamento-v1"
ESQUEMA_REGIOES = "curadoria-ficha-regioes-v1"
DIRETORIO_FICHA = "ficha"
ARQUIVO_CONGELAMENTO = "congelamento.json"
ARQUIVO_REGIOES = "regioes-conferencia.json"
ARQUIVO_REFERENCIA = "referencia.json"
ARQUIVO_COMPARACAO = "comparacao.json"
LEITOR_CONSOLIDADA = "consolidada"
CAMADAS = ("base", "annotation")
ESQUEMA_BASELINE = "curadoria-ficha-baseline-v1"
DIRETORIO_FICHAS = "fichas"
RUNTIME_PADRAO = Path("tmp/benchmark-runtime")
LIMITE_PROCESSOS = 61  # ProcessPoolExecutor recusa mais que isso no Windows
FALHA_DO_POOL = "processo de medição interrompido"
NOME_BASELINE = re.compile(r"baseline-v(\d{3,})")
ESQUEMA_TAXA = "curadoria-ficha-taxa-v1"
DIRETORIO_AMOSTRA = "amostra-humana"
NOME_AMOSTRA = re.compile(r"amostra-v(\d{3,})")
CAMPOS_DO_POSTE = ("identificador", "estruturas", "poste", "coordenada", "simbolos")
CAMPOS_AVALIADOS = (*CAMPOS_DO_POSTE, "vaos")
CHAVES_RESPOSTA = ("correto", "campos_errados", "nao_e_poste", "omissao", "nota")
DPI_RECORTE = 300
MARGEM_RECORTE = 0.04

Registro = dict[str, Any]


def diretorio_ficha(rodada_dir: Path, pdf_id: str) -> Path:
    """Diretório ``pdfs/ID/ficha`` do PDF (o ID é validado contra o manifesto da rodada)."""
    return diretorio_pdf(rodada_dir, pdf_id) / DIRETORIO_FICHA


def _caixa(valores: Sequence[float]) -> tuple[float, float, float, float]:
    return float(valores[0]), float(valores[1]), float(valores[2]), float(valores[3])


def _nome_leitura(leitor: str) -> str:
    return f"leitura-{leitor}.json"


def _numero(valor: Any) -> bool:
    return isinstance(valor, int | float) and not isinstance(valor, bool)


def _bbox_bem_formada(bbox: Any) -> bool:
    if not isinstance(bbox, list) or len(bbox) != 4 or not all(_numero(v) for v in bbox):
        return False
    x0, y0, x1, y1 = bbox
    return all(0 <= v <= 1 for v in bbox) and x0 <= x1 and y0 <= y1


def _erros_regiao_ilegivel(posicao: int, regiao: Any, paginas: frozenset[int]) -> list[str]:
    rotulo = f"atributos_extras.leitura.regioes_ilegiveis[{posicao}]"
    if not isinstance(regiao, dict):
        return [f"{rotulo}: deve ser um objeto"]
    erros = []
    pagina = regiao.get("pagina")
    if not isinstance(pagina, int) or isinstance(pagina, bool) or pagina not in paginas:
        erros.append(f"{rotulo}.pagina: inexistente no índice de tiles")
    if regiao.get("camada") not in CAMADAS:
        erros.append(f"{rotulo}.camada: deve ser 'base' ou 'annotation'")
    if not _bbox_bem_formada(regiao.get("bbox")):
        erros.append(f"{rotulo}.bbox: deve ter 4 números em [0, 1], sem inversão")
    motivo = regiao.get("motivo")
    if not isinstance(motivo, str) or not motivo.strip():
        erros.append(f"{rotulo}.motivo: texto obrigatório")
    return erros


def _erros_metadados(
    leitor: str, leitura: Mapping[str, Any], indice: Mapping[str, Any]
) -> list[str]:
    erros: list[str] = []
    if leitura.get("leitor") != leitor:
        erros.append(
            f"atributos_extras.leitura.leitor: {leitura.get('leitor')!r} difere do leitor "
            f"informado ({leitor!r})"
        )
    if leitura.get("origem") != "revisao_ia":
        erros.append("atributos_extras.leitura.origem: deve ser 'revisao_ia'")
    modelo = leitura.get("modelo")
    if not isinstance(modelo, str) or not modelo.strip():
        erros.append("atributos_extras.leitura.modelo: texto obrigatório")
    tiles = leitura.get("tiles_revisados")
    ids = {str(tile["id"]) for tile in indice["tiles"]}
    if not isinstance(tiles, list) or not tiles or not all(isinstance(t, str) for t in tiles):
        erros.append("atributos_extras.leitura.tiles_revisados: lista não vazia de ids de tile")
    else:
        erros.extend(
            f"atributos_extras.leitura.tiles_revisados: tile {tile} inexistente no índice de tiles"
            for tile in tiles
            if tile not in ids
        )
    ilegiveis = leitura.get("regioes_ilegiveis")
    if not isinstance(ilegiveis, list):
        erros.append("atributos_extras.leitura.regioes_ilegiveis: deve ser uma lista")
    else:
        paginas = frozenset(int(p["pagina"]) for p in indice["paginas"])
        for posicao, regiao in enumerate(ilegiveis):
            erros.extend(_erros_regiao_ilegivel(posicao, regiao, paginas))
    return erros


def _ilegiveis_como_tuplas(leitura: Mapping[str, Any]) -> list[tuple[int, str, list[float]]]:
    return [
        (int(r["pagina"]), str(r["camada"]), list(r["bbox"])) for r in leitura["regioes_ilegiveis"]
    ]


def _erros_completo(
    ficha: Mapping[str, Any], leitura: Mapping[str, Any], indice: Mapping[str, Any]
) -> list[str]:
    if ficha["escopo_anotacao"]["tipo"] != "completo":
        return ["escopo_anotacao.tipo: os leitores a e b exigem escopo completo"]
    return [
        f"escopo_anotacao: tile a_revisar {tile} não foi revisado nem está coberto por "
        "regioes_ilegiveis"
        for tile in tiles_nao_cobertos(
            indice, leitura["tiles_revisados"], _ilegiveis_como_tuplas(leitura)
        )
    ]


def _regioes_de_conferencia(rodada_dir: Path, pdf_id: str) -> list[Registro] | None:
    arquivo = diretorio_ficha(rodada_dir, pdf_id) / ARQUIVO_REGIOES
    if not arquivo.is_file():
        return None
    dados = ler_json(arquivo)
    if (
        not isinstance(dados, dict)
        or dados.get("schema_version") != ESQUEMA_REGIOES
        or dados.get("pdf_id") != pdf_id
        or not isinstance(dados.get("regioes"), list)
    ):
        raise RodadaError(f"{ARQUIVO_REGIOES} com esquema desconhecido ou de outro PDF")
    return [r for r in dados["regioes"] if isinstance(r, dict)]


def _erros_regional(
    rodada_dir: Path,
    pdf_id: str,
    ficha: Mapping[str, Any],
    leitura: Mapping[str, Any],
    indice: Mapping[str, Any],
) -> list[str]:
    if ficha["escopo_anotacao"]["tipo"] != "regional":
        return ["escopo_anotacao.tipo: o leitor c exige escopo regional"]
    conferencia = _regioes_de_conferencia(rodada_dir, pdf_id)
    if conferencia is None:
        return [
            f"{ARQUIVO_REGIOES}: ausente; as regiões de conferência são pré-requisito do leitor c"
        ]
    abertos = set(leitura["tiles_revisados"])
    ilegiveis = _ilegiveis_como_tuplas(leitura)
    erros: list[str] = []
    for posicao, regiao in enumerate(ficha["escopo_anotacao"]["regioes"]):
        rotulo = f"escopo_anotacao.regioes[{posicao}]"
        pagina, caixa = regiao["pagina"], _caixa(regiao["bbox"])
        da_pagina = [r for r in conferencia if r.get("pagina") == pagina]
        if not any(contida_na_uniao(caixa, [_caixa(r["bbox"])]) for r in da_pagina):
            erros.append(f"{rotulo}: fora das regiões de conferência da página {pagina}")
        cobertura = [
            _caixa(t["bbox"])
            for t in indice["tiles"]
            if t["pagina"] == pagina and str(t["id"]) in abertos
        ] + [_caixa(bbox) for p, _, bbox in ilegiveis if p == pagina]
        if not contida_na_uniao(caixa, cobertura):
            erros.append(
                f"{rotulo}: região não coberta pelos tiles_revisados e regioes_ilegiveis "
                f"da página {pagina}"
            )
    return erros


def erros_leitura(
    rodada_dir: Path, pdf_id: str, leitor: str, dados: Mapping[str, Any]
) -> list[str]:
    """Erros (lista vazia = válida) da leitura de ``leitor`` frente ao índice e à rodada."""
    if leitor not in LEITORES:
        return [f"leitor: {leitor!r} desconhecido (use {', '.join(LEITORES)})"]
    erros = validar_ficha(dados)
    if erros:
        return erros
    indice = carregar_indice(rodada_dir, pdf_id)
    erros = []
    if dados["tipo"] != "referencia":
        erros.append("tipo: a leitura deve ser 'referencia'")
    if dados["pdf_sha256"] != indice["sha256_pdf"]:
        erros.append("pdf_sha256: difere do sha256 do PDF da rodada")
    extras = dados.get("atributos_extras")
    leitura = extras.get("leitura") if isinstance(extras, dict) else None
    if not isinstance(leitura, dict):
        return [*erros, "atributos_extras.leitura: bloco de metadados da leitura ausente"]
    erros.extend(_erros_metadados(leitor, leitura, indice))
    if erros:
        return erros
    if leitor == "c":
        return _erros_regional(rodada_dir, pdf_id, dados, leitura, indice)
    return _erros_completo(dados, leitura, indice)


def _manifesto(pasta: Path) -> Registro:
    arquivo = pasta / ARQUIVO_CONGELAMENTO
    if not arquivo.is_file():
        return {"schema_version": ESQUEMA_CONGELAMENTO, "itens": []}
    dados = ler_json(arquivo)
    if (
        not isinstance(dados, dict)
        or dados.get("schema_version") != ESQUEMA_CONGELAMENTO
        or not isinstance(dados.get("itens"), list)
    ):
        raise RodadaError(f"{ARQUIVO_CONGELAMENTO} com esquema desconhecido")
    return dados


def _ler_ficha(arquivo: Path) -> tuple[Any, bytes]:
    try:
        conteudo = Path(arquivo).read_bytes()
    except OSError:
        raise RodadaError(f"arquivo ilegível: {Path(arquivo).name}") from None
    try:
        return json.loads(conteudo.decode("utf-8")), conteudo
    except ValueError:
        raise RodadaError(f"JSON inválido em {Path(arquivo).name}") from None


def congelar_leitura(rodada_dir: Path, pdf_id: str, leitor: str, arquivo: Path) -> Registro:
    """Valida o rascunho e grava a cópia imutável com seu SHA-256; devolve o item registrado."""
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    dados, conteudo = _ler_ficha(arquivo)
    if not isinstance(dados, dict):
        raise ValueError("a ficha deve ser um objeto JSON")
    erros = erros_leitura(rodada_dir, pdf_id, leitor, dados)
    if erros:
        raise ValueError("; ".join(erros))
    pasta.mkdir(parents=True, exist_ok=True)
    copia = pasta / _nome_leitura(leitor)
    with trava(pasta / ARQUIVO_CONGELAMENTO):
        if (pasta / ARQUIVO_REFERENCIA).exists():
            raise ValueError(f"referência já consolidada para {pdf_id}; não há novas leituras")
        manifesto = _manifesto(pasta)
        if copia.exists() or any(item.get("leitor") == leitor for item in manifesto["itens"]):
            raise ValueError(f"leitura {leitor} já congelada para {pdf_id}")
        escrever_bytes_atomico(copia, conteudo)
        item: Registro = {
            "leitor": leitor,
            "arquivo": copia.name,
            "sha256": hash_arquivo(copia),
            "horario": datetime.now(UTC).isoformat(timespec="seconds"),
            "exposicao": False,
        }
        manifesto["itens"].append(item)
        escrever_json_atomico(pasta / ARQUIVO_CONGELAMENTO, manifesto)
    return item


def carregar_congelada(rodada_dir: Path, pdf_id: str, leitor: str) -> Registro:
    """Ficha congelada do leitor, conferida contra o sha256 registrado em ``congelamento.json``."""
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    item = next((i for i in _manifesto(pasta)["itens"] if i.get("leitor") == leitor), None)
    copia = pasta / _nome_leitura(leitor)
    if item is None or not copia.is_file():
        raise ValueError(f"leitura {leitor} não congelada para {pdf_id}")
    if hash_arquivo(copia) != item.get("sha256"):
        raise ValueError(f"leitura {leitor} adulterada: sha256 difere do registrado")
    dados = ler_json(copia)
    if not isinstance(dados, dict):
        raise ValueError(f"leitura {leitor} inválida: a raiz deve ser um objeto")
    return dados


def _paginas_do_pdf(rodada_dir: Path, pdf_id: str) -> int:
    entrada: Registro = next(
        (e for e in carregar_rodada(rodada_dir)["pdfs"] if e.get("pdf_id") == pdf_id), {}
    )
    paginas = entrada.get("paginas")
    if not isinstance(paginas, int) or isinstance(paginas, bool) or paginas < 1:
        raise RodadaError(f"{pdf_id} sem número de páginas válido em rodada.json")
    return paginas


def _validar_opcoes_sem_terceiro(sem_terceiro: bool, motivo: str | None) -> None:
    if motivo is not None and not sem_terceiro:
        raise ValueError("--motivo só vale com --sem-terceiro")
    if sem_terceiro and (motivo is None or not motivo.strip()):
        raise ValueError("--sem-terceiro exige --motivo com o motivo da falta do leitor c")


def _leitura_c(
    rodada_dir: Path, pdf_id: str, comparacao: Registro, sem_terceiro: bool
) -> Registro | None:
    """Leitura C congelada, ou ``None`` quando ela falta e a consolidação pode seguir sem ela."""
    itens = _manifesto(diretorio_ficha(rodada_dir, pdf_id))["itens"]
    if any(item.get("leitor") == "c" for item in itens):
        if sem_terceiro:
            raise ValueError("leitura c congelada; consolide sem --sem-terceiro")
        return carregar_congelada(rodada_dir, pdf_id, "c")
    if regioes_de_conferencia(comparacao) and not sem_terceiro:
        raise ValueError(
            "há regiões de conferência e a leitura c não foi congelada; congele a leitura c "
            "ou use --sem-terceiro --motivo TEXTO"
        )
    return None


def consolidar_referencia(
    rodada_dir: Path, pdf_id: str, *, sem_terceiro: bool = False, motivo: str | None = None
) -> Registro:
    """Consolida A, B e C congeladas em ``referencia.json`` e registra o sha256 no manifesto."""
    _validar_opcoes_sem_terceiro(sem_terceiro, motivo)
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    if not (pasta / ARQUIVO_COMPARACAO).is_file():
        raise ValueError(f"{ARQUIVO_COMPARACAO} ausente para {pdf_id}; rode comparar antes")
    comparacao = ler_json(pasta / ARQUIVO_COMPARACAO)
    if not isinstance(comparacao, dict) or not isinstance(comparacao.get("divergencias"), list):
        raise RodadaError(f"{ARQUIVO_COMPARACAO} com esquema desconhecido")
    a = carregar_congelada(rodada_dir, pdf_id, "a")
    b = carregar_congelada(rodada_dir, pdf_id, "b")
    c = _leitura_c(rodada_dir, pdf_id, comparacao, sem_terceiro)
    paginas = _paginas_do_pdf(rodada_dir, pdf_id)
    with trava(pasta / ARQUIVO_CONGELAMENTO):
        manifesto = _manifesto(pasta)
        if (pasta / ARQUIVO_REFERENCIA).exists() or any(
            item.get("leitor") == LEITOR_CONSOLIDADA for item in manifesto["itens"]
        ):
            raise ValueError(f"referência já consolidada para {pdf_id}; não é refeita")
        referencia = consolidar(a, b, c, comparacao, paginas=paginas)
        if sem_terceiro and motivo is not None:
            referencia["atributos_extras"]["consolidacao"]["motivo_sem_terceiro"] = motivo.strip()
        escrever_json_atomico(pasta / ARQUIVO_REFERENCIA, referencia)
        manifesto["itens"].append(
            {
                "leitor": LEITOR_CONSOLIDADA,
                "arquivo": ARQUIVO_REFERENCIA,
                "sha256": hash_arquivo(pasta / ARQUIVO_REFERENCIA),
                "horario": datetime.now(UTC).isoformat(timespec="seconds"),
                "exposicao": False,
            }
        )
        escrever_json_atomico(pasta / ARQUIVO_CONGELAMENTO, manifesto)
    return referencia


def comparar(rodada_dir: Path, pdf_id: str) -> Registro:
    """Compara as leituras A e B congeladas e grava a comparação e as regiões de conferência."""
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    a = carregar_congelada(rodada_dir, pdf_id, "a")
    b = carregar_congelada(rodada_dir, pdf_id, "b")
    with trava(pasta / ARQUIVO_COMPARACAO):
        for nome in (ARQUIVO_COMPARACAO, ARQUIVO_REGIOES):
            if (pasta / nome).exists():
                raise ValueError(f"{nome} já existe para {pdf_id}; a comparação não é refeita")
        comparacao = comparar_leituras(a, b)
        escrever_json_atomico(pasta / ARQUIVO_COMPARACAO, comparacao)
        escrever_json_atomico(
            pasta / ARQUIVO_REGIOES,
            {
                "schema_version": ESQUEMA_REGIOES,
                "pdf_id": pdf_id,
                "regioes": regioes_de_conferencia(comparacao),
            },
        )
    return comparacao


# --- baseline do analisador atual ----------------------------------------------------------


def _taxa(numerador: int, denominador: int) -> float | None:
    return numerador / denominador if denominador else None


def _contagem_somada(blocos: Sequence[Mapping[str, Any]]) -> Registro:
    tp, fp, fn = (sum(int(b[chave]) for b in blocos) for chave in ("tp", "fp", "fn"))
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precisao": _taxa(tp, tp + fp),
        "recall": _taxa(tp, tp + fn),
    }


def _taxa_somada(blocos: Sequence[Mapping[str, Any]]) -> Registro:
    acertos = sum(int(b["acertos"]) for b in blocos)
    total = sum(int(b["total"]) for b in blocos)
    return {"acertos": acertos, "total": total, "taxa": _taxa(acertos, total)}


def _bloco_agregado(relatorios: Sequence[Mapping[str, Any]]) -> Registro:
    """Soma as contagens dos relatórios e recalcula as taxas (nunca média de taxas)."""
    campos = sorted({campo for r in relatorios for campo in r["campos"]})
    vaos = [r["vaos"] for r in relatorios]
    return {
        "postes": _contagem_somada([r["postes"] for r in relatorios]),
        "campos": {
            campo: _taxa_somada([r["campos"][campo] for r in relatorios if campo in r["campos"]])
            for campo in campos
        },
        "vaos": {
            **_contagem_somada(vaos),
            "comprimento": _taxa_somada([v["comprimento"] for v in vaos]),
            "cabo": _taxa_somada([v["cabo"] for v in vaos]),
        },
        "simbolos": _contagem_somada([r["simbolos"] for r in relatorios]),
        "distancias_casamento": sorted(
            float(p["distancia"]) for r in relatorios for p in r["pares"]
        ),
    }


def agregar_avaliacoes(avaliacoes: Mapping[str, Mapping[str, Any] | None]) -> Registro:
    """Agrega relatórios de ``avaliar`` por PDF e no total (``None`` = sem referência).

    Um PDF sem referência ou com falha do analisador aparece no ``por_pdf`` com sua situação e
    fica fora do total: ausência de medida não é zero.
    """
    por_pdf: Registro = {}
    medidos: list[Mapping[str, Any]] = []
    for pdf_id, avaliacao in avaliacoes.items():
        if avaliacao is None:
            por_pdf[pdf_id] = {"situacao": "sem_referencia"}
        elif "situacao" in avaliacao:
            por_pdf[pdf_id] = dict(avaliacao)
        else:
            por_pdf[pdf_id] = _bloco_agregado([avaliacao])
            medidos.append(avaliacao)
    return {"por_pdf": por_pdf, "total": _bloco_agregado(medidos)}


def _pdfs_do_baseline(rodada_dir: Path, pdf_ids: Sequence[str]) -> list[str]:
    if pdf_ids:
        return selecionar_pdfs(rodada_dir, pdf_ids=pdf_ids)
    return [str(entrada["pdf_id"]) for entrada in carregar_rodada(rodada_dir)["pdfs"]]


def _conferir_referencia(rodada_dir: Path, pdf_id: str) -> Path:
    """``referencia.json`` do PDF, conferida contra o sha256 registrado no congelamento."""
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    item = next(
        (i for i in _manifesto(pasta)["itens"] if i.get("leitor") == LEITOR_CONSOLIDADA), None
    )
    referencia = pasta / ARQUIVO_REFERENCIA
    if item is None:
        raise ValueError(f"referência de {pdf_id} sem registro de congelamento")
    if hash_arquivo(referencia) != item.get("sha256"):
        raise ValueError(f"referência de {pdf_id} adulterada: sha256 difere do registrado")
    return referencia


def _referencias_do_baseline(
    rodada_dir: Path, pdf_ids: Sequence[str], *, parcial: bool
) -> dict[str, Path | None]:
    sem_referencia = [
        pdf_id
        for pdf_id in pdf_ids
        if not (diretorio_ficha(rodada_dir, pdf_id) / ARQUIVO_REFERENCIA).is_file()
    ]
    if sem_referencia and not parcial:
        raise ValueError(
            f"{ARQUIVO_REFERENCIA} ausente para: {', '.join(sem_referencia)}; "
            "consolide antes ou use --parcial"
        )
    return {
        pdf_id: None if pdf_id in sem_referencia else _conferir_referencia(rodada_dir, pdf_id)
        for pdf_id in pdf_ids
    }


def _exigir_ocr(runtime_directory: Path) -> None:
    runtime = inspect_tesseract_runtime(runtime_directory)
    if not runtime.portugues_pronto:
        raise ValueError(f"OCR português obrigatório: {runtime.diagnostico}")


def _proxima_versao_baseline(rodada_dir: Path, pdf_ids: Sequence[str]) -> int:
    nomes = [p.name for p in (rodada_dir / DIRETORIO_FICHAS).glob("baseline-v*-resumo.json")]
    nomes += [
        p.name
        for pdf_id in pdf_ids
        for p in diretorio_ficha(rodada_dir, pdf_id).glob("baseline-v*")
    ]
    numeros = [int(m.group(1)) for nome in nomes if (m := NOME_BASELINE.match(nome))]
    return max(numeros, default=0) + 1


def _padrao_de_caminho(caminho: Path) -> str:
    separador = r"[\\/]+"
    partes = [re.escape(parte) for parte in re.split(separador, str(caminho)) if parte]
    return separador.join(partes)


# Início de caminho absoluto: unidade Windows (``C:\`` ou ``C:/``), UNC (``\\servidor``, também
# com as barras dobradas do repr) ou POSIX (``/home``). UNC e barra POSIX só contam fora de palavra,
# URL, caminho relativo (``a/b``, ``./x``, ``..\\x``) ou resto de ``<caminho>`` já trocado.
_FORA_DE_CAMINHO = r"(?<![\w.:/\\<>~-])"
_INICIO_ABSOLUTO = (
    rf"(?:(?<!\w)[A-Za-z]:[\\/]|{_FORA_DE_CAMINHO}\\{{2,}}(?=\w)"
    rf"|{_FORA_DE_CAMINHO}/(?=[\w.~$/\\-]))"
)
_ABSOLUTO_ENTRE_ASPAS = re.compile(rf"""(['"]){_INICIO_ABSOLUTO}[^'"\r\n]*\1""")
_ABSOLUTO_SOLTO = re.compile(rf"""{_INICIO_ABSOLUTO}(?:[^\s'"]*[^\s'".,;:)\]}}])?""")


def _sem_caminho_absoluto(linha: str) -> str:
    """Troca por ``<caminho>`` o caminho absoluto que sobrou, entre aspas (inteiro) ou solto."""
    linha = _ABSOLUTO_ENTRE_ASPAS.sub(r"\1<caminho>\1", linha)
    return _ABSOLUTO_SOLTO.sub("<caminho>", linha)


def _sanear(texto: str, pdf: Path, pdf_id: str, *diretorios: Path) -> str:
    """Primeira linha do erro sem o caminho do PDF, os diretórios, o nome nem caminho absoluto."""
    linha = (texto.strip().splitlines() or ["sem detalhe"])[0]
    flags = re.IGNORECASE
    linha = re.sub(_padrao_de_caminho(pdf), pdf_id, linha, flags=flags)
    for diretorio in (pdf.parent, *diretorios):
        linha = re.sub(_padrao_de_caminho(diretorio), "<caminho>", linha, flags=flags)
    nomes = [pdf.name] + ([pdf.stem] if len(pdf.stem) >= 4 else [])
    for nome in nomes:
        linha = re.sub(re.escape(nome), pdf_id, linha, flags=flags)
    return _sem_caminho_absoluto(linha)


def _medir_pdf(
    rodada_dir: Path,
    pdf_id: str,
    referencia: Path,
    saida: Path,
    *,
    native_only: bool,
    runtime_directory: Path,
    versao_extracao: str = VERSAO_EXTRACAO,
    executor: Callable[..., Registro] | None = None,
) -> Registro:
    pdf = caminho_pdf_fonte(rodada_dir, pdf_id)
    # Resolvido na chamada (e não no def) para os testes poderem trocar ``executar_benchmark``.
    executar = executor if executor is not None else executar_benchmark
    try:
        return executar(
            pdf,
            referencia,
            saida,
            native_only=native_only,
            runtime_directory=runtime_directory,
            versao_extracao=versao_extracao,
        )
    except Exception as erro:
        diretorios = (rodada_dir.resolve(), runtime_directory.resolve())
        return {"situacao": "falha", "erro": _sanear(str(erro), pdf, pdf_id, *diretorios)}


def _medir_pdf_no_pool(argumentos: tuple[Any, ...]) -> Registro:
    """Ponto de entrada do processo filho: um PDF, só na própria pasta de saída."""
    return _medir_pdf(*argumentos[:4], **argumentos[4])


def _processos_efetivos(pedido: int, com_referencia: int) -> int:
    return max(1, min(pedido, com_referencia, LIMITE_PROCESSOS))


def _medir_em_pool(
    ids: Sequence[str], argumentos: Sequence[tuple[Any, ...]], processos: int
) -> dict[str, Registro]:
    resultados: dict[str, Registro] = {}
    with ProcessPoolExecutor(max_workers=processos) as pool:
        try:
            for pdf_id, resultado in zip(
                ids, pool.map(_medir_pdf_no_pool, argumentos), strict=True
            ):
                resultados[pdf_id] = resultado
        except BrokenProcessPool:
            pass  # crash nativo num worker: os PDFs sem resultado viram falha abaixo
    return {
        pdf_id: resultados.get(pdf_id, {"situacao": "falha", "erro": FALHA_DO_POOL})
        for pdf_id in ids
    }


def _medir_pdfs(
    rodada_dir: Path,
    referencias: Mapping[str, Path | None],
    saidas: Mapping[str, Path],
    *,
    processos: int,
    **opcoes: Any,
) -> dict[str, Registro | None]:
    """Mede cada PDF com referência (serial ou em pool) e preserva a ordem de ``referencias``."""
    ids = [pdf_id for pdf_id, referencia in referencias.items() if referencia is not None]
    argumentos = [
        (rodada_dir, pdf_id, referencias[pdf_id], saidas[pdf_id], opcoes) for pdf_id in ids
    ]
    if processos > 1 and len(ids) > 1:
        medidos = _medir_em_pool(ids, argumentos, processos)
    else:
        medidos = {pdf_id: _medir_pdf_no_pool(a) for pdf_id, a in zip(ids, argumentos, strict=True)}
    return {pdf_id: medidos.get(pdf_id) for pdf_id in referencias}


def _versao_instalada(pacote: str) -> str | None:
    try:
        return version(pacote)
    except PackageNotFoundError:
        return None


def _gerador_do_baseline(pastas: Sequence[Path]) -> Registro | None:
    for pasta in pastas:
        arquivo = pasta / "ficha-predita.json"
        if arquivo.is_file():
            gerador = ler_json(arquivo).get("gerador")
            return gerador if isinstance(gerador, dict) else None
    return None


def _bloco_pendencia_zerado() -> Registro:
    return {c: {"acertos_afirmados": 0, "acertos_com_pendencia": 0} for c in CAMPOS_COM_PENDENCIA}


def _pendentes_por_poste(pasta: Path) -> dict[str, Collection[str]] | None:
    """``id`` do poste predito -> campos pendentes; ``None`` sem ``ficha-predita.json`` legível."""
    arquivo = pasta / "ficha-predita.json"
    if not arquivo.is_file():
        return None
    ficha = ler_json(arquivo)
    postes = ficha.get("postes") if isinstance(ficha, dict) else None
    if not isinstance(postes, list):
        return None
    return {
        str(poste["id"]): poste["pendentes"]
        for poste in postes
        if isinstance(poste, dict) and "id" in poste and isinstance(poste.get("pendentes"), list)
    }


def _pendencia_do_pdf(avaliacao: Mapping[str, Any], pasta: Path) -> Registro | None:
    """Acertos afirmados e com pendência de um PDF, ou ``None`` quando não dá para separar."""
    pendentes = None if "situacao" in avaliacao else _pendentes_por_poste(pasta)
    if pendentes is None:
        return None
    bloco = _bloco_pendencia_zerado()
    for par in avaliacao.get("pares", []):
        campos, predicao = par.get("campos"), par.get("predicao")
        if not isinstance(campos, dict) or predicao not in pendentes:
            continue
        for campo in CAMPOS_COM_PENDENCIA:
            if campos.get(campo) is True:
                chave = (
                    "acertos_com_pendencia" if campo in pendentes[predicao] else "acertos_afirmados"
                )
                bloco[campo][chave] += 1
    return bloco


def _pendencia(
    avaliacoes: Mapping[str, Mapping[str, Any] | None], saidas: Mapping[str, Path]
) -> Registro:
    """Separa, por PDF e no total, os acertos afirmados dos acertos de campo pendente.

    Fica fora o PDF em falha ou sem referência, sem ``ficha-predita.json`` e o par sem ``campos``
    ou sem ``predicao``: o que não dá para cruzar não entra, nem como erro.
    """
    por_pdf: Registro = {}
    for pdf_id, avaliacao in avaliacoes.items():
        bloco = None if avaliacao is None else _pendencia_do_pdf(avaliacao, saidas[pdf_id])
        if bloco is not None:
            por_pdf[pdf_id] = bloco
    total = _bloco_pendencia_zerado()
    for bloco in por_pdf.values():
        for campo, contagem in bloco.items():
            for chave, valor in contagem.items():
                total[campo][chave] += valor
    return {"por_pdf": por_pdf, "total": total}


def _percentual(parte: int, todo: int) -> str:
    return f"{parte}/{todo}" + (f" ({parte / todo:.1%})" if todo else " (n/d)")


def _linha_baseline(rotulo: str, bloco: Mapping[str, Any]) -> str:
    if "situacao" in bloco:
        return f"| {rotulo} | {bloco['situacao']} | | | | | |"
    postes, vaos, simbolos = bloco["postes"], bloco["vaos"], bloco["simbolos"]
    colunas = (
        _percentual(postes["tp"], postes["tp"] + postes["fn"]),
        _percentual(postes["tp"], postes["tp"] + postes["fp"]),
        _percentual(vaos["tp"], vaos["tp"] + vaos["fn"]),
        _percentual(vaos["comprimento"]["acertos"], vaos["comprimento"]["total"]),
        _percentual(vaos["cabo"]["acertos"], vaos["cabo"]["total"]),
        _percentual(simbolos["tp"], simbolos["tp"] + simbolos["fn"]),
    )
    return f"| {rotulo} | medido | " + " | ".join(colunas) + " |"


def _markdown_baseline(resumo: Mapping[str, Any], processos: tuple[int, int] = (1, 1)) -> str:
    pedido, efetivo = processos
    linhas = [
        f"# {resumo['versao']}",
        "",
        f"Versão de extração: {resumo['opcoes']['versao_extracao']}",
        f"Processos: {pedido} (efetivos: {efetivo})",
        "",
        f"Parcial: {'sim' if resumo['parcial'] else 'não'}. Todas as taxas são acertos/total.",
        "",
        "| PDF | Situação | Recall de postes | Precisão de postes | Recall de vãos "
        "| Comprimento | Cabo | Recall de símbolos |",
        "|---|---|---|---|---|---|---|---|",
    ]
    linhas += [_linha_baseline(pdf_id, bloco) for pdf_id, bloco in resumo["por_pdf"].items()]
    linhas.append(_linha_baseline("TOTAL", resumo["total"]))
    linhas += ["", "## Campos do poste (total)", "", "| Campo | Acertos |", "|---|---|"]
    linhas += [
        f"| {campo} | {_percentual(bloco['acertos'], bloco['total'])} |"
        for campo, bloco in resumo["total"]["campos"].items()
    ]
    linhas += [
        "",
        "## Acertos afirmados e com pendência (total)",
        "",
        "| Campo | Acertos afirmados | Acertos com pendência |",
        "|---|---|---|",
    ]
    linhas += [
        f"| {campo} | {bloco['acertos_afirmados']} | {bloco['acertos_com_pendencia']} |"
        for campo, bloco in resumo["pendencia"]["total"].items()
    ]
    linhas += ["", "Vãos e símbolos: sem separação de pendência."]
    return "\n".join(linhas) + "\n"


def baseline(
    rodada_dir: Path,
    pdf_ids: Sequence[str] = (),
    *,
    native_only: bool = False,
    runtime_directory: Path = RUNTIME_PADRAO,
    parcial: bool = False,
    versao_extracao: str = VERSAO_EXTRACAO,
    processos: int = 1,
    _executor: Callable[..., Registro] | None = None,
) -> Registro:
    """Mede o analisador atual contra as referências e grava a próxima ``baseline-vNNN``.

    ``_executor`` é privado, para teste: função de nível de módulo (o spawn a reimporta).
    """
    if versao_extracao not in VERSOES_EXTRACAO:
        raise ValueError(f"versao_extracao desconhecida: {versao_extracao}")
    if processos < 1:
        raise ValueError("processos deve ser pelo menos 1")
    selecionados = _pdfs_do_baseline(rodada_dir, pdf_ids)
    referencias = _referencias_do_baseline(rodada_dir, selecionados, parcial=parcial)
    if not native_only:
        _exigir_ocr(runtime_directory)
    pasta_fichas = rodada_dir / DIRETORIO_FICHAS
    pasta_fichas.mkdir(parents=True, exist_ok=True)
    with trava(pasta_fichas / "baseline"):
        nome = f"baseline-v{_proxima_versao_baseline(rodada_dir, selecionados):03d}"
        saidas = {p: diretorio_ficha(rodada_dir, p) / nome for p in selecionados}
        efetivos = _processos_efetivos(
            processos, sum(1 for r in referencias.values() if r is not None)
        )
        avaliacoes = _medir_pdfs(
            rodada_dir,
            referencias,
            saidas,
            processos=efetivos,
            native_only=native_only,
            runtime_directory=runtime_directory,
            versao_extracao=versao_extracao,
            executor=_executor,
        )
        resumo: Registro = {
            "schema_version": ESQUEMA_BASELINE,
            "versao": nome,
            "opcoes": {
                "native_only": native_only,
                "pdfs": selecionados,
                "versao_extracao": versao_extracao,
            },
            "parcial": parcial,
            "versoes": {
                "pillow": _versao_instalada("pillow"),
                "pymupdf": _versao_instalada("pymupdf"),
            },
            "gerador": _gerador_do_baseline(list(saidas.values())),
            **agregar_avaliacoes(avaliacoes),
            "pendencia": _pendencia(avaliacoes, saidas),
        }
        escrever_json_atomico(pasta_fichas / f"{nome}-resumo.json", resumo)
        escrever_bytes_atomico(
            pasta_fichas / f"{nome}-resumo.md",
            _markdown_baseline(resumo, (processos, efetivos)).encode("utf-8"),
        )
    return resumo


# --- amostra humana e taxa de erro de rótulo ------------------------------------------------


def sortear_amostra(
    postes_por_pdf: Mapping[str, Sequence[str]],
    tamanho: int,
    semente: int,
    *,
    excluir: Collection[tuple[str, str]] = (),
) -> list[tuple[str, str]]:
    """Sorteio determinístico, em rodízio entre os PDFs ordenados (estratificado por folha)."""
    aleatorio = random.Random(semente)
    filas: list[list[tuple[str, str]]] = []
    for pdf_id in sorted(postes_por_pdf):
        restantes = sorted(p for p in postes_por_pdf[pdf_id] if (pdf_id, p) not in excluir)
        aleatorio.shuffle(restantes)
        filas.append([(pdf_id, p) for p in restantes])
    sorteados: list[tuple[str, str]] = []
    while len(sorteados) < tamanho and any(filas):
        for fila in filas:
            if fila and len(sorteados) < tamanho:
                sorteados.append(fila.pop())
    return sorteados


def intervalo_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Intervalo de Wilson para a proporção ``k/n`` (``None`` sem observações)."""
    if n == 0:
        return None
    p = k / n
    fator = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / fator
    meia = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / fator
    return max(0.0, centro - meia), min(1.0, centro + meia)


def _diretorio_humana(rodada_dir: Path) -> Path:
    return Path(rodada_dir).resolve() / DIRETORIO_FICHAS / DIRETORIO_AMOSTRA


def _versoes_amostra(humana: Path) -> list[int]:
    return sorted(
        int(m.group(1)) for p in humana.glob("amostra-v*") if (m := NOME_AMOSTRA.fullmatch(p.name))
    )


def _nome_amostra(versao: int) -> str:
    return f"amostra-v{versao:03d}"


def _populacao(rodada_dir: Path) -> dict[str, Registro]:
    """``referencia.json`` de cada PDF que a tem (conferida contra o congelamento)."""
    referencias: dict[str, Registro] = {}
    for entrada in carregar_rodada(rodada_dir)["pdfs"]:
        pdf_id = str(entrada["pdf_id"])
        if (diretorio_ficha(rodada_dir, pdf_id) / ARQUIVO_REFERENCIA).is_file():
            referencias[pdf_id] = ler_json(_conferir_referencia(rodada_dir, pdf_id))
    if not referencias:
        raise ValueError(f"nenhum PDF com {ARQUIVO_REFERENCIA}; consolide antes de amostrar")
    return referencias


def _campos_da_amostra(poste: Mapping[str, Any], vaos: Sequence[Mapping[str, Any]]) -> Registro:
    ligados = [
        {chave: vao[chave] for chave in ("de", "para", "comprimento_m", "cabo")}
        for vao in vaos
        if poste["id"] in (vao["de"], vao["para"])
    ]
    campos = {chave: poste[chave] for chave in CAMPOS_DO_POSTE}
    return {**campos, "vaos_ligados": ligados, "pendentes": list(poste["pendentes"])}


def _recorte_do_poste(pagina: Any, bbox: Sequence[float]) -> bytes:
    x0, y0, x1, y1 = _caixa(bbox)
    largura, altura = pagina.rect.width, pagina.rect.height
    esquerda, topo, direita, base = (
        min(1.0, max(0.0, v))
        for v in (
            x0 - MARGEM_RECORTE,
            y0 - MARGEM_RECORTE,
            x1 + MARGEM_RECORTE,
            y1 + MARGEM_RECORTE,
        )
    )
    area = pymupdf.Rect(esquerda * largura, topo * altura, direita * largura, base * altura)  # type: ignore[no-untyped-call]
    if area.is_empty:
        raise ValueError("bbox do poste sem área na página")
    return bytes(pagina.get_pixmap(dpi=DPI_RECORTE, clip=area).tobytes("png"))


def _gravar_recortes(rodada_dir: Path, pasta: Path, itens: Sequence[Registro]) -> None:
    for pdf_id in sorted({str(i["pdf_id"]) for i in itens}):
        with pymupdf.open(caminho_pdf_fonte(rodada_dir, pdf_id)) as documento:  # type: ignore[no-untyped-call]
            for item in (i for i in itens if i["pdf_id"] == pdf_id):
                if not 1 <= item["pagina"] <= documento.page_count:
                    raise ValueError(f"página {item['pagina']} inexistente em {pdf_id}")
                png = _recorte_do_poste(documento[item["pagina"] - 1], item["bbox"])
                escrever_bytes_atomico(pasta / item["recorte"], png)


PERGUNTAS_AMOSTRA = (
    "A ficha está correta?",
    "Quais campos erram (identificador, estruturas, poste, coordenada, simbolos, vaos)?",
    "O item não é poste?",
    "Há poste ou vão da rede visível no recorte que não está na ficha?",
)


def _markdown_amostra(versao: int, itens: Sequence[Mapping[str, Any]]) -> str:
    linhas = [f"# Amostra humana {_nome_amostra(versao)}", ""]
    for item in itens:
        linhas += [f"## Item {item['item']} ({item['pdf_id']}, página {item['pagina']})", ""]
        linhas += [f"![item {item['item']}]({item['recorte']})", ""]
        linhas += [
            f"- {chave}: `{json.dumps(valor, ensure_ascii=False)}`"
            for chave, valor in item["campos"].items()
        ]
        linhas += ["", *(f"- [ ] {pergunta}" for pergunta in PERGUNTAS_AMOSTRA), ""]
    return "\n".join(linhas)


def _itens_da_amostra(
    sorteados: Sequence[tuple[str, str]], referencias: Mapping[str, Mapping[str, Any]]
) -> list[Registro]:
    itens: list[Registro] = []
    for posicao, (pdf_id, poste_id) in enumerate(sorteados, start=1):
        referencia = referencias[pdf_id]
        poste = next(p for p in referencia["postes"] if p["id"] == poste_id)
        itens.append(
            {
                "item": f"{posicao:02d}",
                "pdf_id": pdf_id,
                "poste_id": poste_id,
                "pagina": poste["pagina"],
                "bbox": list(poste["bbox"]),
                "campos": _campos_da_amostra(poste, referencia["vaos"]),
                "recorte": f"{posicao:02d}.png",
            }
        )
    return itens


def _ja_sorteados(humana: Path, versoes: Sequence[int]) -> set[tuple[str, str]]:
    return {
        (str(i["pdf_id"]), str(i["poste_id"]))
        for versao in versoes
        for i in ler_json(humana / _nome_amostra(versao) / "amostra.json")
    }


def _gravar_amostra(rodada_dir: Path, pasta: Path, versao: int, itens: Sequence[Registro]) -> None:
    pasta.mkdir()
    try:
        _gravar_recortes(rodada_dir, pasta, itens)
        texto = _markdown_amostra(versao, itens)
        escrever_bytes_atomico(pasta / "amostra.md", texto.encode("utf-8"))
        escrever_json_atomico(pasta / "amostra.json", list(itens))
    except BaseException:
        shutil.rmtree(pasta, ignore_errors=True)
        raise


def amostrar(
    rodada_dir: Path, tamanho: int, semente: int, *, ampliar: bool = False
) -> tuple[int, int]:
    """Cria a próxima ``amostra-vNNN``; devolve ``(versão, itens)``."""
    if tamanho < 1:
        raise ValueError("--tamanho deve ser positivo")
    humana = _diretorio_humana(rodada_dir)
    humana.mkdir(parents=True, exist_ok=True)
    with trava(humana / "amostra"):
        versoes = _versoes_amostra(humana)
        if versoes and not ampliar:
            raise ValueError(f"já existe {_nome_amostra(versoes[-1])}; use --ampliar para ampliar")
        if ampliar and not versoes:
            raise ValueError("nada para ampliar: ainda não existe amostra")
        referencias = _populacao(rodada_dir)
        sorteados = sortear_amostra(
            {pdf_id: [p["id"] for p in ref["postes"]] for pdf_id, ref in referencias.items()},
            tamanho,
            semente,
            excluir=_ja_sorteados(humana, versoes),
        )
        if not sorteados:
            raise ValueError("população esgotada: todos os postes já foram sorteados")
        versao = (versoes[-1] if versoes else 0) + 1
        itens = _itens_da_amostra(sorteados, referencias)
        _gravar_amostra(rodada_dir, humana / _nome_amostra(versao), versao, itens)
    return versao, len(itens)


def _erros_consistencia(item: str, resposta: Mapping[str, Any]) -> list[str]:
    errada = not resposta["correto"]
    campos = resposta.get("campos_errados", [])
    if resposta.get("nao_e_poste") and not errada:
        return [f"item {item}: item que não é poste não pode estar correto"]
    if errada and not resposta.get("nao_e_poste") and not campos:
        return [f"item {item}: ficha incorreta exige campos_errados"]
    if not errada and campos:
        return [f"item {item}: ficha correta não tem campos_errados"]
    return []


def _erros_resposta(item: str, resposta: Any) -> list[str]:
    if not isinstance(resposta, dict):
        return [f"item {item}: a resposta deve ser um objeto"]
    desconhecidas = sorted(set(resposta) - set(CHAVES_RESPOSTA))
    if desconhecidas:
        return [f"item {item}: chaves desconhecidas {desconhecidas}"]
    erros = [
        f"item {item}: {chave} deve ser booleano"
        for chave in ("correto", "nao_e_poste", "omissao")
        if chave in resposta and not isinstance(resposta[chave], bool)
    ]
    campos = resposta.get("campos_errados", [])
    if not isinstance(campos, list) or any(c not in CAMPOS_AVALIADOS for c in campos):
        erros.append(f"item {item}: campos_errados deve listar campos de {CAMPOS_AVALIADOS}")
    if not isinstance(resposta.get("nota", ""), str):
        erros.append(f"item {item}: nota deve ser texto")
    if "correto" not in resposta:
        erros.append(f"item {item}: falta o campo correto")
    return erros or _erros_consistencia(item, resposta)


def _erros_respostas(respostas: Any, itens: Sequence[Mapping[str, Any]]) -> list[str]:
    if not isinstance(respostas, dict):
        return ["as respostas devem ser um objeto {item: resposta}"]
    esperados = [str(i["item"]) for i in itens]
    erros = [f"falta resposta do item {i}" for i in esperados if i not in respostas]
    erros += [f"item inexistente na amostra: {i}" for i in respostas if i not in esperados]
    for item in esperados:
        if item in respostas:
            erros += _erros_resposta(item, respostas[item])
    return erros


def _pasta_amostra(rodada_dir: Path, versao: int) -> Path:
    pasta = _diretorio_humana(rodada_dir) / _nome_amostra(versao)
    if not (pasta / "amostra.json").is_file():
        raise ValueError(f"{_nome_amostra(versao)} inexistente")
    return pasta


def responder(rodada_dir: Path, versao: int, arquivo: Path) -> int:
    """Valida e grava ``respostas.json`` da amostra; devolve o número de respostas."""
    pasta = _pasta_amostra(rodada_dir, versao)
    respostas = ler_json(arquivo)
    erros = _erros_respostas(respostas, ler_json(pasta / "amostra.json"))
    if erros:
        raise ValueError("; ".join(erros))
    with trava(pasta / "respostas.json"):
        if (pasta / "respostas.json").exists():
            raise ValueError(f"{_nome_amostra(versao)} já tem respostas.json; não é regravado")
        escrever_json_atomico(pasta / "respostas.json", respostas)
    return len(respostas)


Avaliacao = tuple[Mapping[str, Any], Mapping[str, Any]]


def _erros_por_campo(avaliacoes: Sequence[Avaliacao]) -> Registro:
    por_campo: Registro = {}
    for campo in CAMPOS_AVALIADOS:
        validas = [
            r
            for i, r in avaliacoes
            if not r.get("nao_e_poste") and campo not in i["campos"]["pendentes"]
        ]
        erros = sum(1 for r in validas if campo in r.get("campos_errados", []))
        por_campo[campo] = {"erros": erros, "avaliados": len(validas)}
    return por_campo


def _bloco_taxa(avaliacoes: Sequence[Avaliacao]) -> Registro:
    n = len(avaliacoes)
    com_erro = sum(1 for _, r in avaliacoes if not r["correto"])
    omissoes = sum(1 for _, r in avaliacoes if r.get("omissao"))
    intervalo = intervalo_wilson(com_erro, n)
    return {
        "itens": n,
        "postes_com_erro": {
            "k": com_erro,
            "n": n,
            "taxa": _taxa(com_erro, n),
            "wilson95": list(intervalo) if intervalo else None,
        },
        "nao_e_poste": sum(1 for _, r in avaliacoes if r.get("nao_e_poste")),
        "omissoes": {"k": omissoes, "n": n, "taxa": _taxa(omissoes, n)},
        "por_campo": _erros_por_campo(avaliacoes),
    }


def _avaliacoes_da_versao(rodada_dir: Path, versao: int) -> list[Avaliacao]:
    pasta = _pasta_amostra(rodada_dir, versao)
    if not (pasta / "respostas.json").is_file():
        raise ValueError(f"{_nome_amostra(versao)} sem respostas.json; responda antes de medir")
    itens = ler_json(pasta / "amostra.json")
    respostas = ler_json(pasta / "respostas.json")
    erros = _erros_respostas(respostas, itens)
    if erros:
        raise ValueError(f"respostas de {_nome_amostra(versao)} inválidas: {'; '.join(erros)}")
    return [(item, respostas[item["item"]]) for item in itens]


def calcular_taxa(rodada_dir: Path) -> Registro:
    """Grava a próxima ``taxa-vNNN`` (versão da maior amostra incluída)."""
    humana = _diretorio_humana(rodada_dir)
    humana.mkdir(parents=True, exist_ok=True)
    with trava(humana / "taxa"):
        versoes = _versoes_amostra(humana)
        if not versoes:
            raise ValueError("nenhuma amostra para medir")
        por_versao = {_nome_amostra(v): _avaliacoes_da_versao(rodada_dir, v) for v in versoes}
        destino = humana / f"taxa-v{versoes[-1]:03d}.json"
        if destino.exists():
            raise ValueError(f"{destino.name} já existe; amplie a amostra para nova taxa")
        taxa: Registro = {
            "schema_version": ESQUEMA_TAXA,
            "versao": destino.stem,
            "por_versao": {nome: _bloco_taxa(av) for nome, av in por_versao.items()},
            "total": _bloco_taxa([par for av in por_versao.values() for par in av]),
        }
        escrever_json_atomico(destino, taxa)
    return taxa


# --- CLI ----------------------------------------------------------------------------------


def _inteiro_positivo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{texto!r} não é um inteiro") from None
    if valor < 1:
        raise argparse.ArgumentTypeError("deve ser um inteiro maior ou igual a 1")
    return valor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    for nome, ajuda in (
        ("validar", "valida a leitura sem gravar nada"),
        ("congelar", "valida e congela a leitura (leitura-LEITOR.json)"),
    ):
        comando = sub.add_parser(nome, help=ajuda)
        comando.add_argument("--rodada", type=Path, required=True)
        comando.add_argument("--pdf", required=True)
        comando.add_argument("--leitor", required=True, choices=LEITORES)
        comando.add_argument("--arquivo", type=Path, required=True)
    comando = sub.add_parser(
        "comparar", help="compara as leituras a e b congeladas e gera as regiões de conferência"
    )
    comando.add_argument("--rodada", type=Path, required=True)
    comando.add_argument("--pdf", required=True)
    comando = sub.add_parser(
        "consolidar", help="consolida as leituras congeladas na referência (referencia.json)"
    )
    comando.add_argument("--rodada", type=Path, required=True)
    comando.add_argument("--pdf", required=True)
    comando.add_argument("--sem-terceiro", action="store_true")
    comando.add_argument("--motivo")
    comando = sub.add_parser(
        "baseline", help="mede o analisador atual contra as referências consolidadas"
    )
    comando.add_argument("--rodada", type=Path, required=True)
    comando.add_argument("--pdf", action="append", default=[])
    comando.add_argument("--native-only", action="store_true")
    comando.add_argument("--runtime-directory", type=Path, default=RUNTIME_PADRAO)
    comando.add_argument("--parcial", action="store_true")
    comando.add_argument("--versao-extracao", choices=VERSOES_EXTRACAO, default=VERSAO_EXTRACAO)
    comando.add_argument("--processos", type=_inteiro_positivo, default=1)
    comando = sub.add_parser(
        "amostra", help="sorteia postes das referências para conferência humana"
    )
    comando.add_argument("--rodada", type=Path, required=True)
    comando.add_argument("--tamanho", type=int, required=True)
    comando.add_argument("--semente", type=int, required=True)
    comando.add_argument("--ampliar", action="store_true")
    comando = sub.add_parser("responder", help="registra as respostas da conferência humana")
    comando.add_argument("--rodada", type=Path, required=True)
    comando.add_argument("--versao", type=int, required=True)
    comando.add_argument("--arquivo", type=Path, required=True)
    comando = sub.add_parser("taxa", help="calcula a taxa de erro de rótulo das amostras")
    comando.add_argument("--rodada", type=Path, required=True)
    return parser


def _imprimir_comparacao(comparacao: Mapping[str, Any], regioes: int) -> None:
    contagem = Counter(d["tipo"] for d in comparacao["divergencias"])
    print("ok: comparação das leituras a e b gravada")
    print("divergências: " + " ".join(f"{t}={contagem[t]}" for t in TIPOS_DE_DIVERGENCIA))
    print(f"regiões de conferência: {regioes}")


def _imprimir_consolidacao(referencia: Mapping[str, Any]) -> None:
    consolidacao = referencia["atributos_extras"]["consolidacao"]
    contagens = [
        f"{chave}={consolidacao[chave]}"
        for chave in (
            "resolvidas_por_c",
            "pendentes",
            "descartadas_por_maioria",
            "nao_cobertas_por_c",
        )
    ]
    contagens.append(f"excluidas={len(consolidacao['excluidas'])}")
    print("ok: referência consolidada gravada")
    print("consolidação: " + " ".join(contagens))
    print(f"escopo: {referencia['escopo_anotacao']['tipo']}")


def _imprimir_baseline(resumo: Mapping[str, Any]) -> int:
    falhas = [p for p, b in resumo["por_pdf"].items() if b.get("situacao") == "falha"]
    postes = resumo["total"]["postes"]
    print(f"{'erro' if falhas else 'ok'}: {resumo['versao']} gravado")
    print(f"postes: tp={postes['tp']} fp={postes['fp']} fn={postes['fn']}")
    for pdf_id in falhas:
        print(f"erro: falha do analisador em {pdf_id}", file=sys.stderr)
    return 1 if falhas else 0


def _executar_humana(args: argparse.Namespace) -> int:
    if args.comando == "amostra":
        versao, itens = amostrar(args.rodada, args.tamanho, args.semente, ampliar=args.ampliar)
        print(f"ok: {_nome_amostra(versao)} gravada com {itens} itens")
    elif args.comando == "responder":
        itens = responder(args.rodada, args.versao, args.arquivo)
        print(f"ok: {itens} respostas de {_nome_amostra(args.versao)} gravadas")
    else:
        taxa = calcular_taxa(args.rodada)
        erro = taxa["total"]["postes_com_erro"]
        print(f"ok: {taxa['versao']} gravada")
        print(f"postes com erro: {erro['k']}/{erro['n']} wilson95={erro['wilson95']}")
    return 0


def _executar(args: argparse.Namespace) -> int:
    if args.comando in ("amostra", "responder", "taxa"):
        return _executar_humana(args)
    if args.comando == "baseline":
        return _imprimir_baseline(
            baseline(
                args.rodada,
                args.pdf,
                native_only=args.native_only,
                runtime_directory=args.runtime_directory,
                parcial=args.parcial,
                versao_extracao=args.versao_extracao,
                processos=args.processos,
            )
        )
    if args.comando == "consolidar":
        referencia = consolidar_referencia(
            args.rodada, args.pdf, sem_terceiro=args.sem_terceiro, motivo=args.motivo
        )
        _imprimir_consolidacao(referencia)
        return 0
    if args.comando == "comparar":
        comparacao = comparar(args.rodada, args.pdf)
        _imprimir_comparacao(comparacao, len(regioes_de_conferencia(comparacao)))
        return 0
    if args.comando == "validar":
        dados, _ = _ler_ficha(args.arquivo)
        erros = (
            erros_leitura(args.rodada, args.pdf, args.leitor, dados)
            if isinstance(dados, dict)
            else ["a ficha deve ser um objeto JSON"]
        )
        if erros:
            for erro in erros:
                print(f"erro: {erro}", file=sys.stderr)
            return 1
        print(f"ok: leitura {args.leitor} válida")
        return 0
    congelar_leitura(args.rodada, args.pdf, args.leitor, args.arquivo)
    print(f"ok: leitura {args.leitor} congelada")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _executar(args)
    except (RodadaError, ValueError) as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
