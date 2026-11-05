# E11 — Spike de treino na GPU AMD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** decidir onde treinar o detector da E12 (ROCm nativo no Windows, WSL2, CPU ou GPU alugada), provando a cadeia treino → ONNX → inferência em CPU com ONNX Runtime e medindo tempos, e registrar a decisão no ADR 0017.

**Architecture:** spike fora do produto. Um pacote novo `scripts/treino_detector/` concentra o ensaio: partes puras (dados sintéticos, métricas, sonda de ambiente, regra de decisão) testadas no gate com o `.venv` de desenvolvimento, e partes com PyTorch/ONNX (`ensaio.py`) que só rodam nos ambientes de treino descartáveis em `tmp/treino-e11/` do checkout principal e nunca são importadas pelo gate. Um lock opt-in `requirements-treino.lock` fixa o ambiente do caminho escolhido. Nada em `src/` muda.

**Tech Stack:** Python 3.11 (gate) e o Python que os wheels de treino exigirem; numpy 2.3.5 e Pillow 13.0.0 (já no lock de dev); PyTorch + torchvision (BSD-3) com ROCm para Windows (wheels oficiais da AMD) e build CPU de `download.pytorch.org/whl/cpu`; `onnx` (Apache-2.0) e `onnxruntime` (MIT) só nos ambientes de treino.

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E11 — Spike de treino na GPU AMD"; design `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (decisão 5) e `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md` (trilhas); `docs/adr/0017-detector-visual-local-e-rotulagem-assistida.md`.

**Laboratório:** não. Nenhuma tarefa ajusta limiar ou heurística contra folhas reais; o ensaio usa só dados sintéticos.

**Estimativa:** Task 1 ≈ 35 min; Task 2 ≈ 70 min (caixa de 45 min para a instalação ROCm; a falha vira evidência); Task 3 ≈ 75 min (código ≈ 25 min, ensaios em série: GPU com caixa de 30 min, CPU com caixa de 15 min, paridade de treino ≈ 5 min). Total ≈ 3h. As caixas garantem o teto; passar de 4h30 no relógio é parada do protocolo.

## Global Constraints

