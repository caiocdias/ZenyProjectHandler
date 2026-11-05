"""Ataque ao relógio estritamente crescente do `job_store` (Task 4 da E06.1).

Cobre `_agora()` isolado (monotonicidade, relógio que volta, deriva, threads, falha do relógio) e o
efeito dele na persistência e na retenção (`prune`): formato gravado, jobs legados, empates reais
vindos do banco e escritas concorrentes.
"""

from __future__ import annotations

import ast
import re
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from threading import Barrier, Thread
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, insert, select

from zeny_project_handler.adapters.persistence.database import managed_sqlite_engine
from zeny_project_handler.adapters.persistence.schema import api_jobs, metadata
from zeny_project_handler_contracts.enums import JobKind, JobStatus
from zeny_project_handler_server import job_store as job_store_module
from zeny_project_handler_server.job_store import JobStore

_UM_US = timedelta(microseconds=1)
_BASE_FIXA = datetime(2030, 1, 1, 12, 0, 0, 500_000, tzinfo=UTC)
_FORMATO_ISO_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{6})?\+00:00$")
_RAIZ_SRC = Path(job_store_module.__file__).resolve().parent


class RelogioFalso:
    """Relógio injetado em `_relogio_bruto`; `ceder` abre a janela de corrida entre threads."""

    def __init__(self, inicio: datetime, *, ceder: bool = False) -> None:
        self.valor = inicio
        self._ceder = ceder

    def __call__(self) -> datetime:
        if self._ceder:
            time.sleep(0)
        return self.valor


@pytest.fixture(autouse=True)
def _relogio_zerado(monkeypatch: pytest.MonkeyPatch) -> None:
    # O último instante é estado global do processo: sem isto, um teste que adiantou o relógio
    # contamina os seguintes. O monkeypatch devolve o valor original no fim.
    monkeypatch.setattr(job_store_module, "_ultimo_instante", None)


@pytest.fixture
def troca_de_thread_agressiva() -> Iterator[None]:
    """Força o interpretador a trocar de thread a cada instante: sem lock, a corrida aparece."""
    original = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        yield
    finally:
        sys.setswitchinterval(original)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    with managed_sqlite_engine(tmp_path / "jobs.db") as criado:
        metadata.create_all(criado)
        yield criado


def _congelar(
    monkeypatch: pytest.MonkeyPatch, inicio: datetime, *, ceder: bool = False
) -> RelogioFalso:
    relogio = RelogioFalso(inicio, ceder=ceder)
    monkeypatch.setattr(job_store_module, "_relogio_bruto", relogio)
    return relogio


def _inserir_terminal(
    engine: Engine,
    job_id: UUID,
    *,
    created_at: datetime,
    updated_at: datetime,
    status: JobStatus = JobStatus.SUCCEEDED,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            insert(api_jobs).values(
                id=str(job_id),
                project_id=None,
                kind=JobKind.ANALYSIS.value,
                status=status.value,
                progress_percent=100,
                message="legado",
                result_json=None,
                error_json=None,
                created_at=created_at.isoformat(),
                updated_at=updated_at.isoformat(),
                expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            )
        )


def _ids_restantes(engine: Engine) -> set[UUID]:
    with engine.connect() as connection:
        return {UUID(str(linha.id)) for linha in connection.execute(select(api_jobs.c.id))}


def _agora() -> datetime:
    return job_store_module._agora()


# --- _agora isolado -------------------------------------------------------------------------


def test_agora_com_relogio_parado_avanca_exatamente_um_microssegundo_por_chamada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _congelar(monkeypatch, _BASE_FIXA)
    chamadas = 1_000

    instantes = [_agora() for _ in range(chamadas)]

    assert instantes[0] == _BASE_FIXA
    assert instantes == [_BASE_FIXA + index * _UM_US for index in range(chamadas)]
    # Deriva limitada: depois de N chamadas no mesmo tique, a hora é no máximo hora real + N·ε.
    assert instantes[-1] - _BASE_FIXA <= chamadas * _UM_US


