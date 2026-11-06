# E17 — Fechamento do cliente com servidor lento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fechar a janela do cliente nunca destrói uma `QThread` viva, nem na janela nem no fim do processo, mesmo com o servidor lento. O monkeypatch de 60 s sai do `tests/conftest.py`, e os testes de cliente que falham de forma intermitente sob carga ficam estáveis.

**Architecture:** o fechamento é adiado, nunca forçado. O painel de projeto e os registros de threads remotas dizem quando não há mais thread de rede rodando. O cancelamento cooperativo já existe: `_global_poll_stop` e `requestInterruption`. A `MainWindow` pede o encerramento e espera até 1000 ms. Se ainda há thread rodando, a janela continua **visível e desabilitada**, com "Encerrando…". O `closeEvent` é ignorado, e um slot de uso único refaz o fechamento quando o estado passa a "nada rodando". O segundo fechamento é o caminho normal, com a janela visível, e o `quitOnLastWindowClosed` encerra o `exec()`.

**Tech Stack:** Python 3.11, PySide6 6.11 (`QThread`, sinais), pytest com `QT_QPA_PLATFORM=offscreen` e testes em subprocesso.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E17 — Fechamento do cliente com servidor lento", e o handoff da E14: I-1, I-2, a correção 37bc2ee e o minor "cenários de reinício com `sleep` de 1,2 e 1,6 s contra o prazo padrão de 1000 ms".

## Global Constraints

- O cliente não importa nada do servidor (`scripts/client_artifact_gate.py`). Projeções e decisões continuam no servidor (ADR 0013).
- Fora de escopo: servidor, contratos e API. O ciclo de vida já corrigido na E14 (37bc2ee, "só a thread atual limpa as referências") não muda.
- Nunca destruir uma `QThread` em execução, nem por destruição do dono nem no fim do processo. Isso vale para a observação global, a pesquisa (`ProjectSearchThread`), as leituras remotas (`RemoteRequestThread`) e as threads de análise e portabilidade que o fechamento já espera.
- Testes de UI com `QT_QPA_PLATFORM=offscreen`. Teste novo não depende de ordem, cwd, porta ou arquivo fixo e usa `tmp_path`. Teste com thread bloqueada num `threading.Event` libera o evento e junta a thread num `try/finally` antes de destruir o dono. Worker que morre sem traceback (`node down`, 0xC0000409) é defeito.
- Teste intermitente achado é corrigido, nunca marcado para repetir (regra da E14). Prazo de produto não é alargado para fazer teste passar.
- Pytest com `--strict-markers` e `ResourceWarning` como erro.
- Sem dependência nova. Gate de complexidade com CC < 31 em `src/`.
- **Arquivos disjuntos com a E06.1 aberta (trilha A):** não tocar em `src/zeny_project_handler/`, `src/zeny_project_handler_server/`, `scripts/`, `tests/unit/test_drawing_model*`, `tests/unit/test_pymupdf_drawing_model_pagina*`, `tests/unit/test_benchmark_simbolos_ficha*`, `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_e06_1_etapa_ataque.py`, `tests/server/test_jobs_api.py` nem `tests/server/test_job_store_relogio_ataque.py`. `CLAUDE.md` só muda se a mudança tornar falso o parágrafo do `QThread`/`node down`, e então só esse parágrafo.
- Suíte inteira: `-n` informado em cada despacho (orçamento de máquina: 20 ÷ suítes simultâneas da sessão, mínimo 2).

## Decisões de desenho (rulings do planejador)

