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

- **R-E06.2.2.1-1, R-9 com teto, sem redesenhar a união:** a união exata em tempo quase linear pede varredura com árvore de segmentos, cara para o que ela resolve. Fica assim: não comparar quem já tem a mesma raiz, o que resolve caixas concêntricas; e um teto determinístico de visitas por página, com `AgrupamentoExcedido`, que `_fonte("grupos", ...)` já traduz em `modelo.grupos_falhou` e `grupos=()`. **Sem nova `VERSAO_MODELO_DESENHO`, como exceção declarada ao invariante de versão:** `grupos` não chega a nenhuma saída versionada do job; `agrupar_candidatos` só roda em `_montar_pagina`, que o analisador padrão não usa; a nova versão mudaria `assinatura_capacidade` e invalidaria todo cache do padrão sem mudança de saída, o que a D12 descarta; `groups` entra no digest do runner; e `_tem_fonte_falha` não grava modelo com `grupos_falhou`. O teto não é só de PDF hostil: as 16 folhas chegam a 3.708.277 visitas (medido na Task 1), porque pular a mesma raiz evita a comparação, mas não a leitura da célula. Por isso o limite é 50.000.000, ~13 vezes o máximo medido, e 2n(n-1) visitas dão ~5.000 círculos sobrepostos no teto. Custo se errado: uma folha nova densa perde os grupos; quem consumir `grupos` (E06.3, H-A e H-B) adiciona `modelo.grupos_falhou` às fontes consumidas e sobe a versão. Descartadas: varredura exata (cara) e pular os grupos no método (quebra `test_modelo_igual_ao_de_extrair_modelo_desenho` e a E06.3).
- **R-E06.2.2.1-2, 5º método ao lado de `declarative-vector-packages`:** já decidida na divisão da E06.2. O motor antigo sai na E09.
- **R-E06.2.2.1-3, tradução da falha de fonte:** o handoff da E06.2.1 pediu para decidir a falha determinística. Só `modelo.caminhos_falhou` vira `FALHA`: é o `get_drawings` que o motor antigo também lê, então o documento já não comporia. As demais fontes (`primitivas`, `textos_nativos`, `textos_shx`, `glifos`) são código novo ou leitura diferente da do motor (RAWDICT e `get_texttrace` contra `words`), e um defeito determinístico nelas abortaria em toda nova tentativa um documento que hoje compõe: viram `FORA_DOMINIO`, com motivo `fonte_falhou:<codigo>`. Isso revê R-E06.2.1-8 só neste ponto, e a falha continua sem virar não detecção. `FORA_DOMINIO` entra no cache integral, e por isso uma falha transitória fica até a assinatura mudar; é aceitável num método opt-in. A matriz mostra `not_applicable` nesses casos, então a E06.2.2.2 os conta como falha, não como exclusão. `TetoGramaticasExcedido` vira `FORA_DOMINIO` com motivo `teto_consultas` (R-E06.2.1-3), e `modelo.glifos_limitados`, que levanta a mesma exceção, com motivo `glifos_limitados`. Como `FonteGramaticaFalhou` traz só o primeiro código, o método olha `modelo.diagnosticos` antes: `caminhos_falhou` presente é `FALHA`, mesmo com outra falha junto. Nunca há observação parcial. Descartadas: tudo `FALHA` (documento nunca compõe por anotação estranha) e tudo `FORA_DOMINIO` (esconde falha que o motor também teria).
- **R-E06.2.2.1-4, resíduo raster como dado, sem observação:** imagem compacta (`4 ≤ lado ≤ 72` pt, como `_unknown_frame`), de página ou de anotação, dentro da página, sobre a qual nenhum casamento do método tem centro, é um `ResiduoRaster`. Dimensão 0 (anotação sem pixels medidos) não conta como mosaico. Mosaico é mesma dimensão em pixels com **hashes distintos** em mais de 8 imagens da página (ladrilho de ortofoto, H3); o mesmo hash repetido é símbolo carimbado e continua resíduo, porque é o caso que refutaria a H2. Dedupe por `(sha256, caixa arredondada)`. **O que "marcado" significa nesta etapa:** `residuos_raster(...)`, pública e determinística, com os módulos dela no digest, é o contrato para a E06.3 e o ponto de partida para a E12, que define o que consome; quem precisa de caixa e hash a chama folha a folha sobre a página aberta, porque `SymbolReconciliation` não carrega coberturas e nada disso chega às propostas. A contagem em `motivo` é só um resumo, no journal e no cache integral. Formato fixo e testado, com os termos em ordem separados por `;`: `residuo_raster:<n>`, inclusive `residuo_raster:0`, que distingue "medido, zero" de "não medido", depois `imagens_falhou` se houver. Em `FORA_DOMINIO`, o `motivo` é `teto_consultas`, `glifos_limitados` (próprio, para não distorcer a leitura do orçamento), `fonte_falhou:<codigo>` ou o de "sem variante habilitada", **sem contagem**, e essa página não pode ser lida como "0 resíduos". Se a E06.3 refutar a H2, há símbolo raster real sem sinal na revisão até a E12, que depende da E09: antecipar a sinalização é decisão do usuário. **Não vira observação:** com classe `None`, cada resíduo viraria `PropostaElemento` `CONFLITANTE` na revisão humana (`interpretation_pipeline.py`), antes de a E12 existir, e fundiria com outros métodos na reconciliação. Reverter é barato. Falha de `modelo.imagens_falhou` ou `modelo.imagens_anotacao_falhou` mantém os casamentos e entra no `motivo` (`imagens_falhou`), para zero resíduo não ser lido como evidência a favor da H2. Custo se errado: a E12 ganha o caminho de observação depois.
- **R-E06.2.2.1-5, rótulo em contorno real (I3):** se a fixture confirmar que o contorno de uma letra aciona `_marca_de_proposta`, a guarda pula só o caminho **lido como glifo**, e não tudo o que cabe na caixa da palavra: a caixa é a do span (R-E06.2.1-4), e um triângulo preenchido dentro dela é o `negative_examples` da variante CT. `PaginaGramatica` ganha `glifos_lidos: frozenset[int]`, posições em `modelo.caminhos`, como `translucidos`, sem tocar em `model.py`. Glifo não resolvido anula o texto (ADR 0016) e não entra em `glifos_lidos`, então o contorno continua contando e a guarda continua fechada. Se a fixture não confirmar, fica só o teste do Step 1 da Task 2, e as Tasks 2 e 6 terminam ali.
- **R-E06.2.2.1-6, adiado para a E09 (troca do padrão):** o desenho malformado ou com ponto não finito descartado sem diagnóstico (M3 da revisão da E06.2.1) e `tabela` obrigatória em `pagina_para_gramaticas`. O método desta etapa sempre passa a tabela. O descarte só importa em PDF hostil, e o método é opt-in até lá.

