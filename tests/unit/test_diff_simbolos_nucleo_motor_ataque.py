# mypy: disable-error-code="no-untyped-call"
"""Ataque ao diff núcleo contra motor: passadas, fronteiras, orientação, falhas, pool e guardas."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any, ClassVar, Final

import pymupdf
import pytest
import scripts.diff_simbolos_nucleo_motor as diff
from tests.fixtures.declarative_symbols import corpus

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    TetoGramaticasExcedido,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import (
    gasto_por_fase as gasto_real,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    pagina_para_gramaticas as modelo_real,
)

Dados = dict[str, Any]
Desenho = Callable[[pymupdf.Page], None]

ID_A: Final = "001-aaaaaaaaaaaa"
ID_B: Final = "002-bbbbbbbbbbbb"
ID_C: Final = "003-cccccccccccc"
CAMARA_CT: Final = "cemig-eo-r3-s06-v001"
QDP: Final = "cemig-eo-r3-s07-v003"
DISCO: Final = "cemig-eo-r3-s28-v001"
PRETO: Final = (0.0, 0.0, 0.0)
CATEGORIAS: Final = ("ambos", "so_motor", "so_nucleo", "indice_diverge", "geometria_diverge")


# --- desenhos -------------------------------------------------------------------------------


def _camara(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(101, 115, 169, 149), color=PRETO, width=1)
    pagina.insert_text((107, 140), "CT", fontsize=11)


def _q_e_dp_no_canto(pagina: pymupdf.Page) -> None:
    """`Q`+`DP` com intruso no fluxo (só o núcleo casa), longe do centro da página: a caixa crua
    e a visual não se cruzam com `/Rotate` 90, então os textos só entram pela caixa visual."""
    pagina.draw_rect(pymupdf.Rect(30, 200, 78, 248), color=PRETO, width=1)
    pagina.insert_text((36, 229), "Q", fontsize=11)
    pagina.insert_text((250, 229), "ZZ", fontsize=11)
    largura = pymupdf.get_text_length("Q", fontsize=11)
    pagina.insert_text((36 + largura, 229), "DP", fontsize=11, color=(0.7, 0.0, 0.0))


def _q_e_dp_no_centro(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(110, 110, 158, 158), color=PRETO, width=1)
    pagina.insert_text((116, 139), "Q", fontsize=11)
    pagina.insert_text((250, 139), "ZZ", fontsize=11)
    largura = pymupdf.get_text_length("Q", fontsize=11)
    pagina.insert_text((116 + largura, 139), "DP", fontsize=11, color=(0.7, 0.0, 0.0))


def _disco_em_faixas(pagina: pymupdf.Page) -> None:
    """O disco que o exportador tessela em faixas (estrato `positive_stripes` do corpus)."""
    corpus.draw_terminal_disc(pagina, "stripes")


# --- rodada sintética -----------------------------------------------------------------------


def _pdf(caminho: Path, paginas: Sequence[Desenho], rotacao: int = 0) -> str:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:
        for desenhar in paginas:
            pagina = documento.new_page(width=300, height=300)
            desenhar(pagina)
            if rotacao:
                pagina.set_rotation(rotacao)
        documento.save(caminho)
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _rodada(
    base: Path, folhas: Sequence[tuple[str, str, str]], raiz_corpus: str = "../corpus"
) -> Path:
    rodada = base / "rodada"
    rodada.mkdir(parents=True)
    manifesto = {
        "schema_version": "curadoria-rodada-v1",
        "raiz_corpus": raiz_corpus,
        "pdfs": [
            {"pdf_id": pdf_id, "caminho_relativo": relativo, "sha256": sha}
            for pdf_id, relativo, sha in folhas
        ],
    }
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    return rodada


def _uma_folha(tmp_path: Path, paginas: Sequence[Desenho], rotacao: int = 0) -> Path:
    sha = _pdf(tmp_path / "corpus" / "folha.pdf", paginas, rotacao)
    return _rodada(tmp_path, [(ID_A, "folha.pdf", sha)])


def _rodar(rodada: Path, saida: Path, processos: int = 1) -> Dados:
    diff.medir_diff(rodada, saida, processos=processos)
    gravado: Dados = json.loads((saida / "diff-nucleo-motor.json").read_text(encoding="utf-8"))
    return gravado


def _markdown(saida: Path) -> str:
    return (saida / "diff-nucleo-motor.md").read_text(encoding="utf-8")


def _textos(saida: Path) -> list[str]:
    return [(saida / "diff-nucleo-motor.json").read_text(encoding="utf-8"), _markdown(saida)]


def _sem_tempo(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {chave: _sem_tempo(item) for chave, item in valor.items() if chave != "tempo_s"}
    if isinstance(valor, list):
        return [_sem_tempo(item) for item in valor]
    return valor


def _itens(relatorio: Dados, categoria: str) -> Iterator[tuple[str, Dados, Dados]]:
    for pdf_id, folha in relatorio["por_pdf"].items():
        for pagina in folha.get("paginas", ()):
            for variante in sorted(pagina["variantes"]):
                for item in pagina["variantes"][variante][categoria]:
                    yield pdf_id, pagina, item


# --- comparador: fronteiras de 0,5 pt -------------------------------------------------------


def _obs(variante: str, indice: int, caixa: Sequence[float]) -> diff.Observada:
    x0, y0, x1, y1 = (float(valor) for valor in caixa)
    return diff.Observada(variante=variante, classe="C", indice_cru=indice, bbox=(x0, y0, x1, y1))


def _contagem(comparacao: Any) -> dict[str, int]:
    return {chave: len(comparacao[chave]) for chave in CATEGORIAS}


def _deslocada(delta: float, coordenada: int) -> tuple[float, ...]:
    base = [100.0, 100.0, 120.0, 120.0]
    base[coordenada] += delta
    return tuple(base)


_FRONTEIRAS = [
    pytest.param(delta, coordenada, perto, id=f"{nome}-c{coordenada}")
    for delta, perto, nome in (
        (0.49, True, "+0.49"),
        (-0.49, True, "-0.49"),
        (0.5, True, "+0.50"),
        (-0.5, True, "-0.50"),
        (0.51, False, "+0.51"),
        (-0.51, False, "-0.51"),
    )
    for coordenada in range(4)
]


@pytest.mark.parametrize(("delta", "coordenada", "perto"), _FRONTEIRAS)
def test_fronteira_de_meio_ponto_na_mesma_chave(delta: float, coordenada: int, perto: bool) -> None:
    """Passadas 1 e 2: até 0,5 pt em cada lado da caixa é `ambos`; além disso, `geometria`."""
    motor = [_obs("v", 3, _deslocada(0.0, 0))]
    nucleo = [_obs("v", 3, _deslocada(delta, coordenada))]

    contagem = _contagem(diff.comparar_observacoes(motor, nucleo)["v"])

    esperado = dict.fromkeys(CATEGORIAS, 0)
    esperado["ambos" if perto else "geometria_diverge"] = 1
    assert contagem == esperado


@pytest.mark.parametrize(("delta", "coordenada", "perto"), _FRONTEIRAS)
def test_fronteira_de_meio_ponto_com_indice_diferente(
    delta: float, coordenada: int, perto: bool
) -> None:
    """Passadas 3 e 4: até 0,5 pt é `indice_diverge`; além disso, um em cada `so_*`."""
    motor = [_obs("v", 3, _deslocada(0.0, 0))]
    nucleo = [_obs("v", 8, _deslocada(delta, coordenada))]

    contagem = _contagem(diff.comparar_observacoes(motor, nucleo)["v"])

    esperado = dict.fromkeys(CATEGORIAS, 0)
    if perto:
        esperado["indice_diverge"] = 1
    else:
        esperado["so_motor"] = esperado["so_nucleo"] = 1
    assert contagem == esperado


def test_mesmo_indice_longe_vai_a_geometria_antes_de_indice_diverge_perto() -> None:
    """Passada 2 antes da 3: o motor de índice 3 pareia com o núcleo de índice 3 longe, e o núcleo
    de índice 7 na mesma caixa sobra como `so_nucleo`, sem roubar o par de `geometria`."""
    caixa = (10.0, 10.0, 20.0, 20.0)
    motor = [_obs("v", 3, caixa)]
    nucleo = [_obs("v", 7, caixa), _obs("v", 3, (50.0, 50.0, 60.0, 60.0))]

    comparacao = diff.comparar_observacoes(motor, nucleo)["v"]

    assert _contagem(comparacao) == {
        "ambos": 0,
        "so_motor": 0,
        "so_nucleo": 1,
        "indice_diverge": 0,
        "geometria_diverge": 1,
    }
    assert comparacao["so_nucleo"][0].indice_cru == 7


def _aleatorias(gerador: random.Random, quantidade: int) -> list[diff.Observada]:
    """Poucas variantes, índices e caixas, para forçar colisões nas quatro passadas."""
    observacoes = []
    for _ in range(quantidade):
        x = gerador.choice([10.0, 10.3, 10.6, 11.2, 40.0])
        y = gerador.choice([10.0, 10.4, 10.9])
        observacoes.append(
            _obs(gerador.choice("ab"), gerador.randint(0, 3), (x, y, x + 10.0, y + 10.0))
        )
    return observacoes


@pytest.mark.parametrize("semente", range(40), ids=lambda s: f"semente{s:02d}")
def test_cada_observacao_cai_em_uma_so_categoria_e_as_somas_fecham(semente: int) -> None:
    gerador = random.Random(semente)
    motor = _aleatorias(gerador, gerador.randint(0, 9))
    nucleo = _aleatorias(gerador, gerador.randint(0, 9))

    comparacao = diff.comparar_observacoes(motor, nucleo)

    vistos_motor: list[int] = []
    vistos_nucleo: list[int] = []
    for variante, tipada in comparacao.items():
        categorias: Mapping[str, Any] = tipada
        do_motor = [o for o in motor if o.variante == variante]
        do_nucleo = [o for o in nucleo if o.variante == variante]
        pares = ("ambos", "indice_diverge", "geometria_diverge")
        emparelhados = sum(len(categorias[c]) for c in pares)
        assert emparelhados + len(categorias["so_motor"]) == len(do_motor)
        assert emparelhados + len(categorias["so_nucleo"]) == len(do_nucleo)
        for categoria in pares:
            for par in categorias[categoria]:
                vistos_motor.append(id(par.motor))
                vistos_nucleo.append(id(par.nucleo))
                assert par.motor.variante == par.nucleo.variante == variante
                mesmo = par.motor.indice_cru == par.nucleo.indice_cru
                perto = diff._perto(par.motor, par.nucleo)
                assert (mesmo, perto) == {
                    "ambos": (True, True),
                    "geometria_diverge": (True, False),
                    "indice_diverge": (False, True),
                }[categoria]
        vistos_motor.extend(id(o) for o in categorias["so_motor"])
        vistos_nucleo.extend(id(o) for o in categorias["so_nucleo"])
        # O que sobra dos dois lados não casaria em nenhuma passada.
        for m in categorias["so_motor"]:
            for n in categorias["so_nucleo"]:
                assert m.indice_cru != n.indice_cru
                assert not diff._perto(m, n)
    assert sorted(vistos_motor) == sorted(id(o) for o in motor)
    assert sorted(vistos_nucleo) == sorted(id(o) for o in nucleo)


def test_somas_por_lado_fecham_no_relatorio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No JSON, `ambos + geometria + indice + so_motor` é o que o motor observou na página."""
    corpo = tmp_path / "corpus"
    rodada = _rodada(
        tmp_path,
        [
            (ID_A, "a.pdf", _pdf(corpo / "a.pdf", [_camara, _q_e_dp_no_centro])),
            (ID_B, "b.pdf", _pdf(corpo / "b.pdf", [_disco_em_faixas, _camara])),
        ],
    )
    vistos: dict[tuple[str, int], tuple[int, int]] = {}
    original_motor, original_nucleo = diff.observar_pacotes, diff.observar_pacotes_modelo

    def contar(lado: int, funcao: Callable[..., Any]) -> Callable[..., Any]:
        def interno(pagina: Any, **kwargs: Any) -> Any:
            resultado = funcao(pagina, **kwargs)
            chave = (kwargs["documento_id"], kwargs["pagina_numero"])
            atual = list(vistos.get(chave, (0, 0)))
            atual[lado] = len(resultado.observacoes)
            vistos[chave] = (atual[0], atual[1])
            return resultado

        return interno

    monkeypatch.setattr(diff, "observar_pacotes", contar(0, original_motor))
    monkeypatch.setattr(diff, "observar_pacotes_modelo", contar(1, original_nucleo))
    relatorio = _rodar(rodada, tmp_path / "saida")

    soma_total = dict.fromkeys(CATEGORIAS, 0)
    for pdf_id, folha in relatorio["por_pdf"].items():
        for pagina in folha["paginas"]:
            motor, nucleo = vistos[(pdf_id, pagina["pagina"])]
            soma = {c: sum(len(v[c]) for v in pagina["variantes"].values()) for c in CATEGORIAS}
            pares = soma["ambos"] + soma["indice_diverge"] + soma["geometria_diverge"]
            assert pares + soma["so_motor"] == motor
            assert pares + soma["so_nucleo"] == nucleo
            for categoria in CATEGORIAS:
                soma_total[categoria] += soma[categoria]
    assert {c: relatorio["total"][c] for c in CATEGORIAS} == soma_total
    assert soma_total["ambos"] >= 2
    assert soma_total["so_nucleo"] == 1


