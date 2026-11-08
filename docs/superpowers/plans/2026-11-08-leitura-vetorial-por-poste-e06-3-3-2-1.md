# E06.3.3.2.1 — Marcas: envolvente e X: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fazer a situação (variante) da haste com barras e do retângulo com diagonal sair certa nas folhas reais — a envolvente passa a ser vista e o X passa a ser o do próprio símbolo —, medir a concordância de situação contra a ficha e fechar os Menores herdados da E06.3.3.1.

**Architecture:** o conserto vive em `drawing_model/grammar_marcas.py`, compartilhado pelas duas gramáticas: os contornos elípticos passam a vir também dos subcaminhos fechados dos caminhos (hoje só de polilinha fechada, que `reconstruir_polilinhas` parte quando a elipse é um subcaminho de dezenas de retas), e o X exige o cruzamento dos braços perto do pictograma. `MarcasDaPagina` guarda o contexto e as gramáticas recusam marcas de outro. O benchmark de símbolos ganha a concordância entre a situação da variante predita (inventário) e a situação anotada na ficha. O método sobre o modelo sobe para 1.3.0.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só adaptadores, scripts e fixtures), pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3.3.2" (divisão) e "E06.3.3.2.1"; o handoff da E06.3.3.1 ("Para a E06.3.3.2"); os planos `docs/superpowers/plans/2026-11-07-leitura-vetorial-por-poste-e06-3-2-2.md` e `2026-11-08-leitura-vetorial-por-poste-e06-3-3-1.md` (R-2/R-3 das gramáticas); ADR 0006 e 0016.

## Global Constraints

