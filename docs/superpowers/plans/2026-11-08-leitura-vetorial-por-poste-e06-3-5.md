# E06.3.5 — Equipamento de interrupção: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reconhecer EQUIPAMENTO_INTERRUPCAO (disco vermelho com curva fusível em S ou com caixa dupla) sobre o modelo de desenho, onde o atual não emite a classe.

**Architecture:** segue a haste, o BT, o transformador e o estai: tipo só do modelo `disc_mark`, executado só por `declarative-drawing-model` no runner opt-in. A gramática vive em `drawing_model/grammar_disc_mark.py` e semeia pelos discos candidatos de `grammar_disc.py`, com um teto de vão parametrizado só para ela, sem mudar a saída de `terminal_disc`.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só adaptadores, scripts e fixtures), JSON + JSON Schema, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3" e "E06.3.5"; D12, D15, D17, D19; handoff da E06.3.4 ("Para a E06.3.5"); plano da E06.3.4 como modelo; ADR 0006 e 0016. Levantamento técnico: `tmp/janela-0.6.0/levantamento-e06-3-5.md` do checkout principal (fora do Git).

## Global Constraints

- Arquitetura hexagonal; o núcleo `drawing_model/` não importa PyMuPDF.
- Nenhuma migração, API ou DTO. O método sobre o modelo liga só no runner opt-in (D12), e `ZENY_SERVER_SYMBOL_COMPOSITION=false` continua sem efeito sobre a saída da análise. A tabela de suporte e a exportação contam as variantes habilitadas (vai a "Decisões para o usuário").
- ADR 0006: `declarative-drawing-model` passa de 1.5.0 a 1.6.0 no commit da habilitação (Task 3). O motor antigo não executa tipo só do modelo.
- Sem dependência nova. Fixtures sintéticas autorais; nenhuma coordenada, hash ou nome de folha real; a guarda de fonte (`_GRAMATICAS_NOVAS`) cobre os arquivos novos. Nada lê `examples/avaliacao-cega/`.
- `terminal_disc` e PONTO_CONEXAO não mudam: mesma saída por folha (`tmp/e06-3-4/final`).
- Não tocar nos arquivos da E07.2.1, aberta em paralelo: `src/zeny_project_handler/adapters/interpretation/`, `composition.py`, `scripts/benchmark_network_pdf.py`, `tests/server/test_ficha_poste_composicao*`, `tests/unit/test_interpretador_*`, `tests/unit/test_ancoragem_poste*`, `tests/integration/test_ficha_poste_cadeia.py`, `tests/integration/test_golden_padrao_e07*`, `tests/fixtures/golden_padrao_e07*`, nem `tests/conftest.py`.
- Gasto máximo por folha: alvo de 300.000 (D15; a 016 está em 206.853). Todo laço paga orçamento.
- Testador e desenvolvedor não commitam arquivos sob `.superpowers/`.

## Review Focus

1. Disco vermelho sem curva ou caixa dupla (poste, aterramento, ponto) não casa; marca dentro de outro desenho que não o disco não casa; `_coberto_depois` e `_palavra_sobre_o_disco` continuam valendo (Task 3).
2. Curva fusível fora de disco (v002) não vira esta classe nem sai em dobro com o disco (Task 3).
3. Ghostscript com o disco em 2 caminhos (preenchimento + traço de fecho) e o conteúdo duplicado (polilinhas e pontos em preenchimento + traço) casa uma vez, sem duplicar (Task 3).
4. `terminal_disc` e as demais gramáticas continuam com a mesma saída (Tasks 2 e 3; provado por folha na medição).
5. Página hostil com milhares de discos e polilinhas → `TetoGramaticasExcedido` pelo orçamento (Task 5). Exemplar de legenda é limite conhecido: a gramática não tem guarda de legenda, como as demais do modelo.

## Decisões do plano

