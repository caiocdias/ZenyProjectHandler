from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts import curation_compare
from scripts.curation_compare import (
    ALERTA_SEM_CLASSES,
    ESQUEMA_COMPARACAO,
    METODO_UNIAO,
    MOTIVO_SEM_METODO,
    ComparacaoRecusadaError,
    comparar,
    comparar_pdf,
    main,
)
from scripts.curation_infer import ResultadoComando, inferir
from scripts.curation_reference import congelar, revisar
from scripts.curation_render import ParametrosRender, carregar_indice, renderizar
from scripts.curation_round import (
    carregar_checkpoint,
    carregar_rodada,
    diretorio_pdf,
    iniciar_rodada,
    transicionar,
)
from scripts.symbol_benchmark_evaluator import PROTOCOL

AGORA = "2026-10-15T12:00:00+00:00"
Registro = dict[str, Any]
# Página de 200 x 200 pt a 72 DPI com tiles de 100 px sem sobreposição: grade 2 x 2 por camada.
# t0000 = superior esquerdo, t0001 = superior direito, t0100 = inferior esquerdo e t0101 =
# inferior direito (em branco, descartado).
RAPIDO = ParametrosRender(lado_tile_px=100, sobreposicao=0.0, dpi_detalhe=72)
LADO = 200.0
DOC = "example:a.pdf"
PACOTES = "declarative-vector-packages"
TRAFOS = "transformer-vector-shapes"
LEGENDA = "document-local-legend"
ESTAIS = "guy-vector-shapes"
CABO = "CABO_AEREO"
TRAFO = "cemig-eo-r3-s18-v001"
TRAFO_OUTRO = "cemig-eo-r3-s18-v002"
REGULADOR = "cemig-eo-r3-s18-v024"
ESTAI_MT = "cemig-eo-r3-s14-v001"
ESTAI_AT = "cemig-eo-r3-s15-v001"
FAMILIA = {
    "TRANSFORMADOR": "family-f02-18",
    "REGULADOR_TENSAO": "family-f02-18",
    "ESTAI": "family-f02-14",
    "CABO_AEREO": "family-f02-16",
}
TL, TR, BL, BR = "p001-base-t0000", "p001-base-t0001", "p001-base-t0100", "p001-base-t0101"

# Posições normalizadas (todas com tinta no PDF, salvo o quadrante inferior direito).
B_O1 = [0.10, 0.10, 0.20, 0.20]
B_O2 = [0.30, 0.10, 0.40, 0.20]
B_O3 = [0.60, 0.10, 0.70, 0.20]
B_O4 = [0.60, 0.30, 0.70, 0.40]
B_O5 = [0.10, 0.80, 0.20, 0.90]
B_FP = [0.80, 0.10, 0.90, 0.20]
B_NEG = [0.30, 0.30, 0.40, 0.40]
B_PROV = [0.80, 0.30, 0.90, 0.40]
B_ILEGIVEL = [0.25, 0.55, 0.45, 0.75]
B_NO_ILEGIVEL = [0.30, 0.60, 0.40, 0.70]
B_DESCARTADO = [0.80, 0.80, 0.90, 0.90]


def _retangulo(x0: float, y0: float, x1: float, y1: float) -> pymupdf.Rect:
    return pymupdf.Rect(x0, y0, x1, y1)  # type: ignore[no-untyped-call]


def _criar_pdf(caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=LADO, height=LADO)
        for caixa in (B_O1, B_O2, B_O3, B_O4, B_O5, B_FP, B_NEG, B_PROV, B_NO_ILEGIVEL):
            pagina.draw_rect(
                _retangulo(*(valor * LADO for valor in caixa)), color=(0, 0, 0), fill=(0, 0, 0)
            )
        documento.save(caminho)


@pytest.fixture(scope="module")
def modelo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    base = tmp_path_factory.mktemp("modelo-comparacao")
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


# --- construção de referência e inferência sintéticas -------------------------------------


def _observacao(
    identidade: str, bbox: list[float], classe: str, tile: str, **campos: Any
) -> Registro:
    registro: Registro = {
        "id": identidade,
        "pagina": 1,
        "camada": "base",
        "bbox": bbox,
        "familia": FAMILIA[classe],
        "class_id": classe,
        "papel": "operacional",
        "texto_original": None,
        "interpretacao": None,
        "estado": "sustentado_por_evidencia",
        "tile_evidencia": tile,
        "fonte_significado": {"tipo": "inventario", "localizador": None},
    }
    registro.update(campos)
    return registro


def _observacoes_base() -> list[Registro]:
    """Cinco ocorrências operacionais; O3 é ambígua (alternativas, sem ID exato)."""
    return [
        _observacao("O1", B_O1, "TRANSFORMADOR", TL, id_inventario=TRAFO),
        _observacao("O2", B_O2, "REGULADOR_TENSAO", TL, id_inventario=REGULADOR),
        _observacao(
            "O3",
            B_O3,
            "ESTAI",
            TR,
            alternativas={"ids_inventario": [ESTAI_MT, ESTAI_AT], "motivo": "tensão ilegível"},
        ),
        _observacao("O4", B_O4, "TRANSFORMADOR", TR, id_inventario=TRAFO),
        _observacao("O5", B_O5, "REGULADOR_TENSAO", BL, id_inventario=REGULADOR),
    ]


def _referencia(
    rodada_dir: Path,
    pdf_id: str,
    observacoes: Sequence[Registro] | None = None,
    *,
    escopo: str = "regional",
    tiles: Sequence[str] = (TL, TR, BL),
) -> Registro:
    checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
    return {
        "schema_version": "curadoria-referencia-visual-v1",
        "pdf": {
            "pdf_id": pdf_id,
            "sha256": checkpoint["sha256"],
            "caminho_relativo": checkpoint["caminho_relativo"],
        },
        "revisor": {"origem": "revisao_ia", "modelo": "indisponivel"},
        "escopo": escopo,
        "tiles_revisados": list(tiles),
        "regioes_ilegiveis": [
            {"id": "R1", "pagina": 1, "camada": "base", "bbox": B_ILEGIVEL, "motivo": "borrado"}
        ],
        "observacoes": list(observacoes if observacoes is not None else _observacoes_base()),
    }


