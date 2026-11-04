# mypy: disable-error-code="no-untyped-call"
"""Ataques ao CLI da rodada de glifos: cegueira, folhas reservadas, leituras, consolidação."""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts.curation_glifos import FORMATO_LEITURA, LEITORES, MARCAS, _parser, main
from scripts.curation_round import hash_arquivo
from tests.fixtures.glyphs.fonte_livre import (
    _ORDEM_DA_TABELA,
    LinhaTexto,
    pdf_texto_contorno,
)

from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import carregar_tabela_glifos
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import ler_texto_glifos
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import caminhos_da_pagina

Registro = dict[str, Any]

RAIZ = Path(__file__).resolve().parents[2]
TEXTO_A = "POSTE 4721"
TEXTO_B = "TESTE 1274"
SHA_INEXISTENTE = "ab" * 32


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    raiz = tmp_path_factory.mktemp("glifos-ataque")
    pdfs = raiz / "pdfs"
    pdfs.mkdir()
    pdf_texto_contorno(pdfs / "folha-secreta-a.pdf", [LinhaTexto(TEXTO_A, (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pdfs / "folha-secreta-b.pdf", [LinhaTexto(TEXTO_B, (20.0, 60.0), 6.0)])
    rodada = raiz / "rodada"
    assert main(["agrupar", "--pdfs", str(pdfs), "--rodada", str(rodada)]) == 0
    return pdfs, rodada


@pytest.fixture
def rodada(base: tuple[Path, Path], tmp_path: Path) -> Path:
    destino = tmp_path / "rodada"
    shutil.copytree(base[1], destino)
    return destino


def _json(arquivo: Path) -> Any:
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _ids(rodada: Path) -> list[str]:
    return [g["id"] for g in _json(rodada / "grupos.json")["grupos"]]


def _leitura(tmp_path: Path, leitor: str, rotulos: list[Registro], nome: str = "r.json") -> Path:
    arquivo = tmp_path / f"{leitor}-{nome}"
    arquivo.write_text(
        json.dumps({"formato": FORMATO_LEITURA, "leitor": leitor, "rotulos": rotulos}),
        encoding="utf-8",
    )
    return arquivo


def _validar(rodada: Path, leitor: str, arquivo: Path) -> int:
    return main(["validar", "--rodada", str(rodada), "--leitor", leitor, "--arquivo", str(arquivo)])


def _todos(rodada: Path, **rotulo: str) -> list[Registro]:
    return [{"grupo": g, **rotulo} for g in _ids(rodada)]


def _agrupar(pdfs: Path, rodada: Path, *extra: str) -> int:
    return main(["agrupar", "--pdfs", str(pdfs), "--rodada", str(rodada), *extra])


# --- cegueira -----------------------------------------------------------------------------


def _textos(valor: Any) -> list[str]:
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, dict):
        return [t for v in valor.values() for t in _textos(v)]
    if isinstance(valor, list):
        return [t for v in valor for t in _textos(v)]
    return []


def test_celulas_json_so_leva_numeros_e_identificadores(rodada: Path) -> None:
    celulas = _json(rodada / "celulas.json")
    permitidos = [t for t in _textos(celulas) if not re.fullmatch(r"c\d{4}", t)]
    assert permitidos == ["curadoria-glifos-celulas-v1"]
    chaves = set(celulas["celulas"][0])
    assert chaves == {"id", "membros", "folhas", "representante", "distante", "contexto"}


def test_nenhum_json_da_rodada_leva_sha_completo_nem_predicao(
    rodada: Path, base: tuple[Path, Path]
) -> None:
    for arquivo in rodada.rglob("*.json"):
        texto = arquivo.read_text(encoding="utf-8")
        assert not re.search(r"[0-9a-f]{64}", texto), arquivo.name
        for pdf in base[0].glob("*.pdf"):
            assert hash_arquivo(pdf) not in texto
        assert "predicao" not in texto.lower(), arquivo.name
        assert "POSTE" not in texto, arquivo.name
    grupos = _json(rodada / "grupos.json")["grupos"]
    assert all("caractere" not in g and "marca" not in g for g in grupos)


def test_rodada_nao_depende_do_nome_nem_do_diretorio_dos_pdfs(
    base: tuple[Path, Path], tmp_path: Path
) -> None:
    outro = tmp_path / "renomeados"
    outro.mkdir()
    shutil.copy(base[0] / "folha-secreta-a.pdf", outro / "zzz.pdf")
    shutil.copy(base[0] / "folha-secreta-b.pdf", outro / "aaa.pdf")
    destino = tmp_path / "r2"
    assert _agrupar(outro, destino) == 0
    for nome in ("grupos.json", "h1.json", "celulas.json"):
        assert _json(destino / nome) == _json(base[1] / nome), nome


def test_agrupar_e_deterministico(base: tuple[Path, Path], tmp_path: Path) -> None:
    destino = tmp_path / "de-novo"
    assert _agrupar(base[0], destino) == 0
    assert (destino / "grupos.json").read_bytes() == (base[1] / "grupos.json").read_bytes()


# --- --excluir-sha ------------------------------------------------------------------------


def test_excluir_sha_com_sha_inexistente_nao_exclui_nada(
    base: tuple[Path, Path], tmp_path: Path
) -> None:
    reservadas = tmp_path / "res.txt"
    reservadas.write_text(SHA_INEXISTENTE.upper() + "\r\n", encoding="utf-8")
    destino = tmp_path / "r"
    assert _agrupar(base[0], destino, "--excluir-sha", str(reservadas)) == 0
    assert _json(destino / "h1.json")["folhas_excluidas"] == 0
    assert _json(destino / "h1.json")["glifos_em_trecho"] == 18


def test_excluir_sha_aceita_maiusculas_e_crlf(base: tuple[Path, Path], tmp_path: Path) -> None:
    reservadas = tmp_path / "res.txt"
    sha = hash_arquivo(base[0] / "folha-secreta-b.pdf").upper()
    reservadas.write_bytes(f"{SHA_INEXISTENTE}\r\n{sha}\r\n".encode())
    destino = tmp_path / "r"
    assert _agrupar(base[0], destino, "--excluir-sha", str(reservadas)) == 0
    assert _json(destino / "h1.json")["folhas_excluidas"] == 1


def test_excluir_sha_com_todas_as_folhas_reservadas_falha(
    base: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    reservadas = tmp_path / "res.txt"
    reservadas.write_text(
        "\n".join(hash_arquivo(p) for p in base[0].glob("*.pdf")), encoding="utf-8"
    )
    assert _agrupar(base[0], tmp_path / "r", "--excluir-sha", str(reservadas)) == 1
    assert "reservadas" in capsys.readouterr().err
    assert not (tmp_path / "r" / "grupos.json").exists()


def test_excluir_sha_arquivo_inexistente_falha_sem_gravar(
    base: tuple[Path, Path], tmp_path: Path
) -> None:
    assert _agrupar(base[0], tmp_path / "r", "--excluir-sha", str(tmp_path / "nao.txt")) == 1
    assert not (tmp_path / "r" / "grupos.json").exists()


def test_excluir_sha_com_marca_de_ordem_de_bytes_ainda_exclui_a_folha(
    base: tuple[Path, Path], tmp_path: Path
) -> None:
    """Out-File -Encoding utf8 do Windows PowerShell 5.1 grava BOM; a folha reservada vazaria."""
    reservadas = tmp_path / "res.txt"
    sha = hash_arquivo(base[0] / "folha-secreta-a.pdf")
    reservadas.write_text(sha + "\n", encoding="utf-8-sig")
    destino = tmp_path / "r"
    codigo = _agrupar(base[0], destino, "--excluir-sha", str(reservadas))
    if codigo == 0:
        assert _json(destino / "h1.json")["folhas_excluidas"] == 1
    else:
        assert not (destino / "grupos.json").exists()


@pytest.mark.parametrize(
    "linha",
    [
        "abc123",  # prefixo curto
        "sha256:" + "ab" * 32,  # prefixo de algoritmo
        "zz" * 32,  # 64 caracteres, não hexadecimais
        "ab" * 33,  # comprido demais
    ],
    ids=["prefixo-curto", "prefixo-de-algoritmo", "nao-hexadecimal", "comprido-demais"],
)
def test_excluir_sha_com_linha_malformada_nao_e_ignorada_em_silencio(
    base: tuple[Path, Path], tmp_path: Path, linha: str
) -> None:
    """Linha que não é sha256 não reserva folha alguma: ignorá-la deixa a folha entrar."""
    reservadas = tmp_path / "res.txt"
    reservadas.write_text(linha + "\n", encoding="utf-8")
    destino = tmp_path / "r"
    assert _agrupar(base[0], destino, "--excluir-sha", str(reservadas)) == 1
    assert not (destino / "grupos.json").exists()


# --- agrupar: limiares, PDFs ruins, folhas ------------------------------------------------


@pytest.mark.parametrize("limiar", ["0", "-0.1", "nan"])
def test_agrupar_recusa_limiar_nao_positivo(
    base: tuple[Path, Path], tmp_path: Path, limiar: str
) -> None:
    assert _agrupar(base[0], tmp_path / "r", "--limiar", limiar) == 1
    assert not (tmp_path / "r").exists()


def test_agrupar_limiar_enorme_nao_funde_formas_de_subcaminhos_diferentes(
    base: tuple[Path, Path], tmp_path: Path
) -> None:
    destino = tmp_path / "r"
    assert _agrupar(base[0], destino, "--limiar", "100") == 0
    grupos = _json(destino / "grupos.json")["grupos"]
    assert len({g["subcaminhos"] for g in grupos}) == len(
        {g["subcaminhos"] for g in _json(base[1] / "grupos.json")["grupos"]}
    )
    assert all(len({g["subcaminhos"]}) == 1 for g in grupos)
    assert len(grupos) < len(_json(base[1] / "grupos.json")["grupos"])


def test_agrupar_pdf_corrompido_falha_com_erro_e_nao_com_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    (pdfs / "ruim.pdf").write_bytes(b"isto nao e um pdf")
    assert _agrupar(pdfs, tmp_path / "r") == 1
    assert "erro:" in capsys.readouterr().err


def test_agrupar_muitos_grupos_dividem_as_folhas_em_quarenta(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    pdf_texto_contorno(pdfs / "x.pdf", [LinhaTexto(_ORDEM_DA_TABELA, (10.0, 60.0), 5.0)])
    destino = tmp_path / "r"
    assert _agrupar(pdfs, destino) == 0
    total = len(_json(destino / "grupos.json")["grupos"])
    esperado = -(-total // 40)
    folhas = sorted(p.name for p in (destino / "contato").glob("*.png"))
    assert folhas == [f"folha-{n:03d}.png" for n in range(1, esperado + 1)]
    assert _json(destino / "h1.json")["folhas_de_contato"] == esperado


def test_agrupar_avisa_quando_o_quadro_incerto_passa_de_30_por_cento(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    pdf_texto_contorno(pdfs / "a.pdf", [LinhaTexto("POSTE", (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pdfs / "b.pdf", [LinhaTexto("-=", (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pdfs / "c.pdf", [LinhaTexto("-=", (30.0, 70.0), 5.0)])
    destino = tmp_path / "r"
    assert _agrupar(pdfs, destino) == 0
    h1 = _json(destino / "h1.json")
    assert h1["fracao_excluida_quadro_incerto"] > 0.30
    assert "mais de 30%" in capsys.readouterr().out


def test_agrupar_forma_vista_em_trecho_certo_e_incerto_nao_conta_como_so_incerta(
    tmp_path: Path,
) -> None:
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    pdf_texto_contorno(pdfs / "a.pdf", [LinhaTexto("POSTE", (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pdfs / "b.pdf", [LinhaTexto("-=", (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pdfs / "c.pdf", [LinhaTexto("-=", (20.0, 60.0), 5.0)])
    destino = tmp_path / "r"
    assert _agrupar(pdfs, destino) == 0
    familia = _json(destino / "h1.json")["por_familia"]["generico"]
    assert familia["formas_so_em_trechos_incertos"] == 2
    assert familia["glifos_excluidos_quadro_incerto"] == 4
    glifos = familia["glifos_em_trecho"]
    membros = sum(g["membros"] for g in _json(destino / "grupos.json")["grupos"])
    assert glifos == membros + familia["glifos_excluidos_quadro_incerto"]


# --- validar ------------------------------------------------------------------------------


def test_validar_aceita_caractere_em_nfd_e_grava_em_nfc(rodada: Path, tmp_path: Path) -> None:
    rotulos = _todos(rodada, marca="ignorar")
    rotulos[0] = {"grupo": rotulos[0]["grupo"], "caractere": unicodedata.normalize("NFD", "É")}
    assert len(rotulos[0]["caractere"]) == 2
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 0
    gravado = _json(rodada / "leituras" / "leitura-a.json")["rotulos"][0]["caractere"]
    assert gravado == "É"
    assert len(gravado) == 1


@pytest.mark.parametrize(
    "caractere",
    [
        "\u200b",  # espaço de largura zero
        "\u00a0",  # espaço sem quebra
        "\u3000",  # espaço ideográfico
        "\x00",
        "\x7f",
        "\u202e",  # inversão de direção
        "\ud800",  # substituto solto
        "AB",
        "ÁB",
        "👍👍",
        "\n",
        " A",
    ],
)
def test_validar_recusa_caracteres_nao_imprimiveis_ou_compostos(
    rodada: Path, tmp_path: Path, caractere: str
) -> None:
    rotulos = _todos(rodada, marca="ignorar")
    rotulos[0] = {"grupo": rotulos[0]["grupo"], "caractere": caractere}
    arquivo = tmp_path / "r.json"
    arquivo.write_text(
        json.dumps({"formato": FORMATO_LEITURA, "leitor": "a", "rotulos": rotulos}),
        encoding="utf-8",
    )
    assert _validar(rodada, "a", arquivo) == 1
    assert not (rodada / "leituras").exists()


@pytest.mark.parametrize("caractere", [7, None, ["A"], {"c": "A"}, True])
def test_validar_recusa_caractere_que_nao_e_texto(
    rodada: Path, tmp_path: Path, caractere: Any
) -> None:
    rotulos = _todos(rodada, marca="ignorar")
    rotulos[0] = {"grupo": rotulos[0]["grupo"], "caractere": caractere}
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 1


@pytest.mark.parametrize("marca", ["IGNORAR", "ignorar ", "", None, 3, ["ignorar"]])
def test_validar_recusa_marca_fora_do_conjunto_exato(
    rodada: Path, tmp_path: Path, marca: Any
) -> None:
    rotulos = _todos(rodada, marca="ignorar")
    rotulos[0] = {"grupo": rotulos[0]["grupo"], "marca": marca}
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 1


def test_validar_aceita_cada_marca_conhecida(rodada: Path, tmp_path: Path) -> None:
    ids = _ids(rodada)
    for leitor, marca in zip("ab", MARCAS[:2], strict=False):
        rotulos = [{"grupo": g, "marca": marca} for g in ids]
        assert _validar(rodada, leitor, _leitura(tmp_path, leitor, rotulos)) == 0
    assert set(MARCAS) == {"ignorar", "ilegivel", "composto", "fragmento", "misto"}


def test_validar_recusa_chave_extra_no_rotulo_e_nao_grava(rodada: Path, tmp_path: Path) -> None:
    rotulos = _todos(rodada, marca="ilegivel")
    rotulos[0]["predicao"] = "P"
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 1
    assert not (rodada / "leituras").exists()


@pytest.mark.parametrize(
    "conteudo",
    ["[]", "7", "null", '"texto"', "{}", '{"formato": "curadoria-glifos-v1"}'],
)
def test_validar_recusa_json_de_forma_errada(rodada: Path, tmp_path: Path, conteudo: str) -> None:
    arquivo = tmp_path / "r.json"
    arquivo.write_text(conteudo, encoding="utf-8")
    assert _validar(rodada, "a", arquivo) == 1


def test_validar_recusa_rotulos_que_nao_e_lista(rodada: Path, tmp_path: Path) -> None:
    arquivo = tmp_path / "r.json"
    arquivo.write_text(
        json.dumps({"formato": FORMATO_LEITURA, "leitor": "a", "rotulos": {"c0001": "P"}}),
        encoding="utf-8",
    )
    assert _validar(rodada, "a", arquivo) == 1


def test_validar_arquivo_inexistente_ou_binario_falha_com_erro(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _validar(rodada, "a", tmp_path / "nao-existe.json") == 1
    binario = tmp_path / "b.json"
    binario.write_bytes(b"\xff\xfe\x00\x80")
    assert _validar(rodada, "a", binario) == 1
    assert "erro:" in capsys.readouterr().err


def test_validar_json_profundamente_aninhado_falha_com_erro_e_nao_com_excecao(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo = tmp_path / "fundo.json"
    arquivo.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
    assert _validar(rodada, "a", arquivo) == 1
    assert "erro:" in capsys.readouterr().err


def test_validar_arquivo_gigante_de_rotulos_repetidos_e_recusado_sem_gravar(
    rodada: Path, tmp_path: Path
) -> None:
    grupo = _ids(rodada)[0]
    rotulos = [{"grupo": grupo, "marca": "ilegivel"}] * 200_000
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 1
    assert not (rodada / "leituras").exists()


def test_validar_leitura_atras_da_consolidacao_e_recusada(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for leitor in "ab":
        assert (
            _validar(rodada, leitor, _leitura(tmp_path, leitor, _todos(rodada, marca="ilegivel")))
            == 0
        )
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    antes = (rodada / "leituras" / "leitura-a.json").read_bytes()
    assert _validar(rodada, "c", _leitura(tmp_path, "c", [])) == 1
    assert "consolidada" in capsys.readouterr().err
    assert (rodada / "leituras" / "leitura-a.json").read_bytes() == antes
    assert not (rodada / "leituras" / "leitura-c.json").exists()


def test_validar_sem_agrupar_antes_falha(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo = _leitura(tmp_path, "a", [])
    assert _validar(tmp_path / "vazia", "a", arquivo) == 1
    assert "agrupar" in capsys.readouterr().err


def test_validar_leitor_fora_de_a_b_c_e_rejeitado_pelo_parser(rodada: Path, tmp_path: Path) -> None:
    arquivo = _leitura(tmp_path, "d", [])
    with pytest.raises(SystemExit) as saida:
        _validar(rodada, "d", arquivo)
    assert saida.value.code == 2


def test_validar_a_aceita_marca_e_caractere_misturados_e_preserva_a_ordem(
    rodada: Path, tmp_path: Path
) -> None:
    ids = _ids(rodada)
    rotulos: list[Registro] = [
        {"grupo": g, "caractere": "X"} if i % 2 else {"grupo": g, "marca": "misto"}
        for i, g in enumerate(ids)
    ]
    rotulos.reverse()
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 0
    copia = _json(rodada / "leituras" / "leitura-a.json")
    assert [r["grupo"] for r in copia["rotulos"]] == [r["grupo"] for r in rotulos]
    assert all(set(r) in ({"grupo", "caractere"}, {"grupo", "marca"}) for r in copia["rotulos"])


# --- consolidar ---------------------------------------------------------------------------


def _ab(rodada: Path, tmp_path: Path, divergente: dict[str, tuple[Registro, Registro]]) -> None:
    for leitor, indice in (("a", 0), ("b", 1)):
        rotulos = [
            {"grupo": g, **(divergente[g][indice] if g in divergente else {"marca": "ilegivel"})}
            for g in _ids(rodada)
        ]
        assert _validar(rodada, leitor, _leitura(tmp_path, leitor, rotulos)) == 0


def test_consolidar_a_diferente_de_b_em_caractere_c_escolhe_o_de_b(
    rodada: Path, tmp_path: Path
) -> None:
    grupo = _ids(rodada)[0]
    _ab(rodada, tmp_path, {grupo: ({"caractere": "P"}, {"caractere": "R"})})
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    assert _validar(rodada, "c", _leitura(tmp_path, "c", [{"grupo": grupo, "caractere": "R"}])) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    aceito = {a["grupo"]: a for a in _json(rodada / "consolidacao.json")["aceitos"]}
    assert aceito[grupo] == {"grupo": grupo, "caractere": "R"}


def test_consolidar_distingue_caractere_de_marca_com_mesmo_texto(
    rodada: Path, tmp_path: Path
) -> None:
    """O caractere literal 'misto' nunca é igual à marca misto; aqui, 'X' contra a marca."""
    grupo = _ids(rodada)[0]
    _ab(rodada, tmp_path, {grupo: ({"caractere": "X"}, {"marca": "misto"})})
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    assert _json(rodada / "divergencias.json")["grupos"] == [grupo]


def test_consolidar_divergencia_repetida_sem_c_mantem_codigo_3_e_divergencias(
    rodada: Path, tmp_path: Path
) -> None:
    ids = _ids(rodada)
    _ab(rodada, tmp_path, {ids[0]: ({"caractere": "P"}, {"caractere": "R"})})
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    primeira = (rodada / "divergencias.json").read_bytes()
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    assert (rodada / "divergencias.json").read_bytes() == primeira
    assert not (rodada / "consolidacao.json").exists()


def test_consolidar_varias_divergencias_exigem_c_em_todas(rodada: Path, tmp_path: Path) -> None:
    ids = _ids(rodada)
    _ab(
        rodada,
        tmp_path,
        {
            ids[0]: ({"caractere": "P"}, {"caractere": "R"}),
            ids[1]: ({"marca": "composto"}, {"marca": "fragmento"}),
        },
    )
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    assert _json(rodada / "divergencias.json")["grupos"] == [ids[0], ids[1]]
    so_um = [{"grupo": ids[0], "caractere": "P"}]
    assert _validar(rodada, "c", _leitura(tmp_path, "c", so_um)) == 1
    completo = [
        {"grupo": ids[0], "caractere": "P"},
        {"grupo": ids[1], "marca": "composto"},
    ]
    assert _validar(rodada, "c", _leitura(tmp_path, "c", completo)) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    resultado = _json(rodada / "consolidacao.json")
    assert resultado["pendentes"] == []
    assert resultado["concordancia_ab"]["concordantes"] == len(ids) - 2


def test_consolidar_leitura_a_corrompida_falha_com_erro(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ab(rodada, tmp_path, {})
    (rodada / "leituras" / "leitura-a.json").write_text("{}", encoding="utf-8")
    assert main(["consolidar", "--rodada", str(rodada)]) == 1
    assert "erro:" in capsys.readouterr().err


def test_consolidar_leitura_a_com_grupo_faltando_falha_com_erro(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ab(rodada, tmp_path, {})
    arquivo = rodada / "leituras" / "leitura-a.json"
    dados = _json(arquivo)
    dados["rotulos"] = dados["rotulos"][1:]
    arquivo.write_text(json.dumps(dados), encoding="utf-8")
    assert main(["consolidar", "--rodada", str(rodada)]) == 1
    assert "erro:" in capsys.readouterr().err


def test_consolidar_muitas_divergencias_dividem_as_folhas_de_divergencia(
    tmp_path: Path,
) -> None:
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    pdf_texto_contorno(pdfs / "x.pdf", [LinhaTexto(_ORDEM_DA_TABELA, (10.0, 60.0), 5.0)])
    rodada = tmp_path / "r"
    assert _agrupar(pdfs, rodada) == 0
    ids = _ids(rodada)
    assert len(ids) > 40
    _ab(rodada, tmp_path, {g: ({"caractere": "P"}, {"caractere": "R"}) for g in ids})
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    folhas = sorted(p.name for p in (rodada / "contato-divergencias").glob("*.png"))
    assert folhas == [f"folha-{n:03d}.png" for n in range(1, -(-len(ids) // 40) + 1)]


# --- publicar -----------------------------------------------------------------------------


def _consolidar_com(rodada: Path, tmp_path: Path, rotulos: list[Registro]) -> None:
    for leitor in "ab":
        assert _validar(rodada, leitor, _leitura(tmp_path, leitor, rotulos)) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 0


@pytest.mark.parametrize("marca", ["ilegivel", "composto", "fragmento", "misto"])
def test_publicar_sem_nenhum_grupo_publicavel_falha_e_nao_grava(
    rodada: Path, tmp_path: Path, marca: str
) -> None:
    _consolidar_com(rodada, tmp_path, _todos(rodada, marca=marca))
    saida = tmp_path / "t.json"
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida)]) == 1
    assert not saida.exists()


def test_publicar_deixa_composto_misto_e_pendente_fora(rodada: Path, tmp_path: Path) -> None:
    ids = _ids(rodada)
    divergencias = {ids[3]: ({"caractere": "P"}, {"caractere": "R"})}
    marcas = {ids[0]: "composto", ids[1]: "misto"}
    for leitor, indice in (("a", 0), ("b", 1)):
        rotulos: list[Registro] = []
        for g in ids:
            if g in divergencias:
                rotulos.append({"grupo": g, **divergencias[g][indice]})
            elif g in marcas:
                rotulos.append({"grupo": g, "marca": marcas[g]})
            else:
                rotulos.append({"grupo": g, "caractere": "X"})
        assert _validar(rodada, leitor, _leitura(tmp_path, leitor, rotulos)) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    c = _leitura(tmp_path, "c", [{"grupo": ids[3], "caractere": "Z"}])
    assert _validar(rodada, "c", c) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    assert _json(rodada / "consolidacao.json")["pendentes"] == [ids[3]]
    saida = tmp_path / "t.json"
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida)]) == 0
    tabela = carregar_tabela_glifos(saida)
    assert len(tabela.glifos) == len(ids) - 3
    assert {g.caractere for g in tabela.glifos} == {"X"}


def test_publicar_ignorar_divide_o_texto_lido_no_pdf(
    rodada: Path, base: tuple[Path, Path], tmp_path: Path
) -> None:
    """Ida e volta com 'ignorar': a forma sai do texto e o resto continua legível."""
    grupos = _json(rodada / "grupos.json")["grupos"]
    ignorado = grupos[0]["id"]
    rotulos: list[Registro] = [
        {"grupo": g["id"], "marca": "ignorar"}
        if g["id"] == ignorado
        else {"grupo": g["id"], "caractere": "X"}
        for g in grupos
    ]
    _consolidar_com(rodada, tmp_path, rotulos)
    saida = tmp_path / "t.json"
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida)]) == 0
    tabela = carregar_tabela_glifos(saida)
    assert [g.caractere for g in tabela.glifos].count(None) == 1
    with pymupdf.open(base[0] / "folha-secreta-a.pdf") as documento:
        caminhos = caminhos_da_pagina(documento[0])
    leitura = ler_texto_glifos(caminhos, tabela)
    texto = "".join(t.texto for t in leitura.textos)
    assert "X" in texto
    assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


@pytest.mark.parametrize(
    "opcao",
    [["--tolerancia", "-0.1"], ["--tolerancia", "nan"], ["--margem", "-1"], ["--quebra", "0"]],
)
def test_publicar_com_parametros_invalidos_falha_sem_deixar_arquivo(
    rodada: Path, tmp_path: Path, opcao: list[str]
) -> None:
    _consolidar_com(rodada, tmp_path, _todos(rodada, caractere="X"))
    saida = tmp_path / "t.json"
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida), *opcao]) == 1
    assert not saida.exists()


def test_publicar_ids_seguem_a_ordem_dos_grupos_e_a_tabela_nao_leva_nome_de_pdf(
    rodada: Path, tmp_path: Path
) -> None:
    _consolidar_com(rodada, tmp_path, _todos(rodada, caractere="X"))
    saida = tmp_path / "t.json"
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida)]) == 0
    texto = saida.read_text(encoding="utf-8")
    assert ".pdf" not in texto
    assert str(tmp_path) not in texto
    assert "folha-secreta" not in texto
    ids = [g["id"] for g in _json(saida)["glifos"]]
    assert ids == [f"g{n:04d}" for n in range(1, len(_ids(rodada)) + 1)]


# --- documentação e CLI -------------------------------------------------------------------

_COMANDO = re.compile(r"-m scripts\.curation_glifos (.+)")
_DOCS = (
    RAIZ / "docs" / "fluxo-curadoria-incremental-simbologia.md",
    RAIZ / ".claude" / "skills" / "curadoria-simbologia" / "SKILL.md",
    RAIZ / ".claude" / "agents" / "curadoria-leitor-visual.md",
)


def _comandos_documentados(arquivo: Path) -> list[list[str]]:
    comandos = []
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        achado = _COMANDO.search(linha)
        if achado:
            comandos.append(achado.group(1).split())
    return comandos


@pytest.mark.parametrize("arquivo", _DOCS, ids=lambda p: p.name)
def test_comandos_documentados_sao_aceitos_pelo_parser_do_cli(arquivo: Path) -> None:
    comandos = _comandos_documentados(arquivo)
    assert comandos, arquivo.name
    substituicoes = {"LEITOR": "a"}
    for argv in comandos:
        argumentos = _parser().parse_args([substituicoes.get(a, a) for a in argv])
        assert argumentos.comando in {"agrupar", "validar", "consolidar", "publicar"}


def test_contrato_cita_os_cinco_subcomandos_marcas_e_limites_do_cli() -> None:
    contrato = _DOCS[0].read_text(encoding="utf-8")
    secao = contrato.split("## Rodada de glifos", 1)[1]
    for subcomando in ("agrupar", "validar", "consolidar", "publicar"):
        assert f"curation_glifos {subcomando}" in secao
    for marca in MARCAS:
        assert marca in secao or marca in _DOCS[2].read_text(encoding="utf-8")
    for limite in ("600", "50%", "30%", "código 3", "--excluir-sha", "sha256[:12]"):
        assert limite in secao, limite


def test_agente_no_modo_glifo_cita_formato_marcas_e_leitores_do_cli() -> None:
    agente = _DOCS[2].read_text(encoding="utf-8")
    modo = agente.split("## Modo glifo", 1)[1]
    assert FORMATO_LEITURA in modo
    for marca in MARCAS:
        assert f"`{marca}`" in modo, marca
    for leitor in LEITORES:
        assert f"`{leitor}`" in modo
    for proibido in ("grupos.json", "consolidacao.json", "divergencias.json", "celulas.json"):
        assert proibido in modo.split("### Proibido no modo glifo", 1)[1].split("###", 1)[0]
    permitido = modo.split("### Permitido no modo glifo", 1)[1].split("###", 1)[0]
    assert "grupos.json" not in permitido
    assert "consolidar" not in permitido
    assert "publicar" not in permitido


def test_settings_permite_o_cli_de_glifos() -> None:
    config = json.loads((RAIZ / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert (
        "Bash(.venv/Scripts/python.exe -m scripts.curation_glifos *)"
        in config["permissions"]["allow"]
    )
