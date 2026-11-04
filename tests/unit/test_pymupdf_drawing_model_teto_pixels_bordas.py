# mypy: disable-error-code="no-untyped-call"
"""Bordas do teto de pixels da imagem de anotação: no teto, dimensões ausentes ou atípicas."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf
import pytest
from tests.unit.test_pymupdf_drawing_model_teto_pixels import _fluxo_bruto, _pdf_com_carimbo

from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho


def _espiar_pixmap(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    chamadas: list[object] = []

    def _espiao(*argumentos: object) -> object:
        chamadas.append(argumentos)
        raise MemoryError("decodificação não deveria acontecer")

    monkeypatch.setattr(pymupdf, "Pixmap", _espiao)
    return chamadas


def _anotacao(pdf: Path) -> object:
    imagens = [i for i in extrair_modelo_desenho(pdf).paginas[0].imagens if i.de_anotacao]
    assert len(imagens) == 1
    return imagens[0]


def test_exatamente_no_teto_ainda_decodifica_pelo_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "teto.pdf"
    _pdf_com_carimbo(pdf, dimensoes=(4000, 4000))
    chamadas = _espiar_pixmap(monkeypatch)

    extrair_modelo_desenho(pdf)

    assert len(chamadas) == 1  # 16_000_000 não passa do teto


def test_um_pixel_acima_do_teto_usa_o_fluxo_bruto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "acima.pdf"
    xref = _pdf_com_carimbo(pdf, dimensoes=(4000, 4001))
    esperado = hashlib.sha256(_fluxo_bruto(pdf, xref)).hexdigest()
    chamadas = _espiar_pixmap(monkeypatch)

    imagem = _anotacao(pdf)

    assert chamadas == []
    assert imagem.sha256 == esperado  # type: ignore[attr-defined]


def test_largura_ausente_degrada_sem_derrubar_a_pagina(tmp_path: Path) -> None:
    pdf = tmp_path / "sem_largura.pdf"
    xref = _pdf_com_carimbo(pdf)
    with pymupdf.open(pdf) as documento:
        documento.xref_set_key(xref, "Width", "null")
        documento.saveIncr()
    pagina = extrair_modelo_desenho(pdf).paginas[0]
    # a MuPDF recusa imagem sem largura: o diagnóstico é o degrau esperado e o resto da página fica
    assert pagina.diagnosticos == ("modelo.imagens_anotacao_falhou",)
    assert pagina.caminhos


@pytest.mark.parametrize("largura", ["200000.0", "200000.5"])
def test_largura_real_acima_do_teto_nao_decodifica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, largura: str
) -> None:
    """DEFEITO: /Width real vira 0 em _inteiro_do_objeto e contorna o teto."""
    pdf = tmp_path / "real.pdf"
    xref = _pdf_com_carimbo(pdf, dimensoes=(200_000, 200_000))
    with pymupdf.open(pdf) as documento:
        documento.xref_set_key(xref, "Width", largura)
        documento.saveIncr()
    chamadas = _espiar_pixmap(monkeypatch)

    extrair_modelo_desenho(pdf)

    assert chamadas == []


def test_largura_indireta_acima_do_teto_nao_decodifica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DEFEITO: /Width como referência indireta vira 0 e contorna o teto."""
    pdf = tmp_path / "indireta.pdf"
    xref = _pdf_com_carimbo(pdf, dimensoes=(200_000, 200_000))
    with pymupdf.open(pdf) as documento:
        numero = documento.get_new_xref()
        documento.update_object(numero, "200000")
        documento.xref_set_key(xref, "Width", f"{numero} 0 R")
        documento.saveIncr()
    chamadas = _espiar_pixmap(monkeypatch)

    extrair_modelo_desenho(pdf)

    assert chamadas == []


def test_dimensoes_negativas_degradam_sem_derrubar_a_pagina(tmp_path: Path) -> None:
    pdf = tmp_path / "negativa.pdf"
    _pdf_com_carimbo(pdf, dimensoes=(-5, -5))
    pagina = extrair_modelo_desenho(pdf).paginas[0]
    assert pagina.diagnosticos == ("modelo.imagens_anotacao_falhou",)
    assert pagina.caminhos
