# E06.3.2.2 — Gramática de haste com barras: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reconhecer ATERRAMENTO e PARA_RAIOS_MT sobre o modelo de desenho com a gramática `stem_bars`, acima do analisador atual nas 16 folhas e com leitura errada afirmada = 0.

**Architecture:** a gramática vive num módulo novo do núcleo puro (`drawing_model/grammar_stem.py`) e só o método sobre o modelo (`declarative-drawing-model`) a executa; o tipo já é aceito nos pacotes e ignorado pelo motor antigo (E06.3.2.1). A caixa do casamento é o pictograma, como no legado, e a haste inteira entra só como componente, para a reconciliação do runner fundir a ocorrência com a do detector legado. As 8 variantes de f02-19 (ATERRAMENTO) e f02-21 (PARA_RAIOS_MT) são habilitadas, e o método sobe para 1.1.0.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só nos adaptadores, scripts e fixtures), JSON, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3", "E06.3.2" (divisão), "E06.3.2.1" (handoff) e "E06.3.2.2"; os blocos "Para a E06.3" dos handoffs da E06.2.1, E06.2.2.1, E06.2.2.2 e E06.3.1; ADR 0016 e ADR 0006; `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md` (laboratório); o levantamento `tmp/e06/levantamento-e06.md` do checkout principal (§3, §10).

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF; o núcleo `drawing_model/` não importa PyMuPDF; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- Nenhuma migração SQLite, nenhuma mudança de API ou DTO. O método sobre o modelo liga só no `SymbolCompositionRunner` opt-in (D12); o analisador padrão não muda.
- Mudança de comportamento de saída incrementa a versão do método (ADR 0006): `declarative-drawing-model` 1.0.0 → 1.1.0 (Task 3), integrada antes da habilitação (Task 4).
- Sem dependência nova em nenhum lock.
- PDFs reais, recortes e conjuntos de dados nunca entram no Git. Fixture sintética autoral positiva e negativa; nenhuma coordenada, hash ou nome de folha real em código, pacote, fixture ou teste (guarda da E06.1, estendida na Task 5; ela também reprova a string `.pdf`).
- Nada lê `examples/avaliacao-cega/`. As referências da rodada E03 (`tmp/curadoria-simbologia/20261103-2300-fichas/`) estão congeladas; leitores visuais não participam.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos. Testes sem dependência de ordem, cwd, porta ou arquivo fixo (use `tmp_path`). mypy strict, ruff check, ruff format, complexidade < 31 em `src`.
- Não tocar `scripts/benchmark_ficha_poste.py` (E15) nem `tests/conftest.py`.
- Worktree da etapa: `.venv/Scripts/python.exe`. Em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` do worktree da etapa, a partir da raiz do worktree da tarefa; a suíte inteira usa `-n` = 20 ÷ suítes ativas (o despacho informa o número).

## Review Focus

1. Haste com barras encostada numa linha longa da rede do mesmo estilo → casa, com a caixa do pictograma; três ou quatro traços paralelos que não são barras de haste (hachura, cerca, texto em glifo como `E` ou `≡`) → não casam (Task 1).
2. Símbolo girado (0°, 90°, 45°) e página com `/Rotate` 90 → mesma variante, caixa coerente na página exibida (Tasks 1 e 3).
3. Página hostil com milhares de segmentos curtos paralelos → `TetoGramaticasExcedido` pelo orçamento, nunca laço sem teto (Task 5).
4. Variante habilitada de tipo só do modelo na matriz da curadoria e no diff núcleo × motor → `fora_do_dominio` no motor antigo e fora da comparação; o gasto do núcleo a inclui (Task 2).
5. Ocorrência vista pelo legado e pelo método novo no runner opt-in → uma ocorrência só, com a geometria do pictograma, inclusive na variante com X sem envolvente e em página `/Rotate` 90 (Task 3).

## Decisões do plano

- **R-E06.3.2-2 (vigente desde a E06.3.2.1):** campos exatos `{"kind": "stem_bars", "bars": 3 | 4, "taper": "decreasing" | "alternating", "enclosure": "none" | "ellipse", "removal_mark": bool, "max_span": (0, 72]}`; pares válidos 3/`decreasing` (ATERRAMENTO) e 4/`alternating` (PARA_RAIOS_MT). `enclosure` e `removal_mark` separam as quatro variantes de situação (base `none`/false; envolvente `ellipse`/false; envolvente e X `ellipse`/true; X sem envolvente `none`/true), mutuamente exclusivas por construção: um desenho casa no máximo uma. A cor não decide nada. Os limiares geométricos são constantes do módulo, escolhidos pelo laboratório.
- **R-E06.3.2-3, caixa e componentes:** a caixa do casamento é o **pictograma**, com a regra de `pymupdf_symbols._symbol_footprint`: a envolvente quando há, senão as barras e o trecho da haste até o comprimento da maior barra. O X **não** entra na caixa (o legado não o inclui), e a haste inteira também não. `max_span` vale sobre o pictograma. A ficha E03 anota o pictograma (caixa ~0,004 × 0,005 da página). `CasamentoGramatica.componentes` (já existe, padrão `()`) lista as posições em `modelo.caminhos` dos demais caminhos do símbolo (haste, barras, X), sem repetir `caminho`, em ordem crescente. A observação ganha uma `PrimitivaObservadaSimbolo` por caminho, com o índice cru e a camada de cada um; `pontos_originais` de cada primitiva é a caixa daquele caminho no espaço cru (derrotado), como `caixa_crua` em `model_symbols._observacao`.
- **R-E06.3.2-4, critério de aceite:** por classe, precisão **e** recall estritamente maiores que os do `atual` (critério `centro`), contra a linha de base congelada `tmp/e06-2-2-2/simbolos/simbolos-ficha.json` (sha256 `b6a3118d…`), conferida de novo na E06.3.2.1: ATERRAMENTO > 56,2% (41/73) e > 95,3% (41/43); PARA_RAIOS_MT > 71,4% (10/14) e > 76,9% (10/13). E **leitura errada afirmada = 0** em ATERRAMENTO e PARA_RAIOS_MT: `total.modelo.centro.leituras_erradas.por_classe` do `simbolos-ficha.json` sem essas classes (a unidade é o par predição × referência de outra classe; linha de base do `atual`: ATERRAMENTO 13, PARA_RAIOS_MT 4). E o gasto máximo do orçamento por folha, com a gramática nova incluída, ≤ 200.000 consultas (R-E06.2.2.2-4), sem página `teto_consultas`. Se o laboratório mostrar que uma referência perdida não é desenhável pelo vetor, a ruling vai ao handoff antes de afrouxar qualquer número.
- **R-E06.3.2-5, matriz da curadoria:** variante habilitada com tipo em `GRAMATICAS_SO_MODELO` tem `declarative-vector-packages` = `fora_do_dominio` em `scripts/coverage_matrix_e16.py`; a matriz não ganha coluna nova (contrato da curadoria; a rodada seguinte decide). O status de variante E04 continua `nao_avaliavel`: o ganho aparece no benchmark por ficha. Vai para "Decisões para o usuário", com os demais consumidores de `status == "enabled"` (tabela de suporte, `symbol_benchmark_runner.py`, `curation_backlog.py`).
- **R-E06.3.2-6, sinal "Exclusivo" no runner opt-in (decisão de arquitetura, vai ao usuário em entrevista no fim do lote):** uma ocorrência de ATERRAMENTO ou PARA_RAIOS_MT vista pelo legado e pelo método novo funde e passa a "Suportado". Se vencer H-A, são dois algoritmos independentes; se vencer H-B ou H-C, a gramática reimplementa a consulta do legado e "Suportado" **não** é corroboração (como na ruling da E06.2.2.1), e essas classes saem do filtro "Exclusivos" do revisor. A alternativa (exclusividade por família de método) exige gravar a família em `simbolo_observacoes`, uma migração. Até a decisão, fica aceito sem mudança de produção.
- **R-E06.3.2-7, escopo da fusão (N4, mudança de escopo, vai a "Decisões para o usuário"):** a seção da etapa pede a taxa de fusão com o legado no runner. Ela **não** é medida nas 16 folhas: exigiria um script novo de ~40 min e passaria o teto de ~3h. A fusão é provada no teste sintético da Task 3, e o handoff leva à E07 que ela só foi provada em fixture: uma ocorrência que não funde vira símbolo duplicado para quem lê o runner (D12).
- **R-E06.3.2-8, pendências herdadas:** o oráculo de `tests/unit/test_gasto_por_fase_ataque.py` sai na Task 1, que muda o despacho do casador (o oráculo chama os privados `_achados_em_molduras`, `_achados_em_discos`, `_gramatica` e `_DISCO_TERMINAL`); `_MODULOS_DO_DIGEST` vira teste de fecho por imports na Task 3. Ficam para depois, com ruling no handoff: promover os privados de `grammar_disc` (a E06.3.3 mexe em `grammar_frames`), `runner._package_prediction` público, recortes e fila do diff.
- **R-E06.3.2-9, se vencer H-A (grupo como unidade):** o plano volta à revisão de arquitetura antes da Onda A, com `drawing_model/symbol_grammars.py` (`_FONTES_CONSUMIDAS` + `modelo.grupos_falhou`) e `drawing_model/model.py` (`VERSAO_MODELO_DESENHO`) na File Structure, a decisão sobre R-1 da E06.2.2.1 tomada e um teste de `grupos_falhou` → `FORA_DOMINIO`. Com H-B ou H-C, nada disso se aplica.
- **R-E06.3.2-10, se vencer H-C (limiares por sinal da página):** a ruling registra a alternativa descartada, `PerfilFamilia` do documento (ADR 0016: "a família do PDF escolhe o perfil de recuperação"), e o porquê: o método roda por página e a família é do documento.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py` (novo) | gramática de haste com barras | 1 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` | despacho explícito por `kind` e `stem_bars` | 1 |
| `tests/fixtures/symbol_grammars/stem_bars.py` (novo; o pacote `__init__.py` e `paginas.py` já existem) | desenhos sintéticos e `CASOS_HASTE` | 1 |
| `tests/unit/test_grammar_stem.py` (novo) | positivos, negativos, pictograma, componentes, `kind` desconhecido | 1 |
| `tests/unit/test_gasto_por_fase_ataque.py` | oráculo removido (R-8) | 1 |
| `tests/unit/test_gramatica_so_modelo_ataque.py` | caracterização reescrita (1); 3 testes com pacotes reais invertidos (4) | 1, 4 |
| `scripts/coverage_matrix_e16.py`, `tests/unit/test_e16_coverage_matrix.py` | R-5 | 2 |
| `scripts/diff_simbolos_nucleo_motor.py`, `tests/unit/test_diff_simbolos_nucleo_motor.py` | comparação só com `variantes_do_motor`; núcleo e gasto com todas | 2 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | primitivas por caminho, versão 1.1.0 | 3 |
| `src/zeny_project_handler_server/symbol_execution.py` | módulos do fecho no digest | 3 |
| `tests/unit/test_model_symbols.py`, `tests/integration/test_model_symbols_runner.py` | primitivas, versão, fecho, fusão com o legado | 3 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-19.json`, `family-f02-21.json` | 8 variantes habilitadas | 4 |
| `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py` | contagens 22→30 e 401→393; gramática real = `CASOS_HASTE` | 4 |
| `tests/unit/test_grammar_stem_teto.py` (novo) | página hostil e orçamento | 5 |
| `tests/unit/test_symbol_packages_sem_memorizacao.py` | guarda em `grammar_stem.py` e na fixture | 5 |
| `tests/unit/test_symbol_matcher_paridade.py` | `grammar_stem` no teste de pureza | 5 |

