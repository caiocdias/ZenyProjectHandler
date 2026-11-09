# E07.1 — Medição da ficha com o runner e golden do padrão Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** medir a ficha predita com o runner ligado, separar ganho de formato de ganho de leitura e fixar a saída da análise padrão antes da E07.2.

**Architecture:** só `scripts/` e `tests/`, sem tocar em `src/`. Um golden congela a saída do interpretador com a opção desligada. O benchmark ganha uma flag que chama `SymbolCompositionRunner` como o servidor faz, e a ficha predita ganha a fonte `propostas-v2`, que lê do que a interpretação já produz.

**Tech Stack:** Python 3.11, pytest, `scripts/` do benchmark por poste.

**Spec:** seção "E07.1" de `docs/roadmap-leitura-vetorial-por-poste.md`, com D18 e D19.

## Global Constraints

- Nenhum arquivo sob `src/` muda nesta etapa.
- `propostas-v1` e `projeto-promovido-v1` continuam produzindo a mesma saída de antes, sem a flag nova.
- Sem a flag, as chaves `gerador` e `opcoes` do resumo não ganham nada.
- PDFs reais, recortes e nomes de folha nunca entram no Git. Fixtures sintéticas positivas e negativas para todo comportamento novo.
- `examples/avaliacao-cega/` não é lido.
- Enquanto a E18 estiver aberta, este plano não edita `README.md`, `CLAUDE.md` nem `docs/especificacao-funcional.md`.
- Não editar `docs/roadmap-leitura-vetorial-por-poste.md`; o orquestrador cuida dele.

## Review Focus

- Golden frágil de outro jeito: ids dependem de uuid fixo e de relógio fixo; nada de `uuid4` no caso sintético (`complete_project` usa `uuid4` e não serve).
- Runner falhando numa folha: a medição daquela folha registra o erro como o baseline já faz, sem derrubar as outras.
- Proposta `REJEITADA` não entra em nenhuma fonte; cabo com um extremo só não vira vão composto; cabos de situações diferentes no mesmo par não se fundem.
- Vão composto com códigos iguais: o mesmo cabo repetido no mesmo par não vira `X / X`, e `codigo_observado` ausente não entra na união.
- ESTAI cujo `suporte_proposta_id` aponta para fora da ficha ou é texto inválido: não vira símbolo do poste errado.

## File Structure

| Arquivo | Tarefa | Responsabilidade |
|---|---|---|
| `tests/integration/test_golden_padrao_e07.py` (novo) | 1 | golden da análise padrão |
| `tests/fixtures/golden_padrao_e07.json` (novo) | 1 | saída congelada |
| `scripts/benchmark_network_pdf.py` | 2 | `run_variant` com runner opcional |
| `scripts/benchmark_ficha_poste.py` | 2, 3 | flag, `gerador`, seleção da fonte |
| `scripts/curation_ficha.py` | 2 | `--simbolos-modelo` no baseline |
| `tests/unit/test_benchmark_ficha_runner_e07.py` (novo) | 2 | flag e `gerador` |
| `scripts/ficha_predita_propostas.py` | 3, 4 | fonte `propostas-v2` |
| `docs/fluxo-curadoria-incremental-simbologia.md`, `examples/README.md` | 2, 3 | documentação da flag e das fontes |
| `tests/unit/test_ficha_predita_propostas_v2.py` (novo) | 3, 4 | fixtures da fonte nova |

Ondas: {1, 2} em paralelo (arquivos disjuntos), depois {3}, depois {4}. As Tasks 2 e 3 tocam `benchmark_ficha_poste.py` e os dois documentos; as 3 e 4 tocam `ficha_predita_propostas.py` e o teste, e a 4 parte da 3.

---

### Task 1: Golden da análise padrão

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** alto

**Files:**
- Create: `tests/integration/test_golden_padrao_e07.py`, `tests/fixtures/golden_padrao_e07.json`

**Interfaces:** Produces: `tests/fixtures/golden_padrao_e07.json`, que as E07.2 e E07.3 usam para provar D18. Consumes: `ExecutarPipelineInterpretacao`, `InterpretadorRegrasExplicitas`, `carregar_registro_regras_inicial`, a fixture e helpers de `tests/integration/test_interpretation_pipeline.py` como modelo.

