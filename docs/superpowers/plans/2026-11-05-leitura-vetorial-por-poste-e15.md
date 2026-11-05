# E15 — Ficha predita a partir das propostas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dar à ficha predita do benchmark por poste uma segunda fonte, `propostas-v1`, que lê as propostas da interpretação (postes, estruturas, equipamentos e cabos propostos) em vez do projeto promovido, mantendo `projeto-promovido-v1` selecionável e o baseline nas 16 folhas rodando em processos paralelos, com acerto afirmado e acerto pendente separados.

**Architecture:** só `scripts/` muda. Um módulo novo, `scripts/ficha_predita_propostas.py`, monta a ficha `predicao` (formato v1, sem mudança) a partir de `variante["semantic"]` (`elementos`/`relacoes`). `scripts/benchmark_ficha_poste.py` escolhe o gerador por `versao_extracao`. `scripts/curation_ficha.py baseline` repassa a versão, ganha `--processos N` com saída igual à serial e grava a separação afirmado × pendente numa chave aditiva do resumo.

**Tech Stack:** Python 3.11, pytest (+xdist), `concurrent.futures.ProcessPoolExecutor`.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E15 — Ficha predita a partir das propostas"; `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md`, seção "E14, E15 e E16 em resumo"; handoffs da E02 (R2, formato v1, R4) e da E03 (baseline, "pontos de ligação do cliente não são poste").

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o cliente não importa nada do servidor; DTOs seguem `tests/contracts/test_architecture.py`.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`. A ficha do poste não é entidade persistida nova, e nenhuma migração SQLite é feita.
- Mudança de comportamento de saída incrementa a versão do extrator ou do interpretador (ADR 0006). Esta etapa não muda o analisador: a versão nova é só do gerador da ficha (`versao_extracao`).
- PDFs reais, recortes, rótulos, conjuntos de dados e pesos nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos.
- Documentação enxuta: nada de histórico de execução em arquivo versionado; atualize só o que a mudança torna falso.
- Sem dependência nova.
- Fora de escopo: mudar o analisador ou a promoção; mudar o formato v1 da ficha (`docs/schemas/ficha-poste.schema.json`), o avaliador (`scripts/ficha_poste_avaliador.py`) ou o casamento 0,02/0,05 (D2); associação geométrica ao poste (E07).
- Não tocar em `src/`, `tests/conftest.py`, `scripts/benchmark_network_pdf.py`, `scripts/ficha_poste.py` nem `scripts/ficha_poste_avaliador.py` (consumidos sem edição).
- Nenhuma leitura de `examples/avaliacao-cega/`.
- Suíte inteira: `-n` informado em cada despacho (orçamento de máquina: 20 ÷ suítes simultâneas da sessão, mínimo 2).

## Decisões de desenho (rulings do planejador)

- **R-E15-1, default da CLI:** o default de `--versao-extracao` continua `projeto-promovido-v1`. Assim, todo comando e teste existente reproduz a saída anterior, e quem quer a fonte nova pede `propostas-v1` explicitamente. A E07 passa o flag. Custo se errado: um flag a mais nos comandos da E07.
- **R-E15-2, o que é proposta "presente":** `estado_revisao` em `PROPOSTA`, `CONFIRMADA` ou `CONFLITANTE`. `REJEITADA` nunca entra, nem como elemento nem como relação. `variante["semantic"]` é o resultado **depois** da promoção automática (`interpretation_pipeline.py:210-215`). Uma proposta promovida chega `CONFIRMADA`, então "pendente por `CONFLITANTE`" só pega o que a promoção não confirmou.
- **R-E15-3, afirmado × pendente (risco "propostas pendentes infladas"):** um campo é **pendente** quando a proposta que o fornece está `CONFLITANTE` ou tem verdadeira alguma das chaves de pendência da promoção. As chaves são as de `automatic_promotion.py:186-199`, copiadas como constante `CHAVES_PENDENCIA` no módulo novo, com comentário que aponta a origem e um teste que as extrai do fonte. Campo pendente entra com o valor e com o nome em `pendentes` do poste (ou do vão). O avaliador (`ficha_poste_avaliador.py:172-178`) soma o acerto sem olhar a pendência. Por isso, a separação é calculada no baseline (Task 2), a partir de `avaliacao.json["pares"]` (raiz do relatório, `ficha_poste_avaliador.py:411-421`) e dos `pendentes` de `ficha-predita.json`, para os 4 campos do poste. Vãos e símbolos ficam sem separação, e o `.md` declara isso.
- **R-E15-4, ligações só por relação proposta:**
  - estrutura → poste por `INSTALADA_EM`;
  - equipamento → poste por `INSTALADO_EM`;
  - cabo → postes por `CONECTA`, **só as que vão a poste da ficha**, porque a regra `cabo-conectado-a-equipamento` também emite `CONECTA` (`regras_interpretacao_v1.json:95-103`).

  Não há casamento geométrico: associação é a E07. Quando falta a relação, o FN aparece no baseline, e essa é a medida honesta da leitura atual.
- **R-E15-5, ponto de entrega não é poste:** proposta `POSTE` com `atributos_sugeridos["tipo_ponto_rede"] == "ENTREGA"` fica fora da ficha, como na promoção (`automatic_promotion.py:66-71`) e pela decisão do usuário na E03. Conta em `atributos_extras.postes_entrega`, chave presente só quando > 0.
- **R-E15-6, leitura dos atributos** (as chaves da promoção, lidas no script, sem importar privados de `src/`):
  - identificador: `atributos_sugeridos["identificador_operacional"]`, com `strip()`, e vazio vira `None`;
  - poste: `codigo_observado`, exceto no poste de símbolo (`origem_simbolo_ocorrencia_id` presente), que vira `None` com `atributos_extras.origem="simbolo"`, como em `benchmark_ficha_poste._poste`;
  - coordenada: `coordenada_leste`/`coordenada_norte`, só com as duas presentes, senão `None`. A `zona` é sempre `None`: a interpretação não emite zona (grep de `coordenada_zona` vazio em `src/`);
  - comprimento do vão:
    - com `comprimento_m` > 0 no cabo, vale ele (`origem_comprimento="ANOTACAO_DESENHO"`);
    - senão, a distância entre as coordenadas dos dois postes, calculada em `Decimal(str(...))` e `quantize(Decimal("0.01"))`, como em `_cable_length` (`automatic_promotion.py:503-521`), com `"COORDENADAS"`. Se um dos postes é pendente, `comprimento_m` vai para `pendentes` do vão;
    - sem nenhum dos dois, `None`;
  - cabo: `codigo_observado` do cabo;
  - símbolo: `atributos_sugeridos["simbolo_classe"]` do equipamento, validado com `_erro_classe("simbolo", classe)`, com as mesmas contagens de `_anexar_simbolos`.
- **R-E15-7, formato do resumo:** `opcoes.versao_extracao` é chave aditiva e `ESQUEMA_BASELINE` continua `curadoria-ficha-baseline-v1` (o leitor do resumo é humano e a chave nova não muda a semântica das antigas). `processos` aparece só no `.md` ("Processos: N"), para o JSON serial e o paralelo serem iguais. A chave nova `pendencia` também é aditiva.
- **R-E15-8, numeração do baseline:** o fechamento roda primeiro `propostas-v1` e depois `projeto-promovido-v1`. Os nomes efetivos (`baseline-vNNN`) vão para o handoff; o design previa `baseline-v004` para a fonte nova.
- **Símbolos 0 por construção nas duas fontes:** `run_variant` não passa `simbolos` (`benchmark_network_pdf.py:263-266`), e `simbolo_classe` só nasce em `_symbol_proposals` (`interpretation_pipeline.py:867`), com `symbol_composition` desligado por padrão. O handoff declara isso, para a E06 e a E07 não lerem 0 de símbolos como medida da leitura.

## Reservas de arquivos (regra de arquivos disjuntos com a E06)

- **Editados pela E15:** `scripts/benchmark_ficha_poste.py`, `scripts/curation_ficha.py`, `scripts/ficha_predita_propostas.py` (novo), `tests/unit/test_ficha_predita_propostas.py` (novo), `tests/unit/test_curation_ficha_baseline_processos.py` (novo) e `examples/README.md` (uma linha).
- **Consumidos sem edição** (a E06 também não deve mudar o contrato deles): `scripts/benchmark_network_pdf.py` (`run_variant`), `scripts/ficha_poste.py`, `scripts/ficha_poste_avaliador.py`. Se a E06 precisar mudar `run_variant`, o conflito é semântico e decide-se antes da revisão do plano dela.

## Review Focus

1. Proposta `REJEITADA` (elemento ou relação) não pode produzir poste, estrutura, símbolo nem vão → testes negativos na Task 1.
2. Ponto de entrega proposto como `POSTE` não pode virar poste nem extremidade de vão → teste na Task 1.
3. Cabo ligado a 2 postes e a um equipamento vira 1 vão; cabo com 1 poste só, ou com 2 `CONECTA` ao mesmo poste, não vira vão → teste parametrizado na Task 1.
4. A ficha da fonte nova passa em `validar_ficha` (ids únicos, `pendentes` sem repetição, enums do schema) mesmo com proposta duplicada → teste na Task 1.
5. `--processos N` com falha num PDF, ou com o pool quebrado, produz um resumo gravado, com `falha` saneada e sem caminho absoluto → testes na Task 2.

---

## File Structure

| Arquivo | Ação | Responsabilidade |
|---|---|---|
| `scripts/benchmark_ficha_poste.py` | modificar | constantes `VERSAO_EXTRACAO`, `VERSAO_EXTRACAO_PROPOSTAS` e `VERSOES_EXTRACAO`; `_gerador` com a versão recebida; parâmetro `versao_extracao` em `executar`; flag `--versao-extracao`; docstring do topo com as duas fontes |
| `scripts/ficha_predita_propostas.py` | criar | `ficha_predita_propostas(variante, pdf_sha256, *, native_only) -> dict`; `CHAVES_PENDENCIA` |
| `scripts/curation_ficha.py` | modificar | `baseline(..., versao_extracao=..., processos=1, _executor=...)`, flags `--versao-extracao` e `--processos`, `opcoes.versao_extracao`, chave `pendencia`, linhas no `.md` |
| `examples/README.md` | modificar | uma frase: `--versao-extracao propostas-v1` seleciona a fonte nova |
| `tests/unit/test_ficha_predita_propostas.py` | criar | fixtures sintéticas positiva e negativa da fonte nova, validade, constantes e CLI |
| `tests/unit/test_curation_ficha_baseline_processos.py` | criar | repasse da versão, igualdade serial × `--processos 4`, falhas, separação de pendência |

Os testes existentes de `benchmark_ficha_poste` e `curation_ficha` não são editados: continuam passando com o default (R-E15-1), e é essa a prova de que a fonte anterior não mudou.

## Tarefas e ondas

| Task | Estimativa | Depende de | Risco | Laboratório |
|---|---|---|---|---|
| 1 — gerador `propostas-v1` | 45 min | nenhuma | alto (núcleo da etapa) | não |
| 2 — baseline com versão, processos e pendência | 45 min | Task 1 (`VERSOES_EXTRACAO`, `executar(..., versao_extracao)`) | alto (concorrência) | não |

Em série: onda 1 = Task 1, onda 2 = Task 2. Soma: ~1h30 de tarefas, mais revisão e fechamento operacional, dentro do teto de ~3h.

---

### Task 1: gerador `propostas-v1`

**Files:**
- Create: `scripts/ficha_predita_propostas.py`
- Modify: `scripts/benchmark_ficha_poste.py` (docstring, constante da linha 37, `_gerador`, `executar`, `main`), `examples/README.md` (parágrafo do benchmark por poste)
- Test: `tests/unit/test_ficha_predita_propostas.py`

**Interfaces:**
- Consumes:
  - `variante` de `scripts.benchmark_network_pdf.run_variant`: `variante["semantic"].elementos` (`PropostaElemento`), `variante["semantic"].relacoes` (`PropostaRelacao`, `interpretation_pipeline.py:64`), `variante["project"].documentos[*].paginas` (número da página por `pagina_id`), `analyzer`, `interpreter_version` e `registry_signature`;
  - `scripts.ficha_poste._erro_classe` e `validar_ficha`.
- Produces (todos em `scripts/benchmark_ficha_poste.py`, salvo o gerador):
  - `VERSAO_EXTRACAO: Final = "projeto-promovido-v1"` (inalterada);
  - `VERSAO_EXTRACAO_PROPOSTAS: Final = "propostas-v1"`;
  - `VERSOES_EXTRACAO: Final = (VERSAO_EXTRACAO, VERSAO_EXTRACAO_PROPOSTAS)`;
  - `_gerador(variante, *, native_only, versao_extracao=VERSAO_EXTRACAO)`;
  - `executar(pdf, referencia, saida, *, native_only, runtime_directory, versao_extracao: str = VERSAO_EXTRACAO) -> dict[str, Any]`, que levanta `ValueError("versao_extracao desconhecida: …")` antes de rodar o analisador;
  - em `scripts/ficha_predita_propostas.py`: `ficha_predita_propostas(variante: Mapping[str, Any], pdf_sha256: str, *, native_only: bool) -> dict[str, Any]` e `CHAVES_PENDENCIA: Final[tuple[str, ...]]`.
- **Imports, sem ciclo:** o módulo novo importa `_bbox`, `_json`, `_gerador` e `VERSAO_EXTRACAO_PROPOSTAS` de `scripts.benchmark_ficha_poste` no topo. `benchmark_ficha_poste.executar` importa `ficha_predita_propostas` **dentro da função**. Nenhum terceiro módulo.

Regras de montagem (R-E15-2 a R-E15-6):
- poste: um por proposta `POSTE` presente com `geometria` e que não é entrega, com `id = str(proposta.id)`, `pagina` pelo `pagina_id` da geometria e `bbox` por `_bbox`;
- estruturas: `codigo_observado` das propostas `ESTRUTURA_MT/BT` presentes que têm relação `INSTALADA_EM` presente para um poste da ficha, ordenadas. Estrutura sem `codigo_observado` é ignorada; sem poste da ficha, conta em `atributos_extras.estruturas_sem_poste` (chave só quando > 0);
- símbolos: `EQUIPAMENTO` presente com `INSTALADO_EM` presente para um poste da ficha, com as mesmas contagens e regras de `_anexar_simbolos`;
- vãos: um por `CABO` presente cujas relações `CONECTA` presentes **com destino em poste da ficha** apontam para exatamente 2 postes distintos. `de`/`para` seguem a ordem dos ids das relações, ordenados. Os outros cabos contam em `atributos_extras.cabos_sem_vao` (chave só quando > 0);
- pendência:
  - o campo vai para `pendentes` quando a proposta que o fornece é pendente (R-E15-3);
  - poste pendente marca `identificador`, `poste` e `coordenada`; estrutura pendente marca `estruturas` do poste; equipamento pendente marca `simbolos` do poste;
  - cabo pendente marca `comprimento_m` e `cabo` do vão; comprimento por coordenada de poste pendente marca `comprimento_m`;
  - em todos os casos, sem repetição e em ordem.

- [ ] **Step 1: Write the failing tests** em `tests/unit/test_ficha_predita_propostas.py`. Monte a `variante` sintética como os testes de `test_benchmark_ficha_poste.py` fazem (objetos de domínio reais, `SHA_QUALQUER`), com um projeto promovido **vazio**, para provar que a fonte é a proposta:
  - `test_propostas_presentes_viram_ficha`: 2 postes `PROPOSTA` ("P1"/"P2", com coordenadas), 1 `ESTRUTURA_MT` "N3" `INSTALADA_EM` P1, 1 equipamento com `simbolo_classe` do inventário `INSTALADO_EM` P2 e bbox de área > 0, e 1 cabo com 2 `CONECTA` e `comprimento_m=35`. Asserções: 2 postes; `estruturas == ["N3"]` em P1; 1 símbolo em P2; 1 vão com `comprimento_m == 35.0` e `atributos_extras.origem_comprimento == "ANOTACAO_DESENHO"`; `gerador.versao_extracao == "propostas-v1"`; `validar_ficha(ficha) == []`.
  - `test_proposta_rejeitada_nao_vira_campo`, parametrizado com ids determinísticos: poste `REJEITADA`; relação `INSTALADA_EM` `REJEITADA`; equipamento `REJEITADA`; cabo `REJEITADA`; uma das 2 `CONECTA` `REJEITADA`. Cada caso afirma a ausência do campo correspondente.
  - `test_proposta_ausente_nao_vira_campo`: semântica sem estrutura nem cabo → `estruturas == []` e `vaos == []`.
  - `test_ponto_de_entrega_nao_vira_poste`: poste com `tipo_ponto_rede="ENTREGA"` e um cabo `CONECTA` P1 + entrega → 1 poste, `vaos == []`, `atributos_extras["postes_entrega"] == 1` e `atributos_extras["cabos_sem_vao"] == 1`.
  - `test_proposta_pendente_vai_para_pendentes`, parametrizado sobre `CONFLITANTE` e sobre `comprimento_pendente=True`, no poste, na estrutura e no cabo. Afirma o valor presente e o nome do campo em `pendentes`.
  - `test_vao_so_conta_conecta_a_poste`, parametrizado:
    - 2 postes + 1 equipamento → 1 vão;
    - 1 poste só → `vaos == []` e `cabos_sem_vao == 1`;
    - 2 `CONECTA` ao mesmo poste → `vaos == []` e `cabos_sem_vao == 1`.
  - `test_estrutura_sem_poste_da_ficha_e_contada`: `atributos_extras["estruturas_sem_poste"] == 1`.
  - `test_comprimento_por_coordenadas`: cabo sem `comprimento_m`, postes em (0, 0) e (3, 4) → `5.0` e `"COORDENADAS"`. Com P2 `CONFLITANTE`, `"comprimento_m" in vao["pendentes"]`.
  - `test_chaves_de_pendencia_iguais_as_da_promocao`: lê `automatic_promotion.py` como texto, por caminho derivado de `Path(__file__)` (raiz do repositório = `Path(__file__).resolve().parents[2]`), nunca do cwd, extrai a tupla `pending_keys = (...)` com `ast` (sem importar privado) e afirma igualdade com `CHAVES_PENDENCIA`.
  - `test_metricas_nas_duas_fontes`: referência sintética de 2 postes e 1 vão (reuse `_referencia_sintetica` de `tests/unit/test_benchmark_ficha_poste.py`) e `variante` com projeto promovido vazio e propostas com os 2 postes. `avaliar(ref, ficha_predita(...))` dá postes `tp == 0`; `avaliar(ref, ficha_predita_propostas(...))` dá `tp == 2` e `fp == 0`.
  - `test_executar_recusa_versao_desconhecida`: `ValueError` antes do analisador, com `run_variant` trocado por função que falha se chamada.
  - `test_cli_aceita_versao_extracao`: `main([... "--versao-extracao", "propostas-v1"])` com `run_variant` sintético via `monkeypatch`; o `ficha-predita.json` gravado traz `"propostas-v1"`.
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_ficha_predita_propostas.py -q` → FAIL (`ModuleNotFoundError: scripts.ficha_predita_propostas`).
- [ ] **Step 3:** implemente `scripts/ficha_predita_propostas.py` e o repasse em `benchmark_ficha_poste.py`, sem mudar a saída de `ficha_predita`. Acrescente à docstring do topo e a `examples/README.md` uma frase sobre `--versao-extracao propostas-v1`.
- [ ] **Step 4:** `.venv/Scripts/python.exe -m pytest tests/unit/test_ficha_predita_propostas.py tests/unit/test_benchmark_ficha_poste.py tests/unit/test_benchmark_ficha_poste_adversarial.py tests/unit/test_benchmark_ficha_poste_final_fix.py -q` → todos PASS; `ruff check`, `ruff format --check` e `mypy` limpos.
- [ ] **Step 5: Commit** (`feat: ficha predita a partir das propostas (propostas-v1)`).

