"""E16 symbol/text conflict values survive persistence and review outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import Engine
from tests.integration.test_e13_semantic_pipeline import (
    _reconciled,
    _runner,
    _symbol,
    _symbol_proposals,
)
from tests.server.test_deliverable_exports import _sheet_rows

from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler.domain.analysis import ExecucaoAnalise
from zeny_project_handler.domain.enums import EstadoRevisao, SituacaoProjeto
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler_client.ui.review_panel import _symbol_detail
from zeny_project_handler_server.deliverable_exports import (
    _add_symbol_annotation,
    _results_sheets,
)
from zeny_project_handler_server.review_api import ReviewApiService
from zeny_project_handler_server.xlsx_export import write_xlsx

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.integration.test_e13_semantic_pipeline",)


def test_conflicting_power_and_situation_remain_visible_in_review_and_exports(
    semantic_context: tuple[Engine, Projeto, ExecucaoAnalise], tmp_path: Path
) -> None:
    engine, project, source = semantic_context
    first, first_observation = _symbol(
        project,
        "vector-45",
        "TRANSFORMADOR",
        situation=SituacaoProjeto.INSTALAR,
        attributes=(("potencia_kva", 45), ("situacao_validada", True)),
    )
    second, second_observation = _symbol(
        project,
        "raster-75",
        "TRANSFORMADOR",
        situation=SituacaoProjeto.EXISTENTE,
        attributes=(("potencia_kva", 75), ("situacao_validada", True)),
    )
    symbols = _reconciled((first, second), calibrated_class="TRANSFORMADOR")
    assert len(symbols.occurrences) == 1
    result = _runner(engine).executar(project.id, source.id, simbolos=symbols)
    proposal = _symbol_proposals(result)[0]
    attributes = dict(proposal.atributos_sugeridos)
    assert attributes["situacao_pendente"] is True
    assert attributes["simbolo_situacao_resolvida"] is False
    assert proposal.estado_revisao is EstadoRevisao.CONFLITANTE
    assert set(str(attributes["simbolo_motivo_pendencia"]).split(",")) >= {
        "situation_conflict",
        "attribute_conflict:potencia_kva",
    }
    expected = {first_observation.id: 45, second_observation.id: 75}
    observed_power = json.loads(str(attributes["simbolo_potencias_observadas"]))
    assert {item["observacao_id"]: item["potencia_kva"] for item in observed_power} == expected
    with SqlAlchemyUnitOfWork(engine) as work:
        stored = work.propostas.obter(proposal.id)
        assert stored == proposal
        evidence = [work.evidencias.obter(identity) for identity in proposal.evidencia_ids]
    assert all(item is not None for item in evidence)
    observed_evidence = {
        str(dict(item.atributos_extraidos)["simbolo_observacao_id"]): dict(item.atributos_extraidos)
        for item in evidence
        if item is not None
    }
    assert {
        key: value["simbolo_potencia_kva_observada"] for key, value in observed_evidence.items()
    } == expected
    assert {value["simbolo_situacao_observada"] for value in observed_evidence.values()} == {
        SituacaoProjeto.INSTALAR.value,
        SituacaoProjeto.EXISTENTE.value,
    }

    session = ReviewApiService(engine).get_session(project.id)
    reviewed = next(item for item in session.proposals if item.proposal_id.root == proposal.id)
    assert reviewed.symbol is not None
    assert reviewed.symbol.effective_situation is None
    reasons = reviewed.symbol.pending_reasons
    assert any("45" in reason and "75" in reason for reason in reasons)
    assert any("INSTALAR" in reason and "EXISTENTE" in reason for reason in reasons)
    detail = _symbol_detail(reviewed)
    assert "45" in detail and "75" in detail
    assert "INSTALAR" in detail and "EXISTENTE" in detail

    sheets = _results_sheets(session)
    xlsx = write_xlsx(tmp_path / "conflict.xlsx", sheets)
    rows = tuple(
        row
        for index, sheet in enumerate(sheets, 1)
        if sheet.name == "Símbolos"
        for row in _sheet_rows(xlsx.read_bytes(), index)[1:]
    )
    row = next(row for row in rows if reviewed.symbol.occurrence_id in row)
    text = " | ".join(row)
    assert "45" in text and "75" in text
    assert "INSTALAR" in text and "EXISTENTE" in text

    pdf_path = tmp_path / "conflict.pdf"
    with pymupdf.open() as pdf:  # type: ignore[no-untyped-call]
        page = pdf.new_page(width=1000, height=1000)
        _add_symbol_annotation(page, reviewed)
        pdf.save(str(pdf_path))
    with pymupdf.open(pdf_path) as pdf:  # type: ignore[no-untyped-call]
        annotation = next(pdf[0].annots())
        content = annotation.info["content"]
        assert "45" in content and "75" in content
        assert "INSTALAR" in content and "EXISTENTE" in content
