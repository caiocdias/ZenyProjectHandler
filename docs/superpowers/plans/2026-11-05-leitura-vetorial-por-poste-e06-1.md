# E06.1 — Medição de símbolos e base dos pacotes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** medir a detecção de símbolos do analisador atual contra os símbolos das fichas de referência da E03 e preparar a base do método sobre o modelo de desenho. A base são as classes da ficha nos pacotes (como `pending`, com fonte rastreável), a página do modelo com índice cru e uma guarda contra memorização.

**Architecture:**
- O benchmark novo é um script (`scripts/benchmark_simbolos_ficha.py`). Ele reaproveita `symbol_benchmark_runner.infer_pdf` para as predições e `symbol_benchmark_evaluator.geometry_match` para o critério IoU, e lê as fichas com `scripts.ficha_poste`.
- O auditor passa a aceitar variantes de qualquer estágio do inventário, e os JSON de `symbol_packages/` ganham variantes `pending`. Nada é habilitado, então a detecção não muda.
- O leitor do modelo ganha uma função pública que monta a `PaginaModelo` da página já aberta, mais o índice cru de cada caminho.
- Nada é ligado no runner nem no analisador padrão.

**Tech Stack:** Python 3.11, PyMuPDF, pytest (+xdist), `concurrent.futures.ProcessPoolExecutor`.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06 — Símbolos sobre o modelo de desenho (dividida em E06.1–E06.3)" (divisão e rulings) e "E06.1 — Medição de símbolos e base dos pacotes". Também valem `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (decisões 1 e 7, "Fronteiras") e `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md`. O levantamento do código está no workspace (`.superpowers/sdd/e06-levantamento/levantamento.md`), fora do Git.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`. Sem migração SQLite.
- Mudança de comportamento de saída incrementa a versão do extrator ou do interpretador (ADR 0006). Nesta subetapa, nenhuma saída do analisador nem do modelo muda: `PyMuPdfDocumentAnalyzer.versao` continua `1.21.0` e `VERSAO_MODELO_DESENHO` continua `modelo-desenho-v2`. As variantes novas entram só `pending`. O `package_sha256` do perfil dos pacotes muda sozinho, e isso invalida o cache do runner, como deve.
- PDFs reais, recortes, rótulos e dados de folha nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos.
- O gate normal não depende de `examples/` nem de `tmp/` (ADR 0005).
- Nenhuma leitura de `examples/avaliacao-cega/`: o benchmark acha o PDF só pelo `rodada.json` e recusa caminho que passe por `avaliacao-cega`.
- Documentação enxuta: nada de histórico de execução em arquivo versionado.
- Gate de complexidade: CC < 31 em `src/` (`scripts/complexity_gate.py src`).
- Sem dependência nova.
- **Arquivos disjuntos com a E15 aberta (trilha B):** não tocar em `scripts/benchmark_ficha_poste.py`, `scripts/curation_ficha.py`, `scripts/ficha_predita_propostas.py`, `examples/README.md`, `tests/unit/test_ficha_predita_propostas.py` nem `tests/unit/test_curation_ficha_baseline_processos.py`. Consumir sem editar `scripts/benchmark_network_pdf.py`, `scripts/ficha_poste.py` e `scripts/ficha_poste_avaliador.py`. Não tocar em `tests/conftest.py` nem no cliente, reservados à E17. `CLAUDE.md` também não muda nesta subetapa.
- Suíte inteira: `-n` informado em cada despacho (orçamento de máquina).

## Decisões de desenho (rulings do planejador)

- **R-E06.1-1, "atual":** é a união do runner sem raster, ou seja, `infer_pdf(pdf, id, include_transformers=True, include_guys=True, include_packages=True)`, com legado, estais, transformadores e pacotes. Fica de fora o raster e o estrutural. Custo se errado: comparar contra uma base mais fraca ou mais forte que a substituída. O método fica registrado no relatório.
- **R-E06.1-2, critérios de casamento:** o relatório traz sempre os dois critérios.
  - `centro` (principal): o centro da predição cai na caixa da referência expandida por `TOLERANCIA_CENTRO = 0.005` em cada lado, no espaço normalizado da página exibida.
  - `iou` (diagnóstico): `symbol_benchmark_evaluator.geometry_match(predicao, referencia)`.
  - O casamento é 1-1 guloso por (página, classe): os pares elegíveis são ordenados por distância de centro, com desempate por índice da referência e depois da predição, e cada lado é usado uma vez.
