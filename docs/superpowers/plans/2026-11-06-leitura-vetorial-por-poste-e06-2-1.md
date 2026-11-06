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

- **R-E06.2.1-1, núcleo separado do motor atual:** os limiares do motor atual são copiados como constantes nomeadas nos módulos novos, sem importar `declarative_symbols` (que importa PyMuPDF). A duplicação dura até a E09, que remove o motor antigo. Custo se errado: um ajuste de limiar teria de ser feito nos dois até lá. A validação dos pacotes (`_GRAMMARS`, `carregar_pacotes`) continua no motor antigo, e a E06.3 vai mexer nela ao criar gramáticas novas; os predicados dele não mudam.
- **R-E06.2.1-2, opacidade fora do modelo:** `Estilo` não tem `fill_opacity`, e `_covered_later` precisa dela. Em vez de mudar o modelo e `VERSAO_MODELO_DESENHO`, `PaginaGramatica.translucidos` carrega as posições translúcidas, lidas pelo adaptador. Custo se errado: o cache do modelo não serve às gramáticas sem reler a página, o que a E06.2.2 já não faz (lê da página aberta). O ADR 0016 quer símbolos sobre o modelo em cache: se a E09 quiser isso, terá de pôr `indices_crus` e `translucidos` no modelo, com versão nova. Vai no handoff.
- **R-E06.2.1-3, teto por orçamento de consultas:** um contador determinístico, não tempo de parede nem número de molduras, porque o custo adversarial vem da densidade numa célula. Estourou, o núcleo levanta `TetoGramaticasExcedido`; a E06.2.2 traduz em cobertura `FORA_DOMINIO` com motivo. Tudo ou nada: observação parcial numa página cortada seria uma não detecção falsa. O limite inicial é 2.000.000 consultas; a E06.2.2 mede o gasto real nas 16 folhas. Por que `FORA_DOMINIO` e não `FALHA`: `FALHA` aborta o documento inteiro em `_require_complete`, e uma página hostil não deve derrubar os outros métodos; `FORA_DOMINIO` entra no cache integral e reconcilia como `not_applicable`, o que é honesto para um teto determinístico. Na E06.2.2, o limite entra nos `parametros` do perfil e os módulos novos em `implementation` (`symbol_execution.py:131-142`). **O teto cobre só o núcleo:** `agrupar_candidatos` roda antes dele, ao montar a página, e é quadrático em caixas sobrepostas (R-E06.2.1-9).
- **R-E06.2.1-4, palavras a partir de spans:** `TextoModelo` é um span, e o motor atual lê palavras. O núcleo quebra por espaço e reparte a largura proporcionalmente aos caracteres, só em texto horizontal (rotação 0 ou 180 ± 1°). Rotação diferente, ou texto `shx` (que declara `rotacao=0.0` sem conhecê-la), nunca é repartido: multi-palavra usa a caixa inteira, com `Palavra.inteira=True`. Para o rótulo positivo isso falha fechado. Nas guardas negativas (`_moldura_tem_texto`, palavra sobre o disco), a palavra `inteira` recusa por interseção com a caixa, e não pelo centro, para a guarda não abrir. **Emenda da execução (rulings da Task 4):** nenhum span é repartido. A repartição por caracteres só seria exata em fonte de largura fixa; o testador mediu falsos positivos em Helvetica, e o texto de glifo não é de largura fixa (o leitor escreve um espaço só para qualquer lacuna, e glifo não resolvido vira `""` com a caixa dentro da bbox). Toda palavra usa a caixa do span, com `inteira=True` se o span tem mais que a palavra (várias palavras ou espaços nas pontas). Vale em qualquer rotação e origem, e as frases deste item sobre repartir ficam revogadas. Caixa exata de palavra (`TextoGlifo.glifos`, `words` do PDF) fica para a E06.2.2, se o benchmark mostrar perda de recall. Spans `nativo` horizontais da mesma linha, com lacuna em `[-t, +t]` (`t = max(0.5, 0.2·menor altura)`, folga acima do que o `words` da PyMuPDF junta, sem emular a heurística dele), viram uma só palavra de texto concatenado, caixa unida e `inteira=True`. A folga falha fechado: onde o motor lê duas palavras e a fusão lê uma, o núcleo perde recall e não afirma nada a mais. Rotacionado, `shx` e `glifo` não fundem. Nas guardas, palavra `inteira` recusa por sobreposição fechada (`sobrepoe`), não por interseção.
- **R-E06.2.1-5, ganhos previstos sobre o motor atual:** casam no modelo: moldura de 4 traços separados (polilinha fechada), retângulo de um caminho com 4 `l` (o motor só aceita `re`), `qu` alinhado aos eixos, `Circulo` que não seja 4 `c`, e rótulo em glifo ou SHX. Isso é o objetivo do porte, não quebra de paridade: o corpus sintético não tem esses casos, e cada um ganha fixture própria na Task 6.
- **R-E06.2.1-6, linha terminal por polilinha:** nos caminhos só de traço, a linha terminal do disco vem das pontas das polilinhas abertas; a linha que atravessa o disco em dois segmentos não termina nele (o motor atual aceita). Nos caminhos com traço e preenchimento, vêm os segmentos crus.
- **R-E06.2.1-7, orientação no espaço visual:** o modelo está no espaço da página visual, e o motor atual julga em coordenadas sem rotação. O núcleo julga no visual: o que o usuário vê em pé casa. `PaginaGramatica` não carrega rotação. As 16 folhas têm `/Rotate` 0 (conferido em 2026-11-06), então nada muda no corpus real; em página com `/Rotate`, o núcleo diverge do motor de propósito. A paridade de caixa e índice cru vale em 0, 90, 180 e 270 só nas gramáticas invariantes (rótulo, diagonais, losango e disco de curva), e barra e faixas entram também em 180; triângulo, barra e faixas ganham pares de divergência esperada. A E06.2.2 desfaz a rotação com a página aberta para gerar `pontos_originais`: vai no handoff. Custo se errado: uma folha com `/Rotate` cujo conteúdo cru esteja "em pé" deixaria de casar, o que não existe no corpus.
- **R-E06.2.1-8, falha de fonte não vira não detecção:** `_fonte` engole a exceção da leitura, o que daria página vazia, ou guardas negativas abertas e falso positivo. `contexto_gramaticas` levanta `FonteGramaticaFalhou(codigo)` quando `modelo.diagnosticos` traz `modelo.caminhos_falhou`, `modelo.primitivas_falhou`, `modelo.textos_nativos_falhou`, `modelo.textos_shx_falhou` ou `modelo.glifos_falhou`. `modelo.glifos_limitados` significa texto parcial e guardas abertas: levanta `TetoGramaticasExcedido`, como o teto. `modelo.glifos_desconhecidos` é o resíduo normal da tabela (~1,1% dos glifos) e não bloqueia. `modelo.grupos_falhou` e `modelo.imagens*_falhou` não bloqueiam: o núcleo não os consome. Na E06.2.2, `FonteGramaticaFalhou` vira `FALHA` e o runner aborta (fail-closed, e `_tem_fonte_falha` já trata isso como transitório).
- **R-E06.2.1-9, agrupamento quadrático fica como pré-condição da E06.2.2:** `_unir_proximos` (`groups.py:105-114`) compara cada item com tudo o que já está nas suas células, e o `test_agrupamento_escala_linearmente` só usa círculos espaçados. O teto não o cobre, porque o orçamento nasce depois da leitura. Corrigir sem mudar a saída exige redesenhar a união, e o núcleo nem consome `grupos`; pular os grupos quebraria `test_modelo_igual_ao_de_extrair_modelo_desenho` e a E06.3 (H-A/H-B). Como na D1 da E06.1: `xfail(strict=True)` por contagem nesta etapa, e a correção é pré-condição da E06.2.2 antes de ligar no runner. Custo se errado: nenhum até a ligação, porque nada desta etapa roda no job.
- **R-E06.2.1-10, moldura deduplicada por proveniência:** caminhos distintos continuam candidatos separados, como no motor, porque `_nested_gray_frame` e `_proposal_mark` olham o estilo e o índice de cada desenho. Só se descarta a primitiva cujas `origens` já geraram moldura de mesma forma. A deduplicação por caixa só acontece em `casar_variantes`, como em `_observe_variant`.

