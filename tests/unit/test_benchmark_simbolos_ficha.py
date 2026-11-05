# mypy: disable-error-code="no-untyped-call"
"""Benchmark de símbolos contra as fichas: casamento, classificação de FP, falhas e processos."""

from __future__ import annotations

import builtins
import hashlib
import json
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any, Literal

import pymupdf
import pytest
import scripts.benchmark_simbolos_ficha as bench
import scripts.symbol_benchmark_runner as runner
from scripts.curation_round import RodadaError
from scripts.ficha_poste import validar_ficha

import zeny_project_handler.adapters.analysis.pymupdf_guys as pymupdf_guys

Dados = dict[str, Any]

# Aterramento do detector legado em página 500x400: bbox normalizada do símbolo desenhado.
BBOX_ATERRAMENTO = [0.11, 0.1375, 0.146, 0.1625]
ID_COM_DESENHO = "001-aaaaaaaaaaaa"
ID_SEM_DESENHO = "002-bbbbbbbbbbbb"


# --- construtores de fixture ------------------------------------------------------------


def _desenhar_aterramento(page: pymupdf.Page) -> None:
    page.draw_line((50, 60), (65, 60), color=(0, 0, 0))
    for indice, comprimento in enumerate((10, 7, 4)):
        x = 65 + indice * 4
        page.draw_line((x, 60 - comprimento / 2), (x, 60 + comprimento / 2), color=(0, 0, 0))


def _pdf(caminho: Path, *, com_aterramento: bool) -> str:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=500, height=400)
        if com_aterramento:
            _desenhar_aterramento(pagina)
        else:
            pagina.draw_line((200, 200), (300, 200), color=(0, 0, 0))
        documento.save(caminho)
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _simbolo(identidade: str, classe: str, bbox: Sequence[float]) -> Dados:
    return {"id": identidade, "classe": classe, "bbox": list(bbox)}


def _poste(
    identidade: str,
    bbox: Sequence[float],
    simbolos: Sequence[Dados] = (),
    pendentes: Sequence[str] = (),
) -> Dados:
    return {
        "id": identidade,
        "pagina": 1,
        "bbox": list(bbox),
        "identificador": None,
        "estruturas": [],
        "poste": None,
        "coordenada": None,
        "simbolos": list(simbolos),
        "pendentes": list(pendentes),
    }


def _ficha(
    postes: Sequence[Dados],
    sha: str = "0" * 64,
    regioes: Sequence[Sequence[float]] | None = None,
) -> Dados:
    escopo: Dados = {"tipo": "completo"}
    if regioes is not None:
        escopo = {
            "tipo": "regional",
            "regioes": [{"pagina": 1, "bbox": list(regiao)} for regiao in regioes],
        }
    ficha = {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": sha,
        "escopo_anotacao": escopo,
        "postes": list(postes),
        "vaos": [],
    }
    assert validar_ficha(ficha) == []
    return ficha


def _predicao(
    classe: str, bbox: Sequence[float], contexto: str = "operational", pagina: int = 1
) -> Dados:
    return {
        "pagina": pagina,
        "classe": classe,
        "bbox": list(bbox),
        "metodo": "teste",
        "contexto": contexto,
    }


def _em(centro: tuple[float, float], meia: float = 0.01) -> list[float]:
    x, y = centro
    return [x - meia, y - meia, x + meia, y + meia]


def _escrever_rodada(
    raiz: Path, folhas: Sequence[tuple[str, str, Dados | None]], caminho_relativo: str | None = None
) -> Path:
    """Rodada sintética em ``raiz/rodada``; ``(pdf_id, nome do pdf, ficha)`` por folha."""
    rodada = raiz / "rodada"
    rodada.mkdir(parents=True)
    pdfs = []
    for pdf_id, nome, ficha in folhas:
        pdfs.append({"pdf_id": pdf_id, "caminho_relativo": caminho_relativo or nome})
        if ficha is not None:
            pasta = rodada / "pdfs" / pdf_id / "ficha"
            pasta.mkdir(parents=True)
            (pasta / "referencia.json").write_text(json.dumps(ficha), encoding="utf-8")
    manifesto = {
        "schema_version": "curadoria-rodada-v1",
        "raiz_corpus": "../corpus",
        "pdfs": pdfs,
    }
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return rodada


