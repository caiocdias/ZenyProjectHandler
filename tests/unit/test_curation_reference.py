from __future__ import annotations

import copy
import hashlib
import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts import curation_reference
from scripts.curation_reference import (
    CAMINHO_ESQUEMA,
    CLASSE_LOCAL,
    ESQUEMA_REFERENCIA,
    FAMILIA_LOCAL,
    PALAVRAS_ESQUEMA,
    ReferenciaInvalidaError,
    carregar_esquema,
    carregar_inventario,
    carregar_referencia_vigente,
    congelar,
    main,
    revisar,
    validar_arquivo,
    validar_esquema,
    validar_referencia,
)
from scripts.curation_render import ParametrosRender, caminho_indice, carregar_indice, renderizar
from scripts.curation_round import (
    RodadaError,
    carregar_checkpoint,
    carregar_rodada,
    diretorio_pdf,
    hash_arquivo,
    iniciar_rodada,
    transicionar,
)
from scripts.symbol_benchmark_runner import CLASS_FAMILY

AGORA = "2026-10-15T12:00:00+00:00"
DEPOIS = "2026-10-15T13:00:00+00:00"
Registro = dict[str, Any]
# 1 pt = 1 px, tiles de 256 px com 38 px de sobreposição: grade 3 x 4 numa página A4.
RAPIDO = ParametrosRender(lado_tile_px=256, sobreposicao=0.15, dpi_detalhe=72)
LARGURA, ALTURA = 595.0, 842.0
TRAFO = "cemig-eo-r3-s18-v001"
REGULADOR = "cemig-eo-r3-s18-v024"
ESTAI_MT = "cemig-eo-r3-s14-v001"
ESTAI_AT = "cemig-eo-r3-s15-v001"


def _retangulo(x0: float, y0: float, x1: float, y1: float) -> pymupdf.Rect:
    return pymupdf.Rect(x0, y0, x1, y1)  # type: ignore[no-untyped-call]


def _norm(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    return [x0 / LARGURA, y0 / ALTURA, x1 / LARGURA, y1 / ALTURA]


def _criar_pdf(caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=LARGURA, height=ALTURA)
        pagina.draw_rect(_retangulo(100, 50, 110, 60), color=(0, 0, 0), fill=(0, 0, 0))
        pagina.draw_line((300, 400), (340, 400), color=(0, 0, 0), width=1)
        pagina.add_rect_annot(_retangulo(400, 600, 440, 640))
        documento.save(caminho)


@pytest.fixture(scope="module")
def modelo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    base = tmp_path_factory.mktemp("modelo-referencia")
    _criar_pdf(base / "corpus" / "a.pdf")
    rodada = base / "rodada"
    iniciar_rodada(
        rodada, base / "corpus", concorrencia=3, raiz_repositorio=base / "sem-git", agora=AGORA
    )
    pdf_id = str(carregar_rodada(rodada)["pdfs"][0]["pdf_id"])
    resultado = renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    assert resultado["totais"]["sucesso"] == 1
    return base, pdf_id


@pytest.fixture
def rodada(modelo: tuple[Path, str], tmp_path: Path) -> tuple[Path, str]:
    base, pdf_id = modelo
    copia = tmp_path / "base"
    shutil.copytree(base, copia)
    return copia / "rodada", pdf_id


def _tile_que_contem(indice: Registro, camada: str, bbox: Sequence[float]) -> str:
    for tile in indice["tiles"]:
        x0, y0, x1, y1 = tile["bbox"]
        if (
            tile["camada"] == camada
            and tile["estado"] == "a_revisar"
            and x0 <= bbox[0]
            and y0 <= bbox[1]
            and bbox[2] <= x1
            and bbox[3] <= y1
        ):
            return str(tile["id"])
    raise AssertionError("nenhum tile a_revisar contém a bbox")


def _a_revisar(indice: Registro) -> list[str]:
    return [str(t["id"]) for t in indice["tiles"] if t["estado"] == "a_revisar"]


def _observacao(identidade: str, **campos: Any) -> Registro:
    registro: Registro = {
        "id": identidade,
        "pagina": 1,
        "camada": "base",
        "texto_original": None,
        "interpretacao": None,
        "quantidades": [],
        "relacoes": [],
        "estado": "sustentado_por_evidencia",
        "fonte_significado": {"tipo": "inventario", "localizador": None},
        "papel": "operacional",
    }
    registro.update(campos)
    return registro


def _referencia(rodada_dir: Path, pdf_id: str) -> Registro:
    """Referência sintética válida: ID exato, alternativas e elemento local desconhecido."""
    indice = carregar_indice(rodada_dir, pdf_id)
    checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
    trafo = _norm(100, 50, 110, 60)
    estai = _norm(300, 399, 340, 401)
    anotacao = _norm(400, 600, 440, 640)
    return {
        "schema_version": ESQUEMA_REFERENCIA,
        "pdf": {
            "pdf_id": pdf_id,
            "sha256": checkpoint["sha256"],
            "caminho_relativo": checkpoint["caminho_relativo"],
        },
        "revisor": {"origem": "revisao_ia", "modelo": "indisponivel"},
        "escopo": "completo",
        "tiles_revisados": _a_revisar(indice),
        "regioes_ilegiveis": [],
        "observacoes": [
            _observacao(
                "O1",
                bbox=trafo,
                familia="family-f02-18",
                class_id="TRANSFORMADOR",
                id_inventario=TRAFO,
                texto_original="T1 75 kVA",
                interpretacao="transformador de 75 kVA",
                quantidades=[{"valor": 75, "unidade": "kVA", "texto_original": "75 kVA"}],
                tile_evidencia=_tile_que_contem(indice, "base", trafo),
            ),
            _observacao(
                "O2",
                bbox=estai,
                trace=[[300 / LARGURA, 400 / ALTURA], [340 / LARGURA, 400 / ALTURA]],
                familia="family-f02-14",
                class_id="ESTAI",
                id_inventario=None,
                alternativas={
                    "ids_inventario": [ESTAI_MT, ESTAI_AT],
                    "motivo": "tensão do estai não legível",
                },
                relacoes=[{"tipo": "ancorado_em", "alvo": "O1"}],
                tile_evidencia=_tile_que_contem(indice, "base", estai),
            ),
            _observacao(
                "O3",
                camada="annotation",
                bbox=anotacao,
                familia=FAMILIA_LOCAL,
                class_id=CLASSE_LOCAL,
                papel="informativo",
                estado="provisorio",
                motivo_estado="retângulo sem legenda local",
                fonte_significado={"tipo": "indisponivel", "localizador": None},
                tile_evidencia=_tile_que_contem(indice, "annotation", anotacao),
            ),
        ],
    }


def _gravar(caminho: Path, valor: Any) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(valor, ensure_ascii=False), encoding="utf-8")
    return caminho


