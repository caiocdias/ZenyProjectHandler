from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest

from zeny_project_handler.application.errors import RecuperacaoImportacaoBloqueadaError
from zeny_project_handler.application.import_recovery import (
    ArmazenamentoJournalImportacao,
    FaseJournalImportacao,
    JournalImportacaoProjeto,
    RecuperadorImportacaoProjeto,
    fingerprint_arquivos_esperados,
    fingerprint_arvore_gerenciada,
)
from zeny_project_handler.ports.persistence import ComprovanteCommitImportacao

OPERATION_ID = UUID("10000000-0000-0000-0000-000000000001")
PROJECT_ID = UUID("20000000-0000-0000-0000-000000000002")
PACKAGE_SHA256 = "1" * 64
PLAN_SHA256 = "2" * 64
TARGET_SHA256 = "3" * 64


def _journal(*, previous_digest: str | None = None) -> JournalImportacaoProjeto:
    new_digest = fingerprint_arquivos_esperados((("document.pdf", 3, "4" * 64),))
    return JournalImportacaoProjeto.novo(
        operation_id=OPERATION_ID,
        project_id=PROJECT_ID,
        package_sha256=PACKAGE_SHA256,
        plan_sha256=PLAN_SHA256,
        target_state_sha256=TARGET_SHA256,
        new_files_sha256=new_digest,
        previous_files_sha256=previous_digest,
        previous_assets_existed=previous_digest is not None,
        created_at=datetime(2026, 8, 6, 12, tzinfo=UTC),
    )


def test_journal_write_is_atomic_and_preserves_last_phase_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ArmazenamentoJournalImportacao(tmp_path)
    prepared = _journal().avancar(FaseJournalImportacao.PREPARADO)
    store.escrever(prepared)
    previous_bytes = store.journal_path.read_bytes()

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("queda simulada")

    monkeypatch.setattr(
        "zeny_project_handler.application.import_recovery.os.replace",
        fail_replace,
    )
    with pytest.raises(RecuperacaoImportacaoBloqueadaError, match="atomicamente"):
        store.escrever(prepared.avancar(FaseJournalImportacao.ARQUIVOS_TROCADOS))

    assert store.journal_path.read_bytes() == previous_bytes
    assert not tuple(store.recovery_root.glob(".z-*.tmp"))


@pytest.mark.parametrize("hostile_path", ["../outside", "C:/outside", "/outside", "a\\b"])
def test_corrupted_or_hostile_journal_blocks_without_touching_external_paths(
    tmp_path: Path,
    hostile_path: str,
) -> None:
    store = ArmazenamentoJournalImportacao(tmp_path)
    store.escrever(_journal())
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("preservar", encoding="utf-8")
    payload = json.loads(store.journal_path.read_text(encoding="utf-8"))
    payload["paths"]["project"] = hostile_path
    store.journal_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RecuperacaoImportacaoBloqueadaError, match="caminhos do journal"):
        RecuperadorImportacaoProjeto(tmp_path).reconciliar(lambda _operation_id: None)

    assert sentinel.read_text(encoding="utf-8") == "preservar"
    assert store.journal_path.exists()


def test_invalid_json_and_orphan_workspace_block_without_cleanup(tmp_path: Path) -> None:
    store = ArmazenamentoJournalImportacao(tmp_path)
    store.recovery_root.mkdir(parents=True)
    store.journal_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(RecuperacaoImportacaoBloqueadaError, match="corrompido"):
        RecuperadorImportacaoProjeto(tmp_path).reconciliar(lambda _operation_id: None)

    store.journal_path.unlink()
    orphan = store.recovery_root / str(OPERATION_ID)
    orphan.mkdir()
    sentinel = orphan / "keep.txt"
    sentinel.write_text("preservar", encoding="utf-8")
    with pytest.raises(RecuperacaoImportacaoBloqueadaError, match="resíduos sem journal"):
        RecuperadorImportacaoProjeto(tmp_path).reconciliar(lambda _operation_id: None)
    assert sentinel.exists()


