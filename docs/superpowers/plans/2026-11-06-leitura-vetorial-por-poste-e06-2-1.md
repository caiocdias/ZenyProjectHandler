# E06.2.1 — Núcleo de gramáticas sobre o modelo: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** portar as 6 gramáticas dos pacotes declarativos para um núcleo puro sobre a página do modelo de desenho, com paridade de variantes por página no corpus sintético e custo limitado por página.

**Architecture:** o núcleo fica em `adapters/analysis/drawing_model/` (puro, sem PyMuPDF) e recebe uma `PaginaGramatica`: a `PaginaModelo`, o índice cru de cada caminho e os preenchimentos translúcidos. Um índice por grade e um orçamento de consultas substituem os laços O(F·D) e `get_text` por moldura do motor atual. O motor `declarative_symbols` não muda: é a referência da paridade. Nada liga no job nem no runner nesta etapa (E06.2.2, D12).

**Tech Stack:** Python 3.11–3.13, dataclasses imutáveis, PyMuPDF só em `pymupdf_drawing_model.py`, pytest, mypy strict.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seções "E06.2" e "E06.2.1", mais `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` e `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md`. O levantamento está em `tmp/e06/levantamento-e06.md` do checkout principal (fora do Git).

## Global Constraints

- Domínio e aplicação não importam PyMuPDF. Em `drawing_model/` o único leitor PyMuPDF continua sendo `pymupdf_drawing_model.py` (fora da pasta); os módulos novos de `drawing_model/` não importam `pymupdf` nem `declarative_symbols`.
- Sem mudança em `VERSAO_MODELO_DESENHO`, no formato do cache, em `Estilo` ou nos tipos de `model.py`: a versão entra na capacidade do analisador padrão, e mudá-la invalidaria o cache de quem não usa o método (D12).
- Sem mudança de saída no analisador padrão, no runner e em `declarative_symbols.py`.
- PDFs reais, recortes e rótulos nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa, autoral.
- Testes novos não dependem de ordem, cwd, porta ou arquivo fixo (`tmp_path`, ids determinísticos), nem de tempo de parede: custo se prova contando trabalho.
- Pytest com `--strict-markers` e `ResourceWarning` como erro: feche documentos PyMuPDF.
- mypy strict, ruff check e ruff format; `scripts/complexity_gate.py src` falha em CC ≥ 31.
- Código e nomes em português, como o resto de `drawing_model/`.
- Nenhuma etapa, fixture ou script lê `examples/avaliacao-cega/`.
- Documentação enxuta: nada de histórico de execução em arquivo versionado.

## Decisões do plano

- **R-E06.2.1-1, núcleo separado do motor atual:** os limiares do motor atual são copiados como constantes nomeadas nos módulos novos, sem importar `declarative_symbols` (que importa PyMuPDF). A duplicação dura até a E09, que remove o motor antigo. Custo se errado: um ajuste de limiar teria de ser feito nos dois até lá; o motor antigo não muda mais.
- **R-E06.2.1-2, opacidade fora do modelo:** `Estilo` não tem `fill_opacity`, e `_covered_later` precisa dela. Em vez de mudar o modelo e `VERSAO_MODELO_DESENHO`, `PaginaGramatica.translucidos` carrega as posições translúcidas, lidas pelo adaptador. Custo se errado: o cache do modelo não serve às gramáticas sem reler a página, o que a E06.2.2 já não faz (lê da página aberta).
- **R-E06.2.1-3, teto por orçamento de consultas:** um contador determinístico, não tempo de parede nem número de molduras, porque o custo adversarial vem da densidade numa célula. Estourou, o núcleo levanta `TetoGramaticasExcedido`; a E06.2.2 traduz em cobertura `FORA_DOMINIO` com motivo. Tudo ou nada: observação parcial numa página cortada seria uma não detecção falsa. O limite inicial é 2.000.000 consultas; a E06.2.2 mede o gasto real nas 16 folhas.
- **R-E06.2.1-4, palavras a partir de spans:** `TextoModelo` é um span, e o motor atual lê palavras. O núcleo quebra por espaço e reparte a largura proporcionalmente aos caracteres, só em texto horizontal (rotação 0 ou 180 ± 1°). Rotação diferente e multi-palavra usa a caixa inteira, o que tende a falhar fechado.
- **R-E06.2.1-5, ganhos previstos sobre o motor atual:** moldura de 4 traços separados (polilinha fechada) e rótulo em glifo ou SHX casam no modelo. Isso é o objetivo do porte, não quebra de paridade: o corpus sintético não tem esses casos, e cada um ganha fixture própria na Task 6.
- **R-E06.2.1-6, linha terminal por polilinha:** nos caminhos só de traço, a linha terminal do disco vem das pontas das polilinhas abertas; a linha que atravessa o disco em dois segmentos não termina nele (o motor atual aceita). Nos caminhos com traço e preenchimento, vêm os segmentos crus.

