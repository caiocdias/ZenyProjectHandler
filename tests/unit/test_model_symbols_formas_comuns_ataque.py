# mypy: disable-error-code="no-untyped-call"
"""Ataques ao agrupamento de formas comuns do modelo (R-E06.3.3.2.2-2), pelo testador.

Determinismo do representante e da lista, a mesma forma em vários pontos e páginas, a chave
termo a termo (âncora e caixa isolados, gramática em JSON canônico), o grupo de um, a
reconciliação de ponta a ponta, o dedupe por variante e caixa do núcleo e os componentes do
representante. Pacotes e desenhos autorais sobre `rect_diagonal`; nada vem de folha real.
"""

from __future__ import annotations

import copy
import itertools
import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.rect_diagonal import desenhar_retangulo
from tests.unit.test_model_symbols_formas_comuns import (
    _CENTRO,
    _FAMILIA,
    _GRAMATICA,
    _OUTRA_FAMILIA,
    _OUTRO_CENTRO,
    _SHA,
    Pacote,
    _carrega,
    _observar,
    _pacote,
    _variante,
)
from tests.unit.test_symbol_packages_sem_memorizacao import _violacoes_de_fonte

from zeny_project_handler.adapters.analysis import model_symbols
from zeny_project_handler.adapters.analysis.declarative_symbols import _enabled, carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    CasamentoGramatica,
    casar_variantes,
)
from zeny_project_handler.adapters.analysis.model_symbols import (
    _observacao,
    observar_pacotes_modelo,
    perfil_pacotes_modelo,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    reconcile_symbols,
)
from zeny_project_handler.domain.symbols import (
    FonteObservacaoSimbolo,
    ObservacaoSimbolo,
    ResultadoMetodoSimbolos,
)

_IDS: Final = ("autoral-forma-v003", "autoral-forma-v001", "autoral-forma-v002")
_LISTA: Final = json.dumps(sorted(_IDS))
_IDS_B: Final = ("autoral-forma-v005", "autoral-forma-v004")
_LISTA_B: Final = json.dumps(sorted(_IDS_B))
_REPRESENTANTE: Final = "autoral-forma-v001"
_ENVOLVIDA: Final[dict[str, Any]] = {**_GRAMATICA, "enclosure": "ellipse"}
_FONTE: Final = FonteObservacaoSimbolo(
    documento_id="formas-comuns", documento_sha256=_SHA, pagina_numero=1, camada="base"
)


@pytest.fixture(scope="module")
def tabela() -> TabelaGlifos:
    return carregar_tabela_glifos()


def _por_id(resultado: ResultadoMetodoSimbolos) -> list[ObservacaoSimbolo]:
    return sorted(resultado.observacoes, key=lambda observacao: observacao.id)


def _possiveis(observacao: ObservacaoSimbolo) -> str:
    return str(dict(observacao.atributos)["referencias_possiveis"])


def _reordenado(pacote: Pacote, ordem: Sequence[str]) -> Pacote:
    """Cópia do pacote já validado com as variantes na `ordem` de ids."""
    copia = copy.deepcopy(pacote)
    por_id = {variante["id"]: variante for variante in copia["variants"]}
    copia["variants"] = [por_id[variante_id] for variante_id in ordem]
    return copia


# --- determinismo ---------------------------------------------------------------------------


def _ordens() -> list[tuple[tuple[str, ...], tuple[str, ...], bool]]:
    """Toda ordem das três variantes de A, as duas de B e as duas ordens dos pacotes."""
    return [
        (ordem_a, ordem_b, b_primeiro)
        for ordem_a in itertools.permutations(_IDS)
        for ordem_b in itertools.permutations(_IDS_B)
        for b_primeiro in (False, True)
    ]


