# E05 — Texto por contorno de glifo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** recuperar, sem OCR, o texto desenhado como contorno preenchido, por assinatura de forma contra uma tabela de glifos versionada, e entregá-lo como evidência de texto com origem declarada.

**Architecture:** um leitor puro em `adapters/analysis/drawing_model/` agrupa caminhos preenchidos pequenos em trechos, estima o quadro do trecho (ângulo, altura e linha de base), calcula a assinatura de cada glifo nesse quadro e a resolve numa tabela JSON versionada em `adapters/analysis/data/`. O modelo de desenho (v2) e o analisador PyMuPDF (1.21.0) consomem o mesmo leitor; o analisador só usa os caminhos da página (não o modelo inteiro), com teto de glifos por página. A tabela real nasce de uma rodada de glifos em `tmp/` (agrupar → leitura dupla cega → consolidar → publicar), e um benchmark mede o recall dos campos da ficha no texto recuperado contra o texto nativo do analisador atual.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só nos leitores `pymupdf_*` e nos scripts), pytest, mypy strict, ruff.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md` seção "E05 — Texto por contorno de glifo", com o design `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (decisão 3) e o ADR `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md`. Handoffs das dependências: seções E03 e E04 do roadmap.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o pacote `drawing_model/` continua puro (guardas em `tests/unit/test_architecture.py`); o cliente não importa nada do servidor (`client_artifact_gate`); DTOs seguem `tests/contracts/test_architecture.py`.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`. Nenhuma entidade persistida nova, nenhuma migração SQLite.
- Mudança de comportamento de saída incrementa a versão do extrator (ADR 0006): analisador `pymupdf-nativo` passa de `1.20.0` para `1.21.0`; modelo de desenho passa de `modelo-desenho-v1` para `modelo-desenho-v2`.
- Mudança de API só por campos aditivos, com `docs/api/openapi-v1.json` regenerado (esta etapa não muda a API).
- PDFs reais, recortes, rótulos, renders e leituras nunca entram no Git. A tabela versionada guarda só assinaturas numéricas e caracteres — nenhum recorte, bitmap, PNG, base64, coordenada de página ou nome/hash de folha real.
- Todo comportamento novo tem fixture sintética positiva e negativa. Valores de teste são inventados (nunca identificadores, coordenadas ou valores de folhas reais).
- Leitura de rotulagem é cega: o leitor nunca vê predição nem a leitura do outro leitor.
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos.
- Documentação enxuta: nada de histórico de execução em arquivo versionado; atualize só o que a mudança torna falso (`CLAUDE.md`, contrato de curadoria, agente/skill).
- Nenhuma dependência nova. `fontTools` não é usado; a fixture de fonte livre usa só PyMuPDF.
- Gate: `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` (cobertura mínima 85.01%, complexidade sem rank E/F).
- Rodadas reais leem os PDFs de `C:\Users\Caio\Desktop\repos\ZenyProjectHandler\examples\` (só leitura) e gravam em `C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\` (checkout principal); o worktree não tem `examples/` nem `tmp/` com dados.

## Review Focus

1. Rótulo girado (90°, 30°, ~180° de leitura) e pares sensíveis a rotação (`6`/`9`) → lido corretamente, porque a assinatura é tomada no quadro do trecho, não por glifo isolado (teste na Task 2).
2. O mesmo texto em tamanhos diferentes → mesma leitura com a mesma tabela (teste na Task 2).
3. Glifo desconhecido no meio de um valor (`11-3?0`) → o trecho não é emitido; nunca sai `11-30` (teste na Task 2).
4. Duas entradas da tabela com caracteres diferentes dentro da margem de ambiguidade → nenhum caractere, contado como ambíguo (teste na Task 2).
5. Página hostil com dezenas de milhares de preenchimentos minúsculos ou subcaminho degenerado → teto com diagnóstico, análise segue (teste na Task 3).

## Decisões de desenho

- **Quadro do trecho:** candidatos a glifo = caminhos `preenchimento`/`traco_e_preenchimento` com 1–8 subcaminhos, até 256 itens e maior lado da caixa em `(0.05, 6.0)` pt. Trecho = candidatos consecutivos na ordem de desenho, com a mesma cor de preenchimento e distância entre centros ≤ `1.6 × max(lados das duas caixas)` (mesma regra do legado `pymupdf_glyphs._adjacent`); só trechos com 2–64 glifos são texto. Ângulo = direção da reta de mínimos quadrados pelos centros, orientada do primeiro para o último glifo. Altura `h` = mediana das alturas dos glifos no quadro; linha de base = mediana dos fundos.
- **Assinatura:** subcaminhos achatados (Bézier em 8 passos), girados para o quadro, reamostrados por comprimento de arco em 24 pontos, orientados no sentido anti-horário e expressos em unidades de `h` relativos ao centro da caixa do glifo; subcaminhos ordenados por (−área, centro y, centro x) arredondados a 2 casas. `caixa = (largura/h, altura/h, (fundo − base)/h)`.
- **Distância:** `inf` se o número de subcaminhos difere; senão `max(dif_caixa, dif_contorno)`, com `dif_caixa` = maior diferença absoluta entre os 3 componentes e `dif_contorno` = média, por subcaminho, da distância média ponto a ponto, minimizada sobre deslocamentos cíclicos de −3 a +3 em torno do início canônico (ponto mais próximo do canto superior esquerdo da caixa do subcaminho).
- **Resolução:** candidatos pré-filtrados por número de subcaminhos e por `dif_caixa ≤ tolerancia`; o melhor com `distância ≤ tolerancia` vence, salvo se outro com caractere diferente estiver a `≤ melhor + margem_ambiguidade` (→ ambíguo). Entrada com `caractere: null` é "ignorar" (forma que não é texto): o glifo sai do trecho e o divide, sem diagnóstico.
- **Palavras:** dentro do trecho, lacuna entre caixas consecutivas no quadro `> espaco × h` insere um espaço; `> quebra × h` divide em textos separados. Qualquer glifo desconhecido ou ambíguo anula o texto inteiro em que cairia (sem caractere parcial) e conta no diagnóstico.
- **Parâmetros na tabela, não no código:** `tolerancia` (0.08), `margem_ambiguidade` (0.02), `espaco` (0.38), `quebra` (1.5) vivem no JSON e podem ser calibrados na Task 6 só com evidência do benchmark.
- **Rotação de saída:** graus anti-horários como vistos na página, `atan2(−dy, dx)` em coordenadas com y para baixo, faixa (−180, 180] — a mesma convenção de `rotacao_graus` do texto nativo.
- **OCR como reserva:** a leitura de glifos não conta como texto nativo na decisão do OCR condicional; quando o OCR roda, candidatos OCR cuja caixa cabe dentro de um texto de glifo são descartados (o glifo é exato), e os demais ficam.
- **Critério 3 (recall contra o baseline da E03):** o baseline da E03 é 0/107 porque a ficha predita vem do projeto promovido (D5 pendente para a E07). Nesta etapa o recall mede o **texto recuperado**: cada valor de campo da referência congelada (identificador, poste, cada estrutura, leste e norte) casa com no máximo uma ocorrência de texto na página. Fonte "base" = evidências `TEXTO` nativas do analisador sem OCR (o mesmo extrator nativo do baseline `--native-only` da E03, que não muda nesta etapa); fonte "novo" = nativas + glifo.

## File Structure

- Create `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_signature.py` — achatamento, assinatura e distância (puro).
- Create `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_table.py` — tipos da tabela, resolução, carga/validação estrita e serialização determinística (puro; lê arquivo).
- Create `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_text.py` — trechos, quadro, palavras e leitura (puro).
- Create `src/zeny_project_handler/adapters/analysis/data/__init__.py` e `data/tabela-glifos-v1.json` (vazia na Task 1; real na Task 6).
- Create `src/zeny_project_handler/adapters/analysis/pymupdf_glyph_text.py` — candidatos `TEXTO` de glifo a partir de uma página PyMuPDF.
- Modify `pyproject.toml` (package-data de `adapters.analysis.data`), `drawing_model/model.py`, `drawing_model/cache.py`, `pymupdf_drawing_model.py`, `pymupdf_analyzer.py`.
- Create `tests/fixtures/glyphs/__init__.py` e `tests/fixtures/glyphs/fonte_livre.py` — PDFs sintéticos com o mesmo texto nativo e em contorno.
- Create `scripts/curation_glifos.py` (rodada de glifos) e `scripts/benchmark_texto_ficha.py` (recall de texto por campo da ficha).
- Modify `.claude/agents/curadoria-leitor-visual.md` (modo glifo), `.claude/settings.json` (allow do CLI), `docs/fluxo-curadoria-incremental-simbologia.md` (seção "Rodada de glifos"), `CLAUDE.md`.

---

### Task 1: Assinatura de glifo e tabela versionada

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_signature.py`
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_table.py`
- Create: `src/zeny_project_handler/adapters/analysis/data/__init__.py`, `src/zeny_project_handler/adapters/analysis/data/tabela-glifos-v1.json`
- Modify: `pyproject.toml` (`[tool.setuptools.package-data]`: `"zeny_project_handler.adapters.analysis.data" = ["*.json"]`)
- Test: `tests/unit/test_glyph_signature.py`, `tests/unit/test_glyph_table.py`

**Interfaces:**
- Produces (`glyph_signature.py`):
  - `PONTOS_POR_SUBCAMINHO: Final = 24`, `PASSOS_BEZIER: Final = 8`
  - `achatar_subcaminho(itens: Sequence[ItemCaminho]) -> tuple[Ponto, ...]`
  - `@dataclass(frozen=True, slots=True) class AssinaturaGlifo: subcaminhos: int; caixa: tuple[float, float, float]; contornos: tuple[tuple[Ponto, ...], ...]`
  - `assinatura_glifo(poligonos_no_quadro: Sequence[Sequence[Ponto]], *, altura_linha: float, base_linha: float) -> AssinaturaGlifo | None` — polígonos já girados para o quadro do trecho (y para baixo); `None` para subcaminho com perímetro nulo, coordenada não finita ou `altura_linha <= 0`.
  - `distancia_assinaturas(a: AssinaturaGlifo, b: AssinaturaGlifo) -> float`
- Produces (`glyph_table.py`):
  - `VERSAO_TABELA_GLIFOS: Final = "tabela-glifos-v1"`
  - `@dataclass(frozen=True, slots=True) class EntradaGlifo: id: str; caractere: str | None; assinatura: AssinaturaGlifo`
  - `@dataclass(frozen=True, slots=True) class TabelaGlifos: versao: str; sha256: str; tolerancia: float; margem_ambiguidade: float; espaco: float; quebra: float; glifos: tuple[EntradaGlifo, ...]`
  - `@dataclass(frozen=True, slots=True) class Resolucao: situacao: Literal["reconhecido", "ignorar", "desconhecido", "ambiguo"]; caractere: str | None; distancia: float`
  - `resolver_glifo(tabela: TabelaGlifos, assinatura: AssinaturaGlifo) -> Resolucao`
  - `carregar_tabela_glifos(caminho: Path | None = None) -> TabelaGlifos` (None = `data/tabela-glifos-v1.json` do pacote via `importlib.resources`; `ValueError` se inválida; `sha256` = hash dos bytes do arquivo)
  - `serializar_tabela_glifos(*, tolerancia: float, margem_ambiguidade: float, espaco: float, quebra: float, glifos: Sequence[EntradaGlifo]) -> str` (JSON UTF-8 determinístico, chaves ordenadas, números arredondados a 4 casas, glifos ordenados por `id`)

Formato do JSON (exatamente estas chaves; qualquer outra é inválida):

```json
{"schema_version": 1, "versao": "tabela-glifos-v1", "tolerancia": 0.08, "margem_ambiguidade": 0.02,
 "espaco": 0.38, "quebra": 1.5,
 "glifos": [{"id": "g0001", "caractere": "P",
             "assinatura": {"subcaminhos": 1, "caixa": [0.62, 1.0, 0.0], "contornos": [[[0.1, -0.2], "...24 pares"]]}}]}