def _erros(rodada_dir: Path, pdf_id: str, referencia: Registro) -> list[str]:
    arquivo = _gravar(rodada_dir.parent / "entrada" / "referencia.json", referencia)
    return validar_arquivo(rodada_dir, pdf_id, arquivo).erros


def _uma_mensagem_com(erros: Sequence[str], *trechos: str) -> None:
    assert erros, "a referência deveria ser recusada"
    assert any(all(trecho in erro for trecho in trechos) for erro in erros), erros


def _checkpoint_bytes(rodada_dir: Path, pdf_id: str) -> bytes:
    return (diretorio_pdf(rodada_dir, pdf_id) / "checkpoint.json").read_bytes()


def _pasta_referencia(rodada_dir: Path, pdf_id: str) -> Path:
    return diretorio_pdf(rodada_dir, pdf_id) / "referencia"


# --- esquema --------------------------------------------------------------------------


def test_esquema_draft_2020_12_com_palavras_suportadas() -> None:
    esquema = carregar_esquema()
    assert esquema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert esquema["properties"]["schema_version"]["const"] == ESQUEMA_REFERENCIA
    assert CAMINHO_ESQUEMA.name == "referencia-visual-curadoria.schema.json"

    def palavras(no: Any) -> set[str]:
        if isinstance(no, list):
            return set().union(*(palavras(item) for item in no)) if no else set()
        if not isinstance(no, dict):
            return set()
        encontradas = set(no) - {"properties", "$defs"}
        for grupo in ("properties", "$defs"):
            for filho in no.get(grupo, {}).values():
                encontradas |= palavras(filho)
        for chave in ("items",):
            if chave in no:
                encontradas |= palavras(no[chave])
        return encontradas

    assert palavras(esquema) <= PALAVRAS_ESQUEMA


def test_validador_de_esquema_recusa_palavra_nao_suportada() -> None:
    with pytest.raises(ValueError, match="oneOf"):
        validar_esquema(1, {"oneOf": [{"type": "integer"}]})


def test_validador_de_esquema_aplica_tipos_ref_e_limites() -> None:
    esquema = {
        "$defs": {"n": {"type": "number", "minimum": 0, "maximum": 1}},
        "type": "object",
        "required": ["a"],
        "additionalProperties": False,
        "properties": {
            "a": {"type": "array", "items": {"$ref": "#/$defs/n"}, "minItems": 1},
            "b": {"type": ["string", "null"], "pattern": "^x"},
        },
    }
    assert validar_esquema({"a": [0, 1]}, esquema) == []
    assert validar_esquema({"a": [0.5], "b": None}, esquema) == []
    assert validar_esquema({"a": [True]}, esquema)
    assert validar_esquema({"a": [2]}, esquema)
    assert validar_esquema({"a": []}, esquema)
    assert validar_esquema({"a": [0], "b": "y"}, esquema)
    assert validar_esquema({"a": [0], "c": 1}, esquema)
    assert validar_esquema({}, esquema)
    assert validar_esquema({"a": [float("nan")]}, esquema)


# --- validar ------------------------------------------------------------------------------


