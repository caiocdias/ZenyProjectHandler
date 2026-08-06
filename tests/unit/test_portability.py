from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from tests.path_fixtures import near_windows_path_limit

from zeny_project_handler.adapters.portability import ZipProjectArchive
from zeny_project_handler.application.errors import PortabilidadeProjetoError
from zeny_project_handler.domain.portability import (
    ArquivoPacoteProjeto,
    EstadoIntegridadePacote,
    ManifestoProjetoPortatil,
    OmissaoPacoteProjeto,
    TratamentoOmissaoPacote,
)
from zeny_project_handler.ports.portability import OrigemArquivoPacote


def _origin(path: Path, relative: str = "files/example.pdf") -> OrigemArquivoPacote:
    payload = path.read_bytes()
    return OrigemArquivoPacote(
        arquivo=ArquivoPacoteProjeto(
            caminho_relativo=relative,
            tipo="PDF",
            sha256=sha256(payload).hexdigest(),
            tamanho_bytes=len(payload),
            tipo_mime="application/pdf",
        ),
        caminho_origem=path,
    )


def _manifest(origin: OrigemArquivoPacote) -> ManifestoProjetoPortatil:
    return ManifestoProjetoPortatil(
        versao_formato=1,
        projeto_id=uuid4(),
        catalogo_id=uuid4(),
        nome_projeto="Projeto portátil",
        criado_em=datetime(2026, 7, 21, 20, tzinfo=UTC),
        arquivos=(origin.arquivo,),
    )


def test_zip_package_survives_move_and_reports_tampered_content(tmp_path: Path) -> None:
    source = tmp_path / "example.pdf"
    source.write_bytes(b"%PDF-1.7\nexample")
    origin = _origin(source)
    package = ZipProjectArchive().criar(tmp_path / "project.zphproj", _manifest(origin), (origin,))
    with ZipFile(package) as archive:
        envelope = json.loads(archive.read("manifest.json"))
    assert "graph_signature" not in envelope["manifest"]
    moved = tmp_path / "other-folder" / package.name
    moved.parent.mkdir()
    package.replace(moved)

    extracted = ZipProjectArchive().extrair_validado(moved, tmp_path / "extracted")

    assert extracted.integridade.integro
    assert (
        extracted.diretorio / origin.arquivo.caminho_relativo
    ).read_bytes() == source.read_bytes()

    tampered = tmp_path / "tampered.zphproj"
    with ZipFile(moved) as original, ZipFile(tampered, "w", compression=ZIP_DEFLATED) as changed:
        for item in original.infolist():
            payload = original.read(item.filename)
            if item.filename == origin.arquivo.caminho_relativo:
                payload += b"changed"
            changed.writestr(item.filename, payload)
    result = ZipProjectArchive().extrair_validado(tampered, tmp_path / "tampered-output")
    assert not result.integridade.integro
    assert {item.codigo for item in result.integridade.problemas} == {"HASH_DIVERGENTE"}


def test_format_2_round_trips_degraded_status_and_auditable_omissions(tmp_path: Path) -> None:
    source = tmp_path / "example.pdf"
    source.write_bytes(b"%PDF-1.7\nexample")
    origin = _origin(source)
    project_id = uuid4()
    omitted_document_id = uuid4()
    manifest = ManifestoProjetoPortatil(
        versao_formato=2,
        projeto_id=project_id,
        catalogo_id=uuid4(),
        nome_projeto="Projeto portátil",
        criado_em=datetime(2026, 7, 21, 20, tzinfo=UTC),
        arquivos=(origin.arquivo,),
        estado_integridade=EstadoIntegridadePacote.DEGRADADO,
        omissoes=(
            OmissaoPacoteProjeto(
                codigo="PDF_AUSENTE",
                tipo="PDF",
                referencia_id=omitted_document_id,
                projeto_id=project_id,
                tratamento=TratamentoOmissaoPacote.OMITIDO,
            ),
        ),
    )

    package = ZipProjectArchive().criar(tmp_path / "degraded.zphproj", manifest, (origin,))
    extracted = ZipProjectArchive().extrair_validado(package, tmp_path / "degraded-output")
    with ZipFile(package) as archive:
        raw_manifest = json.loads(archive.read("manifest.json"))["manifest"]

    assert extracted.integridade.integro
    assert extracted.manifesto == manifest
    assert raw_manifest["format_version"] == 2
    assert raw_manifest["integrity"]["status"] == "DEGRADADO"
    assert raw_manifest["integrity"]["omissions"][0]["reference_id"] == str(omitted_document_id)


def test_zip_package_rejects_path_traversal_and_interruption_preserves_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsafe = tmp_path / "unsafe.zphproj"
    with ZipFile(unsafe, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")
    with pytest.raises(PortabilidadeProjetoError, match="insegura"):
        ZipProjectArchive().extrair_validado(unsafe, tmp_path / "unsafe-output")

    source = tmp_path / "example.pdf"
    source.write_bytes(b"%PDF-1.7\nexample")
    origin = _origin(source)
    destination = tmp_path / "stable.zphproj"
    destination.write_bytes(b"last-integral-version")
    monkeypatch.setattr(
        "zeny_project_handler.adapters.portability.zip_archive.os.replace",
        lambda _source, _target: (_ for _ in ()).throw(OSError("interrupted")),
    )

    with pytest.raises(PortabilidadeProjetoError, match="criar o pacote"):
        ZipProjectArchive().criar(destination, _manifest(origin), (origin,))
    assert destination.read_bytes() == b"last-integral-version"
    assert not tuple(tmp_path.glob(".z-*"))


def test_zip_package_uses_short_sibling_temp_near_windows_path_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "example.pdf"
    source.write_bytes(b"%PDF-1.7\nexample")
    origin = _origin(source)
    destination = near_windows_path_limit(tmp_path, "project.zphproj")
    observed: list[Path] = []
    real_replace = os.replace

    def observe_replace(source_path: Path, target_path: Path) -> None:
        observed.append(Path(source_path))
        real_replace(source_path, target_path)

    monkeypatch.setattr(
        "zeny_project_handler.adapters.portability.zip_archive.os.replace",
        observe_replace,
    )

    package = ZipProjectArchive().criar(destination, _manifest(origin), (origin,))

    assert package == destination
    assert destination.is_file()
    assert len(observed) == 1
    assert observed[0].parent == destination.parent
    assert len(observed[0].name) <= 15
    assert len(str(observed[0])) <= len(str(destination))
    assert set(destination.parent.iterdir()) == {destination}
