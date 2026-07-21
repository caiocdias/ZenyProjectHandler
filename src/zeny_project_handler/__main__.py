"""Ponto de entrada para ``python -m zeny_project_handler``."""

from zeny_project_handler.bootstrap import run


def main() -> int:
    """Execute o aplicativo desktop."""
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
