"""CLI ``baseline`` das fichas do poste: agregação, travas, versões e privacidade."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import scripts.curation_ficha as curation_ficha
from scripts.curation_ficha import agregar_avaliacoes, diretorio_ficha, main
from scripts.curation_round import (
    carregar_rodada,
    escrever_json_atomico,
    hash_arquivo,
    iniciar_rodada,
)
from tests.pdf_fixtures import create_network_benchmark_pdf
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica

Registro = dict[str, Any]
AGORA = "2026-10-15T12:00:00+00:00"


def _bloco(acertos: int, total: int) -> Registro:
    return {"acertos": acertos, "total": total, "taxa": acertos / total if total else None}


def _contagem(tp: int, fp: int, fn: int) -> Registro:
    return {"tp": tp, "fp": fp, "fn": fn}


def _relatorio(tp: int, fp: int, fn: int, distancias: list[float]) -> Registro:
    return {
        "postes": _contagem(tp, fp, fn),
        "campos": {"poste": _bloco(tp, tp + fp), "estruturas": _bloco(0, tp)},
        "vaos": {
            **_contagem(tp, 0, 0),
            "comprimento": _bloco(tp, tp),
            "cabo": _bloco(1, tp),
        },
        "simbolos": _contagem(0, 0, fn),
        "pares": [{"distancia": d} for d in distancias],
    }


def test_agregar_soma_contagens_e_recalcula_taxas() -> None:
    a = _relatorio(2, 0, 0, [0.02, 0.01])
    b = _relatorio(1, 3, 1, [0.005])
    agregado = agregar_avaliacoes({"01-x": a, "02-y": b})
    total = agregado["total"]
    assert total["postes"] == {
        "tp": 3,
        "fp": 3,
        "fn": 1,
        "precisao": 3 / 6,
        "recall": 3 / 4,
    }
    # campo "poste": 2/2 e 1/4 somam 3/6; a média das taxas (0,75) não é a taxa do total (0,5)
    assert total["campos"]["poste"] == {"acertos": 3, "total": 6, "taxa": 3 / 6}
    assert total["campos"]["estruturas"] == {"acertos": 0, "total": 3, "taxa": 0.0}
    assert total["vaos"]["comprimento"] == {"acertos": 3, "total": 3, "taxa": 1.0}
    assert total["vaos"]["cabo"] == {"acertos": 2, "total": 3, "taxa": 2 / 3}
    assert total["vaos"]["tp"] == 3
    assert total["simbolos"] == {"tp": 0, "fp": 0, "fn": 1, "precisao": None, "recall": 0.0}
    assert total["distancias_casamento"] == [0.005, 0.01, 0.02]
    assert agregado["por_pdf"]["01-x"]["postes"]["precisao"] == 1.0
    assert agregado["por_pdf"]["02-y"]["postes"]["precisao"] == 1 / 4


def test_agregar_lista_pdf_sem_referencia() -> None:
    rel = _relatorio(2, 0, 0, [0.01])
    agregado = agregar_avaliacoes({"01-x": rel, "02-y": None})
    assert agregado["por_pdf"]["02-y"] == {"situacao": "sem_referencia"}
    assert agregado["total"]["postes"]["tp"] == 2


def test_agregar_falha_nao_entra_como_zero() -> None:
    falha = {"situacao": "falha", "erro": "boom"}
    agregado = agregar_avaliacoes({"01-x": _relatorio(2, 0, 0, []), "02-y": falha})
    assert agregado["por_pdf"]["02-y"] == falha
    assert agregado["total"]["postes"]["tp"] == 2
    assert agregado["total"]["postes"]["fn"] == 0


def test_agregar_sem_nenhum_relatorio_tem_taxas_indefinidas() -> None:
    total = agregar_avaliacoes({"01-x": None})["total"]
    assert total["postes"] == {"tp": 0, "fp": 0, "fn": 0, "precisao": None, "recall": None}
    assert total["distancias_casamento"] == []


# --- CLI ----------------------------------------------------------------------------------


def _congelar_referencia(rodada_dir: Path, pdf_id: str, referencia: Registro) -> Path:
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    pasta.mkdir(parents=True, exist_ok=True)
    escrever_json_atomico(pasta / "referencia.json", referencia)
    escrever_json_atomico(
        pasta / "congelamento.json",
        {
            "schema_version": "curadoria-ficha-congelamento-v1",
            "itens": [
                {
                    "leitor": "consolidada",
                    "arquivo": "referencia.json",
                    "sha256": hash_arquivo(pasta / "referencia.json"),
                    "horario": AGORA,
                    "exposicao": False,
                }
            ],
        },
    )
    return pasta / "referencia.json"


@pytest.fixture
def rodada_rede(tmp_path: Path) -> tuple[Path, str]:
    (tmp_path / "corpus").mkdir()
    pdf = create_network_benchmark_pdf(tmp_path / "corpus" / "rede-secreta.pdf")
    rodada_dir = tmp_path / "rodada"
    iniciar_rodada(
        rodada_dir,
        tmp_path / "corpus",
        concorrencia=3,
        raiz_repositorio=tmp_path / "sem-git",
        agora=AGORA,
    )
    pdf_id = str(carregar_rodada(rodada_dir)["pdfs"][0]["pdf_id"])
    _congelar_referencia(
        rodada_dir, pdf_id, _referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())
    )
    return rodada_dir, pdf_id


def _argv(rodada_dir: Path, *extras: str) -> list[str]:
    return ["baseline", "--rodada", str(rodada_dir), *extras]


def _nao_deve_rodar(*_: Any, **__: Any) -> None:
    raise AssertionError("o analisador não devia rodar")


def _resumos(rodada_dir: Path) -> list[str]:
    return sorted(p.name for p in (rodada_dir / "fichas").glob("baseline-v*-resumo.*"))


def _resumo(rodada_dir: Path, versao: str) -> Registro:
    dados = json.loads((rodada_dir / "fichas" / f"{versao}-resumo.json").read_text("utf-8"))
    assert isinstance(dados, dict)
    return dados


def test_cli_baseline_recusa_pdf_sem_referencia_sem_parcial(
    rodada_rede: tuple[Path, str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, pdf_id = rodada_rede
    (diretorio_ficha(rodada_dir, pdf_id) / "referencia.json").unlink()
    monkeypatch.setattr(curation_ficha, "executar_benchmark", _nao_deve_rodar)
    assert main(_argv(rodada_dir, "--native-only")) == 1
    erro = capsys.readouterr().err
    assert "referencia.json" in erro and pdf_id in erro
    assert _resumos(rodada_dir) == []

    assert main(_argv(rodada_dir, "--native-only", "--parcial")) == 0
    resumo = _resumo(rodada_dir, "baseline-v001")
    assert resumo["parcial"] is True
    assert resumo["por_pdf"][pdf_id] == {"situacao": "sem_referencia"}


def test_cli_baseline_recusa_referencia_adulterada(
    rodada_rede: tuple[Path, str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, pdf_id = rodada_rede
    arquivo = diretorio_ficha(rodada_dir, pdf_id) / "referencia.json"
    adulterada = json.loads(arquivo.read_text("utf-8"))
    adulterada["postes"][0]["identificador"] = "P9"
    escrever_json_atomico(arquivo, adulterada)
    monkeypatch.setattr(curation_ficha, "executar_benchmark", _nao_deve_rodar)
    for extras in ((), ("--parcial",)):
        assert main(_argv(rodada_dir, "--native-only", *extras)) == 1
        assert "adulterada" in capsys.readouterr().err
    assert _resumos(rodada_dir) == []


def test_cli_baseline_sem_ocr_falha_antes_do_primeiro_pdf(
    rodada_rede: tuple[Path, str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, _ = rodada_rede
    chamadas: list[Path] = []

    def sem_portugues(diretorio: Path) -> SimpleNamespace:
        chamadas.append(diretorio)
        return SimpleNamespace(portugues_pronto=False, diagnostico="tesseract ausente")

    monkeypatch.setattr(curation_ficha, "inspect_tesseract_runtime", sem_portugues)
    monkeypatch.setattr(curation_ficha, "executar_benchmark", _nao_deve_rodar)
    assert main(_argv(rodada_dir, "--runtime-directory", str(rodada_dir / "rt"))) == 1
    assert "tesseract ausente" in capsys.readouterr().err
    assert chamadas == [rodada_dir / "rt"]
    assert _resumos(rodada_dir) == []


def test_cli_baseline_grava_versao_nova_sem_sobrescrever(rodada_rede: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada_rede
    assert main(_argv(rodada_dir, "--native-only")) == 0
    primeiro = (rodada_dir / "fichas" / "baseline-v001-resumo.json").read_bytes()
    assert main(_argv(rodada_dir, "--native-only")) == 0
    assert _resumos(rodada_dir) == [
        "baseline-v001-resumo.json",
        "baseline-v001-resumo.md",
        "baseline-v002-resumo.json",
        "baseline-v002-resumo.md",
    ]
    assert (rodada_dir / "fichas" / "baseline-v001-resumo.json").read_bytes() == primeiro
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    for versao in ("baseline-v001", "baseline-v002"):
        assert sorted(p.name for p in (pasta / versao).iterdir()) == [
            "avaliacao.json",
            "ficha-predita.json",
        ]
    assert _resumo(rodada_dir, "baseline-v002")["versao"] == "baseline-v002"


def test_cli_baseline_grava_resumo_sem_caminho_absoluto(rodada_rede: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada_rede
    assert main(_argv(rodada_dir, "--native-only")) == 0
    texto = (rodada_dir / "fichas" / "baseline-v001-resumo.json").read_text("utf-8")
    markdown = (rodada_dir / "fichas" / "baseline-v001-resumo.md").read_text("utf-8")
    for conteudo in (texto, markdown):
        assert pdf_id in conteudo
        assert str(rodada_dir.parent) not in conteudo
        assert rodada_dir.parent.as_posix() not in conteudo
        assert "rede-secreta" not in conteudo
    resumo = json.loads(texto)
    assert resumo["schema_version"] == "curadoria-ficha-baseline-v1"
    assert resumo["parcial"] is False
    assert resumo["opcoes"]["native_only"] is True
    assert set(resumo["versoes"]) == {"pillow", "pymupdf"}
    assert resumo["gerador"]["native_only"] is True
    bloco = resumo["por_pdf"][pdf_id]
    assert bloco["postes"]["tp"] + bloco["postes"]["fn"] == 2
    assert resumo["total"]["postes"]["tp"] == bloco["postes"]["tp"]
    assert f"| {pdf_id} |" in markdown and "TOTAL" in markdown
    assert f"/{bloco['postes']['tp'] + bloco['postes']['fn']}" in markdown


def test_cli_baseline_registra_falha_sem_zerar(
    rodada_rede: tuple[Path, str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rodada_dir, pdf_id = rodada_rede

    def quebra(*_: Any, **__: Any) -> None:
        raise RuntimeError("falha do analisador")

    monkeypatch.setattr(curation_ficha, "executar_benchmark", quebra)
    assert main(_argv(rodada_dir, "--native-only")) == 1
    assert "falha" in capsys.readouterr().err
    resumo = _resumo(rodada_dir, "baseline-v001")
    assert resumo["por_pdf"][pdf_id] == {"situacao": "falha", "erro": "falha do analisador"}
    assert resumo["total"]["postes"]["tp"] == 0
    assert resumo["total"]["postes"]["recall"] is None
