# E06.3.2 — Aterramento, para-raios MT e H2: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reconhecer ATERRAMENTO e PARA_RAIOS_MT sobre o modelo de desenho com uma gramática nova de haste com barras, acima do analisador atual nas 16 folhas, e confirmar ou refutar a H2 com a contagem de resíduos raster por folha.

**Architecture:** a gramática `stem_bars` vive num módulo novo do núcleo puro (`drawing_model/grammar_stem.py`) e só o método sobre o modelo (`declarative-drawing-model`) a executa: o motor antigo (`declarative-vector-packages`, que sai na E09) aceita o tipo na validação dos pacotes, mas o ignora ao observar (R-1). O casamento passa a carregar todos os caminhos do símbolo (haste e barras), para a reconciliação do runner fundir a ocorrência com a do detector legado. As 8 variantes de f02-19 (ATERRAMENTO) e f02-21 (PARA_RAIOS_MT) são habilitadas. A H2 é medida por um script novo que chama `residuos_raster` folha a folha e cruza cada resíduo com as referências da ficha.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só nos adaptadores e scripts), JSON, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3" (objetivo, escopo, notas, riscos) e "E06.3.2"; os blocos "Para a E06.3" dos handoffs da E06.2.1, E06.2.2.1, E06.2.2.2 e E06.3.1; ADR 0016; `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` e `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md` (laboratório); o levantamento `tmp/e06/levantamento-e06.md` do checkout principal (§1, §3, §10).

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o núcleo `drawing_model/` (salvo `pymupdf_drawing_model.py`, fora dele) não importa PyMuPDF; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- A saída da análise continua `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`; nenhuma migração SQLite; nenhuma mudança de API ou DTO.
- Mudança de comportamento de saída incrementa a versão do método correspondente (ADR 0006): `declarative-drawing-model` 1.0.0 → 1.1.0 (Task 4).
- PDFs reais, recortes, rótulos e conjuntos de dados nunca entram no Git. Todo comportamento novo tem fixture sintética autoral positiva e negativa; nenhuma coordenada, hash ou nome de folha real em código, pacote ou teste (guarda da E06.1, estendida na Task 3).
- Leitura de avaliação é sempre cega. Nada lê `examples/avaliacao-cega/`. As referências da rodada E03 (`tmp/curadoria-simbologia/20261103-2300-fichas/`) estão congeladas e não são editadas; leitores visuais não participam.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos. Testes sem dependência de ordem, cwd, porta ou arquivo fixo (use `tmp_path`). mypy strict, ruff check, ruff format, complexidade < 31 (Radon) em `src`.
- O método sobre o modelo liga só no `SymbolCompositionRunner` opt-in (D12). O analisador padrão não muda.
- Documentação enxuta: nada de histórico de execução em arquivo versionado.
- Não tocar `scripts/benchmark_ficha_poste.py` (E15) nem `tests/conftest.py`.
- Worktree da etapa: `.venv/Scripts/python.exe`. Em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` do worktree da etapa, a partir da raiz do worktree da tarefa; a suíte inteira usa `-n` = 20 ÷ suítes ativas (o despacho informa o número).

## Review Focus

1. Pacote com variante `enabled` de tipo `stem_bars` carregado pelo motor antigo → carrega sem erro e o motor não a observa nem a conta em `classes_suportadas`; o perfil do método sobre o modelo a conta (Task 1).
2. Haste com barras encostada numa linha longa da rede (vão, cabo) do mesmo estilo → ainda casa; três ou quatro traços paralelos que não são barras de haste (hachura, cerca, texto em glifo como `E` ou `≡`) → não casam (Task 3).
3. Página com símbolo girado (0°, 90°, 45°) e página com rotação de página `/Rotate` 90 → mesma variante, caixa coerente na página exibida (Tasks 3 e 4).
4. Página hostil com milhares de segmentos curtos paralelos → `TetoGramaticasExcedido` pelo orçamento, nunca laço sem teto (Task 3).
5. Resíduo raster em página `FORA_DOMINIO` → fica fora da contagem por folha, com o motivo, e não vira "0 resíduos" (Task 2).

## Decisões do plano

- **R-E06.3.2-1, tipo só do modelo:** `stem_bars` entra em `declarative_symbols._GRAMMARS` e no validador de campos, e numa constante pública nova `GRAMATICAS_SO_MODELO = frozenset({"stem_bars"})`. O motor antigo observa e anuncia só `variantes_do_motor(pacotes)` (habilitadas fora de `GRAMATICAS_SO_MODELO`); `_enabled` continua devolvendo todas as habilitadas, para o núcleo. Assim o motor antigo não muda de saída (só o sha dos pacotes, que já muda a cada alteração de pacote) e não ganha um porte que a E09 removeria. O diff núcleo × motor (`scripts/diff_simbolos_nucleo_motor.py`) compara só `variantes_do_motor`, senão toda haste viraria "só no núcleo". Descartado: implementar a gramática também no motor antigo (trabalho jogado fora na E09).
- **R-E06.3.2-2, campos da gramática** (exatos; a validação recusa outros): `{"kind": "stem_bars", "bars": 3 | 4, "taper": "decreasing" | "alternating", "enclosure": "none" | "ellipse", "removal_mark": bool, "max_span": número em (0, 72]}`. `bars`/`taper` separam as classes (ATERRAMENTO 3 `decreasing`, PARA_RAIOS_MT 4 `alternating`); `enclosure` e `removal_mark` separam as quatro variantes de situação (base `none`/false; envolvente `ellipse`/false; envolvente e X `ellipse`/true; X sem envolvente `none`/true). As quatro de uma classe são mutuamente exclusivas por construção: um mesmo desenho casa no máximo uma. A cor não decide nada ("Não inferir estado por cor isolada", inventário). Os limiares geométricos são constantes do módulo, escolhidos pelo laboratório.
- **R-E06.3.2-3, casamento com vários caminhos:** `CasamentoGramatica` ganha `componentes: tuple[int, ...] = ()`, as posições em `modelo.caminhos` dos demais caminhos do símbolo, sem repetir `caminho`, em ordem crescente. As gramáticas atuais deixam vazio. A observação ganha uma `PrimitivaObservadaSimbolo` por caminho (`caminho` e cada componente), com o índice cru e a camada de cada um; `pontos_originais` de cada primitiva é a caixa daquele caminho. Assim `_same_occurrence` acha as primitivas compartilhadas com o legado.
- **R-E06.3.2-4, critério de aceite "maiores que os do atual":** por classe, precisão **e** recall estritamente maiores que os do `atual`, critério `centro`, com as mesmas referências (linha de base congelada `tmp/e06-2-2-2/simbolos/simbolos-ficha.json`, sha256 `b6a3118d…6008d`): ATERRAMENTO > 56,2% de precisão (41/73) e > 95,3% de recall (41/43); PARA_RAIOS_MT > 71,4% (10/14) e > 76,9% (10/13). E **leitura errada afirmada = 0**: nenhuma predição de uma das duas classes com centro na caixa de uma referência da outra. Se o laboratório mostrar que uma referência perdida não é desenhável pelo vetor (resíduo raster, H2), a ruling vai ao handoff antes de afrouxar qualquer número.
- **R-E06.3.2-5, matriz da curadoria:** variante habilitada com tipo em `GRAMATICAS_SO_MODELO` tem `declarative-vector-packages` = `fora_do_dominio` em `scripts/coverage_matrix_e16.py`, porque o motor antigo não a executa; a matriz não ganha coluna nova (é contrato da curadoria e a rodada seguinte decide). O status de variante E04 continua `nao_avaliavel` (`:194-196`): o ganho aparece no benchmark por ficha, não na matriz. Vai para "Decisões para o usuário".
- **R-E06.3.2-6, sinal "Exclusivo" no runner opt-in:** com a haste habilitada, uma ocorrência de ATERRAMENTO ou PARA_RAIOS_MT vista pelo legado e pelo método novo funde e passa a "Suportado". Aqui são dois algoritmos independentes (o legado de `pymupdf_symbols` e a gramática nova), e não dois portes da mesma regra: o rótulo é verdadeiro. Fica aceito, sem mudança de produção; vai para "Decisões para o usuário".
- **R-E06.3.2-7, H2:** é confirmada se nenhum resíduo das 16 folhas for símbolo da rede, pela triagem visual dos recortes (o orquestrador lê os PNG; resíduo com hash repetido é triado uma vez) e pelo cruzamento com as referências (resíduo cuja caixa contém o centro de uma referência de símbolo que nenhum método vetorial casou é candidato a símbolo raster). Página `FORA_DOMINIO` não conta como zero.
- **R-E06.3.2-8, pendências herdadas:** o oráculo de `tests/unit/test_gasto_por_fase_ataque.py` (cópia do corpo antigo de `casar_variantes`) é removido na Task 3, que muda os helpers do casador, como o handoff da E06.2.2.2 manda; `_MODULOS_DO_DIGEST` (cópia manual) vira teste de fecho por imports na Task 4. Ficam para depois, com ruling no handoff: promover os privados de `grammar_disc` (a E06.3.3 mexe em `grammar_frames`), `runner._package_prediction` público (o benchmark não muda aqui), recortes e fila do diff (não há "só no núcleo" a classificar com R-1).
- **R-E06.3.2-9, se o laboratório escolher H-A (grupo como unidade):** quem consome `grupos` adiciona `modelo.grupos_falhou` às fontes consumidas (`symbol_grammars._FONTES_CONSUMIDAS`), põe `LIMITE_VISITAS_AGRUPAMENTO` nos `parametros` do perfil (Task 4) e revê R-1 da E06.2.2.1 (subir `VERSAO_MODELO_DESENHO`). Com H-B ou H-C, nada disso se aplica.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/declarative_symbols.py` | `stem_bars` na validação, `GRAMATICAS_SO_MODELO`, `variantes_do_motor` no motor | 1 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` | `CasamentoGramatica.componentes` (1); despacho de `stem_bars` (3) | 1, 3 |
| `scripts/diff_simbolos_nucleo_motor.py` | compara só `variantes_do_motor` | 1 |
| `tests/unit/test_gramatica_so_modelo.py` (novo) | validação, motor ignora, perfil do modelo conta | 1 |
| `scripts/residuos_raster_folhas.py` (novo) | H2: resíduos por folha, cruzamento com a ficha, recortes | 2 |
| `tests/unit/test_residuos_raster_folhas.py` (novo) | rodada sintética em `tmp_path` | 2 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py` (novo) | gramática de haste com barras | 3 |
| `tests/fixtures/symbol_grammars/stem_bars.py` (novo) | desenhos sintéticos positivos e negativos da haste | 3 |
| `tests/unit/test_grammar_stem.py` (novo) | gramática pelo núcleo, positivos, negativos, teto | 3 |
| `tests/unit/test_symbol_packages_sem_memorizacao.py` | guarda estendida a `grammar_stem.py` | 3 |
| `tests/unit/test_gasto_por_fase_ataque.py` | oráculo removido (R-8) | 3 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | primitivas por componente, versão 1.1.0 | 4 |
| `src/zeny_project_handler_server/symbol_execution.py` | `grammar_stem` no digest (e `model.py`, se o fecho pedir) | 4 |
| `tests/integration/test_model_symbols_runner.py` | fecho por imports no lugar de `_MODULOS_DO_DIGEST`; fusão com o legado | 4 |
| `tests/unit/test_model_symbols.py` | primitivas por componente, versão | 4 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-19.json`, `family-f02-21.json` | 8 variantes habilitadas | 5 |
| `scripts/coverage_matrix_e16.py`, `tests/unit/test_e16_coverage_matrix.py` | R-5 | 5 |
| `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py:287-288` | contagens 22→30 e 401→393; habilitadas = casos do motor ∪ casos só do modelo | 5 |

Ondas: Onda 1, Tasks 1 e 2; laboratório (sobre a Task 1 integrada); Task 3; Onda 2, Tasks 4 e 5; Task 6 (medição, orquestrador).

Soma das tarefas: 3h00 (30 + 35 + 45 + 30 + 40), mais o laboratório (caixa de 60 min, em paralelo) e a medição (~20 min). Parede estimada com as ondas: ~3h15. Fica sem divisão (ruling no ledger): dividir somaria um plano, uma revisão final e um `.bat` a mais, e o estouro de 4h30 do protocolo continua valendo.

## Laboratório (antes da Task 3)

- **Base:** a branch da etapa com a Task 1 integrada. Cada hipótese: um `desenvolvedor` com `isolation: "worktree"`, sem commit e sem a suíte inteira, que implementa `grammar_stem.py`, o despacho no casador e a habilitação das 8 variantes (R-2), e mede.
- **Hipóteses:**
  - **H-A, grupo como unidade:** a gramática roda por `GrupoCandidato` de `modelo.grupos`; a haste e as barras precisam estar no mesmo grupo. R-9 se aplica.
  - **H-B, segmento como semente e consulta espacial:** cada `Segmento` de `contexto.grade_segmentos` com comprimento plausível de haste consulta a grade num raio proporcional a ele, como o legado (`pymupdf_symbols._ground_and_mt_arrester_matches`), incluindo traço longo cortado na caixa.
  - **H-C, H-B com limiares por família:** os mesmos passos de H-B, com tolerâncias escolhidas por um sinal da própria página (origem dos `TextoModelo`: glifo, SHX ou nativo), sem ler o documento. Exige fixture sintética por família.
- **Comando** (no worktree da hipótese, com o `.venv` do worktree da etapa e `PYTHONPATH=<worktree>/src`; `--processos 6` com as três hipóteses rodando):
  `.venv/Scripts/python.exe -m scripts.benchmark_simbolos_ficha --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/laboratorio/e06-3-2/<hipotese>/iter-<k> --metodo modelo --processos 6`
- **Métrica:** tp/fp/fn por classe (critério `centro`) de ATERRAMENTO e PARA_RAIOS_MT contra a linha de base `atual` (R-4), leitura errada afirmada, tempo por folha e gasto máximo do orçamento por folha (de `gasto_por_fase`).
- **Vitória:** R-4 nas duas classes, leitura errada afirmada = 0, positivos e negativos sintéticos do Review Focus 2 verdes, gasto máximo ≤ 200.000 consultas por folha (R-E06.2.2.2-4). Desempate: soma dos F1 das duas classes, depois menor tempo máximo por folha.
- **Parada:** 60 min por hipótese, ou vitória com margem de 2 tp em cada classe.
- **Entrega:** em `<checkout principal>/tmp/laboratorio/e06-3-2/<hipotese>/`: `patch.diff` (contra a base), `metricas.json` por iteração e `conclusoes.md` (o que mudou entre iterações, falsos positivos vistos por tipo, sem coordenada de folha real no patch).
- **Seleção:** pela métrica, com ruling no ledger. Nenhuma vence: a ruling registra a melhor e o déficit, e a Task 3 parte dela; o critério 2 fica como impedimento real se a Task 6 não fechar.

## Tasks

### Task 1: Tipo de gramática só do modelo

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` (só o campo)
- Modify: `scripts/diff_simbolos_nucleo_motor.py`
- Create: `tests/unit/test_gramatica_so_modelo.py`

