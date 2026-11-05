# E06.1 — Medição de símbolos e base do modelo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** medir a detecção de símbolos do analisador atual contra os símbolos das fichas de referência da E03 e preparar a base do método sobre o modelo de desenho, com a página do modelo e o índice cru e uma guarda contra memorização.

**Architecture:**
- O benchmark novo é um script, `scripts/benchmark_simbolos_ficha.py`. Ele reaproveita `symbol_benchmark_runner.infer_pdf` para as predições e `symbol_benchmark_evaluator.geometry_match` para o critério IoU.
- O leitor do modelo ganha uma função pública que monta a `PaginaModelo` da página já aberta, com o índice cru de cada caminho.
- Os pacotes, o runner e o analisador padrão não mudam.

**Tech Stack:** Python 3.11, PyMuPDF, pytest (+xdist), `concurrent.futures.ProcessPoolExecutor`.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06 — Símbolos sobre o modelo de desenho (dividida em E06.1–E06.3)" (divisão e rulings) e "E06.1". Também valem `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (decisões 1 e 7, "Fronteiras") e `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md`. O levantamento do código está em `.superpowers/sdd/e06-levantamento/levantamento.md`, fora do Git.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`. Sem migração SQLite.
- Mudança de comportamento de saída incrementa a versão do extrator ou do interpretador (ADR 0006). Nesta subetapa, nenhuma saída do analisador, do runner, dos pacotes nem do modelo muda. `PyMuPdfDocumentAnalyzer.versao` continua `1.21.0`, `VERSAO_MODELO_DESENHO` continua `modelo-desenho-v2` e `symbol_packages/` não é tocado.
- PDFs reais, recortes, rótulos e dados de folha nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos.
- O gate normal não depende de `examples/` nem de `tmp/` (ADR 0005).
- Nenhuma leitura de `examples/avaliacao-cega/`: o benchmark acha o PDF só pelo `rodada.json` e recusa, antes de qualquer I/O, caminho com o componente `avaliacao-cega`.
- Documentação enxuta: nada de histórico de execução em arquivo versionado.
- Gate de complexidade: CC < 31 em `src/` (`scripts/complexity_gate.py src`).
- Sem dependência nova.
- **Arquivos disjuntos com a E15 aberta (trilha B):**
  - não tocar em `scripts/benchmark_ficha_poste.py`, `scripts/curation_ficha.py`, `scripts/ficha_predita_propostas.py`, `examples/README.md`, `tests/unit/test_ficha_predita_propostas*.py` nem `tests/unit/test_curation_ficha_baseline_processos.py`;
  - consumir sem editar `scripts/benchmark_network_pdf.py`, `scripts/ficha_poste.py` (só `carregar_ficha`, que é público) e `scripts/ficha_poste_avaliador.py`;
  - não tocar em `tests/conftest.py` nem no cliente, reservados à E17;
  - `CLAUDE.md` também não muda nesta subetapa.
- Suíte inteira: `-n` informado em cada despacho (orçamento de máquina).

## Decisões de desenho (rulings do planejador)

- **R-E06.1-0, ampliação dos pacotes adiada para a E06.3.** Variantes `pending` novas nos pacotes teriam efeitos em cadeia:
  - quebrariam `scripts/coverage_matrix_e16.py:271`, no fechamento da curadoria;
  - mudariam `tests/server/test_e14_symbol_review.py:287`;
  - mudariam o que o usuário vê na tabela de suporte da revisão (`symbol_support.py` → `review_api.py` → `ui/review_panel.py`) e nas exportações (`deliverable_exports.py`). A tabela mostraria ESTAI/TRANSFORMADOR como "pendentes" enquanto os detectores dedicados os reconhecem.

  Na E06.3 essas variantes entram já habilitadas, com gramática, e a mudança visível acontece uma vez só, com reconhecimento de verdade. Custo se errado: o auditor da E06.1 continua medindo só o universo E07; nada se perde.
