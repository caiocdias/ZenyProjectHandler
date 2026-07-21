"""Adaptadores para leitura e renderização de PDFs."""

from .coordinates import PontoPlano, TransformacaoAfin, TransformadorCoordenadasPagina
from .errors import (
    PdfArquivoInvalidoError,
    PdfError,
    PdfOrigemAlteradaError,
    PdfPaginaInvalidaError,
    PdfProtegidoError,
)
from .pymupdf_reader import PyMuPdfReader

__all__ = [
    "PdfArquivoInvalidoError",
    "PdfError",
    "PdfOrigemAlteradaError",
    "PdfPaginaInvalidaError",
    "PdfProtegidoError",
    "PontoPlano",
    "PyMuPdfReader",
    "TransformacaoAfin",
    "TransformadorCoordenadasPagina",
]
