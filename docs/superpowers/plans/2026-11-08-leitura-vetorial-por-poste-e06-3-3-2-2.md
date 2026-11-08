# E06.3.3.2.2 — Transformador: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reconhecer TRANSFORMADOR de forma triangular (meio ciano ou de contorno, com ou sem círculo envolvente, com ou sem X) sobre o modelo de desenho, sem afirmar o uso (Rede, Dedicado ou IP) que a forma não discrimina, e sem leitura errada de fato.

**Architecture:** segue o desenho da haste e do BT:
- **Tipo só do modelo:** `split_triangle`, executado só por `declarative-drawing-model` no runner opt-in.
- **Gramática:** vive em `drawing_model/grammar_triangulo.py`. Usa as marcas de `grammar_marcas.py` (envolvente, X, cor canônica e sinal da página) e não mexe nelas.
- **Variantes com a mesma forma:** são 2 ou 3 para cada combinação de preenchimento, envolvente e X. Elas viram **uma** observação, montada em `model_symbols.py`:
  - `variante_inventario` e `template` recebem o representante, que é o menor id do grupo;
  - `referencias_possiveis` recebe a lista JSON do grupo inteiro, a mesma semântica do método E05 de transformadores (`pymupdf_transformers.py:5`, `_referencias_triangulo`).

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só adaptadores, scripts e fixtures), JSON + JSON Schema, pytest (xdist), mypy strict.

