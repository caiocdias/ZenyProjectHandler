# E06.3.2 — Aterramento, para-raios MT e H2: plano de implementação

> **Rascunho (2026-11-07):** a E06.3.2 foi dividida. As Tasks 1 e 2 e a medição da H2 foram para a E06.3.2.1 (`2026-11-07-leitura-vetorial-por-poste-e06-3-2-1.md`); este arquivo é o ponto de partida do plano da E06.3.2.2. Ao abrir a etapa, aplique os achados pendentes da rodada 1 da revisão de arquitetura da E06.3.2: **N3** (a Task 3 com 60 min vira duas: gramática, despacho e seus testes; depois teto, guarda, tupla de pureza e remoção do oráculo, que pode entrar na onda das Tasks 4 e 5), **N4** (a taxa de fusão precisa de código revisado: script versionado que chama `observar_simbolos_legados` e `observar_pacotes_modelo` e passa os dois a `reconcile_symbols(..., CalibrationPolicy())`, numa tarefa com código, dentro do limite de 3 arquivos de produção), **M-a** (o X não entra na caixa do pictograma, como em `_symbol_footprint`; a fusão também testa a variante "X sem envolvente") e **M-c** (Task 5 com 50 min: ruling ou divisão). Revisão de arquitetura própria, rodada 0, com revisor novo.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reconhecer ATERRAMENTO e PARA_RAIOS_MT sobre o modelo de desenho com uma gramática nova de haste com barras, acima do analisador atual nas 16 folhas, e confirmar ou refutar a H2 com a contagem de resíduos raster por folha.

