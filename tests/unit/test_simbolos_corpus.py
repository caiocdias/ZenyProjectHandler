"""Tradução da cobertura de um método em falha, para o benchmark de símbolos."""

from __future__ import annotations

from decimal import Decimal

import pytest
from scripts.simbolos_corpus import falha_da_cobertura

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import CoberturaMetodoSimbolos, FonteObservacaoSimbolo
from zeny_project_handler.domain.values import PontoNormalizado

_ACEITOS = {EstadoMetodoSimbolos.CONCLUIDO, EstadoMetodoSimbolos.NAO_DETECCAO}


def _cobertura(estado: EstadoMetodoSimbolos, motivo: str | None) -> CoberturaMetodoSimbolos:
    return CoberturaMetodoSimbolos(
        fonte=FonteObservacaoSimbolo(
            documento_id="doc", documento_sha256="0" * 64, pagina_numero=1, camada="c"
        ),
        regiao_normalizada=(PontoNormalizado(Decimal("0.1"), Decimal("0.1")),),
        classes_avaliadas=("poste",),
        estado=estado,
        motivo=motivo,
    )


@pytest.mark.parametrize("estado", list(EstadoMetodoSimbolos), ids=lambda e: e.value)
def test_falha_da_cobertura(estado: EstadoMetodoSimbolos) -> None:
    cobertura = _cobertura(estado, "sem fonte")
    esperado = None if estado in _ACEITOS else "sem fonte"
    assert falha_da_cobertura(cobertura) == esperado