- **R-E06.1-3, o que conta como FP:**
  - **classes avaliadas:** as que aparecem em alguma referência da rodada. Predição de outra classe vai para `fora_do_escopo[classe]`, sem FP;
  - **referência regional:** predição com centro fora de todas as regiões da página vai para `fora_das_regioes`, sem FP;
  - **poste com `"simbolos"` em `pendentes`:** os símbolos dele saem do denominador. Predição com centro dentro da caixa desse poste expandida por `0.05` (o limiar de distância do R4) vai para `perto_de_poste_pendente`, sem FP.

  A precisão é um limite inferior, porque a ficha só anota símbolo associado a poste. O `.md` diz isso.
- **R-E06.1-4, família:** `reconhecer_familia(impressao_estrutural(documento)).familia` (de `drawing_model/family.py` e `pymupdf_drawing_model.py`). É barato e não extrai o modelo inteiro.
- **R-E06.1-5, variantes novas:**
  - As variantes do inventário `docs/data/inventario-simbologia-v1.json` das classes ESTAI, TRANSFORMADOR, ATERRAMENTO, PARA_RAIOS_MT e PARA_RAIOS_BT entram nos pacotes como `pending`.
  - Cada uma leva `source_ref = source_refs[0]` do inventário, `visual_note` do inventário e um `reason` que cite a E06.3.
  - As famílias que ainda não têm arquivo ganham `family-f02-NN.json`, com `profile_id` e `source_id` do inventário.
  - O inventário não muda. CONVENCAO_EO e CONJUNTO_EO, que também faltam, ficam fora: não são classes da ficha (fora do escopo da E06).
- **R-E06.1-6, auditor:** o universo esperado continua sendo o das variantes `owner_stage == "E07"`, todas obrigatórias. Variante de outro `owner_stage` presente num pacote é aceita se existir no inventário com a mesma família e as mesmas regras de conferência. O relatório ganha `variants_by_owner_stage`. Variante que não está no inventário continua `unexpected variant`.

## Review Focus

1. Referência com bbox de área zero ou predição com bbox degenerada (polilinha fina do estai) não pode quebrar o casamento nem gerar divisão por zero → caso na Task 1.
2. Folha da rodada com `sha256` diferente do PDF no disco, PDF ausente ou caminho que passa por `avaliacao-cega` → `situacao: "falha"` saneada, sem caminho absoluto, e as outras folhas seguem → testes na Task 1.
3. Uma variante nova escrita à mão como `enabled`, ou fora do inventário, tem de reprovar o auditor → testes na Task 2.
4. Página com desenhos `clip`/`group` intercalados: o índice cru de cada caminho tem de apontar para o desenho certo de `get_drawings(extended=True)` → teste na Task 3.
5. Número com mais de 4 casas decimais ou string hexadecimal de 64 caracteres num pacote → a guarda reprova → teste negativo na Task 4.

---

## File Structure

| Arquivo | Ação | Responsabilidade | Task |
|---|---|---|---|
| `scripts/benchmark_simbolos_ficha.py` | criar | benchmark diagnóstico de símbolos contra as fichas da rodada, `--processos` | 1 |
| `tests/unit/test_benchmark_simbolos_ficha.py` | criar | rodada sintética com 2 PDFs gerados no teste | 1 |
| `scripts/audit_symbol_packages.py` | modificar | aceitar variante de outro estágio presente no inventário; `variants_by_owner_stage` | 2 |
| `src/zeny_project_handler/adapters/analysis/symbol_packages/family-f02-*.json` | modificar/criar | variantes `pending` de ESTAI, TRANSFORMADOR, ATERRAMENTO e PARA_RAIOS_MT/BT | 2 |
| `tests/unit/test_declarative_symbol_packages.py` | modificar | contagens novas de variantes e famílias; testes do auditor ampliado | 2 |
| `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py` | modificar | `pagina_modelo_com_indices(pagina, indice, tabela=None)` | 3 |
| `tests/unit/test_pymupdf_drawing_model_pagina.py` | criar | igualdade com `extrair_modelo_desenho` e índice cru com `clip`/`group` | 3 |
| `tests/unit/test_symbol_packages_sem_memorizacao.py` | criar | guarda contra coordenada, hash e nome de folha nos pacotes | 4 |

