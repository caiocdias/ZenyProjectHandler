from __future__ import annotations

from uuid import uuid4

import pytest
from tests.interpretation_factories import text_evidence

from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.interpretation import ficha_poste as modulo_ficha_poste
from zeny_project_handler.adapters.interpretation.ancoragem_poste import (
    ancorar_postes_no_desenho,
)
from zeny_project_handler.adapters.interpretation.ficha_poste import InterpretadorFichaPoste
from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao


def _solicitacao(catalogo: CatalogoTecnico) -> SolicitacaoInterpretacao:
    extracao_id = uuid4()
    pagina_id = uuid4()
    codigo = catalogo.itens_ativos(CategoriaElemento.POSTE)[0].codigo
    return SolicitacaoInterpretacao(
        projeto_id=uuid4(),
        execucao_id=uuid4(),
        execucao_extracao_id=extracao_id,
        catalogo=catalogo,
        evidencias=(
            text_evidence(
                execution_id=extracao_id,
                page_id=pagina_id,
                key="poste",
                text=f"POSTE {codigo}",
                x="0.10",
                y="0.10",
                color="#008000",
            ),
            text_evidence(
                execution_id=extracao_id,
                page_id=pagina_id,
                key="rotulo",
                text="P1",
                x="0.10",
                y="0.08",
            ),
        ),
        registro=carregar_registro_regras_inicial(),
    )


def test_versoes_do_padrao_e_da_subclasse() -> None:
    assert InterpretadorRegrasExplicitas.versao == "25.0"
    assert InterpretadorFichaPoste.versao == "27.0"
    assert InterpretadorFichaPoste.nome == InterpretadorRegrasExplicitas.nome


def test_ancoragem_sem_propostas_devolve_vazio() -> None:
    assert ancorar_postes_no_desenho((), ()) == ()


def test_subclasse_com_ancoragem_identidade_nao_muda_a_saida(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    def identidade(
        propostas: tuple[PropostaElemento, ...],
        evidencias: tuple[EvidenciaDocumento, ...],
    ) -> tuple[PropostaElemento, ...]:
        del evidencias
        return propostas

    monkeypatch.setattr(modulo_ficha_poste, "ancorar_postes_no_desenho", identidade)
    solicitacao = _solicitacao(catalogo_inicial)
    registro = solicitacao.registro

    padrao = InterpretadorRegrasExplicitas(registro).interpretar(solicitacao)
    ficha = InterpretadorFichaPoste(registro).interpretar(solicitacao)

    assert padrao.elementos
    assert ficha == padrao


def test_excecao_da_ancoragem_vira_diagnostico_sem_derrubar_a_interpretacao(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falha(*_args: object) -> None:
        raise RuntimeError("ancoragem quebrou")

    monkeypatch.setattr(modulo_ficha_poste, "ancorar_postes_no_desenho", falha)
    solicitacao = _solicitacao(catalogo_inicial)
    registro = solicitacao.registro

    padrao = InterpretadorRegrasExplicitas(registro).interpretar(solicitacao)
    ficha = InterpretadorFichaPoste(registro).interpretar(solicitacao)

    assert ficha.elementos == padrao.elementos
    assert ficha.relacoes == padrao.relacoes
    assert [(item.codigo, item.mensagem) for item in ficha.diagnosticos] == [
        ("interpretacao.ancoragem_poste_falhou", "ancoragem quebrou")
    ]
