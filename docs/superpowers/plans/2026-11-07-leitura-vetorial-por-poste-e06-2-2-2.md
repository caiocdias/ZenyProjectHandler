# E06.2.2.2 — Medição do método nas 16 folhas: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** medir o método `declarative-drawing-model` nas 16 folhas, ao lado do atual, e classificar cada casamento em que ele afirma a mais que o motor.

**Architecture:** o benchmark por ficha ganha os métodos `pacotes` e `modelo`, depois de separar métricas, relatório e corpus. Um script novo, `scripts/diff_simbolos_nucleo_motor.py`, compara por folha, página e variante as observações dos dois métodos, sem passar pela ficha, e mede o gasto por fase com `gasto_por_fase`, do núcleo. A classificação é feita sobre recortes em `tmp/`, fora do Git, e só o resumo vai ao handoff.

**Tech Stack:** Python 3.11–3.13, PyMuPDF só em `scripts/` e nos adaptadores, pytest, mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E06.2.2.2", mais os handoffs da E06.2.1 e da E06.2.2.1 na mesma página, `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md`, `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md` e `docs/fluxo-curadoria-incremental-simbologia.md` (exposição, resolução de recorte, papel e estado).

## Global Constraints

- Sem mudança de saída no analisador padrão, em `declarative_symbols.py`, em `VERSAO_MODELO_DESENHO` ou no formato do cache. Esta etapa não muda API nem DTO. `symbol_matcher.py` e `symbol_grammars.py` estão no digest do runner: a Task 3 causa um cache miss no opt-in, sem mudar saída nem `_VERSAO`.
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

1. Folha em que o método novo fica `FORA_DOMINIO` ou `FALHA`: no benchmark, a folha conta como falha do método, fora dos totais dele, e nunca como 0 predições (Task 2). No diff, a unidade é a página: ela sai como `nao_comparada`, fora dos totais (Task 4).
2. Página girada: nas gramáticas invariantes, o diff casa por índice cru, sem falsa divergência; as gramáticas sensíveis divergem por decisão (R-E06.2.1-7) e aparecem como `orientacao`, não como erro (Task 4).
3. O mesmo símbolo com índice cru diferente nos dois métodos: fica em `indice_diverge`, sem inflar `so_nucleo` e `so_motor`. Mesma chave repetida conta como multiconjunto (Task 4).
4. Falha de um lado numa página: não vira "só no outro", inclusive exceção vinda do motor (Task 4).
5. `casar_variantes` não muda de saída nem de gasto depois da separação de fases: valores fixados antes do refactor (Task 3).

## Decisões do plano

- **R-E06.2.2.2-1, `pacotes` além de `modelo`:** `atual` é a união de legado, estais, transformadores e pacotes, e o método novo só substitui a última parte. Sem `pacotes`, o bloco `comparacao` mediria detectores que o modelo não tem. O tempo se compara só entre `pacotes` e `modelo`, porque o de `atual` inclui `tracemalloc`.
- **R-E06.2.2.2-2, chave do diff:** `(página, variante, índice cru)`, em multiconjunto. Ordem: mesma chave com caixa a até 0,5 pt vai a `ambos`; do que sobra, mesma chave vai a `geometria_diverge`; do que sobra, mesma página e variante com caixa a até 0,5 pt vai a `indice_diverge`; o resto fica em `so_nucleo` e `so_motor`. `geometria_diverge` e `indice_diverge` não contam em `so_nucleo` nem em `so_motor`. Na observação as duas caixas já são cruas. Item recebe `orientacao: true` quando a variante tem gramática sensível à orientação e a página está girada, com a exceção da barra a 180 graus (`tests/unit/test_grammar_frames_ataque.py:193-198`), e continua na fila, porque todo "só no núcleo" é classificado.
- **R-E06.2.2.2-3, fases do gasto:** `colagem` (`_fundir_spans_colados`), `indices` (o resto de `contexto_gramaticas`) e `gramaticas` (o resto de `casar_variantes`). A medição usa limite alto para registrar o gasto real, mesmo acima do teto. O motor não tem orçamento: o diff só mede o núcleo. `grandes`, entradas de grade e a razão "trabalho até 64 vezes o gasto" (handoff da E06.2.1) ficam **dispensados** como contagem própria: R-4 julga pelo gasto, e o relatório traz `tempo_s` de `gasto_por_fase` por folha, que mostra se o trabalho real descola do gasto. Custo se errada: um gargalo de `grandes` aparece só como tempo, sem causa nomeada.
- **R-E06.2.2.2-4, o limite:** `LIMITE_CONSULTAS_PAGINA` fica em 2.000.000 se o maior gasto real for ≤ 200.000 (o mesmo 1/10 de folga da E06.2.2.1). Acima disso, o orquestrador decide com ruling no handoff. Mudar o limite muda o perfil do método e passa pela Task 7, com emenda no plano.
- **R-E06.2.2.2-5, classificação (papel e estado separados, como em `fluxo`):**
  - **Forma:** `confere` (o desenho é o símbolo que a variante descreve), `nao_confere` ou `ilegivel`.
  - **Papel:** `operacional`, `informativo_legenda` ou `desconhecido`.
  - **Rótulo:** `confere` + `operacional` ou `desconhecido` = `verdadeiro`; `confere` + `informativo_legenda` = `legenda`, listado à parte, sem correção (o método não infere contexto; é assunto da E07 e da E09); `nao_confere` = `falso_positivo`; `ilegivel` relê em dpi maior com uma segunda instância e, se persistir, vira `provisorio`, listado no handoff, sem correção nem bloqueio.