- **R-E06.3.5-1, tipo `disc_mark`:** campos exatos `{"kind": "disc_mark", "fill": "red", "content": "fuse_curve" | "double_box", "min_span": número em (0, 72], "max_span": número em (0, 72]}`, com `min_span < max_span`. Entra no validador, no schema `docs/schemas/pacotes-simbologia.schema.json`, em `_GRAMMARS`, em `_GRAMMAR_FIELD_VALIDATORS` e em `GRAMATICAS_SO_MODELO`.
- **R-E06.3.5-2, variantes habilitadas:** v017 (`fuse_curve`, 18 referências) e v019 (`double_box`, 1 referência). v018 e v020 (aberta, em verde) ficam `pending`, sem folha com a forma: nenhuma habilitação só por fixture. v001, v002, v040, v038 e v039 ficam `pending`: v002 nasce dentro de v017, e as demais não aparecem nas referências. Ruling em "Decisões para o usuário", junto com a correção do Escopo do roadmap, que falava em chevrons e curva sinuosa. Anel verde com cruz e X vermelho (folha 002) fica fora: classe indefinida na ficha.
  - **Estado de operação:** retirar o `reason` ("mecanismo e estado de contato exigem topologia local") e habilitar v017 e v019 afirma `operating_state: "Fechado"` pelo vermelho. A cor distingue v017 de v018 (aberta) na F02, e a posição operada não é situação de obra (`situation_note` do inventário trata de obra), por isso o vermelho basta aqui. Alternativas descartadas: manter `pending` (recall 0) e fundir aberta e fechada numa só (afirmaria menos, sem ganho). Ruling em "Decisões para o usuário". Com a opção ligada, EQUIPAMENTO_INTERRUPCAO é candidato a ativo (`interpretation_pipeline.py:605-617,1064`): vai ao "Para a E07.2.2".
- **R-E06.3.5-3, teto do disco:** `discos_candidatos` ganha o parâmetro `vao_maximo`, com default igual ao `_VAO_MAXIMO_DISCO` de hoje, que atravessa `_aspecto_redondo`, `_caixas_de_faixa`, `_disco_de_curva`, `_disco_da_pilha` e `_discos_de_faixas`. Só a nova gramática o aumenta, fixado em 72 (o limite do schema), porque os candidatos são calculados uma vez por página, antes das variantes, e `max_span` da variante filtra depois. `terminal_disc` chama sem o parâmetro e não muda. Todos os discos reais levantados são de curva, então a nova gramática pode usar só o caminho `_disco_de_curva`, se o laboratório confirmar, para não pagar `_pilhas_de_faixas` de novo. O laço de `de_curva` em `discos_candidatos`, que hoje não paga orçamento, passa a pagar.
- **R-E06.3.5-4, caixa:** o disco. O conteúdo (curva S, dois pontos terminais ou caixa dupla) só confirma a variante e entra em `componentes`.
- **R-E06.3.5-6, reconciliação no runner:** `_same_occurrence` não olha classe (`symbol_reconciliation.py:207-245`). Sobre o disco de 7,2 pt da 006, o legado lê ATERRAMENTO. O teste da Task 4 usa uma observação de outra classe sobre o disco e **fixa o resultado observado** (funde, com `symbol_class=None`, ou não funde), com asserção sem disjunção. O desfecho vai ao "Para a E07.2.2".
- **R-E06.3.5-5, critério "acima do atual":** o atual tem 0/0/20, por centro (IoU registrado). **Vitória:** precisão e recall da classe maiores que 0, com tp ≥ 18 e FP brutos ≤ 3, triados em render. Leituras erradas: 0 **novas**; as 2 de hoje (002 e 006) continuam e vão ao handoff. Demais classes iguais por folha a `tmp/e06-3-4/final`, núcleo × motor 29/29, gasto ≤ 300.000, auditor sem erro.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`, `docs/schemas/pacotes-simbologia.schema.json` | tipo `disc_mark` | 1 |
| `tests/unit/test_gramatica_disc_mark_tipo.py` (novo) | validação, schema, motor ignora, perfil anuncia | 1 |
| testes de conjunto (`GRAMATICAS_SO_MODELO`): `tests/unit/test_gramatica_so_modelo.py`, `tests/unit/test_habilitacao_hastes_ataque.py`, `tests/unit/test_gramatica_rect_diagonal_tipo_ataque.py` | conjunto | 1 |
| `drawing_model/grammar_disc.py`, `tests/unit/test_grammar_disc_vao_maximo.py` (novo) | teto parametrizado, `terminal_disc` igual | 2 |
| `drawing_model/grammar_disc_mark.py` (novo), `drawing_model/symbol_matcher.py`, `src/zeny_project_handler_server/symbol_execution.py` | gramática, despacho, digest | 3 |
| `tests/fixtures/symbol_grammars/disc_mark.py` (novo), `tests/unit/test_grammar_disc_mark.py` (novo) | fixture, gramática | 3 |
| `symbol_packages/family-f02-20.json`, `model_symbols.py` | habilitação, versão 1.6.0 | 4 |
| testes de contagem (52 → 54, 371 → 369) e de versão: `tests/server/test_e14_symbol_review.py`, `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/unit/test_gramatica_so_modelo_ataque.py`, `tests/unit/test_habilitacao_hastes_ataque.py`, `tests/unit/test_gramatica_rect_diagonal_tipo_ataque.py`, `tests/integration/test_haste_costuras_etapa_testador.py`, `tests/integration/test_model_symbols_bt_runner_ataque.py`, `tests/integration/test_model_symbols_haste_ataque.py`, `tests/unit/test_habilitacao_bt_ataque.py`, `tests/unit/test_model_symbols.py`, `tests/unit/test_model_symbols_componentes_ataque.py`, `tests/integration/test_model_symbols_estai_ataque.py`, `tests/integration/test_model_symbols_estai_runner.py` | contagens e versão | 4 |
| `tests/integration/test_model_symbols_disc_mark_runner.py` (novo) | variantes reais, opção desligada, sem duplicar, reconciliação (R-6) | 4 |
| `tests/unit/test_grammar_disc_mark_teto.py` (novo), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py` | teto, guarda e pureza (o teste novo da Task 4 entra na guarda pelo testador de etapa, porque nasce na mesma onda) | 5 |