- Arquitetura hexagonal; o núcleo `drawing_model/` não importa PyMuPDF; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- Nenhuma migração, API ou DTO; o método sobre o modelo liga só no runner opt-in (D12); o analisador padrão e o motor antigo não mudam.
- ADR 0006: `declarative-drawing-model` 1.2.0 → 1.3.0 no commit que muda a saída (Task 1).
- Sem dependência nova. Fixture sintética positiva e negativa; nenhuma coordenada, hash ou nome de folha real (guarda de fonte por AST e tokenize).
- Nada lê `examples/avaliacao-cega/`; referências da rodada E03 congeladas.
- Pytest com `--strict-markers` e `ResourceWarning` como erro; sem dependência de ordem; mypy strict, ruff, format, complexidade < 31.
- Não tocar `scripts/benchmark_ficha_poste.py` nem `tests/conftest.py`.
- Worktree da etapa com `.venv`; em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` da etapa; a suíte inteira usa `-n` = 20 ÷ suítes ativas.

## Review Focus

1. Elipse desenhada como um subcaminho fechado de dezenas de retas (com outro traço encostado nela) → vira contorno elíptico e a variante com envolvente casa; polígono fechado não elíptico (retângulo, hexágono) e elipse aberta → não (Task 1).
2. X de outro símbolo a alguns pontos do pictograma → não marca retirada; o X do próprio símbolo continua marcando (Task 3).
3. A classe e as caixas que não dependem da envolvente não mudam: tp/fp/fn por classe e folha sem piora, diff núcleo × motor igual (Task 5).
4. Referência sem situação anotada fica fora da concordância; texto livre da ficha ("proposto instalar (verde, círculo…)", "existente (barras…)", `proposto_instalar`) é normalizado (Task 2).
5. `MarcasDaPagina` de outro contexto → `ValueError` nas duas gramáticas (Task 3).

## Decisões do plano

- **R-E06.3.3.2.1-1, envolvente por subcaminho:** `grammar_marcas._contornos` passa a examinar também cada subcaminho fechado de `modelo.caminhos` com pelo menos `_VERTICES_MINIMOS_ELIPSE` itens de reta (ponto final igual ao inicial, a tolerância de fechamento do modelo), com o mesmo critério elíptico de hoje (desvio de raio ≤ `_DESVIO_RAIO_ELIPSE`); um contorno por caminho e subcaminho, deduplicado com os que já vêm de polilinha fechada e de moldura elíptica (mesma caixa arredondada); cada subcaminho examinado paga 1 do orçamento. Os limiares não mudam.
- **R-E06.3.3.2.1-2, X perto do símbolo:** `tem_x` só aceita o par de braços cujo ponto de cruzamento cai dentro do pictograma expandido por `_MARGEM_X × escala` (a margem que já define a janela). Haste e BT passam a ignorar o X de vizinho.
- **R-E06.3.3.2.1-3, guarda de contexto:** `MarcasDaPagina` expõe `contexto` (só leitura); `hastes_candidatas` e `casa_retangulos_diagonal`/`retangulos_candidatos` levantam `ValueError` quando `marcas.contexto is not contexto`.
- **R-E06.3.3.2.1-4, concordância de situação:** cada predição do benchmark passa a levar `variante` (o `template` da observação, quando há); por classe e método, para cada TP cuja referência tem `atributos_extras.situacao`, a situação da ficha é normalizada (minúsculas, sem acento, `_` → espaço, só o prefixo antes de parêntese: `existente`, `proposto instalar`, `proposto retirar`, `proposto substituir`, `abandonado`, `proposto abandonar`) e comparada com a lista `situation` da variante no inventário (normalizada igual). Saem `concordantes`, `discordantes` e `sem_situacao` por classe, folha e família, e uma linha no `.md`. Predição sem variante (o `atual`) conta como `sem_variante`. A concordância é medida antes (código da E06.3.3.1) e depois.
- **R-E06.3.3.2.1-5, Menores do BT (E06.3.3.1):** todos os caminhos de `origens` do retângulo entram nos componentes (âncora em `origens[0]`); a diagonal passa a exigir a cor canônica do retângulo se o benchmark não perder tp de PARA_RAIOS_BT (senão fica como está, com ruling); um negativo de célula de tabela (retângulo de proporção 2–4,5 cruzado por um líder inclinado) — se casar, entra um lado maior máximo por perfil; `raises=AssertionError` nos três xfail estritos de `test_grammar_rect_diagonal_ataque.py` (e o do X curto vira teste normal se a Task 3 o resolver).
- **R-E06.3.3.2.1-6, critério de aceite:**
  - tp/fp/fn por classe do `modelo` sem piora em nenhuma folha em relação a `tmp/e06-3-3-1/simbolos/simbolos-ficha.json`;
  - a concordância de situação de ATERRAMENTO, PARA_RAIOS_MT e PARA_RAIOS_BT (soma das 3) estritamente maior que a medida com o código da E06.3.3.1 (o mesmo script);
  - a distribuição de variantes dos tp passa a ter variantes com envolvente onde o desenho tem envolvente (amostra visual na Task 5);
  - leitura errada de fato = 0;
  - diff igual ao congelado; gasto máximo ≤ 200.000 (a 016 está em 192.308; se passar, a ruling segue a da E06.3.3.1 R-4).

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_marcas.py` | envolvente por subcaminho (1); X perto e guarda de contexto (3) | 1, 3 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py`, `tests/unit/test_model_symbols.py` e os 4 arquivos de ataque que fixam 1.2.0 | versão 1.3.0 | 1 |
| `tests/unit/test_grammar_marcas_envolvente.py` (novo) | envolvente por subcaminho | 1 |
| `scripts/simbolos_ficha_metricas.py`, `scripts/simbolos_ficha_relatorio.py`, `scripts/benchmark_simbolos_ficha.py` | variante na predição e concordância de situação | 2 |
| `tests/unit/test_situacao_concordancia.py` (novo) | concordância e normalização | 2 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py`, `drawing_model/grammar_rect_diagonal.py` | guarda de contexto | 3 |
| `tests/unit/test_grammar_marcas_x_contexto.py` (novo) | X perto do símbolo e guarda | 3 |
| `drawing_model/grammar_rect_diagonal.py`, `tests/fixtures/symbol_grammars/rect_diagonal.py`, `tests/unit/test_grammar_rect_diagonal.py`, `tests/unit/test_grammar_rect_diagonal_ataque.py` | Menores do BT | 4 |

