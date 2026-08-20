"""Inspecione isolamento, permissões e ausência de segredo na imagem do servidor."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def _read_secret(environment_file: Path | None) -> bytes | None:
    if environment_file is None or not environment_file.is_file():
        return None
    for raw_line in environment_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == "ZENY_SERVER_PASSWORD":
            secret = value.strip().encode("utf-8")
            return secret or None
    return None


def _run_runtime_probe(image: str) -> subprocess.CompletedProcess[str]:
    probe = (
        "import importlib.util,os,site; from pathlib import Path; "
        "blocked=('PySide6','zeny_project_handler_client'); "
        "roots=(Path('/app'),*(Path(p) for p in site.getsitepackages())); "
        "bad_name=any(p.name=='.env' for r in roots if r.exists() for p in r.rglob('.env')); "
        "app_dirty=any(Path('/app').iterdir()); "
        "site_writable=any(os.access(p,os.W_OK) for p in map(Path,site.getsitepackages())); "
        "bad=any(importlib.util.find_spec(x) for x in blocked) or bad_name or app_dirty "
        "or site_writable or os.getuid()!=10001 or os.getgid()!=10001; "
        "raise SystemExit(1 if bad else 0)"
    )
    return subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python", image, "-c", probe],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_secret_probe(image: str, secret: bytes) -> subprocess.CompletedProcess[bytes]:
    probe = (
        "import site,sys; from pathlib import Path; secret=sys.stdin.buffer.read(); "
        "roots=(Path('/app'),*(Path(p) for p in site.getsitepackages())); found=False; "
        "files=(p for r in roots if r.exists() for p in r.rglob('*') if p.is_file()); "
        "\nfor p in files:\n"
        " try:\n  found = found or secret in p.read_bytes()\n"
        " except OSError:\n  pass\n"
        "raise SystemExit(1 if found else 0)"
    )
    return subprocess.run(
        ["docker", "run", "--rm", "-i", "--entrypoint", "python", image, "-c", probe],
        input=secret,
        check=False,
        capture_output=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="zeny-project-handler-server:dev")
    parser.add_argument("--secret-env-file", type=Path)
    arguments = parser.parse_args()
    inspect = subprocess.run(
        ["docker", "image", "inspect", arguments.image],
        check=False,
        capture_output=True,
        text=True,
    )
    if inspect.returncode != 0:
        print("GATE DO SERVIDOR: REPROVADO — imagem não encontrada")
        return 1
    metadata = json.loads(inspect.stdout)[0]
    configuration = metadata.get("Config", {})
    user = str(configuration.get("User", ""))
    history = subprocess.run(
        [
            "docker",
            "image",
            "history",
            "--no-trunc",
            "--format",
            "{{.CreatedBy}}",
            arguments.image,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    violations: list[str] = []
    if user != "10001:10001":
        violations.append("imagem não executa com UID/GID fixos 10001:10001")
    if _run_runtime_probe(arguments.image).returncode != 0:
        violations.append(
            "imagem viola permissões runtime, /app vazio, UID/GID ou isolamento do cliente"
        )
    environment = tuple(str(item) for item in configuration.get("Env", ()))
    if any(item.partition("=")[0] == "ZENY_SERVER_PASSWORD" for item in environment):
        violations.append("Config.Env da imagem contém ZENY_SERVER_PASSWORD")
    if configuration.get("Healthcheck") is None:
        violations.append("imagem não possui healthcheck")
    if history.returncode != 0:
        violations.append("histórico da imagem não pôde ser inspecionado")
    elif "ZENY_SERVER_PASSWORD" in history.stdout:
        violations.append("histórico da imagem referencia ZENY_SERVER_PASSWORD")
    secret = _read_secret(arguments.secret_env_file)
    if secret is not None:
        if secret in inspect.stdout.encode("utf-8") or secret in history.stdout.encode("utf-8"):
            violations.append("valor runtime foi encontrado nos metadados ou histórico")
        if _run_secret_probe(arguments.image, secret).returncode != 0:
            violations.append("valor runtime foi encontrado no filesystem final da imagem")
    if violations:
        print("GATE DO SERVIDOR: REPROVADO")
        for item in violations:
            print(f"- {item}")
        return 1
    print("GATE DO SERVIDOR: APROVADO")
    print(
        json.dumps(
            {
                "image": arguments.image,
                "id": metadata.get("Id"),
                "size_bytes": metadata.get("Size"),
                "user": user,
                "healthcheck": True,
                "runtime_secret_checked": secret is not None,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
