from __future__ import annotations

import itertools
import json
import shutil
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pymupdf
import pytest
import scripts.symbol_benchmark_runner as runner
from scripts import curation_backlog
from scripts.curation_backlog import (
    DONOS,
    ESQUEMA_BACKLOG,
    MAX_EXEMPLOS,
    BacklogRecusadoError,
    agregar,
    dependencias,
    donos,
    formar_pistas,
    gerar_backlog,
    main,
    metodos_sem_dono,
)
from scripts.curation_compare import (
    ALERTA_SEM_CLASSES,
    ESQUEMA_COMPARACAO,
    METODO_UNIAO,
    MOTIVO_SEM_METODO,
    _Contexto,
    _divergencia,
)
from scripts.curation_render import ParametrosRender, renderizar
from scripts.curation_round import (
    ROOT,
    carregar_rodada,
    diretorio_pdf,
    hash_arquivo,
    iniciar_rodada,
    json_canonico,
    transicionar,
)

from zeny_project_handler.adapters.analysis import raster_symbols, structural_symbols

AGORA = "2026-10-15T12:00:00+00:00"
Registro = dict[str, Any]
# Página de 200 x 200 pt a 72 DPI com tiles de 100 px: grade 2 x 2 por camada.
RAPIDO = ParametrosRender(lado_tile_px=100, sobreposicao=0.0, dpi_detalhe=72)
TL, TR, BL = "p001-base-t0000", "p001-base-t0001", "p001-base-t0100"
ANALISE = "src/zeny_project_handler/adapters/analysis"
LEGADO = "legacy-vector-symbols"
TRAFOS = "transformer-vector-shapes"
ESTAIS = "guy-vector-shapes"
PACOTES = "declarative-vector-packages"
RASTER_T = "raster-template"
RASTER_H = "raster-hough-generalizado"
EST_RASTER = "structural-raster-graph"
EST_VETOR = "structural-vector-graph"
LEGENDA = "document-local-legend"
F_TRAFO = "family-f02-18"
F_PACOTE = "family-f02-05"
F_SEM_PACOTE = "family-f02-14"
F_CABO = "family-f02-16"
F_POSTE = "family-f02-03"
CABO = "CABO_AEREO"
POSTE = "POSTE"


# --- rodada sintética --------------------------------------------------------------------------


def _criar_pdf(caminho: Path, deslocamento: float) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=200, height=200)
        for x, y in ((20, 20), (120, 20), (20, 120)):
            caixa = pymupdf.Rect(  # type: ignore[no-untyped-call]
                x + deslocamento, y, x + deslocamento + 30, y + 30
            )
            pagina.draw_rect(caixa, color=(0, 0, 0), fill=(0, 0, 0))
        documento.save(caminho)


@pytest.fixture(scope="module")
def modelo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("modelo-backlog")
    for numero in range(3):
        _criar_pdf(base / "corpus" / f"{numero}.pdf", float(numero))
    rodada = base / "rodada"
    iniciar_rodada(
        rodada, base / "corpus", concorrencia=3, raiz_repositorio=base / "sem-git", agora=AGORA
    )
    ids = _ids(rodada)
    assert len(ids) == 3
    assert renderizar(rodada, ids, parametros=RAPIDO, jobs=1)["totais"]["sucesso"] == 3
    return base


@pytest.fixture
def rodada(modelo: Path, tmp_path: Path) -> Path:
    copia = tmp_path / "base"
    shutil.copytree(modelo, copia)
    return copia / "rodada"


def _ids(rodada: Path) -> list[str]:
    return [str(item["pdf_id"]) for item in carregar_rodada(rodada)["pdfs"]]


def _div(
    metodo: str,
    tipo: str,
    familia: str,
    classe: str,
    *,
    n: int,
    tile: str | None = TL,
    pagina: int = 1,
    camada: str = "base",
    perdida: bool | None = None,
    conta_em: str | None = "padrao",
    motivo: str | None = None,
    nivel: str | None = None,
    sem_metodo: bool = False,
) -> Registro:
    """Divergência no formato de ``curation_compare`` (``curadoria-comparacao-v2``)."""
    padrao = {"fp": "fp_ia", "fn": "fn_ia", "duplicata": "fp_ia", "papel_errado": "fp_ia"}
    observacao = f"O{n}" if tipo != "fp" else None
    predicao = f"P{n}" if tipo != "fn" else None
    return {
        "id": "div-" + sha256(json_canonico([metodo, tipo, n]).encode()).hexdigest()[:16],
        "tipo": tipo,
        "nivel": nivel or ("id_exato" if tipo == "id_errado" else "classe"),
        "conta_em": padrao.get(tipo) if conta_em == "padrao" else conta_em,
        "method_id": metodo,
        "observacao_id": observacao,
        "predicao_id": predicao,
        "pagina": pagina,
        "camada": camada,
        "familia": familia,
        "class_id": classe,
        "bbox": [0.1, 0.1, 0.2, 0.2],
        "tile_evidencia": tile,
        "perdida_pela_uniao": (False if perdida is None else perdida) if tipo == "fn" else None,
        "sem_metodo": sem_metodo,
        "detalhe": {"motivo": motivo or {"fn": "sem_predicao"}.get(tipo, "sem_ocorrencia")},
    }


def _lacuna(familia: str, classe: str, *, n: int, tile: str | None = TL) -> Registro:
    """FN da união numa classe que nenhum método declara suportar."""
    return _div(
        METODO_UNIAO,
        "fn",
        familia,
        classe,
        n=n,
        tile=tile,
        perdida=True,
        motivo=MOTIVO_SEM_METODO,
        nivel="uniao",
        sem_metodo=True,
    )


