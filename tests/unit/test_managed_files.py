from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from tests.factories import complete_project

from zeny_project_handler.application.errors import RecuperacaoLimpezaBloqueadaError
from zeny_project_handler.application.managed_files import GerenciadorArquivosGerenciados
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.project import FotoElemento, Projeto


def _photo(photo_id: UUID, payload: bytes) -> FotoElemento:
    digest = sha256(payload).hexdigest()
    return FotoElemento(
        id=photo_id,
        caminho_relativo=f"photos/{digest}.png",
        sha256=digest,
        tipo_mime="image/png",
        tamanho_bytes=len(payload),
    )


def _manager(
    data: Path,
    state: list[Projeto],
    *,
    remover_arvore: Callable[[Path], None] = shutil.rmtree,
    remover_arquivo: Callable[[Path], None] | None = None,
) -> GerenciadorArquivosGerenciados:
    return GerenciadorArquivosGerenciados(
        data,
        lambda: tuple(state),
        remover_arvore=remover_arvore,
        remover_arquivo=remover_arquivo,
    )


def test_shared_digest_is_removed_only_after_last_live_reference(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    payload = b"shared-photo"
    base = complete_project(catalogo_inicial)
    first_photo = _photo(base.elementos[0].fotos[0].id, payload)
    second_photo = replace(first_photo, id=base.elementos[1].id)
    first_element = replace(base.elementos[0], fotos=(first_photo,))
    second_element = replace(base.elementos[1], fotos=(second_photo,))
    project = replace(base, elementos=(first_element, second_element, *base.elementos[2:]))
    state = [project]
    manager = _manager(tmp_path, state)
    managed_file = tmp_path / "project-files" / str(project.id) / first_photo.caminho_relativo
    managed_file.parent.mkdir(parents=True)
    managed_file.write_bytes(payload)

    after_first = replace(
        project,
        elementos=(replace(first_element, fotos=()), second_element, *project.elementos[2:]),
    )
    first_task = manager.preparar_coleta_fotos(project.id, (first_photo,))
    state[:] = [after_first]
    first_result = manager.concluir(first_task)

    assert first_result.arquivos_removidos == 0
    assert not first_result.pendente
    assert managed_file.is_file()

    after_second = replace(
        after_first,
        elementos=(
            after_first.elementos[0],
            replace(second_element, fotos=()),
            *project.elementos[2:],
        ),
    )
    second_task = manager.preparar_coleta_fotos(project.id, (second_photo,))
    state[:] = [after_second]
    second_result = manager.concluir(second_task)

    assert second_result.arquivos_removidos == 1
    assert not second_result.pendente
    assert not managed_file.exists()


def test_project_tombstone_is_restored_on_rollback(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    state = [project]
    manager = _manager(tmp_path, state)
    project_root = tmp_path / "project-files" / str(project.id)
    project_root.mkdir(parents=True)
    (project_root / "managed.bin").write_bytes(b"managed")

    task = manager.preparar_exclusao_projeto(project.id)

    assert not project_root.exists()
    assert manager.armazenamento.tombstone_path(task).is_dir()
    manager.cancelar(task)
    assert (project_root / "managed.bin").read_bytes() == b"managed"
    assert manager.armazenamento.carregar_todos() == ()


@pytest.mark.parametrize("committed", [False, True])
def test_interrupted_project_deletion_is_reconciled_from_database_state(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
    committed: bool,
) -> None:
    project = complete_project(catalogo_inicial)
    state = [project]
    manager = _manager(tmp_path, state)
    project_root = tmp_path / "project-files" / str(project.id)
    project_root.mkdir(parents=True)
    managed_file = project_root / "managed.bin"
    managed_file.write_bytes(b"managed")

    manager.preparar_exclusao_projeto(project.id)
    if committed:
        state.clear()

    recovered = _manager(tmp_path, state)
    assert recovered.reconciliar_pendencias() == 0
    assert managed_file.exists() is not committed
    assert recovered.armazenamento.carregar_todos() == ()


def test_missing_project_root_is_a_valid_idempotent_deletion(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    state = [project]
    manager = _manager(tmp_path, state)

    task = manager.preparar_exclusao_projeto(project.id)
    state.clear()
    result = manager.concluir(task)

    assert not result.pendente
    assert result.arquivos_removidos == 0
    assert manager.armazenamento.carregar_todos() == ()


def test_post_commit_failure_keeps_journal_for_a_later_retry(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    state = [project]
    project_root = tmp_path / "project-files" / str(project.id)
    project_root.mkdir(parents=True)
    (project_root / "managed.bin").write_bytes(b"managed")

    def fail_cleanup(_path: Path) -> None:
        raise OSError("locked")

    manager = _manager(tmp_path, state, remover_arvore=fail_cleanup)
    task = manager.preparar_exclusao_projeto(project.id)
    state.clear()
    result = manager.concluir(task)

    assert result.pendente
    assert manager.armazenamento.journal_path(task.operation_id).is_file()
    assert manager.armazenamento.tombstone_path(task).is_dir()

    retry = _manager(tmp_path, state)
    assert retry.reconciliar_pendencias() == 0
    assert retry.armazenamento.carregar_todos() == ()
    assert not retry.armazenamento.tombstone_path(task).exists()


def test_partial_post_commit_failure_keeps_blob_and_retries_safely(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    payload = b"locked-photo"
    base = complete_project(catalogo_inicial)
    photo = _photo(base.elementos[0].fotos[0].id, payload)
    element = replace(base.elementos[0], fotos=(photo,))
    project = replace(base, elementos=(element, *base.elementos[1:]))
    updated = replace(project, elementos=(replace(element, fotos=()), *base.elementos[1:]))
    state = [project]
    managed_file = tmp_path / "project-files" / str(project.id) / photo.caminho_relativo
    managed_file.parent.mkdir(parents=True)
    managed_file.write_bytes(payload)

    def fail_unlink(_path: Path) -> None:
        raise OSError("locked")

    manager = _manager(tmp_path, state, remover_arquivo=fail_unlink)
    task = manager.preparar_coleta_fotos(project.id, (photo,))
    state[:] = [updated]
    result = manager.concluir(task)

    assert result.pendente
    assert managed_file.is_file()
    assert task is not None
    assert manager.armazenamento.journal_path(task.operation_id).is_file()

    retry = _manager(tmp_path, state)
    assert retry.reconciliar_pendencias() == 0
    assert not managed_file.exists()
    assert retry.armazenamento.carregar_todos() == ()


def test_legacy_photo_is_hashed_for_cleanup_and_missing_file_needs_no_task(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    legacy = project.elementos[0].fotos[0]
    state = [project]
    manager = _manager(tmp_path, state)
    managed_file = tmp_path / "project-files" / str(project.id) / legacy.caminho_relativo

    assert manager.preparar_coleta_fotos(project.id, (legacy,)) is None

    managed_file.parent.mkdir(parents=True)
    managed_file.write_bytes(b"legacy")
    task = manager.preparar_coleta_fotos(project.id, (legacy,))
    state[:] = [
        replace(
            project,
            elementos=(replace(project.elementos[0], fotos=()), *project.elementos[1:]),
        )
    ]
    result = manager.concluir(task)

    assert result.arquivos_removidos == 1
    assert not managed_file.exists()


@pytest.mark.parametrize(
    ("name", "content", "message"),
    (
        ("unexpected.bin", b"residue", "resíduos sem journal"),
        (f"{'1' * 8}-{'1' * 4}-{'1' * 4}-{'1' * 4}-{'1' * 12}.cleanup-v1.json", b"{", "corrompido"),
    ),
)
def test_invalid_cleanup_recovery_entries_block_without_deleting_them(
    tmp_path: Path,
    name: str,
    content: bytes,
    message: str,
) -> None:
    recovery_root = tmp_path / "project-files" / ".cleanup-recovery"
    recovery_root.mkdir(parents=True)
    entry = recovery_root / name
    entry.write_bytes(content)

    with pytest.raises(RecuperacaoLimpezaBloqueadaError, match=message):
        _manager(tmp_path, []).reconciliar_pendencias()

    assert entry.read_bytes() == content


def test_malicious_journal_path_blocks_bootstrap_without_touching_external_file(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    state = [project]
    manager = _manager(tmp_path, state)
    task = manager.preparar_exclusao_projeto(project.id)
    journal_path = manager.armazenamento.journal_path(task.operation_id)
    payload = json.loads(journal_path.read_text(encoding="utf-8"))
    payload["paths"]["tombstone"] = "../../outside"
    journal_path.write_text(json.dumps(payload), encoding="utf-8")
    external = tmp_path / "outside"
    external.write_bytes(b"preserve")

    with pytest.raises(RecuperacaoLimpezaBloqueadaError, match="fora da raiz gerenciada"):
        _manager(tmp_path, state).reconciliar_pendencias()

    assert external.read_bytes() == b"preserve"
