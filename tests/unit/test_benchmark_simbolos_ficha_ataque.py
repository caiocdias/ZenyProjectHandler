# mypy: disable-error-code="no-untyped-call"
"""Ataque ao benchmark de símbolos contra as fichas (E06.1, Task 1).

Cobre o que a suíte do desenvolvedor não cobre: ordem de classificação da R-E06.1-3, empates e
bordas do casamento 1-1, comparação entre métodos com falha parcial, paridade serial/paralelo,
recusa de ``avaliacao-cega`` antes de qualquer I/O, vazamento de caminho no relatório e CLI.
"""

from __future__ import annotations

import builtins
import hashlib
import importlib
import json
import math
import os
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any, ClassVar, Literal

import pymupdf
import pytest
import scripts.benchmark_simbolos_ficha as bench
import scripts.symbol_benchmark_runner as runner
from scripts.ficha_poste import validar_ficha

Dados = dict[str, Any]
Criterio = Literal["centro", "iou"]

BBOX_ATERRAMENTO = [0.11, 0.1375, 0.146, 0.1625]
ID_A = "001-aaaaaaaaaaaa"
ID_B = "002-bbbbbbbbbbbb"
ID_C = "003-cccccccccccc"
ID_D = "004-dddddddddddd"
ID_E = "005-eeeeeeeeeeee"


# --- construtores de fixture ------------------------------------------------------------


def _pdf(caminho: Path, *, com_aterramento: bool) -> str:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=500, height=400)
        if com_aterramento:
            pagina.draw_line((50, 60), (65, 60), color=(0, 0, 0))
            for indice, comprimento in enumerate((10, 7, 4)):
                x = 65 + indice * 4
                pagina.draw_line((x, 60 - comprimento / 2), (x, 60 + comprimento / 2))
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
    pagina: int = 1,
) -> Dados:
    return {
        "id": identidade,
        "pagina": pagina,
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
    regioes: Sequence[tuple[int, Sequence[float]]] | None = None,
) -> Dados:
    escopo: Dados = {"tipo": "completo"}
    if regioes is not None:
        escopo = {
            "tipo": "regional",
            "regioes": [{"pagina": pagina, "bbox": list(bbox)} for pagina, bbox in regioes],
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


def _ref(classe: str, bbox: Sequence[float], pagina: int = 1) -> Dados:
    return {"pagina": pagina, "classe": classe, "bbox": list(bbox)}


def _ficha_aterramento(sha: str) -> Dados:
    return _ficha(
        [_poste("P1", _em((0.128, 0.15)), [_simbolo("S1", "ATERRAMENTO", BBOX_ATERRAMENTO)])], sha
    )


def _ficha_sem_desenho(sha: str) -> Dados:
    return _ficha(
        [_poste("P1", _em((0.7, 0.7)), [_simbolo("S1", "ATERRAMENTO", _em((0.7, 0.7), 0.02))])],
        sha,
    )


def _escrever_rodada(
    raiz: Path,
    folhas: Sequence[tuple[str, str, Dados | str | None]],
    raiz_corpus: str = "../corpus",
) -> Path:
    """Rodada em ``raiz/rodada``; ``(pdf_id, caminho_relativo, ficha | texto bruto | None)``."""
    rodada = raiz / "rodada"
    rodada.mkdir(parents=True, exist_ok=True)
    pdfs = []
    for pdf_id, relativo, ficha in folhas:
        pdfs.append({"pdf_id": pdf_id, "caminho_relativo": relativo})
        if ficha is not None and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", pdf_id):
            pasta = rodada / "pdfs" / pdf_id / "ficha"
            pasta.mkdir(parents=True, exist_ok=True)
            texto = ficha if isinstance(ficha, str) else json.dumps(ficha)
            (pasta / "referencia.json").write_text(texto, encoding="utf-8")
    manifesto = {"schema_version": "curadoria-rodada-v1", "raiz_corpus": raiz_corpus, "pdfs": pdfs}
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return rodada


def _sem_tempo(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {chave: _sem_tempo(item) for chave, item in valor.items() if chave != "tempo_s"}
    if isinstance(valor, list):
        return [_sem_tempo(item) for item in valor]
    return valor


def _rodar(rodada: Path, saida: Path, **opcoes: Any) -> Dados:
    return bench.medir_simbolos(rodada, saida, **opcoes)


def _textos(saida: Path) -> str:
    return "\n".join(
        (saida / nome).read_text(encoding="utf-8")
        for nome in ("simbolos-ficha.json", "simbolos-ficha.md")
    )


def _avaliar(ficha: Dados, predicoes: Sequence[Dados], classes: Sequence[str]) -> Dados:
    return bench.avaliar_predicoes(ficha, predicoes, frozenset(classes))


@pytest.fixture
def rodada_tres_folhas(tmp_path: Path) -> Path:
    """A e C com aterramento desenhado; B com uma referência que nenhum desenho cobre."""
    corpus = tmp_path / "corpus"
    sha_a = _pdf(corpus / "a.pdf", com_aterramento=True)
    sha_b = _pdf(corpus / "b.pdf", com_aterramento=False)
    sha_c = _pdf(corpus / "c.pdf", com_aterramento=True)
    return _escrever_rodada(
        tmp_path,
        [
            (ID_A, "a.pdf", _ficha_aterramento(sha_a)),
            (ID_B, "b.pdf", _ficha_sem_desenho(sha_b)),
            (ID_C, "c.pdf", _ficha_aterramento(sha_c)),
        ],
    )


def test_constantes_do_contrato_seguem_o_plano() -> None:
    assert bench.TOLERANCIA_CENTRO == 0.005
    assert bench.RAIO_POSTE_PENDENTE == 0.05
    assert bench.ESQUEMA == "simbolos-ficha-v1"
    assert set(bench.METODOS) == {"atual", "pacotes", "modelo"}


# --- casar: empates, ordem e bordas -----------------------------------------------------


@pytest.mark.parametrize("criterio", ["centro", "iou"])
def test_casar_empate_exato_de_distancia_pareia_por_indice(criterio: Criterio) -> None:
    caixa = [0.25, 0.25, 0.5, 0.5]
    referencias = [_ref("ATERRAMENTO", caixa), _ref("ATERRAMENTO", caixa)]
    predicoes = [_predicao("ATERRAMENTO", caixa), _predicao("ATERRAMENTO", caixa)]

    assert bench.casar(referencias, predicoes, criterio) == [(0, 0), (1, 1)]


def test_casar_empate_de_distancia_entre_predicoes_fica_com_a_de_menor_indice() -> None:
    referencias = [_ref("ATERRAMENTO", [0.25, 0.25, 0.5, 0.5])]
    # Duas predições à mesma distância (0,0625) do centro (0,375); a de índice 0 vence.
    predicoes = [
        _predicao("ATERRAMENTO", _em((0.4375, 0.375), 0.0)),
        _predicao("ATERRAMENTO", _em((0.3125, 0.375), 0.0)),
    ]

    assert bench.casar(referencias, predicoes, "centro") == [(0, 0)]
    assert bench.casar(referencias, predicoes[::-1], "centro") == [(0, 0)]


def test_casar_nao_depende_da_ordem_das_predicoes_quando_nao_ha_empate() -> None:
    referencias = [
        _ref("ATERRAMENTO", [0.10, 0.1, 0.20, 0.2]),
        _ref("ATERRAMENTO", [0.19, 0.1, 0.30, 0.2]),
        _ref("ATERRAMENTO", [0.29, 0.1, 0.40, 0.2]),
    ]
    predicoes = [
        _predicao("ATERRAMENTO", _em((0.195, 0.15), 0.001)),
        _predicao("ATERRAMENTO", _em((0.12, 0.15), 0.001)),
        _predicao("ATERRAMENTO", _em((0.33, 0.15), 0.001)),
    ]
    esperado = {
        (i, tuple(predicoes[j]["bbox"])) for i, j in bench.casar(referencias, predicoes, "centro")
    }

    for ordem in ([2, 1, 0], [1, 2, 0], [0, 2, 1]):
        permutadas = [predicoes[k] for k in ordem]
        obtido = {
            (i, tuple(permutadas[j]["bbox"]))
            for i, j in bench.casar(referencias, permutadas, "centro")
        }
        assert obtido == esperado
    assert len(esperado) == 3


def test_casar_guloso_prefere_o_par_mais_proximo_mesmo_que_estrague_o_resto() -> None:
    # A predição 0 está dentro das duas referências, mas mais perto da 1; a 1 só cabe na 1.
    referencias = [
        _ref("ATERRAMENTO", [0.10, 0.1, 0.30, 0.2]),
        _ref("ATERRAMENTO", [0.20, 0.1, 0.40, 0.2]),
    ]
    predicoes = [
        _predicao("ATERRAMENTO", _em((0.27, 0.15), 0.0)),
        _predicao("ATERRAMENTO", _em((0.35, 0.15), 0.0)),
    ]

    # Pares: (0,0) dist 0,07; (1,0) dist 0,03; (1,1) dist 0,05. O guloso fecha (1,0) e deixa
    # a referência 0 sem par: o contrato é guloso, não máximo.
    assert bench.casar(referencias, predicoes, "centro") == [(1, 0)]


@pytest.mark.parametrize("criterio", ["centro", "iou"])
@pytest.mark.parametrize(
    "caixa",
    [
        pytest.param([-0.5, -0.5, 1.5, 1.5], id="maior-que-a-pagina"),
        pytest.param([1.2, 1.2, 1.4, 1.4], id="fora-da-pagina"),
        pytest.param([-0.4, -0.4, -0.2, -0.2], id="negativa"),
        pytest.param([0.6, 0.6, 0.4, 0.4], id="invertida"),
        pytest.param([0.5, 0.2, 0.5, 0.8], id="largura-zero"),
        pytest.param([0.2, 0.5, 0.8, 0.5], id="altura-zero"),
        pytest.param([math.nan, 0.0, 0.5, 0.5], id="nan"),
        pytest.param([0.0, 0.0, math.inf, 0.5], id="infinita"),
    ],
)
def test_casar_nao_levanta_com_bbox_degenerada_ou_fora_de_0_1(
    caixa: list[float], criterio: Criterio
) -> None:
    referencias = [_ref("ATERRAMENTO", [0.4, 0.4, 0.6, 0.6]), _ref("ATERRAMENTO", caixa)]
    predicoes = [
        _predicao("ATERRAMENTO", caixa),
        _predicao("ATERRAMENTO", [0.45, 0.45, 0.55, 0.55]),
    ]

    pares = bench.casar(referencias, predicoes, criterio)

    assert len({i for i, _ in pares}) == len(pares)
    assert len({j for _, j in pares}) == len(pares)
    assert all(0 <= i < 2 and 0 <= j < 2 for i, j in pares)


def test_avaliar_predicoes_aceita_bbox_fora_de_0_1_sem_quebrar_as_contagens() -> None:
    ficha = _ficha(
        [_poste("P1", _em((0.5, 0.5)), [_simbolo("S", "ATERRAMENTO", _em((0.5, 0.5), 0.05))])]
    )
    predicoes = [
        _predicao("ATERRAMENTO", [-0.5, -0.5, 1.5, 1.5]),
        _predicao("ATERRAMENTO", [1.2, 1.2, 1.4, 1.4]),
        _predicao("ATERRAMENTO", [math.nan, 0.0, 0.5, 0.5]),
    ]

    resultado = _avaliar(ficha, predicoes, ["ATERRAMENTO"])

    for criterio in ("centro", "iou"):
        classe = resultado[criterio]["por_classe"]["ATERRAMENTO"]
        assert classe["tp"] + classe["fn"] == 1
        assert classe["tp"] + classe["fp"] == 3
    assert resultado["centro"]["por_classe"]["ATERRAMENTO"]["tp"] == 1


# --- classificação do que sobra do casamento (R-E06.1-3, item 4) ------------------------


def _ficha_regional_com_poste_pendente() -> Dados:
    # Região [0, 0.5]x[0, 0.5]; poste pendente na borda direita da região.
    return _ficha(
        [
            _poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))]),
            _poste("P2", [0.49, 0.44, 0.5, 0.46], pendentes=["simbolos"]),
        ],
        regioes=[(1, [0.0, 0.0, 0.5, 0.5])],
    )


