import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest
from tests.factories import complete_project

from zeny_project_handler.adapters.persistence.domain_json import dumps_domain, loads_domain
from zeny_project_handler.adapters.persistence.errors import DomainCodecError
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    ModalidadeTrecho,
    OrigemComprimentoVao,
    SituacaoProjeto,
    TipoTrechoRede,
)
from zeny_project_handler.domain.project import Cabo, Projeto


def test_codec_supports_tagged_values_lists_and_dictionaries() -> None:
    value = {
        "values": [
            UUID("12345678-1234-5678-1234-567812345678"),
            Decimal("1.25"),
            datetime(2026, 7, 21, tzinfo=UTC),
            date(2026, 7, 21),
            SituacaoProjeto.INSTALAR,
            SituacaoProjeto.ALTERAR,
            OrigemComprimentoVao.ANOTACAO_DESENHO,
            TipoTrechoRede.RAMAL_CONEXAO,
            ModalidadeTrecho.AEREO,
        ]
    }

    assert loads_domain(dumps_domain(value), dict) == value


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        '{"$tuple":"invalid"}',
        '{"$enum":"Unknown","value":"X"}',
        '{"$type":"Unknown","fields":{}}',
        '{"$type":"Projeto","fields":[]}',
        '{"$uuid":"invalid"}',
    ],
)
def test_codec_rejects_malformed_or_unregistered_payload(payload: str) -> None:
    with pytest.raises(DomainCodecError):
        loads_domain(payload, object)


def test_codec_rejects_unsupported_values_and_unexpected_root_type() -> None:
    with pytest.raises(DomainCodecError, match="chaves textuais"):
        dumps_domain({1: "invalid"})
    with pytest.raises(DomainCodecError, match="não serializável"):
        dumps_domain({1, 2})
    with pytest.raises(DomainCodecError, match="esperado Projeto"):
        loads_domain("{}", Projeto)


def test_project_codec_preserves_service_codes_and_loads_legacy_payload() -> None:
    project = Projeto(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        nome="1234567890",
        catalogo_versao_id=UUID("87654321-4321-8765-4321-876543218765"),
        criado_em=datetime(2026, 8, 28, tzinfo=UTC),
        codigos_servico=("9012", "0007"),
    )

    assert loads_domain(dumps_domain(project), Projeto).codigos_servico == ("0007", "9012")

    legacy = cast(dict[str, Any], json.loads(dumps_domain(project)))
    fields = cast(dict[str, Any], legacy["fields"])
    fields.pop("codigos_servico")
    loaded = loads_domain(json.dumps(legacy), Projeto)

    assert loaded.codigos_servico == ()


def test_cable_codec_preserves_type_and_loads_missing_fields_as_unknown(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    cable = next(item for item in project.elementos if isinstance(item, Cabo))
    typed_cable = replace(
        cable,
        tipo_trecho=TipoTrechoRede.REDE_DISTRIBUICAO,
        modalidade=ModalidadeTrecho.AEREO,
    )
    typed_project = replace(
        project,
        elementos=tuple(typed_cable if item.id == cable.id else item for item in project.elementos),
    )

    loaded = loads_domain(dumps_domain(typed_project), Projeto)
    loaded_cable = next(item for item in loaded.elementos if isinstance(item, Cabo))
    assert loaded_cable.tipo_trecho is TipoTrechoRede.REDE_DISTRIBUICAO
    assert loaded_cable.modalidade is ModalidadeTrecho.AEREO

    legacy = cast(dict[str, Any], json.loads(dumps_domain(typed_project)))
    project_fields = cast(dict[str, Any], legacy["fields"])
    elements = cast(dict[str, Any], project_fields["elementos"])["$tuple"]
    legacy_cable = next(item for item in elements if item.get("$type") == "Cabo")
    cable_fields = cast(dict[str, Any], legacy_cable["fields"])
    cable_fields.pop("tipo_trecho")
    cable_fields.pop("modalidade")

    legacy_loaded = loads_domain(json.dumps(legacy), Projeto)
    legacy_loaded_cable = next(item for item in legacy_loaded.elementos if isinstance(item, Cabo))
    assert legacy_loaded_cable.tipo_trecho is TipoTrechoRede.DESCONHECIDO
    assert legacy_loaded_cable.modalidade is ModalidadeTrecho.DESCONHECIDO
