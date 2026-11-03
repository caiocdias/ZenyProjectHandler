"""Guardas do modo ficha: cegueira do leitor, ordem da rodada de fichas e invariante do ADR 0017.

Complementa ``test_claude_curation_assets.py``. Os documentos são instruções; aqui se confere o
que protege a cegueira (o que o leitor nunca abre, o que grava e executa) e a operação (ordem
dos passos, limiar de ampliação da amostra, contagem do não-poste, recuperação após queda), com
os mesmos comandos nos dois documentos.
"""

from __future__ import annotations

import re

import pytest
from tests.unit.test_claude_curation_assets import (
    CONTRATO,
    LEITOR,
    ROOT,
    SKILL,
    agente,
    ferramentas,
    problemas_de_comandos,
    secao,
)

CLAUDE_MD = ROOT / "CLAUDE.md"
PROCEDIMENTO = "Procedimento, na ordem:"


def subsecao(texto: str, titulo: str) -> str:
    """Texto entre ``### titulo`` e o próximo cabeçalho ``##``/``###``."""
    encontrado = re.search(
        rf"^### {re.escape(titulo)}\s*$(.*?)(?=^#{{2,3}} |\Z)", texto, re.M | re.S
    )
    if encontrado is None:
        raise AssertionError(f"subseção '### {titulo}' ausente")
    return encontrado.group(1)


def ficha_do_leitor() -> str:
    return secao(agente(LEITOR)[1], "Modo ficha")


def plano(texto: str) -> str:
    return " ".join(texto.split())


def rodada_de_fichas(texto: str) -> str:
    return secao(texto, "Rodada de fichas do poste")


def procedimento(texto: str) -> str:
    rodada = rodada_de_fichas(texto)
    inicio = rodada.index(PROCEDIMENTO)
    fim = rodada.index("`validar` confere", inicio)
    return rodada[inicio:fim]


def passo(texto: str, numero: int) -> str:
    encontrado = re.search(rf"^{numero}\. (.*?)(?=^\d+\. |\Z)", procedimento(texto), re.M | re.S)
    assert encontrado is not None, f"passo {numero} ausente"
    return plano(encontrado.group(1))


@pytest.fixture(params=["skill", "contrato"])
def documento(request: pytest.FixtureRequest) -> str:
    caminho = SKILL if request.param == "skill" else CONTRATO
    return caminho.read_text(encoding="utf-8")


# --- leitor em modo ficha: cegueira -------------------------------------------------------


@pytest.mark.parametrize(
    "proibido",
    [
        "ficha/rascunho-*",
        "ficha/leitura-*.json",
        "ficha/congelamento.json",
        "ficha/comparacao.json",
        "ficha/referencia.json",
        "ficha/baseline-*",
        "fichas/",
    ],
)
def test_leitor_ficha_proibe_cada_caminho_cego_e_nao_o_permite(proibido: str) -> None:
    assert proibido in subsecao(ficha_do_leitor(), "Proibido a mais")
    assert proibido not in subsecao(ficha_do_leitor(), "Permitido a mais")


def test_leitor_ficha_proibe_rascunho_de_outro_leitor() -> None:
    assert "de outro leitor" in plano(subsecao(ficha_do_leitor(), "Proibido a mais"))


@pytest.mark.parametrize(
    "subcomando",
    ["congelar", "comparar", "consolidar", "baseline", "amostra", "responder", "taxa"],
)
def test_leitor_ficha_proibe_os_demais_subcomandos_do_cli(subcomando: str) -> None:
    assert f"`{subcomando}`" in subsecao(ficha_do_leitor(), "Proibido a mais")