## Review Focus

1. Observação do método novo e do motor antigo sobre o mesmo desenho: a reconciliação une por índice cru em vez de duplicar, com e sem OCG, porque é isso que torna o 5º método seguro (Task 3, Task 4).
2. Página rotacionada ou com CropBox: `pontos_originais`, `pontos_normalizados` e a primitiva batem com o motor antigo nas gramáticas invariantes; a divergência de orientação de R-E06.2.1-7 continua explícita (Task 3).
3. Teto, falha de fonte e cache integral: `FORA_DOMINIO` é cacheado sem observação parcial, `FALHA` aborta e nunca entra no cache, e a nova tentativa reprocessa (Task 3, Task 4).
4. Assinatura: mudar pacote, tabela de glifos, limite, módulo do núcleo ou da leitura, ou `VERSAO_MODELO_DESENHO`, muda a assinatura do runner e invalida o cache integral (Task 4).
5. Página densa no agrupamento: o trabalho é limitado por visitas, `grupos_falhou` não derruba a página e a saída das folhas legítimas é igual à de hoje (Task 1).

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/.../drawing_model/groups.py` | não comparar mesma raiz; teto de visitas | 1 |
| `tests/unit/test_drawing_model_groups.py` | equivalência, teto e `grupos_falhou` | 1 |
| `tests/unit/test_drawing_model_geometry_grau_alto.py` | tirar o `xfail` de R-9 | 1 |
| `src/.../drawing_model/glyph_text.py` | `LeituraGlifos.caminhos_lidos` | 2 |
| `src/.../drawing_model/symbol_grammars.py` | `PaginaGramatica.glifos_lidos`; docstring de R-3 | 2, 3 |
| `src/.../pymupdf_drawing_model.py` | `glifos_lidos` em `pagina_para_gramaticas` | 2 |
| `tests/unit/test_glyph_text.py`, `tests/unit/test_pagina_para_gramaticas.py` | caminhos lidos, por grupo e na página | 2 |
| `src/.../drawing_model/grammar_frames.py` | guarda pula o caminho lido como glifo | 6 |
| `tests/unit/test_grammar_frames_contorno_real.py` (novo) | rótulo em contorno real pelo adaptador | 2, 6 |
| `src/.../model_symbols.py` (novo) | perfil, observação, tradução de erro, resíduo raster como dado | 3 |
| `tests/unit/test_model_symbols.py` (novo) | método sobre o corpus, rotação, erros, resíduo | 3 |
| `src/zeny_project_handler_server/symbol_execution.py` | 5º método, tabela, digest e versão | 4 |
| `tests/integration/test_model_symbols_runner.py` (novo) | runner, reconciliação e cache | 4 |
| `tests/unit/test_e15_symbol_signatures.py`, `tests/server/test_e15_symbol_jobs.py`, `tests/integration/test_e15_symbol_cache.py`, `tests/integration/test_e16_symbol_context_runtime.py` | só onde contarem métodos | 4 |
| `tests/unit/test_grammar_frames_ataque.py`, `tests/unit/test_symbol_matcher_ataque.py`, `tests/unit/test_grammar_disc.py` | resíduos herdados | 5 |

`src/...` é `src/zeny_project_handler/adapters/analysis`. Nenhuma outra etapa aberta: a regra de arquivos disjuntos não se aplica.

---

### Task 1: Agrupamento limitado (R-9)

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/groups.py`
- Modify: `tests/unit/test_drawing_model_groups.py`, `tests/unit/test_drawing_model_geometry_grau_alto.py`