**Interfaces:**
- Produces: `declarative_symbols.GRAMATICAS_SO_MODELO: Final[frozenset[str]]`; `declarative_symbols.variantes_do_motor(pacotes: tuple[Package, ...]) -> tuple[tuple[Package, Package], ...]`; validação de `stem_bars` conforme R-2; `perfil_pacotes` e `observar_pacotes` usam `variantes_do_motor`; `CasamentoGramatica.componentes: tuple[int, ...] = ()`.

- [ ] **Step 1: Escrever os testes** em `test_gramatica_so_modelo.py`, com pacotes sintéticos escritos em `tmp_path` e carregados por `carregar_pacotes(packages_dir=tmp_path)`:
  - `test_stem_bars_valido_carrega` (as quatro combinações de R-2 para `bars` 3/`decreasing` e 4/`alternating`);
  - `test_stem_bars_invalido_recusa`, parametrizado: campo a mais, `bars` 2 ou 5, `taper` desconhecido, `enclosure` desconhecido, `removal_mark` não booleano, `max_span` 0, 73 ou booleano → `ValueError`;
  - `test_motor_ignora_variante_so_do_modelo`: um pacote com uma variante `label_in_frame` e uma `stem_bars` habilitadas; `perfil_pacotes(...).classes_suportadas` não contém a classe da `stem_bars`, `("enabled_variants", 1)` nos parâmetros, e `observar_pacotes` numa página PyMuPDF em branco não falha;
  - `test_enabled_continua_com_todas`: `_enabled` devolve as duas;
  - `test_casamento_sem_componentes_por_padrao`.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar** em `declarative_symbols.py` e o campo em `symbol_matcher.py`; no diff, troque `_enabled` por `variantes_do_motor` nos dois lados (e na docstring).