@pytest.fixture
def rodada_sintetica(tmp_path: Path) -> Path:
    """Duas folhas: uma com aterramento desenhado e outra sem desenho algum."""
    corpus = tmp_path / "corpus"
    com = _pdf(corpus / "folha-com-desenho.pdf", com_aterramento=True)
    sem = _pdf(corpus / "folha-sem-desenho.pdf", com_aterramento=False)
    ficha_com = _ficha(
        [_poste("P1", _em((0.128, 0.15)), [_simbolo("S1", "ATERRAMENTO", BBOX_ATERRAMENTO)])], com
    )
    ficha_sem = _ficha(
        [_poste("P1", _em((0.7, 0.7)), [_simbolo("S1", "ATERRAMENTO", _em((0.7, 0.7), 0.02))])],
        sem,
    )
    return _escrever_rodada(
        tmp_path,
        [
            (ID_COM_DESENHO, "folha-com-desenho.pdf", ficha_com),
            (ID_SEM_DESENHO, "folha-sem-desenho.pdf", ficha_sem),
        ],
    )


def _sem_tempo(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {chave: _sem_tempo(item) for chave, item in valor.items() if chave != "tempo_s"}
    if isinstance(valor, list):
        return [_sem_tempo(item) for item in valor]
    return valor


def _rodar(rodada: Path, saida: Path, **opcoes: Any) -> Dados:
    return bench.medir_simbolos(rodada, saida, **opcoes)


# --- casar ------------------------------------------------------------------------------


def test_casar_por_centro_e_um_para_um() -> None:
    referencias = [
        {"pagina": 1, "classe": "A", "bbox": [0.1, 0.1, 0.2, 0.2]},
        {"pagina": 1, "classe": "A", "bbox": [0.6, 0.6, 0.7, 0.7]},
    ]
    predicoes = [
        _predicao("A", _em((0.62, 0.62), 0.001)),
        _predicao("A", _em((0.151, 0.15), 0.001)),
        _predicao("A", _em((0.65, 0.65), 0.001)),
    ]

    pares = bench.casar(referencias, predicoes, "centro")

    # A mais próxima do centro vence, não a primeira da lista; a predição 0 sobra.
    assert pares == [(0, 1), (1, 2)]
    assert len({pred for _, pred in pares}) == len(pares)


def test_casar_empate_de_distancia_fica_com_a_referencia_de_menor_indice() -> None:
    referencias = [
        {"pagina": 1, "classe": "A", "bbox": [0.1, 0.1, 0.3, 0.2]},
        {"pagina": 1, "classe": "A", "bbox": [0.2, 0.1, 0.4, 0.2]},
    ]
    predicoes = [_predicao("A", _em((0.25, 0.15), 0.001))]

    assert bench.casar(referencias, predicoes, "centro") == [(0, 0)]


def test_casar_respeita_a_tolerancia_pagina_e_classe() -> None:
    ref = {"pagina": 1, "classe": "A", "bbox": [0.1, 0.1, 0.2, 0.2]}
    dentro = _predicao("A", _em((0.2 + bench.TOLERANCIA_CENTRO * 0.8, 0.15), 0.0))
    fora = _predicao("A", _em((0.2 + bench.TOLERANCIA_CENTRO * 1.2, 0.15), 0.0))

    assert bench.casar([ref], [dentro], "centro") == [(0, 0)]
    assert bench.casar([ref], [fora], "centro") == []
    assert bench.casar([ref], [_predicao("B", _em((0.15, 0.15)))], "centro") == []
    assert bench.casar([ref], [_predicao("A", _em((0.15, 0.15)), pagina=2)], "centro") == []


def test_casar_iou_nao_casa_polilinha_fina_que_centro_casa() -> None:
    ref = {"pagina": 1, "classe": "ESTAI", "bbox": [0.4, 0.4, 0.5, 0.5]}
    fina = _predicao("ESTAI", [0.45, 0.4, 0.45, 0.5])

    assert bench.casar([ref], [fina], "centro") == [(0, 0)]
    assert bench.casar([ref], [fina], "iou") == []


def test_casar_bbox_de_area_zero_nao_quebra() -> None:
    ponto_ref = {"pagina": 1, "classe": "A", "bbox": [0.4, 0.4, 0.4, 0.4]}
    ponto_pred = _predicao("A", [0.4, 0.4, 0.4, 0.4])
    ref = {"pagina": 1, "classe": "A", "bbox": [0.4, 0.4, 0.5, 0.5]}

    criterios: tuple[Literal["centro", "iou"], ...] = ("centro", "iou")
    for criterio in criterios:
        assert isinstance(bench.casar([ponto_ref], [ponto_pred], criterio), list)
        assert isinstance(bench.casar([ref], [ponto_pred], criterio), list)
    assert bench.casar([ponto_ref], [ponto_pred], "centro") == [(0, 0)]


def test_casar_iou_casa_caixas_sobrepostas() -> None:
    ref = {"pagina": 1, "classe": "A", "bbox": [0.1, 0.1, 0.2, 0.2]}

    assert bench.casar([ref], [_predicao("A", [0.1, 0.1, 0.2, 0.2])], "iou") == [(0, 0)]


# --- avaliar_predicoes ------------------------------------------------------------------


def _avaliar(ficha: Dados, predicoes: Sequence[Dados], classes: Sequence[str]) -> Dados:
    return bench.avaliar_predicoes(ficha, predicoes, frozenset(classes))


def test_classe_fora_do_escopo_nao_e_fp() -> None:
    ficha = _ficha([_poste("P1", _em((0.5, 0.5)), [_simbolo("S", "ATERRAMENTO", _em((0.5, 0.5)))])])
    predicoes = [_predicao("ESTAI", _em((0.2, 0.2))), _predicao("ATERRAMENTO", _em((0.8, 0.8)))]

    bloco = _avaliar(ficha, predicoes, ["ATERRAMENTO"])["centro"]

    assert bloco["fora_do_escopo"] == {"ESTAI": 1}
    assert "ESTAI" not in bloco["por_classe"]
    # Negativo: a classe avaliada, longe de tudo, continua sendo FP.
    assert bloco["por_classe"]["ATERRAMENTO"] == {
        "tp": 0,
        "fp": 1,
        "fn": 1,
        "precisao": 0.0,
        "recall": 0.0,
    }


def test_predicao_fora_das_regioes_nao_e_fp() -> None:
    ficha = _ficha(
        [_poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))])],
        regioes=[[0.0, 0.0, 0.5, 0.5]],
    )
    fora = _predicao("ATERRAMENTO", _em((0.8, 0.8)))
    dentro = _predicao("ATERRAMENTO", _em((0.4, 0.4)))

    bloco_fora = _avaliar(ficha, [fora], ["ATERRAMENTO"])["centro"]
    bloco_dentro = _avaliar(ficha, [dentro], ["ATERRAMENTO"])["centro"]

    assert bloco_fora["fora_das_regioes"] == 1
    assert bloco_fora["por_classe"]["ATERRAMENTO"]["fp"] == 0
    assert bloco_dentro["fora_das_regioes"] == 0
    assert bloco_dentro["por_classe"]["ATERRAMENTO"]["fp"] == 1


