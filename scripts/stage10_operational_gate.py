"""Ensaie lifecycle, hardening e falhas fechadas da imagem do servidor."""

from __future__ import annotations

import argparse
import json
import secrets
import socket
import subprocess
import tempfile
from pathlib import Path
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


class GateError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="zeny-project-handler-server:dev")
    parser.add_argument("--compose-file", type=Path, default=Path("compose.yaml"))
    arguments = parser.parse_args()
    suffix = uuid4().hex[:10]
    project = f"zph-stage10-{suffix}"
    first_password = secrets.token_urlsafe(32)
    second_password = secrets.token_urlsafe(32)
    port = _available_port()
    volumes: set[str] = set()
    containers: set[str] = set()
    temporary_images: set[str] = set()
    compose_prefix: list[str] = []
    try:
        _run(["docker", "info"])
        with tempfile.TemporaryDirectory(prefix="zph-stage10-gate-") as temporary_name:
            environment_file = Path(temporary_name) / "runtime.env"
            _write_environment(environment_file, first_password, port, arguments.image)
            compose_prefix = [
                "docker",
                "compose",
                "--project-name",
                project,
                "--env-file",
                str(environment_file),
                "-f",
                str(arguments.compose_file.resolve()),
            ]
            _run([*compose_prefix, "config", "--quiet"])
            _run([*compose_prefix, "up", "-d", "--no-build"])
            volume = f"{project}_zeny-data"
            volumes.add(volume)
            base_url = f"http://127.0.0.1:{port}"
            _wait_http(base_url, first_password)
            container = _run([*compose_prefix, "ps", "-q", "server"]).stdout.strip()
            if not container:
                raise GateError("O Compose não informou o container do servidor")
            _assert_hardening(container)
            project_id = _create_project(base_url, first_password)
            _assert_project_visible(base_url, first_password, project_id)
            _assert_project_visible(base_url, first_password, project_id)
            _run(
                [
                    "docker",
                    "exec",
                    container,
                    "python",
                    "-c",
                    "from pathlib import Path; Path('/data/.stage10-marker').write_text('ok')",
                ]
            )
            _run([*compose_prefix, "restart", "server"])
            _wait_http(base_url, first_password)
            _assert_project_visible(base_url, first_password, project_id)
            _assert_secret_not_logged(container, first_password)
            _run([*compose_prefix, "down"])
            _run(["docker", "volume", "inspect", volume])
            _run([*compose_prefix, "up", "-d", "--no-build"])
            _wait_http(base_url, first_password)
            _assert_project_visible(base_url, first_password, project_id)
            recreated = _run([*compose_prefix, "ps", "-q", "server"]).stdout.strip()
            marker_probe = (
                "from pathlib import Path; print(Path('/data/.stage10-marker').read_text())"
            )
            marker = _run(
                ["docker", "exec", recreated, "python", "-c", marker_probe]
            ).stdout.strip()
            if marker != "ok":
                raise GateError("O marcador do volume não sobreviveu ao down/up")

            _write_environment(environment_file, second_password, port, arguments.image)
            _run([*compose_prefix, "up", "-d", "--no-build", "--force-recreate"])
            _wait_http(base_url, second_password)
            if _http_status(f"{base_url}/api/v1/session", first_password) != 401:
                raise GateError("A senha anterior continuou válida após a rotação")
            _assert_project_visible(base_url, second_password, project_id)
            rotated = _run([*compose_prefix, "ps", "-q", "server"]).stdout.strip()
            _assert_secret_not_logged(rotated, first_password, second_password)

            update_image = f"zph-stage10-update:{suffix}"
            temporary_images.add(update_image)
            _run(["docker", "tag", arguments.image, update_image])
            _write_environment(environment_file, second_password, port, update_image)
            _run([*compose_prefix, "up", "-d", "--no-build", "--force-recreate"])
            _wait_http(base_url, second_password)
            updated = _run([*compose_prefix, "ps", "-q", "server"]).stdout.strip()
            _assert_container_image(updated, update_image)
            _assert_project_visible(base_url, second_password, project_id)
            _assert_secret_not_logged(updated, second_password)

            _write_environment(environment_file, second_password, port, arguments.image)
            _run([*compose_prefix, "up", "-d", "--no-build", "--force-recreate"])
            _wait_http(base_url, second_password)
            rolled_back = _run([*compose_prefix, "ps", "-q", "server"]).stdout.strip()
            _assert_container_image(rolled_back, arguments.image)
            _assert_project_visible(base_url, second_password, project_id)
            _assert_secret_not_logged(rolled_back, second_password)

        _exercise_missing_ocr(arguments.image, suffix, volumes, containers)
        _exercise_read_only_volume(arguments.image, suffix, volumes, containers)
        _exercise_corrupted_database(arguments.image, suffix, volumes, containers)
        _exercise_future_revision(arguments.image, suffix, volumes, containers)
    except (GateError, subprocess.SubprocessError, OSError) as error:
        print(f"GATE OPERACIONAL DA ETAPA 10: REPROVADO — {error}")
        return 1
    finally:
        if compose_prefix:
            _run([*compose_prefix, "down"], check=False)
        compose_containers = _run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={project}",
            ],
            check=False,
        ).stdout.split()
        for container in compose_containers:
            _run(["docker", "rm", "--force", container], check=False)
        for container in containers:
            _run(["docker", "rm", "--force", container], check=False)
        _run(["docker", "network", "rm", f"{project}_default"], check=False)
        for volume in volumes:
            _run(["docker", "volume", "rm", volume], check=False)
        for image in temporary_images:
            _run(["docker", "image", "rm", image], check=False)
    print("GATE OPERACIONAL DA ETAPA 10: APROVADO")
    print(
        json.dumps(
            {
                "compose_down_up": True,
                "restart_recreate": True,
                "password_rotation": True,
                "image_update_recreate": True,
                "rollback_compatible_image": True,
                "runtime_logs_secret_free": True,
                "two_clients": True,
                "missing_ocr_degraded_only": True,
                "read_only_volume_fail_closed": True,
                "corrupt_database_fail_closed": True,
                "future_revision_fail_closed": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _exercise_missing_ocr(
    image: str,
    suffix: str,
    volumes: set[str],
    containers: set[str],
) -> None:
    volume = f"zph-stage10-ocr-{suffix}"
    container = f"zph-stage10-ocr-{suffix}"
    volumes.add(volume)
    containers.add(container)
    _run(["docker", "volume", "create", volume])
    port = _available_port()
    password = secrets.token_urlsafe(32)
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
            "--mount",
            f"source={volume},target=/data",
            "--publish",
            f"127.0.0.1:{port}:8000",
            "--env",
            f"ZENY_SERVER_PASSWORD={password}",
            "--env",
            "ZENY_TESSERACT_PATH=/missing-tesseract",
            image,
        ]
    )
    payload = _wait_http(f"http://127.0.0.1:{port}", password)
    if not payload.get("ready") or payload.get("ocr", {}).get("status") == "AVAILABLE":
        raise GateError("A ausência do OCR não produziu diagnóstico degradado com ready=true")
    _run(["docker", "rm", "--force", container])
    containers.remove(container)


def _exercise_read_only_volume(
    image: str,
    suffix: str,
    volumes: set[str],
    containers: set[str],
) -> None:
    volume = f"zph-stage10-permission-{suffix}"
    container = f"zph-stage10-permission-{suffix}"
    volumes.add(volume)
    containers.add(container)
    _run(["docker", "volume", "create", volume])
    result = _run(
        [
            "docker",
            "run",
            "--name",
            container,
            "--mount",
            f"source={volume},target=/data,readonly",
            "--env",
            f"ZENY_SERVER_PASSWORD={secrets.token_urlsafe(32)}",
            image,
        ],
        check=False,
        timeout=45,
    )
    if result.returncode == 0:
        raise GateError("O servidor iniciou com o volume montado somente para leitura")
    _run(["docker", "rm", container])
    containers.remove(container)


def _exercise_corrupted_database(
    image: str,
    suffix: str,
    volumes: set[str],
    containers: set[str],
) -> None:
    volume = f"zph-stage10-corrupt-{suffix}"
    volumes.add(volume)
    _initialize_volume(image, volume, f"zph-stage10-corrupt-init-{suffix}")
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--mount",
            f"source={volume},target=/data",
            "--entrypoint",
            "python",
            image,
            "-c",
            (
                "from pathlib import Path; "
                "Path('/data/zeny-project-handler.sqlite3').write_bytes(b'corrupted-stage10')"
            ),
        ]
    )
    container = f"zph-stage10-corrupt-check-{suffix}"
    containers.add(container)
    result = _run(
        [
            "docker",
            "run",
            "--name",
            container,
            "--mount",
            f"source={volume},target=/data",
            "--env",
            f"ZENY_SERVER_PASSWORD={secrets.token_urlsafe(32)}",
            image,
        ],
        check=False,
        timeout=45,
    )
    if result.returncode == 0:
        raise GateError("O servidor iniciou sobre um banco corrompido")
    _run(["docker", "rm", container])
    containers.remove(container)


