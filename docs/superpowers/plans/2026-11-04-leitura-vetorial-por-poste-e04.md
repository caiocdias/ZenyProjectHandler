# E04 — Modelo de desenho e perfis de família — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cada página de PDF vira um modelo de desenho derivado (texto nativo e SHX, polilinhas reconstruídas, círculos e arcos recuperados de Béziers, grupos candidatos a símbolo, com camada, cor e espessura), a família do PDF é reconhecida por impressão estrutural, o modelo entra num cache derivado com versão própria e um script exporta o modelo em DXF de depuração.

**Architecture:** um pacote novo `zeny_project_handler/adapters/analysis/drawing_model/` com tipos e algoritmos puros (sem PyMuPDF: `model.py`, `geometry.py`, `groups.py`, `family.py`, `cache.py`) e um único módulo PyMuPDF (`pymupdf_drawing_model.py`) que lê a página e monta o modelo. O analisador padrão, as evidências, as propostas e as versões de extrator e interpretador não mudam: nesta etapa o modelo só é produzido sob demanda (scripts e testes) e consumido pelas etapas E05–E07. Dois scripts em `scripts/`: o DXF de depuração (ezdxf) e o relatório sobre as folhas reais (H3, tempo e memória), que grava só em `tmp/`.

**Tech Stack:** Python 3.11–3.13, PyMuPDF 1.28.x (só no módulo `pymupdf_*`), ezdxf (MIT, nova dependência de desenvolvimento), pytest, mypy strict, ruff.

**Spec:** seção "E04 — Modelo de desenho e perfis de família" de `docs/roadmap-leitura-vetorial-por-poste.md`; design `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (decisões 1 e 2, "O que os PDFs reais mostram", "Fronteiras"); ADR 0016; ADR 0004 (cache derivado, coordenadas da página visual).

## Global Constraints

- Arquitetura hexagonal: domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf; o cliente não importa nada do servidor (`client_artifact_gate`); DTOs seguem `tests/contracts/test_architecture.py`. Esta etapa não toca `domain/`, `application/`, `ports/`, contratos, API nem cliente.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`; o analisador padrão não muda, então nenhuma versão de extrator/interpretador é incrementada (ADR 0006) e nenhuma migração SQLite é feita.
- PDFs reais, recortes, DXF de folhas reais, rótulos e pesos nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa, gerada no próprio teste com PyMuPDF.
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro: feche documentos PyMuPDF (`with pymupdf.open(...)`) e arquivos.
- Dependências novas: ezdxf, licença MIT, só em lock de desenvolvimento ou de experimentos, nunca no cliente. Decisão desta etapa: `ezdxf` entra em `requirements-development.lock` (o gate precisa abrir o DXF da fixture) e em `requirements-experiments.lock`; o módulo que importa ezdxf fica só em `scripts/`.
- Documentação enxuta: atualize só o que a mudança torna falso (`CLAUDE.md` ganha uma linha sobre o modelo de desenho e os dois scripts). Nada de histórico de execução em arquivo versionado.
- Coordenadas do modelo: espaço da **página visual** (rotação intrínseca `/Rotate` aplicada, origem no canto superior esquerdo, unidade ponto PDF), com `largura` e `altura` da página visual no modelo, como o ADR 0004 pede para candidatos.
- Arquivos gravados pelos scripts em `tmp/` não trazem caminho absoluto nem nome do PDF: só `sha256` (e índice da página).

## Review Focus

- Página com `/Rotate 90/180/270`: textos, polilinhas e círculos saem no espaço da página visual, não no espaço não rotacionado. Teste: `test_extrai_modelo_em_pagina_rotacionada` (Task 3), com `/Rotate 90` e `/Rotate 270`.
- Segmentos colineares e contíguos com camada, cor, espessura ou tracejado diferentes não são fundidos numa polilinha. Teste: `test_nao_funde_segmentos_de_estilo_diferente` (Task 1).
- Quatro Béziers que formam uma elipse (raios diferentes) ou um arco que não fecha não viram círculo. Testes: `test_elipse_nao_vira_circulo` e `test_quarto_de_circulo_vira_arco` (Task 1).
- Página vazia, página só com imagem e documento com várias páginas: o modelo tem uma entrada por página, listas vazias onde não há nada, sem exceção. Teste: `test_modelo_de_pagina_vazia_e_multipagina` (Task 3).
- Folha real com dezenas de milhares de primitivas: a fusão de polilinhas e o agrupamento não podem ser quadráticos. Teste: `test_fusao_e_agrupamento_escalam` (Task 1/Task 2), com 20 000 segmentos sintéticos em grade e limite de 10 s; o tempo e a memória reais vão para o relatório da Task 6.

