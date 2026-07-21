"""Leitura e escrita JSON explícita do conjunto de avaliação privado."""

from __future__ import annotations

import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoAnotacao,
    EstadoConjuntoAvaliacao,
    EstadoCriteriosAvaliacao,
    PapelAnotacao,
    ParticaoAvaliacao,
    SituacaoProjeto,
    TipoGeometria,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.evaluation import (
    AmostraAvaliacao,
    AnotacaoAmostra,
    CriteriosRegressaoAvaliacao,
    GeometriaAvaliacao,
    LimiteCategoriaAvaliacao,
    ManifestoAvaliacao,
    RotuloElementoAvaliacao,
    RotuloRelacaoAvaliacao,
)
from zeny_project_handler.domain.values import PontoNormalizado


class ArquivoAvaliacaoError(ValueError):
    """Arquivo ausente, malformado ou incompatível com o schema suportado."""


class JsonEvaluationDataset:
    def __init__(self, diretorio: Path) -> None:
        self._directory = diretorio.expanduser().resolve()

    def carregar_manifesto(self) -> ManifestoAvaliacao:
        payload = _load_object(self._directory / "manifesto-amostras.json")
        try:
            samples = tuple(_parse_sample(item) for item in _list(payload, "samples"))
            return ManifestoAvaliacao(
                schema_version=_integer(payload, "schema_version"),
                conjunto_id=_string(payload, "dataset_id"),
                versao=_string(payload, "dataset_version"),
                estado=EstadoConjuntoAvaliacao(_string(payload, "status")),
                politica_acesso=_string(payload, "access_policy"),
                criado_em=_datetime(payload, "created_at"),
                congelado_em=_optional_datetime(payload, "frozen_at"),
                amostras=samples,
            )
        except (KeyError, TypeError, ValueError, DomainValidationError) as error:
            raise ArquivoAvaliacaoError("Manifesto de avaliação inválido") from error

    def carregar_criterios(self) -> CriteriosRegressaoAvaliacao:
        payload = _load_object(self._directory / "criterios-regressao.json")
        try:
            thresholds = _object(payload, "thresholds")
            geometry = _object(payload, "geometry_matching")
            limits = tuple(
                LimiteCategoriaAvaliacao(
                    categoria=CategoriaElemento(_string(item, "category")),
                    precisao_minima=_decimal(item, "minimum_precision"),
                    recall_minimo=_decimal(item, "minimum_recall"),
                )
                for item in _list(payload, "per_category")
            )
            return CriteriosRegressaoAvaliacao(
                schema_version=_integer(payload, "schema_version"),
                versao=_string(payload, "criteria_version"),
                estado=EstadoCriteriosAvaliacao(_string(payload, "status")),
                limites_categoria=limits,
                precisao_relacoes_minima=_decimal(thresholds, "minimum_relation_precision"),
                recall_relacoes_minimo=_decimal(thresholds, "minimum_relation_recall"),
                taxa_falhas_extracao_maxima=_decimal(thresholds, "maximum_extraction_failure_rate"),
                latencia_p95_ms_maxima=_decimal(thresholds, "maximum_latency_p95_ms"),
                memoria_python_pico_bytes_maxima=_integer(
                    thresholds, "maximum_python_peak_memory_bytes"
                ),
                divergencia_humana_maxima=_decimal(thresholds, "maximum_human_divergence"),
                tolerancia_ponto=_decimal(geometry, "point_tolerance"),
                tolerancia_polilinha=_decimal(geometry, "polyline_tolerance"),
                iou_area_minimo=_decimal(geometry, "minimum_area_iou"),
            )
        except (KeyError, TypeError, ValueError, DomainValidationError) as error:
            raise ArquivoAvaliacaoError("Critérios de regressão inválidos") from error

    def carregar_anotacao(self, amostra_id: str, papel: PapelAnotacao) -> AnotacaoAmostra:
        return self.carregar_anotacao_do_caminho(self._annotation_path(amostra_id, papel))

    def carregar_anotacao_do_caminho(self, caminho: Path) -> AnotacaoAmostra:
        payload = _load_object(caminho)
        try:
            annotation = AnotacaoAmostra(
                schema_version=_integer(payload, "schema_version"),
                id=_string(payload, "annotation_id"),
                conjunto_id=_string(payload, "dataset_id"),
                conjunto_versao=_string(payload, "dataset_version"),
                amostra_id=_string(payload, "sample_id"),
                documento_sha256=_string(payload, "document_sha256"),
                papel=PapelAnotacao(_string(payload, "role")),
                estado=EstadoAnotacao(_string(payload, "status")),
                anotador_id=_string(payload, "annotator_id"),
                criada_em=_datetime(payload, "created_at"),
                revisada_em=_optional_datetime(payload, "reviewed_at"),
                revisor_id=_optional_string(payload, "reviewer_id"),
                elementos=tuple(_parse_element(item) for item in _list(payload, "elements")),
                relacoes=tuple(_parse_relation(item) for item in _list(payload, "relations")),
            )
        except (KeyError, TypeError, ValueError, DomainValidationError) as error:
            raise ArquivoAvaliacaoError("Anotação de avaliação inválida") from error
        return annotation

    def salvar_anotacao(self, anotacao: AnotacaoAmostra) -> Path:
        destination = self._annotation_path(anotacao.amostra_id, anotacao.papel)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".json.tmp")
        serialized = json.dumps(
            _annotation_dict(anotacao),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        try:
            temporary.write_text(f"{serialized}\n", encoding="utf-8")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def _annotation_path(self, sample_id: str, role: PapelAnotacao) -> Path:
        allowed = "abcdefghijklmnopqrstuvwxyz0123456789-"
        if not sample_id or any(character not in allowed for character in sample_id):
            raise ArquivoAvaliacaoError("ID de amostra inseguro para caminho")
        return self._directory / "annotations" / sample_id / f"{role.value.lower()}.json"


def _parse_sample(value: object) -> AmostraAvaliacao:
    payload = _as_object(value)
    return AmostraAvaliacao(
        id=_string(payload, "id"),
        sha256=_string(payload, "sha256"),
        tamanho_bytes=_integer(payload, "bytes"),
        total_paginas=_integer(payload, "pages"),
        particao=ParticaoAvaliacao(_string(payload, "split")),
        escala=_string(payload, "scale"),
        formato=_string(payload, "format"),
        orientacao=_string(payload, "orientation"),
        qualidade=_string(payload, "quality"),
        densidade=_string(payload, "density"),
        dupla_anotacao=_boolean(payload, "double_annotation"),
        casos_especiais=tuple(str(item) for item in payload.get("known_edge_cases", [])),
    )


def _parse_element(value: object) -> RotuloElementoAvaliacao:
    payload = _as_object(value)
    geometry = _object(payload, "geometry")
    points = tuple(
        PontoNormalizado(Decimal(str(point[0])), Decimal(str(point[1])))
        for point in _list(geometry, "points")
        if isinstance(point, list) and len(point) == 2
    )
    if len(points) != len(_list(geometry, "points")):
        raise TypeError("Pontos devem ser pares")
    return RotuloElementoAvaliacao(
        id=_string(payload, "id"),
        categoria=CategoriaElemento(_string(payload, "category")),
        situacao=SituacaoProjeto(_string(payload, "situation")),
        codigo_catalogo=_optional_string(payload, "catalog_code"),
        geometria=GeometriaAvaliacao(
            pagina_numero=_integer(payload, "page"),
            tipo=TipoGeometria(_string(geometry, "type")),
            pontos=points,
        ),
    )


def _parse_relation(value: object) -> RotuloRelacaoAvaliacao:
    payload = _as_object(value)
    return RotuloRelacaoAvaliacao(
        id=_string(payload, "id"),
        origem_id=_string(payload, "source_id"),
        destino_id=_string(payload, "target_id"),
        tipo_relacao=_string(payload, "type"),
        direcionada=_boolean(payload, "directed"),
    )


def _annotation_dict(annotation: AnotacaoAmostra) -> dict[str, object]:
    return {
        "schema_version": annotation.schema_version,
        "annotation_id": annotation.id,
        "dataset_id": annotation.conjunto_id,
        "dataset_version": annotation.conjunto_versao,
        "sample_id": annotation.amostra_id,
        "document_sha256": annotation.documento_sha256,
        "role": annotation.papel.value,
        "status": annotation.estado.value,
        "annotator_id": annotation.anotador_id,
        "created_at": annotation.criada_em.isoformat(),
        "reviewed_at": annotation.revisada_em.isoformat() if annotation.revisada_em else None,
        "reviewer_id": annotation.revisor_id,
        "elements": [_element_dict(item) for item in annotation.elementos],
        "relations": [_relation_dict(item) for item in annotation.relacoes],
    }


def _element_dict(element: RotuloElementoAvaliacao) -> dict[str, object]:
    return {
        "id": element.id,
        "category": element.categoria.value,
        "situation": element.situacao.value,
        "catalog_code": element.codigo_catalogo,
        "page": element.geometria.pagina_numero,
        "geometry": {
            "type": element.geometria.tipo.value,
            "points": [[str(point.x), str(point.y)] for point in element.geometria.pontos],
        },
    }


def _relation_dict(relation: RotuloRelacaoAvaliacao) -> dict[str, object]:
    return {
        "id": relation.id,
        "source_id": relation.origem_id,
        "target_id": relation.destino_id,
        "type": relation.tipo_relacao,
        "directed": relation.direcionada,
    }


def _load_object(path: Path) -> dict[str, Any]:
    try:
        return _as_object(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError) as error:
        raise ArquivoAvaliacaoError(f"Não foi possível carregar {path.name}") from error


def _as_object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Valor deve ser objeto JSON")
    return cast(dict[str, Any], value)


def _object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    return _as_object(payload[key])


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload[key]
    if not isinstance(value, list):
        raise TypeError(f"{key} deve ser lista")
    return value


def _string(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} deve ser texto")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} deve ser texto ou nulo")
    return value


def _integer(payload: dict[str, Any], key: str) -> int:
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} deve ser inteiro")
    return int(value)


def _boolean(payload: dict[str, Any], key: str) -> bool:
    value = payload[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} deve ser booleano")
    return value


def _decimal(payload: dict[str, Any], key: str) -> Decimal:
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError(f"{key} deve ser decimal")
    return Decimal(str(value))


def _datetime(payload: dict[str, Any], key: str) -> datetime:
    return datetime.fromisoformat(_string(payload, key))


def _optional_datetime(payload: dict[str, Any], key: str) -> datetime | None:
    value = _optional_string(payload, key)
    return datetime.fromisoformat(value) if value else None
