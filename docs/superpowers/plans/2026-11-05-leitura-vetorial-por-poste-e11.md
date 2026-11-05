# E11 — Spike de treino na GPU AMD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** decidir onde treinar o detector da E12 (ROCm nativo no Windows, WSL2, CPU ou GPU alugada), provando a cadeia treino → ONNX → inferência em CPU com ONNX Runtime e medindo tempos, e registrar a decisão no ADR 0017.

**Architecture:** spike fora do produto. Um pacote novo `scripts/treino_detector/` concentra o ensaio: partes puras (dados sintéticos, métricas, sonda de ambiente) testadas no gate com o `.venv` de desenvolvimento, e partes com PyTorch/ONNX (`ensaio.py`) que só rodam nos ambientes de treino descartáveis em `tmp/treino-e11/` do checkout principal e nunca são importadas pelo gate. Um lock opt-in `requirements-treino.lock` fixa o ambiente do caminho escolhido. Nada em `src/` muda.

**Tech Stack:** Python 3.11 (gate) e o Python que os wheels de treino exigirem; numpy 2.3.5 e Pillow 13.0.0 (já no lock de dev); PyTorch + torchvision (BSD-3) com ROCm para Windows (wheels oficiais da AMD) e build CPU de `download.pytorch.org/whl/cpu`; `onnx` e `onnxruntime` (MIT) só nos ambientes de treino.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E11 — Spike de treino na GPU AMD"; design `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (decisão 5) e `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md` (trilhas); `docs/adr/0017-detector-visual-local-e-rotulagem-assistida.md`.

**Laboratório:** não. Nenhuma tarefa ajusta limiar ou heurística contra folhas reais; o ensaio usa só dados sintéticos.

**Estimativa:** Task 1 ≈ 40 min; Task 2 ≈ 70 min (downloads de wheels de vários GB); Task 3 ≈ 70 min. Total ≈ 3h.

## Global Constraints