- **R-E06.2.2.2-6, falso positivo (a nota da seção pede esta decisão):**
  - **Corrigir** quando a causa está `causa_confirmada` e a correção é local (uma guarda, sem mudar a estrutura da gramática ou da fusão), sem derrubar nenhum `verdadeiro`: Task 7, com o teste que hoje fixa o valor invertido, não removido.
  - **Aceitar com ruling** quando corrigir derruba `verdadeiro`, ou muda a estrutura da gramática ou da fusão, ou a causa fica `indeterminada` ou `causa_refutada` sem outra confirmada: vai às "Decisões para o usuário" e ao handoff, como critério da E09, porque o ADR 0016 exige o analisador novo ≥ em todas as métricas. A divergência `nova` aceita com `causa_confirmada` ganha teste "valor de hoje, inverter, não remover" na Task 7, para o conhecimento ficar em fixture; sem causa confirmada, não há o que fixar, e o recorte descrito fica no handoff.
  - **Bloquear** só se a medição for inválida (uma folha sem comparação que impede classificar) ou se o falso positivo for sistemático: pelo menos 5 itens, e a maioria dos `so_nucleo` com causa `indeterminada`. Etapa `#bloqueada`, com os recortes e o que foi tentado.
- **R-E06.2.2.2-7, quem classifica:** as 16 folhas têm 29 observações do método (handoff da E06.2.2.1), então cada item é visto um a um. Uma instância do `desenvolvedor` (modelo `opus`, com o id exposto pela sessão registrado em `classificacao.md`, sem troca de modelo no papel). O despacho diz que TDD e suíte não se aplicam a esta leitura, que ela não edita código nem nada da rodada congelada, e o orquestrador confere HEAD, `git status` e o hash dos `referencia.json` depois (`tmp/` é ignorado pelo Git, então o status não o vê). Ela recebe só `recortes/fila.json`, em que cada entrada é `{id, descricao}`: `descricao` traz o `recognition.grammar` e os `negative_examples` da variante, sem página, motor nem totais, e ela não abre o JSON nem o `.md` do diff. A saída traz `exposicao: sim`, porque o recorte marcado vem do método: a leitura não é cega, e só muda o que os pixels confirmam. Todo `falso_positivo` passa por uma segunda instância nova, que não vê o primeiro rótulo. A conferência do orquestrador é registrada como **não independente**. As 16 folhas já são de desenvolvimento (design), o que torna a revisão exposta aceitável. Os agentes `curadoria-*` não entram: a soul do orquestrador só os despacha quando uma skill de projeto ou o protocolo os exige, e aqui nenhum dos dois exige.
- **R-E06.2.2.2-8, teto da correção:** uma divergência por commit e no máximo uma correção local na etapa, validada primeiro em fixture, com uma única repetição do benchmark nas folhas. Antes do despacho, o orquestrador emenda o plano com arquivos e estimativa. Se pedir limiar ou heurística, uma segunda correção ou uma segunda rodada, sai da etapa: aceite com ruling para o laboratório da E06.3. Por isso esta etapa não tem laboratório.
- **R-E06.2.2.2-9, identidade do item:** o `id` é só do recorte e muda entre execuções. A comparação antes e depois usa a chave natural `(pdf_id, página, variante, índice cru)`. Na Task 6 ficam congelados os `sha256` de `classificacao.md` e de `diff-nucleo-motor.json`; a releitura a 600 dpi e a repetição da Task 7 gravam em `--saida` própria.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `scripts/simbolos_ficha_metricas.py` (novo) | casamento, contadores, avaliação e agregação, puros | 1 |
| `scripts/simbolos_ficha_relatorio.py` (novo) | markdown do relatório | 1 |
| `scripts/simbolos_corpus.py` (novo) | saneamento, guarda cega, localização, referência, pool, cobertura para falha | 1 |
| `scripts/benchmark_simbolos_ficha.py` | métodos, `medir_pdf`, `medir_simbolos`, CLI | 1, 2 |
| `tests/unit/test_benchmark_simbolos_ficha.py`, `tests/unit/test_benchmark_simbolos_ficha_ataque.py` | só alvo de monkeypatch, se a separação pedir | 1 |
| `tests/unit/test_benchmark_simbolos_modelo.py` (novo) | métodos `pacotes` e `modelo` | 2 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_grammars.py` | `ContextoGramatica.gasto_colagem` | 3 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` | `GastoPagina`, `gasto_por_fase` | 3 |
| `tests/unit/test_gasto_por_fase.py` (novo) | fases do gasto | 3 |
| `tests/unit/test_simbolos_corpus.py` (novo) | `falha_da_cobertura` | 1 |
| `scripts/diff_simbolos_nucleo_motor.py` (novo) | diff por folha, página e variante, gasto; recortes e fila | 4, 5 |
| `tests/unit/test_diff_simbolos_nucleo_motor.py` (novo) | diff | 4 |
| `tests/unit/test_diff_simbolos_recortes.py` (novo) | recortes e fila | 5 |
| `tmp/e06-2-2-2/` no checkout principal (fora do Git) | relatórios, recortes, classificação | 2, 4, 5, 6 |
| núcleo e testes da correção | emenda da Task 7 | 7 |