def _predicao(
    local: str,
    metodo: str,
    bbox: list[float],
    classe: str,
    *,
    variante: str | None = None,
    camada: str = "base",
    contexto: str = "operational",
) -> Registro:
    return {
        "id": f"{DOC}:{local}",
        "method_id": metodo,
        "document_id": DOC,
        "page": 1,
        "layer": camada,
        "family": FAMILIA[classe],
        "class_id": classe,
        "bbox": list(bbox),
        "score": 1.0,
        "situation": None,
        "quantity": None,
        "association": None,
        "context": contexto,
        "review_required": True,
        "provenance": {"variant_id": variante} if variante else {"observation_id": local},
    }


def _predicoes_base() -> list[Registro]:
    """Seis predições de dois métodos com resultado conhecido (ver testes de métricas)."""
    return [
        _predicao("A1", PACOTES, B_O1, "TRANSFORMADOR", variante=TRAFO),
        _predicao("A2", PACOTES, B_O3, "ESTAI", variante=ESTAI_MT),
        _predicao("A3", PACOTES, B_FP, "TRANSFORMADOR", variante=TRAFO),
        _predicao("B1", TRAFOS, B_O1, "TRANSFORMADOR"),
        _predicao("B2", TRAFOS, [0.31, 0.10, 0.41, 0.20], "REGULADOR_TENSAO"),
        _predicao("B3", TRAFOS, B_O4, "REGULADOR_TENSAO"),
    ]


def _documento_predicoes(
    sha256: str,
    predicoes: Sequence[Registro],
    *,
    metodos: Sequence[str] = (PACOTES, TRAFOS),
    falhas: Sequence[tuple[str, str]] = (),
    suportadas: Mapping[str, Sequence[Any] | None] | None = None,
) -> Registro:
    """``suportadas[metodo]`` = lista declarada; ``None`` omite o campo; padrão: lista vazia."""
    declaradas = dict(suportadas or {})
    return {
        "schema_version": 1,
        "methods": [
            {
                "id": metodo,
                "version": "1",
                "algorithm_family": "sintetico",
                "shared_sources": [],
                **(
                    {}
                    if metodo in declaradas and declaradas[metodo] is None
                    else {"supported_classes": list(declaradas.get(metodo) or [])}
                ),
                **({"evaluation_scope": "local_candidates; excluded"} if metodo == LEGENDA else {}),
            }
            for metodo in metodos
        ],
        "documents": [{"id": DOC, "sha256": sha256}],
        "predictions": list(predicoes),
        "local_candidates": [
            {
                "id": f"{DOC}:L1",
                "method_id": "document-local-legend",
                "document_id": DOC,
                "page": 1,
                "layer": "base",
                "family": "local-unknown",
                "class_id": "UNKNOWN_LOCAL",
                "bbox": B_FP,
                "context": "operational",
            }
        ],
        "executions": [
            {
                "document_id": DOC,
                "page": 1,
                "layer": camada,
                "method_id": metodo,
                "status": "failed" if (metodo, camada) in falhas else "executed",
            }
            for metodo in metodos
            for camada in ("base", "annotation")
        ],
    }


def _executor_fixo(documento: Registro) -> Any:
    def executor(comando: Sequence[str], *, cwd: Path, log: Path) -> ResultadoComando:
        saida = Path(comando[list(comando).index("--output") + 1])
        saida.mkdir(parents=True, exist_ok=True)
        (saida / "predictions.json").write_text(json.dumps(documento), encoding="utf-8")
        (saida / "manifest.json").write_text(
            json.dumps({"schema_version": 1, "status": "completed_inference", "documents": []}),
            encoding="utf-8",
        )
        log.write_text("ok", encoding="utf-8")
        return ResultadoComando(0)

    return executor


def _gravar(caminho: Path, valor: Any) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(valor, ensure_ascii=False), encoding="utf-8")
    return caminho


def _congelar(rodada_dir: Path, pdf_id: str, referencia: Registro) -> None:
    arquivo = _gravar(rodada_dir.parent / "entrada" / "referencia.json", referencia)
    congelar(rodada_dir, pdf_id, arquivo, agora=AGORA)


def _inferir(rodada_dir: Path, pdf_id: str, predicoes: Sequence[Registro], **opcoes: Any) -> None:
    sha = carregar_checkpoint(rodada_dir, pdf_id)["sha256"]
    documento = _documento_predicoes(sha, predicoes, **opcoes)
    resumo = inferir(
        rodada_dir,
        [pdf_id],
        jobs=1,
        executor=_executor_fixo(documento),
        raiz_repositorio=rodada_dir.parent / "sem-git",
        codigo={"git_write_tree": "indisponivel"},
    )
    assert resumo["totais"]["sucesso"] == 1, resumo


def _preparar(
    rodada_dir: Path,
    pdf_id: str,
    *,
    observacoes: Sequence[Registro] | None = None,
    predicoes: Sequence[Registro] | None = None,
    escopo: str = "regional",
    tiles: Sequence[str] = (TL, TR, BL),
    **opcoes: Any,
) -> None:
    _congelar(
        rodada_dir, pdf_id, _referencia(rodada_dir, pdf_id, observacoes, escopo=escopo, tiles=tiles)
    )
    _inferir(rodada_dir, pdf_id, _predicoes_base() if predicoes is None else predicoes, **opcoes)


def _comparar(rodada_dir: Path, pdf_id: str, **opcoes: Any) -> Registro:
    resumo = comparar_pdf(rodada_dir, pdf_id, **opcoes)
    caminho = rodada_dir / resumo["arquivo"]
    dados: Registro = json.loads(caminho.read_text(encoding="utf-8"))
    return dados


def _contagem(bloco: Registro) -> tuple[Any, Any, Any]:
    return bloco["tp_ia"], bloco["fp_ia"], bloco["fn_ia"]


def _divergencias(comparacao: Registro, **filtro: Any) -> list[Registro]:
    return [
        item
        for item in comparacao["divergencias"]
        if all(item.get(campo) == valor for campo, valor in filtro.items())
    ]


def _local(identidade: str | None) -> str | None:
    return None if identidade is None else identidade.rsplit(":", 1)[-1]


# --- grade sintética ------------------------------------------------------------------------


