# mypy: disable-error-code="no-untyped-call"
"""Formas comuns numa observação do modelo (R-E06.3.3.2.2-2).

Casamentos com a mesma página, o mesmo caminho âncora, a mesma caixa arredondada, a mesma
gramática e os mesmos `class_code`, `family_id`, `role` e `destination` viram uma observação: o
representante é o menor id, e `referencias_possiveis` leva a lista JSON ordenada dos ids. Pacotes
e desenhos autorais, sobre o tipo `rect_diagonal`; nada vem de folha real.
"""

from __future__ import annotations

import copy
import itertools
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.rect_diagonal import desenhar_retangulo
from tests.fixtures.symbol_grammars.triangulo import GRUPO_DA_VARIANTE
from tests.unit.test_symbol_packages_sem_memorizacao import _violacoes_de_fonte

from zeny_project_handler.adapters.analysis.declarative_symbols import _enabled, carregar_pacotes
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import casar_variantes
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
from zeny_project_handler.domain.symbols import FonteObservacaoSimbolo, ResultadoMetodoSimbolos

Pacote = dict[str, Any]

_SHA: Final = "c" * 64
_FAMILIA: Final = "family-autoral-formas"
_OUTRA_FAMILIA: Final = "family-autoral-formas-b"
_CLASSE: Final = "PARA_RAIOS_AUTORAL"
_CENTRO: Final[Ponto] = (150.0, 150.0)
_OUTRO_CENTRO: Final[Ponto] = (80.0, 220.0)
_GRAMATICA: Final[dict[str, Any]] = {
    "kind": "rect_diagonal",
    "enclosure": "none",
    "removal_mark": False,
    "max_span": 72,
}
# Fora da ordem de id, para o representante não ser o primeiro do pacote por acaso.
_IDS: Final = ("autoral-forma-v003", "autoral-forma-v001", "autoral-forma-v002")
_IDS_ORDENADOS: Final = sorted(_IDS)


@pytest.fixture(scope="module")
def tabela() -> TabelaGlifos:
    return carregar_tabela_glifos()


def _variante(
    variante_id: str,
    *,
    gramatica: dict[str, Any] | None = None,
    classe: str = _CLASSE,
    papel: str = "operational",
    destino: str = "equipment_review",
) -> Pacote:
    return {
        "id": variante_id,
        "class_code": classe,
        "role": papel,
        "destination": destino,
        "source_ref": {
            "source_id": "F02",
            "pdf_page": 1,
            "locator": "desenho autoral",
            "review_status": "synthetic_fixture",
        },
        "visual_note": "Retângulo atravessado por diagonal autoral",
        "recognition": {
            "status": "enabled",
            "grammar": copy.deepcopy(_GRAMATICA if gramatica is None else gramatica),
            "negative_examples": ["retângulo com duas diagonais"],
        },
    }


def _pacote(familia: str, variantes: Sequence[Pacote]) -> Pacote:
    return {
        "schema_version": 1,
        "family_id": familia,
        "profile_id": "profile-autoral",
        "source_id": "F02",
        "variants": list(variantes),
    }


def _carrega(tmp_path: Path, *pacotes: Pacote) -> tuple[Pacote, ...]:
    for pacote in pacotes:
        destino = tmp_path / f"{pacote['family_id']}.json"
        destino.write_text(json.dumps(pacote), encoding="utf-8")
    return carregar_pacotes(packages_dir=tmp_path)


def _observar(
    pacotes: tuple[Pacote, ...], tabela: TabelaGlifos, centros: Sequence[Ponto] = (_CENTRO,)
) -> ResultadoMetodoSimbolos:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        for centro in centros:
            desenhar_retangulo(pagina, centro)
        return observar_pacotes_modelo(
            pagina,
            documento_id="formas-comuns",
            documento_sha256=_SHA,
            pagina_numero=1,
            pacotes=pacotes,
            tabela=tabela,
        )


def _atributos(resultado: ResultadoMetodoSimbolos) -> list[dict[str, Any]]:
    return [dict(observacao.atributos) for observacao in resultado.observacoes]


