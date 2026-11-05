# mypy: disable-error-code="no-untyped-call"
"""E06.1, ataque de etapa: guarda de memorização, escala da geometria e integração das tarefas.

Três frentes, sobre o diff inteiro da etapa:

1. a guarda contra memorização de folha (Task 3): formas de escapar que a suíte da tarefa não
   cobre e prova de que ela enxerga qualquer nó dos pacotes reais;
2. a escala da fusão de polilinhas (Task 5): o teste da tarefa mede só a passada de
   colinearidade; aqui o trabalho total é contado (chamadas Python e C vistas por
   ``sys.setprofile``, determinísticas e sem relógio) em outras formas de entrada;
3. a costura entre o benchmark de símbolos (Task 1) e a página do modelo (Task 2): mesma
   numeração de página, mesmo referencial normalizado, mesma família.
"""

from __future__ import annotations

import copy
import json
import math
import random
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pymupdf
import pytest
import scripts.benchmark_simbolos_ficha as bench
from tests.unit.test_benchmark_simbolos_ficha import (
    _desenhar_aterramento,
    _em,
    _ficha,
    _poste,
    _simbolo,
)
from tests.unit.test_drawing_model_geometry_adversarial import traco
from tests.unit.test_pymupdf_drawing_model_pagina import _pdf_com_clip
from tests.unit.test_symbol_packages_sem_memorizacao import _PASTA_PACOTES, verificar_pacote

from zeny_project_handler.adapters.analysis import declarative_symbols
from zeny_project_handler.adapters.analysis.drawing_model.geometry import reconstruir_polilinhas
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    extrair_modelo_desenho,
    pagina_modelo_com_indices,
)

# ---------------------------------------------------------------------------------------
# 1. Guarda contra memorização (Task 3)
# ---------------------------------------------------------------------------------------

# Montado por concatenação para o `git grep` do fechamento não achar este arquivo.
_FOLHA = "PROJETO" + " DE REDE"


@pytest.mark.parametrize(
    "dados",
    [
        pytest.param({"x": -0.123456}, id="float-negativo"),
        pytest.param({"a": [{"b": [[{"c": 0.123456}]]}]}, id="float-aninhado-fundo"),
        pytest.param({"a": [["folha.PDF"]]}, id="pdf-em-maiusculas-aninhado"),
        pytest.param({"h": "A1" * 32}, id="hexadecimal-de-64-em-maiusculas"),
        pytest.param({"h": "sha256:" + "ab" * 32}, id="hexadecimal-com-prefixo"),
        pytest.param({"h": "ab" * 40}, id="hexadecimal-maior-que-64"),
        pytest.param({"p": "x=12.345678 y=3"}, id="coordenada-no-meio-do-texto"),
        pytest.param({"p": _FOLHA.lower() + " ns 1"}, id="nome-de-folha-em-minusculas"),
        pytest.param({"p": "ver " + _FOLHA.title()}, id="nome-de-folha-capitalizado"),
    ],
)
def test_guarda_reprova_formas_comuns_de_memorizacao(dados: Any) -> None:
    assert len(verificar_pacote(dados)) == 1


def test_guarda_conta_cada_violacao_separadamente() -> None:
    dados = {"a": 0.123456, "b": [0.654321, "x.pdf"], "c": {"d": "ab" * 32}}
    assert len(verificar_pacote(dados)) == 4


def test_guarda_indica_o_caminho_do_valor_infrator() -> None:
    (violacao,) = verificar_pacote({"variants": [{"ok": 1}, {"x": 0.123456}]})
    assert "variants[1].x" in violacao


@pytest.mark.parametrize(
    "dados",
    [
        pytest.param({"x": 100000, "y": True, "z": None, "w": 0.0}, id="escalares-sem-casas"),
        pytest.param({"x": 1e16, "y": -1e22}, id="float-enorme-sem-casas"),
        pytest.param({"x": [], "y": {}}, id="contentores-vazios"),
        pytest.param({"x": "v2.0 §3.1; página 6"}, id="texto-de-norma-legitimo"),
        pytest.param({"x": float("nan"), "y": float("inf")}, id="nao-finitos-nao-quebram"),
    ],
)
def test_guarda_aceita_o_que_nao_e_coordenada(dados: Any) -> None:
    assert verificar_pacote(dados) == []


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param(".123456", id="sem-digito-antes-do-ponto"),
        pytest.param("1e-05", id="notacao-cientifica"),
        pytest.param("-1.5E-7", id="notacao-cientifica-com-ponto"),
        pytest.param("0,123456", id="virgula-decimal-ptbr"),
    ],
)
def test_guarda_reprova_string_numerica_com_mais_de_4_casas_em_qualquer_grafia(
    texto: str,
) -> None:
    # Task 3: "nenhum float (nem string numerica) com mais de 4 casas decimais".
    assert len(verificar_pacote({"x": texto})) == 1


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param(_FOLHA.replace(" ", "  "), id="espaco-duplo"),
        pytest.param(_FOLHA.replace(" ", "\n"), id="quebra-de-linha"),
        pytest.param(_FOLHA.replace(" ", chr(0xA0)), id="espaco-sem-quebra"),
    ],
)
def test_guarda_reprova_nome_de_folha_com_espaco_variante(texto: str) -> None:
    # Texto copiado de PDF costuma trazer espaco duplicado, NBSP ou quebra de linha.
    assert len(verificar_pacote({"locator": texto + " NS 123"})) == 1


