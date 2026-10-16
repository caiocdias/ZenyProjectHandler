"""Contrato dos agentes, da skill e das permissões do Claude Code para a curadoria de simbologia.

Os arquivos de ``.claude/`` são instruções, não código; estes testes conferem o que dá para
conferir de forma determinística: frontmatter, ferramentas mínimas dos papéis cegos, comandos
``scripts.*`` que existem de verdade (módulo, subcomando e opções), permissões sem curingas amplos
e ausência de histórico de execução ou instruções de commit.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import shutil
from pathlib import Path
from typing import NoReturn
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLAUDE = ROOT / ".claude"
AGENTES = CLAUDE / "agents"
SKILL = CLAUDE / "skills" / "curadoria-simbologia" / "SKILL.md"
SETTINGS = CLAUDE / "settings.json"
SCRIPTS = ROOT / "scripts"
CONTRATO = ROOT / "docs" / "fluxo-curadoria-incremental-simbologia.md"
# Estado local que o próprio Claude Code cria em ``.claude/`` (ignorado pelo Git).
ESTADO_LOCAL = ("settings.local.json", "worktrees")

LEITOR = "curadoria-leitor-visual"
AUDITOR = "curadoria-auditor-visual"
INVESTIGADOR = "curadoria-investigador"
CORRETOR = "curadoria-corretor"
VERIFICADOR = "curadoria-verificador"
NOMES_AGENTES = (LEITOR, AUDITOR, INVESTIGADOR, CORRETOR, VERIFICADOR)

FERRAMENTAS_CONHECIDAS = frozenset(
    {"Read", "Write", "Edit", "Glob", "Grep", "Bash", "PowerShell", "NotebookEdit"}
)
FERRAMENTAS_LEITURA_VISUAL = frozenset({"Read", "Write", "Glob", "Bash"})
FERRAMENTAS_DE_EDICAO = frozenset({"Edit", "Write", "NotebookEdit"})

# Caminhos da rodada que cada papel cego nunca abre (devem constar da seção "Proibido").
PROIBIDOS_LEITOR = (
    "inferencia-",
    "comparacao-",
    "concordancia-",
    "auditoria/",
    "leitura-auditoria/",
    "ondas/",
    "checkpoint.json",
)
PROIBIDOS_AUDITOR = (*PROIBIDOS_LEITOR, "referencia/", "leitura/", "indice-tiles.json")

# ``.venv/Scripts/python.exe -m scripts.X`` (Git Bash) ou ``.\.venv\Scripts\python.exe``.
COMANDO = re.compile(
    r"(?:\.\\)?\.venv[\\/]Scripts[\\/]python\.exe\s+-m\s+scripts\.([A-Za-z0-9_]+)([^\n`|;&]*)"
)
MENCAO_MODULO = re.compile(r"(?<![\w.])scripts\.([A-Za-z_][A-Za-z0-9_]*)")
MENCAO_ARQUIVO = re.compile(r"(?<![\w.])scripts/([A-Za-z_][A-Za-z0-9_]*)\.py")
OPCAO = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")
ID_ETAPA = re.compile(r"\bE(?:0[1-9]|1[01])\b")
REGRA_PERMITIDA = re.compile(
    r"Bash\(\.venv/Scripts/python\.exe -m "
    r"(?P<alvo>scripts\.(?P<modulo>curation_[a-z0-9_]+|benchmark_[a-z0-9_]+|coverage_matrix_e16"
    r"|reconcile_symbol_benchmark)|pytest|ruff|mypy) \*\)"
)
# CLIs que a skill executa além dos ``curation_*`` (gates sintéticos, composição, matriz e
# exercício de persistência/exportação do fechamento).
CLIS_DO_FECHAMENTO = frozenset(
    {
        "benchmark_symbols",
        "reconcile_symbol_benchmark",
        "benchmark_review_e14",
        "benchmark_packages_e07",
        "coverage_matrix_e16",
        "curation_coverage_e16",
        "audit_symbol_packages",
    }
)


# --- apoio --------------------------------------------------------------------------------


def ler_frontmatter(texto: str) -> tuple[dict[str, str], str]:
    """Frontmatter YAML plano (``chave: valor`` por linha) e o corpo depois dele."""
    linhas = texto.splitlines()
    if not linhas or linhas[0].strip() != "---":
        raise ValueError("arquivo sem frontmatter iniciado por ---")
    try:
        fim = next(i for i in range(1, len(linhas)) if linhas[i].strip() == "---")
    except StopIteration as erro:
        raise ValueError("frontmatter sem --- de fechamento") from erro
    campos: dict[str, str] = {}
    for linha in linhas[1:fim]:
        if not linha.strip():
            continue
        chave, separador, valor = linha.partition(":")
        if not separador or not chave or chave != chave.strip() or " " in chave:
            raise ValueError(f"linha de frontmatter inválida: {linha!r}")
        valor = valor.strip()
        if not valor:
            raise ValueError(f"chave {chave!r} sem valor")
        if ": " in valor or " #" in valor:
            raise ValueError(f"valor de {chave!r} quebraria o YAML sem aspas: {valor!r}")
        if chave in campos:
            raise ValueError(f"chave repetida: {chave!r}")
        campos[chave] = valor
    return campos, "\n".join(linhas[fim + 1 :])


def ferramentas(campos: dict[str, str]) -> set[str]:
    return {item.strip() for item in campos["tools"].split(",") if item.strip()}


def agente(nome: str) -> tuple[dict[str, str], str]:
    return ler_frontmatter((AGENTES / f"{nome}.md").read_text(encoding="utf-8"))


def secao(corpo: str, titulo: str) -> str:
    """Texto entre ``## titulo`` e o próximo cabeçalho de mesmo nível."""
    encontrado = re.search(rf"^## {re.escape(titulo)}\s*$(.*?)(?=^## |\Z)", corpo, re.M | re.S)
    if encontrado is None:
        raise AssertionError(f"seção '## {titulo}' ausente")
    return encontrado.group(1)


