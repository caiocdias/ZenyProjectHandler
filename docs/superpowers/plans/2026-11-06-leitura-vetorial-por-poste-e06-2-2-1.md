# E06.2.2.1 — Método versionado no runner: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** expor o núcleo de gramáticas da E06.2.1 como método de símbolos versionado no `SymbolCompositionRunner` opt-in, com o agrupamento do modelo limitado e o resíduo raster marcado para a E12.

**Architecture:** um adaptador novo, `adapters/analysis/model_symbols.py`, abre a página com `pagina_para_gramaticas`, chama `casar_variantes` e devolve `ResultadoMetodoSimbolos`, como `declarative_symbols.observar_pacotes`. O runner o executa como 5º método, ao lado de `declarative-vector-packages`, e a reconciliação une os dois por índice cru (D12). O analisador padrão não muda.

**Tech Stack:** Python 3.11–3.13, PyMuPDF só nos adaptadores, pytest, mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.2.2" e "E06.2.2.1", mais o handoff da E06.2.1 na mesma página, `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` e `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md`.

## Global Constraints

- Sem mudança de saída no analisador padrão nem em `declarative_symbols.py`. O runner só muda com `symbol_composition` ligado (D12).
- Sem mudança em `VERSAO_MODELO_DESENHO`, no formato do cache, em `Estilo` ou nos tipos de `model.py`: a versão entra na capacidade do analisador padrão.
- Módulos de `drawing_model/` não importam `pymupdf` nem `declarative_symbols`. `model_symbols.py`, como adaptador, pode importar os dois.
- Domínio e aplicação não importam PyMuPDF. Mudança de API só por campos aditivos; esta etapa não muda API nem DTO.
- PDFs reais, recortes e rótulos nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa, autoral.
- Testes novos não dependem de ordem, cwd, porta ou arquivo fixo, nem de tempo de parede: custo se prova contando trabalho.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF.
- mypy strict, ruff check e ruff format; `scripts/complexity_gate.py src` falha em CC ≥ 31. `run` (D 25) e `_cache_complete` (D 29) do runner estão perto do teto.
- Código e nomes em português, como o resto de `drawing_model/`; o runner segue o inglês que já tem.
- Nenhuma etapa, fixture ou script lê `examples/avaliacao-cega/`.
- Documentação enxuta: nada de histórico de execução em arquivo versionado.

## Decisões do plano

