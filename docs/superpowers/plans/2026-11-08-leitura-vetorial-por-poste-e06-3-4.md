# E06.3.4 — Estai: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reconhecer ESTAI (haste com garfo, com ou sem envolvente e X de retirada) sobre o modelo de desenho, sem afirmar forma que a ficha não mostra.

**Architecture:** segue a haste, o BT e o transformador:
- tipo só do modelo `forked_stem`, executado só por `declarative-drawing-model` no runner opt-in;
- gramática em `drawing_model/grammar_estai.py`, usando as marcas de `grammar_marcas.py` (envolvente, X, cor canônica, sinal da página), sem mexer nelas;
- as 3 variantes habilitadas têm gramáticas distintas, e por isso nenhuma observação é agrupada nesta etapa.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só adaptadores, scripts e fixtures), JSON + JSON Schema, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3" e "E06.3.4", D15, D19, handoff da E06.3.3.2.2 ("Para a E06.3.4"), plano `2026-11-08-leitura-vetorial-por-poste-e06-3-3-2-2.md` como modelo, ADR 0006 e 0016. Levantamento técnico: `.superpowers/sdd/2026-11-08-leitura-vetorial-por-poste-e06-3-4/levantamento-e06-3-4.md` do worktree da trilha B.

## Global Constraints

