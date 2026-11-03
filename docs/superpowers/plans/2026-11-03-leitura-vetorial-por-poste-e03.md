# E03 — Rotulagem v0 e baseline real — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a curadoria passa a produzir fichas do poste por leitura dupla cega (com terceiro leitor para divergências e amostra humana), e o analisador atual é medido contra elas, com denominadores, em `tmp/`.

**Architecture:** um módulo puro `scripts/ficha_leitura_dupla.py` compara duas leituras de ficha, gera as regiões de conferência do terceiro leitor e consolida a referência sem palpite (o que não fecha vira `pendentes` ou zona excluída do escopo). O CLI `scripts/curation_ficha.py` faz a E/S dentro de uma rodada da curadoria existente (`RODADA/pdfs/ID/ficha/`): validar e congelar cada leitura, comparar, consolidar, rodar o baseline com `scripts.benchmark_ficha_poste` e montar e medir a amostra humana. O leitor visual da curadoria ganha um "modo ficha"; a skill e o contrato descrevem o fluxo e o invariante revisado do ADR 0017. A parte operacional (16 folhas) é conduzida pelo orquestrador depois das tarefas.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (recortes da amostra), pytest, mypy strict, ruff. Sem dependência nova.

**Spec:** seção "E03 — Rotulagem v0 e baseline real" de `docs/roadmap-leitura-vetorial-por-poste.md`; design `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (decisões 6 e 7, fase F1); ADR 0017; handoff da E02 (formato v1, R2, R4) e da E13 no mesmo roadmap.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o cliente não importa nada do servidor (`client_artifact_gate`); DTOs seguem `tests/contracts/test_architecture.py`. Esta etapa só toca `scripts/`, `tests/`, `docs/`, `.claude/` e `CLAUDE.md`; `src/` não muda.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`; nenhuma migração SQLite; a versão do extrator/interpretador não muda (o analisador não muda).
- PDFs reais, recortes, rótulos, conjuntos de dados e pesos treinados nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa.
- Leitura de avaliação é sempre cega, sem predições à vista. Pré-marcação vale só para o conjunto de treino. O conjunto de avaliação nunca alimenta o treino.
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos.
- Documentação enxuta: nada de histórico de execução em arquivo versionado. Atualize só o que a mudança torna falso (`CLAUDE.md`, contrato de curadoria, especificação funcional).
- Formato da ficha e avaliador da E02 ficam como estão (`ficha-poste-v1`, `PROTOCOLO_FICHA`, casamento guloso 0,02/0,05): a E03 só mede a distribuição das distâncias de casamento e registra; mudar limiar é decisão do usuário (D2).
- Arquivos gravados em `tmp/` pelos CLIs novos não trazem caminho absoluto nem o nome do PDF (só `pdf_id` da rodada e `sha256`), como `benchmark_ficha_poste`.
- Todo JSON gravado usa `scripts.curation_round.escrever_json_atomico`; leitura com `ler_json`.

## Review Focus

- Leitura que vê só parte da folha (tiles ilegíveis): o leitor A/B declara campo em `pendentes`; nunca escopo regional (o validador recusa regional para A e B). Teste: `test_validar_recusa_escopo_regional_para_a_e_b` (Task 1).
- Poste visto por um só leitor e sem terceiro leitor: o consolidado não pode afirmar nem negar o poste; vira zona excluída do escopo, e a predição ali não conta como FP. Teste: `test_consolidar_sem_c_exclui_poste_disputado_do_escopo` (Task 3).
- Terceiro leitor que vê valores dos leitores A/B quebraria a cegueira: `regioes-conferencia.json` só tem `id`, `pagina` e `bbox`. Teste: `test_regioes_de_conferencia_nao_trazem_valores` (Task 2).
- Recongelar uma leitura depois da comparação mascararia ajuste sobre o resultado: `congelar` recusa leitura já congelada e qualquer leitura depois de `referencia.json` existir. Teste: `test_congelar_recusa_depois_da_consolidacao` (Task 1).
- Agregado do baseline que esconde folha ruim no total: o resumo traz cada PDF e o total, com denominadores, e PDF sem referência consolidada aparece como `sem_referencia`, não some. Teste: `test_agregar_lista_pdf_sem_referencia` (Task 4).

