"""CLI usada pelo setup para provisionar o idioma português do Tesseract."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from zeny_project_handler.adapters.analysis.tesseract_runtime import (
    inspect_tesseract_runtime,
    provision_portuguese_language,
)
from zeny_project_handler.config import AppSettings


def main(argv: Sequence[str] | None = None) -> int:
    """Valide ou provisione ``por`` e retorne falha quando ele não estiver utilizável."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provision",
        action="store_true",
        help="baixe o por.traineddata oficial quando ele ainda não estiver disponível",
    )
    arguments = parser.parse_args(argv)
    settings = AppSettings.from_environment()
    runtime = (
        provision_portuguese_language(settings.data_directory)
        if arguments.provision
        else inspect_tesseract_runtime(settings.data_directory)
    )
    if runtime.portugues_pronto:
        selected = "+".join(runtime.idiomas_selecionados)
        print("OCR português confirmado por tesseract --list-langs.")
        print(f"Idiomas selecionados pelo aplicativo: {selected}.")
        return 0

    diagnostic = runtime.diagnostico
    if diagnostic is None:
        print("ERRO: o OCR em português não pôde ser validado.")
    else:
        print(f"ERRO [{diagnostic.codigo}]: {diagnostic.mensagem}")
        print(f"REMEDIAÇÃO: {diagnostic.remediacao}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
