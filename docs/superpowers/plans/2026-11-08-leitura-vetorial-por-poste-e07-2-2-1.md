# E07.2.2.1 — Símbolos no poste certo e ESTAI sem duplicar: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** com a opção ligada, cada símbolo entra no poste certo ou fica pendente, o ESTAI sai em uma ocorrência só, e o poste pendente por disputa não perde as ligações que não dependem do disco.

**Architecture:** três mudanças disjuntas, só com a opção ligada: a ancoragem expõe os sítios em disputa e `_symbol_support` (`application/interpretation_pipeline.py`) os respeita (associação); `_compose` em `application/symbol_reconciliation.py` emparelha ESTAI por contenção (fusão); `_com_poste_no_texto` em `adapters/interpretation/ficha_poste.py` mantém o regime de texto (vínculos). Laboratório decide o emparelhamento e o raio.

**Tech Stack:** Python 3.11, pytest, baseline `scripts.curation_ficha`.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E07.2.2.1". Levantamento: `<checkout principal>/tmp/janela-0.6.0/levantamento-e07-2-2.md` (fora do Git). Base: `dda292a`.

## Global Constraints

- Arquitetura hexagonal; `application/` não importa adaptadores.
- Nenhuma migração, API ou DTO. O método sobre o modelo liga só no runner opt-in (D12). Com `ZENY_SERVER_SYMBOL_COMPOSITION=false`, a saída não muda: `git diff --exit-code f26cc3c -- tests/fixtures/golden_padrao_e07.json` e `git diff --exit-code 877aba1 -- tests/fixtures/golden_padrao_e07_complementar.json` saem 0.
- Ao mudar comportamento de saída, incremente a versão: `InterpretadorFichaPoste.versao` de `26.0` para `27.0` (Task 1); `SYMBOL_SEMANTICS_VERSION` para `e07-2-2-symbol-support-3` (Task 2). A fusão não precisa de versão própria: entra na identidade pelo digest de `symbol_reconciliation.py` (`symbol_execution.py:207`) via `symbol_configuration_signature`.
- Sem dependência nova. Fixtures sintéticas autorais; nenhuma coordenada, hash ou nome de folha real. Nada lê `examples/avaliacao-cega/`.
- Não tocar nos arquivos da E06.3.5, aberta em paralelo: `drawing_model/grammar_disc*.py`, `grammar_disc_mark.py`, `drawing_model/symbol_matcher.py`, `declarative_symbols.py`, `model_symbols.py`, `symbol_packages/family-f02-20.json`, `src/zeny_project_handler_server/symbol_execution.py`, `docs/schemas/pacotes-simbologia.schema.json`, `tests/fixtures/symbol_grammars/disc_mark.py`, `tests/unit/test_grammar_disc*`, `tests/unit/test_gramatica_disc_mark*`.
- **Exceção à regra de arquivos disjuntos (D19), R-E07.2.2.1-7:** `tests/integration/test_model_symbols_estai_runner.py` também é listado na E06.3.5 (contagens e versão). Alternativas: mover o teste de fusão para arquivo novo (deixaria o teste velho vermelho na E06.3.5 até o merge) ou serializar as etapas (custo de horas). Decisão: a Task 3 limita-se à função das linhas 144-161 e à docstring das linhas 10-14; a E06.3.5 mexe em contagens, em outras linhas; conflito, se houver, é resolvido no merge da etapa que fechar por último.
- Testador e desenvolvedor não commitam arquivos sob `.superpowers/`.

## Review Focus

1. Símbolo entre dois postes quase equidistantes: pendente (`nearby` e margem de 0,004), nunca o vizinho, também com o raio novo (Task 2).
2. Símbolo colado a um disco disputado: sem suporte (`(None, candidatos)`), e não migra para o vizinho que sobra dentro do raio (Task 2, R-E07.2.2.1-6).
3. Dois estais reais no mesmo poste: o legado de um, contido no modelo do outro, não funde errado; empate não funde; sobra sem par não some (Task 4).
4. Leitura de outra classe sobre o estai, ou dois modelos sobrepostos, não funde; `support_geometry` da haste é preservada e a geometria é a do modelo (Task 4).
5. Só legado (caso da ablação): a fusão nova não dispara e a ocorrência fica igual (Task 4). Com a opção desligada, `reconcile_symbols` nem é chamado; goldens iguais.