Ondas: laboratório; Onda A: Task 1; Onda B: Tasks 2, 3 e 4, integradas nessa ordem (a versão 1.1.0 entra antes da habilitação); Onda C: Task 5; Task 6 (medição, orquestrador).

Soma das tarefas: 3h00 (45 + 25 + 30 + 35 + 20 + 25), mais o laboratório (caixa de 60 min). As etapas comparáveis levaram até 4h48 no relógio: vale a regra de estouro de 4h30.

## Laboratório (antes da Onda A)

- **Base:** a branch da etapa em `2b6cc09` ou depois. Cada hipótese: um `desenvolvedor` com `isolation: "worktree"`, sem commit e sem a suíte inteira, que implementa `grammar_stem.py`, o despacho no casador (R-2, R-3), a habilitação das 8 variantes no JSON e testes focados com os positivos e negativos do Review Focus 1, e mede.
- **Hipóteses:**
  - **H-A, grupo como unidade:** a gramática roda por `GrupoCandidato` de `modelo.grupos`; haste e barras precisam estar no mesmo grupo. R-9 se aplica.
  - **H-B, segmento como semente e consulta espacial:** cada `Segmento` de `contexto.grade_segmentos` com comprimento plausível de haste consulta a grade num raio proporcional a ele, como o legado (`pymupdf_symbols._ground_and_mt_arrester_matches` e `_ground_bar_signature`), incluindo traço longo cortado na caixa.
  - **H-C, H-B com limiares por sinal da página:** os passos de H-B com tolerâncias escolhidas pela origem dos `TextoModelo` da página (glifo, SHX ou nativo), sem ler o documento. Exige fixture sintética por família. R-10 se aplica.
