"""Ataques à comparação de leitura dupla: bordas, empates, fusão transitiva e colisão de ids."""

from __future__ import annotations

import copy
import random
from typing import Any

import pytest
import scripts.ficha_poste_avaliador as avaliador
from scripts.ficha_leitura_dupla import (
    MARGEM_CONFERENCIA,
    comparar_leituras,
    regioes_de_conferencia,
)
from tests.unit.test_ficha_leitura_dupla import (
    _contem,
    _poste,
    _simbolo,
    _tipos,
    _vao,
    ficha,
)

Registro = dict[str, Any]


def _regiao_de(bbox: list[float], pagina: int = 1) -> Registro:
    return {"pagina": pagina, "bbox": bbox}


def test_aliases_privados_do_avaliador_apontam_para_as_funcoes_publicas() -> None:
    assert avaliador._numeros_iguais is avaliador.numeros_iguais
    assert avaliador._campo_acerta is avaliador.campo_acerta
    assert avaliador._casar_vaos_do_par is avaliador.casar_vaos_do_par
    assert avaliador._casar_simbolos is avaliador.casar_simbolos


def test_comprimento_na_fronteira_da_tolerancia_igual_e_logo_acima_diverge() -> None:
    b = ficha()
    b["vaos"][1]["comprimento_m"] = 35.1  # |35,0 - 35,1| == 0,1 exato: dentro
    assert comparar_leituras(ficha(), b)["divergencias"] == []
    b["vaos"][1]["comprimento_m"] = 34.9
    assert comparar_leituras(ficha(), b)["divergencias"] == []
    b["vaos"][1]["comprimento_m"] = 35.11
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["campo"]) == ("vao_atributo", "comprimento_m")


def test_vao_com_extremos_invertidos_em_b_nao_diverge() -> None:
    b = ficha()
    b["vaos"][0]["de"], b["vaos"][0]["para"] = "P2", "P1"
    assert comparar_leituras(ficha(), b)["divergencias"] == []


def test_vao_atributo_pendente_em_so_um_leitor_diverge_e_nos_dois_nao() -> None:
    b = ficha()
    b["vaos"][1]["pendentes"] = ["cabo"]
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["campo"], d["cabo_a"]) == ("vao_atributo", "cabo", "BT 70")

    a = ficha()
    a["vaos"][1]["pendentes"] = ["cabo"]
    a["vaos"][1]["cabo"] = None
    b["vaos"][1]["cabo"] = None
    assert comparar_leituras(a, b)["divergencias"] == []


def test_simbolos_pendentes_em_so_um_leitor_diverge_e_nos_dois_nao() -> None:
    b = ficha()
    b["postes"][0]["pendentes"] = ["simbolos"]
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["a"], d["b"]) == ("simbolos", "P1", "P1")

    a = ficha()
    a["postes"][0]["pendentes"] = ["simbolos"]
    a["postes"][0]["simbolos"] = [_simbolo("S7", [0.5, 0.5, 0.6, 0.6], classe="ATERRAMENTO")]
    assert comparar_leituras(a, b)["divergencias"] == []


def test_coordenada_alem_da_tolerancia_gera_divergencia_de_campo() -> None:
    b = ficha()
    b["postes"][2]["coordenada"]["leste"] = 700000.011
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["campo"], d["a"]) == ("campo", "coordenada", "P3")
    b["postes"][2]["coordenada"]["leste"] = 700000.01
    assert comparar_leituras(ficha(), b)["divergencias"] == []


def test_dois_campos_divergentes_no_mesmo_poste_geram_duas_divergencias() -> None:
    b = ficha()
    b["postes"][1]["estruturas"] = ["N3"]
    b["postes"][1]["poste"] = "DT 12/600"
    campos = sorted(d["campo"] for d in comparar_leituras(ficha(), b)["divergencias"])
    assert campos == ["estruturas", "poste"]


def test_so_geometria_soma_o_minimo_por_classe_e_ignora_classes_sem_par() -> None:
    a, b = ficha(), ficha()
    a["postes"][0]["simbolos"] = [
        _simbolo("S11", [0.13, 0.30, 0.14, 0.31]),
        _simbolo("S12", [0.15, 0.30, 0.16, 0.31]),
        _simbolo("S13", [0.17, 0.30, 0.18, 0.31], classe="ATERRAMENTO"),
    ]
    b["postes"][0]["simbolos"] = [
        _simbolo("T1", [0.13, 0.35, 0.14, 0.36]),
        _simbolo("T2", [0.17, 0.35, 0.18, 0.36], classe="CONECTOR"),
    ]
    comp = comparar_leituras(a, b)
    assert _tipos(comp) == ["simbolos"]
    assert (
        comp["simbolos_so_geometria"] == 1
    )  # só ESTAI (min(2, 1)); ATERRAMENTO e CONECTOR sem par
    assert comp["iou_simbolos"] == []


