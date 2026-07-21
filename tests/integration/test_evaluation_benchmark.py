from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from tests.evaluation_factories import make_annotation, make_criteria, make_manifest, make_sample

from zeny_project_handler.application.evaluation_benchmark import (
    BenchmarkAvaliacaoError,
    ExecutarBenchmarkAvaliacao,
)
from zeny_project_handler.domain.enums import (
    EstadoConjuntoAvaliacao,
    ModoBenchmark,
    PapelAnotacao,
)
from zeny_project_handler.domain.evaluation import AmostraAvaliacao, AnotacaoAmostra
from zeny_project_handler.ports.evaluation import ResultadoInterpretacaoAvaliacao


class FakeRepository:
    def __init__(self, sample: AmostraAvaliacao, *, frozen: bool = True) -> None:
        state = (
            EstadoConjuntoAvaliacao.CONGELADO if frozen else EstadoConjuntoAvaliacao.EM_PREPARACAO
        )
        self.manifest = make_manifest(test_sample=sample, state=state)
        self.criteria = make_criteria()
        self.annotation = make_annotation(sample=sample)

    def carregar_manifesto(self):  # type: ignore[no-untyped-def]
        return self.manifest

    def carregar_criterios(self):  # type: ignore[no-untyped-def]
        return self.criteria

    def carregar_anotacao(self, amostra_id: str, papel: PapelAnotacao) -> AnotacaoAmostra:
        assert amostra_id == self.annotation.amostra_id
        assert papel is PapelAnotacao.CONSENSO
        return self.annotation

    def salvar_anotacao(self, anotacao: AnotacaoAmostra) -> Path:
        raise NotImplementedError


class FakeInterpreter:
    nome = "fake"
    versao = "1.0"

    def __init__(self, annotation: AnotacaoAmostra) -> None:
        self._annotation = annotation

    def interpretar(self, sample: AmostraAvaliacao, caminho_pdf: Path):  # type: ignore[no-untyped-def]
        assert caminho_pdf.is_file()
        assert sample.id == self._annotation.amostra_id
        return ResultadoInterpretacaoAvaliacao(
            elementos=self._annotation.elementos,
            relacoes=self._annotation.relacoes,
        )


@pytest.mark.integration
def test_benchmark_is_semantically_reproducible(tmp_path: Path) -> None:
    content = b"private synthetic pdf fixture"
    digest = sha256(content).hexdigest()
    sample = make_sample(digest=digest)
    (tmp_path / "source.pdf").write_bytes(content)
    repository = FakeRepository(sample)
    runner = ExecutarBenchmarkAvaliacao(repository, FakeInterpreter(repository.annotation))

    first = runner.executar(
        diretorio_pdfs=tmp_path,
        modo=ModoBenchmark.TESTE_FINAL,
        versao_regras="rules-1",
        configuracao={"threshold": 1},
    )
    second = runner.executar(
        diretorio_pdfs=tmp_path,
        modo=ModoBenchmark.TESTE_FINAL,
        versao_regras="rules-1",
        configuracao={"threshold": 1},
    )

    assert first.approved
    assert first.semantic_signature == second.semantic_signature
    assert first.sample_results[0].latencia_ms >= 0
    assert first.maximum_python_peak_memory_bytes >= 0


@pytest.mark.integration
def test_final_benchmark_refuses_unfrozen_dataset(tmp_path: Path) -> None:
    sample = make_sample()
    repository = FakeRepository(sample, frozen=False)
    runner = ExecutarBenchmarkAvaliacao(repository, FakeInterpreter(repository.annotation))

    with pytest.raises(BenchmarkAvaliacaoError, match="congelado"):
        runner.executar(
            diretorio_pdfs=tmp_path,
            modo=ModoBenchmark.TESTE_FINAL,
            versao_regras="rules-1",
            configuracao={},
        )
