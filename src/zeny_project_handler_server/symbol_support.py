"""Expose installed package gaps separately from document observations."""

from zeny_project_handler.adapters.analysis.declarative_symbols import (
    carregar_pacotes,
    perfil_pacotes,
)
from zeny_project_handler_contracts.review import ReviewSymbolSupportDto


def installed_symbol_support() -> tuple[ReviewSymbolSupportDto, ...]:
    packages = carregar_pacotes()
    signature = perfil_pacotes(packages).assinatura()
    return tuple(
        ReviewSymbolSupportDto(
            family_id=package["family_id"],
            package_signature=signature,
            enabled_reference_ids=tuple(
                variant["id"]
                for variant in package["variants"]
                if variant["recognition"]["status"] == "enabled"
            ),
            pending_reference_ids=tuple(
                variant["id"]
                for variant in package["variants"]
                if variant["recognition"]["status"] == "pending"
            ),
            pending_reasons=tuple(
                dict.fromkeys(
                    variant["recognition"]["reason"]
                    for variant in package["variants"]
                    if variant["recognition"]["status"] == "pending"
                )
            ),
        )
        for package in packages
    )