**Architecture:** a gramática `stem_bars` vive num módulo novo do núcleo puro (`drawing_model/grammar_stem.py`) e só o método sobre o modelo (`declarative-drawing-model`) a executa: o motor antigo (`declarative-vector-packages`, que sai na E09) aceita o tipo na validação dos pacotes e no schema, mas o ignora ao observar e ao anunciar classes (R-1); o perfil do método sobre o modelo anuncia todas as habilitadas. A caixa do casamento é o pictograma, como no legado, e a haste inteira entra só como componente (R-3), para a reconciliação do runner fundir a ocorrência com a do detector legado. As 8 variantes de f02-19 (ATERRAMENTO) e f02-21 (PARA_RAIOS_MT) são habilitadas. A H2 é medida por um script novo que chama `residuos_raster` folha a folha e cruza cada resíduo com as referências da ficha.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só nos adaptadores e scripts), JSON + JSON Schema, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3" (objetivo, escopo, notas, riscos) e "E06.3.2"; os blocos "Para a E06.3" dos handoffs da E06.2.1, E06.2.2.1, E06.2.2.2 e E06.3.1; ADR 0016; `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` e `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md` (laboratório); o levantamento `tmp/e06/levantamento-e06.md` do checkout principal (§1, §3, §10).

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o núcleo `drawing_model/` não importa PyMuPDF (o adaptador `pymupdf_drawing_model.py` fica fora dele); o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- A saída da análise continua `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`; nenhuma migração SQLite; nenhuma mudança de API ou DTO.
- Mudança de comportamento de saída incrementa a versão do método correspondente (ADR 0006): `declarative-drawing-model` 1.0.0 → 1.1.0 (Task 4).
- PDFs reais, recortes, rótulos e conjuntos de dados nunca entram no Git. Todo comportamento novo tem fixture sintética autoral positiva e negativa; nenhuma coordenada, hash ou nome de folha real em código, pacote, fixture ou teste (guarda da E06.1, estendida na Task 3).
- Leitura de avaliação é sempre cega. Nada lê `examples/avaliacao-cega/`. As referências da rodada E03 (`tmp/curadoria-simbologia/20261103-2300-fichas/`) estão congeladas e não são editadas; leitores visuais não participam.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos. Testes sem dependência de ordem, cwd, porta ou arquivo fixo (use `tmp_path`). mypy strict, ruff check, ruff format, complexidade < 31 (Radon) em `src`.
- O método sobre o modelo liga só no `SymbolCompositionRunner` opt-in (D12). O analisador padrão não muda.
- Documentação enxuta: nada de histórico de execução em arquivo versionado.
- Não tocar `scripts/benchmark_ficha_poste.py` (E15) nem `tests/conftest.py`.
- Worktree da etapa: `.venv/Scripts/python.exe`. Em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` do worktree da etapa, a partir da raiz do worktree da tarefa; a suíte inteira usa `-n` = 20 ÷ suítes ativas (o despacho informa o número).

## Review Focus

1. Pacote com variante `enabled` de tipo `stem_bars` carregado pelo motor antigo → carrega sem erro, o motor não a observa nem a conta em `classes_suportadas`, e continua observando a `label_in_frame` ao lado; o perfil do método sobre o modelo a conta e a observação de haste tem cobertura (Task 1).
2. Haste com barras encostada numa linha longa da rede (vão, cabo) do mesmo estilo → ainda casa, com a caixa do pictograma; três ou quatro traços paralelos que não são barras de haste (hachura, cerca, texto em glifo como `E` ou `≡`) → não casam (Task 3).
3. Página com símbolo girado (0°, 90°, 45°) e página com rotação de página `/Rotate` 90 → mesma variante, caixa coerente na página exibida (Tasks 3 e 4).
4. Página hostil com milhares de segmentos curtos paralelos → `TetoGramaticasExcedido` pelo orçamento, nunca laço sem teto (Task 3).
5. Resíduo raster em página `FORA_DOMINIO` ou com imagens que falharam → fica fora da contagem por folha, com o motivo, e não vira "0 resíduos" (Task 2).

## Decisões do plano

- **R-E06.3.2-1, tipo só do modelo:** `stem_bars` entra em `declarative_symbols._GRAMMARS`, no validador de campos e no schema `docs/schemas/pacotes-simbologia.schema.json` (ramo novo do `oneOf`), e numa constante pública nova `GRAMATICAS_SO_MODELO = frozenset({"stem_bars"})`. O motor antigo observa e anuncia só `variantes_do_motor(pacotes)` (habilitadas fora de `GRAMATICAS_SO_MODELO`); `_enabled` continua devolvendo todas as habilitadas. `perfil_pacotes_modelo` passa a calcular `classes_suportadas` e `("enabled_variants", n)` a partir de `_enabled` (todas), e não a herdá-los do motor: sem isso, o domínio recusa a observação de haste por falta de cobertura. O diff núcleo × motor (Task 5) e os testes de paridade (Task 1) comparam só `variantes_do_motor`. Descartado: implementar a gramática também no motor antigo (trabalho jogado fora na E09). Dívida para a E09: `GRAMATICAS_SO_MODELO` e a validação dos pacotes moram em `declarative_symbols.py`, que ela remove.
- **R-E06.3.2-2, campos da gramática** (exatos; a validação recusa outros): `{"kind": "stem_bars", "bars": 3 | 4, "taper": "decreasing" | "alternating", "enclosure": "none" | "ellipse", "removal_mark": bool, "max_span": número em (0, 72]}`. Só os pares `bars` 3 com `decreasing` e `bars` 4 com `alternating` são válidos. O validador não amarra `class_code` a `bars` (o auditor confere a classe contra o inventário). `bars`/`taper` separam as classes (ATERRAMENTO 3 `decreasing`, PARA_RAIOS_MT 4 `alternating`); `enclosure` e `removal_mark` separam as quatro variantes de situação (base `none`/false; envolvente `ellipse`/false; envolvente e X `ellipse`/true; X sem envolvente `none`/true). As quatro de uma classe são mutuamente exclusivas por construção: um mesmo desenho casa no máximo uma. A cor não decide nada ("Não inferir estado por cor isolada", inventário). Os limiares geométricos são constantes do módulo, escolhidos pelo laboratório.
- **R-E06.3.2-3, caixa e componentes:** a caixa do casamento é o **pictograma**, com a regra de `pymupdf_symbols._symbol_footprint`: envolvente quando há, senão barras, X e o trecho da haste até o comprimento da maior barra; a haste inteira não entra na caixa ("A haste de ligação até o poste não pertence ao pictograma"). `max_span` vale sobre o pictograma. A ficha E03 também anota o pictograma (caixa da ordem de 0,004 × 0,005 da página). `CasamentoGramatica` ganha `componentes: tuple[int, ...] = ()`, as posições em `modelo.caminhos` dos demais caminhos do símbolo (haste e barras), sem repetir `caminho`, em ordem crescente; as gramáticas atuais deixam vazio. A observação ganha uma `PrimitivaObservadaSimbolo` por caminho (`caminho` e cada componente), com o índice cru e a camada de cada um; `pontos_originais` de cada primitiva é a caixa daquele caminho.
- **R-E06.3.2-4, critério de aceite "maiores que os do atual":** por classe, precisão **e** recall estritamente maiores que os do `atual`, critério `centro`, com as mesmas referências. Vale a linha de base congelada `tmp/e06-2-2-2/simbolos/simbolos-ficha.json` (sha256 `b6a3118d…6008d`): ATERRAMENTO > 56,2% de precisão (41/73) e > 95,3% de recall (41/43); PARA_RAIOS_MT > 71,4% (10/14) e > 76,9% (10/13). O `atual` remedido na Task 6 tem de coincidir com ela; se divergir, decide a congelada e a divergência é investigada antes do fechamento. E **leitura errada afirmada = 0**: nenhuma predição ATERRAMENTO ou PARA_RAIOS_MT do método `modelo` com centro na caixa de uma referência de **qualquer** outra classe (inclusive a outra das duas), calculada por `leituras_erradas` (Task 2) do mesmo jeito no laboratório e na Task 6. Se o laboratório mostrar que uma referência perdida não é desenhável pelo vetor (resíduo raster, H2), a ruling vai ao handoff antes de afrouxar qualquer número.
- **R-E06.3.2-5, matriz da curadoria:** variante habilitada com tipo em `GRAMATICAS_SO_MODELO` tem `declarative-vector-packages` = `fora_do_dominio` em `scripts/coverage_matrix_e16.py`, porque o motor antigo não a executa; a matriz não ganha coluna nova (é contrato da curadoria e a rodada seguinte decide). O status de variante E04 continua `nao_avaliavel` (`:194-196`): o ganho aparece no benchmark por ficha, não na matriz. Outros consumidores que leem `status == "enabled"` por conta própria vão contar as 8 como habilitadas: `symbol_support.py` (tabela de suporte e exportações), `scripts/symbol_benchmark_runner.py` (`enabled_variant_count` 30) e `scripts/curation_backlog.py:101` (dono `declarative_symbols.py`). Fica assim, registrado em "Decisões para o usuário".
- **R-E06.3.2-6, sinal "Exclusivo" no runner opt-in:** com a haste habilitada, uma ocorrência de ATERRAMENTO ou PARA_RAIOS_MT vista pelo legado e pelo método novo funde e passa a "Suportado". Se vencer H-A, são dois algoritmos independentes e o rótulo é verdadeiro; se vencer H-B ou H-C, a gramática reimplementa a consulta do legado e "Suportado" **não** é corroboração, como na ruling da E06.2.2.1. Fica aceito até a E09, sem mudança de produção, com a taxa de fusão medida na Task 6; vai para "Decisões para o usuário".
- **R-E06.3.2-7, H2:** é confirmada se nenhum resíduo das 16 folhas for símbolo da rede, pela triagem visual dos recortes (o orquestrador lê os PNG; resíduo com hash repetido é triado uma vez) e pelo cruzamento com as referências (resíduo cuja caixa contém o centro de uma referência de símbolo é candidato a símbolo raster). Página `FORA_DOMINIO` ou com imagens que falharam não conta como zero. Limitação: `residuos_raster` só vê imagem compacta (4–72 pt) fora de mosaico; por isso o script também lista as referências de símbolo cujo centro cai sob **qualquer** imagem (`referencias_sob_imagem`), e as que nenhum método vetorial casa são triadas.
- **R-E06.3.2-8, pendências herdadas:** o oráculo de `tests/unit/test_gasto_por_fase_ataque.py` (cópia do corpo antigo de `casar_variantes`) é removido na Task 3, que muda os helpers do casador, como o handoff da E06.2.2.2 manda; `_MODULOS_DO_DIGEST` (cópia manual) vira teste de fecho por imports na Task 4. Ficam para depois, com ruling no handoff: promover os privados de `grammar_disc` (a E06.3.3 mexe em `grammar_frames`), `runner._package_prediction` público (o benchmark não muda aqui), recortes e fila do diff (com R-1, não há "só no núcleo" a classificar).
- **R-E06.3.2-9, se o laboratório escolher H-A (grupo como unidade):** quem consome `grupos` adiciona `modelo.grupos_falhou` às fontes consumidas (`symbol_grammars._FONTES_CONSUMIDAS`), põe `LIMITE_VISITAS_AGRUPAMENTO` nos `parametros` do perfil (Task 4) e revê R-1 da E06.2.2.1 (subir `VERSAO_MODELO_DESENHO`). Com H-B ou H-C, nada disso se aplica.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/declarative_symbols.py` | `stem_bars` na validação, `GRAMATICAS_SO_MODELO`, `variantes_do_motor` no motor | 1 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` | `CasamentoGramatica.componentes` (1); despacho explícito e `stem_bars` (3) | 1, 3 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | perfil com todas as habilitadas (1); primitivas por componente, versão 1.1.0 (4) | 1, 4 |
| `docs/schemas/pacotes-simbologia.schema.json` | ramo `stem_bars` (R-2) | 1 |
| `tests/unit/test_gramatica_so_modelo.py` (novo) | validação, schema, motor ignora, perfil do modelo conta | 1 |
| `tests/unit/test_model_symbols.py` | `test_perfil_declara_o_metodo` (1); primitivas e versão (4) | 1, 4 |
| `tests/unit/test_symbol_matcher_paridade.py` | paridade sobre `variantes_do_motor` (1); `grammar_stem` no teste de pureza (3) | 1, 3 |
| `scripts/residuos_raster_folhas.py` (novo) | H2: resíduos por folha, cruzamento com a ficha, recortes | 2 |
| `scripts/simbolos_ficha_metricas.py` | `leituras_erradas` (R-4) | 2 |
| `tests/unit/test_residuos_raster_folhas.py` (novo), `tests/unit/test_leituras_erradas.py` (novo) | rodada sintética em `tmp_path`; métrica | 2 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py` (novo) | gramática de haste com barras | 3 |
| `tests/fixtures/symbol_grammars/__init__.py`, `tests/fixtures/symbol_grammars/stem_bars.py` (novos) | desenhos sintéticos positivos e negativos da haste, `CASOS_HASTE` | 3 |
| `tests/unit/test_grammar_stem.py` (novo) | gramática pelo núcleo, positivos, negativos, teto | 3 |
| `tests/unit/test_symbol_packages_sem_memorizacao.py` | guarda estendida a `grammar_stem.py` e à fixture | 3 |
| `tests/unit/test_gasto_por_fase_ataque.py` | oráculo removido (R-8) | 3 |
| `src/zeny_project_handler_server/symbol_execution.py` | módulos do fecho no digest | 4 |
| `tests/integration/test_model_symbols_runner.py` | fecho por imports no lugar de `_MODULOS_DO_DIGEST`; fusão com o legado | 4 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-19.json`, `family-f02-21.json` | 8 variantes habilitadas | 5 |
| `scripts/coverage_matrix_e16.py`, `tests/unit/test_e16_coverage_matrix.py` | R-5 | 5 |
| `scripts/diff_simbolos_nucleo_motor.py` | compara só `variantes_do_motor` | 5 |
| `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py:287-288` | contagens 22→30 e 401→393; habilitadas = casos do motor ∪ casos só do modelo | 5 |

Ondas: Onda 1, Tasks 1 e 2; laboratório (sobre a Onda 1 integrada); Task 3; Onda 2, Tasks 4 e 5; Task 6 (medição, orquestrador).

Soma das tarefas: 3h20 (35 + 45 + 60 + 30 + 50), mais o laboratório (caixa de 60 min, em paralelo) e a medição (~25 min). Parede estimada com as ondas: ~3h30. Fica sem divisão (ruling no ledger): dividir somaria um plano, uma revisão final e um `.bat` a mais, e o estouro de 4h30 do protocolo continua valendo.

## Laboratório (antes da Task 3)

- **Base:** a branch da etapa com a Onda 1 integrada. Cada hipótese: um `desenvolvedor` com `isolation: "worktree"`, sem commit e sem a suíte inteira, que implementa `grammar_stem.py`, o despacho no casador (R-2, R-3), a habilitação das 8 variantes e os testes focados com os positivos e negativos do Review Focus 2, escritos no próprio patch, e mede.
- **Hipóteses:**
  - **H-A, grupo como unidade:** a gramática roda por `GrupoCandidato` de `modelo.grupos`; a haste e as barras precisam estar no mesmo grupo. R-9 se aplica.
  - **H-B, segmento como semente e consulta espacial:** cada `Segmento` de `contexto.grade_segmentos` com comprimento plausível de haste consulta a grade num raio proporcional a ele, como o legado (`pymupdf_symbols._ground_and_mt_arrester_matches`), incluindo traço longo cortado na caixa.
  - **H-C, H-B com limiares por família:** os mesmos passos de H-B, com tolerâncias escolhidas por um sinal da própria página (origem dos `TextoModelo`: glifo, SHX ou nativo), sem ler o documento. Exige fixture sintética por família.
- **Comando** (no worktree da hipótese, com o `.venv` do worktree da etapa e `PYTHONPATH=<worktree>/src`; `--processos 6` com as três hipóteses rodando):
  `.venv/Scripts/python.exe -m scripts.benchmark_simbolos_ficha --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/laboratorio/e06-3-2/<hipotese>/iter-<k> --metodo modelo --processos 6`, seguido de `leituras_erradas` (Task 2) sobre o `simbolos-ficha.json` gerado.
- **Métrica:** tp/fp/fn por classe (critério `centro`) de ATERRAMENTO e PARA_RAIOS_MT contra a linha de base `atual` congelada (R-4), leituras erradas afirmadas, tempo por folha e gasto máximo do orçamento por folha (de `gasto_por_fase`).
- **Vitória:** R-4 nas duas classes, leitura errada afirmada = 0, positivos e negativos sintéticos verdes, gasto máximo ≤ 200.000 consultas por folha (R-E06.2.2.2-4). Desempate: soma dos F1 das duas classes, depois menor tempo máximo por folha.
- **Parada:** 60 min por hipótese, ou vitória com margem de 2 tp em cada classe.
- **Entrega:** em `<checkout principal>/tmp/laboratorio/e06-3-2/<hipotese>/`: `patch.diff` (contra a base), `metricas.json` por iteração e `conclusoes.md` (o que mudou entre iterações, falsos positivos vistos por tipo, sem coordenada de folha real no patch).
- **Seleção:** pela métrica, com ruling no ledger. Nenhuma vence: a ruling registra a melhor e o déficit, e a Task 3 parte dela; o critério 2 fica como impedimento real se a Task 6 não fechar.

## Tasks

### Task 1: Tipo de gramática só do modelo

**Estimativa:** 35 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` (só o campo)
- Modify: `src/zeny_project_handler/adapters/analysis/model_symbols.py` (só o perfil)
- Modify: `docs/schemas/pacotes-simbologia.schema.json`
- Create: `tests/unit/test_gramatica_so_modelo.py`
- Modify: `tests/unit/test_model_symbols.py`, `tests/unit/test_symbol_matcher_paridade.py`

