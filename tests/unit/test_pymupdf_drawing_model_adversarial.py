# mypy: disable-error-code="no-untyped-call"
"""Testes adversariais da extração PyMuPDF do modelo de desenho (PDFs sintéticos no teste)."""

from __future__ import annotations

import gc
import re
import warnings
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model.family import LIMIAR_FORMAS_GLIFO
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Circulo,
    ModeloDesenho,
    PaginaModelo,
    Polilinha,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    extrair_modelo_desenho,
    impressao_estrutural,
)

_XREF = re.compile(r"(?<!\d)(\d+)\s+\d+\s+R")
_LARGURA, _ALTURA = 300.0, 200.0


def _png() -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 2, 2), False)
    pixmap.clear_with(0x00FF00)
    return bytes(pixmap.tobytes("png"))


def _visual(rotacao: int, x: float, y: float) -> tuple[float, float]:
    return {
        0: (x, y),
        90: (_ALTURA - y, x),
        180: (_LARGURA - x, _ALTURA - y),
        270: (y, _LARGURA - x),
    }[rotacao]


def _caixa_visual(rotacao: int, x0: float, y0: float, x1: float, y1: float) -> tuple[float, ...]:
    (ax, ay), (bx, by) = _visual(rotacao, x0, y0), _visual(rotacao, x1, y1)
    return (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))


def _perto(a: tuple[float, ...], b: tuple[float, ...], tolerancia: float) -> bool:
    return len(a) == len(b) and all(abs(x - y) <= tolerancia for x, y in zip(a, b, strict=True))


def _arred(pontos: Any) -> set[tuple[float, ...]]:
    return {tuple(round(v, 3) for v in ponto) for ponto in pontos}


def _pagina_unica(modelo: ModeloDesenho) -> PaginaModelo:
    (pagina,) = modelo.paginas
    return pagina


def _stamp_com_imagem(documento: Any, retangulo: pymupdf.Rect) -> None:
    auxiliar = documento.new_page(width=50, height=50)
    xref_imagem = auxiliar.insert_image(auxiliar.rect, stream=_png())
    carimbo = documento[0].add_stamp_annot(retangulo, stamp=0)
    aparencia = _XREF.search(str(documento.xref_get_key(carimbo.xref, "AP")[1]))
    assert aparencia is not None
    xref_aparencia = int(aparencia.group(1))
    documento.xref_set_key(xref_aparencia, "Resources/XObject/ImAp", f"{xref_imagem} 0 R")
    conteudo = bytes(documento.xref_stream(xref_aparencia) or b"")
    documento.update_stream(xref_aparencia, conteudo + b"\nq 12 0 0 12 2 2 cm /ImAp Do Q\n")
    documento.delete_page(documento.page_count - 1)


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
def test_todas_as_fontes_ficam_na_pagina_visual_para_cada_rotacao(
    tmp_path: Path, rotacao: int
) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        pagina.draw_line((10, 20), (60, 20), color=(0, 0, 0))
        pagina.draw_rect(pymupdf.Rect(100, 20, 130, 40), color=(0, 0, 0))
        pagina.draw_circle((150, 90), 10, color=(0, 0, 1))
        pagina.insert_text((200, 150), "P7", fontsize=10)
        pagina.insert_image(pymupdf.Rect(240, 20, 260, 40), stream=_png())
        shx = pagina.add_rect_annot(pymupdf.Rect(40, 120, 90, 145))
        shx.set_info(title="AutoCAD SHX Text", content="N3")
        shx.update()
        pagina.set_rotation(rotacao)
        pdf = tmp_path / "r.pdf"
        documento.save(pdf)

    pagina_modelo = _pagina_unica(extrair_modelo_desenho(pdf))

    esperado = (_LARGURA, _ALTURA) if rotacao in (0, 180) else (_ALTURA, _LARGURA)
    assert (pagina_modelo.largura, pagina_modelo.altura) == esperado
    assert pagina_modelo.diagnosticos == ()
    # O portador SHX traz o próprio vetor (borda vermelha) em get_drawings; filtra pela cor.
    pretas = [
        p
        for p in pagina_modelo.primitivas
        if isinstance(p, Polilinha) and p.estilo.cor == (0.0, 0.0, 0.0)
    ]
    linhas = [p for p in pretas if not p.fechada]
    assert _arred(linhas[0].pontos) == _arred(_visual(rotacao, *p) for p in ((10, 20), (60, 20)))
    fechadas = [p for p in pretas if p.fechada]
    assert len(fechadas) == 1
    assert _arred(fechadas[0].pontos) == _arred(
        _visual(rotacao, x, y) for x, y in ((100, 20), (130, 20), (130, 40), (100, 40))
    )
    circulo = next(p for p in pagina_modelo.primitivas if isinstance(p, Circulo))
    assert _perto(circulo.centro, _visual(rotacao, 150, 90), 0.05)
    assert circulo.raio == pytest.approx(10.0, abs=0.05)
    texto = next(t for t in pagina_modelo.textos if t.texto == "P7")
    assert texto.rotacao == pytest.approx(float(rotacao))
    ex, ey = _visual(rotacao, 200, 150)
    assert texto.bbox[0] - 1 <= ex <= texto.bbox[2] + 1
    assert texto.bbox[1] - 1 <= ey <= texto.bbox[3] + 1
    shx_texto = next(t for t in pagina_modelo.textos if t.origem == "shx")
    assert _perto(shx_texto.bbox, _caixa_visual(rotacao, 40, 120, 90, 145), 1.0)
    (imagem,) = pagina_modelo.imagens
    assert _perto(imagem.bbox, _caixa_visual(rotacao, 240, 20, 260, 40), 0.5)


