# E06.2.2.2 — Medição do método nas 16 folhas: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** medir o método `declarative-drawing-model` nas 16 folhas, ao lado do atual, e classificar cada casamento em que ele afirma a mais que o motor.

**Architecture:** o benchmark por ficha ganha os métodos `pacotes` e `modelo`, depois de separar métricas, relatório e corpus. Um script novo, `scripts/diff_simbolos_nucleo_motor.py`, compara por folha, página e variante as observações dos dois métodos, sem passar pela ficha, e mede o gasto por fase com `gasto_por_fase`, do núcleo. A classificação é feita sobre recortes em `tmp/`, fora do Git, e só o resumo vai ao handoff.

**Tech Stack:** Python 3.11–3.13, PyMuPDF só em `scripts/` e nos adaptadores, pytest, mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E06.2.2.2", mais os handoffs da E06.2.1 e da E06.2.2.1 na mesma página, `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` e `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md`.

## Global Constraints

- Sem mudança de saída no analisador padrão, em `declarative_symbols.py`, em `VERSAO_MODELO_DESENHO` ou no formato do cache. Esta etapa não muda API nem DTO.
- Módulos de `drawing_model/` não importam `pymupdf` nem `declarative_symbols`.
- PDFs reais, recortes, relatórios e rótulos ficam em `tmp/` do checkout principal, nunca no Git. Todo comportamento novo tem fixture sintética positiva e negativa, autoral.
- Nenhum script, fixture ou etapa lê `examples/avaliacao-cega/`: o diff usa a mesma guarda lexical do benchmark, antes de qualquer I/O.
- Relatórios identificam a folha só pelo `pdf_id` da rodada, sem caminho absoluto nem nome de PDF.
- A referência da rodada fica congelada: nada aqui edita `tmp/curadoria-simbologia/20261103-2300-fichas/`.
- Testes novos não dependem de ordem, cwd, porta, arquivo fixo nem tempo de parede. Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF.
- mypy strict, ruff check e ruff format; `scripts/complexity_gate.py src` falha em CC ≥ 31.
- Código e nomes em português.
- Worktree da etapa: `.venv/Scripts/python.exe`. Em onda, `PYTHONPATH=<worktree da tarefa>/src`, e a suíte inteira usa `-n` = 20 ÷ suítes ativas.

## Review Focus

1. Folha em que o método novo fica `FORA_DOMINIO` ou `FALHA`: conta como falha do método, fora dos totais dele, e nunca como 0 predições (Task 2, Task 3).
2. Página girada: o diff casa por índice cru, então a caixa visual do núcleo contra a crua do motor (R-E06.2.1-7) não vira falsa divergência (Task 3).
3. Mesma variante e mesmo índice cru mais de uma vez: conta como multiconjunto; duplicata não some nem casa duas vezes (Task 3).
4. Falha de um lado numa página: a página sai como `nao_comparada`, e não como "só no outro" (Task 3).
5. `casar_variantes` não muda de saída nem de gasto depois da separação de fases (Task 3).

## Decisões do plano

- **R-E06.2.2.2-1, `pacotes` além de `modelo`:** `atual` é a união de legado, estais, transformadores e pacotes, e o método novo só substitui a última parte. Sem `pacotes`, o bloco `comparacao` mediria detectores que o modelo não tem. O motor sai da mesma leitura que o runner faz (`observar_pacotes`), por um caminho mais curto que `infer_pdf`.
- **R-E06.2.2.2-2, chave do diff:** `(página, variante, índice cru)`, em multiconjunto. A caixa não entra na chave, por R-E06.2.1-7; caixa diferente com a mesma chave é contada à parte, em `geometria_diverge`, com tolerância de 0,5 pt.
- **R-E06.2.2.2-3, fases do gasto:** `colagem` (`_fundir_spans_colados`), `indices` (o resto de `contexto_gramaticas`) e `gramaticas` (o resto de `casar_variantes`). A medição usa limite alto para registrar o gasto real, mesmo acima do teto. O motor não tem orçamento: o diff só mede o núcleo.
- **R-E06.2.2.2-4, o limite:** `LIMITE_CONSULTAS_PAGINA` fica em 2.000.000 se o maior gasto real for ≤ 200.000 (o mesmo 1/10 de folga da E06.2.2.1). Acima disso, o orquestrador decide com ruling no handoff. Mudar o limite muda o perfil do método.
- **R-E06.2.2.2-5, casamento classificado como falso positivo (a nota da seção pede esta decisão):**
  - **Corrigir** quando a causa é uma divergência identificada e a correção não derruba nenhum `verdadeiro` do diff: Task 5, com o teste que hoje fixa o valor invertido, não removido, e `_VERSAO` do método subindo.
  - **Aceitar com ruling** quando corrigir derruba `verdadeiro` ou reescreve a gramática: vai à E06.3 e às "Decisões para o usuário", porque o método é opt-in até a E09.
  - **Bloquear** só se a causa não for identificável depois da Task 4: etapa `#bloqueada` com o recorte e o que foi tentado.
  - `indeciso` vale como falso positivo nesta regra.
