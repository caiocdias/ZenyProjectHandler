# mypy: disable-error-code="no-untyped-call"
"""Ataque aos métodos ``pacotes`` e ``modelo`` do benchmark de símbolos (E06.2.2.2, Task 2).

Cobre falha de folha com várias páginas, os sete estados de cobertura, a recusa de folha sem
variante, o limite lido na chamada, página girada com CropBox, saneamento do erro e a
imutabilidade do método ``atual``.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any, Final

import pymupdf
import pytest
import scripts.benchmark_simbolos_ficha as bench
import scripts.simbolos_ficha_metricas as metricas

from zeny_project_handler.adapters.analysis import declarative_symbols, model_symbols
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos

_MOLDURA_CT: Final = (101.0, 115.0, 169.0, 149.0)
_TOLERANCIA: Final = 0.005
_METODOS: Final = ("pacotes", "modelo")
_RAIZ: Final = Path(__file__).resolve().parents[2]

# (módulo, atributo) do observador de cada método, para trocar por um que devolve cobertura falsa.
_OBSERVADORES: Final = {
    "pacotes": (declarative_symbols, "observar_pacotes"),
    "modelo": (model_symbols, "observar_pacotes_modelo"),
}


def _desenhar_ct(pagina: pymupdf.Page) -> None:
    pagina.draw_rect(pymupdf.Rect(_MOLDURA_CT), color=(0, 0, 0), width=1)
    pagina.insert_text((_MOLDURA_CT[0] + 6, _MOLDURA_CT[1] + 25), "CT", fontsize=11)


def _pdf_paginas(caminho: Path, *, com_ct: tuple[bool, ...]) -> Path:
    with pymupdf.open() as documento:
        for desenhar in com_ct:
            pagina = documento.new_page(width=300, height=300)
            if desenhar:
                _desenhar_ct(pagina)
        documento.save(caminho)
    return caminho


def _pdf_girado(caminho: Path, rotacao: int, recorte: pymupdf.Rect | None) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        _desenhar_ct(pagina)
        if recorte is not None:
            pagina.set_cropbox(recorte)
        pagina.set_rotation(rotacao)
        documento.save(caminho)
    return caminho


def _referencia() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": "0" * 64,
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [],
        "vaos": [],
    }


def _medir(pdf: Path, nome: str) -> dict[str, Any]:
    registro = bench.medir_pdf(pdf, _referencia(), "pdf-1", [nome], classes_avaliadas=["CAMARA"])
    bloco: dict[str, Any] = registro["metodos"][nome]
    return bloco


def _com_estado(
    monkeypatch: pytest.MonkeyPatch,
    nome: str,
    estado: EstadoMetodoSimbolos,
    motivo: str | None,
    *,
    paginas: tuple[int, ...] = (1,),
) -> None:
    """Troca a cobertura das páginas ``paginas`` (1-based) pela do estado, mantendo o resto real."""
    modulo, atributo = _OBSERVADORES[nome]
    original = getattr(modulo, atributo)

    def observar(pagina: Any, **kwargs: Any) -> Any:
        resultado = original(pagina, **kwargs)
        if kwargs["pagina_numero"] not in paginas:
            return resultado
        cobertura = dataclasses.replace(resultado.coberturas[0], estado=estado, motivo=motivo)
        return dataclasses.replace(resultado, coberturas=(cobertura,))

    monkeypatch.setattr(modulo, atributo, observar)


# --- uma página falha: a folha inteira é falha do método ----------------------------------


@pytest.mark.parametrize("nome", _METODOS)
def test_pagina_que_falha_derruba_a_folha_inteira_do_metodo(
    nome: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_paginas(tmp_path / "tres.pdf", com_ct=(True, False, True))
    _com_estado(monkeypatch, nome, EstadoMetodoSimbolos.FALHA, "fonte_falhou:x", paginas=(2,))
    resultado = bench.METODOS[nome](pdf, "pdf-1")
    assert resultado["falha"] is not None
    assert "página 2" in resultado["falha"]
    # A página 1 tinha símbolo: a folha não pode virar uma lista parcial de predições.
    assert resultado["predicoes"] == []
    bloco = _medir(pdf, nome)
    assert bloco["situacao"] == "falha"
    assert "comparacao" not in bloco
    assert "centro" not in bloco


@pytest.mark.parametrize("nome", _METODOS)
def test_folha_com_pagina_falha_fica_fora_dos_totais_e_da_comparacao(
    nome: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boa = _pdf_paginas(tmp_path / "boa.pdf", com_ct=(True,))
    ruim = _pdf_paginas(tmp_path / "ruim.pdf", com_ct=(True, False))
    registro_boa = bench.medir_pdf(boa, _referencia(), "a", [nome], classes_avaliadas=["CAMARA"])
    modulo, atributo = _OBSERVADORES[nome]
    original = getattr(modulo, atributo)

    def observar(pagina: Any, **kwargs: Any) -> Any:
        resultado = original(pagina, **kwargs)
        if kwargs["documento_id"] != "b" or kwargs["pagina_numero"] != 2:
            return resultado
        cobertura = dataclasses.replace(
            resultado.coberturas[0], estado=EstadoMetodoSimbolos.FALHA, motivo="quebrou"
        )
        return dataclasses.replace(resultado, coberturas=(cobertura,))

    monkeypatch.setattr(modulo, atributo, observar)
    registro_ruim = bench.medir_pdf(ruim, _referencia(), "b", [nome], classes_avaliadas=["CAMARA"])
    por_pdf = {"a": registro_boa, "b": registro_ruim}
    total = metricas._agregar_total(por_pdf, (nome,))[nome]
    assert total["folhas_medidas"] == 1
    assert total["folhas_com_falha"] == 1
    assert metricas._agregar_comparacao(por_pdf, (nome,))["folhas"] == ["a"]


# --- os sete estados de cobertura ---------------------------------------------------------

_ESTADOS: Final = [
    pytest.param(EstadoMetodoSimbolos.CONCLUIDO, False, id="CONCLUIDO"),
    pytest.param(EstadoMetodoSimbolos.NAO_DETECCAO, False, id="NAO_DETECCAO"),
    pytest.param(EstadoMetodoSimbolos.DESCONHECIDO, True, id="DESCONHECIDO"),
    pytest.param(EstadoMetodoSimbolos.ABSTENCAO, True, id="ABSTENCAO"),
    pytest.param(EstadoMetodoSimbolos.FORA_DOMINIO, True, id="FORA_DOMINIO"),
    pytest.param(EstadoMetodoSimbolos.INDISPONIVEL, True, id="INDISPONIVEL"),
    pytest.param(EstadoMetodoSimbolos.FALHA, True, id="FALHA"),
]


def test_os_sete_estados_estao_cobertos_pelo_parametrize() -> None:
    cobertos = {parametro.values[0] for parametro in _ESTADOS}
    assert cobertos == set(EstadoMetodoSimbolos)


@pytest.mark.parametrize("nome", _METODOS)
@pytest.mark.parametrize(("estado", "e_falha"), _ESTADOS)
def test_so_concluido_e_nao_deteccao_deixam_de_ser_falha(
    nome: str,
    estado: EstadoMetodoSimbolos,
    e_falha: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = _pdf_paginas(tmp_path / "vazio.pdf", com_ct=(False,))
    _com_estado(monkeypatch, nome, estado, "motivo-do-estado")
    resultado = bench.METODOS[nome](pdf, "pdf-1")
    assert (resultado["falha"] is not None) is e_falha
    if e_falha:
        assert "motivo-do-estado" in str(resultado["falha"])
        assert resultado["predicoes"] == []


@pytest.mark.parametrize("nome", _METODOS)
def test_nao_deteccao_real_mede_como_zero_predicoes_e_nao_como_falha(
    nome: str, tmp_path: Path
) -> None:
    bloco = _medir(_pdf_paginas(tmp_path / "vazio.pdf", com_ct=(False,)), nome)
    assert bloco["situacao"] == "ok"
    assert "centro" in bloco


@pytest.mark.parametrize("nome", _METODOS)
def test_folha_sem_variante_habilitada_e_falha_com_o_motivo(
    nome: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(declarative_symbols, "carregar_pacotes", lambda *_, **__: ())
    pdf = _pdf_paginas(tmp_path / "ct.pdf", com_ct=(True,))
    bloco = _medir(pdf, nome)
    assert bloco["situacao"] == "falha"
    assert "Nenhuma variante" in bloco["erro"]
    assert "comparacao" not in bloco


# --- LIMITE_MODELO é lido na chamada; perfil e observação usam o mesmo -------------------


def test_limite_do_modelo_e_lido_na_chamada_e_igual_no_perfil_e_na_observacao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vistos: list[tuple[str, int]] = []
    perfil_original = model_symbols.perfil_pacotes_modelo
    observar_original = model_symbols.observar_pacotes_modelo

    def perfil(*args: Any, **kwargs: Any) -> Any:
        vistos.append(("perfil", kwargs["limite"]))
        return perfil_original(*args, **kwargs)

    def observar(*args: Any, **kwargs: Any) -> Any:
        vistos.append(("observacao", kwargs["limite"]))
        return observar_original(*args, **kwargs)

    monkeypatch.setattr(model_symbols, "perfil_pacotes_modelo", perfil)
    monkeypatch.setattr(model_symbols, "observar_pacotes_modelo", observar)
    monkeypatch.setattr(bench, "LIMITE_MODELO", 777_777)
    pdf = _pdf_paginas(tmp_path / "duas.pdf", com_ct=(True, True))
    resultado = bench.METODOS["modelo"](pdf, "pdf-1")
    assert resultado["falha"] is None
    assert vistos
    assert {limite for _, limite in vistos} == {777_777}
    assert {tipo for tipo, _ in vistos} == {"perfil", "observacao"}


def test_assinatura_do_modelo_acompanha_o_limite_vigente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bench, "LIMITE_MODELO", 123)
    assert bench.ASSINATURAS["modelo"]()["parametros"]["limite_consultas"] == "123"


def test_assinatura_gravada_na_folha_traz_o_limite_vigente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bench, "LIMITE_MODELO", 321)
    pdf = _pdf_paginas(tmp_path / "ct.pdf", com_ct=(True,))
    assert bench.ASSINATURAS["modelo"]()["assinatura"] == next(
        iter(bench.METODOS["modelo"](pdf, "pdf-1")["assinatura"].values())
    )


# --- página girada e CropBox -------------------------------------------------------------

_RECORTES: Final = [
    pytest.param(None, id="sem-cropbox"),
    pytest.param(pymupdf.Rect(60, 70, 290, 280), id="cropbox"),
]


@pytest.mark.parametrize("recorte", _RECORTES)
@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
def test_bbox_normalizada_coincide_entre_pacotes_e_modelo_com_rotacao_e_cropbox(
    rotacao: int, recorte: pymupdf.Rect | None, tmp_path: Path
) -> None:
    pdf = _pdf_girado(tmp_path / "girado.pdf", rotacao, recorte)
    pacotes = bench.METODOS["pacotes"](pdf, "pdf-1")
    modelo = bench.METODOS["modelo"](pdf, "pdf-1")
    assert pacotes["falha"] is None
    assert modelo["falha"] is None
    ct_pacotes = [p for p in pacotes["predicoes"] if p["classe"] == "CAMARA"]
    ct_modelo = [p for p in modelo["predicoes"] if p["classe"] == "CAMARA"]
    assert len(ct_pacotes) == 1
    assert len(ct_modelo) == 1
    for a, b in zip(ct_pacotes[0]["bbox"], ct_modelo[0]["bbox"], strict=True):
        assert abs(a - b) < _TOLERANCIA
    assert all(0.0 <= v <= 1.0 for v in ct_modelo[0]["bbox"])


@pytest.mark.parametrize("nome", _METODOS)
@pytest.mark.parametrize("recorte", _RECORTES)
@pytest.mark.parametrize("rotacao", [0, 90, 180, 270])
def test_bbox_normalizada_e_a_moldura_vista_na_pagina_girada(
    nome: str, rotacao: int, recorte: pymupdf.Rect | None, tmp_path: Path
) -> None:
    pdf = _pdf_girado(tmp_path / "girado.pdf", rotacao, recorte)
    with pymupdf.open(pdf) as documento:
        pagina = documento[0]
        moldura = pymupdf.Rect(_MOLDURA_CT)
        if recorte is not None:
            moldura = moldura - (recorte.x0, recorte.y0, recorte.x0, recorte.y0)
        visual = moldura * pagina.rotation_matrix
        largura, altura = pagina.rect.width, pagina.rect.height
    esperado = [visual.x0 / largura, visual.y0 / altura, visual.x1 / largura, visual.y1 / altura]
    resultado = bench.METODOS[nome](pdf, "pdf-1")
    previstas = [p for p in resultado["predicoes"] if p["classe"] == "CAMARA"]
    assert len(previstas) == 1
    for obtido, certo in zip(previstas[0]["bbox"], esperado, strict=True):
        assert abs(obtido - certo) < _TOLERANCIA


# --- o erro de falha é saneado -----------------------------------------------------------


@pytest.mark.parametrize("nome", _METODOS)
def test_motivo_de_cobertura_com_caminho_e_nome_de_pdf_sai_saneado(
    nome: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasta = tmp_path / "pasta com espaco"
    pasta.mkdir()
    pdf = _pdf_paginas(pasta / "projeto secreto.pdf", com_ct=(True,))
    _com_estado(
        monkeypatch, nome, EstadoMetodoSimbolos.FALHA, f"leitura de {pdf} falhou em {pdf.name}"
    )
    erro = _medir(pdf, nome)["erro"]
    assert str(tmp_path) not in erro
    assert tmp_path.as_posix() not in erro
    assert "secreto" not in erro
    assert ".pdf" not in erro.lower()


@pytest.mark.parametrize("nome", _METODOS)
def test_excecao_do_observador_com_caminho_sai_saneada(
    nome: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf_paginas(tmp_path / "projeto secreto.pdf", com_ct=(True,))
    modulo, atributo = _OBSERVADORES[nome]

    def quebrar(*_: Any, **__: Any) -> Any:
        raise RuntimeError(f"abrir {pdf} deu erro\n  linha dois {pdf}")

    monkeypatch.setattr(modulo, atributo, quebrar)
    bloco = _medir(pdf, nome)
    assert bloco["situacao"] == "falha"
    assert str(tmp_path) not in bloco["erro"]
    assert "secreto" not in bloco["erro"]
    assert "\n" not in bloco["erro"]


# --- o método atual não mudou ------------------------------------------------------------


def _carregar_modulo_antigo(destino: Path) -> Any:
    fonte = subprocess.run(
        ["git", "-C", str(_RAIZ), "show", "c0f0432:scripts/benchmark_simbolos_ficha.py"],
        check=True,
        capture_output=True,
    ).stdout
    arquivo = destino / "benchmark_simbolos_ficha_antigo.py"
    arquivo.write_bytes(fonte)
    spec = importlib.util.spec_from_file_location("benchmark_simbolos_ficha_antigo", arquivo)
    assert spec is not None
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    try:
        spec.loader.exec_module(modulo)
    except BaseException:
        sys.modules.pop(spec.name, None)
        raise
    return modulo


def test_metodo_atual_tem_a_mesma_saida_e_assinatura_de_antes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    antigo = _carregar_modulo_antigo(tmp_path)
    monkeypatch.setitem(sys.modules, "benchmark_simbolos_ficha_antigo", antigo)
    pdf = tmp_path / "folha.pdf"
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        _desenhar_ct(pagina)
        pagina.draw_line((200, 60), (215, 60), color=(0, 0, 0))
        for indice, comprimento in enumerate((10, 7, 4)):
            x = 215 + indice * 4
            pagina.draw_line((x, 60 - comprimento / 2), (x, 60 + comprimento / 2))
        documento.new_page(width=300, height=300)
        documento.save(pdf)
    depois = bench.METODOS["atual"](pdf, "pdf-1")
    antes = antigo.METODOS["atual"](pdf, "pdf-1")
    assert depois["predicoes"]
    assert depois == antes
    assert bench.ASSINATURAS["atual"]() == antigo.ASSINATURAS["atual"]()
    assert set(antigo.METODOS) == {"atual"}


# --- pacotes e modelo na CLI e no relatório ----------------------------------------------


def test_assinaturas_dos_metodos_novos_sao_registros_json_puros() -> None:
    import json

    for nome in _METODOS:
        assinatura = bench.ASSINATURAS[nome]()
        assert json.loads(json.dumps(assinatura)) == assinatura
        assert assinatura["assinatura"]
