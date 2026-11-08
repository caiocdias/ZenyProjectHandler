"""Ataques às marcas compartilhadas: invariância da haste contra a base 706c8c9, pagamento único
dos contornos, bordas da envolvente, X com eixo girado e fronteira do módulo."""

from __future__ import annotations

import ast
import importlib
import math
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
)
from tests.fixtures.symbol_grammars.stem_bars import (
    ALTERNADAS,
    CASOS_HASTE,
    ESTRELA,
    HEXAGONO,
    NEGATIVOS,
    desenhar_haste,
    desenhar_positivo,
    pagina_desenhada,
)

from zeny_project_handler.adapters.analysis.drawing_model import grammar_marcas
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    MarcasDaPagina,
    envolvente,
    tem_x,
)
from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import hastes_candidatas
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Caminho, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    ContextoGramatica,
    PaginaGramatica,
    Segmento,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    casar_variantes,
    gasto_por_fase,
)

_CENTRO: Final[Ponto] = (100.0, 100.0)
_PICTOGRAMA: Final[Caixa] = (95.0, 95.0, 105.0, 105.0)
_BRACO_A: Final[tuple[Ponto, Ponto]] = ((92.0, 92.0), (108.0, 108.0))
_BRACO_B: Final[tuple[Ponto, Ponto]] = ((92.0, 108.0), (108.0, 92.0))


def _pares() -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        ({"family_id": "autoral"}, {"id": v, "recognition": {"status": "enabled", "grammar": g}})
        for v, g in CASOS_HASTE
    ]


def _contexto(caminhos: list[Caminho]) -> ContextoGramatica:
    return contexto_gramaticas(pagina_gramatica(caminhos))


# --- invariância da haste: valores medidos na base 706c8c9, antes da extração -----------------
# Cada linha: casamentos (variante, caixa arredondada a 0,001, caminho, componentes) e o gasto
# (colagem, índices, gramáticas). Gerado rodando o desenho num worktree de 706c8c9.

