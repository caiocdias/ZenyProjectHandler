# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import math
from pathlib import Path

import pymupdf
import pytest
from ezdxf.filemanagement import readfile
from scripts import drawing_model_dxf
from scripts.drawing_model_dxf import exportar_dxf, main

from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Estilo,
    GrupoCandidato,
    ModeloDesenho,
    PaginaModelo,
    PerfilFamilia,
    Polilinha,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import obter_modelo_desenho


def _pdf_com_camadas(caminho: Path) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=200, height=200)
        rede = documento.add_ocg("P", on=True)
        notas = documento.add_ocg("NOTAS", on=True)
        pagina.draw_line((10, 10), (100, 10), oc=rede)
        pagina.draw_circle((60, 60), 12, oc=rede)
        pagina.insert_text((50, 150), "P1 U3(1)", fontsize=10, fontname="helv", oc=notas)
        documento.save(caminho)
    return caminho


def _estilo(camada: str) -> Estilo:
    return Estilo(camada=camada, cor=None, preenchimento=None, espessura=1.0, tracejado="")


def _modelo(*, camada: str = "", arco: Arco | None = None) -> ModeloDesenho:
    estilo = _estilo(camada)
    primitivas: tuple[Polilinha | Arco, ...] = (
        Polilinha(
            pontos=((0.0, 0.0), (10.0, 0.0), (10.0, 5.0)), fechada=True, estilo=estilo, origens=(0,)
        ),
    )
    if arco is not None:
        primitivas += (arco,)
    texto = TextoModelo(
        texto="X1",
        bbox=(20.0, 30.0, 40.0, 40.0),
        origem="nativo",
        rotacao=0.0,
        altura=8.0,
        fonte="helv",
        camada=camada,
    )
    pagina = PaginaModelo(
        indice=0,
        largura=100.0,
        altura=100.0,
        caminhos=(),
        textos=(texto,),
        primitivas=primitivas,
        grupos=(
            GrupoCandidato(
                bbox=(1.0, 2.0, 30.0, 40.0), indices_primitivas=(0,), indices_caminhos=()
            ),
        ),
        imagens=(),
        diagnosticos=(),
    )
    return ModeloDesenho(
        versao="t",
        documento_sha256="0" * 64,
        familia=PerfilFamilia(familia="x", sinais=(), diagnosticos=()),
        paginas=(pagina,),
    )


def test_dxf_da_fixture_abre_com_ezdxf_e_preserva_camadas_e_textos(tmp_path: Path) -> None:
    pdf = _pdf_com_camadas(tmp_path / "a.pdf")
    destino = tmp_path / "a.dxf"

    exportar_dxf(obter_modelo_desenho(pdf, None), 0, destino)

    doc = readfile(destino)
    assert {"P", "NOTAS"} <= {layer.dxf.name for layer in doc.layers}
    textos = [t for t in doc.modelspace().query("TEXT") if t.dxf.text == "P1 U3(1)"]
    assert len(textos) == 1
    assert textos[0].dxf.layer == "NOTAS"
    assert len(doc.modelspace().query("CIRCLE")) == 1
    circulo = doc.modelspace().query("CIRCLE").first
    assert circulo is not None
    assert circulo.dxf.layer == "P"
    assert circulo.dxf.center.y == pytest.approx(200 - 60, abs=0.5)


def test_y_invertido_e_arco_convertido_para_sentido_anti_horario(tmp_path: Path) -> None:
    arco = Arco(
        centro=(50.0, 60.0), raio=5.0, angulo_inicial=30.0, angulo_final=90.0,
        estilo=_estilo("A"), origens=(1,),
    )  # fmt: skip
    destino = tmp_path / "b.dxf"

    exportar_dxf(_modelo(arco=arco), 0, destino)

    msp = readfile(destino).modelspace()
    dxf_arco = msp.query("ARC").first
    assert dxf_arco is not None
    assert dxf_arco.dxf.center.y == pytest.approx(40.0)
    assert math.isclose(dxf_arco.dxf.start_angle, 270.0)
    assert math.isclose(dxf_arco.dxf.end_angle, 330.0)
    polilinha = msp.query("LWPOLYLINE").first
    assert polilinha is not None
    assert polilinha.closed
    assert [round(p[1]) for p in polilinha.get_points()] == [100, 100, 95]
    texto = msp.query("TEXT").first
    assert texto is not None
    assert texto.dxf.height == pytest.approx(8.0)
    assert texto.dxf.layer == "0"
    grupos = msp.query('LWPOLYLINE[layer=="GRUPOS_CANDIDATOS"]')
    assert len(grupos) == 1
    assert grupos.first is not None
    assert grupos.first.closed


