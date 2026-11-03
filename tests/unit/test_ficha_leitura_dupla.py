"""Leitura dupla cega de fichas: comparação de A e B e regiões de conferência (sintéticas)."""

from __future__ import annotations

import copy
import random
from collections import Counter
from typing import Any

import pytest
from scripts.ficha_leitura_dupla import (
    MARGEM_CONFERENCIA,
    MARGEM_CONFERENCIA_CAMPO,
    comparar_leituras,
    consolidar,
    prefixo_so_b,
    regioes_de_conferencia,
    vaos_do_par_em_ordem,
)
from scripts.ficha_poste import validar_ficha
from scripts.ficha_poste_avaliador import avaliar, casar_vaos_do_par

SHA = "a" * 64
Registro = dict[str, Any]
TROCA_TIPO = {
    "poste_so_a": "poste_so_b",
    "poste_so_b": "poste_so_a",
    "vao_so_a": "vao_so_b",
    "vao_so_b": "vao_so_a",
}


def _poste(
    identidade: str, x: float, y: float = 0.30, simbolos: list[Registro] | None = None
) -> Registro:
    return {
        "id": identidade,
        "pagina": 1,
        "bbox": [x, y, x + 0.02, y + 0.02],
        "identificador": identidade,
        "estruturas": ["N1"],
        "poste": "DT 11/300",
        "coordenada": {"leste": 700000.0, "norte": 7800000.0, "zona": "23K"},
        "simbolos": [] if simbolos is None else simbolos,
        "pendentes": [],
    }


def _simbolo(identidade: str, bbox: list[float], classe: str = "ESTAI") -> Registro:
    return {"id": identidade, "classe": classe, "bbox": bbox}


def _vao(de: str, para: str, comprimento: float | None, cabo: str | None) -> Registro:
    return {"de": de, "para": para, "comprimento_m": comprimento, "cabo": cabo, "pendentes": []}


def ficha() -> Registro:
    """3 postes, 2 vãos e 1 símbolo (no P1)."""
    return {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": SHA,
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [
            _poste("P1", 0.10, simbolos=[_simbolo("S1", [0.13, 0.30, 0.15, 0.32])]),
            _poste("P2", 0.40),
            _poste("P3", 0.70),
        ],
        "vaos": [_vao("P1", "P2", 40.0, "3x1/0"), _vao("P2", "P3", 35.0, "BT 70")],
        "atributos_extras": {"leitura": {"leitor": "a"}},
    }


def _postes(ficha_: Registro) -> dict[str, Registro]:
    return {poste["id"]: poste for poste in ficha_["postes"]}


def _tipos(comparacao: Registro) -> list[str]:
    return sorted(d["tipo"] for d in comparacao["divergencias"])


def _contem(externa: list[float], interna: list[float]) -> bool:
    return (
        externa[0] <= interna[0]
        and externa[1] <= interna[1]
        and interna[2] <= externa[2]
        and interna[3] <= externa[3]
    )


def test_leituras_iguais_nao_tem_divergencia() -> None:
    comp = comparar_leituras(ficha(), ficha())
    assert comp["divergencias"] == [] and regioes_de_conferencia(comp) == []
    assert comp["schema_version"] == "curadoria-ficha-comparacao-v1"
    assert comp["pdf_sha256"] == SHA
    assert [(p["a"], p["b"]) for p in comp["pares"]] == [("P1", "P1"), ("P2", "P2"), ("P3", "P3")]
    assert comp["distancias_casamento"] == [0.0, 0.0, 0.0]
    assert comp["iou_simbolos"] == [1.0]
    assert comp["simbolos_so_geometria"] == 0
    assert comp["concordancia"]["postes"]["tp"] == 3
    assert comp["concordancia"]["gerador_predicao"] == {"leitor": "b"}


def test_campo_diferente_gera_divergencia_de_campo() -> None:
    b = ficha()
    b["postes"][0]["estruturas"] = ["N3"]
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["campo"], d["a"], d["b"]) == ("campo", "estruturas", "P1", "P1")
    assert d["id"] == "d001"
    assert d["pagina"] == 1
    poste = ficha()["postes"][0]["bbox"]
    m = MARGEM_CONFERENCIA_CAMPO
    assert d["bbox"] == [poste[0] - m, poste[1] - m, poste[2] + m, poste[3] + m]


def test_campo_pendente_em_so_um_leitor_diverge_e_nos_dois_nao() -> None:
    b = ficha()
    b["postes"][1]["pendentes"] = ["poste"]
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["campo"], d["a"]) == ("campo", "poste", "P2")

    a = ficha()
    a["postes"][1]["pendentes"] = ["poste"]
    a["postes"][1]["poste"] = None
    assert comparar_leituras(a, b)["divergencias"] == []


