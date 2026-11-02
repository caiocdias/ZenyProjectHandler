# E02 — Ficha de referência e benchmark por poste Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Definir o formato da ficha do poste (JSON Schema versionado), um avaliador determinístico que compara ficha de referência e ficha predita com as métricas da decisão 7 do design, e um CLI que extrai a ficha predita do analisador vigente para um PDF, avalia e grava o relatório.

**Architecture:** Ferramenta de benchmark em `scripts/`, no mesmo lugar dos benchmarks vivos (`benchmark_network_pdf`, `symbol_benchmark_evaluator`), sem tocar o produto. O formato é um JSON Schema em `docs/schemas/`, validado pelo validador de subconjunto já existente (`scripts.curation_reference.validar_esquema`) mais regras semânticas em Python. O avaliador é puro (dict → dict). A ficha predita é derivada do resultado promovido do pipeline atual, obtido por `scripts.benchmark_network_pdf.run_variant`.

**Tech Stack:** Python 3.11, stdlib, PyMuPDF (só via `run_variant`), pytest, ruff, mypy strict.

**Spec:** seção "E02 — Ficha de referência e benchmark por poste" de `docs/roadmap-leitura-vetorial-por-poste.md`; decisão 7 e "Fronteiras" de `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md`.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o cliente não importa nada do servidor (`client_artifact_gate`); DTOs seguem `tests/contracts/test_architecture.py`.
- Nenhum arquivo de `src/` muda nesta etapa; a ficha não é entidade persistida e não há migração.
- PDFs reais, recortes, rótulos, conjuntos de dados e pesos treinados nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa.
- O relatório não traz caminho absoluto nem conteúdo da folha além do necessário (só `pdf_sha256`, ids, páginas, bboxes normalizadas e os valores dos campos avaliados).
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos.
- Documentação enxuta: atualize só o que a mudança torna falso ou o que um operador precisa para usar o CLI novo.
- Nenhuma dependência nova (não há `jsonschema` no projeto: use `scripts.curation_reference.validar_esquema`).
- Commits com o parágrafo final exatamente `Soul: <soul>` seguido de `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, sem linha em branco entre os dois.

## Ambiente de execução (vale para todas as tarefas)

O harness recusa `cmd.exe` e scripts bash; rode cada comando simples, da raiz do worktree, com caminhos literais (sem variáveis de shell nem laços em volta de git/python). Escreva arquivos só com Edit/Write. Gate equivalente ao `IniciarTestes.bat`, com `PYTHONUTF8=1` e `QT_QPA_PLATFORM=offscreen`, aprovado = todos com exit 0:

```bash
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe scripts/client_artifact_gate.py --source-only
.venv/Scripts/python.exe -m pytest --basetemp=/c/tmp/zph-<algo-unico> --cov --cov-report=term --cov-fail-under=85.01
.venv/Scripts/python.exe scripts/complexity_gate.py src
```

A suíte completa leva ~10 min (HEAD da E01: 2588 passed, cobertura 88,24%); rode-a em background ou com timeout de 600000.

## Rulings de planejamento

- **R1 — lugar do código.** A E02 é ferramenta de medição, não produto: fica em `scripts/` como os benchmarks vivos. A montagem de ficha do produto é da E07, em `application/`.
- **R2 — fonte da ficha predita.** A ficha predita vem do **projeto promovido** (`Poste`, `EstruturaMt/Bt`, `Equipamento`, `Cabo` e `detectar_vaos`), que é o que o pipeline entrega às etapas seguintes. Propostas pendentes não promovidas não entram. Custo se errado: o baseline subestima o recall do analisador atual; a E03 mede e, se preciso, a fonte muda com versão nova do protocolo.
- **R3 — validação de schema.** Reuso de `scripts.curation_reference.validar_esquema` (subconjunto do Draft 2020-12 já usado no repositório). O schema novo só usa as palavras que ele implementa.
- **R4 — casamento de postes.** Guloso determinístico sobre pares elegíveis ordenados (identificador igual primeiro, depois distância), com limiares versionados em `PROTOCOLO_FICHA`; não é atribuição ótima. Custo se errado: em folhas densas um par subótimo pode trocar dois postes vizinhos; os limiares são calibráveis na E03 com nova versão do protocolo.

## Review Focus

- Dois vãos entre o mesmo par de postes (cabos MT e BT): o formato e o avaliador aceitam e casam por cabo, não colapsam (Task 2, `test_dois_vaos_no_mesmo_par_casam_por_cabo`).
- Referência regional: predição fora das regiões anotadas não conta como FP, e vão com uma ponta fora também não (Task 2, `test_referencia_regional_ignora_predicao_fora_das_regioes`).
- Denominador zero (folha sem poste na referência ou na predição): métricas viram `null`, nunca divisão por zero (Task 2, `test_denominador_zero_da_none`).
- Ordem de entrada diferente produz o mesmo relatório (Task 2, `test_resultado_deterministico_independe_da_ordem`).
- Referência de outro PDF: recusada antes de rodar o analisador (Task 3, `test_referencia_de_outro_pdf_e_recusada`).

---

### Task 1: Formato da ficha do poste e validação

**Files:**
- Create: `docs/schemas/ficha-poste.schema.json`
- Create: `scripts/ficha_poste.py`
- Test: `tests/unit/test_ficha_poste.py`

**Interfaces:**
- Consumes: `scripts.curation_reference.validar_esquema(valor, esquema) -> list[str]` (existente).
- Produces:
  - `CAMINHO_ESQUEMA: Path` (= `<raiz>/docs/schemas/ficha-poste.schema.json`)
  - `validar_ficha(dados: Mapping[str, Any]) -> list[str]` — lista vazia = válida; mensagens em português com o caminho do campo.
  - `carregar_ficha(caminho: Path) -> dict[str, Any]` — lê UTF-8, valida e levanta `ValueError` com os erros juntados por `"; "`.

**Formato (exato).** Schema `"$schema": "https://json-schema.org/draft/2020-12/schema"`, `"$id": "urn:zeny:benchmark:ficha-poste:1"`, `title` e `description` em português dizendo a convenção de coordenadas: a mesma de `symbols-e02-v1` (página exibida, [0,1], origem no canto superior esquerdo). Todo objeto tem `additionalProperties: false`, exceto `atributos_extras`.

```text
raiz (todos obrigatórios):
  schema_version   const 1
  tipo             enum ["referencia", "predicao"]
  pdf_sha256       string, pattern ^[0-9a-f]{64}$
  escopo_anotacao  { tipo: enum ["completo","regional"] (obrigatório), regioes: [ {pagina: integer >=1, bbox} ] (opcional) }
  postes           array de poste
  vaos             array de vao
