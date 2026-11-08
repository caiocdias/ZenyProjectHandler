# mypy: disable-error-code="no-untyped-call"
"""Diff por variante entre o motor declarativo e o núcleo sobre o modelo, com gasto por fase."""

from __future__ import annotations

import builtins
import copy
import hashlib
import json
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
import scripts.diff_simbolos_nucleo_motor as diff
from scripts.curation_round import RodadaError
from tests.fixtures.declarative_symbols.corpus import ENABLED_CASES, draw_symbol
from tests.fixtures.symbol_grammars.stem_bars import CASOS_HASTE, desenhar_positivo

from zeny_project_handler.adapters.analysis import declarative_symbols, pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import LeituraGlifos
from zeny_project_handler.adapters.analysis.model_symbols import perfil_pacotes_modelo

Dados = dict[str, Any]
Desenho = Callable[[pymupdf.Page], None]

ID_A: Final = "001-aaaaaaaaaaaa"
ID_B: Final = "002-bbbbbbbbbbbb"
CAMARA_CT: Final = "cemig-eo-r3-s06-v001"
QDP: Final = "cemig-eo-r3-s07-v003"
TRIANGULO: Final = "cemig-eo-r3-s07-v001"
BARRA: Final = "cemig-eo-r3-s05-v004"
DISCO: Final = "cemig-eo-r3-s28-v001"
PRETO: Final = (0.0, 0.0, 0.0)
QUADRADO: Final = pymupdf.Rect(110, 110, 158, 158)
CAMPOS_ITEM: Final = {
    "id",
    "pagina",
    "variante",
    "classe",
    "indice_cru",
    "bbox",
    "textos",
    "glifos_lidos",
    "diagnosticos",
    "orientacao",
}


def _classe(variante_id: str) -> str:
    return next(
        str(variante["class_code"])
        for pacote in declarative_symbols.carregar_pacotes()
        for variante in pacote["variants"]
        if variante["id"] == variante_id
    )


# --- desenhos -----------------------------------------------------------------------------


def _camara(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(101, 115, 169, 149), color=PRETO, width=1)
    pagina.insert_text((107, 140), "CT", fontsize=11)


def _q_e_dp_com_intruso(pagina: pymupdf.Page) -> None:
    """`tests/unit/test_symbol_matcher_ataque.py`: o núcleo funde `Q`+`DP`, o motor recusa."""
    pagina.draw_rect(QUADRADO, color=PRETO, width=1)
    pagina.insert_text((116, 139), "Q", fontsize=11)
    pagina.insert_text((250, 139), "ZZ", fontsize=11)
    largura = pymupdf.get_text_length("Q", fontsize=11)
    pagina.insert_text((116 + largura, 139), "DP", fontsize=11, color=(0.7, 0.0, 0.0))


def _disco_com_linha_que_dobra(pagina: pymupdf.Page) -> None:
    """`linha_dobra_no_disco_em_dois_tracos` (R-E06.2.1-6): o motor casa, o núcleo não."""
    cinza, roxo = (0.5, 0.5, 0.5), (0.31, 0.10, 0.30)
    pagina.draw_line((60, 150), (150, 150), color=cinza, width=0.7)
    pagina.draw_line((150, 150), (150, 240), color=cinza, width=0.7)
    pagina.draw_circle((150, 150), 1.4, color=roxo, fill=roxo, width=0.2)