def test_guarda_varre_a_mesma_pasta_que_o_carregador_de_pacotes() -> None:
    assert declarative_symbols._PACKAGE_DIR.resolve() == _PASTA_PACOTES.resolve()
    arquivos = sorted(_PASTA_PACOTES.glob("*.json"))
    assert len(arquivos) == len(declarative_symbols.carregar_pacotes())


def _contentores(dados: Any) -> list[dict[str, Any] | list[Any]]:
    achados: list[dict[str, Any] | list[Any]] = []
    if isinstance(dados, dict):
        achados.append(dados)
        for valor in dados.values():
            achados.extend(_contentores(valor))
    elif isinstance(dados, list):
        achados.append(dados)
        for valor in dados:
            achados.extend(_contentores(valor))
    return achados


def test_guarda_enxerga_violacao_injetada_em_qualquer_no_dos_pacotes_reais() -> None:
    injetados = 0
    for arquivo in sorted(_PASTA_PACOTES.glob("*.json")):
        base = json.loads(arquivo.read_text(encoding="utf-8"))
        assert verificar_pacote(base) == [], arquivo.name
        for indice in range(len(_contentores(base))):
            copia = copy.deepcopy(base)
            alvo = _contentores(copia)[indice]
            if isinstance(alvo, dict):
                alvo["injetado"] = 0.123456
            else:
                alvo.append(0.123456)
            assert len(verificar_pacote(copia)) == 1, (arquivo.name, indice)
            injetados += 1
    assert injetados > 100  # a varredura percorreu estruturas reais, nao um punhado


# ---------------------------------------------------------------------------------------
# 2. Escala da fusão de polilinhas (Task 5): trabalho contado, sem relógio
# ---------------------------------------------------------------------------------------


def _eventos(funcao: Callable[[], object]) -> int:
    """Chamadas (Python e C) feitas por `funcao`: o custo medido sem relógio de parede."""
    contagem = 0

    def perfil(_frame: object, evento: str, _arg: object) -> None:
        nonlocal contagem
        if evento in ("call", "c_call"):
            contagem += 1

    anterior = sys.getprofile()
    sys.setprofile(perfil)
    try:
        funcao()
    finally:
        sys.setprofile(anterior)
    return contagem


def _trabalho(construir: Callable[[int], list[Caminho]], n: int) -> int:
    caminhos = construir(n)
    return _eventos(lambda: reconstruir_polilinhas(caminhos))


