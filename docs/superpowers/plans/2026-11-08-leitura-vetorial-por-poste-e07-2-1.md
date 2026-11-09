# E07.2.1 — Posição do poste no desenho: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** com a opção ligada, o poste sai no disco do desenho, com uma proposta por disco, e as relações usam a posição certa para cada regime.

**Architecture:** o interpretador padrão (`InterpretadorRegrasExplicitas`, 25.0) ganha dois ganchos sem efeito: um antes de `associar_tracados_de_cabos` e outro no lugar de `generate_relations`. Uma subclasse `InterpretadorFichaPoste` (26.0), escolhida só na composição do servidor com a opção ligada e no benchmark com `--simbolos-modelo`, sobrescreve os dois. A posição do disco serve aos cabos; a posição do texto continua servindo às relações de estrutura e de equipamento, calibradas nela. A ancoragem é função pura de `adapters/interpretation/`, sobre as evidências VETOR que já chegam ao interpretador.

**Tech Stack:** Python 3.11–3.13, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E07", "E07.2" e "E07.2.1"; D18; handoff da E07.1; levantamento em `tmp/janela-0.6.0/levantamento-e07-2.md`.

## Global Constraints

- Arquitetura hexagonal; a aplicação não importa `adapters/interpretation`.
- **D18:** com `ZENY_SERVER_SYMBOL_COMPOSITION=false`, a análise padrão não muda de saída nem de versão. O interpretador padrão continua `25.0`. Prova: `tests/fixtures/golden_padrao_e07.json` idêntico a `f26cc3c`, e `golden_padrao_e07_complementar.json` idêntico ao commit da Task 1 (que é o único lugar em que o complementar muda).
- Versão **26.0** só na subclasse, só com a opção ligada. `tests/integration/test_interpretation_pipeline.py:243` (25.0) continua válido. `scripts/build_release.py:356` continua declarando a do caminho padrão, correto pela D17.
- Sem migração, API ou DTO. A ficha não é entidade persistida nova; atributos novos ficam em `atributos_sugeridos`, sem reusar chave existente sem conferir (`_normalize_extras` recusa duplicata, `domain/analysis.py:29`).
- `regras_interpretacao_v1.json` e `relation_rules.py` não mudam; mudança ali altera a identidade da análise padrão.
- Fixtures sintéticas autorais; nada de coordenada, hash ou nome de folha real. Nada lê `examples/avaliacao-cega/`.
- Não tocar em `src/zeny_project_handler/adapters/analysis/`, `symbol_execution.py`, `docs/fluxo-curadoria-incremental-simbologia.md`, nem nos arquivos de gramática e pacotes (E06.3.4, aberta em paralelo), nem `tests/conftest.py`.
- Testador e desenvolvedor não commitam arquivos sob `.superpowers/`.

## Review Focus

1. Dois postes próximos com rótulos entre eles: associa ao certo ou marca pendência, nunca ao vizinho errado (Task 4).
2. Disco de glifo no fim do rótulo (`11-300`) não vira poste (Task 4).
3. Par de discos do mesmo poste vira uma posição só; duas leituras do mesmo P no mesmo disco viram uma proposta, com a outra leitura preservada em atributo (Task 4).
4. Poste sem disco por perto mantém a posição do texto, seus vínculos e sua promoção; só ambiguidade real vira pendência (Task 4).
5. Opção desligada: interpretador 25.0, goldens intactos, identidade da execução igual (Tasks 2, 3, 4 e fechamento).

## Decisões do plano

- **R-E07.2.1-1, ganchos e subclasse:** em `rule_based.py`, dois métodos, com o caminho do base sem efeito:
  - `_refinar_propostas_identificadas(self, propostas: tuple[PropostaElemento, ...], solicitacao: SolicitacaoInterpretacao, diagnosticos: list[DiagnosticoAnalise]) -> tuple[PropostaElemento, ...]`, chamado com `project_request` logo depois de `filtrar_propostas_identificadas` e antes do teste de `maximo_propostas`, depois de `_raise_if_cancelled`;
  - `_gerar_relacoes(self, execucao_id, elementos, solicitacao) -> tuple[PropostaRelacao, ...]`, com o corpo atual de `generate_relations`.
  - `InterpretadorFichaPoste` (`versao = "26.0"`, novo `adapters/interpretation/ficha_poste.py`) sobrescreve os dois. Se a ancoragem levantar exceção, o gancho devolve as propostas originais e acrescenta um diagnóstico, no padrão de `_analyzer_diagnostic`.
