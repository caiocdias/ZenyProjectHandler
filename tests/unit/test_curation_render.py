from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable, Sequence
from itertools import pairwise
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from PIL import Image
from scripts.curation_render import (
    ARQUIVO_INDICE,
    DPI_DETALHE_PADRAO,
    ESQUEMA_INDICE,
    JOBS_MAXIMO,
    LIMIAR_BRANCO,
    ParametrosRender,
    caminho_indice,
    carregar_indice,
    grade_eixo,
    main,
    medir_ocupacao,
    renderizar,
)
from scripts.curation_round import (
    RodadaError,
    carregar_checkpoint,
    carregar_rodada,
    diretorio_pdf,
    hash_diretorio,
    iniciar_rodada,
    transicionar,
)
from tests.pdf_fixtures import create_network_benchmark_pdf

from zeny_project_handler.application import visual_occupancy

AGORA = "2026-10-15T12:00:00+00:00"
Registro = dict[str, Any]
# Parâmetros pequenos para testes rápidos: 1 pt = 1 px, tiles de 256 px, sobreposição de 38 px.
RAPIDO = ParametrosRender(lado_tile_px=256, sobreposicao=0.15, dpi_detalhe=72)
CAMADAS = ("base", "annotation")


def _retangulo(x0: float, y0: float, x1: float, y1: float) -> pymupdf.Rect:
    return pymupdf.Rect(x0, y0, x1, y1)  # type: ignore[no-untyped-call]


def _pdf(caminho: Path, desenhar: Callable[[pymupdf.Page], None], *, rotacao: int = 0) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=595, height=842)
        desenhar(pagina)
        if rotacao:
            pagina.set_rotation(rotacao)
        documento.save(caminho)
    return caminho


def _branca(_: pymupdf.Page) -> None:
    return None


def _segmento(pagina: pymupdf.Page) -> None:
    pagina.draw_line((300, 400), (340, 400), color=(0, 0, 0), width=1)