def test_referencia_sintetica_valida_passa(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    arquivo = _gravar(rodada_dir.parent / "entrada" / "referencia.json", referencia)
    resultado = validar_arquivo(rodada_dir, pdf_id, arquivo)
    assert resultado.erros == []
    assert resultado.valida
    assert resultado.referencia == referencia
    assert resultado.indice_sha256 == hash_arquivo(caminho_indice(rodada_dir, pdf_id))


def test_mesma_referencia_em_escopo_regional_tambem_passa(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["escopo"] = "regional"
    assert _erros(rodada_dir, pdf_id, referencia) == []


def test_familia_fora_do_inventario_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["familia"] = "family-f02-99"
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "family-f02-99")


def test_classe_fora_da_familia_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["class_id"] = "ESTAI"
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "ESTAI")


def test_id_inventario_inexistente_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["id_inventario"] = "cemig-eo-r3-s18-v999"
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "cemig-eo-r3-s18-v999")


def test_bbox_fora_de_qualquer_tile_revisado_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    indice = carregar_indice(rodada_dir, pdf_id)
    canto = [0.9, 0.9, 0.95, 0.95]
    revisados = set(referencia["tiles_revisados"])
    assert not any(
        t["id"] in revisados and t["bbox"][0] <= 0.9 and t["bbox"][2] >= 0.95
        for t in indice["tiles"]
        if t["bbox"][1] <= 0.9 and t["bbox"][3] >= 0.95
    )
    referencia["observacoes"][0]["bbox"] = canto
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "tiles revisados")


def test_bbox_em_tile_revisado_de_outra_camada_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["escopo"] = "regional"
    referencia["tiles_revisados"] = [t for t in referencia["tiles_revisados"] if "-base-" in t]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O3", "tiles revisados")


def test_bbox_que_atravessa_dois_tiles_revisados_e_aceita(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    indice = carregar_indice(rodada_dir, pdf_id)
    base = [t for t in indice["tiles"] if t["camada"] == "base" and t["pagina"] == 1]
    referencia["escopo"] = "regional"
    referencia["tiles_revisados"] = [t["id"] for t in base]
    longa = [0.05, 0.4, 0.95, 0.41]
    referencia["observacoes"][1]["bbox"] = longa
    referencia["observacoes"][1].pop("trace")
    referencia["observacoes"].pop()
    assert _erros(rodada_dir, pdf_id, referencia) == []
    referencia["tiles_revisados"].remove("p001-base-t0102")
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O2", "tiles revisados")


def test_tile_de_evidencia_nao_revisado_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["tile_evidencia"] = "p001-base-t0302"
    _uma_mensagem_com(
        _erros(rodada_dir, pdf_id, referencia), "O1", "p001-base-t0302", "não está entre"
    )


def test_tile_de_evidencia_que_nao_toca_a_bbox_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["tile_evidencia"] = referencia["observacoes"][1]["tile_evidencia"]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "não contém")


def test_tile_revisado_inexistente_no_indice_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["tiles_revisados"].append("p009-base-t0000")
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "p009-base-t0000")


def test_tile_revisado_repetido_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    repetido = referencia["tiles_revisados"][0]
    referencia["tiles_revisados"].append(repetido)
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), repetido, "repetido")


def test_id_duplicado_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][2]["id"] = "O1"
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "duplicado")


def test_id_de_regiao_igual_ao_de_observacao_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["regioes_ilegiveis"] = [
        {"id": "O2", "pagina": 1, "camada": "base", "bbox": [0, 0, 0.1, 0.1], "motivo": "borrão"}
    ]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O2", "duplicado")


def test_relacao_para_id_inexistente_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][1]["relacoes"] = [{"tipo": "ancorado_em", "alvo": "O9"}]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O2", "O9")


def test_relacao_consigo_mesma_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][1]["relacoes"] = [{"tipo": "ancorado_em", "alvo": "O2"}]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O2", "si mesma")


def test_escopo_completo_com_tile_a_revisar_nao_revisado_e_recusado(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    evidencias = {item["tile_evidencia"] for item in referencia["observacoes"]}
    faltante = next(t for t in referencia["tiles_revisados"] if t not in evidencias)
    referencia["tiles_revisados"].remove(faltante)
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), faltante, "completo")
    referencia["escopo"] = "regional"
    assert _erros(rodada_dir, pdf_id, referencia) == []


def test_escopo_completo_aceita_tile_coberto_por_regiao_ilegivel(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    indice = carregar_indice(rodada_dir, pdf_id)
    evidencias = {item["tile_evidencia"] for item in referencia["observacoes"]}
    faltante = next(
        t for t in indice["tiles"] if t["estado"] == "a_revisar" and (t["id"] not in evidencias)
    )
    referencia["tiles_revisados"].remove(faltante["id"])
    meio = (faltante["bbox"][0] + faltante["bbox"][2]) / 2
    x0, y0, x1, y1 = faltante["bbox"]
    referencia["regioes_ilegiveis"] = [
        {
            "id": "R1",
            "pagina": 1,
            "camada": faltante["camada"],
            "bbox": [x0, y0, meio, y1],
            "motivo": "hachura densa",
        },
        {
            "id": "R2",
            "pagina": 1,
            "camada": faltante["camada"],
            "bbox": [meio, y0, x1, y1],
            "motivo": "hachura densa",
        },
    ]
    assert _erros(rodada_dir, pdf_id, referencia) == []
    referencia["regioes_ilegiveis"].pop()
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), faltante["id"])


