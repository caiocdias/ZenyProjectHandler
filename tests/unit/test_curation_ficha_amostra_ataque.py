"""Ataques à amostra humana: sorteio, Wilson, recortes, ampliação, respostas e taxa."""

from __future__ import annotations

import json
import struct
from hashlib import sha256
from pathlib import Path
from typing import Any

import pymupdf
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
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica

Registro = dict[str, Any]
AGORA = "2026-10-15T12:00:00+00:00"


# --- sortear_amostra ------------------------------------------------------------------------


def test_sorteio_nao_depende_da_ordem_de_insercao_nem_altera_a_entrada() -> None:
    a = {"01": ["P3", "P1", "P2"], "02": ["P2", "P1"], "03": ["P1"]}
    b = {"03": ["P1"], "02": ["P1", "P2"], "01": ["P2", "P3", "P1"]}
    copia = {k: list(v) for k, v in a.items()}
    assert sortear_amostra(a, 5, 11) == sortear_amostra(b, 5, 11)
    assert a == copia


def test_sorteio_sem_repeticao_e_tamanho_exato() -> None:
    pop = {f"{i:02d}": [f"P{j}" for j in range(4)] for i in range(5)}
    s = sortear_amostra(pop, 13, 3)
    assert len(s) == 13 and len(set(s)) == 13
    assert all(poste in pop[pdf] for pdf, poste in s)


def test_sorteio_rodizio_cobre_cada_pdf_antes_de_repetir() -> None:
    pop = {"01": ["a", "b", "c"], "02": ["a", "b", "c"], "03": ["a"]}
    s = sortear_amostra(pop, 3, 99)
    assert [pdf for pdf, _ in s] == ["01", "02", "03"]
    s = sortear_amostra(pop, 5, 99)
    assert [pdf for pdf, _ in s] == ["01", "02", "03", "01", "02"]


def test_sorteio_tamanho_zero_populacao_vazia_e_tudo_excluido() -> None:
    pop = {"01": ["a", "b"]}
    assert sortear_amostra(pop, 0, 1) == []
    assert sortear_amostra({}, 5, 1) == []
    assert sortear_amostra({"01": []}, 5, 1) == []
    assert sortear_amostra(pop, 5, 1, excluir=[("01", "a"), ("01", "b")]) == []


def test_sorteio_excluir_de_outro_pdf_nao_afeta_poste_homonimo() -> None:
    pop = {"01": ["P1"], "02": ["P1"]}
    assert sortear_amostra(pop, 5, 1, excluir={("01", "P1")}) == [("02", "P1")]


def test_sorteio_depende_da_semente() -> None:
    pop = {"01": [f"P{i}" for i in range(12)]}
    ordens = {tuple(sortear_amostra(pop, 12, semente)) for semente in range(8)}
    assert len(ordens) > 1


# --- intervalo de Wilson --------------------------------------------------------------------


def test_wilson_extremos_zero_e_todos() -> None:
    inferior, superior = intervalo_wilson(0, 20) or (9.0, 9.0)
    assert inferior == pytest.approx(0.0, abs=1e-12)
    assert superior == pytest.approx(0.1611, abs=1e-3)
    inferior, superior = intervalo_wilson(20, 20) or (9.0, 9.0)
    assert inferior == pytest.approx(0.8389, abs=1e-3)
    assert superior == pytest.approx(1.0, abs=1e-12)


def test_wilson_um_de_um_e_zero_de_um() -> None:
    assert intervalo_wilson(1, 1) == pytest.approx((0.2065, 1.0), abs=1e-3)
    assert intervalo_wilson(0, 1) == pytest.approx((0.0, 0.7935), abs=1e-3)