## Review Focus

1. Página hostil, com milhares de molduras, segmentos ou palavras sobrepostos numa célula: `TetoGramaticasExcedido` determinístico, com o trabalho limitado pelo orçamento e nenhum laço quadrático fora dele (Task 2, Task 4, Task 5).
2. Coordenada finita enorme (1e300) ou caixa gigante: a grade não multiplica células nem estoura memória; item fora da página não vira moldura (Task 2).
3. Span com várias palavras, em minúsculas, com espaços nas pontas, rotacionado ou só de espaços: o rótulo casa como no motor atual ou falha fechado, sem exceção (Task 2, Task 4).
4. Página rotacionada ou com CropBox: caixa e índice cru batem com o motor atual, porque a reconciliação do runner depende dos dois (Task 3, Task 6).
5. Geometria degenerada: polilinha fechada com menos de 4 pontos, círculo de raio 0, moldura de lado 0, `Caminho` sem subcaminho, opacidade `NaN` ou não numérica: sem exceção, e o item não casa (Task 2, Task 3, Task 5).

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/drawing_model/geometry.py` | D1: travessia linear em nó de grau alto | 1 |
| `tests/unit/test_e06_1_etapa_ataque.py` | tirar o `xfail` da D1 | 1 |
| `tests/unit/test_drawing_model_geometry_grau_alto.py` (novo) | ordem e origens preservadas em nó de grau alto | 1 |
| `src/.../drawing_model/symbol_grammars.py` (novo) | `PaginaGramatica`, orçamento, grade, molduras, palavras, segmentos, contexto | 2 |
| `tests/fixtures/symbol_grammars/__init__.py`, `paginas.py` (novos) | construtores de `PaginaGramatica` sintética | 2 |
| `tests/unit/test_symbol_grammars_contexto.py` (novo) | núcleo | 2 |
| `src/.../pymupdf_drawing_model.py` | `pagina_para_gramaticas`, translúcidos, fim do fallback de `indices_crus` | 3 |
| `tests/unit/test_pymupdf_drawing_model.py`, `test_pymupdf_drawing_model_adversarial.py` | monkeypatch de `_desenhos` sem o fallback | 3 |
| `tests/unit/test_pagina_para_gramaticas.py` (novo) | adaptador | 3 |
| `src/.../drawing_model/grammar_frames.py` (novo) | 5 gramáticas de moldura | 4 |
| `tests/unit/test_grammar_frames.py` (novo) | positivos e quase-acertos puros | 4 |
| `src/.../drawing_model/grammar_disc.py` (novo) | gramática `terminal_disc` | 5 |
| `tests/unit/test_grammar_disc.py` (novo) | positivos e quase-acertos puros | 5 |
| `src/.../drawing_model/symbol_matcher.py` (novo) | `casar_variantes`, despacho e deduplicação | 6 |
| `tests/unit/test_symbol_matcher_paridade.py` (novo) | paridade com `observar_pacotes` no corpus, rotação, ganhos, pureza | 6 |

`src/...` é `src/zeny_project_handler/adapters/analysis`. Nenhuma etapa aberta em paralelo: a regra de arquivos disjuntos não se aplica.

---

### Task 1: Pré-condição D1, fusão linear em nó de grau alto

**Estimativa:** 20 min · **Depende de:** nenhuma · **Risco:** normal · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/geometry.py` (`_polilinhas_do_estilo`)
- Modify: `tests/unit/test_e06_1_etapa_ataque.py` (remover o `xfail` de `test_fusao_escala_linearmente_com_no_de_grau_alto`)
- Create: `tests/unit/test_drawing_model_geometry_grau_alto.py`