### Task 2: baseline com versão de extração, processos e pendência

**Files:**
- Modify: `scripts/curation_ficha.py` (docstring do topo, `_medir_pdf`, `baseline`, `_markdown_baseline`, parser `baseline`, despacho do `main`)
- Test: `tests/unit/test_curation_ficha_baseline_processos.py`

**Interfaces:**
- Consumes: `scripts.benchmark_ficha_poste.VERSOES_EXTRACAO`, `VERSAO_EXTRACAO` e `executar(..., versao_extracao=...)` (Task 1).
- Produces:
  - `baseline(rodada_dir, pdf_ids=(), *, native_only=False, runtime_directory=RUNTIME_PADRAO, parcial=False, versao_extracao: str = VERSAO_EXTRACAO, processos: int = 1, _executor: Callable[..., Registro] | None = None) -> Registro`. `_executor` é parâmetro privado para teste e tem de ser função de nível de módulo, picklável, porque o spawn do Windows reimporta o módulo e não enxerga `monkeypatch`. Com `None`, o executor é resolvido **na chamada** pelo global `executar_benchmark` do módulo, no processo principal e no filho (`_medir_pdf_no_pool`). Assim, os testes existentes que fazem `monkeypatch.setattr(curation_ficha, "executar_benchmark", …)` continuam valendo no caminho serial;
  - resumo com `opcoes = {"native_only", "pdfs", "versao_extracao"}`, mais a chave aditiva `pendencia = {"por_pdf": {pdf_id: bloco}, "total": bloco}`, em que `bloco = {campo: {"acertos_afirmados": int, "acertos_com_pendencia": int}}` para os 4 campos de `CAMPOS_DO_POSTE`. A conta usa `avaliacao["pares"][*]`: `["predicao"]` é o id do poste predito e `["campos"][campo]` vale `True` para acerto, `False` para erro e `None` para pendente na referência, que fica fora. O id do predito é cruzado com o `pendentes` do poste de mesmo id em `ficha-predita.json`, na pasta do PDF. Ficam fora da `pendencia`, sem erro: PDF em falha ou sem referência, PDF sem `ficha-predita.json` (os executores falsos dos testes existentes não o gravam) e par sem `campos` ou sem `predicao`;
  - `.md`: abaixo do título, "Versão de extração: <versao>" e "Processos: <pedido> (efetivos: <efetivo>)", em que o efetivo é `min(pedido, PDFs com referência, 61)` e vale 1 no caminho serial; no fim, a seção "## Acertos afirmados e com pendência (total)" com uma linha por campo e a frase "Vãos e símbolos: sem separação de pendência.";
  - CLI `baseline`:
    - `--versao-extracao`, com choices = `VERSOES_EXTRACAO` e default `VERSAO_EXTRACAO`;
    - `--processos N`: inteiro ≥ 1, e `0` ou negativo dá erro do argparse (exit 2). O valor efetivo é `min(N, PDFs com referência, 61)`, porque `ProcessPoolExecutor` recusa mais de 61 no Windows (minor da E14).

