"""Execução reproduzível do benchmark sem expor nomes dos PDFs privados."""

from __future__ import annotations

import json
import tracemalloc
from collections import defaultdict
from collections.abc import Mapping
from decimal import Decimal
from hashlib import sha256
from math import ceil
from pathlib import Path
from time import perf_counter_ns

from zeny_project_handler.application.evaluation_metrics import calcular_metricas_semanticas
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoConjuntoAvaliacao,
    EstadoCriteriosAvaliacao,
    ModoBenchmark,
    PapelAnotacao,
    ParticaoAvaliacao,
)
from zeny_project_handler.domain.evaluation import (
    AmostraAvaliacao,
    CriteriosRegressaoAvaliacao,
    validar_anotacao_no_manifesto,
)
from zeny_project_handler.domain.evaluation_metrics import (
    ContagemDeteccao,
    MetricasAmostra,
    MetricasCategoria,
    RelatorioBenchmarkAvaliacao,
)
from zeny_project_handler.ports.evaluation import (
    InterpretadorAvaliacaoPort,
    RepositorioConjuntoAvaliacaoPort,
    ResultadoInterpretacaoAvaliacao,
)


class BenchmarkAvaliacaoError(RuntimeError):
    """O benchmark não pode ser executado de forma íntegra."""


class ExecutarBenchmarkAvaliacao:
    def __init__(
        self,
        repository: RepositorioConjuntoAvaliacaoPort,
        interpreter: InterpretadorAvaliacaoPort,
    ) -> None:
        self._repository = repository
        self._interpreter = interpreter

    def executar(
        self,
        *,
        diretorio_pdfs: Path,
        modo: ModoBenchmark,
        versao_regras: str,
        configuracao: Mapping[str, str | int | bool | None],
    ) -> RelatorioBenchmarkAvaliacao:
        manifest = self._repository.carregar_manifesto()
        criteria = self._repository.carregar_criterios()
        if modo is ModoBenchmark.TESTE_FINAL:
            if manifest.estado is not EstadoConjuntoAvaliacao.CONGELADO:
                raise BenchmarkAvaliacaoError("Teste final exige conjunto congelado")
            if criteria.estado is not EstadoCriteriosAvaliacao.APROVADO:
                raise BenchmarkAvaliacaoError("Teste final exige critérios aprovados")
        partition = (
            ParticaoAvaliacao.TESTE
            if modo is ModoBenchmark.TESTE_FINAL
            else ParticaoAvaliacao.DESENVOLVIMENTO
        )
        samples = tuple(item for item in manifest.amostras if item.particao is partition)
        paths_by_hash = _index_pdfs(diretorio_pdfs)
        results: list[MetricasAmostra] = []
        for sample in samples:
            source = paths_by_hash.get(sample.sha256)
            if source is None:
                raise BenchmarkAvaliacaoError(f"PDF privado ausente para {sample.id}")
            reference = self._repository.carregar_anotacao(sample.id, PapelAnotacao.CONSENSO)
            validar_anotacao_no_manifesto(reference, manifest)
            prediction, latency, memory = self._measure(sample, source)
            categories, relations = calcular_metricas_semanticas(
                reference.elementos,
                reference.relacoes,
                prediction.elementos,
                prediction.relacoes,
                criteria,
            )
            results.append(
                MetricasAmostra(
                    amostra_id=sample.id,
                    categorias=categories,
                    relacoes=relations,
                    falhas_extracao=prediction.falhas_extracao,
                    latencia_ms=latency,
                    memoria_python_pico_bytes=memory,
                )
            )
        aggregate_categories = _aggregate_categories(results)
        aggregate_relations = _aggregate_relations(results)
        failure_rate = Decimal(sum(bool(item.falhas_extracao) for item in results)) / Decimal(
            len(results)
        )
        latency_p95 = _percentile_95(tuple(item.latencia_ms for item in results))
        maximum_memory = max(item.memoria_python_pico_bytes for item in results)
        violations = _criteria_violations(
            aggregate_categories,
            aggregate_relations,
            failure_rate,
            latency_p95,
            maximum_memory,
            criteria,
        )
        signature = _semantic_signature(
            manifest.conjunto_id,
            manifest.versao,
            criteria.versao,
            self._interpreter.nome,
            self._interpreter.versao,
            versao_regras,
            configuracao,
            results,
        )
        return RelatorioBenchmarkAvaliacao(
            dataset_id=manifest.conjunto_id,
            dataset_version=manifest.versao,
            criteria_version=criteria.versao,
            interpreter=self._interpreter.nome,
            interpreter_version=self._interpreter.versao,
            rules_version=versao_regras,
            sample_results=tuple(results),
            aggregate_categories=aggregate_categories,
            aggregate_relations=aggregate_relations,
            extraction_failure_rate=failure_rate,
            latency_p95_ms=latency_p95,
            maximum_python_peak_memory_bytes=maximum_memory,
            semantic_signature=signature,
            approved=not violations,
            violations=violations,
        )

    def _measure(
        self, sample: AmostraAvaliacao, source: Path
    ) -> tuple[ResultadoInterpretacaoAvaliacao, Decimal, int]:
        tracemalloc.start()
        started = perf_counter_ns()
        try:
            try:
                result = self._interpreter.interpretar(sample, source)
            except Exception:
                result = ResultadoInterpretacaoAvaliacao(
                    elementos=(), falhas_extracao=("INTERPRETER_EXCEPTION",)
                )
            elapsed_ms = Decimal(perf_counter_ns() - started) / Decimal(1_000_000)
            _, peak = tracemalloc.get_traced_memory()
            return result, elapsed_ms, peak
        finally:
            tracemalloc.stop()


