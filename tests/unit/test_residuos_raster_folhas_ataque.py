# mypy: disable-error-code="no-untyped-call"
"""Ataque aos resíduos raster por folha: guarda cega, saneamento, rotação, fora do domínio."""

from __future__ import annotations

import gc
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import scripts.residuos_raster_folhas as residuos
from scripts.curation_round import RodadaError
from scripts.ficha_poste import validar_ficha

from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    FonteGramaticaFalhou,
)

Dados = dict[str, Any]
LARGURA, ALTURA = 500.0, 400.0
NOME_PDF = "folha-secreta.pdf"
COR_IMAGEM = (10, 40, 90)


def _imagem(pagina: pymupdf.Page, caixa: tuple[float, float, float, float], cor: int = 10) -> None:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
    pixmap.set_rect(pixmap.irect, (cor, 40, 90))
    pagina.insert_image(pymupdf.Rect(caixa), pixmap=pixmap)


def _salvar(documento: pymupdf.Document, caminho: Path) -> str:
    documento.save(caminho)
    documento.close()
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _pdf(caminho: Path, rotacao: int = 0, imagens: int = 1, paginas: int = 1) -> str:
    documento = pymupdf.open()
    for _ in range(paginas):
        pagina = documento.new_page(width=LARGURA, height=ALTURA)
        for numero in range(imagens):
            deslocamento = 40.0 * numero
            _imagem(pagina, (100 + deslocamento, 100, 130 + deslocamento, 130), 10 + numero)
        pagina.set_rotation(rotacao)
    return _salvar(documento, caminho)


def _ficha(sha: str, simbolos: Sequence[Dados]) -> Dados:
    poste: Dados = {
        "id": "P1",
        "pagina": 1,
        "bbox": [0.1, 0.1, 0.1, 0.1],
        "identificador": None,
        "estruturas": [],
        "poste": None,
        "coordenada": None,
        "simbolos": list(simbolos),
        "pendentes": [],
    }
    ficha: Dados = {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": sha,
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [poste],
        "vaos": [],
    }
    assert validar_ficha(ficha) == []
    return ficha


def _montar(
    raiz: Path,
    folhas: Sequence[tuple[str, str, str, Sequence[Dados]]],
    raiz_corpus: str = "../corpus",
    nome: str = "rodada",
) -> Path:
    rodada = raiz / nome
    entradas = []
    for pdf_id, arquivo, sha, itens in folhas:
        entradas.append({"pdf_id": pdf_id, "caminho_relativo": arquivo, "sha256": sha})
        pasta = rodada / "pdfs" / pdf_id / "ficha"
        pasta.mkdir(parents=True)
        (pasta / "referencia.json").write_text(json.dumps(_ficha(sha, itens)), encoding="utf-8")
    manifesto = {
        "schema_version": "curadoria-rodada-v1",
        "raiz_corpus": raiz_corpus,
        "pdfs": entradas,
    }
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return rodada


def _folha(relatorio: Dados, pdf_id: str) -> Dados:
    return next(item for item in relatorio["folhas"] if item["pdf_id"] == pdf_id)


# --- guarda do conjunto cego -------------------------------------------------------------

_CAMINHOS_CEGOS = [
    "avaliacao-cega/folha.pdf",
    "AVALIACAO-CEGA/folha.pdf",
    "Avaliacao-Cega\\folha.pdf",
    "avaliacao-cega./folha.pdf",
    "avaliacao-cega /folha.pdf",
    "sub/../avaliacao-cega/folha.pdf",
    "x//avaliacao-cega//folha.pdf",
    "./avaliacao-cega/folha.pdf",
]


@pytest.mark.parametrize("relativo", _CAMINHOS_CEGOS)
def test_caminho_relativo_cego_nao_abre_o_pdf(tmp_path: Path, relativo: str) -> None:
    cega = tmp_path / "corpus" / "avaliacao-cega"
    cega.mkdir(parents=True)
    sha = _pdf(cega / "folha.pdf")
    rodada = _montar(tmp_path, [("a", relativo, sha, [])])
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folha = _folha(relatorio, "a")
    assert folha["total"] is None
    assert folha["paginas"] == []
    assert "avaliacao-cega" in folha["erro"]


@pytest.mark.parametrize(
    "raiz_corpus",
    [
        "../corpus/avaliacao-cega",
        "../corpus/AVALIACAO-CEGA",
        "../corpus/x/../avaliacao-cega",
    ],
)
def test_raiz_corpus_cega_nao_abre_o_pdf(tmp_path: Path, raiz_corpus: str) -> None:
    cega = tmp_path / "corpus" / "avaliacao-cega"
    cega.mkdir(parents=True)
    sha = _pdf(cega / "folha.pdf")
    rodada = _montar(tmp_path, [("a", "folha.pdf", sha, [])], raiz_corpus=raiz_corpus)
    try:
        relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    except RodadaError:
        return
    folha = _folha(relatorio, "a")
    assert folha["total"] is None
    assert folha["paginas"] == []
    assert "avaliacao-cega" in folha["erro"]


