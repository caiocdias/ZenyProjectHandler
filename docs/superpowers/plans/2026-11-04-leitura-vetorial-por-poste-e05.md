# E05 — Texto por contorno de glifo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** recuperar, sem OCR, o texto desenhado como contorno preenchido, por assinatura de forma contra uma tabela de glifos versionada, e entregá-lo como evidência de texto com origem declarada.

**Architecture:** um leitor puro em `adapters/analysis/drawing_model/` agrupa caminhos preenchidos pequenos em trechos, estima o quadro do trecho (ângulo, altura e linha de base), calcula a assinatura de cada glifo nesse quadro e a resolve numa tabela JSON versionada em `adapters/analysis/data/`. A tabela real nasce de uma rodada de glifos em `tmp/` (agrupar → leitura dupla cega → consolidar → publicar). O modelo de desenho (v2) e o analisador PyMuPDF (1.21.0) consomem o mesmo leitor; o analisador usa só os caminhos da página (não o modelo inteiro), com teto de glifos, falha isolada por página e tabela indisponível tratada como o OCR indisponível (ADR 0004 §7). Um benchmark mede o recall dos campos da ficha no texto recuperado e conta leituras erradas afirmadas.

**Tech Stack:** Python 3.11–3.13, PyMuPDF (só nos leitores `pymupdf_*` e nos scripts), pytest, mypy strict, ruff.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md` seção "E05 — Texto por contorno de glifo", com o design `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (decisão 3) e o ADR `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md`. Handoffs das dependências: seções E03 e E04 do roadmap.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o pacote `drawing_model/` continua puro (guardas em `tests/unit/test_architecture.py`); o cliente não importa nada do servidor (`client_artifact_gate`); DTOs seguem `tests/contracts/test_architecture.py`.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`. Nenhuma entidade persistida nova, nenhuma migração SQLite. O interpretador não muda nesta etapa.
- Mudança de comportamento de saída incrementa a versão do extrator (ADR 0006): analisador `pymupdf-nativo` passa de `1.20.0` para `1.21.0`; modelo de desenho passa de `modelo-desenho-v1` para `modelo-desenho-v2`.
- Mudança de API só por campos aditivos, com `docs/api/openapi-v1.json` regenerado (esta etapa não muda a API).
- PDFs reais, recortes, rótulos, renders e leituras nunca entram no Git. A tabela versionada guarda só assinaturas numéricas e caracteres — nenhum recorte, bitmap, PNG, base64, coordenada de página ou nome/hash de folha real.
- Todo comportamento novo tem fixture sintética positiva e negativa. Valores de teste são inventados (nunca identificadores, coordenadas ou valores de folhas reais).
- Leitura de rotulagem é cega: o leitor nunca vê predição, nem a leitura do outro leitor, nem a consolidação. Folhas reservadas para avaliação (H4) nunca entram na rodada de glifos.
- Testes injetam a tabela explicitamente; só o teste da tabela empacotada lê a tabela do pacote (o gate não depende de dado curado).
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos.
- Documentação enxuta: nada de histórico de execução em arquivo versionado; atualize só o que a mudança torna falso (`CLAUDE.md`, contrato de curadoria, agente).
- Nenhuma dependência nova; a fixture de fonte livre usa só PyMuPDF.
- Gate: `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` (cobertura mínima 85.01%, complexidade sem rank E/F).
- Rodadas reais leem os PDFs de `C:\Users\Caio\Desktop\repos\ZenyProjectHandler\examples\` (só leitura) e gravam em `C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\curadoria-simbologia\<AAAAMMDD-HHMM>-glifos\` (checkout principal).

## Revisão de arquitetura

- **Veredito:** aprovado com notas (rodada 2), pelo `revisor-arquitetura` no modelo opus.
- **Rodadas:** 2. Rodada 0 bloqueou (C1 tabela fora do wheel do servidor; I1–I6: cor e interpretação, descarte do OCR, geometria/rotação com /Rotate, tamanho das fixtures, erro de rótulo, critério 3). Rodada 1 bloqueou (N1: concordância OCR × glifo sem granularidade). Rodada 2 aprovou.
- **Notas Menores:** N5 (OCR concordante cobrindo um glifo só em parte) e N6 (token do motor de contornos em fragmento) foram incorporados à regra de cobertura e ao teste `test_cobertura_ocr_x_glifo`. Ressalvas do revisor: não construiu o wheel nem rodou testes; aceitou o histograma da sonda e a ausência de /Rotate nas 16 folhas como relatados. Observação lateral levada ao usuário: o `server/pyproject.toml` não listava `symbol_packages` (pode significar que a imagem atual está sem os pacotes declarativos; conferido na Task 1).

## Review Focus

1. Rótulo girado (90°, 30°, leitura invertida) e pares sensíveis a rotação (`6`/`9`), inclusive em página com `/Rotate 90` → lido certo e posicionado igual ao nativo (testes nas Tasks 2 e 4).
2. O mesmo texto em tamanhos diferentes → mesma leitura com a mesma tabela (Task 2).
3. Glifo desconhecido no meio de um valor (`11-3?0`) → o trecho não é emitido; nunca sai `11-30` (Task 2).
4. Glifo lido errado que concorda com a tabela dentro da tolerância → não apaga o OCR que discorda; os dois ficam, com diagnóstico (Task 4); leituras erradas afirmadas são contadas no benchmark (Task 5).
5. Página hostil (dezenas de milhares de preenchimentos minúsculos, cor com aridade ≠ 3, subcaminho degenerado) ou tabela ausente no container → teto/diagnóstico, a análise segue (Tasks 1 e 4).

## Decisões de desenho

- **Candidatos e trechos:** candidato a glifo = caminho `preenchimento`/`traco_e_preenchimento` com 1–8 subcaminhos, até 256 itens e maior lado da caixa em `(0.05, 7.0)` pt (a sonda das 9 folhas de contorno tem 1.260 formas entre 5,5 e 6,5 pt e só 46 entre 6,5 e 7,5). Trecho = candidatos consecutivos na ordem de desenho, com a mesma cor de preenchimento e distância entre centros ≤ `1.6 × max(lados das duas caixas)` (regra do legado `pymupdf_glyphs._adjacent`); só trechos com 2–64 glifos são texto. Ângulo = reta de mínimos quadrados pelos centros, orientada do primeiro para o último glifo. Altura `h` = mediana das alturas dos glifos no quadro; linha de base = mediana dos fundos.
- **Assinatura:** subcaminhos achatados (Bézier em 8 passos), girados para o quadro, reamostrados por comprimento de arco em 24 pontos, orientados no sentido anti-horário e expressos em unidades de `h` relativos ao centro da caixa do glifo; subcaminhos ordenados por (−área, centro y, centro x) arredondados a 2 casas. `caixa = (largura/h, altura/h, (fundo − base)/h)`.
- **Distância:** `inf` se o número de subcaminhos difere; senão `max(dif_caixa, dif_contorno)`, com `dif_caixa` = maior diferença absoluta entre os 3 componentes e `dif_contorno` = média, por subcaminho, da distância média ponto a ponto, minimizada sobre deslocamentos cíclicos de −3 a +3 em torno do início canônico (ponto mais próximo do canto superior esquerdo da caixa do subcaminho).
- **Resolução:** candidatos pré-filtrados por número de subcaminhos e `dif_caixa ≤ tolerancia`; o melhor com `distância ≤ tolerancia` vence, salvo se outro com caractere diferente estiver a `≤ melhor + margem_ambiguidade` (→ ambíguo). Entrada com `caractere: null` é "ignorar" (forma que não é texto): o glifo sai do trecho e o divide, sem diagnóstico.
- **Palavras:** lacuna entre caixas consecutivas no quadro `> espaco × h` insere um espaço; `> quebra × h` divide em textos separados. Glifo desconhecido ou ambíguo anula o texto inteiro em que cairia e conta no diagnóstico.
- **Parâmetros na tabela:** `tolerancia` (0.08), `margem_ambiguidade` (0.02), `espaco` (0.38), `quebra` (1.5) vivem no JSON e só mudam na Task 6 com evidência do benchmark.
- **Tabela única para todas as famílias:** a identidade da forma já separa fontes (glifos de fontes diferentes viram entradas diferentes). Alternativa descartada: tabela por família escolhida pelo perfil — o analisador não calcula a família por página, e as 9 folhas de contorno (Electric Office e Ghostscript) usam o mesmo desenhador de rótulos. A leitura roda em toda família; a sobreposição com texto nativo segue a regra de cobertura abaixo.
- **Versão da tabela:** `versao` (`tabela-glifos-v1`) é a versão do formato; a identidade do conteúdo é o `sha256` dos bytes, que entra na assinatura de capacidade, na chave do cache do modelo e no atributo da evidência. `TextoModelo.fonte` de glifo = `f"{versao}:{sha256[:12]}"`.
- **Tabela indisponível:** o analisador recebe `tabela_glifos: TabelaGlifos | Literal["pacote"] | None = None`. `None` desativa a leitura (assinatura `"tabela_glifos": "desativada"`); `"pacote"` carrega a tabela empacotada na primeira análise e, se ela faltar ou for inválida, desativa a leitura com o diagnóstico `analise.tabela_glifos_indisponivel` e a assinatura `"indisponivel:<codigo>"`, sem derrubar a análise. A composição do servidor usa `"pacote"`.
- **Geometria e rotação:** `caminhos_da_pagina` devolve coordenadas da página visual; a geometria da evidência é cada canto dividido por `page.rect.width`/`height` (sem `_normalized_points`, que giraria de novo). `TextoGlifo.rotacao` usa a convenção do modelo (graus horários visuais em [0, 360), como `TextoModelo.rotacao` nativo). A evidência grava `rotacao_graus` na convenção do texto nativo: a direção do trecho levada ao espaço não girado pela parte linear de `page.derotation_matrix` e `atan2(−dy, dx)`, arredondado a 6 casas.
- **Cor:** o trecho tem uma cor de preenchimento só; a evidência leva `cor` no formato do OCR de contornos (`_pdf_color`), para a interpretação inferir a situação pela cor como no texto nativo (ADR 0006).
- **Ângulo de rótulo:** `span_rules._reliable_label_angle` só confia no ângulo de motores OCR; o texto de glifo, como o nativo, não é fonte de ângulo confiável. Onde o OCR de contornos concorda, ele é mantido (regra de cobertura), então o interpretador não perde a orientação no container; onde só há glifo (sem OCR), a associação de vão fica como hoje sem OCR. Registrado como decisão; o interpretador não muda nesta etapa.
- **OCR como reserva, comparação no nível do glifo:** a leitura de glifos não conta como texto nativo na decisão do OCR condicional. Quando o OCR roda, para cada candidato OCR que sobrepõe textos de glifo (semântica de `_has_glyph_reading` com `allow_fragment=True`), o texto esperado é a concatenação, na ordem de leitura e sem espaços, dos glifos (`TextoGlifo.glifos`) cujo centro cai na caixa do OCR; o OCR é **concordante** se esse texto é igual ao seu texto normalizado sem espaços, e **divergente** caso contrário (os dois ficam e `analise.glifo_ocr_divergente` conta os casos). Depois: texto de glifo com **todos** os glifos cobertos por OCR concordante sai (o OCR cobre, e o interpretador vê exatamente o que via antes, inclusive as regras de orientação do motor `tesseract-contornos-vetoriais`); senão o texto de glifo fica e os OCR concordantes dentro dele saem (fragmentos que ele já contém), exceto o token do motor `tesseract-contornos-vetoriais`, que nunca é descartado; um OCR concordante que cobre um texto de glifo só em parte, sem estar dentro dele, fica junto com esse glifo (duplicação parcial aceita). A mesma regra de cobertura vale contra `TEXTO` nativo concordante (o glifo totalmente coberto sai; sem diagnóstico).
- **Encaixes:** a leitura de glifos roda num extrator próprio que devolve candidatos e diagnósticos (adaptar `_safe_extract` ou envolvê-lo); `extract_revision_appearances` e `reconcile_readings` do complementar recebem os candidatos **sem** o texto de glifo (comportamento preservado), com teste. `caminhos_da_pagina` tolera desenho malformado por item (cor de aridade ≠ 3 vira `None`; desenho com coordenada não finita é descartado), sem esvaziar a página.
- **Critério 3 (recall contra o baseline da E03):** o baseline da E03 é 0/107 porque a ficha predita vem do projeto promovido (D5 adiada para a E07). Aqui o recall mede o **texto recuperado**: cada valor de campo da referência congelada casa com no máximo uma ocorrência de texto. Fonte "base" = `TEXTO` nativo do analisador sem OCR (o mesmo extrator nativo do baseline `--native-only` da E03); fonte "novo" = nativo + glifo. A comparação com o OCR fica para a E09 (OCR português só na imagem Docker). A medição é dentro da amostra (a tabela nasce das mesmas 16 folhas). Essa leitura do critério vai para "Decisões para o usuário".
- **Registros para o usuário (handoff):** a leitura do critério 3, o erro de rótulo sem amostra humana, o allow novo do CLI em `.claude/settings.json`, o modo glifo do `curadoria-leitor-visual` e a inclusão de `symbol_packages` no wheel do servidor (correção de ausência anterior à etapa, com efeito visível em produção) vão para "Decisões para o usuário".
- **Erro de rótulo:** não há amostra humana nesta etapa; a taxa de leitura errada é medida contra as referências congeladas da E03 (que tiveram amostra humana): no benchmark, texto com padrão de campo perto do poste, a distância de edição 1–2 do valor de referência e diferente dele, conta como "erro afirmado". Vai para "Decisões para o usuário".

## File Structure

- Create `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_signature.py` — achatamento, assinatura e distância (puro).
- Create `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_table.py` — tipos, resolução, carga/validação estrita e serialização (puro; lê arquivo).
- Create `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_text.py` — trechos, quadro, palavras e leitura (puro).
- Create `src/zeny_project_handler/adapters/analysis/data/__init__.py` e `data/tabela-glifos-v1.json`.
- Create `src/zeny_project_handler/adapters/analysis/pymupdf_glyph_text.py` — candidatos `TEXTO` de glifo de uma página PyMuPDF.
- Modify `pyproject.toml` e `server/pyproject.toml` (package-data), `drawing_model/model.py`, `drawing_model/cache.py`, `pymupdf_drawing_model.py`, `pymupdf_analyzer.py`, `src/zeny_project_handler_server/composition.py`, `scripts/drawing_model_dxf.py` e `scripts/drawing_model_report.py` (passam a tabela do pacote).
- Create `tests/fixtures/glyphs/__init__.py`, `tests/fixtures/glyphs/fonte_livre.py`.
- Create `scripts/curation_glifos.py` e `scripts/benchmark_texto_ficha.py`.
- Modify `.claude/agents/curadoria-leitor-visual.md`, `.claude/settings.json`, `docs/fluxo-curadoria-incremental-simbologia.md`, `CLAUDE.md`.

---

### Task 1: Assinatura de glifo, tabela versionada e empacotamento

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_signature.py`, `.../drawing_model/glyph_table.py`, `src/zeny_project_handler/adapters/analysis/data/__init__.py`, `.../data/tabela-glifos-v1.json`
- Modify: `pyproject.toml` e `server/pyproject.toml` (`[tool.setuptools.package-data]`)
- Test: `tests/unit/test_glyph_signature.py`, `tests/unit/test_glyph_table.py`, `tests/unit/test_package_data.py`