class _ParserCapturadoError(Exception):
    def __init__(self, parser: argparse.ArgumentParser) -> None:
        super().__init__("parser capturado")
        self.parser = parser


def _capturar(parser: argparse.ArgumentParser, *args: object, **kwargs: object) -> NoReturn:
    raise _ParserCapturadoError(parser)


def parser_do_cli(modulo: str) -> argparse.ArgumentParser:
    """O ``ArgumentParser`` real do CLI: ``_parser()`` ou o que ``main()`` monta e analisa."""
    carregado = importlib.import_module(f"scripts.{modulo}")
    construtor = getattr(carregado, "_parser", None)
    if callable(construtor):
        parser = construtor()
        assert isinstance(parser, argparse.ArgumentParser)
        return parser
    with mock.patch.object(
        argparse.ArgumentParser, "parse_args", autospec=True, side_effect=_capturar
    ):
        try:
            carregado.main()
        except _ParserCapturadoError as capturado:
            return capturado.parser
    raise AssertionError(f"scripts.{modulo}.main() não analisou argumentos")


def opcoes_do_cli(modulo: str) -> tuple[set[str], dict[str, set[str]]]:
    """Opções do parser principal e de cada subcomando."""
    parser = parser_do_cli(modulo)
    subcomandos: dict[str, set[str]] = {}
    for acao in parser._actions:
        if isinstance(acao, argparse._SubParsersAction):
            for nome, sub in acao.choices.items():
                subcomandos[nome] = set(sub._option_string_actions)
    return set(parser._option_string_actions), subcomandos


def problemas_de_comandos(texto: str, scripts: Path = SCRIPTS) -> list[str]:
    """Módulos ``scripts.*`` inexistentes e subcomandos/opções que o CLI citado não define.

    As opções de cada linha são conferidas contra o parser do subcomando citado (mais as do
    parser principal), lidas do ``argparse`` real do CLI.
    """
    problemas: list[str] = []
    citados = {*MENCAO_MODULO.findall(texto), *MENCAO_ARQUIVO.findall(texto)}
    for modulo in sorted(citados):
        if not (scripts / f"{modulo}.py").is_file():
            problemas.append(f"módulo inexistente: scripts.{modulo}")
    for modulo, resto in COMANDO.findall(texto):
        if not (scripts / f"{modulo}.py").is_file():
            continue
        gerais, subcomandos = opcoes_do_cli(modulo)
        validas = gerais
        if subcomandos:
            tokens = resto.split()
            subcomando = tokens[0] if tokens else ""
            if subcomando not in subcomandos:
                problemas.append(f"subcomando inexistente: scripts.{modulo} {subcomando!r}")
                continue
            validas = gerais | subcomandos[subcomando]
        for opcao in OPCAO.findall(resto):
            if opcao not in validas:
                problemas.append(f"opção inexistente: scripts.{modulo} {opcao}")
    return problemas