- Spike sem código de produção: nada em `src/`, nenhum import de `scripts.treino_detector` em `src/` e nenhuma dependência nova em `requirements-server.lock`, `requirements-client*.lock`, `requirements-development.lock`, `requirements.lock`, `requirements-experiments.lock`, `pyproject.toml`, `server/pyproject.toml`, `client/pyproject.toml`, `Dockerfile`, `setup.bat` ou `IniciarTestes.bat`.
- Arquivos proibidos nesta etapa (a E14 da trilha A pode estar editando): `pyproject.toml`, todos os locks existentes, `tests/conftest.py`, `tests/unit/test_dependency_locks.py`, `CLAUDE.md`, `.bat`, contrato de curadoria. Só arquivos novos em `scripts/treino_detector/` e `tests/unit/test_treino_detector_*.py`, o lock novo `requirements-treino.lock` e `docs/adr/0017-detector-visual-local-e-rotulagem-assistida.md`.
- Licença de modelo e código de treino: Apache-2.0, BSD ou MIT. YOLO Ultralytics (AGPL) está excluído. Pesos pré-treinados não são baixados (`weights=None`, `weights_backbone=None`).
- Dados do ensaio: só sintéticos, gerados por `scripts/treino_detector/dados_sinteticos.py`. Nunca ler `examples/`, `examples/avaliacao-cega/` nem nada derivado de folha real.
- Ambientes, wheels, conjuntos, pesos, ONNX e relatórios ficam em `C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\treino-e11\` (ignorado pelo Git). Nada disso é commitado.
- Instalação permitida: a nota da E11 pede confirmação do usuário para instalar ROCm/PyTorch. O prompt desta execução traz, literal: "Qualquer necessidade de intervenção escolha pela opção recomendada após uma avaliação critica dos pro e contras". Avaliada, a opção recomendada é a contida e reversível apagando uma pasta: `pip install` em venvs sob `tmp\treino-e11\`; e, se os wheels exigirem uma versão de Python ausente, `py install 3.12` (ou a versão exigida) no escopo do usuário. **Proibido sem decisão do usuário:** atualizar driver AMD, instalar o ROCm/HIP SDK no sistema, instalar distro WSL ou pacotes dentro do WSL, habilitar recurso do Windows, mexer em variáveis de ambiente do sistema.
- Medições sem contaminação: ensaios, paridade de treino e medição do ONNX Runtime rodam **em série**, com a máquina sem outro processo pesado do ensaio. O conjunto sintético é gerado antes de ligar o cronômetro; a primeira época é "aquecimento" (inclui compilação de kernels MIOpen) e fica fora da vazão. Registre `os.cpu_count()`, `torch.get_num_threads()` e `intra_op_num_threads`.
- Fonte dos wheels ROCm: preferir o índice de release oficial da AMD para Windows (`repo.radeon.com`); índice nightly (`rocm.nightlies.amd.com`, TheRock) só se nenhuma release suportar a gfx1201 (RX 9070 XT), e o relatório registra qual foi usado. Se cair no nightly, o lock leva `--hash=sha256:` em cada pino, os wheels ficam copiados em `tmp\treino-e11\wheels\` e o ADR registra o risco de poda do índice.
- `requirements-treino.lock` é varrido por `tests/unit/test_dependency_locks.py` (`ROOT.glob("requirements*.lock")`): se fixar `Pillow`, `setuptools` ou `wheel`, use exatamente `Pillow==13.0.0`, `setuptools==84.1.0`, `wheel==0.46.2`; instale `setuptools==84.1.0` explicitamente nos venvs (o torch o pede no Python ≥ 3.12); pinos só com `nome==versão` (converta linhas `nome @ https://…` do `pip freeze` em `nome==versão` com `--extra-index-url`/`--find-links`); linhas de índice começam com `--`.
- ROCm no PyTorch expõe a GPU como `torch.cuda` e preenche `torch.version.hip`.
- Gate: `ruff check .`, `ruff format --check .` e `mypy` (strict, cobre `src` e `tests`, e portanto os módulos de `scripts/treino_detector/` importados pelos testes) precisam passar. Os testes não importam `torch`, `torchvision`, `onnx` nem `onnxruntime`, direta ou indiretamente (o `.venv` de dev não os tem).
- Suíte conhecida: em `main`, `tests/unit/test_glyph_text_orcamento.py::test_pagina_hostil_acima_do_teto_de_resolucoes_e_limitada_em_tempo_limitado` reprova por tempo de parede (pré-existente, a E14 corrige). Não é desta etapa: não tocar, relatar se for a única falha.
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro: feche imagens Pillow e arquivos.
- Documentação enxuta: nada de histórico de execução em arquivo versionado. Uso dos scripts nos docstrings dos módulos; decisão e números no ADR 0017.
- Se o harness recusar um comando (por exemplo `wsl.exe` ou `powershell.exe`), não contorne: registre a recusa no relatório como "não sondado" e siga.

## Review Focus

1. GPU visível mas com resultado numérico errado (ROCm que calcula "lixo") → paridade numérica de treino: as mesmas 30 iterações, mesmos pesos iniciais e mesmos lotes em GPU e CPU, com a loss de cada iteração dentro da tolerância (Task 1, `perdas_equivalentes`; Task 3 aplica). A qualidade (recall/precisão ≥ 0,80) só confirma que a cadeia aprende; não é ela que reprova o ROCm.
2. ONNX exportado que roda mas diverge do PyTorch → paridade obrigatória contra o PyTorch em CPU em `eval()`, com margem de score para detecções perto do limiar (Task 1, `deteccoes_equivalentes`; Task 3 aplica).
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
  - `gerar_amostra(semente: int, lado: int = 320, max_simbolos: int = 4) -> AmostraSintetica` — fundo claro com ruído e linhas finas (imitando traço de rede), de 1 a `max_simbolos` símbolos de lado entre 32 e 96 px (compatível com as âncoras do SSDLite320, cuja menor escala é ≈ 64 px), contorno preto, sem sobreposição de caixas (IoU = 0 entre quaisquer duas). O primeiro símbolo sempre cabe; os seguintes que não acharem posição em 50 tentativas são omitidos. Determinística pela semente (`numpy.random.default_rng(semente)`).
  - `gerar_conjunto(semente: int, quantidade: int, lado: int = 320) -> list[AmostraSintetica]` — amostra `i` usa semente derivada `semente * 1_000_003 + i`.
