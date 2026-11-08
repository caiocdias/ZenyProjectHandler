# E06.3.3.2.1 — Marcas: envolvente e X: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fazer a situação (variante) da haste com barras e do retângulo com diagonal sair certa nas folhas reais. A envolvente passa a ser vista, e o X passa a ser o do próprio símbolo. O plano também mede a concordância de situação contra a ficha e fecha os itens herdados da E06.3.3.1.

**Architecture:** o conserto vive em `drawing_model/grammar_marcas.py`, compartilhado pelas duas gramáticas:
- os contornos elípticos passam a vir também dos subcaminhos fechados de caminhos de traço. Hoje vêm só de polilinha fechada, e `reconstruir_polilinhas` parte a polilinha quando a elipse é um subcaminho de dezenas de retas;
- o X exige que os braços se cruzem perto do símbolo, por um critério medido nas folhas;
- `MarcasDaPagina` guarda o contexto, e as gramáticas recusam marcas de outro contexto.

O benchmark de símbolos ganha a concordância entre a situação predita e a situação anotada na ficha, para o `atual` e o `modelo`. O método sobre o modelo sobe para 1.3.0. Alternativa descartada: consertar no modelo (o leitor guardar o `closePath`, ou `reconstruir_polilinhas` preservar o subcaminho). Isso subiria `VERSAO_MODELO_DESENHO` e mudaria as primitivas de todas as gramáticas e do cache.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só adaptadores, scripts e fixtures), pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3.3.2" (divisão) e "E06.3.3.2.1"; o handoff da E06.3.3.1 ("Para a E06.3.3.2"); os planos `docs/superpowers/plans/2026-11-07-leitura-vetorial-por-poste-e06-3-2-2.md` e `2026-11-08-leitura-vetorial-por-poste-e06-3-3-1.md` (R-2/R-3 das gramáticas); ADR 0006 e 0016.

## Global Constraints

