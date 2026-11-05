# E17 — Fechamento do cliente com servidor lento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fechar a janela do cliente nunca destrói uma `QThread` viva, mesmo com o servidor lento. Com isso, o monkeypatch de 60 s do `tests/conftest.py` sai e os testes de cliente intermitentes sob carga ficam estáveis.

**Architecture:** o fechamento é adiado, não forçado. O painel de projeto passa a dizer quando todas as threads de observação (observação global e pesquisa) terminaram. Ele já faz o cancelamento cooperativo: `_global_poll_stop` e `requestInterruption`. A `MainWindow` pede o encerramento. Se alguma thread ainda roda, a janela é escondida, o `closeEvent` é ignorado e o fechamento se refaz quando o painel avisar. Nenhuma thread é esperada sem limite na thread da UI.

**Tech Stack:** Python 3.11, PySide6 6.11 (`QThread`, sinais), pytest com `QT_QPA_PLATFORM=offscreen` e testes em subprocesso.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E17 — Fechamento do cliente com servidor lento", e o handoff da E14 (I-1, I-2, correção 37bc2ee do ciclo de vida da observação).

## Global Constraints

- O cliente não importa nada do servidor (`scripts/client_artifact_gate.py`). Projeções e decisões continuam no servidor (ADR 0013).
- Fora de escopo: servidor, contratos e API. O ciclo de vida já corrigido na E14 (37bc2ee, "só a thread atual limpa as referências") não muda.
- Nunca destruir uma `QThread` em execução. Isso vale para a observação global, a pesquisa e as threads de análise e portabilidade que o fechamento já espera.
- Testes de UI com `QT_QPA_PLATFORM=offscreen`. Teste novo não depende de ordem, cwd, porta ou arquivo fixo e usa `tmp_path`. Worker que morre sem traceback (`node down`, 0xC0000409) é defeito.
- Teste intermitente achado é corrigido, nunca marcado para repetir (regra da E14).
- Pytest com `--strict-markers` e `ResourceWarning` como erro.
- Sem dependência nova. Gate de complexidade com CC < 31 em `src/`.
- **Arquivos disjuntos com a E06.1 aberta (trilha A):** não tocar em `src/zeny_project_handler/`, `src/zeny_project_handler_server/`, `scripts/` nem `tests/unit/test_drawing_model*`, `tests/unit/test_benchmark_simbolos_ficha*`, `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_e06_1_etapa_ataque.py`, `tests/server/test_jobs_api.py` ou `tests/server/test_job_store_relogio_ataque.py`. `CLAUDE.md` só muda se a mudança tornar falso o parágrafo do `QThread`/`node down`, e então só esse parágrafo, porque a E06.1 não toca no `CLAUDE.md`.
- Suíte inteira: `-n` informado em cada despacho, pelo orçamento de máquina.

## Decisões de desenho (rulings do planejador)

- **R-E17-1, fechamento adiado em vez de espera longa.** O `closeEvent` continua esperando no máximo `_CLOSE_WAIT_MS` (300 ms, `main_window.py:51`) pelas threads de observação. Se alguma ainda roda, faz `event.ignore()` e `self.hide()`, marca `_fechamento_adiado = True` e liga, uma única vez, o sinal `observacao_encerrada` do painel a `self.close` com `Qt.QueuedConnection`. No segundo `closeEvent`, as threads já terminaram e o fechamento segue o caminho normal: `pdf_viewer.encerrar()`, `_save_ui_state()`, `release_resources()`. A UI não trava além dos 300 ms.
- **R-E17-2, prazo máximo e estouro.** O prazo máximo efetivo do fechamento adiado é o timeout HTTP do gateway de projeto, `HttpProjectGateway.timeout_seconds = 30.0` (`project_gateway.py:161`), mais uma volta do laço de observação (`_poll_seconds`). A leitura de sessão em curso termina por resposta ou por timeout, e a thread sai pelo `_global_poll_stop`. Se o gateway não tiver timeout (gateway falso de teste), a janela fica escondida até a thread terminar. **Nunca há destruição forçada nem `os._exit`.** O comportamento fica documentado na docstring de `closeEvent`.
- **R-E17-3, o processo não sai enquanto a janela está escondida.** `QApplication.quitOnLastWindowClosed` (padrão `True`) dispara ao fechar a última janela, não ao escondê-la. A Task 2 prova isso no teste em subprocesso: o processo só sai depois que a thread termina e o segundo `close()` roda.
- **R-E17-4, a pesquisa entra no encerramento.** Hoje `shutdown_polling` só pede interrupção à `_search_thread` (`project_panel.py:1062-1063`) e não a espera. Com o painel destruído, ela também pode morrer viva. O conjunto "observação encerrada" passa a ser observação global mais pesquisa.
- **R-E17-5, o conftest perde o monkeypatch.** `_esperar_threads_do_painel_ate_o_fim` e o seu uso saem de `tests/conftest.py`. O teardown da fábrica (`application_factory`, `conftest.py:186`) continua juntando as threads com prazo longo antes de destruir as janelas. Isso é higiene de teste, não encobre o `closeEvent`. Se o teardown passar a fechar pela janela, ele tem de esperar o fechamento adiado concluir.