## Review Focus

1. Página hostil, com milhares de molduras, segmentos ou palavras sobrepostos numa célula: `TetoGramaticasExcedido` determinístico, com o trabalho do núcleo limitado pelo orçamento e nenhum laço quadrático fora dele. O agrupamento do modelo fica fora, com `xfail` (R-9) (Task 1, Task 2, Task 4, Task 5).
2. Coordenada finita enorme (1e300) ou caixa gigante: a grade não multiplica células nem estoura memória; item fora da página não vira moldura (Task 2).
3. Span com várias palavras, em minúsculas, com espaços nas pontas, rotacionado ou só de espaços: o rótulo casa como no motor atual ou falha fechado, sem exceção (Task 2, Task 4).
4. Página rotacionada ou com CropBox: caixa e índice cru batem com o motor atual nas gramáticas invariantes, porque a reconciliação do runner depende dos dois; a orientação segue R-7 (Task 3, Task 6).
5. Geometria degenerada: polilinha fechada com menos de 4 pontos, círculo de raio 0, moldura de lado 0, `Caminho` sem subcaminho, opacidade `NaN` ou não numérica: sem exceção, e o item não casa (Task 2, Task 3, Task 5).
6. Fonte do modelo que falhou ou texto de glifo limitado: nunca vira não detecção nem guarda aberta (Task 2).

