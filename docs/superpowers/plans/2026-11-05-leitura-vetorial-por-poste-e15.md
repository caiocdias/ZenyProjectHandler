# E15 — Ficha predita a partir das propostas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dar à ficha predita do benchmark por poste uma segunda fonte, `propostas-v1`, que lê as propostas da interpretação (postes, estruturas, equipamentos e cabos propostos) em vez do projeto promovido, mantendo `projeto-promovido-v1` selecionável e o baseline nas 16 folhas rodando em processos paralelos.

**Architecture:** só `scripts/` muda. Um módulo novo, `scripts/ficha_predita_propostas.py`, monta a ficha `predicao` (formato v1, sem mudança) a partir de `variante["semantic"]` (`elementos`/`relacoes`). `scripts/benchmark_ficha_poste.py` escolhe o gerador por `versao_extracao`. `scripts/curation_ficha.py baseline` repassa a versão e ganha `--processos N`, com saída igual à serial.

**Tech Stack:** Python 3.11, pytest (+xdist), `concurrent.futures.ProcessPoolExecutor`.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E15 — Ficha predita a partir das propostas"; `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md`, seção "E14, E15 e E16 em resumo"; handoffs da E02 (R2, formato v1, R4) e da E03 (baseline).

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`. A ficha do poste não é entidade persistida nova, e nenhuma migração SQLite é feita.
- Mudança de comportamento de saída incrementa a versão do extrator ou do interpretador (ADR 0006). Esta etapa não muda o analisador: a versão nova é só do gerador da ficha (`versao_extracao`).
- PDFs reais, recortes, rótulos, conjuntos de dados e pesos nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos.
- Documentação enxuta: nada de histórico de execução em arquivo versionado.
- Sem dependência nova.
- Fora de escopo: mudar o analisador ou a promoção; mudar o formato v1 da ficha (`docs/schemas/ficha-poste.schema.json`) ou o casamento 0,02/0,05 (D2); associação geométrica ao poste (E07).
- Não tocar em `src/`, nem em `tests/conftest.py`, nem nos arquivos do plano da E06 aberta (conferido na "File Structure").
- Nenhuma leitura de `examples/avaliacao-cega/`.
- Suíte inteira: `-n` informado em cada despacho (orçamento de máquina: 20 ÷ suítes simultâneas da sessão).

## Decisões de desenho (rulings do planejador)

- **R-E15-1, default da CLI:** o default de `--versao-extracao` continua `projeto-promovido-v1`. Assim, todo comando e teste existente reproduz a saída anterior (critério 1), e quem quer a fonte nova pede `propostas-v1` explicitamente. A E07 passa o flag. Custo se errado: um flag a mais nos comandos da E07.
- **R-E15-2, o que é proposta "presente":** `estado_revisao` em `PROPOSTA`, `CONFIRMADA` ou `CONFLITANTE`. `REJEITADA` nunca entra, nem como elemento nem como relação.
- **R-E15-3, afirmado × pendente (risco "propostas pendentes infladas"):** um campo é **pendente** quando a proposta que o fornece está `CONFLITANTE` ou tem verdadeira alguma das chaves de pendência da promoção. As chaves são as de `automatic_promotion.py:186-199`, copiadas como constante `CHAVES_PENDENCIA` no módulo novo, com comentário que aponta a origem. Campo pendente entra com o valor e com o nome em `pendentes` do poste (ou do vão). Assim, o avaliador o conta à parte (`ficha_poste_avaliador.py:203`).
- **R-E15-4, ligações só por relação proposta:** estrutura → poste por `INSTALADA_EM`, equipamento → poste por `INSTALADO_EM`, cabo → postes por `CONECTA`. Não há casamento geométrico: associação é a E07. Se o pipeline não emite a relação numa folha, o FN aparece no baseline, e essa é a medida honesta da leitura atual.
- **R-E15-5, leitura dos atributos:** as chaves são as da promoção, lidas no script, sem importar privados de `src/`:
  - identificador: `atributos_sugeridos["identificador_operacional"]`, com `strip()`, e vazio vira `None`;
  - poste: `codigo_observado`, exceto quando é poste de símbolo (`origem_simbolo_ocorrencia_id` presente), que vira `None` com `atributos_extras.origem="simbolo"`, como em `benchmark_ficha_poste._poste`;
  - coordenada: `coordenada_leste`/`coordenada_norte`, as duas presentes, ou `None`. A `zona` é sempre `None`: a interpretação não emite zona (grep de `coordenada_zona` vazio em `src/`), como em `CoordenadaCampo` hoje;
  - comprimento do vão: `comprimento_m` > 0 do cabo (`origem_comprimento="ANOTACAO_DESENHO"`); senão, a distância entre as coordenadas dos dois postes, arredondada a 0,01 (`"COORDENADAS"`), como em `_cable_length`; senão, `None`;
  - cabo: `codigo_observado` do cabo;
  - símbolo: `atributos_sugeridos["simbolo_classe"]` do equipamento, validado com `_erro_classe("simbolo", classe)`, com as mesmas contagens de `_anexar_simbolos`.
- **R-E15-6, numeração do baseline:** o fechamento roda primeiro `propostas-v1` (vira `baseline-v004`, o nome do design) e depois `projeto-promovido-v1` (vira `baseline-v005`), que tem de reproduzir as contagens da `baseline-v003`.

## Review Focus

1. Proposta `REJEITADA` (elemento ou relação) não pode produzir poste, estrutura, símbolo nem vão → testes negativos na Task 1.
2. Estrutura ligada a poste rejeitado ou a poste inexistente não pode virar estrutura de outro poste nem quebrar a ficha → contagem `estruturas_sem_poste` e teste na Task 1.
3. Cabo com `CONECTA` para 1 poste só, para 3 postes ou duas vezes o mesmo poste não vira vão inventado → teste parametrizado na Task 1.
4. A ficha gerada pela fonte nova precisa passar em `validar_ficha` (ids únicos, `pendentes` sem repetição, enums do schema) mesmo com proposta duplicada → teste de validade na Task 1.
5. `--processos N` com falha num PDF (o `_medir_pdf` captura e saneia) precisa produzir o mesmo resumo da serial e nunca deixar caminho absoluto → teste na Task 2.

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `scripts/ficha_predita_propostas.py` | criar | `ficha_predita_propostas(variante, pdf_sha256, *, native_only) -> dict`; `VERSAO_EXTRACAO_PROPOSTAS = "propostas-v1"`; `CHAVES_PENDENCIA` |
| `scripts/benchmark_ficha_poste.py` | modificar | `VERSOES_EXTRACAO`, parâmetro `versao_extracao` em `executar`, flag `--versao-extracao`, `_gerador` com a versão recebida |
| `scripts/curation_ficha.py` | modificar | `baseline(..., versao_extracao=..., processos=1)`, flags `--versao-extracao` e `--processos`, `versao_extracao` no resumo JSON e MD |
| `tests/unit/test_ficha_predita_propostas.py` | criar | fixtures sintéticas positiva e negativa da fonte nova, validade e CLI |
| `tests/unit/test_curation_ficha_baseline_processos.py` | criar | repasse da versão e igualdade serial × `--processos 4` |

Nenhum arquivo de `src/`, `tests/conftest.py`, `docs/schemas/`, locks, `.bat`, `CLAUDE.md` ou contrato de curadoria muda. Os testes existentes de `benchmark_ficha_poste` e `curation_ficha` não são editados: continuam passando com o default (R-E15-1).

## Tarefas e ondas

| Task | Estimativa | Depende de | Risco | Laboratório |
|---|---|---|---|---|
| 1 — gerador `propostas-v1` | 45 min | nenhuma | alto (núcleo da etapa) | não |
| 2 — baseline com versão e processos | 40 min | nenhuma (interface fixada abaixo; testes usam `monkeypatch`) | alto (concorrência) | não |

Onda 1: Tasks 1 e 2, com arquivos disjuntos. Soma: ~1h25 de tarefas, mais a revisão e o fechamento operacional, dentro do teto de ~3h.

---

### Task 1: gerador `propostas-v1`

**Files:**
- Create: `scripts/ficha_predita_propostas.py`
- Modify: `scripts/benchmark_ficha_poste.py` (constante na linha 37, `_gerador`, `executar`, `main`)
- Test: `tests/unit/test_ficha_predita_propostas.py`

**Interfaces:**
- Consumes: `variante` de `scripts.benchmark_network_pdf.run_variant`. Usa `variante["semantic"].elementos` (`PropostaElemento`), `variante["semantic"].relacoes` (`PropostaRelacao`, `interpretation_pipeline.py:64`), `variante["project"].documentos[*].paginas` (número da página por `pagina_id`), `analyzer`, `interpreter_version` e `registry_signature`. Usa também `scripts.ficha_poste._erro_classe` e `validar_ficha`.
- Produces:
  - `scripts.ficha_predita_propostas.VERSAO_EXTRACAO_PROPOSTAS: Final = "propostas-v1"`
  - `ficha_predita_propostas(variante: Mapping[str, Any], pdf_sha256: str, *, native_only: bool) -> dict[str, Any]`
  - `scripts.benchmark_ficha_poste.VERSAO_EXTRACAO` continua `"projeto-promovido-v1"`, e `VERSOES_EXTRACAO: Final = (VERSAO_EXTRACAO, VERSAO_EXTRACAO_PROPOSTAS)`
  - `executar(pdf, referencia, saida, *, native_only, runtime_directory, versao_extracao: str = VERSAO_EXTRACAO) -> dict[str, Any]`, que levanta `ValueError("versao_extracao desconhecida: …")` antes de rodar o analisador
  - `_gerador(variante, *, native_only, versao_extracao)`: o campo `gerador.versao_extracao` traz a versão usada

Regras de montagem (R-E15-2 a R-E15-5):
- poste: um por proposta `POSTE` presente com `geometria`, com `id = str(proposta.id)`, `pagina` pelo `pagina_id` da geometria e `bbox` como `benchmark_ficha_poste._bbox`;
- estruturas: `codigo_observado` de propostas `ESTRUTURA_MT/BT` presentes com relação `INSTALADA_EM` presente para um poste da ficha, ordenadas. Estrutura sem `codigo_observado` é ignorada; sem poste da ficha, conta em `atributos_extras.estruturas_sem_poste` (chave só quando > 0);
- símbolos: `EQUIPAMENTO` presente com `INSTALADO_EM` presente para um poste da ficha, com as mesmas contagens e regras de `_anexar_simbolos`;
- vãos: um por `CABO` presente com exatamente 2 relações `CONECTA` presentes para 2 postes **distintos** da ficha (`de`/`para` na ordem dos ids de relação ordenados). Os outros cabos contam em `atributos_extras.cabos_sem_vao` (chave só quando > 0);
- pendência: o campo vai para `pendentes` quando a proposta que o fornece é pendente (R-E15-3). No poste, a pendência marca `identificador`, `poste` e `coordenada`; na estrutura, `estruturas` do poste; no equipamento, `simbolos` do poste; no cabo, `comprimento_m` e `cabo` do vão. Sem repetição, em ordem.

- [ ] **Step 1: Write the failing tests** em `tests/unit/test_ficha_predita_propostas.py`. Monte `variante` sintética como os testes de `test_benchmark_ficha_poste.py` fazem (objetos de domínio reais, `SHA_QUALQUER`), com um projeto promovido **vazio**, para provar que a fonte é a proposta:
  - `test_propostas_presentes_viram_ficha`: 2 postes `PROPOSTA` (ids "P1"/"P2", coordenadas), 1 `ESTRUTURA_MT` "N3" `INSTALADA_EM` P1, 1 equipamento `simbolo_classe` do inventário `INSTALADO_EM` P2 com bbox de área > 0, e 1 cabo com 2 `CONECTA` e `comprimento_m=35`. Asserções: 2 postes; `estruturas == ["N3"]` em P1; 1 símbolo em P2; 1 vão com `comprimento_m == 35.0`, `atributos_extras.origem_comprimento == "ANOTACAO_DESENHO"`; `gerador.versao_extracao == "propostas-v1"`; `validar_ficha(ficha) == []`.
  - `test_proposta_rejeitada_nao_vira_campo`, parametrizado (ids determinísticos) sobre: poste `REJEITADA`; relação `INSTALADA_EM` `REJEITADA`; equipamento `REJEITADA`; cabo `REJEITADA`; uma das 2 `CONECTA` `REJEITADA`. Cada caso afirma a ausência do campo correspondente.
  - `test_proposta_ausente_nao_vira_campo`: a semântica sem estrutura nem cabo dá `estruturas == []` e `vaos == []`.
  - `test_proposta_pendente_vai_para_pendentes`, parametrizado sobre `CONFLITANTE` e sobre `comprimento_pendente=True`, no poste, na estrutura e no cabo. Afirma o valor presente e o nome do campo em `pendentes`.
  - `test_cabo_sem_dois_postes_distintos_nao_vira_vao`, parametrizado: 1 `CONECTA`, 3 `CONECTA`, 2 `CONECTA` para o mesmo poste. Afirma `vaos == []` e `atributos_extras["cabos_sem_vao"] == 1`.
  - `test_estrutura_sem_poste_da_ficha_e_contada`: afirma `atributos_extras["estruturas_sem_poste"] == 1`.
  - `test_comprimento_por_coordenadas`: cabo sem `comprimento_m`, postes em (0, 0) e (3, 4) → `5.0` e `"COORDENADAS"`.
  - `test_metricas_nas_duas_fontes`: com uma referência sintética de 2 postes e 1 vão (reuse `_referencia_sintetica` de `tests/unit/test_benchmark_ficha_poste.py`) e uma `variante` cujo projeto promovido é vazio e cujas propostas trazem os 2 postes: `avaliar(ref, ficha_predita(...))` dá postes `tp == 0`, e `avaliar(ref, ficha_predita_propostas(...))` dá `tp == 2`, `fp == 0`.
  - `test_executar_recusa_versao_desconhecida` (`ValueError` antes do analisador, com `run_variant` trocado por função que falha se chamada) e `test_cli_aceita_versao_extracao` (`main([... "--versao-extracao", "propostas-v1"])` com `run_variant` sintético via `monkeypatch`; o `ficha-predita.json` gravado traz `"propostas-v1"`).
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_ficha_predita_propostas.py -q` → FAIL (`ModuleNotFoundError: scripts.ficha_predita_propostas`).
- [ ] **Step 3:** implemente `scripts/ficha_predita_propostas.py` e o repasse em `benchmark_ficha_poste.py`. Para reaproveitar `_bbox`, `_json` e o bloco `gerador` sem duplicar, mova-os para cima ou importe-os de `benchmark_ficha_poste`, sem import circular: o módulo novo importa de `benchmark_ficha_poste`, e `benchmark_ficha_poste` importa o módulo novo dentro de `executar`, ou extraia um terceiro módulo pequeno. Não mude a saída de `ficha_predita`.
- [ ] **Step 4:** `.venv/Scripts/python.exe -m pytest tests/unit/test_ficha_predita_propostas.py tests/unit/test_benchmark_ficha_poste.py tests/unit/test_benchmark_ficha_poste_adversarial.py tests/unit/test_benchmark_ficha_poste_final_fix.py -q` → todos PASS; `ruff check`, `ruff format --check` e `mypy` limpos.
- [ ] **Step 5: Commit** (`feat: ficha predita a partir das propostas (propostas-v1)`).