- **R-E06.1-1, "atual":** `infer_pdf(pdf, id, include_transformers=True, include_guys=True, include_packages=True)`, a união do runner sem raster: legado, estais, transformadores e pacotes. O raster (parte do perfil `balanced` do runner) e o estrutural ficam fora. Essa união não passa por `reconcile_symbols`, ao contrário do runner do servidor, e o relatório diz isso e conta duplicatas por método e classe. Custo se errado: comparar a E06.3 contra uma base diferente da que o usuário imagina. Vai para "Decisões para o usuário".
- **R-E06.1-2, critérios de casamento.** O relatório traz sempre os dois:
  - `centro` (principal): o centro da predição na caixa da referência, expandida por `TOLERANCIA_CENTRO = 0.005` de cada lado, no espaço normalizado da página exibida;
  - `iou` (diagnóstico): `symbol_benchmark_evaluator.geometry_match(predicao, referencia)["eligible"]`. A função devolve um dict.

  O casamento é 1-1 guloso por (página, classe): ordena os pares elegíveis por distância de centro, desempata pelo índice da referência e depois pelo da predição, e usa cada lado uma vez. Substitui, para este gate, o `symbols-e02-v1` (só IoU) aprovado na E02, e vai para "Decisões para o usuário".
- **R-E06.1-3, ordem e o que conta como FP.**
  1. As predições com `context` de legenda ou informativo saem antes, como `contexto_nao_desenho`, igual para todos os métodos.
  2. As **classes avaliadas** são as que aparecem em alguma referência da rodada, gravadas em `opcoes.classes_avaliadas`. Predição de outra classe vai para `fora_do_escopo[classe]`.
  3. O casamento 1-1 roda com as referências válidas, que excluem os símbolos dos postes com `"simbolos"` em `pendentes`.
  4. Só as predições que **sobraram** são classificadas, nesta ordem:
     - centro fora de todas as regiões da página, em referência regional → `fora_das_regioes`;
     - centro dentro da caixa de um poste com símbolos pendentes, expandida por `RAIO_POSTE_PENDENTE = 0.05` (o limiar de distância do R4) → `perto_de_poste_pendente`;
     - o resto → FP.

  A precisão é um limite inferior, porque a ficha só anota símbolo associado a poste, e o `.md` diz isso.
- **R-E06.1-4, família:** `reconhecer_familia(impressao_estrutural(documento)).familia`, medida fora do `tempo_s` dos métodos.
- **R-E06.1-5, falha de método:** se o manifesto de `infer_pdf` traz `failures` não vazio ou `status == "failed"`, aquele método naquela folha vira `{"situacao": "falha", "erro": …}` e sai dos totais dele. Um detector quebrado não pode baixar a base que a E06.3 tem de superar.
- **R-E06.1-5b, mesmas folhas na comparação:** quando houver mais de um método, o relatório traz também `comparacao`. Ele tem os totais de cada método restritos à interseção das folhas em que todos tiveram sucesso, com a lista dessas folhas. É esse bloco que a E06.2 e a E06.3 comparam ("com as mesmas referências"). Com um método só, `comparacao` repete os totais dele.
- **R-E06.1-6, identidade do "atual":** `opcoes.metodos_assinatura` traz, por método, o `metodo_id`, a `versao` e as `parametros`/assinaturas de perfil que o `infer_pdf` expõe (legado, `e06-estais-v3`, `e05-transformadores-v5`, `package_sha256`), mais a versão da PyMuPDF. O `tempo_s` é declarado no `.md` como "inclui o `tracemalloc` de `infer_pdf`".

## Review Focus

1. Referência com bbox de área zero ou predição com bbox degenerada (polilinha fina do estai) não pode quebrar o casamento nem dividir por zero → caso na Task 1.
2. Folha com `sha256` diferente, PDF ausente, caminho por `avaliacao-cega` ou detector que falha → falha saneada daquela folha ou método, sem caminho absoluto, e as outras seguem → testes na Task 1.
3. Símbolo de referência com centro fora das regiões, mas casado com uma predição, conta TP, não `fora_das_regioes` → teste na Task 1.
4. Página com desenhos `clip`/`group` intercalados: o índice cru de cada caminho tem de apontar para o desenho certo de `get_drawings(extended=True)` → teste na Task 2.
5. Número com mais de 4 casas decimais ou hex de 64 caracteres num pacote → a guarda reprova → teste negativo na Task 3.

---

## File Structure

| Arquivo | Ação | Responsabilidade | Task |
|---|---|---|---|
| `scripts/benchmark_simbolos_ficha.py` | criar | benchmark diagnóstico de símbolos contra as fichas da rodada, `--processos` | 1 |
| `tests/unit/test_benchmark_simbolos_ficha.py` | criar | rodada sintética com 2 PDFs gerados no teste | 1 |
| `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py` | modificar | `pagina_modelo_com_indices(pagina, indice, tabela=None)` | 2 |
| `tests/unit/test_pymupdf_drawing_model_pagina.py` | criar | igualdade com `extrair_modelo_desenho` e índice cru com `clip`/`group` | 2 |
| `tests/unit/test_symbol_packages_sem_memorizacao.py` | criar | guarda contra coordenada, hash e nome de folha nos pacotes | 3 |

