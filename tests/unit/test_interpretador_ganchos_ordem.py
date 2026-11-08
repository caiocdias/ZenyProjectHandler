"""Ataque aos ganchos do interpretador (R-E07.2.1-1): ordem, cancelamento e equivalência."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from tests.interpretation_factories import text_evidence
from tests.unit.test_rule_based_interpreter import _request

from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.interpretation import ficha_poste as modulo_ficha_poste
from zeny_project_handler.adapters.interpretation import rule_based as modulo_base
from zeny_project_handler.adapters.interpretation.ficha_poste import InterpretadorFichaPoste
from zeny_project_handler.adapters.interpretation.operational_labels import (
    filtrar_propostas_identificadas,
)
from zeny_project_handler.adapters.interpretation.relation_rules import generate_relations
from zeny_project_handler.adapters.interpretation.span_rules import associar_tracados_de_cabos
from zeny_project_handler.domain.analysis import DiagnosticoAnalise, PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.ports.interpretation import (
    ConfiguracaoInterpretacao,
    InterpretacaoCanceladaError,
    SolicitacaoInterpretacao,
)

_MARCA = ("marca_gancho", "refinado")

_Refino = Callable[[tuple[PropostaElemento, ...]], tuple[PropostaElemento, ...]]


def _solicitacao(
    catalogo: CatalogoTecnico, configuracao: ConfiguracaoInterpretacao | None = None
) -> SolicitacaoInterpretacao:
    extracao_id = uuid4()
    pagina_id = uuid4()
    codigo = catalogo.itens_ativos(CategoriaElemento.POSTE)[0].codigo
    solicitacao = SolicitacaoInterpretacao(
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
    if configuracao is not None:
        solicitacao = replace(solicitacao, configuracao=configuracao)
    return solicitacao


def _marcar(propostas: tuple[PropostaElemento, ...]) -> tuple[PropostaElemento, ...]:
    return tuple(
        replace(item, atributos_sugeridos=(*item.atributos_sugeridos, _MARCA)) for item in propostas
    )


class _Espiao(InterpretadorRegrasExplicitas):
    """Base com os ganchos instrumentados; o comportamento vem de `refino`."""

    def __init__(self, registro: Any, eventos: list[str], refino: _Refino | None = None) -> None:
        super().__init__(registro)
        self.eventos = eventos
        self.refino = refino
        self.recebidas: list[tuple[PropostaElemento, ...]] = []
        self.solicitacoes: list[SolicitacaoInterpretacao] = []

    def _refinar_propostas_identificadas(
        self,
        propostas: tuple[PropostaElemento, ...],
        solicitacao: SolicitacaoInterpretacao,
        diagnosticos: list[DiagnosticoAnalise],
    ) -> tuple[PropostaElemento, ...]:
        self.eventos.append("gancho")
        self.recebidas.append(propostas)
        self.solicitacoes.append(solicitacao)
        return self.refino(propostas) if self.refino else propostas

    def _gerar_relacoes(self, execucao_id: Any, elementos: Any, solicitacao: Any) -> Any:
        self.eventos.append("relacoes")
        return super()._gerar_relacoes(execucao_id, elementos, solicitacao)


def _instrumentar(monkeypatch: pytest.MonkeyPatch, eventos: list[str]) -> dict[str, Any]:
    capturas: dict[str, Any] = {}
    filtrar = filtrar_propostas_identificadas
    associar = associar_tracados_de_cabos

    def filtrar_espiao(*args: Any, **kwargs: Any) -> Any:
        eventos.append("filtrar")
        capturas["filtrar_evidencias"] = args[1]
        resultado = filtrar(*args, **kwargs)
        capturas["filtrar_saida"] = resultado
        return resultado

    def associar_espiao(*args: Any, **kwargs: Any) -> Any:
        eventos.append("associar")
        capturas["associar_entrada"] = args[0]
        return associar(*args, **kwargs)

    monkeypatch.setattr(modulo_base, "filtrar_propostas_identificadas", filtrar_espiao)
    monkeypatch.setattr(modulo_base, "associar_tracados_de_cabos", associar_espiao)
    return capturas


def test_gancho_roda_entre_filtrar_e_associar_cabos(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    eventos: list[str] = []
    capturas = _instrumentar(monkeypatch, eventos)
    solicitacao = _solicitacao(catalogo_inicial)

    _Espiao(solicitacao.registro, eventos).interpretar(solicitacao)

    assert eventos == ["filtrar", "gancho", "associar", "relacoes"]
    assert capturas["filtrar_saida"]


def test_gancho_recebe_a_saida_do_filtro_e_as_evidencias_filtradas(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    eventos: list[str] = []
    capturas = _instrumentar(monkeypatch, eventos)
    solicitacao = _solicitacao(catalogo_inicial)
    espiao = _Espiao(solicitacao.registro, eventos)

    espiao.interpretar(solicitacao)

    assert espiao.recebidas == [capturas["filtrar_saida"]]
    assert espiao.solicitacoes[0].evidencias == capturas["filtrar_evidencias"]
    assert espiao.solicitacoes[0].execucao_id == solicitacao.execucao_id
    assert espiao.solicitacoes[0].catalogo is solicitacao.catalogo


def test_cabos_recebem_as_propostas_devolvidas_pelo_gancho(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    eventos: list[str] = []
    capturas = _instrumentar(monkeypatch, eventos)
    solicitacao = _solicitacao(catalogo_inicial)

    resultado = _Espiao(solicitacao.registro, eventos, _marcar).interpretar(solicitacao)

    entrada = capturas["associar_entrada"]
    assert entrada
    assert all(_MARCA in item.atributos_sugeridos for item in entrada)
    assert resultado.elementos
    assert all(_MARCA in item.atributos_sugeridos for item in resultado.elementos)


def test_gancho_que_remove_propostas_tira_os_elementos_do_resultado(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    solicitacao = _solicitacao(catalogo_inicial)

    resultado = _Espiao(solicitacao.registro, [], lambda _p: ()).interpretar(solicitacao)

    assert resultado.elementos == ()
    assert resultado.relacoes == ()


def test_limite_de_propostas_estoura_sobre_a_saida_inflada_do_gancho(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    livre = _solicitacao(catalogo_inicial)
    quantidade = len(InterpretadorRegrasExplicitas(livre.registro).interpretar(livre).elementos)
    assert quantidade >= 1
    limitada = _solicitacao(
        catalogo_inicial, ConfiguracaoInterpretacao(maximo_propostas=quantidade)
    )

    with pytest.raises(ValueError, match="excedeu o limite"):
        _Espiao(limitada.registro, [], lambda p: p + p).interpretar(limitada)


def test_limite_de_propostas_vale_sobre_a_saida_reduzida_do_gancho(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    livre = _solicitacao(catalogo_inicial)
    identificadas = len(InterpretadorRegrasExplicitas(livre.registro).interpretar(livre).elementos)
    assert identificadas >= 1
    apertada = _solicitacao(catalogo_inicial, ConfiguracaoInterpretacao(maximo_propostas=1))
    dobrada = _Espiao(apertada.registro, [], lambda p: p[:1] + p[:1])

    with pytest.raises(ValueError, match="excedeu o limite"):
        dobrada.interpretar(apertada)

    reduzida = _Espiao(apertada.registro, [], lambda p: p[:1]).interpretar(apertada)
    assert len(reduzida.elementos) == 1


def test_cancelamento_logo_depois_do_filtro_impede_gancho_cabos_e_relacoes(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    eventos: list[str] = []
    _instrumentar(monkeypatch, eventos)
    solicitacao = _solicitacao(catalogo_inicial)

    with pytest.raises(InterpretacaoCanceladaError):
        _Espiao(solicitacao.registro, eventos).interpretar(
            solicitacao, cancelado=lambda: "filtrar" in eventos
        )

    assert eventos == ["filtrar"]


def test_cancelamento_depois_das_relacoes_ainda_levanta_cancelada(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    eventos: list[str] = []
    _instrumentar(monkeypatch, eventos)
    solicitacao = _solicitacao(catalogo_inicial)

    with pytest.raises(InterpretacaoCanceladaError):
        _Espiao(solicitacao.registro, eventos).interpretar(
            solicitacao, cancelado=lambda: "relacoes" in eventos
        )

    assert eventos == ["filtrar", "gancho", "associar", "relacoes"]


def test_relacoes_do_base_sao_as_do_generate_relations_direto(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    chamadas: list[tuple[Any, ...]] = []
    original = generate_relations

    def espiao(*args: Any) -> Any:
        chamadas.append(args)
        return original(*args)

    monkeypatch.setattr(modulo_base, "generate_relations", espiao)
    solicitacao = _request(catalogo_inicial)
    interpretador = InterpretadorRegrasExplicitas(solicitacao.registro)

    resultado = interpretador.interpretar(solicitacao)

    assert resultado.relacoes
    assert len(chamadas) == 1
    execucao_id, elementos, registro, catalogo = chamadas[0]
    assert execucao_id == solicitacao.execucao_id
    assert registro is interpretador.registro
    assert catalogo is solicitacao.catalogo
    direto = generate_relations(execucao_id, elementos, registro, catalogo)
    assert resultado.relacoes == tuple(sorted(direto, key=lambda item: str(item.id)))
    assert resultado.elementos == tuple(sorted(elementos, key=lambda item: str(item.id)))


def test_gerar_relacoes_falso_nao_chama_o_gancho_de_relacoes_mas_chama_o_de_propostas(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    eventos: list[str] = []
    solicitacao = _solicitacao(catalogo_inicial, ConfiguracaoInterpretacao(gerar_relacoes=False))

    resultado = _Espiao(solicitacao.registro, eventos).interpretar(solicitacao)

    assert eventos == ["gancho"]
    assert resultado.relacoes == ()
    assert resultado.elementos


def test_gerar_relacoes_falso_mantem_padrao_e_ficha_identicos(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    solicitacao = _solicitacao(catalogo_inicial, ConfiguracaoInterpretacao(gerar_relacoes=False))
    registro = solicitacao.registro

    padrao = InterpretadorRegrasExplicitas(registro).interpretar(solicitacao)
    ficha = InterpretadorFichaPoste(registro).interpretar(solicitacao)

    assert padrao.relacoes == ()
    assert ficha == padrao


def test_gancho_do_padrao_devolve_o_mesmo_objeto_e_nao_mexe_nos_diagnosticos(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    solicitacao = _solicitacao(catalogo_inicial)
    interpretador = InterpretadorRegrasExplicitas(solicitacao.registro)
    propostas = interpretador.interpretar(solicitacao).elementos
    diagnosticos: list[DiagnosticoAnalise] = []

    refinadas = interpretador._refinar_propostas_identificadas(propostas, solicitacao, diagnosticos)

    assert refinadas is propostas
    assert diagnosticos == []


def test_diagnostico_acrescentado_pelo_gancho_chega_ao_resultado_depois_dos_dos_analisadores(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    solicitacao = _solicitacao(catalogo_inicial)
    extra = DiagnosticoAnalise(codigo="x.gancho", mensagem="do gancho", extrator="gancho")

    class _Gancho(InterpretadorRegrasExplicitas):
        def _refinar_propostas_identificadas(
            self,
            propostas: tuple[PropostaElemento, ...],
            solicitacao: SolicitacaoInterpretacao,
            diagnosticos: list[DiagnosticoAnalise],
        ) -> tuple[PropostaElemento, ...]:
            diagnosticos.append(extra)
            return propostas

    class _AnalisadorQuebrado:
        nome = "quebrado"
        categoria = CategoriaElemento.POSTE

        def analisar(self, *_args: object) -> Any:
            raise RuntimeError("falha do analisador")

    interpretador = _Gancho(solicitacao.registro, (_AnalisadorQuebrado(),))  # type: ignore[arg-type]

    resultado = interpretador.interpretar(solicitacao)

    assert [item.codigo for item in resultado.diagnosticos] == [
        "interpretacao.analisador_falhou",
        "x.gancho",
    ]


def _com_ancoragem_falha(monkeypatch: pytest.MonkeyPatch, erro: Exception) -> list[tuple[Any, ...]]:
    chamadas: list[tuple[Any, ...]] = []

    def falha(*args: Any) -> Any:
        chamadas.append(args)
        raise erro

    monkeypatch.setattr(modulo_ficha_poste, "ancorar_postes_no_desenho", falha)
    return chamadas


def test_ancoragem_que_falha_entrega_aos_cabos_as_propostas_originais(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    eventos: list[str] = []
    capturas = _instrumentar(monkeypatch, eventos)
    chamadas = _com_ancoragem_falha(monkeypatch, RuntimeError("quebrou"))
    solicitacao = _solicitacao(catalogo_inicial)

    resultado = InterpretadorFichaPoste(solicitacao.registro).interpretar(solicitacao)

    assert eventos == ["filtrar", "associar"]
    assert capturas["associar_entrada"] == capturas["filtrar_saida"]
    assert chamadas[0][0] == capturas["filtrar_saida"]
    assert chamadas[0][1] == capturas["filtrar_evidencias"]
    assert [item.extrator for item in resultado.diagnosticos] == ["ancoragem-poste"]


def test_diagnostico_da_ancoragem_chega_ao_resultado_com_gerar_relacoes_falso(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    _com_ancoragem_falha(monkeypatch, RuntimeError("quebrou"))
    solicitacao = _solicitacao(catalogo_inicial, ConfiguracaoInterpretacao(gerar_relacoes=False))

    resultado = InterpretadorFichaPoste(solicitacao.registro).interpretar(solicitacao)

    assert resultado.relacoes == ()
    assert [item.codigo for item in resultado.diagnosticos] == [
        "interpretacao.ancoragem_poste_falhou"
    ]


def test_excecao_sem_mensagem_usa_o_nome_da_classe_no_diagnostico(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    _com_ancoragem_falha(monkeypatch, KeyError())
    solicitacao = _solicitacao(catalogo_inicial)

    resultado = InterpretadorFichaPoste(solicitacao.registro).interpretar(solicitacao)

    assert [item.mensagem for item in resultado.diagnosticos] == ["KeyError"]


def test_diagnostico_da_ancoragem_nao_vaza_entre_chamadas(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    _com_ancoragem_falha(monkeypatch, RuntimeError("quebrou"))
    solicitacao = _solicitacao(catalogo_inicial)
    interpretador = InterpretadorFichaPoste(solicitacao.registro)

    primeira = interpretador.interpretar(solicitacao)
    segunda = interpretador.interpretar(solicitacao)

    assert len(primeira.diagnosticos) == 1
    assert segunda == primeira


def test_ancoragem_que_muda_proposta_chega_aos_cabos_sem_mudar_o_padrao(
    catalogo_inicial: CatalogoTecnico, monkeypatch: pytest.MonkeyPatch
) -> None:
    eventos: list[str] = []
    capturas = _instrumentar(monkeypatch, eventos)
    solicitacao = _solicitacao(catalogo_inicial)
    registro = solicitacao.registro
    monkeypatch.setattr(
        modulo_ficha_poste, "ancorar_postes_no_desenho", lambda propostas, _ev: _marcar(propostas)
    )

    padrao_antes = InterpretadorRegrasExplicitas(registro).interpretar(solicitacao)
    entrada_padrao = capturas["associar_entrada"]
    ficha = InterpretadorFichaPoste(registro).interpretar(solicitacao)
    entrada_ficha = capturas["associar_entrada"]
    padrao_depois = InterpretadorRegrasExplicitas(registro).interpretar(solicitacao)

    assert entrada_padrao
    assert all(_MARCA not in item.atributos_sugeridos for item in entrada_padrao)
    assert all(_MARCA in item.atributos_sugeridos for item in entrada_ficha)
    assert ficha.elementos
    assert all(_MARCA in item.atributos_sugeridos for item in ficha.elementos)
    assert padrao_antes == padrao_depois
    assert all(_MARCA not in item.atributos_sugeridos for item in padrao_depois.elementos)


def test_subclasse_nao_sobrescreve_o_gerar_relacoes_do_base_nesta_etapa(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    solicitacao = _request(catalogo_inicial)
    registro = solicitacao.registro

    padrao = InterpretadorRegrasExplicitas(registro).interpretar(solicitacao)
    ficha = InterpretadorFichaPoste(registro).interpretar(solicitacao)

    assert padrao.relacoes
    assert ficha == padrao