- **R-E07.2.1-2, escolha na composição:** `src/zeny_project_handler_server/composition.py:490` usa `InterpretadorFichaPoste(registry)` quando `settings.symbol_composition`, senão `InterpretadorRegrasExplicitas(registry)`, importando direto de `adapters/interpretation/ficha_poste.py`. `run_variant` com `simbolos_modelo=True` usa o mesmo.
- **R-E07.2.1-3, ancoragem:** `ancorar_postes_no_desenho(propostas, evidencias) -> tuple[PropostaElemento, ...]` em `adapters/interpretation/ancoragem_poste.py`, função pura, que percorre as evidências uma vez por página.
  - **Candidatos:** `EvidenciaDocumento` VETOR, `operacoes="c,c,c,c"`, com preenchimento numa cor da paleta (cada componente a até 0,03 de: verde `#007000`, verde claro `#00B300`, verde `#008000`, roxo `#4F1A4D`, vermelho `#FF0000`, preto `#000000`), razão de aspecto entre 0,85 e 1,15 e diâmetro de 0,9 a 7 pt, medido nos pontos em unidades de PDF do `conteudo_bruto` (`pymupdf_page_extractors.py:108`), e **não** encostados na caixa de um texto de rótulo (filtro de glifo, definido no laboratório). Os limiares vieram do modelo de desenho, e o laboratório os confirma sobre VETOR.
  - **Sem candidato:** o poste mantém posição e vínculos, com `poste_ancorado_disco=false` e sem `associacao_pendente`.
  - **Ambiguidade real**, medida em sítios depois do agrupamento do par (dois P disputam um sítio, ou o rótulo fica entre dois sítios a menos de 0,004 de diferença): o poste fica na posição do texto, com `associacao_pendente="poste_disco"`, só se o atributo não existir.
  - **Poste ancorado:** geometria CAIXA no centro do par de discos (par agrupado a 0,012), de lado igual ao diâmetro; atributos `poste_ancorado_disco=true` e `poste_texto_centro` (string `"x,y"`); os ids dos discos em `evidencia_ids`, para a proveniência.
  - **Uma proposta por disco:** duas leituras do mesmo P no mesmo disco viram uma. O sobrevivente vem de um sinal real avaliado no laboratório (`situacao_projeto`; marca de risco sobre o rótulo, no padrão de `_supersession_marker`). Se nada decidir, vale o padrão de leitura sem resolução de `category_analyzers.py:721-731`: sobrevive a de maior confiança, com desempate pelo menor id de proposta, mas com `estado_revisao=CONFLITANTE`, `tipo_catalogo_sugerido_id=None` e `classificacao_pendente=True`; a outra leitura vai a `poste_codigo_alternativo`, sem afirmar retirada e sem `associacao_pendente` (para não cortar vínculos). Os `evidencia_ids` se somam. O mesmo P em discos diferentes fica como duas propostas com `associacao_pendente="poste_mesmo_identificador"`, porque aí a ambiguidade é de associação.
- **R-E07.2.1-4, relações por regime:** `_gerar_relacoes` da subclasse gera `INSTALADA_EM` e `INSTALADO_EM` (`CENTROS_PROXIMOS`) com o poste na posição do texto (`poste_texto_centro`, reconstruída em cópia temporária das propostas), porque o raio de 0,10 foi calibrado em texto contra texto, e as demais (`CONECTA` etc.) com o poste no disco. Os ids das relações seguem determinísticos e independentes da geometria. A ancoragem vem antes de `associar_tracados_de_cabos`, para `_nearest_endpoint_pole` já ver o disco.
- **R-E07.2.1-5, derivações sem P:** ficam fora desta etapa (poste criado só por disco foge ao ADR 0006 e o escopo regional do avaliador não controla os FP). Ruling; vão à E07.3 ou à curadoria.
- **R-E07.2.1-6, critério:** contra a baseline v011 (`propostas-v2` com runner): postes tp maior que 43 e precisão e recall maiores (52,4% e 40,2%); acertos absolutos de identificador, poste, coordenada e estruturas sem queda; taxa desses campos sem queda no subconjunto dos 43 casados na v011 (casos novos à parte); vãos tp sem queda; `erros_sem_pendencia` = 0 nos campos identificador, poste e coordenada dos postes novos (leitura errada afirmada), e no campo estruturas com taxa de erro sem pendência dos novos não maior que a da v011 (7/43), porque esse campo vem do vínculo que R-4 mantém; nenhum disco com dois P distintos afirmados; `estruturas_sem_poste` e `cabos_sem_vao` sem aumentar; símbolos medidos e registrados, sem exigir melhora aqui.
- **Alternativas descartadas** (levantamento): etapa depois de `_symbol_proposals`, porque não refaz `INSTALADA_EM` nem `CONECTA`; observação nova de POSTE no runner, porque o disco já chega às evidências VETOR; gramática POSTE, que cobriria mal as 31 variantes.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `tests/integration/test_golden_padrao_e07_complementar.py`, `tests/fixtures/golden_padrao_e07_complementar.json` | casos novos | 1 |
| `src/zeny_project_handler/adapters/interpretation/rule_based.py` | ganchos | 2 |
| `src/zeny_project_handler/adapters/interpretation/ficha_poste.py` (novo) | subclasse 26.0 | 2 |
| `src/zeny_project_handler/adapters/interpretation/ancoragem_poste.py` (novo, identidade) | ancoragem | 2, 4 |
| `tests/unit/test_interpretador_ficha_poste.py` (novo) | ganchos, versões, D18 | 2 |
| `src/zeny_project_handler_server/composition.py`, `scripts/benchmark_network_pdf.py` | escolha do interpretador | 3 |
| `tests/server/test_ficha_poste_composicao.py` (novo) | seleção | 3 |
| `src/zeny_project_handler/adapters/interpretation/ficha_poste.py`, `ancoragem_poste.py`, `tests/unit/test_ancoragem_poste.py` (novo) | ancoragem e relações por regime | 4 |
| `tests/integration/test_ficha_poste_cadeia.py` (novo) | cadeia com a subclasse: relações, promoção, região | 5 |