- [ ] **Step 1: Caso sintético determinístico.** Em `test_golden_padrao_e07.py`, monte um projeto próprio e uma execução de extração com ids `uuid5` de constantes e relógio fixo (`interpretation_context` usa `uuid4`, via `complete_project`, e não serve; siga `_runner` de `test_interpretation_pipeline.py` e a forma das evidências de `_request` de `test_rule_based_interpreter.py`). O caso traz, no mínimo: dois postes com P distintos (`P1`, `P2`), com coordenada e nomenclatura, ligados por cabo com traçado e comprimento (dois `CONECTA`); duas leituras de poste com o mesmo identificador `P3`, a até 0,10 uma da outra e com código ou catálogo diferentes o bastante para não serem fundidas pela deduplicação (duplicata que hoje sobrevive); uma estrutura com rótulo `P3` equidistante, com diferença de até 0,004, das duas leituras de `P3` (empate que devolve nenhum); um cabo sem traçado único (`associacao_pendente`); estrutura MT com qualificador; estrutura BT; equipamento. Execute `executar(project.id, extraction_id)` sem `simbolos` nem `symbol_configuration_signature`.

- [ ] **Step 2: Serialização.** Função `_serializar(resultado) -> dict`: `execucao.id`, `execucao.metodo`, `execucao.versao_metodo`, `execucao.parametros` e, ordenados por id, **todos os campos** de cada `PropostaElemento` e `PropostaRelacao` do resultado, inclusive `situacao_projeto`, `tipo_catalogo_sugerido_id`, `confianca`, `justificativa` e `evidencia_ids`. A geometria sai como tipo, `pagina_id` e a lista ordenada de pontos, sem reduzir polilinha a caixa. Valores não JSON viram `str`. O dicionário passa por `json.loads(json.dumps(...))` antes de comparar, porque tupla não é igual a lista.

- [ ] **Step 3: Teste que falha sem o golden.**

```python
def test_analise_padrao_mantem_saida_congelada(...) -> None:
    resultado = _serializar(_executar(...))
    assert resultado == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_golden_e_da_opcao_desligada(...) -> None:
    resultado = _serializar(_executar(...))
    parametros = dict(resultado["parametros"])
    assert resultado["versao_metodo"] == "25.0"
    assert "semantica_simbolos_versao" not in parametros
    assert "simbolos_reconciliados_assinatura" not in parametros
    assert "configuracao_simbolos_assinatura" not in parametros
```

Rode: `.venv/Scripts/python.exe -m pytest tests/integration/test_golden_padrao_e07.py` → FAIL (arquivo ausente).

- [ ] **Step 4: Gere o golden uma vez**, no estado atual de `src/`, gravando `_serializar(...)` em `tests/fixtures/golden_padrao_e07.json` com `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)`. Confira a mão que o arquivo traz as 5 categorias, dois `CONECTA`, as duas leituras de `P3`, a estrutura do empate sem `INSTALADA_EM` e o cabo com `associacao_pendente` sem relação.

- [ ] **Step 5: Rode duas vezes** o mesmo comando, em processos diferentes → PASS as duas (determinismo).

- [ ] **Step 6: Commit** com a suíte da área verde; rode a suíte inteira uma vez antes do relatório.

---

### Task 2: Flag do runner no benchmark

**Estimativa:** 40 min · **Depende de:** nenhuma · **Risco:** alto

**Files:**
- Modify: `scripts/benchmark_network_pdf.py`, `scripts/benchmark_ficha_poste.py`, `scripts/curation_ficha.py`, `docs/fluxo-curadoria-incremental-simbologia.md`, `examples/README.md`
- Test: `tests/unit/test_benchmark_ficha_runner_e07.py`