@pytest.mark.parametrize(
    ("ordem_a", "ordem_b", "b_primeiro"),
    _ordens(),
    ids=lambda valor: "-".join(v[-4:] for v in valor) if isinstance(valor, tuple) else str(valor),
)
def test_representante_e_lista_nao_dependem_da_ordem_de_pacotes_e_variantes(
    tmp_path: Path,
    tabela: TabelaGlifos,
    ordem_a: tuple[str, ...],
    ordem_b: tuple[str, ...],
    b_primeiro: bool,
) -> None:
    """Duas famílias de gramática igual no mesmo desenho: dois grupos, um por família.

    O perfil fica fixo: a assinatura do método depende da ordem dos pacotes, o que não é deste
    agrupamento; aqui só a ordem que o núcleo vê muda."""
    carregados = _carrega(
        tmp_path,
        _pacote(_FAMILIA, [_variante(i) for i in _IDS]),
        _pacote(_OUTRA_FAMILIA, [_variante(i) for i in _IDS_B]),
    )
    perfil = perfil_pacotes_modelo(carregados, tabela)
    por_familia = {pacote["family_id"]: pacote for pacote in carregados}
    a = _reordenado(por_familia[_FAMILIA], ordem_a)
    b = _reordenado(por_familia[_OUTRA_FAMILIA], ordem_b)

    def observar(pacotes: tuple[Pacote, ...]) -> ResultadoMetodoSimbolos:
        with pymupdf.open() as documento:
            pagina = documento.new_page(width=300, height=300)
            desenhar_retangulo(pagina, _CENTRO)
            return observar_pacotes_modelo(
                pagina,
                documento_id="formas-comuns",
                documento_sha256=_SHA,
                pagina_numero=1,
                pacotes=pacotes,
                tabela=tabela,
                perfil=perfil,
            )

    referencia = observar(carregados)

    resultado = observar((b, a) if b_primeiro else (a, b))

    assert _por_id(resultado) == _por_id(referencia)
    assert sorted((o.template or "", _possiveis(o)) for o in resultado.observacoes) == [
        (_REPRESENTANTE, _LISTA),
        ("autoral-forma-v004", _LISTA_B),
    ]


def test_mesma_pagina_observada_duas_vezes_da_o_mesmo_resultado(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(i) for i in _IDS]))
    centros: tuple[Ponto, ...] = (_CENTRO, _OUTRO_CENTRO)

    primeira = _observar(pacotes, tabela, centros)
    segunda = _observar(pacotes, tabela, centros)

    assert primeira == segunda
    assert [o.id for o in primeira.observacoes] == [o.id for o in segunda.observacoes]


def test_lista_e_ordenada_e_o_representante_e_o_primeiro_dela(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """Caracterização: "menor id" é a ordem de `str`, não a natural (v10 antes de v9).

    Os ids reais têm três dígitos, e as duas ordens coincidem; o que não pode é o representante
    divergir do primeiro da lista.
    """
    ids = ("autoral-forma-v9", "autoral-forma-v10", "autoral-forma-v2")
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(i) for i in ids]))

    (observacao,) = _observar(pacotes, tabela).observacoes

    lista = json.loads(_possiveis(observacao))
    assert lista == ["autoral-forma-v10", "autoral-forma-v2", "autoral-forma-v9"]
    assert observacao.template == lista[0]
    assert dict(observacao.atributos)["variante_inventario"] == lista[0]


def test_atributos_vem_do_representante_e_nao_do_primeiro_casado(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """A referência de fonte difere por variante; o pacote traz o v003 primeiro."""
    variantes = []
    for variante_id in _IDS:
        variante = _variante(variante_id)
        variante["source_ref"]["locator"] = f"desenho autoral {variante_id[-4:]}"
        variantes.append(variante)
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, variantes))

    (observacao,) = _observar(pacotes, tabela).observacoes

    atributos = dict(observacao.atributos)
    assert atributos["localizador_referencia"] == "desenho autoral v001"
    assert atributos["variante_inventario"] == _REPRESENTANTE


# --- vários pontos e páginas ----------------------------------------------------------------


