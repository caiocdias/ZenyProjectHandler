# E07.2.2.1 — Símbolos no poste certo e ESTAI sem duplicar: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** com a opção ligada, cada símbolo entra no poste certo ou fica pendente, o ESTAI sai em uma ocorrência só, e o poste pendente por disputa não perde as ligações que não dependem do disco.

**Architecture:** três mudanças disjuntas, só com a opção ligada: `_symbol_support` em `application/interpretation_pipeline.py` (associação), `_same_occurrence` em `application/symbol_reconciliation.py` (fusão do ESTAI) e `_com_poste_no_texto` em `adapters/interpretation/ficha_poste.py` (regime de texto). Laboratório decide o raio e a forma da fusão.

**Tech Stack:** Python 3.11, pytest, baseline `scripts.curation_ficha`.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E07.2.2.1". Levantamento: `<checkout principal>/tmp/janela-0.6.0/levantamento-e07-2-2.md` (fora do Git). Base: `dda292a`.

## Global Constraints

- Arquitetura hexagonal; `application/` não importa adaptadores.
- Nenhuma migração, API ou DTO. O método sobre o modelo liga só no runner opt-in (D12). Com `ZENY_SERVER_SYMBOL_COMPOSITION=false`, a saída não muda: `git diff --exit-code f26cc3c -- tests/fixtures/golden_padrao_e07.json` e `git diff --exit-code 877aba1 -- tests/fixtures/golden_padrao_e07_complementar.json` saem 0.
- Ao mudar comportamento de saída, incremente a versão: `InterpretadorFichaPoste.versao` de `26.0` para `27.0` (Task 1); `SYMBOL_SEMANTICS_VERSION` para `e07-2-2-symbol-support-3` (Task 2).
- Sem dependência nova. Fixtures sintéticas autorais; nenhuma coordenada, hash ou nome de folha real. Nada lê `examples/avaliacao-cega/`.
- Não tocar nos arquivos da E06.3.5, aberta em paralelo: `drawing_model/grammar_disc*.py`, `grammar_disc_mark.py`, `drawing_model/symbol_matcher.py`, `declarative_symbols.py`, `model_symbols.py`, `symbol_packages/family-f02-20.json`, `src/zeny_project_handler_server/symbol_execution.py`, `docs/schemas/pacotes-simbologia.schema.json`, `tests/fixtures/symbol_grammars/disc_mark.py`, `tests/unit/test_grammar_disc*`, `tests/unit/test_gramatica_disc_mark*`. `tests/integration/test_model_symbols_estai_runner.py` é tocado pelas duas (versão 1.6.0 na E06.3.5; a fusão aqui): conflito resolvido no merge da que fechar por último.
- Testador e desenvolvedor não commitam arquivos sob `.superpowers/`.

## Review Focus

1. Símbolo entre dois postes quase equidistantes: pendente (`nearby` e margem de 0,004), nunca o vizinho, também com o raio novo (Task 2).
2. Poste com `associacao_pendente="poste_disco"` não é candidato pela posição do texto; símbolo colado ao disco disputado fica sem suporte, com os candidatos registrados, e não migra para o vizinho (Task 2).
3. Dois estais reais no mesmo poste: o legado de um, contido no modelo do outro, não funde errado; contenção é 1 para 1, e sobra sem par não some (Task 3).
4. Leitura de outra classe sobre o estai, ou legado com classe ambígua, não funde; ESTAI do modelo sozinho e legado sozinho seguem como hoje; `support_geometry` da haste é preservada e a geometria é a do modelo (Task 3).
5. Opção desligada: o reconciliador recebe só o legado, e a fusão nova não dispara (Tasks 2 e 3); goldens iguais.

## Decisões do plano

