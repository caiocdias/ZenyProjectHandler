# E04 — Modelo de desenho e perfis de família — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cada página de PDF vira um modelo de desenho derivado — caminhos brutos (com subcaminhos, Béziers, tipo traço/preenchimento e ordem de pintura) e, derivados deles, polilinhas reconstruídas, círculos e arcos recuperados de Béziers e grupos candidatos a símbolo; mais texto nativo e SHX; tudo com camada, cor e espessura —, a família do PDF é reconhecida por impressão estrutural, o modelo entra num cache derivado com versão própria e um script exporta o modelo em DXF de depuração.

**Architecture:** um pacote novo `zeny_project_handler/adapters/analysis/drawing_model/` com tipos e algoritmos puros (sem PyMuPDF: `model.py`, `geometry.py`, `groups.py`, `family.py`, `cache.py`) e um único módulo PyMuPDF (`pymupdf_drawing_model.py`) que lê a página e monta o modelo, reaproveitando os auxiliares PyMuPDF vigentes (texto sem anotações, predicado de SHX, critério de glifo). O analisador padrão, as evidências, as propostas e as versões de extrator e interpretador não mudam: nesta etapa o modelo só é produzido sob demanda (scripts e testes) e consumido pelas etapas E05–E07. Dois scripts em `scripts/`: o DXF de depuração (ezdxf) e o relatório sobre as folhas reais (famílias, H3, tempo e memória), que gravam só em `tmp/`.

**Tech Stack:** Python 3.11–3.13, PyMuPDF 1.28.x (só no módulo `pymupdf_*`), ezdxf (MIT, nova dependência de desenvolvimento), pytest, mypy strict, ruff.

**Spec:** seção "E04 — Modelo de desenho e perfis de família" de `docs/roadmap-leitura-vetorial-por-poste.md`; design `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (decisões 1 e 2, "O que os PDFs reais mostram", "Fronteiras"); ADR 0016; ADR 0004 (cache derivado, unidade de falha, coordenadas da página visual); ADR 0006.

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o cliente não importa nada do servidor (`client_artifact_gate`); DTOs seguem `tests/contracts/test_architecture.py`. Esta etapa não toca `domain/`, `application/`, `ports/`, contratos, API nem cliente.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`; o analisador padrão não muda, então nenhuma versão de extrator/interpretador é incrementada (ADR 0006) e nenhuma migração SQLite é feita.
- PDFs reais, recortes, DXF e cache de folhas reais, rótulos e pesos nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa, gerada no próprio teste com PyMuPDF.
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro: feche documentos PyMuPDF (`with pymupdf.open(...)`) e arquivos.
- ezdxf (MIT) entra **só** em `requirements-development.lock` e no extra `dev` do `pyproject.toml`; nunca no lock do servidor, do cliente ou de experimentos. Só `scripts/` importa ezdxf. Dependências transitivas novas também precisam ser Apache-2.0, BSD ou MIT.
- Documentação enxuta: atualize só o que a mudança torna falso (`CLAUDE.md` ganha uma linha sobre o modelo de desenho e os dois scripts). Nada de histórico de execução em arquivo versionado.
- Coordenadas do modelo: espaço da **página visual** (rotação intrínseca `/Rotate` aplicada, origem no canto superior esquerdo, y para baixo, unidade ponto PDF), com `largura` e `altura` da página visual. A normalização 0–1 do ADR 0004 acontece quando o modelo for materializado em evidência (E05–E07), não aqui. Ângulos (`Arco`, `TextoModelo.rotacao`) em graus, nesse mesmo espaço; a conversão para y para cima acontece só no DXF.
- Toda mudança de tolerância, critério ou algoritmo que altere o modelo incrementa `VERSAO_MODELO_DESENHO`.
- Arquivos gravados pelos scripts (relatório, DXF, cache, amostras de imagem) ficam sob `tmp/` do repositório indicado e não trazem caminho absoluto, nome do PDF, produtor nem criador brutos: só `sha256`, índice de página e sinais derivados.

## Review Focus

