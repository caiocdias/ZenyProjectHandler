# E14 — Gate de testes paralelo — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a suíte inteira roda em processos paralelos (`pytest-xdist`) no `.bat` e nas souls, sem perder teste nem cobertura; o `main` volta a passar; os scripts de corpus ganham `--processos N`.

**Architecture:** só infraestrutura de teste e scripts de desenvolvimento. O paralelismo entra na invocação (`-n` no `.bat` e no comando documentado), nunca em `addopts`, para que execuções focadas e os pytest-em-subprocesso de `test_dependency_locks.py` continuem seriais. Asserções de tempo de parede viram contagem de trabalho determinística. Os scripts de corpus paralelizam só a medição pura por PDF, com `ProcessPoolExecutor`, e montam a saída na ordem serial.

**Tech Stack:** Python 3.11–3.13, pytest 9.0.3, pytest-cov 7.1.0, pytest-xdist 3.8.0 (MIT) + execnet (MIT), PyMuPDF, Windows (spawn).

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E14 — Gate de testes paralelo"; design `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md` (decisão A1, seção "E14, E15 e E16 em resumo", "Fica para o construtor").

**Laboratório:** nenhuma tarefa (a etapa não usa laboratório).

## Global Constraints

- Nenhum teste removido, pulado, desmarcado ou deixado de fora por marcador ou `deselect`; o total coletado depois da etapa é ≥ 5331 (coletados antes, `pytest --collect-only -q` em 425104a).
- Cobertura mínima 85,01% (`--cov-fail-under=85.01`), com a cobertura combinada dos processos.
- Teste intermitente achado é corrigido, nunca marcado para repetir (sem `pytest-rerunfailures`, sem `flaky`).
- Pytest com `--strict-markers`; `ResourceWarning` e unraisable são erro: feche documentos PyMuPDF, arquivos e pools.
- Sem mudança de comportamento do produto (`src/` não muda). Sem tocar em `scripts/benchmark_ficha_poste.py` (E15) nem nas souls/`.claude/` (D8).
- Dependência nova só no extra `dev` e em `requirements-development.lock`, com licença MIT/BSD/Apache-2.0; nunca nos locks do cliente ou do servidor.
- O gate normal usa só fixtures sintéticas; nenhum teste lê `examples/` nem `examples/avaliacao-cega/`.
- Código, docstrings e mensagens em português.
- Documentação enxuta: atualize só o que a mudança torna falso (`CLAUDE.md`, docstrings de uso dos scripts).
- ADR 0005: continua um só `.bat`, sem partição nem marcador de corpus. O paralelismo é de processos da mesma suíte, não um segundo gate. No `CLAUDE.md`, escreva "suíte em processos paralelos", nunca "gate paralelo".
- `-n`/`--numprocesses` nunca entram em `addopts`: os pytest em subprocesso de `test_dependency_locks.py` copiam o `ini_options` e têm de continuar seriais.

## Review Focus