_DOURADO: Final[
    dict[str, tuple[tuple[tuple[str, Caixa, int, tuple[int, ...]], ...], tuple[int, int, int]]]
] = {
    "cemig-eo-r3-s19-v001|0.0|0": (
        (("cemig-eo-r3-s19-v001", (146.0, 140.0, 154.0, 153.0), 0, (1, 2, 3)),),
        (0, 8, 23),
    ),
    "cemig-eo-r3-s19-v001|0.0|90": (
        (("cemig-eo-r3-s19-v001", (147.0, 146.0, 160.0, 154.0), 0, (1, 2, 3)),),
        (0, 8, 22),
    ),
    "cemig-eo-r3-s19-v001|37.0|0": (
        (("cemig-eo-r3-s19-v001", (148.195, 141.111, 157.216, 152.396), 0, (1, 2, 3)),),
        (0, 8, 23),
    ),
    "cemig-eo-r3-s19-v001|37.0|90": (
        (("cemig-eo-r3-s19-v001", (147.604, 148.195, 158.889, 157.216), 0, (1, 2, 3)),),
        (0, 8, 23),
    ),
    "cemig-eo-r3-s19-v002|0.0|0": (
        (("cemig-eo-r3-s19-v002", (139.85, 132.35, 160.15, 152.65), 0, (1, 2, 3, 4)),),
        (0, 10, 25),
    ),
    "cemig-eo-r3-s19-v002|0.0|90": (
        (("cemig-eo-r3-s19-v002", (147.35, 139.85, 167.65, 160.15), 0, (1, 2, 3, 4)),),
        (0, 10, 24),
    ),
    "cemig-eo-r3-s19-v002|37.0|0": (
        (("cemig-eo-r3-s19-v002", (144.364, 133.86, 164.664, 154.16), 0, (1, 2, 3, 4)),),
        (0, 10, 25),
    ),
    "cemig-eo-r3-s19-v002|37.0|90": (
        (("cemig-eo-r3-s19-v002", (145.84, 144.364, 166.14, 164.664), 0, (1, 2, 3, 4)),),
        (0, 10, 25),
    ),
    "cemig-eo-r3-s19-v003|0.0|0": (
        (("cemig-eo-r3-s19-v003", (139.85, 132.35, 160.15, 152.65), 0, (1, 2, 3, 4, 5, 6)),),
        (0, 14, 46),
    ),
    "cemig-eo-r3-s19-v003|0.0|90": (
        (("cemig-eo-r3-s19-v003", (147.35, 139.85, 167.65, 160.15), 0, (1, 2, 3, 4, 5, 6)),),
        (0, 14, 45),
    ),
    "cemig-eo-r3-s19-v003|37.0|0": (
        (("cemig-eo-r3-s19-v003", (144.364, 133.86, 164.664, 154.16), 0, (1, 2, 3, 4, 5, 6)),),
        (0, 14, 46),
    ),
    "cemig-eo-r3-s19-v003|37.0|90": (
        (("cemig-eo-r3-s19-v003", (145.84, 144.364, 166.14, 164.664), 0, (1, 2, 3, 4, 5, 6)),),
        (0, 14, 46),
    ),
    "cemig-eo-r3-s19-v004|0.0|0": (
        (("cemig-eo-r3-s19-v004", (146.0, 140.0, 154.0, 153.0), 0, (1, 2, 3, 4, 5)),),
        (0, 12, 44),
    ),
    "cemig-eo-r3-s19-v004|0.0|90": (
        (("cemig-eo-r3-s19-v004", (147.0, 146.0, 160.0, 154.0), 0, (1, 2, 3, 4, 5)),),
        (0, 12, 43),
    ),
    "cemig-eo-r3-s19-v004|37.0|0": (
        (("cemig-eo-r3-s19-v004", (148.195, 141.111, 157.216, 152.396), 0, (1, 2, 3, 4, 5)),),
        (0, 12, 44),
    ),
    "cemig-eo-r3-s19-v004|37.0|90": (
        (("cemig-eo-r3-s19-v004", (147.604, 148.195, 158.889, 157.216), 0, (1, 2, 3, 4, 5)),),
        (0, 12, 44),
    ),
    "cemig-eo-r3-s21-v005|0.0|0": (
        (("cemig-eo-r3-s21-v005", (146.0, 137.5, 154.0, 153.0), 0, (1, 2, 3, 4)),),
        (0, 10, 30),
    ),
    "cemig-eo-r3-s21-v005|0.0|90": (
        (("cemig-eo-r3-s21-v005", (147.0, 146.0, 162.5, 154.0), 0, (1, 2, 3, 4)),),
        (0, 10, 30),
    ),
    "cemig-eo-r3-s21-v005|37.0|0": (
        (("cemig-eo-r3-s21-v005", (148.195, 138.513, 159.519, 152.396), 0, (1, 2, 3, 4)),),
        (0, 10, 32),
    ),
    "cemig-eo-r3-s21-v005|37.0|90": (
        (("cemig-eo-r3-s21-v005", (147.604, 148.195, 161.487, 159.519), 0, (1, 2, 3, 4)),),
        (0, 10, 32),
    ),
    "cemig-eo-r3-s21-v006|0.0|0": (
        (("cemig-eo-r3-s21-v006", (138.6, 129.85, 161.4, 152.65), 0, (1, 2, 3, 4, 5)),),
        (0, 12, 32),
    ),
    "cemig-eo-r3-s21-v006|0.0|90": (
        (("cemig-eo-r3-s21-v006", (147.35, 138.6, 170.15, 161.4), 0, (1, 2, 3, 4, 5)),),
        (0, 12, 32),
    ),
    "cemig-eo-r3-s21-v006|37.0|0": (
        (("cemig-eo-r3-s21-v006", (143.866, 131.612, 166.666, 154.412), 0, (1, 2, 3, 4, 5)),),
        (0, 12, 34),
    ),
    "cemig-eo-r3-s21-v006|37.0|90": (
        (("cemig-eo-r3-s21-v006", (145.588, 143.866, 168.388, 166.666), 0, (1, 2, 3, 4, 5)),),
        (0, 12, 34),
    ),
    "cemig-eo-r3-s21-v007|0.0|0": (
        (("cemig-eo-r3-s21-v007", (138.6, 129.85, 161.4, 152.65), 0, (1, 2, 3, 4, 5, 6, 7)),),
        (0, 16, 57),
    ),
    "cemig-eo-r3-s21-v007|0.0|90": (
        (("cemig-eo-r3-s21-v007", (147.35, 138.6, 170.15, 161.4), 0, (1, 2, 3, 4, 5, 6, 7)),),
        (0, 16, 57),
    ),
    "cemig-eo-r3-s21-v007|37.0|0": (
        (("cemig-eo-r3-s21-v007", (143.866, 131.612, 166.666, 154.412), 0, (1, 2, 3, 4, 5, 6, 7)),),
        (0, 16, 59),
    ),
    "cemig-eo-r3-s21-v007|37.0|90": (
        (("cemig-eo-r3-s21-v007", (145.588, 143.866, 168.388, 166.666), 0, (1, 2, 3, 4, 5, 6, 7)),),
        (0, 16, 59),
    ),
    "cemig-eo-r3-s21-v008|0.0|0": (
        (("cemig-eo-r3-s21-v008", (146.0, 137.5, 154.0, 153.0), 0, (1, 2, 3, 4, 5, 6)),),
        (0, 14, 55),
    ),
    "cemig-eo-r3-s21-v008|0.0|90": (
        (("cemig-eo-r3-s21-v008", (147.0, 146.0, 162.5, 154.0), 0, (1, 2, 3, 4, 5, 6)),),
        (0, 14, 55),
    ),
    "cemig-eo-r3-s21-v008|37.0|0": (
        (("cemig-eo-r3-s21-v008", (148.195, 138.513, 159.519, 152.396), 0, (1, 2, 3, 4, 5, 6)),),
        (0, 14, 57),
    ),
    "cemig-eo-r3-s21-v008|37.0|90": (
        (("cemig-eo-r3-s21-v008", (147.604, 148.195, 161.487, 159.519), 0, (1, 2, 3, 4, 5, 6)),),
        (0, 14, 57),
    ),
    "neg:tres_barras_iguais": ((), (0, 8, 18)),
    "neg:duas_barras": ((), (0, 6, 8)),
    "neg:barras_nao_perpendiculares": ((), (0, 8, 15)),
    "neg:espacamento_fora_da_faixa": ((), (0, 8, 8)),
    "neg:hachura_de_seis_tracos": ((), (0, 12, 34)),
    "neg:glifo_e": ((), (0, 8, 17)),
    "neg:glifo_identico": ((), (0, 6, 12)),
    "neg:barras_de_outra_cor": ((), (0, 8, 10)),
    "hexagono": (
        (("cemig-eo-r3-s21-v005", (146.0, 137.5, 154.0, 153.0), 0, (1, 2, 3, 4)),),
        (0, 17, 54),
    ),
    "estrela": (
        (("cemig-eo-r3-s21-v005", (146.0, 137.5, 154.0, 153.0), 0, (1, 2, 3, 4)),),
        (0, 27, 87),
    ),
}