def _caminhos_de_rodada_cega(base: Path) -> dict[str, Path]:
    return {
        "maiusculas": base.parent / "AVALIACAO-CEGA" / "rodada",
        "ponto-ponto": base.parent / "outra" / ".." / "avaliacao-cega" / "rodada",
        "ponto-ponto-dentro": base / "sub" / ".." / "rodada",
        "ponto-final": Path(str(base) + ".") / "rodada",
    }


@pytest.mark.parametrize(
    "variante", ["maiusculas", "ponto-ponto", "ponto-ponto-dentro", "ponto-final"]
)
def test_rodada_em_pasta_cega_e_recusada_sem_ler_nada(tmp_path: Path, variante: str) -> None:
    (tmp_path / "outra").mkdir()
    base = tmp_path / "avaliacao-cega"
    (base / "sub").mkdir(parents=True)
    sha = _pdf(tmp_path / "corpus.pdf")
    _montar(base, [("a", "corpus.pdf", sha, [])], raiz_corpus="..")
    caminho = _caminhos_de_rodada_cega(base)[variante]
    saida = tmp_path / "saida"
    with pytest.raises(RodadaError):
        residuos.medir_residuos(caminho, saida)
    assert not saida.exists()


# --- saneamento --------------------------------------------------------------------------


def test_pdf_corrompido_nao_vaza_caminho_nem_nome(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    conteudo = b"isto nao e um pdf"
    (corpus / NOME_PDF).write_bytes(conteudo)
    sha = hashlib.sha256(conteudo).hexdigest()
    rodada = _montar(tmp_path, [("a", NOME_PDF, sha, [])])
    saida = tmp_path / "saida"
    relatorio = residuos.medir_residuos(rodada, saida)
    assert _folha(relatorio, "a")["total"] is None
    texto = (saida / "residuos-raster.json").read_text("utf-8")
    assert NOME_PDF not in texto
    assert Path(NOME_PDF).stem not in texto
    assert str(tmp_path) not in texto
    assert tmp_path.as_posix() not in texto


def test_pdf_ausente_nao_vaza_nome(tmp_path: Path) -> None:
    (tmp_path / "corpus").mkdir()
    rodada = _montar(tmp_path, [("a", NOME_PDF, "0" * 64, [])])
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folha = _folha(relatorio, "a")
    assert folha["total"] is None
    assert Path(NOME_PDF).stem not in folha["erro"]
    assert str(tmp_path) not in folha["erro"]


def test_excecao_na_medicao_vira_falha_saneada_e_fecha_o_documento(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sha = _pdf(corpus / NOME_PDF)
    rodada = _montar(tmp_path, [("a", NOME_PDF, sha, [])])

    def explode(*_: Any, **__: Any) -> Any:
        raise RuntimeError(f"falhou em {corpus / NOME_PDF}")

    monkeypatch.setattr(residuos, "residuos_raster", explode)
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    gc.collect()
    folha = _folha(relatorio, "a")
    assert folha["total"] is None
    assert Path(NOME_PDF).stem not in folha["erro"]
    assert str(tmp_path) not in folha["erro"]
    # documento fechado: no Windows o arquivo pode ser removido
    (corpus / NOME_PDF).unlink()


def test_sha_da_rodada_diverge_do_pdf_mesmo_com_ficha_certa(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sha = _pdf(corpus / NOME_PDF)
    rodada = _montar(tmp_path, [("a", NOME_PDF, sha, [])])
    manifesto = json.loads((rodada / "rodada.json").read_text("utf-8"))
    manifesto["pdfs"][0]["sha256"] = "f" * 64
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folha = _folha(relatorio, "a")
    assert folha["total"] is None
    assert "sha256" in folha["erro"]


def test_pdf_id_com_separador_nao_escreve_fora_da_saida(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sha = _pdf(corpus / NOME_PDF)
    rodada = _montar(tmp_path, [("a", NOME_PDF, sha, [])])
    manifesto = json.loads((rodada / "rodada.json").read_text("utf-8"))
    manifesto["pdfs"][0]["pdf_id"] = "../../fuga"
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    saida = tmp_path / "x" / "saida"
    relatorio = residuos.medir_residuos(rodada, saida, recortes=True)
    assert relatorio["folhas"][0]["total"] is None
    assert not list(tmp_path.rglob("*fuga*.png"))


# --- página girada -----------------------------------------------------------------------


def _rodada_girada(raiz: Path, rotacao: int) -> tuple[Path, pymupdf.Rect]:
    corpus = raiz / "corpus"
    corpus.mkdir()
    sha = _pdf(corpus / NOME_PDF, rotacao=rotacao)
    with pymupdf.open(corpus / NOME_PDF) as documento:
        pagina = documento[0]
        visual = pymupdf.Rect(100, 100, 130, 130) * pagina.rotation_matrix
        largura, altura = pagina.rect.width, pagina.rect.height
    visual.normalize()
    centro = ((visual.x0 + visual.x1) / 2 / largura, (visual.y0 + visual.y1) / 2 / altura)
    simbolo = {
        "id": "S1",
        "classe": "ATERRAMENTO",
        "bbox": [centro[0] - 0.01, centro[1] - 0.01, centro[0] + 0.01, centro[1] + 0.01],
    }
    rodada = _montar(raiz, [("a", NOME_PDF, sha, [simbolo])])
    esperado = pymupdf.Rect(
        visual.x0 / largura, visual.y0 / altura, visual.x1 / largura, visual.y1 / altura
    )
    return rodada, esperado


@pytest.mark.parametrize("rotacao", [90, 180, 270])
def test_pagina_girada_caixa_normalizada_na_pagina_exibida(tmp_path: Path, rotacao: int) -> None:
    rodada, esperado = _rodada_girada(tmp_path, rotacao)
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    pagina = _folha(relatorio, "a")["paginas"][0]
    assert pagina["estado"] == "medida"
    assert len(pagina["residuos"]) == 1
    caixa = pagina["residuos"][0]["caixa_normalizada"]
    assert caixa == pytest.approx([esperado.x0, esperado.y0, esperado.x1, esperado.y1], abs=1e-3)


@pytest.mark.parametrize("rotacao", [90, 180, 270])
def test_pagina_girada_cruza_com_referencia_exibida(tmp_path: Path, rotacao: int) -> None:
    rodada, _ = _rodada_girada(tmp_path, rotacao)
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    pagina = _folha(relatorio, "a")["paginas"][0]
    assert pagina["residuos"][0]["referencias_sob"] == ["ATERRAMENTO"]
    assert pagina["referencias_sob_imagem"] == [{"id": "S1", "classe": "ATERRAMENTO"}]


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
def test_recorte_de_pagina_girada_mostra_a_imagem(tmp_path: Path, rotacao: int) -> None:
    rodada, _ = _rodada_girada(tmp_path, rotacao)
    saida = tmp_path / "saida"
    relatorio = residuos.medir_residuos(rodada, saida, recortes=True, dpi=100)
    nome = _folha(relatorio, "a")["paginas"][0]["residuos"][0]["recorte"]
    pixmap = pymupdf.Pixmap(str(saida / nome))
    assert pixmap.width > 0 and pixmap.height > 0
    # 30x30 pt a 100 dpi ~ 42 px, quadrado e preenchido com a cor da imagem
    assert abs(pixmap.width - 42) <= 3 and abs(pixmap.height - 42) <= 3
    centro = pixmap.pixel(pixmap.width // 2, pixmap.height // 2)
    assert tuple(centro[:3]) == COR_IMAGEM


# --- fora do domínio ---------------------------------------------------------------------


def test_fonte_gramatica_falhou_vira_fora_dominio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sha = _pdf(corpus / NOME_PDF)
    rodada = _montar(tmp_path, [("a", NOME_PDF, sha, [])])

    def falha(*_: Any, **__: Any) -> Any:
        raise FonteGramaticaFalhou("modelo.texto_falhou")

    monkeypatch.setattr(residuos, "casar_variantes", falha)
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folha = _folha(relatorio, "a")
    assert folha["total"] is None
    pagina = folha["paginas"][0]
    assert pagina["estado"] == "fora_dominio"
    assert "modelo.texto_falhou" in pagina["motivo"]
    assert pagina["residuos"] == []


def test_uma_pagina_fora_dominio_anula_o_total_da_folha_e_preserva_a_medida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sha = _pdf(corpus / NOME_PDF, paginas=2)
    rodada = _montar(tmp_path, [("a", NOME_PDF, sha, [])])
    original = residuos.casar_variantes
    chamadas = {"n": 0}

    def primeira_falha(*args: Any, **kwargs: Any) -> Any:
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise FonteGramaticaFalhou("modelo.caminhos_falhou")
        return original(*args, **kwargs)

    monkeypatch.setattr(residuos, "casar_variantes", primeira_falha)
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folha = _folha(relatorio, "a")
    assert [p["estado"] for p in folha["paginas"]] == ["fora_dominio", "medida"]
    assert folha["total"] is None
    assert len(folha["paginas"][1]["residuos"]) == 1
    resumo = relatorio["resumo"]
    assert resumo["folhas_medidas"] == 0
    assert resumo["folhas_fora_dominio"] == 1
    assert resumo["residuos"] == 0
    assert resumo["por_hash"] == {}
    assert resumo["sobre_referencia"] == 0


def test_resumo_coerente_com_as_folhas_em_rodada_mista(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sha_a = _pdf(corpus / "a.pdf", imagens=3)
    sha_b = _pdf(corpus / "b.pdf", imagens=1)
    (corpus / "c.pdf").write_bytes(b"lixo")
    rodada = _montar(
        tmp_path,
        [("a", "a.pdf", sha_a, []), ("b", "b.pdf", sha_b, []), ("c", "c.pdf", "0" * 64, [])],
    )
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folhas = relatorio["folhas"]
    resumo = relatorio["resumo"]
    medidas = [f for f in folhas if f["total"] is not None]
    assert resumo["folhas_medidas"] == len(medidas) == 2
    assert resumo["folhas_fora_dominio"] == len(folhas) - len(medidas) == 1
    assert resumo["residuos"] == sum(f["total"] for f in medidas) == 4
    hashes = {r["sha256_curto"] for f in medidas for p in f["paginas"] for r in p["residuos"]}
    assert set(resumo["por_hash"]) == hashes
    for chave, contagem in resumo["por_hash"].items():
        donas = [
            f["pdf_id"]
            for f in medidas
            if any(r["sha256_curto"] == chave for p in f["paginas"] for r in p["residuos"])
        ]
        assert contagem == len(donas)


def test_mesmo_hash_na_mesma_folha_conta_uma_folha_em_por_hash(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    documento = pymupdf.open()
    pagina = documento.new_page(width=LARGURA, height=ALTURA)
    _imagem(pagina, (100, 100, 130, 130), 77)
    _imagem(pagina, (200, 100, 230, 130), 77)
    sha = _salvar(documento, corpus / "a.pdf")
    rodada = _montar(tmp_path, [("a", "a.pdf", sha, [])])
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    assert relatorio["resumo"]["residuos"] == 2
    assert list(relatorio["resumo"]["por_hash"].values()) == [1]


# --- determinismo e recortes -------------------------------------------------------------


def test_processos_tres_folhas_com_falha_e_recortes_sao_deterministicos(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sha_a = _pdf(corpus / "a.pdf", imagens=2)
    sha_b = _pdf(corpus / "b.pdf", rotacao=90, imagens=1)
    (corpus / "c.pdf").write_bytes(b"lixo")
    rodada = _montar(
        tmp_path,
        [("a", "a.pdf", sha_a, []), ("b", "b.pdf", sha_b, []), ("c", "c.pdf", "0" * 64, [])],
    )
    um = residuos.medir_residuos(rodada, tmp_path / "um", recortes=True, processos=1)
    tres = residuos.medir_residuos(rodada, tmp_path / "tres", recortes=True, processos=3)
    assert um == tres
    assert [f["pdf_id"] for f in tres["folhas"]] == ["a", "b", "c"]
    assert (tmp_path / "um" / "residuos-raster.json").read_bytes() == (
        tmp_path / "tres" / "residuos-raster.json"
    ).read_bytes()
    nomes_um = sorted(p.name for p in (tmp_path / "um").glob("*.png"))
    nomes_tres = sorted(p.name for p in (tmp_path / "tres").glob("*.png"))
    assert nomes_um == nomes_tres
    assert len(nomes_um) == 3


def test_recortes_nao_vazam_nome_do_pdf_nos_arquivos_nem_no_json(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sha = _pdf(corpus / NOME_PDF, imagens=2)
    rodada = _montar(tmp_path, [("a", NOME_PDF, sha, [])])
    saida = tmp_path / "saida"
    residuos.medir_residuos(rodada, saida, recortes=True)
    assert all(Path(NOME_PDF).stem not in p.name for p in saida.iterdir())
    assert all(NOME_PDF.encode() not in p.read_bytes() for p in saida.glob("*.json"))
    assert all(NOME_PDF.encode() not in p.read_bytes() for p in saida.glob("*.png"))


def test_folha_sem_referencia_json_e_medida_sem_cruzamento(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sha = _pdf(corpus / "a.pdf")
    rodada = _montar(tmp_path, [("a", "a.pdf", sha, [])])
    (rodada / "pdfs" / "a" / "ficha" / "referencia.json").unlink()
    relatorio = residuos.medir_residuos(rodada, tmp_path / "saida")
    folha = _folha(relatorio, "a")
    assert folha["total"] == 1
    assert folha["paginas"][0]["residuos"][0]["referencias_sob"] == []