## File Structure

| Arquivo | Responsabilidade | Task |
|---|---|---|
| `src/zeny_project_handler/adapters/analysis/drawing_model/geometry.py` | D1: travessia linear em nó de grau alto | 1 |
| `tests/unit/test_e06_1_etapa_ataque.py` | tirar o `xfail` da D1 | 1 |
| `tests/unit/test_drawing_model_geometry_grau_alto.py` (novo) | ordem e origens preservadas em nó de grau alto; agrupamento quadrático em `xfail` | 1 |
| `src/.../drawing_model/symbol_grammars.py` (novo) | `PaginaGramatica`, orçamento, grade, molduras, palavras, segmentos, contexto | 2 |
| `tests/fixtures/symbol_grammars/__init__.py`, `paginas.py` (novos) | construtores de `PaginaGramatica` sintética | 2 |
| `tests/unit/test_symbol_grammars_contexto.py` (novo) | núcleo | 2 |
| `src/.../pymupdf_drawing_model.py` | `pagina_para_gramaticas`, translúcidos, fim do fallback de `indices_crus` | 3 |
| `tests/unit/test_pymupdf_drawing_model.py`, `test_pymupdf_glyph_text_revisao.py`, `test_pymupdf_glyph_text_ataque.py` | monkeypatch de `_desenhos` sem o fallback | 3 |
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

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/geometry.py` (`_polilinhas_do_estilo`)
- Modify: `tests/unit/test_e06_1_etapa_ataque.py` (remover o `xfail` de `test_fusao_escala_linearmente_com_no_de_grau_alto`)
- Create: `tests/unit/test_drawing_model_geometry_grau_alto.py`

**Interfaces:**
- Produces: `reconstruir_polilinhas` com a mesma assinatura e a mesma saída (ordem inclusive).

- [ ] **Step 1: Tirar o `xfail(strict=True)`** do teste citado e ver falhar nos dois parâmetros (`no-com-muitos-raios`, `mesmo-segmento-pintado-n-vezes`).

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_e06_1_etapa_ataque.py -k grau_alto`
Expected: FAIL (`grande <= 2.5 * pequeno`).

- [ ] **Step 2: Escrever `test_saida_identica_em_no_de_grau_alto`**: uma estrela de 5 raios mais um raio duplicado, em ordem fixa, com a lista exata esperada de `(pontos, fechada, origens)`, valores obtidos antes da mudança rodando o código atual. Mais `test_ciclo_e_segmento_duplo_mantem_a_saida`: quadrado fechado com uma diagonal e um segmento pintado duas vezes, mesma técnica. Tem de passar antes e depois da correção. No mesmo arquivo, `test_agrupamento_escala_linearmente_com_caixas_sobrepostas`, com `xfail(strict=True)` e motivo citando R-E06.2.1-9: conta `groups._caixas_se_encostam` (mesma técnica de `_comparacoes` em `tests/unit/test_drawing_model_groups.py`) em n e 2n círculos concêntricos ou quase sobrepostos, e exige `grande <= 2.5 * pequeno`. Tem de falhar hoje, ou o `strict` reprova.

- [ ] **Step 3: Implementar um cursor por nó** em `_polilinhas_do_estilo`: `proxima` e o `while any(...)` passam a usar um ponteiro por nó que avança sobre `incidentes[n]` pulando as arestas usadas. Aresta usada nunca volta a ser livre, então o ponteiro é monótono e a escolha ("a primeira livre") é a mesma de hoje. Ordem da saída idêntica; `VERSAO_MODELO_DESENHO` não muda.

- [ ] **Step 4: Rodar os testes de geometria**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_e06_1_etapa_ataque.py tests/unit/test_drawing_model_geometry.py tests/unit/test_drawing_model_geometry_adversarial.py tests/unit/test_drawing_model_geometry_grau_alto.py`
Expected: PASS, sem xfail no teste da D1 e com o xfail de R-9.

- [ ] **Step 5: Commit** (`fix: reconstruir_polilinhas linear em no de grau alto`).

### Task 2: Núcleo puro: página, orçamento, grade, molduras, palavras e segmentos

**Estimativa:** 45 min · **Depende de:** nenhuma · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_grammars.py`
- Create: `tests/fixtures/symbol_grammars/__init__.py`, `tests/fixtures/symbol_grammars/paginas.py`
- Create: `tests/unit/test_symbol_grammars_contexto.py`