## Tarefas e ondas

| Task | Estimativa | Depende de | Risco | Laboratório |
|---|---|---|---|---|
| 1 — benchmark de símbolos contra as fichas | 45 min | nenhuma | alto (entrada externa, concorrência) | não |
| 2 — auditor e variantes `pending` das classes da ficha | 45 min | nenhuma | normal | não |
| 3 — página do modelo com índice cru | 30 min | nenhuma | alto (parsing de PDF) | não |
| 4 — guarda contra memorização | 20 min | Task 2 (pacotes novos) | normal | não |

Com duas etapas abertas, cada onda tem até 2 tarefas. Onda 1: Tasks 1 e 2. Onda 2: Tasks 3 e 4. Os arquivos são disjuntos. Soma: ~2h20, mais revisão e fechamento operacional, dentro do teto de ~3h.

---

### Task 1: benchmark de símbolos contra as fichas

**Files:**
- Create: `scripts/benchmark_simbolos_ficha.py`
- Test: `tests/unit/test_benchmark_simbolos_ficha.py`

**Interfaces:**
- Consumes:
  - `scripts.symbol_benchmark_runner.infer_pdf(source, document_id, *, include_transformers, include_guys, include_packages, ...) -> tuple[Record, list[Record], list[Record]]`. Os registros de predição trazem `class_id`, `bbox` normalizada da página exibida, página e `method_id`; confira os nomes reais no código e use-os;
  - `scripts.symbol_benchmark_evaluator.geometry_match(a, b) -> bool`;
  - `scripts.ficha_poste.carregar_ficha(path)` e `_centro_na_regiao`, já importados assim por outros scripts;
  - `zeny_project_handler.adapters.analysis.pymupdf_drawing_model.impressao_estrutural` e `drawing_model.family.reconhecer_familia`.
- Produces:
  - `TOLERANCIA_CENTRO: Final = 0.005`; `RAIO_POSTE_PENDENTE: Final = 0.05`; `ESQUEMA: Final = "simbolos-ficha-v1"`;
  - `METODOS: Final[dict[str, Callable[[Path, str], list[dict[str, Any]]]]]`, por enquanto `{"atual": _predicoes_atual}`, cada função de nível de módulo. A E06.2 acrescenta `"modelo"`. Predição normalizada: `{"pagina": int, "classe": str, "bbox": [x0, y0, x1, y1], "metodo": str}`;
  - `casar(referencias: Sequence[dict], predicoes: Sequence[dict], criterio: Literal["centro", "iou"]) -> list[tuple[int, int]]` (pares de índices, R-E06.1-2);
  - `medir_pdf(pdf: Path, referencia: dict, pdf_id: str, metodos: Sequence[str]) -> dict` (uma folha, os dois critérios, `tempo_s` por método e `familia`);
  - `medir_simbolos(rodada: Path, saida: Path, *, metodos: Sequence[str] = ("atual",), processos: int = 1) -> dict`. Grava `simbolos-ficha.json` e `simbolos-ficha.md` em `saida` e devolve o relatório;
  - CLI: `python -m scripts.benchmark_simbolos_ficha --rodada DIR --saida DIR [--metodo atual ...] [--processos N]`, com `N` inteiro ≥ 1 (0 ou negativo → exit 2 do argparse) e efetivo `min(N, folhas, 61)`.