def _comparacao(
    pdf_id: str,
    divergencias: Sequence[Registro],
    *,
    status: dict[str, str] | None = None,
) -> Registro:
    situacao = {
        item["method_id"]: "executado" for item in divergencias if item["method_id"] != METODO_UNIAO
    }
    situacao.update(status or {})
    metodos = {
        metodo: {
            "execucao": {
                "status": estado,
                "por_status": {},
                "falhas": [{"pagina": 1, "camada": "base"}] if estado == "falha" else [],
            }
        }
        for metodo, estado in situacao.items()
    }
    return {
        "schema_version": ESQUEMA_COMPARACAO,
        "pdf_id": pdf_id,
        "vigente": True,
        "escopo": "regional",
        "metodos": metodos,
        "metodos_com_falha": sorted(m for m, e in situacao.items() if e == "falha"),
        "metodos_excluidos": {},
        "divergencias": list(divergencias),
        "alertas": [],
    }


def _registrar(rodada: Path, pdf_id: str, comparacao: Registro, *, auditar: bool = True) -> Path:
    """Leva o checkpoint até ``comparado`` (e ``auditado``) com artefatos sintéticos."""
    pasta = diretorio_pdf(rodada, pdf_id)
    inferencia = pasta / "inferencia-v001"
    inferencia.mkdir(exist_ok=True)
    (inferencia / "predictions.json").write_text("{}", encoding="utf-8")
    referencia = pasta / "referencia" / "referencia-v001.json"
    referencia.parent.mkdir(exist_ok=True)
    referencia.write_text("{}", encoding="utf-8")
    arquivo = pasta / "comparacao-v001.json"
    arquivo.write_text(json_canonico(comparacao), encoding="utf-8")
    transicionar(rodada, pdf_id, "inferido", artefatos=[inferencia], agora=AGORA)
    transicionar(rodada, pdf_id, "referencia_congelada", artefatos=[referencia], agora=AGORA)
    transicionar(rodada, pdf_id, "comparado", artefatos=[arquivo], agora=AGORA)
    if auditar:
        transicionar(rodada, pdf_id, "auditado", artefatos=[referencia], agora=AGORA)
    return arquivo


def _cenario_principal(rodada: Path) -> list[str]:
    """FN de transformador nos três PDFs e FP de pacote só no segundo."""
    ids = _ids(rodada)
    for posicao, pdf_id in enumerate(ids):
        divergencias = [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1, perdida=True)]
        if posicao == 1:
            divergencias.append(_div(PACOTES, "fp", F_PACOTE, "CHAVE_FUSIVEL", n=2, tile=TR))
        _registrar(rodada, pdf_id, _comparacao(pdf_id, divergencias))
    return ids


def _ler_backlog(rodada: Path, onda: int = 1) -> Registro:
    dados = json.loads((rodada / "ondas" / str(onda) / "backlog.json").read_text("utf-8"))
    assert isinstance(dados, dict)
    return dados


# --- critério 1: agrupamento e prioridade ------------------------------------------------------


def test_tres_pdfs_geram_dois_grupos_com_transformador_primeiro(rodada: Path) -> None:
    ids = _cenario_principal(rodada)
    assert main(["--rodada", str(rodada), "--onda", "1"]) == 0
    backlog = _ler_backlog(rodada)
    assert backlog["schema_version"] == ESQUEMA_BACKLOG
    assert backlog["onda"] == 1
    grupos = backlog["grupos"]
    assert [(g["method_id"], g["tipo"]) for g in grupos] == [(TRAFOS, "fn"), (PACOTES, "fp")]
    trafo, pacote = grupos
    assert (trafo["prioridade"], pacote["prioridade"]) == (1, 2)
    assert trafo["pdfs_afetados"] == 3 and trafo["pdfs"] == ids
    assert trafo["ocorrencias"] == 3 and trafo["perdidas_pela_uniao"] == 3
    assert (trafo["familia"], trafo["class_id"]) == (F_TRAFO, "TRANSFORMADOR")
    assert pacote["pdfs_afetados"] == 1 and pacote["pdfs"] == [ids[1]]
    assert [e["pdf_id"] for e in trafo["exemplos"]] == ids
    assert [e["pdf_id"] for e in pacote["exemplos"]] == [ids[1]]
    for grupo in grupos:
        for exemplo in grupo["exemplos"]:
            assert exemplo["tile_evidencia"] in {TL, TR}
            caminho = exemplo["tile_arquivo"]
            assert caminho.startswith(f"pdfs/{exemplo['pdf_id']}/render/")
            assert (rodada / caminho).is_file()
            assert exemplo["comparacao"] == f"pdfs/{exemplo['pdf_id']}/comparacao-v001.json"
    assert trafo["donos"] == [f"{ANALISE}/pymupdf_transformers.py"]
    assert backlog["totais"]["divergencias"] == 4
    assert backlog["totais"]["divergencias_agrupadas"] == 4
    assert backlog["alertas"] == []
    texto = (rodada / "ondas" / "1" / "backlog.md").read_text("utf-8")
    assert "# Backlog da onda 1" in texto
    assert texto.index(TRAFOS) < texto.index(PACOTES)


