# mypy: disable-error-code="no-untyped-call"
"""Author-owned E10 controls for document-scoped legend adaptation.

The fixture PDF is generated here and never uses benchmark ground truth or the
sealed reserve. Coordinates below describe only assertions, not detector input.
"""

from __future__ import annotations

import hashlib
import io

import pymupdf
from PIL import Image, ImageDraw

from zeny_project_handler.adapters.analysis.legacy_symbols import observar_simbolos_legados
from zeny_project_handler.adapters.analysis.legend_symbols import (
    LeituraLegenda,
    ResultadoLegendaDocumental,
    observar_legenda_documental,
)
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import ObservacaoSimbolo

_PAGE_WIDTH = 512
_PAGE_HEIGHT = 256
_EXEMPLAR = (48, 49, 80, 81)
_OCCURRENCE = (310, 148, 342, 180)


def _motif_png() -> bytes:
    """A distinctive local convention that has no catalog class."""
    image = Image.new("L", (48, 48), 255)
    draw = ImageDraw.Draw(image)
    draw.polygon(((10, 12), (36, 9), (39, 34), (24, 39), (8, 30)), outline=0, width=3)
    draw.line(((13, 16), (33, 32)), fill=0, width=3)
    draw.ellipse((28, 15, 34, 21), fill=0)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


_MOTIF_PNG = _motif_png()


def _add_legend(page: pymupdf.Page, description: str, *, revision: str | None = None) -> None:
    page.insert_text((40, 34), "LEGENDA", fontsize=12)
    if revision is not None:
        page.insert_text((275, 34), f"REVISAO {revision}", fontsize=9)
    page.insert_image(pymupdf.Rect(_EXEMPLAR), stream=_MOTIF_PNG)
    page.insert_text((94, 68), description, fontsize=10)


def _add_occurrence(page: pymupdf.Page, box: tuple[int, int, int, int] = _OCCURRENCE) -> None:
    page.insert_image(pymupdf.Rect(box), stream=_MOTIF_PNG)


def _add_legacy_ground(page: pymupdf.Page) -> None:
    page.draw_line((40, 150), (55, 150), color=(0, 0, 0), width=0.5)
    for index, height in enumerate((5, 3.5, 2)):
        x = 55 + index * 4
        page.draw_line((x, 150 - height), (x, 150 + height), color=(0, 0, 0), width=0.5)


def _document(
    *,
    labels: tuple[tuple[int, str, str | None], ...] = ((1, "ANCORA LOCAL", None),),
    occurrences: tuple[int, ...] = (1, 2),
    pages: int = 2,
) -> pymupdf.Document:
    document = pymupdf.open()
    for _ in range(pages):
        document.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
    for page_number, description, revision in labels:
        _add_legend(document[page_number - 1], description, revision=revision)
    for page_number in occurrences:
        _add_occurrence(document[page_number - 1])
    return document


def _observe(
    document: pymupdf.Document,
    document_id: str,
    *,
    leituras_ocr: tuple[LeituraLegenda, ...] = (),
    digest: str | None = None,
) -> ResultadoLegendaDocumental:
    selected_digest = digest or hashlib.sha256(document.tobytes()).hexdigest()
    return observar_legenda_documental(
        document,
        documento_id=document_id,
        documento_sha256=selected_digest,
        leituras_ocr=leituras_ocr,
    )


def _box(observation: ObservacaoSimbolo) -> tuple[float, float, float, float]:
    points = observation.geometria.pontos_originais
    return (
        min(float(point[0]) for point in points),
        min(float(point[1]) for point in points),
        max(float(point[0]) for point in points),
        max(float(point[1]) for point in points),
    )


def test_local_legend_finds_unknown_on_legend_page_and_page_without_legend() -> None:
    with _document() as document:
        result = _observe(document, "project-a/document-a")

    assert any(pair.descricao == "ANCORA LOCAL" for pair in result.pares)
    observations = result.resultado.observacoes
    assert {item.fonte.pagina_numero for item in observations} == {1, 2}
    assert all(item.alternativas[0].classe is None for item in observations)
    assert all(dict(item.atributos)["contexto"] == "operacional" for item in observations)
    assert all(dict(item.atributos)["descricao_legenda"] == "ANCORA LOCAL" for item in observations)
    assert all(dict(item.atributos)["template_sha256"] for item in observations)
    assert all(_box(item)[1] > 100 for item in observations if item.fonte.pagina_numero == 1)
    assert len(result.resultado.coberturas) == 2


def test_legend_search_region_does_not_suppress_an_operational_repetition_below_it() -> None:
    # A heading's search window is broader than the one actual legend row.
    # This occurrence lies below that row on the same page and is an asset
    # candidate even though its x position is inside the heading's window.
    operational_box = (160, 145, 192, 177)
    with _document(occurrences=(), pages=1) as document:
        _add_occurrence(document[0], operational_box)
        result = _observe(document, "project-a/below-legend")

    assert any(
        item.fonte.pagina_numero == 1
        and abs(_box(item)[0] - operational_box[0]) < 3
        and abs(_box(item)[1] - operational_box[1]) < 3
        for item in result.resultado.observacoes
    )
    assert all(_box(item)[1] > 100 for item in result.resultado.observacoes)


