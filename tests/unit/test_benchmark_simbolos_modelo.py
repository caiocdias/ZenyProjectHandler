# mypy: disable-error-code="no-untyped-call"
"""Métodos ``pacotes`` e ``modelo`` do benchmark de símbolos por ficha."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
import scripts.benchmark_simbolos_ficha as bench

from zeny_project_handler.adapters.analysis import model_symbols, pymupdf_drawing_model

_MOLDURA_CT: Final = (101.0, 115.0, 169.0, 149.0)
_TOLERANCIA: Final = 0.005


def _pdf_ct(caminho: Path) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        pagina.draw_rect(pymupdf.Rect(_MOLDURA_CT), color=(0, 0, 0), width=1)
        pagina.insert_text((_MOLDURA_CT[0] + 6, _MOLDURA_CT[1] + 25), "CT", fontsize=11)
        documento.save(caminho)
    return caminho


def _pdf_vazio(caminho: Path) -> Path:
    with pymupdf.open() as documento:
        documento.new_page(width=300, height=300)
        documento.save(caminho)
    return caminho


def _referencia(sha: str = "x") -> dict[str, Any]:
    return {"pdf_sha256": sha, "postes": [], "regioes": [], "simbolos": []}


def test_modelo_e_pacotes_preveem_o_mesmo_rotulo(tmp_path: Path) -> None:
    pdf = _pdf_ct(tmp_path / "ct.pdf")
    pacotes = bench.METODOS["pacotes"](pdf, "pdf-1")
    modelo = bench.METODOS["modelo"](pdf, "pdf-1")
    assert pacotes["falha"] is None
    assert modelo["falha"] is None
    for resultado, nome in ((pacotes, "pacotes"), (modelo, "modelo")):
        assert resultado["predicoes"], nome
        for predicao in resultado["predicoes"]:
            assert set(predicao) == {
                "pagina",
                "classe",
                "bbox",
                "metodo",
                "contexto",
                "variante",
                "situacoes_preditas",
            }
    ct_pacotes = [p for p in pacotes["predicoes"] if p["classe"] == "CAMARA"]
    ct_modelo = [p for p in modelo["predicoes"] if p["classe"] == "CAMARA"]
    assert len(ct_pacotes) == 1
    assert len(ct_modelo) == 1
    assert ct_pacotes[0]["pagina"] == ct_modelo[0]["pagina"] == 1
    assert ct_pacotes[0]["metodo"] != ct_modelo[0]["metodo"]
    for a, b in zip(ct_pacotes[0]["bbox"], ct_modelo[0]["bbox"], strict=True):
        assert abs(a - b) < _TOLERANCIA


def test_folha_sem_simbolo_nao_e_falha(tmp_path: Path) -> None:
    pdf = _pdf_vazio(tmp_path / "vazio.pdf")
    for nome in ("pacotes", "modelo"):
        resultado = bench.METODOS[nome](pdf, "pdf-1")
        assert resultado["predicoes"] == []
        assert resultado["falha"] is None


def test_fonte_falhou_conta_como_falha_nao_como_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_ct(tmp_path / "ct.pdf")

    def levantar(*_: Any, **__: Any) -> Any:
        raise RuntimeError("primitivas quebradas")

    monkeypatch.setattr(pymupdf_drawing_model, "reconstruir_polilinhas", levantar)
    registro = bench.medir_pdf(
        pdf, _referencia(), "pdf-1", ["modelo"], classes_avaliadas=["CAMARA"]
    )
    bloco = registro["metodos"]["modelo"]
    assert bloco["situacao"] == "falha"
    assert "fonte_falhou:modelo.primitivas_falhou" in bloco["erro"]
    assert "comparacao" not in bloco


def test_teto_conta_como_falha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = _pdf_ct(tmp_path / "ct.pdf")
    monkeypatch.setattr(bench, "LIMITE_MODELO", 1)
    registro = bench.medir_pdf(
        pdf, _referencia(), "pdf-1", ["modelo"], classes_avaliadas=["CAMARA"]
    )
    bloco = registro["metodos"]["modelo"]
    assert bloco["situacao"] == "falha"
    assert "teto_consultas" in bloco["erro"]


def test_assinatura_do_modelo_traz_versao_e_tabela() -> None:
    assinatura = bench.ASSINATURAS["modelo"]()
    assert assinatura["metodo_id"] == "declarative-drawing-model"
    assert assinatura["versao"] == model_symbols._VERSAO
    parametros = assinatura["parametros"]
    assert {"tabela_glifos_versao", "tabela_glifos_sha256", "limite_consultas"} <= set(parametros)
    assert parametros["limite_consultas"] == str(bench.LIMITE_MODELO)
    assert bench.ASSINATURAS["pacotes"]()["metodo_id"]


def test_metodo_desconhecido_segue_recusado(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as erro:
        bench.main(["--rodada", str(tmp_path), "--saida", str(tmp_path), "--metodo", "x"])
    assert erro.value.code == 2
