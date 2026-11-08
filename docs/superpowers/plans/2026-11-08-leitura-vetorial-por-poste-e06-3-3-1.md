# E06.3.3.1 — Para-raios BT: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** reconhecer PARA_RAIOS_BT (retângulo atravessado por diagonal) sobre o modelo de desenho, onde o analisador atual não casa nenhuma das 10 referências, sem leitura errada de fato e sem mexer nas classes já reconhecidas.

**Architecture:** mesmo desenho da haste da E06.3.2.2: um tipo de gramática só do modelo (`rect_diagonal`), executado só pelo método `declarative-drawing-model` no runner opt-in. A envolvente, o X de retirada, a cor canônica, o sinal da página (origem predominante do texto) e as marcas da página calculadas uma vez saem de `grammar_stem.py` para um módulo comum (`grammar_marcas.py`), usado pelas duas gramáticas, sem mudar a saída da haste; cada gramática mantém a própria tabela de perfil por origem. A gramática nova vive em `grammar_rect_diagonal.py`; a caixa é o pictograma (envolvente quando há, senão o retângulo com a diagonal), e os demais caminhos entram como componentes.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só adaptadores, scripts e fixtures), JSON + JSON Schema, pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3", "E06.3.3" (divisão) e "E06.3.3.1"; o handoff da E06.3.2.2 (padrão de tipo só do modelo, pictograma, componentes, perfil por página, folga de orçamento); o plano `docs/superpowers/plans/2026-11-07-leitura-vetorial-por-poste-e06-3-2-2.md` (decisões R-E06.3.2-2 a 10, que esta etapa replica); ADR 0016 e 0006.

## Global Constraints

