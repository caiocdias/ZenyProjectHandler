from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import IntegrityError

from zeny_project_handler.adapters.compliance import (
    carregar_registro_conformidade_inicial,
    registro_conformidade_de_dict,
)
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.adapters.persistence.errors import PersistenceConflictError
from zeny_project_handler.adapters.persistence.schema import compliance_rule_revisions
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.errors import RegistroConformidadeError
from zeny_project_handler.domain.compliance import (
    RegistroRegrasConformidade,
    RevisaoRegistroConformidade,
)

pytestmark = pytest.mark.integration


class _Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 12, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        result = self.value
        self.value += timedelta(seconds=1)
        return result


def _service(
    engine: Engine, data: Path, clock: _Clock | None = None
) -> ServicoRegistroRegrasConformidade:
    return ServicoRegistroRegrasConformidade(
        lambda: SqlAlchemyUnitOfWork(engine),
        diretorio_dados=data,
        relogio=clock,
        gerador_id=uuid4,
    )


def _registry_with_synthetic_rule(
    base: RegistroRegrasConformidade | None = None,
) -> RegistroRegrasConformidade:
    payload = deepcopy((base or carregar_registro_conformidade_inicial()).para_dict())
    registry = payload["registry"]
    assert isinstance(registry, dict)
    registry["id"] = str(uuid4())
    registry["version"] = "synthetic-1"
    rules = payload["rules"]
    assert isinstance(rules, list)
    rules.append(
        {
            "id": "fixture.projeto.circuito",
            "title": "Circuito informado",
            "description": "O projeto sintético deve informar o circuito.",
            "scope": "PROJETO",
            "severity": "ALERTA",
            "source": {
                "document": "Fixture pública",
                "revision": "1",
                "item": "1",
                "page": 1,
                "url": None,
            },
            "when": [],
            "unless": [],
            "must": [
                {
                    "fact": "projeto.circuito",
                    "operator": "EXISTE",
                    "expected": [],
                }
            ],
            "enabled": True,
        }
    )
    return registro_conformidade_de_dict(payload)


def _official_2025_5_registry(
    seed: RegistroRegrasConformidade,
) -> RegistroRegrasConformidade:
    payload = deepcopy(seed.para_dict())
    registry = payload["registry"]
    rules = payload["rules"]
    assert isinstance(registry, dict) and isinstance(rules, list)
    registry["version"] = "cemig-normas-distribuicao-2025.5"
    del rules[10:]
    by_id = {
        str(rule["id"]): rule
        for rule in rules
        if isinstance(rule, dict) and isinstance(rule.get("id"), str)
    }
    service_note = by_id["nd31.desenho.numero-projeto"]
    service_note["title"] = "Número do projeto com 10 dígitos"
    service_note["description"] = (
        "O desenho deve informar o número do projeto/Nota de Serviço com 10 dígitos."
    )
    service_note["when"] = [
        {
            "fact": "rede.contexto_urbano",
            "operator": "IGUAL",
            "expected": [True],
        }
    ]
    service_note["must"] = [
        {
            "fact": "projeto.nota_servico",
            "operator": "EXISTE",
            "expected": [],
        }
    ]
    by_id["nd31.desenho.escala"]["enabled"] = False
    angle_conditions = by_id["nd31.equipamento.estrutura-angulo"]["when"]
    cable_conditions = by_id["nd31.cabo.convencional-novo-urbano"]["when"]
    assert isinstance(angle_conditions, list) and isinstance(cable_conditions, list)
    angle_conditions[:] = [
        condition
        for condition in angle_conditions
        if not (
            isinstance(condition, dict)
            and condition.get("fact") == "conexao.angulo_graus"
            and condition.get("operator") == "EXISTE"
        )
    ]
    cable_conditions[:] = [
        condition
        for condition in cable_conditions
        if not (
            isinstance(condition, dict)
            and condition.get("fact") == "cabo.instalar_tecnologia"
            and condition.get("operator") == "EXISTE"
        )
    ]
    by_id["nd31.transformador.poste-existente-30-75"]["description"] = (
        "Na parcela verificável da observação t, transformadores trifásicos de 30, 45 ou 75 kVA "
        "a instalar em posteação existente exigem poste de formato admitido e capacidade nominal "
        "mínima de 300 daN; material PRFV e engastamento permanecem fora desta verificação."
    )
    by_id["nd31.transformador.poste-existente-150-300"]["description"] = (
        "Na parcela verificável da observação t, transformadores trifásicos de 150 ou 300 kVA a "
        "instalar em posteação existente exigem poste de seção circular e capacidade nominal "
        "mínima de 600 daN; material PRFV e engastamento permanecem fora desta verificação."
    )
    return registro_conformidade_de_dict(payload)