## Tarefas e ondas

| Task | Estimativa | Depende de | Risco | Laboratório |
|---|---|---|---|---|
| 1 — benchmark de símbolos contra as fichas | 45 min | nenhuma | alto (entrada externa, concorrência) | não |
| 2 — página do modelo com índice cru | 30 min | nenhuma | alto (parsing de PDF) | não |
| 3 — guarda contra memorização | 20 min | nenhuma | normal | não |

Com duas etapas abertas, cada onda tem até 2 tarefas. Onda 1: Tasks 1 e 2. Onda 2: Task 3. Os arquivos são disjuntos. Soma: ~1h35, mais revisão e fechamento.

---

### Task 1: benchmark de símbolos contra as fichas

**Files:**
- Create: `scripts/benchmark_simbolos_ficha.py`
- Test: `tests/unit/test_benchmark_simbolos_ficha.py`

**Interfaces:**
- Consumes:
  - `scripts.symbol_benchmark_runner.infer_pdf(source, document_id, *, include_transformers, include_guys, include_packages, ...) -> tuple[Record, list[Record], list[Record]]` (manifesto, predições, …). Confira no código os nomes reais das chaves de predição (`class_id`, `bbox` normalizada da página exibida, página, `method_id`, `context`) e do manifesto (`failures`, `status`);
  - `scripts.symbol_benchmark_evaluator.geometry_match(a, b) -> dict`, usando `["eligible"]`;
  - `scripts.ficha_poste.carregar_ficha(path)`. O teste "centro na região" é reimplementado localmente, sem importar o privado `_centro_na_regiao`;
  - `zeny_project_handler.adapters.analysis.pymupdf_drawing_model.impressao_estrutural` e `drawing_model.family.reconhecer_familia`.
- Produces:
  - constantes `TOLERANCIA_CENTRO: Final = 0.005`, `RAIO_POSTE_PENDENTE: Final = 0.05` e `ESQUEMA: Final = "simbolos-ficha-v1"`;
  - `METODOS: Final[dict[str, Callable[[Path, str], ResultadoMetodo]]]`, por enquanto `{"atual": _predicoes_atual}`, com funções de nível de módulo. A E06.2 acrescenta `"modelo"`. `ResultadoMetodo = {"predicoes": [{"pagina": int, "classe": str, "bbox": [x0, y0, x1, y1], "metodo": str, "contexto": str}], "assinatura": dict, "falha": str | None}`;
  - `casar(referencias: Sequence[dict], predicoes: Sequence[dict], criterio: Literal["centro", "iou"]) -> list[tuple[int, int]]`, com pares de índices (R-E06.1-2);
  - `medir_pdf(pdf: Path, referencia: dict, pdf_id: str, metodos: Sequence[str]) -> dict`: uma folha, os dois critérios, `tempo_s` por método e `familia`;
  - `medir_simbolos(rodada: Path, saida: Path, *, metodos: Sequence[str] = ("atual",), processos: int = 1) -> dict`, que grava `simbolos-ficha.json` e `simbolos-ficha.md` em `saida` e devolve o relatório;
  - CLI `python -m scripts.benchmark_simbolos_ficha --rodada DIR --saida DIR [--metodo atual ...] [--processos N]`. `N` é inteiro ≥ 1: 0 ou negativo dá exit 2 do argparse. O efetivo é `min(N, folhas, 61)`, e o `.md` mostra "Processos: <pedido> (efetivos: <efetivo>)".
- Relatório:
  - `{"schema_version", "opcoes": {"metodos", "metodos_assinatura", "criterios": ["centro", "iou"], "tolerancia_centro", "raio_poste_pendente", "classes_avaliadas", "pymupdf"}, "por_pdf", "total", "por_familia"}`;
  - para cada método e critério, `por_classe[classe] = {"tp", "fp", "fn", "precisao", "recall"}`, mais `fora_do_escopo`, `fora_das_regioes`, `perto_de_poste_pendente`, `contexto_nao_desenho` e `duplicatas` (predições da mesma classe com centro na caixa uma da outra, por método). Taxa com denominador 0 → `null`;
  - folha que falha → `{"situacao": "falha", "erro": <primeira linha saneada>}`, e as outras seguem. Método que falha numa folha segue a R-E06.1-5;
  - `tempo_s` só em `por_pdf`. Nenhum caminho absoluto nem nome de PDF: só o `pdf_id` da rodada.