- Spike sem código de produção: nada em `src/`, nenhum import de `scripts.treino_detector` em `src/` e nenhuma dependência nova em `requirements-server.lock`, `requirements-client*.lock`, `requirements-development.lock`, `requirements.lock`, `requirements-experiments.lock`, `pyproject.toml`, `server/pyproject.toml`, `client/pyproject.toml`, `Dockerfile`, `setup.bat` ou `IniciarTestes.bat`.
- Arquivos proibidos nesta etapa (a E14 da trilha A pode estar editando): `pyproject.toml`, todos os locks existentes, `tests/conftest.py`, `tests/unit/test_dependency_locks.py`, `CLAUDE.md`, `.bat`, contrato de curadoria. Só arquivos novos em `scripts/treino_detector/` e `tests/unit/test_treino_detector_*.py`, o lock novo `requirements-treino.lock` e `docs/adr/0017-detector-visual-local-e-rotulagem-assistida.md`.
- Licença de modelo e código de treino: Apache-2.0, BSD ou MIT. YOLO Ultralytics (AGPL) está excluído. Pesos pré-treinados não são baixados (`weights=None`, `weights_backbone=None`).
- Dados do ensaio: só sintéticos, gerados por `scripts/treino_detector/dados_sinteticos.py`. Nunca ler `examples/`, `examples/avaliacao-cega/` nem nada derivado de folha real.
- Ambientes, wheels, conjuntos, pesos, ONNX e relatórios ficam em `C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\treino-e11\` (ignorado pelo Git). Nada disso é commitado.
- Instalação permitida (ruling do orquestrador, por delegação do usuário: só o que é contido e reversível apagando uma pasta): `pip install` em venvs sob `tmp\treino-e11\`; e, se os wheels exigirem uma versão de Python ausente, `py install 3.12` (ou a versão exigida) no escopo do usuário. **Proibido sem decisão do usuário:** atualizar driver AMD, instalar o ROCm/HIP SDK no sistema, instalar distro WSL, habilitar recurso do Windows, mexer em variáveis de ambiente do sistema.
- Fonte dos wheels ROCm: preferir o índice de release oficial da AMD para Windows (`repo.radeon.com`); índice nightly (`rocm.nightlies.amd.com`, TheRock) só se nenhuma release suportar a gfx1201 (RX 9070 XT), e o relatório registra qual foi usado.
- `requirements-treino.lock` é varrido por `tests/unit/test_dependency_locks.py` (`ROOT.glob("requirements*.lock")`): se fixar `Pillow`, `setuptools` ou `wheel`, use exatamente `Pillow==13.0.0`, `setuptools==84.1.0`, `wheel==0.46.2`; pinos só com `==`; linhas de índice começam com `--`.
- ROCm no PyTorch expõe a GPU como `torch.cuda` e preenche `torch.version.hip`.
- Gate: `ruff check .`, `ruff format --check .` e `mypy` (strict, cobre `src` e `tests`, e portanto os módulos de `scripts/treino_detector/` importados pelos testes) precisam passar. Os testes não importam `torch`, `torchvision`, `onnx` nem `onnxruntime`, direta ou indiretamente (o `.venv` de dev não os tem).
- Suíte conhecida: em `main`, `tests/unit/test_glyph_text_orcamento.py::test_pagina_hostil_acima_do_teto_de_resolucoes_e_limitada_em_tempo_limitado` reprova por tempo de parede (pré-existente, a E14 corrige). Não é desta etapa: não tocar, relatar se for a única falha.
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro: feche imagens Pillow e arquivos.
- Documentação enxuta: nada de histórico de execução em arquivo versionado. Uso dos scripts nos docstrings dos módulos; decisão e números no ADR 0017.
- Se o harness recusar um comando (por exemplo `wsl.exe` ou `powershell.exe`), não contorne: registre a recusa no relatório como "não sondado" e siga.

## Review Focus

1. GPU visível mas com resultado numérico errado (ROCm que treina "lixo") → o ensaio exige recall e precisão ≥ 0,80 no conjunto sintético de validação antes de declarar o caminho viável (Task 3, `criterio_qualidade`).
2. ONNX exportado que roda mas diverge do PyTorch → paridade obrigatória: mesmas detecções com score ≥ 0,30 casadas com IoU ≥ 0,99 (Task 1, `deteccoes_equivalentes`; Task 3 aplica).
3. Ambiente de treino sem GPU (driver ausente, wheel sem a gfx1201) → a sonda devolve `gpu_disponivel=False` com o motivo, sem exceção (Task 2, teste com módulo falso que levanta erro).
4. Lock de treino que entra no runtime por acidente (`-r` em outro lock, citação no `Dockerfile`/`setup.bat`) → teste de isolamento (Task 2).
5. Dados sintéticos com caixa fora da imagem ou degenerada, que mascaram erro do treino → teste de geometria das anotações (Task 1).

---

### Task 1: Dados sintéticos e métricas puras do ensaio

**Files:**
- Create: `scripts/treino_detector/__init__.py` (docstring do pacote: propósito, aviso "fora do produto", como montar o venv a partir de `requirements-treino.lock` e rodar `python -m scripts.treino_detector.ensaio`; completado na Task 3)
- Create: `scripts/treino_detector/dados_sinteticos.py`
- Create: `scripts/treino_detector/metricas.py`
- Test: `tests/unit/test_treino_detector_dados.py`, `tests/unit/test_treino_detector_metricas.py`

**Interfaces:**
- Produces (`dados_sinteticos.py`, só numpy e Pillow):
  - `CLASSES: tuple[str, ...] = ("circulo", "triangulo", "quadrado", "cruz")` — rótulo 1..4 na ordem (0 é fundo, convenção do torchvision).
  - `@dataclass(frozen=True) class Anotacao: caixa: tuple[float, float, float, float]` (x0, y0, x1, y1 em pixels) `; rotulo: int`.
  - `@dataclass(frozen=True) class AmostraSintetica: imagem: numpy.ndarray` (H×W×3, `uint8`) `; anotacoes: tuple[Anotacao, ...]`.
  - `gerar_amostra(semente: int, lado: int = 320, max_simbolos: int = 6) -> AmostraSintetica` — fundo claro com ruído e linhas finas (imitando traço de rede), de 1 a `max_simbolos` símbolos de lado entre 16 e 48 px, contorno preto, sem sobreposição de caixas (IoU = 0 entre quaisquer duas). Determinística pela semente (`numpy.random.default_rng(semente)`).
  - `gerar_conjunto(semente: int, quantidade: int, lado: int = 320) -> list[AmostraSintetica]` — amostra `i` usa semente derivada `semente * 1_000_003 + i`.
- Produces (`metricas.py`, só stdlib):
  - `iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float`.
  - `@dataclass(frozen=True) class Deteccao: caixa: tuple[float, float, float, float]; rotulo: int; score: float`.
  - `@dataclass(frozen=True) class ResultadoAvaliacao: verdadeiros: int; falsos_positivos: int; falsos_negativos: int` com propriedades `precisao: float` e `recall: float` (0.0 quando o denominador é 0).
  - `avaliar(predicoes: Sequence[Sequence[Deteccao]], verdade: Sequence[Sequence[Anotacao]], iou_minimo: float = 0.5, score_minimo: float = 0.5) -> ResultadoAvaliacao` — casamento guloso por imagem, por score decrescente, mesma classe, cada verdade casada uma vez.
  - `deteccoes_equivalentes(a: Sequence[Deteccao], b: Sequence[Deteccao], score_minimo: float = 0.30, iou_minimo: float = 0.99) -> bool` — após filtrar por score, mesma quantidade e cada detecção de `a` casa com uma de `b` de mesma classe e IoU ≥ `iou_minimo`.
  - `@dataclass(frozen=True) class ResumoTempo: amostras: int; mediana_s: float; p95_s: float; total_s: float` e `resumir_tempos(tempos_s: Sequence[float]) -> ResumoTempo` (p95 pelo método "nearest-rank"; `ValueError` em sequência vazia).
  - `ladrilhos_por_folha(largura_px: int, altura_px: int, lado: int = 320, sobreposicao: float = 0.10) -> int` — passo `round(lado * (1 - sobreposicao))`, ladrilhos por eixo `ceil(max(dim - lado, 0) / passo) + 1`.

- [ ] **Step 1: Escreva os testes que falham**

```python
# tests/unit/test_treino_detector_dados.py
def test_amostra_e_deterministica_pela_semente():
    a, b = gerar_amostra(7), gerar_amostra(7)
    assert numpy.array_equal(a.imagem, b.imagem) and a.anotacoes == b.anotacoes
    assert not numpy.array_equal(gerar_amostra(8).imagem, a.imagem)

