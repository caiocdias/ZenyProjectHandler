from __future__ import annotations

import json
import shutil
import subprocess
import sys
from hashlib import sha256
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

import zeny_project_handler
from zeny_project_handler_client.assets import APPLICATION_ICON_ICO, APPLICATION_ICON_PNG
from zeny_project_handler_client.ui import application_icon

PROJECT_ROOT = Path(__file__).parents[2]
ASSET_PACKAGE = "zeny_project_handler_client.assets"


def _asset_payload(file_name: str) -> bytes:
    return files(ASSET_PACKAGE).joinpath(file_name).read_bytes()


@pytest.mark.integration
def test_package_exposes_version() -> None:
    assert zeny_project_handler.__version__ == "0.1.1"


@pytest.mark.integration
def test_application_icon_assets_are_valid_in_checkout() -> None:
    png_payload = _asset_payload(APPLICATION_ICON_PNG)
    ico_payload = _asset_payload(APPLICATION_ICON_ICO)

    with Image.open(BytesIO(png_payload)) as png:
        assert png.format == "PNG"
        assert png.size == (1024, 1024)
        assert png.mode == "RGBA"
        assert png.getchannel("A").getextrema() == (0, 255)

    with Image.open(BytesIO(ico_payload)) as ico:
        assert ico.format == "ICO"
        sizes = set(ico.info["sizes"])

    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= sizes


@pytest.mark.integration
def test_missing_application_icon_has_clear_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingResource:
        def joinpath(self, _file_name: str) -> MissingResource:
            return self

        def read_bytes(self) -> bytes:
            raise FileNotFoundError("asset ausente")

    monkeypatch.setattr(application_icon, "files", lambda _package: MissingResource())

    with pytest.raises(RuntimeError, match="Não foi possível ler o ícone empacotado"):
        application_icon.carregar_icone_aplicacao()


@pytest.mark.integration
def test_application_icon_can_be_materialized_for_the_windows_shell(tmp_path: Path) -> None:
    destination = application_icon.materializar_icone_aplicacao(tmp_path)

    assert destination == tmp_path / APPLICATION_ICON_ICO
    assert destination.read_bytes() == _asset_payload(APPLICATION_ICON_ICO)


@pytest.mark.integration
def test_independent_client_wheel_installs_both_icon_assets(tmp_path: Path) -> None:
    source = tmp_path / "wheel-source"
    shutil.copytree(
        PROJECT_ROOT / "src" / "zeny_project_handler_client",
        source / "src" / "zeny_project_handler_client",
    )
    shutil.copytree(
        PROJECT_ROOT / "src" / "zeny_project_handler_contracts",
        source / "src" / "zeny_project_handler_contracts",
    )
    shutil.copytree(PROJECT_ROOT / "client", source / "client")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()

    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-index",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheelhouse),
            str(source / "client"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheel = next(wheelhouse.glob("zeny_project_handler_client-*.whl"))
    expected_members = {
        f"zeny_project_handler_client/assets/{APPLICATION_ICON_PNG}",
        f"zeny_project_handler_client/assets/{APPLICATION_ICON_ICO}",
    }
    with ZipFile(wheel) as archive:
        members = set(archive.namelist())
        assert expected_members <= members
        assert not any(
            member.startswith(("zeny_project_handler/", "zeny_project_handler_server/"))
            for member in members
        )

    installation = tmp_path / "installed"
    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-index",
            "--no-deps",
            "--target",
            str(installation),
            str(wheel),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    verification_code = """
import json
import sys
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

target = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(target))
import zeny_project_handler_client

assert Path(zeny_project_handler_client.__file__).resolve().is_relative_to(target)
assets = files("zeny_project_handler_client.assets")
digests = {
    name: sha256(assets.joinpath(name).read_bytes()).hexdigest()
    for name in sys.argv[2:]
}
print(json.dumps(digests))
"""
    verification = subprocess.run(
        [
            sys.executable,
            "-c",
            verification_code,
            str(installation),
            APPLICATION_ICON_PNG,
            APPLICATION_ICON_ICO,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verification.returncode == 0, verification.stdout + verification.stderr
    installed_hashes = json.loads(verification.stdout)
    assert installed_hashes == {
        APPLICATION_ICON_PNG: sha256(_asset_payload(APPLICATION_ICON_PNG)).hexdigest(),
        APPLICATION_ICON_ICO: sha256(_asset_payload(APPLICATION_ICON_ICO)).hexdigest(),
    }