## Review Focus

1. Fechar a janela duas vezes rápido, ou fechar com análise em andamento (o `QMessageBox` existente) e a observação lenta ao mesmo tempo, não pode duplicar a conexão `observacao_encerrada → close` nem destruir thread viva → teste na Task 2.
2. A thread de observação termina entre o `shutdown_polling` e o `hide()` (corrida): o sinal pode já ter sido emitido. O fechamento não pode ficar preso escondido para sempre → teste na Task 2 (a janela confere de novo o estado depois de conectar).
3. `restart_polling` depois de um fechamento adiado cancelado: hoje o usuário não reabre uma janela escondida. Uma reconexão programática não pode zerar `_fechamento_adiado` de forma que a janela nunca feche → teste na Task 1 ou na 2.
4. Gateway sem timeout (falso de teste que bloqueia até um evento): o processo fica vivo até o evento, a thread termina e o processo sai 0 → teste em subprocesso na Task 2.
5. A pesquisa em curso (`ProjectSearchThread`) bloqueada no gateway durante o fechamento também não pode morrer viva → teste na Task 1.

---

## File Structure

| Arquivo | Ação | Responsabilidade | Task |
|---|---|---|---|
| `src/zeny_project_handler_client/ui/project_panel.py` | modificar | sinal `observacao_encerrada`, `observacao_ativa()`, encerramento que cobre a pesquisa | 1, 3 |
| `tests/unit/test_project_panel_encerramento.py` | criar | contrato do encerramento do painel | 1 |
| `src/zeny_project_handler_client/ui/main_window.py` | modificar | `closeEvent` com fechamento adiado | 2 |
| `tests/conftest.py` | modificar | remover `_esperar_threads_do_painel_ate_o_fim` e o seu uso | 2 |
| `tests/integration/test_main_window_fechamento_servidor_lento.py` | criar | regressão em subprocesso, com leitura de sessão de 1,6 s | 2 |
| `tests/integration/test_application_factory_teardown.py` | modificar (se a Task 3 provar a causa no teste) | estabilidade sob carga | 3 |
| `tests/integration/test_project_panel_polling_restart.py`, `..._casos.py` | modificar (se a Task 3 provar a causa no teste) | estabilidade sob carga | 3 |

## Tarefas e ondas

| Task | Estimativa | Depende de | Risco | Laboratório |
|---|---|---|---|---|
| 1 — encerramento do painel com sinal | 40 min | nenhuma | alto (threads) | não |
| 2 — fechamento adiado da janela e conftest sem monkeypatch | 45 min | Task 1 | alto (threads) | não |
| 3 — testes intermitentes do cliente sob carga | 45 min | Task 2 | alto (threads) | não |

As três tarefas rodam em série, na branch da trilha: dependem uma da outra e dividem `project_panel.py`. A soma é ~2h10.

---

### Task 1: encerramento do painel com sinal

**Files:**
- Modify: `src/zeny_project_handler_client/ui/project_panel.py` (`shutdown_polling`, término das threads de observação e de pesquisa)
- Test: `tests/unit/test_project_panel_encerramento.py`

**Interfaces:**
- Produces:
  - `ProjectPanelWidget.observacao_encerrada: Signal()`. É emitido uma vez por chamada de `shutdown_polling` quando a observação global e a pesquisa não estão mais rodando. Se nada roda no momento da chamada, é emitido via `QTimer.singleShot(0, …)`, para manter o contrato assíncrono.
  - `ProjectPanelWidget.observacao_ativa() -> bool`: `True` se a thread de observação global ou a de pesquisa está rodando.
  - `shutdown_polling(timeout_ms: int = 1_000) -> bool` mantém a assinatura. Agora devolve `True` só quando **as duas** threads terminaram dentro do prazo, e espera a pesquisa no mesmo prazo total.
