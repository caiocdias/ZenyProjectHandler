# E06.3.4 — Estai: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reconhecer ESTAI (haste com garfo, com ou sem envolvente e X de retirada) sobre o modelo de desenho, sem afirmar forma que a ficha não mostra.

**Architecture:** segue a haste, o BT e o transformador:
- tipo só do modelo `forked_stem`, executado só por `declarative-drawing-model` no runner opt-in;
- gramática em `drawing_model/grammar_estai.py`, usando as marcas de `grammar_marcas.py` (envolvente, X, cor canônica, sinal da página), sem mexer nelas;
- variantes de mesma forma viram uma observação, com o agrupamento que já existe em `model_symbols.py`.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só adaptadores, scripts e fixtures), JSON + JSON Schema, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3" e "E06.3.4", D15, D19, handoff da E06.3.3.2.2 ("Para a E06.3.4"), plano `2026-11-08-leitura-vetorial-por-poste-e06-3-3-2-2.md` como modelo, ADR 0006 e 0016. Levantamento técnico: `.superpowers/sdd/levantamento-e06-3-4.md` do worktree da trilha B.

## Global Constraints

- Arquitetura hexagonal: o núcleo `drawing_model/` não importa PyMuPDF; o cliente não importa nada do servidor.
- Nenhuma migração, API ou DTO. O método sobre o modelo liga só no runner opt-in (D12). O analisador padrão, o motor antigo e o legado não mudam, e `ZENY_SERVER_SYMBOL_COMPOSITION=false` continua sem efeito sobre a saída.
- ADR 0006: `declarative-drawing-model` passa de 1.4.0 a 1.5.0 no commit da habilitação (Task 3). O motor antigo não executa tipo só do modelo.
- Sem dependência nova.
- Fixtures sintéticas autorais, positivas e negativas. Nenhuma coordenada, hash ou nome de folha real em código, pacote, fixture ou teste; a guarda de fonte (`_GRAMATICAS_NOVAS`) cobre os arquivos novos.
- Nada lê `examples/avaliacao-cega/`. As referências da rodada E03 estão congeladas. Leitores visuais não participam.
- Pytest com `--strict-markers` e `ResourceWarning` como erro; testes sem dependência de ordem, cwd, porta ou arquivo fixo. mypy strict, ruff e format. Complexidade abaixo de 31.
- Não tocar `scripts/benchmark_ficha_poste.py`, `scripts/benchmark_network_pdf.py`, `scripts/curation_ficha.py`, `scripts/ficha_predita_propostas.py`, `docs/fluxo-curadoria-incremental-simbologia.md` nem `examples/README.md` (arquivos da E07.1, aberta em paralelo), nem `tests/conftest.py`.
- **Gasto máximo por folha: alvo de 300.000 (D15).** A 016 está em 194.909. Se passar, a tarefa otimiza ou reporta DONE_WITH_CONCERNS; acima do alvo, a etapa estaciona e o caso vai ao relatório. `LIMITE_CONSULTAS_PAGINA` não muda.
- Worktree da etapa com `.venv`. Em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` da etapa. A suíte inteira usa `-n` = 20 ÷ suítes ativas.

## Review Focus

1. **Seta e extensão de cota, pé de galinha de cerca, ramal de condutor, chevron da E06.3.5, V do aterramento e linha de chamada de texto** não casam (Task 2).
2. **Mesmo desenho, um grupo:** o desenho casa exatamente uma gramática; o estai com X não casa também a variante sem X (Task 2).
3. **Dois estais opostos no mesmo poste** saem como duas observações, sem fundir, e caixas vizinhas que se encostam não trocam componentes (Task 2).
4. **Página hostil** com milhares de segmentos → `TetoGramaticasExcedido` pelo orçamento, sem laço N² fora dele (Task 4).
5. **Garfo sem círculo vizinho de círculo de outro desenho:** a envolvente só conta se contiver o garfo e for da mesma cor (Task 2).

## Decisões do plano

- **R-E06.3.4-1, tipo `forked_stem`:** campos exatos `{"kind": "forked_stem", "enclosure": "none" | "ellipse", "removal_mark": bool, "max_span": número em (0, 72]}`. Entra no validador de `declarative_symbols.py` (`isinstance` antes de `in`), em `docs/schemas/pacotes-simbologia.schema.json` e em `GRAMATICAS_SO_MODELO`.
- **R-E06.3.4-2, variantes habilitadas:** só as 4 cujo desenho é o traço bifurcado, conforme as `visual_note`: s14 v001 e s15 v001 (`enclosure: none`, `removal_mark: false`), s14 v002 (`enclosure: ellipse`, sem X) e s14 v003 (`removal_mark: true`). As demais (CZ-CZ, poste a poste, cruzeta-poste, e s15 v002) continuam `pending`, porque não têm forma própria na ficha. O agrupamento de formas comuns (`_chave_de_forma`) une s14 v001 e s15 v001 numa observação. Se o laboratório mostrar que uma `visual_note` não confere, ruling no ledger.
- **R-E06.3.4-3, caixa e componentes:** caixa do pictograma, ou seja, a envolvente quando existe; sem envolvente, os vértices do garfo e o trecho da haste até a junção. O X fica fora da caixa. O laboratório mede a alternativa de incluir a haste inteira, e vale a de melhor IoU com a centralidade preservada; a escolha é ruling no ledger. `componentes`: haste, garfo, envolvente e X.
- **R-E06.3.4-4, critério "acima do atual":** o atual tem 64/2/12 por centro e 63/3/13 por IoU, com 0 concordância de situação (ele não informa situação).
  - **Vitória literal:** centro com tp ≥ 65 e fp ≤ 1, ou seja, precisão e recall maiores.
  - **Se a vitória literal não for alcançável**, aceite no padrão "≥ em todas as métricas" do ADR 0016, com ruling em "Decisões para o usuário": tp ≥ 64, fp de fato ≤ 2 (FP triados em render), IoU tp ≥ 63, concordância de situação de ESTAI maior que 0, leitura errada de fato = 0, as demais classes iguais por folha às de `tmp/e06-3-3-2-2/final2`, diff núcleo × motor igual ao congelado e gasto ≤ 300.000.
  - As 8 leituras erradas ESTAI → ATERRAMENTO e 2 ESTAI → PONTO_CONEXAO são preexistentes e não contam como novas; uma gramática que as elimine é ganho, não requisito.
- **R-E06.3.4-5, gasto:** candidatos calculados uma vez por página (`estai_candidatos`) e `MarcasDaPagina` compartilhadas; cada candidato é classificado uma vez, e `casa_estai` só filtra a classificação pronta, sem gasto novo. Todo laço paga orçamento (o N² sem orçamento foi defeito da etapa anterior).

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`, `docs/schemas/pacotes-simbologia.schema.json` | tipo `forked_stem` | 1 |
| `tests/unit/test_gramatica_estai_tipo.py` (novo) | validação, schema, motor ignora, perfil do modelo anuncia | 1 |
| os testes que afirmam o conjunto `GRAMATICAS_SO_MODELO` (`grep -rn -F 'GRAMATICAS_SO_MODELO' tests` e `grep -rn -F '"split_triangle"}' tests`), só a asserção do conjunto | conjunto | 1 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_estai.py` (novo), `drawing_model/symbol_matcher.py` | gramática e despacho | 2 |
| `src/zeny_project_handler_server/symbol_execution.py` | `grammar_estai` no digest | 2 |
| `tests/fixtures/symbol_grammars/estai.py` (novo), `tests/unit/test_grammar_estai.py` (novo) | fixture, gramática, negativos do Review Focus | 2 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-14.json`, `family-f02-15.json` | habilitação das 4 variantes | 3 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | versão 1.5.0 | 3 |
| testes de contagem e de versão (`grep -rn '"1.4.0"\|\b49\b\|\b374\b' tests`, filtrando os de pacotes, auditor, tabela de suporte e perfil) | contagens 49 → 53 e 374 → 370; 1.4.0 → 1.5.0 | 3 |
| `tests/integration/test_model_symbols_estai_runner.py` (novo) | uma observação por forma com os pacotes reais; opção desligada sem efeito | 3 |
| `tests/unit/test_grammar_estai_teto.py` (novo), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py` | teto, guarda e pureza | 4 |

**Ondas:** Task 1; laboratório sobre a Task 1; Task 2; depois {3, 4} em paralelo (arquivos disjuntos); testador de etapa (D8); medição pelo orquestrador.

**Soma:** 2h15 (30 + 45 + 40 + 20), mais o laboratório (caixa de 60 min), cerca de 3h15. Pelo orçamento da etapa e pelo histórico da E06.3.3.2.2 (5h10 contra 3h05), vale a regra de estouro do protocolo. O relógio começa em b2ec3df. Com a janela de release, passar de 4h30 antes do marco de corte leva à ruling de continuar ou estacionar.

## Laboratório (depois da Task 1)

- **Base:** a branch da etapa com a Task 1 integrada.
- **Cada hipótese** é um `desenvolvedor` com `isolation: "worktree"`, sem commit e sem a suíte inteira. Implementa `grammar_estai.py` e o despacho com as marcas de `grammar_marcas.py`, que não altera (mudança nela vira `conclusoes.md` e, se a vencedora depender, uma Task 2b com ruling), habilita as 4 variantes só no worktree, escreve testes focados com os positivos e negativos do Review Focus e mede.
- **Hipóteses** (duas, porque há outra etapa aberta, conforme o Orçamento de máquina):
  - **H-1, garfo como semente:** segmento fino como semente, com vértice de 2 dentes (cerca de 15–40 graus da haste, abertos para longe da haste), com envolvente e X opcionais. Mede também as duas caixas de R-E06.3.4-3.
  - **H-2, H-1 com ancoragem:** a H-1 mais o filtro geométrico de disco preenchido do poste a 3–17 pt, colinear com a haste.
- **Comandos** (rodar no worktree da hipótese, com o `.venv` da etapa e `PYTHONPATH=<worktree>/src`, com `--processos` conforme o Orçamento de máquina):
  - `python -m scripts.benchmark_simbolos_ficha --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/laboratorio/e06-3-4/<hipotese>/iter-<k> --metodo modelo --processos 6`
  - No fim: `python -m scripts.diff_simbolos_nucleo_motor ... --saida .../diff-<k> --processos 6`.
- **Métrica:** `total.modelo.centro.por_classe.ESTAI` e o mesmo em `iou`; lista de FP com folha e caixa; `leituras_erradas`; demais classes contra `tmp/e06-3-3-2-2/final2`; concordância de situação; gasto máximo; tempo máximo por folha.
- **Vitória e desempate:** os da R-E06.3.4-4 (literal antes da alternativa). Empate no critério: menos FP de fato, depois menor gasto. A triagem dos FP em render é do orquestrador, a partir dos recortes da hipótese.
- **Parada:** 60 min por hipótese, ou tp ≥ 65 e fp ≤ 1 com 0 leitura errada de fato.
- **Entrega:** em `tmp/laboratorio/e06-3-4/<hipotese>/`: `patch.diff`, `metricas.json`, `conclusoes.md`, e os recortes dos FP em PNG.

## Tasks

### Task 1: Tipo `forked_stem`

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** alto

**Files:** `declarative_symbols.py`, `docs/schemas/pacotes-simbologia.schema.json`, `tests/unit/test_gramatica_estai_tipo.py` e os testes de conjunto da File Structure.

**Interfaces:** Produces: `GRAMMAR_FORKED_STEM = "forked_stem"` e o validador de `R-E06.3.4-1`; `GRAMATICAS_SO_MODELO` contém o tipo. Reaproveite a forma de `_split_triangle_grammar_ok`.

- [ ] **Step 1: Testes falhando:** aceita a forma exata; recusa `kind` errado, campo extra, `enclosure` fora do conjunto, `max_span` fora de (0, 72] ou de tipo errado (`bool` incluso), `removal_mark` não booleano; o motor antigo ignora variante `forked_stem`; o perfil do modelo a anuncia. `-m pytest tests/unit/test_gramatica_estai_tipo.py` → FAIL.
- [ ] **Step 2: Implemente** validador, schema e `GRAMATICAS_SO_MODELO`; ajuste só a asserção de conjunto nos testes indicados.
- [ ] **Step 3: Rode** os testes e `scripts.audit_symbol_packages` → PASS e `errors []`.
- [ ] **Step 4: Commit** com os testes da área; suíte inteira uma vez antes do relatório.

### Task 2: Gramática de estai

**Estimativa:** 45 min · **Depende de:** laboratório (sobre a Task 1) · **Risco:** alto · **Laboratório:** sim

**Files:** `drawing_model/grammar_estai.py` (novo), `drawing_model/symbol_matcher.py`, `src/zeny_project_handler_server/symbol_execution.py`, `tests/fixtures/symbol_grammars/estai.py` (novo), `tests/unit/test_grammar_estai.py` (novo).

**Interfaces:** Produces `estai_candidatos(contexto, marcas=...) -> tuple[...]` e `casa_estai(contexto, gramatica, candidatos=...) -> ...`, no contrato de `CasamentoGramatica`, partindo do patch vencedor do laboratório. `casa_estai(..., candidatos=)` levanta `ValueError` para candidato de outro contexto. Limiar por `origem_predominante` da página, sem número com mais de 4 casas.

- [ ] **Step 1: Testes** com a fixture sintética: os três grupos de forma (preto sem envolvente, verde com círculo, vermelho com X) casam exatamente uma gramática; dois estais opostos saem como dois casamentos; todos os negativos do Review Focus não casam; a envolvente de outro desenho não conta. → FAIL.
- [ ] **Step 2: Implemente** a partir do patch vencedor, com todo laço pagando orçamento. Registre o gasto na fixture.
- [ ] **Step 3: Rode** os testes focados → PASS; depois repita o benchmark do laboratório (rodada de correção que mexer no comportamento repete o benchmark).
- [ ] **Step 4: Commit**; suíte inteira uma vez antes do relatório.

### Task 3: Habilitação e versão 1.5.0

**Estimativa:** 40 min · **Depende de:** 2 · **Risco:** alto

**Files:** `family-f02-14.json`, `family-f02-15.json`, `model_symbols.py`, os testes de contagem e de versão da File Structure, `tests/integration/test_model_symbols_estai_runner.py` (novo).

**Interfaces:** Consumes: `forked_stem` e a gramática. Produces: `_VERSAO = "1.5.0"`.

- [ ] **Step 1: Habilite** as 4 variantes da R-E06.3.4-2 com `grammar` e `status: enabled`, retirando o `reason` só dessas; as outras 13 ficam como estão.
- [ ] **Step 2: Teste de integração:** com os pacotes reais e a fixture, uma observação por forma (`referencias_possiveis` em lista quando s14 v001 e s15 v001 casam o mesmo desenho), e o caso com a opção desligada sem nenhuma observação do método.
- [ ] **Step 3: Ajuste contagens e versão** (49 → 53, 374 → 370, 1.4.0 → 1.5.0).
- [ ] **Step 4: Rode** `scripts.audit_symbol_packages` e os testes → `errors []` e PASS.
- [ ] **Step 5: Commit**; suíte inteira uma vez antes do relatório.

### Task 4: Teto, guarda e pureza

**Estimativa:** 20 min · **Depende de:** 2 · **Risco:** normal

**Files:** `tests/unit/test_grammar_estai_teto.py` (novo), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py`.

**Interfaces:** Consumes: `casa_estai`, `estai_candidatos`, `OrcamentoConsultas`.

- [ ] **Step 1:** página sintética hostil com milhares de segmentos levanta `TetoGramaticasExcedido`, com o gasto medido.
- [ ] **Step 2:** `grammar_estai.py`, a fixture e os testes novos entram em `_GRAMATICAS_NOVAS`; pureza do núcleo inclui o arquivo novo.
- [ ] **Step 3: Commit**; suíte inteira uma vez antes do relatório.

## Operação do orquestrador (fora das tarefas)

Medição final na trilha B: `scripts.benchmark_simbolos_ficha ... --metodo atual --metodo modelo --saida <checkout principal>/tmp/e06-3-4/final`, `scripts.diff_simbolos_nucleo_motor` e o auditor. Critério da R-E06.3.4-4 verificado por folha. Gate com `cmd.exe //c ".\\IniciarTestes.bat"`.
