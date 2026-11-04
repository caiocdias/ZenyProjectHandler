"""Folha com rótulos em contorno de glifo gera as mesmas propostas que a mesma folha nativa."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests.factories import complete_project
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    pdf_texto_nativo,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.document_analysis import ExecutarAnaliseDocumento
from zeny_project_handler.application.interpretation_pipeline import ExecutarPipelineInterpretacao
from zeny_project_handler.application.pdf_import import ImportarPdfNoProjeto
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, SituacaoProjeto
from zeny_project_handler.ports.analysis import ConfiguracaoAnaliseDocumento

pytestmark = pytest.mark.integration

_VERDE = (0.0, 0.5, 0.0)
_VERMELHO = (1.0, 0.0, 0.0)
# valores inventados: identificador e estruturas na primeira linha, poste na segunda
_FOLHA = (
    LinhaTexto("P7 U4(1) S1N", (60.0, 80.0), 5.0, cor=_VERDE),
    LinhaTexto("11-300", (60.0, 88.0), 5.0, cor=_VERDE),
    LinhaTexto("P8 N1", (220.0, 80.0), 5.0, cor=_VERMELHO),
    LinhaTexto("11-600", (220.0, 88.0), 5.0, cor=_VERMELHO),
)
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

_Proposta = tuple[CategoriaElemento, SituacaoProjeto, str | None, tuple[tuple[str, str], ...]]


def _sem_ids(proposta: PropostaElemento) -> _Proposta:
    atributos = tuple(
        (chave, _UUID.sub("<id>", str(valor)))
        for chave, valor in proposta.atributos_sugeridos
        if not chave.endswith("_id")
    )
    return (proposta.categoria, proposta.situacao_projeto, proposta.codigo_observado, atributos)


def _propostas(
    tmp_path: Path, catalogo: CatalogoTecnico, pdf: Path, tabela: TabelaGlifos
) -> list[_Proposta]:
    engine = create_sqlite_engine(tmp_path / f"{pdf.stem}.sqlite3")
    upgrade_database(engine)
    try:
        projeto = complete_project(catalogo)
        with SqlAlchemyUnitOfWork(engine) as work:
            work.catalogos.salvar(catalogo)
            work.projetos.salvar(projeto)
            work.commit()

        def unidade() -> SqlAlchemyUnitOfWork:
            return SqlAlchemyUnitOfWork(engine)

        importado = ImportarPdfNoProjeto(PyMuPdfReader(), unidade).executar(projeto.id, pdf)
        analise = ExecutarAnaliseDocumento(
            PyMuPdfDocumentAnalyzer(tabela_glifos=tabela), unidade
        ).executar(
            projeto.id,
            importado.inspecao.documento.id,
            configuracao=ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False),
        )
        registro = carregar_registro_regras_inicial()
        interpretado = ExecutarPipelineInterpretacao(
            InterpretadorRegrasExplicitas(registro), registro, unidade
        ).executar(projeto.id, analise.execucao.id)
    finally:
        engine.dispose()
    return sorted(
        (_sem_ids(proposta) for proposta in interpretado.elementos),
        key=lambda p: (p[0].value, p[1].value, p[2] or "", p[3]),
    )


def test_folha_em_contorno_e_nativa_geram_as_mesmas_propostas(
    tmp_path: Path, catalogo_inicial: CatalogoTecnico
) -> None:
    tabela = tabela_do_alfabeto(tmp_path)
    nativo = pdf_texto_nativo(tmp_path / "nativo.pdf", _FOLHA)
    contorno = pdf_texto_contorno(tmp_path / "contorno.pdf", _FOLHA)

    esperado = _propostas(tmp_path, catalogo_inicial, nativo, tabela)
    lido = _propostas(tmp_path, catalogo_inicial, contorno, tabela)

    assert {(p[0], p[1]) for p in esperado} >= {
        (CategoriaElemento.POSTE, SituacaoProjeto.INSTALAR),
        (CategoriaElemento.POSTE, SituacaoProjeto.REMOVER),
        (CategoriaElemento.ESTRUTURA_MT, SituacaoProjeto.INSTALAR),
        (CategoriaElemento.ESTRUTURA_MT, SituacaoProjeto.REMOVER),
        (CategoriaElemento.ESTRUTURA_BT, SituacaoProjeto.INSTALAR),
    }
    assert lido == esperado