**Interfaces:**
- Produces: `LIMITE_VISITAS_AGRUPAMENTO: Final = 50_000_000`; `class AgrupamentoExcedido(Exception)`; `agrupar_candidatos(primitivas, caminhos, *, folga=1.5, lado_maximo=40.0, limite_visitas=LIMITE_VISITAS_AGRUPAMENTO)`.

- [ ] **Step 1: Tirar o `xfail` de `test_agrupamento_escala_linearmente_com_caixas_sobrepostas`** e ver falhar.
- [ ] **Step 2: Escrever os testes**:
  - `test_saida_igual_a_uniao_anterior`: cópia local da união de hoje no teste; 200 sementes com caixas aleatórias, inclusive sobrepostas, e a partição de grupos igual;
  - `test_teto_de_visitas_levanta`: `limite_visitas=10` em página densa levanta `AgrupamentoExcedido`; `limite_visitas` exato passa e o exato menos 1 levanta;
  - `test_visita_nao_multiplica_em_caixas_distantes`: n e 2n caixas espalhadas, visitas no máximo 2,5 vezes;
  - `test_pagina_densa_vira_grupos_falhou`, pelo adaptador, com `pymupdf_drawing_model.agrupar_candidatos` trocado por monkeypatch que passa `limite_visitas` baixo: `modelo.grupos == ()`, `"modelo.grupos_falhou" in modelo.diagnosticos`, sem exceção, e `caminhos` e `primitivas` iguais.
- [ ] **Step 3: Implementar.** Em `_unir_proximos`, uma visita é cada entrada de célula lida, contada antes do `update`; `if raiz(j) == raiz(i): continue` antes de `_caixas_se_encostam`. Estourou, levanta `AgrupamentoExcedido`. CC < 31.
- [ ] **Step 4: Medir nas 16 folhas**, com script descartável fora do Git, lendo `examples/` do checkout principal (`C:\Users\Caio\Desktop\repos\ZenyProjectHandler\examples`), só leitura e sem `avaliacao-cega`, com processos em paralelo: visitas de cada folha. Cole no relatório o máximo por folha e confira que fica abaixo de 1/10 do limite; se não, reporte antes de seguir.
- [ ] **Step 5: Rodar** `.venv/Scripts/python.exe -m pytest tests/unit/test_drawing_model_groups.py tests/unit/test_drawing_model_geometry_grau_alto.py tests/unit/test_pagina_para_gramaticas.py`. Expected: PASS, sem `xfail` de R-9.
- [ ] **Step 6: Commit** (`fix: agrupamento do modelo sem comparacao repetida e com teto de visitas`).

