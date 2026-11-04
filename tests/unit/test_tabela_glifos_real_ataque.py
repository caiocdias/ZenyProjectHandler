"""Ataques à tabela de glifos real empacotada (tabela-glifos-v1, publicada da rodada de glifos):
identidade, ausência de dados de folha, coerência interna e leitura de contorno sintético.

Nenhum teste lê PDF de examples/: a leitura usa a fonte livre das fixtures (Helvetica em
contorno), que tem as mesmas métricas da Arial das folhas e que a tabela real reconhece.
"""

from __future__ import annotations

import json
import math
import random
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    caminhos_do_pdf,
    pdf_texto_contorno,
)

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis.drawing_model import glyph_signature, glyph_table
from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import AssinaturaGlifo
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
    resolver_glifo,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import ler_texto_glifos
from zeny_project_handler.adapters.analysis.drawing_model.model import Ponto

# sha256 (LF) da tabela publicada e medida no benchmark da Task 6 (relatório do desenvolvedor)
_SHA_PUBLICADO = "39a80899b21d93a2f7b8c0c1a6b30f9258ee9794cf5c4084019f59df25c19421"
_CHAVES_JSON = {
    "schema_version",
    "versao",
    "tolerancia",
    "margem_ambiguidade",
    "espaco",
    "quebra",
    "glifos",
    "id",
    "caractere",
    "assinatura",
    "subcaminhos",
    "caixa",
    "contornos",
}


@pytest.fixture(scope="module")
def tabela() -> TabelaGlifos:
    return carregar_tabela_glifos()


def _bruto() -> Any:
    arquivo = Path(glyph_table.__file__).parent.parent / "data" / "tabela-glifos-v1.json"
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _percorrer(valor: Any) -> Iterator[tuple[str | None, Any]]:
    """(chave do objeto que contém, valor) de cada folha do JSON."""
    if isinstance(valor, dict):
        for chave, item in valor.items():
            if isinstance(item, dict | list):
                yield from _percorrer(item)
            else:
                yield chave, item
    elif isinstance(valor, list):
        for item in valor:
            yield from _percorrer(item) if isinstance(item, dict | list) else iter([(None, item)])


def _chaves(valor: Any) -> Iterator[str]:
    if isinstance(valor, dict):
        for chave, item in valor.items():
            yield chave
            yield from _chaves(item)
    elif isinstance(valor, list):
        for item in valor:
            yield from _chaves(item)


def _ler(tmp_path: Path, tabela: TabelaGlifos, texto: str, tamanho: float) -> list[str]:
    pdf = pdf_texto_contorno(tmp_path / "t.pdf", [LinhaTexto(texto, (150.0, 150.0), tamanho)])
    leitura = ler_texto_glifos(caminhos_do_pdf(pdf), tabela)
    pdf.unlink()
    return [lido.texto for lido in leitura.textos]


# --- identidade ---------------------------------------------------------------------------------


def test_tabela_empacotada_e_a_publicada_e_medida_no_benchmark(tabela: TabelaGlifos) -> None:
    assert tabela.sha256 == _SHA_PUBLICADO
    contagem = Counter(g.caractere for g in tabela.glifos)
    assert len(tabela.glifos) == 354
    assert contagem[None] == 1
    assert len([c for c in contagem if c is not None]) == 74


def test_assinatura_de_capacidade_do_servidor_usa_a_tabela_publicada() -> None:
    pacote = PyMuPdfDocumentAnalyzer(tabela_glifos="pacote")
    explicita = PyMuPdfDocumentAnalyzer(tabela_glifos=carregar_tabela_glifos())
    desativada = PyMuPdfDocumentAnalyzer(tabela_glifos=None)
    assert pacote.assinatura_capacidade == explicita.assinatura_capacidade
    assert pacote.assinatura_capacidade != desativada.assinatura_capacidade


# --- sem dados de folha -------------------------------------------------------------------------


def test_json_empacotado_so_tem_as_chaves_do_formato() -> None:
    assert set(_chaves(_bruto())) <= _CHAVES_JSON


