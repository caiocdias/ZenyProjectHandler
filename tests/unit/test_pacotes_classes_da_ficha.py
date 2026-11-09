# mypy: disable-error-code="no-untyped-call"
"""E06.3.1 Task 3: as 58 variantes das classes da ficha nos pacotes, como `pending`.

Percorre os pacotes reais contra o inventario real. O conteudo antigo das tres familias
alteradas fica fixado aqui como golden por id (sha256 do JSON canonico da variante), sem
depender do historico do Git. Quando uma subetapa posterior habilitar uma dessas
variantes, o golden dessa variante muda de proposito junto com o pacote.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts.audit_symbol_packages import audit
from tests.fixtures.declarative_symbols.corpus import build_enabled_corpus
from tests.fixtures.symbol_grammars.estai import GRAMATICAS_ESTAI
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL
from tests.fixtures.symbol_grammars.stem_bars import CASOS_HASTE
from tests.fixtures.symbol_grammars.triangulo import CASOS_TRIANGULO
from tests.unit.test_symbol_packages_sem_memorizacao import verificar_pacote

from zeny_project_handler.adapters.analysis.declarative_symbols import (
    carregar_pacotes,
    observar_pacotes,
    perfil_pacotes,
)
from zeny_project_handler_server.symbol_support import installed_symbol_support

_ROOT = Path(__file__).resolve().parents[2]
_INVENTARIO = _ROOT / "docs/data/inventario-simbologia-v1.json"
_PACOTES = _ROOT / "src/zeny_project_handler/adapters/analysis/symbol_packages"

_FAMILIAS_NOVAS = ("family-f02-14", "family-f02-15", "family-f02-24", "family-f02-25")
_FAMILIAS_ALTERADAS = ("family-f02-18", "family-f02-19", "family-f02-21")
_NOVAS_POR_FAMILIA = {
    "family-f02-14": 15,
    "family-f02-15": 2,
    "family-f02-24": 2,
    "family-f02-25": 4,
    "family-f02-18": 23,
    "family-f02-19": 4,
    "family-f02-21": 8,
}
_ESTAGIOS_NOVOS = {"E04", "E05", "E06"}
# E06.3.4: as três variantes de ESTAI de f02-14 (existente, instalar, retirar).
_VARIANTES_ESTAI = ("cemig-eo-r3-s14-v001", "cemig-eo-r3-s14-v002", "cemig-eo-r3-s14-v003")
_CABECALHO = {"schema_version": 1, "profile_id": "profile-cemig-eo-r3", "source_id": "F02"}

# Variantes que ja existiam antes da Task 3 (a40739c), na ordem original do arquivo.
_GOLDEN_ANTIGAS = {
    "family-f02-18": (
        (
            "cemig-eo-r3-s18-v024",
            "252677e2cc1f727e5eac90db7a292d42edc3ea722d97ac2711448ea2d72ad182",
        ),
        (
            "cemig-eo-r3-s18-v025",
            "1c758722d679077363fd52afb9b8453e55e0f3f3135491d816e3845feed2722b",
        ),
        (
            "cemig-eo-r3-s18-v026",
            "c073884742aad9dc663b775cbb5365563f93fe7a411f112595ab2968346b6867",
        ),
        (
            "cemig-eo-r3-s18-v027",
            "9df5101d7ba0e489bd5b5cb26eb4da35125ef54469563016e4922c10f94e4164",
        ),
    ),
    "family-f02-19": (
        (
            "cemig-eo-r3-s19-v005",
            "cdabc654733b795193ae20c380b2274153a54e1eec4786a8aa666d8073ae3d17",
        ),
        (
            "cemig-eo-r3-s19-v006",
            "386bedf412f419bb2d5f8fada3d3ea1a03f312d36bd5a705d1bf83b50a1fbbaa",
        ),
        (
            "cemig-eo-r3-s19-v007",
            "de11d3ca7712ae0415984a71f65619fdc8c92dcda97090e3e9f250f26927fe81",
        ),
        (
            "cemig-eo-r3-s19-v008",
            "68ab64c45294ffbe656b808ff1b8fb8a71ee7f1b0f71a4b420ce5300f0cc3d2d",
        ),
        (
            "cemig-eo-r3-s19-v009",
            "ff09730cf81288c9f28aaa244ee7b749d50a1a8c200cdf939514caeebdd3daa5",
        ),
        (
            "cemig-eo-r3-s19-v010",
            "0eb6781700d1fdc9d0018689885aef938a4f006f7933ac9adf704712a4d27c91",
        ),
        (
            "cemig-eo-r3-s19-v011",
            "0e2cb79be4d919f1d81ce80f27f509f2a86debdd5c995e2bae34e49c46575942",
        ),
        (
            "cemig-eo-r3-s19-v012",
            "0a3de9ec486da486cf8f52909d38ac81c111822e746ce2948726a00d3e6376e1",
        ),
        (
            "cemig-eo-r3-s19-v013",
            "bcc06778846fab447c43c2b353ec5614010fccbaa7258e1761621c9a8bed928a",
        ),
        (
            "cemig-eo-r3-s19-v014",
            "63a335fda418532edfd632a4fbafc1b583e00a6c51d09f7b349e83f3eef4bd1c",
        ),
        (
            "cemig-eo-r3-s19-v015",
            "dc77511e62cf4b41317ca145eea7a170bc5be9e1cb5cc3aaeb1aa2b01ac57358",
        ),
        (
            "cemig-eo-r3-s19-v016",
            "6aa168fe4f558846b864d32d51f1cb5cefe28c4cd2937ed0ffe8046732cc1dad",
        ),
        (
            "cemig-eo-r3-s19-v017",
            "773e9cb6f970e8c4d1aea416e4bb17eae74a4d8221ad6a4d4f0bc6d0c16f2f06",
        ),
    ),
    "family-f02-21": (
        (
            "cemig-eo-r3-s21-v009",
            "bf4580f6c63563920c14ad7a175a67994a6de22cf3635fc78b471dd739026f42",
        ),
        (
            "cemig-eo-r3-s21-v010",
            "647004a4221c1ce9cc99be5a3efc055d4ddfd45f35b4504766426696103f2304",
        ),
        (
            "cemig-eo-r3-s21-v011",
            "f5d9b79bd9989bf8e8b87a8711f3a17a335b82ff605179ef05ac081ed765f71e",
        ),
        (
            "cemig-eo-r3-s21-v012",
            "dfa3ab560382a87262411ced6ab58bf30ccb53e4b3541152c04ba1124ef2284f",
        ),
        (
            "cemig-eo-r3-s21-v013",
            "28cb550b6c08672a07899f9c21ae3906d28e818b507f44ab9eca97fc9b9a7bef",
        ),
        (
            "cemig-eo-r3-s21-v014",
            "7087e7cd5e27eeaabb1f338aebe2bd76f5d4c1db4ac7dab24be6572784832dfd",
        ),
        (
            "cemig-eo-r3-s21-v015",
            "004648925e163dbba5ff71e0a5dd8524d9526d20dff704a0e4942a43c7da766f",
        ),
    ),
}


def _json(caminho: Path) -> dict[str, Any]:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert isinstance(dados, dict)
    return dados


def _variantes_novas_do_inventario() -> list[dict[str, Any]]:
    inventario = _json(_INVENTARIO)
    return [v for v in inventario["variants"] if v["owner_stage"] in _ESTAGIOS_NOVOS]


def _pacotes_reais() -> dict[str, dict[str, Any]]:
    return {c.stem: _json(c) for c in sorted(_PACOTES.glob("family-f02-*.json"))}


def _variantes_empacotadas() -> dict[str, tuple[str, dict[str, Any]]]:
    return {
        v["id"]: (familia, v)
        for familia, pacote in _pacotes_reais().items()
        for v in pacote["variants"]
    }


def _hash(variante: dict[str, Any]) -> str:
    texto = json.dumps(variante, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode()).hexdigest()


def _razao_esperada(nota_visual: str) -> str:
    return (
        f"Forma E01: {nota_visual}. Gramática sobre o modelo de desenho ainda não "
        "implementada para esta forma; positivo/negativo ainda não validado."
    )


_IDS_NOVAS = [v["id"] for v in _variantes_novas_do_inventario()]
_GRAMATICA_HABILITADAS = {
    **dict(CASOS_HASTE),
    **dict(CASOS_RECT_DIAGONAL),
    **dict(CASOS_TRIANGULO),
    **dict(zip(_VARIANTES_ESTAI, GRAMATICAS_ESTAI.values(), strict=True)),
}


def test_inventario_tem_58_variantes_de_e04_a_e06_nas_sete_familias() -> None:
    novas = _variantes_novas_do_inventario()
    assert len(novas) == 58
    assert Counter(v["family_id"] for v in novas) == _NOVAS_POR_FAMILIA
    assert len(set(_IDS_NOVAS)) == 58


@pytest.mark.parametrize("variant_id", _IDS_NOVAS)
def test_variante_nova_empacotada_espelha_o_inventario_e_fica_pending(variant_id: str) -> None:
    referencia = next(v for v in _variantes_novas_do_inventario() if v["id"] == variant_id)
    empacotadas = _variantes_empacotadas()
    assert variant_id in empacotadas, "variante do inventario sem pacote"
    familia, item = empacotadas[variant_id]
    assert familia == referencia["family_id"]
    assert item["class_code"] == referencia["class_code"]
    assert item["destination"] == referencia["destination"]
    assert item["visual_note"] == referencia["visual_note"]
    assert item["source_ref"] == referencia["source_refs"][0]
    informativa = referencia["function"] in {"convention", "non_asset"}
    assert item["role"] == ("informative" if informativa else "operational")
    if variant_id in _GRAMATICA_HABILITADAS:
        assert item["recognition"] == {
            "status": "enabled",
            "grammar": _GRAMATICA_HABILITADAS[variant_id],
            "negative_examples": referencia["confusable_negatives"],
        }
    else:
        assert item["recognition"] == {
            "status": "pending",
            "reason": _razao_esperada(referencia["visual_note"]),
            "negative_examples": referencia["confusable_negatives"],
        }
    assert set(item) == {
        "id",
        "class_code",
        "role",
        "destination",
        "source_ref",
        "visual_note",
        "recognition",
    }


@pytest.mark.parametrize("familia", _FAMILIAS_NOVAS)
def test_familia_nova_tem_cabecalho_e_todas_as_variantes_do_inventario_na_ordem(
    familia: str,
) -> None:
    pacote = _pacotes_reais()[familia]
    do_inventario = [v for v in _variantes_novas_do_inventario() if v["family_id"] == familia]
    assert {k: v for k, v in pacote.items() if k != "variants"} == {
        **_CABECALHO,
        "family_id": familia,
    }
    assert {v["profile_id"] for v in do_inventario} == {pacote["profile_id"]}
    assert {r["source_id"] for v in do_inventario for r in v["source_refs"]} == {
        pacote["source_id"]
    }
    assert [v["id"] for v in pacote["variants"]] == [v["id"] for v in do_inventario]


@pytest.mark.parametrize("familia", _FAMILIAS_ALTERADAS)
def test_variantes_antigas_das_familias_alteradas_ficam_intactas_e_na_frente(
    familia: str,
) -> None:
    pacote = _pacotes_reais()[familia]
    golden = _GOLDEN_ANTIGAS[familia]
    assert {k: v for k, v in pacote.items() if k != "variants"} == {
        **_CABECALHO,
        "family_id": familia,
    }
    atuais = pacote["variants"]
    assert [v["id"] for v in atuais[: len(golden)]] == [i for i, _ in golden]
    assert [_hash(v) for v in atuais[: len(golden)]] == [h for _, h in golden]
    novas = [v["id"] for v in _variantes_novas_do_inventario() if v["family_id"] == familia]
    assert [v["id"] for v in atuais[len(golden) :]] == novas
    assert len(novas) == _NOVAS_POR_FAMILIA[familia]


def test_as_demais_familias_nao_ganharam_variantes_de_e04_a_e06() -> None:
    novas = set(_IDS_NOVAS)
    for familia, pacote in _pacotes_reais().items():
        if familia in _NOVAS_POR_FAMILIA:
            continue
        assert not novas & {v["id"] for v in pacote["variants"]}, familia


def test_o_total_antigo_mais_o_novo_fecha_em_423() -> None:
    antigas = sum(len(g) for g in _GOLDEN_ANTIGAS.values())
    assert antigas == 24
    assert sum(_NOVAS_POR_FAMILIA.values()) == 58
    assert len(_variantes_empacotadas()) == 423


def test_carregar_pacotes_aceita_os_31_pacotes_reais() -> None:
    pacotes = carregar_pacotes()
    assert len(pacotes) == 31
    assert {p["family_id"] for p in pacotes} >= set(_FAMILIAS_NOVAS)
    assert sum(len(p["variants"]) for p in pacotes) == 423


def test_pending_nao_gera_observacao_e_a_saida_e_a_de_antes(tmp_path: Path) -> None:
    caminho = tmp_path / "corpus.pdf"
    referencia = build_enabled_corpus(caminho)
    sha = hashlib.sha256(caminho.read_bytes()).hexdigest()
    novos = set(_IDS_NOVAS)
    atuais = carregar_pacotes()
    de_antes = tuple(
        {**p, "variants": [v for v in p["variants"] if v["id"] not in novos]}
        for p in atuais
        if any(v["id"] not in novos for v in p["variants"])
    )
    assert len(de_antes) == 27
    with pymupdf.open(caminho) as documento:
        assert len(documento) == referencia["pages"] > 0
        for pagina in documento:
            agora = observar_pacotes(
                pagina,
                documento_id="t3",
                documento_sha256=sha,
                pagina_numero=pagina.number + 1,
                pacotes=atuais,
            )
            antes = observar_pacotes(
                pagina,
                documento_id="t3",
                documento_sha256=sha,
                pagina_numero=pagina.number + 1,
                pacotes=de_antes,
            )
            # So a assinatura do metodo muda: ela identifica o conjunto de pacotes (cache).
            assert all(o.metodo_assinatura == agora.perfil.assinatura() for o in agora.observacoes)
            assert all(o.metodo_assinatura == antes.perfil.assinatura() for o in antes.observacoes)
            assert agora.perfil.assinatura() != antes.perfil.assinatura()
            assert [replace(o, metodo_assinatura=sha) for o in agora.observacoes] == [
                replace(o, metodo_assinatura=sha) for o in antes.observacoes
            ]
            assert agora.coberturas == antes.coberturas
            assert agora.perfil.classes_suportadas == antes.perfil.classes_suportadas
            ids = {dict(o.atributos)["variante_inventario"] for o in agora.observacoes}
            assert not ids & novos


@pytest.mark.parametrize("familia", _FAMILIAS_NOVAS)
def test_familia_so_de_pending_nao_suporta_nenhuma_classe(familia: str) -> None:
    pacote = next(p for p in carregar_pacotes() if p["family_id"] == familia)
    assert perfil_pacotes((pacote,)).classes_suportadas == ()


def _copiar(tmp_path: Path) -> Path:
    destino = tmp_path / "pacotes"
    shutil.copytree(_PACOTES, destino)
    return destino


def test_auditor_real_fecha_sem_erro_com_369_pending_e_54_enabled() -> None:
    relato = audit()
    assert relato["errors"] == []
    assert (relato["expected_variants"], relato["expected_families"]) == (423, 31)
    assert (relato["package_variants"], relato["package_families"]) == (423, 31)
    assert (relato["pending"], relato["enabled"]) == (369, 54)
    assert relato["complete_recognition"] is False
    por_estagio = relato["by_owner_stage"]
    assert set(por_estagio) == {"E04", "E05", "E06", "E07"}
    for estagio in _ESTAGIOS_NOVOS:
        item = por_estagio[estagio]
        # E04: hastes de f02-19 e f02-21 e PARA_RAIOS_BT; E05: TRANSFORMADOR de f02-18;
        # E06: ESTAI de f02-14 (E06.3.4).
        habilitadas = {"E04": 12, "E05": 15, "E06": 3}[estagio]
        assert item["packaged"] == item["expected"] == item["pending"] + habilitadas
        assert item["enabled"] == habilitadas
        # E04 fica inteira habilitada (12 de 12); E05 tem as 15 de TRANSFORMADOR habilitadas e
        # 14 pending; E06 tem as 3 de ESTAI habilitadas e o resto pending. Só E04 fica sem pending.
        assert (item["pending"] == 0) == (estagio == "E04")
    assert sum(por_estagio[e]["expected"] for e in _ESTAGIOS_NOVOS) == 58


@pytest.mark.parametrize("familia", _FAMILIAS_NOVAS)
def test_familia_nova_inteira_ausente_acusa_cada_variante_e_a_familia(
    tmp_path: Path, familia: str
) -> None:
    pasta = _copiar(tmp_path)
    (pasta / f"{familia}.json").unlink()
    erros = audit(package_dir=pasta)["errors"]
    faltantes = [v["id"] for v in _variantes_novas_do_inventario() if v["family_id"] == familia]
    esperados = [f"missing variant: {i}" for i in faltantes] + [f"missing family: {familia}"]
    assert sorted(erros) == sorted(esperados)


def test_uma_variante_ausente_de_familia_existente_nao_acusa_familia(tmp_path: Path) -> None:
    pasta = _copiar(tmp_path)
    caminho = pasta / "family-f02-18.json"
    pacote = _json(caminho)
    removida = pacote["variants"].pop()["id"]
    caminho.write_text(json.dumps(pacote), encoding="utf-8")
    assert audit(package_dir=pasta)["errors"] == [f"missing variant: {removida}"]


def test_familia_sem_arquivo_com_variantes_em_outra_familia_acusa_mismatch(
    tmp_path: Path,
) -> None:
    pasta = _copiar(tmp_path)
    movidas = _json(pasta / "family-f02-15.json")["variants"]
    (pasta / "family-f02-15.json").unlink()
    destino = pasta / "family-f02-14.json"
    pacote = _json(destino)
    pacote["variants"].extend(movidas)
    destino.write_text(json.dumps(pacote), encoding="utf-8")
    relato = audit(package_dir=pasta)
    esperados = [f"{v['id']}: family mismatch" for v in movidas]
    assert sorted(relato["errors"]) == sorted(esperados)
    assert relato["complete_recognition"] is False
    assert relato["package_families"] == 30


def test_familia_vazia_acusa_as_variantes_e_nao_a_familia(tmp_path: Path) -> None:
    pasta = _copiar(tmp_path)
    caminho = pasta / "family-f02-15.json"
    pacote = _json(caminho)
    ids = [v["id"] for v in pacote["variants"]]
    pacote["variants"] = []
    caminho.write_text(json.dumps(pacote), encoding="utf-8")
    relato = audit(package_dir=pasta)
    assert sorted(relato["errors"]) == sorted(f"missing variant: {i}" for i in ids)
    assert relato["complete_recognition"] is False


def test_familia_vazia_nao_carrega_como_pacote_valido(tmp_path: Path) -> None:
    pasta = _copiar(tmp_path)
    caminho = pasta / "family-f02-15.json"
    pacote = _json(caminho)
    pacote["variants"] = []
    caminho.write_text(json.dumps(pacote), encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_pacotes(packages_dir=pasta)


def test_pacote_novo_sem_razao_ou_com_status_invalido_acusa(tmp_path: Path) -> None:
    pasta = _copiar(tmp_path)
    caminho = pasta / "family-f02-24.json"
    pacote = _json(caminho)
    primeiro, segundo = pacote["variants"]
    del primeiro["recognition"]["reason"]
    segundo["recognition"]["status"] = "ready"
    caminho.write_text(json.dumps(pacote), encoding="utf-8")
    esperados = [
        f"{primeiro['id']}: pending without reason",
        f"{segundo['id']}: invalid recognition status",
    ]
    assert sorted(audit(package_dir=pasta)["errors"]) == sorted(esperados)


def test_guarda_contra_memorizacao_alcanca_e_aprova_os_arquivos_novos_e_alterados() -> None:
    cobertos = {c.name for c in _PACOTES.glob("*.json")}
    for familia in (*_FAMILIAS_NOVAS, *_FAMILIAS_ALTERADAS):
        nome = f"{familia}.json"
        assert nome in cobertos
        dados = json.loads((_PACOTES / nome).read_text(encoding="utf-8"))
        assert verificar_pacote(dados) == [], nome


def test_tabela_de_suporte_mostra_as_quatro_familias_novas_so_pendentes_menos_o_estai() -> None:
    suporte = {item.family_id: item for item in installed_symbol_support()}
    assert len(suporte) == 31
    pacotes = _pacotes_reais()
    for familia in _FAMILIAS_NOVAS:
        item = suporte[familia]
        # f02-14 tem as 3 variantes de ESTAI habilitadas (E06.3.4); as demais, só pendentes.
        habilitadas = _VARIANTES_ESTAI if familia == "family-f02-14" else ()
        assert item.enabled_reference_ids == habilitadas
        assert list(item.pending_reference_ids) == [
            v["id"] for v in pacotes[familia]["variants"] if v["id"] not in habilitadas
        ]
        assert len(item.pending_reference_ids) == _NOVAS_POR_FAMILIA[familia] - len(habilitadas)
        assert item.pending_reasons
        for razao in item.pending_reasons:
            assert razao.startswith("Forma E01: ")
            assert razao.endswith("positivo/negativo ainda não validado.")
    assert sum(len(i.pending_reference_ids) for i in suporte.values()) == 369
    assert sum(len(i.enabled_reference_ids) for i in suporte.values()) == 54