def test_caixas_dentro_da_imagem_nao_degeneradas_e_sem_sobreposicao():
    for amostra in gerar_conjunto(3, 50):
        assert amostra.imagem.shape == (320, 320, 3) and amostra.imagem.dtype == numpy.uint8
        assert 1 <= len(amostra.anotacoes) <= 6
        for anot in amostra.anotacoes:
            x0, y0, x1, y1 = anot.caixa
            assert 0 <= x0 < x1 <= 320 and 0 <= y0 < y1 <= 320
            assert 16 <= x1 - x0 <= 48 and 1 <= anot.rotulo <= len(CLASSES)
        assert all(iou(p.caixa, q.caixa) == 0 for p, q in itertools.combinations(amostra.anotacoes, 2))

def test_simbolo_deixa_tinta_escura_dentro_da_caixa():
    # cada caixa contém pixels escuros (< 80) do contorno do símbolo
```

```python
# tests/unit/test_treino_detector_metricas.py
def test_iou_casos_basicos():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (10, 0, 20, 10)) == 0.0
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)

def test_avaliar_conta_classe_errada_e_duplicata_como_falso_positivo(): ...
def test_avaliar_ignora_predicao_abaixo_do_score(): ...
def test_avaliar_sem_predicoes_tem_precisao_zero_e_recall_zero(): ...
def test_deteccoes_equivalentes_aceita_ruido_minimo_e_rejeita_caixa_deslocada(): ...
def test_deteccoes_equivalentes_rejeita_quantidade_diferente_acima_do_score(): ...
def test_resumir_tempos_mediana_p95_e_vazio():
    r = resumir_tempos([float(i) for i in range(1, 21)])
    assert (r.amostras, r.mediana_s, r.p95_s, r.total_s) == (20, 10.5, 19.0, 210.0)
    with pytest.raises(ValueError): resumir_tempos([])

def test_ladrilhos_por_folha():
    assert ladrilhos_por_folha(320, 320) == 1
    assert ladrilhos_por_folha(100, 100) == 1
    assert ladrilhos_por_folha(9933, 7016) == 35 * 25
```

- [ ] **Step 2: Rode e veja falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_treino_detector_dados.py tests/unit/test_treino_detector_metricas.py -v`
Expected: FAIL (`ModuleNotFoundError: scripts.treino_detector`).

- [ ] **Step 3: Implemente `dados_sinteticos.py` e `metricas.py` com as assinaturas acima**

