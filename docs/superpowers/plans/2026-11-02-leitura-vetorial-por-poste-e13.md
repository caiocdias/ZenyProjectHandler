# E13 — Atualização de dependências vulneráveis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fixar nos locks, manifestos e `Dockerfile` a menor versão corrigida de `pillow`, `mako`, `httpx2`, `pytest`, `setuptools` e `wheel`, sem mudar o comportamento do produto.

**Architecture:** os locks são listas de pinos mantidas à mão (`requirements.lock` → `-r requirements-development.lock` → `-r requirements-client.lock` + `-r requirements-server.lock`; `requirements-experiments.lock` e `requirements-client-build.lock` são independentes). Um teste novo de coerência (`tests/unit/test_dependency_locks.py`) fixa a versão corrigida de cada pacote em todo lock, manifesto e `Dockerfile` que o cita, e exige que os limites dos `pyproject.toml` excluam a versão vulnerável. Cada tarefa cuida de um grupo de pacotes em todos os lugares onde ele aparece, para que o teste fique verde ao fim de cada tarefa.

**Tech Stack:** pip, `packaging` (já no lock de dev, 26.2), pytest, osv-scanner 2.7.0 (só na revisão final, rodado pelo orquestrador).

**Spec:** `docs/roadmap-leitura-vetorial-por-poste.md`, seção "E13 — Atualização de dependências vulneráveis"; design `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md` (só as restrições gerais; a E13 não toca na leitura vetorial).

## Global Constraints

