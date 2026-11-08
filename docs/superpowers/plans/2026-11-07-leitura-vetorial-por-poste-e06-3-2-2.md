# E06.3.2.2 — Gramática de haste com barras: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reconhecer ATERRAMENTO e PARA_RAIOS_MT sobre o modelo de desenho com a gramática `stem_bars`, acima do analisador atual nas 16 folhas e com leitura errada afirmada = 0.

**Architecture:** a gramática vive num módulo novo do núcleo puro (`drawing_model/grammar_stem.py`) e só o método sobre o modelo (`declarative-drawing-model`) a executa; o tipo já é aceito nos pacotes e ignorado pelo motor antigo (E06.3.2.1). A caixa do casamento é o pictograma, como no legado, e a haste inteira entra só como componente, para a reconciliação do runner fundir a ocorrência com a do detector legado. As 8 variantes de f02-19 (ATERRAMENTO) e f02-21 (PARA_RAIOS_MT) são habilitadas, e o método sobe para 1.1.0.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só nos adaptadores, scripts e fixtures), JSON, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3", "E06.3.2" (divisão), "E06.3.2.1" (handoff) e "E06.3.2.2"; os blocos "Para a E06.3" dos handoffs da E06.2.1, E06.2.2.1, E06.2.2.2 e E06.3.1; ADR 0016 e ADR 0006; `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md` (laboratório); o levantamento `tmp/e06/levantamento-e06.md` do checkout principal (§3, §10). Este plano parte do rascunho revisado nas rodadas 0 e 1 da E06.3.2 e traz os achados N3, N4, M-a, M-c, M4 e M-d.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF; o núcleo `drawing_model/` não importa PyMuPDF; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- Nenhuma migração SQLite, nenhuma mudança de API ou DTO. O método sobre o modelo liga só no `SymbolCompositionRunner` opt-in (D12); o analisador padrão não muda.
- Mudança de comportamento de saída incrementa a versão do método (ADR 0006): `declarative-drawing-model` 1.0.0 → 1.1.0 (Task 4).
- Sem dependência nova em nenhum lock.
- PDFs reais, recortes e conjuntos de dados nunca entram no Git. Fixture sintética autoral positiva e negativa; nenhuma coordenada, hash ou nome de folha real em código, pacote, fixture ou teste (guarda da E06.1, estendida na Task 3).
- Nada lê `examples/avaliacao-cega/`. As referências da rodada E03 (`tmp/curadoria-simbologia/20261103-2300-fichas/`) estão congeladas; leitores visuais não participam.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos. Testes sem dependência de ordem, cwd, porta ou arquivo fixo (use `tmp_path`). mypy strict, ruff check, ruff format, complexidade < 31 em `src`.
- Não tocar `scripts/benchmark_ficha_poste.py` (E15) nem `tests/conftest.py`.
- Worktree da etapa: `.venv/Scripts/python.exe`. Em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` do worktree da etapa, a partir da raiz do worktree da tarefa; a suíte inteira usa `-n` = 20 ÷ suítes ativas (o despacho informa o número).

## Review Focus

1. Haste com barras encostada numa linha longa da rede do mesmo estilo → casa, com a caixa do pictograma; três ou quatro traços paralelos que não são barras de haste (hachura, cerca, texto em glifo como `E` ou `≡`) → não casam (Task 1).
2. Símbolo girado (0°, 90°, 45°) e página com `/Rotate` 90 → mesma variante, caixa coerente na página exibida (Tasks 1 e 4).
3. Página hostil com milhares de segmentos curtos paralelos → `TetoGramaticasExcedido` pelo orçamento, nunca laço sem teto (Task 3).
4. Variante habilitada de tipo só do modelo na matriz da curadoria e no diff núcleo × motor → `fora_do_dominio` no motor antigo e fora do diff (Task 2).
5. Ocorrência vista pelo legado e pelo método novo no runner opt-in → uma ocorrência só, inclusive na variante com X sem envolvente (Task 4).

## Decisões do plano

- **R-E06.3.2-2 (vigente desde a E06.3.2.1):** campos exatos `{"kind": "stem_bars", "bars": 3 | 4, "taper": "decreasing" | "alternating", "enclosure": "none" | "ellipse", "removal_mark": bool, "max_span": (0, 72]}`; pares válidos 3/`decreasing` (ATERRAMENTO) e 4/`alternating` (PARA_RAIOS_MT). `enclosure` e `removal_mark` separam as quatro variantes de situação (base `none`/false; envolvente `ellipse`/false; envolvente e X `ellipse`/true; X sem envolvente `none`/true), mutuamente exclusivas por construção: um desenho casa no máximo uma. A cor não decide nada. Os limiares geométricos são constantes do módulo, escolhidos pelo laboratório.
- **R-E06.3.2-3, caixa e componentes:** a caixa do casamento é o **pictograma**, com a regra de `pymupdf_symbols._symbol_footprint`: a envolvente quando há, senão as barras e o trecho da haste até o comprimento da maior barra. O X **não** entra na caixa (M-a; o legado não o inclui), e a haste inteira também não. `max_span` vale sobre o pictograma. A ficha E03 anota o pictograma (caixa ~0,004 × 0,005 da página). `CasamentoGramatica.componentes` (já existe, padrão `()`) lista as posições em `modelo.caminhos` dos demais caminhos do símbolo (haste, barras, X), sem repetir `caminho`, em ordem crescente. A observação ganha uma `PrimitivaObservadaSimbolo` por caminho, com o índice cru e a camada de cada um; `pontos_originais` de cada primitiva é a caixa daquele caminho.
- **R-E06.3.2-4, critério de aceite:** por classe, precisão **e** recall estritamente maiores que os do `atual` (critério `centro`), contra a linha de base congelada `tmp/e06-2-2-2/simbolos/simbolos-ficha.json` (sha256 `b6a3118d…`), conferida de novo na E06.3.2.1: ATERRAMENTO > 56,2% (41/73) e > 95,3% (41/43); PARA_RAIOS_MT > 71,4% (10/14) e > 76,9% (10/13). E **leitura errada afirmada = 0** em ATERRAMENTO e PARA_RAIOS_MT: `total.modelo.centro.leituras_erradas.por_classe` do `simbolos-ficha.json` sem essas classes (a unidade é o par predição × referência de outra classe; linha de base do `atual`: ATERRAMENTO 13, PARA_RAIOS_MT 4). Se o laboratório mostrar que uma referência perdida não é desenhável pelo vetor, a ruling vai ao handoff antes de afrouxar qualquer número.
- **R-E06.3.2-5, matriz da curadoria:** variante habilitada com tipo em `GRAMATICAS_SO_MODELO` tem `declarative-vector-packages` = `fora_do_dominio` em `scripts/coverage_matrix_e16.py`; a matriz não ganha coluna nova (contrato da curadoria; a rodada seguinte decide). O status de variante E04 continua `nao_avaliavel`: o ganho aparece no benchmark por ficha. Vai para "Decisões para o usuário", com os demais consumidores de `status == "enabled"` (tabela de suporte, `symbol_benchmark_runner.py`, `curation_backlog.py`).
- **R-E06.3.2-6, sinal "Exclusivo" no runner opt-in:** uma ocorrência de ATERRAMENTO ou PARA_RAIOS_MT vista pelo legado e pelo método novo funde e passa a "Suportado". Se vencer H-A, são dois algoritmos independentes; se vencer H-B ou H-C, a gramática reimplementa a consulta do legado e "Suportado" **não** é corroboração (como na ruling da E06.2.2.1). Aceito até a E09, sem mudança de produção. A fusão é provada no teste sintético da Task 4; a taxa nas 16 folhas **não** é medida (N4: exigiria um script novo de ~40 min e passaria o teto de ~3h da etapa). Vai para "Decisões para o usuário".
- **R-E06.3.2-8, pendências herdadas:** o oráculo de `tests/unit/test_gasto_por_fase_ataque.py` sai na Task 3, porque a Task 1 muda o despacho do casador; `_MODULOS_DO_DIGEST` vira teste de fecho por imports na Task 4. Ficam para depois, com ruling no handoff: promover os privados de `grammar_disc` (a E06.3.3 mexe em `grammar_frames`), `runner._package_prediction` público, recortes e fila do diff.
- **R-E06.3.2-9, se vencer H-A (grupo como unidade):** quem consome `grupos` adiciona `modelo.grupos_falhou` às fontes consumidas (`symbol_grammars._FONTES_CONSUMIDAS`), põe `LIMITE_VISITAS_AGRUPAMENTO` nos `parametros` do perfil (Task 4) e revê R-1 da E06.2.2.1 (subir `VERSAO_MODELO_DESENHO`). Com H-B ou H-C, nada disso se aplica.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py` (novo) | gramática de haste com barras | 1 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` | despacho explícito por `kind` e `stem_bars` | 1 |
| `tests/fixtures/symbol_grammars/__init__.py`, `tests/fixtures/symbol_grammars/stem_bars.py` (novos) | desenhos sintéticos e `CASOS_HASTE` | 1 |
| `tests/unit/test_grammar_stem.py` (novo) | positivos, negativos, pictograma, componentes, `kind` desconhecido | 1 |
| `tests/unit/test_gramatica_so_modelo_ataque.py` | reescreve `test_modelo_ainda_nao_executa_stem_bars_e_falha_alto` | 1 |
| `scripts/coverage_matrix_e16.py`, `tests/unit/test_e16_coverage_matrix.py` | R-5 | 2 |
| `scripts/diff_simbolos_nucleo_motor.py`, `tests/unit/test_diff_simbolos_nucleo_motor.py` | só `variantes_do_motor` | 2 |
| `tests/unit/test_grammar_stem_teto.py` (novo) | página hostil e orçamento | 3 |
| `tests/unit/test_symbol_packages_sem_memorizacao.py` | guarda em `grammar_stem.py` e na fixture | 3 |
| `tests/unit/test_gasto_por_fase_ataque.py` | oráculo removido (R-8) | 3 |
| `tests/unit/test_symbol_matcher_paridade.py` | `grammar_stem` no teste de pureza | 3 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | primitivas por caminho, versão 1.1.0 | 4 |
| `src/zeny_project_handler_server/symbol_execution.py` | módulos do fecho no digest | 4 |
| `tests/unit/test_model_symbols.py`, `tests/integration/test_model_symbols_runner.py` | primitivas, versão, fecho, fusão com o legado | 4 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-19.json`, `family-f02-21.json` | 8 variantes habilitadas | 5 |
| `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py` | contagens 22→30 e 401→393 | 5 |