def test_variantes_de_gramatica_igual_viram_uma_observacao(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(i) for i in _IDS]))

    resultado = _observar(pacotes, tabela)

    assert len(resultado.observacoes) == 1
    observacao = resultado.observacoes[0]
    atributos = dict(observacao.atributos)
    assert observacao.template == "autoral-forma-v001"
    assert atributos["variante_inventario"] == "autoral-forma-v001"
    assert atributos["referencias_possiveis"] == json.dumps(_IDS_ORDENADOS)
    assert json.loads(str(atributos["referencias_possiveis"])) == [
        "autoral-forma-v001",
        "autoral-forma-v002",
        "autoral-forma-v003",
    ]
    assert [a.classe for a in observacao.alternativas] == [_CLASSE]


def test_gramaticas_diferentes_no_mesmo_desenho_nao_se_agrupam(
    tmp_path: Path, tabela: TabelaGlifos
) -> None:
    """`max_span` 40 e 72 casam o mesmo corpo de 8 pt; as gramáticas diferem, e o grupo também."""
    estreita = {**_GRAMATICA, "max_span": 40}
    pacotes = _carrega(
        tmp_path,
        _pacote(
            _FAMILIA,
            [_variante("autoral-forma-v001"), _variante("autoral-forma-v002", gramatica=estreita)],
        ),
    )

    resultado = _observar(pacotes, tabela)

    assert sorted(o.template or "" for o in resultado.observacoes) == [
        "autoral-forma-v001",
        "autoral-forma-v002",
    ]
    assert sorted(a["referencias_possiveis"] for a in _atributos(resultado)) == [
        "autoral-forma-v001",
        "autoral-forma-v002",
    ]


def test_grupo_de_um_nao_muda(tmp_path: Path, tabela: TabelaGlifos) -> None:
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante("autoral-forma-v001")]))
    perfil = perfil_pacotes_modelo(pacotes, tabela)
    fonte = FonteObservacaoSimbolo(
        documento_id="formas-comuns", documento_sha256=_SHA, pagina_numero=1, camada="base"
    )

    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenhar_retangulo(pagina, _CENTRO)
        resultado = observar_pacotes_modelo(
            pagina,
            documento_id="formas-comuns",
            documento_sha256=_SHA,
            pagina_numero=1,
            pacotes=pacotes,
            tabela=tabela,
            perfil=perfil,
        )
        lida = pagina_para_gramaticas(pagina, 0, tabela)
        (casamento,) = casar_variantes(lida, _enabled(pacotes))
        esperada = _observacao(pagina, fonte, perfil.assinatura(), lida, casamento)

    (observacao,) = resultado.observacoes
    assert observacao == esperada
    assert observacao.id == esperada.id
    assert observacao.template == "autoral-forma-v001"
    assert dict(observacao.atributos) == {
        "familia_inventario": _FAMILIA,
        "variante_inventario": "autoral-forma-v001",
        "referencias_possiveis": "autoral-forma-v001",
        "papel": "operational",
        "destino": "equipment_review",
        "contexto": "unknown",
        "fonte_referencia": "F02",
        "localizador_referencia": "desenho autoral",
        "gramatica": "rect_diagonal",
    }


def test_caixas_diferentes_nao_se_agrupam(tmp_path: Path, tabela: TabelaGlifos) -> None:
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(i) for i in _IDS]))

    resultado = _observar(pacotes, tabela, centros=(_CENTRO, _OUTRO_CENTRO))

    assert len(resultado.observacoes) == 2
    assert len({o.geometria for o in resultado.observacoes}) == 2
    for observacao in resultado.observacoes:
        atributos = dict(observacao.atributos)
        assert observacao.template == "autoral-forma-v001"
        assert atributos["referencias_possiveis"] == json.dumps(_IDS_ORDENADOS)


def _par_com_classe_diferente(tmp_path: Path) -> tuple[Pacote, ...]:
    variantes = [_variante("autoral-forma-v001"), _variante("autoral-forma-v002", classe="OUTRA")]
    return _carrega(tmp_path, _pacote(_FAMILIA, variantes))


def _par_com_familia_diferente(tmp_path: Path) -> tuple[Pacote, ...]:
    return _carrega(
        tmp_path,
        _pacote(_FAMILIA, [_variante("autoral-forma-v001")]),
        _pacote(_OUTRA_FAMILIA, [_variante("autoral-forma-v002")]),
    )


