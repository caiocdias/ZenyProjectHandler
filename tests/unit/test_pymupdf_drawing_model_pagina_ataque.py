# mypy: disable-error-code="no-untyped-call"
"""Ataque à página do modelo com índice cru: clip/group aninhados, descartes, rotação e cropbox.

O índice cru de `caminhos[i]` é a posição em `get_drawings(extended=True)`, que traz também
`clip` e `group`. Os oráculos aqui não repetem a implementação: a lista crua é lida de novo pela
própria PyMuPDF e a geometria da página girada/recortada vem da especificação do PDF.
"""

from __future__ import annotations

import gc
import json
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis.drawing_model.cache import (
    JsonDrawingModelCache,
    chave_modelo_desenho,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    VERSAO_MODELO_DESENHO,
    Caminho,
    Ponto,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    caminhos_da_pagina,
    caminhos_e_total_da_pagina,
    extrair_modelo_desenho,
    obter_modelo_desenho,
    pagina_modelo_com_indices,
)

_TOLERANCIA = 1e-3
_TIPOS_DE_CAMINHO = {"s", "f", "fs"}
_LINHAS = (
    LinhaTexto("P7 U4(1) S1N", (40.0, 60.0), 5.0),
    LinhaTexto("11-300", (40.0, 120.0), 5.0),
)

# Traços, recortes aninhados (q/W n/Q) e um Form XObject com grupo de transparência que tem
# o seu próprio recorte e traços dentro: clip e group aparecem entre os caminhos, em vários níveis.
_FORM_COM_GRUPO = (
    b"0 0 1 RG 3 w 150 150 m 190 190 l S\n160 160 20 20 re W n 1 0 0 rg 165 165 5 5 re f\n"
)
_CONTEUDO_ANINHADO = (
    b"1 0 0 RG 10 10 m 50 10 l S\n"
    b"q 0 0 100 100 re W n 20 20 m 60 60 l S\n"
    b"q 10 10 50 50 re W n 0 1 0 rg 30 30 10 10 re f Q\n"
    b"25 25 m 70 25 l S Q\n"
    b"q /Fm0 Do Q\n"
    b"200 200 m 250 250 l S\n"
)


def _pdf_bruto(
    destino: Path,
    conteudo: bytes,
    *,
    form: bytes | None = None,
    rotacao: int = 0,
    cropbox: pymupdf.Rect | None = None,
) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        if form is not None:
            xref_form = documento.get_new_xref()
            documento.update_object(
                xref_form,
                "<</Type/XObject/Subtype/Form/BBox[0 0 300 300]"
                "/Group<</S/Transparency>>/Resources<<>>>>",
            )
            documento.update_stream(xref_form, form)
            documento.xref_set_key(
                pagina.xref, "Resources", f"<</XObject<</Fm0 {xref_form} 0 R>>>>"
            )
        xref_conteudo = documento.get_new_xref()
        documento.update_object(xref_conteudo, "<<>>")
        documento.update_stream(xref_conteudo, conteudo)
        pagina.set_contents(xref_conteudo)
        if cropbox is not None:
            pagina.set_cropbox(cropbox)
        pagina.set_rotation(rotacao)
        documento.save(destino)
    return destino


def _pdf_aninhado(destino: Path, **opcoes: Any) -> Path:
    return _pdf_bruto(destino, _CONTEUDO_ANINHADO, form=_FORM_COM_GRUPO, **opcoes)


def _pontos_crus(desenho: dict[str, Any], matriz: pymupdf.Matrix) -> list[Ponto]:
    pontos: list[pymupdf.Point] = []
    for item in desenho["items"]:
        if item[0] == "re":
            retangulo = pymupdf.Rect(item[1])
            pontos += [retangulo.tl, retangulo.tr, retangulo.br, retangulo.bl]
        elif item[0] == "qu":
            quadrilatero = pymupdf.Quad(item[1])
            pontos += [quadrilatero.ul, quadrilatero.ur, quadrilatero.lr, quadrilatero.ll]
        else:
            pontos += [pymupdf.Point(p) for p in item[1:]]
    return [
        (p.x * matriz.a + p.y * matriz.c + matriz.e, p.x * matriz.b + p.y * matriz.d + matriz.f)
        for p in pontos
    ]


def _pontos_do_caminho(caminho: Caminho) -> list[Ponto]:
    return [p for subcaminho in caminho.subcaminhos for item in subcaminho for p in item.pontos]