- **Comandos** (no worktree da hipótese, com o `.venv` do worktree da etapa e `PYTHONPATH=<worktree>/src`; `--processos 6` com as três rodando; `<rodada E03>` = `<checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas`):
  - `.venv/Scripts/python.exe -m scripts.benchmark_simbolos_ficha --rodada <rodada E03> --saida <checkout principal>/tmp/laboratorio/e06-3-2-2/<hipotese>/iter-<k> --metodo modelo --processos 6`
  - no fim (e quando a métrica de qualidade já vence), `.venv/Scripts/python.exe -m scripts.diff_simbolos_nucleo_motor --rodada <rodada E03> --saida <checkout principal>/tmp/laboratorio/e06-3-2-2/<hipotese>/diff-<k> --processos 6`, só para ler o `gasto` por página (o núcleo e o gasto já recebem todas as habilitadas; a comparação mostra a haste como "só no núcleo" até a Task 2, e isso aqui não importa).
- **Métrica:** por classe (`centro`), tp/fp/fn de ATERRAMENTO e PARA_RAIOS_MT em `total.modelo.centro.por_classe`, contra R-4; `total.modelo.centro.leituras_erradas.por_classe` dessas duas classes; tempo máximo por folha; gasto máximo do orçamento por folha (`gasto.total` do diff) e páginas com `gasto_motivo`.
- **Vitória:** R-4 nas duas classes, leitura errada afirmada = 0 nelas, positivos e negativos sintéticos verdes, gasto máximo ≤ 200.000 por folha e nenhuma página `teto_consultas`. Desempate: soma dos F1 das duas classes, depois o menor tempo máximo por folha.
- **Parada:** 60 min por hipótese, ou vitória com margem de 2 tp em cada classe.
- **Entrega:** em `<checkout principal>/tmp/laboratorio/e06-3-2-2/<hipotese>/`: `patch.diff` (contra a base), `metricas.json` por iteração e `conclusoes.md` (o que mudou, falsos positivos vistos por tipo, sem coordenada de folha real no patch).
- **Seleção:** pela métrica, com ruling no ledger. Se nenhuma vencer, a ruling registra a melhor e o déficit, e a Task 1 parte dela; o critério 2 vira impedimento real se a Task 6 não fechar. Se vencer H-A, R-9.