- Página com `/Rotate 90/180/270`: caminhos, textos, polilinhas e círculos saem no espaço da página visual. Teste: `test_extrai_modelo_em_pagina_rotacionada` (Task 3), com `/Rotate 90` e `/Rotate 270`.
- Glifo em contorno (caminho preenchido feito de Béziers que não formam círculo) sobrevive no modelo com seus subcaminhos, e dois quadrados preenchidos adjacentes não se fundem numa polilinha. Testes: `test_glifo_preenchido_sobrevive_nos_caminhos` e `test_preenchimentos_adjacentes_nao_se_fundem` (Task 3).
- Texto de anotação (FreeText/Stamp) não aparece como texto nativo, e o SHX não aparece duas vezes. Teste: `test_freetext_nao_vira_texto_nativo` (Task 3).
- Folhas reais caem na família certa: a distribuição nas 16 folhas de `examples/` precisa bater com 8 Print To PDF (Electric Office), 6 iText, 1 Ghostscript e 1 AutoCAD. Verificação: passo 2 da execução operacional; divergência ajusta o critério antes de fechar a etapa.
- Página malformada não derruba o documento: falha de uma fonte (texto, desenhos, imagens, SHX) numa página vira diagnóstico daquela página, e as outras fontes e páginas continuam. Teste: `test_falha_de_uma_fonte_vira_diagnostico_da_pagina` (Task 3).

---

### Task 1: Tipos do modelo, geometria pura e guarda de imports

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/__init__.py`, `.../drawing_model/model.py`, `.../drawing_model/geometry.py`
- Modify: `tests/unit/test_architecture.py` (guardas novas)
- Test: `tests/unit/test_drawing_model_geometry.py`

**Interfaces:**
- Produces (em `model.py`, dataclasses `frozen=True, slots=True`; `JsonPrimitive` pode ser importado de `zeny_project_handler.domain` como os adaptadores já fazem):
  - `Estilo(camada: str, cor: tuple[float, float, float] | None, preenchimento: tuple[float, float, float] | None, espessura: float, tracejado: str)`;
  - `ItemCaminho(tipo: Literal["l", "c"], pontos: tuple[tuple[float, float], ...])` (2 pontos para `l`; 4 para `c`: p0, c1, c2, p1);
  - `Caminho(subcaminhos: tuple[tuple[ItemCaminho, ...], ...], estilo: Estilo, tipo: Literal["traco", "preenchimento", "traco_e_preenchimento"], ordem: int)` (`ordem` = ordem de pintura na página; `re`/`qu` viram um subcaminho fechado de 4 itens `l`);
  - `Polilinha(pontos: tuple[tuple[float, float], ...], fechada: bool, estilo: Estilo, origens: tuple[int, ...])`, `Circulo(centro, raio, estilo, origens)`, `Arco(centro, raio, angulo_inicial, angulo_final, estilo, origens)` — `origens` são índices em `PaginaModelo.caminhos`; ângulos em graus no espaço da página visual (y para baixo), medidos a partir do eixo x positivo no sentido horário visual, `angulo_final` > `angulo_inicial`;
  - `TextoModelo(texto: str, bbox: tuple[float, float, float, float], origem: Literal["nativo", "shx"], rotacao: float, altura: float, fonte: str, camada: str)`;
  - `ImagemModelo(bbox: tuple[float, float, float, float], largura_px: int, altura_px: int, sha256: str, de_anotacao: bool)`;
  - `GrupoCandidato(bbox: tuple[float, float, float, float], indices_primitivas: tuple[int, ...], indices_caminhos: tuple[int, ...])` (índices em `primitivas` e em `caminhos`; `indices_caminhos` traz os caminhos preenchidos que não viraram círculo nem arco);
  - `PaginaModelo(indice: int, largura: float, altura: float, caminhos: tuple[Caminho, ...], textos: tuple[TextoModelo, ...], primitivas: tuple[Polilinha | Circulo | Arco, ...], grupos: tuple[GrupoCandidato, ...], imagens: tuple[ImagemModelo, ...], diagnosticos: tuple[str, ...])`;
  - `PerfilFamilia(familia: str, sinais: tuple[tuple[str, JsonPrimitive], ...], diagnosticos: tuple[str, ...])`;
  - `ModeloDesenho(versao: str, documento_sha256: str, familia: PerfilFamilia, paginas: tuple[PaginaModelo, ...])`;
  - `VERSAO_MODELO_DESENHO: Final = "modelo-desenho-v1"`.
- Produces (em `geometry.py`, funções puras):
  - `reconstruir_polilinhas(caminhos: Sequence[Caminho], *, tolerancia_ponto: float = 0.5, tolerancia_angulo_graus: float = 1.0) -> tuple[Polilinha, ...]`: usa **só** os itens `l` de caminhos de tipo `"traco"`; funde segmentos de mesmo `Estilo` que se tocam (extremos a até `tolerancia_ponto`) e são colineares (desvio até `tolerancia_angulo_graus`); depois encadeia segmentos contíguos de mesmo estilo em polilinhas (fechada quando volta ao início), com `origens` = caminhos que contribuíram. Índice espacial por grade (células de `tolerancia_ponto`), nada quadrático.
  - `recuperar_circulos_e_arcos(caminhos: Sequence[Caminho], *, tolerancia_relativa: float = 0.02) -> tuple[Circulo | Arco, ...]`: considera os itens `c` de qualquer tipo de caminho; uma Bézier é arco de círculo quando os extremos e os pontos em t=0,25, 0,5 e 0,75 caem num círculo comum (desvio radial ≤ `tolerancia_relativa` × raio); arcos contíguos do mesmo subcaminho, mesmo centro e raio são unidos; união de 360° vira `Circulo`. Os caminhos de origem continuam em `caminhos` (nada é descartado).
- Guardas em `tests/unit/test_architecture.py`: `ezdxf` e `onnxruntime` entram em `FORBIDDEN_IMPORTS` (domínio); um conjunto próprio `APPLICATION_FORBIDDEN_IMPORTS = frozenset({"pymupdf", "fitz", "ezdxf", "onnxruntime"})` (invariante do roadmap) com o teste `test_aplicacao_nao_importa_leitores_de_pdf_nem_ezdxf` varrendo `application/` (o PIL de `application/visual_occupancy.py` continua permitido ali); e dois testes novos: `test_src_nao_importa_ezdxf` (nenhum arquivo de `src/` importa `ezdxf`) e `test_drawing_model_puro_nao_importa_pymupdf` (`adapters/analysis/drawing_model/` não importa `pymupdf` nem `fitz`).

- [ ] **Step 1: Write the failing tests**

```python
def test_segmentos_colineares_fragmentados_viram_uma_polilinha() -> None:
    e = Estilo("REDE", (0, 0, 0), None, 1.0, "")
    caminhos = [traco(e, (0, 0), (10, 0), ordem=0), traco(e, (10, 0), (25, 0), ordem=1), traco(e, (25.2, 0), (40, 0), ordem=2)]
    (p,) = reconstruir_polilinhas(caminhos)
    assert p.pontos == ((0, 0), (40, 0)) and not p.fechada and p.origens == (0, 1, 2)
