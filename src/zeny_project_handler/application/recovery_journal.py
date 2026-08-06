"""Primitivas compartilhadas por journals locais de recuperação."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath

from zeny_project_handler._atomic_files import sibling_temporary_file

JournalErrorFactory = Callable[[str], BaseException]


def read_json_object(
    path: Path,
    *,
    max_bytes: int,
    error: JournalErrorFactory,
) -> dict[str, object]:
    """Leia um objeto JSON pequeno, regular e sem chaves duplicadas."""
    if path.is_symlink() or not path.is_file():
        raise error("o journal não é um arquivo regular")
    try:
        size = path.stat().st_size
    except OSError as caught:
        raise error("o journal não pôde ser inspecionado") from caught
    if size > max_bytes:
        raise error("o journal excede o limite de tamanho")
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw, object_pairs_hook=_object_without_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as caught:
        raise error("o journal está corrompido ou ilegível") from caught
    if not isinstance(payload, dict):
        raise error("a estrutura do journal é inválida")
    return payload


def write_json_object_atomic(
    path: Path,
    payload: object,
    *,
    max_bytes: int,
    error: JournalErrorFactory,
) -> None:
    """Publique JSON canônico por temporário irmão, ``fsync`` e ``replace``."""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise error("o journal excede o limite de tamanho")
    try:
        with sibling_temporary_file(path) as temporary:
            with temporary.open("wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
    except OSError as caught:
        raise error("o journal não pôde ser publicado atomicamente") from caught


def validated_relative_path(value: str, *, error: JournalErrorFactory) -> PurePosixPath:
    """Aceite somente caminhos POSIX relativos, sem travessia nem semântica Windows."""
    if not value or "\\" in value:
        raise error("o journal contém caminho relativo inválido")
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or any(part in {"", ".", ".."} for part in posix_path.parts)
    ):
        raise error("o journal contém caminho fora da raiz gerenciada")
    return posix_path


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate journal field")
        result[key] = value
    return result
