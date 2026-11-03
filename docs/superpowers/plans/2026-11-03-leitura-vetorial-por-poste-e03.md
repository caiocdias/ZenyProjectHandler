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
- Formato da ficha e comportamento do avaliador da E02 ficam como estão (`ficha-poste-v1`, `PROTOCOLO_FICHA`, casamento guloso 0,02/0,05): a E03 só mede as distâncias de casamento e registra; mudar limiar é decisão do usuário (D2).
- Arquivos gravados em `tmp/` pelos CLIs novos não trazem caminho absoluto nem o nome do PDF (só `pdf_id` da rodada e `sha256`), como `benchmark_ficha_poste`.
- JSON gravado pelos CLIs novos usa `scripts.curation_round.escrever_json_atomico`; exceção: `ficha-predita.json` e `avaliacao.json`, gravados por `benchmark_ficha_poste.executar`, que é reusado sem mudança.
- Nenhuma versão gravada é sobrescrita (contrato, "Layout da rodada"): congelamentos, baselines e amostras são versionados (`-vNNN`) ou recusam destino existente.
- **Suíte verde ao fim de cada tarefa.** `tests/unit/test_claude_curation_assets.py` exige, para todo `scripts/curation_*.py`: regra allow em `.claude/settings.json`, invocação na skill e as mesmas linhas de comando no contrato (paridade linha a linha) com subcomandos e opções existentes. Por isso cada tarefa que cria um subcomando acrescenta as linhas dele na seção "Rodada de fichas do poste" da skill e do contrato, e roda esse arquivo de teste além dos seus. Arquivos sob `.claude/` não podem conter "roadmap", ids de etapa (`E0N`, `E1N`), instrução de commit nem caminho absoluto.

## Decisões de desenho

- **Conferência pelo leitor C, não pelo auditor.** A spec cita o `curadoria-auditor-visual` na adaptação. No modo ficha, a conferência das divergências é um terceiro leitor (`curadoria-leitor-visual`, instância nova, `leitor: c`) restrito às regiões de conferência, que grava uma ficha regional no mesmo formato de A e B. A auditoria amostral de tiles não roda no modo ficha; o auditor não muda. Alternativa descartada: o auditor em modo ficha como conferente das regiões — ele foi desenhado para ler só tiles sorteados e gravar leitura regional de símbolos para concordância, e teria um segundo formato e um segundo prompt de leitura de ficha para manter. A decisão vai a "Decisões para o usuário" no handoff da E03.
- **Allow novo em `.claude/settings.json`:** `Bash(.venv/Scripts/python.exe -m scripts.curation_ficha *)`, no mesmo padrão das regras `curation_*` existentes e exigido pelo teste de guarda. Vai a "Decisões para o usuário" por ser mudança de permissão.

## Review Focus

- Leitor A/B que pula tiles: `completo` exige todo tile `a_revisar` revisado ou coberto por `regioes_ilegiveis`, com a mesma regra de `curation_reference` (inclusive o gêmeo da camada anotada). Teste: `test_validar_recusa_completo_com_tile_a_revisar_nao_coberto` (Task 1).
- Poste visto por um só leitor e sem terceiro leitor, ou área ilegível: o consolidado não afirma nem nega; vira zona excluída do escopo, e a predição ali não conta como FP. Testes: `test_consolidar_sem_c_exclui_poste_disputado_do_escopo` e `test_regiao_ilegivel_vira_zona_excluida` (Task 3).
- Terceiro leitor que vê valores dos leitores A/B quebraria a cegueira: `regioes-conferencia.json` só tem `id`, `pagina` e `bbox`. Teste: `test_regioes_de_conferencia_nao_trazem_valores` (Task 2).
- Dois vãos (MT e BT) no mesmo par de postes: a divergência identifica qual, e a consolidação não troca atributos entre eles. Testes: `test_dois_vaos_no_mesmo_par_so_um_divergente` (Task 2) e `test_consolidar_dois_vaos_no_mesmo_par_nao_troca_atributos` (Task 3).
- Agregado do baseline que esconde folha ruim no total: o resumo traz cada PDF e o total, com denominadores; o CLI recusa rodar com PDF sem referência consolidada, salvo `--parcial` registrado. Teste: `test_cli_baseline_recusa_pdf_sem_referencia_sem_parcial` (Task 4).

---

## Layout em `tmp/` (rodada da curadoria existente)

```
RODADA/pdfs/ID/render/                       # curation_render (já existe)
RODADA/pdfs/ID/ficha/rascunho-{a,b,c}/ficha.json   # o que cada leitor grava (pasta própria por leitor)
RODADA/pdfs/ID/ficha/leitura-{a,b,c}.json    # cópia congelada pelo CLI
RODADA/pdfs/ID/ficha/congelamento.json       # {"schema_version":"curadoria-ficha-congelamento-v1","itens":[{"leitor","arquivo","sha256","horario","exposicao":false}]}
RODADA/pdfs/ID/ficha/comparacao.json         # A × B (só orquestrador e consolidação)
RODADA/pdfs/ID/ficha/regioes-conferencia.json   # o que o leitor C recebe
RODADA/pdfs/ID/ficha/referencia.json         # ficha consolidada (tipo referencia); sha em congelamento.json, leitor "consolidada"
RODADA/pdfs/ID/ficha/baseline-vNNN/{ficha-predita,avaliacao}.json
RODADA/fichas/baseline-vNNN-resumo.{json,md}
RODADA/fichas/amostra-humana/amostra-vNNN/{amostra.json,amostra.md,NN.png,respostas.json}
RODADA/fichas/amostra-humana/taxa-vNNN.json
```

