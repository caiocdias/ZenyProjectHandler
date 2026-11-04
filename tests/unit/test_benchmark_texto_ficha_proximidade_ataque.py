"""Ataques às contagens de acerto perto do poste (≤ 0.05 e ≤ 0.10) do recall de texto da ficha:
limites inclusivos, cumulatividade, centro da caixa, ocorrência atribuída, agregação e markdown
(valores inventados; PDFs sintéticos lidos com a tabela empacotada)."""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import pytest
from scripts.benchmark_texto_ficha import TextoMedido, main, medir_texto
from tests.fixtures.glyphs.fonte_livre import LinhaTexto, pdf_texto_contorno, pdf_texto_nativo

from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    carregar_tabela_glifos,
)

_CAMPOS = ("identificador", "poste", "estruturas", "coordenada")


def _poste_caixa(
    bbox: list[float],
    *,
    identificador: str | None = None,
    poste: str | None = None,
    estruturas: tuple[str, ...] = (),
    id_: str = "P1",
    pagina: int = 1,
) -> dict[str, Any]:
    return {
        "id": id_,
        "pagina": pagina,
        "bbox": bbox,
        "identificador": identificador,
        "estruturas": list(estruturas),
        "poste": poste,
        "coordenada": None,
        "simbolos": [],
        "pendentes": [],
    }


def _no_ponto(x: float, y: float, **campos: Any) -> dict[str, Any]:
    """Poste de caixa degenerada: o centro é exatamente (x, y), sem arredondamento."""
    return _poste_caixa([x, y, x, y], **campos)


def _t(texto: str, centro: tuple[float, float]) -> TextoMedido:
    return TextoMedido(texto, centro, "nativo")


def _proximos(r: dict[str, dict[str, int]], campo: str) -> tuple[int, int, int]:
    c = r[campo]
    return c["acertos"], c["acertos_ate_005"], c["acertos_ate_010"]


# --- limites ------------------------------------------------------------------------------------


def test_acerto_exatamente_a_0_05_conta_nas_duas_faixas() -> None:
    ref = {"postes": [_no_ponto(0.0, 0.0, poste="P7")]}
    r = medir_texto(ref, [_t("P7", (0.05, 0.0))])
    assert _proximos(r, "poste") == (1, 1, 1)


def test_acerto_logo_acima_de_0_05_so_conta_ate_0_10() -> None:
    ref = {"postes": [_no_ponto(0.0, 0.0, poste="P7")]}
    r = medir_texto(ref, [_t("P7", (math.nextafter(0.05, 1.0), 0.0))])
    assert _proximos(r, "poste") == (1, 0, 1)


def test_acerto_exatamente_a_0_10_conta_so_ate_0_10() -> None:
    ref = {"postes": [_no_ponto(0.0, 0.0, poste="P7")]}
    r = medir_texto(ref, [_t("P7", (0.0, 0.1))])
    assert _proximos(r, "poste") == (1, 0, 1)


def test_acerto_logo_acima_de_0_10_e_so_presente_na_pagina() -> None:
    ref = {"postes": [_no_ponto(0.0, 0.0, poste="P7")]}
    r = medir_texto(ref, [_t("P7", (0.0, math.nextafter(0.1, 1.0)))])
    assert _proximos(r, "poste") == (1, 0, 0)


def test_distancia_e_euclidiana_e_nao_por_eixo() -> None:
    # 0.04 em cada eixo: cada eixo cabe em 0.05, a distância (0.0566) não
    ref = {"postes": [_no_ponto(0.0, 0.0, poste="P7")]}
    r = medir_texto(ref, [_t("P7", (0.04, 0.04))])
    assert _proximos(r, "poste") == (1, 0, 1)


@pytest.mark.parametrize(
    ("centro_texto", "esperado"),
    [
        ((0.6, 0.5), (1, 0, 1)),  # encosta na borda direita, a 0.10 do centro
        ((0.61, 0.61), (1, 0, 0)),  # a 0.014 do canto, a 0.156 do centro
    ],
)
def test_distancia_e_ao_centro_da_caixa_do_poste_e_nao_a_borda_nem_ao_canto(
    centro_texto: tuple[float, float], esperado: tuple[int, int, int]
) -> None:
    ref = {"postes": [_poste_caixa([0.4, 0.4, 0.6, 0.6], poste="P7")]}
    r = medir_texto(ref, [_t("P7", centro_texto)])
    assert _proximos(r, "poste") == esperado


# --- qual ocorrência mede -----------------------------------------------------------------------