def _desenho(chave: str) -> tuple[Callable[[pymupdf.Page], object], int]:
    if chave.startswith("neg:"):
        return NEGATIVOS[chave[4:]], 0
    if chave == "hexagono":
        return lambda p: desenhar_haste(p, ALTERNADAS, envolvente=True, contorno=HEXAGONO), 0
    if chave == "estrela":
        return lambda p: desenhar_haste(p, ALTERNADAS, envolvente=True, contorno=ESTRELA), 0
    variante, graus, rotacao = chave.split("|")
    return lambda p: desenhar_positivo(p, variante, graus=float(graus)), int(rotacao)


@pytest.mark.parametrize("chave", list(_DOURADO), ids=list(_DOURADO))
def test_casamentos_e_gasto_da_haste_iguais_aos_da_base(chave: str) -> None:
    desenhar, rotacao = _desenho(chave)
    esperados, gasto_esperado = _DOURADO[chave]

    casamentos = casar_variantes(pagina_desenhada(desenhar, rotacao=rotacao), _pares())
    gasto = gasto_por_fase(pagina_desenhada(desenhar, rotacao=rotacao), _pares())

    assert [c.variante["id"] for c in casamentos] == [e[0] for e in esperados]
    for achado, (_, caixa, caminho, componentes) in zip(casamentos, esperados, strict=True):
        assert achado.caixa == pytest.approx(caixa, abs=1e-3)
        assert achado.caminho == caminho
        assert achado.componentes == componentes
    assert (gasto.colagem, gasto.indices, gasto.gramaticas) == gasto_esperado


# --- MarcasDaPagina: pagamento único também com duas chamadas das hastes ----------------------