def test_absent_legend_does_not_veto_exclusive_legacy_candidate() -> None:
    with _document(labels=(), occurrences=(), pages=1) as document:
        page = document[0]
        _add_legacy_ground(page)
        digest = hashlib.sha256(document.tobytes()).hexdigest()
        legacy = observar_simbolos_legados(
            page,
            documento_id="project-a/no-legend",
            documento_sha256=digest,
            pagina_numero=1,
        )
        local = observar_legenda_documental(
            document, documento_id="project-a/no-legend", documento_sha256=digest
        )

    assert legacy.observacoes
    assert local.pares == ()
    assert local.resultado.observacoes == ()
    assert all(
        coverage.estado is EstadoMetodoSimbolos.NAO_DETECCAO
        for coverage in local.resultado.coberturas
    )
    assert len({item.id for item in (*legacy.observacoes, *local.resultado.observacoes)}) == len(
        legacy.observacoes
    )


def test_repeated_local_image_without_legend_yields_reviewable_unknowns() -> None:
    with _document(labels=(), occurrences=(1, 2)) as document:
        result = _observe(document, "project-a/repeated-no-legend")

    assert result.pares == ()
    assert result.regioes_legenda == ()
    assert {item.fonte.pagina_numero for item in result.resultado.observacoes} == {1, 2}
    assert len(result.resultado.observacoes) == 2
    assert all(item.alternativas[0].classe is None for item in result.resultado.observacoes)
    assert all(
        dict(item.atributos)["origem_legenda"] == "repeticao-imagem-local"
        for item in result.resultado.observacoes
    )
    assert all(dict(item.atributos)["pareamento_incerto"] for item in result.resultado.observacoes)


def test_single_image_does_not_borrow_repetitions_from_other_documents() -> None:
    with _document(labels=(), occurrences=(1, 2)) as repeated:
        assert len(_observe(repeated, "project-a/repeated").resultado.observacoes) == 2
    with _document(labels=(), occurrences=(1,), pages=1) as first_isolated:
        first = _observe(first_isolated, "project-a/isolated")
    with _document(labels=(), occurrences=(1,), pages=1) as second_isolated:
        second = _observe(second_isolated, "project-b/isolated")

    assert first.pares == second.pares == ()
    assert first.resultado.observacoes == second.resultado.observacoes == ()
    assert all(
        coverage.estado is EstadoMetodoSimbolos.NAO_DETECCAO
        for coverage in (*first.resultado.coberturas, *second.resultado.coberturas)
    )


def test_template_and_description_stay_inside_source_document_and_project() -> None:
    with _document(labels=((1, "ANCORA LOCAL", None),)) as first:
        digest = hashlib.sha256(first.tobytes()).hexdigest()
        first_result = _observe(first, "project-a/document-a", digest=digest)
        first_again = _observe(first, "project-a/document-a", digest=digest)
    with _document(labels=(), occurrences=(1,), pages=1) as no_legend:
        no_legend_result = _observe(no_legend, "project-b/document-b")
    with _document(labels=((1, "MARCADOR REVISTO", None),)) as other:
        other_result = _observe(other, "project-b/document-c")

    assert first_result.resultado.observacoes
    assert tuple(item.id for item in first_result.resultado.observacoes) == tuple(
        item.id for item in first_again.resultado.observacoes
    )
    assert no_legend_result.resultado.observacoes == ()
    assert other_result.resultado.observacoes
    assert {
        dict(item.atributos)["descricao_legenda"] for item in first_result.resultado.observacoes
    } == {"ANCORA LOCAL"}
    assert {
        dict(item.atributos)["descricao_legenda"] for item in other_result.resultado.observacoes
    } == {"MARCADOR REVISTO"}
    assert first_result.resultado.perfil.assinatura() != other_result.resultado.perfil.assinatura()


def test_conflicting_ocr_description_remains_reviewable_without_certified_class() -> None:
    with _document() as document:
        _add_legacy_ground(document[0])
        digest = hashlib.sha256(document.tobytes()).hexdigest()
        legacy = observar_simbolos_legados(
            document[0],
            documento_id="project-a/ocr-conflict",
            documento_sha256=digest,
            pagina_numero=1,
        )
        result = _observe(
            document,
            "project-a/ocr-conflict",
            digest=digest,
            leituras_ocr=(
                LeituraLegenda(
                    pagina_numero=1,
                    texto="OUTRO NOME INCERTO",
                    caixa=(94, 57, 195, 70),
                    origem="ocr-injetado",
                    revisao="B",
                ),
            ),
        )

    assert {pair.descricao for pair in result.pares} >= {
        "ANCORA LOCAL",
        "OUTRO NOME INCERTO",
    }
    assert any(pair.origem == "ocr-injetado" and pair.revisao == "B" for pair in result.pares)
    assert any(pair.pareamento_incerto for pair in result.pares)
    assert result.resultado.observacoes
    assert all(item.alternativas[0].classe is None for item in result.resultado.observacoes)
    assert legacy.observacoes
    assert len({item.id for item in (*legacy.observacoes, *result.resultado.observacoes)}) == (
        len(legacy.observacoes) + len(result.resultado.observacoes)
    )
    with _document(labels=(), occurrences=(1,), pages=1) as unrelated:
        assert _observe(unrelated, "project-b/after-ocr-conflict").resultado.observacoes == ()


def test_multiple_legends_and_revisions_preserve_competing_descriptions() -> None:
    with _document(
        labels=((1, "DESCRICAO REV A", "A"), (2, "DESCRICAO REV B", "B")),
        occurrences=(3,),
        pages=3,
    ) as document:
        result = _observe(document, "project-a/multiple-revisions")

    assert {pair.descricao for pair in result.pares} >= {
        "DESCRICAO REV A",
        "DESCRICAO REV B",
    }
    assert {pair.revisao for pair in result.pares} >= {"A", "B"}
    assert result.resultado.observacoes
    assert {item.fonte.pagina_numero for item in result.resultado.observacoes} == {3}
    assert all(item.alternativas[0].classe is None for item in result.resultado.observacoes)
    assert any(pair.pareamento_incerto for pair in result.pares)