### Task 2: Caminhos lidos como glifo chegam à página das gramáticas (I3, parte 1)

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/.../drawing_model/glyph_text.py`, `src/.../drawing_model/symbol_grammars.py`, `src/.../pymupdf_drawing_model.py`
- Create: `tests/unit/test_grammar_frames_contorno_real.py`
- Modify: `tests/unit/test_glyph_text.py`, `tests/unit/test_pagina_para_gramaticas.py`

**Interfaces:**
- Consumes: `pagina_para_gramaticas`, `casar_variantes`; `GlifoDoTrecho.indice_caminho` de `glyph_text.py`; `pdf_texto_contorno`, `pdf_texto_nativo`, `LinhaTexto` e `tabela_do_alfabeto` de `tests/fixtures/glyphs/fonte_livre.py`.
- Produces:
  - `LeituraGlifos.caminhos_lidos: frozenset[int] = frozenset()`, preenchido só nos **grupos** que viram `TextoGlifo`, porque `ler_texto_glifos` descarta por grupo dentro do trecho; com default, sem mudar a saída do analisador padrão;
  - `PaginaGramatica.glifos_lidos: frozenset[int] = frozenset()`, com default para não mudar as fixtures nem as igualdades existentes.

- [ ] **Step 1: Confirmar o defeito.** Escreva `test_rotulo_em_contorno_casa`, sobre o PDF de `pdf_texto_contorno` com a moldura desenhada por cima, em `tmp_path`, com variante `label_in_frame` e `empty_interior` da gramática CT, lida do pacote real `family-f02-06`: `CT` em contorno, com letra de área ≥ 6% da moldura. Se passar sem mudança, I3 não se confirmou: registre no relatório, commit só desse teste, e as Tasks 2 e 6 terminam aqui. Se falhar, siga, e o teste fica com `xfail(strict=True, raises=AssertionError)`, citando I3, até a Task 6.
- [ ] **Step 2: Escrever os testes**:
  - `test_caminhos_lidos_so_de_grupo_resolvido`, em `test_glyph_text.py`: grupo resolvido e grupo não resolvido no mesmo trecho, e só as posições do primeiro entram;
  - `test_glifos_lidos_na_pagina`, em `test_pagina_para_gramaticas.py`: positivo, e negativo com tabela sem a letra; e `pagina.modelo` igual ao de `extrair_modelo_desenho`.
- [ ] **Step 3: Implementar.** `_montar_pagina` repassa a leitura já feita (por exemplo, por `_Fontes`), **sem ler os glifos duas vezes** (~20 s por folha); `pagina_para_gramaticas` preenche `glifos_lidos`. `modelo` não muda.
- [ ] **Step 4: Rodar** `.venv/Scripts/python.exe -m pytest tests/unit/test_grammar_frames_contorno_real.py tests/unit/test_glyph_text.py tests/unit/test_glyph_text_veneno.py tests/unit/test_pymupdf_glyph_text.py tests/unit/test_pagina_para_gramaticas.py tests/unit/test_symbol_grammars_contexto.py`. Expected: PASS, com o `xfail` do Step 1.
- [ ] **Step 5: Commit** (`feat: pagina das gramaticas sabe quais caminhos foram lidos como glifo`).

### Task 6: A guarda de marca pula o caminho lido como glifo (I3, parte 2)

**Estimativa:** 15 min · **Depende de:** Task 2 · **Risco:** alto · **Laboratório:** não

Não roda se a Task 2 não confirmou I3.

**Files:**
- Modify: `src/.../drawing_model/grammar_frames.py`, `tests/unit/test_grammar_frames_contorno_real.py`

**Interfaces:**
- Consumes: `PaginaGramatica.glifos_lidos` (Task 2).

- [ ] **Step 1: Escrever os testes**, no mesmo arquivo e com a mesma variante:
  - tirar o `xfail` de `test_rotulo_em_contorno_casa`;
  - `test_rotulo_em_contorno_nao_resolvido_nao_casa`: tabela sem a letra, sem texto e sem casamento;
  - `test_marca_preenchida_ao_lado_do_rotulo_recusa`: rótulo em contorno mais um retângulo preenchido real na moldura;
  - `test_triangulo_preenchido_na_caixa_do_rotulo_recusa`: triângulo preenchido de **outra cor** contido na caixa do span do rótulo, em contorno e em nativo, com o mesmo resultado nos dois (`negative_examples` da variante CT). Afirme como premissa que `CT` foi lido em `modelo.textos`: triângulo da mesma cor entra no trecho ou o envenena, e o teste recusaria por falta de rótulo, sem exercitar a guarda;
  - `test_rotulo_nativo_igual_ao_contorno`: mesma folha em `pdf_texto_nativo`, mesmas variantes.
- [ ] **Step 2: Implementar R-E06.2.2.1-5.** `_marca_de_proposta` pula a posição que está em `glifos_lidos`.
- [ ] **Step 3: Rodar** `.venv/Scripts/python.exe -m pytest tests/unit/test_grammar_frames_contorno_real.py tests/unit/test_grammar_frames.py tests/unit/test_grammar_frames_ataque.py tests/unit/test_symbol_matcher_paridade.py`. Expected: PASS.
- [ ] **Step 4: Commit** (`fix: contorno do rotulo em glifo nao aciona a guarda de marca`).

### Task 3: Método versionado

**Estimativa:** 45 min · **Depende de:** Task 2 · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/model_symbols.py`, `tests/unit/test_model_symbols.py`
- Modify: `src/.../drawing_model/symbol_grammars.py` (só a docstring de `_verificar_fontes`)