Laboratório; depois Onda A: Tasks 1 e 2; Onda B: Tasks 3, 4 e 5; Task 6 (medição, orquestrador).

Soma das tarefas: 3h00 (45 + 25 + 25 + 30 + 35 + 20), mais o laboratório (caixa de 60 min). Parede estimada com as ondas: ~2h50 incluindo o laboratório.

## Laboratório (antes da Onda A)

- **Base:** a branch da etapa em `2b6cc09` ou depois. Cada hipótese: um `desenvolvedor` com `isolation: "worktree"`, sem commit e sem a suíte inteira, que implementa `grammar_stem.py`, o despacho no casador (R-2, R-3), a habilitação das 8 variantes no JSON e testes focados com os positivos e negativos do Review Focus 1, e mede.
- **Hipóteses:**
  - **H-A, grupo como unidade:** a gramática roda por `GrupoCandidato` de `modelo.grupos`; haste e barras precisam estar no mesmo grupo. R-9 se aplica.
  - **H-B, segmento como semente e consulta espacial:** cada `Segmento` de `contexto.grade_segmentos` com comprimento plausível de haste consulta a grade num raio proporcional a ele, como o legado (`pymupdf_symbols._ground_and_mt_arrester_matches` e `_ground_bar_signature`), incluindo traço longo cortado na caixa.
  - **H-C, H-B com limiares por família:** os passos de H-B com tolerâncias escolhidas por um sinal da própria página (origem dos `TextoModelo`: glifo, SHX ou nativo), sem ler o documento. Exige fixture sintética por família.
