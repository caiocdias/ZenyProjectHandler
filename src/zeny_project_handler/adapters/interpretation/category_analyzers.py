"""Analisadores pequenos, um para cada categoria do catálogo."""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid5

from zeny_project_handler.application.coordinate_pairs import detectar_pares_coordenadas
from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.catalog import ItemCatalogoType, TipoEquipamento, TipoPoste
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
    TipoGeometria,
)
from zeny_project_handler.domain.interpretation import RegraReconhecimento
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao

from .rule_support import (
    contains_code,
    geometry_distance,
    nearest_context_evidence,
    normalized_text,
    situation_from_evidence,
)
from .span_rules import detectar_comprimento_anotado

_POLE_DIMENSION_PATTERN = re.compile(
    r"(?<!\d)(9|10|11|12|13|15|18)\s*M?(?:\s*[-/:X]\s*|\s+)"
    r"(150|300|600|1000)\s*(?:DA?N)?(?!\d)"
)
_COORDINATE_CONTEXT_DISTANCE = 0.12
_CABLE_NOMENCLATURE_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:ABCN|ABN|BN|AN)-\d{1,3}\(\d{1,3}\)(?![A-Z0-9])"
)
_POLE_FORMAT_PHRASES = {
    "CIRCULAR": ("POSTE CIRCULAR", "CIRCULAR"),
    "DUPLO T": ("POSTE DUPLO T", "DUPLO T"),
    "MADEIRA": ("POSTE MADEIRA", "MADEIRA"),
}
_EQUIPMENT_PHRASES = (
    ("CHAVE FUSIVEL REPETIDORA", "CHAVE FUSIVEL REPETIDORA"),
    ("CHAVE FACA", "CHAVE FACA"),
    ("CHAVE FUSIVEL", "CHAVE FUSIVEL"),
    ("TRANSFORMADOR", "TRANSFORMADOR"),
)


class AnalisadorCatalogoPorCodigo:
    """Base reutilizável; subclasses fixam uma única categoria de responsabilidade."""

    nome = "codigo-catalogo"
    versao = "1.0"
    categoria: CategoriaElemento

    def analisar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        regra: RegraReconhecimento,
    ) -> tuple[PropostaElemento, ...]:
        if regra.estrategia != "CODIGO_CATALOGO":
            raise ValueError(f"Estratégia não suportada pelo analisador: {regra.estrategia}")
        items = sorted(
            solicitacao.catalogo.itens_ativos(self.categoria),
            key=lambda item: (-len(item.codigo), item.codigo.casefold()),
        )
        proposals: list[PropostaElemento] = []
        for evidence in sorted(solicitacao.evidencias, key=lambda item: str(item.id)):
            if evidence.tipo not in regra.tipos_evidencia or not evidence.conteudo_bruto:
                continue
            matches = tuple(
                item
                for item in items
                if self._matches_catalog_item(evidence.conteudo_bruto or "", item)
            )
            for item in matches:
                proposal = self._proposal(
                    solicitacao,
                    regra,
                    evidence,
                    item,
                    len(matches) > 1,
                )
                minimum = solicitacao.configuracao.confianca_minima
                if proposal.confianca is not None and proposal.confianca >= minimum:
                    proposals.append(proposal)
        return tuple(proposals)

    def _matches_catalog_item(self, text: str, item: ItemCatalogoType) -> bool:
        return contains_code(text, item.codigo)

    def _proposal(
        self,
        request: SolicitacaoInterpretacao,
        rule: RegraReconhecimento,
        evidence: EvidenciaDocumento,
        item: ItemCatalogoType,
        ambiguous: bool,
    ) -> PropostaElemento:
        contextual = nearest_context_evidence(
            evidence,
            request.evidencias,
            rule.distancia_contexto_maxima,
        )
        situation = None
        if contextual is not None:
            situation = situation_from_evidence(contextual, self.categoria, request.catalogo)
        if situation is None:
            situation = situation_from_evidence(evidence, self.categoria, request.catalogo)
        situation = situation or SituacaoProjeto.EXISTENTE
        context_ids = (contextual.id,) if contextual is not None else ()
        evidence_ids = tuple(sorted({evidence.id, *context_ids}, key=str))
        situation_bonus = (
            Decimal("0.08") if situation is not SituacaoProjeto.EXISTENTE else Decimal(0)
        )
        confidence = min(Decimal(1), rule.confianca_base + situation_bonus)
        geometry = (
            contextual.geometria
            if self.categoria is CategoriaElemento.CABO
            and contextual is not None
            and contextual.geometria.tipo is TipoGeometria.POLILINHA
            else evidence.geometria
        )
        proposal_id = uuid5(
            request.execucao_id,
            f"elemento:{rule.id}:{item.id}:{evidence.id}",
        )
        return PropostaElemento(
            id=proposal_id,
            execucao_id=request.execucao_id,
            categoria=self.categoria,
            situacao_projeto=situation,
            estado_revisao=EstadoRevisao.CONFLITANTE if ambiguous else EstadoRevisao.PROPOSTA,
            evidencia_ids=evidence_ids,
            geometria=geometry,
            tipo_catalogo_sugerido_id=item.id,
            codigo_observado=item.codigo,
            atributos_sugeridos=(
                ("registro_regras", request.registro.versao),
                ("regra_id", rule.id),
            ),
            confianca=confidence,
            justificativa=(
                f"A regra {rule.id} reconheceu exatamente o código {item.codigo} em texto ou OCR."
            ),
        )