**Spec:**
- `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3.3.2" (divisão e achado do transformador real) e "E06.3.3.2.2";
- os handoffs da E06.3.3.1 e da E06.3.3.2.1, inclusive "Para a E06.3.3.2.2";
- o plano `docs/superpowers/plans/2026-11-08-leitura-vetorial-por-poste-e06-3-3-1.md`, que esta etapa replica;
- ADR 0006 e 0016.

## Global Constraints

- Arquitetura hexagonal:
  - o núcleo `drawing_model/` não importa PyMuPDF;
  - o cliente não importa nada do servidor;
  - os DTOs seguem `tests/contracts/test_architecture.py`.
- Nenhuma migração, API ou DTO. O método sobre o modelo liga só no runner opt-in (D12). O analisador padrão, o motor antigo, o legado e o método E05 de transformadores não mudam.
- ADR 0006: `declarative-drawing-model` passa de 1.3.0 a 1.4.0 no commit da habilitação (Task 4). O motor antigo não executa tipo só do modelo (`variantes_do_motor`).
- Sem dependência nova.
- Fixtures sintéticas autorais, positivas e negativas.
  - Nenhuma coordenada, hash ou nome de folha real em código, pacote, fixture ou teste.
  - A guarda de fonte (`_GRAMATICAS_NOVAS`) cobre os arquivos novos.
- Nada lê `examples/avaliacao-cega/`. As referências da rodada E03 estão congeladas. Leitores visuais não participam.
- Pytest:
  - `--strict-markers`, com `ResourceWarning` como erro;
  - testes sem dependência de ordem, cwd, porta ou arquivo fixo.
- mypy strict, ruff e format. Complexidade abaixo de 31.
- Não tocar `scripts/benchmark_ficha_poste.py` nem `tests/conftest.py`.
- **Gasto máximo por folha: alvo de 200.000.** A 016 está em 189.097. Se passar, a tarefa otimiza ou reporta DONE_WITH_CONCERNS. O alvo só sobe por ruling, com o valor registrado no handoff (R-6), **até 220.000**; acima disso, a etapa estaciona e pergunta ao usuário.
- Worktree da etapa com `.venv`.
  - Em onda, use `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` da etapa.
  - A suíte inteira usa `-n` = 20 ÷ suítes ativas.

## Review Focus

1. **Triângulo verde sólido** (marca de poste ou seta de linha), ponta de seta, Δ de glifo e triângulo roxo com S (v016–v018, fora de escopo) → não casam (Task 3).
2. **Meio ciano** (dois preenchimentos, branco e ciano, que dividem o triângulo) e **contorno** (só traço) → saem no grupo certo. O mesmo desenho casa exatamente um grupo de forma (Task 3).
3. **Mesma forma, uso diferente:** v001 e v004 (meio ciano, base) casam o mesmo desenho e saem como **uma** observação com `referencias_possiveis = ["…v001", "…v004"]`. O contorno base sai com v007, v010 e v013.
   - Nunca saem duas ou três predições ou observações do modelo para o mesmo desenho (Task 2; provado na Task 4 com os pacotes reais).
   - Na reconciliação, a lista dá `ambiguous_reference_id` com decisão `review`.
   - Variantes de classe, família, papel ou destino diferentes nunca se agrupam.
4. **Ponto cego da caixa:**
   - a caixa é o pictograma, ou seja, o círculo envolvente quando existe; senão, o triângulo;
   - o X fica fora da caixa;
   - a haste de ligação não é exigida.

   Com a caixa do método E05 (triângulo mais marcadores), a fusão no runner é medida, e não suposta (Task 4).
5. **Página hostil** com milhares de triângulos e preenchimentos → `TetoGramaticasExcedido` pelo orçamento (Task 5).

## Decisões do plano

- **R-E06.3.3.2.2-1, tipo `split_triangle`:**
  - **Campos exatos:** `{"kind": "split_triangle", "fill": "half_cyan" | "outline", "enclosure": "none" | "ellipse", "removal_mark": bool, "max_span": número em (0, 72]}`.
  - **Onde entra:** no validador de `declarative_symbols.py` (com `isinstance` antes de `in`), no schema `docs/schemas/pacotes-simbologia.schema.json` e em `GRAMATICAS_SO_MODELO`.
  - **Mapa das variantes de f02-18:**

    | Grupo | fill | enclosure | removal_mark | Variantes |
    |---|---|---|---|---|
    | meio ciano, base | `half_cyan` | `none` | false | v001, v004 |
    | meio ciano, X | `half_cyan` | `none` | true | v002, v005 |
    | meio ciano, envolvente | `half_cyan` | `ellipse` | false | v003, v006 |
    | contorno, base | `outline` | `none` | false | v007, v010, v013 |
    | contorno, X | `outline` | `none` | true | v008, v011, v014 |
    | contorno, envolvente | `outline` | `ellipse` | false | v009, v012, v015 |

  - **Fora de escopo:** v016–v027 (roxo com S, enrolamentos, regulador) continuam `pending`.
  - **A cor não decide a situação.** O ciano decide só o `fill`, como faz o E05 (`_toca_ciano`).
- **R-E06.3.3.2.2-2, formas comuns sem afirmar o uso:**
  - **Agrupamento** em `model_symbols.observar_pacotes_modelo`. Formam um grupo, e viram **uma** observação, os casamentos que têm igual:
    - a página;
    - o `caminho` âncora;
    - a caixa, arredondada como em `symbol_matcher._caixa_arredondada`;
    - a gramática (dicionários `recognition.grammar` idênticos);
    - `class_code`, `family_id` do pacote, `role` e `destination`.

    Com isso, nunca se esconde uma ambiguidade de classe, que continua saindo como `ambiguous_class_or_id` na reconciliação.
  - **Representante:** o menor id do grupo. Dele saem `template`, `variante_inventario` e os demais atributos.
  - **`referencias_possiveis`:** a lista JSON ordenada dos ids do grupo, a mesma forma do E05 e a que `symbol_reconciliation._reference_ids` já lê.
  - **Grupo de um:** a observação continua exatamente como hoje, com `referencias_possiveis` igual ao id (string).
  - **Por que assim:**
    - o runner exige `variante_inventario` (`scripts/symbol_benchmark_runner.py:462`);
    - as variantes do grupo têm as mesmas situações, então a concordância de situação é a mesma qualquer que seja o representante;
    - não há contrato novo, porque as chaves e a semântica da lista já existem.
  - **Alternativas descartadas:**
    - habilitar só as variantes "Rede", o que afirmaria o uso;
    - uma chave nova de ambiguidade, que seria contrato novo e decisão do usuário;
    - deixar duplicar, o que geraria 2 ou 3 predições ou observações do modelo por transformador. A reconciliação do runner as fundiria, mas o benchmark roda com `reconcile_symbols: False` e as contaria como FP.
  - **Destino:** vai a "Decisões para o usuário" e a "Para a E07".
    - Quando a lista tem mais de um id, `variante_inventario` é o representante (sempre o id "Rede") e **não identifica a variante**. Quem consome lê `referencias_possiveis`.
    - Leitores de hoje: `diff_simbolos_nucleo_motor.py:205`, `symbol_benchmark_runner.py:462` e o mapa variante → situação da E07 (R-7 da E06.3.3.2.1).
    - O agrupamento é decisão do plano, e não de contrato, conforme a revisão de arquitetura: não muda DTO, API nem migração, e `simbolo_reference_ids` persiste a mesma união.
- **R-E06.3.3.2.2-3, caixa, marcas e componentes** (o mesmo padrão do BT):
  - **Caixa:** o pictograma, isto é, a envolvente quando existe e, senão, a caixa do triângulo.
  - **Fora da caixa:** o X e a haste de ligação. A haste de ligação não é exigida.
  - **`componentes`:** triângulo (todos os caminhos de `origens`), preenchimentos, envolvente, X e haste de ligação, quando existe, sem repetir a âncora.
  - **`proprios` do X:** triângulo, preenchimentos e haste.
  - **Contexto:**
    - `MarcasDaPagina` é a recebida no despacho, com `marcas_do_contexto`;
    - cada `Triangulo` candidato guarda o `contexto` de origem;
    - `casa_triangulos(..., candidatos=)` levanta `ValueError` para candidato de outro contexto. Isso fecha, para esta gramática, o Menor da E06.3.3.2.1 sobre `casa_*(candidatos=)`.
- **R-E06.3.3.2.2-4, critério de aceite.** O critério do roadmap não é alcançável como está escrito:
  - o `atual` tem 14/2/0, com recall de 100%;
  - os 2 FP dele são **transformadores reais que a ficha não anota**: o de X vermelho ao lado do P8 na 012 e o de círculo e meio ciano na 014. O orquestrador conferiu os dois em render.
  - Um leitor correto também os lê. "Precisão e recall maiores" exigiria ler menos transformadores reais.

  Ruling do critério desta etapa, no padrão "≥ em todas as métricas" do ADR 0016 (Decisão, último item):
  - TRANSFORMADOR do `modelo` (centro) com tp = 14 e fn = 0;
  - todo FP de TRANSFORMADOR confirmado em render como transformador real ("FP de fato" = 0), de modo que a precisão triada fique ≥ a do `atual` triado (100%);
  - **"acima do atual"** se prova pela concordância de situação de TRANSFORMADOR (centro), em que os concordantes do `modelo` têm de ser estritamente mais que os do `atual`.
    - O E05 não informa `variant_id` nem `situation`, e na E06.3.3.2.1 o `atual` ficou em 0 concordantes.
    - A ficha anota a situação de alguns TRANSFORMADOR ("proposto instalar", "existente").
    - Se nenhum TP do `modelo` tiver situação anotada, o item vira ruling e os demais sustentam o aceite;
  - leitura errada afirmada de fato = 0;
  - as demais classes do `modelo` iguais por folha às de `tmp/e06-3-3-2-1/final/simbolos-ficha.json`;
  - o diff núcleo × motor igual ao congelado;
  - a concordância de situação das três classes da E06.3.3.2.1 sem piora (14/14).

  A ruling vai a "Decisões para o usuário". Os dois transformadores reais sem anotação vão à lista de referências para a curadoria.
- **R-E06.3.3.2.2-5, fusão com o E05 no runner opt-in:**
  - **Caixa do E05:** é a união dos vértices do triângulo com os pontos dos marcadores, o que inclui os extremos do X (`_forma_triangular`).
  - **Teste da Task 4:** usa um desenho que as duas regras observam. O desenvolvedor mede primeiro qual destes três resultados acontece:
    - funde;
    - não funde, com duas ocorrências aceitas até a E09 e registro em "Para a E07";
    - não se sobrepõem.

    Depois, o teste **fixa o resultado observado** com uma asserção, e não com uma disjunção. Assim, uma mudança de fusão quebra o teste.
  - **Limite:** o E05 não muda.
- **R-E06.3.3.2.2-6, gasto:**
  - o triângulo usa candidatos calculados uma vez por página (`triangulos_candidatos`, como `retangulos_candidatos`) e as `MarcasDaPagina` compartilhadas;
  - **cada candidato é classificado uma vez**: `fill`, envolvente e X são lidos e pagos por candidato, e não por variante;
    - `casa_triangulos` só filtra a classificação pronta pela gramática da variante, sem gasto novo;
    - as 15 variantes custam o mesmo que as 6 formas;
    - a Task 3 prova isso (`test_classificacao_uma_vez_por_candidato`), comparando o gasto de uma página com 15 variantes habilitadas e com 6 (uma por grupo);
  - a envolvente e o X só são pedidos para candidatos que passam no triângulo.
  - **Teto:** se o gasto da 016 passar de 200.000, a ruling pode subir o alvo de medição com o valor, **até 220.000**, e o caso vai a "Decisões para o usuário" (folga do teto). Acima de 220.000, a etapa estaciona e a pergunta vai ao usuário, porque o teto é requisito não funcional pendente de decisão desde a E06.3.3.2.1. `LIMITE_CONSULTAS_PAGINA` (2.000.000) não muda.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`, `docs/schemas/pacotes-simbologia.schema.json` | tipo `split_triangle` | 1 |