def _cobre(a: list[Ponto], b: list[Ponto]) -> bool:
    return all(
        any(abs(x - u) < _TOLERANCIA and abs(y - v) < _TOLERANCIA for u, v in b) for x, y in a
    )


def _confere_origem(
    caminhos: tuple[Caminho, ...],
    indices: tuple[int, ...],
    crus: list[dict[str, Any]],
    matriz: pymupdf.Matrix,
) -> None:
    """Cada caminho tem exatamente os pontos (e o estilo) do desenho cru que o índice aponta."""
    assert len(indices) == len(caminhos)
    assert all(type(i) is int for i in indices)
    assert list(indices) == sorted(set(indices)), "índices crus crescem e não se repetem"
    for caminho, indice in zip(caminhos, indices, strict=True):
        desenho = crus[indice]
        assert desenho["type"] in _TIPOS_DE_CAMINHO
        esperados = _pontos_crus(desenho, matriz)
        obtidos = _pontos_do_caminho(caminho)
        assert _cobre(esperados, obtidos)
        assert _cobre(obtidos, esperados)
        assert caminho.estilo.espessura == pytest.approx(float(desenho.get("width") or 0.0))


def _posicoes_de_caminho(crus: list[dict[str, Any]]) -> list[int]:
    return [i for i, desenho in enumerate(crus) if desenho.get("type") in _TIPOS_DE_CAMINHO]


# --- clip e group intercalados e aninhados -------------------------------------------------


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
def test_indices_com_clip_e_group_aninhados_sao_as_posicoes_exatas_dos_tracos(
    tmp_path: Path, rotacao: int
) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf", rotacao=rotacao)

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        crus = pagina.get_drawings(extended=True)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
        matriz = pagina.rotation_matrix

    tipos = [desenho["type"] for desenho in crus]
    assert "group" in tipos
    assert tipos.count("clip") >= 3
    assert max(desenho.get("level", 0) for desenho in crus) >= 2, "precisa haver aninhamento"
    assert len(modelo.caminhos) == len(_posicoes_de_caminho(crus)) == 7
    assert indices == tuple(_posicoes_de_caminho(crus))
    _confere_origem(modelo.caminhos, indices, crus, matriz)


def test_desenhos_identicos_separados_por_clip_recebem_indices_distintos(tmp_path: Path) -> None:
    conteudo = (
        b"1 0 0 RG 10 10 m 50 10 l S\n"
        b"q 0 0 100 100 re W n 10 10 m 50 10 l S Q\n"
        b"q 0 0 200 200 re W n q 0 0 90 90 re W n 10 10 m 50 10 l S Q Q\n"
        b"10 10 m 50 10 l S\n"
    )
    pdf = _pdf_bruto(tmp_path / "identicos.pdf", conteudo)

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        crus = pagina.get_drawings(extended=True)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)

    posicoes = _posicoes_de_caminho(crus)
    assert len(posicoes) == 4
    assert posicoes != list(range(4))
    assert indices == tuple(posicoes)
    assert len({caminho.subcaminhos for caminho in modelo.caminhos}) == 1, "geometria repetida"


def test_pagina_so_com_clip_nao_tem_caminho_nem_indice(tmp_path: Path) -> None:
    pdf = _pdf_bruto(tmp_path / "so-clip.pdf", b"q 0 0 100 100 re W n Q q 5 5 50 50 re W n Q\n")

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        crus = pagina.get_drawings(extended=True)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)

    assert crus and {desenho["type"] for desenho in crus} == {"clip"}
    assert indices == ()
    assert modelo.caminhos == ()
    assert modelo == extrair_modelo_desenho(pdf).paginas[0]