class AnalisadorPoste(AnalisadorCatalogoPorCodigo):
    nome = "poste-codigo-e-nomenclatura"
    versao = "2.0"
    categoria = CategoriaElemento.POSTE

    def analisar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        regra: RegraReconhecimento,
    ) -> tuple[PropostaElemento, ...]:
        exact = super().analisar(solicitacao, regra)
        exact_evidence = {evidence_id for item in exact for evidence_id in item.evidencia_ids}
        proposals = list(exact)
        poles = tuple(
            item
            for item in solicitacao.catalogo.itens_ativos(self.categoria)
            if isinstance(item, TipoPoste)
        )
        option_codes = _option_codes(solicitacao, "formato_poste")
        for evidence in _semantic_evidence(solicitacao, regra):
            if evidence.id in exact_evidence:
                continue
            text = normalized_text(evidence.conteudo_bruto or "")
            dimensions = tuple(dict.fromkeys(_POLE_DIMENSION_PATTERN.findall(text)))
            for height_text, resistance_text in dimensions:
                matching = tuple(
                    item
                    for item in poles
                    if item.altura_m == Decimal(height_text)
                    and item.resistencia_dan == int(resistance_text)
                )
                matching = _filter_poles_by_format(
                    matching,
                    _pole_format_near(evidence, solicitacao),
                    option_codes,
                )
                if matching:
                    proposals.append(
                        _pole_dimension_proposal(
                            solicitacao,
                            regra,
                            evidence,
                            height_text,
                            resistance_text,
                            matching,
                        )
                    )
            if not dimensions:
                pole_format = _explicit_pole_format_from_text(text)
                if pole_format is not None:
                    matching = _filter_poles_by_format(poles, pole_format, option_codes)
                    proposals.append(
                        _untyped_phrase_proposal(
                            solicitacao,
                            regra,
                            evidence,
                            category=self.categoria,
                            observed=f"POSTE {pole_format}",
                            candidate_codes=tuple(item.codigo for item in matching),
                            attribute_name="formato_poste",
                            attribute_value=pole_format,
                            confidence=Decimal("0.58"),
                        )
                    )
        with_coordinates = tuple(_with_nearby_coordinate(item, solicitacao) for item in proposals)
        return tuple(
            item
            for item in with_coordinates
            if item.confianca is None or item.confianca >= solicitacao.configuracao.confianca_minima
        )


class AnalisadorEstruturaMt(AnalisadorCatalogoPorCodigo):
    nome = "estrutura-mt-codigo-catalogo"
    categoria = CategoriaElemento.ESTRUTURA_MT


class AnalisadorEstruturaBt(AnalisadorCatalogoPorCodigo):
    nome = "estrutura-bt-codigo-catalogo"
    categoria = CategoriaElemento.ESTRUTURA_BT