Ondas: Tasks 1 e 3; Tasks 2 e 4; Task 5; Task 6; Task 7, se houver.

Soma: 2h55 sem a Task 7 e 3h40 com ela. A Task 7 é condicional e tem teto (R-E06.2.2.2-8), então a etapa não se divide agora; se a Task 6 pedir correção que não caiba no teto, ela sai da etapa.

## Tasks

### Task 1: Desmembrar o benchmark

**Estimativa:** 35 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

Alto porque move a guarda do conjunto cego e o saneamento.

**Files:**
- Create: `scripts/simbolos_ficha_metricas.py`, `scripts/simbolos_ficha_relatorio.py`, `scripts/simbolos_corpus.py`
- Create: `tests/unit/test_simbolos_corpus.py`
- Modify: `scripts/benchmark_simbolos_ficha.py`; `tests/unit/test_benchmark_simbolos_ficha.py` e `tests/unit/test_benchmark_simbolos_ficha_ataque.py`, só no alvo de monkeypatch

**Interfaces:**
- Produces, em `scripts/simbolos_corpus.py`:
  - `FolhaError(Exception)`, o antigo `_FolhaError`;
  - `sanear(texto, ocultar=())`;
  - `caminho_cego(*caminhos) -> bool`;
  - `recusar_rodada_cega(rodada: Path) -> None`, a recusa hoje inline em `medir_simbolos`;
  - `localizar_pdf(rodada, raiz_corpus, caminho_relativo) -> Path`;
  - `carregar_referencia(rodada, pdf_id)`;
  - `medir_em_paralelo(funcao, tarefas, efetivos, executor) -> list[Registro]`, o pool de `_medir_todas`, com a ordem de entrada. `_medir_todas` passa o `ProcessPoolExecutor` resolvido em `bench`, porque 5 testes fazem `monkeypatch.setattr(bench, ...)` nele;
  - `falha_da_cobertura(cobertura) -> str | None`: lista branca: só `CONCLUIDO` e `NAO_DETECCAO` devolvem `None`; todo outro estado devolve o `motivo` ou o nome do estado.

  Os nomes antigos continuam acessíveis em `scripts.benchmark_simbolos_ficha`.