- **R-E07.2.2.1-1, régua:** controle `baseline-v013` (símbolos tp 90, fp 65, fn 89; postes 58/11/49). A E06.3.5 muda `package_signature` e o runner: se ela entrar antes da medição final, o controle é refeito na `main` antes de medir.
- **R-E07.2.2.1-2, fusão do ESTAI:** o laboratório escolhe entre H-1 (fusão por contenção em `_same_occurrence`, antes do corte de primitivas) e H-2 (supressão no consumidor com ablação ciente). Preferência: H-1, porque a ablação sai limpa sem código adicional (R-E06.3.4-6). Em qualquer das duas: só `ESTAI` dos dois lados, centro do legado dentro da caixa do modelo, emparelhamento 1 para 1 e classe única; demais classes intactas.
- **R-E07.2.2.1-3, teste que fixa "não fundem":** `tests/integration/test_model_symbols_estai_runner.py::test_estai_do_legado_e_do_modelo_nao_fundem` (`Soul: testador`, 4201c3d) fixa o desfecho anterior, e a mudança dele é prevista por esta decisão. Na Task 3, o orquestrador despacha o **testador** antes do desenvolvedor para refazê-lo no novo desfecho (vermelho até a Task 3); o desenvolvedor não toca nele.
- **R-E07.2.2.1-4, vínculos do poste pendente:** só as regras `CENTROS_PROXIMOS` usam o poste na posição do texto, onde a disputa do disco não importa; nelas, `_com_poste_no_texto` retira `associacao_pendente` quando o valor é `poste_disco`. O cabo segue cortado no poste pendente (E07.3). Efeito esperado: `estruturas_sem_poste` volta de 11 para 7; `cabos_sem_vao` fica em 69.
- **R-E07.2.2.1-5, raio:** o raio de `_symbol_support` sai do laboratório (0,025 hoje; 0,030 na H-1; caixa→poste 0,020 na H-2). A margem de 0,004 fica. Fica com a opção ligada: o raio é parâmetro decidido pelo chamador conforme o interpretador, ou o código confirma, com teste, que o caminho só roda com observações do modelo.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/interpretation/ficha_poste.py`, `tests/unit/test_interpretador_ficha_poste_regime.py` (novo), testes de versão (`tests/server/test_ficha_poste_composicao*`, `tests/integration/test_benchmark_runner_e07*`) | vínculos no regime de texto, versão 27.0 | 1 |
| `src/zeny_project_handler/application/interpretation_pipeline.py`, `tests/unit/test_symbol_support_poste_pendente.py` (novo) | associação, poste pendente fora, raio, versão | 2 |
| `src/zeny_project_handler/application/symbol_reconciliation.py`, `tests/unit/test_symbol_reconciliation_estai.py` (novo), `tests/integration/test_model_symbols_estai_runner.py` (testador) | fusão do ESTAI | 3 |
| `tests/integration/test_ficha_poste_cadeia_simbolos.py` (novo), `tests/fixtures/symbol_grammars/dois_postes.py` (novo) | cadeia, dois postes, promoção e regiões | 4 |

**Ondas:** laboratório e Task 1 em paralelo; depois Tasks 2 e 3 em paralelo (arquivos disjuntos); depois Task 4; testador de etapa; medição do orquestrador. Soma: 30 + 45 + 60 + 40 = 2h55, mais o laboratório (60 min, em paralelo à Task 1). Vale a regra de estouro de 4h30; o relógio começa em dda292a.

## Laboratório (depois da revisão do plano, em paralelo à Task 1)

- **Base:** a branch da etapa em worktree destacado por hipótese; cada `desenvolvedor` implementa e mede, sem commitar e sem a suíte inteira, com o `.venv` da etapa e `PYTHONPATH=<worktree>/src`, em cópia da rodada (`<checkout principal>/tmp/laboratorio/e07-2-2-1/<hipotese>/rodada/`, como na E07.2.1).
- **Hipóteses:**
  - **H-1:** fusão por contenção em `_same_occurrence` e raio 0,030 centro a centro.
  - **H-2:** supressão do legado contido no consumidor, com a ablação descontando o contido, e distância do centro do poste à caixa do símbolo com raio 0,020.
- **Comando:** `python -m scripts.curation_ficha baseline --rodada <copia> --native-only --versao-extracao propostas-v2 --simbolos-modelo --processos 6`, comparando `fichas/baseline-vNNN-resumo.json` e `pdfs/*/ficha/baseline-vNNN/avaliacao.json` com a v013. `scripts.benchmark_simbolos_ficha` só guarda a detecção: não passa por `reconcile_symbols`.
- **Vitória:** símbolos tp ≥ 92, fn ≤ 87, fp ≤ 20 (precisão ≥ 82%), 0 símbolo em poste errado, 0 ESTAI em dobro; postes tp ≥ 58 e precisão ≥ 58/69, campos sem regressão; ablação do legado em ESTAI sem ocorrência perdida.
- **Parada:** 60 min por hipótese. Se nenhuma vencer, a etapa estaciona (D20).
- **Entrega:** em `<checkout principal>/tmp/laboratorio/e07-2-2-1/<hipotese>/`: `patch.diff`, `metricas.json`, `conclusoes.md`.

## Tasks

### Task 1: Vínculos do poste pendente no regime de texto

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** alto

**Files:** os da linha "1" da File Structure.

**Interfaces:** Consumes: `InterpretadorFichaPoste._gerar_relacoes` e `_com_poste_no_texto`. Produces: `versao = "27.0"`.

- [ ] **Step 1: Testes falhando:** poste com `associacao_pendente="poste_disco"` e `poste_texto_centro`, com estrutura perto do texto: a relação `CENTROS_PROXIMOS` nasce; o mesmo poste, em regra que não é de texto, não recebe relação; `associacao_pendente` com outro valor continua sem relação no regime de texto; o poste original nas propostas segue com a pendência e a geometria. → FAIL.
- [ ] **Step 2:** implemente conforme R-E07.2.2.1-4, sem tocar `relation_rules.py`, e suba a versão; ajuste só as asserções de versão.
- [ ] **Step 3:** testes da área e goldens → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 2: Associação símbolo → poste

**Estimativa:** 45 min · **Depende de:** laboratório · **Risco:** alto · **Laboratório:** sim

**Files:** os da linha "2" da File Structure.

**Interfaces:** Consumes: o `patch.diff` da hipótese vencedora, sem a parte de fusão. Produces: `SYMBOL_SEMANTICS_VERSION = "e07-2-2-symbol-support-3"`.

- [ ] **Step 1: Testes falhando:** itens 1 e 2 do Review Focus; raio no limite (igual, logo acima); opção desligada igual (R-E07.2.2.1-5). → FAIL.
- [ ] **Step 2:** implemente, tirando de `candidates` o poste com `associacao_pendente="poste_disco"`.
- [ ] **Step 3:** testes da área e goldens → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 3: Fusão do ESTAI

**Estimativa:** 60 min · **Depende de:** laboratório · **Risco:** alto · **Laboratório:** sim

**Files:** os da linha "3" da File Structure.

**Interfaces:** Consumes: o `patch.diff` da vencedora, sem a parte de associação. Produces: o predicado de fusão em `symbol_reconciliation.py`.

- [ ] **Step 0 (testador, antes do desenvolvedor):** refaça `test_estai_do_legado_e_do_modelo_nao_fundem` para o novo desfecho (R-E07.2.2.1-3), com commit próprio.
- [ ] **Step 1: Testes falhando:** itens 3, 4 e 5 do Review Focus; ablação sem o legado não perde a ocorrência; classes diferentes de ESTAI com a mesma contenção não fundem (ATERRAMENTO, PARA_RAIOS_MT). → FAIL.
- [ ] **Step 2:** implemente conforme R-E07.2.2.1-2, sem afrouxar o caminho das demais classes.
- [ ] **Step 3:** testes da área, `tests/unit/test_symbol_reconciliation*` e goldens → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 4: Cadeia, dois postes, promoção e regiões

**Estimativa:** 40 min · **Depende de:** Tasks 1, 2, 3 · **Risco:** normal

**Files:** os da linha "4" da File Structure.

- [ ] **Step 1: Testes:** fixture sintética com dois postes próximos e símbolos entre eles (critério 1), com o `InterpretadorFichaPoste` e `reconcile_symbols`; a promoção e as regiões sobre as propostas com a opção ligada; estai em uma ocorrência; poste pendente com a estrutura ligada.
- [ ] **Step 2:** o que falhar é defeito: relate, sem mudar código de produção fora do combinado.
- [ ] **Step 3: Commit**; suíte inteira uma vez antes do relatório.

## Operação do orquestrador (fora das tarefas)

- Medição final: `baseline` na rodada principal no HEAD integrado, comparada à v013 (R-E07.2.2.1-1), mais os dois `git diff --exit-code` dos goldens.
- Handoff: número novo da baseline, ESTAI em dobro = 0, `estruturas_sem_poste`, `cabos_sem_vao`, limites de raio para a E09.