def test_leitor_ficha_so_executa_o_validar_com_os_argumentos_do_proprio_leitor() -> None:
    permitido = subsecao(ficha_do_leitor(), "Permitido a mais")
    comandos = re.findall(r"^\s*\.venv/Scripts/python\.exe .*$", permitido, re.M)
    assert [c.strip() for c in comandos] == [
        ".venv/Scripts/python.exe -m scripts.curation_ficha validar --rodada RODADA --pdf ID "
        "--leitor LEITOR --arquivo RODADA/pdfs/ID/ficha/rascunho-LEITOR/ficha.json"
    ]
    assert problemas_de_comandos(ficha_do_leitor()) == []


def test_leitor_ficha_so_grava_a_propria_saida() -> None:
    permitido = plano(subsecao(ficha_do_leitor(), "Permitido a mais"))
    assert "apenas a saída `RODADA/pdfs/ID/ficha/rascunho-LEITOR/ficha.json`" in permitido
    assert "Edit" not in ficha_do_leitor()


def test_leitor_ficha_le_a_mais_so_o_esquema() -> None:
    permitido = subsecao(ficha_do_leitor(), "Permitido a mais")
    assert "docs/schemas/ficha-poste.schema.json" in permitido
    leituras = [linha for linha in permitido.splitlines() if linha.startswith("- Ler ")]
    assert len(leituras) == 1


def test_leitor_ficha_nao_grava_o_bloco_de_congelamento() -> None:
    assert "Não inclua o bloco `congelamento`" in plano(ficha_do_leitor())


def test_leitor_ficha_so_ativa_com_modo_e_leitor_e_mantem_o_proibido_normal() -> None:
    abertura = plano(ficha_do_leitor())
    assert "`modo: ficha`" in abertura
    assert "`leitor: a|b|c`" in abertura
    assert "Sem `modo: ficha`, ignore esta seção" in abertura
    assert 'a seção "Proibido" acima continua valendo' in abertura


def test_leitor_c_e_o_unico_a_receber_regioes_de_conferencia() -> None:
    entrada = plano(subsecao(ficha_do_leitor(), "Entrada do modo ficha"))
    assert "Só para o leitor `c`" in entrada
    assert "regioes-conferencia.json" in entrada
    for nome in ("RODADA", "ID", "sha256", "caminho_relativo", "modelo", "leitor"):
        assert f"`{nome}`" in entrada, nome
    for titulo in ("Permitido a mais", "Proibido a mais", "Regras da ficha"):
        assert "regioes-conferencia.json" not in subsecao(ficha_do_leitor(), titulo)


def test_leitor_ficha_exige_escopo_completo_para_a_e_b_e_regional_para_c() -> None:
    regras = plano(subsecao(ficha_do_leitor(), "Regras da ficha"))
    assert "Leitores `a` e `b`: escopo `completo`" in regras
    assert "todo tile `a_revisar` é revisado ou coberto por uma região ilegível" in regras
    assert "escopo `regional`, dentro das regiões recebidas" in regras
    assert "lendo só os tiles abertos que as tocam" in regras
    assert "só tiles que você realmente abriu" in regras


def test_leitor_ficha_traz_as_regras_de_conteudo_da_ficha() -> None:
    regras = plano(subsecao(ficha_do_leitor(), "Regras da ficha"))
    for trecho in (
        "Uma entrada por poste da rede",
        "`class_code` do inventário",
        "Vãos com o comprimento e o cabo escritos",
        "`null` só para o que a folha não tem",
        "`pendentes`",
        "atributos_extras.leitura.regioes_ilegiveis",
        "U+200B",
        "U+FEFF",
        'origem: "revisao_ia"',
        "continuam iguais",
    ):
        assert trecho in regras, trecho


def test_leitor_mantem_ferramentas_minimas() -> None:
    assert ferramentas(agente(LEITOR)[0]) == {"Read", "Write", "Glob", "Bash"}


# --- skill e contrato: procedimento -------------------------------------------------------


def test_skill_e_contrato_trazem_o_mesmo_procedimento() -> None:
    assert procedimento(SKILL.read_text(encoding="utf-8")) == procedimento(
        CONTRATO.read_text(encoding="utf-8")
    )


