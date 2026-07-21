"""Erros explícitos das regras de domínio."""


class DomainValidationError(ValueError):
    """Indica que uma entidade ou relação viola uma invariante do domínio."""
