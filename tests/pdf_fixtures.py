# mypy: disable-error-code="no-untyped-call"
"""Construtores pequenos de PDFs determinísticos usados pelos testes."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf

_XREF_PATTERN = re.compile(r"(?<!\d)(\d+)\s+\d+\s+R")
TEST_RENDER_BUDGET = OrcamentoRenderizacaoPdf(
    limite_pixels=8_000_000,
    limite_bytes=64 * 1024 * 1024,
)


def create_feature_pdf(path: Path) -> Path:
    document = pymupdf.open()
    source_form = pymupdf.open()
    try:
        form_page = source_form.new_page(width=40, height=40)
        form_page.draw_circle((20, 20), 12, color=(0, 0, 1), fill=(0, 0, 1))

        page = document.new_page(width=200, height=100)
        optional_group = document.add_ocg("Camada de teste")
        page.draw_rect(
            pymupdf.Rect(10, 10, 80, 50),
            color=(1, 0, 0),
            fill=(1, 0, 0),
            oc=optional_group,
        )
        page.insert_text((15, 75), "POSTE P1")
        page.insert_image(pymupdf.Rect(90, 10, 110, 30), stream=_red_pixel_png())
        page.add_stamp_annot(pymupdf.Rect(120, 10, 170, 40), stamp=0)
        page.show_pdf_page(pymupdf.Rect(120, 50, 160, 90), source_form, 0)

        rotated = document.new_page(width=200, height=100)
        rotated.insert_text((30, 50), "PAGINA GIRADA")
        rotated.set_cropbox(pymupdf.Rect(20, 10, 180, 90))
        rotated.set_rotation(90)

        scanned = document.new_page(width=120, height=120)
        scanned.insert_image(scanned.rect, stream=_red_pixel_png())
        document.save(path)
    finally:
        source_form.close()
        document.close()
    return path


def create_golden_pdf(path: Path) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=72, height=48)
        page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
        page.draw_rect(pymupdf.Rect(18, 12, 54, 36), color=(1, 0, 0), fill=(1, 0, 0))
        document.save(path)
    finally:
        document.close()
    return path


def create_clip_rotation_golden_pdf(path: Path) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=80, height=60)
        page.draw_rect(pymupdf.Rect(0, 0, 40, 30), color=(1, 0, 0), fill=(1, 0, 0))
        page.draw_rect(pymupdf.Rect(40, 0, 80, 30), color=(0, 1, 0), fill=(0, 1, 0))
        page.draw_rect(pymupdf.Rect(0, 30, 40, 60), color=(0, 0, 1), fill=(0, 0, 1))
        page.draw_rect(pymupdf.Rect(40, 30, 80, 60), color=(1, 1, 0), fill=(1, 1, 0))
        document.save(path)
    finally:
        document.close()
    return path


def create_large_format_pdf(path: Path, *, width_points: float, height_points: float) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=width_points, height=height_points)
        page.insert_text((24, 36), "PRANCHA SINTETICA")
        document.save(path)
    finally:
        document.close()
    return path


def create_callout_formats_pdf(path: Path) -> Path:
    """Crie A4/A3 em retrato/paisagem com alvos assimétricos para os callouts."""
    document = pymupdf.open()
    try:
        formats = (
            (595.0, 842.0, "A4 RETRATO"),
            (842.0, 595.0, "A4 PAISAGEM"),
            (842.0, 1191.0, "A3 RETRATO"),
            (1191.0, 842.0, "A3 PAISAGEM"),
        )
        for width, height, label in formats:
            page = document.new_page(width=width, height=height)
            page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
            page.insert_text((24, 32), label, fontsize=12)
            target = pymupdf.Point(width * 0.46, height * 0.56)
            page.draw_circle(target, 8, color=(0.1, 0.1, 0.1), fill=(0.1, 0.1, 0.1))
            page.insert_text((target.x + 12, target.y + 4), "P2", fontsize=9)
        document.save(path)
    finally:
        document.close()
    return path


def create_callout_header_pdf(path: Path) -> Path:
    """Crie uma folha cujo cabeçalho visual disputa a posição mais próxima de P2."""
    width = 595.0
    height = 842.0
    document = pymupdf.open()
    try:
        page = document.new_page(width=width, height=height)
        page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
        header = pymupdf.Rect(width * 0.58, height * 0.34, width * 0.96, height * 0.76)
        page.draw_rect(header, color=(0.2, 0.2, 0.2), fill=(0.94, 0.94, 0.94), width=1)
        for row in range(1, 7):
            y = header.y0 + header.height * row / 7
            page.draw_line((header.x0, y), (header.x1, y), color=(0.35, 0.35, 0.35))
        page.insert_text((header.x0 + 10, header.y0 + 22), "CABECALHO DO PROJETO", fontsize=10)
        page.insert_text((header.x0 + 10, header.y0 + 62), "NS / FOLHA / ESCALA", fontsize=8)
        target = pymupdf.Point(width * 0.46, height * 0.56)
        page.draw_circle(target, 8, color=(0.1, 0.1, 0.1), fill=(0.1, 0.1, 0.1))
        page.insert_text((target.x + 12, target.y + 4), "P2", fontsize=9)
        document.save(path)
    finally:
        document.close()
    return path


def create_catalog_pdf(path: Path, code: str) -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=240, height=160)
        page.insert_text((20, 25), "P1")
        page.insert_text((20, 40), code)
        document.save(path)
    finally:
        document.close()
    return path


def create_e01_structure_occurrences_pdf(path: Path) -> Path:
    """Crie ocorrências independentes e negativos contextuais para estruturas."""
    document = pymupdf.open()
    try:
        page = _new_e01_page(document, "ESTRUTURAS SINTETICAS")
        page.insert_text((48, 72), "PONTO T1", fontsize=10)
        page.insert_text((48, 96), "N(2)", fontsize=11)
        page.insert_text((48, 132), "N-(4 CAA)", fontsize=11)
        page.insert_text((220, 72), "PONTO T2", fontsize=10)
        page.insert_text((220, 96), "CM3(1)", fontsize=11)
        page.insert_text((220, 124), "CM3(2)", fontsize=11)
        page.insert_text((392, 72), "PONTO T3", fontsize=10)
        page.insert_text((392, 96), "S3R", fontsize=11)
        page.insert_text((392, 136), "S3R", fontsize=11)
        page.insert_text((48, 214), "NEGATIVO: NOTA COM N ISOLADO", fontsize=9)
        document.save(path)
    finally:
        document.close()
    return path


def create_e01_switch_bags_pdf(path: Path) -> Path:
    """Crie chaves com bolsas parciais e controles sem vínculo geométrico."""
    document = pymupdf.open()
    try:
        page = _new_e01_page(document, "CHAVES E BOLSAS SINTETICAS", height=390)
        positive_labels = (("100A-10KA-2H", 74.0), ("100A-10KA-5H", 132.0))
        for label, baseline in positive_labels:
            page.insert_text((48, baseline), label, fontsize=11)
            _draw_partial_bag(page, x=48, baseline=baseline, label=label, suffix=label[-5:])
        page.insert_text((48, 190), "100A-10KA-2H", fontsize=11)
        page.insert_text((48, 232), "100A-10KA-5H", fontsize=11)
        page.insert_text((270, 190), "IDTESTE-300A-12T", fontsize=11)
        page.insert_text((270, 232), "MARCA SEM EQUIPAMENTO", fontsize=9)
        page.draw_polyline(
            [(268, 240), (268, 218), (410, 218), (410, 240)],
            color=_E01_BURGUNDY,
            width=1.4,
        )
        document.save(path)
    finally:
        document.close()
    return path


def create_e01_span_change_pdf(path: Path) -> Path:
    """Crie medida substituída, medida vigente e marca vermelha não relacionada."""
    document = pymupdf.open()
    try:
        page = _new_e01_page(document, "ALTERACAO DE MEDIDA SINTETICA")
        page.draw_line((42, 188), (548, 188), color=(0.1, 0.45, 0.1), width=2)
        page.insert_text((70, 92), "321 m", fontsize=12)
        page.draw_line((66, 86), (118, 86), color=_E01_BURGUNDY, width=2)
        page.insert_text((162, 92), "269 m", fontsize=12)
        page.insert_text((70, 136), "42 m", fontsize=12)
        page.draw_line((66, 146), (112, 146), color=_E01_BURGUNDY, width=2)
        page.insert_text((70, 210), "CABO COLINEAR", fontsize=9)
        document.save(path)
    finally:
        document.close()
    return path


def create_e01_network_service_drop_pdf(path: Path) -> Path:
    """Crie rede colinear, ramal oblíquo e padrão separado do poste."""
    document = pymupdf.open()
    try:
        page = _new_e01_page(document, "REDE RAMAL E PADRAO SINTETICOS", width=680, height=430)
        page.draw_line((62, 210), (438, 210), color=(0.1, 0.45, 0.1), width=2)
        page.draw_circle((96, 210), 5, color=(0, 0, 0), fill=(1, 1, 1))
        page.draw_circle((308, 210), 5, color=(0, 0, 0), fill=(1, 1, 1))
        page.insert_text((78, 194), "P1", fontsize=10)
        page.insert_text((286, 194), "P2 POSTE DA REDE", fontsize=10)
        page.insert_text((278, 236), "ESTRUTURA CM1", fontsize=9)
        page.draw_line((308, 210), (520, 336), color=(0.15, 0.15, 0.15), width=1.6)
        page.draw_circle((520, 336), 5, color=(0, 0, 0), fill=(1, 1, 1))
        page.insert_text((442, 314), "RAMAL R1-ENTREGA", fontsize=9)
        _insert_e01_padrao(page, x=500, baseline=360, fontsize=11)
        page.insert_text((476, 86), "LEGENDA: PADRAO DE COR", fontsize=9)
        page.draw_line((470, 98), (612, 98), color=_E01_BURGUNDY, width=1.4)
        document.save(path)
    finally:
        document.close()
    return path


def create_e01_topology_cases_pdf(path: Path) -> Path:
    """Crie topologias completa, incompleta, terminal e de transição reais."""
    document = pymupdf.open()
    try:
        complete = _new_e01_page(document, "TOPOLOGIA COMPLETA")
        _draw_topology_point(complete, 90, 176, "P1")
        _draw_topology_point(complete, 300, 176, "P2")
        _draw_topology_point(complete, 510, 176, "P3")
        complete.draw_line((90, 176), (300, 176), color=(0.1, 0.45, 0.1), width=2)
        complete.draw_line((300, 176), (510, 176), color=(0.1, 0.45, 0.1), width=2)
        complete.insert_text((222, 214), "MESMA TECNOLOGIA", fontsize=9)

        incomplete = _new_e01_page(document, "TOPOLOGIA INCOMPLETA")
        _draw_topology_point(incomplete, 300, 176, "P4")
        incomplete.draw_line((0, 176), (300, 176), color=(0.1, 0.45, 0.1), width=2)
        incomplete.insert_text((170, 214), "EXTREMIDADE AUSENTE", fontsize=9)

        terminal = _new_e01_page(document, "FIM REAL")
        _draw_topology_point(terminal, 160, 176, "P5")
        _draw_topology_point(terminal, 440, 176, "P6")
        terminal.draw_line((160, 176), (440, 176), color=(0.1, 0.45, 0.1), width=2)
        terminal.insert_text((238, 214), "TRECHO RESOLVIDO", fontsize=9)

        transition = _new_e01_page(document, "TRANSICAO REAL")
        _draw_topology_point(transition, 90, 176, "P7")
        _draw_topology_point(transition, 300, 176, "P8")
        _draw_topology_point(transition, 510, 176, "P9")
        transition.draw_line((90, 176), (300, 176), color=(0.1, 0.45, 0.1), width=2)
        transition.draw_line(
            (300, 176),
            (510, 176),
            color=(0.1, 0.45, 0.1),
            width=2,
            dashes="[5 3] 0",
        )
        transition.insert_text((154, 154), "REDE NUA", fontsize=9)
        transition.insert_text((374, 154), "REDE ISOLADA", fontsize=9)
        document.save(path)
    finally:
        document.close()
    return path


def create_action_requirements_pdf(path: Path, code: str) -> Path:
    """Crie uma prancha com os dois gatilhos operacionais e âncoras distintas."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_text((48, 90), "P1", fontsize=10)
        page.insert_text((48, 108), code, fontsize=9)
        page.insert_text((90, 310), "FAIXA DE SERVIDAO", fontsize=11)
        page.draw_rect(pymupdf.Rect(332, 760, 570, 820), color=(0.2, 0.2, 0.2))
        page.insert_text((350, 792), "Impacto Ambiental: Sim", fontsize=10)
        document.save(path)
    finally:
        document.close()
    return path


