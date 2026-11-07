# mypy: disable-error-code="no-untyped-call"
"""Leitura de texto por contorno de glifo, sobre PDFs sintéticos de fonte livre (Helvetica)."""

from __future__ import annotations

import dataclasses
import math
import random
import time
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


def test_caminhos_lidos_so_de_grupo_resolvido(tmp_path: Path, tabela: TabelaGlifos) -> None:
    # "-" como "ignorar" divide o trecho em "11" e "300", e sem o "3" o segundo grupo se anula
    hifen = _entrada(tabela, "-")
    glifos = tuple(
        dataclasses.replace(g, caractere=None) if g == hifen else g
        for g in tabela.glifos
        if g.caractere != "3"
    )

    leitura = _ler(
        tmp_path,
        [LinhaTexto("11-300", (40.0, 60.0), 5.0)],
        dataclasses.replace(tabela, glifos=glifos),
    )

    assert [t.texto for t in leitura.textos] == ["11"]
    assert leitura.desconhecidos >= 1
    assert leitura.caminhos_lidos == {0, 1}


def test_escala_das_lacunas_nao_depende_dos_outros_glifos_do_texto(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    # "0" passa um pouco da altura de "1"; sem ele a altura bruta da linha cai e a mesma
    # lacuna "1"+"1" cresce em unidades de h. Medida pela altura típica de cada caractere na
    # tabela, ela é a mesma nos dois textos: para qualquer espaco, os dois partem o "11" ou
    # nenhum parte. ("0110" é simétrico: o quadro fica horizontal nos dois textos.)
    caminhos = {
        texto: caminhos_do_pdf(
            pdf_texto_contorno(tmp_path / f"{i}.pdf", [LinhaTexto(texto, (40.0, 60.0), 5.0)])
        )
        for i, texto in enumerate(("0110", "1171"))
    }
    divergentes = []
    for milesimos in range(380, 470):
        com_espaco = dataclasses.replace(tabela, espaco=milesimos / 1000)
        partidos = {
            texto: "1 1" in ler_texto_glifos(c, com_espaco).textos[0].texto
            for texto, c in caminhos.items()
        }
        if len(set(partidos.values())) != 1:
            divergentes.append(milesimos)
    assert divergentes == []


def _colher(tmp_path: Path, texto: str, posicoes: dict[int, str]) -> list[EntradaGlifo]:
    """Entradas com a assinatura dos glifos de `texto` (corpo 5) nas posições pedidas."""
    pdf = pdf_texto_contorno(
        tmp_path / f"colher-{texto}.pdf", [LinhaTexto(texto, (40.0, 60.0), 5.0)]
    )
    (trecho,) = extrair_trechos(caminhos_do_pdf(pdf))
    entradas = []
    for posicao, caractere in posicoes.items():
        assinatura = trecho.glifos[posicao].assinatura
        assert assinatura is not None
        entradas.append(EntradaGlifo(f"{texto}-{posicao}", caractere, assinatura))
    return entradas


@pytest.fixture(scope="module")
def tabela_com_e(tmp_path_factory: pytest.TempPathFactory, tabela: TabelaGlifos) -> TabelaGlifos:
    # "e" colhido em trecho de algarismos (h = altura de maiúscula, "e" a ~0.75 h) e em trecho só
    # de minúsculas (h = altura-x, "e" a ~1.0 h), como na tabela real; sem "z" minúsculo
    pasta = tmp_path_factory.mktemp("com-e")
    entradas = [*_colher(pasta, "0e0", {1: "e"}), *_colher(pasta, "ee", {0: "e"})]
    return dataclasses.replace(tabela, glifos=(*tabela.glifos, *entradas))


@pytest.mark.parametrize("texto", ["ez", "ze"])
def test_glifos_lidos_em_escalas_diferentes_no_mesmo_trecho_anulam_o_texto(
    tmp_path: Path, tabela_com_e: TabelaGlifos, texto: str
) -> None:
    # com h vindo do "e" (altura-x), o "z" tem o desenho e a altura relativa do "Z" (colhido com
    # h = altura de maiúscula): o "e" diz que h é a altura-x e o "Z", que é a de maiúscula. As
    # duas leituras do trecho não cabem na mesma escala: falha fechada, nunca "eZ"
    leitura = _ler(tmp_path, [LinhaTexto(texto, (40.0, 60.0), 5.0)], tabela_com_e)
    assert [t.texto for t in leitura.textos] == []
    assert leitura.ambiguos >= 1


@pytest.mark.parametrize("texto", ["0e0", "ee", "Ze0", "00e"])
def test_glifos_da_mesma_escala_continuam_lidos(
    tmp_path: Path, tabela_com_e: TabelaGlifos, texto: str
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto(texto, (40.0, 60.0), 5.0)], tabela_com_e)
    assert [t.texto for t in leitura.textos] == [texto]