def test_prioridade_e_por_pdfs_afetados_e_nao_por_ocorrencias(rodada: Path) -> None:
    ids = _ids(rodada)
    muitas = [_div(ESTAIS, "fp", "family-f02-21", "ESTAI", n=n) for n in range(10)]
    _registrar(
        rodada,
        ids[0],
        _comparacao(ids[0], [*muitas, _div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=50)]),
    )
    _registrar(
        rodada, ids[1], _comparacao(ids[1], [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=51)])
    )
    _registrar(rodada, ids[2], _comparacao(ids[2], []))
    backlog = gerar_backlog(rodada, 1)["backlog"]
    grupos = backlog["grupos"]
    assert [(g["method_id"], g["pdfs_afetados"], g["ocorrencias"]) for g in grupos] == [
        (TRAFOS, 2, 2),
        (ESTAIS, 1, 10),
    ]


def test_desempate_por_ocorrencias_e_perdidas_pela_uniao() -> None:
    entradas = [
        _entrada(
            "p1",
            [
                _div(ESTAIS, "fp", "family-f02-21", "ESTAI", n=1),
                _div(ESTAIS, "fp", "family-f02-21", "ESTAI", n=2),
                _div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=3, perdida=False),
                _div(LEGADO, "fn", F_TRAFO, "TRANSFORMADOR", n=4, perdida=True),
            ],
        )
    ]
    grupos = agregar(1, entradas)["grupos"]
    assert [g["method_id"] for g in grupos] == [ESTAIS, LEGADO, TRAFOS]


def test_chave_do_grupo_separa_tipo_familia_classe_e_metodo() -> None:
    base = _div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1)
    variacoes = [
        base,
        _div(TRAFOS, "fp", F_TRAFO, "TRANSFORMADOR", n=2),
        _div(TRAFOS, "fn", "family-f02-19", "TRANSFORMADOR", n=3),
        _div(TRAFOS, "fn", F_TRAFO, "REGULADOR_TENSAO", n=4),
        _div(LEGADO, "fn", F_TRAFO, "TRANSFORMADOR", n=5),
    ]
    entradas = [
        _entrada("p1", variacoes),
        _entrada("p2", [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=6)]),
    ]
    grupos = agregar(1, entradas)["grupos"]
    chaves = {(g["tipo"], g["familia"], g["class_id"], g["method_id"]) for g in grupos}
    assert len(grupos) == 5 == len(chaves)
    assert grupos[0]["method_id"] == TRAFOS and grupos[0]["pdfs"] == ["p1", "p2"]
    assert len({g["id"] for g in grupos}) == 5


def test_exemplos_ficam_limitados_e_distribuidos_entre_pdfs() -> None:
    entradas = [
        _entrada("p1", [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=n) for n in range(6)]),
        _entrada("p2", [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=n) for n in range(10, 12)]),
    ]
    (grupo,) = agregar(1, entradas)["grupos"]
    exemplos = grupo["exemplos"]
    assert len(exemplos) == MAX_EXEMPLOS == 5
    assert [e["pdf_id"] for e in exemplos] == ["p1", "p2", "p1", "p2", "p1"]
    assert grupo["ocorrencias"] == 8 and grupo["ocorrencias_por_pdf"] == {"p1": 6, "p2": 2}


def test_diagnosticos_e_contagens_por_conta_em() -> None:
    entradas = [
        _entrada(
            "p1",
            [
                _div(PACOTES, "id_errado", F_PACOTE, "CHAVE_FUSIVEL", n=1, conta_em=None),
                _div(PACOTES, "fp", F_PACOTE, "CHAVE_FUSIVEL", n=2),
            ],
        )
    ]
    grupos = {g["tipo"]: g for g in agregar(1, entradas)["grupos"]}
    assert grupos["id_errado"]["diagnostico"] is True
    assert grupos["id_errado"]["conta_em"] == {"diagnostico": 1}
    assert grupos["fp"]["diagnostico"] is False
    assert grupos["fp"]["conta_em"] == {"fp_ia": 1}


# --- critério 2: pistas disjuntas --------------------------------------------------------------


def test_grupos_que_dependem_do_mesmo_arquivo_ficam_na_mesma_pista() -> None:
    entradas = [
        _entrada(
            "p1",
            [
                _div(RASTER_T, "fp", F_TRAFO, "TRANSFORMADOR", n=1),
                _div(RASTER_H, "fn", F_TRAFO, "TRANSFORMADOR", n=2),
                _div(PACOTES, "fp", F_PACOTE, "CHAVE_FUSIVEL", n=3),
                _div(PACOTES, "fn", F_SEM_PACOTE, "ESTAI", n=4),
                _div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=5),
            ],
        )
    ]
    backlog = agregar(1, entradas)
    pista_de = {g["method_id"] + g["tipo"]: g["pista"] for g in backlog["grupos"]}
    assert pista_de[RASTER_T + "fp"] == pista_de[RASTER_H + "fn"]
    assert pista_de[PACOTES + "fp"] == pista_de[PACOTES + "fn"]
    assert len({pista_de[RASTER_T + "fp"], pista_de[PACOTES + "fp"], pista_de[TRAFOS + "fn"]}) == 3
    pistas = {p["id"]: p for p in backlog["pistas"]}
    assert len(pistas) == 3
    pacotes = pistas[pista_de[PACOTES + "fp"]]
    assert pacotes["arquivos"] == [
        f"{ANALISE}/declarative_symbols.py",
        f"{ANALISE}/symbol_packages/{F_PACOTE}.json",
    ]
    _assert_pistas_disjuntas(backlog["pistas"])
    assert backlog["paralelismo"]["arquivos_compartilhados"] == []
    assert sorted(backlog["paralelismo"]["pistas_paralelas"]) == sorted(pistas)