- **Comando** (no worktree da hipótese, com o `.venv` do worktree da etapa e `PYTHONPATH=<worktree>/src`; `--processos 6` com as três rodando):
  `.venv/Scripts/python.exe -m scripts.benchmark_simbolos_ficha --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/laboratorio/e06-3-2-2/<hipotese>/iter-<k> --metodo modelo --processos 6`
- **Métrica:** por classe (`centro`), tp/fp/fn de ATERRAMENTO e PARA_RAIOS_MT em `total.modelo.centro.por_classe`, contra R-4; `total.modelo.centro.leituras_erradas.por_classe` dessas duas classes; tempo máximo por folha; gasto máximo do orçamento por folha (`gasto_por_fase`).
- **Vitória:** R-4 nas duas classes, leitura errada afirmada = 0 nelas, positivos e negativos sintéticos verdes, gasto máximo ≤ 200.000 consultas por folha (R-E06.2.2.2-4). Desempate: soma dos F1 das duas classes, depois o menor tempo máximo por folha.
- **Parada:** 60 min por hipótese, ou vitória com margem de 2 tp em cada classe.
- **Entrega:** em `<checkout principal>/tmp/laboratorio/e06-3-2-2/<hipotese>/`: `patch.diff` (contra a base), `metricas.json` por iteração e `conclusoes.md` (o que mudou, falsos positivos vistos por tipo, sem coordenada de folha real no patch).
- **Seleção:** pela métrica, com ruling no ledger. Se nenhuma vencer, a ruling registra a melhor e o déficit, e a Task 1 parte dela; o critério 2 vira impedimento real se a Task 6 não fechar.