### Task 2: baseline com versão de extração e processos

**Files:**
- Modify: `scripts/curation_ficha.py` (docstring do topo, `_medir_pdf`, `baseline`, `_markdown_baseline`, parser `baseline`, despacho do `main`)
- Test: `tests/unit/test_curation_ficha_baseline_processos.py`

**Interfaces:**
- Consumes: `scripts.benchmark_ficha_poste.executar(..., versao_extracao=...)`, fixado na Task 1. Nos testes desta tarefa, `executar_benchmark` é trocado por `monkeypatch` em `scripts.curation_ficha`, então a tarefa não espera a Task 1 para ficar verde. A suíte da onda integrada confere o encaixe.
- Produces:
  - `baseline(rodada_dir, pdf_ids=(), *, native_only=False, runtime_directory=RUNTIME_PADRAO, parcial=False, versao_extracao: str = "projeto-promovido-v1", processos: int = 1) -> Registro`
  - resumo com `"opcoes": {"native_only": …, "pdfs": …, "versao_extracao": …, "processos": …}`. **Atenção à igualdade serial × paralela:** `processos` entra só no `.md`, numa linha "Processos: N", e o JSON compara `opcoes` sem ele; documente isso na docstring. Alternativa equivalente: deixar `processos` fora do JSON. Escolha uma e teste-a;
  - o `.md` ganha a linha "Versão de extração: <versao>" abaixo do título;
  - CLI: `baseline --versao-extracao {projeto-promovido-v1,propostas-v1}` (choices vindos de `VERSOES_EXTRACAO`) e `--processos N` (inteiro ≥ 1; `0` ou negativo → erro do argparse; valor > 61 é limitado a 61 no Windows, porque `ProcessPoolExecutor` recusa mais, minor da E14).