def arquivos_claude(raiz: Path = CLAUDE) -> list[Path]:
    """Arquivos versionáveis de ``.claude/``, sem o estado local criado pelo Claude Code."""
    return sorted(
        caminho
        for caminho in raiz.rglob("*")
        if caminho.is_file() and caminho.relative_to(raiz).parts[0] not in ESTADO_LOCAL
    )


def alvo_da_regra(regra: str) -> str:
    encontrado = REGRA_PERMITIDA.fullmatch(regra)
    assert encontrado is not None, f"permissão fora do previsto: {regra}"
    return encontrado.group("alvo")


def regras_allow() -> list[str]:
    dados = json.loads(SETTINGS.read_text(encoding="utf-8"))
    regras = dados["permissions"]["allow"]
    assert isinstance(regras, list)
    return [str(regra) for regra in regras]


# --- agentes ------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", NOMES_AGENTES)
def test_agente_tem_frontmatter_valido(nome: str) -> None:
    campos, corpo = agente(nome)
    assert set(campos) >= {"name", "description", "tools"}
    assert campos["name"] == nome
    assert len(campos["description"]) >= 60
    usadas = ferramentas(campos)
    assert usadas, "tools vazio"
    assert usadas <= FERRAMENTAS_CONHECIDAS, usadas - FERRAMENTAS_CONHECIDAS
    assert "Agent" not in usadas, "subagentes não disparam subagentes"
    assert len(corpo.strip()) > 500


def test_nao_ha_agentes_alem_dos_cinco_papeis() -> None:
    assert sorted(caminho.stem for caminho in AGENTES.glob("*.md")) == sorted(NOMES_AGENTES)


@pytest.mark.parametrize("nome", [LEITOR, AUDITOR])
def test_papeis_cegos_tem_so_ferramentas_minimas(nome: str) -> None:
    usadas = ferramentas(agente(nome)[0])
    assert usadas <= FERRAMENTAS_LEITURA_VISUAL, usadas - FERRAMENTAS_LEITURA_VISUAL
    assert "Read" in usadas
    assert "Write" in usadas
    assert not usadas & (FERRAMENTAS_DE_EDICAO - {"Write"}), "única edição permitida é Write"


@pytest.mark.parametrize(
    ("nome", "proibidos"), [(LEITOR, PROIBIDOS_LEITOR), (AUDITOR, PROIBIDOS_AUDITOR)]
)
def test_papeis_cegos_proibem_predicoes_e_resultados(nome: str, proibidos: tuple[str, ...]) -> None:
    proibido = secao(agente(nome)[1], "Proibido")
    faltando = [caminho for caminho in proibidos if caminho not in proibido]
    assert not faltando, f"{nome} não proíbe {faltando}"


def test_auditor_le_so_os_tiles_recebidos() -> None:
    corpo = agente(AUDITOR)[1]
    permitido = secao(corpo, "Permitido")
    assert "amostra" in permitido
    assert "render/" in permitido


@pytest.mark.parametrize("nome", [INVESTIGADOR, VERIFICADOR])
def test_investigador_e_verificador_nao_editam(nome: str) -> None:
    usadas = ferramentas(agente(nome)[0])
    assert not usadas & FERRAMENTAS_DE_EDICAO, usadas & FERRAMENTAS_DE_EDICAO
    assert "Read" in usadas


def test_corretor_edita_e_exige_fixture_sintetica() -> None:
    campos, corpo = agente(CORRETOR)
    assert {"Read", "Edit", "Write", "Bash"} <= ferramentas(campos)
    texto = corpo.lower()
    for termo in ("fixture sintética", "positivo", "negativo", "arquivos permitidos"):
        assert termo in texto, termo


# --- skill --------------------------------------------------------------------------------


def test_skill_tem_frontmatter_valido() -> None:
    campos, corpo = ler_frontmatter(SKILL.read_text(encoding="utf-8"))
    assert campos["name"] == "curadoria-simbologia"
    assert len(campos["description"]) >= 60
    assert len(corpo.strip()) > 2000


