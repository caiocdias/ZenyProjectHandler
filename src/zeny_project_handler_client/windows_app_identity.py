"""Identidade visual do processo cliente no Windows."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from pathlib import Path

WINDOWS_APP_USER_MODEL_ID = "Zeny.ZenyProjectHandler.Client"


def configurar_identidade_aplicativo_windows() -> None:
    if sys.platform != "win32":
        return
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    setter = shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [ctypes.c_wchar_p]
    setter.restype = ctypes.c_long
    result = int(setter(WINDOWS_APP_USER_MODEL_ID))
    if result != 0:
        raise OSError(
            f"O Windows recusou a identidade do cliente (HRESULT {result & 0xFFFFFFFF:#010x})."
        )


def configurar_identidade_janela_windows(
    _window_handle: int,
    *,
    icon_path: Path,
    relaunch_command: str,
    application_name: str,
) -> Callable[[], None]:
    """Valide metadados do relançamento; o Qt mantém o ícone da janela."""
    del relaunch_command, application_name
    if sys.platform == "win32" and not icon_path.is_file():
        raise FileNotFoundError(icon_path)
    return lambda: None
