"""Integração da identidade do processo com a barra de tarefas do Windows."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from uuid import UUID

WINDOWS_APP_USER_MODEL_ID = "Zeny.ZenyProjectHandler"
_APP_USER_MODEL_FORMAT_ID = "9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"
_I_PROPERTY_STORE_ID = "886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"
_VT_EMPTY = 0
_VT_LPWSTR = 31


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_ushort),
        ("data3", ctypes.c_ushort),
        ("data4", ctypes.c_ubyte * 8),
    ]


class _PropertyKey(ctypes.Structure):
    _fields_ = [("format_id", _Guid), ("property_id", ctypes.c_uint32)]


class _PropVariantValue(ctypes.Union):
    _fields_ = [  # noqa: RUF012 - metadado obrigatório e mutável da API ctypes
        ("wide_string", ctypes.c_wchar_p),
        ("pointer", ctypes.c_void_p),
    ]


class _PropVariant(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [
        ("variant_type", ctypes.c_ushort),
        ("reserved1", ctypes.c_ushort),
        ("reserved2", ctypes.c_ushort),
        ("reserved3", ctypes.c_ushort),
        ("value", _PropVariantValue),
    ]


_PROPERTY_KEYS = {
    "relaunch_command": 2,
    "relaunch_icon": 3,
    "relaunch_display_name": 4,
    "app_user_model_id": 5,
}


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


def configurar_identidade_janela_windows(
    window_handle: int,
    *,
    icon_path: Path,
    relaunch_command: str,
    application_name: str,
) -> Callable[[], None]:
    """Associe à janela o ícone e os metadados usados pela barra de tarefas."""
    if sys.platform != "win32":
        return lambda: None

    propriedades = {
        "app_user_model_id": WINDOWS_APP_USER_MODEL_ID,
        "relaunch_command": relaunch_command,
        "relaunch_display_name": application_name,
        "relaunch_icon": f"{icon_path.resolve()},0",
    }
    _definir_propriedades_janela(window_handle, propriedades)
    cleared = False

    def limpar() -> None:
        nonlocal cleared
        if cleared:
            return
        _definir_propriedades_janela(
            window_handle,
            dict.fromkeys(propriedades),
        )
        cleared = True

    return limpar


def _definir_app_user_model_id(app_user_model_id: str) -> int:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    setter = shell32.SetCurrentProcessExplicitAppUserModelID
    setter.argtypes = [ctypes.c_wchar_p]
    setter.restype = ctypes.c_long
    return int(setter(app_user_model_id))


def _definir_propriedades_janela(
    window_handle: int,
    propriedades: Mapping[str, str | None],
) -> None:
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    get_property_store = shell32.SHGetPropertyStoreForWindow
    get_property_store.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    get_property_store.restype = ctypes.c_long
    interface_id = _guid(_I_PROPERTY_STORE_ID)
    property_store = ctypes.c_void_p()
    result = int(
        get_property_store(
            ctypes.c_void_p(window_handle),
            ctypes.byref(interface_id),
            ctypes.byref(property_store),
        )
    )
    _verificar_hresult(result, "obter as propriedades da janela")

    function_type = ctypes.WINFUNCTYPE
    vtable = ctypes.cast(
        property_store,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ).contents
    set_value = function_type(
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.POINTER(_PropertyKey),
        ctypes.POINTER(_PropVariant),
    )(vtable[6])
    release = function_type(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])
    try:
        for nome, valor in propriedades.items():
            property_id = _PROPERTY_KEYS[nome]
            key = _PropertyKey(_guid(_APP_USER_MODEL_FORMAT_ID), property_id)
            variant = _prop_variant(valor)
            result = int(set_value(property_store, ctypes.byref(key), ctypes.byref(variant)))
            _verificar_hresult(result, f"definir a propriedade {nome}")
    finally:
        release(property_store)


def _guid(value: str) -> _Guid:
    return _Guid.from_buffer_copy(UUID(value).bytes_le)


def _prop_variant(value: str | None) -> _PropVariant:
    variant = _PropVariant()
    if value is None:
        variant.variant_type = _VT_EMPTY
    else:
        variant.variant_type = _VT_LPWSTR
        variant.wide_string = value
    return variant


def _verificar_hresult(result: int, operation: str) -> None:
    if result < 0:
        hresult = result & 0xFFFFFFFF
        raise OSError(f"Falha ao {operation} na integração com o Windows ({hresult:#010x}).")