- **R-E17-1, fechamento adiado com a janela visível.** O `closeEvent` pede o encerramento e espera até `_PRAZO_OBSERVACAO_MS = 1000` (o prazo de hoje, `main_window.py:703`).
  - Se ainda há thread de rede rodando:
    - `event.ignore()`;
    - `setEnabled(False)` e o status "Encerrando: aguardando o servidor responder";
    - `_fechamento_adiado = True`;
    - liga o sinal `rede_encerrada` a um slot de uso único, `_concluir_fechamento_adiado`, que desconecta, confere `rede_ativa()` e só então chama `close()`.
  - Depois de conectar, a janela confere `rede_ativa()` de novo, o que fecha a corrida do Review Focus 2.
  - O segundo `closeEvent` não arma o adiamento de novo: com `_fechamento_adiado` ligado e nada rodando, segue o caminho normal (`pdf_viewer.encerrar()`, `super().closeEvent`, `_save_ui_state()`, `release_resources()`). Com coisa ainda rodando, só ignora.
  - **Alternativa descartada:** esconder a janela (`hide()`). Ela depende de como o Qt trata `lastWindowClosed` com a janela escondida: pode encerrar o `exec()` cedo e destruir a thread viva, ou nunca encerrar, deixando o processo invisível e o servidor efêmero do `.bat` no ar.
  - Os 300 ms de `_CLOSE_WAIT_MS` continuam valendo só para análise e portabilidade, como hoje.
- **R-E17-2, prazo máximo e estouro.**
  - A espera real é limitada pelo timeout por operação de socket do gateway (`timeout_seconds = 30.0`, `project_gateway.py:161`), não por um teto total. `session()` é GET com `_READ_RETRIES = 1` (`:47`, `:478-487`), e a pesquisa tem o mesmo perfil. Assim, um servidor que aceita a conexão e não responde dá ≈ 2 tentativas × 30 s ≈ **60 s**. Um servidor que goteja bytes dá **espera sem teto**.
  - Decisão: (a) aceitar a espera sem teto, com a janela visível e desabilitada e o motivo na tela. Nenhuma destruição forçada.
  - **Alternativas descartadas:**
    - (b) cancelar o HTTP em curso fechando a conexão a partir da thread da UI: muda o gateway em todos os métodos e tem corrida com `http.client`; fica para uma etapa futura, se o usuário pedir;
    - (c) teto com `os._exit` depois de salvar o estado: mata o processo com threads de rede no meio e esconde o defeito.
  - A docstring de `closeEvent` registra o teto real e o comportamento quando ele estoura.
- **R-E17-3, o processo sai pelo `exec()`.** Como a janela continua visível, o segundo `close()` dispara o `quitOnLastWindowClosed` normal. A Task 2 prova isso num subprocesso que roda `create_application` com gateways falsos e um `QTimer` que fecha a janela, e entra em `app.exec()` de verdade. O teste afirma três coisas: saída 0, duração limitada e nenhuma thread rodando quando o `exec()` retorna.
- **R-E17-4, o que é "thread de rede".** A observação global do painel (`_global_poll_thread`) mais as threads registradas nos conjuntos de módulo `project_search._RUNNING_SEARCHES` e `remote_read._RUNNING`. Essas duas não têm pai, então destruir o painel não as destrói. O risco delas está no fim do processo, quando `run()` retorna com elas rodando. Elas são usadas por pesquisa, mercado, documentação e GMAX.
  - O fechamento pede `requestInterruption()` a todas e espera que terminem.
  - O contrato público é `rede_ativa() -> bool`, calculado a partir desses registros e da observação.
- **R-E17-5, o sinal é de estado.** `rede_encerrada` é emitido na thread da UI quando `rede_ativa()` passa de `True` a `False` depois de um pedido de encerramento, e emite uma vez por pedido.
  - **Token próprio:** o pedido guarda um `_token_encerramento` (inteiro) que **só** `restart_polling()` incrementa e cancela. `shutdown_polling` e `set_connection_available` não mexem nele, e é por isso que ele não usa `_connection_generation`. O motivo: com o servidor mudo, `ReconnectableGateway.guarded` emite `failure_detected` → `lost` → `connection_lost` → `set_connection_available(False)` → `shutdown_polling()`, que incrementa `_connection_generation` (`connection.py:50-53,81-87`; `bootstrap.py:249-251`; `main_window.py:636`; `project_panel.py:1059`). Com a geração, o pedido seria invalidado e a janela ficaria presa.
  - Pedido feito com nada rodando emite via `QTimer.singleShot(0, …)`.
  - A conferência `_conferir_encerramento()` roda (i) no `finished` em fila da observação global e (ii) na notificação dos registros (R-E17-9).