def _triangulo(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(QUADRADO, color=PRETO, width=1)
    forma = pagina.new_shape()
    forma.draw_polyline([(134, 112), (156, 156), (112, 156), (134, 112)])
    forma.finish(color=(0.7, 0.0, 0.0), fill=None, width=1)
    forma.commit()


def _barra(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(QUADRADO, color=PRETO, width=1)
    pagina.draw_rect(pymupdf.Rect(118, 118, 150, 150), color=PRETO, width=1)
    pagina.draw_line((119, 134), (149, 134), color=PRETO, width=1)


# --- rodada sintética, sem ficha -----------------------------------------------------------


def _pdf(caminho: Path, desenhar: Desenho, rotacao: int = 0) -> str:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenhar(pagina)
        if rotacao:
            pagina.set_rotation(rotacao)
        documento.save(caminho)
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _rodada(
    base: Path,
    folhas: Sequence[tuple[str, str, str]],
    raiz_corpus: str = "../corpus",
) -> Path:
    """Rodada em ``base/rodada`` com ``(pdf_id, caminho_relativo, sha256)`` por folha."""
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


def _uma_folha(tmp_path: Path, desenhar: Desenho, rotacao: int = 0) -> Path:
    sha = _pdf(tmp_path / "corpus" / "folha.pdf", desenhar, rotacao)
    return _rodada(tmp_path, [(ID_A, "folha.pdf", sha)])


def _rodar(rodada: Path, saida: Path) -> Dados:
    relatorio = diff.medir_diff(rodada, saida)
    gravado: Dados = json.loads((saida / "diff-nucleo-motor.json").read_text(encoding="utf-8"))
    assert gravado == json.loads(json.dumps(relatorio))
    assert gravado["schema_version"] == "diff-nucleo-motor-v1"
    return gravado


def _pagina(relatorio: Dados, pdf_id: str = ID_A) -> Dados:
    folha = relatorio["por_pdf"][pdf_id]
    assert folha["situacao"] == "ok", folha
    (pagina,) = folha["paginas"]
    assert pagina["pagina"] == 1
    return dict(pagina)


def _categorias(pagina: Dados, variante: str) -> Dados:
    return dict(pagina["variantes"][variante])


def _markdown(saida: Path) -> str:
    return (saida / "diff-nucleo-motor.md").read_text(encoding="utf-8")


# --- comparação na página ------------------------------------------------------------------


def test_os_dois_veem(tmp_path: Path) -> None:
    saida = tmp_path / "saida"
    rodada = _uma_folha(tmp_path, _camara)

    assert diff.main(["--rodada", str(rodada), "--saida", str(saida)]) == 0
    relatorio = json.loads((saida / "diff-nucleo-motor.json").read_text(encoding="utf-8"))
    pagina = _pagina(relatorio)
    categorias = _categorias(pagina, CAMARA_CT)

    assert pagina["situacao"] == "comparada"
    assert len(categorias["ambos"]) == 1
    assert categorias["so_nucleo"] == []
    assert categorias["so_motor"] == []
    assert categorias["indice_diverge"] == []
    assert categorias["geometria_diverge"] == []
    assert pagina["cobertura"]["motor"]["estado"] == "CONCLUIDO"
    assert pagina["cobertura"]["nucleo"]["estado"] == "CONCLUIDO"
    assert relatorio["total"]["ambos"] == 1
    assert relatorio["total"]["so_nucleo"] == 0
    assert relatorio["total"]["paginas_comparadas"] == 1


def test_so_no_nucleo_e_listado(tmp_path: Path) -> None:
    saida = tmp_path / "saida"
    pagina = _pagina(_rodar(_uma_folha(tmp_path, _q_e_dp_com_intruso), saida))
    categorias = _categorias(pagina, QDP)

    (item,) = categorias["so_nucleo"]
    assert set(item) == CAMPOS_ITEM
    assert item["id"] == "item-0001"
    assert item["pagina"] == 1
    assert item["variante"] == QDP
    assert item["classe"] == _classe(QDP)
    assert item["indice_cru"] == 0
    assert item["bbox"] == pytest.approx([110.0, 110.0, 158.0, 158.0], abs=0.01)
    assert {(t["texto"], t["origem"], t["rotacao"]) for t in item["textos"]} >= {
        ("Q", "nativo", 0.0),
        ("DP", "nativo", 0.0),
    }
    assert all(t["texto"] != "ZZ" for t in item["textos"])
    assert item["glifos_lidos"] == []
    assert item["diagnosticos"] == []
    assert item["orientacao"] is False
    assert categorias["so_motor"] == []
    assert categorias["ambos"] == []
    linhas = [linha for linha in _markdown(saida).splitlines() if "item-0001" in linha]
    assert len(linhas) == 1
    assert QDP in linhas[0]
    assert ID_A in linhas[0]


def test_so_no_motor_e_listado(tmp_path: Path) -> None:
    saida = tmp_path / "saida"
    relatorio = _rodar(_uma_folha(tmp_path, _disco_com_linha_que_dobra), saida)
    categorias = _categorias(_pagina(relatorio), DISCO)

    (item,) = categorias["so_motor"]
    assert item["variante"] == DISCO
    assert item["classe"] == _classe(DISCO)
    assert item["indice_cru"] == 2
    assert item["bbox"] == pytest.approx([148.6, 148.6, 151.4, 151.4], abs=0.01)
    assert item["orientacao"] is False
    assert categorias["so_nucleo"] == []
    assert relatorio["total"]["so_motor"] == 1
    assert f"| `{DISCO}` | 1 | 0 |" in _markdown(saida).splitlines()


@pytest.mark.parametrize("rotacao", [90, 270], ids=["90", "270"])
def test_pagina_girada_nao_diverge_nas_invariantes(tmp_path: Path, rotacao: int) -> None:
    pagina = _pagina(_rodar(_uma_folha(tmp_path, _camara, rotacao), tmp_path / "saida"))

    assert pagina["rotacao"] == rotacao
    assert set(pagina["variantes"]) == {CAMARA_CT}
    categorias = _categorias(pagina, CAMARA_CT)
    assert len(categorias["ambos"]) == 1
    for chave in ("so_nucleo", "so_motor", "indice_diverge", "geometria_diverge"):
        assert categorias[chave] == [], chave


@pytest.mark.parametrize(
    ("desenhar", "variante", "rotacao", "orientacao"),
    [
        pytest.param(_triangulo, TRIANGULO, 90, True, id="triangulo-90"),
        pytest.param(_triangulo, TRIANGULO, 180, True, id="triangulo-180"),
        pytest.param(_barra, BARRA, 90, True, id="barra-90"),
        pytest.param(_barra, BARRA, 180, False, id="barra-180-e-excecao"),
    ],
)
def test_orientacao_aparece_como_orientacao(
    tmp_path: Path, desenhar: Desenho, variante: str, rotacao: int, orientacao: bool
) -> None:
    pagina = _pagina(_rodar(_uma_folha(tmp_path, desenhar, rotacao), tmp_path / "saida"))
    categorias = _categorias(pagina, variante)

    divergentes = [*categorias["so_nucleo"], *categorias["so_motor"]]
    if orientacao:
        assert divergentes
        assert all(item["orientacao"] is True for item in divergentes)
    else:
        assert divergentes == []
        assert len(categorias["ambos"]) == 1


def test_orientacao_nao_marca_pagina_em_pe() -> None:
    assert diff.sensivel_a_orientacao("triangle_in_frame", 0) is False
    assert diff.sensivel_a_orientacao("triangle_in_frame", 270) is True
    assert diff.sensivel_a_orientacao("nested_rectangles_bar", 180) is False
    assert diff.sensivel_a_orientacao("label_in_frame", 90) is False


@pytest.mark.parametrize(
    ("rotacao", "esperado"), [(0, False), (90, True), (180, False), (270, True)]
)
def test_disco_terminal_so_e_sensivel_deitado(rotacao: int, esperado: bool) -> None:
    """Emenda de R-E06.2.2.2-2: as faixas do disco só ficam em pé a 0 e 180 graus."""
    assert diff.sensivel_a_orientacao("terminal_disc", rotacao) is esperado


# --- multiconjunto e divergências, na função pura -------------------------------------------


def _observada(variante: str, indice: int, caixa: Sequence[float]) -> diff.Observada:
    x0, y0, x1, y1 = (float(valor) for valor in caixa)
    return diff.Observada(variante=variante, classe="C", indice_cru=indice, bbox=(x0, y0, x1, y1))


def _contagem(comparacao: Any) -> dict[str, int]:
    return {chave: len(valor) for chave, valor in comparacao.items()}


def test_mesma_chave_duas_vezes_e_multiconjunto() -> None:
    caixa = (10.0, 10.0, 20.0, 20.0)
    motor = [_observada("v", 3, caixa), _observada("v", 3, caixa)]
    nucleo = [_observada("v", 3, caixa)]

    comparacao = diff.comparar_observacoes(motor, nucleo)

    assert _contagem(comparacao["v"]) == {
        "ambos": 1,
        "so_motor": 1,
        "so_nucleo": 0,
        "indice_diverge": 0,
        "geometria_diverge": 0,
    }


def test_indice_diferente_com_a_mesma_caixa() -> None:
    caixa = (10.0, 10.0, 20.0, 20.0)
    motor = [_observada("v", 3, caixa)]
    nucleo = [_observada("v", 7, (10.4, 10.0, 20.0, 20.4))]

    comparacao = diff.comparar_observacoes(motor, nucleo)

    assert _contagem(comparacao["v"]) == {
        "ambos": 0,
        "so_motor": 0,
        "so_nucleo": 0,
        "indice_diverge": 1,
        "geometria_diverge": 0,
    }
    (par,) = comparacao["v"]["indice_diverge"]
    assert (par.motor.indice_cru, par.nucleo.indice_cru) == (3, 7)


def test_mesma_chave_com_caixa_longe_e_geometria_diverge() -> None:
    motor = [_observada("v", 3, (10.0, 10.0, 20.0, 20.0))]
    nucleo = [_observada("v", 3, (10.0, 10.0, 20.6, 20.0))]

    comparacao = diff.comparar_observacoes(motor, nucleo)

    assert _contagem(comparacao["v"])["geometria_diverge"] == 1
    assert _contagem(comparacao["v"])["so_motor"] == 0
    assert _contagem(comparacao["v"])["so_nucleo"] == 0


def test_caixa_igual_vence_indice_diferente_na_ordem_das_passadas() -> None:
    """Passada 1 antes da 3: o par de mesma chave e caixa sai em `ambos`, mesmo que outro par de
    índice diferente e mesma caixa apareça antes na lista."""
    caixa = (10.0, 10.0, 20.0, 20.0)
    motor = [_observada("v", 3, caixa)]
    nucleo = [_observada("v", 9, caixa), _observada("v", 3, caixa)]

    contagem = _contagem(diff.comparar_observacoes(motor, nucleo)["v"])

    assert (contagem["ambos"], contagem["indice_diverge"], contagem["so_nucleo"]) == (1, 0, 1)


def test_variantes_diferentes_na_mesma_caixa_nao_casam() -> None:
    caixa = (10.0, 10.0, 20.0, 20.0)
    comparacao = diff.comparar_observacoes([_observada("a", 1, caixa)], [_observada("b", 1, caixa)])

    assert _contagem(comparacao["a"])["so_motor"] == 1
    assert _contagem(comparacao["b"])["so_nucleo"] == 1


# --- falhas -----------------------------------------------------------------------------------


def _shx_falha(monkeypatch: pytest.MonkeyPatch) -> None:
    def falhar(_pagina: Any) -> Any:
        raise RuntimeError("shx")

    monkeypatch.setattr(pymupdf_drawing_model, "_textos_shx", falhar)


def _leitura_de_glifos(monkeypatch: pytest.MonkeyPatch, leitura: LeituraGlifos) -> None:
    monkeypatch.setattr(pymupdf_drawing_model, "ler_texto_glifos", lambda *_a, **_k: leitura)


def test_falha_de_um_lado_nao_vira_so_no_outro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _shx_falha(monkeypatch)

    relatorio = _rodar(_uma_folha(tmp_path, _camara), tmp_path / "saida")
    pagina = _pagina(relatorio)

    assert pagina["situacao"] == "nao_comparada"
    assert "fonte_falhou:modelo.textos_shx_falhou" in pagina["motivo"]
    assert pagina["cobertura"]["nucleo"]["estado"] == "FORA_DOMINIO"
    assert pagina["cobertura"]["motor"]["estado"] == "CONCLUIDO"
    assert pagina["variantes"] == {}
    assert relatorio["total"]["so_motor"] == 0
    assert relatorio["total"]["paginas_comparadas"] == 0
    assert relatorio["total"]["paginas_nao_comparadas"] == 1


def test_excecao_do_motor_nao_derruba_a_rodada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = tmp_path / "corpus"
    pdf = corpus / "folha-quebrada.pdf"
    rodada = _rodada(
        tmp_path,
        [
            (ID_A, pdf.name, _pdf(pdf, _camara)),
            (ID_B, "outra.pdf", _pdf(corpus / "outra.pdf", _camara)),
        ],
    )
    original = diff.observar_pacotes

    def motor(pagina: Any, **kwargs: Any) -> Any:
        if kwargs["documento_id"] == ID_A:
            raise RuntimeError(f"falhou lendo {pdf}\nlinha 2")
        return original(pagina, **kwargs)

    monkeypatch.setattr(diff, "observar_pacotes", motor)

    relatorio = _rodar(rodada, tmp_path / "saida")
    pagina = _pagina(relatorio, ID_A)

    assert pagina["situacao"] == "nao_comparada"
    assert pagina["motivo"].startswith("motor: RuntimeError: falhou lendo <")
    assert "folha-quebrada" not in pagina["motivo"]
    assert "linha 2" not in pagina["motivo"]
    assert pagina["cobertura"]["motor"] is None
    assert _pagina(relatorio, ID_B)["situacao"] == "comparada"
    assert relatorio["total"]["ambos"] == 1


def test_gasto_medido_por_fase(tmp_path: Path) -> None:
    pagina = _pagina(_rodar(_uma_folha(tmp_path, _camara), tmp_path / "saida"))

    gasto = pagina["gasto"]
    assert set(gasto) == {"colagem", "indices", "gramaticas", "total"}
    assert gasto["total"] == gasto["colagem"] + gasto["indices"] + gasto["gramaticas"]
    assert gasto["gramaticas"] > 0
    assert pagina["gasto_motivo"] is None
    assert set(pagina["tempo_s"]) == {"motor", "nucleo", "gasto"}


def test_gasto_nulo_com_motivo_na_fonte_que_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _shx_falha(monkeypatch)

    saida = tmp_path / "saida"
    relatorio = _rodar(_uma_folha(tmp_path, _camara), saida)
    pagina = _pagina(relatorio)

    assert pagina["gasto"] is None
    assert pagina["gasto_motivo"] == "fonte_falhou:modelo.textos_shx_falhou"
    assert relatorio["por_pdf"][ID_A]["gasto_maximo"] is None
    linha = next(linha for linha in _markdown(saida).splitlines() if linha.startswith(f"| {ID_A}"))
    assert "fonte_falhou:modelo.textos_shx_falhou" in linha


def test_gasto_nulo_com_motivo_nos_glifos_limitados(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _leitura_de_glifos(monkeypatch, LeituraGlifos((), 0, 0, limitada=True))

    pagina = _pagina(_rodar(_uma_folha(tmp_path, _camara), tmp_path / "saida"))

    assert pagina["gasto"] is None
    assert pagina["gasto_motivo"] == "glifos_limitados"
    assert pagina["situacao"] == "nao_comparada"
    assert "glifos_limitados" in pagina["motivo"]


def test_glifos_desconhecidos_aparecem_no_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _leitura_de_glifos(monkeypatch, LeituraGlifos((), 1, 0, limitada=False))

    pagina = _pagina(_rodar(_uma_folha(tmp_path, _q_e_dp_com_intruso), tmp_path / "saida"))

    (item,) = _categorias(pagina, QDP)["so_nucleo"]
    assert "modelo.glifos_desconhecidos" in item["diagnosticos"]
    assert pagina["gasto"] is not None


def test_gasto_maximo_da_folha_e_razao_contra_o_limite(tmp_path: Path) -> None:
    saida = tmp_path / "saida"
    relatorio = _rodar(_uma_folha(tmp_path, _camara), saida)
    folha = relatorio["por_pdf"][ID_A]
    gasto = folha["paginas"][0]["gasto"]

    assert folha["gasto_maximo"]["pagina"] == 1
    assert folha["gasto_maximo"]["total"] == gasto["total"]
    assert folha["gasto_maximo"]["razao_limite"] == pytest.approx(
        gasto["total"] / diff.LIMITE_CONSULTAS_PAGINA
    )
    assert relatorio["opcoes"]["limite_consultas_pagina"] == diff.LIMITE_CONSULTAS_PAGINA
    assert relatorio["opcoes"]["limite_medicao"] == 10**12
    assert any(linha.startswith(f"| {ID_A} | 1 |") for linha in _markdown(saida).splitlines())


# --- guardas da rodada ------------------------------------------------------------------------


def _vigiar_pasta_cega(monkeypatch: pytest.MonkeyPatch) -> list[str]:
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
    return acessos


def test_recusa_caminho_cego_na_rodada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "Avaliacao-Cega"
    sha = _pdf(base / "corpus" / "folha.pdf", _camara)
    rodada = _rodada(base, [(ID_A, "folha.pdf", sha)])
    acessos = _vigiar_pasta_cega(monkeypatch)
    saida = tmp_path / "saida"

    with pytest.raises(RodadaError, match="avaliacao-cega"):
        diff.medir_diff(rodada, saida)
    with pytest.raises(SystemExit) as erro:
        diff.main(["--rodada", str(rodada), "--saida", str(saida)])

    assert erro.value.code not in (0, None)
    assert acessos == []
    assert not saida.exists()


def test_recusa_caminho_cego_no_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sha = _pdf(tmp_path / "avaliacao-cega" / "folha.pdf", _camara)
    rodada = _rodada(tmp_path / "fora", [(ID_A, "folha.pdf", sha)], "../../avaliacao-cega")
    acessos = _vigiar_pasta_cega(monkeypatch)

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert "avaliacao-cega" in relatorio["por_pdf"][ID_A]["erro"]
    assert relatorio["total"]["folhas_falha"] == 1
    assert acessos == []


def test_sha_diferente_e_recusado(tmp_path: Path) -> None:
    _pdf(tmp_path / "corpus" / "folha.pdf", _camara)
    rodada = _rodada(tmp_path, [(ID_A, "folha.pdf", "0" * 64)])

    relatorio = _rodar(rodada, tmp_path / "saida")

    assert relatorio["por_pdf"][ID_A]["situacao"] == "falha"
    assert "sha256" in relatorio["por_pdf"][ID_A]["erro"]
    assert relatorio["total"]["paginas_comparadas"] == 0


def test_relatorio_sem_nome_de_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    corpus = tmp_path / "corpus"
    nome = "Projeto Secreto 4711.pdf"
    pdf = corpus / nome
    rodada = _rodada(
        tmp_path,
        [
            (ID_A, nome, _pdf(pdf, _q_e_dp_com_intruso)),
            (ID_B, "sumido-9876.pdf", "0" * 64),
        ],
    )
    original = diff.observar_pacotes_modelo

    def nucleo(pagina: Any, **kwargs: Any) -> Any:
        if kwargs["pagina_numero"] == 1 and kwargs["documento_id"] == ID_A:
            original(pagina, **kwargs)
            raise ValueError(f"erro em {pdf} e em {pdf.as_posix()} ({nome})")
        return original(pagina, **kwargs)

    monkeypatch.setattr(diff, "observar_pacotes_modelo", nucleo)
    saida = tmp_path / "saida"

    _rodar(rodada, saida)
    textos = [
        (saida / "diff-nucleo-motor.json").read_text(encoding="utf-8"),
        _markdown(saida),
    ]

    for texto in textos:
        for proibido in ("Secreto", "4711", "sumido", "9876", str(rodada), rodada.as_posix()):
            assert proibido not in texto
        assert str(tmp_path) not in texto
        assert str(tmp_path).replace("\\", "\\\\") not in texto
        assert tmp_path.as_posix() not in texto


# --- tipo só do modelo (R-E06.3.2-5) ---------------------------------------------------------

_CASO_MOLDURA = next(caso for caso in ENABLED_CASES if caso.variant_id == "cemig-eo-r3-s30-v001")
_HASTE_ID, _HASTE_GRAMATICA = CASOS_HASTE[0]


def _pacotes_com_haste(
    diretorio: Path, *, com_haste: bool
) -> tuple[declarative_symbols.Package, ...]:
    """A família real da moldura, com a variante `stem_bars` sintética quando `com_haste`."""
    real = next(
        pacote
        for pacote in declarative_symbols.carregar_pacotes()
        if any(v["id"] == _CASO_MOLDURA.variant_id for v in pacote["variants"])
    )
    moldura = next(v for v in real["variants"] if v["id"] == _CASO_MOLDURA.variant_id)
    variantes = [copy.deepcopy(moldura)]
    if com_haste:
        haste = copy.deepcopy(moldura)
        haste["id"] = _HASTE_ID
        haste["class_code"] = "ATERRAMENTO"
        haste["recognition"] = {
            "status": "enabled",
            "grammar": copy.deepcopy(_HASTE_GRAMATICA),
            "negative_examples": ["haste com barras fora do padrão"],
        }
        variantes.append(haste)
    diretorio.mkdir(parents=True, exist_ok=True)
    pacote = {**copy.deepcopy(real), "variants": variantes}
    (diretorio / f"{pacote['family_id']}.json").write_text(json.dumps(pacote), encoding="utf-8")
    return declarative_symbols.carregar_pacotes(packages_dir=diretorio)


def _recursos(pacotes: tuple[declarative_symbols.Package, ...]) -> diff.Recursos:
    tabela = carregar_tabela_glifos()
    variantes = declarative_symbols._enabled(pacotes)
    return diff.Recursos(
        pacotes=pacotes,
        variantes=variantes,
        gramaticas={str(v["id"]): str(v["recognition"]["grammar"]["kind"]) for _, v in variantes},
        tabela=tabela,
        perfil_nucleo=perfil_pacotes_modelo(pacotes, tabela),
    )


@pytest.fixture
def com_recursos(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[diff.Recursos], None]]:
    diff.recursos.cache_clear()

    def injetar(meios: diff.Recursos) -> None:
        monkeypatch.setattr(diff, "recursos", lambda: meios)

    yield injetar
    monkeypatch.undo()
    diff.recursos.cache_clear()


def _moldura_e_haste(pagina: pymupdf.Page) -> None:
    draw_symbol(pagina, _CASO_MOLDURA)
    desenhar_positivo(pagina, _HASTE_ID, centro=(240.0, 240.0))


def test_variante_so_do_modelo_fica_fora_da_comparacao_e_dentro_do_gasto(
    tmp_path: Path, com_recursos: Callable[[diff.Recursos], None]
) -> None:
    com = _recursos(_pacotes_com_haste(tmp_path / "com", com_haste=True))
    sem = _recursos(_pacotes_com_haste(tmp_path / "sem", com_haste=False))

    com_recursos(com)
    pagina_com = _pagina(_rodar(_uma_folha(tmp_path / "a", _moldura_e_haste), tmp_path / "saida-a"))
    com_recursos(sem)
    pagina_sem = _pagina(_rodar(_uma_folha(tmp_path / "b", _moldura_e_haste), tmp_path / "saida-b"))

    assert pagina_com["situacao"] == "comparada"
    assert set(pagina_com["variantes"]) == {_CASO_MOLDURA.variant_id}
    moldura = _categorias(pagina_com, _CASO_MOLDURA.variant_id)
    assert len(moldura["ambos"]) == 1
    for categoria in ("so_motor", "so_nucleo", "indice_diverge", "geometria_diverge"):
        assert moldura[categoria] == []
    assert pagina_com["gasto"]["gramaticas"] > pagina_sem["gasto"]["gramaticas"]
    assert pagina_com["variantes"] == pagina_sem["variantes"]
