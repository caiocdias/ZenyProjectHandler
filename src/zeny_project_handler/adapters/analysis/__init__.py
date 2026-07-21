"""Adaptadores de análise de documentos."""

from .json_cache import JsonAnalysisCache
from .pymupdf_analyzer import PyMuPdfDocumentAnalyzer

__all__ = ["JsonAnalysisCache", "PyMuPdfDocumentAnalyzer"]