**Ondas:** Tasks 1 e 2 em paralelo (arquivos disjuntos); laboratório sobre as duas; Task 3; depois {4, 5}; testador de etapa; medição do orquestrador. Etapa em paralelo: E07.2.1 (e a E07.2.2, ao abrir, com verificação no plano dela). Soma: 25 + 20 + 45 + 40 + 20 = 2h30, mais o laboratório (60 min), que corre sem dividir porque as tarefas ficam em cerca de 3h. Vale a regra de estouro de 4h30 do protocolo; o relógio começa em 1e8d608.

## Laboratório (depois da Task 1)

- **Base:** a branch da etapa com as Tasks 1 e 2 integradas. Worktree destacado por hipótese; cada `desenvolvedor` implementa e mede, sem commitar e sem a suíte inteira, com o `.venv` da etapa e `PYTHONPATH=<worktree>/src`.
- **Hipóteses** (duas, por haver outra etapa aberta):
  - **H-1, disco como semente:** `discos_candidatos` com o vão maior (R-3), vermelho por `cor_canonica`, e conteúdo confirmado na grade (duas polilinhas pretas de 10+ segmentos e dois pontos pretos para `fuse_curve`; para `double_box`, o `double_box` observado na 008, retângulo `llll` com a linha `l`, definido pela geometria real).
  - **H-2, curva como semente:** polilinhas de 10+ segmentos e dois pontos pretos dentro de um disco; o gasto na 016 precisa caber no alvo.
- **Comandos:** `python -m scripts.benchmark_simbolos_ficha --rodada <rodada E03> --saida <checkout principal>/tmp/laboratorio/e06-3-5/<hipotese>/iter-<k> --metodo modelo --processos 6`, e `scripts.diff_simbolos_nucleo_motor` no fim.
- **Métrica e vitória:** R-E06.3.5-5, mais tp por folha, tamanho do disco por folha e gasto máximo.
- **Parada:** 60 min por hipótese. Se nenhuma vencer, a etapa estaciona (D20).
- **Entrega:** em `<checkout principal>/tmp/laboratorio/e06-3-5/<hipotese>/`: `patch.diff`, `metricas.json`, `conclusoes.md` e os recortes dos FP em PNG.

## Tasks

### Task 1: Tipo `disc_mark`

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** alto

**Files:** os da linha "1" da File Structure.

**Interfaces:** Produces: `GRAMMAR_DISC_MARK = "disc_mark"` e o validador de R-E06.3.5-1.

- [ ] **Step 1: Testes falhando:** aceita a forma exata; recusa `kind` errado, campo extra, `fill` fora do conjunto, `content` fora do conjunto, `min_span` ou `max_span` fora de (0, 72] ou de tipo errado (`bool` incluso), `min_span >= max_span`; o motor ignora; o perfil do modelo anuncia.
- [ ] **Step 2:** implemente validador, schema e conjunto; ajuste só as asserções de conjunto.
- [ ] **Step 3:** testes e auditor → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 2: Teto parametrizado do disco

**Estimativa:** 20 min · **Depende de:** nenhuma · **Risco:** alto

**Files:** os da linha "2" da File Structure.

**Interfaces:** Produces: `discos_candidatos(contexto, *, vao_maximo: float = _VAO_MAXIMO_DISCO)` (R-E06.3.5-3).