```

- [ ] **Step 1: Testes que falham** — em `test_glyph_signature.py`:
  - `test_assinatura_invariante_a_translacao_e_escala`: o mesmo polígono (um "L" de 6 pontos) transladado e escalado ×3, com `altura_linha` escalada junto → `distancia_assinaturas == pytest.approx(0, abs=1e-9)`.
  - `test_inicio_e_sentido_do_contorno_nao_mudam_a_assinatura`: o mesmo polígono começando em outro vértice e em sentido inverso → distância `< 1e-6`.
  - `test_formas_diferentes_ficam_longe`: "L" × "T" → distância `> 0.08`; quantidade de subcaminhos diferente → `math.inf`.
  - `test_variacao_pequena_de_curva_fica_dentro_da_tolerancia`: círculo de 4 Béziers × o mesmo com pontos de controle deslocados 1% do raio → distância `< 0.08`.
  - `test_degenerado_devolve_none`: subcaminho com todos os pontos iguais, coordenada `nan`, `altura_linha=0` → `None`.
  Em `test_glyph_table.py`:
  - `test_tabela_empacotada_vazia_carrega`: `carregar_tabela_glifos()` → `versao == "tabela-glifos-v1"`, `glifos == ()`, `len(sha256) == 64`.
  - `test_ida_e_volta_preserva_a_tabela`: `serializar_tabela_glifos(...)` gravado em `tmp_path` e recarregado → mesmas entradas; serializar duas vezes → bytes idênticos.
  - `test_tabela_invalida_e_recusada` (parametrizado): chave extra (`"png"`), `caractere` com 2 caracteres ou espaço em branco, `caractere: null` válido só como ignorar, número `NaN`/`Infinity`, coordenada com `|v| > 4`, contorno com tamanho ≠ 24, `subcaminhos` ≠ `len(contornos)`, `id` repetido, `schema_version` ≠ 1 → `ValueError`.
  - `test_resolver_reconhece_ignora_desconhece_e_detecta_ambiguidade`: tabela com "P", "R" (assinaturas sintéticas distintas) e uma entrada ignorar → assinatura de "P" → `reconhecido/"P"`; da entrada ignorar → `ignorar/None`; forma longe de todas → `desconhecido`; tabela com "O" e "0" de assinaturas a distância `< margem` → `ambiguo/None`.
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_glyph_signature.py tests/unit/test_glyph_table.py -q` → falha de import.
- [ ] **Step 3: Implementar** os dois módulos com as assinaturas acima e o algoritmo da seção "Decisões de desenho"; criar `data/__init__.py`, o JSON vazio (`glifos: []`, parâmetros iniciais) gerado por `serializar_tabela_glifos`, e a linha de package-data no `pyproject.toml`. Validação estrita: tipos exatos (`bool` não vale como número), floats finitos.
- [ ] **Step 4: Rodar e ver passar** — mesmo comando → PASS; `.venv/Scripts/python.exe -m mypy` e `-m ruff check .` limpos; `tests/unit/test_architecture.py` passa (pacote puro).
- [ ] **Step 5: Commit** — `feat(analise): assinatura de glifo e tabela versionada`.