- **R-E17-8, rede de segurança contra notificação perdida.** Durante o adiamento, um `QTimer` da `MainWindow` de 250 ms reconfere `rede_ativa()` e chama `_concluir_fechamento_adiado()` assim que dá `False`. O timer para no fechamento. Assim, nenhuma classe de notificação perdida (ordem `_dispose` × conferência, thread de outro painel, perda de conexão) prende a janela. O sinal continua sendo o caminho rápido.
  - Com `_fechamento_adiado` ligado, `MainWindow.set_connection_available` não chama `shutdown_polling` nem reconecta, e só registra o evento no log.
- **R-E17-9, os registros notificam o término.** `remote_read` e `project_search` ganham, cada um, um `QObject` de módulo (`notificador_leituras`, `notificador_pesquisas`) com o sinal `terminou`. Ele é emitido dentro de `_dispose`, **depois** do `discard`. `leituras_ativas()` e `pesquisas_ativas()` contam só os membros com `isRunning()`. O painel liga `_conferir_encerramento` aos dois sinais **só enquanto há pedido pendente**, e desconecta ao emitir ou ao cancelar (R2-M1: o painel destruído nunca fica ligado ao notificador de módulo). Os notificadores são criados de forma preguiçosa, no primeiro `launch()`, na thread principal (R2-M2). Os registros valem para o processo inteiro, então `rede_ativa()` conta também as threads de outra janela do mesmo processo: isso é seguro, porque só faz esperar mais, e fica na docstring.
- **R-E17-10, o fechamento depois do `exec()`.** `bootstrap.run()` chama `window.close()` no `finally`, depois do `exec()` (`bootstrap.py:325-326`). Esse terceiro `closeEvent`, com a janela já fechada, não roda `release_resources()` de novo nem rearma o adiamento.
- **R-E17-6, o conftest perde o monkeypatch.** `_esperar_threads_do_painel_ate_o_fim` e o seu uso (`tests/conftest.py:59-80`, `:103`) saem. O teardown da fábrica (`conftest.py:186`) continua juntando as threads com o prazo próprio `_PRAZO_ENCERRAR_THREADS_MS` antes de destruir as janelas: isso é higiene de teste e não encobre o `closeEvent`.
  - Os testes que só passavam por causa do monkeypatch são corrigidos no mesmo commit (Task 3). Os cenários de polling dormem 1,2 a 1,6 s em `session()` contra o prazo de 1000 ms (`test_project_panel_polling_restart.py:72`, `test_project_panel_polling_restart_casos.py:80,84,92,104,117,119`).
- **R-E17-7, estimativa.** A spec previa ~1h. A revisão mostrou que o fechamento cobre também as threads remotas e que o monkeypatch encobre testes que dependem dele. A soma passa a ~2h50, dentro do teto de ~3h. A ruling fica no handoff.

## Review Focus

1. Dois `close()` rápidos, ou fechamento com análise em andamento (o `QMessageBox` existente) junto com observação lenta, não podem duplicar a conexão nem destruir thread viva → teste na Task 2.
2. A thread termina entre o pedido e a conexão do slot (corrida) → o fechamento não fica preso desabilitado → teste na Task 2.
3. `restart_polling` depois de um pedido de encerramento → a thread velha não dispara o fechamento → teste na Task 1.
4. O gateway falso sem timeout, que bloqueia num evento, mantém o processo vivo até o evento. A thread termina e o processo sai com 0 → teste em subprocesso na Task 2.
5. Pesquisa ou leitura remota (mercado/GMAX/documentação) em curso no fechamento não pode morrer viva no fim do processo → testes nas Tasks 1 e 2.

---

## File Structure