- Arquitetura hexagonal; o núcleo `drawing_model/` não importa PyMuPDF; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- Nenhuma migração, API ou DTO. O método sobre o modelo liga só no runner opt-in (D12); o analisador padrão não muda.
- ADR 0006: `declarative-drawing-model` 1.1.0 → 1.2.0 no mesmo commit da habilitação (Task 4), que é quando a saída muda. O motor antigo não executa tipo só do modelo (`variantes_do_motor`).
- Sem dependência nova.
- Fixture sintética autoral positiva e negativa; nenhuma coordenada, hash ou nome de folha real em código, pacote, fixture ou teste (a guarda de fonte por AST da E06.3.2.2 é estendida ao módulo novo).
- Nada lê `examples/avaliacao-cega/`; as referências da rodada E03 estão congeladas; leitores visuais não participam.
- Pytest com `--strict-markers` e `ResourceWarning` como erro; testes sem dependência de ordem, cwd, porta ou arquivo fixo; mypy strict, ruff, format, complexidade < 31.
- Não tocar `scripts/benchmark_ficha_poste.py` nem `tests/conftest.py`.
- Worktree da etapa com `.venv`; em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` da etapa; a suíte inteira usa `-n` = 20 ÷ suítes ativas.

## Review Focus

1. Retângulo girado com a diagonal que passa além dele (com ou sem ganchos nas pontas), dentro de elipse ou sem ela, com ou sem X → casa a variante certa, com a caixa do pictograma; a diagonal com ganchos e a haste de ligação **não** formam um X falso (v002 não vira v003) (Task 3).
2. Retângulos com uma diagonal que não são para-raios: TORRE_AT (`framed_diagonals`, duas diagonais canto a canto), moldura de rótulo com traço, moldura de tabela, losango → não casam (Task 3).
3. A haste já reconhecida (ATERRAMENTO, PARA_RAIOS_MT) e as 22 variantes do motor continuam com a mesma saída depois da extração das marcas (Task 2, conferido pelo orquestrador antes do laboratório) e da gramática nova (Task 6).
4. Página hostil com muitos quadriláteros e diagonais → `TetoGramaticasExcedido` pelo orçamento (Task 5).
5. Um mesmo desenho casa no máximo uma das 4 variantes de situação (Task 3).
6. PARA_RAIOS_BT desenhado no estilo clássico (haste alinhada ao corpo, que `_bt_arrester_matches` do legado reconhece) no runner opt-in → uma ocorrência só, ou a ruling de que não funde (Task 4).

## Decisões do plano

- **R-E06.3.3.1-1, tipo `rect_diagonal`:** campos exatos `{"kind": "rect_diagonal", "enclosure": "none" | "ellipse", "removal_mark": bool, "max_span": número em (0, 72]}`, no validador de `declarative_symbols.py`, no schema `docs/schemas/pacotes-simbologia.schema.json` e em `GRAMATICAS_SO_MODELO`. Situações: v001 base (`none`/false), v002 envolvente (`ellipse`/false), v003 envolvente e X (`ellipse`/true), v004 X sem envolvente (`none`/true). A cor não decide nada.
- **R-E06.3.3.1-2, marcas compartilhadas:** `drawing_model/grammar_marcas.py` recebe só o que é de fato comum, com os mesmos valores e a mesma semântica de hoje:
  - o sinal da página (`origem_predominante`);
  - a cor canônica;
  - os contornos e a envolvente (Bézier e poligonal elíptica);
  - o X de retirada (braços como traço solto, cores comparadas entre si, pares pagos).

  As interfaces generalizam os parâmetros de hoje, sem semântica nova:
  - `envolvente(contornos, exigidos: Sequence[Ponto], escala: float, ancora: Ponto, proprios: frozenset[int]) -> Contorno | None`. Todos os `exigidos` dentro da elipse, diâmetro em `_ENVOLVENTE × escala` e os caminhos `proprios` excluídos;
  - `tem_x(contexto, pictograma: Caixa, escala: float, eixo: float, proprios: frozenset[Segmento]) -> tuple[Segmento, Segmento] | None`, sem parâmetro de cor.

  Cada gramática fica com a própria tabela `Perfil` por origem: a da haste continua em `grammar_stem.py`. `grammar_stem.py` reexporta de forma explícita (`X as X`) o que os testes importam dele. A saída da haste não muda:
  - prova nos testes da haste;
  - prova no benchmark que o orquestrador roda sobre a Onda A integrada, antes do laboratório, com as demais classes iguais às de `tmp/e06-3-2-2/simbolos/simbolos-ficha.json`.

  Resolve também o achado da E06.3.2.2 sobre `Haste` expor `_Contorno` e os imports de privados. Alternativas descartadas (desvio da nota da E06.3.3, que citava `grammar_frames.py`):
  - estender `framed_diagonals` com uma diagonal, que levaria a gramática ao motor antigo;
  - pôr a gramática em `grammar_frames.py`, que guarda os limiares do motor.

  A nota da E06.3.3.2 fica desatualizada nesse ponto.
- **R-E06.3.3.1-3, caixa, haste e componentes:** a caixa é o pictograma: a envolvente quando há, senão o retângulo unido à diagonal. O X não entra na caixa. A haste de ligação **não é exigida** pela gramática e também não entra na caixa. Quando existe (traço que sai do retângulo ou da envolvente rumo ao poste), entra nos `componentes`, junto com retângulo, diagonal, ganchos, envolvente e X, sem repetir a âncora. O conjunto `proprios` do X contém retângulo, diagonal, ganchos e haste de ligação.
- **R-E06.3.3.1-4, critério de aceite** (com a lição da E06.3.2.2, uma definição só):
  - PARA_RAIOS_BT com tp ≥ 1 e precisão ≥ 50% (fp ≤ tp). A precisão do `atual` é `n/d` (0/0/10), e o piso é decisão deste plano: vai a "Decisões para o usuário". A precisão medida contra a ficha é um limite inferior, porque a ficha só anota símbolo associado a poste;
  - leitura errada afirmada **de fato** = 0, com triagem visual das leituras erradas e dos FP de PARA_RAIOS_BT, como na E06.3.2.2;
  - as demais classes do `modelo` iguais, por folha, às de `tmp/e06-3-2-2/simbolos/simbolos-ficha.json`;
  - diff núcleo × motor igual ao congelado da E06.2.2.2.
  - Gasto máximo por folha: alvo ≤ 200.000 (a 016 já gasta 187.659). Os contornos e o sinal da página são calculados uma vez por contexto e compartilhados pelas duas gramáticas: `MarcasDaPagina` (Task 2) é preguiçoso, e numa página só com haste o gasto não muda, porque os contornos só são pagos quando alguém os pede. Se ainda passar, a ruling sobe o alvo de medição com o valor no handoff e registra que isso corrói a folga de 10× da R-E06.2.2.2-4. `LIMITE_CONSULTAS_PAGINA` (2.000.000) não muda.
- **R-E06.3.3.1-5, referências suspeitas:** a 006 `P8-para-raios` (rotulada PARA_RAIOS_MT) é um retângulo com diagonal; uma predição de PARA_RAIOS_BT ali é leitura certa pelo inventário, e a triagem a classifica como troca de rótulo. O handoff a soma à lista da curadoria.
- **R-E06.3.3.1-6, fusão com o legado:** para PARA_RAIOS_BT, a caixa do legado é a união de haste, corpo e diagonal (`pymupdf_symbols.py:894`, fora de `_PICTOGRAM_CLASSES`). `_same_occurrence` exige centro e tamanho próximos, então com a caixa do pictograma a fusão provavelmente não acontece. Não se mexe no legado: isso quebraria "`atual` igual ao congelado" e pediria versão nova dele pelo ADR 0006.

  A Task 4 mede em teste de runner, com um desenho que satisfaça as duas regras (a do legado e a da gramática nova), e registra um de três resultados:
  - funde;
  - não funde: duas ocorrências aceitas no runner opt-in até a E09, com o handoff "Para a E07";
  - nenhum desenho satisfaz as duas regras: "o legado e o modelo não se sobrepõem", também registrado.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`, `docs/schemas/pacotes-simbologia.schema.json` | tipo `rect_diagonal` | 1 |