Leitor: `"a"`, `"b"` ou `"c"` (constante `LEITORES = ("a", "b", "c")`).

Metadados de cada leitura em `atributos_extras.leitura` da raiz da ficha: `{"leitor": "a"|"b"|"c", "modelo": str, "origem": "revisao_ia", "tiles_revisados": [str, ...], "regioes_ilegiveis": [{"pagina": int, "camada": "base"|"annotation", "bbox": [x0,y0,x1,y1], "motivo": str}]}` (`tiles_revisados` não vazio, ids do `indice-tiles.json` do PDF; `regioes_ilegiveis` pode ser vazia).

---

### Task 1: Validar e congelar leituras de ficha

**Files:**
- Create: `scripts/curation_ficha.py`
- Modify: `scripts/curation_reference.py` (extrair a cobertura de tiles para função pública, sem mudar o comportamento de `validar`), `.claude/settings.json` (allow novo), `.claude/skills/curadoria-simbologia/SKILL.md` e `docs/fluxo-curadoria-incremental-simbologia.md` (seção "Rodada de fichas do poste" com as linhas de `validar` e `congelar`)
- Test: `tests/unit/test_curation_ficha.py`; rodar também `tests/unit/test_curation_reference.py` e `tests/unit/test_claude_curation_assets.py`

**Interfaces:**
- Consumes: `scripts.ficha_poste.validar_ficha`; `scripts.curation_round` (`carregar_rodada`, `diretorio_pdf`, `escrever_json_atomico`, `ler_json`, `hash_arquivo`, `_trava` exposta como `trava`, mantendo o nome antigo como alias); `scripts.curation_render.carregar_indice`.
- Produces:
  - em `scripts/curation_reference.py`: `tiles_nao_cobertos(indice: Mapping[str, Any], revisados: Iterable[str], regioes_ilegiveis: Iterable[tuple[int, str, Sequence[float]]]) -> list[str]` (ids `a_revisar` não revisados nem cobertos; mesma regra do gêmeo anotado), usada também por `_erros_cobertura`.
  - em `scripts/curation_ficha.py`: `LEITORES`; `diretorio_ficha(rodada_dir: Path, pdf_id: str) -> Path`; `erros_leitura(rodada_dir: Path, pdf_id: str, leitor: str, dados: Mapping[str, Any]) -> list[str]`; `congelar_leitura(rodada_dir: Path, pdf_id: str, leitor: str, arquivo: Path) -> dict[str, Any]`; `carregar_congelada(rodada_dir: Path, pdf_id: str, leitor: str) -> dict[str, Any]` (confere o sha256 registrado; `ValueError` se divergir ou faltar); `main(argv: Sequence[str] | None = None) -> int` com `validar` e `congelar` (`--rodada`, `--pdf`, `--leitor`, `--arquivo`); erro → `erro: ...` em stderr e código 1.
  - formato de `regioes-conferencia.json` (produzido na Task 2, lido aqui): `{"schema_version": "curadoria-ficha-regioes-v1", "pdf_id": str, "regioes": [{"id": "r001", "pagina": int, "bbox": [x0,y0,x1,y1]}]}`.

Regras de `erros_leitura` (além de `validar_ficha`): `tipo == "referencia"`; `pdf_sha256` igual ao `sha256` do PDF na rodada; `atributos_extras.leitura` presente, com `leitor` igual ao informado, `origem == "revisao_ia"`, `tiles_revisados` não vazio e só com ids do índice, `regioes_ilegiveis` bem formadas (página existente, camada válida, bbox em [0,1] não invertida); leitores `a` e `b` exigem `escopo_anotacao.tipo == "completo"` e `tiles_nao_cobertos(...) == []`; o leitor `c` exige `regional`, com cada região contida em alguma região de `regioes-conferencia.json` do PDF (que precisa existir) e contida na união das bbox (normalizadas) dos tiles de `tiles_revisados` da mesma página com as `regioes_ilegiveis` de C da mesma página (a mesma noção `contida_na_uniao` de `curation_reference`): tile não aberto não é declarado.

- [ ] **Step 1: Write the failing tests** (rodada sintética com `tests/pdf_fixtures.py` + `curation_round.iniciar_rodada` + `curation_render.renderizar`, como em `tests/unit/test_curation_reference.py`; fichas montadas no próprio teste)