| Arquivo | Ação | Responsabilidade | Task |
|---|---|---|---|
| `src/zeny_project_handler_client/ui/project_panel.py` | modificar | `rede_encerrada`, pedido de encerramento por estado, `rede_ativa()` (observação + registros) | 1 |
| `src/zeny_project_handler_client/ui/remote_read.py` | modificar | `leituras_ativas() -> bool`, `interromper_leituras() -> None` sobre `_RUNNING` | 1 |
| `src/zeny_project_handler_client/ui/project_search.py` | modificar | `pesquisas_ativas() -> bool`, `interromper_pesquisas() -> None` sobre `_RUNNING_SEARCHES` | 1 |
| `tests/unit/test_project_panel_encerramento.py` | criar | contrato do encerramento por estado | 1 |
| `src/zeny_project_handler_client/ui/main_window.py` | modificar | `closeEvent` com fechamento adiado, visível e desabilitado, e log do adiamento | 2 |
| `tests/integration/test_main_window_fechamento_servidor_lento.py` | criar | regressão em subprocesso com 1,6 s, `exec()` real, dois `close()`, corrida e gateway sem timeout | 2 |
| `tests/conftest.py` | modificar | remover `_esperar_threads_do_painel_ate_o_fim` e o seu uso | 3 |
| `tests/integration/test_project_panel_polling_restart.py`, `tests/integration/test_project_panel_polling_restart_casos.py` | modificar | gateway por evento ou prazo explícito, no lugar de `sleep` contra 1000 ms | 3 |
| `tests/integration/test_window.py`, `tests/integration/test_client_reconnection.py`, `tests/integration/test_panel_scroll.py`, `tests/integration/test_protected_pdf_ui.py`, `tests/e2e/test_span_compliance_ui.py` | modificar (só onde fecham e conferem na mesma linha) | esperar o fim do fechamento antes de conferir | 3 |
| `tests/integration/test_application_factory_teardown.py` | modificar (se a Task 4 provar a causa no teste) | estabilidade sob carga | 4 |

## Tarefas e ondas

| Task | Estimativa | Depende de | Risco | Laboratório |
|---|---|---|---|---|
| 1 — encerramento por estado no painel e nos registros | 45 min | nenhuma | alto (threads) | não |
| 2 — fechamento adiado da janela com `exec()` real | 45 min | Task 1 | alto (threads) | não |
| 3 — conftest sem monkeypatch e testes que dependiam dele | 40 min | Task 2 | alto (threads, testes Qt) | não |
| 4 — resíduo intermitente sob carga, com caixa de tempo | 40 min | Task 3 | alto (threads) | não |

As tarefas rodam em série na branch da trilha, porque cada uma depende da anterior. Total ~2h50 (R-E17-7).

---

### Task 1: encerramento por estado no painel e nos registros

**Files:**
- Modify: `src/zeny_project_handler_client/ui/project_panel.py`, `src/zeny_project_handler_client/ui/remote_read.py`, `src/zeny_project_handler_client/ui/project_search.py`
- Test: `tests/unit/test_project_panel_encerramento.py`

**Interfaces:**
- Produces:
  - `remote_read.leituras_ativas() -> bool` e `remote_read.interromper_leituras() -> None`. A segunda faz `requestInterruption()` em toda thread de `_RUNNING`.
  - `project_search.pesquisas_ativas() -> bool` e `project_search.interromper_pesquisas() -> None`, as mesmas funções sobre `_RUNNING_SEARCHES`.
  - `ProjectPanelWidget.rede_encerrada: Signal()`.
  - `ProjectPanelWidget.rede_ativa() -> bool`, que dá `True` quando a observação global roda ou quando `leituras_ativas()` ou `pesquisas_ativas()` é verdadeira.
  - `ProjectPanelWidget.pedir_encerramento(timeout_ms: int) -> bool`. Faz o que `shutdown_polling` faz hoje e mais `interromper_leituras()` e `interromper_pesquisas()`. Espera até `timeout_ms` no total e devolve `not self.rede_ativa()`. O pedido fica pendente, sob `_token_encerramento`, até a emissão.
  - `remote_read.notificador_leituras.terminou: Signal()` e `project_search.notificador_pesquisas.terminou: Signal()` são emitidos em `_dispose`, depois do `discard` (R-E17-9).
  - `shutdown_polling(timeout_ms=1_000) -> bool` continua com a mesma assinatura e o mesmo comportamento, para os chamadores atuais (teardown e `set_connection_available`).