## Resultado do laboratório (2026-11-07)

- H-A: ATERRAMENTO 6/20/37, PARA_RAIOS_MT 0/0/13 (os grupos quebram a unidade: só 27 de 65 hastes têm haste e barras no mesmo grupo). Descartada.
- H-B: 41/20/2 e 10/4/3, gasto máximo 611.402 (acima de 200.000). Descartada.
- **H-C, escolhida:** 41/7/2 e 10/4/3, gasto máximo 191.334, sem `teto_consultas`, até 26,6 s por folha sob carga. O sinal da página (texto em glifo) é um proxy da escala do símbolo (haste de 4 a 6 pt), e R-10 se aplica. Patch em `tmp/laboratorio/e06-3-2-2/h-c/patch.diff` do checkout principal.
- **Triagem** (`tmp/laboratorio/e06-3-2-2/h-c/triagem/`): os 5 FN restantes são referências com rótulo trocado na ficha congelada:
  - 006 `P8-para-raios`, 010 `b-P1-circulo-norte` e 012 `P8-pr-2` estão rotuladas PARA_RAIOS_MT sobre um desenho que não tem 4 barras alternadas;
  - 006 `P8-aterramento-1` e 010 `b-P1-aterramento-oval-sul` estão rotuladas ATERRAMENTO sobre 4 barras alternadas;
  - o `atual` também não casa nenhuma delas.