**Interfaces:**
- Consumes: tipos de `drawing_model/model.py`.
- Produces (todas públicas no módulo, usadas pelas Tasks 3–6):
  - `LIMITE_CONSULTAS_PAGINA: Final = 2_000_000`
  - `class TetoGramaticasExcedido(Exception)`
  - `class FonteGramaticaFalhou(Exception)`, com `codigo: str` (R-8)
  - `@dataclass(frozen=True, slots=True) class PaginaGramatica: modelo: PaginaModelo; indices_crus: tuple[int, ...]; translucidos: frozenset[int]`: `indices_crus[i]` e `translucidos` falam da posição `i` em `modelo.caminhos`; `__post_init__` levanta `ValueError` se `len(indices_crus) != len(modelo.caminhos)`.
  - `class OrcamentoConsultas: __init__(self, limite: int); gastar(self, quantidade: int = 1) -> None` (levanta `TetoGramaticasExcedido`); `gasto: int`.
  - `class GradeEspacial(Generic[T]): __init__(self, itens: Iterable[tuple[Caixa, T]], limites: Caixa, orcamento: OrcamentoConsultas)`; `consultar(self, caixa: Caixa) -> list[T]` em ordem de inserção, sem repetir, gastando 1 do orçamento por item visitado.
  - `@dataclass(frozen=True, slots=True) class Moldura: forma: Literal["retangulo", "elipse", "losango"]; caixa: Caixa; caminho: int`
  - `@dataclass(frozen=True, slots=True) class Segmento: a: Ponto; b: Ponto; caminho: int`
  - `@dataclass(frozen=True, slots=True) class Palavra: texto: str; caixa: Caixa; inteira: bool` (`texto` em maiúsculas, sem espaços nas pontas; `inteira` conforme R-4, só para span de várias palavras não repartido)
  - `@dataclass(frozen=True, slots=True) class ContextoGramatica` com `pagina: PaginaGramatica`, `orcamento`, `molduras: tuple[Moldura, ...]`, `grade_molduras: GradeEspacial[Moldura]`, `grade_palavras: GradeEspacial[Palavra]`, `grade_segmentos: GradeEspacial[Segmento]`, `grade_caminhos: GradeEspacial[int]`, `caixas_caminhos: Mapping[int, Caixa]`.
  - `contexto_gramaticas(pagina: PaginaGramatica, *, limite: int = LIMITE_CONSULTAS_PAGINA) -> ContextoGramatica`
  - Auxiliares públicos `contem(externa: Caixa, interna: Caixa) -> bool`, com borda fechada, `intersecta(a: Caixa, b: Caixa) -> bool`, com comparação estrita (encostar não conta, como `Rect.intersects`), e `ponto_em(caixa: Caixa, ponto: Ponto) -> bool`, com borda fechada. Caixa de lado 0 não `intersecta` nada e não `contem` nada, e pode estar contida. O corpus não tem caso de borda: quem prova essa semântica são os testes de borda das Tasks 2 e 4.

Regras que o implementador não decide:
- **Grade:** célula de 16 pt; só indexa a parte da caixa dentro de `limites` (página com margem de 16 pt), e caixa que cobriria mais de 64 células vai para uma lista `grandes`, percorrida em toda consulta, contando orçamento. Item inteiramente fora é ignorado. Mesmo desenho de `_CamadasDoTexto` em `pymupdf_drawing_model.py`, sem compartilhar código (ele é adaptador).
- **Molduras:** por caminho, em ordem de posição; por subcaminho fechado de 4 `l`: `retangulo` se os lados são alinhados aos eixos (tolerância 0,01 pt), senão `losango` se `_is_diamond` confere (mesma regra do motor: lados ≥ 4, tolerância `max(1, 0,08·min(l, a))`, cada canto do losango com 2 pontas). Um caminho de exatamente 4 `c` e nada mais: `elipse`, com a caixa dos pontos. Depois as primitivas: `Polilinha` fechada de 4 pontos vira `retangulo` ou `losango` (`caminho = origens[0]`) e `Circulo` de raio > 0 vira `elipse`. Dedup por proveniência (R-10): a primitiva cujas `origens` já geraram moldura de mesma forma é descartada; caminhos distintos ficam separados. Moldura com lado 0 ou inteiramente fora da página não entra.
- **Segmentos:** os itens `l` de todo subcaminho que não seja moldura fechada de 4 `l`; mantêm a posição do caminho.
- **Palavras:** `R-E06.2.1-4`. Texto só de espaços ou com `bbox` não finita não gera palavra.
- **Caminhos:** `caixas_caminhos` não traz caminho sem pontos (sem subcaminho).
- **Fontes:** `contexto_gramaticas` aplica R-8 antes de indexar.
- **Contexto:** gasta orçamento ao construir (um por item indexado), para página gigante também estourar ali.

