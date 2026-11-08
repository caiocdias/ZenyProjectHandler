# E18 — Versão 0.6.0 e candidata de segurança Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o produto declara 0.6.0, as notas da release deixam de ter número escrito à mão, a opção de leitura vetorial fica documentada desligada e uma release completa sai em `dist/release/0.6.0/`.

**Architecture:** só troca de valores, texto de notas e documentação, sem comportamento novo do produto. As notas leem as versões do código e o commit do git na hora do build. O build real é operação do orquestrador, depois da integração das tarefas.

**Tech Stack:** Python 3.13, `scripts/build_release.py`, Docker, PyInstaller.

**Spec:** seção "E18" de `docs/roadmap-leitura-vetorial-por-poste.md` e bloco "Janela de release 0.6.0" do protocolo (D16, D17, D20).

## Global Constraints

- API segue `1.6.0`, sem mudança de contrato; formato de volume `1`; Alembic `0009_remote_jobs`.
- Nenhuma versão de extrator, interpretador ou método muda nesta etapa, e a análise padrão não muda de saída.
- `ZENY_SERVER_SYMBOL_COMPOSITION` continua `false` por padrão (D17).
- Código, mensagens e documentos em português.
- Fora de histórico e de documentos de etapas passadas, `git grep -n "0\.5\.0"` não acha declaração da versão do produto.
- Não editar `docs/roadmap-leitura-vetorial-por-poste.md`; o orquestrador cuida dele.

## Review Focus

- Árvore suja no build: `build_release` recusa, com `BUILD DE RELEASE: REPROVADO` e o motivo, em vez de citar um commit que não descreve os arquivos.
- Seed com regra desabilitada: as notas contam só as habilitadas.
- Commit citado: é o HEAD do checkout de onde o script roda (`ROOT`), não o do diretório corrente.
- Falha do git (sem repositório ou sem `git`): `ReleaseBuildError` com mensagem acionável, nunca traceback.
- `.env` do kit servidor: quem copia o exemplo recebe a opção explícita e desligada; o `compose.release.yaml` já tem o padrão `false` e não muda.

## File Structure

| Arquivo | Tarefa | Responsabilidade |
|---|---|---|
| `pyproject.toml`, `client/pyproject.toml`, `server/pyproject.toml` | 1 | versão declarada |
| `src/zeny_project_handler/__init__.py`, `src/zeny_project_handler_client/__init__.py` | 1 | `__version__` |
| `src/zeny_project_handler_server/composition.py` | 1 | valor de reserva de `_server_version` |
| `Dockerfile`, `scripts/build_client.py` | 1 | `ARG` e `DEFAULT_VERSION` |
| `README.md`, `CLAUDE.md`, `docs/especificacao-funcional.md` | 1 | comandos e tabela de versão |
| `server/env.release.example`, `server/LEIA-ME-SERVIDOR.md` | 1 | opção documentada |
| `tests/integration/test_package_import.py` | 1 | versão esperada |
| `tests/unit/test_release_kit_docs.py` (novo) | 1 | opção documentada no kit |
| `scripts/build_release.py` | 2 | notas, commit e guarda de árvore limpa |
| `tests/unit/test_release_build.py` | 2 | notas e versão validada |

Tarefa 1 tem mais de 3 arquivos de produção por ser a mesma troca de valor repetida (lote de mesma forma da SDD); dividir só multiplicaria despachos sem superfície de revisão própria.

---

### Task 1: Troca da versão e opção documentada

**Estimativa:** 25 min · **Depende de:** nenhuma · **Risco:** normal

**Files:**
- Modify: os da linha "1" da File Structure, nos pontos abaixo
- Create: `tests/unit/test_release_kit_docs.py`
- Test: `tests/integration/test_package_import.py`, `tests/unit/test_release_kit_docs.py`

**Interfaces:** não consome nem produz nada para a Task 2.

- [ ] **Step 1: Testes falhando.** Em `tests/integration/test_package_import.py`, a versão esperada passa a `"0.6.0"`. Crie `tests/unit/test_release_kit_docs.py`, com `ROOT = Path(__file__).resolve().parents[2]`:

```python
def test_exemplo_de_ambiente_do_kit_traz_leitura_vetorial_desligada() -> None:
    linhas = (ROOT / "server" / "env.release.example").read_text(encoding="utf-8").splitlines()
    assert "ZENY_SERVER_SYMBOL_COMPOSITION=false" in linhas


def test_guia_do_servidor_explica_a_leitura_vetorial_opcional() -> None:
    guia = (ROOT / "server" / "LEIA-ME-SERVIDOR.md").read_text(encoding="utf-8")
    assert "ZENY_SERVER_SYMBOL_COMPOSITION" in guia
    assert "desligada por padrão" in guia
```

