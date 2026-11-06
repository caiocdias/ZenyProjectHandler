"""Ataque à retenção do `job_store` com `updated_at` empatado (Task 4 da E06.1).

O relógio do Windows avança em passos de ~15,6 ms, então jobs gravados em sequência podem ter o
mesmo `updated_at` (e o mesmo `created_at`). A retenção (`JobStore.prune`) precisa desempatar de
forma determinística: `updated_at`, depois `created_at`, depois a ordem de inserção (`rowid`).

Os testes só dependem do contrato público de `JobStore` e da substituição de `job_store.datetime`
ou de linhas gravadas direto no banco; não dependem de nenhum detalhe do relógio interno.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, insert, select

from zeny_project_handler.adapters.persistence.database import managed_sqlite_engine
from zeny_project_handler.adapters.persistence.schema import api_jobs, metadata
from zeny_project_handler_contracts.enums import JobKind, JobStatus
from zeny_project_handler_server import job_store as job_store_module
from zeny_project_handler_server.job_store import JobStore

_UM_US = timedelta(microseconds=1)
_FORMATO_ISO_UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{6})?\+00:00$")


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    with managed_sqlite_engine(tmp_path / "jobs.db") as criado:
        metadata.create_all(criado)
        yield criado


def _congelar_relogio(monkeypatch: pytest.MonkeyPatch, instante: datetime) -> None:
    """Faz `datetime.now` do `job_store` devolver sempre o mesmo instante (tique do Windows)."""

    class Congelado(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Congelado:
            return cls.combine(instante.date(), instante.timetz())

    monkeypatch.setattr(job_store_module, "datetime", Congelado)


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


def _criar_e_finalizar(store: JobStore, job_id: UUID) -> None:
    store.create(job_id, None, JobKind.ANALYSIS)
    store.finish(job_id, status=JobStatus.SUCCEEDED, message="ok", result_json="{}")


# --- formato persistido ---------------------------------------------------------------------


def test_formato_persistido_continua_iso_utc_e_o_vencimento_soma_a_retencao_exata(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _congelar_relogio(monkeypatch, datetime.now(UTC).replace(microsecond=0))
    retencao = timedelta(minutes=90)
    store = JobStore(engine, retention=retencao, maximum_retained=5)
    job_id = uuid4()

    criado = store.create(job_id, None, JobKind.ANALYSIS)
    final = store.finish(job_id, status=JobStatus.SUCCEEDED, message="ok", result_json="{}")

    with engine.connect() as connection:
        linha = connection.execute(select(api_jobs).where(api_jobs.c.id == str(job_id))).one()
    for texto in (linha.created_at, linha.updated_at, linha.expires_at):
        assert _FORMATO_ISO_UTC.match(texto), texto
    assert criado.created_at == criado.updated_at
    assert criado.expires_at == criado.created_at + retencao
    assert final.created_at == criado.created_at
    assert final.updated_at >= final.created_at
    assert final.expires_at == final.updated_at + retencao
    for instante in (final.created_at, final.updated_at, final.expires_at):
        assert instante.utcoffset() == timedelta(0)


def test_ordem_textual_dos_updated_at_acompanha_a_cronologia_na_virada_do_segundo(
    engine: Engine,
) -> None:
    # `isoformat()` omite a fração quando o microssegundo é zero; a retenção ordena por texto.
    virada = (datetime.now(UTC) + timedelta(seconds=1)).replace(microsecond=0)
    momentos = [virada - 2 * _UM_US, virada - _UM_US, virada, virada + _UM_US, virada + 2 * _UM_US]
    ids = [uuid4() for _ in momentos]
    for job_id, momento in zip(ids, momentos, strict=True):
        _inserir_terminal(
            engine, job_id, created_at=momento - timedelta(seconds=1), updated_at=momento
        )

    with engine.connect() as connection:
        textos = [
            str(linha.updated_at)
            for linha in connection.execute(
                select(api_jobs.c.updated_at).order_by(api_jobs.c.updated_at)
            )
        ]
    assert any("." not in texto.split("T")[1].split("+")[0] for texto in textos), (
        "o cenário precisa conter um segundo cheio, sem fração"
    )
    assert [datetime.fromisoformat(texto) for texto in textos] == momentos

    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=2)
    assert store.prune() == len(ids) - 2
    assert _ids_restantes(engine) == set(ids[-2:])


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
    _criar_e_finalizar(store, novo)

    assert store.prune() == 2
    assert _ids_restantes(engine) == {novo, legado_fracao}


def test_job_novo_no_mesmo_tique_de_um_legado_nao_perde_a_retencao(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    agora = datetime.now(UTC)
    _congelar_relogio(monkeypatch, agora)
    legado = uuid4()
    _inserir_terminal(engine, legado, created_at=agora, updated_at=agora)
    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=1)
    novo = uuid4()
    _criar_e_finalizar(store, novo)

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
    # Linhas gravadas no mesmo tique do relógio: `updated_at` igual, `created_at` distintos.
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


@pytest.mark.parametrize(
    "ordem_de_insercao",
    [
        pytest.param((0, 1, 2), id="ids-crescentes-na-ordem-de-insercao"),
        pytest.param((2, 1, 0), id="ids-decrescentes-na-ordem-de-insercao"),
        pytest.param((1, 2, 0), id="ids-embaralhados-na-ordem-de-insercao"),
    ],
)
def test_prune_com_updated_at_e_created_at_empatados_mantem_o_ultimo_inserido(
    engine: Engine, ordem_de_insercao: tuple[int, ...]
) -> None:
    # Empate total: só a ordem física de inserção (rowid) separa os jobs, não o id (UUID).
    instante = datetime.now(UTC) - timedelta(minutes=5)
    ids = [UUID(int=indice + 1) for indice in range(3)]
    for posicao in ordem_de_insercao:
        _inserir_terminal(engine, ids[posicao], created_at=instante, updated_at=instante)
    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=1)

    assert store.prune() == 2
    assert _ids_restantes(engine) == {ids[ordem_de_insercao[-1]]}


@pytest.mark.parametrize(
    "relogio_congelado", [False, True], ids=["relogio-real", "relogio-congelado"]
)
def test_prune_depois_de_reconcile_interrupted_mantem_o_job_criado_por_ultimo(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, relogio_congelado: bool
) -> None:
    # `reconcile_interrupted` grava o mesmo `updated_at` em todos os jobs interrompidos.
    if relogio_congelado:
        _congelar_relogio(monkeypatch, datetime.now(UTC))
    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=1)
    ids = [uuid4() for _ in range(3)]
    for job_id in ids:
        store.create(job_id, None, JobKind.ANALYSIS)

    assert store.reconcile_interrupted() == 3

    assert store.prune() == 2
    assert _ids_restantes(engine) == {ids[-1]}


def test_prune_com_relogio_parado_mantem_o_ultimo_job_finalizado(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # O cenário do teste intermitente original: tudo no mesmo tique do relógio.
    _congelar_relogio(monkeypatch, datetime.now(UTC))
    store = JobStore(engine, retention=timedelta(hours=1), maximum_retained=1)
    ids = [uuid4() for _ in range(8)]
    for job_id in ids:
        _criar_e_finalizar(store, job_id)

    assert store.prune() == len(ids) - 1
    assert _ids_restantes(engine) == {ids[-1]}
