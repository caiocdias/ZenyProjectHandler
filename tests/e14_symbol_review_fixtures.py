# mypy: disable-error-code="no-untyped-call"
"""Authorial E14 development fixture; never reads the sealed symbol reserve."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pymupdf

from tests.factories import complete_project
from tests.integration.test_e13_semantic_pipeline import _reconciled, _runner, _symbol
from tests.unit.test_symbol_reconciliation import _profile, _result
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
)
from zeny_project_handler.domain.enums import (
    EstadoExecucaoAnalise,
    EstadoMetodoSimbolos,
    TipoEvidencia,
)
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.symbols import AlternativaClasseSimbolo
from zeny_project_handler.domain.values import GeometriaDocumento
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler_server.composition import ServerRuntime, compose_server_runtime
from zeny_project_handler_server.config import ServerSettings

PASSWORD = "senha isolada fixture E14 simbologia"
AUTH = {"Authorization": f"Bearer {PASSWORD}", "X-Zeny-Review-Symbols": "1"}


@dataclass(frozen=True)
class SymbolReviewFixture:
    settings: ServerSettings
    runtime: ServerRuntime
    project: Projeto
    proposals: tuple[PropostaElemento, ...]
    source: Path


def create_symbol_review_pdf(path: Path) -> Path:
    """Draw six review locations; hypotheses are seeded, not detector accuracy claims."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as pdf:
        for page_number in (1, 2):
            page = pdf.new_page(width=1000, height=1000)
            labels = ("Exclusive transformer", "Conflict: transformer / arrester", "Unknown")
            if page_number == 2:
                labels = ("Informative legend", "Guy support", "Unsupported family")
                page.set_rotation(90)
            inverse = page.derotation_matrix
            for index, (x, label) in enumerate(zip((100, 350, 600), labels, strict=True)):
                page.draw_rect(pymupdf.Rect(x, 100, x + 80, 180) * inverse, color=(0.7, 0.7, 0.7))
                page.insert_text(
                    pymupdf.Point(x, 90) * inverse, label, fontsize=10, rotate=page.rotation
                )
                if index == 0:
                    page.draw_circle(pymupdf.Point(x + 32, 137) * inverse, 17)
                    page.draw_circle(pymupdf.Point(x + 48, 150) * inverse, 17)
                elif index == 1:
                    page.draw_polyline(
                        [
                            pymupdf.Point(px, py) * inverse
                            for px, py in ((x + 20, 115), (x + 60, 140), (x + 20, 165))
                        ]
                    )
                else:
                    page.draw_rect(pymupdf.Rect(x + 20, 120, x + 60, 160) * inverse)
                    page.draw_line(
                        pymupdf.Point(x + 20, 120) * inverse, pymupdf.Point(x + 60, 160) * inverse
                    )
        pdf.save(str(path))
    return path


def seed_symbol_review(directory: Path, *, legacy_evidence: bool = False) -> SymbolReviewFixture:
    """Seed E12→E13 outputs on two pages, including a rotated second page."""
    from uuid import uuid4, uuid5

    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=directory,
    )
    runtime = compose_server_runtime(settings)
    project = complete_project(runtime.core.catalog)
    page = project.documentos[0].paginas[0]
    pdf_source = create_symbol_review_pdf(directory / "fixture-symbol-review.pdf")
    inspection = PyMuPdfReader().inspecionar(pdf_source)
    page = replace(inspection.documento.paginas[0], id=page.id)
    second = inspection.documento.paginas[1]
    document = replace(inspection.documento, id=project.documentos[0].id, paginas=(page, second))
    project = replace(project, documentos=(document,), ordem_leitura_paginas=(page.id, second.id))
    source = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=project.id,
        metodo="fixture-e14-source",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 9, 24, 9, tzinfo=UTC),
        finalizada_em=datetime(2026, 9, 24, 9, 1, tzinfo=UTC),
    )
    with SqlAlchemyUnitOfWork(runtime.core.engine) as work:
        work.projetos.salvar(project)
        work.fontes_pdf.salvar(
            ReferenciaFontePdf(
                documento_id=document.id,
                projeto_id=project.id,
                caminho_canonico=inspection.caminho_origem,
                sha256=document.sha256,
                tamanho_bytes=inspection.tamanho_bytes,
                modificado_em_ns=inspection.modificado_em_ns,
            )
        )
        work.execucoes_analise.salvar(source)
        work.commit()
    exclusive, observation = _symbol(project, "exclusive-vector", "TRANSFORMADOR", x="0.10")
    if legacy_evidence:
        observation = replace(observation, chave_legada="preserved-legacy-e14")
        exclusive = replace(exclusive, observacoes=(observation,))
        with SqlAlchemyUnitOfWork(runtime.core.engine) as work:
            work.evidencias.salvar(
                EvidenciaDocumento(
                    id=uuid5(source.id, "preserved-legacy-e14"),
                    execucao_id=source.id,
                    pagina_id=page.id,
                    tipo=TipoEvidencia.VETOR,
                    geometria=GeometriaDocumento.caixa(
                        page.id, *observation.geometria.pontos_normalizados
                    ),
                    metodo="preserved-legacy-method",
                    versao_metodo="legacy",
                    parametros=(),
                    conteudo_bruto=None,
                    criada_em=source.iniciada_em,
                    atributos_extraidos=(("legacy_marker", "preserve-original"),),
                )
            )
            work.commit()
    silent = _result(_profile("silent-raster"), state=EstadoMetodoSimbolos.NAO_DETECCAO)
    silent = replace(silent, coberturas=(replace(silent.coberturas[0], fonte=observation.fonte),))
    failed = _result(_profile("failed-raster"), state=EstadoMetodoSimbolos.FALHA)
    failed = replace(failed, coberturas=(replace(failed.coberturas[0], fonte=observation.fonte),))
    unknown, unknown_observation = _symbol(project, "unknown-vector", "TRANSFORMADOR", x="0.60")
    unknown = replace(
        unknown,
        observacoes=(
            replace(unknown_observation, alternativas=(AlternativaClasseSimbolo(classe=None),)),
        ),
    )
    methods = (
        exclusive,
        silent,
        failed,
        _symbol(project, "conflict-vector", "TRANSFORMADOR", x="0.35")[0],
        _symbol(project, "conflict-raster", "PARA_RAIOS", x="0.35")[0],
        unknown,
        _symbol(
            project,
            "legend-vector",
            "TRANSFORMADOR",
            page=2,
            attributes=(("contexto", "legenda"),),
        )[0],
        _symbol(project, "guy-vector", "ESTAI", page=2, x="0.35")[0],
        _symbol(
            project,
            "unsupported-vector",
            "TR_ID_1",
            page=2,
            x="0.60",
            attributes=(("status", "pending"),),
        )[0],
    )
    result = _runner(runtime.core.engine).executar(
        project.id, source.id, simbolos=_reconciled(methods)
    )
    return SymbolReviewFixture(settings, runtime, project, result.elementos, pdf_source)
