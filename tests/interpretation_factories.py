"""Fixtures determinísticas do pipeline de interpretação."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid5

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def text_evidence(
    *,
    execution_id: UUID,
    page_id: UUID,
    key: str,
    text: str,
    x: str,
    y: str,
    color: str = "#000000",
    rotation: str = "0",
) -> EvidenciaDocumento:
    return EvidenciaDocumento(
        id=uuid5(execution_id, key),
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=TipoEvidencia.TEXTO,
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal(x), Decimal(y)),
        ),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto=text,
        criada_em=datetime(2026, 7, 21, 12, tzinfo=UTC),
        atributos_extraidos=(
            ("cor", color),
            ("rotacao_graus", Decimal(rotation)),
        ),
    )


def vector_evidence(
    *,
    execution_id: UUID,
    page_id: UUID,
    key: str,
    points: tuple[tuple[str, str], ...],
    color: str = "#000000",
) -> EvidenciaDocumento:
    return EvidenciaDocumento(
        id=uuid5(execution_id, key),
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=TipoEvidencia.VETOR,
        geometria=GeometriaDocumento.polilinha(
            page_id,
            tuple(PontoNormalizado(Decimal(x), Decimal(y)) for x, y in points),
        ),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto="linha",
        criada_em=datetime(2026, 7, 21, 12, tzinfo=UTC),
        atributos_extraidos=(("cor_contorno", color),),
    )


def image_evidence(
    *,
    execution_id: UUID,
    page_id: UUID,
    key: str,
    x: str,
    y: str,
) -> EvidenciaDocumento:
    return EvidenciaDocumento(
        id=uuid5(execution_id, key),
        execucao_id=execution_id,
        pagina_id=page_id,
        tipo=TipoEvidencia.IMAGEM,
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal(x), Decimal(y)),
        ),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto="hash-imagem",
        criada_em=datetime(2026, 7, 21, 12, tzinfo=UTC),
    )
