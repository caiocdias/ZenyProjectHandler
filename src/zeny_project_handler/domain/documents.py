"""Entidades que preservam o PDF e seu sistema de coordenadas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import CaixaPagina, decimal_value, required_text

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
VALID_ROTATIONS = frozenset({0, 90, 180, 270})


def _validate_pdf_file_name(value: str) -> str:
    file_name = required_text(value, field_name="nome_arquivo")
    if Path(file_name).name != file_name or Path(file_name).suffix.lower() != ".pdf":
        raise DomainValidationError("nome_arquivo deve conter somente o nome de um PDF")
    return file_name


def _validate_document_digest(value: str) -> str:
    digest = value.strip().lower()
    if not SHA256_PATTERN.fullmatch(digest):
        raise DomainValidationError("sha256 deve conter 64 caracteres hexadecimais")
    return digest


def _validate_document_pages(pages: tuple[PaginaDocumento, ...]) -> None:
    if not pages:
        raise DomainValidationError("Um documento deve possuir ao menos uma página")
    if len({page.id for page in pages}) != len(pages):
        raise DomainValidationError("IDs de página devem ser únicos no documento")
    if [page.numero for page in pages] != list(range(1, len(pages) + 1)):
        raise DomainValidationError("Páginas devem estar ordenadas e numeradas sem lacunas")


@dataclass(frozen=True, slots=True)
class PaginaDocumento:
    id: UUID
    numero: int
    largura_pontos: Decimal
    altura_pontos: Decimal
    rotacao_graus: int
    media_box: CaixaPagina
    crop_box: CaixaPagina
    matriz_pdf_para_pagina: tuple[Decimal, ...] = ()
    matriz_rotacao_pagina: tuple[Decimal, ...] = ()

    def __post_init__(self) -> None:
        width = decimal_value(self.largura_pontos, field_name="largura_pontos")
        height = decimal_value(self.altura_pontos, field_name="altura_pontos")
        if self.numero < 1:
            raise DomainValidationError("Número da página deve começar em 1")
        if width <= 0 or height <= 0:
            raise DomainValidationError("Dimensões da página devem ser positivas")
        if self.rotacao_graus not in VALID_ROTATIONS:
            raise DomainValidationError("Rotação da página deve ser 0, 90, 180 ou 270 graus")
        pdf_matrix = tuple(
            decimal_value(value, field_name="matriz_pdf_para_pagina")
            for value in self.matriz_pdf_para_pagina
        )
        rotation_matrix = tuple(
            decimal_value(value, field_name="matriz_rotacao_pagina")
            for value in self.matriz_rotacao_pagina
        )
        if len(pdf_matrix) not in {0, 6} or len(rotation_matrix) not in {0, 6}:
            raise DomainValidationError("Matrizes de página devem possuir seis coeficientes")
        object.__setattr__(self, "largura_pontos", width)
        object.__setattr__(self, "altura_pontos", height)
        object.__setattr__(self, "matriz_pdf_para_pagina", pdf_matrix)
        object.__setattr__(self, "matriz_rotacao_pagina", rotation_matrix)


@dataclass(frozen=True, slots=True)
class DocumentoProjeto:
    id: UUID
    nome_arquivo: str
    sha256: str
    paginas: tuple[PaginaDocumento, ...]
    tamanho_bytes: int | None = None
    versao_pdf: str | None = None
    produtor: str | None = None

    def __post_init__(self) -> None:
        file_name = _validate_pdf_file_name(self.nome_arquivo)
        digest = _validate_document_digest(self.sha256)
        pages = tuple(self.paginas)
        _validate_document_pages(pages)
        if self.tamanho_bytes is not None and self.tamanho_bytes <= 0:
            raise DomainValidationError("Tamanho do PDF deve ser positivo")
        pdf_version = self.versao_pdf.strip() if self.versao_pdf else None
        producer = self.produtor.strip() if self.produtor else None
        object.__setattr__(self, "nome_arquivo", file_name)
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(self, "paginas", pages)
        object.__setattr__(self, "versao_pdf", pdf_version or None)
        object.__setattr__(self, "produtor", producer or None)
