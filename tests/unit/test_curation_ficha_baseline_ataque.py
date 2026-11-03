"""Ataques ao ``baseline`` das fichas: multi-PDF, falha parcial, versões e vazamento de caminhos."""

from __future__ import annotations

import json
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import scripts.benchmark_ficha_poste as benchmark_ficha_poste
import scripts.curation_ficha as curation_ficha
from scripts.curation_ficha import agregar_avaliacoes, diretorio_ficha, main
from scripts.curation_round import carregar_rodada, escrever_json_atomico, iniciar_rodada
from tests.pdf_fixtures import create_network_benchmark_pdf
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica
from tests.unit.test_curation_ficha_baseline import (
    _argv,
    _bloco,
    _congelar_referencia,
    _nao_deve_rodar,
    _relatorio,
    _resumo,
    _resumos,
)

AGORA = "2026-10-15T12:00:00+00:00"


@pytest.fixture
def rodada_dupla(tmp_path: Path) -> tuple[Path, list[str]]:
    (tmp_path / "corpus").mkdir()
    pdfs = [
        create_network_benchmark_pdf(tmp_path / "corpus" / f"{nome}.pdf")
        for nome in ("alfa-secreto", "beta-secreto")
    ]
    rodada_dir = tmp_path / "rodada"
    iniciar_rodada(
        rodada_dir,
        tmp_path / "corpus",
        concorrencia=3,
        raiz_repositorio=tmp_path / "sem-git",
        agora=AGORA,
    )
    ids = [str(e["pdf_id"]) for e in carregar_rodada(rodada_dir)["pdfs"]]
    assert len(ids) == 2
    for pdf_id, pdf in zip(ids, sorted(pdfs), strict=True):
        _congelar_referencia(
            rodada_dir, pdf_id, _referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())
        )
    return rodada_dir, ids


# --- agregação ------------------------------------------------------------------------------


def test_agregar_distancias_do_total_ordenadas_entre_pdfs_e_por_pdf_ordenadas() -> None:
    agregado = agregar_avaliacoes(
        {"01-x": _relatorio(2, 0, 0, [0.03, 0.01]), "02-y": _relatorio(1, 0, 0, [0.02])}
    )
    assert agregado["total"]["distancias_casamento"] == [0.01, 0.02, 0.03]
    assert agregado["por_pdf"]["01-x"]["distancias_casamento"] == [0.01, 0.03]


def test_agregar_denominador_zero_de_campo_e_vao_vira_none() -> None:
    rel = _relatorio(0, 0, 0, [])
    rel["campos"] = {"poste": _bloco(0, 0)}
    rel["vaos"]["comprimento"] = _bloco(0, 0)
    total = agregar_avaliacoes({"01-x": rel})["total"]
    assert total["campos"]["poste"] == {"acertos": 0, "total": 0, "taxa": None}
    assert total["vaos"]["comprimento"]["taxa"] is None
    assert total["vaos"]["precisao"] is None and total["vaos"]["recall"] is None


def test_agregar_campo_presente_so_em_um_relatorio_soma_so_dele() -> None:
    a = _relatorio(1, 0, 0, [])
    b = _relatorio(1, 0, 0, [])
    b["campos"]["coordenada"] = _bloco(1, 2)
    total = agregar_avaliacoes({"01-x": a, "02-y": b})["total"]
    assert total["campos"]["coordenada"] == {"acertos": 1, "total": 2, "taxa": 0.5}


def test_agregar_so_falha_e_sem_referencia_mantem_ordem_e_total_indefinido() -> None:
    falha = {"situacao": "falha", "erro": "x"}
    agregado = agregar_avaliacoes({"01-x": falha, "02-y": None})
    assert list(agregado["por_pdf"]) == ["01-x", "02-y"]
    assert agregado["total"]["postes"]["precisao"] is None


# --- CLI ------------------------------------------------------------------------------------