def test_poste_so_em_a_e_vao_so_em_b() -> None:
    sem_p3 = ficha()
    sem_p3["postes"] = sem_p3["postes"][:2]
    sem_p3["vaos"] = sem_p3["vaos"][:1]
    divergencias = comparar_leituras(ficha(), sem_p3)["divergencias"]
    assert _tipos({"divergencias": divergencias}) == ["poste_so_a", "vao_so_a"]
    poste = next(d for d in divergencias if d["tipo"] == "poste_so_a")
    assert (poste["a"], poste["b"], poste["campo"]) == ("P3", None, None)
    vao = next(d for d in divergencias if d["tipo"] == "vao_so_a")
    assert (vao["de"], vao["para"], vao["cabo_a"], vao["cabo_b"]) == ("P2", "P3", "BT 70", None)
    p2, p3 = (_postes(ficha())[i]["bbox"] for i in ("P2", "P3"))
    m = MARGEM_CONFERENCIA
    assert vao["bbox"] == [p2[0] - m, p2[1] - m, p3[2] + m, p3[3] + m]

    com_vao_extra = ficha()
    com_vao_extra["vaos"].append(_vao("P1", "P3", 70.0, "BT 70"))
    [d] = comparar_leituras(ficha(), com_vao_extra)["divergencias"]
    assert (d["tipo"], d["de"], d["para"], d["cabo_a"], d["cabo_b"]) == (
        "vao_so_b",
        "P1",
        "P3",
        None,
        "BT 70",
    )

    com_p9 = ficha()
    com_p9["postes"].append(_poste("P9", 0.40, y=0.70))
    com_p9["vaos"].append(_vao("P2", "P9", 50.0, "BT 70"))
    divergencias = comparar_leituras(ficha(), com_p9)["divergencias"]
    assert _tipos({"divergencias": divergencias}) == ["poste_so_b", "vao_so_b"]
    poste = next(d for d in divergencias if d["tipo"] == "poste_so_b")
    assert (poste["a"], poste["b"]) == (None, "P9")
    vao = next(d for d in divergencias if d["tipo"] == "vao_so_b")
    assert (vao["de"], vao["para"]) == ("P2", "b-P9")


def test_dois_vaos_no_mesmo_par_so_um_divergente() -> None:
    a = ficha()
    a["vaos"] = [_vao("P1", "P2", 40.0, "3x1/0"), _vao("P1", "P2", 38.0, "BT 70")]
    b = copy.deepcopy(a)
    b["vaos"][1]["comprimento_m"] = 30.0
    [d] = comparar_leituras(a, b)["divergencias"]
    assert (d["tipo"], d["campo"], d["cabo_a"], d["cabo_b"]) == (
        "vao_atributo",
        "comprimento_m",
        "BT 70",
        "BT 70",
    )
    assert (d["de"], d["para"], d["a"], d["b"]) == ("P1", "P2", None, None)
    assert isinstance(d["indice"], int)


def test_cabo_divergente_gera_vao_atributo_cabo() -> None:
    b = ficha()
    b["vaos"][1]["cabo"] = "BT 35"
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["campo"], d["cabo_a"], d["cabo_b"]) == (
        "vao_atributo",
        "cabo",
        "BT 70",
        "BT 35",
    )


def test_simbolo_em_um_so_leitor_gera_divergencia_simbolos_com_bbox_que_o_contem() -> None:
    b = ficha()
    b["postes"][0]["simbolos"] = []
    comp = comparar_leituras(ficha(), b)
    [d] = comp["divergencias"]
    assert (d["tipo"], d["a"], d["b"], d["campo"]) == ("simbolos", "P1", "P1", None)
    simbolo = ficha()["postes"][0]["simbolos"][0]["bbox"]
    poste = ficha()["postes"][0]["bbox"]
    assert _contem(d["bbox"], simbolo) and _contem(d["bbox"], poste)
    m = MARGEM_CONFERENCIA
    assert d["bbox"] == [poste[0] - m, poste[1] - m, simbolo[2] + m, simbolo[3] + m]
    assert comp["iou_simbolos"] == []


def test_simbolo_de_mesma_classe_que_nao_casa_por_iou_conta_so_geometria() -> None:
    b = ficha()
    b["postes"][0]["simbolos"] = [_simbolo("S1", [0.20, 0.30, 0.22, 0.32])]
    comp = comparar_leituras(ficha(), b)
    assert _tipos(comp) == ["simbolos"]
    assert comp["simbolos_so_geometria"] == 1

    outra_classe = ficha()
    outra_classe["postes"][0]["simbolos"] = [
        _simbolo("S1", [0.20, 0.30, 0.22, 0.32], classe="ATERRAMENTO")
    ]
    assert comparar_leituras(ficha(), outra_classe)["simbolos_so_geometria"] == 0


def test_comprimento_divergente_alem_da_tolerancia() -> None:
    b = ficha()
    b["vaos"][1]["comprimento_m"] = 35.05
    assert comparar_leituras(ficha(), b)["divergencias"] == []

    b["vaos"][1]["comprimento_m"] = 40.0
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["campo"]) == ("vao_atributo", "comprimento_m")

    b["vaos"][1]["comprimento_m"] = None
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["campo"]) == ("vao_atributo", "comprimento_m")


def _com_divergencias() -> tuple[Registro, Registro]:
    a, b = ficha(), ficha()
    b["postes"][0]["estruturas"] = ["N3"]
    b["postes"][2]["simbolos"] = [_simbolo("S9", [0.73, 0.30, 0.75, 0.32])]
    b["vaos"][0]["cabo"] = "4x4/0"
    a["postes"].append(_poste("P4", 0.40, y=0.70))
    return a, b


