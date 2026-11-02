# E01 — Limpeza do projeto Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remover do repositório os scripts, testes, fixtures e documentos de etapas encerradas, sem mudar o comportamento do produto, deixando o gate verde.

**Architecture:** Só remoções e ajustes de referência. Nenhum arquivo de `src/` muda. Testes que exercitam código de `src/` por meio de um módulo removido são mantidos e reapontados para o módulo de `src/`; testes que só exercitam código removido saem com ele.

**Tech Stack:** Python 3.11 (venv `.venv` do worktree), pytest, ruff, mypy.

**Spec:** seção "E01 — Limpeza do projeto" de `docs/roadmap-leitura-vetorial-por-poste.md` e §"Escopo da F0" de `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md`.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o cliente não importa nada do servidor (`client_artifact_gate`); DTOs seguem `tests/contracts/test_architecture.py`.
- Código de `src/` e ADRs estão fora do escopo desta etapa: não editar.
- PDFs reais, recortes, rótulos, conjuntos de dados e pesos treinados nunca entram no Git.
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro.
- Documentação enxuta: nada de histórico de execução em arquivo versionado. Atualize só o que a mudança torna falso (`CLAUDE.md`, contrato de curadoria, especificação funcional).
- Fora de escopo (não remover): `benchmark_symbols`, `benchmark_network_pdf`, `symbol_benchmark_*`, `benchmark_transformers_e05`, `benchmark_guys_e06`, `benchmark_packages_e07`, `benchmark_review_e14`, `benchmark_semantic_e13`, `reconcile_symbol_benchmark`, `curation_coverage_e16`, `coverage_matrix_e16`, `audit_symbol_packages`, todos os `curation_*`, `build_release`, `build_client`, `release_artifact_gate`, `server_artifact_gate`, `client_artifact_gate`, `complexity_gate`, `generate_openapi_v1`, `smoke_examples`, `run_development_client`.
- Commits com o trailer `Soul: <soul>` pedido no despacho.

## Ambiente de execução (vale para todas as tarefas)

O harness desta sessão recusa `cmd.exe`, portanto `IniciarTestes.bat` não roda. O gate equivalente é a sequência abaixo, a partir da raiz do worktree, com `PYTHONUTF8=1` e `QT_QPA_PLATFORM=offscreen`; aprovado = todos com exit 0:

```bash
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe scripts/client_artifact_gate.py --source-only
.venv/Scripts/python.exe -m pytest --basetemp=/c/tmp/zph-<algo-unico> --cov --cov-report=term --cov-fail-under=85.01
.venv/Scripts/python.exe scripts/complexity_gate.py src
```

A suíte completa leva ~10 min (baseline: 2611 passed, cobertura 88,24%). Rode-a em background quando a ferramenta tiver timeout menor. A cobertura mede só pacotes de `src/` (`[tool.coverage.run] source` no `pyproject.toml`), então remover testes de scripts só baixa a cobertura se esses testes cobriam `src/`.

## Rulings de planejamento (registradas no ledger)

- **R1 — critério de grep.** "Referência fora do histórico de revisões deste roadmap" é lido como: fora de `docs/roadmap-leitura-vetorial-por-poste.md`, de `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` e de `docs/superpowers/plans/` (documentos de planejamento que descrevem a própria remoção).
- **R2 — `requirements-experiments.lock`.** `scripts/experiments/` só importa stdlib, PyMuPDF, Pillow e módulos do projeto; todos os pacotes fixados no lock servem ao OCR complementar opt-in do servidor (`src/zeny_project_handler/adapters/analysis/rapid_ocr.py`, `rapidocr_onnxruntime` + `numpy`) ou já são dependências do servidor. Nenhuma entrada é usada só pelos experimentos: as entradas ficam; só os comentários do cabeçalho que citam os experimentos E11/E12A são reescritos.
- **R3 — `stage1N` e `visual_qa_review_highlights`.** Nenhum gate vivo os importa: `build_release.py` chama só `release_artifact_gate.py`; `stage12_release_gate` só é citado como texto em `tests/unit/test_project_scripts.py`. Saem. `pywinauto` fica no `pyproject.toml`/`requirements-development.lock` (fora do escopo desta etapa), anotado no handoff como sem uso.
- **R4 — fixtures de reserva.** `tests/fixtures/symbols/e16r2/` inteiro só serve a `benchmark_reserve_e16r2` e sai. `tests/fixtures/symbols/reserve.sealed.zip` fica: é citado por `tests/fixtures/symbols/manifest.json`, usado pelo benchmark vivo.
- **R5 — `.claude/settings.json`.** A allow-list não cita nada removido (conferido): sem mudança.