def test_segmentos_em_l_viram_polilinha_de_tres_pontos() -> None: ...
def test_quadrado_de_traco_vira_polilinha_fechada() -> None: ...
def test_nao_funde_segmentos_de_estilo_diferente() -> None: ...   # camada, cor, espessura, tracejado
def test_caminho_preenchido_nao_entra_na_fusao() -> None: ...       # quadrado tipo "preenchimento" → nenhuma polilinha
def test_circulo_em_quatro_beziers_vira_circulo() -> None:
    (c,) = recuperar_circulos_e_arcos([circulo_em_beziers((50, 50), 5, tipo="traco")])
    assert isinstance(c, Circulo) and c.centro == pytest.approx((50, 50), abs=1e-3) and c.raio == pytest.approx(5, rel=1e-3) and c.origens == (0,)
def test_disco_preenchido_tambem_vira_circulo() -> None: ...
def test_quarto_de_circulo_vira_arco() -> None: ...
def test_elipse_nao_vira_circulo() -> None: ...                   # raios 5 e 8 → ()
def test_curva_s_nao_vira_arco() -> None: ...
def test_fusao_escala_linearmente() -> None:
    # 10 000 e 20 000 segmentos de 1 pt em linhas paralelas: tempo(20k)/tempo(10k) < 3
