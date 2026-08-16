"""Derivação de fatos documentais, geométricos e normativos de um projeto."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid5

from zeny_project_handler.application.compliance_evaluation import avaliar_regras_conformidade
from zeny_project_handler.application.human_review import SessaoRevisao
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import (
    JsonPrimitive,
    TipoCabo,
    TipoEquipamento,
    TipoEstruturaMt,
    TipoPoste,
)
from zeny_project_handler.domain.compliance import (
    AchadoConformidade,
    AlvoConformidade,
    FatoConformidade,
    ItemInspecaoDocumental,
    RegistroRegrasConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
    TipoOrigemPdf,
)
from zeny_project_handler.domain.project import ElementoProjetoType, Equipamento, Poste
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

from .compliance_fact_providers import (
    ContextoProvedorFatos,
    ProvedorFatosConformidade,
    criar_fato_conformidade,
)
from .document_compliance import prover_fatos_documentais
from .document_zones import (
    evidencia_eh_anotacao_de_revisao,
    evidencia_esta_na_zona_de_cabecalho,
    evidencias_sem_anotacoes_de_revisao,
)
from .span_compliance import prover_fatos_vaos
from .topology_compliance import medir_extensao_rede_instalar, prover_fatos_topologicos

_TEXT_TYPES = {TipoEvidencia.TEXTO, TipoEvidencia.OCR}
_NEARBY_TEXT_DISTANCE = 0.035
_REGION_TEXT_DISTANCE = 0.08
_LABELED_FIELD_PATTERN = re.compile(
    r"^\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9 .()/º°_-]{0,60}?)\s*:\s*(.*?)\s*$"
)
_KNOWN_DOCUMENT_LABEL_PATTERN = re.compile(
    r"(?<![A-Za-zÀ-ÿ0-9])("
    r"NOTA\s+DE\s+SERVI[CÇ]O|N[ÚU]MERO\s+DO\s+PROJETO|N\.?\s*DO\s+PROJETO|NS|"
    r"ESCALA|FORMATO(?:\s+DA\s+FOLHA)?|FOLHA|PRANCHA|DATA(?:\s+DO\s+PROJETO)?|"
    r"CIRCUITO|ALIMENTADOR|SOLIC\.?|EXTENS[AÃ]O|IN[IÍ]CIO|FINAL|"
    r"CIDADE|BAIRRO|CLIENTE|TELEFONE|SERVI[CÇ]O|DISPOSITIVO|LEVANTAMENTO|"
    r"PROJETO|APROVA[CÇ][AÃ]O|IMPACTO\s+AMBIENTAL"
    r")\s*:",
    re.IGNORECASE,
)
_CONTEXT_FIELD_LABELS = {
    "AREA",
    "BAIRRO",
    "CLASSIFICACAO",
    "CONTEXTO",
    "LOCALIZACAO",
    "SERVICO",
    "TIPO DE AREA",
    "TIPO DE SERVICO",
    "ZONA",
}
_CONTEXT_VALUE_PATTERN = re.compile(r"(?:(?:AREA|REDE|ZONA)\s+)?(URBAN[AO]|RURAL)")
_FIELD_PATTERNS = {
    "nota_servico": re.compile(
        r"\b(?:NOTA\s+DE\s+SERVICO|N[Oº°.]?\s*(?:DO\s+)?PROJETO|NS)"
        r"\s*[:=.-]?\s*(\d{10})\b"
    ),
    "escala": re.compile(r"\bESCALA\s*[:=.-]?\s*(1\s*:\s*\d{2,6})\b"),
    "formato_folha": re.compile(r"\bFORMATO\s*[:=.-]?\s*(A[1-4])\b"),
    "numero_folha": re.compile(
        r"\b(?:FOLHA|PRANCHA)\s*(?:N[Oº°.]?)?\s*[:=.-]?\s*([A-Z0-9][A-Z0-9./-]{0,15})"
    ),
    "data_projeto": re.compile(
        r"\bDATA(?:\s+DO\s+PROJETO)?\s*[:=.-]?\s*(\d{2}[/-]\d{2}[/-]\d{2,4})\b"
    ),
    "circuito": re.compile(r"\b(?:CIRCUITO|ALIMENTADOR)\s*[:=.-]?\s*([A-Z0-9][A-Z0-9._/-]{1,20})"),
}
_FIELD_LABELS = {
    "nota_servico": "Nota de Serviço / número do projeto",
    "escala": "Escala",
    "formato_folha": "Formato da folha",
    "numero_folha": "Número da folha",
    "data_projeto": "Data do projeto",
    "circuito": "Circuito / alimentador",
}
_ABNT_PAGE_SIZES = {
    "A1": (1684.0, 2384.0),
    "A2": (1191.0, 1684.0),
    "A3": (842.0, 1191.0),
    "A4": (595.0, 842.0),
}
_TRANSFORMER_POWER_PATTERN = re.compile(r"^-3-(30|45|75|150|300)$")
_POLE_IDENTIFIER_PATTERN = re.compile(r"P0*([1-9][0-9]*)")


@dataclass(frozen=True, slots=True)
class _CampoRotuladoDocumento:
    rotulo: str
    valor: str
    evidencias: tuple[EvidenciaDocumento, ...]
    geometria: GeometriaDocumento


@dataclass(frozen=True, slots=True)
class _SignatureEvidence:
    fields: tuple[EvidenciaDocumento, ...]
    signed_fields: tuple[EvidenciaDocumento, ...]
    labels: tuple[EvidenciaDocumento, ...]

    @property
    def combined(self) -> tuple[EvidenciaDocumento, ...]:
        return (*self.fields, *self.labels)


@dataclass(frozen=True, slots=True)
class _NetworkContext:
    urban: bool = False
    rural: bool = False
    origin: str = ""
    confidence: Decimal = Decimal("0")
    evidence: tuple[EvidenciaDocumento, ...] = ()


@dataclass(frozen=True, slots=True)
class _RegionFactContext:
    proposals_by_id: dict[UUID, PropostaElemento]
    confirmed_elements_by_proposal: dict[UUID, ElementoProjetoType]
    technology_options: dict[UUID, str]
    equipment_class_options: dict[UUID, str]
    phase_options: dict[UUID, str]
    post_format_options: dict[UUID, str]
    network_context: _NetworkContext
    text_evidence: tuple[EvidenciaDocumento, ...]
    evidence: tuple[EvidenciaDocumento, ...]


@dataclass(frozen=True, slots=True)
class _TransformerCandidate:
    proposal: PropostaElemento
    element: Equipamento
    power_kva: int


@dataclass(frozen=True, slots=True)
class _TransformerPostPair:
    transformer: _TransformerCandidate
    pole_proposal: PropostaElemento
    pole: Poste


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoConformidadeProjeto:
    alvos: tuple[AlvoConformidade, ...]
    fatos: tuple[FatoConformidade, ...]
    achados: tuple[AchadoConformidade, ...]
    itens_documentais: tuple[ItemInspecaoDocumental, ...]


def analisar_conformidade_projeto(
    sessao: SessaoRevisao,
    registro: RegistroRegrasConformidade,
    *,
    provedores_fatos: tuple[ProvedorFatosConformidade, ...] | None = None,
) -> ResultadoConformidadeProjeto:
    targets = _targets(sessao)
    project_target = next(item for item in targets if item.tipo is TipoEscopoConformidade.PROJETO)
    document_targets = {
        item.referencia_id: item
        for item in targets
        if item.tipo is TipoEscopoConformidade.DOCUMENTO
    }
    facts: list[FatoConformidade] = []
    items: list[ItemInspecaoDocumental] = []
    page_to_document = {
        page.id: document for document in sessao.projeto.documentos for page in document.paginas
    }
    evidence_by_document = {
        document.id: tuple(
            item for item in sessao.evidencias if page_to_document.get(item.pagina_id) == document
        )
        for document in sessao.projeto.documentos
    }

    metadata_values = _metadata_values(sessao)
    network_context = _network_context(sessao)
    if network_context.urban:
        facts.append(
            _fact(
                project_target.id,
                "rede.contexto_urbano",
                True,
                network_context.origin,
                evidence=network_context.evidence,
                confidence=network_context.confidence,
            )
        )
    elif network_context.rural:
        facts.append(
            _fact(
                project_target.id,
                "rede.contexto_rural",
                True,
                network_context.origin,
                evidence=network_context.evidence,
                confidence=network_context.confidence,
            )
        )
    detected_values: dict[str, list[tuple[str, EvidenciaDocumento | None]]] = {}
    for document in sessao.projeto.documentos:
        target = document_targets[document.id]
        document_evidence = evidence_by_document[document.id]
        project_document_evidence = evidencias_sem_anotacoes_de_revisao(document_evidence)
        fields = _extract_document_fields(project_document_evidence)
        for key, matches in fields.items():
            detected_values.setdefault(key, []).extend(matches)
            for value, evidence in matches:
                facts.append(
                    _fact(
                        target.id,
                        f"documento.{key}",
                        value,
                        "texto/OCR do cabeçalho",
                        evidence=(evidence,),
                        confidence=Decimal("0.86"),
                    )
                )
        physical_format = _document_format(document)
        if physical_format is not None and "formato_folha" not in fields:
            detected_values.setdefault("formato_folha", []).append((physical_format, None))
            facts.append(
                _fact(
                    target.id,
                    "documento.formato_folha",
                    physical_format,
                    "dimensões físicas da página PDF",
                    confidence=Decimal("0.98"),
                )
            )
        items.extend(
            _document_header_items(
                document,
                fields,
                project_document_evidence,
                physical_format=physical_format,
                metadata_values=metadata_values,
            )
        )
        document_facts, document_items = _document_control_facts(
            document, target.id, document_evidence
        )
        facts.extend(document_facts)
        items.extend(document_items)

    project_service_note = sessao.projeto.nome.strip()
    if re.fullmatch(r"[0-9]{10}", project_service_note):
        facts.append(
            _fact(
                project_target.id,
                "projeto.nota_servico",
                project_service_note,
                "NS usada como nome do projeto",
                confidence=Decimal("1"),
            )
        )

    for key in _FIELD_LABELS:
        values = detected_values.get(key, ())
        if key == "nota_servico":
            for value, value_evidence in values:
                header_evidence = (value_evidence,) if value_evidence is not None else ()
                facts.append(
                    _fact(
                        project_target.id,
                        "projeto.nota_servico_cabecalho",
                        value,
                        "texto/OCR do cabeçalho PDF",
                        evidence=header_evidence,
                        confidence=Decimal("0.86"),
                    )
                )
                if value != project_service_note:
                    facts.append(
                        _fact(
                            project_target.id,
                            "projeto.nota_servico_divergencia",
                            f"cabeçalho PDF: {value}; nome do projeto: {project_service_note}",
                            (
                                f"comparação da NS do cabeçalho {value} com a NS "
                                f"do projeto {project_service_note}"
                            ),
                            evidence=header_evidence,
                            confidence=Decimal("0.86"),
                        )
                    )
            continue
        if key in metadata_values:
            facts.append(
                _fact(
                    project_target.id,
                    f"projeto.{key}",
                    metadata_values[key],
                    "metadado confirmado do projeto",
                    confidence=Decimal("1"),
                )
            )
        for value, value_evidence in values:
            facts.append(
                _fact(
                    project_target.id,
                    f"projeto.{key}",
                    value,
                    "texto/OCR ou dimensão do documento",
                    evidence=((value_evidence,) if value_evidence is not None else ()),
                    confidence=Decimal("0.86"),
                )
            )

    facts.extend(_project_automation_facts(sessao, project_target.id))

    provider_context = ContextoProvedorFatos(sessao=sessao, alvos=targets)
    providers = provedores_fatos if provedores_fatos is not None else provedores_fatos_padrao()
    for provider in providers:
        facts.extend(provider(provider_context))
    unique_facts = _deduplicate_facts(tuple(facts))
    findings = avaliar_regras_conformidade(registro, targets, unique_facts)
    return ResultadoConformidadeProjeto(
        alvos=targets,
        fatos=unique_facts,
        achados=findings,
        itens_documentais=tuple(items),
    )


def _targets(session: SessaoRevisao) -> tuple[AlvoConformidade, ...]:
    project = session.projeto
    result = [
        AlvoConformidade(
            id=uuid5(project.id, "conformidade:projeto"),
            tipo=TipoEscopoConformidade.PROJETO,
            rotulo=project.nome,
            referencia_id=project.id,
        )
    ]
    for document in project.documentos:
        result.append(
            AlvoConformidade(
                id=uuid5(document.id, "conformidade:documento"),
                tipo=TipoEscopoConformidade.DOCUMENTO,
                rotulo=document.nome_arquivo,
                referencia_id=document.id,
            )
        )
        for page in document.paginas:
            result.append(
                AlvoConformidade(
                    id=uuid5(page.id, "conformidade:pagina"),
                    tipo=TipoEscopoConformidade.PAGINA,
                    rotulo=f"{document.nome_arquivo} · página {page.numero}",
                    referencia_id=page.id,
                    pagina_id=page.id,
                )
            )
    for index, region in enumerate(session.regioes, start=1):
        result.append(
            AlvoConformidade(
                id=uuid5(region.id, "conformidade:regiao"),
                tipo=TipoEscopoConformidade.REGIAO,
                rotulo=region.rotulo_ponto or f"Região {index}",
                referencia_id=region.id,
                pagina_id=region.pagina_id,
                geometria=region.geometria,
            )
        )
    for proposal in session.propostas:
        if isinstance(proposal, PropostaElemento):
            result.append(
                AlvoConformidade(
                    id=uuid5(proposal.id, "conformidade:elemento"),
                    tipo=TipoEscopoConformidade.ELEMENTO,
                    rotulo=f"{proposal.categoria.value} {proposal.codigo_observado or ''}".strip(),
                    referencia_id=proposal.id,
                    pagina_id=proposal.geometria.pagina_id,
                    geometria=proposal.geometria,
                )
            )
    return tuple(result)


def _metadata_values(session: SessaoRevisao) -> dict[str, str]:
    metadata = session.projeto.metadados
    if metadata is None:
        return {}
    result = {
        "nota_servico": metadata.nota_servico,
        "escala": metadata.escala,
        "formato_folha": metadata.formato_folha,
        "numero_folha": metadata.numero_folha,
        "circuito": metadata.circuito,
        "data_projeto": metadata.data_projeto.isoformat() if metadata.data_projeto else None,
    }
    return {key: value for key, value in result.items() if value is not None}


def _project_automation_facts(
    session: SessaoRevisao,
    target_id: UUID,
) -> tuple[FatoConformidade, ...]:
    """Materialize verificações globais já decidíveis pelo conteúdo e pelo modelo confirmado."""
    return (
        *_project_document_presence_facts(session, target_id),
        *_project_pole_facts(session, target_id),
        *_project_extension_facts(session, target_id),
        _project_prordr_fact(session, target_id),
    )


def _project_document_presence_facts(
    session: SessaoRevisao,
    target_id: UUID,
) -> tuple[FatoConformidade, ...]:
    text_evidence = tuple(
        item
        for item in evidencias_sem_anotacoes_de_revisao(session.evidencias)
        if item.tipo in _TEXT_TYPES and item.conteudo_bruto
    )
    normalized_evidence = tuple(
        (item, _normalize_text(item.conteudo_bruto or "")) for item in text_evidence
    )
    file_text = " ".join(
        _normalize_text(document.nome_arquivo) for document in session.projeto.documentos
    )
    full_text = " ".join((file_text, *(text for _item, text in normalized_evidence)))

    material_evidence = tuple(
        item
        for item, text in normalized_evidence
        if "RELACAO DE MATERIA" in text or "ORCAMENTO" in text
    )
    has_materials = "RELACAO DE MATERIA" in full_text and "ORCAMENTO" in full_text
    memory_evidence = tuple(
        item
        for item, text in normalized_evidence
        if "MEMORIA DE CALCULO" in text or "CALCULO ELETRICO" in text or "CALCULO MECANICO" in text
    )
    has_memory = "MEMORIA DE CALCULO" in full_text or (
        "CALCULO ELETRICO" in full_text and "CALCULO MECANICO" in full_text
    )
    return (
        _fact(
            target_id,
            "projeto.relacao_materiais_orcamento_identificada",
            has_materials,
            "nome e conteúdo textual dos PDFs do projeto",
            evidence=material_evidence,
            confidence=Decimal("0.90"),
        ),
        _fact(
            target_id,
            "projeto.memoria_calculo_identificada",
            has_memory,
            "nome e conteúdo textual dos PDFs do projeto",
            evidence=memory_evidence,
            confidence=Decimal("0.90"),
        ),
    )


def _project_prordr_fact(session: SessaoRevisao, target_id: UUID) -> FatoConformidade:
    prordr_evidence = tuple(
        item
        for item in evidencias_sem_anotacoes_de_revisao(session.evidencias)
        if item.tipo in _TEXT_TYPES
        and item.conteudo_bruto
        and any(value in _normalize_text(item.conteudo_bruto) for value in ("PRORDR", "PRODR"))
    )
    return _fact(
        target_id,
        "projeto.prordr_identificado",
        bool(prordr_evidence),
        "conteúdo textual dos PDFs do projeto",
        evidence=prordr_evidence,
        confidence=Decimal("0.92"),
    )


def _project_pole_facts(
    session: SessaoRevisao,
    target_id: UUID,
) -> tuple[FatoConformidade, ...]:
    poles = tuple(
        item
        for item in session.projeto.elementos
        if isinstance(item, Poste) and item.situacao is not SituacaoProjeto.REMOVER
    )
    if not poles:
        return ()
    numbers: list[int] = []
    for pole in poles:
        identifier = pole.identificador_operacional or pole.referencia_desenho or ""
        match = _POLE_IDENTIFIER_PATTERN.fullmatch(_normalize_text(identifier))
        if match is not None:
            numbers.append(int(match.group(1)))
    sequential = (
        len(numbers) == len(poles)
        and len(set(numbers)) == len(numbers)
        and sorted(numbers) == list(range(1, len(poles) + 1))
    )
    geometry = next((item.geometria for item in poles if item.geometria is not None), None)
    return (
        _fact(
            target_id,
            "projeto.postes_total",
            len(poles),
            "postes ativos do modelo confirmado",
            confidence=Decimal("1"),
            geometry=geometry,
        ),
        _fact(
            target_id,
            "projeto.postes_numeracao_sequencial",
            sequential,
            "identificadores operacionais dos postes ativos",
            confidence=Decimal("1"),
            geometry=geometry,
        ),
    )


def _project_extension_facts(
    session: SessaoRevisao,
    target_id: UUID,
) -> tuple[FatoConformidade, ...]:
    extension_m, extension_complete, extension_geometry = medir_extensao_rede_instalar(
        session.projeto
    )
    if extension_m is None:
        return ()
    return (
        _fact(
            target_id,
            "projeto.extensao_rede_instalar_m",
            extension_m,
            "soma deduplicada dos percursos de cabos a instalar",
            confidence=Decimal("1"),
            geometry=extension_geometry,
        ),
        _fact(
            target_id,
            "projeto.extensao_rede_instalar_avaliada",
            extension_complete,
            "cobertura dos comprimentos dos percursos de cabos a instalar",
            confidence=Decimal("1"),
            geometry=extension_geometry,
        ),
    )


def _extract_document_fields(
    evidence: tuple[EvidenciaDocumento, ...],
) -> dict[str, list[tuple[str, EvidenciaDocumento]]]:
    text_evidence = tuple(
        item for item in evidence if item.tipo in _TEXT_TYPES and item.conteudo_bruto
    )
    searchable = _searchable_texts(text_evidence)
    searchable_header = _searchable_texts(
        tuple(item for item in text_evidence if evidencia_esta_na_zona_de_cabecalho(item))
    )
    found: dict[str, list[tuple[str, EvidenciaDocumento]]] = {}
    seen: set[tuple[str, str, UUID]] = set()
    for key, pattern in _FIELD_PATTERNS.items():
        candidates = searchable_header if key == "nota_servico" else searchable
        for text, anchor in candidates:
            normalized = _normalize_text(text)
            for match in pattern.finditer(normalized):
                value = match.group(1).replace(" ", "")
                if key == "escala":
                    value = value.replace(" ", "")
                identity = (key, value, anchor.pagina_id)
                if identity in seen:
                    continue
                seen.add(identity)
                found.setdefault(key, []).append((value, anchor))
    return found


def _searchable_texts(
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[tuple[str, EvidenciaDocumento], ...]:
    result: list[tuple[str, EvidenciaDocumento]] = []
    for anchor in evidence:
        nearby = tuple(
            item
            for item in evidence
            if item.pagina_id == anchor.pagina_id
            and _box_gap(anchor.geometria, item.geometria) <= _NEARBY_TEXT_DISTANCE
        )
        ordered = sorted(
            nearby,
            key=lambda item: (
                _center(item.geometria)[1],
                _center(item.geometria)[0],
            ),
        )
        combined = " ".join(item.conteudo_bruto or "" for item in ordered)
        result.append((anchor.conteudo_bruto or "", anchor))
        if combined.strip() and combined != (anchor.conteudo_bruto or ""):
            result.append((combined, anchor))
    return tuple(result)


def _header_labeled_fields(
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[_CampoRotuladoDocumento, ...]:
    candidates = tuple(
        item
        for item in evidence
        if item.tipo in _TEXT_TYPES
        and item.conteudo_bruto
        and evidencia_esta_na_zona_de_cabecalho(item)
    )
    return _extract_labeled_fields(candidates)


def _servitude_labeled_fields(
    evidence: tuple[EvidenciaDocumento, ...],
    anchors: tuple[EvidenciaDocumento, ...],
) -> tuple[_CampoRotuladoDocumento, ...]:
    if not anchors:
        return ()
    candidates = tuple(
        item
        for item in evidence
        if item.tipo in _TEXT_TYPES
        and item.conteudo_bruto
        and any(_is_in_servitude_section(item, anchor) for anchor in anchors)
    )
    return _extract_labeled_fields(candidates)


def _is_in_servitude_section(
    item: EvidenciaDocumento,
    anchor: EvidenciaDocumento,
) -> bool:
    if item.pagina_id != anchor.pagina_id:
        return False
    item_x, item_y = _center(item.geometria)
    anchor_x, anchor_y = _center(anchor.geometria)
    return abs(item_x - anchor_x) <= 0.24 and anchor_y - 0.015 <= item_y <= anchor_y + 0.085


def _extract_labeled_fields(
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[_CampoRotuladoDocumento, ...]:
    ordered = tuple(
        sorted(
            evidence,
            key=lambda item: (
                str(item.pagina_id),
                _center(item.geometria)[1],
                _center(item.geometria)[0],
                str(item.id),
            ),
        )
    )
    result: list[_CampoRotuladoDocumento] = []
    seen: set[tuple[UUID, str, str]] = set()
    for item in ordered:
        for line in (item.conteudo_bruto or "").splitlines() or ("",):
            for label, raw_value in _labeled_pairs_in_line(line):
                value = _clean_labeled_value(
                    label,
                    re.sub(r"\s+", " ", raw_value).strip(),
                )
                field_evidence: tuple[EvidenciaDocumento, ...] = (item,)
                geometry = item.geometria
                if not value:
                    neighbor = _rightward_field_value(item, ordered)
                    if neighbor is not None:
                        value = re.sub(r"\s+", " ", neighbor.conteudo_bruto or "").strip()
                        field_evidence = (item, neighbor)
                        geometry = _combined_geometry((item.geometria, neighbor.geometria))
                identity = (item.pagina_id, _normalize_text(label), value.casefold())
                if identity in seen:
                    continue
                seen.add(identity)
                result.append(
                    _CampoRotuladoDocumento(
                        rotulo=label,
                        valor=value,
                        evidencias=field_evidence,
                        geometria=geometry,
                    )
                )
    return tuple(result)


def _labeled_pairs_in_line(line: str) -> tuple[tuple[str, str], ...]:
    known_matches = tuple(_KNOWN_DOCUMENT_LABEL_PATTERN.finditer(line))
    if known_matches:
        return tuple(
            (
                re.sub(r"\s+", " ", match.group(1)).strip(),
                line[
                    match.end() : (
                        known_matches[index + 1].start()
                        if index + 1 < len(known_matches)
                        else len(line)
                    )
                ].strip(),
            )
            for index, match in enumerate(known_matches)
        )
    generic = _LABELED_FIELD_PATTERN.fullmatch(line)
    if generic is None:
        return ()
    return ((re.sub(r"\s+", " ", generic.group(1)).strip(), generic.group(2).strip()),)


def _clean_labeled_value(label: str, value: str) -> str:
    key = _canonical_header_key(label)
    patterns = {
        "nota_servico": re.compile(r"(?<!\d)(\d{10})(?!\d)"),
        "escala": re.compile(r"\b(1\s*:\s*\d{2,6})\b"),
        "formato_folha": re.compile(r"\b(A[1-4])\b", re.IGNORECASE),
        "data_projeto": re.compile(r"\b(\d{2}[/-]\d{2}[/-]\d{2,4})\b"),
    }
    pattern = patterns.get(key or "")
    if pattern is None:
        return value
    match = pattern.search(value)
    return re.sub(r"\s+", "", match.group(1)) if match is not None else value


def _rightward_field_value(
    label: EvidenciaDocumento,
    evidence: tuple[EvidenciaDocumento, ...],
) -> EvidenciaDocumento | None:
    label_x, label_y = _center(label.geometria)
    candidates = tuple(
        item
        for item in evidence
        if item.id != label.id
        and item.pagina_id == label.pagina_id
        and item.conteudo_bruto
        and ":" not in item.conteudo_bruto
        and _center(item.geometria)[0] > label_x
        and abs(_center(item.geometria)[1] - label_y) <= 0.008
        and _box_gap(label.geometria, item.geometria) <= 0.055
    )
    return min(
        candidates,
        key=lambda item: (
            _box_gap(label.geometria, item.geometria),
            _center(item.geometria)[0],
            str(item.id),
        ),
        default=None,
    )


def _canonical_header_key(label: str) -> str | None:
    normalized = _normalize_text(label).strip(" .")
    aliases = {
        "nota_servico": ("NOTA DE SERVICO", "NUMERO DO PROJETO", "N DO PROJETO", "NS"),
        "escala": ("ESCALA",),
        "formato_folha": ("FORMATO", "FORMATO DA FOLHA"),
        "numero_folha": ("FOLHA", "NUMERO DA FOLHA", "PRANCHA"),
        "data_projeto": ("DATA", "DATA DO PROJETO"),
        "circuito": ("CIRCUITO", "ALIMENTADOR"),
    }
    return next(
        (key for key, labels in aliases.items() if normalized in labels),
        None,
    )


def _document_header_items(
    document: DocumentoProjeto,
    fields: dict[str, list[tuple[str, EvidenciaDocumento]]],
    document_evidence: tuple[EvidenciaDocumento, ...],
    *,
    physical_format: str | None,
    metadata_values: dict[str, str],
) -> tuple[ItemInspecaoDocumental, ...]:
    result: list[ItemInspecaoDocumental] = []
    generic_fields = _header_labeled_fields(document_evidence)
    represented_keys: set[str] = set()
    for field in generic_fields:
        canonical_key = _canonical_header_key(field.rotulo)
        if canonical_key is not None:
            represented_keys.add(canonical_key)
        value = field.valor or "Não informado"
        result.append(
            ItemInspecaoDocumental(
                grupo="Cabeçalho",
                campo=field.rotulo,
                valor=value,
                estado="IDENTIFICADO" if field.valor else "NAO_IDENTIFICADO",
                documento_id=document.id,
                pagina_id=field.evidencias[0].pagina_id,
                geometria=field.geometria,
                evidencia_ids=tuple(item.id for item in field.evidencias),
                confianca=Decimal("0.92") if field.valor else Decimal("0.86"),
            )
        )
    for key, label in _FIELD_LABELS.items():
        if key in represented_keys:
            continue
        matches = fields.get(key, ())
        if matches:
            value, match_evidence = matches[0]
            result.append(
                ItemInspecaoDocumental(
                    grupo="Cabeçalho",
                    campo=label,
                    valor=value,
                    estado="IDENTIFICADO",
                    documento_id=document.id,
                    pagina_id=match_evidence.pagina_id,
                    geometria=match_evidence.geometria,
                    evidencia_ids=(match_evidence.id,),
                    confianca=Decimal("0.86"),
                )
            )
        elif key in metadata_values:
            result.append(
                ItemInspecaoDocumental(
                    grupo="Cabeçalho",
                    campo=label,
                    valor=metadata_values[key],
                    estado="CONFIRMADO",
                    documento_id=document.id,
                    confianca=Decimal("1"),
                )
            )
        elif key == "formato_folha" and physical_format is not None:
            result.append(
                ItemInspecaoDocumental(
                    grupo="Cabeçalho",
                    campo=label,
                    valor=physical_format,
                    estado="INFERIDO_PELA_PAGINA",
                    documento_id=document.id,
                    pagina_id=document.paginas[0].id,
                    confianca=Decimal("0.98"),
                )
            )
        else:
            result.append(
                ItemInspecaoDocumental(
                    grupo="Cabeçalho",
                    campo=label,
                    valor="Não identificado",
                    estado="NAO_IDENTIFICADO",
                    documento_id=document.id,
                )
            )
    return tuple(result)


def _document_control_facts(
    document: DocumentoProjeto,
    target_id: UUID,
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[tuple[FatoConformidade, ...], tuple[ItemInspecaoDocumental, ...]]:
    semantic_evidence = evidencias_sem_anotacoes_de_revisao(evidence)
    servitude = _servitude_evidence(semantic_evidence)
    stamps = _stamp_evidence(evidence)
    signatures = _signature_evidence(evidence)
    facts = (
        *_servitude_facts(target_id, servitude),
        _stamp_fact(target_id, stamps),
        *_signature_facts(target_id, signatures),
    )
    items = (
        *_servitude_items(document, semantic_evidence, servitude),
        _stamp_item(document, stamps),
        _signature_item(document, signatures),
    )
    return facts, items


def _servitude_evidence(
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[EvidenciaDocumento, ...]:
    return tuple(
        item
        for item in evidence
        if item.tipo in _TEXT_TYPES
        and any(
            token in _normalize_text(item.conteudo_bruto or "")
            for token in ("SERVIDAO", "FAIXA DE SERVIDAO", "FAIXA DE DOMINIO")
        )
    )


def _servitude_facts(
    target_id: UUID,
    servitude: tuple[EvidenciaDocumento, ...],
) -> tuple[FatoConformidade, ...]:
    if not servitude:
        return ()
    return (
        _fact(
            target_id,
            "documento.servidao_mencionada",
            True,
            "menção textual",
            evidence=servitude,
            confidence=Decimal("0.90"),
        ),
    )


def _servitude_items(
    document: DocumentoProjeto,
    evidence: tuple[EvidenciaDocumento, ...],
    servitude: tuple[EvidenciaDocumento, ...],
) -> tuple[ItemInspecaoDocumental, ...]:
    fields = _servitude_labeled_fields(evidence, servitude)
    if fields:
        return tuple(
            ItemInspecaoDocumental(
                grupo="Servidão",
                campo=field.rotulo,
                valor=field.valor or "Não informado",
                estado="IDENTIFICADO" if field.valor else "NAO_IDENTIFICADO",
                documento_id=document.id,
                pagina_id=field.evidencias[0].pagina_id,
                geometria=field.geometria,
                evidencia_ids=tuple(item.id for item in field.evidencias),
                confianca=Decimal("0.92") if field.valor else Decimal("0.86"),
            )
            for field in fields
        )
    return (
        ItemInspecaoDocumental(
            grupo="Servidão",
            campo="Servidão / faixa de domínio",
            valor=(
                f"{len(servitude)} menção(ões) localizada(s), sem campos rotulados"
                if servitude
                else "Nenhuma menção localizada"
            ),
            estado="IDENTIFICADO" if servitude else "NAO_IDENTIFICADO",
            documento_id=document.id,
            pagina_id=servitude[0].pagina_id if servitude else None,
            geometria=servitude[0].geometria if servitude else None,
            evidencia_ids=tuple(item.id for item in servitude),
            confianca=Decimal("0.72") if servitude else None,
        ),
    )


def _stamp_evidence(
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[EvidenciaDocumento, ...]:
    return tuple(
        item
        for item in evidence
        if item.origem_pdf.tipo is TipoOrigemPdf.ANOTACAO
        and (item.origem_pdf.subtipo_anotacao or "").casefold() == "stamp"
        and _in_document_control_zone(item.geometria)
    )


def _stamp_fact(
    target_id: UUID,
    stamps: tuple[EvidenciaDocumento, ...],
) -> FatoConformidade:
    return _fact(
        target_id,
        "documento.carimbo_candidato_quantidade",
        len(stamps),
        "anotações PDF Stamp na zona de cabeçalho/rodapé",
        evidence=stamps,
        confidence=Decimal("0.65"),
    )


def _stamp_item(
    document: DocumentoProjeto,
    stamps: tuple[EvidenciaDocumento, ...],
) -> ItemInspecaoDocumental:
    return ItemInspecaoDocumental(
        grupo="Carimbos e selos",
        campo="Candidatos gráficos",
        valor=(
            f"{len(stamps)} candidato(s) em zona documental"
            if stamps
            else "Nenhum candidato localizado"
        ),
        estado="IDENTIFICADO" if stamps else "NAO_IDENTIFICADO",
        documento_id=document.id,
        pagina_id=stamps[0].pagina_id if stamps else None,
        geometria=stamps[0].geometria if stamps else None,
        evidencia_ids=tuple(item.id for item in stamps),
        confianca=Decimal("0.65") if stamps else None,
    )


def _signature_evidence(evidence: tuple[EvidenciaDocumento, ...]) -> _SignatureEvidence:
    fields = tuple(
        item
        for item in evidence
        if dict(item.atributos_extraidos).get("tipo_campo_formulario") == "Sig"
    )
    signed_fields = tuple(
        item
        for item in fields
        if dict(item.atributos_extraidos).get("campo_formulario_preenchido") is True
    )
    labels = tuple(
        item
        for item in evidence
        if item.tipo in _TEXT_TYPES
        and not evidencia_eh_anotacao_de_revisao(item)
        and any(
            token in _normalize_text(item.conteudo_bruto or "")
            for token in ("ASSINATURA", "RESPONSAVEL TECNICO", "CREA")
        )
    )
    return _SignatureEvidence(fields, signed_fields, labels)


def _signature_facts(
    target_id: UUID,
    signatures: _SignatureEvidence,
) -> tuple[FatoConformidade, ...]:
    if not signatures.signed_fields:
        return ()
    return (
        _fact(
            target_id,
            "documento.assinatura_pdf_preenchida",
            True,
            "campo PDF /Sig preenchido",
            evidence=signatures.signed_fields,
            confidence=Decimal("0.98"),
        ),
    )


def _signature_item(
    document: DocumentoProjeto,
    signatures: _SignatureEvidence,
) -> ItemInspecaoDocumental:
    combined = signatures.combined
    return ItemInspecaoDocumental(
        grupo="Assinaturas",
        campo="Campos e indícios de assinatura",
        valor=_signature_summary(
            signatures.fields,
            signatures.signed_fields,
            signatures.labels,
        ),
        estado=(
            "ASSINATURA_PDF_PRESENTE"
            if signatures.signed_fields
            else ("IDENTIFICADO" if combined else "NAO_IDENTIFICADO")
        ),
        documento_id=document.id,
        pagina_id=combined[0].pagina_id if combined else None,
        geometria=combined[0].geometria if combined else None,
        evidencia_ids=tuple(dict.fromkeys(item.id for item in combined)),
        confianca=(
            Decimal("0.98") if signatures.signed_fields else (Decimal("0.60") if combined else None)
        ),
    )


def _region_facts(
    session: SessaoRevisao,
    *,
    region_targets: dict[UUID | None, AlvoConformidade],
) -> tuple[FatoConformidade, ...]:
    context = _region_fact_context(session)
    facts: list[FatoConformidade] = []
    for region in session.regioes:
        target = region_targets[region.id]
        proposals = tuple(
            context.proposals_by_id[item_id]
            for item_id in region.elemento_ids
            if item_id in context.proposals_by_id
        )
        nearby_text = tuple(
            item
            for item in context.text_evidence
            if item.pagina_id == region.pagina_id
            and _box_gap(region.geometria, item.geometria) <= _REGION_TEXT_DISTANCE
        )
        facts.append(_equipment_install_fact(target.id, proposals, context.evidence))
        facts.extend(_equipment_class_facts(target.id, proposals, session, context))
        facts.extend(_network_context_facts(target.id, context.network_context))
        facts.extend(_risk_facts(target.id, nearby_text))
        facts.extend(_cable_technology_facts(target.id, proposals, session, context))
        facts.extend(_installed_cable_technology_facts(target.id, proposals, session, context))
        facts.extend(_structure_post_facts(target.id, proposals, session, context))
        facts.extend(_existing_post_transformer_facts(target.id, proposals, session, context))
    return tuple(facts)


def prover_fatos_regionais(contexto: ContextoProvedorFatos) -> tuple[FatoConformidade, ...]:
    """Adapte a família regional existente ao contrato explícito de provedores."""
    targets = {
        item.referencia_id: item
        for item in contexto.alvos
        if item.tipo is TipoEscopoConformidade.REGIAO
    }
    return _region_facts(contexto.sessao, region_targets=targets)


def provedores_fatos_padrao() -> tuple[ProvedorFatosConformidade, ...]:
    """Composição determinística usada fora do bootstrap e em testes diretos."""
    return (
        prover_fatos_documentais,
        prover_fatos_regionais,
        prover_fatos_vaos,
        prover_fatos_topologicos,
    )


def _region_fact_context(session: SessaoRevisao) -> _RegionFactContext:
    review_evidence_ids = {
        item.id for item in session.evidencias if evidencia_eh_anotacao_de_revisao(item)
    }
    proposals_by_id = {
        item.id: item
        for item in session.propostas
        if isinstance(item, PropostaElemento)
        and item.estado_revisao is not EstadoRevisao.REJEITADA
        and not review_evidence_ids.intersection(item.evidencia_ids)
    }
    confirmed_by_id = {item.id: item for item in session.projeto.elementos}
    confirmed_elements_by_proposal = {
        decision.proposta_id: confirmed_by_id[decision.elemento_confirmado_id]
        for decision in session.decisoes
        if decision.proposta_id in proposals_by_id
        and decision.elemento_confirmado_id in confirmed_by_id
    }
    return _RegionFactContext(
        proposals_by_id=proposals_by_id,
        confirmed_elements_by_proposal=confirmed_elements_by_proposal,
        technology_options=_catalog_option_codes(session, "tecnologia_rede"),
        equipment_class_options=_catalog_option_codes(session, "classe_equipamento"),
        phase_options=_catalog_option_codes(session, "configuracao_fases"),
        post_format_options=_catalog_option_codes(session, "formato_poste"),
        network_context=_network_context(session),
        text_evidence=tuple(
            item
            for item in session.evidencias
            if item.tipo in _TEXT_TYPES
            and item.conteudo_bruto
            and not evidencia_eh_anotacao_de_revisao(item)
        ),
        evidence=session.evidencias,
    )


def _catalog_option_codes(session: SessaoRevisao, group_key: str) -> dict[UUID, str]:
    return {
        option.id: option.codigo
        for group in session.catalogo.grupos_opcao
        if group.chave == group_key
        for option in group.opcoes
    }


def _proposal_evidence(
    proposal: PropostaElemento,
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[EvidenciaDocumento, ...]:
    return tuple(item for item in evidence if item.id in proposal.evidencia_ids)


def _equipment_install_fact(
    target_id: UUID,
    proposals: tuple[PropostaElemento, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> FatoConformidade:
    equipment = tuple(item for item in proposals if item.categoria is CategoriaElemento.EQUIPAMENTO)
    return _fact(
        target_id,
        "regiao.equipamento_instalar",
        any(item.situacao_projeto is SituacaoProjeto.INSTALAR for item in equipment),
        "elementos reconhecidos na região",
        evidence=tuple(
            item for proposal in equipment for item in evidence if item.id in proposal.evidencia_ids
        ),
        confidence=Decimal("0.90"),
    )


def _equipment_class_facts(
    target_id: UUID,
    proposals: tuple[PropostaElemento, ...],
    session: SessaoRevisao,
    context: _RegionFactContext,
) -> tuple[FatoConformidade, ...]:
    facts: list[FatoConformidade] = []
    for proposal in proposals:
        if proposal.categoria is not CategoriaElemento.EQUIPAMENTO:
            continue
        catalog_item = (
            session.catalogo.item_por_id(proposal.tipo_catalogo_sugerido_id)
            if proposal.tipo_catalogo_sugerido_id is not None
            else None
        )
        if not isinstance(catalog_item, TipoEquipamento):
            continue
        equipment_class = context.equipment_class_options.get(
            catalog_item.classe_equipamento_opcao_id
        )
        if equipment_class:
            facts.append(
                _fact(
                    target_id,
                    "regiao.equipamento_classe",
                    equipment_class,
                    "catálogo do equipamento reconhecido",
                    evidence=_proposal_evidence(proposal, context.evidence),
                    confidence=proposal.confianca,
                )
            )
    return tuple(facts)


def _network_context_facts(
    target_id: UUID,
    context: _NetworkContext,
) -> tuple[FatoConformidade, ...]:
    key = (
        "rede.contexto_urbano"
        if context.urban
        else ("rede.contexto_rural" if context.rural else None)
    )
    if key is None:
        return ()
    return (
        _fact(
            target_id,
            key,
            True,
            context.origin,
            evidence=context.evidence,
            confidence=context.confidence,
        ),
    )


def _risk_facts(
    target_id: UUID,
    nearby_text: tuple[EvidenciaDocumento, ...],
) -> tuple[FatoConformidade, ...]:
    risk_evidence = _risk_assessment_evidence(nearby_text)
    return (
        _fact(
            target_id,
            "regiao.risco_abalroamento_avaliado",
            bool(risk_evidence),
            (
                "nota textual próxima ao equipamento"
                if risk_evidence
                else "ausência de nota de avaliação na região do equipamento"
            ),
            evidence=risk_evidence,
            confidence=Decimal("0.82") if risk_evidence else Decimal("1"),
        ),
    )


def _cable_technology_facts(
    target_id: UUID,
    proposals: tuple[PropostaElemento, ...],
    session: SessaoRevisao,
    context: _RegionFactContext,
) -> tuple[FatoConformidade, ...]:
    facts: list[FatoConformidade] = []
    for proposal in proposals:
        if proposal.categoria is not CategoriaElemento.CABO:
            continue
        catalog_item = (
            session.catalogo.item_por_id(proposal.tipo_catalogo_sugerido_id)
            if proposal.tipo_catalogo_sugerido_id is not None
            else None
        )
        if not isinstance(catalog_item, TipoCabo):
            continue
        technology = context.technology_options.get(catalog_item.tecnologia_rede_opcao_id)
        if technology:
            facts.append(
                _fact(
                    target_id,
                    "cabo.tecnologia",
                    technology,
                    "catálogo do cabo reconhecido",
                    evidence=_proposal_evidence(proposal, context.evidence),
                    confidence=proposal.confianca,
                )
            )
    return tuple(facts)


def _installed_cable_technology_facts(
    target_id: UUID,
    proposals: tuple[PropostaElemento, ...],
    session: SessaoRevisao,
    context: _RegionFactContext,
) -> tuple[FatoConformidade, ...]:
    facts: list[FatoConformidade] = []
    for proposal in proposals:
        if (
            proposal.categoria is not CategoriaElemento.CABO
            or proposal.situacao_projeto is not SituacaoProjeto.INSTALAR
        ):
            continue
        catalog_item = (
            session.catalogo.item_por_id(proposal.tipo_catalogo_sugerido_id)
            if proposal.tipo_catalogo_sugerido_id is not None
            else None
        )
        if not isinstance(catalog_item, TipoCabo):
            continue
        technology = context.technology_options.get(catalog_item.tecnologia_rede_opcao_id)
        if technology:
            facts.append(
                _fact(
                    target_id,
                    "cabo.instalar_tecnologia",
                    technology,
                    "catálogo do cabo reconhecido como instalação",
                    evidence=_proposal_evidence(proposal, context.evidence),
                    confidence=proposal.confianca,
                )
            )
    return tuple(facts)


def _structure_post_facts(
    target_id: UUID,
    proposals: tuple[PropostaElemento, ...],
    session: SessaoRevisao,
    context: _RegionFactContext,
) -> tuple[FatoConformidade, ...]:
    structures: list[tuple[PropostaElemento, TipoEstruturaMt]] = []
    poles: list[tuple[PropostaElemento, TipoPoste]] = []
    for proposal in proposals:
        catalog_item = (
            session.catalogo.item_por_id(proposal.tipo_catalogo_sugerido_id)
            if proposal.tipo_catalogo_sugerido_id is not None
            else None
        )
        if proposal.situacao_projeto is SituacaoProjeto.INSTALAR and isinstance(
            catalog_item, TipoEstruturaMt
        ):
            structures.append((proposal, catalog_item))
        if proposal.situacao_projeto is not SituacaoProjeto.REMOVER and isinstance(
            catalog_item, TipoPoste
        ):
            poles.append((proposal, catalog_item))

    if len(structures) != 1 or len(poles) != 1:
        return ()

    structure_proposal, structure = structures[0]
    pole_proposal, pole = poles[0]
    post_format = context.post_format_options.get(pole.formato_opcao_id)
    if not post_format:
        return ()
    return (
        _fact(
            target_id,
            "regiao.estrutura_mt_instalar_codigo",
            structure.codigo,
            "catálogo da única estrutura de MT reconhecida como instalação",
            evidence=_proposal_evidence(structure_proposal, context.evidence),
            confidence=structure_proposal.confianca,
        ),
        _fact(
            target_id,
            "regiao.poste_ativo_formato",
            post_format,
            "catálogo do único poste reconhecido e não removido",
            evidence=_proposal_evidence(pole_proposal, context.evidence),
            confidence=pole_proposal.confianca,
        ),
    )


def _existing_post_transformer_facts(
    target_id: UUID,
    proposals: tuple[PropostaElemento, ...],
    session: SessaoRevisao,
    context: _RegionFactContext,
) -> tuple[FatoConformidade, ...]:
    """Correlacione somente um transformador e um poste confirmados na mesma região."""
    equipment_proposals = tuple(
        item for item in proposals if item.categoria is CategoriaElemento.EQUIPAMENTO
    )
    candidates = _transformer_candidates(equipment_proposals, session, context)
    applicability_evidence = _proposals_evidence(equipment_proposals, context.evidence)
    if context.network_context.rural or not candidates:
        return _transformer_applicability_facts(
            target_id,
            value=False,
            origin="aplicabilidade resolvida por contexto, situação e catálogo confirmados",
            evidence=applicability_evidence,
            confidence=Decimal("0.98"),
        )
    if not context.network_context.urban or len(candidates) != 1:
        return ()

    pair = _confirmed_transformer_post_pair(candidates[0], proposals, session, context)
    if pair is None:
        return ()
    if pair.pole.situacao is not SituacaoProjeto.EXISTENTE:
        return _transformer_applicability_facts(
            target_id,
            value=False,
            origin="o equipamento confirmado não está associado a poste existente",
            evidence=tuple(
                dict.fromkeys(
                    (
                        *applicability_evidence,
                        *_proposal_evidence(pair.pole_proposal, context.evidence),
                    )
                )
            ),
            confidence=_combined_confidence(
                pair.transformer.proposal.confianca,
                pair.pole_proposal.confianca,
            ),
        )
    return _transformer_post_facts(target_id, pair, session, context)


def _transformer_candidates(
    proposals: tuple[PropostaElemento, ...],
    session: SessaoRevisao,
    context: _RegionFactContext,
) -> tuple[_TransformerCandidate, ...]:
    candidates: list[_TransformerCandidate] = []
    for proposal in proposals:
        element = context.confirmed_elements_by_proposal.get(proposal.id)
        if not isinstance(element, Equipamento):
            continue
        catalog_item = session.catalogo.item_por_id(element.tipo_catalogo_id)
        if not isinstance(catalog_item, TipoEquipamento):
            continue
        candidate = _transformer_candidate(proposal, element, catalog_item, context)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _transformer_candidate(
    proposal: PropostaElemento,
    element: Equipamento,
    catalog_item: TipoEquipamento,
    context: _RegionFactContext,
) -> _TransformerCandidate | None:
    power_match = _TRANSFORMER_POWER_PATTERN.fullmatch(catalog_item.codigo)
    equipment_class = context.equipment_class_options.get(catalog_item.classe_equipamento_opcao_id)
    phase = context.phase_options.get(catalog_item.configuracao_fases_opcao_id)
    if (
        element.situacao is not SituacaoProjeto.INSTALAR
        or equipment_class != "TRANSFORMADOR"
        or phase != "TRIFASICA"
        or power_match is None
    ):
        return None
    return _TransformerCandidate(proposal, element, int(power_match.group(1)))


def _proposals_evidence(
    proposals: tuple[PropostaElemento, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[EvidenciaDocumento, ...]:
    combined = tuple(
        item for proposal in proposals for item in _proposal_evidence(proposal, evidence)
    )
    return tuple(dict.fromkeys(combined))


def _transformer_applicability_facts(
    target_id: UUID,
    *,
    value: bool,
    origin: str,
    evidence: tuple[EvidenciaDocumento, ...],
    confidence: Decimal | None,
) -> tuple[FatoConformidade, ...]:
    return (
        _fact(
            target_id,
            "regiao.transformador_trifasico_poste_existente_avaliavel",
            value,
            origin,
            evidence=evidence,
            confidence=confidence,
        ),
    )


def _confirmed_transformer_post_pair(
    transformer: _TransformerCandidate,
    proposals: tuple[PropostaElemento, ...],
    session: SessaoRevisao,
    context: _RegionFactContext,
) -> _TransformerPostPair | None:
    related = tuple(
        relation
        for relation in session.projeto.relacoes_confirmadas
        if relation.tipo_relacao == "INSTALADO_EM" and relation.origem_id == transformer.element.id
    )
    if len(related) != 1 or related[0].destino_id != transformer.element.poste_id:
        return None
    pole = next(
        (
            item
            for item in session.projeto.elementos
            if item.id == related[0].destino_id and isinstance(item, Poste)
        ),
        None,
    )
    if pole is None:
        return None
    pole_proposals = tuple(
        item
        for item in proposals
        if item.categoria is CategoriaElemento.POSTE
        and context.confirmed_elements_by_proposal.get(item.id) == pole
    )
    if len(pole_proposals) != 1:
        return None
    pole_proposal = pole_proposals[0]
    if context.confirmed_elements_by_proposal.get(pole_proposal.id) != pole:
        return None
    return _TransformerPostPair(transformer, pole_proposal, pole)


def _transformer_post_facts(
    target_id: UUID,
    pair: _TransformerPostPair,
    session: SessaoRevisao,
    context: _RegionFactContext,
) -> tuple[FatoConformidade, ...]:
    equipment_proposal = pair.transformer.proposal
    pole_proposal = pair.pole_proposal

    pole_evidence = _proposal_evidence(pair.pole_proposal, context.evidence)
    equipment_evidence = _proposal_evidence(equipment_proposal, context.evidence)
    pair_evidence = tuple(
        dict.fromkeys((*equipment_evidence, *pole_evidence, *context.network_context.evidence))
    )
    confidence = _combined_confidence(
        equipment_proposal.confianca,
        pole_proposal.confianca,
        context.network_context.confidence,
    )
    facts: list[FatoConformidade] = [
        _fact(
            target_id,
            "regiao.transformador_trifasico_poste_existente_avaliavel",
            True,
            "relação confirmada 1:1 entre transformador e poste na região",
            evidence=pair_evidence,
            confidence=confidence,
            geometry=equipment_proposal.geometria,
        ),
        _fact(
            target_id,
            "regiao.transformador_potencia_kva",
            pair.transformer.power_kva,
            "código exato do transformador no catálogo técnico",
            evidence=equipment_evidence,
            confidence=equipment_proposal.confianca,
            geometry=equipment_proposal.geometria,
        ),
    ]
    pole_type = session.catalogo.item_por_id(pair.pole.tipo_catalogo_id)
    if isinstance(pole_type, TipoPoste):
        facts.append(
            _fact(
                target_id,
                "regiao.poste_transformador_resistencia_dan",
                pole_type.resistencia_dan,
                "tipo do poste confirmado e associado ao transformador",
                evidence=pole_evidence,
                confidence=pole_proposal.confianca,
                geometry=pole_proposal.geometria,
            )
        )
        post_format = context.post_format_options.get(pole_type.formato_opcao_id)
        if post_format:
            facts.append(
                _fact(
                    target_id,
                    "regiao.poste_transformador_formato",
                    post_format,
                    "formato canônico do tipo de poste confirmado",
                    evidence=pole_evidence,
                    confidence=pole_proposal.confianca,
                    geometry=pole_proposal.geometria,
                )
            )
    return tuple(facts)


def _combined_confidence(*values: Decimal | None) -> Decimal | None:
    known = tuple(item for item in values if item is not None)
    return min(known) if len(known) == len(values) else None


def _network_context(session: SessaoRevisao) -> _NetworkContext:
    metadata = session.projeto.metadados
    metadata_kind = (
        _context_kind(metadata.tipo_servico)
        if metadata is not None and metadata.tipo_servico
        else None
    )
    evidence_by_kind = _explicit_context_evidence(session.evidencias)
    document_kinds = {kind for kind, evidence in evidence_by_kind.items() if evidence}
    if len(document_kinds) > 1 or (
        metadata_kind is not None and document_kinds and metadata_kind not in document_kinds
    ):
        return _NetworkContext()
    if metadata_kind is not None:
        return _NetworkContext(
            urban=metadata_kind == "URBANA",
            rural=metadata_kind == "RURAL",
            origin="tipo de serviço do projeto",
            confidence=Decimal("1"),
        )
    if not document_kinds:
        return _NetworkContext()
    kind = next(iter(document_kinds))
    return _NetworkContext(
        urban=kind == "URBANA",
        rural=kind == "RURAL",
        origin="classificação explícita no cabeçalho do projeto",
        confidence=Decimal("0.95"),
        evidence=evidence_by_kind[kind],
    )


def _explicit_context_evidence(
    evidence: tuple[EvidenciaDocumento, ...],
) -> dict[str, tuple[EvidenciaDocumento, ...]]:
    project_text = tuple(
        item
        for item in evidence
        if item.tipo in _TEXT_TYPES
        and item.conteudo_bruto
        and not evidencia_eh_anotacao_de_revisao(item)
    )
    found: dict[str, list[EvidenciaDocumento]] = {"URBANA": [], "RURAL": []}
    for field in _header_labeled_fields(project_text):
        if _normalize_text(field.rotulo) not in _CONTEXT_FIELD_LABELS:
            continue
        kind = _context_kind(field.valor)
        if kind is not None:
            found[kind].extend(field.evidencias)
    return {kind: tuple(dict.fromkeys(items)) for kind, items in found.items()}


def _context_kind(value: str) -> str | None:
    normalized = _normalize_text(value)
    match = _CONTEXT_VALUE_PATTERN.fullmatch(normalized)
    if match is None:
        return None
    return "URBANA" if match.group(1).startswith("URBAN") else "RURAL"


def _risk_assessment_evidence(
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[EvidenciaDocumento, ...]:
    normalized = " ".join(_normalize_text(item.conteudo_bruto or "") for item in evidence)
    if "ABALROAMENTO" not in normalized or not any(
        token in normalized for token in ("RISCO", "AVALIACAO", "AVALIADO")
    ):
        return ()
    return tuple(
        item
        for item in evidence
        if any(
            token in _normalize_text(item.conteudo_bruto or "")
            for token in ("ABALROAMENTO", "RISCO", "AVALIACAO", "AVALIADO")
        )
    )


def _document_format(document: DocumentoProjeto) -> str | None:
    formats = tuple(_page_format(page) for page in document.paginas)
    known = tuple(item for item in formats if item is not None)
    return known[0] if known and len(set(known)) == 1 else None


def _page_format(page: PaginaDocumento) -> str | None:
    dimensions = sorted((float(page.largura_pontos), float(page.altura_pontos)))
    for label, raw in _ABNT_PAGE_SIZES.items():
        expected = sorted(raw)
        relative_error = max(
            abs(actual - target) / target
            for actual, target in zip(dimensions, expected, strict=True)
        )
        if relative_error <= 0.025:
            return label
    return None


def _fact(
    target_id: UUID,
    key: str,
    value: JsonPrimitive,
    origin: str,
    *,
    evidence: tuple[EvidenciaDocumento, ...] = (),
    confidence: Decimal | None = None,
    geometry: GeometriaDocumento | None = None,
) -> FatoConformidade:
    return criar_fato_conformidade(
        target_id,
        key,
        value,
        origin,
        evidencias=evidence,
        confianca=confidence,
        geometria=geometry,
    )


def _deduplicate_facts(facts: tuple[FatoConformidade, ...]) -> tuple[FatoConformidade, ...]:
    result: dict[tuple[UUID, str, object], FatoConformidade] = {}
    for fact in facts:
        key = (fact.alvo_id, fact.chave, fact.valor)
        previous = result.get(key)
        if previous is None or (fact.confianca or Decimal(0)) > (previous.confianca or Decimal(0)):
            result[key] = fact
    return tuple(result.values())


def _signature_summary(
    fields: tuple[EvidenciaDocumento, ...],
    signed: tuple[EvidenciaDocumento, ...],
    labels: tuple[EvidenciaDocumento, ...],
) -> str:
    if signed:
        return (
            f"{len(signed)} campo(s) PDF /Sig preenchido(s); "
            "validade criptográfica ainda não verificada"
        )
    if fields:
        return f"{len(fields)} campo(s) PDF /Sig vazio(s)"
    if labels:
        return f"{len(labels)} rótulo(s) textual(is); assinatura identificada pelo desenho"
    return "Nenhum campo ou rótulo localizado"


def _in_document_control_zone(geometry: GeometriaDocumento) -> bool:
    x, y = _center(geometry)
    return x >= 0.62 or y >= 0.76


def _combined_geometry(
    geometries: tuple[GeometriaDocumento, ...],
) -> GeometriaDocumento:
    page_id = geometries[0].pagina_id
    left = min(_bounds(item)[0] for item in geometries)
    top = min(_bounds(item)[1] for item in geometries)
    right = max(_bounds(item)[2] for item in geometries)
    bottom = max(_bounds(item)[3] for item in geometries)
    minimum = Decimal("0.001")
    maximum_origin = Decimal(1) - minimum
    x0 = min(Decimal(str(left)), maximum_origin)
    y0 = min(Decimal(str(top)), maximum_origin)
    x1 = min(Decimal(1), max(Decimal(str(right)), x0 + minimum))
    y1 = min(Decimal(1), max(Decimal(str(bottom)), y0 + minimum))
    return GeometriaDocumento.caixa(
        page_id,
        PontoNormalizado(x0, y0),
        PontoNormalizado(x1, y1),
    )


def _box_gap(left: GeometriaDocumento, right: GeometriaDocumento) -> float:
    left_x0, left_y0, left_x1, left_y1 = _bounds(left)
    right_x0, right_y0, right_x1, right_y1 = _bounds(right)
    dx = max(left_x0 - right_x1, right_x0 - left_x1, 0.0)
    dy = max(left_y0 - right_y1, right_y0 - left_y1, 0.0)
    return math.hypot(dx, dy)


def _bounds(geometry: GeometriaDocumento) -> tuple[float, float, float, float]:
    xs = tuple(float(point.x) for point in geometry.pontos)
    ys = tuple(float(point.y) for point in geometry.pontos)
    return min(xs), min(ys), max(xs), max(ys)


def _center(geometry: GeometriaDocumento) -> tuple[float, float]:
    left, top, right, bottom = _bounds(geometry)
    return (left + right) / 2, (top + bottom) / 2


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_marks.upper()).strip()