def test_camada_anotada_igual_base_e_coberta_pelo_tile_base(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    indice = copy.deepcopy(carregar_indice(rodada_dir, pdf_id))
    inventario = carregar_inventario()
    referencia["observacoes"].pop()
    referencia["tiles_revisados"] = [t for t in referencia["tiles_revisados"] if "-base-" in t]
    a_revisar_anotada = [t for t in _a_revisar(indice) if "-anotada-" in t]
    assert a_revisar_anotada
    erros = validar_referencia(referencia, indice=indice, inventario=inventario)
    _uma_mensagem_com(erros, a_revisar_anotada[0], "completo")
    base_a_revisar = {
        (t["linha"], t["coluna"])
        for t in indice["tiles"]
        if t["camada"] == "base" and t["estado"] == "a_revisar"
    }
    for tile in indice["tiles"]:
        if tile["camada"] == "annotation":
            tile["estado"] = (
                "a_revisar"
                if (tile["linha"], tile["coluna"]) in base_a_revisar
                else "descartado_branco"
            )
    indice["paginas"][0]["camada_anotada_igual_base"] = True
    assert validar_referencia(referencia, indice=indice, inventario=inventario) == []
    indice["paginas"][0]["camada_anotada_igual_base"] = False
    assert validar_referencia(referencia, indice=indice, inventario=inventario)


def test_alternativas_sem_id_inventario_sao_aceitas(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    observacao = referencia["observacoes"][1]
    assert observacao["alternativas"] and observacao["id_inventario"] is None
    del observacao["id_inventario"]
    assert _erros(rodada_dir, pdf_id, referencia) == []


def test_alternativas_e_id_inventario_juntos_sao_recusados(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][1]["id_inventario"] = ESTAI_MT
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O2", "alternativas")


def test_id_inventario_de_outra_classe_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["id_inventario"] = REGULADOR
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", REGULADOR, "contradiz")


def test_alternativas_que_nao_incluem_a_classe_sao_recusadas(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][1]["alternativas"]["ids_inventario"] = [TRAFO, REGULADOR]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O2", "alternativas")


def test_alternativas_inexistentes_ou_repetidas_sao_recusadas(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][1]["alternativas"]["ids_inventario"] = [ESTAI_MT, "nao-existe"]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O2", "nao-existe")
    referencia["observacoes"][1]["alternativas"]["ids_inventario"] = [ESTAI_MT, ESTAI_MT]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O2", "repetid")


def test_uma_alternativa_so_e_recusada_pelo_esquema(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][1]["alternativas"]["ids_inventario"] = [ESTAI_MT]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O2", "ids_inventario")


def test_familia_de_inventario_sem_id_nem_alternativas_e_recusada(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["id_inventario"] = None
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "id_inventario")
    referencia["observacoes"][0]["papel"] = "negativo"
    assert _erros(rodada_dir, pdf_id, referencia) == []


def test_familia_local_nao_aceita_id_nem_classe_do_inventario(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][2]["id_inventario"] = TRAFO
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O3", FAMILIA_LOCAL)
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][2]["class_id"] = "TRANSFORMADOR"
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O3", CLASSE_LOCAL)


@pytest.mark.parametrize(("classe", "familia"), sorted(CLASS_FAMILY.items()))
def test_mapeamento_das_predicoes_do_runner_existe_no_inventario(classe: str, familia: str) -> None:
    inventario = carregar_inventario()
    assert familia in inventario.familias
    assert classe in inventario.classes_por_familia[familia]


def test_estado_nao_sustentado_exige_motivo(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    del referencia["observacoes"][2]["motivo_estado"]
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O3", "motivo_estado")


def test_legenda_sem_localizador_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["fonte_significado"] = {
        "tipo": "legenda_local",
        "localizador": None,
    }
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "localizador")


@pytest.mark.parametrize(
    "bbox",
    [[0.3, 0.1, 0.2, 0.2], [0.2, 0.1, 0.2, 0.1]],
    ids=["invertida", "ponto"],
)
def test_bbox_invertida_ou_ponto_e_recusada(rodada: tuple[Path, str], bbox: list[float]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["bbox"] = bbox
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "bbox")


def test_erros_de_esquema_citam_o_id_da_observacao(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][1]["papel"] = "equipamento"
    referencia["observacoes"][0]["extra"] = True
    del referencia["observacoes"][2]["estado"]
    erros = _erros(rodada_dir, pdf_id, referencia)
    _uma_mensagem_com(erros, "O2", "papel")
    _uma_mensagem_com(erros, "O1", "extra")
    _uma_mensagem_com(erros, "O3", "estado")


def test_pagina_inexistente_no_indice_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["pagina"] = 2
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), "O1", "página 2")


@pytest.mark.parametrize("campo", ["pdf_id", "sha256", "caminho_relativo"])
def test_identidade_do_pdf_divergente_e_recusada(rodada: tuple[Path, str], campo: str) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["pdf"][campo] = "0" * 64 if campo == "sha256" else "outro"
    _uma_mensagem_com(_erros(rodada_dir, pdf_id, referencia), f"pdf.{campo}")


