"""Manifesto e diagnósticos de integridade de projetos portáteis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from uuid import UUID

from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import required_text

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class EstadoIntegridadePacote(StrEnum):
    INTEGRO = "INTEGRO"
    DEGRADADO = "DEGRADADO"


class TratamentoOmissaoPacote(StrEnum):
    OMITIDO = "OMITIDO"
    PERMANECE_EXTERNO = "PERMANECE_EXTERNO"


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
class OmissaoPacoteProjeto:
    codigo: str
    tipo: str
    referencia_id: UUID
    projeto_id: UUID
    tratamento: TratamentoOmissaoPacote

    def __post_init__(self) -> None:
        object.__setattr__(self, "codigo", required_text(self.codigo, field_name="codigo").upper())
        object.__setattr__(self, "tipo", required_text(self.tipo, field_name="tipo").upper())
        if not isinstance(self.tratamento, TratamentoOmissaoPacote):
            raise DomainValidationError("Tratamento da omissão do pacote é inválido")


@dataclass(frozen=True, slots=True, kw_only=True)
class ManifestoProjetoPortatil:
    versao_formato: int
    projeto_id: UUID
    catalogo_id: UUID
    nome_projeto: str
    criado_em: datetime
    arquivos: tuple[ArquivoPacoteProjeto, ...]
    estado_integridade: EstadoIntegridadePacote = EstadoIntegridadePacote.INTEGRO
    omissoes: tuple[OmissaoPacoteProjeto, ...] = ()

    def __post_init__(self) -> None:
        files = tuple(self.arquivos)
        omissions = tuple(self.omissoes)
        if self.versao_formato not in {1, 2}:
            raise DomainValidationError("Versão de pacote portátil não suportada")
        if self.criado_em.tzinfo is None:
            raise DomainValidationError("Data do manifesto deve possuir fuso horário")
        if len({item.caminho_relativo.casefold() for item in files}) != len(files):
            raise DomainValidationError("Manifesto não pode repetir caminhos de arquivos")
        if not isinstance(self.estado_integridade, EstadoIntegridadePacote):
            raise DomainValidationError("Estado de integridade do pacote é inválido")
        if self.versao_formato == 1 and (
            self.estado_integridade is not EstadoIntegridadePacote.INTEGRO or omissions
        ):
            raise DomainValidationError("Formato 1 não registra degradação ou omissões")
        if self.versao_formato == 2 and (
            (self.estado_integridade is EstadoIntegridadePacote.DEGRADADO) != bool(omissions)
        ):
            raise DomainValidationError(
                "Estado degradado e omissões devem ser registrados em conjunto"
            )
        omission_keys = {
            (item.codigo, item.tipo, item.referencia_id, item.projeto_id, item.tratamento)
            for item in omissions
        }
        if len(omission_keys) != len(omissions):
            raise DomainValidationError("Manifesto não pode repetir omissões")
        object.__setattr__(
            self, "nome_projeto", required_text(self.nome_projeto, field_name="nome_projeto")
        )
        object.__setattr__(self, "arquivos", files)
        object.__setattr__(self, "omissoes", omissions)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProblemaIntegridadeProjeto:
    codigo: str
    mensagem: str
    caminho_relativo: str | None = None
    critico: bool = False
    tipo: str | None = None
    referencia_id: UUID | None = None
    projeto_id: UUID | None = None
    tratamento: TratamentoOmissaoPacote | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "codigo", required_text(self.codigo, field_name="codigo"))
        object.__setattr__(self, "mensagem", required_text(self.mensagem, field_name="mensagem"))
        if self.tipo is not None:
            object.__setattr__(self, "tipo", required_text(self.tipo, field_name="tipo").upper())
        audit_fields = (self.tipo, self.referencia_id, self.projeto_id, self.tratamento)
        if any(item is not None for item in audit_fields) and any(
            item is None for item in audit_fields
        ):
            raise DomainValidationError(
                "Problema auditável deve identificar tipo, referência, projeto e tratamento"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class RelatorioIntegridadeProjeto:
    problemas: tuple[ProblemaIntegridadeProjeto, ...] = ()

    @property
    def integro(self) -> bool:
        return not self.problemas

    @property
    def utilizavel(self) -> bool:
        return not any(item.critico for item in self.problemas)

    @property
    def estado(self) -> EstadoIntegridadePacote:
        if self.integro:
            return EstadoIntegridadePacote.INTEGRO
        return EstadoIntegridadePacote.DEGRADADO

    @property
    def omissoes(self) -> tuple[OmissaoPacoteProjeto, ...]:
        return tuple(
            OmissaoPacoteProjeto(
                codigo=item.codigo,
                tipo=item.tipo,
                referencia_id=item.referencia_id,
                projeto_id=item.projeto_id,
                tratamento=item.tratamento,
            )
            for item in self.problemas
            if item.tipo is not None
            and item.referencia_id is not None
            and item.projeto_id is not None
            and item.tratamento is not None
        )