---

## Layout em `tmp/` (rodada da curadoria existente)

```
RODADA/pdfs/ID/render/                 # curation_render (já existe)
RODADA/pdfs/ID/ficha/leitura/{a,b,c}.json   # o que o leitor grava (rascunho)
RODADA/pdfs/ID/ficha/leitura-{a,b,c}.json   # congelado pelo CLI (cópia canônica)
RODADA/pdfs/ID/ficha/congelamento.json # {"schema_version":"curadoria-ficha-congelamento-v1","itens":[{"leitor","arquivo","sha256","horario","exposicao":false}]}
RODADA/pdfs/ID/ficha/comparacao.json   # A × B (só orquestrador e consolidação)
RODADA/pdfs/ID/ficha/regioes-conferencia.json  # o que o leitor C recebe
RODADA/pdfs/ID/ficha/referencia.json   # ficha consolidada (tipo referencia), sha em congelamento.json com leitor "consolidada"
RODADA/pdfs/ID/ficha/baseline/{ficha-predita,avaliacao}.json
RODADA/fichas/baseline-resumo.{json,md}
RODADA/fichas/amostra-humana/{amostra.json,amostra.md,NN.png,respostas.json,taxa.json}
```

Leitor: `"a"`, `"b"` ou `"c"` (minúsculo, constante `LEITORES = ("a", "b", "c")`).

Metadados de cada leitura em `atributos_extras.leitura` da raiz da ficha: `{"leitor": "a"|"b"|"c", "modelo": str, "origem": "revisao_ia", "tiles_revisados": [str, ...]}` (não vazio; cada id existe no `indice-tiles.json` do PDF).

---

### Task 1: Validar e congelar leituras de ficha

**Files:**
- Create: `scripts/curation_ficha.py`
- Test: `tests/unit/test_curation_ficha.py`

**Interfaces:**
- Consumes: `scripts.ficha_poste.validar_ficha`; `scripts.curation_round` (`carregar_rodada`, `diretorio_pdf`, `escrever_json_atomico`, `ler_json`, `hash_arquivo`); `scripts.curation_render.carregar_indice`.
- Produces:
  - `LEITORES: Final = ("a", "b", "c")`
  - `diretorio_ficha(rodada_dir: Path, pdf_id: str) -> Path` (`RODADA/pdfs/ID/ficha`)
  - `erros_leitura(rodada_dir: Path, pdf_id: str, leitor: str, dados: Mapping[str, Any]) -> list[str]`
  - `congelar_leitura(rodada_dir: Path, pdf_id: str, leitor: str, arquivo: Path) -> dict[str, Any]` (devolve o item gravado em `congelamento.json`)
  - `carregar_congelada(rodada_dir: Path, pdf_id: str, leitor: str) -> dict[str, Any]` (relê e confere o sha256 registrado; `ValueError` se divergir ou faltar)
  - `main(argv: Sequence[str] | None = None) -> int` com subcomandos `validar` e `congelar` (`--rodada`, `--pdf`, `--leitor`, `--arquivo`); erro → mensagem `erro: ...` em stderr e código 1.

Regras de `erros_leitura` (além de `validar_ficha`): `tipo == "referencia"`; `pdf_sha256` igual ao `sha256` do PDF na rodada; `atributos_extras.leitura` presente e coerente com o `leitor` informado, `origem == "revisao_ia"`, `tiles_revisados` não vazio e só com ids do índice; leitores `a` e `b` exigem `escopo_anotacao.tipo == "completo"`; o leitor `c` exige `regional`, com cada região contida em alguma região de `regioes-conferencia.json` do PDF (que precisa existir).

- [ ] **Step 1: Write the failing tests** (rodada sintética com `tests/pdf_fixtures.py` + `curation_round.iniciar_rodada` + `curation_render.renderizar`, como em `tests/unit/test_curation_reference.py`; fichas montadas no próprio teste)