# --- orientação -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gramatica", "rotacao", "esperado"),
    [
        ("triangle_in_frame", 0, False),
        ("triangle_in_frame", 90, True),
        ("triangle_in_frame", 180, True),
        ("triangle_in_frame", 270, True),
        ("nested_rectangles_bar", 0, False),
        ("nested_rectangles_bar", 90, True),
        ("nested_rectangles_bar", 180, False),
        ("nested_rectangles_bar", 270, True),
        ("label_in_frame", 90, False),
        ("label_in_frame", 180, False),
        ("framed_diagonals", 270, False),
        ("diamond_three_dots", 90, False),
        ("", 90, False),
    ],
    ids=lambda v: str(v),
)
def test_sensivel_a_orientacao_so_onde_a_regra_diz(
    gramatica: str, rotacao: int, esperado: bool
) -> None:
    assert diff.sensivel_a_orientacao(gramatica, rotacao) is esperado


@pytest.mark.parametrize("rotacao", [90, 270], ids=["90", "270"])
def test_disco_em_faixas_deitado_aparece_como_orientacao(tmp_path: Path, rotacao: int) -> None:
    """R-E06.2.1-7: "triângulo, barra e faixas ganham pares de divergência esperada"; as faixas
    só ficam em pé em 0 e 180. O disco tesselado em faixas (estrato `positive_stripes` do corpus),
    numa página com `/Rotate` 90 ou 270, é casado pelo motor e não pelo núcleo, por decisão: o
    item tem de sair com `orientacao: true`, não como divergência real (Review Focus 2)."""
    relatorio = _rodar(_uma_folha(tmp_path, [_disco_em_faixas], rotacao), tmp_path / "saida")
    (pagina,) = relatorio["por_pdf"][ID_A]["paginas"]
    categorias = pagina["variantes"][DISCO]

    divergentes = [*categorias["so_motor"], *categorias["so_nucleo"]]
    assert divergentes, "o motor casa as faixas cruas e o núcleo não as casa deitadas"
    assert [item["orientacao"] for item in divergentes] == [True] * len(divergentes)