**Ondas:** Task 1; Task 2; depois {3}; laboratório sobre a Task 3; Task 4; Task 5. Soma: 30 + 25 + 20 + 45 + 25 = 2h25, mais o laboratório (60 min). Etapa em paralelo: E06.3.4, trilha B, com arquivos disjuntos.

## Laboratório (depois da Task 3)

- **Base:** a branch da etapa com a Task 3 integrada. Worktree destacado por hipótese, criado pelo orquestrador; cada `desenvolvedor` implementa, sem commitar e sem a suíte inteira, e reproduz sobre VETOR a contagem de candidatos do levantamento (87/107 a ≤ 0,005 no modelo de desenho).
- **Hipóteses** (duas, por haver outra etapa aberta):
  - **H-A, atribuição 1:1:** sítios de disco como posição; P atribuído ao sítio mais próximo com exclusão mútua; as duas hipóteses aplicam R-E07.2.1-4, com as estruturas vinculadas pela posição do texto.
  - **H-B, conservadora:** mantém as propostas com P e move a geometria para o disco mais próximo até um raio escolhido no laboratório (0,04 é o ponto de partida; a mediana nomenclatura–poste é 0,040 e na família iText é 0,060), com o filtro de glifo; funde as leituras do mesmo P no mesmo disco.
- **Comando:** cada hipótese usa cópia própria da rodada, para não cair na trava do baseline: copie `<checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas` para `<checkout principal>/tmp/laboratorio/e07-2-1/<hipotese>/rodada` e rode `python -m scripts.curation_ficha baseline --rodada <copia> --native-only --versao-extracao propostas-v2 --simbolos-modelo --processos 6`, com `PYTHONPATH=<worktree>/src` e o `.venv` da etapa.
- **Métrica:** a da R-E07.2.1-6, mais postes por família; "mesmo P em mais de uma região por folha" (`agrupar_regioes_da_analise`, limite de 0,10, derruba a `ENTREGA`); propostas por P duplicado; distância mediana do centro casado; `estruturas_sem_poste`, `cabos_sem_vao`, relações por tipo e por folha contra a v011; símbolos tp/fp/fn; postes pendentes; regressões por folha.
- **Vitória:** a R-E07.2.1-6, com leitura errada afirmada = 0. Empate: menos FP de poste, depois menos postes pendentes.
- **Parada:** 60 min por hipótese. Se nenhuma vencer, a etapa estaciona (D20).
- **Entrega:** em `<checkout principal>/tmp/laboratorio/e07-2-1/<hipotese>/`: `patch.diff`, `metricas.json`, `conclusoes.md`.

## Resultado do laboratório (2026-11-08)

Laboratório em `tmp/laboratorio/e07-2-1/` do checkout principal, com base em 527bdd4. Controle: `baseline-v011` (postes 43/39/64).

