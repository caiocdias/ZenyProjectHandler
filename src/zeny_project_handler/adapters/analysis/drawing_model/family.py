"""Perfil por família de produtor do PDF, a partir de sinais estruturais já extraídos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from zeny_project_handler.adapters.analysis.drawing_model.model import PerfilFamilia

FAMILIAS: Final = ("electric_office_print", "itext", "ghostscript", "autocad", "generico")
LIMIAR_FORMAS_GLIFO: Final = 300


@dataclass(frozen=True, slots=True)
class ImpressaoEstrutural:
    produtor: str
    criador: str
    nomes_ocg: tuple[str, ...]
    spans_texto_nativo: int
    formas_glifo: int
    anotacoes_shx: int
    imagens: int


def reconhecer_familia(impressao: ImpressaoEstrutural) -> PerfilFamilia:
    produtor = impressao.produtor.lower()
    criador = impressao.criador.lower()
    autocad = (
        any(marca in texto for texto in (produtor, criador) for marca in ("pdfplot", "autocad"))
        or impressao.anotacoes_shx > 0
        or len(impressao.nomes_ocg) > 0
    )
    print_to_pdf = "print to pdf" in produtor
    sinais = (
        ("ocgs", len(impressao.nomes_ocg)),
        ("spans_texto_nativo", impressao.spans_texto_nativo),
        ("formas_glifo", impressao.formas_glifo),
        ("anotacoes_shx", impressao.anotacoes_shx),
        ("imagens", impressao.imagens),
        ("produtor_itext", "itext" in produtor),
        ("produtor_ghostscript", "ghostscript" in produtor),
        ("produtor_print_to_pdf", print_to_pdf),
        ("produtor_autocad", autocad),
    )
    if autocad:
        return PerfilFamilia("autocad", sinais, ())
    if "itext" in produtor:
        return PerfilFamilia("itext", sinais, ())
    if "ghostscript" in produtor:
        return PerfilFamilia("ghostscript", sinais, ())
    if print_to_pdf:
        if impressao.formas_glifo >= LIMIAR_FORMAS_GLIFO:
            return PerfilFamilia("electric_office_print", sinais, ())
        return PerfilFamilia("generico", sinais, ("familia.print_to_pdf_sem_glifos",))
    return PerfilFamilia("generico", sinais, ("familia.desconhecida",))