def test_skill_descreve_o_fluxo_por_ondas() -> None:
    corpo = ler_frontmatter(SKILL.read_text(encoding="utf-8"))[1]
    obrigatorios = (
        "entre 3 e 5",
        "--concorrencia",
        "rodada.json",
        "Modo de reserva",
        "general-purpose",
        "em série, na árvore principal",
        "uma de cada vez",
        "Integração serial",
        "IniciarTestes.bat",
        "matriz-simbologia-curadoria-atual.csv",
        "matriz-simbologia-e16.csv",
        "relatorio.md",
        "--exposicao sim",
        "falhas_execucao",
        "acoplamentos",
        "Nunca faça commit",
        "RODADA/inicial/",
        "--demand RODADA/demanda.json",
        "Pendências acionáveis",
        "no máximo dois ciclos",
        "TP/FP/FN sintéticos inicial",
        "Sem ganho validado",
        "UI/exportações",
        "herdam o modelo",
        "duplicata",
    )
    faltando = [termo for termo in obrigatorios if termo not in corpo]
    assert not faltando, faltando
    for nome in NOMES_AGENTES:
        assert nome in corpo, f"a skill não usa {nome}"


def test_skill_cobre_todos_os_clis_da_curadoria() -> None:
    corpo = SKILL.read_text(encoding="utf-8")
    invocados = {modulo for modulo, _ in COMANDO.findall(corpo)}
    curadoria = {caminho.stem for caminho in SCRIPTS.glob("curation_*.py")}
    assert curadoria <= invocados, curadoria - invocados
    assert invocados >= CLIS_DO_FECHAMENTO, CLIS_DO_FECHAMENTO - invocados


def test_contrato_e_skill_executam_os_mesmos_clis() -> None:
    """Paridade contrato↔skill: os mesmos comandos (módulo, subcomando e opções), linha a linha."""
    contrato = CONTRATO.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")

    def comandos(texto: str) -> set[tuple[str, str]]:
        return {(modulo, " ".join(resto.split())) for modulo, resto in COMANDO.findall(texto)}

    no_contrato, na_skill = comandos(contrato), comandos(skill)
    assert no_contrato - na_skill == set(), "só no contrato"
    assert na_skill - no_contrato == set(), "só na skill"
    assert problemas_de_comandos(contrato) == []


@pytest.mark.parametrize("arquivo", [SKILL, CONTRATO])
def test_toda_inferencia_da_rodada_roda_o_pipeline(arquivo: Path) -> None:
    corpo = arquivo.read_text(encoding="utf-8")
    inferencias = [resto for modulo, resto in COMANDO.findall(corpo) if modulo == "curation_infer"]
    assert inferencias
    for resto in inferencias:
        assert "--pipeline" in resto.split(), resto


def test_benchmark_review_roda_sobre_a_inferencia_do_corpus_inteiro() -> None:
    corpo = SKILL.read_text(encoding="utf-8")
    comandos = {
        modulo: resto
        for modulo, resto in COMANDO.findall(corpo)
        if modulo in {"benchmark_review_e14", "benchmark_symbols"} and "examples" in resto
    }
    assert "--root examples" in comandos["benchmark_symbols"]
    assert "--pdf" not in comandos["benchmark_symbols"]
    revisao = comandos["benchmark_review_e14"]
    assert "--root examples" in revisao
    assert "fechamento/corpus/" in revisao


@pytest.mark.parametrize("arquivo", [SKILL, *(AGENTES / f"{nome}.md" for nome in NOMES_AGENTES)])
def test_comandos_citados_existem(arquivo: Path) -> None:
    assert problemas_de_comandos(arquivo.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    ("linha", "esperado"),
    [
        (".venv/Scripts/python.exe -m scripts.curation_inexistente --rodada R", "inexistente: scr"),
        ("Rode `scripts.curation_fantasma` antes.", "módulo inexistente"),
        (".venv/Scripts/python.exe -m scripts.curation_round fechar --rodada R", "subcomando"),
        (".venv/Scripts/python.exe -m scripts.curation_backlog --rodada R --todas", "opção"),
        (".venv/Scripts/python.exe -m scripts.curation_audit concordancia --ampliar", "opção"),
        (".venv/Scripts/python.exe -m scripts.coverage_matrix_e16 --matrix M", "opção"),
    ],
)
def test_verificacao_de_comandos_detecta_erro_numa_copia(
    tmp_path: Path, linha: str, esperado: str
) -> None:
    copia = tmp_path / "SKILL.md"
    shutil.copyfile(SKILL, copia)
    assert problemas_de_comandos(copia.read_text(encoding="utf-8")) == []
    with copia.open("a", encoding="utf-8") as saida:
        saida.write(f"\n```bash\n{linha}\n```\n")
    problemas = problemas_de_comandos(copia.read_text(encoding="utf-8"))
    assert problemas
    assert any(esperado in problema for problema in problemas), problemas


