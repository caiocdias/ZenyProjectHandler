"""Integração da identidade do processo com a barra de tarefas do Windows."""

from __future__ import annotations

import ctypes
import sys

WINDOWS_APP_USER_MODEL_ID = "Zeny.ZenyProjectHandler"


def configurar_identidade_aplicativo_windows() -> None:
    """Identifique o processo para agrupamento e ícone corretos na barra de tarefas."""
    if sys.platform != "win32":
        return

    result = _definir_app_user_model_id(WINDOWS_APP_USER_MODEL_ID)
    if result != 0:
        hresult = result & 0xFFFFFFFF
        raise OSError(
            f"O Windows recusou o identificador do aplicativo "
            f"{WINDOWS_APP_USER_MODEL_ID!r} (HRESULT {hresult:#010x})."
        )


def _definir_app_user_model_id(app_user_model_id: str) -> int:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    setter = shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [ctypes.c_wchar_p]
    setter.restype = ctypes.c_long
    return int(setter(app_user_model_id))
