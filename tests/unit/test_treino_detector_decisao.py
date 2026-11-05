"""Regra de decisão do caminho de treino do detector (spike E11)."""

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
    horas_estimadas_treino,
    main,
    resultado_de_relatorio,
    segundos_estimados_por_folha,
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


def _nao_ensaiado(nome: str, motivo: str = "sem relatório") -> ResultadoCaminho:
    return ResultadoCaminho(
        nome=nome,
        ensaiado=False,
        paridade_treino=False,
        exportacao_onnx=False,
        paridade_onnx=False,
        imagens_por_segundo=None,
        qualidade_ok=None,
        motivo_nao_ensaiado=motivo,
    )


def _descartado(decisao: Decisao, caminho: str) -> str:
    motivos = dict(decisao.descartados)
    assert caminho in motivos
    return motivos[caminho]


def test_horas_e_folha() -> None:
    assert horas_estimadas_treino(100.0) == pytest.approx(20_000 * 30 / 100 / 3600)
    with pytest.raises(ValueError):
        horas_estimadas_treino(0.0)
    with pytest.raises(ValueError):
        horas_estimadas_treino(-1.0)
    assert segundos_estimados_por_folha(0.02) == pytest.approx(0.02 * 875)


def test_rocm_vence_com_paridades_e_vazao_3x() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", imagens_por_segundo=300.0),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=50.0, paridade_treino=False),
    )
    assert decisao.caminho == "rocm-nativo"
    assert {nome for nome, _ in decisao.descartados} == {"wsl2", "cpu"}


def test_rocm_abaixo_de_3x_mas_dentro_de_12h_vence() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", imagens_por_segundo=100.0),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=60.0),
    )
    assert decisao.caminho == "rocm-nativo"


def test_rocm_abaixo_de_3x_e_acima_de_12h_cai() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", imagens_por_segundo=10.0),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=5.0),
    )
    assert decisao.caminho == "gpu-alugada"
    assert "12 h" in _descartado(decisao, "rocm-nativo")


def test_rocm_sem_vazao_da_cpu_vale_so_o_criterio_de_horas() -> None:
    cpu_sem_vazao = _caminho("cpu", imagens_por_segundo=None, erro_fase="treino")
    assert (
        decidir_caminho(
            _caminho("rocm-nativo", imagens_por_segundo=20.0), _nao_ensaiado("wsl2"), cpu_sem_vazao
        ).caminho
        == "rocm-nativo"
    )
    assert (
        decidir_caminho(
            _caminho("rocm-nativo", imagens_por_segundo=10.0), _nao_ensaiado("wsl2"), cpu_sem_vazao
        ).caminho
        == "gpu-alugada"
    )


def test_rocm_sem_paridade_de_treino_cai() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", imagens_por_segundo=300.0, paridade_treino=False),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "cpu"
    assert "paridade de treino" in _descartado(decisao, "rocm-nativo")


@pytest.mark.parametrize(
    ("campo", "trecho"),
    [("exportacao_onnx", "exportação ONNX"), ("paridade_onnx", "paridade ONNX")],
)
def test_rocm_sem_exportacao_ou_paridade_onnx_cai(campo: str, trecho: str) -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", imagens_por_segundo=300.0, **{campo: False}),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=5.0),
    )
    assert decisao.caminho == "gpu-alugada"
    assert trecho in _descartado(decisao, "rocm-nativo")


def test_rocm_qualidade_ruim_nao_reprova_mas_aparece_no_motivo() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", imagens_por_segundo=300.0, qualidade_ok=False),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "rocm-nativo"
    assert "qualidade" in decisao.motivo
    assert "ressalva" in decisao.motivo


def test_wsl2_nao_ensaiado_nunca_e_escolhido() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", paridade_treino=False),
        _nao_ensaiado("wsl2", "sonda recusada"),
        _caminho("cpu", imagens_por_segundo=5.0),
    )
    assert decisao.caminho == "gpu-alugada"
    assert ("wsl2", "não ensaiado: sonda recusada") in decisao.descartados


def test_wsl2_ensaiado_e_viavel_vence_quando_rocm_cai() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", paridade_treino=False),
        _caminho("wsl2", imagens_por_segundo=300.0),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "wsl2"


def test_cpu_dentro_de_12h_vence_sem_gpu() -> None:
    decisao = decidir_caminho(
        _nao_ensaiado("rocm-nativo"),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=20.0, paridade_treino=False),
    )
    assert decisao.caminho == "cpu"
    assert _descartado(decisao, "rocm-nativo").startswith("não ensaiado")


def test_cpu_acima_de_12h_vira_gpu_alugada() -> None:
    decisao = decidir_caminho(
        _nao_ensaiado("rocm-nativo"),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=5.0),
    )
    assert decisao.caminho == "gpu-alugada"
    assert "12 h" in _descartado(decisao, "cpu")