## Decisões do plano

- **R-E07.2.2.1-1, régua:** controle `baseline-v013` (símbolos tp 90, fp 65, fn 89; postes 58/11/49). A E06.3.5 muda `package_signature` e o runner: se ela entrar antes da medição final, o controle é refeito na `main` antes de medir.
- **R-E07.2.2.1-2, fusão do ESTAI (no reconciliador):**
  - **Par compatível:** um lado é o método do modelo (`perfil.metodo_id` igual à constante do id do método sobre o modelo, em `symbol_reconciliation.py`, com teste de paridade contra o perfil real) e o outro não é; `classe == "ESTAI"` nas duas observações, com alternativa única de classe; o centro da caixa do legado dentro da caixa do modelo; mesma fonte (`_source_key`).
  - **Emparelhamento em `_compose`, explícito**, para não depender da ordem por id: o compatível é a relação, e o emparelhamento decide. O laboratório escolhe entre H-1 (único nos dois sentidos) e H-2 (menor distância entre centros, com margem de 0,004; empate não funde). `_same_occurrence` não muda para as demais classes. Como `_compose` roda na ablação, ela herda a regra.
  - **ESTAI em dobro** na medição: par legado/modelo compatível e único que ficou sem fundir. Par que fica de fora por empate é contado à parte e vai ao handoff.
  - **Classe e subtipo:** o legado traz subtipo (`_MT`/`_AT`) e o modelo traz `None`. Em grupo fundido por este caminho, `identities` em `_occurrence` considera só a classe, e a ocorrência não recebe `ambiguous_class_or_id` por causa do subtipo; o subtipo do legado é preservado na ocorrência. As demais classes seguem como hoje.
  - **Geometria:** em grupo fundido por este caminho, `selected` é a observação do modelo (`by_quality` por número de primitivas não vale aqui); `support_geometry` segue a primeira não nula.
