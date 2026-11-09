"""Ataque aos vínculos do poste pendente no regime de texto (E07.2.2.1, Task 1)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from tests.factories import complete_project
from tests.unit.test_ancoragem_poste import (
    EXECUCAO,
    PAGINA,
    _atributos,
    _disco,
    _poste,
    _solicitacao_relacoes,
)

from zeny_project_handler.adapters.interpretation.ancoragem_poste import (
    ancorar_postes_no_desenho,
)
from zeny_project_handler.adapters.interpretation.ficha_poste import InterpretadorFichaPoste
from zeny_project_handler.adapters.interpretation.rule_based import InterpretadorRegrasExplicitas
from zeny_project_handler.application.automatic_promotion import promover_resultado_automatico
from zeny_project_handler.domain.analysis import PropostaElemento, PropostaRelacao
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao


def _disputa() -> tuple[PropostaElemento, PropostaElemento]:
    """Dois postes disputam um só disco; a saída real da ancoragem os deixa pendentes."""
    originais = (_poste("a", "P1", 0.30, 0.30), _poste("b", "P2", 0.34, 0.30))
    p1, p2 = ancorar_postes_no_desenho(originais, (_disco("d1", 0.32, 0.30),))
    assert _atributos(p1)["associacao_pendente"] == "poste_disco"
    assert _atributos(p2)["associacao_pendente"] == "poste_disco"
    return p1, p2


def _origem(
    chave: str,
    identificador: str | None,
    x: float,
    y: float = 0.30,
    categoria: CategoriaElemento = CategoriaElemento.ESTRUTURA_MT,
    pagina: UUID = PAGINA,
) -> PropostaElemento:
    atributos = (("identificador_operacional", identificador),) if identificador else ()
    return replace(
        _poste(chave, "x", x, y, codigo="N1", pagina=pagina),
        categoria=categoria,
        atributos_sugeridos=atributos,
    )


def _ancorado(identificador: str, centro_texto: str) -> PropostaElemento:
    return _poste(
        "z",
        identificador,
        0.60,
        0.30,
        extras=(("poste_ancorado_disco", True), ("poste_texto_centro", centro_texto)),
    )


def _relacoes(
    catalogo: CatalogoTecnico,
    elementos: tuple[PropostaElemento, ...],
    interpretador: type[InterpretadorRegrasExplicitas] = InterpretadorFichaPoste,
) -> tuple[PropostaRelacao, ...]:
    solicitacao = _solicitacao_relacoes(catalogo)
    return interpretador(solicitacao.registro)._gerar_relacoes(EXECUCAO, elementos, solicitacao)


def _ligacoes(relacoes: tuple[PropostaRelacao, ...]) -> set[tuple[str, UUID, UUID]]:
    return {(r.tipo_relacao, r.origem_referencia_id, r.destino_referencia_id) for r in relacoes}


def test_estrutura_bt_tambem_liga_ao_poste_pendente(catalogo_inicial: CatalogoTecnico) -> None:
    p1, p2 = _disputa()
    origem = _origem("e", "P1", 0.36, categoria=CategoriaElemento.ESTRUTURA_BT)

    relacoes = _relacoes(catalogo_inicial, (p1, p2, origem))

    assert _ligacoes(relacoes) == {("INSTALADA_EM", origem.id, p1.id)}


@pytest.mark.parametrize(
    "valor",
    ["poste_mesmo_identificador", "tracado", "contextos_locais_em_empate", "Poste_Disco"],
)
def test_outros_valores_de_pendencia_nao_ganham_relacao(
    catalogo_inicial: CatalogoTecnico, valor: str
) -> None:
    pendente = _poste("a", "P1", 0.30, 0.30, extras=(("associacao_pendente", valor),))

    assert _relacoes(catalogo_inicial, (pendente, _origem("e", "P1", 0.36))) == ()


def test_pendencia_de_outro_valor_com_centro_de_texto_tambem_segue_cortada(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    pendente = _poste(
        "a",
        "P1",
        0.50,
        0.30,
        extras=(
            ("associacao_pendente", "tracado"),
            ("poste_ancorado_disco", True),
            ("poste_texto_centro", "0.3,0.3"),
        ),
    )

    assert _relacoes(catalogo_inicial, (pendente, _origem("e", "P1", 0.36))) == ()


def test_origem_pendente_continua_sem_relacao(catalogo_inicial: CatalogoTecnico) -> None:
    p1, p2 = _disputa()
    origem = replace(
        _origem("e", "P1", 0.36),
        atributos_sugeridos=(
            ("identificador_operacional", "P1"),
            ("associacao_pendente", "poste_disco"),
        ),
    )

    assert _relacoes(catalogo_inicial, (p1, p2, origem)) == ()


def test_entradas_nao_sao_mutadas_e_o_destino_e_o_poste_original(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    p1, p2 = _disputa()
    elementos = (p1, p2, _origem("e", "P1", 0.36))
    antes = tuple(elementos)

    relacoes = _relacoes(catalogo_inicial, elementos)

    assert len(relacoes) == 1
    assert elementos == antes
    assert all(a is b for a, b in zip(elementos, antes, strict=True))
    assert relacoes[0].destino_referencia_id == p1.id
    assert _atributos(p1)["associacao_pendente"] == "poste_disco"
    assert _atributos(p2)["associacao_pendente"] == "poste_disco"


def test_duas_estruturas_do_mesmo_poste_pendente_ligam_cada_uma(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    p1, p2 = _disputa()
    e1 = _origem("e1", "P1", 0.36, 0.30)
    e2 = _origem("e2", "P1", 0.28, 0.32)

    relacoes = _relacoes(catalogo_inicial, (p1, p2, e1, e2))

    assert _ligacoes(relacoes) == {
        ("INSTALADA_EM", e1.id, p1.id),
        ("INSTALADA_EM", e2.id, p1.id),
    }


def test_estrutura_do_p2_colada_no_p1_liga_ao_p2_e_nunca_ao_mais_proximo(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    p1, p2 = _disputa()
    origem = _origem("e", "P2", 0.305)

    assert _ligacoes(_relacoes(catalogo_inicial, (p1, p2, origem))) == {
        ("INSTALADA_EM", origem.id, p2.id)
    }


def test_estrutura_de_identificador_sem_poste_correspondente_fica_sem_relacao(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    p1, p2 = _disputa()

    assert _relacoes(catalogo_inicial, (p1, p2, _origem("e", "P7", 0.305))) == ()


def test_estrutura_sem_identificador_mais_perto_do_ancorado_que_do_pendente_liga_ao_ancorado(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    p1, p2 = _disputa()
    ancorado = _ancorado("P3", "0.37,0.3")
    origem = _origem("e", None, 0.36)

    # ancorado no texto a 0,01; o pendente P2 (0,34) a 0,02: o pendente não rouba o vínculo
    assert _ligacoes(_relacoes(catalogo_inicial, (p1, p2, ancorado, origem))) == {
        ("INSTALADA_EM", origem.id, ancorado.id)
    }


def test_estrutura_com_identificador_do_pendente_ignora_ancorado_vizinho_de_outro_nome(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    p1, p2 = _disputa()
    ancorado = _ancorado("P3", "0.361,0.3")
    origem = _origem("e", "P1", 0.36)

    assert _ligacoes(_relacoes(catalogo_inicial, (p1, p2, ancorado, origem))) == {
        ("INSTALADA_EM", origem.id, p1.id)
    }


def test_estrutura_sem_identificador_empatada_entre_pendente_e_ancorado_fica_sem_relacao(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    # Efeito colateral da R-E07.2.2.1-4: o pendente agora compete e o empate (margem de 0,004)
    # corta o vínculo, em vez de dá-lo ao ancorado como na 26.0. Sem relação errada.
    p1, p2 = _disputa()
    ancorado = _ancorado("P3", "0.3,0.3")
    origem = _origem("e", None, 0.32)

    assert _relacoes(catalogo_inicial, (p1, p2, ancorado, origem)) == ()


def _pilha(
    y2: float, estrutura: tuple[float, float] = (0.36, 0.30)
) -> tuple[tuple[PropostaElemento, ...], PropostaElemento]:
    originais = (
        _poste("a1", "P1", 0.30, 0.29),
        _poste("a2", "P1", 0.30, y2, codigo="12-300"),
        _poste("b", "P2", 0.34, 0.30),
    )
    resultado = ancorar_postes_no_desenho(originais, (_disco("d1", 0.32, 0.30),))
    pilha = [item for item in resultado if _atributos(item)["identificador_operacional"] == "P1"]
    assert len(pilha) == 2
    assert all(_atributos(item).get("associacao_pendente") == "poste_disco" for item in pilha)
    return resultado, _origem("e", "P1", *estrutura)


def test_pilha_com_diferenca_dentro_da_margem_fica_sem_relacao(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    # (0.30, 0.29) e (0.30, 0.31) equidistam da estrutura em (0.36, 0.30)
    resultado, origem = _pilha(0.31)

    assert _relacoes(catalogo_inicial, (*resultado, origem)) == ()


def test_pilha_com_diferenca_acima_da_margem_liga_so_ao_mais_proximo(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    # (0.30, 0.29) e (0.30, 0.30) com a estrutura em (0.30, 0.36): 0,07 contra 0,06
    resultado, origem = _pilha(0.30, (0.30, 0.36))
    mais_perto = next(
        item
        for item in resultado
        if _atributos(item)["identificador_operacional"] == "P1"
        and item.geometria.pontos[0].y > 0.295
    )

    relacoes = _relacoes(catalogo_inicial, (*resultado, origem))

    assert len(relacoes) == 1
    assert relacoes[0].destino_referencia_id == mais_perto.id


def test_ligado_x_desligado_o_25_0_nao_muda_e_o_27_0_so_acrescenta_o_pendente(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    p1, p2 = _disputa()
    origem = _origem("e", "P1", 0.36)
    elementos = (p1, p2, origem)

    assert _relacoes(catalogo_inicial, elementos, InterpretadorRegrasExplicitas) == ()
    assert _ligacoes(_relacoes(catalogo_inicial, elementos)) == {("INSTALADA_EM", origem.id, p1.id)}


def test_25_0_com_poste_ancorado_nao_usa_o_centro_do_texto(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    ancorado = _poste(
        "a",
        "P1",
        0.80,
        0.60,
        extras=(("poste_ancorado_disco", True), ("poste_texto_centro", "0.3,0.3")),
    )
    origem = _origem("e", "P1", 0.36)

    assert _relacoes(catalogo_inicial, (ancorado, origem), InterpretadorRegrasExplicitas) == ()
    assert len(_relacoes(catalogo_inicial, (ancorado, origem))) == 1


def _tipada(
    catalogo: CatalogoTecnico, proposta: PropostaElemento, categoria: CategoriaElemento
) -> PropostaElemento:
    item = catalogo.itens_ativos(categoria)[0]
    return replace(proposta, tipo_catalogo_sugerido_id=item.id, codigo_observado=item.codigo)


def test_promocao_automatica_nao_promove_a_relacao_nem_a_estrutura_pelo_pendente(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    p1, p2 = _disputa()
    elementos = (
        _tipada(catalogo_inicial, p1, CategoriaElemento.POSTE),
        _tipada(catalogo_inicial, p2, CategoriaElemento.POSTE),
        _tipada(catalogo_inicial, _origem("e", "P1", 0.36), CategoriaElemento.ESTRUTURA_MT),
    )
    relacoes = _relacoes(catalogo_inicial, elementos)
    assert len(relacoes) == 1
    projeto = complete_project(catalogo_inicial)

    resultado = promover_resultado_automatico(
        projeto,
        catalogo_inicial,
        elementos,
        relacoes,
        promovido_em=datetime(2026, 11, 8, tzinfo=UTC),
    )

    assert resultado.projeto.relacoes_confirmadas == projeto.relacoes_confirmadas
    assert resultado.projeto.elementos == projeto.elementos
    assert resultado.decisoes == ()
    assert all(item.estado_revisao is not EstadoRevisao.CONFIRMADA for item in resultado.elementos)
    assert all(item.estado_revisao is not EstadoRevisao.CONFIRMADA for item in resultado.relacoes)


def test_promocao_automatica_controle_promove_quando_o_poste_nao_esta_pendente(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    # Controle: a mesma montagem com o poste ancorado promove; sem isto o teste acima não
    # distinguiria "pendente barra" de "montagem que nunca promoveria".
    projeto = complete_project(catalogo_inicial)
    pagina = projeto.documentos[0].paginas[0].id
    livre = _poste("a", "P1", 0.30, 0.30, pagina=pagina)
    origem = _origem("e", "P1", 0.36, pagina=pagina)
    elementos = (
        _tipada(catalogo_inicial, livre, CategoriaElemento.POSTE),
        _tipada(catalogo_inicial, origem, CategoriaElemento.ESTRUTURA_MT),
    )
    relacoes = _relacoes(catalogo_inicial, elementos)
    assert len(relacoes) == 1

    resultado = promover_resultado_automatico(
        projeto,
        catalogo_inicial,
        elementos,
        relacoes,
        promovido_em=datetime(2026, 11, 8, tzinfo=UTC),
    )

    assert len(resultado.projeto.relacoes_confirmadas) == len(projeto.relacoes_confirmadas) + 1