| `tests/unit/test_gramatica_rect_diagonal_tipo.py` (novo) | validação, schema, motor ignora, perfil do modelo conta | 1 |
| `tests/unit/test_gramatica_so_modelo.py:169`, `tests/unit/test_habilitacao_hastes_ataque.py:102` | só a asserção de `GRAMATICAS_SO_MODELO` (passa a conter `stem_bars` e `rect_diagonal`) | 1 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_marcas.py` (novo), `drawing_model/grammar_stem.py` | marcas compartilhadas | 2 |
| `src/zeny_project_handler_server/symbol_execution.py` | `grammar_marcas` (2) e `grammar_rect_diagonal` (3) no digest | 2, 3 |
| `tests/unit/test_grammar_marcas.py` (novo) | envolvente, X, origem predominante, cor e marcas da página preguiçosas, isolados | 2 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_rect_diagonal.py` (novo), `drawing_model/symbol_matcher.py` | gramática e despacho | 3 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | `_VERSAO = "1.2.0"` | 4 |
| `tests/fixtures/symbol_grammars/rect_diagonal.py` (novo), `tests/unit/test_grammar_rect_diagonal.py` (novo) | fixture, gramática | 3 |
| `tests/unit/test_model_symbols.py` | versão 1.2.0 | 4 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-21.json` (v001–v004) | habilitação | 4 |
| `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py`, `tests/unit/test_gramatica_so_modelo_ataque.py`, `tests/unit/test_habilitacao_hastes_ataque.py` | contagens 30→34 e 393→389, motor 22 e modelo 34 | 4 |
| `tests/unit/test_model_symbols_componentes_ataque.py`, `tests/integration/test_haste_costuras_etapa_testador.py`, `tests/integration/test_model_symbols_haste_ataque.py` | versão 1.1.0 → 1.2.0 nas asserções de perfil e assinatura | 4 |
| `tests/integration/test_model_symbols_bt_runner.py` (novo) | fusão de PARA_RAIOS_BT com o legado no runner (R-6) | 4 |
| `tests/unit/test_grammar_rect_diagonal_teto.py` (novo), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py` | teto, guarda e pureza | 5 |

Ondas: Onda A, Tasks 1 e 2 (arquivos disjuntos); laboratório sobre a Onda A integrada; Task 3; Onda B, Tasks 4 e 5; Task 6 (medição, orquestrador).

Soma: 3h05 (25 + 35 + 45 + 40 + 20 + 20), mais o laboratório (caixa de 60 min). O relógio começa em 80cfff2; vale a regra de estouro de 4h30 do protocolo (a E06.3.2.2 levou 3h36 com o mesmo formato).

## Laboratório (depois da Onda A)