def _marcador(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(_retangulo(100, 50, 110, 60), color=(0, 0, 0), fill=(0, 0, 0))


def _anotacao(pagina: pymupdf.Page) -> None:
    pagina.add_rect_annot(_retangulo(400, 600, 440, 640))


def _rodada(tmp_path: Path, pdfs: dict[str, Callable[[Path], Path]], nome: str = "rodada") -> Path:
    corpus = tmp_path / f"corpus-{nome}"
    for relativo, criar in pdfs.items():
        criar(corpus / relativo)
    rodada = tmp_path / nome
    iniciar_rodada(
        rodada, corpus, concorrencia=3, raiz_repositorio=tmp_path / "sem-git", agora=AGORA
    )
    return rodada


def _unico(tmp_path: Path, criar: Callable[[Path], Path], nome: str = "rodada") -> tuple[Path, str]:
    rodada = _rodada(tmp_path, {"a.pdf": criar}, nome)
    return rodada, str(carregar_rodada(rodada)["pdfs"][0]["pdf_id"])


def _indice(rodada: Path, pdf_id: str) -> Registro:
    dados = json.loads(
        (diretorio_pdf(rodada, pdf_id) / "render" / ARQUIVO_INDICE).read_text("utf-8")
    )
    assert isinstance(dados, dict)
    return dados


def _tiles(indice: Registro, camada: str, pagina: int = 1) -> list[Registro]:
    return [t for t in indice["tiles"] if t["camada"] == camada and t["pagina"] == pagina]


def _a_revisar(indice: Registro, camada: str) -> list[Registro]:
    return [t for t in _tiles(indice, camada) if t["estado"] == "a_revisar"]


def _contem(bbox: Sequence[float], x0: float, y0: float, x1: float, y1: float) -> bool:
    return bbox[0] <= x0 and bbox[1] <= y0 and x1 <= bbox[2] and y1 <= bbox[3]


def _intervalos_cobrem(intervalos: list[tuple[float, float]], fim: float) -> bool:
    alcance = 0.0
    for inicio, termino in sorted(intervalos):
        if inicio > alcance:
            return False
        alcance = max(alcance, termino)
    return alcance >= fim


def _pixels_escuros(caminho: Path) -> tuple[int, int, int, int]:
    with Image.open(caminho) as imagem:
        mascara = imagem.convert("L").point(lambda valor: 255 if valor < 128 else 0)
        caixa = mascara.getbbox()
    assert caixa is not None
    return caixa


# --- grade --------------------------------------------------------------------------------


def test_grade_eixo_usa_passo_fixo_e_trunca_o_ultimo_tile() -> None:
    assert grade_eixo(842, 256, 0.15) == [(0, 256), (218, 474), (436, 692), (654, 842)]
    assert grade_eixo(256, 256, 0.15) == [(0, 256)]
    assert grade_eixo(100, 256, 0.15) == [(0, 100)]
    assert grade_eixo(1654, 1536, 0.15) == [(0, 1536), (1306, 1654)]
    assert grade_eixo(500, 200, 0.0) == [(0, 200), (200, 400), (400, 500)]


@pytest.mark.parametrize("comprimento", [1, 255, 257, 1000, 1653, 2339, 4961])
@pytest.mark.parametrize("sobreposicao", [0.0, 0.15, 0.3, 0.5])
def test_grade_eixo_cobre_tudo_com_sobreposicao_exata(
    comprimento: int, sobreposicao: float
) -> None:
    lado = 256
    segmentos = grade_eixo(comprimento, lado, sobreposicao)
    assert segmentos[0][0] == 0
    assert segmentos[-1][1] == comprimento
    assert all(0 < fim - inicio <= lado for inicio, fim in segmentos)
    for (_, fim), (inicio, _) in pairwise(segmentos):
        assert fim - inicio == round(lado * sobreposicao)
    # O último tile sempre acrescenta pixels novos: nenhum tile fica contido no anterior.
    for (_, anterior), (_, atual) in pairwise(segmentos):
        assert atual > anterior


def test_grade_eixo_recusa_dimensoes_invalidas() -> None:
    with pytest.raises(ValueError):
        grade_eixo(0, 256, 0.15)
    with pytest.raises(ValueError):
        grade_eixo(100, 0, 0.15)


# --- ocupação -----------------------------------------------------------------------------


def test_limiar_branco_igual_ao_do_mapa_de_ocupacao_visual() -> None:
    assert visual_occupancy._LIMIAR_BRANCO == LIMIAR_BRANCO


def test_medir_ocupacao_conta_pixels_nao_brancos_pelo_canal_mais_escuro() -> None:
    imagem = Image.new("RGB", (10, 10), (255, 255, 255))
    assert medir_ocupacao(imagem) == (0, 0.0)
    imagem.putpixel((0, 0), (255, 255, LIMIAR_BRANCO - 1))
    imagem.putpixel((1, 0), (LIMIAR_BRANCO, LIMIAR_BRANCO, 255))
    imagem.putpixel((2, 0), (0, 0, 0))
    assert medir_ocupacao(imagem) == (2, 0.02)


# --- critérios de aceite ------------------------------------------------------------------


@pytest.mark.parametrize("sobreposicao", [0.15, 0.3])
def test_tiles_cobrem_pagina_a4_com_sobreposicao_pedida_nas_duas_camadas(
    tmp_path: Path, sobreposicao: float
) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    parametros = ParametrosRender(sobreposicao=sobreposicao)
    resultado = renderizar(rodada, [pdf_id], parametros=parametros, jobs=1)
    assert resultado["totais"]["sucesso"] == 1
    indice = _indice(rodada, pdf_id)
    pagina = indice["paginas"][0]
    largura, altura = pagina["detalhe_px"]
    dpi = DPI_DETALHE_PADRAO
    assert (largura, altura) == (round(595 * dpi / 72), round(842 * dpi / 72))
    esperado = round(1536 * sobreposicao)
    for camada in CAMADAS:
        tiles = _tiles(indice, camada)
        colunas = sorted({tuple(t["bbox_px"][0::2]) for t in tiles})
        linhas = sorted({tuple(t["bbox_px"][1::2]) for t in tiles})
        assert len(tiles) == len(colunas) * len(linhas) >= 4
        for eixo, total in ((colunas, largura), (linhas, altura)):
            assert eixo[0][0] == 0 and eixo[-1][1] == total
            for (_, fim), (inicio, _) in pairwise(eixo):
                assert abs((fim - inicio) - esperado) <= 1
        for tile in tiles:
            x0, y0, x1, y1 = tile["bbox_px"]
            assert tile["bbox"] == [x0 / largura, y0 / altura, x1 / largura, y1 / altura]
            assert (tile["largura_px"], tile["altura_px"]) == (x1 - x0, y1 - y0)
            assert max(tile["largura_px"], tile["altura_px"]) <= 1536
            assert tile["dpi"] == DPI_DETALHE_PADRAO
            caminho = rodada / tile["arquivo"]
            with Image.open(caminho) as imagem:
                assert imagem.size == (x1 - x0, y1 - y0)
        normalizadas_x = [(t["bbox"][0], t["bbox"][2]) for t in tiles]
        normalizadas_y = [(t["bbox"][1], t["bbox"][3]) for t in tiles]
        assert _intervalos_cobrem(normalizadas_x, 1.0)
        assert _intervalos_cobrem(normalizadas_y, 1.0)
        assert min(t["bbox"][0] for t in tiles) == 0.0
        assert max(t["bbox"][3] for t in tiles) == 1.0


def test_visoes_gerais_tem_lado_maior_limitado_e_bbox_da_pagina_inteira(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    renderizar(rodada, [pdf_id], parametros=ParametrosRender(lado_tile_px=512), jobs=1)
    indice = _indice(rodada, pdf_id)
    visoes = {visao["camada"]: visao for visao in indice["visoes"]}
    assert set(visoes) == set(CAMADAS)
    assert visoes["base"]["arquivo"].endswith("/render/p001-visao-base.png")
    assert visoes["annotation"]["arquivo"].endswith("/render/p001-visao-anotada.png")
    for visao in visoes.values():
        assert visao["bbox"] == [0.0, 0.0, 1.0, 1.0]
        assert max(visao["largura_px"], visao["altura_px"]) <= 512
        assert max(visao["largura_px"], visao["altura_px"]) >= 500
        with Image.open(rodada / visao["arquivo"]) as imagem:
            assert imagem.size == (visao["largura_px"], visao["altura_px"])
        assert (
            visao["sha256"] == hashlib.sha256((rodada / visao["arquivo"]).read_bytes()).hexdigest()
        )


def test_pagina_branca_nao_gera_tile_a_revisar_mas_mantem_os_png(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _branca))
    resultado = renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    indice = _indice(rodada, pdf_id)
    assert indice["tiles"]
    for tile in indice["tiles"]:
        assert tile["estado"] == "descartado_branco"
        assert tile["ocupacao"] == 0.0 and tile["pixels_ocupados"] == 0
        assert (rodada / tile["arquivo"]).is_file()
    assert indice["totais"]["a_revisar"] == 0
    assert indice["totais"]["descartado_branco"] == len(indice["tiles"])
    assert resultado["pdfs"][0]["a_revisar"] == 0


def test_segmento_unico_gera_tile_a_revisar_que_o_contem(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    indice = _indice(rodada, pdf_id)
    segmento = (300 / 595, 399.5 / 842, 340 / 595, 400.5 / 842)
    for camada in CAMADAS:
        revisar = _a_revisar(indice, camada)
        assert len(revisar) >= 1
        assert any(_contem(tile["bbox"], *segmento) for tile in revisar)
        for tile in revisar:
            assert tile["ocupacao"] > 0
        # Todo tile que intersecta o segmento fica para revisão; nenhum com conteúdo é descartado
        for tile in _tiles(indice, camada):
            x0, y0, x1, y1 = tile["bbox_px"]
            intersecta = x0 < 340 and x1 > 300 and y0 < 401 and y1 > 399
            assert (tile["estado"] == "a_revisar") == intersecta


def test_traco_de_um_pixel_nao_e_descartado_pelo_limiar_padrao(tmp_path: Path) -> None:
    def ponto(pagina: pymupdf.Page) -> None:
        pagina.draw_line((100, 100), (103, 100), color=(0, 0, 0), width=0.5)

    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, ponto))
    renderizar(rodada, [pdf_id], parametros=ParametrosRender(dpi_detalhe=72), jobs=1)
    indice = _indice(rodada, pdf_id)
    assert _a_revisar(indice, "base")


