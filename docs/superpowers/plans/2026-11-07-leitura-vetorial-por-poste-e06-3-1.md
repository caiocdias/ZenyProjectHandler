# E06.3.1 — Pacotes das classes da ficha: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** pôr nos pacotes, como `pending`, as 58 variantes do inventário de ESTAI, TRANSFORMADOR, ATERRAMENTO e PARA_RAIOS_MT/BT que estão fora deles, com o auditor e a matriz da E16 aceitando variante de outro `owner_stage`.

**Architecture:** só dados e ferramentas de auditoria. Os pacotes JSON em `adapters/analysis/symbol_packages/` ganham 4 famílias novas e variantes novas em 3 existentes. O auditor passa a exigir todas as variantes não E10 do inventário, com relato por estágio. A matriz marca a variante empacotada de outro estágio como `pendente_sem_inferencia` no método de pacotes. Nada é reconhecido de novo: `pending` não gera observação.

**Tech Stack:** Python 3.11–3.13, JSON, pytest, mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3" (escopo e divisão) e "E06.3.1"; `docs/data/inventario-simbologia-v1.json`; o levantamento em `tmp/e06/levantamento-e06.md` do checkout principal (§2, §5).

## Global Constraints

- O inventário `docs/data/inventario-simbologia-v1.json` é congelado: nada aqui o edita.
- Cada variante nova copia do inventário `id`, `class_code`, `destination`, `visual_note` e `source_refs[0]` (como `source_ref`). O `role` deriva de `function`: `informative` se `function` ∈ {`convention`, `non_asset`}, senão `operational`. O mesmo vale para as variantes que já existem. `recognition` = `{"status": "pending", "reason": ..., "negative_examples": confusable_negatives}`, no formato das `pending` atuais.
- O pacote da família nova segue o cabeçalho dos atuais (`schema_version` 1, `family_id` igual ao nome do arquivo, `profile_id` e `source_id` da família no inventário), e a validação de `declarative_symbols.carregar_pacotes` aceita tudo sem mudança no código dela.
- Sem mudança em `declarative_symbols.py`, no núcleo, no runner, na API ou nos DTOs. A assinatura do perfil de pacotes muda porque o sha dos pacotes muda: é esperado (cache miss no runner opt-in).
- A matriz publicada (`docs/data/matriz-simbologia-e16*`) não é regenerada.
- Testes sem dependência de ordem, cwd ou arquivo fixo fora do repositório. mypy strict, ruff check e ruff format.
- Nada lê `examples/` nem `examples/avaliacao-cega/`.
- Worktree da etapa: `.venv/Scripts/python.exe`.

## Review Focus

1. Variante empacotada que diverge do inventário (classe, destino, `source_ref`, papel) → o auditor acusa erro, como já faz para E07 (Task 1).
2. Variante esperada que falta, inclusive de estágio não E07 → `missing variant` (Task 1).
3. As famílias E10 (f02-01, f02-02) continuam fora: nem esperadas, nem aceitas se aparecerem (Task 1).
4. Tabela de suporte da revisão: as classes novas (ESTAI, TRANSFORMADOR, ...) aparecem com as `pending` novas, e a ordem continua estável (Task 2).
5. Matriz: variante E04, E05 ou E06 empacotada mantém o status da evidência do próprio estágio e só ganha `pendente_sem_inferencia` no método de pacotes (Task 2).

## Decisões do plano

- **R-E06.3.1-1, o que o auditor exige:** todas as variantes do inventário com `owner_stage` ≠ E10, e não só as E07. Assim, as 58 novas também acusam `missing variant`, e o relato ganha `by_owner_stage` com variantes, `enabled` e `pending` por estágio. Uma variante E10 empacotada é `unexpected variant`.
- **R-E06.3.1-2, matriz publicada:** não é regenerada aqui. Ela é artefato da curadoria e exige relatórios novos das E05, E06 e E07; a coluna `package_status` das 58 fica defasada até a próxima rodada. O script passa a aceitar a variante empacotada de outro estágio, e um teste com fixture prova isso.
- **R-E06.3.1-3, `reason` das variantes novas:** `"Forma E01: <visual_note>. Gramática sobre o modelo de desenho planejada na <subetapa> (E06.3); positivo/negativo ainda não validado."`, com `<subetapa>` por classe: ATERRAMENTO e PARA_RAIOS_MT → E06.3.2; PARA_RAIOS_BT e TRANSFORMADOR (e o CONJUNTO_EO da f02-25) → E06.3.3; ESTAI → E06.3.4.
- **R-E06.3.1-4, 7 arquivos JSON numa tarefa:** acima do limite de 3 arquivos de produção, mas são dados gerados mecanicamente do inventário. Dividir exigiria deixar o auditor vermelho entre tarefas. O gerador é descartável e não entra no Git.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-14.json`, `-15`, `-24`, `-25` (novos) | famílias ESTAI MT/AT, transformador terciário e de medida | 1 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-18.json`, `-19`, `-21` | variantes novas (transformador; aterramento; para-raios MT/BT) | 1 |
| `scripts/audit_symbol_packages.py` | universo esperado e relato por estágio | 1 |
| `tests/unit/test_declarative_symbol_packages.py` | contagens e paridade com o inventário | 1 |
| `tests/unit/test_audit_symbol_packages.py` (novo) | auditor por estágio | 1 |
| `scripts/coverage_matrix_e16.py` | estado do método de pacotes para variante de outro estágio | 2 |
| `tests/unit/test_e16_coverage_matrix.py` | caso da variante empacotada de outro estágio | 2 |
| `tests/server/test_e14_symbol_review.py:287` | total de `pending` na tabela de suporte | 2 |