---

### Task 1: Tipos do modelo e geometria pura (polilinhas, círculos e arcos)

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/drawing_model/__init__.py`, `.../drawing_model/model.py`, `.../drawing_model/geometry.py`
- Test: `tests/unit/test_drawing_model_geometry.py`

**Interfaces:**
- Produces (em `model.py`, dataclasses `frozen=True, slots=True`, só stdlib):
  - `Estilo(camada: str, cor: tuple[float, float, float] | None, preenchimento: tuple[float, float, float] | None, espessura: float, tracejado: str)`;
  - `Segmento(p0: tuple[float, float], p1: tuple[float, float], estilo: Estilo)`;
  - `Bezier(p0, c1, c2, p1: tuple[float, float], estilo: Estilo)`;
  - `Polilinha(pontos: tuple[tuple[float, float], ...], fechada: bool, estilo: Estilo)`;
  - `Circulo(centro: tuple[float, float], raio: float, estilo: Estilo)`;
  - `Arco(centro: tuple[float, float], raio: float, angulo_inicial: float, angulo_final: float, estilo: Estilo)` (graus, sentido anti-horário no espaço da página visual com y para baixo convertido como em DXF: documente a convenção no docstring);
  - `TextoModelo(texto: str, bbox: tuple[float, float, float, float], origem: Literal["nativo", "shx"], rotacao: float, altura: float, fonte: str, camada: str)`;
  - `GrupoCandidato(bbox: tuple[float, float, float, float], indices_primitivas: tuple[int, ...])` (índices na lista `primitivas` da página);
  - `PaginaModelo(indice: int, largura: float, altura: float, textos: tuple[TextoModelo, ...], primitivas: tuple[Polilinha | Circulo | Arco, ...], grupos: tuple[GrupoCandidato, ...], imagens: tuple[ImagemModelo, ...], beziers_soltas: int)` (`beziers_soltas` = Béziers que não viraram círculo nem arco; não entram em `primitivas`);
  - `ImagemModelo(bbox: tuple[float, float, float, float], largura_px: int, altura_px: int, sha256: str)`;
  - `ModeloDesenho(versao: str, documento_sha256: str, familia: PerfilFamilia, paginas: tuple[PaginaModelo, ...])` — `PerfilFamilia` vem da Task 2; nesta tarefa declare-o em `model.py` como `PerfilFamilia(familia: str, sinais: Mapping[str, JsonPrimitive], diagnosticos: tuple[str, ...])` e a Task 2 só o preenche;
  - `VERSAO_MODELO_DESENHO: Final = "modelo-desenho-v1"`.
- Produces (em `geometry.py`, funções puras):
  - `reconstruir_polilinhas(segmentos: Sequence[Segmento], *, tolerancia_ponto: float = 0.5, tolerancia_angulo_graus: float = 1.0) -> tuple[Polilinha, ...]`: funde segmentos de **mesmo `Estilo`** que se tocam (extremos a até `tolerancia_ponto`) e são colineares (desvio angular até `tolerancia_angulo_graus`) num só segmento; depois encadeia segmentos contíguos de mesmo estilo em polilinhas (fechada quando volta ao início). Use índice espacial por grade (dicionário de células de `tolerancia_ponto`) para não ser quadrático.
  - `recuperar_circulos_e_arcos(beziers: Sequence[Bezier], *, tolerancia_relativa: float = 0.02) -> tuple[tuple[Circulo | Arco, ...], tuple[Bezier, ...]]`: devolve os círculos/arcos reconhecidos e as Béziers que sobraram. Uma Bézier é arco de círculo quando os 2 extremos e o ponto em t=0,5 caem num círculo comum e os pontos em t=0,25 e t=0,75 também (desvio radial ≤ `tolerancia_relativa` × raio). Arcos contíguos de mesmo estilo, mesmo centro e mesmo raio são unidos; a união que cobre 360° vira `Circulo`.

- [ ] **Step 1: Write the failing tests**

```python
def test_segmentos_colineares_fragmentados_viram_uma_polilinha() -> None:
    e = Estilo("REDE", (0, 0, 0), None, 1.0, "")
    segs = [Segmento((0, 0), (10, 0), e), Segmento((10, 0), (25, 0), e), Segmento((25.2, 0), (40, 0), e)]
    (p,) = reconstruir_polilinhas(segs)
    assert p.pontos == ((0, 0), (40, 0)) and not p.fechada
