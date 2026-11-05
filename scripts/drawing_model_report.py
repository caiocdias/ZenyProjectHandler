# mypy: disable-error-code="no-untyped-call"
"""Relatório do modelo de desenho sobre um diretório de PDFs (famílias, imagens, custo).

Uso:
    python -m scripts.drawing_model_report --raiz DIR --saida ARQUIVO.json
        [--amostras-imagem DIR] [--raiz-repositorio DIR] [--processos N]

Por PDF: sha256, família e sinais; por página, contagens de caminhos, textos, polilinhas,
círculos, arcos, grupos candidatos e diagnósticos; tempo e pico de memória (``tracemalloc``,
só alocações Python) da extração; e a classe de cada imagem:

- ``ladrilho``: imagem de página cujo tamanho em pixels se repete em pelo menos 4 imagens do
  PDF e cuja caixa se encaixa numa grade (alguma outra imagem do mesmo tamanho na página
  tem borda horizontal e borda vertical alinhadas, tolerância de 1 pt);
- ``anotacao``: imagem de anotação (carimbo, assinatura, foto);
- ``outra``: o resto.

Com ``--amostras-imagem``, grava PNGs nomeados pelo ``sha256`` da imagem: cada ``outra``, até 3
``anotacao`` e, por PDF, até 5 ladrilhos cuja caixa cruza algum grupo candidato ou texto mais 2
ladrilhos sorteados com ``random.Random(sha256 do PDF)``. O PNG de imagem de página traz os
pixels originais (localizados pelo digest do pixmap); quando não há como localizá-los (imagem de
anotação), é um recorte renderizado da caixa a 150 dpi, que inclui o que estiver sobreposto.
Cada amostra gravada traz ``fonte_pixels`` (``original`` ou ``recorte``); um sha256 já gravado
na execução não é regravado. Falha ao gravar amostras não descarta a medição: vira
``erro_amostras`` (nome da classe da exceção) no PDF.

``--saida`` e ``--amostras-imagem`` precisam ficar em ``tmp/`` da raiz do repositório (padrão:
diretório atual). Nada no relatório nem nos nomes de arquivo traz caminho, nome, produtor ou
criador do PDF; os PDFs saem ordenados pelo ``sha256``.

Com ``--processos N`` (inteiro >= 1, padrão 1) os PDFs são medidos em até N processos; as
amostras de imagem continuam sendo gravadas em série, na ordem dos PDFs. ``tempo_s`` e
``pico_memoria_bytes`` medem a execução, não a leitura: com mais de um processo o tempo inclui a
disputa por CPU e o pico depende da partida a frio de cada processo do pool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
import tracemalloc
from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from itertools import pairwise
from pathlib import Path
from typing import Any, Final

import pymupdf

from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caixa,
    Circulo,
    ImagemModelo,
    ModeloDesenho,
    PaginaModelo,
    Polilinha,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho

MINIMO_LADRILHOS_IGUAIS: Final = 4
TOLERANCIA_GRADE: Final = 1.0
MAXIMO_ANOTACOES: Final = 3
MAXIMO_LADRILHOS_QUE_CRUZAM: Final = 5
LADRILHOS_SORTEADOS: Final = 2
DPI_RECORTE: Final = 150
_CLASSES: Final = ("ladrilho", "anotacao", "outra")
_TIPOS_CAMINHO: Final = ("traco", "preenchimento", "traco_e_preenchimento")


def _classificar_pagina(
    pagina: PaginaModelo, tamanhos_repetidos: set[tuple[int, int]]
) -> list[str]:
    candidatos = [
        indice
        for indice, imagem in enumerate(pagina.imagens)
        if not imagem.de_anotacao
        and (imagem.largura_px, imagem.altura_px) in tamanhos_repetidos
        and imagem.largura_px > 0
    ]
    em_grade = _em_grade([pagina.imagens[i] for i in candidatos])
    ladrilhos = {candidatos[posicao] for posicao in em_grade}
    return [
        "anotacao" if imagem.de_anotacao else "ladrilho" if indice in ladrilhos else "outra"
        for indice, imagem in enumerate(pagina.imagens)
    ]


def _em_grade(imagens: list[ImagemModelo]) -> set[int]:
    """Posições (em ``imagens``) cujas bordas x e y alinham com as de outra do mesmo tamanho."""
    por_tamanho: dict[tuple[int, int], list[int]] = {}
    for posicao, imagem in enumerate(imagens):
        por_tamanho.setdefault((imagem.largura_px, imagem.altura_px), []).append(posicao)
    resultado: set[int] = set()
    for grupo in por_tamanho.values():
        alinha_x = _alinhadas([(imagens[p].bbox[0], imagens[p].bbox[2]) for p in grupo])
        alinha_y = _alinhadas([(imagens[p].bbox[1], imagens[p].bbox[3]) for p in grupo])
        resultado.update(p for k, p in enumerate(grupo) if alinha_x[k] and alinha_y[k])
    return resultado


def _alinhadas(bordas: list[tuple[float, float]]) -> list[bool]:
    """Para cada par de bordas, se alguma borda de OUTRO item cai a menos de 1 pt."""
    ordenadas = sorted((valor, dono) for dono, par in enumerate(bordas) for valor in par)
    valores = [valor for valor, _ in ordenadas]
    resposta: list[bool] = []
    for dono, par in enumerate(bordas):
        achou = False
        for valor in par:
            inicio = bisect_left(valores, valor - TOLERANCIA_GRADE)
            fim = bisect_right(valores, valor + TOLERANCIA_GRADE)
            if any(ordenadas[k][1] != dono for k in range(inicio, fim)):
                achou = True
                break
        resposta.append(achou)
    return resposta


def _fracao_coberta(pagina: PaginaModelo, caixas: list[Caixa]) -> float:
    area_pagina = pagina.largura * pagina.altura
    if not caixas or area_pagina <= 0:
        return 0.0
    recortadas = [
        (max(x0, 0.0), max(y0, 0.0), min(x1, pagina.largura), min(y1, pagina.altura))
        for x0, y0, x1, y1 in caixas
    ]
    validas = [c for c in recortadas if c[2] > c[0] and c[3] > c[1]]
    xs = sorted({x for c in validas for x in (c[0], c[2])})
    area = 0.0
    for esquerda, direita in pairwise(xs):
        faixa = sorted((c[1], c[3]) for c in validas if c[0] <= esquerda and c[2] >= direita)
        coberto = 0.0
        fim_atual = float("-inf")
        for inicio, fim in faixa:
            inicio = max(inicio, fim_atual)
            if fim > inicio:
                coberto += fim - inicio
            fim_atual = max(fim_atual, fim)
        area += coberto * (direita - esquerda)
    return min(area / area_pagina, 1.0)


def _cruza(a: Caixa, b: Caixa) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _medir_pagina(pagina: PaginaModelo, classes: list[str]) -> dict[str, Any]:
    tipos: Counter[str] = Counter(caminho.tipo for caminho in pagina.caminhos)
    ladrilhos = [i.bbox for i, c in zip(pagina.imagens, classes, strict=True) if c == "ladrilho"]
    contagem_classes = Counter(classes)
    return {
        "indice": pagina.indice,
        "caminhos": {tipo: tipos.get(tipo, 0) for tipo in _TIPOS_CAMINHO},
        "textos": {
            "nativo": sum(1 for t in pagina.textos if t.origem == "nativo"),
            "shx": sum(1 for t in pagina.textos if t.origem == "shx"),
            "glifo": sum(1 for t in pagina.textos if t.origem == "glifo"),
        },
        "polilinhas": sum(1 for p in pagina.primitivas if isinstance(p, Polilinha)),
        "circulos": sum(1 for p in pagina.primitivas if isinstance(p, Circulo)),
        "arcos": sum(1 for p in pagina.primitivas if isinstance(p, Arco)),
        "grupos": len(pagina.grupos),
        "diagnosticos": dict(sorted(Counter(pagina.diagnosticos).items())),
        "imagens": {classe: contagem_classes.get(classe, 0) for classe in _CLASSES},
        "fracao_ladrilhos": round(_fracao_coberta(pagina, ladrilhos), 4),
    }


def _amostra(imagem: ImagemModelo, pagina: int, classe: str, motivo: str) -> dict[str, Any]:
    return {
        "sha256": imagem.sha256,
        "classe": classe,
        "motivo": motivo,
        "pagina": pagina,
        "bbox": [round(v, 2) for v in imagem.bbox],
    }


def _escolher_amostras(modelo: ModeloDesenho, classes: list[list[str]]) -> list[dict[str, Any]]:
    outras: dict[str, dict[str, Any]] = {}
    anotacoes: dict[str, dict[str, Any]] = {}
    ladrilhos: dict[str, tuple[ImagemModelo, int]] = {}
    cruzam: dict[str, dict[str, Any]] = {}
    for pagina, classes_da_pagina in zip(modelo.paginas, classes, strict=True):
        obstaculos = [g.bbox for g in pagina.grupos] + [t.bbox for t in pagina.textos]
        for imagem, classe in zip(pagina.imagens, classes_da_pagina, strict=True):
            if classe == "outra":
                outras.setdefault(imagem.sha256, _amostra(imagem, pagina.indice, classe, "outra"))
            elif classe == "anotacao":
                anotacoes.setdefault(
                    imagem.sha256, _amostra(imagem, pagina.indice, classe, "anotacao")
                )
            else:
                ladrilhos.setdefault(imagem.sha256, (imagem, pagina.indice))
                if (
                    len(cruzam) < MAXIMO_LADRILHOS_QUE_CRUZAM
                    and imagem.sha256 not in cruzam
                    and any(_cruza(imagem.bbox, o) for o in obstaculos)
                ):
                    cruzam[imagem.sha256] = _amostra(
                        imagem, pagina.indice, "ladrilho", "cruza_grupo_ou_texto"
                    )
    restantes = sorted(sha for sha in ladrilhos if sha not in cruzam)
    sorteados = random.Random(modelo.documento_sha256).sample(
        restantes, min(LADRILHOS_SORTEADOS, len(restantes))
    )
    amostras = [*outras.values(), *list(anotacoes.values())[:MAXIMO_ANOTACOES], *cruzam.values()]
    for sha in sorteados:
        imagem, pagina_indice = ladrilhos[sha]
        amostras.append(_amostra(imagem, pagina_indice, "ladrilho", "sorteio"))
    return amostras


def _sha256_do_arquivo(pdf: Path) -> str:
    with pdf.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


def _extrair_medindo(pdf: Path, tabela: TabelaGlifos | None) -> tuple[ModeloDesenho, float, int]:
    iniciou = not tracemalloc.is_tracing()
    if iniciou:
        tracemalloc.start()
    tracemalloc.reset_peak()
    inicio = time.perf_counter()
    try:
        modelo = extrair_modelo_desenho(pdf, tabela)
        tempo = time.perf_counter() - inicio
        _, pico = tracemalloc.get_traced_memory()
    finally:
        if iniciou:
            tracemalloc.stop()
    return modelo, tempo, pico


def medir_pdf(pdf: Path, tabela: TabelaGlifos | None = None) -> dict[str, Any]:
    modelo, tempo, pico = _extrair_medindo(pdf, tabela)
    tamanhos = Counter(
        (i.largura_px, i.altura_px)
        for pagina in modelo.paginas
        for i in pagina.imagens
        if not i.de_anotacao
    )
    repetidos = {t for t, n in tamanhos.items() if n >= MINIMO_LADRILHOS_IGUAIS}
    classes = [_classificar_pagina(pagina, repetidos) for pagina in modelo.paginas]
    total = Counter(c for da_pagina in classes for c in da_pagina)
    return {
        "sha256": modelo.documento_sha256,
        "familia": modelo.familia.familia,
        "sinais": dict(modelo.familia.sinais),
        "diagnosticos_familia": list(modelo.familia.diagnosticos),
        "tempo_s": round(tempo, 3),
        "pico_memoria_bytes": pico,
        "imagens": {classe: total.get(classe, 0) for classe in _CLASSES},
        "paginas": [_medir_pagina(p, c) for p, c in zip(modelo.paginas, classes, strict=True)],
        "amostras": _escolher_amostras(modelo, classes),
    }


def _sha256_do_pixmap(pixmap: Any) -> str:
    return hashlib.sha256(bytes(pixmap.digest or b"")).hexdigest()


def _pixels_da_pagina(documento: Any, pagina: Any, sha256: str) -> bytes | None:
    for informacao in pagina.get_images(full=True):
        pixmap = pymupdf.Pixmap(documento, int(informacao[0]))
        if _sha256_do_pixmap(pixmap) != sha256:
            continue
        if pixmap.colorspace is None or pixmap.colorspace.n != 3 or pixmap.alpha:
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
        return bytes(pixmap.tobytes("png"))
    return None


def _pixels_da_amostra(documento: Any, amostra: dict[str, Any]) -> tuple[bytes, str]:
    """PNG da amostra e a origem dos pixels: ``original`` ou ``recorte`` renderizado."""
    pagina = documento.load_page(int(amostra["pagina"]))
    if amostra["classe"] != "anotacao":
        conteudo = _pixels_da_pagina(documento, pagina, str(amostra["sha256"]))
        if conteudo is not None:
            return conteudo, "original"
    recorte = pagina.get_pixmap(clip=pymupdf.Rect(*amostra["bbox"]), dpi=DPI_RECORTE)
    return bytes(recorte.tobytes("png")), "recorte"


def gravar_amostras(
    pdf: Path,
    amostras: Sequence[dict[str, Any]],
    destino: Path,
    fontes: dict[str, str] | None = None,
) -> dict[str, str]:
    """Grava um PNG por sha256 ainda ausente de ``fontes`` e anota nele a origem dos pixels."""
    fontes = {} if fontes is None else fontes
    destino.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(pdf) as documento:
        for amostra in amostras:
            sha256 = str(amostra["sha256"])
            if sha256 in fontes:
                continue
            conteudo, fonte = _pixels_da_amostra(documento, amostra)
            (destino / f"{sha256}.png").write_bytes(conteudo)
            fontes[sha256] = fonte
    return fontes


def _dentro_de_tmp(caminho: Path, raiz: Path) -> bool:
    return caminho.resolve().is_relative_to((raiz / "tmp").resolve())


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relatório do modelo de desenho sobre PDFs.")
    parser.add_argument("--raiz", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--amostras-imagem", type=Path, default=None)
    parser.add_argument("--raiz-repositorio", type=Path, default=Path.cwd())
    parser.add_argument("--processos", type=int, default=1)
    argumentos = parser.parse_args(argv)
    if argumentos.processos < 1:
        parser.error("--processos precisa ser >= 1")
    return argumentos


def _medir_com_tabela(pdf: Path, tabela: TabelaGlifos) -> dict[str, Any]:
    try:
        return medir_pdf(pdf, tabela)
    except Exception as erro:  # um PDF ruim não pode derrubar o relatório inteiro
        return {"sha256": _sha256_do_arquivo(pdf), "erro": type(erro).__name__}


_TABELA_DO_PROCESSO: TabelaGlifos | None = None


def _iniciar_processo() -> None:
    global _TABELA_DO_PROCESSO
    _TABELA_DO_PROCESSO = carregar_tabela_glifos()


def _medir_no_processo(pdf: Path) -> dict[str, Any]:
    if _TABELA_DO_PROCESSO is None:
        raise RuntimeError("processo do pool sem tabela de glifos")
    return _medir_com_tabela(pdf, _TABELA_DO_PROCESSO)


def _medir_todos(
    pdfs: Sequence[Path], tabela: TabelaGlifos, processos: int
) -> list[dict[str, Any]]:
    if processos <= 1 or len(pdfs) <= 1:
        return [_medir_com_tabela(pdf, tabela) for pdf in pdfs]
    with ProcessPoolExecutor(
        max_workers=min(processos, len(pdfs)), initializer=_iniciar_processo
    ) as pool:
        return list(pool.map(_medir_no_processo, pdfs))


def _registrar_amostras(
    pdf: Path, medicao: dict[str, Any], amostras_dir: Path, fontes: dict[str, str]
) -> None:
    try:
        gravar_amostras(pdf, medicao["amostras"], amostras_dir, fontes)
    except Exception as erro:  # falha nas amostras não descarta a medição
        medicao["erro_amostras"] = type(erro).__name__
    for amostra in medicao["amostras"]:
        if amostra["sha256"] in fontes:
            amostra["fonte_pixels"] = fontes[amostra["sha256"]]


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = _argumentos(argv)
    raiz_repositorio: Path = argumentos.raiz_repositorio
    for opcao, caminho in (
        ("--saida", argumentos.saida),
        ("--amostras-imagem", argumentos.amostras_imagem),
    ):
        if caminho is not None and not _dentro_de_tmp(caminho, raiz_repositorio):
            print(f"{opcao} precisa ficar dentro de tmp/ da raiz do repositorio", file=sys.stderr)
            return 2
    if not argumentos.raiz.is_dir():
        print("--raiz inexistente", file=sys.stderr)
        return 2
    pdfs = sorted(
        p for p in argumentos.raiz.rglob("*") if p.suffix.lower() == ".pdf" and p.is_file()
    )
    try:
        tabela = carregar_tabela_glifos()
    except ValueError as erro:  # tabela empacotada ausente ou inválida
        print(str(erro), file=sys.stderr)
        return 2
    fontes: dict[str, str] = {}
    brutas = _medir_todos(pdfs, tabela, argumentos.processos)
    if argumentos.amostras_imagem is not None:
        for pdf, medicao in zip(pdfs, brutas, strict=True):
            if "erro" not in medicao:
                _registrar_amostras(pdf, medicao, argumentos.amostras_imagem, fontes)
    medicoes = sorted(brutas, key=lambda medicao: str(medicao["sha256"]))
    validas = [m for m in medicoes if "erro" not in m]
    relatorio = {
        "resumo": {
            "pdfs": len(medicoes),
            "erros": len(medicoes) - len(validas),
            "familias": dict(sorted(Counter(m["familia"] for m in validas).items())),
            "imagens": {c: sum(m["imagens"][c] for m in validas) for c in _CLASSES},
        },
        "pdfs": medicoes,
    }
    argumentos.saida.parent.mkdir(parents=True, exist_ok=True)
    argumentos.saida.write_text(json.dumps(relatorio, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