- Arquitetura hexagonal: o núcleo `drawing_model/` não importa PyMuPDF; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- Nenhuma migração, API ou DTO. O método sobre o modelo liga só no runner opt-in (D12). O analisador padrão, o motor antigo e o legado não mudam.
- ADR 0006: `declarative-drawing-model` 1.2.0 → 1.3.0 no commit que muda a saída (Task 1).
- Sem dependência nova. Fixture sintética positiva e negativa, sem coordenada, hash ou nome de folha real (guarda de fonte por AST e tokenize).
- Nada lê `examples/avaliacao-cega/`; as referências da rodada E03 estão congeladas.
- Pytest com `--strict-markers` e `ResourceWarning` como erro; testes sem dependência de ordem; mypy strict, ruff, format, complexidade < 31.
- Não tocar `scripts/benchmark_ficha_poste.py` nem `tests/conftest.py`.
- **Gasto máximo por folha: 200.000 é teto rígido nesta etapa.** A 016 está em 192.308. Se uma tarefa passar disso, ela otimiza ou reporta DONE_WITH_CONCERNS; o alvo não sobe aqui.
- Worktree da etapa com `.venv`. Em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` da etapa; a suíte inteira usa `-n` = 20 ÷ suítes ativas.

## Review Focus

1. Elipse desenhada como subcaminho fechado de dezenas de retas, inclusive no mesmo caminho do retângulo do BT ou com um traço encostado → vira contorno elíptico, e a variante com envolvente casa. Polígono fechado não elíptico, elipse aberta e polígono fechado **preenchido** → não viram contorno nem pagam (Task 1).
2. X de outro símbolo perto do pictograma → não marca retirada; o X do próprio símbolo continua marcando. Os dois casos seguem o critério medido nas folhas (Task 3).
3. Classe e caixas que não dependem da envolvente não mudam: tp/fp/fn por classe e folha sem piora, e o diff núcleo × motor fica igual (Task 5).
4. Referência sem situação anotada fica fora da concordância. O texto livre da ficha é normalizado. Variante com `situation` vazia ou "N/A" vai para um balde próprio (Task 2).
5. `MarcasDaPagina` de outro contexto → `ValueError` nas duas gramáticas (Task 3).

## Decisões do plano

- **R-E06.3.3.2.1-1, envolvente por subcaminho:**
  - **Fonte:** `grammar_marcas._contornos` examina também os subcaminhos de **caminhos de traço** (`tipo == "traco"`). Entram só os que passam primeiro no filtro estrutural barato: pelo menos `_VERTICES_MINIMOS_ELIPSE` itens de reta e fechamento dentro de `_TOLERANCIA_FECHAMENTO` (constante nomeada; o valor sai da medição do Step 0 da Task 1).
  - **Critério:** o mesmo critério elíptico de hoje. Cada subcaminho que passa no filtro paga 1, e quem não passa não paga.
  - **Duplicata:** a mesma elipse vinda de polilinha, de moldura e de subcaminho vira um contorno só.
  - **Exclusão:** resolve-se só em `grammar_marcas`, sem mudar o que as gramáticas passam em `proprios: frozenset[int]`.
    - O campo `caminhos` de `Contorno` fica como está. `test_grammar_marcas.py:93`, `grammar_stem.py:435` e `grammar_rect_diagonal.py:255` o leem.
    - A origem entra como campo novo: polilinha, moldura ou subcaminho, e o índice do subcaminho.
    - Um contorno de subcaminho elíptico (≥ `_VERTICES_MINIMOS_ELIPSE` retas) nunca é o retângulo nem um traço da haste. Por isso a checagem de `proprios` não o descarta quando o caminho dele coincide com um caminho próprio.
  - Os limiares elípticos não mudam.
- **R-E06.3.3.2.1-2, X perto do símbolo:**
  - o critério sai da medição do Step 0 da Task 3: nas 16 folhas, a distância do cruzamento ao centro do pictograma, relativa à escala, para os X próprios (v004/v003 que o desenho confirma) e para os 3 X de vizinho da E06.3.3.1;
  - candidatos: cruzamento dentro do pictograma sem margem, ou a até `k × escala` da âncora;
  - escolhe-se o que separa os dois grupos com folga, e `tem_x` passa a exigi-lo;
  - a fixture é relativa à escala;
  - critério de parada: os 3 casos de X de vizinho perdem a marca de X (nem v003 nem v004) e nenhum tp com X próprio se perde. Se nenhum critério separa, DONE_WITH_CONCERNS com a medição.
- **R-E06.3.3.2.1-3, guarda de contexto:** `MarcasDaPagina` expõe `contexto` (só leitura). `hastes_candidatas` e `retangulos_candidatos` levantam `ValueError` quando `marcas.contexto is not contexto`.
- **R-E06.3.3.2.1-4, concordância de situação:**
  - **Predição:** cada predição do benchmark passa a levar `variante: str | None` e `situacoes_preditas: frozenset[str]` (normalizadas e vazias quando não há), porque uma variante pode declarar várias situações. A regra: a predição é concordante se a situação normalizada da ficha está no conjunto. As fontes são estas:
    - a variante vem do `template` da observação ou de `provenance.variant_id` (pacotes no `atual`);
    - a situação vem da `situation` do legado ou das situações da variante no inventário;
    - sem nenhuma das duas, a variante fica `None` e o conjunto fica vazio.
  - **Normalização:** a situação da ficha (`atributos_extras.situacao`) e a predita passam por minúsculas, sem acento, `_` → espaço, e só o prefixo antes de parêntese.
  - **Métrica:** por classe e método, sobre os TP (critério `centro`) cuja referência tem situação anotada: `concordantes` / (`concordantes` + `discordantes`).
  - **Baldes à parte**, decididos na métrica:
    - `sem_situacao_ficha`: a referência não tem situação anotada;
    - `situacao_nao_declarada`: `variante` não nula com `situacoes_da_variante(variante) is None`, isto é, `situation` vazia (`[]`) ou "N/A";
    - `sem_situacao_predita`: o conjunto vazio fora do caso anterior.

    O teste dos três baldes cobre a variante com `situation: []`.
  - **Saída:** a chave aditiva se chama `concordancia_situacao`, para não confundir com `metodos.<m>.situacao`. O inventário é carregado pelo caminho do módulo, sem depender do cwd.
- **R-E06.3.3.2.1-5, itens herdados do BT (E06.3.3.1):**
  - todos os caminhos de `origens` do retângulo entram nos componentes, com a âncora em `origens[0]`;
  - a diagonal passa a exigir a cor canônica do retângulo, se o benchmark não perder tp de PARA_RAIOS_BT; senão o comportamento fica, com ruling;
  - entra um negativo de célula de tabela. Se ele casar, entra um lado maior máximo de 2 × o maior lado de corpo de BT medido nas 16 folhas (o valor e a origem vão para o relatório), desde que não derrube tp;
  - **a haste de ligação que sai da envolvente** (R-E06.3.3.1-3, `_haste_de_ligacao`) passa a ser buscada a partir da borda da envolvente, alinhada ao corpo, e entra nos componentes;
  - `raises=AssertionError` nos três xfail estritos de `test_grammar_rect_diagonal_ataque.py`. O do X curto vira teste normal se a Task 3 o resolver.
- **R-E06.3.3.2.1-6, critério de aceite:**
  1. tp/fp/fn por classe do `modelo` sem piora em nenhuma folha em relação a `tmp/e06-3-3-1/simbolos/simbolos-ficha.json`;
  2. triagem em render, pelo orquestrador, dos 10 tp de PARA_RAIOS_BT: a variante predita é a do desenho (envolvente e X). As 3 v004 indevidas da E06.3.3.1 somem;
  3. amostra de 5 tp de haste com envolvente desenhada: saem v002/v003 ou v006/v007;
  4. a concordância de situação da soma de ATERRAMENTO, PARA_RAIOS_MT e PARA_RAIOS_BT (taxa, R-4) fica **estritamente maior** que a de antes, como pede o roadmap. Em dois casos isso não se aplica: a de antes já é 100%, ou nenhuma referência anotada tem envolvente ou X no desenho. Nesses casos, o orquestrador registra uma ruling, os critérios 2 e 3 sustentam o aceite e a ruling vai a "Decisões para o usuário". A taxa e as contagens vão ao handoff;
  5. leitura errada de fato = 0, o diff igual ao congelado, gasto ≤ 200.000.
- **R-E06.3.3.2.1-7, situação no runner (para a E07):** `model_symbols._observacao` não preenche `situacao`, então no runner a situação é derivável da variante, mas fica pendente. Onde mora o mapa variante → situação (no adaptador ou no consumidor) é decisão da E07, e vai ao handoff.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_marcas.py` | envolvente por subcaminho e origem do contorno (1); X perto e guarda (3) | 1, 3 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | versão 1.3.0 | 1 |
| `tests/unit/test_grammar_marcas_envolvente.py` (novo) | envolvente por subcaminho | 1 |
| `tests/unit/test_model_symbols.py`, `tests/unit/test_model_symbols_componentes_ataque.py`, `tests/integration/test_haste_costuras_etapa_testador.py`, `tests/integration/test_model_symbols_haste_ataque.py`, `tests/unit/test_habilitacao_bt_ataque.py`, `tests/integration/test_model_symbols_bt_runner_ataque.py:25` | versão 1.2.0 → 1.3.0 (o desenvolvedor confirma as linhas com `grep -rn '"1.2.0"' tests`) | 1 |
| `scripts/simbolos_ficha_metricas.py`, `scripts/simbolos_ficha_relatorio.py`, `scripts/benchmark_simbolos_ficha.py` | variante e situação na predição; concordância | 2 |
| `tests/unit/test_situacao_concordancia.py` (novo) | concordância e normalização | 2 |
| `tests/unit/test_benchmark_simbolos_modelo.py:48`, `tests/unit/test_benchmark_simbolos_modelo_ataque.py:388` | as chaves `variante` e `situacoes_preditas` nas predições | 2 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py`, `drawing_model/grammar_rect_diagonal.py` | guarda de contexto | 3 |
| `tests/unit/test_grammar_marcas_x_contexto.py` (novo) | X perto do símbolo e guarda | 3 |
| `drawing_model/grammar_rect_diagonal.py`, `tests/fixtures/symbol_grammars/rect_diagonal.py`, `tests/unit/test_grammar_rect_diagonal.py`, `tests/unit/test_grammar_rect_diagonal_ataque.py` | itens herdados do BT | 4 |

Ondas:
- Onda A, Tasks 1 e 2 (disjuntas). O orquestrador integra a Task 2 primeiro, mede a concordância de antes e depois integra a Task 1.
- Task 3.
- Task 4.
- Testador de etapa (D8: uma vez por etapa; as Tasks 1, 3 e 4 mexem no mesmo módulo compartilhado).
- Task 5 (medição).

Soma: 3h00 (40 + 40 + 40 + 35 + 25). O relógio conta desde 0529544. Os Step 0 e o testador de etapa ficam fora da soma, que está no limite do orçamento: o orquestrador acompanha o relógio por tarefa e vale a regra de estouro de 4h30.

## Revisão de arquitetura

- **Veredito:** aprovado com notas.
- **Rodadas:** 2. A rodada 0 bloqueou com I-1 a I-6, a rodada 1 com N-I1, e a rodada 2 aprovou com notas.
- **Modelo:** opus (revisor-arquitetura).
- **Nota Menor da rodada 2:** havia contradição entre `None` e o conjunto vazio da situação predita, e os baldes `sem_situacao_predita` e `situacao_nao_declarada` se confundiam. Já foi aplicada no texto da R-4.
- **Menores aceitos como estão:** M-10, a nota de `grammar_frames.py`, que é da E06.3.3. N-M5, o orçamento no limite: o orquestrador acompanha o relógio por tarefa.

## Tasks

### Task 1: Envolvente por subcaminho fechado e versão 1.3.0

**Estimativa:** 40 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não (Step 0 mede antes de implementar)

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_marcas.py`, `src/zeny_project_handler/adapters/analysis/model_symbols.py`
- Create: `tests/unit/test_grammar_marcas_envolvente.py`
- Modify (só a versão): os arquivos de teste listados na File Structure