- Produces (`metricas.py`, só stdlib):
  - `iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float`.
  - `@dataclass(frozen=True) class Deteccao: caixa: tuple[float, float, float, float]; rotulo: int; score: float`.
  - `@dataclass(frozen=True) class ResultadoAvaliacao: verdadeiros: int; falsos_positivos: int; falsos_negativos: int` com propriedades `precisao: float` e `recall: float` (0.0 quando o denominador é 0).
  - `avaliar(predicoes: Sequence[Sequence[Deteccao]], verdade: Sequence[Sequence[Anotacao]], iou_minimo: float = 0.5, score_minimo: float = 0.5) -> ResultadoAvaliacao` — casamento guloso por imagem, por score decrescente, mesma classe, cada verdade casada uma vez.
  - `deteccoes_equivalentes(referencia: Sequence[Deteccao], candidata: Sequence[Deteccao], score_minimo: float = 0.30, margem: float = 0.05, iou_minimo: float = 0.99) -> bool` — simétrica com margem: cada detecção de um lado com score ≥ `score_minimo + margem` casa (uma a uma, mesma classe, IoU ≥ `iou_minimo`) com uma do outro lado de score ≥ `score_minimo - margem`, nos dois sentidos. Detecções entre os dois limiares não exigem par. A referência é sempre o PyTorch em CPU em `eval()`.
  - `perdas_equivalentes(referencia: Sequence[float], candidata: Sequence[float], tolerancia_relativa: float = 0.05) -> bool` — mesmo comprimento (> 0), todos finitos e `abs(c - r) <= tolerancia_relativa * max(abs(r), 1e-6)` em cada iteração.
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
        assert 1 <= len(amostra.anotacoes) <= 4
        for anot in amostra.anotacoes:
            x0, y0, x1, y1 = anot.caixa
            assert 0 <= x0 < x1 <= 320 and 0 <= y0 < y1 <= 320
            assert 32 <= x1 - x0 <= 96 and 1 <= anot.rotulo <= len(CLASSES)
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
def test_deteccoes_equivalentes_rejeita_deteccao_sem_par_acima_da_margem(): ...   # score 0.50 só de um lado → False
def test_deteccoes_equivalentes_tolera_deteccao_perto_do_limiar(): ...           # 0.31 de um lado e 0.29 do outro → True
def test_deteccoes_equivalentes_e_simetrica(): ...
def test_perdas_equivalentes():
    assert perdas_equivalentes([2.0, 1.5], [2.05, 1.46])
    assert not perdas_equivalentes([2.0, 1.5], [2.0, 1.7])
    assert not perdas_equivalentes([2.0], [float("nan")])
    assert not perdas_equivalentes([2.0, 1.5], [2.0])
    assert not perdas_equivalentes([], [])
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
def test_src_nao_importa_treino_nem_torch_nem_onnx(): ...        # ast em src/**/*.py: módulo de topo (nome.split(".")[0]) nunca em {"torch", "torchvision", "onnx"}; nenhum import de "scripts.treino_detector" nem "scripts"
def test_guarda_de_src_permite_onnxruntime(): ...                # o detector de imports da guarda, aplicado a "import onnxruntime" e "from onnxruntime import X", não acusa nada (a E12 põe o adaptador em src/)
def test_lock_de_treino_nao_entra_em_runtime_nem_build(): ...    # "requirements-treino.lock" ausente de todos os outros requirements*.lock, Dockerfile, setup.bat, IniciarTestes.bat, pyproject.toml, server/pyproject.toml, client/pyproject.toml
def test_lock_de_treino_existe_e_fixa_torch_e_onnxruntime(): ... # pinos "torch", "torchvision", "onnx", "onnxruntime" com ==
def test_modulos_testados_nao_importam_torch_no_topo(): ...      # ast: dados_sinteticos, metricas, ambiente sem import top-level de torch/torchvision/onnx/onnxruntime
```

- [ ] **Step 2: Rode e veja falhar** (`-m pytest tests/unit/test_treino_detector_ambiente.py tests/unit/test_treino_detector_isolamento.py -v` → FAIL)

- [ ] **Step 3: Implemente `ambiente.py`** com as assinaturas acima.

- [ ] **Step 4: Monte o ambiente ROCm nativo**

Em `tmp\treino-e11\venv-rocm`: descubra no índice de release da AMD os wheels PyTorch/torchvision para Windows com suporte à gfx1201 e a versão de Python que eles exigem (crie com `py -3.X -m venv`; se faltar, `py install 3.X`, conforme as Global Constraints). Instale `torch`, `torchvision`, `onnx`, `onnxruntime`, `numpy`, `Pillow==13.0.0`. Rode `python -m scripts.treino_detector.ambiente --saida ...\ambiente-rocm.json` a partir da raiz do worktree. Registre em `instalacao.md` os comandos, os índices, os tempos e a versão do driver AMD (Adrenalin), se obtível sem PowerShell (por exemplo, versão de arquivo de `C:\Windows\System32\amdhip64_7.dll`). Caixa de tempo: 45 min do início da instalação ROCm; ao estourar, ou com falha de instalação ou `gpu_disponivel=False`, pare o ROCm e registre: vira evidência, não aborta a tarefa.

- [ ] **Step 5: Monte o ambiente CPU de referência**

Em `tmp\treino-e11\venv-cpu` (Python 3.11): `torch`/`torchvision` de `https://download.pytorch.org/whl/cpu`, mais `onnx`, `onnxruntime`, `numpy==2.3.5`, `Pillow==13.0.0`. Sonda em `ambiente-cpu.json`.