- **Antes do laboratório:** o orquestrador roda o benchmark `--metodo modelo` na Onda A integrada e confere as demais classes contra `tmp/e06-3-2-2/simbolos/simbolos-ficha.json`, para atribuir à Task 2 qualquer mudança da haste.
- **Regra:** o patch de hipótese não toca `grammar_marcas.py` nem `grammar_stem.py`. Se precisar, a hipótese descreve a mudança em `conclusoes.md`, e uma Task 2b de refatoração (com prova de invariância da haste e ruling) entra antes da Task 3.
- **Base:** a branch da etapa com a Onda A integrada. Cada hipótese: um `desenvolvedor` com `isolation: "worktree"`, sem commit e sem a suíte inteira, que implementa `grammar_rect_diagonal.py` e o despacho (R-1, R-3) com as marcas de `grammar_marcas.py`, habilita as 4 variantes no JSON só no worktree, escreve testes focados com os positivos e negativos do Review Focus 1, 2 e 5, e mede.
- **Hipóteses:**
  - **H-1, moldura primeiro:** candidatos de `contexto.molduras` (retângulo) mais quadrilátero fechado girado das polilinhas; a diagonal é um segmento que cruza o retângulo de ponta a ponta e passa além dele.
  - **H-2, diagonal primeiro:** cada segmento de comprimento plausível que atravessa um quadrilátero fechado (consulta à grade) é semente; o quadrilátero precisa ter a proporção do para-raios (lado maior/menor entre 2 e 4,5, como o legado; a faixa final é a do laboratório).
  - **H-3, envolvente primeiro:** a elipse de `grammar_marcas` é semente para v002/v003; dentro dela, quadrilátero e diagonal. Para v001/v004 (sem envolvente), cai em H-2.
  - Todas usam o sinal da página (`origem_predominante`) e as `MarcasDaPagina` de `grammar_marcas`, com a própria tabela de perfil por origem dentro de `grammar_rect_diagonal.py`.
- **Comandos** (no worktree da hipótese, `.venv` da etapa e `PYTHONPATH=<worktree>/src`, `--processos 6`; `<rodada E03>` = `<checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas`): `python -m scripts.benchmark_simbolos_ficha --rodada <rodada E03> --saida <checkout principal>/tmp/laboratorio/e06-3-3-1/<hipotese>/iter-<k> --metodo modelo --processos 6`; no fim, `python -m scripts.diff_simbolos_nucleo_motor ... --saida .../diff-<k> --processos 6` para o gasto.
- **Métrica:** `total.modelo.centro.por_classe.PARA_RAIOS_BT` (tp/fp/fn); `leituras_erradas.por_classe.PARA_RAIOS_BT`; as outras classes iguais às de `tmp/e06-3-2-2/simbolos/simbolos-ficha.json`; gasto máximo e `gasto_motivo`; tempo máximo por folha.
- **Vitória:** maior F1 de PARA_RAIOS_BT, com quatro condições: leitura errada de fato = 0 (triagem rápida das leituras erradas e dos FP da hipótese), precisão ≥ 50%, outras classes intactas e gasto ≤ 200.000. Se nenhuma hipótese ficar no gasto, escolhe-se pela qualidade e aplica-se R-4. Desempate: menor gasto.
- **Parada:** 60 min por hipótese, ou 8 tp ou mais com 0 leitura errada de fato.
- **Entrega:** `tmp/laboratorio/e06-3-3-1/<hipotese>/`: `patch.diff`, `metricas.json` e `conclusoes.md`.

## Tasks

### Task 1: Tipo `rect_diagonal`

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`, `docs/schemas/pacotes-simbologia.schema.json`
- Modify (só a asserção de `GRAMATICAS_SO_MODELO`): `tests/unit/test_gramatica_so_modelo.py:169`, `tests/unit/test_habilitacao_hastes_ataque.py:102`
- Create: `tests/unit/test_gramatica_rect_diagonal_tipo.py`

**Interfaces:**
- Produces: `rect_diagonal` em `_GRAMMARS`, no validador (com `isinstance` antes de `in`, como a correção da E06.3.2.1) e em `GRAMATICAS_SO_MODELO`; ramo do schema.
- Também muda: só a asserção de `GRAMATICAS_SO_MODELO` em `tests/unit/test_gramatica_so_modelo.py:169` e em `tests/unit/test_habilitacao_hastes_ataque.py:102` (o conjunto passa a `{"stem_bars", "rect_diagonal"}`); o resto desses arquivos não é desta tarefa.

- [ ] **Step 1: Escrever os testes** com pacotes em `tmp_path` (`carregar_pacotes(packages_dir=tmp_path)`): `test_rect_diagonal_valido_carrega` (as 4 combinações), `test_rect_diagonal_invalido_recusa` (campo a mais ou a menos, `enclosure` desconhecido ou lista, `removal_mark` não booleano, `max_span` 0, 73, NaN ou booleano), `test_schema_tem_o_ramo_rect_diagonal` (estrutural, sem biblioteca, como o da `stem_bars`), `test_motor_ignora_rect_diagonal` (o motor não a observa nem a anuncia) e `test_perfil_do_modelo_anuncia_rect_diagonal`.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar** o arquivo, `tests/unit/test_gramatica_so_modelo*.py`, `tests/unit/test_habilitacao_hastes_ataque.py`, `tests/unit/test_declarative_symbol_packages.py`, o auditor (`errors []`), ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: tipo de gramatica rect_diagonal so do modelo`).