**Interfaces:**
- Produces: `declarative_symbols.GRAMATICAS_SO_MODELO: Final[frozenset[str]]`; `declarative_symbols.variantes_do_motor(pacotes: tuple[Package, ...]) -> tuple[tuple[Package, Package], ...]`; validação de `stem_bars` conforme R-2; `perfil_pacotes` e `observar_pacotes` usam `variantes_do_motor`; `perfil_pacotes_modelo` com `classes_suportadas` e `enabled_variants` de `_enabled`; `CasamentoGramatica.componentes: tuple[int, ...] = ()`.

- [ ] **Step 1: Escrever os testes** em `test_gramatica_so_modelo.py`, com pacotes sintéticos escritos em `tmp_path` e carregados por `carregar_pacotes(packages_dir=tmp_path)`:
  - `test_stem_bars_valido_carrega` (as quatro combinações de `enclosure`/`removal_mark` para 3/`decreasing` e para 4/`alternating`);
  - `test_stem_bars_invalido_recusa`, parametrizado: campo a mais, `bars` 2 ou 5, 3 com `alternating`, 4 com `decreasing`, `taper` desconhecido, `enclosure` desconhecido, `removal_mark` não booleano, `max_span` 0, 73 ou booleano → `ValueError`;
  - `test_schema_aceita_e_recusa_como_o_validador`: os mesmos válidos e inválidos contra `docs/schemas/pacotes-simbologia.schema.json` (com a biblioteca de JSON Schema que os testes atuais do schema já usam);
  - `test_motor_ignora_variante_so_do_modelo`: um pacote com uma variante `label_in_frame` e uma `stem_bars` habilitadas; `perfil_pacotes(...).classes_suportadas` não contém a classe da `stem_bars`, `("enabled_variants", 1)` nos parâmetros, e `observar_pacotes` numa página com a moldura positiva da `label_in_frame` (desenhada como em `tests/fixtures/declarative_symbols/corpus.py`) observa só ela, sem falhar;
  - `test_perfil_do_modelo_conta_a_variante_so_do_modelo`: `perfil_pacotes_modelo` do mesmo pacote tem as duas classes e `("enabled_variants", 2)`;
  - `test_enabled_continua_com_todas` e `test_casamento_sem_componentes_por_padrao`.
  - Em `test_model_symbols.py`, `test_perfil_declara_o_metodo` passa a comparar `classes_suportadas` e `enabled_variants` com os de `_enabled`, não com os do motor.
  - Em `test_symbol_matcher_paridade.py`, a fixture `variantes` passa a usar `variantes_do_motor(carregar_pacotes())`; faça o mesmo em qualquer outro teste que compare núcleo e motor com os pacotes reais (procure `_enabled(` em `tests/`).
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar** em `declarative_symbols.py`, no perfil de `model_symbols.py`, no schema e o campo em `symbol_matcher.py`.
- [ ] **Step 4: Rodar** o arquivo novo, `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_symbol_matcher_paridade.py`, `tests/unit/test_model_symbols*.py`, os testes do schema dos pacotes e `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`); ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: tipo de gramatica so do modelo de desenho`).

### Task 2: Medição da H2 por folha e leituras erradas

**Estimativa:** 45 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `scripts/residuos_raster_folhas.py`
- Modify: `scripts/simbolos_ficha_metricas.py`
- Create: `tests/unit/test_residuos_raster_folhas.py`, `tests/unit/test_leituras_erradas.py`

**Interfaces:**
- Consumes: `model_symbols.residuos_raster`, `pagina_para_gramaticas`, `casar_variantes`, `_enabled`; o mapa de folhas de `scripts/simbolos_corpus.py` (mesma guarda de `avaliacao-cega` e mesma conferência de sha do benchmark).
- Produces:
  - CLI `python -m scripts.residuos_raster_folhas --rodada DIR --saida DIR [--recortes] [--dpi 200] [--processos N]`; `saida/residuos-raster.json` no esquema `residuos-raster-v1`: `{"esquema", "rodada", "folhas": [{"pdf_id", "paginas": [{"pagina", "estado": "medida" | "fora_dominio", "motivo", "residuos": [{"caixa_normalizada", "sha256_curto", "de_anotacao", "referencias_sob": [classe, ...], "recorte": "<nome>.png" | null}], "referencias_sob_imagem": [{"id", "classe"}]}], "total": int | null}], "resumo": {"folhas_medidas", "folhas_fora_dominio", "residuos", "por_hash": {sha256_curto: n_folhas}, "sobre_referencia": n, "referencias_sob_imagem": n}}`. `total` é `null` quando alguma página da folha é `fora_dominio`. Sem nome de PDF nem caminho na saída, só o id da rodada.
  - `simbolos_ficha_metricas.leituras_erradas(relatorio: Mapping[str, Any], metodo: str, classes: Collection[str], referencias: Mapping[str, Any]) -> list[dict[str, Any]]` — ou a forma equivalente que o relatório do benchmark já permita: para cada predição de uma classe de `classes` do método, as referências de **outra** classe cuja caixa (com a mesma tolerância do critério `centro`) contém o centro dela; e uma CLI `python -m scripts.simbolos_ficha_metricas leituras-erradas --rodada DIR --relatorio <simbolos-ficha.json> --metodo modelo --classe ATERRAMENTO --classe PARA_RAIOS_MT` que imprime a lista e o total. Se o `simbolos-ficha.json` não guardar as predições, o comando recalcula a partir de `--rodada` com o método nomeado; diga no relatório qual caminho tomou.

- [ ] **Step 1: Escrever os testes.** Em `test_residuos_raster_folhas.py`, sobre uma rodada sintética em `tmp_path` (2 PDFs gerados pelo PyMuPDF, com `rodada.json` e `ficha/referencia.json` no formato da E03; um PDF com uma imagem compacta inserida sobre a caixa de uma referência de símbolo, outra longe e uma imagem grande sob outra referência; o outro sem imagem):
  - `test_conta_residuos_por_folha` (2 e 0) e `test_cruza_com_referencia` (`referencias_sob == ["ATERRAMENTO"]` só na imagem sobre a referência);
  - `test_referencia_sob_imagem_grande_e_listada`;
  - `test_pagina_fora_dominio_nao_vira_zero`: monkeypatch de `casar_variantes` levantando `TetoGramaticasExcedido` → `estado == "fora_dominio"`, `total is None`;
  - `test_imagens_falhou_nao_vira_zero`: diagnóstico `modelo.imagens_falhou` (ou `modelo.imagens_anotacao_falhou`) na página → `fora_dominio` com o motivo, `total is None`;
  - `test_recortes_gravados` com `--recortes` (PNG existe, nome sem o do PDF) e `test_saida_sem_caminho_nem_nome_de_pdf`;
  - `test_recusa_avaliacao_cega` (rodada apontando para `avaliacao-cega`, como no benchmark);
  - `test_processos_da_o_mesmo_resultado` (`--processos 1` e `2`).
  - Em `test_leituras_erradas.py`: predição ATERRAMENTO com centro na caixa de uma referência PARA_RAIOS_BT → 1 leitura errada; com centro na de uma ATERRAMENTO → 0; com centro fora de tudo → 0; classe fora de `classes` → ignorada.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.** Por página: `pagina_para_gramaticas(pagina, indice, tabela)`, `casar_variantes` com as variantes habilitadas dos pacotes carregados uma vez por folha, `residuos_raster(pagina, casamentos)`; `FonteGramaticaFalhou`, `TetoGramaticasExcedido`, `modelo.caminhos_falhou`, `modelo.imagens_falhou` e `modelo.imagens_anotacao_falhou` dão `fora_dominio` com o motivo. Recorte por `page.get_pixmap(clip=<caixa crua>, dpi=dpi)`, com a caixa crua vinda da derrotação, como `model_symbols._observacao`. Paralelismo como `scripts/benchmark_simbolos_ficha.py` (`ProcessPoolExecutor`, ordem serial).
- [ ] **Step 4: Rodar** os dois arquivos de teste, os testes atuais do benchmark (`tests/unit/test_benchmark_simbolos_ficha*.py`, `tests/unit/test_simbolos_ficha*.py`), ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: medicao de residuos raster por folha (H2) e leituras erradas`).

