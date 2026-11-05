"""``--processos`` do benchmark de texto da ficha: mesma saída que a serial, em pool."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from scripts.benchmark_texto_ficha import main
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    pdf_texto_nativo,
    tabela_do_alfabeto,
)

_MEDIDAS = re.compile(r'("(?:tempo_[a-z_]*s|pico_memoria_bytes)": )[0-9.]+')
_LINHA_TEMPO = re.compile(r"^Tempo de análise:.*$", re.MULTILINE)
_CHAVES_DE_TEMPO = ("tempo_analise_com_glifos_s", "tempo_analise_sem_glifos_s", "tempo_glifos_s")
_IDS = (
    "001-aaaaaaaaaaaa",
    "002-bbbbbbbbbbbb",
    "003-cccccccccccc",
    "004-dddddddddddd",
    "005-eeeeeeeeeeee",
)


def _sem_medidas_do_processo(conteudo: str) -> str:
    return _LINHA_TEMPO.sub("Tempo de análise: 0", _MEDIDAS.sub(r"\g<1>0", conteudo))


def _referencia(rodada: Path, pdf_id: str, pdf: Path) -> None:
    pasta = rodada / "pdfs" / pdf_id / "ficha"
    pasta.mkdir(parents=True)
    poste = {
        "id": "P1",
        "pagina": 1,
        "bbox": [0.095, 0.295, 0.105, 0.305],
        "identificador": None,
        "estruturas": ["11-300"],
        "poste": "P7",
        "coordenada": None,
        "simbolos": [],
        "pendentes": [],
    }
    ficha = {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [poste],
        "vaos": [],
    }
    (pasta / "referencia.json").write_text(json.dumps(ficha), encoding="utf-8")


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Cinco folhas (nativas e em contorno, bytes distintos), uma referência por folha."""
    tabela_do_alfabeto(tmp_path)
    pdfs = tmp_path / "pdfs-origem"
    pdfs.mkdir()
    rodada = tmp_path / "rodada"
    for indice, pdf_id in enumerate(_IDS):
        linhas = [
            LinhaTexto("P7", (40.0 + indice, 60.0), 5.0),
            LinhaTexto("11-300", (40.0, 120.0 + indice), 5.0),
        ]
        escrever = pdf_texto_contorno if indice % 2 else pdf_texto_nativo
        _referencia(rodada, pdf_id, escrever(pdfs / f"folha-{indice}.pdf", linhas))
    return rodada, pdfs, tmp_path / "tabela-alfabeto.json"


def _rodar(
    corpus: tuple[Path, Path, Path], saida: Path, *extras: str, rodada: Path | None = None
) -> int:
    base, pdfs, tabela = corpus
    return main(
        [
            *["--rodada", str(rodada or base), "--pdfs", str(pdfs), "--saida", str(saida)],
            *["--tabela", str(tabela), *extras],
        ]
    )


def test_processos_4_produz_a_mesma_saida_que_a_serial(
    corpus: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    serial, paralela = tmp_path / "serial", tmp_path / "paralela"

    assert _rodar(corpus, serial) == 0
    assert _rodar(corpus, paralela, "--processos", "4") == 0

    json_serial = (serial / "texto-ficha.json").read_text(encoding="utf-8")
    md_serial = (serial / "texto-ficha.md").read_text(encoding="utf-8")
    for chave in _CHAVES_DE_TEMPO:
        assert f'"{chave}"' in json_serial
    assert _LINHA_TEMPO.search(md_serial)
    assert list(json.loads(json_serial)["por_pdf"]) == list(_IDS)
    for nome in ("texto-ficha.json", "texto-ficha.md"):
        esperado = _sem_medidas_do_processo((serial / nome).read_text(encoding="utf-8"))
        obtido = _sem_medidas_do_processo((paralela / nome).read_text(encoding="utf-8"))
        assert obtido == esperado


def test_processos_maior_que_o_numero_de_pdfs_funciona(
    corpus: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    assert _rodar(corpus, tmp_path / "s", "--processos", "16") == 0

    dados = json.loads((tmp_path / "s" / "texto-ficha.json").read_text(encoding="utf-8"))
    assert list(dados["por_pdf"]) == list(_IDS)


def test_corpus_vazio_com_processos(corpus: tuple[Path, Path, Path], tmp_path: Path) -> None:
    vazia = tmp_path / "rodada-vazia"
    (vazia / "pdfs").mkdir(parents=True)

    assert _rodar(corpus, tmp_path / "serial", rodada=vazia) == 0
    assert _rodar(corpus, tmp_path / "paralela", "--processos", "4", rodada=vazia) == 0

    for nome in ("texto-ficha.json", "texto-ficha.md"):
        assert (tmp_path / "paralela" / nome).read_bytes() == (
            tmp_path / "serial" / nome
        ).read_bytes()


def test_referencia_sem_pdf_com_processos_recusa_sem_medir(
    corpus: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    base, _, tabela = corpus

    with pytest.raises(ValueError, match="001-aaaaaaaaaaaa"):
        main(
            [
                *["--rodada", str(base), "--pdfs", str(vazio), "--saida", str(tmp_path / "s")],
                *["--tabela", str(tabela), "--processos", "4"],
            ]
        )
    assert not (tmp_path / "s").exists()


@pytest.mark.parametrize("processos", ["0", "-1"], ids=["zero", "negativo"])
def test_processos_invalido_sai_com_2(
    corpus: tuple[Path, Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    processos: str,
) -> None:
    with pytest.raises(SystemExit) as saida:
        _rodar(corpus, tmp_path / "s", "--processos", processos)

    assert saida.value.code == 2
    assert "--processos precisa ser >= 1" in capsys.readouterr().err
    assert not (tmp_path / "s").exists()
