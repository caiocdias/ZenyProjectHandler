"""Falhe o gate quando funções ou métodos Python atingirem rank E/F no Radon."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from radon.complexity import cc_rank, cc_visit

_BLOCKING_COMPLEXITY = 31


@dataclass(frozen=True, slots=True)
class ComplexityViolation:
    path: Path
    name: str
    line: int
    complexity: int

    @property
    def rank(self) -> str:
        return cc_rank(self.complexity)


@dataclass(frozen=True, slots=True)
class ComplexityGateResult:
    functions_analyzed: int
    violations: tuple[ComplexityViolation, ...]


def analyze_complexity(roots: Iterable[Path]) -> ComplexityGateResult:
    functions_analyzed = 0
    violations: list[ComplexityViolation] = []
    for path in _python_files(roots):
        blocks = cc_visit(path.read_text(encoding="utf-8"))
        for block in _function_blocks(blocks):
            functions_analyzed += 1
            if block.complexity >= _BLOCKING_COMPLEXITY:
                violations.append(
                    ComplexityViolation(
                        path=path,
                        name=_qualified_name(block),
                        line=block.lineno,
                        complexity=block.complexity,
                    )
                )
    return ComplexityGateResult(
        functions_analyzed=functions_analyzed,
        violations=tuple(violations),
    )


def _python_files(roots: Iterable[Path]) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            paths.add(root)
        elif root.is_dir():
            paths.update(root.rglob("*.py"))
    return tuple(sorted(paths, key=lambda path: str(path).casefold()))


def _function_blocks(blocks: Iterable[Any]) -> Iterator[Any]:
    for block in blocks:
        if hasattr(block, "methods"):
            continue
        yield block
        yield from _function_blocks(getattr(block, "closures", ()))


def _qualified_name(block: Any) -> str:
    classname = getattr(block, "classname", None)
    return f"{classname}.{block.name}" if classname else str(block.name)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bloqueia funções e métodos com complexidade ciclomática rank E/F.",
    )
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        default=(Path("src"),),
        help="Arquivos ou diretórios Python a analisar (padrão: src).",
    )
    return parser


def main(arguments: list[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    result = analyze_complexity(options.roots)
    if result.violations:
        print("GATE DE COMPLEXIDADE E/F: REPROVADO")
        for violation in result.violations:
            print(
                f"{violation.path}:{violation.line}: {violation.rank} "
                f"({violation.complexity}) {violation.name}"
            )
        print(f"Funções e métodos analisados: {result.functions_analyzed}")
        return 1
    print("GATE DE COMPLEXIDADE E/F: APROVADO")
    print(f"Funções e métodos analisados: {result.functions_analyzed}")
    print("Nenhuma função ou método rank E/F encontrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