- Python suportado: `>=3.11,<3.14` (Windows para cliente/dev; servidor Linux em `python:3.13.7-slim-bookworm`).
- Versões-alvo (menor versão corrigida segundo o osv-scanner de 2026-11-02): `Pillow==13.0.0`, `Mako==1.4.2`, `httpx2==2.12.0` (exige `httpcore2==2.12.0`), `pytest==9.0.3`, `setuptools==84.1.0`, `wheel==0.46.2`.
- Vulneráveis que os limites precisam excluir: Pillow 12.2.0, Mako 1.3.12, httpx2 2.10.0, pytest 8.4.2, setuptools 80.10.2, wheel 0.45.1.
- Dependências transitivas só mudam quando a versão nova exigir. Nenhum pacote sem vulnerabilidade apontada é atualizado; nenhuma dependência nova.
- A mesma versão de cada pacote atualizado em todos os locks que o fixam; grafia do nome como já está em cada lock (`Pillow`, `Mako`).
- Mudança de comportamento de saída da análise incrementa a versão do extrator (ADR 0006): `PyMuPdfDocumentAnalyzer.versao = "1.20.0"` em `src/zeny_project_handler/adapters/analysis/pymupdf_analyzer.py:59`.
- PDFs reais e qualquer artefato derivado deles nunca entram no Git. Leitura de `examples/` só no checkout principal (`C:\Users\Caio\Desktop\repos\ZenyProjectHandler\examples`), somente leitura; saídas em `C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\e13\`.
- Ambientes descartáveis (venvs de prova, wheels baixados) ficam em `tmp/e13/` do worktree (ignorado pelo Git) e não são commitados.
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro.
- Documentação enxuta: nada de histórico de execução em arquivo versionado.

## Review Focus

1. Máquina nova rodando `setup.bat` com Python 3.11, 3.12 ou 3.13 → toda versão-alvo tem wheel `win_amd64` para as três versões (prova por `pip download --only-binary=:all:` nas Tasks 1–3).
2. `docker build` do servidor (Linux, cp313) → Pillow 13.0.0 e Mako 1.4.2 têm wheel/distribuição instalável para `manylinux_2_28_x86_64` cp313 (Task 1); setuptools 84.1.0 constrói o wheel do servidor sem `pkg_resources` (Task 3).
3. Pillow 13 muda raster, OCR ou overlay → a saída da análise sobre os 16 PDFs de `examples/` e os rasters que o analisador entrega ao motor OCR são comparados antes/depois por digest determinístico (Task 1); diferença incrementa a versão do extrator. Os demais usos de Pillow (callouts de `application/visual_occupancy.py`, rasters do `viewer_api.py`, exportações) ficam cobertos pelo gate sintético; mudança nos callouts incrementaria a versão do método de conformidade, não a do extrator.
4. Lock opt-in de experimentos (`rapidocr-onnxruntime` 1.4.4) deixa de resolver com Pillow 13 → `pip install --dry-run --ignore-installed` do lock (Task 1).
5. pytest 9 transforma em erro algo que o pytest 8 só avisava (ou muda coleta/plugins `pytest-cov` 7.1.0 e `pytest-qt` 4.5.0) → a suíte inteira roda com pytest 9.0.3 na Task 2, sem afrouxar `filterwarnings` nem `--strict-markers`.

---

### Task 1: Runtime do servidor — Pillow 13.0.0 e Mako 1.4.2, com teste de coerência

**Files:**
- Create: `tests/unit/test_dependency_locks.py`
- Modify: `requirements-server.lock:11,13`, `requirements-experiments.lock:15`, `pyproject.toml:22`, `server/pyproject.toml:13`
- Modify (só se o digest mudar): `src/zeny_project_handler/adapters/analysis/pymupdf_analyzer.py:59` e os testes que fixam `"1.20.0"` como versão do analisador

**Interfaces:**
- Produces (em `tests/unit/test_dependency_locks.py`, usados pelas Tasks 2 e 3):
  - `VERSOES_CORRIGIDAS: dict[str, str]` — nome canônico (`packaging.utils.canonicalize_name`) → versão-alvo. Task 1 cria com `pillow` e `mako`; Task 2 acrescenta `httpx2`, `httpcore2`, `pytest`; Task 3 acrescenta `setuptools`, `wheel`.
  - `VERSOES_VULNERAVEIS: dict[str, str]` — nome canônico → versão que o scanner apontou. `httpcore2` (não apontado, só exigido por `httpx2` 2.12.0) entra só em `VERSOES_CORRIGIDAS`; o teste de manifestos usa `VERSOES_VULNERAVEIS.get(nome)` e pula a exclusão quando não há vulnerável registrado.
  - `_pinos(lock: Path) -> dict[str, str]` — pinos `nome==versão` das linhas do próprio arquivo (ignora comentários, linhas em branco e `-r`), chave canônica.
  - `_requisitos_de_manifesto(pyproject: Path) -> list[Requirement]` — `build-system.requires` + `project.dependencies` + todas as listas de `project.optional-dependencies`.
  - `LOCKS = sorted(ROOT.glob("requirements*.lock"))`, `MANIFESTOS = [ROOT / "pyproject.toml", ROOT / "server" / "pyproject.toml", ROOT / "client" / "pyproject.toml"]`.

- [ ] **Step 1: Digest determinístico da análise antes da troca (Pillow 12.2.0)**

Script descartável em `C:\Users\Caio\Desktop\repos\ZenyProjectHandler\tmp\e13\digest_analise.py` (fora do Git), rodado com o `.venv` do worktree sobre cada PDF de `examples/` do checkout principal. Duas medidas por PDF:

- **Caminho nativo:** monte a análise como `scripts/smoke_examples.py` (leitor, `PyMuPdfDocumentAnalyzer()` sem cache, catálogo, interpretador e orçamento de render), mas com `projeto_id`, `execucao_id` (da análise e da interpretação) e `criada_em` fixos (constantes no script, iguais nas duas rodadas). Serialize em JSON canônico (chaves ordenadas) todas as evidências, propostas e relações, excluindo também qualquer campo de id ou timestamp que ainda derive de `uuid4`/relógio, e tire o SHA-256.
- **Entrada do OCR:** o Tesseract não está instalado nesta máquina (só existe na imagem Docker). Rode o analisador com `habilitar_ocr_condicional=True` e um motor OCR gravador, definido no script, que implementa `MotorOcrPort` (`consultar_capacidade` disponível; `reconhecer` e os métodos dos ports `MotorOcrIdentificadorPort`, `MotorOcrRotuloOperacionalPort`, `MotorOcrGlifosPort` e `MotorOcrBlocoOperacionalPort` de `src/zeny_project_handler/ports/analysis.py` devolvem tupla vazia) e acumula, em ordem de chamada, o SHA-256 dos pixels e das dimensões de cada `PaginaRasterOcr` recebida. O digest é o SHA-256 da lista. Isso prova que o pré-processamento com Pillow entrega ao Tesseract os mesmos pixels; a codificação interna do `TesseractCliOcr` fica fora e é registrada no relatório, assim como o fato de que só os rasters pedidos com OCR vazio são comparados (passos que dependem de texto já reconhecido podem não ser chamados).

Rode o "antes" duas vezes e exija digests idênticos entre as rodadas antes de seguir (se não forem, o script ainda não é determinístico: corrija o script, não o produto). Saída: `tmp\e13\digest-antes.json` no checkout principal, com id do PDF (hash do nome, nunca o nome) → `{nativo, entrada_ocr, chamadas_ocr}`.

- [ ] **Step 2: Escreva o teste de coerência que falha**

```python
VERSOES_CORRIGIDAS = {"pillow": "13.0.0", "mako": "1.4.2"}
VERSOES_VULNERAVEIS = {"pillow": "12.2.0", "mako": "1.3.12"}

