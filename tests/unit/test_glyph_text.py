# mypy: disable-error-code="no-untyped-call"
"""Leitura de texto por contorno de glifo, sobre PDFs sintéticos de fonte livre (Helvetica)."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from pathlib import Path

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import (
    ALFABETO,
    LinhaTexto,
    caminhos_do_pdf,
    pdf_texto_contorno,
    pdf_texto_nativo,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis.drawing_model import glyph_text
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    EntradaGlifo,
    TabelaGlifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import (
    LeituraGlifos,
    TextoGlifo,
    extrair_trechos,
    ler_texto_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Estilo,
    ItemCaminho,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto"))


def _ler(
    tmp_path: Path, linhas: Sequence[LinhaTexto], tabela: TabelaGlifos, **kw: int
) -> LeituraGlifos:
    pdf = pdf_texto_contorno(tmp_path / "contorno.pdf", linhas, **kw)
    return ler_texto_glifos(caminhos_do_pdf(pdf), tabela)


def _nativos(tmp_path: Path, linhas: Sequence[LinhaTexto], **kw: int) -> tuple[TextoModelo, ...]:
    pdf = pdf_texto_nativo(tmp_path / "nativo.pdf", linhas, **kw)
    (pagina,) = extrair_modelo_desenho(pdf).paginas
    return pagina.textos


def _normalizar(texto: str) -> str:
    return " ".join(texto.split())


def _diferenca_angular(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _sem_caractere(tabela: TabelaGlifos, caractere: str) -> TabelaGlifos:
    glifos = tuple(g for g in tabela.glifos if g.caractere != caractere)
    return dataclasses.replace(tabela, glifos=glifos)


def _entrada(tabela: TabelaGlifos, caractere: str) -> EntradaGlifo:
    (entrada,) = (g for g in tabela.glifos if g.caractere == caractere)
    return entrada


_LINHAS = (
    LinhaTexto("P7 U4(1) S1N", (40.0, 60.0), 5.0),
    LinhaTexto("11-300", (40.0, 120.0), 5.0),
    LinhaTexto("E=612345 N=7801234", (40.0, 180.0), 5.0),
)


def _por_linha(textos: Sequence[TextoGlifo | TextoModelo]) -> list[str]:
    return [_normalizar(t.texto) for t in sorted(textos, key=lambda t: (t.bbox[1], t.bbox[0]))]


def test_tabela_do_alfabeto_tem_um_glifo_por_caractere(tabela: TabelaGlifos) -> None:
    assert sorted(g.caractere or "" for g in tabela.glifos) == sorted(ALFABETO)
    assert len(tabela.sha256) == 64


def test_contorno_le_o_mesmo_texto_que_o_nativo(tmp_path: Path, tabela: TabelaGlifos) -> None:
    leitura = _ler(tmp_path, _LINHAS, tabela)

    assert _por_linha(leitura.textos) == _por_linha(_nativos(tmp_path, _LINHAS))
    assert _por_linha(leitura.textos) == ["P7 U4(1) S1N", "11-300", "E=612345 N=7801234"]
    assert (leitura.desconhecidos, leitura.ambiguos, leitura.limitada) == (0, 0, False)
    (texto,) = (t for t in leitura.textos if t.texto == "11-300")
    assert texto.quantidade_glifos == 6
    assert [c for c, _ in texto.glifos] == list("11-300")
    assert texto.cor == pytest.approx((0.0, 0.0, 0.0))


def test_contorno_sem_texto_nativo_e_caixa_proxima_do_nativo(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", _LINHAS)
    (pagina,) = extrair_modelo_desenho(pdf).paginas
    assert pagina.textos == ()
    leitura = ler_texto_glifos(pagina.caminhos, tabela)
    for lido, nativo in zip(
        sorted(leitura.textos, key=lambda t: t.bbox[1]),
        sorted(_nativos(tmp_path, _LINHAS), key=lambda t: t.bbox[1]),
        strict=True,
    ):
        assert lido.bbox[0] == pytest.approx(nativo.bbox[0], abs=1.0)
        assert lido.bbox[2] == pytest.approx(nativo.bbox[2], abs=1.0)
        assert nativo.bbox[1] - 0.5 <= lido.bbox[1] and lido.bbox[3] <= nativo.bbox[3] + 0.5


@pytest.mark.parametrize("rotacao", [90.0, 30.0])
def test_rotulo_girado_le_igual(tmp_path: Path, tabela: TabelaGlifos, rotacao: float) -> None:
    linhas = [
        dataclasses.replace(linha, rotacao=rotacao, origem=(100.0 + 90.0 * i, 250.0))
        for i, linha in enumerate(_LINHAS)
    ]

    leitura = _ler(tmp_path, linhas, tabela)
    nativos = _nativos(tmp_path, linhas)

    assert sorted(_normalizar(t.texto) for t in leitura.textos) == sorted(
        _normalizar(t.texto) for t in nativos
    )
    for texto in leitura.textos:
        (nativo,) = (n for n in nativos if _normalizar(n.texto) == _normalizar(texto.texto))
        assert _diferenca_angular(texto.rotacao, nativo.rotacao) <= 2.0


def test_par_sensivel_a_rotacao_le_igual_a_0_e_180(tmp_path: Path, tabela: TabelaGlifos) -> None:
    for rotacao in (0.0, 180.0):
        linhas = [LinhaTexto("69 96", (200.0, 150.0), 5.0, rotacao=rotacao)]
        leitura = _ler(tmp_path, linhas, tabela)
        (nativo,) = _nativos(tmp_path, linhas)
        assert [t.texto for t in leitura.textos] == ["69 96"]
        assert _diferenca_angular(leitura.textos[0].rotacao, nativo.rotacao) <= 2.0


@pytest.mark.parametrize("rotacao_pagina", [90, 270])
def test_pagina_com_rotate_le_e_posiciona_como_o_nativo(
    tmp_path: Path, tabela: TabelaGlifos, rotacao_pagina: int
) -> None:
    linhas = [LinhaTexto("P10 N1", (60.0, 80.0), 5.0)]

    leitura = _ler(tmp_path, linhas, tabela, rotacao_pagina=rotacao_pagina)
    (nativo,) = _nativos(tmp_path, linhas, rotacao_pagina=rotacao_pagina)

    (texto,) = leitura.textos
    assert texto.texto == "P10 N1"
    assert _diferenca_angular(texto.rotacao, nativo.rotacao) <= 2.0
    # a caixa nativa vai de avanço a avanço, com ascendente e descendente; a do glifo é a tinta
    x0, y0, x1, y1 = texto.bbox
    n0, n1, n2, n3 = nativo.bbox
    assert n0 - 0.5 <= x0 and n1 - 0.5 <= y0 and x1 <= n2 + 0.5 and y1 <= n3 + 0.5
    assert y1 - y0 == pytest.approx(n3 - n1, abs=2.0)


def test_cantos_seguem_a_ordem_inicio_base_fim_base_fim_topo_inicio_topo(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    for rotacao in (0.0, 90.0, 30.0):
        leitura = _ler(tmp_path, [LinhaTexto("P10 N1", (200.0, 150.0), 5.0, rotacao)], tabela)
        (texto,) = leitura.textos
        inicio_base, fim_base, fim_topo, inicio_topo = texto.cantos
        direcao = math.degrees(
            math.atan2(fim_base[1] - inicio_base[1], fim_base[0] - inicio_base[0])
        )
        assert _diferenca_angular(direcao % 360.0, texto.rotacao) <= 0.01
        # o topo fica a 90° anti-horários visuais da direção (y para baixo)
        subida = math.degrees(
            math.atan2(inicio_topo[1] - inicio_base[1], inicio_topo[0] - inicio_base[0])
        )
        assert _diferenca_angular(subida % 360.0, (texto.rotacao - 90.0) % 360.0) <= 0.01
        assert math.dist(fim_topo, inicio_topo) == pytest.approx(math.dist(fim_base, inicio_base))
        xs = [p[0] for p in texto.cantos]
        ys = [p[1] for p in texto.cantos]
        assert texto.bbox == pytest.approx((min(xs), min(ys), max(xs), max(ys)), abs=0.3)


@pytest.mark.parametrize("rotacao", [0.0, 30.0])
def test_glifos_fora_do_centro_nao_inclinam_o_angulo_do_trecho(
    tmp_path: Path, rotacao: float
) -> None:
    pdf = pdf_texto_contorno(
        tmp_path / "c.pdf", [LinhaTexto("E=(61)-2345 N7801234", (60.0, 250.0), 5.0, rotacao)]
    )

    (trecho,) = extrair_trechos(caminhos_do_pdf(pdf))

    # só pelos centros, "=", "(", ")" e "-" no começo inclinam a reta em ~0,4°
    assert _diferenca_angular(trecho.rotacao, (-rotacao) % 360.0) <= 0.05


def test_tamanho_diferente_le_igual(tmp_path: Path, tabela: TabelaGlifos) -> None:
    linhas = [
        LinhaTexto("P10 N1", (40.0, 60.0), 3.0),
        LinhaTexto("P10 N1", (40.0, 160.0), 6.0),
    ]

    leitura = _ler(tmp_path, linhas, tabela)

    pequeno, grande = sorted(leitura.textos, key=lambda t: t.bbox[1])
    assert (pequeno.texto, grande.texto) == ("P10 N1", "P10 N1")
    assert grande.altura / pequeno.altura == pytest.approx(2.0, rel=0.1)


def test_glifo_desconhecido_nao_produz_caractere(tmp_path: Path, tabela: TabelaGlifos) -> None:
    linhas = [LinhaTexto("P7", (40.0, 60.0), 5.0), LinhaTexto("11-300", (40.0, 120.0), 5.0)]

    leitura = _ler(tmp_path, linhas, _sem_caractere(tabela, "3"))

    assert not any("11-" in t.texto for t in leitura.textos)
    assert not any("1-" in t.texto or "00" in t.texto for t in leitura.textos)
    assert leitura.desconhecidos >= 1
    assert [t.texto for t in leitura.textos] == ["P7"]


def test_glifo_ambiguo_nao_produz_caractere(tmp_path: Path, tabela: TabelaGlifos) -> None:
    letra_o = _entrada(tabela, "O")
    copia = EntradaGlifo("copia-o", "0", letra_o.assinatura)
    ambigua = dataclasses.replace(tabela, glifos=(*tabela.glifos, copia))
    linhas = [LinhaTexto("POSTE", (40.0, 60.0), 5.0), LinhaTexto("P7", (40.0, 120.0), 5.0)]

    leitura = _ler(tmp_path, linhas, ambigua)

    assert not any("O" in t.texto or "0" in t.texto for t in leitura.textos)
    assert leitura.ambiguos >= 1
    assert [t.texto for t in leitura.textos] == ["P7"]


def test_formas_isoladas_e_tracos_nao_viram_texto(tmp_path: Path, tabela: TabelaGlifos) -> None:
    pdf = tmp_path / "formas.pdf"
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=400, height=300)
        pagina.draw_rect(pymupdf.Rect(20, 20, 23, 23), color=None, fill=(0, 0, 0))
        pagina.draw_circle((60, 60), 1.5, color=None, fill=(0, 0, 0))
        for i in range(6):
            pagina.draw_rect(pymupdf.Rect(100 + 4 * i, 100, 103 + 4 * i, 103), color=(0, 0, 0))
        pagina.draw_line((10, 200), (300, 200), color=(0, 0, 0))
        pagina.draw_rect(pymupdf.Rect(150, 150, 190, 190), color=None, fill=(0, 0, 0))
        documento.save(pdf)

    caminhos = caminhos_do_pdf(pdf)
    leitura = ler_texto_glifos(caminhos, tabela)

    assert extrair_trechos(caminhos) == ()
    assert leitura == LeituraGlifos((), 0, 0, False)


def test_glifo_maior_que_o_lado_maximo_nao_e_candidato(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto("P10 N1", (40.0, 60.0), 12.0)], tabela)

    assert leitura.textos == ()
    assert glyph_text.LADO_MAXIMO_GLIFO == 7.0


def test_entrada_ignorar_divide_o_trecho(tmp_path: Path, tabela: TabelaGlifos) -> None:
    hifen = _entrada(tabela, "-")
    glifos = tuple(
        dataclasses.replace(g, caractere=None) if g == hifen else g for g in tabela.glifos
    )

    leitura = _ler(
        tmp_path,
        [LinhaTexto("11-300", (40.0, 60.0), 5.0)],
        dataclasses.replace(tabela, glifos=glifos),
    )

    assert sorted(t.texto for t in leitura.textos) == ["11", "300"]
    assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


def test_cor_do_trecho(tmp_path: Path, tabela: TabelaGlifos) -> None:
    linhas = [
        LinhaTexto("P7 S1N", (40.0, 60.0), 5.0, cor=(0.0, 1.0, 0.0)),
        LinhaTexto("P10", (40.0, 120.0), 5.0, cor=(1.0, 0.0, 0.0)),
    ]

    leitura = _ler(tmp_path, linhas, tabela)

    verde, vermelho = sorted(leitura.textos, key=lambda t: t.bbox[1])
    assert verde.texto == "P7 S1N" and vermelho.texto == "P10"
    assert verde.cor == pytest.approx((0.0, 1.0, 0.0), abs=0.01)
    assert vermelho.cor == pytest.approx((1.0, 0.0, 0.0), abs=0.01)


def test_cores_diferentes_separam_trechos(tmp_path: Path, tabela: TabelaGlifos) -> None:
    linhas = [
        LinhaTexto("P1", (40.0, 60.0), 5.0, cor=(0.0, 0.0, 1.0)),
        LinhaTexto("N7", (47.0, 60.0), 5.0, cor=(1.0, 0.0, 0.0)),
    ]

    leitura = _ler(tmp_path, linhas, tabela)

    assert sorted(t.texto for t in leitura.textos) == ["N7", "P1"]


def test_limite_de_glifos_por_pagina(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P10N1", (40.0, 60.0), 5.0)])
    caminhos = caminhos_do_pdf(pdf)
    assert [t.texto for t in ler_texto_glifos(caminhos, tabela).textos] == ["P10N1"]

    monkeypatch.setattr(glyph_text, "LIMITE_GLIFOS_PAGINA", 3)

    assert ler_texto_glifos(caminhos, tabela) == LeituraGlifos((), 0, 0, limitada=True)


def test_trecho_expoe_glifos_em_ordem_de_leitura_e_rotacao(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pdf = pdf_texto_contorno(
        tmp_path / "c.pdf", [LinhaTexto("P10", (100.0, 100.0), 5.0, rotacao=90.0)]
    )
    caminhos = caminhos_do_pdf(pdf)

    (trecho,) = extrair_trechos(caminhos)

    assert [g.indice_caminho for g in trecho.glifos] == [0, 1, 2]
    assert trecho.rotacao == pytest.approx(270.0, abs=1.0)
    assert trecho.altura == pytest.approx(0.729 * 5.0, rel=0.05)
    assert all(g.assinatura is not None for g in trecho.glifos)
    ys = [g.caixa[1] for g in trecho.glifos]
    assert ys == sorted(ys, reverse=True)


def _quadrado_preenchido(x: float, ordem: int) -> Caminho:
    cantos = [(x, 10.0), (x + 2.0, 10.0), (x + 2.0, 12.0), (x, 12.0)]
    itens = tuple(ItemCaminho("l", (cantos[i], cantos[(i + 1) % 4])) for i in range(4))
    return Caminho((itens,), Estilo("", None, (0.0, 0.0, 0.0), 0.0, ""), "preenchimento", ordem)


@pytest.mark.parametrize(
    "item_ruim",
    [
        ItemCaminho("l", ()),
        ItemCaminho("l", ((1.0, 1.0),)),
        ItemCaminho("c", ((1.0, 1.0), (2.0, 2.0))),
    ],
)
def test_item_sem_os_pontos_do_seu_tipo_nao_e_candidato(
    tabela: TabelaGlifos, item_ruim: ItemCaminho
) -> None:
    ruim = Caminho(((item_ruim,),), Estilo("", None, (0.0, 0.0, 0.0), 0.0, ""), "preenchimento", 1)
    # o item ruim não é candidato: separa os dois quadrados, que sozinhos não formam trecho
    caminhos = [_quadrado_preenchido(10.0, 0), ruim, _quadrado_preenchido(13.0, 2)]

    assert extrair_trechos(caminhos) == ()
    assert ler_texto_glifos(caminhos, tabela) == LeituraGlifos((), 0, 0, False)
    assert extrair_trechos([_quadrado_preenchido(10.0, 0), _quadrado_preenchido(13.0, 1)])