- Consumes: o ciclo de vida da E14 (só a thread atual limpa as referências, `_global_polling_destroyed`).

- [ ] **Step 1: Write the failing tests**, com gateway falso que bloqueia `session()` e `search` até um `threading.Event`:
  - `test_shutdown_com_observacao_lenta_devolve_false_e_emite_quando_terminar`: `shutdown_polling(100)` → `False`, e `observacao_ativa()` → `True`. Depois que o evento é liberado, `observacao_encerrada` é emitido exatamente 1 vez (conte com `qtbot.waitSignal` ou com um contador e `QCoreApplication.processEvents` até um prazo) e `observacao_ativa()` → `False`.
  - `test_shutdown_sem_threads_emite_assincrono`: sem thread rodando, `shutdown_polling()` → `True`, e o sinal chega no próximo giro do laço, não dentro da chamada.
  - `test_pesquisa_em_curso_entra_no_encerramento`: pesquisa bloqueada no gateway → `shutdown_polling(100)` → `False`. Liberada, o sinal é emitido e a `QThread` da pesquisa não está mais rodando.
  - `test_restart_depois_do_shutdown_nao_emite_sinal_velho`: `shutdown_polling` com thread lenta, depois `restart_polling()` antes de a thread velha terminar. A thread velha terminar não pode emitir `observacao_encerrada` para a geração nova, ou, se emitir, isso tem de estar documentado e testado. Use a geração de conexão (`_connection_generation`) para decidir.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_project_panel_encerramento.py -q` → FAIL (`AttributeError: observacao_encerrada`).
- [ ] **Step 3:** implemente. Os testes existentes de polling (`tests/integration/test_project_panel_polling_restart*.py`) continuam verdes sem edição.
- [ ] **Step 4:** os testes novos e os de polling e painel (`-k "project_panel or polling"`) → PASS. ruff, format, mypy e `complexity_gate` limpos.
- [ ] **Step 5: Commit** (`feat: painel avisa quando a observacao encerrou`).

### Task 2: fechamento adiado da janela e conftest sem monkeypatch

**Files:**
- Modify: `src/zeny_project_handler_client/ui/main_window.py:678-708` (`closeEvent`), `tests/conftest.py:55-80` (o monkeypatch e o seu uso)
- Test: `tests/integration/test_main_window_fechamento_servidor_lento.py`

**Interfaces:**
- Consumes: `observacao_encerrada`, `observacao_ativa()` e `shutdown_polling(timeout_ms) -> bool` da Task 1.
- Produces: `MainWindow._fechamento_adiado: bool`, o comportamento R-E17-1/2/3 e a docstring de `closeEvent` com o prazo máximo e o que acontece quando ele estoura.

- [ ] **Step 1: Write the failing tests** em `tests/integration/test_main_window_fechamento_servidor_lento.py`, no padrão de subprocesso de `tests/integration/test_application_factory_teardown.py`: cenário gravado em `tmp_path`, `pytest -p tests.conftest -n 0` num subprocesso e asserção no código de saída.
  - `test_fechar_com_leitura_de_sessao_de_1_6_s_nao_aborta`: o gateway falso dorme 1,6 s em `session()`, e a janela é fechada durante a leitura. O código de saída é 0, e o critério 1 pede vermelho com 3221226505 antes da correção. Rode-o primeiro contra o código atual **sem** o monkeypatch do conftest e registre o código de saída vermelho no relatório. Depois aplique a correção e confirme o verde.
  - `test_fechamento_adiado_esconde_e_fecha_depois`: no mesmo processo, sem subprocesso, `close()` durante a leitura lenta deixa `isVisible()` → `False` e `_fechamento_adiado` → `True`, e a janela não foi destruída. Quando a leitura termina, a janela fecha de verdade (`release_resources` chamado uma vez).
  - `test_dois_closes_rapidos_nao_duplicam_conexao` e `test_thread_termina_entre_shutdown_e_hide` (Review Focus 1 e 2).
  - `test_gateway_sem_timeout_fica_escondido_ate_liberar` (Review Focus 4): em subprocesso, com o gateway bloqueado num evento liberado por timer depois de 2 s → saída 0.
- [ ] **Step 2:** os testes novos → FAIL contra o código atual. O de subprocesso tem de sair 3221226505 ou outro código de aborto, e o código fica registrado.
- [ ] **Step 3:** implemente o `closeEvent` (R-E17-1) e remova o monkeypatch do conftest (R-E17-5). O teste `tests/integration/test_application_factory_teardown.py` tem de continuar verde. Se ele dependia do monkeypatch, relate antes de mudar.
- [ ] **Step 4:** os testes novos, `tests/integration/test_application_factory_teardown.py`, os de polling e `tests/test_mvp_ui.py` (ou equivalente que cubra `closeEvent`) → PASS. ruff, format, mypy, `complexity_gate` e `client_artifact_gate --source-only` limpos. Suíte inteira uma vez, com o `-n` do despacho.
- [ ] **Step 5: Commit** (`fix: fechar a janela adia a destruicao ate a observacao encerrar`).

### Task 3: testes intermitentes do cliente sob carga

**Files:**
- Modify: só o que a investigação provar ser a causa, entre `src/zeny_project_handler_client/ui/project_panel.py`, `src/zeny_project_handler_client/ui/main_window.py` e os testes `tests/integration/test_application_factory_teardown.py`, `test_project_panel_polling_restart.py` e `test_project_panel_polling_restart_casos.py`.

**Interfaces:** nenhuma pública nova.

Contexto: na execução paralela da E15 e da E06.1, com 3 suítes `-n 6` simultâneas, falharam de forma intermitente:
- `test_project_panel_polling_restart_casos.py::test_casos_de_borda_da_destruicao_tardia_da_thread_de_observacao` (várias vezes);
- `test_project_panel_polling_restart.py::test_destruicao_tardia_da_thread_antiga_nao_solta_a_thread_reiniciada`;
- `test_application_factory_teardown.py::test_leitura_de_sessao_mais_lenta_que_o_fechamento_nao_destroi_thread_em_execucao`, com 1 falha em 5 execuções isoladas.

Todos passam isolados na maioria das vezes. O handoff da E14 registra cenários de reinício com `sleep` de 1,2 e 1,6 s contra o prazo padrão de 1000 ms.

- [ ] **Step 1:** use `superpowers:systematic-debugging`. Reproduza sob carga: rode os 3 arquivos 20 vezes com `-n 6` enquanto outra suíte `-n 6` roda em paralelo, no mesmo worktree, com `--basetemp` distintos. Registre a taxa de falha e a saída de cada falha (código de saída do subprocesso, stderr).
- [ ] **Step 2:** ache a causa. Ela pode estar no código (thread destruída viva noutro caminho) ou no teste (prazo de parede curto sob carga). Escreva o teste determinístico que a reproduz sempre, por exemplo com gateway controlado por evento em vez de `sleep`.
- [ ] **Step 3:** corrija a causa. Se for no teste, troque a espera por tempo de parede por sincronização por evento ou sinal, sem alargar prazo nem repetir. Se for no código, corrija o código.
- [ ] **Step 4:** a mesma carga do Step 1 → 20/20 verdes nos 3 arquivos. Suíte inteira uma vez.
- [ ] **Step 5: Commit** (`fix:`/`test:` conforme a causa).

---

## Fechamento operacional (orquestrador)

1. Critério 1: o código de saída vermelho (3221226505) antes e o verde depois, tirados do relatório da Task 2, e o `git grep -n "_esperar_threads_do_painel_ate_o_fim\|_PRAZO_ENCERRAR_THREADS_MS" tests/conftest.py` mostrando que o monkeypatch saiu (o teardown pode manter o prazo próprio, R-E17-5).
2. Critério 2: o prazo máximo e o comportamento ao estourar (R-E17-1/2) na docstring de `closeEvent` e no handoff.
3. `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`, sem outra suíte da sessão rodando.

## Critérios de aceite → evidência

| Critério | Evidência |
|---|---|
| teste em subprocesso com leitura de 1,6 s: vermelho antes (3221226505), verde depois, sem o monkeypatch | Task 2, Step 2 e Step 4; passo 1 do fechamento |
| fechamento sem travar a UI além do necessário; prazo e estouro documentados | R-E17-1/2; docstring; passo 2 |
| `.bat` aprovado | passo 3 |