def test_locks_nao_fixam_versao_abaixo_da_corrigida() -> None:
    for lock in LOCKS:
        for nome, versao in _pinos(lock).items():
            if nome in VERSOES_CORRIGIDAS:
                assert Version(versao) >= Version(VERSOES_CORRIGIDAS[nome]), f"{lock.name}: {nome}=={versao}"

def test_pacote_corrigido_tem_a_mesma_versao_em_todos_os_locks() -> None:
    # para cada nome de VERSOES_CORRIGIDAS, o conjunto de versões fixadas nos LOCKS tem no máximo 1 elemento
    ...

def test_todo_pacote_corrigido_esta_em_algum_lock_ou_manifesto() -> None:
    # evita teste vazio: cada chave de VERSOES_CORRIGIDAS aparece em pelo menos um lock ou manifesto
    ...

def test_limites_dos_manifestos_admitem_a_corrigida_e_excluem_a_vulneravel() -> None:
    for manifesto in MANIFESTOS:
        for requisito in _requisitos_de_manifesto(manifesto):
            nome = canonicalize_name(requisito.name)
            if nome in VERSOES_CORRIGIDAS:
                assert requisito.specifier.contains(VERSOES_CORRIGIDAS[nome])
                vulneravel = VERSOES_VULNERAVEIS.get(nome)
                if vulneravel is not None:
                    assert not requisito.specifier.contains(vulneravel)
```

- [ ] **Step 3: Rode e confirme a falha**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_dependency_locks.py -v`
Expected: FAIL em `test_locks_nao_fixam_versao_abaixo_da_corrigida` (`Pillow==12.2.0`, `Mako==1.3.12`) e em `test_limites_...` (`Pillow>=12.2,<13`).

- [ ] **Step 4: Atualize pinos e limites**

`Pillow==13.0.0` em `requirements-server.lock` e `requirements-experiments.lock`; `Mako==1.4.2` em `requirements-server.lock`; `"Pillow>=13.0,<14"` em `pyproject.toml` e `server/pyproject.toml`. `MarkupSafe` só muda se `Mako==1.4.2` exigir (confira `Requires-Dist` no METADATA do wheel).

- [ ] **Step 5: Prove instalação nas plataformas**

Run (cada um, destino `tmp/e13/wheels/`):
- `pip download --no-deps --only-binary=:all: --platform win_amd64 --python-version 3.11 Pillow==13.0.0` e o mesmo com `3.12` e `3.13`;
- `pip download --no-deps --only-binary=:all: --platform manylinux_2_28_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux2014_x86_64 --python-version 3.13 --implementation cp --abi cp313 --abi none Pillow==13.0.0 Mako==1.4.2`;
- `pip install --dry-run --ignore-installed -r requirements-experiments.lock` (resolve com dependências);
- `pip install --dry-run --ignore-installed -r requirements-server.lock`.
Expected: todos com exit 0, sem conflito. Falha aqui é BLOCKED, com a saída.