@pytest.mark.parametrize("texto", ["ZZ", "Z0", "PZ"])
def test_trecho_sem_ancora_com_letra_sem_par_de_caixa_falha_fechado(
    tmp_path: Path, tabela_com_e: TabelaGlifos, texto: str
) -> None:
    # a tabela tem as duas escalas (o "e"), mas nenhum caractere deste trecho foi colhido nas
    # duas: nada diz se h é a altura de maiúscula ou a altura-x, e o "Z" não tem o "z" na tabela
    # para separar ("zz" com h = altura-x sairia "ZZ"). Falha fechada
    leitura = _ler(tmp_path, [LinhaTexto(texto, (40.0, 60.0), 5.0)], tabela_com_e)
    assert [t.texto for t in leitura.textos] == []
    assert leitura.ambiguos >= 1


@pytest.mark.parametrize("texto", ["47", "11", "Ze0"])
def test_trecho_sem_letra_sem_par_ou_ancorado_continua_lido(
    tmp_path: Path, tabela_com_e: TabelaGlifos, texto: str
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto(texto, (40.0, 60.0), 5.0)], tabela_com_e)
    assert [t.texto for t in leitura.textos] == [texto]


def test_tabela_numa_escala_so_nao_exige_ancora(tmp_path: Path, tabela: TabelaGlifos) -> None:
    # a tabela do alfabeto (só maiúsculas e algarismos) não tem nenhum caractere nas duas
    # escalas: não há o que confundir, e "Z0" continua lido
    leitura = _ler(tmp_path, [LinhaTexto("Z0", (40.0, 60.0), 5.0)], tabela)
    assert [t.texto for t in leitura.textos] == ["Z0"]


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


_CELULA = 45.0
_ROTACOES_VARREDURA = (0.0, 17.5, 30.0, 90.0, 180.0, 270.0, 41.0, 133.0, 222.0, 301.0)


def _varredura_curta(
    tmp_path: Path, tabela: TabelaGlifos, semente: int, paginas: int
) -> tuple[int, int, list[tuple[str, str]]]:
    """Trechos de 2 a 4 glifos sorteados do alfabeto inteiro, um por célula de uma grade.

    Devolve (trechos, lidos, erros), com erro = leitura diferente do texto desenhado."""
    sorteio = random.Random(semente)
    colunas, linhas_grade = int(400 // _CELULA), int(300 // _CELULA)
    total = lidos = 0
    erros: list[tuple[str, str]] = []
    for pagina in range(paginas):
        tamanho = (3.0, 4.0, 5.0, 6.0)[pagina % 4]
        rotacao = _ROTACOES_VARREDURA[pagina % len(_ROTACOES_VARREDURA)]
        linhas = []
        for indice in range(colunas * linhas_grade):
            texto = "".join(sorteio.choice(ALFABETO) for _ in range(sorteio.randint(2, 4)))
            centro = (
                _CELULA * (indice % colunas + 0.5),
                _CELULA * (indice // colunas + 0.5),
            )
            linhas.append(LinhaTexto(texto, centro, tamanho, rotacao))
        leitura = _ler(tmp_path, linhas, tabela)
        total += len(linhas)
        for lido in leitura.textos:
            primeiro = lido.glifos[0][1]
            centro_glifo = ((primeiro[0] + primeiro[2]) / 2, (primeiro[1] + primeiro[3]) / 2)
            dono = min(linhas, key=lambda linha: math.dist(linha.origem, centro_glifo))
            lidos += 1
            if lido.texto != dono.texto:
                erros.append((dono.texto, lido.texto))
    return total, lidos, erros


def test_varredura_de_trechos_curtos_nunca_le_errado(tmp_path: Path, tabela: TabelaGlifos) -> None:
    total, lidos, erros = _varredura_curta(tmp_path, tabela, semente=20261104, paginas=24)

    assert total == 24 * 48
    assert erros == []
    assert lidos >= total // 4


@pytest.mark.parametrize("texto", ["P10 N1..", "..P10 N1", "N1,-55", "P7...N1"])
def test_pontuacao_pequena_em_sequencia_fica_no_trecho(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), 5.0)], tabela)

    assert [t.texto for t in leitura.textos] == [texto]