def test_wilson_propriedades_em_toda_a_grade() -> None:
    for n in range(1, 31):
        anterior = (-1.0, -1.0)
        for k in range(n + 1):
            intervalo = intervalo_wilson(k, n)
            assert intervalo is not None
            inferior, superior = intervalo
            # tolerância: o arredondamento de ponto flutuante deixa 6/6 em 0.9999999999999999
            assert 0.0 <= inferior <= k / n + 1e-12
            assert k / n - 1e-12 <= superior <= 1.0
            assert inferior > anterior[0] - 1e-12 and superior > anterior[1] - 1e-12
            espelho = intervalo_wilson(n - k, n) or (9.0, 9.0)
            assert inferior == pytest.approx(1 - espelho[1], abs=1e-9)
            anterior = intervalo


def test_wilson_z_maior_alarga_o_intervalo() -> None:
    estreito = intervalo_wilson(3, 20, z=1.0) or (0.0, 0.0)
    largo = intervalo_wilson(3, 20, z=2.58) or (0.0, 0.0)
    assert largo[0] < estreito[0] and largo[1] > estreito[1]


# --- CLI: fixtures --------------------------------------------------------------------------


def _pdf(caminho: Path, rotulo: str) -> Path:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=600, height=400)
        pagina.insert_text((100, 100), rotulo, fontsize=10)
        pagina.draw_line((110, 115), (460, 115), color=(0, 0.5, 0))
        documento.save(caminho)
    return caminho


def _referencia(sha: str, postes: list[Registro] | None = None) -> Registro:
    ref = _referencia_sintetica(sha)
    if postes is not None:
        ref["postes"] = postes
        ref["vaos"] = []
    return ref


def _congelar(pasta: Path, referencia: Registro) -> None:
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


def _montar(
    tmp_path: Path, nomes: list[str], com_referencia: list[bool] | None = None
) -> tuple[Path, list[str]]:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for nome in nomes:
        _pdf(corpus / f"{nome}.pdf", nome)
    rodada_dir = tmp_path / "rodada"
    iniciar_rodada(
        rodada_dir, corpus, concorrencia=3, raiz_repositorio=tmp_path / "sem-git", agora=AGORA
    )
    entradas = carregar_rodada(rodada_dir)["pdfs"]
    ids = [str(e["pdf_id"]) for e in entradas]
    flags = com_referencia or [True] * len(ids)
    for entrada, tem in zip(entradas, flags, strict=True):
        if tem:
            origem = corpus / Path(str(entrada["caminho_relativo"])).name
            sha = sha256(origem.read_bytes()).hexdigest()
            _congelar(diretorio_ficha(rodada_dir, str(entrada["pdf_id"])), _referencia(sha))
    return rodada_dir, ids


def _humana(rodada_dir: Path) -> Path:
    return rodada_dir / "fichas" / "amostra-humana"


def _amostra(rodada_dir: Path, versao: int = 1) -> list[Registro]:
    texto = (_humana(rodada_dir) / f"amostra-v{versao:03d}" / "amostra.json").read_text("utf-8")
    dados = json.loads(texto)
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


def _dimensoes_png(dados: bytes) -> tuple[int, int]:
    assert dados[:8] == b"\x89PNG\r\n\x1a\n"
    largura, altura = struct.unpack(">II", dados[16:24])
    return int(largura), int(altura)


# --- CLI amostra ----------------------------------------------------------------------------


def test_amostra_so_usa_pdfs_com_referencia_e_estratifica_entre_eles(tmp_path: Path) -> None:
    rodada_dir, ids = _montar(
        tmp_path, ["alfa-secreto", "beta-secreto", "gama-secreto"], [True, False, True]
    )
    assert _gerar(rodada_dir, tamanho=4) == 0
    itens = _amostra(rodada_dir)
    assert {i["pdf_id"] for i in itens} == {ids[0], ids[2]}
    assert [i["pdf_id"] for i in itens].count(ids[0]) == 2
    assert [i["pdf_id"] for i in itens].count(ids[2]) == 2
    assert [i["item"] for i in itens] == ["01", "02", "03", "04"]
    pasta = _humana(rodada_dir) / "amostra-v001"
    for arquivo in pasta.iterdir():
        dados = arquivo.read_bytes()
        assert b"secreto" not in dados and str(tmp_path).encode() not in dados