### Task 2: Marcas compartilhadas

**Estimativa:** 35 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_marcas.py`, `tests/unit/test_grammar_marcas.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_stem.py`, `src/zeny_project_handler_server/symbol_execution.py`

**Interfaces:**
- Produces, em `grammar_marcas.py` (nomes públicos): `origem_predominante(modelo) -> str`, `cor_canonica(cor, preenchimento) -> str | None`, `Contorno` (caixa e caminho), `contornos(contexto) -> GradeEspacial[Contorno]`, `envolvente(contornos, exigidos: Sequence[Ponto], escala: float, ancora: Ponto, proprios: frozenset[int]) -> Contorno | None` e `tem_x(contexto, pictograma: Caixa, escala: float, eixo: float, proprios: frozenset[Segmento]) -> tuple[Segmento, Segmento] | None` (R-2: generalização dos parâmetros de hoje, sem cor); e `MarcasDaPagina(contexto)`, preguiçoso, com a `origem` predominante e a propriedade `contornos`, calculada e paga uma vez, só quando alguém a pede. `hastes_candidatas(contexto, *, marcas: MarcasDaPagina | None = None)` usa as marcas recebidas ou cria as suas; com `None`, o comportamento e o gasto são os de hoje. Os limiares da envolvente, do X e `_TOLERANCIA_COR` mudam de módulo sem mudar de valor. `Perfil` e a tabela por origem da haste ficam em `grammar_stem.py`, com `perfil_da_pagina` usando `origem_predominante` de `grammar_marcas`. `grammar_stem.py` reexporta de forma explícita (`X as X`) o que `tests/unit/test_grammar_stem*.py` importa dele (por exemplo `origem_predominante`), por causa do mypy strict.

- [ ] **Step 1: Escrever** `test_grammar_marcas.py` com os casos isolados (envolvente Bézier e poligonal, nas bordas de 8 vértices e desvio 0,2; X com braço solto e com braço em contorno; cor canônica e tolerância; origem predominante; `MarcasDaPagina` paga os contornos uma vez e não os paga se ninguém pedir), movendo para cá, sem enfraquecer, os casos equivalentes que hoje testam esses helpers por dentro da haste, se houver.
- [ ] **Step 2: Rodar** e ver falhar (módulo ausente).
- [ ] **Step 3: Extrair** para `grammar_marcas.py` e fazer `grammar_stem.py` importar dele; `Haste` deixa de expor tipo privado; `grammar_marcas` entra no digest do runner.
- [ ] **Step 4: Rodar** `tests/unit/test_grammar_stem*.py`, `tests/unit/test_grammar_marcas.py`, `tests/integration/test_model_symbols_runner.py` (fecho do digest), `tests/unit/test_symbol_matcher*.py`, ruff, format, mypy e `scripts/complexity_gate.py src`. Nenhum teste da haste muda.
- [ ] **Step 5: Commit** (`refactor: marcas compartilhadas das gramaticas do modelo`).

### Task 3: Gramática `rect_diagonal`

**Estimativa:** 45 min · **Depende de:** laboratório (sobre as Tasks 1 e 2) · **Risco:** alto · **Laboratório:** sim

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_rect_diagonal.py`, `tests/fixtures/symbol_grammars/rect_diagonal.py`, `tests/unit/test_grammar_rect_diagonal.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`, `src/zeny_project_handler_server/symbol_execution.py` (digest)