**Interfaces:**
- Produces (`glyph_signature.py`): `PONTOS_POR_SUBCAMINHO: Final = 24`, `PASSOS_BEZIER: Final = 8`; `achatar_subcaminho(itens: Sequence[ItemCaminho]) -> tuple[Ponto, ...]`; `@dataclass(frozen=True, slots=True) class AssinaturaGlifo: subcaminhos: int; caixa: tuple[float, float, float]; contornos: tuple[tuple[Ponto, ...], ...]`; `assinatura_glifo(poligonos_no_quadro: Sequence[Sequence[Ponto]], *, altura_linha: float, base_linha: float) -> AssinaturaGlifo | None` (polígonos já no quadro do trecho, y para baixo; `None` para perímetro nulo, coordenada não finita ou `altura_linha <= 0`); `distancia_assinaturas(a: AssinaturaGlifo, b: AssinaturaGlifo) -> float`.
- Produces (`glyph_table.py`): `VERSAO_TABELA_GLIFOS: Final = "tabela-glifos-v1"`; `EntradaGlifo(id: str, caractere: str | None, assinatura: AssinaturaGlifo)`; `TabelaGlifos(versao: str, sha256: str, tolerancia: float, margem_ambiguidade: float, espaco: float, quebra: float, glifos: tuple[EntradaGlifo, ...])`; `Resolucao(situacao: Literal["reconhecido", "ignorar", "desconhecido", "ambiguo"], caractere: str | None, distancia: float)` (todas `@dataclass(frozen=True, slots=True)`); `resolver_glifo(tabela: TabelaGlifos, assinatura: AssinaturaGlifo) -> Resolucao`; `carregar_tabela_glifos(caminho: Path | None = None) -> TabelaGlifos` (None = JSON do pacote via `importlib.resources`; `ValueError` se ausente ou inválida; `sha256` dos bytes); `serializar_tabela_glifos(*, tolerancia: float, margem_ambiguidade: float, espaco: float, quebra: float, glifos: Sequence[EntradaGlifo]) -> str` (JSON determinístico, chaves ordenadas, números a 4 casas, glifos por `id`).

