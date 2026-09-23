# mypy: disable-error-code="no-untyped-call"
"""Opt-in raster symbol search over the whole page, independent of vector proposals.

The bundled drawing is an author-owned E02 control. It is not a reproduction of,
or evidence for equivalence to, a normative F02 symbol. Scores are raw image
similarities, never probabilities. OpenCV is an optional experiment.
"""

from __future__ import annotations

import importlib.util
import io
import math
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any

import pymupdf
from PIL import Image, ImageChops

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, TipoGeometria
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    FonteObservacaoSimbolo,
    GeometriaObservacaoSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    ResultadoMetodoSimbolos,
    TransformacaoSimbolo,
)
from zeny_project_handler.domain.values import PontoNormalizado

_VERSION = "e08-raster-3"
_MATCH_THRESHOLD = 0.88
_COARSE_THRESHOLD = 0.72


@dataclass(frozen=True, slots=True, kw_only=True)
class TemplateRasterVerificado:
    id: str
    classe: str
    fonte_referencia: str
    dados_png: bytes
    sha256: str

    def __post_init__(self) -> None:
        if not all((self.id.strip(), self.classe.strip(), self.fonte_referencia.strip())):
            raise ValueError("Template exige identidade, classe e procedência")
        if sha256(self.dados_png).hexdigest() != self.sha256:
            raise ValueError("Hash do template diverge dos bytes PNG")
        with Image.open(io.BytesIO(self.dados_png)) as image:
            if image.format != "PNG" or not (8 <= image.width <= 128 and 8 <= image.height <= 128):
                raise ValueError("Template deve ser PNG entre 8 e 128 pixels por eixo")
            binary = image.convert("L").point(lambda value: 0 if value < 220 else 1)
            values = binary.tobytes()
            if not (0 < values.count(0) < len(values) // 2):
                raise ValueError("Template deve conter traços escuros e fundo claro")


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguracaoDetectorRaster:
    dpi: int = 144
    tile_pixels: int = 768
    sobreposicao_pixels: int = 96
    escalas: tuple[float, ...] = (1.0,)
    rotacoes: tuple[int, ...] = (0, 90, 180, 270)
    limite_candidatos: int = 256
    limite_bytes: int = 64_000_000

    def __post_init__(self) -> None:
        if not 72 <= self.dpi <= 600:
            raise ValueError("DPI deve ficar entre 72 e 600")
        if (
            not 64 <= self.tile_pixels <= 2048
            or not 0 <= self.sobreposicao_pixels < self.tile_pixels
        ):
            raise ValueError("Tile/sobreposição inválidos")
        if not self.escalas or any(not math.isfinite(s) or not 0.5 <= s <= 2 for s in self.escalas):
            raise ValueError("Escalas devem ser finitas entre 0.5 e 2")
        if not self.rotacoes or any(angle not in (0, 90, 180, 270) for angle in self.rotacoes):
            raise ValueError("Rotações devem ser cardinais")
        if self.limite_candidatos < 1 or self.limite_bytes < 1:
            raise ValueError("Orçamentos devem ser positivos")


@dataclass(frozen=True, slots=True)
class _Match:
    template: TemplateRasterVerificado
    method: str
    box: tuple[float, float, float, float]
    score: float
    scale: float
    rotation: int
    tile: tuple[int, int]
    raster_hash: str


_DEFAULT_CONFIG = ConfiguracaoDetectorRaster()


def carregar_templates_raster() -> tuple[TemplateRasterVerificado, ...]:
    """Return versioned E02 author-owned grounding/surge controls, not F02 artwork.

    Geometry duplicates the public fixture generator's `_segments` for these two
    classes, independently of benchmark labels/ROIs and fixture output PDFs.
    The common canvas includes the fourth-bar area in both controls, so absence
    of that bar is visible to the matching score rather than silently cropped.
    """
    templates = []
    for class_code, count, identity in (
        ("ATERRAMENTO", 3, "e02-control-grounding-v2"),
        ("PARA_RAIOS_MT", 4, "e02-control-surge-mt-v1"),
    ):
        document = pymupdf.open()
        try:
            page = document.new_page(width=31, height=13)
            page.draw_line((2, 6.5), (17, 6.5), color=(0, 0, 0), width=0.5)
            for index, length in enumerate((10.0, 7.0, 4.0, 7.0)[:count]):
                x = 17 + index * 4
                page.draw_line(
                    (x, 6.5 - length / 2),
                    (x, 6.5 + length / 2),
                    color=(0, 0, 0),
                    width=0.5,
                )
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(2, 2), colorspace=pymupdf.csRGB, alpha=False
            )
            with Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples) as image:
                stream = io.BytesIO()
                image.save(stream, format="PNG")
                data = stream.getvalue()
        finally:
            document.close()
        templates.append(
            TemplateRasterVerificado(
                id=identity,
                classe=class_code,
                fonte_referencia=(
                    f"E02:tests/symbol_benchmark_fixtures.py:_segments:{class_code}:controle-autoral"
                ),
                dados_png=data,
                sha256=sha256(data).hexdigest(),
            )
        )
    return tuple(templates)