| `tests/unit/test_gramatica_triangulo_tipo.py` (novo) | validação, schema, motor ignora, perfil do modelo anuncia | 1 |
| os testes que afirmam o conjunto `GRAMATICAS_SO_MODELO` (`grep -rn -F 'GRAMATICAS_SO_MODELO' tests` e `grep -rn -F '"rect_diagonal"}' tests`). São pelo menos `tests/unit/test_gramatica_so_modelo.py`, `tests/unit/test_habilitacao_hastes_ataque.py` e `tests/unit/test_gramatica_rect_diagonal_tipo_ataque.py:251` | só a asserção do conjunto | 1 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | agrupamento de formas comuns (2), versão 1.4.0 (4) | 2, 4 |
| `tests/unit/test_model_symbols_formas_comuns.py` (novo) | agrupamento | 2 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_triangulo.py` (novo), `drawing_model/symbol_matcher.py` | gramática e despacho | 3 |
| `src/zeny_project_handler_server/symbol_execution.py` | `grammar_triangulo` no digest | 3 |
| `tests/fixtures/symbol_grammars/triangulo.py` (novo), `tests/unit/test_grammar_triangulo.py` (novo) | fixture, gramática | 3 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-18.json` (v001–v015) | habilitação | 4 |
| os testes de contagem e de versão (`grep -rn '"1.3.0"\|1_3_0\|389\|\b34\b' tests` filtrado para os testes de pacotes, auditor, tabela de suporte e perfil: `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py`, `tests/unit/test_gramatica_so_modelo_ataque.py`, `tests/unit/test_habilitacao_hastes_ataque.py`, `tests/unit/test_habilitacao_bt_ataque.py`, `tests/unit/test_model_symbols.py`, `tests/unit/test_model_symbols_componentes_ataque.py`, `tests/integration/test_haste_costuras_etapa_testador.py`, `tests/integration/test_model_symbols_haste_ataque.py`, `tests/integration/test_model_symbols_bt_runner_ataque.py`, `tests/unit/test_gramatica_rect_diagonal_tipo_ataque.py:249`) | contagens 34 → 49 e 389 → 374; versão 1.3.0 → 1.4.0 | 4 |
| `tests/integration/test_model_symbols_trafo_runner.py` (novo) | uma observação por forma com os pacotes reais; fusão com o E05 (R-5) | 4 |
| `tests/unit/test_grammar_triangulo_teto.py` (novo), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py` | teto, guarda e pureza | 5 |

**Ondas:**
1. Onda A, Tasks 1 e 2 (arquivos disjuntos).
2. Laboratório sobre a Onda A integrada.
3. Task 3.
4. Onda B, Tasks 4 e 5 (arquivos disjuntos).
5. Testador de etapa (D8).
6. Task 6, medição pelo orquestrador.

**Soma:** 3h05 (25 + 35 + 45 + 40 + 20 + 20), mais o laboratório (caixa de 60 min), cerca de 4h05.
- É o mesmo formato da E06.3.3.1, que não foi dividida.
- **Risco registrado:** as duas etapas anteriores estouraram a estimativa (3h36 e 3h40 contra 3h00), e esta pode passar das 4h30.
- O relógio começa em 264d4cb, e vale a regra de estouro do protocolo. Se o relógio passar de 4h30 antes da medição, o orquestrador decide entre continuar, dividir ou estacionar, e registra a ruling.

## Laboratório (depois da Onda A)

- **Base:** a branch da etapa com a Onda A integrada.
- **Cada hipótese** é um `desenvolvedor` com `isolation: "worktree"`, sem commit e sem a suíte inteira. Ele:
  - implementa `grammar_triangulo.py` e o despacho (R-1, R-3, R-6) com as marcas de `grammar_marcas.py`, que ele não altera.
    - Se precisar, descreve a mudança em `conclusoes.md`.
    - Se a hipótese vencedora depender dela, o orquestrador abre uma Task 2b antes da Task 3 e registra a ruling. Campos pré-declarados da Task 2b:
      - Estimativa: até 45 min. Depende de: laboratório. Risco: alto.
      - Arquivos: `drawing_model/grammar_marcas.py` e os testes dele (`tests/unit/test_grammar_marcas*.py`).
      - Prova: tp/fp/fn por folha das três classes iguais a `tmp/e06-3-3-2-1/final`, concordância de 14/14 e diff igual ao congelado.
      - A mudança de saída fica coberta pela 1.4.0 da Task 4, na mesma etapa (ADR 0006). A soma é recalculada.
    - Se a hipótese não depender dela, a mudança vai ao handoff;
  - habilita as 15 variantes no JSON só no worktree, com as gramáticas da tabela de R-1;
  - escreve testes focados com os positivos e negativos do Review Focus 1 e 2;
  - mede.
- **Hipóteses:**
  - **H-1, contorno primeiro.** As sementes são triângulos fechados de traço: polilinha fechada de 3 vértices, subcaminho fechado de 3 retas, ou caminho de 3 retas com preenchimento. O `half_cyan` é um preenchimento ciano dentro do triângulo, encostado numa mediana.
  - **H-2, preenchimento primeiro.** As sementes são os preenchimentos triangulares: dois preenchimentos, branco e ciano, que dividem uma aresta formam o triângulo `half_cyan`. Para `outline`, cai em H-1.
  - **H-3, envolvente primeiro.** O círculo de `grammar_marcas` é semente para os grupos com envolvente, com o triângulo inscrito. Sem envolvente, cai em H-1.
  - Todas usam o sinal da página (`origem_predominante`) e as `MarcasDaPagina`, com a própria tabela de perfil por origem dentro de `grammar_triangulo.py`.
- **Comandos:**
  - Rode no worktree da hipótese, com o `.venv` da etapa, `PYTHONPATH=<worktree>/src` e `--processos 6`. `<rodada E03>` é `<checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas`.
  - Benchmark: `python -m scripts.benchmark_simbolos_ficha --rodada <rodada E03> --saida <checkout principal>/tmp/laboratorio/e06-3-3-2-2/<hipotese>/iter-<k> --metodo modelo --processos 6`.
  - No fim: `python -m scripts.diff_simbolos_nucleo_motor ... --saida .../diff-<k> --processos 6`.
- **Métrica:**
  - `total.modelo.centro.por_classe.TRANSFORMADOR` (tp/fp/fn);
  - a lista dos FP com folha e caixa;
  - `leituras_erradas` por classe;
  - as outras classes iguais às de `tmp/e06-3-3-2-1/final/simbolos-ficha.json`;
  - a distribuição dos grupos de forma;
  - o gasto máximo;
  - o tempo máximo por folha.
- **Vitória:**
  - tp = 14 e fn = 0;
  - fp ≤ 2;
  - todo FP com render que mostre transformador real. A triagem em render é do **orquestrador**, a partir dos recortes da hipótese;
  - leitura errada de fato = 0;
  - outras classes intactas;
  - gasto ≤ 200.000.

  O desempate é o menor número de FP brutos e, depois, o menor gasto. Se nenhuma hipótese cumprir tudo, escolhe-se a de maior tp com 0 leitura errada de fato, e aplica-se R-4 ou R-6 com ruling.
- **Parada:** 60 min por hipótese, ou 14/≤2/0 com 0 leitura errada de fato e os FP triados.
- **Entrega:** em `tmp/laboratorio/e06-3-3-2-2/<hipotese>/`, os arquivos `patch.diff`, `metricas.json` e `conclusoes.md`, com os recortes dos FP em PNG.

## Revisão de arquitetura

- **Veredito:** aprovado com notas, na rodada 1 (`revisor-arquitetura`, opus).
  - Rodada 0: bloqueado por 2 Importantes. O primeiro era a chave do agrupamento sem classe, família, papel e destino. O segundo era o gasto cobrado por variante e o teto sem limite. Havia ainda 9 Menores.
  - Rodada 1: aprovado com notas.
- **Modelo:** opus.
- **Notas Menores da rodada 1, aplicadas antes da execução:**
  - a R-6 aponta a Task 3 como a que prova o gasto;
  - a Task 2b condicional tem os campos pré-declarados;
  - o teto de 220.000 está nas Global Constraints.
- **Sem decisão de arquitetura para o usuário:** a R-2 é decisão do plano, e a R-4 é ruling de critério, que vai a "Decisões para o usuário".

## Tasks

### Task 1: Tipo `split_triangle`

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`, `docs/schemas/pacotes-simbologia.schema.json`
- Modify: os testes que afirmam o conjunto `GRAMATICAS_SO_MODELO`, só nessa asserção, que passa a `{"stem_bars", "rect_diagonal", "split_triangle"}`
- Create: `tests/unit/test_gramatica_triangulo_tipo.py`