def _index_pdfs(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        raise BenchmarkAvaliacaoError("Diretório de PDFs não existe")
    result: dict[str, Path] = {}
    for path in directory.glob("*.pdf"):
        digest = _file_sha256(path)
        if digest in result:
            raise BenchmarkAvaliacaoError("Corpus contém PDFs duplicados")
        result[digest] = path
    return result


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _aggregate_categories(results: list[MetricasAmostra]) -> tuple[MetricasCategoria, ...]:
    counts: dict[CategoriaElemento, ContagemDeteccao] = defaultdict(
        lambda: ContagemDeteccao(verdadeiros_positivos=0, falsos_positivos=0, falsos_negativos=0)
    )
    for result in results:
        for metric in result.categorias:
            counts[metric.categoria] = counts[metric.categoria].somar(metric.contagem)
    return tuple(
        MetricasCategoria(categoria=item, contagem=counts[item]) for item in CategoriaElemento
    )


def _aggregate_relations(results: list[MetricasAmostra]) -> ContagemDeteccao:
    total = ContagemDeteccao(verdadeiros_positivos=0, falsos_positivos=0, falsos_negativos=0)
    for result in results:
        total = total.somar(result.relacoes)
    return total


def _percentile_95(values: tuple[Decimal, ...]) -> Decimal:
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * 0.95) - 1)]


def _criteria_violations(
    categories: tuple[MetricasCategoria, ...],
    relations: ContagemDeteccao,
    failure_rate: Decimal,
    latency_p95: Decimal,
    maximum_memory: int,
    criteria: CriteriosRegressaoAvaliacao,
) -> tuple[str, ...]:
    limits = {item.categoria: item for item in criteria.limites_categoria}
    violations: list[str] = []
    for metric in categories:
        limit = limits[metric.categoria]
        if metric.contagem.precisao < limit.precisao_minima:
            violations.append(f"PRECISAO_INSUFICIENTE:{metric.categoria.value}")
        if metric.contagem.recall < limit.recall_minimo:
            violations.append(f"RECALL_INSUFICIENTE:{metric.categoria.value}")
    if relations.precisao < criteria.precisao_relacoes_minima:
        violations.append("PRECISAO_RELACOES_INSUFICIENTE")
    if relations.recall < criteria.recall_relacoes_minimo:
        violations.append("RECALL_RELACOES_INSUFICIENTE")
    if failure_rate > criteria.taxa_falhas_extracao_maxima:
        violations.append("TAXA_FALHAS_EXTRACAO_EXCEDIDA")
    if latency_p95 > criteria.latencia_p95_ms_maxima:
        violations.append("LATENCIA_P95_EXCEDIDA")
    if maximum_memory > criteria.memoria_python_pico_bytes_maxima:
        violations.append("MEMORIA_PYTHON_EXCEDIDA")
    return tuple(violations)


def _semantic_signature(
    dataset_id: str,
    dataset_version: str,
    criteria_version: str,
    interpreter: str,
    interpreter_version: str,
    rules_version: str,
    configuration: Mapping[str, str | int | bool | None],
    results: list[MetricasAmostra],
) -> str:
    payload = {
        "dataset": [dataset_id, dataset_version],
        "criteria": criteria_version,
        "interpreter": [interpreter, interpreter_version],
        "rules": rules_version,
        "configuration": dict(sorted(configuration.items())),
        "samples": [
            {
                "id": result.amostra_id,
                "categories": [
                    [
                        metric.categoria.value,
                        metric.contagem.verdadeiros_positivos,
                        metric.contagem.falsos_positivos,
                        metric.contagem.falsos_negativos,
                    ]
                    for metric in result.categorias
                ],
                "relations": [
                    result.relacoes.verdadeiros_positivos,
                    result.relacoes.falsos_positivos,
                    result.relacoes.falsos_negativos,
                ],
                "failures": list(result.falhas_extracao),
            }
            for result in results
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode("utf-8")).hexdigest()