- [ ] **Step 4: Rodar** o arquivo novo, `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_symbol_matcher_paridade.py`, os testes do diff (`tests/unit/test_diff_simbolos_nucleo_motor*.py`) e `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`); ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: tipo de gramatica so do modelo de desenho`).

### Task 2: Medição da H2 por folha

**Estimativa:** 35 min · **Depende de:** nenhuma · **Risco:** normal · **Laboratório:** não

**Files:**
- Create: `scripts/residuos_raster_folhas.py`
- Create: `tests/unit/test_residuos_raster_folhas.py`

**Interfaces:**
- Consumes: `model_symbols.residuos_raster`, `pagina_para_gramaticas`, `casar_variantes`, `_enabled`; o mapa de folhas de `scripts/simbolos_corpus.py` (mesma guarda de `avaliacao-cega` e mesma conferência de sha do benchmark).
- Produces: CLI `python -m scripts.residuos_raster_folhas --rodada DIR --saida DIR [--recortes] [--dpi 200] [--processos N]`; `saida/residuos-raster.json` no esquema `residuos-raster-v1`: `{"esquema", "rodada", "folhas": [{"pdf_id", "paginas": [{"pagina", "estado": "medida" | "fora_dominio", "motivo", "residuos": [{"caixa_normalizada", "sha256_curto", "de_anotacao", "referencias_sob": [classe, ...], "recorte": "<nome>.png" | null}]}], "total": int | null}], "resumo": {"folhas_medidas", "folhas_fora_dominio", "residuos", "por_hash": {sha256_curto: n_folhas}, "sobre_referencia": n}}`. `total` é `null` quando alguma página da folha é `fora_dominio`. Sem nome de PDF nem caminho na saída, só o id da rodada.

- [ ] **Step 1: Escrever os testes** sobre uma rodada sintética em `tmp_path` (2 PDFs gerados pelo PyMuPDF, com `rodada.json` e `ficha/referencia.json` no formato da E03; um PDF com uma imagem compacta inserida sobre a caixa de uma referência de símbolo e outra longe; o outro sem imagem):
  - `test_conta_residuos_por_folha` (2 e 0) e `test_cruza_com_referencia` (`referencias_sob == ["ATERRAMENTO"]` só na imagem sobre a referência);
  - `test_pagina_fora_dominio_nao_vira_zero`: monkeypatch de `casar_variantes` levantando `TetoGramaticasExcedido` → `estado == "fora_dominio"`, `total is None`;
  - `test_recortes_gravados` com `--recortes` (PNG existe, nome sem o do PDF) e `test_saida_sem_caminho_nem_nome_de_pdf`;
  - `test_recusa_avaliacao_cega` (rodada apontando para `avaliacao-cega`, como no benchmark);
  - `test_processos_da_o_mesmo_resultado` (`--processos 1` e `2`).
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.** Por página: `pagina_para_gramaticas(pagina, indice, tabela)`, `casar_variantes` com as variantes habilitadas dos pacotes carregados uma vez por folha, `residuos_raster(pagina, casamentos)`; `FonteGramaticaFalhou`, `TetoGramaticasExcedido` e `modelo.caminhos_falhou` dão `fora_dominio` com o motivo. Recorte por `page.get_pixmap(clip=<caixa crua>, dpi=dpi)`, com a caixa crua vinda da derrotação, como `model_symbols._observacao`. Paralelismo como `scripts/benchmark_simbolos_ficha.py` (`ProcessPoolExecutor`, ordem serial).
- [ ] **Step 4: Rodar** o arquivo de teste, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: medicao de residuos raster por folha (H2)`).