```python
def test_validar_aceita_leitura_a_completa(rodada) -> None:
    assert erros_leitura(rodada_dir, pdf_id, "a", ficha_leitor("a")) == []

def test_validar_recusa_escopo_regional_para_a_e_b(rodada) -> None:
    for leitor in ("a", "b"):
        assert any("escopo" in e for e in erros_leitura(rodada_dir, pdf_id, leitor, ficha_regional(leitor)))

def test_validar_recusa_completo_com_tile_a_revisar_nao_coberto(rodada) -> None:
    # tiles_revisados sem um tile a_revisar → erro citando o id do tile
    # mesmo tile coberto por regioes_ilegiveis → []

def test_validar_recusa_sha_de_outro_pdf_tile_inexistente_e_leitor_trocado(rodada) -> None: ...
    # três casos, cada um com a mensagem citando o campo (pdf_sha256, tiles_revisados, leitor)

def test_validar_c_exige_regioes_de_conferencia_e_regioes_contidas(rodada) -> None: ...
    # sem regioes-conferencia.json → erro; região de C fora das regiões de conferência → erro; contida → []

def test_validar_c_exige_tiles_revisados_que_cubram_as_regioes(rodada) -> None: ...
    # região de C sem tile revisado que a cubra → erro citando a região; com os tiles → []

def test_congelar_grava_copia_e_sha_e_recusa_segunda_vez(rodada) -> None:
    item = congelar_leitura(rodada_dir, pdf_id, "a", rascunho)
    assert item["sha256"] == hash_arquivo(diretorio_ficha(rodada_dir, pdf_id) / "leitura-a.json")
    assert item["exposicao"] is False
    with pytest.raises(ValueError, match="já congelada"):
        congelar_leitura(rodada_dir, pdf_id, "a", rascunho)

def test_congelar_recusa_depois_da_consolidacao(rodada) -> None:
    # com ficha/referencia.json presente, congelar b → ValueError com "consolidada"

def test_carregar_congelada_detecta_adulteracao(rodada) -> None: ...

def test_cli_validar_e_congelar_codigos_de_saida(rodada, capsys) -> None: ...
    # válida → 0 e "ok"; inválida → 1 e "erro:" no stderr, sem caminho absoluto na saída
```

- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_ficha.py -q` → FAIL (módulo inexistente).
- [ ] **Step 3:** implementar; acrescentar o allow e as linhas `.venv/Scripts/python.exe -m scripts.curation_ficha validar --rodada RODADA --pdf ID --leitor LEITOR --arquivo RODADA/pdfs/ID/ficha/rascunho-LEITOR/ficha.json` e o equivalente `congelar` na skill e no contrato (seção nova "Rodada de fichas do poste", uma frase por comando nesta tarefa; o texto completo vem na Task 6).
- [ ] **Step 4:** pytest de `test_curation_ficha.py`, `test_curation_reference.py` e `test_claude_curation_assets.py` → PASS; `ruff check .`, `ruff format --check .`, `mypy` → limpos.
- [ ] **Step 5:** commit `feat(curadoria): validar e congelar leituras de ficha do poste`.

---

### Task 2: Comparar leituras A × B e regiões de conferência

**Files:**
- Create: `scripts/ficha_leitura_dupla.py`
- Modify: `scripts/ficha_poste_avaliador.py` (só tornar públicos, com o mesmo comportamento: `campo_acerta`, `numeros_iguais`, `casar_vaos_do_par`, `casar_simbolos`; os nomes privados antigos ficam como alias), `scripts/curation_ficha.py` (subcomando `comparar`), skill e contrato (linha de `comparar`)
- Test: `tests/unit/test_ficha_leitura_dupla.py`, `tests/unit/test_curation_ficha.py`; rodar também `tests/unit/test_ficha_poste_avaliador.py` e `tests/unit/test_claude_curation_assets.py`

**Interfaces:**
- Consumes: `scripts.ficha_poste_avaliador` (`avaliar`, `casar_postes`, `PROTOCOLO_FICHA`, `CAMPOS_DO_POSTE`, `normalizar_texto` e os quatro públicos acima — reuse, não duplique); Task 1.
- Produces:
  - `MARGEM_CONFERENCIA: Final = 0.02` e `MARGEM_CONFERENCIA_CAMPO: Final = 0.04` (espaço normalizado da página)
  - `comparar_leituras(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]` com `schema_version` (`"curadoria-ficha-comparacao-v1"`), `pdf_sha256`, `pares` (`[{"a", "b", "distancia"}]`), `concordancia` (relatório de `avaliar(a, b_como_predicao)`, B convertido a `tipo: "predicao"` com `gerador: {"leitor": "b"}`; é assimétrico porque pendentes de A saem do denominador), `divergencias`, `distancias_casamento` (ordenada), `iou_simbolos` (IoU dos símbolos casados, ordenada) e `simbolos_so_geometria` (contagem de símbolos de mesma classe no mesmo par que não casaram por IoU).
  - Cada divergência: `{"id": "d001"…, "tipo", "pagina", "bbox", "a": id|None, "b": id|None, "campo": str|None}`; `tipo` em `"poste_so_a"`, `"poste_so_b"`, `"campo"` (um por campo divergente de um par, inclusive pendente em só um leitor), `"simbolos"` (símbolos do par não casam por inteiro), `"vao_so_a"`, `"vao_so_b"`, `"vao_atributo"` (`campo` = `comprimento_m` ou `cabo`). Divergência de vão leva também `de`, `para` (ids de A; para vão só em B, os ids de A casados aos extremos, e `"b-" + id` para extremo que só B tem, a mesma regra de ids da consolidação), `indice` (posição estável dentro do par, saída de `casar_vaos_do_par`), `cabo_a`, `cabo_b`.
  - bbox: poste/vão = bbox do poste (envolvente dos dois postes no vão) + `MARGEM_CONFERENCIA`; `campo` = bbox do poste + `MARGEM_CONFERENCIA_CAMPO`; `simbolos` = envolvente do poste e dos símbolos dos dois leitores + `MARGEM_CONFERENCIA`; tudo recortado a [0, 1].
  - `regioes_de_conferencia(comparacao: Mapping[str, Any]) -> list[dict[str, Any]]`: bbox das divergências, fundidas por página até não haver sobreposição; ids `r001`…; cada item só `{"id", "pagina", "bbox"}`.
  - CLI `comparar --rodada --pdf`: exige A e B congeladas (`carregar_congelada`) e recusa se `comparacao.json` já existe; grava `ficha/comparacao.json` e `ficha/regioes-conferencia.json`; imprime contagens de divergência por tipo.

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
    # espelho: poste P9 só em B com vão P2|P9 só em B → poste_so_b e vao_so_b com para == "b-P9"

def test_dois_vaos_no_mesmo_par_so_um_divergente() -> None:
    # par P1|P2 com vão MT (cabo "3x1/0") e BT (cabo "BT 70"); B muda só o comprimento do BT
    [d] = comparar_leituras(a, b)["divergencias"]
    assert (d["tipo"], d["campo"], d["cabo_a"], d["cabo_b"]) == ("vao_atributo", "comprimento_m", "BT 70", "BT 70")

def test_simbolo_em_um_so_leitor_gera_divergencia_simbolos_com_bbox_que_o_contem() -> None: ...

def test_comprimento_divergente_alem_da_tolerancia() -> None:
    # 35,0 × 35,05 → sem divergência (tolerância 0,1 m do PROTOCOLO_FICHA); 35 × 40 → vao_atributo comprimento_m

def test_regioes_de_conferencia_nao_trazem_valores() -> None:
    assert all(set(r) == {"id", "pagina", "bbox"} for r in regioes_de_conferencia(comp_com_divergencias))

def test_regioes_sobrepostas_sao_fundidas_e_recortadas_a_pagina() -> None: ...
    # duas divergências a 0,01 uma da outra → 1 região; poste em x=0,005 → x0 == 0.0

def test_permutar_listas_nao_muda_o_resultado() -> None: ...
    # postes, vãos e símbolos de A e B em outra ordem → comparação idêntica

def test_trocar_a_e_b_espelha_as_divergencias() -> None: ...
    # comparar(b, a) × comparar(a, b): compara o multiconjunto de (tipo com so_a↔so_b trocado, pagina,
    # bbox, campo, par de ids de poste {a, b} trocado, cabo_a↔cabo_b trocados); sem os ids dNNN, sem
    # indice e sem de/para (que seguem a leitura da esquerda). A concordancia não é simétrica.

def test_cli_comparar_exige_a_e_b_congeladas_e_nao_sobrescreve(rodada) -> None: ...
```

