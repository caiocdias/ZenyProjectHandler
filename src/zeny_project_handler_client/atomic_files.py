"""Publicação atômica de downloads escolhidos pelo usuário."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from tempfile import NamedTemporaryFile


@contextmanager
def sibling_temporary_file(destination: Path) -> Iterator[Path]:
    """Crie um temporário irmão e remova qualquer resto ao sair."""
    temporary_path: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="wb",
            prefix=".z-",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        yield temporary_path
    finally:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