def test_grade_sintetica_tem_quatro_tiles_por_camada_e_um_descartado(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    base = {tile["id"]: tile for tile in indice["tiles"] if tile["camada"] == "base"}
    assert base[TL]["bbox"] == [0.0, 0.0, 0.5, 0.5]
    assert base[TR]["bbox"] == [0.5, 0.0, 1.0, 0.5]
    assert base[BL]["bbox"] == [0.0, 0.5, 0.5, 1.0]
    assert base[BR]["estado"] == "descartado_branco"
    assert {base[t]["estado"] for t in (TL, TR, BL)} == {"a_revisar"}
    assert indice["paginas"][0]["camada_anotada_igual_base"] is True


# --- métricas do caso sintético --------------------------------------------------------------


def test_caso_sintetico_produz_tp_fp_fn_esperados_por_metodo_e_uniao(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    comparacao = _comparar(rodada_dir, pdf_id)

    assert comparacao["schema_version"] == ESQUEMA_COMPARACAO
    assert comparacao["protocolo"]["id"] == PROTOCOL["id"]
    assert comparacao["escopo"] == "regional"
    metodos = comparacao["metodos"]
    assert sorted(metodos) == [PACOTES, TRAFOS]
    # A (pacotes): A1 casa O1, A2 casa O3 por classe, A3 é FP; O2, O4 e O5 ficam sem predição.
    assert _contagem(metodos[PACOTES]["classe"]) == (2, 1, 3)
    # B: B1 casa O1, B2 casa O2 (IoU 0,82), B3 tem classe errada em O4 (FP) e O4 fica FN.
    assert _contagem(metodos[TRAFOS]["classe"]) == (2, 1, 3)
    uniao = comparacao["uniao"]
    # A1 e B1 são equivalentes exatos: 5 candidatas de 6 observações de entrada.
    assert uniao["candidatas"] == 5
    assert uniao["observacoes_entrada"] == 6
    assert _contagem(uniao["classe"]) == (3, 2, 2)

    # Métricas por família (nível classe).
    assert _contagem(metodos[PACOTES]["por_familia"]["family-f02-18"]) == (1, 1, 3)
    assert _contagem(metodos[PACOTES]["por_familia"]["family-f02-14"]) == (1, 0, 0)
    assert _contagem(metodos[TRAFOS]["por_familia"]["family-f02-18"]) == (2, 1, 2)
    assert _contagem(metodos[TRAFOS]["por_familia"]["family-f02-14"]) == (0, 0, 1)
    assert _contagem(uniao["por_familia"]["family-f02-18"]) == (2, 2, 2)
    assert _contagem(uniao["por_familia"]["family-f02-14"]) == (1, 0, 0)

    # Precisão e revocação regional; sem revocação global em escopo regional.
    assert uniao["classe"]["precisao"] == pytest.approx(3 / 5)
    assert uniao["classe"]["revocacao_regional"] == pytest.approx(3 / 5)
    assert uniao["classe"]["revocacao_global"] is None
    assert metodos[PACOTES]["classe"]["revocacao_global"] is None


def test_denominadores_do_caso_sintetico(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    denominadores = _comparar(rodada_dir, pdf_id)["denominadores"]

    assert denominadores["tiles"] == {
        "indice": 8,
        "a_revisar": 6,
        "descartado_branco": 2,
        "revisados": 3,
        "revisados_por_gemeo": 3,
        "revisados_descartados": 0,
        "a_revisar_nao_revisados": 0,
    }
    assert denominadores["regioes_ilegiveis"] == 1
    assert denominadores["observacoes"] == {
        "total": 5,
        "em_escopo": 5,
        "fora_do_escopo": 0,
        "operacionais_avaliaveis": 5,
        "negativos": 0,
        "provisorias": 0,
        "ilegiveis": 0,
        "papel_desconhecido": 0,
        "locais": 0,
        "ambiguas": 1,
        "com_id_inventario": 4,
    }
    assert denominadores["predicoes"] == {
        "total": 6,
        "em_escopo": 6,
        "fora_do_escopo": 0,
        "nao_operacionais_em_escopo": 0,
        "candidatos_locais_ignorados": 1,
    }


def test_divergencias_sao_rastreaveis_e_somam_as_metricas(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    comparacao = _comparar(rodada_dir, pdf_id)

    ids = [item["id"] for item in comparacao["divergencias"]]
    assert len(ids) == len(set(ids))
    for metodo, bloco in comparacao["metodos"].items():
        divergencias = _divergencias(comparacao, method_id=metodo, nivel="classe")
        assert sum(item["conta_em"] == "fp_ia" for item in divergencias) == bloco["classe"]["fp_ia"]
        assert sum(item["conta_em"] == "fn_ia" for item in divergencias) == bloco["classe"]["fn_ia"]
    for item in comparacao["divergencias"]:
        assert set(item) >= {
            "id",
            "tipo",
            "nivel",
            "conta_em",
            "method_id",
            "observacao_id",
            "predicao_id",
            "pagina",
            "camada",
            "familia",
            "class_id",
            "bbox",
            "tile_evidencia",
            "detalhe",
        }
        assert item["tile_evidencia"] in {TL, TR, BL}

    fp_a = _divergencias(comparacao, method_id=PACOTES, tipo="fp")
    assert [(_local(item["predicao_id"]), item["tile_evidencia"]) for item in fp_a] == [("A3", TR)]
    assert fp_a[0]["bbox"] == B_FP
    fn_a = _divergencias(comparacao, method_id=PACOTES, tipo="fn")
    assert sorted(item["observacao_id"] for item in fn_a) == ["O2", "O4", "O5"]
    # B3 tem a geometria de O4 com outra classe: FP ligado à observação confundida.
    fp_b = _divergencias(comparacao, method_id=TRAFOS, tipo="fp")
    assert [(_local(i["predicao_id"]), i["observacao_id"]) for i in fp_b] == [("B3", "O4")]
    assert fp_b[0]["detalhe"]["motivo"] == "classe_divergente"
    fn_b = {
        item["observacao_id"]: item
        for item in _divergencias(comparacao, method_id=TRAFOS, tipo="fn")
    }
    assert sorted(fn_b) == ["O3", "O4", "O5"]
    assert _local(fn_b["O4"]["predicao_id"]) == "B3"
    assert fn_b["O4"]["tile_evidencia"] == TR
    # O4 e O5 não foram achados por nenhum método; O2 e O3 foram achados por algum.
    perdidas = {
        item["observacao_id"]: item["perdida_pela_uniao"]
        for item in comparacao["divergencias"]
        if item["tipo"] == "fn"
    }
    assert perdidas == {"O2": False, "O3": False, "O4": True, "O5": True}
    assert not _divergencias(comparacao, tipo="id_errado")
    assert not _divergencias(comparacao, tipo="duplicata")


# --- escopo regional ----------------------------------------------------------------------


def test_predicao_fora_do_escopo_nao_vira_fp(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    predicoes = [
        _predicao("C1", PACOTES, B_O1, "TRANSFORMADOR", variante=TRAFO),
        _predicao("C2", PACOTES, B_DESCARTADO, "TRANSFORMADOR"),
        _predicao("C3", PACOTES, B_NO_ILEGIVEL, "TRANSFORMADOR"),
        _predicao("C4", PACOTES, B_O3, "TRANSFORMADOR"),
    ]
    _preparar(
        rodada_dir,
        pdf_id,
        observacoes=[_observacao("O1", B_O1, "TRANSFORMADOR", TL, id_inventario=TRAFO)],
        predicoes=predicoes,
        tiles=(TL, BL),
    )
    comparacao = _comparar(rodada_dir, pdf_id)

    fora = comparacao["fora_do_escopo"]
    assert fora["total"] == 3
    assert fora["por_motivo"] == {
        "regiao_ilegivel": 1,
        "tile_descartado": 1,
        "tile_nao_revisado": 1,
    }
    assert fora["por_metodo"] == {PACOTES: 3}
    motivos = {_local(item["predicao_id"]): item["motivo"] for item in fora["predicoes"]}
    assert motivos == {"C2": "tile_descartado", "C3": "regiao_ilegivel", "C4": "tile_nao_revisado"}
    assert _contagem(comparacao["metodos"][PACOTES]["classe"]) == (1, 0, 0)
    assert _contagem(comparacao["uniao"]["classe"]) == (1, 0, 0)
    citadas = {_local(item["predicao_id"]) for item in comparacao["divergencias"]}
    assert citadas.isdisjoint({"C2", "C3", "C4"})
    assert comparacao["denominadores"]["predicoes"]["fora_do_escopo"] == 3
    assert comparacao["denominadores"]["predicoes"]["em_escopo"] == 1


def test_observacao_em_regiao_ilegivel_sai_do_denominador(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    observacoes = [
        *_observacoes_base(),
        _observacao("O6", B_NO_ILEGIVEL, "TRANSFORMADOR", BL, id_inventario=TRAFO),
    ]
    _preparar(rodada_dir, pdf_id, observacoes=observacoes)
    comparacao = _comparar(rodada_dir, pdf_id)

    assert comparacao["denominadores"]["observacoes"]["fora_do_escopo"] == 1
    assert comparacao["denominadores"]["observacoes"]["operacionais_avaliaveis"] == 5
    assert _contagem(comparacao["uniao"]["classe"]) == (3, 2, 2)
    assert not _divergencias(comparacao, observacao_id="O6")


def test_camada_anotada_igual_base_usa_tile_gemeo_revisado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    predicoes = [_predicao("D1", PACOTES, B_FP, "TRANSFORMADOR", camada="annotation")]
    _preparar(rodada_dir, pdf_id, predicoes=predicoes)
    comparacao = _comparar(rodada_dir, pdf_id)

    assert comparacao["fora_do_escopo"]["total"] == 0
    divergencia = _divergencias(comparacao, tipo="fp")
    assert [(item["camada"], item["tile_evidencia"]) for item in divergencia] == [
        ("annotation", "p001-anotada-t0001")
    ]


def test_escopo_completo_publica_revocacao_global(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id, escopo="completo")
    comparacao = _comparar(rodada_dir, pdf_id)

    assert comparacao["escopo"] == "completo"
    uniao = comparacao["uniao"]["classe"]
    assert uniao["revocacao_global"] == pytest.approx(3 / 5)
    assert uniao["revocacao_global"] == uniao["revocacao_regional"]


# --- ambiguidade, ID exato e papéis -----------------------------------------------------------


def test_alternativas_contam_como_tp_de_classe_e_nunca_como_tp_exato(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    comparacao = _comparar(rodada_dir, pdf_id)

    pacotes = comparacao["metodos"][PACOTES]
    exato = pacotes["id_exato"]
    assert exato["aplicavel"] is True
    # Só A1 casa O1 com o mesmo ID; A2 (sobre a ambígua O3) não é TP nem FP exato.
    assert _contagem(exato) == (1, 1, 3)
    assert exato["ocorrencias_com_id"] == 4
    assert exato["ocorrencias_ambiguas"] == 1
    assert exato["nao_resolvidas"]["ambigua"] == 1
    assert exato["predicoes_com_id"] == 3
    assert exato["predicoes_sem_id"] == 0
    # A2 é TP de classe em O3.
    assert pacotes["classe"]["tp_ia"] == 2
    assert not _divergencias(comparacao, predicao_id=f"{DOC}:A2")
    # O método sem variante não publica métrica de ID exato (não é zero).
    trafos = comparacao["metodos"][TRAFOS]["id_exato"]
    assert trafos["aplicavel"] is False
    assert _contagem(trafos) == (None, None, None)
    assert trafos["predicoes_sem_id"] == 3
    uniao = comparacao["uniao"]["id_exato"]
    assert _contagem(uniao) == (1, 1, 3)
    assert uniao["predicoes_sem_id"] == 2


def test_variante_igual_a_uma_alternativa_nao_vira_tp_exato(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    observacoes = [
        _observacao(
            "O3",
            B_O3,
            "ESTAI",
            TR,
            alternativas={"ids_inventario": [ESTAI_MT, ESTAI_AT], "motivo": "tensão ilegível"},
        )
    ]
    predicoes = [_predicao("A2", PACOTES, B_O3, "ESTAI", variante=ESTAI_MT)]
    _preparar(rodada_dir, pdf_id, observacoes=observacoes, predicoes=predicoes)
    comparacao = _comparar(rodada_dir, pdf_id)

    pacotes = comparacao["metodos"][PACOTES]
    assert _contagem(pacotes["classe"]) == (1, 0, 0)
    assert _contagem(pacotes["id_exato"]) == (0, 0, 0)
    assert pacotes["id_exato"]["nao_resolvidas"]["ambigua"] == 1


def test_id_inventario_divergente_gera_id_errado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    observacoes = [_observacao("O1", B_O1, "TRANSFORMADOR", TL, id_inventario=TRAFO)]
    predicoes = [_predicao("A1", PACOTES, B_O1, "TRANSFORMADOR", variante=TRAFO_OUTRO)]
    _preparar(rodada_dir, pdf_id, observacoes=observacoes, predicoes=predicoes)
    comparacao = _comparar(rodada_dir, pdf_id)

    pacotes = comparacao["metodos"][PACOTES]
    assert _contagem(pacotes["classe"]) == (1, 0, 0)
    assert _contagem(pacotes["id_exato"]) == (0, 1, 1)
    assert pacotes["id_exato"]["id_errado"] == 1
    [divergencia] = _divergencias(comparacao, tipo="id_errado")
    assert divergencia["nivel"] == "id_exato"
    assert divergencia["conta_em"] is None
    assert divergencia["observacao_id"] == "O1"
    assert _local(divergencia["predicao_id"]) == "A1"
    assert divergencia["detalhe"]["id_inventario"] == TRAFO
    assert divergencia["detalhe"]["variantes_preditas"] == [TRAFO_OUTRO]
    assert divergencia["tile_evidencia"] == TL


def test_duas_predicoes_do_mesmo_metodo_geram_uma_duplicata(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    observacoes = [_observacao("O1", B_O1, "TRANSFORMADOR", TL, id_inventario=TRAFO)]
    predicoes = [
        _predicao("A1", PACOTES, B_O1, "TRANSFORMADOR", variante=TRAFO),
        _predicao("A9", PACOTES, [0.11, 0.10, 0.21, 0.20], "TRANSFORMADOR", variante=TRAFO),
    ]
    _preparar(rodada_dir, pdf_id, observacoes=observacoes, predicoes=predicoes)
    comparacao = _comparar(rodada_dir, pdf_id)

    duplicatas = _divergencias(comparacao, tipo="duplicata")
    assert len(duplicatas) == 1
    assert duplicatas[0]["method_id"] == PACOTES
    assert duplicatas[0]["observacao_id"] == "O1"
    assert _local(duplicatas[0]["predicao_id"]) == "A9"
    assert duplicatas[0]["conta_em"] == "fp_ia"
    classe = comparacao["metodos"][PACOTES]["classe"]
    assert _contagem(classe) == (1, 1, 0)
    assert classe["duplicatas"] == 1
    assert not _divergencias(comparacao, tipo="fp")


def test_papel_errado_em_controle_negativo_e_em_predicao_nao_operacional(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    observacoes = [
        _observacao("O1", B_O1, "TRANSFORMADOR", TL, id_inventario=TRAFO),
        _observacao("N1", B_NEG, "TRANSFORMADOR", TL, papel="negativo"),
    ]
    predicoes = [
        _predicao("A1", PACOTES, B_O1, "TRANSFORMADOR", contexto="informative"),
        _predicao("A5", PACOTES, B_NEG, "TRANSFORMADOR"),
    ]
    _preparar(rodada_dir, pdf_id, observacoes=observacoes, predicoes=predicoes)
    comparacao = _comparar(rodada_dir, pdf_id)

    classe = comparacao["metodos"][PACOTES]["classe"]
    # A5 é operacional sobre um controle negativo: FP de papel; A1 é informativa sobre O1.
    assert _contagem(classe) == (0, 1, 1)
    assert classe["papel_errado"] == 1
    assert classe["nao_operacionais"] == 1
    papeis = {
        _local(item["predicao_id"]): (item["observacao_id"], item["conta_em"])
        for item in _divergencias(comparacao, tipo="papel_errado")
    }
    assert papeis == {"A5": ("N1", "fp_ia"), "A1": ("O1", None)}
    fn_pacotes = _divergencias(comparacao, tipo="fn", method_id=PACOTES)
    assert [item["observacao_id"] for item in fn_pacotes] == ["O1"]
    assert comparacao["denominadores"]["observacoes"]["negativos"] == 1
    assert comparacao["denominadores"]["predicoes"]["nao_operacionais_em_escopo"] == 1


def test_provisoria_e_desconhecida_contam_a_parte(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    observacoes = [
        _observacao("O1", B_O1, "TRANSFORMADOR", TL, id_inventario=TRAFO),
        _observacao(
            "P1",
            B_PROV,
            "TRANSFORMADOR",
            TR,
            id_inventario=TRAFO,
            estado="provisorio",
            motivo_estado="traço parcialmente coberto",
        ),
        _observacao("U1", B_NEG, "TRANSFORMADOR", TL, id_inventario=TRAFO, papel="desconhecido"),
    ]
    predicoes = [
        _predicao("A1", PACOTES, B_O1, "TRANSFORMADOR", variante=TRAFO),
        _predicao("A6", PACOTES, B_PROV, "TRANSFORMADOR", variante=TRAFO),
        _predicao("A7", PACOTES, B_NEG, "REGULADOR_TENSAO"),
    ]
    _preparar(rodada_dir, pdf_id, observacoes=observacoes, predicoes=predicoes)
    comparacao = _comparar(rodada_dir, pdf_id)

    classe = comparacao["metodos"][PACOTES]["classe"]
    assert _contagem(classe) == (1, 0, 0)
    assert classe["nao_resolvidas"] == {
        "total": 2,
        "provisorio": 1,
        "papel_desconhecido": 1,
        "ilegivel": 0,
        "local": 0,
    }
    observacoes_den = comparacao["denominadores"]["observacoes"]
    assert observacoes_den["provisorias"] == 1
    assert observacoes_den["papel_desconhecido"] == 1
    assert observacoes_den["operacionais_avaliaveis"] == 1
    assert not _divergencias(comparacao, observacao_id="P1")
    assert not _divergencias(comparacao, predicao_id=f"{DOC}:A6")


def test_metodo_so_de_candidatos_locais_fica_fora_das_metricas(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id, metodos=(PACOTES, TRAFOS, LEGENDA))
    comparacao = _comparar(rodada_dir, pdf_id)

    assert sorted(comparacao["metodos"]) == [PACOTES, TRAFOS]
    assert list(comparacao["metodos_excluidos"]) == [LEGENDA]
    assert _contagem(comparacao["uniao"]["classe"]) == (3, 2, 2)
    assert not _divergencias(comparacao, method_id=LEGENDA)
    assert comparacao["denominadores"]["predicoes"]["candidatos_locais_ignorados"] == 1


def test_metodo_com_falha_de_execucao_e_sinalizado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id, falhas=[(TRAFOS, "base")])
    comparacao = _comparar(rodada_dir, pdf_id)

    assert comparacao["metodos"][TRAFOS]["execucao"]["status"] == "falha"
    assert comparacao["metodos"][TRAFOS]["execucao"]["falhas"] == [{"camada": "base", "pagina": 1}]
    assert comparacao["metodos"][PACOTES]["execucao"]["status"] == "executado"
    assert comparacao["metodos_com_falha"] == [TRAFOS]


# --- classes suportadas por método e lacunas de cobertura ------------------------------------

B_C1 = [0.30, 0.30, 0.40, 0.40]
CABO_ID = "cemig-eo-r3-s16-v001"
SUPORTE = {ESTAIS: ["ESTAI"], TRAFOS: ["TRANSFORMADOR", "REGULADOR_TENSAO"]}


def _cenario_suporte() -> tuple[list[Registro], list[Registro]]:
    """ESTAI (estais) e TRANSFORMADOR (trafos) suportados; nenhum método suporta CABO_AEREO.

    E1 ESTAI casa G1; O1 TRANSFORMADOR não é achado; C1 CABO_AEREO recebe G2 (predição de
    classe não suportada pelo método de estais); C2 CABO_AEREO não é achado por ninguém.
    """
    observacoes = [
        _observacao("E1", B_O3, "ESTAI", TR, id_inventario=ESTAI_MT),
        _observacao("O1", B_O1, "TRANSFORMADOR", TL, id_inventario=TRAFO),
        _observacao("C1", B_C1, CABO, TL, id_inventario=CABO_ID),
        _observacao("C2", B_O5, CABO, BL, id_inventario=CABO_ID),
    ]
    predicoes = [
        _predicao("G1", ESTAIS, B_O3, "ESTAI", variante=ESTAI_MT),
        _predicao("G2", ESTAIS, B_C1, CABO),
    ]
    return observacoes, predicoes


def _preparar_suporte(
    rodada_dir: Path,
    pdf_id: str,
    metodos: Sequence[str],
    suportadas: Mapping[str, Sequence[Any] | None],
) -> None:
    observacoes, predicoes = _cenario_suporte()
    _preparar(
        rodada_dir,
        pdf_id,
        observacoes=observacoes,
        predicoes=predicoes,
        metodos=metodos,
        suportadas=suportadas,
    )


def test_metodo_so_de_estai_nao_recebe_fn_de_cabo_mas_recebe_fp(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar_suporte(rodada_dir, pdf_id, (ESTAIS, TRAFOS), SUPORTE)
    comparacao = _comparar(rodada_dir, pdf_id)

    assert comparacao["schema_version"] == ESQUEMA_COMPARACAO == "curadoria-comparacao-v2"
    estais = comparacao["metodos"][ESTAIS]
    assert estais["classes_suportadas"] == ["ESTAI"]
    assert estais["ocorrencias_fora_do_suporte"] == 3
    # G1 casa E1; G2 (CABO_AEREO, fora do suporte) é FP normal; sem FN de O1, C1 nem C2.
    assert _contagem(estais["classe"]) == (1, 1, 0)
    assert estais["classe"]["revocacao_regional"] == pytest.approx(1.0)
    assert _contagem(estais["por_familia"][FAMILIA[CABO]]) == (0, 1, 0)
    assert estais["por_familia"][FAMILIA[CABO]]["ocorrencias"] == 0
    assert _contagem(estais["por_familia"]["family-f02-18"]) == (0, 0, 0)
    # ID exato também restrito ao conjunto suportado.
    assert _contagem(estais["id_exato"]) == (1, 0, 0)
    assert estais["id_exato"]["ocorrencias_com_id"] == 1
    assert not _divergencias(comparacao, method_id=ESTAIS, tipo="fn")
    [fp] = _divergencias(comparacao, method_id=ESTAIS, tipo="fp")
    assert (_local(fp["predicao_id"]), fp["class_id"]) == ("G2", CABO)
    assert fp["detalhe"]["classe_suportada"] is False
    assert fp["sem_metodo"] is False

    trafos = comparacao["metodos"][TRAFOS]
    assert trafos["classes_suportadas"] == ["REGULADOR_TENSAO", "TRANSFORMADOR"]
    assert _contagem(trafos["classe"]) == (0, 0, 1)
    [fn] = _divergencias(comparacao, method_id=TRAFOS, tipo="fn")
    assert (fn["observacao_id"], fn["perdida_pela_uniao"], fn["sem_metodo"]) == ("O1", True, False)
    assert comparacao["alertas"] == []
    for metodo, bloco in comparacao["metodos"].items():
        divergencias = _divergencias(comparacao, method_id=metodo, nivel="classe")
        assert sum(item["conta_em"] == "fn_ia" for item in divergencias) == bloco["classe"]["fn_ia"]
        assert sum(item["conta_em"] == "fp_ia" for item in divergencias) == bloco["classe"]["fp_ia"]


def test_uniao_mantem_fn_de_classe_sem_metodo_marcado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar_suporte(rodada_dir, pdf_id, (ESTAIS, TRAFOS), SUPORTE)
    comparacao = _comparar(rodada_dir, pdf_id)

    uniao = comparacao["uniao"]
    # A união mede contra todas as ocorrências: G2 casa C1 (TP); O1 e C2 ficam FN.
    assert _contagem(uniao["classe"]) == (2, 0, 2)
    assert uniao["fn_sem_metodo"] == 1
    assert uniao["classes_sem_metodo"] == [CABO]
    [lacuna] = _divergencias(comparacao, sem_metodo=True)
    assert lacuna["tipo"] == "fn"
    assert lacuna["nivel"] == "uniao"
    assert lacuna["method_id"] == METODO_UNIAO
    assert lacuna["conta_em"] == "fn_ia"
    assert lacuna["observacao_id"] == "C2"
    assert lacuna["predicao_id"] is None
    assert lacuna["class_id"] == CABO
    assert lacuna["perdida_pela_uniao"] is True
    assert lacuna["detalhe"]["motivo"] == MOTIVO_SEM_METODO == "classe_sem_metodo"
    assert lacuna["tile_evidencia"] == BL
    # O1 é perdida pela união mas tem método (trafos): não vira lacuna.
    assert not _divergencias(comparacao, nivel="uniao", observacao_id="O1")
    divergencias_uniao = _divergencias(comparacao, nivel="uniao")
    assert sum(item["conta_em"] == "fn_ia" for item in divergencias_uniao) == uniao["fn_sem_metodo"]
    resumo = comparar_pdf(rodada_dir, pdf_id)
    assert resumo["alertas"] == []


def test_metodo_sem_classes_suportadas_gera_alerta_e_mantem_comportamento(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _preparar_suporte(
        rodada_dir,
        pdf_id,
        (ESTAIS, TRAFOS, PACOTES),
        {ESTAIS: ["ESTAI"], TRAFOS: None, PACOTES: []},
    )
    comparacao = _comparar(rodada_dir, pdf_id)

    assert comparacao["alertas"] == [
        {"method_id": PACOTES, "motivo": "vazia", "tipo": ALERTA_SEM_CLASSES},
        {"method_id": TRAFOS, "motivo": "ausente", "tipo": ALERTA_SEM_CLASSES},
    ]
    for metodo in (TRAFOS, PACOTES):
        bloco = comparacao["metodos"][metodo]
        assert bloco["classes_suportadas"] is None
        assert bloco["ocorrencias_fora_do_suporte"] == 0
        # Comportamento antigo: FN de todas as ocorrências operacionais avaliáveis.
        assert _contagem(bloco["classe"]) == (0, 0, 4)
        fn = _divergencias(comparacao, method_id=metodo, tipo="fn")
        assert sorted(item["observacao_id"] for item in fn) == ["C1", "C2", "E1", "O1"]
    assert _contagem(comparacao["metodos"][ESTAIS]["classe"]) == (1, 1, 0)
    # Método sem declaração cobre toda classe: nenhuma falta é atribuída à ausência de método.
    assert comparacao["uniao"]["fn_sem_metodo"] == 0
    assert comparacao["uniao"]["classes_sem_metodo"] == []
    assert not _divergencias(comparacao, sem_metodo=True)
    resumo = comparar_pdf(rodada_dir, pdf_id)
    assert [alerta["method_id"] for alerta in resumo["alertas"]] == [PACOTES, TRAFOS]


def test_classes_suportadas_invalidas_sao_recusadas(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar_suporte(rodada_dir, pdf_id, (ESTAIS,), {ESTAIS: ["ESTAI", 7]})
    with pytest.raises(ComparacaoRecusadaError, match="supported_classes"):
        comparar_pdf(rodada_dir, pdf_id)


# --- recusas ------------------------------------------------------------------------------


def _estado(rodada_dir: Path, pdf_id: str) -> tuple[bytes, list[str]]:
    pasta = diretorio_pdf(rodada_dir, pdf_id)
    return (
        (pasta / "checkpoint.json").read_bytes(),
        sorted(item.name for item in pasta.glob("comparacao-v*.json")),
    )


def test_referencia_nao_congelada_e_recusada_sem_alterar_checkpoint(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _inferir(rodada_dir, pdf_id, _predicoes_base())
    antes = _estado(rodada_dir, pdf_id)

    with pytest.raises(ComparacaoRecusadaError, match="não tem referência congelada"):
        comparar_pdf(rodada_dir, pdf_id)
    assert main(["--rodada", str(rodada_dir), "--pdf", pdf_id]) != 0
    assert "recusado" in capsys.readouterr().out
    assert _estado(rodada_dir, pdf_id) == antes


def test_versao_de_referencia_nao_registrada_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    pasta = diretorio_pdf(rodada_dir, pdf_id) / "referencia"
    orfa = json.loads((pasta / "referencia-v001.json").read_text(encoding="utf-8"))
    (pasta / "referencia-v002.json").write_text(json.dumps(orfa), encoding="utf-8")
    antes = _estado(rodada_dir, pdf_id)

    with pytest.raises(ComparacaoRecusadaError, match="não foi congelada"):
        comparar_pdf(rodada_dir, pdf_id, referencia="v002")
    with pytest.raises(ComparacaoRecusadaError, match="não foi congelada"):
        comparar_pdf(rodada_dir, pdf_id, referencia="v007")
    assert _estado(rodada_dir, pdf_id) == antes


def test_referencia_adulterada_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    arquivo = diretorio_pdf(rodada_dir, pdf_id) / "referencia" / "referencia-v001.json"
    arquivo.write_bytes(arquivo.read_bytes() + b"\n")
    antes = _estado(rodada_dir, pdf_id)

    with pytest.raises(ComparacaoRecusadaError, match="SHA-256"):
        comparar_pdf(rodada_dir, pdf_id)
    assert main(["--rodada", str(rodada_dir), "--pdf", pdf_id]) == 1
    assert _estado(rodada_dir, pdf_id) == antes


def test_sha256_do_pdf_divergente_entre_referencia_e_inferencia_e_recusado(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _congelar(rodada_dir, pdf_id, _referencia(rodada_dir, pdf_id))
    # Inferência registrada à mão com SHA-256 de outro PDF (o CLI de inferência recusaria).
    pasta = diretorio_pdf(rodada_dir, pdf_id) / "inferencia-v001"
    _gravar(
        pasta / "simbolos" / "predictions.json", _documento_predicoes("0" * 64, _predicoes_base())
    )
    _gravar(pasta / "simbolos" / "manifest.json", {"schema_version": 1})
    transicionar(rodada_dir, pdf_id, "inferido", artefatos=[pasta], dados={"versao": pasta.name})
    antes = _estado(rodada_dir, pdf_id)

    with pytest.raises(ComparacaoRecusadaError, match="SHA-256 do PDF"):
        comparar_pdf(rodada_dir, pdf_id)
    assert main(["--rodada", str(rodada_dir), "--pdf", pdf_id]) == 1
    assert _estado(rodada_dir, pdf_id) == antes


def test_inferencia_adulterada_ou_sem_registro_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    pasta = diretorio_pdf(rodada_dir, pdf_id)
    (pasta / "inferencia-v009").mkdir()
    antes = _estado(rodada_dir, pdf_id)
    with pytest.raises(ComparacaoRecusadaError, match="inferencia-v009"):
        comparar_pdf(rodada_dir, pdf_id, inferencia="v009")

    predicoes = pasta / "inferencia-v001" / "simbolos" / "predictions.json"
    dados = json.loads(predicoes.read_text(encoding="utf-8"))
    dados["predictions"] = dados["predictions"][:1]
    predicoes.write_text(json.dumps(dados), encoding="utf-8")
    with pytest.raises(ComparacaoRecusadaError, match="SHA-256"):
        comparar_pdf(rodada_dir, pdf_id)
    assert _estado(rodada_dir, pdf_id) == antes


def test_sem_inferencia_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _congelar(rodada_dir, pdf_id, _referencia(rodada_dir, pdf_id))
    antes = _estado(rodada_dir, pdf_id)
    with pytest.raises(ComparacaoRecusadaError, match="inferência"):
        comparar_pdf(rodada_dir, pdf_id)
    assert _estado(rodada_dir, pdf_id) == antes


def test_fase_terminal_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    transicionar(rodada_dir, pdf_id, "encerrado_com_pendencias", nota="teste")
    antes = _estado(rodada_dir, pdf_id)
    with pytest.raises(ComparacaoRecusadaError, match="fase terminal"):
        comparar_pdf(rodada_dir, pdf_id)
    assert _estado(rodada_dir, pdf_id) == antes


def test_predicao_com_bbox_invalida_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(
        rodada_dir,
        pdf_id,
        predicoes=[_predicao("A1", PACOTES, [0.3, 0.1, 0.2, 0.2], "TRANSFORMADOR")],
    )
    antes = _estado(rodada_dir, pdf_id)
    with pytest.raises(ComparacaoRecusadaError, match="A1"):
        comparar_pdf(rodada_dir, pdf_id)
    assert _estado(rodada_dir, pdf_id) == antes


# --- checkpoint, versões e determinismo -------------------------------------------------------


def test_checkpoint_avanca_para_comparado_com_hash_e_resumo(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    resumo = comparar_pdf(rodada_dir, pdf_id, agora=AGORA)

    assert resumo["status"] == "sucesso"
    assert resumo["versao"] == "comparacao-v001.json"
    assert resumo["checkpoint_avancado"] is True
    assert resumo["uniao"] == {"fn_ia": 2, "fp_ia": 2, "tp_ia": 3}
    checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
    assert checkpoint["fase"] == "comparado"
    [artefato] = checkpoint["marcos"]["comparado"]["artefatos"]
    assert artefato["caminho"] == f"pdfs/{pdf_id}/comparacao-v001.json"
    evento = checkpoint["historico"][-1]
    assert evento["dados"]["inferencia"] == "inferencia-v001"
    assert evento["dados"]["referencia"] == "referencia-v001.json"
    assert evento["dados"]["escopo"] == "regional"
    assert evento["dados"]["uniao"] == {"fn_ia": 2, "fp_ia": 2, "tp_ia": 3}
    comparacao = json.loads((rodada_dir / artefato["caminho"]).read_text(encoding="utf-8"))
    assert comparacao["referencia"]["versao"] == "referencia-v001.json"
    assert comparacao["referencia"]["exposicao_predicoes"] is False
    assert comparacao["inferencia"]["versao"] == "inferencia-v001"
    assert comparacao["vigente"] is True
    texto = json.dumps(comparacao)
    assert "Users" not in texto and ":\\\\" not in texto


def test_duas_execucoes_sao_deterministicas_e_nao_sobrescrevem(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    pasta = diretorio_pdf(rodada_dir, pdf_id)
    (pasta / "comparacao-v001.json").write_text("ocupado", encoding="utf-8")

    primeira = comparar_pdf(rodada_dir, pdf_id)
    segunda = comparar_pdf(rodada_dir, pdf_id)

    assert (primeira["versao"], segunda["versao"]) == (
        "comparacao-v002.json",
        "comparacao-v003.json",
    )
    assert (pasta / "comparacao-v001.json").read_text(encoding="utf-8") == "ocupado"
    assert (pasta / "comparacao-v002.json").read_bytes() == (
        pasta / "comparacao-v003.json"
    ).read_bytes()


def test_versoes_nao_vigentes_geram_diagnostico_sem_avancar_checkpoint(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    _inferir(rodada_dir, pdf_id, _predicoes_base()[:3])
    antes = (diretorio_pdf(rodada_dir, pdf_id) / "checkpoint.json").read_bytes()

    resumo = comparar_pdf(rodada_dir, pdf_id, inferencia="v001")

    assert resumo["status"] == "sucesso"
    assert resumo["checkpoint_avancado"] is False
    assert (diretorio_pdf(rodada_dir, pdf_id) / "checkpoint.json").read_bytes() == antes
    comparacao = json.loads((rodada_dir / resumo["arquivo"]).read_text(encoding="utf-8"))
    assert comparacao["vigente"] is False
    assert comparacao["inferencia"]["vigente"] is False
    assert _contagem(comparacao["uniao"]["classe"]) == (3, 2, 2)
    # A vigente (v002) só tem o método de pacotes: sem B, a união perde O2.
    vigente = _comparar(rodada_dir, pdf_id)
    assert vigente["inferencia"]["versao"] == "inferencia-v002"
    assert _contagem(vigente["uniao"]["classe"]) == (2, 1, 3)


def test_referencia_revisada_anterior_pode_ser_comparada_como_diagnostico(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    nova = _referencia(rodada_dir, pdf_id, _observacoes_base()[:2])
    arquivo = _gravar(rodada_dir.parent / "entrada" / "revisada.json", nova)
    revisar(rodada_dir, pdf_id, arquivo, motivo="teste", exposicao_predicoes=True, agora=AGORA)

    vigente = _comparar(rodada_dir, pdf_id)
    assert vigente["referencia"]["versao"] == "referencia-v002.json"
    assert vigente["referencia"]["exposicao_predicoes"] is True
    assert vigente["denominadores"]["observacoes"]["total"] == 2
    anterior = comparar_pdf(rodada_dir, pdf_id, referencia="v001")
    assert anterior["checkpoint_avancado"] is False


def test_funcao_pura_comparar_e_deterministica(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    entrada = curation_compare.carregar_entradas(rodada_dir, pdf_id)
    primeira = comparar(**entrada.argumentos())
    segunda = comparar(**copy.deepcopy(entrada).argumentos())
    assert primeira == segunda


# --- CLI ----------------------------------------------------------------------------------


def test_cli_por_onda_compara_e_imprime_resumo(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)

    assert main(["--rodada", str(rodada_dir), "--onda", "1"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["totais"] == {"falha": 0, "recusado": 0, "sucesso": 1}
    [registro] = saida["pdfs"]
    assert registro["pdf_id"] == pdf_id
    assert registro["versao"] == "comparacao-v001.json"
    assert registro["uniao"] == {"fn_ia": 2, "fp_ia": 2, "tp_ia": 3}


def test_cli_recusa_selecao_e_versao_invalidas(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    _preparar(rodada_dir, pdf_id)
    assert main(["--rodada", str(rodada_dir)]) == 1
    assert "--onda" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["--rodada", str(rodada_dir), "--pdf", pdf_id, "--inferencia", "2"])
    with pytest.raises(SystemExit):
        main(["--rodada", str(rodada_dir), "--pdf", pdf_id, "--referencia", "v1"])
