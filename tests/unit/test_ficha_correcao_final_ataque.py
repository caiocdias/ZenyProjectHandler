"""Ataques do testador à onda final das fichas: empate de C, recorte girado e saneamento."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import scripts.curation_ficha as curation_ficha
from tests.unit.test_ficha_correcao_final import _pixels, _preto, _vermelho
from tests.unit.test_ficha_leitura_dupla import (
    _consolidar,
    _contagem,
    _leitura_c,
    _postes,
    _simbolo,
    _vao,
    ficha,
)

Registro = dict[str, Any]


def _vao_p2_p3(referencia: Registro) -> Registro:
    return next(v for v in referencia["vaos"] if (v["de"], v["para"]) == ("P2", "P3"))


def _c_p2_p3(a: Registro, comprimento: float | None, cabo: str | None = "BT 70") -> Registro:
    vao = _vao("P2", "P3", comprimento, cabo)
    return _leitura_c(a["postes"][1], a["postes"][2], vaos=[vao])


# --- M1 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("ordem", ["ab", "ba"])
def test_comprimento_c_exatamente_na_tolerancia_dos_dois_lados_fica_pendente(ordem: str) -> None:
    a, b = ficha(), ficha()
    b["vaos"][1]["comprimento_m"] = 35.2  # A=35,0 e B=35,2 divergem
    x, y = (a, b) if ordem == "ab" else (b, a)
    referencia = _consolidar(x, y, _c_p2_p3(a, 35.1))  # |C-A| = |C-B| = 0,1 (limite inclusivo)
    vao = _vao_p2_p3(referencia)
    assert (vao["comprimento_m"], vao["pendentes"]) == (None, ["comprimento_m"])
    assert _contagem(referencia)["resolvidas_por_c"] == 0
    assert _contagem(referencia)["pendentes"] == 1


def test_comprimento_c_logo_fora_da_tolerancia_de_um_lado_resolve_para_o_outro() -> None:
    a, b = ficha(), ficha()
    b["vaos"][1]["comprimento_m"] = 35.2
    referencia = _consolidar(a, b, _c_p2_p3(a, 35.11))  # a 0,11 de A e 0,09 de B: só B
    vao = _vao_p2_p3(referencia)
    assert (vao["comprimento_m"], vao["pendentes"]) == (35.2, [])
    assert _contagem(referencia)["resolvidas_por_c"] == 1
    assert _contagem(referencia)["pendentes"] == 0


def test_c_ambiguo_no_comprimento_nao_contamina_o_cabo_do_mesmo_vao() -> None:
    a, b = ficha(), ficha()
    b["vaos"][1]["comprimento_m"] = 35.15
    b["vaos"][1]["cabo"] = "BT 95"  # cabo diverge; C confirma só A
    referencia = _consolidar(a, b, _c_p2_p3(a, 35.08, "BT 70"))
    vao = _vao_p2_p3(referencia)
    assert (vao["comprimento_m"], vao["cabo"]) == (None, "BT 70")
    assert vao["pendentes"] == ["comprimento_m"]
    assert _contagem(referencia)["resolvidas_por_c"] == 1
    assert _contagem(referencia)["pendentes"] == 1


def test_comprimento_pendente_em_um_leitor_e_c_perto_do_outro_resolve_por_c() -> None:
    a, b = ficha(), ficha()
    a["vaos"][1]["comprimento_m"] = None
    a["vaos"][1]["pendentes"] = ["comprimento_m"]
    referencia = _consolidar(a, b, _c_p2_p3(b, 35.08))  # só B é candidato
    vao = _vao_p2_p3(referencia)
    assert (vao["comprimento_m"], vao["pendentes"]) == (35.0, [])
    assert _contagem(referencia)["resolvidas_por_c"] == 1


def test_c_pendente_no_comprimento_nao_resolve_nem_conta_como_ambiguo() -> None:
    a, b = ficha(), ficha()
    b["vaos"][1]["comprimento_m"] = 35.15
    c = _c_p2_p3(a, None)
    c["vaos"][0]["pendentes"] = ["comprimento_m"]
    referencia = _consolidar(a, b, c)
    assert _vao_p2_p3(referencia)["comprimento_m"] is None
    assert _contagem(referencia)["resolvidas_por_c"] == 0
    assert _contagem(referencia)["pendentes"] == 1


def test_empate_de_c_fora_da_regiao_conta_nao_coberta_e_dentro_nao() -> None:
    a, b = ficha(), ficha()
    b["vaos"][1]["comprimento_m"] = 35.15
    dentro = _consolidar(a, b, _c_p2_p3(a, 35.08))
    assert _contagem(dentro)["nao_cobertas_por_c"] == 0
    assert _contagem(dentro)["pendentes"] == 1
    ilegivel = [{"pagina": 1, "bbox": [0.69, 0.29, 0.73, 0.33]}]  # em volta do P3
    fora = _consolidar(
        a,
        b,
        _leitura_c(
            a["postes"][1],
            a["postes"][2],
            vaos=[_vao("P2", "P3", 35.08, "BT 70")],
            ilegiveis=ilegivel,
        ),
    )
    assert _contagem(fora)["nao_cobertas_por_c"] == 1
    assert _contagem(fora)["pendentes"] == 1
    assert _contagem(fora)["resolvidas_por_c"] == 0


@pytest.mark.parametrize("ordem", ["ab", "ba"])
def test_coordenada_norte_ambigua_fica_pendente_mesmo_com_leste_divergente(ordem: str) -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["coordenada"]["norte"] = 7800000.015
    poste_c = copy.deepcopy(a["postes"][0])
    poste_c["coordenada"]["norte"] = 7800000.0075
    x, y = (a, b) if ordem == "ab" else (b, a)
    referencia = _consolidar(x, y, _leitura_c(poste_c))
    p1 = _postes(referencia)["P1"]
    assert (p1["coordenada"], p1["pendentes"]) == (None, ["coordenada"])
    assert _contagem(referencia)["pendentes"] == 1
    assert _contagem(referencia)["resolvidas_por_c"] == 0


def test_coordenada_c_no_limite_exato_dos_dois_lados_fica_pendente() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["coordenada"]["leste"] = 700000.02
    poste_c = copy.deepcopy(a["postes"][0])
    poste_c["coordenada"]["leste"] = 700000.01  # 0,01 de cada lado (limite inclusivo)
    referencia = _consolidar(a, b, _leitura_c(poste_c))
    p1 = _postes(referencia)["P1"]
    assert (p1["coordenada"], p1["pendentes"]) == (None, ["coordenada"])


def test_c_com_um_leitor_confirmado_na_coordenada_resolve() -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["coordenada"]["leste"] = 700000.02
    poste_c = copy.deepcopy(a["postes"][0])
    poste_c["coordenada"]["leste"] = 700000.0  # só A
    referencia = _consolidar(a, b, _leitura_c(poste_c))
    p1 = _postes(referencia)["P1"]
    assert p1["coordenada"]["leste"] == 700000.0 and p1["pendentes"] == []
    assert _contagem(referencia)["resolvidas_por_c"] == 1


@pytest.mark.parametrize("ordem", ["ab", "ba"])
def test_simbolos_ambiguos_nao_apagam_os_outros_campos_resolvidos_por_c(ordem: str) -> None:
    a, b = ficha(), ficha()
    b["postes"][0]["simbolos"] = [_simbolo("S1", [0.138, 0.30, 0.158, 0.32])]
    b["postes"][0]["poste"] = "DT 12/300"  # poste diverge; C confirma só A
    poste_c = copy.deepcopy(a["postes"][0])
    poste_c["simbolos"] = [_simbolo("S1", [0.134, 0.30, 0.154, 0.32])]
    x, y = (a, b) if ordem == "ab" else (b, a)
    referencia = _consolidar(x, y, _leitura_c(poste_c))
    p1 = _postes(referencia)["P1"]
    assert p1["pendentes"] == ["simbolos"]
    assert p1["poste"] == "DT 11/300"
    assert _contagem(referencia)["resolvidas_por_c"] == 1
    assert _contagem(referencia)["pendentes"] == 1


def test_consolidar_com_empate_de_c_nao_altera_as_entradas() -> None:
    a, b = ficha(), ficha()
    b["vaos"][1]["comprimento_m"] = 35.15
    c = _c_p2_p3(a, 35.08)
    antes = copy.deepcopy((a, b, c))
    _consolidar(a, b, c)
    assert (a, b, c) == antes


# --- M2 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("rotacao", [90, 180, 270])
def test_recorte_em_pdf_girado_gravado_e_reaberto_do_disco(tmp_path: Path, rotacao: int) -> None:
    arquivo = tmp_path / "girado.pdf"
    with pymupdf.open() as novo:  # type: ignore[no-untyped-call]
        pagina = novo.new_page(width=500, height=300)
        marca = pymupdf.Rect(60, 40, 100, 70)  # type: ignore[no-untyped-call]
        pagina.draw_rect(marca, color=(0, 0, 0), fill=(0, 0, 0))
        pagina.draw_rect(
            pymupdf.Rect(380, 200, 430, 250),  # type: ignore[no-untyped-call]
            color=(1, 0, 0),
            fill=(1, 0, 0),
        )
        pagina.set_rotation(rotacao)
        exibida = marca * pagina.rotation_matrix
        largura, altura = pagina.rect.width, pagina.rect.height
        novo.save(arquivo)
    with pymupdf.open(arquivo) as documento:  # type: ignore[no-untyped-call]
        bbox = [
            exibida.x0 / largura,
            exibida.y0 / altura,
            exibida.x1 / largura,
            exibida.y1 / altura,
        ]
        png = curation_ficha._recorte_do_poste(documento[0], bbox)
    w, h, cores = _pixels(png)
    assert _preto(cores[(h // 2) * w + w // 2])
    assert not any(_vermelho(cor) for cor in cores)


# --- M3 ---------------------------------------------------------------------------------------

sem = curation_ficha._sem_caminho_absoluto

TROCAS = {
    "windows_minusculo": ("c:\\users\\x\\a.pdf falhou", "<caminho> falhou"),
    "windows_barra_normal_meio": ("falha C:/Users/x/a.pdf falhou", "falha <caminho> falhou"),
    "windows_entre_parenteses": ("falha (C:\\Users\\x\\a.pdf)", "falha (<caminho>)"),
    "windows_ponto_final": ("falha C:\\Users\\x\\a.pdf.", "falha <caminho>."),
    "windows_virgula": ("falha C:\\Users\\x\\a.pdf, depois", "falha <caminho>, depois"),
    "windows_dois_pontos": ("falha C:\\Users\\x\\a.pdf: motivo", "falha <caminho>: motivo"),
    "windows_repr_dobrado": (
        "Permission denied: 'C:\\\\Users\\\\x\\\\a.pdf'",
        "Permission denied: '<caminho>'",
    ),
    "windows_apos_igual": ("chave=C:\\x\\y", "chave=<caminho>"),
    "posix_open": ("open('/etc/passwd')", "open('<caminho>')"),
    "posix_aspas_com_espaco": (
        "[Errno 2] No such file or directory: '/home/u/a b/c.pdf'",
        "[Errno 2] No such file or directory: '<caminho>'",
    ),
    "posix_lista": ("lista [/tmp/a, /tmp/b]", "lista [<caminho>, <caminho>]"),
    "posix_tupla": ("tupla ('/tmp/a', 'b')", "tupla ('<caminho>', 'b')"),
    "posix_dict": ("dict {'p': '/tmp/a'}", "dict {'p': '<caminho>'}"),
    "posix_opcao": ("use --opt /tmp/x", "use --opt <caminho>"),
    "posix_dev_null": ("x /dev/null y", "x <caminho> y"),
    "unc_com_barras_normais": ("rede //srv/share/y fim", "rede <caminho> fim"),
    "dois_caminhos_na_linha": ("de C:\\a\\b para /tmp/c", "de <caminho> para <caminho>"),
}

PRESERVADAS = [
    "razão 1/2 e 10/12/2026",
    "tente com e/ou sem, valor 5 m/s e km/h",
    "A/B/C e Sim/Não",
    "erro: /",
    "TypeError: a / b",
    "x//y",
    "encoding utf-8/ignore",
    "caminho relativo ~/x/y e ~\\x",
    "variável %APPDATA%\\x\\y e $HOME/x",
    "C:rel\\x sem barra depois da unidade",
    "'a\\b' e uma\\barra",
    "linha 1\\n2 com escape literal",
    "versão 3.11/3.13 e Python3/pip",
    "veja https://x.com/a/b e http://y.org/c",
]


@pytest.mark.parametrize("chave", sorted(TROCAS))
def test_sem_caminho_absoluto_troca_so_o_caminho(chave: str) -> None:
    mensagem, esperado = TROCAS[chave]
    assert sem(mensagem) == esperado


@pytest.mark.parametrize("mensagem", PRESERVADAS)
def test_sem_caminho_absoluto_preserva_texto_que_nao_e_caminho(mensagem: str) -> None:
    assert sem(mensagem) == mensagem


@pytest.mark.parametrize("chave", sorted(TROCAS))
def test_sem_caminho_absoluto_e_idempotente(chave: str) -> None:
    uma_vez = sem(TROCAS[chave][0])
    assert sem(uma_vez) == uma_vez


def test_sem_caminho_absoluto_nao_deixa_raiz_de_unidade_nem_usuario() -> None:
    saida = sem("a C:\\Users\\caio\\x.pdf b /home/caio/y.pdf c \\\\srv\\caio\\z")
    assert "caio" not in saida and "C:" not in saida and "srv" not in saida


def test_limitacao_conhecida_caminho_com_espaco_sem_aspas_fora_dos_diretorios_conhecidos() -> None:
    # LIMITAÇÃO DOCUMENTADA (não é defeito desta onda): sem aspas, o caminho para no primeiro
    # espaço. Só a raiz sai; o resto do caminho (relativo, sem raiz) permanece na mensagem.
    assert sem("dir C:\\Program Files\\Tesseract\\t.exe falhou") == (
        "dir <caminho> Files\\Tesseract\\t.exe falhou"
    )
    assert sem("dir /usr/share/tesseract ocr/t falhou") == "dir <caminho> ocr/t falhou"


def test_sanear_so_a_primeira_linha_e_sem_caminho_na_sequencia(tmp_path: Path) -> None:
    pdf = tmp_path / "corpus" / "alfa-secreto.pdf"
    texto = "falhou em /home/caio/x.pdf\nTraceback: C:\\Users\\caio\\y.py"
    assert curation_ficha._sanear(texto, pdf, "01-x") == "falhou em <caminho>"


def test_sanear_diretorio_conhecido_com_espaco_e_barra_normal_sai_inteiro(tmp_path: Path) -> None:
    pdf = tmp_path / "corpus" / "alfa-secreto.pdf"
    runtime = tmp_path / "meu runtime" / "ocr"
    mensagem = f"nao achou {runtime.as_posix()}/tesseract.exe agora"
    saida = curation_ficha._sanear(mensagem, pdf, "01-x", runtime.resolve())
    assert "meu runtime" not in saida and tmp_path.name not in saida
    assert saida.startswith("nao achou ") and saida.endswith(" agora")


def test_sanear_nome_do_pdf_vira_id_e_o_caminho_do_pdf_some(tmp_path: Path) -> None:
    pdf = tmp_path / "corpus" / "alfa-secreto.pdf"
    saida = curation_ficha._sanear(f"nao abriu {pdf} (alfa-secreto)", pdf, "01-x")
    assert "alfa-secreto" not in saida and str(tmp_path) not in saida
    assert saida == "nao abriu 01-x (01-x)"
