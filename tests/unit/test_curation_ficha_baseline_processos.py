"""``baseline`` das fichas: versão de extração, processos paralelos e separação de pendência.

Os executores falsos são funções de nível de módulo: o spawn do Windows reimporta este módulo no
processo filho e não enxerga ``monkeypatch``.
"""

from __future__ import annotations

import copy
import json
import multiprocessing
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import scripts.curation_ficha as curation_ficha
from scripts.curation_ficha import baseline, diretorio_ficha, main
from scripts.curation_round import carregar_rodada, iniciar_rodada
from scripts.ficha_poste import carregar_ficha
from scripts.ficha_poste_avaliador import avaliar
from tests.pdf_fixtures import create_network_benchmark_pdf
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica
from tests.unit.test_curation_ficha_baseline import (
    _argv,
    _congelar_referencia,
    _relatorio,
    _resumo,
)

Registro = dict[str, Any]
AGORA = "2026-10-15T12:00:00+00:00"
NOMES = ("alfa-secreto", "beta-secreto", "gama-secreto")
CAMPOS_PENDENCIA = ("identificador", "estruturas", "poste", "coordenada")
VERSAO_PROPOSTAS = "propostas-v1"


def _grava(caminho: Path, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, sort_keys=True), encoding="utf-8")


def _executor_sintetico(
    pdf: Path,
    referencia: Path,
    saida: Path,
    *,
    native_only: bool,
    runtime_directory: Path,
    versao_extracao: str,
) -> Registro:
    """Grava ``ficha-predita.json`` e devolve uma avaliação que depende do nome do PDF."""
    _grava(saida / "ficha-predita.json", {"postes": [], "versao_extracao": versao_extracao})
    relatorio = _relatorio(1 + sum(map(ord, pdf.stem)) % 3, 0, 0, [0.01])
    _grava(saida / "avaliacao.json", relatorio)
    return relatorio


def _executor_falha_num_pdf(
    pdf: Path,
    referencia: Path,
    saida: Path,
    *,
    native_only: bool,
    runtime_directory: Path,
    versao_extracao: str,
) -> Registro:
    if pdf.stem == "beta-secreto":
        raise RuntimeError(f"nao abriu {pdf}")
    return _executor_sintetico(
        pdf,
        referencia,
        saida,
        native_only=native_only,
        runtime_directory=runtime_directory,
        versao_extracao=versao_extracao,
    )


def _executor_derruba_o_processo(
    pdf: Path,
    referencia: Path,
    saida: Path,
    *,
    native_only: bool,
    runtime_directory: Path,
    versao_extracao: str,
) -> Registro:
    if pdf.stem == "beta-secreto" and multiprocessing.parent_process() is not None:
        os._exit(1)
    return _executor_sintetico(
        pdf,
        referencia,
        saida,
        native_only=native_only,
        runtime_directory=runtime_directory,
        versao_extracao=versao_extracao,
    )


def _executor_sem_ficha(pdf: Path, referencia: Path, saida: Path, **_: Any) -> Registro:
    """Formato dos executores dos testes existentes: ``pares`` só com distância, sem ficha."""
    return _relatorio(1, 0, 0, [0.1])


def _executor_com_pendencia(pdf: Path, referencia: Path, saida: Path, **_: Any) -> Registro:
    """Dois postes de mesmo identificador; a 2ª predição declara o identificador pendente."""
    ref = carregar_ficha(referencia)
    for poste in ref["postes"]:
        poste["identificador"] = "P1"
    predita = copy.deepcopy(ref)
    predita["tipo"] = "predicao"
    predita["gerador"] = {"versao_extracao": "propostas-v1"}
    renomeados = {"r1": "p1", "r2": "p2"}
    for poste in predita["postes"]:
        poste["id"] = renomeados[poste["id"]]
    predita["postes"][1]["pendentes"] = ["identificador"]
    for vao in predita["vaos"]:
        vao["de"], vao["para"] = renomeados[vao["de"]], renomeados[vao["para"]]
    _grava(saida / "ficha-predita.json", predita)
    return avaliar(ref, predita)