```python
def test_validar_aceita_leitura_a_completa(rodada) -> None:
    assert erros_leitura(rodada_dir, pdf_id, "a", ficha_leitor("a")) == []

def test_validar_recusa_escopo_regional_para_a_e_b(rodada) -> None:
    for leitor in ("a", "b"):
        assert any("escopo" in e for e in erros_leitura(rodada_dir, pdf_id, leitor, ficha_regional(leitor)))

def test_validar_recusa_sha_de_outro_pdf_tile_inexistente_e_leitor_trocado(rodada) -> None: ...
    # três casos, cada um com a mensagem citando o campo (pdf_sha256, tiles_revisados, leitor)

def test_validar_c_exige_regioes_de_conferencia_e_regioes_contidas(rodada) -> None: ...
    # sem regioes-conferencia.json → erro; região de C fora das regiões de conferência → erro; contida → []

def test_congelar_grava_copia_e_sha_e_recusa_segunda_vez(rodada) -> None:
    item = congelar_leitura(rodada_dir, pdf_id, "a", rascunho)
    assert item["sha256"] == hash_arquivo(diretorio_ficha(rodada_dir, pdf_id) / "leitura-a.json")
    assert item["exposicao"] is False
    with pytest.raises(ValueError, match="já congelada"):
        congelar_leitura(rodada_dir, pdf_id, "a", rascunho)

def test_congelar_recusa_depois_da_consolidacao(rodada) -> None:
    # com ficha/referencia.json presente, congelar b → ValueError("consolidada")

def test_carregar_congelada_detecta_adulteracao(rodada) -> None: ...

def test_cli_validar_e_congelar_codigos_de_saida(rodada, capsys) -> None: ...
    # válida → 0 e "ok"; inválida → 1 e "erro:" no stderr, sem caminho absoluto na saída
```

- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_ficha.py -q` → FAIL (módulo inexistente).
- [ ] **Step 3:** implementar em `scripts/curation_ficha.py` (docstring de módulo com o uso dos subcomandos; `curation_round._trava` para a escrita de `congelamento.json`).
- [ ] **Step 4:** pytest do arquivo → PASS; `ruff check`, `ruff format --check`, `mypy` → limpos.
- [ ] **Step 5:** commit `feat(curadoria): validar e congelar leituras de ficha do poste`.

---

### Task 2: Comparar leituras A × B e regiões de conferência

**Files:**
- Create: `scripts/ficha_leitura_dupla.py`
- Modify: `scripts/curation_ficha.py` (subcomando `comparar`)
- Test: `tests/unit/test_ficha_leitura_dupla.py`, `tests/unit/test_curation_ficha.py`

**Interfaces:**
- Consumes: `scripts.ficha_poste_avaliador` (`avaliar`, `casar_postes`, `PROTOCOLO_FICHA`, `CAMPOS_DO_POSTE`, `normalizar_texto` e os comparadores de campo, de vão e de símbolo já existentes — reuse, não duplique; importar privado é aceito, como já faz `benchmark_ficha_poste`); Task 1.
- Produces:
  - `MARGEM_CONFERENCIA: Final = 0.02` (espaço normalizado da página)
  - `comparar_leituras(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]` com chaves `schema_version` (`"curadoria-ficha-comparacao-v1"`), `pdf_sha256`, `pares` (`[{"a", "b", "distancia"}]`), `concordancia` (o relatório de `avaliar(a, b_como_predicao)`, B convertido a `tipo: "predicao"` com `gerador: {"leitor": "b"}`), `divergencias` (lista ordenada e determinística, ids `d001`…) e `distancias_casamento` (lista ordenada das distâncias dos pares).
  - Cada divergência: `{"id", "tipo", "pagina", "bbox", "a": id|None, "b": id|None, "campo": str|None}`, com `tipo` em `"poste_so_a"`, `"poste_so_b"`, `"campo"` (um por campo divergente de um par, inclusive campo pendente em um só leitor), `"simbolos"` (conjuntos de símbolos do par não casam por inteiro), `"vao_so_a"`, `"vao_so_b"`, `"vao_atributo"` (`campo` = `comprimento_m` ou `cabo`). Para vão, `a`/`b` = `"DE|PARA"` e `bbox` = envolvente das bbox dos dois postes.
  - `regioes_de_conferencia(comparacao: Mapping[str, Any]) -> list[dict[str, Any]]`: bbox de cada divergência expandida por `MARGEM_CONFERENCIA`, recortada a [0, 1], e regiões da mesma página que se sobrepõem fundidas até não haver sobreposição; ids `r001`…; cada item só `{"id", "pagina", "bbox"}`.
  - CLI `comparar --rodada --pdf`: exige A e B congeladas (`carregar_congelada`), grava `ficha/comparacao.json` e `ficha/regioes-conferencia.json` (`{"schema_version": "curadoria-ficha-regioes-v1", "pdf_id", "regioes": [...]}`), imprime contagens de divergência por tipo.

- [ ] **Step 1: Write the failing tests** (fichas sintéticas de 3 postes, 2 vãos, 1 símbolo)

```python
def test_leituras_iguais_nao_tem_divergencia() -> None:
    comp = comparar_leituras(ficha(), ficha())
    assert comp["divergencias"] == [] and regioes_de_conferencia(comp) == []