- [ ] **Step 1: Criar a fixture** `tests/fixtures/symbol_grammars/paginas.py`, sem PyMuPDF: `estilo(cor=(0,0,0), preenchimento=None, camada="")`, `linha(a, b, ordem=0, ...)`, `retangulo_traco(caixa, ordem=0, ...)`, `poligono(pontos, ordem=0, preenchimento=None, ...)`, `circulo_bezier(centro, raio, ordem=0, ...)`, `texto(palavra, caixa, origem="nativo", rotacao=0.0)` e `pagina_gramatica(caminhos, textos=(), primitivas=None, largura=300.0, altura=300.0, translucidos=frozenset(), diagnosticos=()) -> PaginaGramatica`: com `primitivas=None`, chama `reconstruir_polilinhas` e `recuperar_circulos_e_arcos`; `indices_crus` é `range` deslocado de 10 (para o teste notar confusão entre posição e índice cru).

- [ ] **Step 2: Escrever os testes**, com estes nomes e asserções:
  - `test_orcamento_estoura_no_limite`: `OrcamentoConsultas(3)`, `gastar(3)` passa, `gastar()` levanta `TetoGramaticasExcedido`.
  - `test_grade_consulta_em_ordem_sem_repetir`: item em duas células sai uma vez; a ordem é a de inserção.
  - `test_grade_ignora_item_fora_da_pagina` e `test_coordenada_enorme_nao_multiplica_celulas`: caixa `(-1e300, -1e300, 1e300, 1e300)` vai para `grandes` e sai na consulta; `len(grade._celulas)` não cresce com ela.
  - `test_molduras_retangulo_elipse_losango`: um de cada, por caminho.
  - `test_moldura_de_quatro_tracos_separados`: 4 `linha` do mesmo estilo → 1 `retangulo`, com `caminho` igual à menor posição.
  - `test_retangulo_de_caminho_e_sua_polilinha_saem_uma_vez` e `test_circulo_de_caminho_com_centro_nao_inteiro_sai_uma_vez`: centro `(100.37, 50.81)`, raio 3,3, sem depender de arredondamento (R-10).
  - `test_traco_e_preenchimento_na_mesma_caixa_sao_duas_molduras`: dois caminhos, duas `Moldura` (R-10).
  - `test_circulo_de_dois_arcos_vira_elipse`.
  - `test_degenerados_nao_viram_moldura`: polilinha fechada de 3 pontos, círculo de raio 0, retângulo de largura 0, item fora da página e `Caminho` sem subcaminho.
  - `test_alinhamento_de_indices_validado`: `PaginaGramatica` com `indices_crus` de outro tamanho levanta `ValueError`.
  - `test_palavras_de_um_span`: `"CT 12"` a x∈[0, 50] → `CT` em x∈[0, 20] e `12` em x∈[30, 50], `"ct"` vira `CT`, `"   "` não gera nada, o texto com `rotacao=45` e duas palavras gera duas palavras com a caixa inteira e `inteira=True`, e o mesmo com `origem="shx"` e `rotacao=0.0`. `bbox` com `nan` ou `inf` não gera nada.
  - `test_segmentos_excluem_moldura_fechada`.
  - `test_semantica_de_borda`: `contem` e `ponto_em` aceitam borda; `intersecta` recusa caixas só encostadas e caixa de lado 0.
  - `test_fonte_que_falhou_levanta` (parametrizado nos 5 códigos de R-8), `test_fonte_que_nao_consumo_nao_bloqueia` (`modelo.grupos_falhou`, `modelo.imagens_falhou`, `modelo.imagens_anotacao_falhou`), `test_glifos_limitados_levanta_teto` e `test_glifos_desconhecidos_nao_bloqueia`.
  - `test_pagina_densa_estoura_o_orcamento_ao_construir`: 5.000 retângulos sobrepostos com `limite=1_000` levantam `TetoGramaticasExcedido`.
  - `test_trabalho_da_consulta_cresce_com_a_densidade_local_e_nao_com_a_pagina`: mesma consulta, 1.000 e 2.000 itens distantes dela: o gasto da consulta não muda.

- [ ] **Step 3: Implementar `symbol_grammars.py`** conforme as interfaces. CC < 31 em tudo.