**Interfaces:**
- Produces: `reconstruir_polilinhas` com a mesma assinatura e a mesma saída (ordem inclusive).

- [ ] **Step 1: Tirar o `xfail(strict=True)`** do teste citado e ver falhar nos dois parâmetros (`no-com-muitos-raios`, `mesmo-segmento-pintado-n-vezes`).

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_e06_1_etapa_ataque.py -k grau_alto`
Expected: FAIL (`grande <= 2.5 * pequeno`).

- [ ] **Step 2: Escrever `test_saida_identica_em_no_de_grau_alto`**: uma estrela de 5 raios mais um raio duplicado, em ordem fixa, com a lista exata esperada de `(pontos, fechada, origens)`, valores obtidos antes da mudança rodando o código atual. Mais `test_ciclo_e_segmento_duplo_mantem_a_saida`: quadrado fechado com uma diagonal e um segmento pintado duas vezes, mesma técnica. Tem de passar antes e depois da correção.

- [ ] **Step 3: Implementar um cursor por nó** em `_polilinhas_do_estilo`: `proxima` e o `while any(...)` passam a usar um ponteiro por nó que avança sobre `incidentes[n]` pulando as arestas usadas. Aresta usada nunca volta a ser livre, então o ponteiro é monótono e a escolha ("a primeira livre") é a mesma de hoje. Ordem da saída idêntica; `VERSAO_MODELO_DESENHO` não muda.

- [ ] **Step 4: Rodar os testes de geometria**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_e06_1_etapa_ataque.py tests/unit/test_drawing_model_geometry.py tests/unit/test_drawing_model_geometry_adversarial.py tests/unit/test_drawing_model_geometry_grau_alto.py`
Expected: PASS, sem xfail nesse teste.

- [ ] **Step 5: Commit** (`fix: reconstruir_polilinhas linear em no de grau alto`).

### Task 2: Núcleo puro: página, orçamento, grade, molduras, palavras e segmentos