def _exercise_future_revision(
    image: str,
    suffix: str,
    volumes: set[str],
    containers: set[str],
) -> None:
    volume = f"zph-stage10-future-{suffix}"
    volumes.add(volume)
    _initialize_volume(image, volume, f"zph-stage10-future-init-{suffix}")
    update = (
        "import sqlite3; from contextlib import closing; "
        "c=sqlite3.connect('/data/zeny-project-handler.sqlite3'); "
        "c.execute(\"UPDATE alembic_version SET version_num='9999_future_schema'\"); "
        "c.commit(); c.close()"
    )
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--mount",
            f"source={volume},target=/data",
            "--entrypoint",
            "python",
            image,
            "-c",
            update,
        ]
    )
    container = f"zph-stage10-future-check-{suffix}"
    containers.add(container)
    result = _run(
        [
            "docker",
            "run",
            "--name",
            container,
            "--mount",
            f"source={volume},target=/data",
            "--env",
            f"ZENY_SERVER_PASSWORD={secrets.token_urlsafe(32)}",
            image,
        ],
        check=False,
        timeout=45,
    )
    if result.returncode == 0:
        raise GateError("Uma imagem incompatível aceitou revisão futura do banco")
    _run(["docker", "rm", container])
    containers.remove(container)
    query = (
        "import sqlite3; c=sqlite3.connect('/data/zeny-project-handler.sqlite3'); "
        "print(c.execute('SELECT version_num FROM alembic_version').fetchone()[0]); c.close()"
    )
    preserved = _run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--mount",
            f"source={volume},target=/data",
            "--entrypoint",
            "python",
            image,
            "-c",
            query,
        ]
    ).stdout.strip()
    if preserved != "9999_future_schema":
        raise GateError("A falha incompatível alterou a revisão preservada no volume")