### Task 3: Gramática de haste com barras

**Estimativa:** 60 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** sim (parte do patch vencedor)

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`
- Create: `tests/fixtures/symbol_grammars/__init__.py`, `tests/fixtures/symbol_grammars/stem_bars.py`, `tests/unit/test_grammar_stem.py`
- Modify: `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_gasto_por_fase_ataque.py`, `tests/unit/test_symbol_matcher_paridade.py` (só a tupla do teste de pureza)

**Interfaces:**
- Consumes: `ContextoGramatica` (grades, orçamento), `CasamentoGramatica.componentes` (Task 1).
- Produces: `grammar_stem.casa_hastes(contexto: ContextoGramatica, gramatica: Mapping[str, Any]) -> list[tuple[Caixa, int, tuple[int, ...]]]` (caixa visual do pictograma, R-3; posição do caminho das barras ou da envolvente que ancora o símbolo; componentes de R-3), sem efeito colateral fora do orçamento; a fixture exporta `CASOS_HASTE: tuple[tuple[str, dict[str, Any]], ...]` (id de cada uma das 8 variantes de R-2 e a gramática dela, com o `max_span` do laboratório) e as funções de desenho; `_casar_no_contexto` despacha explicitamente por `kind` (`terminal_disc`, `stem_bars` e os tipos de moldura) e levanta `ValueError` em `kind` desconhecido, preenchendo `componentes`. Toda consulta paga do orçamento: página hostil levanta `TetoGramaticasExcedido`.

- [ ] **Step 1: Escrever a fixture e os testes**, partindo do patch vencedor do laboratório. A fixture desenha com PyMuPDF (cor de traço comum, sem copiar folha real): haste com 3 barras decrescentes; com 4 alternadas; cada uma com elipse envolvente, com X, com os dois; giradas 90° e 45°; haste encostada numa linha longa do mesmo estilo; página com `/Rotate` 90. Negativos: 3 barras iguais; 2 barras; barras não perpendiculares; espaçamento fora da faixa; hachura de 6 traços paralelos sem haste; texto em glifo `E` e `≡` desenhado como caminho; barras de cor diferente da haste. Testes em `test_grammar_stem.py`, pelo núcleo (`pagina_para_gramaticas` + `casar_variantes` com as 8 variantes de `CASOS_HASTE`):
  - `test_positivo_casa_so_a_variante_certa`, parametrizado pelos 8 positivos × 3 rotações: exatamente uma variante, a esperada;
  - `test_caixa_e_o_pictograma`: a caixa contém barras, envolvente (quando há) e a ponta da haste, e não a haste inteira; com a haste encostada na linha longa, a caixa é a mesma da haste curta, a menos de 0,5 pt;
  - `test_negativo_nao_casa`, parametrizado pelos negativos: nenhum casamento;
  - `test_componentes_listam_haste_e_barras` (R-3);
  - `test_pagina_hostil_estoura_o_orcamento`: 20.000 traços curtos paralelos e limite pequeno → `TetoGramaticasExcedido`;
  - `test_kind_desconhecido_recusa` (despacho explícito);
  - em `test_symbol_packages_sem_memorizacao.py`, `test_gramaticas_novas_passam_na_guarda`, que aplica `_violacoes_de_texto` ao fonte de `grammar_stem.py` e de `tests/fixtures/symbol_grammars/stem_bars.py`;
  - em `test_symbol_matcher_paridade.py`, `grammar_stem` entra na tupla de `test_modulos_do_nucleo_nao_importam_pymupdf`.
- [ ] **Step 2: Rodar** e ver falhar (sem o patch) ou conferir que o patch passa os positivos e negativos.
- [ ] **Step 3: Implementar** a partir do patch, só nos dois arquivos de produção. Remova de `test_gasto_por_fase_ataque.py` o oráculo do corpo antigo e os testes que dependem dele (R-8); o restante do arquivo fica.
- [ ] **Step 4: Rodar** os testes novos, `tests/unit/test_symbol_matcher*.py`, `tests/unit/test_gasto_por_fase*.py`, `tests/unit/test_grammar_*`, ruff, format, mypy e `scripts/complexity_gate.py src`; e o benchmark do laboratório com `--metodo modelo` (com as variantes habilitadas só no worktree, sem commitar o JSON), colando no relatório o bloco de ATERRAMENTO e PARA_RAIOS_MT e o total de `leituras-erradas`.
- [ ] **Step 5: Commit** (`feat: gramatica de haste com barras no nucleo`).

### Task 4: Observação com componentes, versão e digest

**Estimativa:** 30 min · **Depende de:** Task 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/model_symbols.py`
- Modify: `src/zeny_project_handler_server/symbol_execution.py`
- Modify: `tests/unit/test_model_symbols.py`, `tests/integration/test_model_symbols_runner.py`