- [ ] **Step 0: Medir na folha real** (sem commit). Com `pagina_para_gramaticas` nas folhas 005 e 001, que têm BT e haste com envolvente, descubra em `modelo.caminhos`:
  - como a elipse está: em quantos subcaminhos, com quantos itens, de que tipo (traço ou preenchimento);
  - se fecha por reta explícita ou não, e a distância entre o primeiro e o último ponto;
  - se divide o caminho com o retângulo ou com a haste.

  Fixe `_TOLERANCIA_FECHAMENTO` a partir disso, com folga, e registre no relatório. Pare e reporte NEEDS_CONTEXT com a medição em dois casos:
  - a elipse não é subcaminho de retas;
  - o tipo medido não é `traco`, por exemplo `traco_e_preenchimento`. O orquestrador decide então se esse tipo entra de forma explícita.
- [ ] **Step 1: Escrever os testes** com páginas puras (`tests/fixtures/symbol_grammars/paginas.py`), no formato medido no Step 0:
  - elipse como subcaminho fechado de dezenas de retas, com um traço encostado → um contorno;
  - elipse no mesmo caminho do retângulo do BT → a envolvente casa;
  - haste da fixture `stem_bars.py` dentro dela → v002/v006; sem a elipse → base;
  - retângulo e octógono irregular fechados → nenhum contorno elíptico;
  - elipse aberta → nenhum;
  - polígono elíptico fechado **preenchido** → nenhum, e não paga;
  - a mesma elipse vinda de polilinha e de subcaminho → um contorno só;
  - gasto: 1 por subcaminho que passa no filtro estrutural.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar** (R-1) e a versão.
