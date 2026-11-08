# mypy: disable-error-code="no-untyped-call"
"""Resíduos raster por folha (H2) sobre uma rodada sintética."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import scripts.residuos_raster_folhas as residuos
from scripts.curation_round import RodadaError
from scripts.ficha_poste import validar_ficha

from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    TetoGramaticasExcedido,
)

Dados = dict[str, Any]
LARGURA, ALTURA = 500.0, 400.0
NOME_PDF = "folha-secreta.pdf"


def _bbox(centro: tuple[float, float], meia: float = 10.0) -> list[float]:
    x, y = centro
    return [(x - meia) / LARGURA, (y - meia) / ALTURA, (x + meia) / LARGURA, (y + meia) / ALTURA]


def _imagem(pagina: pymupdf.Page, caixa: tuple[float, float, float, float], cor: int) -> None:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
    pixmap.set_rect(pixmap.irect, (cor, 40, 90))
    pagina.insert_image(pymupdf.Rect(caixa), pixmap=pixmap)


def _pdf_com_imagens(caminho: Path) -> str:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=LARGURA, height=ALTURA)
        _imagem(pagina, (100, 100, 130, 130), 10)  # compacta, sobre a referência ATERRAMENTO
        _imagem(pagina, (300, 300, 330, 330), 200)  # compacta, longe de qualquer referência
        _imagem(pagina, (200, 50, 400, 200), 120)  # grande, sob a referência CAMARA
        documento.save(caminho)
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _pdf_vazio(caminho: Path) -> str:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=LARGURA, height=ALTURA)
        pagina.draw_line((10, 10), (60, 10), color=(0, 0, 0))
        documento.save(caminho)
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _ficha(sha: str, simbolos: Sequence[Dados]) -> Dados:
    poste: Dados = {
        "id": "P1",
        "pagina": 1,
        "bbox": [0.1, 0.1, 0.1, 0.1],
        "identificador": None,
        "estruturas": [],
        "poste": None,
        "coordenada": None,
        "simbolos": list(simbolos),
        "pendentes": [],
    }
    ficha: Dados = {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": sha,
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [poste],
        "vaos": [],
    }
    assert validar_ficha(ficha) == []
    return ficha


def _rodada(raiz: Path, nome: str = "rodada") -> Path:
    corpus = raiz / "corpus"
    corpus.mkdir(parents=True)
    sha_a = _pdf_com_imagens(corpus / NOME_PDF)
    sha_b = _pdf_vazio(corpus / "outra.pdf")
    simbolos = [
        {"id": "S1", "classe": "ATERRAMENTO", "bbox": _bbox((115, 115))},
        {"id": "S2", "classe": "CAMARA", "bbox": _bbox((300, 125))},
    ]
    rodada = raiz / nome
    folhas = [("a", NOME_PDF, sha_a, simbolos), ("b", "outra.pdf", sha_b, [])]
    entradas = []
    for pdf_id, arquivo, sha, itens in folhas:
        entradas.append({"pdf_id": pdf_id, "caminho_relativo": arquivo, "sha256": sha})
        pasta = rodada / "pdfs" / pdf_id / "ficha"
        pasta.mkdir(parents=True)
        (pasta / "referencia.json").write_text(json.dumps(_ficha(sha, itens)), encoding="utf-8")
    manifesto = {
        "schema_version": "curadoria-rodada-v1",
        "raiz_corpus": "../corpus",
        "pdfs": entradas,
    }
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return rodada


def _folha(relatorio: Dados, pdf_id: str) -> Dados:
    return next(item for item in relatorio["folhas"] if item["pdf_id"] == pdf_id)


@pytest.fixture
def rodada(tmp_path: Path) -> Path:
    return _rodada(tmp_path)


def test_conta_residuos_por_folha(rodada: Path, tmp_path: Path) -> None:
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    assert relatorio["esquema"] == "residuos-raster-v1"
    assert _folha(relatorio, "a")["total"] == 2
    assert _folha(relatorio, "b")["total"] == 0
    assert relatorio["resumo"]["folhas_medidas"] == 2
    assert relatorio["resumo"]["folhas_fora_dominio"] == 0
    assert relatorio["resumo"]["residuos"] == 2
    gravado = json.loads((tmp_path / "saida" / "residuos-raster.json").read_text("utf-8"))
    assert gravado == relatorio


def test_cruza_com_referencia(rodada: Path, tmp_path: Path) -> None:
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    pagina = _folha(relatorio, "a")["paginas"][0]
    assert pagina["estado"] == "medida"
    sob = [item["referencias_sob"] for item in pagina["residuos"]]
    assert sob == [["ATERRAMENTO"], []]
    assert relatorio["resumo"]["sobre_referencia"] == 1
    por_hash = relatorio["resumo"]["por_hash"]
    assert sorted(por_hash.values()) == [1, 1]
    assert all(len(chave) == residuos.TAMANHO_HASH_CURTO for chave in por_hash)


def test_referencia_sob_imagem_grande_e_listada(rodada: Path, tmp_path: Path) -> None:
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    listadas = _folha(relatorio, "a")["paginas"][0]["referencias_sob_imagem"]
    assert {"id": "S2", "classe": "CAMARA"} in listadas
    assert {"id": "S1", "classe": "ATERRAMENTO"} in listadas
    assert relatorio["resumo"]["referencias_sob_imagem"] == 2


def test_pagina_fora_dominio_nao_vira_zero(
    rodada: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def teto(*_: Any, **__: Any) -> Any:
        raise TetoGramaticasExcedido("teto")

    monkeypatch.setattr(residuos, "casar_variantes", teto)
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folha = _folha(relatorio, "a")
    assert folha["total"] is None
    pagina = folha["paginas"][0]
    assert pagina["estado"] == "fora_dominio"
    assert pagina["motivo"]
    assert pagina["residuos"] == []
    assert relatorio["resumo"]["folhas_fora_dominio"] == 2
    assert relatorio["resumo"]["folhas_medidas"] == 0
    assert relatorio["resumo"]["residuos"] == 0


@pytest.mark.parametrize(
    "diagnostico",
    ["modelo.imagens_falhou", "modelo.imagens_anotacao_falhou", "modelo.caminhos_falhou"],
)
def test_imagens_falhou_nao_vira_zero(
    rodada: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, diagnostico: str
) -> None:
    original = residuos.pagina_para_gramaticas

    def com_falha(*args: Any, **kwargs: Any) -> Any:
        pagina = original(*args, **kwargs)
        modelo = dataclasses.replace(
            pagina.modelo, diagnosticos=(*pagina.modelo.diagnosticos, diagnostico)
        )
        return dataclasses.replace(pagina, modelo=modelo)

    monkeypatch.setattr(residuos, "pagina_para_gramaticas", com_falha)
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folha = _folha(relatorio, "b")
    assert folha["total"] is None
    pagina = folha["paginas"][0]
    assert pagina["estado"] == "fora_dominio"
    assert diagnostico in pagina["motivo"]


def test_recortes_gravados(rodada: Path, tmp_path: Path) -> None:
    saida = tmp_path / "saida"
    relatorio = residuos.medir_residuos(rodada, saida, recortes=True, dpi=100)
    nomes = [item["recorte"] for item in _folha(relatorio, "a")["paginas"][0]["residuos"]]
    assert all(nomes)
    for nome in nomes:
        assert (saida / nome).is_file()
        assert Path(NOME_PDF).stem not in nome
    sem = residuos.medir_residuos(rodada, tmp_path / "saida2")
    assert all(item["recorte"] is None for item in _folha(sem, "a")["paginas"][0]["residuos"])


def test_saida_sem_caminho_nem_nome_de_pdf(rodada: Path, tmp_path: Path) -> None:
    residuos.medir_residuos(rodada, tmp_path / "saida", recortes=True)
    texto = (tmp_path / "saida" / "residuos-raster.json").read_text("utf-8")
    assert NOME_PDF not in texto
    assert Path(NOME_PDF).stem not in texto
    assert str(tmp_path) not in texto
    assert tmp_path.as_posix() not in texto
    assert ".pdf" not in texto
    assert json.loads(texto)["rodada"] == "rodada"


def test_recusa_avaliacao_cega(tmp_path: Path) -> None:
    rodada = _rodada(tmp_path / "avaliacao-cega")
    with pytest.raises(RodadaError, match="avaliacao-cega"):
        residuos.medir_residuos(rodada, tmp_path / "saida")
    with pytest.raises(SystemExit) as erro:
        residuos.main(["--rodada", str(rodada), "--saida", str(tmp_path / "saida")])
    assert erro.value.code == 1
    assert not (tmp_path / "saida").exists()


def test_caminho_de_pdf_cego_vira_falha_da_folha(rodada: Path, tmp_path: Path) -> None:
    manifesto = json.loads((rodada / "rodada.json").read_text("utf-8"))
    manifesto["pdfs"][0]["caminho_relativo"] = "avaliacao-cega/x.pdf"
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folha = _folha(relatorio, "a")
    assert folha["total"] is None
    assert "avaliacao-cega" in folha["erro"]
    assert ".pdf" not in folha["erro"]


def test_sha_divergente_vira_falha_da_folha(rodada: Path, tmp_path: Path) -> None:
    ficha_caminho = rodada / "pdfs" / "b" / "ficha" / "referencia.json"
    ficha = json.loads(ficha_caminho.read_text("utf-8"))
    ficha["pdf_sha256"] = "0" * 64
    ficha_caminho.write_text(json.dumps(ficha), encoding="utf-8")
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    assert _folha(relatorio, "b")["total"] is None
    assert "sha256" in _folha(relatorio, "b")["erro"]
    assert _folha(relatorio, "a")["total"] == 2


def test_processos_da_o_mesmo_resultado(rodada: Path, tmp_path: Path) -> None:
    um = residuos.medir_residuos(rodada, tmp_path / "um", processos=1)
    dois = residuos.medir_residuos(rodada, tmp_path / "dois", processos=2)
    assert um == dois
    assert [folha["pdf_id"] for folha in dois["folhas"]] == ["a", "b"]


def test_main_grava_a_saida(rodada: Path, tmp_path: Path) -> None:
    argumentos = ["--rodada", str(rodada), "--saida", str(tmp_path / "s"), "--recortes"]
    assert residuos.main(argumentos) == 0
    assert (tmp_path / "s" / "residuos-raster.json").is_file()