class AnalisadorCabo(AnalisadorCatalogoPorCodigo):
    nome = "cabo-codigo-e-nomenclatura"
    versao = "2.0"
    categoria = CategoriaElemento.CABO

    def analisar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        regra: RegraReconhecimento,
    ) -> tuple[PropostaElemento, ...]:
        exact = super().analisar(solicitacao, regra)
        exact_evidence = {evidence_id for item in exact for evidence_id in item.evidencia_ids}
        proposals = list(exact)
        for evidence in _semantic_evidence(solicitacao, regra):
            if evidence.id in exact_evidence:
                continue
            observed_codes = tuple(
                dict.fromkeys(
                    match.group(0)
                    for match in _CABLE_NOMENCLATURE_PATTERN.finditer(
                        normalized_text(evidence.conteudo_bruto or "")
                    )
                )
            )
            for observed in observed_codes:
                situation, evidence_ids = _situation_and_evidence(
                    solicitacao,
                    regra,
                    evidence,
                    self.categoria,
                )
                contextual = nearest_context_evidence(
                    evidence,
                    solicitacao.evidencias,
                    regra.distancia_contexto_maxima,
                )
                geometry = (
                    contextual.geometria
                    if contextual is not None
                    and contextual.geometria.tipo is TipoGeometria.POLILINHA
                    else evidence.geometria
                )
                proposals.append(
                    PropostaElemento(
                        id=uuid5(
                            solicitacao.execucao_id,
                            f"elemento:{regra.id}:nomenclatura:{evidence.id}:{observed}",
                        ),
                        execucao_id=solicitacao.execucao_id,
                        categoria=self.categoria,
                        situacao_projeto=situation,
                        estado_revisao=EstadoRevisao.CONFLITANTE,
                        evidencia_ids=evidence_ids,
                        geometria=geometry,
                        codigo_observado=observed,
                        atributos_sugeridos=(
                            ("catalogo_nao_localizado", True),
                            ("regra_id", regra.id),
                        ),
                        confianca=Decimal("0.66"),
                        justificativa=(
                            "A nomenclatura de cabo foi reconhecida, mas não existe uma "
                            "correspondência exata no catálogo publicado; requer classificação."
                        ),
                    )
                )
        with_lengths = tuple(_with_nearby_span_length(item, solicitacao) for item in proposals)
        return tuple(
            item
            for item in with_lengths
            if item.confianca is None or item.confianca >= solicitacao.configuracao.confianca_minima
        )


class AnalisadorEquipamento(AnalisadorCatalogoPorCodigo):
    nome = "equipamento-codigo-e-nomenclatura"
    versao = "2.0"
    categoria = CategoriaElemento.EQUIPAMENTO

    def _matches_catalog_item(self, text: str, item: ItemCatalogoType) -> bool:
        normalized = normalized_text(text)
        aliases = {item.codigo}
        if item.codigo.startswith("-"):
            aliases.add(item.codigo[1:])
        aliases.update(alias.replace(",", ".") for alias in tuple(aliases))
        return any(
            re.search(
                rf"(?<![A-Z0-9]){re.escape(normalized_text(alias))}"
                rf"(?:\s*KVA)?(?![A-Z0-9])",
                normalized,
            )
            is not None
            for alias in aliases
        )

    def analisar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        regra: RegraReconhecimento,
    ) -> tuple[PropostaElemento, ...]:
        exact = super().analisar(solicitacao, regra)
        exact_evidence = {item.evidencia_ids[0] for item in exact}
        option_codes = _option_codes(solicitacao, "classe_equipamento")
        equipment = tuple(
            item
            for item in solicitacao.catalogo.itens_ativos(self.categoria)
            if isinstance(item, TipoEquipamento)
        )
        proposals = list(exact)
        for evidence in _semantic_evidence(solicitacao, regra):
            if evidence.id in exact_evidence:
                continue
            text = normalized_text(evidence.conteudo_bruto or "")
            phrase = next((phrase for phrase, _ in _EQUIPMENT_PHRASES if phrase in text), None)
            if phrase is None:
                continue
            class_code = next(code for label, code in _EQUIPMENT_PHRASES if label == phrase)
            matching = tuple(
                item
                for item in equipment
                if option_codes.get(item.classe_equipamento_opcao_id) == class_code
            )
            proposals.append(
                _untyped_phrase_proposal(
                    solicitacao,
                    regra,
                    evidence,
                    category=self.categoria,
                    observed=phrase,
                    candidate_codes=tuple(item.codigo for item in matching),
                    attribute_name="classe_equipamento",
                    attribute_value=class_code,
                    confidence=Decimal("0.62"),
                )
            )
        return tuple(
            item
            for item in proposals
            if item.confianca is None or item.confianca >= solicitacao.configuracao.confianca_minima
        )


