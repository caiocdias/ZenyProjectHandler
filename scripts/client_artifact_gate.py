"""Falhe se fonte, wheel ou bundle cliente contiverem runtime protegido."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
CLIENT_SOURCE = ROOT / "src" / "zeny_project_handler_client"
FORBIDDEN_IMPORTS = (
    "alembic",
    "fitz",
    "pymupdf",
    "sqlite3",
    "sqlalchemy",
    "zipfile",
    "zeny_project_handler",
    "zeny_project_handler_api_spec",
    "zeny_project_handler_server",
)
FORBIDDEN_DEPENDENCIES = ("alembic", "pymupdf", "sqlalchemy", "tesseract")
FORBIDDEN_PATH_PARTS = (
    "/adapters/",
    "/application/",
    "/domain/",
    "/migrations/",
    "/ports/",
    "analysis-cache",
    "regras_conformidade",
    "regras_interpretacao",
    ".sqlite",
)
FORBIDDEN_ARCHIVE_TOKENS = (
    "zeny_project_handler.adapters",
    "zeny_project_handler.application",
    "zeny_project_handler.domain",
    "zeny_project_handler.ports",
    "zeny_project_handler_server",
    "sqlalchemy",
    "alembic",
    "pymupdf",
    "fitz",
    "sqlite3",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--zip", dest="bundle_zip", type=Path)
    parser.add_argument("--manifest", type=Path)
    arguments = parser.parse_args()
    violations = _source_violations()
    if not arguments.source_only:
        if arguments.wheel is None or arguments.bundle_zip is None:
            parser.error("--wheel e --zip são obrigatórios fora de --source-only")
        violations.extend(_wheel_violations(arguments.wheel))
        violations.extend(_bundle_violations(arguments.bundle_zip))
        if arguments.manifest is not None:
            violations.extend(
                _outer_manifest_violations(
                    arguments.manifest,
                    (arguments.wheel, arguments.bundle_zip),
                )
            )
    if violations:
        print("GATE DO CLIENTE: REPROVADO")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("GATE DO CLIENTE: APROVADO")
    print("Fonte e artefatos contêm somente UI, transporte, contratos e assets permitidos.")
    return 0


def _source_violations() -> list[str]:
    violations: list[str] = []
    for path in sorted(CLIENT_SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            for module in modules:
                if module == "zeny_project_handler_client" or module.startswith(
                    "zeny_project_handler_client."
                ):
                    continue
                if module == "zeny_project_handler_contracts" or module.startswith(
                    "zeny_project_handler_contracts."
                ):
                    continue
                if any(
                    module == item or module.startswith(f"{item}.") for item in FORBIDDEN_IMPORTS
                ):
                    violations.append(
                        f"import protegido em {path.relative_to(ROOT)}:{node.lineno}: {module}"
                    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in CLIENT_SOURCE.rglob("*.py"))
    if "ZENY_SERVER_PASSWORD" in source:
        violations.append("o cliente lê ou referencia ZENY_SERVER_PASSWORD")
    return violations


def _wheel_violations(path: Path) -> list[str]:
    violations: list[str] = []
    with ZipFile(path) as archive:
        names = archive.namelist()
        if not any(name.startswith("zeny_project_handler_client/") for name in names):
            violations.append("wheel não contém zeny_project_handler_client")
        if not any(name.startswith("zeny_project_handler_contracts/") for name in names):
            violations.append("wheel não contém os contratos")
        for name in names:
            normalized = f"/{name.casefold()}"
            if name.startswith(("zeny_project_handler/", "zeny_project_handler_server/")):
                violations.append(f"pacote protegido no wheel: {name}")
            if any(part in normalized for part in FORBIDDEN_PATH_PARTS):
                violations.append(f"arquivo protegido no wheel: {name}")
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(metadata_name))
        for requirement in metadata.get_all("Requires-Dist", []):
            normalized = requirement.casefold()
            if any(name in normalized for name in FORBIDDEN_DEPENDENCIES):
                violations.append(f"dependência protegida no wheel: {requirement}")
    return violations


def _bundle_violations(path: Path) -> list[str]:
    violations: list[str] = []
    with ZipFile(path) as archive:
        names = archive.namelist()
        lowered = [name.casefold() for name in names]
        if not any(name.endswith("/zenyprojecthandler.exe") for name in lowered):
            violations.append("ZIP não contém ZenyProjectHandler.exe")
        if any(name.endswith((".py", ".pyc", ".sqlite", ".sqlite3")) for name in lowered):
            violations.append("ZIP contém fonte/bytecode Python ou SQLite")
        for name in lowered:
            normalized = f"/{name}"
            if any(part in normalized for part in FORBIDDEN_PATH_PARTS):
                violations.append(f"arquivo protegido no ZIP: {name}")
        manifest_name = next(
            (name for name in names if name.endswith("/client-bundle-manifest.json")),
            None,
        )
        sbom_name = next((name for name in names if name.endswith("/client-sbom.json")), None)
        executable_name = next(
            (name for name in names if name.casefold().endswith("/zenyprojecthandler.exe")),
            None,
        )
        if manifest_name is None or sbom_name is None or executable_name is None:
            return [*violations, "ZIP não contém manifesto, SBOM e executável obrigatórios"]
        manifest = json.loads(archive.read(manifest_name))
        root = PurePosixPath(manifest_name).parent
        for record in manifest.get("files", []):
            member = (root / record["path"]).as_posix()
            payload = archive.read(member)
            size_mismatch = len(payload) != record["size_bytes"]
            hash_mismatch = hashlib.sha256(payload).hexdigest() != record["sha256"]
            if size_mismatch or hash_mismatch:
                violations.append(f"hash/tamanho divergente no bundle: {record['path']}")
        sbom = json.loads(archive.read(sbom_name))
        for component in sbom.get("components", []):
            name = str(component.get("name", "")).casefold()
            if any(item in name for item in FORBIDDEN_DEPENDENCIES):
                violations.append(f"dependência protegida no SBOM: {name}")
        violations.extend(_pyinstaller_archive_violations(path, archive.read(executable_name)))
    return violations


def _pyinstaller_archive_violations(zip_path: Path, executable: bytes) -> list[str]:
    temporary = zip_path.with_suffix(".gate-executable.tmp.exe")
    try:
        temporary.write_bytes(executable)
        command = [
            sys.executable,
            "-m",
            "PyInstaller.utils.cliutils.archive_viewer",
            "-l",
            "-r",
            str(temporary),
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            return ["não foi possível abrir o arquivo PyInstaller para inspeção"]
        listing = completed.stdout.casefold()
        return [
            f"módulo protegido no executável: {token}"
            for token in FORBIDDEN_ARCHIVE_TOKENS
            if token in listing
        ]
    finally:
        temporary.unlink(missing_ok=True)


def _outer_manifest_violations(manifest_path: Path, artifacts: tuple[Path, ...]) -> list[str]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in payload.get("artifacts", [])}
    violations = []
    for path in artifacts:
        record = by_name.get(path.name)
        if record is None:
            violations.append(f"artefato ausente do manifesto: {path.name}")
        elif record["size_bytes"] != path.stat().st_size or record["sha256"] != _sha256(path):
            violations.append(f"hash/tamanho externo divergente: {path.name}")
    return violations


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
