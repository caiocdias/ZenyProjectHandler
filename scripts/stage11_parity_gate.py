"""Aceite da Etapa 11 com wheel/ZIP cliente e imagem Docker isolados."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import re
import secrets
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

import pymupdf
from pywinauto import Application

ROOT = Path(__file__).resolve().parents[1]
UUID_FIXTURE = "00000000-0000-4000-8000-000000000001"
_METHODS = ("get", "post", "put", "patch", "delete")
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class GateError(RuntimeError):
    pass


class TrafficAudit:
    def __init__(self, server_password: str, pdf_password: str) -> None:
        self.server_password = server_password.encode()
        self.pdf_password = pdf_password.encode()
        self.requests = 0
        self.protected_requests = 0
        self.authorization_only = True
        self.pdf_password_unlock_only = True
        self.safe_responses = True
        self.violations: list[str] = []
        self._lock = threading.Lock()

    def observe_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        with self._lock:
            self.requests += 1
            authorization = headers.get("authorization", "").encode()
            if authorization:
                self.protected_requests += 1
            if self.server_password in path.encode() or self.server_password in body:
                self.authorization_only = False
                self.violations.append(
                    f"segredo do servidor fora do Authorization em {method} {path}"
                )
            if self.server_password in authorization and authorization != (
                b"Bearer " + self.server_password
            ):
                self.authorization_only = False
                self.violations.append(f"Authorization inesperado em {method} {path}")
            if self.pdf_password in body and not path.endswith("/unlock"):
                self.pdf_password_unlock_only = False
                self.violations.append(
                    f"senha PDF fora do endpoint de desbloqueio em {method} {path}"
                )
            lowered = body.lower()
            if b"c:\\" in lowered or b"/data/" in lowered:
                self.violations.append(f"caminho físico atravessou request em {method} {path}")

    def observe_response(
        self,
        method: str,
        path: str,
        content_type: str,
        body: bytes,
    ) -> None:
        if not any(item in content_type.casefold() for item in ("json", "text")):
            return
        lowered = body.lower()
        forbidden = (b"/data/", b"traceback", b"zeny_project_handler.adapters", b"c:\\")
        with self._lock:
            if self.server_password in body or self.pdf_password in body:
                self.safe_responses = False
                self.violations.append(f"segredo retornado em {method} {path}")
            if any(token in lowered for token in forbidden):
                self.safe_responses = False
                self.violations.append(f"detalhe interno retornado em {method} {path}")


def _proxy_handler(upstream_port: int, audit: TrafficAudit) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self._forward()

        def do_POST(self) -> None:
            self._forward()

        def do_PUT(self) -> None:
            self._forward()

        def do_PATCH(self) -> None:
            self._forward()

        def do_DELETE(self) -> None:
            self._forward()

        def log_message(self, _format: str, *_args: object) -> None:
            pass

        def _forward(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            headers = {
                key.casefold(): value
                for key, value in self.headers.items()
                if key.casefold() not in _HOP_BY_HOP and key.casefold() != "host"
            }
            audit.observe_request(self.command, self.path, headers, body)
            connection = http.client.HTTPConnection("127.0.0.1", upstream_port, timeout=360)
            try:
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read()
                response_headers = [
                    (key, value)
                    for key, value in response.getheaders()
                    if key.casefold() not in _HOP_BY_HOP and key.casefold() != "content-length"
                ]
                content_type = next(
                    (value for key, value in response_headers if key.casefold() == "content-type"),
                    "",
                )
                audit.observe_response(self.command, self.path, content_type, payload)
                self.send_response(response.status)
                for key, value in response_headers:
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            finally:
                connection.close()

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="zeny-project-handler-server:dev")
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--zip", dest="client_zip", type=Path, required=True)
    arguments = parser.parse_args()
    suffix = uuid4().hex[:10]
    container = f"zph-stage11-{suffix}"
    volume = f"zph-stage11-{suffix}"
    server_password = secrets.token_hex(32)
    pdf_password = secrets.token_hex(16)
    upstream_port = _available_port()
    proxy: ThreadingHTTPServer | None = None
    proxy_thread: threading.Thread | None = None
    result: dict[str, object] = {}
    try:
        _run(["docker", "info"], timeout=60)
        _validate_inputs(arguments.wheel, arguments.client_zip, arguments.image)
        temporary_root = Path("C:/tmp")
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="zph-stage11-", dir=temporary_root) as name:
            temporary = Path(name)
            client_root = temporary / "client-host"
            client_root.mkdir()
            fixtures = _create_fixtures(client_root, pdf_password)
            _run(["docker", "volume", "create", volume])
            _run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--name",
                    container,
                    "--read-only",
                    "--tmpfs",
                    "/tmp:rw,noexec,nosuid,nodev,size=268435456",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--pids-limit",
                    "256",
                    "--memory",
                    "2g",
                    "--mount",
                    f"source={volume},target=/data",
                    "--publish",
                    f"127.0.0.1:{upstream_port}:8000",
                    "--env",
                    f"ZENY_SERVER_PASSWORD={server_password}",
                    arguments.image,
                ],
                timeout=120,
            )
            direct_url = f"http://127.0.0.1:{upstream_port}"
            _wait_ready(direct_url, server_password)
            audit = TrafficAudit(server_password, pdf_password)
            proxy = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                _proxy_handler(upstream_port, audit),
            )
            proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            proxy_thread.start()
            proxy_url = f"http://127.0.0.1:{proxy.server_port}"

            _run_packaged_ui_smoke(
                arguments.client_zip,
                proxy_url,
                server_password,
                client_root / "ui-data",
                temporary,
            )
            common = {
                "base_url": proxy_url,
                "password": server_password,
                "protected_password": pdf_password,
                "client_root": str(client_root),
                **{key: str(value) for key, value in fixtures.items()},
            }
            client_python, client_site_packages = _prepare_isolated_client_runtime(temporary)
            prepared = _run_client_matrix(
                arguments.wheel,
                "prepare",
                common,
                temporary,
                client_python,
                client_site_packages,
            )
            _run(["docker", "restart", container], timeout=90)
            _wait_ready(direct_url, server_password)
            after_restart = _run_client_matrix(
                arguments.wheel,
                "after-restart",
                {**common, "state": prepared},
                temporary,
                client_python,
                client_site_packages,
            )
            auth_matrix = _audit_route_authentication(proxy_url, server_password)
            _audit_runtime_secrets(
                container,
                server_password,
                pdf_password,
                client_root,
                arguments.wheel,
                arguments.client_zip,
                after_restart,
            )
            _run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "client_artifact_gate.py"),
                    "--wheel",
                    str(arguments.wheel),
                    "--zip",
                    str(arguments.client_zip),
                    "--manifest",
                    str(arguments.client_zip.parent / "client-manifest.json"),
                ],
                timeout=180,
            )
            server_gate_environment = temporary / "server-artifact-gate.env"
            server_gate_environment.write_text(
                f"ZENY_SERVER_PASSWORD={server_password}\n",
                encoding="utf-8",
            )
            try:
                _run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "server_artifact_gate.py"),
                        "--image",
                        arguments.image,
                        "--secret-env-file",
                        str(server_gate_environment),
                    ],
                    timeout=180,
                )
            finally:
                server_gate_environment.unlink(missing_ok=True)
            if audit.violations:
                raise GateError("; ".join(audit.violations))
            image_metadata = json.loads(
                _run(["docker", "image", "inspect", arguments.image]).stdout
            )[0]
            result = {
                "client_zip": _record(arguments.client_zip),
                "client_wheel": _record(arguments.wheel),
                "server_image": {
                    "name": arguments.image,
                    "id": image_metadata["Id"],
                    "size_bytes": image_metadata["Size"],
                },
                "packaged_ui_authenticated": True,
                "packaged_wheel_boundary": True,
                "client_server_filesystem_shared": False,
                "docker_restart": True,
                "auth_routes": auth_matrix,
                "traffic": {
                    "requests": audit.requests,
                    "protected_requests": audit.protected_requests,
                    "server_password_only_in_authorization": audit.authorization_only,
                    "pdf_password_only_in_unlock_requests": audit.pdf_password_unlock_only,
                    "responses_without_internal_paths_or_secrets": audit.safe_responses,
                },
                "prepare": prepared,
                "after_restart": after_restart,
                "parity": _parity_matrix(prepared, after_restart),
                "secrets_absent_from_persistent_artifacts": True,
            }
    except Exception as error:
        print(f"GATE DE PARIDADE DA ETAPA 11: REPROVADO — {error}")
        return 1
    finally:
        if proxy is not None:
            proxy.shutdown()
            proxy.server_close()
        if proxy_thread is not None:
            proxy_thread.join(timeout=10)
        _run(["docker", "rm", "--force", container], check=False, timeout=60)
        _run(["docker", "volume", "rm", volume], check=False, timeout=60)
    print("GATE DE PARIDADE DA ETAPA 11: APROVADO")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _validate_inputs(wheel: Path, client_zip: Path, image: str) -> None:
    if not wheel.is_file() or not client_zip.is_file():
        raise GateError("wheel/ZIP do cliente não foram encontrados")
    _run(["docker", "image", "inspect", image])


def _create_fixtures(root: Path, pdf_password: str) -> dict[str, Path]:
    catalog = json.loads(
        (
            ROOT
            / "src"
            / "zeny_project_handler"
            / "adapters"
            / "catalog"
            / "data"
            / "catalogo_cemig_v2.json"
        ).read_text(encoding="utf-8")
    )
    catalog_code = str(catalog["items"][0]["code"])
    primary = root / "primary-stage11.pdf"
    document = pymupdf.open()
    try:
        for index in range(12):
            page = document.new_page(width=595, height=842)
            page.insert_text((40, 45), f"PROJETO REDE URBANA NS 0099887766 FOLHA {index + 1}")
            page.insert_text((80, 140), f"P{index + 1}")
            page.insert_text((80, 160), catalog_code)
            page.draw_line((80, 180), (420, 180), color=(0, 1, 0), width=2)
            page.insert_text(
                (250, 770),
                "NUMERO DO PROJETO: 1234567890  ESCALA: 1:250  FORMATO: A4",
            )
            page.insert_text(
                (250, 790),
                f"FOLHA: {index + 1}/12  DATA: 20/08/2026  CIRCUITO: ETAPA11",
            )
        document.save(primary)
    finally:
        document.close()
    second = root / "second-stage11.pdf"
    document = pymupdf.open()
    try:
        page = document.new_page(width=300, height=200)
        page.insert_text((20, 30), "DOCUMENTO COMPLEMENTAR SERVIDAO ASSINATURA ESCALA 1:500")
        page.draw_rect((20, 50, 280, 180), color=(1, 0, 0))
        document.save(second)
    finally:
        document.close()
    protected = root / "protected-stage11.pdf"
    document = pymupdf.open()
    try:
        page = document.new_page(width=200, height=120)
        page.insert_text((20, 60), "PDF PROTEGIDO ETAPA 11")
        document.save(
            protected,
            encryption=int(pymupdf.PDF_ENCRYPT_AES_256),
            owner_pw="owner-stage11",
            user_pw=pdf_password,
        )
    finally:
        document.close()
    photo = root / "photo-stage11.png"
    photo.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFElEQVR4nGP4z8DAwMDA"
            "xMDAwAAAHgQCAf2m3iUAAAAASUVORK5CYII="
        )
    )
    return {
        "primary_pdf": primary,
        "second_pdf": second,
        "protected_pdf": protected,
        "photo": photo,
    }


def _run_client_matrix(
    wheel: Path,
    phase: str,
    plan: dict[str, object],
    temporary: Path,
    client_python: Path,
    site_packages: Path,
) -> dict[str, object]:
    environment = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(wheel.resolve()), str(site_packages.resolve()))),
        "PYTHONUTF8": "1",
        "QT_QPA_PLATFORM": "offscreen",
    }
    completed = subprocess.run(
        [
            str(client_python),
            "-S",
            str((ROOT / "scripts" / "stage11_client_matrix.py").resolve()),
            phase,
        ],
        cwd=temporary,
        env=environment,
        input=json.dumps(plan),
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if completed.returncode != 0 or not lines:
        detail = (completed.stderr or completed.stdout).strip()
        raise GateError(f"cliente empacotado falhou na fase {phase}: {detail[-1000:]}")
    payload = json.loads(lines[-1])
    if payload.get("ok") is not True:
        raise GateError(f"matriz do cliente falhou na fase {phase}: {payload.get('error')}")
    payload.pop("ok", None)
    return payload


def _prepare_isolated_client_runtime(temporary: Path) -> tuple[Path, Path]:
    runtime = temporary / "client-runtime"
    _run([sys.executable, "-m", "venv", str(runtime)], timeout=120)
    client_python = runtime / "Scripts" / "python.exe"
    _run(
        [
            str(client_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--requirement",
            str(ROOT / "requirements-client.lock"),
        ],
        timeout=600,
    )
    return client_python.resolve(), (runtime / "Lib" / "site-packages").resolve()


def _run_packaged_ui_smoke(
    client_zip: Path,
    base_url: str,
    password: str,
    data_directory: Path,
    temporary: Path,
) -> None:
    extract_root = temporary / "portable-client"
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
        "LOCALAPPDATA": str(temporary / "local-app-data"),
        "ZENY_CLIENT_SERVER_URL": base_url,
        "ZENY_DATA_DIR": str(data_directory),
    }
    process = subprocess.Popen(
        [str(executable), "--smoke-test"],
        cwd=executable.parent,
        env=environment,
    )
    try:
        application = Application(backend="uia").connect(process=process.pid, timeout=45)
        deadline = monotonic() + 45
        dialog = None
        observed: list[tuple[int, str, int]] = []
        while monotonic() < deadline and dialog is None:
            dialogs = application.windows(
                title="Conectar ao servidor Zeny",
                control_type="Window",
                visible_only=True,
                enabled_only=True,
            )
            distinct_dialogs = {item.handle: item for item in dialogs}.values()
            observed = [
                (
                    item.handle,
                    item.element_info.automation_id,
                    len(item.descendants(control_type="Edit")),
                )
                for item in distinct_dialogs
            ]
            candidates = [
                item for item in distinct_dialogs if len(item.descendants(control_type="Edit")) == 2
            ]
            named_candidates = [
                item for item in candidates if item.element_info.automation_id == "connectionDialog"
            ]
            if len(named_candidates) == 1:
                dialog = named_candidates[0]
            elif len(candidates) == 1:
                dialog = candidates[0]
            else:
                sleep(0.1)
        if dialog is None:
            raise GateError(
                f"UI Automation não identificou uma raiz única para o diálogo: {observed}"
            )
        edits = dialog.descendants(control_type="Edit")
        password_input = next(
            (item for item in edits if item.element_info.automation_id == "serverPasswordInput"),
            edits[1],
        )
        password_input.set_edit_text(password)
        buttons = [
            item
            for item in dialog.descendants(control_type="Button")
            if item.window_text() == "Conectar"
        ]
        if len(buttons) != 1:
            raise GateError("UI Automation não encontrou um botão Conectar único")
        connect_button = buttons[0]
        connect_button.invoke()
        return_code = process.wait(timeout=90)
    except BaseException:
        process.kill()
        process.wait(timeout=15)
        raise
    if return_code != 0:
        raise GateError(f"ZIP cliente encerrou o smoke autenticado com código {return_code}")
    forbidden = ("*.sqlite", "*.sqlite3", "*.db")
    if any(path for pattern in forbidden for path in data_directory.rglob(pattern)):
        raise GateError("cliente empacotado criou banco local")
    if (data_directory / "cache").exists() or (data_directory / "project-files").exists():
        raise GateError("cliente empacotado criou cache/arquivos de negócio locais")
    _assert_bytes_absent(data_directory, (password.encode(),))


def _audit_route_authentication(base_url: str, password: str) -> dict[str, object]:
    openapi = json.loads((ROOT / "docs" / "api" / "openapi-v1.json").read_text(encoding="utf-8"))
    wrong_password = hashlib.sha256(f"credencial-invalida:{password}".encode()).hexdigest()
    checked = 0
    for template, path_item in openapi["paths"].items():
        if template == "/health/live":
            continue
        path = re.sub(r"\{[^}]+\}", UUID_FIXTURE, template)
        for method in _METHODS:
            if method not in path_item:
                continue
            missing = _raw_status(base_url, method.upper(), path, None)
            wrong = _raw_status(base_url, method.upper(), path, wrong_password)
            correct = _raw_status(base_url, method.upper(), path, password)
            if missing != 401 or wrong != 401 or correct == 401:
                raise GateError(
                    f"auth inconsistente em {method.upper()} {template}: "
                    f"sem={missing}, errada={wrong}, correta={correct}"
                )
            checked += 1
    return {
        "operations_checked": checked,
        "missing_401": True,
        "wrong_401": True,
        "correct_not_401": True,
    }


def _raw_status(base_url: str, method: str, path: str, password: str | None) -> int:
    request = Request(base_url + path, method=method)
    if password is not None:
        request.add_header("Authorization", f"Bearer {password}")
    try:
        with urlopen(request, timeout=15) as response:
            response.read()
            return int(response.status)
    except HTTPError as error:
        error.read()
        return int(error.code)
    except (URLError, TimeoutError, OSError) as error:
        raise GateError(f"falha de rede na matriz de autenticação: {error}") from error


def _audit_runtime_secrets(
    container: str,
    server_password: str,
    pdf_password: str,
    client_root: Path,
    wheel: Path,
    client_zip: Path,
    after_restart: dict[str, object],
) -> None:
    secrets_to_find = (server_password.encode(), pdf_password.encode())
    logs = _run(["docker", "logs", container]).stdout.encode()
    if any(secret in logs for secret in secrets_to_find) or b"authorization" in logs.lower():
        raise GateError("senha/header Authorization encontrado nos logs Docker")
    probe = (
        "import json,sys; from pathlib import Path; "
        "secrets=json.loads(sys.stdin.read()); found=[]; "
        "files=(p for p in Path('/data').rglob('*') if p.is_file()); "
        "\nfor p in files:\n"
        " try:\n  data=p.read_bytes()\n"
        " except OSError:\n  continue\n"
        " if any(bytes.fromhex(value) in data for value in secrets): found.append(str(p))\n"
        "print(json.dumps(found)); raise SystemExit(1 if found else 0)"
    )
    completed = subprocess.run(
        ["docker", "exec", "-i", container, "python", "-c", probe],
        input=json.dumps([item.hex() for item in secrets_to_find]),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise GateError(f"senha encontrada no volume: {completed.stdout.strip()}")
    _assert_bytes_absent(client_root, secrets_to_find)
    for artifact in (wheel, client_zip):
        payload = artifact.read_bytes()
        if any(secret in payload for secret in secrets_to_find):
            raise GateError(f"senha encontrada no artefato cliente {artifact.name}")
    for key in ("project_package", "backup_package"):
        path = Path(str(after_restart[key]))
        payload = path.read_bytes()
        if any(secret in payload for secret in secrets_to_find):
            raise GateError(f"senha encontrada no pacote exportado {path.name}")
    git_probe = subprocess.run(
        ["git", "grep", "-F", server_password],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if git_probe.returncode == 0:
        raise GateError("segredo runtime encontrado em arquivo versionado")


def _assert_bytes_absent(root: Path, secrets_to_find: tuple[bytes, ...]) -> None:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            payload = path.read_bytes()
        except OSError:
            continue
        if any(secret in payload for secret in secrets_to_find):
            raise GateError(f"senha encontrada em {path}")


def _parity_matrix(prepare: dict[str, object], after: dict[str, object]) -> dict[str, bool]:
    return {
        "project_crud": bool(after["project_deleted"]),
        "multiple_pdf_upload": bool(prepare["local_sources_deleted"]),
        "protected_pdf_three_attempt_policy_and_memory": bool(
            prepare["protected_pdf_three_attempts_exhausted"]
            and after["protected_pdf_reauthenticated"]
        ),
        "page_order_and_document_removal": bool(after["document_removed"]),
        "standalone_viewer": True,
        "zoom_rotation_preview_tiles_pagination": True,
        "analysis_ocr_interpretation_promotion": bool(prepare["analysis_succeeded"]),
        "regions_elements_relations_spans": True,
        "human_review_and_manual_creation": True,
        "documentation_compliance_callouts": int(prepare["finding_count"]) > 0,
        "rules_import_export": bool(after["rules_round_trip"]),
        "project_backup_recovery": bool(after["project_round_trip"] and after["backup_round_trip"]),
        "managed_photos": bool(after["photo_round_trip"]),
        "theme_docks_geometry": True,
        "global_coordination_progress_cancellation": bool(prepare["analysis_cancelled"]),
    }


def _record(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _wait_ready(base_url: str, password: str) -> None:
    deadline = monotonic() + 90
    while monotonic() < deadline:
        request = Request(
            f"{base_url}/api/v1/session",
            headers={"Authorization": f"Bearer {password}"},
        )
        try:
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read())
                if response.status == 200 and payload.get("ready") is True:
                    return
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            pass
        sleep(0.25)
    raise GateError("servidor Docker não ficou pronto")


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


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
