"""Versão e política de compatibilidade da API pública."""

API_VERSION = "1.3.0"
API_V1_PREFIX = "/api/v1"
MIN_COMPATIBLE_API_VERSION = "1.3.0"
MAX_COMPATIBLE_API_VERSION = "1.999.999"
API_COMPATIBILITY_POLICY = (
    "Compatibilidade é preservada dentro da versão principal v1 pela faixa negociada. Campos "
    "opcionais e operações podem ser adicionados; novos valores fechados ou campos obrigatórios "
    "elevam o piso compatível. Remover, renomear ou mudar a semântica existente de campos, enums "
    "ou rotas exige uma nova versão principal. O cliente deve negociar a faixa informada por "
    "GET /api/v1/session."
)