def _grade_de_segmentos(n: int) -> list[Caminho]:
    por_linha = 100
    return [
        traco(
            (float(i % por_linha), float(i // por_linha * 5)),
            (float(i % por_linha + 1), float(i // por_linha * 5)),
            ordem=i,
        )
        for i in range(n)
    ]


def _segmentos_disjuntos(n: int) -> list[Caminho]:
    return [traco((i * 3.0, 0.0), (i * 3.0 + 1, 0.0), ordem=i) for i in range(n)]


def _cadeia_reta_embaralhada(n: int) -> list[Caminho]:
    ordem = list(range(n))
    random.Random(7).shuffle(ordem)
    return [traco((float(i), 0.0), (float(i + 1), 0.0), ordem=k) for k, i in enumerate(ordem)]


def _perimetro_de_quadrado_colinear(n: int) -> list[Caminho]:
    lado = n // 4
    pontos = [(float(i), 0.0) for i in range(lado)]
    pontos += [(float(lado), float(i)) for i in range(lado)]
    pontos += [(float(lado - i), float(lado)) for i in range(lado)]
    pontos += [(0.0, float(lado - i)) for i in range(lado)]
    return [traco(*pontos, (0.0, 0.0))]


def _circulo_poligonal(n: int) -> list[Caminho]:
    raio = n / 4.0
    pontos = [
        (raio * math.cos(2 * math.pi * i / n), raio * math.sin(2 * math.pi * i / n))
        for i in range(n)
    ]
    return [traco(*pontos, pontos[0])]


def _pente(n: int) -> list[Caminho]:
    dentes = n // 2
    espinha = [traco((float(i), 0.0), (float(i + 1), 0.0), ordem=i) for i in range(dentes)]
    pontas = [traco((float(i), 0.0), (float(i), 5.0), ordem=dentes + i) for i in range(dentes)]
    return espinha + pontas


def _ziguezague_e_reta_fechados(n: int) -> list[Caminho]:
    metade = n // 2
    ida = [(float(i), float(i % 2) * 5) for i in range(metade)]
    volta = [(float(metade - i), 10.0) for i in range(metade)]
    return [traco(*ida, *volta, ida[0])]


def _reta_ziguezague_reta(n: int) -> list[Caminho]:
    terco = n // 3
    antes = [(float(i), 0.0) for i in range(terco)]
    meio = [(terco + float(i), float(i % 2) * 5) for i in range(terco)]
    depois = [(2.0 * terco + float(i), 0.0) for i in range(terco)]
    return [traco(*antes, *meio, *depois)]


def _ziguezague_puro(n: int) -> list[Caminho]:
    return [traco(*[(float(i), float(i % 2) * 5) for i in range(n)])]


@pytest.mark.parametrize(
    "construir",
    [
        pytest.param(_grade_de_segmentos, id="grade-de-segmentos-soltos"),
        pytest.param(_segmentos_disjuntos, id="segmentos-disjuntos"),
        pytest.param(_cadeia_reta_embaralhada, id="cadeia-reta-em-ordem-embaralhada"),
        pytest.param(_perimetro_de_quadrado_colinear, id="perimetro-fechado-colinear"),
        pytest.param(_circulo_poligonal, id="circulo-poligonal-fechado"),
        pytest.param(_pente, id="espinha-com-dentes-em-t"),
        pytest.param(_ziguezague_puro, id="ziguezague-sem-colineares"),
        pytest.param(_ziguezague_e_reta_fechados, id="ziguezague-e-reta-em-laco-fechado"),
        pytest.param(_reta_ziguezague_reta, id="reta-ziguezague-reta"),
    ],
)
def test_fusao_escala_linearmente_em_formas_variadas(
    construir: Callable[[int], list[Caminho]],
) -> None:
    pequeno, grande = _trabalho(construir, 4_000), _trabalho(construir, 8_000)
    assert pequeno >= 4_000  # ao menos uma chamada por segmento: a contagem mede algo
    assert grande <= 2.5 * pequeno, (pequeno, grande)


def _estrela(n: int) -> list[Caminho]:
    # raio proporcional a n: as pontas ficam a mais de 1 pt umas das outras (nada se funde)
    return [
        traco(
            (0.0, 0.0),
            (n * math.cos(2 * math.pi * i / n), n * math.sin(2 * math.pi * i / n)),
            ordem=i,
        )
        for i in range(n)
    ]


def _segmento_repetido(n: int) -> list[Caminho]:
    return [traco((0.0, 0.0), (10.0, 0.0), ordem=i) for i in range(n)]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "reconstruir_polilinhas quadrática em nó de grau alto (estrela/segmento repetido); "
        "corrigir antes da E06.2 ligar o modelo no servidor — ruling R18 da E06.1"
    ),
)
@pytest.mark.parametrize(
    "construir",
    [
        pytest.param(_estrela, id="no-com-muitos-raios"),
        pytest.param(_segmento_repetido, id="mesmo-segmento-pintado-n-vezes"),
    ],
)
def test_fusao_escala_linearmente_com_no_de_grau_alto(
    construir: Callable[[int], list[Caminho]],
) -> None:
    # Requisito "nada quadratico" da geometria. `_polilinhas_do_estilo` reabre a lista de arestas
    # incidentes do no a cada percurso e a cada `any(...)`: com grau k, k percursos de custo k.
    pequeno, grande = _trabalho(construir, 1_000), _trabalho(construir, 2_000)
    assert pequeno >= 1_000
    assert grande <= 2.5 * pequeno, (pequeno, grande)


def test_estrela_continua_correta_alem_de_lenta_ou_rapida() -> None:
    # Guarda de sanidade do cenario acima: n raios distintos viram n polilinhas abertas.
    caminhos = _estrela(300)
    polilinhas = reconstruir_polilinhas(caminhos)
    assert len(polilinhas) == 300
    assert all(not p.fechada and len(p.pontos) == 2 for p in polilinhas)
    assert {o for p in polilinhas for o in p.origens} == set(range(300))


# ---------------------------------------------------------------------------------------
# 3. Costura entre o benchmark de símbolos (Task 1) e a página do modelo (Task 2)
# ---------------------------------------------------------------------------------------


def _pdf_aterramento(caminho: Path, *, rotacao: int = 0, pagina_do_desenho: int = 1) -> Path:
    with pymupdf.open() as documento:
        for numero in range(1, pagina_do_desenho + 1):
            pagina = documento.new_page(width=500, height=400)
            if numero == pagina_do_desenho:
                _desenhar_aterramento(pagina)
            pagina.set_rotation(rotacao)
        documento.save(caminho)
    return caminho


def _caixa_normalizada_do_modelo(
    caminho: Path, indice: int
) -> tuple[tuple[float, float, float, float], int]:
    with pymupdf.open(caminho) as documento:
        pagina, indices = pagina_modelo_com_indices(documento[indice], indice)
    pontos = [p for c in pagina.caminhos for s in c.subcaminhos for i in s for p in i.pontos]
    assert pontos
    caixa = (
        min(p[0] for p in pontos) / pagina.largura,
        min(p[1] for p in pontos) / pagina.altura,
        max(p[0] for p in pontos) / pagina.largura,
        max(p[1] for p in pontos) / pagina.altura,
    )
    return caixa, len(indices)


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
def test_bbox_do_benchmark_e_o_modelo_usam_o_mesmo_referencial_da_pagina_exibida(
    tmp_path: Path, rotacao: int
) -> None:
    pdf = _pdf_aterramento(tmp_path / "rot.pdf", rotacao=rotacao)
    predicoes = bench._predicoes_atual(pdf, "x")["predicoes"]
    assert [p["classe"] for p in predicoes] == ["ATERRAMENTO"]
    esperado = predicoes[0]["bbox"]

    caixa, quantos = _caixa_normalizada_do_modelo(pdf, 0)

    assert quantos > 0
    folga = 1e-6
    # o simbolo previsto cabe na caixa dos tracos do modelo (que inclui o filete de ligacao)
    assert caixa[0] - folga <= esperado[0] and esperado[2] <= caixa[2] + folga
    assert caixa[1] - folga <= esperado[1] and esperado[3] <= caixa[3] + folga
    # e encosta nos dois lados em que nao ha filete: a caixa nao esta deslocada nem espelhada
    lados_encostados = sum(abs(a - b) < 1e-3 for a, b in zip(caixa, esperado, strict=True))
    assert lados_encostados >= 3


def test_pagina_do_benchmark_e_de_base_1_e_a_do_modelo_de_base_0(tmp_path: Path) -> None:
    pdf = _pdf_aterramento(tmp_path / "duas.pdf", pagina_do_desenho=2)
    (predicao,) = bench._predicoes_atual(pdf, "x")["predicoes"]
    assert predicao["pagina"] == 2

    modelo = extrair_modelo_desenho(pdf)
    com_caminhos = [p.indice for p in modelo.paginas if p.caminhos]
    assert com_caminhos == [predicao["pagina"] - 1]

    caixa, _ = _caixa_normalizada_do_modelo(pdf, predicao["pagina"] - 1)
    assert caixa[0] - 1e-6 <= predicao["bbox"][0] <= predicao["bbox"][2] <= caixa[2] + 1e-6


def test_medir_pdf_usa_a_mesma_familia_do_modelo_em_pagina_com_clip_e_grupo(
    tmp_path: Path,
) -> None:
    pdf = _pdf_com_clip(tmp_path / "clip.pdf")
    ficha = _ficha(
        [_poste("P1", _em((0.5, 0.5)), [_simbolo("S1", "ATERRAMENTO", _em((0.5, 0.5)))])]
    )

    medida = bench.medir_pdf(pdf, ficha, "001-aaaaaaaaaaaa", ("atual",))

    assert medida["situacao"] == "ok"
    assert medida["familia"] == extrair_modelo_desenho(pdf).familia.familia
    assert medida["metodos"]["atual"]["situacao"] == "ok"


def test_benchmark_nao_depende_do_estado_deixado_pela_pagina_do_modelo(tmp_path: Path) -> None:
    # `_DesenhosFiltrados` e `indices_crus` nao podem vazar para a impressao estrutural.
    pdf = _pdf_com_clip(tmp_path / "clip.pdf")
    from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import impressao_estrutural

    with pymupdf.open(pdf) as documento:
        antes = impressao_estrutural(documento)
        pagina_modelo_com_indices(documento[0], 0)
        depois = impressao_estrutural(documento)
    assert antes == depois