- **R-E06.2.2.1-1, R-9 com teto, sem redesenhar a união:** a união exata em tempo quase linear pede varredura com árvore de segmentos, cara para um caso só de PDF hostil, e `_unir_proximos` precisa da mesma saída em toda folha legítima. Fica assim: não comparar quem já tem a mesma raiz, o que resolve caixas concêntricas; e um teto determinístico de visitas por página, com `AgrupamentoExcedido`, que `_fonte("grupos", ...)` já traduz em `modelo.grupos_falhou` e `grupos=()`. Essa fonte não bloqueia o núcleo (R-E06.2.1-8), porque ele não consome grupos. **Sem nova `VERSAO_MODELO_DESENHO`:** a saída só muda em página acima do teto, que hoje leva minutos, e nenhuma das 16 folhas chega nele (Task 1, medição). Custo se errado: uma folha real acima do teto perde os grupos, o que a E06.3 veria se H-A ou H-B os consumirem.
- **R-E06.2.2.1-2, 5º método ao lado de `declarative-vector-packages`:** já decidida na divisão da E06.2. O motor antigo sai na E09.
- **R-E06.2.2.1-3, tradução da falha de fonte:** o handoff da E06.2.1 pediu para decidir a falha determinística. `modelo.caminhos_falhou`, `modelo.primitivas_falhou` e `modelo.textos_nativos_falhou` viram `FALHA`, porque o motor antigo lê as mesmas fontes e abortaria igual. `modelo.textos_shx_falhou` e `modelo.glifos_falhou` são superfície nova: viram `FORA_DOMINIO` com motivo, para uma anotação estranha não impedir a composição do documento em toda nova tentativa. `FORA_DOMINIO` entra no cache integral, e por isso uma falha transitória de glifo fica até a assinatura mudar; é aceitável num método opt-in. `TetoGramaticasExcedido` vira `FORA_DOMINIO` com motivo (R-E06.2.1-3). Nos dois casos: nenhuma observação parcial.
- **R-E06.2.2.1-4, resíduo raster:** imagem compacta (`4 ≤ lado ≤ 72` pt, como `_unknown_frame`), de página ou de anotação, sobre a qual nenhum casamento do método tem centro, vira observação de classe `None`, `destino=review_only`, `gramatica=residuo_raster`, com o `sha256` da imagem nos atributos. Não afirma classe, e a E12 a consome. Mosaico não conta: dimensão em pixels repetida em mais de 8 imagens da página é ladrilho de ortofoto (H3). A E06.3 confirma a H2 com esse dado. Custo se errado: ruído de revisão no opt-in, que a Task 3 mede nas 16 folhas.
- **R-E06.2.2.1-5, rótulo em contorno real (I3):** se a fixture confirmar que o contorno de uma letra aciona `_marca_de_proposta`, a guarda ignora caminho preenchido contido numa palavra de texto `glifo` resolvida. Glifo não resolvido anula o texto (ADR 0016), então o contorno continua contando e a guarda continua fechada. Se a fixture não confirmar, a Task 2 fica só com os testes.
- **R-E06.2.2.1-6, adiado para a E09 (troca do padrão):** o desenho malformado ou com ponto não finito descartado sem diagnóstico (M3 da revisão da E06.2.1) e `tabela` obrigatória em `pagina_para_gramaticas`. O método desta etapa sempre passa a tabela. O descarte só importa em PDF hostil, e o método é opt-in até lá.

## Review Focus

1. Observação do método novo e do motor antigo sobre o mesmo desenho: a reconciliação une por índice cru em vez de duplicar, porque é isso que torna o 5º método seguro (Task 3, Task 4).
2. Página rotacionada ou com CropBox: `pontos_originais`, `pontos_normalizados` e a primitiva batem com o motor antigo nas gramáticas invariantes; a divergência de orientação de R-E06.2.1-7 continua explícita (Task 3).
3. Teto, falha de fonte e cache integral: `FORA_DOMINIO` é cacheado sem observação parcial, `FALHA` aborta e nunca entra no cache, e a nova tentativa reprocessa (Task 3, Task 4).
4. Assinatura: mudar pacote, tabela de glifos, limite, módulo do núcleo ou `VERSAO_MODELO_DESENHO` muda a assinatura do runner e invalida o cache integral (Task 4).
5. Página densa no agrupamento: o trabalho é limitado por visitas, `grupos_falhou` não derruba a página e a saída das folhas legítimas é igual à de hoje (Task 1).

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/.../drawing_model/groups.py` | não comparar mesma raiz; teto de visitas | 1 |
| `tests/unit/test_drawing_model_groups.py` | equivalência, teto e `grupos_falhou` | 1 |
| `tests/unit/test_drawing_model_geometry_grau_alto.py` | tirar o `xfail` de R-9 | 1 |
| `src/.../drawing_model/symbol_grammars.py` | `Palavra.de_glifo` | 2 |
| `src/.../drawing_model/grammar_frames.py` | guarda ignora o contorno da palavra de glifo | 2 |
| `tests/unit/test_grammar_frames_contorno_real.py` (novo) | rótulo em contorno real pelo adaptador | 2 |
| `src/.../model_symbols.py` (novo) | perfil, observação, tradução de erro, resíduo raster | 3 |
| `tests/unit/test_model_symbols.py` (novo) | método sobre o corpus, rotação, erros, resíduo | 3 |
| `src/zeny_project_handler_server/symbol_execution.py` | 5º método, tabela, digest e versão | 4 |
| `tests/integration/test_model_symbols_runner.py` (novo) | runner, reconciliação e cache | 4 |
| `tests/unit/test_e15_symbol_signatures.py`, `tests/server/test_e15_symbol_jobs.py`, `tests/integration/test_e15_symbol_cache.py`, `tests/integration/test_e16_symbol_context_runtime.py` | só onde contam 4 métodos | 4 |
| `tests/unit/test_grammar_frames_ataque.py`, `tests/unit/test_symbol_matcher_ataque.py` | resíduos herdados | 5 |

`src/...` é `src/zeny_project_handler/adapters/analysis`. Nenhuma outra etapa aberta: a regra de arquivos disjuntos não se aplica.

---

### Task 1: Agrupamento limitado (R-9)

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/groups.py`
- Modify: `tests/unit/test_drawing_model_groups.py`, `tests/unit/test_drawing_model_geometry_grau_alto.py`