def test_limiar_de_ocupacao_configuravel_descarta_tiles_esparsos(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    parametros = ParametrosRender(lado_tile_px=256, dpi_detalhe=72, limiar_ocupacao=0.01)
    renderizar(rodada, [pdf_id], parametros=parametros, jobs=1)
    indice = _indice(rodada, pdf_id)
    assert indice["parametros"]["limiar_ocupacao"] == 0.01
    assert indice["totais"]["a_revisar"] == 0


def test_camada_anotada_inclui_anotacoes_e_base_nao(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _anotacao))
    renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    indice = _indice(rodada, pdf_id)
    assert indice["paginas"][0]["anotacoes"] == 1
    assert indice["paginas"][0]["camada_anotada_igual_base"] is False
    assert not _a_revisar(indice, "base")
    revisar = _a_revisar(indice, "annotation")
    assert any(
        _contem(tile["bbox"], 400 / 595, 600 / 842, 440 / 595, 640 / 842) for tile in revisar
    )
    assert all(tile["arquivo"].split("/")[-1].startswith("p001-anotada-t") for tile in revisar)


def test_rotacao_90_mantem_bbox_na_pagina_exibida(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _marcador, rotacao=90))
    renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    indice = _indice(rodada, pdf_id)
    pagina = indice["paginas"][0]
    assert pagina["rotacao"] == 90
    assert (pagina["largura_pt"], pagina["altura_pt"]) == (842.0, 595.0)
    assert pagina["detalhe_px"] == [842, 595]
    # Marcador em (100,50)-(110,60) na página sem rotação; exibido em (782,100)-(792,110).
    fonte = next((tmp_path / "corpus-rodada").glob("*.pdf"))
    with pymupdf.open(fonte) as documento:  # type: ignore[no-untyped-call]
        pagina_pdf = documento[0]
        exibido = _retangulo(100, 50, 110, 60) * pagina_pdf.rotation_matrix
        largura, altura = pagina_pdf.rect.width, pagina_pdf.rect.height
    esperado = (
        exibido.x0 / largura,
        exibido.y0 / altura,
        exibido.x1 / largura,
        exibido.y1 / altura,
    )
    assert esperado == pytest.approx((782 / 842, 100 / 595, 792 / 842, 110 / 595))
    for camada in CAMADAS:
        revisar = _a_revisar(indice, camada)
        assert len(revisar) == 1
        tile = revisar[0]
        assert _contem(tile["bbox"], *esperado)
        x0, y0, x1, y1 = _pixels_escuros(rodada / tile["arquivo"])
        bx0, by0, bx1, by1 = tile["bbox"]
        escala_x = (bx1 - bx0) / tile["largura_px"]
        escala_y = (by1 - by0) / tile["altura_px"]
        medido = (
            bx0 + x0 * escala_x,
            by0 + y0 * escala_y,
            bx0 + x1 * escala_x,
            by0 + y1 * escala_y,
        )
        assert medido == pytest.approx(esperado, abs=1.5 / 595)