def test_disco_em_faixas_a_180_e_em_pe_casa_nos_dois(tmp_path: Path) -> None:
    relatorio = _rodar(_uma_folha(tmp_path, [_disco_em_faixas], 180), tmp_path / "saida")
    (pagina,) = relatorio["por_pdf"][ID_A]["paginas"]

    assert len(pagina["variantes"][DISCO]["ambos"]) == 1
    assert pagina["variantes"][DISCO]["so_motor"] == []


@pytest.fixture(scope="module")
def corpus_habilitado(tmp_path_factory: pytest.TempPathFactory) -> Path:
    caminho = tmp_path_factory.mktemp("corpus-habilitado") / "fonte.pdf"
    corpus.build_enabled_corpus(caminho)
    return caminho


@pytest.mark.parametrize("rotacao", [0, 90, 180, 270], ids=["0", "90", "180", "270"])
def test_corpus_habilitado_so_diverge_com_orientacao(
    corpus_habilitado: Path, tmp_path: Path, rotacao: int
) -> None:
    """Corpus com todas as variantes habilitadas: em pé, tudo em `ambos`; girado, toda divergência
    é das previstas por R-E06.2.1-7 (o núcleo só perde o que o motor casa cru) e sai marcada."""
    destino = tmp_path / "corpus" / "c.pdf"
    destino.parent.mkdir(parents=True)
    with pymupdf.open(corpus_habilitado) as documento:
        for pagina in documento:
            pagina.set_rotation(rotacao)
        documento.save(destino)
    sha = hashlib.sha256(destino.read_bytes()).hexdigest()
    relatorio = _rodar(_rodada(tmp_path, [(ID_A, "c.pdf", sha)]), tmp_path / "saida")

    total = relatorio["total"]
    assert total["paginas_nao_comparadas"] == 0
    assert (total["so_nucleo"], total["indice_diverge"], total["geometria_diverge"]) == (0, 0, 0)
    assert total["ambos"] > 0
    if rotacao == 0:
        assert total["so_motor"] == 0
    sem_orientacao = [
        (pagina["pagina"], item["variante"])
        for _, pagina, item in _itens(relatorio, "so_motor")
        if item["orientacao"] is not True
    ]
    assert sem_orientacao == []


