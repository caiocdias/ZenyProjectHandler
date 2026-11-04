# mypy: disable-error-code="no-untyped-call"
"""CLI da rodada de glifos: agrupamento, leitura dupla cega, consolidação e tabela publicada."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts.curation_glifos import assinatura_de_json, main
from scripts.curation_round import hash_arquivo
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    carregar_tabela_glifos,
    resolver_glifo,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import ler_texto_glifos
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import caminhos_da_pagina

Registro = dict[str, Any]

TEXTO_A = "POSTE 4721"
TEXTO_B = "TESTE 1274"
LETRAS = set((TEXTO_A + TEXTO_B).replace(" ", ""))


@pytest.fixture(scope="module")
def rodada_base(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, Path]:
    raiz = tmp_path_factory.mktemp("glifos")
    pdfs = raiz / "pdfs"
    pdfs.mkdir()
    pdf_texto_contorno(pdfs / "folha-secreta-a.pdf", [LinhaTexto(TEXTO_A, (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pdfs / "folha-secreta-b.pdf", [LinhaTexto(TEXTO_B, (20.0, 60.0), 6.0)])
    rodada = raiz / "rodada"
    assert main(["agrupar", "--pdfs", str(pdfs), "--rodada", str(rodada)]) == 0
    return raiz, pdfs, rodada


@pytest.fixture
def rodada(rodada_base: tuple[Path, Path, Path], tmp_path: Path) -> Path:
    destino = tmp_path / "rodada"
    shutil.copytree(rodada_base[2], destino)
    return destino


def _json(arquivo: Path) -> Any:
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _grupos(rodada: Path) -> list[Registro]:
    grupos = _json(rodada / "grupos.json")["grupos"]
    assert isinstance(grupos, list)
    return grupos


def _caractere_do_grupo(grupo: Registro, tabela: Any) -> str:
    resolucao = resolver_glifo(tabela, assinatura_de_json(grupo["assinatura"]))
    assert resolucao.caractere is not None, grupo["id"]
    return str(resolucao.caractere)


def _rotulos_corretos(rodada: Path, tmp_path: Path) -> dict[str, str]:
    tabela = tabela_do_alfabeto(tmp_path)
    return {g["id"]: _caractere_do_grupo(g, tabela) for g in _grupos(rodada)}


def _leitura(
    tmp_path: Path, leitor: str, rotulos: list[Registro], nome: str = "rascunho.json"
) -> Path:
    arquivo = tmp_path / f"{leitor}-{nome}"
    arquivo.write_text(
        json.dumps({"formato": "curadoria-glifos-v1", "leitor": leitor, "rotulos": rotulos}),
        encoding="utf-8",
    )
    return arquivo


def _validar(rodada: Path, leitor: str, arquivo: Path) -> int:
    return main(["validar", "--rodada", str(rodada), "--leitor", leitor, "--arquivo", str(arquivo)])


def _rotulos_de(caracteres: dict[str, str]) -> list[Registro]:
    return [{"grupo": g, "caractere": c} for g, c in caracteres.items()]


def _validar_a_e_b(
    rodada: Path, tmp_path: Path, alterar_b: dict[str, Registro] | None = None
) -> dict[str, str]:
    certos = _rotulos_corretos(rodada, tmp_path)
    rotulos_b = _rotulos_de(certos)
    for rotulo in rotulos_b:
        rotulo.update((alterar_b or {}).get(rotulo["grupo"], {}))
        if "marca" in rotulo:
            rotulo.pop("caractere", None)
    assert _validar(rodada, "a", _leitura(tmp_path, "a", _rotulos_de(certos))) == 0
    assert _validar(rodada, "b", _leitura(tmp_path, "b", rotulos_b)) == 0
    return certos


# --- agrupar ------------------------------------------------------------------------------


def test_agrupar_junta_a_mesma_letra_e_separa_letras_diferentes(
    rodada: Path, tmp_path: Path
) -> None:
    grupos = _grupos(rodada)
    certos = _rotulos_corretos(rodada, tmp_path)
    assert sorted(certos.values()) == sorted(LETRAS)
    assert [g["id"] for g in grupos] == [f"c{i:04d}" for i in range(1, len(grupos) + 1)]
    por_letra = {certos[g["id"]]: g for g in grupos}
    assert por_letra["T"]["membros"] == 3  # POSTE, TESTE (2)
    assert por_letra["E"]["membros"] == 3
    assert por_letra["P"]["membros"] == 1
    assert por_letra["P"]["folhas"] == 1
    assert por_letra["T"]["folhas"] == 2
    assert por_letra["T"]["familias"] == {"generico": 3}
    assert por_letra["T"]["distancia_maxima_interna"] <= 0.04
    assert [g["membros"] for g in grupos] == sorted((g["membros"] for g in grupos), reverse=True)


def test_agrupar_grava_h1_com_contagens_por_familia(rodada: Path) -> None:
    h1 = _json(rodada / "h1.json")
    assert h1["trechos"] == 2
    assert h1["glifos_em_trecho"] == 18
    assert h1["candidatos"] == 18
    assert h1["distribuicao_subcaminhos"]["1"] >= 1
    familia = h1["por_familia"]["generico"]
    assert familia["glifos_em_trecho"] == 18
    assert familia["glifos_excluidos_quadro_incerto"] == 0
    assert familia["fracao_excluida_quadro_incerto"] == 0.0


def test_agrupar_exclui_a_folha_reservada_por_sha(
    rodada_base: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _, pdfs, _ = rodada_base
    reservada = tmp_path / "reservadas.txt"
    reservada.write_text(hash_arquivo(pdfs / "folha-secreta-b.pdf") + "\n\n", encoding="utf-8")
    saida = tmp_path / "rodada-sem-b"
    argv = ["agrupar", "--pdfs", str(pdfs), "--rodada", str(saida), "--excluir-sha", str(reservada)]
    assert main(argv) == 0
    assert _json(saida / "h1.json")["glifos_em_trecho"] == 9
    assert max(g["folhas"] for g in _grupos(saida)) == 1


def test_agrupar_nao_grava_nome_de_pdf_nem_caminho_absoluto(
    rodada: Path, rodada_base: tuple[Path, Path, Path]
) -> None:
    raiz, pdfs, _ = rodada_base
    for arquivo in rodada.rglob("*.json"):
        texto = arquivo.read_text(encoding="utf-8")
        assert "folha-secreta" not in texto, arquivo.name
        assert ".pdf" not in texto, arquivo.name
        assert str(raiz) not in texto
        assert str(raiz).replace("\\", "/") not in texto
        assert str(raiz).replace("\\", "\\\\") not in texto
    folhas = _json(rodada / "h1.json")["folhas"]
    assert sorted(folhas) == sorted(hash_arquivo(p)[:12] for p in pdfs.glob("*.pdf"))


def test_agrupar_grava_folhas_de_contato_png(rodada: Path) -> None:
    folha = rodada / "contato" / "folha-001.png"
    assert folha.is_file()
    with pymupdf.open(folha) as imagem:
        assert imagem.page_count == 1
        assert imagem[0].rect.width > 400


def test_agrupar_recusa_sobrescrever_rodada_existente(
    rodada: Path, rodada_base: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["agrupar", "--pdfs", str(rodada_base[1]), "--rodada", str(rodada)]
    assert main(argv) == 1
    assert "já existe" in capsys.readouterr().err


def test_agrupar_sem_pdf_falha(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    assert main(["agrupar", "--pdfs", str(vazio), "--rodada", str(tmp_path / "r")]) == 1
    assert "nenhum PDF" in capsys.readouterr().err


def test_agrupar_quadro_incerto_fica_fora_dos_grupos_e_conta_no_h1(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    pdf_texto_contorno(pdfs / "a.pdf", [LinhaTexto(TEXTO_A, (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pdfs / "b.pdf", [LinhaTexto("-=", (20.0, 60.0), 5.0)])
    rodada = tmp_path / "r"
    assert main(["agrupar", "--pdfs", str(pdfs), "--rodada", str(rodada)]) == 0
    familia = _json(rodada / "h1.json")["por_familia"]["generico"]
    assert familia["glifos_excluidos_quadro_incerto"] == 2
    assert familia["fracao_excluida_quadro_incerto"] == pytest.approx(2 / 11, abs=1e-4)
    assert familia["formas_so_em_trechos_incertos"] == 2
    assert sum(g["membros"] for g in _grupos(rodada)) == 9


# --- validar ------------------------------------------------------------------------------


def test_validar_aceita_leitura_completa_e_grava_copia(rodada: Path, tmp_path: Path) -> None:
    certos = _rotulos_corretos(rodada, tmp_path)
    arquivo = _leitura(tmp_path, "a", _rotulos_de(certos))
    assert _validar(rodada, "a", arquivo) == 0
    assert _json(rodada / "leituras" / "leitura-a.json") == _json(arquivo)


def test_validar_recusa_sobrescrever_a_leitura(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo = _leitura(tmp_path, "a", _rotulos_de(_rotulos_corretos(rodada, tmp_path)))
    assert _validar(rodada, "a", arquivo) == 0
    assert _validar(rodada, "a", arquivo) == 1
    assert "já existe" in capsys.readouterr().err


def test_validar_normaliza_o_caractere_em_nfc(rodada: Path, tmp_path: Path) -> None:
    certos = _rotulos_corretos(rodada, tmp_path)
    grupo = next(g for g, c in certos.items() if c == "E")
    rotulos = _rotulos_de(certos)
    for rotulo in rotulos:
        if rotulo["grupo"] == grupo:
            rotulo["caractere"] = "É"
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 0
    copia = _json(rodada / "leituras" / "leitura-a.json")
    assert {r["grupo"]: r.get("caractere") for r in copia["rotulos"]}[grupo] == "É"


@pytest.mark.parametrize(
    ("rotulo", "trecho"),
    [
        ({"caractere": "AB"}, "caractere"),
        ({"caractere": " "}, "caractere"),
        ({"caractere": ""}, "caractere"),
        ({"caractere": "\t"}, "caractere"),
        ({"marca": "talvez"}, "marca"),
        ({"marca": "ignorar", "caractere": "A"}, "exatamente um"),
        ({}, "exatamente um"),
    ],
)
def test_validar_recusa_rotulo_malformado(
    rodada: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    rotulo: Registro,
    trecho: str,
) -> None:
    rotulos = _rotulos_de(_rotulos_corretos(rodada, tmp_path))
    rotulos[0] = {"grupo": rotulos[0]["grupo"], **rotulo}
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 1
    err = capsys.readouterr().err
    assert "erro:" in err
    assert trecho in err
    assert not (rodada / "leituras" / "leitura-a.json").exists()


def test_validar_recusa_grupo_faltando_repetido_e_desconhecido(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rotulos = _rotulos_de(_rotulos_corretos(rodada, tmp_path))
    faltando = rotulos[1:]
    assert _validar(rodada, "a", _leitura(tmp_path, "a", faltando, "falta.json")) == 1
    assert f"faltando: {rotulos[0]['grupo']}" in capsys.readouterr().err
    repetido = [*rotulos, rotulos[0]]
    assert _validar(rodada, "a", _leitura(tmp_path, "a", repetido, "rep.json")) == 1
    assert "repetido" in capsys.readouterr().err
    desconhecido = [*rotulos, {"grupo": "c9999", "marca": "ignorar"}]
    assert _validar(rodada, "a", _leitura(tmp_path, "a", desconhecido, "desc.json")) == 1
    assert "desconhecido" in capsys.readouterr().err


def test_validar_recusa_formato_e_leitor_trocados(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo = _leitura(tmp_path, "b", _rotulos_de(_rotulos_corretos(rodada, tmp_path)))
    assert _validar(rodada, "a", arquivo) == 1
    assert "leitor" in capsys.readouterr().err
    arquivo.write_text(json.dumps({"formato": "outro", "leitor": "a", "rotulos": []}))
    assert _validar(rodada, "a", arquivo) == 1
    assert "formato" in capsys.readouterr().err
    arquivo.write_text("{ nao e json")
    assert _validar(rodada, "a", arquivo) == 1
    assert "JSON" in capsys.readouterr().err


def test_validar_leitor_c_exige_divergencias(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo = _leitura(tmp_path, "c", [{"grupo": "c0001", "marca": "ignorar"}])
    assert _validar(rodada, "c", arquivo) == 1
    assert "divergencias.json" in capsys.readouterr().err


def test_validar_leitor_c_cobre_exatamente_as_divergencias(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    certos = _validar_a_e_b(rodada, tmp_path, {"c0002": {"marca": "ilegivel"}})
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    fora = [{"grupo": "c0002", "caractere": certos["c0002"]}, {"grupo": "c0001", "marca": "misto"}]
    assert _validar(rodada, "c", _leitura(tmp_path, "c", fora, "fora.json")) == 1
    assert "fora das divergências" in capsys.readouterr().err
    assert _validar(rodada, "c", _leitura(tmp_path, "c", [], "vazio.json")) == 1
    assert "faltando: c0002" in capsys.readouterr().err
    certa = [{"grupo": "c0002", "caractere": certos["c0002"]}]
    assert _validar(rodada, "c", _leitura(tmp_path, "c", certa, "certa.json")) == 0


# --- consolidar ---------------------------------------------------------------------------


def test_consolidar_aceita_quando_a_e_b_concordam(rodada: Path, tmp_path: Path) -> None:
    certos = _validar_a_e_b(rodada, tmp_path)
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    consolidacao = _json(rodada / "consolidacao.json")
    assert consolidacao["pendentes"] == []
    assert {a["grupo"]: a["caractere"] for a in consolidacao["aceitos"]} == certos
    assert consolidacao["concordancia_ab"] == {"concordantes": len(certos), "total": len(certos)}
    assert not (rodada / "divergencias.json").exists()


def test_consolidar_sem_c_lista_a_divergencia_e_sai_com_3(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _validar_a_e_b(rodada, tmp_path, {"c0003": {"marca": "ilegivel"}})
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    assert _json(rodada / "divergencias.json")["grupos"] == ["c0003"]
    assert (rodada / "contato-divergencias" / "folha-001.png").is_file()
    assert not (rodada / "consolidacao.json").exists()
    assert "c0003" in capsys.readouterr().out


def test_consolidar_c_desempata_com_um_dos_dois(rodada: Path, tmp_path: Path) -> None:
    certos = _validar_a_e_b(rodada, tmp_path, {"c0003": {"marca": "ilegivel"}})
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    leitura_c = _leitura(tmp_path, "c", [{"grupo": "c0003", "marca": "ilegivel"}])
    assert _validar(rodada, "c", leitura_c) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    consolidacao = _json(rodada / "consolidacao.json")
    assert consolidacao["pendentes"] == []
    aceito = {a["grupo"]: a for a in consolidacao["aceitos"]}
    assert aceito["c0003"] == {"grupo": "c0003", "marca": "ilegivel"}
    assert aceito["c0001"]["caractere"] == certos["c0001"]
    assert consolidacao["concordancia_ab"]["concordantes"] == len(certos) - 1


def test_consolidar_c_diferente_dos_dois_deixa_pendente(rodada: Path, tmp_path: Path) -> None:
    _validar_a_e_b(rodada, tmp_path, {"c0003": {"marca": "ilegivel"}})
    assert main(["consolidar", "--rodada", str(rodada)]) == 3
    assert (
        _validar(rodada, "c", _leitura(tmp_path, "c", [{"grupo": "c0003", "marca": "misto"}])) == 0
    )
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    consolidacao = _json(rodada / "consolidacao.json")
    assert consolidacao["pendentes"] == ["c0003"]
    assert "c0003" not in {a["grupo"] for a in consolidacao["aceitos"]}
    assert consolidacao["contagens"]["misto"] == {}


def test_consolidar_conta_marcas_aceitas_por_familia(rodada: Path, tmp_path: Path) -> None:
    certos = _rotulos_corretos(rodada, tmp_path)
    rotulos = _rotulos_de(certos)
    rotulos[1] = {"grupo": "c0002", "marca": "composto"}
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 0
    assert _validar(rodada, "b", _leitura(tmp_path, "b", rotulos)) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    contagens = _json(rodada / "consolidacao.json")["contagens"]
    membros = _grupos(rodada)[1]["membros"]
    assert contagens["composto"] == {"generico": membros}
    assert contagens["fragmento"] == {}


def test_consolidar_exige_as_leituras_a_e_b(
    rodada: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["consolidar", "--rodada", str(rodada)]) == 1
    assert "leitura a" in capsys.readouterr().err


def test_consolidar_recusa_refazer_a_consolidacao(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _validar_a_e_b(rodada, tmp_path)
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 1
    assert "já consolidada" in capsys.readouterr().err


# --- publicar -----------------------------------------------------------------------------


def test_publicar_gera_tabela_que_le_o_texto_do_pdf_sintetico(
    rodada: Path, rodada_base: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    _validar_a_e_b(rodada, tmp_path)
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    saida = tmp_path / "tabela.json"
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida)]) == 0
    tabela = carregar_tabela_glifos(saida)
    assert (tabela.tolerancia, tabela.margem_ambiguidade) == (0.08, 0.02)
    assert (tabela.espaco, tabela.quebra) == (0.48, 1.5)
    assert [g.id for g in tabela.glifos] == [f"g{i:04d}" for i in range(1, len(LETRAS) + 1)]
    for pdf, esperado in (("folha-secreta-a.pdf", TEXTO_A), ("folha-secreta-b.pdf", TEXTO_B)):
        with pymupdf.open(rodada_base[1] / pdf) as documento:
            caminhos = caminhos_da_pagina(documento[0])
        leitura = ler_texto_glifos(caminhos, tabela)
        assert [t.texto for t in leitura.textos] == [esperado]
        assert (leitura.desconhecidos, leitura.ambiguos) == (0, 0)


def test_publicar_deixa_fora_marcas_e_pendentes_e_ignorar_vira_null(
    rodada: Path, tmp_path: Path
) -> None:
    certos = _rotulos_corretos(rodada, tmp_path)
    rotulos = _rotulos_de(certos)
    rotulos[0] = {"grupo": rotulos[0]["grupo"], "marca": "ignorar"}
    rotulos[1] = {"grupo": rotulos[1]["grupo"], "marca": "ilegivel"}
    rotulos[2] = {"grupo": rotulos[2]["grupo"], "marca": "fragmento"}
    for leitor in "ab":
        assert _validar(rodada, leitor, _leitura(tmp_path, leitor, rotulos)) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    saida = tmp_path / "tabela.json"
    argv = ["publicar", "--rodada", str(rodada), "--saida", str(saida), "--espaco", "0.5"]
    assert main(argv) == 0
    tabela = carregar_tabela_glifos(saida)
    assert tabela.espaco == 0.5
    caracteres = [g.caractere for g in tabela.glifos]
    assert caracteres[0] is None
    assert len(caracteres) == len(rotulos) - 2


def test_publicar_exige_consolidacao_e_nao_sobrescreve(
    rodada: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saida = tmp_path / "tabela.json"
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida)]) == 1
    assert "consolidacao.json" in capsys.readouterr().err
    _validar_a_e_b(rodada, tmp_path)
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida)]) == 0
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida)]) == 1
    assert "já existe" in capsys.readouterr().err


# --- --min-membros e formas incertas ------------------------------------------------------


def _agrupar_com_corte(pdfs: Path, destino: Path, minimo: str) -> int:
    argv = ["agrupar", "--pdfs", str(pdfs), "--rodada", str(destino), "--min-membros", minimo]
    return main(argv)


def test_agrupar_min_membros_corta_grupos_raros_e_registra_no_h1(
    rodada_base: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    saida = tmp_path / "corte"
    assert _agrupar_com_corte(rodada_base[1], saida, "2") == 0
    grupos = _grupos(saida)
    assert len(grupos) == len(LETRAS) - 2
    assert all(g["membros"] >= 2 for g in grupos)
    assert [c["id"] for c in _json(saida / "celulas.json")["celulas"]] == [g["id"] for g in grupos]
    h1 = _json(saida / "h1.json")
    assert (h1["min_membros"], h1["grupos_nao_rotulados"], h1["glifos_nao_rotulados"]) == (2, 2, 2)


def test_agrupar_min_membros_padrao_nao_corta_nada(rodada: Path) -> None:
    h1 = _json(rodada / "h1.json")
    assert (h1["min_membros"], h1["grupos_nao_rotulados"], h1["glifos_nao_rotulados"]) == (1, 0, 0)


def test_validar_nao_exige_rotulo_de_grupo_cortado(
    rodada_base: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    saida = tmp_path / "corte"
    assert _agrupar_com_corte(rodada_base[1], saida, "2") == 0
    rotulos: list[Registro] = [{"grupo": g["id"], "marca": "ilegivel"} for g in _grupos(saida)]
    assert _validar(saida, "a", _leitura(tmp_path, "a", rotulos)) == 0


def test_agrupar_recusa_min_membros_invalido(
    rodada_base: tuple[Path, Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _agrupar_com_corte(rodada_base[1], tmp_path / "r0", "0") == 1
    assert "--min-membros" in capsys.readouterr().err
    assert _agrupar_com_corte(rodada_base[1], tmp_path / "r9", "999") == 1
    assert "membros suficientes" in capsys.readouterr().err


def test_h1_lista_as_formas_que_so_aparecem_em_trechos_incertos(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    pdf_texto_contorno(pdfs / "a.pdf", [LinhaTexto(TEXTO_A, (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pdfs / "b.pdf", [LinhaTexto("-=", (20.0, 60.0), 5.0)])
    rodada = tmp_path / "r"
    assert main(["agrupar", "--pdfs", str(pdfs), "--rodada", str(rodada)]) == 0
    formas = _json(rodada / "h1.json")["por_familia"]["generico"]["formas_incertas"]
    assert len(formas) == 2
    assert set(formas[0]) == {"subcaminhos", "caixa"}
    assert "a.pdf" not in json.dumps(formas)
