"""Ataques ao ``baseline`` das fichas com processos, versão de extração e pendência (E15 Task 2).

Os executores falsos são funções de nível de módulo (o spawn do Windows reimporta este módulo no
filho e não enxerga ``monkeypatch``); as variações passam por ``functools.partial``, que é
picklável. O pool é trocado por um espião em thread só onde o teste precisa contar ``max_workers``.
"""

from __future__ import annotations

import copy
import functools
import json
import multiprocessing
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from typing import Any, ClassVar

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
CAMPOS = ("identificador", "estruturas", "poste", "coordenada")
FALHA_DO_POOL = "processo de medição interrompido"
ZERO = {"acertos_afirmados": 0, "acertos_com_pendencia": 0}


# --- executores falsos (nível de módulo) --------------------------------------------------------


def _grava(caminho: Path, dados: Any) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, sort_keys=True), encoding="utf-8")


def _predita_copia_da_referencia(referencia: Path) -> tuple[Registro, Registro]:
    """Referência carregada e predição idêntica a ela (ids ``p1``/``p2``), sem pendência."""
    ref = carregar_ficha(referencia)
    predita = copy.deepcopy(ref)
    predita["tipo"] = "predicao"
    predita["gerador"] = {"versao_extracao": "propostas-v1"}
    renomeados = {"r1": "p1", "r2": "p2"}
    for poste in predita["postes"]:
        poste["id"] = renomeados[poste["id"]]
    for vao in predita["vaos"]:
        vao["de"], vao["para"] = renomeados[vao["de"]], renomeados[vao["para"]]
    return ref, predita


def _executor_simples(pdf: Path, referencia: Path, saida: Path, **_: Any) -> Registro:
    relatorio = _relatorio(1 + sum(map(ord, pdf.stem)) % 3, 0, 0, [0.01])
    _grava(saida / "avaliacao.json", relatorio)
    return relatorio


def _executor_pendencia_mista(pdf: Path, referencia: Path, saida: Path, **_: Any) -> Registro:
    """alfa: p2 declara os 4 campos pendentes; beta: p1 erra o identificador (pendente) e p2
    declara só ``estruturas``; gama: não grava ``ficha-predita.json``."""
    ref, predita = _predita_copia_da_referencia(referencia)
    if pdf.stem == "alfa-secreto":
        predita["postes"][1]["pendentes"] = list(CAMPOS)
    elif pdf.stem == "beta-secreto":
        predita["postes"][0]["identificador"] = "ERRADO"
        predita["postes"][0]["pendentes"] = ["identificador"]
        predita["postes"][1]["pendentes"] = ["estruturas"]
    if pdf.stem != "gama-secreto":
        _grava(saida / "ficha-predita.json", predita)
    return avaliar(ref, predita)


def _executor_derruba(pdf: Path, referencia: Path, saida: Path, *, alvo: str, **_: Any) -> Registro:
    if pdf.stem == alvo and multiprocessing.parent_process() is not None:
        os._exit(1)
    return _executor_simples(pdf, referencia, saida)


def _executor_que_cita(
    pdf: Path, referencia: Path, saida: Path, *, forma: str, runtime_directory: Path, **_: Any
) -> Registro:
    citados = {
        "referencia": str(referencia),
        "referencia_posix": referencia.as_posix(),
        "saida": str(saida),
        "saida_posix": saida.as_posix(),
        "runtime": str(runtime_directory),
        "runtime_posix": runtime_directory.as_posix(),
        "pdf_pai": str(pdf.parent),
        "pdf_irmao": str(pdf.parent / "outro.pdf"),
        "fora_do_corpus": str(pdf.parent.parent / "estranho" / "dado.bin"),
        "fora_do_corpus_posix": (pdf.parent.parent / "estranho" / "dado.bin").as_posix(),
    }
    if forma == "oserror":
        with open(pdf.parent / "nao-existe.bin", "rb"):
            pass
    if forma == "todas":
        raise RuntimeError("falha em " + " e ".join(citados.values()))
    raise RuntimeError(f"falha em {citados[forma]}")


def _executor_ficha_com_conteudo(
    pdf: Path, referencia: Path, saida: Path, *, conteudo: str, **_: Any
) -> Registro:
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "ficha-predita.json").write_text(conteudo, encoding="utf-8")
    return _executor_simples(pdf, referencia, saida)


