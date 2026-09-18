"""Compatibilidade da persistência anterior ao contrato interno de símbolos."""

import json
from decimal import Decimal
from uuid import UUID

from zeny_project_handler.adapters.persistence.domain_json import dumps_domain, loads_domain
from zeny_project_handler.domain.analysis import EvidenciaDocumento, OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia


def test_pre_symbol_contract_evidence_json_still_loads() -> None:
    # Snapshot do formato anterior: nenhum campo de observação/método E03.
    page_id = "12345678-1234-5678-1234-567812345678"
    payload = {
        "$type": "EvidenciaDocumento",
        "fields": {
            "id": {"$uuid": "22345678-1234-5678-1234-567812345678"},
            "execucao_id": {"$uuid": "32345678-1234-5678-1234-567812345678"},
            "pagina_id": {"$uuid": page_id},
            "tipo": {"$enum": "TipoEvidencia", "value": "VETOR"},
            "geometria": {
                "$type": "GeometriaDocumento",
                "fields": {
                    "pagina_id": {"$uuid": page_id},
                    "tipo": {"$enum": "TipoGeometria", "value": "PONTO"},
                    "pontos": {
                        "$tuple": [
                            {
                                "$type": "PontoNormalizado",
                                "fields": {
                                    "x": {"$decimal": "0.12"},
                                    "y": {"$decimal": "0.34"},
                                },
                            }
                        ]
                    },
                },
            },
            "metodo": "pymupdf-nativo",
            "versao_metodo": "1.18.0",
            "parametros": {"$tuple": []},
            "conteudo_bruto": "ATERRAMENTO",
            "criada_em": {"$datetime": "2026-09-18T12:00:00+00:00"},
            "atributos_extraidos": {
                "$tuple": [
                    {"$tuple": ["confianca", {"$decimal": "0.88"}]},
                    {"$tuple": ["reconhecido_por_simbologia", True]},
                ]
            },
        },
    }

    restored = loads_domain(json.dumps(payload), EvidenciaDocumento)

    assert restored.pagina_id == UUID(page_id)
    assert restored.tipo is TipoEvidencia.VETOR
    assert restored.origem_pdf == OrigemObjetoPdf()
    assert restored.artefato is None
    assert restored.conteudo_bruto == "ATERRAMENTO"
    assert dict(restored.atributos_extraidos)["confianca"] == Decimal("0.88")
    assert loads_domain(dumps_domain(restored), EvidenciaDocumento) == restored