Paralelismo:
- Com `processos > 1` e mais de 1 PDF com referência, uma função de módulo `_medir_pdf_no_pool(argumentos)` chama `_medir_pdf` num `ProcessPoolExecutor`, com `pool.map` na ordem de `selecionados`.
- Cada PDF grava só na própria pasta `saidas[pdf_id]`. O resumo, a trava e a escrita atômica ficam no processo principal.
- `BrokenProcessPool` (crash nativo num worker) não aborta o comando: os PDFs sem resultado viram `{"situacao": "falha", "erro": "processo de medição interrompido"}`, e o resumo é gravado mesmo assim.
- O resultado é idêntico ao serial, porque `agregar_avaliacoes` recebe o mesmo dicionário na mesma ordem.

- [ ] **Step 1: Write the failing tests** em `tests/unit/test_curation_ficha_baseline_processos.py`. Monte a rodada sintética como `tests/unit/test_curation_ficha_baseline.py` faz, reusando os helpers dele por import, sem editá-lo, com 3 PDFs sintéticos. O executor falso é uma função de nível de módulo deste arquivo de teste, passada por `_executor`. Ela grava `ficha-predita.json` e devolve uma avaliação sintética que depende do `pdf_id`. O import do filho depende do `sys.path` herdado (modo prepend do pytest); se o spawn não achar o módulo de teste, ponha o executor falso num módulo auxiliar do mesmo diretório e registre no relatório.
  - `test_versao_extracao_e_repassada`: com `versao_extracao="propostas-v1"`, o executor recebe `versao_extracao="propostas-v1"`, e `resumo["opcoes"]["versao_extracao"] == "propostas-v1"`.
  - `test_processos_4_produz_o_mesmo_resumo_que_a_serial`: rodadas gêmeas em `tmp_path`, serial e `processos=4`. Os `-resumo.json`, carregados, são iguais, e os `avaliacao.json` por PDF são iguais byte a byte.
  - `test_processos_com_falha_num_pdf`: o executor levanta `RuntimeError` com o caminho absoluto do PDF num dos 3. As duas execuções dão o mesmo resumo, com `situacao == "falha"` e sem o caminho absoluto.
  - `test_pool_quebrado_grava_resumo_com_falha`: o executor falso chama `os._exit(1)` num PDF (só quando `processos > 1`). Afirma só que o resumo foi gravado e que esse PDF aparece com `situacao == "falha"`. Os outros PDFs podem cair juntos, porque a quebra do pool atinge os futures pendentes, e o teste não afirma nada sobre eles.
  - `test_pendencia_separa_afirmado_de_pendente`: o executor falso monta referência e predição sintéticas de 2 postes com o mesmo identificador, a 2ª predição com `"identificador"` em `pendentes`. Ele grava a `ficha-predita.json` e devolve o relatório de `scripts.ficha_poste_avaliador.avaliar()` **real**, e não um dicionário escrito à mão, para travar o formato verdadeiro. Afirma `resumo["pendencia"]["total"]["identificador"] == {"acertos_afirmados": 1, "acertos_com_pendencia": 1}`.
  - `test_pendencia_tolera_relatorio_sem_pares_completos`: executor falso no formato dos testes existentes (`pares` só com `distancia`, sem `ficha-predita.json`) → o comando sai 0, e `resumo["pendencia"]["total"]` tem os 4 campos zerados.
  - `test_processos_invalido_e_recusado`: `main(["baseline", "--rodada", …, "--processos", "0"])` → `SystemExit` com código 2.
  - `test_markdown_traz_versao_e_pendencia`: o `.md` contém `Versão de extração: propostas-v1`, `Processos: 4 (efetivos: 3)` e `Vãos e símbolos: sem separação de pendência.`
