from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests.path_fixtures import near_windows_path_limit

from zeny_project_handler._atomic_files import (
    sibling_temporary_directory,
    sibling_temporary_file,
)
from zeny_project_handler.application.errors import PortabilidadeProjetoError
from zeny_project_handler.application.project_portability import _copy_atomic


def test_sibling_temporaries_are_short_unique_and_always_cleaned(tmp_path: Path) -> None:
    destination = tmp_path / ("f" * 64 + ".png")

    with sibling_temporary_file(destination) as first:
        with sibling_temporary_file(destination) as second:
            assert first.exists()
            assert second.exists()
            assert first != second
            assert first.parent == second.parent == destination.parent
            assert len(first.name) <= 15
            assert len(second.name) <= 15
        assert not second.exists()
    assert not first.exists()

    with sibling_temporary_directory(destination) as staging:
        (staging / "partial.txt").write_text("partial", encoding="utf-8")
        assert staging.parent == destination.parent
        assert len(staging.name) <= 11
    assert not staging.exists()

    with sibling_temporary_directory(destination, vacant=True) as recovery:
        assert not recovery.exists()
        assert recovery.parent == destination.parent
        assert len(recovery.name) <= 11
    assert not recovery.exists()


def test_atomic_copy_handles_near_limit_path_and_preserves_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\nportable-photo")
    modified_ns = 1_700_000_000_123_456_700
    os.utime(source, ns=(modified_ns, modified_ns))
    destination = near_windows_path_limit(tmp_path, "f" * 64 + ".png")
    observed: list[Path] = []
    real_replace = os.replace

    def observe_replace(source_path: Path, target_path: Path) -> None:
        observed.append(Path(source_path))
        real_replace(source_path, target_path)

    monkeypatch.setattr(
        "zeny_project_handler.application.project_portability.os.replace",
        observe_replace,
    )

    _copy_atomic(source, destination)

    assert destination.read_bytes() == source.read_bytes()
    assert destination.stat().st_mtime_ns == source.stat().st_mtime_ns
    assert len(observed) == 1
    assert observed[0].parent == destination.parent
    assert len(observed[0].name) <= 15
    assert len(str(observed[0])) < len(str(destination))
    assert set(destination.parent.iterdir()) == {destination}


def test_atomic_copy_failure_preserves_destination_and_removes_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"new-version")
    destination = near_windows_path_limit(tmp_path, "f" * 64 + ".png")
    destination.write_bytes(b"stable-version")

    def interrupt_copy(_source: Path, temporary: Path) -> None:
        Path(temporary).write_bytes(b"partial")
        raise OSError("interrupted")

    monkeypatch.setattr(
        "zeny_project_handler.application.project_portability.shutil.copy2",
        interrupt_copy,
    )

    with pytest.raises(PortabilidadeProjetoError, match="destino gerenciado"):
        _copy_atomic(source, destination)

    assert destination.read_bytes() == b"stable-version"
    assert set(destination.parent.iterdir()) == {destination}
