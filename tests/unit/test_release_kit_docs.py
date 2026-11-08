from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_exemplo_de_ambiente_do_kit_traz_leitura_vetorial_desligada() -> None:
    linhas = (ROOT / "server" / "env.release.example").read_text(encoding="utf-8").splitlines()
    assert "ZENY_SERVER_SYMBOL_COMPOSITION=false" in linhas


def test_guia_do_servidor_explica_a_leitura_vetorial_opcional() -> None:
    guia = (ROOT / "server" / "LEIA-ME-SERVIDOR.md").read_text(encoding="utf-8")
    normalizado = " ".join(guia.split())
    assert "ZENY_SERVER_SYMBOL_COMPOSITION" in normalizado
    assert "desligada por padrão" in normalizado