# --- conteúdo de .claude/ -----------------------------------------------------------------


@pytest.mark.parametrize("arquivo", arquivos_claude() if CLAUDE.is_dir() else [CLAUDE])
def test_claude_nao_guarda_historico_nem_instrucao_de_commit(arquivo: Path) -> None:
    texto = arquivo.read_text(encoding="utf-8")
    assert "roadmap" not in texto.lower()
    assert ID_ETAPA.findall(texto) == []
    for proibido in ("git commit", "git push", "--no-verify", "git reset --hard"):
        assert proibido not in texto, proibido
    assert not re.search(r"[A-Za-z]:[\\/]Users", texto), "caminho local absoluto"


def test_correcoes_rodam_em_serie_sem_worktree() -> None:
    corretor = agente(CORRETOR)
    assert "árvore principal" in corretor[0]["description"]
    for arquivo in arquivos_claude():
        texto = arquivo.read_text(encoding="utf-8")
        assert 'isolation: "worktree"' not in texto, arquivo
        assert "hash-object" not in texto, arquivo


def test_estado_local_do_claude_code_fica_fora_da_verificacao(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "a.md").write_text("ok", encoding="utf-8")
    (tmp_path / "settings.local.json").write_text("{}", encoding="utf-8")
    copia = tmp_path / "worktrees" / "agente-1"
    copia.mkdir(parents=True)
    (copia / "README.md").write_text("E08 roadmap git commit", encoding="utf-8")
    relativos = [caminho.relative_to(tmp_path).as_posix() for caminho in arquivos_claude(tmp_path)]
    assert relativos == ["agents/a.md"]


def test_estado_local_do_claude_code_e_ignorado_pelo_git() -> None:
    linhas = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".claude/settings.local.json" in linhas
    assert ".claude/worktrees/" in linhas


def test_claude_contem_apenas_os_arquivos_esperados() -> None:
    relativos = sorted(caminho.relative_to(CLAUDE).as_posix() for caminho in arquivos_claude())
    esperados = sorted(
        ["settings.json", "skills/curadoria-simbologia/SKILL.md"]
        + [f"agents/{nome}.md" for nome in NOMES_AGENTES]
    )
    assert relativos == esperados


# --- permissões ---------------------------------------------------------------------------


def test_settings_tem_so_permissoes_allow() -> None:
    dados = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert set(dados) == {"permissions"}
    assert set(dados["permissions"]) == {"allow"}


def test_permissoes_sem_curingas_amplos_e_so_comandos_previstos() -> None:
    regras = regras_allow()
    assert regras
    assert len(regras) == len(set(regras)), "regra repetida"
    for regra in regras:
        assert regra.count("*") == 1, regra
        encontrado = REGRA_PERMITIDA.fullmatch(regra)
        assert encontrado is not None, f"permissão fora do previsto: {regra}"
        modulo = encontrado.group("modulo")
        if modulo is not None:
            assert (SCRIPTS / f"{modulo}.py").is_file(), regra


def test_permissoes_cobrem_os_clis_da_curadoria_e_os_gates() -> None:
    alvos = {alvo_da_regra(regra) for regra in regras_allow()}
    curadoria = {f"scripts.{caminho.stem}" for caminho in SCRIPTS.glob("curation_*.py")}
    esperados = curadoria | {
        "scripts.coverage_matrix_e16",
        "scripts.benchmark_packages_e07",
        "scripts.benchmark_symbols",
        "scripts.benchmark_review_e14",
        "scripts.reconcile_symbol_benchmark",
        "pytest",
        "ruff",
        "mypy",
    }
    assert esperados <= alvos, esperados - alvos


def test_verificacao_de_permissoes_recusa_regra_ampla() -> None:
    for regra in ("Bash(*)", "Bash(.venv/Scripts/python.exe *)", "Bash(git *)"):
        assert REGRA_PERMITIDA.fullmatch(regra) is None, regra
