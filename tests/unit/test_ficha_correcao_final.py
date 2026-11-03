"""Correções da revisão final das fichas: empate de C, recorte em página girada e saneamento."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import scripts.curation_ficha as curation_ficha
from scripts.curation_ficha import main
from tests.unit.test_claude_curation_assets import CONTRATO, SKILL
from tests.unit.test_claude_curation_assets_ficha import plano, rodada_de_fichas
from tests.unit.test_curation_ficha_baseline import _argv, _resumo
from tests.unit.test_curation_ficha_baseline_sanear import _montar
from tests.unit.test_ficha_leitura_dupla import (
    _consolidar,
    _contagem,
    _leitura_c,
    _postes,
    _simbolo,
    _vao,
    ficha,
)

Registro = dict[str, Any]


# --- M1: C que confirma A e B ao mesmo tempo não desempata -----------------------------------


def _vao_p2_p3(referencia: Registro) -> Registro:
    return next(v for v in referencia["vaos"] if (v["de"], v["para"]) == ("P2", "P3"))


def _c_do_vao_p2_p3(a: Registro, comprimento: float) -> Registro:
    return _leitura_c(a["postes"][1], a["postes"][2], vaos=[_vao("P2", "P3", comprimento, "BT 70")])


@pytest.mark.parametrize("ordem", ["ab", "ba"])
def test_comprimento_confirmado_por_c_nos_dois_lados_fica_pendente(ordem: str) -> None:
    a, b = ficha(), ficha()
    b["vaos"][1]["comprimento_m"] = 35.15  # A=35,0 e B=35,15 divergem (tolerância 0,1 m)
    x, y = (a, b) if ordem == "ab" else (b, a)
    referencia = _consolidar(x, y, _c_do_vao_p2_p3(a, 35.08))  # C a 0,08 e 0,07 dos dois
    vao = _vao_p2_p3(referencia)
    assert (vao["comprimento_m"], vao["pendentes"]) == (None, ["comprimento_m"])
    assert (_contagem(referencia)["resolvidas_por_c"], _contagem(referencia)["pendentes"]) == (
        0,
        1,
    )


def test_comprimento_confirmado_por_c_num_so_lado_e_resolvido() -> None:
    a, b = ficha(), ficha()
    b["vaos"][1]["comprimento_m"] = 35.15
    referencia = _consolidar(a, b, _c_do_vao_p2_p3(a, 35.0))  # C a 0,15 de B: só confirma A
    vao = _vao_p2_p3(referencia)
    assert (vao["comprimento_m"], vao["pendentes"]) == (35.0, [])
    assert (_contagem(referencia)["resolvidas_por_c"], _contagem(referencia)["pendentes"]) == (
        1,
        0,
    )


@pytest.mark.parametrize("ordem", ["ab", "ba"])
def test_coordenada_confirmada_por_c_nos_dois_lados_fica_pendente(ordem: str) -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["coordenada"]["leste"] = 700000.015  # 0,015 m de A (tolerância 0,01 m)
    poste_c = copy.deepcopy(a["postes"][0])
    poste_c["coordenada"]["leste"] = 700000.0075  # a 0,0075 m de A e de B
    x, y = (a, b) if ordem == "ab" else (b, a)
    referencia = _consolidar(x, y, _leitura_c(poste_c))
    p1 = _postes(referencia)["P1"]
    assert (p1["coordenada"], p1["pendentes"]) == (None, ["coordenada"])
    assert (_contagem(referencia)["resolvidas_por_c"], _contagem(referencia)["pendentes"]) == (
        0,
        1,
    )


@pytest.mark.parametrize("ordem", ["ab", "ba"])
def test_simbolos_que_c_casa_por_inteiro_com_a_e_com_b_ficam_pendentes(ordem: str) -> None:
    a, b = ficha(), ficha()
    # IoU(A, B) = 0,43 < 0,5: A e B divergem; IoU(C, A) = IoU(C, B) = 0,67: C casa com os dois
    b["postes"][0]["simbolos"] = [_simbolo("S1", [0.138, 0.30, 0.158, 0.32])]
    poste_c = copy.deepcopy(a["postes"][0])
    poste_c["simbolos"] = [_simbolo("S1", [0.134, 0.30, 0.154, 0.32])]
    x, y = (a, b) if ordem == "ab" else (b, a)
    referencia = _consolidar(x, y, _leitura_c(poste_c))
    p1 = _postes(referencia)["P1"]
    assert (p1["simbolos"], p1["pendentes"]) == ([], ["simbolos"])
    assert (_contagem(referencia)["resolvidas_por_c"], _contagem(referencia)["pendentes"]) == (
        0,
        1,
    )


FRASE_DO_EMPATE = (
    "se C, dentro da tolerância, confirma A e B ao mesmo tempo, o valor fica pendente e não "
    "conta como resolvido por C"
)


@pytest.mark.parametrize("caminho", [SKILL, CONTRATO], ids=["skill", "contrato"])
def test_skill_e_contrato_dizem_que_c_nos_dois_lados_deixa_pendente(caminho: Path) -> None:
    assert FRASE_DO_EMPATE in plano(rodada_de_fichas(caminho.read_text(encoding="utf-8")))


# --- M2: recorte da amostra em página com /Rotate --------------------------------------------


def _pixels(png: bytes) -> tuple[int, int, list[tuple[int, int, int]]]:
    pixmap = pymupdf.Pixmap(png)  # type: ignore[no-untyped-call]
    amostras, n = pixmap.samples, pixmap.n
    cores = [(amostras[i], amostras[i + 1], amostras[i + 2]) for i in range(0, len(amostras), n)]
    return pixmap.width, pixmap.height, cores


def _preto(cor: tuple[int, int, int]) -> bool:
    return max(cor) < 60


def _vermelho(cor: tuple[int, int, int]) -> bool:
    return cor[0] > 200 and cor[1] < 80 and cor[2] < 80


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
def test_recorte_da_bbox_exibida_contem_a_marca_em_pagina_girada(rotacao: int) -> None:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=600, height=400)
        marca = pymupdf.Rect(90, 60, 130, 90)  # type: ignore[no-untyped-call]
        isca = pymupdf.Rect(470, 290, 510, 330)  # type: ignore[no-untyped-call]
        pagina.draw_rect(marca, color=(0, 0, 0), fill=(0, 0, 0))
        pagina.draw_rect(isca, color=(1, 0, 0), fill=(1, 0, 0))
        pagina.set_rotation(rotacao)
        exibida = marca * pagina.rotation_matrix
        largura, altura = pagina.rect.width, pagina.rect.height
        # a fixture confere a posição exibida na página inteira renderizada
        inteira = pagina.get_pixmap(dpi=72)
        assert _preto(inteira.pixel(int(exibida.x0 + 20), int(exibida.y0 + 15))[:3])
        bbox = [
            exibida.x0 / largura,
            exibida.y0 / altura,
            exibida.x1 / largura,
            exibida.y1 / altura,
        ]
        png = curation_ficha._recorte_do_poste(pagina, bbox)
    w, h, cores = _pixels(png)
    escala = curation_ficha.DPI_RECORTE / 72
    margem_x, margem_y = 0.04 * largura, 0.04 * altura
    assert abs(w - (exibida.width + 2 * margem_x) * escala) <= 3
    assert abs(h - (exibida.height + 2 * margem_y) * escala) <= 3
    pretos = sum(1 for cor in cores if _preto(cor))
    assert pretos >= 0.9 * exibida.width * exibida.height * escala * escala
    assert _preto(cores[(h // 2) * w + w // 2])
    assert not any(_vermelho(cor) for cor in cores)


# --- M3: saneamento remove o runtime e qualquer caminho absoluto restante --------------------

ABSOLUTOS = {
    "posix_home": ("nao abriu /home/caio/rede.pdf", "nao abriu <caminho>"),
    "posix_tmp_com_dois_pontos": ("falha em /tmp/a/b.pdf: erro", "falha em <caminho>: erro"),
    "posix_usr": (
        "lib /usr/lib/libtesseract.so.5 ausente",
        "lib <caminho> ausente",
    ),
    "posix_entre_parenteses": ("arquivo (/opt/x/y) sumiu", "arquivo (<caminho>) sumiu"),
    "windows": ("D:\\outro\\disco\\por.traineddata nao abriu", "<caminho> nao abriu"),
    "windows_barras_normais": ("abriu D:/outro/x.pdf.", "abriu <caminho>."),
    "windows_repr": (
        "nao abriu 'E:\\\\dados\\\\x.pdf', tente",
        "nao abriu '<caminho>', tente",
    ),
    "windows_entre_aspas_com_espaco": (
        "[Errno 2] No such file: 'E:\\Program Files\\Tesseract OCR\\tessdata'",
        "[Errno 2] No such file: '<caminho>'",
    ),
    "posix_entre_aspas_com_espaco": (
        'arquivo "/var/tmp/com espaco/x" sumiu',
        'arquivo "<caminho>" sumiu',
    ),
    "unc": ("rede \\\\servidor\\share\\x.pdf; tente", "rede <caminho>; tente"),
    "unc_repr": ("rede '\\\\\\\\srv\\\\x.pdf' e \\\\\\\\srv\\\\y", "rede '<caminho>' e <caminho>"),
}

SEM_CAMINHO_ABSOLUTO = [
    "falha do analisador",
    "taxa 3/4 e campo a/b em 2026/11/03",
    "veja http://exemplo.com/a/b e https://x.y/z",
    "proporção 1 / 2",
    "relativo ../corpus/x, ./y e .\\corpus\\z",
    "relativo no repr '..\\\\corpus\\\\x' e 'corpus\\\\y'",
    "<caminho>\\\\fichas\\\\x e <caminho>/fichas/y continuam",
    "TypeError: unsupported operand type(s) for /: 'int' and 'str'",
    "OCR português obrigatório: tesseract ausente",
    "padrão C: sem barra",
]


@pytest.mark.parametrize("chave", sorted(ABSOLUTOS))
def test_sanear_troca_caminho_absoluto_restante_e_preserva_o_resto(
    tmp_path: Path, chave: str
) -> None:
    mensagem, esperado = ABSOLUTOS[chave]
    pdf = tmp_path / "corpus" / "alfa-secreto.pdf"
    assert curation_ficha._sanear(mensagem, pdf, "01-x") == esperado


@pytest.mark.parametrize("mensagem", SEM_CAMINHO_ABSOLUTO)
def test_sanear_nao_mexe_em_mensagem_sem_caminho_absoluto(tmp_path: Path, mensagem: str) -> None:
    pdf = tmp_path / "corpus" / "alfa-secreto.pdf"
    assert curation_ficha._sanear(mensagem, pdf, "01-x") == mensagem


def test_baseline_falha_nao_vaza_o_runtime_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rodada_dir, pdf_id, _ = _montar(tmp_path, "rede-secreta.pdf")
    runtime = tmp_path / "meu runtime" / "ocr"

    def quebra(*_: Any, runtime_directory: Path, **__: Any) -> None:
        raise RuntimeError(f"nao achou {runtime_directory.resolve() / 'tesseract.exe'}")

    monkeypatch.setattr(curation_ficha, "executar_benchmark", quebra)
    argv = _argv(rodada_dir, "--native-only", "--runtime-directory", str(runtime))
    assert main(argv) == 1
    erro = _resumo(rodada_dir, "baseline-v001")["por_pdf"][pdf_id]["erro"]
    assert erro == f"nao achou <caminho>{os.sep}tesseract.exe"
    for sufixo in ("json", "md"):
        texto = (rodada_dir / "fichas" / f"baseline-v001-resumo.{sufixo}").read_text("utf-8")
        assert "meu runtime" not in texto and str(tmp_path) not in texto