- [ ] **Step 2:** pytest → FAIL.
- [ ] **Step 3:** implementar (`ficha_leitura_dupla.py` puro, sem E/S) e o subcomando; linha `.venv/Scripts/python.exe -m scripts.curation_ficha comparar --rodada RODADA --pdf ID` na skill e no contrato.
- [ ] **Step 4:** pytest dos quatro arquivos → PASS; ruff, format, mypy limpos.
- [ ] **Step 5:** commit `feat(curadoria): comparação de leitura dupla de fichas e regiões de conferência`.

---

### Task 3: Consolidar a referência sem palpite

**Files:**
- Modify: `scripts/ficha_leitura_dupla.py`, `scripts/curation_ficha.py` (subcomando `consolidar`), skill e contrato (linhas de `consolidar`, com e sem `--sem-terceiro`)
- Test: `tests/unit/test_ficha_leitura_dupla.py`, `tests/unit/test_curation_ficha.py`; rodar também `tests/unit/test_claude_curation_assets.py`

**Interfaces:**
- Consumes: Task 2 (`comparar_leituras`, formato de `divergencias`, públicos do avaliador), Task 1.
- Produces:
  - `consolidar(a: Mapping[str, Any], b: Mapping[str, Any], c: Mapping[str, Any] | None, comparacao: Mapping[str, Any], *, paginas: int) -> dict[str, Any]`: ficha `tipo: "referencia"` válida por `validar_ficha`, com `atributos_extras.consolidacao = {"resolvidas_por_c": int, "pendentes": int, "descartadas_por_maioria": int, "nao_cobertas_por_c": int, "excluidas": [{"pagina", "bbox", "motivo"}]}` e sem `atributos_extras.leitura`.
  - CLI `consolidar --rodada --pdf [--sem-terceiro --motivo TEXTO]`: exige `comparacao.json`; com regiões de conferência e sem C congelada, só roda com `--sem-terceiro` e `--motivo` (vai a `consolidacao.motivo_sem_terceiro`); `paginas` vem da entrada do PDF em `rodada.json`; grava `ficha/referencia.json` e registra o sha em `congelamento.json` com `leitor: "consolidada"`, `exposicao: false`. Recusa se `referencia.json` já existe.

Regras (C é casada a A ou B com `casar_postes`; "C cobre" = o centro do poste, ou os dois extremos do vão, está numa região da ficha C e fora das `regioes_ilegiveis` de C):