def _assert_pistas_disjuntas(pistas: Sequence[Registro]) -> None:
    paralelas = [p for p in pistas if p["paralela"]]
    for primeira, segunda in itertools.combinations(paralelas, 2):
        assert not set(primeira["arquivos"]) & set(segunda["arquivos"]), (primeira, segunda)
    vistos: dict[str, str] = {}
    for pista in pistas:
        for arquivo in pista["arquivos"]:
            assert vistos.setdefault(arquivo, pista["id"]) == pista["id"]


@pytest.mark.parametrize("tamanho", [2, 3, 4])
def test_pistas_paralelas_nunca_compartilham_arquivo(tamanho: int) -> None:
    familias = (F_TRAFO, F_PACOTE, F_SEM_PACOTE)
    combinacoes = list(itertools.combinations(sorted(DONOS), tamanho))
    for metodos in combinacoes:
        divergencias = [
            _div(metodo, "fn", familias[i % 3], "X", n=i) for i, metodo in enumerate(metodos)
        ]
        backlog = agregar(1, [_entrada("p1", divergencias)])
        _assert_pistas_disjuntas(backlog["pistas"])
        assert backlog["paralelismo"]["arquivos_compartilhados"] == []
        cobertos = {a for p in backlog["pistas"] for a in p["arquivos"]}
        esperados = {a for g in backlog["grupos"] for a in g["donos"]}
        assert cobertos == esperados


def test_formar_pistas_une_por_arquivo_comum_transitivamente() -> None:
    itens = [
        {"id": "a", "donos": ["x.py"], "pdfs": ["p1"], "ocorrencias": 1},
        {"id": "b", "donos": ["x.py", "y.py"], "pdfs": ["p2"], "ocorrencias": 1},
        {"id": "c", "donos": ["y.py", "z.py"], "pdfs": ["p3"], "ocorrencias": 1},
        {"id": "d", "donos": ["w.py"], "pdfs": ["p1"], "ocorrencias": 1},
    ]
    pistas = formar_pistas(itens)
    assert [sorted(p["itens"]) for p in pistas] == [["a", "b", "c"], ["d"]]
    assert pistas[0]["arquivos"] == ["x.py", "y.py", "z.py"]
    assert all(p["paralela"] for p in pistas)


def test_acoplamento_por_dependencia_editada_por_outra_pista_e_declarado() -> None:
    entradas = [
        _entrada(
            "p1",
            [
                _div(LEGADO, "fn", F_TRAFO, "TRANSFORMADOR", n=1),
                _div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=2),
            ],
        )
    ]
    backlog = agregar(1, entradas)
    pistas = {tuple(p["arquivos"]): p for p in backlog["pistas"]}
    trafos = pistas[(f"{ANALISE}/pymupdf_transformers.py",)]
    legado = next(p for p in backlog["pistas"] if p is not trafos)
    assert f"{ANALISE}/pymupdf_symbols.py" in legado["arquivos"]
    assert f"{ANALISE}/pymupdf_symbols.py" in trafos["dependencias"]
    assert {"arquivo": f"{ANALISE}/pymupdf_symbols.py", "pista": legado["id"]} in trafos[
        "acoplamentos"
    ]
    assert trafos["paralela"] and legado["paralela"]


def test_dependencias_sao_transitivas_dentro_do_pacote_de_analise() -> None:
    legenda = dependencias([f"{ANALISE}/legend_symbols.py"])
    assert f"{ANALISE}/raster_symbols.py" in legenda
    trafos = dependencias([f"{ANALISE}/pymupdf_transformers.py"])
    assert {f"{ANALISE}/pymupdf_symbols.py", f"{ANALISE}/pymupdf_support.py"} <= set(trafos)
    assert f"{ANALISE}/pymupdf_transformers.py" not in trafos
    # pymupdf_analyzer -> pymupdf_ocr -> pymupdf_ocr_page: só pelo fecho transitivo.
    legado = dependencias(DONOS[LEGADO])
    assert f"{ANALISE}/pymupdf_ocr.py" in legado
    assert f"{ANALISE}/pymupdf_ocr_page.py" in legado
    assert not set(DONOS[LEGADO]) & set(legado)


# --- critério 3: todo method_id do runner tem dono ---------------------------------------------

FUNCOES_DE_METADADOS = {
    "method_metadata",
    "transformer_method_metadata",
    "guy_method_metadata",
    "package_method_metadata",
    "raster_method_metadata",
    "structural_method_metadata",
    "legend_method_metadata",
}


def _metodos_emitidos_pelo_runner() -> set[str]:
    encontradas = {
        nome
        for nome in dir(runner)
        if nome.endswith("method_metadata") and callable(getattr(runner, nome))
    }
    assert encontradas == FUNCOES_DE_METADADOS, (
        "o runner mudou o conjunto de funções *_method_metadata; inclua a nova função aqui e "
        "dê dono aos method_id dela em scripts/curation_backlog.py"
    )
    estruturais = (
        structural_symbols.ConfiguracaoDetectorEstrutural(entrada="raster"),
        structural_symbols.ConfiguracaoDetectorEstrutural(entrada="vetor"),
    )
    registros = [
        runner.method_metadata(),
        runner.transformer_method_metadata(),
        runner.guy_method_metadata(),
        runner.package_method_metadata(),
        *runner.raster_method_metadata(
            raster_symbols.carregar_templates_raster(), raster_symbols.ConfiguracaoDetectorRaster()
        ),
        *runner.structural_method_metadata(estruturais),
        runner.legend_method_metadata(include_ocr=False),
        runner.legend_method_metadata(include_ocr=True),
    ]
    return {str(registro["id"]) for registro in registros}