- [ ] **Step 2:** `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_ficha_baseline_processos.py -q` → FAIL (`TypeError: unexpected keyword argument 'versao_extracao'`).
- [ ] **Step 3:** implemente em `scripts/curation_ficha.py`.
- [ ] **Step 4:** `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_ficha_baseline_processos.py tests/unit/test_curation_ficha_baseline.py tests/unit/test_curation_ficha_baseline_ataque.py tests/unit/test_curation_ficha_baseline_sanear.py -q` → todos PASS; ruff, format e mypy limpos.
- [ ] **Step 5: Commit** (`feat: baseline da ficha com versao de extracao, processos e pendencia`).

---

## Fechamento operacional (orquestrador, depois das tarefas e antes da revisão final)

A rodada é `tmp/curadoria-simbologia/20261103-2300-fichas/` do **checkout principal**. Os PDFs ficam no `examples/` dele, só leitura. O Python é o `.venv` do **worktree B**, e o cwd é o checkout principal. O código vem do worktree: `"<worktree B>\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'<worktree B>'); import runpy; runpy.run_module('scripts.curation_ficha', run_name='__main__', alter_sys=True)" baseline …`. O editable do venv B já aponta `zeny_project_handler` para o `src/` do worktree B. Antes, confira com `__file__` que `scripts.curation_ficha` e `zeny_project_handler` vêm do worktree. Nos filhos, confira que `gerador.analisador_assinatura` é igual nos 16 PDFs e igual ao de uma execução serial de 1 PDF.