**Interfaces:**
- Produces: `split_triangle` em `_GRAMMARS`, no validador (`_split_triangle_grammar_ok`) e em `GRAMATICAS_SO_MODELO`, e o ramo do schema.

- [ ] **Step 1: Escrever os testes** com pacotes em `tmp_path` (`carregar_pacotes(packages_dir=tmp_path)`):
  - `test_split_triangle_valido_carrega`: as 6 combinações da tabela de R-1;
  - `test_split_triangle_invalido_recusa`:
    - campo a mais ou a menos;
    - `fill` desconhecido ou lista;
    - `enclosure` desconhecido;
    - `removal_mark` não booleano;
    - `max_span` 0, 73, NaN ou booleano;
  - `test_schema_tem_o_ramo_split_triangle`: estrutural, como o da `rect_diagonal`;
  - `test_motor_ignora_split_triangle`;
  - `test_perfil_do_modelo_anuncia_split_triangle`.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar:**
  - o arquivo novo, `tests/unit/test_gramatica_so_modelo*.py`, `tests/unit/test_habilitacao_hastes_ataque.py` e `tests/unit/test_declarative_symbol_packages.py`;
  - o auditor, que deve sair com `errors []`;
  - ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: tipo de gramatica split_triangle so do modelo`).

### Task 2: Formas comuns numa observação

**Estimativa:** 35 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/model_symbols.py`
- Create: `tests/unit/test_model_symbols_formas_comuns.py`

