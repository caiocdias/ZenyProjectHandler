"""Ensaie os kits exatos em hosts temporários sem checkout compartilhado."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile

from pywinauto import Application

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.stage11_parity_gate import _run_packaged_ui_smoke  # noqa: E402

PLACEHOLDER = "troque-por-uma-senha-longa-e-aleatoria"


class GateError(RuntimeError):
    """Falha do ensaio de distribuição da release."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--client-manifest", type=Path, required=True)
    arguments = parser.parse_args()
    suffix = uuid4().hex[:10]
    project = f"zph-stage12-{suffix}"
    compose_prefix: list[str] = []
    report: dict[str, object] = {}
    try:
        _run(["docker", "info"], timeout=60)
        release_dir = arguments.release_dir.resolve()
        manifest = json.loads((release_dir / "release-manifest.json").read_text(encoding="utf-8"))
        version = str(manifest["release_version"])
        image = str(manifest["server"]["image"]["reference"])
        digest = str(manifest["server"]["image"]["id_digest"])
        archive_name = Path(str(manifest["server"]["image"]["archive"])).name
        temporary_root = Path("C:/tmp")
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="zph-stage12-", dir=temporary_root) as name:
            temporary = Path(name)
            client_host = temporary / "client-host"
            server_host = temporary / "server-host"
            shutil.copytree(release_dir / "client", client_host)
            shutil.copytree(release_dir / "server", server_host)
            _assert_distribution_boundary(client_host, server_host, version)

            _run(["docker", "image", "rm", image], check=False, timeout=120)
            if _run(["docker", "image", "inspect", image], check=False).returncode == 0:
                raise GateError(
                    "a tag da release permaneceu local; não foi possível provar docker load"
                )
            _run(["docker", "load", "--input", str(server_host / archive_name)], timeout=300)
            loaded = json.loads(_run(["docker", "image", "inspect", image]).stdout)[0]
            if loaded.get("Id") != digest:
                raise GateError("docker load não restaurou o digest registrado no manifesto")

            password = secrets.token_urlsafe(36)
            port = _available_port()
            environment_file = server_host / ".env"
            environment = (server_host / ".env-example").read_text(encoding="utf-8")
            environment = environment.replace(PLACEHOLDER, password).replace(
                "ZENY_SERVER_PORT=8000",
                f"ZENY_SERVER_PORT={port}",
            )
            environment_file.write_text(environment, encoding="utf-8", newline="\n")
            compose_prefix = [
                "docker",
                "compose",
                "--project-name",
                project,
                "--project-directory",
                str(server_host),
                "--env-file",
                str(environment_file),
                "-f",
                str(server_host / "compose.release.yaml"),
            ]
            config = json.loads(_run([*compose_prefix, "config", "--format", "json"]).stdout)
            service = config["services"]["server"]
            if "build" in service or service.get("image") != image:
                raise GateError("o host limpo tentou construir ou usar outra imagem")
            _run([*compose_prefix, "up", "-d", "--no-build"], timeout=180)
            base_url = f"http://127.0.0.1:{port}"
            session = _wait_ready(base_url, password)
            container = _run([*compose_prefix, "ps", "-q", "server"]).stdout.strip()
            _assert_runtime_boundary(container, digest)

            client_zip = client_host / f"ZenyProjectHandler-Client-{version}-win-x64.zip"
            _run_packaged_ui_smoke(
                client_zip,
                base_url,
                password,
                client_host / "ui-data",
                temporary,
            )
            _run_packaged_incompatible_smoke(
                client_zip,
                client_host / "incompatible-ui-data",
                temporary,
            )
            project_id = _create_project(base_url, password)
            _run([*compose_prefix, "up", "-d", "--no-build", "--force-recreate"], timeout=180)
            session_after = _wait_ready(base_url, password)
            _assert_project_visible(base_url, password, project_id)
            recreated = _run([*compose_prefix, "ps", "-q", "server"]).stdout.strip()
            _assert_runtime_boundary(recreated, digest)
            _assert_secret_absent(recreated, password, client_host)
            _run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "release_artifact_gate.py"),
                    "--release-dir",
                    str(release_dir),
                    "--wheel",
                    str(arguments.wheel.resolve()),
                    "--client-manifest",
                    str(arguments.client_manifest.resolve()),
                    "--image",
                    image,
                ],
                timeout=300,
            )
            server_gate_environment = temporary / "server-secret.env"
            server_gate_environment.write_text(
                f"ZENY_SERVER_PASSWORD={password}\n",
                encoding="utf-8",
            )
            _run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "server_artifact_gate.py"),
                    "--image",
                    image,
                    "--secret-env-file",
                    str(server_gate_environment),
                ],
                timeout=300,
            )
            report = {
                "release_version": version,
                "client_host": {
                    "received_only_client_set": True,
                    "checkout_absent": True,
                    "python_absent_from_process_path": True,
                    "packaged_executable_authenticated": True,
                    "incompatible_api_refused_before_window": True,
                    "business_data_created_locally": False,
                },
                "server_host": {
                    "received_only_server_set": True,
                    "checkout_absent": True,
                    "docker_load_used": True,
                    "compose_build_absent": True,
                    "source_bind_mounts": False,
                    "persistent_after_recreate": True,
                },
                "image": {"reference": image, "digest": digest},
                "api": {
                    "before_recreate": session["api_version"],
                    "after_recreate": session_after["api_version"],
                    "supported_combination_accepted": True,
                    "incompatible_combination_refused": True,
                },
                "project_id_after_recreate": project_id,
                "runtime_secret_absent": True,
            }
    except Exception as error:
        print(f"GATE DE DISTRIBUIÇÃO DA ETAPA 12: REPROVADO — {error}")
        return 1
    finally:
        if compose_prefix:
            _run([*compose_prefix, "down"], check=False, timeout=120)
        _remove_project_resources(project)
    print("GATE DE DISTRIBUIÇÃO DA ETAPA 12: APROVADO")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _assert_distribution_boundary(client_host: Path, server_host: Path, version: str) -> None:
    client_names = {path.name for path in client_host.iterdir() if path.is_file()}
    server_names = {path.name for path in server_host.iterdir() if path.is_file()}
    if client_names != {
        f"ZenyProjectHandler-Client-{version}-win-x64.zip",
        "LEIA-ME-CLIENTE.md",
        "client-sbom.json",
    }:
        raise GateError("o host cliente recebeu arquivos além do conjunto de distribuição")
    if server_names != {
        f"ZenyProjectHandler-Server-{version}.oci.tar",
        "compose.release.yaml",
        ".env-example",
        "LEIA-ME-SERVIDOR.md",
        "server-sbom.json",
    }:
        raise GateError("o host Docker recebeu arquivos além do kit servidor")
    forbidden = {"src", "tests", "client", "server", "dockerfile", "pyproject.toml", ".git"}
    for host in (client_host, server_host):
        if any(path.name.casefold() in forbidden for path in host.rglob("*")):
            raise GateError(f"checkout/código-fonte encontrado no host temporário {host.name}")