Desenho com `PIL.ImageDraw` sobre `Image.new("RGB", ...)`, convertido para `numpy.asarray(..., dtype=uint8)`; sorteio de posição com rejeição (até 50 tentativas por símbolo) para garantir IoU 0.

- [ ] **Step 4: Rode os testes, ruff e mypy**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_treino_detector_dados.py tests/unit/test_treino_detector_metricas.py -v` → PASS; `.venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m ruff format --check . && .venv/Scripts/python.exe -m mypy` → sem erros.

- [ ] **Step 5: Commit** (`feat(treino): dados sinteticos e metricas do spike de treino`, trailer `Soul: desenvolvedor`)

---

### Task 2: Sonda de ambiente, ambientes de treino e lock opt-in

**Files:**
- Create: `scripts/treino_detector/ambiente.py`
- Create: `requirements-treino.lock`
- Test: `tests/unit/test_treino_detector_ambiente.py`, `tests/unit/test_treino_detector_isolamento.py`
- Fora do Git: `C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\treino-e11\venv-rocm\`, `...\venv-cpu\`, `...\ambiente-rocm.json`, `...\ambiente-cpu.json`, `...\ambiente-wsl.txt`, `...\instalacao.md` (comandos exatos, índices, versões, tempos de download/instalação, erros).

**Interfaces:**
- Consumes: nada da Task 1.
- Produces (`ambiente.py`, só stdlib no topo; imports de `torch`, `torchvision`, `onnx`, `onnxruntime` só via o importador injetado):
  - `@dataclass(frozen=True) class Ambiente: python: str; plataforma: str; torch: str | None; torchvision: str | None; onnx: str | None; onnxruntime: str | None; hip: str | None; cuda: str | None; gpu_disponivel: bool; gpu_nome: str | None; gpu_arquitetura: str | None; motivo_sem_gpu: str | None`.
  - `coletar_ambiente(importar: Callable[[str], ModuleType] = importlib.import_module) -> Ambiente` — pacote ausente vira `None`; qualquer exceção ao consultar a GPU vira `gpu_disponivel=False` com `motivo_sem_gpu` = tipo e mensagem; `gpu_arquitetura` de `torch.cuda.get_device_properties(0).gcnArchName` quando existir.
  - `main(argv: Sequence[str] | None = None) -> int` — `python -m scripts.treino_detector.ambiente --saida ARQUIVO.json` grava `dataclasses.asdict` em JSON e imprime na saída.

- [ ] **Step 1: Escreva os testes que falham**

```python
# tests/unit/test_treino_detector_ambiente.py — importador falso devolve SimpleNamespace
def test_sem_torch_tudo_none_e_sem_gpu(): ...          # ModuleNotFoundError → torch None, gpu False, motivo cita torch
def test_torch_rocm_com_gpu(): ...                     # version.hip="7.1", cuda.is_available()→True, nome "AMD Radeon RX 9070 XT", gcnArchName "gfx1201"
def test_torch_cpu_sem_gpu_tem_motivo(): ...           # is_available()→False → motivo "torch.cuda.is_available() == False"
def test_excecao_ao_consultar_gpu_vira_motivo_sem_propagar(): ...  # is_available levanta RuntimeError("hipErrorNoBinaryForGpu")
def test_main_grava_json(tmp_path): ...                # chaves do JSON == campos de Ambiente
```

```python
# tests/unit/test_treino_detector_isolamento.py
def test_src_nao_importa_treino_nem_torch_nem_onnx(): ...        # varre src/**/*.py: nenhum import de scripts.treino_detector, torch, torchvision, onnx
def test_lock_de_treino_nao_entra_em_runtime_nem_build(): ...    # "requirements-treino.lock" ausente de todos os outros requirements*.lock, Dockerfile, setup.bat, IniciarTestes.bat, pyproject.toml, server/pyproject.toml, client/pyproject.toml
def test_lock_de_treino_existe_e_fixa_torch_e_onnxruntime(): ... # pinos "torch", "torchvision", "onnx", "onnxruntime" com ==
def test_modulos_testados_nao_importam_torch_no_topo(): ...      # ast: dados_sinteticos, metricas, ambiente sem import top-level de torch/torchvision/onnx/onnxruntime
```

- [ ] **Step 2: Rode e veja falhar** (`-m pytest tests/unit/test_treino_detector_ambiente.py tests/unit/test_treino_detector_isolamento.py -v` → FAIL)

- [ ] **Step 3: Implemente `ambiente.py`** com as assinaturas acima.

- [ ] **Step 4: Monte o ambiente ROCm nativo**

Em `tmp\treino-e11\venv-rocm`: descubra no índice de release da AMD os wheels PyTorch/torchvision para Windows com suporte à gfx1201 e a versão de Python que eles exigem (crie com `py -3.X -m venv`; se faltar, `py install 3.X`, conforme as Global Constraints). Instale `torch`, `torchvision`, `onnx`, `onnxruntime`, `numpy`, `Pillow==13.0.0`. Rode `python -m scripts.treino_detector.ambiente --saida ...\ambiente-rocm.json` a partir da raiz do worktree. Registre em `instalacao.md` os comandos, os índices e os tempos. Falha de instalação ou `gpu_disponivel=False` não aborta a tarefa: vira evidência.

- [ ] **Step 5: Monte o ambiente CPU de referência**

Em `tmp\treino-e11\venv-cpu` (Python 3.11): `torch`/`torchvision` de `https://download.pytorch.org/whl/cpu`, mais `onnx`, `onnxruntime`, `numpy==2.3.5`, `Pillow==13.0.0`. Sonda em `ambiente-cpu.json`.

