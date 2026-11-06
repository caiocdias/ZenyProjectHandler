# mypy: disable-error-code="no-untyped-call"
"""Ataques ao casamento de variantes: deduplicação, orçamento, falhas de fonte, rótulo em pedaços
e pureza transitiva do núcleo."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.paginas import (
    circulo_bezier,
    linha,
    pagina_gramatica,
    retangulo_traco,
    texto,
)

from zeny_project_handler.adapters.analysis import declarative_symbols as motor_antigo
from zeny_project_handler.adapters.analysis.drawing_model import (
    grammar_disc,
    grammar_frames,
    symbol_grammars,
    symbol_matcher,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    FonteGramaticaFalhou,
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas

Par = tuple[Mapping[str, Any], Mapping[str, Any]]

_MOLDURA: Final[Caixa] = (101.0, 115.0, 169.0, 149.0)
_ROTULO: Final[Caixa] = (107.0, 130.0, 125.0, 142.0)
_CENTRO_DISCO: Final = (150.0, 150.0)
_ROXO: Final = (0.31, 0.10, 0.30)
_CINZA: Final = (0.5, 0.5, 0.5)
_DISCO: Final[dict[str, Any]] = {
    "kind": "terminal_disc",
    "fill": "purple",
    "min_span": 1.0,
    "max_span": 4.0,
    "terminal_line": True,
}


def _rotulo(rotulo: str = "CT", forma: str = "rectangle") -> dict[str, Any]:
    return {"kind": "label_in_frame", "frame": forma, "label": rotulo, "max_span": 96}


def _par(identificador: str, gramatica: Mapping[str, Any], pacote: str = "p") -> Par:
    return {"family_id": pacote}, {
        "id": identificador,
        "recognition": {"status": "enabled", "grammar": gramatica},
    }


def _pagina_rotulo() -> PaginaGramatica:
    return pagina_gramatica((retangulo_traco(_MOLDURA),), (texto("CT", _ROTULO),))


def _pagina_rotulo_e_disco() -> PaginaGramatica:
    return pagina_gramatica(
        (
            retangulo_traco(_MOLDURA),
            linha((60.0, 150.0), _CENTRO_DISCO, cor=_CINZA),
            circulo_bezier(_CENTRO_DISCO, 1.4, cor=None, preenchimento=_ROXO),
        ),
        (texto("CT", _ROTULO),),
    )


def _quem(casamentos: Sequence[CasamentoGramatica]) -> list[tuple[str, str, int]]:
    return [(c.variante["id"], c.pacote["family_id"], c.caminho) for c in casamentos]


# --- deduplicação e ordem -------------------------------------------------------------------


def test_mesma_variante_em_dois_pacotes_deduplica_e_fica_com_o_primeiro() -> None:
    lista = (
        _par("a", _rotulo(), "p1"),
        _par("a", _rotulo(), "p2"),
        _par("b", _rotulo(), "p3"),
    )

    assert _quem(casar_variantes(_pagina_rotulo(), lista)) == [("a", "p1", 0), ("b", "p3", 0)]


def test_variantes_distintas_na_mesma_caixa_casam_todas_na_ordem_da_lista() -> None:
    lista = (_par("c", _rotulo(), "p3"), _par("a", _rotulo(), "p1"), _par("b", _rotulo(), "p2"))

    assert _quem(casar_variantes(_pagina_rotulo(), lista)) == [
        ("c", "p3", 0),
        ("a", "p1", 0),
        ("b", "p2", 0),
    ]


def _duas_molduras_com_x1(primeira: float, segunda: float) -> PaginaGramatica:
    x0, y0, _, y1 = _MOLDURA
    return pagina_gramatica(
        (retangulo_traco((x0, y0, primeira, y1)), retangulo_traco((x0, y0, segunda, y1))),
        (texto("CT", _ROTULO),),
    )


def test_caixas_que_arredondam_para_valores_diferentes_nao_deduplicam() -> None:
    """169,0004 e 169,0006 arredondam para 169,000 e 169,001: duas caixas, a 0,0002 de distância."""
    pagina = _duas_molduras_com_x1(169.0004, 169.0006)

    assert len(casar_variantes(pagina, (_par("a", _rotulo()),))) == 2


def test_caixas_que_arredondam_para_o_mesmo_valor_deduplicam_a_distancia_maior() -> None:
    """169,0006 e 169,0014 arredondam ambas para 169,001, mesmo a 0,0008 de distância."""
    pagina = _duas_molduras_com_x1(169.0006, 169.0014)

    assert len(casar_variantes(pagina, (_par("a", _rotulo()),))) == 1


def test_ordem_com_molduras_e_discos_intercalados_segue_a_lista() -> None:
    lista = (_par("m1", _rotulo()), _par("d", _DISCO), _par("m2", _rotulo()))

    casamentos = casar_variantes(_pagina_rotulo_e_disco(), lista)

    assert [c.variante["id"] for c in casamentos] == ["m1", "d", "m2"]
    assert casamentos == casar_variantes(_pagina_rotulo_e_disco(), lista)


def test_variante_de_disco_sem_disco_na_pagina_nao_casa_nem_levanta() -> None:
    pagina = pagina_gramatica((), (texto("CT", _ROTULO),))

    assert casar_variantes(pagina, (_par("d", _DISCO),)) == ()


def test_pacote_vazio_passa_intacto_para_o_casamento() -> None:
    pacote: Mapping[str, Any] = {}
    variante = _par("a", _rotulo())[1]

    (casamento,) = casar_variantes(_pagina_rotulo(), ((pacote, variante),))

    assert casamento.pacote is pacote
    assert casamento.variante is variante


# --- orçamento ------------------------------------------------------------------------------


def test_teto_baixo_levanta_na_gramatica_de_disco() -> None:
    pagina = _pagina_rotulo_e_disco()
    construir = contexto_gramaticas(pagina).orcamento.gasto

    with pytest.raises(TetoGramaticasExcedido):
        casar_variantes(pagina, (_par("d", _DISCO),), limite=construir)


def _custo_alem_do_contexto(pagina: PaginaGramatica, lista: Sequence[Par]) -> int:
    """Menor `limite` que deixa `casar_variantes` terminar, menos o que o contexto já gasta."""
    base = contexto_gramaticas(pagina).orcamento.gasto
    for limite in range(base, base + 500):
        try:
            casar_variantes(pagina, lista, limite=limite)
        except TetoGramaticasExcedido:
            continue
        return limite - base
    raise AssertionError("limite não encontrado")


def test_sem_variante_de_disco_os_discos_nao_cobram_do_teto() -> None:
    lista = (_par("m", _rotulo()),)

    com_disco = _pagina_rotulo_e_disco()
    sem_disco = _pagina_rotulo()
    # O círculo do disco também é uma moldura candidata (elipse): cada uma cobra 1 por variante.
    extras = len(contexto_gramaticas(com_disco).molduras) - len(
        contexto_gramaticas(sem_disco).molduras
    )

    assert extras == 1
    assert _custo_alem_do_contexto(com_disco, lista) == (
        _custo_alem_do_contexto(sem_disco, lista) + extras
    )


def test_com_variante_de_disco_os_discos_cobram_do_teto() -> None:
    """Controle do anterior: o mesmo medidor enxerga o custo quando há variante de disco."""
    lista = (_par("m", _rotulo()), _par("d", _DISCO))

    assert _custo_alem_do_contexto(_pagina_rotulo_e_disco(), lista) > _custo_alem_do_contexto(
        _pagina_rotulo_e_disco(), lista[:1]
    )


def test_teto_nunca_devolve_casamento_parcial() -> None:
    """Para todo limite, ou levanta ou devolve exatamente o resultado sem limite."""
    lista = (_par("m1", _rotulo()), _par("d", _DISCO), _par("m2", _rotulo("XX")))
    completo = casar_variantes(_pagina_rotulo_e_disco(), lista)
    piso = contexto_gramaticas(_pagina_rotulo_e_disco()).orcamento.gasto
    levantou = devolveu = 0

    for limite in range(piso, piso + 200):
        try:
            resultado = casar_variantes(_pagina_rotulo_e_disco(), lista, limite=limite)
        except TetoGramaticasExcedido:
            levantou += 1
            continue
        devolveu += 1
        assert resultado == completo, f"limite={limite}"

    assert completo
    assert levantou > 0
    assert devolveu > 0


def test_limite_zero_em_pagina_com_moldura_levanta() -> None:
    with pytest.raises(TetoGramaticasExcedido):
        casar_variantes(_pagina_rotulo(), (_par("a", _rotulo()),), limite=0)


# --- falhas de fonte ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "codigo",
    [
        "modelo.caminhos_falhou",
        "modelo.primitivas_falhou",
        "modelo.textos_nativos_falhou",
        "modelo.textos_shx_falhou",
        "modelo.glifos_falhou",
    ],
)
def test_cada_fonte_consumida_que_falhou_propaga_sem_casamento(codigo: str) -> None:
    pagina = pagina_gramatica(
        (retangulo_traco(_MOLDURA),), (texto("CT", _ROTULO),), diagnosticos=(codigo,)
    )

    with pytest.raises(FonteGramaticaFalhou) as erro:
        casar_variantes(pagina, (_par("a", _rotulo()), _par("d", _DISCO)))

    assert erro.value.codigo == codigo


def test_glifos_limitados_viram_teto_e_nao_casamento() -> None:
    pagina = pagina_gramatica(
        (retangulo_traco(_MOLDURA),),
        (texto("CT", _ROTULO),),
        diagnosticos=("modelo.glifos_limitados",),
    )

    with pytest.raises(TetoGramaticasExcedido):
        casar_variantes(pagina, (_par("a", _rotulo()),))


def test_diagnostico_de_fonte_nao_consumida_nao_atrapalha() -> None:
    pagina = pagina_gramatica(
        (retangulo_traco(_MOLDURA),),
        (texto("CT", _ROTULO),),
        diagnosticos=("modelo.imagens_falhou",),
    )

    assert len(casar_variantes(pagina, (_par("a", _rotulo()),))) == 1


def test_fonte_falhou_levanta_mesmo_sem_variantes() -> None:
    """Tudo ou nada: a página com fonte falha nunca devolve `()` como se fosse não detecção."""
    pagina = pagina_gramatica((), diagnosticos=("modelo.caminhos_falhou",))

    with pytest.raises(FonteGramaticaFalhou):
        casar_variantes(pagina, ())


# --- rótulo em pedaços, contra o `words` do motor -------------------------------------------

_QUADRADO = pymupdf.Rect(110, 110, 158, 158)
_VERMELHO = (0.7, 0.0, 0.0)
_QDP: Final[dict[str, Any]] = next(
    dict(variante["recognition"]["grammar"])
    for pacote in motor_antigo.carregar_pacotes()
    for variante in pacote["variants"]
    if variante["id"] == "cemig-eo-r3-s07-v003"
)


@contextmanager
def _pagina_pdf(desenhar: Callable[[pymupdf.Page], None]) -> Iterator[pymupdf.Page]:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenhar(pagina)
        yield pagina


def _q_e_dp(lacuna: float, y_do_intruso: float | None) -> Callable[[pymupdf.Page], None]:
    """`Q` e `DP` lado a lado, e (opcional) outro `insert_text` longe, entre os dois no fluxo."""

    def desenhar(pagina: pymupdf.Page) -> None:
        pagina.draw_rect(_QUADRADO, color=(0, 0, 0), width=1)
        pagina.insert_text((116, 139), "Q", fontsize=11)
        if y_do_intruso is not None:
            pagina.insert_text((250, y_do_intruso), "ZZ", fontsize=11)
        largura = pymupdf.get_text_length("Q", fontsize=11)
        pagina.insert_text((116 + largura + lacuna, 139), "DP", fontsize=11, color=_VERMELHO)

    return desenhar


def _motor_casa(pagina: pymupdf.Page) -> bool:
    desenhos = tuple(pagina.get_drawings(extended=True))
    contexto = motor_antigo._page_context(pagina, None, None, desenhos, ())  # type: ignore[arg-type]
    return any(
        motor_antigo._frame_ok(forma, retangulo, _QDP)
        and motor_antigo._grammar_matches(contexto, _QDP, retangulo, indice)
        for forma, retangulo, indice in contexto.frames
    )


def _nucleo_casa(pagina: pymupdf.Page) -> bool:
    return bool(casar_variantes(pagina_para_gramaticas(pagina, 0), (_par("qdp", _QDP),)))


@pytest.mark.parametrize("lacuna", [-1.0, 0.0, 1.0], ids=lambda v: f"lacuna{v:+.0f}")
def test_pedacos_adjacentes_sem_intruso_casam_nos_dois(lacuna: float) -> None:
    """Controle: sem o intruso o `words` junta `Q`+`DP` e os dois leem QDP."""
    with _pagina_pdf(_q_e_dp(lacuna, None)) as pagina:
        assert [w[4] for w in pagina.get_text("words")] == ["QDP"]
        assert _motor_casa(pagina)
        assert _nucleo_casa(pagina)


@pytest.mark.parametrize("y_do_intruso", [139.0, 200.0], ids=lambda v: f"intruso-y{v:.0f}")
@pytest.mark.parametrize("lacuna", [-1.0, 0.0, 1.0], ids=lambda v: f"lacuna{v:+.0f}")
def test_residuo_pedacos_com_intruso_no_fluxo_casam_no_nucleo_e_o_motor_recusa(
    lacuna: float, y_do_intruso: float
) -> None:
    """EXCEÇÃO CONHECIDA DE R-E06.2.1-4 (concatenação exata do rótulo, `Q`+`DP`), valor de hoje.
    Um `insert_text` longe entre os dois pedaços no fluxo faz o `words` da PyMuPDF ler `Q`, `ZZ`,
    `DP`, e o motor recusa; o núcleo funde pela geometria e casa. É afirmação a mais, não
    falha fechada. Medir a frequência em folhas reais na E06.2.2; se a fusão passar a respeitar
    a ordem do fluxo, inverter este teste, não removê-lo."""
    with _pagina_pdf(_q_e_dp(lacuna, y_do_intruso)) as pagina:
        assert [w[4] for w in pagina.get_text("words")] == ["Q", "ZZ", "DP"]
        assert not _motor_casa(pagina)
        assert _nucleo_casa(pagina)


# --- pureza transitiva ----------------------------------------------------------------------

_PROIBIDOS: Final = frozenset({"pymupdf", "fitz", "declarative_symbols", "pymupdf_drawing_model"})
_IMPORTACAO_DINAMICA: Final = frozenset({"__import__", "import_module"})
_RAIZ_SRC: Final = Path(symbol_matcher.__file__ or "").parents[4]


def _arquivo_do_modulo(raiz: Path, nome: str) -> Path | None:
    base = raiz.joinpath(*nome.split("."))
    for candidato in (base.with_suffix(".py"), base / "__init__.py"):
        if candidato.is_file():
            return candidato
    return None


def _nome_chamado(no: ast.Call) -> str:
    if isinstance(no.func, ast.Name):
        return no.func.id
    return no.func.attr if isinstance(no.func, ast.Attribute) else ""


def _nomes_importados(arvore: ast.AST, pacote: str) -> Iterator[str]:
    """Nomes absolutos pontilhados de cada import; `pacote` resolve os relativos."""
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                yield alias.name
        elif isinstance(no, ast.ImportFrom):
            base = no.module or ""
            if no.level:
                partes = pacote.split(".")
                partes = partes[: len(partes) - (no.level - 1)]
                base = ".".join([*partes, *([base] if base else [])])
            yield base
            for alias in no.names:
                yield f"{base}.{alias.name}"
        elif (
            isinstance(no, ast.Call)
            and _nome_chamado(no) in _IMPORTACAO_DINAMICA
            and no.args
            and isinstance(no.args[0], ast.Constant)
            and isinstance(no.args[0].value, str)
        ):
            yield no.args[0].value


def _proibidos_alcancaveis(raiz: Path, iniciais: Sequence[str], topo: str) -> dict[str, str]:
    """Para cada nome proibido alcançado, o módulo que o importa. Segue só os módulos de `topo`,
    sem executar nada e sem contar o `__init__` dos pacotes pais."""
    achados: dict[str, str] = {}
    vistos: set[str] = set()
    fila = list(iniciais)
    while fila:
        modulo = fila.pop()
        if modulo in vistos:
            continue
        vistos.add(modulo)
        arquivo = _arquivo_do_modulo(raiz, modulo)
        if arquivo is None or arquivo.name == "__init__.py":
            continue
        pacote = modulo.rpartition(".")[0]
        for nome in _nomes_importados(ast.parse(arquivo.read_text(encoding="utf-8")), pacote):
            if set(nome.split(".")) & _PROIBIDOS:
                achados.setdefault(nome, modulo)
            elif nome.split(".")[0] == topo:
                fila.append(nome)
    return achados


def _arvore(raiz: Path, arquivos: Mapping[str, str]) -> None:
    for caminho, fonte in arquivos.items():
        destino = raiz / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(fonte, encoding="utf-8")


@pytest.mark.parametrize(
    ("b", "esperado"),
    [
        pytest.param("import pymupdf\n", {"pymupdf": "t.b"}, id="indireto-import"),
        pytest.param(
            "from pymupdf import Page\n",
            {"pymupdf": "t.b", "pymupdf.Page": "t.b"},
            id="indireto-from",
        ),
        pytest.param("import fitz as f\n", {"fitz": "t.b"}, id="indireto-fitz"),
        pytest.param(
            "from t import declarative_symbols\n",
            {"t.declarative_symbols": "t.b"},
            id="indireto-from-pacote",
        ),
        pytest.param("def f():\n    import pymupdf\n", {"pymupdf": "t.b"}, id="indireto-tardio"),
        pytest.param(
            "import importlib\nimportlib.import_module('pymupdf')\n",
            {"pymupdf": "t.b"},
            id="dinamico",
        ),
        pytest.param("x = __import__('fitz')\n", {"fitz": "t.b"}, id="dunder-import"),
        pytest.param("import json\n", {}, id="limpo"),
    ],
)
def test_detector_transitivo_reprova_import_indireto(
    tmp_path: Path, b: str, esperado: dict[str, str]
) -> None:
    _arvore(
        tmp_path,
        {"t/__init__.py": "import pymupdf\n", "t/a.py": "from . import b\n", "t/b.py": b},
    )

    assert _proibidos_alcancaveis(tmp_path, ["t.a"], "t") == esperado


def test_detector_transitivo_resolve_import_relativo_de_dois_niveis(tmp_path: Path) -> None:
    _arvore(
        tmp_path,
        {
            "t/__init__.py": "",
            "t/s/__init__.py": "",
            "t/s/a.py": "from ..u import c\n",
            "t/u/__init__.py": "",
            "t/u/c.py": "import pymupdf\n",
        },
    )

    assert _proibidos_alcancaveis(tmp_path, ["t.s.a"], "t") == {"pymupdf": "t.u.c"}


def test_nucleo_nao_alcanca_pymupdf_nem_o_motor_nem_o_leitor_nem_indiretamente() -> None:
    modulos = [m.__name__ for m in (symbol_grammars, grammar_frames, grammar_disc, symbol_matcher)]

    assert all(_arquivo_do_modulo(_RAIZ_SRC, modulo) is not None for modulo in modulos)
    assert _proibidos_alcancaveis(_RAIZ_SRC, modulos, "zeny_project_handler") == {}