### Task 2: Leitura de texto por glifo (pura) e fixture de fonte livre

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_text.py`
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py` (expor `caminhos_da_pagina`)
- Create: `tests/fixtures/glyphs/__init__.py`, `tests/fixtures/glyphs/fonte_livre.py`
- Test: `tests/unit/test_glyph_text.py`

**Interfaces:**
- Consumes: Task 1 (`assinatura_glifo`, `achatar_subcaminho`, `resolver_glifo`, `TabelaGlifos`, `EntradaGlifo`).
- Produces (`glyph_text.py`):
  - `LIMITE_GLIFOS_PAGINA: Final = 20_000`
  - `@dataclass(frozen=True, slots=True) class GlifoDoTrecho: indice_caminho: int; caixa: Caixa; assinatura: AssinaturaGlifo | None`
  - `@dataclass(frozen=True, slots=True) class TrechoGlifos: glifos: tuple[GlifoDoTrecho, ...]; rotacao: float; altura: float`
  - `extrair_trechos(caminhos: Sequence[Caminho]) -> tuple[TrechoGlifos, ...]` (glifos na ordem de leitura)
  - `@dataclass(frozen=True, slots=True) class TextoGlifo: texto: str; bbox: Caixa; cantos: tuple[Ponto, Ponto, Ponto, Ponto]; rotacao: float; altura: float; quantidade_glifos: int`
  - `@dataclass(frozen=True, slots=True) class LeituraGlifos: textos: tuple[TextoGlifo, ...]; desconhecidos: int; ambiguos: int; limitada: bool`
  - `ler_texto_glifos(caminhos: Sequence[Caminho], tabela: TabelaGlifos) -> LeituraGlifos` — com mais de `LIMITE_GLIFOS_PAGINA` candidatos devolve `LeituraGlifos((), 0, 0, limitada=True)` sem ler.