def test_simbolos_casados_com_iou_parcial_registram_iou_ordenado() -> None:
    a, b = ficha(), ficha()
    a["postes"][1]["simbolos"] = [_simbolo("S2", [0.40, 0.30, 0.42, 0.32])]
    b["postes"][1]["simbolos"] = [_simbolo("S2", [0.405, 0.30, 0.425, 0.32])]
    comp = comparar_leituras(a, b)
    assert comp["iou_simbolos"] == sorted(comp["iou_simbolos"])
    assert len(comp["iou_simbolos"]) == 2
    assert all(0.0 < v <= 1.0 for v in comp["iou_simbolos"])


def test_bbox_de_simbolos_inclui_simbolo_que_so_b_tem_e_recorta_a_um() -> None:
    a, b = ficha(), ficha()
    a["postes"][2]["bbox"] = [0.96, 0.30, 0.98, 0.32]
    b["postes"][2]["bbox"] = [0.96, 0.30, 0.98, 0.32]
    b["postes"][2]["simbolos"] = [_simbolo("S9", [0.97, 0.31, 0.995, 0.33])]
    [d] = comparar_leituras(a, b)["divergencias"]
    assert d["tipo"] == "simbolos"
    assert d["bbox"][2] == 1.0
    assert d["bbox"][0] == pytest.approx(0.96 - MARGEM_CONFERENCIA)
    assert _contem(d["bbox"], [0.97, 0.31, 0.995, 0.33])


def test_bbox_do_campo_usa_a_envolvente_dos_dois_postes() -> None:
    a, b = ficha(), ficha()
    b["postes"][1]["bbox"] = [0.42, 0.33, 0.44, 0.35]
    b["postes"][1]["estruturas"] = ["N3"]
    [d] = comparar_leituras(a, b)["divergencias"]
    assert _contem(d["bbox"], [0.40, 0.30, 0.44, 0.35])


def test_poste_so_b_em_outra_pagina_e_vao_entre_dois_postes_so_de_b() -> None:
    b = ficha()
    p8 = _poste("P8", 0.20, y=0.60)
    p9 = _poste("P9", 0.50, y=0.60)
    p8["pagina"] = p9["pagina"] = 2
    b["postes"] += [p8, p9]
    b["vaos"].append(_vao("P8", "P9", 20.0, "BT 70"))
    divergencias = comparar_leituras(ficha(), b)["divergencias"]
    assert _tipos({"divergencias": divergencias}) == ["poste_so_b", "poste_so_b", "vao_so_b"]
    vao = next(d for d in divergencias if d["tipo"] == "vao_so_b")
    assert (vao["pagina"], vao["de"], vao["para"]) == (2, "b-P8", "b-P9")
    assert all(d["pagina"] == 2 for d in divergencias)


def test_permutar_com_vaos_empatados_no_mesmo_par_e_simbolos_iguais() -> None:
    a = ficha()
    a["vaos"] = [
        _vao("P1", "P2", 40.0, "BT 70"),
        _vao("P1", "P2", 40.0, "BT 70"),
        _vao("P1", "P2", 41.0, "BT 70"),
        _vao("P1", "P2", None, None),
    ]
    b = copy.deepcopy(a)
    b["vaos"] = [
        _vao("P1", "P2", 40.0, "BT 70"),
        _vao("P1", "P2", 55.0, "BT 70"),
        _vao("P2", "P1", None, None),
    ]
    a["postes"][1]["simbolos"] = [_simbolo(f"S2{i}", [0.40, 0.30, 0.42, 0.32]) for i in range(3)]
    b["postes"][1]["simbolos"] = [_simbolo(f"T2{i}", [0.40, 0.30, 0.42, 0.32]) for i in range(2)]
    esperado = comparar_leituras(a, b)
    assert esperado["divergencias"]
    for semente in range(20):
        sorteio = random.Random(semente)
        pa, pb = copy.deepcopy(a), copy.deepcopy(b)
        for leitura in (pa, pb):
            sorteio.shuffle(leitura["vaos"])
            sorteio.shuffle(leitura["postes"])
            for poste in leitura["postes"]:
                sorteio.shuffle(poste["simbolos"])
        assert comparar_leituras(pa, pb) == esperado


