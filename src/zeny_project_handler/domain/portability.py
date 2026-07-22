"""Manifesto e diagnósticos de integridade de projetos portáteis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from uuid import UUID

from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import required_text

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True, kw_only=True)
class ArquivoPacoteProjeto:
    caminho_relativo: str
    tipo: str
    sha256: str
    tamanho_bytes: int
    tipo_mime: str
    referencia_id: UUID | None = None

    def __post_init__(self) -> None:
        normalized = required_text(
            self.caminho_relativo.replace("\\", "/"), field_name="caminho_relativo"
        )
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(normalized)
        if posix_path.is_absolute() or windows_path.is_absolute() or ".." in posix_path.parts:
            raise DomainValidationError("Arquivo do pacote deve usar caminho relativo seguro")
        digest = self.sha256.strip().lower()
        if not _SHA256_PATTERN.fullmatch(digest):
            raise DomainValidationError("SHA-256 do arquivo do pacote é inválido")
        if self.tamanho_bytes < 0:
            raise DomainValidationError("Tamanho do arquivo do pacote não pode ser negativo")
        object.__setattr__(self, "caminho_relativo", posix_path.as_posix())
        object.__setattr__(self, "tipo", required_text(self.tipo, field_name="tipo").upper())
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(
            self,
            "tipo_mime",
            required_text(self.tipo_mime, field_name="tipo_mime").lower(),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ManifestoProjetoPortatil:
    versao_formato: int
    projeto_id: UUID
    catalogo_id: UUID
    nome_projeto: str
    criado_em: datetime
    arquivos: tuple[ArquivoPacoteProjeto, ...]
    assinatura_grafo: str | None = None

    def __post_init__(self) -> None:
        files = tuple(self.arquivos)
        if self.versao_formato != 1:
            raise DomainValidationError("Versão de pacote portátil não suportada")
        if self.criado_em.tzinfo is None:
            raise DomainValidationError("Data do manifesto deve possuir fuso horário")
        if len({item.caminho_relativo.casefold() for item in files}) != len(files):
            raise DomainValidationError("Manifesto não pode repetir caminhos de arquivos")
        graph_signature = self.assinatura_grafo.strip().lower() if self.assinatura_grafo else None
        if graph_signature is not None and not _SHA256_PATTERN.fullmatch(graph_signature):
            raise DomainValidationError("Assinatura do grafo no pacote é inválida")
        object.__setattr__(
            self, "nome_projeto", required_text(self.nome_projeto, field_name="nome_projeto")
        )
        object.__setattr__(self, "arquivos", files)
        object.__setattr__(self, "assinatura_grafo", graph_signature)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProblemaIntegridadeProjeto:
    codigo: str
    mensagem: str
    caminho_relativo: str | None = None
    critico: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "codigo", required_text(self.codigo, field_name="codigo"))
        object.__setattr__(self, "mensagem", required_text(self.mensagem, field_name="mensagem"))


@dataclass(frozen=True, slots=True, kw_only=True)
class RelatorioIntegridadeProjeto:
    problemas: tuple[ProblemaIntegridadeProjeto, ...] = ()

    @property
    def integro(self) -> bool:
        return not self.problemas

    @property
    def utilizavel(self) -> bool:
        return not any(item.critico for item in self.problemas)
