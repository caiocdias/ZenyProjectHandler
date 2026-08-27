from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from zeny_project_handler.adapters.compliance import (
    carregar_registro_conformidade_inicial,
    registro_conformidade_de_dict,
)
from zeny_project_handler.domain.compliance import DisponibilidadeProvedorFato
from zeny_project_handler.domain.compliance_facts import (
    CATALOGO_FATOS_CONFORMIDADE,
    validar_semantica_registro,
)
from zeny_project_handler.domain.errors import DomainValidationError


def _seed_payload() -> dict[str, object]:
    return deepcopy(carregar_registro_conformidade_inicial().para_dict())


def _first_condition(payload: dict[str, object]) -> dict[str, object]:
    rules = payload["rules"]
    assert isinstance(rules, list)
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        conditions = rule.get("when")
        if not isinstance(conditions, list):
            continue
        for condition in conditions:
            if (
                isinstance(condition, dict)
                and condition.get("fact") == "rede.contexto_urbano"
                and condition.get("operator") == "IGUAL"
            ):
                return condition
    raise AssertionError("O catálogo não contém a condição booleana usada pelo teste")


def test_fact_catalog_covers_current_and_planned_seed_vocabulary() -> None:
    registry = carregar_registro_conformidade_inicial()
    definitions = {item.chave: item for item in CATALOGO_FATOS_CONFORMIDADE}
    used = {
        condition.chave_fato
        for rule in registry.regras
        for condition in (*rule.aplicabilidade, *rule.excecoes, *rule.requisitos)
    }

    assert used <= definitions.keys()
    assert definitions["projeto.nota_servico"].disponibilidade is (
        DisponibilidadeProvedorFato.DISPONIVEL
    )
    assert definitions["vao.comprimento_m"].disponibilidade is (
        DisponibilidadeProvedorFato.DISPONIVEL
    )
    assert (
        definitions["regiao.transformador_trifasico_poste_existente_avaliavel"].disponibilidade
        is DisponibilidadeProvedorFato.DISPONIVEL
    )
    assert definitions["regiao.poste_transformador_resistencia_dan"].disponibilidade is (
        DisponibilidadeProvedorFato.DISPONIVEL
    )
    assert definitions["conexao.angulo_graus"].disponibilidade is (
        DisponibilidadeProvedorFato.DISPONIVEL
    )
    warnings = validar_semantica_registro(registry)
    assert not any("conexao.angulo_graus" in item for item in warnings)
    assert all("vao.comprimento_m" not in item for item in warnings)


def test_official_2025_6_seed_contains_the_complete_additive_rule_set() -> None:
    registry = carregar_registro_conformidade_inicial()
    expected_additions = {
        "nd31.desenho.numero-folha",
        "nd31.desenho.data-projeto",
        "nd31.desenho.circuito",
        "nd31.poste.urbano-altura-minima",
        "nd31.poste.urbano-formato-circular",
        "nd31.equipamento.poste-novo-altura",
        "nd31.equipamento.poste-novo-resistencia",
        "catalogo.compatibilidade.estrutura-cabo",
        "nd31.transformador.chave-fusivel",
        "nd31.transformador.para-raios-bt",
        "nd31.transformador.para-raios-mt",
        "nd31.transformador.aterramento",
        "pacote.coerencia.transformador-potencia",
        "pacote.coerencia.fases",
        "pacote.coerencia.codigo",
        "pacote.coerencia.circuito",
        "pacote.documentacao.gd",
        "pacote.documentacao.prordr-fotos",
        "nd31.rede.neutro-aterramento-200m",
        "nd31.rede.compacta-aterramento-temporario-160m",
    }

    assert registry.versao == "cemig-normas-distribuicao-2025.6"
    assert len(registry.regras) == 39
    assert expected_additions <= {item.id for item in registry.regras}