`--processos` = 20 ÷ suítes e benchmarks que a sessão roda ao mesmo tempo (contando a E06), arredondado para baixo, com mínimo de 2.

1. `baseline --rodada <rodada> --native-only --versao-extracao propostas-v1 --processos <n>`. Grava o baseline novo, com denominadores por PDF e no total.
2. `baseline --rodada <rodada> --native-only --versao-extracao projeto-promovido-v1 --processos <n>`. Total, `por_pdf` e bloco `gerador` (versões e assinaturas) têm de ser iguais aos da `baseline-v003`, por script, com a saída anexada. A prova forte do default inalterado é a suíte existente, que passa sem edição. Se o `gerador` diferir do da v003 (o analisador ou o interpretador mudou depois da E05), a diferença vai para o handoff, e a comparação de contagens passa a ser informativa.
3. Totais por campo e por família no handoff, com acertos afirmados e com pendência separados (chave `pendencia`). A família de cada PDF vem do relatório do modelo de desenho da E04 (`tmp/e04/`) ou da rodada de glifos da E05. O pico de memória por processo fica registrado.
4. `git grep -n "PROJETO DE REDE NS"` só acha as linhas que citam o critério.
5. `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`, sem outra suíte da sessão rodando.

Se a revisão final mexer no gerador, os passos 1–3 se repetem.