- [ ] **Step 4: Rodar:**
  - os testes novos, `tests/unit/test_grammar_marcas*.py`, `tests/unit/test_grammar_stem*.py`, `tests/unit/test_grammar_rect_diagonal*.py`, `tests/unit/test_model_symbols*.py` e `tests/integration/test_model_symbols*.py`;
  - ruff, format, mypy e complexidade;
  - o benchmark e o diff com as variantes reais (`--processos 10`, saída em `<checkout principal>/tmp/e06-3-3-2-1/task1-*`). Cole tp/fp/fn por classe, a distribuição de variantes de ATERRAMENTO, PARA_RAIOS_MT e PARA_RAIOS_BT e o gasto máximo.

  **Portão:** os BT e as hastes com envolvente desenhada (as folhas do Step 0) saem com variante de envolvente, e o gasto fica ≤ 200.000. Senão, DONE_WITH_CONCERNS. Dourados de gasto da haste que mudarem (`test_grammar_marcas_ataque.py`, `test_grammar_marcas.py`): DONE_WITH_CONCERNS com os valores, sem editar os dourados.
- [ ] **Step 5: Commit** (`feat: envolvente lida do subcaminho fechado e versao 1.3.0`).

### Task 2: Concordância de situação no benchmark

**Estimativa:** 40 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `scripts/simbolos_ficha_metricas.py`, `scripts/simbolos_ficha_relatorio.py`, `scripts/benchmark_simbolos_ficha.py`
- Create: `tests/unit/test_situacao_concordancia.py`
- Modify: `tests/unit/test_benchmark_simbolos_modelo.py:48` (o conjunto de chaves da predição ganha `variante` e `situacoes_preditas`) e `tests/unit/test_benchmark_simbolos_modelo_ataque.py:388` (o dicionário esperado do `atual` ganha as duas chaves com os valores certos; o resto fica igual)