Ondas: Onda A, Tasks 1 e 2 (disjuntas); o orquestrador integra a Task 2 primeiro e mede a concordância de antes, depois integra a Task 1; Task 3; Task 4; Task 5 (medição).

Soma: 2h50 (40 + 40 + 35 + 30 + 25). Relógio desde 0529544; vale a regra de estouro de 4h30.

## Tasks

### Task 1: Envolvente por subcaminho fechado e versão 1.3.0

**Estimativa:** 40 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_marcas.py`, `src/zeny_project_handler/adapters/analysis/model_symbols.py`
- Create: `tests/unit/test_grammar_marcas_envolvente.py`
- Modify (só a versão): `tests/unit/test_model_symbols.py`, `tests/unit/test_model_symbols_componentes_ataque.py`, `tests/integration/test_haste_costuras_etapa_testador.py`, `tests/integration/test_model_symbols_haste_ataque.py`, `tests/unit/test_habilitacao_bt_ataque.py` e outros que afirmem `"1.2.0"` (procure; liste no relatório)

**Interfaces:**
- Produces: contornos elípticos também de subcaminhos fechados (R-1); `_VERSAO = "1.3.0"`.

- [ ] **Step 1: Escrever os testes** com páginas puras (`tests/fixtures/symbol_grammars/paginas.py`): elipse como subcaminho fechado de 72 retas com um traço encostado → um contorno; o mesmo com a haste da fixture `stem_bars.py` dentro → a variante com envolvente (v002 e v006) casa, e sem a elipse a base; retângulo e hexágono fechados (≥ 8 lados não elípticos: octógono irregular) → nenhum contorno elíptico; elipse aberta (sem fechar) → nenhum; mesma elipse vinda de polilinha e de subcaminho → um contorno só; gasto: 1 por subcaminho examinado.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar** (R-1) e a versão.
- [ ] **Step 4: Rodar** os novos, `tests/unit/test_grammar_marcas*.py`, `tests/unit/test_grammar_stem*.py`, `tests/unit/test_grammar_rect_diagonal*.py`, `tests/unit/test_model_symbols*.py`, `tests/integration/test_model_symbols*.py`, ruff, format, mypy, complexidade; e o benchmark e o diff com as variantes reais (`--processos 10`, saída em `<checkout principal>/tmp/e06-3-3-2-1/task1-*`), colando tp/fp/fn por classe, a distribuição de variantes de ATERRAMENTO, PARA_RAIOS_MT e PARA_RAIOS_BT e o gasto máximo. Testes dourados de gasto da haste (`test_grammar_marcas_ataque.py`, `test_grammar_marcas.py`) que mudarem por causa do subcaminho: pare e reporte DONE_WITH_CONCERNS com os valores (não edite os dourados).
- [ ] **Step 5: Commit** (`feat: envolvente lida do subcaminho fechado e versao 1.3.0`).

### Task 2: Concordância de situação no benchmark

**Estimativa:** 40 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `scripts/simbolos_ficha_metricas.py`, `scripts/simbolos_ficha_relatorio.py`, `scripts/benchmark_simbolos_ficha.py`
- Create: `tests/unit/test_situacao_concordancia.py`

**Interfaces:**
- Produces: `simbolos_ficha_metricas.normalizar_situacao(texto: str) -> str | None`; `situacoes_da_variante(variante_id) -> frozenset[str]` (do inventário, carregado uma vez); a predição do benchmark leva `variante` (ou `None`); por bloco de critério, a chave aditiva `"situacao": {"concordantes": int, "discordantes": int, "sem_situacao": int, "sem_variante": int, "por_classe": {...}}`, somada pelos agregadores; uma linha no `.md`.

- [ ] **Step 1: Testes:** normalização dos textos reais citados em R-4 e de `None`; concordância com uma variante cuja `situation` contém a da ficha; discordância; referência sem situação; predição sem variante; agregação de duas folhas; a chave nova não muda as existentes.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar** os novos e `tests/unit/test_benchmark_simbolos_ficha*.py`, `tests/unit/test_leituras_erradas*.py`, ruff, format, mypy.
- [ ] **Step 5: Commit** (`feat: concordancia de situacao no benchmark de simbolos`).

### Task 3: X perto do símbolo e guarda de contexto

**Estimativa:** 35 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_marcas.py`, `drawing_model/grammar_stem.py`, `drawing_model/grammar_rect_diagonal.py`
- Create: `tests/unit/test_grammar_marcas_x_contexto.py`

