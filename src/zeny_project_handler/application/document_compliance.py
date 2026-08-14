"""Fatos determinísticos de coerência e presença no pacote documental."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.compliance import FatoConformidade, TipoEscopoConformidade
from zeny_project_handler.domain.documents import DocumentoProjeto

from .compliance_fact_providers import ContextoProvedorFatos, criar_fato_conformidade
from .document_zones import evidencias_sem_anotacoes_de_revisao

_DRAWING_FILE_TOKENS = ("DESENHO", "PLANTA", "PRANCHA", "PROJETO")
_MATERIAL_FILE_TOKENS = ("MATERIA", "ORCAMENTO")
_MATERIAL_TEXT_TOKENS = ("RELACAO DE MATERIAIS", "LISTA DE MATERIAIS", "ORCAMENTO")
_GD_APPLICABILITY_TOKENS = (
    "GERACAO DISTRIBUIDA",
    "MICROGERACAO",
    "MINIGERACAO",
    "SISTEMA FOTOVOLTAICO",
    "GERADOR FOTOVOLTAICO",
)
_GD_DOCUMENT_TOKENS = (
    "PARECER DE ACESSO",
    "ORCAMENTO DE CONEXAO",
    "FORMULARIO DE ACESSO",
    "RELATORIO DE COMISSIONAMENTO",
)
_PHOTO_TOKENS = ("REGISTRO FOTOGRAFICO", "RELATORIO FOTOGRAFICO", "FOTOGRAFIA", "FOTOS")
_POWER_PATTERNS = (
    re.compile(r"\b(?:TRANSFORMADOR(?:ES)?|TRAFO)\b.{0,60}?\b(\d{1,4}(?:[.,]\d+)?)\s*KVA\b"),
    re.compile(r"\b(\d{1,4}(?:[.,]\d+)?)\s*KVA\b.{0,40}?\b(?:TRANSFORMADOR|TRAFO)\b"),
    re.compile(r"(?<!\d)-[13]-(\d{1,4}(?:[.,]\d+)?)(?!\d)"),
)
_PHASE_WORD_PATTERN = re.compile(r"\b(MONOFASICO|BIFASICO|TRIFASICO)\b")
_PHASE_COUNT_PATTERN = re.compile(r"\b([123])\s*(?:F|FASES?)\b")
_PHASE_CODE_PATTERN = re.compile(r"(?<!\d)-([13])-\d{1,4}(?:[.,]\d+)?(?!\d)")
_CODE_PATTERNS = (
    re.compile(r"\b(?:CODIGO|COD\.?)\s*[:=]\s*([-A-Z0-9][A-Z0-9./_-]{1,30})"),
    re.compile(r"(?<![A-Z0-9])(-[13]-\d{1,4}(?:[.,]\d+)?)(?![A-Z0-9])"),
)
_CIRCUIT_PATTERN = re.compile(r"\b(?:CIRCUITO|ALIMENTADOR)\s*[:=]\s*([A-Z0-9][A-Z0-9._/-]{1,20})")


@dataclass(frozen=True, slots=True)
class _ValueEvidence:
    value: str
    evidence: EvidenciaDocumento


@dataclass(frozen=True, slots=True)
class _DocumentSignals:
    document: DocumentoProjeto
    role: str | None
    evidence: tuple[EvidenciaDocumento, ...]
    powers: tuple[_ValueEvidence, ...]
    phases: tuple[_ValueEvidence, ...]
    codes: tuple[_ValueEvidence, ...]
    circuits: tuple[_ValueEvidence, ...]
    normalized_content: str


@dataclass(frozen=True, slots=True)
class _Comparison:
    assessed: bool
    coherent: bool
    evidence: tuple[EvidenciaDocumento, ...]


def prover_fatos_documentais(
    contexto: ContextoProvedorFatos,
) -> tuple[FatoConformidade, ...]:
    """Compare documentos distintos e detecte anexos por marcadores textuais fortes."""
    project_target = next(
        (item for item in contexto.alvos if item.tipo is TipoEscopoConformidade.PROJETO),
        None,
    )
    if project_target is None:
        return ()
    signals = _document_signals(contexto)
    facts: list[FatoConformidade] = []
    for key, attribute in (
        ("potencia_transformador", "powers"),
        ("fases", "phases"),
        ("codigo", "codes"),
        ("circuito", "circuits"),
    ):
        comparison = _compare_value_sets(signals, attribute)
        facts.append(
            criar_fato_conformidade(
                project_target.id,
                f"projeto.coerencia_{key}_avaliada",
                comparison.assessed,
                "comparação entre desenho e relação de materiais/orçamento",
                evidencias=comparison.evidence,
                confianca=Decimal("0.95"),
            )
        )
        if comparison.assessed:
            facts.append(
                criar_fato_conformidade(
                    project_target.id,
                    f"projeto.coerencia_{key}",
                    comparison.coherent,
                    "conjuntos de valores explícitos extraídos de documentos distintos",
                    evidencias=comparison.evidence,
                    confianca=Decimal("0.95"),
                )
            )

    gd_evidence = _evidence_with_tokens(signals, _GD_APPLICABILITY_TOKENS)
    gd_document_evidence = _evidence_with_tokens(signals, _GD_DOCUMENT_TOKENS)
    photo_evidence = _evidence_with_tokens(signals, _PHOTO_TOKENS)
    has_linked_photos = any(item.fotos for item in contexto.sessao.projeto.elementos)
    facts.extend(
        (
            criar_fato_conformidade(
                project_target.id,
                "projeto.geracao_distribuida_identificada",
                _package_has_tokens(signals, _GD_APPLICABILITY_TOKENS),
                "nomes e conteúdo textual dos PDFs do projeto",
                evidencias=gd_evidence,
                confianca=Decimal("0.92"),
            ),
            criar_fato_conformidade(
                project_target.id,
                "projeto.documentacao_gd_identificada",
                _package_has_tokens(signals, _GD_DOCUMENT_TOKENS),
                "documentos de acesso/conexão identificados no pacote",
                evidencias=gd_document_evidence,
                confianca=Decimal("0.92"),
            ),
            criar_fato_conformidade(
                project_target.id,
                "projeto.registro_fotografico_identificado",
                has_linked_photos or _package_has_tokens(signals, _PHOTO_TOKENS),
                "fotos vinculadas ao modelo ou registro fotográfico identificado no pacote",
                evidencias=photo_evidence,
                confianca=Decimal("0.92"),
            ),
        )
    )
    return tuple(facts)


def _document_signals(contexto: ContextoProvedorFatos) -> tuple[_DocumentSignals, ...]:
    page_to_document = {
        page.id: document
        for document in contexto.sessao.projeto.documentos
        for page in document.paginas
    }
    evidence_by_document = {
        document.id: evidencias_sem_anotacoes_de_revisao(
            tuple(
                item
                for item in contexto.sessao.evidencias
                if page_to_document.get(item.pagina_id) == document
            )
        )
        for document in contexto.sessao.projeto.documentos
    }
    return tuple(
        _signals_for_document(document, evidence_by_document[document.id])
        for document in contexto.sessao.projeto.documentos
    )


def _signals_for_document(
    document: DocumentoProjeto,
    evidence: tuple[EvidenciaDocumento, ...],
) -> _DocumentSignals:
    normalized_name = re.sub(r"[-_.]+", " ", _normalize(document.nome_arquivo))
    normalized_evidence = tuple(
        (item, _normalize(item.conteudo_bruto or "")) for item in evidence if item.conteudo_bruto
    )
    content = " ".join((normalized_name, *(text for _item, text in normalized_evidence)))
    role = _document_role(normalized_name, content)
    return _DocumentSignals(
        document=document,
        role=role,
        evidence=evidence,
        powers=_extract_values(normalized_evidence, _POWER_PATTERNS, _canonical_number),
        phases=_extract_phases(normalized_evidence),
        codes=_extract_values(normalized_evidence, _CODE_PATTERNS, str.upper),
        circuits=_extract_values(normalized_evidence, (_CIRCUIT_PATTERN,), str.upper),
        normalized_content=content,
    )


def _document_role(name: str, content: str) -> str | None:
    if any(token in name for token in _MATERIAL_FILE_TOKENS):
        return "MATERIALS"
    if any(token in name for token in _DRAWING_FILE_TOKENS):
        return "DRAWING"
    if any(token in content for token in _MATERIAL_TEXT_TOKENS):
        return "MATERIALS"
    if "ESCALA" in content and any(token in content for token in ("FOLHA", "FORMATO", "NS:")):
        return "DRAWING"
    return None


def _extract_values(
    evidence: tuple[tuple[EvidenciaDocumento, str], ...],
    patterns: tuple[re.Pattern[str], ...],
    normalize_value: Callable[[str], str],
) -> tuple[_ValueEvidence, ...]:
    result: list[_ValueEvidence] = []
    seen: set[tuple[str, UUID]] = set()
    for item, text in evidence:
        for pattern in patterns:
            for match in pattern.finditer(text):
                value = normalize_value(match.group(1))
                identity = (value, item.id)
                if identity not in seen:
                    seen.add(identity)
                    result.append(_ValueEvidence(value, item))
    return tuple(result)


def _extract_phases(
    evidence: tuple[tuple[EvidenciaDocumento, str], ...],
) -> tuple[_ValueEvidence, ...]:
    labels = {"MONOFASICO": "1F", "BIFASICO": "2F", "TRIFASICO": "3F"}
    result: list[_ValueEvidence] = []
    seen: set[tuple[str, UUID]] = set()
    for item, text in evidence:
        values = (
            *(labels[match.group(1)] for match in _PHASE_WORD_PATTERN.finditer(text)),
            *(f"{match.group(1)}F" for match in _PHASE_COUNT_PATTERN.finditer(text)),
            *(f"{match.group(1)}F" for match in _PHASE_CODE_PATTERN.finditer(text)),
        )
        for value in values:
            identity = (value, item.id)
            if identity not in seen:
                seen.add(identity)
                result.append(_ValueEvidence(value, item))
    return tuple(result)


def _compare_value_sets(
    signals: tuple[_DocumentSignals, ...],
    attribute: str,
) -> _Comparison:
    drawings = tuple(item for item in signals if item.role == "DRAWING")
    materials = tuple(item for item in signals if item.role == "MATERIALS")
    drawing_values = _unique_values(drawings, attribute)
    material_values = _unique_values(materials, attribute)
    assessed = bool(drawing_values and material_values)
    evidence = _comparison_evidence(drawings, materials, attribute) if assessed else ()
    return _Comparison(
        assessed=assessed,
        coherent=assessed and drawing_values == material_values,
        evidence=evidence,
    )


def _unique_values(signals: tuple[_DocumentSignals, ...], attribute: str) -> set[str]:
    return {
        item.value
        for signal in signals
        for item in getattr(signal, attribute)
        if isinstance(item, _ValueEvidence)
    }


def _comparison_evidence(
    drawings: tuple[_DocumentSignals, ...],
    materials: tuple[_DocumentSignals, ...],
    attribute: str,
) -> tuple[EvidenciaDocumento, ...]:
    return tuple(
        dict.fromkeys(
            item.evidence
            for signal in (*drawings, *materials)
            for item in getattr(signal, attribute)
            if isinstance(item, _ValueEvidence)
        )
    )


def _package_has_tokens(signals: tuple[_DocumentSignals, ...], tokens: tuple[str, ...]) -> bool:
    return any(token in signal.normalized_content for signal in signals for token in tokens)


def _evidence_with_tokens(
    signals: tuple[_DocumentSignals, ...], tokens: tuple[str, ...]
) -> tuple[EvidenciaDocumento, ...]:
    return tuple(
        dict.fromkeys(
            item
            for signal in signals
            for item in signal.evidence
            if any(token in _normalize(item.conteudo_bruto or "") for token in tokens)
        )
    )


def _canonical_number(value: str) -> str:
    number = Decimal(value.replace(",", "."))
    return format(number.normalize(), "f")


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_marks.upper()).strip()
