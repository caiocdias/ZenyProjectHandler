"""Renderização e triagem de tiles da curadoria: visão geral, tiles com sobreposição e índice.

Uso:
    python -m scripts.curation_render --rodada DIR (--onda K | --pdf ID ...)
        [--lado-tile-px 1536] [--sobreposicao 0.15] [--dpi-detalhe 400]
        [--limiar-ocupacao 0.000001] [--jobs N]

Para cada página de cada PDF selecionado, grava em ``pdfs/ID/render/``:

- ``pNNN-visao-base.png`` e ``pNNN-visao-anotada.png``: a página inteira com lado maior limitado
  a ``--lado-tile-px``;
- ``pNNN-base-tLLCC.png`` e ``pNNN-anotada-tLLCC.png``: tiles de detalhe renderizados a
  ``--dpi-detalhe`` numa grade de passo fixo (linha ``LL``, coluna ``CC``) que cobre a página
  inteira; vizinhos se sobrepõem em ``round(lado * sobreposicao)`` pixels e o último tile de
  cada eixo é truncado na borda da página;
- ``indice-tiles.json``: id estável, página, camada, bbox normalizada na página exibida (mesma
  convenção do avaliador ``symbols-e02-v1``), DPI, dimensões, SHA-256, ocupação e estado de
  cada tile, com totais por página e camada.

A camada ``base`` é renderizada sem anotações e a camada ``annotation`` com elas (nomes de camada
do avaliador; nos arquivos, ``base`` e ``anotada``). Um tile cuja fração de pixels não brancos
(canal mais escuro abaixo de ``LIMIAR_BRANCO``, o mesmo critério do mapa de ocupação visual do
servidor) não passa de ``--limiar-ocupacao`` é marcado ``descartado_branco`` sem apagar o PNG;
os demais ficam ``a_revisar``. O índice não tem horários nem caminhos absolutos: duas
renderizações do mesmo PDF com os mesmos parâmetros produzem os mesmos bytes. Ao terminar, o
checkpoint do PDF avança para ``renderizado``; a renderização é recusada depois que a referência
foi congelada (os tiles são a base dela).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import tempfile
import uuid
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, NamedTuple

import pymupdf
from PIL import Image, ImageChops
from PIL import __version__ as versao_pillow

from scripts.curation_round import (
    RodadaError,
    TransicaoInvalidaError,
    caminho_pdf_fonte,
    carregar_checkpoint,
    carregar_rodada,
    diretorio_pdf,
    escrever_json_atomico,
    json_canonico,
    ler_json,
    selecionar_pdfs,
    transicionar,
    validar_transicao,
)

ESQUEMA_INDICE = "curadoria-indice-tiles-v1"
DIRETORIO_RENDER = "render"
ARQUIVO_INDICE = "indice-tiles.json"
# Mesmo limiar de branco de ``zeny_project_handler.application.visual_occupancy``.
LIMIAR_BRANCO = 248
LADO_TILE_PADRAO = 1536
LADO_TILE_MINIMO = 64
LADO_TILE_MAXIMO = 8192
SOBREPOSICAO_PADRAO = 0.15
SOBREPOSICAO_MAXIMA = 0.5
# Símbolos de rede em A4/A3 têm 10 a 25 px a 200 dpi; 400 dpi os deixa legíveis na leitura visual.
DPI_DETALHE_PADRAO = 400
DPI_MINIMO = 36
DPI_MAXIMO = 1200
# Conservador: só tiles com no máximo ~2 pixels não brancos em 1536 x 1536 são descartados.
LIMIAR_OCUPACAO_PADRAO = 0.000001
JOBS_PADRAO = 3
JOBS_MAXIMO = 5
GRADE_MAXIMA = 99
ESTADO_REVISAR = "a_revisar"
ESTADO_DESCARTADO = "descartado_branco"
CONTADORES = ("a_revisar", "descartado_branco", "tiles")
CONVENCAO_BBOX = {
    "protocolo": "symbols-e02-v1",
    "espaco": "página exibida (rotação aplicada), origem no canto superior esquerdo",
    "formato": "[x0, y0, x1, y1] normalizados em [0,1]; x0 <= x1, y0 <= y1",
    "origem_pixels": "bbox_px na renderização de detalhe da página inteira (detalhe_px)",
}

Registro = dict[str, Any]


class Camada(NamedTuple):
    nome: str
    rotulo: str
    anotacoes: bool


CAMADAS = (Camada("base", "base", False), Camada("annotation", "anotada", True))


@dataclass(frozen=True, slots=True)
class ParametrosRender:
    lado_tile_px: int = LADO_TILE_PADRAO
    sobreposicao: float = SOBREPOSICAO_PADRAO
    dpi_detalhe: int = DPI_DETALHE_PADRAO
    limiar_ocupacao: float = LIMIAR_OCUPACAO_PADRAO

    def validar(self) -> None:
        if not LADO_TILE_MINIMO <= self.lado_tile_px <= LADO_TILE_MAXIMO:
            raise RodadaError(
                f"lado do tile deve estar entre {LADO_TILE_MINIMO} e {LADO_TILE_MAXIMO} px"
            )
        if not 0.0 <= self.sobreposicao <= SOBREPOSICAO_MAXIMA:
            raise RodadaError(f"sobreposição deve estar entre 0 e {SOBREPOSICAO_MAXIMA}")
        if not DPI_MINIMO <= self.dpi_detalhe <= DPI_MAXIMO:
            raise RodadaError(f"DPI de detalhe deve estar entre {DPI_MINIMO} e {DPI_MAXIMO}")
        if not 0.0 <= self.limiar_ocupacao < 1.0:
            raise RodadaError("limiar de ocupação deve estar em [0, 1)")

    def registro(self) -> Registro:
        return {**asdict(self), "limiar_branco": LIMIAR_BRANCO}


# --- grade e ocupação ---------------------------------------------------------------------


def grade_eixo(comprimento_px: int, lado_px: int, sobreposicao: float) -> list[tuple[int, int]]:
    """Intervalos ``[inicio, fim)`` de passo fixo que cobrem ``[0, comprimento_px)``.

    Vizinhos se sobrepõem em ``round(lado_px * sobreposicao)`` pixels; o último intervalo é
    truncado na borda e sempre acrescenta pixels que o anterior não cobre.
    """
    sobreposicao_px = round(lado_px * sobreposicao)
    passo = lado_px - sobreposicao_px
    if comprimento_px < 1 or lado_px < 1 or passo < 1:
        raise ValueError("grade requer comprimento, lado e passo positivos")
    intervalos: list[tuple[int, int]] = []
    inicio = 0
    while True:
        fim = min(inicio + lado_px, comprimento_px)
        intervalos.append((inicio, fim))
        if fim >= comprimento_px:
            return intervalos
        inicio += passo


def medir_ocupacao(imagem: Image.Image) -> tuple[int, float]:
    """Pixels cujo canal mais escuro fica abaixo de ``LIMIAR_BRANCO`` e a fração que ocupam."""
    rgb = imagem.convert("RGB")
    vermelho, verde, azul = rgb.split()
    mais_escuro = ImageChops.darker(ImageChops.darker(vermelho, verde), azul)
    ocupados = sum(mais_escuro.histogram()[:LIMIAR_BRANCO])
    return ocupados, ocupados / (rgb.width * rgb.height)


# --- renderização -------------------------------------------------------------------------


def _png(imagem: Image.Image, destino: Path) -> Registro:
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG", compress_level=6)
    conteudo = buffer.getvalue()
    destino.write_bytes(conteudo)
    return {"bytes": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest()}


def _imagem(pagina: pymupdf.Page, zoom: float, anotacoes: bool) -> Image.Image:
    matriz = pymupdf.Matrix(zoom, zoom)  # type: ignore[no-untyped-call]
    pixmap = pagina.get_pixmap(matrix=matriz, annots=anotacoes, alpha=False)
    imagem = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    del pixmap
    return imagem


class _Pagina(NamedTuple):
    numero: int
    largura_px: int
    altura_px: int
    colunas: list[tuple[int, int]]
    linhas: list[tuple[int, int]]


def _visao(
    pagina: pymupdf.Page, numero: int, camada: Camada, parametros: ParametrosRender, destino: Path
) -> Registro:
    maior_lado = max(pagina.rect.width, pagina.rect.height)
    # (lado - 1) evita que o arredondamento para pixels inteiros passe do lado pedido.
    zoom = min((parametros.lado_tile_px - 1) / maior_lado, parametros.dpi_detalhe / 72)
    imagem = _imagem(pagina, zoom, camada.anotacoes)
    nome = f"p{numero:03d}-visao-{camada.rotulo}"
    return {
        "altura_px": imagem.height,
        "arquivo": f"{nome}.png",
        "bbox": [0.0, 0.0, 1.0, 1.0],
        "camada": camada.nome,
        "dpi": round(zoom * 72, 4),
        "id": nome,
        "largura_px": imagem.width,
        "pagina": numero,
        **_png(imagem, destino / f"{nome}.png"),
    }


def _tile(
    imagem: Image.Image,
    pagina: _Pagina,
    camada: Camada,
    posicao: tuple[int, int],
    parametros: ParametrosRender,
    destino: Path,
) -> Registro:
    linha, coluna = posicao
    x0, x1 = pagina.colunas[coluna]
    y0, y1 = pagina.linhas[linha]
    recorte = imagem.crop((x0, y0, x1, y1))
    ocupados, ocupacao = medir_ocupacao(recorte)
    nome = f"p{pagina.numero:03d}-{camada.rotulo}-t{linha:02d}{coluna:02d}"
    estado = ESTADO_DESCARTADO if ocupacao <= parametros.limiar_ocupacao else ESTADO_REVISAR
    return {
        "altura_px": y1 - y0,
        "arquivo": f"{nome}.png",
        "bbox": [
            x0 / pagina.largura_px,
            y0 / pagina.altura_px,
            x1 / pagina.largura_px,
            y1 / pagina.altura_px,
        ],
        "bbox_px": [x0, y0, x1, y1],
        "camada": camada.nome,
        "coluna": coluna,
        "dpi": parametros.dpi_detalhe,
        "estado": estado,
        "id": nome,
        "largura_px": x1 - x0,
        "linha": linha,
        "ocupacao": ocupacao,
        "pagina": pagina.numero,
        "pixels_ocupados": ocupados,
        **_png(recorte, destino / f"{nome}.png"),
    }


def _contagem(tiles: Sequence[Registro]) -> Registro:
    revisar = sum(1 for tile in tiles if tile["estado"] == ESTADO_REVISAR)
    return {"a_revisar": revisar, "descartado_branco": len(tiles) - revisar, "tiles": len(tiles)}


def _renderizar_pagina(
    pagina: pymupdf.Page, numero: int, parametros: ParametrosRender, destino: Path
) -> tuple[Registro, list[Registro], list[Registro]]:
    zoom = parametros.dpi_detalhe / 72
    visoes: list[Registro] = []
    tiles: list[Registro] = []
    totais: Registro = {}
    sha_por_camada: dict[str, list[str]] = {}
    geometria: _Pagina | None = None
    for camada in CAMADAS:
        visoes.append(_visao(pagina, numero, camada, parametros, destino))
        imagem = _imagem(pagina, zoom, camada.anotacoes)
        if geometria is None:
            lado, fracao = parametros.lado_tile_px, parametros.sobreposicao
            geometria = _Pagina(
                numero,
                imagem.width,
                imagem.height,
                grade_eixo(imagem.width, lado, fracao),
                grade_eixo(imagem.height, lado, fracao),
            )
            if max(len(geometria.colunas), len(geometria.linhas)) > GRADE_MAXIMA:
                raise RodadaError(
                    f"página {numero} exige mais de {GRADE_MAXIMA} tiles por eixo; "
                    "reduza --dpi-detalhe ou aumente --lado-tile-px"
                )
        if (imagem.width, imagem.height) != (geometria.largura_px, geometria.altura_px):
            raise RodadaError(f"página {numero}: camadas renderizadas com dimensões diferentes")
        da_camada = [
            _tile(imagem, geometria, camada, (linha, coluna), parametros, destino)
            for linha in range(len(geometria.linhas))
            for coluna in range(len(geometria.colunas))
        ]
        tiles.extend(da_camada)
        totais[camada.nome] = _contagem(da_camada)
        sha_por_camada[camada.nome] = [tile["sha256"] for tile in da_camada]
    assert geometria is not None
    registro = {
        "altura_pt": float(pagina.rect.height),
        "anotacoes": len(list(pagina.annots())),  # type: ignore[no-untyped-call]
        "camada_anotada_igual_base": sha_por_camada["base"] == sha_por_camada["annotation"],
        "detalhe_px": [geometria.largura_px, geometria.altura_px],
        "grade": {
            "colunas": len(geometria.colunas),
            "linhas": len(geometria.linhas),
            "sobreposicao_px": round(parametros.lado_tile_px * parametros.sobreposicao),
        },
        "largura_pt": float(pagina.rect.width),
        "pagina": numero,
        "rotacao": int(pagina.rotation),
        "totais": totais,
        "widgets": len(list(pagina.widgets())),  # type: ignore[no-untyped-call]
    }
    return registro, visoes, tiles


def gerar_indice(
    conteudo_pdf: bytes,
    destino: Path,
    parametros: ParametrosRender,
    *,
    pdf_id: str,
    sha256_pdf: str,
    caminho_relativo: str,
    prefixo: str,
) -> Registro:
    """Renderiza todas as páginas em ``destino`` e devolve o índice (sem gravá-lo).

    ``prefixo`` é o caminho, relativo à rodada, em que ``destino`` será publicado; os campos
    ``arquivo`` do índice começam por ele.
    """
    paginas: list[Registro] = []
    visoes: list[Registro] = []
    tiles: list[Registro] = []
    documento: Any = pymupdf.open(stream=conteudo_pdf, filetype="pdf")  # type: ignore[no-untyped-call]
    with documento:
        for indice, pagina in enumerate(documento, start=1):
            registro, da_pagina_visoes, da_pagina_tiles = _renderizar_pagina(
                pagina, indice, parametros, destino
            )
            paginas.append(registro)
            visoes.extend(da_pagina_visoes)
            tiles.extend(da_pagina_tiles)
    if not paginas:
        raise RodadaError(f"PDF sem páginas: {caminho_relativo}")
    for item in (*visoes, *tiles):
        item["arquivo"] = f"{prefixo}/{item['arquivo']}"
    contagem = _contagem(tiles)
    return {
        "caminho_relativo": caminho_relativo,
        "convencao_bbox": dict(CONVENCAO_BBOX),
        "paginas": paginas,
        "parametros": parametros.registro(),
        "pdf_id": pdf_id,
        "renderizador": {
            "mupdf": pymupdf.VersionFitz,
            "pillow": versao_pillow,
            "pymupdf": pymupdf.VersionBind,
        },
        "schema_version": ESQUEMA_INDICE,
        "sha256_pdf": sha256_pdf,
        "tiles": tiles,
        "totais": {**contagem, "paginas": len(paginas)},
        "visoes": visoes,
    }


# --- PDF da rodada ------------------------------------------------------------------------


def caminho_indice(rodada_dir: Path, pdf_id: str) -> Path:
    return diretorio_pdf(rodada_dir, pdf_id) / DIRETORIO_RENDER / ARQUIVO_INDICE


def carregar_indice(rodada_dir: Path, pdf_id: str) -> Registro:
    """Índice de tiles vigente de um PDF, conferido contra o esquema e o ID."""
    arquivo = caminho_indice(rodada_dir, pdf_id)
    if not arquivo.is_file():
        raise RodadaError(f"índice de tiles ausente para {pdf_id}; rode curation_render")
    dados = ler_json(arquivo)
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_INDICE:
        raise RodadaError(f"índice de tiles com esquema desconhecido: {pdf_id}")
    if dados.get("pdf_id") != pdf_id:
        raise RodadaError(f"índice de tiles de outro PDF em {pdf_id}")
    return dados


def _publicar(novo: Path, final: Path) -> None:
    """Troca ``final`` por ``novo``; em falha, o diretório anterior é restaurado."""
    antigo: Path | None = None
    if final.exists():
        antigo = final.with_name(f".{final.name}-antigo-{uuid.uuid4().hex}")
        final.rename(antigo)
    try:
        novo.rename(final)
    except OSError:
        if antigo is not None:
            antigo.rename(final)
        raise
    if antigo is not None:
        shutil.rmtree(antigo, ignore_errors=True)


def _renderizar_validado(
    rodada_dir: Path, pdf_id: str, checkpoint: Registro, parametros: ParametrosRender
) -> Registro:
    relativo = str(checkpoint["caminho_relativo"])
    fonte = caminho_pdf_fonte(rodada_dir, pdf_id)
    if not fonte.is_file():
        raise RodadaError(f"PDF fonte ausente: {relativo}")
    conteudo = fonte.read_bytes()
    if hashlib.sha256(conteudo).hexdigest() != checkpoint["sha256"]:
        raise RodadaError(f"SHA-256 do PDF fonte difere do registrado no init: {relativo}")
    pdf_dir = diretorio_pdf(rodada_dir, pdf_id)
    final = pdf_dir / DIRETORIO_RENDER
    prefixo = f"pdfs/{pdf_id}/{DIRETORIO_RENDER}"
    temporario = Path(tempfile.mkdtemp(prefix=f".{DIRETORIO_RENDER}-", dir=pdf_dir))
    try:
        indice = gerar_indice(
            conteudo,
            temporario,
            parametros,
            pdf_id=pdf_id,
            sha256_pdf=str(checkpoint["sha256"]),
            caminho_relativo=relativo,
            prefixo=prefixo,
        )
        escrever_json_atomico(temporario / ARQUIVO_INDICE, indice)
        # Revalida logo antes de publicar: a referência pode ter sido congelada no intervalo.
        validar_transicao(carregar_checkpoint(rodada_dir, pdf_id), "renderizado")
        _publicar(temporario, final)
    finally:
        shutil.rmtree(temporario, ignore_errors=True)
    transicionar(
        rodada_dir,
        pdf_id,
        "renderizado",
        artefatos=[final / ARQUIVO_INDICE, final],
        dados={
            "indice": f"{prefixo}/{ARQUIVO_INDICE}",
            "parametros": parametros.registro(),
            "totais": indice["totais"],
        },
    )
    return dict(indice["totais"])


def renderizar_pdf(rodada_dir: Path, pdf_id: str, parametros: ParametrosRender) -> Registro:
    """Renderiza um PDF da rodada; recusa e falhas ficam registradas, nunca propagadas."""
    inicio = perf_counter()
    registro: Registro = {
        "a_revisar": 0,
        "descartado_branco": 0,
        "falhas": [],
        "pdf_id": pdf_id,
        "status": "sucesso",
        "tiles": 0,
    }
    try:
        checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
        validar_transicao(checkpoint, "renderizado")
    except TransicaoInvalidaError as erro:
        registro.update(status="recusado", falhas=[str(erro)])
    except Exception as erro:
        registro.update(status="falha", falhas=[f"{type(erro).__name__}: {erro}"])
    else:
        try:
            totais = _renderizar_validado(Path(rodada_dir), pdf_id, checkpoint, parametros)
            registro.update({chave: totais[chave] for chave in CONTADORES})
        except Exception as erro:
            registro.update(status="falha", falhas=[f"{type(erro).__name__}: {erro}"])
    registro["duracao_s"] = round(perf_counter() - inicio, 3)
    return registro


def _falha_de_processo(pdf_id: str, erro: BaseException) -> Registro:
    return {
        "a_revisar": 0,
        "descartado_branco": 0,
        "duracao_s": 0.0,
        "falhas": [f"{type(erro).__name__}: {erro}"],
        "pdf_id": pdf_id,
        "status": "falha",
        "tiles": 0,
    }


def renderizar(
    rodada_dir: Path,
    pdf_ids: Sequence[str],
    *,
    parametros: ParametrosRender | None = None,
    jobs: int = JOBS_PADRAO,
) -> Registro:
    """Renderiza os PDFs pedidos em até ``jobs`` processos; a falha de um não para os demais."""
    efetivos = parametros or ParametrosRender()
    efetivos.validar()
    if not 1 <= jobs <= JOBS_MAXIMO:
        raise RodadaError(f"--jobs deve estar entre 1 e {JOBS_MAXIMO}")
    rodada = Path(rodada_dir).resolve()
    carregar_rodada(rodada)
    if jobs == 1 or len(pdf_ids) <= 1:
        resultados = [renderizar_pdf(rodada, pdf_id, efetivos) for pdf_id in pdf_ids]
    else:
        # PyMuPDF não é seguro entre threads: cada PDF é renderizado em um processo.
        with ProcessPoolExecutor(max_workers=min(jobs, len(pdf_ids))) as pool:
            futuros = [pool.submit(renderizar_pdf, rodada, pdf_id, efetivos) for pdf_id in pdf_ids]
            resultados = []
            for pdf_id, futuro in zip(pdf_ids, futuros, strict=True):
                try:
                    resultados.append(futuro.result())
                except Exception as erro:
                    resultados.append(_falha_de_processo(pdf_id, erro))
    totais = {"falha": 0, "recusado": 0, "sucesso": 0}
    for resultado in resultados:
        totais[resultado["status"]] += 1
    return {
        "jobs": jobs,
        "parametros": efetivos.registro(),
        "pdfs": resultados,
        "totais": totais,
    }


# --- CLI ----------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rodada", type=Path, required=True)
    selecao = parser.add_mutually_exclusive_group(required=True)
    selecao.add_argument("--onda", type=int)
    selecao.add_argument("--pdf", dest="pdfs", nargs="+", metavar="ID")
    parser.add_argument("--lado-tile-px", type=int, default=LADO_TILE_PADRAO)
    parser.add_argument("--sobreposicao", type=float, default=SOBREPOSICAO_PADRAO)
    parser.add_argument("--dpi-detalhe", type=int, default=DPI_DETALHE_PADRAO)
    parser.add_argument(
        "--limiar-ocupacao",
        type=float,
        default=LIMIAR_OCUPACAO_PADRAO,
        help="tile com fração de pixels não brancos <= limiar fica descartado_branco",
    )
    parser.add_argument("--jobs", type=int, default=JOBS_PADRAO)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    parametros = ParametrosRender(
        lado_tile_px=args.lado_tile_px,
        sobreposicao=args.sobreposicao,
        dpi_detalhe=args.dpi_detalhe,
        limiar_ocupacao=args.limiar_ocupacao,
    )
    try:
        parametros.validar()
        pdf_ids = selecionar_pdfs(args.rodada, onda=args.onda, pdf_ids=args.pdfs or ())
        resultado = renderizar(args.rodada, pdf_ids, parametros=parametros, jobs=args.jobs)
    except RodadaError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    print(json_canonico(resultado), end="")
    return 0 if resultado["totais"]["sucesso"] == len(resultado["pdfs"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