def test_src_nao_importa_ezdxf() -> None: ...                     # em test_architecture.py
def test_drawing_model_puro_nao_importa_pymupdf() -> None: ...    # em test_architecture.py
```

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/unit/test_drawing_model_geometry.py tests/unit/test_architecture.py -q` → FAIL.
- [ ] **Step 3: Implement** `model.py`, `geometry.py` e as guardas.
- [ ] **Step 4: Run** os dois arquivos → PASS; `ruff check`, `ruff format --check`, `mypy` → limpos.
- [ ] **Step 5: Commit** `feat(analise): tipos do modelo de desenho, geometria pura e guardas de import`.

---

### Task 2: Perfil por família e grupos candidatos a símbolo

**Files:**
- Create: `.../drawing_model/family.py`, `.../drawing_model/groups.py`
- Test: `tests/unit/test_drawing_model_family.py`, `tests/unit/test_drawing_model_groups.py`

**Interfaces:**
- Consumes: Task 1.
- Produces:
  - `ImpressaoEstrutural(produtor: str, criador: str, nomes_ocg: tuple[str, ...], spans_texto_nativo: int, formas_glifo: int, anotacoes_shx: int, imagens: int)` (dataclass pura, preenchida pela Task 3; `formas_glifo` usa o critério vigente `_is_glyph` de `pymupdf_glyphs.py`: tipo `f`, até 256 itens, lados entre 0,05 e 6 pt);
  - `FAMILIAS: Final = ("electric_office_print", "itext", "ghostscript", "autocad", "generico")`, `LIMIAR_FORMAS_GLIFO: Final = 300`;
  - `reconhecer_familia(impressao: ImpressaoEstrutural) -> PerfilFamilia`, nesta ordem: `autocad` se `"pdfplot"` ou `"autocad"` em produtor/criador (sem diferenciar maiúsculas), ou `anotacoes_shx > 0`, ou há OCGs; `itext` se `"itext"` no produtor; `ghostscript` se `"ghostscript"` no produtor; `electric_office_print` se `"print to pdf"` no produtor e `formas_glifo >= LIMIAR_FORMAS_GLIFO`; `"print to pdf"` sem esse sinal → `generico` com diagnóstico `"familia.print_to_pdf_sem_glifos"`; o resto → `generico` com `"familia.desconhecida"`. `sinais` traz só valores derivados (`ocgs`, `spans_texto_nativo`, `formas_glifo`, `anotacoes_shx`, `imagens` e booleanos `produtor_itext`, `produtor_ghostscript`, `produtor_print_to_pdf`, `produtor_autocad`), nunca produtor/criador brutos;
  - `agrupar_candidatos(primitivas: Sequence[Polilinha | Circulo | Arco], caminhos: Sequence[Caminho], *, folga: float = 1.5, lado_maximo: float = 40.0) -> tuple[GrupoCandidato, ...]`: os elementos agrupados são as primitivas e os caminhos que não foram convertidos **inteiramente** num `Circulo` (todos os seus itens viraram o mesmo círculo) e que são de tipo `"preenchimento"`/`"traco_e_preenchimento"` (polígonos e glifos preenchidos, inclusive os que têm só uma parte reconhecida como arco) ou de tipo `"traco"` com algum item `c` não coberto por círculo ou arco (elipses e curvas livres traçadas); union-find com grade espacial sobre caixas dilatadas por `folga`; descarta grupos com lado maior que `lado_maximo` pt e grupos formados por uma única polilinha aberta de dois pontos.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize(("impressao", "familia"), [...])  # um caso positivo por família
def test_reconhece_cada_familia(impressao, familia) -> None: ...
def test_print_to_pdf_sem_glifos_cai_no_generico_com_diagnostico() -> None: ...
def test_familia_desconhecida_cai_no_generico_com_diagnostico() -> None:
    perfil = reconhecer_familia(ImpressaoEstrutural("LibreOffice", "", (), 10, 0, 0, 0))
    assert perfil.familia == "generico" and "familia.desconhecida" in perfil.diagnosticos
