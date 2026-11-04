# mypy: disable-error-code="no-untyped-call"
"""Ataques à leitura de texto por glifo e à fixture de fonte livre (Task 2 da E05)."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.glyphs import fonte_livre
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
    extrair_trechos,
    ler_texto_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Estilo,
    ItemCaminho,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-adv"))


def _ler(
    tmp_path: Path, linhas: Sequence[LinhaTexto], tabela: TabelaGlifos, **kw: int
) -> LeituraGlifos:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", linhas, **kw)
    return ler_texto_glifos(caminhos_do_pdf(pdf), tabela)


def _sem(tabela: TabelaGlifos, *caracteres: str) -> TabelaGlifos:
    glifos = tuple(g for g in tabela.glifos if g.caractere not in caracteres)
    return dataclasses.replace(tabela, glifos=glifos)


def _ignorando(tabela: TabelaGlifos, caractere: str) -> TabelaGlifos:
    glifos = tuple(
        dataclasses.replace(g, caractere=None) if g.caractere == caractere else g
        for g in tabela.glifos
    )
    return dataclasses.replace(tabela, glifos=glifos)


def _diferenca_angular(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


# --- rotação, tamanho, pares 6/9 -------------------------------------------------------------


@pytest.mark.parametrize("rotacao", [0.0, 30.0, 90.0, 180.0, 270.0])
@pytest.mark.parametrize("tamanho", [3.0, 6.0])
def test_par_6_9_e_rotulo_lidos_certos_em_qualquer_rotacao_e_tamanho(
    tmp_path: Path, tabela: TabelaGlifos, rotacao: float, tamanho: float
) -> None:
    linhas = [LinhaTexto("69 96 P7", (200.0, 150.0), tamanho, rotacao=rotacao)]

    leitura = _ler(tmp_path, linhas, tabela)

    assert [t.texto for t in leitura.textos] == ["69 96 P7"]
    assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


@pytest.mark.parametrize("rotacao_pagina", [90, 180, 270])
@pytest.mark.parametrize("rotacao", [0.0, 90.0, 180.0])
def test_pagina_girada_com_rotulo_girado_le_e_alinha_com_o_nativo(
    tmp_path: Path, tabela: TabelaGlifos, rotacao_pagina: int, rotacao: float
) -> None:
    linhas = [LinhaTexto("69 96", (200.0, 150.0), 5.0, rotacao=rotacao)]
    leitura = _ler(tmp_path, linhas, tabela, rotacao_pagina=rotacao_pagina)
    pdf = pdf_texto_nativo(tmp_path / "n.pdf", linhas, rotacao_pagina=rotacao_pagina)
    (pagina,) = extrair_modelo_desenho(pdf).paginas
    (nativo,) = pagina.textos
    (texto,) = leitura.textos

    assert texto.texto == "69 96"
    assert _diferenca_angular(texto.rotacao, nativo.rotacao) <= 2.0


@pytest.mark.parametrize("tamanho", [3.0, 4.0, 5.0, 6.0])
def test_alfabeto_completo_lido_em_todos_os_tamanhos(
    tmp_path: Path, tabela: TabelaGlifos, tamanho: float
) -> None:
    # várias linhas curtas: um trecho tem no máximo 64 glifos
    linhas = [
        LinhaTexto("ABCDEFGHIJKLM", (20.0, 40.0), tamanho),
        LinhaTexto("NOPQRSTUVWXYZ", (20.0, 80.0), tamanho),
        LinhaTexto("0123456789", (20.0, 120.0), tamanho),
        LinhaTexto("1-(2)/3.4,5=6", (20.0, 160.0), tamanho),
    ]

    leitura = _ler(tmp_path, linhas, tabela)

    assert sorted(t.texto for t in leitura.textos) == sorted(linha.texto for linha in linhas)
    assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


@pytest.mark.parametrize("ausente", list("E612345N78=-"))
def test_glifo_desconhecido_em_qualquer_posicao_nunca_gera_valor_parcial(
    tmp_path: Path, tabela: TabelaGlifos, ausente: str
) -> None:
    linha = LinhaTexto("E=612345-N7801234", (40.0, 60.0), 5.0)
    quantidade = linha.texto.count(ausente)

    leitura = _ler(tmp_path, [linha], _sem(tabela, ausente))

    assert leitura.textos == ()
    assert leitura.desconhecidos == quantidade
    assert leitura.ambiguos == 0


def test_desconhecido_conta_um_por_glifo_e_so_no_texto_que_anula(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    linhas = [LinhaTexto("3033", (40.0, 60.0), 5.0), LinhaTexto("P7", (40.0, 120.0), 5.0)]

    leitura = _ler(tmp_path, linhas, _sem(tabela, "3"))

    assert [t.texto for t in leitura.textos] == ["P7"]
    assert leitura.desconhecidos == 3


# --- ignorar ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("11--30", ["11", "30"]),
        ("1-300", ["1", "300"]),
        ("1-1", ["1", "1"]),
    ],
)
def test_ignorar_nas_pontas_ou_repetido_divide_sem_texto_vazio(
    tmp_path: Path, tabela: TabelaGlifos, texto: str, esperado: list[str]
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto(texto, (40.0, 60.0), 5.0)], _ignorando(tabela, "-"))

    assert sorted(t.texto for t in leitura.textos) == sorted(esperado)
    assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


def test_ignorar_nao_mascara_desconhecido_do_outro_lado(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    leitura = _ler(
        tmp_path,
        [LinhaTexto("11-30", (40.0, 60.0), 5.0)],
        _ignorando(_sem(tabela, "3"), "-"),
    )

    assert [t.texto for t in leitura.textos] == ["11"]
    assert leitura.desconhecidos == 1


@pytest.mark.parametrize("texto", ["-11", "11-"])
def test_ignorar_na_ponta_de_trecho_de_3_glifos_deixa_o_valor_lido(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # BUG (vermelho documentado): com 3 glifos, um deles fora da linha de base na ponta, a
    # mediana de Theil-Sen (ponto de ruptura de 29%) pega a inclinação do "-" e o quadro vira
    # ~13 graus; os três glifos viram "desconhecido" e o "11" se perde. Falha fechada (nunca
    # sai texto errado), mas o recall cai onde o plano espera "11".
    leitura = _ler(tmp_path, [LinhaTexto(texto, (40.0, 60.0), 5.0)], _ignorando(tabela, "-"))

    assert [t.texto for t in leitura.textos] == ["11"]
    assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


@pytest.mark.parametrize("texto", ["-11", "11-", "(1)", "--1", "=1", "()", "(((", "---", "-()/"])
def test_trecho_curto_de_pontuacao_nunca_vira_caractere_errado(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    leitura = _ler(tmp_path, [LinhaTexto(texto, (40.0, 60.0), 5.0)], tabela)

    # falha fechada: ou lê exatamente o que está desenhado, ou não lê nada
    assert [t.texto for t in leitura.textos] in ([], [texto])


# --- limites de trecho e de página -----------------------------------------------------------


@pytest.mark.parametrize(
    ("quantidade", "lido"), [(1, False), (2, True), (3, True), (64, True), (65, False)]
)
def test_trecho_so_e_texto_entre_2_e_64_glifos(
    tmp_path: Path, tabela: TabelaGlifos, quantidade: int, lido: bool
) -> None:
    texto = "P" * quantidade
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto(texto, (10.0, 60.0), 4.0)])
    caminhos = caminhos_do_pdf(pdf)

    leitura = ler_texto_glifos(caminhos, tabela)
    trechos = extrair_trechos(caminhos)

    if lido:
        assert [t.texto for t in leitura.textos] == [texto]
        assert [len(t.glifos) for t in trechos] == [quantidade]
    else:
        assert leitura.textos == ()
        assert trechos == ()
    assert (leitura.desconhecidos, leitura.ambiguos, leitura.limitada) == (0, 0, False)


def test_teto_de_pagina_e_inclusivo_e_conta_candidatos_fora_de_trechos(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 5 glifos num trecho + 1 candidato isolado, longe: 6 candidatos
    linhas = [LinhaTexto("P10N1", (40.0, 60.0), 5.0), LinhaTexto("P", (300.0, 250.0), 5.0)]
    caminhos = caminhos_do_pdf(pdf_texto_contorno(tmp_path / "c.pdf", linhas))

    monkeypatch.setattr(glyph_text, "LIMITE_GLIFOS_PAGINA", 6)
    no_limite = ler_texto_glifos(caminhos, tabela)
    monkeypatch.setattr(glyph_text, "LIMITE_GLIFOS_PAGINA", 5)
    acima = ler_texto_glifos(caminhos, tabela)

    assert [t.texto for t in no_limite.textos] == ["P10N1"] and not no_limite.limitada
    assert acima == LeituraGlifos((), 0, 0, limitada=True)


def test_teto_nao_conta_formas_que_nao_sao_candidatas(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P10", (40.0, 60.0), 5.0)])
    pdf2 = tmp_path / "c2.pdf"
    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        for i in range(10):
            pagina.draw_rect(pymupdf.Rect(10, 200 + 15 * i, 150, 210 + 15 * i), fill=(0, 0, 0))
        documento.save(pdf2)
    monkeypatch.setattr(glyph_text, "LIMITE_GLIFOS_PAGINA", 3)

    leitura = ler_texto_glifos(caminhos_do_pdf(pdf2), tabela)

    assert not leitura.limitada
    assert [t.texto for t in leitura.textos] == ["P10"]


# --- quebra x espaço, cor, determinismo ------------------------------------------------------


def test_espaco_alto_cola_palavras_e_espaco_baixo_separa_digitos(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    caminhos = caminhos_do_pdf(
        pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P1 N7", (40.0, 60.0), 5.0)])
    )

    colado = ler_texto_glifos(caminhos, dataclasses.replace(tabela, espaco=2.0))
    separado = ler_texto_glifos(caminhos, dataclasses.replace(tabela, espaco=0.0))

    assert [t.texto for t in colado.textos] == ["P1N7"]
    assert [t.texto for t in separado.textos] == ["P 1 N 7"]


def test_quebra_baixa_divide_em_textos_separados_e_quebra_alta_nao(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    caminhos = caminhos_do_pdf(
        pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P1 N7", (40.0, 60.0), 5.0)])
    )

    dividido = ler_texto_glifos(caminhos, dataclasses.replace(tabela, quebra=0.5))
    inteiro = ler_texto_glifos(caminhos, dataclasses.replace(tabela, quebra=1.5))

    assert [t.texto for t in dividido.textos] == ["P1", "N7"]
    assert [t.quantidade_glifos for t in dividido.textos] == [2, 2]
    assert [t.texto for t in inteiro.textos] == ["P1 N7"]


def test_texto_dividido_por_quebra_tem_bbox_e_glifos_proprios(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    caminhos = caminhos_do_pdf(
        pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("P1 N7", (40.0, 60.0), 5.0)])
    )

    esquerdo, direito = ler_texto_glifos(caminhos, dataclasses.replace(tabela, quebra=0.5)).textos

    assert esquerdo.bbox[2] < direito.bbox[0]
    assert [c for c, _ in esquerdo.glifos] == ["P", "1"]
    assert [c for c, _ in direito.glifos] == ["N", "7"]


def test_trechos_de_cor_quase_igual_no_mesmo_lugar_nao_se_fundem(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    linhas = [
        LinhaTexto("P7", (40.0, 60.0), 5.0, cor=(0.0, 0.0, 0.0)),
        LinhaTexto("N1", (47.0, 60.0), 5.0, cor=(0.0, 0.0, 0.01)),
    ]

    leitura = _ler(tmp_path, linhas, tabela)

    assert sorted(t.texto for t in leitura.textos) == ["N1", "P7"]


def test_leitura_e_deterministica_e_independe_de_leituras_anteriores(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    linhas = [
        LinhaTexto("E=612345 N=7801234", (40.0, 60.0), 5.0),
        LinhaTexto("11-300", (40.0, 120.0), 5.0, rotacao=30.0),
    ]
    caminhos = caminhos_do_pdf(pdf_texto_contorno(tmp_path / "c.pdf", linhas))

    primeira = ler_texto_glifos(caminhos, tabela)
    segunda = ler_texto_glifos(caminhos, tabela)
    com_tabela_menor = ler_texto_glifos(caminhos, _sem(tabela, "-"))
    depois = ler_texto_glifos(caminhos, tabela)

    assert primeira == segunda == depois
    assert sorted(t.texto for t in primeira.textos) == ["11-300", "E=612345 N=7801234"]
    assert [t.texto for t in com_tabela_menor.textos] == ["E=612345 N=7801234"]


def test_memoria_nao_vaza_entre_tabelas_com_rotulos_diferentes(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    trocas = {"P": "N", "N": "P"}
    trocados = tuple(
        EntradaGlifo(g.id, trocas.get(g.caractere or "", g.caractere), g.assinatura)
        for g in tabela.glifos
    )
    caminhos = caminhos_do_pdf(
        pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("PN", (40.0, 60.0), 5.0)])
    )

    com_a = ler_texto_glifos(caminhos, tabela)
    com_b = ler_texto_glifos(caminhos, dataclasses.replace(tabela, glifos=trocados))

    assert [t.texto for t in com_a.textos] == ["PN"]
    assert [t.texto for t in com_b.textos] == ["NP"]


def test_dois_glifos_com_fundos_diferentes_formam_um_trecho_de_quadro_incerto(
    tmp_path: Path,
) -> None:
    # limitação documentada: com 2 glifos de fundos diferentes ("-1") nenhum estimador resolve
    # a inclinação; o contrato é só: um trecho de 2 glifos, ordem de leitura, sem exceção.
    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("-1", (40.0, 60.0), 5.0)])

    (trecho,) = extrair_trechos(caminhos_do_pdf(pdf))

    assert [g.indice_caminho for g in trecho.glifos] == [0, 1]
    assert math.isfinite(trecho.rotacao) and 0.0 <= trecho.rotacao < 360.0
    assert trecho.altura > 0.0


# --- entradas construídas à mão --------------------------------------------------------------


def _caminho(
    pontos: Sequence[tuple[float, float]],
    ordem: int,
    *,
    cor: tuple[float, float, float] | None = (0.0, 0.0, 0.0),
    tipo: str = "preenchimento",
) -> Caminho:
    itens = tuple(
        ItemCaminho("l", (pontos[i], pontos[(i + 1) % len(pontos)])) for i in range(len(pontos))
    )
    return Caminho(
        (itens,),
        Estilo("", None, cor, 0.0, ""),
        tipo,  # type: ignore[arg-type]
        ordem,
    )


def _quadrado(x: float, ordem: int, lado: float = 2.0) -> Caminho:
    return _caminho([(x, 10), (x + lado, 10), (x + lado, 10 + lado), (x, 10 + lado)], ordem)


def test_forma_degenerada_no_meio_do_trecho_nao_derruba_a_leitura(
    tabela: TabelaGlifos,
) -> None:
    linha_fina = _caminho([(8, 10), (10, 10.2), (12, 10)], 1)
    caminhos = [_quadrado(0, 0), linha_fina, _quadrado(4, 2)]

    leitura = ler_texto_glifos(caminhos, tabela)

    assert leitura.textos == ()
    assert leitura.limitada is False


def test_coordenada_nao_finita_em_caminho_montado_a_mao_nao_e_candidata(
    tabela: TabelaGlifos,
) -> None:
    nao_finito = _caminho([(2, 10), (float("nan"), 10), (3, 12)], 1)
    caminhos = [_quadrado(0, 0), nao_finito, _quadrado(3, 2)]

    assert ler_texto_glifos(caminhos, tabela).textos == ()
    assert extrair_trechos(caminhos) == ()


def test_traco_sem_preenchimento_nao_forma_trecho(tabela: TabelaGlifos) -> None:
    caminhos = [
        _caminho([(0, 10), (2, 10), (2, 12)], 0, cor=None, tipo="traco"),
        _caminho([(3, 10), (5, 10), (5, 12)], 1, cor=None, tipo="traco"),
    ]

    assert extrair_trechos(caminhos) == ()
    assert ler_texto_glifos(caminhos, tabela) == LeituraGlifos((), 0, 0, limitada=False)


def test_ler_sem_caminhos_devolve_leitura_vazia(tabela: TabelaGlifos) -> None:
    assert ler_texto_glifos([], tabela) == LeituraGlifos((), 0, 0, limitada=False)
    assert extrair_trechos([]) == ()


# --- fixture de fonte livre ------------------------------------------------------------------


def test_interpretador_de_d_aceita_relativos_absolutos_e_repeticao_implicita() -> None:
    primeiro, segundo = fonte_livre._interpretar_d(
        "M10 20 l5 0 0 5 h-5 v-5 z M0 0 L1 0 1 1 C1 2 2 2 3 3 Z"
    )

    assert primeiro[0] == ((10.0, 20.0), (15.0, 20.0))
    assert primeiro[1] == ((15.0, 20.0), (15.0, 25.0))
    assert primeiro[2] == ((15.0, 25.0), (10.0, 25.0))
    assert primeiro[3] == ((10.0, 25.0), (10.0, 20.0))
    assert segundo[0] == ((0.0, 0.0), (1.0, 0.0))
    assert segundo[1] == ((1.0, 0.0), (1.0, 1.0))
    assert segundo[2] == ((1.0, 1.0), (1.0, 2.0), (2.0, 2.0), (3.0, 3.0))
    assert segundo[3] == ((3.0, 3.0), (0.0, 0.0))


def test_interpretador_de_d_curva_relativa_parte_do_ponto_atual() -> None:
    (sub,) = fonte_livre._interpretar_d("M10 10 c1 0 2 1 3 3")

    assert sub[0] == ((10.0, 10.0), (11.0, 10.0), (12.0, 11.0), (13.0, 13.0))


@pytest.mark.parametrize(
    "d", ["M0 0 A1 1 0 0 1 2 2", "M0 0 Q1 1 2 2", "M0 0 S1 1 2 2", "M0 0 T1 1"]
)
def test_interpretador_de_d_rejeita_comando_nao_suportado(d: str) -> None:
    with pytest.raises(ValueError, match="não suportado"):
        fonte_livre._interpretar_d(d)


@pytest.mark.parametrize("d", ["M0", "M0 0 L1", "M0 0 C1 1 2 2", "M0 0 H", "M0 0 l"])
def test_interpretador_de_d_rejeita_numeros_faltando(d: str) -> None:
    with pytest.raises(ValueError):
        fonte_livre._interpretar_d(d)


def test_interpretador_de_d_vazio_nao_tem_subcaminhos() -> None:
    assert fonte_livre._interpretar_d("") == []


def test_fixture_nao_deixa_arquivo_aberto_apos_gerar_e_ler(tmp_path: Path) -> None:
    linhas = [LinhaTexto("P10 N1", (40.0, 60.0), 5.0)]
    contorno = pdf_texto_contorno(tmp_path / "c.pdf", linhas)
    nativo = pdf_texto_nativo(tmp_path / "n.pdf", linhas)
    caminhos_do_pdf(contorno)
    tabela_do_alfabeto(tmp_path)

    for arquivo in (contorno, nativo, tmp_path / "alfabeto.pdf"):
        arquivo.unlink()  # no Windows falha se o documento seguir aberto

    assert not list(tmp_path.glob("*.pdf"))


def test_contorno_nao_tem_texto_nativo_e_nativo_tem(tmp_path: Path) -> None:
    linhas = [LinhaTexto("P10", (40.0, 60.0), 5.0)]
    with pymupdf.open(pdf_texto_contorno(tmp_path / "c.pdf", linhas)) as doc:
        assert doc[0].get_text().strip() == ""
    with pymupdf.open(pdf_texto_nativo(tmp_path / "n.pdf", linhas)) as doc:
        assert doc[0].get_text().strip() == "P10"


def test_contorno_gera_um_caminho_preenchido_por_glifo_na_cor_da_linha(tmp_path: Path) -> None:
    pdf = pdf_texto_contorno(
        tmp_path / "c.pdf", [LinhaTexto("P0 1", (40.0, 60.0), 5.0, cor=(1.0, 0.0, 0.0))]
    )

    caminhos: tuple[Any, ...] = caminhos_do_pdf(pdf)

    assert len(caminhos) == 3  # o espaço não vira caminho
    assert all(c.estilo.preenchimento == pytest.approx((1.0, 0.0, 0.0)) for c in caminhos)
    assert len(caminhos[0].subcaminhos) == 2  # "P" tem furo
    assert len(caminhos[1].subcaminhos) == 2  # "0" tem furo


def test_alfabeto_da_fixture_e_ascii_sem_repeticao() -> None:
    assert ALFABETO.isascii()
    assert len(set(ALFABETO)) == len(ALFABETO)