def _pares_hostis() -> list[Registro]:
    tudo = dict.fromkeys(CAMPOS, True)
    sem_nada = dict.fromkeys(CAMPOS, None)
    base = {"distancia": 0.0}
    return [
        {**base, "predicao": "p1"},  # sem campos
        {**base, "predicao": "p1", "campos": None},
        {**base, "predicao": "p1", "campos": ["x"]},
        {**base, "campos": tudo},  # sem predicao
        {**base, "predicao": None, "campos": tudo},
        {**base, "predicao": "fantasma", "campos": tudo},  # sem id correspondente na ficha
        {  # o único válido: identificador e poste certos, estruturas errada, coordenada pendente
            **base,
            "predicao": "p1",
            "campos": {
                "identificador": True,
                "estruturas": False,
                "poste": True,
                "coordenada": None,
            },
        },
        {**base, "predicao": "p2", "campos": sem_nada},  # tudo pendente na referência
    ]


def _executor_pares_hostis(pdf: Path, referencia: Path, saida: Path, **_: Any) -> Registro:
    postes = [{"id": "p1", "pendentes": ["poste"]}, {"id": "p2", "pendentes": []}]
    _grava(saida / "ficha-predita.json", {"postes": postes})
    relatorio = _relatorio(1, 0, 0, [0.0])
    relatorio["pares"] = _pares_hostis()
    return relatorio


def _executor_referencia_pendente(pdf: Path, referencia: Path, saida: Path, **_: Any) -> Registro:
    """O identificador do p1 é pendente na referência (e na predição): fica fora da conta."""
    ref, predita = _predita_copia_da_referencia(referencia)
    ref["postes"][0]["pendentes"] = ["identificador"]
    predita["postes"][0]["pendentes"] = ["identificador"]
    predita["postes"][1]["pendentes"] = ["identificador"]
    _grava(saida / "ficha-predita.json", predita)
    return avaliar(ref, predita)


# --- montagem -----------------------------------------------------------------------------------


def _montar(
    tmp_path: Path, nome_rodada: str, nomes: tuple[str, ...] = NOMES
) -> tuple[Path, list[str]]:
    corpus = tmp_path / "corpus"
    corpus.mkdir(exist_ok=True)
    pdfs = [create_network_benchmark_pdf(corpus / f"{nome}.pdf") for nome in nomes]
    rodada_dir = tmp_path / nome_rodada
    iniciar_rodada(
        rodada_dir, corpus, concorrencia=3, raiz_repositorio=tmp_path / "sem-git", agora=AGORA
    )
    ids = [str(e["pdf_id"]) for e in carregar_rodada(rodada_dir)["pdfs"]]
    assert len(ids) == len(nomes)
    for pdf_id, pdf in zip(ids, sorted(pdfs), strict=True):
        _congelar_referencia(
            rodada_dir, pdf_id, _referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())
        )
    return rodada_dir, ids


@pytest.fixture
def rodada(tmp_path: Path) -> tuple[Path, list[str]]:
    return _montar(tmp_path, "rodada")


def _texto(rodada_dir: Path, versao: str, sufixo: str = "json") -> str:
    return (rodada_dir / "fichas" / f"{versao}-resumo.{sufixo}").read_text("utf-8")


def _baselines_gravados(rodada_dir: Path, ids: list[str]) -> list[Path]:
    """Resumos e pastas ``baseline-v*`` (por PDF) existentes na rodada."""
    achados = list((rodada_dir / "fichas").glob("baseline-v*"))
    for pdf_id in ids:
        achados += list(diretorio_ficha(rodada_dir, pdf_id).glob("baseline-v*"))
    return achados


def _como_v001(texto: str) -> str:
    return texto.replace("baseline-v002", "baseline-v001")


class _PoolEspiao(ThreadPoolExecutor):
    """Troca o ``ProcessPoolExecutor``: registra ``max_workers`` e roda em thread."""

    criados: ClassVar[list[int | None]] = []

    def __init__(self, max_workers: int | None = None, **_: Any) -> None:
        _PoolEspiao.criados.append(max_workers)
        super().__init__(max_workers=min(max_workers or 1, 4))