**Interfaces:**
- Consumes: `declarative_symbols.Package`, `_enabled`, `_geometry`, `_validate_page_size`, `carregar_pacotes`; `pagina_para_gramaticas`; `casar_variantes`, `CasamentoGramatica`; `PaginaGramatica`, `TetoGramaticasExcedido`, `FonteGramaticaFalhou`, `LIMITE_CONSULTAS_PAGINA`; `TabelaGlifos`, `carregar_tabela_glifos`; `VERSAO_MODELO_DESENHO`.
- Produces:
  - `perfil_pacotes_modelo(pacotes: tuple[Package, ...], tabela: TabelaGlifos, *, limite: int = LIMITE_CONSULTAS_PAGINA) -> PerfilMetodoSimbolos`: `metodo_id="declarative-drawing-model"`, `versao="1.0.0"`, `familia`, `classes_suportadas` e `camadas_suportadas` como `perfil_pacotes`, `dominio_aplicacao="PDF vetorial lido pelo modelo de desenho; contexto não inferido"`, `fontes_compartilhadas=("pymupdf:get_drawings:extended", "pymupdf:get_text:rawdict", "pymupdf:annotations", "modelo-desenho:glifos")`, `perfil_referencia` igual ao do motor, `parametros` com `modelo_desenho`, `package_sha256`, `tabela_glifos_versao`, `tabela_glifos_sha256`, `limite_consultas`, `enabled_variants`.
  - `observar_pacotes_modelo(page: Any, *, documento_id: str, documento_sha256: str, pagina_numero: int, pacotes: tuple[Package, ...], tabela: TabelaGlifos, perfil: PerfilMetodoSimbolos | None = None, limite: int = LIMITE_CONSULTAS_PAGINA) -> ResultadoMetodoSimbolos`. `perfil` evita recalcular o sha a cada página.
  - `@dataclass(frozen=True, slots=True) class ResiduoRaster: caixa: Caixa; sha256: str; de_anotacao: bool`
  - `residuos_raster(pagina: PaginaGramatica, casamentos: Sequence[CasamentoGramatica]) -> tuple[ResiduoRaster, ...]`, em ordem de `modelo.imagens`.