- [ ] **Step 6: Sonde o WSL2 sem instalar nada**

`wsl.exe -l -v` (e, se houver distro, `wsl -d <distro> -- uname -a`, `ls /dev/dxg` e `python3 -c "import torch; print(torch.__version__, torch.version.hip)"`). Grave a saída ou a recusa do harness em `ambiente-wsl.txt`. Não instale distro, ROCm nem pacotes no WSL.

- [ ] **Step 7: Escreva `requirements-treino.lock`**

Cabeçalho em comentário: "Lock opt-in de treino do detector (E11/E12); nunca incluir nos requisitos de cliente, servidor, desenvolvimento ou release." e a versão de Python exigida. Pinos `==` do `pip freeze` do ambiente ROCm se ele tiver `gpu_disponivel=True`; senão, do ambiente CPU (com a linha `--index-url` correspondente). A Task 3 pode trocar a variante se a decisão mudar.

- [ ] **Step 8: Rode os testes novos e o gate**

`-m pytest tests/unit/test_treino_detector_ambiente.py tests/unit/test_treino_detector_isolamento.py tests/unit/test_dependency_locks.py -v` → PASS; ruff, format e mypy → sem erros.

- [ ] **Step 9: Commit** (`feat(treino): sonda de ambiente e lock opt-in de treino`, trailer `Soul: desenvolvedor`). O relatório traz o conteúdo de `ambiente-*.json`, `ambiente-wsl.txt` e o resumo de `instalacao.md`.

---

### Task 3: Decisão testada, ensaio treino → ONNX → CPU e registro no ADR 0017

