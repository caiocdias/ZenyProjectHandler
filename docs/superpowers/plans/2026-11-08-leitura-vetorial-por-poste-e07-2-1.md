# E07.2.1 — Posição do poste no desenho: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** com a opção ligada, o poste sai no disco do desenho, com uma proposta por identificador por folha, e as relações de estrutura e de cabo usam a posição nova.

**Architecture:** o interpretador padrão (`InterpretadorRegrasExplicitas`, 25.0) ganha um gancho sem efeito, e uma subclasse `InterpretadorFichaPoste` (26.0), escolhida só na composição do servidor com a opção ligada e no benchmark com `--simbolos-modelo`, sobrescreve o gancho. O gancho roda entre `filtrar_propostas_identificadas` e `associar_tracados_de_cabos`, e por isso cabos, deduplicação e relações já usam a posição nova. A ancoragem é função pura de `adapters/interpretation/`, sobre as evidências VETOR que já chegam ao interpretador.

**Tech Stack:** Python 3.11–3.13, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E07", "E07.2" e "E07.2.1"; D18; handoff da E07.1; levantamento em `tmp/janela-0.6.0/levantamento-e07-2.md`.

## Global Constraints

- Arquitetura hexagonal; a aplicação não importa `adapters/interpretation`.
- **D18:** com `ZENY_SERVER_SYMBOL_COMPOSITION=false`, a análise padrão não muda de saída nem de versão. O interpretador padrão continua `25.0`, e os goldens `tests/fixtures/golden_padrao_e07.json` e `golden_padrao_e07_complementar.json` não mudam (o complementar pode ganhar casos só na Task 1, antes de qualquer mudança em `src/`).
- Versão **26.0** só na subclasse, só com a opção ligada. `tests/integration/test_interpretation_pipeline.py:243` (25.0) continua válido.
- Sem migração, API ou DTO. A ficha não é entidade persistida nova; atributos novos ficam em `atributos_sugeridos`.
- Fixtures sintéticas autorais; nada de coordenada, hash ou nome de folha real. Nada lê `examples/avaliacao-cega/`.
- Não tocar em `src/zeny_project_handler/adapters/analysis/`, `symbol_execution.py`, `docs/fluxo-curadoria-incremental-simbologia.md`, nem nos arquivos de gramática e pacotes (E06.3.4, aberta em paralelo), nem `tests/conftest.py`.
- Testador e desenvolvedor não commitam arquivos sob `.superpowers/`.

## Review Focus

1. Dois postes próximos com rótulos entre eles: associa ao certo ou marca pendência, nunca ao vizinho errado (Task 3).
2. Disco de glifo no fim do rótulo (`11-300`) não vira poste (Task 3).
3. Par de discos do mesmo poste vira uma posição só (centro do par); duas leituras do mesmo P no mesmo disco viram uma proposta (Task 3).
4. Poste sem disco por perto mantém a posição do texto, com `associacao_pendente`, sem sumir (Task 3).
5. Opção desligada: interpretador 25.0, golden intacto, identidade da execução igual (Tasks 2 e 3).

## Decisões do plano