- [ ] **Step 1: Escrever os testes**:
  - `test_paridade_de_observacao_com_o_motor_no_corpus`: em `build_enabled_corpus`, cada observação do método tem geometria, primitiva, `template` e atributos iguais aos de `observar_pacotes` na mesma página; só `metodo_assinatura` e o id diferem. Inclui `camada`, com e sem OCG;
  - `test_geometria_com_rotacao_e_cropbox`: 90, 180, 270 e CropBox nas gramáticas invariantes: `pontos_originais` e `pontos_normalizados` batem com o motor a menos de 1e-3;
  - `test_divergencia_de_orientacao_continua_explicita`: triângulo a 180°;
  - `test_teto_vira_fora_de_dominio_sem_observacao`: motivo `teto_consultas`, e `classes_avaliadas` igual às suportadas, para a matriz dar `not_applicable`;
  - `test_fonte_nova_vira_fora_de_dominio` (`primitivas`, `textos_nativos`, `textos_shx`, `glifos`, por monkeypatch em `pagina_para_gramaticas`): motivo `fonte_falhou:<codigo>`, sem caminho nem nome de PDF, sem observação;
  - `test_caminhos_falhou_vira_falha` e `test_caminhos_e_outra_fonte_falham_juntos_vira_falha`;
  - `test_sem_casamento_e_nao_deteccao` e `test_sem_variante_habilitada_e_fora_de_dominio`, como `_coverage_state`;
  - `test_perfil_muda_com_pacote_tabela_e_limite`;
  - `test_residuo_raster`, parametrizado: imagem compacta conta, de página e de anotação; não contam imagem grande, imagem fora da página, imagem com centro de um casamento sobre ela e `> 8` imagens de mesma dimensão com hashes distintos; o mesmo hash repetido `> 8` vezes conta; dimensão 0 não vira mosaico; mesma imagem na mesma caixa conta uma vez;
  - `test_residuo_nao_vira_observacao`: a contagem vem em `motivo` (`residuo_raster:<n>`), e `observacoes` não muda;
  - `test_formato_do_motivo`, parametrizado: `residuo_raster:0`; `residuo_raster:2`; `residuo_raster:2;imagens_falhou`; `teto_consultas`, `glifos_limitados` e `fonte_falhou:<codigo>` sem contagem;
  - `test_imagens_falhou_mantem_casamentos_e_marca_motivo`.
- [ ] **Step 2: Implementar.** A caixa do casamento vem no espaço visual; `pymupdf.Rect(caixa) * page.derotation_matrix` dá a caixa cru para `_geometry` (R-E06.2.1-7). A primitiva usa `indices_crus[c.caminho]` e `estilo.camada or None`: `Estilo.camada` é `""` sem OCG, o motor grava `None`, e a reconciliação compara os dois, então `""` duplicaria toda ocorrência. Os atributos são os de `_known_observation`. `perfil.assinatura()` é calculada uma vez por chamada. Uma só cobertura por página, como o motor. A tradução segue R-E06.2.2.1-3, e a docstring de `_verificar_fontes`, em `symbol_grammars.py`, passa a citá-la. Exceção inesperada não é capturada: o runner é fail-closed.
- [ ] **Step 3: Medir nas 16 folhas**, com script descartável, como na Task 1: tempo, estado da cobertura, motivo e resíduos por folha. Cole no relatório. Se passar de 20 resíduos numa folha ou houver cobertura `FORA_DOMINIO`/`FALHA`, reporte antes de seguir.
- [ ] **Step 4: Rodar** `.venv/Scripts/python.exe -m pytest tests/unit/test_model_symbols.py`. Expected: PASS.
- [ ] **Step 5: Commit** (`feat: metodo de pacotes sobre o modelo de desenho`).

### Task 4: Ligação no runner