### Task 3: Gramática de haste com barras

**Estimativa:** 45 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** sim (parte do patch vencedor)

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`
- Create: `tests/fixtures/symbol_grammars/stem_bars.py`, `tests/unit/test_grammar_stem.py`
- Modify: `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_gasto_por_fase_ataque.py`

**Interfaces:**
- Consumes: `ContextoGramatica` (grades, orçamento), `CasamentoGramatica.componentes` (Task 1).
- Produces: `grammar_stem.casa_hastes(contexto: ContextoGramatica, gramatica: Mapping[str, Any]) -> list[tuple[Caixa, int, tuple[int, ...]]]` (caixa visual do símbolo inteiro, posição do caminho da haste, componentes de R-3), sem efeito colateral fora do orçamento; a fixture exporta `CASOS_HASTE: tuple[tuple[str, dict[str, Any]], ...]` (id de cada uma das 8 variantes de R-2 e a gramática dela, com o `max_span` do laboratório) e as funções de desenho; `_casar_no_contexto` despacha `stem_bars` para ela e preenche `componentes`. Toda consulta paga do orçamento: página hostil levanta `TetoGramaticasExcedido`.

- [ ] **Step 1: Escrever a fixture e os testes**, partindo do patch vencedor do laboratório. A fixture desenha com PyMuPDF (cor de traço comum, sem copiar folha real): haste com 3 barras decrescentes; com 4 alternadas; cada uma com elipse envolvente, com X, com os dois; giradas 90° e 45°; haste encostada numa linha longa do mesmo estilo; página com `/Rotate` 90. Negativos: 3 barras iguais; 2 barras; barras não perpendiculares; espaçamento fora da faixa; hachura de 6 traços paralelos sem haste; texto em glifo `E` e `≡` desenhado como caminho; barras de cor diferente da haste. Testes em `test_grammar_stem.py`, pelo núcleo (`pagina_para_gramaticas` + `casar_variantes` com as 8 variantes de R-2 montadas no teste):
  - `test_positivo_casa_so_a_variante_certa`, parametrizado pelos 8 positivos × 3 rotações: exatamente uma variante, a esperada, e a caixa contém haste e barras;
  - `test_negativo_nao_casa`, parametrizado pelos negativos: nenhum casamento;
  - `test_componentes_listam_haste_e_barras` (R-3);
  - `test_pagina_hostil_estoura_o_orcamento`: 20.000 traços curtos paralelos e limite pequeno → `TetoGramaticasExcedido`;
  - em `test_symbol_packages_sem_memorizacao.py`, `test_gramaticas_novas_passam_na_guarda`, que aplica `_violacoes_de_texto` ao fonte de `grammar_stem.py`.
- [ ] **Step 2: Rodar** e ver falhar (sem o patch) ou conferir que o patch passa os positivos e negativos.
- [ ] **Step 3: Implementar** a partir do patch, só nos dois arquivos de produção. Remova de `test_gasto_por_fase_ataque.py` o oráculo do corpo antigo e os testes que dependem dele (R-8); o restante do arquivo fica.
- [ ] **Step 4: Rodar** os testes novos, `tests/unit/test_symbol_matcher*.py`, `tests/unit/test_gasto_por_fase*.py`, `tests/unit/test_grammar_*`, ruff, format, mypy e `scripts/complexity_gate.py src`; e o benchmark do laboratório com `--metodo modelo` (com as variantes habilitadas só no worktree, sem commitar o JSON), colando o bloco de ATERRAMENTO e PARA_RAIOS_MT no relatório.
- [ ] **Step 5: Commit** (`feat: gramatica de haste com barras no nucleo`).

### Task 4: Observação com componentes, versão e digest

**Estimativa:** 30 min · **Depende de:** Task 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/model_symbols.py`
- Modify: `src/zeny_project_handler_server/symbol_execution.py`
- Modify: `tests/unit/test_model_symbols.py`, `tests/integration/test_model_symbols_runner.py`

