"""Re-teste da regra de decisão após a correção de vazão inválida e de `erro` (E11, Task 3)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.treino_detector.decisao import (
    Decisao,
    ResultadoCaminho,
    decidir_caminho,
    main,
    resultado_de_relatorio,
)


def _caminho(nome: str, **campos: Any) -> ResultadoCaminho:
    base = ResultadoCaminho(
        nome=nome,
        ensaiado=True,
        paridade_treino=True,
        exportacao_onnx=True,
        paridade_onnx=True,
        imagens_por_segundo=100.0,
        qualidade_ok=True,
        trajetoria_ok=True,
    )
    return dataclasses.replace(base, **campos)


def _nao_ensaiado(nome: str) -> ResultadoCaminho:
    return ResultadoCaminho(
        nome=nome,
        ensaiado=False,
        paridade_treino=False,
        exportacao_onnx=False,
        paridade_onnx=False,
        imagens_por_segundo=None,
        qualidade_ok=None,
        motivo_nao_ensaiado="sem relatório",
    )


def _decidir(rocm: ResultadoCaminho, cpu: ResultadoCaminho) -> Decisao:
    return decidir_caminho(rocm, _nao_ensaiado("wsl2"), cpu)


def _motivos(decisao: Decisao) -> dict[str, str]:
    return dict(decisao.descartados)


def _escrever(caminho: Path, conteudo: Any) -> Path:
    texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo)
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _relatorio_ok(vazao: float, **extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "imagens_por_segundo_treino": vazao,
        "qualidade_ok": True,
        "paridade_treino": {"paridade_primeira_iteracao": True, "trajetoria_equivalente": True},
        "exportacao_onnx": {"ok": True},
        "paridade_onnx": {"ok": True},
        "erro": None,
    }
    base.update(extra)
    return base


@pytest.mark.parametrize("vazao", [5e-324, 1e-300, 1e-9])
def test_vazao_positiva_minuscula_reprova_por_horas_sem_excecao(vazao: float) -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=vazao),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "cpu"
    assert "12 h" in _motivos(decisao)["rocm-nativo"]


def test_cpu_com_vazao_positiva_minuscula_e_inviavel_por_horas() -> None:
    decisao = _decidir(_nao_ensaiado("rocm-nativo"), _caminho("cpu", imagens_por_segundo=5e-324))
    assert decisao.caminho == "gpu-alugada"
    assert "12 h" in _motivos(decisao)["cpu"]


@pytest.mark.parametrize("vazao", [float("nan"), float("-inf")])
def test_vazao_nan_ou_menos_infinito_torna_o_caminho_inviavel(vazao: float) -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=vazao),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "cpu"
    assert "vazão de treino inválida" in _motivos(decisao)["rocm-nativo"]


def test_vazao_infinita_nao_e_medida_confiavel_e_nao_escolhe_caminho() -> None:
    # inf passa em `> 0` e daria 0 h na carga de referência; medição infinita é inválida.
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=float("inf")),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "cpu"


def test_relatorio_json_com_nan_nao_derruba_a_decisao(tmp_path: Path) -> None:
    rocm = _escrever(tmp_path / "r.json", '{"imagens_por_segundo_treino": NaN}')
    cpu = _escrever(tmp_path / "c.json", _relatorio_ok(50.0))
    saida = tmp_path / "d.json"

    assert main(["--rocm", str(rocm), "--cpu", str(cpu), "--saida", str(saida)]) == 0
    assert json.loads(saida.read_text(encoding="utf-8"))["caminho"] == "cpu"


@pytest.mark.parametrize("erro", [["falhou"], 7, 1.5, True, {"fase": None}, {"fase": ""}])
def test_erro_em_qualquer_forma_nao_vazia_conta_como_fase_desconhecida(
    tmp_path: Path, erro: Any
) -> None:
    arquivo = _escrever(tmp_path / "r.json", _relatorio_ok(50.0, erro=erro))
    cpu = resultado_de_relatorio("cpu", arquivo)

    assert cpu.erro_fase == "desconhecida"
    decisao = _decidir(_nao_ensaiado("rocm-nativo"), cpu)
    assert decisao.caminho == "gpu-alugada"
    assert "erro na fase desconhecida" in _motivos(decisao)["cpu"]


def test_erro_com_fase_numerica_vira_texto(tmp_path: Path) -> None:
    arquivo = _escrever(tmp_path / "r.json", _relatorio_ok(50.0, erro={"fase": 3}))
    assert resultado_de_relatorio("cpu", arquivo).erro_fase == "3"


def test_erro_null_ou_ausente_nao_gera_fase(tmp_path: Path) -> None:
    sem_chave = {k: v for k, v in _relatorio_ok(50.0).items() if k != "erro"}
    for relatorio in (_relatorio_ok(50.0), sem_chave):
        arquivo = _escrever(tmp_path / "r.json", relatorio)
        assert resultado_de_relatorio("cpu", arquivo).erro_fase is None


@pytest.mark.parametrize("vazao_cpu", [0.0, -3.0, float("nan")])
def test_cpu_com_vazao_invalida_nao_serve_de_referencia_para_a_razao(vazao_cpu: float) -> None:
    # gpu 12 img/s = 13,9 h (> 12 h): só a razão 3x poderia salvá-la; com cpu inválida não vale.
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=12.0),
        _caminho("cpu", imagens_por_segundo=vazao_cpu),
    )
    assert decisao.caminho == "gpu-alugada"
    assert "12 h" in _motivos(decisao)["rocm-nativo"]
    assert "vazão de treino inválida" in _motivos(decisao)["cpu"]


def test_cpu_valida_continua_servindo_de_referencia_apos_a_correcao() -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=12.0),
        _caminho("cpu", imagens_por_segundo=4.0),
    )
    assert decisao.caminho == "rocm-nativo"


def test_motivo_de_vazao_invalida_cita_o_valor_recebido() -> None:
    decisao = _decidir(_caminho("rocm-nativo", imagens_por_segundo=-5.0), _nao_ensaiado("cpu"))
    assert "-5" in _motivos(decisao)["rocm-nativo"]