def test_todo_method_id_emitido_pelo_runner_tem_dono() -> None:
    emitidos = _metodos_emitidos_pelo_runner()
    assert len(emitidos) == 9
    assert metodos_sem_dono(emitidos) == []
    assert set(DONOS) == emitidos, "dono de method_id que o runner não emite mais"


def test_cobertura_do_mapa_detecta_metodo_sem_dono(monkeypatch: pytest.MonkeyPatch) -> None:
    reduzido = {chave: valor for chave, valor in DONOS.items() if chave != RASTER_H}
    monkeypatch.setattr(curation_backlog, "DONOS", reduzido)
    assert metodos_sem_dono(_metodos_emitidos_pelo_runner()) == [RASTER_H]


def test_arquivos_donos_existem_e_ficam_na_analise() -> None:
    for metodo, arquivos in DONOS.items():
        assert arquivos, metodo
        for arquivo in arquivos:
            assert arquivo.startswith(f"{ANALISE}/"), arquivo
            assert (ROOT / arquivo).is_file(), arquivo


def test_dono_de_pacotes_inclui_o_arquivo_da_familia_quando_existe() -> None:
    assert donos(PACOTES, F_PACOTE) == (
        f"{ANALISE}/declarative_symbols.py",
        f"{ANALISE}/symbol_packages/{F_PACOTE}.json",
    )
    assert donos(PACOTES, F_SEM_PACOTE) == (f"{ANALISE}/declarative_symbols.py",)
    assert donos(PACOTES, "../../segredo") == (f"{ANALISE}/declarative_symbols.py",)
    assert donos(TRAFOS, F_PACOTE) == (f"{ANALISE}/pymupdf_transformers.py",)
    assert donos("metodo-novo", F_TRAFO) == ()


def test_metodo_sem_dono_fica_fora_das_pistas_e_gera_alerta() -> None:
    entradas = [
        _entrada(
            "p1",
            [
                _div("metodo-novo", "fn", F_TRAFO, "TRANSFORMADOR", n=1),
                _div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=2),
            ],
        )
    ]
    backlog = agregar(1, entradas)
    sem_dono = next(g for g in backlog["grupos"] if g["method_id"] == "metodo-novo")
    assert sem_dono["donos"] == [] and sem_dono["pista"] is None
    assert backlog["sem_dono"] == [sem_dono["id"]]
    assert all(sem_dono["id"] not in p["grupos"] for p in backlog["pistas"])
    assert {"tipo": "metodo_sem_dono", "method_id": "metodo-novo"} in [
        {k: a[k] for k in ("tipo", "method_id")} for a in backlog["alertas"]
    ]


# --- falha de execução e método sem registro ---------------------------------------------------


def test_metodo_com_falha_vira_falha_de_execucao_e_nao_divergencia_comum() -> None:
    entradas = [
        _entrada(
            "p1",
            [
                _div(RASTER_T, "fn", F_TRAFO, "TRANSFORMADOR", n=1),
                _div(RASTER_T, "fn", F_TRAFO, "TRANSFORMADOR", n=2),
                _div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=3),
            ],
            status={RASTER_T: "falha"},
        ),
        _entrada(
            "p2",
            [_div(RASTER_T, "fn", F_TRAFO, "TRANSFORMADOR", n=4)],
        ),
    ]
    backlog = agregar(1, entradas)
    raster = [g for g in backlog["grupos"] if g["method_id"] == RASTER_T]
    assert len(raster) == 1 and raster[0]["pdfs"] == ["p2"] and raster[0]["ocorrencias"] == 1
    (falha,) = backlog["falhas_execucao"]
    assert falha["method_id"] == RASTER_T and falha["status"] == "falha"
    assert falha["pdfs"] == ["p1"] and falha["divergencias_retidas"] == 2
    assert falha["locais"] == {"p1": [{"camada": "base", "pagina": 1}]}
    assert falha["donos"] == [f"{ANALISE}/raster_symbols.py"]
    pista = next(p for p in backlog["pistas"] if falha["id"] in p["falhas_execucao"])
    assert raster[0]["id"] in pista["grupos"]
    resumo = {p["pdf_id"]: p for p in backlog["pdfs"]}
    assert resumo["p1"]["metodos_com_falha"] == [RASTER_T]
    assert resumo["p1"]["divergencias_retidas"] == {RASTER_T: 2}
    assert backlog["totais"]["divergencias_retidas"] == 2
    assert backlog["totais"]["divergencias_agrupadas"] == 2
    assert any(a["tipo"] == "metodo_com_falha" and a["pdf_id"] == "p1" for a in backlog["alertas"])


def test_metodo_listado_em_metodos_com_falha_tambem_e_falha() -> None:
    comparacao = _comparacao("p1", [_div(ESTAIS, "fn", "family-f02-21", "ESTAI", n=1)])
    comparacao["metodos_com_falha"] = [ESTAIS]
    backlog = agregar(1, [_entrada("p1", comparacao=comparacao)])
    assert backlog["grupos"] == []
    assert [f["method_id"] for f in backlog["falhas_execucao"]] == [ESTAIS]