1. Teste que só falha em processo paralelo → isolar por `tmp_path`/fixture; serial só como último recurso e na passada serial do mesmo `.bat` (Task 2). Riscos já conhecidos:
   - estado global, cwd e Qt offscreen;
   - os pytest em subprocesso de `test_dependency_locks.py:455`, sem `--basetemp`, que usam o `pytest-of-<usuário>` padrão do `%TEMP%`: a limpeza numerada concorrente no Windows pode dar `PermissionError`. Correção preferida: passar `--basetemp=<tmp_path>/interno` ao subprocesso;
   - `test_dependency_locks.py:699-712` grava e apaga `ROOT/build`;
   - o `--basetemp` curto do `.bat` ganha `popen-gwN\` com xdist (caminho mais longo);
   - prazos de espera com `monotonic()` em `tests/server` e `tests/integration` (por exemplo `test_jobs_api.py:252`, `+ 2` s), sob 20 processos (Task 1, Step 4).
2. Cobertura que cai ou deixa de ser exigida com xdist → o `.bat` mantém `--cov-fail-under=85.01`, e a cobertura paralela fica a ≤ 0,2 p.p. da serial: as duas porcentagens são medidas no fechamento, lado a lado no handoff.
3. Exceção dentro de um processo do pool (PDF inválido) → mesma saída da serial: o relatório grava `{"sha256", "erro"}` do PDF ruim e segue. Tabela ausente continua saindo com código 2 antes de abrir o pool (Task 3).
4. Ordem e "primeiro vence" com processos → saída na ordem serial e amostras de imagem gravadas em série no processo principal (Task 3).
5. `--processos` 0, negativo, maior que o número de PDFs ou corpus vazio → 0/negativo sai com código 2; os outros funcionam igual à serial (Task 3).

## File Structure

| Arquivo | Task | Responsabilidade |
|---|---|---|
| `tests/unit/test_glyph_text_orcamento.py` | 1 | teste vermelho: tempo de parede → contagem de trabalho |
| `tests/unit/test_drawing_model_geometry.py`, `test_drawing_model_geometry_adversarial.py`, `test_drawing_model_groups.py`, `test_glyph_text.py`, `test_glyph_text_varredura.py`, `test_pymupdf_drawing_model.py`, `test_pymupdf_drawing_model_adversarial.py`, `test_pymupdf_drawing_model_teto_pixels.py` | 1 | só os que não aguentam a carga paralela (regra na Task 1) |
| arquivos de `tests/server` e `tests/integration` com prazo `monotonic()` (achados por `grep -rlnE "perf_counter\|monotonic" tests`) | 1 | só os prazos que não aguentam a carga paralela (regra na Task 1) |
| `pyproject.toml` (extra `dev`) | 2 | `pytest-xdist>=3.8,<4` |
| `requirements-development.lock` | 2 | `execnet==<última estável>` e `pytest-xdist==3.8.0`, em ordem alfabética |
| `IniciarTestes.bat` | 2 | pytest paralelo com cobertura combinada e `--durations=15`; passada serial só se a Task 2 precisar |
| `tests/unit/test_project_scripts.py` | 2 | o `.bat` exige `-n`, `--cov-fail-under=85.01` e `--durations=15`; xdist no extra e no lock |
| `tests/**` (arquivos que falharem só em paralelo) | 2 | isolamento |
| `CLAUDE.md` (seção "Comandos") | 2, 3 | comando paralelo da suíte; `--processos` dos scripts |
| `scripts/benchmark_texto_ficha.py` | 3 | `--processos N` |
| `scripts/drawing_model_report.py` | 3 | `--processos N` |
| `tests/unit/test_benchmark_texto_ficha_processos.py` (novo) | 3 | igualdade serial × paralela e validação da opção |
| `tests/unit/test_drawing_model_report_processos.py` (novo) | 3 | idem |

Estimativa: Task 1 ≈ 45 min, Task 2 ≈ 75 min, Task 3 ≈ 50 min. A soma é 2h50 de tarefas (ciclo completo de cada uma), abaixo do teto de ~3h, e a etapa não é dividida. Para caber, a Step 7 da Task 2 reaproveita as 3 últimas execuções da Step 5 quando nada mudou depois delas, e a execução serial do fechamento roda em segundo plano durante a revisão final.

---

### Task 1: Asserções de tempo de parede viram contagem de trabalho

**Estimativa:** 45 min. **Laboratório:** não.

**Files:**
- Modify: `tests/unit/test_glyph_text_orcamento.py:133-145`
- Modify (condicional, regra abaixo): os arquivos da File Structure marcados Task 1 (os 8 de `perf_counter` e os prazos `monotonic()` de `tests/server` e `tests/integration`)

**Interfaces:**
- Consumes: `glyph_text.ler_texto_glifos`, `glyph_text.LIMITE_RESOLUCOES_PAGINA`, `glyph_text.LIMITE_GLIFOS_PAGINA`, helper `_contar` do próprio arquivo.
- Produces: nada para as outras tarefas.

Ambiente: para medir a carga paralela antes da Task 2, instale no `.venv` do worktree `pytest-xdist==3.8.0` (`.venv/Scripts/python.exe -m pip install pytest-xdist==3.8.0`). É só o ambiente local; o lock e o manifesto mudam na Task 2. Rode a suíte inteira com `-n auto` quando a soul pedir a suíte inteira.

- [ ] **Step 1: Perfil do teste vermelho.** Rode `python -m cProfile -s cumtime` (ou `pytest --profile` equivalente via script) sobre `test_pagina_hostil_acima_do_teto_de_resolucoes_e_limitada_em_tempo_limitado` e anote as funções de `glyph_text`/`glyph_signature` com ≥ 80% do tempo acumulado. Elas são as que o teste vai contar.
- [ ] **Step 2: Reescreva o teste** como `test_pagina_hostil_acima_do_teto_de_resolucoes_e_limitada_em_trabalho_limitado`: remova `time.perf_counter` e a asserção `< 20.0`; mantenha `leitura == _LIMITADA` e a asserção de resoluções; acrescente, com `monkeypatch` contando como `_contar`, a contagem de cada função dominante do Step 1, com o limite que o código garante por construção (por exemplo `== len(candidatos)` ou `<= LIMITE_RESOLUCOES_PAGINA + _EXCESSO_POR_TRECHO`), escrito como constante ou expressão no teste e justificado num comentário de uma linha. Não mude `src/`.
- [ ] **Step 3: Prove que o teste pega a regressão:** com um `monkeypatch` temporário que desliga o teto (`LIMITE_RESOLUCOES_PAGINA` alto), o teste falha pela contagem; reverta o experimento (não commite).
- [ ] **Step 4: Regra para os demais testes de tempo.** O conjunto é a saída de `grep -rlnE "perf_counter|monotonic" tests --include=*.py`: os 8 outros arquivos de `perf_counter` e os prazos de espera `monotonic() + L` de `tests/server` e `tests/integration`. Rode a suíte inteira 3 vezes com `-n auto --durations=0 -p no:cacheprovider` e grave as durações desses testes. Trate todo teste que:
  - falhou em alguma das 3 execuções; ou
  - tem limite absoluto ou prazo de `L` segundos e durou ≥ `0,5 × L` em alguma execução.

  Como tratar:
  - asserção de tempo de parede → contagem de trabalho (mesma técnica);
  - prazo de espera → espera por evento, ou prazo alargado para ≥ 4 × a duração máxima medida.

  Testes de razão (`melhor(grande) / melhor(pequeno) < 3`) que passaram nas 3 execuções ficam como estão. No relatório, liste cada teste com a duração máxima, o limite e a decisão.
- [ ] **Step 5: Verifique.** `.venv/Scripts/python.exe -m pytest tests/unit/test_glyph_text_orcamento.py -v` → PASS; suíte inteira `-n auto` → verde; `ruff check`, `ruff format --check`, `mypy` → limpos.
- [ ] **Step 6: Commit** `test(analise): teto de resolucoes medido por contagem de trabalho` com o trailer `Soul: desenvolvedor`.

---

### Task 2: Suíte paralela no gate

**Estimativa:** 75 min. **Laboratório:** não.

**Files:**
- Modify: `pyproject.toml` (extra `dev`), `requirements-development.lock`, `IniciarTestes.bat:55-58` (linha `Comando:` e a invocação do pytest), `tests/unit/test_project_scripts.py` (novo teste junto de `test_quality_script_enforces_the_relevant_quality_gates`, l.152-170), `CLAUDE.md` (seção "Comandos")
- Modify (condicional): testes que falharem só em paralelo

**Interfaces:**
- Consumes: Task 1 (suíte verde).
- Produces: comando da suíte paralela `python -m pytest -n <N> --cov` documentado no `CLAUDE.md`, que as souls passam a usar.

- [ ] **Step 1: Teste do `.bat` primeiro.** Em `test_project_scripts.py`, novo teste `test_quality_script_runs_pytest_in_parallel_with_combined_coverage`:
  ```python
  quality_script = script_text("IniciarTestes.bat")
  assert re.search(r"python -m pytest -n (auto|\d+)\b", quality_script)
  assert "--cov-fail-under=85.01" in quality_script
  assert "--durations=15" in quality_script
  configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
  addopts = configuration["tool"]["pytest"]["ini_options"]["addopts"].split()
  assert not any(a == "-n" or a.startswith(("-n", "--numprocesses", "--dist")) for a in addopts)
  ```
  e `test_xdist_is_a_dev_dependency_pinned_in_the_development_lock`: `pytest-xdist` aparece no extra `dev` do `pyproject.toml` com limite `>=3.8,<4` e `pytest-xdist==3.8.0` e `execnet==` aparecem em `requirements-development.lock`, e nenhum dos dois aparece em `requirements-client.lock` nem em `requirements-server.lock`. Rode → FAIL.
- [ ] **Step 2: Dependência.** `pytest-xdist>=3.8,<4` no extra `dev`; `execnet==<última estável no PyPI>` e `pytest-xdist==3.8.0` no lock de desenvolvimento, em ordem alfabética; instale pelo lock (`pip install -r requirements-development.lock`) e rode `pip check`.
- [ ] **Step 3: Número de processos.** Meça o passo pytest completo (`--basetemp` curto, `--cov --cov-report=term-missing --cov-fail-under=85.01`) com `-n auto`, `-n 10` e `-n 16`. Fique com `auto`, a menos que um N fixo seja ≥ 15% mais rápido; registre os três tempos e a cobertura de cada um no relatório. Distribuição: padrão do xdist (`load`), a menos que a medição mostre outra ≥ 15% melhor.
- [ ] **Step 4: `.bat`.** Troque a invocação para `python -m pytest -n <N> --basetemp="!PYTEST_BASETEMP!" --cov --cov-report=term-missing --cov-fail-under=85.01 --durations=15` e a linha `Comando:` do cabeçalho da seção. Não mexa no resto do `.bat`.
- [ ] **Step 5: Isolamento.** Rode a suíte paralela inteira 3 vezes seguidas. Todo teste que falhar só em paralelo (passa em `pytest <arquivo>::<teste>` serial) é corrigido pela causa (estado global, arquivo fixo, cwd, porta fixa) com `tmp_path`/fixtures. Se algum não puder ser isolado, registre o marcador `serial` em `[tool.pytest.ini_options].markers`, marque só esse teste e faça o `.bat` rodar duas passadas: `-n <N> -m "not serial" --cov ... --cov-fail-under=0` e `-m serial --cov --cov-append --cov-fail-under=85.01`, com o código de saída das duas somado ao `SUITE_STATUS`; acrescente ao teste do Step 1 a asserção das duas passadas. Explique no relatório cada caso.
- [ ] **Step 6: `CLAUDE.md`.** Na seção "Comandos": o gate completo roda a suíte em paralelo; acrescente a linha `.\.venv\Scripts\python.exe -m pytest -n <N> --cov   # suíte inteira em paralelo (pytest-xdist); use antes de commit e no fim da tarefa` e diga que execuções focadas (`arquivo::teste`) continuam seriais e que `-n 0` força a suíte serial. Atualize a linha da cobertura se ela citar só a forma serial.
- [ ] **Step 7: Verifique.** Os dois testes novos → PASS; 3 suítes paralelas seguidas verdes, com o total de testes de cada uma ≥ 5331 passed+xfailed e cobertura ≥ 85,01% (reaproveite as 3 últimas da Step 5 se nada mudou depois delas); `ruff`, `format`, `mypy`, `pip check` limpos.
- [ ] **Step 8: Commit** `build(testes): suite paralela com pytest-xdist no gate` com o trailer `Soul: desenvolvedor`.

---

### Task 3: `--processos N` nos scripts de corpus

**Estimativa:** 50 min. **Laboratório:** não.

**Files:**
- Modify: `scripts/benchmark_texto_ficha.py` (`executar`, `main`, docstring), `scripts/drawing_model_report.py` (`_argumentos`, `main`, docstring), `CLAUDE.md` (linha do `drawing_model_report`)
- Create: `tests/unit/test_benchmark_texto_ficha_processos.py`, `tests/unit/test_drawing_model_report_processos.py`

**Interfaces:**
- Consumes: nada das outras tarefas.
- Produces:
  - `benchmark_texto_ficha.executar(rodada: Path, pdfs: Path, saida: Path, tabela_arquivo: Path | None, processos: int = 1) -> dict[str, Any]`;
  - `benchmark_texto_ficha.main` e `drawing_model_report.main` aceitam `--processos N` (inteiro ≥ 1, padrão 1).

Desenho (o que o implementador não pode decidir sozinho):
- **Pool:** `concurrent.futures.ProcessPoolExecutor(max_workers=min(processos, n_itens))`, aberto num `with`, só quando `processos > 1` e houver mais de um item. Com `processos == 1`, o caminho é o serial atual, sem pool. As funções de trabalho ficam no nível do módulo (spawn no Windows) e recebem só `Path` e dados JSON-serializáveis.
- **Tabela de glifos:** o processo principal continua carregando e validando a tabela antes de medir, com o mesmo comportamento de hoje. No `drawing_model_report`, tabela ausente ou inválida → código 2. Cada processo do pool carrega a tabela uma vez, no `initializer` do pool (`carregar_tabela_glifos(tabela_arquivo)` / `carregar_tabela_glifos()`, guardada numa global do módulo), fora do `try` da medição por PDF.
- **Ordem:** os resultados são montados na ordem da entrada serial (`pool.map`), nunca na ordem de término.
- **`benchmark_texto_ficha`:** resolve todos os PDFs pelas referências antes de abrir o pool; referência sem PDF levanta o mesmo `ValueError` de hoje, sem medir nada. O trabalho paralelo é `_medir_pdf` por referência.
- **`drawing_model_report`:** só `medir_pdf` vai para o pool, embrulhado numa função de módulo que devolve `{"sha256", "erro": type(erro).__name__}` quando a medição levanta, como hoje. A gravação das amostras (`gravar_amostras`) e o dicionário `fontes` continuam em série, no processo principal, na ordem ordenada dos PDFs, para manter o "primeiro PDF vence".
- **Medidas do processo:** os campos `tempo_*` e `pico_memoria_bytes` (`drawing_model_report.py:223-256`, pico do `tracemalloc` por processo) medem a execução, não a leitura. Com `--processos > 1`, os tempos incluem a disputa por CPU, e o pico depende da partida a frio de cada processo do pool. A docstring diz isso. A saída não registra o número de processos.
- **Validação:** `--processos` < 1 → `parser.error` (código 2), com mensagem `--processos precisa ser >= 1`.

- [ ] **Step 1: Testes que falham.** Em cada arquivo novo, uma fixture com ≥ 5 folhas sintéticas de PDF (gere com os helpers já usados em `test_benchmark_texto_ficha.py` e `test_drawing_model_report.py`; no `drawing_model_report`, inclua uma folha com texto em contorno, uma com imagem que gera amostra repetida em duas folhas e um arquivo `.pdf` inválido). Testes:
  - `test_processos_4_produz_a_mesma_saida_que_a_serial`: roda `main([... ])` serial e `main([..., "--processos", "4"])` em saídas distintas sob `tmp_path` e compara os arquivos byte a byte depois de `_sem_medidas_do_processo`, função do teste que troca por `0` o valor de toda chave JSON `tempo_*` e `pico_memoria_bytes` (regex `("(?:tempo_[a-z_]*s|pico_memoria_bytes)": )[0-9.]+`) e, no `texto-ficha.md`, as linhas que começam por `Tempo de análise:`. Antes de normalizar, o teste confere que as chaves existem, para a normalização não passar em branco:
    - no benchmark: `tempo_analise_com_glifos_s`, `tempo_analise_sem_glifos_s`, `tempo_glifos_s` e a linha `Tempo de análise:`;
    - no report: `tempo_s` e `pico_memoria_bytes` em cada PDF medido (a entrada do PDF inválido não as tem). No `drawing_model_report`, compare também os nomes e os bytes dos PNG de `--amostras-imagem`.
  - `test_processos_maior_que_o_numero_de_pdfs_funciona` (`--processos 16`) e `test_corpus_vazio_com_processos` (relatório vazio igual ao serial).
  - `test_processos_invalido_sai_com_2` parametrizado com `0` e `-1`.
  - no `drawing_model_report`: `test_pdf_invalido_no_pool_vira_erro_no_relatorio` (a entrada do inválido é `{"sha256", "erro"}` e as outras são medidas).
  Rode → FAIL (opção desconhecida).
- [ ] **Step 2: Implemente** conforme o desenho acima, nos dois scripts, sem mudar a saída serial (os testes atuais dos dois scripts seguem verdes sem alteração).
- [ ] **Step 3: Docstrings e `CLAUDE.md`:** uso com `[--processos N]` e o aviso dos tempos; acrescente ` --processos 4` como opcional na linha do `drawing_model_report` no `CLAUDE.md`.
- [ ] **Step 4: Verifique.** Os testes novos e os de `test_benchmark_texto_ficha*.py` e `test_drawing_model_report*.py` → PASS; suíte inteira paralela verde; `ruff`, `format`, `mypy`, `complexity_gate` limpos; nenhum `ResourceWarning`.
- [ ] **Step 5: Commit** `feat(scripts): --processos nos scripts de corpus` com o trailer `Soul: desenvolvedor`.

---

## Fechamento da etapa (orquestrador)

- **Gate (critério 2):** o `.bat` é o que a etapa muda, por isso o espelho não basta.
  - O `.bat` real roda no worktree (`cmd.exe //c IniciarTestes.bat`) antes do `#concluida`. Quem roda é o orquestrador; se o harness recusar `cmd.exe` na sessão isolada, ele sai do modo worktree (`ExitWorktree`, mantendo o worktree) e roda o `.bat` pelo caminho absoluto do worktree. O `relatorio-testes.txt` vai para a revisão final. Depois do `.bat`, o orquestrador volta ao worktree (`EnterWorktree` com o caminho) antes de qualquer edição ou commit, ou usa só `git -C <worktree>`. Ele confere que `git -C <worktree> branch --show-current` dá `roadmap/leitura-vetorial-por-poste`.
  - Se nenhum caminho rodar o `.bat` real: o critério 2 vai para "Decisões para o usuário" como "verificado só pelo espelho", com o `.bat` real como condição do merge. O espelho `.superpowers/sdd/gate.sh` é atualizado para a invocação nova, e a revisão final compara linha a linha a seção pytest do `.bat` com a do espelho.
- **Critério 1:** o conjunto de node IDs de `pytest --collect-only -q` em 425104a (gravado no workspace antes da Task 1) ⊆ o conjunto depois, com o renomeado da Task 1 mapeado. Com duas passadas no `.bat`, conta a união das duas.
- **Critério 3:** tempo do passo pytest antes (1578 s, `relatorio-testes.txt` de 2026-11-04) e depois, e as 15 durações mais lentas, no handoff.
- **Critério 4:** 3 suítes paralelas seguidas e 1 serial (`-n 0 --cov --cov-report=term-missing`), todas verdes, com as saídas na revisão final. A cobertura paralela e a serial vão lado a lado no handoff.
- **Critério 6:** `pip check` e `osv-scanner` no `requirements-development.lock`.

## Revisão de arquitetura

- **Veredito:** aprovado com notas.
- **Rodadas:** 1 (rodada 0 bloqueada por I1 — `.bat` real só pelo espelho — e I2 — `pico_memoria_bytes` na igualdade; ambos corrigidos, com M1–M9).
- **Modelo:** opus (`revisor-arquitetura`).
- **Notas Menores da rodada 1, aplicadas antes da Task 1:**
  - N1: as estimativas dos cabeçalhos e o bloco "Files" da Task 1 igualados à File Structure;
  - N2: as chaves exigidas por script na normalização da Task 3;
  - N3: a volta ao worktree e a conferência da branch depois do `.bat` real.
- **Não verificado pelo revisor (sem Bash):** a compatibilidade pytest-xdist 3.8.0 × pytest 9.0.3 × pytest-cov 7.1.0 e a versão do execnet (ficam com `pip check` e `osv-scanner`); a existência do `ExitWorktree` (confirmada pelo orquestrador: ferramenta da sessão).