def test_muitos_tracos_com_clip_a_cada_tres_mantem_a_correspondencia(tmp_path: Path) -> None:
    quantidade = 1500
    trechos = []
    for i in range(quantidade):
        x = 5 + (i % 250)
        y = 5 + (i // 250) * 10
        traco = f"{x} {y} m {x + 3} {y + 2} l S\n"
        trechos.append(f"q {x - 1} {y - 1} 10 10 re W n {traco}Q\n" if i % 3 == 0 else traco)
    pdf = _pdf_bruto(tmp_path / "muitos.pdf", "".join(trechos).encode("ascii"))

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        crus = pagina.get_drawings(extended=True)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
        matriz = pagina.rotation_matrix

    assert len(modelo.caminhos) == quantidade
    assert len(crus) > quantidade
    assert indices == tuple(_posicoes_de_caminho(crus))
    _confere_origem(modelo.caminhos, indices, crus, matriz)


# --- página girada e com CropBox deslocado -------------------------------------------------


def _girar(rotacao: int, ponto: Ponto, largura: float, altura: float) -> Ponto:
    """Ponto da página sem rotação (y para baixo) → página visual, pela especificação do PDF."""
    x, y = ponto
    return {
        0: (x, y),
        90: (altura - y, x),
        180: (largura - x, altura - y),
        270: (y, largura - x),
    }[rotacao]


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
def test_pagina_girada_e_com_cropbox_deslocado_tem_geometria_e_indice_corretos(
    tmp_path: Path, rotacao: int
) -> None:
    # CropBox em coordenadas PDF (y para cima): x 50..250, y 80..280 (200 x 200).
    conteudo = b"1 0 0 RG 100 100 m 150 120 l S\n"
    pdf = _pdf_bruto(
        tmp_path / "recorte.pdf", conteudo, rotacao=rotacao, cropbox=pymupdf.Rect(50, 20, 250, 220)
    )

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        crus = pagina.get_drawings(extended=True)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
        matriz = pagina.rotation_matrix

    # o recorte da CropBox entra como um `clip` na frente: o índice não é a ordem do caminho
    assert crus[0]["type"] == "clip"
    assert indices == (1,)
    (caminho,) = modelo.caminhos
    # (100,100)->(150,120) no PDF: sem rotação, y para baixo, origem no canto da CropBox
    esperados = [_girar(rotacao, p, 200.0, 200.0) for p in ((50.0, 180.0), (100.0, 160.0))]
    obtidos = _pontos_do_caminho(caminho)
    assert obtidos == pytest.approx(esperados, abs=_TOLERANCIA)
    assert (modelo.largura, modelo.altura) == (200.0, 200.0)
    _confere_origem(modelo.caminhos, indices, crus, matriz)


@pytest.mark.parametrize("rotacao", [90, 270])
def test_pagina_retangular_girada_troca_largura_e_altura_e_mantem_indices(
    tmp_path: Path, rotacao: int
) -> None:
    pdf = _pdf_bruto(
        tmp_path / "retangular.pdf",
        b"q 0 0 400 100 re W n 1 0 0 RG 10 10 m 300 90 l S Q 0 0 1 RG 20 20 m 40 40 l S\n",
        rotacao=rotacao,
    )
    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        # a página quadrada do helper vira retangular só pelo cropbox
        crus = pagina.get_drawings(extended=True)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
        matriz = pagina.rotation_matrix

    assert indices == tuple(_posicoes_de_caminho(crus))
    assert modelo == extrair_modelo_desenho(pdf).paginas[0]
    _confere_origem(modelo.caminhos, indices, crus, matriz)


# --- descartes: não finito, tipo fora de _TIPOS_CAMINHO, malformado --------------------------


def _ruim(tipo: Any, itens: Any, **extra: Any) -> dict[str, Any]:
    return {
        "type": tipo,
        "items": itens,
        "rect": pymupdf.Rect(0.0, 0.0, 1.0, 1.0),
        "fill": (0.0, 0.0, 0.0),
        "color": None,
        "width": 0.0,
        **extra,
    }


def _ponto(x: float, y: float) -> pymupdf.Point:
    return pymupdf.Point(x, y)


def _descartados() -> dict[str, dict[str, Any]]:
    nan, inf = float("nan"), float("inf")
    return {
        "nan": _ruim("f", [("l", _ponto(nan, 0.0), _ponto(1.0, 1.0))]),
        "inf": _ruim("s", [("l", _ponto(0.0, 0.0), _ponto(inf, 1.0))]),
        "bezier_curta": _ruim("s", [("c", _ponto(0.0, 0.0), _ponto(1.0, 1.0))]),
        "sem_itens": _ruim("fs", []),
        "so_operacao_desconhecida": _ruim("s", [("zz", _ponto(0.0, 0.0), _ponto(1.0, 1.0))]),
        "espessura_ilegivel": _ruim("s", [("l", _ponto(0.0, 0.0), _ponto(1.0, 1.0))], width="x"),
        "tipo_fora": _ruim("xx", [("l", _ponto(0.0, 0.0), _ponto(1.0, 1.0))]),
        "tipo_none": _ruim(None, [("l", _ponto(0.0, 0.0), _ponto(1.0, 1.0))]),
        "clip_falso": _ruim("clip", [("re", pymupdf.Rect(0, 0, 5, 5), 1)]),
        "group_falso": _ruim("group", []),
    }


def _injetar_em_get_drawings(
    monkeypatch: pytest.MonkeyPatch, extras: list[tuple[int, dict[str, Any]]]
) -> None:
    """Insere desenhos na lista crua; a posição é a da lista original (antes da inserção)."""
    original = pymupdf.Page.get_drawings

    def injetado(self: pymupdf.Page, *args: Any, **kwargs: Any) -> Any:
        lista = list(original(self, *args, **kwargs))
        for posicao, desenho in sorted(extras, key=lambda par: par[0], reverse=True):
            lista.insert(posicao, desenho)
        return lista

    monkeypatch.setattr(pymupdf.Page, "get_drawings", injetado)


@pytest.mark.parametrize("nome", sorted(_descartados()))
def test_desenho_descartado_nao_desloca_os_indices_dos_vizinhos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nome: str
) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf")
    ruim = _descartados()[nome]
    # início, meio (entre clips/traços) e fim da lista crua
    _injetar_em_get_drawings(monkeypatch, [(0, ruim), (3, dict(ruim)), (6, dict(ruim)), (99, ruim)])

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        crus = pagina.get_drawings(extended=True)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
        matriz = pagina.rotation_matrix

    assert len(crus) > 12
    por_tipo_ruim = [i for i, d in enumerate(crus) if d.get("items") is ruim["items"]]
    assert len(por_tipo_ruim) >= 3
    assert len(modelo.caminhos) == 7, "só os sete traços de verdade sobrevivem"
    assert not set(indices) & set(por_tipo_ruim)
    _confere_origem(modelo.caminhos, indices, crus, matriz)
    assert modelo == extrair_modelo_desenho(pdf).paginas[0]


