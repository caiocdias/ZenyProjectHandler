# mypy: disable-error-code="no-untyped-call"
"""Testes adversariais do relatório do modelo de desenho (amostras, privacidade, erros)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pymupdf
from scripts.drawing_model_report import main, medir_pdf

_XREF = re.compile(r"(\d+) 0 R")


def _png(cor: tuple[int, int, int], lado: int = 4) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, lado, lado), False)
    pixmap.set_rect(pixmap.irect, cor)
    return bytes(pixmap.tobytes("png"))


def _cor(indice: int) -> tuple[int, int, int]:
    return (10 + 13 * indice, 200 - 7 * indice, 30 + 11 * indice)


def _grade(
    caminho: Path,
    *,
    colunas: int = 4,
    linhas: int = 4,
    passo: int = 50,
    lado_caixa: int = 50,
    distintas: bool = True,
    textos_nos_ladrilhos: tuple[int, ...] = (),
    metadados: dict[str, str] | None = None,
) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=600, height=600)
        for indice in range(colunas * linhas):
            x, y = 10 + passo * (indice % colunas), 10 + passo * (indice // colunas)
            cor = _cor(indice if distintas else 0)
            caixa = pymupdf.Rect(x, y, x + lado_caixa, y + lado_caixa)
            pagina.insert_image(caixa, stream=_png(cor))
        for indice in textos_nos_ladrilhos:
            x = 12 + passo * (indice % colunas)
            y = 40 + passo * (indice // colunas)
            pagina.insert_text((x, y), "AB", fontsize=8, fontname="helv")
        if metadados:
            documento.set_metadata(metadados)
        documento.save(caminho)
    return caminho


def _com_carimbos(caminho: Path, quantidade: int) -> Path:
    with pymupdf.open() as documento:
        documento.new_page(width=400, height=300)
        xrefs = []
        for k in range(quantidade):
            auxiliar = documento.new_page(width=50, height=50)
            xrefs.append(auxiliar.insert_image(auxiliar.rect, stream=_png(_cor(k), lado=6)))
        for k, xref_imagem in enumerate(xrefs):
            area = pymupdf.Rect(10 + 60 * k, 10, 60 + 60 * k, 60)
            carimbo = documento[0].add_stamp_annot(area, stamp=0)
            aparencia = _XREF.search(str(documento.xref_get_key(carimbo.xref, "AP")[1]))
            assert aparencia is not None
            xref_ap = int(aparencia.group(1))
            documento.xref_set_key(xref_ap, "Resources/XObject/ImAp", f"{xref_imagem} 0 R")
            fluxo = bytes(documento.xref_stream(xref_ap) or b"")
            documento.update_stream(xref_ap, fluxo + b"\nq 12 0 0 12 2 2 cm /ImAp Do Q\n")
        for _ in range(quantidade):
            documento.delete_page(1)
        documento.save(caminho)
    return caminho


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tmp").mkdir(parents=True)
    return repo


def _amostras(pdf: Path) -> list[dict[str, Any]]:
    return list(medir_pdf(pdf)["amostras"])


def test_quatro_imagens_do_mesmo_tamanho_em_paginas_diferentes_nao_sao_ladrilho(
    tmp_path: Path,
) -> None:
    with pymupdf.open() as documento:
        for _ in range(4):
            pagina = documento.new_page(width=200, height=200)
            pagina.insert_image(pymupdf.Rect(10, 10, 60, 60), stream=_png((250, 0, 0)))
        documento.save(tmp_path / "p.pdf")

    assert medir_pdf(tmp_path / "p.pdf")["imagens"] == {"ladrilho": 0, "anotacao": 0, "outra": 4}


def test_grade_com_folga_de_um_ponto_ainda_e_ladrilho(tmp_path: Path) -> None:
    pdf = _grade(tmp_path / "a.pdf", colunas=2, linhas=2, passo=51, lado_caixa=50)

    assert medir_pdf(pdf)["imagens"]["ladrilho"] == 4


def test_fracao_de_ladrilhos_nao_conta_area_sobreposta_duas_vezes(tmp_path: Path) -> None:
    pdf = _grade(tmp_path / "s.pdf", colunas=2, linhas=2, passo=25, lado_caixa=50)

    medicao = medir_pdf(pdf)

    assert medicao["imagens"]["ladrilho"] == 4
    assert medicao["paginas"][0]["fracao_ladrilhos"] == round(75 * 75 / (600 * 600), 4)


def test_ladrilhos_identicos_geram_uma_unica_amostra(tmp_path: Path) -> None:
    amostras = _amostras(_grade(tmp_path / "i.pdf", colunas=2, linhas=2, distintas=False))

    assert [a["motivo"] for a in amostras] == ["sorteio"]


def test_pdf_sem_imagens_nao_tem_amostras_nem_classes(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        documento.new_page().insert_text((50, 50), "oi")
        documento.save(tmp_path / "v.pdf")

    medicao = medir_pdf(tmp_path / "v.pdf")

    assert medicao["amostras"] == []
    assert medicao["imagens"] == {"ladrilho": 0, "anotacao": 0, "outra": 0}


def test_limite_de_cinco_ladrilhos_que_cruzam_e_dois_sorteados_sem_repeticao(
    tmp_path: Path,
) -> None:
    pdf = _grade(tmp_path / "c.pdf", textos_nos_ladrilhos=(0, 1, 2, 3, 4, 5, 6))

    amostras = _amostras(pdf)

    motivos = [a["motivo"] for a in amostras]
    assert motivos.count("cruza_grupo_ou_texto") == 5
    assert motivos.count("sorteio") == 2
    assert len(amostras) == 7
    assert len({a["sha256"] for a in amostras}) == 7
    assert _amostras(pdf) == amostras


def test_poucos_ladrilhos_nao_quebram_o_sorteio(tmp_path: Path) -> None:
    pdf = _grade(tmp_path / "q.pdf", colunas=2, linhas=2, textos_nos_ladrilhos=(0, 1, 2))

    motivos = sorted(a["motivo"] for a in _amostras(pdf))

    assert motivos == ["cruza_grupo_ou_texto"] * 3 + ["sorteio"]


def test_no_maximo_tres_anotacoes_por_pdf(tmp_path: Path) -> None:
    medicao = medir_pdf(_com_carimbos(tmp_path / "an.pdf", 5))

    assert medicao["imagens"]["anotacao"] == 5
    anotadas = [a for a in medicao["amostras"] if a["classe"] == "anotacao"]
    assert len(anotadas) == 3
    assert len({a["sha256"] for a in anotadas}) == 3


def test_todas_as_imagens_outra_entram_na_amostra(tmp_path: Path) -> None:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=400, height=400)
        for k in range(7):
            x, y = 10 + 53 * k, 10 + 31 * k
            pagina.insert_image(pymupdf.Rect(x, y, x + 20 + k, y + 20), stream=_png(_cor(k), 5 + k))
        documento.save(tmp_path / "o.pdf")

    amostras = _amostras(tmp_path / "o.pdf")

    assert [a["classe"] for a in amostras] == ["outra"] * 7
    assert len({a["sha256"] for a in amostras}) == 7


def test_metadados_com_caminho_nao_vazam_no_relatorio_nem_nos_nomes(tmp_path: Path) -> None:
    pasta = tmp_path / "entrada"
    pasta.mkdir()
    _grade(
        pasta / "Projeto-Cliente-XPTO.pdf",
        colunas=2,
        linhas=2,
        metadados={
            "producer": "C:\\Users\\fulano\\Documentos\\gerador-secreto.exe",
            "creator": "/home/fulano/ferramenta-secreta",
            "title": "TITULO-SECRETO",
            "author": "AUTOR-SECRETO",
            "subject": "ASSUNTO-SECRETO",
        },
    )
    repo = _repo(tmp_path)
    saida = repo / "tmp" / "r.json"
    amostras = repo / "tmp" / "img"

    codigo = main(
        [
            *["--raiz", str(pasta), "--saida", str(saida)],
            *["--amostras-imagem", str(amostras), "--raiz-repositorio", str(repo)],
        ]
    )

    assert codigo == 0
    conteudo = saida.read_text(encoding="utf-8").lower()
    nomes = " ".join(p.name for p in amostras.iterdir()).lower()
    for proibido in ("fulano", "secret", "xpto", "projeto-cliente", "gerador", "documentos"):
        assert proibido not in conteudo
        assert proibido not in nomes
    assert "/home" not in conteudo and "c:" not in conteudo and "\\\\" not in conteudo


def test_pdf_corrompido_vira_erro_e_nao_derruba_os_demais(tmp_path: Path) -> None:
    pasta = tmp_path / "entrada"
    pasta.mkdir()
    _grade(pasta / "bom.pdf", colunas=2, linhas=2)
    ruim = pasta / "ruim.PDF"
    ruim.write_bytes(b"%PDF-1.4 isto nao e um pdf valido")
    (pasta / "nota.txt").write_text("ignorar", encoding="utf-8")
    repo = _repo(tmp_path)
    saida = repo / "tmp" / "r.json"

    codigo = main(["--raiz", str(pasta), "--saida", str(saida), "--raiz-repositorio", str(repo)])

    assert codigo == 0
    relatorio = json.loads(saida.read_text(encoding="utf-8"))
    assert relatorio["resumo"]["pdfs"] == 2 and relatorio["resumo"]["erros"] == 1
    com_erro = [p for p in relatorio["pdfs"] if "erro" in p]
    assert len(com_erro) == 1
    assert set(com_erro[0]) == {"sha256", "erro"}
    assert com_erro[0]["sha256"] == hashlib.sha256(ruim.read_bytes()).hexdigest()
    assert "ruim" not in saida.read_text(encoding="utf-8").lower()
    assert relatorio["resumo"]["imagens"]["ladrilho"] == 4


def test_saida_e_amostras_fora_de_tmp_sao_recusadas_sem_efeito_colateral(tmp_path: Path) -> None:
    pasta = tmp_path / "pdfs"
    pasta.mkdir()
    _grade(pasta / "a.pdf", colunas=2, linhas=2)
    repo = _repo(tmp_path)
    base = ["--raiz", str(pasta), "--raiz-repositorio", str(repo)]
    dentro = str(repo / "tmp" / "r.json")
    absoluta_fora = tmp_path / "fora" / "r.json"
    irma = repo / "tmp-outro" / "r.json"
    escapando = repo / "tmp" / ".." / "img"

    codigos = (
        main([*base, "--saida", str(absoluta_fora)]),
        main([*base, "--saida", str(irma)]),
        main([*base, "--saida", dentro, "--amostras-imagem", str(escapando)]),
        main([*base, "--saida", dentro, "--amostras-imagem", str(tmp_path / "abs")]),
    )

    assert codigos == (2, 2, 2, 2)
    assert not absoluta_fora.parent.exists() and not irma.parent.exists()
    assert not (repo / "img").exists() and not (tmp_path / "abs").exists()
    assert not (repo / "tmp" / "r.json").exists()


def test_raiz_inexistente_retorna_erro_sem_gravar(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    codigo = main(
        [
            *["--raiz", str(tmp_path / "nao-existe"), "--saida", str(repo / "tmp" / "r.json")],
            *["--raiz-repositorio", str(repo)],
        ]
    )

    assert codigo == 2
    assert not (repo / "tmp" / "r.json").exists()


def test_diretorio_sem_pdfs_gera_relatorio_vazio(tmp_path: Path) -> None:
    pasta = tmp_path / "vazia"
    pasta.mkdir()
    repo = _repo(tmp_path)
    saida = repo / "tmp" / "r.json"

    codigo = main(["--raiz", str(pasta), "--saida", str(saida), "--raiz-repositorio", str(repo)])

    assert codigo == 0
    resumo = json.loads(saida.read_text(encoding="utf-8"))["resumo"]
    assert resumo["pdfs"] == 0 and resumo["familias"] == {}