def test_cli_baseline_falha_em_um_pdf_mede_os_demais_e_sai_com_1(
    rodada_dupla: tuple[Path, list[str]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, ids = rodada_dupla
    real = benchmark_ficha_poste.executar
    chamados: list[Path] = []

    def parcial(pdf: Path, *args: Any, **kwargs: Any) -> Any:
        chamados.append(pdf)
        if pdf.stem == "alfa-secreto":
            raise RuntimeError(f"nao abriu {pdf}")
        return real(pdf, *args, **kwargs)

    monkeypatch.setattr(curation_ficha, "executar_benchmark", parcial)
    assert main(_argv(rodada_dir, "--native-only")) == 1
    assert len(chamados) == 2
    assert ids[0] in capsys.readouterr().err
    resumo = _resumo(rodada_dir, "baseline-v001")
    assert resumo["por_pdf"][ids[0]]["situacao"] == "falha"
    assert str(rodada_dir.parent) not in json.dumps(resumo)
    assert "alfa-secreto" not in json.dumps(resumo)
    assert resumo["por_pdf"][ids[1]]["postes"]["tp"] == 2
    assert resumo["total"]["postes"]["tp"] == 2
    assert (rodada_dir / "fichas" / "baseline-v001-resumo.md").is_file()


def test_cli_baseline_pdf_inexistente_recusa_sem_gravar(
    rodada_dupla: tuple[Path, list[str]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, _ = rodada_dupla
    monkeypatch.setattr(curation_ficha, "executar_benchmark", _nao_deve_rodar)
    assert main(_argv(rodada_dir, "--native-only", "--pdf", "99-nao-existe")) == 1
    assert "99-nao-existe" in capsys.readouterr().err
    assert _resumos(rodada_dir) == []


def test_cli_baseline_pdf_seleciona_apenas_o_pedido(
    rodada_dupla: tuple[Path, list[str]],
) -> None:
    rodada_dir, ids = rodada_dupla
    assert main(_argv(rodada_dir, "--native-only", "--pdf", ids[1])) == 0
    resumo = _resumo(rodada_dir, "baseline-v001")
    assert list(resumo["por_pdf"]) == [ids[1]]
    assert resumo["opcoes"]["pdfs"] == [ids[1]]
    assert not (diretorio_ficha(rodada_dir, ids[0]) / "baseline-v001").exists()


def test_cli_baseline_parcial_mede_o_com_referencia_e_lista_o_sem(
    rodada_dupla: tuple[Path, list[str]],
) -> None:
    rodada_dir, ids = rodada_dupla
    (diretorio_ficha(rodada_dir, ids[0]) / "referencia.json").unlink()
    assert main(_argv(rodada_dir, "--native-only", "--parcial")) == 0
    resumo = _resumo(rodada_dir, "baseline-v001")
    assert resumo["por_pdf"][ids[0]] == {"situacao": "sem_referencia"}
    assert resumo["por_pdf"][ids[1]]["postes"]["tp"] == 2
    markdown = (rodada_dir / "fichas" / "baseline-v001-resumo.md").read_text("utf-8")
    assert "sem_referencia" in markdown


def test_cli_baseline_item_consolidada_ausente_no_congelamento_recusa(
    rodada_dupla: tuple[Path, list[str]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, ids = rodada_dupla
    pasta = diretorio_ficha(rodada_dir, ids[0])
    escrever_json_atomico(
        pasta / "congelamento.json",
        {"schema_version": "curadoria-ficha-congelamento-v1", "itens": []},
    )
    monkeypatch.setattr(curation_ficha, "executar_benchmark", _nao_deve_rodar)
    assert main(_argv(rodada_dir, "--native-only")) == 1
    assert "congelamento" in capsys.readouterr().err
    assert _resumos(rodada_dir) == []


def test_cli_baseline_referencia_adulterada_em_um_de_dois_nao_roda_nenhum(
    rodada_dupla: tuple[Path, list[str]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, ids = rodada_dupla
    arquivo = diretorio_ficha(rodada_dir, ids[1]) / "referencia.json"
    dados = json.loads(arquivo.read_text("utf-8"))
    dados["vaos"][0]["comprimento_m"] = 99.0
    escrever_json_atomico(arquivo, dados)
    monkeypatch.setattr(curation_ficha, "executar_benchmark", _nao_deve_rodar)
    assert main(_argv(rodada_dir, "--native-only")) == 1
    assert "adulterada" in capsys.readouterr().err
    assert _resumos(rodada_dir) == []


def test_cli_baseline_diretorio_de_versao_existente_sem_resumo_nao_e_reutilizado(
    rodada_dupla: tuple[Path, list[str]],
) -> None:
    rodada_dir, ids = rodada_dupla
    orfao = diretorio_ficha(rodada_dir, ids[0]) / "baseline-v001"
    orfao.mkdir()
    (orfao / "marca.txt").write_text("nao apagar", "utf-8")
    assert main(_argv(rodada_dir, "--native-only")) == 0
    assert _resumos(rodada_dir) == ["baseline-v002-resumo.json", "baseline-v002-resumo.md"]
    assert (orfao / "marca.txt").read_text("utf-8") == "nao apagar"
    assert sorted(p.name for p in orfao.iterdir()) == ["marca.txt"]


def test_cli_baseline_ocr_ok_e_conferido_uma_so_vez_com_dois_pdfs(
    rodada_dupla: tuple[Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, _ = rodada_dupla
    chamadas: list[Path] = []
    argumentos: list[bool] = []

    def pronto(diretorio: Path) -> SimpleNamespace:
        chamadas.append(diretorio)
        return SimpleNamespace(portugues_pronto=True, diagnostico="ok")

    def falso(pdf: Path, referencia: Path, saida: Path, **kwargs: Any) -> dict[str, Any]:
        argumentos.append(kwargs["native_only"])
        return _relatorio(1, 0, 0, [0.1])

    monkeypatch.setattr(curation_ficha, "inspect_tesseract_runtime", pronto)
    monkeypatch.setattr(curation_ficha, "executar_benchmark", falso)
    assert main(_argv(rodada_dir)) == 0
    assert len(chamadas) == 1
    assert argumentos == [False, False]


def test_cli_baseline_native_only_nao_consulta_o_ocr(
    rodada_dupla: tuple[Path, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, _ = rodada_dupla
    monkeypatch.setattr(curation_ficha, "inspect_tesseract_runtime", _nao_deve_rodar)
    assert main(_argv(rodada_dir, "--native-only")) == 0


def test_cli_baseline_resumo_registra_versoes_reais_e_nenhum_caminho_nem_nome_de_pdf(
    rodada_dupla: tuple[Path, list[str]],
) -> None:
    rodada_dir, ids = rodada_dupla
    assert main(_argv(rodada_dir, "--native-only")) == 0
    resumo = _resumo(rodada_dir, "baseline-v001")
    assert resumo["versoes"] == {"pillow": version("pillow"), "pymupdf": version("pymupdf")}
    for sufixo in ("json", "md"):
        texto = (rodada_dir / "fichas" / f"baseline-v001-resumo.{sufixo}").read_text("utf-8")
        for proibido in (
            str(rodada_dir.parent),
            rodada_dir.parent.as_posix(),
            "alfa-secreto",
            "beta-secreto",
            ".pdf",
        ):
            assert proibido not in texto
        assert all(pdf_id in texto for pdf_id in ids)
    assert resumo["gerador"]["native_only"] is True