def test_ids_de_a_que_comecam_com_b_nao_colidem_com_postes_so_de_b() -> None:
    # A tem um poste "b-P9"; B tem um poste P9 sem par: o id de B vira "b-P9" na regra de ids.
    a = ficha()
    a["postes"].append(_poste("b-P9", 0.10, y=0.80))
    b = ficha()
    b["postes"].append(_poste("P9", 0.80, y=0.10))
    b["vaos"].append(_vao("P3", "P9", 30.0, "BT 70"))
    comp = comparar_leituras(a, b)
    assert _tipos(comp) == ["poste_so_a", "poste_so_b", "vao_so_b"]
    so_a = next(d for d in comp["divergencias"] if d["tipo"] == "poste_so_a")
    so_b = next(d for d in comp["divergencias"] if d["tipo"] == "poste_so_b")
    assert so_a["bbox"] != so_b["bbox"]
    assert so_a["bbox"][0] == pytest.approx(0.10 - MARGEM_CONFERENCIA)
    assert so_b["bbox"][0] == pytest.approx(0.80 - MARGEM_CONFERENCIA)
    [vao] = [d for d in comp["divergencias"] if d["tipo"] == "vao_so_b"]
    assert _contem(vao["bbox"], [0.70, 0.30, 0.82, 0.32])  # P3 e o P9 de B, não o b-P9 de A


# --- regiões de conferência ----------------------------------------------------------------------


def _comp(*regioes: Registro) -> Registro:
    return {"divergencias": [{"tipo": "campo", **r} for r in regioes]}


def test_cadeia_a_b_c_so_se_junta_pela_fusao_transitiva_em_qualquer_ordem() -> None:
    caixas = [[0.0, 0.1, 0.2, 0.3], [0.15, 0.1, 0.45, 0.3], [0.4, 0.1, 0.6, 0.3]]
    for ordem in ([0, 1, 2], [2, 0, 1], [2, 1, 0], [0, 2, 1]):
        comp = _comp(*(_regiao_de(caixas[i]) for i in ordem))
        [regiao] = regioes_de_conferencia(comp)
        assert regiao["bbox"] == [0.0, 0.1, 0.6, 0.3]


def test_fusao_que_cresce_alcanca_caixa_antes_disjunta() -> None:
    # C só toca a envolvente de A+B, não A nem B isoladamente.
    a = [0.0, 0.0, 0.2, 0.1]
    b = [0.0, 0.05, 0.1, 0.4]
    c = [0.15, 0.3, 0.3, 0.45]
    comp = _comp(_regiao_de(a), _regiao_de(b), _regiao_de(c))
    [regiao] = regioes_de_conferencia(comp)
    assert regiao["bbox"] == [0.0, 0.0, 0.3, 0.45]


def test_regioes_disjuntas_continuam_separadas_e_ordenadas_por_pagina() -> None:
    comp = _comp(
        _regiao_de([0.5, 0.5, 0.6, 0.6], pagina=2),
        _regiao_de([0.1, 0.1, 0.2, 0.2], pagina=2),
        _regiao_de([0.1, 0.1, 0.2, 0.2], pagina=1),
    )
    regioes = regioes_de_conferencia(comp)
    assert [(r["id"], r["pagina"]) for r in regioes] == [("r001", 1), ("r002", 2), ("r003", 2)]
    assert all(set(r) == {"id", "pagina", "bbox"} for r in regioes)


def test_caixas_sobrepostas_em_paginas_diferentes_nao_se_fundem() -> None:
    comp = _comp(_regiao_de([0.1, 0.1, 0.4, 0.4], 1), _regiao_de([0.2, 0.2, 0.5, 0.5], 2))
    regioes = regioes_de_conferencia(comp)
    assert [r["bbox"] for r in regioes] == [[0.1, 0.1, 0.4, 0.4], [0.2, 0.2, 0.5, 0.5]]


def test_regioes_nao_dependem_da_ordem_das_divergencias_nem_alteram_a_entrada() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["estruturas"] = ["N3"]
    b["postes"][2]["poste"] = "DT 12/600"
    b["vaos"][0]["cabo"] = "4x4/0"
    comp = comparar_leituras(a, b)
    copia = copy.deepcopy(comp)
    esperado = regioes_de_conferencia(comp)
    assert comp == copia
    invertida = {**comp, "divergencias": list(reversed(comp["divergencias"]))}
    assert regioes_de_conferencia(invertida) == esperado