@pytest.fixture
def espiao(monkeypatch: pytest.MonkeyPatch) -> type[_PoolEspiao]:
    _PoolEspiao.criados = []
    monkeypatch.setattr(curation_ficha, "ProcessPoolExecutor", _PoolEspiao)
    return _PoolEspiao


# --- igualdade serial x paralelo ----------------------------------------------------------------


def test_json_bruto_serial_e_paralelo_sao_identicos_byte_a_byte(
    rodada: tuple[Path, list[str]],
) -> None:
    rodada_dir, _ = rodada
    baseline(rodada_dir, native_only=True, _executor=_executor_pendencia_mista)
    baseline(rodada_dir, native_only=True, processos=3, _executor=_executor_pendencia_mista)
    assert _como_v001(_texto(rodada_dir, "baseline-v002")) == _texto(rodada_dir, "baseline-v001")


def test_dois_pdfs_em_pool_igual_ao_serial(tmp_path: Path) -> None:
    rodada_dir, _ = _montar(tmp_path, "dupla", NOMES[:2])
    baseline(rodada_dir, native_only=True, _executor=_executor_pendencia_mista)
    baseline(rodada_dir, native_only=True, processos=2, _executor=_executor_pendencia_mista)
    assert _como_v001(_texto(rodada_dir, "baseline-v002")) == _texto(rodada_dir, "baseline-v001")
    assert "Processos: 2 (efetivos: 2)" in _texto(rodada_dir, "baseline-v002", "md")


def test_um_pdf_com_muitos_processos_nao_cria_pool(
    rodada: tuple[Path, list[str]], espiao: type[_PoolEspiao]
) -> None:
    rodada_dir, ids = rodada
    baseline(rodada_dir, (ids[0],), native_only=True, _executor=_executor_pendencia_mista)
    baseline(
        rodada_dir, (ids[0],), native_only=True, processos=4, _executor=_executor_pendencia_mista
    )
    assert espiao.criados == []
    assert _como_v001(_texto(rodada_dir, "baseline-v002")) == _texto(rodada_dir, "baseline-v001")
    assert "Processos: 4 (efetivos: 1)" in _texto(rodada_dir, "baseline-v002", "md")


def test_parcial_com_pdf_sem_referencia_em_pool_igual_ao_serial(
    rodada: tuple[Path, list[str]],
) -> None:
    rodada_dir, ids = rodada
    (diretorio_ficha(rodada_dir, ids[1]) / "referencia.json").unlink()
    baseline(rodada_dir, native_only=True, parcial=True, _executor=_executor_pendencia_mista)
    baseline(
        rodada_dir,
        native_only=True,
        parcial=True,
        processos=4,
        _executor=_executor_pendencia_mista,
    )
    serial = _texto(rodada_dir, "baseline-v001")
    assert _como_v001(_texto(rodada_dir, "baseline-v002")) == serial
    resumo = json.loads(serial)
    assert resumo["por_pdf"][ids[1]] == {"situacao": "sem_referencia"}
    assert ids[1] not in resumo["pendencia"]["por_pdf"]
    assert "Processos: 4 (efetivos: 2)" in _texto(rodada_dir, "baseline-v002", "md")


def test_parcial_com_um_so_pdf_medido_respeita_o_monkeypatch_mesmo_com_processos(
    rodada: tuple[Path, list[str]], monkeypatch: pytest.MonkeyPatch, espiao: type[_PoolEspiao]
) -> None:
    rodada_dir, ids = rodada
    for pdf_id in ids[1:]:
        (diretorio_ficha(rodada_dir, pdf_id) / "referencia.json").unlink()
    chamadas: list[str] = []

    def trocado(pdf: Path, referencia: Path, saida: Path, **kwargs: Any) -> Registro:
        chamadas.append(kwargs["versao_extracao"])
        return _relatorio(1, 0, 0, [0.1])

    monkeypatch.setattr(curation_ficha, "executar_benchmark", trocado)
    assert main(_argv(rodada_dir, "--native-only", "--parcial", "--processos", "8")) == 0
    assert chamadas == ["projeto-promovido-v1"]
    assert espiao.criados == []