def test_campo_diferente_gera_divergencia_de_campo() -> None:
    b = ficha(); b["postes"][0]["estruturas"] = ["N3"]
    [d] = comparar_leituras(ficha(), b)["divergencias"]
    assert (d["tipo"], d["campo"], d["a"], d["b"]) == ("campo", "estruturas", "P1", "P1")

def test_poste_so_em_a_e_vao_so_em_b() -> None: ...
    # remove P3 de B (e o vão P2|P3) → poste_so_a + vao_so_a; acrescenta vão P1|P3 em B → vao_so_b

def test_simbolo_em_um_so_leitor_gera_divergencia_simbolos() -> None: ...

def test_comprimento_divergente_alem_da_tolerancia() -> None:
    # 35,0 × 35,05 → sem divergência (tolerância 0,1 m do PROTOCOLO_FICHA); 35 × 40 → vao_atributo comprimento_m

def test_regioes_de_conferencia_nao_trazem_valores() -> None:
    regioes = regioes_de_conferencia(comp_com_divergencias)
    assert all(set(r) == {"id", "pagina", "bbox"} for r in regioes)

def test_regioes_sobrepostas_sao_fundidas_e_recortadas_a_pagina() -> None: ...
    # duas divergências a 0,01 uma da outra → 1 região; poste em x=0,005 → x0 == 0.0

def test_resultado_independe_da_ordem_de_entrada() -> None: ...