- Relatório (`simbolos-ficha.json`):
  - `{"schema_version": ESQUEMA, "opcoes": {"metodos", "criterios": ["centro", "iou"], "tolerancia_centro", "raio_poste_pendente"}, "por_pdf": {pdf_id: {...}}, "total": {...}, "por_familia": {...}}`;
  - para cada método e critério: `por_classe[classe] = {"tp", "fp", "fn", "precisao", "recall"}`, mais `fora_do_escopo`, `fora_das_regioes` e `perto_de_poste_pendente`. Taxa com denominador 0 → `null`;
  - folha que falha: `{"situacao": "falha", "erro": <primeira linha saneada>}`, e as outras folhas seguem;
  - `tempo_s` só em `por_pdf`. Nenhum caminho absoluto nem nome de PDF: só o `pdf_id` da rodada.
- Localização do PDF: lê `rodada.json` (`raiz_corpus` relativo à rodada + `pdfs[*].caminho_relativo`) e confere o `sha256` do arquivo contra `referencia["pdf_sha256"]`. Recusa como falha um caminho resolvido que contenha o componente `avaliacao-cega`. A referência é `pdfs/<pdf_id>/ficha/referencia.json`, e a folha sem referência fica `sem_referencia`.
- Paralelismo: com `processos > 1` e mais de 1 folha, `ProcessPoolExecutor(max_workers=efetivo)` + `pool.map` na ordem do `rodada.json`, no padrão de `scripts/benchmark_texto_ficha.py:406-419`. `BrokenProcessPool` → as folhas sem resultado viram falha, e o relatório é gravado mesmo assim.

- [ ] **Step 1: Write the failing tests.** Gere no teste uma rodada sintética em `tmp_path`:
  - 2 PDFs de 1 página desenhados com PyMuPDF. Use formas que o "atual" reconhece de verdade, reaproveitando os construtores de fixture dos testes de `pymupdf_symbols`, `pymupdf_guys` ou `pymupdf_transformers`, por exemplo um aterramento e um estai sintéticos;
  - `rodada.json` com `raiz_corpus` relativo;
  - fichas de referência válidas por `scripts.ficha_poste.validar_ficha`. Testes:
  - `test_casar_por_centro_e_um_para_um`: 2 referências da mesma classe e 3 predições → 2 pares, sem predição repetida, na ordem do R-E06.1-2;
  - `test_casar_iou_nao_casa_polilinha_fina_que_centro_casa`: predição de caixa degenerada (largura 0) no meio da referência → `centro` casa e `iou` não, sem exceção;
  - `test_classe_fora_do_escopo_nao_e_fp`, `test_predicao_fora_das_regioes_nao_e_fp`, `test_predicao_perto_de_poste_pendente_nao_e_fp`;
  - `test_medir_simbolos_na_rodada_sintetica`: o "atual" sobre os 2 PDFs → `tp` ≥ 1 na classe desenhada e `fn` = 1 numa referência sem desenho (positivo e negativo), com `familia` presente;
  - `test_processos_2_igual_a_serial`: os JSON, carregados, são iguais depois de remover `tempo_s`, e os `.md` são iguais depois de remover a coluna ou linha de tempo, se houver;
  - `test_sha_diferente_e_falha_saneada` e `test_caminho_avaliacao_cega_e_recusado` (rodada cujo `caminho_relativo` aponta para `avaliacao-cega/x.pdf` dentro de `tmp_path`) → `situacao == "falha"`, sem `str(tmp_path)` no JSON;
  - `test_cli_processos_invalido` → `SystemExit` com código 2;
  - `test_relatorio_sem_caminho_absoluto_nem_nome_de_pdf`.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_simbolos_ficha.py -q` → FAIL (`ModuleNotFoundError`).
- [ ] **Step 3:** implemente `scripts/benchmark_simbolos_ficha.py`.
- [ ] **Step 4:** o mesmo comando → PASS; `ruff check`, `ruff format --check` e `mypy` limpos.
- [ ] **Step 5: Commit** (`feat: benchmark de simbolos contra as fichas de referencia`).

### Task 2: auditor e variantes `pending` das classes da ficha

**Files:**
- Modify: `scripts/audit_symbol_packages.py`; `src/zeny_project_handler/adapters/analysis/symbol_packages/` (os JSON das famílias de ESTAI, TRANSFORMADOR, ATERRAMENTO e PARA_RAIOS no inventário, criando os que faltam)
- Modify (teste): `tests/unit/test_declarative_symbol_packages.py`

**Interfaces:**
- Consumes: `docs/data/inventario-simbologia-v1.json`; `declarative_symbols.carregar_pacotes`, que tem de continuar aceitando os pacotes (formato inalterado).
- Produces:
  - auditoria com `errors == []` e `enabled == 22` (inalterado), `pending == 343 + <novas>` e `variants_by_owner_stage: dict[str, int]`;
  - `perfil_pacotes().classes_suportadas` inalterado, porque nenhuma variante nova é habilitada.

Regras (R-E06.1-5 e R-E06.1-6):
- Gere as variantes a partir do inventário, de forma determinística: um script descartável fora do Git, ou à mão. Mantenha a ordem do inventário dentro de cada família e o formato exato das variantes existentes (`id`, `class_code`, `role`, `destination`, `source_ref`, `visual_note`, `recognition`).
- `role` e `destination` são os que o auditor deriva da `function` do inventário.
- `recognition = {"status": "pending", "reason": "Gramática vetorial sobre o modelo de desenho pendente (E06.3); <visual_note resumida>"}`, com o `reason` de ≥ 12 caracteres.

- [ ] **Step 1: Write the failing tests** em `tests/unit/test_declarative_symbol_packages.py`:
  - `test_pacotes_tem_as_classes_da_ficha_como_pendentes`: entre as variantes carregadas há ≥ 1 de cada classe ESTAI, TRANSFORMADOR, ATERRAMENTO, PARA_RAIOS_MT e PARA_RAIOS_BT, todas `pending`. O total de habilitadas continua 22, e `perfil_pacotes().classes_suportadas` não muda;
  - `test_auditor_aceita_variante_de_outro_estagio_do_inventario`: auditoria real → `errors == []` e `variants_by_owner_stage` com as chaves de estágio presentes;
  - `test_auditor_recusa_variante_fora_do_inventario`: cópia em `tmp_path` com uma variante inventada → erro `unexpected variant`;
  - `test_auditor_recusa_variante_nova_habilitada_sem_gramatica`: cópia com uma variante nova `enabled` sem `grammar` → erro;
  - atualize as contagens fixas existentes (365 variantes e as contagens por família) para os números novos, derivados do inventário no próprio teste sempre que possível, em vez de literais.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_declarative_symbol_packages.py -q` → FAIL.