- **R-E07.2.1-1, gancho e subclasse:** em `rule_based.py`, método `_refinar_propostas_identificadas(self, propostas: tuple[PropostaElemento, ...], solicitacao: SolicitacaoInterpretacao) -> tuple[PropostaElemento, ...]` (no base, devolve `propostas`), chamado logo depois de `filtrar_propostas_identificadas` e antes de `associar_tracados_de_cabos`. `InterpretadorFichaPoste` (`versao = "26.0"`, novo arquivo `adapters/interpretation/ficha_poste.py`) o sobrescreve chamando `ancorar_postes_no_desenho`.
- **R-E07.2.1-2, escolha na composição:** `src/zeny_project_handler_server/composition.py:490` usa `InterpretadorFichaPoste(registry)` quando `settings.symbol_composition`, senão `InterpretadorRegrasExplicitas(registry)`. `run_variant` com `simbolos_modelo=True` usa o mesmo interpretador da opção ligada.
- **R-E07.2.1-3, ancoragem:** `ancorar_postes_no_desenho(propostas, evidencias) -> tuple[PropostaElemento, ...]` em `adapters/interpretation/ancoragem_poste.py`, função pura. Candidatos: `EvidenciaDocumento` de tipo VETOR com `operacoes="c,c,c,c"`, preenchidos, de cor da paleta do levantamento, diâmetro de pelo menos 0,9 pt e no máximo 7 pt, e não encostados em caixa de texto do rótulo (filtro de fragmento de glifo, definido pelo laboratório). A regra de atribuição vem do laboratório. Poste sem candidato continua na posição do texto, com `associacao_pendente="poste_disco"`. O poste ancorado recebe geometria CAIXA centrada no centro do par de discos, com lado do disco, e os atributos `poste_ancorado_disco=true` e `poste_texto_centro` para auditoria.
- **R-E07.2.1-4, derivações sem P:** ramo do laboratório: disco verde claro (0; 0,70; 0) sem proposta vira poste com `associacao_pendente="sem_rotulo_p"`, se o laboratório mostrar ganho sem FP novo. Sem ganho, ruling, e fica para a E07.3 ou a curadoria.
- **R-E07.2.1-5, gasto de CPU:** a etapa percorre as evidências VETOR uma vez por página; não usa as gramáticas nem o orçamento do modelo de desenho.
- **R-E07.2.1-6, critério:** vitória sobre a baseline v011 (`propostas-v2` com runner): postes tp maior que 43, precisão e recall maiores que os da v011 (52,4% e 40,2%), identificador, poste, coordenada e estruturas sem queda de taxa, e vãos tp sem queda.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `tests/integration/test_golden_padrao_e07_complementar.py`, `tests/fixtures/golden_padrao_e07_complementar.json` | casos novos | 1 |
| `src/zeny_project_handler/adapters/interpretation/rule_based.py` | gancho | 2 |
| `src/zeny_project_handler/adapters/interpretation/ficha_poste.py` (novo) | subclasse 26.0 | 2 |
| `src/zeny_project_handler_server/composition.py`, `scripts/benchmark_network_pdf.py` | escolha do interpretador | 2 |
| `tests/server/test_ficha_poste_composicao.py` (novo), `tests/unit/test_interpretador_ficha_poste.py` (novo) | seleção, versões, D18 | 2 |
| `src/zeny_project_handler/adapters/interpretation/ancoragem_poste.py` (novo) | ancoragem | 3 |
| `tests/unit/test_ancoragem_poste.py` (novo) | ancoragem | 3 |

**Ondas:** Task 1, depois {2}, depois laboratório sobre a Task 2, depois Task 3. Etapa em paralelo: E06.3.4, trilha B, com arquivos disjuntos. Soma: 30 + 30 + 45 = 1h45, mais laboratório (60 min).

## Laboratório (depois da Task 2)

- **Base:** a branch da etapa com a Task 2 integrada. Worktree destacado por hipótese, criado pelo orquestrador; cada `desenvolvedor` implementa em `ancoragem_poste.py` e mede, sem commitar e sem a suíte inteira.
- **Hipóteses** (duas, por haver outra etapa aberta):
  - **H-A, disco da paleta ancorado em P:** sítios de disco (par agrupado a 0,012) como posição; atribuição 1:1 entre P e sítios pela proximidade do rótulo; ligação de nomenclatura e estruturas ao disco; ramo das derivações sem P (R-4).
  - **H-B, conservadora:** mantém as propostas com P e move a geometria para o disco mais próximo até 0,04, com o filtro de glifo; funde as leituras do mesmo P no mesmo disco; não cria poste.
- **Comando:** cada hipótese usa cópia própria da rodada, para não cair na trava do baseline: copie `<checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas` para `tmp/laboratorio/e07-2-1/<hipotese>/rodada` e rode `python -m scripts.curation_ficha baseline --rodada <copia> --native-only --versao-extracao propostas-v2 --simbolos-modelo --processos 6`, com `PYTHONPATH=<worktree>/src` e o `.venv` da etapa.
- **Métrica:** postes tp/fp/fn e por família; taxas de identificador, poste, coordenada e estruturas; vãos; contagem de propostas por P duplicado; distância mediana do centro casado; regressões por folha contra a v011.
- **Vitória:** a R-E07.2.1-6. Empate: menos FP de poste, depois menos propostas pendentes.
- **Parada:** 60 min por hipótese, ou vitória com o tp acima de 80.
- **Entrega:** em `tmp/laboratorio/e07-2-1/<hipotese>/`: `patch.diff`, `metricas.json`, `conclusoes.md`.