- Produces (`pymupdf_drawing_model.py`): `caminhos_da_pagina(pagina: Any) -> tuple[Caminho, ...]` (mesmos caminhos que o modelo já monta; `_caminhos_e_glifos` passa a usá-la).
- Produces (`tests/fixtures/glyphs/fonte_livre.py`):
  - `@dataclass(frozen=True) class LinhaTexto: texto: str; origem: tuple[float, float]; tamanho: float; rotacao: float = 0.0`
  - `pdf_texto_nativo(destino: Path, linhas: Sequence[LinhaTexto]) -> Path` — Helvetica (Base14) com `insert_text`; rotação por `morph=(origem, pymupdf.Matrix(rotacao))`.
  - `pdf_texto_contorno(destino: Path, linhas: Sequence[LinhaTexto]) -> Path` — a mesma página nativa convertida por `page.get_svg_image(text_as_path=True)`; cada `<use>` vira **um** caminho preenchido preto (todos os subcaminhos do glifo num único `Shape.finish`), na ordem do SVG; comandos aceitos `M L H V C Z` (absolutos e relativos); outro comando levanta `ValueError`. Sem texto nativo no resultado.
  - `ALFABETO: Final = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-()/.,="`
  - `tabela_do_alfabeto(tmp: Path) -> TabelaGlifos` — renderiza `ALFABETO` em contorno (tamanho 10, rotação 0, um caractere por glifo, separados por espaço), lê com `extrair_trechos` e rotula cada glifo com o caractere conhecido; serializa com os parâmetros iniciais e recarrega com `carregar_tabela_glifos`.

