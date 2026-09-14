# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest
from tests.factories import complete_project
from tests.pdf_fixtures import create_e11_revision_pdf
from tests.unit.test_pymupdf_analyzer import FakeOcr, _request

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis.pymupdf_page_extractors import _extract_text
from zeny_project_handler.adapters.analysis.pymupdf_revisions import extract_revision_appearances
from zeny_project_handler.application.document_zones import evidencias_sem_anotacoes_de_revisao
from zeny_project_handler.application.technical_revisions import (
    attach_revision_conflicts,
    effective_revision_project,
    revision_data,
)
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao, SituacaoProjeto
from zeny_project_handler.ports.analysis import PaginaRasterOcr, TrechoTextoOcr


class RevisionOcr(FakeOcr):
    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        self.pages.append(pagina)
        return (TrechoTextoOcr(texto="ABCN-16(16)", caixa_normalizada=(0.1, 0.1, 0.9, 0.9)),)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_occlusion_preserves_both_layers_and_excludes_comment_photo_stamp_and_shx(
    tmp_path: Path,
    rotation: int,
) -> None:
    path = create_e11_revision_pdf(tmp_path / "revision.pdf", rotation=rotation)
    before = sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
    request = _request(path)
    result = PyMuPdfDocumentAnalyzer(motor_ocr=RevisionOcr()).analisar(request)
    revisions = [
        item for item in result.evidencias if "revisao_tecnica" in dict(item.atributos_extraidos)
    ]
    assert len(revisions) == 2  # Cable occlusion and N4 strike, never photo/signature/comments.
    revision = next(item for item in revisions if "ABCN" in str(item.atributos_extraidos))
    data = json.loads(str(dict(revision.atributos_extraidos)["revisao_tecnica"]))
    assert data["base_text"] == "ABCN-35(70)"
    assert data["visible_text"] == "ABCN-16(16)"
    assert data["base_png"] != data["visible_png"]
    assert data["source_sha256"] == before[0]
    semantic = evidencias_sem_anotacoes_de_revisao(result.evidencias)
    assert any(item.conteudo_bruto == "N3" for item in semantic)  # SHX carrier.
    assert not any("Comentário" in (item.conteudo_bruto or "") for item in semantic)
    base = next(item for item in semantic if item.conteudo_bruto == "ABCN-35(70)")
    proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=uuid4(),
        categoria=CategoriaElemento.CABO,
        estado_revisao=EstadoRevisao.PROPOSTA,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        evidencia_ids=(base.id,),
        geometria=base.geometria,
        codigo_observado="ABCN-35(70)",
    )
    marked = attach_revision_conflicts((proposal,), result.evidencias)[0]
    assert marked.estado_revisao is EstadoRevisao.CONFLITANTE
    marked_revision = revision_data(marked)
    assert marked_revision is not None and marked_revision["decision"] is None
    assert before == (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    second = PyMuPdfDocumentAnalyzer(motor_ocr=RevisionOcr()).analisar(
        replace(request, execucao_id=uuid4())
    )
    assert {
        json.loads(str(dict(item.atributos_extraidos)["revisao_tecnica"]))["group_id"]
        for item in revisions
    } == {
        json.loads(str(dict(item.atributos_extraidos)["revisao_tecnica"]))["group_id"]
        for item in second.evidencias
        if "revisao_tecnica" in dict(item.atributos_extraidos)
    }


def test_no_overlay_keeps_base_processable(tmp_path: Path) -> None:
    path = create_e11_revision_pdf(tmp_path / "base.pdf", revised=False)
    with pymupdf.open(path) as document:
        page = document[0]
        candidates = extract_revision_appearances(page, 1, "1" * 64, _extract_text(page, 1), None)
    assert len(candidates) == 1  # Only the N4 strike remains.
    assert (
        json.loads(str(dict(candidates[0].atributos_extraidos)["revisao_tecnica"]))["base_text"]
        == "N4"
    )


@pytest.mark.parametrize("failure", [True, False])
def test_ocr_failure_or_absence_preserves_unresolved_conflict(
    tmp_path: Path, failure: bool
) -> None:
    class FailingOcr(RevisionOcr):
        def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
            raise RuntimeError("synthetic failure")

    path = create_e11_revision_pdf(tmp_path / "failure.pdf")
    with pymupdf.open(path) as document:
        page = document[0]
        candidates = extract_revision_appearances(
            page, 1, "1" * 64, _extract_text(page, 1), FailingOcr() if failure else None
        )
    assert len(candidates) == 2
    for item in candidates:
        data = json.loads(str(dict(item.atributos_extraidos)["revisao_tecnica"]))
        assert data["visible_text"] is None and data["decision"] is None
        assert data["ocr_failed"] == failure


def test_legacy_confirmed_alternative_is_history_not_current_content(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    cable = next(item for item in project.elementos if item.categoria is CategoriaElemento.CABO)
    assert cable.geometria is not None
    proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=uuid4(),
        categoria=cable.categoria,
        estado_revisao=EstadoRevisao.CONFLITANTE,
        situacao_projeto=cable.situacao,
        evidencia_ids=(uuid4(),),
        geometria=cable.geometria,
        codigo_observado=cable.codigo_observado,
        atributos_sugeridos=(
            (
                "revisao_tecnica",
                json.dumps({"base_code": cable.codigo_observado, "decision": None}),
            ),
        ),
    )
    effective = effective_revision_project(project, (proposal,), ())
    assert cable not in effective.elementos
    assert cable in project.elementos
    assert len(effective.elementos) == len(project.elementos) - 1