def test_mesma_forma_em_tres_pontos_da_tres_observacoes_cada_uma_com_a_lista(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(i) for i in _IDS]))
    centros: tuple[Ponto, ...] = (_CENTRO, _OUTRO_CENTRO, (230.0, 60.0))

    resultado = _observar(pacotes, tabela, centros)

    assert len(resultado.observacoes) == 3
    assert len({o.geometria for o in resultado.observacoes}) == 3
    assert len({o.primitivas for o in resultado.observacoes}) == 3
    assert {(o.template, _possiveis(o)) for o in resultado.observacoes} == {
        (_REPRESENTANTE, _LISTA)
    }


def test_mesma_forma_em_duas_paginas_da_uma_observacao_por_pagina(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(i) for i in _IDS]))
    perfil = perfil_pacotes_modelo(pacotes, tabela)

    with pymupdf.open() as documento:
        for centro in (_CENTRO, _OUTRO_CENTRO):
            desenhar_retangulo(documento.new_page(width=300, height=300), centro)
        resultados = [
            observar_pacotes_modelo(
                documento[numero - 1],
                documento_id="formas-comuns",
                documento_sha256=_SHA,
                pagina_numero=numero,
                pacotes=pacotes,
                tabela=tabela,
                perfil=perfil,
            )
            for numero in (1, 2)
        ]

    observacoes = [o for resultado in resultados for o in resultado.observacoes]
    assert [len(resultado.observacoes) for resultado in resultados] == [1, 1]
    assert [o.fonte.pagina_numero for o in observacoes] == [1, 2]
    assert {(o.template, _possiveis(o)) for o in observacoes} == {(_REPRESENTANTE, _LISTA)}
    assert observacoes[0].id != observacoes[1].id


# --- a chave, termo a termo -----------------------------------------------------------------