def _legacy_bundled_registry(seed: RegistroRegrasConformidade) -> RegistroRegrasConformidade:
    safe = _safe_2025_4_registry(seed)
    current_span = next(
        item for item in safe.regras if item.id == "nd31.vao.urbano-compacto-isolado"
    )
    legacy_span = replace(
        current_span,
        aplicabilidade=tuple(
            item
            for item in current_span.aplicabilidade
            if item.chave_fato != "vao.aplicabilidade_excecao_45_60_resolvida"
        ),
    )
    return replace(
        safe,
        versao="cemig-normas-distribuicao-2025.3",
        regras=tuple(legacy_span if item.id == legacy_span.id else item for item in safe.regras),
    )


def _safe_2025_4_registry(seed: RegistroRegrasConformidade) -> RegistroRegrasConformidade:
    previous = _official_2025_5_registry(seed)
    return replace(
        previous,
        versao="cemig-normas-distribuicao-2025.4",
        regras=previous.regras[:8],
    )


def _official_2025_6_registry(
    seed: RegistroRegrasConformidade,
) -> RegistroRegrasConformidade:
    return replace(
        seed,
        versao="cemig-normas-distribuicao-2025.6",
        regras=seed.regras[:39],
    )


def _official_2025_7_registry(
    seed: RegistroRegrasConformidade,
) -> RegistroRegrasConformidade:
    return replace(
        seed,
        versao="cemig-normas-distribuicao-2025.7",
        regras=seed.regras[:41],
    )


def _legacy_service_note_registry(
    seed: RegistroRegrasConformidade,
) -> RegistroRegrasConformidade:
    payload = deepcopy(seed.para_dict())
    rules = payload["rules"]
    assert isinstance(rules, list)
    rule = next(
        item
        for item in rules
        if isinstance(item, dict) and item.get("id") == "nd31.desenho.numero-projeto"
    )
    rule["title"] = "Número do projeto com 10 dígitos"
    rule["description"] = (
        "O desenho deve informar o número do projeto/Nota de Serviço com 10 dígitos."
    )
    rule["when"] = [
        {
            "fact": "rede.contexto_urbano",
            "operator": "IGUAL",
            "expected": [True],
        }
    ]
    rule["must"] = [
        {
            "fact": "projeto.nota_servico",
            "operator": "EXISTE",
            "expected": [],
        }
    ]
    return registro_conformidade_de_dict(payload)


def _registry_with_rule_enabled(rule_id: str, *, enabled: bool) -> RegistroRegrasConformidade:
    payload = deepcopy(carregar_registro_conformidade_inicial().para_dict())
    registry = payload["registry"]
    rules = payload["rules"]
    assert isinstance(registry, dict) and isinstance(rules, list)
    registry["id"] = str(uuid4())
    registry["version"] = f"enabled-{rule_id}-{enabled}"
    rule = next(item for item in rules if isinstance(item, dict) and item.get("id") == rule_id)
    rule["enabled"] = enabled
    return registro_conformidade_de_dict(payload)