def test_fora_das_regioes_vem_antes_de_perto_de_poste_pendente() -> None:
    ficha = _ficha_regional_com_poste_pendente()
    # Centro fora da região (x > 0,5) e dentro do raio do poste pendente: conta uma vez só.
    fora_e_perto = _predicao("ATERRAMENTO", _em((0.52, 0.45), 0.0))

    bloco = _avaliar(ficha, [fora_e_perto], ["ATERRAMENTO"])["centro"]

    assert bloco["fora_das_regioes"] == 1
    assert bloco["perto_de_poste_pendente"] == 0
    assert bloco["por_classe"]["ATERRAMENTO"]["fp"] == 0


def test_perto_de_poste_pendente_dentro_da_regiao_nao_e_fora_das_regioes() -> None:
    ficha = _ficha_regional_com_poste_pendente()

    bloco = _avaliar(ficha, [_predicao("ATERRAMENTO", _em((0.47, 0.45), 0.0))], ["ATERRAMENTO"])[
        "centro"
    ]

    assert bloco["fora_das_regioes"] == 0
    assert bloco["perto_de_poste_pendente"] == 1
    assert bloco["por_classe"]["ATERRAMENTO"]["fp"] == 0


def test_casamento_vem_antes_de_fora_das_regioes_e_de_perto_de_poste_pendente() -> None:
    # A referência (poste P1, dentro da região) tem o símbolo fora da região e colado ao poste
    # pendente: a predição que a acerta é TP, não cai nem em fora_das_regioes nem em perto.
    ficha = _ficha(
        [
            _poste("P1", _em((0.4, 0.4)), [_simbolo("S", "ATERRAMENTO", _em((0.52, 0.45), 0.01))]),
            _poste("P2", [0.49, 0.44, 0.5, 0.46], pendentes=["simbolos"]),
        ],
        regioes=[(1, [0.0, 0.0, 0.5, 0.5])],
    )

    for criterio in ("centro", "iou"):
        bloco = _avaliar(
            ficha, [_predicao("ATERRAMENTO", _em((0.52, 0.45), 0.01))], ["ATERRAMENTO"]
        )[criterio]
        assert bloco["por_classe"]["ATERRAMENTO"]["tp"] == 1
        assert bloco["fora_das_regioes"] == 0
        assert bloco["perto_de_poste_pendente"] == 0