def test_cpu_sem_paridade_onnx_vira_gpu_alugada() -> None:
    decisao = decidir_caminho(
        _nao_ensaiado("rocm-nativo"),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=50.0, paridade_onnx=False),
    )
    assert decisao.caminho == "gpu-alugada"
    assert "paridade ONNX" in _descartado(decisao, "cpu")


def test_resultado_de_relatorio_ausente_e_nao_ensaiado(tmp_path: Path) -> None:
    for relatorio in (None, tmp_path / "nao-existe.json"):
        resultado = resultado_de_relatorio("wsl2", relatorio)
        assert resultado.ensaiado is False
        assert resultado.imagens_por_segundo is None
        assert resultado.motivo_nao_ensaiado


def _relatorio(**campos: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "imagens_por_segundo_treino": 123.5,
        "qualidade_ok": False,
        "paridade_treino": {"paridade_primeira_iteracao": True, "trajetoria_equivalente": False},
        "exportacao_onnx": {"ok": True, "exportador": "dynamo", "opset": 18},
        "paridade_onnx": {"ok": True, "imagens": 20, "divergentes": 0},
        "erro": None,
    }
    base.update(campos)
    return base


def test_resultado_de_relatorio_le_campos(tmp_path: Path) -> None:
    arquivo = tmp_path / "relatorio.json"
    arquivo.write_text(json.dumps(_relatorio()), encoding="utf-8")

    assert resultado_de_relatorio("rocm-nativo", arquivo) == ResultadoCaminho(
        nome="rocm-nativo",
        ensaiado=True,
        paridade_treino=True,
        exportacao_onnx=True,
        paridade_onnx=True,
        imagens_por_segundo=123.5,
        qualidade_ok=False,
        trajetoria_ok=False,
    )


def test_resultado_de_relatorio_sem_paridade_de_treino(tmp_path: Path) -> None:
    arquivo = tmp_path / "relatorio.json"
    arquivo.write_text(json.dumps(_relatorio(paridade_treino=None)), encoding="utf-8")

    resultado = resultado_de_relatorio("cpu", arquivo)
    assert resultado.paridade_treino is False
    assert resultado.trajetoria_ok is None


def test_relatorio_com_erro_e_ensaiado_e_nao_escolhido(tmp_path: Path) -> None:
    arquivo = tmp_path / "relatorio.json"
    arquivo.write_text(
        json.dumps(
            _relatorio(
                exportacao_onnx={"ok": False, "erro": "falhou"},
                paridade_onnx=None,
                erro={"fase": "exportacao", "mensagem": "RuntimeError: x"},
            )
        ),
        encoding="utf-8",
    )
    rocm = resultado_de_relatorio("rocm-nativo", arquivo)
    assert rocm.ensaiado is True
    assert rocm.erro_fase == "exportacao"
    assert rocm.paridade_onnx is False

    decisao = decidir_caminho(rocm, _nao_ensaiado("wsl2"), _caminho("cpu", imagens_por_segundo=5.0))
    assert decisao.caminho == "gpu-alugada"
    assert "exportacao" in _descartado(decisao, "rocm-nativo")


def test_vazao_ausente_torna_caminho_inviavel() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", imagens_por_segundo=None),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=None),
    )
    assert decisao.caminho == "gpu-alugada"
    assert "vazão" in _descartado(decisao, "rocm-nativo")
    assert "vazão" in _descartado(decisao, "cpu")


def test_trajetoria_divergente_com_primeira_iteracao_ok_e_ressalva() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", imagens_por_segundo=300.0, trajetoria_ok=False),
        _nao_ensaiado("wsl2"),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "rocm-nativo"
    assert "trajetória" in decisao.motivo


def test_main_grava_decisao(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rocm = tmp_path / "rocm.json"
    rocm.write_text(json.dumps(_relatorio(imagens_por_segundo_treino=300.0)), encoding="utf-8")
    cpu = tmp_path / "cpu.json"
    cpu.write_text(
        json.dumps(_relatorio(imagens_por_segundo_treino=50.0, paridade_treino=None)),
        encoding="utf-8",
    )
    saida = tmp_path / "decisao.json"

    codigo = main(
        [
            "--rocm",
            str(rocm),
            "--cpu",
            str(cpu),
            "--motivo-wsl2",
            "sonda recusada",
            "--saida",
            str(saida),
        ]
    )

    assert codigo == 0
    gravado = json.loads(saida.read_text(encoding="utf-8"))
    assert gravado["caminho"] == "rocm-nativo"
    assert ["wsl2", "não ensaiado: sonda recusada"] in gravado["descartados"]
    assert json.loads(capsys.readouterr().out) == gravado
