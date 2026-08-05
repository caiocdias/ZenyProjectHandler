"""Cache JSON derivado, descartável e independente do banco principal."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from zeny_project_handler._atomic_files import sibling_temporary_file
from zeny_project_handler.domain.analysis import DiagnosticoAnalise, OrigemObjetoPdf
from zeny_project_handler.domain.catalog import JsonPrimitive
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria, TipoOrigemPdf
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    ExtracaoDocumentoNormalizada,
    GeometriaNormalizada,
)

_CACHE_KEY = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_VERSION = 1


class JsonAnalysisCache:
    """Persiste somente resultados reproduzíveis; ausência ou corrupção equivale a cache vazio."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory.expanduser().resolve()

    def obter(self, chave: str) -> ExtracaoDocumentoNormalizada | None:
        target = self._target(chave)
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if raw.get("schema_version") != _SCHEMA_VERSION:
                return None
            return _decode_extraction(cast(dict[str, Any], raw))
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def salvar(self, chave: str, extracao: ExtracaoDocumentoNormalizada) -> None:
        target = self._target(chave)
        self._directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            _encode_extraction(extracao),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with sibling_temporary_file(target) as temporary_path:
            temporary_path.write_text(payload, encoding="utf-8")
            temporary_path.replace(target)

    def _target(self, chave: str) -> Path:
        if not _CACHE_KEY.fullmatch(chave):
            raise ValueError("Chave de cache deve ser um SHA-256 hexadecimal")
        return self._directory / f"{chave}.json"


def _encode_extraction(extraction: ExtracaoDocumentoNormalizada) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "candidatos": [_encode_candidate(item) for item in extraction.candidatos],
        "diagnosticos": [_encode_diagnostic(item) for item in extraction.diagnosticos],
    }


def _encode_candidate(candidate: CandidatoEvidenciaDocumento) -> dict[str, Any]:
    return {
        "chave_estavel": candidate.chave_estavel,
        "pagina_numero": candidate.pagina_numero,
        "tipo": candidate.tipo.value,
        "geometria": {
            "tipo": candidate.geometria.tipo.value,
            "pontos": [[str(point.x), str(point.y)] for point in candidate.geometria.pontos],
        },
        "origem_pdf": {
            "tipo": candidate.origem_pdf.tipo.value,
            "numero_objeto": candidate.origem_pdf.numero_objeto,
            "indice_anotacao": candidate.origem_pdf.indice_anotacao,
            "subtipo_anotacao": candidate.origem_pdf.subtipo_anotacao,
            "nome_recurso": candidate.origem_pdf.nome_recurso,
        },
        "conteudo_bruto": candidate.conteudo_bruto,
        "atributos_extraidos": [
            [key, _encode_extra(value)] for key, value in candidate.atributos_extraidos
        ],
    }


def _encode_diagnostic(diagnostic: DiagnosticoAnalise) -> dict[str, Any]:
    return {
        "codigo": diagnostic.codigo,
        "mensagem": diagnostic.mensagem,
        "extrator": diagnostic.extrator,
        "pagina_numero": diagnostic.pagina_numero,
        "objeto_xref": diagnostic.objeto_xref,
    }


def _encode_extra(value: JsonPrimitive) -> object:
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    return value


def _decode_extraction(raw: dict[str, Any]) -> ExtracaoDocumentoNormalizada:
    candidates = tuple(_decode_candidate(cast(dict[str, Any], item)) for item in raw["candidatos"])
    diagnostics = tuple(
        DiagnosticoAnalise(**cast(dict[str, Any], item)) for item in raw["diagnosticos"]
    )
    return ExtracaoDocumentoNormalizada(candidatos=candidates, diagnosticos=diagnostics)


def _decode_candidate(raw: dict[str, Any]) -> CandidatoEvidenciaDocumento:
    raw_geometry = cast(dict[str, Any], raw["geometria"])
    raw_origin = cast(dict[str, Any], raw["origem_pdf"])
    points = tuple(PontoNormalizado(Decimal(x), Decimal(y)) for x, y in raw_geometry["pontos"])
    extras = tuple((str(key), _decode_extra(value)) for key, value in raw["atributos_extraidos"])
    return CandidatoEvidenciaDocumento(
        chave_estavel=str(raw["chave_estavel"]),
        pagina_numero=int(raw["pagina_numero"]),
        tipo=TipoEvidencia(str(raw["tipo"])),
        geometria=GeometriaNormalizada(
            tipo=TipoGeometria(str(raw_geometry["tipo"])), pontos=points
        ),
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf(str(raw_origin["tipo"])),
            numero_objeto=_optional_int(raw_origin.get("numero_objeto")),
            indice_anotacao=_optional_int(raw_origin.get("indice_anotacao")),
            subtipo_anotacao=_optional_string(raw_origin.get("subtipo_anotacao")),
            nome_recurso=_optional_string(raw_origin.get("nome_recurso")),
        ),
        conteudo_bruto=_optional_string(raw.get("conteudo_bruto")),
        atributos_extraidos=extras,
    )


def _decode_extra(value: object) -> JsonPrimitive:
    if isinstance(value, dict) and set(value) == {"decimal"}:
        return Decimal(str(value["decimal"]))
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ValueError("Atributo extra inválido no cache")


def _optional_int(value: object) -> int | None:
    return int(str(value)) if value is not None else None


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None