def test_ocg_ou_shx_identifica_autocad_mesmo_com_outro_produtor() -> None: ...
def test_sinais_nao_trazem_produtor_bruto() -> None: ...   # produtor com caminho/nome não aparece em sinais
def test_agrupa_circulo_e_tracos_proximos_num_grupo() -> None: ...
def test_triangulo_preenchido_entra_no_grupo_pelos_caminhos() -> None: ...   # indices_caminhos == (i,)
def test_caminho_que_virou_circulo_nao_entra_duas_vezes() -> None: ...
def test_preenchido_com_arco_parcial_entra_pelos_caminhos() -> None: ...   # "D" preenchido
def test_elipse_tracada_entra_pelos_caminhos() -> None: ...
def test_nao_agrupa_formas_distantes() -> None: ...
def test_descarta_grupo_maior_que_lado_maximo() -> None: ...
def test_agrupamento_escala_linearmente() -> None: ...      # 10k e 20k círculos pequenos: razão de tempo < 3
```

- [ ] **Step 2–4:** FAIL → implementar → PASS; ruff, format, mypy.
- [ ] **Step 5: Commit** `feat(analise): perfil por família e grupos candidatos a símbolo`.

---

### Task 3: Extração PyMuPDF do modelo de desenho

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py`
- Test: `tests/unit/test_pymupdf_drawing_model.py` (gera os PDFs sintéticos no teste)

**Interfaces:**
- Consumes: Tasks 1 e 2; auxiliares vigentes: o padrão de `_extract_text` em `pymupdf_page_extractors.py` (texto por `page.get_displaylist(annots=False)` com a rotação zerada durante a extração e restaurada depois), `_is_technical_annotation` de `pymupdf_annotations.py` (predicado de portador SHX) e `_is_glyph` de `pymupdf_glyphs.py`. Reaproveite-os por import ou extraia um auxiliar comum sem mudar o comportamento deles.
- Produces:
  - `impressao_estrutural(documento: pymupdf.Document) -> ImpressaoEstrutural`;
  - `extrair_modelo_desenho(pdf: Path) -> ModeloDesenho`: abre com `with`, sha256 do arquivo, família, e por página, cada fonte numa unidade de falha própria (exceção numa fonte → diagnóstico `"modelo.<fonte>_falhou"` em `PaginaModelo.diagnosticos`, a fonte fica vazia e o resto continua):
    - **caminhos**: `page.get_drawings(extended=True)`; as entradas `clip` e `group` são ignoradas (só os caminhos de traço/preenchimento entram), com a camada vinda do campo `layer` de cada caminho; `Estilo` a partir de `layer`, `color`, `fill`, `width`, `dashes`; tipo `s`→`"traco"`, `f`→`"preenchimento"`, `fs`→`"traco_e_preenchimento"`; `ordem` = posição na lista; `re`/`qu` viram subcaminho fechado de 4 itens `l`; subcaminhos separados onde o ponto inicial de um item não continua o anterior;
    - **textos nativos**: pelo padrão de `_extract_text` (sem anotações), um `TextoModelo` por span (texto, bbox, rotação pela direção da linha, altura pelo tamanho, fonte); **camada do texto** por `page.get_texttrace()` (campo `layer` por span, casado pela bbox); se a PyMuPDF 1.28 não expuser `layer` no texttrace, `camada = ""` e o relatório da tarefa diz isso (a Task 5 se ajusta, ver lá);
    - **textos SHX**: anotações que passam no predicado `_is_technical_annotation`, `origem="shx"`, bbox da anotação, texto do conteúdo da anotação;
    - **imagens**: `get_image_info(hashes=True)` (página, `de_anotacao=False`) mais as imagens das appearance streams de anotações (`de_anotacao=True`), percorrendo `/AP` como `pymupdf_annotations.py` já faz;
    - tudo transformado para a página visual com `page.rotation_matrix`; depois `reconstruir_polilinhas`, `recuperar_circulos_e_arcos` e `agrupar_candidatos`.

- [ ] **Step 1: Write the failing tests**