def test_cli_comparar_exige_a_e_b_congeladas(rodada) -> None: ...
```

- [ ] **Step 2:** pytest dos dois arquivos → FAIL.
- [ ] **Step 3:** implementar `scripts/ficha_leitura_dupla.py` (puro, sem E/S) e o subcomando.
- [ ] **Step 4:** pytest → PASS; ruff, format, mypy limpos.
- [ ] **Step 5:** commit `feat(curadoria): comparação de leitura dupla de fichas e regiões de conferência`.

---

### Task 3: Consolidar a referência sem palpite

**Files:**
- Modify: `scripts/ficha_leitura_dupla.py`, `scripts/curation_ficha.py` (subcomando `consolidar`)
- Test: `tests/unit/test_ficha_leitura_dupla.py`, `tests/unit/test_curation_ficha.py`

**Interfaces:**
- Consumes: Task 2 (`comparar_leituras`, formato de `divergencias`), Task 1.
- Produces:
  - `consolidar(a: Mapping[str, Any], b: Mapping[str, Any], c: Mapping[str, Any] | None, comparacao: Mapping[str, Any]) -> dict[str, Any]`: ficha `tipo: "referencia"` válida por `validar_ficha`, com `atributos_extras.consolidacao = {"resolvidas_por_c": int, "pendentes": int, "excluidas": [{"pagina", "bbox", "motivo"}], "descartadas_por_maioria": int}` e sem `atributos_extras.leitura`.
  - CLI `consolidar --rodada --pdf [--sem-terceiro --motivo TEXTO]`: exige `comparacao.json`; com regiões de conferência e sem C congelada, só roda com `--sem-terceiro` e `--motivo` (o motivo vai para `consolidacao.motivo_sem_terceiro`); grava `ficha/referencia.json` e registra o sha em `congelamento.json` com `leitor: "consolidada"`, `exposicao: false`. Recusa se `referencia.json` já existe.

Regras (C é casada a A ou B com `casar_postes`; "C cobre" = o centro do poste, ou os dois extremos do vão, está numa região da ficha C):

1. Par A–B, campo igual → valor de A. Campo diferente, ou pendente em só um leitor → se C tem poste casado, não pendente, e o valor dele é igual (mesmo comparador do avaliador) ao de A ou de B não pendente → esse valor (`resolvidas_por_c += 1`); senão o campo vai a `pendentes` com valor nulo (`null`, `[]` em estruturas) e `pendentes += 1`. Pendente nos dois → pendente.
2. Símbolos do par: casam por inteiro → símbolos de A. Senão, os de quem C confirma por inteiro; senão `simbolos` em `pendentes` e lista vazia.
3. Poste só em um leitor: C tem poste casado → entra, com campos pela regra 1 entre esse leitor e C; C cobre e não tem poste → descartado (`descartadas_por_maioria += 1`); C ausente ou não cobre → zona excluída (bbox do poste expandida por `MARGEM_CONFERENCIA`, motivo `"poste_disputado"`).
4. Vão só em um leitor: C tem o vão entre os postes casados → entra, atributos pela regra 1; C cobre os dois extremos e não tem → descartado; senão os dois extremos viram zonas excluídas (motivo `"vao_disputado"`). Vão nos dois com atributo divergente → regra 1 por atributo (`pendentes` do vão).
5. Com zonas excluídas, `escopo_anotacao` vira `regional`: por página com postes, a página `[0, 0, 1, 1]` menos as zonas (subtração de retângulos, até 4 por corte); postes cujo centro cai numa zona saem, com seus vãos. Sem zonas, `completo`.
6. Ids: os de A; poste que só B (confirmado por C) traz recebe `"b-" + id`. Ids de símbolo idem.

- [ ] **Step 1: Write the failing tests**

```python
def test_consolidar_sem_divergencia_reproduz_a_sem_metadados_de_leitura() -> None: ...
def test_campo_divergente_resolvido_por_c() -> None:
    # A estruturas N1, B N3, C N3 → N3; resolvidas_por_c == 1
def test_campo_divergente_sem_acordo_vira_pendente_nulo() -> None:
    # A N1, B N3, C U3 → "estruturas" em pendentes, estruturas == []
def test_simbolos_sem_acordo_viram_pendentes() -> None: ...
def test_poste_so_em_a_confirmado_por_c_entra() -> None: ...
def test_poste_so_em_a_negado_por_c_e_descartado() -> None: ...
def test_consolidar_sem_c_exclui_poste_disputado_do_escopo() -> None:
    ref = consolidar(a, b_sem_p3, None, comparar_leituras(a, b_sem_p3))
    assert ref["escopo_anotacao"]["tipo"] == "regional"
    assert "P3" not in {p["id"] for p in ref["postes"]}
    # predição com poste em P3 avaliada contra ref: P3 não conta como FP
    assert avaliar(ref, predicao_com_p3)["postes"]["fp"] == 0
def test_vao_so_em_um_leitor_sem_c_exclui_os_extremos() -> None: ...
def test_regioes_do_escopo_cobrem_a_pagina_menos_as_zonas() -> None: ...
    # ponto fora das zonas está em alguma região; centro da zona não está em nenhuma