**Estimativa:** 30 min · **Depende de:** Tasks 1, 3 e 6 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler_server/symbol_execution.py`
- Create: `tests/integration/test_model_symbols_runner.py`
- Modify (só se contarem métodos): `tests/unit/test_e15_symbol_signatures.py`, `tests/server/test_e15_symbol_jobs.py`, `tests/integration/test_e15_symbol_cache.py`, `tests/integration/test_e16_symbol_context_runtime.py`

**Interfaces:**
- Consumes: `model_symbols.perfil_pacotes_modelo`, `observar_pacotes_modelo`; `carregar_tabela_glifos`.
- Produces: `SymbolCompositionRunner(settings, *, templates=None, packages=None, calibration=None, glyph_table=None)`; `_VERSION = "e06-server-symbol-composition-2"`.

- [ ] **Step 1: Escrever os testes**:
  - `test_quinto_metodo_roda_e_entra_na_assinatura`: um PDF sintético do corpus, com `symbol_profile` sem raster, `run` conclui, e o journal traz `declarative-drawing-model` em cada página;
  - `test_mesmo_desenho_nao_duplica_na_reconciliacao`: o mesmo rótulo visto pelos dois métodos vira 1 ocorrência com os dois métodos, em página com e sem OCG;
  - `test_assinatura_muda_com_tabela_e_com_modulo_do_nucleo`: tabela diferente e digest diferente, parametrizado em `symbol_matcher`, `glyph_signature` e `pymupdf_annotations` (monkeypatch em `_module_digest`);
  - `test_teto_no_metodo_novo_e_cacheado_e_nao_derruba_os_outros`: `limite` pequeno por monkeypatch: `run` conclui, a segunda execução dá `cache_hit`, e os outros métodos observam;
  - `test_falha_de_fonte_aborta_e_nao_entra_no_cache`: `modelo.caminhos_falhou` levanta `SymbolCompositionError`, sem cache;
  - `test_residuo_raster_nao_gera_proposta`: página com imagem compacta: `reconcile_symbols` não ganha ocorrência, e o `motivo` traz a contagem no journal.
- [ ] **Step 2: Implementar.** Perfil depois de `perfil_pacotes`, calculado uma vez; `_observe_page` chama `_check_cancelled` e emite depois de `observar_pacotes`, com a página aberta; no digest, `model_symbols`, `pymupdf_drawing_model`, `pymupdf_annotations`, `pymupdf_page_extractors`, `pymupdf_support` (`_box_geometry`), `pymupdf_glyphs` (`_path_points` define os cantos de `re` e `qu`), e de `drawing_model/` `symbol_grammars`, `grammar_frames`, `grammar_disc`, `symbol_matcher`, `groups`, `geometry`, `glyph_text`, `glyph_signature` e `glyph_table`. `run` e `_cache_complete` não ganham ramo: `_profiles` já dá a contagem. Assinatura do cache muda só para quem liga o opt-in.
- [ ] **Step 3: Ajustar o que contar 4 métodos**, sem mudar o que cada teste verifica. Se nenhum contar, registre no relatório.
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
| 2 | Tasks 3 e 6 | dependem da Task 2; arquivos disjuntos |
| 3 | Task 4 | depende das Tasks 1, 3 e 6 |

Soma das estimativas: 155 min. A numeração das Tasks 3 a 5 foi mantida ao dividir a Task 2 em 2 e 6, por causa do limite de 3 arquivos de produção por tarefa.

## Fechamento operacional

| Critério de aceite | Evidência |
|---|---|
| Fixtures positivas e negativas do método e da ligação | Tasks 3 e 4 |
| Agrupamento de R-9 sem `xfail` | Task 1 |
| `scripts.audit_symbol_packages` → 0 erros | Task 4 |
| `IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` | o orquestrador roda `cmd.exe //c ".\\IniciarTestes.bat"` antes do `#concluida` e confere a data do relatório |

No handoff, para a E06.2.2.2:
- o nome e a assinatura do método; tempo, cobertura e resíduos por folha (Task 3, Step 3); a instrução de separar o gasto de orçamento entre colagem e gramáticas no diff;
- contar `fonte_falhou:` como falha, não como exclusão; `glifos_desconhecidos` deixa a guarda sem aquele texto.

Para a E06.3: a H2 se confirma chamando `residuos_raster` folha a folha, e não lendo a ocorrência reconciliada, e uma página `FORA_DOMINIO` não conta como 0 resíduos; quem consumir `grupos` adiciona `modelo.grupos_falhou` às fontes consumidas e sobe a versão (R-1).

Para a E12: `residuos_raster` é o ponto de partida; o contrato do que ela consome é dela.

Para a E09: R-6; R-E06.2.1-2; `model_symbols` depende de privados de `declarative_symbols`, que ela remove.

Em "Decisões para o usuário": R-1 (exceção ao invariante de versão), R-3 (fonte nova que falha deixa de ser fail-closed) e R-4 (resíduo raster como dado, sem observação).

A medição da Task 3 roda sem a guarda da Task 6, que corre na mesma onda: o orquestrador repete o script depois de integrar a Onda 2 e leva esse número ao handoff.

## Revisão de arquitetura

- **Veredito:** aprovado com notas.
- **Rodadas:** 2.
- **Modelo:** opus.
- **Notas Menores:** as duas da rodada 2 foram aplicadas ao plano (medição da Task 3 antes da guarda da Task 6 e texto de R-5). Não verificado pelo revisor: nada executado; se I3 se confirma; visitas, resíduos e estados de cobertura nas 16 folhas, que as Tasks 1 e 3 medem. R-1, R-3 e R-4 vão a "Decisões para o usuário" no fechamento.
