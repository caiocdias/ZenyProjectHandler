# E06.3.2.1 — Base da haste, leituras erradas e H2: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** preparar o tipo de gramática `stem_bars`, que só o método sobre o modelo de desenho executa; medir a leitura errada afirmada no benchmark de símbolos; e confirmar ou refutar a H2 com a contagem de resíduos raster por folha.

**Architecture:** `stem_bars` passa a ser aceito na validação dos pacotes e no schema publicado, mas o motor antigo (`declarative-vector-packages`, que sai na E09) o ignora ao observar e ao anunciar classes; o perfil do método sobre o modelo (`declarative-drawing-model`) anuncia todas as variantes habilitadas. Nenhuma variante é habilitada aqui: a gramática e a habilitação são da E06.3.2.2. O benchmark de símbolos ganha a contagem de leituras erradas afirmadas, e um script novo mede os resíduos raster por folha para a H2.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só nos adaptadores e scripts), JSON + JSON Schema (documento), pytest (xdist), mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.3", "E06.3.2" (divisão) e "E06.3.2.1"; os blocos "Para a E06.3" dos handoffs da E06.2.2.1 (H2) e da E06.3.1; ADR 0016. Este plano foi recortado do plano da E06.3.2, revisado nas rodadas 0 e 1 (ledger), com os achados N1, N2 e M-b da rodada 1 aplicados.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF; o núcleo `drawing_model/` não importa PyMuPDF; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- Nenhuma migração SQLite, nenhuma mudança de API ou DTO. O analisador padrão não muda; o método sobre o modelo liga só no `SymbolCompositionRunner` opt-in (D12).
- Mudança de comportamento de saída incrementa a versão do método (ADR 0006). Aqui nenhum método muda de saída com os pacotes atuais (nenhuma `stem_bars` habilitada), e os perfis mantêm a ordem dos `parametros` para a assinatura deles não mudar à toa. A assinatura do runner opt-in muda mesmo assim, porque `declarative_symbols.py`, `model_symbols.py` e `symbol_matcher.py` estão no digest dele: cache miss esperado.
- Sem dependência nova em nenhum lock.
- PDFs reais, recortes e conjuntos de dados nunca entram no Git. Fixture sintética autoral positiva e negativa; nenhuma coordenada, hash ou nome de folha real em código ou teste.
- Nada lê `examples/avaliacao-cega/`. As referências da rodada E03 (`tmp/curadoria-simbologia/20261103-2300-fichas/`) estão congeladas.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos. Testes sem dependência de ordem, cwd, porta ou arquivo fixo (use `tmp_path`). mypy strict, ruff check, ruff format, complexidade < 31 em `src`.
- Não tocar `scripts/benchmark_ficha_poste.py` (E15) nem `tests/conftest.py`.
- Worktree da etapa: `.venv/Scripts/python.exe`. Em onda, `PYTHONPATH=<worktree da tarefa>/src` com o `.venv` do worktree da etapa, a partir da raiz do worktree da tarefa; a suíte inteira usa `-n` = 20 ÷ suítes ativas (o despacho informa o número).

## Review Focus

1. Pacote com variante `enabled` de tipo `stem_bars` carregado pelo motor antigo → carrega, o motor não a observa nem a conta em `classes_suportadas`, e continua observando a `label_in_frame` ao lado; o perfil do método sobre o modelo a conta (Task 1).
2. Gramática `stem_bars` com um par `bars`/`taper` fora dos dois válidos, campo a mais ou `max_span` fora de (0, 72] → recusada pelo validador e fora do schema (Task 1).
3. Predição não casada com centro na caixa de uma referência de outra classe → conta como leitura errada; predição casada ou longe de qualquer referência → não conta (Task 3).
4. Resíduo raster em página `FORA_DOMINIO` ou com imagens que falharam → fica fora da contagem por folha, com o motivo, e não vira "0 resíduos" (Task 2).
5. Referência de símbolo sob uma imagem grande (fora da faixa de `residuos_raster`) → listada para triagem (Task 2).

## Decisões do plano

