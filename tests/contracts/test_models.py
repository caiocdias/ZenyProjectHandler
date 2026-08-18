"""Serialização, validação e estabilidade dos DTOs v1."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from zeny_project_handler_contracts.backup import BackupPreflightResponse
from zeny_project_handler_contracts.base import (
    BackupPreflightId,
    CalloutId,
    ComplianceExecutionId,
    ContractModel,
    CorrelationId,
    DocumentId,
    ElementId,
    EvidenceId,
    FindingId,
    JobId,
    PageId,
    PhotoId,
    ProjectId,
    ProjectImportPreflightId,
    ProposalId,
    RegionId,
    ReviewSessionId,
    UploadId,
)
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    FileMetadataDto,
    NormalizedBoxDto,
    NormalizedPointDto,
    PageMetadataDto,
)
from zeny_project_handler_contracts.compliance import (
    ComplianceCalloutDto,
    ComplianceExecutionResponse,
    ComplianceExecutionSummaryDto,
    ComplianceFindingDto,
)
from zeny_project_handler_contracts.documentation import (
    DocumentationResponse,
    DocumentationSectionDto,
    DocumentFieldDto,
)
from zeny_project_handler_contracts.documents import (
    CreateUploadResponse,
    DocumentUploadPreflightDto,
)
from zeny_project_handler_contracts.enums import (
    AnalysisExecutionState,
    ComplianceStatus,
    ComplianceTargetScope,
    DocumentationFieldStatus,
    ElementCategory,
    ElementSituation,
    IntegrityState,
    IssueSeverity,
    JobKind,
    JobStatus,
    OcrStatus,
    PreflightDisposition,
    ProjectState,
    ReviewDecision,
    ReviewState,
    SpanLengthSource,
    UploadState,
)
from zeny_project_handler_contracts.errors import ErrorCode, ErrorEnvelope
from zeny_project_handler_contracts.jobs import JobAcceptedResponse
from zeny_project_handler_contracts.photos import ManagedPhotoDto, ManagedPhotoResponse
from zeny_project_handler_contracts.portability import (
    ProjectImportPreflightResponse,
    ProjectImportSummaryDto,
)
from zeny_project_handler_contracts.projects import ProjectAnalysisSummaryDto, ProjectSummaryDto
from zeny_project_handler_contracts.review import (
    AnalysisRegionDto,
    ReviewProposalDto,
    ReviewSessionResponse,
)
from zeny_project_handler_contracts.session import OcrDiagnosticDto, SessionCapabilitiesResponse

UUIDS = tuple(UUID(int=index) for index in range(1, 25))
NOW = datetime(2026, 8, 17, 21, 35, tzinfo=UTC)
SHA256 = "a" * 64
BOX = NormalizedBoxDto(x="0.1", y="0.2", width="0.3", height="0.4")
FILE = FileMetadataDto(
    display_name="documento.pdf",
    mime_type="application/pdf",
    size_bytes=1024,
    sha256=SHA256,
)
EVIDENCE = EvidenceNavigationDto(
    evidence_id=EvidenceId(UUIDS[0]),
    document_id=DocumentId(UUIDS[1]),
    page_id=PageId(UUIDS[2]),
    geometry=BOX,
    label="origem",
)


def _representative_models() -> list[ContractModel]:
    error = ErrorEnvelope(
        code=ErrorCode.STALE_STATE,
        message="estado alterado",
        correlation_id=CorrelationId(UUIDS[3]),
        details={"expected": 4, "actual": 5},
    )
    session = SessionCapabilitiesResponse(
        server_version="0.1.0",
        api_version="1.0.0",
        min_compatible_api_version="1.0.0",
        max_compatible_api_version="1.999.999",
        ready=True,
        capabilities=("projects", "viewer"),
        ocr=OcrDiagnosticDto(status=OcrStatus.AVAILABLE, message="OCR disponível"),
        server_time=NOW,
    )
    project = ProjectSummaryDto(
        project_id=ProjectId(UUIDS[4]),
        service_note="1234567890",
        state=ProjectState.READY,
        document_count=1,
        page_count=2,
        analysis=ProjectAnalysisSummaryDto(
            last_extraction=AnalysisExecutionState.SUCCEEDED,
            last_interpretation=AnalysisExecutionState.SUCCEEDED,
            pending_proposals=1,
            completed_decisions=2,
        ),
        created_at=NOW,
        updated_at=NOW,
    )
    upload = CreateUploadResponse(
        upload_id=UploadId(UUIDS[5]),
        state=UploadState.PREFLIGHT_READY,
        display_name="documento.pdf",
        size_received=1024,
        sha256=SHA256,
        preflight=DocumentUploadPreflightDto(
            disposition=PreflightDisposition.READY,
            password_required=False,
            duplicate_content=False,
            detected_page_count=2,
        ),
    )
    job = JobAcceptedResponse(
        job_id=JobId(UUIDS[6]),
        kind=JobKind.ANALYSIS,
        status=JobStatus.QUEUED,
        poll_after_ms=350,
    )
    proposal = ReviewProposalDto(
        proposal_id=ProposalId(UUIDS[7]),
        category=ElementCategory.POLE,
        situation=ElementSituation.INSTALL,
        review_state=ReviewState.PENDING,
        label="Poste 1",
        confidence="0.92",
        attributes={"catalog_code": "P-1"},
        evidence=(EVIDENCE,),
    )
    review = ReviewSessionResponse(
        review_session_id=ReviewSessionId(UUIDS[8]),
        project_id=ProjectId(UUIDS[4]),
        project_version=7,
        semantic_signature="semantic-v1",
        regions=(
            AnalysisRegionDto(
                region_id=RegionId(UUIDS[9]),
                label="Região 1",
                geometry=BOX,
                proposal_ids=(proposal.proposal_id,),
                relation_ids=(),
            ),
        ),
        proposals=(proposal,),
        relations=(),
        spans=(),
    )
    documentation = DocumentationResponse(
        project_id=ProjectId(UUIDS[4]),
        semantic_signature="semantic-v1",
        sections=(
            DocumentationSectionDto(
                section_key="header",
                label="Cabeçalho",
                fields=(
                    DocumentFieldDto(
                        field_key="service_note",
                        label="NS",
                        value="1234567890",
                        status=DocumentationFieldStatus.PRESENT,
                        evidence=(EVIDENCE,),
                    ),
                ),
            ),
        ),
    )
    callout = ComplianceCalloutDto(
        callout_id=CalloutId(UUIDS[10]),
        finding_id=FindingId(UUIDS[11]),
        text="Ajustar afastamento",
        anchor=NormalizedPointDto(x="0.2", y="0.3"),
        box=BOX,
        navigation=EVIDENCE,
    )
    compliance = ComplianceExecutionResponse(
        execution=ComplianceExecutionSummaryDto(
            execution_id=ComplianceExecutionId(UUIDS[12]),
            project_id=ProjectId(UUIDS[4]),
            rule_registry_revision="2025.6",
            semantic_signature="semantic-v1",
            method_version="6",
            is_stale=False,
            compliant_count=38,
            divergence_count=1,
            not_evaluable_count=0,
            completed_at=NOW,
        ),
        findings=(
            ComplianceFindingDto(
                finding_id=FindingId(UUIDS[11]),
                rule_id="RULE-1",
                rule_number=1,
                status=ComplianceStatus.DIVERGENCE,
                target_scope=ComplianceTargetScope.ELEMENT,
                target_id=str(UUIDS[13]),
                summary="Afastamento insuficiente",
                source_reference="ND-1",
                evidence=(EVIDENCE,),
                callout=callout,
            ),
        ),
    )
    project_import = ProjectImportPreflightResponse(
        preflight_id=ProjectImportPreflightId(UUIDS[14]),
        package_sha256=SHA256,
        target_fingerprint="b" * 64,
        disposition=PreflightDisposition.CONFIRMATION_REQUIRED,
        integrity_state=IntegrityState.INTACT,
        summary=ProjectImportSummaryDto(
            project_id=ProjectId(UUIDS[15]),
            service_note="9876543210",
            document_count=2,
            page_count=3,
            photo_count=1,
            replaces_existing=True,
        ),
        issues=(),
        expires_at=NOW,
    )
    backup = BackupPreflightResponse(
        preflight_id=BackupPreflightId(UUIDS[16]),
        source_fingerprint="c" * 64,
        disposition=PreflightDisposition.READY,
        integrity_state=IntegrityState.INTACT,
        project_count=1,
        document_count=2,
        issues=(),
        expires_at=NOW,
    )
    photo = ManagedPhotoResponse(
        photo=ManagedPhotoDto(
            photo_id=PhotoId(UUIDS[17]),
            project_id=ProjectId(UUIDS[4]),
            element_id=ElementId(UUIDS[18]),
            file=FILE,
            attached_at=NOW,
        )
    )
    return [
        error,
        session,
        project,
        upload,
        job,
        review,
        documentation,
        compliance,
        project_import,
        backup,
        photo,
    ]


@pytest.mark.parametrize("model", _representative_models(), ids=lambda value: type(value).__name__)
def test_representative_dtos_round_trip_json(model: ContractModel) -> None:
    rebuilt = type(model).model_validate_json(model.model_dump_json())
    assert rebuilt == model


def test_unknown_fields_naive_dates_wrong_ids_and_decimal_numbers_are_rejected() -> None:
    valid_project = {
        "project_id": str(UUIDS[4]),
        "service_note": "1234567890",
        "state": "READY",
        "document_count": 1,
        "page_count": 2,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    with pytest.raises(ValidationError):
        ProjectSummaryDto.model_validate({**valid_project, "server_path": "C:/secret.pdf"})
    with pytest.raises(ValidationError):
        ProjectSummaryDto.model_validate({**valid_project, "created_at": "2026-08-17T21:35:00"})
    with pytest.raises(ValidationError):
        ProjectSummaryDto.model_validate({**valid_project, "state": "UNKNOWN"})
    with pytest.raises(ValidationError):
        ProjectSummaryDto.model_validate({**valid_project, "project_id": DocumentId(UUIDS[1])})
    with pytest.raises(ValidationError):
        NormalizedBoxDto.model_validate({"x": 0.1, "y": "0", "width": "1", "height": "1"})


def test_password_is_serialized_for_transport_but_hidden_from_repr() -> None:
    from zeny_project_handler_contracts.documents import UnlockPdfRequest

    request = UnlockPdfRequest(password="não-registrar")
    assert request.model_dump_json() == '{"password":"não-registrar"}'
    assert "não-registrar" not in repr(request)


def test_enum_values_are_stable() -> None:
    expected = {
        ErrorCode: [
            "AUTHENTICATION_FAILED",
            "AUTHORIZATION_FAILED",
            "VALIDATION_ERROR",
            "RESOURCE_NOT_FOUND",
            "PDF_PASSWORD_REQUIRED",
            "PDF_PASSWORD_INVALID",
            "PDF_SOURCE_CHANGED",
            "VIEWER_SESSION_EXPIRED",
            "OPERATION_CONFLICT",
            "STALE_STATE",
            "UPLOAD_TOO_LARGE",
            "UNSUPPORTED_MEDIA_TYPE",
            "INTEGRITY_ERROR",
            "IDEMPOTENCY_CONFLICT",
            "RATE_LIMITED",
            "INTERNAL_ERROR",
        ],
        ProjectState: ["CREATED", "READY", "ANALYZING", "ERROR"],
        AnalysisExecutionState: ["STARTED", "SUCCEEDED", "FAILED", "CANCELLED"],
        UploadState: [
            "RECEIVING",
            "PREFLIGHT_READY",
            "PASSWORD_REQUIRED",
            "IMPORTED",
            "REJECTED",
            "EXPIRED",
        ],
        JobKind: [
            "ANALYSIS",
            "COMPLIANCE",
            "PROJECT_EXPORT",
            "PROJECT_IMPORT",
            "BACKUP_CREATE",
            "BACKUP_RESTORE",
        ],
        JobStatus: [
            "QUEUED",
            "RUNNING",
            "WAITING_CONFIRMATION",
            "CANCELLING",
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
        ],
        IssueSeverity: ["INFO", "WARNING", "ERROR"],
        IntegrityState: ["INTACT", "DEGRADED", "INVALID"],
        OcrStatus: ["AVAILABLE", "UNAVAILABLE", "DEGRADED"],
        ElementCategory: ["POLE", "MV_STRUCTURE", "LV_STRUCTURE", "CABLE", "EQUIPMENT"],
        ElementSituation: ["EXISTING", "INSTALL", "REMOVE"],
        ReviewState: ["PENDING", "ACCEPTED", "ADJUSTED", "REJECTED"],
        ReviewDecision: ["ACCEPT", "ADJUST", "REJECT", "CREATE_MANUAL"],
        SpanLengthSource: ["DRAWING_LABEL", "COORDINATE_DISTANCE", "UNAVAILABLE"],
        DocumentationFieldStatus: ["PRESENT", "ABSENT", "UNCERTAIN"],
        ComplianceStatus: ["COMPLIANT", "DIVERGENCE", "NOT_EVALUABLE"],
        ComplianceTargetScope: ["PROJECT", "DOCUMENT", "PAGE", "REGION", "ELEMENT"],
        PreflightDisposition: ["READY", "CONFIRMATION_REQUIRED", "REJECTED"],
    }
    assert {enum_type: [member.value for member in enum_type] for enum_type in expected} == expected


def test_page_metadata_enforces_bounded_pagination() -> None:
    assert PageMetadataDto(limit=200, offset=0, total=0).limit == 200
    with pytest.raises(ValidationError):
        PageMetadataDto(limit=201, offset=0, total=0)


def test_file_names_are_display_names_not_paths() -> None:
    with pytest.raises(ValidationError):
        FileMetadataDto(
            display_name="C:\\cliente\\documento.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            sha256=SHA256,
        )
