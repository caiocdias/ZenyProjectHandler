"""Ataques à validação e ao congelamento de leituras de ficha (complemento do desenvolvedor)."""

# ruff: noqa: F811  (fixtures importadas e usadas como parâmetro)
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.curation_ficha import (
    carregar_congelada,
    congelar_leitura,
    diretorio_ficha,
    erros_leitura,
    main,
)
from scripts.curation_reference import tiles_nao_cobertos
from scripts.curation_render import caminho_indice, carregar_indice
from scripts.curation_round import RodadaError, escrever_json_atomico
from tests.unit.test_curation_ficha import (  # noqa: F401  (fixtures reaproveitadas)
    REGIAO_C,
    _argv,
    _ficha,
    _ficha_regional,
    _gravar_conferencia,
    _norm,
    _rascunho,
    _tile_base_a_revisar,
    _tiles_a_revisar,
    _tiles_que_cobrem,
    modelo,
    rodada,
)

Registro = dict[str, Any]


def _ids(indice: Registro, camada: str) -> list[str]:
    return [str(t["id"]) for t in indice["tiles"] if t["camada"] == camada]


def _com_anotada_igual_base(rodada_dir: Path, pdf_id: str) -> Registro:
    """Reescreve o índice da cópia: camada anotada igual à base (como no teste de referência)."""
    indice = copy.deepcopy(carregar_indice(rodada_dir, pdf_id))
    base = {
        (t["linha"], t["coluna"])
        for t in indice["tiles"]
        if t["camada"] == "base" and t["estado"] == "a_revisar"
    }
    for tile in indice["tiles"]:
        if tile["camada"] == "annotation":
            tile["estado"] = (
                "a_revisar" if (tile["linha"], tile["coluna"]) in base else "descartado_branco"
            )
    indice["paginas"][0]["camada_anotada_igual_base"] = True
    escrever_json_atomico(caminho_indice(rodada_dir, pdf_id), indice)
    return indice


# --- tiles_nao_cobertos --------------------------------------------------------------------