**Interfaces:**
- Consumes: `CasamentoGramatica.componentes`, `grammar_stem`, `CASOS_HASTE` e as funções de desenho da fixture (Task 3).
- Produces: `_VERSAO = "1.1.0"`; observação com uma primitiva por caminho do casamento (R-3); todo módulo do fecho de imports no digest do runner.

- [ ] **Step 1: Escrever os testes:**
  - em `test_model_symbols.py`: `test_observacao_tem_uma_primitiva_por_caminho` (casamento com `componentes=(5, 9)` → 3 primitivas com os índices crus das posições, em ordem, e camada de cada caminho), `test_sem_componentes_continua_com_uma_primitiva`, `test_versao_1_1_0`;
  - em `test_model_symbols_runner.py`: `test_digest_cobre_o_fecho_de_imports` (todo módulo de `zeny_project_handler.adapters.analysis` importado, direta ou transitivamente, por `model_symbols` está no digest do runner), no lugar da lista `_MODULOS_DO_DIGEST`; `test_haste_funde_com_o_legado`, parametrizado por haste curta, haste encostada numa linha longa e página com `/Rotate` 90 (pacotes com a variante base habilitada em `tmp_path`): o runner reconcilia legado e modelo numa só ocorrência.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.** Todo módulo que o fecho apontar entra no digest (por exemplo `drawing_model/model.py`); a assinatura do runner muda (cache miss opt-in, esperado). Se `run` ou `_cache_complete` passarem de CC 30, extraia função antes.