## Critérios de aceite → evidência

| Critério | Evidência |
|---|---|
| relatório traz a `versao_extracao` usada; a anterior reproduz a `baseline-v003` | `gerador.versao_extracao` em `ficha-predita.json` e `avaliacao.json`; `opcoes.versao_extracao` no resumo; passo 2 do fechamento; suíte existente sem edição |
| fixtures sintéticas produzem as métricas esperadas nas duas fontes | `test_metricas_nas_duas_fontes` e os demais testes da Task 1 |
| baseline novo em `tmp/` com denominadores; totais por campo e família no handoff | passos 1 e 3 do fechamento |
| nenhum nome de folha em arquivo versionado | passo 4 |
| `.bat` aprovado | passo 5 |

## Revisão de arquitetura

- **Veredito:** aprovado com notas.
- **Rodadas:** 2. A rodada 0 bloqueou com I1–I5 e M1–M12, a rodada 1 com N1–N2 e N3–N5, e a rodada 2 aprovou com notas.
- **Modelo:** opus (`revisor-arquitetura`).
- **Notas Menores:**
  - M-R3, o valor de "Processos" no `.md`: aplicado, com pedido e efetivo.
  - M12, sem ARCHITECTURE.md: a revisão julgou contra o `CLAUDE.md`, o roadmap, o design e os ADRs 0005, 0006 e 0009.
  - Não verificados pela revisão: o comportamento real do spawn e do `BrokenProcessPool` e o editable do venv B. O plano exige conferir por `__file__`.