Ondas: Task 1; Task 2.

Soma: 75 min.

## Tasks

### Task 1: Pacotes e auditor

**Estimativa:** 45 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `family-f02-14.json`, `family-f02-15.json`, `family-f02-24.json`, `family-f02-25.json` em `src/zeny_project_handler/adapters/analysis/symbol_packages/`; `tests/unit/test_audit_symbol_packages.py`
- Modify: `family-f02-18.json`, `family-f02-19.json`, `family-f02-21.json`; `scripts/audit_symbol_packages.py`; `tests/unit/test_declarative_symbol_packages.py`

**Interfaces:**
- Produces: `audit(...)` devolve, além do que já devolve, `by_owner_stage: dict[str, {"expected": int, "packaged": int, "enabled": int, "pending": int}]`. `expected_variants` passa a 423 e `package_families` a 31. A saída curta da CLI ganha `by_owner_stage`.

- [ ] **Step 1: Escrever os testes** (vermelhos):
  - em `test_audit_symbol_packages.py`, com inventário e pacotes sintéticos em `tmp_path`:
    - `test_variante_de_outro_estagio_e_esperada`: variante E05 do inventário sem pacote dá `missing variant`;
    - `test_variante_de_outro_estagio_divergente_acusa`: E06 empacotada com classe errada dá `class mismatch`;
    - `test_familia_e10_nao_e_esperada_nem_aceita`: E10 ausente não acusa; E10 empacotada dá `unexpected variant`;
    - `test_relato_por_estagio`: `by_owner_stage` conta esperadas, empacotadas, `enabled` e `pending`;
  - em `test_declarative_symbol_packages.py`: as contagens passam a 423 variantes e 31 famílias, com as contagens por família novas, e a checagem "E07 package contains non-E07 variant" passa a aceitar qualquer estágio do inventário menos E10. Nenhuma checagem é removida: cada contagem muda para o valor novo.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Gerar os pacotes** com um script descartável (fora do Git, em `tmp/`), aplicando as Global Constraints e R-E06.3.1-3, na ordem das variantes no inventário. As variantes novas vão ao fim do arquivo existente; o que já existe não muda.
- [ ] **Step 4: Ajustar o auditor** (R-E06.3.1-1).
- [ ] **Step 5: Rodar** os dois arquivos de teste, `tests/unit/test_declarative_symbols*.py`, `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/integration/test_model_symbols_runner.py` e `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`, `expected_variants: 423`). Depois, a suíte inteira uma vez, mypy, ruff e format.
- [ ] **Step 6: Commit** (`feat: variantes das classes da ficha nos pacotes como pending`).

### Task 2: Matriz da E16 e tabela de suporte

**Estimativa:** 30 min · **Depende de:** Task 1 · **Risco:** normal · **Laboratório:** não

**Files:**
- Modify: `scripts/coverage_matrix_e16.py`, `tests/unit/test_e16_coverage_matrix.py`, `tests/server/test_e14_symbol_review.py`

**Interfaces:**
- Consumes: os pacotes da Task 1.

- [ ] **Step 1: Escrever os testes:**
  - em `test_e16_coverage_matrix.py`, `test_variante_empacotada_de_outro_estagio`: com fixtures em `tmp_path`, uma variante E05 empacotada como `pending` mantém o `status` da evidência E05 (relatório ou baseline) e tem `declarative-vector-packages` = `pendente_sem_inferencia` e `package_status` = `pending`;
  - em `test_e14_symbol_review.py:287`, o total de `pending` passa ao valor medido com os pacotes da Task 1 (343 + 58 = 401, se nenhuma das 58 cair fora da tabela; confira e use o valor real).
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar** em `_method_states`: variante de outro estágio com pacote ganha o estado do método de pacotes pelo `recognition.status` do pacote, como já acontece em E07. O resto não muda.
- [ ] **Step 4: Rodar** `tests/unit/test_e16_coverage_matrix.py`, `tests/server/test_e14_symbol_review.py`, `tests/unit/test_deliverable_exports.py`, ruff e format. Expected: PASS.
- [ ] **Step 5: Commit** (`feat: matriz e16 reconhece variante empacotada de outro estagio`).

## Fechamento operacional

| Critério de aceite | Evidência |
|---|---|
| Auditor com 0 erros, as 58 como `pending` e relato por estágio | Task 1; saída da CLI no handoff |
| Tabela de suporte conta as novas `pending`, testes fixos atualizados | Task 2 |
| `IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` | `cmd.exe //c ".\\IniciarTestes.bat"`, conferindo a data do relatório |

Em "Decisões para o usuário": as 58 `pending` passam a aparecer na tabela de suporte da revisão e nas exportações (a classe aparece com referências pendentes, sem reconhecimento), e a matriz publicada fica defasada na coluna `package_status` até a próxima rodada de curadoria.

Para a E06.3.2 a E06.3.5: a subetapa habilita as variantes da sua classe (já empacotadas) e atualiza o `reason` e as contagens `enabled`.