- **Leituras erradas** (17 pares):
  - 5 são essas trocas;
  - 8 são o terra real na ponta de estai;
  - 2 são uma haste real na borda da caixa de uma chave;
  - 2 são leitura errada de fato: 011, X falso formado pelos traços do para-raios.
- **Critério aplicado** (ruling no ledger, desvio previsto em R-4):
  - por classe, o recall é calculado sem as 5 referências trocadas, nos dois métodos, e precisa ser ≥ o do `atual`;
  - a precisão (bruta) precisa ser estritamente maior que a do `atual`;
  - as leituras erradas **de fato** precisam ser 0, com a triagem refeita sobre o patch final;
  - as referências trocadas vão à curadoria.
  - Para PARA_RAIOS_MT, a Task 1 precisa cortar ao menos um FP que não seja troca (X falso, colados).

## Tasks

### Task 1: Gramática de haste com barras

**Estimativa:** 45 min · **Depende de:** laboratório · **Risco:** alto · **Laboratório:** sim (parte do patch vencedor)

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`
- Create: `tests/fixtures/symbol_grammars/stem_bars.py`, `tests/unit/test_grammar_stem.py`
- Modify: `tests/unit/test_gramatica_so_modelo_ataque.py` (só `test_modelo_ainda_nao_executa_stem_bars_e_falha_alto`), `tests/unit/test_gasto_por_fase_ataque.py` (só o oráculo)

**Interfaces:**
- Consumes: `ContextoGramatica` (grades, orçamento); `CasamentoGramatica.componentes`; construtores de `tests/fixtures/symbol_grammars/paginas.py`.
- Produces: `grammar_stem.casa_hastes(contexto: ContextoGramatica, gramatica: Mapping[str, Any]) -> list[tuple[Caixa, int, tuple[int, ...]]]` (caixa visual do pictograma, R-3; posição do caminho que ancora o símbolo; componentes), sem efeito colateral fora do orçamento; toda consulta paga do orçamento. `_casar_no_contexto` despacha explicitamente por `kind` (`terminal_disc`, `stem_bars` e os tipos de moldura) e levanta `ValueError` em `kind` desconhecido, preenchendo `componentes`. A fixture exporta `CASOS_HASTE: tuple[tuple[str, dict[str, Any]], ...]` (id de cada uma das 8 variantes e a gramática dela, com o `max_span` do laboratório) e as funções de desenho que as Tasks 3 e 5 usam.

- [ ] **Step 1: Escrever a fixture e os testes**, partindo do patch vencedor. A fixture desenha com PyMuPDF (cor comum, sem copiar folha real, sem a string `.pdf`): haste com 3 barras decrescentes; com 4 alternadas; cada uma com elipse envolvente, com X, com os dois; giradas 90° e 45°; haste encostada numa linha longa do mesmo estilo; página com `/Rotate` 90. Negativos: 3 barras iguais; 2 barras; barras não perpendiculares; espaçamento fora da faixa; hachura de 6 traços paralelos sem haste; texto em glifo `E` e `≡` desenhado como caminho; barras de cor diferente da haste. Em `test_grammar_stem.py`, pelo núcleo (`pagina_para_gramaticas` + `casar_variantes` com as 8 variantes de `CASOS_HASTE`):
  - `test_positivo_casa_so_a_variante_certa`, parametrizado pelos 8 positivos × 3 rotações: exatamente uma variante, a esperada;
  - `test_caixa_e_o_pictograma`: a caixa contém barras, envolvente (quando há) e a ponta da haste, e não a haste inteira nem o X fora da envolvente; com a haste encostada na linha longa, a caixa é a mesma da haste curta, a menos de 0,5 pt;
  - `test_negativo_nao_casa`, parametrizado pelos negativos;
  - `test_componentes_listam_haste_barras_e_x`;
  - `test_kind_desconhecido_recusa`;
  - em `test_gramatica_so_modelo_ataque.py`, `test_modelo_ainda_nao_executa_stem_bars_e_falha_alto` vira `test_modelo_executa_stem_bars`: com uma variante `stem_bars` habilitada (pacote em `tmp_path`), `observar_pacotes_modelo` numa página com o positivo dela observa uma vez a classe dela, sem erro;
  - em `test_gasto_por_fase_ataque.py`, remova o oráculo do corpo antigo de `casar_variantes` (`_casar_antigo`) e os testes que dependem só dele, mantendo `test_fases_nao_negativas_e_somam_o_gasto_do_orcamento`.
- [ ] **Step 2: Rodar** e conferir que os novos falham sem o patch e passam com ele.
- [ ] **Step 3: Implementar** a partir do patch, só nos dois arquivos de produção.
- [ ] **Step 4: Rodar** os testes novos, `tests/unit/test_symbol_matcher*.py`, `tests/unit/test_gramatica_so_modelo*.py`, `tests/unit/test_gasto_por_fase*.py`, `tests/unit/test_grammar_*`, `tests/unit/test_model_symbols.py`, ruff, format, mypy e `scripts/complexity_gate.py src`; e o benchmark do laboratório com `--metodo modelo` (com as 8 variantes habilitadas só no worktree, sem commitar o JSON), colando no relatório os blocos de ATERRAMENTO e PARA_RAIOS_MT e as leituras erradas.
- [ ] **Step 5: Commit** (`feat: gramatica de haste com barras no nucleo`).

### Task 2: Matriz e diff para tipo só do modelo

**Estimativa:** 25 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `scripts/coverage_matrix_e16.py`, `tests/unit/test_e16_coverage_matrix.py`
- Modify: `scripts/diff_simbolos_nucleo_motor.py`, `tests/unit/test_diff_simbolos_nucleo_motor.py`

**Interfaces:**
- Consumes: `declarative_symbols.GRAMATICAS_SO_MODELO`, `variantes_do_motor`, `_enabled`; a gramática `stem_bars` executável (Task 1).
- Produces: no diff, o motor observa com os pacotes (ele mesmo filtra por `variantes_do_motor`), o núcleo (`observar_pacotes_modelo`) e o gasto (`_medir_gasto`) recebem **todas** as habilitadas, e a comparação núcleo × motor considera só as variantes de `variantes_do_motor`; as do modelo ficam fora de `ambos`/`so_*` (e o docstring diz isso).

- [ ] **Step 1: Escrever os testes**, com pacotes sintéticos em `tmp_path`:
  - `test_variante_so_do_modelo_fica_fora_do_dominio_no_motor` (R-5): variante E04 habilitada com `stem_bars` → `declarative-vector-packages` = `fora_do_dominio`, status `nao_avaliavel`; variante E07 habilitada `label_in_frame` continua `id_exato_sintetico`;
  - no diff, numa página sintética com uma moldura positiva e uma haste positiva (fixture da Task 1): a haste não aparece em `ambos` nem em `so_*`, a moldura continua em `ambos`, e o `gasto.gramaticas` é maior que o da mesma página sem a variante `stem_bars`. `recursos()` é `@cache` por processo e lê os pacotes reais: o teste faz monkeypatch de `diff.recursos` com um `Recursos` montado dos pacotes em `tmp_path` e chama `recursos.cache_clear()` antes e depois (fixture), para não depender da ordem sob xdist.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar** R-5 na matriz e o diff como em Produces.
- [ ] **Step 4: Rodar** os dois arquivos de teste, `tests/unit/test_diff_simbolos_nucleo_motor_ataque.py`, `tests/unit/test_curation_coverage_e16*.py`, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: matriz e diff tratam gramatica so do modelo`).