@pytest.mark.parametrize("texto", ["C0..", "..C0", "...C", ",-55", "1,-5"])
def test_pontuacao_pequena_em_trecho_curto_le_inteira_ou_avisa(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), 5.0)], tabela)

    lidos = [t.texto for t in leitura.textos]
    assert lidos in ([], [texto])
    if not lidos:
        # o trecho não sai, mas a perda nunca é silenciosa
        assert leitura.desconhecidos + leitura.ambiguos >= 1
    caminhos = caminhos_do_pdf(
        pdf_texto_contorno(tmp_path / "t.pdf", [LinhaTexto(texto, (150.0, 150.0), 5.0)])
    )
    assert [len(t.glifos) for t in extrair_trechos(caminhos)] == [len(texto)]


@pytest.mark.parametrize("texto", [".RQ", "RQ.", "-AQ", "Q.R", "(DQ"])
def test_q_com_pontuacao_que_entorta_o_quadro_provisorio_nunca_vira_o(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # o "." torce a reta dos centros em ~12 graus; um passo só de refino a partir dali deixava
    # os dois quadros concordando em "O"
    for tamanho in (3.0, 5.0):
        leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), tamanho)], tabela)
        assert [t.texto for t in leitura.textos] in ([], [texto])


@pytest.mark.parametrize("rotacao", [0.0, 41.0, 133.0, 222.0, 301.0])
@pytest.mark.parametrize("texto", ["Q-", "-Q", "Q.", "=Q", "-1", "Q"])
def test_trecho_com_menos_de_2_glifos_de_corpo_inteiro_nao_e_lido(
    tmp_path: Path, tabela: TabelaGlifos, texto: str, rotacao: float
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto(texto, (150.0, 150.0), 5.0, rotacao)], tabela)

    assert leitura.textos == ()
    if len(texto) >= 2:
        assert leitura.ambiguos == len(texto)


def _retangulo_preenchido(
    x: float, y: float, lado: float, ordem: int, cor: tuple[float, float, float] = (0.0, 0.0, 0.0)
) -> Caminho:
    cantos = [(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado)]
    itens = tuple(ItemCaminho("l", (cantos[i], cantos[(i + 1) % 4])) for i in range(4))
    return Caminho((itens,), Estilo("", None, cor, 0.0, ""), "preenchimento", ordem)


