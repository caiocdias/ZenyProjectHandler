"""R-E07.2.1-3 e 4 de ponta a ponta: o que `generate_relations` recebe por regime.

Cada caso monta uma folha sintética pequena e roda `InterpretadorFichaPoste` pelo
`ExecutarPipelineInterpretacao`. Um espião em `generate_relations` (o importado pela subclasse)
registra a geometria dos postes entregue a cada regra de relação: as de `CENTROS_PROXIMOS`
(estrutura e equipamento) devem ver o poste na posição do texto; as demais, no disco do desenho
quando ancorado.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine
from tests.integration.test_ficha_poste_cadeia import (
    _atributos,
    _cabo,
    _centro,
    _disco,
    _elementos,
    _estrutura,
    _executar,
    _folha_com_disco,
    _poste,
    _texto,
)
from tests.integration.test_golden_padrao_e07 import _VERDE

from zeny_project_handler.adapters.interpretation.relation_rules import generate_relations
from zeny_project_handler.adapters.persistence import create_sqlite_engine, upgrade_database
from zeny_project_handler.application.interpretation_pipeline import ResultadoExecucaoInterpretacao
from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento

pytestmark = pytest.mark.integration

_TEXTO = "CENTROS_PROXIMOS"
Ponto = tuple[float, float]


@dataclass
class _Espiao:
    """Postes vistos por cada estratégia: estratégia -> lista de {id do poste: centro}."""

    chamadas: dict[str, list[dict[UUID, Ponto]]] = field(default_factory=dict)

    def por_regime(self, *, texto: bool) -> list[dict[UUID, Ponto]]:
        return [
            postes
            for estrategia, lista in self.chamadas.items()
            for postes in lista
            if (estrategia == _TEXTO) is texto
        ]


@pytest.fixture
def espiao(monkeypatch: pytest.MonkeyPatch) -> _Espiao:
    original: Callable[..., Any] = generate_relations
    visto = _Espiao()

    def gravar(
        execucao_id: UUID, elementos: tuple[PropostaElemento, ...], registro: Any, *resto: Any
    ) -> Any:
        (regra,) = registro.regras_relacao
        visto.chamadas.setdefault(regra.estrategia, []).append(
            {
                item.id: _centro(item)
                for item in elementos
                if item.categoria is CategoriaElemento.POSTE
            }
        )
        return original(execucao_id, elementos, registro, *resto)

    monkeypatch.setattr(
        "zeny_project_handler.adapters.interpretation.ficha_poste.generate_relations", gravar
    )
    return visto


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    motor = create_sqlite_engine(tmp_path / "regimes.sqlite3")
    upgrade_database(motor)
    try:
        yield motor
    finally:
        motor.dispose()


def _rodar(
    engine: Engine, catalogo: CatalogoTecnico, folha: tuple[EvidenciaDocumento, ...]
) -> ResultadoExecucaoInterpretacao:
    resultado, _ = _executar(engine, catalogo, folha)
    return resultado


def _centros(espiao: _Espiao, poste: UUID, *, texto: bool) -> set[Ponto]:
    """Centros do poste em todas as chamadas do regime, arredondados."""
    return {
        (round(centro[0], 6), round(centro[1], 6))
        for postes in espiao.por_regime(texto=texto)
        for identificador, centro in postes.items()
        if identificador == poste
    }


def _poste_de(resultado: ResultadoExecucaoInterpretacao, identificador: str) -> PropostaElemento:
    (poste,) = (
        item
        for item in _elementos(resultado, CategoriaElemento.POSTE)
        if _atributos(item)["identificador_operacional"] == identificador
    )
    return poste


def _posicao_do_texto(poste: PropostaElemento) -> Ponto:
    x, y = (float(parte) for parte in str(_atributos(poste)["poste_texto_centro"]).split(","))
    return (round(x, 6), round(y, 6))


def test_ancorado_entrega_o_texto_ao_regime_de_texto_e_o_disco_ao_demais(
    engine: Engine, catalogo_inicial: CatalogoTecnico, espiao: _Espiao
) -> None:
    resultado = _rodar(engine, catalogo_inicial, _folha_com_disco(catalogo_inicial, (0.305, 0.30)))
    poste = _poste_de(resultado, "P1")

    assert _atributos(poste)["poste_ancorado_disco"] is True
    assert espiao.por_regime(texto=True)
    assert espiao.por_regime(texto=False)
    assert _centros(espiao, poste.id, texto=True) == {(0.30, 0.30)}
    assert _centros(espiao, poste.id, texto=False) == {(0.305, 0.30)}


def test_sem_candidato_entrega_a_posicao_do_texto_aos_dois_regimes(
    engine: Engine, catalogo_inicial: CatalogoTecnico, espiao: _Espiao
) -> None:
    folha = (
        *_poste(catalogo_inicial, "p1", "P1", "0.30", "0.30"),
        _estrutura("estrutura", "0.30", "0.32"),
        *_cabo(catalogo_inicial, "cabo", (("0.30", "0.30"), ("0.36", "0.30")), ("0.33", "0.31")),
        # há disco na folha, mas longe de qualquer P: sem candidato, `poste_ancorado_disco=false`
        _disco("disco-de-outro-lugar", 0.80, 0.60),
    )
    poste = _poste_de(_rodar(engine, catalogo_inicial, folha), "P1")

    assert _atributos(poste)["poste_ancorado_disco"] is False
    assert _centros(espiao, poste.id, texto=True) == {(0.30, 0.30)}
    assert _centros(espiao, poste.id, texto=False) == {(0.30, 0.30)}


def test_ambiguo_entrega_a_posicao_do_texto_aos_dois_regimes(
    engine: Engine, catalogo_inicial: CatalogoTecnico, espiao: _Espiao
) -> None:
    folha = (
        *_poste(catalogo_inicial, "p1", "P1", "0.30", "0.30"),
        *_poste(catalogo_inicial, "p2", "P2", "0.34", "0.30"),
        _disco("disco-disputado", 0.32, 0.30),
    )
    resultado = _rodar(engine, catalogo_inicial, folha)

    for identificador, posicao in (("P1", (0.30, 0.30)), ("P2", (0.34, 0.30))):
        poste = _poste_de(resultado, identificador)
        assert _atributos(poste)["associacao_pendente"] == "poste_disco"
        assert _centros(espiao, poste.id, texto=True) == {posicao}
        assert _centros(espiao, poste.id, texto=False) == {posicao}


def test_duas_leituras_no_mesmo_disco_entregam_um_so_poste_a_cada_regime(
    engine: Engine, catalogo_inicial: CatalogoTecnico, espiao: _Espiao
) -> None:
    codigos = [item.codigo for item in catalogo_inicial.itens_ativos(CategoriaElemento.POSTE)]
    folha = (
        _texto("leitura-a", f"POSTE {codigos[3]}", "0.30", "0.30", color=_VERDE),
        _texto("leitura-b", f"POSTE {codigos[1]}", "0.30", "0.306", color=_VERDE),
        _texto("rotulo", "P1", "0.30", "0.27"),
        _disco("disco-p1", 0.33, 0.30),
    )
    resultado = _rodar(engine, catalogo_inicial, folha)
    poste = _poste_de(resultado, "P1")
    atributos = _atributos(poste)

    assert atributos["poste_ancorado_disco"] is True
    assert "poste_codigo_alternativo" in atributos
    assert _posicao_do_texto(poste) in {(0.30, 0.30), (0.30, 0.306)}
    for regime in (True, False):
        for postes in espiao.por_regime(texto=regime):
            assert list(postes) == [poste.id]
    assert _centros(espiao, poste.id, texto=True) == {_posicao_do_texto(poste)}
    assert _centros(espiao, poste.id, texto=False) == {(0.33, 0.30)}


def test_mesmo_p_em_discos_diferentes_entrega_cada_proposta_no_seu_lugar(
    engine: Engine, catalogo_inicial: CatalogoTecnico, espiao: _Espiao
) -> None:
    # Dois rótulos P1 a 0,08 um do outro: a análise padrão os mantém na mesma ocorrência (só o
    # componente vencedor de cada identificador sobrevive; a 0,12 ou mais ficaria um só).
    folha = (
        *_poste(catalogo_inicial, "esquerda", "P1", "0.30", "0.30"),
        *_poste(catalogo_inicial, "direita", "P1", "0.38", "0.30"),
        _disco("disco-esquerda", 0.33, 0.30),
        _disco("disco-direita", 0.41, 0.30),
    )
    resultado = _rodar(engine, catalogo_inicial, folha)
    postes = _elementos(resultado, CategoriaElemento.POSTE)
    por_texto = {_posicao_do_texto(item): item for item in postes}

    assert len(postes) == 2
    for item in postes:
        assert _atributos(item)["associacao_pendente"] == "poste_mesmo_identificador"
        assert _atributos(item)["poste_ancorado_disco"] is True
    assert set(por_texto) == {(0.30, 0.30), (0.38, 0.30)}
    esquerda, direita = por_texto[(0.30, 0.30)].id, por_texto[(0.38, 0.30)].id
    assert _centros(espiao, esquerda, texto=True) == {(0.30, 0.30)}
    assert _centros(espiao, esquerda, texto=False) == {(0.33, 0.30)}
    assert _centros(espiao, direita, texto=True) == {(0.38, 0.30)}
    assert _centros(espiao, direita, texto=False) == {(0.41, 0.30)}
