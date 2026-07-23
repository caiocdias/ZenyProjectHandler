"""Pacote ZIP validado, sem extração de caminhos inseguros."""

from __future__ import annotations

import json
import os
import stat
from contextlib import suppress
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from zeny_project_handler.application.errors import PortabilidadeProjetoError
from zeny_project_handler.domain.portability import (
    ArquivoPacoteProjeto,
    ManifestoProjetoPortatil,
    ProblemaIntegridadeProjeto,
    RelatorioIntegridadeProjeto,
)
from zeny_project_handler.ports.portability import (
    OrigemArquivoPacote,
    PacoteProjetoExtraido,
)

_MANIFEST_PATH = "manifest.json"


class ZipProjectArchive:
    def criar(
        self,
        destino: Path,
        manifesto: ManifestoProjetoPortatil,
        origens: tuple[OrigemArquivoPacote, ...],
    ) -> Path:
        target = destino.expanduser().resolve()
        source_by_name = {item.arquivo.caminho_relativo: item for item in origens}
        expected = {item.caminho_relativo for item in manifesto.arquivos}
        if set(source_by_name) != expected:
            raise PortabilidadeProjetoError("As origens não correspondem ao manifesto do pacote")
        for item in origens:
            _validate_source(item)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
                archive.writestr(_MANIFEST_PATH, _manifest_envelope(manifesto))
                for item in sorted(origens, key=lambda entry: entry.arquivo.caminho_relativo):
                    archive.write(item.caminho_origem, item.arquivo.caminho_relativo)
            os.replace(temporary, target)
        except (OSError, BadZipFile) as error:
            raise PortabilidadeProjetoError("Não foi possível criar o pacote") from error
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
        return target

    def extrair_validado(self, pacote: Path, destino: Path) -> PacoteProjetoExtraido:
        package_path = pacote.expanduser().resolve()
        target = destino.expanduser().resolve()
        if not package_path.is_file():
            raise PortabilidadeProjetoError("Pacote informado não existe")
        target.mkdir(parents=True, exist_ok=True)
        try:
            with ZipFile(package_path) as archive:
                members = archive.infolist()
                _validate_members(members)
                try:
                    envelope = cast(dict[str, Any], json.loads(archive.read(_MANIFEST_PATH)))
                except (KeyError, ValueError, TypeError) as error:
                    raise PortabilidadeProjetoError("Manifesto do pacote é inválido") from error
                manifesto = _manifest_from_envelope(envelope)
                problems = _member_problems(members, manifesto)
                for member in members:
                    if member.filename == _MANIFEST_PATH or member.is_dir():
                        continue
                    destination = target / PurePosixPath(member.filename)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as source, destination.open("wb") as output:
                        while chunk := source.read(1024 * 1024):
                            output.write(chunk)
        except BadZipFile as error:
            raise PortabilidadeProjetoError("Arquivo não é um pacote ZIP válido") from error
        problems.extend(_extracted_problems(target, manifesto))
        return PacoteProjetoExtraido(
            manifesto=manifesto,
            diretorio=target,
            integridade=RelatorioIntegridadeProjeto(problemas=tuple(problems)),
        )


def _validate_source(origin: OrigemArquivoPacote) -> None:
    path = origin.caminho_origem.expanduser().resolve()
    if not path.is_file():
        raise PortabilidadeProjetoError(
            f"Arquivo do pacote não foi encontrado: {origin.arquivo.caminho_relativo}"
        )
    digest, size = _file_digest(path)
    if digest != origin.arquivo.sha256 or size != origin.arquivo.tamanho_bytes:
        raise PortabilidadeProjetoError(
            f"Arquivo mudou durante a exportação: {origin.arquivo.caminho_relativo}"
        )


def _validate_members(members: list[ZipInfo]) -> None:
    names: set[str] = set()
    for member in members:
        name = member.filename.replace("\\", "/")
        posix_path = PurePosixPath(name)
        windows_path = PureWindowsPath(name)
        mode = member.external_attr >> 16
        if (
            not name
            or posix_path.is_absolute()
            or windows_path.is_absolute()
            or ".." in posix_path.parts
            or name.casefold() in names
            or member.flag_bits & 0x1
            or stat.S_ISLNK(mode)
        ):
            raise PortabilidadeProjetoError("Pacote contém uma entrada insegura")
        names.add(name.casefold())


