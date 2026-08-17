"""Entry point do worker único Uvicorn."""

from __future__ import annotations

import uvicorn

from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.config import ServerSettings


def main() -> int:
    """Valide a configuração antes de abrir o socket do servidor."""
    settings = ServerSettings.from_environment()
    application = create_app(settings)
    uvicorn.run(
        application,
        host=settings.host,
        port=settings.port,
        workers=1,
        access_log=False,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