1. Par A–B, campo igual → valor de A. Campo diferente, ou pendente em só um leitor → se C cobre, tem poste casado e o campo não está pendente em C, e o valor de C é igual (`campo_acerta`) ao de A ou de B não pendente → esse valor (`resolvidas_por_c += 1`); senão o campo vai a `pendentes` com valor nulo (`null`; `[]` em estruturas) e `pendentes += 1`; se C não cobre, `nao_cobertas_por_c += 1` também. Pendente nos dois → pendente.
2. Símbolos do par: casam por inteiro (`casar_simbolos`) → os de A. Senão, os de quem C confirma por inteiro; senão `simbolos` em `pendentes` e lista vazia.
3. Poste só em um leitor: C tem poste casado → entra, com campos pela regra 1 entre esse leitor e C; C cobre e não tem poste → descartado (`descartadas_por_maioria += 1`); senão zona excluída (bbox do poste + `MARGEM_CONFERENCIA`, motivo `"poste_disputado"`).
4. Vãos, por par de postes consolidados e com o casamento de `casar_vaos_do_par` (o mesmo de `comparar_leituras`, inclusive para C): vão nos dois → atributos pela regra 1, atributo a atributo, no `pendentes` do vão; vão só em um → C tem o vão casado → entra, atributos pela regra 1; C cobre os dois extremos e não tem → descartado; senão os dois extremos viram zonas excluídas (motivo `"vao_disputado"`).
5. `regioes_ilegiveis` de A e de B viram zonas excluídas (motivo `"ilegivel"`).
6. Com zonas excluídas, `escopo_anotacao` vira `regional`: para cada página de 1 a `paginas`, `[0, 0, 1, 1]` menos as zonas daquela página (subtração de retângulos, até 4 por corte); postes cujo centro cai numa zona saem, com seus vãos. Sem zonas, `completo`.
7. Ids: os de A; poste que só B traz (confirmado por C) recebe `"b-" + id`; ids de símbolo idem.

- [ ] **Step 1: Write the failing tests**

```python
def test_consolidar_sem_divergencia_reproduz_a_sem_metadados_de_leitura() -> None: ...
def test_campo_divergente_resolvido_por_c() -> None:
    # A estruturas N1, B N3, C N3 → N3; resolvidas_por_c == 1
def test_campo_divergente_sem_acordo_vira_pendente_nulo() -> None:
    # A N1, B N3, C U3 → "estruturas" em pendentes, estruturas == []
def test_divergencia_fora_das_regioes_de_c_conta_nao_coberta() -> None: ...
def test_simbolos_sem_acordo_viram_pendentes() -> None: ...
def test_poste_so_em_a_confirmado_por_c_entra() -> None: ...
def test_poste_so_em_a_negado_por_c_e_descartado() -> None: ...
def test_consolidar_sem_c_exclui_poste_disputado_do_escopo() -> None:
    ref = consolidar(a, b_sem_p3, None, comparar_leituras(a, b_sem_p3), paginas=1)
    assert ref["escopo_anotacao"]["tipo"] == "regional"
    assert "P3" not in {p["id"] for p in ref["postes"]}
    assert avaliar(ref, predicao_com_p3)["postes"]["fp"] == 0
def test_regiao_ilegivel_vira_zona_excluida() -> None: ...
def test_vao_so_em_um_leitor_sem_c_exclui_os_extremos() -> None: ...
def test_consolidar_dois_vaos_no_mesmo_par_nao_troca_atributos() -> None: ...
    # MT igual nos dois; BT com comprimento divergente resolvido por C → MT intacto, BT com o valor de C
def test_escopo_cobre_todas_as_paginas_menos_as_zonas() -> None: ...
    # paginas=2, zona só na página 1 → página 2 inteira é região; centro da zona não está em nenhuma região
def test_cli_consolidar_exige_c_ou_sem_terceiro_com_motivo(rodada) -> None: ...
```

- [ ] **Step 2:** pytest → FAIL.
- [ ] **Step 3:** implementar; linhas `consolidar --rodada RODADA --pdf ID` e `consolidar --rodada RODADA --pdf ID --sem-terceiro --motivo "MOTIVO"` na skill e no contrato.
- [ ] **Step 4:** pytest → PASS; ruff, format, mypy; nenhuma função nova com rank Radon E/F.
- [ ] **Step 5:** commit `feat(curadoria): consolidação da ficha de referência sem palpite`.

---

### Task 4: Baseline do analisador atual por poste

**Files:**
- Modify: `scripts/curation_ficha.py` (subcomando `baseline`), skill e contrato (linhas de `baseline`)
- Test: `tests/unit/test_curation_ficha.py`; rodar também `tests/unit/test_claude_curation_assets.py`

