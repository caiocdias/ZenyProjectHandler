"""CLI ``consolidar`` das fichas do poste: pré-requisitos, terceiro leitor e imutabilidade."""

# ruff: noqa: F811  (fixtures importadas e usadas como parâmetro)
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.curation_ficha import congelar_leitura, diretorio_ficha, main
from scripts.curation_round import hash_arquivo
from scripts.ficha_poste import validar_ficha
from tests.unit.test_curation_ficha import (  # noqa: F401  (fixtures reaproveitadas)
    _ficha,
    _ficha_regional,
    _rascunho,
    modelo,
    rodada,
)

Registro = dict[str, Any]


def _argv_consolidar(rodada_dir: Path, pdf_id: str, *extras: str) -> list[str]:
    return ["consolidar", "--rodada", str(rodada_dir), "--pdf", pdf_id, *extras]


def _congelar(rodada_dir: Path, pdf_id: str, leitor: str, ficha: Registro) -> None:
    congelar_leitura(rodada_dir, pdf_id, leitor, _rascunho(rodada_dir, pdf_id, leitor, ficha))


def _congelar_a_b_e_comparar(rodada_dir: Path, pdf_id: str, *, divergente: bool) -> None:
    _congelar(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    leitura_b = _ficha(rodada_dir, pdf_id, "b")
    if divergente:
        leitura_b["postes"][0]["estruturas"] = ["N3"]
    _congelar(rodada_dir, pdf_id, "b", leitura_b)
    assert main(["comparar", "--rodada", str(rodada_dir), "--pdf", pdf_id]) == 0


def _ler(arquivo: Path) -> Registro:
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    assert isinstance(dados, dict)
    return dados


def _sem_caminho(texto: str, rodada_dir: Path) -> bool:
    return (
        str(rodada_dir) not in texto
        and str(rodada_dir).replace("\\", "/") not in texto
        and "a.pdf" not in texto
    )


def test_cli_consolidar_exige_a_comparacao(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _congelar(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    _congelar(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b"))
    assert main(_argv_consolidar(rodada_dir, pdf_id)) == 1
    erro = capsys.readouterr().err
    assert "comparacao.json" in erro
    assert _sem_caminho(erro, rodada_dir)
    assert not (diretorio_ficha(rodada_dir, pdf_id) / "referencia.json").exists()


def test_cli_consolidar_exige_c_ou_sem_terceiro_com_motivo(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _congelar_a_b_e_comparar(rodada_dir, pdf_id, divergente=True)
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    capsys.readouterr()

    assert main(_argv_consolidar(rodada_dir, pdf_id)) == 1
    assert "--sem-terceiro" in capsys.readouterr().err
    assert main(_argv_consolidar(rodada_dir, pdf_id, "--sem-terceiro")) == 1
    assert "--motivo" in capsys.readouterr().err
    assert main(_argv_consolidar(rodada_dir, pdf_id, "--sem-terceiro", "--motivo", " ")) == 1
    assert "--motivo" in capsys.readouterr().err
    assert main(_argv_consolidar(rodada_dir, pdf_id, "--motivo", "sem C")) == 1
    assert "--sem-terceiro" in capsys.readouterr().err
    assert not (pasta / "referencia.json").exists()

    motivo = "leitor C indisponível nesta rodada"
    assert main(_argv_consolidar(rodada_dir, pdf_id, "--sem-terceiro", "--motivo", motivo)) == 0
    saida = capsys.readouterr()
    assert saida.err == ""
    assert "referência consolidada" in saida.out
    assert "pendentes=1" in saida.out
    assert _sem_caminho(saida.out, rodada_dir)

    referencia = _ler(pasta / "referencia.json")
    assert validar_ficha(referencia) == []
    consolidacao = referencia["atributos_extras"]["consolidacao"]
    assert consolidacao["motivo_sem_terceiro"] == motivo
    assert (consolidacao["pendentes"], consolidacao["nao_cobertas_por_c"]) == (1, 1)
    assert referencia["postes"][0]["pendentes"] == ["estruturas"]
    assert _sem_caminho((pasta / "referencia.json").read_text(encoding="utf-8"), rodada_dir)

    itens = _ler(pasta / "congelamento.json")["itens"]
    [item] = [i for i in itens if i["leitor"] == "consolidada"]
    assert item["arquivo"] == "referencia.json"
    assert item["sha256"] == hash_arquivo(pasta / "referencia.json")
    assert item["exposicao"] is False

    antes = (pasta / "referencia.json").read_bytes()
    assert main(_argv_consolidar(rodada_dir, pdf_id, "--sem-terceiro", "--motivo", motivo)) == 1
    assert "já" in capsys.readouterr().err
    assert (pasta / "referencia.json").read_bytes() == antes
    assert len(_ler(pasta / "congelamento.json")["itens"]) == len(itens)


def test_cli_consolidar_com_c_congelada_resolve_e_recusa_sem_terceiro(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _congelar_a_b_e_comparar(rodada_dir, pdf_id, divergente=True)
    _congelar(rodada_dir, pdf_id, "c", _ficha_regional(rodada_dir, pdf_id, "c"))
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    capsys.readouterr()

    assert main(_argv_consolidar(rodada_dir, pdf_id, "--sem-terceiro", "--motivo", "x")) == 1
    assert "leitura c" in capsys.readouterr().err
    assert not (pasta / "referencia.json").exists()

    assert main(_argv_consolidar(rodada_dir, pdf_id)) == 0
    assert "resolvidas_por_c=1" in capsys.readouterr().out
    referencia = _ler(pasta / "referencia.json")
    assert validar_ficha(referencia) == []
    assert referencia["postes"][0]["estruturas"] == []
    assert referencia["postes"][0]["pendentes"] == []
    assert "motivo_sem_terceiro" not in referencia["atributos_extras"]["consolidacao"]


def test_cli_consolidar_sem_divergencias_dispensa_o_terceiro(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _congelar_a_b_e_comparar(rodada_dir, pdf_id, divergente=False)
    assert main(_argv_consolidar(rodada_dir, pdf_id)) == 0
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    referencia = _ler(pasta / "referencia.json")
    leitura_a = _ler(pasta / "leitura-a.json")
    assert referencia["postes"] == leitura_a["postes"]
    assert referencia["escopo_anotacao"] == {"tipo": "completo"}
    assert "leitura" not in referencia["atributos_extras"]


def test_cli_consolidar_recusa_folha_sem_area_anotavel_sem_gravar_nada(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    ilegivel = {"pagina": 1, "camada": "base", "bbox": [0.0, 0.0, 1.0, 1.0], "motivo": "mancha"}
    for leitor in ("a", "b"):
        _congelar(
            rodada_dir, pdf_id, leitor, _ficha(rodada_dir, pdf_id, leitor, ilegiveis=[ilegivel])
        )
    assert main(["comparar", "--rodada", str(rodada_dir), "--pdf", pdf_id]) == 0
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    manifesto = (pasta / "congelamento.json").read_bytes()
    capsys.readouterr()

    assert main(_argv_consolidar(rodada_dir, pdf_id)) == 1
    saida = capsys.readouterr()
    assert saida.err.startswith("erro: folha sem área anotável")
    assert "ilegivel=1" in saida.err
    assert _sem_caminho(saida.err, rodada_dir)
    assert not (pasta / "referencia.json").exists()
    assert (pasta / "congelamento.json").read_bytes() == manifesto


def test_cli_consolidar_recusa_comparacao_adulterada(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _congelar_a_b_e_comparar(rodada_dir, pdf_id, divergente=True)
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    comparacao = _ler(pasta / "comparacao.json")
    comparacao["divergencias"] = []
    (pasta / "comparacao.json").write_text(json.dumps(comparacao), encoding="utf-8")
    capsys.readouterr()
    assert main(_argv_consolidar(rodada_dir, pdf_id)) == 1
    assert "comparação" in capsys.readouterr().err
    assert not (pasta / "referencia.json").exists()
