"""Valide estrutura, integridade e isolamento dos arquivos exatos da release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from tarfile import TarFile
from tarfile import open as open_tar

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_CLIENT_COMPONENTS = {"alembic", "pymupdf", "sqlalchemy", "tesseract"}
FORBIDDEN_SERVER_COMPONENTS = {"pyside6", "pyside6_addons", "pyside6_essentials", "shiboken6"}
PLACEHOLDER = "troque-por-uma-senha-longa-e-aleatoria"
MARKET_CONNECTION_PLACEHOLDER = "troque-por-uma-string-de-conexao-sql-server"
MARKET_TIMEOUT = "15"


class ReleaseGateError(RuntimeError):
    """Violação do contrato físico da release."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--client-manifest", type=Path, required=True)
    parser.add_argument("--pyinstaller-python", type=Path, default=Path(sys.executable))
    parser.add_argument("--image")
    arguments = parser.parse_args()
    try:
        report = validate_release(
            arguments.release_dir.resolve(),
            wheel=arguments.wheel.resolve(),
            client_manifest=arguments.client_manifest.resolve(),
            pyinstaller_python=arguments.pyinstaller_python.resolve(),
            image=arguments.image,
        )
    except (OSError, ReleaseGateError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"GATE DA RELEASE: REPROVADO — {error}")
        return 1
    print("GATE DA RELEASE: APROVADO")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def validate_release(
    release_dir: Path,
    *,
    wheel: Path,
    client_manifest: Path,
    pyinstaller_python: Path = Path(sys.executable),
    image: str | None,
) -> dict[str, object]:
    manifest_path = release_dir / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = str(manifest["release_version"])
    expected = _expected_paths(version)
    actual = {
        path.relative_to(release_dir).as_posix()
        for path in release_dir.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ReleaseGateError(f"estrutura divergente; ausentes={missing}, extras={extra}")
    payloads = actual - {"release-manifest.json", "SHA256SUMS.txt"}
    records = {str(item["path"]): item for item in manifest["files"]}
    if records.keys() != payloads:
        raise ReleaseGateError("o manifesto não cobre exatamente todos os payloads da release")
    for relative, record in records.items():
        _validate_record(release_dir / relative, record)
    _validate_sha256s(release_dir, actual)
    _validate_distribution_sets(manifest, expected)
    image_record = dict(manifest["server"]["image"])
    image_reference = str(image_record["reference"])
    if image is not None and image != image_reference:
        raise ReleaseGateError("a imagem validada diverge da referência do manifesto")
    _validate_compose_and_environment(release_dir, image_reference)
    _validate_sboms(release_dir, version)
    _validate_server_archive(release_dir / str(image_record["archive"]), image_reference)
    _validate_guides(release_dir, version, image_reference, str(image_record["id_digest"]))

    client_zip = release_dir / "client" / f"ZenyProjectHandler-Client-{version}-win-x64.zip"
    _run_checked(
        [
            sys.executable,
            str(ROOT / "scripts" / "client_artifact_gate.py"),
            "--wheel",
            str(wheel),
            "--zip",
            str(client_zip),
            "--manifest",
            str(client_manifest),
            "--pyinstaller-python",
            str(pyinstaller_python),
        ],
        "gate interno do cliente",
    )
    if image is not None:
        _validate_loaded_image(image, str(image_record["id_digest"]), version)
        _run_checked(
            [
                sys.executable,
                str(ROOT / "scripts" / "server_artifact_gate.py"),
                "--image",
                image,
            ],
            "gate interno do servidor",
        )
    return {
        "release_version": version,
        "files": len(actual),
        "manifest_payloads": len(records),
        "sha256_entries": len(actual) - 1,
        "compose_without_build": True,
        "client_isolated": True,
        "server_isolated": image is not None,
        "image_reference": image_reference,
        "image_digest": image_record["id_digest"],
    }


def _expected_paths(version: str) -> set[str]:
    return {
        f"client/ZenyProjectHandler-Client-{version}-win-x64.zip",
        "client/LEIA-ME-CLIENTE.md",
        "client/client-sbom.json",
        f"server/ZenyProjectHandler-Server-{version}.oci.tar",
        "server/compose.release.yaml",
        "server/.env-example",
        "server/LEIA-ME-SERVIDOR.md",
        "server/server-sbom.json",
        "server/THIRD_PARTY_NOTICES.md",
        "RELEASE_NOTES.md",
        "release-manifest.json",
        "SHA256SUMS.txt",
    }


def _validate_record(path: Path, record: dict[str, object]) -> None:
    if path.stat().st_size != int(record["size_bytes"]) or _sha256(path) != record["sha256"]:
        raise ReleaseGateError(f"tamanho/hash divergente no manifesto: {path.name}")


def _validate_sha256s(release_dir: Path, actual: set[str]) -> None:
    entries: dict[str, str] = {}
    for line in (release_dir / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if not separator or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ReleaseGateError("linha inválida em SHA256SUMS.txt")
        entries[relative] = digest
    expected = actual - {"SHA256SUMS.txt"}
    if entries.keys() != expected:
        raise ReleaseGateError("SHA256SUMS.txt não cobre exatamente os arquivos distribuídos")
    for relative, digest in entries.items():
        if _sha256(release_dir / relative) != digest:
            raise ReleaseGateError(f"SHA-256 divergente: {relative}")


def _validate_distribution_sets(manifest: dict[str, object], expected: set[str]) -> None:
    sets = dict(manifest["distribution_sets"])
    combined = {
        str(path)
        for name in ("client_user", "server_administrator", "common_integrity")
        for path in sets[name]
    }
    if combined != expected:
        raise ReleaseGateError("os conjuntos físicos de distribuição não cobrem a release")
    client_set = {str(item) for item in sets["client_user"]}
    server_set = {str(item) for item in sets["server_administrator"]}
    if client_set & server_set:
        raise ReleaseGateError("cliente e servidor compartilham payload físico indevido")
    if any(not item.startswith("client/") for item in client_set):
        raise ReleaseGateError("conjunto do usuário contém arquivo que não pertence ao cliente")
    if any(not item.startswith("server/") for item in server_set):
        raise ReleaseGateError(
            "conjunto do administrador contém arquivo que não pertence ao servidor"
        )


def _validate_compose_and_environment(release_dir: Path, image_reference: str) -> None:
    server = release_dir / "server"
    compose = server / "compose.release.yaml"
    text = compose.read_text(encoding="utf-8")
    if re.search(r"(?m)^\s*build\s*:", text) or "image:" not in text:
        raise ReleaseGateError("compose.release.yaml deve usar image: e não pode conter build:")
    environment_path = server / ".env-example"
    environment = environment_path.read_text(encoding="utf-8")
    if f"ZENY_SERVER_PASSWORD={PLACEHOLDER}" not in environment:
        raise ReleaseGateError(".env-example não contém o placeholder fail-closed esperado")
    if (
        "ZENY_MARKET_SQLSERVER_CONNECTION_STRING="
        f"{MARKET_CONNECTION_PLACEHOLDER}" not in environment
    ):
        raise ReleaseGateError(".env-example não contém o placeholder fail-closed do SQL Server")
    if f"ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS={MARKET_TIMEOUT}" not in environment:
        raise ReleaseGateError(".env-example não fixa o timeout SQL Server esperado")
    if f"ZENY_SERVER_IMAGE={image_reference}" not in environment:
        raise ReleaseGateError(".env-example não fixa a tag da release")
    if "ZENY_CLIENT" in environment or "@ZENY_" in environment:
        raise ReleaseGateError(
            ".env-example do servidor contém opção de cliente ou token não renderizado"
        )
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(environment_path),
            "-f",
            str(compose),
            "config",
            "--format",
            "json",
        ],
        cwd=server,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ReleaseGateError(f"Compose de release inválido: {completed.stderr.strip()}")
    configuration = json.loads(completed.stdout)
    service = configuration["services"]["server"]
    if "build" in service or service.get("image") != image_reference:
        raise ReleaseGateError("configuração resolvida do Compose diverge da imagem da release")
    service_environment = service.get("environment", {})
    if (
        not isinstance(service_environment, dict)
        or service_environment.get("ZENY_MARKET_SQLSERVER_CONNECTION_STRING")
        != MARKET_CONNECTION_PLACEHOLDER
    ):
        raise ReleaseGateError("Compose não preserva a conexão SQL Server somente em runtime")
    if str(service_environment.get("ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS")) != MARKET_TIMEOUT:
        raise ReleaseGateError("Compose não preserva o timeout SQL Server positivo")


def _validate_sboms(release_dir: Path, version: str) -> None:
    client = json.loads((release_dir / "client" / "client-sbom.json").read_text(encoding="utf-8"))
    server = json.loads((release_dir / "server" / "server-sbom.json").read_text(encoding="utf-8"))
    for name, sbom in (("cliente", client), ("servidor", server)):
        if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.5":
            raise ReleaseGateError(f"SBOM do {name} não é CycloneDX 1.5")
    client_components = {str(item["name"]).casefold() for item in client["components"]}
    server_components = {str(item["name"]).casefold() for item in server["components"]}
    if FORBIDDEN_CLIENT_COMPONENTS & client_components:
        raise ReleaseGateError("SBOM do cliente contém dependência exclusiva do servidor")
    if FORBIDDEN_SERVER_COMPONENTS & server_components:
        raise ReleaseGateError("SBOM do servidor contém Qt/cliente")
    if "zeny-project-handler-client" not in client_components:
        raise ReleaseGateError("SBOM do cliente não identifica a aplicação")
    if "zeny-project-handler-server" not in server_components:
        raise ReleaseGateError("SBOM do servidor não identifica a aplicação")
    if (
        not {
            "msodbcsql18",
            "pymupdf",
            "pyodbc",
            "sqlalchemy",
            "tesseract-ocr",
            "unixodbc",
        }
        <= server_components
    ):
        raise ReleaseGateError(
            "SBOM do servidor não cobre runtimes Python, OCR e ODBC obrigatórios"
        )
    server_versions = {
        str(item["name"]).casefold(): str(item["version"]) for item in server["components"]
    }
    expected_odbc_versions = {
        "pyodbc": "5.3.0",
        "msodbcsql18": "18.6.2.1-1",
        "unixodbc": "2.3.11-2+deb12u1",
    }
    if any(
        server_versions.get(name) != version for name, version in expected_odbc_versions.items()
    ):
        raise ReleaseGateError("SBOM do servidor diverge das versões ODBC fixadas")
    applications = [item for item in client["components"] if item["type"] == "application"]
    if not applications or applications[0]["version"] != version:
        raise ReleaseGateError("versão do cliente diverge em sua SBOM")


def _validate_server_archive(path: Path, image_reference: str) -> None:
    with open_tar(path, mode="r") as archive:
        names = set(archive.getnames())
        if "manifest.json" not in names or not (
            {"index.json", "oci-layout"} <= names or "repositories" in names
        ):
            raise ReleaseGateError("archive da imagem não é carregável por docker load")
        if any(PurePosixPath(name).name == ".env" for name in names):
            raise ReleaseGateError("archive da imagem contém membro .env")
        docker_manifest = _tar_json(archive, "manifest.json")
        oci_index = _tar_json(archive, "index.json") if "index.json" in names else None
    if not isinstance(docker_manifest, list) or not docker_manifest:
        raise ReleaseGateError("manifest.json do archive não contém imagem")
    tags = {
        str(tag)
        for item in docker_manifest
        if isinstance(item, dict)
        for tag in item.get("RepoTags", ())
    }
    if image_reference not in tags:
        raise ReleaseGateError("archive da imagem não contém a tag de release esperada")
    if oci_index is not None and (
        not isinstance(oci_index, dict) or oci_index.get("schemaVersion") != 2
    ):
        raise ReleaseGateError("index OCI do archive é inválido")


def _tar_json(archive: TarFile, name: str) -> object:
    member = archive.extractfile(name)
    if member is None:
        raise ReleaseGateError(f"membro ausente no archive: {name}")
    return json.loads(member.read())


def _validate_guides(release_dir: Path, version: str, image: str, digest: str) -> None:
    client = (release_dir / "client" / "LEIA-ME-CLIENTE.md").read_text(encoding="utf-8")
    server = (release_dir / "server" / "LEIA-ME-SERVIDOR.md").read_text(encoding="utf-8")
    notes = (release_dir / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    notices = (release_dir / "server" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    if "ZenyProjectHandler.exe" not in client or "senha nunca é salva" not in client:
        raise ReleaseGateError("guia do cliente não cobre execução/conexão segura")
    required = (
        version,
        image,
        digest,
        "docker load",
        "--no-build",
        "down -v",
        "rollback",
        "firewall",
        "ZENY_MARKET_SQLSERVER_CONNECTION_STRING",
        "TrustServerCertificate=no",
        "SELECT",
    )
    if any(item.casefold() not in server.casefold() for item in required):
        raise ReleaseGateError("guia do servidor não cobre instalação/operação/rollback completos")
    if version not in notes or API_VERSION not in notes or ALEMBIC_REVISION not in notes:
        raise ReleaseGateError("release notes não registram versões de produto/API/schema")
    for component in ("pyodbc", "msodbcsql18", "unixODBC"):
        if component.casefold() not in notices.casefold():
            raise ReleaseGateError(f"notices do servidor omitem {component}")
    if "@IMAGE_" in server or "@RELEASE_" in server:
        raise ReleaseGateError("guia do servidor contém token não renderizado")


def _validate_loaded_image(image: str, digest: str, version: str) -> None:
    completed = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ReleaseGateError("imagem declarada não está carregada para inspeção")
    metadata = json.loads(completed.stdout)[0]
    labels = metadata.get("Config", {}).get("Labels", {}) or {}
    if metadata.get("Id") != digest or labels.get("org.opencontainers.image.version") != version:
        raise ReleaseGateError("digest/label da imagem carregada diverge do manifesto")


def _run_checked(command: list[str], description: str) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ReleaseGateError(f"{description} falhou: {detail[-1000:]}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


API_VERSION = "1.1.0"
ALEMBIC_REVISION = "0009_remote_jobs"


if __name__ == "__main__":
    raise SystemExit(main())
