"""DXF de depuração do modelo de desenho de uma página de PDF.

Uso:
    python -m scripts.drawing_model_dxf PDF --saida ARQUIVO.dxf [--pagina N] [--cache DIR]
        [--raiz-repositorio DIR]

Grava um DXF com uma camada por ``Estilo.camada``/``TextoModelo.camada`` (vazia vira ``0``;
nomes inválidos são saneados), um ``TEXT`` por texto, uma ``LWPOLYLINE`` por polilinha,
``CIRCLE``, ``ARC`` e, na camada ``GRUPOS_CANDIDATOS``, o retângulo de cada grupo candidato.
O modelo usa y para baixo e ângulos no sentido horário visual; o DXF inverte y e converte os
ângulos. O texto é posicionado no centro da caixa (alinhamento médio), que serve também aos
textos rotacionados. ``--saida`` e ``--cache`` precisam ficar em ``tmp/`` da raiz do repositório
(padrão: diretório atual). O DXF não traz caminho absoluto nem nome do PDF.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment
from ezdxf.filemanagement import new as novo_documento
from ezdxf.layouts.layout import Modelspace

from zeny_project_handler.adapters.analysis.drawing_model.cache import JsonDrawingModelCache
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Circulo,
    ModeloDesenho,
    PaginaModelo,
    Polilinha,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import obter_modelo_desenho

CAMADA_GRUPOS = "GRUPOS_CANDIDATOS"
CAMADA_PADRAO = "0"
_INVALIDOS_EM_CAMADA = re.compile(r'[<>/\\":;?*|=`\x00-\x1f]')
_TAMANHO_MAXIMO_CAMADA = 255


def nome_de_camada(nome: str) -> str:
    saneado = _INVALIDOS_EM_CAMADA.sub("_", nome).strip()[:_TAMANHO_MAXIMO_CAMADA]
    return saneado or CAMADA_PADRAO


def exportar_dxf(modelo: ModeloDesenho, pagina: int, destino: Path) -> None:
    alvo = next((p for p in modelo.paginas if p.indice == pagina), None)
    if alvo is None:
        raise ValueError(f"pagina {pagina} inexistente no modelo")
    documento = novo_documento("R2010")
    espaco = documento.modelspace()
    for texto in alvo.textos:
        _adicionar_texto(documento, espaco, alvo, texto)
    for primitiva in alvo.primitivas:
        _adicionar_primitiva(documento, espaco, alvo, primitiva)
    for grupo in alvo.grupos:
        x0, y0, x1, y1 = grupo.bbox
        pontos = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        espaco.add_lwpolyline(
            [_ponto(alvo, p) for p in pontos],
            close=True,
            dxfattribs={"layer": _camada(documento, CAMADA_GRUPOS)},
        )
    destino.parent.mkdir(parents=True, exist_ok=True)
    documento.saveas(destino)


def _camada(documento: Drawing, nome: str) -> str:
    saneado = nome_de_camada(nome)
    if saneado not in documento.layers:
        documento.layers.add(saneado)
    return saneado


def _ponto(pagina: PaginaModelo, ponto: tuple[float, float]) -> tuple[float, float]:
    return (ponto[0], pagina.altura - ponto[1])


def _adicionar_texto(
    documento: Drawing, espaco: Modelspace, pagina: PaginaModelo, texto: TextoModelo
) -> None:
    x0, y0, x1, y1 = texto.bbox
    entidade = espaco.add_text(
        texto.texto,
        height=texto.altura if texto.altura > 0 else 1.0,
        rotation=-texto.rotacao,
        dxfattribs={"layer": _camada(documento, texto.camada)},
    )
    entidade.set_placement(
        _ponto(pagina, ((x0 + x1) / 2, (y0 + y1) / 2)), align=TextEntityAlignment.MIDDLE_CENTER
    )


def _adicionar_primitiva(
    documento: Drawing,
    espaco: Modelspace,
    pagina: PaginaModelo,
    primitiva: Polilinha | Circulo | Arco,
) -> None:
    atributos = {"layer": _camada(documento, primitiva.estilo.camada)}
    if isinstance(primitiva, Polilinha):
        espaco.add_lwpolyline(
            [_ponto(pagina, p) for p in primitiva.pontos],
            close=primitiva.fechada,
            dxfattribs=atributos,
        )
    elif isinstance(primitiva, Circulo):
        espaco.add_circle(_ponto(pagina, primitiva.centro), primitiva.raio, dxfattribs=atributos)
    else:
        # Horário visual com y para baixo vira anti-horário com y para cima: [a, b] -> [-b, -a].
        espaco.add_arc(
            _ponto(pagina, primitiva.centro),
            primitiva.raio,
            (-primitiva.angulo_final) % 360.0,
            (-primitiva.angulo_inicial) % 360.0,
            dxfattribs=atributos,
        )


def _dentro_de_tmp(caminho: Path, raiz: Path) -> bool:
    return caminho.resolve().is_relative_to((raiz / "tmp").resolve())


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Exporta o modelo de desenho de uma página em DXF."
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--pagina", type=int, default=0)
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--raiz-repositorio", type=Path, default=Path.cwd())
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = _argumentos(argv)
    raiz: Path = argumentos.raiz_repositorio
    for opcao, caminho in (("--saida", argumentos.saida), ("--cache", argumentos.cache)):
        if caminho is not None and not _dentro_de_tmp(caminho, raiz):
            print(f"{opcao} precisa ficar dentro de tmp/ da raiz do repositorio", file=sys.stderr)
            return 2
    if not argumentos.pdf.is_file():
        print("PDF inexistente", file=sys.stderr)
        return 2
    cache = JsonDrawingModelCache(argumentos.cache) if argumentos.cache is not None else None
    modelo = obter_modelo_desenho(argumentos.pdf, cache)
    try:
        exportar_dxf(modelo, argumentos.pagina, argumentos.saida)
    except ValueError as erro:
        print(str(erro), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