**Files:**
- Create: `scripts/treino_detector/decisao.py` (puro, só stdlib + `metricas`)
- Create: `scripts/treino_detector/ensaio.py` (torch/torchvision/onnx/onnxruntime; nunca importado por teste nem por `src/`)
- Modify: `scripts/treino_detector/__init__.py` (docstring de uso final)
- Modify: `docs/adr/0017-detector-visual-local-e-rotulagem-assistida.md` (seção nova "Caminho de treino (E11)" e o bullet de Decisão "(GPU AMD, PyTorch com ROCm, a confirmar por spike)" passa a remeter a ela)
- Modify (só se a decisão trocar a variante): `requirements-treino.lock`
- Test: `tests/unit/test_treino_detector_decisao.py`; `tests/unit/test_treino_detector_isolamento.py` (acrescentar `decisao` à guarda "sem torch no topo" e uma guarda de que nenhum arquivo em `tests/` nem em `src/` importa `scripts.treino_detector.ensaio`)
- Fora do Git: `tmp\treino-e11\paridade-treino\`, `tmp\treino-e11\ensaio-cuda\`, `tmp\treino-e11\ensaio-cpu\` (cada um com `relatorio.json`, `log.txt` e, nos ensaios, `modelo.onnx`) e `tmp\treino-e11\decisao.json`.

**Interfaces:**
- Consumes: `gerar_conjunto`, `CLASSES`, `Anotacao` (Task 1); `avaliar`, `deteccoes_equivalentes`, `perdas_equivalentes`, `resumir_tempos`, `ladrilhos_por_folha`, `Deteccao`, `ResumoTempo` (Task 1); `coletar_ambiente` (Task 2).
- Produces (`decisao.py`):
  - Premissas (constantes, registradas no ADR como premissas, não como spec): `CARGA_REFERENCIA_LADRILHOS = 20_000`, `CARGA_REFERENCIA_EPOCAS = 30`, `LIMITE_HORAS_TREINO = 12.0`, `RAZAO_MINIMA_GPU_CPU = 3.0`, `FOLHA_REFERENCIA_PX = (9933, 7016)` (A1 a 300 dpi → 875 ladrilhos de 320 px com 10% de sobreposição), `ORCAMENTO_FOLHA_S = 60.0` (orçamento da E12).
  - `horas_estimadas_treino(imagens_por_segundo: float, ladrilhos: int = CARGA_REFERENCIA_LADRILHOS, epocas: int = CARGA_REFERENCIA_EPOCAS) -> float` — `ladrilhos * epocas / imagens_por_segundo / 3600`; `ValueError` se `imagens_por_segundo <= 0`.
  - `segundos_estimados_por_folha(mediana_ladrilho_s: float, largura_px: int = 9933, altura_px: int = 7016) -> float` — `mediana × ladrilhos_por_folha(largura_px, altura_px)`; é um teto (a E12 só atua no resíduo e roda no container).
  - `@dataclass(frozen=True) class ResultadoCaminho: nome: str; ensaiado: bool; paridade_treino: bool; exportacao_onnx: bool; paridade_onnx: bool; imagens_por_segundo: float | None; qualidade_ok: bool | None; trajetoria_ok: bool | None = None; erro_fase: str | None = None; motivo_nao_ensaiado: str | None = None`.
  - `@dataclass(frozen=True) class Decisao: caminho: str` (um de `"rocm-nativo"`, `"wsl2"`, `"cpu"`, `"gpu-alugada"`) `; motivo: str; descartados: tuple[tuple[str, str], ...]` (caminho, motivo medido ou "não ensaiado: …").
  - `decidir_caminho(rocm: ResultadoCaminho, wsl2: ResultadoCaminho, cpu: ResultadoCaminho) -> Decisao` — regra fixa, nesta ordem:
    0. `imagens_por_segundo is None` (ensaio com `erro` ou sem lote pós-aquecimento) torna o caminho inviável, com o motivo (fase do erro, se houver);
    1. caminho GPU (`rocm`, depois `wsl2`) é escolhido se `ensaiado`, `paridade_treino` (= `paridade_primeira_iteracao`), `exportacao_onnx`, `paridade_onnx` e (`imagens_por_segundo >= RAZAO_MINIMA_GPU_CPU × cpu.imagens_por_segundo` ou `horas_estimadas_treino(imagens_por_segundo) <= LIMITE_HORAS_TREINO`); sem vazão da CPU, vale só o critério de horas. Caminho não ensaiado nunca é escolhido;
    2. `cpu` se `ensaiado`, `exportacao_onnx`, `paridade_onnx` e `horas_estimadas_treino(cpu.imagens_por_segundo) <= LIMITE_HORAS_TREINO`;
    3. senão `gpu-alugada` (D1, proposta ao usuário).
    `qualidade_ok` não reprova caminho: entra no `motivo` como confirmação ou ressalva.
  - `resultado_de_relatorio(nome: str, relatorio: Path | None) -> ResultadoCaminho` — `None` ou arquivo ausente → `ensaiado=False` com motivo; lê os campos do `relatorio.json` do ensaio (abaixo) e, para GPU, o `relatorio.json` da paridade de treino passado via o campo `paridade_treino` do próprio ensaio.
  - `main(argv: Sequence[str] | None = None) -> int` — `python -m scripts.treino_detector.decisao --rocm A.json --cpu B.json [--wsl2 C.json] --saida decisao.json`; imprime a `Decisao` em JSON.
- Produces (`ensaio.py`): CLI com dois subcomandos, rodados da raiz do worktree com o Python do venv de treino:
  - `paridade --saida DIR [--iteracoes 30] [--lote 16] [--semente 0] [--tolerancia 0.05]` — no venv ROCm: mesmo `state_dict` inicial (semeado), os mesmos lotes, sem aumento de dados, `train()`, SGD; roda as N iterações na CPU e depois na GPU e grava as duas curvas de loss, `paridade_primeira_iteracao` = `perdas_equivalentes(cpu[:1], gpu[:1], 1e-3)` (pesos idênticos: é a prova de que o ROCm calcula certo), `trajetoria_equivalente` = `perdas_equivalentes(cpu, gpu, tolerancia)` e `primeira_divergencia` (índice da 1ª iteração fora da tolerância, ou `null`). A trajetória é prova secundária: divergir nela com a 1ª iteração ok é ressalva no motivo, não reprovação (SGD, mineração de negativos e MIOpen acumulam diferença).
  - `treino --dispositivo {cuda,cpu} --saida DIR [--treino 2000] [--validacao 200] [--epocas 20] [--lote 16] [--minutos-max 30] [--semente 0] [--paridade-treino ARQUIVO]` — grava `relatorio.json` com: `ambiente` (Task 2), `nucleos` (`os.cpu_count()`), `torch_threads`, `modelo`, `dispositivo`, `epocas_feitas`, `aquecimento_s` (os 10 primeiros lotes da execução, que incluem a compilação de kernels), `imagens_por_segundo_treino` (imagens ÷ tempo de todos os lotes depois desses 10; `null` se não houver lote depois deles), `medida_vazao` (`"lotes-apos-10"`), `segundos_por_epoca` (épocas completas), `qualidade` (`precisao`, `recall` a IoU 0,5 e score 0,5 na validação) e `qualidade_ok` (`recall >= 0.80 and precisao >= 0.80`), `paridade_treino` (conteúdo do arquivo passado, ou `null`), `exportacao_onnx` (`ok`, `exportador`, `opset`, `segundos`, `erro`), `paridade_onnx` (`deteccoes_equivalentes` entre PyTorch em CPU `eval()` e ONNX Runtime em 20 imagens de validação), `inferencia_cpu_onnxruntime` (`ResumoTempo` por ladrilho 320 px em 100 execuções após 5 de aquecimento, com `intra_op_num_threads`), `segundos_estimados_por_folha` e `horas_estimadas_treino_referencia` (das funções de `decisao.py`), `erro` (`fase` e `mensagem`, ou `null`).

- [ ] **Step 1: Escreva os testes de `decisao.py` que falham**

```python
# tests/unit/test_treino_detector_decisao.py
def test_horas_e_folha():
    assert horas_estimadas_treino(100.0) == pytest.approx(20_000 * 30 / 100 / 3600)
    with pytest.raises(ValueError): horas_estimadas_treino(0.0)
    assert segundos_estimados_por_folha(0.02) == pytest.approx(0.02 * 875)