## Review Focus

- Teste que exercita `src/` por meio de módulo removido (`scripts/experiments/rapid_ocr.py` reexporta `RapidLocalOcr` e `map_quad` de `src`): apagá-lo sem reapontar perde cobertura e proteção de comportamento vivo — a Task 1 reaponta.
- Import transitivo escondido: um script vivo ou teste que importa um módulo removido só aparece na coleta do pytest ou no mypy; o gate completo depois de cada tarefa pega.
- Queda de cobertura abaixo de 85,01% por remoção de testes que também cobriam `src/` (`interpret_rapid`/`topology_audit` chamam código de `src/`): conferir o TOTAL da suíte no fim de cada tarefa.
- Documento vivo afirmando algo que deixou de ser verdade (README descrevendo a validação de distribuição em host temporário, CLAUDE.md citando `scripts/experiments/`): Task 3.
- Remoção de algo usado pela skill de curadoria ou por `build_release`: a lista "Fora de escopo" acima é fechada; o gate e o grep final pegam.

---

### Task 1: Remover `scripts/experiments/` e os benchmarks que dependem dele

**Files:**
- Delete: `scripts/experiments/` (diretório inteiro), `scripts/benchmark_method_reconciliation.py`, `scripts/benchmark_network_alternatives.py`, `tests/unit/test_e11_experiment.py`, `tests/unit/test_network_alternatives.py`
- Create: `tests/unit/test_rapid_ocr.py`
- Modify: `tests/unit/test_e13_occurrences.py` (remove o import de `scripts.experiments.compare` e `test_context_comparison_requires_matching_source`)
- Modify: `tests/unit/test_e14_topology.py` (remove o import de `scripts.experiments.topology_audit` e `test_topology_evaluator_requires_explicit_continuity_and_unsplit_identity`)
- Modify: `requirements-experiments.lock` (só o cabeçalho de comentários, ver R2)

**Interfaces:**
- Consumes: `zeny_project_handler.adapters.analysis.rapid_ocr.RapidLocalOcr` e `map_quad` (existentes, não mudam).
- Produces: nada que outras tarefas usem.

- [ ] **Step 1: Mover os dois testes que cobrem `src/`.** Copie para `tests/unit/test_rapid_ocr.py` `test_coordinate_mapping_uses_pixel_origin_and_keeps_polygon` e `test_ocr_rejects_invalid_memory_before_calling_optional_engine` de `tests/unit/test_network_alternatives.py`, importando `RapidLocalOcr` e `map_quad` de `zeny_project_handler.adapters.analysis.rapid_ocr` (e o que mais esses dois testes usarem, ex.: `PaginaRasterOcr`). As asserções sobre `map_quad` e `RapidLocalOcr` são copiadas sem mudança; as asserções sobre `segment_distance` (de `scripts.experiments.global_graph`, removido nesta tarefa) **saem**, porque testam código de experimento. Nada é movido para `src/`.
- [ ] **Step 2: Rodar o arquivo novo.** `.venv/Scripts/python.exe -m pytest tests/unit/test_rapid_ocr.py -v` → 2 passed.
- [ ] **Step 3: Apagar** os arquivos listados em Delete e remover dos dois testes mistos o import e o teste citados em Modify, mais todo import que ficar sem uso por causa disso (ex.: `from scripts.benchmark_network_pdf import json_value` em `test_e13_occurrences.py`, usado só pelo teste removido). O resto desses arquivos fica intacto.
- [ ] **Step 4: Reescrever o cabeçalho do `requirements-experiments.lock`.** Entradas fixadas inalteradas. Os comentários passam a dizer que é o lock opt-in de dependências fora do runtime padrão (nunca incluído nos requisitos padrão de cliente/servidor/release) e que hoje serve ao OCR complementar do servidor (`ZENY_SERVER_COMPLEMENTARY_OCR`), sem citar E11/E12A nem pesos em `tmp/`.
- [ ] **Step 5: Conferir que nada vivo importa o que saiu.** Grep por `scripts.experiments`, `scripts/experiments`, `benchmark_method_reconciliation`, `benchmark_network_alternatives` em `*.py`, `*.toml`, `*.lock`, `*.json`, `*.bat` → sem resultado.
- [ ] **Step 6: Gate completo** (seção "Ambiente de execução") → todos exit 0; anote no relatório o número de testes e o TOTAL de cobertura.
- [ ] **Step 7: Commit** `chore: remove experimentos encerrados e benchmarks dependentes`.

