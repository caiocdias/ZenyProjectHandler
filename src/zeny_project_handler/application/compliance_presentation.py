"""API estável para os textos de conformidade compilados no servidor."""

from .compliance_presentation_core import (
    formatar_alvo,
    formatar_escopo,
    formatar_lista_condicoes,
    formatar_texto_achado,
    formatar_valores_achado,
)

__all__ = [
    "formatar_alvo",
    "formatar_escopo",
    "formatar_lista_condicoes",
    "formatar_texto_achado",
    "formatar_valores_achado",
]
