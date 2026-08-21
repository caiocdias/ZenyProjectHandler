"""Construa wheel interno e ZIP Windows autocontido do cliente magro."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERSION = "0.2.0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--output-root", type=Path, default=ROOT / "dist" / "client")
    arguments = parser.parse_args()
    if sys.platform != "win32" or platform.machine().casefold() not in {"amd64", "x86_64"}:
        raise SystemExit("O bundle oficial da Etapa 9 deve ser construído em Windows x64")
    version = arguments.version
    output = arguments.output_root.resolve() / version
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    work = ROOT / "build" / "client" / version
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    wheelhouse = output / "wheel"
    wheelhouse.mkdir()
    _run(
        sys.executable,
        "-m",
        "pip",
        "wheel",
        str(ROOT / "client"),
        "--no-deps",
        "--no-build-isolation",
        "--wheel-dir",
        str(wheelhouse),
    )
    wheel = next(wheelhouse.glob("zeny_project_handler_client-*.whl"))

    bundle_dist = work / "dist"
    _run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(bundle_dist),
        "--workpath",
        str(work / "pyinstaller"),
        str(ROOT / "client" / "zeny-client.spec"),
    )
    bundle = bundle_dist / "ZenyProjectHandler"
    shutil.copy2(ROOT / "client" / "LEIA-ME-CLIENTE.md", bundle / "LEIA-ME-CLIENTE.md")
    sbom = _sbom(version)
    _write_json(bundle / "client-sbom.json", sbom)
    bundle_manifest = {
        "schema_version": 1,
        "artifact": f"ZenyProjectHandler-Client-{version}-win-x64",
        "client_version": version,
        "files": _file_records(bundle, excluded={"client-bundle-manifest.json"}),
    }
    _write_json(bundle / "client-bundle-manifest.json", bundle_manifest)

    zip_path = output / f"ZenyProjectHandler-Client-{version}-win-x64.zip"
    _portable_zip(bundle, zip_path, f"ZenyProjectHandler-Client-{version}-win-x64")
    outer_sbom = output / "client-sbom.json"
    _write_json(outer_sbom, sbom)
    artifact_manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "client_version": version,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "artifacts": [_record(wheel), _record(zip_path), _record(outer_sbom)],
    }
    manifest_path = output / "client-manifest.json"
    _write_json(manifest_path, artifact_manifest)
    _run(
        sys.executable,
        str(ROOT / "scripts" / "client_artifact_gate.py"),
        "--wheel",
        str(wheel),
        "--zip",
        str(zip_path),
        "--manifest",
        str(manifest_path),
    )
    print(json.dumps(artifact_manifest, ensure_ascii=False, indent=2))
    return 0


def _run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def _record(path: Path) -> dict[str, object]:
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _file_records(directory: Path, *, excluded: set[str]) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(directory).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name not in excluded
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _sbom(version: str) -> dict[str, object]:
    components: list[dict[str, str]] = [
        {
            "type": "application",
            "name": "zeny-project-handler-client",
            "version": version,
        }
    ]
    for raw_line in (ROOT / "requirements-client.lock").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, locked_version = line.split("==", maxsplit=1)
        components.append({"type": "library", "name": name, "version": locked_version})
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "components": components,
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _portable_zip(source: Path, destination: Path, root_name: str) -> None:
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = Path(root_name) / path.relative_to(source)
            info = ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)


if __name__ == "__main__":
    raise SystemExit(main())