- **R-E06.2.2.2-6, quem classifica:** um `desenvolvedor` lê os recortes, sem editar nada e sem ver a ficha, e o orquestrador confere. O ledger registra quantos houve. As 16 folhas têm 29 observações do método (handoff da E06.2.2.1), então cada item é visto um a um.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `scripts/simbolos_ficha_metricas.py` (novo) | casamento, contadores, avaliação e agregação, puros | 1 |
| `scripts/simbolos_ficha_relatorio.py` (novo) | markdown do relatório | 1 |
| `scripts/simbolos_corpus.py` (novo) | `sanear`, guarda cega, `localizar_pdf`, referência da rodada | 1 |
| `scripts/benchmark_simbolos_ficha.py` | métodos, `medir_pdf`, `medir_simbolos`, CLI | 1, 2 |
| `tests/unit/test_benchmark_simbolos_ficha.py`, `tests/unit/test_benchmark_simbolos_ficha_ataque.py` | só alvo de monkeypatch, se a separação pedir | 1 |
| `tests/unit/test_benchmark_simbolos_modelo.py` (novo) | métodos `pacotes` e `modelo` | 2 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_grammars.py` | `ContextoGramatica.gasto_colagem` | 3 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` | `GastoPagina`, `gasto_por_fase` | 3 |
| `scripts/diff_simbolos_nucleo_motor.py` (novo) | diff por folha, página e variante, gasto, recortes | 3 |
| `tests/unit/test_gasto_por_fase.py`, `tests/unit/test_diff_simbolos_nucleo_motor.py` (novos) | fases e diff | 3 |
| `tmp/e06-2-2-2/` no checkout principal (fora do Git) | relatórios, recortes, classificação | 2, 3, 4 |
| núcleo e testes da correção | definidos pela classificação | 5 |

Ondas: Task 1; Tasks 2 e 3 em paralelo, com arquivos disjuntos; Task 4; Task 5, se houver.

## Tasks

### Task 1: Desmembrar o benchmark

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** normal · **Laboratório:** não

**Files:**
- Create: `scripts/simbolos_ficha_metricas.py`, `scripts/simbolos_ficha_relatorio.py`, `scripts/simbolos_corpus.py`
- Modify: `scripts/benchmark_simbolos_ficha.py`; `tests/unit/test_benchmark_simbolos_ficha.py` e `tests/unit/test_benchmark_simbolos_ficha_ataque.py`, só no alvo de monkeypatch

**Interfaces:**
- Produces: em `scripts/simbolos_corpus.py`, `sanear(texto, ocultar=())`, `caminho_cego(*caminhos) -> bool`, `localizar_pdf(rodada, raiz_corpus, caminho_relativo) -> Path` e `carregar_referencia(rodada, pdf_id)`. Os nomes antigos continuam acessíveis em `scripts.benchmark_simbolos_ficha`.

- [ ] **Step 1: Rodar os testes atuais** `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_simbolos_ficha.py tests/unit/test_benchmark_simbolos_ficha_ataque.py -q` e guardar a contagem.
- [ ] **Step 2: Mover**, sem mudar comportamento: casamento, contadores, avaliação e agregação para `simbolos_ficha_metricas.py`; `_pct`, `_linhas_*` e `_markdown` para `simbolos_ficha_relatorio.py`; saneamento, guarda cega, localização e referência para `simbolos_corpus.py`. O benchmark reimporta o que os testes usam. Nenhum assert muda; se um monkeypatch precisar de outro alvo, troque só o alvo e diga no relatório.
- [ ] **Step 3: Conferir** a mesma contagem do Step 1, depois `.venv/Scripts/python.exe -m ruff check scripts tests/unit/test_benchmark_simbolos_ficha.py` e `ruff format --check`. Nenhum arquivo novo passa de 400 linhas. `python -m scripts.benchmark_simbolos_ficha --help` funciona.
- [ ] **Step 4: Commit** (`refactor: benchmark de simbolos em metricas, relatorio e corpus`).