**Interfaces:**
- Produces: em `observar_pacotes_modelo`, o agrupamento de R-2. Grupo de mais de um id → uma `ObservacaoSimbolo`:
  - `template` e `variante_inventario` = menor id;
  - `atributos["referencias_possiveis"]` = `json.dumps(sorted(ids))`.

  Grupo de um → a observação de hoje, sem nenhuma mudança.

- [ ] **Step 1: Escrever os testes.** Use pacotes sintéticos em `tmp_path`, com duas ou três variantes de gramática **idêntica** de um tipo existente (`stem_bars` ou `rect_diagonal`, com a fixture desse tipo), habilitadas, e página pura desenhada pela fixture:
  - `test_variantes_de_gramatica_igual_viram_uma_observacao`: uma observação, `template` = menor id e `referencias_possiveis` = lista JSON ordenada;
  - `test_gramaticas_diferentes_no_mesmo_desenho_nao_se_agrupam`: duas variantes de gramática diferente que casassem a mesma caixa continuam separadas, se houver desenho assim; senão, documente por que não há;
  - `test_grupo_de_um_nao_muda`: a observação é igual à de hoje, campo a campo;
  - `test_caixas_diferentes_nao_se_agrupam`: duas ocorrências da mesma forma em pontos diferentes da página dão duas observações, cada uma com a lista;
  - `test_classes_diferentes_nao_se_agrupam`: duas variantes de gramática idêntica e `class_code` diferente (ou `family_id`, `role` ou `destination` diferente), no mesmo desenho, dão duas observações;
  - `test_reconciliacao_le_a_lista`: `reconcile_symbols`, a API pública, sobre a observação agrupada leva aos ids do grupo inteiro, com o motivo `ambiguous_reference_id` e a decisão `review`;
  - `test_nenhuma_habilitada_real_compartilha_a_chave`: com os pacotes reais de hoje, nenhum par de variantes habilitadas tem a mesma chave de grupo (gramática, `class_code`, `family_id`, `role`, `destination`).
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar:**
  - o arquivo novo, `tests/unit/test_model_symbols*.py` e `tests/integration/test_model_symbols*.py`;
  - ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: variantes de mesma forma numa observacao do modelo`).

### Task 3: Gramática `split_triangle`

**Estimativa:** 45 min · **Depende de:** laboratório (sobre as Tasks 1 e 2) · **Risco:** alto · **Laboratório:** sim

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_triangulo.py`, `tests/fixtures/symbol_grammars/triangulo.py`, `tests/unit/test_grammar_triangulo.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`, `src/zeny_project_handler_server/symbol_execution.py` (digest)