def _member_problems(
    members: list[ZipInfo], manifesto: ManifestoProjetoPortatil
) -> list[ProblemaIntegridadeProjeto]:
    actual = {item.filename for item in members if not item.is_dir()}
    expected = {_MANIFEST_PATH, *(item.caminho_relativo for item in manifesto.arquivos)}
    problems: list[ProblemaIntegridadeProjeto] = []
    for name in sorted(expected - actual):
        problems.append(
            ProblemaIntegridadeProjeto(
                codigo="ARQUIVO_AUSENTE",
                mensagem="Arquivo declarado não está presente no pacote.",
                caminho_relativo=name,
                critico=name.endswith(".sqlite3"),
            )
        )
    for name in sorted(actual - expected):
        problems.append(
            ProblemaIntegridadeProjeto(
                codigo="ARQUIVO_NAO_DECLARADO",
                mensagem="Pacote contém arquivo não declarado no manifesto.",
                caminho_relativo=name,
                critico=True,
            )
        )
    return problems


def _extracted_problems(
    root: Path, manifesto: ManifestoProjetoPortatil
) -> list[ProblemaIntegridadeProjeto]:
    problems: list[ProblemaIntegridadeProjeto] = []
    for item in manifesto.arquivos:
        path = root / PurePosixPath(item.caminho_relativo)
        if not path.is_file():
            continue
        digest, size = _file_digest(path)
        detected = _detect_mime(path)
        if digest != item.sha256 or size != item.tamanho_bytes:
            problems.append(
                ProblemaIntegridadeProjeto(
                    codigo="HASH_DIVERGENTE",
                    mensagem="Conteúdo ou tamanho diverge do manifesto.",
                    caminho_relativo=item.caminho_relativo,
                    critico=item.tipo == "BANCO",
                )
            )
        if detected is not None and detected != item.tipo_mime:
            problems.append(
                ProblemaIntegridadeProjeto(
                    codigo="TIPO_DIVERGENTE",
                    mensagem="Assinatura do arquivo diverge do tipo declarado.",
                    caminho_relativo=item.caminho_relativo,
                    critico=True,
                )
            )
    return problems


def _manifest_envelope(manifesto: ManifestoProjetoPortatil) -> str:
    manifest = _manifest_to_dict(manifesto)
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    envelope = {"manifest": manifest, "manifest_sha256": sha256(canonical.encode()).hexdigest()}
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _manifest_from_envelope(envelope: dict[str, Any]) -> ManifestoProjetoPortatil:
    raw = envelope.get("manifest")
    signature = str(envelope.get("manifest_sha256", ""))
    if not isinstance(raw, dict):
        raise PortabilidadeProjetoError("Manifesto do pacote não é um objeto")
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if sha256(canonical.encode()).hexdigest() != signature:
        raise PortabilidadeProjetoError("Assinatura do manifesto é inválida")
    try:
        return ManifestoProjetoPortatil(
            versao_formato=int(raw["format_version"]),
            projeto_id=UUID(str(raw["project_id"])),
            catalogo_id=UUID(str(raw["catalog_id"])),
            nome_projeto=str(raw["project_name"]),
            criado_em=datetime.fromisoformat(str(raw["created_at"])),
            arquivos=tuple(
                ArquivoPacoteProjeto(
                    caminho_relativo=str(item["path"]),
                    tipo=str(item["kind"]),
                    sha256=str(item["sha256"]),
                    tamanho_bytes=int(item["size"]),
                    tipo_mime=str(item["mime_type"]),
                    referencia_id=(
                        UUID(str(item["reference_id"])) if item.get("reference_id") else None
                    ),
                )
                for item in cast(list[dict[str, Any]], raw["files"])
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PortabilidadeProjetoError("Campos do manifesto são inválidos") from error


def _manifest_to_dict(manifesto: ManifestoProjetoPortatil) -> dict[str, object]:
    payload: dict[str, object] = {
        "format_version": manifesto.versao_formato,
        "project_id": str(manifesto.projeto_id),
        "catalog_id": str(manifesto.catalogo_id),
        "project_name": manifesto.nome_projeto,
        "created_at": manifesto.criado_em.isoformat(),
        "files": [
            {
                "path": item.caminho_relativo,
                "kind": item.tipo,
                "sha256": item.sha256,
                "size": item.tamanho_bytes,
                "mime_type": item.tipo_mime,
                "reference_id": str(item.referencia_id) if item.referencia_id else None,
            }
            for item in manifesto.arquivos
        ],
    }
    return payload


def _file_digest(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _detect_mime(path: Path) -> str | None:
    with path.open("rb") as source:
        header = source.read(16)
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"SQLite format 3\x00"):
        return "application/vnd.sqlite3"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if path.suffix.casefold() == ".json":
        return "application/json"
    return None