```python
def test_extrai_texto_nativo_com_posicao_rotacao_e_altura(tmp_path) -> None: ...
def test_freetext_nao_vira_texto_nativo(tmp_path) -> None: ...      # PDF com FreeText "NOTA" → nenhum TextoModelo nativo "NOTA"
def test_extrai_texto_shx_uma_vez(tmp_path) -> None: ...            # anotação Square "AutoCAD SHX Text" → 1 texto shx, 0 nativo igual
def test_segmentos_fragmentados_do_pdf_viram_uma_polilinha(tmp_path) -> None: ...
def test_circulo_desenhado_com_beziers_vira_circulo(tmp_path) -> None: ...   # page.draw_circle
def test_glifo_preenchido_sobrevive_nos_caminhos(tmp_path) -> None:
    # caminho preenchido em forma de "S" com Béziers → 1 Caminho tipo "preenchimento" com os itens "c", nenhuma Polilinha
def test_preenchimentos_adjacentes_nao_se_fundem(tmp_path) -> None: ...
def test_camada_ocg_vai_para_o_estilo_e_para_o_texto(tmp_path) -> None: ...  # desenho e texto no OCG "P"
def test_extrai_modelo_em_pagina_rotacionada(tmp_path) -> None: ...          # /Rotate 90 e 270
def test_modelo_de_pagina_vazia_e_multipagina(tmp_path) -> None: ...
def test_fixture_de_cada_familia_e_reconhecida(tmp_path) -> None: ...         # metadados, OCG, SHX, 400 glifos → 4 famílias + genérico
def test_imagem_de_anotacao_e_marcada(tmp_path) -> None: ...                  # Stamp com imagem → de_anotacao=True
def test_falha_de_uma_fonte_vira_diagnostico_da_pagina(tmp_path, monkeypatch) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar → PASS; ruff, format, mypy.
- [ ] **Step 5: Commit** `feat(analise): extração PyMuPDF do modelo de desenho`.

---

### Task 4: Cache derivado do modelo com versão própria

**Files:**
- Create: `.../drawing_model/cache.py`
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py` (entrada com cache)
- Test: `tests/unit/test_drawing_model_cache.py`

**Interfaces:**
- Consumes: Tasks 1–3; `zeny_project_handler._atomic_files.sibling_temporary_file` (como em `json_cache.py`).
- Produces:
  - `chave_modelo_desenho(documento_sha256: str, versao_leitor: str, versao: str = VERSAO_MODELO_DESENHO) -> str`: sha256 de `f"{documento_sha256}:{versao}:{versao_leitor}"`; o módulo PyMuPDF passa `versao_leitor=f"pymupdf-{pymupdf.VersionBind}"`, e `cache.py` continua puro;
  - `JsonDrawingModelCache(diretorio: Path)` com `obter(chave: str) -> ModeloDesenho | None` e `salvar(chave: str, modelo: ModeloDesenho) -> None`: um JSON por chave em `diretorio / "modelo-desenho"`, `schema_version` próprio, gravação atômica por `sibling_temporary_file`, `Decimal` codificado como string com marcador de tipo; JSON corrompido, versão ou esquema diferente → `None`;
  - `obter_modelo_desenho(pdf: Path, cache: JsonDrawingModelCache | None) -> ModeloDesenho`: tenta o cache, extrai e salva quando falta; falha de leitura ou gravação do cache não derruba a extração (como `pymupdf_analyzer._write_cache`); modelo com diagnóstico de fonte falha não é gravado (a falha pode ser transitória).

- [ ] **Step 1: Write the failing tests**