**Interfaces:**
- Produces:
  - `normalizar_situacao(texto: str | None) -> str | None`;
  - `situacoes_da_variante(variante_id: str) -> frozenset[str] | None`, com `None` para "não declarada";
  - as predições com `variante` e `situacoes_preditas`;
  - a chave `concordancia_situacao` por bloco de critério, somada pelos agregadores (R-4);
  - uma linha no `.md`.

- [ ] **Step 1: Testes:**
  - a normalização dos textos reais ("proposto instalar (verde, círculo…)", "existente (barras pretas…)", `proposto_instalar`) e de `None`;
  - concordância: com variante do modelo, com `situation` do legado e com `variant_id` dos pacotes;
  - discordância;
  - os três baldes;
  - agregação de duas folhas;
  - a chave nova não muda as existentes.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar** os novos, os dois arquivos alterados, `tests/unit/test_benchmark_simbolos_ficha*.py` e `tests/unit/test_leituras_erradas*.py`, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: concordancia de situacao no benchmark de simbolos`).

### Task 3: X perto do símbolo e guarda de contexto

**Estimativa:** 40 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não (Step 0 mede e escolhe)

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_marcas.py`, `drawing_model/grammar_stem.py`, `drawing_model/grammar_rect_diagonal.py`
- Create: `tests/unit/test_grammar_marcas_x_contexto.py`

- [ ] **Step 0: Medir** (R-2). Nas 16 folhas, com o código da Task 1, levante a distância do cruzamento ao centro do pictograma, relativa à escala:
  - dos X próprios de haste e de BT, confirmados em render;
  - dos 3 X de vizinho da E06.3.3.1, que estão em `tmp/e06-3-3-1/task3-render-bt/` do checkout principal, ou que você reidentifica.

  Escolha o critério que separa os dois grupos com folga e registre-o no relatório.
