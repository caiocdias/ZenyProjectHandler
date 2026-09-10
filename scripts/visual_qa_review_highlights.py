"""Capture a matriz E06 com o visualizador Qt real e um PDF sintético local.

Execute ``python -m scripts.visual_qa_review_highlights`` na raiz do repositório.
As capturas não substituem a inspeção humana nem modificam PDFs de entrada.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import fitz
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication
from tests.viewer_gateway import LocalTestPdfViewerGateway

from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf
from zeny_project_handler_client.ui.pdf_viewer import PdfViewerWidget
from zeny_project_handler_client.ui.theme import Tema, aplicar_tema
from zeny_project_handler_client.ui.visibility import REVIEW_HIGHLIGHT_OPACITY
from zeny_project_handler_contracts.base import CalloutId, FindingId, PageId, ProposalId
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    NormalizedBoxDto,
    NormalizedPointDto,
)
from zeny_project_handler_contracts.compliance import ComplianceCalloutDto
from zeny_project_handler_contracts.enums import (
    ElementCategory,
    ElementSituation,
    ReviewGeometryKind,
    ReviewState,
)
from zeny_project_handler_contracts.review import ReviewGeometryDto, ReviewOverlayDto

PAGE_SIZE = 600


def _point(x: float, y: float) -> NormalizedPointDto:
    return NormalizedPointDto(x=str(x / PAGE_SIZE), y=str(y / PAGE_SIZE))


def _samples(page_id: PageId) -> tuple[ReviewOverlayDto, ...]:
    definitions = (
        ("Instalar", "INSTALL", "BOX", ((180, 205), (285, 224)), "ACCEPTED"),
        ("Existente", "EXISTING", "BOX", ((315, 205), (420, 224)), "PENDING"),
        (
            "Remover",
            "REMOVE",
            "POLYGON",
            ((180, 240), (282, 254), (280, 272), (178, 258)),
            "CONFLICTING",
        ),
        (
            "Alterar",
            "CHANGE",
            "POLYGON",
            ((315, 242), (417, 230), (419, 248), (317, 260)),
            "ADJUSTED",
        ),
        ("Traçado", "INSTALL", "POLYLINE", ((180, 290), (235, 307), (278, 290)), "PENDING"),
        ("Ponto", "CHANGE", "POINT", ((322, 293),), "PENDING"),
        ("Mesma A", "INSTALL", "BOX", ((180, 334), (241, 355)), "PENDING"),
        ("Mesma B", "INSTALL", "BOX", ((215, 334), (277, 355)), "PENDING"),
        ("Diferente A", "REMOVE", "BOX", ((315, 358), (379, 379)), "PENDING"),
        ("Diferente B", "CHANGE", "BOX", ((352, 358), (420, 379)), "PENDING"),
        ("Rejeitada", "REMOVE", "BOX", ((180, 381), (279, 400)), "REJECTED"),
    )
    result = []
    for label, situation, kind, points, state in definitions:
        geometry = ReviewGeometryDto(
            page_id=page_id,
            kind=ReviewGeometryKind(kind),
            points=tuple(_point(x, y) for x, y in points),
        )
        result.append(
            ReviewOverlayDto(
                proposal_id=ProposalId(uuid5(NAMESPACE_URL, f"e06:{label}")),
                geometry=geometry,
                link_geometry=geometry,
                label=label,
                category=ElementCategory.CABLE,
                situation=ElementSituation(situation),
                situation_label=label,
                review_state=ReviewState(state),
            )
        )
    return tuple(result)


def _source(path: Path) -> None:
    with fitz.open() as document:
        page = document.new_page(width=PAGE_SIZE, height=PAGE_SIZE)
        page.insert_text((180, 178), "E06 - leitura localizada / 25%", fontsize=12)
        for x, y, text in (
            (183, 218, "INSTALAR 11-300"),
            (318, 218, "EXISTENTE 2-CAA"),
            (182, 254, "REMOVER 3-CAA"),
            (319, 250, "ALTERAR 4-CAA"),
            (180, 327, "Mesma cor: sem acumulo"),
            (315, 353, "Cores diferentes"),
            (183, 394, "REJEITADA: sem cor"),
            (333, 296, "Ponto"),
        ):
            page.insert_text((x, y), text, fontsize=8)
        page.draw_polyline([(180, 290), (235, 307), (278, 290)], color=(0, 0, 0), width=1)
        page.draw_circle((322, 293), 2.5, color=(0, 0, 0), width=0.6)
        for y in (338, 345, 351):
            page.draw_line((183, y), (273, y), width=0.4, color=(0, 0, 0))
        page.insert_text((317, 371), "Texto sob sobreposicao", fontsize=7)
        page.insert_text((180, 424), "Ausencia de realce nao prova ausencia de ativo.", fontsize=8)
        document.save(path)


def _settle(application: QApplication, viewer: PdfViewerWidget) -> None:
    deadline = time.monotonic() + 20
    stable = 0
    while time.monotonic() < deadline:
        application.processEvents()
        ready = (
            viewer._current_preview is not None
            and viewer._current_preview.plano.rotacao_adicional_graus == viewer._rotation
            and viewer._render_queue.esta_ociosa()
            and not viewer._detail_timer.isActive()
        )
        stable = stable + 1 if ready else 0
        if stable >= 10:
            return
        time.sleep(0.01)
    raise TimeoutError("O visualizador não estabilizou a prévia e os tiles em 20 segundos")


def _contact_sheet(output: Path, rows: list[dict[str, Any]], theme: str) -> None:
    selected = [row for row in rows if row["theme"] == theme]
    sheet = QImage(1600, 1020, QImage.Format.Format_RGB32)
    sheet.fill(QColor("#e5e7eb"))
    painter = QPainter(sheet)
    painter.setFont(QFont("Arial", 11))
    for index, row in enumerate(selected):
        x, y = (index % 4) * 400, (index // 4) * 340
        painter.setPen(QColor("black"))
        painter.drawText(x + 6, y + 18, f"{theme} / {row['zoom']:.0%} / {row['rotation']} graus")
        screenshot = QImage(str(output / row["file"]))
        painter.drawImage(QRect(x, y + 25, 400, 309), screenshot)
    painter.end()
    if not sheet.save(str(output / f"contact-{theme}.png")):
        raise RuntimeError("Falha ao salvar folha de contato")


def capture(output: Path) -> list[dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / "runtime"
    runtime.mkdir(exist_ok=True)
    tempfile.tempdir = str(runtime.resolve())
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    if not isinstance(application, QApplication):
        raise RuntimeError("Uma QApplication é necessária")
    source = output / "synthetic-review.pdf"
    _source(source)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    gateway = LocalTestPdfViewerGateway(
        budget=OrcamentoRenderizacaoPdf(limite_pixels=360_000, limite_bytes=2_600_000)
    )
    viewer = PdfViewerWidget(gateway=gateway, dpi=144, limite_pixels_tile=40_000)
    viewer.resize(1100, 850)
    viewer.show()
    rows: list[dict[str, Any]] = []
    try:
        if not viewer.carregar_pdf(source):
            raise RuntimeError("Falha ao abrir fixture sintética")
        _settle(application, viewer)
        assert viewer.inspecao is not None
        page = viewer.inspecao.pages[0]
        proposals = _samples(page.page_id)
        viewer.definir_propostas_revisao(proposals)
        box = NormalizedBoxDto(
            x=str(315 / 600), y=str(307 / 600), width=str(105 / 600), height=str(34 / 600)
        )
        callout = ComplianceCalloutDto(
            callout_id=CalloutId(uuid5(NAMESPACE_URL, "e06:callout")),
            finding_id=FindingId(uuid5(NAMESPACE_URL, "e06:finding")),
            text="Callout preservado",
            anchor=_point(322, 293),
            box=box,
            font_size_points="7",
            navigation=EvidenceNavigationDto(
                document_id=viewer.inspecao.document_id,
                page_id=page.page_id,
                geometry=box,
                label="Callout E06",
            ),
        )
        viewer.definir_callouts_conformidade((callout,))
        for theme in Tema:
            aplicar_tema(application, theme)
            for zoom in (0.5, 1.0, 2.0):
                for rotation in (0, 90, 180, 270):
                    viewer._rotation = rotation
                    viewer._render_current_page()
                    _settle(application, viewer)
                    viewer.view.definir_zoom(zoom)
                    viewer.view.centerOn(viewer.view.sceneRect().center())
                    _settle(application, viewer)
                    viewer.view._review_items[str(proposals[0].proposal_id.root)].setSelected(True)
                    application.processEvents()
                    filename = f"{theme.value}-zoom{int(zoom * 100)}-rot{rotation}.png"
                    if not viewer.grab().save(str(output / filename)):
                        raise RuntimeError(f"Falha ao salvar {filename}")
                    row = {
                        "theme": theme.value,
                        "zoom": viewer.view.zoom,
                        "rotation": rotation,
                        "file": filename,
                        "highlights": len(viewer.view._review_items),
                        "callouts": len(viewer.view._callout_items),
                        "tiles": len(viewer.view._tile_items),
                        "captured": True,
                        "human_review": "pending",
                    }
                    rows.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        viewer.encerrar()
        viewer.close()
        gateway.close()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    for theme in Tema:
        _contact_sheet(output, rows, theme.value)
    (output / "matrix.json").write_text(
        json.dumps(
            {
                "source_sha256": original_hash,
                "opacity": REVIEW_HIGHLIGHT_OPACITY,
                "window": [1100, 850],
                "rows": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("tmp/e06/visual"))
    options = parser.parse_args()
    capture(options.output.resolve())


if __name__ == "__main__":
    main()