- [ ] **Step 1: Testes que falham** em `test_glyph_text.py` (todos com `tabela_do_alfabeto`; valores inventados):
  - `test_contorno_le_o_mesmo_texto_que_o_nativo`: linhas `"P7 U4(1) S1N"`, `"11-300"`, `"E=612345 N=7801234"` em tamanho 8 → textos lidos de `caminhos_da_pagina` do PDF em contorno == textos nativos do PDF nativo (`page.get_text("text")` por linha, espaços normalizados).
  - `test_rotulo_girado_le_igual`: as mesmas linhas com rotação 90 e 30 → mesmo texto; `rotacao` do `TextoGlifo` a ±2° de 90/30; linha `"69 96"` a 0° e 180° → `"69 96"` (nunca `"66"`/`"99"`).
  - `test_tamanho_diferente_le_igual`: `"P10 N1"` em tamanhos 5 e 14 → mesmo texto; `altura` proporcional ao tamanho (razão a ±10%).
  - `test_glifo_desconhecido_nao_produz_caractere`: tabela do alfabeto sem a entrada de `"3"` → `"11-300"` não aparece em nenhum texto, nenhum texto contém `"11-"` sozinho, `desconhecidos >= 1`; a linha `"P7"` no mesmo PDF continua lida.
  - `test_glifo_ambiguo_nao_produz_caractere`: tabela com uma cópia da assinatura de `"O"` rotulada `"0"` → texto com `O` não é emitido e `ambiguos >= 1`.
  - `test_formas_isoladas_e_tracos_nao_viram_texto`: um preenchimento pequeno isolado e um traço (`tipo="traco"`) → `textos == ()`, `desconhecidos == 0`.
  - `test_entrada_ignorar_divide_o_trecho`: tabela com a assinatura de `"-"` como `caractere=None` → `"11-300"` vira dois textos `"11"` e `"300"`.
  - `test_limite_de_glifos_por_pagina`: monkeypatch de `LIMITE_GLIFOS_PAGINA` para 3 com 5 glifos → `limitada is True`, `textos == ()`.
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_glyph_text.py -q` → falha de import.
- [ ] **Step 3: Implementar** `glyph_text.py` conforme "Decisões de desenho" (quadro, assinatura no quadro, resolução, espaço/quebra da tabela, anulação do texto com glifo desconhecido/ambíguo), `caminhos_da_pagina` e a fixture. A fixture fecha todo documento PyMuPDF.
- [ ] **Step 4: Rodar e ver passar** — o mesmo comando e `tests/unit/test_pymupdf_drawing_model.py` → PASS; mypy e ruff limpos.
- [ ] **Step 5: Commit** — `feat(analise): leitura de texto por contorno de glifo`.

### Task 3: Texto de glifo no modelo de desenho e no analisador

**Files:**
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/model.py` (`VERSAO_MODELO_DESENHO = "modelo-desenho-v2"`; `TextoModelo.origem: Literal["nativo", "shx", "glifo"]`)
- Modify: `src/zeny_project_handler/adapters/analysis/drawing_model/cache.py` (decodifica `origem="glifo"`)
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py`
- Create: `src/zeny_project_handler/adapters/analysis/pymupdf_glyph_text.py`
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_analyzer.py`
- Test: `tests/unit/test_pymupdf_glyph_text.py`, ajustes em `tests/unit/test_pymupdf_drawing_model.py` e `tests/unit/test_pymupdf_analyzer.py`

**Interfaces:**
- Consumes: Task 2 (`ler_texto_glifos`, `caminhos_da_pagina`, `TextoGlifo`, fixture), Task 1 (`carregar_tabela_glifos`, `TabelaGlifos`).
- Produces:
  - `extrair_modelo_desenho(pdf: Path, tabela: TabelaGlifos | None = None) -> ModeloDesenho` e `obter_modelo_desenho(pdf: Path, cache: JsonDrawingModelCache | None, tabela: TabelaGlifos | None = None) -> ModeloDesenho` (None = tabela do pacote). Textos de glifo entram em `PaginaModelo.textos` com `origem="glifo"`, `fonte=tabela.versao`, `camada=""`. Diagnósticos de página: `"modelo.glifos_desconhecidos"` (havendo desconhecido ou ambíguo) e `"modelo.glifos_limitados"`. A chave de cache usa `versao_leitor = f"pymupdf-{pymupdf.VersionBind}:glifos-{tabela.sha256}"`.
  - `pymupdf_glyph_text.candidatos_texto_glifos(pagina: Any, numero_pagina: int, tabela: TabelaGlifos) -> tuple[tuple[CandidatoEvidenciaDocumento, ...], tuple[DiagnosticoAnalise, ...]]` — `tipo=TEXTO`, `chave_estavel=f"p{n}:texto_glifo:{i}"`, geometria polígono dos `cantos` normalizados como o texto nativo, `conteudo_bruto=texto`, atributos `origem_texto="contorno_glifo"`, `tabela_glifos=<versao>`, `tabela_glifos_sha256`, `quantidade_glifos`, `rotacao_graus` (Decimal), `altura` (Decimal). Diagnósticos `analise.glifos_desconhecidos` (mensagem com as contagens de desconhecidos e ambíguos) e `analise.glifos_limitados`, `extrator="texto_glifos"`.
  - `PyMuPdfDocumentAnalyzer.versao = "1.21.0"`; construtor ganha `tabela_glifos: TabelaGlifos | None = None`; `assinatura_capacidade` inclui `"tabela_glifos": <sha256>` e `"modelo_desenho": VERSAO_MODELO_DESENHO`.

