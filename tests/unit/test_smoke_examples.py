from pathlib import Path

import pytest
from scripts.smoke_examples import descobrir_pdfs, executar_smoke_pdf, main
from tests.pdf_fixtures import create_analysis_pdf


def test_dynamic_smoke_discovers_nested_pdfs_without_a_manifest(tmp_path: Path) -> None:
    nested = tmp_path / "novas-amostras"
    nested.mkdir()
    first = create_analysis_pdf(tmp_path / "primeiro.pdf")
    second = create_analysis_pdf(nested / "SEGUNDO.PDF")
    (tmp_path / "ignorar.txt").write_text("não é PDF", encoding="utf-8")

    assert descobrir_pdfs(tmp_path) == tuple(
        sorted((first, second), key=lambda caminho: caminho.as_posix().casefold())
    )


def test_dynamic_smoke_runs_the_real_native_pipeline_without_changing_source(
    tmp_path: Path,
) -> None:
    source = create_analysis_pdf(tmp_path / "projeto-sintetico.pdf")
    before = source.stat()

    result = executar_smoke_pdf(source)

    after = source.stat()
    assert result.paginas == 2
    assert result.evidencias
    assert result.propostas
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)


def test_dynamic_smoke_is_optional_when_no_local_pdf_exists(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([str(tmp_path)]) == 0
    assert "Nenhum PDF local encontrado" in capsys.readouterr().out
