"""Entidades auditáveis de análise e revisão humana."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import PurePosixPath, PureWindowsPath
from typing import TypeAlias
from uuid import UUID

from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.documents import SHA256_PATTERN
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    SituacaoProjeto,
    TipoDecisaoRevisao,
    TipoEvidencia,
    TipoOrigemPdf,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import GeometriaDocumento, decimal_value, required_text


def _normalize_extras(values: ExtraAttributes, *, field_name: str) -> ExtraAttributes:
    extras = tuple(sorted(values, key=lambda item: item[0]))
    if any(not key.strip() for key, _ in extras) or len({key for key, _ in extras}) != len(extras):
        raise DomainValidationError(f"{field_name} deve possuir chaves únicas e não vazias")
    return extras


def _optional_text(value: str | None) -> str | None:
    normalized = value.strip() if value else None
    return normalized or None


@dataclass(frozen=True, slots=True, kw_only=True)
class OrigemObjetoPdf:
    tipo: TipoOrigemPdf = TipoOrigemPdf.CONTEUDO_PAGINA
    numero_objeto: int | None = None
    indice_anotacao: int | None = None
    subtipo_anotacao: str | None = None
    nome_recurso: str | None = None

    def __post_init__(self) -> None:
        if self.numero_objeto is not None and self.numero_objeto < 1:
            raise DomainValidationError("Número do objeto PDF deve ser positivo")
        if self.indice_anotacao is not None and self.indice_anotacao < 0:
            raise DomainValidationError("Índice de anotação PDF não pode ser negativo")
        if self.tipo in {TipoOrigemPdf.ANOTACAO, TipoOrigemPdf.APARENCIA_ANOTACAO} and (
            self.numero_objeto is None and self.indice_anotacao is None
        ):
            raise DomainValidationError("Origem de anotação deve preservar objeto ou índice PDF")
        object.__setattr__(self, "subtipo_anotacao", _optional_text(self.subtipo_anotacao))
        object.__setattr__(self, "nome_recurso", _optional_text(self.nome_recurso))


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtefatoExtraido:
    caminho_relativo: str
    sha256: str
    mime_type: str
    tamanho_bytes: int

    def __post_init__(self) -> None:
        normalized = required_text(
            self.caminho_relativo.replace("\\", "/"), field_name="caminho_relativo"
        )
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(normalized)
        if posix_path.is_absolute() or windows_path.is_absolute() or ".." in posix_path.parts:
            raise DomainValidationError("Artefato deve usar caminho relativo interno ao projeto")
        digest = self.sha256.strip().lower()
        if not SHA256_PATTERN.fullmatch(digest):
            raise DomainValidationError("SHA-256 do artefato é inválido")
        if self.tamanho_bytes <= 0:
            raise DomainValidationError("Tamanho do artefato deve ser positivo")
        object.__setattr__(self, "caminho_relativo", posix_path.as_posix())
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(
            self, "mime_type", required_text(self.mime_type, field_name="mime_type").lower()
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DiagnosticoAnalise:
    """Falha localizada que não invalida os demais resultados da análise."""

    codigo: str
    mensagem: str
    extrator: str
    pagina_numero: int | None = None
    objeto_xref: int | None = None

    def __post_init__(self) -> None:
        if self.pagina_numero is not None and self.pagina_numero < 1:
            raise DomainValidationError("Página do diagnóstico deve ser positiva")
        if self.objeto_xref is not None and self.objeto_xref < 1:
            raise DomainValidationError("Objeto do diagnóstico deve ser positivo")
        object.__setattr__(self, "codigo", required_text(self.codigo, field_name="codigo"))
        object.__setattr__(self, "mensagem", required_text(self.mensagem, field_name="mensagem"))
        object.__setattr__(self, "extrator", required_text(self.extrator, field_name="extrator"))


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecucaoAnalise:
    id: UUID
    projeto_id: UUID
    metodo: str
    versao_metodo: str
    parametros: ExtraAttributes
    estado: EstadoExecucaoAnalise
    iniciada_em: datetime
    finalizada_em: datetime | None = None
    erro: str | None = None
    diagnosticos: tuple[DiagnosticoAnalise, ...] = ()

    def __post_init__(self) -> None:
        if self.iniciada_em.tzinfo is None:
            raise DomainValidationError("Início da análise deve possuir fuso horário")
        if self.finalizada_em is not None:
            if self.finalizada_em.tzinfo is None:
                raise DomainValidationError("Fim da análise deve possuir fuso horário")
            if self.finalizada_em < self.iniciada_em:
                raise DomainValidationError("Análise não pode terminar antes de iniciar")
        if self.estado is EstadoExecucaoAnalise.INICIADA and self.finalizada_em is not None:
            raise DomainValidationError("Análise iniciada não pode possuir data de término")
        if self.estado is not EstadoExecucaoAnalise.INICIADA and self.finalizada_em is None:
            raise DomainValidationError("Análise encerrada deve possuir data de término")
        error_message = self.erro.strip() if self.erro else None
        if self.estado is EstadoExecucaoAnalise.FALHOU and not error_message:
            raise DomainValidationError("Análise com falha deve registrar o erro")
        object.__setattr__(self, "metodo", required_text(self.metodo, field_name="metodo"))
        object.__setattr__(
            self,
            "versao_metodo",
            required_text(self.versao_metodo, field_name="versao_metodo"),
        )
        object.__setattr__(
            self, "parametros", _normalize_extras(self.parametros, field_name="Parâmetros")
        )
        object.__setattr__(self, "erro", error_message)
        object.__setattr__(self, "diagnosticos", tuple(self.diagnosticos))


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenciaDocumento:
    id: UUID
    execucao_id: UUID
    pagina_id: UUID
    tipo: TipoEvidencia
    geometria: GeometriaDocumento
    metodo: str
    versao_metodo: str
    parametros: ExtraAttributes
    conteudo_bruto: str | None
    criada_em: datetime
    origem_pdf: OrigemObjetoPdf = OrigemObjetoPdf()
    artefato: ArtefatoExtraido | None = None
    atributos_extraidos: ExtraAttributes = ()

    def __post_init__(self) -> None:
        if self.geometria.pagina_id != self.pagina_id:
            raise DomainValidationError("Geometria da evidência deve pertencer à página informada")
        if self.criada_em.tzinfo is None:
            raise DomainValidationError("Data da evidência deve possuir fuso horário")
        raw_content = self.conteudo_bruto.strip() if self.conteudo_bruto else None
        object.__setattr__(self, "metodo", required_text(self.metodo, field_name="metodo"))
        object.__setattr__(
            self,
            "versao_metodo",
            required_text(self.versao_metodo, field_name="versao_metodo"),
        )
        object.__setattr__(
            self, "parametros", _normalize_extras(self.parametros, field_name="Parâmetros")
        )
        object.__setattr__(self, "conteudo_bruto", raw_content)
        object.__setattr__(
            self,
            "atributos_extraidos",
            _normalize_extras(self.atributos_extraidos, field_name="Atributos extraídos"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PropostaElemento:
    id: UUID
    execucao_id: UUID
    categoria: CategoriaElemento
    situacao_projeto: SituacaoProjeto
    estado_revisao: EstadoRevisao
    evidencia_ids: tuple[UUID, ...]
    geometria: GeometriaDocumento
    tipo_catalogo_sugerido_id: UUID | None = None
    codigo_observado: str | None = None
    atributos_sugeridos: ExtraAttributes = ()
    confianca: Decimal | None = None
    justificativa: str | None = None

    def __post_init__(self) -> None:
        evidence_ids = tuple(self.evidencia_ids)
        if not evidence_ids or len(set(evidence_ids)) != len(evidence_ids):
            raise DomainValidationError("Proposta deve possuir evidências únicas")
        confidence = self.confianca
        if confidence is not None:
            confidence = decimal_value(confidence, field_name="confianca")
            if not Decimal(0) <= confidence <= Decimal(1):
                raise DomainValidationError("Confiança deve estar entre 0 e 1")
        object.__setattr__(self, "evidencia_ids", evidence_ids)
        object.__setattr__(self, "codigo_observado", _optional_text(self.codigo_observado))
        object.__setattr__(
            self,
            "atributos_sugeridos",
            _normalize_extras(self.atributos_sugeridos, field_name="Atributos sugeridos"),
        )
        object.__setattr__(self, "confianca", confidence)
        object.__setattr__(self, "justificativa", _optional_text(self.justificativa))


@dataclass(frozen=True, slots=True, kw_only=True)
class PropostaRelacao:
    id: UUID
    execucao_id: UUID
    origem_referencia_id: UUID
    destino_referencia_id: UUID
    tipo_relacao: str
    evidencia_ids: tuple[UUID, ...]
    estado_revisao: EstadoRevisao = EstadoRevisao.PROPOSTA
    confianca: Decimal | None = None
    justificativa: str | None = None

    def __post_init__(self) -> None:
        if self.origem_referencia_id == self.destino_referencia_id:
            raise DomainValidationError("Proposta de relação deve ligar referências distintas")
        evidence_ids = tuple(self.evidencia_ids)
        if not evidence_ids or len(set(evidence_ids)) != len(evidence_ids):
            raise DomainValidationError("Relação proposta deve possuir evidências únicas")
        confidence = self.confianca
        if confidence is not None:
            confidence = decimal_value(confidence, field_name="confianca")
            if not Decimal(0) <= confidence <= Decimal(1):
                raise DomainValidationError("Confiança deve estar entre 0 e 1")
        object.__setattr__(
            self, "tipo_relacao", required_text(self.tipo_relacao, field_name="tipo_relacao")
        )
        object.__setattr__(self, "evidencia_ids", evidence_ids)
        object.__setattr__(self, "confianca", confidence)
        object.__setattr__(self, "justificativa", _optional_text(self.justificativa))


ReferenciaProposta: TypeAlias = PropostaElemento | PropostaRelacao


@dataclass(frozen=True, slots=True, kw_only=True)
class DecisaoRevisao:
    id: UUID
    proposta_id: UUID
    decisao: TipoDecisaoRevisao
    revisor: str
    decidida_em: datetime
    elemento_confirmado_id: UUID | None = None
    relacao_confirmada_id: UUID | None = None
    motivo: str | None = None

    def __post_init__(self) -> None:
        if self.decidida_em.tzinfo is None:
            raise DomainValidationError("Data da decisão deve possuir fuso horário")
        confirmed_references = tuple(
            item
            for item in (self.elemento_confirmado_id, self.relacao_confirmada_id)
            if item is not None
        )
        if self.decisao is TipoDecisaoRevisao.REJEITAR and confirmed_references:
            raise DomainValidationError("Proposta rejeitada não pode gerar referência confirmada")
        if (
            self.decisao in {TipoDecisaoRevisao.ACEITAR, TipoDecisaoRevisao.AJUSTAR}
            and len(confirmed_references) != 1
        ):
            raise DomainValidationError(
                "Proposta aceita ou ajustada deve indicar uma única referência confirmada"
            )
        object.__setattr__(self, "revisor", required_text(self.revisor, field_name="revisor"))
        object.__setattr__(self, "motivo", self.motivo.strip() if self.motivo else None)