def _profile(
    method: str,
    templates: tuple[TemplateRasterVerificado, ...],
    config: ConfiguracaoDetectorRaster,
    cv_version: str | None,
) -> PerfilMetodoSimbolos:
    source = "pymupdf:rgb-page-tiles:e08"
    return PerfilMetodoSimbolos(
        metodo_id=f"raster-{method}",
        versao=_VERSION,
        familia="raster-templates-e-hough-correlacionados",
        dominio_aplicacao=(
            "Página base rasterizada integralmente; controles autorais ou templates verificados"
        ),
        classes_suportadas=tuple(sorted({item.classe for item in templates})),
        camadas_suportadas=("base",),
        fontes_compartilhadas=(source, "e08:templates-compartilhados"),
        perfil_referencia="E02:controles-autorais;E01:identidades-verificadas",
        parametros=(
            ("dpi", config.dpi),
            ("tile_pixels", config.tile_pixels),
            ("sobreposicao_pixels", config.sobreposicao_pixels),
            ("escalas", ",".join(str(s) for s in config.escalas)),
            ("rotacoes", ",".join(str(r) for r in config.rotacoes)),
            ("limite_candidatos", config.limite_candidatos),
            ("limite_bytes", config.limite_bytes),
            ("pixel_ink_threshold", 220),
            ("coarse_threshold", Decimal(str(_COARSE_THRESHOLD))),
            ("dedup_iou_min", Decimal("0.62")),
            ("proposal_cap", "max(8192,limite_candidatos*1000):after-exact-coarse-filter"),
            ("anchor_strategy", "pillow-native-all-dark-and-light-samples"),
            ("tile_memory_multiplier", 20),
            ("raw_match_cap", "limite_candidatos*16"),
            ("template_resampling", "nearest"),
            ("render_annots", False),
            (
                "threshold_bruto",
                Decimal(str(_MATCH_THRESHOLD)) if method == "template" else None,
            ),
            ("hough_votes_threshold", 12 if method == "hough-generalizado" else None),
            ("hough_canny_thresholds", "60,140" if method == "hough-generalizado" else None),
            ("hough_dp", 2 if method == "hough-generalizado" else None),
            ("hough_levels", 180 if method == "hough-generalizado" else None),
            ("pymupdf_version", str(pymupdf.VersionBind)),
            ("opencv_version", cv_version or "indisponivel"),
            ("templates_sha256", ",".join(sorted(item.sha256 for item in templates))),
        ),
    )


def perfis_simbolos_raster(
    *,
    templates: tuple[TemplateRasterVerificado, ...],
    configuracao: ConfiguracaoDetectorRaster = _DEFAULT_CONFIG,
) -> tuple[PerfilMetodoSimbolos, ...]:
    """Stable method signatures without opening a document or executing a page."""
    if len({item.id for item in templates}) != len(templates):
        raise ValueError("IDs de templates devem ser únicos")
    cv_version: str | None = None
    if importlib.util.find_spec("cv2") is not None:
        try:
            cv2 = importlib.import_module("cv2")
            cv_version = str(cv2.__version__)
        except (ImportError, OSError):
            cv_version = None
    return (
        _profile("template", templates, configuracao, cv_version),
        _profile("hough-generalizado", templates, configuracao, cv_version),
    )


def _positions(length: int, tile: int, overlap: int) -> tuple[int, ...]:
    if length <= tile:
        return (0,)
    stride = tile - overlap
    positions = list(range(0, length - tile + 1, stride))
    if positions[-1] != length - tile:
        positions.append(length - tile)
    return tuple(positions)


