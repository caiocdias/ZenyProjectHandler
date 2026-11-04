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


def test_print_to_pdf_no_limiar_exato_de_glifos_e_electric_office_print() -> None:
    no_limiar = ImpressaoEstrutural("Microsoft: Print To PDF", "", (), 0, LIMIAR_FORMAS_GLIFO, 0, 0)
    abaixo = ImpressaoEstrutural(
        "Microsoft: Print To PDF", "", (), 0, LIMIAR_FORMAS_GLIFO - 1, 0, 0
    )
    assert reconhecer_familia(no_limiar).familia == "electric_office_print"
    assert reconhecer_familia(no_limiar).diagnosticos == ()
    assert reconhecer_familia(abaixo).familia == "generico"


def test_print_to_pdf_com_glifos_mas_com_ocg_e_autocad() -> None:
    impressao = ImpressaoEstrutural("Print To PDF", "", ("L1",), 0, 500, 0, 0)
    assert reconhecer_familia(impressao).familia == "autocad"


def test_itext_e_ghostscript_vencem_print_to_pdf() -> None:
    itext = ImpressaoEstrutural("iText Print To PDF", "", (), 0, 900, 0, 0)
    gs = ImpressaoEstrutural("Ghostscript Print To PDF", "", (), 0, 900, 0, 0)
    assert reconhecer_familia(itext).familia == "itext"
    assert reconhecer_familia(gs).familia == "ghostscript"


def test_itext_ghostscript_e_print_to_pdf_ignoram_maiusculas() -> None:
    assert reconhecer_familia(ImpressaoEstrutural("ITEXT 7", "", (), 0, 0, 0, 0)).familia == "itext"
    gs = ImpressaoEstrutural("GHOSTSCRIPT", "", (), 0, 0, 0, 0)
    assert reconhecer_familia(gs).familia == "ghostscript"
    ptp = ImpressaoEstrutural("PRINT TO PDF", "", (), 0, 300, 0, 0)
    assert reconhecer_familia(ptp).familia == "electric_office_print"


def test_itext_so_no_criador_nao_identifica_itext() -> None:
    perfil = reconhecer_familia(ImpressaoEstrutural("", "iText", (), 0, 0, 0, 0))
    assert perfil.familia == "generico" and "familia.desconhecida" in perfil.diagnosticos


def test_produtor_vazio_e_generico_desconhecido_sem_sinais_de_produtor() -> None:
    perfil = reconhecer_familia(ImpressaoEstrutural("", "", (), 0, 0, 0, 0))
    sinais = dict(perfil.sinais)
    assert perfil.familia == "generico"
    assert perfil.diagnosticos == ("familia.desconhecida",)
    assert not any(sinais[k] for k in sinais if k.startswith("produtor_"))


def test_autocad_no_criador_vence_produtor_ghostscript() -> None:
    impressao = ImpressaoEstrutural("GPL Ghostscript", "AutoCAD 2020", (), 0, 0, 0, 0)
    perfil = reconhecer_familia(impressao)
    assert perfil.familia == "autocad"
    assert perfil.diagnosticos == ()
    assert dict(perfil.sinais)["produtor_ghostscript"] is True


def test_sinais_numericos_refletem_contagens_e_nomes_ocg_nao_vazam() -> None:
    impressao = ImpressaoEstrutural(
        "C:\\segredo\\x.exe", "", ("C:\\camada-secreta", "Outra"), 7, 8, 0, 9
    )
    perfil = reconhecer_familia(impressao)
    sinais = dict(perfil.sinais)
    assert (sinais["ocgs"], sinais["spans_texto_nativo"], sinais["formas_glifo"]) == (2, 7, 8)
    assert sinais["imagens"] == 9
    assert "segredo" not in repr(perfil) and "camada-secreta" not in repr(perfil)


def test_reconhecimento_e_deterministico() -> None:
    impressao = ImpressaoEstrutural("LibreOffice", "", (), 10, 0, 0, 0)
    assert reconhecer_familia(impressao) == reconhecer_familia(impressao)