def _initialize_volume(image: str, volume: str, container: str) -> None:
    password = secrets.token_urlsafe(32)
    _run(["docker", "volume", "create", volume])
    _run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            container,
            "--mount",
            f"source={volume},target=/data",
            "--env",
            f"ZENY_SERVER_PASSWORD={password}",
            image,
        ]
    )
    deadline = monotonic() + 45
    while monotonic() < deadline:
        status = _run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", container],
            check=False,
        ).stdout.strip()
        if status == "healthy":
            break
        if status == "unhealthy":
            raise GateError("O volume de fixture não ficou saudável")
        sleep(0.25)
    else:
        raise GateError("Timeout ao inicializar volume de fixture")
    _run(["docker", "rm", "--force", container])


def _assert_hardening(container: str) -> None:
    metadata = json.loads(_run(["docker", "inspect", container]).stdout)[0]
    host = metadata["HostConfig"]
    config = metadata["Config"]
    if config.get("User") != "10001:10001":
        raise GateError("O container não usa UID/GID fixos")
    if not host.get("ReadonlyRootfs"):
        raise GateError("O root filesystem não está somente para leitura")
    if "ALL" not in (host.get("CapDrop") or ()):
        raise GateError("As capabilities Linux não foram removidas")
    if "no-new-privileges:true" not in (host.get("SecurityOpt") or ()):
        raise GateError("no-new-privileges não está ativo")
    if int(host.get("PidsLimit") or 0) <= 0 or int(host.get("Memory") or 0) <= 0:
        raise GateError("Limites de PIDs/memória não estão ativos")
    write_probe = _run(
        [
            "docker",
            "exec",
            container,
            "python",
            "-c",
            "from pathlib import Path; Path('/app/forbidden').write_text('x')",
        ],
        check=False,
    )
    if write_probe.returncode == 0:
        raise GateError("O usuário runtime conseguiu gravar em /app")