**Interfaces:**
- Consumes: `scripts.benchmark_ficha_poste.executar(pdf, referencia, saida, *, native_only, runtime_directory)`; `zeny_project_handler.adapters.analysis.tesseract_runtime.inspect_tesseract_runtime`; `curation_round.caminho_pdf_fonte`; Tasks 1 e 3.
- Produces:
  - `agregar_avaliacoes(avaliacoes: Mapping[str, Mapping[str, Any] | None]) -> dict[str, Any]` (chave = `pdf_id`; `None` = sem referência): `{"por_pdf": {pdf_id: {...} | {"situacao": "sem_referencia"}}, "total": {...}}`; cada bloco tem `postes` (tp, fp, fn, precisão, recall), `campos` (por campo: acertos, total, taxa), `vaos` (tp, fp, fn, `comprimento` e `cabo` com acertos/total), `simbolos` (tp, fp, fn) e `distancias_casamento` (ordenada, dos `pares`); taxas recalculadas das somas, nunca média de taxas.
  - CLI `baseline --rodada [--pdf ID ...] [--native-only] [--runtime-directory DIR] [--parcial]`: recusa se algum PDF selecionado não tem `referencia.json`, salvo `--parcial`; sem `--native-only`, confere o OCR português uma vez antes do laço (`inspect_tesseract_runtime`) e falha cedo com o diagnóstico; confere o sha de cada `referencia.json` contra `congelamento.json`; usa a próxima versão livre `vNNN` e roda `executar` com saída `ficha/baseline-vNNN/`; grava `fichas/baseline-vNNN-resumo.json` (`schema_version` `"curadoria-ficha-baseline-v1"`, `versao`, opções, `parcial`, `versoes` com Pillow e PyMuPDF instalados, `gerador` de uma predição, e o agregado) e `.md` (tabela por PDF e total com denominadores). Falha do analisador num PDF → `{"situacao": "falha", "erro": str}` (falha não é zero) e código 1 no fim.

- [ ] **Step 1: Write the failing tests**

```python
def test_agregar_soma_contagens_e_recalcula_taxas() -> None:
    # dois relatórios sintéticos (2 e 1 tp) → total tp 3, precisão = 3/(3+fp_total)
def test_agregar_lista_pdf_sem_referencia() -> None:
    assert agregar_avaliacoes({"01-x": rel, "02-y": None})["por_pdf"]["02-y"] == {"situacao": "sem_referencia"}
def test_cli_baseline_recusa_pdf_sem_referencia_sem_parcial(rodada) -> None: ...
def test_cli_baseline_recusa_referencia_adulterada(rodada) -> None: ...
def test_cli_baseline_sem_ocr_falha_antes_do_primeiro_pdf(rodada, monkeypatch) -> None: ...
def test_cli_baseline_grava_versao_nova_sem_sobrescrever(rodada) -> None:
    # duas execuções --native-only → baseline-v001 e baseline-v002, os dois resumos preservados
def test_cli_baseline_grava_resumo_sem_caminho_absoluto(rodada) -> None:
    # PDF sintético de rede de 2 postes (o de tests/unit/test_benchmark_ficha_poste.py), --native-only;
    # o resumo cita pdf_id e não contém str(tmp_path) nem o nome do arquivo PDF
def test_cli_baseline_registra_falha_sem_zerar(rodada, monkeypatch) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar (linhas `baseline --rodada RODADA` e `baseline --rodada RODADA --native-only` na skill e no contrato) → PASS; ruff, format, mypy.
- [ ] **Step 5:** commit `feat(curadoria): baseline por poste do analisador atual sobre a rodada`.

---

### Task 5: Amostra humana e taxa de erro de rótulo

**Files:**
- Modify: `scripts/curation_ficha.py` (subcomandos `amostra`, `responder` e `taxa`), skill e contrato (linhas)
- Test: `tests/unit/test_curation_ficha.py`; rodar também `tests/unit/test_claude_curation_assets.py`

**Interfaces:**
- Consumes: Tasks 1 e 3; `curation_round.caminho_pdf_fonte`; PyMuPDF para o recorte.
- Produces:
  - `sortear_amostra(postes_por_pdf: Mapping[str, Sequence[str]], tamanho: int, semente: int, *, excluir: Collection[tuple[str, str]] = ()) -> list[tuple[str, str]]`: determinística; rodízio entre PDFs ordenados (estratificada por folha), sorteio dentro de cada PDF com `random.Random(semente)`; ignora os pares de `excluir`; `tamanho` maior que a população → toda a população restante.
  - `intervalo_wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None` (`None` se `n == 0`).
  - CLI `amostra --rodada --tamanho N --semente S [--ampliar]`: só PDFs com `referencia.json`; sem `--ampliar` recusa se já existe amostra; com `--ampliar` cria a próxima `amostra-vNNN` excluindo os itens já sorteados. Grava `amostra.json` (`[{"item": "NN", "pdf_id", "poste_id", "pagina", "bbox", "campos": {identificador, estruturas, poste, coordenada, simbolos, vaos_ligados, pendentes}, "recorte": "NN.png"}]`), `NN.png` (página a 300 dpi recortada na bbox do poste + 0,04, recortada à página) e `amostra.md` (uma seção por item com a imagem, os campos e as perguntas: a ficha está correta? quais campos erram? o item não é poste? há poste ou vão da rede visível no recorte que não está na ficha?).
  - CLI `responder --rodada --versao N --arquivo ARQ`: valida as respostas (regras abaixo) e grava `amostra-vNNN/respostas.json`; recusa se já existe (as respostas não são regravadas).
  - CLI `taxa --rodada`: lê `respostas.json` de cada `amostra-vNNN` (`{"NN": {"correto": bool, "campos_errados": [...], "nao_e_poste": bool, "omissao": bool, "nota": str}}`), exige resposta para todos os itens e `campos_errados` não vazio quando `correto` é falso e `nao_e_poste` é falso (campos em `identificador`, `estruturas`, `poste`, `coordenada`, `simbolos`, `vaos`); recusa, citando a versão, se alguma `amostra-vNNN` não tem `respostas.json`; grava `amostra-humana/taxa-vNNN.json` (versão = maior amostra incluída; recusa se já existe) com, por versão e no total: `itens`, `postes_com_erro` (k, n, taxa, `wilson95`), `nao_e_poste`, `omissoes` (denominador = recortes) e `por_campo` (`erros`, `avaliados`, sem os itens em que o campo está em `pendentes`).

- [ ] **Step 1: Write the failing tests**

```python
def test_sortear_amostra_e_deterministica_e_estratificada() -> None:
    pop = {"01-a": ["P1", "P2", "P3"], "02-b": ["P1"], "03-c": ["P1", "P2"]}
    s = sortear_amostra(pop, 3, 7)
    assert s == sortear_amostra(pop, 3, 7) and {pdf for pdf, _ in s} == set(pop)