- Localização do PDF:
  - lê `rodada.json` (`raiz_corpus` relativo à rodada + `pdfs[*].caminho_relativo`);
  - **antes de qualquer I/O do arquivo**, recusa como falha o caminho que tenha um componente `avaliacao-cega`;
  - depois confere o `sha256` contra `referencia["pdf_sha256"]`;
  - a referência fica em `pdfs/<pdf_id>/ficha/referencia.json`, e a folha sem referência fica `sem_referencia`.
- Paralelismo:
  - com `processos > 1` e mais de 1 folha, `ProcessPoolExecutor(max_workers=efetivo)` + `pool.map` na ordem do `rodada.json`, no padrão de `scripts/benchmark_texto_ficha.py:406-419`;
  - `BrokenProcessPool` → as folhas sem resultado viram falha, e o relatório é gravado mesmo assim.

- [ ] **Step 1: Write the failing tests.** Gere no teste uma rodada sintética em `tmp_path`:
  - 2 PDFs de 1 página desenhados com PyMuPDF, com formas que o "atual" reconhece de verdade. Reaproveite os construtores de fixture dos testes de `pymupdf_symbols`, `pymupdf_guys` ou `pymupdf_transformers`, por exemplo um aterramento e um estai sintéticos;
  - `rodada.json` com `raiz_corpus` relativo;
  - fichas de referência válidas por `scripts.ficha_poste.validar_ficha`.

  Testes:
  - `test_casar_por_centro_e_um_para_um`: 2 referências da mesma classe e 3 predições → 2 pares, sem predição repetida, na ordem do R-E06.1-2;
  - `test_casar_iou_nao_casa_polilinha_fina_que_centro_casa`: predição de caixa degenerada (largura 0) no meio da referência → `centro` casa e `iou` não, sem exceção;
  - `test_classe_fora_do_escopo_nao_e_fp`, `test_predicao_fora_das_regioes_nao_e_fp`, `test_predicao_perto_de_poste_pendente_nao_e_fp` e `test_contexto_de_legenda_nao_e_fp`;
  - `test_referencia_fora_da_regiao_casada_conta_tp` (Review Focus 3);
  - `test_poste_pendente_nao_engole_tp_do_vizinho`: um poste pendente a 0,03 de um poste com símbolo casado → o TP continua TP;
  - `test_medir_simbolos_na_rodada_sintetica`: o "atual" sobre os 2 PDFs → `tp` ≥ 1 na classe desenhada (positivo), `fn` = 1 numa referência sem desenho (negativo) e `familia` e `metodos_assinatura` presentes;
  - `test_falha_de_detector_tira_o_metodo_dos_totais`: com `monkeypatch`, um detector de `infer_pdf` levanta erro → o método naquela folha fica `situacao: "falha"` e fora dos totais. Rode serial, porque o `monkeypatch` não atravessa o spawn;
  - `test_processos_2_igual_a_serial`: os JSON, carregados, são iguais depois de remover `tempo_s`;
  - `test_sha_diferente_e_falha_saneada`: sem `str(tmp_path)` no JSON;
  - `test_caminho_avaliacao_cega_e_recusado_sem_ler`: o `caminho_relativo` aponta para `avaliacao-cega/x.pdf` em `tmp_path`, e um `monkeypatch` em `Path.read_bytes`/`open`, em `pymupdf.open` e em `infer_pdf` acusa qualquer uso daquele caminho → falha, sem leitura;
  - `test_cli_processos_invalido` → `SystemExit` com código 2;
  - `test_relatorio_sem_caminho_absoluto_nem_nome_de_pdf`.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_simbolos_ficha.py -q` → FAIL (`ModuleNotFoundError`).
- [ ] **Step 3:** implemente `scripts/benchmark_simbolos_ficha.py`.
- [ ] **Step 4:** o mesmo comando → PASS; `ruff check`, `ruff format --check` e `mypy` limpos.
- [ ] **Step 5: Commit** (`feat: benchmark de simbolos contra as fichas de referencia`).

### Task 2: página do modelo com índice cru

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py`
- Test: `tests/unit/test_pymupdf_drawing_model_pagina.py`