## Tasks

### Task 1: Gramática de haste com barras

**Estimativa:** 45 min · **Depende de:** laboratório · **Risco:** alto · **Laboratório:** sim (parte do patch vencedor)

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`
- Create: `tests/fixtures/symbol_grammars/__init__.py`, `tests/fixtures/symbol_grammars/stem_bars.py`, `tests/unit/test_grammar_stem.py`
- Modify: `tests/unit/test_gramatica_so_modelo_ataque.py` (só `test_modelo_ainda_nao_executa_stem_bars_e_falha_alto`)

**Interfaces:**
- Consumes: `ContextoGramatica` (grades, orçamento); `CasamentoGramatica.componentes`.
- Produces: `grammar_stem.casa_hastes(contexto: ContextoGramatica, gramatica: Mapping[str, Any]) -> list[tuple[Caixa, int, tuple[int, ...]]]` (caixa visual do pictograma, R-3; posição do caminho que ancora o símbolo; componentes), sem efeito colateral fora do orçamento; toda consulta paga do orçamento. `_casar_no_contexto` despacha explicitamente por `kind` (`terminal_disc`, `stem_bars` e os tipos de moldura) e levanta `ValueError` em `kind` desconhecido, preenchendo `componentes`. A fixture exporta `CASOS_HASTE: tuple[tuple[str, dict[str, Any]], ...]` (id de cada uma das 8 variantes e a gramática dela, com o `max_span` do laboratório) e as funções de desenho que as Tasks 3 e 4 usam.

- [ ] **Step 1: Escrever a fixture e os testes**, partindo do patch vencedor. A fixture desenha com PyMuPDF (cor comum, sem copiar folha real): haste com 3 barras decrescentes; com 4 alternadas; cada uma com elipse envolvente, com X, com os dois; giradas 90° e 45°; haste encostada numa linha longa do mesmo estilo; página com `/Rotate` 90. Negativos: 3 barras iguais; 2 barras; barras não perpendiculares; espaçamento fora da faixa; hachura de 6 traços paralelos sem haste; texto em glifo `E` e `≡` desenhado como caminho; barras de cor diferente da haste. Em `test_grammar_stem.py`, pelo núcleo (`pagina_para_gramaticas` + `casar_variantes` com as 8 variantes de `CASOS_HASTE`):
  - `test_positivo_casa_so_a_variante_certa`, parametrizado pelos 8 positivos × 3 rotações: exatamente uma variante, a esperada;
  - `test_caixa_e_o_pictograma`: a caixa contém barras, envolvente (quando há) e a ponta da haste, e não a haste inteira nem o X fora da envolvente; com a haste encostada na linha longa, a caixa é a mesma da haste curta, a menos de 0,5 pt;
  - `test_negativo_nao_casa`, parametrizado pelos negativos;
  - `test_componentes_listam_haste_barras_e_x`;
  - `test_kind_desconhecido_recusa`;
  - em `test_gramatica_so_modelo_ataque.py`, `test_modelo_ainda_nao_executa_stem_bars_e_falha_alto` vira `test_modelo_executa_stem_bars`: com uma variante `stem_bars` habilitada, `observar_pacotes_modelo` numa página com o positivo dela observa uma vez a classe dela, sem erro.
- [ ] **Step 2: Rodar** e conferir que falham sem o patch e passam com ele.
- [ ] **Step 3: Implementar** a partir do patch, só nos dois arquivos de produção.
- [ ] **Step 4: Rodar** os testes novos, `tests/unit/test_symbol_matcher*.py`, `tests/unit/test_gramatica_so_modelo*.py`, `tests/unit/test_grammar_*`, ruff, format, mypy e `scripts/complexity_gate.py src`; e o benchmark do laboratório com `--metodo modelo` (com as 8 variantes habilitadas só no worktree, sem commitar o JSON), colando no relatório os blocos de ATERRAMENTO e PARA_RAIOS_MT e as leituras erradas.
- [ ] **Step 5: Commit** (`feat: gramatica de haste com barras no nucleo`).

### Task 2: Matriz e diff para tipo só do modelo

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `scripts/coverage_matrix_e16.py`, `tests/unit/test_e16_coverage_matrix.py`
- Modify: `scripts/diff_simbolos_nucleo_motor.py`, `tests/unit/test_diff_simbolos_nucleo_motor.py`

**Interfaces:**
- Consumes: `declarative_symbols.GRAMATICAS_SO_MODELO`, `variantes_do_motor`.

- [ ] **Step 1: Escrever os testes**, com pacotes sintéticos em `tmp_path`:
  - `test_variante_so_do_modelo_fica_fora_do_dominio_no_motor` (R-5): variante E04 habilitada com `stem_bars` → `declarative-vector-packages` = `fora_do_dominio`, status `nao_avaliavel`; variante E07 habilitada `label_in_frame` continua `id_exato_sintetico`;
  - no diff: com uma variante `stem_bars` habilitada nos pacotes, ela não aparece em nenhum lado do diff, e as demais continuam.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar** R-5 na matriz e `variantes_do_motor` nos dois lados do diff (e na docstring).
- [ ] **Step 4: Rodar** os dois arquivos de teste, `tests/unit/test_curation_coverage_e16.py`, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: matriz e diff tratam gramatica so do modelo`).