def test_max_span_72_e_72_0_nao_se_agrupam_caracterizacao(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """Caracterização: a gramática entra em JSON canônico, e `72 != 72.0` nele, embora `==` os
    iguale. Do lado conservador: separa, nunca esconde. Se a chave passar a `==`, este teste
    muda junto com a decisão."""
    flutuante = {**_GRAMATICA, "max_span": 72.0}
    pacotes = _carrega(
        tmp_path,
        _pacote(
            _FAMILIA,
            [_variante("autoral-forma-v001"), _variante("autoral-forma-v002", gramatica=flutuante)],
        ),
    )
    gramaticas = [variante["recognition"]["grammar"] for _, variante in _enabled(pacotes)]
    assert gramaticas[0] == gramaticas[1]
    assert type(gramaticas[1]["max_span"]) is float

    resultado = _observar(pacotes, tabela)

    assert sorted(_possiveis(o) for o in resultado.observacoes) == [
        "autoral-forma-v001",
        "autoral-forma-v002",
    ]


def test_gramatica_igual_com_chaves_em_outra_ordem_se_agrupa(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """A ordem das chaves no JSON do pacote não é diferença de forma."""
    invertida = dict(reversed(list(_GRAMATICA.items())))
    assert list(invertida) != list(_GRAMATICA)
    pacotes = _carrega(
        tmp_path,
        _pacote(
            _FAMILIA,
            [_variante("autoral-forma-v002", gramatica=invertida), _variante("autoral-forma-v001")],
        ),
    )

    (observacao,) = _observar(pacotes, tabela).observacoes

    assert observacao.template == _REPRESENTANTE
    assert _possiveis(observacao) == json.dumps(["autoral-forma-v001", "autoral-forma-v002"])


def _observar_com_casamentos(
    monkeypatch: pytest.MonkeyPatch,
    pacotes: tuple[Pacote, ...],
    tabela: TabelaGlifos,
    transformar: Callable[[tuple[CasamentoGramatica, ...]], tuple[CasamentoGramatica, ...]],
    *,
    envolvida: bool = False,
) -> ResultadoMetodoSimbolos:
    """Observa um desenho com os casamentos reais do núcleo passados por `transformar`."""
    original = casar_variantes

    def alterado(*args: Any, **kwargs: Any) -> tuple[CasamentoGramatica, ...]:
        return transformar(original(*args, **kwargs))

    monkeypatch.setattr(model_symbols, "casar_variantes", alterado)
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenhar_retangulo(
            pagina, _CENTRO, envolvente=envolvida, ganchos=envolvida, haste=envolvida
        )
        return observar_pacotes_modelo(
            pagina,
            documento_id="formas-comuns",
            documento_sha256=_SHA,
            pagina_numero=1,
            pacotes=pacotes,
            tabela=tabela,
        )


def _so_no_v002(
    mudar: Callable[[CasamentoGramatica], CasamentoGramatica],
) -> Callable[[tuple[CasamentoGramatica, ...]], tuple[CasamentoGramatica, ...]]:
    def transformar(casamentos: tuple[CasamentoGramatica, ...]) -> tuple[CasamentoGramatica, ...]:
        return tuple(
            mudar(c) if c.variante["id"] == "autoral-forma-v002" else c for c in casamentos
        )

    return transformar


def test_ancoras_diferentes_na_mesma_caixa_nao_se_agrupam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """Só o âncora muda (o caminho da diagonal, que existe na página); a caixa é a mesma."""
    pacotes = _carrega(
        tmp_path,
        _pacote(_FAMILIA, [_variante("autoral-forma-v001"), _variante("autoral-forma-v002")]),
    )

    resultado = _observar_com_casamentos(
        monkeypatch,
        pacotes,
        tabela,
        _so_no_v002(lambda c: replace(c, caminho=c.componentes[0], componentes=(c.caminho,))),
    )

    assert sorted(_possiveis(o) for o in resultado.observacoes) == [
        "autoral-forma-v001",
        "autoral-forma-v002",
    ]


def test_caixas_diferentes_no_mesmo_ancora_nao_se_agrupam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """Só a caixa muda, acima do arredondamento de 0,001; o âncora é o mesmo. Isola o termo
    da caixa, que nenhum desenho determinístico separa do âncora."""
    pacotes = _carrega(
        tmp_path,
        _pacote(_FAMILIA, [_variante("autoral-forma-v001"), _variante("autoral-forma-v002")]),
    )

    def deslocada(casamento: CasamentoGramatica) -> CasamentoGramatica:
        x0, y0, x1, y1 = casamento.caixa
        return replace(casamento, caixa=(x0 + 0.5, y0, x1 + 0.5, y1))

    resultado = _observar_com_casamentos(monkeypatch, pacotes, tabela, _so_no_v002(deslocada))

    assert sorted(_possiveis(o) for o in resultado.observacoes) == [
        "autoral-forma-v001",
        "autoral-forma-v002",
    ]


def test_caixas_iguais_ate_o_arredondamento_se_agrupam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """A caixa entra arredondada, como em `symbol_matcher`: um nanoponto não separa o grupo."""
    pacotes = _carrega(
        tmp_path,
        _pacote(_FAMILIA, [_variante("autoral-forma-v002"), _variante("autoral-forma-v001")]),
    )

    def quase(casamento: CasamentoGramatica) -> CasamentoGramatica:
        x0, y0, x1, y1 = casamento.caixa
        return replace(casamento, caixa=(x0 + 1e-9, y0, x1, y1 - 1e-9))

    resultado = _observar_com_casamentos(monkeypatch, pacotes, tabela, _so_no_v002(quase))

    (observacao,) = resultado.observacoes
    assert observacao.template == _REPRESENTANTE
    assert _possiveis(observacao) == json.dumps(["autoral-forma-v001", "autoral-forma-v002"])


# --- dedupe do núcleo por variante e caixa (`vistos`) ---------------------------------------


def test_desenho_duplicado_no_mesmo_lugar_da_uma_observacao_com_a_lista_sem_repeticao(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """O núcleo descarta a mesma variante na mesma caixa arredondada; o grupo não repete id."""
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(i) for i in _IDS]))

    (observacao,) = _observar(pacotes, tabela, centros=(_CENTRO, _CENTRO)).observacoes

    assert observacao.template == _REPRESENTANTE
    assert _possiveis(observacao) == _LISTA


