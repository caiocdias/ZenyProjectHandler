# E06.3.1 — Pacotes das classes da ficha: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pôr nos pacotes, como `pending`, as 58 variantes do inventário de ESTAI, TRANSFORMADOR, ATERRAMENTO e PARA_RAIOS_MT/BT que estão fora deles. O auditor, a matriz da E16 e o comparador da curadoria passam a aceitar variante de outro `owner_stage`.

**Architecture:** dados e ferramentas de auditoria, sem mudança no reconhecimento: `pending` não gera observação. Os pacotes JSON em `adapters/analysis/symbol_packages/` ganham 4 famílias novas e variantes novas em 3 existentes. O auditor passa a exigir todas as variantes não E10 do inventário, com relato por estágio. A matriz e o comparador da curadoria distinguem o reconhecimento pelo método de pacotes (variante E07) do reconhecimento pelo método do próprio estágio (E04 a E06).

**Tech Stack:** Python 3.11–3.13, JSON, pytest, mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3" (escopo e divisão) e "E06.3.1"; `docs/data/inventario-simbologia-v1.json`; `docs/fluxo-curadoria-incremental-simbologia.md` (matriz e fechamento); o levantamento em `tmp/e06/levantamento-e06.md` do checkout principal (§2, §5).

## Global Constraints

- O inventário `docs/data/inventario-simbologia-v1.json` e a matriz histórica da E16 (`docs/data/matriz-simbologia-e16*`) são congelados: nada aqui os edita.
- Cada variante nova copia do inventário `id`, `class_code`, `destination`, `visual_note` e `source_refs[0]` (como `source_ref`). O `role` deriva de `function`: `informative` se `function` ∈ {`convention`, `non_asset`}, senão `operational`. `recognition` = `{"status": "pending", "reason": ..., "negative_examples": confusable_negatives}`, no formato das `pending` atuais. As variantes que já estão nos pacotes já obedecem a isso, e nada muda nelas.
- O pacote da família nova segue o cabeçalho dos atuais (`schema_version` 1, `family_id` igual ao nome do arquivo, `profile_id` e `source_id` da família no inventário), e a validação de `declarative_symbols.carregar_pacotes` aceita tudo sem mudança no código dela.
- Sem mudança em `declarative_symbols.py`, no núcleo, no runner, na API ou nos DTOs. A assinatura do perfil de pacotes muda porque o sha dos pacotes muda: é esperado (cache miss no runner opt-in).
- Testes sem dependência de ordem, cwd ou arquivo fixo fora do repositório. mypy strict, ruff check e ruff format.
- Nada lê `examples/` nem `examples/avaliacao-cega/`.
- Worktree da etapa: `.venv/Scripts/python.exe`. Em onda, `PYTHONPATH=<worktree da tarefa>/src`, e a suíte inteira usa `-n` = 20 ÷ suítes ativas.

## Review Focus

1. Variante empacotada que diverge do inventário (classe, destino, `source_ref`, papel) → o auditor acusa erro, como já faz para E07 (Task 1).
2. Variante esperada que falta, inclusive de estágio não E07 → `missing variant` (Task 3).
3. As famílias E10 (f02-01, f02-02) continuam fora: nem esperadas nem aceitas se aparecerem, no auditor e na matriz (Tasks 1 e 2).
4. A tabela de suporte da revisão é por família: as 4 famílias novas aparecem como só pendentes, e a ordem continua estável (Task 3).
5. Uma variante E05 com `reconhecido_exato` herdado, agora empacotada como `pending`, passa pelo comparador da curadoria. Uma E07 `pending` com `reconhecido_exato` continua recusada (Task 2).

## Decisões do plano

- **R-E06.3.1-1, o que o auditor exige:** todas as variantes do inventário com `owner_stage` ≠ E10, e não só as E07. Assim, as 58 novas também acusam `missing variant`, e o relato ganha `by_owner_stage` com variantes esperadas, empacotadas, `enabled` e `pending` por estágio. Uma variante E10 empacotada é `unexpected variant`. `complete_recognition` passa a exigir também as variantes E04 a E06 habilitadas. Hoje o valor continua `false` e nada no fluxo o consome. A docstring diz isso.
- **R-E06.3.1-2, "pending não é exato" vale só para o método de pacotes:** 12 das 58 (s18-v017 a v023, s24-v001/002, s25-v001/003/004) já são `reconhecido_exato` na matriz da E16, pela evidência E05 do detector de transformadores. Empacotá-las como `pending` faria `curation_coverage_e16 compare` recusar a próxima matriz (`pending package counted as exact recognition`), que é o motivo de a ampliação ter sido adiada na E06.1 (R9).
  - **Decisão:** o predicado da recusa passa a ser `status == "reconhecido_exato" and package_status == "pending" and owner_stage == "E07"`. Só a variante E07 é reconhecida pelo método de pacotes, então só nela o `pending` contradiz o exato. Variante de outro estágio mantém o status da evidência do próprio estágio. O leitor `read_matrix` já exige `owner_stage`, e nenhuma coluna nova entra.
  - **Alternativas descartadas:** não empacotar as 12 contradiz o escopo. Rebaixar o status delas seria uma perda falsa (`lost_exact_ids`).
  - **Contrato:** é mudança no contrato da curadoria. Só a frase "Nenhum `pending` é reconhecimento" de `docs/fluxo-curadoria-incremental-simbologia.md:44-45` passa a "`pending` do pacote não conta como reconhecimento pelo método de pacotes". A de `:572` continua verdadeira e não muda. Vai para "Decisões para o usuário".
