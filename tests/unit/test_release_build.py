from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts.build_release import (
    ReleaseBuildError,
    _render_server_environment,
    _validate_version,
    _write_sha256s,
)
from scripts.release_artifact_gate import _validate_sha256s

ROOT = Path(__file__).resolve().parents[2]


def test_release_version_must_be_stable_semver_and_match_all_packages() -> None:
    _validate_version("0.1.0")

    for invalid in ("1", "1.0", "01.0.0", "1.0.0-rc.1", "v1.0.0", "0.2.0"):
        with pytest.raises(ReleaseBuildError):
            _validate_version(invalid)


def test_release_compose_is_image_only_and_server_environment_is_separate(tmp_path: Path) -> None:
    compose = (ROOT / "server" / "compose.release.yaml").read_text(encoding="utf-8")
    assert "image:" in compose
    assert "build:" not in compose
    assert "zeny-data:/data" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose

    destination = tmp_path / ".env-example"
    _render_server_environment("zeny-project-handler-server:0.1.0", destination)
    environment = destination.read_text(encoding="utf-8")
    assert "ZENY_SERVER_IMAGE=zeny-project-handler-server:0.1.0" in environment
    assert "ZENY_SERVER_PASSWORD=troque-por-uma-senha-longa-e-aleatoria" in environment
    assert "ZENY_CLIENT" not in environment
    assert "@ZENY_SERVER_IMAGE@" not in environment


def test_release_sources_document_load_lifecycle_backup_and_rollback() -> None:
    guide = (ROOT / "server" / "LEIA-ME-SERVIDOR.md").read_text(encoding="utf-8").casefold()
    for requirement in (
        "docker load",
        "--no-build",
        "health",
        "firewall",
        "down -v",
        "backup",
        "atualizar",
        "rollback",
        "trocar a senha",
    ):
        assert requirement in guide
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "org.opencontainers.image.version" in dockerfile
    assert "ZENY_RELEASE_VERSION" in dockerfile


def test_sha256_index_covers_every_distributed_file_except_itself(tmp_path: Path) -> None:
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "artifact.zip").write_bytes(b"cliente")
    manifest = tmp_path / "release-manifest.json"
    manifest.write_text(json.dumps({"release": "fixture"}), encoding="utf-8")

    _write_sha256s(tmp_path)
    actual = {
        path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()
    }
    _validate_sha256s(tmp_path, actual)
    entries = (tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert hashlib.sha256(b"cliente").hexdigest() in entries
    assert "client/artifact.zip" in entries
    assert "release-manifest.json" in entries
    assert "SHA256SUMS.txt" not in entries