def test_segunda_predicao_sobre_a_mesma_referencia_nao_e_absorvida_pelo_casamento() -> None:
    ficha = _ficha(
        [_poste("P1", _em((0.5, 0.5)), [_simbolo("S", "ATERRAMENTO", _em((0.5, 0.5), 0.02))])]
    )
    duas = [
        _predicao("ATERRAMENTO", _em((0.5, 0.5), 0.02)),
        _predicao("ATERRAMENTO", _em((0.5, 0.5), 0.02)),
    ]

    bloco = _avaliar(ficha, duas, ["ATERRAMENTO"])["centro"]

    assert bloco["por_classe"]["ATERRAMENTO"] == {
        "tp": 1,
        "fp": 1,
        "fn": 0,
        "precisao": 0.5,
        "recall": 1.0,
    }


def test_raio_do_poste_pendente_e_respeitado_dos_dois_lados() -> None:
    ficha = _ficha(
        [
            _poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))]),
            _poste("P2", [0.7, 0.7, 0.7, 0.7], pendentes=["simbolos"]),
        ]
    )
    dentro = _predicao("ATERRAMENTO", _em((0.7 + bench.RAIO_POSTE_PENDENTE * 0.98, 0.7), 0.0))
    fora = _predicao("ATERRAMENTO", _em((0.7 + bench.RAIO_POSTE_PENDENTE * 1.02, 0.7), 0.0))

    bloco = _avaliar(ficha, [dentro, fora], ["ATERRAMENTO"])["centro"]

    assert bloco["perto_de_poste_pendente"] == 1
    assert bloco["por_classe"]["ATERRAMENTO"]["fp"] == 1


def test_poste_pendente_de_outra_pagina_nao_desculpa_fp() -> None:
    ficha = _ficha(
        [
            _poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))]),
            _poste("P2", _em((0.7, 0.7)), pendentes=["simbolos"], pagina=2),
        ]
    )

    bloco = _avaliar(ficha, [_predicao("ATERRAMENTO", _em((0.7, 0.7)), pagina=1)], ["ATERRAMENTO"])[
        "centro"
    ]
    bloco_certo = _avaliar(
        ficha, [_predicao("ATERRAMENTO", _em((0.7, 0.7)), pagina=2)], ["ATERRAMENTO"]
    )["centro"]

    assert bloco["perto_de_poste_pendente"] == 0
    assert bloco["por_classe"]["ATERRAMENTO"]["fp"] == 1
    assert bloco_certo["perto_de_poste_pendente"] == 1


def test_predicao_em_pagina_inexistente_na_referencia_nao_levanta() -> None:
    completo = _ficha(
        [_poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))])]
    )
    regional = _ficha(
        [_poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))])],
        regioes=[(1, [0.0, 0.0, 0.5, 0.5])],
    )
    na_pagina_7 = _predicao("ATERRAMENTO", _em((0.2, 0.2)), pagina=7)

    em_completo = _avaliar(completo, [na_pagina_7], ["ATERRAMENTO"])["centro"]
    em_regional = _avaliar(regional, [na_pagina_7], ["ATERRAMENTO"])["centro"]

    # A referência da página 1 não é casada com uma predição da página 7.
    assert em_completo["por_classe"]["ATERRAMENTO"]["tp"] == 0
    assert em_completo["por_classe"]["ATERRAMENTO"]["fp"] == 1
    assert em_completo["por_classe"]["ATERRAMENTO"]["fn"] == 1
    # Escopo regional sem região naquela página: tudo o que sobra ali está fora das regiões.
    assert em_regional["fora_das_regioes"] == 1
    assert em_regional["por_classe"]["ATERRAMENTO"]["fp"] == 0


def test_referencia_regional_sem_regiao_na_pagina_da_predicao_marca_fora_das_regioes() -> None:
    ficha = _ficha(
        [
            _poste("P1", _em((0.2, 0.2)), [_simbolo("S", "ATERRAMENTO", _em((0.2, 0.2)))]),
            _poste(
                "P2", _em((0.6, 0.6)), [_simbolo("S2", "ATERRAMENTO", _em((0.6, 0.6)))], pagina=2
            ),
        ],
        regioes=[(1, [0.0, 0.0, 0.5, 0.5]), (2, [0.5, 0.5, 1.0, 1.0])],
    )
    predicoes = [
        _predicao("ATERRAMENTO", _em((0.2, 0.2))),
        _predicao("ATERRAMENTO", _em((0.6, 0.6)), pagina=2),
        _predicao("ATERRAMENTO", _em((0.2, 0.2)), pagina=2),
        _predicao("ATERRAMENTO", _em((0.6, 0.6)), pagina=3),
    ]

    bloco = _avaliar(ficha, predicoes, ["ATERRAMENTO"])["centro"]

    assert bloco["por_classe"]["ATERRAMENTO"]["tp"] == 2
    assert bloco["fora_das_regioes"] == 2
    assert bloco["por_classe"]["ATERRAMENTO"]["fp"] == 0


def test_predicao_de_legenda_em_cima_da_referencia_nao_vira_tp() -> None:
    ficha = _ficha(
        [_poste("P1", _em((0.5, 0.5)), [_simbolo("S", "ATERRAMENTO", _em((0.5, 0.5), 0.02))])]
    )
    em_cima = [
        _predicao("ATERRAMENTO", _em((0.5, 0.5), 0.02), contexto="legend"),
        _predicao("ATERRAMENTO", _em((0.5, 0.5), 0.02), contexto="informative"),
    ]

    resultado = _avaliar(ficha, em_cima, ["ATERRAMENTO"])

    assert resultado["contexto_nao_desenho"] == 2
    for criterio in ("centro", "iou"):
        classe = resultado[criterio]["por_classe"]["ATERRAMENTO"]
        assert (classe["tp"], classe["fp"], classe["fn"]) == (0, 0, 1)


def test_predicao_de_legenda_de_classe_fora_do_escopo_conta_so_como_contexto() -> None:
    ficha = _ficha([_poste("P1", _em((0.5, 0.5)), [_simbolo("S", "ATERRAMENTO", _em((0.5, 0.5)))])])

    resultado = _avaliar(ficha, [_predicao("ESTAI", _em((0.1, 0.1)), contexto="legend")], [])

    assert resultado["contexto_nao_desenho"] == 1
    assert resultado["centro"]["fora_do_escopo"] == {}


# --- folhas sem símbolos ----------------------------------------------------------------