# --- item so_nucleo em página girada --------------------------------------------------------


def _q_e_dp_em_pe_para_quem_ve(caminho: Path, rotacao: int) -> str:
    """`_q_e_dp_no_canto` desenhado em pé no espaço visual de uma página com `/Rotate`."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        pagina.set_rotation(rotacao)
        matriz = pagina.derotation_matrix
        pagina.draw_rect(pymupdf.Rect(30, 200, 78, 248) * matriz, color=PRETO, width=1)
        largura = pymupdf.get_text_length("Q", fontsize=11)
        for texto, x, cor in (
            ("Q", 36.0, PRETO),
            ("ZZ", 250.0, PRETO),
            ("DP", 36.0 + largura, (0.7, 0.0, 0.0)),
        ):
            ponto = pymupdf.Point(x, 229) * matriz
            pagina.insert_text(ponto, texto, fontsize=11, rotate=rotacao, color=cor)
        documento.save(caminho)
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("rotacao", "caixa_crua"),
    [
        (0, (30.0, 200.0, 78.0, 248.0)),
        (90, (200.0, 222.0, 248.0, 270.0)),
        (180, (222.0, 52.0, 270.0, 100.0)),
        (270, (52.0, 30.0, 100.0, 78.0)),
    ],
    ids=["0", "90", "180", "270"],
)
def test_item_so_nucleo_traz_os_textos_da_caixa_visual(
    tmp_path: Path, rotacao: int, caixa_crua: tuple[float, ...]
) -> None:
    """A caixa do item é crua; os textos do modelo estão no espaço visual. Girada, a caixa crua não
    cruza os textos: eles só entram se a caixa for levada ao visual pela rotação da página."""
    sha = _q_e_dp_em_pe_para_quem_ve(tmp_path / "corpus" / "folha.pdf", rotacao)
    relatorio = _rodar(_rodada(tmp_path, [(ID_A, "folha.pdf", sha)]), tmp_path / "saida")
    (pagina,) = relatorio["por_pdf"][ID_A]["paginas"]

    (item,) = pagina["variantes"][QDP]["so_nucleo"]
    assert item["bbox"] == pytest.approx(list(caixa_crua), abs=0.01)
    assert item["orientacao"] is False
    textos = {(t["texto"], t["origem"], t["rotacao"]) for t in item["textos"]}
    assert {("Q", "nativo", 0.0), ("DP", "nativo", 0.0)} <= textos
    assert all(texto != "ZZ" for texto, _, _ in textos)


# --- página não comparada fica fora, a folha continua ---------------------------------------


def test_excecao_do_motor_numa_pagina_nao_derruba_as_outras(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rodada = _uma_folha(tmp_path, [_q_e_dp_no_centro, _camara, _q_e_dp_no_centro])
    original = diff.observar_pacotes

    def motor(pagina: Any, **kwargs: Any) -> Any:
        if kwargs["pagina_numero"] == 1:
            raise RuntimeError("quebrou")
        return original(pagina, **kwargs)

    monkeypatch.setattr(diff, "observar_pacotes", motor)
    saida = tmp_path / "saida"
    relatorio = _rodar(rodada, saida)
    folha = relatorio["por_pdf"][ID_A]

    assert folha["situacao"] == "ok"
    assert [p["situacao"] for p in folha["paginas"]] == ["nao_comparada", "comparada", "comparada"]
    assert folha["paginas"][0]["variantes"] == {}
    assert folha["paginas"][0]["gasto"] is not None
    assert folha["totais"]["paginas_comparadas"] == 2
    assert folha["totais"]["paginas_nao_comparadas"] == 1
    assert relatorio["total"]["so_nucleo"] == 1
    assert relatorio["total"]["ambos"] == 1
    (item,) = (item for _, _, item in _itens(relatorio, "so_nucleo"))
    assert (item["id"], item["pagina"]) == ("item-0001", 3)
    assert "- 001-aaaaaaaaaaaa · p. 1: motor: RuntimeError: quebrou" in _markdown(saida)


def test_fonte_que_falha_numa_pagina_so_tira_aquela_pagina(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = pymupdf_drawing_model._textos_shx

    def shx(pagina: Any) -> Any:
        if pagina.number == 0:
            raise RuntimeError("shx")
        return original(pagina)

    monkeypatch.setattr(pymupdf_drawing_model, "_textos_shx", shx)
    relatorio = _rodar(_uma_folha(tmp_path, [_camara, _camara]), tmp_path / "saida")
    primeira, segunda = relatorio["por_pdf"][ID_A]["paginas"]

    assert primeira["situacao"] == "nao_comparada"
    assert primeira["gasto"] is None
    assert primeira["gasto_motivo"] == "fonte_falhou:modelo.textos_shx_falhou"
    assert primeira["cobertura"]["motor"]["estado"] == "CONCLUIDO"
    assert segunda["situacao"] == "comparada"
    assert segunda["gasto"] is not None
    assert relatorio["total"]["ambos"] == 1
    assert relatorio["total"]["so_motor"] == 0
    assert relatorio["por_pdf"][ID_A]["gasto_maximo"]["pagina"] == 2


# --- gasto acima do teto ----------------------------------------------------------------------


def test_gasto_acima_do_teto_e_numero_real_e_nao_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O diff mede com limite próprio, não com o padrão: com o padrão de `gasto_por_fase` e o
    `LIMITE_CONSULTAS_PAGINA` reduzidos a 3, a página gasta mais que isso e o número sai inteiro,
    com razão > 1, e a comparação não é afetada."""
    real = gasto_real
    limites: list[int] = []

    def gasto(pagina: Any, variantes: Any, *, limite: int = 3) -> Any:
        limites.append(limite)
        return real(pagina, variantes, limite=limite)

    monkeypatch.setattr(diff, "gasto_por_fase", gasto)
    monkeypatch.setattr(diff, "LIMITE_CONSULTAS_PAGINA", 3)
    saida = tmp_path / "saida"
    pdf = tmp_path / "corpus" / "folha.pdf"
    relatorio = _rodar(_uma_folha(tmp_path, [_camara]), saida)
    (pagina,) = relatorio["por_pdf"][ID_A]["paginas"]

    assert limites == [10**12]
    assert pagina["situacao"] == "comparada"
    assert pagina["gasto_motivo"] is None
    total = pagina["gasto"]["total"]
    assert total > 3
    maximo = relatorio["por_pdf"][ID_A]["gasto_maximo"]
    assert maximo["razao_limite"] == pytest.approx(total / 3)
    assert maximo["razao_limite"] > 1
    assert f"| {total} | {total / 3:.6f} |" in _markdown(saida)
    # O número é real: o mesmo gasto com o teto logo abaixo dele estoura.
    with pymupdf.open(pdf) as documento:
        modelo = modelo_real(documento[0], 0, diff.recursos().tabela)
        with pytest.raises(TetoGramaticasExcedido):
            real(modelo, diff.recursos().variantes, limite=total - 1)
        assert real(modelo, diff.recursos().variantes, limite=total).total == total