def test_regioes_de_conferencia_nao_trazem_valores() -> None:
    comp_com_divergencias = comparar_leituras(*_com_divergencias())
    regioes = regioes_de_conferencia(comp_com_divergencias)
    assert regioes
    assert all(set(r) == {"id", "pagina", "bbox"} for r in regioes)
    assert [r["id"] for r in regioes] == [f"r{i:03d}" for i in range(1, len(regioes) + 1)]
    for divergencia in comp_com_divergencias["divergencias"]:
        assert any(_contem(r["bbox"], divergencia["bbox"]) for r in regioes)


def test_regioes_sobrepostas_sao_fundidas_e_recortadas_a_pagina() -> None:
    a = ficha()
    a["postes"].append(_poste("P4", 0.73))  # P3 vai de 0,70 a 0,72: 0,01 de distância
    b = ficha()
    b["postes"][2]["poste"] = "DT 12/600"
    comp = comparar_leituras(a, b)
    assert _tipos(comp) == ["campo", "poste_so_a"]
    [regiao] = regioes_de_conferencia(comp)
    assert regiao["pagina"] == 1
    assert all(_contem(regiao["bbox"], d["bbox"]) for d in comp["divergencias"])

    a, b = ficha(), ficha()
    for leitura in (a, b):
        leitura["postes"][0]["bbox"] = [0.005, 0.30, 0.025, 0.32]
        leitura["postes"][0]["simbolos"] = []
    b["postes"][0]["estruturas"] = ["N3"]
    b["postes"][2]["estruturas"] = ["N3"]
    regioes = regioes_de_conferencia(comparar_leituras(a, b))
    assert len(regioes) == 2
    assert regioes[0]["bbox"][0] == 0.0
    assert all(0.0 <= v <= 1.0 for r in regioes for v in r["bbox"])


def test_regioes_ficam_separadas_por_pagina() -> None:
    a, b = ficha(), ficha()
    for leitura in (a, b):
        leitura["postes"][2]["pagina"] = 2
        leitura["postes"][2]["bbox"] = list(leitura["postes"][1]["bbox"])
        leitura["vaos"] = leitura["vaos"][:1]
    b["postes"][1]["estruturas"] = ["N3"]
    b["postes"][2]["estruturas"] = ["N3"]
    regioes = regioes_de_conferencia(comparar_leituras(a, b))
    assert [(r["id"], r["pagina"]) for r in regioes] == [("r001", 1), ("r002", 2)]
    assert regioes[0]["bbox"] == regioes[1]["bbox"]


def _embaralhar(ficha_: Registro, semente: int) -> Registro:
    sorteio = random.Random(semente)
    copia = copy.deepcopy(ficha_)
    sorteio.shuffle(copia["postes"])
    sorteio.shuffle(copia["vaos"])
    for poste in copia["postes"]:
        sorteio.shuffle(poste["simbolos"])
    return copia


def _rica() -> tuple[Registro, Registro]:
    a, b = _com_divergencias()
    for leitura in (a, b):
        leitura["postes"][1]["simbolos"] = [
            _simbolo("S2", [0.43, 0.30, 0.45, 0.32]),
            _simbolo("S3", [0.40, 0.33, 0.42, 0.35], classe="ATERRAMENTO"),
        ]
        leitura["vaos"].append(_vao("P1", "P2", 41.0, "BT 70"))
    b["vaos"].append(_vao("P1", "P3", 70.0, "BT 70"))
    b["postes"].append(_poste("P9", 0.10, y=0.70))
    return a, b


def test_permutar_listas_nao_muda_o_resultado() -> None:
    a, b = _rica()
    esperado = comparar_leituras(a, b)
    assert len(esperado["divergencias"]) >= 5
    for semente in range(6):
        permutado = comparar_leituras(_embaralhar(a, semente), _embaralhar(b, semente + 100))
        assert permutado == esperado


def _renomear(ficha_: Registro, prefixo: str) -> Registro:
    copia = copy.deepcopy(ficha_)
    for poste in copia["postes"]:
        poste["id"] = prefixo + poste["id"]
        for simbolo in poste["simbolos"]:
            simbolo["id"] = prefixo + simbolo["id"]
    for vao in copia["vaos"]:
        vao["de"], vao["para"] = prefixo + vao["de"], prefixo + vao["para"]
    return copia


def _espelho(divergencia: Registro) -> tuple[Any, ...]:
    return (
        TROCA_TIPO.get(divergencia["tipo"], divergencia["tipo"]),
        divergencia["pagina"],
        tuple(divergencia["bbox"]),
        divergencia["campo"],
        divergencia["b"],
        divergencia["a"],
        divergencia.get("cabo_b"),
        divergencia.get("cabo_a"),
    )


def _direta(divergencia: Registro) -> tuple[Any, ...]:
    return (
        divergencia["tipo"],
        divergencia["pagina"],
        tuple(divergencia["bbox"]),
        divergencia["campo"],
        divergencia["a"],
        divergencia["b"],
        divergencia.get("cabo_a"),
        divergencia.get("cabo_b"),
    )