def test_metodo_sem_registro_gera_alerta_e_retem_divergencias() -> None:
    entradas = [
        _entrada(
            "p1",
            [_div(EST_VETOR, "fn", F_TRAFO, "TRANSFORMADOR", n=n) for n in range(3)],
            status={EST_VETOR: "sem_registro"},
        )
    ]
    backlog = agregar(1, entradas)
    assert backlog["grupos"] == [] and backlog["pistas"] == []
    (falha,) = backlog["falhas_execucao"]
    assert falha["status"] == "sem_registro" and falha["pista"] is None
    assert falha["divergencias_retidas"] == 3
    assert backlog["pdfs"][0]["metodos_sem_registro"] == [EST_VETOR]
    assert any(a["tipo"] == "metodo_sem_registro" for a in backlog["alertas"])


# --- entradas da onda --------------------------------------------------------------------------


def test_pdf_sem_comparacao_vigente_gera_alerta(rodada: Path) -> None:
    ids = _ids(rodada)
    for pdf_id in ids[:2]:
        _registrar(
            rodada,
            pdf_id,
            _comparacao(pdf_id, [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1)]),
        )
    backlog = gerar_backlog(rodada, 1)["backlog"]
    resumo = {p["pdf_id"]: p for p in backlog["pdfs"]}
    assert resumo[ids[2]]["comparacao"] is None
    assert resumo[ids[2]]["fase"] == "renderizado"
    assert {"tipo": "sem_comparacao_vigente", "pdf_id": ids[2]} in [
        {k: a[k] for k in ("tipo", "pdf_id")} for a in backlog["alertas"]
    ]
    assert backlog["grupos"][0]["pdfs"] == ids[:2]
    assert backlog["totais"]["pdfs"] == 3 and backlog["totais"]["pdfs_com_comparacao"] == 2


def test_referencia_nao_auditada_e_sinalizada(rodada: Path) -> None:
    ids = _ids(rodada)
    _registrar(rodada, ids[0], _comparacao(ids[0], []), auditar=False)
    backlog = gerar_backlog(rodada, 1)["backlog"]
    assert backlog["pdfs"][0]["referencia_auditada"] is False
    assert any(
        a["tipo"] == "referencia_nao_auditada" and a["pdf_id"] == ids[0] for a in backlog["alertas"]
    )


def test_le_a_comparacao_do_marco_e_nao_a_de_maior_numero(rodada: Path) -> None:
    ids = _ids(rodada)
    _registrar(
        rodada, ids[0], _comparacao(ids[0], [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1)])
    )
    diagnostica = _comparacao(ids[0], [_div(LEGADO, "fp", F_TRAFO, "TRANSFORMADOR", n=9)])
    diagnostica["vigente"] = False
    (diretorio_pdf(rodada, ids[0]) / "comparacao-v002.json").write_text(
        json_canonico(diagnostica), encoding="utf-8"
    )
    backlog = gerar_backlog(rodada, 1)["backlog"]
    assert [g["method_id"] for g in backlog["grupos"]] == [TRAFOS]
    assert backlog["pdfs"][0]["comparacao"]["versao"] == "comparacao-v001.json"


def test_comparacao_adulterada_e_recusada_sem_gravar(rodada: Path) -> None:
    ids = _cenario_principal(rodada)
    arquivo = diretorio_pdf(rodada, ids[0]) / "comparacao-v001.json"
    arquivo.write_text(arquivo.read_text("utf-8").replace("TRANSFORMADOR", "OUTRO"), "utf-8")
    with pytest.raises(BacklogRecusadoError, match="difere do registrado"):
        gerar_backlog(rodada, 1)
    assert main(["--rodada", str(rodada), "--onda", "1"]) == 1
    assert not (rodada / "ondas").exists()


@pytest.mark.parametrize(
    ("campo", "valor", "mensagem"),
    [
        ("schema_version", "outro", "esquema"),
        ("vigente", False, "vigente"),
        ("pdf_id", "outro-pdf", "outro PDF"),
        ("divergencias", [{"id": "div-x"}], "divergência"),
    ],
)
def test_comparacao_invalida_e_recusada(campo: str, valor: Any, mensagem: str) -> None:
    comparacao = _comparacao("p1", [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1)])
    comparacao[campo] = valor
    with pytest.raises(BacklogRecusadoError, match=mensagem):
        agregar(1, [_entrada("p1", comparacao=comparacao)])


def test_divergencia_repetida_e_recusada() -> None:
    item = _div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1)
    with pytest.raises(BacklogRecusadoError, match="repetida"):
        agregar(1, [_entrada("p1", [item, dict(item)])])


def test_tile_fora_da_rodada_nao_vira_caminho_de_exemplo() -> None:
    entrada = _entrada(
        "p1",
        [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1)],
        tiles={TL: "../../fora/t.png"},
    )
    backlog = agregar(1, [entrada])
    (exemplo,) = backlog["grupos"][0]["exemplos"]
    assert exemplo["tile_evidencia"] == TL and exemplo["tile_arquivo"] is None
    assert any(a["tipo"] == "tile_sem_arquivo" for a in backlog["alertas"])


