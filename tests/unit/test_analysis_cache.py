from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from zeny_project_handler.adapters.analysis import JsonAnalysisCache
from zeny_project_handler.domain.analysis import DiagnosticoAnalise, OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    ExtracaoDocumentoNormalizada,
    GeometriaNormalizada,
)


def _extraction() -> ExtracaoDocumentoNormalizada:
    return ExtracaoDocumentoNormalizada(
        candidatos=(
            CandidatoEvidenciaDocumento(
                chave_estavel="p1:texto:0",
                pagina_numero=1,
                tipo=TipoEvidencia.TEXTO,
                geometria=GeometriaNormalizada(
                    tipo=TipoGeometria.CAIXA,
                    pontos=(
                        PontoNormalizado(Decimal("0.1"), Decimal("0.2")),
                        PontoNormalizado(Decimal("0.3"), Decimal("0.4")),
                    ),
                ),
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto="P1",
                atributos_extraidos=(
                    ("peso", Decimal("0.75")),
                    ("visivel", True),
                ),
            ),
        ),
        diagnosticos=(
            DiagnosticoAnalise(
                codigo="teste.parcial",
                mensagem="Falha localizada",
                extrator="teste",
                pagina_numero=1,
            ),
        ),
    )


def test_json_cache_round_trip_and_malformed_payload(tmp_path: Path) -> None:
    cache = JsonAnalysisCache(tmp_path / "cache")
    key = "a" * 64

    assert cache.obter(key) is None
    cache.salvar(key, _extraction())
    assert cache.obter(key) == _extraction()

    (tmp_path / "cache" / f"{key}.json").write_text("not-json", encoding="utf-8")
    assert cache.obter(key) is None


def test_json_cache_rejects_unsafe_key(tmp_path: Path) -> None:
    cache = JsonAnalysisCache(tmp_path)
    with pytest.raises(ValueError, match="SHA-256"):
        cache.salvar("../escape", _extraction())