def test_segmentos_em_l_viram_polilinha_de_tres_pontos() -> None: ...
def test_quadrado_vira_polilinha_fechada() -> None: ...
def test_nao_funde_segmentos_de_estilo_diferente() -> None:
    # mesmo traçado, um com camada "A" e outro "B" (e variantes: cor, espessura, tracejado) → 2 polilinhas
def test_circulo_em_quatro_beziers_vira_circulo() -> None:
    # aproximação clássica k = 0.5523 de um círculo de raio 5 em (50, 50)
    (c,), resto = recuperar_circulos_e_arcos(quatro_beziers_de_circulo((50, 50), 5))
    assert isinstance(c, Circulo) and c.centro == pytest.approx((50, 50), abs=1e-3) and c.raio == pytest.approx(5, rel=1e-3) and resto == ()
def test_quarto_de_circulo_vira_arco() -> None: ...   # só 1 das 4 Béziers → Arco de 90°
def test_elipse_nao_vira_circulo() -> None: ...       # raios 5 e 8 → nenhuma forma, 4 Béziers no resto
def test_curva_s_nao_vira_arco() -> None: ...
def test_fusao_e_agrupamento_escalam() -> None:
    # 20 000 segmentos de 1 pt em 200 linhas paralelas de mesmo estilo → 200 polilinhas em < 10 s
```

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/unit/test_drawing_model_geometry.py -q` → FAIL (módulos inexistentes).
- [ ] **Step 3: Implement** `model.py` e `geometry.py` conforme as interfaces.
- [ ] **Step 4: Run** o arquivo de teste → PASS; `ruff check`, `ruff format --check`, `mypy` → limpos.
- [ ] **Step 5: Commit** `feat(analise): tipos do modelo de desenho e geometria pura`.

---

### Task 2: Perfil por família e grupos candidatos a símbolo

**Files:**
- Create: `.../drawing_model/family.py`, `.../drawing_model/groups.py`
- Test: `tests/unit/test_drawing_model_family.py`, `tests/unit/test_drawing_model_groups.py`