def test_proximidade_e_da_ocorrencia_atribuida_e_nao_de_qualquer_ocorrencia() -> None:
    # os dois postes têm a estrutura N1; a única ocorrência perto de B é tomada por A, que está
    # mais perto dela, e B fica com a ocorrência distante: acerto de B não conta como próximo
    a = _no_ponto(0.50, 0.50, estruturas=("N1",), id_="A")
    b = _no_ponto(0.50, 0.53, estruturas=("N1",), id_="B")
    textos = [_t("N1", (0.50, 0.505)), _t("N1", (0.95, 0.95))]
    r = medir_texto({"postes": [a, b]}, textos)
    assert _proximos(r, "estruturas") == (2, 1, 1)


def test_valor_repetido_perto_e_longe_mede_a_ocorrencia_mais_proxima() -> None:
    ref = {"postes": [_no_ponto(0.5, 0.5, poste="P7")]}
    r = medir_texto(ref, [_t("P7", (0.9, 0.9)), _t("P7", (0.5, 0.52))])
    assert _proximos(r, "poste") == (1, 1, 1)


def test_valor_dentro_de_texto_longo_mede_o_centro_do_texto_inteiro() -> None:
    # o benchmark mede pelo centro da evidência de texto, não pela posição do valor dentro dela
    ref = {"postes": [_no_ponto(0.0, 0.0, poste="P7")]}
    r = medir_texto(ref, [_t("P7 E MAIS UM MONTE DE PALAVRAS", (0.2, 0.0))])
    assert _proximos(r, "poste") == (1, 0, 0)


def test_erro_afirmado_perto_do_poste_nao_conta_como_acerto_proximo() -> None:
    ref = {"postes": [_no_ponto(0.5, 0.5, poste="11-300")]}
    r = medir_texto(ref, [_t("11-301", (0.5, 0.5))])
    assert r["poste"] == {
        "total": 1,
        "acertos": 0,
        "erros_afirmados": 1,
        "acertos_ate_005": 0,
        "acertos_ate_010": 0,
    }


def test_proximidade_de_um_campo_nao_vaza_para_outro() -> None:
    ref = {"postes": [_no_ponto(0.5, 0.5, poste="P7", estruturas=("N1",))]}
    r = medir_texto(ref, [_t("P7", (0.5, 0.5)), _t("N1", (0.9, 0.9))])
    assert _proximos(r, "poste") == (1, 1, 1)
    assert _proximos(r, "estruturas") == (1, 0, 0)
    assert _proximos(r, "identificador") == (0, 0, 0)


# --- invariantes --------------------------------------------------------------------------------


@pytest.mark.parametrize("semente", range(25))
def test_cumulativo_005_nao_passa_010_que_nao_passa_acertos(semente: int) -> None:
    sorteio = random.Random(semente)
    valores = ["N1", "N2", "P7", "11-300", "A B"]
    postes = [
        _no_ponto(
            sorteio.random(),
            sorteio.random(),
            identificador=sorteio.choice(valores),
            poste=sorteio.choice(valores),
            estruturas=tuple(sorteio.sample(valores, 2)),
            id_=f"P{i}",
        )
        for i in range(4)
    ]
    textos = [_t(sorteio.choice(valores), (sorteio.random(), sorteio.random())) for _ in range(12)]
    r = medir_texto({"postes": postes}, textos)
    assert list(r) == list(_CAMPOS)
    for contagem in r.values():
        assert all(type(v) is int for v in contagem.values())
        assert 0 <= contagem["acertos_ate_005"] <= contagem["acertos_ate_010"]
        assert contagem["acertos_ate_010"] <= contagem["acertos"] <= contagem["total"]
        assert contagem["acertos"] + contagem["erros_afirmados"] <= contagem["total"]


def test_tudo_no_centro_do_poste_conta_em_todas_as_faixas() -> None:
    ref = {"postes": [_no_ponto(0.3, 0.7, identificador="X1", poste="P7", estruturas=("N1",))]}
    textos = [_t(v, (0.3, 0.7)) for v in ("X1", "P7", "N1")]
    r = medir_texto(ref, textos)
    for campo in ("identificador", "poste", "estruturas"):
        assert _proximos(r, campo) == (1, 1, 1)


# --- CLI com a tabela empacotada ----------------------------------------------------------------