**Interfaces:**
- Consumes: `CasamentoGramatica.componentes`, `grammar_stem`.
- Produces: `_VERSAO = "1.1.0"`; observação com uma primitiva por caminho do casamento (R-3); `grammar_stem` no digest do runner.

- [ ] **Step 1: Escrever os testes:**
  - em `test_model_symbols.py`: `test_observacao_tem_uma_primitiva_por_caminho` (casamento com `componentes=(5, 9)` → 3 primitivas com os índices crus das posições, em ordem, e camada de cada caminho), `test_sem_componentes_continua_com_uma_primitiva`, `test_versao_1_1_0`;
  - em `test_model_symbols_runner.py`: `test_digest_cobre_o_fecho_de_imports` (os módulos de `zeny_project_handler.adapters.analysis` importados, direta ou transitivamente, por `model_symbols` estão no digest do runner), no lugar da lista `_MODULOS_DO_DIGEST`; `test_haste_funde_com_o_legado` (página sintética com um aterramento da fixture da Task 3 e pacotes com a variante base habilitada em `tmp_path`: o runner reconcilia legado e modelo numa só ocorrência).
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.** Se o fecho mostrar `drawing_model/model.py` fora do digest, ele entra (a assinatura do runner muda: cache miss opt-in, esperado). Se `run` ou `_cache_complete` passarem de CC 30, extraia função antes.
- [ ] **Step 4: Rodar** os dois arquivos, `tests/server/` filtrado por `symbol`, ruff, format, mypy e `scripts/complexity_gate.py src`.
- [ ] **Step 5: Commit** (`feat: observacao com componentes e versao 1.1.0 do metodo sobre o modelo`).

