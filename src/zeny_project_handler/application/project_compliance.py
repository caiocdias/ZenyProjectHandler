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
from zeny_project_handler.domain.catalog import JsonPrimitive, TipoCabo, TipoEquipamento
from zeny_project_handler.domain.compliance import (
    AchadoConformidade,
    AlvoConformidade,
    FatoConformidade,
    RegistroRegrasConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    SituacaoProjeto,
    TipoEvidencia,
    TipoOrigemPdf,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

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
_HEADER_ZONE_TOP = 0.76
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


@dataclass(frozen=True, slots=True, kw_only=True)
class ItemInspecaoDocumental:
    grupo: str
    campo: str
    valor: str
    estado: str
    documento_id: UUID
    pagina_id: UUID | None = None
    geometria: GeometriaDocumento | None = None
    evidencia_ids: tuple[UUID, ...] = ()
    confianca: Decimal | None = None


@dataclass(frozen=True, slots=True)
class _CampoRotuladoDocumento:
    rotulo: str
    valor: str
    evidencias: tuple[EvidenciaDocumento, ...]
    geometria: GeometriaDocumento


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoConformidadeProjeto:
    alvos: tuple[AlvoConformidade, ...]
    fatos: tuple[FatoConformidade, ...]
    achados: tuple[AchadoConformidade, ...]
    itens_documentais: tuple[ItemInspecaoDocumental, ...]


def analisar_conformidade_projeto(
    sessao: SessaoRevisao,
    registro: RegistroRegrasConformidade,
) -> ResultadoConformidadeProjeto:
    targets = _targets(sessao)
    project_target = next(item for item in targets if item.tipo is TipoEscopoConformidade.PROJETO)
    document_targets = {
        item.referencia_id: item
        for item in targets
        if item.tipo is TipoEscopoConformidade.DOCUMENTO
    }
    region_targets = {
        item.referencia_id: item for item in targets if item.tipo is TipoEscopoConformidade.REGIAO
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
    if _is_urban_context(sessao):
        facts.append(
            _fact(
                project_target.id,
                "rede.contexto_urbano",
                True,
                "tipo de serviço do projeto",
                confidence=Decimal("1"),
            )
        )
    detected_values: dict[str, list[tuple[str, EvidenciaDocumento | None]]] = {}
    for document in sessao.projeto.documentos:
        target = document_targets[document.id]
        document_evidence = evidence_by_document[document.id]
        fields = _extract_document_fields(document_evidence)
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
                document_evidence,
                physical_format=physical_format,
                metadata_values=metadata_values,
            )
        )
        document_facts, document_items = _document_control_facts(
            document, target.id, document_evidence
        )
        facts.extend(document_facts)
        items.extend(document_items)

    for key in _FIELD_LABELS:
        values = detected_values.get(key, ())
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

    facts.extend(
        _region_facts(
            sessao,
            region_targets=region_targets,
        )
    )
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