def test_duas_execucoes_produzem_hashes_identicos(tmp_path: Path) -> None:
    original = create_network_benchmark_pdf(tmp_path / "original.pdf")

    def criar(caminho: Path) -> Path:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, caminho)
        return caminho

    primeira, pdf_a = _unico(tmp_path, criar, "um")
    segunda, pdf_b = _unico(tmp_path, criar, "dois")
    assert pdf_a == pdf_b
    renderizar(primeira, [pdf_a], parametros=RAPIDO, jobs=1)
    renderizar(segunda, [pdf_b], parametros=RAPIDO, jobs=1)
    render_a = diretorio_pdf(primeira, pdf_a) / "render"
    render_b = diretorio_pdf(segunda, pdf_b) / "render"
    assert (render_a / ARQUIVO_INDICE).read_bytes() == (render_b / ARQUIVO_INDICE).read_bytes()
    assert hash_diretorio(render_a) == hash_diretorio(render_b)
    indice = _indice(primeira, pdf_a)
    for item in [*indice["tiles"], *indice["visoes"]]:
        assert (
            item["sha256"] == hashlib.sha256((primeira / item["arquivo"]).read_bytes()).hexdigest()
        )
    # Rerenderizar a mesma rodada antes de congelar a referência reproduz os mesmos bytes.
    antes = hash_diretorio(render_a)
    renderizar(primeira, [pdf_a], parametros=RAPIDO, jobs=1)
    assert hash_diretorio(render_a) == antes
    eventos = [
        e for e in carregar_checkpoint(primeira, pdf_a)["historico"] if e["para"] == "renderizado"
    ]
    assert len(eventos) == 2