### Task 3: Teto, guarda, pureza e oráculo

**Estimativa:** 25 min · **Depende de:** Task 1 · **Risco:** normal · **Laboratório:** não

**Files:**
- Create: `tests/unit/test_grammar_stem_teto.py`
- Modify: `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_gasto_por_fase_ataque.py`, `tests/unit/test_symbol_matcher_paridade.py`

**Interfaces:**
- Consumes: `grammar_stem`, as funções de desenho da fixture (Task 1).

- [ ] **Step 1:** `test_pagina_hostil_estoura_o_orcamento` (20.000 traços curtos paralelos e limite pequeno → `TetoGramaticasExcedido`) e `test_gasto_cresce_linear_com_hastes` (gasto de 10 e de 100 hastes isoladas, razão ≤ 15, contagem de trabalho e não tempo de parede); `test_gramaticas_novas_passam_na_guarda` aplica `_violacoes_de_texto` ao fonte de `grammar_stem.py` e de `tests/fixtures/symbol_grammars/stem_bars.py`; `grammar_stem` entra na tupla de `test_modulos_do_nucleo_nao_importam_pymupdf`; remova de `test_gasto_por_fase_ataque.py` o oráculo do corpo antigo de `casar_variantes` e os testes que dependem só dele (R-8), mantendo `test_fases_nao_negativas_e_somam_o_gasto_do_orcamento`.
- [ ] **Step 2: Rodar** os quatro arquivos; se o teto ou a linearidade falharem, reporte como DONE_WITH_CONCERNS com a saída (é defeito de produção da Task 1, não do teste).
- [ ] **Step 3: Commit** (`test: teto, guarda e pureza da gramatica de haste`).

### Task 4: Observação com componentes, versão e digest