def test_every_semantically_rural_or_urban_rule_has_the_matching_guard() -> None:
    registry = carregar_registro_conformidade_inicial()
    market_facts = {"rede.contexto_rural", "rede.contexto_urbano"}
    guarded_counts: Counter[str] = Counter()

    for rule in registry.regras:
        declared_guards = {
            condition.chave_fato
            for condition in rule.aplicabilidade
            if condition.chave_fato in market_facts
        }
        semantic_text = f"{rule.id} {rule.titulo} {rule.descricao}".casefold()
        expected_guards = {
            guard
            for marker, guard in (
                ("rural", "rede.contexto_rural"),
                ("urban", "rede.contexto_urbano"),
            )
            if marker in semantic_text
        }

        assert expected_guards <= declared_guards, rule.id
        assert len(declared_guards) <= 1, rule.id
        guarded_counts.update(declared_guards)

    assert guarded_counts == Counter(
        {
            "rede.contexto_urbano": 16,
            "rede.contexto_rural": 6,
        }
    )

    evaluator = (
        Path(__file__).parents[2]
        / "src"
        / "zeny_project_handler"
        / "application"
        / "compliance_evaluation.py"
    ).read_text(encoding="utf-8")
    assert all(fact not in evaluator for fact in market_facts)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("fact", "projeto.chave_inventada", "chave de fato desconhecida"),
        ("operator", "MAIOR", "operador MAIOR incompatível"),
        ("expected", ["sim"], "valor incompatível com BOOLEANO"),
    ],
)
def test_semantic_validation_rejects_unknown_incompatible_or_wrongly_typed_conditions(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = _seed_payload()
    _first_condition(payload)[field] = value

    with pytest.raises(DomainValidationError, match=message):
        registro_conformidade_de_dict(payload)


def test_schema_validation_reports_duplicate_rule_id_atomically() -> None:
    payload = _seed_payload()
    rules = payload["rules"]
    assert isinstance(rules, list)
    rules.append(deepcopy(rules[0]))

    with pytest.raises(DomainValidationError, match=r"campo id.*ID duplicado"):
        registro_conformidade_de_dict(payload)


def test_schema_rejects_executable_or_unknown_fields_without_evaluating_them() -> None:
    payload = _seed_payload()
    rules = payload["rules"]
    assert isinstance(rules, list)
    rule = rules[0]
    assert isinstance(rule, dict)
    rule["python"] = "__import__('pathlib').Path('executed').write_text('bad')"

    with pytest.raises(DomainValidationError, match="campo não permitido: python"):
        registro_conformidade_de_dict(payload)


def test_canonical_signature_keeps_declared_condition_order() -> None:
    registry = carregar_registro_conformidade_inicial()
    payload = registry.para_dict()
    rules = payload["rules"]
    assert isinstance(rules, list)
    rule = rules[3]
    assert isinstance(rule, dict)
    conditions = rule["when"]
    assert isinstance(conditions, list)
    rule["when"] = list(reversed(conditions))
    reordered = registro_conformidade_de_dict(payload)

    assert reordered.assinatura() != registry.assinatura()


def test_decimal_expected_value_remains_a_schema_number_on_export() -> None:
    payload = _seed_payload()
    rules = payload["rules"]
    assert isinstance(rules, list)
    span_rule = next(
        item
        for item in rules
        if isinstance(item, dict) and item.get("id") == "nd31.vao.urbano-compacto-isolado"
    )
    assert isinstance(span_rule, dict)
    must = span_rule["must"]
    assert isinstance(must, list)
    condition = must[0]
    assert isinstance(condition, dict)
    condition["expected"] = [45.5]

    registry = registro_conformidade_de_dict(payload)
    exported = registry.para_dict()
    reparsed = registro_conformidade_de_dict(exported)

    exported_rules = exported["rules"]
    assert isinstance(exported_rules, list)
    exported_span = next(
        item
        for item in exported_rules
        if isinstance(item, dict) and item.get("id") == "nd31.vao.urbano-compacto-isolado"
    )
    assert isinstance(exported_span, dict)
    exported_must = exported_span["must"]
    assert isinstance(exported_must, list)
    exported_condition = exported_must[0]
    assert isinstance(exported_condition, dict)
    assert exported_condition["expected"] == [45.5]
    assert reparsed == registry