**Estimativa:** 40 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_grammars.py`
- Create: `tests/fixtures/symbol_grammars/__init__.py`, `tests/fixtures/symbol_grammars/paginas.py`
- Create: `tests/unit/test_symbol_grammars_contexto.py`

**Interfaces:**
- Consumes: tipos de `drawing_model/model.py`.
- Produces (todas públicas no módulo, usadas pelas Tasks 3–6):
  - `LIMITE_CONSULTAS_PAGINA: Final = 2_000_000`
  - `class TetoGramaticasExcedido(Exception)`
  - `@dataclass(frozen=True, slots=True) class PaginaGramatica: modelo: PaginaModelo; indices_crus: tuple[int, ...]; translucidos: frozenset[int]`: `indices_crus[i]` e `translucidos` falam da posição `i` em `modelo.caminhos`.
  - `class OrcamentoConsultas: __init__(self, limite: int); gastar(self, quantidade: int = 1) -> None` (levanta `TetoGramaticasExcedido`); `gasto: int`.
  - `class GradeEspacial(Generic[T]): __init__(self, itens: Iterable[tuple[Caixa, T]], limites: Caixa, orcamento: OrcamentoConsultas)`; `consultar(self, caixa: Caixa) -> list[T]` em ordem de inserção, sem repetir, gastando 1 do orçamento por item visitado.
  - `@dataclass(frozen=True, slots=True) class Moldura: forma: Literal["retangulo", "elipse", "losango"]; caixa: Caixa; caminho: int`
  - `@dataclass(frozen=True, slots=True) class Segmento: a: Ponto; b: Ponto; caminho: int`
  - `@dataclass(frozen=True, slots=True) class Palavra: texto: str; caixa: Caixa` (`texto` em maiúsculas, sem espaços nas pontas)
  - `@dataclass(frozen=True, slots=True) class ContextoGramatica` com `pagina: PaginaGramatica`, `orcamento`, `molduras: tuple[Moldura, ...]`, `grade_molduras: GradeEspacial[Moldura]`, `grade_palavras: GradeEspacial[Palavra]`, `grade_segmentos: GradeEspacial[Segmento]`, `grade_caminhos: GradeEspacial[int]`, `caixas_caminhos: Mapping[int, Caixa]`.
  - `contexto_gramaticas(pagina: PaginaGramatica, *, limite: int = LIMITE_CONSULTAS_PAGINA) -> ContextoGramatica`
  - Auxiliares públicos `contem(externa: Caixa, interna: Caixa) -> bool`, `intersecta(a: Caixa, b: Caixa) -> bool`.

Regras que o implementador não decide:
- **Grade:** célula de 16 pt; só indexa a parte da caixa dentro de `limites` (página com margem de 16 pt), e caixa que cobriria mais de 64 células vai para uma lista `grandes`, percorrida em toda consulta, contando orçamento. Item inteiramente fora é ignorado. Mesmo desenho de `_CamadasDoTexto` em `pymupdf_drawing_model.py`, sem compartilhar código (ele é adaptador).
- **Molduras:** por caminho, em ordem de posição; por subcaminho fechado de 4 `l`: `retangulo` se os lados são alinhados aos eixos (tolerância 0,01 pt), senão `losango` se `_is_diamond` confere (mesma regra do motor: lados ≥ 4, tolerância `max(1, 0,08·min(l, a))`, cada canto do losango com 2 pontas). Um caminho de exatamente 4 `c` e nada mais: `elipse`, com a caixa dos pontos. Depois as primitivas: `Polilinha` fechada de 4 pontos vira `retangulo` ou `losango` (`caminho = origens[0]`) e `Circulo` de raio > 0 vira `elipse`. Deduplica por `(forma, caixa arredondada a 3 casas)`, ficando o primeiro. Moldura com lado 0 ou inteiramente fora da página não entra.
- **Segmentos:** os itens `l` de todo subcaminho que não seja moldura fechada de 4 `l`; mantêm a posição do caminho.
- **Palavras:** `R-E06.2.1-4`. Texto só de espaços não gera palavra.
- **Contexto:** gasta orçamento ao construir (um por item indexado), para página gigante também estourar ali.

- [ ] **Step 1: Criar a fixture** `tests/fixtures/symbol_grammars/paginas.py`, sem PyMuPDF: `estilo(cor=(0,0,0), preenchimento=None, camada="")`, `linha(a, b, ordem=0, ...)`, `retangulo_traco(caixa, ordem=0, ...)`, `poligono(pontos, ordem=0, preenchimento=None, ...)`, `circulo_bezier(centro, raio, ordem=0, ...)`, `texto(palavra, caixa, origem="nativo", rotacao=0.0)` e `pagina_gramatica(caminhos, textos=(), primitivas=None, largura=300.0, altura=300.0, translucidos=frozenset()) -> PaginaGramatica`: com `primitivas=None`, chama `reconstruir_polilinhas` e `recuperar_circulos_e_arcos`; `indices_crus` é `range` deslocado de 10 (para o teste notar confusão entre posição e índice cru).

- [ ] **Step 2: Escrever os testes**, com estes nomes e asserções:
  - `test_orcamento_estoura_no_limite`: `OrcamentoConsultas(3)`, `gastar(3)` passa, `gastar()` levanta `TetoGramaticasExcedido`.
  - `test_grade_consulta_em_ordem_sem_repetir`: item em duas células sai uma vez; a ordem é a de inserção.
  - `test_grade_ignora_item_fora_da_pagina` e `test_coordenada_enorme_nao_multiplica_celulas`: caixa `(-1e300, -1e300, 1e300, 1e300)` vai para `grandes` e sai na consulta; `len(grade._celulas)` não cresce com ela.
  - `test_molduras_retangulo_elipse_losango`: um de cada, por caminho.
  - `test_moldura_de_quatro_tracos_separados`: 4 `linha` do mesmo estilo → 1 `retangulo`, com `caminho` igual à menor posição.
  - `test_retangulo_duplicado_por_caminho_e_polilinha_sai_uma_vez`.
  - `test_circulo_de_dois_arcos_vira_elipse`.
  - `test_degenerados_nao_viram_moldura`: polilinha fechada de 3 pontos, círculo de raio 0, retângulo de largura 0 e item fora da página.
  - `test_palavras_de_um_span`: `"CT 12"` a x∈[0, 50] → `CT` em x∈[0, 20] e `12` em x∈[30, 50], `"ct"` vira `CT`, `"   "` não gera nada, e o texto com `rotacao=45` e duas palavras gera duas palavras com a caixa inteira.
  - `test_segmentos_excluem_moldura_fechada`.
  - `test_pagina_densa_estoura_o_orcamento_ao_construir`: 5.000 retângulos sobrepostos com `limite=1_000` levantam `TetoGramaticasExcedido`.
  - `test_trabalho_da_consulta_cresce_com_a_densidade_local_e_nao_com_a_pagina`: mesma consulta, 1.000 e 2.000 itens distantes dela: o gasto da consulta não muda.

- [ ] **Step 3: Implementar `symbol_grammars.py`** conforme as interfaces. CC < 31 em tudo.

- [ ] **Step 4: Rodar**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_symbol_grammars_contexto.py`
Expected: PASS.