def test_amostra_e_reprodutivel_entre_rodadas_com_mesma_semente(tmp_path: Path) -> None:
    resultados = []
    for nome in ("r1", "r2"):
        base = tmp_path / nome
        base.mkdir()
        rodada_dir, _ = _montar(base, ["alfa", "beta"])
        assert _gerar(rodada_dir, tamanho=3, semente=42) == 0
        resultados.append([(i["poste_id"], i["pagina"], i["bbox"]) for i in _amostra(rodada_dir)])
    assert resultados[0] == resultados[1]


def test_recorte_no_canto_e_recortado_a_pagina(tmp_path: Path) -> None:
    rodada_dir, ids = _montar(tmp_path, ["alfa"])
    sha = sha256(next((tmp_path / "corpus").glob("*.pdf")).read_bytes()).hexdigest()

    def poste(id_: str, bbox: list[float]) -> Registro:
        return {
            "id": id_,
            "pagina": 1,
            "bbox": bbox,
            "identificador": id_,
            "estruturas": [],
            "poste": None,
            "coordenada": None,
            "simbolos": [],
            "pendentes": [],
        }

    postes = [poste("sup", [0.0, 0.0, 0.02, 0.02]), poste("inf", [0.98, 0.98, 1.0, 1.0])]
    _congelar(diretorio_ficha(rodada_dir, ids[0]), _referencia(sha, postes))
    assert _gerar(rodada_dir, tamanho=2) == 0
    pasta = _humana(rodada_dir) / "amostra-v001"
    for item in _amostra(rodada_dir):
        largura, altura = _dimensoes_png((pasta / item["recorte"]).read_bytes())
        # 0,06 da página (0,02 + margem 0,04) a 300 dpi: 36 pt x 24 pt -> 150 x 100 px
        assert abs(largura - 150) <= 2 and abs(altura - 100) <= 2, (
            item["poste_id"],
            largura,
            altura,
        )


