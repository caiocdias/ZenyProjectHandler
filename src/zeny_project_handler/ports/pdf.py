"""Contratos neutros para inspecionar e renderizar documentos PDF."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento

PdfRectangle = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class DiagnosticoPdf:
    codigo: str
    mensagem: str
    pagina_numero: int | None = None
    objeto_xref: int | None = None


@dataclass(frozen=True, slots=True)
class FragmentoTextoPdf:
    texto: str
    caixa: PdfRectangle


@dataclass(frozen=True, slots=True)
class GraficoVetorialPdf:
    tipo: str
    caixa: PdfRectangle
    quantidade_comandos: int


@dataclass(frozen=True, slots=True)
class ImagemIncorporadaPdf:
    xref: int
    mascara_xref: int
    largura: int
    altura: int
    bits_por_componente: int
    espaco_cor: str
    nome: str
    filtro: str
    referenciador_xref: int


@dataclass(frozen=True, slots=True)
class AnotacaoPdf:
    xref: int
    subtipo: str
    caixa: PdfRectangle | None
    aparencias_xrefs: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class FormXObjectPdf:
    xref: int
    nome: str
    referenciador_xref: int
    caixa: PdfRectangle


@dataclass(frozen=True, slots=True)
class GrupoConteudoOpcionalPdf:
    xref: int
    nome: str
    ligado: bool
    intencoes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InventarioPaginaPdf:
    pagina: PaginaDocumento
    textos: tuple[FragmentoTextoPdf, ...] = ()
    vetores: tuple[GraficoVetorialPdf, ...] = ()
    imagens: tuple[ImagemIncorporadaPdf, ...] = ()
    anotacoes: tuple[AnotacaoPdf, ...] = ()
    forms_xobjects: tuple[FormXObjectPdf, ...] = ()
    diagnosticos: tuple[DiagnosticoPdf, ...] = ()


@dataclass(frozen=True, slots=True)
class InspecaoPdf:
    documento: DocumentoProjeto
    caminho_origem: Path
    tamanho_bytes: int
    modificado_em_ns: int
    adaptador: str
    paginas: tuple[InventarioPaginaPdf, ...]
    grupos_conteudo_opcional: tuple[GrupoConteudoOpcionalPdf, ...] = ()
    diagnosticos: tuple[DiagnosticoPdf, ...] = ()


@dataclass(frozen=True, slots=True)
class PaginaPdfRenderizada:
    pagina_numero: int
    largura_pixels: int
    altura_pixels: int
    stride: int
    dados_rgb: bytes
    dpi: int
    rotacao_adicional_graus: int


@dataclass(frozen=True, slots=True)
class ReferenciaFontePdf:
    documento_id: UUID
    projeto_id: UUID
    caminho_canonico: Path
    sha256: str
    tamanho_bytes: int
    modificado_em_ns: int


class SessaoLeituraPdfPort(Protocol):
    """Origem inspecionada cuja identidade vale apenas durante esta sessão."""

    @property
    def inspecao(self) -> InspecaoPdf: ...

    def renderizar_pagina(
        self,
        pagina_numero: int,
        *,
        dpi: int,
        rotacao_adicional_graus: int = 0,
        recorte_normalizado: PdfRectangle | None = None,
    ) -> PaginaPdfRenderizada: ...

    def fechar(self) -> None: ...


class LeitorPdfPort(Protocol):
    def abrir_sessao(
        self,
        caminho: Path,
        *,
        senha: str | None = None,
        documento_id: UUID | None = None,
        sha256_esperado: str | None = None,
    ) -> SessaoLeituraPdfPort: ...

    def inspecionar(
        self,
        caminho: Path,
        *,
        senha: str | None = None,
        documento_id: UUID | None = None,
    ) -> InspecaoPdf: ...

    def renderizar_pagina(
        self,
        caminho: Path,
        pagina_numero: int,
        *,
        dpi: int,
        rotacao_adicional_graus: int = 0,
        recorte_normalizado: PdfRectangle | None = None,
        senha: str | None = None,
        sha256_esperado: str | None = None,
    ) -> PaginaPdfRenderizada: ...

    def verificar_origem(self, inspecao: InspecaoPdf) -> None: ...


class FontePdfRepositoryPort(Protocol):
    def obter(self, documento_id: UUID) -> ReferenciaFontePdf | None: ...

    def salvar(self, referencia: ReferenciaFontePdf) -> None: ...