### Task 2: Métodos `pacotes` e `modelo` no benchmark

**Estimativa:** 30 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `scripts/benchmark_simbolos_ficha.py`
- Create: `tests/unit/test_benchmark_simbolos_modelo.py`

**Interfaces:**
- Consumes: `declarative_symbols.observar_pacotes`, `model_symbols.observar_pacotes_modelo`, `perfil_pacotes_modelo`, `carregar_tabela_glifos`.
- Produces: `METODOS["pacotes"]`, `METODOS["modelo"]`, `ASSINATURAS["pacotes"]`, `ASSINATURAS["modelo"]`.

- [ ] **Step 1: Escrever os testes**, com PDF sintético do corpus das gramáticas:
  - `test_modelo_e_pacotes_preveem_o_mesmo_rotulo`: um rótulo `CT` em moldura dá uma predição `{pagina, classe, bbox, metodo, contexto}` em cada método, com a mesma classe e `bbox` normalizada a menos de 0,005;
  - `test_folha_sem_simbolo_nao_e_falha`: `NAO_DETECCAO` dá predições vazias e `falha` `None`;
  - `test_fonte_falhou_conta_como_falha_nao_como_zero`: monkeypatch de `reconstruir_polilinhas` que levanta faz `medir_pdf` trazer `situacao` de falha com `fonte_falhou:modelo.primitivas_falhou`, fora de `comparacao`;
  - `test_teto_conta_como_falha`: limite pequeno por monkeypatch dá falha com `teto_consultas`;
  - `test_assinatura_do_modelo_traz_versao_e_tabela`: `ASSINATURAS["modelo"]()` tem `metodo_id` `declarative-drawing-model`, `versao` `1.0.0` e os parâmetros do perfil;
  - `test_metodo_desconhecido_segue_recusado`: a CLI recusa `--metodo x`.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar** `_predicoes_pacotes(pdf, pdf_id) -> ResultadoMetodo` e `_predicoes_modelo(pdf, pdf_id) -> ResultadoMetodo`: abrem o PDF, chamam o método em cada página (perfil e pacotes calculados uma vez por folha), convertem a observação como o ramo `include_packages` de `infer_pdf` em `scripts/symbol_benchmark_runner.py` (`bbox` dos `pontos_normalizados`). Toda cobertura `FALHA` ou `FORA_DOMINIO` vira `falha` com o `motivo` e a página. Observação sem classe (candidato desconhecido do motor) fica de fora. Registre os dois em `METODOS` e `ASSINATURAS`; `atual` não muda.
- [ ] **Step 4: Rodar** o arquivo novo e os dois do benchmark; ruff e format. Expected: PASS.
- [ ] **Step 5: Commit** (`feat: metodos pacotes e modelo no benchmark de simbolos`).

Depois de integrar, o orquestrador roda, com o `--processos` do orçamento:
`.venv/Scripts/python.exe -m scripts.benchmark_simbolos_ficha --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/e06-2-2-2/simbolos --metodo atual --metodo pacotes --metodo modelo --processos 10`.

### Task 3: Diff por variante, com o gasto por fase

