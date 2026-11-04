# mypy: disable-error-code="no-untyped-call"
"""Relatório: falha nas amostras preserva a medição; origem dos pixels; entradas não PDF."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts import drawing_model_report
from scripts.drawing_model_report import main

_XREF = re.compile(r"(\d+) 0 R")


def _png(cor: tuple[int, int, int], lado: int = 4) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, lado, lado), False)
    pixmap.set_rect(pixmap.irect, cor)
    return bytes(pixmap.tobytes("png"))


def _pdf(caminho: Path) -> Path:
    """Quatro ladrilhos, uma imagem `outra` e um carimbo com imagem no /AP."""
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        for linha in range(2):
            for coluna in range(2):
                x, y = 10 + 50 * coluna, 10 + 50 * linha
                pagina.insert_image(pymupdf.Rect(x, y, x + 50, y + 50), stream=_png((250, 0, 0)))
        pagina.insert_image(pymupdf.Rect(200, 150, 210, 160), stream=_png((0, 0, 250), lado=8))
        auxiliar = documento.new_page(width=50, height=50)
        xref_imagem = auxiliar.insert_image(auxiliar.rect, stream=_png((0, 250, 0)))
        carimbo = documento[0].add_stamp_annot(pymupdf.Rect(220, 20, 280, 60), stamp=0)
        aparencia = _XREF.search(str(documento.xref_get_key(carimbo.xref, "AP")[1]))
        assert aparencia is not None
        xref_aparencia = int(aparencia.group(1))
        documento.xref_set_key(xref_aparencia, "Resources/XObject/ImAp", f"{xref_imagem} 0 R")
        conteudo = bytes(documento.xref_stream(xref_aparencia) or b"")
        documento.update_stream(xref_aparencia, conteudo + b"\nq 12 0 0 12 2 2 cm /ImAp Do Q\n")
        documento.delete_page(1)
        documento.save(caminho)
    return caminho


def _rodar(tmp_path: Path, pasta: Path, *, amostras: bool = True) -> dict[str, Any]:
    repo = tmp_path / "repo"
    (repo / "tmp").mkdir(parents=True, exist_ok=True)
    saida = repo / "tmp" / "r.json"
    argumentos = ["--raiz", str(pasta), "--saida", str(saida), "--raiz-repositorio", str(repo)]
    if amostras:
        argumentos += ["--amostras-imagem", str(repo / "tmp" / "img")]
    assert main(argumentos) == 0
    return dict(json.loads(saida.read_text(encoding="utf-8")))


def test_falha_so_nas_amostras_preserva_a_medicao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf(pasta / "a.pdf")

    def _falha(*_argumentos: object, **_nomeados: object) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(drawing_model_report, "gravar_amostras", _falha)

    relatorio = _rodar(tmp_path, pasta)

    assert relatorio["resumo"]["erros"] == 0
    medicao = relatorio["pdfs"][0]
    assert "erro" not in medicao
    assert medicao["erro_amostras"] == "OSError"
    assert medicao["imagens"] == {"ladrilho": 4, "anotacao": 1, "outra": 1}
    assert medicao["paginas"] and medicao["amostras"]
    assert all("fonte_pixels" not in a for a in medicao["amostras"])


def test_amostras_gravadas_sem_falha_nao_tem_erro_amostras(tmp_path: Path) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf(pasta / "a.pdf")

    medicao = _rodar(tmp_path, pasta)["pdfs"][0]

    assert "erro_amostras" not in medicao and "erro" not in medicao


def test_amostra_diz_se_os_pixels_sao_originais_ou_recorte(tmp_path: Path) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf(pasta / "a.pdf")

    amostras = _rodar(tmp_path, pasta)["pdfs"][0]["amostras"]

    fontes = {a["classe"]: a["fonte_pixels"] for a in amostras}
    assert fontes == {"outra": "original", "ladrilho": "original", "anotacao": "recorte"}


def test_imagem_de_pagina_nao_localizada_vira_recorte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf(pasta / "a.pdf")
    monkeypatch.setattr(drawing_model_report, "_pixels_da_pagina", lambda *_a: None)

    amostras = _rodar(tmp_path, pasta)["pdfs"][0]["amostras"]

    assert amostras and {a["fonte_pixels"] for a in amostras} == {"recorte"}


def test_sem_amostras_de_imagem_nao_ha_fonte_pixels(tmp_path: Path) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf(pasta / "a.pdf")

    amostras = _rodar(tmp_path, pasta, amostras=False)["pdfs"][0]["amostras"]

    assert amostras and all("fonte_pixels" not in a for a in amostras)


def test_diretorio_com_sufixo_pdf_e_ignorado(tmp_path: Path) -> None:
    pasta = tmp_path / "pdfs"
    (pasta / "pasta.pdf").mkdir(parents=True)
    (pasta / "pasta.pdf" / "dentro.pdf").write_bytes((_pdf(tmp_path / "x.pdf")).read_bytes())
    _pdf(pasta / "a.pdf")

    resumo = _rodar(tmp_path, pasta, amostras=False)["resumo"]

    assert resumo["pdfs"] == 2 and resumo["erros"] == 0