def test_escopo_completo_nao_tem_fora_das_regioes() -> None:
    ficha = _ficha([_poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))])])

    bloco = _avaliar(ficha, [_predicao("ATERRAMENTO", _em((0.9, 0.9)))], ["ATERRAMENTO"])["centro"]

    assert bloco["fora_das_regioes"] == 0
    assert bloco["por_classe"]["ATERRAMENTO"]["fp"] == 1


def test_predicao_perto_de_poste_pendente_nao_e_fp() -> None:
    ficha = _ficha(
        [
            _poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))]),
            _poste("P2", [0.7, 0.7, 0.71, 0.71], pendentes=["simbolos"]),
        ]
    )
    perto = _predicao("ATERRAMENTO", _em((0.7 + 0.03, 0.7), 0.0))
    longe = _predicao("ATERRAMENTO", _em((0.7 + 0.2, 0.7), 0.0))

    bloco = _avaliar(ficha, [perto, longe], ["ATERRAMENTO"])["centro"]

    assert bloco["perto_de_poste_pendente"] == 1
    assert bloco["por_classe"]["ATERRAMENTO"]["fp"] == 1


def test_contexto_de_legenda_nao_e_fp() -> None:
    ficha = _ficha([_poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))])])
    predicoes = [
        _predicao("ATERRAMENTO", _em((0.8, 0.8)), contexto="legend"),
        _predicao("ATERRAMENTO", _em((0.6, 0.6)), contexto="informative"),
        _predicao("ATERRAMENTO", _em((0.9, 0.1)), contexto="operational"),
    ]

    resultado = _avaliar(ficha, predicoes, ["ATERRAMENTO"])

    assert resultado["contexto_nao_desenho"] == 2
    assert resultado["centro"]["por_classe"]["ATERRAMENTO"]["fp"] == 1