**Estimativa:** 45 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_grammars.py`, `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`
- Create: `scripts/diff_simbolos_nucleo_motor.py`, `tests/unit/test_gasto_por_fase.py`, `tests/unit/test_diff_simbolos_nucleo_motor.py`

**Interfaces:**
- Consumes: `scripts/simbolos_corpus.py` da Task 1; `observar_pacotes`; `observar_pacotes_modelo`; `pagina_para_gramaticas`.
- Produces:
  - `ContextoGramatica.gasto_colagem: int`;
  - `GastoPagina(colagem: int, indices: int, gramaticas: int)` frozen, com a propriedade `total`;
  - `gasto_por_fase(pagina, variantes, *, limite=LIMITE_CONSULTAS_PAGINA) -> GastoPagina`, em `symbol_matcher.py`;
  - CLI `python -m scripts.diff_simbolos_nucleo_motor --rodada RODADA --saida DIR [--processos N] [--recortes]`, que grava `diff-nucleo-motor.json` (esquema `diff-nucleo-motor-v1`) e `diff-nucleo-motor.md` em `DIR`, e os PNG em `DIR/recortes/`.

- [ ] **Step 1: Escrever os testes do gasto** em `test_gasto_por_fase.py`:
  - `test_fases_somam_o_gasto_de_casar_variantes`: para o corpus sintético, `gasto_por_fase(...).total` é igual ao `orcamento.gasto` final de um contexto percorrido por `casar_variantes` (com um espião em `contexto_gramaticas`);
  - `test_casar_variantes_nao_muda`: a mesma tupla de casamentos antes e depois da separação, nas variantes publicadas;
  - `test_colagem_cresce_com_colunas_alinhadas`: N linhas com a mesma borda direita aumentam `colagem` e não `gramaticas`; sem variante de disco, `gramaticas` não paga pontas;
  - `test_teto_vale_na_medicao`: `limite` pequeno levanta `TetoGramaticasExcedido`, e limite alto devolve o gasto real.
- [ ] **Step 2: Escrever os testes do diff** em `test_diff_simbolos_nucleo_motor.py`, com rodada sintética em `tmp_path`:
  - `test_os_dois_veem`: rótulo casado pelos dois vai a `ambos`, com `so_nucleo` e `so_motor` vazios;
  - `test_so_no_nucleo_e_listado`: a fixture `Q`+`DP` de `test_grammar_frames_ataque.py` lista o item com `{pagina, variante, classe, indice_cru, bbox}`;
  - `test_so_no_motor_e_listado`: a fixture de disco com linha que dobra (R-6);
  - `test_pagina_girada_nao_diverge`: 90 e 270 graus: `ambos`, sem `geometria_diverge`;
  - `test_mesma_chave_duas_vezes_e_multiconjunto`: duas observações do motor contra uma do núcleo dão 1 em `ambos` e 1 em `so_motor`;
  - `test_falha_de_um_lado_nao_vira_so_no_outro`: `FORA_DOMINIO` no núcleo com observação no motor dá a página como `nao_comparada`, com o motivo, e a folha fora dos totais de `so_motor`;
  - `test_recusa_caminho_cego`: rodada ou PDF com componente `avaliacao-cega` é recusado antes de qualquer leitura;
  - `test_relatorio_sem_nome_de_pdf`: nem o JSON nem o markdown trazem o nome do PDF ou o caminho da rodada;
  - `test_recortes_so_com_a_opcao`: `--recortes` grava um PNG por item `so_nucleo`, com a caixa marcada e o nome `<pdf_id>-p<pagina>-<variante>-<indice_cru>.png`.
- [ ] **Step 3: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 4: Implementar o gasto.** `contexto_gramaticas` grava `gasto_colagem` logo depois de `_fundir_spans_colados`. `casar_variantes` passa a delegar a `_casar_no_contexto(contexto, variantes)`, e `gasto_por_fase` usa o mesmo helper. A saída de `casar_variantes` não muda; `_VERSAO` também não, e o digest do runner muda sozinho.
- [ ] **Step 5: Implementar o diff.** Abre o PDF e, por página, roda `observar_pacotes`, `observar_pacotes_modelo` e `gasto_por_fase` com `limite=10**12`, medindo o tempo de cada um. Compara por `(página, template, primitivas[0].indice)` em `Counter` (R-E06.2.2.2-2), ignorando observação sem `template` (candidato desconhecido do motor). Grava, por folha e página: `cobertura` dos dois, por variante `ambos`, `so_motor`, `so_nucleo`, `geometria_diverge`; `gasto` e `tempo_s`; e os totais. O markdown lista **todo** item `so_nucleo` numa linha, os `so_motor` por variante, e a tabela de gasto por folha com o maior `total` e a razão contra `LIMITE_CONSULTAS_PAGINA`. Recorte a 200 dpi, com margem de 40 pt e a caixa em vermelho. Processos como no benchmark, com a ordem do `rodada.json` na saída.
- [ ] **Step 6: Rodar** os dois arquivos, mypy, ruff, format e `scripts/complexity_gate.py src`. Expected: PASS.
- [ ] **Step 7: Commit** (`feat: diff de simbolos nucleo contra motor com gasto por fase`).

Depois de integrar, o orquestrador roda: `.venv/Scripts/python.exe -m scripts.diff_simbolos_nucleo_motor --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/e06-2-2-2/diff --processos 10 --recortes`.

### Task 4: Classificar cada "só no núcleo"

**Estimativa:** 25 min · **Depende de:** Tasks 2 e 3 · **Risco:** normal · **Laboratório:** não

Sem código e sem commit: o orquestrador roda o benchmark e o diff, e despacha a classificação (R-E06.2.2.2-6). Não entra no ciclo testador/revisora; a conferência é a do Step 2.

- [ ] **Step 1: Classificar.** Para cada item `so_nucleo` de `diff-nucleo-motor.md`, o `desenvolvedor` lê o recorte e grava em `<checkout principal>/tmp/e06-2-2-2/classificacao.md`: `pdf_id`, página, variante, índice cru; rótulo `verdadeiro`, `falso_positivo` ou `indeciso`; a causa, pela lista de divergências do handoff da E06.2.1 (`Q`+`DP`, sobreimpressão, spans a 90/180/270°, `qu` inclinado, borda, contorno de letra na moldura) ou `nova`, com o que o recorte mostra. Não vê a ficha nem as predições do motor, e não edita código.
- [ ] **Step 2: Conferir.** O orquestrador lê os recortes de todo `falso_positivo` e `indeciso`, e de uma amostra de 5 `verdadeiro` (todos, se forem menos), e aplica R-E06.2.2.2-5, com uma ruling por item no ledger.
- [ ] **Step 3: Decidir as divergências.** Para cada divergência em que o núcleo afirma a mais, do handoff da E06.2.1: observada em quantos itens e qual decisão. Para as que perdem recall: quantos `so_motor` por variante e causa provável, sem classificar um a um. Vai ao handoff.

### Task 5: Corrigir os falsos positivos (condicional)

**Estimativa:** até 45 min · **Depende de:** Task 4 · **Risco:** alto · **Laboratório:** não

Só existe se a Task 4 decidir corrigir algum item. Sem isso, o ledger registra e a tarefa é pulada.

**Files:** definidos pela ruling da Task 4, em `drawing_model/` e `tests/unit/`; `model_symbols.py` para `_VERSAO`.

- [ ] **Step 1: Teste.** Inverta o teste que fixa a divergência (não remova), com a fixture sintética positiva e negativa. Sem memorizar coordenada, hash ou folha.
- [ ] **Step 2: Corrigir** no núcleo, sem derrubar nenhum `verdadeiro`.
- [ ] **Step 3: Subir `_VERSAO`** em `model_symbols.py` para `1.0.1`; a saída muda (invariante de versão).
- [ ] **Step 4: Rodar** `tests/unit/test_grammar_frames_ataque.py`, `test_grammar_disc.py`, `test_model_symbols.py`, `tests/integration/test_model_symbols_runner.py`, a suíte inteira uma vez, mypy, ruff, format e `scripts/complexity_gate.py src`.
- [ ] **Step 5: Commit** (`fix: <divergencia> deixa de afirmar a mais no nucleo`).

Depois, o orquestrador repete o benchmark e o diff, confere que o item saiu e que nenhum `verdadeiro` caiu, e leva esse número ao handoff.

## Fechamento operacional

| Critério de aceite | Evidência |
|---|---|
| O benchmark mede o método novo nas 16 folhas, ao lado do atual | Task 2; `tmp/e06-2-2-2/simbolos/simbolos-ficha.md`, com `comparacao` |
| Diff por variante e folha, sem passar pela ficha, em `tmp/`, cada "só no núcleo" listado e classificado | Task 3 e 4; `tmp/e06-2-2-2/diff/` e `classificacao.md` |
| Gasto real de orçamento e o limite de `LIMITE_CONSULTAS_PAGINA` no handoff | Task 3; R-E06.2.2.2-4 |
| `scripts.audit_symbol_packages` → 0 erros | o orquestrador roda antes do `#concluida` |
| `IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` | `cmd.exe //c ".\\IniciarTestes.bat"`, conferindo a data do relatório |

No handoff, para a E06.3: a linha de base dos três métodos no benchmark; as divergências decididas; o gasto por fase, porque as gramáticas novas gastam do mesmo limite; e os `so_motor` por causa, porque a perda de recall define a prioridade dela.

Em "Decisões para o usuário": cada falso positivo aceito com ruling e o limite, se mudar.
