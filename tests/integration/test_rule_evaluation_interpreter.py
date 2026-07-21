from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from tests.pdf_fixtures import create_analysis_pdf

from zeny_project_handler.adapters.evaluation import InterpretadorRegrasAvaliacao
from zeny_project_handler.adapters.interpretation import carregar_registro_regras_inicial
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, ParticaoAvaliacao
from zeny_project_handler.domain.evaluation import AmostraAvaliacao

pytestmark = pytest.mark.integration


def test_real_pipeline_adapter_produces_benchmark_labels_deterministically(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> None:
    source = create_analysis_pdf(tmp_path / "evaluation.pdf")
    content = source.read_bytes()
    sample = AmostraAvaliacao(
        id="amostra-sintetica",
        sha256=sha256(content).hexdigest(),
        tamanho_bytes=len(content),
        total_paginas=2,
        particao=ParticaoAvaliacao.DESENVOLVIMENTO,
        escala="1:1000",
        formato="A4",
        orientacao="PAISAGEM",
        qualidade="ALTA",
        densidade="MEDIA",
    )
    interpreter = InterpretadorRegrasAvaliacao(
        catalogo_inicial,
        carregar_registro_regras_inicial(),
    )

    first = interpreter.interpretar(sample, source)
    second = interpreter.interpretar(sample, source)

    assert first == second
    assert any(item.categoria is CategoriaElemento.ESTRUTURA_MT for item in first.elementos)
    assert all(item.geometria.pagina_numero <= sample.total_paginas for item in first.elementos)
