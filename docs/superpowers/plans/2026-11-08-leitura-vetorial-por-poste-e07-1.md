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

- Golden frágil de outro jeito: ids dependem de uuid fixo e de relógio fixo; nada de `uuid4` no caso sintético.
- Runner falhando numa folha: a medição daquela folha registra o erro como o baseline já faz, sem derrubar as outras.
- Proposta `REJEITADA` não entra em nenhuma fonte; cabo com um extremo só não vira vão composto.
- Vão composto com códigos iguais: o mesmo cabo repetido no mesmo par não vira `X / X`.
- ESTAI cujo `suporte_proposta_id` aponta para fora da ficha: não vira símbolo do poste errado.

## File Structure

| Arquivo | Tarefa | Responsabilidade |
|---|---|---|
| `tests/integration/test_golden_padrao_e07.py` (novo) | 1 | golden da análise padrão |
| `tests/data/golden_padrao_e07.json` (novo) | 1 | saída congelada |
| `scripts/benchmark_network_pdf.py` | 2 | `run_variant` com runner opcional |
| `scripts/benchmark_ficha_poste.py` | 2, 3 | flag, `gerador`, seleção da fonte |
| `scripts/curation_ficha.py` | 2 | `--simbolos-modelo` no baseline |
| `docs/fluxo-curadoria-incremental-simbologia.md`, `examples/README.md` | 2 | documentação da flag |
| `tests/unit/test_benchmark_ficha_runner_e07.py` (novo) | 2 | flag e `gerador` |
| `scripts/ficha_predita_propostas.py` | 3 | fonte `propostas-v2` |
| `tests/unit/test_ficha_predita_propostas_v2.py` (novo) | 3 | fixtures da fonte nova |

Ondas: {1, 2} em paralelo (arquivos disjuntos), depois {3}, porque a 3 toca `benchmark_ficha_poste.py`, como a 2.

---

### Task 1: Golden da análise padrão

**Estimativa:** 30 min · **Depende de:** nenhuma · **Risco:** alto

**Files:**
- Create: `tests/integration/test_golden_padrao_e07.py`, `tests/data/golden_padrao_e07.json`

**Interfaces:** Produces: `tests/data/golden_padrao_e07.json`, que as E07.2 e E07.3 usam para provar D18. Consumes: `ExecutarPipelineInterpretacao`, `InterpretadorRegrasExplicitas`, `carregar_registro_regras_inicial`, a fixture e helpers de `tests/integration/test_interpretation_pipeline.py` como modelo.

- [ ] **Step 1: Caso sintético determinístico.** Em `test_golden_padrao_e07.py`, monte um projeto e uma execução de extração com ids `uuid5` de constantes e relógio fixo, seguindo `interpretation_context`/`_runner` de `test_interpretation_pipeline.py` e as evidências de `_request` de `test_rule_based_interpreter.py`: um poste com rótulo `P1`, coordenada e nomenclatura; estrutura MT com qualificador; estrutura BT; cabo com traço e comprimento; equipamento. Execute `executar(project.id, extraction_id)` sem `simbolos` nem `symbol_configuration_signature`.