def test_executor_explicito_vence_o_monkeypatch_do_global(
    rodada: tuple[Path, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    rodada_dir, ids = rodada

    def nao_deve_rodar(*_: Any, **__: Any) -> Registro:
        raise AssertionError("o global não devia ser usado quando há _executor")

    monkeypatch.setattr(curation_ficha, "executar_benchmark", nao_deve_rodar)
    resumo = baseline(rodada_dir, (ids[0],), native_only=True, _executor=_executor_simples)
    assert resumo["por_pdf"][ids[0]].get("situacao") is None


@pytest.mark.parametrize("versao", ["projeto-promovido-v1", "propostas-v1"])
def test_spawn_real_com_analisador_igual_ao_serial(
    rodada: tuple[Path, list[str]], versao: str, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, ids = rodada
    assert main(_argv(rodada_dir, "--native-only", "--versao-extracao", versao)) == 0
    assert (
        main(_argv(rodada_dir, "--native-only", "--versao-extracao", versao, "--processos", "2"))
        == 0
    )
    capsys.readouterr()
    assert _como_v001(_texto(rodada_dir, "baseline-v002")) == _texto(rodada_dir, "baseline-v001")
    for pdf_id in ids:
        pasta = diretorio_ficha(rodada_dir, pdf_id)
        for arquivo in ("avaliacao.json", "ficha-predita.json"):
            assert (pasta / "baseline-v001" / arquivo).read_bytes() == (
                pasta / "baseline-v002" / arquivo
            ).read_bytes(), f"{arquivo} de {pdf_id} difere entre o serial e o pool"
    resumo = _resumo(rodada_dir, "baseline-v002")
    assert resumo["opcoes"]["versao_extracao"] == versao
    assert resumo["total"]["postes"]["tp"] > 0


def test_spawn_real_com_pdf_removido_vira_falha_saneada_e_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, ids = _montar(tmp_path, "rodada")
    (tmp_path / "corpus" / "beta-secreto.pdf").unlink()
    assert main(_argv(rodada_dir, "--native-only", "--processos", "3")) == 1
    capsys.readouterr()
    resumo = _resumo(rodada_dir, "baseline-v001")
    assert resumo["por_pdf"][ids[1]]["situacao"] == "falha"
    assert resumo["por_pdf"][ids[0]].get("situacao") is None
    assert resumo["por_pdf"][ids[2]].get("situacao") is None
    _sem_caminho_nem_nome(_texto(rodada_dir, "baseline-v001"), tmp_path)
    _sem_caminho_nem_nome(_texto(rodada_dir, "baseline-v001", "md"), tmp_path)


# --- limite de processos ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pedido", "com_referencia", "esperado"),
    [(1, 10, 1), (4, 3, 3), (200, 3, 3), (61, 100, 61), (62, 100, 61), (1000, 1000, 61), (5, 1, 1)],
)
def test_processos_efetivos(pedido: int, com_referencia: int, esperado: int) -> None:
    assert curation_ficha._processos_efetivos(pedido, com_referencia) == esperado


def test_processos_maior_que_pdfs_cria_pool_do_tamanho_dos_pdfs(
    rodada: tuple[Path, list[str]], espiao: type[_PoolEspiao]
) -> None:
    rodada_dir, _ = rodada
    baseline(rodada_dir, native_only=True, processos=200, _executor=_executor_simples)
    assert espiao.criados == [3]


def test_processos_acima_de_61_com_mais_de_61_pdfs_limita_o_pool_a_61(
    tmp_path: Path, espiao: type[_PoolEspiao]
) -> None:
    nomes = tuple(f"pdf-{n:03d}-secreto" for n in range(63))
    rodada_dir, _ = _montar(tmp_path, "grande", nomes)
    resumo = baseline(rodada_dir, native_only=True, processos=100, _executor=_executor_simples)
    assert espiao.criados == [61]
    assert len(resumo["por_pdf"]) == 63
    assert "Processos: 100 (efetivos: 61)" in _texto(rodada_dir, "baseline-v001", "md")


@pytest.mark.skipif(sys.platform != "win32", reason="limite do ProcessPoolExecutor no Windows")
def test_premissa_processpoolexecutor_recusa_mais_de_61_no_windows() -> None:
    from concurrent.futures import ProcessPoolExecutor

    with pytest.raises(ValueError, match="61"):
        ProcessPoolExecutor(max_workers=62)


def test_pool_nao_e_criado_com_processos_1(
    rodada: tuple[Path, list[str]], espiao: type[_PoolEspiao]
) -> None:
    rodada_dir, _ = rodada
    baseline(rodada_dir, native_only=True, processos=1, _executor=_executor_simples)
    assert espiao.criados == []


# --- pool quebrado ------------------------------------------------------------------------------


@pytest.mark.parametrize("alvo", NOMES)
def test_pool_quebrado_em_qualquer_posicao_grava_resumo_e_md(tmp_path: Path, alvo: str) -> None:
    rodada_dir, ids = _montar(tmp_path, "rodada")
    posicao = NOMES.index(alvo)
    resumo = baseline(
        rodada_dir,
        native_only=True,
        processos=2,
        _executor=functools.partial(_executor_derruba, alvo=alvo),
    )
    assert _resumo(rodada_dir, "baseline-v001") == resumo
    assert (rodada_dir / "fichas" / "baseline-v001-resumo.md").is_file()
    assert resumo["por_pdf"][ids[posicao]] == {"situacao": "falha", "erro": FALHA_DO_POOL}
    medidos = [i for i in ids if resumo["por_pdf"][i].get("situacao") is None]
    # O que não falhou entra no total, e o que falhou fica fora (ausência não é zero).
    assert resumo["total"]["postes"]["tp"] == sum(
        resumo["por_pdf"][i]["postes"]["tp"] for i in medidos
    )
    assert set(resumo["pendencia"]["por_pdf"]) <= set(medidos)
    _sem_caminho_nem_nome(_texto(rodada_dir, "baseline-v001"), tmp_path)
    _sem_caminho_nem_nome(_texto(rodada_dir, "baseline-v001", "md"), tmp_path)


def test_apos_pool_quebrado_a_trava_e_liberada_e_a_proxima_versao_avanca(
    tmp_path: Path,
) -> None:
    rodada_dir, _ = _montar(tmp_path, "rodada")
    baseline(
        rodada_dir,
        native_only=True,
        processos=2,
        _executor=functools.partial(_executor_derruba, alvo="beta-secreto"),
    )
    segundo = baseline(rodada_dir, native_only=True, processos=2, _executor=_executor_simples)
    assert segundo["versao"] == "baseline-v002"
    assert all(b.get("situacao") is None for b in segundo["por_pdf"].values())


def test_main_com_pdf_em_falha_do_pool_termina_1_e_grava_resumo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rodada_dir, ids = _montar(tmp_path, "rodada")
    original = curation_ficha.baseline

    def com_executor_que_derruba(*args: Any, **kwargs: Any) -> Registro:
        return original(
            *args,
            **kwargs,
            _executor=functools.partial(_executor_derruba, alvo="beta-secreto"),
        )

    monkeypatch.setattr(curation_ficha, "baseline", com_executor_que_derruba)
    assert main(_argv(rodada_dir, "--native-only", "--processos", "2")) == 1
    erro = capsys.readouterr().err
    assert ids[1] in erro
    assert _resumo(rodada_dir, "baseline-v001")["por_pdf"][ids[1]]["situacao"] == "falha"


# --- falha saneada nos dois caminhos ------------------------------------------------------------


def _sem_caminho_nem_nome(texto: str, tmp_path: Path) -> None:
    minusculo = texto.lower()
    assert str(tmp_path).lower() not in minusculo
    assert tmp_path.as_posix().lower() not in minusculo
    assert str(tmp_path).lower().replace("\\", "\\\\") not in minusculo
    assert "pytest-of" not in minusculo
    assert not re.search(r"[a-z]:[\\/]", minusculo), "sobrou caminho com unidade"
    for nome in NOMES:
        assert nome not in minusculo


FORMAS = [
    "referencia",
    "referencia_posix",
    "saida",
    "saida_posix",
    "runtime",
    "runtime_posix",
    "pdf_pai",
    "pdf_irmao",
    "fora_do_corpus",
    "fora_do_corpus_posix",
    "oserror",
]


@pytest.mark.parametrize("forma", FORMAS)
def test_falha_serial_cita_caminho_e_sai_saneada(tmp_path: Path, forma: str) -> None:
    rodada_dir, ids = _montar(tmp_path, "rodada")
    resumo = baseline(
        rodada_dir,
        native_only=True,
        runtime_directory=tmp_path / "runtime-dir",
        _executor=functools.partial(_executor_que_cita, forma=forma),
    )
    assert all(resumo["por_pdf"][i]["situacao"] == "falha" for i in ids)
    _sem_caminho_nem_nome(_texto(rodada_dir, "baseline-v001"), tmp_path)
    _sem_caminho_nem_nome(_texto(rodada_dir, "baseline-v001", "md"), tmp_path)


@pytest.mark.parametrize("forma", ["todas", "oserror"])
def test_falha_em_pool_cita_caminho_e_sai_saneada_igual_ao_serial(
    tmp_path: Path, forma: str
) -> None:
    rodada_dir, ids = _montar(tmp_path, "rodada")
    executor = functools.partial(_executor_que_cita, forma=forma)
    runtime = tmp_path / "runtime-dir"
    baseline(rodada_dir, native_only=True, runtime_directory=runtime, _executor=executor)
    baseline(
        rodada_dir, native_only=True, runtime_directory=runtime, processos=3, _executor=executor
    )
    assert _como_v001(_texto(rodada_dir, "baseline-v002")) == _texto(rodada_dir, "baseline-v001")
    resumo = _resumo(rodada_dir, "baseline-v002")
    assert all(resumo["por_pdf"][i]["situacao"] == "falha" for i in ids)
    _sem_caminho_nem_nome(_texto(rodada_dir, "baseline-v002"), tmp_path)
    _sem_caminho_nem_nome(_texto(rodada_dir, "baseline-v002", "md"), tmp_path)


# --- pendência ----------------------------------------------------------------------------------


def test_pendencia_com_pares_reais_do_avaliador_e_invariante_com_os_acertos(
    rodada: tuple[Path, list[str]],
) -> None:
    rodada_dir, ids = rodada
    resumo = baseline(rodada_dir, native_only=True, _executor=_executor_pendencia_mista)
    por_pdf = resumo["pendencia"]["por_pdf"]
    assert set(por_pdf) == {ids[0], ids[1]}  # gama não gravou ficha-predita.json
    esperado_alfa = {c: {"acertos_afirmados": 1, "acertos_com_pendencia": 1} for c in CAMPOS}
    assert por_pdf[ids[0]] == esperado_alfa
    assert por_pdf[ids[1]] == {
        "identificador": {"acertos_afirmados": 1, "acertos_com_pendencia": 0},
        "estruturas": {"acertos_afirmados": 1, "acertos_com_pendencia": 1},
        "poste": {"acertos_afirmados": 2, "acertos_com_pendencia": 0},
        "coordenada": {"acertos_afirmados": 2, "acertos_com_pendencia": 0},
    }
    for pdf_id in (ids[0], ids[1]):
        for campo in CAMPOS:
            soma = sum(por_pdf[pdf_id][campo].values())
            assert soma == resumo["por_pdf"][pdf_id]["campos"][campo]["acertos"], (pdf_id, campo)
    assert resumo["pendencia"]["total"] == {
        "identificador": {"acertos_afirmados": 2, "acertos_com_pendencia": 1},
        "estruturas": {"acertos_afirmados": 2, "acertos_com_pendencia": 2},
        "poste": {"acertos_afirmados": 3, "acertos_com_pendencia": 1},
        "coordenada": {"acertos_afirmados": 3, "acertos_com_pendencia": 1},
    }


def test_pendencia_em_pool_igual_a_serial_com_relatorio_real(
    rodada: tuple[Path, list[str]],
) -> None:
    rodada_dir, _ = rodada
    serial = baseline(rodada_dir, native_only=True, _executor=_executor_pendencia_mista)
    paralelo = baseline(
        rodada_dir, native_only=True, processos=3, _executor=_executor_pendencia_mista
    )
    assert serial["pendencia"] == paralelo["pendencia"]
    assert serial["pendencia"]["total"]["estruturas"]["acertos_com_pendencia"] == 2


def test_pendencia_ignora_par_hostil_e_conta_so_o_valido(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, ids = rodada
    resumo = baseline(rodada_dir, (ids[0],), native_only=True, _executor=_executor_pares_hostis)
    assert resumo["pendencia"]["total"] == {
        "identificador": {"acertos_afirmados": 1, "acertos_com_pendencia": 0},
        "estruturas": ZERO,  # False não é acerto
        "poste": {"acertos_afirmados": 0, "acertos_com_pendencia": 1},  # p1 declara "poste"
        "coordenada": ZERO,  # None (pendente na referência) fica fora
    }


def test_campo_pendente_na_referencia_fica_fora_da_conta_com_relatorio_real(
    rodada: tuple[Path, list[str]],
) -> None:
    rodada_dir, ids = rodada
    resumo = baseline(
        rodada_dir, (ids[0],), native_only=True, _executor=_executor_referencia_pendente
    )
    pares = resumo["pendencia"]["total"]
    # p1: identificador é None na referência (fora). p2: acerta e a predição declara pendente.
    assert pares["identificador"] == {"acertos_afirmados": 0, "acertos_com_pendencia": 1}
    assert pares["poste"] == {"acertos_afirmados": 2, "acertos_com_pendencia": 0}
    assert resumo["total"]["campos"]["identificador"]["total"] == 1


def test_pendencia_pdf_sem_ficha_fica_fora_sem_afetar_o_total(
    rodada: tuple[Path, list[str]],
) -> None:
    rodada_dir, ids = rodada
    resumo = baseline(rodada_dir, native_only=True, _executor=_executor_pendencia_mista)
    assert ids[2] not in resumo["pendencia"]["por_pdf"]
    somado = sum(
        bloco[c]["acertos_afirmados"] + bloco[c]["acertos_com_pendencia"]
        for bloco in resumo["pendencia"]["por_pdf"].values()
        for c in CAMPOS
    )
    total = resumo["pendencia"]["total"]
    assert somado == sum(
        total[c]["acertos_afirmados"] + total[c]["acertos_com_pendencia"] for c in CAMPOS
    )


@pytest.mark.parametrize(
    "conteudo",
    [
        "{nao e json",
        "",
        "[]",
        "null",
        '{"postes": null}',
        '{"postes": "p1"}',
        '{"postes": [null, 3, "x", {"pendentes": ["poste"]}]}',
        '{"postes": [{"id": "p1", "pendentes": "poste"}]}',
        '{"postes": [{"id": "p1"}]}',
    ],
    ids=[
        "json_invalido",
        "vazio",
        "lista",
        "null",
        "postes_null",
        "postes_texto",
        "postes_nao_dict",
        "pendentes_texto",
        "sem_pendentes",
    ],
)
def test_ficha_predita_corrompida_nao_derruba_o_baseline(
    rodada: tuple[Path, list[str]], conteudo: str
) -> None:
    rodada_dir, ids = rodada
    resumo = baseline(
        rodada_dir,
        (ids[0],),
        native_only=True,
        _executor=functools.partial(_executor_ficha_com_conteudo, conteudo=conteudo),
    )
    assert (rodada_dir / "fichas" / "baseline-v001-resumo.json").is_file()
    assert resumo["pendencia"]["total"] == dict.fromkeys(CAMPOS, ZERO)


@pytest.mark.parametrize("conteudo", ["{nao e json", "", "[]", "null", '{"postes": null}'])
def test_pendencia_isolada_tolera_ficha_predita_ilegivel(tmp_path: Path, conteudo: str) -> None:
    """``_pendencia`` sozinha (sem ``_gerador_do_baseline``): ficha ilegível deixa o PDF de fora."""
    (tmp_path / "ficha-predita.json").write_text(conteudo, encoding="utf-8")
    relatorio = _relatorio(1, 0, 0, [0.0])
    relatorio["pares"] = _pares_hostis()
    resultado = curation_ficha._pendencia({"01-x": relatorio}, {"01-x": tmp_path})
    assert resultado == {"por_pdf": {}, "total": dict.fromkeys(CAMPOS, ZERO)}


# --- markdown -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("processos", "sem_referencia", "linha"),
    [
        (1, 0, "Processos: 1 (efetivos: 1)"),
        (2, 0, "Processos: 2 (efetivos: 2)"),
        (4, 0, "Processos: 4 (efetivos: 3)"),
        (4, 1, "Processos: 4 (efetivos: 2)"),
        (4, 2, "Processos: 4 (efetivos: 1)"),
        (7, 0, "Processos: 7 (efetivos: 3)"),
    ],
)
def test_markdown_processos_pedido_e_efetivo(
    rodada: tuple[Path, list[str]], processos: int, sem_referencia: int, linha: str
) -> None:
    rodada_dir, ids = rodada
    for pdf_id in ids[:sem_referencia]:
        (diretorio_ficha(rodada_dir, pdf_id) / "referencia.json").unlink()
    baseline(
        rodada_dir,
        native_only=True,
        parcial=bool(sem_referencia),
        processos=processos,
        _executor=_executor_simples,
    )
    linhas = _texto(rodada_dir, "baseline-v001", "md").splitlines()
    assert linhas[0] == "# baseline-v001"
    assert linhas[2] == "Versão de extração: projeto-promovido-v1"
    assert linhas[3] == linha


def test_markdown_pendencia_espelha_o_json_e_termina_com_a_frase_dos_vaos(
    rodada: tuple[Path, list[str]],
) -> None:
    rodada_dir, _ = rodada
    resumo = baseline(rodada_dir, native_only=True, _executor=_executor_pendencia_mista)
    linhas = _texto(rodada_dir, "baseline-v001", "md").splitlines()
    inicio = linhas.index("## Acertos afirmados e com pendência (total)")
    for campo in CAMPOS:
        bloco = resumo["pendencia"]["total"][campo]
        esperada = f"| {campo} | {bloco['acertos_afirmados']} | {bloco['acertos_com_pendencia']} |"
        assert esperada in linhas[inicio:]
    assert [linha for linha in linhas if linha][
        -1
    ] == "Vãos e símbolos: sem separação de pendência."
    assert linhas.count("Vãos e símbolos: sem separação de pendência.") == 1


def test_markdown_versao_de_extracao_vem_do_resumo(rodada: tuple[Path, list[str]]) -> None:
    rodada_dir, _ = rodada
    baseline(
        rodada_dir,
        native_only=True,
        versao_extracao="propostas-v1",
        _executor=_executor_simples,
    )
    assert "Versão de extração: propostas-v1" in _texto(rodada_dir, "baseline-v001", "md")


# --- argumentos ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        ["--processos", "abc"],
        ["--processos", "1.5"],
        ["--processos", ""],
        ["--processos", "-1"],
        ["--processos", "0"],
        ["--versao-extracao", ""],
        ["--versao-extracao", "Propostas-V1"],
        ["--versao-extracao", "propostas-v2"],
    ],
)
def test_cli_argumento_invalido_sai_2_sem_gravar_nada(
    rodada: tuple[Path, list[str]], extra: list[str]
) -> None:
    rodada_dir, ids = rodada
    with pytest.raises(SystemExit) as saida:
        main(_argv(rodada_dir, "--native-only", *extra))
    assert saida.value.code == 2
    assert not _baselines_gravados(rodada_dir, ids)