def _pagina_com_haste() -> PaginaGramatica:
    return pagina_desenhada(lambda p: desenhar_positivo(p, "cemig-eo-r3-s19-v002"))


def test_dois_pedidos_de_hastes_com_as_mesmas_marcas_pagam_os_contornos_uma_vez() -> None:
    contexto = contexto_gramaticas(_pagina_com_haste())
    marcas = MarcasDaPagina(contexto)
    inicio = contexto.orcamento.gasto
    primeira = hastes_candidatas(contexto, marcas=marcas)
    gasto_primeira = contexto.orcamento.gasto - inicio
    meio = contexto.orcamento.gasto
    segunda = hastes_candidatas(contexto, marcas=marcas)
    gasto_segunda = contexto.orcamento.gasto - meio

    isolado = contexto_gramaticas(_pagina_com_haste())
    antes = isolado.orcamento.gasto
    assert MarcasDaPagina(isolado).contornos is not None
    custo_contornos = isolado.orcamento.gasto - antes

    assert custo_contornos > 0
    assert segunda == primeira
    assert gasto_primeira - gasto_segunda == custo_contornos


def test_dois_pedidos_sem_marcas_pagam_os_contornos_cada_um() -> None:
    """Sem marcas recebidas cada chamada cria as suas: o gasto de hoje, sem compartilhar."""
    contexto = contexto_gramaticas(_pagina_com_haste())
    inicio = contexto.orcamento.gasto
    hastes_candidatas(contexto)
    primeiro = contexto.orcamento.gasto - inicio
    meio = contexto.orcamento.gasto
    hastes_candidatas(contexto)

    assert contexto.orcamento.gasto - meio == primeiro


def test_marcas_sem_pedido_nao_pagam_nada_mesmo_lendo_a_origem_varias_vezes() -> None:
    contexto = contexto_gramaticas(_pagina_com_haste())
    antes = contexto.orcamento.gasto
    marcas = MarcasDaPagina(contexto)

    assert {marcas.origem for _ in range(3)} == {"nativo"}
    assert contexto.orcamento.gasto == antes


# --- envolvente: bordas -----------------------------------------------------------------------


def _achar(
    caminhos: list[Caminho],
    exigidos: tuple[Ponto, ...] = (_CENTRO,),
    escala: float = 8.0,
    ancora: Ponto = _CENTRO,
    proprios: frozenset[int] = frozenset(),
) -> Any:
    marcas = MarcasDaPagina(_contexto(caminhos))
    return envolvente(marcas.contornos, exigidos, escala, ancora, proprios)


@pytest.mark.parametrize(
    ("distancia", "achada"),
    [(10.1, True), (10.15, True), (10.2, False)],
    ids=["dentro-da-tolerancia", "no-limite-da-tolerancia", "fora-da-tolerancia"],
)
def test_exigido_perto_da_borda_da_elipse_usa_a_tolerancia_da_escala(
    distancia: float, achada: bool
) -> None:
    """Escala 8 dá tolerância 0,16 sobre o raio 10 do círculo."""
    resultado = _achar(
        [circulo_bezier(_CENTRO, 10.0)], exigidos=(_CENTRO, (100.0 + distancia, 100.0))
    )

    assert (resultado is not None) is achada


def test_exigido_na_caixa_mas_fora_da_elipse_recusa() -> None:
    """O canto (108, 108) está dentro da caixa de 20 de lado, mas fora da elipse."""
    assert _achar([circulo_bezier(_CENTRO, 10.0)], exigidos=(_CENTRO, (108.0, 108.0))) is None


def test_ancora_distante_da_elipse_nao_acha_mesmo_contendo_os_exigidos() -> None:
    """A janela de busca é em torno da âncora (alcance 3,06 vezes a escala)."""
    caminhos = [circulo_bezier(_CENTRO, 10.0)]

    assert _achar(caminhos, ancora=(104.0, 100.0)) is not None
    assert _achar(caminhos, ancora=(140.0, 100.0)) is None


def test_envolventes_empatadas_no_diametro_escolhem_o_menor_indice_de_caminho() -> None:
    resultado = _achar([circulo_bezier(_CENTRO, 10.0), circulo_bezier(_CENTRO, 10.0)])

    assert resultado is not None
    assert resultado.caminhos == (0,)