**Interfaces:**
- Consumes: Task 1 (`PerfilFamilia`, primitivas, `GrupoCandidato`).
- Produces:
  - `ImpressaoEstrutural(produtor: str, criador: str, nomes_ocg: tuple[str, ...], spans_texto_nativo: int, formas_pequenas_preenchidas: int, anotacoes_shx: int, imagens: int)` (dataclass pura, preenchida pela Task 3);
  - constantes `FAMILIAS: Final = ("electric_office_print", "itext", "ghostscript", "autocad", "generico")` e `LIMIAR_FORMAS_GLIFO: Final = 300`;
  - `reconhecer_familia(impressao: ImpressaoEstrutural) -> PerfilFamilia`, por regras nesta ordem: `autocad` se `"pdfplot"` ou `"autocad"` no produtor/criador (sem diferenciar maiúsculas), ou `anotacoes_shx > 0`, ou houver OCGs; `itext` se `"itext"` no produtor; `ghostscript` se `"ghostscript"` no produtor; `electric_office_print` se `"print to pdf"` no produtor **e** `formas_pequenas_preenchidas >= LIMIAR_FORMAS_GLIFO`; senão `generico` com diagnóstico `"familia.desconhecida"`. `"print to pdf"` sem o sinal de glifos também cai em `generico`, com diagnóstico `"familia.print_to_pdf_sem_glifos"` (o produtor sozinho não identifica o Electric Office). `sinais` guarda os números da impressão (sem produtor bruto se ele trouxer caminho);
  - `agrupar_candidatos(primitivas: Sequence[Polilinha | Circulo | Arco], *, folga: float = 1.5, lado_maximo: float = 40.0) -> tuple[GrupoCandidato, ...]`: une primitivas cujas caixas, dilatadas por `folga`, se tocam (union-find com grade espacial); descarta grupos cujo lado maior passa de `lado_maximo` pt (traçado da rede, não símbolo) e grupos de uma só polilinha aberta de dois pontos (segmento solto).

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize(("impressao", "familia"), [...])  # um caso positivo por família
def test_reconhece_cada_familia(impressao, familia) -> None: ...
def test_print_to_pdf_sem_glifos_cai_no_generico_com_diagnostico() -> None: ...
def test_familia_desconhecida_cai_no_generico_com_diagnostico() -> None:
    perfil = reconhecer_familia(ImpressaoEstrutural("LibreOffice", "", (), 10, 0, 0, 0))
    assert perfil.familia == "generico" and "familia.desconhecida" in perfil.diagnosticos
def test_ocg_ou_shx_identifica_autocad_mesmo_com_outro_produtor() -> None: ...
def test_agrupa_circulo_e_tracos_proximos_num_grupo() -> None: ...
def test_nao_agrupa_formas_distantes() -> None: ...
def test_descarta_grupo_maior_que_lado_maximo() -> None: ...   # linha longa da rede
def test_agrupamento_escala() -> None: ...                     # 20 000 círculos pequenos em grade < 10 s
```

- [ ] **Step 2–4:** FAIL → implementar → PASS; ruff, format, mypy.
- [ ] **Step 5: Commit** `feat(analise): perfil por família e grupos candidatos a símbolo`.

---

### Task 3: Extração PyMuPDF do modelo de desenho

**Files:**
- Create: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py`
- Test: `tests/unit/test_pymupdf_drawing_model.py` (gera os PDFs sintéticos no teste)

**Interfaces:**
- Consumes: Tasks 1 e 2.
- Produces:
  - `impressao_estrutural(documento: pymupdf.Document) -> ImpressaoEstrutural` (OCGs por `documento.get_ocgs()`; SHX = anotações cujo título, assunto ou conteúdo marca `"AutoCAD SHX Text"`; "forma pequena preenchida" = desenho com preenchimento e caixa de lado ≤ 3 pt);
  - `extrair_modelo_desenho(pdf: Path) -> ModeloDesenho`: abre com `with`, calcula o sha256 do arquivo, reconhece a família, e por página: textos nativos por span (`get_text("rawdict")`: texto, bbox, rotação pela direção da linha, altura pelo tamanho da fonte, fonte, camada vazia), textos SHX das anotações (`origem="shx"`, bbox da anotação), segmentos/Béziers/retângulos de `get_drawings()` (retângulo vira 4 segmentos; `quad` idem) com `Estilo` a partir de `layer`, `color`, `fill`, `width`, `dashes`; imagens por `get_image_info(hashes=True)`. Tudo é transformado para a página visual com `page.rotation_matrix` antes da geometria; depois `reconstruir_polilinhas`, `recuperar_circulos_e_arcos` (as Béziers que sobram só são contadas em `PaginaModelo.beziers_soltas`) e `agrupar_candidatos`.

- [ ] **Step 1: Write the failing tests** (cada PDF sintético é gerado com PyMuPDF dentro do teste; nada de `examples/`)