- [ ] **Step 5: Commit** (`feat: nucleo puro das gramaticas sobre o modelo de desenho`).

### Task 3: Página para as gramáticas a partir da página aberta

**Estimativa:** 20 min · **Depende de:** Task 2 · **Risco:** normal · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py`
- Modify: `tests/unit/test_pymupdf_drawing_model.py`, `tests/unit/test_pymupdf_drawing_model_adversarial.py` (só os `monkeypatch` de `_desenhos`)
- Create: `tests/unit/test_pagina_para_gramaticas.py`

**Interfaces:**
- Consumes: `PaginaGramatica` (Task 2).
- Produces: `pagina_para_gramaticas(pagina: pymupdf.Page, indice: int, tabela: TabelaGlifos | None = None) -> PaginaGramatica`. `pagina_modelo_com_indices` continua igual, para quem já a usa.

- [ ] **Step 1: Escrever os testes**:
  - `test_indices_crus_alinhados_com_clip_e_grupo`: reutiliza `_pdf_com_clip` de `tests/unit/test_pymupdf_drawing_model_pagina.py`; igual a `pagina_modelo_com_indices`.
  - `test_translucido_marcado_pela_posicao_no_caminho`: um retângulo com `fill_opacity=0.5` e um opaco, mais um `clip` antes deles: `translucidos == {posição do translúcido}`.
  - `test_opacidade_invalida_vale_como_opaca`, com `monkeypatch` de `pagina.get_drawings`: `fill_opacity` `None`, `float("nan")` e `"x"` não marcam nem levantam.
  - `test_desenho_descartado_nao_desalinha_translucidos`: desenho malformado antes do translúcido.
  - `test_modelo_igual_ao_de_extrair_modelo_desenho`: `pagina.modelo == extrair_modelo_desenho(pdf).paginas[0]`.
  - `test_sem_fallback_de_indices`: com `_desenhos` trocado por uma lista simples, `modelo.diagnosticos` traz `modelo.caminhos_falhou`.

- [ ] **Step 2: Implementar.** `_Fontes` ganha `translucidos: frozenset[int]`; `_caminhos_e_glifos` passa a devolver também as posições (em `caminhos`) com `fill_opacity` numérica, finita e `< 0.99`, e lê `desenhos.indices_crus` direto, sem `getattr` nem `or range(...)`. O `sem_caminhos` de `_ler_fontes` ganha `frozenset()`. `_desenhos` passa a anotar `_DesenhosFiltrados`. Nenhuma mudança em `model.py`, `cache.py` e `VERSAO_MODELO_DESENHO`.

- [ ] **Step 3: Ajustar os `monkeypatch`** que devolvem lista simples: passam a devolver `_DesenhosFiltrados(enumerate(lista))`, sem mudar o que cada teste verifica.

- [ ] **Step 4: Rodar**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_pagina_para_gramaticas.py tests/unit/test_pymupdf_drawing_model.py tests/unit/test_pymupdf_drawing_model_adversarial.py tests/unit/test_pymupdf_drawing_model_pagina.py tests/unit/test_pymupdf_drawing_model_pagina_ataque.py`
Expected: PASS.

- [ ] **Step 5: Commit** (`feat: pagina para as gramaticas com indice cru e translucidos`).

### Task 4: Gramáticas de moldura

