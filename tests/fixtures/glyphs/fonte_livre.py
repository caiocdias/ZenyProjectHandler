# mypy: disable-error-code="no-untyped-call"
"""PDFs sintéticos com o mesmo texto em Helvetica Base14 nativa e convertido em contornos.

A versão em contorno vem do SVG da página nativa (`get_svg_image(text_as_path=True)`): cada
`<use>` vira um caminho preenchido na cor da linha, com todos os subcaminhos num único
`Shape.finish`, e a página resultante não tem texto nativo.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pymupdf

from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    EntradaGlifo,
    TabelaGlifos,
    carregar_tabela_glifos,
    serializar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import extrair_trechos
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import caminhos_da_pagina

ALFABETO: Final = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-()/.,="
# "." e "," lado a lado, separados por espaço, ficam longe demais para a regra de vizinhança
# (1,6 x o maior lado) e partiriam o alfabeto num trecho curto de quadro torto.
_ORDEM_DA_TABELA: Final = ALFABETO.replace(".,=", ".=,")
# Na Helvetica a maior lacuna dentro de palavra é 0,423 h ("11") e o menor espaço entre
# palavras, 0,547 h; 0,38 (o valor da tabela empacotada vazia) leria "11" como "1 1".
ESPACO_DA_FIXTURE: Final = 0.48
LARGURA: Final = 400.0
ALTURA: Final = 300.0

_SVG: Final = "{http://www.w3.org/2000/svg}"
_XLINK: Final = "{http://www.w3.org/1999/xlink}href"
_TOKEN: Final = re.compile(r"[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_MATRIZ: Final = re.compile(r"matrix\(([^)]*)\)")

Ponto = tuple[float, float]
Segmento = tuple[Ponto, ...]


@dataclass(frozen=True, slots=True)
class LinhaTexto:
    texto: str
    origem: tuple[float, float]
    tamanho: float
    rotacao: float = 0.0
    cor: tuple[float, float, float] = (0, 0, 0)


def _documento_nativo(linhas: Sequence[LinhaTexto], rotacao_pagina: int) -> Any:
    documento = pymupdf.open()
    pagina = documento.new_page(width=LARGURA, height=ALTURA)
    for linha in linhas:
        morph = None
        if linha.rotacao:
            morph = (pymupdf.Point(*linha.origem), pymupdf.Matrix(linha.rotacao))
        pagina.insert_text(
            linha.origem,
            linha.texto,
            fontsize=linha.tamanho,
            fontname="helv",
            color=linha.cor,
            morph=morph,
        )
    pagina.set_rotation(rotacao_pagina)
    return documento


def pdf_texto_nativo(
    destino: Path, linhas: Sequence[LinhaTexto], *, rotacao_pagina: int = 0
) -> Path:
    with _documento_nativo(linhas, rotacao_pagina) as documento:
        documento.save(destino)
    return destino


def _numeros(tokens: list[str], posicao: int) -> tuple[list[float], int]:
    valores: list[float] = []
    while posicao < len(tokens) and not tokens[posicao].isalpha():
        valores.append(float(tokens[posicao]))
        posicao += 1
    return valores, posicao


class _Caneta:
    """Interpreta um `d` de SVG em subcaminhos de segmentos `l` (2 pontos) e `c` (4 pontos)."""

    def __init__(self) -> None:
        self.subcaminhos: list[list[Segmento]] = []
        self.atual: Ponto = (0.0, 0.0)
        self.inicio: Ponto = (0.0, 0.0)

    def mover(self, ponto: Ponto) -> None:
        self.fechar()
        self.subcaminhos.append([])
        self.atual = self.inicio = ponto

    def linha(self, ponto: Ponto) -> None:
        self.subcaminhos[-1].append((self.atual, ponto))
        self.atual = ponto

    def curva(self, c1: Ponto, c2: Ponto, fim: Ponto) -> None:
        self.subcaminhos[-1].append((self.atual, c1, c2, fim))
        self.atual = fim

    def fechar(self) -> None:
        if self.subcaminhos and self.subcaminhos[-1] and self.atual != self.inicio:
            self.linha(self.inicio)
        self.atual = self.inicio


def _interpretar_d(d: str) -> list[list[Segmento]]:
    tokens = _TOKEN.findall(d)
    caneta = _Caneta()
    posicao = 0
    while posicao < len(tokens):
        comando = tokens[posicao]
        if comando.upper() not in "MLHVCZ" or not comando.isalpha():
            raise ValueError(f"Comando de caminho SVG não suportado: {comando!r}.")
        valores, posicao = _numeros(tokens, posicao + 1)
        _aplicar(caneta, comando, valores)
    caneta.fechar()
    return [subcaminho for subcaminho in caneta.subcaminhos if subcaminho]


def _aplicar(caneta: _Caneta, comando: str, valores: list[float]) -> None:
    relativo = comando.islower()
    tipo = comando.upper()
    if tipo == "Z":
        caneta.fechar()
        return
    passo = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6}[tipo]
    if not valores or len(valores) % passo:
        raise ValueError(f"Comando SVG {comando!r} com {len(valores)} números.")
    for i in range(0, len(valores), passo):
        x0, y0 = caneta.atual if relativo else (0.0, 0.0)
        grupo = valores[i : i + passo]
        if tipo == "H":
            caneta.linha((grupo[0] + x0, caneta.atual[1]))
        elif tipo == "V":
            caneta.linha((caneta.atual[0], grupo[0] + y0))
        elif tipo == "C":
            c1, c2, fim = ((grupo[k] + x0, grupo[k + 1] + y0) for k in (0, 2, 4))
            caneta.curva(c1, c2, fim)
        elif tipo == "M" and i == 0:
            caneta.mover((grupo[0] + x0, grupo[1] + y0))
        else:
            caneta.linha((grupo[0] + x0, grupo[1] + y0))


def _matriz(transformacao: str) -> tuple[float, ...]:
    casamento = _MATRIZ.fullmatch(transformacao.strip())
    if casamento is None:
        raise ValueError(f"Transformação SVG não suportada: {transformacao!r}.")
    valores = tuple(float(v) for v in re.split(r"[\s,]+", casamento.group(1).strip()))
    if len(valores) != 6:
        raise ValueError(f"Matriz SVG inválida: {transformacao!r}.")
    return valores


def _glifos_do_svg(
    svg: str, linhas: Sequence[LinhaTexto]
) -> list[tuple[list[list[Segmento]], int]]:
    """Subcaminhos (já na página visual) de cada `<use>` não vazio e o índice da linha dele."""
    raiz = ET.fromstring(svg)
    definicoes = {caminho.get("id"): caminho.get("d") or "" for caminho in raiz.iter(f"{_SVG}path")}
    usos = list(raiz.iter(f"{_SVG}use"))
    caracteres = [(indice, c) for indice, linha in enumerate(linhas) for c in linha.texto]
    if len(usos) != len(caracteres):
        raise ValueError(f"SVG com {len(usos)} glifos para {len(caracteres)} caracteres.")
    glifos: list[tuple[list[list[Segmento]], int]] = []
    for uso, (indice, caractere) in zip(usos, caracteres, strict=True):
        if uso.get("data-text") != caractere:
            raise ValueError(f"SVG fora de ordem: {uso.get('data-text')!r} != {caractere!r}.")
        a, b, c, d, e, f = _matriz(uso.get("transform") or "")
        subcaminhos = _interpretar_d(definicoes[(uso.get(_XLINK) or "").removeprefix("#")])
        if not subcaminhos:
            continue
        glifos.append(
            (
                [
                    [tuple((a * x + c * y + e, b * x + d * y + f) for x, y in s) for s in sub]
                    for sub in subcaminhos
                ],
                indice,
            )
        )
    return glifos


def pdf_texto_contorno(
    destino: Path, linhas: Sequence[LinhaTexto], *, rotacao_pagina: int = 0
) -> Path:
    with _documento_nativo(linhas, rotacao_pagina) as nativo:
        pagina_nativa = nativo[0]
        svg = pagina_nativa.get_svg_image(text_as_path=True)
        m = pagina_nativa.derotation_matrix
        a, b, c, d, e, f = (float(v) for v in (m.a, m.b, m.c, m.d, m.e, m.f))
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=LARGURA, height=ALTURA)
        forma = pagina.new_shape()
        for subcaminhos, indice in _glifos_do_svg(svg, linhas):
            for subcaminho in subcaminhos:
                for segmento in subcaminho:
                    pontos = [
                        pymupdf.Point(a * x + c * y + e, b * x + d * y + f) for x, y in segmento
                    ]
                    if len(pontos) == 2:
                        forma.draw_line(*pontos)
                    else:
                        forma.draw_bezier(*pontos)
            forma.finish(color=None, fill=linhas[indice].cor, width=0)
        forma.commit()
        pagina.set_rotation(rotacao_pagina)
        documento.save(destino)
    return destino


def caminhos_do_pdf(pdf: Path) -> tuple[Any, ...]:
    with pymupdf.open(pdf) as documento:
        return caminhos_da_pagina(documento[0])


def tabela_do_alfabeto(tmp: Path) -> TabelaGlifos:
    """Tabela com um glifo por caractere do `ALFABETO` em contorno, tamanho 5, rotação 0."""
    texto = " ".join(_ORDEM_DA_TABELA)
    pdf = pdf_texto_contorno(tmp / "alfabeto.pdf", [LinhaTexto(texto, (20.0, 60.0), 5.0)])
    trechos = extrair_trechos(caminhos_do_pdf(pdf))
    if len(trechos) != 1 or len(trechos[0].glifos) != len(ALFABETO):
        raise ValueError(f"Alfabeto lido em {len(trechos)} trechos; esperado um só.")
    entradas = []
    for caractere, glifo in zip(_ORDEM_DA_TABELA, trechos[0].glifos, strict=True):
        if glifo.assinatura is None:
            raise ValueError(f"Glifo {caractere!r} sem assinatura.")
        entradas.append(EntradaGlifo(f"g{ord(caractere):04d}", caractere, glifo.assinatura))
    arquivo = tmp / "tabela-alfabeto.json"
    arquivo.write_text(
        serializar_tabela_glifos(
            tolerancia=0.08,
            margem_ambiguidade=0.02,
            espaco=ESPACO_DA_FIXTURE,
            quebra=1.5,
            glifos=entradas,
        ),
        encoding="utf-8",
    )
    return carregar_tabela_glifos(arquivo)