**Interfaces:**
- Consumes: `_ler_fontes(pagina)`, `_montar_pagina(indice, pagina, fontes, tabela=None)`, `_desenhos(pagina)` e `_TIPOS_CAMINHO` (mesmo módulo).
- Produces: `pagina_modelo_com_indices(pagina: pymupdf.Page, indice: int, tabela: TabelaGlifos | None = None) -> tuple[PaginaModelo, tuple[int, ...]]`.
  - O primeiro elemento é igual a `extrair_modelo_desenho(pdf, tabela).paginas[indice]` para a mesma página.
  - O segundo tem um item por `caminhos[i]` do modelo: a posição, em `pagina.get_drawings(extended=True)`, do desenho que originou `caminhos[i]`.
  - `get_drawings` é chamado uma vez só por chamada.
  - Não muda o cache, o formato do modelo nem `VERSAO_MODELO_DESENHO`.

- [ ] **Step 1: Write the failing tests:**
  - `test_pagina_modelo_igual_a_extracao_do_documento`: PDF sintético com linhas, retângulo, círculo e texto → o modelo da função é igual a `extrair_modelo_desenho(pdf).paginas[0]`;
  - `test_indices_crus_apontam_para_o_desenho_de_origem`: PDF sintético cujo `get_drawings(extended=True)` traz itens `clip`/`group` intercalados. Pode vir de `page.show_pdf_page` de outra página com clip ou de um Form XObject com clip; o teste afirma antes que há ao menos um `clip` ou `group` na lista crua. Para cada `i`, o desenho cru em `indices[i]` tem o mesmo `rect` e os mesmos itens geométricos do caminho `i`, numa comparação aproximada e na mesma transformação;
  - `test_pagina_sem_desenhos` → `(modelo, ())`;
  - `test_get_drawings_chamado_uma_vez`: `monkeypatch` conta as chamadas → 1.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_pymupdf_drawing_model_pagina.py -q` → FAIL (`ImportError`).
- [ ] **Step 3:** implemente. Se `_ler_fontes` já chama `get_drawings`, guarde os índices crus em `_Fontes` em vez de chamar de novo. `scripts/complexity_gate.py src` continua aprovado.
- [ ] **Step 4:** o mesmo comando e mais `-k "drawing_model"` → PASS; ruff, format e mypy limpos.
- [ ] **Step 5: Commit** (`feat: pagina do modelo de desenho com indice cru dos caminhos`).

### Task 3: guarda contra memorização

**Files:**
- Test: `tests/unit/test_symbol_packages_sem_memorizacao.py`

**Interfaces:**
- Consumes: os JSON de `src/zeny_project_handler/adapters/analysis/symbol_packages/`, por caminho derivado de `Path(__file__)`, nunca do cwd.
- Produces: `verificar_pacote(dados: Any) -> list[str]`, função do próprio módulo de teste que devolve as violações. A E06.2 e a E06.3 vão estender a guarda às gramáticas novas.

Regras, aplicadas a todo valor de todo pacote:
- nenhum `float` (nem string numérica) com mais de 4 casas decimais, que seria coordenada de folha;
- nenhuma string que contenha um hexadecimal de 64 caracteres, que seria sha256 de PDF;
- nenhuma string com `.pdf`. Hoje há 0 ocorrências;
- nenhuma string com o padrão de nome de folha real, montado por concatenação no teste (`"PROJETO" + " DE REDE"`, sem diferenciar maiúsculas), para o `git grep` do fechamento não achar o próprio teste.

- [ ] **Step 1:** escreva `test_pacotes_reais_passam_na_guarda` (todos os pacotes → `[]`) e, parametrizado, `test_guarda_reprova` com 4 casos sintéticos: float `0.123456`, hex de 64 caracteres, nome de folha montado por concatenação e `"folha.pdf"`. Cada um → 1 violação.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_symbol_packages_sem_memorizacao.py -q` → PASS nos reais e nos 4 negativos. O teste nasce verde nos reais, porque a guarda protege as próximas subetapas; os 4 negativos provam que ela não passa à toa.
- [ ] **Step 3: Commit** (`test: guarda contra memorizacao de folha nos pacotes`).

---

## Fechamento operacional (orquestrador, antes da revisão final)