### Task 3: Observação com componentes, versão e digest

**Estimativa:** 30 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/model_symbols.py`
- Modify: `src/zeny_project_handler_server/symbol_execution.py`
- Modify: `tests/unit/test_model_symbols.py`, `tests/integration/test_model_symbols_runner.py`

**Interfaces:**
- Consumes: `CasamentoGramatica.componentes`, `grammar_stem`, as funções de desenho de `tests/fixtures/symbol_grammars/stem_bars.py`.
- Produces: `_VERSAO = "1.1.0"`; observação com uma primitiva por caminho do casamento (R-3); todo módulo do fecho de imports de `model_symbols` no digest do runner.

- [ ] **Step 1: Escrever os testes:**
  - em `test_model_symbols.py`: `test_observacao_tem_uma_primitiva_por_caminho` (casamento com `componentes=(5, 9)` → 3 primitivas com os índices crus das posições, em ordem, a camada de cada caminho e `pontos_originais` no espaço cru, conferido numa página `/Rotate` 90), `test_sem_componentes_continua_com_uma_primitiva`, `test_versao_1_1_0`;
  - em `test_model_symbols_runner.py`: `test_digest_cobre_o_fecho_de_imports` no lugar da lista `_MODULOS_DO_DIGEST` (todo módulo de `zeny_project_handler.adapters.analysis` importado, direta ou transitivamente, por `model_symbols` está no digest); `test_haste_funde_com_o_legado`, parametrizado por haste curta, haste encostada numa linha longa, X sem envolvente e página com `/Rotate` 90 (pacotes com a variante correspondente habilitada em `tmp_path`): o runner reconcilia legado e modelo numa só ocorrência, a geometria escolhida da ocorrência é o pictograma (a menos de 0,5 pt) e a geometria de suporte continua vindo do legado.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.** Todo módulo que o fecho apontar entra no digest (por exemplo `drawing_model/model.py`); a assinatura do runner muda (cache miss opt-in, esperado). Se `run` ou `_cache_complete` passarem de CC 30, extraia função antes. Se a fusão falhar pela geometria do pictograma, reporte DONE_WITH_CONCERNS com os números de `_same_occurrence` (centro, tamanho, IoU), sem afrouxar a reconciliação.
- [ ] **Step 4: Rodar** os dois arquivos, `tests/server/` filtrado por `symbol`, ruff, format, mypy e `scripts/complexity_gate.py src`.
- [ ] **Step 5: Commit** (`feat: observacao com componentes e versao 1.1.0 do metodo sobre o modelo`).

### Task 4: Habilitação das variantes de haste

**Estimativa:** 35 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-19.json` (v001–v004), `family-f02-21.json` (v005–v008)
- Modify: `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py`, `tests/unit/test_gramatica_so_modelo_ataque.py` (só os 3 testes com pacotes reais)