- **R-E07.2.2.1-3, teste que fixa "não fundem":** `tests/integration/test_model_symbols_estai_runner.py::test_estai_do_legado_e_do_modelo_nao_fundem` (`Soul: testador`, 4201c3d) fixa o desfecho anterior. Na Task 3, o testador o refaz antes do desenvolvedor, afirmando o desfecho em `composto.occurrences`, sem importar o privado `_same_occurrence` (o teste atual o importa).
- **R-E07.2.2.1-4, vínculos do poste pendente:** só as regras `CENTROS_PROXIMOS` usam o poste na posição do texto, onde a disputa do disco não importa, e as três têm destino POSTE. O pendente sai de `_sem_ancora` já na posição do texto e sem `poste_texto_centro`, por isso `_com_poste_no_texto` retira `associacao_pendente` quando o valor é `poste_disco` **antes** do teste do centro. O cabo segue cortado no poste pendente (E07.3). Efeito esperado: `estruturas_sem_poste` de 11 para 7 e `cabos_sem_vao` em 69; a pilha não fundida (leituras empilhadas que empatam na margem) pode ficar sem vínculo, e não com o vínculo errado: ela entra no teste e na medição.
- **R-E07.2.2.1-5, raio:** o raio de `_symbol_support` sai do laboratório (0,025 hoje). `simbolos` só chega com `symbol_runner` (`mvp_workflow.py:470-485`), criado só com a opção (`server/composition.py:472`), e por isso o raio novo vale só com ela ligada, sem parâmetro novo. A margem de 0,004 fica.
- **R-E07.2.2.1-6, sítio disputado:** `_sem_ancora` passa a gravar, no caminho ligado, `poste_disco_sitios` = `"x,y;x,y"` com os sítios em disputa do P pendente (o `_atribuir` expõe o par grupo→sítios). Em `_symbol_support`, o poste com pendência `poste_disco` deixa de ser candidato pela posição do texto; entra em `candidates` pela menor distância do centro do símbolo a um sítio dele. Se o mais próximo dentro do raio é pendente ou está empatado com pendente, a função devolve `(None, nearby)`, sem cair no vizinho, e os candidatos vão a `simbolo_suportes_candidatos`. Poste pendente sem sítio registrado sai da lista.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/interpretation/ficha_poste.py`, `tests/unit/test_interpretador_ficha_poste_regime.py` (novo), testes de versão (`tests/unit/test_interpretador_ficha_poste.py`, `tests/server/test_ficha_poste_composicao*`, `tests/integration/test_benchmark_runner_e07*`) | vínculos no regime de texto, versão 27.0 | 1 |
| `src/zeny_project_handler/application/interpretation_pipeline.py`, `src/zeny_project_handler/adapters/interpretation/ancoragem_poste.py`, `tests/unit/test_symbol_support_poste_pendente.py` (novo), `tests/unit/test_ancoragem_poste.py` | sítios em disputa, associação, raio, versão | 2 |
| `tests/integration/test_model_symbols_estai_runner.py` (só a função e a docstring citadas) | teste da fusão, testador | 3 |
| `src/zeny_project_handler/application/symbol_reconciliation.py`, `tests/unit/test_symbol_reconciliation_estai.py` (novo) | emparelhamento do ESTAI | 4 |
| `tests/integration/test_ficha_poste_cadeia_simbolos.py` (novo), `tests/fixtures/symbol_grammars/dois_postes.py` (novo) | cadeia, dois postes, promoção e regiões | 5 |

**Ondas:** laboratório e Task 1 em paralelo; depois Task 2 em um worktree e, em outro, Task 3 seguida da Task 4 (assim o vermelho da Task 3 não atinge a suíte da Task 2); depois Task 5; testador de etapa; medição do orquestrador. Soma: 30 + 45 + 15 + 45 + 40 = 2h55, mais o laboratório (60 min). Vale a regra de estouro de 4h30; o relógio começa em dda292a.

## Laboratório (depois da revisão do plano, em paralelo à Task 1)

- **Base:** a branch da etapa em worktree destacado por hipótese; cada `desenvolvedor` implementa e mede, sem commitar e sem a suíte inteira, com o `.venv` da etapa e `PYTHONPATH=<worktree>/src`, em cópia da rodada (`<checkout principal>/tmp/laboratorio/e07-2-2-1/<hipotese>/rodada/`, como na E07.2.1).
- **Hipóteses** (o eixo do raio é cruzado nas duas, com 3 valores):
  - **H-1:** emparelhamento único nos dois sentidos.
  - **H-2:** menor distância entre centros, com margem de 0,004; empate não funde.
- **Raios a cruzar:** centro a centro 0,025 e 0,030; distância do centro do poste à caixa do símbolo, 0,020.
- **Comando:** `python -m scripts.curation_ficha baseline --rodada <copia> --native-only --versao-extracao propostas-v2 --simbolos-modelo --processos 6`, comparando `fichas/baseline-vNNN-resumo.json` e `pdfs/*/ficha/baseline-vNNN/avaliacao.json` com a v013. `scripts.benchmark_simbolos_ficha` só guarda a detecção: não passa por `reconcile_symbols`.
- **Vitória:** símbolos tp ≥ 92, fn ≤ 87, fp ≤ 20 (precisão ≥ 82%), 0 símbolo em poste errado, 0 ESTAI em dobro; postes tp ≥ 58 e precisão ≥ 58/69, campos sem regressão; ablação do legado em ESTAI sem ocorrência perdida.
- **Parada:** 60 min por hipótese. Se nenhuma vencer, a etapa estaciona (D20), depois de cruzar a fusão com os raios.
- **Entrega:** em `<checkout principal>/tmp/laboratorio/e07-2-2-1/<hipotese>/`: `patch.diff`, `metricas.json`, `conclusoes.md`, com o raio e os ESTAI por empate declarados.

## Tasks

### Task 1: Vínculos do poste pendente no regime de texto

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** alto

**Files:** os da linha "1" da File Structure.

**Interfaces:** Consumes: `InterpretadorFichaPoste._gerar_relacoes` e `_com_poste_no_texto`. Produces: `versao = "27.0"`.

- [ ] **Step 1: Testes falhando,** com a fixture montada pela saída real de `ancorar_postes_no_desenho`: poste pendente por disputa com estrutura perto do texto → a relação `CENTROS_PROXIMOS` nasce; o mesmo poste, em regra que não é de texto, não recebe relação; `associacao_pendente` com outro valor continua sem relação no regime de texto; o poste original nas propostas segue com a pendência e a geometria; leituras empilhadas do P pendente empatando → sem relação, nunca relação errada. → FAIL.
- [ ] **Step 2:** implemente conforme R-E07.2.2.1-4, sem tocar `relation_rules.py`, e suba a versão; ajuste só as asserções de versão.
- [ ] **Step 3:** testes da área e goldens → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 2: Associação símbolo → poste

**Estimativa:** 45 min · **Depende de:** laboratório · **Risco:** alto · **Laboratório:** sim

**Files:** os da linha "2" da File Structure.

**Interfaces:** Consumes: o `patch.diff` da hipótese vencedora, sem a parte de fusão. Produces: `SYMBOL_SEMANTICS_VERSION = "e07-2-2-symbol-support-3"` e o atributo `poste_disco_sitios`.

- [ ] **Step 1: Testes falhando:** itens 1 e 2 do Review Focus; `_sem_ancora` grava os sítios só para P pendente por disputa; raio no limite (igual, logo acima); poste pendente sem sítio não é candidato. → FAIL.
- [ ] **Step 2:** implemente conforme R-E07.2.2.1-5 e R-E07.2.2.1-6.
- [ ] **Step 3:** testes da área e goldens → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 3: Teste da fusão (testador)

**Estimativa:** 15 min · **Depende de:** laboratório · **Risco:** alto · **Soul:** testador

**Files:** o da linha "3" da File Structure.

- [ ] **Step 1:** refaça a função e a docstring citadas em R-E07.2.2.1-7 para o novo desfecho (R-E07.2.2.1-3), afirmando em `composto.occurrences`, com commit próprio. O teste fica vermelho até a Task 4, no mesmo worktree.

### Task 4: Fusão do ESTAI

**Estimativa:** 45 min · **Depende de:** Task 3 · **Risco:** alto · **Laboratório:** sim

**Files:** os da linha "4" da File Structure.

**Interfaces:** Consumes: o `patch.diff` da vencedora, sem a parte de associação. Produces: o emparelhamento em `_compose`.

- [ ] **Step 1: Testes falhando:** itens 3, 4 e 5 do Review Focus; ablação sem o legado não perde a ocorrência; ATERRAMENTO e PARA_RAIOS_MT com a mesma contenção não fundem; ordem das observações não altera o resultado; a constante do método do modelo bate com o perfil real. → FAIL.
- [ ] **Step 2:** implemente conforme R-E07.2.2.1-2, sem afrouxar o caminho das demais classes.
- [ ] **Step 3:** testes da área, `tests/unit/test_symbol_reconciliation*`, o teste da Task 3 e goldens → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 5: Cadeia, dois postes, promoção e regiões

**Estimativa:** 40 min · **Depende de:** Tasks 1, 2, 4 · **Risco:** normal

**Files:** os da linha "5" da File Structure.

- [ ] **Step 1: Testes:** fixture sintética com dois postes próximos e símbolos entre eles (critério 1), com o `InterpretadorFichaPoste` e `reconcile_symbols`; a promoção e as regiões sobre as propostas com a opção ligada, incluindo o efeito de poste pendente com estrutura ligada em `analysis_regions.py`; estai em uma ocorrência; ablação.
- [ ] **Step 2:** o que falhar é defeito: relate, sem mudar código de produção fora do combinado.
- [ ] **Step 3: Commit**; suíte inteira uma vez antes do relatório.

## Operação do orquestrador (fora das tarefas)

- Medição final: `baseline` na rodada principal no HEAD integrado, comparada à v013 (R-E07.2.2.1-1), mais os dois `git diff --exit-code` dos goldens.
- Handoff: número novo da baseline, ESTAI em dobro = 0 (e os por empate à parte), `estruturas_sem_poste`, `cabos_sem_vao`, raio e limites para a E09.
