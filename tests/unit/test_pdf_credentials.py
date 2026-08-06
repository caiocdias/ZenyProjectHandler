from __future__ import annotations

import os
from pathlib import Path

import pytest
from tests.pdf_fixtures import create_protected_pdf

from zeny_project_handler.application.pdf_credentials import (
    IdentidadeCredencialPdf,
    ProvedorCredenciaisPdfMemoria,
    identificar_origem_pdf,
)


def test_memory_provider_is_per_identity_clearable_and_secret_safe(tmp_path: Path) -> None:
    first = create_protected_pdf(tmp_path / "primeiro.pdf", "segredo-a")
    second = create_protected_pdf(tmp_path / "segundo.pdf", "segredo-b")
    first_identity = identificar_origem_pdf(first)
    second_identity = identificar_origem_pdf(second)
    provider = ProvedorCredenciaisPdfMemoria()

    provider.guardar(first_identity, "segredo-a")
    provider.guardar(second_identity, "segredo-b")

    assert provider.obter(first_identity) == "segredo-a"
    assert provider.obter(second_identity) == "segredo-b"
    assert "segredo" not in repr(provider)
    provider.reter({second_identity})
    assert provider.obter(first_identity) is None
    assert provider.obter(second_identity) == "segredo-b"
    provider.limpar()
    assert len(provider) == 0


def test_changed_file_identity_never_reuses_the_previous_password(tmp_path: Path) -> None:
    source = create_protected_pdf(tmp_path / "mutavel.pdf", "segredo")
    original = identificar_origem_pdf(source)
    provider = ProvedorCredenciaisPdfMemoria()
    provider.guardar(original, "segredo")

    status = source.stat()
    os.utime(source, ns=(status.st_atime_ns, status.st_mtime_ns + 1_000_000))
    changed = identificar_origem_pdf(source)

    assert changed != original
    assert not original.ainda_descreve(source)
    assert provider.obter(changed) is None


def test_identity_and_provider_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        IdentidadeCredencialPdf("invalido", 1, 0)
    with pytest.raises(ValueError, match="tamanho"):
        IdentidadeCredencialPdf("0" * 64, 0, 0)
    with pytest.raises(ValueError, match="modificação"):
        IdentidadeCredencialPdf("0" * 64, 1, -1)
    with pytest.raises(ValueError, match="vazia"):
        ProvedorCredenciaisPdfMemoria().guardar(
            IdentidadeCredencialPdf("0" * 64, 1, 0),
            "",
        )