- [ ] **Step 4: Rodar**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_symbol_grammars_contexto.py`
Expected: PASS.

- [ ] **Step 5: Commit** (`feat: nucleo puro das gramaticas sobre o modelo de desenho`).

### Task 3: Página para as gramáticas a partir da página aberta

**Estimativa:** 25 min · **Depende de:** Task 2 · **Risco:** alto · **Laboratório:** não

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py`
- Modify: `tests/unit/test_pymupdf_drawing_model.py:593-601`, `tests/unit/test_pymupdf_glyph_text_revisao.py:336-343`, `tests/unit/test_pymupdf_glyph_text_ataque.py:352,399-401` (só os `monkeypatch` de `_desenhos`; confira também `tests/unit/test_pymupdf_glyph_text.py:728`)
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

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_pagina_para_gramaticas.py tests/unit/test_pymupdf_drawing_model.py tests/unit/test_pymupdf_drawing_model_adversarial.py tests/unit/test_pymupdf_drawing_model_pagina.py tests/unit/test_pymupdf_drawing_model_pagina_ataque.py tests/unit/test_pymupdf_glyph_text.py tests/unit/test_pymupdf_glyph_text_revisao.py tests/unit/test_pymupdf_glyph_text_ataque.py`
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
| `_triangle_in_frame` | `_triangulo_na_moldura` | caminho de 1 subcaminho com 3 `l`; `Estilo.preenchimento is not None` é "sólido"; orientação no espaço visual (R-7) |
| `_frame_has_text` | `_moldura_tem_texto` | centro da palavra; palavra `inteira` recusa por interseção (R-4) |
| `_diagonal_count` | `_diagonais` | consulta `grade_segmentos` |
| `_nested_rectangles_bar` | `_retangulos_com_barra` | `grade_molduras` e `grade_segmentos`; barra horizontal no espaço visual (R-7) |
| `_diamond_three_dots` | `_losango_tres_pontos` | `grade_molduras` |

- [ ] **Step 1: Escrever os testes**, com `tests/fixtures/symbol_grammars/paginas.py` (só leitura), um por gramática, nos pares positivo/quase-acerto de `tests/fixtures/declarative_symbols/corpus.py`:
  - `test_rotulo_em_retangulo` e `test_rotulo_em_elipse` (positivos); `test_rotulo_errado`, `test_rotulo_fora_da_moldura`, `test_rotulo_que_toca_a_borda_nao_casa` (dentro do inset de 5%), `test_rotulo_minusculo_casa`, `test_rotulo_em_glifo_casa`, `test_rotulo_em_shx_casa`.
  - `test_empty_interior_recusa_marca_preenchida` (≥ 6% da área) e `test_empty_interior_recusa_diagonal_longa` (≥ 55% nos dois eixos); `test_empty_interior_aceita_marca_pequena`.
  - `test_moldura_interna_cinza` e os negativos `sem preenchimento`, `colorida` e `descentrada`; `test_moldura_interna_cinza_pintada_em_dois_caminhos`: traço e depois preenchimento na mesma caixa casa (R-10).
  - `test_empty_interior_com_externa_de_traco_e_preenchimento`: paridade com o motor, que avalia cada caminho como moldura própria (R-10).
  - `test_empty_interior_aceita_linha_longa_que_so_encosta_no_canto`: a caixa da linha só encosta na moldura, e `intersecta` não conta.
  - `test_tres_pontos_com_centro_nao_inteiro`: cada ponto é 1 caminho de 4 `c` mais o seu `Circulo` primitivo, que a proveniência descarta: conta 3 e casa (R-10). `test_tres_pontos_em_dois_caminhos_cada_nao_casa`: cada ponto pintado em 2 caminhos conta 6 e não casa, como no motor.
  - `test_triangulo_vazio_e_solido`, `test_triangulo_de_preenchimento_trocado`, `test_triangulo_pequeno_nao_casa`, `test_triangulo_invertido_nao_casa` (no espaço visual, R-7).
  - `test_duas_diagonais`, `test_uma_diagonal`, `test_diagonais_com_texto` e `test_diagonais_com_span_inteiro_que_cruza_recusa`: palavra `inteira` cujo centro fica fora e cuja caixa cruza a moldura (R-4).
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
- **Bandas:** um caminho cujos subcaminhos são todos retângulos de 4 `l` conta uma banda por subcaminho (o `re` e o `qu` do motor); um caminho só de `l`, com 3 ou mais itens no total, conta uma banda pela caixa. A altura da banda é a do espaço visual (R-7).
- **Disco de curva:** 4 `c` no total e no máximo 1 `l`, somando os subcaminhos.
- **Linha terminal:** `R-E06.2.1-6`. Candidatos: pontas das `Polilinha` abertas de estilo com `cor` não `None` e `min(cor) < 0.9`, mais os `Segmento` de caminhos `traco_e_preenchimento` no mesmo critério. O `Segmento` cujo `caminho` está em `membros` não conta; as polilinhas só vêm de traço puro, e membro tem preenchimento, então essa regra não se aplica a elas. A consulta usa a grade de `pontas_terminais`, construída uma vez por página.
- **Coberto depois:** consulta `grade_caminhos` pela caixa do disco, só posições `> max(membros)`, com `preenchimento` não `None`, fora de `pagina.translucidos`.
- **Palavra sobre o disco:** o centro de uma palavra dentro da caixa do disco recusa, pela `grade_palavras`; palavra `inteira` recusa por interseção (R-4).
- **Orçamento:** `_band_stacks` gasta 1 por pilha aberta visitada e `pontas_terminais` gasta 1 por ponta indexada.

- [ ] **Step 1: Escrever os testes**, com os nomes dos casos de `TERMINAL_DISC_POSITIVES` e `TERMINAL_DISC_NEGATIVES` do corpus:
  - positivos: `test_disco_solido`, `test_disco_dividido` (preenchido + contorno), `test_disco_em_faixas` (12 faixas, retângulos e triângulos alternados);
  - negativos: `test_sem_disco`, `test_verde`, `test_vermelho`, `test_preto`, `test_lilas`, `test_sem_linha`, `test_linha_atravessando`, `test_grande`, `test_com_rotulo`, `test_coberto`, `test_triangulo`;
  - `test_coberto_por_translucido_nao_cobre` (posição em `translucidos`) e `test_coberto_antes_nao_cobre` (ordem anterior);
  - `test_linha_de_dois_segmentos_atravessando_nao_termina` (R-6) e `test_linha_em_ziguezague_termina_no_disco` (último segmento curto; o motor atual perde esse caso);
  - `test_contorno_do_proprio_disco_nao_conta` (segmento de caminho `traco_e_preenchimento` em `membros`); `test_span_inteiro_sobre_o_disco_recusa` (R-4);
  - `test_faixas_com_buraco_nao_viram_disco` e `test_faixa_descentrada_nao_vira_disco`;
  - `test_milhares_de_faixas_estouram_o_orcamento`.

- [ ] **Step 2: Implementar `grammar_disc.py`.** CC < 31; sem `pymupdf`.

- [ ] **Step 3: Rodar**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_grammar_disc.py`
Expected: PASS.

