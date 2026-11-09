"""Cadeia dos símbolos no poste certo (E07.2.2.1, Task 5), com a opção de símbolos ligada.

Cada caso monta uma folha sintética pequena, reconcilia observações de símbolo sintéticas
(`reconcile_symbols`), roda o pipeline persistido com `InterpretadorFichaPoste` e `simbolos=...`
e confere o que a etapa promete de ponta a ponta: o símbolo entra no poste certo ou fica pendente,
nunca no vizinho; o poste pendente por disputa de disco mantém as ligações do regime de texto; o
estai sai em uma ocorrência; a ablação do legado não perde a ocorrência; a promoção e as regiões
seguem funcionando sobre as propostas novas. A cena está em `symbol_grammars/dois_postes.py`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine
from tests.fixtures.symbol_grammars import dois_postes as cena
from tests.integration.test_ficha_poste_cadeia import (
    _atributos,
    _disco,
    _elementos,
    _estrutura,
    _poste,
    _regioes,
    _texto,
)
from tests.integration.test_golden_padrao_e07 import (
    _DOCUMENTO_ID,
    _EXTRACAO_ID,
    _VERDE,
    _projeto,
)
from tests.unit.test_symbol_reconciliation import _policy, _result

from zeny_project_handler.adapters.interpretation import carregar_registro_regras_inicial
from zeny_project_handler.adapters.interpretation.ficha_poste import InterpretadorFichaPoste
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.analysis_regions import RegiaoAnalise
from zeny_project_handler.application.interpretation_pipeline import (
    ExecutarPipelineInterpretacao,
    ResultadoExecucaoInterpretacao,
)
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    SymbolReconciliation,
    reconcile_symbols,
)
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, TipoEquipamento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    SituacaoProjeto,
)
from zeny_project_handler.domain.symbols import ObservacaoSimbolo, PerfilMetodoSimbolos

pytestmark = pytest.mark.integration

_FOLHA = cena.FolhaDeSimbolos(documento_id=str(_DOCUMENTO_ID), documento_sha256="e" * 64)
_INTERRUPCAO = "EQUIPAMENTO_INTERRUPCAO"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    motor = create_sqlite_engine(tmp_path / "cadeia-simbolos.sqlite3")
    upgrade_database(motor)
    try:
        yield motor
    finally:
        motor.dispose()


def _reconciliar(
    *entradas: tuple[PerfilMetodoSimbolos, tuple[ObservacaoSimbolo, ...]],
    politica: CalibrationPolicy | None = None,
) -> SymbolReconciliation:
    return reconcile_symbols(
        tuple(_result(perfil, *observacoes) for perfil, observacoes in entradas),
        politica or CalibrationPolicy(),
    )


def _executar(
    engine: Engine,
    catalogo: CatalogoTecnico,
    evidencias: tuple[EvidenciaDocumento, ...],
    simbolos: SymbolReconciliation | None,
) -> ResultadoExecucaoInterpretacao:
    projeto = _projeto(catalogo)
    extracao = ExecucaoAnalise(
        id=_EXTRACAO_ID,
        projeto_id=projeto.id,
        metodo="fixture-extraction",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 7, 21, 12, tzinfo=UTC),
        finalizada_em=datetime(2026, 7, 21, 12, 1, tzinfo=UTC),
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        if work.projetos.obter(projeto.id) is None:
            work.catalogos.salvar(catalogo)
            work.projetos.salvar(projeto)
            work.execucoes_analise.salvar(extracao)
            for item in evidencias:
                work.evidencias.salvar(item)
            work.commit()
    registro = carregar_registro_regras_inicial()
    return ExecutarPipelineInterpretacao(
        InterpretadorFichaPoste(registro),
        registro,
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 7, 21, 13, tzinfo=UTC),
    ).executar(projeto.id, extracao.id, simbolos=simbolos)


def _dois_postes(catalogo: CatalogoTecnico) -> tuple[EvidenciaDocumento, ...]:
    return (
        *_poste(catalogo, "p1", "P1", *cena.POSTE_ESQUERDO),
        *_poste(catalogo, "p2", "P2", *cena.POSTE_DIREITO),
    )


def _postes_por_nome(resultado: ResultadoExecucaoInterpretacao) -> dict[str, UUID]:
    return {
        str(_atributos(item)["identificador_operacional"]): item.id
        for item in _elementos(resultado, CategoriaElemento.POSTE)
    }


def _centro_x(elemento: PropostaElemento) -> float:
    pontos = elemento.geometria.pontos
    return float(sum(p.x for p in pontos) / len(pontos))


def _simbolos(
    resultado: ResultadoExecucaoInterpretacao, classe: str | None = None
) -> list[PropostaElemento]:
    """Propostas de símbolo, da esquerda para a direita."""
    achados = [
        item
        for item in resultado.elementos
        if "origem_simbolo_ocorrencia_id" in _atributos(item)
        and (classe is None or _atributos(item)["simbolo_classe"] == classe)
    ]
    return sorted(achados, key=_centro_x)


def _suportes(resultado: ResultadoExecucaoInterpretacao, simbolo: PropostaElemento) -> list[UUID]:
    return [
        item.destino_referencia_id
        for item in resultado.relacoes
        if item.origem_referencia_id == simbolo.id and item.tipo_relacao == "INSTALADO_EM"
    ]


def _candidatos(simbolo: PropostaElemento) -> set[str]:
    bruto = _atributos(simbolo)["simbolo_suportes_candidatos"]
    return {str(item["proposta_id"]) for item in json.loads(str(bruto))}


def _regiao_do(regioes: tuple[RegiaoAnalise, ...], elemento: PropostaElemento) -> RegiaoAnalise:
    (achada,) = (item for item in regioes if elemento.id in item.elemento_ids)
    return achada


def _tres_observacoes(
    classe: str,
    *,
    situacao: SituacaoProjeto | None = None,
    atributos: tuple[tuple[str, object], ...] = (),
) -> tuple[ObservacaoSimbolo, ...]:
    return tuple(
        cena.observacao(
            cena.PERFIL_MODELO,
            classe,
            canto,
            _FOLHA,
            situacao=situacao,
            atributos=atributos,  # type: ignore[arg-type]
        )
        for canto in (cena.CAIXA_PERTO_ESQUERDO, cena.CAIXA_NO_MEIO, cena.CAIXA_PERTO_DIREITO)
    )


# --- critério 1 e EQUIPAMENTO_INTERRUPCAO ------------------------------------------------------


def test_interrupcao_entre_dois_postes_vai_ao_poste_certo_ou_fica_pendente(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    simbolos = _reconciliar((cena.PERFIL_MODELO, _tres_observacoes(_INTERRUPCAO)))

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    postes = _postes_por_nome(resultado)
    esquerdo, meio, direito = _simbolos(resultado, _INTERRUPCAO)
    # entre os dois, a diferença é zero e não passa a margem: pendente, sem suporte nem relação
    atributos = _atributos(meio)
    assert atributos["suporte_proposta_id"] is None
    assert atributos["associacao_pendente"] is True
    assert _candidatos(meio) == {str(postes["P1"]), str(postes["P2"])}
    # os outros dois apontam só o poste certo, nos atributos e na relação; nenhum vai ao vizinho
    assert _atributos(esquerdo)["suporte_proposta_id"] == str(postes["P1"])
    assert _atributos(direito)["suporte_proposta_id"] == str(postes["P2"])
    assert {s.id: _suportes(resultado, s) for s in (esquerdo, meio, direito)} == {
        esquerdo.id: [postes["P1"]],
        meio.id: [],
        direito.id: [postes["P2"]],
    }


def test_interrupcao_e_simbolo_de_equipamento_sem_catalogo_e_nao_vira_ativo(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    # O catálogo inicial ainda não tem a classe EQUIPAMENTO_INTERRUPCAO: o símbolo entra no poste
    # certo como observação revisável, com o catálogo não localizado, e não é promovido.
    simbolos = _reconciliar((cena.PERFIL_MODELO, _tres_observacoes(_INTERRUPCAO)))

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    esquerdo, _, direito = _simbolos(resultado, _INTERRUPCAO)
    for simbolo in (esquerdo, direito):
        atributos = _atributos(simbolo)
        assert simbolo.categoria is CategoriaElemento.EQUIPAMENTO
        assert atributos["simbolo_papel"] == "equipamento"
        assert atributos["simbolo_associacao_resolvida"] is True
        assert atributos["catalogo_nao_localizado"] is True
        assert simbolo.estado_revisao is not EstadoRevisao.CONFIRMADA


# --- promoção e regiões ------------------------------------------------------------------------


def _transformador_do_catalogo(catalogo: CatalogoTecnico) -> TipoEquipamento:
    opcao = next(
        item.id
        for grupo in catalogo.grupos_opcao
        if grupo.chave == "classe_equipamento"
        for item in grupo.opcoes
        if item.codigo == "TRANSFORMADOR"
    )
    return next(
        item
        for item in catalogo.itens_ativos(CategoriaElemento.EQUIPAMENTO)
        if isinstance(item, TipoEquipamento) and item.classe_equipamento_opcao_id == opcao
    )


def test_promocao_e_regioes_seguem_as_propostas_do_poste_certo_com_a_opcao_ligada(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    equipamento = _transformador_do_catalogo(catalogo_inicial)
    observacoes = _tres_observacoes(
        "TRANSFORMADOR",
        situacao=SituacaoProjeto.INSTALAR,
        atributos=(
            ("tipo_catalogo_id", str(equipamento.id)),
            ("situacao_validada", True),
            ("quantidade_ativos", 1),
        ),
    )
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, observacoes),
        politica=_policy((cena.PERFIL_MODELO, "TRANSFORMADOR", "0.995", 90)),
    )
    folha = _dois_postes(catalogo_inicial)

    resultado = _executar(engine, catalogo_inicial, folha, simbolos)

    postes = _postes_por_nome(resultado)
    esquerdo, meio, direito = _simbolos(resultado, "TRANSFORMADOR")
    # promoção: os dois de suporte único passam; o do meio fica fora, pendente
    assert esquerdo.estado_revisao is EstadoRevisao.CONFIRMADA
    assert direito.estado_revisao is EstadoRevisao.CONFIRMADA
    assert meio.estado_revisao is not EstadoRevisao.CONFIRMADA
    assert _atributos(meio)["associacao_pendente"] is True
    assert _suportes(resultado, esquerdo) == [postes["P1"]]
    assert _suportes(resultado, direito) == [postes["P2"]]
    assert _suportes(resultado, meio) == []
    # regiões: cada poste reúne o seu símbolo; o do meio não entra em nenhum dos dois
    regioes = _regioes(resultado, folha, catalogo_inicial)
    regiao_p1 = _regiao_do(regioes, esquerdo)
    regiao_p2 = _regiao_do(regioes, direito)
    assert (regiao_p1.rotulo_ponto, regiao_p2.rotulo_ponto) == ("P1", "P2")
    assert postes["P1"] in regiao_p1.elemento_ids
    assert postes["P2"] in regiao_p2.elemento_ids
    assert meio.id not in {*regiao_p1.elemento_ids, *regiao_p2.elemento_ids}
    assert meio.id in _regiao_do(regioes, meio).elemento_ids


# --- poste pendente por disputa: símbolo, vínculos e regiões -----------------------------------


def _folha_disputada(catalogo: CatalogoTecnico) -> tuple[EvidenciaDocumento, ...]:
    """P1 e P2 disputam um disco entre eles; P3 tem disco próprio e a estrutura U1 fica no P1."""
    return (
        *_dois_postes(catalogo),
        _texto(
            "p3-poste",
            f"POSTE {catalogo.itens_ativos(CategoriaElemento.POSTE)[3].codigo}",
            *cena.POSTE_TERCEIRO,
            color=_VERDE,
        ),
        _texto("p3-rotulo", "P3", *cena.ROTULO_TERCEIRO),
        _estrutura("estrutura", "0.30", "0.32"),
        _disco("disco-disputado", *cena.DISCO_DISPUTADO),
        _disco("disco-p3", *cena.DISCO_TERCEIRO),
    )


def _simbolo_no_disco_disputado() -> SymbolReconciliation:
    observacao = cena.observacao(
        cena.PERFIL_MODELO, _INTERRUPCAO, cena.CAIXA_NO_DISCO, _FOLHA, lado=cena.LADO_NO_DISCO
    )
    return _reconciliar((cena.PERFIL_MODELO, (observacao,)))


def test_simbolo_no_disco_disputado_fica_pendente_e_nao_migra_para_o_terceiro_poste(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    resultado = _executar(
        engine, catalogo_inicial, _folha_disputada(catalogo_inicial), _simbolo_no_disco_disputado()
    )

    postes = _postes_por_nome(resultado)
    (simbolo,) = _simbolos(resultado)
    atributos = _atributos(simbolo)
    # o P3 alcança o símbolo (a 0,016 do disco dele) e é candidato, mas nunca o suporte
    assert set(postes) == {"P1", "P2", "P3"}
    assert _candidatos(simbolo) == {str(item) for item in postes.values()}
    assert atributos["suporte_proposta_id"] is None
    assert atributos["associacao_pendente"] is True
    assert _suportes(resultado, simbolo) == []
    # P1 e P2 ficam com a pendência `poste_disco` e o sítio em disputa
    for nome in ("P1", "P2"):
        poste = next(item for item in resultado.elementos if item.id == postes[nome])
        assert _atributos(poste)["associacao_pendente"] == "poste_disco"
        assert _atributos(poste)["poste_disco_sitios"] == "0.32,0.3"


def test_poste_pendente_mantem_a_estrutura_ligada_e_as_regioes_ficam_separadas(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    folha = _folha_disputada(catalogo_inicial)

    resultado = _executar(engine, catalogo_inicial, folha, _simbolo_no_disco_disputado())

    postes = _postes_por_nome(resultado)
    (estrutura,) = _elementos(resultado, CategoriaElemento.ESTRUTURA_MT)
    # R-E07.2.2.1-4: a estrutura do regime de texto segue ligada ao P1, pendente por disputa
    ligacoes = [item for item in resultado.relacoes if item.origem_referencia_id == estrutura.id]
    assert [(item.tipo_relacao, item.destino_referencia_id) for item in ligacoes] == [
        ("INSTALADA_EM", postes["P1"])
    ]
    # regiões: o poste pendente forma a sua região (contexto próprio), a estrutura fica na região
    # do rótulo P1; a ligação aparece como vínculo das duas (uma ponta em cada)
    regioes = _regioes(resultado, folha, catalogo_inicial)
    poste_p1 = next(item for item in resultado.elementos if item.id == postes["P1"])
    do_poste = _regiao_do(regioes, poste_p1)
    da_estrutura = _regiao_do(regioes, estrutura)
    assert do_poste.elemento_ids == (postes["P1"],)
    assert da_estrutura.rotulo_ponto == "P1"
    assert do_poste.id != da_estrutura.id
    assert ligacoes[0].id in do_poste.vinculo_ids
    assert ligacoes[0].id in da_estrutura.vinculo_ids


# --- estai em uma ocorrência e ablação ---------------------------------------------------------


def _estai_modelo() -> ObservacaoSimbolo:
    return cena.observacao(
        cena.PERFIL_MODELO, "ESTAI", cena.CAIXA_ESTAI_MODELO, _FOLHA, lado=cena.LADO_ESTAI_MODELO
    )


def _estai_legado(classe: str = "ESTAI") -> ObservacaoSimbolo:
    return cena.observacao(
        cena.PERFIL_LEGADO, classe, cena.CAIXA_ESTAI_LEGADO, _FOLHA, subtipo="ancora"
    )


def test_estai_do_legado_e_do_modelo_sai_em_uma_ocorrencia_na_cadeia(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    modelo, legado = _estai_modelo(), _estai_legado()
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, (modelo,)),
        (cena.PERFIL_LEGADO, (legado,)),
    )

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    (estai,) = _simbolos(resultado, "ESTAI")
    atributos = _atributos(estai)
    assert sorted(json.loads(str(atributos["simbolo_observacao_ids"]))) == sorted(
        [modelo.id, legado.id]
    )
    # a geometria é a do modelo (centro em 0,510), não a do eixo do legado (0,509)
    assert _centro_x(estai) == pytest.approx(0.51, abs=1e-6)
    assert atributos["simbolo_papel"] == "suporte"


def test_leitura_de_outra_classe_sobre_o_estai_nao_funde_e_aparecem_duas_ocorrencias(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, (_estai_modelo(),)),
        (cena.PERFIL_LEGADO, (_estai_legado("PARA_RAIOS"),)),
    )

    resultado = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)

    assert len(simbolos.occurrences) == 2
    assert len(_simbolos(resultado, "ESTAI")) == 1
    assert len(_simbolos(resultado, "PARA_RAIOS")) == 1


def test_ablacao_do_legado_mantem_a_ocorrencia_do_estai_na_cadeia(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    simbolos = _reconciliar(
        (cena.PERFIL_MODELO, (_estai_modelo(),)),
        (cena.PERFIL_LEGADO, (_estai_legado(),)),
    )
    ablacao = next(
        item
        for item in simbolos.ablations
        if item.method_signature == cena.PERFIL_LEGADO.assinatura()
    )
    sem_legado = replace(simbolos, occurrences=ablacao.occurrences)

    completo = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), simbolos)
    reduzido = _executar(engine, catalogo_inicial, _dois_postes(catalogo_inicial), sem_legado)

    assert ablacao.lost_occurrence_ids == ()
    (estai_completo,) = _simbolos(completo, "ESTAI")
    (estai_reduzido,) = _simbolos(reduzido, "ESTAI")
    assert estai_reduzido.geometria == estai_completo.geometria


# --- opção desligada ---------------------------------------------------------------------------


def test_sem_simbolos_nao_ha_proposta_de_simbolo_e_a_estrutura_segue_ligada(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    resultado = _executar(engine, catalogo_inicial, _folha_disputada(catalogo_inicial), None)

    assert _simbolos(resultado) == []
    assert "semantica_simbolos_versao" not in dict(resultado.execucao.parametros)
    (estrutura,) = _elementos(resultado, CategoriaElemento.ESTRUTURA_MT)
    assert [
        item.destino_referencia_id
        for item in resultado.relacoes
        if item.origem_referencia_id == estrutura.id
    ] == [_postes_por_nome(resultado)["P1"]]