def test_cli_consolidar_exige_c_ou_sem_terceiro_com_motivo(rodada) -> None: ...
```

- [ ] **Step 2:** pytest → FAIL.
- [ ] **Step 3:** implementar.
- [ ] **Step 4:** pytest → PASS; ruff, format, mypy; `scripts/complexity_gate.py src` não cobre `scripts/`, mas nenhuma função nova pode ter rank Radon E/F.
- [ ] **Step 5:** commit `feat(curadoria): consolidação da ficha de referência sem palpite`.

---

### Task 4: Baseline do analisador atual por poste

**Files:**
- Modify: `scripts/curation_ficha.py` (subcomando `baseline`)
- Test: `tests/unit/test_curation_ficha.py`

**Interfaces:**
- Consumes: `scripts.benchmark_ficha_poste.executar(pdf, referencia, saida, *, native_only, runtime_directory)`; `curation_round.caminho_pdf_fonte`; Tasks 1 e 3 (`referencia.json` com sha em `congelamento.json`).
- Produces:
  - `agregar_avaliacoes(avaliacoes: Mapping[str, Mapping[str, Any] | None]) -> dict[str, Any]` (chave = `pdf_id`; `None` = sem referência): `{"schema_version": "curadoria-ficha-baseline-v1", "por_pdf": {pdf_id: {...} | {"situacao": "sem_referencia"}}, "total": {...}}`, em que cada bloco tem `postes` (tp, fp, fn, precisão, recall), `campos` (por campo: acertos, total, taxa), `vaos` (tp, fp, fn, `comprimento` e `cabo` com acertos/total) e `simbolos` (tp, fp, fn); taxas recalculadas das somas, nunca média de taxas; `distancias_casamento` do total = lista ordenada das distâncias dos `pares` de todos os PDFs.
  - CLI `baseline --rodada [--pdf ID ...] [--native-only] [--runtime-directory DIR]`: para cada PDF (todos da rodada por padrão), confere o sha da `referencia.json` contra `congelamento.json`, roda `executar` com saída `ficha/baseline/`, e grava `RODADA/fichas/baseline-resumo.json` e `.md` (tabela por PDF e total com denominadores, opção `native_only` e `gerador` registrados). Falha do analisador num PDF → `{"situacao": "falha", "erro": str}` no resumo (falha não é zero) e código de saída 1 no fim.

- [ ] **Step 1: Write the failing tests**

```python
def test_agregar_soma_contagens_e_recalcula_taxas() -> None:
    # dois relatórios sintéticos (2/1 tp) → total tp 3, precisão = 3/(3+fp_total)
def test_agregar_lista_pdf_sem_referencia() -> None:
    assert agregar_avaliacoes({"01-x": rel, "02-y": None})["por_pdf"]["02-y"] == {"situacao": "sem_referencia"}
def test_cli_baseline_recusa_referencia_adulterada(rodada) -> None: ...
def test_cli_baseline_grava_resumo_sem_caminho_absoluto(rodada) -> None:
    # PDF sintético de rede de 2 postes (o mesmo da E02, tests/unit/test_benchmark_ficha_poste.py), --native-only
    # resumo existe, cita pdf_id, não contém str(tmp_path) nem o nome do arquivo PDF
def test_cli_baseline_registra_falha_sem_zerar(rodada, monkeypatch) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar → PASS; ruff, format, mypy.
- [ ] **Step 5:** commit `feat(curadoria): baseline por poste do analisador atual sobre a rodada`.

---

### Task 5: Amostra humana e taxa de erro de rótulo

**Files:**
- Modify: `scripts/curation_ficha.py` (subcomandos `amostra` e `taxa`)
- Test: `tests/unit/test_curation_ficha.py`

**Interfaces:**
- Consumes: Tasks 1 e 3; `curation_round.caminho_pdf_fonte`; PyMuPDF para o recorte.
- Produces:
  - `sortear_amostra(postes_por_pdf: Mapping[str, Sequence[str]], tamanho: int, semente: int) -> list[tuple[str, str]]`: determinística; distribui por rodízio entre PDFs ordenados (estratificada por folha) e sorteia dentro de cada PDF com `random.Random(semente)`; `tamanho` maior que a população → toda a população.
  - CLI `amostra --rodada --tamanho N --semente S`: só PDFs com `referencia.json`; grava `RODADA/fichas/amostra-humana/amostra.json` (`[{"item": "NN", "pdf_id", "poste_id", "pagina", "bbox", "campos": {identificador, estruturas, poste, coordenada, simbolos, vaos_ligados, pendentes}, "recorte": "NN.png"}]`), `NN.png` (página renderizada a 300 dpi, recortada na bbox do poste expandida por 0,04 e recortada à página) e `amostra.md` (uma seção por item com a imagem e os campos, e as instruções de resposta). Recusa se a amostra já existe.
  - CLI `taxa --rodada --respostas ARQ`: `respostas.json` = `{"NN": {"correto": bool, "campos_errados": [campo, ...], "nota": str}}`; exige resposta para todos os itens e `campos_errados` não vazio quando `correto` é falso (campos em `identificador`, `estruturas`, `poste`, `coordenada`, `simbolos`, `vaos`); grava `taxa.json` com `{"itens": n, "postes_com_erro": k, "taxa_erro_poste": k/n, "por_campo": {campo: {"erros", "avaliados"}}}`, em que `avaliados` exclui os itens em que o campo está em `pendentes`.

