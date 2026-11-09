"""Ataque à habilitação das 8 variantes de haste: gramática literal, motor, modelo e relatos."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final, cast

import pymupdf
import pytest
from scripts.audit_symbol_packages import audit
from tests.fixtures.declarative_symbols.corpus import build_enabled_corpus
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL
from tests.fixtures.symbol_grammars.stem_bars import (
    ALTERNADAS,
    CASOS_HASTE,
    DECRESCENTES,
    NEGATIVOS,
    desenhar_haste,
    desenhar_positivo,
)

from zeny_project_handler.adapters.analysis.declarative_symbols import (
    GRAMATICAS_SO_MODELO,
    carregar_pacotes,
    observar_pacotes,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import carregar_tabela_glifos
from zeny_project_handler.adapters.analysis.model_symbols import observar_pacotes_modelo
from zeny_project_handler_server.deliverable_exports import _symbol_support_sheet
from zeny_project_handler_server.symbol_support import installed_symbol_support

_PACOTES: Final = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "zeny_project_handler"
    / "adapters"
    / "analysis"
    / "symbol_packages"
)
_SHA: Final = "b" * 64
_CLASSES_HASTE: Final = {"ATERRAMENTO", "PARA_RAIOS_MT"}

# Tabela escrita à mão, independente de CASOS_HASTE: (classe, barras, afilamento, envolvente, X).
_ESPERADO: Final[dict[str, tuple[str, int, str, str, bool]]] = {
    "cemig-eo-r3-s19-v001": ("ATERRAMENTO", 3, "decreasing", "none", False),
    "cemig-eo-r3-s19-v002": ("ATERRAMENTO", 3, "decreasing", "ellipse", False),
    "cemig-eo-r3-s19-v003": ("ATERRAMENTO", 3, "decreasing", "ellipse", True),
    "cemig-eo-r3-s19-v004": ("ATERRAMENTO", 3, "decreasing", "none", True),
    "cemig-eo-r3-s21-v005": ("PARA_RAIOS_MT", 4, "alternating", "none", False),
    "cemig-eo-r3-s21-v006": ("PARA_RAIOS_MT", 4, "alternating", "ellipse", False),
    "cemig-eo-r3-s21-v007": ("PARA_RAIOS_MT", 4, "alternating", "ellipse", True),
    "cemig-eo-r3-s21-v008": ("PARA_RAIOS_MT", 4, "alternating", "none", True),
}


def _variantes() -> dict[str, dict[str, Any]]:
    return {v["id"]: v for pacote in carregar_pacotes() for v in pacote["variants"]}


def _observar_modelo(pagina: pymupdf.Page) -> Any:
    return observar_pacotes_modelo(
        pagina,
        documento_id="hastes",
        documento_sha256=_SHA,
        pagina_numero=pagina.number + 1,
        pacotes=carregar_pacotes(),
        tabela=carregar_tabela_glifos(),
    )


def _classes(resultado: Any) -> list[str | None]:
    return [o.alternativas[0].classe for o in resultado.observacoes]


@pytest.mark.parametrize("variante", sorted(_ESPERADO))
def test_gramatica_do_json_bate_com_a_tabela_escrita_a_mao(variante: str) -> None:
    classe, barras, afilamento, envolvente, x = _ESPERADO[variante]
    item = _variantes()[variante]
    assert item["class_code"] == classe
    assert item["recognition"]["status"] == "enabled"
    assert item["recognition"]["grammar"] == {
        "kind": "stem_bars",
        "bars": barras,
        "taper": afilamento,
        "enclosure": envolvente,
        "removal_mark": x,
        "max_span": 72,
    }
    assert "reason" not in item["recognition"]


def test_so_as_oito_hastes_tem_gramatica_stem_bars_e_a_fixture_cobre_as_mesmas() -> None:
    com_haste = {
        i
        for i, v in _variantes().items()
        if v["recognition"].get("grammar", {}).get("kind") == "stem_bars"
    }
    assert com_haste == set(_ESPERADO)
    assert {i for i, _ in CASOS_HASTE} == set(_ESPERADO)
    assert {
        "stem_bars",
        "rect_diagonal",
        "split_triangle",
        "forked_stem",
        "disc_mark",
    } == GRAMATICAS_SO_MODELO


@pytest.mark.parametrize("familia", ["family-f02-19", "family-f02-21"])
def test_as_quatro_situacoes_de_cada_familia_sao_distintas(familia: str) -> None:
    pacote = next(p for p in carregar_pacotes() if p["family_id"] == familia)
    chaves = [
        (v["recognition"]["grammar"]["enclosure"], v["recognition"]["grammar"]["removal_mark"])
        for v in pacote["variants"]
        if v["recognition"].get("grammar", {}).get("kind") == "stem_bars"
    ]
    assert sorted(chaves) == [
        ("ellipse", False),
        ("ellipse", True),
        ("none", False),
        ("none", True),
    ]


def test_variantes_nao_habilitadas_das_duas_familias_seguem_pending_com_razao() -> None:
    for familia in ("family-f02-19", "family-f02-21"):
        pacote = next(p for p in carregar_pacotes() if p["family_id"] == familia)
        for v in pacote["variants"]:
            reconhecimento = v["recognition"]
            if v["id"] in _ESPERADO or v["id"] in {i for i, _ in CASOS_RECT_DIAGONAL}:
                continue
            assert reconhecimento["status"] == "pending", v["id"]
            assert reconhecimento["reason"], v["id"]
            assert "grammar" not in reconhecimento, v["id"]


def test_negative_examples_das_hastes_sao_textos_nao_vazios_e_sem_repeticao() -> None:
    for variante in _ESPERADO:
        negativos = _variantes()[variante]["recognition"]["negative_examples"]
        assert isinstance(negativos, list)
        assert negativos
        assert all(isinstance(n, str) and n.strip() for n in negativos)
        assert len(set(negativos)) == len(negativos)


@pytest.mark.parametrize("variante", sorted(_ESPERADO))
@pytest.mark.parametrize("rotacao", [0, 90])
def test_pacotes_reais_modelo_le_a_haste_e_o_motor_antigo_nao(variante: str, rotacao: int) -> None:
    classe = _ESPERADO[variante][0]
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        desenhar_positivo(pagina, variante)
        pagina.set_rotation(rotacao)
        pelo_modelo = _observar_modelo(pagina)
        pelo_motor = observar_pacotes(
            pagina,
            documento_id="hastes",
            documento_sha256=_SHA,
            pagina_numero=1,
            pacotes=carregar_pacotes(),
        )
    assert _classes(pelo_modelo) == [classe]
    assert pelo_motor.observacoes == ()
    assert not _CLASSES_HASTE & set(pelo_motor.coberturas[0].classes_avaliadas)
    assert set(pelo_modelo.coberturas[0].classes_avaliadas) >= _CLASSES_HASTE


@pytest.mark.parametrize("nome", sorted(NEGATIVOS))
def test_pacotes_reais_negativo_nao_gera_aterramento_nem_para_raios(nome: str) -> None:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=300, height=300)
        NEGATIVOS[nome](pagina)
        classes = _classes(_observar_modelo(pagina))
    assert not _CLASSES_HASTE & set(classes)


def test_pacotes_reais_pagina_vazia_e_corpus_das_22_nao_leem_haste(tmp_path: Path) -> None:
    caminho = tmp_path / "corpus.pdf"
    build_enabled_corpus(caminho)
    with pymupdf.open(caminho) as documento:  # type: ignore[no-untyped-call]
        assert len(documento) > 0
        for pagina in documento:
            assert not _CLASSES_HASTE & set(_classes(_observar_modelo(pagina)))
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        assert _classes(_observar_modelo(documento.new_page(width=300, height=300))) == []


def test_aterramento_e_para_raios_na_mesma_pagina_dao_uma_leitura_de_cada() -> None:
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=400, height=300)
        desenhar_haste(pagina, DECRESCENTES, (100.0, 150.0))
        desenhar_haste(pagina, ALTERNADAS, (300.0, 150.0), envolvente=True)
        classes = _classes(_observar_modelo(pagina))
    assert sorted(str(c) for c in classes) == ["ATERRAMENTO", "PARA_RAIOS_MT"]


def test_tabela_de_suporte_lista_as_quatro_hastes_de_cada_familia_como_enabled() -> None:
    suporte = {item.family_id: item for item in installed_symbol_support()}
    for familia, prefixo in (("family-f02-19", "s19"), ("family-f02-21", "s21")):
        item = suporte[familia]
        esperadas = {i for i in _ESPERADO if f"-{prefixo}-" in i}
        assert len(esperadas) == 4
        assert esperadas <= set(item.enabled_reference_ids)
        assert not esperadas & set(item.pending_reference_ids)
        assert not set(item.enabled_reference_ids) & set(item.pending_reference_ids)
        assert all(razao for razao in item.pending_reasons)


def test_exportacao_xlsx_de_suporte_leva_as_hastes_nas_enabled_e_fora_das_pending() -> None:
    sessao = cast(Any, SimpleNamespace(symbol_support=installed_symbol_support()))
    planilha = _symbol_support_sheet(sessao)
    por_familia = {linha[0]: linha for linha in planilha.rows}
    for variante, (classe, *_) in _ESPERADO.items():
        familia = "family-f02-19" if classe == "ATERRAMENTO" else "family-f02-21"
        _, habilitadas, pendentes, *_ = por_familia[familia]
        assert variante in str(habilitadas).split("; ")
        assert variante not in str(pendentes).split("; ")
    total = sum(len(str(linha[1]).split("; ")) for linha in planilha.rows if linha[1])
    assert total == 52


def test_auditor_acusa_haste_habilitada_sem_gramatica(tmp_path: Path) -> None:
    pasta = tmp_path / "pacotes"
    shutil.copytree(_PACOTES, pasta)
    alvo = pasta / "family-f02-19.json"
    dados = json.loads(alvo.read_text(encoding="utf-8"))
    haste = next(v for v in dados["variants"] if v["id"] in _ESPERADO)
    del haste["recognition"]["grammar"]
    alvo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    assert audit(package_dir=pasta)["errors"]


def test_auditor_real_relata_as_oito_hastes_no_estagio_e04() -> None:
    relato = audit()
    assert relato["errors"] == []
    assert (relato["enabled"], relato["pending"]) == (52, 371)
    assert relato["by_owner_stage"]["E04"]["enabled"] >= 8