def _assert_container_image(container: str, expected_image: str) -> None:
    actual = _run(["docker", "inspect", "--format", "{{.Config.Image}}", container]).stdout.strip()
    if actual != expected_image:
        raise GateError(f"Container usa imagem {actual!r}, esperada {expected_image!r}")


def _assert_secret_not_logged(container: str, *secrets_to_check: str) -> None:
    result = _run(["docker", "logs", container])
    logs = result.stdout + result.stderr
    if any(secret in logs for secret in secrets_to_check):
        raise GateError("Um segredo de runtime foi encontrado nos logs do container")


def _write_environment(path: Path, password: str, port: int, image: str) -> None:
    path.write_text(
        "\n".join(
            (
                f"ZENY_SERVER_PASSWORD={password}",
                f"ZENY_SERVER_IMAGE={image}",
                "ZENY_SERVER_BIND_ADDRESS=127.0.0.1",
                f"ZENY_SERVER_PORT={port}",
                "ZENY_SERVER_MEMORY_LIMIT=2g",
                "ZENY_SERVER_PIDS_LIMIT=256",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def _create_project(base_url: str, password: str) -> str:
    status, payload = _json_request(
        f"{base_url}/api/v1/projects",
        password,
        method="POST",
        body={"service_note": "0010203040"},
        extra_headers={"Idempotency-Key": "stage10-operational-project"},
    )
    if status != 201:
        raise GateError(f"Criação do projeto retornou HTTP {status}")
    return str(payload["project"]["project_id"])


def _assert_project_visible(base_url: str, password: str, project_id: str) -> None:
    status, payload = _json_request(f"{base_url}/api/v1/projects", password)
    identifiers = {str(item["project_id"]) for item in payload.get("items", ())}
    if status != 200 or project_id not in identifiers:
        raise GateError("Um dos clientes não observou o projeto persistido")


def _wait_http(base_url: str, password: str) -> dict[str, object]:
    deadline = monotonic() + 60
    while monotonic() < deadline:
        status, payload = _json_request(f"{base_url}/api/v1/session", password)
        if status == 200 and payload.get("ready") is True:
            return payload
        sleep(0.25)
    raise GateError("Timeout aguardando readiness autenticada")


def _http_status(url: str, password: str) -> int:
    status, _payload = _json_request(url, password)
    return status


def _json_request(
    url: str,
    password: str,
    *,
    method: str = "GET",
    body: dict[str, object] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Authorization": f"Bearer {password}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    headers.update(extra_headers or {})
    request = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=3) as response:
            return int(response.status), json.loads(response.read())
    except HTTPError as error:
        try:
            payload = json.loads(error.read())
        except (ValueError, OSError):
            payload = {}
        return int(error.code), payload
    except (URLError, TimeoutError, OSError):
        return 0, {}


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _run(
    command: list[str],
    *,
    check: bool = True,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        name = " ".join(command[:3])
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = detail[-1] if detail else "sem diagnóstico"
        raise GateError(f"{name} falhou: {suffix}")
    return completed


if __name__ == "__main__":
    raise SystemExit(main())