**Interfaces:**
- Consumes: `CASOS_HASTE` (Task 1) — se a fixture não exportar com esse nome, devolva ao orquestrador.
- Produces: 30 `enabled` e 393 `pending`.

- [ ] **Step 1: Atualizar os testes:**
  - `test_enabled_status_is_distinct_from_registered_coverage` com habilitadas = `_ENABLED_IDS` ∪ ids de `CASOS_HASTE` e as de `CASOS_HASTE` com tipo em `GRAMATICAS_SO_MODELO` (os testes que rodam o motor antigo sobre `ENABLED_CASES` não mudam);
  - `test_gramatica_real_das_hastes_igual_a_casos_haste`: a gramática de cada uma das 8 no JSON é igual à de `CASOS_HASTE`;
  - contagens `(393, 30)` no auditor e `== 30`/`== 393` na tabela de suporte (`test_e14_symbol_review.py:287-288` e `test_pacotes_classes_da_ficha.py`); o golden das variantes antigas muda só nas 8 (de `pending` com `reason` para `enabled` com `grammar` e `negative_examples`);
  - em `test_gramatica_so_modelo_ataque.py`, inverter `test_variantes_do_motor_com_pacotes_reais_igual_a_enabled`, `test_perfil_do_modelo_com_pacotes_reais_igual_ao_do_motor` e `test_perfil_do_modelo_com_pacotes_reais_herda_todos_os_parametros_do_motor`: com os pacotes reais, o motor fica com as habilitadas menos `GRAMATICAS_SO_MODELO` (22) e o modelo anuncia também ATERRAMENTO e PARA_RAIOS_MT (30), com os demais parâmetros iguais.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Habilitar** as 8 variantes com a gramática de `CASOS_HASTE` e `negative_examples` = os `confusable_negatives` do inventário, sem `reason`.
- [ ] **Step 4: Rodar** os testes alterados, `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`, `enabled` 30), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py`, `tests/unit/test_model_symbols.py` (a paridade modelo × motor no corpus habilitado é um negativo da haste contra as 22 molduras e discos), ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: habilita aterramento e para-raios MT sobre o modelo`).

### Task 5: Teto, guarda e pureza

**Estimativa:** 20 min · **Depende de:** Task 1 · **Risco:** normal · **Laboratório:** não