- Arquitetura hexagonal: o núcleo `drawing_model/` não importa PyMuPDF; o cliente não importa nada do servidor.
- Nenhuma migração, API ou DTO. O método sobre o modelo liga só no runner opt-in (D12). O analisador padrão, o motor antigo e o legado não mudam, e `ZENY_SERVER_SYMBOL_COMPOSITION=false` continua sem efeito sobre a saída da análise. A tabela de suporte da revisão e a exportação, que leem os pacotes incondicionalmente, passam a contar as variantes habilitadas (decisão registrada desde a E06.3.1) e vão a "Decisões para o usuário".
- ADR 0006: `declarative-drawing-model` passa de 1.4.0 a 1.5.0 no commit da habilitação (Task 3). O motor antigo não executa tipo só do modelo.
- Sem dependência nova.
- Fixtures sintéticas autorais, positivas e negativas. Nenhuma coordenada, hash ou nome de folha real em código, pacote, fixture ou teste; a guarda de fonte (`_GRAMATICAS_NOVAS`) cobre os arquivos novos.
- Nada lê `examples/avaliacao-cega/`. As referências da rodada E03 estão congeladas. Leitores visuais não participam.
- Pytest com `--strict-markers` e `ResourceWarning` como erro; testes sem dependência de ordem, cwd, porta ou arquivo fixo. mypy strict, ruff e format. Complexidade abaixo de 31.
- Não tocar `scripts/benchmark_ficha_poste.py`, `scripts/benchmark_network_pdf.py`, `scripts/curation_ficha.py`, `scripts/ficha_predita_propostas.py`, `docs/fluxo-curadoria-incremental-simbologia.md` nem `examples/README.md` (arquivos da E07.1, aberta em paralelo), nem `tests/conftest.py`.
- **Gasto máximo por folha: alvo de 300.000 (D15).** A 016 está em 194.909. Se passar, a tarefa otimiza ou reporta DONE_WITH_CONCERNS; acima do alvo, a etapa estaciona e o caso vai ao relatório. `LIMITE_CONSULTAS_PAGINA` não muda.
- Worktree da etapa com `.venv`. Em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` da etapa. A suíte inteira usa `-n` = 20 ÷ suítes ativas.

## Review Focus

1. **Seta e extensão de cota, pé de galinha de cerca, ramal de condutor, chevron da E06.3.5, V do aterramento, linha de chamada de texto, traço tracejado, roxo, wipeout, texto dentro do garfo e só preenchimento** não casam (Task 2).
2. **Mesmo desenho, um grupo:** o desenho casa exatamente uma gramática; o estai com X não casa também a variante sem X (Task 2).
3. **Dois estais opostos no mesmo poste** saem como duas observações, sem fundir, e caixas vizinhas que se encostam não trocam componentes (Task 2).
4. **Página hostil** com milhares de segmentos → `TetoGramaticasExcedido` pelo orçamento, sem laço N² fora dele (Task 4).
5. **Garfo sem círculo vizinho de círculo de outro desenho:** a envolvente só conta se contiver o garfo e for da mesma cor dele (Task 2).
6. **Garfo colorido sem marca:** verde ou vermelho, sem círculo e sem X, não casa o grupo "existente" (Task 2).

## Decisões do plano

- **R-E06.3.4-1, tipo `forked_stem`:** campos exatos `{"kind": "forked_stem", "enclosure": "none" | "ellipse", "removal_mark": bool, "max_span": número em (0, 72]}`. Com `removal_mark: true`, `enclosure` tem de ser `none`: **X vence a envolvente**, como no transformador, e a combinação `ellipse` + X é recusada no validador e no schema. Entra no validador de `declarative_symbols.py` (`isinstance` antes de `in`), em `docs/schemas/pacotes-simbologia.schema.json` e em `GRAMATICAS_SO_MODELO`.
- **R-E06.3.4-2, variantes habilitadas (as 3 de f02-14; cada uma tem gramática distinta):** só s14 v001 (`enclosure: none`, sem X; garfo preto ou cinza), s14 v002 (`enclosure: ellipse`, sem X) e s14 v003 (`enclosure: none`, `removal_mark: true`; X sobre garfo com ou sem círculo). As demais continuam `pending`, inclusive s15 v001: `_chave_de_forma` inclui o `family_id` e não une s14 e s15, por decisão da E06.3.3.2.2, e s15 v001 sairia como observação duplicada do mesmo desenho. Ruling em "Decisões para o usuário": o desenho do âncora AT sai como s14 v001, pacote de estai MT, o que afirma a família que a forma não mostra; a classe (ESTAI) está certa, e a E09 ou a curadoria decidem o agrupamento entre famílias. Se o laboratório mostrar que uma `visual_note` não confere, ruling no ledger.
  - **Garfo colorido sem marca** (verde ou vermelho, sem círculo e sem X) é recusado e registrado em `conclusoes.md`/handoff, para não afirmar "Existente" pelo inventário de v001 (`situation_note`: não inferir por cor isolada).
- **R-E06.3.4-3, caixa e componentes:** caixa do pictograma, ou seja, a envolvente quando existe (e também no estai com X sobre círculo, quando o círculo for da mesma cor do garfo); sem envolvente, os vértices do garfo e o trecho da haste até a junção. O X fica fora da caixa. O laboratório mede a alternativa de incluir a haste inteira, e vale a de melhor IoU com a centralidade preservada; a fusão com o legado (R-6) é critério secundário de desempate. A escolha é ruling no ledger. `componentes`: haste, garfo, envolvente e X.
- **R-E06.3.4-4, critério "acima do atual":** o atual tem 64/2/12 por centro e 63/3/13 por IoU, com 0 concordância de situação (ele não informa situação), antes da triagem; depois da triagem em render, os valores do `atual` são recalculados do mesmo jeito que os do `modelo`.
  - **Vitória literal, medida pela precisão e recall calculados:** precisão e recall de centro estritamente maiores que os do `atual` (97,0% e 84,2% brutos, recalculados depois da triagem), sem depender de pares fixos de `tp` e `fp`; precisão e recall do `atual` e do `modelo` usam a mesma triagem em render dos FP.
  - **Só depois de triados os FN restantes do `modelo` e confirmado que são todos de forma não coberta pelas hipóteses** vale a alternativa no padrão "≥ em todas as métricas" do ADR 0016, com ruling em "Decisões para o usuário": precisão e recall de centro, com a mesma triagem nos dois métodos, maiores ou iguais aos do `atual` e **recall estritamente maior que o do `atual`, ou então a etapa estaciona**, IoU tp ≥ 63, concordância de situação de ESTAI maior que 0, leitura errada de fato = 0, as demais classes iguais por folha às de `tmp/e06-3-3-2-2/final2`, diff núcleo × motor igual ao congelado e gasto ≤ 300.000.
  - As 8 leituras erradas ESTAI → ATERRAMENTO e 2 ESTAI → PONTO_CONEXAO são preexistentes e não contam como novas; uma gramática que as elimine é ganho, não requisito.
- **R-E06.3.4-5, gasto:** candidatos calculados uma vez por página (`estai_candidatos`) e `MarcasDaPagina` compartilhadas; cada candidato é classificado uma vez, e `casa_estai` só filtra a classificação pronta, sem gasto novo. Todo laço paga orçamento (o N² sem orçamento foi defeito da etapa anterior). A prova fica na Task 4, com os três itens do modelo: classificação uma vez por candidato, linearidade do gasto com 10 e 100 desenhos e teto calibrado com o `pytest.raises` só sobre a gramática, com o limite sendo o gasto dos índices mais uma folga.
- **R-E06.3.4-6, fusão com o legado no runner:** o legado (`pymupdf_guys.observar_estais`) emite POLILINHA do eixo, e `_same_occurrence` exige centro e tamanho próximos, com IoU ≥ 0,80 ou extremos a até 0,002 quando a área é zero. O teste da Task 3 usa um desenho que as duas regras observam e **fixa o resultado observado** com uma asserção (funde, não funde ou não sobrepõe), sem disjunção. Se não fundir, cada estai vira duas ocorrências no runner: o desfecho vai a "Para a E07", e a E07.2 trata a duplicata.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`, `docs/schemas/pacotes-simbologia.schema.json` | tipo `forked_stem` | 1 |
| `tests/unit/test_gramatica_estai_tipo.py` (novo) | validação, schema, motor ignora, perfil do modelo anuncia | 1 |
| os testes que afirmam o conjunto `GRAMATICAS_SO_MODELO` (`grep -rn -F 'GRAMATICAS_SO_MODELO' tests` e `grep -rn -F '"split_triangle"}' tests`), só a asserção do conjunto | conjunto | 1 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_estai.py` (novo), `drawing_model/symbol_matcher.py` | gramática e despacho | 2 |
| `src/zeny_project_handler_server/symbol_execution.py` | `grammar_estai` no digest | 2 |
| `tests/fixtures/symbol_grammars/estai.py` (novo), `tests/unit/test_grammar_estai.py` (novo) | fixture, gramática, negativos do Review Focus | 2 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-14.json` | habilitação das 3 variantes | 3 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | versão 1.5.0 | 3 |
| testes de contagem: `tests/server/test_e14_symbol_review.py:287-288`, `tests/unit/test_declarative_symbol_packages.py:177-178`, `tests/unit/test_pacotes_classes_da_ficha.py:363,476-477` (e `:370-375` e `:463-475`, que afirmam E06 só pendente, mudam de sentido; `_GRAMATICA_HABILITADAS` nesse arquivo recebe as 3 variantes), `tests/unit/test_gramatica_so_modelo_ataque.py:121,145,155`, `tests/unit/test_habilitacao_hastes_ataque.py:216,233`, `tests/unit/test_gramatica_rect_diagonal_tipo_ataque.py:249`; de versão: `tests/integration/test_haste_costuras_etapa_testador.py`, `tests/integration/test_model_symbols_bt_runner_ataque.py`, `tests/integration/test_model_symbols_haste_ataque.py`, `tests/unit/test_habilitacao_bt_ataque.py`, `tests/unit/test_model_symbols.py`, `tests/unit/test_model_symbols_componentes_ataque.py` | contagens 49 → 52 e 374 → 371; 1.4.0 → 1.5.0 | 3 |
| `tests/integration/test_model_symbols_estai_runner.py` (novo) | uma observação por forma com os pacotes reais; opção desligada sem efeito; fusão com o legado (R-6) | 3 |
| `tests/unit/test_grammar_estai_teto.py` (novo), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py` | teto, guarda e pureza (o teste novo da Task 3 entra na guarda pelo testador de etapa, porque nasce na mesma onda) | 4 |

**Ondas:** Task 1; laboratório sobre a Task 1; Task 2; depois {3, 4} em paralelo (arquivos disjuntos); testador de etapa (D8); medição pelo orquestrador.

**Soma:** 2h15 (30 + 45 + 40 + 20), mais o laboratório (caixa de 60 min), cerca de 3h15, sem dividir porque as tarefas ficam abaixo de ~3h e o laboratório corre em paralelo aos despachos da outra etapa. Pelo orçamento da etapa e pelo histórico da E06.3.3.2.2 (5h10 contra 3h05), vale a regra de estouro do protocolo. O relógio começa em b2ec3df. Com a janela de release, passar de 4h30 antes do marco de corte leva à ruling de continuar ou estacionar.

## Laboratório (depois da Task 1)

- **Base:** a branch da etapa com a Task 1 integrada.
- **Cada hipótese** é um `desenvolvedor` com `isolation: "worktree"`, sem commit e sem a suíte inteira. Implementa `grammar_estai.py` e o despacho com as marcas de `grammar_marcas.py`, que não altera (mudança nela vira `conclusoes.md` e, se a vencedora depender, uma Task 2b com ruling), habilita as 3 variantes de f02-14 só no worktree, escreve testes focados com os positivos e negativos do Review Focus e mede.
- **Medida obrigatória:** o desfecho da fusão com o legado (R-6), de cada hipótese e de cada caixa, medido num teste focado com `SymbolReconciliation` sobre um desenho que o legado observe, a partir de `tests/fixtures/guys/fixtures.py`.
- **Hipóteses** (duas, porque há outra etapa aberta, conforme o Orçamento de máquina):
  - **H-1, garfo como semente:** segmento fino como semente, com vértice de 2 dentes (cerca de 15–40 graus da haste, abertos para longe da haste), com envolvente e X opcionais. Mede também as duas caixas de R-E06.3.4-3.
  - **H-2, H-1 com ancoragem:** a H-1 mais o filtro geométrico de disco preenchido do poste, a distância relativa ao perfil da página (nunca limiar absoluto em pontos, porque as folhas maiores têm caixas maiores e a folha 008 tem estai sem disco), colinear com a haste.
- **Comandos** (rodar no worktree da hipótese, com o `.venv` da etapa e `PYTHONPATH=<worktree>/src`, com `--processos` conforme o Orçamento de máquina):
  - `python -m scripts.benchmark_simbolos_ficha --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/laboratorio/e06-3-4/<hipotese>/iter-<k> --metodo modelo --processos 6`
  - No fim: `python -m scripts.diff_simbolos_nucleo_motor ... --saida .../diff-<k> --processos 6`.
- **Métrica:** `total.modelo.centro.por_classe.ESTAI` e o mesmo em `iou`; lista de FP com folha e caixa; `leituras_erradas`; demais classes contra `tmp/e06-3-3-2-2/final2`; concordância de situação; gasto máximo; tempo máximo por folha.
- **Vitória e desempate:** os da R-E06.3.4-4 (literal antes da alternativa). Empate no critério: fusão com o legado (R-6), depois menos FP de fato e menor gasto. A triagem dos FP em render é do orquestrador, a partir dos recortes da hipótese.
- **Parada:** 60 min por hipótese, ou a vitória literal com 0 leitura errada de fato.
- **Entrega:** em `tmp/laboratorio/e06-3-4/<hipotese>/`: `patch.diff`, `metricas.json`, `conclusoes.md`, e os recortes dos FP em PNG.

## Tasks

### Task 1: Tipo `forked_stem`

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** alto

**Files:** `declarative_symbols.py`, `docs/schemas/pacotes-simbologia.schema.json`, `tests/unit/test_gramatica_estai_tipo.py` e os testes de conjunto da File Structure. Em vez de grep, os testes de conjunto são: `tests/unit/test_gramatica_so_modelo.py`, `tests/unit/test_habilitacao_hastes_ataque.py`, `tests/unit/test_gramatica_rect_diagonal_tipo_ataque.py` e `tests/unit/test_gramatica_triangulo_tipo_ataque.py`, onde a asserção citar o conjunto; confirme com grep antes de editar.

**Interfaces:** Produces: `GRAMMAR_FORKED_STEM = "forked_stem"` e o validador de `R-E06.3.4-1`; `GRAMATICAS_SO_MODELO` contém o tipo. Reaproveite a forma de `_split_triangle_grammar_ok`.

- [ ] **Step 1: Testes falhando:** aceita a forma exata; recusa `kind` errado, campo extra, `enclosure` fora do conjunto, `max_span` fora de (0, 72] ou de tipo errado (`bool` incluso), `removal_mark` não booleano e `ellipse` com X; o motor antigo ignora variante `forked_stem`; o perfil do modelo a anuncia. `-m pytest tests/unit/test_gramatica_estai_tipo.py` → FAIL.
- [ ] **Step 2: Implemente** validador, schema e `GRAMATICAS_SO_MODELO`; ajuste só a asserção de conjunto nos testes indicados.
- [ ] **Step 3: Rode** os testes e `scripts.audit_symbol_packages` → PASS e `errors []`.
- [ ] **Step 4: Commit** com os testes da área; suíte inteira uma vez antes do relatório.

### Task 2: Gramática de estai

**Estimativa:** 45 min · **Depende de:** laboratório (sobre a Task 1) · **Risco:** alto · **Laboratório:** sim

**Files:** `drawing_model/grammar_estai.py` (novo), `drawing_model/symbol_matcher.py`, `src/zeny_project_handler_server/symbol_execution.py`, `tests/fixtures/symbol_grammars/estai.py` (novo), `tests/unit/test_grammar_estai.py` (novo).

**Interfaces:** Produces `estai_candidatos(contexto, *, marcas: MarcasDaPagina) -> tuple[CandidatoEstai, ...]` e `casa_estai(contexto, gramatica, *, candidatos: tuple[CandidatoEstai, ...]) -> list[tuple[Caixa, int, tuple[int, ...]]]` (o mesmo contrato de `casa_triangulos`: caixa, caminho âncora e componentes; quem monta `CasamentoGramatica` é o despacho), com `CandidatoEstai` dataclass frozen levando `contexto`, `caixa`, `caminho_ancora`, `componentes`, `enclosure` e `removal_mark`; a fixture `tests/fixtures/symbol_grammars/estai.py` exporta `pagina_estai(destino, formas)` e `GRAMATICAS_ESTAI`, e um teste afirma que as três variantes habilitadas do pacote usam exatamente `GRAMATICAS_ESTAI`. Tudo partindo do patch vencedor do laboratório. `casa_estai(..., candidatos=)` levanta `ValueError` para candidato de outro contexto. Cor por `_mesma_cor` de `grammar_marcas` (uso privado já feito em `grammar_rect_diagonal`, declarado aqui) e preto/cinza por componentes iguais até 0,05 e abaixo de 0,4. Limiar por `origem_predominante` da página, sem número com mais de 4 casas.

- [ ] **Step 1: Testes** com a fixture sintética: os três grupos de forma (preto ou cinza sem envolvente, verde com círculo, X sobre garfo com círculo e sem círculo) casam exatamente uma gramática; dois estais opostos saem como dois casamentos; todos os negativos do Review Focus, inclusive garfo colorido sem marca, não casam; a envolvente de outro desenho não conta. → FAIL.
- [ ] **Step 2: Implemente** a partir do patch vencedor, com todo laço pagando orçamento. Registre o gasto na fixture.
- [ ] **Step 3: Rode** os testes focados → PASS; depois repita o benchmark do laboratório (rodada de correção que mexer no comportamento repete o benchmark).
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 3: Habilitação e versão 1.5.0

**Estimativa:** 40 min · **Depende de:** 2 · **Risco:** alto

**Files:** `family-f02-14.json`, `model_symbols.py`, os testes de contagem e de versão da File Structure, `tests/integration/test_model_symbols_estai_runner.py` (novo).

**Interfaces:** Consumes: `forked_stem` e a gramática. Produces: `_VERSAO = "1.5.0"`.

- [ ] **Step 1: Habilite** as 3 variantes de f02-14 da R-E06.3.4-2 com `grammar` e `status: enabled`, retirando o `reason` só dessas; as outras 14 ficam como estão, e `family-f02-15.json` não muda.
- [ ] **Step 2: Teste de integração:** com os pacotes reais e a fixture, uma observação por forma, sem observação duplicada do mesmo desenho; o caso com a opção desligada sem nenhuma observação do método; e a fusão com o legado (R-6), com a asserção do resultado observado.
- [ ] **Step 3: Ajuste contagens e versão** (49 → 52, 374 → 371, 1.4.0 → 1.5.0), incluindo o sentido novo de `test_pacotes_classes_da_ficha.py:370-375,463-475` e as listas `_GRAMATICA_HABILITADAS` desse arquivo.
- [ ] **Step 4: Rode** `scripts.audit_symbol_packages` e os testes → `errors []` e PASS.
- [ ] **Step 5: Commit**; suíte inteira uma vez antes do relatório.

### Task 4: Teto, guarda e pureza

**Estimativa:** 20 min · **Depende de:** 2 · **Risco:** normal

**Files:** `tests/unit/test_grammar_estai_teto.py` (novo), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py`.