- **R-E06.3.2-1, tipo só do modelo:** `stem_bars` entra em `declarative_symbols._GRAMMARS`, no validador de campos e no schema `docs/schemas/pacotes-simbologia.schema.json` (ramo novo do `oneOf`), e numa constante pública nova `GRAMATICAS_SO_MODELO = frozenset({"stem_bars"})`. O motor antigo observa e anuncia só `variantes_do_motor(pacotes)` (habilitadas fora de `GRAMATICAS_SO_MODELO`); `_enabled` continua devolvendo todas. `perfil_pacotes_modelo` calcula `classes_suportadas` e `("enabled_variants", n)` a partir de `_enabled`, sem herdá-los do motor: sem isso, o domínio recusaria a observação de haste por falta de cobertura. Os testes de paridade núcleo × motor comparam só `variantes_do_motor`. Descartado: portar a gramática também para o motor antigo (sai na E09). Dívida para a E09: `GRAMATICAS_SO_MODELO` e a validação dos pacotes moram em `declarative_symbols.py`.
- **R-E06.3.2-2, campos da gramática** (exatos): `{"kind": "stem_bars", "bars": 3 | 4, "taper": "decreasing" | "alternating", "enclosure": "none" | "ellipse", "removal_mark": bool, "max_span": número em (0, 72]}`. Só os pares `bars` 3 com `decreasing` e `bars` 4 com `alternating` são válidos. O validador não amarra `class_code` a `bars` (o auditor confere a classe contra o inventário).
- **R-E06.3.2-3 (parte desta etapa):** `CasamentoGramatica` ganha `componentes: tuple[int, ...] = ()` (posições em `modelo.caminhos` dos demais caminhos do símbolo); as gramáticas atuais deixam vazio. Quem o preenche e o consome é a E06.3.2.2.
- **R-E06.3.2-4 (parte desta etapa), leitura errada afirmada:** uma predição **não casada** (FP no critério do benchmark) cujo centro cai na caixa, com a mesma tolerância do critério `centro`, de uma referência de **outra** classe. A predição casada é leitura certa e não conta. O benchmark grava, por método, a lista e o total, somados por classe da predição, família e folha. A E06.3.2.2 exige 0 em ATERRAMENTO e PARA_RAIOS_MT.
- **R-E06.3.2-7, H2:** é confirmada se nenhum resíduo das 16 folhas for símbolo da rede, pela triagem visual dos recortes (o orquestrador lê os PNG; hash repetido é triado uma vez) e pelo cruzamento com as referências. Página `FORA_DOMINIO` ou com imagens que falharam não conta como zero. Como `residuos_raster` só vê imagem compacta (4–72 pt) fora de mosaico, o script também lista as referências de símbolo cujo centro cai sob **qualquer** imagem (`referencias_sob_imagem`); todas são triadas (devem ser poucas). A medição usa as variantes habilitadas de hoje (a haste ainda não está habilitada): um casamento só tira resíduo, então a contagem fica, no máximo, maior, o lado conservador para a H2.

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/declarative_symbols.py` | `stem_bars` na validação, `GRAMATICAS_SO_MODELO`, `variantes_do_motor` no motor | 1 |
| `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` | `CasamentoGramatica.componentes` | 1 |
| `src/zeny_project_handler/adapters/analysis/model_symbols.py` | perfil com todas as habilitadas | 1 |
| `docs/schemas/pacotes-simbologia.schema.json` | ramo `stem_bars` | 1 |
| `tests/unit/test_gramatica_so_modelo.py` (novo) | validação, schema estrutural, motor ignora, perfil do modelo conta | 1 |
| `tests/unit/test_model_symbols.py` | `test_perfil_declara_o_metodo` | 1 |
| `tests/unit/test_symbol_matcher_paridade.py` | paridade sobre `variantes_do_motor` (`:89`, `:135`) | 1 |
| `scripts/residuos_raster_folhas.py` (novo), `tests/unit/test_residuos_raster_folhas.py` (novo) | H2 | 2 |
| `scripts/simbolos_ficha_metricas.py`, `scripts/simbolos_ficha_relatorio.py`, `tests/unit/test_leituras_erradas.py` (novo) | leitura errada afirmada no benchmark e linha no `.md` | 3 |

Onda 1: Tasks 1, 2 e 3 (arquivos disjuntos). Depois, a Task 4 (orquestrador).

Soma: 1h50 (35 + 40 + 25 + 10).

## Tasks

### Task 1: Tipo de gramática só do modelo

**Estimativa:** 35 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/declarative_symbols.py`
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py` (só o campo)
- Modify: `src/zeny_project_handler/adapters/analysis/model_symbols.py` (só o perfil)
- Modify: `docs/schemas/pacotes-simbologia.schema.json`
- Create: `tests/unit/test_gramatica_so_modelo.py`
- Modify: `tests/unit/test_model_symbols.py`, `tests/unit/test_symbol_matcher_paridade.py`

**Interfaces:**
- Produces: `declarative_symbols.GRAMATICAS_SO_MODELO: Final[frozenset[str]]`; `declarative_symbols.variantes_do_motor(pacotes: tuple[Package, ...]) -> tuple[tuple[Package, Package], ...]`; validação de `stem_bars` (R-2); `perfil_pacotes` e `observar_pacotes` usam `variantes_do_motor`; `perfil_pacotes_modelo` com `classes_suportadas` e `enabled_variants` de `_enabled`; `CasamentoGramatica.componentes: tuple[int, ...] = ()`.

- [ ] **Step 1: Escrever os testes** em `test_gramatica_so_modelo.py`, com pacotes sintéticos escritos em `tmp_path` e carregados por `carregar_pacotes(packages_dir=tmp_path)`:
  - `test_stem_bars_valido_carrega` (as quatro combinações de `enclosure`/`removal_mark` para 3/`decreasing` e para 4/`alternating`);
  - `test_stem_bars_invalido_recusa`, parametrizado: campo a mais, `bars` 2 ou 5, 3 com `alternating`, 4 com `decreasing`, `taper` desconhecido, `enclosure` desconhecido, `removal_mark` não booleano, `max_span` 0, 73 ou booleano → `ValueError`;
  - `test_schema_tem_o_ramo_stem_bars`, estrutural e sem biblioteca de JSON Schema (o projeto não tem nenhuma; não acrescente): lê o schema, acha no `oneOf` o ramo (ou os dois sub-ramos) de `kind` `stem_bars` e confere `additionalProperties: false`, `required` com os seis campos, os enums de R-2, o par `bars`/`taper` restrito aos dois válidos (dois sub-ramos ou `if`/`then`) e `max_span` com `exclusiveMinimum` 0 e `maximum` 72;
  - `test_motor_ignora_variante_so_do_modelo`: um pacote com uma variante `label_in_frame` e uma `stem_bars` habilitadas; `perfil_pacotes(...).classes_suportadas` não contém a classe da `stem_bars`, `("enabled_variants", 1)` nos parâmetros, e `observar_pacotes` numa página com a moldura positiva da `label_in_frame` (desenhada como em `tests/fixtures/declarative_symbols/corpus.py`) observa só ela, sem falhar;
  - `test_perfil_do_modelo_conta_a_variante_so_do_modelo`: `perfil_pacotes_modelo` do mesmo pacote tem as duas classes e `("enabled_variants", 2)`;
  - `test_enabled_continua_com_todas` e `test_casamento_sem_componentes_por_padrao`.
  - Em `test_model_symbols.py`, `test_perfil_declara_o_metodo` passa a comparar `classes_suportadas` e `enabled_variants` com os de `_enabled`, não com os do motor.
  - Em `test_symbol_matcher_paridade.py`, os dois usos de `_enabled(` (`:89` e `:135`) passam a `variantes_do_motor(`. São os únicos em `tests/` que comparam núcleo e motor; `test_model_symbols.py:567` fica.
- [ ] **Step 2: Rodar** e ver falhar pelo motivo certo.
- [ ] **Step 3: Implementar** em `declarative_symbols.py`, no perfil de `model_symbols.py`, no schema e o campo em `symbol_matcher.py`.
- [ ] **Step 4: Rodar** o arquivo novo, `tests/unit/test_declarative_symbol_packages.py`, `tests/unit/test_symbol_matcher_paridade.py`, `tests/unit/test_model_symbols*.py` e `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` (`errors: []`); ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: tipo de gramatica so do modelo de desenho`).

### Task 2: Resíduos raster por folha (H2)

**Estimativa:** 40 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `scripts/residuos_raster_folhas.py`
- Create: `tests/unit/test_residuos_raster_folhas.py`

**Interfaces:**
- Consumes: `model_symbols.residuos_raster`, `pagina_para_gramaticas`, `casar_variantes`, `_enabled`, `carregar_tabela_glifos`; o mapa de folhas de `scripts/simbolos_corpus.py` (mesma guarda de `avaliacao-cega` e mesma conferência de sha do benchmark).
- Produces: CLI `python -m scripts.residuos_raster_folhas --rodada DIR --saida DIR [--recortes] [--dpi 200] [--processos N]`; `saida/residuos-raster.json` no esquema `residuos-raster-v1`: `{"esquema", "rodada", "folhas": [{"pdf_id", "paginas": [{"pagina", "estado": "medida" | "fora_dominio", "motivo", "residuos": [{"caixa_normalizada", "sha256_curto", "de_anotacao", "referencias_sob": [classe, ...], "recorte": "<nome>.png" | null}], "referencias_sob_imagem": [{"id", "classe"}]}], "total": int | null}], "resumo": {"folhas_medidas", "folhas_fora_dominio", "residuos", "por_hash": {sha256_curto: n_folhas}, "sobre_referencia": n, "referencias_sob_imagem": n}}`. `total` é `null` quando alguma página da folha é `fora_dominio`. Sem nome de PDF nem caminho na saída, só o id da rodada.

- [ ] **Step 1: Escrever os testes** sobre uma rodada sintética em `tmp_path` (2 PDFs gerados pelo PyMuPDF, com `rodada.json` e `ficha/referencia.json` no formato da E03; um PDF com uma imagem compacta inserida sobre a caixa de uma referência de símbolo, outra longe e uma imagem grande sob outra referência; o outro sem imagem):
  - `test_conta_residuos_por_folha` (2 e 0) e `test_cruza_com_referencia` (`referencias_sob == ["ATERRAMENTO"]` só na imagem sobre a referência);
  - `test_referencia_sob_imagem_grande_e_listada`;
  - `test_pagina_fora_dominio_nao_vira_zero`: monkeypatch de `casar_variantes` levantando `TetoGramaticasExcedido` → `estado == "fora_dominio"`, `total is None`;
  - `test_imagens_falhou_nao_vira_zero`: diagnóstico `modelo.imagens_falhou` (e, parametrizado, `modelo.imagens_anotacao_falhou`) na página → `fora_dominio` com o motivo, `total is None`;
  - `test_recortes_gravados` com `--recortes` (PNG existe, nome sem o do PDF) e `test_saida_sem_caminho_nem_nome_de_pdf`;
  - `test_recusa_avaliacao_cega` (rodada apontando para `avaliacao-cega`, como no benchmark);
  - `test_processos_da_o_mesmo_resultado` (`--processos 1` e `2`).
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar.** Por página: `pagina_para_gramaticas(pagina, indice, tabela)`, `casar_variantes` com as variantes habilitadas dos pacotes carregados uma vez por folha, `residuos_raster(pagina, casamentos)`; `FonteGramaticaFalhou`, `TetoGramaticasExcedido`, `modelo.caminhos_falhou`, `modelo.imagens_falhou` e `modelo.imagens_anotacao_falhou` dão `fora_dominio` com o motivo. Recorte por `page.get_pixmap(clip=<caixa crua>, dpi=dpi)`, com a caixa crua vinda da derrotação, como `model_symbols._observacao`. Paralelismo como `scripts/benchmark_simbolos_ficha.py` (`ProcessPoolExecutor`, ordem serial).
- [ ] **Step 4: Rodar** o arquivo de teste, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: residuos raster por folha para a H2`).

### Task 3: Leitura errada afirmada no benchmark

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `scripts/simbolos_ficha_metricas.py`, `scripts/simbolos_ficha_relatorio.py` (só a linha do `.md`)
- Create: `tests/unit/test_leituras_erradas.py`

**Interfaces:**
- Produces: `simbolos_ficha_metricas.leituras_erradas(referencias: Sequence[Mapping[str, Any]], predicoes: Sequence[Mapping[str, Any]], casadas: Collection[int], tolerancia: float) -> list[dict[str, Any]]` — função pura: para cada predição de índice fora de `casadas`, uma entrada `{"classe_predita", "classe_referencia", "referencia_id"}` por referência de **outra** classe cuja caixa, alargada pela tolerância do critério `centro`, contém o centro da predição. Nomes dos parâmetros podem seguir os tipos internos que `avaliar_predicoes` já usa; a semântica é esta. A chave aditiva `"leituras_erradas": {"total": int, "por_classe": {classe: int}, "itens": [...]}` é calculada por critério em `_bloco_criterio` (onde o casamento de cada critério é feito), com as casadas daquele critério, e somada em `_somar_criterio` e nos agregadores atuais (por família, folha e geral), como as contagens tp/fp/fn. R-4 lê o bloco `centro`. O relatório `.md` (`simbolos_ficha_relatorio._markdown`) ganha uma linha com o total por método no critério `centro`.

- [ ] **Step 1: Escrever os testes** em `test_leituras_erradas.py`:
  - predição ATERRAMENTO não casada com centro na caixa de uma referência PARA_RAIOS_BT → 1 item, `classe_referencia == "PARA_RAIOS_BT"`;
  - predição ATERRAMENTO casada com a referência ATERRAMENTO, cujo centro também cai numa referência PARA_RAIOS_MT encostada → 0 (a casada é leitura certa);
  - predição não casada com centro fora de toda referência → 0; no limite da tolerância → 1, e fora dela → 0;
  - `avaliar_predicoes` grava `leituras_erradas` com `total` e `por_classe`, e a agregação soma duas folhas;
  - a chave nova não muda nenhuma das chaves existentes do bloco (compare tp/fp/fn de um caso dos testes atuais).
- [ ] **Step 2: Rodar** e ver falhar.
- [ ] **Step 3: Implementar** a função e a chamada em `_bloco_criterio`, que já tem referências, predições e o casamento em mãos; sem importar `benchmark_simbolos_ficha` (import circular).
- [ ] **Step 4: Rodar** `tests/unit/test_leituras_erradas.py`, `tests/unit/test_benchmark_simbolos_ficha*.py` e os demais testes de `simbolos_ficha_*`, ruff, format e mypy.
- [ ] **Step 5: Commit** (`feat: leitura errada afirmada no benchmark de simbolos`).

### Task 4: Medição da H2 nas 16 folhas (orquestrador)

**Estimativa:** 10 min (mais a triagem) · **Depende de:** Tasks 1, 2 e 3 · **Risco:** normal · **Laboratório:** não

Sem código: o orquestrador roda, na branch da etapa com a Onda 1 integrada, com `<rodada E03>` = `<checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas` e `--processos 10`:
- [ ] `python -m scripts.residuos_raster_folhas --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2-1/h2 --recortes --processos 10` → contagem por folha; triagem visual dos recortes (hash repetido uma vez) e das `referencias_sob_imagem`; veredito da H2 no handoff e na linha H2 de "Hipóteses e decisões em aberto".
- [ ] `python -m scripts.benchmark_simbolos_ficha --rodada <rodada E03> --saida <checkout principal>/tmp/e06-3-2-1/simbolos --metodo atual --metodo modelo --processos 10` → tp/fp/fn iguais aos de `tmp/e06-2-2-2/simbolos/simbolos-ficha.json` e a linha de base de leituras erradas de cada método (a E06.3.2.2 compara contra ela).
- [ ] `python -m scripts.audit_symbol_packages` → `errors: []`.

## Fechamento operacional

- Suíte inteira com a onda integrada; nenhuma tarefa `Risco: normal` produz código, então sem testador de etapa; `osv-scanner` nos 7 locks; `check_test_integrity --base <MERGE_BASE>`; revisão final; `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` (conferir a data do `relatorio-testes.txt`).
- Handoff com: H2 por folha e veredito, linha de base de leituras erradas, R-1 em "Decisões para o usuário" (o motor antigo ignora tipo só do modelo; outros consumidores de `status == "enabled"` passarão a contar variantes que ele não executa), e o bloco "Para a E06.3.2.2".

## Revisão de arquitetura

- **Veredito:** aprovado com notas, na rodada 2 (`revisor-arquitetura`, opus). Rodada 0 (plano da E06.3.2 inteiro): bloqueado, 2 Críticos e 6 Importantes. Rodada 1: bloqueado, 4 Importantes novos; a etapa foi dividida e este plano recortado. Rodada 2: aprovado com notas.
- **Modelo:** opus.
- **Notas Menores da rodada 2, aplicadas antes da execução:** M1 (chave por critério em `_bloco_criterio`), M2 (`simbolos_ficha_relatorio.py` na Task 3), M3 (triar todas as `referencias_sob_imagem`), M4 (o rascunho da E06.3.2.2 lê a chave `leituras_erradas` do relatório, sem CLI), M5 (assinatura do runner muda pelo digest; ordem dos `parametros` mantida).
