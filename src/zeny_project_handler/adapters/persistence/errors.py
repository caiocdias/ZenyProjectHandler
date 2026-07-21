"""Erros estáveis expostos pelo adaptador de persistência."""


class PersistenceError(RuntimeError):
    """Erro base de armazenamento local."""


class PersistenceConflictError(PersistenceError):
    """A operação violaria imutabilidade ou concorrência esperada."""


class PersistenceNotFoundError(PersistenceError):
    """A entidade solicitada não existe no armazenamento."""


class DomainCodecError(PersistenceError):
    """O payload persistido não representa um tipo de domínio permitido."""