def _extract_document_fields(
    evidence: tuple[EvidenciaDocumento, ...],
) -> dict[str, list[tuple[str, EvidenciaDocumento]]]:
    text_evidence = tuple(
        item for item in evidence if item.tipo in _TEXT_TYPES and item.conteudo_bruto
    )
    searchable = _searchable_texts(text_evidence)
    found: dict[str, list[tuple[str, EvidenciaDocumento]]] = {}
    seen: set[tuple[str, str, UUID]] = set()
    for text, anchor in searchable:
        normalized = _normalize_text(text)
        for key, pattern in _FIELD_PATTERNS.items():
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
        and _center(item.geometria)[1] >= _HEADER_ZONE_TOP
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
    facts: list[FatoConformidade] = []
    items: list[ItemInspecaoDocumental] = []
    servitude = tuple(
        item
        for item in evidence
        if item.tipo in _TEXT_TYPES
        and any(
            token in _normalize_text(item.conteudo_bruto or "")
            for token in ("SERVIDAO", "FAIXA DE SERVIDAO", "FAIXA DE DOMINIO")
        )
    )
    if servitude:
        facts.append(
            _fact(
                target_id,
                "documento.servidao_mencionada",
                True,
                "menção textual",
                evidence=servitude,
                confidence=Decimal("0.90"),
            )
        )
    servitude_fields = _servitude_labeled_fields(evidence, servitude)
    if servitude_fields:
        items.extend(
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
            for field in servitude_fields
        )
    else:
        items.append(
            ItemInspecaoDocumental(
                grupo="Servidão",
                campo="Servidão / faixa de domínio",
                valor=(
                    f"{len(servitude)} menção(ões) localizada(s), sem campos rotulados"
                    if servitude
                    else "Nenhuma menção localizada; aplicabilidade ainda não determinada"
                ),
                estado="REQUER_REVISAO_VISUAL" if servitude else "NAO_AVALIAVEL",
                documento_id=document.id,
                pagina_id=servitude[0].pagina_id if servitude else None,
                geometria=servitude[0].geometria if servitude else None,
                evidencia_ids=tuple(item.id for item in servitude),
                confianca=Decimal("0.72") if servitude else None,
            )
        )

    stamps = tuple(
        item
        for item in evidence
        if item.origem_pdf.tipo is TipoOrigemPdf.ANOTACAO
        and (item.origem_pdf.subtipo_anotacao or "").casefold() == "stamp"
        and _in_document_control_zone(item.geometria)
    )
    facts.append(
        _fact(
            target_id,
            "documento.carimbo_candidato_quantidade",
            len(stamps),
            "anotações PDF Stamp na zona de cabeçalho/rodapé",
            evidence=stamps,
            confidence=Decimal("0.65"),
        )
    )
    items.append(
        ItemInspecaoDocumental(
            grupo="Carimbos e selos",
            campo="Candidatos gráficos",
            valor=(
                f"{len(stamps)} candidato(s) em zona documental"
                if stamps
                else "Nenhum candidato localizado"
            ),
            estado="REQUER_REVISAO_VISUAL" if stamps else "NAO_IDENTIFICADO",
            documento_id=document.id,
            pagina_id=stamps[0].pagina_id if stamps else None,
            geometria=stamps[0].geometria if stamps else None,
            evidencia_ids=tuple(item.id for item in stamps),
            confianca=Decimal("0.65") if stamps else None,
        )
    )

    signature_fields = tuple(
        item
        for item in evidence
        if dict(item.atributos_extraidos).get("tipo_campo_formulario") == "Sig"
    )
    signed_fields = tuple(
        item
        for item in signature_fields
        if dict(item.atributos_extraidos).get("campo_formulario_preenchido") is True
    )
    signature_labels = tuple(
        item
        for item in evidence
        if item.tipo in _TEXT_TYPES
        and any(
            token in _normalize_text(item.conteudo_bruto or "")
            for token in ("ASSINATURA", "RESPONSAVEL TECNICO", "CREA")
        )
    )
    if signed_fields:
        facts.append(
            _fact(
                target_id,
                "documento.assinatura_pdf_preenchida",
                True,
                "campo PDF /Sig preenchido",
                evidence=signed_fields,
                confidence=Decimal("0.98"),
            )
        )
    signature_evidence = (*signature_fields, *signature_labels)
    items.append(
        ItemInspecaoDocumental(
            grupo="Assinaturas",
            campo="Campos e indícios de assinatura",
            valor=_signature_summary(signature_fields, signed_fields, signature_labels),
            estado=(
                "ASSINATURA_PDF_PRESENTE"
                if signed_fields
                else ("REQUER_REVISAO_VISUAL" if signature_evidence else "NAO_IDENTIFICADO")
            ),
            documento_id=document.id,
            pagina_id=signature_evidence[0].pagina_id if signature_evidence else None,
            geometria=signature_evidence[0].geometria if signature_evidence else None,
            evidencia_ids=tuple(dict.fromkeys(item.id for item in signature_evidence)),
            confianca=(
                Decimal("0.98")
                if signed_fields
                else (Decimal("0.60") if signature_evidence else None)
            ),
        )
    )
    return tuple(facts), tuple(items)