- [ ] **Step 1: Testes**, relativos à escala:
  - X de vizinho na faixa medida → sem retirada, nas duas gramáticas;
  - X próprio → marca;
  - X na borda do critério: dentro marca, fora não;
  - marcas de outro contexto → `ValueError` em `hastes_candidatas` e em `retangulos_candidatos`;
  - mesmo contexto → funciona.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar** (R-2, R-3).
- [ ] **Step 4: Rodar** os testes das três gramáticas e de `grammar_marcas`, ruff, format, mypy e complexidade; e o benchmark e o diff (`task3-*`).

  **Portão:** os 3 casos de X de vizinho perdem a marca de X (não saem v003 nem v004), nenhum tp com X próprio se perde e o gasto fica ≤ 200.000. Senão, DONE_WITH_CONCERNS com a medição. Dourados que mudarem: DONE_WITH_CONCERNS com os valores.
- [ ] **Step 5: Commit** (`feat: x de retirada perto do simbolo e marcas do mesmo contexto`).

### Task 4: Itens herdados do retângulo com diagonal

**Estimativa:** 35 min · **Depende de:** Task 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_rect_diagonal.py`, `tests/fixtures/symbol_grammars/rect_diagonal.py`, `tests/unit/test_grammar_rect_diagonal.py`, `tests/unit/test_grammar_rect_diagonal_ataque.py`

- [ ] **Step 1: Testes** (R-5):
  - retângulo montado de 4 caminhos → os que não são âncora entram nos componentes;
  - diagonal de cor diferente da do retângulo → não casa. Isso só vale se o Step 4 não perder tp; senão, o teste fixa o comportamento atual e o relatório diz por quê;
  - negativo de célula de tabela;
  - haste de ligação que sai da envolvente (v002 e v003), alinhada ao corpo → entra nos componentes e em `proprios`;
  - `raises=AssertionError` nos três xfail estritos. O do X curto vira teste normal se a Task 3 o resolveu.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar** os arquivos, ruff, format, mypy e complexidade; e o benchmark (`task4-*`), com tp de PARA_RAIOS_BT.
- [ ] **Step 5: Commit** (`fix: itens herdados do retangulo com diagonal`).

### Task 5: Medição (orquestrador)

**Estimativa:** 25 min · **Depende de:** Tasks 1 a 4 e o testador de etapa · **Risco:** normal

- [ ] **Concordância de antes:** na branch só com a Task 2 integrada, rode o benchmark `atual` e `modelo` com saída em `<checkout principal>/tmp/e06-3-3-2-1/antes`.
- [ ] **Depois:** com as Tasks 1 a 4 integradas, rode o benchmark (`.../depois`) e o diff (`.../diff`), contra R-6.
- [ ] **Triagem em render:** os 10 tp de PARA_RAIOS_BT e 5 tp de haste com envolvente, conferindo a variante.
- [ ] **Auditor:** `errors []` e 34.

## Fechamento operacional

- Suíte inteira por onda; testador de etapa; `osv-scanner`; `check_test_integrity --base <base da etapa>`; revisão final; `.\IniciarTestes.bat`.
- Handoff com:
  - a concordância de antes e depois (taxa e contagens), a distribuição de variantes e o gasto;
  - o critério do X e a tolerância de fechamento medidos;
  - o bloco "Para a E06.3.3.2.2": a envolvente do transformador pelo mesmo caminho, e o fato de que Rede, Dedicado e IP não se distinguem pela forma;
  - o bloco "Para a E07": R-7, situação no runner;
  - em "Decisões para o usuário": o teto de gasto como requisito não funcional. A folga é cumulativa e o transformador vem a seguir.