def _assert_runtime_boundary(container: str, digest: str) -> None:
    if not container:
        raise GateError("Compose não informou o container servidor")
    metadata = json.loads(_run(["docker", "inspect", container]).stdout)[0]
    if metadata.get("Image") != digest:
        raise GateError("container não usa o digest testado")
    if metadata.get("HostConfig", {}).get("ReadonlyRootfs") is not True:
        raise GateError("root filesystem do servidor não está read-only")
    if any(item.get("Type") == "bind" for item in metadata.get("Mounts", ())):
        raise GateError("host Docker montou checkout/bind no container")
    destinations = {item.get("Destination") for item in metadata.get("Mounts", ())}
    if "/data" not in destinations:
        raise GateError("volume persistente /data não foi montado")


def _create_project(base_url: str, password: str) -> str:
    status, payload = _json_request(
        f"{base_url}/api/v1/projects",
        password,
        method="POST",
        body={"service_note": "1201201201"},
        headers={"Idempotency-Key": "stage12-release-project"},
    )
    if status != 201:
        raise GateError(f"criação no servidor do kit retornou HTTP {status}")
    return str(payload["project"]["project_id"])


def _assert_project_visible(base_url: str, password: str, project_id: str) -> None:
    status, payload = _json_request(f"{base_url}/api/v1/projects", password)
    identifiers = {str(item["project_id"]) for item in payload.get("items", ())}
    if status != 200 or project_id not in identifiers:
        raise GateError("dados não sobreviveram ao recreate do kit servidor")


def _wait_ready(base_url: str, password: str) -> dict[str, object]:
    deadline = monotonic() + 90
    while monotonic() < deadline:
        status, payload = _json_request(f"{base_url}/api/v1/session", password)
        if status == 200 and payload.get("ready") is True:
            return payload
        sleep(0.25)
    raise GateError("servidor carregado do archive não ficou pronto")


def _json_request(
    url: str,
    password: str,
    *,
    method: str = "GET",
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"Authorization": f"Bearer {password}", **(headers or {})}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, method=method, headers=request_headers)
    try:
        with urlopen(request, timeout=5) as response:
            return int(response.status), dict(json.loads(response.read()))
    except HTTPError as error:
        try:
            return int(error.code), dict(json.loads(error.read()))
        except (OSError, ValueError):
            return int(error.code), {}
    except (URLError, TimeoutError, OSError):
        return 0, {}