def _montar(tmp_path: Path, nome_rodada: str) -> tuple[Path, list[str]]:
    corpus = tmp_path / "corpus"
    corpus.mkdir(exist_ok=True)
    pdfs = [create_network_benchmark_pdf(corpus / f"{nome}.pdf") for nome in NOMES]
    rodada_dir = tmp_path / nome_rodada
    iniciar_rodada(
        rodada_dir, corpus, concorrencia=3, raiz_repositorio=tmp_path / "sem-git", agora=AGORA
    )
    ids = [str(e["pdf_id"]) for e in carregar_rodada(rodada_dir)["pdfs"]]
    assert len(ids) == len(NOMES)
    for pdf_id, pdf in zip(ids, sorted(pdfs), strict=True):
        _congelar_referencia(
            rodada_dir, pdf_id, _referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())
        )
    return rodada_dir, ids


@pytest.fixture
def rodada(tmp_path: Path) -> tuple[Path, list[str]]:
    return _montar(tmp_path, "rodada")


def _sem_ids(resumo: Registro, ids: list[str]) -> str:
    """O id do PDF muda de uma rodada para outra; troca por posição para comparar os resumos."""
    texto = json.dumps(resumo, sort_keys=True)
    for posicao, pdf_id in enumerate(ids):
        texto = texto.replace(pdf_id, f"pdf-{posicao}")
    return texto


def _avaliacoes(rodada_dir: Path, ids: list[str], versao: str = "baseline-v001") -> list[bytes]:
    return [(diretorio_ficha(rodada_dir, i) / versao / "avaliacao.json").read_bytes() for i in ids]