def test_skill_e_contrato_trazem_a_mesma_recuperacao_apos_queda() -> None:
    def recuperacao(texto: str) -> str:
        encontrado = re.search(r"^Recuperação após queda:.*?(?=\n\n|\Z)", texto, re.M | re.S)
        assert encontrado is not None
        return plano(encontrado.group(0))

    assert recuperacao(SKILL.read_text(encoding="utf-8")) == recuperacao(
        CONTRATO.read_text(encoding="utf-8")
    )


def test_procedimento_segue_a_ordem_dos_comandos(documento: str) -> None:
    proc = procedimento(documento)
    assert [int(n) for n in re.findall(r"^(\d+)\. ", proc, re.M)] == [1, 2, 3, 4, 5, 6]
    por_passo = {
        1: ("curation_round init", "curation_render"),
        2: ("`leitor: a` ou `b`", "`validar` e `congelar`"),
        3: ("`comparar`", "`leitor: c`", "`validar` e `congelar`"),
        4: ("`consolidar`",),
        5: ("`amostra`", "`responder`", "`taxa`"),
        6: ("`baseline`",),
    }
    for numero, marcos in por_passo.items():
        texto = passo(documento, numero)
        posicoes = [texto.index(marco) for marco in marcos]
        assert posicoes == sorted(posicoes), (numero, marcos)


def test_baseline_so_depois_de_todas_as_folhas_consolidadas(documento: str) -> None:
    assert passo(documento, 6).startswith("`baseline` só depois de todas as folhas consolidadas")
    assert all("`baseline`" not in passo(documento, n) for n in range(1, 6))


def test_baseline_sem_ocr_usa_native_only_e_registra_a_pendencia(documento: str) -> None:
    ultimo = passo(documento, 6)
    assert "--native-only" in ultimo
    assert "OCR português" in ultimo
    assert "pendência de OCR" in ultimo
    assert "relatório da rodada" in ultimo


def test_auditoria_amostral_nao_roda_no_modo_ficha_e_a_conferencia_e_o_leitor_c(
    documento: str,
) -> None:
    primeiro = passo(documento, 1)
    assert "No modo ficha a auditoria amostral de tiles não roda" in primeiro
    assert "o leitor C substitui a auditoria" in primeiro
    assert "não há inferência nem comparação de símbolos" in primeiro
    assert "sem `--anterior`" in primeiro


def test_leitores_a_e_b_sao_instancias_novas_em_paralelo_com_modo_ficha(documento: str) -> None:
    dois = passo(documento, 2)
    assert "instâncias novas" in dois
    assert "em paralelo" in dois
    assert "`modo: ficha`" in dois
    assert "`leitor: a` ou `b`" in dois
    assert "curadoria-leitor-visual" in dois
    assert "leitura incompleta volta ao mesmo leitor antes de congelar" in dois


def test_leitor_c_so_recebe_regioes_de_conferencia_e_nunca_as_leituras(documento: str) -> None:
    tres = passo(documento, 3)
    assert "instância nova" in tres
    assert "`leitor: c`" in tres
    assert "só `regioes-conferencia.json`" in tres
    assert "nunca `comparacao.json` nem as leituras de A e B" in tres


def test_dispensa_do_leitor_c_so_sem_regiao_ou_com_sem_terceiro_e_motivo(documento: str) -> None:
    quatro = passo(documento, 4)
    assert "Só sem região de conferência ou com `--sem-terceiro`" in quatro
    assert "motivo" in quatro
    assert "folha sem área anotável" in quatro


def test_amostra_ampliada_acima_de_20_por_cento_de_erro(documento: str) -> None:
    cinco = passo(documento, 5)
    assert "passar de 20%" in cinco
    assert "`--ampliar`" in cinco
    assert "rode `taxa` outra vez" in cinco
    assert "conferência dos recortes pelo usuário" in cinco