def _region_facts(
    session: SessaoRevisao,
    *,
    region_targets: dict[UUID | None, AlvoConformidade],
) -> tuple[FatoConformidade, ...]:
    proposal_by_id = {
        item.id: item for item in session.propostas if isinstance(item, PropostaElemento)
    }
    technology_options = {
        option.id: option.codigo
        for group in session.catalogo.grupos_opcao
        if group.chave == "tecnologia_rede"
        for option in group.opcoes
    }
    equipment_class_options = {
        option.id: option.codigo
        for group in session.catalogo.grupos_opcao
        if group.chave == "classe_equipamento"
        for option in group.opcoes
    }
    facts = []
    urban_context = _is_urban_context(session)
    text_evidence = tuple(
        item for item in session.evidencias if item.tipo in _TEXT_TYPES and item.conteudo_bruto
    )
    for region in session.regioes:
        target = region_targets[region.id]
        nearby_text = tuple(
            item
            for item in text_evidence
            if item.pagina_id == region.pagina_id
            and _box_gap(region.geometria, item.geometria) <= _REGION_TEXT_DISTANCE
        )
        proposals = tuple(
            proposal_by_id[item_id] for item_id in region.elemento_ids if item_id in proposal_by_id
        )
        equipment_install = any(
            item.categoria is CategoriaElemento.EQUIPAMENTO
            and item.situacao_projeto is SituacaoProjeto.INSTALAR
            for item in proposals
        )
        facts.append(
            _fact(
                target.id,
                "regiao.equipamento_instalar",
                equipment_install,
                "elementos reconhecidos na região",
                evidence=tuple(
                    evidence
                    for item in proposals
                    if item.categoria is CategoriaElemento.EQUIPAMENTO
                    for evidence in session.evidencias
                    if evidence.id in item.evidencia_ids
                ),
                confidence=Decimal("0.90"),
            )
        )
        for proposal in proposals:
            if proposal.categoria is not CategoriaElemento.EQUIPAMENTO:
                continue
            item = (
                session.catalogo.item_por_id(proposal.tipo_catalogo_sugerido_id)
                if proposal.tipo_catalogo_sugerido_id is not None
                else None
            )
            if isinstance(item, TipoEquipamento):
                equipment_class = equipment_class_options.get(item.classe_equipamento_opcao_id)
                if equipment_class:
                    facts.append(
                        _fact(
                            target.id,
                            "regiao.equipamento_classe",
                            equipment_class,
                            "catálogo do equipamento reconhecido",
                            evidence=tuple(
                                evidence
                                for evidence in session.evidencias
                                if evidence.id in proposal.evidencia_ids
                            ),
                            confidence=proposal.confianca,
                        )
                    )
        if urban_context:
            facts.append(
                _fact(
                    target.id,
                    "rede.contexto_urbano",
                    True,
                    "tipo de serviço do projeto",
                    confidence=Decimal("1"),
                )
            )
        risk_evidence = _risk_assessment_evidence(nearby_text)
        if risk_evidence:
            facts.append(
                _fact(
                    target.id,
                    "regiao.risco_abalroamento_avaliado",
                    True,
                    "nota textual próxima ao equipamento",
                    evidence=risk_evidence,
                    confidence=Decimal("0.82"),
                )
            )
        for proposal in proposals:
            if proposal.categoria is not CategoriaElemento.CABO:
                continue
            item = (
                session.catalogo.item_por_id(proposal.tipo_catalogo_sugerido_id)
                if proposal.tipo_catalogo_sugerido_id is not None
                else None
            )
            if isinstance(item, TipoCabo):
                technology = technology_options.get(item.tecnologia_rede_opcao_id)
                if technology:
                    facts.append(
                        _fact(
                            target.id,
                            "cabo.tecnologia",
                            technology,
                            "catálogo do cabo reconhecido",
                            evidence=tuple(
                                evidence
                                for evidence in session.evidencias
                                if evidence.id in proposal.evidencia_ids
                            ),
                            confidence=proposal.confianca,
                        )
                    )
    return tuple(facts)


def _is_urban_context(session: SessaoRevisao) -> bool:
    metadata = session.projeto.metadados
    return bool(
        metadata and metadata.tipo_servico and "URBAN" in _normalize_text(metadata.tipo_servico)
    )


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
    evidence_ids = tuple(dict.fromkeys(item.id for item in evidence))
    identity = f"{key}:{value}:{origin}:{','.join(map(str, evidence_ids))}"
    return FatoConformidade(
        id=uuid5(target_id, identity),
        alvo_id=target_id,
        chave=key,
        valor=value,
        origem=origin,
        evidencia_ids=evidence_ids,
        confianca=confidence,
        geometria=geometry or (evidence[0].geometria if evidence else None),
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
        return f"{len(labels)} rótulo(s) textual(is); assinatura gráfica requer revisão visual"
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