- [ ] **Step 1: Testes que falham:**
  - `test_texto_em_contorno_da_fonte_livre_le_igual_ao_nativo` (critério de aceite 1, em `test_pymupdf_glyph_text.py`): PDF nativo e PDF em contorno das mesmas linhas (as da Task 2, incluindo rotação 90 e 30) analisados por `PyMuPdfDocumentAnalyzer(tabela_glifos=tabela_do_alfabeto(...))` sem OCR → multiconjunto dos `conteudo_bruto` das evidências `TEXTO` com `origem_texto="contorno_glifo"` no PDF em contorno == multiconjunto dos `conteudo_bruto` das evidências `TEXTO` do PDF nativo (espaços normalizados); no PDF nativo nenhuma evidência tem `origem_texto`.
  - `test_glifo_ausente_gera_diagnostico_e_nao_produz_caractere` (critério 2): tabela sem `"3"` → diagnóstico `analise.glifos_desconhecidos` na página e nenhum `conteudo_bruto` contém `"11-"`.
  - `test_pagina_com_glifos_demais_tem_teto`: monkeypatch do limite → diagnóstico `analise.glifos_limitados`, demais evidências da página presentes.
  - `test_leitura_de_glifos_que_falha_nao_derruba_a_pagina`: `candidatos_texto_glifos` levantando exceção → diagnóstico `analise.texto_glifos_falhou` e texto nativo/vetores preservados.
  - `test_glifo_nao_conta_como_texto_nativo_para_o_ocr`: no PDF em contorno, a decisão do OCR condicional recebe `native_characters == 0`.
  - `test_ocr_coberto_por_glifo_e_descartado`: função pura `_descartar_ocr_coberto(ocr, glifos)` com candidatos construídos à mão → OCR inteiramente dentro da caixa de um texto de glifo some; OCR fora fica.
  - `test_versao_e_assinatura_de_capacidade`: `versao == "1.21.0"`; tabelas com `sha256` diferentes → assinaturas diferentes.
  - Em `test_pymupdf_drawing_model.py`: `test_modelo_traz_texto_de_glifo_e_versao_v2` (`origem == "glifo"`, `VERSAO_MODELO_DESENHO == "modelo-desenho-v2"`, ida e volta pelo cache preserva o texto de glifo; tabela diferente → chave de cache diferente).
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_pymupdf_glyph_text.py tests/unit/test_pymupdf_drawing_model.py tests/unit/test_pymupdf_analyzer.py -q`.
- [ ] **Step 3: Implementar.** No `_extract_page`, com `config.extrair_texto`, rodar `candidatos_texto_glifos` por `_safe_extract("texto_glifos", ...)`; `native_characters` conta só `TEXTO` sem `origem_texto`; aplicar `_descartar_ocr_coberto` aos candidatos OCR antes de juntá-los. Testes existentes que mudarem de expectativa por causa do texto de glifo ou do diagnóstico novo precisam de justificativa no relatório; não afrouxe asserções.
- [ ] **Step 4: Rodar e ver passar** — o mesmo comando, depois a suíte inteira `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`, mypy, ruff e `scripts/complexity_gate.py src` → verdes.
- [ ] **Step 5: Commit** — `feat(analise): texto de glifo no modelo de desenho e no analisador 1.21.0`.

### Task 4: Rodada de glifos (CLI) e modo glifo do leitor visual

**Files:**
- Create: `scripts/curation_glifos.py`
- Modify: `.claude/agents/curadoria-leitor-visual.md` (seção "Modo glifo"), `.claude/settings.json` (`"Bash(.venv/Scripts/python.exe -m scripts.curation_glifos *)"`), `docs/fluxo-curadoria-incremental-simbologia.md` (seção "Rodada de glifos"), `CLAUDE.md` (curadoria e arquitetura: tabela de glifos e CLI)
- Test: `tests/unit/test_curation_glifos.py`

**Interfaces:**
- Consumes: Task 2 (`extrair_trechos`, `caminhos_da_pagina`, fixture), Task 1 (`distancia_assinaturas`, `EntradaGlifo`, `serializar_tabela_glifos`).
- Produces: `python -m scripts.curation_glifos <subcomando>`:
  - `agrupar --pdfs DIR --rodada R [--limiar 0.04]` — todos os glifos de trechos de todos os PDFs; agrupamento líder (ordem: frequência decrescente) com `distancia_assinaturas <= limiar`; grava `R/grupos.json` (`id` `c0001…`, `subcaminhos`, `membros`, `familias` {família: n}, `folhas` (contagem), `assinatura` do representante), `R/h1.json` (candidatos, trechos, glifos em trecho, distribuição de subcaminhos, por família) e folhas de contato `R/contato/folha-NNN.png` (até 48 grupos por folha; em cada célula o id, o representante em pé e ampliado e um trecho de contexto em pé com o glifo marcado). Sem nome de PDF nem caminho absoluto nos JSON (folhas identificadas por `sha256[:12]`).
  - `validar --rodada R --leitor {a,b,c} --arquivo F` — formato `curadoria-glifos-v1`: `{"formato": "curadoria-glifos-v1", "leitor": "a", "rotulos": [{"grupo": "c0001", "caractere": "P"} | {"grupo": "c0002", "marca": "ignorar"|"ilegivel"|"composto"|"fragmento"}]}`; A e B cobrem todos os grupos, C cobre exatamente os de `R/divergencias.json`; `caractere` é um único caractere imprimível sem espaço (após NFC). Válido → cópia em `R/leituras/leitura-<leitor>.json`; recusa sobrescrever.
  - `consolidar --rodada R` — A = B → aceito; A ≠ B e C igual a um deles → aceito; senão pendente. Sem C, grava `R/divergencias.json` e `R/contato-divergencias/folha-NNN.png` e para com código 3. Com C (ou sem divergência), grava `R/consolidacao.json` (aceitos, pendentes, contagens de `composto`/`fragmento` por família para H1, concordância A × B).
  - `publicar --rodada R --saida ARQ [--tolerancia 0.08 --margem 0.02 --espaco 0.38 --quebra 1.5]` — tabela com os aceitos (`caractere` → entrada; `ignorar` → `caractere: null`; `ilegivel`/`composto`/`fragmento`/pendente ficam fora), ids `g0001…` na ordem dos grupos, via `serializar_tabela_glifos`.

- [ ] **Step 1: Testes que falham** em `test_curation_glifos.py`, com PDFs sintéticos de `pdf_texto_contorno` (dois PDFs, valores inventados): `agrupar` junta as ocorrências da mesma letra num grupo e separa letras diferentes; os JSON não contêm `tmp_path` nem nome de arquivo; as folhas de contato existem e são PNG; `validar` recusa grupo faltando, caractere com 2 letras, marca desconhecida, leitor C fora das divergências, sobrescrita; `consolidar` com A = B aceita, com A ≠ B sem C sai com 3 e lista a divergência, com C desempata ou deixa pendente; `publicar` gera tabela que `carregar_tabela_glifos` aceita e que, aplicada ao PDF sintético, lê o texto nativo (ida e volta completa).
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_glifos.py -q`.
- [ ] **Step 3: Implementar** o CLI; escrever a seção "Modo glifo" do agente (entrada: rodada e lista de folhas de contato; lê só os PNG de `contato/` ou `contato-divergencias/`; nunca abre `grupos.json`, leituras de outro leitor, consolidação nem tabela; grava o rascunho e roda `validar`; regra para dúvida: `ilegivel`, nunca palpite; `composto` quando a forma tem mais de um caractere, `fragmento` quando é parte de um), a seção do contrato e o allow do CLI; atualizar `CLAUDE.md` (linha de arquitetura do `drawing_model` com a tabela de glifos e linha do CLI na seção de curadoria).
- [ ] **Step 4: Rodar e ver passar** — o mesmo comando, mypy e ruff limpos.
- [ ] **Step 5: Commit** — `feat(curadoria): rodada de glifos com leitura dupla cega`.

