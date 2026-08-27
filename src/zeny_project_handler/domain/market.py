"""Classificação canônica do mercado atendido por uma Nota de Serviço."""

from enum import StrEnum


class Mercado(StrEnum):
    """Únicos mercados aceitos do cadastro externo de Notas de Serviço."""

    RURAL = "RURAL"
    URBANO = "URBANO"
