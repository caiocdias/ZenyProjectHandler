from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select
from tests.factories import complete_project
from tests.pdf_fixtures import create_feature_pdf, create_protected_pdf

from zeny_project_handler.adapters.pdf import (
    PdfArquivoInvalidoError,
    PdfProtegidoError,
    PyMuPdfReader,
)
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.adapters.persistence.schema import document_sources
from zeny_project_handler.application.errors import (
    DocumentoDuplicadoError,
    ProjetoNaoEncontradoError,
)
from zeny_project_handler.application.pdf_import import ImportarPdfNoProjeto
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.project import Projeto


@pytest.fixture
def persisted_project(
    tmp_path: Path,
    catalogo_inicial: CatalogoTecnico,
) -> Iterator[tuple[Engine, Projeto]]:
    engine = create_sqlite_engine(tmp_path / "pdf-import.sqlite3")
    upgrade_database(engine)
    project = complete_project(catalogo_inicial)
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(project)
        work.commit()
    try:
        yield engine, project
    finally:
        engine.dispose()


@pytest.mark.integration
def test_valid_pdf_is_added_with_verified_source_in_one_transaction(
    tmp_path: Path,
    persisted_project: tuple[Engine, Projeto],
) -> None:
    engine, original = persisted_project
    source = create_feature_pdf(tmp_path / "novo-projeto.pdf")
    use_case = ImportarPdfNoProjeto(PyMuPdfReader(), lambda: SqlAlchemyUnitOfWork(engine))

    result = use_case.executar(original.id, source)

    assert len(result.projeto.documentos) == len(original.documentos) + 1
    imported = result.inspecao.documento
    with SqlAlchemyUnitOfWork(engine) as work:
        persisted = work.projetos.obter(original.id)
        reference = work.fontes_pdf.obter(imported.id)
    assert persisted == result.projeto
    assert reference is not None
    assert reference.caminho_canonico == source.resolve()
    assert reference.sha256 == imported.sha256


@pytest.mark.integration
def test_invalid_protected_duplicate_and_missing_project_do_not_mutate_existing_project(
    tmp_path: Path,
    persisted_project: tuple[Engine, Projeto],
) -> None:
    engine, project = persisted_project
    source = create_feature_pdf(tmp_path / "duplicado.pdf")
    protected = create_protected_pdf(tmp_path / "protegido.pdf")
    corrupt = tmp_path / "corrompido.pdf"
    corrupt.write_bytes(b"%PDF quebrado")
    use_case = ImportarPdfNoProjeto(PyMuPdfReader(), lambda: SqlAlchemyUnitOfWork(engine))

    with pytest.raises(PdfArquivoInvalidoError):
        use_case.executar(project.id, corrupt)
    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.projetos.obter(project.id) == project
    with pytest.raises(PdfProtegidoError):
        use_case.executar(project.id, protected)
    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.projetos.obter(project.id) == project
    with pytest.raises(ProjetoNaoEncontradoError):
        use_case.executar(uuid4(), source)
    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.projetos.obter(project.id) == project

    first = use_case.executar(project.id, source)
    with pytest.raises(DocumentoDuplicadoError):
        use_case.executar(project.id, source)

    with SqlAlchemyUnitOfWork(engine) as work:
        persisted = work.projetos.obter(project.id)
    assert persisted == first.projeto


@pytest.mark.integration
def test_pdf_source_is_removed_by_project_cascade(
    tmp_path: Path,
    persisted_project: tuple[Engine, Projeto],
) -> None:
    engine, project = persisted_project
    source = create_feature_pdf(tmp_path / "cascade.pdf")
    use_case = ImportarPdfNoProjeto(PyMuPdfReader(), lambda: SqlAlchemyUnitOfWork(engine))
    use_case.executar(project.id, source)

    with SqlAlchemyUnitOfWork(engine) as work:
        assert work.projetos.remover(project.id)
        work.commit()
    with engine.connect() as connection:
        count = connection.scalar(select(func.count()).select_from(document_sources))
    assert count == 0