def test_textos_do_json_sao_so_ids_sequenciais_opacos_e_caracteres_soltos() -> None:
    # nenhum texto livre: nada de caminho, nome de arquivo, id de PDF ou de rodada
    bruto = _bruto()
    textos = [(chave, v) for chave, v in _percorrer(bruto) if isinstance(v, str)]
    ids = [v for chave, v in textos if chave == "id"]
    assert ids == [f"g{n:04d}" for n in range(1, len(bruto["glifos"]) + 1)]
    for chave, valor in textos:
        if chave == "caractere":
            assert len(valor) == 1
        else:
            assert (chave, valor) == ("versao", "tabela-glifos-v1") or chave == "id"


def test_numeros_do_json_sao_relativos_ao_glifo_e_nao_coordenadas_de_pagina() -> None:
    bruto = _bruto()
    for glifo in bruto["glifos"]:
        assinatura = glifo["assinatura"]
        for contorno in assinatura["contornos"]:
            for x, y in contorno:
                assert abs(x) <= 1.0 and abs(y) <= 1.0
        assert all(abs(v) <= 2.0 for v in assinatura["caixa"])
        assert assinatura["caixa"][0] > 0 and assinatura["caixa"][1] > 0


def test_json_empacotado_nao_cita_pasta_de_exemplos_nem_de_rodada() -> None:
    arquivo = Path(glyph_table.__file__).parent.parent / "data" / "tabela-glifos-v1.json"
    texto = arquivo.read_text(encoding="utf-8").lower()
    for proibido in ("examples", "curadoria", "rodada", "users", ".json", "tmp", ":\\\\"):
        assert proibido not in texto


# --- coerência interna --------------------------------------------------------------------------


def test_cada_entrada_publicada_resolve_para_o_proprio_caractere(tabela: TabelaGlifos) -> None:
    divergentes = []
    for entrada in tabela.glifos:
        r = resolver_glifo(tabela, entrada.assinatura)
        esperado = "ignorar" if entrada.caractere is None else "reconhecido"
        if (r.situacao, r.caractere) != (esperado, entrada.caractere):
            divergentes.append((entrada.id, entrada.caractere, r.situacao, r.caractere))
    assert divergentes == []


# --- leitura de contorno sintético --------------------------------------------------------------


@pytest.mark.parametrize("tamanho", [3.0, 5.0, 7.0])
@pytest.mark.parametrize("texto", ["0123456789", "11-300", "P7", "69 96", "N1 N2"])
def test_tabela_real_le_algarismos_e_valores_de_poste_em_contorno(
    tmp_path: Path, tabela: TabelaGlifos, texto: str, tamanho: float
) -> None:
    assert _ler(tmp_path, tabela, texto, tamanho) == [texto]


def test_analisador_com_a_tabela_do_pacote_emite_o_texto_de_glifo(tmp_path: Path) -> None:
    from scripts.benchmark_texto_ficha import _solicitacao, _texto_da_evidencia

    pdf = pdf_texto_contorno(tmp_path / "c.pdf", [LinhaTexto("11-300", (40.0, 120.0), 5.0)])
    resultado = PyMuPdfDocumentAnalyzer(tabela_glifos="pacote").analisar(_solicitacao(pdf))
    medidos = [m for e in resultado.evidencias if (m := _texto_da_evidencia(e)) is not None]
    assert [(m.texto, m.origem) for m in medidos] == [("11-300", "glifo")]


# --- defeitos: a tabela real afirma texto errado ------------------------------------------------