**Interfaces:**
- Produces:
  - `run_variant(..., simbolos_modelo: bool = False)` em `benchmark_network_pdf.py`. Com `True`, depois de `ExecutarAnaliseDocumento`, chama `SymbolCompositionRunner(_settings_benchmark(directory)).run(project.documentos[0], <ReferenciaFontePdf>)` e passa `simbolos=` e `symbol_configuration_signature=runner.signature` a `.executar`.
  - `_settings_benchmark(directory: Path) -> ServerSettings`: `symbol_composition=True`, `symbol_profile="vector-only"`, `data_directory=directory / "dados-simbolos"` (criada), `symbol_model_path=None`, senha e string de conexão fictícias válidas, como em `tests/integration/test_model_symbols_runner.py:53-60`.
  - `executar(..., simbolos_modelo: bool = False)` em `benchmark_ficha_poste.py`, e `baseline(..., simbolos_modelo: bool = False)` em `curation_ficha.py`, com a flag de CLI `--simbolos-modelo`.
  - `run_variant` devolve `"symbol_configuration_signature"` na variante só quando ligada. `_gerador(variante, ...)` deriva dela, sem parâmetro novo: com a chave na variante, acrescenta `"simbolos_modelo": {"perfil": "vector-only", "assinatura": <valor>}`; sem a chave, o `gerador` não muda. Assim, as duas fontes registram o runner pela mesma chamada que já fazem.
  - O `opcoes` do resumo do baseline ganha `"simbolos_modelo": true` só com a flag, e a flag é repassada a `baseline` e `executar` só quando ligada (como a versão já é em `main`), para não mudar os fakes de assinatura estrita dos testes.
  - O repasse condicional vale também para `run_variant`: só recebe `simbolos_modelo` quando ligada, para não quebrar o espião de assinatura estrita em `tests/unit/test_benchmark_ficha_poste_adversarial.py:955`.
  - `baseline` e `executar` recusam `simbolos_modelo=True` com `versao_extracao` `projeto-promovido-v1`, com `ValueError` e mensagem dizendo que essa fonte não usa símbolos; a combinação não tem medida útil.

- [ ] **Step 1: Testes falhando** em `tests/unit/test_benchmark_ficha_runner_e07.py`:
  - `test_gerador_sem_flag_nao_ganha_chave` (fake de `variante`): `"simbolos_modelo" not in _gerador(variante, native_only=True)`.
  - `test_gerador_com_assinatura_na_variante_registra_perfil_e_assinatura`.
  - `test_ponta_a_ponta_executar_grava_simbolos_no_gerador`: `executar(..., simbolos_modelo=True, versao_extracao=propostas-v1)`, com `run_variant` fake devolvendo a chave; afirme `gerador.simbolos_modelo` na `ficha-predita.json` gravada.
  - `test_simbolos_modelo_recusa_projeto_promovido`.
  - `test_cli_baseline_aceita_a_flag_e_propaga`: `main` do `curation_ficha` com `monkeypatch` em `baseline`, afirmando `simbolos_modelo=True`.
  - `test_opcoes_do_resumo_so_mudam_com_a_flag`: sem flag, `"simbolos_modelo" not in resumo["opcoes"]`.
  - `test_run_variant_com_simbolos_chama_runner` (`tests/integration` se precisar de PDF sintético): fixture sintética de `tests/integration/test_model_symbols_runner.py`, com `simbolos_modelo=True`; afirme que `variante["semantic"].execucao.parametros` contém `semantica_simbolos_versao` e que há proposta com `origem_simbolo_ocorrencia_id` ou `simbolo_classe`.

- [ ] **Step 2: Rode e veja falhar.** `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_ficha_runner_e07.py` → FAIL.

- [ ] **Step 3: Implemente** conforme as Interfaces. O import do `SymbolCompositionRunner` e de `ServerSettings` fica dentro do ramo `simbolos_modelo`, para o caminho sem flag não carregar o servidor. Falha do runner numa folha segue o tratamento existente da medição por PDF do baseline, sem caminho novo.

- [ ] **Step 4: Documente** em `docs/fluxo-curadoria-incremental-simbologia.md` (bloco de `--versao-extracao`, linha 807) e em `examples/README.md`: uma linha sobre `--simbolos-modelo` (runner ligado, perfil `vector-only`), em prosa, sem linha de comando completa (`test_contrato_e_skill_executam_os_mesmos_clis` exige paridade com a skill).

