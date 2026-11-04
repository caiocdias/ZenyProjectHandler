# mypy: disable-error-code="no-untyped-call"
"""Imagem de anotação acima do teto de pixels não é decodificada para obter a identidade."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho

_XREF = re.compile(r"(\d+) 0 R")


def _png(lado: int = 6) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, lado, lado), False)
    pixmap.set_rect(pixmap.irect, (40, 120, 200))
    return bytes(pixmap.tobytes("png"))


def _pdf_com_carimbo(caminho: Path, dimensoes: tuple[int, int] | None = None) -> int:
    """Carimbo cujo /AP desenha uma imagem; `dimensoes` reescreve /Width e /Height dela."""
    with pymupdf.open() as documento:
        documento.new_page(width=300, height=200)
        auxiliar = documento.new_page(width=50, height=50)
        xref_imagem = int(auxiliar.insert_image(auxiliar.rect, stream=_png()))
        carimbo = documento[0].add_stamp_annot(pymupdf.Rect(20, 20, 80, 60), stamp=0)
        aparencia = _XREF.search(str(documento.xref_get_key(carimbo.xref, "AP")[1]))
        assert aparencia is not None
        xref_ap = int(aparencia.group(1))
        documento.xref_set_key(xref_ap, "Resources/XObject/ImAp", f"{xref_imagem} 0 R")
        fluxo = bytes(documento.xref_stream(xref_ap) or b"")
        documento.update_stream(xref_ap, fluxo + b"\nq 12 0 0 12 2 2 cm /ImAp Do Q\n")
        documento.delete_page(1)
        if dimensoes is not None:
            documento.xref_set_key(xref_imagem, "Width", str(dimensoes[0]))
            documento.xref_set_key(xref_imagem, "Height", str(dimensoes[1]))
        documento.save(caminho)
    return xref_imagem


def _fluxo_bruto(pdf: Path, xref: int) -> bytes:
    with pymupdf.open(pdf) as documento:
        return bytes(documento.xref_stream_raw(xref) or b"")


def test_dimensoes_acima_do_teto_usam_sha_do_fluxo_bruto_sem_decodificar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "hostil.pdf"
    xref = _pdf_com_carimbo(pdf, dimensoes=(200_000, 200_000))
    esperado = hashlib.sha256(_fluxo_bruto(pdf, xref)).hexdigest()

    def _proibido(*_argumentos: object) -> object:
        raise AssertionError("imagem acima do teto não pode ser decodificada")

    monkeypatch.setattr(pymupdf, "Pixmap", _proibido)
    inicio = time.perf_counter()
    modelo = extrair_modelo_desenho(pdf)
    duracao = time.perf_counter() - inicio

    pagina = modelo.paginas[0]
    assert "modelo.imagens_anotacao_falhou" not in pagina.diagnosticos
    anotacoes = [i for i in pagina.imagens if i.de_anotacao]
    assert len(anotacoes) == 1
    assert (anotacoes[0].largura_px, anotacoes[0].altura_px) == (200_000, 200_000)
    assert anotacoes[0].sha256 == esperado
    assert duracao < 5.0


def test_dimensoes_abaixo_do_teto_mantem_o_digest_de_pixels(tmp_path: Path) -> None:
    pdf = tmp_path / "normal.pdf"
    xref = _pdf_com_carimbo(pdf)
    with pymupdf.open(pdf) as documento:
        digest = bytes(pymupdf.Pixmap(documento, xref).digest or b"")

    modelo = extrair_modelo_desenho(pdf)

    anotacoes = [i for i in modelo.paginas[0].imagens if i.de_anotacao]
    assert len(anotacoes) == 1
    assert (anotacoes[0].largura_px, anotacoes[0].altura_px) == (6, 6)
    assert anotacoes[0].sha256 == hashlib.sha256(digest).hexdigest()
    assert anotacoes[0].sha256 != hashlib.sha256(_fluxo_bruto(pdf, xref)).hexdigest()


def test_referencia_em_ciclo_na_largura_usa_o_fluxo_bruto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "base.pdf"
    xref = _pdf_com_carimbo(base)
    sem_compressao = tmp_path / "indireta.pdf"
    with pymupdf.open(base) as documento:
        numero = documento.get_new_xref()
        documento.update_object(numero, "200000")
        documento.xref_set_key(xref, "Width", f"{numero} 0 R")
        documento.save(sem_compressao, garbage=0, deflate=False, expand=0)
    # `update_object` não aceita um objeto que é só referência: o ciclo (N 0 R dentro de N)
    # entra no arquivo com o mesmo tamanho, sem mexer nos offsets da tabela xref.
    original = f"{numero} 0 obj\n200000\nendobj".encode()
    ciclo = f"{numero} 0 obj\n{f'{numero} 0 R':<6}\nendobj".encode()
    assert len(ciclo) == len(original)
    bruto = sem_compressao.read_bytes()
    assert bruto.count(original) == 1
    pdf = tmp_path / "ciclo.pdf"
    pdf.write_bytes(bruto.replace(original, ciclo))
    esperado = hashlib.sha256(_fluxo_bruto(pdf, xref)).hexdigest()

    def _proibido(*_argumentos: object) -> object:
        raise AssertionError("largura desconhecida não pode ser decodificada")

    monkeypatch.setattr(pymupdf, "Pixmap", _proibido)
    pagina = extrair_modelo_desenho(pdf).paginas[0]

    assert "modelo.imagens_anotacao_falhou" not in pagina.diagnosticos
    anotacoes = [i for i in pagina.imagens if i.de_anotacao]
    assert len(anotacoes) == 1 and anotacoes[0].sha256 == esperado
    assert anotacoes[0].largura_px == 0