- [ ] **Step 4: Rodar** os dois arquivos, `tests/server/` filtrado por `symbol`, ruff, format, mypy e `scripts/complexity_gate.py src`.
- [ ] **Step 5: Commit** (`feat: observacao com componentes e versao 1.1.0 do metodo sobre o modelo`).

### Task 5: Habilitação das variantes de haste

**Estimativa:** 50 min · **Depende de:** Task 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-19.json` (v001–v004), `family-f02-21.json` (v005–v008)
- Modify: `scripts/coverage_matrix_e16.py`, `tests/unit/test_e16_coverage_matrix.py`
- Modify: `scripts/diff_simbolos_nucleo_motor.py` e os testes dele que mudarem
- Modify: `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py`

**Interfaces:**
- Consumes: R-2, `GRAMATICAS_SO_MODELO`, `variantes_do_motor`, `CASOS_HASTE` (Task 3) — se a fixture não exportar com esse nome, devolva ao orquestrador.
- Produces: 30 `enabled` e 393 `pending`.

- [ ] **Step 1: Atualizar os testes:**
  - `test_enabled_status_is_distinct_from_registered_coverage`: habilitadas = `_ENABLED_IDS` ∪ ids de `CASOS_HASTE`; as de `CASOS_HASTE` têm tipo em `GRAMATICAS_SO_MODELO`, e os testes que rodam o motor antigo sobre `ENABLED_CASES` não mudam;
  - contagens: `(393, 30)` no auditor, `== 30` e `== 393` na tabela de suporte (`test_e14_symbol_review.py:287-288`, `test_pacotes_classes_da_ficha.py`), e o golden das variantes antigas muda só nas 8 (de `pending` com `reason` para `enabled` com `grammar` e `negative_examples`);
  - `test_e16_coverage_matrix.py`: `test_variante_so_do_modelo_fica_fora_do_dominio_no_motor` (R-5);
  - teste do diff: com uma variante `stem_bars` habilitada nos pacotes, ela não aparece no diff.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Habilitar** as 8 variantes com a gramática de `CASOS_HASTE`, `negative_examples` = os `confusable_negatives` do inventário, sem `reason`; R-5 na matriz; e `variantes_do_motor` nos dois lados do diff (e na docstring).
- [ ] **Step 4: Rodar** os testes alterados, `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`, `enabled` 30), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py`, os testes do schema, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: habilita aterramento e para-raios MT sobre o modelo`).

### Task 6: Medição nas 16 folhas e H2 (orquestrador)

**Estimativa:** 25 min · **Depende de:** Tasks 2, 4 e 5 · **Risco:** normal · **Laboratório:** não

Sem código: o orquestrador roda, na branch da etapa com as Tasks 1–5 integradas e `--processos 10`, com `<rodada E03>` = `<checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas`:
- [ ] `python -m scripts.benchmark_simbolos_ficha --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2/simbolos --metodo atual --metodo modelo --processos 10` → R-4 nas duas classes; `atual` igual ao congelado; o bloco `modelo` das outras classes igual, por folha, ao de `tmp/e06-2-2-2/simbolos/simbolos-ficha.json`. Falha vira rodada de correção da Task 3 (e repete o benchmark).
- [ ] `python -m scripts.simbolos_ficha_metricas leituras-erradas ... --metodo modelo --classe ATERRAMENTO --classe PARA_RAIOS_MT` → 0.
- [ ] `python -m scripts.diff_simbolos_nucleo_motor --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2/diff --processos 10` → contra `tmp/e06-2-2-2/diff/diff-nucleo-motor.json` (sha256 `20f3b708…6eeeee`), pela chave natural `(pdf_id, página, variante, índice cru)`: `ambos` 29 e `so_*` 0 nas variantes do motor.
- [ ] Taxa de fusão (R-6): runner de símbolos com reconciliação nas 16 folhas (`scripts/symbol_benchmark_runner.py` ou um comando de uma linha com `SymbolCompositionRunner`, sem script novo versionado), contando as ocorrências de ATERRAMENTO e PARA_RAIOS_MT com legado e modelo juntos contra as de um método só.
- [ ] `python -m scripts.residuos_raster_folhas --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2/h2 --recortes --processos 10` → contagem por folha e triagem visual (R-7); veredito da H2 no handoff e na linha H2 de "Hipóteses e decisões em aberto".
- [ ] `python -m scripts.audit_symbol_packages` → `errors: []`.

## Fechamento operacional

- Suíte inteira por onda; testador de etapa se alguma tarefa `Risco: normal` produziu código (nenhuma, hoje); scanner `osv-scanner` nos 7 locks; `check_test_integrity --base <MERGE_BASE>`; revisão final; `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` (conferir a data do `relatorio-testes.txt`).
- Handoff com: tabela do benchmark, leituras erradas, diff contra o congelado, taxa de fusão, H2 por folha, decisões R-1 a R-9 que mudam contrato ou o visível (R-1, R-5, R-6) em "Decisões para o usuário", o bloco "Para a E06.3.3" (padrão de tipo só do modelo, pictograma e componentes para as molduras de para-raios BT e transformador) e o bloco "Para a E09" (`GRAMATICAS_SO_MODELO` e validação dos pacotes em `declarative_symbols.py`).
