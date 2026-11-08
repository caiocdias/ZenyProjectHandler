"""Gramática `split_triangle` (TRANSFORMADOR): grupos, negativos, caixa, contexto, gasto e E05."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.rect_diagonal import pagina_desenhada
from tests.fixtures.symbol_grammars.triangulo import (
    CASOS_TRIANGULO,
    CENTRO,
    GRUPO_DA_VARIANTE,
    GRUPOS,
    LADO,
    NEGATIVOS,
    PRETO,
    VERMELHO_ESCURO,
    Grupo,
    bracos_x,
    caminhos_trafo,
    desenhar_grupo,
    desenhar_trafo,
    desenhar_trafo_e05,
    pagina_com_texto,
    pagina_delta_de_glifo,
    ponta_da_haste,
    raio_envolvente,
    variantes_do_grupo,
    vertices,
)
from tests.unit.test_guarda_fonte_estendida_testador import (
    _violacoes_de_bytes_e_inteiros,
    _violacoes_de_comentarios,
)
from tests.unit.test_symbol_packages_sem_memorizacao import _violacoes_de_fonte

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import MarcasDaPagina
from zeny_project_handler.adapters.analysis.drawing_model.grammar_triangulo import (
    casa_triangulos,
    triangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
    gasto_por_fase,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas
from zeny_project_handler.adapters.analysis.pymupdf_transformers import observar_transformadores

_EPSILON: Final = 1e-3  # PyMuPDF devolve coordenadas em float32
_GRUPOS_ENVOLVENTE: Final = [g for g in GRUPOS if g[1] == "ellipse"]
_GRUPOS_MEIO_CIANO: Final = [g for g in GRUPOS if g[0] == "half_cyan"]
_BASE_CONTORNO: Final[Grupo] = ("outline", "none", False)
_RAIZ: Final = Path(__file__).resolve().parents[2]
_ARQUIVOS_NOVOS: Final = (
    _RAIZ
    / "src"
    / "zeny_project_handler"
    / "adapters"
    / "analysis"
    / "drawing_model"
    / "grammar_triangulo.py",
    _RAIZ / "tests" / "fixtures" / "symbol_grammars" / "triangulo.py",
    _RAIZ / "tests" / "unit" / "test_grammar_triangulo.py",
)


def _id_grupo(grupo: Grupo) -> str:
    return f"{grupo[0]}-{grupo[1]}-{'x' if grupo[2] else 'sem_x'}"


def _pares(
    casos: tuple[tuple[str, dict[str, Any]], ...] = CASOS_TRIANGULO,
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        (
            {"family_id": "autoral"},
            {"id": variante, "recognition": {"status": "enabled", "grammar": gramatica}},
        )
        for variante, gramatica in casos
    ]


def _casamentos(pagina: PaginaGramatica) -> tuple[CasamentoGramatica, ...]:
    return casar_variantes(pagina, _pares())


def _variantes(pagina: PaginaGramatica) -> set[str]:
    return {str(c.variante["id"]) for c in _casamentos(pagina)}


def _desenhada(desenhar: Callable[[pymupdf.Page], object]) -> set[str]:
    return _variantes(pagina_desenhada(desenhar))


def _um_por_caixa(pagina: PaginaGramatica) -> CasamentoGramatica:
    """O casamento do único desenho da página: todas as variantes casam a mesma caixa."""
    casamentos = _casamentos(pagina)
    assert len({(c.caixa, c.caminho, c.componentes) for c in casamentos}) == 1
    return casamentos[0]


def _contem(caixa: Caixa, ponto: Ponto) -> bool:
    return (
        caixa[0] - _EPSILON <= ponto[0] <= caixa[2] + _EPSILON
        and caixa[1] - _EPSILON <= ponto[1] <= caixa[3] + _EPSILON
    )


# Positivos -------------------------------------------------------------------------------------


@pytest.mark.parametrize("graus", [0.0, 30.0, 90.0], ids=["0", "30", "90"])
@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_positivo_casa_so_o_grupo_certo(grupo: Grupo, graus: float) -> None:
    assert _desenhada(lambda p: desenhar_grupo(p, grupo, graus)) == variantes_do_grupo(grupo)


@pytest.mark.parametrize("graus", [0.0, 30.0], ids=["0", "30"])
@pytest.mark.parametrize("grupo", _GRUPOS_MEIO_CIANO, ids=_id_grupo)
def test_meio_ciano_de_dois_preenchimentos_sem_traco_casa(grupo: Grupo, graus: float) -> None:
    def desenhar(p: pymupdf.Page) -> None:
        desenhar_grupo(p, grupo, graus, metades="sem_traco")

    assert _desenhada(desenhar) == variantes_do_grupo(grupo)


@pytest.mark.parametrize("graus", [0.0, 30.0], ids=["0", "30"])
@pytest.mark.parametrize("grupo", _GRUPOS_MEIO_CIANO, ids=_id_grupo)
def test_meio_ciano_em_hachura_e_lido_pela_envoltoria(grupo: Grupo, graus: float) -> None:
    """Cada metade num preenchimento de duas fatias triangulares: a envoltória é a metade."""

    def desenhar(p: pymupdf.Page) -> None:
        desenhar_grupo(p, grupo, graus, metades="hachura")

    assert _desenhada(desenhar) == variantes_do_grupo(grupo)


@pytest.mark.parametrize("grupo", _GRUPOS_MEIO_CIANO, ids=_id_grupo)
def test_hachura_que_nao_cobre_a_metade_nao_e_meio_ciano(grupo: Grupo) -> None:
    """As fatias ciano não somam a área da envoltória: sobra o contorno, no grupo `outline`."""

    def desenhar(p: pymupdf.Page) -> None:
        desenhar_grupo(p, grupo, metades="hachura_com_falha")

    assert _desenhada(desenhar) == variantes_do_grupo(("outline", grupo[1], grupo[2]))


@pytest.mark.parametrize("contorno", ["lados", "mediana"])
@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_contorno_de_lados_soltos_ou_com_mediana_casa(grupo: Grupo, contorno: str) -> None:
    """Três traços soltos (a polilinha fechada do modelo) ou a mediana no caminho do contorno."""
    assert _desenhada(lambda p: desenhar_grupo(p, grupo, contorno=contorno)) == (
        variantes_do_grupo(grupo)
    )


@pytest.mark.parametrize("graus", [0.0, 30.0], ids=["0", "30"])
@pytest.mark.parametrize("forma", ["retas", "circulo", "elipse"])
@pytest.mark.parametrize("grupo", _GRUPOS_ENVOLVENTE, ids=_id_grupo)
def test_envolvente_de_cada_forma_casa(grupo: Grupo, forma: str, graus: float) -> None:
    def desenhar(p: pymupdf.Page) -> None:
        desenhar_grupo(p, grupo, graus, forma_envolvente=forma)

    assert _desenhada(desenhar) == variantes_do_grupo(grupo)


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_ligado_por_haste_a_uma_linha_casa_o_mesmo_grupo(grupo: Grupo) -> None:
    assert _desenhada(lambda p: desenhar_grupo(p, grupo, linha_de_rede=True)) == (
        variantes_do_grupo(grupo)
    )


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_sem_haste_casa_o_mesmo_grupo(grupo: Grupo) -> None:
    """A haste de ligação não é exigida (R-E06.3.3.2.2-3)."""
    assert _desenhada(lambda p: desenhar_grupo(p, grupo, haste=False)) == variantes_do_grupo(grupo)


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_pagina_com_rotate_90_casa_o_mesmo_grupo_na_pagina_exibida(grupo: Grupo) -> None:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=200)
        desenhar_trafo(
            pagina,
            grupo[0],
            centro=(100.0, 80.0),
            envolvente=grupo[1] == "ellipse",
            x=grupo[2],
        )
        pagina.set_rotation(90)
        matriz = pagina.rotation_matrix
        exibida = pagina_para_gramaticas(pagina, 0)

    assert _variantes(exibida) == variantes_do_grupo(grupo)
    caixa = _um_por_caixa(exibida).caixa
    for x, y in vertices((100.0, 80.0)):
        exibido = (matriz.a * x + matriz.c * y + matriz.e, matriz.b * x + matriz.d * y + matriz.f)
        assert _contem(caixa, exibido)


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_pagina_de_texto_em_glifo_casa_o_mesmo_grupo(grupo: Grupo) -> None:
    pagina = pagina_com_texto(caminhos_trafo(grupo, CENTRO, LADO), "glifo")

    assert _variantes(pagina) == variantes_do_grupo(grupo)


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_simbolo_pequeno_so_casa_na_pagina_de_texto_em_glifo(grupo: Grupo) -> None:
    """Lado de 2,4 pt: abaixo do mínimo absoluto de 3 pt, acima do de glifo, 1,5 pt."""
    caminhos = caminhos_trafo(grupo, CENTRO, 2.4)

    assert _variantes(pagina_com_texto(caminhos, "glifo")) == variantes_do_grupo(grupo)
    assert _variantes(pagina_com_texto(caminhos, "nativo")) == set()
    assert _variantes(pagina_com_texto(caminhos, "shx")) == set()
    assert _variantes(pagina_com_texto(caminhos, None)) == set()


@pytest.mark.parametrize("fill", ["half_cyan", "outline"])
def test_x_vence_a_envolvente(fill: str) -> None:
    """Com envolvente e X no mesmo desenho, sai o grupo do X, como no E05 (ruling do lab)."""

    def desenhar(p: pymupdf.Page) -> None:
        desenhar_trafo(p, fill, envolvente=True, x=True)

    assert _desenhada(desenhar) == variantes_do_grupo((fill, "none", True))


def test_metade_de_outra_cor_que_nao_ciano_e_contorno() -> None:
    """A metade cheia vermelho-escura não é `half_cyan`: o desenho é `outline`, como no E05."""

    def desenhar(p: pymupdf.Page) -> None:
        desenhar_trafo(p, "half_cyan", cor_da_metade=VERMELHO_ESCURO)

    assert _desenhada(desenhar) == variantes_do_grupo(_BASE_CONTORNO)


def test_dois_desenhos_na_mesma_pagina_casam_cada_um_o_seu_grupo() -> None:
    def desenhar(p: pymupdf.Page) -> None:
        desenhar_trafo(p, "half_cyan", centro=(60.0, 60.0), x=True)
        desenhar_trafo(p, "outline", centro=(200.0, 200.0), graus=30.0, envolvente=True)

    esperadas = variantes_do_grupo(("half_cyan", "none", True)) | variantes_do_grupo(
        ("outline", "ellipse", False)
    )
    assert _desenhada(desenhar) == esperadas


# Negativos -------------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", sorted(NEGATIVOS))
def test_negativo_nao_casa(nome: str) -> None:
    assert _desenhada(NEGATIVOS[nome]) == set()


def test_delta_de_glifo_nao_casa() -> None:
    assert _variantes(pagina_delta_de_glifo(lido=True)) == set()
    # O mesmo contorno, quando não virou texto, é um triângulo de contorno: o negativo é o glifo.
    assert _variantes(pagina_delta_de_glifo(lido=False)) == variantes_do_grupo(_BASE_CONTORNO)


def test_pagina_sem_desenho_nao_casa() -> None:
    assert _desenhada(lambda p: None) == set()


def _seta_vazada_em_linha(lados_da_linha: float) -> Callable[[pymupdf.Page], object]:
    """Contorno de lado `LADO / 2` com uma linha de `lados_da_linha` lados que termina no meio da
    base e segue para fora."""

    def desenhar(p: pymupdf.Page) -> None:
        lado = LADO / 2
        a, b, c = vertices(lado=lado)
        meio = ((b[0] + c[0]) / 2, (b[1] + c[1]) / 2)
        dx, dy = meio[0] - a[0], meio[1] - a[1]
        norma = math.hypot(dx, dy)
        longe = (
            meio[0] + dx / norma * lados_da_linha * lado,
            meio[1] + dy / norma * lados_da_linha * lado,
        )
        p.draw_line(longe, meio, color=PRETO, width=0.14)
        p.draw_polyline([a, b, c, a], color=PRETO, width=0.14, closePath=True)

    return desenhar


@pytest.mark.parametrize(
    ("lados_da_linha", "casa"), [(1.5, True), (2.5, False)], ids=["1_5_lado", "2_5_lados"]
)
def test_seta_vazada_so_com_linha_de_dois_lados_ou_mais(lados_da_linha: float, casa: bool) -> None:
    """Ruling da rodada 3: a linha curta (como a haste de um vizinho, de cerca de 1 lado) não faz
    seta; a de 2 lados ou mais, sim."""
    esperadas = variantes_do_grupo(_BASE_CONTORNO) if casa else set()

    assert _desenhada(_seta_vazada_em_linha(lados_da_linha)) == esperadas


def test_pictograma_maior_que_max_span_nao_casa() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_trafo(p, "outline"))
    gramatica = dict(CASOS_TRIANGULO)["cemig-eo-r3-s18-v007"]
    estreita = {**gramatica, "max_span": LADO - 0.5}
    larga = {**gramatica, "max_span": LADO + 0.5}

    assert casa_triangulos(contexto_gramaticas(pagina), estreita) == []
    assert len(casa_triangulos(contexto_gramaticas(pagina), larga)) == 1


# Caixa e componentes ---------------------------------------------------------------------------


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_caixa_e_o_pictograma(grupo: Grupo) -> None:
    casamento = _um_por_caixa(pagina_desenhada(lambda p: desenhar_grupo(p, grupo)))
    caixa = casamento.caixa
    if grupo[1] == "ellipse":
        raio = raio_envolvente()
        esperada = (CENTRO[0] - raio, CENTRO[1] - raio, CENTRO[0] + raio, CENTRO[1] + raio)
    else:
        pontos = vertices()
        esperada = (
            min(p[0] for p in pontos),
            min(p[1] for p in pontos),
            max(p[0] for p in pontos),
            max(p[1] for p in pontos),
        )
    assert caixa == pytest.approx(esperada, abs=0.05)
    assert not _contem(caixa, ponta_da_haste())
    if grupo[2]:
        assert not any(_contem(caixa, p) for braco in bracos_x() for p in braco)


@pytest.mark.parametrize(
    ("grupo", "esperados"),
    [
        (("half_cyan", "ellipse", False), (1, 2, 3, 4)),
        (("half_cyan", "none", False), (1, 2, 3)),
        (("half_cyan", "none", True), (1, 2, 3, 4, 5)),
        (("outline", "ellipse", False), (1, 2)),
        (("outline", "none", False), (1,)),
        (("outline", "none", True), (1, 2, 3)),
    ],
    ids=lambda v: _id_grupo(v) if isinstance(v, tuple) and isinstance(v[0], str) else None,
)
def test_componentes(grupo: Grupo, esperados: tuple[int, ...]) -> None:
    """Ordem do desenho: contorno (0, a âncora), metades, haste, envolvente e braços do X."""
    casamento = _um_por_caixa(pagina_desenhada(lambda p: desenhar_grupo(p, grupo)))

    assert casamento.caminho == 0
    assert casamento.componentes == esperados


# Contexto e gasto ------------------------------------------------------------------------------


def test_marcas_de_outro_contexto_recusa() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_trafo(p, "outline"))

    with pytest.raises(ValueError, match="outro contexto"):
        triangulos_candidatos(
            contexto_gramaticas(pagina), marcas=MarcasDaPagina(contexto_gramaticas(pagina))
        )


def test_candidatos_de_outro_contexto_recusa() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_trafo(p, "outline"))
    candidatos = triangulos_candidatos(contexto_gramaticas(pagina))
    assert candidatos

    with pytest.raises(ValueError, match="outro contexto"):
        casa_triangulos(contexto_gramaticas(pagina), CASOS_TRIANGULO[0][1], candidatos=candidatos)


def test_casa_triangulos_so_filtra_sem_gastar() -> None:
    pagina = pagina_desenhada(lambda p: desenhar_trafo(p, "half_cyan", x=True))
    contexto = contexto_gramaticas(pagina)
    candidatos = triangulos_candidatos(contexto)
    antes = contexto.orcamento.gasto

    for _, gramatica in CASOS_TRIANGULO:
        casa_triangulos(contexto, gramatica, candidatos=candidatos)

    assert contexto.orcamento.gasto == antes


def test_classificacao_uma_vez_por_candidato() -> None:
    """As 15 variantes custam o mesmo que as 6 formas, uma por grupo (R-E06.3.3.2.2-6)."""

    def desenhar(p: pymupdf.Page) -> None:
        for i, grupo in enumerate(GRUPOS):
            desenhar_trafo(
                p,
                grupo[0],
                centro=(40.0 + 45.0 * i, 150.0),
                envolvente=grupo[1] == "ellipse",
                x=grupo[2],
            )

    pagina = pagina_desenhada(desenhar)
    gramaticas = dict(CASOS_TRIANGULO)
    um_por_grupo = tuple(
        (variante, gramaticas[variante])
        for variante in (min(variantes_do_grupo(grupo)) for grupo in GRUPOS)
    )
    assert len(_casamentos(pagina)) == len(CASOS_TRIANGULO)
    assert gasto_por_fase(pagina, _pares()) == gasto_por_fase(pagina, _pares(um_por_grupo))


# E05 (R-E06.3.3.2.2-5) -------------------------------------------------------------------------


def _observacoes_e05(grupo: Grupo) -> list[set[str]]:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        desenhar_trafo_e05(pagina, grupo)
        resultado = observar_transformadores(
            pagina, documento_id="autoral", documento_sha256="0" * 64, pagina_numero=1
        )
    return [
        set(json.loads(str(dict(o.atributos)["referencias_possiveis"])))
        for o in resultado.observacoes
        if o.alternativas[0].classe == "TRANSFORMADOR"
    ]


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_trafo_e05_e_observado_pelo_e05_no_mesmo_grupo(grupo: Grupo) -> None:
    """Uma observação do E05, cujas referências contêm as do grupo. Sem marcador, o E05 não
    estreita: o base dá todas as variantes do mesmo `fill` (`_referencias_triangulo`)."""
    if grupo[1] == "none" and not grupo[2]:
        esperadas = {v for v, g in GRUPO_DA_VARIANTE.items() if g[0] == grupo[0]}
    else:
        esperadas = variantes_do_grupo(grupo)

    assert _observacoes_e05(grupo) == [esperadas]


@pytest.mark.parametrize("grupo", GRUPOS, ids=_id_grupo)
def test_trafo_e05_casa_a_gramatica_nova(grupo: Grupo) -> None:
    pagina = pagina_desenhada(lambda p: desenhar_trafo_e05(p, grupo))

    assert _variantes(pagina) == variantes_do_grupo(grupo)


# Guarda de fonte -------------------------------------------------------------------------------


@pytest.mark.parametrize("arquivo", _ARQUIVOS_NOVOS, ids=lambda a: a.name)
def test_arquivos_novos_passam_na_guarda_de_fonte(arquivo: Path) -> None:
    """A guarda de `_GRAMATICAS_NOVAS` (fonte, comentários, bytes e inteiros) nos arquivos novos."""
    fonte = arquivo.read_text(encoding="utf-8")

    assert _violacoes_de_fonte(fonte, arquivo.name) == []
    assert _violacoes_de_comentarios(fonte, arquivo.name) == []
    assert _violacoes_de_bytes_e_inteiros(fonte, arquivo.name) == []