def test_folha_sem_simbolos_na_ficha_e_sem_predicoes_tem_taxas_nulas() -> None:
    sem_postes = _ficha([])
    sem_simbolos = _ficha([_poste("P1", _em((0.5, 0.5)))])

    for ficha in (sem_postes, sem_simbolos):
        resultado = _avaliar(ficha, [], ["ATERRAMENTO"])
        for criterio in ("centro", "iou"):
            assert resultado[criterio]["por_classe"] == {}
            assert resultado[criterio]["geral"] == {
                "tp": 0,
                "fp": 0,
                "fn": 0,
                "precisao": None,
                "recall": None,
            }
        assert resultado["duplicatas"] == {}


def test_folha_sem_simbolos_na_ficha_conta_fp_de_classe_avaliada_na_rodada() -> None:
    ficha = _ficha([_poste("P1", _em((0.5, 0.5)))])

    resultado = _avaliar(ficha, [_predicao("ATERRAMENTO", _em((0.5, 0.5)))], ["ATERRAMENTO"])

    classe = resultado["centro"]["por_classe"]["ATERRAMENTO"]
    assert classe == {"tp": 0, "fp": 1, "fn": 0, "precisao": 0.0, "recall": None}


def test_rodada_sem_nenhum_simbolo_de_referencia_nao_conta_fp(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    sha = _pdf(corpus / "a.pdf", com_aterramento=True)
    ficha = _ficha([_poste("P1", _em((0.128, 0.15)))], sha)
    rodada = _escrever_rodada(tmp_path, [(ID_A, "a.pdf", ficha)])

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["opcoes"]["classes_avaliadas"] == []
    bloco = relatorio["total"]["atual"]["centro"]
    assert bloco["por_classe"] == {}
    assert bloco["geral"] == {"tp": 0, "fp": 0, "fn": 0, "precisao": None, "recall": None}
    assert sum(bloco["fora_do_escopo"].values()) >= 1


def test_folha_sem_simbolos_recebe_fp_das_classes_avaliadas_pelas_outras_folhas(
    tmp_path: Path,
) -> None:
    corpus = tmp_path / "corpus"
    sha_a = _pdf(corpus / "a.pdf", com_aterramento=True)
    sha_b = _pdf(corpus / "b.pdf", com_aterramento=True)
    sem_simbolos = _ficha([_poste("P1", _em((0.128, 0.15)))], sha_b)
    rodada = _escrever_rodada(
        tmp_path,
        [(ID_A, "a.pdf", _ficha_aterramento(sha_a)), (ID_B, "b.pdf", sem_simbolos)],
    )

    relatorio = _rodar(rodada, tmp_path / "saida")

    folha = relatorio["por_pdf"][ID_B]["metodos"]["atual"]["centro"]
    assert folha["por_classe"]["ATERRAMENTO"]["fp"] >= 1
    assert folha["por_classe"]["ATERRAMENTO"]["fn"] == 0
    assert folha["por_classe"]["ATERRAMENTO"]["recall"] is None


def test_rodada_sem_folha_medida_grava_relatorio_vazio_com_processos_altos(
    tmp_path: Path,
) -> None:
    (tmp_path / "corpus").mkdir()
    rodada = _escrever_rodada(tmp_path, [(ID_A, "a.pdf", None), (ID_B, "b.pdf", None)])
    saida = tmp_path / "saida"

    relatorio = _rodar(rodada, saida, processos=4)

    assert relatorio["por_pdf"] == {
        ID_A: {"situacao": "sem_referencia"},
        ID_B: {"situacao": "sem_referencia"},
    }
    assert relatorio["comparacao"]["folhas"] == []
    assert relatorio["total"]["atual"]["folhas_medidas"] == 0
    assert relatorio["por_familia"] == {}
    assert "Processos: 4 (efetivos: 0)" in (saida / "simbolos-ficha.md").read_text("utf-8")


# --- comparação entre métodos (R-E06.1-5b) ----------------------------------------------


def _registrar_metodo(
    monkeypatch: pytest.MonkeyPatch, nome: str, funcao: Callable[[Path, str], Any]
) -> None:
    monkeypatch.setitem(bench.METODOS, nome, funcao)
    monkeypatch.setitem(
        bench.ASSINATURAS, nome, lambda: {"metodo_id": nome, "versao": "t", "observacao": ""}
    )


def test_comparacao_exclui_a_folha_em_que_um_metodo_levanta_excecao(
    rodada_tres_folhas: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def outro(pdf: Path, pdf_id: str) -> Dados:
        if pdf_id == ID_B:
            raise RuntimeError(f"explodiu em {pdf}")
        return {"predicoes": [], "assinatura": {}, "falha": None}

    _registrar_metodo(monkeypatch, "outro", outro)

    relatorio = _rodar(rodada_tres_folhas, tmp_path / "saida", metodos=("atual", "outro"))

    comparacao = relatorio["comparacao"]
    assert comparacao["folhas"] == [ID_A, ID_C]
    atual = comparacao["metodos"]["atual"]
    assert atual["folhas_medidas"] == 2
    # B (fn = 1 para o atual) não entra na comparação, mas entra no total do atual.
    assert atual["centro"]["geral"]["fn"] == 0
    assert relatorio["total"]["atual"]["folhas_medidas"] == 3
    assert relatorio["total"]["atual"]["centro"]["geral"]["fn"] == 1
    assert relatorio["total"]["outro"]["folhas_medidas"] == 2
    assert relatorio["por_pdf"][ID_B]["metodos"]["outro"]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_B]["metodos"]["atual"]["situacao"] == "ok"
    assert str(tmp_path) not in _textos(tmp_path / "saida")


def test_comparacao_com_tres_metodos_exige_sucesso_de_todos(
    rodada_tres_folhas: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falha_em(alvo: str) -> Callable[[Path, str], Dados]:
        def metodo(pdf: Path, pdf_id: str) -> Dados:
            erro = "quebrou" if pdf_id == alvo else None
            return {"predicoes": [], "assinatura": {}, "falha": erro}

        return metodo

    _registrar_metodo(monkeypatch, "m1", falha_em(ID_A))
    _registrar_metodo(monkeypatch, "m2", falha_em(ID_C))

    relatorio = _rodar(rodada_tres_folhas, tmp_path / "saida", metodos=("atual", "m1", "m2"))

    assert relatorio["comparacao"]["folhas"] == [ID_B]
    for nome in ("atual", "m1", "m2"):
        assert relatorio["comparacao"]["metodos"][nome]["folhas_medidas"] == 1


def test_comparacao_fica_vazia_quando_um_metodo_falha_em_todas_as_folhas(
    rodada_tres_folhas: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def sempre(pdf: Path, pdf_id: str) -> Dados:
        return {"predicoes": [], "assinatura": {}, "falha": "quebrou"}

    _registrar_metodo(monkeypatch, "outro", sempre)
    saida = tmp_path / "saida"

    relatorio = _rodar(rodada_tres_folhas, saida, metodos=("atual", "outro"))

    comparacao = relatorio["comparacao"]
    assert comparacao["folhas"] == []
    zerado = comparacao["metodos"]["atual"]["centro"]["geral"]
    assert zerado == {"tp": 0, "fp": 0, "fn": 0, "precisao": None, "recall": None}
    assert relatorio["total"]["atual"]["folhas_medidas"] == 3
    assert relatorio["total"]["outro"]["folhas_medidas"] == 0
    assert relatorio["total"]["outro"]["centro"]["por_classe"] == {}
    texto = (saida / "simbolos-ficha.md").read_text(encoding="utf-8")
    assert "mesmas folhas (0)" in texto


def test_comparacao_ignora_folha_com_falha_e_sem_referencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    sha_a = _pdf(corpus / "a.pdf", com_aterramento=True)
    _pdf(corpus / "b.pdf", com_aterramento=True)
    rodada = _escrever_rodada(
        tmp_path,
        [
            (ID_A, "a.pdf", _ficha_aterramento(sha_a)),
            (ID_B, "b.pdf", _ficha_aterramento("f" * 64)),
            (ID_C, "c.pdf", None),
        ],
    )

    def outro(pdf: Path, pdf_id: str) -> Dados:
        return {"predicoes": [], "assinatura": {}, "falha": None}

    _registrar_metodo(monkeypatch, "outro", outro)

    relatorio = _rodar(rodada, tmp_path / "saida", metodos=("atual", "outro"))

    assert relatorio["comparacao"]["folhas"] == [ID_A]
    assert relatorio["por_pdf"][ID_B]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_C] == {"situacao": "sem_referencia"}
    # A folha sem referência não é falha; a de sha errado é, para os dois métodos.
    for nome in ("atual", "outro"):
        assert relatorio["total"][nome]["folhas_medidas"] == 1
        assert relatorio["total"][nome]["folhas_com_falha"] == 1


# --- detector que falha tira o método dos totais ----------------------------------------

_DETECTORES = [
    pytest.param(
        "zeny_project_handler.adapters.analysis.pymupdf_symbols",
        "_extract_symbolic_equipment",
        id="legado",
    ),
    pytest.param(
        "zeny_project_handler.adapters.analysis.pymupdf_guys", "observar_estais", id="estais"
    ),
    pytest.param(
        "zeny_project_handler.adapters.analysis.pymupdf_transformers",
        "observar_transformadores",
        id="transformadores",
    ),
    pytest.param(
        "zeny_project_handler.adapters.analysis.declarative_symbols",
        "observar_pacotes",
        id="pacotes",
    ),
]


@pytest.mark.parametrize(("modulo", "atributo"), _DETECTORES)
def test_detector_que_falha_numa_folha_tira_so_essa_folha_dos_totais(
    modulo: str,
    atributo: str,
    rodada_tres_folhas: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def quebrado(pagina: Any, *_: Any, **__: Any) -> Any:
        if str(pagina.parent.name).endswith("b.pdf"):
            raise RuntimeError("detector quebrou")
        return original(pagina, *_, **__)

    alvo = importlib.import_module(modulo)
    original = getattr(alvo, atributo)
    monkeypatch.setattr(alvo, atributo, quebrado)

    relatorio = _rodar(rodada_tres_folhas, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_B]["metodos"]["atual"]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_A]["metodos"]["atual"]["situacao"] == "ok"
    total = relatorio["total"]["atual"]
    assert total["folhas_medidas"] == 2
    assert total["folhas_com_falha"] == 1
    # O FN da folha B (referência sem desenho) não pode entrar na base que a E06.3 vai superar.
    assert total["centro"]["geral"]["fn"] == 0
    assert total["centro"]["por_classe"]["ATERRAMENTO"]["tp"] >= 2


def test_manifesto_com_status_failed_sem_failures_tambem_tira_o_metodo(
    rodada_tres_folhas: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = runner.infer_pdf

    def com_status_failed(*args: Any, **kwargs: Any) -> Any:
        manifesto, previstas, execucoes = original(*args, **kwargs)
        if args[1] == ID_B:
            manifesto = {**manifesto, "status": "failed", "failures": []}
        return manifesto, previstas, execucoes

    monkeypatch.setattr(runner, "infer_pdf", com_status_failed)

    relatorio = _rodar(rodada_tres_folhas, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_B]["metodos"]["atual"]["situacao"] == "falha"
    assert relatorio["total"]["atual"]["folhas_medidas"] == 2


# --- serial x paralelo e pool -----------------------------------------------------------


def _rodada_mista(tmp_path: Path) -> Path:
    """Cinco folhas fora de ordem alfabética: ok, sha errado, sem referência, ok, ok."""
    corpus = tmp_path / "corpus"
    sha_c = _pdf(corpus / "c.pdf", com_aterramento=True)
    _pdf(corpus / "a.pdf", com_aterramento=True)
    sha_b = _pdf(corpus / "b.pdf", com_aterramento=False)
    sha_e = _pdf(corpus / "e.pdf", com_aterramento=True)
    return _escrever_rodada(
        tmp_path,
        [
            (ID_C, "c.pdf", _ficha_aterramento(sha_c)),
            (ID_A, "a.pdf", _ficha_aterramento("f" * 64)),
            (ID_D, "d.pdf", None),
            (ID_B, "b.pdf", _ficha_sem_desenho(sha_b)),
            (ID_E, "e.pdf", _ficha_aterramento(sha_e)),
        ],
    )


def test_paralelo_igual_ao_serial_com_falha_sem_referencia_e_ordem_do_rodada_json(
    tmp_path: Path,
) -> None:
    rodada = _rodada_mista(tmp_path)
    serial = _rodar(rodada, tmp_path / "serial", processos=1)
    paralelo = _rodar(rodada, tmp_path / "paralelo", processos=3)

    ordem = [ID_C, ID_A, ID_D, ID_B, ID_E]
    assert list(serial["por_pdf"]) == ordem
    assert list(paralelo["por_pdf"]) == ordem
    assert _sem_tempo(paralelo) == _sem_tempo(serial)
    for chave in ("tp", "fp", "fn"):
        por_familia = sum(
            bloco["atual"]["centro"]["geral"][chave] for bloco in serial["por_familia"].values()
        )
        assert por_familia == serial["total"]["atual"]["centro"]["geral"][chave]
    assert serial["comparacao"]["folhas"] == [ID_C, ID_B, ID_E]
    assert paralelo["comparacao"]["folhas"] == [ID_C, ID_B, ID_E]
    json_serial = json.loads((tmp_path / "serial" / "simbolos-ficha.json").read_text("utf-8"))
    json_paralelo = json.loads((tmp_path / "paralelo" / "simbolos-ficha.json").read_text("utf-8"))
    assert _sem_tempo(json_paralelo) == _sem_tempo(json_serial)
    md_serial = (tmp_path / "serial" / "simbolos-ficha.md").read_text(encoding="utf-8")
    md_paralelo = (tmp_path / "paralelo" / "simbolos-ficha.md").read_text(encoding="utf-8")
    assert "Processos: 3 (efetivos: 3)" in md_paralelo
    assert (
        md_paralelo.replace("Processos: 3 (efetivos: 3)", "Processos: 1 (efetivos: 1)") == md_serial
    )


class _PoolFalso:
    """Substitui o ``ProcessPoolExecutor``: registra ``max_workers`` e roda no mesmo processo."""

    criados: ClassVar[list[int]] = []

    def __init__(self, max_workers: int | None = None, **_: Any) -> None:
        _PoolFalso.criados.append(int(max_workers or 0))

    def __enter__(self) -> _PoolFalso:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def map(self, funcao: Callable[[Any], Any], itens: Sequence[Any]) -> Iterator[Any]:
        return map(funcao, itens)


def test_processos_efetivos_sao_limitados_a_61(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "corpus").mkdir()
    folhas = [
        (f"{indice:03d}-xxxxxxxxxxxx", f"{indice}.pdf", _ficha([_poste("P1", _em((0.5, 0.5)))]))
        for indice in range(1, 63)
    ]
    rodada = _escrever_rodada(tmp_path, folhas)
    _PoolFalso.criados = []
    monkeypatch.setattr(bench, "ProcessPoolExecutor", _PoolFalso)

    _rodar(rodada, tmp_path / "saida", processos=100)

    assert _PoolFalso.criados == [61]
    assert "Processos: 100 (efetivos: 61)" in (tmp_path / "saida" / "simbolos-ficha.md").read_text(
        "utf-8"
    )


def test_uma_so_folha_nao_cria_pool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    corpus = tmp_path / "corpus"
    sha = _pdf(corpus / "a.pdf", com_aterramento=True)
    rodada = _escrever_rodada(tmp_path, [(ID_A, "a.pdf", _ficha_aterramento(sha))])
    _PoolFalso.criados = []
    monkeypatch.setattr(bench, "ProcessPoolExecutor", _PoolFalso)

    relatorio = _rodar(rodada, tmp_path / "saida", processos=8)

    assert _PoolFalso.criados == []
    assert relatorio["por_pdf"][ID_A]["situacao"] == "ok"
    assert "Processos: 8 (efetivos: 1)" in (tmp_path / "saida" / "simbolos-ficha.md").read_text(
        "utf-8"
    )


def test_pool_quebrado_antes_do_primeiro_resultado_falha_todas_e_grava_o_relatorio(
    rodada_tres_folhas: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PoolQuebrado(_PoolFalso):
        def map(self, funcao: Callable[[Any], Any], itens: Sequence[Any]) -> Iterator[Any]:
            raise BrokenProcessPool("morreu na partida")

    monkeypatch.setattr(bench, "ProcessPoolExecutor", PoolQuebrado)
    saida = tmp_path / "saida"

    relatorio = _rodar(rodada_tres_folhas, saida, processos=3)

    for pdf_id in (ID_A, ID_B, ID_C):
        assert relatorio["por_pdf"][pdf_id]["situacao"] == "falha"
    assert relatorio["total"]["atual"]["folhas_medidas"] == 0
    assert relatorio["total"]["atual"]["folhas_com_falha"] == 3
    assert (saida / "simbolos-ficha.json").is_file()
    assert (saida / "simbolos-ficha.md").is_file()
    assert str(tmp_path) not in _textos(saida)


def test_pool_quebrado_no_meio_preserva_sem_referencia_e_resultados_anteriores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rodada = _rodada_mista(tmp_path)

    class PoolQuebrado(_PoolFalso):
        def map(self, funcao: Callable[[Any], Any], itens: Sequence[Any]) -> Iterator[Any]:
            yield funcao(itens[0])
            yield funcao(itens[1])
            raise BrokenProcessPool("morreu")

    monkeypatch.setattr(bench, "ProcessPoolExecutor", PoolQuebrado)

    relatorio = _rodar(rodada, tmp_path / "saida", processos=2)

    assert relatorio["por_pdf"][ID_C]["situacao"] == "ok"
    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_D] == {"situacao": "sem_referencia"}
    assert relatorio["por_pdf"][ID_B]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_E]["situacao"] == "falha"
    assert relatorio["comparacao"]["folhas"] == [ID_C]


# --- avaliacao-cega: recusa lexical antes de qualquer I/O -------------------------------


def _vigiar_io(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Registra todo acesso a disco, PyMuPDF ou ``infer_pdf`` cujo argumento cite a pasta cega."""
    acessos: list[str] = []

    def vigiar(original: Callable[..., Any]) -> Callable[..., Any]:
        def interno(*args: Any, **kwargs: Any) -> Any:
            if any("avaliacao-cega" in str(item).casefold() for item in (*args, *kwargs.values())):
                acessos.append(f"{getattr(original, '__name__', original)}")
            return original(*args, **kwargs)

        return interno

    for nome in ("is_file", "exists", "stat", "read_bytes", "open", "resolve", "is_dir"):
        monkeypatch.setattr(Path, nome, vigiar(getattr(Path, nome)))
    monkeypatch.setattr(builtins, "open", vigiar(builtins.open))
    monkeypatch.setattr(os.path, "isfile", vigiar(os.path.isfile))
    monkeypatch.setattr(os.path, "exists", vigiar(os.path.exists))
    monkeypatch.setattr(pymupdf, "open", vigiar(pymupdf.open))
    monkeypatch.setattr(runner, "infer_pdf", vigiar(runner.infer_pdf))
    return acessos


def _rodada_cega(tmp_path: Path, raiz_corpus: str, relativo: str) -> Path:
    corpus = tmp_path / "corpus"
    sha = _pdf(corpus / "avaliacao-cega" / "x.pdf", com_aterramento=True)
    relativo = relativo.replace("{corpus}", corpus.as_posix())
    return _escrever_rodada(
        tmp_path, [(ID_A, relativo, _ficha_aterramento(sha))], raiz_corpus=raiz_corpus
    )


@pytest.mark.parametrize(
    ("raiz_corpus", "relativo"),
    [
        pytest.param("../corpus/avaliacao-cega", "x.pdf", id="na-raiz-do-corpus"),
        pytest.param("../corpus/AVALIACAO-CEGA", "x.pdf", id="na-raiz-em-maiusculas"),
        pytest.param("../corpus", "AvaLiacao-CEGA/x.pdf", id="caixa-mista"),
        pytest.param("../corpus", "avaliacao-cega//x.pdf", id="separador-duplo"),
        pytest.param("../corpus", "./avaliacao-cega/./x.pdf", id="pontos-no-meio"),
        pytest.param("../corpus", "sub/../avaliacao-cega/x.pdf", id="volta-com-ponto-ponto"),
        pytest.param("../corpus", "avaliacao-cega/../avaliacao-cega/x.pdf", id="vai-e-volta"),
        pytest.param("../corpus", "{corpus}/avaliacao-cega/x.pdf", id="caminho-absoluto"),
        pytest.param("../corpus/sub/..", "avaliacao-cega/x.pdf", id="raiz-com-ponto-ponto"),
        pytest.param("../corpus", "sub\\..\\avaliacao-cega\\x.pdf", id="barras-invertidas"),
    ],
)
def test_avaliacao_cega_e_recusada_sem_nenhum_acesso_ao_caminho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raiz_corpus: str, relativo: str
) -> None:
    rodada = _rodada_cega(tmp_path, raiz_corpus, relativo)
    acessos = _vigiar_io(monkeypatch)

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert "metodos" not in relatorio["por_pdf"][ID_A]
    assert acessos == []
    assert relatorio["total"]["atual"]["folhas_medidas"] == 0


@pytest.mark.skipif(
    sys.platform != "win32", reason="no Windows o componente com ponto final é o mesmo diretório"
)
@pytest.mark.parametrize(
    ("raiz_corpus", "relativo"),
    [
        pytest.param("../corpus", "avaliacao-cega./x.pdf", id="ponto-final-no-relativo"),
        pytest.param("../corpus", "AVALIACAO-CEGA./x.pdf", id="ponto-final-em-maiusculas"),
        pytest.param("../corpus/avaliacao-cega.", "x.pdf", id="ponto-final-na-raiz"),
    ],
)
def test_avaliacao_cega_com_ponto_final_do_windows_tambem_e_recusada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raiz_corpus: str, relativo: str
) -> None:
    rodada = _rodada_cega(tmp_path, raiz_corpus, relativo)
    # Sem a guarda o Windows entrega o PDF: "avaliacao-cega." e "avaliacao-cega" são o mesmo nome.
    assert (tmp_path / "corpus" / "avaliacao-cega." / "x.pdf").is_file()
    acessos = _vigiar_io(monkeypatch)

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert "metodos" not in relatorio["por_pdf"][ID_A]
    assert acessos == []


def test_pasta_cuja_nome_apenas_contem_avaliacao_cega_nao_e_recusada(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    sha = _pdf(corpus / "minha-avaliacao-cega-2" / "avaliacao-cega.pdf", com_aterramento=True)
    rodada = _escrever_rodada(
        tmp_path,
        [(ID_A, "minha-avaliacao-cega-2/avaliacao-cega.pdf", _ficha_aterramento(sha))],
    )

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "ok"


def test_folha_sem_referencia_na_pasta_cega_nao_e_aberta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pdf(tmp_path / "corpus" / "avaliacao-cega" / "x.pdf", com_aterramento=True)
    rodada = _escrever_rodada(tmp_path, [(ID_A, "avaliacao-cega/x.pdf", None)])
    acessos = _vigiar_io(monkeypatch)

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A] == {"situacao": "sem_referencia"}
    assert acessos == []


# --- entrada externa: ficha, PDF, pdf_id ------------------------------------------------


def test_sha_com_um_byte_alterado_e_recusado_e_as_outras_folhas_seguem(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    sha_a = _pdf(corpus / "a.pdf", com_aterramento=True)
    sha_b = _pdf(corpus / "b.pdf", com_aterramento=True)
    dados = bytearray((corpus / "a.pdf").read_bytes())
    dados.extend(b"\n%adulterado")
    (corpus / "a.pdf").write_bytes(bytes(dados))
    rodada = _escrever_rodada(
        tmp_path,
        [(ID_A, "a.pdf", _ficha_aterramento(sha_a)), (ID_B, "b.pdf", _ficha_aterramento(sha_b))],
    )

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert "metodos" not in relatorio["por_pdf"][ID_A]
    assert relatorio["por_pdf"][ID_B]["situacao"] == "ok"
    assert relatorio["total"]["atual"]["folhas_medidas"] == 1
    assert relatorio["total"]["atual"]["folhas_com_falha"] == 1


@pytest.mark.parametrize(
    "conteudo",
    [
        pytest.param(b"", id="arquivo-vazio"),
        pytest.param(b"isto nao e um pdf\n" * 20, id="texto-qualquer"),
    ],
)
def test_pdf_ilegivel_com_sha_correto_e_falha_da_folha(tmp_path: Path, conteudo: bytes) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "quebrado.pdf").write_bytes(conteudo)
    sha_quebrado = hashlib.sha256(conteudo).hexdigest()
    sha_b = _pdf(corpus / "b.pdf", com_aterramento=True)
    rodada = _escrever_rodada(
        tmp_path,
        [
            (ID_A, "quebrado.pdf", _ficha_aterramento(sha_quebrado)),
            (ID_B, "b.pdf", _ficha_aterramento(sha_b)),
        ],
    )

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_B]["situacao"] == "ok"
    assert "quebrado" not in _textos(tmp_path / "saida")
    assert str(tmp_path) not in _textos(tmp_path / "saida")


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("{ isto nao e json", id="json-invalido"),
        pytest.param("[]", id="json-nao-objeto"),
        pytest.param(json.dumps({"schema_version": 1}), id="ficha-incompleta"),
    ],
)
def test_referencia_corrompida_e_falha_da_folha_sem_derrubar_as_outras(
    tmp_path: Path, texto: str
) -> None:
    corpus = tmp_path / "corpus"
    sha_b = _pdf(corpus / "b.pdf", com_aterramento=True)
    _pdf(corpus / "a.pdf", com_aterramento=True)
    rodada = _escrever_rodada(
        tmp_path,
        [(ID_A, "a.pdf", texto), (ID_B, "b.pdf", _ficha_aterramento(sha_b))],
    )

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_B]["situacao"] == "ok"
    assert str(tmp_path) not in _textos(tmp_path / "saida")


def test_ficha_do_tipo_predicao_nao_serve_de_referencia(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    sha = _pdf(corpus / "a.pdf", com_aterramento=True)
    ficha = _ficha_aterramento(sha)
    ficha["tipo"] = "predicao"
    ficha["gerador"] = {"nome": "teste", "versao": "1"}
    rodada = _escrever_rodada(tmp_path, [(ID_A, "a.pdf", json.dumps(ficha))])

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert "metodos" not in relatorio["por_pdf"][ID_A]


@pytest.mark.parametrize(
    "pdf_id",
    [
        pytest.param("../fora", id="sobe-diretorio"),
        pytest.param("..\\fora", id="sobe-diretorio-windows"),
        pytest.param("a/b", id="com-barra"),
        pytest.param("", id="vazio"),
        pytest.param("..", id="ponto-ponto"),
    ],
)
def test_pdf_id_hostil_no_rodada_json_nao_sai_da_rodada(tmp_path: Path, pdf_id: str) -> None:
    corpus = tmp_path / "corpus"
    sha = _pdf(corpus / "a.pdf", com_aterramento=True)
    rodada = _escrever_rodada(tmp_path, [(pdf_id, "a.pdf", None)])
    # Ficha válida plantada exatamente onde o pdf_id hostil apontaria.
    plantada = rodada / "pdfs" / pdf_id / "ficha"
    plantada.mkdir(parents=True, exist_ok=True)
    (plantada / "referencia.json").write_text(json.dumps(_ficha_aterramento(sha)), "utf-8")

    relatorio = _rodar(rodada, tmp_path / "saida")

    folha = relatorio["por_pdf"][pdf_id]
    assert folha["situacao"] == "falha"
    assert "metodos" not in folha


# --- relatório sem caminho absoluto nem nome de PDF -------------------------------------


def _sem_caminho_nem_nome(texto: str, tmp_path: Path, *nomes: str) -> None:
    assert str(tmp_path) not in texto
    assert tmp_path.as_posix() not in texto
    assert str(tmp_path).upper() not in texto.upper()
    assert not re.search(r"[A-Za-z]:[\\/]", texto)
    for nome in nomes:
        assert nome not in texto


def test_relatorio_de_rodada_com_varias_falhas_nao_vaza_caminho_nem_nome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    sha_ok = _pdf(corpus / "sub-secreta" / "pdf-secreto-ok.pdf", com_aterramento=True)
    _pdf(corpus / "sub-secreta" / "pdf-secreto-sha.pdf", com_aterramento=True)
    (corpus / "pdf-secreto-lixo.pdf").write_bytes(b"lixo")
    rodada = _escrever_rodada(
        tmp_path,
        [
            (ID_A, "sub-secreta/pdf-secreto-ok.pdf", _ficha_aterramento(sha_ok)),
            (ID_B, "sub-secreta/pdf-secreto-sha.pdf", _ficha_aterramento("f" * 64)),
            (ID_C, "pdf-secreto-lixo.pdf", _ficha_aterramento(hashlib.sha256(b"lixo").hexdigest())),
            (ID_D, "sub-secreta/pdf-secreto-ausente.pdf", _ficha_aterramento("a" * 64)),
            (ID_E, "avaliacao-cega/pdf-secreto-cego.pdf", _ficha_aterramento("b" * 64)),
        ],
    )

    def quebrado(pdf: Path, pdf_id: str) -> Dados:
        raise OSError(f"falha ao ler {pdf} e ../corpus/sub-secreta/pdf-secreto-ok.pdf")

    _registrar_metodo(monkeypatch, "quebrado", quebrado)
    saida = tmp_path / "saida"

    relatorio = _rodar(rodada, saida, metodos=("atual", "quebrado"))

    assert relatorio["por_pdf"][ID_A]["metodos"]["quebrado"]["situacao"] == "falha"
    _sem_caminho_nem_nome(_textos(saida), tmp_path, "pdf-secreto")


def test_erro_de_detector_com_caminho_de_rede_nao_vaza_o_servidor(
    rodada_tres_folhas: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ``infer_pdf`` faz ``resolve()``: em unidade mapeada o caminho do erro vira UNC, que não é
    # igual à string ``pdf`` que o script conhece e precisa ser saneado pela forma.
    def quebrado(pdf: Path, pdf_id: str) -> Dados:
        raise OSError(r"não abriu \\servidor-cemig\projetos\rede\folha-12.bin")

    _registrar_metodo(monkeypatch, "quebrado", quebrado)
    saida = tmp_path / "saida"

    _rodar(rodada_tres_folhas, saida, metodos=("quebrado",))

    texto = _textos(saida)
    assert "servidor-cemig" not in texto
    assert "projetos" not in texto


def test_erro_de_detector_com_o_caminho_do_pdf_em_outra_caixa_nao_vaza_o_nome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    sha = _pdf(corpus / "Projeto Rua Tal 12.pdf", com_aterramento=True)
    rodada = _escrever_rodada(tmp_path, [(ID_A, "Projeto Rua Tal 12.pdf", _ficha_aterramento(sha))])

    def quebrado(pdf: Path, pdf_id: str) -> Dados:
        # Caixa diferente da que o script conhece (o Windows devolve a caixa do disco).
        raise OSError(f"falha em '{str(pdf).upper()}' na pagina 1")

    _registrar_metodo(monkeypatch, "quebrado", quebrado)
    saida = tmp_path / "saida"

    _rodar(rodada, saida, metodos=("quebrado",))

    texto = _textos(saida).upper()
    assert "RUA TAL" not in texto
    assert "PROJETO" not in texto


def test_opcoes_e_assinaturas_nao_trazem_caminho_da_maquina(
    rodada_tres_folhas: Path, tmp_path: Path
) -> None:
    saida = tmp_path / "saida"

    _rodar(rodada_tres_folhas, saida)

    texto = _textos(saida)
    raiz_repo = Path(bench.__file__).resolve().parent.parent
    assert str(raiz_repo) not in texto
    assert raiz_repo.as_posix() not in texto
    assert not re.search(r"[A-Za-z]:[\\/]", texto)
    for pdf in ("a.pdf", "b.pdf", "c.pdf"):
        assert pdf not in texto


# --- CLI --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor",
    [
        pytest.param("0", id="zero"),
        pytest.param("-3", id="negativo"),
        pytest.param("abc", id="texto"),
        pytest.param("1.5", id="decimal"),
        pytest.param("1e2", id="cientifico"),
        pytest.param("", id="vazio"),
    ],
)
def test_cli_processos_invalido_sai_com_2_sem_criar_a_saida(valor: str, tmp_path: Path) -> None:
    saida = tmp_path / "saida"

    with pytest.raises(SystemExit) as erro:
        bench.main(["--rodada", str(tmp_path), "--saida", str(saida), "--processos", valor])

    assert erro.value.code == 2
    assert not saida.exists()


def test_cli_metodo_desconhecido_sai_com_2(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as erro:
        bench.main(["--rodada", str(tmp_path), "--saida", str(tmp_path), "--metodo", "inexistente"])

    assert erro.value.code == 2


def test_cli_sem_rodada_ou_sem_saida_sai_com_2(tmp_path: Path) -> None:
    for argumentos in (["--saida", str(tmp_path)], ["--rodada", str(tmp_path)]):
        with pytest.raises(SystemExit) as erro:
            bench.main(argumentos)
        assert erro.value.code == 2


def test_cli_rodada_inexistente_sai_com_1_sem_criar_a_saida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saida = tmp_path / "saida"

    with pytest.raises(SystemExit) as erro:
        bench.main(["--rodada", str(tmp_path / "nao-existe"), "--saida", str(saida)])

    assert erro.value.code == 1
    assert not saida.exists()
    assert str(tmp_path) not in capsys.readouterr().err


def test_cli_com_processos_pelo_argparse_chega_ao_relatorio(
    rodada_tres_folhas: Path, tmp_path: Path
) -> None:
    saida = tmp_path / "saida"

    codigo = bench.main(
        ["--rodada", str(rodada_tres_folhas), "--saida", str(saida), "--processos", "2"]
    )

    assert codigo == 0
    assert "Processos: 2 (efetivos: 2)" in (saida / "simbolos-ficha.md").read_text("utf-8")


def test_medir_simbolos_recusa_metodo_desconhecido_e_processos_invalidos(
    rodada_tres_folhas: Path, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match=r"m[ée]todo"):
        _rodar(rodada_tres_folhas, tmp_path / "s1", metodos=("nao-existe",))
    with pytest.raises(ValueError, match="processos"):
        _rodar(rodada_tres_folhas, tmp_path / "s2", processos=0)
    assert not (tmp_path / "s1").exists()
    assert not (tmp_path / "s2").exists()