Formato do JSON (exatamente estas chaves; qualquer outra é inválida):

```json
{"schema_version": 1, "versao": "tabela-glifos-v1", "tolerancia": 0.08, "margem_ambiguidade": 0.02,
 "espaco": 0.38, "quebra": 1.5,
 "glifos": [{"id": "g0001", "caractere": "P",
             "assinatura": {"subcaminhos": 1, "caixa": [0.62, 1.0, 0.0], "contornos": [[[0.1, -0.2], "...24 pares"]]}}]}
```

- [ ] **Step 1: Testes que falham** — `test_glyph_signature.py`:
  - `test_assinatura_invariante_a_translacao_e_escala`: o mesmo "L" de 6 pontos transladado e escalado ×3 (com `altura_linha` ×3) → distância `approx(0, abs=1e-9)`.
  - `test_inicio_e_sentido_do_contorno_nao_mudam_a_assinatura`: outro vértice inicial e sentido inverso → distância `< 1e-6`.
  - `test_formas_diferentes_ficam_longe`: "L" × "T" → `> 0.08`; número de subcaminhos diferente → `math.inf`.
  - `test_variacao_pequena_de_curva_fica_dentro_da_tolerancia`: círculo de 4 Béziers × o mesmo com controles deslocados 1% do raio → `< 0.08`.
  - `test_degenerado_devolve_none`: pontos todos iguais, `nan`, `altura_linha=0` → `None`.
  `test_glyph_table.py`:
  - `test_tabela_empacotada_vazia_carrega`: `carregar_tabela_glifos()` → `versao == "tabela-glifos-v1"`, `glifos == ()`, `len(sha256) == 64` (este teste é substituído na Task 6).
  - `test_ida_e_volta_preserva_a_tabela`; serializar duas vezes → bytes idênticos.
  - `test_tabela_invalida_e_recusada` (parametrizado): chave extra (`"png"`), `caractere` com 2 caracteres ou espaço, `NaN`/`Infinity`, coordenada com `|v| > 4`, contorno ≠ 24 pontos, `subcaminhos` ≠ `len(contornos)`, `id` repetido, `schema_version` ≠ 1, `bool` no lugar de número, arquivo inexistente → `ValueError`.
  - `test_resolver_reconhece_ignora_desconhece_e_detecta_ambiguidade` (tabela sintética com "P", "R", uma entrada ignorar, e "O"/"0" a distância `< margem`).
  `test_package_data.py`:
  - `test_package_data_do_servidor_cobre_o_da_raiz`: lê os dois `pyproject.toml` com `tomllib`; toda chave `zeny_project_handler.*` (não `_client`) do `package-data` da raiz existe no do servidor com os mesmos padrões; inclui `zeny_project_handler.adapters.analysis.data` e `zeny_project_handler.adapters.analysis.symbol_packages`.
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_glyph_signature.py tests/unit/test_glyph_table.py tests/unit/test_package_data.py -q`.
- [ ] **Step 3: Implementar** os módulos (algoritmo em "Decisões de desenho"), `data/__init__.py`, o JSON vazio gerado por `serializar_tabela_glifos` com os parâmetros iniciais, e as entradas de package-data nos dois `pyproject.toml` (no do servidor, `adapters.analysis.data` e o `symbol_packages` que já faltava).
- [ ] **Step 4: Rodar e ver passar** — o mesmo comando; mypy, ruff e `tests/unit/test_architecture.py` limpos. Conferir o conteúdo real do wheel do servidor: `.venv/Scripts/python.exe -m pip wheel --no-deps --no-build-isolation --wheel-dir C:/tmp/zph-wheel-e05 ./server` e listar o zip — precisa conter `zeny_project_handler/adapters/analysis/data/tabela-glifos-v1.json` e os `symbol_packages/*.json`; registrar a listagem no relatório (o diretório fica fora do repositório; apague-o depois).
- [ ] **Step 5: Commit** — `feat(analise): assinatura de glifo e tabela versionada`.

### Task 2: Leitura de texto por glifo (pura) e fixture de fonte livre

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/glyph_text.py`, `tests/fixtures/glyphs/__init__.py`, `tests/fixtures/glyphs/fonte_livre.py`
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py` (`caminhos_da_pagina` com tolerância por desenho)
- Test: `tests/unit/test_glyph_text.py`, `tests/unit/test_pymupdf_drawing_model_adversarial.py`

**Interfaces:**
- Consumes: Task 1.
- Produces (`glyph_text.py`): `LIMITE_GLIFOS_PAGINA: Final = 20_000`, `LADO_MAXIMO_GLIFO: Final = 7.0`; `GlifoDoTrecho(indice_caminho: int, caixa: Caixa, assinatura: AssinaturaGlifo | None)`; `TrechoGlifos(glifos: tuple[GlifoDoTrecho, ...], rotacao: float, altura: float, cor: Cor | None)`; `extrair_trechos(caminhos: Sequence[Caminho]) -> tuple[TrechoGlifos, ...]` (glifos na ordem de leitura; `rotacao` na convenção do modelo); `TextoGlifo(texto: str, bbox: Caixa, cantos: tuple[Ponto, Ponto, Ponto, Ponto], rotacao: float, altura: float, quantidade_glifos: int, cor: Cor | None, glifos: tuple[tuple[str, Caixa], ...])` (`glifos` = caractere e caixa visual de cada glifo, na ordem de leitura, sem os espaços); `LeituraGlifos(textos: tuple[TextoGlifo, ...], desconhecidos: int, ambiguos: int, limitada: bool)` (todas `@dataclass(frozen=True, slots=True)`); `ler_texto_glifos(caminhos: Sequence[Caminho], tabela: TabelaGlifos) -> LeituraGlifos` (acima de `LIMITE_GLIFOS_PAGINA` candidatos → `LeituraGlifos((), 0, 0, limitada=True)`). `cantos` em coordenadas visuais da página, na ordem início-base, fim-base, fim-topo, início-topo.
- Produces (`pymupdf_drawing_model.py`): `caminhos_da_pagina(pagina: Any) -> tuple[Caminho, ...]`.
- Produces (fixture): `LinhaTexto(texto: str, origem: tuple[float, float], tamanho: float, rotacao: float = 0.0, cor: tuple[float, float, float] = (0, 0, 0))`; `pdf_texto_nativo(destino: Path, linhas: Sequence[LinhaTexto], *, rotacao_pagina: int = 0) -> Path` (Helvetica Base14 por `insert_text`; rotação por `morph=(origem, pymupdf.Matrix(rotacao))`; `/Rotate` por `set_rotation`); `pdf_texto_contorno(destino, linhas, *, rotacao_pagina: int = 0) -> Path` (a página nativa convertida por `get_svg_image(text_as_path=True)`; cada `<use>` vira **um** caminho preenchido na cor da linha, todos os subcaminhos num único `Shape.finish`, na ordem do SVG; comandos `M L H V C Z` absolutos e relativos; outro comando → `ValueError`; sem texto nativo); `ALFABETO: Final = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-()/.,="`; `tabela_do_alfabeto(tmp: Path) -> TabelaGlifos` (alfabeto em contorno, tamanho 5, rotação 0, caracteres separados por espaço; cada glifo de `extrair_trechos` rotulado com o caractere conhecido; serializa e recarrega).
- Tamanhos das fixtures: 3 a 6 pt (com `LADO_MAXIMO_GLIFO = 7.0`, "(" a 6 pt mede ~5,6 pt).

- [ ] **Step 1: Testes que falham** em `test_glyph_text.py` (tabela do alfabeto; valores inventados):
  - `test_contorno_le_o_mesmo_texto_que_o_nativo`: `"P7 U4(1) S1N"`, `"11-300"`, `"E=612345 N=7801234"` em 5 pt → textos lidos == textos nativos por linha (espaços normalizados).
  - `test_rotulo_girado_le_igual`: as mesmas linhas a 90 e 30 → mesmo texto; `rotacao` na convenção do modelo igual à do `TextoModelo` nativo da mesma linha (±2°); `"69 96"` a 0° e 180° → `"69 96"`.
  - `test_tamanho_diferente_le_igual`: `"P10 N1"` em 3 e 6 pt → mesmo texto; razão das `altura` = 2 (±10%).
  - `test_glifo_desconhecido_nao_produz_caractere`: tabela sem `"3"` → nenhum texto contém `"11-"`, `desconhecidos >= 1`; `"P7"` continua lido.
  - `test_glifo_ambiguo_nao_produz_caractere`: cópia da assinatura de `"O"` rotulada `"0"` → texto com `O` não sai, `ambiguos >= 1`.
  - `test_formas_isoladas_e_tracos_nao_viram_texto`; `test_glifo_maior_que_o_lado_maximo_nao_e_candidato` (texto a 12 pt → `textos == ()`).
  - `test_entrada_ignorar_divide_o_trecho`: `"-"` como `caractere=None` → `"11"` e `"300"`.
  - `test_cor_do_trecho`: linha em verde → `TextoGlifo.cor == (0, 1, 0)` (±0.01).
  - `test_limite_de_glifos_por_pagina` (monkeypatch para 3 com 5 glifos → `limitada`).
  Em `test_pymupdf_drawing_model_adversarial.py`: `test_desenho_com_cor_de_aridade_errada_nao_esvazia_a_pagina` (monkeypatch de `get_drawings` com um desenho de `fill` de 4 componentes e outro válido → o válido continua em `caminhos_da_pagina`, o malformado tem preenchimento `None`); `test_desenho_com_coordenada_nao_finita_e_descartado`.
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_glyph_text.py tests/unit/test_pymupdf_drawing_model_adversarial.py -q`.
- [ ] **Step 3: Implementar** `glyph_text.py`, `caminhos_da_pagina` (o `_caminhos_e_glifos` passa a usá-la) e a fixture (fecha todo documento).
- [ ] **Step 4: Rodar e ver passar** — o mesmo comando e `tests/unit/test_pymupdf_drawing_model.py`; mypy e ruff limpos.
- [ ] **Step 5: Commit** — `feat(analise): leitura de texto por contorno de glifo`.

### Task 3: Rodada de glifos (CLI) e modo glifo do leitor visual

**Files:**
- Create: `scripts/curation_glifos.py`
- Modify: `.claude/agents/curadoria-leitor-visual.md` (seção "Modo glifo"), `.claude/settings.json` (`"Bash(.venv/Scripts/python.exe -m scripts.curation_glifos *)"`), `docs/fluxo-curadoria-incremental-simbologia.md` (seção "Rodada de glifos"), `CLAUDE.md`
- Test: `tests/unit/test_curation_glifos.py`

**Interfaces:**
- Consumes: Task 2 (`extrair_trechos`, `caminhos_da_pagina`, fixture), Task 1 (`distancia_assinaturas`, `EntradaGlifo`, `serializar_tabela_glifos`).
- Produces: `python -m scripts.curation_glifos <subcomando>`:
  - `agrupar --pdfs DIR --rodada R [--limiar 0.04] [--excluir-sha ARQ]` — todos os glifos de trechos; agrupamento líder (frequência decrescente) com `distancia_assinaturas <= limiar`; `--excluir-sha` lista sha256 de folhas reservadas que ficam de fora. Grava `R/grupos.json` (`id` `c0001…`, `subcaminhos`, `membros`, `familias` {família: n}, `folhas` (contagem), `distancia_maxima_interna`, `assinatura` do representante), `R/h1.json` (candidatos, trechos, glifos em trecho, distribuição de subcaminhos, por família) e folhas de contato `R/contato/folha-NNN.png` (até 40 grupos por folha; célula com o id, a contagem, o representante em pé e ampliado, o membro mais distante do representante e um trecho de contexto em pé com o glifo marcado). Sem nome de PDF nem caminho absoluto nos JSON (folhas por `sha256[:12]`). Família por `extrair_modelo_desenho(...).familia.familia` sem tabela.
  - `validar --rodada R --leitor {a,b,c} --arquivo F` — formato `curadoria-glifos-v1`: `{"formato": "curadoria-glifos-v1", "leitor": "a", "rotulos": [{"grupo": "c0001", "caractere": "P"} | {"grupo": "c0002", "marca": "ignorar"|"ilegivel"|"composto"|"fragmento"|"misto"}]}` (`misto` = a célula mostra caracteres diferentes); A e B cobrem todos os grupos, C cobre exatamente os de `R/divergencias.json`; `caractere` é um caractere imprimível sem espaço (após NFC). Válido → cópia em `R/leituras/leitura-<leitor>.json`; recusa sobrescrever.
  - `consolidar --rodada R` — A = B → aceito; A ≠ B e C igual a um deles → aceito; senão pendente. Sem C e com divergência, grava `R/divergencias.json` e `R/contato-divergencias/folha-NNN.png` e sai com código 3. Senão grava `R/consolidacao.json` (aceitos, pendentes, contagens de `composto`/`fragmento`/`misto` por família, concordância A × B).
  - `publicar --rodada R --saida ARQ [--tolerancia 0.08 --margem 0.02 --espaco 0.38 --quebra 1.5]` — aceitos com `caractere` → entrada; `ignorar` → `caractere: null`; `ilegivel`/`composto`/`fragmento`/`misto`/pendente ficam fora; ids `g0001…` na ordem dos grupos; via `serializar_tabela_glifos`.

- [ ] **Step 1: Testes que falham** com PDFs de `pdf_texto_contorno` (dois PDFs, valores inventados): `agrupar` junta a mesma letra e separa letras diferentes; `--excluir-sha` tira a folha; JSON sem `tmp_path` nem nome de arquivo; folhas de contato PNG existem; `validar` recusa grupo faltando, caractere de 2 letras, marca desconhecida, leitor C fora das divergências e sobrescrita; `consolidar` aceita A = B, sai com 3 e lista a divergência sem C, desempata ou deixa pendente com C; `publicar` gera tabela aceita por `carregar_tabela_glifos` que, aplicada ao PDF sintético, lê o texto nativo (ida e volta).
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_glifos.py -q`.
- [ ] **Step 3: Implementar** o CLI; a seção "Modo glifo" do agente (entrada: rodada e lista de folhas de contato; lê só os PNG de `contato/` ou `contato-divergencias/`; nunca abre `grupos.json`, leituras de outro leitor, consolidação nem tabela; grava o rascunho e roda `validar`; na dúvida `ilegivel`, nunca palpite; `composto` = mais de um caractere numa forma, `fragmento` = parte de um, `misto` = representante e membro distante são caracteres diferentes); a seção "Rodada de glifos" do contrato (rodada em `tmp/curadoria-simbologia/<AAAAMMDD-HHMM>-glifos/`, folhas reservadas para avaliação excluídas por `--excluir-sha`, regra de parada: mais de 600 grupos ou menos de 50% dos candidatos das famílias de contorno em trechos → parar e registrar antes de despachar leitores; se H1 falhar, o gatilho é segmentar por subcaminho); o allow; `CLAUDE.md` (linha do `drawing_model` com a tabela de glifos; linha do CLI na seção de curadoria).
- [ ] **Step 4: Rodar e ver passar** — o mesmo comando; mypy e ruff limpos.
- [ ] **Step 5: Commit** — `feat(curadoria): rodada de glifos com leitura dupla cega`.

### Entre as Tasks 3 e 4: sonda de H1 (orquestrador)

Logo depois do commit da Task 3, o orquestrador roda `agrupar` sobre `examples\` do checkout principal para `tmp\curadoria-simbologia\<AAAAMMDD-HHMM>-glifos\` e aplica a regra de parada do contrato (mais de 600 grupos ou menos de 50% dos candidatos das famílias de contorno em trechos → parar a etapa, registrar e acionar o gatilho de H1 falsa). Passando, despacha os leitores A e B em modo glifo (paralelos, cegos um ao outro, com as instruções do modo no próprio despacho), `validar`, `consolidar` e, havendo divergência, o leitor C. A consolidação fica pronta para a Task 6; as Tasks 4 e 5 seguem em paralelo à leitura.

### Task 4: Texto de glifo no modelo de desenho e no analisador

**Files:**
- Modify: `drawing_model/model.py` (`VERSAO_MODELO_DESENHO = "modelo-desenho-v2"`; `TextoModelo.origem: Literal["nativo", "shx", "glifo"]`), `drawing_model/cache.py`, `pymupdf_drawing_model.py`, `pymupdf_analyzer.py`, `src/zeny_project_handler_server/composition.py`, `scripts/drawing_model_dxf.py`, `scripts/drawing_model_report.py`, `scripts/smoke_examples.py` e `scripts/benchmark_network_pdf.py` (passam `tabela_glifos="pacote"`, para medir o que o servidor roda; o `baseline` de `curation_ficha` herda pelo `run_variant`)
- Create: `src/zeny_project_handler/adapters/analysis/pymupdf_glyph_text.py`
- Test: `tests/unit/test_pymupdf_glyph_text.py`, `tests/integration/test_texto_glifo_interpretacao.py`, ajustes em `tests/unit/test_pymupdf_drawing_model.py` e `tests/unit/test_pymupdf_analyzer.py`

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces:
  - `extrair_modelo_desenho(pdf: Path, tabela: TabelaGlifos | None = None) -> ModeloDesenho` e `obter_modelo_desenho(pdf: Path, cache: JsonDrawingModelCache | None, tabela: TabelaGlifos | None = None) -> ModeloDesenho` (None = sem leitura de glifos). Textos de glifo em `PaginaModelo.textos` com `origem="glifo"`, `fonte=f"{versao}:{sha256[:12]}"`, `camada=""`, `rotacao` na convenção do modelo. Diagnósticos `"modelo.glifos_desconhecidos"` e `"modelo.glifos_limitados"`. Chave do cache: `versao_leitor = f"pymupdf-{pymupdf.VersionBind}:glifos-{tabela.sha256 if tabela else 'nenhuma'}"`. Os scripts `drawing_model_dxf`/`drawing_model_report` passam `carregar_tabela_glifos()`.
  - `pymupdf_glyph_text.candidatos_texto_glifos(pagina: Any, numero_pagina: int, tabela: TabelaGlifos) -> tuple[tuple[CandidatoEvidenciaDocumento, ...], tuple[DiagnosticoAnalise, ...]]` — `tipo=TEXTO`, `chave_estavel=f"p{n}:texto_glifo:{i}"`, geometria polígono dos `cantos` divididos por `page.rect`, `conteudo_bruto=texto`, atributos `origem_texto="contorno_glifo"`, `tabela_glifos=<versao>`, `tabela_glifos_sha256`, `quantidade_glifos`, `rotacao_graus` (Decimal, convenção nativa), `altura` (Decimal), `cor` (`_pdf_color`). Diagnósticos `analise.glifos_desconhecidos` (contagens de desconhecidos e ambíguos) e `analise.glifos_limitados`, `extrator="texto_glifos"`.
  - `PyMuPdfDocumentAnalyzer.versao = "1.21.0"`; construtor `tabela_glifos: TabelaGlifos | Literal["pacote"] | None = None`; `assinatura_capacidade` inclui `"tabela_glifos"` (sha256, `"desativada"` ou `"indisponivel:<codigo>"`) e `"modelo_desenho": VERSAO_MODELO_DESENHO`. A composição do servidor passa `"pacote"`.

- [ ] **Step 1: Testes que falham:**
  - `test_texto_em_contorno_da_fonte_livre_le_igual_ao_nativo` (critério 1): PDFs nativo e em contorno das linhas da Task 2 (com rotações 90 e 30), `PyMuPdfDocumentAnalyzer(tabela_glifos=tabela_do_alfabeto(...))` sem OCR → multiconjunto dos `conteudo_bruto` das `TEXTO` com `origem_texto="contorno_glifo"` (contorno) == multiconjunto dos `conteudo_bruto` das `TEXTO` (nativo); centros das geometrias pareadas a ≤ 0.01 e `rotacao_graus` a ±2°.
  - `test_pagina_com_rotate_90_posiciona_igual_ao_nativo`: o mesmo par com `rotacao_pagina=90` → centros a ≤ 0.01 e `rotacao_graus` a ±2°, na evidência e no `TextoModelo` do modelo v2.
  - `test_glifo_ausente_gera_diagnostico_e_nao_produz_caractere` (critério 2): tabela sem `"3"` → `analise.glifos_desconhecidos` e nenhum `conteudo_bruto` contém `"11-"`.
  - `test_tabela_do_pacote_indisponivel_desativa_com_diagnostico`: `tabela_glifos="pacote"` com o carregador monkeypatched para levantar `ValueError` → análise conclui, diagnóstico `analise.tabela_glifos_indisponivel`, assinatura com `"indisponivel:"`, nenhuma `TEXTO` de glifo; `tabela_glifos=None` → assinatura `"desativada"`.
  - `test_pagina_com_glifos_demais_tem_teto` e `test_leitura_de_glifos_que_falha_nao_derruba_a_pagina` (`analise.texto_glifos_falhou`, texto nativo e vetores preservados).
  - `test_glifo_nao_conta_como_texto_nativo_para_o_ocr` (`native_characters == 0` no PDF em contorno).
  - `test_cobertura_ocr_x_glifo` (função pura `_resolver_cobertura(ocr, glifos)` com candidatos e `TextoGlifo` à mão), parametrizado:
    - fragmento: OCR `"P7"` dentro do glifo `"P7 U4(1)"` → OCR sai, glifo fica, sem divergência;
    - cobertura total: OCR `"P7 U4(1)"` (caixa 10% folgada) sobre o glifo `"P7 U4(1)"` → glifo sai, OCR fica;
    - superconjunto: uma linha OCR `"P7 U4(1) 11-300"` cobrindo dois textos de glifo concordantes → os dois glifos saem, OCR fica;
    - token direcionado de motor de contornos (`motor_ocr="tesseract-contornos-vetoriais"`) igual ao glifo → glifo sai, OCR fica com seus atributos;
    - fragmento do motor de contornos: token `"P7"` com `motor_ocr="tesseract-contornos-vetoriais"` dentro do glifo `"P7 U4(1)"` → os dois ficam;
    - superconjunto parcial: linha OCR concordante cobrindo o glifo A inteiro e metade do glifo B → A sai, B e o OCR ficam;
    - divergência: OCR `"P1"` sobre o glifo `"P7"` → os dois ficam e `analise.glifo_ocr_divergente` conta 1;
    - OCR fora de qualquer glifo → fica.
  - `test_glifo_coberto_por_nativo_concordante_e_descartado` (e glifo só parcialmente coberto fica).
  - `test_revisoes_e_complementar_nao_veem_texto_de_glifo`.
  - `test_versao_e_assinatura_de_capacidade`: `versao == "1.21.0"`; tabelas de `sha256` diferente → assinaturas diferentes.
  - `test_modelo_traz_texto_de_glifo_e_versao_v2` (em `test_pymupdf_drawing_model.py`): `origem == "glifo"`, ida e volta pelo cache, tabela diferente → chave diferente, `tabela=None` → sem texto de glifo.
  - `tests/integration/test_texto_glifo_interpretacao.py::test_folha_em_contorno_e_nativa_geram_as_mesmas_propostas`: fixture com rótulos coloridos (verde e vermelho) de poste e estrutura, nativa e em contorno, pelo pipeline de interpretação usado nos testes de integração existentes → mesmas propostas (categoria, situação e valores), comparadas sem ids.
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_pymupdf_glyph_text.py tests/unit/test_pymupdf_drawing_model.py tests/unit/test_pymupdf_analyzer.py tests/integration/test_texto_glifo_interpretacao.py -q`.
- [ ] **Step 3: Implementar** conforme "Decisões de desenho" (encaixes, OCR como reserva, tabela indisponível, geometria e rotação). Testes existentes que mudarem de expectativa precisam de justificativa no relatório; não afrouxe asserções.
- [ ] **Step 4: Rodar e ver passar** — o mesmo comando, depois `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`, mypy, ruff e `scripts/complexity_gate.py src`.
- [ ] **Step 5: Commit** — `feat(analise): texto de glifo no modelo de desenho e no analisador 1.21.0`.

### Task 5: Benchmark de recall de texto por campo da ficha

**Files:**
- Create: `scripts/benchmark_texto_ficha.py`
- Test: `tests/unit/test_benchmark_texto_ficha.py`

**Interfaces:**
- Consumes: `scripts/ficha_poste.carregar_ficha`, Task 4 (`PyMuPdfDocumentAnalyzer`, `origem_texto`), `extrair_modelo_desenho` (família).
- Produces:
  - `TextoMedido(texto: str, centro: tuple[float, float], origem: Literal["nativo", "glifo"])` (centro normalizado na página exibida, convenção `symbols-e02-v1`).
  - `recall_texto(referencia: Mapping[str, Any], textos: Sequence[TextoMedido]) -> dict[str, dict[str, int]]` — por campo (`identificador`, `poste`, `estruturas`, `coordenada`): `{"total": n, "acertos": k, "erros_afirmados": e}`. Instâncias: `identificador`, `poste`, cada item de `estruturas`, `str(leste)` e `str(norte)` de cada poste; campo `null` ou em `pendentes` do poste não conta. Normalização: NFKC, maiúsculas, espaços colapsados. Ocorrência = casamento de `(?<![0-9A-Z])valor(?![0-9A-Z])`; cada ocorrência serve a uma instância; atribuição gulosa global por distância crescente ao centro da bbox do poste. Erro afirmado = instância sem acerto cujo token mais próximo do poste (até 0.05 de distância normalizada) tem o mesmo comprimento ±1 e distância de edição 1–2 do valor.
  - CLI `python -m scripts.benchmark_texto_ficha --rodada RODADA_E03 --pdfs DIR --saida DIR [--tabela ARQ]` — casa PDF e referência por `pdf_sha256`; analisador sem OCR com `tabela_glifos=` a tabela de `--tabela` ou a do pacote; fonte `base` = `TEXTO` sem `origem_texto`, `novo` = todas as `TEXTO`; grava `texto-ficha.json` e `texto-ficha.md` com acertos, totais e erros afirmados por campo × fonte, por PDF (id da rodada), por família e total, mais a versão do analisador, o `sha256` da tabela e o tempo da leitura de glifos por PDF. Sem nome de PDF nem caminho absoluto.
- [ ] **Step 1: Testes que falham:** dois postes com `"N1"` e um só texto `"N1"` → 1 de 2; `"P1"` não casa `"P10"`; `"E=612345"` casa leste; pendente não conta; `"11-30O"` perto do poste com referência `"11-300"` → `erros_afirmados == 1`; CLI ponta a ponta com PDF nativo e em contorno da fixture (referência sintética válida para `carregar_ficha` na estrutura de rodada em `tmp_path`, `--tabela` com a tabela do alfabeto) → contorno com `base` 0 e `novo` > 0; saída sem `tmp_path`.
- [ ] **Step 2: Rodar e ver falhar** — `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_texto_ficha.py -q`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar e ver passar** — mesmo comando, mypy e ruff.
- [ ] **Step 5: Commit** — `feat(benchmark): recall de texto por campo da ficha`.

### Task 6: Tabela real, medição nas 16 folhas e H1

**Pré-requisito:** a consolidação da sonda de H1 (entre as Tasks 3 e 4) pronta, sem pendência que impeça publicar (nenhuma folha está reservada para avaliação hoje; H4 ainda não foi atendida).

**Files (desenvolvedor):**
- Modify: `src/zeny_project_handler/adapters/analysis/data/tabela-glifos-v1.json` (gerado por `publicar`)
- Test: `tests/unit/test_glyph_table.py`

- [ ] **Step 1: Teste que falha** — `test_tabela_empacotada_real_e_valida_e_sem_dados_de_folha` (substitui `test_tabela_empacotada_vazia_carrega`): `carregar_tabela_glifos()` tem ≥ 30 entradas com caractere, cobre `0–9`, e o JSON (minúsculo) não contém `pdf`, `png`, `sha`, `base64` nem sequência hexadecimal de 12+ caracteres.
- [ ] **Step 2: Publicar** — `python -m scripts.curation_glifos publicar --rodada <R> --saida src/zeny_project_handler/adapters/analysis/data/tabela-glifos-v1.json`; o teste passa.
- [ ] **Step 3: Medir** — `python -m scripts.benchmark_texto_ficha --rodada C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\curadoria-simbologia\20261103-2300-fichas --pdfs C:\Users\Caio\Desktop\repos\ZenyProjectHandler\examples --saida <R>\benchmark`; no relatório: acertos, totais e erros afirmados por campo × fonte, por família e total; tempo da leitura de glifos por folha (orçamento: ≤ 5 s por folha; estouro é registrado e vai para "Decisões para o usuário", sem bloquear).
- [ ] **Step 4: Baseline da E02 com o analisador 1.21.0** — `python -m scripts.curation_ficha baseline --rodada C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\curadoria-simbologia\20261103-2300-fichas --native-only` (grava a próxima `baseline-vNNN` da rodada) → registrar o total (esperado 0/107 enquanto D5 não entra), confirmando que a ficha promovida não regrediu (o `run_variant` usa `tabela_glifos="pacote"` desde a Task 4, então mede a configuração do servidor).
- [ ] **Step 5: Calibrar só com evidência** — se `novo` não superar `base` numa família de contorno (`electric_office_print`, `ghostscript`) ou houver erro afirmado, investigar; ajustar só `tolerancia`/`margem`/`espaco`/`quebra` via `publicar`, medir de novo e registrar antes e depois; persistindo, registrar a família como "continua com OCR".
- [ ] **Step 6: Suíte inteira** — `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider` verde (os testes injetam tabela; só o da tabela empacotada a lê).
- [ ] **Step 7: H1 no relatório** — de `h1.json` e `consolidacao.json`: proporção de candidatos em trecho, distribuição de subcaminhos, grupos `composto`/`fragmento`/`misto` por família; conclusão sobre H1.
- [ ] **Step 8: Commit** — `feat(analise): tabela de glifos v1 a partir da rodada de glifos`.
