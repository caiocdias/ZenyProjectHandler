from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from zeny_project_handler.application.coordinate_pairs import detectar_pares_coordenadas
from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado


def _evidence(page_id: UUID, text: str, x: str) -> EvidenciaDocumento:
    return EvidenciaDocumento(
        id=uuid4(),
        execucao_id=uuid4(),
        pagina_id=page_id,
        tipo=TipoEvidencia.TEXTO,
        geometria=GeometriaDocumento.ponto(
            page_id,
            PontoNormalizado(Decimal(x), Decimal("0.4")),
        ),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto=text,
        criada_em=datetime(2026, 7, 23, tzinfo=UTC),
    )


def _distance(left: GeometriaDocumento, right: GeometriaDocumento) -> float:
    return abs(float(left.pontos[0].x - right.pontos[0].x))


def test_pairs_multiple_nearby_coordinates_without_reusing_or_crossing_values() -> None:
    page_id = uuid4()
    east_1 = _evidence(page_id, "280653", "0.10")
    north_1 = _evidence(page_id, "7683008", "0.11")
    east_2 = _evidence(page_id, "465702", "0.30")
    north_2 = _evidence(page_id, "7772468", "0.31")

    pairs = detectar_pares_coordenadas(
        (east_1, north_2, east_2, north_1),
        distancia_maxima=0.25,
        distancia_geometrias=_distance,
    )

    assert {(item.leste, item.norte) for item in pairs} == {
        (280653, 7683008),
        (465702, 7772468),
    }
    assert len({evidence_id for pair in pairs for evidence_id in pair.evidencia_ids}) == 4


def test_pairs_values_in_their_original_order_inside_one_fragment() -> None:
    page_id = uuid4()
    evidence = _evidence(
        page_id,
        "280653/7683008 465702:7772468",
        "0.20",
    )

    pairs = detectar_pares_coordenadas(
        (evidence,),
        distancia_maxima=0,
        distancia_geometrias=_distance,
    )

    assert [(item.leste, item.norte) for item in pairs] == [
        (280653, 7683008),
        (465702, 7772468),
    ]