### Task 5: Benchmark de recall de texto por campo da ficha

**Files:**
- Create: `scripts/benchmark_texto_ficha.py`
- Test: `tests/unit/test_benchmark_texto_ficha.py`

**Interfaces:**
- Consumes: `scripts/ficha_poste.carregar_ficha` (referência), Task 3 (`PyMuPdfDocumentAnalyzer`, atributo `origem_texto`), `extrair_modelo_desenho` (só para a família).
- Produces:
  - `@dataclass(frozen=True) class TextoMedido: texto: str; centro: tuple[float, float]; origem: Literal["nativo", "glifo"]` (centro normalizado na página exibida, convenção `symbols-e02-v1`)
  - `recall_texto(referencia: Mapping[str, Any], textos: Sequence[TextoMedido]) -> dict[str, dict[str, int]]` — por campo (`identificador`, `poste`, `estruturas`, `coordenada`): `{"total": n, "acertos": k}`. Instâncias: `identificador`, `poste`, cada item de `estruturas`, `str(coordenada["leste"])` e `str(coordenada["norte"])` (inteiros) de cada poste; campo `null` ou listado em `pendentes` do poste não conta. Normalização: NFKC, maiúsculas, espaços colapsados. Uma ocorrência = casamento de `(?<![0-9A-Z])valor(?![0-9A-Z])` no texto normalizado; cada ocorrência serve a no máximo uma instância; atribuição gulosa global por distância crescente entre o centro do texto e o centro da bbox do poste.
  - CLI `python -m scripts.benchmark_texto_ficha --rodada RODADA_E03 --pdfs DIR --saida DIR` — casa PDF e referência por `pdf_sha256`; para cada PDF roda o analisador sem OCR; fonte `base` = `TEXTO` sem `origem_texto`, fonte `novo` = todas as `TEXTO`; grava `texto-ficha.json` e `texto-ficha.md` com recall por campo × fonte, por PDF (id `NNN-sha12` da rodada), por família e total, mais a versão do analisador e o `sha256` da tabela. Sem nome de PDF nem caminho absoluto na saída.