### Task 5: Habilitação das variantes de haste

**Estimativa:** 40 min · **Depende de:** Task 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-19.json` (v001–v004), `family-f02-21.json` (v005–v008)
- Modify: `scripts/coverage_matrix_e16.py`, `tests/unit/test_e16_coverage_matrix.py`
- Modify: `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py`

**Interfaces:**
- Consumes: R-2, `GRAMATICAS_SO_MODELO`, a fixture `tests/fixtures/symbol_grammars/stem_bars.py` (Task 3), que exporta `CASOS_HASTE: tuple[tuple[str, dict[str, Any]], ...]` (id da variante, gramática) — se a Task 3 não exportar com esse nome, devolva ao orquestrador.
- Produces: 30 `enabled` e 393 `pending`.

- [ ] **Step 1: Atualizar os testes:**
  - `test_enabled_status_is_distinct_from_registered_coverage`: habilitadas = `_ENABLED_IDS` ∪ ids de `CASOS_HASTE`; as de `CASOS_HASTE` têm tipo em `GRAMATICAS_SO_MODELO`, e os testes que rodam o motor antigo sobre `ENABLED_CASES` não mudam;
  - contagens: `(393, 30)` no auditor, `== 30` e `== 393` na tabela de suporte (`test_e14_symbol_review.py:287-288`, `test_pacotes_classes_da_ficha.py`), e o golden das variantes antigas muda só nas 8 (de `pending` com `reason` para `enabled` com `grammar` e `negative_examples`);
  - `test_e16_coverage_matrix.py`: `test_variante_so_do_modelo_fica_fora_do_dominio_no_motor` (R-5).
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Habilitar** as 8 variantes com a gramática de `CASOS_HASTE` (R-2 e o `max_span` do laboratório), `negative_examples` = os `confusable_negatives` do inventário, sem `reason`; e R-5 na matriz.
- [ ] **Step 4: Rodar** os testes alterados, `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`, `enabled` 30), `tests/unit/test_symbol_packages_sem_memorizacao.py`, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: habilita aterramento e para-raios MT sobre o modelo`).

