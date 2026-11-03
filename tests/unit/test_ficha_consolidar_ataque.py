"""Ataque à consolidação da ficha de referência: bordas, simetria A/B e avaliador."""

# ruff: noqa: F811  (fixtures importadas e usadas como parâmetro)

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.curation_ficha import congelar_leitura, diretorio_ficha, main
from scripts.ficha_leitura_dupla import comparar_leituras, consolidar
from scripts.ficha_poste import validar_ficha
from scripts.ficha_poste_avaliador import avaliar
from tests.unit.test_curation_ficha import _ficha, _rascunho, modelo, rodada  # noqa: F401
from tests.unit.test_ficha_leitura_dupla import (
    _cabos,
    _consolidar,
    _contagem,
    _ilegivel,
    _leitura_c,
    _poste,
    _postes,
    _sem_p3,
    _simbolo,
    _vao,
    _vaos_p1_p2,
    ficha,
)

Registro = dict[str, Any]


def _como_predicao(leitura: Registro) -> Registro:
    predicao = copy.deepcopy(leitura)
    predicao["tipo"] = "predicao"
    predicao["gerador"] = {"leitor": "teste"}
    return predicao


# --- simetria A/B --------------------------------------------------------------------------------


def test_poste_so_em_b_sem_c_exclui_a_zona_e_nao_gera_fp() -> None:
    a, b = _sem_p3(), ficha()
    referencia = consolidar(a, b, None, comparar_leituras(a, b), paginas=1)
    assert validar_ficha(referencia) == []
    assert set(_postes(referencia)) == {"P1", "P2"}
    [zona] = _contagem(referencia)["excluidas"]
    assert zona["motivo"] == "poste_disputado"
    assert referencia["escopo_anotacao"]["tipo"] == "regional"
    relatorio = avaliar(referencia, _como_predicao(b))
    assert (relatorio["postes"]["fp"], relatorio["vaos"]["fp"]) == (0, 0)


def test_poste_so_em_b_negado_por_c_e_descartado() -> None:
    a, b = _sem_p3(), ficha()
    referencia = _consolidar(a, b, _leitura_c(b["postes"][1]))
    assert set(_postes(referencia)) == {"P1", "P2"}
    assert referencia["vaos"] == a["vaos"]
    assert _contagem(referencia)["descartadas_por_maioria"] == 1
    assert referencia["escopo_anotacao"] == {"tipo": "completo"}


def test_vao_so_em_b_sem_c_exclui_os_extremos_e_so_em_b_com_c_entra() -> None:
    a, b = ficha(), ficha()
    a["vaos"] = a["vaos"][:1]
    referencia = _consolidar(a, b)
    assert [z["motivo"] for z in _contagem(referencia)["excluidas"]] == ["vao_disputado"] * 2
    assert set(_postes(referencia)) == {"P1"}

    c = _leitura_c(a["postes"][1], a["postes"][2], vaos=[_vao("P2", "P3", 35.0, "BT 70")])
    referencia = _consolidar(a, b, c)
    assert referencia["vaos"] == b["vaos"]
    assert _contagem(referencia)["excluidas"] == []


# --- campos e vãos -------------------------------------------------------------------------------


def test_c_cobre_mas_sem_poste_casado_deixa_pendente_sem_contar_nao_coberta() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["estruturas"] = ["N3"]
    c = _leitura_c(a["postes"][1])  # cobre a página toda, mas só tem o P2
    referencia = _consolidar(a, b, c)
    assert _postes(referencia)["P1"]["pendentes"] == ["estruturas"]
    assert _contagem(referencia) == {
        "resolvidas_por_c": 0,
        "pendentes": 1,
        "descartadas_por_maioria": 0,
        "nao_cobertas_por_c": 0,
        "excluidas": [],
    }


def test_atributo_de_vao_pendente_em_um_leitor_e_resolvido_por_c() -> None:
    a, b = ficha(), ficha()
    b["vaos"][0]["comprimento_m"] = None
    b["vaos"][0]["pendentes"] = ["comprimento_m"]
    c = _leitura_c(a["postes"][0], a["postes"][1], vaos=[_vao("P1", "P2", 40.0, "3x1/0")])
    referencia = _consolidar(a, b, c)
    assert _cabos(referencia)["3x1/0"] == 40.0
    assert _contagem(referencia)["resolvidas_por_c"] == 1

    sem_c = _consolidar(a, b)
    vao = next(v for v in sem_c["vaos"] if v["cabo"] == "3x1/0")
    assert (vao["comprimento_m"], vao["pendentes"]) == (None, ["comprimento_m"])
    assert _contagem(sem_c)["nao_cobertas_por_c"] == 1


def test_atributo_de_vao_divergente_fora_de_c_conta_nao_coberta() -> None:
    a, b = ficha(), ficha()
    b["vaos"][1]["comprimento_m"] = 50.0
    c = _leitura_c(regioes=[{"pagina": 1, "bbox": [0.0, 0.0, 0.2, 0.2]}])
    referencia = _consolidar(a, b, c)
    assert _contagem(referencia) == {
        "resolvidas_por_c": 0,
        "pendentes": 1,
        "descartadas_por_maioria": 0,
        "nao_cobertas_por_c": 1,
        "excluidas": [],
    }


