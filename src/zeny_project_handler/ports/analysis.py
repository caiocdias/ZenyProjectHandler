"""Contrato neutro para análise nativa de documentos e OCR opcional."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import UUID

from zeny_project_handler.domain.analysis import (
    DiagnosticoAnalise,
    EvidenciaDocumento,
    OrigemObjetoPdf,
)
from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.pdf import ReferenciaFontePdf


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguracaoAnaliseDocumento:
    extrair_texto: bool = True
    extrair_vetores: bool = True
    extrair_imagens: bool = True
    extrair_anotacoes: bool = True
    extrair_forms_xobjects: bool = True
    habilitar_ocr_condicional: bool = True
    minimo_caracteres_texto_nativo: int = 20
    area_imagem_minima_para_ocr: Decimal = Decimal("0.10")
    minimo_vetores_para_ocr: int = 1000
    dpi_ocr: int = 200
    profundidade_maxima_xobject: int = 12

    def __post_init__(self) -> None:
        if self.minimo_caracteres_texto_nativo < 0:
            raise ValueError("Mínimo de caracteres nativos não pode ser negativo")
        image_area = Decimal(self.area_imagem_minima_para_ocr)
        if not Decimal(0) <= image_area <= Decimal(1):
            raise ValueError("Área mínima de imagem para OCR deve estar entre 0 e 1")
        object.__setattr__(self, "area_imagem_minima_para_ocr", image_area)
        if self.minimo_vetores_para_ocr < 1:
            raise ValueError("Mínimo de vetores para OCR deve ser positivo")
        if not 72 <= self.dpi_ocr <= 600:
            raise ValueError("DPI de OCR deve estar entre 72 e 600")
        if not 1 <= self.profundidade_maxima_xobject <= 64:
            raise ValueError("Profundidade de XObject deve estar entre 1 e 64")

    def parametros(self) -> ExtraAttributes:
        return tuple(
            sorted(
                (
                    ("dpi_ocr", self.dpi_ocr),
                    ("area_imagem_minima_para_ocr", self.area_imagem_minima_para_ocr),
                    ("extrair_anotacoes", self.extrair_anotacoes),
                    ("extrair_forms_xobjects", self.extrair_forms_xobjects),
                    ("extrair_imagens", self.extrair_imagens),
                    ("extrair_texto", self.extrair_texto),
                    ("extrair_vetores", self.extrair_vetores),
                    ("habilitar_ocr_condicional", self.habilitar_ocr_condicional),
                    ("minimo_caracteres_texto_nativo", self.minimo_caracteres_texto_nativo),
                    ("minimo_vetores_para_ocr", self.minimo_vetores_para_ocr),
                    ("profundidade_maxima_xobject", self.profundidade_maxima_xobject),
                )
            )
        )

    def assinatura(self) -> str:
        payload = json.dumps(
            {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in self.parametros()
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class GeometriaNormalizada:
    tipo: TipoGeometria
    pontos: tuple[PontoNormalizado, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidatoEvidenciaDocumento:
    chave_estavel: str
    pagina_numero: int
    tipo: TipoEvidencia
    geometria: GeometriaNormalizada
    origem_pdf: OrigemObjetoPdf
    conteudo_bruto: str | None = None
    atributos_extraidos: ExtraAttributes = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtracaoDocumentoNormalizada:
    candidatos: tuple[CandidatoEvidenciaDocumento, ...]
    diagnosticos: tuple[DiagnosticoAnalise, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class SolicitacaoAnaliseDocumento:
    projeto_id: UUID
    documento: DocumentoProjeto
    fonte: ReferenciaFontePdf
    execucao_id: UUID
    criada_em: datetime
    configuracao: ConfiguracaoAnaliseDocumento = ConfiguracaoAnaliseDocumento()
    senha: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoAnaliseDocumento:
    evidencias: tuple[EvidenciaDocumento, ...]
    diagnosticos: tuple[DiagnosticoAnalise, ...]
    cache_utilizado: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PaginaRasterOcr:
    pagina_numero: int
    largura_pixels: int
    altura_pixels: int
    stride: int
    dados_rgb: bytes
    dpi: int


@dataclass(frozen=True, slots=True, kw_only=True)
class TrechoTextoOcr:
    texto: str
    caixa_normalizada: tuple[float, float, float, float]
    confianca: float | None = None


class MotorOcrPort(Protocol):
    nome: str
    versao: str

    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]: ...


class CacheAnaliseDocumentoPort(Protocol):
    def obter(self, chave: str) -> ExtracaoDocumentoNormalizada | None: ...

    def salvar(self, chave: str, extracao: ExtracaoDocumentoNormalizada) -> None: ...


class AnalisadorDocumentoPort(Protocol):
    nome: str
    versao: str

    def analisar(self, solicitacao: SolicitacaoAnaliseDocumento) -> ResultadoAnaliseDocumento: ...


def chave_cache_analise(
    *, documento_sha256: str, configuracao: ConfiguracaoAnaliseDocumento, analisador: str
) -> str:
    payload = f"{documento_sha256}:{configuracao.assinatura()}:{analisador}"
    return sha256(payload.encode("utf-8")).hexdigest()


def validar_fonte_solicitacao(solicitacao: SolicitacaoAnaliseDocumento) -> Path:
    if solicitacao.documento.id != solicitacao.fonte.documento_id:
        raise ValueError("Fonte PDF não pertence ao documento solicitado")
    if solicitacao.projeto_id != solicitacao.fonte.projeto_id:
        raise ValueError("Fonte PDF não pertence ao projeto solicitado")
    if solicitacao.documento.sha256 != solicitacao.fonte.sha256:
        raise ValueError("Hash da fonte diverge do documento solicitado")
    if solicitacao.criada_em.tzinfo is None:
        raise ValueError("Data da solicitação deve possuir fuso horário")
    return solicitacao.fonte.caminho_canonico
