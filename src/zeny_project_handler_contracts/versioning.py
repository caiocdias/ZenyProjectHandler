"""Versão e política de compatibilidade da API pública."""

API_VERSION = "1.2.0"
API_V1_PREFIX = "/api/v1"
MIN_COMPATIBLE_API_VERSION = "1.0.0"
MAX_COMPATIBLE_API_VERSION = "1.999.999"
API_COMPATIBILITY_POLICY = (
    "Compatibilidade é preservada dentro da versão principal v1. Campos opcionais e operações "
    "podem ser adicionados; remover, renomear ou mudar a semântica de campos, enums ou rotas exige "
    "uma nova versão principal. O cliente deve negociar a faixa informada por GET /api/v1/session."
)