# Página de 400 x 300 pt. "P7" com origem (40, 60) tem centro perto de (0.108, 0.194); o poste
# fica nesse centro. "11-300" 21 pt abaixo fica a ~0.07 dele (entre 0.05 e 0.10) e "N1" no
# canto oposto, a mais de 0.7: presente na página, longe do poste.
_LINHAS = [
    LinhaTexto("P7", (40.0, 60.0), 5.0),
    LinhaTexto("11-300", (40.0, 81.0), 5.0),
    LinhaTexto("N1", (340.0, 270.0), 5.0),
]
_CENTRO_POSTE = (0.108, 0.194)
_ESPERADO = {
    "poste": {
        "total": 1,
        "acertos": 1,
        "erros_afirmados": 0,
        "acertos_ate_005": 1,
        "acertos_ate_010": 1,
    },
    "estruturas": {
        "total": 1,
        "acertos": 1,
        "erros_afirmados": 0,
        "acertos_ate_005": 0,
        "acertos_ate_010": 1,
    },
    "identificador": {
        "total": 1,
        "acertos": 1,
        "erros_afirmados": 0,
        "acertos_ate_005": 0,
        "acertos_ate_010": 0,
    },
    "coordenada": {
        "total": 0,
        "acertos": 0,
        "erros_afirmados": 0,
        "acertos_ate_005": 0,
        "acertos_ate_010": 0,
    },
}
_ZERADO_DE_ACERTOS = {
    campo: {**c, "acertos": 0, "acertos_ate_005": 0, "acertos_ate_010": 0}
    for campo, c in _ESPERADO.items()
}


def _referencia(rodada: Path, pdf_id: str, pdf: Path) -> None:
    pasta = rodada / "pdfs" / pdf_id / "ficha"
    pasta.mkdir(parents=True)
    x, y = _CENTRO_POSTE
    poste = _poste_caixa(
        [x - 0.004, y - 0.004, x + 0.004, y + 0.004],
        identificador="N1",
        poste="P7",
        estruturas=("11-300",),
    )
    ficha = {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [poste],
        "vaos": [],
    }
    (pasta / "referencia.json").write_text(json.dumps(ficha), encoding="utf-8")


@pytest.fixture(scope="module")
def relatorio(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], str]:
    raiz = tmp_path_factory.mktemp("proximidade")
    pasta = raiz / "origem"
    pasta.mkdir()
    nativo = pdf_texto_nativo(pasta / "a.pdf", _LINHAS)
    contorno = pdf_texto_contorno(pasta / "b.pdf", _LINHAS)
    rodada = raiz / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    _referencia(rodada, "002-bbbbbbbbbbbb", contorno)
    saida = raiz / "saida"
    # sem --tabela: mede com a tabela empacotada real, como o servidor
    assert main(["--rodada", str(rodada), "--pdfs", str(pasta), "--saida", str(saida)]) == 0
    dados: dict[str, Any] = json.loads((saida / "texto-ficha.json").read_text(encoding="utf-8"))
    return dados, (saida / "texto-ficha.md").read_text(encoding="utf-8")


def test_cli_nativo_conta_perto_e_longe_do_poste(relatorio: tuple[dict[str, Any], str]) -> None:
    dados, _ = relatorio
    fontes = dados["por_pdf"]["001-aaaaaaaaaaaa"]["fontes"]
    assert fontes["base"] == _ESPERADO
    assert fontes["novo"] == _ESPERADO


def test_cli_contorno_lido_pela_tabela_empacotada_conta_perto_e_longe(
    relatorio: tuple[dict[str, Any], str],
) -> None:
    dados, _ = relatorio
    fontes = dados["por_pdf"]["002-bbbbbbbbbbbb"]["fontes"]
    assert fontes["base"] == _ZERADO_DE_ACERTOS
    assert fontes["novo"] == _ESPERADO
    assert dados["tabela_sha256"] == carregar_tabela_glifos().sha256


def test_cli_total_e_familias_somam_as_contagens_de_proximidade(
    relatorio: tuple[dict[str, Any], str],
) -> None:
    dados, _ = relatorio
    for fonte in ("base", "novo"):
        for campo in _CAMPOS:
            for chave in _ESPERADO[campo]:
                por_pdf = sum(b["fontes"][fonte][campo][chave] for b in dados["por_pdf"].values())
                por_familia = sum(b[fonte][campo][chave] for b in dados["por_familia"].values())
                assert dados["total"][fonte][campo][chave] == por_pdf == por_familia
    assert dados["total"]["novo"]["estruturas"]["acertos_ate_005"] == 0
    assert dados["total"]["novo"]["estruturas"]["acertos_ate_010"] == 2


def test_cli_markdown_poe_cada_contagem_na_sua_coluna(
    relatorio: tuple[dict[str, Any], str],
) -> None:
    _, md = relatorio
    total = md.split("### Total", 1)[1].split("###", 1)[0]
    # acertos | total | recall | ≤ 0.05 | ≤ 0.10 | erros afirmados
    assert "| poste | novo | 2 | 2 | 100.0% | 2 | 2 | 0 |" in total
    assert "| estruturas | novo | 2 | 2 | 100.0% | 0 | 2 | 0 |" in total
    assert "| identificador | novo | 2 | 2 | 100.0% | 0 | 0 | 0 |" in total
    assert "| estruturas | base | 1 | 2 | 50.0% | 0 | 1 | 0 |" in total