def test_sortear_amostra_maior_que_populacao_devolve_o_restante() -> None: ...
def test_intervalo_wilson_conhecido() -> None:
    assert intervalo_wilson(2, 20) == pytest.approx((0.0279, 0.3010), abs=1e-3)
    assert intervalo_wilson(0, 0) is None
def test_cli_amostra_grava_recortes_e_md_sem_nome_do_pdf(rodada) -> None: ...
def test_cli_amostra_ampliar_cria_v002_sem_repetir_itens(rodada) -> None: ...
def test_cli_taxa_calcula_por_poste_campo_omissao_e_nao_poste(rodada) -> None: ...
def test_cli_responder_recusa_resposta_faltando_erro_sem_campo_e_regravacao(rodada) -> None: ...
def test_cli_taxa_versiona_e_nao_sobrescreve(rodada) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar (documento PyMuPDF fechado com `with`; linhas `amostra --rodada RODADA --tamanho N --semente S`, `amostra --rodada RODADA --tamanho N --semente S --ampliar`, `responder --rodada RODADA --versao N --arquivo ARQ` e `taxa --rodada RODADA` na skill e no contrato) → PASS; ruff, format, mypy.
- [ ] **Step 5:** commit `feat(curadoria): amostra humana de fichas e taxa de erro de rótulo`.

---

### Task 6: Leitor visual em modo ficha, skill, contrato e CLAUDE.md

**Files:**
- Modify: `.claude/agents/curadoria-leitor-visual.md`, `.claude/skills/curadoria-simbologia/SKILL.md`, `docs/fluxo-curadoria-incremental-simbologia.md`, `CLAUDE.md`, `tests/unit/test_claude_curation_assets.py`
- Test: `tests/unit/test_claude_curation_assets.py`

**Interfaces:**
- Consumes: os subcomandos, opções e caminhos das Tasks 1–5, exatamente como definidos acima.

Conteúdo:
- **Agente leitor:** seção "Modo ficha", ativada quando a tarefa traz `modo: ficha` e `leitor: a|b|c`. Entrada: `RODADA`, `ID`, `sha256`, `caminho_relativo`, `modelo`, `leitor`, saída `RODADA/pdfs/ID/ficha/rascunho-LEITOR/ficha.json` e, só para `c`, o caminho de `regioes-conferencia.json`. Permitido a mais: ler `docs/schemas/ficha-poste.schema.json`; gravar só a saída; rodar só `.venv/Scripts/python.exe -m scripts.curation_ficha validar --rodada RODADA --pdf ID --leitor LEITOR --arquivo RODADA/pdfs/ID/ficha/rascunho-LEITOR/ficha.json`. Proibido a mais: `ficha/rascunho-*` de outro leitor, `ficha/leitura-*.json`, `ficha/congelamento.json`, `ficha/comparacao.json`, `ficha/referencia.json`, `ficha/baseline-*`, `fichas/`. Regras: uma entrada por poste da rede (identificador, estruturas, poste, coordenada escrita na folha, símbolos associados com `class_code` do inventário e bbox), vãos com comprimento e cabo escritos; `null` só para o que a folha não tem; o que não dá para ler vai em `pendentes`; área ilegível em `atributos_extras.leitura.regioes_ilegiveis`; normalizar U+200B/U+FEFF; A e B com escopo `completo` e todos os tiles `a_revisar` revisados ou cobertos por região ilegível; C com escopo `regional` dentro das regiões recebidas, lendo só os tiles que as tocam; `tiles_revisados` só com tiles abertos. As regras do modo normal continuam iguais. A `description` do frontmatter cita o modo ficha.
- **Skill e contrato:** a seção "Rodada de fichas do poste" ganha o procedimento completo, com as mesmas linhas de comando nos dois arquivos: `curation_round init` e `curation_render` como hoje (sem inferência nem comparação de símbolos); leitores `a` e `b` por PDF (instâncias novas, `modo: ficha`) em paralelo; `validar`/`congelar` de cada um; `comparar`; leitor `c` (instância nova) só com as regiões de conferência, quando houver; `consolidar`; `amostra` → conferência pelo usuário → `responder` → `taxa` (ampliar a amostra se a taxa de erro de poste passar de 20%); `baseline` só depois de todas as folhas consolidadas (com `--native-only` e pendência de OCR registrada se o OCR português não estiver disponível). Diz que no modo ficha a auditoria amostral de tiles não roda e a conferência é o leitor C.
- **Contrato, invariante:** substitui o parágrafo "Uma rodada **não treina o assistente de forma permanente**…" pelo invariante revisado do ADR 0017: os rótulos (fichas consolidadas) podem alimentar o treino; a leitura de avaliação continua cega; o conjunto de avaliação é separado por folha, congelado e nunca usado no treino; pré-marcação só no conjunto de treino; conhecimento duradouro do analisador continua sendo mudança versionada em algoritmos, pacotes e fixtures.
- **CLAUDE.md:** na seção "Curadoria de simbologia", acrescente `curation_ficha.py` à lista de CLIs e uma frase sobre a rodada de fichas.