Paralelismo: com `processos > 1` e mais de 1 PDF com referência, `_medir_pdf` roda em `ProcessPoolExecutor(max_workers=min(processos, n, 61))`, com `pool.map` na ordem de `selecionados`. Cada PDF grava só na própria pasta `saidas[pdf_id]`. O resumo, a trava e a escrita atômica ficam no processo principal. O resultado tem de ser idêntico ao serial, porque `agregar_avaliacoes` recebe o mesmo dicionário na mesma ordem. Funções despachadas ao pool precisam ser de nível de módulo (pickle no spawn do Windows).

- [ ] **Step 1: Write the failing tests** em `tests/unit/test_curation_ficha_baseline_processos.py`. Monte a rodada sintética como `tests/unit/test_curation_ficha_baseline.py` faz (reuse os helpers dele por import, sem editá-lo), com 3 PDFs sintéticos, e troque `executar_benchmark` por uma função de módulo determinística que grava `ficha-predita.json` e devolve um relatório de avaliação sintético que depende do `pdf_id`:
  - `test_versao_extracao_e_repassada`: `baseline(..., versao_extracao="propostas-v1")` chama o executor com `versao_extracao="propostas-v1"`, e o resumo traz `opcoes.versao_extracao == "propostas-v1"`;
  - `test_processos_4_produz_o_mesmo_resumo_que_a_serial`: rodadas gêmeas em `tmp_path` (serial e `processos=4`). Os `-resumo.json`, comparados como dicionários, são iguais, salvo o campo de `processos` conforme a escolha documentada, e os `avaliacao.json` por PDF são iguais byte a byte. O executor trocado precisa funcionar no spawn: defina-o num módulo importável, por exemplo uma função de nível de módulo no próprio arquivo de teste, e troque-o com `monkeypatch.setattr("scripts.curation_ficha.executar_benchmark", …)`. Se o spawn não enxergar o monkeypatch, injete o executor por parâmetro privado `_executor` em `baseline` e documente;
  - `test_processos_com_falha_num_pdf`: o executor levanta `RuntimeError` com o caminho absoluto do PDF num dos 3. As duas execuções dão o mesmo resumo, com `situacao == "falha"` e sem o caminho absoluto;
  - `test_processos_invalido_e_recusado`: `main(["baseline", "--rodada", …, "--processos", "0"])` → `SystemExit` com código 2;
  - `test_markdown_traz_versao`: o `.md` gerado contém `Versão de extração: propostas-v1`.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_ficha_baseline_processos.py -q` → FAIL (`TypeError: unexpected keyword argument 'versao_extracao'`).
- [ ] **Step 3:** implemente em `scripts/curation_ficha.py`.
- [ ] **Step 4:** `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_ficha_baseline_processos.py tests/unit/test_curation_ficha_baseline.py tests/unit/test_curation_ficha_baseline_ataque.py tests/unit/test_curation_ficha_baseline_sanear.py -q` → todos PASS; ruff, format e mypy limpos.
- [ ] **Step 5: Commit** (`feat: baseline da ficha com versao de extracao e processos`).

---

## Fechamento operacional (orquestrador, depois da onda integrada e antes da revisão final)

A rodada é `tmp/curadoria-simbologia/20261103-2300-fichas/` do **checkout principal**. Os PDFs ficam no `examples/` dele, só leitura. O código vem deste worktree: o orquestrador roda a partir do checkout principal, com `sys.path[0]` apontando para o worktree (`python -c "import sys; sys.path.insert(0, r'<worktree>'); sys.path.insert(1, r'<worktree>\src'); import runpy; runpy.run_module('scripts.curation_ficha', run_name='__main__', alter_sys=True)" baseline …`). Antes, confere com `__file__` que `scripts.curation_ficha` e `zeny_project_handler` vêm do worktree.

1. `baseline --rodada <rodada> --native-only --versao-extracao propostas-v1 --processos <n>` → `baseline-v004`, com denominadores por PDF e no total.
2. `baseline --rodada <rodada> --native-only --versao-extracao projeto-promovido-v1 --processos <n>` → `baseline-v005`. As contagens de `total` e `por_pdf` têm de ser iguais às da `baseline-v003`: comparação por script, com a saída anexada (critério 1).
3. Totais por campo e por família no handoff. A família de cada PDF vem do relatório do modelo de desenho da E04/E05 ou da coluna de família da rodada de glifos. Campos afirmados e pendentes vão separados, como manda o risco da etapa.
4. `git grep -n "PROJETO DE REDE NS"` só acha as linhas que citam o critério (critério 4).
5. `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` (critério 5), sem outra suíte da sessão rodando.

## Critérios de aceite → evidência

| Critério | Evidência |
|---|---|
| relatório traz a `versao_extracao` usada; a anterior reproduz a `baseline-v003` | `gerador.versao_extracao` em `ficha-predita.json` e `avaliacao.json`; `opcoes.versao_extracao` no resumo; passo 2 do fechamento |
| fixtures sintéticas produzem as métricas esperadas nas duas fontes | `test_metricas_nas_duas_fontes` e os demais testes da Task 1 |
| baseline novo em `tmp/` com denominadores; totais por campo e família no handoff | passos 1 e 3 do fechamento |
| nenhum nome de folha em arquivo versionado | passo 4 |
| `.bat` aprovado | passo 5 |