def test_teto_sem_glifos_limitados_tem_motivo_proprio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = gasto_real
    monkeypatch.setattr(
        diff, "gasto_por_fase", lambda pagina, variantes, **_: real(pagina, variantes, limite=1)
    )

    relatorio = _rodar(_uma_folha(tmp_path, [_camara]), tmp_path / "saida")
    (pagina,) = relatorio["por_pdf"][ID_A]["paginas"]

    assert pagina["gasto"] is None
    assert pagina["gasto_motivo"] == "teto_consultas"
    assert relatorio["por_pdf"][ID_A]["gasto_maximo"] is None


# --- guardas, sha256 e saneamento -------------------------------------------------------------


def test_sha_diferente_nao_le_nenhuma_pagina(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpo = tmp_path / "corpus"
    _pdf(corpo / "a.pdf", [_camara])
    rodada = _rodada(
        tmp_path,
        [(ID_A, "a.pdf", "f" * 64), (ID_B, "b.pdf", _pdf(corpo / "b.pdf", [_camara]))],
    )
    chamados: list[str] = []
    original = diff.observar_pacotes

    def motor(pagina: Any, **kwargs: Any) -> Any:
        chamados.append(kwargs["documento_id"])
        return original(pagina, **kwargs)

    monkeypatch.setattr(diff, "observar_pacotes", motor)
    relatorio = _rodar(rodada, tmp_path / "saida")

    assert chamados == [ID_B]
    assert relatorio["por_pdf"][ID_A] == {
        "situacao": "falha",
        "erro": "sha256 do PDF difere do sha256 do rodada.json",
    }
    assert relatorio["total"]["folhas_falha"] == 1
    assert relatorio["total"]["ambos"] == 1


def test_sha_em_maiusculas_e_aceito(tmp_path: Path) -> None:
    sha = _pdf(tmp_path / "corpus" / "a.pdf", [_camara])
    relatorio = _rodar(_rodada(tmp_path, [(ID_A, "a.pdf", sha.upper())]), tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "ok"


@pytest.mark.parametrize(
    ("entrada", "trecho"),
    [
        pytest.param({"sha256": ""}, "sem sha256", id="sha-vazio"),
        pytest.param({"sha256": None}, "sem sha256", id="sha-nulo"),
        pytest.param(
            {"caminho_relativo": "Sumido Secreto 4711.pdf"}, "não encontrado", id="sumido"
        ),
    ],
)
def test_entrada_invalida_falha_a_folha_sem_nome(
    tmp_path: Path, entrada: dict[str, Any], trecho: str
) -> None:
    sha = _pdf(tmp_path / "corpus" / "Projeto Secreto 4711.pdf", [_camara])
    rodada = _rodada(tmp_path, [(ID_A, "Projeto Secreto 4711.pdf", sha)])
    manifesto = json.loads((rodada / "rodada.json").read_text(encoding="utf-8"))
    manifesto["pdfs"][0].update(entrada)
    (rodada / "rodada.json").write_text(json.dumps(manifesto), encoding="utf-8")
    saida = tmp_path / "saida"

    relatorio = _rodar(rodada, saida)

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert trecho in relatorio["por_pdf"][ID_A]["erro"]
    for texto in _textos(saida):
        assert "Secreto" not in texto
        assert "4711" not in texto


@pytest.mark.parametrize(
    "relativo",
    ["sub/Avaliacao-Cega/a.pdf", "sub/avaliacao-cega./a.pdf", "x/../AVALIACAO-CEGA/a.pdf"],
    ids=["meio", "ponto-final", "normalizado"],
)
def test_componente_cego_no_meio_do_caminho_relativo_e_recusado_sem_abrir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relativo: str
) -> None:
    abertos: list[Any] = []
    original_open = pymupdf.open

    def abrir(*args: Any, **kwargs: Any) -> Any:
        abertos.append(args)
        return original_open(*args, **kwargs)

    monkeypatch.setattr(pymupdf, "open", abrir)
    rodada = _rodada(tmp_path, [(ID_A, relativo, "0" * 64)])
    saida = tmp_path / "saida"

    relatorio = _rodar(rodada, saida)

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert "avaliacao-cega" in relatorio["por_pdf"][ID_A]["erro"]
    assert abertos == []
    for texto in _textos(saida):
        assert "sub/" not in texto
        assert "a.pdf" not in texto


def test_excecao_fora_das_capturadas_falha_a_folha_com_erro_saneado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpo = tmp_path / "corpus"
    nome = "Projeto Secreto 4711.pdf"
    pdf = corpo / "sub dir" / nome
    rodada = _rodada(
        tmp_path,
        [
            (ID_A, f"sub dir/{nome}", _pdf(pdf, [_camara])),
            (ID_B, "b.pdf", _pdf(corpo / "b.pdf", [_q_e_dp_no_centro])),
        ],
    )
    original = modelo_real
    chamadas: list[int] = []

    def modelo(pagina: Any, indice: int, tabela: Any) -> Any:
        chamadas.append(indice)
        if len(chamadas) == 1:
            raise OSError(
                f"[Errno 5] falhou em '{pdf}' ({pdf.resolve().as_posix()}; Projeto Secreto 4711)"
            )
        return original(pagina, indice, tabela)

    monkeypatch.setattr(diff, "pagina_para_gramaticas", modelo)
    saida = tmp_path / "saida"

    relatorio = _rodar(rodada, saida)

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_A]["erro"].startswith("OSError: [Errno 5] falhou em")
    assert relatorio["por_pdf"][ID_B]["situacao"] == "ok"
    (item,) = (item for _, _, item in _itens(relatorio, "so_nucleo"))
    assert item["id"] == "item-0001"
    for texto in _textos(saida):
        for proibido in ("Secreto", "4711", "sub dir", str(tmp_path), tmp_path.as_posix()):
            assert proibido not in texto
        assert str(tmp_path).replace("\\", "\\\\") not in texto