def test_trocar_a_e_b_espelha_as_divergencias() -> None:
    a, b = _rica()
    b = _renomear(b, "Q")
    ab = comparar_leituras(a, b)["divergencias"]
    ba = comparar_leituras(b, a)["divergencias"]
    assert len(ab) >= 5
    assert Counter(_direta(d) for d in ab) == Counter(_espelho(d) for d in ba)


def test_id_so_de_b_que_colide_com_id_de_a_ganha_mais_um_prefixo() -> None:
    def para_do_vao_so_b(ids_extras_a: list[str]) -> str:
        a = ficha()
        for numero, identidade in enumerate(ids_extras_a):
            a["postes"].append(_poste(identidade, 0.10 + 0.2 * numero, y=0.80))
        b = ficha()
        b["postes"].append(_poste("P9", 0.80, y=0.10))
        b["vaos"].append(_vao("P3", "P9", 30.0, "BT 70"))
        [vao] = [d for d in comparar_leituras(a, b)["divergencias"] if d["tipo"] == "vao_so_b"]
        return str(vao["para"])

    assert para_do_vao_so_b([]) == "b-P9"
    assert para_do_vao_so_b(["b-P9"]) == "b-b-P9"
    assert para_do_vao_so_b(["b-P9", "b-b-P9"]) == "b-b-b-P9"


def test_prefixo_unico_vale_para_todos_os_postes_so_de_b() -> None:
    # B tem "P9" e "b-P9" sem par; A tem "b-P9": os dois de B ganham o mesmo prefixo, sem colisão.
    a = ficha()
    a["postes"].append(_poste("b-P9", 0.10, y=0.80))
    b = ficha()
    b["postes"].append(_poste("P9", 0.80, y=0.10))
    b["postes"].append(_poste("b-P9", 0.80, y=0.50))
    b["vaos"].append(_vao("P9", "b-P9", 30.0, "BT 70"))
    [vao] = [d for d in comparar_leituras(a, b)["divergencias"] if d["tipo"] == "vao_so_b"]
    assert {vao["de"], vao["para"]} == {"b-b-P9", "b-b-b-P9"}
    assert vao["bbox"][1] < 0.10 and vao["bbox"][3] > 0.52