**Interfaces:**
- Produces: `LIMITE_VISITAS_AGRUPAMENTO: Final = 2_000_000`; `class AgrupamentoExcedido(Exception)`; `agrupar_candidatos(primitivas, caminhos, *, folga=1.5, lado_maximo=40.0, limite_visitas=LIMITE_VISITAS_AGRUPAMENTO)`.

- [ ] **Step 1: Tirar o `xfail` de `test_agrupamento_escala_linearmente_com_caixas_sobrepostas`** e ver falhar.
- [ ] **Step 2: Escrever os testes**:
  - `test_saida_igual_a_uniao_anterior`: cópia local da união de hoje no teste; 200 sementes com caixas aleatórias, inclusive sobrepostas, e a partição de grupos igual;
  - `test_teto_de_visitas_levanta`: `limite_visitas=10` em página densa levanta `AgrupamentoExcedido`; `limite_visitas` exato passa e o exato menos 1 levanta;
  - `test_visita_nao_multiplica_em_caixas_distantes`: n e 2n caixas espalhadas, visitas no máximo 2,5 vezes;
  - `test_pagina_densa_vira_grupos_falhou`, pelo adaptador, com o teto trocado por monkeypatch: `modelo.grupos == ()`, `"modelo.grupos_falhou" in modelo.diagnosticos`, sem exceção, e `caminhos` e `primitivas` iguais.
- [ ] **Step 3: Implementar.** Em `_unir_proximos`, uma visita é cada entrada de célula lida, contada antes do `update`; `if raiz(j) == raiz(i): continue` antes de `_caixas_se_encostam`. Estourou, levanta `AgrupamentoExcedido`. CC < 31.
- [ ] **Step 4: Medir nas 16 folhas**, com script descartável fora do Git, lendo `examples/` do checkout principal (`C:\Users\Caio\Desktop\repos\ZenyProjectHandler\examples`), só leitura e sem `avaliacao-cega`, com processos em paralelo: visitas de cada folha. Cole no relatório o máximo por folha e confira que fica abaixo de 1/10 do limite; se não, reporte antes de seguir.
- [ ] **Step 5: Rodar** `.venv/Scripts/python.exe -m pytest tests/unit/test_drawing_model_groups.py tests/unit/test_drawing_model_geometry_grau_alto.py tests/unit/test_pagina_para_gramaticas.py`. Expected: PASS, sem `xfail` de R-9.
- [ ] **Step 6: Commit** (`fix: agrupamento do modelo sem comparacao repetida e com teto de visitas`).

### Task 2: Rótulo em contorno real (I3)

**Estimativa:** 35 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify (se o defeito se confirmar): `src/.../drawing_model/symbol_grammars.py`, `src/.../drawing_model/grammar_frames.py`
- Create: `tests/unit/test_grammar_frames_contorno_real.py`

**Interfaces:**
- Consumes: `pagina_para_gramaticas`, `casar_variantes`; `pdf_texto_contorno`, `LinhaTexto` e `tabela_do_alfabeto` de `tests/fixtures/glyphs/fonte_livre.py`.
- Produces (se confirmar): `Palavra.de_glifo: bool = False`, com default para não mudar as igualdades existentes.

