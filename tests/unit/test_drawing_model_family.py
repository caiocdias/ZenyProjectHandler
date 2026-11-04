"""Perfil por família de produtor."""

from __future__ import annotations

import pytest

from zeny_project_handler.adapters.analysis.drawing_model.family import (
    FAMILIAS,
    LIMIAR_FORMAS_GLIFO,
    ImpressaoEstrutural,
    reconhecer_familia,
)


@pytest.mark.parametrize(
    ("impressao", "familia"),
    [
        (
            ImpressaoEstrutural("Microsoft: Print To PDF", "", (), 0, 400, 0, 0),
            "electric_office_print",
        ),
        (ImpressaoEstrutural("iText 5.5", "", (), 10, 0, 0, 0), "itext"),
        (ImpressaoEstrutural("GPL Ghostscript 9.5", "", (), 10, 0, 0, 0), "ghostscript"),
        (ImpressaoEstrutural("AutoCAD PDF (General).pc3", "", (), 0, 0, 0, 0), "autocad"),
        (ImpressaoEstrutural("LibreOffice", "", (), 10, 0, 0, 0), "generico"),
    ],
)
def test_reconhece_cada_familia(impressao: ImpressaoEstrutural, familia: str) -> None:
    perfil = reconhecer_familia(impressao)
    assert perfil.familia == familia
    assert perfil.familia in FAMILIAS


def test_pdfplot_no_criador_sem_diferenciar_maiusculas() -> None:
    assert reconhecer_familia(ImpressaoEstrutural("x", "PdfPlot", (), 0, 0, 0, 0)).familia == (
        "autocad"
    )


def test_print_to_pdf_sem_glifos_cai_no_generico_com_diagnostico() -> None:
    impressao = ImpressaoEstrutural("Print to PDF", "", (), 0, LIMIAR_FORMAS_GLIFO - 1, 0, 0)
    perfil = reconhecer_familia(impressao)
    assert perfil.familia == "generico"
    assert "familia.print_to_pdf_sem_glifos" in perfil.diagnosticos


def test_familia_desconhecida_cai_no_generico_com_diagnostico() -> None:
    perfil = reconhecer_familia(ImpressaoEstrutural("LibreOffice", "", (), 10, 0, 0, 0))
    assert perfil.familia == "generico" and "familia.desconhecida" in perfil.diagnosticos


def test_ocg_ou_shx_identifica_autocad_mesmo_com_outro_produtor() -> None:
    com_ocg = ImpressaoEstrutural("iText", "", ("Camada",), 0, 0, 0, 0)
    com_shx = ImpressaoEstrutural("Ghostscript", "", (), 0, 0, 2, 0)
    assert reconhecer_familia(com_ocg).familia == "autocad"
    assert reconhecer_familia(com_shx).familia == "autocad"


def test_sinais_nao_trazem_produtor_bruto() -> None:
    impressao = ImpressaoEstrutural(
        "C:/Users/fulano/gerador.exe", "Projeto Sigiloso", (), 1, 2, 3, 4
    )
    sinais = dict(reconhecer_familia(impressao).sinais)
    assert set(sinais) == {
        "ocgs",
        "spans_texto_nativo",
        "formas_glifo",
        "anotacoes_shx",
        "imagens",
        "produtor_itext",
        "produtor_ghostscript",
        "produtor_print_to_pdf",
        "produtor_autocad",
    }
    texto = repr(sinais)
    assert "fulano" not in texto and "Sigiloso" not in texto
