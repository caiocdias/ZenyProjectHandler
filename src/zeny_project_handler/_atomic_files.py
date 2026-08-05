"""Primitivas de temporários irmãos para publicação atômica."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

_TEMPORARY_PREFIX = ".z-"


@contextmanager
def sibling_temporary_file(destination: Path) -> Iterator[Path]:
    """Crie um arquivo curto e exclusivo ao lado do destino e sempre tente removê-lo."""
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            prefix=_TEMPORARY_PREFIX,
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


@contextmanager
def sibling_temporary_directory(destination: Path, *, vacant: bool = False) -> Iterator[Path]:
    """Crie um diretório curto ao lado do destino e remova seu conteúdo ao sair.

    ``vacant`` reserva um nome exclusivo e o libera antes do uso, como exigido por
    ``os.replace`` ao mover um diretório no Windows.
    """
    with TemporaryDirectory(
        prefix=_TEMPORARY_PREFIX,
        dir=destination.parent,
        ignore_cleanup_errors=True,
    ) as temporary_name:
        temporary_path = Path(temporary_name)
        if vacant:
            temporary_path.rmdir()
        yield temporary_path