- [ ] **Step 1: Escrever os testes**, sobre o PDF de `pdf_texto_contorno` com a moldura desenhada por cima, em `tmp_path`, com variante `label_in_frame` e `empty_interior` da gramática CT, lida do pacote real `family-f02-06`:
  - `test_rotulo_em_contorno_casa`: `CT` em contorno, com letra de área ≥ 6% da moldura;
  - `test_rotulo_em_contorno_nao_resolvido_nao_casa`: tabela sem a letra, sem texto e sem casamento;
  - `test_marca_preenchida_ao_lado_do_rotulo_recusa`: rótulo em contorno mais um retângulo preenchido real na moldura;
  - `test_rotulo_nativo_igual_ao_contorno`: mesma folha em `pdf_texto_nativo`, mesmas variantes.
- [ ] **Step 2: Rodar.** Se o primeiro passar sem mudança, registre no relatório que I3 não se confirmou, commit só dos testes, pule os passos 3 e 4.
- [ ] **Step 3: Implementar R-E06.2.2.1-5.** `_palavras_do_texto` preenche `de_glifo` para origem `glifo`; `_marca_de_proposta` pula caminho preenchido contido (`contem`) numa palavra `de_glifo` de `grade_palavras.consultar(limites)`, pago no orçamento.
- [ ] **Step 4: Rodar** `.venv/Scripts/python.exe -m pytest tests/unit/test_grammar_frames_contorno_real.py tests/unit/test_grammar_frames.py tests/unit/test_grammar_frames_ataque.py tests/unit/test_symbol_grammars_contexto.py tests/unit/test_symbol_matcher_paridade.py`. Expected: PASS.
- [ ] **Step 5: Commit** (`fix: contorno do rotulo em glifo nao aciona a guarda de marca`).

### Task 3: Método versionado

**Estimativa:** 45 min · **Depende de:** Task 2 · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/model_symbols.py`, `tests/unit/test_model_symbols.py`

**Interfaces:**
- Consumes: `declarative_symbols.Package`, `_enabled`, `_geometry`, `_validate_page_size`, `carregar_pacotes`; `pagina_para_gramaticas`; `casar_variantes`, `CasamentoGramatica`; `TetoGramaticasExcedido`, `FonteGramaticaFalhou`, `LIMITE_CONSULTAS_PAGINA`; `TabelaGlifos`, `carregar_tabela_glifos`; `VERSAO_MODELO_DESENHO`.
- Produces:
  - `perfil_pacotes_modelo(pacotes: tuple[Package, ...], tabela: TabelaGlifos, *, limite: int = LIMITE_CONSULTAS_PAGINA) -> PerfilMetodoSimbolos`: `metodo_id="declarative-drawing-model"`, `versao="1.0.0"`, `familia`, `classes_suportadas` e `camadas_suportadas` como `perfil_pacotes`, `perfil_referencia` igual ao do motor, `parametros` com `modelo_desenho`, `package_sha256`, `tabela_glifos_versao`, `tabela_glifos_sha256`, `limite_consultas`, `enabled_variants`.
  - `observar_pacotes_modelo(page: Any, *, documento_id: str, documento_sha256: str, pagina_numero: int, pacotes: tuple[Package, ...], tabela: TabelaGlifos, perfil: PerfilMetodoSimbolos | None = None, limite: int = LIMITE_CONSULTAS_PAGINA) -> ResultadoMetodoSimbolos`. `perfil` evita recalcular o sha a cada página.

- [ ] **Step 1: Escrever os testes**:
  - `test_paridade_de_observacao_com_o_motor_no_corpus`: em `build_enabled_corpus`, cada observação do método tem geometria, primitiva, `template` e atributos iguais aos de `observar_pacotes` na mesma página; só `metodo_assinatura` e o id diferem;
  - `test_geometria_com_rotacao_e_cropbox`: 90, 180, 270 e CropBox nas gramáticas invariantes: `pontos_originais` e `pontos_normalizados` batem com o motor a menos de 1e-3;
  - `test_divergencia_de_orientacao_continua_explicita`: triângulo a 180°;
  - `test_teto_vira_fora_de_dominio_sem_observacao` e `test_fonte_nova_vira_fora_de_dominio` (`textos_shx`, `glifos`, por monkeypatch em `pagina_para_gramaticas`), com motivo saneado, sem caminho nem nome de PDF;
  - `test_fonte_comum_vira_falha` (`caminhos`, `primitivas`, `textos_nativos`);
  - `test_sem_casamento_e_nao_deteccao` e `test_sem_variante_habilitada_e_fora_de_dominio`, como `_coverage_state`;
  - `test_perfil_muda_com_pacote_tabela_e_limite`;
  - `test_residuo_raster_marca_imagem_compacta` e os negativos: imagem grande; `> 8` imagens de mesma dimensão (mosaico); imagem com centro de um casamento sobre ela; imagem de anotação conta. A observação tem `classe=None`, `destino=review_only`, `gramatica=residuo_raster` e o `sha256`.
- [ ] **Step 2: Implementar.** A caixa do casamento vem no espaço visual; `pymupdf.Rect(caixa) * page.derotation_matrix` dá a caixa cru para `_geometry` (R-E06.2.1-7). A primitiva usa `indices_crus[c.caminho]` e `estilo.camada`. Os atributos são os de `_known_observation`. `perfil.assinatura()` é calculada uma vez por chamada. Uma só cobertura por página, como o motor: a tradução de R-E06.2.2.1-3 mantém isso. Exceção inesperada não é capturada: o runner é fail-closed.
- [ ] **Step 3: Medir o resíduo nas 16 folhas**, com script descartável, como na Task 1: resíduos por folha. Cole no relatório. Se passar de 20 numa folha, reporte antes de seguir: a regra do mosaico pode estar errada.
- [ ] **Step 4: Rodar** `.venv/Scripts/python.exe -m pytest tests/unit/test_model_symbols.py`. Expected: PASS.
- [ ] **Step 5: Commit** (`feat: metodo de pacotes sobre o modelo de desenho`).

### Task 4: Ligação no runner

**Estimativa:** 30 min · **Depende de:** Tasks 1 e 3 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler_server/symbol_execution.py`
- Create: `tests/integration/test_model_symbols_runner.py`
- Modify (só as contagens de métodos): `tests/unit/test_e15_symbol_signatures.py`, `tests/server/test_e15_symbol_jobs.py`, `tests/integration/test_e15_symbol_cache.py`, `tests/integration/test_e16_symbol_context_runtime.py`