def test_recorte_de_poste_no_meio_inclui_margem_dos_dois_lados(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    assert _gerar(rodada_dir, tamanho=2) == 0
    pasta = _humana(rodada_dir) / "amostra-v001"
    for item in _amostra(rodada_dir):
        x0, y0, x1, y1 = item["bbox"]
        esperado = ((x1 - x0 + 0.08) * 600 * 300 / 72, (y1 - y0 + 0.08) * 400 * 300 / 72)
        largura, altura = _dimensoes_png((pasta / item["recorte"]).read_bytes())
        assert abs(largura - esperado[0]) <= 3 and abs(altura - esperado[1]) <= 3


def test_pagina_inexistente_nao_deixa_amostra_parcial_e_permite_nova_tentativa(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, ids = _montar(tmp_path, ["alfa"])
    pasta_ficha = diretorio_ficha(rodada_dir, ids[0])
    original = json.loads((pasta_ficha / "referencia.json").read_text("utf-8"))
    quebrada = json.loads(json.dumps(original))
    quebrada["postes"][0]["pagina"] = 7
    quebrada["postes"][1]["pagina"] = 7
    _congelar(pasta_ficha, quebrada)
    assert _gerar(rodada_dir, tamanho=2) == 1
    assert "erro:" in capsys.readouterr().err
    assert not (_humana(rodada_dir) / "amostra-v001").exists()
    _congelar(pasta_ficha, original)
    assert _gerar(rodada_dir, tamanho=2) == 0
    assert len(_amostra(rodada_dir)) == 2


def test_referencia_adulterada_apos_congelar_recusa_amostra(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, ids = _montar(tmp_path, ["alfa"])
    arquivo = diretorio_ficha(rodada_dir, ids[0]) / "referencia.json"
    dados = json.loads(arquivo.read_text("utf-8"))
    dados["postes"][0]["identificador"] = "ADULTERADO"
    escrever_json_atomico(arquivo, dados)
    assert _gerar(rodada_dir) == 1
    assert "erro:" in capsys.readouterr().err
    assert not (_humana(rodada_dir) / "amostra-v001").exists()


@pytest.mark.parametrize("tamanho", [0, -3])
def test_amostra_tamanho_nao_positivo_e_recusado(
    tmp_path: Path, tamanho: int, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    assert _gerar(rodada_dir, tamanho=tamanho) == 1
    assert "erro:" in capsys.readouterr().err
    assert not (_humana(rodada_dir) / "amostra-v001").exists()


def test_ampliar_nao_toca_a_v001_e_nao_repete_mesmo_com_outra_semente(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa", "beta"])
    assert _gerar(rodada_dir, tamanho=3, semente=1) == 0
    v1 = _humana(rodada_dir) / "amostra-v001"
    antes = {p.name: p.read_bytes() for p in v1.iterdir()}
    assert _gerar(rodada_dir, "--ampliar", tamanho=10, semente=999) == 0
    assert {p.name: p.read_bytes() for p in v1.iterdir()} == antes
    primeiros = {(i["pdf_id"], i["poste_id"]) for i in _amostra(rodada_dir, 1)}
    segundos = {(i["pdf_id"], i["poste_id"]) for i in _amostra(rodada_dir, 2)}
    assert len(primeiros) == 3 and len(segundos) == 1  # 2 PDFs x 2 postes = 4
    assert not primeiros & segundos
    assert [i["item"] for i in _amostra(rodada_dir, 2)] == ["01"]


def test_ampliar_duas_vezes_gera_v002_e_v003_disjuntas(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa", "beta", "gama"])
    assert _gerar(rodada_dir, tamanho=2) == 0
    assert _gerar(rodada_dir, "--ampliar", tamanho=2) == 0
    assert _gerar(rodada_dir, "--ampliar", tamanho=2) == 0
    todos = [(i["pdf_id"], i["poste_id"]) for v in (1, 2, 3) for i in _amostra(rodada_dir, v)]
    assert len(todos) == 6 and len(set(todos)) == 6


def test_amostra_md_tem_uma_secao_por_item_com_imagem_e_perguntas(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa", "beta"])
    assert _gerar(rodada_dir, tamanho=3) == 0
    md = (_humana(rodada_dir) / "amostra-v001" / "amostra.md").read_text("utf-8")
    for numero in ("01", "02", "03"):
        assert f"({numero}.png)" in md and f"## Item {numero}" in md
    assert md.count("O item não é poste?") == 3
    assert md.count("A ficha está correta?") == 3
    assert md.count("não está na ficha?") == 3


def test_amostra_json_so_tem_as_chaves_do_contrato(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    assert _gerar(rodada_dir) == 0
    for item in _amostra(rodada_dir):
        assert set(item) == {"item", "pdf_id", "poste_id", "pagina", "bbox", "campos", "recorte"}
        assert set(item["campos"]) == {
            "identificador",
            "estruturas",
            "poste",
            "coordenada",
            "simbolos",
            "vaos_ligados",
            "pendentes",
        }


# --- CLI responder --------------------------------------------------------------------------


def test_responder_arquivo_inexistente_ou_json_invalido_falha_sem_gravar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    _gerar(rodada_dir)
    destino = _humana(rodada_dir) / "amostra-v001" / "respostas.json"
    argumentos = ["responder", "--rodada", str(rodada_dir), "--versao", "1", "--arquivo"]
    assert main([*argumentos, str(tmp_path / "nao-existe.json")]) == 1
    assert "erro:" in capsys.readouterr().err
    quebrado = tmp_path / "quebrado.json"
    quebrado.write_text("{ nao e json", encoding="utf-8")
    assert main([*argumentos, str(quebrado)]) == 1
    assert "erro:" in capsys.readouterr().err
    assert not destino.exists()


@pytest.mark.parametrize(
    "resposta",
    [
        _ok(nao_e_poste=True),  # não é poste mas "correto"
        _ok(campos_errados=["poste"]),  # correto com campo errado
        _ok(correto=1),  # inteiro não é booleano
        _ok(nao_e_poste="nao"),
        _ok(omissao="nao"),
        _ok(correto=False, campos_errados="poste"),  # texto no lugar de lista
        _ok(correto=False, campos_errados=[["poste"]]),
        _ok(correto=False, campos_errados=["vaos_ligados"]),  # nome interno, não avaliado
        _ok(nota=5),
        None,
        "ok",
        {"campos_errados": []},  # sem "correto"
    ],
)
def test_responder_recusa_resposta_invalida_e_aceita_depois_a_correta(
    tmp_path: Path, resposta: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    _gerar(rodada_dir, tamanho=1)
    destino = _humana(rodada_dir) / "amostra-v001" / "respostas.json"
    assert _responder(rodada_dir, 1, {"01": resposta}, tmp_path) == 1
    assert "erro:" in capsys.readouterr().err
    assert not destino.exists()
    assert _responder(rodada_dir, 1, {"01": _ok()}, tmp_path) == 0
    assert json.loads(destino.read_text("utf-8")) == {"01": _ok()}


def test_responder_aceita_resposta_minima_sem_chaves_opcionais(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    _gerar(rodada_dir, tamanho=1)
    assert _responder(rodada_dir, 1, {"01": {"correto": True}}, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0


def test_responder_nao_altera_a_amostra(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    _gerar(rodada_dir)
    pasta = _humana(rodada_dir) / "amostra-v001"
    antes = {p.name: p.read_bytes() for p in pasta.iterdir()}
    itens = {i["item"]: _ok() for i in _amostra(rodada_dir)}
    assert _responder(rodada_dir, 1, itens, tmp_path) == 0
    depois = {p.name: p.read_bytes() for p in pasta.iterdir() if p.name != "respostas.json"}
    assert depois == antes


# --- CLI taxa -------------------------------------------------------------------------------


def _taxa(rodada_dir: Path, versao: int) -> Registro:
    texto = (_humana(rodada_dir) / f"taxa-v{versao:03d}.json").read_text("utf-8")
    dados = json.loads(texto)
    assert isinstance(dados, dict)
    return dados


def test_taxa_omissao_em_ficha_correta_conta_so_como_omissao(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    _gerar(rodada_dir)
    resp = {"01": _ok(omissao=True), "02": _ok()}
    assert _responder(rodada_dir, 1, resp, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0
    total = _taxa(rodada_dir, 1)["total"]
    assert total["omissoes"] == {"k": 1, "n": 2, "taxa": 0.5}
    assert total["postes_com_erro"]["k"] == 0
    assert total["postes_com_erro"]["taxa"] == 0.0
    inferior, superior = total["postes_com_erro"]["wilson95"]
    assert inferior == pytest.approx(0.0, abs=1e-12) and 0.5 < superior < 0.8
    assert all(c["erros"] == 0 and c["avaliados"] == 2 for c in total["por_campo"].values())


def test_taxa_nao_poste_com_campo_marcado_nao_entra_em_por_campo(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    _gerar(rodada_dir)
    resp = {
        "01": _ok(correto=False, nao_e_poste=True, campos_errados=["poste"]),
        "02": _ok(correto=False, campos_errados=["poste", "simbolos"]),
    }
    assert _responder(rodada_dir, 1, resp, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0
    total = _taxa(rodada_dir, 1)["total"]
    assert total["nao_e_poste"] == 1 and total["postes_com_erro"]["k"] == 2
    assert total["por_campo"]["poste"] == {"erros": 1, "avaliados": 1}
    assert total["por_campo"]["simbolos"] == {"erros": 1, "avaliados": 1}
    assert total["por_campo"]["identificador"] == {"erros": 0, "avaliados": 1}


def test_taxa_por_campo_pendente_so_sai_do_denominador_daquele_item(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    _gerar(rodada_dir)
    pasta = _humana(rodada_dir) / "amostra-v001"
    itens = _amostra(rodada_dir)
    itens[0]["campos"]["pendentes"] = ["estruturas", "simbolos"]
    escrever_json_atomico(pasta / "amostra.json", itens)
    assert _responder(rodada_dir, 1, {"01": _ok(), "02": _ok()}, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0
    campos = _taxa(rodada_dir, 1)["total"]["por_campo"]
    assert campos["estruturas"] == {"erros": 0, "avaliados": 1}
    assert campos["simbolos"] == {"erros": 0, "avaliados": 1}
    assert campos["identificador"] == {"erros": 0, "avaliados": 2}
    assert campos["vaos"] == {"erros": 0, "avaliados": 2}


def test_taxa_agrega_versoes_e_total_e_a_soma_das_partes(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa", "beta"])
    _gerar(rodada_dir, tamanho=3)
    r1 = {
        "01": _ok(correto=False, campos_errados=["estruturas"], omissao=True),
        "02": _ok(),
        "03": _ok(correto=False, nao_e_poste=True),
    }
    assert _responder(rodada_dir, 1, r1, tmp_path) == 0
    _gerar(rodada_dir, "--ampliar", tamanho=3)
    r2 = {"01": _ok(correto=False, campos_errados=["vaos"])}
    assert _responder(rodada_dir, 2, r2, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0
    taxa = _taxa(rodada_dir, 2)
    assert taxa["versao"] == "taxa-v002"
    v1 = taxa["por_versao"]["amostra-v001"]
    v2 = taxa["por_versao"]["amostra-v002"]
    total = taxa["total"]
    assert (v1["itens"], v1["postes_com_erro"]["k"]) == (3, 2)
    assert (v2["itens"], v2["postes_com_erro"]["k"]) == (1, 1)
    erro = total["postes_com_erro"]
    assert (total["itens"], erro["k"], erro["n"]) == (4, 3, 4)
    assert erro["taxa"] == 0.75
    assert total["omissoes"] == {"k": 1, "n": 4, "taxa": 0.25}
    assert total["nao_e_poste"] == 1
    assert total["por_campo"]["estruturas"] == {"erros": 1, "avaliados": 3}
    assert total["por_campo"]["vaos"] == {"erros": 1, "avaliados": 3}
    esperado = intervalo_wilson(3, 4) or (0.0, 0.0)
    assert erro["wilson95"] == pytest.approx(list(esperado))


def test_taxa_recusa_se_a_ultima_versao_nao_tem_respostas_mesmo_com_v001_respondida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    _gerar(rodada_dir, tamanho=1)
    assert _responder(rodada_dir, 1, {"01": _ok()}, tmp_path) == 0
    _gerar(rodada_dir, "--ampliar", tamanho=1)
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 1
    erro = capsys.readouterr().err
    assert "amostra-v002" in erro and "amostra-v001" not in erro
    assert list(_humana(rodada_dir).glob("taxa-v*.json")) == []


def test_taxa_recusa_respostas_adulteradas_depois_de_gravadas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa"])
    _gerar(rodada_dir, tamanho=1)
    assert _responder(rodada_dir, 1, {"01": _ok()}, tmp_path) == 0
    destino = _humana(rodada_dir) / "amostra-v001" / "respostas.json"
    destino.write_text(json.dumps({"01": _ok(correto=False)}), encoding="utf-8")  # sem campos
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 1
    assert "amostra-v001" in capsys.readouterr().err
    destino.write_text(json.dumps({}), encoding="utf-8")  # falta o item
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 1
    assert list(_humana(rodada_dir).glob("taxa-v*.json")) == []


def test_taxa_nao_vaza_caminho_nem_nome_do_pdf(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, ["alfa-secreto"])
    _gerar(rodada_dir, tamanho=1)
    assert _responder(rodada_dir, 1, {"01": _ok(nota="ok")}, tmp_path) == 0
    assert main(["taxa", "--rodada", str(rodada_dir)]) == 0
    texto = (_humana(rodada_dir) / "taxa-v001.json").read_text("utf-8")
    assert "secreto" not in texto and str(tmp_path) not in texto
