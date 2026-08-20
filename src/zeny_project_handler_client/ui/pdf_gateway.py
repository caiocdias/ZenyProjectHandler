"""Gateway HTTP do visualizador cliente; não abre nem inspeciona conteúdo PDF local."""

from __future__ import annotations

import http.client
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Never, Protocol, TypeVar
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel

from zeny_project_handler_contracts import API_V1_PREFIX
from zeny_project_handler_contracts.base import PageId
from zeny_project_handler_contracts.common import NormalizedBoxDto
from zeny_project_handler_contracts.documents import UnlockPdfRequest
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.viewer import (
    CloseViewerSessionResponse,
    CreateViewerSessionResponse,
    RasterMetadataDto,
    UnlockViewerPdfResponse,
    ViewerDocumentDto,
    ViewerPageDto,
    ViewerProjectResponse,
)

_CHUNK_SIZE = 1024 * 1024
_READ_RETRIES = 1
ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class RemoteRaster:
    png: bytes
    metadata: RasterMetadataDto


@dataclass(slots=True)
class ViewerGatewayError(RuntimeError):
    code: ErrorCode
    message: str
    status_code: int | None = None
    correlation_id: str | None = None
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        suffix = f" (correlação {self.correlation_id})" if self.correlation_id else ""
        return f"{self.message}{suffix}"


class PdfViewerGateway(Protocol):
    def create_session(
        self,
        paths: tuple[Path, ...],
        *,
        idempotency_key: str,
    ) -> CreateViewerSessionResponse: ...

    def unlock_session_pdf(
        self,
        session_id: UUID,
        upload_id: UUID,
        password: str,
    ) -> UnlockViewerPdfResponse: ...

    def close_session(self, session_id: UUID) -> CloseViewerSessionResponse: ...

    def get_project(self, project_id: UUID) -> ViewerProjectResponse: ...

    def get_page(self, page_id: UUID) -> ViewerPageDto: ...

    def unlock_project_document(self, document_id: UUID, password: str) -> ViewerDocumentDto: ...

    def render_preview(self, page_id: UUID, *, dpi: int, rotation: int) -> RemoteRaster: ...

    def render_tile(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        clip: NormalizedBoxDto,
    ) -> RemoteRaster: ...


@dataclass(frozen=True, slots=True)
class UnavailablePdfViewerGateway:
    message: str

    def _fail(self) -> Never:
        raise ViewerGatewayError(ErrorCode.AUTHENTICATION_FAILED, self.message)

    def create_session(
        self,
        _paths: tuple[Path, ...],
        *,
        idempotency_key: str,
    ) -> CreateViewerSessionResponse:
        del idempotency_key
        self._fail()

    def unlock_session_pdf(
        self,
        _session_id: UUID,
        _upload_id: UUID,
        _password: str,
    ) -> UnlockViewerPdfResponse:
        self._fail()

    def close_session(self, _session_id: UUID) -> CloseViewerSessionResponse:
        self._fail()

    def get_project(self, _project_id: UUID) -> ViewerProjectResponse:
        self._fail()

    def get_page(self, _page_id: UUID) -> ViewerPageDto:
        self._fail()

    def unlock_project_document(
        self,
        _document_id: UUID,
        _password: str,
    ) -> ViewerDocumentDto:
        self._fail()

    def render_preview(self, _page_id: UUID, *, dpi: int, rotation: int) -> RemoteRaster:
        del dpi, rotation
        self._fail()

    def render_tile(
        self,
        _page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        clip: NormalizedBoxDto,
    ) -> RemoteRaster:
        del dpi, rotation, clip
        self._fail()


