"""Backup consistente do SQLite com publicação atômica no destino."""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing, suppress
from pathlib import Path
from uuid import uuid4

from .errors import PersistenceError


def create_atomic_backup(database_path: Path, destination: Path) -> Path:
    """Copie um snapshot consistente e substitua o destino somente após validação."""
    source_path = database_path.expanduser().resolve()
    target_path = destination.expanduser().resolve()
    if not source_path.is_file():
        raise PersistenceError("Banco de dados de origem não existe")
    if source_path == target_path:
        raise PersistenceError("Backup deve usar um caminho diferente do banco de origem")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_name(f".{target_path.name}.{uuid4().hex}.tmp")
    try:
        with (
            closing(sqlite3.connect(source_path)) as source,
            closing(sqlite3.connect(temporary_path)) as target,
        ):
            source.backup(target)
            integrity = target.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise PersistenceError("Snapshot SQLite falhou na verificação de integridade")
            target.commit()
        os.replace(temporary_path, target_path)
    except (OSError, sqlite3.Error) as error:
        raise PersistenceError("Não foi possível criar o backup SQLite") from error
    finally:
        with suppress(OSError):
            temporary_path.unlink(missing_ok=True)
    return target_path
