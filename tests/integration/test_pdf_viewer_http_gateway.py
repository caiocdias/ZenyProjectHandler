from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import closing
from io import BytesIO
from pathlib import Path
from socket import create_server
from threading import Event, Thread
from uuid import uuid4

import pytest
from PIL import Image
from tests.pdf_fixtures import create_golden_pdf, create_protected_pdf
from uvicorn import Config, Server

from zeny_project_handler_client.ui.pdf_gateway import HttpPdfViewerGateway, ViewerGatewayError
from zeny_project_handler_contracts.base import DocumentId, PageId
from zeny_project_handler_contracts.common import NormalizedBoxDto
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.viewer import ViewerPageDto
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.config import ServerSettings

PASSWORD = "senha servidor viewer HTTP real"


@pytest.mark.integration
def test_http_gateway_streams_upload_unlocks_and_renders_remote_png(tmp_path: Path) -> None:
    regular = create_golden_pdf(tmp_path / "regular.pdf")
    pdf_password = "senha PDF em memoria"
    protected = create_protected_pdf(tmp_path / "protegido.pdf", pdf_password)
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server-data",
        render_dpi=600,
        render_max_pixels=8_000_000,
        render_max_bytes=64 * 1024 * 1024,
        viewer_session_ttl_seconds=60,
    )

    with closing(create_server(("127.0.0.1", 0))) as listener:
        port = int(listener.getsockname()[1])
        server = Server(
            Config(
                create_app(settings),
                log_level="critical",
                lifespan="on",
            )
        )

        def serve() -> None:
            server.run(sockets=[listener])

        thread = Thread(target=serve, name="viewer-http-test", daemon=True)
        thread.start()
        _wait_until_started(server, thread)
        try:
            bad_gateway = HttpPdfViewerGateway(
                f"http://127.0.0.1:{port}",
                "senha incorreta",
            )
            with pytest.raises(ViewerGatewayError) as denied:
                bad_gateway.create_session((regular,), idempotency_key="viewer-http-denied")
            assert denied.value.code is ErrorCode.AUTHENTICATION_FAILED

            gateway = HttpPdfViewerGateway(f"http://127.0.0.1:{port}", PASSWORD)
            created = gateway.create_session(
                (regular, protected),
                idempotency_key="viewer-http-session",
            )
            assert [item.display_name for item in created.documents] == [regular.name]
            assert [item.display_name for item in created.pending_uploads] == [protected.name]

            unlocked = gateway.unlock_session_pdf(
                created.viewer_session_id.root,
                created.pending_uploads[0].upload_id.root,
                pdf_password,
            )
            assert [item.display_name for item in unlocked.documents] == [
                regular.name,
                protected.name,
            ]
            page_id = unlocked.documents[0].pages[0].page_id.root
            assert gateway.get_page(page_id).page_id.root == page_id

            preview = gateway.render_preview(page_id, dpi=72, rotation=90)
            image = Image.open(BytesIO(preview.png))
            assert image.size == (
                preview.metadata.pixel_width,
                preview.metadata.pixel_height,
            )
            assert preview.metadata.rotation_degrees == 90

            tile = gateway.render_tile(
                page_id,
                dpi=144,
                rotation=270,
                clip=NormalizedBoxDto(x="0.1", y="0.2", width="0.3", height="0.4"),
            )
            assert tile.metadata.rotation_degrees == 270
            assert tuple(
                float(value)
                for value in (
                    tile.metadata.clip.x,
                    tile.metadata.clip.y,
                    tile.metadata.clip.width,
                    tile.metadata.clip.height,
                )
            ) == pytest.approx((0.1, 0.2, 0.3, 0.4))
            assert gateway.close_session(created.viewer_session_id.root).closed
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


def _wait_until_started(server: Server, thread: Thread) -> None:
    tick = Event()
    for _attempt in range(500):
        if server.started:
            return
        if not thread.is_alive():
            break
        tick.wait(0.01)
    raise RuntimeError("O servidor HTTP de teste não iniciou dentro do limite")


def test_http_gateway_retries_only_idempotent_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    page_id = uuid4()
    page = ViewerPageDto(
        page_id=PageId(page_id),
        document_id=DocumentId(uuid4()),
        reading_order=0,
        source_page_number=1,
        width_points="200",
        height_points="100",
        intrinsic_rotation_degrees=0,
    )
    attempts: list[str] = []

    def flaky_read(
        _self: HttpPdfViewerGateway,
        method: str,
        _path: str,
        *,
        headers: Mapping[str, str] | None,
        body: bytes | Iterable[bytes] | None,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, body
        attempts.append(method)
        if len(attempts) == 1:
            raise TimeoutError
        return 200, {"content-type": "application/json"}, page.model_dump_json().encode()

    monkeypatch.setattr(HttpPdfViewerGateway, "_request_once", flaky_read)
    gateway = HttpPdfViewerGateway("http://127.0.0.1:1", PASSWORD)
    assert gateway.get_page(page_id) == page
    assert attempts == ["GET", "GET"]

    attempts.clear()

    def unavailable_mutation(
        _self: HttpPdfViewerGateway,
        method: str,
        _path: str,
        *,
        headers: Mapping[str, str] | None,
        body: bytes | Iterable[bytes] | None,
    ) -> tuple[int, dict[str, str], bytes]:
        del headers, body
        attempts.append(method)
        raise OSError("indisponível")

    monkeypatch.setattr(HttpPdfViewerGateway, "_request_once", unavailable_mutation)
    with pytest.raises(ViewerGatewayError) as failure:
        gateway.close_session(uuid4())
    assert failure.value.code is ErrorCode.INTERNAL_ERROR
    assert attempts == ["DELETE"]