- [ ] **Step 1: Testes:** X de vizinho a 5–19 pt do pictograma (o caso medido na E06.3.3.1) → sem marca de retirada, nas duas gramáticas; X do próprio símbolo → marca; X com o cruzamento na borda do pictograma expandido → marca, logo fora → não; marcas de outro contexto → `ValueError` em `hastes_candidatas` e na gramática do BT; mesmo contexto → funciona.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar** (R-2, R-3).
- [ ] **Step 4: Rodar** os testes das três gramáticas e de `grammar_marcas`, ruff, format, mypy, complexidade; benchmark e diff (`task3-*`), colando tp/fp/fn, distribuição de variantes e gasto. Dourados que mudarem: DONE_WITH_CONCERNS com os valores.
- [ ] **Step 5: Commit** (`feat: x de retirada perto do simbolo e marcas do mesmo contexto`).

### Task 4: Menores do retângulo com diagonal

**Estimativa:** 30 min · **Depende de:** Task 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_rect_diagonal.py`, `tests/fixtures/symbol_grammars/rect_diagonal.py`, `tests/unit/test_grammar_rect_diagonal.py`, `tests/unit/test_grammar_rect_diagonal_ataque.py`

- [ ] **Step 1: Testes** (R-5): retângulo montado de 4 caminhos → os 3 que não são âncora entram nos componentes; diagonal de cor diferente da do retângulo → não casa (só se a medição do Step 4 não perder tp; senão o teste fixa o comportamento atual e o relatório diz); negativo de célula de tabela; `raises=AssertionError` nos três xfail estritos (o do X curto vira teste normal se a Task 3 o resolveu).
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar** os arquivos, ruff, format, mypy, complexidade; benchmark (`task4-*`) com tp de PARA_RAIOS_BT.
- [ ] **Step 5: Commit** (`fix: menores do retangulo com diagonal`).

### Task 5: Medição (orquestrador)

**Estimativa:** 25 min · **Depende de:** Tasks 1 a 4 · **Risco:** normal

- [ ] Concordância de antes: na branch com só a Task 2 integrada, benchmark `atual`+`modelo` (`<checkout principal>/tmp/e06-3-3-2-1/antes`).
- [ ] Depois: benchmark (`.../depois`) e diff (`.../diff`) com as Tasks 1–4 integradas: R-6.
- [ ] Amostra visual: render de 5 tp com envolvente e de 3 com X, conferindo a variante.
- [ ] Auditor → `errors []`, 34.

## Fechamento operacional

- Suíte inteira por onda; testador de etapa se houver tarefa de risco normal com código (não há); `osv-scanner`; `check_test_integrity --base <base da etapa>`; revisão final; `.\IniciarTestes.bat`.
- Handoff com a concordância antes e depois, a distribuição de variantes, o gasto, e o bloco "Para a E06.3.3.2.2" (a envolvente do transformador pelo mesmo caminho; uso Rede/Dedicado/IP não discriminável).
