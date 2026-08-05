from __future__ import annotations

import json
from pathlib import Path

import pytest

from zeny_project_handler.adapters.evaluation import ArquivoAvaliacaoError, JsonEvaluationDataset
from zeny_project_handler.domain.enums import PapelAnotacao

PROJECT_ROOT = Path(__file__).parents[2]


def test_annotation_template_round_trips_atomically(tmp_path: Path) -> None:
    source_repository = JsonEvaluationDataset(PROJECT_ROOT / "evaluation")
    annotation = source_repository.carregar_anotacao_do_caminho(
        PROJECT_ROOT / "evaluation" / "annotation-template.json"
    )
    repository = JsonEvaluationDataset(tmp_path)

    saved = repository.salvar_anotacao(annotation)
    restored = repository.carregar_anotacao(annotation.amostra_id, PapelAnotacao.PRIMARIA)

    assert restored == annotation
    assert saved.name == "primaria.json"
    assert not tuple(saved.parent.glob(".z-*"))


def test_malformed_annotation_is_rejected(tmp_path: Path) -> None:
    malformed = tmp_path / "invalid.json"
    malformed.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    with pytest.raises(ArquivoAvaliacaoError, match="inválida"):
        JsonEvaluationDataset(tmp_path).carregar_anotacao_do_caminho(malformed)


def test_sample_id_cannot_escape_annotation_directory(tmp_path: Path) -> None:
    repository = JsonEvaluationDataset(tmp_path)

    with pytest.raises(ArquivoAvaliacaoError, match="inseguro"):
        repository.carregar_anotacao("../fora", PapelAnotacao.CONSENSO)
