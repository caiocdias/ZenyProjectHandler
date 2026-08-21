"""Execute a matriz remota usando somente o wheel empacotado do cliente."""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import sys
from hashlib import sha256
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from zeny_project_handler_client.connection import ConnectionManager
from zeny_project_handler_client.ui.project_gateway import (
    HttpProjectGateway,
    ProjectGatewayError,
)
from zeny_project_handler_contracts.backup import (
    ConfirmBackupRestoreRequest,
    CreateBackupJobRequest,
)
from zeny_project_handler_contracts.common import NormalizedBoxDto, NormalizedPointDto
from zeny_project_handler_contracts.enums import (
    JobStatus,
    ReviewGeometryKind,
    UploadState,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.jobs import JobResultResponse
from zeny_project_handler_contracts.portability import ConfirmProjectImportRequest
from zeny_project_handler_contracts.review import (
    CreateManualElementRequest,
    CreateManualRelationRequest,
    ReviewElementInputDto,
    ReviewGeometryDto,
)
from zeny_project_handler_contracts.rules import ConfirmRuleImportRequest

_TERMINAL_JOBS = {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
_BLOCKED_MODULES = (
    "alembic",
    "fitz",
    "pymupdf",
    "sqlalchemy",
    "zeny_project_handler",
    "zeny_project_handler_api_spec",
    "zeny_project_handler_server",
)


class MatrixError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare", "after-restart"))
    arguments = parser.parse_args()
    plan = json.loads(sys.stdin.read())
    try:
        _assert_packaged_boundary()
        result = _prepare(plan) if arguments.phase == "prepare" else _after_restart(plan)
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


def _prepare(plan: dict[str, object]) -> dict[str, object]:
    base_url = str(plan["base_url"])
    password = str(plan["password"])
    client_root = Path(str(plan["client_root"]))
    primary_pdf = Path(str(plan["primary_pdf"]))
    second_pdf = Path(str(plan["second_pdf"]))
    protected_pdf = Path(str(plan["protected_pdf"]))
    protected_password = str(plan["protected_password"])
    photo = Path(str(plan["photo"]))

    _assert_bad_password(base_url, password)
    first = ConnectionManager()
    second = ConnectionManager()
    first_session = first.connect(base_url, password)
    second_session = second.connect(base_url, password)
    _require(first_session.ready and second_session.ready, "sessões autenticadas não ficaram ready")
    first_gateways = first.gateways
    second_gateways = second.gateways

    created = first_gateways.project.create_project(
        "0011223344",
        idempotency_key="stage11-main-project",
    ).project
    project_id = created.project_id.root
    listed = second_gateways.project.list_projects()
    _require(
        project_id in {item.project_id.root for item in listed.items},
        "o segundo cliente não observou o projeto criado pelo primeiro",
    )
    updated = second_gateways.project.update_project(
        project_id,
        "0099887766",
        expected_project_version=created.project_version,
    ).project
    _require(updated.service_note == "0099887766", "alteração da NS não foi persistida")

    uploads = []
    for index, source in enumerate((primary_pdf, second_pdf), start=1):
        uploaded = first_gateways.project.upload_document(
            project_id,
            source,
            idempotency_key=f"stage11-main-pdf-{index}",
        )
        _require(uploaded.state is UploadState.IMPORTED, f"upload {index} não foi importado")
        uploads.append(uploaded)

    protected = first_gateways.project.upload_document(
        project_id,
        protected_pdf,
        idempotency_key="stage11-protected-pdf",
    )
    _require(
        protected.state is UploadState.PASSWORD_REQUIRED,
        "PDF protegido não solicitou senha",
    )
    try:
        first_gateways.project.unlock_upload(protected.upload_id.root, "incorreta-stage11")
    except ProjectGatewayError as error:
        _require(
            error.code is ErrorCode.PDF_PASSWORD_INVALID, "senha incorreta teve erro inesperado"
        )
    else:
        raise MatrixError("senha incorreta abriu o PDF protegido")
    unlocked = first_gateways.project.unlock_upload(
        protected.upload_id.root,
        protected_password,
    )
    _require(unlocked.state is UploadState.IMPORTED, "senha correta não importou o PDF protegido")

    attempts_project = first_gateways.project.create_project(
        "0033110033",
        idempotency_key="stage11-password-attempts-project",
    ).project
    attempts_upload = first_gateways.project.upload_document(
        attempts_project.project_id.root,
        protected_pdf,
        idempotency_key="stage11-password-attempts-upload",
    )
    _require(
        attempts_upload.state is UploadState.PASSWORD_REQUIRED,
        "PDF do ensaio de três tentativas não solicitou senha",
    )
    for remaining in (2, 1, 0):
        try:
            first_gateways.project.unlock_upload(
                attempts_upload.upload_id.root,
                "incorreta-stage11",
            )
        except ProjectGatewayError as error:
            _require(
                error.code is ErrorCode.PDF_PASSWORD_INVALID,
                "tentativa incorreta teve erro inesperado",
            )
            _require(
                int((error.details or {}).get("password_attempts_remaining", -1)) == remaining,
                "contador de tentativas do PDF protegido divergiu",
            )
        else:
            raise MatrixError("senha incorreta abriu o PDF do ensaio de três tentativas")
    try:
        first_gateways.project.unlock_upload(
            attempts_upload.upload_id.root,
            protected_password,
        )
    except ProjectGatewayError as error:
        _require(
            error.code is ErrorCode.OPERATION_CONFLICT,
            "upload esgotado não foi rejeitado como conflito",
        )
    else:
        raise MatrixError("upload esgotado aceitou a senha correta")
    _require(
        first_gateways.project.delete_project(attempts_project.project_id.root).deleted,
        "projeto temporário do ensaio de tentativas não foi removido",
    )

    project = second_gateways.project.get_project(project_id).project
    _require(len(project.documents) == 3, "seleção múltipla/PDF protegido não gerou 3 documentos")
    original_order = tuple(page.page_id.root for page in project.pages)
    reordered_ids = tuple(reversed(original_order))
    reordered = first_gateways.project.replace_page_order(
        project_id,
        reordered_ids,
        expected_project_version=project.project_version,
    )
    _require(
        tuple(page.page_id.root for page in reordered.pages) == reordered_ids,
        "ordem de páginas não foi persistida",
    )

    standalone = first_gateways.pdf.create_session(
        (primary_pdf, second_pdf),
        idempotency_key="stage11-viewer-session",
    )
    _require(len(standalone.documents) == 2, "viewer avulso não recebeu os dois PDFs")
    standalone_page = standalone.documents[0].pages[0].page_id.root
    preview = first_gateways.pdf.render_preview(standalone_page, dpi=72, rotation=90)
    tile = first_gateways.pdf.render_tile(
        standalone_page,
        dpi=144,
        rotation=270,
        clip=NormalizedBoxDto(x="0.1", y="0.1", width="0.5", height="0.5"),
    )
    _require(
        preview.png.startswith(b"\x89PNG") and tile.png.startswith(b"\x89PNG"),
        "raster remoto inválido",
    )
    _require(
        first_gateways.pdf.close_session(standalone.viewer_session_id.root).closed,
        "sessão avulsa não foi encerrada",
    )

    for source in (primary_pdf, second_pdf, protected_pdf):
        source.unlink()
    project_viewer = second_gateways.pdf.get_project(project_id)
    _require(len(project_viewer.documents) == 3, "viewer do projeto dependeu das cópias locais")
    renderable = next(document for document in project_viewer.documents if document.pages)
    rendered = second_gateways.pdf.render_preview(
        renderable.pages[0].page_id.root,
        dpi=72,
        rotation=0,
    )
    _require(rendered.png.startswith(b"\x89PNG"), "preview gerada pelo servidor é inválida")

    current = first_gateways.project.get_project(project_id).project
    cancelled_job = first_gateways.project.create_analysis_job(
        project_id,
        expected_project_version=current.project_version,
        force_reanalysis=True,
        idempotency_key="stage11-analysis-cancel",
    )
    first_gateways.project.cancel_job(cancelled_job.job_id.root)
    cancelled = _wait_job(first_gateways.project, cancelled_job.job_id.root, timeout=180)
    _require(cancelled.status is JobStatus.CANCELLED, "análise cancelada publicou outro terminal")

    current = second_gateways.project.get_project(project_id).project
    successful_job = second_gateways.project.create_analysis_job(
        project_id,
        expected_project_version=current.project_version,
        force_reanalysis=True,
        idempotency_key="stage11-analysis-success",
    )
    successful = _wait_job(second_gateways.project, successful_job.job_id.root, timeout=300)
    _require(successful.status is JobStatus.SUCCEEDED, "análise real não terminou com sucesso")
    analysis_result = second_gateways.project.get_job_result(successful_job.job_id.root)
    _require(analysis_result.result is not None, "job de análise não publicou resultado")

    review = first_gateways.review.get_session(project_id)
    _require(review.page_order and review.catalog_items, "sessão de revisão veio incompleta")
    geometry = ReviewGeometryDto(
        page_id=review.page_order[0],
        kind=ReviewGeometryKind.POINT,
        points=(NormalizedPointDto(x="0.25", y="0.25"),),
    )
    catalog_item = review.catalog_items[0]
    manual = first_gateways.review.create_manual_element(
        project_id,
        CreateManualElementRequest(
            author="Aceite E2E Etapa 11",
            reason="Paridade da revisão manual pelo cliente empacotado",
            element=ReviewElementInputDto(
                category=catalog_item.category,
                catalog_item_id=catalog_item.catalog_item_id,
                situation="INSTALL",
                geometry=geometry,
                observed_code=catalog_item.code,
            ),
            expected_project_version=review.project_version,
        ),
    )
    _require(manual.element_id is not None, "criação manual não retornou elemento")
    refreshed = second_gateways.review.get_session(project_id)
    source_reference = next(
        (
            item.reference_id
            for item in refreshed.references
            if item.reference_id != manual.element_id.root
        ),
        None,
    )
    if source_reference is None:
        second_manual = second_gateways.review.create_manual_element(
            project_id,
            CreateManualElementRequest(
                author="Aceite E2E Etapa 11",
                reason="Segunda referência para relação manual",
                element=ReviewElementInputDto(
                    category=catalog_item.category,
                    catalog_item_id=catalog_item.catalog_item_id,
                    situation="EXISTING",
                    geometry=geometry,
                    observed_code=catalog_item.code,
                ),
                expected_project_version=refreshed.project_version,
            ),
        )
        _require(second_manual.element_id is not None, "segunda criação manual falhou")
        source_reference = second_manual.element_id.root
        refreshed = first_gateways.review.get_session(project_id)
    relation = first_gateways.review.create_manual_relation(
        project_id,
        CreateManualRelationRequest(
            author="Aceite E2E Etapa 11",
            reason="Relação manual pela fronteira HTTP",
            source_reference_id=source_reference,
            target_reference_id=manual.element_id.root,
            relation_type="ASSOCIADO_A",
            expected_project_version=refreshed.project_version,
        ),
    )
    _require(relation.relation_id is not None, "relação manual não foi persistida")

    documentation = second_gateways.documentation.get_documentation(project_id)
    latest = second_gateways.documentation.get_latest_compliance(project_id)
    _require(documentation.project_id.root == project_id, "documentação remota divergiu do projeto")
    _require(latest is not None and latest.findings, "conformidade remota não publicou achados")
    history = second_gateways.documentation.list_compliance_history(project_id)
    _require(history.page.total >= 1, "histórico de conformidade está vazio")
    compliance_job = second_gateways.documentation.create_compliance_job(
        project_id,
        expected_semantic_signature=documentation.semantic_signature,
        idempotency_key="stage11-compliance-job",
    )
    compliance_status = _wait_job(
        second_gateways.documentation,
        compliance_job.job_id.root,
        timeout=180,
    )
    _require(compliance_status.status is JobStatus.SUCCEEDED, "reanálise de conformidade falhou")
    latest = second_gateways.documentation.get_latest_compliance(project_id)
    _require(
        latest is not None and latest.findings,
        "reanálise concluída não publicou achados de conformidade",
    )

    registry = first_gateways.documentation.get_active_registry()
    _require(registry.active_rule_count == 39, "linha de base não contém 39 regras ativas")
    registry_payload = first_gateways.documentation.download_active_registry()
    downloaded_rules = client_root / "rules-downloaded.json"
    downloaded_rules.write_bytes(registry_payload)
    custom_rules = client_root / "rules-stage11.json"
    custom_rules.write_bytes(_custom_rule_registry(registry_payload))
    preflight = second_gateways.documentation.preflight_rule_import(
        custom_rules,
        idempotency_key="stage11-rules-preflight",
    )
    imported_rules = second_gateways.documentation.confirm_rule_import(
        ConfirmRuleImportRequest(
            preflight_id=preflight.preflight_id,
            fingerprint=preflight.fingerprint,
            expected_active_revision=preflight.current_revision,
            confirmed=True,
        )
    )
    _require(imported_rules.active_rule_count == 40, "round trip de regras não publicou revisão")

    photo_id, photo_hash = _attach_photo(
        base_url,
        password,
        project_id,
        manual.element_id.root,
        photo,
    )
    _require(
        _download_photo(base_url, password, project_id, photo_id) == photo.read_bytes(),
        "download da foto divergiu do upload",
    )

    final_project = first_gateways.project.get_project(project_id).project
    return {
        "phase": "prepare",
        "project_id": str(project_id),
        "service_note": final_project.service_note,
        "page_order": [str(item.page_id.root) for item in final_project.pages],
        "document_hashes": sorted(item.file.sha256 for item in final_project.documents),
        "protected_document_id": str(
            unlocked.document.document_id.root if unlocked.document else ""
        ),
        "manual_element_id": str(manual.element_id.root),
        "manual_relation_id": str(relation.relation_id.root),
        "photo_id": str(photo_id),
        "photo_sha256": photo_hash,
        "rule_revision": imported_rules.revision,
        "rule_count": imported_rules.active_rule_count,
        "finding_count": len(latest.findings),
        "callout_count": sum(item.callout is not None for item in latest.findings),
        "analysis_cancelled": True,
        "analysis_succeeded": True,
        "protected_pdf_three_attempts_exhausted": True,
        "two_clients": True,
        "local_sources_deleted": True,
    }


def _after_restart(plan: dict[str, object]) -> dict[str, object]:
    base_url = str(plan["base_url"])
    password = str(plan["password"])
    state = dict(plan["state"])
    client_root = Path(str(plan["client_root"]))
    protected_password = str(plan["protected_password"])
    project_id = UUID(str(state["project_id"]))
    first = ConnectionManager()
    second = ConnectionManager()
    first.connect(base_url, password)
    second.connect(base_url, password)
    first_gateways = first.gateways
    second_gateways = second.gateways

    project = first_gateways.project.get_project(project_id).project
    _require(project.service_note == state["service_note"], "NS não sobreviveu ao restart")
    _require(
        [str(page.page_id.root) for page in project.pages] == state["page_order"],
        "ordem de páginas não sobreviveu ao restart",
    )
    _require(
        sorted(item.file.sha256 for item in project.documents) == state["document_hashes"],
        "hashes dos documentos não sobreviveram ao restart",
    )
    protected_id = UUID(str(state["protected_document_id"]))
    protected_document = second_gateways.pdf.unlock_project_document(
        protected_id,
        protected_password,
    )
    _require(protected_document.pages, "PDF protegido não reabriu após novo desbloqueio")
    viewer = second_gateways.pdf.get_project(project_id)
    _require(
        protected_id in {item.document_id.root for item in viewer.documents},
        "viewer não publicou o documento protegido após reautenticação",
    )
    raster = second_gateways.pdf.render_preview(
        protected_document.pages[0].page_id.root,
        dpi=72,
        rotation=0,
    )
    _require(raster.png.startswith(b"\x89PNG"), "raster após restart é inválida")

    review = first_gateways.review.get_session(project_id)
    _require(
        UUID(str(state["manual_element_id"]))
        in {item.element_id.root for item in review.confirmed_elements},
        "revisão manual não sobreviveu ao restart",
    )
    _require(
        UUID(str(state["manual_relation_id"]))
        in {item.relation_id.root for item in review.confirmed_relations},
        "relação manual não sobreviveu ao restart",
    )
    registry = second_gateways.documentation.get_active_registry()
    _require(
        registry.revision == state["rule_revision"] and registry.active_rule_count == 40,
        "revisão ativa de regras não sobreviveu ao restart",
    )
    photo = _download_photo(
        base_url,
        password,
        project_id,
        UUID(str(state["photo_id"])),
    )
    _require(sha256(photo).hexdigest() == state["photo_sha256"], "foto não sobreviveu ao restart")

    export_job = first_gateways.portability.create_project_export_job(
        project_id,
        expected_project_version=project.project_version,
        idempotency_key="stage11-project-export",
    )
    export_result = _wait_result(first_gateways.portability, export_job.job_id.root, 240)
    _require(export_result.download is not None, "exportação não publicou download")
    project_package = client_root / "stage11-project.zphproj"
    first_gateways.portability.download_to(
        export_result.download.download_id.root,
        project_package,
        progress=_ignore_progress,
        cancelled=_never_cancelled,
    )
    _require(
        sha256(project_package.read_bytes()).hexdigest() == export_result.download.sha256,
        "hash local do .zphproj divergiu",
    )
    first_gateways.project.delete_project(project_id)
    import_preflight = second_gateways.portability.preflight_project_import(
        project_package,
        idempotency_key="stage11-project-import-preflight",
        progress=_ignore_progress,
        cancelled=_never_cancelled,
    )
    import_job = second_gateways.portability.create_project_import_job(
        ConfirmProjectImportRequest(
            preflight_id=import_preflight.preflight_id,
            package_sha256=import_preflight.package_sha256,
            target_fingerprint=import_preflight.target_fingerprint,
            replace_existing=False,
            confirmed=True,
        ),
        idempotency_key="stage11-project-import",
    )
    _wait_result(second_gateways.portability, import_job.job_id.root, 240)
    imported = first_gateways.project.get_project(project_id).project
    _require(len(imported.documents) == 3, ".zphproj não restaurou os documentos")
    _require(
        _download_photo(base_url, password, project_id, UUID(str(state["photo_id"]))) == photo,
        ".zphproj não preservou foto/associação",
    )

    backup_preflight = first_gateways.portability.preflight_backup()
    backup_job = first_gateways.portability.create_backup_job(
        CreateBackupJobRequest(
            preflight_id=backup_preflight.preflight_id,
            source_fingerprint=backup_preflight.source_fingerprint,
            accept_degraded=False,
            confirmed=True,
        ),
        idempotency_key="stage11-backup-create",
    )
    backup_result = _wait_result(first_gateways.portability, backup_job.job_id.root, 240)
    _require(backup_result.download is not None, "backup não publicou download")
    backup_package = client_root / "stage11-server.zphbackup"
    first_gateways.portability.download_to(
        backup_result.download.download_id.root,
        backup_package,
        progress=_ignore_progress,
        cancelled=_never_cancelled,
    )
    _require(
        sha256(backup_package.read_bytes()).hexdigest() == backup_result.download.sha256,
        "hash local do .zphbackup divergiu",
    )
    first_gateways.project.delete_project(project_id)
    restore_preflight = second_gateways.portability.preflight_backup_restore(
        backup_package,
        idempotency_key="stage11-backup-restore-preflight",
        progress=_ignore_progress,
        cancelled=_never_cancelled,
    )
    restore_job = second_gateways.portability.create_backup_restore_job(
        ConfirmBackupRestoreRequest(
            preflight_id=restore_preflight.preflight_id,
            package_sha256=restore_preflight.package_sha256,
            target_fingerprint=restore_preflight.target_fingerprint,
            accept_degraded=False,
            confirmed=True,
        ),
        idempotency_key="stage11-backup-restore",
    )
    _wait_result(second_gateways.portability, restore_job.job_id.root, 240)
    restored = first_gateways.project.get_project(project_id).project
    _require(len(restored.documents) == 3, ".zphbackup não restaurou o projeto")
    _require(
        second_gateways.documentation.get_active_registry().active_rule_count == 40,
        ".zphbackup não preservou a revisão ativa",
    )

    disposable = first_gateways.project.create_project(
        "0077007700",
        idempotency_key="stage11-delete-project",
    ).project
    _require(
        first_gateways.project.delete_project(disposable.project_id.root).deleted,
        "exclusão de projeto não foi confirmada",
    )
    removable_document = restored.documents[-1]
    removed = first_gateways.project.remove_document(
        project_id, removable_document.document_id.root
    )
    _require(removed.removed, "remoção de documento não foi confirmada")

    return {
        "phase": "after-restart",
        "project_id": str(project_id),
        "project_package": str(project_package),
        "project_package_sha256": sha256(project_package.read_bytes()).hexdigest(),
        "backup_package": str(backup_package),
        "backup_package_sha256": sha256(backup_package.read_bytes()).hexdigest(),
        "restart_persistence": True,
        "project_round_trip": True,
        "backup_round_trip": True,
        "photo_round_trip": True,
        "rules_round_trip": True,
        "protected_pdf_reauthenticated": True,
        "document_removed": True,
        "project_deleted": True,
    }


def _assert_packaged_boundary() -> None:
    violations = [name for name in _BLOCKED_MODULES if importlib.util.find_spec(name) is not None]
    if violations:
        raise MatrixError(f"runtime do cliente consegue importar módulos protegidos: {violations}")
    client_spec = importlib.util.find_spec("zeny_project_handler_client")
    contracts_spec = importlib.util.find_spec("zeny_project_handler_contracts")
    origins = (
        str(client_spec.origin if client_spec else ""),
        str(contracts_spec.origin if contracts_spec else ""),
    )
    if not all(".whl" in origin.casefold() for origin in origins):
        raise MatrixError(f"cliente/contratos não foram carregados do wheel: {origins}")


def _assert_bad_password(base_url: str, password: str) -> None:
    wrong = sha256(f"credencial-invalida:{password}".encode()).hexdigest()
    try:
        HttpProjectGateway(base_url, wrong).session()
    except ProjectGatewayError as error:
        _require(
            error.status_code == 401 and error.code is ErrorCode.AUTHENTICATION_FAILED,
            "senha incorreta não recebeu envelope 401 uniforme",
        )
    else:
        raise MatrixError("senha incorreta foi aceita")


def _wait_job(gateway: object, job_id: UUID, timeout: int) -> object:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        status = gateway.get_job(job_id)
        if status.status in _TERMINAL_JOBS:
            return status
        sleep(max(status.poll_after_ms / 1000, 0.25) if hasattr(status, "poll_after_ms") else 0.25)
    raise MatrixError(f"job {job_id} não terminou em {timeout}s")


def _wait_result(gateway: object, job_id: UUID, timeout: int) -> JobResultResponse:
    status = _wait_job(gateway, job_id, timeout)
    _require(status.status is JobStatus.SUCCEEDED, f"job {job_id} terminou em {status.status}")
    return gateway.get_job_result(job_id)


def _custom_rule_registry(payload: bytes) -> bytes:
    decoded = json.loads(payload)
    registry = decoded["registry"]
    rules = decoded["rules"]
    registry["id"] = str(uuid4())
    registry["version"] = "stage11-artifact-e2e"
    added = dict(rules[0])
    added["id"] = "fixture.stage11.artifact-e2e"
    added["title"] = "Regra do aceite isolado da Etapa 11"
    rules[:] = [added]
    return json.dumps(decoded, ensure_ascii=False).encode("utf-8")


def _attach_photo(
    base_url: str,
    password: str,
    project_id: UUID,
    element_id: UUID,
    path: Path,
) -> tuple[UUID, str]:
    content = path.read_bytes()
    boundary = f"----zeny-stage11-photo-{uuid4().hex}"
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    status, _headers, response = _http_request(
        base_url,
        password,
        "POST",
        f"/api/v1/projects/{project_id}/elements/{element_id}/photos",
        body=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
            "Idempotency-Key": "stage11-photo",
        },
    )
    _require(status == 201, f"upload de foto retornou HTTP {status}")
    photo = json.loads(response)["photo"]
    _require(photo["file"]["sha256"] == sha256(content).hexdigest(), "hash da foto divergiu")
    return UUID(photo["photo_id"]), str(photo["file"]["sha256"])


def _download_photo(base_url: str, password: str, project_id: UUID, photo_id: UUID) -> bytes:
    status, _headers, payload = _http_request(
        base_url,
        password,
        "GET",
        f"/api/v1/projects/{project_id}/photos/{photo_id}/content",
    )
    _require(status == 200, f"download de foto retornou HTTP {status}")
    return payload


def _http_request(
    base_url: str,
    password: str,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    parsed = urlsplit(base_url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=60)
    request_headers = {"Authorization": f"Bearer {password}", **(headers or {})}
    try:
        connection.request(
            method, f"{parsed.path.rstrip('/')}{path}", body=body, headers=request_headers
        )
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def _ignore_progress(_current: int, _total: int, _message: str) -> None:
    pass


def _never_cancelled() -> bool:
    return False


def _require(condition: object, message: str) -> None:
    if not condition:
        raise MatrixError(message)


if __name__ == "__main__":
    raise SystemExit(main())