**Estimativa:** 40 min · **Depende de:** Task 2 · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_frames.py`
- Create: `tests/unit/test_grammar_frames.py`

**Interfaces:**
- Consumes: `ContextoGramatica`, `Moldura`, `contem`, `intersecta` (Task 2).
- Produces: `casa_moldura(contexto: ContextoGramatica, gramatica: Mapping[str, Any], moldura: Moldura) -> bool`, para os `kind` `label_in_frame`, `triangle_in_frame`, `framed_diagonals`, `nested_rectangles_bar` e `diamond_three_dots`. Levanta `ValueError` em `kind` desconhecido.

Porte, com os mesmos limiares (constantes nomeadas), da função correspondente de `declarative_symbols.py`:

| Motor atual | Núcleo | O que muda |
|---|---|---|
| `_frame_ok` (`frame` → `forma`: `rectangle`→`retangulo`, `ellipse`→`elipse`, `diamond`→`losango`) | `_moldura_ok` | nada |
| `_label_in_frame` (inset 5%, os dois cantos dentro) | `_rotulo_na_moldura` | consulta `grade_palavras` na caixa |
| `_nested_gray_frame` | `_moldura_interna_cinza` | consulta `grade_molduras` |
| `_proposal_mark` | `_marca_de_proposta` | consulta `grade_caminhos`; usa `Estilo.preenchimento` e os `l` do caminho |
| `_triangle_in_frame` | `_triangulo_na_moldura` | caminho de 1 subcaminho com 3 `l`; `Estilo.preenchimento is not None` é "sólido" |
| `_frame_has_text` | `_moldura_tem_texto` | centro da palavra |
| `_diagonal_count` | `_diagonais` | consulta `grade_segmentos` |
| `_nested_rectangles_bar` | `_retangulos_com_barra` | `grade_molduras` e `grade_segmentos` |
| `_diamond_three_dots` | `_losango_tres_pontos` | `grade_molduras` |

- [ ] **Step 1: Escrever os testes**, com `tests/fixtures/symbol_grammars/paginas.py` (só leitura), um por gramática, nos pares positivo/quase-acerto de `tests/fixtures/declarative_symbols/corpus.py`:
  - `test_rotulo_em_retangulo` e `test_rotulo_em_elipse` (positivos); `test_rotulo_errado`, `test_rotulo_fora_da_moldura`, `test_rotulo_que_toca_a_borda_nao_casa` (dentro do inset de 5%), `test_rotulo_minusculo_casa`, `test_rotulo_em_glifo_casa`.
  - `test_empty_interior_recusa_marca_preenchida` (≥ 6% da área) e `test_empty_interior_recusa_diagonal_longa` (≥ 55% nos dois eixos); `test_empty_interior_aceita_marca_pequena`.
  - `test_moldura_interna_cinza` e os negativos `sem preenchimento`, `colorida` e `descentrada`.
  - `test_triangulo_vazio_e_solido`, `test_triangulo_de_preenchimento_trocado`, `test_triangulo_pequeno_nao_casa`, `test_triangulo_invertido_nao_casa`.
  - `test_duas_diagonais`, `test_uma_diagonal`, `test_diagonais_com_texto`.
  - `test_retangulos_com_barra`, `test_sem_interno`, `test_sem_barra`, `test_barra_de_outro_retangulo_nao_conta`.
  - `test_losango_tres_pontos`, `test_dois_pontos`, `test_ponto_fora_do_losango`.
  - `test_moldura_fora_dos_limites_de_tamanho`: `max_span`, lado < 4 e aspecto.
  - `test_kind_desconhecido_levanta`.
  - `test_cem_molduras_densas_estouram_o_orcamento`: página com orçamento pequeno levanta `TetoGramaticasExcedido`, sem varrer tudo.

- [ ] **Step 2: Implementar `grammar_frames.py`.** CC < 31; sem `pymupdf`.

- [ ] **Step 3: Rodar**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_grammar_frames.py`
Expected: PASS.

- [ ] **Step 4: Commit** (`feat: gramaticas de moldura sobre o modelo de desenho`).

### Task 5: Gramática do disco terminal

