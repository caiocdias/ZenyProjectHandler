# mypy: disable-error-code="no-untyped-call"
"""Extração PyMuPDF do modelo de desenho sobre PDFs sintéticos gerados no teste."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import LinhaTexto, pdf_texto_contorno, tabela_do_alfabeto

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model import glyph_text
from zeny_project_handler.adapters.analysis.drawing_model.cache import (
    JsonDrawingModelCache,
    chave_modelo_desenho,
)
from zeny_project_handler.adapters.analysis.drawing_model.family import LIMIAR_FORMAS_GLIFO
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    VERSAO_MODELO_DESENHO,
    Circulo,
    ModeloDesenho,
    PaginaModelo,
    Polilinha,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    extrair_modelo_desenho,
    impressao_estrutural,
    obter_modelo_desenho,
)

_XREF = re.compile(r"(?<!\d)(\d+)\s+\d+\s+R")


def _png_vermelho() -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 2, 2), False)
    pixmap.clear_with(0xFF0000)
    return bytes(pixmap.tobytes("png"))


def _salvar(documento: Any, caminho: Path) -> Path:
    documento.save(caminho)
    return caminho


def _pagina(modelo: ModeloDesenho, indice: int = 0) -> PaginaModelo:
    return modelo.paginas[indice]


def _nativos(pagina: PaginaModelo) -> list[str]:
    return [t.texto for t in pagina.textos if t.origem == "nativo"]


def _proximo(a: tuple[float, ...], b: tuple[float, ...], tolerancia: float = 0.01) -> bool:
    return len(a) == len(b) and all(abs(x - y) <= tolerancia for x, y in zip(a, b, strict=True))


def test_extrai_texto_nativo_com_posicao_rotacao_e_altura(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        pagina.insert_text((50, 100), "P1", fontsize=12)
        pagina.insert_text((150, 150), "MT", fontsize=9, rotate=90)
        pdf = _salvar(documento, tmp_path / "texto.pdf")

    modelo = extrair_modelo_desenho(pdf)

    assert modelo.versao == VERSAO_MODELO_DESENHO
    assert modelo.documento_sha256 == hashlib.sha256(pdf.read_bytes()).hexdigest()
    textos = {t.texto: t for t in _pagina(modelo).textos}
    p1, mt = textos["P1"], textos["MT"]
    assert p1.origem == "nativo" and mt.origem == "nativo"
    assert p1.rotacao == pytest.approx(0.0)
    assert p1.altura == pytest.approx(12.0)
    assert p1.fonte == "Helvetica"
    assert p1.camada == ""
    x0, y0, x1, y1 = p1.bbox
    assert x0 == pytest.approx(50.0, abs=0.5) and y1 == pytest.approx(100.0, abs=4.0)
    assert x1 > x0 and y1 > y0 and y0 < 100.0
    # Texto subindo (rotate=90): no espaço visual com y para baixo, sentido horário, é 270°.
    assert mt.rotacao == pytest.approx(270.0)
    assert mt.altura == pytest.approx(9.0)
    mx0, my0, mx1, my1 = mt.bbox
    assert my1 == pytest.approx(150.0, abs=0.5) and mx0 < 150.0 < mx1
    assert my1 - my0 > mx1 - mx0  # texto vertical: caixa mais alta que larga


def test_freetext_nao_vira_texto_nativo(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        pagina.insert_text((20, 40), "POSTE", fontsize=10)
        pagina.add_freetext_annot(pymupdf.Rect(100, 120, 200, 150), "NOTA")
        pdf = _salvar(documento, tmp_path / "freetext.pdf")

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    assert _nativos(pagina_modelo) == ["POSTE"]
    assert all(t.texto != "NOTA" for t in pagina_modelo.textos)


def test_extrai_texto_shx_uma_vez(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        shx = pagina.add_rect_annot(pymupdf.Rect(40, 120, 90, 145))
        shx.set_info(title="AutoCAD SHX Text", content="N3")
        shx.update()
        revisao = pagina.add_rect_annot(pymupdf.Rect(150, 120, 200, 145))
        revisao.set_info(title="Revisor", content="N4")
        revisao.update()
        pdf = _salvar(documento, tmp_path / "shx.pdf")

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    shx_textos = [t for t in pagina_modelo.textos if t.origem == "shx"]
    assert [t.texto for t in shx_textos] == ["N3"]
    assert _proximo(shx_textos[0].bbox, (40.0, 120.0, 90.0, 145.0), 1.0)
    assert "N3" not in _nativos(pagina_modelo)
    assert all(t.texto != "N4" for t in pagina_modelo.textos)


def test_segmentos_fragmentados_do_pdf_viram_uma_polilinha(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        for inicio, fim in (((10, 50), (60, 50)), ((60, 50), (110, 50)), ((110, 50), (110, 90))):
            pagina.draw_line(inicio, fim, color=(0, 0.5, 0), width=1.5)
        pdf = _salvar(documento, tmp_path / "fragmentos.pdf")

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    assert len(pagina_modelo.caminhos) == 3
    assert all(c.tipo == "traco" for c in pagina_modelo.caminhos)
    assert [c.ordem for c in pagina_modelo.caminhos] == [0, 1, 2]
    polilinhas = [p for p in pagina_modelo.primitivas if isinstance(p, Polilinha)]
    assert len(polilinhas) == 1
    assert polilinhas[0].origens == (0, 1, 2)
    assert set(polilinhas[0].pontos) == {(10.0, 50.0), (110.0, 50.0), (110.0, 90.0)}
    estilo = polilinhas[0].estilo
    assert _proximo(estilo.cor or (), (0.0, 0.5, 0.0)) and estilo.espessura == pytest.approx(1.5)
    assert estilo.preenchimento is None and estilo.camada == ""


def test_circulo_desenhado_com_beziers_vira_circulo(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        pagina.draw_circle((150, 60), 10, color=(0, 0, 1))
        pdf = _salvar(documento, tmp_path / "circulo.pdf")

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    (caminho,) = pagina_modelo.caminhos
    assert [item.tipo for sub in caminho.subcaminhos for item in sub] == ["c"] * 4
    circulos = [p for p in pagina_modelo.primitivas if isinstance(p, Circulo)]
    assert len(circulos) == 1
    assert _proximo(circulos[0].centro, (150.0, 60.0), 0.05)
    assert circulos[0].raio == pytest.approx(10.0, abs=0.05)
    assert not [p for p in pagina_modelo.primitivas if isinstance(p, Polilinha)]


def test_glifo_preenchido_sobrevive_nos_caminhos(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        forma = pagina.new_shape()
        forma.draw_bezier((100, 100), (112, 92), (114, 104), (104, 108))
        forma.draw_bezier((104, 108), (93, 112), (99, 125), (112, 120))
        forma.draw_line((112, 120), (111, 123))
        forma.draw_bezier((111, 123), (95, 128), (88, 112), (101, 105))
        forma.draw_bezier((101, 105), (109, 101), (107, 96), (100, 100))
        forma.finish(color=None, fill=(0, 0, 0), closePath=True)
        forma.commit()
        pdf = _salvar(documento, tmp_path / "glifo.pdf")

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    (caminho,) = pagina_modelo.caminhos
    assert caminho.tipo == "preenchimento"
    assert caminho.estilo.preenchimento == (0.0, 0.0, 0.0) and caminho.estilo.cor is None
    tipos = [item.tipo for sub in caminho.subcaminhos for item in sub]
    assert tipos.count("c") == 4
    assert not [p for p in pagina_modelo.primitivas if isinstance(p, Polilinha)]
    assert any(0 in g.indices_caminhos for g in pagina_modelo.grupos)


def test_preenchimentos_adjacentes_nao_se_fundem(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        pagina.draw_rect(pymupdf.Rect(50, 50, 60, 60), color=None, fill=(1, 0, 0))
        pagina.draw_rect(pymupdf.Rect(60, 50, 70, 60), color=None, fill=(1, 0, 0))
        pdf = _salvar(documento, tmp_path / "adjacentes.pdf")

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    assert len(pagina_modelo.caminhos) == 2
    for caminho in pagina_modelo.caminhos:
        assert caminho.tipo == "preenchimento"
        (subcaminho,) = caminho.subcaminhos
        assert [item.tipo for item in subcaminho] == ["l"] * 4
        assert subcaminho[0].pontos[0] == subcaminho[-1].pontos[1]  # retângulo fechado
    assert not [p for p in pagina_modelo.primitivas if isinstance(p, Polilinha)]


def test_retangulo_tracado_vira_polilinha_fechada_e_subcaminhos_separam(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        pagina.draw_rect(pymupdf.Rect(10, 10, 30, 20), color=(0, 0, 0))
        forma = pagina.new_shape()
        forma.draw_polyline([(100, 10), (110, 10), (110, 20)])
        forma.draw_polyline([(150, 10), (160, 10)])
        forma.finish(color=(0, 0, 0), closePath=False)
        forma.commit()
        pdf = _salvar(documento, tmp_path / "subcaminhos.pdf")

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    retangulo, dupla = pagina_modelo.caminhos
    assert len(retangulo.subcaminhos) == 1 and len(retangulo.subcaminhos[0]) == 4
    assert [len(sub) for sub in dupla.subcaminhos] == [2, 1]
    fechadas = [p for p in pagina_modelo.primitivas if isinstance(p, Polilinha) and p.fechada]
    assert len(fechadas) == 1 and set(fechadas[0].pontos) == {
        (10.0, 10.0),
        (30.0, 10.0),
        (30.0, 20.0),
        (10.0, 20.0),
    }


def test_camada_ocg_vai_para_o_estilo_e_para_o_texto(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        ocg = documento.add_ocg("P", on=True)
        pagina.draw_line((10, 10), (100, 10), oc=ocg)
        pagina.draw_line((10, 30), (100, 30))
        pagina.insert_text((50, 80), "P1 U3(1)", fontsize=10, oc=ocg)
        pagina.insert_text((50, 120), "LIVRE", fontsize=10)
        pdf = _salvar(documento, tmp_path / "ocg.pdf")

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    assert [c.estilo.camada for c in pagina_modelo.caminhos] == ["P", ""]
    camadas = {
        p.pontos[0][1]: p.estilo.camada
        for p in pagina_modelo.primitivas
        if isinstance(p, Polilinha)
    }
    assert camadas == {10.0: "P", 30.0: ""}
    textos = {t.texto: t.camada for t in pagina_modelo.textos}
    assert textos == {"P1 U3(1)": "P", "LIVRE": ""}


@pytest.mark.parametrize("rotacao", [90, 270])
def test_extrai_modelo_em_pagina_rotacionada(tmp_path: Path, rotacao: int) -> None:
    largura, altura = 300.0, 200.0
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=largura, height=altura)
        pagina.draw_line((10, 20), (60, 20), color=(0, 0, 0))
        pagina.draw_circle((150, 60), 10, color=(0, 0, 1))
        pagina.insert_text((200, 150), "P7", fontsize=10)
        pagina.insert_image(pymupdf.Rect(240, 20, 260, 40), stream=_png_vermelho())
        shx = pagina.add_rect_annot(pymupdf.Rect(40, 120, 90, 145))
        shx.set_info(title="AutoCAD SHX Text", content="N3")
        shx.update()
        pagina.set_rotation(rotacao)
        pdf = _salvar(documento, tmp_path / f"rotacao-{rotacao}.pdf")

    def visual(x: float, y: float) -> tuple[float, float]:
        return (altura - y, x) if rotacao == 90 else (y, largura - x)

    def caixa_visual(x0: float, y0: float, x1: float, y1: float) -> tuple[float, ...]:
        (ax, ay), (bx, by) = visual(x0, y0), visual(x1, y1)
        return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    assert (pagina_modelo.largura, pagina_modelo.altura) == (altura, largura)
    assert pagina_modelo.diagnosticos == ()
    linha = next(p for p in pagina_modelo.primitivas if isinstance(p, Polilinha))
    assert set(linha.pontos) == {visual(10, 20), visual(60, 20)}
    circulo = next(p for p in pagina_modelo.primitivas if isinstance(p, Circulo))
    assert _proximo(circulo.centro, visual(150, 60), 0.05)
    texto = next(t for t in pagina_modelo.textos if t.texto == "P7")
    assert texto.rotacao == pytest.approx(float(rotacao))
    tx0, ty0, tx1, ty1 = texto.bbox
    assert 0 <= tx0 < tx1 <= altura and 0 <= ty0 < ty1 <= largura
    esperado_x, esperado_y = visual(200, 150)
    assert tx0 - 1 <= esperado_x <= tx1 + 1 and ty0 - 1 <= esperado_y <= ty1 + 1
    shx_texto = next(t for t in pagina_modelo.textos if t.origem == "shx")
    assert _proximo(shx_texto.bbox, caixa_visual(40, 120, 90, 145), 1.0)
    (imagem,) = pagina_modelo.imagens
    assert _proximo(imagem.bbox, caixa_visual(240, 20, 260, 40), 0.5)


def test_modelo_de_pagina_vazia_e_multipagina(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        documento.new_page(width=300, height=200)
        cheia = documento.new_page(width=400, height=250)
        cheia.insert_text((20, 40), "P2", fontsize=10)
        cheia.draw_line((10, 100), (90, 100))
        pdf = _salvar(documento, tmp_path / "multipagina.pdf")

    modelo = extrair_modelo_desenho(pdf)

    vazia, cheia_modelo = modelo.paginas
    assert (vazia.indice, cheia_modelo.indice) == (0, 1)
    assert (vazia.largura, vazia.altura) == (300.0, 200.0)
    assert (cheia_modelo.largura, cheia_modelo.altura) == (400.0, 250.0)
    assert vazia.caminhos == () and vazia.textos == () and vazia.primitivas == ()
    assert vazia.grupos == () and vazia.imagens == () and vazia.diagnosticos == ()
    assert _nativos(cheia_modelo) == ["P2"] and len(cheia_modelo.caminhos) == 1


def _pdf_com_glifos(caminho: Path, quantidade: int) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=600, height=400)
        forma = pagina.new_shape()
        for indice in range(quantidade):
            x, y = 10 + (indice % 50) * 8, 10 + (indice // 50) * 8
            forma.draw_rect(pymupdf.Rect(x, y, x + 3, y + 4))
            forma.finish(color=None, fill=(0, 0, 0))
        forma.commit()
        documento.set_metadata({"producer": "Microsoft: Print To PDF"})
        return _salvar(documento, caminho)


def test_fixture_de_cada_familia_e_reconhecida(tmp_path: Path) -> None:
    def com_produtor(nome: str, produtor: str) -> Path:
        with pymupdf.open() as documento:
            documento.new_page(width=300, height=200).insert_text((20, 40), "P1")
            documento.set_metadata({"producer": produtor})
            return _salvar(documento, tmp_path / nome)

    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        pagina.draw_line((10, 10), (90, 10), oc=documento.add_ocg("POSTES"))
        ocg = _salvar(documento, tmp_path / "ocg.pdf")
    with pymupdf.open() as documento:
        anotacao = documento.new_page(width=300, height=200).add_rect_annot((40, 40, 90, 60))
        anotacao.set_info(title="AutoCAD SHX Text", content="N3")
        anotacao.update()
        shx = _salvar(documento, tmp_path / "shx.pdf")
    casos = {
        com_produtor("itext.pdf", "iText 5.5.13"): "itext",
        com_produtor("gs.pdf", "GPL Ghostscript 9.54"): "ghostscript",
        com_produtor("plot.pdf", "AutoCAD PDF (General Documentation).pc3"): "autocad",
        ocg: "autocad",
        shx: "autocad",
        _pdf_com_glifos(tmp_path / "eo.pdf", 400): "electric_office_print",
        _pdf_com_glifos(tmp_path / "print.pdf", 10): "generico",
        com_produtor("libre.pdf", "LibreOffice 7"): "generico",
    }

    familias = {pdf.name: extrair_modelo_desenho(pdf).familia.familia for pdf in casos}

    assert familias == {pdf.name: familia for pdf, familia in casos.items()}


def test_impressao_estrutural_conta_sinais_do_documento(tmp_path: Path) -> None:
    pdf = _pdf_com_glifos(tmp_path / "glifos.pdf", LIMIAR_FORMAS_GLIFO)
    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        pagina.insert_text((20, 380), "P1 P2", fontsize=10)
        pagina.insert_image(pymupdf.Rect(500, 300, 520, 320), stream=_png_vermelho())
        anotacao = pagina.add_rect_annot((400, 300, 450, 320))
        anotacao.set_info(title="AutoCAD SHX Text", content="N3")
        anotacao.update()
        documento.add_ocg("REDE")
        documento.set_metadata({"producer": "Microsoft: Print To PDF", "creator": "EO"})
        impressao = impressao_estrutural(documento)

    assert impressao.produtor == "Microsoft: Print To PDF" and impressao.criador == "EO"
    assert impressao.nomes_ocg == ("REDE",)
    assert impressao.spans_texto_nativo == 1
    assert impressao.formas_glifo == LIMIAR_FORMAS_GLIFO
    assert impressao.anotacoes_shx == 1
    assert impressao.imagens == 1


def test_imagem_de_anotacao_e_marcada(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        pagina.insert_image(pymupdf.Rect(10, 10, 30, 30), stream=_png_vermelho())
        auxiliar = documento.new_page(width=50, height=50)
        xref_imagem = auxiliar.insert_image(auxiliar.rect, stream=_png_vermelho())
        pagina = documento[0]
        carimbo = pagina.add_stamp_annot(pymupdf.Rect(100, 50, 200, 100), stamp=0)
        aparencia = _XREF.search(str(documento.xref_get_key(carimbo.xref, "AP")[1]))
        assert aparencia is not None
        xref_aparencia = int(aparencia.group(1))
        documento.xref_set_key(xref_aparencia, "Resources/XObject/ImAp", f"{xref_imagem} 0 R")
        conteudo = bytes(documento.xref_stream(xref_aparencia) or b"")
        documento.update_stream(xref_aparencia, conteudo + b"\nq 12 0 0 12 2 2 cm /ImAp Do Q\n")
        documento.delete_page(1)
        pdf = _salvar(documento, tmp_path / "carimbo.pdf")

    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))

    da_pagina = [i for i in pagina_modelo.imagens if not i.de_anotacao]
    da_anotacao = [i for i in pagina_modelo.imagens if i.de_anotacao]
    assert len(da_pagina) == 1 and len(da_anotacao) == 1
    assert _proximo(da_pagina[0].bbox, (10.0, 10.0, 30.0, 30.0), 0.5)
    assert (da_anotacao[0].largura_px, da_anotacao[0].altura_px) == (2, 2)
    assert da_anotacao[0].bbox[0] >= 99.0 and da_anotacao[0].bbox[2] <= 201.0
    # Mesma imagem na página e no carimbo: a identidade de conteúdo coincide.
    assert da_pagina[0].sha256 == da_anotacao[0].sha256
    assert re.fullmatch(r"[0-9a-f]{64}", da_pagina[0].sha256)


def test_falha_de_uma_fonte_vira_diagnostico_da_pagina(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pymupdf.open() as documento:
        for _ in range(2):
            pagina = documento.new_page(width=300, height=200)
            pagina.insert_text((20, 40), "P1", fontsize=10)
            pagina.draw_line((10, 100), (90, 100))
        pdf = _salvar(documento, tmp_path / "falha.pdf")
    original = pymupdf_drawing_model._textos_nativos

    def falha_na_primeira(pagina: Any) -> Any:
        if pagina.number == 0:
            raise RuntimeError("fonte corrompida")
        return original(pagina)

    monkeypatch.setattr(pymupdf_drawing_model, "_textos_nativos", falha_na_primeira)

    primeira, segunda = extrair_modelo_desenho(pdf).paginas

    assert primeira.diagnosticos == ("modelo.textos_nativos_falhou",)
    assert primeira.textos == ()
    assert len(primeira.caminhos) == 1 and len(primeira.primitivas) == 1
    assert segunda.diagnosticos == ()
    assert _nativos(segunda) == ["P1"]


def test_falha_dos_caminhos_esvazia_so_os_derivados(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        pagina.insert_text((20, 40), "P1", fontsize=10)
        pagina.draw_line((10, 100), (90, 100))
        pdf = _salvar(documento, tmp_path / "falha-caminhos.pdf")

    def falha(pagina: Any) -> Any:
        raise RuntimeError("operador inválido")

    monkeypatch.setattr(pymupdf_drawing_model, "_desenhos", falha)

    (pagina_modelo,) = extrair_modelo_desenho(pdf).paginas

    assert pagina_modelo.diagnosticos == ("modelo.caminhos_falhou",)
    assert pagina_modelo.caminhos == ()
    assert pagina_modelo.primitivas == () and pagina_modelo.grupos == ()
    assert _nativos(pagina_modelo) == ["P1"]


def test_texto_com_matriz_gigante_nao_explode_o_casamento_de_camada(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        ocg = documento.add_ocg("P", on=True)
        pagina.insert_text((50, 80), "P1", fontsize=10, fontname="helv", oc=ocg)
        xref_conteudo = pagina.get_contents()[-1]
        conteudo = bytes(documento.xref_stream(xref_conteudo) or b"")
        gigante = b"\nBT /helv 1 Tf 100000 0 0 100000 0 0 Tm (AAAA) Tj ET\n" * 3
        documento.update_stream(xref_conteudo, conteudo + gigante)
        pdf = _salvar(documento, tmp_path / "matriz-gigante.pdf")

    inicio = time.perf_counter()
    pagina_modelo = _pagina(extrair_modelo_desenho(pdf))
    duracao = time.perf_counter() - inicio

    assert duracao < 5.0
    assert pagina_modelo.diagnosticos == ()
    camadas = {t.texto: t.camada for t in pagina_modelo.textos}
    assert camadas["P1"] == "P"


def test_desenho_com_itens_invalidos_sai_sozinho_e_o_vizinho_fica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def preenchido(x: float, itens: Any) -> dict[str, Any]:
        return {
            "type": "f",
            "items": itens,
            "fill": (0.0, 0.0, 0.0),
            "color": None,
            "width": 0.0,
            "rect": pymupdf.Rect(x, 10, x + 2, 12),
            "layer": "",
        }

    desenhos = [
        preenchido(10, [("l", "nao e ponto", None)]),
        preenchido(20, [("c", pymupdf.Point(20, 10))]),
        preenchido(30, [("l", pymupdf.Point(30, 10), pymupdf.Point(32, 10))]),
    ]
    pdf = tmp_path / "vazio.pdf"
    with pymupdf.open() as documento:
        documento.new_page(width=100, height=100)
        documento.save(pdf)
    monkeypatch.setattr(pymupdf.Page, "get_drawings", lambda _pagina, extended=False: desenhos)

    with pymupdf.open(pdf) as documento:
        (caminho,) = pymupdf_drawing_model.caminhos_da_pagina(documento[0])

    assert caminho.ordem == 2
    assert caminho.subcaminhos[0][0].pontos == ((30.0, 10.0), (32.0, 10.0))


# --- texto de glifo (modelo v2) -------------------------------------------------------------


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-modelo"))


def test_modelo_traz_texto_de_glifo_e_versao_v2(tmp_path: Path, tabela: TabelaGlifos) -> None:
    linhas = [LinhaTexto("P7 U4(1)", (40.0, 60.0), 5.0), LinhaTexto("11-300", (40.0, 120.0), 5.0)]
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", linhas)
    cache = JsonDrawingModelCache(tmp_path / "cache")

    modelo = extrair_modelo_desenho(pdf, tabela)

    assert VERSAO_MODELO_DESENHO == "modelo-desenho-v2"
    assert modelo.versao == "modelo-desenho-v2"
    (pagina,) = modelo.paginas
    assert sorted(t.texto for t in pagina.textos) == ["11-300", "P7 U4(1)"]
    for texto in pagina.textos:
        assert texto.origem == "glifo"
        assert texto.fonte == f"{tabela.versao}:{tabela.sha256[:12]}"
        assert texto.camada == ""
        assert texto.rotacao == pytest.approx(0.0, abs=1.0) or texto.rotacao == pytest.approx(
            360.0, abs=1.0
        )
        assert 3.0 < texto.altura < 5.0
    assert pagina.diagnosticos == ()
    assert extrair_modelo_desenho(pdf).paginas[0].textos == ()
    assert extrair_modelo_desenho(pdf, None).paginas[0].textos == ()

    primeiro = obter_modelo_desenho(pdf, cache, tabela)
    assert primeiro == modelo
    assert obter_modelo_desenho(pdf, cache, tabela) == modelo
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    chave = chave_modelo_desenho(sha, f"pymupdf-{pymupdf.VersionBind}:glifos-{tabela.sha256}")
    assert cache.obter(chave) == modelo

    outra = replace(tabela, sha256="0" * 64)
    obter_modelo_desenho(pdf, cache, outra)
    sem_tabela = obter_modelo_desenho(pdf, cache)
    assert sem_tabela.paginas[0].textos == ()
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 3


def test_modelo_diagnostica_glifo_desconhecido_e_pagina_limitada(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("11-300", (40.0, 60.0), 5.0)])
    sem_tres = replace(tabela, glifos=tuple(g for g in tabela.glifos if g.caractere != "3"))

    (desconhecido,) = extrair_modelo_desenho(pdf, sem_tres).paginas
    monkeypatch.setattr(glyph_text, "LIMITE_GLIFOS_PAGINA", 3)
    (limitada,) = extrair_modelo_desenho(pdf, tabela).paginas

    assert desconhecido.textos == () and desconhecido.diagnosticos == (
        "modelo.glifos_desconhecidos",
    )
    assert limitada.textos == () and limitada.diagnosticos == ("modelo.glifos_limitados",)


def test_falha_na_leitura_de_glifos_vira_diagnostico_de_fonte(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("11-300", (40.0, 60.0), 5.0)])

    def _falha(*_args: object) -> object:
        raise RuntimeError("quebrou")

    monkeypatch.setattr(pymupdf_drawing_model, "ler_texto_glifos", _falha)
    (pagina,) = extrair_modelo_desenho(pdf, tabela).paginas

    assert pagina.diagnosticos == ("modelo.glifos_falhou",)
    assert pagina.caminhos and pagina.textos == ()


def test_ultimo_desenho_descartado_envenena_o_trecho_no_modelo(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("11-300", (40.0, 60.0), 5.0)])
    original = pymupdf_drawing_model._desenhos

    def _desenhos(pagina: Any) -> list[dict[str, Any]]:
        desenhos = original(pagina)
        ultimo = dict(desenhos[-1])
        ultimo["items"] = [("l", pymupdf.Point(float("nan"), 0.0), pymupdf.Point(1.0, 1.0))]
        return [*desenhos[:-1], ultimo]

    monkeypatch.setattr(pymupdf_drawing_model, "_desenhos", _desenhos)

    (pagina,) = extrair_modelo_desenho(pdf, tabela).paginas

    assert len(pagina.caminhos) == 5
    assert pagina.textos == ()
    assert pagina.diagnosticos == ("modelo.glifos_desconhecidos",)