**Interfaces:**
- Produces:
  - `grammar_triangulo.triangulos_candidatos(contexto, *, marcas: MarcasDaPagina) -> tuple[Triangulo, ...]`;
  - `grammar_triangulo.casa_triangulos(contexto, gramatica, *, candidatos) -> list[tuple[Caixa, int, tuple[int, ...]]]`;
  - o despacho de `split_triangle` em `_casar_no_contexto`, com os candidatos calculados uma vez por página e as `marcas` compartilhadas;
  - na fixture:
    - `CASOS_TRIANGULO: tuple[tuple[str, dict[str, Any]], ...]`: as 15 variantes de f02-18 v001–v015 e a gramática de cada uma, pela tabela de R-1;
    - as funções de desenho;
    - `desenhar_trafo_e05(page, grupo)`, que desenha o positivo no estilo que `pymupdf_transformers.observar_transformadores` reconhece (triângulo de traço com haste externa e, para `half_cyan`, preenchimento ciano). O teste de fusão da Task 4 usa essa função. Se o E05 não observar o desenho, corrige-se a fixture.

- [ ] **Step 1: Escrever a fixture e os testes,** partindo do patch vencedor.
  - **Positivos,** cada um nos 6 grupos:
    - triângulo girado a 0°, 30° e 90°;
    - meio ciano com os dois preenchimentos;
    - contorno;
    - com elipse ou círculo (inclusive girado, de 72 retas);
    - com X vermelho;
    - ligado por haste a uma linha;
    - página `/Rotate` 90;
    - página com texto em glifo.
  - **Negativos:**
    - triângulo verde sólido de um preenchimento só;
    - ponta de seta presa numa linha;
    - Δ de glifo;
    - triângulo roxo com S;
    - triângulo aberto, com 2 lados;
    - triângulo grande, acima de `max_span`;
    - círculo sem triângulo;
    - triângulo ciano inteiro, sem metade branca. Se o laboratório mostrar que esse desenho existe como transformador real, ele vira positivo, com o motivo no relatório.
  - **Testes:**
    - `test_positivo_casa_so_o_grupo_certo`: o desenho casa as variantes do grupo dele e nenhuma de outro;
    - `test_caixa_e_o_pictograma`;
    - `test_negativo_nao_casa`;
    - `test_componentes`;
    - `test_marcas_de_outro_contexto_recusa`: `ValueError`, pela guarda `marcas_do_contexto`;
    - `test_candidatos_de_outro_contexto_recusa`: `casa_triangulos(..., candidatos=)` com candidatos de outro contexto levanta `ValueError` (R-3);
    - `test_classificacao_uma_vez_por_candidato`: com as 15 variantes, o gasto é igual ao de 6 variantes, uma por grupo (R-6);
    - `test_trafo_e05_casa_a_gramatica_nova`: se a gramática recusar o desenho do E05, o teste fixa a recusa e o relatório diz isso, para a R-5.