### Task 2: Remover harnesses de reserva, gates de estágio e o script de QA visual

**Files:**
- Delete: `scripts/benchmark_reserve_e16.py`, `scripts/benchmark_reserve_e16r2.py`, `tests/unit/test_e16_reserve_gate.py`, `tests/unit/test_e16r2_reserve_gate.py`, `tests/fixtures/symbols/e16r2/` (diretório inteiro), `scripts/stage10_operational_gate.py`, `scripts/stage11_client_matrix.py`, `scripts/stage11_parity_gate.py`, `scripts/stage12_release_gate.py`, `scripts/visual_qa_review_highlights.py`
- Modify: `tests/unit/test_project_scripts.py` (`test_sql_server_driver_provenance_is_pinned_and_documented`: remover a leitura de `scripts/stage12_release_gate.py` e a asserção `'"--pyinstaller-python"' in distribution_gate`; as demais asserções ficam)

**Interfaces:** nenhuma.

- [ ] **Step 1: Apagar** os arquivos e diretórios listados em Delete. Não apagar `tests/fixtures/symbols/reserve.sealed.zip` nem `tests/integration/test_stage10_cutover.py` (testa o cutover do servidor em `src/`).
- [ ] **Step 2: Ajustar `test_project_scripts.py`** conforme Modify.
- [ ] **Step 3: Rodar** `.venv/Scripts/python.exe -m pytest tests/unit/test_project_scripts.py -v` → todos passam.
- [ ] **Step 4: Conferir** por grep em `*.py`, `*.toml`, `*.lock`, `*.json`, `*.bat` que nenhum dos nomes removidos (`benchmark_reserve_e16`, `stage10_operational_gate`, `stage11_client_matrix`, `stage11_parity_gate`, `stage12_release_gate`, `visual_qa_review_highlights`, `fixtures/symbols/e16r2`, `sealed_access`) aparece.
- [ ] **Step 5: Gate completo** → todos exit 0; anote testes e cobertura.
- [ ] **Step 6: Commit** `chore: remove harnesses de reserva, gates de estágio e QA visual encerrados`.

### Task 3: Documentação viva sem histórico nem referências removidas

**Files:**
- Delete: `docs/roadmap-curadoria-simbologia-paralela.md`
- Modify: `README.md`, `CLAUDE.md` (parágrafo final da seção "Curadoria de simbologia"), `examples/README.md` (só se citar algo removido)

**Interfaces:** nenhuma.

- [ ] **Step 1: Apagar** `docs/roadmap-curadoria-simbologia-paralela.md`.
- [ ] **Step 2: README inteiro fica com uso e operação, sem narrativa de etapas.** O escopo é o arquivo todo, não só as seções citadas abaixo.
  - Toda narrativa de etapa, rodada, versão como marco ou resultado medido sai: entre outros, as seções de topo `### Ocorrências e contexto dos pontos (E13)` e `### Leitura complementar local (E12B)`, os parágrafos de "Estado atual" do tipo "O extrator 1.17.0 …", "A referência local recuperou as 95 ocorrências", "E13 distingue …", "E12 acrescenta …", "não cumpre as metas E10", "E15A–E15E detalham o trabalho restante", "A composição de símbolos E15 …", e as descrições da tabela de Configuração que citam "composição E15" ou "política de calibração E12".
  - O comportamento vigente que esses trechos descrevem (aba Trechos físicos e tabela Vãos; OCR complementar opt-in com `ZENY_SERVER_COMPLEMENTARY_OCR=true` e `requirements-experiments.lock`; Leituras auxiliares, limites e cancelamento; o que cada variável de configuração faz) fica, reescrito nas seções existentes adequadas ("Estado atual", "OCR no servidor", "Configuração"), sem IDs de etapa e sem números de rodada.
  - Valores literais de código/configuração que contêm um ID (ex.: o valor `e12-uncalibrated-1`) ficam exatamente como estão.
  - Em "Testes e qualidade", remova a frase sobre a validação de distribuição em host Docker temporário e diretório cliente sem checkout (era `stage12_release_gate`, removido na Task 2); mantenha a descrição do que `build_release.py` faz.
  - Em "Limites conhecidos", remova a referência histórica à "validação da release 0.4.0 registrada no histórico do Git" e as frases sobre correções já feitas ("O falso realce simbólico foi corrigido na extração 1.18.0"). O item do ZIP portátil passa a dizer só o limite (sem assinatura de código e sem instalador): a alegação "a verificação automatizada comprova inicialização autocontida no Windows x64 sem usar o Python do host" sai, porque essa verificação era `stage11_parity_gate`/`stage12_release_gate`, removidos na Task 2. Mantenha os demais limites vigentes.
  - Mantenha intactos os textos que `tests/unit/test_project_scripts.py` exige do README (`TESSDATA_FAST_REVISION` e `PORTUGUESE_TRAINEDDATA_SHA256`).
  - Verificação: `git grep -nwE 'E[0-9]{2}[A-Z]?' -- README.md` → nenhuma ocorrência que não seja valor literal de código/configuração; cole a saída no relatório. (Antes da mudança, esse comando acha as linhas 3, 21, 98, 102, 115, 116, 334, 339 e 355 — prova de que o padrão funciona.)