def test_ambiguous_managed_tree_blocks_and_never_deletes_it(tmp_path: Path) -> None:
    store = ArmazenamentoJournalImportacao(tmp_path)
    journal = _journal()
    store.escrever(journal)
    paths = store.preparar_workspace(journal)
    paths.project.mkdir()
    sentinel = paths.project / "unknown.txt"
    sentinel.write_text("não pertence ao journal", encoding="utf-8")
    unknown_digest = fingerprint_arvore_gerenciada(paths.project)

    with pytest.raises(RecuperacaoImportacaoBloqueadaError, match="ambíguo"):
        RecuperadorImportacaoProjeto(tmp_path).reconciliar(lambda _operation_id: None)

    assert fingerprint_arvore_gerenciada(paths.project) == unknown_digest
    assert sentinel.exists()
    assert store.journal_path.exists()


@pytest.mark.parametrize("committed", [False, True])
def test_recovery_resumes_after_its_cleanup_is_interrupted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    committed: bool,
) -> None:
    store = ArmazenamentoJournalImportacao(tmp_path)
    project_root = store.managed_root / str(PROJECT_ID)
    project_root.mkdir(parents=True)
    (project_root / "state.bin").write_bytes(b"old")
    previous_digest = fingerprint_arvore_gerenciada(project_root)
    assert previous_digest is not None
    new_file_digest = sha256(b"new").hexdigest()
    new_tree_digest = fingerprint_arquivos_esperados((("state.bin", len(b"new"), new_file_digest),))
    journal = JournalImportacaoProjeto.novo(
        operation_id=OPERATION_ID,
        project_id=PROJECT_ID,
        package_sha256=PACKAGE_SHA256,
        plan_sha256=PLAN_SHA256,
        target_state_sha256=TARGET_SHA256,
        new_files_sha256=new_tree_digest,
        previous_files_sha256=previous_digest,
        previous_assets_existed=True,
        created_at=datetime(2026, 8, 6, 12, tzinfo=UTC),
    )
    store.escrever(journal)
    paths = store.preparar_workspace(journal)
    (paths.staging / "state.bin").write_bytes(b"new")
    journal = journal.avancar(FaseJournalImportacao.PREPARADO)
    store.escrever(journal)
    project_root.replace(paths.previous)
    paths.staging.replace(project_root)
    journal = journal.avancar(FaseJournalImportacao.ARQUIVOS_TROCADOS)
    store.escrever(journal)
    receipt = ComprovanteCommitImportacao(
        operacao_id=OPERATION_ID,
        projeto_id=PROJECT_ID,
        pacote_sha256=PACKAGE_SHA256,
        plano_sha256=PLAN_SHA256,
        arquivos_sha256=new_tree_digest,
        confirmado_em=datetime(2026, 8, 6, 12, 1, tzinfo=UTC),
    )

    def get_receipt(_operation_id: UUID) -> ComprovanteCommitImportacao | None:
        return receipt if committed else None

    def interrupt_cleanup(_path: Path) -> None:
        raise OSError("queda durante a limpeza")

    with monkeypatch.context() as patch:
        patch.setattr(
            "zeny_project_handler.application.import_recovery.shutil.rmtree",
            interrupt_cleanup,
        )
        with pytest.raises(RecuperacaoImportacaoBloqueadaError, match="interrompida"):
            RecuperadorImportacaoProjeto(tmp_path).reconciliar(get_receipt)

    expected_action = "commit_completed" if committed else "previous_restored"
    recovery = RecuperadorImportacaoProjeto(tmp_path)
    assert recovery.reconciliar(get_receipt) == expected_action
    assert (project_root / "state.bin").read_bytes() == (b"new" if committed else b"old")
    assert recovery.reconciliar(get_receipt) is None
    assert not tuple(store.recovery_root.iterdir())