- [ ] **Step 1: Rodar os testes atuais** `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_simbolos_ficha.py tests/unit/test_benchmark_simbolos_ficha_ataque.py -q` e guardar a contagem.
- [ ] **Step 2: Escrever** `test_falha_da_cobertura`, parametrizado no `EstadoMetodoSimbolos` inteiro, em `tests/unit/test_simbolos_corpus.py`, e vê-lo falhar.
- [ ] **Step 3: Mover**, sem mudar comportamento: casamento, contadores, avaliação e agregação para `simbolos_ficha_metricas.py`; `_pct`, `_linhas_*` e `_markdown` para `simbolos_ficha_relatorio.py`; o resto da lista acima para `simbolos_corpus.py`. O benchmark reimporta o que os testes usam. Nenhum assert muda; se um monkeypatch precisar de outro alvo, troque só o alvo e diga no relatório.
- [ ] **Step 4: Conferir** a contagem do Step 1 nos dois arquivos, `tests/unit/test_simbolos_corpus.py` verde, `.venv/Scripts/python.exe -m ruff check scripts tests/unit/test_simbolos_corpus.py` e `ruff format --check`. Nenhum arquivo novo passa de 400 linhas. `python -m scripts.benchmark_simbolos_ficha --help` funciona.
- [ ] **Step 5: Commit** (`refactor: benchmark de simbolos em metricas, relatorio e corpus`).

### Task 2: Métodos `pacotes` e `modelo` no benchmark

**Estimativa:** 30 min · **Depende de:** Task 1 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `scripts/benchmark_simbolos_ficha.py`
- Create: `tests/unit/test_benchmark_simbolos_modelo.py`

**Interfaces:**
- Consumes: `falha_da_cobertura`; `declarative_symbols.observar_pacotes`; `model_symbols.observar_pacotes_modelo`, `perfil_pacotes_modelo`; `carregar_tabela_glifos`.
- Produces: `METODOS["pacotes"]`, `METODOS["modelo"]`, `ASSINATURAS["pacotes"]`, `ASSINATURAS["modelo"]`; `LIMITE_MODELO`, constante do módulo igual a `LIMITE_CONSULTAS_PAGINA`, lida na chamada e passada como `limite=` ao perfil e à observação.

- [ ] **Step 1: Escrever os testes**, com PDF sintético do corpus das gramáticas:
  - `test_modelo_e_pacotes_preveem_o_mesmo_rotulo`: um rótulo `CT` em moldura dá uma predição `{pagina, classe, bbox, metodo, contexto}` em cada método, com a mesma classe e `bbox` normalizada a menos de 0,005;
  - `test_folha_sem_simbolo_nao_e_falha`: `NAO_DETECCAO` dá predições vazias e `falha` `None`;
  - `test_fonte_falhou_conta_como_falha_nao_como_zero`: monkeypatch de `reconstruir_polilinhas` que levanta faz `medir_pdf` trazer `situacao` de falha com `fonte_falhou:modelo.primitivas_falhou`, fora de `comparacao`;
  - `test_teto_conta_como_falha`: monkeypatch de `bench.LIMITE_MODELO` para um valor pequeno dá falha com `teto_consultas`;
  - `test_assinatura_do_modelo_traz_versao_e_tabela`: `ASSINATURAS["modelo"]()` tem `metodo_id` `declarative-drawing-model`, `versao` igual a `model_symbols._VERSAO` e os parâmetros do perfil;
  - `test_metodo_desconhecido_segue_recusado`: a CLI recusa `--metodo x`.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar** `_predicoes_pacotes(pdf, pdf_id) -> ResultadoMetodo` e `_predicoes_modelo(pdf, pdf_id) -> ResultadoMetodo`: abrem o PDF, chamam o método em cada página (perfil e pacotes calculados uma vez por folha), convertem a observação como o ramo `include_packages` de `infer_pdf` em `scripts/symbol_benchmark_runner.py` (`bbox` dos `pontos_normalizados`). A falha de uma página, por `falha_da_cobertura`, vira `falha` da folha, com o motivo e a página. Registre os dois em `METODOS` e `ASSINATURAS`; `atual` não muda.