def test_regiao_nao_vaza_valores_nem_ids_de_poste() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["estruturas"] = ["N3"]
    texto = repr(regioes_de_conferencia(comparar_leituras(a, b)))
    for proibido in ("N3", "estruturas", "P1", "campo", "tipo"):
        assert proibido not in texto


def _com_colisoes_em_cadeia() -> tuple[Registro, Registro]:
    a = ficha()
    a["postes"] += [_poste("b-P9", 0.10, y=0.80), _poste("b-b-P9", 0.40, y=0.80)]
    b = ficha()
    b["postes"] += [_poste("P9", 0.80, y=0.10), _poste("P8", 0.80, y=0.50)]
    b["vaos"] += [_vao("P3", "P9", 30.0, "BT 70"), _vao("P9", "P8", 25.0, "BT 70")]
    return a, b


def test_colisao_em_cadeia_repete_o_prefixo_o_minimo_e_igual_para_todos_so_b() -> None:
    a, b = _com_colisoes_em_cadeia()
    comp = comparar_leituras(a, b)
    assert _tipos(comp) == [
        "poste_so_a",
        "poste_so_a",
        "poste_so_b",
        "poste_so_b",
        "vao_so_b",
        "vao_so_b",
    ]
    vaos = sorted((d["de"], d["para"]) for d in comp["divergencias"] if d["tipo"] == "vao_so_b")
    assert vaos == [("P3", "b-b-b-P9"), ("b-b-b-P9", "b-b-b-P8")]
    por_a = {d["a"]: d["bbox"] for d in comp["divergencias"] if d["tipo"] == "poste_so_a"}
    assert por_a["b-P9"][0] == pytest.approx(0.10 - MARGEM_CONFERENCIA)
    assert por_a["b-b-P9"][0] == pytest.approx(0.40 - MARGEM_CONFERENCIA)
    vao_p3 = next(
        d for d in comp["divergencias"] if (d.get("de"), d.get("para")) == ("P3", "b-b-b-P9")
    )
    assert _contem(vao_p3["bbox"], [0.70, 0.30, 0.82, 0.32])


def test_colisao_so_de_um_dos_postes_so_b_muda_o_prefixo_de_todos() -> None:
    a = ficha()
    a["postes"].append(_poste("b-P9", 0.10, y=0.80))
    b = ficha()
    b["postes"] += [_poste("P9", 0.80, y=0.10), _poste("P8", 0.80, y=0.50)]
    b["vaos"].append(_vao("P9", "P8", 25.0, "BT 70"))
    comp = comparar_leituras(a, b)
    [vao] = [d for d in comp["divergencias"] if d["tipo"] == "vao_so_b"]
    assert (vao["de"], vao["para"]) == ("b-b-P9", "b-b-P8")


def test_sem_colisao_o_prefixo_continua_b_hifen() -> None:
    a = ficha()
    a["postes"].append(_poste("b-P1", 0.10, y=0.80))  # não colide: B não tem P1 só dele
    b = ficha()
    b["postes"].append(_poste("P9", 0.80, y=0.10))
    b["vaos"].append(_vao("P3", "P9", 30.0, "BT 70"))
    [vao] = [d for d in comparar_leituras(a, b)["divergencias"] if d["tipo"] == "vao_so_b"]
    assert (vao["de"], vao["para"]) == ("P3", "b-P9")


def test_colisoes_em_cadeia_sao_deterministicas_sob_permutacao() -> None:
    a, b = _com_colisoes_em_cadeia()
    esperado = comparar_leituras(a, b)
    for semente in range(15):
        sorteio = random.Random(semente)
        pa, pb = copy.deepcopy(a), copy.deepcopy(b)
        for leitura in (pa, pb):
            sorteio.shuffle(leitura["postes"])
            sorteio.shuffle(leitura["vaos"])
        assert comparar_leituras(pa, pb) == esperado


def test_espelhar_com_ids_b_hifen_troca_so_a_e_so_b_e_mantem_bboxes() -> None:
    a, b = _com_colisoes_em_cadeia()
    ab = comparar_leituras(a, b)["divergencias"]
    ba = comparar_leituras(b, a)["divergencias"]
    troca = {
        "poste_so_a": "poste_so_b",
        "poste_so_b": "poste_so_a",
        "vao_so_a": "vao_so_b",
        "vao_so_b": "vao_so_a",
    }

    def chave(d: Registro, espelhar: bool) -> tuple[Any, ...]:
        tipo = troca.get(d["tipo"], d["tipo"]) if espelhar else d["tipo"]
        return (tipo, d["pagina"], tuple(d["bbox"]), d["campo"])

    assert sorted(chave(d, False) for d in ab) == sorted(chave(d, True) for d in ba)
    so_a_ba = {d["a"] for d in ba if d["tipo"] == "poste_so_a"}
    so_b_ba = {d["b"] for d in ba if d["tipo"] == "poste_so_b"}
    assert so_a_ba == {"P9", "P8"}
    assert so_b_ba == {"b-P9", "b-b-P9"}