- [ ] **Step 4: Commit** (`feat: gramatica do disco terminal sobre o modelo de desenho`).

### Task 6: Casamento de variantes e paridade com o motor atual

**Estimativa:** 40 min · **Depende de:** Tasks 3, 4 e 5 · **Risco:** alto · **Laboratório:** não

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/symbol_matcher.py`
- Create: `tests/unit/test_symbol_matcher_paridade.py`

**Interfaces:**
- Consumes: `contexto_gramaticas`, `casa_moldura`, `discos_candidatos`, `pontas_terminais`, `casa_disco`. `pagina_para_gramaticas` só nos testes: `symbol_matcher.py` é puro e não a importa.
- Produces:
  - `@dataclass(frozen=True, slots=True) class CasamentoGramatica: pacote: Mapping[str, Any]; variante: Mapping[str, Any]; caixa: Caixa; caminho: int`
  - `casar_variantes(pagina: PaginaGramatica, variantes: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]], *, limite: int = LIMITE_CONSULTAS_PAGINA) -> tuple[CasamentoGramatica, ...]`: na ordem de `variantes` e de `molduras`/`discos`; deduplica por `(id da variante, caixa arredondada a 3 casas)`, como `_observe_variant`; `variantes` são as habilitadas, como `declarative_symbols._enabled` entrega. Só monta os discos se alguma variante for `terminal_disc`. Levanta `TetoGramaticasExcedido` e `FonteGramaticaFalhou`.

- [ ] **Step 1: Escrever os testes**:
  - `test_paridade_de_variantes_por_pagina_no_corpus`: `build_enabled_corpus(tmp_path / "c.pdf")`; para cada página, `{c.variante["id"]}` é igual a `expected_variant_ids` do manifesto e às `template` de `observar_pacotes` na mesma página. Parametrização única, com `pacotes = carregar_pacotes()`, e mensagem de erro com `page`, `variant_id` e `stratum`.
  - `test_caixa_e_indice_cru_batem_com_o_motor_atual` (estratos `positive*`, rotação 0, todas as gramáticas): compara a caixa do casamento normalizada por largura/altura com o envelope de `pontos_normalizados` da observação, a menos de 1e-3, e `indices_crus[c.caminho] == int(obs.primitivas[0].indice)`.
  - `test_rotacao_nas_gramaticas_invariantes` (parametrizado em 90, 180 e 270): `set_rotation` nas páginas `positive*` de `label_in_frame`, `framed_diagonals`, `diamond_three_dots` e `terminal_disc` de curva (`solid`, `split`): mesma comparação. Mais `nested_rectangles_bar` e `positive_stripes` em 180.
  - `test_divergencia_esperada_de_orientacao` (R-7), nos dois sentidos, um par por gramática sensível: o corpus de `triangle_in_frame` com rotação 180 não casa no núcleo e casa no motor; o conteúdo desenhado de modo a ficar em pé com `/Rotate` 90 casa no núcleo e não no motor. Idem barra e faixas em 90.
  - `test_cropbox_nao_desloca_a_caixa`: página do corpus com `set_cropbox`, mesma comparação.
  - `test_ganho_moldura_de_quatro_tracos`: rótulo `CT` em moldura de 4 `draw_line` separados: o núcleo casa e `observar_pacotes` não. E `test_quase_acerto_de_quatro_tracos_com_folga`: um canto aberto em 2 pt: nenhum dos dois casa.
  - `test_ganho_rotulo_em_glifo` e `test_ganho_rotulo_em_shx`: página pura com `texto(..., origem=...)` e moldura casa; sem o texto, não.
  - `test_ganho_retangulo_de_quatro_linhas_em_um_caminho` em página pura (`poligono`), sem comparar com o motor: a PyMuPDF troca 4 linhas fechadas por `qu` ou `re`, e o que chega dela depende de como foi desenhado. `test_ganho_qu_alinhado` e `test_ganho_circulo_de_dois_arcos` (R-5), comparando com o motor. Cada um com o quase-acerto correspondente.
  - `test_pagina_sem_desenhos_nao_casa_nada` e `test_variantes_vazias_nao_montam_discos`.
  - `test_ordem_e_deterministica`: duas execuções, mesma tupla.
  - `test_teto_propaga`: `limite=10` em página densa levanta `TetoGramaticasExcedido`. `test_fonte_falhou_propaga`: `modelo.diagnosticos=("modelo.caminhos_falhou",)` levanta `FonteGramaticaFalhou`.
  - `test_modulos_do_nucleo_nao_importam_pymupdf`: lê com `ast` os 4 módulos novos e reprova import de `pymupdf`, `fitz`, `declarative_symbols` e `pymupdf_drawing_model`.

- [ ] **Step 2: Implementar `symbol_matcher.py`.**

- [ ] **Step 3: Rodar**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_symbol_matcher_paridade.py tests/unit/test_declarative_symbol_packages.py`
Expected: PASS. Divergência de paridade é defeito do porte: corrija em `symbol_grammars.py`, `grammar_frames.py` ou `grammar_disc.py`, nunca no corpus nem em `declarative_symbols.py`. A exceção é a divergência de orientação de R-7, que tem teste próprio.

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