# --- ordem, pool e ids opacos -----------------------------------------------------------------


def _rodada_tres(tmp_path: Path) -> Path:
    """Fora da ordem alfabética: C (2 itens), A (sem item), B (1 item, página 2)."""
    corpo = tmp_path / "corpus"
    return _rodada(
        tmp_path,
        [
            (ID_C, "c.pdf", _pdf(corpo / "c.pdf", [_q_e_dp_no_centro, _q_e_dp_no_canto])),
            (ID_A, "a.pdf", _pdf(corpo / "a.pdf", [_camara])),
            (ID_B, "b.pdf", _pdf(corpo / "b.pdf", [_camara, _q_e_dp_no_centro])),
        ],
    )


def _ids(relatorio: Dados) -> list[tuple[str, int, str]]:
    return sorted(
        (pdf_id, pagina["pagina"], item["id"])
        for pdf_id, pagina, item in _itens(relatorio, "so_nucleo")
    )


def test_ids_seguem_a_ordem_da_rodada_nao_a_do_pdf_id(tmp_path: Path) -> None:
    saida = tmp_path / "saida"
    diff.medir_diff(_rodada_tres(tmp_path), saida)
    relatorio = json.loads((saida / "diff-nucleo-motor.json").read_text(encoding="utf-8"))

    assert _ids(relatorio) == [
        (ID_B, 2, "item-0003"),
        (ID_C, 1, "item-0001"),
        (ID_C, 2, "item-0002"),
    ]
    linhas = [linha for linha in _markdown(saida).splitlines() if linha.startswith("- `item-")]
    assert [linha.split("`")[1] for linha in linhas] == ["item-0001", "item-0002", "item-0003"]
    assert [linha.split(" · ")[1] for linha in linhas] == [ID_C, ID_C, ID_B]