- [ ] **Step 5: Rode e veja passar.** Mesmo comando → PASS.

- [ ] **Step 6: Commit** com a suíte da área verde; rode a suíte inteira uma vez antes do relatório.

---

### Task 3: Fonte `propostas-v2`: estruturas, código de cabo e ESTAI

**Estimativa:** 35 min · **Depende de:** 2 (mesmo arquivo) · **Risco:** alto

**Files:**
- Modify: `scripts/ficha_predita_propostas.py`, `scripts/benchmark_ficha_poste.py` (`VERSOES_EXTRACAO`, a constante `VERSAO_EXTRACAO_PROPOSTAS_V2 = "propostas-v2"`, a seleção da fonte em `executar` e o docstring), `scripts/curation_ficha.py` (só o docstring), `docs/fluxo-curadoria-incremental-simbologia.md` e `examples/README.md` (listam as fontes)
- Test: `tests/unit/test_ficha_predita_propostas_v2.py`

**Interfaces:**
- Produces: `ficha_predita_propostas(variante, pdf_sha256, *, native_only: bool, versao: str = VERSAO_EXTRACAO_PROPOSTAS)`. Com `versao="propostas-v1"` a saída é idêntica à atual. `gerador.versao_extracao` recebe a versão usada.

Regras da v2 (só nela):
1. **Estruturas:** usa `token_estrutura` dos atributos, com queda para `codigo_observado` quando ausente; lista ordenada.
2. **Código de cabo:** remove espaços depois de hífen (`N- (1N2)` → `N-(1N2)`); colapsa os demais.
3. **ESTAI:** equipamento com `simbolo_classe == "ESTAI"` e sem relação `INSTALADO_EM` entra no poste de `suporte_proposta_id`, se esse valor, comparado como texto a `str(poste_id)`, for de poste da ficha; senão conta `simbolos_de_poste_fora_da_ficha`, como hoje, sem interpretar o texto como UUID. Com relação, vale a relação.

- [ ] **Step 1: Testes falhando** em `tests/unit/test_ficha_predita_propostas_v2.py`, com propostas sintéticas no molde de `tests/unit/test_ficha_predita_propostas*.py`:
  - `test_v2_usa_token_com_qualificador`: `token_estrutura="U4(1)"` → `["U4(1)"]`; negativa sem token → `codigo_observado`.
  - `test_v2_normaliza_espaco_apos_hifen`: `"N- (1N2)"` → `"N-(1N2)"`.
  - `test_v2_rejeitada_fica_fora`.
  - `test_v2_estai_entra_pelo_suporte_do_poste`, `test_v2_estai_com_suporte_fora_da_ficha_nao_entra_no_vizinho` e `test_v2_estai_com_suporte_invalido_nao_entra`.
  - `test_v1_continua_igual`: mesma entrada com `versao="propostas-v1"` dá o resultado da v1 (estruturas com código nu).

- [ ] **Step 2: Rode e veja falhar.** `.venv/Scripts/python.exe -m pytest tests/unit/test_ficha_predita_propostas_v2.py` → FAIL.

- [ ] **Step 3: Implemente** com funções privadas `_estrutura_v2` e `_codigo_cabo_v2`, sem alterar as funções da v1. Como `_anexar_estruturas` e `_vao` leem `codigo_observado` direto, na v2 pós-processe a lista gerada pela v1 (estruturas e `cabo` de cada vão), para a Task 4 só trocar a montagem dos vãos. Atualize as listas de fontes nos dois documentos e os docstrings dos três scripts. O helper de propostas sintéticas do arquivo de teste sempre fornece `variante["extraction"]`, ainda que vazio, para a Task 4 não quebrar os testes da 3.

- [ ] **Step 4: Rode e veja passar.** Mesmo comando → PASS.

- [ ] **Step 5: Commit** com a suíte da área verde; rode a suíte inteira uma vez antes do relatório.

---

### Task 4: Vão composto da `propostas-v2`

**Estimativa:** 35 min · **Depende de:** 3 (mesmos arquivos) · **Risco:** alto

**Files:**
- Modify: `scripts/ficha_predita_propostas.py`
- Test: `tests/unit/test_ficha_predita_propostas_v2.py`