- [ ] **Step 3:** implemente o auditor e grave os JSON.
- [ ] **Step 4:** `.venv/Scripts/python.exe -m pytest tests/unit/test_declarative_symbol_packages.py tests/unit -q -k "declarative or symbol_package or audit"`, e depois `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → `"errors": []`. O ruff e o mypy ficam limpos. Rode também os testes do runner e dos pacotes (`-k "symbol_execution or packages"`), porque a assinatura do perfil muda com o sha.
- [ ] **Step 5: Commit** (`feat: classes da ficha como variantes pendentes nos pacotes`).

### Task 3: página do modelo com índice cru

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py`
- Test: `tests/unit/test_pymupdf_drawing_model_pagina.py`

**Interfaces:**
- Consumes: `_ler_fontes(pagina)`, `_montar_pagina(indice, pagina, fontes, tabela=None)`, `_desenhos(pagina)` e `_TIPOS_CAMINHO` (mesmo módulo).
- Produces: `pagina_modelo_com_indices(pagina: pymupdf.Page, indice: int, tabela: TabelaGlifos | None = None) -> tuple[PaginaModelo, tuple[int, ...]]`. O primeiro elemento é igual a `extrair_modelo_desenho(pdf, tabela).paginas[indice]` para a mesma página. O segundo tem um item por `caminhos[i]` do modelo, com a posição em `pagina.get_drawings(extended=True)` do desenho que originou `caminhos[i]`. `get_drawings` é chamado uma vez só por chamada. Não muda o cache, o formato do modelo nem `VERSAO_MODELO_DESENHO`.