def test_ordem_do_caminho_tem_lacunas_e_o_indice_cru_continua_certo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf")
    descartados = _descartados()
    _injetar_em_get_drawings(
        monkeypatch,
        [(1, descartados["nan"]), (2, descartados["tipo_fora"]), (5, descartados["sem_itens"])],
    )

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        crus = pagina.get_drawings(extended=True)
        modelo, indices = pagina_modelo_com_indices(pagina, 0)
        matriz = pagina.rotation_matrix

    ordens = [caminho.ordem for caminho in modelo.caminhos]
    assert ordens != list(range(len(ordens))), "um descartado entre filtrados abre lacuna na ordem"
    filtrados = [i for i, d in enumerate(crus) if d.get("type") in _TIPOS_DE_CAMINHO]
    assert indices == tuple(filtrados[ordem] for ordem in ordens)
    for caminho, indice in zip(modelo.caminhos, indices, strict=True):
        assert crus[indice]["type"] in _TIPOS_DE_CAMINHO
        assert crus[indice].get("items") is not _descartados()["nan"]["items"]
        assert _cobre(_pontos_crus(crus[indice], matriz), _pontos_do_caminho(caminho))


def test_todos_os_desenhos_descartados_devolve_indices_vazios(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_bruto(tmp_path / "vazio.pdf", b"q 0 0 10 10 re W n Q\n")
    _injetar_em_get_drawings(
        monkeypatch, [(0, _descartados()["nan"]), (1, _descartados()["tipo_fora"])]
    )

    with pymupdf.open(pdf) as documento:
        modelo, indices = pagina_modelo_com_indices(documento[0], 0)

    assert indices == ()
    assert modelo.caminhos == ()
    assert modelo == extrair_modelo_desenho(pdf).paginas[0]


# --- igualdade exata com a extração do documento -------------------------------------------


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-pagina"))


@pytest.mark.parametrize("rotacao", [0, 90])
def test_pagina_com_texto_de_glifo_e_tabela_e_igual_a_extracao(
    tmp_path: Path, tabela: TabelaGlifos, rotacao: int
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "glifos.pdf", _LINHAS, rotacao_pagina=rotacao)

    with pymupdf.open(pdf) as documento:
        modelo, indices = pagina_modelo_com_indices(documento[0], 0, tabela)
    com_tabela = extrair_modelo_desenho(pdf, tabela).paginas[0]

    assert modelo == com_tabela
    assert {texto.origem for texto in modelo.textos} == {"glifo"}
    assert sorted(texto.texto for texto in modelo.textos) == sorted(
        linha.texto for linha in _LINHAS
    )
    assert indices == tuple(range(len(modelo.caminhos))), "sem clip, índice cru é a ordem"


def test_sem_tabela_nao_le_texto_de_glifo_e_continua_igual_a_extracao(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "glifos.pdf", _LINHAS)

    with pymupdf.open(pdf) as documento:
        sem_tabela, _ = pagina_modelo_com_indices(documento[0], 0)
        com_tabela, _ = pagina_modelo_com_indices(documento[0], 0, tabela)

    assert sem_tabela == extrair_modelo_desenho(pdf).paginas[0]
    assert com_tabela == extrair_modelo_desenho(pdf, tabela).paginas[0]
    assert sem_tabela.textos == ()
    assert com_tabela.textos


def test_diagnosticos_de_glifo_com_desenho_descartado_sao_os_da_extracao(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "glifos.pdf", _LINHAS)
    _injetar_em_get_drawings(monkeypatch, [(3, _descartados()["nan"])])

    with pymupdf.open(pdf) as documento:
        modelo, indices = pagina_modelo_com_indices(documento[0], 0, tabela)
    extraido = extrair_modelo_desenho(pdf, tabela).paginas[0]

    assert modelo == extraido
    assert "modelo.glifos_desconhecidos" in modelo.diagnosticos
    assert 3 not in indices, "o descartado na posição crua 3 não tem caminho"
    assert indices[:3] == (0, 1, 2)
    assert indices[3] == 4


def test_falha_de_get_drawings_vira_diagnostico_e_indices_vazios(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf")

    def quebra(self: pymupdf.Page, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("get_drawings quebrou")

    monkeypatch.setattr(pymupdf.Page, "get_drawings", quebra)

    with pymupdf.open(pdf) as documento:
        modelo, indices = pagina_modelo_com_indices(documento[0], 0)

    assert indices == ()
    assert modelo.caminhos == ()
    assert "modelo.caminhos_falhou" in modelo.diagnosticos
    assert modelo == extrair_modelo_desenho(pdf).paginas[0]


def test_segunda_pagina_usa_os_proprios_indices_e_o_indice_recebido(tmp_path: Path) -> None:
    pdf = tmp_path / "duas.pdf"
    with pymupdf.open() as documento:
        documento.new_page(width=300, height=300).draw_line((1, 1), (2, 2))
        pagina = documento.new_page(width=300, height=300)
        pagina.draw_line((10, 10), (20, 20))
        pagina.draw_line((30, 30), (40, 40))
        documento.save(pdf)
    aninhado = _pdf_aninhado(tmp_path / "aninhado.pdf")
    with pymupdf.open(aninhado) as origem, pymupdf.open(pdf) as destino:
        destino.insert_pdf(origem)
        destino.save(tmp_path / "tres.pdf")

    tres = tmp_path / "tres.pdf"
    with pymupdf.open(tres) as documento:
        modelo, indices = pagina_modelo_com_indices(documento[2], 2)
        crus = documento[2].get_drawings(extended=True)

    assert modelo.indice == 2
    assert modelo == extrair_modelo_desenho(tres).paginas[2]
    assert indices == tuple(_posicoes_de_caminho(crus))
    assert len(indices) == 7


# --- get_drawings uma única vez -------------------------------------------------------------


def _contar_get_drawings(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    chamadas: list[bool] = []
    original = pymupdf.Page.get_drawings

    def contado(self: pymupdf.Page, *args: Any, **kwargs: Any) -> Any:
        chamadas.append(kwargs.get("extended", False))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_drawings", contado)
    return chamadas


def test_get_drawings_uma_vez_so_com_tabela_de_glifos_e_pagina_girada(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = pdf_texto_contorno(tmp_path / "glifos.pdf", _LINHAS, rotacao_pagina=90)
    chamadas = _contar_get_drawings(monkeypatch)

    with pymupdf.open(pdf) as documento:
        modelo, _ = pagina_modelo_com_indices(documento[0], 0, tabela)

    assert modelo.textos
    assert chamadas == [True]


def test_get_drawings_uma_vez_com_anotacao_de_aparencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = tmp_path / "anotada.pdf"
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        pagina.draw_line((10, 10), (100, 10))
        pagina.add_freetext_annot(pymupdf.Rect(50, 50, 200, 100), "NOTA")
        pagina.add_rect_annot(pymupdf.Rect(20, 120, 80, 160))
        documento.save(pdf)
    chamadas = _contar_get_drawings(monkeypatch)

    with pymupdf.open(pdf) as documento:
        pagina_modelo_com_indices(documento[0], 0)

    assert chamadas == [True]


def test_get_drawings_uma_vez_mesmo_quando_ele_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf")
    chamadas: list[bool] = []

    def quebra(self: pymupdf.Page, *args: Any, **kwargs: Any) -> Any:
        chamadas.append(True)
        raise RuntimeError("falhou")

    monkeypatch.setattr(pymupdf.Page, "get_drawings", quebra)

    with pymupdf.open(pdf) as documento:
        pagina_modelo_com_indices(documento[0], 0)

    assert chamadas == [True], "sem nova tentativa de leitura"


# --- consumidores atuais, cache e versão não mudam --------------------------------------------


def test_consumidores_atuais_de_caminhos_nao_veem_o_indice(tmp_path: Path) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf", rotacao=90)

    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        caminhos, total = caminhos_e_total_da_pagina(pagina)
        so_caminhos = caminhos_da_pagina(pagina)
        modelo, _ = pagina_modelo_com_indices(pagina, 0)
        crus = pagina.get_drawings(extended=True)

    assert type(caminhos) is tuple
    assert type(total) is int
    assert total == len(_posicoes_de_caminho(crus)) == 7
    assert caminhos == so_caminhos == modelo.caminhos
    assert [caminho.ordem for caminho in caminhos] == list(range(7))


def test_total_de_desenhos_conta_os_descartados_sem_contar_clip_nem_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf")
    descartados = _descartados()
    _injetar_em_get_drawings(
        monkeypatch,
        [
            (0, descartados["nan"]),
            (4, descartados["bezier_curta"]),
            (50, descartados["clip_falso"]),
        ],
    )

    with pymupdf.open(pdf) as documento:
        caminhos, total = caminhos_e_total_da_pagina(documento[0])

    assert len(caminhos) == 7
    assert total == 9


def test_cache_guarda_o_mesmo_modelo_e_a_versao_nao_muda(tmp_path: Path) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf")
    cache = JsonDrawingModelCache(tmp_path / "cache")

    primeiro = obter_modelo_desenho(pdf, cache)
    with pymupdf.open(pdf) as documento:
        pagina, _ = pagina_modelo_com_indices(documento[0], 0)
    depois = obter_modelo_desenho(pdf, cache)

    assert primeiro.versao == VERSAO_MODELO_DESENHO
    assert primeiro.paginas == (pagina,)
    assert depois == primeiro
    arquivos = list((tmp_path / "cache" / "modelo-desenho").glob("*.json"))
    assert len(arquivos) == 1
    gravado = json.loads(arquivos[0].read_text(encoding="utf-8"))
    assert gravado["modelo"]["versao"] == VERSAO_MODELO_DESENHO
    chave = chave_modelo_desenho(primeiro.documento_sha256, f"pymupdf-{pymupdf.VersionBind}")
    assert cache.obter(chave) == primeiro, "a chave do cache continua a de antes"


def test_chamar_a_pagina_nao_altera_o_modelo_extraido_depois(tmp_path: Path) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf")
    antes = extrair_modelo_desenho(pdf)

    with pymupdf.open(pdf) as documento:
        pagina_modelo_com_indices(documento[0], 0)
        pagina_modelo_com_indices(documento[0], 0)

    assert extrair_modelo_desenho(pdf) == antes


# --- ciclo de vida do documento ---------------------------------------------------------------


def test_resultado_vale_apos_fechar_o_documento_e_nao_deixa_recurso_aberto(
    tmp_path: Path,
) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf")
    with pymupdf.open(pdf) as documento:
        modelo, indices = pagina_modelo_com_indices(documento[0], 0)
    gc.collect()

    assert documento.is_closed
    assert modelo == extrair_modelo_desenho(pdf).paginas[0]
    assert all(type(i) is int for i in indices)
    pdf.unlink()  # no Windows, um arquivo ainda aberto não pode ser apagado
    gc.collect()


def test_documento_fecha_limpo_mesmo_quando_a_leitura_de_caminhos_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_aninhado(tmp_path / "aninhado.pdf")

    def quebra(self: pymupdf.Page, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("falhou")

    monkeypatch.setattr(pymupdf.Page, "get_drawings", quebra)
    with pymupdf.open(pdf) as documento:
        pagina_modelo_com_indices(documento[0], 0)
    gc.collect()

    assert documento.is_closed
    pdf.unlink()
