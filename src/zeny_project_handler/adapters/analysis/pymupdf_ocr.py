# mypy: disable-error-code="no-untyped-call"
"""Fronteira de rasterização usada exclusivamente pelo OCR condicional."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from math import atan2, degrees, hypot
from typing import Any

import pymupdf
from PIL import Image, ImageOps

from zeny_project_handler.domain.analysis import DiagnosticoAnalise, OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    GeometriaNormalizada,
    MotorOcrBlocoOperacionalPort,
    MotorOcrIdentificadorPort,
    MotorOcrPort,
    MotorOcrRotuloOperacionalPort,
    PaginaRasterOcr,
    SolicitacaoAnaliseDocumento,
)

from .pymupdf_support import _extras, _normalized_point

_POINT_IDENTIFIER_PATTERN = re.compile(r"P0*(\d{1,3})", re.IGNORECASE)
_TARGETED_SPAN_IDENTIFIER_PATTERN = re.compile(
    r"V?0*(\d{1,3})-0*(\d{1,3})",
    re.IGNORECASE,
)
_NUMERIC_OPERATIONAL_LABEL_PATTERN = re.compile(r"[0-9OQCDILSBZG]+(?:-[0-9OQCDILSBZG]+)+")
_MESSENGER_CABLE_PATTERN = re.compile(
    r"([ABC]+M-\d{1,3}\(3/8)\"?\)?",
    re.IGNORECASE,
)
_NEUTRAL_CABLE_PATTERN = re.compile(
    r"N-\((\d{1,2}N\d{1,2}|(?:\d{1,2}(?:/\d{1,2})?)(?:CAA|CA))\)?",
    re.IGNORECASE,
)
_INSULATED_CABLE_PATTERN = re.compile(
    r"([ABC]+N-\d{1,3}\(\d{1,3}\))",
    re.IGNORECASE,
)
_CANONICAL_MESSENGER_CABLE_PATTERN = re.compile(r"[ABC]+M-\d{1,3}\(3/8\"\)")
_CANONICAL_NEUTRAL_CABLE_PATTERN = re.compile(
    r"N-(?: \(\d{1,2}N\d{1,2}\)|\(\d{1,2}(?:/\d{1,2})? (?:CAA|CA)\))"
)
_CANONICAL_INSULATED_CABLE_PATTERN = re.compile(r"[ABC]+N-\d{1,3}\(\d{1,3}\)")
_SPAN_LENGTH_PATTERN = re.compile(
    r"(?<!\d)(\d{1,4})\s*M\s+VR\s*[:=]?\s*(\d{1,4})\s*M(?![A-Z0-9])",
    re.IGNORECASE,
)
_EQUIPMENT_OCR_PATTERN = re.compile(
    r"(?<![A-Z0-9])([0-9OQCDILSBZGT]{2,4})A[-/:]"
    r"([0-9OQCDILSBZG]{1,2})KA[-/:]([0-9OQCDILSBZG]{1,2})([HK])"
    r"(?![A-Z0-9])",
    re.IGNORECASE,
)
_NUMERIC_OCR_TRANSLATION = str.maketrans(
    {
        "O": "0",
        "Q": "0",
        "C": "0",
        "D": "0",
        "I": "1",
        "L": "1",
        "Z": "2",
        "S": "5",
        "B": "8",
        "G": "6",
    }
)
_MINIMUM_POINT_IDENTIFIER_CONFIDENCE = Decimal("0.20")
_MINIMUM_OPERATIONAL_LABEL_CONFIDENCE = Decimal("0.20")
_MINIMUM_TARGETED_IDENTIFIER_CONFIDENCE = Decimal("0.10")


@dataclass(frozen=True, slots=True)
class _OperationalFrame:
    bounds: tuple[Decimal, Decimal, Decimal, Decimal]
    origin: tuple[float, float]
    horizontal_axis: tuple[float, float]
    vertical_axis: tuple[float, float]
    width_points: float
    height_points: float

    @property
    def center(self) -> tuple[float, float]:
        return (
            self.origin[0] + self.horizontal_axis[0] / 2 + self.vertical_axis[0] / 2,
            self.origin[1] + self.horizontal_axis[1] / 2 + self.vertical_axis[1] / 2,
        )


@dataclass(frozen=True, slots=True)
class _RectifiedRegion:
    raster: PaginaRasterOcr
    origin: tuple[float, float]
    horizontal_axis: tuple[float, float]
    vertical_axis: tuple[float, float]
    content_width_pixels: int
    content_height_pixels: int
    padding_pixels: int


def _conditional_ocr(
    page: Any,
    page_number: int,
    request: SolicitacaoAnaliseDocumento,
    ocr_engine: MotorOcrPort | None,
    native_characters: int,
    image_coverage: Decimal,
    vector_count: int,
    image_candidates: tuple[CandidatoEvidenciaDocumento, ...],
) -> tuple[tuple[CandidatoEvidenciaDocumento, ...], tuple[DiagnosticoAnalise, ...]]:
    config = request.configuracao
    if not config.habilitar_ocr_condicional:
        return (), ()
    has_enough_native_text = native_characters >= config.minimo_caracteres_texto_nativo
    has_relevant_raster = image_coverage >= config.area_imagem_minima_para_ocr
    has_dense_vector_content = vector_count >= config.minimo_vetores_para_ocr
    use_full_page = not has_enough_native_text or has_relevant_raster or has_dense_vector_content
    regional_images = tuple(
        item
        for item in image_candidates
        if _candidate_area(item) >= config.area_imagem_regional_minima_para_ocr
        and _has_regional_ocr_resolution(item)
    )
    if not use_full_page and not regional_images:
        return (), ()
    if ocr_engine is None:
        return (), (
            DiagnosticoAnalise(
                codigo="analise.ocr_indisponivel",
                mensagem=(
                    "A página pode conter texto rasterizado, mas nenhum motor OCR está configurado."
                ),
                extrator="ocr",
                pagina_numero=page_number,
            ),
        )
    try:
        if use_full_page:
            if has_dense_vector_content:
                candidates = _extract_ocr_tiled(
                    page,
                    page_number,
                    ocr_engine,
                    config.dpi_ocr,
                    divisions=config.divisoes_ocr_conteudo_denso,
                    overlap=config.sobreposicao_ocr_conteudo_denso,
                )
            else:
                candidates = _extract_ocr(page, page_number, ocr_engine, config.dpi_ocr)
        else:
            candidates = tuple(
                candidate
                for index, image in enumerate(regional_images)
                for candidate in _extract_ocr_region(
                    page,
                    page_number,
                    ocr_engine,
                    config.dpi_ocr,
                    bounds=_candidate_bounds(image),
                    stable_suffix=f"imagem:{index}",
                )
            )
    except Exception:
        return (), (
            DiagnosticoAnalise(
                codigo="analise.ocr_falhou",
                mensagem=(
                    "O extrator de ocr falhou nesta página; os demais resultados foram mantidos."
                ),
                extrator="ocr",
                pagina_numero=page_number,
            ),
        )
    if not has_dense_vector_content or not isinstance(
        ocr_engine,
        MotorOcrIdentificadorPort,
    ):
        return candidates, ()
    targeted_candidates: list[CandidatoEvidenciaDocumento] = []
    targeted_diagnostics: list[DiagnosticoAnalise] = []
    try:
        targeted_candidates.extend(
            _extract_point_identifiers(
                page,
                page_number,
                ocr_engine,
                config.dpi_ocr_identificadores,
            )
        )
    except Exception:
        targeted_diagnostics.append(
            DiagnosticoAnalise(
                codigo="analise.ocr_identificadores_falhou",
                mensagem=(
                    "A leitura localizada dos identificadores de ponto falhou; "
                    "o OCR geral da página foi mantido."
                ),
                extrator="ocr-identificadores",
                pagina_numero=page_number,
            )
        )
    if isinstance(ocr_engine, MotorOcrRotuloOperacionalPort):
        try:
            targeted_candidates.extend(
                _extract_blue_operational_identifiers(
                    page,
                    page_number,
                    ocr_engine,
                    config.dpi_ocr_identificadores,
                )
            )
            targeted_candidates.extend(
                _extract_linear_operational_labels(
                    page,
                    page_number,
                    ocr_engine,
                    config.dpi_ocr_rotulos_inclinados,
                )
            )
        except Exception:
            targeted_diagnostics.append(
                DiagnosticoAnalise(
                    codigo="analise.ocr_rotulos_lineares_falhou",
                    mensagem=(
                        "A leitura localizada de rótulos inclinados falhou; "
                        "os demais resultados de OCR foram mantidos."
                    ),
                    extrator="ocr-rotulos-lineares",
                    pagina_numero=page_number,
                )
            )
    if isinstance(ocr_engine, MotorOcrBlocoOperacionalPort):
        try:
            targeted_candidates.extend(
                _extract_marked_equipment_labels(
                    page,
                    page_number,
                    ocr_engine,
                    config.dpi_ocr_rotulos_inclinados,
                )
            )
        except Exception:
            targeted_diagnostics.append(
                DiagnosticoAnalise(
                    codigo="analise.ocr_equipamentos_marcados_falhou",
                    mensagem=(
                        "A leitura localizada de equipamentos em caixas ou riscados falhou; "
                        "os demais resultados de OCR foram mantidos."
                    ),
                    extrator="ocr-equipamentos-marcados",
                    pagina_numero=page_number,
                )
            )
    return (
        _deduplicate_tiled_candidates((*candidates, *targeted_candidates)),
        tuple(targeted_diagnostics),
    )


def _extract_ocr(
    page: Any, page_number: int, engine: MotorOcrPort, dpi: int
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    return _extract_ocr_region(
        page,
        page_number,
        engine,
        dpi,
        bounds=(Decimal(0), Decimal(0), Decimal(1), Decimal(1)),
        stable_suffix="pagina",
    )


def _extract_ocr_tiled(
    page: Any,
    page_number: int,
    engine: MotorOcrPort,
    dpi: int,
    *,
    divisions: int,
    overlap: Decimal,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    step = Decimal(1) / Decimal(divisions)
    candidates = tuple(
        candidate
        for row in range(divisions)
        for column in range(divisions)
        for candidate in _extract_ocr_region(
            page,
            page_number,
            engine,
            dpi,
            bounds=(
                max(Decimal(0), Decimal(column) * step - overlap),
                max(Decimal(0), Decimal(row) * step - overlap),
                min(Decimal(1), Decimal(column + 1) * step + overlap),
                min(Decimal(1), Decimal(row + 1) * step + overlap),
            ),
            stable_suffix=f"bloco:{row}:{column}",
        )
    )
    return _deduplicate_tiled_candidates(candidates)


def _extract_point_identifiers(
    page: Any,
    page_number: int,
    engine: MotorOcrIdentificadorPort,
    dpi: int,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    candidates: list[CandidatoEvidenciaDocumento] = []
    for index, bounds in enumerate(_red_circle_bounds(page)):
        pixmap = _render_bounds(page, _padded_bounds(bounds), dpi)
        raster = _blue_only_raster(pixmap, page_number, dpi)
        recognized = list(engine.reconhecer_identificador(raster))
        rotation = _identifier_rotation_degrees(raster)
        if rotation:
            recognized.extend(engine.reconhecer_identificador(_rotate_raster(raster, rotation)))
        best = max(
            (
                (match, item)
                for item in recognized
                if (match := _POINT_IDENTIFIER_PATTERN.fullmatch(item.texto.strip())) is not None
                and item.confianca is not None
                and Decimal(str(item.confianca)) >= _MINIMUM_POINT_IDENTIFIER_CONFIDENCE
            ),
            key=lambda pair: pair[1].confianca or 0,
            default=None,
        )
        if best is None:
            continue
        match, item = best
        point_number = int(match.group(1))
        if point_number == 0:
            continue
        confidence = Decimal(str(item.confianca))
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=f"p{page_number}:ocr-identificador:{index}:P{point_number}",
                pagina_numero=page_number,
                tipo=TipoEvidencia.OCR,
                geometria=GeometriaNormalizada(
                    tipo=TipoGeometria.CAIXA,
                    pontos=(
                        _normalized_point(float(bounds[0]), float(bounds[1])),
                        _normalized_point(float(bounds[2]), float(bounds[3])),
                    ),
                ),
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=f"P{point_number}",
                atributos_extraidos=_extras(
                    motor_ocr="tesseract-identificador-localizado",
                    confianca=confidence,
                    dpi=dpi,
                    pre_processamento="isolamento_azul_em_circulo_vermelho",
                ),
            )
        )
        if isinstance(engine, MotorOcrRotuloOperacionalPort):
            candidates.extend(
                _extract_operational_labels_near_point(
                    page,
                    page_number,
                    engine,
                    dpi,
                    point_bounds=bounds,
                    point_index=index,
                )
            )
    return tuple(candidates)


def _extract_blue_operational_identifiers(
    page: Any,
    page_number: int,
    engine: MotorOcrRotuloOperacionalPort,
    dpi: int,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    """Leia Pn e Vn-m diretamente dos grupos de glifos vetoriais azuis."""
    candidates: list[CandidatoEvidenciaDocumento] = []
    for index, bounds in enumerate(_blue_glyph_group_bounds(page)):
        raster = _blue_only_raster(
            _render_bounds(page, _expanded_bounds(bounds, Decimal("0.45")), dpi),
            page_number,
            dpi,
        )
        recognized = list(engine.reconhecer_rotulo_operacional(raster))
        rotation = _identifier_rotation_degrees(raster)
        if rotation:
            recognized.extend(
                engine.reconhecer_rotulo_operacional(_rotate_raster(raster, rotation))
            )
            recognized.extend(
                engine.reconhecer_rotulo_operacional(_rotate_raster(raster, rotation + 180))
            )
        valid = tuple(
            (value, item)
            for item in recognized
            if item.texto.strip()
            and item.confianca is not None
            and Decimal(str(item.confianca)) >= _MINIMUM_TARGETED_IDENTIFIER_CONFIDENCE
            and (value := _normalize_targeted_identifier(item.texto)) is not None
        )
        if not valid:
            continue
        value, best = max(
            valid,
            key=lambda pair: (
                pair[1].confianca or 0,
                len(pair[0]),
                pair[0],
            ),
        )
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=f"p{page_number}:ocr-identificador-vetorial:{index}:{value}",
                pagina_numero=page_number,
                tipo=TipoEvidencia.OCR,
                geometria=_geometry_from_bounds(bounds),
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=value,
                atributos_extraidos=_extras(
                    motor_ocr="tesseract-identificador-vetorial-localizado",
                    confianca=Decimal(str(best.confianca)),
                    dpi=dpi,
                    rotacao_aplicada_graus=Decimal(str(round(rotation, 3))),
                    pre_processamento="agrupamento_de_glifos_azuis_vetoriais",
                ),
            )
        )
    return tuple(candidates)


def _extract_linear_operational_labels(
    page: Any,
    page_number: int,
    engine: MotorOcrPort,
    dpi: int,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    """Retifique caixas verdes inclinadas e leia códigos e comprimentos de cabos."""
    frames = _linear_cable_frames(page)
    candidates: list[CandidatoEvidenciaDocumento] = []
    for index, frame in enumerate(frames):
        rectified = _rectified_frame_region(
            page,
            page_number,
            frame,
            dpi,
            isolate="green",
            padding=True,
        )
        recognized = list(engine.reconhecer(rectified.raster))
        if isinstance(engine, MotorOcrRotuloOperacionalPort):
            recognized.extend(engine.reconhecer_rotulo_operacional(rectified.raster))
        valid_labels = tuple(
            (normalized, item)
            for item in recognized
            if item.texto.strip()
            and (normalized := _normalize_operational_label_text(item.texto))
            and _is_cable_operational_label(normalized)
        )
        if valid_labels:
            label, best = max(
                valid_labels,
                key=lambda pair: (
                    pair[1].confianca or 0,
                    len(pair[0]),
                    pair[0],
                ),
            )
            confidence = Decimal(str(best.confianca)) if best.confianca is not None else Decimal(0)
            candidates.append(
                CandidatoEvidenciaDocumento(
                    chave_estavel=f"p{page_number}:ocr-rotulo-linear:{index}:{label}",
                    pagina_numero=page_number,
                    tipo=TipoEvidencia.OCR,
                    geometria=_geometry_from_bounds(frame.bounds),
                    origem_pdf=OrigemObjetoPdf(),
                    conteudo_bruto=label,
                    atributos_extraidos=_extras(
                        motor_ocr="tesseract-rotulo-linear-retificado",
                        confianca=confidence,
                        dpi=dpi,
                        rotacao_original_graus=Decimal(
                            str(
                                round(
                                    degrees(
                                        atan2(
                                            frame.horizontal_axis[1],
                                            frame.horizontal_axis[0],
                                        )
                                    ),
                                    3,
                                )
                            )
                        ),
                        pre_processamento="retificacao_afim_e_isolamento_verde",
                    ),
                )
            )
        if frame.width_points < 12:
            continue
        neighborhood = _rectified_frame_region(
            page,
            page_number,
            frame,
            dpi,
            horizontal_start=-0.5,
            horizontal_span=2.0,
            vertical_start=-4.0,
            vertical_span=9.0,
            isolate="neutral-dark",
            padding=True,
        )
        length_matches = tuple(
            (match, item)
            for item in engine.reconhecer(neighborhood.raster)
            if item.texto.strip()
            and (match := _SPAN_LENGTH_PATTERN.search(item.texto.upper())) is not None
        )
        if not length_matches:
            continue
        match, best_length = max(
            length_matches,
            key=lambda pair: (
                pair[1].confianca or 0,
                len(pair[1].texto),
            ),
        )
        length_text = f"{int(match.group(1))}m VR:{int(match.group(2))}m"
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=f"p{page_number}:ocr-comprimento-linear:{index}:{length_text}",
                pagina_numero=page_number,
                tipo=TipoEvidencia.OCR,
                geometria=_geometry_from_rectified_ocr(neighborhood, best_length, page),
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=length_text,
                atributos_extraidos=_extras(
                    motor_ocr="tesseract-comprimento-linear-retificado",
                    confianca=(
                        Decimal(str(best_length.confianca))
                        if best_length.confianca is not None
                        else None
                    ),
                    dpi=dpi,
                    pre_processamento="retificacao_afim_e_isolamento_neutro_escuro",
                ),
            )
        )
    return tuple(candidates)


def _extract_marked_equipment_labels(
    page: Any,
    page_number: int,
    engine: MotorOcrBlocoOperacionalPort,
    dpi: int,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    """Leia equipamentos dentro de caixas vinho e sob traços de remoção."""
    candidates: list[CandidatoEvidenciaDocumento] = []
    markers: list[tuple[str, _OperationalFrame | tuple[Decimal, Decimal, Decimal, Decimal]]] = [
        ("INSTALAR", frame) for frame in _equipment_bubble_frames(page)
    ]
    markers.extend(("REMOVER", bounds) for bounds in _equipment_strike_bounds(page))
    for index, (situation, marker) in enumerate(markers):
        if isinstance(marker, _OperationalFrame):
            region = _rectified_frame_region(
                page,
                page_number,
                marker,
                dpi,
                isolate="neutral-dark",
                padding=True,
            )
            raster = _flip_raster_vertically(region.raster)
            bounds = marker.bounds
            preprocessing = "retificacao_de_bolha_vinho_e_isolamento_neutro"
        else:
            bounds = marker
            raster = _neutral_dark_raster(
                _render_bounds(page, _equipment_strike_crop(bounds), dpi),
                page_number,
                dpi,
                padding=True,
            )
            preprocessing = "remocao_de_traco_vinho_e_isolamento_neutro"
        recognized = tuple(
            (normalized, item)
            for item in engine.reconhecer_bloco_operacional(raster)
            if item.texto.strip()
            and (normalized := _normalize_equipment_ocr_text(item.texto)) is not None
        )
        if not recognized:
            continue
        label, best = max(
            recognized,
            key=lambda pair: (
                pair[1].confianca or 0,
                len(pair[0]),
                pair[0],
            ),
        )
        confidence = Decimal(str(best.confianca)) if best.confianca is not None else Decimal(0)
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=(
                    f"p{page_number}:ocr-equipamento-marcado:{index}:{situation}:{label}"
                ),
                pagina_numero=page_number,
                tipo=TipoEvidencia.OCR,
                geometria=_geometry_from_bounds(bounds),
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=label,
                atributos_extraidos=_extras(
                    motor_ocr="tesseract-equipamento-marcado-localizado",
                    confianca=confidence,
                    dpi=dpi,
                    pre_processamento=preprocessing,
                    situacao_projeto_forcada=situation,
                ),
            )
        )
    return tuple(candidates)


def _normalize_equipment_ocr_text(text: str) -> str | None:
    normalized = "".join(text.upper().split())
    match = _EQUIPMENT_OCR_PATTERN.search(normalized)
    if match is None:
        return None
    numeric = tuple(
        group.translate(_NUMERIC_OCR_TRANSLATION).replace("T", "1") for group in match.groups()[:3]
    )
    if any(not value.isdigit() for value in numeric):
        return None
    return f"{int(numeric[0])}A/{int(numeric[1])}KA/{int(numeric[2])}{match.group(4).upper()}"


def _extract_operational_labels_near_point(
    page: Any,
    page_number: int,
    engine: MotorOcrRotuloOperacionalPort,
    dpi: int,
    *,
    point_bounds: tuple[Decimal, Decimal, Decimal, Decimal],
    point_index: int,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    candidates = []
    green_bounds = _green_label_bounds(page, point_bounds)
    for label_index, bounds in enumerate(green_bounds):
        pixmap = _render_bounds(page, _inset_bounds(bounds, Decimal("0.02")), dpi)
        raster = _green_only_raster(pixmap, page_number, dpi)
        best = max(
            (
                item
                for item in engine.reconhecer_rotulo_operacional(raster)
                if item.texto.strip()
                and item.confianca is not None
                and Decimal(str(item.confianca)) >= _MINIMUM_OPERATIONAL_LABEL_CONFIDENCE
            ),
            key=lambda item: item.confianca or 0,
            default=None,
        )
        if best is None:
            continue
        confidence = Decimal(str(best.confianca))
        recognized_text = _normalize_operational_label_text(best.texto)
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=(
                    f"p{page_number}:ocr-rotulo-operacional:"
                    f"{point_index}:{label_index}:{recognized_text}"
                ),
                pagina_numero=page_number,
                tipo=TipoEvidencia.OCR,
                geometria=GeometriaNormalizada(
                    tipo=TipoGeometria.CAIXA,
                    pontos=(
                        _normalized_point(float(bounds[0]), float(bounds[1])),
                        _normalized_point(float(bounds[2]), float(bounds[3])),
                    ),
                ),
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=recognized_text,
                atributos_extraidos=_extras(
                    motor_ocr="tesseract-rotulo-operacional-localizado",
                    confianca=confidence,
                    dpi=dpi,
                    pre_processamento="isolamento_verde_em_caixa_vetorial",
                ),
            )
        )
    if not green_bounds and isinstance(engine, MotorOcrBlocoOperacionalPort):
        candidates.extend(
            _extract_unboxed_operational_labels_near_point(
                page,
                page_number,
                engine,
                dpi,
                point_bounds=point_bounds,
                point_index=point_index,
            )
        )
    return tuple(candidates)


def _extract_unboxed_operational_labels_near_point(
    page: Any,
    page_number: int,
    engine: MotorOcrBlocoOperacionalPort,
    dpi: int,
    *,
    point_bounds: tuple[Decimal, Decimal, Decimal, Decimal],
    point_index: int,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    point_left, _point_top, point_right, point_bottom = point_bounds
    point_width = point_right - point_left
    point_height = point_bounds[3] - point_bounds[1]
    point_center_x = (point_left + point_right) / 2
    bounds = (
        max(Decimal(0), point_center_x - point_width * Decimal("1.80")),
        max(Decimal(0), point_bottom - point_height * Decimal("0.05")),
        min(Decimal(1), point_center_x + point_width * Decimal("1.80")),
        min(Decimal(1), point_bottom + point_height * Decimal("3.00")),
    )
    raster = _dark_only_raster(
        _render_bounds(page, bounds, dpi),
        page_number,
        dpi,
    )
    candidates = []
    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    for label_index, item in enumerate(engine.reconhecer_bloco_operacional(raster)):
        if (
            not item.texto.strip()
            or item.confianca is None
            or Decimal(str(item.confianca)) < _MINIMUM_OPERATIONAL_LABEL_CONFIDENCE
        ):
            continue
        recognized_text = _normalize_operational_label_text(item.texto)
        x0, y0, x1, y1 = item.caixa_normalizada
        geometry = GeometriaNormalizada(
            tipo=TipoGeometria.CAIXA,
            pontos=(
                _normalized_point(
                    float(left + Decimal(str(x0)) * width),
                    float(top + Decimal(str(y0)) * height),
                ),
                _normalized_point(
                    float(left + Decimal(str(x1)) * width),
                    float(top + Decimal(str(y1)) * height),
                ),
            ),
        )
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=(
                    f"p{page_number}:ocr-bloco-operacional:"
                    f"{point_index}:{label_index}:{recognized_text}"
                ),
                pagina_numero=page_number,
                tipo=TipoEvidencia.OCR,
                geometria=geometry,
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=recognized_text,
                atributos_extraidos=_extras(
                    motor_ocr="tesseract-bloco-operacional-localizado",
                    confianca=Decimal(str(item.confianca)),
                    dpi=dpi,
                    pre_processamento="isolamento_escuro_abaixo_do_ponto",
                ),
            )
        )
    return tuple(candidates)


def _normalize_operational_label_text(text: str) -> str:
    normalized = "".join(text.upper().split()).replace("“", '"').replace("”", '"')
    if _NUMERIC_OPERATIONAL_LABEL_PATTERN.fullmatch(normalized):
        return normalized.translate(_NUMERIC_OCR_TRANSLATION)
    if messenger := _MESSENGER_CABLE_PATTERN.fullmatch(normalized):
        return f'{messenger.group(1)}")'
    if neutral := _NEUTRAL_CABLE_PATTERN.fullmatch(normalized):
        designation = neutral.group(1)
        material = re.fullmatch(r"(\d{1,2}(?:/\d{1,2})?)(CAA|CA)", designation)
        if material is not None:
            return f"N-({material.group(1)} {material.group(2)})"
        return f"N- ({designation})"
    if insulated := _INSULATED_CABLE_PATTERN.fullmatch(normalized):
        return insulated.group(1)
    return normalized


def _normalize_targeted_identifier(text: str) -> str | None:
    normalized = "".join(text.upper().split())
    normalized = normalized.replace("/-", "-").replace("--", "-")
    point = _POINT_IDENTIFIER_PATTERN.fullmatch(normalized)
    if point is not None:
        number = int(point.group(1))
        return f"P{number}" if number else None
    span = _TARGETED_SPAN_IDENTIFIER_PATTERN.fullmatch(normalized)
    if span is None:
        return None
    origin = int(span.group(1))
    destination = int(span.group(2))
    if not origin or not destination or origin == destination:
        return None
    return f"V{origin}-{destination}"


def _is_cable_operational_label(text: str) -> bool:
    return any(
        pattern.fullmatch(text) is not None
        for pattern in (
            _CANONICAL_MESSENGER_CABLE_PATTERN,
            _CANONICAL_NEUTRAL_CABLE_PATTERN,
            _CANONICAL_INSULATED_CABLE_PATTERN,
        )
    )


def _geometry_from_bounds(
    bounds: tuple[Decimal, Decimal, Decimal, Decimal],
) -> GeometriaNormalizada:
    left, top, right, bottom = bounds
    return GeometriaNormalizada(
        tipo=TipoGeometria.CAIXA,
        pontos=(
            _normalized_point(float(left), float(top)),
            _normalized_point(float(right), float(bottom)),
        ),
    )


def _expanded_bounds(
    bounds: tuple[Decimal, Decimal, Decimal, Decimal],
    factor: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    left, top, right, bottom = bounds
    padding = max(right - left, bottom - top) * factor
    return (
        max(Decimal(0), left - padding),
        max(Decimal(0), top - padding),
        min(Decimal(1), right + padding),
        min(Decimal(1), bottom + padding),
    )


def _blue_glyph_group_bounds(
    page: Any,
) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...]:
    page_rect = page.rect
    glyphs: list[tuple[float, float, float, float]] = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        rectangle = drawing.get("rect")
        if fill is None or rectangle is None:
            continue
        is_blue = (
            float(fill[2]) >= 0.25
            and float(fill[2]) - float(fill[0]) >= 0.20
            and float(fill[2]) - float(fill[1]) >= 0.12
        )
        bounds = (
            float(rectangle.x0 / page_rect.width),
            float(rectangle.y0 / page_rect.height),
            float(rectangle.x1 / page_rect.width),
            float(rectangle.y1 / page_rect.height),
        )
        if is_blue and bounds[2] - bounds[0] <= 0.012 and bounds[3] - bounds[1] <= 0.010:
            glyphs.append(bounds)
    parents = list(range(len(glyphs)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    for left_index, left in enumerate(glyphs):
        for right_index in range(left_index + 1, len(glyphs)):
            right = glyphs[right_index]
            height = max(left[3] - left[1], right[3] - right[1])
            x_gap = max(0.0, left[0] - right[2], right[0] - left[2])
            y_gap = max(0.0, left[1] - right[3], right[1] - left[3])
            center_y_gap = abs((left[1] + left[3] - right[1] - right[3]) / 2)
            if x_gap <= height * 0.75 and y_gap <= height * 0.50 and center_y_gap <= height * 0.80:
                union(left_index, right_index)
    groups: dict[int, list[tuple[float, float, float, float]]] = {}
    for index, bounds in enumerate(glyphs):
        groups.setdefault(find(index), []).append(bounds)
    result = []
    for group in groups.values():
        if len(group) < 2:
            continue
        result.append(
            (
                Decimal(str(min(item[0] for item in group))),
                Decimal(str(min(item[1] for item in group))),
                Decimal(str(max(item[2] for item in group))),
                Decimal(str(max(item[3] for item in group))),
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda bounds: (
                bounds[1],
                bounds[0],
                bounds[3],
                bounds[2],
            ),
        )
    )


def _linear_cable_frames(page: Any) -> tuple[_OperationalFrame, ...]:
    all_frames = tuple(
        frame
        for drawing in page.get_drawings()
        if (frame := _operational_frame(page, drawing)) is not None
    )
    primary = tuple(frame for frame in all_frames if frame.width_points >= 12)
    selected = tuple(
        frame
        for frame in all_frames
        if frame in primary
        or any(
            hypot(
                frame.center[0] - candidate.center[0],
                frame.center[1] - candidate.center[1],
            )
            <= 18
            for candidate in primary
        )
    )
    return tuple(
        sorted(
            selected,
            key=lambda frame: (
                frame.bounds[1],
                frame.bounds[0],
                frame.bounds[3],
                frame.bounds[2],
            ),
        )
    )


def _equipment_bubble_frames(page: Any) -> tuple[_OperationalFrame, ...]:
    frames = tuple(
        frame
        for drawing in page.get_drawings()
        if (frame := _equipment_bubble_frame(page, drawing)) is not None
    )
    return tuple(
        sorted(
            frames,
            key=lambda frame: (
                frame.bounds[1],
                frame.bounds[0],
                frame.bounds[3],
                frame.bounds[2],
            ),
        )
    )


def _equipment_bubble_frame(
    page: Any,
    drawing: dict[str, Any],
) -> _OperationalFrame | None:
    color = drawing.get("color")
    rectangle = drawing.get("rect")
    items: tuple[Any, ...] = tuple(drawing.get("items") or ())
    if (
        color is None
        or rectangle is None
        or len(items) != 1
        or not _is_dark_red_color(color)
        or items[0][0] not in {"re", "qu"}
    ):
        return None
    shape = items[0][1]
    if items[0][0] == "qu":
        upper_left, upper_right, lower_left = shape.ul, shape.ur, shape.ll
    else:
        upper_left, upper_right, lower_left = shape.tl, shape.tr, shape.bl
    top_axis = (
        float(upper_right.x - upper_left.x),
        float(upper_right.y - upper_left.y),
    )
    side_axis = (
        float(lower_left.x - upper_left.x),
        float(lower_left.y - upper_left.y),
    )
    top_length = hypot(*top_axis)
    side_length = hypot(*side_axis)
    width = max(top_length, side_length)
    height = min(top_length, side_length)
    if not (15 <= width <= 80 and 2 <= height <= 12 and width / height >= 2.2):
        return None
    horizontal_axis, vertical_axis = (
        (side_axis, top_axis) if side_length > top_length else (top_axis, side_axis)
    )
    page_rect = page.rect
    return _OperationalFrame(
        bounds=(
            Decimal(str(rectangle.x0 / page_rect.width)),
            Decimal(str(rectangle.y0 / page_rect.height)),
            Decimal(str(rectangle.x1 / page_rect.width)),
            Decimal(str(rectangle.y1 / page_rect.height)),
        ),
        origin=(float(upper_left.x), float(upper_left.y)),
        horizontal_axis=horizontal_axis,
        vertical_axis=vertical_axis,
        width_points=width,
        height_points=height,
    )


def _equipment_strike_bounds(
    page: Any,
) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...]:
    page_rect = page.rect
    result = []
    for drawing in page.get_drawings():
        color = drawing.get("color")
        rectangle = drawing.get("rect")
        items: tuple[Any, ...] = tuple(drawing.get("items") or ())
        if (
            color is None
            or rectangle is None
            or len(items) != 1
            or items[0][0] != "l"
            or not _is_dark_red_color(color)
        ):
            continue
        width = Decimal(str(rectangle.width / page_rect.width))
        height = Decimal(str(rectangle.height / page_rect.height))
        if not (
            Decimal("0.015") <= width <= Decimal("0.12")
            and height <= Decimal("0.005")
            and width / max(height, Decimal("0.00001")) >= Decimal(8)
        ):
            continue
        result.append(
            (
                Decimal(str(rectangle.x0 / page_rect.width)),
                Decimal(str(rectangle.y0 / page_rect.height)),
                Decimal(str(rectangle.x1 / page_rect.width)),
                Decimal(str(rectangle.y1 / page_rect.height)),
            )
        )
    return tuple(
        sorted(
            set(result),
            key=lambda bounds: (
                bounds[1],
                bounds[0],
                bounds[3],
                bounds[2],
            ),
        )
    )


def _is_dark_red_color(color: Any) -> bool:
    return 0.35 <= float(color[0]) <= 0.65 and float(color[1]) <= 0.15 and float(color[2]) <= 0.15


def _equipment_strike_crop(
    bounds: tuple[Decimal, Decimal, Decimal, Decimal],
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    left, top, right, bottom = bounds
    horizontal_padding = max(Decimal("0.004"), (right - left) * Decimal("0.12"))
    return (
        max(Decimal(0), left - horizontal_padding),
        max(Decimal(0), top - Decimal("0.007")),
        min(Decimal(1), right + horizontal_padding),
        min(Decimal(1), bottom + Decimal("0.006")),
    )


def _operational_frame(page: Any, drawing: dict[str, Any]) -> _OperationalFrame | None:
    color = drawing.get("color")
    rectangle = drawing.get("rect")
    items: tuple[Any, ...] = tuple(drawing.get("items") or ())
    if color is None or rectangle is None or len(items) != 1:
        return None
    if not (
        float(color[1]) >= 0.30
        and float(color[1]) - float(color[0]) >= 0.20
        and float(color[1]) - float(color[2]) >= 0.20
        and items[0][0] in {"re", "qu"}
    ):
        return None
    shape = items[0][1]
    if items[0][0] == "qu":
        upper_left, upper_right, lower_left = shape.ul, shape.ur, shape.ll
    else:
        upper_left, upper_right, lower_left = shape.tl, shape.tr, shape.bl
    top_axis = (
        float(upper_right.x - upper_left.x),
        float(upper_right.y - upper_left.y),
    )
    side_axis = (
        float(lower_left.x - upper_left.x),
        float(lower_left.y - upper_left.y),
    )
    top_length = hypot(*top_axis)
    side_length = hypot(*side_axis)
    width = max(top_length, side_length)
    height = min(top_length, side_length)
    if not (7 <= width <= 22 and 2 <= height <= 6 and width / height >= 2.2):
        return None
    horizontal_axis, vertical_axis = (
        (side_axis, top_axis) if side_length > top_length else (top_axis, side_axis)
    )
    page_rect = page.rect
    return _OperationalFrame(
        bounds=(
            Decimal(str(rectangle.x0 / page_rect.width)),
            Decimal(str(rectangle.y0 / page_rect.height)),
            Decimal(str(rectangle.x1 / page_rect.width)),
            Decimal(str(rectangle.y1 / page_rect.height)),
        ),
        origin=(float(upper_left.x), float(upper_left.y)),
        horizontal_axis=horizontal_axis,
        vertical_axis=vertical_axis,
        width_points=width,
        height_points=height,
    )


def _rectified_frame_region(
    page: Any,
    page_number: int,
    frame: _OperationalFrame,
    dpi: int,
    *,
    horizontal_start: float = 0,
    horizontal_span: float = 1,
    vertical_start: float = 0,
    vertical_span: float = 1,
    isolate: str,
    padding: bool,
) -> _RectifiedRegion:
    origin = (
        frame.origin[0]
        + horizontal_start * frame.horizontal_axis[0]
        + vertical_start * frame.vertical_axis[0],
        frame.origin[1]
        + horizontal_start * frame.horizontal_axis[1]
        + vertical_start * frame.vertical_axis[1],
    )
    horizontal_axis = (
        horizontal_span * frame.horizontal_axis[0],
        horizontal_span * frame.horizontal_axis[1],
    )
    vertical_axis = (
        vertical_span * frame.vertical_axis[0],
        vertical_span * frame.vertical_axis[1],
    )
    corners = (
        origin,
        (origin[0] + horizontal_axis[0], origin[1] + horizontal_axis[1]),
        (origin[0] + vertical_axis[0], origin[1] + vertical_axis[1]),
        (
            origin[0] + horizontal_axis[0] + vertical_axis[0],
            origin[1] + horizontal_axis[1] + vertical_axis[1],
        ),
    )
    clip = pymupdf.Rect(
        min(point[0] for point in corners) - 1,
        min(point[1] for point in corners) - 1,
        max(point[0] for point in corners) + 1,
        max(point[1] for point in corners) + 1,
    )
    pixmap = page.get_pixmap(
        dpi=dpi,
        colorspace=pymupdf.csRGB,
        alpha=False,
        annots=True,
        clip=clip,
    )
    source = Image.frombytes("RGB", (pixmap.width, pixmap.height), bytes(pixmap.samples))
    scale = dpi / 72
    width_pixels = max(1, round(hypot(*horizontal_axis) * scale))
    height_pixels = max(1, round(hypot(*vertical_axis) * scale))
    coefficients = (
        horizontal_axis[0] * scale / width_pixels,
        vertical_axis[0] * scale / height_pixels,
        origin[0] * scale - pixmap.x,
        horizontal_axis[1] * scale / width_pixels,
        vertical_axis[1] * scale / height_pixels,
        origin[1] * scale - pixmap.y,
    )
    rectified = source.transform(
        (width_pixels, height_pixels),
        Image.Transform.AFFINE,
        coefficients,
        resample=Image.Resampling.BICUBIC,
        fillcolor="white",
    )
    if isolate == "green":
        isolated = _isolated_image(rectified, color="green")
    elif isolate == "neutral-dark":
        isolated = _isolated_image(rectified, color="neutral-dark")
    else:
        raise ValueError(f"Isolamento de OCR desconhecido: {isolate}")
    padding_pixels = max(20, height_pixels) if padding else 0
    if padding_pixels:
        isolated = ImageOps.expand(isolated, border=padding_pixels, fill="white")
    raster = PaginaRasterOcr(
        pagina_numero=page_number,
        largura_pixels=isolated.width,
        altura_pixels=isolated.height,
        stride=isolated.width * 3,
        dados_rgb=isolated.tobytes(),
        dpi=dpi,
    )
    return _RectifiedRegion(
        raster=raster,
        origin=origin,
        horizontal_axis=horizontal_axis,
        vertical_axis=vertical_axis,
        content_width_pixels=width_pixels,
        content_height_pixels=height_pixels,
        padding_pixels=padding_pixels,
    )


def _isolated_image(image: Image.Image, *, color: str) -> Image.Image:
    source = image.convert("RGB").tobytes()
    pixels = bytearray(len(source))
    for offset in range(0, len(source), 3):
        red, green, blue = source[offset : offset + 3]
        selected = (
            green > red + 20 and green > blue + 20 and green > 45
            if color == "green"
            else max(red, green, blue) < 200 and max(red, green, blue) - min(red, green, blue) < 35
        )
        value = 0 if selected else 255
        pixels[offset : offset + 3] = bytes((value, value, value))
    return Image.frombytes("RGB", image.size, bytes(pixels))


def _geometry_from_rectified_ocr(
    region: _RectifiedRegion,
    item: Any,
    page: Any,
) -> GeometriaNormalizada:
    x0, y0, x1, y1 = item.caixa_normalizada
    padding = region.padding_pixels
    raster_width = region.raster.largura_pixels
    raster_height = region.raster.altura_pixels

    def fraction(value: float, raster_size: int, content_size: int) -> float:
        return min(1.0, max(0.0, (value * raster_size - padding) / content_size))

    left = fraction(x0, raster_width, region.content_width_pixels)
    top = fraction(y0, raster_height, region.content_height_pixels)
    right = fraction(x1, raster_width, region.content_width_pixels)
    bottom = fraction(y1, raster_height, region.content_height_pixels)
    page_points = tuple(
        (
            region.origin[0]
            + horizontal * region.horizontal_axis[0]
            + vertical * region.vertical_axis[0],
            region.origin[1]
            + horizontal * region.horizontal_axis[1]
            + vertical * region.vertical_axis[1],
        )
        for horizontal, vertical in (
            (left, top),
            (right, top),
            (right, bottom),
            (left, bottom),
        )
    )
    page_rect = page.rect
    bounds = (
        Decimal(str((min(point[0] for point in page_points) - page_rect.x0) / page_rect.width)),
        Decimal(str((min(point[1] for point in page_points) - page_rect.y0) / page_rect.height)),
        Decimal(str((max(point[0] for point in page_points) - page_rect.x0) / page_rect.width)),
        Decimal(str((max(point[1] for point in page_points) - page_rect.y0) / page_rect.height)),
    )
    return _geometry_from_bounds(bounds)


def _green_label_bounds(
    page: Any,
    point_bounds: tuple[Decimal, Decimal, Decimal, Decimal],
) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...]:
    page_rect = page.rect
    point_left, _point_top, point_right, point_bottom = point_bounds
    point_width = point_right - point_left
    point_height = point_bounds[3] - point_bounds[1]
    point_center_x = (point_left + point_right) / 2
    result = []
    for drawing in page.get_drawings():
        color = drawing.get("color")
        items: tuple[Any, ...] = tuple(drawing.get("items") or ())
        rectangle = drawing.get("rect")
        if color is None or rectangle is None or len(items) != 1:
            continue
        is_green = (
            Decimal(str(color[1])) >= Decimal("0.30")
            and Decimal(str(color[1])) - Decimal(str(color[0])) >= Decimal("0.20")
            and Decimal(str(color[1])) - Decimal(str(color[2])) >= Decimal("0.20")
        )
        if not is_green or items[0][0] not in {"re", "qu"}:
            continue
        bounds = (
            Decimal(str(rectangle.x0 / page_rect.width)),
            Decimal(str(rectangle.y0 / page_rect.height)),
            Decimal(str(rectangle.x1 / page_rect.width)),
            Decimal(str(rectangle.y1 / page_rect.height)),
        )
        left, top, right, bottom = bounds
        width = right - left
        height = bottom - top
        center_x = (left + right) / 2
        if not (
            point_width * Decimal("0.50") <= width <= point_width * Decimal("2.00")
            and point_height * Decimal("0.25") <= height <= point_height * Decimal("0.80")
            and abs(center_x - point_center_x) <= point_width * Decimal("0.60")
            and point_bottom - point_height * Decimal("0.10") <= top
            and bottom <= point_bottom + point_height * Decimal("2.50")
        ):
            continue
        result.append(bounds)
    return tuple(
        sorted(
            set(result),
            key=lambda bounds: (
                bounds[1],
                bounds[0],
                bounds[3],
                bounds[2],
            ),
        )
    )


def _red_circle_bounds(
    page: Any,
) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...]:
    page_rect = page.rect
    result = []
    for drawing in page.get_drawings():
        color = drawing.get("color")
        items = drawing.get("items") or ()
        rectangle = drawing.get("rect")
        if color is None or rectangle is None:
            continue
        width = Decimal(str(rectangle.width / page_rect.width))
        height = Decimal(str(rectangle.height / page_rect.height))
        is_dark_red = (
            Decimal("0.35") <= Decimal(str(color[0])) <= Decimal("0.65")
            and Decimal(str(color[1])) <= Decimal("0.15")
            and Decimal(str(color[2])) <= Decimal("0.15")
        )
        is_ellipse = len(items) == 4 and all(item[0] == "c" for item in items)
        if not (
            is_dark_red
            and is_ellipse
            and Decimal("0.008") <= width <= Decimal("0.020")
            and Decimal("0.006") <= height <= Decimal("0.015")
        ):
            continue
        result.append(
            (
                Decimal(str(rectangle.x0 / page_rect.width)),
                Decimal(str(rectangle.y0 / page_rect.height)),
                Decimal(str(rectangle.x1 / page_rect.width)),
                Decimal(str(rectangle.y1 / page_rect.height)),
            )
        )
    return tuple(result)


def _padded_bounds(
    bounds: tuple[Decimal, Decimal, Decimal, Decimal],
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    left, top, right, bottom = bounds
    horizontal_padding = (right - left) * Decimal("0.12")
    vertical_padding = (bottom - top) * Decimal("0.15")
    return (
        max(Decimal(0), left - horizontal_padding),
        max(Decimal(0), top - vertical_padding),
        min(Decimal(1), right + horizontal_padding),
        min(Decimal(1), bottom + vertical_padding),
    )


def _inset_bounds(
    bounds: tuple[Decimal, Decimal, Decimal, Decimal],
    factor: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    return (
        left + width * factor,
        top + height * factor,
        right - width * factor,
        bottom - height * factor,
    )


def _render_bounds(
    page: Any,
    bounds: tuple[Decimal, Decimal, Decimal, Decimal],
    dpi: int,
) -> Any:
    left, top, right, bottom = bounds
    page_rect = page.rect
    return page.get_pixmap(
        dpi=dpi,
        colorspace=pymupdf.csRGB,
        alpha=False,
        annots=True,
        clip=pymupdf.Rect(
            page_rect.x0 + float(left) * page_rect.width,
            page_rect.y0 + float(top) * page_rect.height,
            page_rect.x0 + float(right) * page_rect.width,
            page_rect.y0 + float(bottom) * page_rect.height,
        ),
    )


def _blue_only_raster(pixmap: Any, page_number: int, dpi: int) -> PaginaRasterOcr:
    source = bytes(pixmap.samples)
    pixels = bytearray(len(source))
    for offset in range(0, len(source), 3):
        red, green, blue = source[offset : offset + 3]
        value = 0 if blue > red + 50 and blue > green + 50 else 255
        pixels[offset : offset + 3] = bytes((value, value, value))
    return PaginaRasterOcr(
        pagina_numero=page_number,
        largura_pixels=pixmap.width,
        altura_pixels=pixmap.height,
        stride=pixmap.stride,
        dados_rgb=bytes(pixels),
        dpi=dpi,
    )


def _green_only_raster(pixmap: Any, page_number: int, dpi: int) -> PaginaRasterOcr:
    source = bytes(pixmap.samples)
    pixels = bytearray(len(source))
    for offset in range(0, len(source), 3):
        red, green, blue = source[offset : offset + 3]
        value = 0 if green > red + 25 and green > blue + 25 and green > 55 else 255
        pixels[offset : offset + 3] = bytes((value, value, value))
    return PaginaRasterOcr(
        pagina_numero=page_number,
        largura_pixels=pixmap.width,
        altura_pixels=pixmap.height,
        stride=pixmap.stride,
        dados_rgb=bytes(pixels),
        dpi=dpi,
    )


def _dark_only_raster(pixmap: Any, page_number: int, dpi: int) -> PaginaRasterOcr:
    source = bytes(pixmap.samples)
    pixels = bytearray(len(source))
    for offset in range(0, len(source), 3):
        red, green, blue = source[offset : offset + 3]
        value = 0 if max(red, green, blue) < 180 else 255
        pixels[offset : offset + 3] = bytes((value, value, value))
    return PaginaRasterOcr(
        pagina_numero=page_number,
        largura_pixels=pixmap.width,
        altura_pixels=pixmap.height,
        stride=pixmap.stride,
        dados_rgb=bytes(pixels),
        dpi=dpi,
    )


def _neutral_dark_raster(
    pixmap: Any,
    page_number: int,
    dpi: int,
    *,
    padding: bool,
) -> PaginaRasterOcr:
    image = _isolated_image(
        Image.frombytes("RGB", (pixmap.width, pixmap.height), bytes(pixmap.samples)),
        color="neutral-dark",
    )
    if padding:
        image = ImageOps.expand(image, border=max(40, image.height), fill="white")
    return PaginaRasterOcr(
        pagina_numero=page_number,
        largura_pixels=image.width,
        altura_pixels=image.height,
        stride=image.width * 3,
        dados_rgb=image.tobytes(),
        dpi=dpi,
    )


def _identifier_rotation_degrees(raster: PaginaRasterOcr) -> float:
    components = _black_components(raster)
    if len(components) < 2:
        return 0
    first = components[0]
    last = components[-1]
    delta_x = last[0] - first[0]
    delta_y = last[1] - first[1]
    if delta_x <= 0:
        return 0
    angle = degrees(atan2(delta_y, delta_x))
    return angle if abs(angle) >= 22 else 0


def _black_components(
    raster: PaginaRasterOcr,
) -> tuple[tuple[float, float], ...]:
    black = {
        (x, y)
        for y in range(raster.altura_pixels)
        for x in range(raster.largura_pixels)
        if raster.dados_rgb[y * raster.stride + x * 3] == 0
    }
    components = []
    while black:
        pending = [black.pop()]
        points = []
        while pending:
            point = pending.pop()
            points.append(point)
            x, y = point
            neighbours = {
                (x + delta_x, y + delta_y)
                for delta_y in (-1, 0, 1)
                for delta_x in (-1, 0, 1)
                if delta_x or delta_y
            }
            connected = neighbours & black
            black.difference_update(connected)
            pending.extend(connected)
        if len(points) >= 10:
            components.append(
                (
                    sum(point[0] for point in points) / len(points),
                    sum(point[1] for point in points) / len(points),
                )
            )
    return tuple(sorted(components))


def _rotate_raster(raster: PaginaRasterOcr, angle: float) -> PaginaRasterOcr:
    rows = b"".join(
        raster.dados_rgb[row * raster.stride : row * raster.stride + raster.largura_pixels * 3]
        for row in range(raster.altura_pixels)
    )
    image = Image.frombytes(
        "RGB",
        (raster.largura_pixels, raster.altura_pixels),
        rows,
    )
    rotated = image.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor="white",
    )
    return PaginaRasterOcr(
        pagina_numero=raster.pagina_numero,
        largura_pixels=rotated.width,
        altura_pixels=rotated.height,
        stride=rotated.width * 3,
        dados_rgb=rotated.tobytes(),
        dpi=raster.dpi,
    )


def _flip_raster_vertically(raster: PaginaRasterOcr) -> PaginaRasterOcr:
    rows = b"".join(
        raster.dados_rgb[row * raster.stride : row * raster.stride + raster.largura_pixels * 3]
        for row in range(raster.altura_pixels)
    )
    image = ImageOps.flip(
        Image.frombytes(
            "RGB",
            (raster.largura_pixels, raster.altura_pixels),
            rows,
        )
    )
    return PaginaRasterOcr(
        pagina_numero=raster.pagina_numero,
        largura_pixels=image.width,
        altura_pixels=image.height,
        stride=image.width * 3,
        dados_rgb=image.tobytes(),
        dpi=raster.dpi,
    )


def _deduplicate_tiled_candidates(
    candidates: tuple[CandidatoEvidenciaDocumento, ...],
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    selected: list[CandidatoEvidenciaDocumento] = []
    for candidate in candidates:
        if _is_operational_label_candidate(candidate):
            selected = [
                current
                for current in selected
                if not (
                    _is_general_ocr_candidate(current)
                    and _is_single_ocr_token(current)
                    and _candidate_centers_are_very_close(current, candidate)
                )
            ]
        duplicate_index = next(
            (
                index
                for index, current in enumerate(selected)
                if _same_ocr_text(current, candidate)
                and _candidate_centers_are_close(current, candidate)
            ),
            None,
        )
        if duplicate_index is None:
            selected.append(candidate)
            continue
        if _ocr_confidence(candidate) > _ocr_confidence(selected[duplicate_index]):
            selected[duplicate_index] = candidate
    return tuple(selected)


def _is_operational_label_candidate(candidate: CandidatoEvidenciaDocumento) -> bool:
    return dict(candidate.atributos_extraidos).get("motor_ocr") in {
        "tesseract-equipamento-marcado-localizado",
        "tesseract-identificador-vetorial-localizado",
        "tesseract-rotulo-linear-retificado",
        "tesseract-rotulo-operacional-localizado",
    }


def _is_general_ocr_candidate(candidate: CandidatoEvidenciaDocumento) -> bool:
    motor = dict(candidate.atributos_extraidos).get("motor_ocr")
    return bool(motor) and motor not in {
        "tesseract-equipamento-marcado-localizado",
        "tesseract-identificador-localizado",
        "tesseract-identificador-vetorial-localizado",
        "tesseract-rotulo-linear-retificado",
        "tesseract-rotulo-operacional-localizado",
    }


def _is_single_ocr_token(candidate: CandidatoEvidenciaDocumento) -> bool:
    return len((candidate.conteudo_bruto or "").split()) == 1


def _same_ocr_text(
    first: CandidatoEvidenciaDocumento,
    second: CandidatoEvidenciaDocumento,
) -> bool:
    return " ".join((first.conteudo_bruto or "").upper().split()) == " ".join(
        (second.conteudo_bruto or "").upper().split()
    )


def _candidate_centers_are_close(
    first: CandidatoEvidenciaDocumento,
    second: CandidatoEvidenciaDocumento,
) -> bool:
    first_bounds = _candidate_bounds(first)
    second_bounds = _candidate_bounds(second)
    return abs(
        (first_bounds[0] + first_bounds[2]) / 2 - (second_bounds[0] + second_bounds[2]) / 2
    ) <= Decimal("0.015") and abs(
        (first_bounds[1] + first_bounds[3]) / 2 - (second_bounds[1] + second_bounds[3]) / 2
    ) <= Decimal("0.015")


def _candidate_centers_are_very_close(
    first: CandidatoEvidenciaDocumento,
    second: CandidatoEvidenciaDocumento,
) -> bool:
    first_bounds = _candidate_bounds(first)
    second_bounds = _candidate_bounds(second)
    return abs(
        (first_bounds[0] + first_bounds[2]) / 2 - (second_bounds[0] + second_bounds[2]) / 2
    ) <= Decimal("0.006") and abs(
        (first_bounds[1] + first_bounds[3]) / 2 - (second_bounds[1] + second_bounds[3]) / 2
    ) <= Decimal("0.003")


def _ocr_confidence(candidate: CandidatoEvidenciaDocumento) -> Decimal:
    value = dict(candidate.atributos_extraidos).get("confianca")
    return Decimal(str(value)) if value is not None else Decimal(0)


def _extract_ocr_region(
    page: Any,
    page_number: int,
    engine: MotorOcrPort,
    dpi: int,
    *,
    bounds: tuple[Decimal, Decimal, Decimal, Decimal],
    stable_suffix: str,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    left, top, right, bottom = bounds
    page_rect = page.rect
    clip = pymupdf.Rect(
        page_rect.x0 + float(left) * page_rect.width,
        page_rect.y0 + float(top) * page_rect.height,
        page_rect.x0 + float(right) * page_rect.width,
        page_rect.y0 + float(bottom) * page_rect.height,
    )
    pixmap = page.get_pixmap(
        dpi=dpi,
        colorspace=pymupdf.csRGB,
        alpha=False,
        annots=True,
        clip=clip,
    )
    raster = PaginaRasterOcr(
        pagina_numero=page_number,
        largura_pixels=pixmap.width,
        altura_pixels=pixmap.height,
        stride=pixmap.stride,
        dados_rgb=bytes(pixmap.samples),
        dpi=dpi,
    )
    candidates = []
    for index, item in enumerate(engine.reconhecer(raster)):
        x0, y0, x1, y1 = item.caixa_normalizada
        width = right - left
        height = bottom - top
        geometry = GeometriaNormalizada(
            tipo=TipoGeometria.CAIXA,
            pontos=(
                _normalized_point(
                    float(left + Decimal(str(x0)) * width),
                    float(top + Decimal(str(y0)) * height),
                ),
                _normalized_point(
                    float(left + Decimal(str(x1)) * width),
                    float(top + Decimal(str(y1)) * height),
                ),
            ),
        )
        confidence = Decimal(str(item.confianca)) if item.confianca is not None else None
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=(
                    f"p{page_number}:ocr:{engine.nome}:{engine.versao}:{stable_suffix}:{index}"
                ),
                pagina_numero=page_number,
                tipo=TipoEvidencia.OCR,
                geometria=geometry,
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=item.texto,
                atributos_extraidos=_extras(
                    motor_ocr=engine.nome,
                    versao_motor_ocr=engine.versao,
                    confianca=confidence,
                    dpi=dpi,
                    recorte_normalizado=",".join(map(str, bounds)),
                ),
            )
        )
    return tuple(candidates)


def _candidate_bounds(
    candidate: CandidatoEvidenciaDocumento,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    x_values = tuple(point.x for point in candidate.geometria.pontos)
    y_values = tuple(point.y for point in candidate.geometria.pontos)
    return min(x_values), min(y_values), max(x_values), max(y_values)


def _candidate_area(candidate: CandidatoEvidenciaDocumento) -> Decimal:
    left, top, right, bottom = _candidate_bounds(candidate)
    return (right - left) * (bottom - top)


def _has_regional_ocr_resolution(candidate: CandidatoEvidenciaDocumento) -> bool:
    attributes = dict(candidate.atributos_extraidos)
    width = int(attributes.get("largura_pixels") or 0)
    height = int(attributes.get("altura_pixels") or 0)
    return min(width, height) >= 16 and width * height >= 4096
