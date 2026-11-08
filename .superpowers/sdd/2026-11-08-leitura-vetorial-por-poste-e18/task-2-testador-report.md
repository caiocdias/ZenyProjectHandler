# Task 2 - Relatório do testador

Status: suíte verde, nenhum defeito achado. Intervalo 8008af0..825fd7a.

## Testes novos (tests/unit/test_release_build.py), 18 casos
- commit_de_origem devolve SHA completo de repo limpo
- recusa arquivo rastreado modificado; recusa mudança só no índice
- repositório sem commits vira ReleaseBuildError
- falha do git no `status` vira ReleaseBuildError
- os dois comandos git rodam com cwd=root (espião)
- fatos com seed inválido (7 variantes parametrizadas: json quebrado, lista, vazio, registro vazio, regras texto/inteiros, regra vazia) -> ReleaseBuildError
- fatos sem arquivo de seed -> ReleaseBuildError
- fatos contam só ativas com 5 regras desabilitadas
- build_release/main com seed inválido reprova antes de _reset_directory/_run (exit 1, sem traceback)
- main com git ausente reprova com mensagem acionável, sem iniciar build
- notas trazem a linha "- Origem: commit `...`"

## Evidência
- Área: 35 passed (`pytest tests/unit/test_release_build.py`).
- Suíte inteira: `.venv/Scripts/python.exe -m pytest -n 6` -> 11148 passed, 5 xfailed in 492.57s.
- ruff check/format limpos. mypy isolado no arquivo reporta import-untyped (ambiente do worktree, mypy rodado fora do gate); não investigado.

## Testes existentes
Nenhum alterado. Observação: o teste de HEAD mutável substitui muitos helpers (acoplado à estrutura de build_release), mas protege o build/release real (ROOT=tmp_path) e o sentinela.
Não rodei build_release real nem Docker.
