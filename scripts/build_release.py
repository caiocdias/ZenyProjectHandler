"""Monte a release física e separada do cliente Windows e do servidor Docker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
API_VERSION = "1.0.0"
MIN_COMPATIBLE_API_VERSION = "1.0.0"
MAX_COMPATIBLE_API_VERSION = "1.999.999"
VOLUME_FORMAT_VERSION = 1
ALEMBIC_REVISION = "0009_remote_jobs"
BASE_IMAGE = (
    "python:3.13.7-slim-bookworm@"
    "sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d"
)
DOCKERFILE_FRONTEND = (
    "docker/dockerfile:1@sha256:ecfaec9ed6d810b56388c508f4121597bfbba70d41a6dfeee4d8cad5f295fc32"
)


class ReleaseBuildError(RuntimeError):
    """Erro seguro e acionável na montagem da release."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version", required=True, help="versão estável no formato MAJOR.MINOR.PATCH"
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "dist" / "release",
    )
    parser.add_argument("--image-repository", default="zeny-project-handler-server")
    arguments = parser.parse_args()
    try:
        manifest = build_release(
            arguments.version,
            output_root=arguments.output_root,
            image_repository=arguments.image_repository,
        )
    except (OSError, ReleaseBuildError, subprocess.CalledProcessError) as error:
        print(f"BUILD DE RELEASE: REPROVADO — {error}")
        return 1
    print("BUILD DE RELEASE: APROVADO")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def build_release(
    version: str,
    *,
    output_root: Path,
    image_repository: str,
) -> dict[str, object]:
    _validate_version(version)
    source_date_epoch = _source_date_epoch()
    os.environ["SOURCE_DATE_EPOCH"] = str(source_date_epoch)
    os.environ["PYTHONHASHSEED"] = "0"
    output_root = output_root.resolve()
    target = output_root / version
    work = ROOT / "build" / "release" / version
    staging = work / "staging"
    client_build_root = work / "client-artifacts"
    _reset_directory(work)
    staging.mkdir(parents=True)
    client_directory = staging / "client"
    server_directory = staging / "server"
    client_directory.mkdir()
    server_directory.mkdir()

    client_builder = work / "client-builder"
    _run(sys.executable, "-m", "venv", str(client_builder))
    client_python = client_builder / "Scripts" / "python.exe"
    _run(
        str(client_python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--requirement",
        str(ROOT / "requirements-client.lock"),
        "--requirement",
        str(ROOT / "requirements-client-build.lock"),
    )
    _run(
        str(client_python),
        str(ROOT / "scripts" / "build_client.py"),
        "--version",
        version,
        "--output-root",
        str(client_build_root),
    )
    built_client = client_build_root / version
    client_zip = built_client / f"ZenyProjectHandler-Client-{version}-win-x64.zip"
    client_wheel = next((built_client / "wheel").glob("zeny_project_handler_client-*.whl"))
    shutil.copy2(client_zip, client_directory / client_zip.name)
    shutil.copy2(ROOT / "client" / "LEIA-ME-CLIENTE.md", client_directory)
    shutil.copy2(built_client / "client-sbom.json", client_directory)

    image_reference = f"{image_repository}:{version}"
    image_archive = server_directory / f"ZenyProjectHandler-Server-{version}.oci.tar"
    subprocess.run(
        ["docker", "image", "rm", image_reference],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    _run(
        "docker",
        "build",
        "--no-cache",
        "--provenance=false",
        "--file",
        str(ROOT / "Dockerfile"),
        "--target",
        "runtime",
        "--build-arg",
        f"ZENY_RELEASE_VERSION={version}",
        "--build-arg",
        f"SOURCE_DATE_EPOCH={source_date_epoch}",
        "--output",
        (
            f"type=docker,name={image_reference},dest={image_archive.as_posix()},"
            "rewrite-timestamp=true"
        ),
        str(ROOT),
    )
    _run("docker", "load", "--input", str(image_archive))
    image_metadata = _image_metadata(image_reference, version)
    image_digest = str(image_metadata["Id"])
    shutil.copy2(ROOT / "server" / "compose.release.yaml", server_directory)
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", server_directory)
    _render_server_environment(image_reference, server_directory / ".env-example")
    _render_server_guide(
        version,
        image_reference,
        image_digest,
        image_archive.name,
        server_directory / "LEIA-ME-SERVIDOR.md",
    )
    _write_json(server_directory / "server-sbom.json", _server_sbom(version, image_reference))
    _write_release_notes(staging / "RELEASE_NOTES.md", version, image_reference, image_digest)

    payload_records = _file_records(staging)
    manifest: dict[str, object] = {
        "schema_version": 1,
        "release_version": version,
        "reproducibility": {
            "source_date_epoch": source_date_epoch,
            "python_hash_seed": 0,
            "base_image": BASE_IMAGE,
            "dockerfile_frontend": DOCKERFILE_FRONTEND,
            "locked_client_dependencies": "requirements-client.lock",
            "locked_server_dependencies": "requirements-server.lock",
        },
        "client": {
            "version": version,
            "platform": "windows-x86_64",
            "minimum_api_version": MIN_COMPATIBLE_API_VERSION,
            "maximum_api_version": MAX_COMPATIBLE_API_VERSION,
        },
        "server": {
            "version": version,
            "api_version": API_VERSION,
            "minimum_compatible_api_version": MIN_COMPATIBLE_API_VERSION,
            "maximum_compatible_api_version": MAX_COMPATIBLE_API_VERSION,
            "volume_format_version": VOLUME_FORMAT_VERSION,
            "alembic_revision": ALEMBIC_REVISION,
            "image": {
                "reference": image_reference,
                "id_digest": image_digest,
                "archive": f"server/{image_archive.name}",
                "archive_format": "docker-image-archive-compatible-with-docker-load",
            },
        },
        "distribution_sets": {
            "client_user": [
                f"client/{client_zip.name}",
                "client/LEIA-ME-CLIENTE.md",
                "client/client-sbom.json",
            ],
            "server_administrator": [
                f"server/{image_archive.name}",
                "server/compose.release.yaml",
                "server/.env-example",
                "server/LEIA-ME-SERVIDOR.md",
                "server/server-sbom.json",
                "server/THIRD_PARTY_NOTICES.md",
            ],
            "common_integrity": [
                "RELEASE_NOTES.md",
                "release-manifest.json",
                "SHA256SUMS.txt",
            ],
        },
        "files": payload_records,
        "integrity_index": {
            "algorithm": "SHA-256",
            "manifest_covers": "todos os payloads, exceto o próprio manifesto e SHA256SUMS.txt",
            "sha256s_covers": "todos os arquivos distribuídos, exceto o próprio SHA256SUMS.txt",
        },
    }
    _write_json(staging / "release-manifest.json", manifest)
    _write_sha256s(staging)

    _run(
        sys.executable,
        str(ROOT / "scripts" / "release_artifact_gate.py"),
        "--release-dir",
        str(staging),
        "--wheel",
        str(client_wheel),
        "--client-manifest",
        str(built_client / "client-manifest.json"),
        "--pyinstaller-python",
        str(client_python),
        "--image",
        image_reference,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(staging), str(target))
    return json.loads((target / "release-manifest.json").read_text(encoding="utf-8"))


def _validate_version(version: str) -> None:
    if SEMVER.fullmatch(version) is None:
        raise ReleaseBuildError("a versão deve usar SemVer estável MAJOR.MINOR.PATCH")
    declared = {
        path: str(_project_data(path)["version"])
        for path in (
            ROOT / "pyproject.toml",
            ROOT / "client" / "pyproject.toml",
            ROOT / "server" / "pyproject.toml",
        )
    }
    mismatches = [
        f"{path.relative_to(ROOT)}={value}" for path, value in declared.items() if value != version
    ]
    if mismatches:
        raise ReleaseBuildError(
            f"versão {version} diverge dos manifestos do produto: {', '.join(mismatches)}"
        )


def _project_data(path: Path) -> dict[str, object]:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    return dict(payload["project"])


def _source_date_epoch() -> int:
    configured = os.environ.get("SOURCE_DATE_EPOCH")
    if configured is not None:
        try:
            value = int(configured)
        except ValueError as error:
            raise ReleaseBuildError("SOURCE_DATE_EPOCH deve ser um inteiro Unix") from error
        if value < 315532800:
            raise ReleaseBuildError("SOURCE_DATE_EPOCH deve ser posterior a 1980-01-01")
        return value
    completed = subprocess.run(
        ["git", "log", "-1", "--format=%ct"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        value = int(completed.stdout.strip())
    except ValueError as error:
        raise ReleaseBuildError("não foi possível obter SOURCE_DATE_EPOCH do checkout") from error
    if completed.returncode != 0 or value < 315532800:
        raise ReleaseBuildError("timestamp do checkout é inválido para build reproduzível")
    return value


def _image_metadata(image: str, version: str) -> dict[str, object]:
    completed = _run("docker", "image", "inspect", image)
    metadata = json.loads(completed.stdout)[0]
    labels = metadata.get("Config", {}).get("Labels", {}) or {}
    if labels.get("org.opencontainers.image.version") != version:
        raise ReleaseBuildError("a imagem não contém o label OCI da versão solicitada")
    digest = str(metadata.get("Id", ""))
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise ReleaseBuildError("o Docker não informou um digest de imagem válido")
    return dict(metadata)


def _render_server_environment(image_reference: str, destination: Path) -> None:
    template = (ROOT / "server" / "env.release.example").read_text(encoding="utf-8")
    destination.write_text(
        template.replace("@ZENY_SERVER_IMAGE@", image_reference),
        encoding="utf-8",
        newline="\n",
    )


def _render_server_guide(
    version: str,
    image_reference: str,
    image_digest: str,
    image_archive: str,
    destination: Path,
) -> None:
    template = (ROOT / "server" / "LEIA-ME-SERVIDOR.md").read_text(encoding="utf-8")
    rendered = (
        template.replace("@RELEASE_VERSION@", version)
        .replace("@IMAGE_REFERENCE@", image_reference)
        .replace("@IMAGE_DIGEST@", image_digest)
        .replace("@IMAGE_ARCHIVE@", image_archive)
    )
    destination.write_text(rendered, encoding="utf-8", newline="\n")


def _server_sbom(version: str, image_reference: str) -> dict[str, object]:
    components: list[dict[str, str]] = [
        {"type": "application", "name": "zeny-project-handler-server", "version": version},
        {"type": "container", "name": BASE_IMAGE, "version": "3.13.7-slim-bookworm"},
    ]
    components.extend(_locked_components(ROOT / "requirements-server.lock"))
    query = _run(
        "docker",
        "run",
        "--rm",
        "--entrypoint",
        "dpkg-query",
        image_reference,
        "-W",
        "-f=${Package}\t${Version}\n",
        "tesseract-ocr",
        "tesseract-ocr-por",
        "libtesseract5",
        "msodbcsql18",
        "unixodbc",
    )
    for line in query.stdout.splitlines():
        name, separator, package_version = line.partition("\t")
        if separator:
            components.append({"type": "library", "name": name, "version": package_version})
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": components[0],
            "properties": [{"name": "image", "value": image_reference}],
        },
        "components": components,
    }


def _locked_components(path: Path) -> list[dict[str, str]]:
    components: list[dict[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, locked_version = line.split("==", maxsplit=1)
        components.append({"type": "library", "name": name, "version": locked_version})
    return components


def _write_release_notes(path: Path, version: str, image: str, digest: str) -> None:
    path.write_text(
        f"""# Notas da release {version}

- Cliente Windows: `{version}`; ZIP portátil x64 autocontido, sem Python instalado.
- Servidor: `{version}`; imagem `{image}` (`{digest}`).
- API: `{API_VERSION}`; faixa compatível `{MIN_COMPATIBLE_API_VERSION}`-
  `{MAX_COMPATIBLE_API_VERSION}`.
- Volume: formato `{VOLUME_FORMAT_VERSION}`; revisão Alembic `{ALEMBIC_REVISION}`.

Esta release substitui o painel de importação/backup por **Exportar**. O servidor compila o PDF
anotado e as planilhas Excel de Resultados, Documentação e Conformidade; o cliente baixa os arquivos
com validação de tamanho e SHA-256. Backup e restauração do volume permanecem responsabilidades do
administrador do servidor.

A classificação rural/urbana da conformidade consulta o SQL Server externo uma vez por execução.
O administrador deve configurar a conexão ODBC com TLS e login de `SELECT` mínimo no `.env`; falha,
ausência ou resposta inválida interrompe a análise sem fallback. Depois de uma alteração no
cadastro externo, execute novamente **Analisar conformidade** para criar o snapshot atualizado.

O cliente deve ser distribuído somente aos usuários finais; o kit servidor, somente aos
administradores. Ambos podem receber também os três arquivos comuns de notas e integridade. Não
existe senha predefinida: o administrador deve criar `.env` a partir do exemplo antes do primeiro
start.

Upgrade executa validação e migração fail-closed antes da prontidão. Faça um snapshot administrativo
consistente do volume com o serviço parado antes de trocar a imagem. Rollback no mesmo volume só é
permitido quando a imagem anterior suporta o formato e a revisão atuais; caso contrário, restaure o
snapshot pré-upgrade em volume novo.
""",
        encoding="utf-8",
        newline="\n",
    )


def _file_records(directory: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(directory).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name not in {"release-manifest.json", "SHA256SUMS.txt"}
    ]


def _write_sha256s(directory: Path) -> None:
    lines = [
        f"{_sha256(path)}  {path.relative_to(directory).as_posix()}"
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.txt"
    ]
    (directory / "SHA256SUMS.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _run(*command: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=command[:2] != ("docker", "build"),
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ReleaseBuildError(
            f"{' '.join(command[:3])} falhou: {detail[-1500:] or 'sem diagnóstico'}"
        )
    return completed


if __name__ == "__main__":
    raise SystemExit(main())