- [ ] **Step 2: Rodar** e ver falhar sem o patch.
- [ ] **Step 3: Implementar** a partir do patch.
- [ ] **Step 4: Rodar:**
  - os testes novos, `tests/unit/test_grammar_*`, `tests/unit/test_symbol_matcher*.py`, `tests/unit/test_model_symbols*.py` e `tests/integration/test_model_symbols_runner.py`;
  - ruff, format, mypy e complexidade;
  - o benchmark e o diff, com as 15 habilitadas só no worktree e o JSON restaurado no fim (`task3-*`). Cole:
    - TRANSFORMADOR (tp/fp/fn) e a lista dos FP;
    - as leituras erradas;
    - a distribuição dos grupos;
    - o gasto máximo.
- [ ] **Step 5: Commit** (`feat: gramatica do transformador triangular`).

### Task 4: Habilitação de TRANSFORMADOR

**Estimativa:** 40 min · **Depende de:** Task 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-18.json` (v001–v015), `src/zeny_project_handler/adapters/analysis/model_symbols.py` (só `_VERSAO = "1.4.0"`)
- Modify: os testes de contagem e de versão da File Structure. Confirme com o grep da File Structure e liste no relatório cada arquivo e linha que mudou.
- Create: `tests/integration/test_model_symbols_trafo_runner.py`

**Interfaces:**
- Consumes: `CASOS_TRIANGULO` e `desenhar_trafo_e05`. Se não existirem com esses nomes, devolva ao orquestrador.
- Produces: 49 `enabled` e 374 `pending`; `declarative-drawing-model` 1.4.0.

- [ ] **Step 1: Atualizar os testes:**
  - as habilitadas passam a ser as de hoje ∪ os ids de `CASOS_TRIANGULO`;
  - `test_gramatica_real_igual_a_casos_triangulo`;
  - as contagens (374, 49) no auditor e na tabela de suporte;
  - o motor continua com 22, e o modelo passa a 49 com TRANSFORMADOR nas classes;
  - o golden das variantes antigas muda só nas 15;
  - o relato por estágio: f02-18 é do E05;
  - a versão 1.3.0 passa a 1.4.0 nos testes de perfil e de assinatura, com os nomes `1_3_0` renomeados para `1_4_0`.

  Em `test_model_symbols_trafo_runner.py`, com os pacotes reais no runner opt-in:
  - `test_uma_observacao_por_forma`: para cada um dos 6 grupos, o desenho da fixture dá **uma** observação de TRANSFORMADOR do modelo, com `referencias_possiveis` igual à lista do grupo;
  - `test_fusao_com_o_e05`: com `desenhar_trafo_e05`, primeiro afirma que o E05 e `declarative-drawing-model` observaram TRANSFORMADOR. Depois mede o resultado: uma ocorrência (funde), duas (não funde) ou "não se sobrepõem" (a gramática recusa o desenho). O teste **fixa o resultado observado** com uma asserção, sem disjunção. O relatório diz qual caso aconteceu, com os números de `_same_occurrence`.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Habilitar** as 15 com a gramática de `CASOS_TRIANGULO` e `negative_examples` = `confusable_negatives` do inventário, sem `reason`.
- [ ] **Step 4: Rodar:**
  - os arquivos alterados;
  - o auditor, que deve sair com `errors []` e 49;
  - `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_model_symbols.py` e `tests/unit/test_grammar_frames_ataque.py`;
  - ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: habilita transformador triangular sobre o modelo`).

