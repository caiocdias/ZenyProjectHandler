"""Amostra humana das fichas do poste e taxa de erro de rótulo (CLI amostra/responder/taxa)."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from scripts.curation_ficha import (
    diretorio_ficha,
    intervalo_wilson,
    main,
    sortear_amostra,
)
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


def test_sortear_amostra_e_deterministica_e_estratificada() -> None:
    pop = {"01-a": ["P1", "P2", "P3"], "02-b": ["P1"], "03-c": ["P1", "P2"]}
    s = sortear_amostra(pop, 3, 7)
    assert s == sortear_amostra(pop, 3, 7)
    assert {pdf for pdf, _ in s} == set(pop)


def test_sortear_amostra_rodizio_e_excluir() -> None:
    pop = {"01-a": ["P1", "P2", "P3"], "02-b": ["P1"]}
    s = sortear_amostra(pop, 3, 1, excluir={("01-a", "P1")})
    assert ("01-a", "P1") not in s
    assert [pdf for pdf, _ in s] == ["01-a", "02-b", "01-a"]


def test_sortear_amostra_maior_que_populacao_devolve_o_restante() -> None:
    pop = {"01-a": ["P1", "P2"], "02-b": ["P1"]}
    s = sortear_amostra(pop, 50, 3, excluir={("02-b", "P1")})
    assert sorted(s) == [("01-a", "P1"), ("01-a", "P2")]


def test_intervalo_wilson_conhecido() -> None:
    assert intervalo_wilson(2, 20) == pytest.approx((0.0279, 0.3010), abs=1e-3)
    assert intervalo_wilson(0, 0) is None
    inferior, superior = intervalo_wilson(0, 10) or (1.0, 0.0)
    assert inferior == 0.0 and 0.2 < superior < 0.4


@pytest.fixture
def rodada(tmp_path: Path) -> tuple[Path, str]:
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
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    pasta.mkdir(parents=True, exist_ok=True)
    escrever_json_atomico(
        pasta / "referencia.json", _referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())
    )
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
    return rodada_dir, pdf_id


def _humana(rodada_dir: Path) -> Path:
    return rodada_dir / "fichas" / "amostra-humana"


def _amostra(rodada_dir: Path, versao: int = 1) -> list[Registro]:
    arquivo = _humana(rodada_dir) / f"amostra-v{versao:03d}" / "amostra.json"
    dados = json.loads(arquivo.read_text("utf-8"))
    assert isinstance(dados, list)
    return dados


def _gerar(rodada_dir: Path, *extras: str, tamanho: int = 2, semente: int = 5) -> int:
    return main(
        [
            "amostra",
            "--rodada",
            str(rodada_dir),
            "--tamanho",
            str(tamanho),
            "--semente",
            str(semente),
            *extras,
        ]
    )


def _responder(rodada_dir: Path, versao: int, respostas: Any, tmp: Path) -> int:
    arquivo = tmp / f"resp-{versao}.json"
    arquivo.write_text(json.dumps(respostas), encoding="utf-8")
    return main(
        [
            "responder",
            "--rodada",
            str(rodada_dir),
            "--versao",
            str(versao),
            "--arquivo",
            str(arquivo),
        ]
    )


def _ok(**mudancas: Any) -> Registro:
    base: Registro = {
        "correto": True,
        "campos_errados": [],
        "nao_e_poste": False,
        "omissao": False,
        "nota": "",
    }
    return {**base, **mudancas}


def test_cli_amostra_grava_recortes_e_md_sem_nome_do_pdf(
    rodada: tuple[Path, str], tmp_path: Path
) -> None:
    rodada_dir, pdf_id = rodada
    assert _gerar(rodada_dir) == 0
    pasta = _humana(rodada_dir) / "amostra-v001"
    itens = _amostra(rodada_dir)
    assert [i["item"] for i in itens] == ["01", "02"]
    assert {i["poste_id"] for i in itens} == {"r1", "r2"}
    assert all(i["pdf_id"] == pdf_id and i["recorte"] == f"{i['item']}.png" for i in itens)
    for item in itens:
        assert (pasta / item["recorte"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    r1 = next(i for i in itens if i["poste_id"] == "r1")
    assert r1["campos"]["identificador"] == "P1"
    assert r1["campos"]["vaos_ligados"][0]["para"] == "r2"
    md = (pasta / "amostra.md").read_text("utf-8")
    assert "01.png" in md and "A ficha está correta?" in md
    for arquivo in (pasta / "amostra.json", pasta / "amostra.md"):
        texto = arquivo.read_text("utf-8")
        assert "rede-secreta" not in texto and str(tmp_path) not in texto


def test_cli_amostra_recusa_repetir_e_ampliar_cria_v002_sem_repetir(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = rodada
    assert _gerar(rodada_dir, tamanho=1) == 0
    primeiro = _amostra(rodada_dir)[0]["poste_id"]
    assert _gerar(rodada_dir, tamanho=1) == 1
    assert "--ampliar" in capsys.readouterr().err
    assert _gerar(rodada_dir, "--ampliar", tamanho=5) == 0
    segundo = _amostra(rodada_dir, 2)
    assert [i["poste_id"] for i in segundo] == [({"r1", "r2"} - {primeiro}).pop()]
    assert segundo[0]["item"] == "01"
    assert (_humana(rodada_dir) / "amostra-v002" / "01.png").is_file()
    assert _gerar(rodada_dir, "--ampliar") == 1  # população esgotada
    assert "erro:" in capsys.readouterr().err
    assert not (_humana(rodada_dir) / "amostra-v003").exists()


def test_cli_amostra_ampliar_sem_amostra_previa_e_pdf_sem_referencia(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    assert _gerar(rodada_dir, "--ampliar") == 1
    assert "erro:" in capsys.readouterr().err
    (diretorio_ficha(rodada_dir, pdf_id) / "referencia.json").unlink()
    assert _gerar(rodada_dir) == 1
    assert "erro:" in capsys.readouterr().err
    assert not (_humana(rodada_dir) / "amostra-v001").exists()


def test_cli_responder_recusa_resposta_faltando_erro_sem_campo_e_regravacao(
    rodada: tuple[Path, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = rodada
    _gerar(rodada_dir)
    destino = _humana(rodada_dir) / "amostra-v001" / "respostas.json"
    invalidas: list[Any] = [
        {"01": _ok()},  # falta o item 02
        {"01": _ok(), "02": _ok(), "03": _ok()},  # item inexistente
        {"01": _ok(), "02": _ok(correto=False)},  # erro sem campo
        {"01": _ok(), "02": _ok(correto=False, campos_errados=["cor"])},  # campo inválido
        {"01": _ok(), "02": {"correto": "sim"}},
        {"01": _ok(), "02": _ok(extra=1)},
        [],
    ]
    for resp in invalidas:
        assert _responder(rodada_dir, 1, resp, tmp_path) == 1, resp
        assert "erro:" in capsys.readouterr().err
        assert not destino.exists()
    assert _responder(rodada_dir, 9, {}, tmp_path) == 1
    capsys.readouterr()
    validas = {"01": _ok(), "02": _ok(correto=False, nao_e_poste=True)}
    assert _responder(rodada_dir, 1, validas, tmp_path) == 0
    antes = destino.read_bytes()
    assert _responder(rodada_dir, 1, {"01": _ok(), "02": _ok()}, tmp_path) == 1
    assert destino.read_bytes() == antes
    assert str(tmp_path) not in antes.decode("utf-8")


def test_cli_taxa_calcula_por_poste_campo_omissao_e_nao_poste(
    rodada: tuple[Path, str], tmp_path: Path
) -> None:
    rodada_dir, _ = rodada
    _gerar(rodada_dir)
    itens = {i["poste_id"]: i["item"] for i in _amostra(rodada_dir)}
    respostas = {
        itens["r1"]: _ok(correto=False, campos_errados=["estruturas", "vaos"], omissao=True),
        itens["r2"]: _ok(),
    }
    assert _responder(rodada_dir, 1, respostas, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0
    taxa = json.loads((_humana(rodada_dir) / "taxa-v001.json").read_text("utf-8"))
    total = taxa["total"]
    assert total["itens"] == 2
    assert total["postes_com_erro"]["k"] == 1 and total["postes_com_erro"]["n"] == 2
    assert total["postes_com_erro"]["taxa"] == 0.5
    assert total["postes_com_erro"]["wilson95"] == pytest.approx(list(intervalo_wilson(1, 2) or ()))
    assert total["nao_e_poste"] == 0
    assert total["omissoes"] == {"k": 1, "n": 2, "taxa": 0.5}
    assert total["por_campo"]["estruturas"] == {"erros": 1, "avaliados": 2}
    assert total["por_campo"]["vaos"] == {"erros": 1, "avaliados": 2}
    assert total["por_campo"]["poste"] == {"erros": 0, "avaliados": 2}
    assert taxa["por_versao"]["amostra-v001"] == total
    assert str(tmp_path) not in json.dumps(taxa)


def test_cli_taxa_exclui_campo_pendente_e_conta_nao_poste(
    rodada: tuple[Path, str], tmp_path: Path
) -> None:
    rodada_dir, _ = rodada
    _gerar(rodada_dir)
    pasta = _humana(rodada_dir) / "amostra-v001"
    itens = _amostra(rodada_dir)
    itens[1]["campos"]["pendentes"] = ["coordenada"]
    escrever_json_atomico(pasta / "amostra.json", itens)
    resp = {
        itens[0]["item"]: _ok(correto=False, nao_e_poste=True),
        itens[1]["item"]: _ok(),
    }
    assert _responder(rodada_dir, 1, resp, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0
    total = json.loads((_humana(rodada_dir) / "taxa-v001.json").read_text("utf-8"))["total"]
    assert total["nao_e_poste"] == 1
    assert total["postes_com_erro"]["k"] == 1
    # item que não é poste não avalia campo; o pendente também fica fora do denominador
    assert total["por_campo"]["coordenada"] == {"erros": 0, "avaliados": 0}
    assert total["por_campo"]["poste"] == {"erros": 0, "avaliados": 1}


def test_cli_taxa_recusa_amostra_sem_respostas_citando_a_versao(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = rodada
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 1
    capsys.readouterr()
    _gerar(rodada_dir, tamanho=1)
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 1
    assert "amostra-v001" in capsys.readouterr().err
    assert list(_humana(rodada_dir).glob("taxa-v*.json")) == []


def test_cli_taxa_versiona_e_nao_sobrescreve(rodada: tuple[Path, str], tmp_path: Path) -> None:
    rodada_dir, _ = rodada
    _gerar(rodada_dir, tamanho=1)
    unico = _amostra(rodada_dir)[0]["item"]
    assert _responder(rodada_dir, 1, {unico: _ok()}, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0
    v1 = (_humana(rodada_dir) / "taxa-v001.json").read_bytes()
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 1  # já existe taxa-v001
    assert (_humana(rodada_dir) / "taxa-v001.json").read_bytes() == v1
    _gerar(rodada_dir, "--ampliar", tamanho=1)
    erro = {"01": _ok(correto=False, campos_errados=["poste"])}
    assert _responder(rodada_dir, 2, erro, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0
    v2 = json.loads((_humana(rodada_dir) / "taxa-v002.json").read_text("utf-8"))
    assert set(v2["por_versao"]) == {"amostra-v001", "amostra-v002"}
    assert v2["total"]["itens"] == 2 and v2["total"]["postes_com_erro"]["k"] == 1
    assert (_humana(rodada_dir) / "taxa-v001.json").read_bytes() == v1
