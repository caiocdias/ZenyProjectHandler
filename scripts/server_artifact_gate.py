"""Inspecione a imagem do servidor para impedir mistura com o cliente Qt."""

from __future__ import annotations

import argparse
import json
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="zeny-project-handler-server:dev")
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
    user = str(metadata.get("Config", {}).get("User", ""))
    probe = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            arguments.image,
            "-c",
            (
                "import importlib.util; "
                "blocked=('PySide6','zeny_project_handler_client'); "
                "raise SystemExit(1 if any(importlib.util.find_spec(x) for x in blocked) else 0)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    violations = []
    if not user or user.casefold() in {"0", "root"}:
        violations.append("imagem executa como root")
    if probe.returncode != 0:
        violations.append("imagem contém PySide6 ou zeny_project_handler_client")
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
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