@dataclass(slots=True)
class HttpPdfViewerGateway:
    base_url: str
    password: str = field(repr=False)
    timeout_seconds: float = 30.0
    _scheme: str = field(init=False, repr=False)
    _host: str = field(init=False, repr=False)
    _port: int = field(init=False, repr=False)
    _base_path: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("A URL do servidor deve usar http:// ou https:// e conter um host")
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("A URL do servidor não pode conter credenciais, query ou fragmento")
        if not self.password:
            raise ValueError("A senha do servidor é obrigatória")
        if self.timeout_seconds <= 0:
            raise ValueError("O timeout HTTP deve ser positivo")
        self._scheme = parsed.scheme
        self._host = parsed.hostname
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._base_path = parsed.path.rstrip("/")

    def create_session(
        self,
        paths: tuple[Path, ...],
        *,
        idempotency_key: str,
    ) -> CreateViewerSessionResponse:
        if not paths:
            raise ValueError("Selecione ao menos um PDF")
        boundary = f"----zeny-{uuid4().hex}"
        parts = tuple(_multipart_file(path, boundary) for path in paths)
        ending = f"--{boundary}--\r\n".encode()
        content_length = sum(part.size for part in parts) + len(ending)

        def body() -> Iterable[bytes]:
            for part in parts:
                yield part.header
                with part.path.open("rb") as stream:
                    while chunk := stream.read(_CHUNK_SIZE):
                        yield chunk
                yield b"\r\n"
            yield ending

        status, headers, payload = self._request(
            "POST",
            f"{API_V1_PREFIX}/viewer-sessions",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(content_length),
                "Idempotency-Key": idempotency_key,
            },
            body=body(),
        )
        return self._model_response(status, headers, payload, CreateViewerSessionResponse)

    def unlock_session_pdf(
        self,
        session_id: UUID,
        upload_id: UUID,
        password: str,
    ) -> UnlockViewerPdfResponse:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/viewer-sessions/{session_id}/uploads/{upload_id}/unlock",
            UnlockPdfRequest(password=password),
            UnlockViewerPdfResponse,
        )

    def close_session(self, session_id: UUID) -> CloseViewerSessionResponse:
        return self._json_model(
            "DELETE",
            f"{API_V1_PREFIX}/viewer-sessions/{session_id}",
            None,
            CloseViewerSessionResponse,
        )

    def get_project(self, project_id: UUID) -> ViewerProjectResponse:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/projects/{project_id}/viewer",
            None,
            ViewerProjectResponse,
        )

    def get_page(self, page_id: UUID) -> ViewerPageDto:
        return self._json_model(
            "GET",
            f"{API_V1_PREFIX}/viewer-pages/{page_id}",
            None,
            ViewerPageDto,
        )

    def unlock_project_document(self, document_id: UUID, password: str) -> ViewerDocumentDto:
        return self._json_model(
            "POST",
            f"{API_V1_PREFIX}/viewer-documents/{document_id}/unlock",
            UnlockPdfRequest(password=password),
            ViewerDocumentDto,
        )

    def render_preview(self, page_id: UUID, *, dpi: int, rotation: int) -> RemoteRaster:
        return self._raster(
            page_id,
            "preview",
            {"dpi": dpi, "rotation": rotation},
        )

    def render_tile(
        self,
        page_id: UUID,
        *,
        dpi: int,
        rotation: int,
        clip: NormalizedBoxDto,
    ) -> RemoteRaster:
        return self._raster(
            page_id,
            "tiles",
            {
                "x": clip.x,
                "y": clip.y,
                "width": clip.width,
                "height": clip.height,
                "dpi": dpi,
                "rotation": rotation,
            },
        )

    def _raster(
        self,
        page_id: UUID,
        resource: str,
        query: Mapping[str, object],
    ) -> RemoteRaster:
        status, headers, payload = self._request(
            "GET",
            f"{API_V1_PREFIX}/viewer-pages/{page_id}/{resource}?{urlencode(query)}",
        )
        self._raise_for_error(status, headers, payload)
        if headers.get("content-type", "").split(";", 1)[0] != "image/png":
            raise ViewerGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "O servidor devolveu um formato de raster inesperado.",
                status_code=status,
                correlation_id=headers.get("x-correlation-id"),
            )
        metadata = _raster_metadata(headers)
        if metadata.page_id.root != page_id:
            raise ViewerGatewayError(
                ErrorCode.INTEGRITY_ERROR,
                "O raster recebido pertence a outra página.",
                status_code=status,
                correlation_id=headers.get("x-correlation-id"),
            )
        return RemoteRaster(png=payload, metadata=metadata)

    def _json_model(
        self,
        method: str,
        path: str,
        request_model: BaseModel | None,
        response_model: type[ModelT],
    ) -> ModelT:
        payload = None
        request_headers: dict[str, str] = {}
        if request_model is not None:
            payload = request_model.model_dump_json().encode()
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(payload))
        status, headers, content = self._request(
            method,
            path,
            headers=request_headers,
            body=payload,
        )
        return self._model_response(status, headers, content, response_model)

    def _model_response(
        self,
        status: int,
        headers: Mapping[str, str],
        payload: bytes,
        model: type[ModelT],
    ) -> ModelT:
        self._raise_for_error(status, headers, payload)
        try:
            return model.model_validate_json(payload)
        except ValueError as error:
            raise ViewerGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "A resposta do servidor não corresponde ao contrato do visualizador.",
                status_code=status,
                correlation_id=headers.get("x-correlation-id"),
            ) from error

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | Iterable[bytes] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        attempts = _READ_RETRIES + 1 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                return self._request_once(method, path, headers=headers, body=body)
            except (OSError, TimeoutError, http.client.HTTPException) as error:
                if attempt + 1 == attempts:
                    raise ViewerGatewayError(
                        ErrorCode.INTERNAL_ERROR,
                        "O servidor do visualizador está indisponível ou excedeu o tempo limite.",
                    ) from error
        raise AssertionError("Quantidade de tentativas HTTP inválida")

    def _request_once(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None,
        body: bytes | Iterable[bytes] | None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection_type = (
            http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
        )
        connection = connection_type(self._host, self._port, timeout=self.timeout_seconds)
        try:
            connection.putrequest(method, f"{self._base_path}{path}")
            connection.putheader("Authorization", f"Bearer {self.password}")
            connection.putheader("Accept", "application/json, image/png")
            for name, value in (headers or {}).items():
                connection.putheader(name, value)
            connection.endheaders()
            if isinstance(body, bytes):
                connection.send(body)
            elif body is not None:
                for chunk in body:
                    connection.send(chunk)
            response = connection.getresponse()
            response_headers = {name.lower(): value for name, value in response.getheaders()}
            return response.status, response_headers, response.read()
        finally:
            connection.close()

    @staticmethod
    def _raise_for_error(
        status: int,
        headers: Mapping[str, str],
        payload: bytes,
    ) -> None:
        if 200 <= status < 300:
            return
        try:
            envelope = ErrorEnvelope.model_validate_json(payload)
        except ValueError as error:
            raise ViewerGatewayError(
                ErrorCode.INTERNAL_ERROR,
                "O servidor devolveu uma falha sem envelope seguro.",
                status_code=status,
                correlation_id=headers.get("x-correlation-id"),
            ) from error
        raise ViewerGatewayError(
            envelope.code,
            envelope.message,
            status_code=status,
            correlation_id=str(envelope.correlation_id.root),
            details=dict(envelope.details) if envelope.details is not None else None,
        )


@dataclass(frozen=True, slots=True)
class _MultipartFile:
    path: Path
    header: bytes
    size: int


def _multipart_file(path: Path, boundary: str) -> _MultipartFile:
    source = path.expanduser().resolve(strict=True)
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise ValueError("Selecione somente arquivos PDF regulares")
    display_name = source.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files"; filename="{display_name}"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    return _MultipartFile(source, header, len(header) + source.stat().st_size + 2)


def _raster_metadata(headers: Mapping[str, str]) -> RasterMetadataDto:
    try:
        clip_values = headers["x-zeny-clip"].split(",")
        if len(clip_values) != 4:
            raise ValueError("clip")
        clip = NormalizedBoxDto(
            x=clip_values[0],
            y=clip_values[1],
            width=clip_values[2],
            height=clip_values[3],
        )
        return RasterMetadataDto(
            page_id=PageId(UUID(headers["x-zeny-page-id"])),
            pixel_width=int(headers["x-zeny-pixel-width"]),
            pixel_height=int(headers["x-zeny-pixel-height"]),
            page_pixel_width=int(headers["x-zeny-page-pixel-width"]),
            page_pixel_height=int(headers["x-zeny-page-pixel-height"]),
            origin_x_pixels=int(headers["x-zeny-origin-x"]),
            origin_y_pixels=int(headers["x-zeny-origin-y"]),
            requested_dpi=int(headers["x-zeny-requested-dpi"]),
            effective_dpi=int(headers["x-zeny-effective-dpi"]),
            rotation_degrees=int(headers["x-zeny-rotation"]),
            clip=clip,
            reduced=headers["x-zeny-reduced"].lower() == "true",
            content_type="image/png",
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ViewerGatewayError(
            ErrorCode.INTEGRITY_ERROR,
            "Os metadados do raster remoto estão ausentes ou inválidos.",
        ) from error