| hipótese | postes tp/fp/fn | precisão / recall | vãos tp/fp/fn | símbolos tp/fp/fn | mesmo P em mais de uma região |
|---|---|---|---|---|---|
| **H-A, escolhida** | 59/10/48 | 85,5% / 55,1% | 28/3/55 | 33/62/146 | 2 (v011: 1) |
| H-B | 56/13/51 | 81,2% / 52,3% | 26/5/57 | 32/57/147 | 1 |

- As duas cumprem a R-E07.2.1-6: acertos absolutos de identificador, poste, coordenada e estruturas sem queda, taxa sem queda na coorte dos 43 casados na v011, vãos tp sem queda, `estruturas_sem_poste` e `cabos_sem_vao` sem aumentar, leitura errada afirmada 0, nenhum disco com dois P afirmados.
- **H-A escolhida** por mais postes e menos FP de poste. Custa um "mesmo P em mais de uma região" a mais (015 P1, uma estrutura isolada), que vai ao handoff e à E07.3. O empate previsto no plano não ocorreu.
- **Sinal das pilhas de leitura:** `situacao_projeto` (REMOVER contra INSTALAR) decide as 8 pilhas medidas, sem precisar de marca de risco.
- **Desvios da R-E07.2.1-3, adotados como rulings:** origem da atribuição é o centro do rótulo P (`evidencia_identificador_id`), não a nomenclatura, porque a nomenclatura trocava o disco de um P não lido vizinho (5 casos); par de discos a 0,013; raio de atribuição 0,14; roxo só a até 0,04 do rótulo. Leitura distante do mesmo rótulo P fica como proposta sem pendência, porque fundir subia `estruturas_sem_poste` de 7 para 18. Limiares calibrados nas 16 folhas: a E09 mede o sobreajuste.
- **Filtro de glifo** removeu 0 de 262 candidatos, porque o FP do levantamento veio do modelo de desenho e não aparece como `c,c,c,c` nas evidências VETOR. Fica como salvaguarda do Review Focus 2.
- **Candidatos sobre VETOR:** 90/107 a até 0,005 (levantamento: 87).

## Tasks

### Task 1: Ampliar o golden complementar

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** normal

**Files:** `tests/integration/test_golden_padrao_e07_complementar.py`, `tests/fixtures/golden_padrao_e07_complementar.json`.

**Interfaces:** Consumes: os helpers do arquivo. O golden principal não muda.

- [ ] **Step 1:** acrescente ao caso sintético do complementar: polilinha de cabo com vértice intermediário; cabo com extremo perto de `_MAXIMUM_PATH_ENDPOINT_DISTANCE` (`span_rules.py:34`), em cada lado do limite; cabo com um extremo só; fusão de duplicata decidida por confiança; caso de `_local_context` com a tolerância de 0,004. Gere o JSON uma vez, no `src/` atual, e confira à mão que os casos aparecem. Rode `pytest tests/integration/test_golden_padrao_e07*.py` em dois processos diferentes.
- [ ] **Step 2:** `git diff --exit-code f26cc3c -- tests/fixtures/golden_padrao_e07.json`.
- [ ] **Step 3:** mutação manual em `span_rules.py` e em `_deduplicate_point_proposals`, sem commit: o complementar fica vermelho; desfaça.
- [ ] **Step 4: Commit** com os testes da área; suíte inteira uma vez antes do relatório.

### Task 2: Ganchos e subclasse

**Estimativa:** 25 min · **Depende de:** 1 · **Risco:** alto

**Files:** `rule_based.py`, `ficha_poste.py` (novo), `ancoragem_poste.py` (novo, com a função como identidade), `tests/unit/test_interpretador_ficha_poste.py` (novo).

**Interfaces:** Produces: `InterpretadorFichaPoste` (`nome` igual ao do base, `versao = "26.0"`) e os dois ganchos de R-E07.2.1-1. `ancorar_postes_no_desenho` devolve `propostas`. A subclasse trata exceção da ancoragem como diagnóstico, com teste.

- [ ] **Step 1: Testes falhando:** o padrão continua `25.0`; `InterpretadorFichaPoste.versao == "26.0"`; os dois goldens passam com o padrão; ancoragem que levanta exceção vira diagnóstico, sem derrubar a interpretação.
- [ ] **Step 2:** implemente os ganchos no base, sem nenhuma mudança de comportamento, e a subclasse.
- [ ] **Step 3:** testes e goldens → PASS; `git diff --exit-code f26cc3c -- tests/fixtures/golden_padrao_e07.json`.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 3: Escolha na composição e no benchmark

**Estimativa:** 20 min · **Depende de:** 2 · **Risco:** alto

**Files:** `composition.py`, `scripts/benchmark_network_pdf.py`, `tests/server/test_ficha_poste_composicao.py` (novo).

