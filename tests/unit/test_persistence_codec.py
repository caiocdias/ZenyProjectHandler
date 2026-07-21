from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from zeny_project_handler.adapters.persistence.domain_json import dumps_domain, loads_domain
from zeny_project_handler.adapters.persistence.errors import DomainCodecError
from zeny_project_handler.domain.enums import SituacaoProjeto
from zeny_project_handler.domain.project import Projeto


def test_codec_supports_tagged_values_lists_and_dictionaries() -> None:
    value = {
        "values": [
            UUID("12345678-1234-5678-1234-567812345678"),
            Decimal("1.25"),
            datetime(2026, 7, 21, tzinfo=UTC),
            date(2026, 7, 21),
            SituacaoProjeto.INSTALAR,
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
