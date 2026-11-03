"""Leituras de ficha do poste da curadoria: validação e congelamento.

Uso:
    python -m scripts.curation_ficha validar --rodada DIR --pdf ID --leitor {a,b,c} --arquivo JSON
    python -m scripts.curation_ficha congelar --rodada DIR --pdf ID --leitor {a,b,c} --arquivo JSON
    python -m scripts.curation_ficha comparar --rodada DIR --pdf ID
    python -m scripts.curation_ficha consolidar --rodada DIR --pdf ID [--sem-terceiro --motivo T]
    python -m scripts.curation_ficha baseline --rodada DIR [--pdf ID ...] [--native-only]
        [--runtime-directory DIR] [--parcial]

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
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

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
NOME_BASELINE = re.compile(r"baseline-v(\d{3,})")

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


def _sanear(texto: str, pdf: Path, pdf_id: str, *diretorios: Path) -> str:
    """Primeira linha do erro sem o caminho do PDF, os diretórios nem o nome do arquivo."""
    linha = (texto.strip().splitlines() or ["sem detalhe"])[0]
    flags = re.IGNORECASE
    linha = re.sub(_padrao_de_caminho(pdf), pdf_id, linha, flags=flags)
    for diretorio in (pdf.parent, *diretorios):
        linha = re.sub(_padrao_de_caminho(diretorio), "<caminho>", linha, flags=flags)
    nomes = [pdf.name] + ([pdf.stem] if len(pdf.stem) >= 4 else [])
    for nome in nomes:
        linha = re.sub(re.escape(nome), pdf_id, linha, flags=flags)
    return linha


def _medir_pdf(
    rodada_dir: Path,
    pdf_id: str,
    referencia: Path,
    saida: Path,
    *,
    native_only: bool,
    runtime_directory: Path,
) -> Registro:
    pdf = caminho_pdf_fonte(rodada_dir, pdf_id)
    try:
        return executar_benchmark(
            pdf,
            referencia,
            saida,
            native_only=native_only,
            runtime_directory=runtime_directory,
        )
    except Exception as erro:
        return {"situacao": "falha", "erro": _sanear(str(erro), pdf, pdf_id, rodada_dir.resolve())}


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


def _markdown_baseline(resumo: Mapping[str, Any]) -> str:
    linhas = [
        f"# {resumo['versao']}",
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
    return "\n".join(linhas) + "\n"


def baseline(
    rodada_dir: Path,
    pdf_ids: Sequence[str] = (),
    *,
    native_only: bool = False,
    runtime_directory: Path = RUNTIME_PADRAO,
    parcial: bool = False,
) -> Registro:
    """Mede o analisador atual contra as referências e grava a próxima ``baseline-vNNN``."""
    selecionados = _pdfs_do_baseline(rodada_dir, pdf_ids)
    referencias = _referencias_do_baseline(rodada_dir, selecionados, parcial=parcial)
    if not native_only:
        _exigir_ocr(runtime_directory)
    pasta_fichas = rodada_dir / DIRETORIO_FICHAS
    pasta_fichas.mkdir(parents=True, exist_ok=True)
    with trava(pasta_fichas / "baseline"):
        nome = f"baseline-v{_proxima_versao_baseline(rodada_dir, selecionados):03d}"
        saidas = {p: diretorio_ficha(rodada_dir, p) / nome for p in selecionados}
        avaliacoes = {
            pdf_id: None
            if referencia is None
            else _medir_pdf(
                rodada_dir,
                pdf_id,
                referencia,
                saidas[pdf_id],
                native_only=native_only,
                runtime_directory=runtime_directory,
            )
            for pdf_id, referencia in referencias.items()
        }
        resumo: Registro = {
            "schema_version": ESQUEMA_BASELINE,
            "versao": nome,
            "opcoes": {"native_only": native_only, "pdfs": selecionados},
            "parcial": parcial,
            "versoes": {
                "pillow": _versao_instalada("pillow"),
                "pymupdf": _versao_instalada("pymupdf"),
            },
            "gerador": _gerador_do_baseline(list(saidas.values())),
            **agregar_avaliacoes(avaliacoes),
        }
        escrever_json_atomico(pasta_fichas / f"{nome}-resumo.json", resumo)
        escrever_bytes_atomico(
            pasta_fichas / f"{nome}-resumo.md", _markdown_baseline(resumo).encode("utf-8")
        )
    return resumo


# --- CLI ----------------------------------------------------------------------------------


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


def _executar(args: argparse.Namespace) -> int:
    if args.comando == "baseline":
        return _imprimir_baseline(
            baseline(
                args.rodada,
                args.pdf,
                native_only=args.native_only,
                runtime_directory=args.runtime_directory,
                parcial=args.parcial,
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
