"""Desempate da fusão de leituras pontuais pela evidência de OCR localizado (analise padrao).

O golden complementar não exerce `targeted_evidence_ids` de `_deduplicate_point_proposals`, e
acrescentar o caso a ele mudaria os 44 elementos congelados. Este arquivo prende o desempate à
parte: duas leituras do mesmo poste no mesmo lugar, a de código (confiança 0,82) e a de
nomenclatura (0,86). Sem OCR localizado vence a de nomenclatura; com a de código vinda de um motor
de OCR localizado, vence a de código, mesmo menos confiante.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine
from tests.integration.test_golden_padrao_e07 import _EXTRACAO_ID, _PAGINA_ID, _projeto
from tests.interpretation_factories import text_evidence

from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
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
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoExecucaoAnalise

pytestmark = pytest.mark.integration

_MOTORES_LOCALIZADOS = (
    "tesseract-bloco-operacional-localizado",
    "tesseract-rotulo-linear-retificado",
    "tesseract-rotulo-operacional-localizado",
)


def _texto(chave: str, conteudo: str, y: str, motor: str | None = None) -> EvidenciaDocumento:
    base = text_evidence(
        execution_id=_EXTRACAO_ID,
        page_id=_PAGINA_ID,
        key=chave,
        text=conteudo,
        x="0.45",
        y=y,
    )
    if motor is None:
        return base
    return replace(base, atributos_extraidos=(*base.atributos_extraidos, ("motor_ocr", motor)))


def _folha(
    catalogo: CatalogoTecnico, motor_do_codigo: str | None
) -> tuple[EvidenciaDocumento, ...]:
    codigo = next(
        item.codigo
        for item in catalogo.itens_ativos(CategoriaElemento.POSTE)
        if item.codigo.startswith("P-11M-300DAN-CIRCULAR")
    )
    return (
        _texto("codigo", f"POSTE {codigo}", "0.22", motor_do_codigo),
        _texto("nomenclatura", "11M-300 CIRCULAR", "0.22"),
        _texto("rotulo", "P24", "0.19"),
    )


def _executar(
    engine: Engine, catalogo: CatalogoTecnico, evidencias: tuple[EvidenciaDocumento, ...]
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
        work.catalogos.salvar(catalogo)
        work.projetos.salvar(projeto)
        work.execucoes_analise.salvar(extracao)
        for item in evidencias:
            work.evidencias.salvar(item)
        work.commit()
    registro = carregar_registro_regras_inicial()
    return ExecutarPipelineInterpretacao(
        InterpretadorRegrasExplicitas(registro),
        registro,
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 7, 21, 13, tzinfo=UTC),
    ).executar(projeto.id, extracao.id)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    motor = create_sqlite_engine(tmp_path / "dedup.sqlite3")
    upgrade_database(motor)
    try:
        yield motor
    finally:
        motor.dispose()


def _poste_unico(resultado: ResultadoExecucaoInterpretacao) -> PropostaElemento:
    (poste,) = (item for item in resultado.elementos if item.categoria is CategoriaElemento.POSTE)
    return poste


def test_sem_ocr_localizado_a_leitura_de_nomenclatura_mais_confiante_vence(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    poste = _poste_unico(_executar(engine, catalogo_inicial, _folha(catalogo_inicial, None)))

    assert poste.confianca == Decimal("0.86")
    assert poste.codigo_observado == "11-300"
    assert len(poste.evidencia_ids) == 3


@pytest.mark.parametrize("motor", _MOTORES_LOCALIZADOS)
def test_leitura_de_ocr_localizado_vence_a_mais_confiante_e_une_as_evidencias(
    engine: Engine, catalogo_inicial: CatalogoTecnico, motor: str
) -> None:
    poste = _poste_unico(_executar(engine, catalogo_inicial, _folha(catalogo_inicial, motor)))

    assert poste.confianca == Decimal("0.82")
    assert poste.codigo_observado != "11-300"
    # texto do código + texto da nomenclatura + rótulo P24, mesmo com a leitura de menor confiança
    assert len(poste.evidencia_ids) == 3
