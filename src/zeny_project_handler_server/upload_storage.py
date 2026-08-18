"""Recepção limitada e publicação atômica de uploads do servidor."""

from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from uuid import UUID, uuid4

from fastapi import UploadFile

from zeny_project_handler_server.api_errors import UploadTooLargeError, validation_error

_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class ReceivedUpload:
    path: Path
    display_name: str
    content_type: str | None
    size_bytes: int
    sha256: str


@dataclass(slots=True)
class PublishedUpload:
    """Troca reversível até o commit do banco confirmar a publicação."""

    source: Path
    destination: Path
    destination_preexisted: bool

    def complete(self) -> None:
        if self.source != self.destination:
            self.source.unlink(missing_ok=True)

    def restore_source(self) -> None:
        if self.destination_preexisted:
            return
        if not self.destination.exists():
            return
        if self.source.exists():
            self.destination.unlink()
            return
        os.replace(self.destination, self.source)

    def move_to_pending(self, pending: Path) -> None:
        pending.parent.mkdir(parents=True, exist_ok=True)
        if self.destination_preexisted and self.source.exists():
            os.replace(self.source, pending)
        elif self.destination.exists():
            os.replace(self.destination, pending)
        elif self.source.exists():
            os.replace(self.source, pending)
        else:
            raise OSError("O upload protegido não está disponível para retenção")
        if self.source != pending:
            self.source.unlink(missing_ok=True)


class ManagedUploadStorage:
    """Escolha todos os caminhos sob a raiz de dados e nunca aceite destino do cliente."""

    def __init__(self, data_directory: Path, *, maximum_bytes: int) -> None:
        self.data_directory = data_directory.expanduser().resolve()
        self.maximum_bytes = maximum_bytes
        self.upload_root = self.data_directory / "uploads"
        self.incoming_root = self.upload_root / "incoming"
        self.pending_root = self.upload_root / "pending"
        self.managed_root = self.data_directory / "project-files"
        self._prepare_roots()

    async def receive(self, upload: UploadFile) -> ReceivedUpload:
        display_name = sanitize_display_name(upload.filename)
        temporary = self.incoming_root / f"{uuid4()}.part"
        digest = sha256()
        size = 0
        try:
            with temporary.open("xb") as output:
                while chunk := await upload.read(_CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.maximum_bytes:
                        raise UploadTooLargeError(self.maximum_bytes)
                    output.write(chunk)
                    digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            if size == 0:
                raise validation_error("O arquivo enviado está vazio.")
            return ReceivedUpload(
                path=temporary,
                display_name=display_name,
                content_type=upload.content_type,
                size_bytes=size,
                sha256=digest.hexdigest(),
            )
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def publish_document(
        self,
        upload: ReceivedUpload,
        *,
        project_id: UUID,
        document_id: UUID,
    ) -> PublishedUpload:
        project_root = self._project_root(project_id)
        destination = project_root / "documents" / f"{document_id}.pdf"
        return self._publish(upload, destination)

    def publish_pending(
        self,
        source: Path,
        *,
        project_id: UUID,
        document_id: UUID,
    ) -> PublishedUpload:
        destination = self._project_root(project_id) / "documents" / f"{document_id}.pdf"
        received = ReceivedUpload(
            path=self._contained_pending(source),
            display_name=f"{document_id}.pdf",
            content_type="application/pdf",
            size_bytes=source.stat().st_size,
            sha256=_file_sha256(source),
        )
        return self._publish(received, destination)

    def pending_path(self, upload_id: UUID) -> Path:
        return self.pending_root / f"{upload_id}.pdf"

    def pending_relative_path(self, upload_id: UUID) -> str:
        return f"pending/{upload_id}.pdf"

    def resolve_pending_relative(self, relative: str) -> Path:
        candidate = PurePosixPath(relative)
        if candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 2:
            raise validation_error("A referência interna do upload é inválida.")
        path = (self.upload_root / candidate).resolve()
        return self._contained_pending(path)

    def discard(self, upload: ReceivedUpload) -> None:
        upload.path.unlink(missing_ok=True)

    def cleanup_interrupted(self) -> int:
        """Remova somente partes sem publicação deixadas por processo anterior."""
        removed = 0
        for path in self.incoming_root.glob("*.part"):
            if path.is_file() and not path.is_symlink():
                path.unlink()
                removed += 1
        return removed

    def _publish(self, upload: ReceivedUpload, destination: Path) -> PublishedUpload:
        self._assert_regular_source(upload.path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._assert_contained(destination, self.managed_root)
        existed = destination.exists()
        if existed:
            self._assert_regular_source(destination)
            if (
                destination.stat().st_size != upload.size_bytes
                or _file_sha256(destination) != upload.sha256
            ):
                raise validation_error("Um arquivo gerenciado diverge da identidade esperada.")
        else:
            os.replace(upload.path, destination)
        return PublishedUpload(upload.path, destination, existed)

    def _prepare_roots(self) -> None:
        self.data_directory.mkdir(parents=True, exist_ok=True)
        for path in (self.upload_root, self.incoming_root, self.pending_root):
            if os.path.lexists(path) and (path.is_symlink() or not path.is_dir()):
                raise RuntimeError("A raiz de uploads gerenciados não é um diretório regular")
            path.mkdir(exist_ok=True)

    def _project_root(self, project_id: UUID) -> Path:
        root = (self.managed_root / str(project_id)).resolve()
        self._assert_contained(root, self.managed_root)
        return root

    def _contained_pending(self, path: Path) -> Path:
        resolved = path.resolve()
        self._assert_contained(resolved, self.pending_root)
        return resolved

    @staticmethod
    def _assert_contained(path: Path, root: Path) -> None:
        resolved_root = root.resolve()
        if not path.resolve().is_relative_to(resolved_root):
            raise validation_error("Um caminho interno saiu da raiz gerenciada.")

    @staticmethod
    def _assert_regular_source(path: Path) -> None:
        if path.is_symlink() or not path.is_file():
            raise validation_error("O upload temporário não é um arquivo regular.")


def sanitize_display_name(raw_name: str | None) -> str:
    name = (raw_name or "").strip()
    if not name or len(name) > 255 or any(ord(character) < 32 for character in name):
        raise validation_error("O nome de exibição do arquivo é inválido.")
    if PurePosixPath(name).name != name or PureWindowsPath(name).name != name:
        raise validation_error("Envie apenas o nome de exibição, sem caminho local.")
    return name


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()