def test_glifo_do_valor_reprovado_no_filtro_envenena_as_metades(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    # a 7,5 pt "(" e ")" medem mais que LADO_MAXIMO_GLIFO: não são candidatos e abririam um
    # buraco na ordem de desenho; as metades "P7 U4" e "S1N" não podem sair como completas
    leitura = _ler(tmp_path, [LinhaTexto("P7 U4(1) S1N", (40.0, 60.0), 7.5)], tabela)

    assert leitura.textos == ()
    assert leitura.desconhecidos + leitura.ambiguos >= 1


def _renumerado(caminhos: Sequence[Caminho], salto_em: int) -> list[Caminho]:
    """Caminhos com a `ordem` a partir da posição `salto_em` adiantada em 1: um desenho dali
    foi descartado por `caminhos_da_pagina` (malformado) e não chegou à leitura."""
    return [
        dataclasses.replace(c, ordem=c.ordem + 1) if posicao >= salto_em else c
        for posicao, c in enumerate(caminhos)
    ]


_OUTRO = LinhaTexto("X", (300.0, 250.0), 5.0, cor=(1.0, 0.0, 0.0))
_VALOR = LinhaTexto("P10 N1", (40.0, 60.0), 5.0)


@pytest.mark.parametrize(
    ("linhas", "salto_em"),
    [
        ((_VALOR, _OUTRO), 5),  # descartado logo depois do último glifo
        ((_OUTRO, _VALOR), 1),  # descartado logo antes do primeiro glifo
        ((_VALOR, _OUTRO), 3),  # descartado entre "P10" e "N1"
        ((_VALOR,), 0),  # descartados os desenhos do início da página
        ((_VALOR,), None),  # descartado o último desenho da página (o "1" final)
    ],
    ids=["depois", "antes", "meio", "inicio", "fim"],
)
def test_glifo_descartado_na_extracao_envenena_o_trecho(
    tmp_path: Path, tabela: TabelaGlifos, linhas: Sequence[LinhaTexto], salto_em: int | None
) -> None:
    caminhos = caminhos_do_pdf(pdf_texto_contorno(tmp_path / "c.pdf", linhas))
    total = len(caminhos)
    assert [t.texto for t in ler_texto_glifos(caminhos, tabela, total).textos] == ["P10 N1"]

    if salto_em is None:  # sem caminho seguinte: só o total de desenhos revela o descarte
        leitura = ler_texto_glifos(caminhos[:-1], tabela, total)
    else:
        leitura = ler_texto_glifos(_renumerado(caminhos, salto_em), tabela)

    assert leitura.textos == ()
    assert leitura.desconhecidos >= 1


def test_salto_de_ordem_longe_do_trecho_nao_envenena(tmp_path: Path, tabela: TabelaGlifos) -> None:
    linhas = (_VALOR, _OUTRO, LinhaTexto("Y", (300.0, 280.0), 5.0, cor=(1.0, 0.0, 0.0)))
    caminhos = caminhos_do_pdf(pdf_texto_contorno(tmp_path / "c.pdf", linhas))

    leitura = ler_texto_glifos(_renumerado(caminhos, 6), tabela)

    assert [t.texto for t in leitura.textos] == ["P10 N1"]
    assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


@pytest.mark.parametrize("onde", ["depois", "antes"])
def test_preenchimento_grande_colado_da_mesma_cor_anula_o_texto(
    tmp_path: Path, tabela: TabelaGlifos, onde: str
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P10 N1", (40.0, 60.0), 5.0)])
    caminhos = list(caminhos_do_pdf(pdf))
    (trecho,) = extrair_trechos(caminhos)
    if onde == "depois":
        _, y0, x1, _ = trecho.glifos[-1].caixa
        caminhos.append(_retangulo_preenchido(x1 + 0.5, y0 - 2.0, 8.0, len(caminhos)))
    else:
        x0, y0, _, _ = trecho.glifos[0].caixa
        caminhos.insert(0, _retangulo_preenchido(x0 - 8.5, y0 - 2.0, 8.0, -1))

    leitura = ler_texto_glifos(caminhos, tabela)

    assert leitura.textos == ()
    assert leitura.desconhecidos >= 1


def test_preenchimento_grande_distante_ou_de_outra_cor_nao_anula_o_texto(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P10 N1", (40.0, 60.0), 5.0)])
    base = list(caminhos_do_pdf(pdf))
    _, y0, x1, _ = extrair_trechos(base)[0].glifos[-1].caixa
    colado = _retangulo_preenchido(x1 + 0.5, y0 - 2.0, 8.0, len(base))
    variantes = [
        [*base, _retangulo_preenchido(x1 + 60.0, y0, 40.0, len(base))],
        [*base, dataclasses.replace(colado, estilo=Estilo("", None, (1.0, 0.0, 0.0), 0.0, ""))],
        [*base, dataclasses.replace(colado, tipo="traco")],
    ]

    for caminhos in variantes:
        leitura = ler_texto_glifos(caminhos, tabela)
        assert [t.texto for t in leitura.textos] == ["P10 N1"]
        assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


def test_orcamento_de_pontos_da_pagina_limita_a_leitura(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P10N1", (40.0, 60.0), 5.0)])
    caminhos = caminhos_do_pdf(pdf)
    assert glyph_text.LIMITE_PONTOS_PAGINA >= 1_000_000
    assert [t.texto for t in ler_texto_glifos(caminhos, tabela).textos] == ["P10N1"]

    monkeypatch.setattr(glyph_text, "LIMITE_PONTOS_PAGINA", 50)

    assert ler_texto_glifos(caminhos, tabela) == LeituraGlifos((), 0, 0, limitada=True)


def test_pagina_hostil_de_candidatos_pesados_e_limitada_rapido(tabela: TabelaGlifos) -> None:
    # 5.000 candidatos de 256 Béziers: abaixo do teto de candidatos, acima do de pontos
    def pesado(ordem: int) -> Caminho:
        x, y = 10.0 * (ordem % 50), 10.0 * (ordem // 50)
        bezier = ItemCaminho("c", ((x, y), (x + 1, y + 1), (x + 2, y + 1), (x + 3, y)))
        estilo = Estilo("", None, (0.0, 0.0, 0.0), 0.0, "")
        return Caminho(((bezier,) * 256,), estilo, "preenchimento", ordem)

    caminhos = [pesado(i) for i in range(5_000)]
    # tempo de CPU do processo: o relogio de parede infla quando a maquina esta saturada
    inicio = time.process_time()

    leitura = ler_texto_glifos(caminhos, tabela)

    assert leitura.limitada
    assert time.process_time() - inicio < 5.0


@pytest.mark.parametrize(
    ("texto", "incerto"),
    [("P10 N1", False), ("E=612345 N=7801234", False), ("AQ", True), ("-1", True), ("Q-", True)],
)
def test_trecho_marca_quadro_incerto(tmp_path: Path, texto: str, incerto: bool) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto(texto, (40.0, 60.0), 5.0)])

    (trecho,) = extrair_trechos(caminhos_do_pdf(pdf))

    assert trecho.quadro_incerto is incerto
