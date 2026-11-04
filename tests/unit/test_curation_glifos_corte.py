# mypy: disable-error-code="no-untyped-call"
"""Ataques ao corte --min-membros, ao determinismo e a formas_incertas da rodada de glifos."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from scripts.curation_glifos import FORMATO_LEITURA, main
from tests.fixtures.glyphs.fonte_livre import LinhaTexto, pdf_texto_contorno

from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import carregar_tabela_glifos

Registro = dict[str, Any]


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    pasta = tmp_path_factory.mktemp("corte") / "pdfs"
    pasta.mkdir()
    pdf_texto_contorno(pasta / "um.pdf", [LinhaTexto("POSTE 4721", (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pasta / "dois.pdf", [LinhaTexto("TESTE 1274", (20.0, 60.0), 6.0)])
    return pasta


def _json(arquivo: Path) -> Any:
    return json.loads(arquivo.read_text(encoding="utf-8"))


def _agrupar(pdfs: Path, rodada: Path, *extra: str) -> int:
    return main(["agrupar", "--pdfs", str(pdfs), "--rodada", str(rodada), *extra])


def _membros(rodada: Path) -> list[int]:
    return [g["membros"] for g in _json(rodada / "grupos.json")["grupos"]]


@pytest.fixture(scope="module")
def completa(pdfs: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    destino = tmp_path_factory.mktemp("completa") / "r"
    assert _agrupar(pdfs, destino) == 0
    return destino


def _leitura(tmp_path: Path, leitor: str, rotulos: list[Registro]) -> Path:
    arquivo = tmp_path / f"{leitor}.json"
    arquivo.write_text(
        json.dumps({"formato": FORMATO_LEITURA, "leitor": leitor, "rotulos": rotulos}),
        encoding="utf-8",
    )
    return arquivo


def _validar(rodada: Path, leitor: str, arquivo: Path) -> int:
    return main(["validar", "--rodada", str(rodada), "--leitor", leitor, "--arquivo", str(arquivo)])


# --- argumento ----------------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["0", "-1", "-100"])
def test_min_membros_nao_positivo_e_recusado_sem_gravar(
    pdfs: Path, tmp_path: Path, valor: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _agrupar(pdfs, tmp_path / "r", "--min-membros", valor) == 1
    assert "--min-membros" in capsys.readouterr().err
    assert not (tmp_path / "r").exists()


@pytest.mark.parametrize("valor", ["1.5", "abc", "", "nan"])
def test_min_membros_nao_inteiro_e_rejeitado_pelo_parser(
    pdfs: Path, tmp_path: Path, valor: str
) -> None:
    with pytest.raises(SystemExit) as saida:
        _agrupar(pdfs, tmp_path / "r", "--min-membros", valor)
    assert saida.value.code == 2
    assert not (tmp_path / "r").exists()


def test_min_membros_acima_do_maior_grupo_falha_sem_gravar(pdfs: Path, tmp_path: Path) -> None:
    assert _agrupar(pdfs, tmp_path / "r", "--min-membros", "1000000") == 1
    assert not (tmp_path / "r").exists()


# --- fronteira ----------------------------------------------------------------------------


def test_min_membros_um_equivale_ao_padrao(pdfs: Path, tmp_path: Path, completa: Path) -> None:
    assert _agrupar(pdfs, tmp_path / "r", "--min-membros", "1") == 0
    atual, base = _json(tmp_path / "r" / "grupos.json"), _json(completa / "grupos.json")
    assert atual["grupos"] == base["grupos"]
    h1 = _json(tmp_path / "r" / "h1.json")
    assert (h1["min_membros"], h1["grupos_nao_rotulados"], h1["glifos_nao_rotulados"]) == (1, 0, 0)


def test_corte_mantem_exatamente_os_grupos_com_membros_igual_ou_maior(
    pdfs: Path, tmp_path: Path, completa: Path
) -> None:
    todos = _membros(completa)
    for corte in sorted(set(todos)):
        destino = tmp_path / f"r{corte}"
        assert _agrupar(pdfs, destino, "--min-membros", str(corte)) == 0
        esperado = [m for m in todos if m >= corte]
        assert _membros(destino) == esperado, corte
        h1 = _json(destino / "h1.json")
        assert h1["min_membros"] == corte
        assert h1["grupos_nao_rotulados"] == len(todos) - len(esperado)
        assert h1["glifos_nao_rotulados"] == sum(m for m in todos if m < corte)
        ids = [g["id"] for g in _json(destino / "grupos.json")["grupos"]]
        assert ids == [f"c{n:04d}" for n in range(1, len(esperado) + 1)]
        celulas = _json(destino / "celulas.json")["celulas"]
        assert [c["id"] for c in celulas] == ids
        assert _json(destino / "grupos.json")["min_membros"] == corte


def test_corte_acima_do_maior_grupo_por_um_falha(
    pdfs: Path, tmp_path: Path, completa: Path
) -> None:
    assert _agrupar(pdfs, tmp_path / "r", "--min-membros", str(max(_membros(completa)) + 1)) == 1
    assert not (tmp_path / "r").exists()


def test_corte_preserva_o_total_de_glifos_em_trecho(
    pdfs: Path, tmp_path: Path, completa: Path
) -> None:
    destino = tmp_path / "r"
    assert _agrupar(pdfs, destino, "--min-membros", "3") == 0
    h1 = _json(destino / "h1.json")
    rotulados = sum(_membros(destino))
    assert rotulados + h1["glifos_nao_rotulados"] == sum(_membros(completa))
    assert h1["glifos_em_trecho"] == _json(completa / "h1.json")["glifos_em_trecho"]


def test_corte_deixa_o_grupo_de_fora_das_folhas_de_contato(pdfs: Path, tmp_path: Path) -> None:
    destino = tmp_path / "r"
    assert _agrupar(pdfs, destino, "--min-membros", "3") == 0
    assert _json(destino / "h1.json")["folhas_de_contato"] == 1
    assert [p.name for p in (destino / "contato").glob("*.png")] == ["folha-001.png"]


# --- validar / consolidar / publicar coerentes com o corte --------------------------------


def _com_corte(pdfs: Path, tmp_path: Path, corte: int) -> Path:
    destino = tmp_path / "rodada"
    assert _agrupar(pdfs, destino, "--min-membros", str(corte)) == 0
    return destino


def test_validar_exige_so_os_grupos_do_corte_e_recusa_o_cortado(
    pdfs: Path, tmp_path: Path, completa: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada = _com_corte(pdfs, tmp_path, 3)
    ids = [g["id"] for g in _json(rodada / "grupos.json")["grupos"]]
    assert len(ids) < len(_membros(completa))
    rotulos = [{"grupo": g, "caractere": "X"} for g in ids]
    cortado = [*rotulos, {"grupo": f"c{len(ids) + 1:04d}", "caractere": "X"}]
    assert _validar(rodada, "a", _leitura(tmp_path, "a", cortado)) == 1
    assert "desconhecido" in capsys.readouterr().err
    assert _validar(rodada, "a", _leitura(tmp_path, "a", rotulos)) == 0


def test_ciclo_completo_com_corte_publica_so_os_grupos_do_corte(pdfs: Path, tmp_path: Path) -> None:
    rodada = _com_corte(pdfs, tmp_path, 3)
    ids = [g["id"] for g in _json(rodada / "grupos.json")["grupos"]]
    for leitor in "ab":
        rotulos = [{"grupo": g, "caractere": "X"} for g in ids]
        assert _validar(rodada, leitor, _leitura(tmp_path, leitor, rotulos)) == 0
    assert main(["consolidar", "--rodada", str(rodada)]) == 0
    consolidacao = _json(rodada / "consolidacao.json")
    assert consolidacao["concordancia_ab"] == {"concordantes": len(ids), "total": len(ids)}
    saida = tmp_path / "t.json"
    assert main(["publicar", "--rodada", str(rodada), "--saida", str(saida)]) == 0
    assert len(carregar_tabela_glifos(saida).glifos) == len(ids)


def test_consolidar_recusa_leitura_adulterada_com_grupo_de_fora_do_corte(
    pdfs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rodada = _com_corte(pdfs, tmp_path, 3)
    ids = [g["id"] for g in _json(rodada / "grupos.json")["grupos"]]
    for leitor in "ab":
        rotulos = [{"grupo": g, "marca": "ilegivel"} for g in ids]
        assert _validar(rodada, leitor, _leitura(tmp_path, leitor, rotulos)) == 0
    arquivo = rodada / "leituras" / "leitura-b.json"
    dados = _json(arquivo)
    dados["rotulos"].append({"grupo": "c0099", "marca": "ilegivel"})
    arquivo.write_text(json.dumps(dados), encoding="utf-8")
    assert main(["consolidar", "--rodada", str(rodada)]) == 1
    assert "desconhecido" in capsys.readouterr().err
    assert not (rodada / "consolidacao.json").exists()


# --- determinismo e deduplicação ----------------------------------------------------------


def test_renomear_e_reordenar_os_pdfs_nao_muda_nenhum_json(
    pdfs: Path, tmp_path: Path, completa: Path
) -> None:
    outro = tmp_path / "outro"
    outro.mkdir()
    shutil.copy(pdfs / "um.pdf", outro / "zz-ultimo.pdf")
    shutil.copy(pdfs / "dois.pdf", outro / "aa-primeiro.pdf")
    destino = tmp_path / "r"
    assert _agrupar(outro, destino) == 0
    for nome in ("grupos.json", "h1.json", "celulas.json"):
        assert (destino / nome).read_bytes() == (completa / nome).read_bytes(), nome
    base = sorted(p.name for p in (completa / "contato").iterdir())
    assert sorted(p.name for p in (destino / "contato").iterdir()) == base


def test_copia_identica_de_pdf_com_outro_nome_nao_dobra_os_membros(
    pdfs: Path, tmp_path: Path, completa: Path
) -> None:
    com_copia = tmp_path / "copias"
    shutil.copytree(pdfs, com_copia)
    shutil.copy(pdfs / "um.pdf", com_copia / "copia-de-um.pdf")
    destino = tmp_path / "r"
    assert _agrupar(com_copia, destino) == 0
    assert (destino / "grupos.json").read_bytes() == (completa / "grupos.json").read_bytes()


def test_corte_tambem_e_deterministico_com_renomeacao(pdfs: Path, tmp_path: Path) -> None:
    outro = tmp_path / "outro"
    outro.mkdir()
    shutil.copy(pdfs / "um.pdf", outro / "9.pdf")
    shutil.copy(pdfs / "dois.pdf", outro / "1.pdf")
    a, b = tmp_path / "a", tmp_path / "b"
    assert _agrupar(pdfs, a, "--min-membros", "2") == 0
    assert _agrupar(outro, b, "--min-membros", "2") == 0
    for nome in ("grupos.json", "h1.json", "celulas.json"):
        assert (a / nome).read_bytes() == (b / nome).read_bytes(), nome


# --- formas_incertas ----------------------------------------------------------------------


def _com_incertos(tmp_path: Path) -> Path:
    pasta = tmp_path / "inc"
    pasta.mkdir()
    pdf_texto_contorno(pasta / "a.pdf", [LinhaTexto("TESTE", (20.0, 60.0), 5.0)])
    pdf_texto_contorno(pasta / "b.pdf", [LinhaTexto("-=", (20.0, 60.0), 5.0)])
    return pasta


def test_formas_incertas_lista_so_forma_e_confere_com_a_contagem(tmp_path: Path) -> None:
    destino = tmp_path / "r"
    assert _agrupar(_com_incertos(tmp_path), destino) == 0
    familia = _json(destino / "h1.json")["por_familia"]["generico"]
    formas = familia["formas_incertas"]
    assert len(formas) == familia["formas_so_em_trechos_incertos"] == 2
    for forma in formas:
        assert set(forma) == {"subcaminhos", "caixa"}
        assert isinstance(forma["subcaminhos"], int)
        assert len(forma["caixa"]) == 3
        assert all(isinstance(v, float) for v in forma["caixa"])
    assert formas == sorted(formas, key=lambda f: (f["subcaminhos"], f["caixa"]))


def test_formas_incertas_nao_leva_folha_nem_caminho_nem_pdf(tmp_path: Path) -> None:
    pasta = _com_incertos(tmp_path)
    destino = tmp_path / "r"
    assert _agrupar(pasta, destino) == 0
    h1 = _json(destino / "h1.json")
    texto = json.dumps(h1["por_familia"]["generico"]["formas_incertas"])
    assert not re.search(r"[0-9a-f]{12}", texto)
    assert ".pdf" not in texto
    assert str(tmp_path) not in texto
    assert "contornos" not in texto


def test_formas_incertas_vazia_quando_tudo_e_quadro_confirmado(completa: Path) -> None:
    familia = _json(completa / "h1.json")["por_familia"]["generico"]
    assert familia["formas_incertas"] == []
    assert familia["formas_so_em_trechos_incertos"] == 0


def test_formas_incertas_independe_do_corte(tmp_path: Path) -> None:
    pasta = _com_incertos(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    assert _agrupar(pasta, a) == 0
    assert _agrupar(pasta, b, "--min-membros", "2") == 0
    de_a = _json(a / "h1.json")["por_familia"]["generico"]["formas_incertas"]
    de_b = _json(b / "h1.json")["por_familia"]["generico"]["formas_incertas"]
    assert de_a == de_b


# --- --excluir-sha estrito ----------------------------------------------------------------


def test_excluir_sha_aceita_comentarios_linhas_vazias_e_bom(pdfs: Path, tmp_path: Path) -> None:
    from scripts.curation_round import hash_arquivo

    reservadas = tmp_path / "res.txt"
    sha = hash_arquivo(pdfs / "dois.pdf")
    reservadas.write_text(f"# folhas de avaliação\n\n   \n{sha.upper()}  \n", encoding="utf-8-sig")
    destino = tmp_path / "r"
    assert _agrupar(pdfs, destino, "--excluir-sha", str(reservadas)) == 0
    assert _json(destino / "h1.json")["folhas_excluidas"] == 1


def test_excluir_sha_com_comentario_no_fim_da_linha_e_erro(pdfs: Path, tmp_path: Path) -> None:
    from scripts.curation_round import hash_arquivo

    reservadas = tmp_path / "res.txt"
    reservadas.write_text(hash_arquivo(pdfs / "dois.pdf") + "  # folha 3\n", encoding="utf-8")
    assert _agrupar(pdfs, tmp_path / "r", "--excluir-sha", str(reservadas)) == 1
    assert not (tmp_path / "r").exists()


def test_excluir_sha_em_utf16_falha_sem_gravar(pdfs: Path, tmp_path: Path) -> None:
    from scripts.curation_round import hash_arquivo

    reservadas = tmp_path / "res.txt"
    reservadas.write_text(hash_arquivo(pdfs / "dois.pdf") + "\n", encoding="utf-16")
    assert _agrupar(pdfs, tmp_path / "r", "--excluir-sha", str(reservadas)) == 1
    assert not (tmp_path / "r").exists()
