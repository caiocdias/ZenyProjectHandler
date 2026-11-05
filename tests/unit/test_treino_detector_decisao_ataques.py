"""Ataques do testador à regra de decisão do caminho de treino (spike E11, Task 3)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.treino_detector import decisao as modulo
from scripts.treino_detector.decisao import (
    Decisao,
    ResultadoCaminho,
    decidir_caminho,
    horas_estimadas_treino,
    main,
    resultado_de_relatorio,
    segundos_estimados_por_folha,
)
from scripts.treino_detector.metricas import ladrilhos_por_folha

# vazão que dá exatamente 12,0 h na carga de referência (20 000 ladrilhos x 30 épocas)
VAZAO_NO_LIMITE_DE_HORAS = 20_000 * 30 / (12.0 * 3600)


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


def _nao_ensaiado(nome: str, motivo: str = "sem relatório", **campos: Any) -> ResultadoCaminho:
    base = ResultadoCaminho(
        nome=nome,
        ensaiado=False,
        paridade_treino=False,
        exportacao_onnx=False,
        paridade_onnx=False,
        imagens_por_segundo=None,
        qualidade_ok=None,
        motivo_nao_ensaiado=motivo,
    )
    return dataclasses.replace(base, **campos)


def _decidir(
    rocm: ResultadoCaminho, cpu: ResultadoCaminho, wsl2: ResultadoCaminho | None = None
) -> Decisao:
    return decidir_caminho(rocm, wsl2 or _nao_ensaiado("wsl2"), cpu)


def _motivos(decisao: Decisao) -> dict[str, str]:
    return dict(decisao.descartados)


def _escrever(caminho: Path, conteudo: Any) -> Path:
    texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo)
    caminho.write_text(texto, encoding="utf-8")
    return caminho


# ------------------------------------------------------------------ fórmulas e premissas


def test_premissas_da_regra_sao_as_registradas_no_plano() -> None:
    assert modulo.CARGA_REFERENCIA_LADRILHOS == 20_000
    assert modulo.CARGA_REFERENCIA_EPOCAS == 30
    assert modulo.LIMITE_HORAS_TREINO == 12.0
    assert modulo.RAZAO_MINIMA_GPU_CPU == 3.0
    assert modulo.FOLHA_REFERENCIA_PX == (9933, 7016)
    assert modulo.ORCAMENTO_FOLHA_S == 60.0


def test_horas_estimadas_com_valores_exatos_e_parametros_explicitos() -> None:
    assert horas_estimadas_treino(1.0, ladrilhos=3600, epocas=1) == pytest.approx(1.0)
    assert horas_estimadas_treino(10.0, ladrilhos=36_000, epocas=2) == pytest.approx(2.0)
    assert horas_estimadas_treino(VAZAO_NO_LIMITE_DE_HORAS) == pytest.approx(12.0)


def test_horas_dobrar_vazao_divide_por_dois_e_dobrar_carga_dobra() -> None:
    base = horas_estimadas_treino(40.0)
    assert horas_estimadas_treino(80.0) == pytest.approx(base / 2)
    assert horas_estimadas_treino(40.0, ladrilhos=40_000) == pytest.approx(base * 2)
    assert horas_estimadas_treino(40.0, epocas=60) == pytest.approx(base * 2)


def test_horas_com_zero_epocas_ou_ladrilhos_e_zero() -> None:
    assert horas_estimadas_treino(10.0, epocas=0) == 0.0
    assert horas_estimadas_treino(10.0, ladrilhos=0) == 0.0


@pytest.mark.parametrize("vazao", [0.0, -0.001, -100.0])
def test_horas_rejeita_vazao_nao_positiva(vazao: float) -> None:
    with pytest.raises(ValueError, match="positiva"):
        horas_estimadas_treino(vazao)


def test_segundos_por_folha_padrao_e_875_ladrilhos_vezes_a_mediana() -> None:
    assert ladrilhos_por_folha(9933, 7016) == 875
    assert segundos_estimados_por_folha(0.1) == pytest.approx(87.5)
    assert segundos_estimados_por_folha(0.0) == 0.0


def test_segundos_por_folha_respeita_dimensoes_explicitas() -> None:
    para_320 = segundos_estimados_por_folha(2.0, largura_px=320, altura_px=320)
    maior = segundos_estimados_por_folha(2.0, largura_px=1000, altura_px=800)
    assert para_320 == pytest.approx(2.0 * ladrilhos_por_folha(320, 320))
    assert maior == pytest.approx(2.0 * ladrilhos_por_folha(1000, 800))
    assert maior > para_320


# ------------------------------------------------------------------ ramos da regra


def test_rocm_e_wsl2_ambos_viaveis_rocm_vence_e_wsl2_e_cpu_sao_preteridos() -> None:
    decisao = decidir_caminho(
        _caminho("rocm-nativo", imagens_por_segundo=300.0),
        _caminho("wsl2", imagens_por_segundo=400.0),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "rocm-nativo"
    assert _motivos(decisao) == {
        "wsl2": "viável, mas preterido por rocm-nativo",
        "cpu": "viável, mas preterido por rocm-nativo",
    }


def test_wsl2_vence_e_cpu_viavel_e_preterida_quando_rocm_nao_foi_ensaiado() -> None:
    decisao = _decidir(
        _nao_ensaiado("rocm-nativo", "sem GPU"),
        _caminho("cpu", imagens_por_segundo=50.0),
        wsl2=_caminho("wsl2", imagens_por_segundo=300.0),
    )
    assert decisao.caminho == "wsl2"
    assert _motivos(decisao)["rocm-nativo"] == "não ensaiado: sem GPU"
    assert _motivos(decisao)["cpu"] == "viável, mas preterido por wsl2"


def test_cpu_viavel_e_escolhida_quando_as_duas_gpus_falham_e_a_ordem_dos_descartados_e_fixa() -> (
    None
):
    decisao = decidir_caminho(
        _caminho("rocm-nativo", paridade_onnx=False),
        _caminho("wsl2", exportacao_onnx=False),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "cpu"
    assert [nome for nome, _ in decisao.descartados] == ["rocm-nativo", "wsl2"]


def test_gpu_alugada_lista_os_tres_caminhos_descartados_em_ordem() -> None:
    decisao = decidir_caminho(
        _nao_ensaiado("rocm-nativo", "a"), _nao_ensaiado("wsl2", "b"), _nao_ensaiado("cpu", "c")
    )
    assert decisao.caminho == "gpu-alugada"
    assert decisao.descartados == (
        ("rocm-nativo", "não ensaiado: a"),
        ("wsl2", "não ensaiado: b"),
        ("cpu", "não ensaiado: c"),
    )
    assert "GPU alugada" in decisao.motivo


def test_nome_recebido_nao_governa_o_rotulo_do_caminho() -> None:
    decisao = decidir_caminho(
        _caminho("qualquer-coisa", imagens_por_segundo=300.0),
        _nao_ensaiado("wsl2"),
        _caminho("outro", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "rocm-nativo"
    assert "cpu" in _motivos(decisao)


def test_nao_ensaiado_nunca_e_escolhido_mesmo_com_todos_os_campos_verdadeiros() -> None:
    mentiroso = _nao_ensaiado(
        "rocm-nativo",
        "recusado",
        paridade_treino=True,
        exportacao_onnx=True,
        paridade_onnx=True,
        imagens_por_segundo=1000.0,
    )
    decisao = _decidir(mentiroso, _nao_ensaiado("cpu"))
    assert decisao.caminho == "gpu-alugada"
    assert _motivos(decisao)["rocm-nativo"] == "não ensaiado: recusado"


def test_cpu_nao_ensaiada_com_vazao_preenchida_nao_conta_como_referencia_de_razao() -> None:
    # 12 img/s = 13,9 h (> 12 h); a razão 3x só valeria com cpu ensaiada de 4 img/s.
    cpu_fantasma = _nao_ensaiado("cpu", imagens_por_segundo=4.0)
    decisao = _decidir(_caminho("rocm-nativo", imagens_por_segundo=12.0), cpu_fantasma)
    assert decisao.caminho == "gpu-alugada"


def test_gpu_nao_exige_paridade_de_treino_na_cpu_nem_a_cpu_exige_na_gpu() -> None:
    # só a GPU é reprovada por falta de paridade de treino; a cpu não é.
    gpu = _decidir(
        _caminho("rocm-nativo", paridade_treino=False), _caminho("cpu", paridade_treino=False)
    )
    assert gpu.caminho == "cpu"
    assert "paridade de treino" in _motivos(gpu)["rocm-nativo"]


def test_cpu_com_erro_de_fase_e_reprovada_mesmo_com_o_resto_ok() -> None:
    decisao = _decidir(
        _nao_ensaiado("rocm-nativo"), _caminho("cpu", imagens_por_segundo=50.0, erro_fase="onnx")
    )
    assert decisao.caminho == "gpu-alugada"
    assert "erro na fase onnx" in _motivos(decisao)["cpu"]


def test_gpu_com_erro_de_fase_e_reprovada_mesmo_com_o_resto_ok() -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=300.0, erro_fase="treino"),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "cpu"
    assert "erro na fase treino" in _motivos(decisao)["rocm-nativo"]


def test_motivos_de_varias_falhas_sao_acumulados_e_nao_so_a_primeira() -> None:
    decisao = _decidir(
        _caminho(
            "rocm-nativo",
            paridade_treino=False,
            exportacao_onnx=False,
            paridade_onnx=False,
            imagens_por_segundo=300.0,
        ),
        _nao_ensaiado("cpu"),
    )
    motivo = _motivos(decisao)["rocm-nativo"]
    assert "paridade de treino" in motivo
    assert "exportação ONNX" in motivo
    assert "paridade ONNX" in motivo


# ------------------------------------------------------------------ vazão None e limites


def test_gpu_com_vazao_none_e_cpu_ok_nao_levanta_e_cita_vazao_no_motivo() -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=None), _caminho("cpu", imagens_por_segundo=50.0)
    )
    assert decisao.caminho == "cpu"
    assert "vazão" in _motivos(decisao)["rocm-nativo"]


def test_cpu_sem_vazao_e_gpu_com_horas_ok_escolhe_gpu() -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=14.0),
        _caminho("cpu", imagens_por_segundo=None),
    )
    assert decisao.caminho == "rocm-nativo"
    assert "vazão" in _motivos(decisao)["cpu"]


def test_cpu_sem_vazao_nunca_e_escolhida() -> None:
    decisao = _decidir(_nao_ensaiado("rocm-nativo"), _caminho("cpu", imagens_por_segundo=None))
    assert decisao.caminho == "gpu-alugada"


def test_razao_exatamente_3x_na_gpu_lenta_vence() -> None:
    # gpu 12 img/s = 13,9 h (> 12 h); cpu 4 img/s: razão exata 3,0 -> aceita (>=)
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=12.0), _caminho("cpu", imagens_por_segundo=4.0)
    )
    assert decisao.caminho == "rocm-nativo"
    assert "3.0x a CPU" in decisao.motivo


def test_razao_um_pouco_abaixo_de_3x_na_gpu_lenta_cai() -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=11.99), _caminho("cpu", imagens_por_segundo=4.0)
    )
    assert decisao.caminho == "gpu-alugada"
    motivo = _motivos(decisao)["rocm-nativo"]
    assert "abaixo de 3x a CPU" in motivo
    assert "12 h" in motivo


def test_horas_exatamente_12_na_gpu_sem_razao_vence() -> None:
    assert horas_estimadas_treino(VAZAO_NO_LIMITE_DE_HORAS) == 12.0
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=VAZAO_NO_LIMITE_DE_HORAS),
        _caminho("cpu", imagens_por_segundo=VAZAO_NO_LIMITE_DE_HORAS),
    )
    assert decisao.caminho == "rocm-nativo"


def test_horas_um_pouco_acima_de_12_na_gpu_sem_razao_cai() -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=13.8),
        _caminho("cpu", imagens_por_segundo=13.8),
    )
    assert decisao.caminho == "gpu-alugada"


def test_cpu_exatamente_12h_vence_e_um_pouco_acima_cai() -> None:
    no_limite = _decidir(
        _nao_ensaiado("rocm-nativo"), _caminho("cpu", imagens_por_segundo=VAZAO_NO_LIMITE_DE_HORAS)
    )
    acima = _decidir(_nao_ensaiado("rocm-nativo"), _caminho("cpu", imagens_por_segundo=13.8))
    assert no_limite.caminho == "cpu"
    assert acima.caminho == "gpu-alugada"


@pytest.mark.parametrize("vazao", [0.0, -5.0])
def test_vazao_zero_ou_negativa_no_relatorio_torna_o_caminho_inviavel_sem_excecao(
    vazao: float,
) -> None:
    # defeito: horas_estimadas_treino levanta ValueError dentro de _falhas_gpu/_falhas_cpu
    # e derruba a decisão inteira em vez de reprovar o caminho.
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=vazao),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "cpu"
    assert "rocm-nativo" in _motivos(decisao)


def test_cpu_com_vazao_zero_no_relatorio_nao_derruba_a_decisao() -> None:
    decisao = _decidir(_nao_ensaiado("rocm-nativo"), _caminho("cpu", imagens_por_segundo=0.0))
    assert decisao.caminho == "gpu-alugada"


# ------------------------------------------------------------------ motivo e ressalvas


def test_motivo_do_gpu_escolhido_traz_paridade_vazao_horas_e_razao() -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=300.0),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.motivo.startswith("paridade de treino na 1ª iteração ok")
    assert "300.0 img/s" in decisao.motivo
    assert "0.6 h" in decisao.motivo
    assert "6.0x a CPU" in decisao.motivo


def test_motivo_da_cpu_escolhida_nao_cita_razao_nem_paridade_de_treino() -> None:
    decisao = _decidir(
        _nao_ensaiado("rocm-nativo"),
        _caminho("cpu", imagens_por_segundo=20.0, paridade_treino=False),
    )
    assert "x a CPU" not in decisao.motivo
    assert "paridade de treino" not in decisao.motivo
    assert "8.3 h" in decisao.motivo


def test_qualidade_none_diz_nao_medida_e_trajetoria_none_ou_true_nao_gera_ressalva() -> None:
    for trajetoria in (None, True):
        decisao = _decidir(
            _caminho(
                "rocm-nativo",
                imagens_por_segundo=300.0,
                qualidade_ok=None,
                trajetoria_ok=trajetoria,
            ),
            _caminho("cpu", imagens_por_segundo=50.0),
        )
        assert decisao.caminho == "rocm-nativo"
        assert "qualidade não medida" in decisao.motivo
        assert "trajetória" not in decisao.motivo


def test_qualidade_boa_e_confirmada_sem_ressalva() -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=300.0, qualidade_ok=True),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert "qualidade confirmada" in decisao.motivo
    assert "ressalva" not in decisao.motivo


def test_trajetoria_divergente_nao_reprova_nem_a_primeira_iteracao_ok_some() -> None:
    decisao = _decidir(
        _caminho("rocm-nativo", imagens_por_segundo=300.0, trajetoria_ok=False),
        _caminho("cpu", imagens_por_segundo=50.0),
    )
    assert decisao.caminho == "rocm-nativo"
    assert "1ª iteração ok" in decisao.motivo
    assert "trajetória" in decisao.motivo


def test_decisao_e_resultado_sao_imutaveis_e_descartados_e_tupla_de_pares() -> None:
    decisao = _decidir(_nao_ensaiado("rocm-nativo"), _nao_ensaiado("cpu"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        decisao.caminho = "cpu"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        _caminho("cpu").ensaiado = False  # type: ignore[misc]
    assert isinstance(decisao.descartados, tuple)
    assert all(isinstance(par, tuple) and len(par) == 2 for par in decisao.descartados)


def test_decidir_nao_muda_os_resultados_recebidos() -> None:
    rocm = _caminho("nome-original", imagens_por_segundo=300.0)
    _decidir(rocm, _caminho("cpu"))
    assert rocm.nome == "nome-original"


# ------------------------------------------------------------------ resultado_de_relatorio


def test_relatorio_vazio_e_ensaiado_com_tudo_falso_e_sem_excecao(tmp_path: Path) -> None:
    resultado = resultado_de_relatorio("cpu", _escrever(tmp_path / "r.json", {}))
    assert resultado == ResultadoCaminho(
        nome="cpu",
        ensaiado=True,
        paridade_treino=False,
        exportacao_onnx=False,
        paridade_onnx=False,
        imagens_por_segundo=None,
        qualidade_ok=None,
        trajetoria_ok=None,
        erro_fase=None,
    )
    assert _decidir(resultado, resultado).caminho == "gpu-alugada"


def test_relatorio_parcial_so_com_vazao_nao_inventa_paridades(tmp_path: Path) -> None:
    resultado = resultado_de_relatorio(
        "rocm-nativo", _escrever(tmp_path / "r.json", {"imagens_por_segundo_treino": 50})
    )
    assert resultado.imagens_por_segundo == 50.0
    assert isinstance(resultado.imagens_por_segundo, float)
    assert not (resultado.exportacao_onnx or resultado.paridade_onnx or resultado.paridade_treino)


@pytest.mark.parametrize(
    "bloco",
    [{"ok": False}, {"ok": "true"}, {"ok": 1}, {"ok": None}, {}, None, "ok", ["ok"], True, 1],
)
def test_blocos_onnx_so_valem_com_ok_igual_a_true_literal(tmp_path: Path, bloco: Any) -> None:
    arquivo = _escrever(tmp_path / "r.json", {"exportacao_onnx": bloco, "paridade_onnx": bloco})
    resultado = resultado_de_relatorio("cpu", arquivo)
    assert resultado.exportacao_onnx is False
    assert resultado.paridade_onnx is False


@pytest.mark.parametrize("valor", [False, "true", 1, None, "sim"])
def test_paridade_primeira_iteracao_so_vale_com_true_literal(tmp_path: Path, valor: Any) -> None:
    arquivo = _escrever(
        tmp_path / "r.json", {"paridade_treino": {"paridade_primeira_iteracao": valor}}
    )
    assert resultado_de_relatorio("rocm-nativo", arquivo).paridade_treino is False


@pytest.mark.parametrize("bloco", ["paridade", ["paridade_primeira_iteracao"], 3, True])
def test_paridade_treino_que_nao_e_objeto_vira_falso_e_trajetoria_none(
    tmp_path: Path, bloco: Any
) -> None:
    resultado = resultado_de_relatorio(
        "rocm-nativo", _escrever(tmp_path / "r.json", {"paridade_treino": bloco})
    )
    assert resultado.paridade_treino is False
    assert resultado.trajetoria_ok is None


def test_paridade_treino_sem_trajetoria_deixa_trajetoria_none(tmp_path: Path) -> None:
    arquivo = _escrever(
        tmp_path / "r.json", {"paridade_treino": {"paridade_primeira_iteracao": True}}
    )
    resultado = resultado_de_relatorio("rocm-nativo", arquivo)
    assert resultado.paridade_treino is True
    assert resultado.trajetoria_ok is None


def test_vazao_numerica_em_texto_e_convertida_para_float(tmp_path: Path) -> None:
    resultado = resultado_de_relatorio(
        "cpu", _escrever(tmp_path / "r.json", {"imagens_por_segundo_treino": "22.5"})
    )
    assert resultado.imagens_por_segundo == 22.5


def test_vazao_nao_numerica_nao_vira_caminho_viavel(tmp_path: Path) -> None:
    arquivo = _escrever(tmp_path / "r.json", {"imagens_por_segundo_treino": "rapido"})
    with pytest.raises(ValueError):
        resultado_de_relatorio("cpu", arquivo)


def test_erro_com_fase_preenche_erro_fase_e_mensagem_sozinha_nao(tmp_path: Path) -> None:
    com_fase = resultado_de_relatorio(
        "cpu", _escrever(tmp_path / "a.json", {"erro": {"fase": "treino", "mensagem": "x"}})
    )
    assert com_fase.erro_fase == "treino"
    assert com_fase.ensaiado is True


def test_erro_sem_fase_ou_nao_objeto_nao_deixa_o_ensaio_passar_como_limpo(
    tmp_path: Path,
) -> None:
    # defeito: `erro_fase` só olha erro["fase"]; um `erro` não nulo sem fase (ou texto solto)
    # é descartado em silêncio e o caminho pode ser escolhido apesar de o ensaio ter falhado.
    completo = {
        "imagens_por_segundo_treino": 50.0,
        "exportacao_onnx": {"ok": True},
        "paridade_onnx": {"ok": True},
    }
    for erro in ({"mensagem": "RuntimeError: x"}, "RuntimeError: x"):
        arquivo = _escrever(tmp_path / "r.json", {**completo, "erro": erro})
        cpu = resultado_de_relatorio("cpu", arquivo)
        assert _decidir(_nao_ensaiado("rocm-nativo"), cpu).caminho == "gpu-alugada", erro


def test_json_malformado_levanta_erro_de_json_e_nao_vira_nao_ensaiado(tmp_path: Path) -> None:
    arquivo = _escrever(tmp_path / "r.json", '{"imagens_por_segundo_treino": 5')
    with pytest.raises(json.JSONDecodeError):
        resultado_de_relatorio("cpu", arquivo)


def test_arquivo_json_vazio_levanta_erro_de_json(tmp_path: Path) -> None:
    with pytest.raises(json.JSONDecodeError):
        resultado_de_relatorio("cpu", _escrever(tmp_path / "r.json", ""))


def test_json_de_topo_nao_objeto_nao_e_aceito_como_relatorio(tmp_path: Path) -> None:
    with pytest.raises((ValueError, TypeError, AttributeError)):
        resultado_de_relatorio("cpu", _escrever(tmp_path / "r.json", "[1, 2]"))


def test_caminho_que_e_diretorio_conta_como_ausente(tmp_path: Path) -> None:
    resultado = resultado_de_relatorio("cpu", tmp_path)
    assert resultado.ensaiado is False
    assert resultado.motivo_nao_ensaiado is not None
    assert "ausente" in resultado.motivo_nao_ensaiado


def test_motivos_de_nao_ensaiado_distinguem_none_de_arquivo_ausente(tmp_path: Path) -> None:
    sem_arquivo = tmp_path / "x.json"
    assert resultado_de_relatorio("cpu", None).motivo_nao_ensaiado == "relatório não fornecido"
    ausente = resultado_de_relatorio("cpu", sem_arquivo).motivo_nao_ensaiado
    assert ausente is not None
    assert str(sem_arquivo) in ausente
    assert "ausente" in ausente


def test_nome_passado_e_preservado_no_resultado(tmp_path: Path) -> None:
    assert resultado_de_relatorio("wsl2", None).nome == "wsl2"
    assert resultado_de_relatorio("wsl2", _escrever(tmp_path / "r.json", {})).nome == "wsl2"


# ------------------------------------------------------------------ main


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


def test_main_sem_nenhum_relatorio_decide_gpu_alugada_e_cria_pastas_da_saida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saida = tmp_path / "a" / "b" / "decisao.json"

    assert main(["--saida", str(saida)]) == 0

    gravado = json.loads(saida.read_text(encoding="utf-8"))
    assert gravado["caminho"] == "gpu-alugada"
    assert [d[0] for d in gravado["descartados"]] == ["rocm-nativo", "wsl2", "cpu"]
    assert all("relatório não fornecido" in d[1] for d in gravado["descartados"])
    assert json.loads(capsys.readouterr().out) == gravado


def test_main_arquivos_inexistentes_viram_nao_ensaiados_e_nao_levantam(tmp_path: Path) -> None:
    saida = tmp_path / "d.json"
    codigo = main(
        [
            "--rocm", str(tmp_path / "r.json"),
            "--cpu", str(tmp_path / "c.json"),
            "--saida", str(saida),
        ]
    )  # fmt: skip
    gravado = json.loads(saida.read_text(encoding="utf-8"))
    assert codigo == 0
    assert gravado["caminho"] == "gpu-alugada"
    assert all("ausente" in motivo for nome, motivo in gravado["descartados"] if nome != "wsl2")


def test_main_wsl2_omitido_aparece_como_nao_fornecido_e_nao_impede_a_decisao(
    tmp_path: Path,
) -> None:
    rocm = _escrever(tmp_path / "r.json", _relatorio_ok(300.0))
    cpu = _escrever(tmp_path / "c.json", _relatorio_ok(50.0))
    saida = tmp_path / "d.json"

    main(["--rocm", str(rocm), "--cpu", str(cpu), "--saida", str(saida)])

    gravado = json.loads(saida.read_text(encoding="utf-8"))
    assert gravado["caminho"] == "rocm-nativo"
    assert ["wsl2", "não ensaiado: relatório não fornecido"] in gravado["descartados"]


def test_main_motivo_wsl2_e_ignorado_quando_ha_relatorio_wsl2(tmp_path: Path) -> None:
    rocm = _escrever(tmp_path / "r.json", _relatorio_ok(300.0, paridade_treino=None))
    wsl2 = _escrever(tmp_path / "w.json", _relatorio_ok(300.0))
    cpu = _escrever(tmp_path / "c.json", _relatorio_ok(50.0))
    saida = tmp_path / "d.json"

    main(
        [
            "--rocm", str(rocm), "--wsl2", str(wsl2), "--cpu", str(cpu),
            "--motivo-wsl2", "nao deveria aparecer", "--saida", str(saida),
        ]
    )  # fmt: skip

    gravado = json.loads(saida.read_text(encoding="utf-8"))
    assert gravado["caminho"] == "wsl2"
    assert "nao deveria aparecer" not in json.dumps(gravado)


def test_main_so_cpu_escolhe_cpu_e_motivo_wsl2_acompanha_o_descarte(tmp_path: Path) -> None:
    cpu = _escrever(tmp_path / "c.json", _relatorio_ok(20.0, paridade_treino=None))
    saida = tmp_path / "d.json"

    main(["--cpu", str(cpu), "--motivo-wsl2", "sem distro", "--saida", str(saida)])

    gravado = json.loads(saida.read_text(encoding="utf-8"))
    assert gravado["caminho"] == "cpu"
    assert ["wsl2", "não ensaiado: sem distro"] in gravado["descartados"]


def test_main_grava_utf8_legivel_sem_escapes_e_termina_em_quebra_de_linha(
    tmp_path: Path,
) -> None:
    saida = tmp_path / "d.json"
    main(["--motivo-wsl2", "ação proibida", "--saida", str(saida)])

    bruto = saida.read_bytes().decode("utf-8")
    assert "ação proibida" in bruto
    assert "\\u" not in bruto
    assert bruto.endswith("\n")


def test_main_sobrescreve_decisao_anterior(tmp_path: Path) -> None:
    saida = _escrever(tmp_path / "d.json", "lixo " * 500)
    main(["--saida", str(saida)])
    assert json.loads(saida.read_text(encoding="utf-8"))["caminho"] == "gpu-alugada"


def test_main_sem_saida_sai_com_erro_de_uso() -> None:
    with pytest.raises(SystemExit) as erro:
        main([])
    assert erro.value.code == 2


def test_main_propaga_json_malformado_sem_gravar_a_saida(tmp_path: Path) -> None:
    rocm = _escrever(tmp_path / "r.json", "{ruim")
    saida = tmp_path / "d.json"
    with pytest.raises(json.JSONDecodeError):
        main(["--rocm", str(rocm), "--saida", str(saida)])
    assert not saida.exists()