- [ ] **Step 6: Sincronize o `.venv` do worktree e rode o digest depois**

Run: `.venv/Scripts/python.exe -m pip install -r requirements-development.lock`, depois o script do Step 1 gravando `tmp\e13\digest-depois.json`.
Expected: digests `nativo` e `entrada_ocr` iguais por PDF. Se algum diferir, incremente `PyMuPdfDocumentAnalyzer.versao` para `"1.21.0"` (o grep não acha teste que fixe `"1.20.0"`; se algum aparecer, ajuste-o) e descreva no relatório quantos PDFs mudaram e em qual medida (nativo ou entrada do OCR) e que tipo de item mudou, sem nome de folha nem conteúdo.

- [ ] **Step 7: Rode o teste e a suíte**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_dependency_locks.py -v` → PASS; `.venv/Scripts/python.exe -m pytest` → sem falhas.

- [ ] **Step 8: Commit**

```bash
git add tests/unit/test_dependency_locks.py requirements-server.lock requirements-experiments.lock pyproject.toml server/pyproject.toml
# só se o Step 6 incrementou a versão:
git add src/zeny_project_handler/adapters/analysis/pymupdf_analyzer.py  # e cada teste ajustado, nominalmente
git commit -m "build(deps): Pillow 13.0.0 e Mako 1.4.2 no runtime do servidor"
```

### Task 2: Ferramentas de desenvolvimento — httpx2 2.12.0, pytest 9.0.3 e saída do pywinauto

**Files:**
- Modify: `requirements-development.lock` (`httpcore2`, `httpx2`, `pytest`, remoção de `comtypes`, `pywin32`, `pywinauto`), `pyproject.toml:30,32,35`
- Modify: `tests/unit/test_dependency_locks.py` (`VERSOES_CORRIGIDAS`/`VERSOES_VULNERAVEIS`)
- Modify (só se pytest 9 exigir): testes ou `[tool.pytest.ini_options]`, sem afrouxar `filterwarnings`, `--strict-markers` nem `fail_under`

**Interfaces:**
- Consumes: `VERSOES_CORRIGIDAS`, `VERSOES_VULNERAVEIS`, `_pinos`, `_requisitos_de_manifesto` da Task 1.

- [ ] **Step 1: Teste que falha**

Acrescente `"httpx2": "2.12.0"`, `"httpcore2": "2.12.0"`, `"pytest": "9.0.3"` em `VERSOES_CORRIGIDAS` (e `"httpx2": "2.10.0"`, `"pytest": "8.4.2"` em `VERSOES_VULNERAVEIS`), e:

```python
def test_pywinauto_sem_uso_fora_do_ambiente() -> None:
    """pywinauto não é importado pelo projeto (E13); comtypes e pywin32 só entravam por ele."""
    for lock in LOCKS:
        assert "pywinauto" not in _pinos(lock)
    for manifesto in MANIFESTOS:
        assert all(canonicalize_name(r.name) != "pywinauto" for r in _requisitos_de_manifesto(manifesto))
```

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_dependency_locks.py -v` → FAIL nos pinos de dev e no `pywinauto`.

- [ ] **Step 2: Prove que nada usa `pywinauto`, `comtypes` e `pywin32`**

Run: `git grep -nE "pywinauto|comtypes|win32api|win32con|win32com|pywintypes|import win32" -- . ':!docs/superpowers' ':!docs/roadmap-*' ':!*.lock' ':!pyproject.toml'` (cobre src, scripts, tests, client, server, docs, README.md, CLAUDE.md, .claude/settings.json e os .bat) → vazio; `pip show -r` mostra que só `pywinauto` exige `comtypes` e `pywin32`. `six` fica (exigido por `mando`). Se algo os usar, mantenha-os, registre no relatório e tire do teste a parte do `pywinauto`.

- [ ] **Step 3: Atualize pinos e limites**