- [ ] **Step 6: Sonde o WSL2 sem instalar nada**

`wsl.exe -l -v` (e, se houver distro, `wsl -d <distro> -- uname -a` e `ls /dev/dxg`). Grave a saída ou a recusa do harness em `ambiente-wsl.txt`. Não instale distro nem ROCm no WSL.

- [ ] **Step 7: Escreva `requirements-treino.lock`**

Cabeçalho em comentário: "Lock opt-in de treino do detector (E11/E12); nunca incluir nos requisitos de cliente, servidor, desenvolvimento ou release." e a versão de Python exigida. Pinos `==` do `pip freeze` do ambiente ROCm se ele tiver `gpu_disponivel=True`; senão, do ambiente CPU (com a linha `--index-url` correspondente). A Task 3 pode trocar a variante se a decisão mudar.

- [ ] **Step 8: Rode os testes novos e o gate**

`-m pytest tests/unit/test_treino_detector_ambiente.py tests/unit/test_treino_detector_isolamento.py tests/unit/test_dependency_locks.py -v` → PASS; ruff, format e mypy → sem erros.

- [ ] **Step 9: Commit** (`feat(treino): sonda de ambiente e lock opt-in de treino`, trailer `Soul: desenvolvedor`). O relatório traz o conteúdo de `ambiente-*.json`, `ambiente-wsl.txt` e o resumo de `instalacao.md`.

---

### Task 3: Ensaio treino → ONNX → CPU, medições e decisão no ADR 0017