- [ ] **Step 3: CLAUDE.md.** Troque a última frase da seção "Curadoria de simbologia" por: benchmarks ficam em `scripts/`; `requirements-experiments.lock` é o lock opt-in de dependências fora do runtime padrão (hoje, o OCR complementar do servidor). Nenhuma outra mudança.
- [ ] **Step 4: Critério de grep (R1).** Para cada padrão removido nas Tasks 1–3 (`benchmark_method_reconciliation`, `benchmark_network_alternatives`, `benchmark_reserve_e16`, `benchmark_reserve_e16r2`, `stage10_operational_gate`, `stage11_client_matrix`, `stage11_parity_gate`, `stage12_release_gate`, `visual_qa_review_highlights`, `scripts.experiments` (regex: pega `/` e `.`), `fixtures/symbols/e16r2`, `sealed_access`, `roadmap-curadoria-simbologia-paralela`), `git grep -n -- <padrão> -- ':!docs/roadmap-leitura-vetorial-por-poste.md' ':!docs/superpowers/'` → sem saída. Cole a saída (vazia) de cada um no relatório.
- [ ] **Step 5: Gate completo** → todos exit 0, mais `.venv/Scripts/python.exe -m pytest tests/unit/test_project_scripts.py tests/unit/test_claude_curation_assets.py -q` → passam.
- [ ] **Step 6: Commit** `docs: remove histórico de etapas e roadmap encerrado da documentação viva`.

## Verificação da etapa (orquestrador, depois da Task 3)

- Critério 1: o grep da Task 3, Step 4, rodado de novo sobre o HEAD final.
- Critério 2: `build_release.py` não importa nem chama nenhum removido (grep em `scripts/build_release.py`, `scripts/build_client.py`, `scripts/release_artifact_gate.py`, `scripts/server_artifact_gate.py`, `scripts/client_artifact_gate.py`), `client_artifact_gate.py --source-only` aprovado e `tests/unit/test_release_build.py` verde. `build_release.py` de ensaio não é executado (exige Docker e PyInstaller e grava em `dist/`); a prova é estática.
- Critério 3: gate completo equivalente ao `IniciarTestes.bat` com todos os exit 0 e cobertura ≥ 85,01%.

## Revisão de arquitetura

- **Veredito:** aprovado com notas.
- **Rodadas:** 1 (rodada 0 bloqueada por 3 Importantes, corrigidos no plano: asserções de `segment_distance` na Task 1; README inteiro na Task 3; alegação de verificação automatizada do ZIP portátil).
- **Modelo:** opus (revisor-arquitetura).
- **Notas Menores:** M3 — os critérios que pedem `IniciarTestes.bat` são provados pelo gate equivalente; o usuário roda o `.bat` antes de integrar o lote. M5 — `allow_reserve`/mensagens "sealed until E16" em `scripts/symbol_benchmark_evaluator.py` e `pywinauto` ficam sem uso; revisar em E03/E09. M6 — não há ARCHITECTURE.md; o julgamento usou a seção "Arquitetura" do `CLAUDE.md` e os ADRs 0005, 0012, 0016 e 0017. N1 — verificação do README usa `git grep -nwE` (aplicada).