def test_mesma_variante_em_caixas_quase_iguais_nao_se_repete_na_lista(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """Cada casamento do grupo chega duas vezes, a cópia um nanoponto ao lado (o que o `vistos` do
    núcleo deixaria passar se o arredondamento fosse outro): um grupo, três ids distintos."""
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(i) for i in _IDS]))

    def duplicar(casamentos: tuple[CasamentoGramatica, ...]) -> tuple[CasamentoGramatica, ...]:
        copias = tuple(
            replace(c, caixa=(c.caixa[0] + 1e-9, c.caixa[1], c.caixa[2], c.caixa[3]))
            for c in casamentos
        )
        return casamentos + copias

    resultado = _observar_com_casamentos(monkeypatch, pacotes, tabela, duplicar)

    (observacao,) = resultado.observacoes
    assert json.loads(_possiveis(observacao)) == sorted(_IDS)


# --- grupo de um ----------------------------------------------------------------------------


def test_grupo_de_um_ao_lado_de_um_grupo_continua_string(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """Mesmo desenho: v001 e v002 agrupam; v003, de outra classe, sai só e com o id puro."""
    variantes = [
        _variante("autoral-forma-v003", classe="OUTRA_AUTORAL"),
        _variante("autoral-forma-v002"),
        _variante("autoral-forma-v001"),
    ]
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, variantes))

    resultado = _observar(pacotes, tabela)

    assert sorted((o.template or "", _possiveis(o)) for o in resultado.observacoes) == [
        (_REPRESENTANTE, json.dumps(["autoral-forma-v001", "autoral-forma-v002"])),
        ("autoral-forma-v003", "autoral-forma-v003"),
    ]
    sozinha = next(o for o in resultado.observacoes if o.template == "autoral-forma-v003")
    assert not _possiveis(sozinha).startswith(("[", '"'))
    assert _observacao_igual_a_de_hoje(sozinha, pacotes, tabela)


def _observacao_igual_a_de_hoje(
    observacao: ObservacaoSimbolo, pacotes: tuple[Pacote, ...], tabela: TabelaGlifos
) -> bool:
    """A observação do casamento da mesma variante pelo `_observacao` sem grupo."""
    perfil = perfil_pacotes_modelo(pacotes, tabela)
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenhar_retangulo(pagina, _CENTRO)
        lida = pagina_para_gramaticas(pagina, 0, tabela)
        (casamento,) = [
            c
            for c in casar_variantes(lida, _enabled(pacotes))
            if c.variante["id"] == observacao.template
        ]
        esperada = _observacao(pagina, _FONTE, perfil.assinatura(), lida, casamento)
    return observacao == esperada


def test_grupo_de_um_com_os_pacotes_reais_tem_o_id_puro(tabela: TabelaGlifos) -> None:
    """Com os pacotes reais nada se agrupa: cada observação de um positivo autoral de
    `rect_diagonal` leva em `referencias_possiveis` o próprio id, nunca uma lista."""
    pacotes = carregar_pacotes()
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenhar_retangulo(pagina, _CENTRO, envolvente=True)
        resultado = observar_pacotes_modelo(
            pagina,
            documento_id="formas-comuns",
            documento_sha256=_SHA,
            pagina_numero=1,
            pacotes=pacotes,
            tabela=tabela,
        )

    assert resultado.observacoes
    for observacao in resultado.observacoes:
        assert _possiveis(observacao) == observacao.template


# --- reconciliação de ponta a ponta ---------------------------------------------------------


def test_reconciliacao_do_grupo_de_um_nao_e_referencia_ambigua(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(_REPRESENTANTE)]))

    (ocorrencia,) = reconcile_symbols(
        (_observar(pacotes, tabela),), CalibrationPolicy()
    ).occurrences

    assert ocorrencia.reference_ids == (_REPRESENTANTE,)
    assert "ambiguous_reference_id" not in ocorrencia.reasons
    assert "invalid_reference_id" not in ocorrencia.reasons
    assert "ambiguous_class_or_id" not in ocorrencia.reasons