def test_comparar_recusa_fichas_de_pdfs_diferentes() -> None:
    b = ficha()
    b["pdf_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="pdf_sha256"):
        comparar_leituras(ficha(), b)


def test_comparar_nao_altera_as_entradas() -> None:
    a, b = _rica()
    copia_a, copia_b = copy.deepcopy(a), copy.deepcopy(b)
    comparar_leituras(a, b)
    assert (a, b) == (copia_a, copia_b)


# --- públicos compartilhados com a consolidação --------------------------------------------------


def test_prefixo_so_b_repete_o_minimo_e_vale_para_todos() -> None:
    assert prefixo_so_b(["P1", "P2"], ["P9"]) == "b-"
    assert prefixo_so_b(["b-P9"], ["P9", "P8"]) == "b-b-"
    assert prefixo_so_b(["b-P9", "b-b-P8"], ["P9", "P8"]) == "b-b-b-"
    assert prefixo_so_b(["b-P9"], []) == "b-"


def _vaos_p1_p2(*cabos_comprimentos: tuple[str, float]) -> list[Registro]:
    return [_vao("P1", "P2", comprimento, cabo) for cabo, comprimento in cabos_comprimentos]


def test_vaos_do_par_em_ordem_devolve_casados_e_sobras_deterministicas() -> None:
    refs = _vaos_p1_p2(("3x1/0", 40.0), ("BT 70", 30.0), ("BT 35", 20.0))
    preds = _vaos_p1_p2(("3x1/0", 40.0))
    casados, sobra_a, sobra_b = vaos_do_par_em_ordem(refs, preds)
    assert casados == casar_vaos_do_par(refs, preds)
    assert sobra_b == []
    assert sorted(v["cabo"] for v in sobra_a) == ["BT 35", "BT 70"]
    for _ in range(4):
        refs.reverse()
        assert vaos_do_par_em_ordem(refs, preds) == (casados, sobra_a, sobra_b)
    casados_inv, sobra_a_inv, sobra_b_inv = vaos_do_par_em_ordem(preds, refs)
    assert sobra_a_inv == [] and sobra_b_inv == sobra_a and len(casados_inv) == 1


def test_duas_sobras_no_mesmo_par_tem_indices_que_apontam_o_vao_certo() -> None:
    a = ficha()
    a["vaos"] = _vaos_p1_p2(("3x1/0", 40.0), ("BT 70", 30.0), ("BT 35", 20.0))
    b = ficha()
    b["vaos"] = _vaos_p1_p2(("3x1/0", 40.0))
    casados, sobra_a, _ = vaos_do_par_em_ordem(a["vaos"], b["vaos"])
    for tipo, x, y, sobra in (("vao_so_a", a, b, sobra_a), ("vao_so_b", b, a, sobra_a)):
        divergencias = sorted(
            (d for d in comparar_leituras(x, y)["divergencias"] if d["tipo"] == tipo),
            key=lambda d: d["indice"],
        )
        assert [d["indice"] for d in divergencias] == [1, 2]
        cabos = [d["cabo_a"] if tipo == "vao_so_a" else d["cabo_b"] for d in divergencias]
        assert cabos == [sobra[d["indice"] - len(casados)]["cabo"] for d in divergencias]


# --- consolidação --------------------------------------------------------------------------------

CONTAGEM_ZERADA = {
    "resolvidas_por_c": 0,
    "pendentes": 0,
    "descartadas_por_maioria": 0,
    "nao_cobertas_por_c": 0,
    "excluidas": [],
}
PAGINA_INTEIRA = {"pagina": 1, "bbox": [0.0, 0.0, 1.0, 1.0]}


def _leitura_c(
    *postes: Registro,
    vaos: list[Registro] | None = None,
    regioes: list[Registro] | None = None,
    ilegiveis: list[Registro] | None = None,
) -> Registro:
    """Leitura C regional, com ids próprios (prefixo ``c``) para não depender dos de A."""
    c = ficha()
    c["postes"] = [copy.deepcopy(poste) for poste in postes]
    c["vaos"] = copy.deepcopy(vaos or [])
    c["escopo_anotacao"] = {"tipo": "regional", "regioes": regioes or [PAGINA_INTEIRA]}
    c["atributos_extras"] = {"leitura": {"leitor": "c", "regioes_ilegiveis": ilegiveis or []}}
    return _renomear(c, "c")


def _consolidar(a: Registro, b: Registro, c: Registro | None = None, paginas: int = 1) -> Registro:
    referencia = consolidar(a, b, c, comparar_leituras(a, b), paginas=paginas)
    assert validar_ficha(referencia) == []
    assert referencia["tipo"] == "referencia"
    assert "leitura" not in referencia["atributos_extras"]
    return referencia


def _contagem(referencia: Registro) -> Registro:
    return dict(referencia["atributos_extras"]["consolidacao"])


def _sem_p3() -> Registro:
    b = ficha()
    b["postes"] = b["postes"][:2]
    b["vaos"] = b["vaos"][:1]
    return b


def _ilegivel(bbox: list[float], pagina: int = 1) -> Registro:
    return {"pagina": pagina, "camada": "base", "bbox": bbox, "motivo": "mancha"}


def _cabos(referencia: Registro) -> dict[str | None, float | None]:
    return {v["cabo"]: v["comprimento_m"] for v in referencia["vaos"]}


def test_consolidar_sem_divergencia_reproduz_a_sem_metadados_de_leitura() -> None:
    referencia = _consolidar(ficha(), ficha())
    esperado = ficha()
    esperado["atributos_extras"] = {"consolidacao": CONTAGEM_ZERADA}
    assert referencia == esperado


def test_campo_divergente_resolvido_por_c() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["estruturas"] = ["N3"]
    referencia = _consolidar(a, b, _leitura_c(b["postes"][0]))
    p1 = _postes(referencia)["P1"]
    assert (p1["estruturas"], p1["pendentes"]) == (["N3"], [])
    assert _contagem(referencia) == {**CONTAGEM_ZERADA, "resolvidas_por_c": 1}

    referencia = _consolidar(a, b, _leitura_c(a["postes"][0]))
    assert _postes(referencia)["P1"]["estruturas"] == ["N1"]
    assert _contagem(referencia)["resolvidas_por_c"] == 1


def test_campo_divergente_sem_acordo_vira_pendente_nulo() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["estruturas"] = ["N3"]
    poste_c = copy.deepcopy(a["postes"][0])
    poste_c["estruturas"] = ["U3"]
    referencia = _consolidar(a, b, _leitura_c(poste_c))
    p1 = _postes(referencia)["P1"]
    assert (p1["estruturas"], p1["pendentes"]) == ([], ["estruturas"])
    assert _contagem(referencia) == {**CONTAGEM_ZERADA, "pendentes": 1}

    poste_c["estruturas"] = ["N3"]
    poste_c["pendentes"] = ["estruturas"]
    referencia = _consolidar(a, b, _leitura_c(poste_c))
    assert _postes(referencia)["P1"]["pendentes"] == ["estruturas"]

    b = ficha()
    b["postes"][1]["poste"] = "DT 12/600"
    b["postes"][1]["coordenada"] = None
    p2 = _postes(_consolidar(a, b))["P2"]
    assert (p2["poste"], p2["coordenada"], p2["pendentes"]) == (None, None, ["poste", "coordenada"])


def test_campo_pendente_nos_dois_fica_pendente_e_em_um_so_e_resolvido_por_c() -> None:
    a, b = ficha(), ficha()
    for leitura in (a, b):
        leitura["postes"][1]["pendentes"] = ["identificador"]
    referencia = _consolidar(a, b)
    p2 = _postes(referencia)["P2"]
    assert (p2["identificador"], p2["pendentes"]) == (None, ["identificador"])
    assert _contagem(referencia) == CONTAGEM_ZERADA

    a = ficha()
    referencia = _consolidar(a, b, _leitura_c(a["postes"][1]))
    p2 = _postes(referencia)["P2"]
    assert (p2["identificador"], p2["pendentes"]) == ("P2", [])
    assert _contagem(referencia)["resolvidas_por_c"] == 1


def test_divergencia_fora_das_regioes_de_c_conta_nao_coberta() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["estruturas"] = ["N3"]
    longe = _leitura_c(regioes=[{"pagina": 1, "bbox": [0.5, 0.5, 0.9, 0.9]}])
    esperado = {**CONTAGEM_ZERADA, "pendentes": 1, "nao_cobertas_por_c": 1}
    assert _contagem(_consolidar(a, b, longe)) == esperado
    assert _contagem(_consolidar(a, b)) == esperado

    ilegivel = _leitura_c(b["postes"][0], ilegiveis=[_ilegivel([0.05, 0.25, 0.20, 0.40])])
    referencia = _consolidar(a, b, ilegivel)
    assert _postes(referencia)["P1"]["pendentes"] == ["estruturas"]
    assert _contagem(referencia) == esperado


def test_simbolos_sem_acordo_viram_pendentes() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["simbolos"] = []
    poste_c = copy.deepcopy(a["postes"][0])
    poste_c["simbolos"] = [_simbolo("S5", [0.50, 0.50, 0.52, 0.52])]
    referencia = _consolidar(a, b, _leitura_c(poste_c))
    p1 = _postes(referencia)["P1"]
    assert (p1["simbolos"], p1["pendentes"]) == ([], ["simbolos"])
    assert _contagem(referencia) == {**CONTAGEM_ZERADA, "pendentes": 1}


def test_simbolos_confirmados_por_c_vem_de_quem_c_confirma() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["simbolos"] = []
    referencia = _consolidar(a, b, _leitura_c(b["postes"][0]))
    p1 = _postes(referencia)["P1"]
    assert (p1["simbolos"], p1["pendentes"]) == ([], [])
    referencia = _consolidar(a, b, _leitura_c(a["postes"][0]))
    assert _postes(referencia)["P1"]["simbolos"] == a["postes"][0]["simbolos"]

    a, b = ficha(), ficha()
    a["postes"][1]["simbolos"] = [_simbolo("b-S9", [0.43, 0.30, 0.45, 0.32])]
    b["postes"][1]["simbolos"] = [_simbolo("b-S9", [0.43, 0.30, 0.45, 0.32])]
    b["postes"][2]["simbolos"] = [_simbolo("S9", [0.73, 0.30, 0.75, 0.32])]
    referencia = _consolidar(a, b, _leitura_c(b["postes"][2]))
    assert _postes(referencia)["P3"]["simbolos"] == [_simbolo("b-b-S9", [0.73, 0.30, 0.75, 0.32])]
    assert _contagem(referencia)["resolvidas_por_c"] == 1


def test_poste_so_em_a_confirmado_por_c_entra() -> None:
    a, b = ficha(), _sem_p3()
    c = _leitura_c(a["postes"][1], a["postes"][2], vaos=[_vao("P2", "P3", 35.0, "BT 70")])
    referencia = _consolidar(a, b, c)
    assert _postes(referencia)["P3"] == a["postes"][2]
    assert referencia["vaos"] == a["vaos"]
    assert referencia["escopo_anotacao"] == {"tipo": "completo"}
    assert _contagem(referencia) == CONTAGEM_ZERADA

    c["postes"][1]["poste"] = "DT 12/600"
    referencia = _consolidar(a, b, c)
    p3 = _postes(referencia)["P3"]
    assert (p3["poste"], p3["pendentes"]) == (None, ["poste"])
    assert _contagem(referencia) == {**CONTAGEM_ZERADA, "pendentes": 1}


def test_poste_so_em_b_confirmado_por_c_usa_o_prefixo_da_comparacao() -> None:
    a = ficha()
    a["postes"].append(_poste("b-P9", 0.10, y=0.80))
    b = ficha()
    b["postes"].append(_poste("P9", 0.80, y=0.10))
    b["vaos"].append(_vao("P3", "P9", 30.0, "BT 70"))
    c = _leitura_c(
        a["postes"][3], b["postes"][2], b["postes"][3], vaos=[_vao("P3", "P9", 30.0, "BT 70")]
    )
    comparacao = comparar_leituras(a, b)
    [vao_so_b] = [d for d in comparacao["divergencias"] if d["tipo"] == "vao_so_b"]
    referencia = consolidar(a, b, c, comparacao, paginas=1)
    assert validar_ficha(referencia) == []
    postes = _postes(referencia)
    assert set(postes) == {"P1", "P2", "P3", "b-P9", "b-b-P9"}
    assert postes["b-b-P9"]["bbox"] == b["postes"][3]["bbox"]
    assert postes["b-P9"]["bbox"] == a["postes"][3]["bbox"]
    novo = next(v for v in referencia["vaos"] if "b-b-P9" in (v["de"], v["para"]))
    assert (novo["de"], novo["para"]) == (vao_so_b["de"], vao_so_b["para"])


def test_poste_so_em_a_negado_por_c_e_descartado() -> None:
    a, b = ficha(), _sem_p3()
    referencia = _consolidar(a, b, _leitura_c(a["postes"][1]))
    assert set(_postes(referencia)) == {"P1", "P2"}
    assert referencia["vaos"] == a["vaos"][:1]
    assert referencia["escopo_anotacao"] == {"tipo": "completo"}
    assert _contagem(referencia) == {**CONTAGEM_ZERADA, "descartadas_por_maioria": 1}


def test_consolidar_sem_c_exclui_poste_disputado_do_escopo() -> None:
    a, b_sem_p3 = ficha(), _sem_p3()
    referencia = consolidar(a, b_sem_p3, None, comparar_leituras(a, b_sem_p3), paginas=1)
    assert validar_ficha(referencia) == []
    assert referencia["escopo_anotacao"]["tipo"] == "regional"
    assert "P3" not in {p["id"] for p in referencia["postes"]}
    predicao_com_p3 = copy.deepcopy(a)
    predicao_com_p3["tipo"] = "predicao"
    predicao_com_p3["gerador"] = {"leitor": "teste"}
    relatorio = avaliar(referencia, predicao_com_p3)
    assert relatorio["postes"]["fp"] == 0
    assert relatorio["vaos"]["fp"] == 0
    [zona] = _contagem(referencia)["excluidas"]
    p3 = a["postes"][2]["bbox"]
    m = MARGEM_CONFERENCIA
    assert zona == {
        "pagina": 1,
        "bbox": [p3[0] - m, p3[1] - m, p3[2] + m, p3[3] + m],
        "motivo": "poste_disputado",
    }


def test_regiao_ilegivel_vira_zona_excluida() -> None:
    a, b = ficha(), ficha()
    a["atributos_extras"]["leitura"]["regioes_ilegiveis"] = [_ilegivel([0.90, 0.90, 0.95, 0.95])]
    b["atributos_extras"]["leitura"]["regioes_ilegiveis"] = [_ilegivel([0.65, 0.25, 0.80, 0.40])]
    referencia = _consolidar(a, b)
    assert _contagem(referencia)["excluidas"] == [
        {"pagina": 1, "bbox": [0.65, 0.25, 0.80, 0.40], "motivo": "ilegivel"},
        {"pagina": 1, "bbox": [0.90, 0.90, 0.95, 0.95], "motivo": "ilegivel"},
    ]
    assert referencia["escopo_anotacao"]["tipo"] == "regional"
    assert set(_postes(referencia)) == {"P1", "P2"}
    assert referencia["vaos"] == a["vaos"][:1]


def test_vao_so_em_um_leitor_sem_c_exclui_os_extremos() -> None:
    a, b = ficha(), ficha()
    b["vaos"] = b["vaos"][:1]
    referencia = _consolidar(a, b)
    zonas = _contagem(referencia)["excluidas"]
    assert [z["motivo"] for z in zonas] == ["vao_disputado", "vao_disputado"]
    for zona, poste in zip(zonas, a["postes"][1:], strict=True):
        assert _contem(zona["bbox"], poste["bbox"])
    assert set(_postes(referencia)) == {"P1"}
    assert referencia["vaos"] == []

    c = _leitura_c(a["postes"][1], a["postes"][2])
    referencia = _consolidar(a, b, c)
    assert set(_postes(referencia)) == {"P1", "P2", "P3"}
    assert referencia["vaos"] == b["vaos"]
    assert _contagem(referencia) == {**CONTAGEM_ZERADA, "descartadas_por_maioria": 1}

    c = _leitura_c(a["postes"][1], a["postes"][2], vaos=[_vao("P2", "P3", 35.0, "BT 70")])
    referencia = _consolidar(a, b, c)
    assert referencia["vaos"] == a["vaos"]
    assert _contagem(referencia) == CONTAGEM_ZERADA


def test_consolidar_dois_vaos_no_mesmo_par_nao_troca_atributos() -> None:
    a = ficha()
    a["vaos"] = _vaos_p1_p2(("3x1/0", 40.0), ("BT 70", 38.0))
    b = copy.deepcopy(a)
    b["vaos"][1]["comprimento_m"] = 30.0
    c = _leitura_c(
        a["postes"][0], a["postes"][1], vaos=_vaos_p1_p2(("3x1/0", 99.0), ("BT 70", 30.0))
    )
    referencia = _consolidar(a, b, c)
    assert _cabos(referencia) == {"3x1/0": 40.0, "BT 70": 30.0}
    assert all(v["pendentes"] == [] for v in referencia["vaos"])
    assert _contagem(referencia) == {**CONTAGEM_ZERADA, "resolvidas_por_c": 1}

    c["vaos"][1]["comprimento_m"] = 50.0
    referencia = _consolidar(a, b, c)
    vao_bt = next(v for v in referencia["vaos"] if v["cabo"] == "BT 70")
    assert (vao_bt["comprimento_m"], vao_bt["pendentes"]) == (None, ["comprimento_m"])
    assert _contagem(referencia) == {**CONTAGEM_ZERADA, "pendentes": 1}


def test_duas_sobras_no_mesmo_par_a_consolidacao_usa_o_mesmo_vao_do_indice() -> None:
    a = ficha()
    a["vaos"] = _vaos_p1_p2(("3x1/0", 40.0), ("BT 70", 30.0), ("BT 35", 20.0))
    b = ficha()
    b["vaos"] = _vaos_p1_p2(("3x1/0", 40.0))
    casados, sobra_a, _ = vaos_do_par_em_ordem(a["vaos"], b["vaos"])
    comparacao = comparar_leituras(a, b)
    for j, confirmado in enumerate(sobra_a):
        [divergencia] = [
            d
            for d in comparacao["divergencias"]
            if d["tipo"] == "vao_so_a" and d["indice"] == len(casados) + j
        ]
        assert divergencia["cabo_a"] == confirmado["cabo"]
        c = _leitura_c(a["postes"][0], a["postes"][1], vaos=[*b["vaos"], dict(confirmado)])
        referencia = consolidar(a, b, c, comparacao, paginas=1)
        esperado = {"3x1/0": 40.0, confirmado["cabo"]: confirmado["comprimento_m"]}
        assert _cabos(referencia) == esperado
        assert _contagem(referencia) == {**CONTAGEM_ZERADA, "descartadas_por_maioria": 1}


def _area(caixa: list[float]) -> float:
    return max(0.0, caixa[2] - caixa[0]) * max(0.0, caixa[3] - caixa[1])


def _intersecao(c1: list[float], c2: list[float]) -> list[float]:
    return [max(c1[0], c2[0]), max(c1[1], c2[1]), min(c1[2], c2[2]), min(c1[3], c2[3])]


def test_escopo_cobre_todas_as_paginas_menos_as_zonas() -> None:
    a, b = ficha(), ficha()
    zona = [0.50, 0.50, 0.60, 0.70]
    a["atributos_extras"]["leitura"]["regioes_ilegiveis"] = [_ilegivel(zona)]
    referencia = _consolidar(a, b, paginas=2)
    regioes = referencia["escopo_anotacao"]["regioes"]
    assert [r for r in regioes if r["pagina"] == 2] == [{"pagina": 2, "bbox": [0.0, 0.0, 1.0, 1.0]}]
    pagina_1 = [r["bbox"] for r in regioes if r["pagina"] == 1]
    assert 1 < len(pagina_1) <= 4
    assert all(r["pagina"] in (1, 2) for r in regioes)
    centro = (0.55, 0.60)
    assert not any(r[0] <= centro[0] <= r[2] and r[1] <= centro[1] <= r[3] for r in pagina_1)
    assert all(_area(_intersecao(r, zona)) == 0 for r in pagina_1)
    assert sum(_area(r) for r in pagina_1) == pytest.approx(1 - _area(zona))
    for i, r1 in enumerate(pagina_1):
        assert all(_area(_intersecao(r1, r2)) == 0 for r2 in pagina_1[i + 1 :])
    assert set(_postes(referencia)) == {"P1", "P2", "P3"}


def test_zonas_sobrepostas_e_em_paginas_diferentes() -> None:
    a, b = ficha(), ficha()
    a["atributos_extras"]["leitura"]["regioes_ilegiveis"] = [
        _ilegivel([0.50, 0.50, 0.60, 0.70]),
        _ilegivel([0.55, 0.65, 0.80, 0.90]),
        _ilegivel([0.0, 0.0, 1.0, 0.5], pagina=2),
    ]
    referencia = _consolidar(a, b, paginas=2)
    regioes = referencia["escopo_anotacao"]["regioes"]
    pagina_1 = [r["bbox"] for r in regioes if r["pagina"] == 1]
    uniao_das_zonas = 0.1 * 0.2 + 0.25 * 0.25 - 0.05 * 0.05
    assert sum(_area(r) for r in pagina_1) == pytest.approx(1 - uniao_das_zonas)
    assert [r["bbox"] for r in regioes if r["pagina"] == 2] == [[0.0, 0.5, 1.0, 1.0]]


def test_consolidar_recusa_comparacao_de_outras_leituras_e_c_de_outro_pdf() -> None:
    a, b = ficha(), _sem_p3()
    with pytest.raises(ValueError, match="comparação"):
        consolidar(a, b, None, comparar_leituras(a, ficha()), paginas=1)
    c = _leitura_c(a["postes"][2])
    c["pdf_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="pdf_sha256"):
        consolidar(a, b, c, comparar_leituras(a, b), paginas=1)


def test_consolidar_independe_da_ordem_e_nao_altera_as_entradas() -> None:
    a, b = _rica()
    c = _leitura_c(*b["postes"], vaos=b["vaos"])
    comparacao = comparar_leituras(a, b)
    copias = copy.deepcopy((a, b, c, comparacao))
    esperado = consolidar(a, b, c, comparacao, paginas=1)
    assert (a, b, c, comparacao) == copias
    assert validar_ficha(esperado) == []
    assert _contagem(esperado)["resolvidas_por_c"] >= 3
    for semente in range(6):
        permutada = consolidar(
            _embaralhar(a, semente),
            _embaralhar(b, semente + 100),
            _embaralhar(c, semente + 200),
            comparacao,
            paginas=1,
        )
        assert permutada == esperado