def test_tiles_nao_cobertos_so_base_revisada_deixa_a_anotada_descoberta(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    base = [i for i in _tiles_a_revisar(indice) if "-base-" in i]
    anotadas = [i for i in _tiles_a_revisar(indice) if "-anotada-" in i]
    assert base and anotadas
    # camada_anotada_igual_base é False nesta página: o gêmeo base não vale
    assert tiles_nao_cobertos(indice, base, []) == anotadas


def test_tiles_nao_cobertos_geme_base_cobre_anotada_quando_camadas_iguais(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    indice = _com_anotada_igual_base(rodada_dir, pdf_id)
    base = [i for i in _tiles_a_revisar(indice) if "-base-" in i]
    assert tiles_nao_cobertos(indice, base, []) == []
    # sem um dos gêmeos base, o par anotado volta a ficar descoberto
    resto = base[1:]
    assert tiles_nao_cobertos(indice, resto, []) != []


def test_validar_completo_aceita_so_base_quando_anotada_igual_base(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    indice = _com_anotada_igual_base(rodada_dir, pdf_id)
    base = [i for i in _tiles_a_revisar(indice) if "-base-" in i]
    ficha = _ficha(rodada_dir, pdf_id, "a", tiles=base)
    assert erros_leitura(rodada_dir, pdf_id, "a", ficha) == []


def test_validar_completo_recusa_so_base_quando_anotada_difere(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    base = [i for i in _tiles_a_revisar(indice) if "-base-" in i]
    anotadas = [i for i in _tiles_a_revisar(indice) if "-anotada-" in i]
    erros = erros_leitura(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b", tiles=base))
    for tile in anotadas:
        assert any(tile in e for e in erros), (tile, erros)


def test_tiles_nao_cobertos_regiao_ilegivel_parcial_nao_cobre(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    alvo = _tile_base_a_revisar(indice)
    x0, y0, x1, y1 = alvo["bbox"]
    metade = [x0, y0, (x0 + x1) / 2, y1]
    revisados = [i for i in _tiles_a_revisar(indice) if i != alvo["id"]]
    assert alvo["id"] in tiles_nao_cobertos(
        indice, revisados, [(alvo["pagina"], alvo["camada"], metade)]
    )


def test_tiles_nao_cobertos_regiao_ilegivel_de_outra_camada_ou_pagina_nao_cobre(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    alvo = _tile_base_a_revisar(indice)
    revisados = [i for i in _tiles_a_revisar(indice) if i != alvo["id"]]
    outra_camada = (alvo["pagina"], "annotation", alvo["bbox"])
    outra_pagina = (alvo["pagina"] + 1, alvo["camada"], alvo["bbox"])
    assert alvo["id"] in tiles_nao_cobertos(indice, revisados, [outra_camada, outra_pagina])


def test_tiles_nao_cobertos_aceita_iteraveis_e_nao_exige_ordem(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    todos = _tiles_a_revisar(indice)
    assert tiles_nao_cobertos(indice, iter(reversed(todos)), iter([])) == []
    assert tiles_nao_cobertos(indice, [], []) == todos
    assert tiles_nao_cobertos(indice, frozenset(todos), ()) == []


def test_tiles_nao_cobertos_ignora_revisado_descartado_e_nao_revisado_branco(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    brancos = [str(t["id"]) for t in indice["tiles"] if t["estado"] != "a_revisar"]
    assert brancos
    # tile em branco nunca é exigido; revisá-lo não cobre os a_revisar
    assert tiles_nao_cobertos(indice, brancos, []) == _tiles_a_revisar(indice)
    assert not set(tiles_nao_cobertos(indice, [], [])) & set(brancos)


# --- leitor c ------------------------------------------------------------------------------


def test_validar_c_regiao_coberta_so_por_ilegivel_de_c(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _gravar_conferencia(rodada_dir, pdf_id)
    ficha = _ficha_regional(rodada_dir, pdf_id, "c")
    leitura = ficha["atributos_extras"]["leitura"]
    indice = carregar_indice(rodada_dir, pdf_id)
    longe = next(str(t["id"]) for t in indice["tiles"] if t["bbox"][1] > 0.5)
    leitura["tiles_revisados"] = [longe]
    leitura["regioes_ilegiveis"] = [
        {
            "pagina": 1,
            "camada": "base",
            "bbox": _norm(80, 30, 140, 80),
            "motivo": "borrado",
        }
    ]
    assert erros_leitura(rodada_dir, pdf_id, "c", ficha) == []


def test_validar_c_ilegivel_de_outra_pagina_nao_cobre(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _gravar_conferencia(rodada_dir, pdf_id)
    ficha = _ficha_regional(rodada_dir, pdf_id, "c")
    leitura = ficha["atributos_extras"]["leitura"]
    indice = carregar_indice(rodada_dir, pdf_id)
    leitura["tiles_revisados"] = [str(next(t["id"] for t in indice["tiles"] if t["bbox"][1] > 0.5))]
    # a página 2 não existe: a região ilegível é recusada e, de qualquer forma, não cobre a página 1
    leitura["regioes_ilegiveis"] = [
        {"pagina": 2, "camada": "base", "bbox": _norm(80, 30, 140, 80), "motivo": "borrado"}
    ]
    erros = erros_leitura(rodada_dir, pdf_id, "c", ficha)
    assert erros != []


def test_validar_c_regiao_a_cavalo_em_dois_tiles_revisados_e_aceita(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    # conferência larga o bastante para conter a região que atravessa a emenda dos tiles
    escrever_json_atomico(
        diretorio_ficha(rodada_dir, pdf_id) / "regioes-conferencia.json",
        {
            "schema_version": "curadoria-ficha-regioes-v1",
            "pdf_id": pdf_id,
            "regioes": [{"id": "r001", "pagina": 1, "bbox": [0.0, 0.0, 1.0, 1.0]}],
        },
    )
    indice = carregar_indice(rodada_dir, pdf_id)
    # emenda horizontal entre colunas 0 e 1 (x de 0.37 a 0.43), linha 0
    regiao = [0.35, 0.05, 0.45, 0.10]
    cobrem = _tiles_que_cobrem(indice, regiao)
    assert cobrem == []  # nenhum tile sozinho contém a região
    base = [
        str(t["id"])
        for t in indice["tiles"]
        if t["camada"] == "base" and t["linha"] == 0 and t["coluna"] in (0, 1)
    ]
    ficha = _ficha_regional(rodada_dir, pdf_id, "c")
    ficha["escopo_anotacao"]["regioes"] = [{"pagina": 1, "bbox": regiao}]
    ficha["postes"][0]["bbox"] = [0.39, 0.06, 0.41, 0.08]
    ficha["atributos_extras"]["leitura"]["tiles_revisados"] = base
    assert erros_leitura(rodada_dir, pdf_id, "c", ficha) == []
    # abrindo só um dos dois, a região fica descoberta
    ficha["atributos_extras"]["leitura"]["tiles_revisados"] = base[:1]
    assert any("tiles_revisados" in e for e in erros_leitura(rodada_dir, pdf_id, "c", ficha))


def test_validar_c_regiao_que_atravessa_duas_regioes_de_conferencia_e_recusada(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    regiao = _norm(*REGIAO_C)
    meio = (regiao[0] + regiao[2]) / 2
    escrever_json_atomico(
        diretorio_ficha(rodada_dir, pdf_id) / "regioes-conferencia.json",
        {
            "schema_version": "curadoria-ficha-regioes-v1",
            "pdf_id": pdf_id,
            "regioes": [
                {"id": "r001", "pagina": 1, "bbox": [regiao[0], regiao[1], meio, regiao[3]]},
                {"id": "r002", "pagina": 1, "bbox": [meio, regiao[1], regiao[2], regiao[3]]},
            ],
        },
    )
    erros = erros_leitura(rodada_dir, pdf_id, "c", _ficha_regional(rodada_dir, pdf_id, "c"))
    assert any("conferência" in e for e in erros), erros


def test_validar_c_regiao_de_conferencia_de_outra_pagina_nao_vale(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    escrever_json_atomico(
        diretorio_ficha(rodada_dir, pdf_id) / "regioes-conferencia.json",
        {
            "schema_version": "curadoria-ficha-regioes-v1",
            "pdf_id": pdf_id,
            "regioes": [{"id": "r001", "pagina": 2, "bbox": [0.0, 0.0, 1.0, 1.0]}],
        },
    )
    erros = erros_leitura(rodada_dir, pdf_id, "c", _ficha_regional(rodada_dir, pdf_id, "c"))
    assert any("conferência" in e for e in erros), erros


@pytest.mark.parametrize(
    "conteudo",
    [
        {"schema_version": "outro", "pdf_id": "{pdf}", "regioes": []},
        {"schema_version": "curadoria-ficha-regioes-v1", "pdf_id": "outro-pdf", "regioes": []},
        {"schema_version": "curadoria-ficha-regioes-v1", "pdf_id": "{pdf}", "regioes": "x"},
        [],
    ],
)
def test_validar_c_recusa_regioes_de_conferencia_de_outro_pdf_ou_esquema(
    rodada: tuple[Path, str], conteudo: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    if isinstance(conteudo, dict):
        conteudo = {k: (pdf_id if v == "{pdf}" else v) for k, v in conteudo.items()}
    escrever_json_atomico(
        diretorio_ficha(rodada_dir, pdf_id) / "regioes-conferencia.json", conteudo
    )
    ficha = _ficha_regional(rodada_dir, pdf_id, "c")
    with pytest.raises((RodadaError, ValueError)):
        erros = erros_leitura(rodada_dir, pdf_id, "c", ficha)
        raise ValueError(erros) if erros else AssertionError("aceitou conferência inválida")
    arquivo = _rascunho(rodada_dir, pdf_id, "c", ficha)
    assert main(_argv("validar", rodada_dir, pdf_id, "c", arquivo)) == 1
    erro = capsys.readouterr().err
    assert erro.startswith("erro:")
    assert str(rodada_dir) not in erro


def test_validar_c_recusa_tile_revisado_inexistente_mesmo_com_cobertura(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _gravar_conferencia(rodada_dir, pdf_id)
    ficha = _ficha_regional(rodada_dir, pdf_id, "c")
    ficha["atributos_extras"]["leitura"]["tiles_revisados"].append("p009-base-t0000")
    erros = erros_leitura(rodada_dir, pdf_id, "c", ficha)
    assert any("p009-base-t0000" in e for e in erros), erros


def test_validar_c_aceita_e_congela_leitura_regional(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _gravar_conferencia(rodada_dir, pdf_id)
    ficha = _ficha_regional(rodada_dir, pdf_id, "c")
    item = congelar_leitura(rodada_dir, pdf_id, "c", _rascunho(rodada_dir, pdf_id, "c", ficha))
    assert item["leitor"] == "c"
    assert carregar_congelada(rodada_dir, pdf_id, "c") == ficha


# --- validar não grava e não quebra --------------------------------------------------------


def test_validar_via_cli_nao_cria_arquivos_de_congelamento(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    arquivo = _rascunho(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    antes = sorted(p.name for p in diretorio_ficha(rodada_dir, pdf_id).rglob("*"))
    assert main(_argv("validar", rodada_dir, pdf_id, "a", arquivo)) == 0
    capsys.readouterr()
    depois = sorted(p.name for p in diretorio_ficha(rodada_dir, pdf_id).rglob("*"))
    assert antes == depois
    assert not (diretorio_ficha(rodada_dir, pdf_id) / "leitura-a.json").exists()
    assert not (diretorio_ficha(rodada_dir, pdf_id) / "congelamento.json").exists()


def test_cli_ficha_com_raiz_nao_objeto_e_erro_limpo(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    arquivo = rodada_dir / "lista.json"
    arquivo.write_text("[1, 2]", encoding="utf-8")
    for comando in ("validar", "congelar"):
        assert main(_argv(comando, rodada_dir, pdf_id, "a", arquivo)) == 1
        erro = capsys.readouterr().err
        assert erro.startswith("erro:")
        assert str(rodada_dir) not in erro


def test_cli_leitor_desconhecido_e_rejeitado_pelo_parser(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    arquivo = _rascunho(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    with pytest.raises(SystemExit) as saida:
        main(_argv("validar", rodada_dir, pdf_id, "d", arquivo))
    assert saida.value.code == 2


def test_erros_leitura_leitor_desconhecido_via_api(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    erros = erros_leitura(rodada_dir, pdf_id, "d", _ficha(rodada_dir, pdf_id, "a"))
    assert any("leitor" in e for e in erros)


@pytest.mark.parametrize(
    "mutacao",
    [
        lambda leitura: leitura.update(tiles_revisados="p001-base-t0000"),
        lambda leitura: leitura.update(tiles_revisados=[["p001-base-t0000"]]),
        lambda leitura: leitura.update(tiles_revisados=[None]),
        lambda leitura: leitura.update(regioes_ilegiveis=None),
        lambda leitura: leitura.update(regioes_ilegiveis=["x"]),
        lambda leitura: leitura.update(regioes_ilegiveis=[{"pagina": True, "camada": "base"}]),
        lambda leitura: leitura.update(
            regioes_ilegiveis=[
                {
                    "pagina": 1,
                    "camada": "base",
                    "bbox": [0.1, 0.1, float("nan"), 0.2],
                    "motivo": "x",
                }
            ]
        ),
        lambda leitura: leitura.update(
            regioes_ilegiveis=[
                {"pagina": 1, "camada": "base", "bbox": [True, 0, 1, 1], "motivo": "x"}
            ]
        ),
        lambda leitura: leitura.update(modelo=""),
        lambda leitura: leitura.update(modelo=3),
        lambda leitura: leitura.pop("tiles_revisados"),
        lambda leitura: leitura.pop("regioes_ilegiveis"),
    ],
)
def test_validar_metadados_malformados_viram_erro_sem_excecao(
    rodada: tuple[Path, str], mutacao: Any
) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha(rodada_dir, pdf_id, "a")
    mutacao(ficha["atributos_extras"]["leitura"])
    erros = erros_leitura(rodada_dir, pdf_id, "a", ficha)
    assert erros != []
    assert all(isinstance(e, str) for e in erros)


def test_validar_erros_nao_vazam_caminho_absoluto(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha(rodada_dir, pdf_id, "a", tiles=[])
    ficha["pdf_sha256"] = "0" * 64
    ficha["atributos_extras"]["leitura"]["origem"] = "humana"
    erros = erros_leitura(rodada_dir, pdf_id, "b", ficha)
    assert erros
    for erro in erros:
        assert str(rodada_dir) not in erro
        assert str(rodada_dir.parent) not in erro


# --- congelar ------------------------------------------------------------------------------


def test_congelar_copia_os_bytes_do_rascunho_e_ignora_edicao_posterior(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    rascunho = _rascunho(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    original = rascunho.read_bytes()
    congelar_leitura(rodada_dir, pdf_id, "a", rascunho)
    copia = diretorio_ficha(rodada_dir, pdf_id) / "leitura-a.json"
    assert copia.read_bytes() == original
    rascunho.write_text("{}", encoding="utf-8")
    assert copia.read_bytes() == original
    assert carregar_congelada(rodada_dir, pdf_id, "a")["tipo"] == "referencia"


def test_congelar_recusa_copia_orfa_sem_registro_no_manifesto(rodada: tuple[Path, str]) -> None:
    """Crash entre a cópia e o manifesto: a leitura órfã não pode ser sobrescrita em silêncio."""
    rodada_dir, pdf_id = rodada
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "leitura-b.json").write_text('{"orfa": true}', encoding="utf-8")
    rascunho = _rascunho(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b"))
    with pytest.raises(ValueError, match="já congelada"):
        congelar_leitura(rodada_dir, pdf_id, "b", rascunho)
    assert (pasta / "leitura-b.json").read_text(encoding="utf-8") == '{"orfa": true}'
    assert not (pasta / "congelamento.json").exists()
    with pytest.raises(ValueError, match="não congelada"):
        carregar_congelada(rodada_dir, pdf_id, "b")


def test_congelar_falha_ao_gravar_manifesto_deixa_orfa_fail_closed(
    rodada: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simula o crash entre cópia e manifesto: o estado resultante nunca vira leitura confiável."""
    import scripts.curation_ficha as modulo

    rodada_dir, pdf_id = rodada
    rascunho = _rascunho(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))

    def _quebra(*_: Any, **__: Any) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(modulo, "escrever_json_atomico", _quebra)
    with pytest.raises(OSError, match="disco cheio"):
        congelar_leitura(rodada_dir, pdf_id, "a", rascunho)
    monkeypatch.undo()
    # a cópia existe, mas sem registro: não é carregável como congelada e nova tentativa é recusada
    with pytest.raises(ValueError, match="não congelada"):
        carregar_congelada(rodada_dir, pdf_id, "a")
    with pytest.raises(ValueError, match="já congelada"):
        congelar_leitura(rodada_dir, pdf_id, "a", rascunho)
    # a trava não pode ficar presa depois da falha
    assert not list(diretorio_ficha(rodada_dir, pdf_id).glob("*.lock"))
    outro = _rascunho(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b"))
    assert congelar_leitura(rodada_dir, pdf_id, "b", outro)["leitor"] == "b"


def test_congelar_mensagem_de_consolidada_tem_precedencia_e_nada_e_gravado(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    rascunho_a = _rascunho(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    congelar_leitura(rodada_dir, pdf_id, "a", rascunho_a)
    escrever_json_atomico(diretorio_ficha(rodada_dir, pdf_id) / "referencia.json", {})
    antes = (diretorio_ficha(rodada_dir, pdf_id) / "congelamento.json").read_bytes()
    with pytest.raises(ValueError, match="consolidada"):
        congelar_leitura(rodada_dir, pdf_id, "a", rascunho_a)
    rascunho_c = _rascunho(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b"))
    with pytest.raises(ValueError, match="consolidada"):
        congelar_leitura(rodada_dir, pdf_id, "b", rascunho_c)
    assert (diretorio_ficha(rodada_dir, pdf_id) / "congelamento.json").read_bytes() == antes
    assert not (diretorio_ficha(rodada_dir, pdf_id) / "leitura-b.json").exists()
    # leituras já congeladas continuam legíveis depois da consolidação
    assert carregar_congelada(rodada_dir, pdf_id, "a")["tipo"] == "referencia"


def test_congelar_cli_depois_da_consolidacao_sai_com_erro_sem_caminho(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    escrever_json_atomico(diretorio_ficha(rodada_dir, pdf_id) / "referencia.json", {})
    arquivo = _rascunho(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b"))
    assert main(_argv("congelar", rodada_dir, pdf_id, "b", arquivo)) == 1
    saida = capsys.readouterr()
    assert saida.out == ""
    assert "consolidada" in saida.err
    assert str(rodada_dir) not in saida.err


def test_congelar_invalido_via_cli_nao_grava_nada(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha(rodada_dir, pdf_id, "a", tiles=[])
    arquivo = _rascunho(rodada_dir, pdf_id, "a", ficha)
    assert main(_argv("congelar", rodada_dir, pdf_id, "a", arquivo)) == 1
    assert capsys.readouterr().err.startswith("erro:")
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    assert not (pasta / "leitura-a.json").exists()
    assert not (pasta / "congelamento.json").exists()
    assert not list(pasta.glob("*.lock"))


def test_congelar_leitor_do_rascunho_diferente_do_informado_e_recusado(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    rascunho = _rascunho(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "b"))
    with pytest.raises(ValueError, match="leitor"):
        congelar_leitura(rodada_dir, pdf_id, "a", rascunho)
    assert not (diretorio_ficha(rodada_dir, pdf_id) / "leitura-a.json").exists()


def test_congelar_pdf_fora_da_rodada_e_recusado_sem_criar_diretorios(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    rascunho = _rascunho(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    with pytest.raises((RodadaError, ValueError)):
        congelar_leitura(rodada_dir, "../fora", "a", rascunho)
    assert not (rodada_dir.parent / "fora").exists()
    assert not (rodada_dir / "pdfs" / ".." / "fora").exists()


# --- carregar_congelada --------------------------------------------------------------------


def _congelada(rodada_dir: Path, pdf_id: str, leitor: str = "a") -> Registro:
    ficha = _ficha(rodada_dir, pdf_id, leitor)
    return congelar_leitura(
        rodada_dir, pdf_id, leitor, _rascunho(rodada_dir, pdf_id, leitor, ficha)
    )


def test_carregar_congelada_detecta_troca_de_conteudo_com_mesmo_tamanho(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _congelada(rodada_dir, pdf_id)
    copia = diretorio_ficha(rodada_dir, pdf_id) / "leitura-a.json"
    conteudo = copia.read_bytes()
    copia.write_bytes(conteudo.replace(b"P1", b"P2", 1))
    assert copia.stat().st_size == len(conteudo)
    with pytest.raises(ValueError, match="adulterada"):
        carregar_congelada(rodada_dir, pdf_id, "a")


def test_carregar_congelada_detecta_sha_do_manifesto_alterado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _congelada(rodada_dir, pdf_id)
    manifesto = diretorio_ficha(rodada_dir, pdf_id) / "congelamento.json"
    dados = json.loads(manifesto.read_text(encoding="utf-8"))
    dados["itens"][0]["sha256"] = "f" * 64
    manifesto.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(ValueError, match="adulterada"):
        carregar_congelada(rodada_dir, pdf_id, "a")


def test_carregar_congelada_recusa_copia_removida_ou_registro_removido(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _congelada(rodada_dir, pdf_id)
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    manifesto = pasta / "congelamento.json"
    guardado = manifesto.read_bytes()

    manifesto.unlink()
    with pytest.raises(ValueError, match="não congelada"):
        carregar_congelada(rodada_dir, pdf_id, "a")
    manifesto.write_bytes(guardado)

    (pasta / "leitura-a.json").unlink()
    with pytest.raises(ValueError, match="não congelada"):
        carregar_congelada(rodada_dir, pdf_id, "a")


def test_carregar_congelada_manifesto_com_esquema_desconhecido_e_recusado(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _congelada(rodada_dir, pdf_id)
    manifesto = diretorio_ficha(rodada_dir, pdf_id) / "congelamento.json"
    manifesto.write_text(json.dumps({"schema_version": "x", "itens": []}), encoding="utf-8")
    with pytest.raises((RodadaError, ValueError)):
        carregar_congelada(rodada_dir, pdf_id, "a")
    with pytest.raises((RodadaError, ValueError)):
        congelar_leitura(
            rodada_dir,
            pdf_id,
            "b",
            _rascunho(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b")),
        )
    assert not (diretorio_ficha(rodada_dir, pdf_id) / "leitura-b.json").exists()


def test_carregar_congelada_nao_confunde_leitores(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _congelada(rodada_dir, pdf_id, "a")
    _congelada(rodada_dir, pdf_id, "b")
    a = carregar_congelada(rodada_dir, pdf_id, "a")
    b = carregar_congelada(rodada_dir, pdf_id, "b")
    assert a["atributos_extras"]["leitura"]["leitor"] == "a"
    assert b["atributos_extras"]["leitura"]["leitor"] == "b"
    with pytest.raises(ValueError, match="não congelada"):
        carregar_congelada(rodada_dir, pdf_id, "c")
