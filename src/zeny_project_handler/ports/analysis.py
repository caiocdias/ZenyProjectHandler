"""Contrato neutro para análise nativa de documentos e OCR opcional."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import UUID

from zeny_project_handler.domain.analysis import (
    DiagnosticoAnalise,
    EvidenciaDocumento,
    OrigemObjetoPdf,
)
from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.documents import SHA256_PATTERN, DocumentoProjeto
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
    area_imagem_regional_minima_para_ocr: Decimal = Decimal("0.0025")
    minimo_vetores_para_ocr: int = 1000
    dpi_ocr: int = 450
    dpi_ocr_identificadores: int = 1200
    dpi_ocr_rotulos_inclinados: int = 1800
    divisoes_ocr_conteudo_denso: int = 3
    sobreposicao_ocr_conteudo_denso: Decimal = Decimal("0.025")
    profundidade_maxima_xobject: int = 12

    def __post_init__(self) -> None:
        if self.minimo_caracteres_texto_nativo < 0:
            raise ValueError("Mínimo de caracteres nativos não pode ser negativo")
        image_area = Decimal(self.area_imagem_minima_para_ocr)
        if not Decimal(0) <= image_area <= Decimal(1):
            raise ValueError("Área mínima de imagem para OCR deve estar entre 0 e 1")
        object.__setattr__(self, "area_imagem_minima_para_ocr", image_area)
        regional_image_area = Decimal(self.area_imagem_regional_minima_para_ocr)
        if not Decimal(0) <= regional_image_area <= image_area:
            raise ValueError(
                "Área mínima de OCR regional deve ficar entre zero e o limite de página"
            )
        object.__setattr__(
            self,
            "area_imagem_regional_minima_para_ocr",
            regional_image_area,
        )
        if self.minimo_vetores_para_ocr < 1:
            raise ValueError("Mínimo de vetores para OCR deve ser positivo")
        if not 72 <= self.dpi_ocr <= 600:
            raise ValueError("DPI de OCR deve estar entre 72 e 600")
        if not 300 <= self.dpi_ocr_identificadores <= 1200:
            raise ValueError("DPI de OCR de identificadores deve estar entre 300 e 1200")
        if not 600 <= self.dpi_ocr_rotulos_inclinados <= 2400:
            raise ValueError("DPI de OCR de rótulos inclinados deve estar entre 600 e 2400")
        if not 2 <= self.divisoes_ocr_conteudo_denso <= 6:
            raise ValueError("Divisões de OCR denso devem estar entre 2 e 6")
        dense_overlap = Decimal(self.sobreposicao_ocr_conteudo_denso)
        if not Decimal(0) <= dense_overlap <= Decimal("0.10"):
            raise ValueError("Sobreposição de OCR denso deve estar entre zero e 0,10")
        object.__setattr__(self, "sobreposicao_ocr_conteudo_denso", dense_overlap)
        if not 1 <= self.profundidade_maxima_xobject <= 64:
            raise ValueError("Profundidade de XObject deve estar entre 1 e 64")

    def parametros(self) -> ExtraAttributes:
        return tuple(
            sorted(
                (
                    ("dpi_ocr", self.dpi_ocr),
                    ("dpi_ocr_identificadores", self.dpi_ocr_identificadores),
                    ("dpi_ocr_rotulos_inclinados", self.dpi_ocr_rotulos_inclinados),
                    (
                        "divisoes_ocr_conteudo_denso",
                        self.divisoes_ocr_conteudo_denso,
                    ),
                    ("area_imagem_minima_para_ocr", self.area_imagem_minima_para_ocr),
                    (
                        "area_imagem_regional_minima_para_ocr",
                        self.area_imagem_regional_minima_para_ocr,
                    ),
                    ("extrair_anotacoes", self.extrair_anotacoes),
                    ("extrair_forms_xobjects", self.extrair_forms_xobjects),
                    ("extrair_imagens", self.extrair_imagens),
                    ("extrair_texto", self.extrair_texto),
                    ("extrair_vetores", self.extrair_vetores),
                    ("habilitar_ocr_condicional", self.habilitar_ocr_condicional),
                    ("minimo_caracteres_texto_nativo", self.minimo_caracteres_texto_nativo),
                    ("minimo_vetores_para_ocr", self.minimo_vetores_para_ocr),
                    ("profundidade_maxima_xobject", self.profundidade_maxima_xobject),
                    (
                        "sobreposicao_ocr_conteudo_denso",
                        self.sobreposicao_ocr_conteudo_denso,
                    ),
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


@dataclass(frozen=True, slots=True, kw_only=True)
class IdentidadeDadosTreinadosOcr:
    idioma: str
    sha256: str

    def __post_init__(self) -> None:
        language = self.idioma.strip()
        digest = self.sha256.strip().lower()
        if not language:
            raise ValueError("Idioma dos dados treinados deve ser informado")
        if not SHA256_PATTERN.fullmatch(digest):
            raise ValueError("Identidade traineddata deve ser um SHA-256 hexadecimal")
        object.__setattr__(self, "idioma", language)
        object.__setattr__(self, "sha256", digest)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacidadeMotorOcr:
    implementacao: str
    versao: str
    idiomas: tuple[str, ...]
    dados_treinados: tuple[IdentidadeDadosTreinadosOcr, ...]
    parametros: ExtraAttributes

    def __post_init__(self) -> None:
        implementation = self.implementacao.strip()
        version = self.versao.strip()
        languages = tuple(language.strip() for language in self.idiomas)
        parameters = tuple(sorted(self.parametros, key=lambda item: item[0]))
        if not implementation or not version:
            raise ValueError("Implementação e versão do OCR devem ser informadas")
        if not languages or any(not language for language in languages):
            raise ValueError("A capacidade OCR deve selecionar ao menos um idioma")
        if len(set(languages)) != len(languages):
            raise ValueError("Idiomas selecionados para OCR devem ser únicos")
        if tuple(item.idioma for item in self.dados_treinados) != languages:
            raise ValueError("Dados treinados devem corresponder aos idiomas selecionados")
        if any(not key.strip() for key, _ in parameters) or len(
            {key for key, _ in parameters}
        ) != len(parameters):
            raise ValueError("Parâmetros da capacidade OCR devem possuir chaves únicas")
        object.__setattr__(self, "implementacao", implementation)
        object.__setattr__(self, "versao", version)
        object.__setattr__(self, "idiomas", languages)
        object.__setattr__(self, "parametros", parameters)

    def assinatura(self) -> str:
        payload = json.dumps(
            {
                "implementacao": self.implementacao,
                "versao": self.versao,
                "idiomas": self.idiomas,
                "dados_treinados": [
                    {"idioma": item.idioma, "sha256": item.sha256} for item in self.dados_treinados
                ],
                "parametros": {
                    key: str(value) if isinstance(value, Decimal) else value
                    for key, value in self.parametros
                },
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoConsultaCapacidadeOcr:
    capacidade: CapacidadeMotorOcr | None
    diagnosticos: tuple[DiagnosticoAnalise, ...] = ()

    def __post_init__(self) -> None:
        if self.capacidade is None and not self.diagnosticos:
            raise ValueError("Capacidade OCR ausente deve possuir diagnóstico")
        object.__setattr__(self, "diagnosticos", tuple(self.diagnosticos))


class MotorOcrPort(Protocol):
    nome: str

    def consultar_capacidade(self) -> ResultadoConsultaCapacidadeOcr: ...

    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]: ...


@runtime_checkable
class MotorOcrIdentificadorPort(Protocol):
    def reconhecer_identificador(
        self,
        pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]: ...


@runtime_checkable
class MotorOcrRotuloOperacionalPort(Protocol):
    def reconhecer_rotulo_operacional(
        self,
        pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]: ...


@runtime_checkable
class MotorOcrBlocoOperacionalPort(Protocol):
    def reconhecer_bloco_operacional(
        self,
        pagina: PaginaRasterOcr,
    ) -> tuple[TrechoTextoOcr, ...]: ...


class CacheAnaliseDocumentoPort(Protocol):
    def obter(self, chave: str) -> ExtracaoDocumentoNormalizada | None: ...

    def salvar(self, chave: str, extracao: ExtracaoDocumentoNormalizada) -> None: ...


class AnalisadorDocumentoPort(Protocol):
    nome: str
    versao: str

    @property
    def assinatura_capacidade(self) -> str: ...

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