def test_referencia_fora_da_regiao_casada_conta_tp() -> None:
    # O poste está na região; o símbolo (e a predição que o acerta) está fora dela.
    ficha = _ficha(
        [_poste("P1", _em((0.4, 0.4)), [_simbolo("S", "ATERRAMENTO", _em((0.7, 0.7), 0.02))])],
        regioes=[[0.0, 0.0, 0.5, 0.5]],
    )

    bloco = _avaliar(ficha, [_predicao("ATERRAMENTO", _em((0.7, 0.7), 0.02))], ["ATERRAMENTO"])[
        "centro"
    ]

    assert bloco["por_classe"]["ATERRAMENTO"]["tp"] == 1
    assert bloco["fora_das_regioes"] == 0


def test_poste_pendente_nao_engole_tp_do_vizinho() -> None:
    ficha = _ficha(
        [
            _poste("P1", _em((0.5, 0.5)), [_simbolo("S", "ATERRAMENTO", _em((0.5, 0.5), 0.02))]),
            _poste("P2", _em((0.53, 0.5), 0.0), pendentes=["simbolos"]),
        ]
    )

    bloco = _avaliar(ficha, [_predicao("ATERRAMENTO", _em((0.5, 0.5), 0.02))], ["ATERRAMENTO"])[
        "centro"
    ]

    assert bloco["por_classe"]["ATERRAMENTO"]["tp"] == 1
    assert bloco["perto_de_poste_pendente"] == 0


def test_simbolo_de_poste_pendente_sai_do_denominador() -> None:
    ficha = _ficha(
        [
            _poste(
                "P1", _em((0.5, 0.5)), [_simbolo("S", "ATERRAMENTO", _em((0.5, 0.5)))], ["simbolos"]
            )
        ]
    )

    bloco = _avaliar(ficha, [], ["ATERRAMENTO"])["centro"]

    assert bloco["por_classe"].get("ATERRAMENTO", {"fn": 0})["fn"] == 0
    assert bloco["geral"] == {"tp": 0, "fp": 0, "fn": 0, "precisao": None, "recall": None}


def test_duplicatas_contam_predicoes_da_mesma_classe_uma_dentro_da_outra() -> None:
    ficha = _ficha([_poste("P1", _em((0.5, 0.5)), [_simbolo("S", "ATERRAMENTO", _em((0.5, 0.5)))])])
    predicoes = [
        _predicao("ATERRAMENTO", _em((0.5, 0.5), 0.02)),
        _predicao("ATERRAMENTO", _em((0.505, 0.5), 0.02)),
        _predicao("ESTAI", _em((0.5, 0.5), 0.02)),
        _predicao("ATERRAMENTO", _em((0.9, 0.9), 0.02)),
    ]

    assert _avaliar(ficha, predicoes, ["ATERRAMENTO"])["duplicatas"] == {"ATERRAMENTO": 1}


# --- medir_simbolos ---------------------------------------------------------------------


def test_medir_simbolos_na_rodada_sintetica(rodada_sintetica: Path, tmp_path: Path) -> None:
    saida = tmp_path / "saida"

    relatorio = _rodar(rodada_sintetica, saida)

    assert relatorio["schema_version"] == bench.ESQUEMA
    assert "atual" in relatorio["opcoes"]["metodos_assinatura"]
    assert relatorio["opcoes"]["classes_avaliadas"] == ["ATERRAMENTO"]
    com = relatorio["por_pdf"][ID_COM_DESENHO]
    sem = relatorio["por_pdf"][ID_SEM_DESENHO]
    assert com["familia"] and sem["familia"]
    positivo = com["metodos"]["atual"]["centro"]["por_classe"]["ATERRAMENTO"]
    assert positivo["tp"] >= 1
    assert positivo["fn"] == 0
    assert com["metodos"]["atual"]["iou"]["por_classe"]["ATERRAMENTO"]["tp"] >= 1
    negativo = sem["metodos"]["atual"]["centro"]["por_classe"]["ATERRAMENTO"]
    assert negativo["fn"] == 1
    assert negativo["tp"] == 0
    total = relatorio["total"]["atual"]["centro"]["por_classe"]["ATERRAMENTO"]
    assert total["tp"] == positivo["tp"]
    assert total["fn"] == 1
    assert sum(len(bloco) for bloco in relatorio["por_familia"].values()) >= 1
    assert (saida / "simbolos-ficha.json").is_file()
    assert (saida / "simbolos-ficha.md").is_file()
    assert json.loads((saida / "simbolos-ficha.json").read_text(encoding="utf-8")) == relatorio
    assert relatorio["comparacao"]["metodos"]["atual"] == relatorio["total"]["atual"]