**Interfaces:** Consumes: `casa_estai`, `estai_candidatos`, `OrcamentoConsultas`.

- [ ] **Step 1:** `test_classificacao_uma_vez_por_candidato`: gasto de página com as 3 variantes igual ao de uma variante só; linearidade do gasto com 10 e 100 desenhos; página hostil com milhares de segmentos levanta `TetoGramaticasExcedido`, com limite igual ao gasto dos índices mais uma folga e só a gramática dentro do `pytest.raises`.
- [ ] **Step 2:** `grammar_estai.py`, a fixture, `tests/unit/test_grammar_estai*.py` e `tests/unit/test_gramatica_estai_tipo.py` entram em `_GRAMATICAS_NOVAS`; pureza do núcleo inclui o arquivo novo.
- [ ] **Step 3: Commit**; suíte inteira uma vez antes do relatório.

## Operação do orquestrador (fora das tarefas)

Medição final na trilha B: `scripts.benchmark_simbolos_ficha ... --metodo atual --metodo modelo --saida <checkout principal>/tmp/e06-3-4/final`, `scripts.diff_simbolos_nucleo_motor` e o auditor. Critério da R-E06.3.4-4 verificado por folha. `check_test_integrity --base b2ec3df`, `osv-scanner` nos locks. Gate com `cmd.exe //c ".\\IniciarTestes.bat"`. O handoff registra R-2 (variantes `pending`, s15 v001), R-4, R-6, a tabela de suporte e a exportação ("Decisões para o usuário") e o "Para a E07" (desfecho da fusão) e "Para a E06.3.5" (gasto restante).

## Revisão de arquitetura

- Veredito: aprovado com notas.
- Rodadas: 2.
- Modelo: opus.
- Notas Menores: a medida de fusão usa `reconcile_symbols`; se não houver fusão, o desfecho vai ao plano da E07.2, e não só ao handoff.
- Custo aceito: o desenho do âncora AT sai como s14 v001, do pacote MT (R-2), em "Decisões para o usuário".