def _assert_secret_absent(container: str, password: str, client_host: Path) -> None:
    logs = _run(["docker", "logs", container]).stdout.encode()
    secret = password.encode()
    if secret in logs or b"authorization" in logs.lower():
        raise GateError("segredo/header encontrado nos logs do kit servidor")
    probe = (
        "import sys; from pathlib import Path; secret=sys.stdin.buffer.read(); found=False; "
        "files=(p for p in Path('/data').rglob('*') if p.is_file()); "
        "\nfor p in files:\n"
        " try:\n  found = found or secret in p.read_bytes()\n"
        " except OSError:\n  pass\n"
        "raise SystemExit(1 if found else 0)"
    )
    completed = subprocess.run(
        ["docker", "exec", "-i", container, "python", "-c", probe],
        input=secret,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise GateError("segredo runtime encontrado no volume")
    for path in client_host.rglob("*"):
        if path.is_file() and secret in path.read_bytes():
            raise GateError("segredo runtime encontrado no pacote/host cliente")


class _IncompatibleHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/api/v1/session":
            self.send_error(404)
            return
        payload = json.dumps(
            {
                "server_version": "2.0.0",
                "api_version": "2.0.0",
                "min_compatible_api_version": "2.0.0",
                "max_compatible_api_version": "2.999.999",
                "ready": True,
                "capabilities": ["incompatible-fixture"],
                "ocr": {
                    "status": "AVAILABLE",
                    "engine": "fixture",
                    "language": "por",
                    "message": "Disponível",
                },
                "global_operation": None,
                "server_time": "2026-08-21T00:00:00-03:00",
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


def _run_packaged_incompatible_smoke(client_zip: Path, data_dir: Path, temporary: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _IncompatibleHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    extract_root = temporary / "incompatible-client"
    with ZipFile(client_zip) as archive:
        archive.extractall(extract_root)
    executable = next(extract_root.rglob("ZenyProjectHandler.exe"))
    system_root = os.environ.get("SYSTEMROOT", "C:/Windows")
    environment = {
        "PATH": str(Path(system_root) / "System32"),
        "SystemRoot": system_root,
        "WINDIR": os.environ.get("WINDIR", "C:/Windows"),
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "LOCALAPPDATA": str(temporary / "incompatible-local-app-data"),
        "ZENY_CLIENT_SERVER_URL": f"http://127.0.0.1:{server.server_port}",
        "ZENY_DATA_DIR": str(data_dir),
    }
    process = subprocess.Popen(
        [str(executable), "--smoke-test"], cwd=executable.parent, env=environment
    )
    try:
        application = Application(backend="uia").connect(process=process.pid, timeout=45)
        deadline = monotonic() + 45
        dialog = None
        while monotonic() < deadline and dialog is None:
            candidates = application.windows(
                title="Conectar ao servidor Zeny",
                control_type="Window",
                visible_only=True,
                enabled_only=True,
            )
            candidates = [
                item for item in candidates if len(item.descendants(control_type="Edit")) == 2
            ]
            if len(candidates) == 1:
                dialog = candidates[0]
            else:
                sleep(0.1)
        if dialog is None:
            raise GateError("UI Automation não encontrou o diálogo da sessão incompatível")
        edits = dialog.descendants(control_type="Edit")
        password = next(
            (item for item in edits if item.element_info.automation_id == "serverPasswordInput"),
            edits[1],
        )
        password.set_edit_text("senha-apenas-para-fixture")
        connect_buttons = [
            item
            for item in dialog.descendants(control_type="Button")
            if item.window_text() == "Conectar"
        ]
        if len(connect_buttons) != 1:
            raise GateError("UI Automation não encontrou o botão Conectar incompatível")
        connect_buttons[0].invoke()
        deadline = monotonic() + 30
        feedback_text = ""
        observed_texts: list[str] = []
        while monotonic() < deadline and "incompatíveis" not in feedback_text:
            observed_texts = [
                item.window_text() for item in dialog.descendants(control_type="Text")
            ]
            feedback_text = next(
                (item for item in observed_texts if "incompatíveis" in item),
                "",
            )
            sleep(0.1)
        if "incompatíveis" not in feedback_text:
            raise GateError(
                "cliente empacotado não exibiu a recusa de API incompatível; "
                f"textos observados: {observed_texts!r}"
            )
        if application.windows(title_re="Zeny Project Handler", control_type="Window"):
            raise GateError("cliente carregou a janela de dados após sessão incompatível")
        dialog.close()
        if process.wait(timeout=30) != 0:
            raise GateError("cliente incompatível não encerrou de forma segura")
    except BaseException:
        process.kill()
        process.wait(timeout=15)
        raise
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
    if (data_dir / "cache").exists() or (data_dir / "project-files").exists():
        raise GateError("sessão incompatível criou dados de negócio no cliente")


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _remove_project_resources(project: str) -> None:
    resource_commands = (
        (
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
            ["docker", "rm", "--force"],
        ),
        (
            [
                "docker",
                "network",
                "ls",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={project}",
            ],
            ["docker", "network", "rm"],
        ),
        (
            [
                "docker",
                "volume",
                "ls",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={project}",
            ],
            ["docker", "volume", "rm"],
        ),
    )
    for list_command, remove_prefix in resource_commands:
        completed = _run(list_command, check=False, timeout=60)
        for identifier in completed.stdout.splitlines():
            if identifier.strip():
                _run([*remove_prefix, identifier.strip()], check=False, timeout=60)


def _run(
    command: list[str],
    *,
    check: bool = True,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        raise GateError(
            f"{' '.join(command[:3])} falhou: {detail[-1] if detail else 'sem diagnóstico'}"
        )
    return completed


if __name__ == "__main__":
    raise SystemExit(main())