**Interfaces:** Consumes: `ficha_predita_propostas(..., versao=...)` da Task 3; `variante["extraction"].evidencias`, que `run_variant` já devolve.

Regra da v2 (só nela): cabos da mesma `situacao_projeto` ligados ao mesmo par de postes da ficha (chave sem ordem) viram um vão só. `cabo` é a união, por `" / "`, dos códigos distintos e não vazios, normalizados como na Task 3, ordenados pela caixa da evidência de `evidencia_rotulo_id` do cabo: menor y, depois menor x, depois o próprio código. Cabo sem essa evidência vem depois dos que têm, por código. `comprimento_m` e origem vêm do primeiro cabo dessa ordem com comprimento de origem `ANOTACAO_DESENHO`; se nenhum tiver, do primeiro com comprimento; `pendentes` é a união. Cabo com menos de 2 postes distintos fica como na v1 (`cabos_sem_vao`). Situações diferentes no mesmo par continuam em vãos separados.

- [ ] **Step 1: Testes falhando:**
  - `test_v2_une_cabos_do_mesmo_par_em_vao_composto_de_cima_para_baixo`: dois cabos com a **mesma polilinha** e rótulos em y diferentes → 1 vão, `"A / B"`, com A de y menor, seja qual for a ordem dos ids.
  - `test_v2_desempata_rotulos_na_mesma_linha_por_x` e `test_v2_cabo_sem_rotulo_vem_depois`.
  - `test_v2_cabo_repetido_no_mesmo_par_nao_duplica` e `test_v2_codigo_ausente_nao_entra_na_uniao`.
  - `test_v2_cabo_com_extremo_unico_nao_vira_vao`.
  - `test_v2_situacoes_diferentes_no_mesmo_par_nao_se_fundem`.
  - `test_v2_par_sem_ordem_funde_a_b_e_b_a`.
  - `test_v2_prefere_comprimento_anotado_no_vao_composto`.

- [ ] **Step 2: Rode e veja falhar.** Mesmo comando da Task 3 → FAIL.

- [ ] **Step 3: Implemente** em função privada `_vaos_v2`, sem alterar `_vaos` da v1.

- [ ] **Step 4: Rode e veja passar.** Mesmo comando → PASS.

- [ ] **Step 5: Commit** com a suíte da área verde; rode a suíte inteira uma vez antes do relatório.

---

## Operação do orquestrador (fora das tarefas)

Com as tarefas integradas, a partir do worktree da trilha A, **em série** (o baseline segura uma trava na rodada; o paralelismo fica em `--processos`):

1. Controle: `-m scripts.curation_ficha baseline --rodada <tmp>/20261103-2300-fichas --native-only --versao-extracao propostas-v1 --processos N` → compara `total` e `por_pdf` com a v004.
2. `propostas-v2` sem runner: `... --versao-extracao propostas-v2 --processos N`.
3. `propostas-v1` com runner: `... --versao-extracao propostas-v1 --simbolos-modelo --processos N`.
4. `propostas-v2` com runner: `... --versao-extracao propostas-v2 --simbolos-modelo --processos N`.

`N` segue o "Orçamento de máquina". A rodada grava em `tmp/` do checkout principal. O handoff mapeia cada `baseline-vNNN` para fonte, runner e commit, separa o ganho de formato do ganho de leitura, diz quantos compostos da referência a ordem de `_vaos_v2` acerta, se há dois vãos da referência no mesmo par, quantos pares foram separados por situação e registra que os 5 compostos de estrutura (`U3-U3(1)`) continuam errados na v2, por virem do tokenizador.

## Revisão de arquitetura

- Veredito: aprovado com notas.
- Rodadas: 1.
- Modelo: opus.
- Notas Menores (aplicadas neste plano): empate do golden com rótulo P3; repasse da flag também a `run_variant`; docstrings da fonte nova; pós-processamento da v1 na Task 3; comprimento anotado no vão composto; contagem de pares separados por situação; régua da E07.3 no roadmap.
- Divergência registrada para a E07.2: é provável que passe de ~3h e seja dividida no plano dela.