def test_vao_so_em_um_leitor_com_so_um_extremo_coberto_vira_zona() -> None:
    a, b = ficha(), ficha()
    b["vaos"] = b["vaos"][:1]
    # a região de C cobre o P2 (x=0.40) mas não o P3 (x=0.70)
    c = _leitura_c(a["postes"][1], regioes=[{"pagina": 1, "bbox": [0.30, 0.0, 0.55, 1.0]}])
    referencia = _consolidar(a, b, c)
    motivos = [z["motivo"] for z in _contagem(referencia)["excluidas"]]
    assert motivos == ["vao_disputado", "vao_disputado"]
    assert _contagem(referencia)["descartadas_por_maioria"] == 0


def test_vao_so_em_um_leitor_com_extremo_ilegivel_em_c_vira_zona() -> None:
    a, b = ficha(), ficha()
    b["vaos"] = b["vaos"][:1]
    c = _leitura_c(
        a["postes"][1],
        a["postes"][2],
        ilegiveis=[_ilegivel([0.68, 0.28, 0.74, 0.34])],
    )
    referencia = _consolidar(a, b, c)
    assert [z["motivo"] for z in _contagem(referencia)["excluidas"]] == ["vao_disputado"] * 2
    assert _contagem(referencia)["descartadas_por_maioria"] == 0


def test_duas_sobras_no_mesmo_par_sem_c_geram_so_duas_zonas() -> None:
    a = ficha()
    a["vaos"] = _vaos_p1_p2(("3x1/0", 40.0), ("BT 70", 30.0), ("BT 35", 20.0))
    b = ficha()
    b["vaos"] = _vaos_p1_p2(("3x1/0", 40.0))
    referencia = _consolidar(a, b)
    assert len(_contagem(referencia)["excluidas"]) == 2


def test_poste_so_em_a_com_regiao_ilegivel_em_c_nao_e_descartado() -> None:
    a, b = ficha(), _sem_p3()
    c = _leitura_c(a["postes"][1], ilegiveis=[_ilegivel([0.68, 0.28, 0.74, 0.34])])
    referencia = _consolidar(a, b, c)
    assert _contagem(referencia)["descartadas_por_maioria"] == 0
    assert [z["motivo"] for z in _contagem(referencia)["excluidas"]] == ["poste_disputado"]


def test_c_completo_cobre_tudo_e_descarta() -> None:
    a, b = ficha(), _sem_p3()
    c = _leitura_c(a["postes"][1])
    c["escopo_anotacao"] = {"tipo": "completo"}
    referencia = _consolidar(a, b, c)
    assert _contagem(referencia)["descartadas_por_maioria"] == 1


# --- escopo e zonas ------------------------------------------------------------------------------


def test_zona_ilegivel_que_cobre_a_pagina_toda_ainda_gera_referencia_valida() -> None:
    a, b = ficha(), ficha()
    a["atributos_extras"]["leitura"]["regioes_ilegiveis"] = [_ilegivel([0.0, 0.0, 1.0, 1.0])]
    referencia = consolidar(a, b, None, comparar_leituras(a, b), paginas=1)
    assert validar_ficha(referencia) == []
    assert referencia["postes"] == []


def test_zona_exclui_vizinho_confirmado_e_seus_vaos() -> None:
    a, b = ficha(), ficha()
    a["atributos_extras"]["leitura"]["regioes_ilegiveis"] = [_ilegivel([0.39, 0.29, 0.43, 0.33])]
    referencia = _consolidar(a, b)
    assert set(_postes(referencia)) == {"P1", "P3"}
    assert referencia["vaos"] == []


@pytest.mark.parametrize("paginas", [0, -1, True, 1.5])
def test_paginas_invalido_e_recusado(paginas: Any) -> None:
    a, b = ficha(), ficha()
    with pytest.raises(ValueError, match="paginas"):
        consolidar(a, b, None, comparar_leituras(a, b), paginas=paginas)


def test_zona_em_pagina_depois_do_fim_nao_quebra_o_escopo() -> None:
    a, b = ficha(), ficha()
    a["atributos_extras"]["leitura"]["regioes_ilegiveis"] = [
        _ilegivel([0.1, 0.1, 0.2, 0.2], pagina=3)
    ]
    referencia = consolidar(a, b, None, comparar_leituras(a, b), paginas=2)
    assert validar_ficha(referencia) == []
    assert {r["pagina"] for r in referencia["escopo_anotacao"]["regioes"]} == {1, 2}


# --- interação com o avaliador -------------------------------------------------------------------