def test_proprio_exclui_so_o_contorno_dele_e_a_outra_elipse_assume() -> None:
    caminhos = [circulo_bezier(_CENTRO, 10.0), circulo_bezier(_CENTRO, 11.0)]

    resultado = _achar(caminhos, proprios=frozenset({0}))

    assert resultado is not None
    assert resultado.caminhos == (1,)


def test_proprio_de_outro_caminho_nao_exclui_o_contorno() -> None:
    assert _achar([circulo_bezier(_CENTRO, 10.0)], proprios=frozenset({7})) is not None


def test_sem_exigidos_a_menor_elipse_da_janela_vence() -> None:
    resultado = _achar([circulo_bezier(_CENTRO, 12.0), circulo_bezier(_CENTRO, 9.0)], exigidos=())

    assert resultado is not None
    assert resultado.caminhos == (1,)


# --- X: braços próprios, cores e eixo girado --------------------------------------------------


def _x(caminhos: list[Caminho], eixo: float = math.pi / 2) -> Any:
    return tem_x(_contexto(caminhos), _PICTOGRAMA, 8.0, eixo, frozenset())


def test_x_com_os_dois_bracos_proprios_nao_conta() -> None:
    contexto = _contexto([linha(*_BRACO_A), linha(*_BRACO_B)])
    todos: frozenset[Segmento] = frozenset(contexto.grade_segmentos.itens)

    assert len(todos) == 2
    assert tem_x(contexto, _PICTOGRAMA, 8.0, math.pi / 2, todos) is None


@pytest.mark.parametrize(
    ("graus", "forma"),
    [(0.0, True), (10.0, True), (80.0, True), (100.0, True), (45.0, False), (135.0, False)],
    ids=["horizontal", "dez", "oitenta", "cem", "paralelo-a-um-braco", "paralelo-ao-outro"],
)
def test_x_com_o_eixo_girado_exige_os_dois_bracos_inclinados_25_a_65_graus(
    graus: float, forma: bool
) -> None:
    """Braços a 45 e 135 graus: um eixo paralelo a um deles deixa esse braço de fora."""
    resultado = _x([linha(*_BRACO_A), linha(*_BRACO_B)], eixo=math.radians(graus))

    assert (resultado is not None) is forma


def test_x_com_cor_ausente_nos_dois_bracos_forma() -> None:
    assert _x([linha(*_BRACO_A, cor=None), linha(*_BRACO_B, cor=None)]) is not None


def test_x_com_um_braco_sem_cor_e_outro_fora_do_legado_nao_forma() -> None:
    assert _x([linha(*_BRACO_A, cor=None), linha(*_BRACO_B, cor=(0.25, 0.25, 0.75))]) is None


def test_x_com_bracos_fora_da_janela_do_pictograma_nao_forma() -> None:
    deslocado = [linha((a[0] + 40.0, a[1]), (b[0] + 40.0, b[1])) for a, b in (_BRACO_A, _BRACO_B)]

    assert _x(deslocado) is None


def test_x_com_bracos_curtos_demais_nao_forma() -> None:
    """Comprimento mínimo 0,8 vezes a escala 8: 6,4. Braços de 4 de lado."""
    curtos = [linha((98.0, 98.0), (102.0, 102.0)), linha((98.0, 102.0), (102.0, 98.0))]

    assert _x(curtos) is None


# --- fronteira do módulo ----------------------------------------------------------------------


def _importados(modulo: ModuleType) -> set[str]:
    arvore = ast.parse(Path(str(modulo.__file__)).read_text(encoding="utf-8"))
    importados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            importados.add(no.module or "")
    return importados


def test_grammar_marcas_e_o_que_ela_importa_do_pacote_nao_tocam_o_pymupdf() -> None:
    """Só o leitor do modelo (`pymupdf_drawing_model`) abre PDF; as marcas ficam puras."""
    pacote = "zeny_project_handler.adapters.analysis.drawing_model"
    diretos = {m for m in _importados(grammar_marcas) if m.startswith(pacote)}

    assert f"{pacote}.model" in diretos
    for nome in {"", *diretos}:
        modulo = grammar_marcas if nome == "" else importlib.import_module(nome)
        assert not {m for m in _importados(modulo) if m.split(".")[0] in {"pymupdf", "fitz"}}, nome