### Task 6: Medição nas 16 folhas e H2 (orquestrador)

**Estimativa:** 20 min · **Depende de:** Tasks 2, 4 e 5 · **Risco:** normal · **Laboratório:** não

Sem código: o orquestrador roda, na branch da etapa com as Tasks 1–5 integradas e `--processos 10`:
- [ ] `python -m scripts.benchmark_simbolos_ficha --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2/simbolos --metodo atual --metodo modelo --processos 10` → R-4 nas duas classes, tabela no handoff; falha vira rodada de correção da Task 3 (e repete o benchmark).
- [ ] `python -m scripts.residuos_raster_folhas --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2/h2 --recortes --processos 10` → contagem por folha e triagem visual (R-7); veredito da H2 no handoff e na linha H2 de "Hipóteses e decisões em aberto".
- [ ] `python -m scripts.audit_symbol_packages` → `errors: []`.

## Fechamento operacional

- Suíte inteira por onda; testador de etapa se alguma tarefa `Risco: normal` produziu código (a Task 2); scanner `osv-scanner` nos 7 locks; `check_test_integrity --base <MERGE_BASE>`; revisão final; `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` (conferir a data do `relatorio-testes.txt`).
- Handoff com: tabela do benchmark, H2 por folha, decisões R-1 a R-9 que mudam contrato ou o visível (R-1, R-5, R-6) em "Decisões para o usuário", e o bloco "Para a E06.3.3" (padrão de tipo só do modelo e componentes para as molduras de para-raios BT e transformador).
