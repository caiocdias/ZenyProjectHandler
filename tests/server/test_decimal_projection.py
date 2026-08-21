"""Regressões da projeção de decimais do domínio para os contratos HTTP."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import uuid4

import pytest

from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler_contracts.common import NormalizedBoxDto
from zeny_project_handler_server.compliance_api import _box as compliance_box
from zeny_project_handler_server.review_api import _box as review_box


@pytest.mark.parametrize("project_box", (review_box, compliance_box))
def test_zero_extent_with_decimal_scale_is_projected_without_scientific_notation(
    project_box: Callable[[GeometriaDocumento], NormalizedBoxDto],
) -> None:
    geometry = GeometriaDocumento.ponto(
        uuid4(),
        PontoNormalizado(
            Decimal("0.12500000000000000"),
            Decimal("0.25000000000000000"),
        ),
    )

    box = project_box(geometry)

    assert box.width == "0.00000000000000000"
    assert box.height == "0.00000000000000000"