def create_mixed_raster_text_pdf(path: Path) -> Path:
    """Página com texto nativo suficiente e uma imagem que ainda exige OCR."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=120, height=120)
        page.insert_image(page.rect, stream=_red_pixel_png())
        page.insert_text((10, 20), "TEXTO NATIVO SUFICIENTE NA MARGEM")
        document.save(path)
    finally:
        document.close()
    return path


def create_small_raster_region_pdf(path: Path) -> Path:
    """Página híbrida com uma pequena região raster que precisa de OCR localizado."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=200, height=200)
        page.insert_text((10, 20), "TEXTO NATIVO SUFICIENTE NO CARIMBO DO PROJETO")
        page.insert_image(
            pymupdf.Rect(140, 120, 180, 160),
            stream=_scanned_text_png(),
        )
        document.save(path)
    finally:
        document.close()
    return path


def create_dense_vector_text_pdf(path: Path) -> Path:
    """Página CAD sintética em que glifos podem ter sido convertidos em muitos caminhos."""
    document = pymupdf.open()
    try:
        page = document.new_page(width=120, height=120)
        page.insert_text((10, 20), "TEXTO NATIVO SUFICIENTE NO CARIMBO")
        shape = page.new_shape()
        for index in range(1000):
            coordinate = float(index % 100) + 10
            row = float(index // 100) + 40
            shape.draw_line((coordinate, row), (coordinate + 0.2, row + 0.2))
            shape.finish()
        shape.commit()
        document.save(path)
    finally:
        document.close()
    return path


def create_analysis_pdf(path: Path) -> Path:
    """PDF rico, incluindo imagem em appearance stream e Form XObject aninhado."""
    document = pymupdf.open()
    nested = pymupdf.open()
    try:
        nested_page = nested.new_page(width=40, height=40)
        nested_page.draw_circle((20, 20), 12, color=(0, 0, 1), fill=(0, 0, 1))
        nested_page.insert_image(pymupdf.Rect(12, 12, 28, 28), stream=_red_pixel_png())

        page = document.new_page(width=240, height=160)
        page.insert_text((12, 25), "POSTE P1", fontsize=10)
        page.insert_text((105, 40), "P2", fontsize=10)
        page.insert_text((25, 135), "MT", fontsize=9, rotate=90)
        page.draw_line((10, 40), (90, 40), color=(0, 1, 0), width=2)
        page.draw_bezier((10, 55), (30, 35), (60, 75), (90, 55), color=(0, 0, 1))
        page.draw_polyline([(10, 70), (50, 90), (90, 70)], color=(1, 0, 0), closePath=True)
        image_xref = page.insert_image(pymupdf.Rect(105, 10, 125, 30), stream=_red_pixel_png())
        stamp = page.add_stamp_annot(pymupdf.Rect(135, 10, 205, 40), stamp=0)
        page.add_freetext_annot(pymupdf.Rect(105, 45, 180, 65), "ESTRUTURA N1")
        shx = page.add_rect_annot(pymupdf.Rect(105, 70, 150, 100))
        shx.set_info(title="AutoCAD SHX Text")
        shx.update()
        note = page.add_text_annot((205, 85), "NOTA COM POPUP")
        note.set_popup(pymupdf.Rect(155, 100, 230, 145))
        page.show_pdf_page(pymupdf.Rect(10, 105, 50, 145), nested, 0)

        appearance_match = _XREF_PATTERN.search(str(document.xref_get_key(stamp.xref, "AP")[1]))
        assert appearance_match is not None
        appearance_xref = int(appearance_match.group(1))
        document.xref_set_key(
            appearance_xref, "Resources/XObject/ImAppearance", f"{image_xref} 0 R"
        )
        original_stream = bytes(document.xref_stream(appearance_xref) or b"")
        document.update_stream(
            appearance_xref,
            original_stream + b"\nq 12 0 0 12 2 2 cm /ImAppearance Do Q\n",
        )

        scanned = document.new_page(width=120, height=120)
        scanned.insert_image(scanned.rect, stream=_red_pixel_png())
        document.save(path)
    finally:
        nested.close()
        document.close()
    return path


def create_protected_pdf(path: Path, password: str = "senha") -> Path:
    document = pymupdf.open()
    try:
        page = document.new_page(width=100, height=100)
        page.insert_text((10, 50), "PROTEGIDO")
        document.save(
            path,
            encryption=int(pymupdf.PDF_ENCRYPT_AES_256),  # type: ignore[attr-defined]
            owner_pw="proprietario",
            user_pw=password,
        )
    finally:
        document.close()
    return path


_E01_BURGUNDY = (0.55, 0.0, 0.2)


def _new_e01_page(
    document: pymupdf.Document,
    title: str,
    *,
    width: float = 600,
    height: float = 320,
) -> pymupdf.Page:
    page = document.new_page(width=width, height=height)
    page.insert_text((24, 28), title, fontsize=12)
    return page


def _draw_partial_bag(
    page: pymupdf.Page,
    *,
    x: float,
    baseline: float,
    label: str,
    suffix: str,
) -> None:
    label_width = pymupdf.get_text_length(label, fontname="helv", fontsize=11)
    suffix_width = pymupdf.get_text_length(suffix, fontname="helv", fontsize=11)
    left = x + label_width - suffix_width - 2
    right = x + label_width + 3
    page.draw_polyline(
        [
            (left, baseline - 14),
            (right, baseline - 14),
            (right, baseline + 4),
            (left, baseline + 4),
        ],
        color=_E01_BURGUNDY,
        width=1.4,
    )


def _draw_topology_point(page: pymupdf.Page, x: float, y: float, label: str) -> None:
    page.draw_circle((x, y), 5, color=(0, 0, 0), fill=(1, 1, 1))
    page.insert_text((x - 8, y - 14), label, fontsize=9)


def _insert_e01_padrao(
    page: pymupdf.Page,
    *,
    x: float,
    baseline: float,
    fontsize: float,
) -> None:
    """Desenhe PADRÃO com texto ASCII extraível e til sobreposto sintético."""
    page.insert_text((x, baseline), "PADRAO", fontsize=fontsize)
    prefix_width = pymupdf.get_text_length("PADR", fontname="helv", fontsize=fontsize)
    letter_width = pymupdf.get_text_length("A", fontname="helv", fontsize=fontsize)
    left = x + prefix_width + 1
    top = baseline - fontsize - 2
    page.draw_bezier(
        (left, top),
        (left + letter_width * 0.3, top - 2),
        (left + letter_width * 0.7, top + 2),
        (left + letter_width - 1, top),
        color=(0, 0, 0),
        width=0.8,
    )


def _red_pixel_png() -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 2, 2), False)
    pixmap.clear_with(0xFF0000)
    return bytes(pixmap.tobytes("png"))


def _scanned_text_png() -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page(width=100, height=50)
        page.insert_text((5, 25), "280653/7683008", fontsize=8)
        return bytes(page.get_pixmap(dpi=144, alpha=False).tobytes("png"))
    finally:
        document.close()