```python
def test_ida_e_volta_preserva_o_modelo(tmp_path) -> None: ...
def test_segunda_chamada_usa_o_cache_sem_reextrair(tmp_path, monkeypatch) -> None: ...
def test_versao_diferente_invalida_o_cache(tmp_path) -> None: ...
def test_json_corrompido_e_ignorado(tmp_path) -> None: ...
def test_falha_de_gravacao_nao_derruba_a_extracao(tmp_path, monkeypatch) -> None: ...
def test_modelo_com_diagnostico_de_falha_nao_e_gravado(tmp_path, monkeypatch) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar → PASS; ruff, format, mypy.
- [ ] **Step 5: Commit** `feat(analise): cache derivado do modelo de desenho com versão própria`.

---

### Task 5: DXF de depuração (ezdxf como dependência de desenvolvimento)

**Files:**
- Create: `scripts/drawing_model_dxf.py`
- Modify: `requirements-development.lock` (ezdxf e transitivas ainda não fixadas, versões exatas instaladas), `pyproject.toml` (extra `dev`), `docs/roadmap-leitura-vetorial-por-poste.md` linha de "Restrições e invariantes" sobre dependências ("locks do servidor, de desenvolvimento ou de experimentos, nunca no cliente nem no runtime sem consumidor"), `CLAUDE.md` (uma linha na lista de comandos)
- Test: `tests/unit/test_drawing_model_dxf.py`

**Interfaces:**
- Consumes: `obter_modelo_desenho` (Task 4).
- Produces: CLI `python -m scripts.drawing_model_dxf PDF --saida ARQUIVO.dxf [--pagina N] [--cache DIR] [--raiz-repositorio DIR]` (recusa `--saida` e `--cache` fora de `tmp/` da raiz do repositório; padrão: diretório atual) e `exportar_dxf(modelo: ModeloDesenho, pagina: int, destino: Path) -> None`: camada DXF por `Estilo.camada`/`TextoModelo.camada` (vazia → `"0"`; nomes saneados), `TEXT` por texto (posição, altura, rotação), `LWPOLYLINE` por polilinha, `CIRCLE`, `ARC`, retângulo na camada `"GRUPOS_CANDIDATOS"` por grupo, y invertido (y para cima) e ângulos convertidos.

- [ ] **Step 1: Write the failing tests**

```python
def test_dxf_da_fixture_abre_com_ezdxf_e_preserva_camadas_e_textos(tmp_path) -> None:
    # PDF sintético: OCG "P" com linha + círculo; OCG "NOTAS" com o texto "P1 U3(1)"
    exportar_dxf(obter_modelo_desenho(pdf, None), 0, destino)
    doc = ezdxf.readfile(destino)
    assert {"P", "NOTAS"} <= {layer.dxf.name for layer in doc.layers}
    assert any(t.dxf.text == "P1 U3(1)" for t in doc.modelspace().query("TEXT"))
    assert len(doc.modelspace().query("CIRCLE")) == 1
    # camada do texto: "NOTAS" se a Task 3 obteve a camada pelo texttrace; senão "0" (o relatório da Task 3 diz qual)
def test_cli_grava_dxf_e_recusa_pagina_inexistente(tmp_path) -> None: ...
def test_cli_recusa_saida_e_cache_fora_de_tmp(tmp_path) -> None: ...
def test_nome_de_camada_invalido_e_saneado(tmp_path) -> None: ...
```

- [ ] **Step 2:** instalar a dependência no `.venv` (`.venv/Scripts/python.exe -m pip install ezdxf==<versão estável atual>`), conferir a licença de cada transitiva nova, rodar o teste → FAIL.
- [ ] **Step 3: Implement** o script; fixe as versões exatas no lock de desenvolvimento; `pip check` limpo.
- [ ] **Step 4: Run** o teste → PASS; ruff, format, mypy; `scripts/client_artifact_gate.py --source-only` limpo.
- [ ] **Step 5: Commit** `feat(scripts): DXF de depuração do modelo de desenho`.

---

### Task 6: Relatório das folhas reais (famílias, H3, custo) — script e teste sintético

**Files:**
- Create: `scripts/drawing_model_report.py`
- Modify: `CLAUDE.md` (mesma linha da Task 5 ou a seguinte)
- Test: `tests/unit/test_drawing_model_report.py`

**Interfaces:**
- Consumes: `extrair_modelo_desenho` e `impressao_estrutural` (Task 3).
- Produces: CLI `python -m scripts.drawing_model_report --raiz DIR --saida ARQUIVO.json [--amostras-imagem DIR] [--raiz-repositorio DIR]` (recusa saídas fora de `tmp/`) e `medir_pdf(pdf: Path) -> dict[str, Any]` com, por PDF: `sha256`, família e sinais; por página: contagens de caminhos (por tipo), textos (nativo/SHX), polilinhas, círculos, arcos, grupos e diagnósticos; tempo (`time.perf_counter`) e pico de memória (`tracemalloc`) da extração; e por imagem uma classe:
  - `ladrilho`: imagem de página cujo tamanho em pixels se repete em pelo menos 4 imagens do PDF e cujas caixas se encaixam numa grade (bordas alinhadas com tolerância de 1 pt);
  - `anotacao`: `de_anotacao=True` (carimbo, assinatura, foto);
  - `outra`: o resto.
  Contagens por classe, fração da página coberta pelos ladrilhos e, com `--amostras-imagem`, PNGs nomeados pelo `sha256` da imagem para inspeção visual: cada imagem `outra`; até 3 `anotacao` por PDF; e, por PDF, os ladrilhos cuja caixa cruza algum grupo candidato ou texto (até 5) mais 2 ladrilhos sorteados com semente fixa (`random.Random(sha256 do PDF)`).

- [ ] **Step 1: Write the failing tests**

```python
def test_medir_pdf_sintetico_conta_primitivas_e_classifica_imagens(tmp_path) -> None:
    # 4 imagens iguais em grade → ladrilho; 1 imagem pequena isolada → outra; Stamp com imagem → anotacao