def test_campo_pendente_na_referencia_nao_penaliza_a_predicao() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["estruturas"] = ["N3"]
    referencia = _consolidar(a, b)
    for estruturas in (["N1"], ["N3"], ["U3"]):
        predicao = _como_predicao(a)
        predicao["postes"][0]["estruturas"] = estruturas
        relatorio = avaliar(referencia, predicao)
        assert relatorio["postes"]["fp"] == 0 and relatorio["postes"]["fn"] == 0


def test_vao_na_zona_excluida_nao_gera_fp_de_vao() -> None:
    a, b = ficha(), ficha()
    b["vaos"] = b["vaos"][:1]
    referencia = _consolidar(a, b)
    relatorio = avaliar(referencia, _como_predicao(a))
    assert (relatorio["postes"]["fp"], relatorio["vaos"]["fp"]) == (0, 0)


# --- ids -----------------------------------------------------------------------------------------


def test_simbolo_b_nao_colide_com_id_de_simbolo_de_a_em_outro_poste() -> None:
    a, b = ficha(), ficha()
    a["postes"][2]["simbolos"] = [_simbolo("b-S1", [0.73, 0.30, 0.75, 0.32])]
    b["postes"][2]["simbolos"] = [_simbolo("b-S1", [0.73, 0.30, 0.75, 0.32])]
    b["postes"][0]["simbolos"] = [_simbolo("S1", [0.50, 0.50, 0.52, 0.52])]
    a["postes"][0]["simbolos"] = []
    referencia = _consolidar(a, b, _leitura_c(b["postes"][0], a["postes"][2]))
    ids = [s["id"] for p in referencia["postes"] for s in p["simbolos"]]
    assert len(ids) == len(set(ids)) == 2


def test_dois_postes_so_de_b_nao_colidem_entre_si_nem_com_a() -> None:
    a = ficha()
    a["postes"].append(_poste("b-P8", 0.10, y=0.80))
    b = ficha()
    b["postes"].extend([_poste("P8", 0.70, y=0.80), _poste("P9", 0.40, y=0.80)])
    c = _leitura_c(a["postes"][3], *b["postes"][3:])
    referencia = _consolidar(a, b, c)
    ids = [p["id"] for p in referencia["postes"]]
    assert len(ids) == len(set(ids)) == 6


# --- CLI -----------------------------------------------------------------------------------------


def _congelar(rodada_dir: Path, pdf_id: str, leitor: str, ficha_: Registro) -> None:
    congelar_leitura(rodada_dir, pdf_id, leitor, _rascunho(rodada_dir, pdf_id, leitor, ficha_))


def _argv(rodada_dir: Path, pdf_id: str, *extras: str) -> list[str]:
    return ["consolidar", "--rodada", str(rodada_dir), "--pdf", pdf_id, *extras]


def test_cli_consolidar_sem_leitura_b_congelada_falha_sem_gravar(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _congelar(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    (pasta / "comparacao.json").write_text(json.dumps({"divergencias": []}), encoding="utf-8")
    assert main(_argv(rodada_dir, pdf_id)) == 1
    assert "leitura b" in capsys.readouterr().err
    assert not (pasta / "referencia.json").exists()


def test_cli_leitura_c_orfa_sem_item_no_manifesto_e_ignorada_so_com_sem_terceiro(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _congelar(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    divergente = _ficha(rodada_dir, pdf_id, "b")
    divergente["postes"][0]["estruturas"] = ["N3"]
    _congelar(rodada_dir, pdf_id, "b", divergente)
    assert main(["comparar", "--rodada", str(rodada_dir), "--pdf", pdf_id]) == 0
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    orfa = _ficha(rodada_dir, pdf_id, "c")
    orfa["postes"][0]["estruturas"] = ["N3"]
    (pasta / "leitura-c.json").write_text(json.dumps(orfa), encoding="utf-8")
    capsys.readouterr()

    assert main(_argv(rodada_dir, pdf_id)) == 1  # não usa a C órfã em silêncio
    assert "--sem-terceiro" in capsys.readouterr().err
    assert not (pasta / "referencia.json").exists()

    assert main(_argv(rodada_dir, pdf_id, "--sem-terceiro", "--motivo", "c órfã")) == 0
    referencia = json.loads((pasta / "referencia.json").read_text(encoding="utf-8"))
    assert referencia["postes"][0]["pendentes"] == ["estruturas"]  # C órfã não resolveu nada


def test_cli_referencia_sem_item_no_manifesto_nao_e_refeita(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _congelar(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    _congelar(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b"))
    assert main(["comparar", "--rodada", str(rodada_dir), "--pdf", pdf_id]) == 0
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    (pasta / "referencia.json").write_text("{}", encoding="utf-8")
    manifesto_antes = (pasta / "congelamento.json").read_bytes()
    capsys.readouterr()
    assert main(_argv(rodada_dir, pdf_id)) == 1
    assert "já" in capsys.readouterr().err
    assert (pasta / "referencia.json").read_text(encoding="utf-8") == "{}"
    assert (pasta / "congelamento.json").read_bytes() == manifesto_antes