def test_agora_depois_de_rajada_no_mesmo_tique_volta_a_seguir_o_relogio_real(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relogio = _congelar(monkeypatch, _BASE_FIXA)
    for _ in range(1_000):
        _agora()

    relogio.valor = _BASE_FIXA + timedelta(milliseconds=5)
    seguinte = _agora()

    # A deriva da rajada (999 µs) não se acumula: o relógio real, já à frente, vale de novo.
    assert seguinte == relogio.valor
    assert _agora() == relogio.valor + _UM_US


def test_agora_aceita_relogio_exatamente_um_microssegundo_a_frente_sem_somar_de_novo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relogio = _congelar(monkeypatch, _BASE_FIXA)
    primeiro = _agora()

    relogio.valor = primeiro + _UM_US
    segundo = _agora()
    terceiro = _agora()

    assert segundo == primeiro + _UM_US
    assert terceiro == segundo + _UM_US


@pytest.mark.parametrize(
    "recuo",
    [
        pytest.param(_UM_US, id="recua-1-microssegundo"),
        pytest.param(timedelta(seconds=1), id="recua-1-segundo"),
        pytest.param(timedelta(hours=1), id="recua-1-hora-dst-ou-ntp"),
        pytest.param(timedelta(days=365), id="recua-1-ano"),
    ],
)
def test_agora_nao_regride_nem_trava_quando_o_relogio_volta_no_tempo(
    monkeypatch: pytest.MonkeyPatch, recuo: timedelta
) -> None:
    relogio = _congelar(monkeypatch, _BASE_FIXA)
    antes = _agora()

    relogio.valor = _BASE_FIXA - recuo
    depois = [_agora() for _ in range(5)]

    assert depois == [antes + index * _UM_US for index in range(1, 6)]

    # Quando o relógio real ultrapassa o último instante entregue, ele volta a mandar.
    relogio.valor = depois[-1] + timedelta(seconds=1)
    assert _agora() == relogio.valor


def test_relogio_bruto_real_devolve_instante_utc_com_fuso() -> None:
    # Contrato: o formato persistido é sempre UTC (`+00:00`); a ordenação textual depende disso.
    instante = job_store_module._relogio_bruto()

    assert instante.tzinfo is UTC
    assert abs(datetime.now(UTC) - instante) < timedelta(seconds=5)


def test_agora_com_relogio_real_e_estritamente_crescente_e_tem_fuso() -> None:
    instantes = [_agora() for _ in range(20_000)]

    assert all(a < b for a, b in pairwise(instantes))
    assert all(item.utcoffset() == timedelta(0) for item in instantes)


def test_agora_com_relogio_real_nao_se_afasta_do_relogio_bruto_alem_da_rajada() -> None:
    chamadas = 20_000
    antes = datetime.now(UTC)
    ultimo = [_agora() for _ in range(chamadas)][-1]
    depois = datetime.now(UTC)

    assert ultimo <= depois + chamadas * _UM_US
    assert ultimo >= antes


def test_agora_concorrente_com_relogio_parado_entrega_instantes_unicos_e_crescentes_por_thread(
    monkeypatch: pytest.MonkeyPatch, troca_de_thread_agressiva: None
) -> None:
    threads_n, por_thread = 8, 250
    _congelar(monkeypatch, _BASE_FIXA, ceder=True)
    largada = Barrier(threads_n)
    resultados: list[list[datetime]] = [[] for _ in range(threads_n)]

    def trabalhar(indice: int) -> None:
        largada.wait()
        resultados[indice] = [_agora() for _ in range(por_thread)]

    threads = [Thread(target=trabalhar, args=(indice,)) for indice in range(threads_n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not any(thread.is_alive() for thread in threads)

    todos = [item for lista in resultados for item in lista]
    assert len(todos) == threads_n * por_thread
    assert len(set(todos)) == len(todos)
    assert min(todos) == _BASE_FIXA
    assert max(todos) == _BASE_FIXA + (len(todos) - 1) * _UM_US
    for lista in resultados:
        assert all(a < b for a, b in pairwise(lista))


def test_agora_concorrente_com_relogio_real_entrega_instantes_unicos_e_crescentes_por_thread(
    troca_de_thread_agressiva: None,
) -> None:
    threads_n, por_thread = 8, 2_000
    largada = Barrier(threads_n)
    resultados: list[list[datetime]] = [[] for _ in range(threads_n)]

    def trabalhar(indice: int) -> None:
        largada.wait()
        resultados[indice] = [_agora() for _ in range(por_thread)]

    threads = [Thread(target=trabalhar, args=(indice,)) for indice in range(threads_n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    assert not any(thread.is_alive() for thread in threads)

    todos = [item for lista in resultados for item in lista]
    assert len(set(todos)) == threads_n * por_thread
    for lista in resultados:
        assert all(a < b for a, b in pairwise(lista))


def test_agora_com_falha_do_relogio_libera_o_lock_e_preserva_o_ultimo_instante(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relogio = _congelar(monkeypatch, _BASE_FIXA)
    primeiro = _agora()

    def quebrado() -> datetime:
        raise OSError("relógio indisponível")

    monkeypatch.setattr(job_store_module, "_relogio_bruto", quebrado)
    with pytest.raises(OSError, match="relógio indisponível"):
        _agora()
    assert job_store_module._ultimo_instante == primeiro

    monkeypatch.setattr(job_store_module, "_relogio_bruto", relogio)
    seguinte: list[datetime] = []
    thread = Thread(target=lambda: seguinte.append(_agora()))
    thread.start()
    thread.join(5)

    assert not thread.is_alive(), "o lock do relógio ficou preso depois da falha"
    assert seguinte == [primeiro + _UM_US]


# --- formato persistido e ordenação textual -------------------------------------------------


def test_formato_persistido_continua_iso_utc_e_o_vencimento_soma_a_retencao_exata(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = datetime.now(UTC).replace(microsecond=0)
    _congelar(monkeypatch, base)
    retencao = timedelta(minutes=90)
    store = JobStore(engine, retention=retencao, maximum_retained=5)
    job_id = uuid4()

    criado = store.create(job_id, None, JobKind.ANALYSIS)
    final = store.finish(job_id, status=JobStatus.SUCCEEDED, message="ok", result_json="{}")

    with engine.connect() as connection:
        linha = connection.execute(select(api_jobs).where(api_jobs.c.id == str(job_id))).one()
    assert linha.created_at == base.isoformat()  # microssegundo zero: sem fração
    assert linha.updated_at == (base + _UM_US).isoformat()
    assert linha.updated_at.endswith(".000001+00:00")
    assert _FORMATO_ISO_UTC.match(linha.created_at)
    assert _FORMATO_ISO_UTC.match(linha.updated_at)
    assert _FORMATO_ISO_UTC.match(linha.expires_at)
    assert criado.created_at == criado.updated_at == base
    assert criado.expires_at == base + retencao
    assert final.created_at == base
    assert final.updated_at == base + _UM_US
    assert final.expires_at == final.updated_at + retencao
    assert final.updated_at.utcoffset() == timedelta(0)


def test_ordem_textual_dos_updated_at_acompanha_a_cronologia_na_virada_do_segundo(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `isoformat()` omite a fração quando o microssegundo é zero; a retenção ordena por texto.
    virada = (datetime.now(UTC) + timedelta(seconds=1)).replace(microsecond=0)
    _congelar(monkeypatch, virada - 3 * _UM_US)
    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=1)
    ids = [uuid4() for _ in range(4)]
    for job_id in ids:
        store.create(job_id, None, JobKind.ANALYSIS)
        store.finish(job_id, status=JobStatus.SUCCEEDED, message="ok", result_json="{}")

    with engine.connect() as connection:
        textos = [
            str(linha.updated_at)
            for linha in connection.execute(
                select(api_jobs.c.updated_at).order_by(api_jobs.c.updated_at)
            )
        ]
    assert any("." not in texto.split("+")[0].split("T")[1] for texto in textos), (
        "o cenário precisa cruzar um segundo cheio, sem fração"
    )
    cronologicos = [datetime.fromisoformat(texto) for texto in textos]
    assert cronologicos == sorted(cronologicos)
    assert len(set(cronologicos)) == len(ids)

    assert store.prune() == len(ids) - 1
    assert _ids_restantes(engine) == {ids[-1]}


# --- jobs gravados antes da mudança ---------------------------------------------------------


def test_jobs_legados_continuam_ordenando_certo_contra_jobs_novos(engine: Engine) -> None:
    agora = datetime.now(UTC)
    t0 = (agora - timedelta(minutes=10)).replace(microsecond=0)
    legado_inteiro, legado_fracao, legado_antigo = uuid4(), uuid4(), uuid4()
    _inserir_terminal(
        engine, legado_antigo, created_at=t0 - timedelta(hours=1), updated_at=t0 - _UM_US
    )
    _inserir_terminal(engine, legado_inteiro, created_at=t0, updated_at=t0)  # sem fração
    _inserir_terminal(engine, legado_fracao, created_at=t0, updated_at=t0 + _UM_US)
    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=2)
    novo = uuid4()
    store.create(novo, None, JobKind.ANALYSIS)
    store.finish(novo, status=JobStatus.SUCCEEDED, message="ok", result_json="{}")

    assert store.prune() == 2
    assert _ids_restantes(engine) == {novo, legado_fracao}


def test_job_novo_e_sempre_mais_recente_que_legado_gravado_com_relogio_atual(
    engine: Engine,
) -> None:
    # Legado gravado com o relógio bruto "agora": o novo job, mesmo no mesmo tique, não pode perder.
    agora = datetime.now(UTC)
    legado = uuid4()
    _inserir_terminal(engine, legado, created_at=agora, updated_at=agora)
    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=1)
    novo = uuid4()
    store.create(novo, None, JobKind.ANALYSIS)
    store.finish(novo, status=JobStatus.SUCCEEDED, message="ok", result_json="{}")

    assert store.prune() == 1
    assert _ids_restantes(engine) == {novo}


# --- empates reais vindos do banco ----------------------------------------------------------


@pytest.mark.parametrize(
    "ordem_de_insercao",
    [
        pytest.param((0, 1, 2), id="inserido-do-mais-antigo-ao-mais-novo"),
        pytest.param((2, 1, 0), id="inserido-do-mais-novo-ao-mais-antigo"),
        pytest.param((1, 0, 2), id="inserido-fora-de-ordem"),
    ],
)
def test_prune_com_updated_at_empatado_no_banco_mantem_o_job_criado_por_ultimo(
    engine: Engine, ordem_de_insercao: tuple[int, ...]
) -> None:
    # Linhas legadas (gravadas antes do relógio monotônico) podem trazer o mesmo `updated_at`.
    # O desempate tem de ser determinístico e pela ordem de criação (brief da Task 4).
    base = datetime.now(UTC) - timedelta(minutes=5)
    empate = base + timedelta(milliseconds=50)
    ids = [UUID(int=indice + 1) for indice in range(3)]
    for posicao in ordem_de_insercao:
        _inserir_terminal(
            engine,
            ids[posicao],
            created_at=base + timedelta(milliseconds=posicao * 10),
            updated_at=empate,
        )
    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=1)

    assert store.prune() == 2
    assert _ids_restantes(engine) == {ids[2]}


def test_prune_depois_de_reconcile_interrupted_mantem_o_job_criado_por_ultimo(
    engine: Engine,
) -> None:
    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=1)
    ids = [uuid4() for _ in range(3)]
    for job_id in ids:
        store.create(job_id, None, JobKind.ANALYSIS)

    assert store.reconcile_interrupted() == 3

    assert store.prune() == 2
    assert _ids_restantes(engine) == {ids[-1]}


# --- escritas concorrentes no store ---------------------------------------------------------


def test_create_update_e_finish_em_threads_entre_dois_stores_nao_empatam_nem_travam(
    engine: Engine,
) -> None:
    threads_n, por_thread, retidos = 8, 10, 7
    lojas = (
        JobStore(engine, retention=timedelta(hours=1), maximum_retained=retidos),
        JobStore(engine, retention=timedelta(hours=1), maximum_retained=retidos),
    )
    largada = Barrier(threads_n)
    erros: list[BaseException] = []
    por_job: dict[UUID, list[UUID]] = {}

    def trabalhar(indice: int) -> None:
        loja = lojas[indice % 2]
        ids = [uuid4() for _ in range(por_thread)]
        por_job[uuid4()] = ids
        try:
            largada.wait()
            for job_id in ids:
                loja.create(job_id, None, JobKind.ANALYSIS)
                loja.update_progress(
                    job_id, status=JobStatus.RUNNING, progress_percent=50, message="meio"
                )
                loja.finish(job_id, status=JobStatus.SUCCEEDED, message="ok", result_json="{}")
        except BaseException as erro:
            erros.append(erro)

    threads = [Thread(target=trabalhar, args=(indice,)) for indice in range(threads_n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(120)
    assert not any(thread.is_alive() for thread in threads), (
        "deadlock entre o lock do relógio e o do store"
    )
    assert erros == []

    todos = [job_id for ids in por_job.values() for job_id in ids]
    registros = [lojas[0].get(job_id) for job_id in todos]
    assert all(
        registro is not None and registro.status is JobStatus.SUCCEEDED for registro in registros
    )
    finais = [registro.updated_at for registro in registros if registro is not None]
    criados = [registro.created_at for registro in registros if registro is not None]
    assert len(set(finais)) == len(todos)
    assert len(set(criados)) == len(todos)
    assert all(
        registro.updated_at > registro.created_at for registro in registros if registro is not None
    )
    # Dentro de cada thread a ordem de criação é a ordem cronológica dos updated_at.
    for ids in por_job.values():
        momentos = [lojas[0].get(job_id).updated_at for job_id in ids]  # type: ignore[union-attr]
        assert momentos == sorted(momentos)

    esperados = sorted(
        (registro for registro in registros if registro is not None),
        key=lambda registro: registro.updated_at,
        reverse=True,
    )[:retidos]
    assert lojas[0].prune() == len(todos) - retidos
    assert _ids_restantes(engine) == {registro.job_id for registro in esperados}


# --- contrato de processo único -------------------------------------------------------------


def test_servidor_sobe_com_um_unico_processo_porque_o_lock_do_relogio_e_por_processo() -> None:
    arvore = ast.parse((_RAIZ_SRC / "__main__.py").read_text(encoding="utf-8"))
    chamadas_run = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "run"
    ]
    assert chamadas_run, "uvicorn.run não encontrado em __main__.py"
    workers = [
        palavra.value
        for chamada in chamadas_run
        for palavra in chamada.keywords
        if palavra.arg == "workers"
    ]
    assert len(workers) == 1
    assert isinstance(workers[0], ast.Constant)
    assert workers[0].value == 1