def test_seed_is_idempotent_and_real_changes_preserve_immutable_history(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "registry.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    seed = carregar_registro_conformidade_inicial()

    first = service.inicializar(seed)
    second = service.inicializar(seed)

    assert first == second
    assert len(service.listar_historico()) == 1
    summary = service.preparar_importacao(_registry_with_synthetic_rule())
    changed = service.importar(summary)
    assert changed.id != first.id
    assert len(service.listar_historico()) == 2
    assert service.obter_revisao_ativa() == changed
    assert first.registro == service.listar_historico()[0].registro

    with engine.begin() as connection, pytest.raises(IntegrityError, match="imutavel"):
        connection.execute(
            update(compliance_rule_revisions)
            .where(compliance_rule_revisions.c.revision_id == str(first.id))
            .values(canonical_json="{}")
        )

    same = service.importar(service.preparar_importacao(changed.registro))
    assert same.id == changed.id
    assert len(service.listar_historico()) == 2
    engine.dispose()


def test_startup_migrates_only_unchanged_service_note_rule(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "service-note-rule-migration.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    seed = carregar_registro_conformidade_inicial()
    legacy = _legacy_service_note_registry(seed)
    initial = service.inicializar(legacy)

    migrated = service.inicializar(seed)

    assert migrated.id != initial.id
    migrated_rule = next(
        item for item in migrated.registro.regras if item.id == "nd31.desenho.numero-projeto"
    )
    seed_rule = next(item for item in seed.regras if item.id == migrated_rule.id)
    assert migrated_rule == seed_rule
    assert service.inicializar(seed) == migrated
    assert len(service.listar_historico()) == 2
    engine.dispose()


def test_startup_migrates_only_unchanged_legacy_span_rule_and_preserves_custom_rules(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine(tmp_path / "seed-migration.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    safe_seed = carregar_registro_conformidade_inicial()
    legacy_seed = _legacy_bundled_registry(safe_seed)
    service.inicializar(legacy_seed)
    customized = service.importar(
        service.preparar_importacao(_registry_with_synthetic_rule(legacy_seed))
    )

    migrated = service.inicializar(safe_seed)

    assert migrated.id != customized.id
    assert any(item.id == "fixture.projeto.circuito" for item in migrated.registro.regras)
    assert next(
        item for item in migrated.registro.regras if item.id == "nd31.vao.urbano-compacto-isolado"
    ) == next(item for item in safe_seed.regras if item.id == "nd31.vao.urbano-compacto-isolado")
    assert migrated.registro.versao == (
        "synthetic-1+seguranca-vao-2025.4+adicoes-2025.5+comparacao-ns-cabecalho"
        "+atualizacao-2025.6+adicoes-2025.6+adicoes-2025.7+adicoes-2026.1"
    )
    migrated_by_id = {item.id: item for item in migrated.registro.regras}
    assert all(migrated_by_id[item.id] == item for item in safe_seed.regras)
    assert len(service.listar_historico()) == 3
    assert service.inicializar(safe_seed) == migrated
    assert len(service.listar_historico()) == 3
    engine.dispose()


def test_startup_does_not_overwrite_a_custom_legacy_span_rule(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "custom-seed-migration.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    safe_seed = carregar_registro_conformidade_inicial()
    legacy_seed = _legacy_bundled_registry(safe_seed)
    legacy_span = next(
        item for item in legacy_seed.regras if item.id == "nd31.vao.urbano-compacto-isolado"
    )
    custom_span = replace(legacy_span, titulo="Limite de vão personalizado")
    custom_registry = replace(
        legacy_seed,
        id=uuid4(),
        versao="custom-span-rule",
        regras=tuple(
            custom_span if item.id == custom_span.id else item for item in legacy_seed.regras
        ),
    )
    initial = service.inicializar(custom_registry)

    after_restart = service.inicializar(safe_seed)

    assert after_restart.id != initial.id
    assert (
        next(item for item in after_restart.registro.regras if item.id == custom_span.id)
        == custom_span
    )
    migrated_by_id = {item.id: item for item in after_restart.registro.regras}
    assert all(
        migrated_by_id[item.id] == item for item in safe_seed.regras if item.id != custom_span.id
    )
    assert after_restart.registro.versao == (
        "custom-span-rule+adicoes-2025.5+comparacao-ns-cabecalho+atualizacao-2025.6"
        "+adicoes-2025.6+adicoes-2025.7+adicoes-2026.1"
    )
    assert len(service.listar_historico()) == 2
    engine.dispose()


def test_startup_migrates_2025_4_without_overwriting_a_colliding_2025_5_id(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine(tmp_path / "additive-seed-migration.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    seed = carregar_registro_conformidade_inicial()
    old = _safe_2025_4_registry(seed)
    colliding = replace(seed.regras[8], titulo="Regra local com ID futuro")
    customized = replace(
        old,
        id=uuid4(),
        versao="custom-2025.4",
        regras=(*old.regras, colliding),
    )
    initial = service.inicializar(customized)

    migrated = service.inicializar(seed)

    migrated_by_id = {item.id: item for item in migrated.registro.regras}
    assert migrated.id != initial.id
    assert migrated_by_id[colliding.id] == colliding
    assert migrated_by_id[seed.regras[9].id] == seed.regras[9]
    assert all(migrated_by_id[item.id] == item for item in seed.regras if item.id != colliding.id)
    assert migrated.registro.versao == (
        "custom-2025.4+adicoes-2025.5+comparacao-ns-cabecalho+atualizacao-2025.6"
        "+adicoes-2025.6+adicoes-2025.7+adicoes-2026.1"
    )
    numbers = {item.regra_id: item.numero for item in service.listar_numeros()}
    assert numbers[colliding.id] == 9
    assert numbers[seed.regras[9].id] == 10
    assert service.inicializar(seed) == migrated
    assert len(service.listar_historico()) == 2
    engine.dispose()


def test_startup_upgrades_unchanged_2025_4_registry_to_exact_2025_7_seed(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine(tmp_path / "official-seed-migration.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    seed = carregar_registro_conformidade_inicial()
    old = _safe_2025_4_registry(seed)
    initial = service.inicializar(old)

    migrated = service.inicializar(seed)

    assert migrated.id != initial.id
    assert migrated.registro.id == old.id
    assert migrated.registro.regras == seed.regras
    assert migrated.registro.versao == "cemig-normas-distribuicao-2026.1"
    assert service.inicializar(seed) == migrated
    assert len(service.listar_historico()) == 2
    engine.dispose()


def test_startup_upgrades_unchanged_2025_5_registry_to_exact_2025_7_seed(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine(tmp_path / "official-2025-5-migration.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    seed = carregar_registro_conformidade_inicial()
    old = _official_2025_5_registry(seed)
    initial = service.inicializar(old)

    migrated = service.inicializar(seed)

    assert migrated.id != initial.id
    assert migrated.registro.id == old.id
    assert migrated.registro == seed
    assert service.inicializar(seed) == migrated
    assert len(service.listar_historico()) == 2
    engine.dispose()


def test_startup_adds_2025_7_rules_after_existing_numbers_and_preserves_history(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine(tmp_path / "official-2025-6-migration.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    seed = carregar_registro_conformidade_inicial()
    previous = _official_2025_6_registry(seed)
    initial = service.inicializar(previous)
    numbers_before = {item.regra_id: item.numero for item in service.listar_numeros()}

    migrated = service.inicializar(seed)
    numbers_after = {item.regra_id: item.numero for item in service.listar_numeros()}

    assert migrated.id != initial.id
    assert migrated.registro == seed
    assert len(service.listar_historico()) == 2
    assert all(numbers_after[rule_id] == number for rule_id, number in numbers_before.items())
    assert numbers_after["bi.acoes.impacto-ambiental"] == 40
    assert numbers_after["bi.acoes.falta-servidao"] == 41
    assert numbers_after["nd51.ramal-conexao-aereo-comprimento"] == 42
    assert service.inicializar(seed) == migrated
    assert len(service.listar_historico()) == 2
    engine.dispose()


def test_startup_adds_2026_1_service_drop_rule_to_unchanged_2025_7_registry(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine(tmp_path / "official-2025-7-migration.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    seed = carregar_registro_conformidade_inicial()
    previous = _official_2025_7_registry(seed)
    initial = service.inicializar(previous)

    migrated = service.inicializar(seed)
    numbers = {item.regra_id: item.numero for item in service.listar_numeros()}

    assert migrated.id != initial.id
    assert migrated.registro == seed
    assert migrated.registro.regras[:-1] == previous.regras
    assert numbers["bi.acoes.falta-servidao"] == 41
    assert numbers["nd51.ramal-conexao-aereo-comprimento"] == 42
    assert len(service.listar_historico()) == 2
    assert service.inicializar(seed) == migrated
    engine.dispose()


def test_startup_preserves_custom_2025_5_rule_and_colliding_2025_6_id(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine(tmp_path / "custom-2025-5-migration.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    seed = carregar_registro_conformidade_inicial()
    old = _official_2025_5_registry(seed)
    old_angle = next(item for item in old.regras if item.id == "nd31.equipamento.estrutura-angulo")
    custom_angle = replace(old_angle, titulo="Ângulo avaliado por regra local")
    future_rule = seed.regras[10]
    colliding = replace(future_rule, titulo="Regra local com ID da versão 2025.6")
    customized = replace(
        old,
        id=uuid4(),
        versao="custom-2025.5",
        regras=(
            *(custom_angle if item.id == custom_angle.id else item for item in old.regras),
            colliding,
        ),
    )
    initial = service.inicializar(customized)

    migrated = service.inicializar(seed)

    migrated_by_id = {item.id: item for item in migrated.registro.regras}
    assert migrated.id != initial.id
    assert migrated_by_id[custom_angle.id] == custom_angle
    assert migrated_by_id[colliding.id] == colliding
    assert all(
        migrated_by_id[item.id] == item
        for item in seed.regras
        if item.id not in {custom_angle.id, colliding.id}
    )
    assert migrated.registro.versao == (
        "custom-2025.5+comparacao-ns-cabecalho+atualizacao-2025.6+adicoes-2025.6+adicoes-2025.7"
        "+adicoes-2026.1"
    )
    assert service.inicializar(seed) == migrated
    assert len(service.listar_historico()) == 2
    engine.dispose()


def test_import_omission_preserves_rules_and_stable_numbers(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "numbers.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    service.inicializar(carregar_registro_conformidade_inicial())
    imported = service.importar(service.preparar_importacao(_registry_with_synthetic_rule()))
    before = {item.regra_id: item.numero for item in service.listar_numeros()}

    omitted_from_file = carregar_registro_conformidade_inicial()
    merged = service.importar(service.preparar_importacao(omitted_from_file))

    assert imported.id != merged.id
    assert any(rule.id == "fixture.projeto.circuito" for rule in merged.registro.regras)
    assert not hasattr(service, "remover_regra")
    assert not hasattr(service, "definir_regra_ativa")
    catalog = service.caminho_catalogo.read_text(encoding="utf-8")
    assert f"Regra {before['fixture.projeto.circuito']}" in catalog
    assert "Importações que omitam IDs da revisão ativa preservam essas regras" in catalog
    assert "when:" in catalog and "unless:" in catalog and "must:" in catalog

    after = {item.regra_id: item.numero for item in service.listar_numeros()}
    assert after["fixture.projeto.circuito"] == before["fixture.projeto.circuito"]

    forbidden_registry = carregar_registro_conformidade_inicial()
    forbidden_revision = RevisaoRegistroConformidade(
        id=uuid4(),
        registro=forbidden_registry,
        assinatura=forbidden_registry.assinatura(),
        json_canonico=forbidden_registry.json_canonico(),
        criada_em=datetime(2026, 8, 12, 13, tzinfo=UTC),
        ativa=True,
    )
    with (
        pytest.raises(PersistenceConflictError, match="não pode remover IDs"),
        SqlAlchemyUnitOfWork(engine) as work,
    ):
        work.registros_conformidade.salvar_ativa(forbidden_revision)
        work.commit()
    assert service.obter_revisao_ativa().id == merged.id
    engine.dispose()


def test_catalog_write_failure_rolls_back_and_preserves_previous_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_sqlite_engine(tmp_path / "atomic.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    initial = service.inicializar(carregar_registro_conformidade_inicial())
    previous_catalog = service.caminho_catalogo.read_bytes()

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(
        "zeny_project_handler.application.compliance_registry.os.replace",
        fail_replace,
    )
    with pytest.raises(RegistroConformidadeError, match="publicar o catálogo"):
        service.importar(service.preparar_importacao(_registry_with_synthetic_rule()))

    assert service.obter_revisao_ativa().id == initial.id
    assert len(service.listar_historico()) == 1
    assert service.caminho_catalogo.read_bytes() == previous_catalog
    assert not any(
        item.name.startswith(".z-") for item in service.caminho_catalogo.parent.iterdir()
    )
    engine.dispose()


def test_database_commit_failure_restores_previous_catalog_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_sqlite_engine(tmp_path / "commit-atomic.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    initial = service.inicializar(carregar_registro_conformidade_inicial())
    previous_catalog = service.caminho_catalogo.read_bytes()
    import_summary = service.preparar_importacao(_registry_with_synthetic_rule())

    def fail_commit(_work: SqlAlchemyUnitOfWork) -> None:
        raise RuntimeError("interrupted commit")

    monkeypatch.setattr(SqlAlchemyUnitOfWork, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="interrupted commit"):
        service.importar(import_summary)

    assert service.obter_revisao_ativa() == initial
    assert service.listar_historico() == (initial,)
    assert service.caminho_catalogo.read_bytes() == previous_catalog
    assert not any(
        item.name.startswith(".z-") for item in service.caminho_catalogo.parent.iterdir()
    )
    engine.dispose()


def test_export_is_schema_compatible_and_revision_rows_are_not_duplicated(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "export.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    service.inicializar(carregar_registro_conformidade_inicial())
    service.importar(
        service.preparar_importacao(
            _registry_with_rule_enabled("nd31.desenho.formato", enabled=False)
        )
    )
    exported = service.exportar(tmp_path / "out" / "registry.json")

    loaded = registro_conformidade_de_dict(json.loads(exported.read_text(encoding="utf-8")))
    assert not next(item for item in loaded.regras if item.id == "nd31.desenho.formato").ativa
    with engine.connect() as connection:
        count = connection.scalar(select(func.count()).select_from(compliance_rule_revisions))
    assert count == 2
    engine.dispose()