@pytest.mark.parametrize("texto", ["BI-1", "IP 11", "II7I"])
def test_i_maiusculo_nunca_e_afirmado_como_l_minusculo(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # Na Helvetica/Arial "I" e "l" são a mesma barra; a tabela publica as duas letras para
    # barras quase iguais e decide pelo ruído da caixa: o certo é ler "I" ou falhar fechado.
    # (O mesmo acontece em corpo 3 e 7.)
    lidos = _ler(tmp_path, tabela, texto, 5.0)
    assert lidos in ([texto], [])


@pytest.mark.parametrize("texto", ["11-214", "11-147", "1171", "11"])
def test_par_11_nao_e_partido_quando_o_texto_so_tem_algarismos_planos(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # "11-300" é lido inteiro (teste acima); sem algarismo redondo a altura da linha cai ~3% e a
    # lacuna "1"+"1" (0.417 h com "3"/"0") passa a 0.4302 h, acima de 0.43: o texto sai com
    # um espaço a mais. (O mesmo acontece em corpo 3 e 7.)
    lidos = _ler(tmp_path, tabela, texto, 5.0)
    assert lidos in ([texto], [])
    assert re.search(r"\d \d", " ".join(lidos)) is None


# --- rodada 1: escala das lacunas, espaço 0.48 e homóglifos fora -------------------------------

# contagem de cada algarismo na tabela antes da exclusão de homóglifos (publicação de 9fd1454)
_ALGARISMOS_PUBLICADOS = {
    "0": 14,
    "1": 11,
    "2": 7,
    "3": 15,
    "4": 10,
    "5": 9,
    "6": 4,
    "7": 8,
    "8": 5,
    "9": 3,
}
# altura de corpo do "1" (e dos algarismos planos) da fonte livre em corpo 5
_H_CORPO_5 = 3.615


def test_exclusao_de_homoglifos_nao_tira_nenhum_algarismo(tabela: TabelaGlifos) -> None:
    contagem = Counter(g.caractere for g in tabela.glifos)
    assert {c: contagem[c] for c in "0123456789"} == _ALGARISMOS_PUBLICADOS


@pytest.mark.parametrize("contexto", ["{}-300", "300-{}", "N{}", "({})"])
def test_todo_par_de_algarismos_e_lido_inteiro_em_qualquer_vizinhanca(
    tmp_path: Path, tabela: TabelaGlifos, contexto: str
) -> None:
    # a escala nova não pode depender de quais glifos estão no texto: nenhum par de algarismos
    # ganha espaço nem é trocado, com ou sem glifo redondo ao lado
    errados = []
    for a in "0123456789":
        for b in "0123456789":
            texto = contexto.format(a + b)
            lidos = _ler(tmp_path, tabela, texto, 5.0)
            if lidos != [texto]:
                errados.append((texto, lidos))
    assert errados == []


def _borda(tmp_path: Path, tabela: TabelaGlifos, texto: str, origem_x: float) -> float:
    """Com origem 0, a borda esquerda do primeiro glifo; senão, a direita do último."""
    pdf = pdf_texto_contorno(tmp_path / "b.pdf", [LinhaTexto(texto, (origem_x, 150.0), 5.0)])
    leitura = ler_texto_glifos(caminhos_do_pdf(pdf), tabela)
    pdf.unlink()
    (lido,) = leitura.textos
    return float(lido.glifos[-1][1][2] if origem_x else lido.glifos[0][1][0])


@pytest.mark.parametrize(
    ("esquerda", "direita"),
    [("11", "300"), ("300", "11"), ("11", "11"), ("300", "300"), ("1171", "1171")],
)
@pytest.mark.parametrize(("lacuna_h", "separa"), [(0.45, False), (0.51, True)])
def test_lacuna_decide_o_espaco_igual_com_glifos_redondos_de_um_lado_so(
    tmp_path: Path,
    tabela: TabelaGlifos,
    esquerda: str,
    direita: str,
    lacuna_h: float,
    separa: bool,
) -> None:
    # Glifos redondos só de um lado inclinam o quadro (~0.6°) e mudam a escala em ~1%; o limiar
    # efetivo medido fica entre 0.475 e 0.485 h. Lacuna de 0.45 h nunca vira espaço e de 0.51 h
    # sempre vira, qualquer que seja a vizinhança.
    fim = _borda(tmp_path, tabela, esquerda, 100.0)
    inicio = _borda(tmp_path, tabela, direita, 0.0)
    x = fim + lacuna_h * _H_CORPO_5 - inicio
    linhas = [LinhaTexto(esquerda, (100.0, 150.0), 5.0), LinhaTexto(direita, (x, 150.0), 5.0)]
    pdf = pdf_texto_contorno(tmp_path / "l.pdf", linhas)
    leitura = ler_texto_glifos(caminhos_do_pdf(pdf), tabela)
    esperado = f"{esquerda} {direita}" if separa else esquerda + direita
    assert [t.texto for t in leitura.textos] == [esperado]


@pytest.mark.parametrize("texto", ["OO7O", "O0O", "OoO", "ava", "vav", "awa", "aza", "aIa"])
def test_maiuscula_e_minuscula_de_mesmo_desenho_nunca_sao_trocadas(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # A exclusão de homóglifos tirou só o par mais próximo de cada caso; seguem publicadas
    # variantes de mesmo desenho (S/s a 0.0401 de contorno, O/o a 0.0454, C/c a 0.0488) e
    # letras sem a outra caixa na tabela (W, Z): quando a altura da linha vem das próprias
    # letras, a forma casa a variante do outro caso. O certo é ler o texto ou falhar fechado.
    # (O mesmo acontece em corpo 3 e 7.)
    lidos = _ler(tmp_path, tabela, texto, 5.0)
    assert lidos in ([texto], [])


@pytest.mark.parametrize("texto", ["QQ7Q", "Q0Q"])
def test_q_maiusculo_nunca_e_afirmado_como_o_minusculo(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    lidos = _ler(tmp_path, tabela, texto, 5.0)
    assert lidos in ([texto], [])


# --- rodada 3: altura relativa a h, desenho empatado e homóglifos pelo resolvedor -------------


def test_ruido_de_caixa_ate_0_05_nunca_leva_uma_entrada_a_outro_caractere(
    tabela: TabelaGlifos,
) -> None:
    # Cada entrada publicada com largura, altura ou base deslocada em ±0.05 h (abaixo do p99.5
    # legítimo de altura, 0.053) é um glifo plausível daquele caractere: a resolução pode falhar
    # fechada, mas nunca afirmar outro caractere.
    trocados = []
    for entrada in tabela.glifos:
        assinatura = entrada.assinatura
        for eixo in range(3):
            for delta in (-0.05, 0.05):
                caixa = list(assinatura.caixa)
                caixa[eixo] += delta
                ruidosa = AssinaturaGlifo(
                    assinatura.subcaminhos, (caixa[0], caixa[1], caixa[2]), assinatura.contornos
                )
                r = resolver_glifo(tabela, ruidosa)
                if r.situacao in ("reconhecido", "ignorar") and r.caractere != entrada.caractere:
                    trocados.append((entrada.id, entrada.caractere, eixo, delta, r.caractere))
    assert trocados == []


_CONTEXTOS_DE_ALTURA = [
    "({})",
    "{})",
    "l{}",
    "{}g",
    "{}j",
    "{}q",
    "{}p",
    "{}y",
    "{}Á",
    "{}Ç",
    "{}°",
    "e{}",
    "a{}",
    "s{}",
    "t{}",
    "{}m",
    "{}A",
    "h{}",
    "b{}d",
]


@pytest.mark.parametrize("contexto", _CONTEXTOS_DE_ALTURA)
def test_algarismo_ao_lado_de_letra_alta_baixa_ou_acentuada_nunca_e_trocado(
    tmp_path: Path, tabela: TabelaGlifos, contexto: str
) -> None:
    # vizinhos com ascendente, descendente, acento ou parêntese mudam o h do trecho; a condição
    # de altura não pode trocar o algarismo nem a letra (falhar fechado é aceitável)
    errados = []
    for algarismo in "0123456789":
        texto = contexto.format(algarismo)
        lidos = _ler(tmp_path, tabela, texto, 5.0)
        if lidos not in ([texto], []):
            errados.append((texto, lidos))
    assert errados == []


@pytest.mark.parametrize("texto", ["ew", "we", "ez", "ze"])
def test_minuscula_sem_entrada_na_tabela_nunca_vira_a_maiuscula(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # A tabela não tem "w" nem "z"; com o h do trecho vindo de "e", a forma minúscula fica a
    # Δaltura 0.023 de "W"/"Z" (dentro de 0.055) e é afirmada maiúscula. "awa"/"aza" falham
    # fechados só porque o "a" muda o h. (O mesmo em corpo 3 e 7.)
    lidos = _ler(tmp_path, tabela, texto, 5.0)
    assert lidos in ([texto], [])


def test_l_minusculo_ao_lado_de_algarismos_nunca_vira_i_maiusculo(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    # "l" com h dos algarismos tem altura 1.028; o "I" restante da tabela casa a 0.0598 com
    # Δaltura 0.049 (dentro de 0.055), e a variante de "l" que sobrou (1.368 h) não concorre.
    lidos = _ler(tmp_path, tabela, "l-77", 5.0)
    assert lidos in (["l-77"], [])


@pytest.mark.parametrize("texto", ["f0", "f8"])
def test_f_ao_lado_de_algarismo_nunca_e_afirmado_como_t(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # o "f" da fonte livre fica a 0.075 de "t" (tolerância 0.08) e longe dos "f" publicados
    lidos = _ler(tmp_path, tabela, texto, 5.0)
    assert lidos in ([texto], [])


# --- rodada 4: forma decide, escala coerente no trecho, abandono antecipado -------------------


def _distancia_contorno_completa(a: Sequence[Ponto], b: Sequence[Ponto]) -> float:
    """Referência sem abandono: média ponto a ponto, mínima sobre os deslocamentos cíclicos de
    `b` e dos seus pontos médios (a definição da docstring), somando na mesma ordem."""
    n = len(a)
    medios = [
        ((b[i][0] + b[(i + 1) % n][0]) / 2.0, (b[i][1] + b[(i + 1) % n][1]) / 2.0) for i in range(n)
    ]
    melhor = math.inf
    for alvo in (b, medios):
        for deslocamento in range(n):
            soma = 0.0
            for i in range(n):
                soma += math.dist(a[i], alvo[(i + deslocamento) % n])
            melhor = min(melhor, soma / n)
    return melhor


def test_abandono_antecipado_da_distancia_de_contorno_da_o_mesmo_valor(
    tabela: TabelaGlifos,
) -> None:
    contornos = [c for g in tabela.glifos for c in g.assinatura.contornos]
    sorteio = random.Random(11)
    pares = [(sorteio.choice(contornos), sorteio.choice(contornos)) for _ in range(1500)]
    for _ in range(500):
        a = sorteio.choice(contornos)
        ruidoso = tuple(
            (x + sorteio.uniform(-0.03, 0.03), y + sorteio.uniform(-0.03, 0.03)) for x, y in a
        )
        pares += [(a, ruidoso), (ruidoso, a), (a, a)]
    diferentes = [
        (a, b)
        for a, b in pares
        if glyph_signature._distancia_contorno(a, b) != _distancia_contorno_completa(a, b)
    ]
    assert diferentes == []


@pytest.mark.parametrize("rotacao", [0.0, 90.0, 180.0])
@pytest.mark.parametrize("tamanho", [3.0, 5.0, 7.0])
def test_texto_so_de_algarismos_nunca_vira_letra_nem_outro_numero(
    tmp_path: Path, tabela: TabelaGlifos, tamanho: float, rotacao: float
) -> None:
    # repetições do mesmo algarismo (o caso em que a escala vem de um caractere só) e valores
    # típicos de campo: ler certo ou falhar fechado
    textos = [d * k for d in "0123456789" for k in (2, 3)]
    textos += ["11-300", "13,8", "4/0", "2x1/0", "(10)", "0.5", "69", "96", "86", "18"]
    errados = []
    for texto in textos:
        pdf = pdf_texto_contorno(
            tmp_path / "d.pdf", [LinhaTexto(texto, (150.0, 150.0), tamanho, rotacao=rotacao)]
        )
        lidos = [t.texto for t in ler_texto_glifos(caminhos_do_pdf(pdf), tabela).textos]
        pdf.unlink()
        if lidos not in ([texto], []):
            errados.append((texto, lidos))
    assert errados == []


@pytest.mark.parametrize("texto", ["lzz", "zzl", "lww", "wwl"])
def test_letra_publicada_so_na_escala_x_nao_esconde_a_escala_do_trecho(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # O único "l" publicado foi colhido com h = altura-x (1.368 h); a menor altura do "l" é essa
    # mesma, então o "l" de um trecho com h = altura-x dá razão ~1.0 e é tomado como escala de
    # maiúscula. "zz"/"ww" na altura-x casam "Z"/"W" de maiúscula e o trecho parece coerente.
    # (O mesmo em corpo 3 e 7.)
    lidos = _ler(tmp_path, tabela, texto, 5.0)
    assert lidos in ([texto], [])


@pytest.mark.parametrize("texto", ["gg", "jj", "ww", "zz", "gg 10"])
def test_trecho_de_uma_minuscula_repetida_nunca_e_afirmado_trocado(
    tmp_path: Path, tabela: TabelaGlifos, texto: str
) -> None:
    # Resíduo declarado pelo desenvolvedor na Rodada 4: sem outro glifo, a escala e a base do
    # trecho vêm da própria letra. "gg" sai "99" (inventa algarismos, também com "10" ao lado),
    # "jj" sai "ii", "ww"/"zz" saem maiúsculas. (O mesmo em corpo 3 e 7, rotação 0 e 90.)
    lidos = _ler(tmp_path, tabela, texto, 5.0)
    assert lidos in ([texto], [])


# --- rodada 5: base fora da janela de forma, âncora de escala ---------------------------------


def _ler_girado(
    tmp_path: Path, tabela: TabelaGlifos, texto: str, tamanho: float, rotacao: float
) -> list[str]:
    linha = LinhaTexto(texto, (150.0, 150.0), tamanho, rotacao=rotacao)
    pdf = pdf_texto_contorno(tmp_path / "r.pdf", [linha])
    lidos = [t.texto for t in ler_texto_glifos(caminhos_do_pdf(pdf), tabela).textos]
    pdf.unlink()
    return lidos


@pytest.mark.parametrize("rotacao", [0.0, 90.0])
@pytest.mark.parametrize("sinal", list(",.:'\"°/-"))
def test_pontuacao_com_a_base_fora_da_janela_nunca_troca(
    tmp_path: Path, tabela: TabelaGlifos, sinal: str, rotacao: float
) -> None:
    # a base deixou de restringir a disputa de forma: "," e "'", "." e "°" têm desenho parecido
    # em alturas diferentes da linha; podem falhar fechados, nunca trocar um pelo outro
    textos = [f"13{sinal}8", f"{sinal}10", f"10{sinal}", f"N1{sinal}N2", f"P{sinal}7", sinal * 2]
    errados = []
    for texto in textos:
        lidos = _ler_girado(tmp_path, tabela, texto, 5.0, rotacao)
        if lidos not in ([texto], []):
            errados.append((texto, lidos))
    assert errados == []


@pytest.mark.parametrize("tamanho", [3.0, 5.0, 7.0])
def test_algarismo_repetido_e_lido_sem_perda(
    tmp_path: Path, tabela: TabelaGlifos, tamanho: float
) -> None:
    # trecho de um caractere só, sem âncora: o algarismo não tem par de caixa e a forma com a
    # escala igualada confirma; "11", "000", "8888" têm de sair lidos, não só "não trocados"
    perdidos = []
    for algarismo in "0123456789":
        for vezes in (2, 3, 4):
            texto = algarismo * vezes
            lidos = _ler_girado(tmp_path, tabela, texto, tamanho, 0.0)
            if lidos != [texto]:
                perdidos.append((texto, lidos))
    assert perdidos == []


@pytest.mark.parametrize("vezes", [2, 3])
def test_letra_repetida_sozinha_no_trecho_nunca_e_trocada(
    tmp_path: Path, tabela: TabelaGlifos, vezes: int
) -> None:
    # todas as letras, maiúsculas e minúsculas, sozinhas e repetidas (o caso sem âncora)
    errados = []
    for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
        texto = letra * vezes
        lidos = _ler_girado(tmp_path, tabela, texto, 5.0, 0.0)
        if lidos not in ([texto], []):
            errados.append((texto, lidos))
    assert errados == []