**Interfaces:**
- Consumes: `model_symbols.perfil_pacotes_modelo`, `observar_pacotes_modelo`; `carregar_tabela_glifos`.
- Produces: `SymbolCompositionRunner(settings, *, templates=None, packages=None, calibration=None, glyph_table=None)`; `_VERSION = "e06-server-symbol-composition-2"`.

- [ ] **Step 1: Escrever os testes**:
  - `test_quinto_metodo_roda_e_entra_na_assinatura`: um PDF sintético do corpus, com `symbol_profile` sem raster, `run` conclui, e o journal traz `declarative-drawing-model` em cada página;
  - `test_mesmo_desenho_nao_duplica_na_reconciliacao`: o mesmo rótulo visto pelos dois métodos vira 1 ocorrência com os dois métodos;
  - `test_assinatura_muda_com_tabela_e_com_modulo_do_nucleo`: tabela diferente e digest de `symbol_matcher` diferente (monkeypatch em `_module_digest`);
  - `test_teto_no_metodo_novo_e_cacheado_e_nao_derruba_os_outros`: `limite` pequeno por monkeypatch: `run` conclui, a segunda execução dá `cache_hit`, e os outros métodos observam;
  - `test_falha_de_fonte_aborta_e_nao_entra_no_cache`: `modelo.caminhos_falhou` levanta `SymbolCompositionError`, sem cache;
  - `test_residuo_raster_atravessa_a_reconciliacao`: página com imagem compacta: `reconcile_symbols` não quebra, e o resíduo não vira classe afirmada.
