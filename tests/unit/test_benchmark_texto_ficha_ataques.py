"""Ataques ao benchmark de recall de texto da ficha: fronteira, normalização, atribuição,
erro afirmado e CLI (valores inventados)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from scripts.benchmark_texto_ficha import TextoMedido, main, recall_texto
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    pdf_texto_nativo,
    tabela_do_alfabeto,
)


def _poste(
    identificador: str | None = None,
    *,
    poste: str | None = None,
    estruturas: Sequence[str] = (),
    coordenada: dict[str, Any] | None = None,
    pendentes: Sequence[str] = (),
    centro: tuple[float, float] = (0.5, 0.5),
    pagina: int = 1,
    id_: str = "P1",
) -> dict[str, Any]:
    x, y = centro
    return {
        "id": id_,
        "pagina": pagina,
        "bbox": [x - 0.005, y - 0.005, x + 0.005, y + 0.005],
        "identificador": identificador,
        "estruturas": list(estruturas),
        "poste": poste,
        "coordenada": coordenada,
        "simbolos": [],
        "pendentes": list(pendentes),
    }


def _ref(*postes: dict[str, Any]) -> dict[str, Any]:
    return {"postes": list(postes)}


def _t(texto: str, centro: tuple[float, float] = (0.5, 0.52)) -> TextoMedido:
    return TextoMedido(texto, centro, "nativo")


def _conta(r: dict[str, dict[str, int]], campo: str) -> tuple[int, int, int]:
    c = r[campo]
    return c["total"], c["acertos"], c["erros_afirmados"]


# --- fronteira e escape -----------------------------------------------------------------


@pytest.mark.parametrize("texto", ["AP1", "P1X", "P12", "1P1", "P1P"])
def test_valor_colado_a_alfanumerico_nao_e_acerto(texto: str) -> None:
    r = recall_texto(_ref(_poste(poste="P1")), [_t(texto)])
    assert r["poste"]["acertos"] == 0


@pytest.mark.parametrize("texto", ["(P1)", "P1,", "P1/P2", "-P1-", "P1 P2", "E:P1"])
def test_valor_cercado_por_pontuacao_ou_espaco_e_acerto(texto: str) -> None:
    r = recall_texto(_ref(_poste(poste="P1")), [_t(texto)])
    assert r["poste"]["acertos"] == 1


def test_estrutura_n1_nao_casa_n1a() -> None:
    r = recall_texto(_ref(_poste(estruturas=["N1"])), [_t("N1A")])
    assert _conta(r, "estruturas") == (1, 0, 1)  # fusão: afirma um valor errado


def test_valor_com_parenteses_casa_literalmente() -> None:
    r = recall_texto(_ref(_poste(estruturas=["U4(1)"])), [_t("(U4(1))")])
    assert r["estruturas"]["acertos"] == 1


def test_parenteses_nao_viram_grupo_de_regex() -> None:
    # Sem escape, "U4(1)" viraria "U41" e casaria o texto abaixo.
    r = recall_texto(_ref(_poste(estruturas=["U4(1)"])), [_t("U41")])
    assert r["estruturas"]["acertos"] == 0


def test_ponto_nao_vira_curinga() -> None:
    r = recall_texto(_ref(_poste(poste="A.B")), [_t("AXB")])
    assert r["poste"]["acertos"] == 0


@pytest.mark.parametrize("especial", ["A+B", "A*B", "A?B", "A[1]", "A|B", "A^B", "A$B", "A\\B"])
def test_caracteres_especiais_de_regex_sao_literais(especial: str) -> None:
    r = recall_texto(_ref(_poste(poste=especial)), [_t(f"x {especial} y")])
    assert r["poste"]["acertos"] == 1


def test_valor_com_hifen_respeita_fronteira_dos_digitos() -> None:
    ref = _ref(_poste(poste="11-300"))
    assert recall_texto(ref, [_t("(11-300)")])["poste"]["acertos"] == 1
    assert recall_texto(ref, [_t("211-300")])["poste"]["acertos"] == 0
    assert recall_texto(ref, [_t("11-3001")])["poste"]["acertos"] == 0


# --- normalização ----------------------------------------------------------------------


def test_nfkc_largura_total_casa() -> None:
    r = recall_texto(_ref(_poste(poste="P1")), [_t(chr(0xFF30) + chr(0xFF11))])
    assert r["poste"]["acertos"] == 1


def test_minusculas_no_texto_e_na_referencia() -> None:
    r = recall_texto(_ref(_poste(poste="dt p1")), [_t("Dt  P1")])
    assert r["poste"]["acertos"] == 1


def test_espacos_nao_ascii_tab_e_quebra_colapsam() -> None:
    texto = "DT" + chr(0xA0) + chr(9) + "11/300" + chr(10)
    r = recall_texto(_ref(_poste(poste="DT 11/300")), [_t(texto)])
    assert r["poste"]["acertos"] == 1


def test_valor_so_de_espacos_na_referencia_nao_conta() -> None:
    r = recall_texto(_ref(_poste(estruturas=["   "])), [_t("X")])
    assert r["estruturas"]["total"] == 0


# --- atribuição ------------------------------------------------------------------------


def test_duas_ocorrencias_servem_a_duas_instancias() -> None:
    ref = _ref(_poste(estruturas=["N1", "N1"]))
    assert recall_texto(ref, [_t("N1 N1")])["estruturas"]["acertos"] == 2
    assert recall_texto(ref, [_t("N1")])["estruturas"]["acertos"] == 1


def test_uma_ocorrencia_de_texto_serve_leste_ou_norte_nao_os_dois() -> None:
    c = {"leste": 100, "norte": 100, "zona": "23K"}
    r = recall_texto(_ref(_poste(coordenada=c)), [_t("100")])
    assert _conta(r, "coordenada") == (2, 1, 0)


def test_atribuicao_gulosa_global_pela_menor_distancia_independe_da_ordem_da_referencia() -> None:
    longe = _poste(poste="N1", centro=(0.4, 0.2), id_="P2")
    perto = _poste(estruturas=["N1"], centro=(0.2, 0.2), id_="P1")
    texto = _t("N1", (0.27, 0.2))
    for ordem in ((longe, perto), (perto, longe)):
        r = recall_texto(_ref(*ordem), [texto])
        assert r["estruturas"]["acertos"] == 1
        assert r["poste"]["acertos"] == 0


def test_empate_de_distancia_e_deterministico_e_independe_da_ordem_dos_textos() -> None:
    ref = _ref(_poste(poste="N1", centro=(0.3, 0.3)), _poste(estruturas=["N1"], centro=(0.5, 0.3)))
    t = _t("N1", (0.4, 0.3))
    resultados = {
        json.dumps(recall_texto(ref, lote), sort_keys=True)
        for lote in ([t], [t, _t("ZZ", (0.9, 0.9))], [_t("ZZ", (0.9, 0.9)), t])
    }
    assert len(resultados) == 1


def test_empate_entre_dois_textos_para_uma_instancia() -> None:
    ref = _ref(_poste(poste="N1"))
    a, b = _t("N1", (0.5, 0.53)), _t("N1", (0.5, 0.47))
    assert recall_texto(ref, [a, b]) == recall_texto(ref, [b, a])
    assert recall_texto(ref, [a, b])["poste"]["acertos"] == 1


# --- campos que não contam -------------------------------------------------------------


def test_pendente_de_um_campo_nao_apaga_os_demais() -> None:
    p = _poste(
        "ID9",
        poste="P3",
        estruturas=["N1"],
        coordenada={"leste": 10, "norte": 20, "zona": "23K"},
        pendentes=["poste", "coordenada"],
    )
    r = recall_texto(_ref(p), [])
    assert _conta(r, "identificador") == (1, 0, 0)
    assert _conta(r, "poste") == (0, 0, 0)
    assert _conta(r, "estruturas") == (1, 0, 0)
    assert _conta(r, "coordenada") == (0, 0, 0)


def test_pendente_com_texto_presente_nao_gera_acerto_nem_erro() -> None:
    r = recall_texto(_ref(_poste(poste="P1", pendentes=["poste"])), [_t("P1"), _t("P2")])
    assert _conta(r, "poste") == (0, 0, 0)


def test_coordenada_nao_inteira_exige_fronteira_decimal() -> None:
    c = {"leste": 1.5, "norte": 7801234.5, "zona": "23K"}
    r = recall_texto(_ref(_poste(coordenada=c)), [_t("N=7801234.55"), _t("E 1.5")])
    assert _conta(r, "coordenada")[:2] == (2, 1)


def test_coordenada_float_inteira_nao_casa_digito_colado() -> None:
    c = {"leste": 612345.0, "norte": 1.0, "zona": "23K"}
    r = recall_texto(_ref(_poste(coordenada=c)), [_t("6123450")])
    assert r["coordenada"]["acertos"] == 0


# --- erro afirmado ---------------------------------------------------------------------


@pytest.mark.parametrize("lido", ["ABXDEF", "ABCDE", "ABCDEFG", "AXCDYF"])
def test_erro_afirmado_com_comprimento_e_edicao_dentro_do_limite(lido: str) -> None:
    r = recall_texto(_ref(_poste(poste="ABCDEF")), [_t(lido)])
    assert _conta(r, "poste") == (1, 0, 1)


@pytest.mark.parametrize("lido", ["AXYZEF", "ABCD", "QABXDEFG", "UVWXYZ"])
def test_nao_e_erro_afirmado_com_edicao_3_ou_comprimento_a_2(lido: str) -> None:
    r = recall_texto(_ref(_poste(poste="ABCDEF")), [_t(lido)])
    assert _conta(r, "poste") == (1, 0, 0)


@pytest.mark.parametrize("lido", ["2N4", "N42", "XN4X"])
def test_fusao_conta_como_erro_afirmado(lido: str) -> None:
    r = recall_texto(_ref(_poste(estruturas=["N4"])), [_t(lido)])
    assert _conta(r, "estruturas") == (1, 0, 1)


def test_raio_de_0_05_separa_erro_de_ausencia() -> None:
    ref = _ref(_poste(poste="ABCDEF", centro=(0.5, 0.5)))
    assert recall_texto(ref, [_t("ABXDEF", (0.5, 0.54))])["poste"]["erros_afirmados"] == 1
    assert recall_texto(ref, [_t("ABXDEF", (0.5, 0.56))])["poste"]["erros_afirmados"] == 0


def test_so_o_texto_mais_proximo_pode_ser_erro() -> None:
    ref = _ref(_poste(poste="ABCDEF"))
    textos = [_t("ZZZZZZZZ", (0.5, 0.51)), _t("ABXDEF", (0.5, 0.53))]
    assert recall_texto(ref, textos)["poste"]["erros_afirmados"] == 0


def test_valor_legitimo_de_outro_poste_nao_e_erro_afirmado() -> None:
    a = _poste(estruturas=["N1"], centro=(0.2, 0.2), id_="P1")
    b = _poste(estruturas=["N2"], centro=(0.21, 0.2), id_="P2")
    r = recall_texto(_ref(a, b), [_t("N2", (0.2, 0.21))])
    assert _conta(r, "estruturas") == (2, 1, 0)


def test_valor_que_e_prefixo_de_outro_valor_acertado_nao_vira_fusao() -> None:
    ref = _ref(_poste(estruturas=["N4", "N42"]))
    r = recall_texto(ref, [_t("N42", (0.5, 0.51))])
    assert _conta(r, "estruturas") == (2, 1, 0)


def test_acerto_e_erro_sao_mutuamente_exclusivos_na_mesma_instancia() -> None:
    ref = _ref(_poste(poste="P1"))
    r = recall_texto(ref, [_t("P1", (0.5, 0.51)), _t("P12", (0.5, 0.505))])
    assert _conta(r, "poste") == (1, 1, 0)


def test_referencia_vazia_devolve_os_quatro_campos_zerados() -> None:
    r = recall_texto(_ref(), [_t("X")])
    assert list(r) == ["identificador", "poste", "estruturas", "coordenada"]
    assert all(c == {"total": 0, "acertos": 0, "erros_afirmados": 0} for c in r.values())


# --- CLI -------------------------------------------------------------------------------


def _pdfs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    tabela = tabela_do_alfabeto(tmp_path)
    assert tabela.sha256
    arquivo = tmp_path / "tabela-alfabeto.json"
    linhas = [LinhaTexto("P7", (40.0, 60.0), 5.0), LinhaTexto("11-300", (40.0, 120.0), 5.0)]
    pasta = tmp_path / "origem"
    pasta.mkdir()
    nativo = pdf_texto_nativo(pasta / "segredo-nativo.pdf", linhas)
    contorno = pdf_texto_contorno(pasta / "segredo-contorno.pdf", linhas)
    return arquivo, pasta, nativo, contorno


def _referencia(
    rodada: Path,
    pdf_id: str,
    pdf: Path,
    *,
    sha: str | None = None,
    escopo: dict[str, Any] | None = None,
) -> None:
    pasta = rodada / "pdfs" / pdf_id / "ficha"
    pasta.mkdir(parents=True)
    ficha = {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": sha or hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "escopo_anotacao": escopo or {"tipo": "completo"},
        "postes": [_poste(poste="P7", estruturas=["11-300"], centro=(0.10, 0.30))],
        "vaos": [],
    }
    (pasta / "referencia.json").write_text(json.dumps(ficha), encoding="utf-8")


def _rodar(rodada: Path, pasta: Path, saida: Path, tabela: Path | None) -> dict[str, Any]:
    args = ["--rodada", str(rodada), "--pdfs", str(pasta), "--saida", str(saida)]
    if tabela is not None:
        args += ["--tabela", str(tabela)]
    assert main(args) == 0
    dados: dict[str, Any] = json.loads((saida / "texto-ficha.json").read_text(encoding="utf-8"))
    return dados


def _soma(fonte: dict[str, dict[str, int]], chave: str) -> int:
    return sum(c[chave] for c in fonte.values())


def test_cli_agregacao_total_e_familia_somam_os_pdfs(tmp_path: Path) -> None:
    tabela, pasta, nativo, contorno = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    _referencia(rodada, "002-bbbbbbbbbbbb", contorno)
    d = _rodar(rodada, pasta, tmp_path / "s", tabela)
    for fonte in ("base", "novo"):
        for chave in ("total", "acertos", "erros_afirmados"):
            por_pdf = sum(_soma(b["fontes"][fonte], chave) for b in d["por_pdf"].values())
            por_familia = sum(_soma(b[fonte], chave) for b in d["por_familia"].values())
            assert _soma(d["total"][fonte], chave) == por_pdf == por_familia
    assert _soma(d["total"]["novo"], "total") == 4


def test_cli_base_do_nativo_igual_ao_novo(tmp_path: Path) -> None:
    tabela, pasta, nativo, _ = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    d = _rodar(rodada, pasta, tmp_path / "s", tabela)
    f = d["por_pdf"]["001-aaaaaaaaaaaa"]["fontes"]
    assert f["base"] == f["novo"]
    assert _soma(f["base"], "acertos") == 2


def test_cli_pdf_sem_referencia_e_ignorado(tmp_path: Path) -> None:
    tabela, pasta, nativo, _ = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    d = _rodar(rodada, pasta, tmp_path / "s", tabela)
    assert list(d["por_pdf"]) == ["001-aaaaaaaaaaaa"]


def test_cli_sha_divergente_recusa_citando_o_id(tmp_path: Path) -> None:
    tabela, pasta, nativo, _ = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo, sha="0" * 64)
    args = ["--rodada", str(rodada), "--pdfs", str(pasta), "--saida", str(tmp_path / "s")]
    with pytest.raises(ValueError, match="001-aaaaaaaaaaaa"):
        main([*args, "--tabela", str(tabela)])


def test_cli_rodada_sem_referencias_gera_totais_zerados(tmp_path: Path) -> None:
    tabela, pasta, _, _ = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    (rodada / "pdfs").mkdir(parents=True)
    d = _rodar(rodada, pasta, tmp_path / "s", tabela)
    assert d["por_pdf"] == {} and d["por_familia"] == {}
    assert _soma(d["total"]["novo"], "total") == 0
    assert (tmp_path / "s" / "texto-ficha.md").is_file()


def test_cli_referencia_regional_e_medida(tmp_path: Path) -> None:
    tabela, pasta, nativo, _ = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    escopo = {"tipo": "regional", "regioes": [{"pagina": 1, "bbox": [0.0, 0.0, 0.6, 0.6]}]}
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo, escopo=escopo)
    d = _rodar(rodada, pasta, tmp_path / "s", tabela)
    assert _soma(d["total"]["novo"], "total") == 2


def test_cli_sem_tabela_usa_a_do_pacote(tmp_path: Path) -> None:
    _, pasta, nativo, _ = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    d = _rodar(rodada, pasta, tmp_path / "s", None)
    assert len(d["tabela_sha256"]) == 64


def test_cli_tabela_invalida_falha_antes_de_gravar(tmp_path: Path) -> None:
    _, pasta, nativo, _ = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    ruim = tmp_path / "ruim.json"
    ruim.write_text("{nao e json", encoding="utf-8")
    saida = tmp_path / "s"
    args = ["--rodada", str(rodada), "--pdfs", str(pasta), "--saida", str(saida)]
    with pytest.raises(ValueError, match="Tabela de glifos"):
        main([*args, "--tabela", str(ruim)])
    assert not (saida / "texto-ficha.json").exists()


def test_cli_tabela_inexistente_falha(tmp_path: Path) -> None:
    _, pasta, nativo, _ = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    args = ["--rodada", str(rodada), "--pdfs", str(pasta), "--saida", str(tmp_path / "s")]
    with pytest.raises((ValueError, OSError)):
        main([*args, "--tabela", str(tmp_path / "nao-existe.json")])


def test_cli_saida_sem_caminho_absoluto_nem_nome_de_pdf(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tabela, pasta, nativo, contorno = _pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    _referencia(rodada, "002-bbbbbbbbbbbb", contorno)
    saida = tmp_path / "s"
    _rodar(rodada, pasta, saida, tabela)
    posix = tmp_path.as_posix()
    for conteudo in (
        (saida / "texto-ficha.json").read_text(encoding="utf-8"),
        (saida / "texto-ficha.md").read_text(encoding="utf-8"),
        capsys.readouterr().out,
    ):
        assert str(tmp_path) not in conteudo and posix not in conteudo
        assert "segredo" not in conteudo and ".pdf" not in conteudo
        assert tmp_path.name not in conteudo