def test_relatorio_nao_tem_caminho_nome_nem_produtor(tmp_path) -> None: ...
def test_cli_recusa_saida_fora_de_tmp(tmp_path) -> None: ...
def test_amostras_de_imagem_sao_nomeadas_pelo_sha(tmp_path) -> None: ...
def test_amostra_inclui_ladrilho_que_cruza_grupo_e_sorteio_estavel(tmp_path) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar → PASS; ruff, format, mypy.
- [ ] **Step 5: Commit** `feat(scripts): relatório do modelo de desenho sobre folhas reais`.

---

## Execução operacional (orquestrador, depois das Tasks 1–6 revisadas)

1. Do worktree, com a raiz do repositório no checkout principal: `python -m scripts.drawing_model_report --raiz <checkout principal>/examples --saida <checkout principal>/tmp/e04/relatorio-modelo.json --amostras-imagem <checkout principal>/tmp/e04/imagens --raiz-repositorio <checkout principal>`.
2. Famílias: a distribuição nas 16 folhas precisa ser 8 `electric_office_print`, 6 `itext`, 1 `ghostscript`, 1 `autocad`. Divergência → ajuste do critério (nova rodada de correção da Task 2/3, com `VERSAO_MODELO_DESENHO` incrementada) antes de fechar.
3. H3: o orquestrador inspeciona as amostras `outra`, `anotacao` e os ladrilhos amostrados. H3 vale se os ladrilhos amostrados mostram só a ortofoto (nenhuma rede, símbolo ou texto queimado no raster) e nenhuma imagem `outra` contém símbolo ou texto da rede; o resultado (contagens por classe e o que as amostras mostram) vai ao handoff.
4. DXF de 2 folhas reais de famílias diferentes em `tmp/e04/`, para inspeção do usuário quando possível.
5. Tempo e memória por folha no handoff (risco da etapa).
6. Handoff para as próximas etapas: quando E05–E07 levarem o modelo ao analisador, `VERSAO_MODELO_DESENHO` entra na assinatura de capacidade e na versão do extrator (ADR 0004, ADR 0006); se `application/` precisar dos tipos do modelo, eles migram para `ports/`; no AutoCAD o SHX também chega como traço vetorial e vai gerar polilinhas e grupos que duplicam o texto (nota para a E06); a linha de "Fronteiras" do design sobre locks fica como pendência do arquiteto.

## Revisão de arquitetura

- **Veredito:** aprovado com notas, na rodada 2 (`revisor-arquitetura`, modelo opus).
- **Rodadas:** 2. Rodada 0 bloqueou com 6 Importantes (modelo descartava contornos e Béziers que a E05/E06 consomem; texto de anotação como nativo; camada do texto indefinida; fronteira do ezdxf sem guarda; método da H3 cego a raster; regras de família sem conferência nas folhas reais) e 12 Menores; rodada 1 resolveu todos e bloqueou com 3 Importantes novos (guarda de `application/` × PIL; ladrilhos fora da inspeção da H3; preenchidos fora dos grupos); rodada 2 aprovou.
- **Notas Menores da rodada 2:** caminho preenchido com arco parcial e curva traçada que não é círculo ficavam fora dos grupos — aplicadas no texto da Task 2 (`agrupar_candidatos`), com dois testes a mais.
- **Não verificado pelo revisor:** se `get_texttrace()` da PyMuPDF 1.28 expõe `layer` (o plano prevê a alternativa) e o comportamento de `_is_glyph` com `get_drawings(extended=True)` depois de filtrar `clip`/`group`.