@pytest.mark.parametrize("rotacao_pagina", [0, 90, 180, 270])
def test_texto_com_rotacao_propria_soma_a_rotacao_da_pagina(
    tmp_path: Path, rotacao_pagina: int
) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        pagina.insert_text((100, 100), "AB", fontsize=10, rotate=90)
        pagina.set_rotation(rotacao_pagina)
        pdf = tmp_path / "t.pdf"
        documento.save(pdf)

    (texto,) = _pagina_unica(extrair_modelo_desenho(pdf)).textos

    # rotate=90 sozinho vale 270 no espaço visual (y para baixo); a página soma o seu giro.
    assert texto.rotacao == pytest.approx(float((270 + rotacao_pagina) % 360))
    assert texto.altura == pytest.approx(10.0)


def test_stamp_e_freetext_nao_viram_texto_nativo_nem_shx(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        pagina.insert_text((20, 40), "REAL", fontsize=10)
        pagina.add_stamp_annot(pymupdf.Rect(100, 50, 220, 100), stamp=0)
        pagina.add_freetext_annot(pymupdf.Rect(100, 120, 200, 150), "NOTA LIVRE")
        pdf = tmp_path / "a.pdf"
        documento.save(pdf)

    pagina_modelo = _pagina_unica(extrair_modelo_desenho(pdf))

    assert [(t.texto, t.origem) for t in pagina_modelo.textos] == [("REAL", "nativo")]
    with pymupdf.open(pdf) as documento:
        impressao = impressao_estrutural(documento)
    assert impressao.anotacoes_shx == 0
    assert impressao.spans_texto_nativo == 1


def test_square_shx_sem_conteudo_conta_como_portador_mas_nao_gera_texto(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        vazio = pagina.add_rect_annot(pymupdf.Rect(40, 120, 90, 145))
        vazio.set_info(title="AutoCAD SHX Text", content="")
        vazio.update()
        pdf = tmp_path / "v.pdf"
        documento.save(pdf)

    modelo = extrair_modelo_desenho(pdf)

    assert _pagina_unica(modelo).textos == ()
    assert modelo.familia.familia == "autocad"


def test_anotacao_square_comum_com_conteudo_nao_vira_texto(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        comum = pagina.add_rect_annot(pymupdf.Rect(40, 120, 90, 145))
        comum.set_info(title="Revisor", content="COMENTARIO")
        comum.update()
        pdf = tmp_path / "c.pdf"
        documento.save(pdf)

    modelo = extrair_modelo_desenho(pdf)

    assert _pagina_unica(modelo).textos == ()
    assert modelo.familia.familia == "generico"


def test_ocgs_distintos_vao_para_estilo_e_texto_de_cada_um(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        postes = documento.add_ocg("POSTES", on=True)
        notas = documento.add_ocg("NOTAS", on=True)
        pagina.draw_line((10, 10), (100, 10), oc=postes)
        pagina.draw_rect(pymupdf.Rect(10, 30, 40, 50), fill=(1, 0, 0), color=None, oc=notas)
        pagina.insert_text((50, 100), "UM", fontsize=10, oc=postes)
        pagina.insert_text((50, 130), "DOIS", fontsize=10, oc=notas)
        pdf = tmp_path / "o.pdf"
        documento.save(pdf)

    pagina_modelo = _pagina_unica(extrair_modelo_desenho(pdf))

    assert [c.estilo.camada for c in pagina_modelo.caminhos] == ["POSTES", "NOTAS"]
    assert {t.texto: t.camada for t in pagina_modelo.textos} == {"UM": "POSTES", "DOIS": "NOTAS"}


def test_camada_do_texto_em_pagina_rotacionada_continua_correta(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        ocg = documento.add_ocg("NOTAS", on=True)
        pagina.insert_text((50, 100), "DENTRO", fontsize=10, oc=ocg)
        pagina.insert_text((50, 130), "FORA", fontsize=10)
        pagina.set_rotation(90)
        pdf = tmp_path / "or.pdf"
        documento.save(pdf)

    textos = _pagina_unica(extrair_modelo_desenho(pdf)).textos

    assert {t.texto: t.camada for t in textos} == {"DENTRO": "NOTAS", "FORA": ""}


def _pdf_com_conteudo(caminho: Path, fluxo: bytes) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        pagina.draw_line((1, 1), (2, 2))
        documento.update_stream(pagina.get_contents()[0], fluxo)
        documento.save(caminho)
    return caminho


def test_clip_nao_entra_nos_caminhos_e_nao_desloca_a_ordem(tmp_path: Path) -> None:
    pdf = _pdf_com_conteudo(
        tmp_path / "clip.pdf",
        b"q 0 0 100 100 re W n 1 0 0 rg 10 10 30 30 re f Q q 0 0 1 rg 50 50 20 20 re f Q",
    )

    caminhos = _pagina_unica(extrair_modelo_desenho(pdf)).caminhos

    assert [c.tipo for c in caminhos] == ["preenchimento", "preenchimento"]
    assert [c.ordem for c in caminhos] == [0, 1]
    assert [c.estilo.preenchimento for c in caminhos] == [(1.0, 0.0, 0.0), (0.0, 0.0, 1.0)]
    assert all(len(c.subcaminhos) == 1 and len(c.subcaminhos[0]) == 4 for c in caminhos)


def test_subcaminhos_separam_quando_o_proximo_item_nao_continua(tmp_path: Path) -> None:
    pdf = _pdf_com_conteudo(
        tmp_path / "sub.pdf",
        b"0 0 0 RG 10 10 m 20 10 l 20 20 l 60 60 m 70 60 l "
        b"100 100 m 110 100 120 110 130 110 c 130 110 m 140 110 l S",
    )
    separado = _pdf_com_conteudo(
        tmp_path / "sub2.pdf",
        b"0 0 0 RG 10 10 m 20 10 l 30 10 40 20 50 20 c 90 90 m 95 90 l S",
    )

    (caminho,) = _pagina_unica(extrair_modelo_desenho(pdf)).caminhos

    # `m` no ponto onde o item anterior terminou continua o mesmo subcaminho.
    assert [len(s) for s in caminho.subcaminhos] == [2, 1, 2]
    assert [i.tipo for i in caminho.subcaminhos[2]] == ["c", "l"]
    (outro,) = _pagina_unica(extrair_modelo_desenho(separado)).caminhos
    assert [[i.tipo for i in s] for s in outro.subcaminhos] == [["l", "c"], ["l"]]


def test_re_e_qu_preenchidos_viram_subcaminho_fechado_de_quatro_itens(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        pagina.draw_rect(pymupdf.Rect(10, 10, 40, 30), fill=(1, 0, 0), color=None)
        pagina.draw_quad(
            pymupdf.Quad((60, 10), (90, 10), (60, 30), (90, 30)), fill=(0, 1, 0), color=None
        )
        pdf = tmp_path / "req.pdf"
        documento.save(pdf)

    retangulo, quadrilatero = _pagina_unica(extrair_modelo_desenho(pdf)).caminhos

    for caminho in (retangulo, quadrilatero):
        assert caminho.tipo == "preenchimento"
        assert len(caminho.subcaminhos) == 1 and len(caminho.subcaminhos[0]) == 4
        itens = caminho.subcaminhos[0]
        assert all(i.tipo == "l" for i in itens)
        for i, item in enumerate(itens):
            assert item.pontos[1] == itens[(i + 1) % 4].pontos[0]
    assert {i.pontos[0] for i in retangulo.subcaminhos[0]} == {
        (10.0, 10.0),
        (40.0, 10.0),
        (40.0, 30.0),
        (10.0, 30.0),
    }


def test_tipos_estilo_e_ordem_de_pintura_dos_caminhos(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        pagina.draw_line((10, 10), (90, 10), color=(1, 0, 0), width=2.5, dashes="[3] 0")
        pagina.draw_rect(pymupdf.Rect(10, 30, 40, 50), fill=(0, 1, 0), color=None)
        pagina.draw_rect(pymupdf.Rect(60, 30, 90, 50), fill=(0, 0, 1), color=(0, 0, 0))
        pdf = tmp_path / "e.pdf"
        documento.save(pdf)

    traco, preenchimento, ambos = _pagina_unica(extrair_modelo_desenho(pdf)).caminhos

    assert [c.ordem for c in (traco, preenchimento, ambos)] == [0, 1, 2]
    assert (traco.tipo, preenchimento.tipo, ambos.tipo) == (
        "traco",
        "preenchimento",
        "traco_e_preenchimento",
    )
    assert traco.estilo.cor == (1.0, 0.0, 0.0) and traco.estilo.preenchimento is None
    assert traco.estilo.espessura == pytest.approx(2.5)
    assert "3" in traco.estilo.tracejado
    assert preenchimento.estilo.cor is None
    assert preenchimento.estilo.preenchimento == (0.0, 1.0, 0.0)
    assert ambos.estilo.cor == (0.0, 0.0, 0.0) and ambos.estilo.preenchimento == (0.0, 0.0, 1.0)


def test_imagem_so_de_anotacao_nao_conta_na_pagina_nem_duas_vezes(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        documento.new_page(width=_LARGURA, height=_ALTURA)
        _stamp_com_imagem(documento, pymupdf.Rect(100, 50, 200, 100))
        pdf = tmp_path / "s.pdf"
        documento.save(pdf)

    pagina_modelo = _pagina_unica(extrair_modelo_desenho(pdf))
    with pymupdf.open(pdf) as documento:
        contagem = impressao_estrutural(documento).imagens

    assert [i.de_anotacao for i in pagina_modelo.imagens] == [True]
    assert contagem == 1


def test_imagem_de_anotacao_em_pagina_rotacionada_fica_no_espaco_visual(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        documento.new_page(width=_LARGURA, height=_ALTURA)
        _stamp_com_imagem(documento, pymupdf.Rect(100, 50, 200, 100))
        documento[0].set_rotation(270)
        pdf = tmp_path / "sr.pdf"
        documento.save(pdf)

    (imagem,) = _pagina_unica(extrair_modelo_desenho(pdf)).imagens
    with pymupdf.open(pdf) as documento:
        # o carimbo ajusta a própria altura ao criar; vale o /Rect real, sem rotação da página
        pagina_aberta = documento[0]
        (xref, _tipo, _campo), *_ = pagina_aberta.annot_xrefs()
        retangulo = pymupdf.Rect(pagina_aberta.load_annot(xref).rect)

    assert imagem.de_anotacao
    esperado = _caixa_visual(270, retangulo.x0, retangulo.y0, retangulo.x1, retangulo.y1)
    assert _perto(imagem.bbox, esperado, 0.5)
    assert imagem.bbox[3] - imagem.bbox[1] == pytest.approx(retangulo.width, abs=0.5)


def _pdf_completo(caminho: Path, paginas: int = 2) -> Path:
    with pymupdf.open() as documento:
        for _ in range(paginas):
            pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
            pagina.insert_text((20, 40), "P1", fontsize=10)
            pagina.draw_line((10, 100), (90, 100))
            pagina.insert_image(pymupdf.Rect(200, 20, 220, 40), stream=_png())
            shx = pagina.add_rect_annot(pymupdf.Rect(40, 120, 90, 145))
            shx.set_info(title="AutoCAD SHX Text", content="N3")
            shx.update()
        _stamp_com_imagem(documento, pymupdf.Rect(100, 50, 200, 100))
        documento.save(caminho)
    return caminho


@pytest.mark.parametrize(
    ("funcao", "diagnostico"),
    [
        ("_textos_shx", "modelo.textos_shx_falhou"),
        ("_imagens_da_pagina", "modelo.imagens_falhou"),
        ("_imagens_de_anotacoes", "modelo.imagens_anotacao_falhou"),
        ("_caminhos_e_glifos", "modelo.caminhos_falhou"),
    ],
)
def test_falha_em_uma_fonte_so_esvazia_aquela_fonte_na_pagina_certa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, funcao: str, diagnostico: str
) -> None:
    pdf = _pdf_completo(tmp_path / "f.pdf")
    referencia_0, referencia_1 = extrair_modelo_desenho(pdf).paginas
    original = getattr(pymupdf_drawing_model, funcao)

    def falha_na_primeira(pagina: Any) -> Any:
        if pagina.number == 0:
            raise RuntimeError("fonte corrompida")
        return original(pagina)

    monkeypatch.setattr(pymupdf_drawing_model, funcao, falha_na_primeira)
    primeira, segunda = extrair_modelo_desenho(pdf).paginas

    assert primeira.diagnosticos == (diagnostico,)
    assert segunda.diagnosticos == ()
    assert segunda == referencia_1
    nativos = [t for t in primeira.textos if t.origem == "nativo"]
    shx = [t for t in primeira.textos if t.origem == "shx"]
    da_pagina = [i for i in primeira.imagens if not i.de_anotacao]
    de_anotacao = [i for i in primeira.imagens if i.de_anotacao]
    ref_nativos = [t for t in referencia_0.textos if t.origem == "nativo"]
    ref_shx = [t for t in referencia_0.textos if t.origem == "shx"]
    ref_da_pagina = [i for i in referencia_0.imagens if not i.de_anotacao]
    ref_de_anotacao = [i for i in referencia_0.imagens if i.de_anotacao]
    assert nativos == ref_nativos
    assert (shx == ref_shx) == (funcao != "_textos_shx")
    assert (da_pagina == ref_da_pagina) == (funcao != "_imagens_da_pagina")
    assert (de_anotacao == ref_de_anotacao) == (funcao != "_imagens_de_anotacoes")
    assert (primeira.caminhos == referencia_0.caminhos) == (funcao != "_caminhos_e_glifos")


def test_varias_fontes_falhando_acumulam_diagnosticos_na_ordem_das_fontes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_completo(tmp_path / "m.pdf", paginas=1)

    def falha(pagina: Any) -> Any:
        raise RuntimeError("x")

    monkeypatch.setattr(pymupdf_drawing_model, "_imagens_da_pagina", falha)
    monkeypatch.setattr(pymupdf_drawing_model, "_textos_nativos", falha)

    pagina_modelo = _pagina_unica(extrair_modelo_desenho(pdf))

    assert pagina_modelo.diagnosticos == ("modelo.textos_nativos_falhou", "modelo.imagens_falhou")
    assert [t.texto for t in pagina_modelo.textos] == ["N3"]
    # a linha da página vem primeiro; o resto é vetor das anotações (borda SHX, carimbo)
    assert pagina_modelo.caminhos[0].subcaminhos[0][0].pontos == ((10.0, 100.0), (90.0, 100.0))


def test_documento_e_fechado_sem_resource_warning_mesmo_com_fonte_falhando(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_completo(tmp_path / "w.pdf")
    abertos: list[Any] = []
    abrir = pymupdf.open

    def espiao(*args: Any, **kwargs: Any) -> Any:
        documento = abrir(*args, **kwargs)
        abertos.append(documento)
        return documento

    def falha(pagina: Any) -> Any:
        raise RuntimeError("x")

    monkeypatch.setattr(pymupdf, "open", espiao)
    monkeypatch.setattr(pymupdf_drawing_model, "_imagens_de_anotacoes", falha)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        extrair_modelo_desenho(pdf)
        gc.collect()

    assert len(abertos) == 1 and abertos[0].is_closed
    pdf.unlink()


def _pdf_com_formas(
    caminho: Path,
    quantidade: int,
    *,
    lado: float = 3.0,
    preencher: bool = True,
    produtor: str = "Microsoft: Print To PDF",
    paginas: int = 1,
) -> Path:
    with pymupdf.open() as documento:
        restante = quantidade
        for numero in range(paginas):
            pagina = documento.new_page(width=800, height=800)
            na_pagina = restante if numero == paginas - 1 else quantidade // paginas
            restante -= na_pagina
            forma = pagina.new_shape()
            for indice in range(na_pagina):
                x, y = 10 + (indice % 50) * 12, 10 + (indice // 50) * 12
                forma.draw_rect(pymupdf.Rect(x, y, x + lado, y + lado + 1))
                if preencher:
                    forma.finish(color=None, fill=(0, 0, 0))
                else:
                    forma.finish(color=(0, 0, 0), fill=None)
            forma.commit()
        documento.set_metadata({"producer": produtor})
        documento.save(caminho)
    return caminho


def test_limiar_de_300_glifos_e_exato(tmp_path: Path) -> None:
    abaixo = extrair_modelo_desenho(_pdf_com_formas(tmp_path / "a.pdf", LIMIAR_FORMAS_GLIFO - 1))
    no_limiar = extrair_modelo_desenho(_pdf_com_formas(tmp_path / "b.pdf", LIMIAR_FORMAS_GLIFO))

    assert abaixo.familia.familia == "generico"
    assert no_limiar.familia.familia == "electric_office_print"


def test_glifos_somam_entre_paginas_para_o_limiar(tmp_path: Path) -> None:
    modelo = extrair_modelo_desenho(_pdf_com_formas(tmp_path / "p.pdf", 320, paginas=2))

    assert modelo.familia.familia == "electric_office_print"
    assert dict(modelo.familia.sinais)["formas_glifo"] == 320


@pytest.mark.parametrize(
    ("kwargs", "motivo"),
    [
        ({"lado": 8.0}, "formas grandes demais (>= 6 pt) não são glifos"),
        ({"preencher": False}, "traço sem preenchimento não é glifo"),
        ({"produtor": "Qualquer Coisa"}, "sem Print To PDF não é Electric Office"),
    ],
)
def test_formas_que_nao_cumprem_o_criterio_de_glifo_nao_formam_familia_eo(
    tmp_path: Path, kwargs: dict[str, Any], motivo: str
) -> None:
    modelo = extrair_modelo_desenho(_pdf_com_formas(tmp_path / "n.pdf", 400, **kwargs))

    assert modelo.familia.familia == "generico", motivo


def test_produtor_itext_com_ocg_e_autocad_pela_precedencia_da_familia(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        documento.new_page(width=_LARGURA, height=_ALTURA)
        documento.add_ocg("REDE")
        documento.set_metadata({"producer": "iText 5.5.13"})
        pdf = tmp_path / "i.pdf"
        documento.save(pdf)

    assert extrair_modelo_desenho(pdf).familia.familia == "autocad"


def test_texto_so_com_espacos_e_ignorado_e_spans_multiplos_sao_separados(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=_LARGURA, height=_ALTURA)
        pagina.insert_text((20, 40), "   ", fontsize=10)
        pagina.insert_text((20, 80), "A", fontsize=10, fontname="helv")
        pagina.insert_text((60, 80), "B", fontsize=14, fontname="cour")
        pdf = tmp_path / "sp.pdf"
        documento.save(pdf)

    textos = _pagina_unica(extrair_modelo_desenho(pdf)).textos

    assert sorted((t.texto, t.altura) for t in textos) == [("A", 10.0), ("B", 14.0)]
    assert all(t.fonte for t in textos)