def test_paralelo_igual_ao_serial_com_ids_e_ordem_da_rodada(tmp_path: Path) -> None:
    rodada = _rodada_tres(tmp_path)

    serial = diff.medir_diff(rodada, tmp_path / "serial", processos=1)
    paralelo = diff.medir_diff(rodada, tmp_path / "paralelo", processos=3)

    assert list(serial["por_pdf"]) == [ID_C, ID_A, ID_B]
    assert list(paralelo["por_pdf"]) == [ID_C, ID_A, ID_B]
    assert _sem_tempo(paralelo) == _sem_tempo(serial)
    json_serial = json.loads((tmp_path / "serial" / "diff-nucleo-motor.json").read_text("utf-8"))
    json_paralelo = json.loads(
        (tmp_path / "paralelo" / "diff-nucleo-motor.json").read_text("utf-8")
    )
    assert _sem_tempo(json_paralelo) == _sem_tempo(json_serial)
    assert _ids(json_paralelo) == _ids(json_serial)
    md_serial = _markdown(tmp_path / "serial")
    md_paralelo = _markdown(tmp_path / "paralelo")
    assert "Processos: 3 pedidos, 3 efetivos." in md_paralelo
    corte = "## Totais"
    assert (
        md_paralelo.split(corte, 1)[1].split("## Gasto")[0]
        == (md_serial.split(corte, 1)[1].split("## Gasto")[0])
    )