## Tasks

### Task 1: Ampliar o golden complementar

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** normal

**Files:** `tests/integration/test_golden_padrao_e07_complementar.py`, `tests/fixtures/golden_padrao_e07_complementar.json`.

**Interfaces:** Consumes: os helpers do arquivo. O golden principal não muda.

- [ ] **Step 1:** acrescente ao caso sintético do complementar: polilinha de cabo com vértice intermediário; cabo com extremo perto de `_MAXIMUM_PATH_ENDPOINT_DISTANCE` (`span_rules.py:34`) em cada lado do limite; cabo com um extremo só; fusão de duplicata decidida por confiança; caso de `_local_context` com a tolerância 0,004. Gere o JSON uma vez, no `src/` atual, e confira à mão que os casos aparecem. Execute `pytest tests/integration/test_golden_padrao_e07*.py` em dois processos diferentes.
- [ ] **Step 2:** `git diff --exit-code -- tests/fixtures/golden_padrao_e07.json` (principal intacto).
- [ ] **Step 3:** mutação manual em `span_rules.py` e em `_deduplicate_point_proposals`, sem commit: o complementar precisa ficar vermelho; desfaça.
- [ ] **Step 4: Commit** com os testes da área; suíte inteira uma vez antes do relatório.

### Task 2: Gancho, subclasse e composição

**Estimativa:** 30 min · **Depende de:** 1 · **Risco:** alto

**Files:** `rule_based.py`, `ficha_poste.py` (novo), `composition.py`, `scripts/benchmark_network_pdf.py`, `tests/server/test_ficha_poste_composicao.py` (novo), `tests/unit/test_interpretador_ficha_poste.py` (novo).

**Interfaces:** Produces: `InterpretadorFichaPoste` (`nome` igual ao base, `versao = "26.0"`); `_refinar_propostas_identificadas`. A subclasse chama por ora `ancorar_postes_no_desenho` de `ancoragem_poste.py`, criada aqui como identidade (`return propostas`).

- [ ] **Step 1: Testes falhando:** o interpretador padrão continua `25.0`; `InterpretadorFichaPoste.versao == "26.0"`; `compose_server_runtime` com `symbol_composition=False` usa o padrão e com `True` usa a subclasse (`isinstance`, sem expor a API); o golden e o complementar passam com o padrão; `run_variant(..., simbolos_modelo=True)` executa o interpretador 26.0.
- [ ] **Step 2:** implemente o gancho, a subclasse com a identidade, e a escolha em `composition.py` e `run_variant`.
- [ ] **Step 3: Rode** os testes e os goldens → PASS; `git diff --exit-code` dos goldens.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 3: Ancoragem do poste

**Estimativa:** 45 min · **Depende de:** laboratório (sobre a Task 2) · **Risco:** alto · **Laboratório:** sim

**Files:** `ancoragem_poste.py`, `tests/unit/test_ancoragem_poste.py` (novo).

**Interfaces:** Produces: `ancorar_postes_no_desenho(propostas, evidencias)`, conforme R-E07.2.1-3 e o patch vencedor. Dados de fixture com evidências VETOR sintéticas (`operacoes="c,c,c,c"`).

- [ ] **Step 1: Testes** do Review Focus 1 a 4 e dos negativos: disco de fragmento de glifo, disco fora da paleta, disco grande, poste sem disco. Dois postes próximos com rótulos entre eles associam ao certo ou ficam pendentes, sem trocar. → FAIL.
- [ ] **Step 2: Implemente** a partir do patch vencedor, com as regras escolhidas no laboratório.
- [ ] **Step 3: Rode** os testes focados e o benchmark do laboratório, que precisa manter a vitória. → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

## Operação do orquestrador (fora das tarefas)

Medição final: `curation_ficha baseline --rodada <rodada> --native-only --versao-extracao propostas-v2 --simbolos-modelo --processos 8`, comparando com a v011 por folha. `git diff --exit-code f26cc3c -- tests/fixtures/golden_padrao_e07*.json`, com o complementar ampliado na Task 1 como exceção documentada. Testador de etapa (Task 1 é `normal`), `check_test_integrity --base <início>`, `osv-scanner`, revisão final e gate `cmd.exe //c ".\\IniciarTestes.bat"`.
