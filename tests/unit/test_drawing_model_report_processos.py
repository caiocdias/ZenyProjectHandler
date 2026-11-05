# mypy: disable-error-code="no-untyped-call"
"""``--processos`` do relatório do modelo de desenho: mesma saída que a serial, em pool."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts.drawing_model_report import main
from tests.fixtures.glyphs.fonte_livre import LinhaTexto, pdf_texto_contorno
from tests.unit.test_drawing_model_report import _pdf_com_ladrilhos, _pdf_completo, _png, _repo

_MEDIDAS = re.compile(r'("(?:tempo_[a-z_]*s|pico_memoria_bytes)": )[0-9.]+')


def _sem_medidas_do_processo(conteudo: str) -> str:
    return _MEDIDAS.sub(r"\g<1>0", conteudo)


def _pdf_com_imagem_repetida(caminho: Path) -> Path:
    """Duas folhas com a mesma imagem 'outra' (mesma amostra) que ``_pdf_completo`` também tem."""
    with pymupdf.open() as documento:
        for _ in range(2):
            pagina = documento.new_page(width=300, height=200)
            pagina.insert_image(pymupdf.Rect(200, 150, 210, 160), stream=_png((0, 0, 250), lado=8))
        documento.save(caminho)
    return caminho


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """Seis folhas válidas (contorno, imagem repetida em duas folhas) e um .pdf inválido."""
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf_completo(pasta / "a.pdf")
    _pdf_com_imagem_repetida(pasta / "b.pdf")
    _pdf_com_ladrilhos(pasta / "c.pdf")
    _pdf_com_ladrilhos(pasta / "d.pdf", texto_no_ladrilho=2)
    pdf_texto_contorno(pasta / "e.pdf", [LinhaTexto("P7 11-300", (40.0, 60.0), 5.0)])
    pdf_texto_contorno(pasta / "f.pdf", [LinhaTexto("N1 N2", (60.0, 90.0), 6.0)])
    (pasta / "invalido.pdf").write_bytes(b"isto nao e um pdf")
    return pasta


def _rodar(pasta: Path, repo: Path, nome: str, *extras: str) -> tuple[Path, Path]:
    saida = repo / "tmp" / nome / "r.json"
    amostras = repo / "tmp" / nome / "imagens"
    codigo = main(
        [
            *["--raiz", str(pasta), "--saida", str(saida)],
            *["--amostras-imagem", str(amostras), "--raiz-repositorio", str(repo), *extras],
        ]
    )
    assert codigo == 0
    return saida, amostras


def _medidos(relatorio: dict[str, Any]) -> list[dict[str, Any]]:
    return [pdf for pdf in relatorio["pdfs"] if "erro" not in pdf]


def test_processos_4_produz_a_mesma_saida_que_a_serial(corpus: Path, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    saida_serial, imagens_serial = _rodar(corpus, repo, "serial")
    saida_paralela, imagens_paralela = _rodar(corpus, repo, "paralela", "--processos", "4")

    serial = saida_serial.read_text(encoding="utf-8")
    medidos = _medidos(json.loads(serial))
    assert len(medidos) == 6
    assert all("tempo_s" in pdf and "pico_memoria_bytes" in pdf for pdf in medidos)
    assert _sem_medidas_do_processo(saida_paralela.read_text(encoding="utf-8")) == (
        _sem_medidas_do_processo(serial)
    )
    pngs_serial = {p.name: p.read_bytes() for p in imagens_serial.iterdir()}
    assert pngs_serial
    assert {p.name: p.read_bytes() for p in imagens_paralela.iterdir()} == pngs_serial


def test_amostra_repetida_entre_pdfs_fica_com_a_fonte_do_primeiro(
    corpus: Path, tmp_path: Path
) -> None:
    repo = _repo(tmp_path)
    saida, imagens = _rodar(corpus, repo, "paralela", "--processos", "4")

    medidos = _medidos(json.loads(saida.read_text(encoding="utf-8")))
    contagem: dict[str, int] = {}
    for pdf in medidos:
        for amostra in pdf["amostras"]:
            contagem[amostra["sha256"]] = contagem.get(amostra["sha256"], 0) + 1
    assert any(vezes > 1 for vezes in contagem.values())
    assert {p.stem for p in imagens.iterdir()} == set(contagem)


def test_processos_maior_que_o_numero_de_pdfs_funciona(corpus: Path, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    saida, _ = _rodar(corpus, repo, "muitos", "--processos", "16")

    assert json.loads(saida.read_text(encoding="utf-8"))["resumo"]["pdfs"] == 7


def test_corpus_vazio_com_processos(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    repo = _repo(tmp_path)
    saida_serial, _ = _rodar(vazio, repo, "serial")
    saida_paralela, _ = _rodar(vazio, repo, "paralela", "--processos", "4")

    assert saida_paralela.read_bytes() == saida_serial.read_bytes()
    assert json.loads(saida_serial.read_text(encoding="utf-8"))["pdfs"] == []


def test_pdf_invalido_no_pool_vira_erro_no_relatorio(corpus: Path, tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    saida, _ = _rodar(corpus, repo, "paralela", "--processos", "4")

    pdfs = json.loads(saida.read_text(encoding="utf-8"))["pdfs"]
    erros = [pdf for pdf in pdfs if "erro" in pdf]
    assert len(erros) == 1
    assert set(erros[0]) == {"sha256", "erro"}
    assert len(_medidos({"pdfs": pdfs})) == 6


@pytest.mark.parametrize("processos", ["0", "-1"], ids=["zero", "negativo"])
def test_processos_invalido_sai_com_2(
    corpus: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], processos: str
) -> None:
    repo = _repo(tmp_path)
    saida = repo / "tmp" / "r.json"

    with pytest.raises(SystemExit) as encerrou:
        main(
            [
                *["--raiz", str(corpus), "--saida", str(saida)],
                *["--raiz-repositorio", str(repo), "--processos", processos],
            ]
        )

    assert encerrou.value.code == 2
    assert "--processos precisa ser >= 1" in capsys.readouterr().err
    assert not saida.exists()