Dev lock: `httpcore2==2.12.0`, `httpx2==2.12.0`, `pytest==9.0.3`; remova `comtypes`, `pywin32`, `pywinauto`. `pyproject.toml`: `"httpx2>=2.12,<2.13"`, `"pytest>=9.0.3,<10"`, remova `"pywinauto>=0.6.9,<0.7"`. Outras transitivas só se `Requires-Dist` de httpx2/httpcore2 2.12.0 ou pytest 9.0.3 exigir (`pytest-cov` 7.1.0 e `pytest-qt` 4.5.0 ficam se aceitarem pytest 9). Se a exigência cair num pacote de `requirements-server.lock` (`anyio`, `h11`, `idna`, `typing_extensions`), não aplique: pare e devolva BLOCKED com o `Requires-Dist`, porque isso muda o runtime do servidor fora do digest da Task 1.

- [ ] **Step 4: Prove instalação em ambiente limpo**

Run: crie `tmp/e13/venv-dev` com o Python do `.venv`, `pip install -r requirements-development.lock`, `pip install --no-build-isolation --no-deps -e .`, `pip check` → `No broken requirements found.`; `pip download --no-deps --only-binary=:all: --platform win_amd64 --python-version {3.11,3.12,3.13} httpx2==2.12.0 httpcore2==2.12.0 pytest==9.0.3` → exit 0.

- [ ] **Step 5: Sincronize o `.venv` do worktree e rode a suíte com pytest 9**

Run: `.venv/Scripts/python.exe -m pip install -r requirements-development.lock`, `.venv/Scripts/python.exe -m pip uninstall -y pywinauto comtypes pywin32`, `.venv/Scripts/python.exe -m pip check`, depois `.venv/Scripts/python.exe -m pytest --cov`.
Expected: `pytest 9.0.3` no cabeçalho, sem falhas, cobertura ≥ 85,01%. Erro novo do pytest 9 se corrige na causa (teste ou configuração), nunca com `ignore` em `filterwarnings`.

- [ ] **Step 6: Commit**

```bash
git add requirements-development.lock pyproject.toml tests/unit/test_dependency_locks.py
# mais, nominalmente, cada teste ou configuração que o pytest 9 exigiu mudar
git commit -m "build(deps): httpx2 2.12.0 e pytest 9.0.3 no dev; remove pywinauto sem uso"
```

### Task 3: Ferramentas de build — setuptools 84.1.0 e wheel 0.46.2

**Files:**
- Modify: `requirements-development.lock` (`setuptools`), `requirements-client-build.lock:8-9`, `pyproject.toml:2`, `server/pyproject.toml:2`, `client/pyproject.toml:2`, `Dockerfile:13`
- Modify: `tests/unit/test_dependency_locks.py`

**Interfaces:**
- Consumes: os nomes da Task 1.

- [ ] **Step 1: Teste que falha**

Acrescente `"setuptools": "84.1.0"`, `"wheel": "0.46.2"` (vulneráveis `80.10.2`, `0.45.1`), e:

```python
def test_dockerfile_instala_o_setuptools_corrigido() -> None:
    pinos = re.findall(r"setuptools==([\w.]+)", (ROOT / "Dockerfile").read_text(encoding="utf-8"))
    assert pinos == [VERSOES_CORRIGIDAS["setuptools"]]
```

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_dependency_locks.py -v` → FAIL nos locks, nos três `[build-system]` e no `Dockerfile`.

- [ ] **Step 2: Atualize pinos e limites**

`setuptools==84.1.0` nos locks de dev e client-build; `wheel==0.46.2` no client-build; `[build-system] requires = ["setuptools>=84.1,<85"]` na raiz; `["setuptools==84.1.0", "wheel==0.46.2"]` em `server/` e `client/`; `pip install setuptools==84.1.0` no `Dockerfile`. `packaging` do client-build (25.0) só muda se `wheel==0.46.2` exigir.

- [ ] **Step 3: Prove os builds**

Todos os builds reais do projeto usam `--no-build-isolation` com o setuptools do ambiente; a prova espelha esses caminhos. Esta máquina tem Python 3.11.9 e 3.15, sem 3.13: use 3.11 (o do `.venv`) e registre isso no relatório.

Run:
- **Espelho do builder do `Dockerfile`:** venv descartável `tmp/e13/venv-server-build`, instale só `setuptools==84.1.0`, rode `python -m pip wheel --no-deps --no-build-isolation -w tmp/e13/wheels ./server` → `zeny_project_handler_server-0.5.0-*.whl` gerado.
- **Build real do cliente:** venv descartável `tmp/e13/venv-client-build` com `pip install -r requirements-client.lock -r requirements-client-build.lock`, `pip check`, depois `python scripts/build_client.py --output-root tmp/e13/dist` (exige Windows x64; gera wheel e ZIP e já roda o `client_artifact_gate` sobre eles) → exit 0.
- **Caminho do `setup.bat`:** no `.venv` do worktree, depois de `pip install -r requirements-development.lock`: `python -m pip install --no-build-isolation --no-deps -e .` → exit 0, e `python -c "import zeny_project_handler"` → exit 0. (`tests/integration/test_package_import.py` também constrói com `--no-build-isolation` no gate.)
- `pip download --no-deps --only-binary=:all: setuptools==84.1.0 wheel==0.46.2` → exit 0 (puro Python).
Expected: todos com exit 0. Falha de build por `pkg_resources`, metadado ou PyInstaller é BLOCKED, com a saída.

- [ ] **Step 4: Rode o teste e a suíte**

Run: `.venv/Scripts/python.exe -m pytest tests/unit/test_dependency_locks.py -v` → PASS; `.venv/Scripts/python.exe -m pytest` → sem falhas; `.venv/Scripts/python.exe -m pip check` → sem requisitos quebrados.

- [ ] **Step 5: Commit**

```bash
git add requirements-development.lock requirements-client-build.lock pyproject.toml server/pyproject.toml client/pyproject.toml Dockerfile tests/unit/test_dependency_locks.py
git commit -m "build(deps): setuptools 84.1.0 e wheel 0.46.2 nos locks, manifestos e Dockerfile"
```

### Fechamento da etapa (orquestrador)

- `osv-scanner scan source -L requirements.txt:<lock>` nos 6 locks → nenhum dos 6 pacotes com vulnerabilidade corrigível; restante registrado no handoff.
- Critério 2 sobre o estado final: venv limpo `tmp/e13/venv-final`, `pip install -r requirements-development.lock`, `pip install --no-build-isolation --no-deps -e .`, `pip check` → `No broken requirements found.`
- `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO` (roda no worktree com o `.\`; baseline em 4a7f60b aprovado); `scripts/client_artifact_gate.py --source-only` → aprovado.
- `docker build` do `Dockerfile`: o daemon Docker não está rodando nesta máquina (2026-11-02), e ligá-lo é ação fora do worktree. Se continuar assim, a etapa não vira `#concluida`: fica `#bloqueada`, com "Bloqueios" = só o `docker build` pendente, evidência das provas equivalentes (espelho do builder, wheels manylinux) e ação de desbloqueio = o usuário rodar `docker build` e registrar o resultado. A E03 depende da E13 e fica para trás; o lote segue para a próxima elegível.
- Handoff: os limites alargados (`Pillow<13`, `httpx2<2.11`, `pytest<9`, `setuptools<81`) vêm dos commits iniciais de setup (`fecc5be`, `e9e5559`, `2641ed3`), sem motivo registrado (`git log -S`, nota da spec).

## Revisão de arquitetura

- Veredito: aprovado com notas.
- Rodadas: 1 (rodada 0 bloqueada por I1 digest não determinístico e sem OCR, I2 commit sem a versão do extrator, I3 prova de build fora dos caminhos `--no-build-isolation`; todos resolvidos na rodada 1).
- Modelo: opus (`revisor-arquitetura`).
- Notas Menores: N1 (snippet do teste de manifestos alinhado ao `.get`, aplicado); N2 (o motor gravador só compara rasters pedidos com OCR vazio, registrado no Step 1); M10 (o repositório não tem documento ARCHITECTURE; julgado contra spec, ADRs 0005, 0006, 0012, 0013 e código).