poste (obrigatórios: todos menos atributos_extras):
  id               string minLength 1
  pagina           integer >= 1
  bbox             array de 4 números em [0,1], minItems 4, maxItems 4  ([x0, y0, x1, y1])
  identificador    string minLength 1 | null
  estruturas       array de string minLength 1
  poste            string minLength 1 | null
  coordenada       { leste: number, norte: number } | null
  simbolos         array de { classe: string minLength 1, bbox }
  atributos_extras object livre (ignorado pela métrica)
vao (todos obrigatórios):
  de, para         string minLength 1 (ids de poste)
  comprimento_m    number >= 0 | null
  cabo             string minLength 1 | null
```

Regras semânticas em `validar_ficha` (além do schema): ids de poste únicos; `de` e `para` existem em `postes` e são diferentes; `x0 <= x1` e `y0 <= y1` em toda bbox; `escopo_anotacao.tipo == "regional"` exige `regioes` com pelo menos 1 item e `"completo"` proíbe `regioes`; `tipo == "predicao"` exige escopo `"completo"`; numa referência regional, o centro de cada poste está dentro de alguma região da mesma página. Vários vãos entre o mesmo par de postes são permitidos.

- [ ] **Step 1: Testes que falham** em `tests/unit/test_ficha_poste.py`, com um construtor local `_ficha_completa()` (2 postes na página 1, um com coordenada, estruturas, poste e 1 símbolo; 1 vão com comprimento e cabo; `atributos_extras` com uma chave qualquer):
  - `test_ficha_completa_e_valida`: `validar_ficha(_ficha_completa()) == []`.
  - `test_schema_carrega_e_usa_so_palavras_suportadas`: o schema lido de `CAMINHO_ESQUEMA` valida a ficha completa via `validar_esquema` sem `ValueError`.
  - `test_campo_extra_e_recusado` (parametrizado: na raiz, num poste, num vão, num símbolo, em `coordenada`): cada caso devolve pelo menos um erro.
  - `test_atributos_extras_aceitam_qualquer_chave`.
  - `test_campo_obrigatorio_ausente_e_recusado` (parametrizado em `pdf_sha256`, `postes`, `postes[0].estruturas`, `vaos[0].cabo`).
  - `test_vao_com_poste_inexistente_ou_laco_e_recusado`.
  - `test_id_de_poste_repetido_e_recusado`.
  - `test_bbox_invertida_ou_fora_de_0_1_e_recusada`.
  - `test_escopo_regional_exige_regioes_e_completo_as_proibe`.
  - `test_predicao_exige_escopo_completo`.
  - `test_poste_de_referencia_regional_fora_das_regioes_e_recusado`.
  - `test_dois_vaos_no_mesmo_par_sao_validos`.
  - `test_carregar_ficha_levanta_com_erros` (arquivo em `tmp_path` com campo extra → `ValueError`).
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_ficha_poste.py -v` → falham por módulo inexistente.
- [ ] **Step 3: Implementar** o schema e `scripts/ficha_poste.py` (docstring de módulo em português dizendo o propósito e a convenção de coordenadas).
- [ ] **Step 4:** o mesmo comando → todos passam.
- [ ] **Step 5: Gate completo** → todos exit 0.
- [ ] **Step 6: Commit** `feat: formato versionado da ficha do poste e validação`.