1. Rode a partir do worktree da trilha A, com o `.venv` dele: `.venv/Scripts/python.exe -m scripts.benchmark_simbolos_ficha --rodada <checkout principal>/tmp/curadoria-simbologia/20261103-2300-fichas --saida <checkout principal>/tmp/e06/simbolos-atual --processos <n>`. O `<n>` é 20 ÷ suítes e benchmarks simultâneos da sessão, com mínimo de 2.
2. Leve ao handoff os totais por classe, família e folha nos dois critérios, mais `fora_do_escopo`, `fora_das_regioes`, `perto_de_poste_pendente`, `contexto_nao_desenho`, `duplicatas`, falhas de método e tempo por folha.
3. `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → `"errors": []`, com os pacotes inalterados.
4. `git grep -n "PROJETO DE REDE NS"` só acha as linhas que citam o critério.
5. `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`, sem outra suíte da sessão rodando.

## Critérios de aceite → evidência

| Critério | Evidência |
|---|---|
| fixtures sintéticas positivas e negativas | Tasks 1, 2 e 3 |
| auditor com 0 erros | passo 3 do fechamento |
| baseline diagnóstico do atual em `tmp/`, totais no handoff | passos 1 e 2 do fechamento |
| guarda verde | Task 3 |
| `.bat` aprovado | passo 5 |

---

## Emenda durante a execução (R12)

### Task 4: teste intermitente do `job_store`

- **Estimativa:** 30 min. **Depende de:** nenhuma. **Risco:** normal. **Laboratório:** não.
- **Por que entra:** `tests/server/test_jobs_api.py::test_job_store_accepts_complete_state_matrix_without_progress_regression` falha de forma intermitente, mesmo isolado e sem nenhum arquivo da E06.1. Na branch da trilha A, em 2026-11-05, o resultado foi 1 falha em 3 execuções: `limited.prune() == 2`, mas o job mais antigo continua existindo. Pela regra da E14, teste intermitente é defeito e é corrigido, nunca repetido. Ele ameaça o `.bat` de todas as etapas.

**Files:**
- Modify: o que a investigação provar ser a causa, só entre `src/zeny_project_handler_server/job_store.py` e `tests/server/test_jobs_api.py`. Os dois são disjuntos da E15 e da E17.

**Interfaces:**
- Consumes/Produces: o contrato público de `job_store` (`prune`, ordenação e retenção) não muda. Se a causa for de produção, por exemplo empate de timestamp na ordenação, o desempate tem de ser determinístico (por exemplo, pela ordem de criação) e documentado na docstring.

- [ ] **Step 1:** use `superpowers:systematic-debugging`. Reproduza com `for i in $(seq 1 20); do .venv/Scripts/python.exe -m pytest "tests/server/test_jobs_api.py::test_job_store_accepts_complete_state_matrix_without_progress_regression" -q -p no:cacheprovider | tail -1; done` e registre a taxa de falha. Ache a causa: empate de relógio, resolução do `datetime`/`time` no Windows ou ordem não determinística.
- [ ] **Step 2:** escreva um teste determinístico que reproduza a causa sempre, por exemplo com relógio injetado ou dois jobs com o mesmo timestamp, e veja-o falhar.
- [ ] **Step 3:** corrija a causa, na produção ou no teste, conforme o que a investigação provar. Não use `sleep`, nem retry, nem afrouxe asserção.
- [ ] **Step 4:** o mesmo laço de 20 execuções → 20/20 verdes; `tests/server/test_jobs_api.py` inteiro verde; ruff, format e mypy limpos.
- [ ] **Step 5: Commit** (`fix: ...` ou `test: ...`, conforme a causa).

Onda 2 passa a ter as Tasks 3 e 4, com arquivos disjuntos.

## Revisão de arquitetura

- **Veredito:** aprovado com notas.
- **Rodadas:** 1. A rodada 0 bloqueou com I1–I5 e M1–M12, e a rodada 1 aprovou com notas.
- **Modelo:** opus (`revisor-arquitetura`).
- **Notas Menores, aplicadas:**
  - a pendência da entrevista sobre o runner opt-in foi para o roadmap (E06.2) e vai para o handoff da E06.1;
  - a comparação entre métodos usa a interseção das folhas (R-E06.1-5b);
  - o teste de `avaliacao-cega` intercepta também `pymupdf.open` e `infer_pdf`;
  - a E06.3 precisa listar `tests/server/test_e14_symbol_review.py:287` na File Structure;
  - a Task 1 está no limite de 45 min; se estourar, o paralelismo e a CLI viram tarefa própria;
  - M12: não há ARCHITECTURE.md.