- [ ] **Step 1: Write the failing tests**

```python
def test_sortear_amostra_e_deterministica_e_estratificada() -> None:
    pop = {"01-a": ["P1", "P2", "P3"], "02-b": ["P1"], "03-c": ["P1", "P2"]}
    s = sortear_amostra(pop, 3, 7)
    assert s == sortear_amostra(pop, 3, 7) and {pdf for pdf, _ in s} == set(pop)
def test_sortear_amostra_maior_que_populacao_devolve_tudo() -> None: ...
def test_cli_amostra_grava_recortes_e_md_sem_nome_do_pdf(rodada) -> None: ...
def test_cli_taxa_calcula_por_poste_e_por_campo_excluindo_pendentes(rodada) -> None: ...
def test_cli_taxa_recusa_resposta_faltando_ou_erro_sem_campo(rodada) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar (documento PyMuPDF fechado com `with`) → PASS; ruff, format, mypy.
- [ ] **Step 5:** commit `feat(curadoria): amostra humana de fichas e taxa de erro de rótulo`.

---

### Task 6: Leitor visual em modo ficha, skill, contrato e CLAUDE.md

**Files:**
- Modify: `.claude/agents/curadoria-leitor-visual.md`, `.claude/skills/curadoria-simbologia/SKILL.md`, `docs/fluxo-curadoria-incremental-simbologia.md`, `CLAUDE.md`, `examples/README.md` (só se citar o fluxo da ficha), `tests/unit/test_claude_curation_assets.py`
- Test: `tests/unit/test_claude_curation_assets.py`

**Interfaces:**
- Consumes: os subcomandos e caminhos das Tasks 1–5 (exatamente como definidos acima).

Conteúdo:
- **Agente leitor:** nova seção "Modo ficha", ativada quando a tarefa traz `modo: ficha` e `leitor: a|b|c`. Entrada: `RODADA`, `ID`, `sha256`, `caminho_relativo`, `modelo`, `leitor`, saída `RODADA/pdfs/ID/ficha/leitura/LEITOR.json` e, só para `c`, o caminho de `regioes-conferencia.json`. Permitido a mais: ler `docs/schemas/ficha-poste.schema.json`; gravar só a saída; rodar só `.venv/Scripts/python.exe -m scripts.curation_ficha validar --rodada RODADA --pdf ID --leitor LEITOR --arquivo SAIDA`. Proibido a mais: `ficha/leitura-*.json`, `ficha/comparacao.json`, `ficha/referencia.json`, `ficha/baseline/`, `fichas/` e as leituras de outros leitores. Regras: uma entrada por poste da rede (identificador, estruturas, poste, coordenada UTM escrita na folha, símbolos associados com classe do inventário e bbox), vãos com comprimento e cabo escritos; `null` só para o que a folha não tem; o que não dá para ler vai em `pendentes`; normalizar U+200B/U+FEFF; A e B com escopo `completo`; C com escopo `regional` igual às regiões recebidas, lendo só os tiles que as tocam; `atributos_extras.leitura` com `tiles_revisados`. As regras do modo normal continuam iguais. A `description` do frontmatter cita o modo ficha.
- **Skill:** seção "Rodada de fichas do poste" com o procedimento: `curation_round init` e `curation_render` como hoje (sem inferência nem comparação de símbolos); dois leitores por PDF (instâncias novas, `modo: ficha`, leitores `a` e `b`) em paralelo; `curation_ficha validar`/`congelar` de cada um; `comparar`; leitor `c` (instância nova) só com as regiões de conferência quando houver; `consolidar`; `amostra` → conferência pelo usuário → `taxa`; `baseline` (com `--native-only` e pendência de OCR registrada se o OCR português não estiver disponível). Ordem obrigatória: nenhum `baseline` antes da consolidação de todas as folhas medidas.
- **Contrato:** substitui a frase "Uma rodada não treina o assistente de forma permanente…" pelo invariante revisado do ADR 0017 (os rótulos podem alimentar o treino; a leitura de avaliação continua cega, o conjunto de avaliação é separado por folha, congelado e nunca usado no treino; pré-marcação só no conjunto de treino), e acrescenta uma subseção curta "Ficha do poste" descrevendo leitura dupla, terceiro leitor, consolidação sem palpite, amostra humana e baseline, apontando a skill.
- **CLAUDE.md:** na seção "Curadoria de simbologia", acrescente `curation_ficha.py` à lista de CLIs e uma frase sobre a rodada de fichas.

- [ ] **Step 1:** acrescentar a `tests/unit/test_claude_curation_assets.py` testes que falham: o leitor tem a seção "Modo ficha" e cita `scripts.curation_ficha validar` e os caminhos proibidos da ficha; a skill cita os subcomandos `validar`, `congelar`, `comparar`, `consolidar`, `amostra`, `taxa` e `baseline` de `scripts.curation_ficha`; o contrato não contém mais "não treina o assistente" e cita ADR 0017.
- [ ] **Step 2:** pytest do arquivo → FAIL.
- [ ] **Step 3:** editar os documentos.
- [ ] **Step 4:** pytest do arquivo → PASS (e os testes já existentes desse arquivo continuam verdes).
- [ ] **Step 5:** commit `docs(curadoria): leitor em modo ficha, rodada de fichas e invariante do ADR 0017`.

---

## Execução operacional (orquestrador, depois das Tasks 1–6 revisadas)

Roda a partir do worktree, com o corpus `examples/` e a rodada em `tmp/` do checkout principal (protocolo do roadmap). `RODADA` = `<checkout principal>/tmp/curadoria-simbologia/AAAAMMDD-HHMM-fichas`.

1. **Pré-condição do leitor:** o `curadoria-leitor-visual` registrado na sessão precisa ter o modo ficha. A definição é carregada no início da sessão a partir do checkout em que ela foi aberta; se o agente disparado não reconhecer `modo: ficha` (devolve a pendência ou segue o formato antigo), pare: o usuário reabre `claude --agent orquestrador` no diretório do worktree, e a execução retoma daqui pelo ledger.
2. `curation_round init --rodada RODADA --raiz <examples do checkout principal> --concorrencia 4`; `curation_render --rodada RODADA --onda K --jobs 4` para cada onda.
3. Leitores `a` e `b` por PDF (instâncias novas, em segundo plano, até 4 por vez; sem `model`), cada um só com as entradas do modo ficha. `validar` e `congelar` cada leitura; leitura incompleta volta ao mesmo leitor antes de congelar.
4. `comparar` por PDF; leitor `c` (instância nova) para cada PDF com regiões de conferência; `validar`/`congelar` `c`; `consolidar`.
5. `amostra --tamanho 20 --semente 20261103`; o usuário confere os 20 recortes de `amostra.md` (entrevista); o orquestrador grava as respostas e roda `taxa`. Taxa de erro de poste acima de 20% → amostra ampliada para 40 itens (segunda semente) e registro, como manda o risco da etapa.
6. `baseline --rodada RODADA` sem `--native-only` se `tmp/benchmark-runtime` tiver o OCR português; senão `--native-only`, com o OCR registrado como pendência e como decisão para o usuário.
7. `RODADA/fichas/relatorio.md`: leitores e modelo, concordância A × B por PDF (postes, campos, vãos, símbolos, com denominadores), divergências por tipo, resolvidas por C, pendentes e zonas excluídas, distribuição das distâncias de casamento (calibração R4), taxa de erro da amostra humana e baseline por PDF e total.
8. Critérios: `git grep -n "PROJETO DE REDE NS"` vazio; gate completo verde.