def test_formato_das_divergencias_do_comparador_e_aceito() -> None:
    observacao = {
        "id": "O1",
        "pagina": 1,
        "camada": "base",
        "bbox": [0.1, 0.1, 0.2, 0.2],
        "familia": F_TRAFO,
        "class_id": "TRANSFORMADOR",
        "tile_evidencia": TL,
    }
    contexto = _Contexto(
        escopo=cast(Any, None),
        observacoes={"O1": observacao},
        positivas=[],
        perdidas_pela_uniao=frozenset({"O1"}),
    )
    divergencia = _divergencia(
        contexto,
        tipo="fn",
        nivel="classe",
        conta_em="fn_ia",
        metodo=TRAFOS,
        observacao_id="O1",
        predicao=None,
        detalhe={"motivo": "sem_predicao", "classe_predita": None},
    )
    assert set(divergencia) == set(_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1))
    (grupo,) = agregar(1, [_entrada("p1", [divergencia])])["grupos"]
    assert grupo["perdidas_pela_uniao"] == 1
    assert grupo["exemplos"][0]["divergencia_id"] == divergencia["id"]


# --- lacunas de cobertura (classe sem método) --------------------------------------------------


def test_lacunas_de_cobertura_ficam_fora_dos_grupos_pistas_e_sem_dono() -> None:
    entradas = [
        _entrada(
            "p1",
            [
                _lacuna(F_CABO, CABO, n=1),
                _lacuna(F_CABO, CABO, n=2, tile=TR),
                *(_lacuna(F_POSTE, POSTE, n=n) for n in range(3, 7)),
                _div(ESTAIS, "fn", F_SEM_PACOTE, "ESTAI", n=7),
            ],
        ),
        _entrada("p2", [_lacuna(F_CABO, CABO, n=8, tile=BL)]),
    ]
    backlog = agregar(1, entradas)

    assert backlog["schema_version"] == ESQUEMA_BACKLOG == "curadoria-backlog-v2"
    # Só o método que suporta ESTAI vira grupo; nenhum grupo de método para CABO_AEREO/POSTE.
    assert [(g["method_id"], g["class_id"]) for g in backlog["grupos"]] == [(ESTAIS, "ESTAI")]
    lacunas = backlog["lacunas_de_cobertura"]
    # Prioridade: PDFs afetados primeiro (CABO 2 PDFs x 3 antes de POSTE 1 PDF x 4).
    assert [
        (item["familia"], item["class_id"], item["pdfs_afetados"], item["ocorrencias"])
        for item in lacunas
    ] == [(F_CABO, CABO, 2, 3), (F_POSTE, POSTE, 1, 4)]
    cabo, poste = lacunas
    assert (cabo["prioridade"], poste["prioridade"]) == (1, 2)
    assert cabo["pdfs"] == ["p1", "p2"] and cabo["ocorrencias_por_pdf"] == {"p1": 2, "p2": 1}
    assert cabo["id"].startswith("lac-") and cabo["id"] != poste["id"]
    assert [e["pdf_id"] for e in cabo["exemplos"]] == ["p1", "p2", "p1"]
    assert all(e["tile_arquivo"] for e in cabo["exemplos"])
    for lacuna in lacunas:
        assert "donos" not in lacuna and "pista" not in lacuna and "method_id" not in lacuna
    ids_lacunas = {item["id"] for item in lacunas}
    assert backlog["sem_dono"] == []
    assert all(not ids_lacunas & set(p["grupos"]) for p in backlog["pistas"])
    assert [p["arquivos"] for p in backlog["pistas"]] == [[f"{ANALISE}/pymupdf_guys.py"]]
    assert not [a for a in backlog["alertas"] if a["tipo"] == "metodo_sem_dono"]
    totais = backlog["totais"]
    assert totais["divergencias"] == 8
    assert totais["divergencias_agrupadas"] == 1
    assert totais["divergencias_em_lacunas"] == 7
    assert totais["divergencias_retidas"] == 0
    assert totais["lacunas_de_cobertura"] == 2
    resumo = {p["pdf_id"]: p for p in backlog["pdfs"]}
    assert resumo["p1"]["divergencias_em_lacunas"] == 6
    assert resumo["p2"]["divergencias_em_lacunas"] == 1
    texto = curation_backlog.renderizar_markdown(backlog)
    assert "## Lacunas de cobertura" in texto
    secao = texto[texto.index("## Lacunas de cobertura") : texto.index("## Exemplos")]
    assert secao.index(CABO) < secao.index(POSTE)
    assert "Lacunas de cobertura: 2" in texto


def test_lacuna_gerada_pelo_comparador_vai_para_lacunas_de_cobertura() -> None:
    observacao = {
        "id": "C2",
        "pagina": 1,
        "camada": "base",
        "bbox": [0.1, 0.8, 0.2, 0.9],
        "familia": F_CABO,
        "class_id": CABO,
        "tile_evidencia": BL,
    }
    contexto = _Contexto(
        escopo=cast(Any, None),
        observacoes={"C2": observacao},
        positivas=[],
        perdidas_pela_uniao=frozenset({"C2"}),
    )
    divergencia = _divergencia(
        contexto,
        tipo="fn",
        nivel="uniao",
        conta_em="fn_ia",
        metodo=METODO_UNIAO,
        observacao_id="C2",
        predicao=None,
        detalhe={"motivo": MOTIVO_SEM_METODO, "classe_predita": None},
        sem_metodo=True,
    )
    assert set(divergencia) == set(_lacuna(F_CABO, CABO, n=1))
    backlog = agregar(1, [_entrada("p1", [divergencia])])
    assert backlog["grupos"] == [] and backlog["pistas"] == []
    (lacuna,) = backlog["lacunas_de_cobertura"]
    assert (lacuna["familia"], lacuna["class_id"], lacuna["ocorrencias"]) == (F_CABO, CABO, 1)
    assert lacuna["exemplos"][0]["divergencia_id"] == divergencia["id"]