def test_reconciliacao_do_grupo_com_vizinha_de_outra_classe_mantem_a_ambiguidade_de_classe(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """O agrupamento não esconde a classe: a ocorrência junta o grupo e a vizinha, com os dois
    motivos e os três ids."""
    variantes = [
        _variante("autoral-forma-v001"),
        _variante("autoral-forma-v002"),
        _variante("autoral-forma-v003", classe="OUTRA_AUTORAL"),
    ]
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, variantes))
    resultado = _observar(pacotes, tabela)
    assert len(resultado.observacoes) == 2

    (ocorrencia,) = reconcile_symbols((resultado,), CalibrationPolicy()).occurrences

    assert len(ocorrencia.observations) == 2
    assert ocorrencia.reference_ids == tuple(sorted(_IDS))
    assert "ambiguous_class_or_id" in ocorrencia.reasons
    assert "ambiguous_reference_id" in ocorrencia.reasons
    assert "invalid_reference_id" not in ocorrencia.reasons
    assert ocorrencia.decision == "review"


# --- componentes e primitivas do representante ----------------------------------------------


def _sem_referencias(observacao: ObservacaoSimbolo) -> tuple[Any, ...]:
    atributos = tuple(par for par in observacao.atributos if par[0] != "referencias_possiveis")
    return (
        observacao.fonte,
        observacao.geometria,
        observacao.alternativas,
        observacao.primitivas,
        observacao.template,
        observacao.score_bruto,
        atributos,
    )


def test_primitivas_do_grupo_sao_as_do_representante_sem_repeticao(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """Com envolvente, ganchos e haste o casamento tem componentes; o grupo de três sai igual ao
    v001 sozinho, fora a lista, e cada caminho do símbolo aparece numa primitiva só."""
    variantes = [_variante(i, gramatica=_ENVOLVIDA) for i in _IDS]
    (tmp_path / "grupo").mkdir()
    (tmp_path / "sozinho").mkdir()
    agrupados = _carrega(tmp_path / "grupo", _pacote(_FAMILIA, variantes))
    sozinho = _carrega(
        tmp_path / "sozinho", _pacote(_FAMILIA, [_variante(_REPRESENTANTE, gramatica=_ENVOLVIDA)])
    )

    def observar(pacotes: tuple[Pacote, ...]) -> tuple[ObservacaoSimbolo, CasamentoGramatica]:
        with pymupdf.open() as documento:
            pagina = documento.new_page(width=300, height=300)
            desenhar_retangulo(pagina, _CENTRO, envolvente=True, ganchos=True, haste=True)
            resultado = observar_pacotes_modelo(
                pagina,
                documento_id="formas-comuns",
                documento_sha256=_SHA,
                pagina_numero=1,
                pacotes=pacotes,
                tabela=tabela,
            )
            lida = pagina_para_gramaticas(pagina, 0, tabela)
            casamento = min(
                casar_variantes(lida, _enabled(pacotes)), key=lambda c: str(c.variante["id"])
            )
        (observacao,) = resultado.observacoes
        return observacao, casamento

    grupo, casamento = observar(agrupados)
    unica, _ = observar(sozinho)

    assert casamento.componentes
    assert _sem_referencias(grupo) == _sem_referencias(unica)
    indices = [primitiva.indice for primitiva in grupo.primitivas]
    assert len(indices) == len(set(indices)) == 1 + len(casamento.componentes)
    assert _possiveis(grupo) == _LISTA
    assert _possiveis(unica) == _REPRESENTANTE


def test_este_arquivo_passa_na_guarda_de_fonte() -> None:
    caminho = Path(__file__)
    assert _violacoes_de_fonte(caminho.read_text(encoding="utf-8"), caminho.name) == []
