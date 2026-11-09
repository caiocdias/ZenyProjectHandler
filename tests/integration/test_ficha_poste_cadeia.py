"""Cadeia completa com `InterpretadorFichaPoste` (26.0): ancoragem, relações, promoção e região.

Cada caso monta uma folha sintética pequena, roda o pipeline persistido com a subclasse e confere o
que a E07.2.1 promete: o poste sai no disco do desenho, `INSTALADA_EM` segue a posição do texto,
`CONECTA` segue o disco, a promoção automática vale e a região é única com o rótulo P. Ambiguidade
de disco fica pendente e sem relação errada.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid5

import pytest
from sqlalchemy import Engine
from tests.integration.test_golden_padrao_e07 import (
    _EXTRACAO_ID,
    _PAGINA_ID,
    _VERDE,
    _projeto,
)
from tests.interpretation_factories import text_evidence, vector_evidence

from zeny_project_handler.adapters.interpretation import carregar_registro_regras_inicial
from zeny_project_handler.adapters.interpretation.ficha_poste import InterpretadorFichaPoste
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.analysis_regions import (
    RegiaoAnalise,
    agrupar_regioes_da_analise,
)
from zeny_project_handler.application.interpretation_pipeline import (
    ExecutarPipelineInterpretacao,
    ResultadoExecucaoInterpretacao,
)
from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    TipoEvidencia,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

pytestmark = pytest.mark.integration

_DISCO_VERDE = "#007000"


def _texto(chave: str, conteudo: str, x: str, y: str, **extra: str) -> EvidenciaDocumento:
    return text_evidence(
        execution_id=_EXTRACAO_ID,
        page_id=_PAGINA_ID,
        key=chave,
        text=conteudo,
        x=x,
        y=y,
        **extra,
    )


def _disco(chave: str, x: float, y: float) -> EvidenciaDocumento:
    """Disco verde de 1,7 pt de diâmetro (`operacoes="c,c,c,c"`), como o extrator VETOR emite."""
    meia = 0.85
    curvas = [
        ["c", [-meia, 0], [-meia, 0], [0, -meia], [0, -meia]],
        ["c", [0, -meia], [meia, 0], [meia, 0], [meia, 0]],
        ["c", [meia, 0], [0, meia], [0, meia], [0, meia]],
        ["c", [0, meia], [-meia, 0], [-meia, 0], [-meia, 0]],
    ]
    return EvidenciaDocumento(
        id=uuid5(_EXTRACAO_ID, chave),
        execucao_id=_EXTRACAO_ID,
        pagina_id=_PAGINA_ID,
        tipo=TipoEvidencia.VETOR,
        geometria=GeometriaDocumento.caixa(
            _PAGINA_ID,
            PontoNormalizado(*_decimais(x - 0.001, y - 0.001)),
            PontoNormalizado(*_decimais(x + 0.001, y + 0.001)),
        ),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto=json.dumps(curvas),
        criada_em=datetime(2026, 7, 21, 12, tzinfo=UTC),
        atributos_extraidos=(
            ("operacoes", "c,c,c,c"),
            ("cor_preenchimento", _DISCO_VERDE),
            ("tipo_caminho", "f"),
        ),
    )


def _decimais(x: float, y: float) -> tuple[Decimal, Decimal]:
    return Decimal(str(round(x, 6))), Decimal(str(round(y, 6)))


def _poste(
    catalogo: CatalogoTecnico, chave: str, identificador: str, x: str, y: str
) -> tuple[EvidenciaDocumento, ...]:
    """Nomenclatura verde de poste mais o rótulo P<n> 0,03 acima."""
    codigo = catalogo.itens_ativos(CategoriaElemento.POSTE)[3].codigo
    return (
        _texto(f"{chave}-poste", f"POSTE {codigo}", x, y, color=_VERDE),
        _texto(f"{chave}-rotulo", identificador, x, str(round(float(y) - 0.03, 4))),
    )


def _estrutura(chave: str, x: str, y: str) -> EvidenciaDocumento:
    return _texto(chave, "U1", x, y, color=_VERDE, rotation="90")


def _cabo(
    catalogo: CatalogoTecnico,
    chave: str,
    pontos: tuple[tuple[str, str], ...],
    rotulo: tuple[str, str],
) -> tuple[EvidenciaDocumento, ...]:
    cabo = catalogo.itens_ativos(CategoriaElemento.CABO)[1].codigo
    return (
        vector_evidence(
            execution_id=_EXTRACAO_ID,
            page_id=_PAGINA_ID,
            key=f"{chave}-tracado",
            points=pontos,
            color=_VERDE,
        ),
        _texto(f"{chave}-cabo", cabo, rotulo[0], rotulo[1], color=_VERDE),
    )


def _executar(
    engine: Engine, catalogo: CatalogoTecnico, evidencias: tuple[EvidenciaDocumento, ...]
) -> tuple[ResultadoExecucaoInterpretacao, tuple[EvidenciaDocumento, ...]]:
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
        work.catalogos.salvar(catalogo)
        work.projetos.salvar(projeto)
        work.execucoes_analise.salvar(extracao)
        for item in evidencias:
            work.evidencias.salvar(item)
        work.commit()
    registro = carregar_registro_regras_inicial()
    resultado = ExecutarPipelineInterpretacao(
        InterpretadorFichaPoste(registro),
        registro,
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 7, 21, 13, tzinfo=UTC),
    ).executar(projeto.id, extracao.id)
    return resultado, evidencias


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    motor = create_sqlite_engine(tmp_path / "cadeia.sqlite3")
    upgrade_database(motor)
    try:
        yield motor
    finally:
        motor.dispose()


def _elementos(
    resultado: ResultadoExecucaoInterpretacao, categoria: CategoriaElemento
) -> list[PropostaElemento]:
    return [item for item in resultado.elementos if item.categoria is categoria]


def _poste_unico(resultado: ResultadoExecucaoInterpretacao) -> PropostaElemento:
    (poste,) = _elementos(resultado, CategoriaElemento.POSTE)
    return poste


def _atributos(elemento: PropostaElemento) -> dict[str, object]:
    return dict(elemento.atributos_sugeridos)


def _centro(elemento: PropostaElemento) -> tuple[float, float]:
    pontos = elemento.geometria.pontos
    return (
        float(sum(p.x for p in pontos) / len(pontos)),
        float(sum(p.y for p in pontos) / len(pontos)),
    )


def _destinos(resultado: ResultadoExecucaoInterpretacao, tipo: str) -> list[object]:
    return [item.destino_referencia_id for item in resultado.relacoes if item.tipo_relacao == tipo]


def _regioes(
    resultado: ResultadoExecucaoInterpretacao,
    evidencias: tuple[EvidenciaDocumento, ...],
    catalogo: CatalogoTecnico,
) -> tuple[RegiaoAnalise, ...]:
    return agrupar_regioes_da_analise(
        (*resultado.elementos, *resultado.relacoes),
        evidencias,
        _projeto(catalogo).documentos,
    )


def _folha_com_disco(
    catalogo: CatalogoTecnico, disco: tuple[float, float]
) -> tuple[EvidenciaDocumento, ...]:
    """P1 com estrutura e um cabo de um extremo só, que parte do disco do poste."""
    x, y = disco
    return (
        *_poste(catalogo, "p1", "P1", "0.30", "0.30"),
        _estrutura("estrutura", "0.30", "0.32"),
        *_cabo(
            catalogo,
            "cabo",
            ((str(x), str(y)), (str(round(x + 0.06, 6)), str(y))),
            (str(round(x + 0.03, 6)), str(round(y + 0.01, 6))),
        ),
        _disco("disco-p1", x, y),
    )


def _verifica_cadeia(
    resultado: ResultadoExecucaoInterpretacao,
    evidencias: tuple[EvidenciaDocumento, ...],
    catalogo: CatalogoTecnico,
) -> PropostaElemento:
    poste = _poste_unico(resultado)
    (estrutura,) = _elementos(resultado, CategoriaElemento.ESTRUTURA_MT)
    (cabo,) = _elementos(resultado, CategoriaElemento.CABO)
    tipos = {item.tipo_relacao for item in resultado.relacoes}
    assert {"INSTALADA_EM", "CONECTA"} <= tipos
    assert _destinos(resultado, "INSTALADA_EM") == [poste.id]
    assert _destinos(resultado, "CONECTA") == [poste.id]
    assert {item.origem_referencia_id for item in resultado.relacoes} == {estrutura.id, cabo.id}
    assert poste.estado_revisao is EstadoRevisao.CONFIRMADA
    (regiao,) = _regioes(resultado, evidencias, catalogo)
    assert regiao.rotulo_ponto == "P1"
    assert {poste.id, estrutura.id, cabo.id} <= set(regiao.elemento_ids)
    return poste


def test_cadeia_completa_com_disco_ancora_vincula_promove_e_forma_uma_regiao(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    resultado, evidencias = _executar(
        engine, catalogo_inicial, _folha_com_disco(catalogo_inicial, (0.305, 0.30))
    )

    poste = _verifica_cadeia(resultado, evidencias, catalogo_inicial)

    assert _atributos(poste)["poste_ancorado_disco"] is True
    assert _centro(poste) == pytest.approx((0.305, 0.30), abs=1e-6)


def test_disco_a_mais_de_0_10_da_estrutura_mantem_regimes_separados_e_regiao_unica(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    # Estrutura em (0.30, 0.32); centro do disco a 0,1005 dela (>0,10), com folga de caixa de
    # 0,0995 (<=0,10): INSTALADA_EM usa o texto do poste e a região ainda os reúne.
    resultado, evidencias = _executar(
        engine, catalogo_inicial, _folha_com_disco(catalogo_inicial, (0.4005, 0.32))
    )

    poste = _verifica_cadeia(resultado, evidencias, catalogo_inicial)

    assert _atributos(poste)["poste_ancorado_disco"] is True
    assert _centro(poste) == pytest.approx((0.4005, 0.32), abs=1e-6)


def test_folga_de_caixa_acima_de_0_10_separa_a_regiao_e_e_limite_conhecido(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    # Mesma folha com o disco 0,001 mais longe (folga 0,1005): INSTALADA_EM e CONECTA continuam,
    # mas a região, que mede caixa contra caixa com limite de 0,10, separa estrutura e poste.
    resultado, evidencias = _executar(
        engine, catalogo_inicial, _folha_com_disco(catalogo_inicial, (0.4015, 0.32))
    )

    poste = _poste_unico(resultado)

    assert _destinos(resultado, "INSTALADA_EM") == [poste.id]
    assert _destinos(resultado, "CONECTA") == [poste.id]
    assert len(_regioes(resultado, evidencias, catalogo_inicial)) == 2


def test_poste_sem_disco_mantem_posicao_vinculos_promocao_e_regiao(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    folha = (
        *_poste(catalogo_inicial, "p1", "P1", "0.30", "0.30"),
        _estrutura("estrutura", "0.30", "0.32"),
        *_cabo(catalogo_inicial, "cabo", (("0.30", "0.30"), ("0.36", "0.30")), ("0.33", "0.31")),
        _disco("disco-de-outro-lugar", 0.80, 0.60),
    )
    resultado, evidencias = _executar(engine, catalogo_inicial, folha)

    poste = _verifica_cadeia(resultado, evidencias, catalogo_inicial)

    atributos = _atributos(poste)
    assert atributos["poste_ancorado_disco"] is False
    assert "poste_texto_centro" not in atributos
    assert "associacao_pendente" not in atributos
    assert _centro(poste) == pytest.approx((0.30, 0.30), abs=1e-6)


def test_ambiguidade_de_disco_fica_pendente_sem_relacao_errada(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    # Dois P disputam o único disco, no meio deles.
    folha = (
        *_poste(catalogo_inicial, "p1", "P1", "0.30", "0.30"),
        *_poste(catalogo_inicial, "p2", "P2", "0.34", "0.30"),
        _estrutura("estrutura", "0.30", "0.32"),
        _disco("disco-disputado", 0.32, 0.30),
    )
    resultado, _ = _executar(engine, catalogo_inicial, folha)

    postes = _elementos(resultado, CategoriaElemento.POSTE)
    ids = {item.id for item in postes}

    assert len(postes) == 2
    # P1 tem a estrutura U1 (ela herda o identificador P1 e também sai CONFLITANTE, sem relação),
    # e por isso o poste sai CONFLITANTE; P2, sem estrutura, fica PROPOSTA. Nenhum é CONFIRMADA,
    # porque `associacao_pendente` barra a promoção automática.
    estados = {
        _atributos(poste)["identificador_operacional"]: poste.estado_revisao for poste in postes
    }
    assert estados == {"P1": EstadoRevisao.CONFLITANTE, "P2": EstadoRevisao.PROPOSTA}
    posicoes = {"P1": (0.30, 0.30), "P2": (0.34, 0.30)}
    for poste in postes:
        atributos = _atributos(poste)
        assert atributos["associacao_pendente"] == "poste_disco"
        assert atributos["poste_ancorado_disco"] is False
        # fica na posição do texto, sem o disco disputado e sem o centro do texto reservado
        assert "poste_texto_centro" not in atributos
        assert _centro(poste) == pytest.approx(
            posicoes[str(atributos["identificador_operacional"])], abs=1e-6
        )
    assert not any(
        {item.origem_referencia_id, item.destino_referencia_id} & ids for item in resultado.relacoes
    )