# --- índice e checkpoint ------------------------------------------------------------------


def test_indice_tem_ids_estaveis_hash_estado_e_totais(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    indice = _indice(rodada, pdf_id)
    entrada = carregar_rodada(rodada)["pdfs"][0]
    assert indice["schema_version"] == ESQUEMA_INDICE
    assert indice["pdf_id"] == pdf_id
    assert indice["sha256_pdf"] == entrada["sha256"]
    assert indice["caminho_relativo"] == "a.pdf"
    assert indice["convencao_bbox"]["protocolo"] == "symbols-e02-v1"
    assert indice["parametros"] == {
        "dpi_detalhe": 72,
        "lado_tile_px": 256,
        "limiar_branco": LIMIAR_BRANCO,
        "limiar_ocupacao": RAPIDO.limiar_ocupacao,
        "sobreposicao": 0.15,
    }
    ids = [tile["id"] for tile in indice["tiles"]]
    assert len(ids) == len(set(ids))
    # A4 a 72 DPI com tiles de 256 px: 3 colunas por 4 linhas por camada.
    assert ids[:3] == ["p001-base-t0000", "p001-base-t0001", "p001-base-t0002"]
    assert "p001-anotada-t0302" in ids and len(ids) == 24
    for tile in indice["tiles"]:
        assert tile["arquivo"] == f"pdfs/{pdf_id}/render/{tile['id']}.png"
        assert tile["estado"] in {"a_revisar", "descartado_branco"}
        assert set(tile) >= {"linha", "coluna", "pagina", "camada", "bbox", "sha256", "ocupacao"}
    pagina = indice["paginas"][0]
    assert pagina["grade"] == {"colunas": 3, "linhas": 4, "sobreposicao_px": 38}
    assert pagina["anotacoes"] == 0 and pagina["camada_anotada_igual_base"] is True
    assert pagina["totais"]["base"] == {"a_revisar": 1, "descartado_branco": 11, "tiles": 12}
    assert pagina["totais"]["annotation"] == {"a_revisar": 1, "descartado_branco": 11, "tiles": 12}
    assert indice["totais"] == {"a_revisar": 2, "descartado_branco": 22, "paginas": 1, "tiles": 24}
    texto = (diretorio_pdf(rodada, pdf_id) / "render" / ARQUIVO_INDICE).read_text("utf-8")
    assert str(tmp_path) not in texto and "Users" not in texto and "\\" not in texto


def test_checkpoint_avanca_para_renderizado_com_hash_do_indice(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    resultado = renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    checkpoint = carregar_checkpoint(rodada, pdf_id)
    assert checkpoint["fase"] == "renderizado"
    artefatos = {item["caminho"]: item for item in checkpoint["marcos"]["renderizado"]["artefatos"]}
    indice = diretorio_pdf(rodada, pdf_id) / "render" / ARQUIVO_INDICE
    caminho_indice = f"pdfs/{pdf_id}/render/{ARQUIVO_INDICE}"
    assert artefatos[caminho_indice]["sha256"] == hashlib.sha256(indice.read_bytes()).hexdigest()
    assert artefatos[f"pdfs/{pdf_id}/render"]["tipo"] == "diretorio"
    dados = checkpoint["historico"][-1]["dados"]
    assert dados["indice"] == caminho_indice
    assert dados["totais"]["a_revisar"] == 2
    assert resultado["pdfs"][0] == {
        "a_revisar": 2,
        "descartado_branco": 22,
        "duracao_s": resultado["pdfs"][0]["duracao_s"],
        "falhas": [],
        "pdf_id": pdf_id,
        "status": "sucesso",
        "tiles": 24,
    }
    assert not [p for p in diretorio_pdf(rodada, pdf_id).iterdir() if p.name.startswith(".")]


def test_renderizar_depois_de_congelar_referencia_e_recusado_sem_tocar_render(
    tmp_path: Path,
) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    referencia = diretorio_pdf(rodada, pdf_id) / "referencia" / "referencia-v001.json"
    referencia.parent.mkdir()
    referencia.write_text("{}", encoding="utf-8")
    transicionar(rodada, pdf_id, "referencia_congelada", artefatos=[referencia], agora=AGORA)
    render = diretorio_pdf(rodada, pdf_id) / "render"
    antes = hash_diretorio(render)
    checkpoint_antes = carregar_checkpoint(rodada, pdf_id)
    resultado = renderizar(rodada, [pdf_id], parametros=ParametrosRender(dpi_detalhe=72), jobs=1)
    assert resultado["pdfs"][0]["status"] == "recusado"
    assert resultado["totais"] == {"falha": 0, "recusado": 1, "sucesso": 0}
    assert hash_diretorio(render) == antes
    assert carregar_checkpoint(rodada, pdf_id) == checkpoint_antes


def test_pdf_alterado_desde_init_falha_sem_renderizar(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    _pdf(tmp_path / "corpus-rodada" / "a.pdf", _marcador)
    resultado = renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    registro = resultado["pdfs"][0]
    assert registro["status"] == "falha"
    assert any("SHA-256" in falha for falha in registro["falhas"])
    assert not (diretorio_pdf(rodada, pdf_id) / "render").exists()
    assert carregar_checkpoint(rodada, pdf_id)["fase"] == "preparado"


def test_pdf_ilegivel_falha_isolado_e_os_demais_renderizam(tmp_path: Path) -> None:
    def corrompido(caminho: Path) -> Path:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(b"%PDF-1.7\nnao e um pdf de verdade")
        return caminho

    rodada = _rodada(
        tmp_path,
        {
            "a.pdf": lambda caminho: _pdf(caminho, _segmento),
            "b.pdf": corrompido,
            "c.pdf": lambda caminho: _pdf(caminho, _marcador),
        },
    )
    ids = [str(item["pdf_id"]) for item in carregar_rodada(rodada)["pdfs"]]
    resultado = renderizar(rodada, ids, parametros=RAPIDO, jobs=1)
    estados = {item["pdf_id"]: item["status"] for item in resultado["pdfs"]}
    assert estados == {ids[0]: "sucesso", ids[1]: "falha", ids[2]: "sucesso"}
    assert [item["pdf_id"] for item in resultado["pdfs"]] == ids
    assert carregar_checkpoint(rodada, ids[1])["fase"] == "preparado"
    assert not (diretorio_pdf(rodada, ids[1]) / "render").exists()
    assert not [p for p in diretorio_pdf(rodada, ids[1]).iterdir() if p.name.startswith(".")]


def test_jobs_em_processos_paralelos_renderizam_todos(tmp_path: Path) -> None:
    rodada = _rodada(
        tmp_path,
        {
            "a.pdf": lambda caminho: _pdf(caminho, _segmento),
            "b.pdf": lambda caminho: _pdf(caminho, _marcador),
        },
    )
    ids = [str(item["pdf_id"]) for item in carregar_rodada(rodada)["pdfs"]]
    resultado = renderizar(rodada, ids, parametros=RAPIDO, jobs=2)
    assert resultado["jobs"] == 2
    assert resultado["totais"] == {"falha": 0, "recusado": 0, "sucesso": 2}
    for pdf_id in ids:
        assert carregar_checkpoint(rodada, pdf_id)["fase"] == "renderizado"


@pytest.mark.parametrize(
    "parametros",
    [
        ParametrosRender(lado_tile_px=63),
        ParametrosRender(sobreposicao=-0.1),
        ParametrosRender(sobreposicao=0.51),
        ParametrosRender(dpi_detalhe=35),
        ParametrosRender(dpi_detalhe=1201),
        ParametrosRender(limiar_ocupacao=-0.1),
        ParametrosRender(limiar_ocupacao=1.0),
    ],
)
def test_parametros_invalidos_sao_recusados(tmp_path: Path, parametros: ParametrosRender) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _branca))
    with pytest.raises(RodadaError):
        renderizar(rodada, [pdf_id], parametros=parametros, jobs=1)
    assert carregar_checkpoint(rodada, pdf_id)["fase"] == "preparado"


@pytest.mark.parametrize("jobs", [0, JOBS_MAXIMO + 1])
def test_jobs_fora_do_intervalo_e_recusado(tmp_path: Path, jobs: int) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _branca))
    with pytest.raises(RodadaError):
        renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=jobs)