- [ ] **Step 1: Write the failing tests:**
  - `test_pagina_modelo_igual_a_extracao_do_documento`: PDF sintético com linhas, retângulo, círculo e texto → o modelo da função é igual a `extrair_modelo_desenho(pdf).paginas[0]`;
  - `test_indices_crus_apontam_para_o_desenho_de_origem`: PDF sintético com `clip` e `group`, de forma que `get_drawings(extended=True)` traga itens `clip`/`group` intercalados (por exemplo com `page.show_pdf_page` de outra página ou um Form XObject com clip). Para cada `i`, o desenho cru em `indices[i]` tem o mesmo `rect` e os mesmos itens geométricos do caminho `i` (comparação aproximada, na mesma transformação);
  - `test_pagina_sem_desenhos`: retorno `(modelo, ())`;
  - `test_get_drawings_chamado_uma_vez`: `monkeypatch` conta as chamadas → 1.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_pymupdf_drawing_model_pagina.py -q` → FAIL (`ImportError`).
- [ ] **Step 3:** implemente. Se `_ler_fontes` já chama `get_drawings`, guarde os índices crus em `_Fontes` em vez de chamar de novo. Depois, `scripts/complexity_gate.py src` continua aprovado.
- [ ] **Step 4:** o mesmo comando, mais `-k "drawing_model"` → PASS; ruff, format e mypy limpos.
- [ ] **Step 5: Commit** (`feat: pagina do modelo de desenho com indice cru dos caminhos`).

### Task 4: guarda contra memorização

**Files:**
- Test: `tests/unit/test_symbol_packages_sem_memorizacao.py`

**Interfaces:**
- Consumes: os JSON de `symbol_packages/` (Task 2), lidos por caminho derivado de `Path(__file__)`, nunca do cwd.
- Produces: `verificar_pacote(dados: Any) -> list[str]`, função do próprio módulo de teste que devolve as violações.

Regras da guarda, aplicadas a todo valor de todo pacote:
- nenhum `float` (ou string numérica) com mais de 4 casas decimais (coordenada de folha);
- nenhuma string que contenha um hexadecimal de 64 caracteres (sha256 de PDF);
- nenhuma string com `.pdf` além do formato de `source_ref.locator` do inventário F02 (o PDF-fonte normativo, não uma folha). Na dúvida, compare com o `locator` do inventário;
- nenhuma string com o padrão de nome de folha real `PROJETO DE REDE` (sem diferenciar maiúsculas).

- [ ] **Step 1:** `test_pacotes_reais_passam_na_guarda` (todos os pacotes → `[]`) e, parametrizado, `test_guarda_reprova` com 4 casos sintéticos: float `0.123456`, hex de 64 caracteres, `"PROJETO DE REDE NS 1"` e `"folha.pdf"` fora do locator. Cada um → 1 violação.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_symbol_packages_sem_memorizacao.py -q` → PASS nos pacotes reais e nos 4 negativos. Este teste nasce verde nos reais: a guarda protege as próximas subetapas. A prova de que não passa à toa são os 4 negativos.
- [ ] **Step 3: Commit** (`test: guarda contra memorizacao de folha nos pacotes`).

---

## Fechamento operacional (orquestrador, antes da revisão final)

1. Rode o benchmark nas 16 folhas, a partir do worktree da trilha A, com o `.venv` dele: `.venv/Scripts/python.exe -m scripts.benchmark_simbolos_ficha --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/e06/simbolos-atual --processos <n>`. O `<n>` é 20 ÷ suítes e benchmarks simultâneos da sessão, com mínimo de 2.
2. Leve ao handoff os totais por classe, família e folha nos dois critérios, e também `fora_do_escopo`, `fora_das_regioes`, `perto_de_poste_pendente` e o tempo por folha.
3. `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → `"errors": []` (critério 2).
4. `git grep -n "PROJETO DE REDE NS"` só acha as linhas que citam o critério.
5. `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`, sem outra suíte da sessão rodando.

## Critérios de aceite → evidência

| Critério | Evidência |
|---|---|
| fixtures sintéticas positivas e negativas | Tasks 1, 3 e 4 |
| auditor com 0 erros e as variantes novas | Task 2; passo 3 do fechamento |
| baseline diagnóstico do atual em `tmp/`, totais no handoff | passos 1 e 2 do fechamento |
| guarda verde | Task 4 |
| `.bat` aprovado | passo 5 |
