from __future__ import annotations

import json
from copy import deepcopy
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
from zeny_project_handler.adapters.persistence.schema import compliance_rule_revisions
from zeny_project_handler.application.compliance_registry import (
    ServicoRegistroRegrasConformidade,
)
from zeny_project_handler.application.errors import RegistroConformidadeError
from zeny_project_handler.domain.compliance import RegistroRegrasConformidade

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


def _registry_with_synthetic_rule() -> RegistroRegrasConformidade:
    payload = deepcopy(carregar_registro_conformidade_inicial().para_dict())
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


def test_removal_preserves_revision_and_never_reuses_stable_rule_number(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "numbers.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    service.inicializar(carregar_registro_conformidade_inicial())
    imported = service.importar(service.preparar_importacao(_registry_with_synthetic_rule()))
    before = {item.regra_id: item.numero for item in service.listar_numeros()}

    removed = service.remover_regra("fixture.projeto.circuito")
    assert all(item.id != "fixture.projeto.circuito" for item in removed.registro.regras)
    assert any(
        item.id == imported.id
        and any(rule.id == "fixture.projeto.circuito" for rule in item.registro.regras)
        for item in service.listar_historico()
    )
    catalog = service.caminho_catalogo.read_text(encoding="utf-8")
    assert f"Regra {before['fixture.projeto.circuito']}" in catalog
    assert "REMOVIDA" in catalog
    assert "when:" in catalog and "unless:" in catalog and "must:" in catalog

    reimported = service.importar(service.preparar_importacao(_registry_with_synthetic_rule()))
    after = {item.regra_id: item.numero for item in service.listar_numeros()}
    assert reimported.registro.regras[-1].id == "fixture.projeto.circuito"
    assert after["fixture.projeto.circuito"] == before["fixture.projeto.circuito"]
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


def test_export_is_schema_compatible_and_revision_rows_are_not_duplicated(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "export.sqlite3")
    upgrade_database(engine)
    service = _service(engine, tmp_path / "data", _Clock())
    service.inicializar(carregar_registro_conformidade_inicial())
    service.definir_regra_ativa("nd31.desenho.formato", ativa=False)
    exported = service.exportar(tmp_path / "out" / "registry.json")

    loaded = registro_conformidade_de_dict(json.loads(exported.read_text(encoding="utf-8")))
    assert not next(item for item in loaded.regras if item.id == "nd31.desenho.formato").ativa
    with engine.connect() as connection:
        count = connection.scalar(select(func.count()).select_from(compliance_rule_revisions))
    assert count == 2
    engine.dispose()