def test_taxa_conta_nao_poste_como_erro_e_mantem_no_denominador(documento: str) -> None:
    cinco = passo(documento, 5)
    assert 'conta o item marcado "não é poste" como erro' in cinco
    assert "mantém no denominador" in cinco


def test_recuperacao_manual_apos_queda_e_explicita(documento: str) -> None:
    rodada = plano(rodada_de_fichas(documento))
    for trecho in (
        "Recuperação após queda",
        "congelamento, comparação, consolidação ou amostra",
        "`comparacao.json` sem `regioes-conferencia.json`",
        "`amostra-vNNN` sem `amostra.json`",
        "o CLI recusa seguir",
        "A recuperação é manual e explícita",
        "remova o arquivo órfão, repita o comando e registre o fato no relatório da rodada",
    ):
        assert trecho in rodada, trecho


def test_comandos_da_rodada_de_fichas_existem_nos_clis(documento: str) -> None:
    assert problemas_de_comandos(rodada_de_fichas(documento)) == []


def test_rodada_de_fichas_cita_todos_os_subcomandos_do_cli(documento: str) -> None:
    rodada = rodada_de_fichas(documento)
    for subcomando in (
        "validar",
        "congelar",
        "comparar",
        "consolidar",
        "amostra",
        "responder",
        "taxa",
        "baseline",
    ):
        assert f"scripts.curation_ficha {subcomando}" in rodada, subcomando


# --- contrato: invariante do ADR 0017 -----------------------------------------------------


def test_invariante_do_adr_0017_traz_cada_clausula() -> None:
    texto = CONTRATO.read_text(encoding="utf-8")
    inicio = texto.index("Invariante do ADR 0017")
    paragrafo = plano(texto[inicio : texto.index("\n\n", inicio)])
    for clausula in (
        "os rótulos (fichas consolidadas) podem alimentar o treino",
        "a leitura de avaliação continua cega",
        "separado por folha",
        "congelado",
        "nunca usado no treino",
        "a pré-marcação assistida só vale no conjunto de treino",
        "conhecimento duradouro do analisador continua sendo mudança revisável",
        "algoritmos",
        "pacotes",
        "fixtures/testes versionados",
    ):
        assert clausula in paragrafo, clausula


def test_contrato_nao_proibe_mais_treino_com_rotulos() -> None:
    texto = CONTRATO.read_text(encoding="utf-8")
    assert "não treina o assistente" not in texto
    assert "não treina" not in texto.split("O fluxo usa a capacidade visual")[0]


def test_invariante_do_adr_0017_aparece_uma_vez_e_antes_do_fluxo() -> None:
    texto = CONTRATO.read_text(encoding="utf-8")
    assert texto.count("Invariante do ADR 0017") == 1
    assert texto.index("Invariante do ADR 0017") < texto.index("O fluxo usa a capacidade visual")


# --- CLAUDE.md ----------------------------------------------------------------------------


def test_claude_md_lista_o_cli_de_fichas_e_aponta_a_secao_do_contrato() -> None:
    texto = plano(CLAUDE_MD.read_text(encoding="utf-8"))
    assert "`curation_ficha.py`" in texto
    assert 'seção "Rodada de fichas do poste"' in texto
    assert "leitores `a`/`b`/`c` em modo ficha" in texto
    assert (ROOT / "scripts" / "curation_ficha.py").is_file()


# --- sentinelas: os helpers falham quando o texto regride ----------------------------------


def test_helper_de_passo_falha_para_passo_inexistente() -> None:
    with pytest.raises(AssertionError):
        passo(SKILL.read_text(encoding="utf-8"), 9)


def test_helper_de_subsecao_falha_para_subsecao_inexistente() -> None:
    with pytest.raises(AssertionError):
        subsecao(ficha_do_leitor(), "Liberado a mais")
