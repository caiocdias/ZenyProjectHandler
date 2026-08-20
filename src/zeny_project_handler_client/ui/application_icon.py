"""Carregamento do ícone empacotado do cliente."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QIcon, QImageReader, QPixmap

from zeny_project_handler_client.assets import APPLICATION_ICON_ICO

_ASSET_PACKAGE = "zeny_project_handler_client.assets"


def materializar_icone_aplicacao(diretorio: Path) -> Path:
    """Disponibilize o ICO em caminho estável para o shell do Windows."""
    payload = _ler_payload_icone()
    destino = diretorio / APPLICATION_ICON_ICO
    try:
        atual = destino.read_bytes()
    except FileNotFoundError:
        atual = None
    if atual != payload:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(payload)
    return destino


def carregar_icone_aplicacao() -> QIcon:
    """Leia todos os frames do ICO pelo pacote, inclusive dentro de um wheel."""
    payload = _ler_payload_icone()

    buffer = QBuffer()
    buffer.setData(QByteArray(payload))
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        raise RuntimeError("Não foi possível abrir o ícone empacotado para leitura pelo Qt.")

    reader = QImageReader(buffer, b"ico")
    frame_count = reader.imageCount()
    if frame_count <= 0:
        raise RuntimeError(
            f"O Qt não reconheceu frames em {_ASSET_PACKAGE}/{APPLICATION_ICON_ICO}: "
            f"{reader.errorString()}"
        )

    icon = QIcon()
    for frame_index in range(frame_count):
        if not reader.jumpToImage(frame_index):
            raise RuntimeError(
                f"O Qt não conseguiu acessar o frame {frame_index} do ícone empacotado: "
                f"{reader.errorString()}"
            )
        image = reader.read()
        if image.isNull():
            raise RuntimeError(
                f"O Qt não conseguiu decodificar o frame {frame_index} do ícone empacotado: "
                f"{reader.errorString()}"
            )
        icon.addPixmap(QPixmap.fromImage(image))

    if icon.isNull():
        raise RuntimeError("O ícone empacotado foi lido, mas resultou em um QIcon nulo.")
    return icon


def _ler_payload_icone() -> bytes:
    try:
        payload = files(_ASSET_PACKAGE).joinpath(APPLICATION_ICON_ICO).read_bytes()
    except (FileNotFoundError, OSError) as error:
        raise RuntimeError(
            f"Não foi possível ler o ícone empacotado {_ASSET_PACKAGE}/{APPLICATION_ICON_ICO}."
        ) from error
    if not payload:
        raise RuntimeError(
            f"O ícone empacotado {_ASSET_PACKAGE}/{APPLICATION_ICON_ICO} está vazio."
        )
    return payload