def test_rocm_vence_com_paridades_e_vazao_3x(): ...                 # rocm 300 img/s, cpu 50 → "rocm-nativo"
def test_rocm_abaixo_de_3x_mas_dentro_de_12h_vence(): ...           # rocm 100, cpu 60 (1,67×) → horas(100)=1,67 ≤ 12 → "rocm-nativo"
def test_rocm_sem_paridade_de_treino_cai(): ...                     # paridade_treino False → não escolhido; descartados cita "paridade de treino"
def test_rocm_qualidade_ruim_nao_reprova_mas_aparece_no_motivo(): ...
def test_wsl2_nao_ensaiado_nunca_e_escolhido(): ...                 # descartados contém ("wsl2", "não ensaiado: …")
def test_cpu_dentro_de_12h_vence_sem_gpu(): ...                     # rocm não ensaiado, cpu 20 img/s → horas 8,3 → "cpu"
def test_cpu_acima_de_12h_vira_gpu_alugada(): ...                   # cpu 5 img/s → 33 h → "gpu-alugada"
def test_cpu_sem_paridade_onnx_vira_gpu_alugada(): ...
def test_resultado_de_relatorio_ausente_e_nao_ensaiado(tmp_path): ...
def test_resultado_de_relatorio_le_campos(tmp_path): ...            # json mínimo escrito no teste → ResultadoCaminho com os valores
def test_relatorio_com_erro_e_ensaiado_e_nao_escolhido(tmp_path): ...  # erro {"fase": "exportacao", ...} → ensaiado, descartados cita "exportacao"
def test_vazao_ausente_torna_caminho_inviavel(): ...                # rocm com imagens_por_segundo None → não escolhido, sem TypeError
def test_trajetoria_divergente_com_primeira_iteracao_ok_e_ressalva(): ...  # rocm escolhido, motivo cita a trajetória
def test_main_grava_decisao(tmp_path): ...
```

- [ ] **Step 2: Rode e veja falhar** (`-m pytest tests/unit/test_treino_detector_decisao.py -v` → FAIL)

- [ ] **Step 3: Implemente `decisao.py`** com as assinaturas acima; acrescente as guardas novas em `test_treino_detector_isolamento.py`; rode os testes → PASS.

- [ ] **Step 4: Implemente `ensaio.py`**

Modelo `torchvision.models.detection.ssdlite320_mobilenet_v3_large(weights=None, weights_backbone=None, num_classes=len(CLASSES) + 1)`; se a exportação ONNX dele falhar, repita com `fasterrcnn_mobilenet_v3_large_320_fpn` (mesmos parâmetros) e registre os dois. SGD (lr 0,01, momentum 0,9, weight decay 4e-5) ou o que convergir, registrado; para por `--epocas` ou `--minutos-max`. Conjuntos gerados antes de ligar o cronômetro. Exportação `torch.onnx.export` em `eval()`, opset ≥ 17, entrada fixa 1×3×320×320 (exportador TorchScript `dynamo=False` se o dynamo falhar; registre qual). Inferência com `onnxruntime.InferenceSession(..., providers=["CPUExecutionProvider"])`. Tempo com `time.perf_counter`, com `torch.cuda.synchronize()` antes de ler o relógio na GPU. Exceção em qualquer fase vai para `erro` no relatório, e o processo sai com código 1 depois de gravá-lo.

- [ ] **Step 5: Rode, em série, com a máquina sem outro ensaio**

1. Paridade de treino (venv ROCm, só se `ambiente-rocm.json` tem `gpu_disponivel=True`): `...\venv-rocm\Scripts\python.exe -m scripts.treino_detector.ensaio paridade --saida ...\tmp\treino-e11\paridade-treino`.
2. Ensaio GPU (mesma condição): `... ensaio treino --dispositivo cuda --minutos-max 30 --paridade-treino ...\paridade-treino\relatorio.json --saida ...\ensaio-cuda`.
3. Ensaio CPU (venv CPU), depois do anterior terminar: `... ensaio treino --dispositivo cpu --epocas 3 --minutos-max 15 --saida ...\ensaio-cpu` (mede vazão; a qualidade não é exigida).
4. WSL2: só é ensaiado se a sonda da Task 2 achou distro com torch ROCm já instalado e funcional; senão fica "não ensaiado", com o motivo da sonda e a proibição de instalar.
5. Decisão: `.venv\Scripts\python.exe -m scripts.treino_detector.decisao --rocm ...\ensaio-cuda\relatorio.json --cpu ...\ensaio-cpu\relatorio.json --saida ...\decisao.json` (passe `--wsl2` só se houver relatório).

- [ ] **Step 6: Escreva a seção do ADR 0017**

Seção "Caminho de treino (E11)", com data: caminho escolhido conforme `decisao.json`; hardware da medição (CPU, núcleos, GPU, RAM se obtível); versões (Python, torch, torchvision, HIP, onnx, onnxruntime, driver, índice dos wheels); tabela de tempos (vazão de treino GPU e CPU sem aquecimento, aquecimento, segundos por época, paridade de treino, qualidade, exportação e exportador, paridade ONNX, latência ONNX Runtime por ladrilho mediana/p95 com threads, estimativa por folha contra os 60 s da E12, horas da carga de referência); premissas com derivação (carga de referência 20 000 ladrilhos × 30 épocas, limite de 12 h, razão 3×, folha A1 a 300 dpi = 875 ladrilhos, a estimativa por folha é teto e foi medida nesta máquina, não no container); alternativas descartadas com o motivo medido ou "não ensaiada" e por quê; como reproduzir (`requirements-treino.lock` + comandos). Se o lock vier de índice nightly, o risco de poda. O bullet de Decisão do ADR que diz "(GPU AMD, PyTorch com ROCm, a confirmar por spike)" passa a remeter a esta seção. Sem histórico de execução além disso.

- [ ] **Step 7: Atualize o docstring de `scripts/treino_detector/__init__.py`** com os comandos finais e, se a decisão mudou a variante, o `requirements-treino.lock`.

- [ ] **Step 8: Rode os testes e o gate**

`-m pytest tests/unit/test_treino_detector_*.py tests/unit/test_dependency_locks.py -v` → PASS; ruff, format, mypy → sem erros; suíte inteira conforme a soul.

- [ ] **Step 9: Commit** (`docs(adr): caminho de treino do detector decidido pelo spike E11`, trailer `Soul: desenvolvedor`). O relatório cita inteiros os `relatorio.json` de paridade e dos ensaios e o `decisao.json`.

## Revisão de arquitetura

- Veredito: aprovado com notas (revisor-arquitetura, modelo opus).
- Rodadas: 1 (rodada 0 bloqueada por I1–I4; rodada 1 aprovou com os 14 achados resolvidos).
- Notas Menores da rodada 1, incorporadas a este plano antes da execução:
  - N1: a paridade de treino que reprova é a da 1ª iteração (tolerância 1e-3); a trajetória de 30 iterações é ressalva, com `primeira_divergencia`.
  - N2: relatório com `erro` ou sem vazão vira caminho ensaiado e inviável, com testes.
  - N3: vazão medida por lotes depois de 10 lotes de aquecimento, não por época.
- Para o handoff: na integração com a E14, rodar de novo `tests/unit/test_dependency_locks.py` sobre o `main` com `requirements-treino.lock` (M5).