**Estimativa:** 35 min · **Depende de:** Task 2 · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/grammar_disc.py`
- Create: `tests/unit/test_grammar_disc.py`

**Interfaces:**
- Consumes: `ContextoGramatica` (Task 2).
- Produces:
  - `@dataclass(frozen=True, slots=True) class Disco: caixa: Caixa; caminho: int; membros: frozenset[int]; preenchimento: Cor` (posições em `modelo.caminhos`; `caminho = min(membros)`).
  - `discos_candidatos(contexto: ContextoGramatica) -> tuple[Disco, ...]`
  - `pontas_terminais(contexto: ContextoGramatica) -> GradeEspacial[Segmento]`: cada linha candidata, indexada pela caixa das suas pontas, uma entrada por ponta, com `a` = a ponta indexada e `b` = a outra.
  - `casa_disco(contexto: ContextoGramatica, gramatica: Mapping[str, Any], disco: Disco, pontas: GradeEspacial[Segmento]) -> bool`

Porte de `_curve_disc`, `_band_rects`, `_stack_disc`, `_disc_profile`, `_continues`, `_band_stacks`, `_band_discs`, `_disc_candidates`, `_is_purple`, `_has_terminal_line`, `_covered_later` e `_terminal_disc_matches`, com os mesmos limiares, e estas diferenças:
- **Bandas:** um caminho cujos subcaminhos são todos retângulos de 4 `l` conta uma banda por subcaminho (o `re` e o `qu` do motor); um caminho só de `l`, com 3 ou mais itens no total, conta uma banda pela caixa.
- **Disco de curva:** 4 `c` no total e no máximo 1 `l`, somando os subcaminhos.
- **Linha terminal:** `R-E06.2.1-6`. Candidatos: pontas das `Polilinha` abertas de estilo com `cor` não `None` e `min(cor) < 0.9`, mais os `Segmento` de caminhos `traco_e_preenchimento` no mesmo critério. Uma polilinha cujas `origens` estão todas em `membros` não conta. A consulta usa a grade de `pontas_terminais`, construída uma vez por página.
- **Coberto depois:** consulta `grade_caminhos` pela caixa do disco, só posições `> max(membros)`, com `preenchimento` não `None`, fora de `pagina.translucidos`.
- **Palavra sobre o disco:** o centro de uma palavra dentro da caixa do disco recusa, pela `grade_palavras`.

- [ ] **Step 1: Escrever os testes**, com os nomes dos casos de `TERMINAL_DISC_POSITIVES` e `TERMINAL_DISC_NEGATIVES` do corpus:
  - positivos: `test_disco_solido`, `test_disco_dividido` (preenchido + contorno), `test_disco_em_faixas` (12 faixas, retângulos e triângulos alternados);
  - negativos: `test_sem_disco`, `test_verde`, `test_vermelho`, `test_preto`, `test_lilas`, `test_sem_linha`, `test_linha_atravessando`, `test_grande`, `test_com_rotulo`, `test_coberto`, `test_triangulo`;
  - `test_coberto_por_translucido_nao_cobre` (posição em `translucidos`) e `test_coberto_antes_nao_cobre` (ordem anterior);
  - `test_linha_de_dois_segmentos_atravessando_nao_termina` (R-6) e `test_linha_em_ziguezague_termina_no_disco` (último segmento curto; o motor atual perde esse caso);
  - `test_linha_do_proprio_disco_nao_conta`;
  - `test_faixas_com_buraco_nao_viram_disco` e `test_faixa_descentrada_nao_vira_disco`;
  - `test_milhares_de_faixas_estouram_o_orcamento`.

- [ ] **Step 2: Implementar `grammar_disc.py`.** CC < 31; sem `pymupdf`.

- [ ] **Step 3: Rodar**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_grammar_disc.py`
Expected: PASS.

- [ ] **Step 4: Commit** (`feat: gramatica do disco terminal sobre o modelo de desenho`).

### Task 6: Casamento de variantes e paridade com o motor atual