**Interfaces:**
- Produces: `grammar_rect_diagonal.casa_retangulos_diagonal(contexto, gramatica, *, candidatos=None) -> list[tuple[Caixa, int, tuple[int, ...]]]`; despacho de `rect_diagonal` em `_casar_no_contexto`, com os candidatos calculados uma vez por página (como `hastes_candidatas`); `_casar_no_contexto` cria uma `MarcasDaPagina` (Task 2) e a passa às duas gramáticas (`hastes_candidatas(contexto, marcas=...)`), sem mudar o gasto de uma página só com haste (R-4); a docstring de `CasamentoGramatica.componentes` (`symbol_matcher.py:54-55`, "só a haste com barras os preenche") passa a citar as duas gramáticas; a fixture exporta `CASOS_RECT_DIAGONAL: tuple[tuple[str, dict[str, Any]], ...]` (as 4 variantes de f02-21 v001–v004 e a gramática de cada uma), as funções de desenho e `desenhar_bt_classico(page, situacao)`. Esta última desenha o positivo no estilo do legado: haste alinhada ao corpo retangular de proporção 2–4,5, diagonal de 0,55 a 1,15 × a haste, centrada no corpo e passando além dele. O teste de fusão da Task 4 usa essa função.

- [ ] **Step 1: Fixture e testes**, partindo do patch vencedor: positivos (retângulo girado 0°, 30°, 90° com diagonal além do retângulo, com e sem ganchos; com elipse; com X; com os dois; ligado por haste a uma linha longa; página `/Rotate` 90; página com texto em glifo e símbolo pequeno) e negativos (TORRE_AT com duas diagonais; moldura de rótulo com texto; retângulo com diagonal que não passa além; diagonal sem retângulo; losango; retângulo com proporção fora da faixa escolhida no laboratório; **X falso**: diagonal com ganchos mais haste de ligação, em elipse sem X, não pode virar v003). `test_positivo_casa_so_a_variante_certa` (4 variantes × rotações), `test_caixa_e_o_pictograma`, `test_negativo_nao_casa`, `test_componentes`, `test_bt_classico_casa_a_gramatica_nova` (se a faixa do laboratório recusar o desenho clássico, o teste fixa a recusa e o relatório o diz, para a R-6).
- [ ] **Step 2: Rodar** e ver falhar sem o patch.
- [ ] **Step 3: Implementar** a partir do patch.
- [ ] **Step 4: Rodar** os testes novos, `tests/unit/test_grammar_*`, `tests/unit/test_symbol_matcher*.py`, `tests/unit/test_model_symbols*.py`, `tests/integration/test_model_symbols_runner.py`, ruff, format, mypy e complexidade; e o benchmark (com as 4 habilitadas só no worktree, JSON restaurado no fim), colando a métrica de PARA_RAIOS_BT, as leituras erradas e o gasto máximo do diff.
- [ ] **Step 5: Commit** (`feat: gramatica do retangulo com diagonal`).

### Task 4: Habilitação de PARA_RAIOS_BT

