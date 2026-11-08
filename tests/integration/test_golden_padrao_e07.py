"""Golden da análise padrão (`simbolos=None`): congela a saída para provar a decisão D18.

Para regenerar o golden de propósito (somente com uma mudança de comportamento aprovada), rode
``python -m tests.integration.test_golden_padrao_e07`` a partir da raiz do repositório.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import UUID, uuid5

import pytest
from sqlalchemy import Engine
from tests.interpretation_factories import image_evidence, text_evidence, vector_evidence

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
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
from zeny_project_handler.domain.analysis import EvidenciaDocumento, ExecucaoAnalise
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoExecucaoAnalise
from zeny_project_handler.domain.project import Projeto
from zeny_project_handler.domain.values import CaixaPagina

pytestmark = pytest.mark.integration

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "golden_padrao_e07.json"

_RAIZ = UUID("00000000-0000-5000-8000-0000000000e7")
_PROJETO_ID = uuid5(_RAIZ, "projeto")
_EXTRACAO_ID = uuid5(_RAIZ, "extracao")
_PAGINA_ID = uuid5(_RAIZ, "pagina")
_DOCUMENTO_ID = uuid5(_RAIZ, "documento")
_VERDE = "#008000"
_VERMELHO = "#FF0000"


def _projeto(catalogo: CatalogoTecnico) -> Projeto:
    caixa = CaixaPagina(Decimal(0), Decimal(0), Decimal(1000), Decimal(700))
    pagina = PaginaDocumento(
        id=_PAGINA_ID,
        numero=1,
        largura_pontos=Decimal(1000),
        altura_pontos=Decimal(700),
        rotacao_graus=0,
        media_box=caixa,
        crop_box=caixa,
    )
    documento = DocumentoProjeto(
        id=_DOCUMENTO_ID,
        nome_arquivo="golden-e07.pdf",
        sha256="e" * 64,
        paginas=(pagina,),
        tamanho_bytes=1234,
        versao_pdf="1.7",
        produtor="AutoCAD",
    )
    return Projeto(
        id=_PROJETO_ID,
        nome="Golden E07",
        catalogo_versao_id=catalogo.id,
        criado_em=datetime(2026, 7, 21, 10, tzinfo=UTC),
        documentos=(documento,),
    )


def _evidencias(catalogo: CatalogoTecnico) -> tuple[EvidenciaDocumento, ...]:
    def texto(chave: str, conteudo: str, x: str, y: str, **extra: str) -> EvidenciaDocumento:
        return text_evidence(
            execution_id=_EXTRACAO_ID,
            page_id=_PAGINA_ID,
            key=chave,
            text=conteudo,
            x=x,
            y=y,
            **extra,
        )

    cabo_a, cabo_b = (item.codigo for item in catalogo.itens_ativos(CategoriaElemento.CABO)[:2])
    postes = tuple(item.codigo for item in catalogo.itens_ativos(CategoriaElemento.POSTE))
    return (
        # P1 e P2: postes com nomenclatura, coordenada e cabo com traçado e comprimento.
        texto("poste-p1", f"POSTE {postes[3]}", "0.10", "0.30", color=_VERDE),
        texto("rotulo-p1", "P1", "0.10", "0.27"),
        texto("leste-p1", "0465702", "0.12", "0.33"),
        texto("norte-p1", "7772468", "0.13", "0.33"),
        texto("poste-p2", f"POSTE {postes[4]}", "0.60", "0.30", color=_VERDE),
        texto("rotulo-p2", "P2", "0.60", "0.27"),
        texto("leste-p2", "0465750", "0.62", "0.33"),
        texto("norte-p2", "7772490", "0.63", "0.33"),
        texto("cabo-rotulo", cabo_a, "0.35", "0.32", color=_VERDE),
        texto("vao-rotulo", "V1-2", "0.35", "0.27"),
        texto("vao-comprimento", "Vão: 42,5 m", "0.35", "0.29"),
        vector_evidence(
            execution_id=_EXTRACAO_ID,
            page_id=_PAGINA_ID,
            key="cabo-tracado",
            points=(("0.10", "0.30"), ("0.60", "0.30")),
            color=_VERDE,
        ),
        # P3: duas leituras do mesmo identificador, a até 0,10 uma da outra, com catálogos
        # diferentes (a deduplicação não as funde), e uma estrutura equidistante delas.
        texto("poste-p3-a", f"POSTE {postes[0]}", "0.20", "0.70", color=_VERDE),
        texto("poste-p3-b", f"POSTE {postes[1]}", "0.28", "0.70", color=_VERDE),
        texto("rotulo-p3", "P3", "0.24", "0.66"),
        texto("estrutura-p3", "U1", "0.24", "0.70", color=_VERDE, rotation="90"),
        # Cabo cujo rótulo é equidistante de dois traçados paralelos: associação pendente.
        texto("cabo-ambiguo-rotulo", cabo_b, "0.82", "0.505", color=_VERDE),
        vector_evidence(
            execution_id=_EXTRACAO_ID,
            page_id=_PAGINA_ID,
            key="cabo-ambiguo-tracado-a",
            points=(("0.70", "0.50"), ("0.95", "0.50")),
            color=_VERDE,
        ),
        vector_evidence(
            execution_id=_EXTRACAO_ID,
            page_id=_PAGINA_ID,
            key="cabo-ambiguo-tracado-b",
            points=(("0.70", "0.51"), ("0.95", "0.51")),
            color=_VERDE,
        ),
        # Estrutura MT com qualificador, estrutura BT e equipamento junto de P1 e P2.
        texto("estrutura-mt-qualificada", "N(2)", "0.11", "0.29", color=_VERDE),
        texto("estrutura-bt", "S1N", "0.61", "0.31", color=_VERMELHO),
        texto("rotulo-p4", "P4", "0.85", "0.25"),
        texto(
            "equipamento",
            catalogo.itens_ativos(CategoriaElemento.EQUIPAMENTO)[0].codigo,
            "0.85",
            "0.28",
        ),
        image_evidence(
            execution_id=_EXTRACAO_ID,
            page_id=_PAGINA_ID,
            key="equipamento-imagem",
            x="0.85",
            y="0.28",
        ),
    )


def _executar(engine: Engine, catalogo: CatalogoTecnico) -> ResultadoExecucaoInterpretacao:
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
        for item in _evidencias(catalogo):
            work.evidencias.salvar(item)
        work.commit()
    registro = carregar_registro_regras_inicial()
    return ExecutarPipelineInterpretacao(
        InterpretadorRegrasExplicitas(registro),
        registro,
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 7, 21, 13, tzinfo=UTC),
    ).executar(projeto.id, extracao.id)


def _valor(valor: Any) -> Any:
    if is_dataclass(valor) and not isinstance(valor, type):
        return {campo.name: _valor(getattr(valor, campo.name)) for campo in fields(valor)}
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, (tuple, list)):
        return [_valor(item) for item in valor]
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    return str(valor)


def _serializar(resultado: ResultadoExecucaoInterpretacao) -> dict[str, Any]:
    execucao = resultado.execucao
    dados = {
        "id": str(execucao.id),
        "metodo": execucao.metodo,
        "versao_metodo": execucao.versao_metodo,
        "parametros": _valor(execucao.parametros),
        "elementos": [
            _valor(item) for item in sorted(resultado.elementos, key=lambda item: str(item.id))
        ],
        "relacoes": [
            _valor(item) for item in sorted(resultado.relacoes, key=lambda item: str(item.id))
        ],
    }
    # Tupla não é igual a lista: normaliza como o arquivo JSON.
    normalizado: dict[str, Any] = json.loads(json.dumps(dados, ensure_ascii=False))
    return normalizado


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    motor = create_sqlite_engine(tmp_path / "golden.sqlite3")
    upgrade_database(motor)
    try:
        yield motor
    finally:
        motor.dispose()


def test_analise_padrao_mantem_saida_congelada(
    engine: Engine, catalogo_inicial: CatalogoTecnico
) -> None:
    resultado = _serializar(_executar(engine, catalogo_inicial))

    assert resultado == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_golden_e_da_opcao_desligada(engine: Engine, catalogo_inicial: CatalogoTecnico) -> None:
    resultado = _serializar(_executar(engine, catalogo_inicial))

    parametros = dict(resultado["parametros"])
    assert resultado["versao_metodo"] == "25.0"
    assert "semantica_simbolos_versao" not in parametros
    assert "simbolos_reconciliados_assinatura" not in parametros
    assert "configuracao_simbolos_assinatura" not in parametros


def _gerar_golden() -> None:
    with TemporaryDirectory() as pasta:
        motor = create_sqlite_engine(Path(pasta) / "golden.sqlite3")
        upgrade_database(motor)
        try:
            resultado = _serializar(_executar(motor, carregar_catalogo_inicial()))
        finally:
            motor.dispose()
    GOLDEN.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    _gerar_golden()