**Estimativa:** 30 min · **Depende de:** Tasks 3, 4 e 5 · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`
- Create: `tests/unit/test_symbol_matcher_paridade.py`

**Interfaces:**
- Consumes: `contexto_gramaticas`, `casa_moldura`, `discos_candidatos`, `pontas_terminais`, `casa_disco`, `pagina_para_gramaticas`.
- Produces:
  - `@dataclass(frozen=True, slots=True) class CasamentoGramatica: pacote: Mapping[str, Any]; variante: Mapping[str, Any]; caixa: Caixa; caminho: int`
  - `casar_variantes(pagina: PaginaGramatica, variantes: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]], *, limite: int = LIMITE_CONSULTAS_PAGINA) -> tuple[CasamentoGramatica, ...]`: na ordem de `variantes` e de `molduras`/`discos`; deduplica por `(id da variante, caixa arredondada a 3 casas)`, como `_observe_variant`; `variantes` são as habilitadas, como `declarative_symbols._enabled` entrega. Só monta os discos se alguma variante for `terminal_disc`. Levanta `TetoGramaticasExcedido`.

- [ ] **Step 1: Escrever os testes**:
  - `test_paridade_de_variantes_por_pagina_no_corpus`: `build_enabled_corpus(tmp_path / "c.pdf")`; para cada página, `{c.variante["id"]}` é igual a `expected_variant_ids` do manifesto e às `template` de `observar_pacotes` na mesma página. Parametrização única, com `pacotes = carregar_pacotes()`, e mensagem de erro com `page`, `variant_id` e `stratum`.
  - `test_caixa_e_indice_cru_batem_com_o_motor_atual` (parametrizado em rotação 0, 90, 180 e 270, nos estratos `positive*`): aplica `set_rotation` em cada página do corpus, compara a caixa do casamento normalizada por largura/altura com o envelope de `pontos_normalizados` da observação, a menos de 1e-3, e `indices_crus[c.caminho] == int(obs.primitivas[0].indice)`.
  - `test_cropbox_nao_desloca_a_caixa`: página do corpus com `set_cropbox`, mesma comparação.
  - `test_ganho_moldura_de_quatro_tracos`: rótulo `CT` em moldura de 4 `draw_line` separados: o núcleo casa e `observar_pacotes` não. E `test_quase_acerto_de_quatro_tracos_com_folga`: um canto aberto em 2 pt: nenhum dos dois casa.
  - `test_ganho_rotulo_em_glifo`: página pura com `texto(..., origem="glifo")` e moldura casa; sem o texto, não.
  - `test_pagina_sem_desenhos_nao_casa_nada` e `test_variantes_vazias_nao_montam_discos`.
  - `test_ordem_e_deterministica`: duas execuções, mesma tupla.
  - `test_teto_propaga`: `limite=10` em página densa levanta `TetoGramaticasExcedido`.
  - `test_modulos_do_nucleo_nao_importam_pymupdf`: lê com `ast` os 4 módulos novos e reprova import de `pymupdf`, `fitz`, `declarative_symbols` e `pymupdf_drawing_model`.

- [ ] **Step 2: Implementar `symbol_matcher.py`.**

- [ ] **Step 3: Rodar**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_symbol_matcher_paridade.py tests/unit/test_declarative_symbol_packages.py`
Expected: PASS. Divergência de paridade é defeito do porte: corrija em `symbol_grammars.py`, `grammar_frames.py` ou `grammar_disc.py`, nunca no corpus nem em `declarative_symbols.py`.

- [ ] **Step 4: Rodar o auditor e os gates**

Run: `.venv/Scripts/python.exe -m scripts.audit_symbol_packages`, `.venv/Scripts/python.exe -m mypy`, `.venv/Scripts/python.exe -m ruff check .`, `.venv/Scripts/python.exe -m ruff format --check .` e `.venv/Scripts/python.exe scripts/complexity_gate.py src`.
Expected: `errors []` e os gates verdes.

- [ ] **Step 5: Commit** (`feat: casamento de variantes sobre o modelo com paridade no corpus`).

---

## Ondas

| Onda | Tarefas | Por que juntas |
|---|---|---|
| 1 | Tasks 1 e 2 | sem dependência; arquivos disjuntos |
| 2 | Tasks 3, 4 e 5 | só dependem da Task 2; arquivos disjuntos; a fixture de `tests/fixtures/symbol_grammars/` é só leitura |
| 3 | Task 6 | depende das três |

Soma das estimativas: 185 min (~3h05), dentro do "~3h" do orçamento.