**Estimativa:** 40 min · **Depende de:** Task 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-21.json` (v001–v004), `src/zeny_project_handler/adapters/analysis/model_symbols.py` (só `_VERSAO = "1.2.0"`)
- Modify: `tests/unit/test_model_symbols.py` (versão, inclusive `:591` e `:1238`), `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_pacotes_classes_da_ficha.py`, `tests/server/test_e14_symbol_review.py`, `tests/unit/test_gramatica_so_modelo_ataque.py`, `tests/unit/test_habilitacao_hastes_ataque.py`, `tests/unit/test_model_symbols_componentes_ataque.py` (`:136-139`), `tests/integration/test_haste_costuras_etapa_testador.py` (`:71-75`, inclusive a comparação com `replace(..., versao=...)`), `tests/integration/test_model_symbols_haste_ataque.py` (`:143-147`)
- Create: `tests/integration/test_model_symbols_bt_runner.py`

**Interfaces:**
- Consumes: `CASOS_RECT_DIAGONAL` — se não existir com esse nome, devolva ao orquestrador.
- Produces: 34 `enabled` e 389 `pending`; `declarative-drawing-model` 1.2.0 (`test_versao_1_2_0`, no lugar do teste da 1.1.0).

- [ ] **Step 1: Atualizar os testes:** habilitadas = `_ENABLED_IDS` ∪ hastes ∪ ids de `CASOS_RECT_DIAGONAL`; `test_gramatica_real_igual_a_casos_rect_diagonal`; contagens (389, 34) no auditor e na tabela de suporte; o motor continua com 22 e o modelo passa a 34 com PARA_RAIOS_BT nas classes; o golden das variantes antigas muda só nas 4; famílias só `pending` e relato por estágio (E04 passa a 12 habilitadas). Em `test_habilitacao_hastes_ataque.py`:
  - `test_as_quatro_situacoes_de_cada_familia_sao_distintas` passa a filtrar por `kind == "stem_bars"`;
  - `test_variantes_nao_habilitadas_das_duas_familias_seguem_pending_com_razao` deixa de exigir `pending` em f02-21 v001–v004.

  A versão passa de 1.1.0 a 1.2.0 nos três arquivos de ataque listados. Em `test_model_symbols_bt_runner.py`:
  - roda `desenhar_bt_classico` (fixture da Task 3), nas 4 situações, com os pacotes reais, no runner opt-in;
  - primeiro afirma que as duas assinaturas observaram PARA_RAIOS_BT na página: o legado e `declarative-drawing-model`;
  - só então julga: uma ocorrência com os dois métodos (funde) ou duas ocorrências (não funde, ruling de R-6);
  - se a gramática nova recusar o desenho clássico (Task 3), o teste fixa "o legado e o modelo não se sobrepõem" e não alega fusão.

  Diga qual caso aconteceu no relatório, com os números de `_same_occurrence`.
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Habilitar** as 4 com a gramática de `CASOS_RECT_DIAGONAL` e `negative_examples` = `confusable_negatives` do inventário, sem `reason`.
- [ ] **Step 4: Rodar** os alterados, o auditor (`errors []`, 34), `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_model_symbols.py`, `tests/unit/test_grammar_frames_ataque.py`, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: habilita para-raios BT sobre o modelo`).

### Task 5: Teto, guarda e pureza

**Estimativa:** 20 min · **Depende de:** Task 3 · **Risco:** normal · **Laboratório:** não

**Files:**
- Create: `tests/unit/test_grammar_rect_diagonal_teto.py`
- Modify: `tests/unit/test_symbol_packages_sem_memorizacao.py`, `tests/unit/test_symbol_matcher_paridade.py`

- [ ] **Step 1:** página hostil (milhares de quadriláteros e diagonais, construtores puros de `tests/fixtures/symbol_grammars/paginas.py`), com o limite = gasto só dos índices + folga e só a gramática dentro do `pytest.raises(TetoGramaticasExcedido)`; linearidade do gasto com 10 e 100 símbolos, conferindo os casamentos; guarda de fonte (AST e tokenize) sobre `grammar_rect_diagonal.py`, `grammar_marcas.py` e a fixture nova; `grammar_rect_diagonal` e `grammar_marcas` na tupla de pureza.
- [ ] **Step 2: Rodar**; falha de teto ou linearidade é defeito da Task 3: reporte DONE_WITH_CONCERNS.
- [ ] **Step 3: Commit** (`test: teto, guarda e pureza da gramatica do retangulo com diagonal`).

### Task 6: Medição nas 16 folhas (orquestrador)

**Estimativa:** 20 min · **Depende de:** Tasks 1 a 5 · **Risco:** normal

- [ ] Benchmark `atual` e `modelo` (`--saida <checkout principal>/tmp/e06-3-3-1/simbolos`, `--processos 10`): R-4; `atual` igual ao congelado; as demais classes do `modelo` iguais às de `tmp/e06-3-2-2/simbolos` por folha.
- [ ] Triagem visual das leituras erradas e dos FP de PARA_RAIOS_BT (render em alta resolução das caixas).
- [ ] Diff (`--saida .../tmp/e06-3-3-1/diff`) igual ao congelado; gasto máximo e `gasto_motivo`.
- [ ] Auditor → `errors []`, 34.

## Fechamento operacional

- Suíte inteira por onda; testador de etapa (a Task 5 é de risco normal); `osv-scanner` nos 7 locks; `check_test_integrity --base <base da etapa>`; revisão final; `.\IniciarTestes.bat`.
- Handoff com a tabela, a triagem, o gasto, as decisões que mudam o visível (consumidores de `enabled` com 34; referências suspeitas para a curadoria) e o bloco "Para a E06.3.3.2".