def _par_com_destino_diferente(tmp_path: Path) -> tuple[Pacote, ...]:
    variantes = [
        _variante("autoral-forma-v001"),
        _variante("autoral-forma-v002", destino="network_context"),
    ]
    return _carrega(tmp_path, _pacote(_FAMILIA, variantes))


def _par_com_papel_diferente(tmp_path: Path) -> tuple[Pacote, ...]:
    """O carregador amarra o papel ao destino; aqui só o papel muda, depois de carregar."""
    (pacote,) = _carrega(
        tmp_path,
        _pacote(_FAMILIA, [_variante("autoral-forma-v001"), _variante("autoral-forma-v002")]),
    )
    alterado = copy.deepcopy(pacote)
    alterado["variants"][1]["role"] = "informative"
    return (alterado,)


@pytest.mark.parametrize(
    "construir",
    [
        pytest.param(_par_com_classe_diferente, id="class_code"),
        pytest.param(_par_com_familia_diferente, id="family_id"),
        pytest.param(_par_com_destino_diferente, id="destination"),
        pytest.param(_par_com_papel_diferente, id="role"),
    ],
)
def test_classes_diferentes_nao_se_agrupam(
    tmp_path: Path, tabela: TabelaGlifos, construir: Any
) -> None:
    pacotes = construir(tmp_path)

    resultado = _observar(pacotes, tabela)

    assert sorted(o.template or "" for o in resultado.observacoes) == [
        "autoral-forma-v001",
        "autoral-forma-v002",
    ]
    assert sorted(a["referencias_possiveis"] for a in _atributos(resultado)) == [
        "autoral-forma-v001",
        "autoral-forma-v002",
    ]


def test_reconciliacao_le_a_lista(tmp_path: Path, tabela: TabelaGlifos) -> None:
    pacotes = _carrega(tmp_path, _pacote(_FAMILIA, [_variante(i) for i in _IDS]))
    resultado = _observar(pacotes, tabela)

    reconciliacao = reconcile_symbols((resultado,), CalibrationPolicy())

    (ocorrencia,) = reconciliacao.occurrences
    # Uma observação só: a lista vem dela, e não da fusão de várias observações.
    assert len(ocorrencia.observations) == 1
    assert ocorrencia.reference_ids == tuple(_IDS_ORDENADOS)
    assert "ambiguous_reference_id" in ocorrencia.reasons
    assert "invalid_reference_id" not in ocorrencia.reasons
    assert "ambiguous_class_or_id" not in ocorrencia.reasons
    assert ocorrencia.decision == "review"


def _chave_de_forma(pacote: Pacote, variante: Pacote) -> tuple[Any, ...]:
    return (
        variante["recognition"]["grammar"],
        variante["class_code"],
        pacote["family_id"],
        variante["role"],
        variante["destination"],
    )


def test_habilitadas_reais_so_compartilham_a_chave_dentro_do_grupo_da_r1() -> None:
    """Com TRANSFORMADOR habilitado (Task 4), os únicos pares com a mesma chave nos pacotes reais
    são as variantes de um mesmo grupo de forma da R-E06.3.3.2.2-1, todas de TRANSFORMADOR: nenhum
    par atravessa classe, família, papel ou destino, e as demais habilitadas seguem sozinhas."""
    habilitadas = _enabled(carregar_pacotes())

    pares = {
        (primeira[1]["id"], segunda[1]["id"])
        for primeira, segunda in itertools.combinations(habilitadas, 2)
        if _chave_de_forma(*primeira) == _chave_de_forma(*segunda)
    }
    do_mesmo_grupo = {
        (primeira, segunda)
        for primeira, segunda in itertools.combinations(sorted(GRUPO_DA_VARIANTE), 2)
        if GRUPO_DA_VARIANTE[primeira] == GRUPO_DA_VARIANTE[segunda]
    }
    por_id = {variante["id"]: variante for _, variante in habilitadas}

    assert habilitadas
    assert {tuple(sorted(par)) for par in pares} == do_mesmo_grupo
    assert len(do_mesmo_grupo) == 3 * 1 + 3 * 3  # três grupos de dois e três de três
    assert {por_id[i]["class_code"] for par in pares for i in par} == {"TRANSFORMADOR"}


def test_este_arquivo_passa_na_guarda_de_fonte() -> None:
    caminho = Path(__file__)
    assert _violacoes_de_fonte(caminho.read_text(encoding="utf-8"), caminho.name) == []