def test_tiles_permitidos_restringem_a_revisao(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["escopo"] = "regional"
    evidencia = referencia["observacoes"][0]["tile_evidencia"]
    referencia["tiles_revisados"] = [evidencia]
    referencia["observacoes"] = referencia["observacoes"][:1]
    arquivo = _gravar(rodada_dir.parent / "entrada" / "auditoria.json", referencia)
    assert validar_arquivo(rodada_dir, pdf_id, arquivo, tiles_permitidos=[evidencia]).valida
    outro = validar_arquivo(rodada_dir, pdf_id, arquivo, tiles_permitidos=["p001-base-t0101"])
    _uma_mensagem_com(outro.erros, evidencia, "fora dos tiles permitidos")


def test_tile_descartado_pode_ser_revisado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["tiles_revisados"].append("p001-base-t0302")
    referencia["observacoes"][0]["papel"] = "negativo"
    assert _erros(rodada_dir, pdf_id, referencia) == []


def test_json_com_nan_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    texto = json.dumps(_referencia(rodada_dir, pdf_id)).replace("75,", "NaN,", 1)
    arquivo = rodada_dir.parent / "entrada" / "nan.json"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(texto, encoding="utf-8")
    with pytest.raises(RodadaError, match="NaN"):
        validar_arquivo(rodada_dir, pdf_id, arquivo)


def test_indice_alterado_depois_do_render_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    indice = caminho_indice(rodada_dir, pdf_id)
    indice.write_bytes(indice.read_bytes() + b"\n")
    with pytest.raises(RodadaError, match="índice de tiles"):
        _erros(rodada_dir, pdf_id, referencia)


def test_pdf_sem_renderizacao_e_recusado(tmp_path: Path) -> None:
    _criar_pdf(tmp_path / "corpus" / "a.pdf")
    rodada_dir = tmp_path / "rodada"
    iniciar_rodada(rodada_dir, tmp_path / "corpus", concorrencia=1, raiz_repositorio=tmp_path)
    pdf_id = str(carregar_rodada(rodada_dir)["pdfs"][0]["pdf_id"])
    arquivo = _gravar(tmp_path / "ref.json", {"schema_version": ESQUEMA_REFERENCIA})
    with pytest.raises(RodadaError, match="renderizado"):
        validar_arquivo(rodada_dir, pdf_id, arquivo)


# --- congelar -----------------------------------------------------------------------------


def test_congelar_grava_v001_hash_e_fase(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    entrada = _gravar(rodada_dir.parent / "entrada" / "referencia.json", referencia)
    checkpoint = congelar(rodada_dir, pdf_id, entrada, agora=DEPOIS)

    arquivo = _pasta_referencia(rodada_dir, pdf_id) / "referencia-v001.json"
    assert arquivo.is_file()
    sha = hash_arquivo(arquivo)
    assert checkpoint["fase"] == "referencia_congelada"
    assert checkpoint["referencia"] == {
        "arquivo": f"pdfs/{pdf_id}/referencia/referencia-v001.json",
        "horario": DEPOIS,
        "origem": "leitura",
        "sha256": sha,
        "versao": "referencia-v001.json",
    }
    assert checkpoint["marcos"]["referencia_congelada"]["artefatos"][0]["sha256"] == sha
    assert carregar_checkpoint(rodada_dir, pdf_id) == checkpoint
    congelada = json.loads(arquivo.read_text("utf-8"))
    bloco = congelada.pop("congelamento")
    assert congelada == referencia
    assert bloco == {
        "exposicao_predicoes": False,
        "indice_tiles_sha256": hash_arquivo(caminho_indice(rodada_dir, pdf_id)),
        "inferencias_presentes": [],
        "motivo": None,
        "origem": "leitura",
        "sha256_entrada": hashlib.sha256(entrada.read_bytes()).hexdigest(),
        "versao": 1,
        "versao_anterior": None,
    }
    evento = checkpoint["historico"][-1]
    assert evento["dados"]["exposicao_predicoes"] is False
    assert evento["dados"]["inferencias_presentes"] == []
    assert validar_arquivo(rodada_dir, pdf_id, arquivo).valida
    vigente, caminho = carregar_referencia_vigente(rodada_dir, pdf_id)
    assert caminho == arquivo
    assert vigente["congelamento"]["versao"] == 1


def test_segundo_congelar_falha_sem_alterar_nada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    entrada = _gravar(
        rodada_dir.parent / "entrada" / "referencia.json", _referencia(rodada_dir, pdf_id)
    )
    congelar(rodada_dir, pdf_id, entrada, agora=DEPOIS)
    arquivo = _pasta_referencia(rodada_dir, pdf_id) / "referencia-v001.json"
    antes = (arquivo.read_bytes(), _checkpoint_bytes(rodada_dir, pdf_id))
    outra = _referencia(rodada_dir, pdf_id)
    outra["observacoes"] = outra["observacoes"][:1]
    entrada_nova = _gravar(rodada_dir.parent / "entrada" / "outra.json", outra)
    with pytest.raises(RodadaError, match="revisar"):
        congelar(rodada_dir, pdf_id, entrada_nova)
    assert (arquivo.read_bytes(), _checkpoint_bytes(rodada_dir, pdf_id)) == antes
    assert sorted(p.name for p in _pasta_referencia(rodada_dir, pdf_id).iterdir()) == [
        "referencia-v001.json"
    ]


def test_congelar_referencia_invalida_nao_escreve_nada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["familia"] = "family-f02-99"
    entrada = _gravar(rodada_dir.parent / "entrada" / "referencia.json", referencia)
    antes = _checkpoint_bytes(rodada_dir, pdf_id)
    with pytest.raises(ReferenciaInvalidaError) as erro:
        congelar(rodada_dir, pdf_id, entrada)
    assert any("O1" in item for item in erro.value.erros)
    assert _checkpoint_bytes(rodada_dir, pdf_id) == antes
    pasta = _pasta_referencia(rodada_dir, pdf_id)
    assert not pasta.exists() or not any(pasta.iterdir())


def test_congelar_registra_inferencia_ja_presente(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    (diretorio_pdf(rodada_dir, pdf_id) / "inferencia-v001").mkdir()
    (diretorio_pdf(rodada_dir, pdf_id) / "inferencia-v002").mkdir()
    entrada = _gravar(
        rodada_dir.parent / "entrada" / "referencia.json", _referencia(rodada_dir, pdf_id)
    )
    checkpoint = congelar(rodada_dir, pdf_id, entrada)
    congelada, _ = carregar_referencia_vigente(rodada_dir, pdf_id)
    presentes = ["inferencia-v001", "inferencia-v002"]
    assert congelada["congelamento"]["inferencias_presentes"] == presentes
    assert checkpoint["historico"][-1]["dados"]["inferencias_presentes"] == presentes


def test_congelar_e_revisar_recusam_entrada_com_bloco_de_congelamento(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["congelamento"] = {"versao": 1}
    entrada = _gravar(rodada_dir.parent / "entrada" / "com-bloco.json", referencia)
    antes = _checkpoint_bytes(rodada_dir, pdf_id)
    with pytest.raises(RodadaError, match="congelamento"):
        congelar(rodada_dir, pdf_id, entrada)
    assert _checkpoint_bytes(rodada_dir, pdf_id) == antes
    del referencia["congelamento"]
    congelar(rodada_dir, pdf_id, _gravar(entrada, referencia))
    _, v001 = carregar_referencia_vigente(rodada_dir, pdf_id)
    with pytest.raises(RodadaError, match="congelamento"):
        revisar(rodada_dir, pdf_id, v001, motivo="reaplicar", exposicao_predicoes=False)


def test_congelar_nao_sobrescreve_versao_orfa(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    orfa = _pasta_referencia(rodada_dir, pdf_id) / "referencia-v001.json"
    orfa.parent.mkdir(parents=True)
    orfa.write_bytes(b"{}")
    entrada = _gravar(
        rodada_dir.parent / "entrada" / "referencia.json", _referencia(rodada_dir, pdf_id)
    )
    antes = _checkpoint_bytes(rodada_dir, pdf_id)
    with pytest.raises(RodadaError, match=r"referencia-v001\.json já existe sem registro"):
        congelar(rodada_dir, pdf_id, entrada)
    assert orfa.read_bytes() == b"{}"
    assert _checkpoint_bytes(rodada_dir, pdf_id) == antes


def test_criacao_de_versao_e_exclusiva_mesmo_sem_a_checagem_previa(
    rodada: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rodada_dir, pdf_id = rodada
    orfa = _pasta_referencia(rodada_dir, pdf_id) / "referencia-v001.json"
    orfa.parent.mkdir(parents=True)
    orfa.write_bytes(b"{}")
    monkeypatch.setattr(curation_reference, "versoes_existentes", lambda _: [])
    entrada = _gravar(
        rodada_dir.parent / "entrada" / "referencia.json", _referencia(rodada_dir, pdf_id)
    )
    antes = _checkpoint_bytes(rodada_dir, pdf_id)
    with pytest.raises(RodadaError, match="nunca são sobrescritas"):
        congelar(rodada_dir, pdf_id, entrada)
    assert orfa.read_bytes() == b"{}"
    assert _checkpoint_bytes(rodada_dir, pdf_id) == antes
    assert sorted(item.name for item in orfa.parent.iterdir()) == ["referencia-v001.json"]


def test_congelar_em_fase_terminal_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    transicionar(rodada_dir, pdf_id, "encerrado_com_pendencias", nota="sem leitura")
    entrada = _gravar(
        rodada_dir.parent / "entrada" / "referencia.json", _referencia(rodada_dir, pdf_id)
    )
    antes = _checkpoint_bytes(rodada_dir, pdf_id)
    with pytest.raises(RodadaError, match="terminal"):
        congelar(rodada_dir, pdf_id, entrada)
    assert _checkpoint_bytes(rodada_dir, pdf_id) == antes
    assert not _pasta_referencia(rodada_dir, pdf_id).exists()


# --- revisar ------------------------------------------------------------------------------


def _congelado(rodada_dir: Path, pdf_id: str) -> tuple[Path, bytes]:
    entrada = _gravar(
        rodada_dir.parent / "entrada" / "referencia.json", _referencia(rodada_dir, pdf_id)
    )
    congelar(rodada_dir, pdf_id, entrada, agora=DEPOIS)
    v001 = _pasta_referencia(rodada_dir, pdf_id) / "referencia-v001.json"
    return v001, v001.read_bytes()


def _revisada(rodada_dir: Path, pdf_id: str, nome: str = "revisada.json") -> Path:
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["texto_original"] = "T1 112,5 kVA"
    return _gravar(rodada_dir.parent / "entrada" / nome, referencia)


def test_revisar_cria_v002_com_motivo_e_exposicao(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    v001, bytes_v001 = _congelado(rodada_dir, pdf_id)
    checkpoint = revisar(
        rodada_dir,
        pdf_id,
        _revisada(rodada_dir, pdf_id),
        motivo="divergência do comparador mostrou potência mal lida",
        exposicao_predicoes=True,
        agora="2026-10-15T14:00:00+00:00",
    )
    v002 = _pasta_referencia(rodada_dir, pdf_id) / "referencia-v002.json"
    assert v001.read_bytes() == bytes_v001
    congelada = json.loads(v002.read_text("utf-8"))
    bloco = congelada["congelamento"]
    assert bloco["versao"] == 2
    assert bloco["origem"] == "revisao"
    assert bloco["exposicao_predicoes"] is True
    assert bloco["motivo"] == "divergência do comparador mostrou potência mal lida"
    assert bloco["versao_anterior"] == {
        "arquivo": f"pdfs/{pdf_id}/referencia/referencia-v001.json",
        "sha256": hashlib.sha256(bytes_v001).hexdigest(),
    }
    assert congelada["observacoes"][0]["texto_original"] == "T1 112,5 kVA"
    assert checkpoint["referencia"]["versao"] == "referencia-v002.json"
    assert checkpoint["referencia"]["origem"] == "revisao"
    assert checkpoint["referencia"]["sha256"] == hash_arquivo(v002)
    dados = checkpoint["historico"][-1]["dados"]
    assert dados["exposicao_predicoes"] is True
    assert dados["motivo"] == bloco["motivo"]
    assert dados["versao_anterior"] == "referencia-v001.json"


def test_revisar_sem_exposicao_registra_false(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _congelado(rodada_dir, pdf_id)
    revisar(
        rodada_dir,
        pdf_id,
        _revisada(rodada_dir, pdf_id),
        motivo="releitura cega de um tile",
        exposicao_predicoes=False,
    )
    congelada, caminho = carregar_referencia_vigente(rodada_dir, pdf_id)
    assert caminho.name == "referencia-v002.json"
    assert congelada["congelamento"]["exposicao_predicoes"] is False


def test_revisar_duas_vezes_preserva_todas_as_versoes(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _, bytes_v001 = _congelado(rodada_dir, pdf_id)
    revisar(rodada_dir, pdf_id, _revisada(rodada_dir, pdf_id), motivo="a", exposicao_predicoes=True)
    pasta = _pasta_referencia(rodada_dir, pdf_id)
    bytes_v002 = (pasta / "referencia-v002.json").read_bytes()
    revisar(rodada_dir, pdf_id, _revisada(rodada_dir, pdf_id), motivo="b", exposicao_predicoes=True)
    assert (pasta / "referencia-v001.json").read_bytes() == bytes_v001
    assert (pasta / "referencia-v002.json").read_bytes() == bytes_v002
    v003 = json.loads((pasta / "referencia-v003.json").read_text("utf-8"))
    assert (
        v003["congelamento"]["versao_anterior"]["sha256"] == hashlib.sha256(bytes_v002).hexdigest()
    )


def test_revisar_pula_numero_ocupado_sem_sobrescrever(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _congelado(rodada_dir, pdf_id)
    orfa = _pasta_referencia(rodada_dir, pdf_id) / "referencia-v002.json"
    orfa.write_bytes(b"orfa")
    checkpoint = revisar(
        rodada_dir, pdf_id, _revisada(rodada_dir, pdf_id), motivo="x", exposicao_predicoes=True
    )
    assert orfa.read_bytes() == b"orfa"
    assert checkpoint["referencia"]["versao"] == "referencia-v003.json"
    congelada, _ = carregar_referencia_vigente(rodada_dir, pdf_id)
    assert congelada["congelamento"]["versao_anterior"]["arquivo"].endswith("v001.json")


def test_revisar_sem_referencia_congelada_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    antes = _checkpoint_bytes(rodada_dir, pdf_id)
    with pytest.raises(RodadaError, match="congelar"):
        revisar(
            rodada_dir, pdf_id, _revisada(rodada_dir, pdf_id), motivo="x", exposicao_predicoes=True
        )
    assert _checkpoint_bytes(rodada_dir, pdf_id) == antes
    assert not _pasta_referencia(rodada_dir, pdf_id).exists()


@pytest.mark.parametrize("motivo", ["", "   "])
def test_revisar_sem_motivo_e_recusado(rodada: tuple[Path, str], motivo: str) -> None:
    rodada_dir, pdf_id = rodada
    _congelado(rodada_dir, pdf_id)
    antes = _checkpoint_bytes(rodada_dir, pdf_id)
    with pytest.raises(RodadaError, match="motivo"):
        revisar(
            rodada_dir,
            pdf_id,
            _revisada(rodada_dir, pdf_id),
            motivo=motivo,
            exposicao_predicoes=True,
        )
    assert _checkpoint_bytes(rodada_dir, pdf_id) == antes
    assert not (_pasta_referencia(rodada_dir, pdf_id) / "referencia-v002.json").exists()


def test_revisar_com_versao_vigente_adulterada_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    v001, _ = _congelado(rodada_dir, pdf_id)
    v001.write_bytes(v001.read_bytes() + b" ")
    antes = _checkpoint_bytes(rodada_dir, pdf_id)
    with pytest.raises(RodadaError, match="SHA-256"):
        revisar(
            rodada_dir, pdf_id, _revisada(rodada_dir, pdf_id), motivo="x", exposicao_predicoes=True
        )
    assert _checkpoint_bytes(rodada_dir, pdf_id) == antes
    with pytest.raises(RodadaError, match="SHA-256"):
        carregar_referencia_vigente(rodada_dir, pdf_id)


def test_revisar_referencia_invalida_nao_cria_versao(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _congelado(rodada_dir, pdf_id)
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][1]["relacoes"] = [{"tipo": "x", "alvo": "O9"}]
    entrada = _gravar(rodada_dir.parent / "entrada" / "invalida.json", referencia)
    with pytest.raises(ReferenciaInvalidaError):
        revisar(rodada_dir, pdf_id, entrada, motivo="x", exposicao_predicoes=True)
    assert not (_pasta_referencia(rodada_dir, pdf_id) / "referencia-v002.json").exists()


def test_revisar_invalida_comparacao_anterior(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _congelado(rodada_dir, pdf_id)
    transicionar(rodada_dir, pdf_id, "inferido")
    transicionar(rodada_dir, pdf_id, "comparado")
    checkpoint = revisar(
        rodada_dir, pdf_id, _revisada(rodada_dir, pdf_id), motivo="x", exposicao_predicoes=True
    )
    assert "comparado" not in checkpoint["marcos"]
    assert checkpoint["fase"] == "referencia_congelada"


# --- CLI ----------------------------------------------------------------------------------


def _cli(argv: list[str]) -> int:
    return main(argv)


def test_cli_validar_congelar_e_revisar(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    base = ["--rodada", str(rodada_dir), "--pdf", pdf_id]
    entrada = _gravar(
        rodada_dir.parent / "entrada" / "referencia.json", _referencia(rodada_dir, pdf_id)
    )
    assert _cli(["validar", *base, "--arquivo", str(entrada)]) == 0
    assert "válida" in capsys.readouterr().out
    assert _cli(["congelar", *base, "--arquivo", str(entrada)]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["versao"] == "referencia-v001.json"
    assert _cli(["congelar", *base, "--arquivo", str(entrada)]) == 1
    assert "revisar" in capsys.readouterr().err
    revisada = _revisada(rodada_dir, pdf_id)
    comando = ["revisar", *base, "--arquivo", str(revisada), "--motivo", "m"]
    assert _cli([*comando, "--exposicao", "sim"]) == 0
    assert json.loads(capsys.readouterr().out)["exposicao_predicoes"] is True
    assert _cli([*comando, "--exposicao", "nao"]) == 0
    assert json.loads(capsys.readouterr().out)["versao"] == "referencia-v003.json"


def test_cli_validar_lista_erros_com_id(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    referencia = _referencia(rodada_dir, pdf_id)
    referencia["observacoes"][0]["familia"] = "family-f02-99"
    referencia["observacoes"][1]["relacoes"] = [{"tipo": "x", "alvo": "O9"}]
    entrada = _gravar(rodada_dir.parent / "entrada" / "referencia.json", referencia)
    codigo = _cli(
        ["validar", "--rodada", str(rodada_dir), "--pdf", pdf_id, "--arquivo", str(entrada)]
    )
    assert codigo == 1
    erro = capsys.readouterr().err
    assert "O1" in erro and "family-f02-99" in erro
    assert "O2" in erro and "O9" in erro


def test_cli_revisar_exige_exposicao_explicita(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    comando = [
        "revisar",
        "--rodada",
        str(rodada_dir),
        "--pdf",
        pdf_id,
        "--arquivo",
        "x.json",
        "--motivo",
        "m",
    ]
    with pytest.raises(SystemExit) as saida:
        _cli(comando)
    assert saida.value.code == 2
    with pytest.raises(SystemExit):
        _cli([*comando, "--exposicao", "talvez"])


def test_cli_pdf_desconhecido_falha(rodada: tuple[Path, str]) -> None:
    rodada_dir, _ = rodada
    assert _cli(["validar", "--rodada", str(rodada_dir), "--pdf", "999-x", "--arquivo", "x"]) == 1