```python
def test_extrai_texto_nativo_com_posicao_rotacao_e_altura(tmp_path) -> None: ...
def test_extrai_texto_shx_de_anotacao(tmp_path) -> None: ...
def test_segmentos_fragmentados_do_pdf_viram_uma_polilinha(tmp_path) -> None:
    # três draw_line colineares e contíguos de mesma cor → 1 Polilinha com 2 pontos
def test_circulo_desenhado_com_beziers_vira_circulo(tmp_path) -> None:
    # page.draw_circle (PyMuPDF desenha com 4 Béziers) → 1 Circulo com centro e raio esperados
def test_camada_ocg_vai_para_o_estilo(tmp_path) -> None: ...   # desenho dentro de OCG "P" → estilo.camada == "P"
def test_extrai_modelo_em_pagina_rotacionada(tmp_path) -> None: ...   # /Rotate 90 e 270
def test_modelo_de_pagina_vazia_e_multipagina(tmp_path) -> None: ...
def test_fixture_de_cada_familia_e_reconhecida(tmp_path) -> None:
    # metadados producer/creator, OCG, SHX e 400 quadradinhos preenchidos montam as 4 famílias e o genérico
def test_documento_fechado_sem_resourcewarning(tmp_path) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar → PASS; ruff, format, mypy.
- [ ] **Step 5: Commit** `feat(analise): extração PyMuPDF do modelo de desenho`.

---

### Task 4: Cache derivado do modelo com versão própria

**Files:**
- Create: `.../drawing_model/cache.py`
- Modify: `src/zeny_project_handler/adapters/analysis/pymupdf_drawing_model.py` (função de entrada com cache)
- Test: `tests/unit/test_drawing_model_cache.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `chave_modelo_desenho(documento_sha256: str, versao: str = VERSAO_MODELO_DESENHO) -> str` (sha256 de `f"{documento_sha256}:{versao}"`);
  - `JsonDrawingModelCache(diretorio: Path)` com `obter(chave: str) -> ModeloDesenho | None` e `salvar(chave: str, modelo: ModeloDesenho) -> None`: um JSON por chave em `diretorio / "modelo-desenho"`, gravação atômica (arquivo temporário + `os.replace`), `schema_version` próprio; JSON corrompido, versão diferente ou esquema diferente → `None` (falha de cache nunca derruba a extração, como no ADR 0004);
  - `obter_modelo_desenho(pdf: Path, cache: JsonDrawingModelCache | None) -> ModeloDesenho` em `pymupdf_drawing_model.py`: calcula o sha, tenta o cache, extrai e salva quando falta.

- [ ] **Step 1: Write the failing tests**

```python
def test_ida_e_volta_preserva_o_modelo(tmp_path) -> None: ...          # salvar → obter == modelo original
def test_segunda_chamada_usa_o_cache_sem_reextrair(tmp_path, monkeypatch) -> None: ...
def test_versao_diferente_invalida_o_cache(tmp_path) -> None: ...
def test_json_corrompido_e_ignorado(tmp_path) -> None: ...
def test_gravacao_atomica_nao_deixa_arquivo_parcial(tmp_path, monkeypatch) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar → PASS; ruff, format, mypy.
- [ ] **Step 5: Commit** `feat(analise): cache derivado do modelo de desenho com versão própria`.

---

### Task 5: DXF de depuração (ezdxf como dependência de desenvolvimento)

**Files:**
- Create: `scripts/drawing_model_dxf.py`
- Modify: `requirements-development.lock`, `requirements-experiments.lock` (linha `ezdxf==<versão estável atual>` e suas dependências transitivas que ainda não estiverem fixadas), `CLAUDE.md` (uma linha na lista de comandos)
- Test: `tests/unit/test_drawing_model_dxf.py`

**Interfaces:**
- Consumes: `obter_modelo_desenho` (Task 4).
- Produces: CLI `python -m scripts.drawing_model_dxf PDF --saida ARQUIVO.dxf [--pagina N] [--cache DIR]` e função `exportar_dxf(modelo: ModeloDesenho, pagina: int, destino: Path) -> None`: uma camada DXF por `Estilo.camada` (camada vazia vira `"0"`; nomes saneados para o DXF), `TEXT` por `TextoModelo` (posição, altura e rotação), `LWPOLYLINE` por `Polilinha`, `CIRCLE`, `ARC`, e um retângulo na camada `"GRUPOS_CANDIDATOS"` por grupo; eixo y invertido para o DXF (y para cima). Cor ACI aproximada da cor RGB é opcional; a camada é obrigatória.

- [ ] **Step 1: Write the failing tests**

```python
def test_dxf_da_fixture_abre_com_ezdxf_e_preserva_camadas_e_textos(tmp_path) -> None:
    # PDF sintético com OCG "P" (linha + círculo) e OCG "NOTAS" (texto "P1 U3(1)")
    exportar_dxf(obter_modelo_desenho(pdf, None), 0, destino)
    doc = ezdxf.readfile(destino)
    assert {"P", "NOTAS"} <= {layer.dxf.name for layer in doc.layers}
    assert any(t.dxf.text == "P1 U3(1)" and t.dxf.layer == "NOTAS" for t in doc.modelspace().query("TEXT"))
    assert len(doc.modelspace().query("CIRCLE")) == 1
