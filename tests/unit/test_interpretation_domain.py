from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from zeny_project_handler.adapters.interpretation import (
    JsonRuleRegistry,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.ports.interpretation import ConfiguracaoInterpretacao


def test_initial_rule_registry_is_complete_and_has_stable_signature() -> None:
    first = carregar_registro_regras_inicial()
    second = carregar_registro_regras_inicial()

    assert {rule.categoria for rule in first.regras_reconhecimento} == set(CategoriaElemento)
    assert first.assinatura() == second.assinatura()
    assert len(first.assinatura()) == 64
    assert first.regra_da_categoria(CategoriaElemento.POSTE).id == "poste-codigo-catalogo"


def test_rule_registry_and_configuration_reject_ambiguous_limits() -> None:
    registry = carregar_registro_regras_inicial()

    with pytest.raises(DomainValidationError, match="únicos"):
        replace(
            registry,
            regras_relacao=(registry.regras_relacao[0], registry.regras_relacao[0]),
        )
    with pytest.raises(ValueError, match="Confiança"):
        ConfiguracaoInterpretacao(confianca_minima=Decimal("-1"))
    with pytest.raises(ValueError, match="Máximo"):
        ConfiguracaoInterpretacao(maximo_propostas=0)


def test_rule_repository_can_load_an_external_user_selected_file() -> None:
    project_root = Path(__file__).parents[2]
    rules_path = (
        project_root
        / "src"
        / "zeny_project_handler"
        / "adapters"
        / "interpretation"
        / "data"
        / "regras_interpretacao_v1.json"
    )

    external = JsonRuleRegistry(rules_path).carregar()
    embedded = JsonRuleRegistry().carregar()

    assert external == embedded