def _semantic_evidence(
    request: SolicitacaoInterpretacao, rule: RegraReconhecimento
) -> tuple[EvidenciaDocumento, ...]:
    return tuple(
        evidence
        for evidence in sorted(request.evidencias, key=lambda item: str(item.id))
        if evidence.tipo in rule.tipos_evidencia and evidence.conteudo_bruto
    )


def _option_codes(request: SolicitacaoInterpretacao, group_key: str) -> dict[UUID, str]:
    return {
        option.id: normalized_text(option.codigo)
        for group in request.catalogo.grupos_opcao
        if group.chave == group_key
        for option in group.opcoes
    }


def _format_from_text(text: str) -> str | None:
    return next(
        (code for code, phrases in _POLE_FORMAT_PHRASES.items() if any(p in text for p in phrases)),
        None,
    )


def _explicit_pole_format_from_text(text: str) -> str | None:
    return next(
        (code for code in _POLE_FORMAT_PHRASES if f"POSTE {code}" in text),
        None,
    )


def _pole_format_near(
    evidence: EvidenciaDocumento,
    request: SolicitacaoInterpretacao,
) -> str | None:
    direct = _format_from_text(normalized_text(evidence.conteudo_bruto or ""))
    if direct is not None:
        return direct
    nearby = sorted(
        (
            item
            for item in request.evidencias
            if item.id != evidence.id
            and item.tipo in {TipoEvidencia.TEXTO, TipoEvidencia.OCR}
            and item.pagina_id == evidence.pagina_id
            and item.conteudo_bruto
            and geometry_distance(evidence.geometria, item.geometria) <= 0.025
        ),
        key=lambda item: geometry_distance(evidence.geometria, item.geometria),
    )
    return next(
        (
            pole_format
            for item in nearby
            if (pole_format := _format_from_text(normalized_text(item.conteudo_bruto or "")))
            is not None
        ),
        None,
    )


def _filter_poles_by_format(
    poles: tuple[TipoPoste, ...],
    pole_format: str | None,
    option_codes: dict[UUID, str],
) -> tuple[TipoPoste, ...]:
    if pole_format is None:
        return poles
    return tuple(item for item in poles if option_codes.get(item.formato_opcao_id) == pole_format)


def _situation_and_evidence(
    request: SolicitacaoInterpretacao,
    rule: RegraReconhecimento,
    evidence: EvidenciaDocumento,
    category: CategoriaElemento,
) -> tuple[SituacaoProjeto, tuple[UUID, ...]]:
    contextual = nearest_context_evidence(
        evidence,
        request.evidencias,
        rule.distancia_contexto_maxima,
    )
    situation = (
        situation_from_evidence(contextual, category, request.catalogo)
        if contextual is not None
        else None
    )
    situation = situation or situation_from_evidence(evidence, category, request.catalogo)
    evidence_ids = tuple(
        sorted({evidence.id, *((contextual.id,) if contextual is not None else ())}, key=str)
    )
    return situation or SituacaoProjeto.EXISTENTE, evidence_ids


def _pole_dimension_proposal(
    request: SolicitacaoInterpretacao,
    rule: RegraReconhecimento,
    evidence: EvidenciaDocumento,
    height: str,
    resistance: str,
    matching: tuple[TipoPoste, ...],
) -> PropostaElemento:
    situation, evidence_ids = _situation_and_evidence(
        request, rule, evidence, CategoriaElemento.POSTE
    )
    unique = len(matching) == 1
    selected = matching[0]
    observed = f"{height}-{resistance}"
    return PropostaElemento(
        id=uuid5(request.execucao_id, f"elemento:{rule.id}:nomenclatura:{evidence.id}:{observed}"),
        execucao_id=request.execucao_id,
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=situation,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=evidence_ids,
        geometria=evidence.geometria,
        tipo_catalogo_sugerido_id=selected.id,
        codigo_observado=observed,
        atributos_sugeridos=(
            ("altura_m", height),
            ("candidatos_catalogo", ",".join(item.codigo for item in matching)),
            ("catalogo_inferido", not unique),
            ("regra_id", rule.id),
            ("resistencia_dan", int(resistance)),
        ),
        confianca=Decimal("0.86") if unique else Decimal("0.80"),
        justificativa=(
            "A nomenclatura de poste altura-resistência foi reconhecida em texto nativo ou OCR; "
            + (
                "o formato também foi identificado."
                if unique
                else (
                    f"o formato não estava explícito e {selected.codigo} foi escolhido "
                    "como correspondência canônica."
                )
            )
        ),
    )


