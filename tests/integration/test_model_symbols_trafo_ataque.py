# mypy: disable-error-code="no-untyped-call"
"""E06.3.3.2.2, Task 4, ataque do testador: pacotes reais, R-2 e sensibilidade da fusao (R-5)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.fixtures.symbol_grammars import triangulo as fixture
from tests.fixtures.symbol_grammars.triangulo import (
    CASOS_TRIANGULO,
    GRUPOS,
    Grupo,
    desenhar_grupo,
    variantes_do_grupo,
)
from tests.integration.test_model_symbols_trafo_runner import _de_trafo, _id_grupo, _rodar

from zeny_project_handler.application.symbol_reconciliation import _same_occurrence

pytestmark = pytest.mark.integration

_RAIZ = Path(__file__).resolve().parents[2]


def _variantes_f02_18() -> list[dict[str, object]]:
    pasta = _RAIZ / "src/zeny_project_handler/adapters/analysis/symbol_packages"
    dados = json.loads((pasta / "family-f02-18.json").read_text(encoding="utf-8"))
    return list(dados["variants"])


def test_f02_18_tem_27_variantes_15_habilitadas_e_12_pendentes_com_razao() -> None:
    variantes = _variantes_f02_18()
    assert len(variantes) == 27
    enabled = {v["id"] for v in variantes if v["recognition"]["status"] == "enabled"}  # type: ignore[index]
    assert enabled == {i for i, _ in CASOS_TRIANGULO}
    for v in variantes:
        reconhecimento = v["recognition"]
        assert isinstance(reconhecimento, dict)
        if v["id"] in enabled:
            assert set(reconhecimento) == {"status", "grammar", "negative_examples"}, v["id"]
        else:
            assert reconhecimento["status"] == "pending", v["id"]
            assert str(reconhecimento["reason"]).strip(), v["id"]
            assert "grammar" not in reconhecimento, v["id"]


def test_negativos_das_15_sao_os_confundiveis_do_inventario() -> None:
    inventario = json.loads(
        (_RAIZ / "docs/data/inventario-simbologia-v1.json").read_text(encoding="utf-8")
    )
    confundiveis: dict[str, list[str]] = {}

    def varre(no: object) -> None:
        if isinstance(no, dict):
            if "confusable_negatives" in no and "id" in no:
                confundiveis[str(no["id"])] = no["confusable_negatives"]
            for filho in no.values():
                varre(filho)
        elif isinstance(no, list):
            for filho in no:
                varre(filho)

    varre(inventario)
    for v in _variantes_f02_18():
        if v["id"] in {i for i, _ in CASOS_TRIANGULO}:
            esperado = confundiveis[str(v["id"])]
            assert esperado
            assert v["recognition"]["negative_examples"] == esperado, v["id"]  # type: ignore[index]


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_grupo_reconcilia_em_review_com_referencia_ambigua_e_template_do_menor_id(
    tmp_path: Path, grupo: Grupo
) -> None:
    composto, novo, _ = _rodar(tmp_path, desenhar_grupo, grupo)
    (modelo,) = [o for o in _de_trafo(composto) if o.metodo_assinatura == novo]
    menor = min(variantes_do_grupo(grupo))
    atributos = dict(modelo.atributos)
    assert atributos["variante_inventario"] == menor
    (ocorrencia,) = [o for o in composto.occurrences if modelo in o.observations]
    assert ocorrencia.decision == "review"
    assert "ambiguous_reference_id" in ocorrencia.reasons
    assert set(ocorrencia.reference_ids) >= variantes_do_grupo(grupo)


# Sensibilidade (R-5): com o X nominal (0,7 do lado) a fusao nao acontece; encurtando o X
# para 0,7 do nominal ainda nao; a partir de 0,6 do nominal ela passa a fundir. Caracteriza,
# nao recomenda: o valor fixado em test_fusao_com_o_e05 continua o do X nominal.
@pytest.mark.parametrize("fill", ["outline", "half_cyan"])
@pytest.mark.parametrize(
    ("fator", "ocorrencias"),
    [(1.0, 2), (0.8, 2), (0.7, 2), (0.6, 1), (0.3, 1)],
    ids=lambda v: str(v),
)
def test_sensibilidade_da_fusao_ao_tamanho_do_x(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fill: str,
    fator: float,
    ocorrencias: int,
) -> None:
    grupo: Grupo = (fill, "none", True)
    monkeypatch.setattr(fixture, "MEIO_X", fixture.MEIO_X * fator)
    composto, novo, legados = _rodar(tmp_path, fixture.desenhar_trafo_e05, grupo)
    de_trafo = _de_trafo(composto)
    (modelo,) = [o for o in de_trafo if o.metodo_assinatura == novo]
    (e05,) = [o for o in de_trafo if o.metodo_assinatura in legados]
    ocupadas = [o for o in composto.occurrences if any(x in de_trafo for x in o.observations)]
    assert len(ocupadas) == ocorrencias
    assert _same_occurrence(modelo, e05) == (ocorrencias == 1)