def test_markdown_declara_processos_e_limites(rodada_sintetica: Path, tmp_path: Path) -> None:
    saida = tmp_path / "saida"

    _rodar(rodada_sintetica, saida, processos=1)

    texto = (saida / "simbolos-ficha.md").read_text(encoding="utf-8")
    assert "Processos: 1 (efetivos: 1)" in texto
    assert "tracemalloc" in texto
    assert "limite inferior" in texto
    assert "reconcile_symbols" in texto


def test_falha_de_detector_tira_o_metodo_dos_totais(
    rodada_sintetica: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def quebrado(*_: Any, **__: Any) -> Any:
        raise RuntimeError(f"detector quebrou em {tmp_path / 'privado' / 'x.pdf'}")

    monkeypatch.setattr(pymupdf_guys, "observar_estais", quebrado)

    relatorio = _rodar(rodada_sintetica, tmp_path / "saida")

    for pdf_id in (ID_COM_DESENHO, ID_SEM_DESENHO):
        bloco = relatorio["por_pdf"][pdf_id]["metodos"]["atual"]
        assert bloco["situacao"] == "falha"
        assert bloco["erro"].startswith("RuntimeError: detector quebrou")
        assert "centro" not in bloco
    total = relatorio["total"]["atual"]
    assert total["folhas_medidas"] == 0
    assert total["folhas_com_falha"] == 2
    assert total["centro"]["por_classe"] == {}
    texto = (tmp_path / "saida" / "simbolos-ficha.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in texto
    assert tmp_path.as_posix() not in texto


def test_processos_2_igual_a_serial(rodada_sintetica: Path, tmp_path: Path) -> None:
    serial = _rodar(rodada_sintetica, tmp_path / "serial", processos=1)
    paralelo = _rodar(rodada_sintetica, tmp_path / "paralelo", processos=2)

    assert _sem_tempo(paralelo) == _sem_tempo(serial)
    carregado = json.loads((tmp_path / "paralelo" / "simbolos-ficha.json").read_text("utf-8"))
    assert _sem_tempo(carregado) == _sem_tempo(serial)
    assert list(paralelo["por_pdf"]) == [ID_COM_DESENHO, ID_SEM_DESENHO]
    assert "Processos: 2 (efetivos: 2)" in (tmp_path / "paralelo" / "simbolos-ficha.md").read_text(
        encoding="utf-8"
    )


def test_processos_limitado_pelo_numero_de_folhas(rodada_sintetica: Path, tmp_path: Path) -> None:
    _rodar(rodada_sintetica, tmp_path / "s", processos=16)

    texto = (tmp_path / "s" / "simbolos-ficha.md").read_text(encoding="utf-8")
    assert "Processos: 16 (efetivos: 2)" in texto


def test_pool_quebrado_vira_falha_e_grava_o_relatorio(
    rodada_sintetica: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PoolQuebrado:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def __enter__(self) -> PoolQuebrado:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def map(self, funcao: Callable[[Any], Any], itens: Sequence[Any]) -> Iterator[Any]:
            yield funcao(itens[0])
            raise BrokenProcessPool("morreu")

    monkeypatch.setattr(bench, "ProcessPoolExecutor", PoolQuebrado)

    relatorio = _rodar(rodada_sintetica, tmp_path / "saida", processos=2)

    assert relatorio["por_pdf"][ID_COM_DESENHO]["situacao"] == "ok"
    assert relatorio["por_pdf"][ID_SEM_DESENHO]["situacao"] == "falha"
    assert (tmp_path / "saida" / "simbolos-ficha.json").is_file()


def test_sha_diferente_e_falha_saneada(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _pdf(corpus / "a.pdf", com_aterramento=True)
    _pdf(corpus / "b.pdf", com_aterramento=False)
    sha_b = hashlib.sha256((corpus / "b.pdf").read_bytes()).hexdigest()
    ficha_errada = _ficha([_poste("P1", _em((0.5, 0.5)))], "f" * 64)
    ficha_boa = _ficha([_poste("P1", _em((0.5, 0.5)))], sha_b)
    rodada = _escrever_rodada(
        tmp_path,
        [(ID_COM_DESENHO, "a.pdf", ficha_errada), (ID_SEM_DESENHO, "b.pdf", ficha_boa)],
    )

    relatorio = _rodar(rodada, tmp_path / "saida")

    falha = relatorio["por_pdf"][ID_COM_DESENHO]
    assert falha["situacao"] == "falha"
    assert "sha256" in falha["erro"]
    assert relatorio["por_pdf"][ID_SEM_DESENHO]["situacao"] == "ok"
    texto = (tmp_path / "saida" / "simbolos-ficha.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in texto
    assert tmp_path.as_posix() not in texto


def test_pdf_ausente_e_folha_sem_referencia(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    ficha = _ficha([_poste("P1", _em((0.5, 0.5)))])
    rodada = _escrever_rodada(
        tmp_path,
        [(ID_COM_DESENHO, "nao-existe.pdf", ficha), (ID_SEM_DESENHO, "outra.pdf", None)],
    )

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_COM_DESENHO]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_SEM_DESENHO] == {"situacao": "sem_referencia"}
    assert str(tmp_path) not in json.dumps(relatorio)


def test_caminho_avaliacao_cega_e_recusado_sem_ler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cega = tmp_path / "corpus" / "avaliacao-cega"
    cega.mkdir(parents=True)
    sha = _pdf(cega / "x.pdf", com_aterramento=True)
    rodada = _escrever_rodada(
        tmp_path,
        [(ID_COM_DESENHO, "x.pdf", _ficha([_poste("P1", _em((0.5, 0.5)))], sha))],
        caminho_relativo="avaliacao-cega/x.pdf",
    )
    acessos: list[str] = []

    def vigiar(original: Callable[..., Any]) -> Callable[..., Any]:
        def interno(*args: Any, **kwargs: Any) -> Any:
            if any("avaliacao-cega" in str(item) for item in (*args, *kwargs.values())):
                acessos.append(str(args[:1]))
            return original(*args, **kwargs)

        return interno

    monkeypatch.setattr(Path, "read_bytes", vigiar(Path.read_bytes))
    monkeypatch.setattr(Path, "open", vigiar(Path.open))
    monkeypatch.setattr(builtins, "open", vigiar(builtins.open))
    monkeypatch.setattr(pymupdf, "open", vigiar(pymupdf.open))
    monkeypatch.setattr(runner, "infer_pdf", vigiar(runner.infer_pdf))

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_COM_DESENHO]["situacao"] == "falha"
    assert "avaliacao-cega" in relatorio["por_pdf"][ID_COM_DESENHO]["erro"]
    assert acessos == []


@pytest.mark.parametrize(
    "relativo", ["Avaliacao-Cega/x.pdf", "avaliacao-cega\\x.pdf", "pasta/../avaliacao-cega/x.pdf"]
)
def test_avaliacao_cega_recusada_em_variantes_de_caminho(tmp_path: Path, relativo: str) -> None:
    ficha = _ficha([_poste("P1", _em((0.5, 0.5)))])
    rodada = _escrever_rodada(
        tmp_path, [(ID_COM_DESENHO, "x.pdf", ficha)], caminho_relativo=relativo
    )

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_COM_DESENHO]["situacao"] == "falha"
    assert "avaliacao-cega" in relatorio["por_pdf"][ID_COM_DESENHO]["erro"]


def test_comparacao_usa_so_as_folhas_em_que_todos_os_metodos_tiveram_sucesso(
    rodada_sintetica: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def outro(pdf: Path, pdf_id: str) -> Dados:
        if pdf_id == ID_SEM_DESENHO:
            return {"predicoes": [], "assinatura": {}, "falha": "RuntimeError: quebrou"}
        return {"predicoes": [], "assinatura": {}, "falha": None}

    monkeypatch.setitem(bench.METODOS, "outro", outro)
    monkeypatch.setitem(
        bench.ASSINATURAS, "outro", lambda: {"metodo_id": "outro", "versao": "t", "observacao": ""}
    )

    relatorio = _rodar(rodada_sintetica, tmp_path / "saida", metodos=("atual", "outro"))

    comparacao = relatorio["comparacao"]
    assert comparacao["folhas"] == [ID_COM_DESENHO]
    assert comparacao["metodos"]["atual"]["folhas_medidas"] == 1
    assert comparacao["metodos"]["atual"]["centro"]["por_classe"]["ATERRAMENTO"]["fn"] == 0
    assert relatorio["total"]["atual"]["folhas_medidas"] == 2
    assert relatorio["total"]["outro"]["folhas_medidas"] == 1


# --- CLI e saneamento -------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["0", "-1", "x"])
def test_cli_processos_invalido(valor: str, tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as erro:
        bench.main(["--rodada", str(tmp_path), "--saida", str(tmp_path), "--processos", valor])

    assert erro.value.code == 2


def test_cli_roda_na_rodada_sintetica(rodada_sintetica: Path, tmp_path: Path) -> None:
    saida = tmp_path / "saida"

    codigo = bench.main(
        ["--rodada", str(rodada_sintetica), "--saida", str(saida), "--metodo", "atual"]
    )

    assert codigo == 0
    assert (saida / "simbolos-ficha.json").is_file()


def test_relatorio_sem_caminho_absoluto_nem_nome_de_pdf(
    rodada_sintetica: Path, tmp_path: Path
) -> None:
    saida = tmp_path / "saida"

    _rodar(rodada_sintetica, saida)

    for nome in ("simbolos-ficha.json", "simbolos-ficha.md"):
        texto = (saida / nome).read_text(encoding="utf-8")
        assert str(tmp_path) not in texto
        assert tmp_path.as_posix() not in texto
        assert "folha-com-desenho" not in texto
        assert "folha-sem-desenho" not in texto
        assert ID_COM_DESENHO in texto


def test_tempo_s_so_aparece_em_por_pdf(rodada_sintetica: Path, tmp_path: Path) -> None:
    relatorio = _rodar(rodada_sintetica, tmp_path / "saida")

    assert "tempo_s" in relatorio["por_pdf"][ID_COM_DESENHO]["metodos"]["atual"]
    sem_por_pdf = {chave: valor for chave, valor in relatorio.items() if chave != "por_pdf"}
    assert "tempo_s" not in json.dumps(sem_por_pdf)


def test_sanear_remove_caminhos_e_fica_na_primeira_linha() -> None:
    erro = bench.sanear(
        "OSError: falhou em C:\\Users\\x\\y\\folha 1.pdf e /home/u/a/b.pdf\nlinha 2"
    )

    assert "\n" not in erro
    assert "Users" not in erro
    assert "home" not in erro
    assert ".pdf" not in erro
    assert erro.startswith("OSError: falhou em")


@pytest.mark.parametrize(
    "bruto",
    [
        "falhou em \\\\servidor\\projetos\\rede\\folha 12.bin ao abrir",
        "falhou em \\\\?\\C:\\projetos\\rede\\folha 12.bin ao abrir",
        "falhou em \\\\servidor ao abrir",
    ],
)
def test_sanear_remove_caminho_de_rede_e_prefixo_estendido(bruto: str) -> None:
    erro = bench.sanear(bruto)

    for vazado in ("servidor", "projetos", "rede", "folha", "C:", "\\\\"):
        assert vazado not in erro
    assert erro.startswith("falhou em")
    assert erro.endswith("ao abrir")


def test_sanear_oculta_o_caminho_conhecido_em_qualquer_caixa() -> None:
    erro = bench.sanear(
        "falha em C:\\Pasta X\\Rua Tal 12.PDF aqui", ["c:\\pasta x\\rua tal 12.pdf"]
    )

    assert "Rua" not in erro
    assert "Pasta" not in erro


@pytest.mark.parametrize(
    "parte",
    [
        "avaliacao-cega.",
        "AVALIACAO-CEGA..",
        "avaliacao-cega ",
        "avaliacao-cega. .",
        "avaliacao-cega:$I30",
    ],
)
def test_componente_equivalente_no_windows_vira_avaliacao_cega(parte: str) -> None:
    assert bench.COMPONENTE_CEGO in bench._componentes(f"x/{parte}/y.pdf")


def test_componente_parecido_mas_diferente_nao_vira_avaliacao_cega() -> None:
    assert bench.COMPONENTE_CEGO not in bench._componentes("x/avaliacao-cega-2/a.cega/y.pdf")


# --- rodada dentro de avaliacao-cega ----------------------------------------------------


def _rodada_em(base: Path, raiz_corpus: str, caminho_relativo: str, sha: str) -> Path:
    """Rodada em ``base/r`` com uma folha e a ficha dela."""
    rodada = base / "r"
    pasta = rodada / "pdfs" / ID_COM_DESENHO / "ficha"
    pasta.mkdir(parents=True)
    ficha = _ficha([_poste("P1", _em((0.128, 0.15)))], sha)
    (pasta / "referencia.json").write_text(json.dumps(ficha), encoding="utf-8")
    manifesto = {
        "schema_version": "curadoria-rodada-v1",
        "raiz_corpus": raiz_corpus,
        "pdfs": [{"pdf_id": ID_COM_DESENHO, "caminho_relativo": caminho_relativo}],
    }
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return rodada


def _vigiar_pasta_cega(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Registra todo acesso, a arquivo ou ao PyMuPDF, cujo argumento cite ``avaliacao-cega``."""
    acessos: list[str] = []

    def vigiar(original: Callable[..., Any]) -> Callable[..., Any]:
        def interno(*args: Any, **kwargs: Any) -> Any:
            if any("avaliacao-cega" in str(item).casefold() for item in (*args, *kwargs.values())):
                acessos.append(str(getattr(original, "__name__", original)))
            return original(*args, **kwargs)

        return interno

    for nome in ("is_file", "exists", "stat", "read_bytes", "read_text", "open", "resolve"):
        monkeypatch.setattr(Path, nome, vigiar(getattr(Path, nome)))
    monkeypatch.setattr(builtins, "open", vigiar(builtins.open))
    monkeypatch.setattr(pymupdf, "open", vigiar(pymupdf.open))
    monkeypatch.setattr(runner, "infer_pdf", vigiar(runner.infer_pdf))
    return acessos


@pytest.mark.parametrize("raiz_corpus", ["..", "."])
def test_rodada_dentro_de_avaliacao_cega_e_recusada_sem_ler_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raiz_corpus: str
) -> None:
    base = tmp_path / "avaliacao-cega"
    pdf = base if raiz_corpus == ".." else base / "r"
    sha = _pdf(pdf / "x.pdf", com_aterramento=True)
    rodada = _rodada_em(base, raiz_corpus, "x.pdf", sha)
    acessos = _vigiar_pasta_cega(monkeypatch)
    saida = tmp_path / "saida"

    with pytest.raises(RodadaError, match="avaliacao-cega"):
        _rodar(rodada, saida)

    assert acessos == []
    assert not saida.exists()


def test_cli_com_rodada_dentro_de_avaliacao_cega_sai_com_erro_sem_relatorio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "Avaliacao-Cega"
    rodada = _rodada_em(base, "..", "x.pdf", _pdf(base / "x.pdf", com_aterramento=True))
    acessos = _vigiar_pasta_cega(monkeypatch)
    saida = tmp_path / "saida"

    with pytest.raises(SystemExit) as erro:
        bench.main(["--rodada", str(rodada), "--saida", str(saida)])

    assert erro.value.code not in (0, None)
    assert acessos == []
    assert not saida.exists()


def test_rodada_fora_com_raiz_do_corpus_dentro_de_avaliacao_cega_e_falha_da_folha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = _pdf(tmp_path / "avaliacao-cega" / "x.pdf", com_aterramento=True)
    rodada = _rodada_em(tmp_path / "fora", "../../avaliacao-cega", "x.pdf", sha)
    acessos = _vigiar_pasta_cega(monkeypatch)

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_COM_DESENHO]["situacao"] == "falha"
    assert "avaliacao-cega" in relatorio["por_pdf"][ID_COM_DESENHO]["erro"]
    assert acessos == []


def test_rodada_fora_com_corpus_comum_continua_medindo(tmp_path: Path) -> None:
    sha = _pdf(tmp_path / "corpus" / "x.pdf", com_aterramento=True)
    rodada = _rodada_em(tmp_path / "fora", "../../corpus", "x.pdf", sha)

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_COM_DESENHO]["situacao"] == "ok"


def test_localizar_pdf_confere_tambem_o_caminho_da_rodada() -> None:
    rodada = Path("exemplos") / "avaliacao-cega" / "r"

    with pytest.raises(bench._FolhaError, match="avaliacao-cega"):
        bench.localizar_pdf(rodada, "..", "x.pdf")
    assert bench.localizar_pdf(Path("exemplos") / "r", "../corpus", "x.pdf").name == "x.pdf"
