# mypy: disable-error-code="no-untyped-call"
"""`fonte_pixels` precisa dizer a verdade sobre o PNG que ficou em disco."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.drawing_model_report import main
from tests.unit.test_drawing_model_report_robustez import _pdf


def _rodar(tmp_path: Path, pasta: Path) -> tuple[dict[str, Any], Path]:
    repo = tmp_path / "repo"
    (repo / "tmp").mkdir(parents=True, exist_ok=True)
    saida = repo / "tmp" / "r.json"
    imagens = repo / "tmp" / "img"
    argumentos = [
        "--raiz",
        str(pasta),
        "--saida",
        str(saida),
        "--raiz-repositorio",
        str(repo),
        "--amostras-imagem",
        str(imagens),
    ]
    assert main(argumentos) == 0
    return dict(json.loads(saida.read_text(encoding="utf-8"))), imagens


def test_png_antigo_em_disco_e_sobrescrito_e_a_origem_confere(tmp_path: Path) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf(pasta / "a.pdf")
    primeiro, imagens = _rodar(tmp_path, pasta)
    por_classe = {a["classe"]: a for a in primeiro["pdfs"][0]["amostras"]}
    alvo = imagens / f"{por_classe['outra']['sha256']}.png"
    original = alvo.read_bytes()
    alvo.write_bytes(b"lixo de uma execucao anterior")

    segundo, _ = _rodar(tmp_path, pasta)

    assert alvo.read_bytes() == original
    assert {a["classe"]: a["fonte_pixels"] for a in segundo["pdfs"][0]["amostras"]}[
        "outra"
    ] == "original"


def test_mesmo_sha_em_dois_pdfs_reaproveita_origem_e_grava_uma_vez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf(pasta / "a.pdf")
    _pdf(pasta / "b.pdf")
    gravacoes: list[str] = []
    original = Path.write_bytes

    def _contar(self: Path, dados: bytes) -> int:
        if self.suffix == ".png":
            gravacoes.append(self.name)
        return original(self, dados)

    monkeypatch.setattr(Path, "write_bytes", _contar)

    relatorio, imagens = _rodar(tmp_path, pasta)

    assert len(gravacoes) == len(set(gravacoes))
    for medicao in relatorio["pdfs"]:
        for amostra in medicao["amostras"]:
            assert amostra["fonte_pixels"] in {"original", "recorte"}
            assert (imagens / f"{amostra['sha256']}.png").is_file()
