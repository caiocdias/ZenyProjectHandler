"""Ataque à Task 3 da E07.1 (fonte ``propostas-v2``): bordas, entradas hostis e regressões.

Complementa ``test_ficha_predita_propostas_v2.py`` sem alterá-lo. Fixtures sintéticas apenas.
Os testes que falham aqui documentam defeitos do gerador; nenhum foi ajustado para passar.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import scripts.benchmark_ficha_poste as modulo
from scripts.curation_ficha import baseline
from scripts.ficha_poste import validar_ficha
from scripts.ficha_predita_propostas import ficha_predita_propostas
from tests.pdf_fixtures import create_network_benchmark_pdf
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica
from tests.unit.test_curation_ficha_baseline_processos import _montar
from tests.unit.test_ficha_predita_propostas import SHA_QUALQUER, _Cena

from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao

POSTE = CategoriaElemento.POSTE
ESTRUTURA_MT = CategoriaElemento.ESTRUTURA_MT
EQUIPAMENTO = CategoriaElemento.EQUIPAMENTO
CABO = CategoriaElemento.CABO
V1 = "propostas-v1"
V2 = "propostas-v2"


def _ficha(cena: _Cena, versao: str = V2) -> dict[str, Any]:
    variante = cena.variante()
    variante["extraction"] = {}
    return ficha_predita_propostas(variante, SHA_QUALQUER, native_only=True, versao=versao)


def _poste(cena: _Cena, x: float = 0.2) -> Any:
    return cena.elemento(POSTE, codigo="POSTE", x=x, atributos={"identificador_operacional": "P"})


def _estai(cena: _Cena, suporte: object, **extra: Any) -> Any:
    return cena.elemento(
        EQUIPAMENTO, atributos={"simbolo_classe": "ESTAI", "suporte_proposta_id": suporte}, **extra
    )


def _cabo_entre(cena: _Cena, codigo: str | None, **extra: Any) -> None:
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    cabo = cena.elemento(CABO, codigo=codigo, **extra)
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, p2, "CONECTA")


def _classes(poste: dict[str, Any]) -> list[str]:
    return [s["classe"] for s in poste["simbolos"]]


def _estrutura_em(cena: _Cena, poste: Any, codigo: str | None, **atributos: Any) -> None:
    estrutura = cena.elemento(ESTRUTURA_MT, codigo=codigo, atributos=atributos)
    cena.relacao(estrutura, poste, "INSTALADA_EM")


# --- estruturas ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token", ["", "   ", "\t\n", None], ids=["vazio", "espacos", "tabnl", "none"]
)
def test_v2_token_vazio_cai_para_codigo_observado(
    catalogo_inicial: CatalogoTecnico, token: object
) -> None:
    cena = _Cena(catalogo_inicial)
    _estrutura_em(cena, _poste(cena), "N3", token_estrutura=token)

    assert _ficha(cena)["postes"][0]["estruturas"] == ["N3"]


@pytest.mark.parametrize(
    "token", [["U4"], {"a": 1}, ("U4",), object()], ids=["lista", "dict", "tupla", "objeto"]
)
def test_v2_token_de_tipo_hostil_nao_vira_texto_de_repr(
    catalogo_inicial: CatalogoTecnico, token: object
) -> None:
    cena = _Cena(catalogo_inicial)
    _estrutura_em(cena, _poste(cena), "N3", token_estrutura=token)

    ficha = _ficha(cena)

    assert validar_ficha(ficha) == []
    assert ficha["postes"][0]["estruturas"] == ["N3"]


def test_v2_token_numerico_vira_texto_sem_quebrar(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    _estrutura_em(cena, _poste(cena), "N3", token_estrutura=7)

    ficha = _ficha(cena)

    assert validar_ficha(ficha) == []
    assert ficha["postes"][0]["estruturas"] == ["7"]


def test_v2_token_com_bordas_em_branco_e_aparado(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    _estrutura_em(cena, _poste(cena), "U4", token_estrutura=" U4(1) ")

    assert _ficha(cena)["postes"][0]["estruturas"] == ["U4(1)"]


def test_v2_estrutura_sem_token_nem_codigo_nao_conta_como_sem_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    _poste(cena)
    cena.elemento(ESTRUTURA_MT)
    cena.elemento(ESTRUTURA_MT, codigo="  ")

    ficha = _ficha(cena)

    assert ficha["postes"][0]["estruturas"] == []
    assert "estruturas_sem_poste" not in ficha["atributos_extras"]


def test_v2_estrutura_so_com_token_e_sem_relacao_conta_sem_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    _poste(cena)
    cena.elemento(ESTRUTURA_MT, atributos={"token_estrutura": "U4(1)"})

    ficha = _ficha(cena)

    assert ficha["postes"][0]["estruturas"] == []
    assert ficha["atributos_extras"]["estruturas_sem_poste"] == 1


def test_v2_lista_de_estruturas_ordenada_com_repeticao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    poste = _poste(cena)
    for token in ("U4(1)", "N3", "U4(1)", "B1"):
        _estrutura_em(cena, poste, None, token_estrutura=token)

    assert _ficha(cena)["postes"][0]["estruturas"] == ["B1", "N3", "U4(1)", "U4(1)"]


def test_v2_estrutura_pendente_com_token_marca_pendencia(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    pendente = cena.elemento(
        ESTRUTURA_MT, estado=EstadoRevisao.CONFLITANTE, atributos={"token_estrutura": "U4(1)"}
    )
    cena.relacao(pendente, p1, "INSTALADA_EM")
    _estrutura_em(cena, p2, None, token_estrutura="N3")

    por_id = {p["id"]: p for p in _ficha(cena)["postes"]}

    assert por_id[str(p1.id)]["estruturas"] == ["U4(1)"]
    assert por_id[str(p1.id)]["pendentes"] == ["estruturas"]
    assert por_id[str(p2.id)]["pendentes"] == []


# --- código de cabo -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("N- (1N2)", "N-(1N2)"),
        ("N-\t(1N2)", "N-(1N2)"),
        ("N-\n(1N2)", "N-(1N2)"),
        ("N-  -  (1N2)", "N--(1N2)"),
        ("N - (1N2)", "N -(1N2)"),
        ("  N-(1N2)  ", "N-(1N2)"),
        ("3  x  4 - 2", "3 x 4 -2"),
        ("A--  B", "A--B"),
        ("N-(1N2)", "N-(1N2)"),
        ("N-", "N-"),
        ("-", "-"),
    ],
    ids=repr,
)
def test_v2_codigo_de_cabo_espacos_e_hifens(
    catalogo_inicial: CatalogoTecnico, bruto: str, esperado: str
) -> None:
    cena = _Cena(catalogo_inicial)
    _cabo_entre(cena, bruto)

    assert _ficha(cena)["vaos"][0]["cabo"] == esperado


@pytest.mark.parametrize("codigo", [None, "", "   ", "\t"], ids=repr)
def test_v2_codigo_de_cabo_ausente_ou_em_branco_vira_nulo_e_ficha_valida(
    catalogo_inicial: CatalogoTecnico, codigo: str | None
) -> None:
    cena = _Cena(catalogo_inicial)
    _cabo_entre(cena, codigo)

    ficha = _ficha(cena)

    assert ficha["vaos"][0]["cabo"] is None
    assert validar_ficha(ficha) == []


def test_v2_cabo_nao_altera_demais_campos_do_vao(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    _cabo_entre(cena, "N- (1N2)")

    v1, v2 = _ficha(cena, V1)["vaos"][0], _ficha(cena)["vaos"][0]

    assert {k: v for k, v in v1.items() if k != "cabo"} == {
        k: v for k, v in v2.items() if k != "cabo"
    }


# --- ESTAI --------------------------------------------------------------------------------------


def test_v2_estai_com_relacao_para_poste_vale_a_relacao_mesmo_com_suporte_fora(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    cena.relacao(_estai(cena, str(uuid4())), p2, "INSTALADO_EM")

    ficha = _ficha(cena)
    por_id = {p["id"]: p for p in ficha["postes"]}

    assert _classes(por_id[str(p2.id)]) == ["ESTAI"]
    assert _classes(por_id[str(p1.id)]) == []
    assert "simbolos_de_poste_fora_da_ficha" not in ficha["atributos_extras"]


def test_v2_estai_nao_entra_duas_vezes_com_relacao_e_suporte_no_mesmo_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = _poste(cena)
    cena.relacao(_estai(cena, str(p1.id)), p1, "INSTALADO_EM")

    assert _classes(_ficha(cena)["postes"][0]) == ["ESTAI"]


def test_v2_estai_com_relacao_rejeitada_cai_para_o_suporte(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    cena.relacao(_estai(cena, str(p2.id)), p1, "INSTALADO_EM", estado=EstadoRevisao.REJEITADA)

    por_id = {p["id"]: p for p in _ficha(cena)["postes"]}

    assert _classes(por_id[str(p2.id)]) == ["ESTAI"]
    assert _classes(por_id[str(p1.id)]) == []


def test_v2_estai_com_relacao_de_outro_tipo_nao_conta_como_instalado_em(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    cena.relacao(_estai(cena, str(p2.id)), p1, "CONECTA")

    por_id = {p["id"]: p for p in _ficha(cena)["postes"]}

    assert _classes(por_id[str(p2.id)]) == ["ESTAI"]


def test_v2_estai_pendente_pelo_suporte_marca_pendencia_de_simbolos(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = _poste(cena)
    _estai(cena, str(p1.id), estado=EstadoRevisao.CONFLITANTE)

    poste = _ficha(cena)["postes"][0]

    assert _classes(poste) == ["ESTAI"]
    assert "simbolos" in poste["pendentes"]


def test_v2_suporte_uuid_objeto_e_comparado_como_texto(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = _poste(cena)
    _estai(cena, p1.id)

    assert _classes(_ficha(cena)["postes"][0]) == ["ESTAI"]


@pytest.mark.parametrize("variacao", ["maiuscula", "espaco"])
def test_v2_suporte_e_comparado_literalmente_sem_normalizar(
    catalogo_inicial: CatalogoTecnico, variacao: str
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = _poste(cena)
    texto = str(p1.id)
    _estai(cena, texto.upper() if variacao == "maiuscula" else f" {texto} ")

    ficha = _ficha(cena)

    assert _classes(ficha["postes"][0]) == []
    assert ficha["atributos_extras"]["simbolos_de_poste_fora_da_ficha"] == 1


@pytest.mark.parametrize("suporte", [[], {}, ["x"], True, 0, 1.5, float("nan")], ids=repr)
def test_v2_suporte_de_tipo_hostil_nao_quebra_nem_entra(
    catalogo_inicial: CatalogoTecnico, suporte: object
) -> None:
    cena = _Cena(catalogo_inicial)
    _poste(cena)
    _estai(cena, suporte)

    ficha = _ficha(cena)

    assert validar_ficha(ficha) == []
    assert _classes(ficha["postes"][0]) == []
    assert ficha["atributos_extras"]["simbolos_de_poste_fora_da_ficha"] == 1


def test_v2_suporte_que_aponta_para_nao_poste_nao_entra(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    _poste(cena)
    estrutura = cena.elemento(ESTRUTURA_MT, codigo="N3")
    _estai(cena, str(estrutura.id))

    ficha = _ficha(cena)

    assert _classes(ficha["postes"][0]) == []
    assert ficha["atributos_extras"]["simbolos_de_poste_fora_da_ficha"] == 1


def test_v2_suporte_so_vale_para_equipamento_estai_exato(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = _poste(cena)
    suporte = str(p1.id)
    cena.elemento(
        EQUIPAMENTO,
        atributos={"simbolo_classe": "TRANSFORMADOR", "suporte_proposta_id": suporte},
    )
    cena.elemento(
        EQUIPAMENTO, atributos={"simbolo_classe": "estai", "suporte_proposta_id": suporte}
    )
    cena.elemento(
        ESTRUTURA_MT,
        codigo="N3",
        atributos={"simbolo_classe": "ESTAI", "suporte_proposta_id": suporte},
    )

    assert _classes(_ficha(cena)["postes"][0]) == []


def test_v2_dois_estais_no_mesmo_suporte_contam_os_dois(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = _poste(cena)
    _estai(cena, str(p1.id))
    _estai(cena, str(p1.id))

    assert _classes(_ficha(cena)["postes"][0]) == ["ESTAI", "ESTAI"]


# --- pendentes, imutabilidade e determinismo ----------------------------------------------------


def test_v2_pendentes_de_poste_e_de_vao_preservadas(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    _cabo_entre(cena, "N- (1N2)", estado=EstadoRevisao.CONFLITANTE)

    v1, v2 = _ficha(cena, V1), _ficha(cena)

    assert v2["vaos"][0]["pendentes"] == v1["vaos"][0]["pendentes"] == ["cabo", "comprimento_m"]
    assert [p["pendentes"] for p in v2["postes"]] == [p["pendentes"] for p in v1["postes"]]


def test_v2_e_deterministica_e_nao_muta_a_variante(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1, p2 = _poste(cena), _poste(cena, 0.6)
    _estrutura_em(cena, p1, None, token_estrutura="U4(1)")
    _estai(cena, str(p2.id))
    cabo = cena.elemento(CABO, codigo="N- (1N2)")
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, p2, "CONECTA")
    variante = cena.variante()
    variante["extraction"] = {}
    antes = repr(variante["semantic"])

    a = ficha_predita_propostas(variante, SHA_QUALQUER, native_only=True, versao=V2)
    b = ficha_predita_propostas(variante, SHA_QUALQUER, native_only=True, versao=V2)

    assert a == b
    assert repr(variante["semantic"]) == antes


def test_v2_sem_token_estai_nem_espaco_difere_da_v1_so_no_gerador(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    _estrutura_em(cena, _poste(cena), "N3")
    cabo = cena.elemento(CABO, codigo="N-(1N2)")
    cena.relacao(cabo, _poste(cena, 0.5), "CONECTA")
    cena.relacao(cabo, _poste(cena, 0.7), "CONECTA")

    v1, v2 = _ficha(cena, V1), _ficha(cena)

    assert v1["gerador"]["versao_extracao"] == V1
    assert v2["gerador"]["versao_extracao"] == V2
    v1["gerador"]["versao_extracao"] = V2
    assert v1 == v2


# --- v1 intocada --------------------------------------------------------------------------------


def test_v1_ignora_token_estai_e_normalizacao_de_cabo(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = _poste(cena)
    _estrutura_em(cena, p1, "U4", token_estrutura="U4(1)")
    cena.elemento(ESTRUTURA_MT, atributos={"token_estrutura": "N3"})
    _estai(cena, str(p1.id))
    _cabo_entre(cena, "N-  (1N2)")

    ficha = _ficha(cena, V1)

    assert ficha["postes"][0]["estruturas"] == ["U4"]
    assert _classes(ficha["postes"][0]) == []
    assert ficha["atributos_extras"]["simbolos_de_poste_fora_da_ficha"] == 1
    assert "estruturas_sem_poste" not in ficha["atributos_extras"]
    assert ficha["vaos"][0]["cabo"] == "N-  (1N2)"
    assert ficha["gerador"]["versao_extracao"] == V1


def test_versao_padrao_e_v1_e_nao_e_posicional(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    _cabo_entre(cena, "N- (1N2)")
    variante = cena.variante()
    variante["extraction"] = {}

    padrao = ficha_predita_propostas(variante, SHA_QUALQUER, native_only=True)

    assert padrao["gerador"]["versao_extracao"] == V1
    assert padrao["vaos"][0]["cabo"] == "N- (1N2)"
    with pytest.raises(TypeError):
        ficha_predita_propostas(variante, SHA_QUALQUER, True, V2)  # type: ignore[misc]


@pytest.mark.parametrize(
    "versao", ["", "propostas-v3", "Propostas-V2", "propostas-v2 ", "projeto-promovido-v1"]
)
def test_versao_invalida_levanta_value_error(
    catalogo_inicial: CatalogoTecnico, versao: str
) -> None:
    with pytest.raises(ValueError, match="versao desconhecida"):
        _ficha(_Cena(catalogo_inicial), versao)


# --- seleção em executar e repasse pelo curation_ficha ------------------------------------------


def _preparar(tmp_path: Path) -> tuple[Path, Path]:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    referencia = tmp_path / "ref.json"
    referencia.write_text(
        json.dumps(_referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())), encoding="utf-8"
    )
    return pdf, referencia


@pytest.mark.parametrize("versao", [V1, V2])
def test_executar_seleciona_a_fonte_e_repassa_a_versao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, versao: str
) -> None:
    pdf, referencia = _preparar(tmp_path)
    recebidas: list[str] = []

    def espiao(*args: Any, **kwargs: Any) -> Any:
        recebidas.append(kwargs.get("versao", V1))
        return ficha_predita_propostas(*args, **kwargs)

    monkeypatch.setattr("scripts.ficha_predita_propostas.ficha_predita_propostas", espiao)
    saida = tmp_path / "saida"

    modulo.executar(
        pdf,
        referencia,
        saida,
        native_only=True,
        runtime_directory=tmp_path / "rt",
        versao_extracao=versao,
    )

    ficha = json.loads((saida / "ficha-predita.json").read_text(encoding="utf-8"))
    assert recebidas == [versao]
    assert ficha["gerador"]["versao_extracao"] == versao
    assert validar_ficha(ficha) == []


def test_executar_v2_nao_usa_o_gerador_do_projeto_promovido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf, referencia = _preparar(tmp_path)

    def proibido(*_: Any, **__: Any) -> Any:
        raise AssertionError("v2 não devia usar ficha_predita do projeto promovido")

    monkeypatch.setattr(modulo, "ficha_predita", proibido)
    modulo.executar(
        pdf,
        referencia,
        tmp_path / "saida",
        native_only=True,
        runtime_directory=tmp_path / "rt",
        versao_extracao=V2,
    )


def test_executar_versao_desconhecida_e_recusada_antes_de_rodar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf, referencia = _preparar(tmp_path)

    def nao_deve_rodar(*_: Any, **__: Any) -> Any:
        raise AssertionError("não devia rodar")

    monkeypatch.setattr(modulo, "run_variant", nao_deve_rodar)
    with pytest.raises(ValueError, match="versao_extracao desconhecida"):
        modulo.executar(
            pdf,
            referencia,
            tmp_path / "saida",
            native_only=True,
            runtime_directory=tmp_path / "rt",
            versao_extracao="propostas-v9",
        )


def test_main_aceita_v2_e_repassa_ao_executar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[dict[str, Any]] = []

    def falso(*_: Any, **kwargs: Any) -> dict[str, Any]:
        chamadas.append(kwargs)
        return {}

    monkeypatch.setattr(modulo, "executar", falso)

    codigo = modulo.main(
        [
            str(tmp_path / "x.pdf"),
            "--referencia",
            str(tmp_path / "r.json"),
            "--saida",
            str(tmp_path / "s"),
            "--native-only",
            "--versao-extracao",
            V2,
        ]
    )

    assert codigo == 0
    assert chamadas[0]["versao_extracao"] == V2


@pytest.mark.parametrize("versao", [V1, V2])
def test_curation_ficha_repassa_a_versao_ao_executor(tmp_path: Path, versao: str) -> None:
    rodada_dir, _ = _montar(tmp_path, "rodada")
    recebidas: list[str] = []

    def executor(pdf: Path, referencia: Path, saida: Path, **opcoes: Any) -> dict[str, Any]:
        recebidas.append(opcoes["versao_extracao"])
        raise RuntimeError("interrompe a medição")

    baseline(rodada_dir, native_only=True, versao_extracao=versao, _executor=executor)

    assert recebidas
    assert set(recebidas) == {versao}
    resumo = next((rodada_dir / "fichas").glob("baseline-v*-resumo.json"))
    assert json.loads(resumo.read_text(encoding="utf-8"))["opcoes"]["versao_extracao"] == versao