**Interfaces:** Consumes: `InterpretadorFichaPoste`.

- [ ] **Step 1: Testes falhando:** `compose_server_runtime` com `symbol_composition=False` usa o padrão (versão 25.0, sem a chave na identidade) e com `True` usa a subclasse; `run_variant(..., simbolos_modelo=True)` executa o interpretador 26.0.
- [ ] **Step 2:** implemente conforme R-E07.2.1-2.
- [ ] **Step 3:** testes e goldens → PASS.
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 4: Ancoragem e relações por regime

**Estimativa:** 45 min · **Depende de:** laboratório (sobre a Task 3) · **Risco:** alto · **Laboratório:** sim

**Files:** `ancoragem_poste.py`, `ficha_poste.py`, `tests/unit/test_ancoragem_poste.py` (novo).

**Interfaces:** Produces: `ancorar_postes_no_desenho(propostas, evidencias)` conforme R-E07.2.1-3 e o patch vencedor; `_gerar_relacoes` conforme R-E07.2.1-4. Dados de fixture com evidências VETOR sintéticas (`operacoes="c,c,c,c"`).

- [ ] **Step 1: Testes** dos itens 1 a 4 do Review Focus; caso que discrimina os regimes: disco a mais de 0,10 da estrutura e a menos de 0,10 do texto, com `INSTALADA_EM` mantida; negativos (disco de fragmento de glifo, fora da paleta, grande, não redondo); poste sem disco mantém vínculos e posição, sem `associacao_pendente`; página hostil com muitos discos e rótulos sem laço quadrático fora de teto; `associacao_pendente` preexistente não é sobrescrita. → FAIL.
- [ ] **Step 2: Implemente** a partir do patch vencedor.
- [ ] **Step 3:** testes focados e goldens → PASS; repita o benchmark do laboratório (vitória mantida).
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 5: Cadeia com a subclasse

**Estimativa:** 25 min · **Depende de:** 4 · **Risco:** alto

**Files:** `tests/integration/test_ficha_poste_cadeia.py` (novo).

**Interfaces:** Consumes: `InterpretadorFichaPoste`, `ExecutarPipelineInterpretacao`, a promoção e as regiões.

- [ ] **Step 1: Testes:** caso sintético com P, nomenclatura, estrutura, polilinha da rede e disco: `INSTALADA_EM`, `CONECTA`, promoção e região única com rótulo P; caso com o centro do disco a mais de 0,10 do centro da estrutura e folga de caixa de até 0,10 (regimes separados e região única; folga maior é limite conhecido, medido pela métrica do laboratório e registrado no handoff); caso com poste sem disco: mantém vínculos, promoção e região; ambiguidade de disco fica pendente e sem relação errada.
- [ ] **Step 2:** rode e ajuste o caso até refletir o comportamento esperado; se a cadeia falhar, é defeito da Task 4 (volta como rodada).
- [ ] **Step 3: Commit**; suíte inteira uma vez antes do relatório.

## Operação do orquestrador (fora das tarefas)

Medição final: `curation_ficha baseline --rodada <rodada> --native-only --versao-extracao propostas-v2 --simbolos-modelo --processos 8`, comparando com a v011 por folha. Pacote de revisão com `git diff --exit-code f26cc3c -- tests/fixtures/golden_padrao_e07.json` e `git diff --exit-code <commit da Task 1> -- tests/fixtures/golden_padrao_e07_complementar.json`, nas Tasks 2 a 5 e no fechamento. O handoff registra o commit da Task 1 como nova base do complementar para a E07.2.2 e a E07.3, a ruling de que a redação do Objetivo do roadmap ("uma proposta por identificador por folha", relações na posição nova) cedeu a uma proposta por disco e a dois regimes de relação, e o destino das derivações sem P, que entram no escopo da E07.3. Testador de etapa (Task 1 é `normal`), `check_test_integrity --base <início>`, `osv-scanner`, revisão final e gate `cmd.exe //c ".\\IniciarTestes.bat"`.

## Revisão de arquitetura

- Veredito: aprovado com notas.
- Rodadas: 2.
- Modelo: opus.
- Notas Menores (aplicadas): padrão de leitura sem resolução no fallback do sobrevivente; fixture de folga de caixa definida; "mesmo P em mais de uma região" medido e registrado no handoff.
- Ponto mais provável de parada: o sinal que distingue poste certo e poste a retirar nas 7 pilhas. Sem ele, o critério da R-E07.2.1-6 reprova, e a etapa estaciona (D20).