Soma das estimativas: 210 min (~3h30), um pouco acima do "~3h" do orçamento.

**R-E06.2.1-11, não dividir de novo:** as 6 tarefas formam um só porte, e a paridade da Task 6 precisa das outras cinco; cortar aqui daria uma subetapa sem critério de aceite próprio e mais uma rodada de plano e de revisão final, que custam mais do que os ~30 min excedentes. As ondas 1 e 2 correm em paralelo e reduzem o relógio. Custo se errado: o estouro de 4h30 segue a regra do protocolo.

## Fechamento operacional

| Critério de aceite | Evidência |
|---|---|
| Fixtures sintéticas positivas e negativas, paridade de variantes por página | Tasks 2, 4, 5 e 6; `test_paridade_de_variantes_por_pagina_no_corpus` |
| Teste de nó de grau alto da D1 sem `xfail` | Task 1; saída de `pytest -k grau_alto` |
| `scripts.audit_symbol_packages` → 0 erros | Task 6, Step 4 |
| `IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` | o orquestrador roda `cmd.exe //c IniciarTestes.bat` ao fim, antes do `#concluida` |

No handoff, para a E06.2.2:
- `FonteGramaticaFalhou` vira `FALHA`, e `TetoGramaticasExcedido` vira `FORA_DOMINIO` com motivo; o limite vai nos `parametros` do perfil e os módulos novos em `implementation`;
- o `xfail` de R-9 é pré-condição de ligar no runner;
- `pontos_originais` desfaz a rotação com a página aberta (R-7);
- R-2: `indices_crus` e `translucidos` no modelo, se a E09 usar o cache;
- o método passa sempre a tabela de glifos: sem ela, o texto de glifo some e as guardas negativas abrem;
- decidir o tratamento da falha determinística de fonte: `modelo.textos_shx_falhou` é superfície nova, porque o motor atual não lê anotações, e uma anotação estranha abortaria a composição do documento em toda nova tentativa. R-8 trata falha de fonte como transitória, e R-3 não quer que página hostil derrube os outros métodos.

## Revisão de arquitetura

- **Veredito:** aprovado com notas.
- **Rodadas:** 1.
- **Modelo:** opus.
- **Notas Menores:** N1–N5 da rodada 1 aplicadas ao plano (semântica de `intersecta` e `ponto_em`, teste de ganho em página pura, decisão da falha determinística no handoff, R-11 com a Task 6 em 40 min, ambiguidade dos 3 pontos). Não verificado pelo revisor: nada executado; semântica de `fz_is_point_inside_rect` em C; custo real do teto e de `glifos_limitados` em folhas reais (medição da E06.2.2).