**Estimativa:** 30 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/model_symbols.py`
- Modify: `src/zeny_project_handler_server/symbol_execution.py`
- Modify: `tests/unit/test_model_symbols.py`, `tests/integration/test_model_symbols_runner.py`

**Interfaces:**
- Consumes: `CasamentoGramatica.componentes`, `grammar_stem`, as funções de desenho de `tests/fixtures/symbol_grammars/stem_bars.py`.
- Produces: `_VERSAO = "1.1.0"`; observação com uma primitiva por caminho do casamento (R-3); todo módulo do fecho de imports de `model_symbols` no digest do runner.

- [ ] **Step 1: Escrever os testes:**
  - em `test_model_symbols.py`: `test_observacao_tem_uma_primitiva_por_caminho` (casamento com `componentes=(5, 9)` → 3 primitivas com os índices crus das posições, em ordem, e a camada de cada caminho), `test_sem_componentes_continua_com_uma_primitiva`, `test_versao_1_1_0`;
  - em `test_model_symbols_runner.py`: `test_digest_cobre_o_fecho_de_imports` no lugar da lista `_MODULOS_DO_DIGEST` (todo módulo de `zeny_project_handler.adapters.analysis` importado, direta ou transitivamente, por `model_symbols` está no digest); `test_haste_funde_com_o_legado`, parametrizado por haste curta, haste encostada numa linha longa, X sem envolvente e página com `/Rotate` 90 (pacotes com a variante correspondente habilitada em `tmp_path`): o runner reconcilia legado e modelo numa só ocorrência.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.** Todo módulo que o fecho apontar entra no digest (por exemplo `drawing_model/model.py`); a assinatura do runner muda (cache miss opt-in, esperado). Se `run` ou `_cache_complete` passarem de CC 30, extraia função antes. Se a fusão falhar por geometria do pictograma, reporte DONE_WITH_CONCERNS com os números de `_same_occurrence` (centro, tamanho, IoU), sem afrouxar a reconciliação.
- [ ] **Step 4: Rodar** os dois arquivos, `tests/server/` filtrado por `symbol`, ruff, format, mypy e `scripts/complexity_gate.py src`.
- [ ] **Step 5: Commit** (`feat: observacao com componentes e versao 1.1.0 do metodo sobre o modelo`).

### Task 5: Habilitação das variantes de haste

**Estimativa:** 35 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-19.json` (v001–v004), `family-f02-21.json` (v005–v008)
- Modify: `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py`

**Interfaces:**
- Consumes: `CASOS_HASTE` (Task 1) — se a fixture não exportar com esse nome, devolva ao orquestrador.
- Produces: 30 `enabled` e 393 `pending`.

- [ ] **Step 1: Atualizar os testes:** `test_enabled_status_is_distinct_from_registered_coverage` com habilitadas = `_ENABLED_IDS` ∪ ids de `CASOS_HASTE` e as de `CASOS_HASTE` com tipo em `GRAMATICAS_SO_MODELO` (os testes que rodam o motor antigo sobre `ENABLED_CASES` não mudam); contagens `(393, 30)` no auditor e `== 30`/`== 393` na tabela de suporte (`test_e14_symbol_review.py:287-288` e `test_pacotes_classes_da_ficha.py`); o golden das variantes antigas muda só nas 8 (de `pending` com `reason` para `enabled` com `grammar` e `negative_examples`).
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Habilitar** as 8 variantes com a gramática de `CASOS_HASTE` e `negative_examples` = os `confusable_negatives` do inventário, sem `reason`.
- [ ] **Step 4: Rodar** os testes alterados, `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`, `enabled` 30), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py`, `tests/unit/test_gramatica_so_modelo*.py`, `tests/unit/test_e16_coverage_matrix.py`, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: habilita aterramento e para-raios MT sobre o modelo`).

### Task 6: Medição nas 16 folhas (orquestrador)

**Estimativa:** 20 min · **Depende de:** Tasks 1 a 5 · **Risco:** normal · **Laboratório:** não

Sem código: o orquestrador roda, na branch da etapa com as Tasks 1–5 integradas, com `<rodada E03>` = `<checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas` e `--processos 10`:
- [ ] `python -m scripts.benchmark_simbolos_ficha --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2-2/simbolos --metodo atual --metodo modelo --processos 10` → R-4 nas duas classes e leituras erradas = 0 nelas; `atual` igual ao congelado; o bloco `modelo` das outras classes igual, por folha, ao congelado. Falha vira rodada de correção da Task 1 (e repete o benchmark).
- [ ] `python -m scripts.diff_simbolos_nucleo_motor --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2-2/diff --processos 10` → contra `tmp/e06-2-2-2/diff/diff-nucleo-motor.json` (sha256 `20f3b708…`), pela chave natural `(pdf_id, página, variante, índice cru)`: `ambos` 29 e `so_*` 0 nas variantes do motor.
- [ ] `python -m scripts.audit_symbol_packages` → `errors: []`, 30 `enabled`.

## Fechamento operacional

- Suíte inteira por onda; testador de etapa (a Task 3 é de risco normal) sobre `MERGE_BASE..HEAD`; `osv-scanner` nos 7 locks; `check_test_integrity --base <MERGE_BASE>`; revisão final; `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` (conferir a data do `relatorio-testes.txt`).
- Handoff com: tabela do benchmark, leituras erradas, diff contra o congelado, decisões que mudam o visível (R-5, R-6) em "Decisões para o usuário", o bloco "Para a E06.3.3" (tipo só do modelo, pictograma e componentes para as molduras de para-raios BT e transformador) e o bloco "Para a E09".