### Task 2: Avaliador determinístico por poste

**Files:**
- Create: `scripts/ficha_poste_avaliador.py`
- Test: `tests/unit/test_ficha_poste_avaliador.py`

**Interfaces:**
- Consumes: `scripts.ficha_poste.validar_ficha` (Task 1); `scripts.symbol_benchmark_evaluator.geometry_match(first, second) -> dict` (existente; recebe dicts com `"bbox"` e devolve `"eligible"` e `"iou"`).
- Produces:
  - `PROTOCOLO_FICHA: Final[Mapping[str, Any]] = {"id": "ficha-poste-v1", "distancia_max": 0.02, "distancia_max_mesmo_identificador": 0.05, "tolerancia_coordenada_m": 0.01, "tolerancia_comprimento_m": 0.1}`
  - `normalizar_texto(valor: str | None) -> str | None` — `strip`, espaços internos colapsados em um, maiúsculas; vazio → `None`.
  - `casar_postes(referencia: Sequence[Mapping[str, Any]], predicao: Sequence[Mapping[str, Any]]) -> list[tuple[str, str, float]]` — pares `(id_ref, id_pred, distancia)`.
  - `avaliar(referencia: Mapping[str, Any], predicao: Mapping[str, Any]) -> dict[str, Any]`.

**Regras (exatas).**
- Distância = euclidiana entre centros de bbox, só na mesma página. Par elegível se `distancia <= distancia_max`, ou se os dois identificadores normalizados são iguais e não nulos e `distancia <= distancia_max_mesmo_identificador`. Ordenação dos elegíveis: `(0 se identificadores iguais e não nulos senão 1, distancia, id_ref, id_pred)`; escolha gulosa um-para-um.
- `avaliar` recusa com `ValueError`: ficha inválida (mensagens de `validar_ficha`), `referencia["tipo"] != "referencia"`, `predicao["tipo"] != "predicao"`, `pdf_sha256` diferentes.
- Escopo regional: antes do casamento, postes preditos cujo centro não está em nenhuma região da mesma página são descartados, com seus símbolos e com os vãos que tocam algum poste descartado.
- Postes: TP = pares; FP = preditos não casados; FN = referência não casados.
- Campos, sobre os pares: `identificador` e `poste` contam quando o valor de referência não é nulo, acerto = textos normalizados iguais; `estruturas` conta sempre, acerto = listas normalizadas e ordenadas iguais; `coordenada` conta quando a de referência não é nula, acerto = predita não nula e `|Δleste|` e `|Δnorte|` ≤ `tolerancia_coordenada_m`.
- Vãos: um vão de referência `(a, b)` só pode casar com vão predito entre `m(a)` e `m(b)` (não ordenado, `m` = mapa do casamento). Dentro do mesmo par de postes, casar primeiro os de cabo normalizado igual e não nulo; os restantes em ordem de `(comprimento_m is None, comprimento_m, cabo or "")` dos dois lados. TP/FP/FN como nos postes. `comprimento` conta nos vãos casados com comprimento de referência não nulo (acerto = predito não nulo e `|Δ| <= tolerancia_comprimento_m`); `cabo` conta nos casados com cabo de referência não nulo (acerto = normalizados iguais).
- Símbolos: dentro de cada par de postes, casar símbolos com `classe` normalizada igual e `geometry_match(...)["eligible"]`, guloso por `iou` decrescente e depois índices. Não casados → FP (preditos) e FN (referência); símbolos de postes não casados também são FP/FN.
- Taxas: `precisao = tp/(tp+fp)`, `recall = tp/(tp+fn)`, `taxa = acertos/total`; denominador 0 → `None`.
- `atributos_extras` nunca é lido.