- Emissão (R-E17-5/9): o `finished` em fila da observação global e os sinais `terminou` dos dois registros chamam `_conferir_encerramento()`. Com pedido pendente, `not rede_ativa()` e token igual, o painel emite `rede_encerrada` e limpa o pedido. Só `restart_polling()` cancela o pedido, incrementando o token.

- [ ] **Step 1: Write the failing tests.** Use gateways falsos que bloqueiam `session()` ou `search` num `threading.Event`, sempre com `try/finally` que libera o evento e junta as threads:
  - `test_pedido_com_observacao_lenta_devolve_false_e_emite_uma_vez`;
  - `test_pedido_sem_threads_emite_assincrono` (não emite dentro da chamada);
  - `test_pesquisa_em_curso_entra_no_encerramento`;
  - `test_leitura_remota_em_curso_entra_no_encerramento`, com uma `RemoteRequestThread` bloqueada;
  - `test_restart_cancela_o_pedido_e_a_thread_velha_nao_emite` (Review Focus 3);
  - `test_dois_pedidos_seguidos_emitem_uma_vez_cada`;
  - `test_shutdown_por_perda_de_conexao_nao_cancela_o_pedido` (N1): pedido pendente com observação lenta, depois `shutdown_polling()`, que é o que a perda de conexão chama. A observação termina, e o sinal é emitido;
  - `test_leitura_remota_de_outro_painel_e_a_ultima_viva` (N2): a última thread viva é uma `RemoteRequestThread` criada fora do painel de projeto (por exemplo, a do mercado ou uma criada no teste). Quando ela termina, o sinal é emitido;
  - `test_ativas_conta_so_threads_rodando`: um membro do registro que já terminou, mas ainda não passou pelo `_dispose`, não conta.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_project_panel_encerramento.py -q` → FAIL (`AttributeError`).
- [ ] **Step 3:** implemente. Os testes existentes do painel, da pesquisa e das leituras remotas continuam verdes sem edição.
- [ ] **Step 4:** testes novos e `-k "project_panel or search or remote or market or gmax or documentation"` → PASS. ruff, format, mypy, `complexity_gate` e `client_artifact_gate --source-only` limpos.
- [ ] **Step 5: Commit** (`feat: painel e leituras remotas avisam quando a rede encerrou`).

### Task 2: fechamento adiado da janela com `exec()` real

**Files:**
- Modify: `src/zeny_project_handler_client/ui/main_window.py:678-708` (`closeEvent` e um slot novo; constante `_PRAZO_OBSERVACAO_MS = 1000`)
- Test: `tests/integration/test_main_window_fechamento_servidor_lento.py`

**Interfaces:**
- Consumes: `pedir_encerramento`, `rede_ativa` e `rede_encerrada` (Task 1).
- Produces:
  - `MainWindow._fechamento_adiado: bool` e o timer de reconferência de 250 ms (R-E17-8);
  - `set_connection_available` não faz nada durante o adiamento, além do log (R-E17-8);
  - `MainWindow._concluir_fechamento_adiado()`, slot de uso único;
  - a docstring de `closeEvent` com o teto real e o estouro (R-E17-2);
  - o log `logging.getLogger(__name__)` no início do adiamento e no fim, com o tempo decorrido.

- [ ] **Step 1: Write the failing tests.**
  - `test_fechar_com_leitura_de_sessao_de_1_6_s_nao_aborta`: subprocesso no padrão de `test_application_factory_teardown.py`, com cenário em `tmp_path`, **sem** o monkeypatch do conftest. Para isso, o cenário define a própria fábrica ou desliga o monkeypatch localmente. Rode-o primeiro contra o código atual e registre o código de saída vermelho (3221226505 ou outro de aborto, pelo critério 1). Depois da correção, a saída é 0.
  - `test_exec_real_sai_depois_da_thread`: subprocesso que roda um script Python, não o pytest. O script monta `create_application` com gateways falsos, cuja `session()` dorme 1,6 s, agenda o fechamento com `QTimer` e chama `app.exec()`. Afirma: saída 0; duração < 30 s; nenhuma thread de rede rodando quando `exec()` retorna (o script imprime isso antes de sair).
  - `test_fechamento_adiado_fica_visivel_desabilitado_e_fecha_depois`, em processo: `close()` durante a leitura lenta → `isVisible()` e `not isEnabled()` e `_fechamento_adiado`. Depois da leitura, a janela fecha e `release_resources` roda 1 vez.
  - `test_dois_closes_rapidos_nao_duplicam_conexao`, `test_thread_termina_entre_pedido_e_conexao` e `test_gateway_sem_timeout_espera_o_evento` (Review Focus 1, 2 e 4; o último em subprocesso, com o evento liberado por timer depois de 2 s).
  - `test_perda_de_conexao_durante_o_adiamento_nao_prende_a_janela` (N1): `window.set_connection_available(False, …)` durante o adiamento não impede o fechamento. De preferência, um segundo caso passa pelo `ReconnectableGateway` real, com um gateway falso que levanta `ProjectGatewayError(INTERNAL_ERROR)` depois de 1,6 s.
  - `test_timer_de_reconferencia_fecha_sem_sinal`: com o sinal desconectado à força no teste, o timer de 250 ms fecha a janela quando a rede encerra.
  - `test_run_com_close_no_finally_nao_repete_release` (R-E17-10): por `bootstrap.run()` com `dialog_factory` falsa, ou afirmando que o `closeEvent` seguinte ao fechamento não chama `release_resources` de novo.
- [ ] **Step 2:** os testes novos → FAIL contra o código atual. Registre o código de saída do subprocesso.
- [ ] **Step 3:** implemente o `closeEvent` (R-E17-1/2/3).
- [ ] **Step 4:** testes novos, `tests/integration/test_application_factory_teardown.py` e `tests/e2e/test_mvp_ui.py` → PASS. ruff, format, mypy, `complexity_gate` e `client_artifact_gate --source-only` limpos. Suíte inteira uma vez, com o `-n` do despacho. O monkeypatch do conftest ainda existe nesta tarefa.
- [ ] **Step 5: Commit** (`fix: fechar a janela adia ate a rede encerrar, sem destruir thread viva`).

### Task 3: conftest sem monkeypatch e testes que dependiam dele

**Files:**
- Modify: `tests/conftest.py` (R-E17-6) e os testes listados na File Structure para a Task 3, só onde precisar

**Interfaces:** helper de teste `esperar_fechamento(window, prazo_s)`. Ele processa eventos até `not window.isVisible()` e está definido no próprio `tests/conftest.py`, ou num módulo de apoio em `tests/`.

- [ ] **Step 1:** remova o monkeypatch. Rode `tests/integration/test_project_panel_polling_restart*.py` e os testes que fecham e conferem na mesma linha (`test_window.py:173-177`, `:923-925`; `test_client_reconnection.py:141-144`; `test_panel_scroll.py:289`; `test_protected_pdf_ui.py:142`; `e2e/test_span_compliance_ui.py:150`). Registre quais falham e por quê.
- [ ] **Step 2:** corrija os testes de polling, trocando o `sleep` de 1,2/1,6 s contra 1000 ms por um gateway controlado por evento ou por um prazo explícito no `shutdown_polling` do teste. Não alargue o prazo do produto. Nos testes que fecham e conferem, use `esperar_fechamento`.
- [ ] **Step 3:** os arquivos tocados ficam verdes 5 vezes seguidas, e também com o `-n` do despacho. `git grep -n "_esperar_threads_do_painel_ate_o_fim" tests/` fica vazio. Suíte inteira uma vez.
- [ ] **Step 4: Commit** (`test: conftest sem o prazo de 60 s e testes que dependiam dele`).

### Task 4: resíduo intermitente sob carga, com caixa de tempo

**Files:** só o que a investigação provar ser a causa, no cliente (`src/zeny_project_handler_client/ui/`) ou em `tests/integration/test_application_factory_teardown.py` e nos testes de polling.

**Contexto:** na execução paralela das E15 e E06.1, com 3 suítes `-n 6` ao mesmo tempo, falharam de forma intermitente:
- `test_project_panel_polling_restart_casos.py::test_casos_de_borda_da_destruicao_tardia_da_thread_de_observacao`, várias vezes;
- `test_project_panel_polling_restart.py::test_destruicao_tardia_da_thread_antiga_nao_solta_a_thread_reiniciada`;
- `test_application_factory_teardown.py::test_leitura_de_sessao_mais_lenta_que_o_fechamento_nao_destroi_thread_em_execucao`, 1 em 5 execuções isoladas.

Depois das Tasks 1–3, a parte determinística (o prazo de 1000 ms e as threads remotas) já saiu. Fica o resíduo sob carga.

- [ ] **Step 1:** use `superpowers:systematic-debugging`. **Caixa de tempo: 30 min.** Reproduza com o `-n` do despacho: rode os 3 arquivos 10 vezes seguidas, mais 1 rodada simultânea com a suíte inteira no mesmo `-n`, só quando o orquestrador avisar que não há outra suíte da sessão. Registre a taxa de falha e a saída de cada falha.
- [ ] **Step 2:** sem falha na caixa → **DONE** com evidência (taxa 0/N, comandos e saídas), sem mudança de código. Com falha, ache a causa, escreva o teste determinístico e corrija sem alargar prazo nem repetir. Se a caixa estourar sem causa, **pare** com DONE_WITH_CONCERNS, a evidência e a hipótese. O orquestrador estaciona com ruling.
- [ ] **Step 3: Commit** (se houve mudança).

---

## Fechamento operacional (orquestrador)

1. Critério 1: o código de saída vermelho antes e o verde depois (relatório da Task 2), mais `git grep -n "_esperar_threads_do_painel_ate_o_fim" tests/` vazio. O teardown mantém o próprio `_PRAZO_ENCERRAR_THREADS_MS` (R-E17-6).
2. Critério 2: espera de até 1000 ms antes de adiar, janela visível e desabilitada, teto real ≈ 60 s com o servidor mudo e sem teto com o servidor que goteja. Fica na docstring de `closeEvent` e no handoff (R-E17-1/2).
3. `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`, sem outra suíte da sessão rodando.

## Critérios de aceite → evidência

| Critério | Evidência |
|---|---|
| teste em subprocesso com leitura de 1,6 s: vermelho antes (3221226505), verde depois, sem o monkeypatch | Task 2, Steps 2 e 4; Task 3; passo 1 do fechamento |
| fechamento sem travar a UI além do necessário; prazo máximo e estouro documentados | R-E17-1/2; docstring; passo 2 |
| `.bat` aprovado | passo 3 |

## Revisão de arquitetura

- **Veredito:** aprovado com notas.
- **Rodadas:** 2. A rodada 0 bloqueou com C1, I1–I6 e M1–M6, a rodada 1 com N1 e N2 (e N3–N5 menores), e a rodada 2 aprovou com notas.
- **Modelo:** opus (`revisor-arquitetura`).
- **Notas Menores:**
  - R2-M1 (sinal de módulo ligado só com pedido pendente) e R2-M2 (notificadores preguiçosos): aplicadas no R-E17-9.
  - N5: o despacho da Task 2 avisa que os testes que fecham e conferem correm sem o monkeypatch protetor até a Task 3.
  - Não há ARCHITECTURE.md: a revisão julgou contra o CLAUDE.md, a spec E17, o ADR 0013 e o código.