# --- indice dos vãos: discrimina vãos do mesmo par e cabo ----------------------------------------


def _do_par(leitura: Registro) -> list[Registro]:
    return [v for v in leitura["vaos"] if {v["de"], v["para"]} == {"P1", "P2"}]


def _ficha_com_vaos(vaos: list[Registro]) -> Registro:
    leitura = ficha()
    leitura["vaos"] = vaos
    return leitura


def test_indice_aponta_o_vao_certo_de_a_quando_dois_vaos_do_mesmo_cabo_divergem() -> None:
    a = _ficha_com_vaos([_vao("P1", "P2", 38.0, "BT 70"), _vao("P1", "P2", 50.0, "BT 70")])
    b = _ficha_com_vaos([_vao("P1", "P2", 30.0, "BT 70"), _vao("P1", "P2", 60.0, "BT 70")])
    divergencias = comparar_leituras(a, b)["divergencias"]
    assert len(divergencias) == 2
    assert all(d["campo"] == "comprimento_m" for d in divergencias)
    assert sorted(d["indice"] for d in divergencias) == [0, 1]
    casados = avaliador.casar_vaos_do_par(_do_par(a), _do_par(b))
    for d in divergencias:
        va, vb = casados[d["indice"]]
        assert not avaliador.numeros_iguais(va["comprimento_m"], vb["comprimento_m"], 0.1)
        assert (va["de"], va["para"], va["cabo"]) == (d["de"], d["para"], d["cabo_a"])


def test_indice_distingue_o_vao_divergente_do_que_casa_igual_no_mesmo_par_e_cabo() -> None:
    a = _ficha_com_vaos([_vao("P1", "P2", 38.0, "BT 70"), _vao("P1", "P2", 50.0, "BT 70")])
    b = _ficha_com_vaos([_vao("P1", "P2", 38.0, "BT 70"), _vao("P1", "P2", 60.0, "BT 70")])
    [d] = comparar_leituras(a, b)["divergencias"]  # o vão casado igual não aparece
    assert (d["tipo"], d["campo"]) == ("vao_atributo", "comprimento_m")
    va, vb = avaliador.casar_vaos_do_par(_do_par(a), _do_par(b))[d["indice"]]
    assert (va["comprimento_m"], vb["comprimento_m"]) == (50.0, 60.0)


def test_vao_so_a_tem_indice_igual_ao_numero_de_casados_do_par() -> None:
    a = _ficha_com_vaos([_vao("P1", "P2", 40.0, "3x1/0"), _vao("P1", "P2", 30.0, "BT 70")])
    b = _ficha_com_vaos([_vao("P1", "P2", 40.0, "3x1/0")])
    [d] = comparar_leituras(a, b)["divergencias"]  # o vão casado e igual não diverge
    casados = avaliador.casar_vaos_do_par(_do_par(a), _do_par(b))
    assert len(casados) == 1
    assert (d["tipo"], d["cabo_a"], d["cabo_b"]) == ("vao_so_a", "BT 70", None)
    assert d["indice"] == len(casados)


def test_vao_so_b_tem_indice_igual_ao_numero_de_casados_do_par() -> None:
    a = _ficha_com_vaos([_vao("P1", "P2", 40.0, "3x1/0")])
    b = _ficha_com_vaos([_vao("P1", "P2", 40.0, "3x1/0"), _vao("P1", "P2", 30.0, "BT 70")])
    [d] = comparar_leituras(a, b)["divergencias"]
    assert (d["tipo"], d["cabo_a"], d["cabo_b"]) == ("vao_so_b", None, "BT 70")
    assert d["indice"] == 1


def test_indice_e_estavel_sob_permutacao_dos_vaos() -> None:
    a = _ficha_com_vaos([_vao("P1", "P2", 38.0, "BT 70"), _vao("P1", "P2", 50.0, "BT 70")])
    b = _ficha_com_vaos([_vao("P1", "P2", 38.0, "BT 70"), _vao("P1", "P2", 60.0, "BT 70")])
    esperado = comparar_leituras(a, b)["divergencias"]
    a["vaos"].reverse()
    b["vaos"].reverse()
    assert comparar_leituras(a, b)["divergencias"] == esperado