class _PoolFalso:
    """Substitui o `ProcessPoolExecutor`: registra `max_workers` e roda no mesmo processo."""

    criados: ClassVar[list[int]] = []

    def __init__(self, max_workers: int | None = None, **_: Any) -> None:
        _PoolFalso.criados.append(int(max_workers or 0))

    def __enter__(self) -> _PoolFalso:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def map(self, funcao: Callable[[Any], Any], itens: Sequence[Any]) -> Iterator[Any]:
        yield from map(funcao, itens)


def test_ids_vem_do_resultado_e_nao_da_ordem_de_conclusao_do_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Um pool que conclui as folhas de trás para frente não muda nem a ordem nem os ids."""

    class PoolInvertido(_PoolFalso):
        def map(self, funcao: Callable[[Any], Any], itens: Sequence[Any]) -> Iterator[Any]:
            resultados = [funcao(item) for item in reversed(list(itens))]
            yield from reversed(resultados)

    rodada = _rodada_tres(tmp_path)
    serial = diff.medir_diff(rodada, tmp_path / "serial")
    _PoolFalso.criados = []
    monkeypatch.setattr(diff, "ProcessPoolExecutor", PoolInvertido)
    invertido = diff.medir_diff(rodada, tmp_path / "invertido", processos=100)

    assert _PoolFalso.criados == [3]
    assert list(invertido["por_pdf"]) == [ID_C, ID_A, ID_B]
    assert _sem_tempo(invertido) == _sem_tempo(serial)


def test_pool_quebrado_no_meio_falha_o_resto_e_numera_o_que_mediu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class PoolQuebrado(_PoolFalso):
        def map(self, funcao: Callable[[Any], Any], itens: Sequence[Any]) -> Iterator[Any]:
            yield funcao(itens[0])
            raise BrokenProcessPool("morreu")

    monkeypatch.setattr(diff, "ProcessPoolExecutor", PoolQuebrado)
    saida = tmp_path / "saida"

    relatorio = diff.medir_diff(_rodada_tres(tmp_path), saida, processos=2)

    assert relatorio["por_pdf"][ID_C]["situacao"] == "ok"
    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert relatorio["por_pdf"][ID_B]["situacao"] == "falha"
    assert relatorio["total"]["folhas_falha"] == 2
    assert relatorio["total"]["so_nucleo"] == 2
    assert _ids(relatorio) == [(ID_C, 1, "item-0001"), (ID_C, 2, "item-0002")]
    assert (saida / "diff-nucleo-motor.md").is_file()


def test_processos_invalidos_sao_recusados(tmp_path: Path) -> None:
    rodada = _uma_folha(tmp_path, [_camara])

    with pytest.raises(ValueError, match="processos"):
        diff.medir_diff(rodada, tmp_path / "saida", processos=0)
    with pytest.raises(SystemExit) as erro:
        diff.main(["--rodada", str(rodada), "--saida", str(tmp_path / "s"), "--processos", "0"])
    assert erro.value.code == 2
    assert not (tmp_path / "saida").exists()
    assert not (tmp_path / "s").exists()


# --- markdown -----------------------------------------------------------------------------------


def test_markdown_lista_todo_so_nucleo_numa_linha_e_os_totais_batem(tmp_path: Path) -> None:
    saida = tmp_path / "saida"
    relatorio = diff.medir_diff(_rodada_tres(tmp_path), saida)
    texto = _markdown(saida)

    for _, pagina, item in _itens(relatorio, "so_nucleo"):
        linhas = [linha for linha in texto.splitlines() if f"`{item['id']}`" in linha]
        assert len(linhas) == 1
        assert f"p. {pagina['pagina']}" in linhas[0]
        assert f"`{QDP}`" in linhas[0]
    total = relatorio["total"]
    assert (
        f"| {total['ambos']} | {total['so_motor']} | {total['so_nucleo']} | "
        f"{total['indice_diverge']} | {total['geometria_diverge']} | "
        f"{total['paginas_comparadas']} | {total['paginas_nao_comparadas']} | "
        f"{total['folhas_falha']} |"
    ) in texto.splitlines()
    assert total["so_nucleo"] == 3