- [ ] **Step 2: Implementar.** Perfil depois de `perfil_pacotes`, calculado uma vez; `_observe_page` emite depois de `observar_pacotes`, com `pagina_para_gramaticas` sobre a página aberta; no digest, `model_symbols`, `symbol_grammars`, `grammar_frames`, `grammar_disc`, `symbol_matcher`, `groups`, `geometry`, `glyph_text` e `pymupdf_drawing_model`. `run` e `_cache_complete` não ganham ramo: `_profiles` já dá a contagem. Assinatura do cache muda só para quem liga o opt-in.
- [ ] **Step 3: Ajustar as contagens de 4 para 5** nos testes existentes, sem mudar o que verificam.
- [ ] **Step 4: Rodar** `.venv/Scripts/python.exe -m pytest tests/integration/test_model_symbols_runner.py tests/unit/test_e15_symbol_signatures.py tests/server/test_e15_symbol_jobs.py tests/integration/test_e15_symbol_cache.py tests/integration/test_e16_symbol_context_runtime.py`, depois `.venv/Scripts/python.exe -m scripts.audit_symbol_packages`, mypy, ruff, format e `scripts/complexity_gate.py src`. Expected: PASS, `errors []`.
- [ ] **Step 5: Commit** (`feat: metodo sobre o modelo como quinto metodo do runner opt-in`).

### Task 5: Resíduos herdados da revisão final da E06.2.1

**Estimativa:** 15 min · **Depende de:** nenhuma · **Risco:** normal · **Laboratório:** não · **Soul:** `testador` (só testes)

**Files:**
- Modify: `tests/unit/test_grammar_frames_ataque.py`, `tests/unit/test_symbol_matcher_ataque.py`, `tests/unit/test_grammar_disc.py:499` (só o comentário)

- [ ] **Step 1: Corrigir `test_guarda_com_sobreimpressao_alem_da_folga_recusa_como_o_motor`:** nome e docstring dizem que recusa só porque o centro de `12` cai na moldura, e não provam ausência de resíduo.
- [ ] **Step 2: Acrescentar `test_residuo_aceito_guarda_sobreimpressao_alem_da_folga`**, parametrizado em (14, helv, -4) e (11, cour, -3): premissa `words`, `motor == set()` e `nucleo != set()`. Comentário citando R-4 e a instrução de inverter, não remover. Se a medida não abrir a guarda, reporte: o handoff da E06.2.1 precisa mudar.
- [ ] **Step 3: Acrescentar `test_residuo_aceito_rotulo_concatenado`:** `C`+`T` com lacuna entre o limite de `words` (~2 pt) e `t` (~3 pt): motor lê duas palavras e recusa, núcleo casa. Se `words` não separar nessa faixa, registre e deixe paridade.
- [ ] **Step 4: Corrigir o "~1,5" em `test_grammar_frames_ataque.py:868` e "só a interseção recusa" em `test_grammar_disc.py:499`.**
- [ ] **Step 5: Rodar** `.venv/Scripts/python.exe -m pytest tests/unit/test_grammar_frames_ataque.py tests/unit/test_symbol_matcher_ataque.py tests/unit/test_grammar_disc.py`. Expected: PASS.
- [ ] **Step 6: Commit** (`test: residuos herdados de R-4 e docstring corrigida`).

---

## Ondas

| Onda | Tarefas | Por que juntas |
|---|---|---|
| 1 | Tasks 1, 2 e 5 | sem dependência; arquivos disjuntos |
| 2 | Task 3 | depende da Task 2 |
| 3 | Task 4 | depende das Tasks 1 e 3 |

Soma das estimativas: 150 min.

## Fechamento operacional

| Critério de aceite | Evidência |
|---|---|
| Fixtures positivas e negativas do método e da ligação | Tasks 3 e 4 |
| Agrupamento de R-9 sem `xfail` | Task 1 |
| `scripts.audit_symbol_packages` → 0 erros | Task 4 |
| `IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` | o orquestrador roda `cmd.exe //c ".\\IniciarTestes.bat"` antes do `#concluida` e confere a data do relatório |

No handoff, para a E06.2.2.2: o nome e a assinatura do método; o custo por folha do journal; quantos resíduos raster por folha; a instrução de separar o gasto de orçamento entre colagem e gramáticas no diff.
