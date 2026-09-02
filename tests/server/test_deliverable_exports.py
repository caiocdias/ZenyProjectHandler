# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from time import monotonic, sleep
from typing import cast
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZipFile

import pymupdf
from fastapi.testclient import TestClient

from tests.market_fakes import FakeClassificadorMercado
from tests.pdf_fixtures import create_analysis_pdf
from zeny_project_handler_contracts.base import (
    CalloutId,
    DocumentId,
    ElementId,
    FindingId,
    PageId,
    ProjectId,
    ReviewSessionId,
)
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    NormalizedBoxDto,
    NormalizedPointDto,
)
from zeny_project_handler_contracts.compliance import ComplianceCalloutDto
from zeny_project_handler_contracts.enums import (
    ComplianceStatus,
    ElementSituation,
    SpanLengthSource,
    SpanType,
)
from zeny_project_handler_contracts.review import DetectedSpanDto, ReviewSessionResponse
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import compose_server_runtime
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.deliverable_exports import (
    _add_callout_annotation,
    _results_sheets,
)

PASSWORD = "senha segura para exportar arquivos finais"
AUTH = {"Authorization": f"Bearer {PASSWORD}"}
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _project_with_pdf(client: TestClient, source: Path) -> tuple[str, int]:
    created = client.post(
        "/api/v1/projects",
        headers={**AUTH, "Idempotency-Key": "deliverable-project"},
        json={"service_note": "0001234567"},
    )
    assert created.status_code == 201, created.text
    project_id = str(created.json()["project"]["project_id"])
    uploaded = client.post(
        f"/api/v1/projects/{project_id}/document-uploads",
        headers={**AUTH, "Idempotency-Key": "deliverable-pdf"},
        files={"file": (source.name, source.read_bytes(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    current = client.get(f"/api/v1/projects/{project_id}", headers=AUTH)
    assert current.status_code == 200
    return project_id, int(current.json()["project"]["project_version"])


def _create_export(
    client: TestClient,
    project_id: str,
    version: int,
    kind: str,
) -> tuple[dict[str, object], bytes]:
    created = client.post(
        f"/api/v1/projects/{project_id}/deliverable-exports",
        headers=AUTH,
        json={"kind": kind, "expected_project_version": version},
    )
    assert created.status_code == 201, created.text
    metadata = cast(dict[str, object], created.json())
    downloaded = client.get(f"/api/v1/downloads/{metadata['download_id']}", headers=AUTH)
    assert downloaded.status_code == 200, downloaded.text
    assert len(downloaded.content) == metadata["size_bytes"]
    return metadata, downloaded.content


def _wait_job(client: TestClient, job_id: str) -> None:
    deadline = monotonic() + 20
    while monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH)
        assert response.status_code == 200, response.text
        status = response.json()["status"]
        if status == "SUCCEEDED":
            return
        if status in {"FAILED", "CANCELLED"}:
            raise AssertionError(response.text)
        sleep(0.02)
    raise AssertionError("A análise não terminou no prazo")


def _sheet_names(content: bytes) -> tuple[str, ...]:
    with ZipFile(BytesIO(content)) as archive:
        assert archive.testzip() is None
        root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    return tuple(
        str(item.attrib["name"])
        for item in root.findall(f"{{{_SPREADSHEET_NS}}}sheets/{{{_SPREADSHEET_NS}}}sheet")
    )


def _sheet_rows(content: bytes, sheet_index: int) -> tuple[tuple[str, ...], ...]:
    with ZipFile(BytesIO(content)) as archive:
        root = ElementTree.fromstring(archive.read(f"xl/worksheets/sheet{sheet_index}.xml"))
    return tuple(
        tuple(
            (cell.findtext(f"{{{_SPREADSHEET_NS}}}is/{{{_SPREADSHEET_NS}}}t") or "")
            for cell in row.findall(f"{{{_SPREADSHEET_NS}}}c")
        )
        for row in root.findall(f"{{{_SPREADSHEET_NS}}}sheetData/{{{_SPREADSHEET_NS}}}row")
    )


def test_results_span_sheet_presents_the_public_review_contract() -> None:
    span_id = uuid4()
    span = DetectedSpanDto(
        span_id=span_id,
        start_point_id=uuid4(),
        end_point_id=uuid4(),
        cable_element_id=ElementId(uuid4()),
        label="V1-2",
        span_type=SpanType.CONNECTION_BRANCH,
        span_type_label="Ramal de conexão",
        situation=ElementSituation.CHANGE,
        situation_label="A alterar",
        start_label="Poste P1",
        end_label="Padrão do cliente",
        cable_label="B-4 CAA — Cabo multiplexado",
        length="27.5",
        length_label="27,50 m",
        length_source=SpanLengthSource.DRAWING_LABEL,
        length_source_label="Anotação do desenho",
        page_label="Folha 1",
        evidence=(),
    )
    session = ReviewSessionResponse(
        review_session_id=ReviewSessionId(uuid4()),
        project_id=ProjectId(uuid4()),
        service_note="0001234567",
        project_version=1,
        semantic_signature="semantic-e08",
        page_order=(),
        catalog_items=(),
        references=(),
        confirmed_elements=(),
        confirmed_relations=(),
        regions=(),
        proposals=(),
        relations=(),
        spans=(span,),
        audit=(),
    )

    span_sheet = _results_sheets(session)[1]

    assert span_sheet.headers == (
        "Vão",
        "Tipo",
        "Situação",
        "Ponto de origem",
        "Ponto de destino",
        "Cabo",
        "Comprimento",
        "Fonte",
        "Folha",
        "ID do vão",
    )
    assert span_sheet.rows == (
        (
            "V1-2",
            "Ramal de conexão",
            "A alterar",
            "Poste P1",
            "Padrão do cliente",
            "B-4 CAA — Cabo multiplexado",
            "27,50 m",
            "Anotação do desenho",
            "Folha 1",
            str(span_id),
        ),
    )


def test_server_generates_pdf_and_three_real_xlsx_deliverables(tmp_path: Path) -> None:
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server",
    )
    source = create_analysis_pdf(tmp_path / "projeto.pdf")
    runtime = compose_server_runtime(
        settings,
        market_classifier=FakeClassificadorMercado(),
    )
    with TestClient(create_app(settings, runtime_factory=lambda _settings: runtime)) as client:
        project_id, version = _project_with_pdf(client, source)

        pdf_metadata, pdf_content = _create_export(
            client,
            project_id,
            version,
            "ANNOTATED_PDF",
        )
        assert pdf_metadata["file_name"] == "0001234567-pdf-anotado.pdf"
        document = pymupdf.open(stream=pdf_content, filetype="pdf")
        try:
            assert document.page_count == 2
            document_metadata = document.metadata
            assert document_metadata is not None
            assert document_metadata["title"] == "Projeto 0001234567 com anotações"
        finally:
            document.close()

        compliance_metadata, compliance_content = _create_export(
            client,
            project_id,
            version,
            "COMPLIANCE_XLSX",
        )
        assert str(compliance_metadata["mime_type"]).endswith("spreadsheetml.sheet")
        assert _sheet_names(compliance_content) == ("Conformidade", "Regras")

        analysis = client.post(
            f"/api/v1/projects/{project_id}/analysis-jobs",
            headers={**AUTH, "Idempotency-Key": "deliverable-analysis"},
            json={"expected_project_version": version, "force_reanalysis": False},
        )
        assert analysis.status_code == 202, analysis.text
        _wait_job(client, str(analysis.json()["job_id"]))
        current = client.get(f"/api/v1/projects/{project_id}", headers=AUTH)
        analyzed_version = int(current.json()["project"]["project_version"])

        _results_metadata, results_content = _create_export(
            client,
            project_id,
            analyzed_version,
            "RESULTS_XLSX",
        )
        assert _sheet_names(results_content) == ("Elementos", "Vãos")
        span_rows = _sheet_rows(results_content, 2)
        assert span_rows[0] == (
            "Vão",
            "Tipo",
            "Situação",
            "Ponto de origem",
            "Ponto de destino",
            "Cabo",
            "Comprimento",
            "Fonte",
            "Folha",
            "ID do vão",
        )
        _documentation_metadata, documentation_content = _create_export(
            client,
            project_id,
            analyzed_version,
            "DOCUMENTATION_XLSX",
        )
        assert _sheet_names(documentation_content) == ("Documentação",)

        stale = client.post(
            f"/api/v1/projects/{project_id}/deliverable-exports",
            headers=AUTH,
            json={"kind": "RESULTS_XLSX", "expected_project_version": version},
        )
        assert stale.status_code == 409
        assert stale.json()["code"] == "STALE_STATE"


def test_pdf_callout_is_a_downloadable_annotation_even_on_rotated_page(tmp_path: Path) -> None:
    output = tmp_path / "annotated.pdf"
    document = pymupdf.open()
    try:
        page = document.new_page(width=240, height=160)
        page.set_rotation(90)
        finding_id = uuid4()
        page_id = uuid4()
        document_id = uuid4()
        box = NormalizedBoxDto(x="0.55", y="0.1", width="0.35", height="0.25")
        callout = ComplianceCalloutDto(
            callout_id=CalloutId(finding_id),
            finding_id=FindingId(finding_id),
            text="R1 · Divergência de teste",
            anchor=NormalizedPointDto(x="0.2", y="0.7"),
            box=box,
            status=ComplianceStatus.DIVERGENCE,
            navigation=EvidenceNavigationDto(
                document_id=DocumentId(document_id),
                page_id=PageId(page_id),
                geometry=box,
                label="Divergência de teste",
            ),
        )
        _add_callout_annotation(page, callout, box)
        document.save(output)
    finally:
        document.close()

    reopened = pymupdf.open(output)
    try:
        reopened_page = reopened[0]
        annotations = tuple(reopened_page.annots() or ())
        assert len(annotations) == 1
        assert annotations[0].info["content"] == "R1 · Divergência de teste"
        assert annotations[0].rect.is_empty is False
    finally:
        reopened.close()