- [ ] **Step 1: Testes que falham:** `recall_texto` com referência sintética de 2 postes que compartilham a estrutura `"N1"` e um só texto `"N1"` → 1 de 2 acertos (ocorrência única); `"P1"` não casa com `"P10"`; `"E=612345"` casa leste `612345`; campo em `pendentes` não conta; CLI ponta a ponta com um PDF nativo e um em contorno da fixture (referência sintética válida para `carregar_ficha`, gravada em `tmp_path` com a estrutura de rodada) → `novo` ≥ `base` e o PDF em contorno tem `base` 0 e `novo` > 0 com a tabela do alfabeto injetada (opção oculta de teste `--tabela ARQ`); saída sem `tmp_path`.
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_texto_ficha.py -q`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar** — mesmo comando, mypy e ruff.
- [ ] **Step 5: Commit** — `feat(benchmark): recall de texto por campo da ficha`.

### Task 6: Tabela real, medição nas 16 folhas e H1

Esta tarefa tem uma parte operacional do orquestrador antes do despacho.

**Parte do orquestrador (antes do desenvolvedor):**
1. `python -m scripts.curation_glifos agrupar --pdfs C:\Users\Caio\Desktop\repos\ZenyProjectHandler\examples --rodada C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\curadoria-glifos\<AAAAMMDD-HHMM>`.
2. Despachar dois `curadoria-leitor-visual` em modo glifo (A e B, em paralelo, cegos um ao outro) com as instruções do modo glifo no próprio despacho; `validar` de cada um.
3. `consolidar`; havendo divergência, despachar o leitor C sobre `contato-divergencias/`, `validar` e `consolidar` de novo.

**Files (desenvolvedor):**
- Modify: `src/zeny_project_handler/adapters/analysis/data/tabela-glifos-v1.json` (gerado por `publicar`)
- Test: `tests/unit/test_glyph_table.py` (tabela empacotada real)

- [ ] **Step 1: Teste que falha** — `test_tabela_empacotada_real_e_valida_e_sem_dados_de_folha`: `carregar_tabela_glifos()` tem ≥ 30 entradas com caractere, cobre os dígitos `0–9`, e o texto do JSON (minúsculo) não contém `pdf`, `png`, `sha`, `base64` nem sequência hexadecimal de 12+ caracteres.
- [ ] **Step 2: Publicar** — `python -m scripts.curation_glifos publicar --rodada <R> --saida src/zeny_project_handler/adapters/analysis/data/tabela-glifos-v1.json`; rodar o teste → PASS.
- [ ] **Step 3: Medir** — `python -m scripts.benchmark_texto_ficha --rodada C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\curadoria-simbologia\20261103-2300-fichas --pdfs C:\Users\Caio\Desktop\repos\ZenyProjectHandler\examples --saida <R>\benchmark`; registrar no relatório o recall por campo × fonte, por família e total, e o tempo da leitura de glifos por folha.
- [ ] **Step 4: Calibrar só com evidência** — se `novo` não superar `base` numa família de contorno (`electric_office_print`, `ghostscript`) por falha de leitura atribuível a `tolerancia`/`espaco`/`quebra`, ajustar só esses parâmetros via `publicar` e medir de novo, registrando antes e depois; se ainda assim não superar, registrar a família como "continua com OCR".
- [ ] **Step 5: Suíte inteira** — `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` verde; testes que mudarem de expectativa com a tabela real precisam de justificativa no relatório.
- [ ] **Step 6: H1 no relatório** — de `h1.json` e `consolidacao.json`: proporção de glifos em trecho, distribuição de subcaminhos e grupos `composto`/`fragmento` por família; conclusão sobre H1.
- [ ] **Step 7: Commit** — `feat(analise): tabela de glifos v1 a partir da rodada de glifos`.