@pytest.mark.parametrize("processos", [1, 2, 61, 62, 1000])
def test_cli_aceita_qualquer_inteiro_positivo(processos: int, tmp_path: Path) -> None:
    args = curation_ficha._parser().parse_args(
        ["baseline", "--rodada", str(tmp_path), "--processos", str(processos)]
    )
    assert args.processos == processos


@pytest.mark.parametrize(
    "opcoes", [{"processos": 0}, {"processos": -3}, {"versao_extracao": "inexistente-v9"}]
)
def test_api_argumento_invalido_levanta_antes_de_medir_ou_gravar(
    rodada: tuple[Path, list[str]], opcoes: dict[str, Any]
) -> None:
    rodada_dir, ids = rodada

    def nao_deve_rodar(*_: Any, **__: Any) -> Registro:
        raise AssertionError("não devia medir nada")

    with pytest.raises(ValueError):
        baseline(rodada_dir, native_only=True, _executor=nao_deve_rodar, **opcoes)
    assert not _baselines_gravados(rodada_dir, ids)


def test_resumo_padrao_traz_a_versao_de_extracao_padrao_e_a_chave_pendencia(
    rodada: tuple[Path, list[str]],
) -> None:
    rodada_dir, _ = rodada
    resumo = baseline(rodada_dir, native_only=True, _executor=_executor_simples)
    assert resumo["opcoes"] == {
        "native_only": True,
        "pdfs": resumo["opcoes"]["pdfs"],
        "versao_extracao": "projeto-promovido-v1",
    }
    assert resumo["schema_version"] == "curadoria-ficha-baseline-v1"
    assert set(resumo["pendencia"]) == {"por_pdf", "total"}
    assert "processos" not in json.dumps(resumo)