def test_versao_extracao_e_repassada(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, _ = rodada
    recebidas: list[str] = []

    def espiao(pdf: Path, referencia: Path, saida: Path, **kwargs: Any) -> Registro:
        recebidas.append(kwargs["versao_extracao"])
        return _relatorio(1, 0, 0, [0.1])

    resumo = baseline(
        rodada_dir, native_only=True, versao_extracao=VERSAO_PROPOSTAS, _executor=espiao
    )
    assert recebidas == [VERSAO_PROPOSTAS] * len(NOMES)
    assert resumo["opcoes"]["versao_extracao"] == VERSAO_PROPOSTAS
    assert set(resumo["opcoes"]) == {"native_only", "pdfs", "versao_extracao"}


def test_processos_4_produz_o_mesmo_resumo_que_a_serial(tmp_path: Path) -> None:
    serial_dir, ids_serial = _montar(tmp_path, "serial")
    paralela_dir, ids_paralela = _montar(tmp_path, "paralela")
    baseline(serial_dir, native_only=True, _executor=_executor_sintetico)
    baseline(paralela_dir, native_only=True, processos=4, _executor=_executor_sintetico)

    serial = _resumo(serial_dir, "baseline-v001")
    paralela = _resumo(paralela_dir, "baseline-v001")
    assert _sem_ids(serial, ids_serial) == _sem_ids(paralela, ids_paralela)
    assert _avaliacoes(serial_dir, ids_serial) == _avaliacoes(paralela_dir, ids_paralela)
    assert len({*_avaliacoes(serial_dir, ids_serial)}) > 1


def test_processos_com_falha_num_pdf(tmp_path: Path) -> None:
    serial_dir, ids_serial = _montar(tmp_path, "serial")
    paralela_dir, ids = _montar(tmp_path, "paralela")
    baseline(serial_dir, native_only=True, _executor=_executor_falha_num_pdf)
    baseline(paralela_dir, native_only=True, processos=4, _executor=_executor_falha_num_pdf)

    serial, paralela = _resumo(serial_dir, "baseline-v001"), _resumo(paralela_dir, "baseline-v001")
    assert _sem_ids(serial, ids_serial) == _sem_ids(paralela, ids)
    falhas = [i for i in ids if paralela["por_pdf"][i].get("situacao") == "falha"]
    assert len(falhas) == 1
    assert str(tmp_path) not in json.dumps(paralela)
    assert "beta-secreto" not in json.dumps(paralela)
    assert paralela["total"]["postes"]["tp"] > 0


def test_pool_quebrado_grava_resumo_com_falha(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, ids = rodada
    resumo = baseline(
        rodada_dir, native_only=True, processos=3, _executor=_executor_derruba_o_processo
    )

    gravado = _resumo(rodada_dir, "baseline-v001")
    assert gravado == resumo
    assert (rodada_dir / "fichas" / "baseline-v001-resumo.md").is_file()
    falhas = [i for i in ids if gravado["por_pdf"][i].get("situacao") == "falha"]
    assert falhas, "o PDF que derrubou o processo precisa aparecer como falha"
    assert all("erro" in gravado["por_pdf"][i] for i in falhas)
    assert str(rodada_dir.parent) not in json.dumps(gravado)


def test_pendencia_separa_afirmado_de_pendente(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, ids = rodada
    resumo = baseline(
        rodada_dir, (ids[0],), native_only=True, parcial=True, _executor=_executor_com_pendencia
    )
    pendencia = resumo["pendencia"]
    assert pendencia["total"]["identificador"] == {
        "acertos_afirmados": 1,
        "acertos_com_pendencia": 1,
    }
    assert set(pendencia["total"]) == set(CAMPOS_PENDENCIA)
    assert pendencia["por_pdf"][ids[0]] == pendencia["total"]
    # O campo "poste" também acerta nos dois, e nenhum está declarado pendente.
    assert pendencia["total"]["poste"] == {"acertos_afirmados": 2, "acertos_com_pendencia": 0}


def test_pendencia_tolera_relatorio_sem_pares_completos(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, _ = rodada
    resumo = baseline(rodada_dir, native_only=True, _executor=_executor_sem_ficha)
    zerado = {"acertos_afirmados": 0, "acertos_com_pendencia": 0}
    assert resumo["pendencia"]["total"] == dict.fromkeys(CAMPOS_PENDENCIA, zerado)
    assert resumo["pendencia"]["por_pdf"] == {}


def test_main_sem_o_executor_privado_continua_saindo_0(
    rodada: tuple[Path, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    rodada_dir, _ = rodada
    monkeypatch.setattr(curation_ficha, "executar_benchmark", _executor_sem_ficha)
    assert main(_argv(rodada_dir, "--native-only", "--versao-extracao", VERSAO_PROPOSTAS)) == 0
    assert _resumo(rodada_dir, "baseline-v001")["opcoes"]["versao_extracao"] == VERSAO_PROPOSTAS


@pytest.mark.parametrize("valor", ["0", "-2"])
def test_processos_invalido_e_recusado(rodada: tuple[Path, list[str]], valor: str) -> None:
    rodada_dir, _ = rodada
    with pytest.raises(SystemExit) as saida:
        main(_argv(rodada_dir, "--native-only", "--processos", valor))
    assert saida.value.code == 2


def test_versao_extracao_desconhecida_e_recusada(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, _ = rodada
    with pytest.raises(SystemExit) as saida:
        main(_argv(rodada_dir, "--native-only", "--versao-extracao", "inexistente-v9"))
    assert saida.value.code == 2


def test_markdown_traz_versao_e_pendencia(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, _ = rodada
    baseline(
        rodada_dir,
        native_only=True,
        versao_extracao=VERSAO_PROPOSTAS,
        processos=4,
        _executor=_executor_sintetico,
    )
    texto = (rodada_dir / "fichas" / "baseline-v001-resumo.md").read_text("utf-8")
    assert f"Versão de extração: {VERSAO_PROPOSTAS}" in texto
    assert "Processos: 4 (efetivos: 3)" in texto
    assert "## Acertos afirmados e com pendência (total)" in texto
    assert "Vãos e símbolos: sem separação de pendência." in texto
    assert "processos" not in json.dumps(_resumo(rodada_dir, "baseline-v001"))


def test_markdown_serial_declara_um_processo(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, _ = rodada
    baseline(rodada_dir, native_only=True, _executor=_executor_sintetico)
    texto = (rodada_dir / "fichas" / "baseline-v001-resumo.md").read_text("utf-8")
    assert "Processos: 1 (efetivos: 1)" in texto
    assert "Versão de extração: projeto-promovido-v1" in texto


def test_processos_acima_de_61_sao_limitados(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, _ = rodada
    baseline(rodada_dir, native_only=True, processos=200, _executor=_executor_sintetico)
    texto = (rodada_dir / "fichas" / "baseline-v001-resumo.md").read_text("utf-8")
    assert "Processos: 200 (efetivos: 3)" in texto


def test_cli_aceita_processos_positivo_e_usa_o_padrao_serial(tmp_path: Path) -> None:
    base = ["baseline", "--rodada", str(tmp_path)]
    parser = curation_ficha._parser()
    assert parser.parse_args([*base, "--processos", "2"]).processos == 2
    padrao = parser.parse_args(base)
    assert padrao.processos == 1
    assert padrao.versao_extracao == "projeto-promovido-v1"