- [ ] **Step 1:** acrescentar a `tests/unit/test_claude_curation_assets.py` testes que falham: o leitor tem a seção "Modo ficha", cita `scripts.curation_ficha validar` e proíbe `comparacao.json`, `referencia.json` e `leitura-*.json` da ficha; a skill cita `modo: ficha` e "leitor C"; o contrato não contém mais "não treina o assistente" e cita o ADR 0017.
- [ ] **Step 2:** pytest do arquivo → FAIL.
- [ ] **Step 3:** editar os documentos.
- [ ] **Step 4:** pytest do arquivo → PASS (os testes existentes continuam verdes).
- [ ] **Step 5:** commit `docs(curadoria): leitor em modo ficha, rodada de fichas e invariante do ADR 0017`.

---

## Execução operacional (orquestrador, depois das Tasks 1–6 revisadas)

Roda a partir do worktree, com o corpus `examples/` e a rodada em `tmp/` do checkout principal (protocolo do roadmap). `RODADA` = `<checkout principal>/tmp/curadoria-simbologia/AAAAMMDD-HHMM-fichas`.

1. **Pré-condição do leitor, antes de qualquer disparo:** a sessão carrega os agentes de projeto do checkout em que foi aberta. Se ela foi aberta no checkout principal e o `.claude/agents/curadoria-leitor-visual.md` de lá não tem "Modo ficha", pare sem disparar: o usuário reabre `claude --agent orquestrador` no diretório do worktree, e a execução retoma daqui pelo ledger.
2. `curation_round init --rodada RODADA --raiz <examples do checkout principal> --concorrencia 4`; `curation_render --rodada RODADA --onda K --jobs 4` para cada onda.
3. Leitores `a` e `b` por PDF (instâncias novas, em segundo plano, até 4 por vez, sem `model`), cada um só com as entradas do modo ficha. `validar` e `congelar` cada leitura; leitura incompleta volta ao mesmo leitor antes de congelar.
4. `comparar` por PDF; leitor `c` (instância nova) para cada PDF com regiões de conferência; `validar`/`congelar` `c`; `consolidar`.
5. `amostra --tamanho 20 --semente 20261103`; o usuário confere os recortes de `amostra.md` (entrevista); o orquestrador grava as respostas com `responder` e roda `taxa`. Taxa de erro de poste acima de 20% → `amostra --ampliar --tamanho 20 --semente 20261104`, nova conferência e `taxa` de novo.
6. Baseline: conferir antes se `<checkout principal>/tmp/benchmark-runtime` tem o OCR português e passar esse caminho em `--runtime-directory`. Sem OCR, `--native-only`, com o OCR como pendência e decisão para o usuário (alternativa: rodar o baseline na imagem Docker, que tem o Tesseract). Baseline nativo subestima as famílias sem texto nativo e não serve sozinho para a decisão 7 do design.
7. `RODADA/fichas/relatorio.md`: leitores e modelo; concordância A × B por PDF (postes, campos, vãos, símbolos, com denominadores); divergências por tipo, resolvidas por C, não cobertas, pendentes e zonas excluídas; distribuições de distância de casamento (calibração R4) e de IoU de símbolos; taxa de erro da amostra humana com intervalo de Wilson, omissões e não-postes; baseline por PDF e total, com opções e versões de Pillow/PyMuPDF.
8. Critérios: `git grep -n "PROJETO DE REDE NS"` vazio; gate completo verde.

## Revisão de arquitetura

- **Veredito:** aprovado com notas, na rodada 2 (`revisor-arquitetura`, modelo opus).
- **Rodadas:** 2. Rodada 0 bloqueou com 6 Importantes (guarda de `.claude/` e suíte verde por tarefa, cobertura do escopo completo de A/B, auditor fora do escopo sem registro, identidade de vão no mesmo par, versões sobrescritas no baseline e na amostra, amostra humana sem omissão nem não-poste) e 11 Menores; rodada 1 bloqueou com 1 Importante novo (cobertura das regiões do leitor C contra os tiles abertos) e 3 Menores; rodada 2 aprovou.
- **Nota Menor:** `taxa` com amostra ainda sem respostas — aplicada no texto da Task 5 (fail-closed: recusa citando a versão), com o caso a mais em `test_cli_taxa_versiona_e_nao_sobrescreve`.
- **Não verificado pelo revisor:** bbox normalizada dos tiles no `indice-tiles.json`; mensagens de `_erros_cobertura` preservadas na extração de `tiles_nao_cobertos` (o `test_curation_reference.py` roda na Task 1).