def test_nome_de_camada_invalido_e_saneado(tmp_path: Path) -> None:
    destino = tmp_path / "c.dxf"

    exportar_dxf(_modelo(camada='A/B:C"D<E>'), 0, destino)

    doc = readfile(destino)
    nomes = {layer.dxf.name for layer in doc.layers}
    assert "A_B_C_D_E_" in nomes
    assert doc.modelspace().query("LWPOLYLINE").first.dxf.layer == "A_B_C_D_E_"


def test_exportar_recusa_pagina_inexistente(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="pagina"):
        exportar_dxf(_modelo(), 3, tmp_path / "d.dxf")


def test_cli_grava_dxf_e_recusa_pagina_inexistente(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdf = _pdf_com_camadas(tmp_path / "a.pdf")
    saida = tmp_path / "tmp" / "saida.dxf"
    base = ["--raiz-repositorio", str(tmp_path)]

    assert main([str(pdf), "--saida", str(saida), *base]) == 0
    assert len(readfile(saida).modelspace().query("CIRCLE")) == 1

    saida2 = tmp_path / "tmp" / "outra.dxf"
    assert main([str(pdf), "--saida", str(saida2), "--pagina", "7", *base]) != 0
    assert not saida2.exists()
    assert "pagina" in capsys.readouterr().err


def test_cli_usa_cache_dentro_de_tmp(tmp_path: Path) -> None:
    pdf = _pdf_com_camadas(tmp_path / "a.pdf")
    cache = tmp_path / "tmp" / "cache"

    codigo = main(
        [str(pdf), "--saida", str(tmp_path / "tmp" / "s.dxf"), "--cache", str(cache),
         "--raiz-repositorio", str(tmp_path)]
    )  # fmt: skip

    assert codigo == 0
    assert any(cache.iterdir())


def test_cli_recusa_saida_e_cache_fora_de_tmp(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdf = _pdf_com_camadas(tmp_path / "a.pdf")
    base = ["--raiz-repositorio", str(tmp_path)]

    fora = tmp_path / "fora.dxf"
    assert main([str(pdf), "--saida", str(fora), *base]) != 0
    assert not fora.exists()
    assert "tmp" in capsys.readouterr().err

    escapando = tmp_path / "tmp" / ".." / "escapou.dxf"
    assert main([str(pdf), "--saida", str(escapando), *base]) != 0
    assert not (tmp_path / "escapou.dxf").exists()

    cache_fora = tmp_path / "cache"
    codigo = main(
        [str(pdf), "--saida", str(tmp_path / "tmp" / "s.dxf"), "--cache", str(cache_fora), *base]
    )
    assert codigo != 0
    assert not cache_fora.exists()


def test_cli_com_tabela_de_glifos_indisponivel_sai_com_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _indisponivel(_caminho: Path | None = None) -> object:
        raise ValueError("Tabela de glifos indisponível: sem arquivo.")

    monkeypatch.setattr(drawing_model_dxf, "carregar_tabela_glifos", _indisponivel)
    pdf = _pdf_com_camadas(tmp_path / "a.pdf")
    saida = tmp_path / "tmp" / "saida.dxf"

    codigo = main([str(pdf), "--saida", str(saida), "--raiz-repositorio", str(tmp_path)])

    assert codigo == 2
    assert not saida.exists()
    assert "tabela de glifos" in capsys.readouterr().err.lower()