**Relatório (chaves exatas):**

```text
{ "schema_version": 1, "protocolo": PROTOCOLO_FICHA, "pdf_sha256": str, "escopo": "completo"|"regional",
  "postes":   {"tp","fp","fn","precisao","recall"},
  "campos":   {"identificador"|"estruturas"|"poste"|"coordenada": {"acertos","total","taxa"}},
  "vaos":     {"tp","fp","fn","precisao","recall","comprimento":{"acertos","total","taxa"},"cabo":{"acertos","total","taxa"}},
  "simbolos": {"tp","fp","fn","precisao","recall"},
  "pares":    [ {"referencia": id, "predicao": id, "distancia": float, "campos": {campo: bool|None}} ]  (ordenado por id de referência),
  "nao_casados": {"referencia": [ids ordenados], "predicao": [ids ordenados]} }
```

`campos` de cada par usa `None` quando o campo não conta naquele par.

- [ ] **Step 1: Testes que falham** em `tests/unit/test_ficha_poste_avaliador.py`. Use construtores locais de ficha (válidas pelo `validar_ficha` da Task 1):
  - `test_acerto_total_tem_todas_as_metricas_em_um`: predição = referência com `tipo="predicao"` e ids diferentes → postes, campos, vãos, comprimento, cabo e símbolos com precisão/recall/taxa `1.0`.
  - `test_simbolo_no_poste_vizinho_conta_fp_e_fn`: mesmo símbolo (classe e bbox) ligado ao poste vizinho na predição → `simbolos == {tp: n-1, fp: 1, fn: 1, ...}` e postes intactos.
  - `test_poste_ausente_reduz_recall_e_vao_vira_fn`: predição sem um poste de 3 → `postes.fn == 1`, `recall == 2/3`, o vão que tocava o poste ausente em `vaos.fn`.
  - `test_vao_com_comprimento_errado_casa_mas_erra_comprimento`: 35 m contra 40 m → `vaos.tp == 1`, `comprimento == {acertos: 0, total: 1, taxa: 0.0}`, `cabo.taxa == 1.0`.
  - `test_dois_vaos_no_mesmo_par_casam_por_cabo`: referência com MT e BT no mesmo par, predição com a ordem trocada → `vaos.tp == 2`, `cabo.taxa == 1.0`.
  - `test_referencia_regional_ignora_predicao_fora_das_regioes`: poste predito fora da região, com um vão até um poste dentro → não aparece em `postes.fp` nem `vaos.fp` e não está em `nao_casados.predicao`.
  - `test_identificador_igual_casa_ate_distancia_maior`: centros a 0,04 com o mesmo identificador → casam; com identificadores diferentes → não casam (1 FP, 1 FN).
  - `test_erro_de_campo_conta_so_no_campo`: identificador, poste, estruturas e coordenada errados num par → postes TP e cada campo com `acertos == 0`.
  - `test_atributos_extras_nao_afetam_metricas`.
  - `test_denominador_zero_da_none`: referência e predição sem postes → `precisao` e `recall` `None` em postes, vãos e símbolos.
  - `test_pdf_ou_tipo_errado_e_recusado` (parametrizado: sha diferente, referência com `tipo="predicao"`, predição com `tipo="referencia"`, ficha inválida).
  - `test_resultado_deterministico_independe_da_ordem`: listas embaralhadas com `random.Random(7)` → relatório igual.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_ficha_poste_avaliador.py -v` → falham.
- [ ] **Step 3: Implementar** `scripts/ficha_poste_avaliador.py`. Funções com complexidade ciclomática < 31 (gate Radon E/F); quebre por responsabilidade (casamento, campos, vãos, símbolos, escopo).
- [ ] **Step 4:** o mesmo comando → todos passam.
- [ ] **Step 5: Gate completo** → todos exit 0.
- [ ] **Step 6: Commit** `feat: avaliador determinístico de fichas por poste`.

### Task 3: Ficha predita do analisador vigente, CLI e baseline sintético

**Files:**
- Create: `scripts/benchmark_ficha_poste.py`
- Test: `tests/unit/test_benchmark_ficha_poste.py`
- Modify: `examples/README.md` (um parágrafo com o comando do CLI, como os outros comandos sobre `examples/`; saída sempre em `tmp/`)

**Interfaces:**
- Consumes: `scripts.benchmark_network_pdf.run_variant(source, directory, *, ocr, telemetry=False, complementary=False) -> dict` (existente; chaves usadas: `"project"` (`Projeto` promovido), `"decisions"` (`DecisaoRevisao | None` por proposta), `"semantic"` (com `.elementos`)); `zeny_project_handler.application.spans.detectar_vaos(projeto)`; `scripts.ficha_poste.validar_ficha`, `carregar_ficha`; `scripts.ficha_poste_avaliador.avaliar`.
- Produces:
  - `ficha_predita(variante: Mapping[str, Any], pdf_sha256: str) -> dict[str, Any]`
  - `executar(pdf: Path, referencia: Path, saida: Path, *, native_only: bool, runtime_directory: Path) -> dict[str, Any]` — devolve o relatório de `avaliar`.
  - `main(argumentos: list[str] | None = None) -> int` — `python -m scripts.benchmark_ficha_poste PDF --referencia REF --saida DIR [--native-only] [--runtime-directory DIR]` (padrão de `--runtime-directory`: `tmp/benchmark-runtime`, o mesmo de `benchmark_network_pdf`).

**Mapeamento da ficha predita (R2).** `tipo="predicao"`, escopo `{"tipo": "completo"}`.
- Um poste por `Poste` do projeto promovido com `geometria` não nula: `id = str(elemento.id)`; `pagina` = número da página de `geometria.pagina_id` em `projeto.documentos[*].paginas`; `bbox = [min x, min y, max x, max y]` dos pontos da geometria, na convenção `symbols-e02-v1` (confira como `scripts/symbol_benchmark_runner.py` converte geometrias de proposta em bbox e use a mesma conversão); `identificador = identificador_operacional`; `poste = codigo_observado`; `coordenada = {"leste": float, "norte": float}` de `coordenada_campo` ou `None`; `estruturas` = `codigo_observado` não nulos das `EstruturaMt`/`EstruturaBt` com `poste_id` igual, ordenados; `atributos_extras = {}`.
- Símbolos: `Equipamento` com `poste_id` do poste cuja proposta de origem (a decisão em `"decisions"` com `elemento_confirmado_id == equipamento.id` → `proposta_id` → proposta em `semantic.elementos`) tem o atributo `simbolo_classe` não nulo; `classe` = esse valor; `bbox` da geometria do equipamento. Equipamento sem `simbolo_classe` ou sem geometria fica fora.
- Vãos: `detectar_vaos(projeto)` com `poste_origem_id` e `poste_destino_id` entre os postes da ficha: `de`/`para` = ids desses postes; `comprimento_m` = `float` ou `None`; `cabo` = `codigo_observado` do `Cabo` de `cabo_id` (ou `None`).

**`executar`:** lê e valida a referência (`carregar_ficha`); calcula o SHA-256 do PDF e recusa com `ValueError` se for diferente do da referência, **antes** de rodar o analisador; prepara o OCR como `benchmark_network_pdf.benchmark` faz (com `--native-only`, sem OCR; sem a opção, `inspect_tesseract_runtime` e exigência de português); roda `run_variant` num `TemporaryDirectory` criado dentro de `saida`; monta a ficha predita, valida, avalia; grava `saida/ficha-predita.json` e `saida/avaliacao.json` (UTF-8, `ensure_ascii=False`, `indent=2`, `sort_keys=True`); confere que tamanho, mtime e SHA-256 do PDF não mudaram. Nenhum dos arquivos gravados contém caminho absoluto nem o nome do PDF.

- [ ] **Step 1: Testes que falham** em `tests/unit/test_benchmark_ficha_poste.py`, usando `tests.pdf_fixtures.create_network_benchmark_pdf` (2 postes `P1` e `P2` com `P-9M-150DAN-CIRCULAR`, vão `ABC-4 CA` de `35m`) e sempre `native_only=True`:
  - `test_ficha_predita_da_rede_sintetica_e_valida`: `validar_ficha(ficha) == []`, `ficha["tipo"] == "predicao"`, `ficha["pdf_sha256"]` igual ao do arquivo.
  - `test_cli_grava_ficha_e_avaliacao_sem_caminho_absoluto`: `main([...])` devolve 0; os dois arquivos existem; o texto deles não contém `str(tmp_path)`, `tmp_path.as_posix()` nem o nome do PDF; não sobra diretório temporário em `saida`.
  - `test_referencia_de_outro_pdf_e_recusada`: referência com outro `pdf_sha256` → `ValueError` e `saida` sem `ficha-predita.json`.
  - `test_baseline_sintetico_do_analisador_atual`: referência montada no teste com o SHA do PDF gerado (`P1` e `P2` com identificador, `poste` e o vão de 35 m `ABC-4 CA`, bboxes nas posições do texto na página 600×400). Rode uma vez, leia os números reais e fixe no teste os valores de `postes`, `campos`, `vaos` e `simbolos` do relatório: é o baseline sintético, que muda só com uma mudança deliberada do analisador ou do protocolo. Registre no relatório da tarefa os valores e o porquê de cada erro.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_ficha_poste.py -v` → falham (exceto o baseline, que é fixado no Step 4).
- [ ] **Step 3: Implementar** `scripts/benchmark_ficha_poste.py` (docstring de módulo com o uso do CLI) e o parágrafo em `examples/README.md`.
- [ ] **Step 4:** o mesmo comando → todos passam, com o baseline fixado.
- [ ] **Step 5: Gate completo** → todos exit 0.
- [ ] **Step 6: Commit** `feat: CLI de benchmark por poste com ficha predita e baseline sintético`.

## Verificação da etapa (orquestrador, depois da Task 3)

- Critério 1 (schema valida ficha completa e rejeita campo extra): `test_ficha_poste.py` verde.
- Critério 2 (métricas esperadas em acerto total, símbolo no poste vizinho, poste ausente, vão errado): `test_ficha_poste_avaliador.py` verde.
- Critério 3 (CLI grava relatório em diretório informado, sem caminho absoluto): `test_benchmark_ficha_poste.py` verde.
- Critério 4: gate completo equivalente ao `IniciarTestes.bat`, todos exit 0.