**Files:**
- Create: `scripts/treino_detector/ensaio.py`
- Modify: `scripts/treino_detector/__init__.py` (docstring de uso final)
- Modify: `docs/adr/0017-detector-visual-local-e-rotulagem-assistida.md` (seção nova "Caminho de treino (E11)")
- Modify (só se a decisão trocar a variante): `requirements-treino.lock`
- Test: `tests/unit/test_treino_detector_isolamento.py` (acrescentar `ensaio` à lista de módulos verificados por `ast` **só** quanto a não ser importado por nenhum teste nem por `src/`)
- Fora do Git: `tmp\treino-e11\ensaio-<dispositivo>\` com `relatorio.json`, `modelo.onnx`, `log.txt`.

**Interfaces:**
- Consumes: `gerar_conjunto`, `CLASSES`, `Anotacao` (Task 1); `avaliar`, `deteccoes_equivalentes`, `resumir_tempos`, `ladrilhos_por_folha`, `Deteccao` (Task 1); `coletar_ambiente` (Task 2).
- Produces: CLI `python -m scripts.treino_detector.ensaio --dispositivo {cuda,cpu} --saida DIR [--treino 2000] [--validacao 200] [--epocas 20] [--lote 16] [--minutos-max 45] [--semente 0]` que grava `relatorio.json` com: `ambiente` (Task 2), `modelo`, `dispositivo`, `epocas_feitas`, `imagens_por_segundo_treino`, `segundos_por_epoca`, `qualidade` (`precisao`, `recall` a IoU 0,5 e score 0,5 na validação), `criterio_qualidade` (`recall >= 0.80 and precisao >= 0.80`), `exportacao_onnx` (`ok`, `opset`, `segundos`, erro), `paridade_onnx` (resultado de `deteccoes_equivalentes` em 20 imagens de validação), `inferencia_cpu_onnxruntime` (`ResumoTempo` por ladrilho 320 px em 100 execuções, com `intra_op_num_threads` registrado), `segundos_estimados_por_folha` (mediana × `ladrilhos_por_folha(9933, 7016)`), `horas_estimadas_treino_referencia` (20 000 ladrilhos × 30 épocas ÷ `imagens_por_segundo_treino` ÷ 3600).

- [ ] **Step 1: Implemente `ensaio.py`**

Modelo `torchvision.models.detection.ssdlite320_mobilenet_v3_large(weights=None, weights_backbone=None, num_classes=len(CLASSES) + 1)`; se a exportação ONNX dele falhar, repita com `fasterrcnn_mobilenet_v3_large_320_fpn` (mesmos parâmetros) e registre os dois. Otimizador SGD (lr 0,01, momentum 0,9) ou o que convergir; para por `--epocas` ou `--minutos-max`. Exportação `torch.onnx.export` em `eval()`, opset ≥ 17, entrada fixa 1×3×320×320 (exportador TorchScript `dynamo=False` se o dynamo falhar; registre qual). Inferência com `onnxruntime.InferenceSession(..., providers=["CPUExecutionProvider"])`. Tempo com `time.perf_counter`, `torch.cuda.synchronize()` antes de ler o relógio na GPU. Uma exceção em qualquer fase vai para o relatório com a fase e a mensagem, e o processo termina com código 1 depois de gravar o relatório.

- [ ] **Step 2: Rode o ensaio na GPU (ambiente ROCm), se `ambiente-rocm.json` tiver `gpu_disponivel=True`**

Run (da raiz do worktree): `C:\...\tmp\treino-e11\venv-rocm\Scripts\python.exe -m scripts.treino_detector.ensaio --dispositivo cuda --saida C:\...\tmp\treino-e11\ensaio-cuda`

- [ ] **Step 3: Rode o ensaio em CPU (ambiente CPU), em paralelo ao Step 2**

Mesmo comando com `--dispositivo cpu --epocas 3 --minutos-max 20 --saida ...\ensaio-cpu` (mede vazão; não precisa atingir o critério de qualidade). O ONNX do ensaio CPU também passa pela paridade e pela medição de inferência.

- [ ] **Step 4: Aplique a regra de decisão e escreva a seção do ADR 0017**

Regra (fixa, nesta ordem):
1. **ROCm nativo** se o ensaio CUDA tem `criterio_qualidade` verdadeiro, exportação e paridade ok, e `imagens_por_segundo_treino` ≥ 3× o da CPU.
2. **WSL2** se (1) falhou, a sonda achou distro com `/dev/dxg` e há caminho documentado sem instalar nada no sistema — senão fica como alternativa não ensaiada, com o motivo.
3. **CPU** se `horas_estimadas_treino_referencia` da CPU ≤ 12.
4. **GPU alugada (D1)**, como proposta ao usuário, se nada acima vale.

Seção "Caminho de treino (E11)" no ADR 0017, com data: caminho escolhido; versões (Python, torch, torchvision, HIP, onnx, onnxruntime, driver se a sonda trouxer, índice dos wheels); tabela de tempos (vazão de treino GPU e CPU, segundos por época, qualidade, exportação, paridade, latência ONNX Runtime por ladrilho mediana/p95, estimativa por folha contra o orçamento de 60 s da E12, horas da carga de referência); alternativas descartadas com o motivo medido; como reproduzir (`requirements-treino.lock` + comando do ensaio). Sem histórico de execução além disso.

- [ ] **Step 5: Atualize o docstring de `scripts/treino_detector/__init__.py`** com o comando final e, se a decisão mudou a variante, o `requirements-treino.lock`.

- [ ] **Step 6: Rode os testes e o gate**

`-m pytest tests/unit/test_treino_detector_*.py tests/unit/test_dependency_locks.py -v` → PASS; ruff, format, mypy → sem erros; suíte inteira conforme a soul.

- [ ] **Step 7: Commit** (`docs(adr): caminho de treino do detector decidido pelo spike E11`, trailer `Soul: desenvolvedor`). O relatório cita os dois `relatorio.json` inteiros.