- [ ] **Step 1: Testes falhando:** com o default, a saída é idêntica à atual (`terminal_disc`, com as fixtures de PONTO_CONEXAO); com `vao_maximo=72`, disco de 14,4 pt passa; `_caixas_de_faixa` respeita o parâmetro; o laço de `de_curva` paga orçamento. → FAIL.
- [ ] **Step 2:** implemente conforme R-E06.3.5-3, sem mudar a chamada de `terminal_disc`.
- [ ] **Step 3:** testes e `scripts.diff_simbolos_nucleo_motor` → PASS; demais classes iguais.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 3: Gramática de disco com marca

**Estimativa:** 45 min · **Depende de:** laboratório · **Risco:** alto · **Laboratório:** sim

**Files:** os da linha "3" da File Structure.

**Interfaces:** Produces: `disc_mark_candidatos(contexto) -> tuple[CandidatoDiscMark, ...]` e `casa_disc_mark(contexto, gramatica, *, candidatos) -> list[tuple[Caixa, int, tuple[int, ...]]]`, com `CandidatoDiscMark` dataclass frozen com `contexto`, `caixa`, `caminho_ancora`, `componentes` e `content`, e `ValueError` para candidato de outro contexto. Parte de `<checkout principal>/tmp/laboratorio/e06-3-5/<vencedora>/patch.diff`, sem a habilitação no JSON.

- [ ] **Step 1: Testes** dos itens 1 a 3 do Review Focus, positivos (fuse_curve e double_box em 5, 7,2, 10 e 14,4 pt) e negativos, fixture sintética; `terminal_disc` igual ao atual. → FAIL.
- [ ] **Step 2:** implemente a partir do patch, com todo laço pagando orçamento.
- [ ] **Step 3:** testes focados e benchmark do laboratório → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 4: Habilitação e versão 1.6.0

**Estimativa:** 40 min · **Depende de:** 3 · **Risco:** alto

**Files:** os da linha "4" da File Structure.

**Interfaces:** Produces: `_VERSAO = "1.6.0"`.

- [ ] **Step 1:** habilite v017 e v019 conforme R-E06.3.5-2, com `min_span` e `max_span` do laboratório, retirando o `reason` só dessas.
- [ ] **Step 2: Teste de integração:** com os pacotes reais e a fixture, uma observação por desenho, sem duplicar com a curva; opção desligada sem observação do método; reconciliação (R-E06.3.5-6), com asserção do desfecho observado.
- [ ] **Step 3:** ajuste contagens e versão; `scripts.audit_symbol_packages` → `errors []`.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 5: Teto, guarda e pureza

**Estimativa:** 20 min · **Depende de:** 3 · **Risco:** normal

**Files:** os da linha "5" da File Structure.

**Interfaces:** Consumes: `disc_mark_candidatos`, `casa_disc_mark`, `OrcamentoConsultas`.

- [ ] **Step 1:** classificação uma vez por candidato; linearidade com 10 e 100 desenhos; página hostil com limite calibrado pelo gasto linear medido, com controle negativo e validação por mutação de cada `gastar`.
- [ ] **Step 2:** `grammar_disc_mark.py`, a fixture, `test_grammar_disc_mark.py`, `test_gramatica_disc_mark_tipo.py`, `test_grammar_disc_vao_maximo.py` e `test_grammar_disc_mark_teto.py` em `_GRAMATICAS_NOVAS`; pureza do núcleo inclui o arquivo. O teste novo da Task 4 entra pelo testador de etapa.
- [ ] **Step 3: Commit**; suíte inteira uma vez antes do relatório.

## Operação do orquestrador (fora das tarefas)

Medição final: `scripts.benchmark_simbolos_ficha ... --metodo atual --metodo modelo --saida <checkout principal>/tmp/e06-3-5/final`, `scripts.diff_simbolos_nucleo_motor` e auditor. `check_test_integrity --base 1e8d608`, `osv-scanner`, testador de etapa (Task 5 é `normal`), revisão final, gate `cmd.exe //c ".\\IniciarTestes.bat"`. O handoff registra a correção do Escopo do roadmap (chevrons pelas referências), R-2 (v017, v019 e a afirmação de estado), R-5, R-6, as 2 leituras erradas preexistentes (002 e 006), a tabela de suporte, os discos de 5 pt que colidem com a paleta da E07.2.1, as variantes habilitadas sem positivo autoral na matriz (`owner_stage: "E07"`, `coverage_matrix_e16.py:242-250`) e o "Para a E07.2.2".