- [ ] **Step 2: Serialização.** Função `_serializar(resultado) -> dict`: `execucao.id`, `execucao.metodo`, `execucao.versao_metodo`, `execucao.parametros` e, ordenados por id, `elementos` (id, categoria, estado_revisao, codigo_observado, evidencia_ids, atributos_sugeridos, geometria em caixa) e `relacoes` (id, tipo, origem, destino, estado). Valores não JSON viram `str`.

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
```

Rode: `.venv/Scripts/python.exe -m pytest tests/integration/test_golden_padrao_e07.py` → FAIL (arquivo ausente).

- [ ] **Step 4: Gere o golden uma vez**, no estado atual de `src/`, gravando `_serializar(...)` em `tests/data/golden_padrao_e07.json` com `json.dumps(..., ensure_ascii=False, indent=2, sort_keys=True)`. Confira a mão que o arquivo traz as 5 categorias e ao menos uma relação de cada tipo gerada.

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
  - `_gerador(..., simbolos_modelo: bool = False)`: quando `True`, acrescenta `"simbolos_modelo": {"perfil": "vector-only", "assinatura": <runner.signature>}`. `run_variant` devolve `"symbol_configuration_signature"` na variante quando ligada. O `opcoes` do resumo do baseline ganha `"simbolos_modelo": true` só com a flag.

- [ ] **Step 1: Testes falhando** em `tests/unit/test_benchmark_ficha_runner_e07.py`:
  - `test_gerador_sem_flag_nao_ganha_chave` (fake de `variante`): `"simbolos_modelo" not in _gerador(variante, native_only=True)`.
  - `test_gerador_com_flag_registra_perfil_e_assinatura`.
  - `test_cli_baseline_aceita_a_flag_e_propaga`: `main` do `curation_ficha` com `monkeypatch` em `baseline`, afirmando `simbolos_modelo=True`.
  - `test_opcoes_do_resumo_so_mudam_com_a_flag`: sem flag, `"simbolos_modelo" not in resumo["opcoes"]`.
  - `test_run_variant_com_simbolos_chama_runner` (`tests/integration` se precisar de PDF sintético): fixture sintética de `tests/integration/test_model_symbols_runner.py`, com `simbolos_modelo=True`; afirme que `variante["semantic"].execucao.parametros` contém `semantica_simbolos_versao` e que há proposta com `origem_simbolo_ocorrencia_id` ou `simbolo_classe`.

- [ ] **Step 2: Rode e veja falhar.** `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_ficha_runner_e07.py` → FAIL.

- [ ] **Step 3: Implemente** conforme as Interfaces. O import do `SymbolCompositionRunner` e de `ServerSettings` fica dentro do ramo `simbolos_modelo`, para o caminho sem flag não carregar o servidor. Falha do runner numa folha segue o tratamento existente da medição por PDF do baseline, sem caminho novo.

- [ ] **Step 4: Documente** em `docs/fluxo-curadoria-incremental-simbologia.md` (bloco de `--versao-extracao`, linha 807) e em `examples/README.md`: uma linha sobre `--simbolos-modelo` (runner ligado, perfil `vector-only`).

- [ ] **Step 5: Rode e veja passar.** Mesmo comando → PASS.

- [ ] **Step 6: Commit** com a suíte da área verde; rode a suíte inteira uma vez antes do relatório.

---

### Task 3: Fonte `propostas-v2` da ficha predita

**Estimativa:** 45 min · **Depende de:** 2 (mesmo arquivo) · **Risco:** alto

**Files:**
- Modify: `scripts/ficha_predita_propostas.py`, `scripts/benchmark_ficha_poste.py` (só `VERSOES_EXTRACAO`, a constante `VERSAO_EXTRACAO_PROPOSTAS_V2 = "propostas-v2"` e a seleção da fonte em `executar`)
- Test: `tests/unit/test_ficha_predita_propostas_v2.py`

**Interfaces:**
- Produces: `ficha_predita_propostas(variante, pdf_sha256, *, native_only: bool, versao: str = VERSAO_EXTRACAO_PROPOSTAS)`. Com `versao="propostas-v1"` a saída é idêntica à atual.

Regras da v2 (só nela):
1. **Estruturas:** usa `token_estrutura` dos atributos, com queda para `codigo_observado` quando ausente; lista ordenada.
2. **Código de cabo:** remove espaços depois de hífen (`N- (1N2)` → `N-(1N2)`); colapsa os demais.
3. **Vão composto:** cabos ligados ao mesmo par de postes da ficha viram um vão só: `cabo` = códigos distintos unidos por `" / "`, na ordem de cima para baixo da caixa do rótulo do cabo (menor y, depois menor x, da geometria da proposta); `comprimento_m` e origem do primeiro cabo nessa ordem com comprimento; `pendentes` é a união. Cabo com menos de 2 postes distintos fica como na v1 (`cabos_sem_vao`).
4. **ESTAI:** equipamento com `simbolo_classe == "ESTAI"` e sem relação `INSTALADO_EM` entra no poste de `suporte_proposta_id`, se esse id for de poste da ficha; senão conta `simbolos_de_poste_fora_da_ficha`, como hoje. Com relação, vale a relação.

- [ ] **Step 1: Testes falhando** em `tests/unit/test_ficha_predita_propostas_v2.py`, com propostas sintéticas no molde de `tests/unit/test_ficha_predita_propostas*.py`:
  - `test_v2_usa_token_com_qualificador`: `token_estrutura="U4(1)"` → `["U4(1)"]`; negativa sem token → `codigo_observado`.
  - `test_v2_normaliza_espaco_apos_hifen`: `"N- (1N2)"` → `"N-(1N2)"`.
  - `test_v2_une_cabos_do_mesmo_par_em_vao_composto_de_cima_para_baixo`: 2 cabos, mesmo par → 1 vão, `"A / B"`, com A de y menor.
  - `test_v2_cabo_repetido_no_mesmo_par_nao_duplica`: dois cabos de mesmo código → `cabo` sem repetição.
  - `test_v2_cabo_com_extremo_unico_nao_vira_vao` e `test_v2_rejeitada_fica_fora`.
  - `test_v2_estai_entra_pelo_suporte_do_poste` e `test_v2_estai_com_suporte_fora_da_ficha_nao_entra_no_vizinho`.
  - `test_v1_continua_igual`: mesma entrada com `versao="propostas-v1"` dá o resultado da v1 (estruturas com código nu, um vão por cabo).

- [ ] **Step 2: Rode e veja falhar.** `.venv/Scripts/python.exe -m pytest tests/unit/test_ficha_predita_propostas_v2.py` → FAIL.

- [ ] **Step 3: Implemente** com funções privadas `_estrutura_v2`, `_codigo_cabo_v2` e `_vaos_v2`, sem alterar as funções da v1. `gerador.versao_extracao` recebe a versão usada.

- [ ] **Step 4: Rode e veja passar.** Mesmo comando → PASS.

- [ ] **Step 5: Commit** com a suíte da área verde; rode a suíte inteira uma vez antes do relatório.

---

## Operação do orquestrador (fora das tarefas)

Com as tarefas integradas, a partir do worktree da trilha A, em paralelo:

1. Controle: `-m scripts.curation_ficha baseline --rodada <tmp>/20261103-2300-fichas --native-only --versao-extracao propostas-v1 --processos N` → compara `total` e `por_pdf` com a v004.
2. `propostas-v2` sem runner: `... --versao-extracao propostas-v2 --processos N`.
3. `propostas-v2` com runner: `... --versao-extracao propostas-v2 --simbolos-modelo --processos N`.

`N` segue o "Orçamento de máquina". Totais no handoff. A rodada grava em `tmp/` do checkout principal.