def _with_nearby_coordinate(
    proposal: PropostaElemento,
    request: SolicitacaoInterpretacao,
) -> PropostaElemento:
    coordinate = _coordinate_near(proposal, request)
    if coordinate is None:
        return proposal
    east, north, evidence_ids = coordinate
    attributes = dict(proposal.atributos_sugeridos)
    attributes.update(
        {
            "coordenada_leste": east,
            "coordenada_norte": north,
            "coordenada_origem": "texto_ou_ocr",
        }
    )
    return replace(
        proposal,
        evidencia_ids=tuple(sorted({*proposal.evidencia_ids, *evidence_ids}, key=str)),
        atributos_sugeridos=tuple(attributes.items()),
    )


def _with_nearby_span_length(
    proposal: PropostaElemento,
    request: SolicitacaoInterpretacao,
) -> PropostaElemento:
    detected = detectar_comprimento_anotado(proposal.geometria, request.evidencias)
    if detected is None:
        return proposal
    length, evidence = detected
    attributes = dict(proposal.atributos_sugeridos)
    attributes.update(
        {
            "comprimento_m": length,
            "comprimento_origem": "anotacao_desenho",
            "evidencia_comprimento_id": str(evidence.id),
        }
    )
    return replace(
        proposal,
        evidencia_ids=tuple(sorted({*proposal.evidencia_ids, evidence.id}, key=str)),
        atributos_sugeridos=tuple(attributes.items()),
    )


def _coordinate_near(
    proposal: PropostaElemento,
    request: SolicitacaoInterpretacao,
) -> tuple[int, int, tuple[UUID, ...]] | None:
    pairs = detectar_pares_coordenadas(
        request.evidencias,
        distancia_maxima=_COORDINATE_CONTEXT_DISTANCE * 2,
        distancia_geometrias=geometry_distance,
    )
    nearby = tuple(
        pair
        for pair in pairs
        if pair.geometria_leste.pagina_id == proposal.geometria.pagina_id
        and max(
            geometry_distance(proposal.geometria, pair.geometria_leste),
            geometry_distance(proposal.geometria, pair.geometria_norte),
        )
        <= _COORDINATE_CONTEXT_DISTANCE
    )
    if not nearby:
        return None
    selected = min(
        nearby,
        key=lambda pair: (
            max(
                geometry_distance(proposal.geometria, pair.geometria_leste),
                geometry_distance(proposal.geometria, pair.geometria_norte),
            ),
            pair.leste,
            pair.norte,
        ),
    )
    return selected.leste, selected.norte, selected.evidencia_ids


def _untyped_phrase_proposal(
    request: SolicitacaoInterpretacao,
    rule: RegraReconhecimento,
    evidence: EvidenciaDocumento,
    *,
    category: CategoriaElemento,
    observed: str,
    candidate_codes: tuple[str, ...],
    attribute_name: str,
    attribute_value: str,
    confidence: Decimal,
) -> PropostaElemento:
    situation, evidence_ids = _situation_and_evidence(request, rule, evidence, category)
    return PropostaElemento(
        id=uuid5(request.execucao_id, f"elemento:{rule.id}:frase:{evidence.id}:{observed}"),
        execucao_id=request.execucao_id,
        categoria=category,
        situacao_projeto=situation,
        estado_revisao=EstadoRevisao.CONFLITANTE,
        evidencia_ids=evidence_ids,
        geometria=evidence.geometria,
        codigo_observado=observed,
        atributos_sugeridos=(
            (attribute_name, attribute_value),
            ("candidatos_catalogo", ",".join(candidate_codes)),
            ("regra_id", rule.id),
        ),
        confianca=confidence,
        justificativa=(
            "A classe ou formato foi reconhecido em texto nativo ou OCR; "
            "o tipo exato requer revisão humana."
        ),
    )