def _variants(
    templates: tuple[TemplateRasterVerificado, ...], config: ConfiguracaoDetectorRaster
) -> tuple[tuple[TemplateRasterVerificado, float, int, Image.Image, bytes], ...]:
    results = []
    for template in templates:
        with Image.open(io.BytesIO(template.dados_png)) as source:
            base = source.convert("L")
        for factor in config.escalas:
            scaled = base.resize(
                (max(8, round(base.width * factor)), max(8, round(base.height * factor))),
                Image.Resampling.NEAREST,
            )
            for angle in config.rotacoes:
                rotated = scaled.rotate(angle, expand=True)
                binary = rotated.point(lambda value: 0 if value < 220 else 1).tobytes()
                results.append((template, factor, angle, rotated, binary))
    return tuple(results)


def _sample_points(
    binary: bytes, width: int, height: int
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    # Spread anchors across both foreground and background; foreground alone
    # would accept a dense black patch and white alone would accept blank paper.
    dark = [i for i, value in enumerate(binary) if value == 0]
    light = [i for i, value in enumerate(binary) if value != 0]
    if len(dark) < 5 or len(light) < 5:
        return (), ()

    def sampled(items: list[int]) -> tuple[int, ...]:
        stride = max(1, len(items) // 16)
        return tuple(items[::stride][:16])

    return sampled(dark), sampled(light)


def _score(
    image: bytes, image_width: int, binary: bytes, width: int, height: int, x: int, y: int
) -> float:
    dark_hits = dark_total = light_hits = light_total = 0
    for row in range(height):
        image_start = (y + row) * image_width + x
        template_start = row * width
        for column in range(width):
            ink = binary[template_start + column] == 0
            same = (image[image_start + column] == 0) == ink
            if ink:
                dark_total += 1
                dark_hits += same
            else:
                light_total += 1
                light_hits += same
    return (dark_hits / dark_total + light_hits / light_total) / 2


def _native_anchor_counts(
    binary_page: Image.Image, samples: tuple[int, ...], template_width: int
) -> Image.Image:
    counts = Image.new("L", binary_page.size, 0)
    for index in samples:
        dx, dy = index % template_width, index // template_width
        counts = ImageChops.add(counts, ImageChops.offset(binary_page, -dx, -dy))
    return counts


def _coarse_candidate_mask(
    page: bytes,
    page_width: int,
    page_height: int,
    dark: tuple[int, ...],
    light: tuple[int, ...],
    template_width: int,
) -> bytes:
    """Compute exactly the existing dark/light coarse predicate in Pillow C.

    Offset wraps at image edges, but callers inspect only complete template
    windows, whose sample coordinates never cross an edge.
    """
    white_page = Image.frombytes("L", (page_width, page_height), page)
    dark_page = white_page.point(lambda value: 1 if value == 0 else 0)
    dark_counts = _native_anchor_counts(dark_page, dark, template_width)
    light_counts = _native_anchor_counts(white_page, light, template_width)
    mask = Image.new("L", (page_width, page_height), 0)
    required_dark = math.ceil(len(dark) * _COARSE_THRESHOLD)
    for dark_hits in range(required_dark, len(dark) + 1):
        minimum_light = next(
            (
                count
                for count in range(len(light) + 1)
                if (dark_hits / len(dark) + count / len(light)) / 2 >= _COARSE_THRESHOLD
            ),
            None,
        )
        if minimum_light is None:
            continue
        dark_mask = dark_counts.point(lambda value, hits=dark_hits: 255 if value == hits else 0)
        light_mask = light_counts.point(
            lambda value, minimum=minimum_light: 255 if value >= minimum else 0
        )
        mask = ImageChops.lighter(mask, ImageChops.multiply(dark_mask, light_mask))
    return mask.tobytes()


def _search_template(
    page: bytes,
    page_width: int,
    page_height: int,
    template: bytes,
    width: int,
    height: int,
    *,
    limit: int,
) -> tuple[list[tuple[int, int, float]], bool]:
    dark, light = _sample_points(template, width, height)
    if not dark or not light or width > page_width or height > page_height:
        return [], False
    candidates: list[tuple[int, int, float]] = []
    coarse = _coarse_candidate_mask(page, page_width, page_height, dark, light, width)
    proposals = 0
    for y in range(page_height - height + 1):
        row_start = y * page_width
        row_end = row_start + page_width - width + 1
        cursor = row_start
        while (cursor := coarse.find(b"\xff", cursor, row_end)) >= 0:
            x = cursor - row_start
            cursor += 1
            proposals += 1
            if proposals > max(8192, limit * 1000):
                return candidates, True
            score = _score(page, page_width, template, width, height, x, y)
            if score < _MATCH_THRESHOLD:
                continue
            current_box = (float(x), float(y), float(x + width), float(y + height))
            existing = next(
                (
                    i
                    for i, (cx, cy, _) in enumerate(candidates)
                    if _iou(
                        current_box,
                        (float(cx), float(cy), float(cx + width), float(cy + height)),
                    )
                    >= 0.62
                ),
                None,
            )
            if existing is not None:
                if score > candidates[existing][2]:
                    candidates[existing] = (x, y, score)
                continue
            candidates.append((x, y, score))
            if len(candidates) > limit:
                return candidates[:limit], True
    return candidates, False


def _iou(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    area = max(0.0, right - left) * max(0.0, bottom - top)
    total = (first[2] - first[0]) * (first[3] - first[1])
    total += (second[2] - second[0]) * (second[3] - second[1]) - area
    return area / total if total > 0 else 0.0


def _deduplicate(
    matches: list[_Match], limit: int
) -> tuple[list[tuple[_Match, tuple[_Match, ...]]], bool]:
    grouped: list[list[_Match]] = []
    # Sorted score only picks a representative. It does not add votes or alter
    # the score from DPI/rotation/tile repeats.
    for match in sorted(matches, key=lambda item: item.score, reverse=True):
        owner = next(
            (group for group in grouped if _iou(group[0].box, match.box) >= 0.62),
            None,
        )
        if owner is None:
            if len(grouped) >= limit:
                return [(group[0], tuple(group)) for group in grouped], True
            grouped.append([match])
        else:
            owner.append(match)
    return [(group[0], tuple(group)) for group in grouped], False


def _geometry(page: Any, box: tuple[float, float, float, float]) -> GeometriaObservacaoSimbolo:
    x0, y0, x1, y1 = box
    width, height = float(page.rect.width), float(page.rect.height)
    visual = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    inverse = page.derotation_matrix
    original = tuple(pymupdf.Point(x, y) * inverse for x, y in visual)
    matrix = (
        Decimal(str(width * inverse.a)),
        Decimal(str(width * inverse.b)),
        Decimal(str(height * inverse.c)),
        Decimal(str(height * inverse.d)),
        Decimal(str(inverse.e)),
        Decimal(str(inverse.f)),
    )
    return GeometriaObservacaoSimbolo(
        tipo=TipoGeometria.POLIGONO,
        pontos_originais=tuple((Decimal(str(p.x)), Decimal(str(p.y))) for p in original),
        pontos_normalizados=tuple(
            PontoNormalizado(
                Decimal(str(min(1.0, max(0.0, x / width)))),
                Decimal(str(min(1.0, max(0.0, y / height)))),
            )
            for x, y in visual
        ),
        transformacao=TransformacaoSimbolo(
            normalizada_para_original=matrix,
            sistema_original="pymupdf-page-unrotated:points:top-left",
        ),
        normalizacao_limitada=any(not (0 <= x <= width and 0 <= y <= height) for x, y in visual),
    )


def _observation(
    page: Any,
    source: FonteObservacaoSimbolo,
    profile: PerfilMetodoSimbolos,
    best: _Match,
    matches: tuple[_Match, ...],
) -> ObservacaoSimbolo:
    attributes = (
        ("fonte_referencia", best.template.fonte_referencia),
        ("template_sha256", best.template.sha256),
        ("templates_correlacionados", ";".join(sorted({m.template.id for m in matches}))),
        ("tiles_concordantes", ";".join(f"{m.tile[0]},{m.tile[1]}" for m in matches)),
        ("variantes_correlacionadas", ";".join(f"{m.scale}:{m.rotation}" for m in matches)),
        (
            "score_tipo",
            "votos_hough_brutos_nao_probabilidade"
            if best.method == "hough"
            else "similaridade_binaria_bruta_nao_probabilidade",
        ),
    )
    by_class: dict[str, float] = {}
    for match in matches:
        by_class[match.template.classe] = max(
            by_class.get(match.template.classe, float("-inf")), match.score
        )
    return ObservacaoSimbolo(
        fonte=source,
        metodo_assinatura=profile.assinatura(),
        geometria=_geometry(page, best.box),
        alternativas=tuple(
            AlternativaClasseSimbolo(classe=classe, score_bruto=Decimal(str(score)))
            for classe, score in sorted(by_class.items(), key=lambda item: item[1], reverse=True)
        ),
        score_bruto=Decimal(str(best.score)),
        raster_sha256=best.raster_hash,
        template=best.template.id,
        atributos=attributes,
    )


def observar_simbolos_raster(
    page: Any,
    *,
    documento_id: str,
    documento_sha256: str,
    pagina_numero: int,
    templates: tuple[TemplateRasterVerificado, ...],
    configuracao: ConfiguracaoDetectorRaster = _DEFAULT_CONFIG,
) -> tuple[ResultadoMetodoSimbolos, ...]:
    """Scan every page tile once and emit correlated template/Hough method results."""
    templates = tuple(templates)
    if len({item.id for item in templates}) != len(templates):
        raise ValueError("IDs de templates devem ser únicos")
    if page.rect.width <= 0 or page.rect.height <= 0:
        raise ValueError("Página deve possuir área positiva")
    variants = _variants(templates, configuracao)
    max_span = max((max(item[3].size) for item in variants), default=0)
    overlap = max(configuracao.sobreposicao_pixels, max_span)
    if overlap >= configuracao.tile_pixels:
        raise ValueError("Tile deve comportar a maior variante e sobreposição")
    template_profile, hough_profile = perfis_simbolos_raster(
        templates=templates, configuracao=configuracao
    )
    cv_available = dict(hough_profile.parametros)["opencv_version"] != "indisponivel"
    source = FonteObservacaoSimbolo(
        documento_id=documento_id,
        documento_sha256=documento_sha256,
        pagina_numero=pagina_numero,
        camada="base",
    )
    factor = configuracao.dpi / 72
    page_width = math.ceil(float(page.rect.width) * factor)
    page_height = math.ceil(float(page.rect.height) * factor)
    memory_failure = (
        min(page_width, configuracao.tile_pixels) * min(page_height, configuracao.tile_pixels) * 20
        > configuracao.limite_bytes
    )
    template_matches: list[_Match] = []
    hough_matches: list[_Match] = []
    saturated = False
    hough_failure: str | None = None
    for tile_y in (
        () if memory_failure else _positions(page_height, configuracao.tile_pixels, overlap)
    ):
        for tile_x in _positions(page_width, configuracao.tile_pixels, overlap):
            right = min(page_width, tile_x + configuracao.tile_pixels)
            bottom = min(page_height, tile_y + configuracao.tile_pixels)
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(factor, factor),
                colorspace=pymupdf.csRGB,
                alpha=False,
                annots=False,
                clip=pymupdf.Rect(
                    tile_x / factor, tile_y / factor, right / factor, bottom / factor
                ),
            )
            if pix.width * pix.height * 20 > configuracao.limite_bytes:
                memory_failure = True
                break
            raster_hash = sha256(pix.samples).hexdigest()
            with Image.frombytes("RGB", (pix.width, pix.height), pix.samples) as rgb:
                gray = rgb.convert("L")
            binary = gray.point(lambda value: 0 if value < 220 else 1).tobytes()
            for template, scale, angle, image, template_binary in variants:
                found, overflow = _search_template(
                    binary,
                    pix.width,
                    pix.height,
                    template_binary,
                    image.width,
                    image.height,
                    limit=configuracao.limite_candidatos,
                )
                saturated |= overflow
                for x, y, score in found:
                    box = (
                        (pix.x + x) / factor,
                        (pix.y + y) / factor,
                        (pix.x + x + image.width) / factor,
                        (pix.y + y + image.height) / factor,
                    )
                    template_matches.append(
                        _Match(
                            template,
                            "template",
                            box,
                            score,
                            scale,
                            angle,
                            (tile_x, tile_y),
                            raster_hash,
                        )
                    )
                if len(template_matches) > configuracao.limite_candidatos * 16:
                    saturated = True
                    break
            if saturated and len(template_matches) > configuracao.limite_candidatos * 16:
                break
            if cv_available and templates:
                try:
                    hough_matches.extend(
                        _hough_tile(
                            gray, variants, pix.x, pix.y, factor, (tile_x, tile_y), raster_hash
                        )
                    )
                except Exception as error:
                    hough_failure = f"{type(error).__name__}: {error}"
            if len(hough_matches) > configuracao.limite_candidatos * 16:
                saturated = True
                break
        if memory_failure or (
            saturated
            and max(len(template_matches), len(hough_matches)) > configuracao.limite_candidatos * 16
        ):
            break
    template_groups, cap_reached = _deduplicate(template_matches, configuracao.limite_candidatos)
    hough_groups, hough_cap = _deduplicate(hough_matches, configuracao.limite_candidatos)
    saturated |= cap_reached or hough_cap
    region = (PontoNormalizado(Decimal(0), Decimal(0)), PontoNormalizado(Decimal(1), Decimal(1)))
    template_observations = tuple(
        _observation(page, source, template_profile, best, group) for best, group in template_groups
    )
    hough_observations = tuple(
        _observation(page, source, hough_profile, best, group) for best, group in hough_groups
    )
    template_state = (
        EstadoMetodoSimbolos.FALHA
        if saturated or memory_failure
        else EstadoMetodoSimbolos.CONCLUIDO
        if template_observations
        else EstadoMetodoSimbolos.NAO_DETECCAO
    )
    hough_state = (
        EstadoMetodoSimbolos.INDISPONIVEL
        if not cv_available
        else EstadoMetodoSimbolos.FALHA
        if hough_failure or saturated or memory_failure
        else EstadoMetodoSimbolos.CONCLUIDO
        if hough_observations
        else EstadoMetodoSimbolos.NAO_DETECCAO
    )
    return (
        ResultadoMetodoSimbolos(
            perfil=template_profile,
            coberturas=(
                CoberturaMetodoSimbolos(
                    fonte=source,
                    regiao_normalizada=region,
                    classes_avaliadas=template_profile.classes_suportadas,
                    estado=template_state,
                    motivo=(
                        "Orçamento de memória insuficiente"
                        if memory_failure
                        else "Limite de candidatos/picos alcançado"
                        if saturated
                        else None
                    ),
                ),
            ),
            observacoes=template_observations,
        ),
        ResultadoMetodoSimbolos(
            perfil=hough_profile,
            coberturas=(
                CoberturaMetodoSimbolos(
                    fonte=source,
                    regiao_normalizada=region,
                    classes_avaliadas=hough_profile.classes_suportadas,
                    estado=hough_state,
                    motivo=(
                        "OpenCV não instalado"
                        if not cv_available
                        else hough_failure
                        or (
                            "Orçamento de memória insuficiente"
                            if memory_failure
                            else "Limite de candidatos alcançado"
                            if saturated
                            else None
                        )
                    ),
                ),
            ),
            observacoes=hough_observations,
        ),
    )


def _hough_tile(
    gray: Image.Image,
    variants: tuple[tuple[TemplateRasterVerificado, float, int, Image.Image, bytes], ...],
    origin_x: int,
    origin_y: int,
    factor: float,
    tile: tuple[int, int],
    raster_hash: str,
) -> list[_Match]:
    """Optional Generalized Hough Ballard trial; no fallback pretends it ran."""
    cv2 = importlib.import_module("cv2")
    np = importlib.import_module("numpy")

    page = np.asarray(gray)
    edges = cv2.Canny(page, 60, 140)
    matches = []
    for template, scale, angle, image, _ in variants:
        model = cv2.createGeneralizedHoughBallard()
        model.setMinDist(max(8, min(image.size) // 2))
        model.setDp(2)
        model.setLevels(180)
        model.setVotesThreshold(12)
        model.setTemplate(cv2.Canny(np.asarray(image), 60, 140))
        positions, votes = model.detect(edges)
        if positions is None or votes is None:
            continue
        for position, vote in zip(positions.reshape(-1, 4), votes.reshape(-1, 3), strict=True):
            center_x, center_y = position[:2]
            x = float(center_x) - image.width / 2
            y = float(center_y) - image.height / 2
            if x < 0 or y < 0 or x + image.width > gray.width or y + image.height > gray.height:
                continue
            box = (
                (origin_x + x) / factor,
                (origin_y + y) / factor,
                (origin_x + x + image.width) / factor,
                (origin_y + y + image.height) / factor,
            )
            matches.append(
                _Match(template, "hough", box, float(vote[0]), scale, angle, tile, raster_hash)
            )
    return matches