def test_carregar_indice_confere_presenca_esquema_e_pdf(tmp_path: Path) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    with pytest.raises(RodadaError, match="ausente"):
        carregar_indice(rodada, pdf_id)
    renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    assert carregar_indice(rodada, pdf_id) == _indice(rodada, pdf_id)
    arquivo = caminho_indice(rodada, pdf_id)
    assert arquivo == diretorio_pdf(rodada, pdf_id) / "render" / ARQUIVO_INDICE
    dados = _indice(rodada, pdf_id)
    arquivo.write_text(json.dumps({**dados, "pdf_id": "999-000000000000"}), encoding="utf-8")
    with pytest.raises(RodadaError, match="outro PDF"):
        carregar_indice(rodada, pdf_id)
    arquivo.write_text(json.dumps({**dados, "schema_version": "x"}), encoding="utf-8")
    with pytest.raises(RodadaError, match="esquema"):
        carregar_indice(rodada, pdf_id)


# --- CLI ----------------------------------------------------------------------------------


def test_cli_renderiza_onda_e_imprime_resumo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    argumentos = ["--rodada", str(rodada), "--onda", "1", "--lado-tile-px", "256"]
    argumentos += ["--sobreposicao", "0.15", "--dpi-detalhe", "72", "--jobs", "1"]
    assert main(argumentos) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["pdfs"][0]["pdf_id"] == pdf_id
    assert saida["pdfs"][0]["status"] == "sucesso"
    assert saida["parametros"]["dpi_detalhe"] == 72
    assert carregar_checkpoint(rodada, pdf_id)["fase"] == "renderizado"


def test_cli_retorna_erro_em_parametro_invalido_ou_falha(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada, pdf_id = _unico(tmp_path, lambda caminho: _pdf(caminho, _segmento))
    assert main(["--rodada", str(rodada), "--pdf", pdf_id, "--sobreposicao", "0.9"]) == 1
    assert "sobreposição" in capsys.readouterr().err
    assert main(["--rodada", str(rodada), "--pdf", "999-000000000000"]) == 1
    _pdf(tmp_path / "corpus-rodada" / "a.pdf", _marcador)
    assert main(["--rodada", str(rodada), "--pdf", pdf_id, "--dpi-detalhe", "72"]) == 1
    assert json.loads(capsys.readouterr().out)["totais"]["falha"] == 1