### Task 5: Teto, guarda e pureza

**Estimativa:** 20 min · **Depende de:** Task 3 · **Risco:** normal · **Laboratório:** não

**Files:**
- Create: `tests/unit/test_grammar_triangulo_teto.py`
- Modify: `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py`

- [ ] **Step 1: Escrever os testes:**
  - página hostil, com milhares de triângulos e preenchimentos montados pelos construtores puros de `tests/fixtures/symbol_grammars/paginas.py`. O limite é o gasto só dos índices mais uma folga, e só a gramática fica dentro do `pytest.raises(TetoGramaticasExcedido)`;
  - linearidade do gasto com 10 e com 100 símbolos, conferindo os casamentos;
  - guarda de fonte (AST e tokenize) sobre `grammar_triangulo.py`, `tests/fixtures/symbol_grammars/triangulo.py`, `tests/unit/test_grammar_triangulo.py`, `tests/unit/test_gramatica_triangulo_tipo.py`, `tests/unit/test_model_symbols_formas_comuns.py` e `tests/unit/test_grammar_triangulo_teto.py`, em `_GRAMATICAS_NOVAS`. Fica de fora `tests/integration/test_model_symbols_trafo_runner.py`, que a Task 4 cria em paralelo; o testador de etapa o inclui;
  - `grammar_triangulo` na tupla de pureza.
- [ ] **Step 2: Rodar.** Falha de teto ou de linearidade é defeito da Task 3: reporte DONE_WITH_CONCERNS.
- [ ] **Step 3: Commit** (`test: teto, guarda e pureza da gramatica do transformador`).

### Task 6: Medição nas 16 folhas (orquestrador)

**Estimativa:** 20 min · **Depende de:** Tasks 1 a 5 e o testador de etapa · **Risco:** normal

- [ ] Rodar o benchmark `atual` e `modelo`, com `--saida <checkout principal>/tmp/e06-3-3-2-2/final` e `--processos 20`. Conferir:
  - R-4;
  - o `atual` igual ao de `tmp/e06-3-3-2-1/final`;
  - as demais classes do `modelo` iguais por folha;
  - a concordância das três classes da E06.3.3.2.1 igual (14/14);
  - a concordância de TRANSFORMADOR (nova).
- [ ] Triagem em render dos FP de TRANSFORMADOR, das leituras erradas e de uma amostra de 6 tp, um por grupo, com o grupo conferido.
- [ ] Diff (`--saida .../final-diff`) igual ao congelado, com o gasto máximo.
- [ ] Auditor: `errors []` e 49.

## Fechamento operacional

- Suíte inteira por onda; testador de etapa; `osv-scanner` nos 7 locks; `check_test_integrity --base 264d4cb`; revisão final; `.\IniciarTestes.bat`.
- Handoff com:
  - a tabela de TRANSFORMADOR (`atual` e `modelo`) e a triagem dos FP;
  - a distribuição dos grupos de forma e o gasto;
  - em "Decisões para o usuário":
    - R-2, o representante de `variante_inventario`;
    - R-4, o critério reinterpretado;
    - o resultado da R-5;
    - a contagem de 49 habilitadas;
    - os transformadores reais sem anotação, para a curadoria;
  - "Para a E07": R-2, a lista em `referencias_possiveis`, e a fusão com o E05;
  - "Para a E06.3.4": o estai, com a mesma estratégia de grupos se houver formas comuns.
