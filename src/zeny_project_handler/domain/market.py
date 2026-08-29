"""Valores canônicos do cadastro operacional externo."""

from enum import StrEnum


class Mercado(StrEnum):
    """Únicos mercados aceitos do cadastro externo de Notas de Serviço."""

    RURAL = "RURAL"
    URBANO = "URBANO"


class DescricaoAcao(StrEnum):
    """Descrições exatas de ações cuja conclusão pode ser consultada."""

    AVALIAR_IMPACTO_AMBIENTAL = "AVALIAR IMPACTO AMBIENTAL"
    FALTA_SERVIDAO = "FALTA SERVIDÃO"