- **R-E06.3.1-3, conjunto de pacotes na matriz:** os pacotes contêm todas as variantes E07, só variantes do inventário e nenhuma E10. A matriz aceita subconjunto das não E07; o auditor, não (R-1). As duas regras ficam escritas no código e nos testes.
- **R-E06.3.1-4, matriz histórica da E16:** é imutável por contrato, e o script já recusa gravá-la. A próxima rodada publica `matriz-simbologia-curadoria-atual*` a partir dela, com os pacotes novos.
- **R-E06.3.1-5, `reason` das variantes novas:** descreve a lacuna técnica, como os atuais, sem citar etapa: `"Forma E01: <visual_note>. Gramática sobre o modelo de desenho ainda não implementada para esta forma; positivo/negativo ainda não validado."`. O mapa classe → subetapa fica no roadmap.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `scripts/audit_symbol_packages.py` | aceita variante não E10 empacotada; relato por estágio; depois exige todas | 1, 3 |
| `tests/unit/test_audit_symbol_packages.py` (novo) | auditor por estágio | 1, 3 |
| `scripts/coverage_matrix_e16.py` | conjunto de pacotes (R-3) e estado do método de pacotes para variante de outro estágio | 2 |
| `scripts/curation_coverage_e16.py` | a recusa de `pending` exato olha o método de pacotes (R-2) | 2 |
| `tests/unit/test_e16_coverage_matrix.py`, `tests/unit/test_curation_coverage_e16.py` | casos novos, sem remover os atuais | 2 |
| `docs/fluxo-curadoria-incremental-simbologia.md` | a frase de R-2 | 2 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-14.json`, `-15`, `-24`, `-25` (novos) e `family-f02-18.json`, `-19`, `-21` | as 58 variantes | 3 |
| `tests/unit/test_declarative_symbol_packages.py`, `tests/server/test_e14_symbol_review.py:287` | contagens | 3 |

Ondas: Tasks 1 e 2 (arquivos disjuntos); Task 3.

Soma: 2h00 (30 + 45 + 45).

## Tasks

### Task 1: Auditor por estágio

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `scripts/audit_symbol_packages.py`
- Create: `tests/unit/test_audit_symbol_packages.py`

**Interfaces:**
- Produces: `audit(...)` devolve também `by_owner_stage: dict[str, {"expected": int, "packaged": int, "enabled": int, "pending": int}]`. Nesta tarefa, `expected` de cada estágio conta as variantes do inventário, mas só as E07 são exigidas (`missing variant`). Variante não E07 e não E10 empacotada passa pelas mesmas checagens de família, perfil, classe, destino, `source_ref` e papel. A saída curta da CLI ganha `by_owner_stage`.

- [ ] **Step 1: Escrever os testes** em `test_audit_symbol_packages.py`, com inventário e pacotes sintéticos em `tmp_path`. Nas fixtures, toda variante não E10 do inventário sintético está empacotada, para nenhuma asserção mudar quando a Task 3 passar a exigir todas:
  - `test_variante_de_outro_estagio_empacotada_e_aceita`;
  - `test_variante_de_outro_estagio_divergente_acusa`: E06 empacotada com classe errada dá `class mismatch`;
  - `test_familia_e10_nao_e_aceita`: E10 empacotada dá `unexpected variant`;
  - `test_relato_por_estagio`.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar** e atualizar a docstring do módulo (R-1).
- [ ] **Step 4: Rodar** o arquivo novo, `tests/unit/test_declarative_symbol_packages.py` e `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`, com os pacotes de hoje), ruff e format.
- [ ] **Step 5: Commit** (`feat: auditor de pacotes aceita outro estagio e relata por estagio`).

### Task 2: Matriz e comparador da curadoria

**Estimativa:** 45 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `scripts/coverage_matrix_e16.py`, `scripts/curation_coverage_e16.py`, `tests/unit/test_e16_coverage_matrix.py`, `tests/unit/test_curation_coverage_e16.py`, `docs/fluxo-curadoria-incremental-simbologia.md`

- [ ] **Step 1: Escrever os testes**, com fixtures em `tmp_path` e sem remover nenhum atual:
  - em `test_e16_coverage_matrix.py`:
    - `test_variante_empacotada_de_outro_estagio`: uma variante E05 empacotada como `pending` mantém o `status` da evidência E05 (relatório ou baseline) e tem `declarative-vector-packages` = `pendente_sem_inferencia` e `package_status` = `pending`;
    - `test_pacotes_sem_alguma_e07_recusa`;
    - `test_pacote_com_variante_fora_do_inventario_recusa`;
    - `test_pacote_com_variante_e10_recusa`;
    - `test_outro_estagio_sem_pacote_continua_aceito`: o caso atual de `:90-177` continua verde.
  - em `test_curation_coverage_e16.py`:
    - `test_e05_exata_com_pacote_pending_e_aceita`;
    - o caso que já existe (E07 `pending` exata recusada) continua verde, com o helper `_matrix` sem mudança nas asserções atuais;
  - ponta a ponta, em `test_curation_coverage_e16.py`: `test_matriz_gerada_com_e05_exata_e_pacote_pending_passa_no_compare`: `coverage_matrix_e16.build(...)` com a E05 exata herdada do baseline e o pacote `pending`, o CSV gravado em `tmp_path`, `read_matrix` e `compare` contra a mesma matriz sem erro.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar** R-2 e R-3 e trocar a frase do fluxo em `:44-45`.
- [ ] **Step 4: Rodar** os dois arquivos, `tests/unit/test_claude_curation_assets.py`, a suíte inteira uma vez, mypy, ruff e format.
- [ ] **Step 5: Commit** (`feat: matriz e comparador da curadoria aceitam pacote pending de outro estagio`).

### Task 3: As 58 variantes nos pacotes

**Estimativa:** 45 min · **Depende de:** Tasks 1 e 2 · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `family-f02-14.json`, `family-f02-15.json`, `family-f02-24.json`, `family-f02-25.json` em `src/zeny_project_handler/adapters/analysis/symbol_packages/`
- Modify: `family-f02-18.json`, `family-f02-19.json`, `family-f02-21.json`; `scripts/audit_symbol_packages.py` (passa a exigir todas as não E10); `tests/unit/test_audit_symbol_packages.py`; `tests/unit/test_declarative_symbol_packages.py`; `tests/server/test_e14_symbol_review.py`

- [ ] **Step 1: Escrever os testes** (vermelhos):
  - em `test_audit_symbol_packages.py`, `test_variante_de_outro_estagio_e_esperada`: E05 do inventário sem pacote dá `missing variant`;
  - em `test_declarative_symbol_packages.py`, cada contagem passa ao valor novo, sem remover checagem:
    - `:88`: o filtro só E07 passa a não E10;
    - `:90`, `:147`, `:148` e `:162`: 365 passa a 423;
    - `:97` e `:309`: 27 pacotes passam a 31;
    - `:113`: `_FAMILY_COUNTS` ganha as famílias novas, e as alteradas mudam de contagem;
    - `:120`: "non-E07 variant" passa a "variante E10 ou fora do inventário";
    - `:366`: 17 famílias só pendentes passam a 21;
    - o comentário de `:41-42` acompanha;
  - em `test_e14_symbol_review.py:287`: 343 passa a 401.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Gerar os pacotes** com um script descartável (fora do Git, em `tmp/`), conforme as Global Constraints e R-5, na ordem das variantes no inventário. As variantes novas vão ao fim do arquivo existente.
- [ ] **Step 4: Exigir todas as não E10** no auditor (R-1).
- [ ] **Step 5: Rodar** os testes de pacotes, auditor e revisão, `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_deliverable_exports.py`, `tests/integration/test_model_symbols_runner.py` e `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`, `expected_variants: 423`, `pending: 401`). Depois, a suíte inteira uma vez, mypy, ruff e format.
- [ ] **Step 6: Commit** (`feat: variantes das classes da ficha nos pacotes como pending`).

## Fechamento operacional

| Critério de aceite | Evidência |
|---|---|
| Auditor com 0 erros, as 58 como `pending` e relato por estágio | Task 3; saída da CLI no handoff |
| Tabela de suporte conta as novas `pending`, testes fixos atualizados | Task 3 |
| `IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` | `cmd.exe //c ".\\IniciarTestes.bat"`, conferindo a data do relatório |

Em "Decisões para o usuário":
- R-2: a mudança no contrato da curadoria;
- a tabela de suporte da revisão e a planilha de capacidade passam a mostrar 4 famílias novas (ESTAI MT/AT, transformador terciário e de medida) e as novas `pending` nas famílias existentes. ESTAI e TRANSFORMADOR aparecem como pendentes no pacote, embora os detectores dedicados do runner opt-in os reconheçam;
- `complete_recognition` do auditor muda de significado (R-1).

Para a E06.3.2 a E06.3.5: a subetapa habilita as variantes da sua classe, já empacotadas, e troca o `reason` e as contagens `enabled`.