- [ ] **Step 2: Rode e veja falhar.** `.venv/Scripts/python.exe -m pytest tests/integration/test_package_import.py tests/unit/test_release_kit_docs.py` → FAIL.

- [ ] **Step 3: Troque `0.5.0` por `0.6.0`** em: `pyproject.toml:7`, `client/pyproject.toml:7`, `server/pyproject.toml:7`, `src/zeny_project_handler/__init__.py:5`, `src/zeny_project_handler_client/__init__.py:3`, `src/zeny_project_handler_server/composition.py:519`, `Dockerfile:25`, `scripts/build_client.py:18`, `README.md:412`, `README.md:415`, `CLAUDE.md:31`, `docs/especificacao-funcional.md:18`.

- [ ] **Step 4: Documente a opção.** Em `server/env.release.example`, logo depois de `ZENY_SERVER_JOB_MAX_RETAINED=100`, acrescente um comentário de uma linha e a linha `ZENY_SERVER_SYMBOL_COMPOSITION=false`. Em `server/LEIA-ME-SERVIDOR.md`, logo depois do parágrafo que termina em "IPv4 privado específico do servidor.", acrescente:

```markdown
`ZENY_SERVER_SYMBOL_COMPOSITION` controla a leitura vetorial nova de símbolos, que vem desligada por
padrão (`false`). Com ela desligada, a análise funciona como antes. Ligar custa mais tempo por
análise e muda os resultados guardados em cache; só ligue em homologação, e não há ganho de
confiança declarado para o resultado.
```

- [ ] **Step 5: Rode e veja passar.** Mesmo comando do Step 2 → PASS. Confira `git grep -n "0\.5\.0" -- . ':!docs/roadmap-*' ':!docs/superpowers/*' ':!*.lock' ':!tests/unit/test_release_build.py'` → saída vazia (a Task 2 troca o arquivo excluído).

- [ ] **Step 6: Commit** com a suíte da área verde; rode a suíte inteira uma vez antes do relatório.

---

### Task 2: Notas da release verdadeiras

**Estimativa:** 35 min · **Depende de:** nenhuma · **Risco:** normal

**Files:**
- Modify: `scripts/build_release.py`
- Test: `tests/unit/test_release_build.py`

**Interfaces:**
- Produces (internas a `scripts/build_release.py`):
  - `_commit_de_origem(root: Path = ROOT) -> str`: SHA completo do `HEAD` de `root`; levanta `ReleaseBuildError` se `git status --porcelain` em `root` não sair vazio, com mensagem contendo `árvore suja`, ou se o git falhar, com mensagem contendo `não foi possível obter o commit`.
  - `_fatos_do_produto(root: Path = ROOT) -> _FatosProduto`: dataclass frozen com `versao_extracao`, `versao_interpretacao`, `metodo_conformidade`, `registro_conformidade`, `regras_habilitadas: int`.
  - `_write_release_notes(path: Path, version: str, image: str, digest: str, commit: str, fatos: _FatosProduto) -> None`.

- [ ] **Step 1: Testes falhando.** Em `tests/unit/test_release_build.py`, troque `"0.5.0"` por `"0.6.0"` nas linhas 25 e 57 e use a nova assinatura. Fixture `FATOS = _FatosProduto("9.8.7", "6.5", "4", "registro-x", 3)` e commit `"a" * 40`. Testes:

```python
def test_release_notes_declare_current_api_and_acceptance_limits(tmp_path: Path) -> None:
    destination = tmp_path / "RELEASE_NOTES.md"
    _write_release_notes(destination, "0.6.0", "zeny-server:0.6.0", "sha256:fixture", "a" * 40, FATOS)
    notes = destination.read_text(encoding="utf-8")
    assert f"API: `{API_VERSION}`" in notes
    assert f"faixa compatível `{MIN_COMPATIBLE_API_VERSION}`" in notes
    assert "ainda não está homologado" in notes


def test_notas_citam_commit_e_versoes_recebidas(tmp_path: Path) -> None:
    ...  # mesmas chamadas; afirme os 40 "a", "9.8.7", "6.5", método "4", "registro-x", "3 regras habilitadas"


def test_notas_dizem_que_a_leitura_vetorial_vem_desligada(tmp_path: Path) -> None:
    ...  # afirme "ZENY_SERVER_SYMBOL_COMPOSITION" e "desligada por padrão"


def test_notas_nao_trazem_numero_de_versao_escrito_a_mao(tmp_path: Path) -> None:
    ...  # afirme que "1.18.0", "25.0", "42 regras" não aparecem nas notas geradas com FATOS


def test_fatos_do_produto_leem_as_versoes_do_codigo() -> None:
    fatos = _fatos_do_produto()
    assert fatos.versao_extracao == PyMuPdfDocumentAnalyzer.versao
    assert fatos.versao_interpretacao == InterpretadorRegrasExplicitas.versao
    assert fatos.metodo_conformidade == VERSAO_METODO_CONFORMIDADE


def test_fatos_contam_so_regras_habilitadas(tmp_path: Path) -> None:
    ...  # seed sintético em tmp_path com a mesma estrutura de caminho, 2 regras enabled=true e 1 false; afirme regras_habilitadas == 2 e o nome do registro


def test_commit_de_origem_recusa_arvore_suja(tmp_path: Path) -> None:
    ...  # git init em tmp_path, commit, arquivo não rastreado; pytest.raises(ReleaseBuildError, match="árvore suja")


def test_commit_de_origem_devolve_head_do_root_e_nao_do_cwd(tmp_path, monkeypatch) -> None:
    ...  # dois repositórios em tmp_path; chdir para o segundo; afirme o SHA do primeiro quando root=primeiro


def test_commit_de_origem_sem_repositorio_da_erro_acionavel(tmp_path: Path) -> None:
    ...  # diretório sem git; pytest.raises(ReleaseBuildError, match="não foi possível obter o commit")
```

Os repositórios dos testes configuram `user.name`/`user.email` locais.

- [ ] **Step 2: Rode e veja falhar.** `.venv/Scripts/python.exe -m pytest tests/unit/test_release_build.py` → FAIL.

- [ ] **Step 3: Implemente em `scripts/build_release.py`.**
  - `_fatos_do_produto` importa `PyMuPdfDocumentAnalyzer` (`zeny_project_handler.adapters.analysis.pymupdf_analyzer`), `InterpretadorRegrasExplicitas` (`zeny_project_handler.adapters.interpretation.rule_based`), `VERSAO_METODO_CONFORMIDADE` (`zeny_project_handler.application.compliance_analysis`) e lê `root / "src/zeny_project_handler/adapters/compliance/data/regras_conformidade_v1.json"`: `registry.version` e a contagem de `rules` com `enabled` verdadeiro.
  - `build_release` chama `_commit_de_origem()` e `_fatos_do_produto()` logo depois de `_validate_version`, antes de `_reset_directory`, para falhar antes de gastar build.
  - O corpo das notas mantém: as linhas de cliente/servidor/API/volume, o parágrafo da distribuição (cliente só a usuários finais etc.), o de upgrade e rollback, o de API/GMAX e o limite de homologação. Sai o parágrafo "Esta release inclui…" e o "O registro distribuído…", que dão lugar a:

```markdown
- Origem: commit `{commit}`.

## O que mudou desde a 0.5.0

- Dependências do cliente e do servidor atualizadas para versões sem vulnerabilidade corrigível conhecida.
- Fechar a janela do cliente com o servidor lento agora espera a rede encerrar, sem derrubar o programa, e os painéis avisam quando a rede encerrou.
- A extração recupera texto desenhado em contorno, antes perdido, nas folhas sem texto nativo.
- A leitura vetorial nova de símbolos está incluída como opção desligada por padrão (`ZENY_SERVER_SYMBOL_COMPOSITION=false`). Com ela desligada, a leitura de símbolos é a mesma da 0.5.0.

## Versões

O registro distribuído `{registro}` contém {n} regras habilitadas e usa o método de conformidade {metodo}. A extração usa a versão {extracao} e a interpretação {interpretacao}.
```

- [ ] **Step 4: Rode e veja passar.** Mesmo comando → PASS.

- [ ] **Step 5: Commit** com a suíte da área verde; rode a suíte inteira uma vez antes do relatório.

---

## Operação do orquestrador (fora das tarefas)

1. Integradas as tarefas, primeiro build: `.venv/Scripts/python.exe scripts/build_release.py --version 0.6.0 --output-root C:/Users/Caio/Desktop/repos/ZenyProjectHandler/dist/release`, medido com `date`; conferência com `sha256sum -c SHA256SUMS.txt`. Candidata registrada em `dist/release/ESTADO-0.6.0.md`.
2. Revisão final. Correção que mude código, `Dockerfile` ou script exige novo build, sobre o commit que entra.
3. `cmd.exe //c IniciarTestes.bat`.
4. T_build (build + conferência + gate) no handoff; recálculo dos marcos.