def test_alerta_de_metodo_sem_classes_suportadas_e_repassado() -> None:
    comparacao = _comparacao("p1", [_div(ESTAIS, "fn", F_SEM_PACOTE, "ESTAI", n=1)])
    comparacao["alertas"] = [{"tipo": ALERTA_SEM_CLASSES, "method_id": ESTAIS, "motivo": "ausente"}]
    backlog = agregar(1, [_entrada("p1", comparacao=comparacao)])
    assert {
        "tipo": ALERTA_SEM_CLASSES,
        "pdf_id": "p1",
        "method_id": ESTAIS,
        "motivo": "ausente",
    } in backlog["alertas"]
    assert [g["method_id"] for g in backlog["grupos"]] == [ESTAIS]


def test_comparacao_v1_e_recusada_com_orientacao() -> None:
    comparacao = _comparacao("p1", [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1)])
    comparacao["schema_version"] = "curadoria-comparacao-v1"
    with pytest.raises(BacklogRecusadoError, match="curation_compare"):
        agregar(1, [_entrada("p1", comparacao=comparacao)])


@pytest.mark.parametrize(
    "divergencia",
    [
        _div(METODO_UNIAO, "fn", F_CABO, CABO, n=1, nivel="uniao"),
        _div(ESTAIS, "fp", F_CABO, CABO, n=2, sem_metodo=True),
        _div(ESTAIS, "fn", F_CABO, CABO, n=3, sem_metodo=True),
    ],
)
def test_marca_sem_metodo_incoerente_e_recusada(divergencia: Registro) -> None:
    with pytest.raises(BacklogRecusadoError, match="sem_metodo"):
        agregar(1, [_entrada("p1", [divergencia])])


# --- gravação e CLI ----------------------------------------------------------------------------


def test_backlog_e_deterministico_e_sem_caminho_absoluto(rodada: Path) -> None:
    _cenario_principal(rodada)
    assert main(["--rodada", str(rodada), "--onda", "1"]) == 0
    pasta = rodada / "ondas" / "1"
    primeiro = {nome: (pasta / nome).read_bytes() for nome in ("backlog.json", "backlog.md")}
    assert main(["--rodada", str(rodada), "--onda", "1"]) == 0
    assert {nome: (pasta / nome).read_bytes() for nome in primeiro} == primeiro
    for conteudo in primeiro.values():
        texto = conteudo.decode("utf-8")
        assert str(rodada.parent) not in texto and rodada.parent.as_posix() not in texto
        assert "C:" not in texto and "Users" not in texto
    backlog = _ler_backlog(rodada)
    for pdf in backlog["pdfs"]:
        registrado = pdf["comparacao"]
        assert hash_arquivo(rodada / registrado["arquivo"]) == registrado["sha256"]
    assert sorted(item.name for item in pasta.iterdir()) == ["backlog.json", "backlog.md"]


def test_cli_imprime_resumo_e_alertas(rodada: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ids = _ids(rodada)
    _registrar(
        rodada, ids[0], _comparacao(ids[0], [_div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1)])
    )
    assert main(["--rodada", str(rodada), "--onda", "1"]) == 0
    saida = capsys.readouterr()
    resumo = json.loads(saida.out)
    assert resumo["arquivos"] == ["ondas/1/backlog.json", "ondas/1/backlog.md"]
    assert resumo["grupos"] == 1 and resumo["pistas"] == 1
    assert resumo["alertas"] == 2
    assert "alerta: sem_comparacao_vigente" in saida.err


def test_cli_recusa_onda_inexistente(rodada: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--rodada", str(rodada), "--onda", "9"]) == 1
    assert "onda inexistente" in capsys.readouterr().err
    assert not (rodada / "ondas").exists()


def test_markdown_lista_grupos_pistas_e_falhas() -> None:
    entradas = [
        _entrada(
            "p1",
            [
                _div(TRAFOS, "fn", F_TRAFO, "TRANSFORMADOR", n=1),
                _div(RASTER_T, "fn", F_TRAFO, "TRANSFORMADOR", n=2),
            ],
            status={RASTER_T: "falha"},
        )
    ]
    texto = curation_backlog.renderizar_markdown(agregar(1, entradas))
    for trecho in (
        "## Grupos",
        "## Pistas",
        "## Falhas de execução",
        "## Alertas",
        "pista-01",
        f"{ANALISE}/pymupdf_transformers.py",
        RASTER_T,
    ):
        assert trecho in texto


# --- auxiliares das entradas puras -------------------------------------------------------------


def _entrada(
    pdf_id: str,
    divergencias: Sequence[Registro] = (),
    *,
    status: dict[str, str] | None = None,
    comparacao: Registro | None = None,
    tiles: dict[str, str] | None = None,
) -> curation_backlog.EntradaPdf:
    dados = comparacao
    if dados is None:
        dados = _comparacao(pdf_id, divergencias, status=status)
    padrao = {tile: f"pdfs/{pdf_id}/render/{tile}.png" for tile in (TL, TR, BL)}
    return curation_backlog.EntradaPdf(
        pdf_id=pdf_id,
        fase="auditado",
        auditado=True,
        comparacao=dados,
        arquivo=f"pdfs/{pdf_id}/comparacao-v001.json",
        sha256="0" * 64,
        tiles=padrao if tiles is None else tiles,
    )