**Files:**
- Create: `tests/unit/test_grammar_stem_teto.py`
- Modify: `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py`

**Interfaces:**
- Consumes: `grammar_stem`; os construtores puros de `tests/fixtures/symbol_grammars/paginas.py` (`pagina_gramatica`, `linha`) para a página hostil, sem PyMuPDF.

- [ ] **Step 1:** `test_pagina_hostil_estoura_o_orcamento` (20.000 traços curtos paralelos e limite pequeno → `TetoGramaticasExcedido`) e `test_gasto_cresce_linear_com_hastes` (gasto de 10 e de 100 hastes isoladas, razão ≤ 15, contagem de trabalho e não tempo de parede); `test_gramaticas_novas_passam_na_guarda` aplica `_violacoes_de_texto` ao fonte de `grammar_stem.py` e de `tests/fixtures/symbol_grammars/stem_bars.py`; `grammar_stem` entra na tupla de `test_modulos_do_nucleo_nao_importam_pymupdf`.
- [ ] **Step 2: Rodar** os três arquivos; se o teto ou a linearidade falharem, reporte DONE_WITH_CONCERNS com a saída (é defeito de produção da Task 1, não do teste).
- [ ] **Step 3: Commit** (`test: teto, guarda e pureza da gramatica de haste`).

### Task 6: Medição nas 16 folhas (orquestrador)

**Estimativa:** 25 min · **Depende de:** Tasks 1 a 5 · **Risco:** normal · **Laboratório:** não

Sem código: o orquestrador roda, na branch da etapa com as Tasks 1–5 integradas, com `<rodada E03>` = `<checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas` e `--processos 10`:
- [ ] `python -m scripts.benchmark_simbolos_ficha --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2-2/simbolos --metodo atual --metodo modelo --processos 10` → R-4 nas duas classes e leituras erradas = 0 nelas; `atual` igual ao congelado; o bloco `modelo` das outras classes igual, por folha, ao congelado. Falha vira rodada de correção da Task 1 (e repete o benchmark).
- [ ] `python -m scripts.diff_simbolos_nucleo_motor --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2-2/diff --processos 10` → contra `tmp/e06-2-2-2/diff/diff-nucleo-motor.json` (sha256 `20f3b708…`), pela chave natural `(pdf_id, página, variante, índice cru)`: `ambos` 29 e `so_*` 0 nas variantes do motor; gasto máximo por folha ≤ 200.000 e nenhuma página `teto_consultas`, com o valor no handoff.
- [ ] `python -m scripts.audit_symbol_packages` → `errors: []`, 30 `enabled`.

## Fechamento operacional

- Suíte inteira por onda; testador de etapa (a Task 5 é de risco normal) sobre `MERGE_BASE..HEAD`; `osv-scanner` nos 7 locks; `check_test_integrity --base <MERGE_BASE>`; revisão final; `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` (conferir a data do `relatorio-testes.txt`).
- Handoff com: tabela do benchmark, leituras erradas, gasto, diff contra o congelado; "Decisões para o usuário" com R-5, R-6 (entrevista no fim do lote) e R-7 (escopo da fusão); os blocos "Para a E06.3.3" (tipo só do modelo, pictograma e componentes para as molduras de para-raios BT e transformador), "Para a E07" (fusão com o legado provada só em fixture sintética) e "Para a E09".

## Revisão de arquitetura

- **Veredito:** aprovado com notas, na rodada 1 (`revisor-arquitetura`, opus). Rodada 0: bloqueado, 4 Importantes (testes quebrados fora dos Files, dependência oculta da Task 2, gasto não medido, caminho da H-A fora da File Structure) e 7 Menores, todos corrigidos. Este plano parte de um rascunho revisado nas rodadas 0 e 1 da E06.3.2, antes da divisão.
- **Modelo:** opus.
- **Notas Menores da rodada 1:** N-1 aplicada (o teste do diff injeta `Recursos` e limpa o `@cache`); N-2 (Task 1 no teto de 45 min com a remoção do oráculo): se o laboratório entregar pouco teste reaproveitável, os negativos de glifo `E` e `≡` vão para a Task 5, com ruling.
- **Decisão de arquitetura para o usuário (entrevista no fim do lote):** R-6.