- [ ] **Step 4: Rodar** o arquivo novo e os dois do benchmark; ruff e format. Expected: PASS.
- [ ] **Step 5: Commit** (`feat: metodos pacotes e modelo no benchmark de simbolos`).

### Task 3: Gasto do orçamento por fase

**Estimativa:** 20 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_grammars.py`, `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`
- Create: `tests/unit/test_gasto_por_fase.py`

**Interfaces:**
- Produces:
  - `ContextoGramatica.gasto_colagem: int`;
  - `GastoPagina(colagem: int, indices: int, gramaticas: int)` frozen, com a propriedade `total`;
  - `gasto_por_fase(pagina, variantes, *, limite=LIMITE_CONSULTAS_PAGINA) -> GastoPagina`, em `symbol_matcher.py`. Levanta o mesmo que `casar_variantes`: `FonteGramaticaFalhou` com qualquer limite; `TetoGramaticasExcedido` também com qualquer limite em `glifos_limitados`, e acima do limite nos demais casos.

- [ ] **Step 1: Fixar os valores atuais, antes do refactor.** Com o código de hoje, para uma página do corpus sintético e um conjunto de variantes definido no próprio teste (não as publicadas, que a E06.3 amplia), meça a tupla de casamentos e o `orcamento.gasto` final (espião em `contexto_gramaticas`). Grave os valores como literais em `test_casar_variantes_nao_muda_saida_nem_gasto` e veja passar.
- [ ] **Step 2: Escrever os testes novos** em `test_gasto_por_fase.py`:
  - `test_fases_somam_o_gasto_fixado`: `gasto_por_fase(...).total` é igual ao literal do Step 1;
  - `test_colagem_cresce_com_colunas_alinhadas`: N linhas com a mesma borda direita aumentam `colagem` e não `gramaticas`;
  - `test_sem_disco_gramaticas_nao_paga_pontas`;
  - `test_teto_vale_na_medicao`: `limite` pequeno levanta `TetoGramaticasExcedido`, e `limite=10**12` devolve o gasto real;
  - `test_fonte_falhou_levanta_com_qualquer_limite`;
  - `test_glifos_limitados_levanta_teto_com_qualquer_limite`.
- [ ] **Step 3: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 4: Implementar.** `contexto_gramaticas` grava `gasto_colagem` logo depois de `_fundir_spans_colados`. `casar_variantes` passa a delegar a `_casar_no_contexto(contexto, variantes)`, e `gasto_por_fase` usa o mesmo helper. `_VERSAO` não muda.
- [ ] **Step 5: Rodar** o arquivo novo, `tests/unit/test_symbol_matcher_ataque.py`, `tests/unit/test_grammar_frames_ataque.py`, `tests/unit/test_model_symbols.py`, `tests/integration/test_model_symbols_runner.py`, mypy, ruff, format e `scripts/complexity_gate.py src`. Expected: PASS.
- [ ] **Step 6: Commit** (`feat: gasto do orcamento de gramaticas por fase`).

### Task 4: Diff por variante

**Estimativa:** 35 min · **Depende de:** Tasks 1 e 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `scripts/diff_simbolos_nucleo_motor.py`, `tests/unit/test_diff_simbolos_nucleo_motor.py`

**Interfaces:**
- Consumes: `scripts/simbolos_corpus.py`; `gasto_por_fase`; `observar_pacotes`; `observar_pacotes_modelo`; `pagina_para_gramaticas`.
- Produces: CLI `python -m scripts.diff_simbolos_nucleo_motor --rodada RODADA --saida DIR [--processos N]`, que grava `diff-nucleo-motor.json` (esquema `diff-nucleo-motor-v1`) e `diff-nucleo-motor.md` em `DIR`. Cada item `so_nucleo` traz `id` opaco (`item-0001`, pela ordem da rodada; R-E06.2.2.2-9). Para a Task 5: `Item` e a abertura das páginas ficam em funções reutilizáveis do script.

- [ ] **Step 1: Escrever os testes**, com rodada sintética em `tmp_path`, sem `ficha/`:
  - `test_os_dois_veem`: rótulo casado pelos dois vai a `ambos`, com `so_nucleo` e `so_motor` vazios;
  - `test_so_no_nucleo_e_listado`: a fixture `Q`+`DP` de `tests/unit/test_symbol_matcher_ataque.py:307-354` lista o item com `{id, pagina, variante, classe, indice_cru, bbox, textos, glifos_lidos, diagnosticos}`, em que `textos` são os textos do modelo na caixa, com a origem (nativo, shx ou glifo) e a rotação;
  - `test_so_no_motor_e_listado`: a fixture de disco com linha que dobra (R-6);
  - `test_pagina_girada_nao_diverge_nas_invariantes`: 90 e 270 graus, nas gramáticas invariantes, dão `ambos`, sem `geometria_diverge`;
  - `test_orientacao_aparece_como_orientacao`: uma gramática sensível à orientação (R-E06.2.1-7, `tests/unit/test_grammar_frames_ataque.py:193-198`) em página girada fica em `so_nucleo` ou `so_motor`, com `orientacao: true` no item;
  - `test_mesma_chave_duas_vezes_e_multiconjunto`: duas observações do motor contra uma do núcleo dão 1 em `ambos` e 1 em `so_motor`;
  - `test_indice_diferente_com_a_mesma_caixa`: mesma variante e caixa, índices diferentes: 1 em `indice_diverge`, nada em `so_nucleo` nem em `so_motor`;
  - `test_falha_de_um_lado_nao_vira_so_no_outro`: `FORA_DOMINIO` no núcleo com observação no motor dá a página `nao_comparada`, com o motivo, fora dos totais;
  - `test_excecao_do_motor_nao_derruba_a_rodada`: exceção de `observar_pacotes` dá a página `nao_comparada`, com o erro saneado;
  - `test_gasto_nulo_com_motivo`: fonte que falha e `glifos_limitados` gravam `gasto: null` e o motivo; `glifos_desconhecidos` aparece no item quando ocorre;
  - `test_recusa_caminho_cego`: rodada ou PDF com componente `avaliacao-cega` é recusado antes de qualquer leitura;
  - `test_sha_diferente_e_recusado`: PDF com `sha256` diferente do `rodada.json` falha a folha;
  - `test_relatorio_sem_nome_de_pdf`: nem o JSON nem o markdown trazem o nome do PDF ou o caminho da rodada.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar.** Confere o `sha256` da entrada do `rodada.json`. Por página, roda `observar_pacotes`, `observar_pacotes_modelo` e `gasto_por_fase` com `limite=10**12` (capturando `FonteGramaticaFalhou` e `TetoGramaticasExcedido`), com o tempo de cada um à parte. Compara conforme R-E06.2.2.2-2. Grava, por folha e página: `cobertura` dos dois, por variante `ambos`, `so_motor`, `so_nucleo`, `indice_diverge`, `geometria_diverge`; `gasto` e `tempo_s`; e os totais. O markdown lista **todo** item `so_nucleo` numa linha, os `so_motor` por variante, e a tabela de gasto por folha com o maior `total` e a razão contra `LIMITE_CONSULTAS_PAGINA`. Processos com `medir_em_paralelo`.
- [ ] **Step 4: Rodar** o arquivo novo, ruff e format. Expected: PASS.
- [ ] **Step 5: Commit** (`feat: diff de simbolos nucleo contra motor com gasto por fase`).

### Task 5: Recortes e fila de classificação

**Estimativa:** 20 min · **Depende de:** Task 4 · **Risco:** normal · **Laboratório:** não

**Files:**
- Modify: `scripts/diff_simbolos_nucleo_motor.py`
- Create: `tests/unit/test_diff_simbolos_recortes.py`

**Interfaces:**
- Produces: as opções `--recortes` e `--dpi` (padrão 400) na CLI, que gravam, para cada item `so_nucleo`, `DIR/recortes/<id>-limpo.png`, `<id>-marcado.png` e `<id>-pagina.png`, mais `DIR/recortes/fila.json`, lista de `{id, descricao}`.

- [ ] **Step 1: Escrever os testes**, com rodada sintética em `tmp_path`:
  - `test_recortes_so_com_a_opcao`: sem a opção, nenhum PNG; com ela, os três por item;
  - `test_fila_so_traz_id_e_descricao`: as chaves são exatamente `id` e `descricao`, e `descricao` traz `recognition.grammar` e `negative_examples` da variante, sem página, caixa, motor, totais, nome do PDF ou caminho da rodada;
  - `test_recorte_em_pagina_girada_contem_o_simbolo`: a 90 graus, o recorte limpo contém o rótulo (conferido por pixels não brancos no centro), porque a caixa crua é levada ao espaço visual antes do clip;
  - `test_marca_nao_cobre_a_moldura`: os pixels da moldura no marcado são iguais aos do limpo.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar.** Margem de 80 pt, com `--dpi` no limpo e no marcado. O marcado desenha **no pixmap**, com a caixa afastada 4 pt da moldura. A miniatura é a página inteira a 72 dpi, com a posição marcada.
- [ ] **Step 4: Rodar** os dois arquivos do diff, ruff e format. Expected: PASS.
- [ ] **Step 5: Commit** (`feat: recortes e fila de classificacao no diff de simbolos`).

### Task 6: Medir e classificar

**Estimativa:** 35 min · **Depende de:** Tasks 2 e 5 · **Risco:** normal · **Laboratório:** não

Sem código e sem commit. Não entra no ciclo testador/revisora; a conferência é a do Step 4.

- [ ] **Step 1: Medir.** O orquestrador roda, com o `--processos` do orçamento:
  - `.venv/Scripts/python.exe -m scripts.benchmark_simbolos_ficha --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/e06-2-2-2/simbolos --metodo atual --metodo pacotes --metodo modelo --processos 10`
  - `.venv/Scripts/python.exe -m scripts.diff_simbolos_nucleo_motor --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/e06-2-2-2/diff --processos 10 --recortes`
- [ ] **Step 2: Rotular** (R-E06.2.2.2-5 e -7). Uma instância lê `recortes/fila.json` e, para cada id, abre a miniatura, o limpo e o marcado, com a `descricao` da fila. Grava em `<checkout principal>/tmp/e06-2-2-2/classificacao.md`: id; forma; papel; o que os pixels mostram; `exposicao: sim`; o id do modelo. Não vê a ficha, o JSON nem o `.md` do diff, nem as predições do motor.
- [ ] **Step 3: Causa e segunda leitura.** Para cada `nao_confere`, uma segunda instância nova lê os mesmos recortes sem ver o primeiro rótulo; divergência entre as duas vira `ilegivel`. Para cada `falso_positivo` que sobrar, uma instância com acesso ao item do JSON (`textos`, `glifos_lidos`, `diagnosticos`) e ao código dá `causa_confirmada`, `causa_refutada` ou `indeterminada`, pela lista de divergências do handoff da E06.2.1 (`Q`+`DP`, sobreimpressão, spans a 90/180/270°, `qu` inclinado, borda, contorno de letra na moldura, orientação R-7) ou `nova`. Cada `ilegivel` relê em `--dpi 600`, com `--saida` própria (`tmp/e06-2-2-2/diff-600`), localizando o item pela chave natural.
- [ ] **Step 4: Conferir.** O orquestrador lê os recortes de todo `falso_positivo` e `provisorio`, e de uma amostra de até 5 `verdadeiro` sorteada com `random.Random(20261107)`, registra a conferência como não independente e aplica R-E06.2.2.2-6, com uma ruling por item no ledger. Grava no ledger o `sha256` de `classificacao.md` e de `diff/diff-nucleo-motor.json` e o hash dos `referencia.json` da rodada: a partir daqui os dois arquivos estão congelados.
- [ ] **Step 5: Decidir as divergências.** Para cada divergência em que o núcleo afirma a mais, do handoff da E06.2.1: observada em quantos itens e qual decisão. Para as que perdem recall: quantos `so_motor` por variante e causa provável, sem classificar um a um. Vai ao handoff.

### Task 7: Fechar os itens em código (condicional)

**Estimativa:** até 45 min · **Depende de:** Task 6 · **Risco:** alto · **Laboratório:** não

Só existe se a Task 6 decidir corrigir um item, aceitar uma divergência `nova` com `causa_confirmada` ou mudar o limite (R-E06.2.2.2-4). Sem isso, o ledger registra e a tarefa é pulada. Antes do despacho, o orquestrador emenda esta seção com arquivos, estimativa e o item (R-E06.2.2.2-8).

**Files:** os da emenda, em `drawing_model/` e `tests/unit/`; para correção, também `adapters/analysis/model_symbols.py` e `tests/unit/test_model_symbols.py:588` (literal da versão).

- [ ] **Step 1: Teste.** Na correção, inverta o teste que fixa a divergência (não remova), com fixture sintética positiva e negativa. Na `nova` aceita, escreva o teste "valor de hoje, inverter, não remover". Sem memorizar coordenada, hash ou folha.
- [ ] **Step 2: Corrigir** no núcleo, com uma guarda local (só na correção).
- [ ] **Step 3: Subir `_VERSAO`** em `model_symbols.py` para `1.0.1` e ajustar o literal (só na correção; a saída muda).
- [ ] **Step 4: Rodar** `tests/unit/test_grammar_frames_ataque.py`, `tests/unit/test_symbol_matcher_ataque.py`, `tests/unit/test_grammar_disc.py`, `tests/unit/test_model_symbols.py`, `tests/integration/test_model_symbols_runner.py`, a suíte inteira uma vez, mypy, ruff, format e `scripts/complexity_gate.py src`.
- [ ] **Step 5: Commit**, um por divergência (`fix: <divergencia> deixa de afirmar a mais no nucleo` ou `test: fixa <divergencia> como valor de hoje`).

Depois de uma correção, o orquestrador repete uma vez o benchmark e o diff, com `--saida` própria (`tmp/e06-2-2-2/simbolos-pos` e `diff-pos`), e compara com o JSON congelado pela chave natural (R-E06.2.2.2-9): o item saiu; `ambos` por variante não cai; `so_motor` não sobe; e todo `so_nucleo` novo é classificado como na Task 6. Se falhar, a correção é revertida e o item vira aceite com ruling.

## Fechamento operacional

| Critério de aceite | Evidência |
|---|---|
| O benchmark mede o método novo nas 16 folhas, ao lado do atual | Tasks 2 e 6; `tmp/e06-2-2-2/simbolos/simbolos-ficha.md`, com `comparacao` |
| Diff por variante e folha, sem passar pela ficha, em `tmp/`, cada "só no núcleo" listado e classificado | Tasks 4, 5 e 6; `tmp/e06-2-2-2/diff/` e `classificacao.md` |
| Gasto real de orçamento e o limite de `LIMITE_CONSULTAS_PAGINA` no handoff | Tasks 3 e 4; R-E06.2.2.2-4 |
| `scripts.audit_symbol_packages` → 0 erros | o orquestrador roda antes do `#concluida` |
| `IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` | `cmd.exe //c ".\\IniciarTestes.bat"`, conferindo a data do relatório |

No handoff, para a E06.3:
- a linha de base dos três métodos, com o aviso de que o benchmark por ficha quase não discrimina: 177 das 179 referências são de classes sem variante habilitada (levantamento da E06.1);
- as divergências decididas, o gasto por fase, porque as gramáticas novas gastam do mesmo limite, e os `so_motor` por causa, porque a perda de recall define a prioridade dela;
- `gasto_por_fase` e o diff, para reusar;
- os `provisorio`.

Para a E09, como critério de aceite: cada falso positivo aceito e cada `legenda`. Esta etapa só edita a própria seção do roadmap, e a E06.2.2.2 não é dependência direta da E09, então o critério fica no handoff e em "Decisões para o usuário", com o pedido de um ponteiro na seção da E09, feito pelo usuário ou pelo arquiteto.

Em "Decisões para o usuário": cada falso positivo aceito com ruling, o limite, se mudar, a classificação ser exposta e de uma só máquina (sem amostra humana), e o ponteiro na E09, se houver item.