def test_cli_grava_dxf_e_recusa_pagina_inexistente(tmp_path) -> None: ...
def test_nome_de_camada_invalido_e_saneado(tmp_path) -> None: ...
```

- [ ] **Step 2:** instalar a nova dependência no `.venv` (`.venv/Scripts/python.exe -m pip install ezdxf==<versão>`), rodar o teste → FAIL (script inexistente).
- [ ] **Step 3: Implement** o script; acrescente as linhas aos dois locks (versões exatas do que foi instalado, `pip check` limpo).
- [ ] **Step 4: Run** o teste → PASS; `pip check`, ruff, format, mypy; `scripts/client_artifact_gate.py --source-only` limpo.
- [ ] **Step 5: Commit** `feat(scripts): DXF de depuração do modelo de desenho`.

---

### Task 6: Relatório das folhas reais (H3, custo) — script e teste sintético

**Files:**
- Create: `scripts/drawing_model_report.py`
- Modify: `CLAUDE.md` (mesma linha da Task 5 ou a seguinte)
- Test: `tests/unit/test_drawing_model_report.py`

**Interfaces:**
- Consumes: `extrair_modelo_desenho` e `impressao_estrutural` (Task 3).
- Produces: CLI `python -m scripts.drawing_model_report --raiz DIR --saida ARQUIVO.json` e função `medir_pdf(pdf: Path) -> dict[str, Any]` com, por PDF: `sha256`, família e sinais, por página: número de textos (nativo/SHX), polilinhas, círculos, arcos, Béziers soltas, grupos, e as imagens (quantidade, lado em pixels mínimo/mediano/máximo, fração da página coberta pela união das caixas, quantas imagens têm lado ≤ 64 px e quantas caixas de imagem cruzam algum grupo candidato); tempo (`time.perf_counter`) e pico de memória (`tracemalloc`) da extração. A saída JSON não traz caminho nem nome de PDF; recusa `--saida` fora de `tmp/` do repositório informado por `--raiz-repositorio` (padrão: diretório atual).

- [ ] **Step 1: Write the failing tests**

```python
def test_medir_pdf_sintetico_conta_primitivas_e_imagens(tmp_path) -> None: ...
def test_relatorio_nao_tem_caminho_nem_nome_do_pdf(tmp_path) -> None: ...
def test_cli_recusa_saida_fora_de_tmp(tmp_path) -> None: ...
```

- [ ] **Step 2–4:** FAIL → implementar → PASS; ruff, format, mypy.
- [ ] **Step 5: Commit** `feat(scripts): relatório do modelo de desenho sobre folhas reais`.

---

## Execução operacional (orquestrador, depois das Tasks 1–6 revisadas)

1. `python -m scripts.drawing_model_report --raiz <examples do checkout principal> --saida <checkout principal>/tmp/e04/relatorio-modelo.json` (rodado do worktree, com `--raiz-repositorio` no checkout principal).
2. H3: a partir do relatório, decidir se as imagens das folhas Print To PDF e iText são só ladrilhos da ortofoto (critério: imagens grandes, em grade, cobrindo a área do mapa, nenhuma pequena cruzando grupo candidato). Resultado no handoff.
3. DXF de 2 folhas reais de famílias diferentes em `tmp/e04/`, para inspeção do usuário quando possível.
4. Tempo e memória por folha no handoff (risco da etapa).

## Revisão de arquitetura

(preenchida pelo orquestrador após a revisão)
