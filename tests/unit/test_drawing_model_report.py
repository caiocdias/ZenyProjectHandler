# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts import drawing_model_report
from scripts.drawing_model_report import main, medir_pdf

from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho

_XREF = re.compile(r"(\d+) 0 R")
_CORES = [(250, 0, 0), (0, 250, 0), (0, 0, 250), (250, 250, 0), (0, 250, 250), (250, 0, 250)]


def _png(cor: tuple[int, int, int], lado: int = 4) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, lado, lado), False)
    pixmap.set_rect(pixmap.irect, cor)
    return bytes(pixmap.tobytes("png"))


def _pdf_com_ladrilhos(caminho: Path, *, texto_no_ladrilho: int | None = None) -> Path:
    """Grade 4x2 de ladrilhos 4x4 px com seis cores distintas (seis sha256 diferentes)."""
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=400, height=300)
        for indice in range(8):
            x, y = 10 + 50 * (indice % 4), 10 + 50 * (indice // 4)
            cor = _CORES[indice % len(_CORES)]
            pagina.insert_image(pymupdf.Rect(x, y, x + 50, y + 50), stream=_png(cor))
        if texto_no_ladrilho is not None:
            x = 12 + 50 * (texto_no_ladrilho % 4)
            y = 40 + 50 * (texto_no_ladrilho // 4)
            pagina.insert_text((x, y), "ABC", fontsize=8, fontname="helv")
        documento.save(caminho)
    return caminho


def _pdf_completo(caminho: Path, *, metadados: dict[str, str] | None = None) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        for linha in range(2):
            for coluna in range(2):
                x, y = 10 + 50 * coluna, 10 + 50 * linha
                pagina.insert_image(pymupdf.Rect(x, y, x + 50, y + 50), stream=_png((250, 0, 0)))
        pagina.insert_image(pymupdf.Rect(200, 150, 210, 160), stream=_png((0, 0, 250), lado=8))
        pagina.draw_line((120, 20), (200, 20))
        pagina.draw_circle((150, 100), 10)
        pagina.insert_text((120, 60), "P1 U3(1)", fontsize=10, fontname="helv")
        auxiliar = documento.new_page(width=50, height=50)
        xref_imagem = auxiliar.insert_image(auxiliar.rect, stream=_png((0, 250, 0)))
        carimbo = documento[0].add_stamp_annot(pymupdf.Rect(220, 20, 280, 60), stamp=0)
        aparencia = _XREF.search(str(documento.xref_get_key(carimbo.xref, "AP")[1]))
        assert aparencia is not None
        xref_aparencia = int(aparencia.group(1))
        documento.xref_set_key(xref_aparencia, "Resources/XObject/ImAp", f"{xref_imagem} 0 R")
        conteudo = bytes(documento.xref_stream(xref_aparencia) or b"")
        documento.update_stream(xref_aparencia, conteudo + b"\nq 12 0 0 12 2 2 cm /ImAp Do Q\n")
        documento.delete_page(1)
        if metadados:
            documento.set_metadata(metadados)
        documento.save(caminho)
    return caminho


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tmp").mkdir(parents=True)
    return repo


def test_medir_pdf_sintetico_conta_primitivas_e_classifica_imagens(tmp_path: Path) -> None:
    medicao = medir_pdf(_pdf_completo(tmp_path / "a.pdf"))

    assert re.fullmatch(r"[0-9a-f]{64}", medicao["sha256"])
    assert medicao["familia"] == "generico"
    assert dict(medicao["sinais"])["imagens"] >= 5
    assert medicao["imagens"] == {"ladrilho": 4, "anotacao": 1, "outra": 1}
    assert medicao["tempo_s"] >= 0.0 and medicao["pico_memoria_bytes"] > 0
    pagina = medicao["paginas"][0]
    assert pagina["imagens"] == {"ladrilho": 4, "anotacao": 1, "outra": 1}
    assert 0.0 < pagina["fracao_ladrilhos"] < 1.0
    assert pagina["textos"]["nativo"] >= 1 and pagina["textos"]["shx"] == 0
    assert pagina["circulos"] == 1
    assert pagina["polilinhas"] >= 1
    assert set(pagina["caminhos"]) == {"traco", "preenchimento", "traco_e_preenchimento"}
    assert pagina["caminhos"]["traco"] >= 2
    assert isinstance(pagina["arcos"], int) and isinstance(pagina["grupos"], int)
    assert isinstance(pagina["diagnosticos"], dict)


def test_tres_imagens_iguais_nao_sao_ladrilho(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=200)
        for coluna in range(3):
            x = 10 + 50 * coluna
            pagina.insert_image(pymupdf.Rect(x, 10, x + 50, 60), stream=_png((250, 0, 0)))
        documento.save(tmp_path / "t.pdf")

    assert medir_pdf(tmp_path / "t.pdf")["imagens"] == {"ladrilho": 0, "anotacao": 0, "outra": 3}


def test_imagens_iguais_fora_de_grade_nao_sao_ladrilho(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=400, height=400)
        for x, y in ((10, 10), (97, 31), (183, 219), (301, 143)):
            pagina.insert_image(pymupdf.Rect(x, y, x + 20, y + 20), stream=_png((250, 0, 0)))
        documento.save(tmp_path / "g.pdf")

    assert medir_pdf(tmp_path / "g.pdf")["imagens"] == {"ladrilho": 0, "anotacao": 0, "outra": 4}


def test_relatorio_nao_tem_caminho_nome_nem_produtor(tmp_path: Path) -> None:
    pasta = tmp_path / "pasta-secreta"
    pasta.mkdir()
    _pdf_completo(
        pasta / "nome-secreto.pdf",
        metadados={"producer": "PRODUTOR-SECRETO", "creator": "CRIADOR-SECRETO"},
    )
    repo = _repo(tmp_path)
    saida = repo / "tmp" / "e04" / "r.json"
    amostras = repo / "tmp" / "e04" / "imagens"

    codigo = main(
        [
            "--raiz",
            str(pasta),
            "--saida",
            str(saida),
            "--amostras-imagem",
            str(amostras),
            "--raiz-repositorio",
            str(repo),
        ]
    )

    assert codigo == 0
    conteudo = saida.read_text(encoding="utf-8")
    nomes = " ".join(p.name for p in amostras.iterdir())
    for proibido in ("secreto", "pasta-secreta", "nome-secreto", str(tmp_path)):
        assert proibido.lower() not in conteudo.lower()
        assert proibido.lower() not in nomes.lower()
    assert len(json.loads(conteudo)["pdfs"]) == 1


def test_cli_recusa_saida_fora_de_tmp(tmp_path: Path) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf_completo(pasta / "a.pdf")
    repo = _repo(tmp_path)
    base = ["--raiz", str(pasta), "--raiz-repositorio", str(repo)]

    fora = main([*base, "--saida", str(repo / "r.json")])
    amostras_fora = main(
        [*base, "--saida", str(repo / "tmp" / "r.json"), "--amostras-imagem", str(repo / "img")]
    )
    escapando = main([*base, "--saida", str(repo / "tmp" / ".." / "r.json")])

    assert (fora, amostras_fora, escapando) == (2, 2, 2)
    assert not (repo / "r.json").exists() and not (repo / "tmp" / "r.json").exists()


def test_amostras_de_imagem_sao_nomeadas_pelo_sha(tmp_path: Path) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf_completo(pasta / "a.pdf")
    repo = _repo(tmp_path)
    saida = repo / "tmp" / "r.json"
    amostras = repo / "tmp" / "imagens"

    codigo = main(
        [
            *["--raiz", str(pasta), "--saida", str(saida)],
            *["--amostras-imagem", str(amostras), "--raiz-repositorio", str(repo)],
        ]
    )

    assert codigo == 0
    pdf = json.loads(saida.read_text(encoding="utf-8"))["pdfs"][0]
    esperados = {a["sha256"] for a in pdf["amostras"]}
    arquivos = {p.stem: p for p in amostras.iterdir()}
    assert set(arquivos) == esperados
    assert all(re.fullmatch(r"[0-9a-f]{64}", sha) for sha in arquivos)
    assert all(p.suffix == ".png" and p.read_bytes()[:4] == b"\x89PNG" for p in arquivos.values())
    assert {a["classe"] for a in pdf["amostras"]} == {"outra", "anotacao", "ladrilho"}


def _amostras(pdf: Path) -> list[dict[str, Any]]:
    return list(medir_pdf(pdf)["amostras"])


def test_amostra_inclui_ladrilho_que_cruza_texto_e_sorteio_estavel(tmp_path: Path) -> None:
    sem_texto_pdf = _pdf_com_ladrilhos(tmp_path / "a.pdf")
    copia = tmp_path / "b.pdf"
    copia.write_bytes(sem_texto_pdf.read_bytes())  # o sorteio depende só do sha256 do PDF
    com_texto_pdf = _pdf_com_ladrilhos(tmp_path / "c.pdf", texto_no_ladrilho=2)

    sem_texto = _amostras(sem_texto_pdf)
    com_texto = _amostras(com_texto_pdf)

    assert [a["motivo"] for a in sem_texto] == ["sorteio", "sorteio"]
    assert _amostras(copia) == sem_texto
    assert _amostras(com_texto_pdf) == com_texto
    cruzados = [a for a in com_texto if a["motivo"] == "cruza_grupo_ou_texto"]
    assert len(cruzados) == 1 and len(com_texto) == 3
    modelo = extrair_modelo_desenho(com_texto_pdf)
    coberto = next(
        i
        for i in modelo.paginas[0].imagens
        if abs(i.bbox[0] - 110.0) < 1.0 and abs(i.bbox[1] - 10.0) < 1.0
    )
    assert cruzados[0]["sha256"] == coberto.sha256


def test_cli_com_tabela_de_glifos_indisponivel_sai_com_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _indisponivel(_caminho: Path | None = None) -> object:
        raise ValueError("Tabela de glifos inválida: JSON ilegível.")

    monkeypatch.setattr(drawing_model_report, "carregar_tabela_glifos", _indisponivel)
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _pdf_completo(pasta / "a.pdf")
    repo = _repo(tmp_path)
    saida = repo / "tmp" / "r.json"

    codigo = main(["--raiz", str(pasta), "--raiz-repositorio", str(repo), "--saida", str(saida)])

    assert codigo == 2
    assert not saida.exists()
    assert "tabela de glifos" in capsys.readouterr().err.lower()
