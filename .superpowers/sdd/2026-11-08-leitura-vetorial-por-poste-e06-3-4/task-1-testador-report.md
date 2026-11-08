# Task 1 (E06.3.4, forked_stem): relatorio do testador

Status: suite verde, nenhum defeito encontrado.

## Analise
Diff e2d6d73..HEAD: validador `_forked_stem_grammar_ok`, ramo do schema, `GRAMATICAS_SO_MODELO`, testes do desenvolvedor.
Forma exata, bool/zero/negativo/>72 em max_span (via `_validate_grammar`), ellipse+X e conjuntos ja cobertos pelo desenvolvedor.

## Testes novos (tests/unit/test_gramatica_estai_tipo_ataque.py, 74 casos)
- test_schema_e_validador_concordam (44 variacoes): schema (avaliador estrito) e carregar_pacotes concordam em max_span (0, -0.0, 72, 72.0000001, 96, nan, inf, bool, texto, nulo, lista, dict), enclosure (caixa, espaco, vazio, nulo, bool, int, lista, dict), removal_mark (0/1/1.0/texto/nulo/lista/dict), ellipse+X, campos extra de outros tipos, campos faltando.
- test_enclosure_nao_textual_recusa_sem_type_error (9): lista/dict/tupla/etc. nao explodem em `in`.
- test_max_span_nao_finito_no_json_recusa (3): NaN/Infinity/-Infinity cru no JSON.
- test_kind_de_tipo_errado_recusa_sem_type_error (6).
- test_validadores_e_gramaticas_coerentes; test_schema_e_codigo_listam_os_mesmos_tipos; test_so_modelo_nao_inclui_tipos_do_motor_antigo.
- test_schema_aceita_as_tres_combinacoes_validas (3, controle do avaliador).
- Motor antigo: forked_stem sozinho nao observa nada nem anuncia classe; coexistencia com moldura observa so a moldura.
- Perfil do modelo: anuncia a classe uma vez com 2 variantes; nao anuncia variante pendente.

## Suite
`.venv/Scripts/python.exe -m pytest -n 6` -> 11274 passed, 5 xfailed in 378.46s (xfails pre-existentes de ledger).
ruff check/format limpos no arquivo novo. mypy neste worktree acusa import-untyped (pacote instalado sem py.typed; ambiente, nao o teste).

## Testes existentes suspeitos
Nenhum.
