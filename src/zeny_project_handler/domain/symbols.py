"""Observações internas de símbolos, sem catálogo, fusão ou probabilidade implícita.

Identidades identificam saídas de um método/configuração, nunca um ativo físico.
Classes são abertas: estais e símbolos informativos não exigem CategoriaElemento.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass
from decimal import Decimal
from enum import Enum
from hashlib import sha256

from zeny_project_handler.domain.analysis import OrigemObjetoPdf, _normalize_extras
from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.documents import SHA256_PATTERN
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos, SituacaoProjeto, TipoGeometria
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import PontoNormalizado, decimal_value, required_text

PontoOriginalSimbolo = tuple[Decimal, Decimal]
MatrizAfimSimbolo = tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]


def _canonical(value: object) -> object:
    if isinstance(value, Enum):
        return [value.__class__.__name__, value.value]
    if isinstance(value, Decimal):
        return ["Decimal", str(value)]
    if is_dataclass(value) and not isinstance(value, type):
        return [
            value.__class__.__name__,
            {field.name: _canonical(getattr(value, field.name)) for field in fields(value)},
        ]
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    raise DomainValidationError(f"Valor sem assinatura canônica: {type(value).__name__}")


def _signature(value: object) -> str:
    payload = json.dumps(
        _canonical(value), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _digest(value: str) -> str:
    digest = value.strip().lower()
    if not SHA256_PATTERN.fullmatch(digest):
        raise DomainValidationError("Identidade deve ser um SHA-256 hexadecimal")
    return digest


def _texts(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    result = tuple(sorted(required_text(value, field_name=field) for value in values))
    if len(set(result)) != len(result):
        raise DomainValidationError(f"{field} não aceita duplicatas")
    return result


def _points(values: tuple[PontoOriginalSimbolo, ...]) -> tuple[PontoOriginalSimbolo, ...]:
    if not values:
        raise DomainValidationError("Geometria original deve preservar pontos")
    return tuple(
        (decimal_value(x, field_name="x"), decimal_value(y, field_name="y")) for x, y in values
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class FonteObservacaoSimbolo:
    documento_id: str
    documento_sha256: str
    pagina_numero: int
    camada: str
    origem_pdf: OrigemObjetoPdf = field(default_factory=OrigemObjetoPdf)

    def __post_init__(self) -> None:
        if self.pagina_numero < 1:
            raise DomainValidationError("Página deve ser positiva")
        object.__setattr__(
            self, "documento_id", required_text(self.documento_id, field_name="documento_id")
        )
        object.__setattr__(self, "documento_sha256", _digest(self.documento_sha256))
        object.__setattr__(self, "camada", required_text(self.camada, field_name="camada"))


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformacaoSimbolo:
    """Afim x'=a*x+c*y+e, y'=b*x+d*y+f; não desfaz clipping."""

    normalizada_para_original: MatrizAfimSimbolo
    sistema_original: str

    def __post_init__(self) -> None:
        matrix = self.normalizada_para_original
        if len(matrix) != 6 or any(not value.is_finite() for value in matrix):
            raise DomainValidationError("Transformação deve conter seis Decimals finitos")
        if matrix[0] * matrix[3] == matrix[1] * matrix[2]:
            raise DomainValidationError("Transformação deve ser invertível")
        object.__setattr__(
            self,
            "sistema_original",
            required_text(self.sistema_original, field_name="sistema_original"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class GeometriaObservacaoSimbolo:
    """Geometrias brutas e legadas separadas, inclusive degeneração e clipping."""

    tipo: TipoGeometria
    pontos_originais: tuple[PontoOriginalSimbolo, ...]
    pontos_normalizados: tuple[PontoNormalizado, ...]
    transformacao: TransformacaoSimbolo
    normalizacao_limitada: bool = False

    def __post_init__(self) -> None:
        if not self.pontos_normalizados:
            raise DomainValidationError("Geometria normalizada deve preservar pontos")
        object.__setattr__(self, "pontos_originais", _points(self.pontos_originais))
        object.__setattr__(self, "pontos_normalizados", tuple(self.pontos_normalizados))


@dataclass(frozen=True, slots=True, kw_only=True)
class PrimitivaObservadaSimbolo:
    indice: str
    camada: str | None
    pontos_originais: tuple[PontoOriginalSimbolo, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "indice", required_text(self.indice, field_name="indice"))
        object.__setattr__(self, "pontos_originais", _points(self.pontos_originais))


@dataclass(frozen=True, slots=True, kw_only=True)
class AlternativaClasseSimbolo:
    classe: str | None = None
    subtipo: str | None = None
    score_bruto: Decimal | None = None

    def __post_init__(self) -> None:
        if self.classe is not None:
            object.__setattr__(self, "classe", required_text(self.classe, field_name="classe"))
        if self.score_bruto is not None:
            object.__setattr__(
                self, "score_bruto", decimal_value(self.score_bruto, field_name="score_bruto")
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class PerfilMetodoSimbolos:
    metodo_id: str
    versao: str
    familia: str
    dominio_aplicacao: str
    classes_suportadas: tuple[str, ...]
    camadas_suportadas: tuple[str, ...]
    fontes_compartilhadas: tuple[str, ...]
    perfil_referencia: str
    parametros: ExtraAttributes = ()
    modelo: str | None = None
    template: str | None = None

    def __post_init__(self) -> None:
        for name in ("metodo_id", "versao", "familia", "dominio_aplicacao", "perfil_referencia"):
            object.__setattr__(self, name, required_text(getattr(self, name), field_name=name))
        for name in ("classes_suportadas", "camadas_suportadas", "fontes_compartilhadas"):
            object.__setattr__(self, name, _texts(getattr(self, name), name))
        object.__setattr__(
            self, "parametros", _normalize_extras(self.parametros, field_name="parametros")
        )

    def assinatura(self) -> str:
        return _signature(self)

    def possui_origem_correlacionada(self, outro: PerfilMetodoSimbolos) -> bool:
        """False significa correlação não declarada, não independência comprovada."""
        return self.familia == outro.familia or bool(
            set(self.fontes_compartilhadas) & set(outro.fontes_compartilhadas)
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CoberturaMetodoSimbolos:
    """Região avaliada pelo envelope retangular dos pontos, não por polígono arbitrário."""

    fonte: FonteObservacaoSimbolo
    regiao_normalizada: tuple[PontoNormalizado, ...]
    classes_avaliadas: tuple[str, ...]
    estado: EstadoMetodoSimbolos
    motivo: str | None = None

    def __post_init__(self) -> None:
        if not self.regiao_normalizada:
            raise DomainValidationError("Cobertura deve identificar a região")
        if self.estado not in {
            EstadoMetodoSimbolos.CONCLUIDO,
            EstadoMetodoSimbolos.NAO_DETECCAO,
        } and (not self.motivo or not self.motivo.strip()):
            raise DomainValidationError("Estado não concluído exige motivo")
        object.__setattr__(
            self, "classes_avaliadas", _texts(self.classes_avaliadas, "classes_avaliadas")
        )
        object.__setattr__(self, "regiao_normalizada", tuple(self.regiao_normalizada))


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservacaoSimbolo:
    fonte: FonteObservacaoSimbolo
    metodo_assinatura: str
    geometria: GeometriaObservacaoSimbolo
    alternativas: tuple[AlternativaClasseSimbolo, ...]
    score_bruto: Decimal | None = None
    primitivas: tuple[PrimitivaObservadaSimbolo, ...] = ()
    raster_sha256: str | None = None
    modelo: str | None = None
    template: str | None = None
    situacao: SituacaoProjeto | None = None
    atributos: ExtraAttributes = ()
    chave_legada: str | None = None
    conteudo_bruto: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metodo_assinatura", _digest(self.metodo_assinatura))
        if not self.alternativas:
            raise DomainValidationError(
                "Observação exige alternativa; use classe None se desconhecida"
            )
        if self.score_bruto is not None:
            object.__setattr__(
                self, "score_bruto", decimal_value(self.score_bruto, field_name="score_bruto")
            )
        if self.raster_sha256 is not None:
            object.__setattr__(self, "raster_sha256", _digest(self.raster_sha256))
        object.__setattr__(self, "alternativas", tuple(self.alternativas))
        object.__setattr__(self, "primitivas", tuple(self.primitivas))
        object.__setattr__(
            self, "atributos", _normalize_extras(self.atributos, field_name="atributos")
        )

    @property
    def id(self) -> str:
        return _signature(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class HipoteseSimbolo:
    """Vínculo explícito fornecido pelo consumidor; não executa associação/fusão."""

    hipotese_id: str
    observacoes_ids: tuple[str, ...]
    alternativas: tuple[AlternativaClasseSimbolo, ...] = ()

    def __post_init__(self) -> None:
        if not self.observacoes_ids:
            raise DomainValidationError("Hipótese exige observações")
        object.__setattr__(
            self, "hipotese_id", required_text(self.hipotese_id, field_name="hipotese_id")
        )
        object.__setattr__(self, "observacoes_ids", _texts(self.observacoes_ids, "observacoes_ids"))
        object.__setattr__(self, "alternativas", tuple(self.alternativas))


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoMetodoSimbolos:
    perfil: PerfilMetodoSimbolos
    coberturas: tuple[CoberturaMetodoSimbolos, ...]
    observacoes: tuple[ObservacaoSimbolo, ...] = ()

    def __post_init__(self) -> None:
        if not self.coberturas:
            raise DomainValidationError("Resultado exige cobertura, inclusive em falha")
        for coverage in self.coberturas:
            if coverage.estado is not EstadoMetodoSimbolos.FORA_DOMINIO and (
                coverage.fonte.camada not in self.perfil.camadas_suportadas
                or not set(coverage.classes_avaliadas) <= set(self.perfil.classes_suportadas)
            ):
                raise DomainValidationError("Cobertura fora das capacidades declaradas")
        for observation in self.observacoes:
            if observation.metodo_assinatura != self.perfil.assinatura():
                raise DomainValidationError("Assinatura da observação diverge do método")
            matching = tuple(
                coverage
                for coverage in self.coberturas
                if _coverage_contains(coverage, observation)
            )
            if not any(
                coverage.estado in {EstadoMetodoSimbolos.CONCLUIDO, EstadoMetodoSimbolos.FALHA}
                for coverage in matching
            ):
                raise DomainValidationError("Observação exige cobertura executada da mesma fonte")
            if any(coverage.estado is EstadoMetodoSimbolos.NAO_DETECCAO for coverage in matching):
                raise DomainValidationError("Não detecção contradiz observação na mesma cobertura")
        if len({observation.id for observation in self.observacoes}) != len(self.observacoes):
            raise DomainValidationError("Resultado não aceita observações duplicadas")
        object.__setattr__(self, "coberturas", tuple(self.coberturas))
        object.__setattr__(self, "observacoes", tuple(self.observacoes))

    @property
    def completo(self) -> bool:
        return all(
            coverage.estado
            in {
                EstadoMetodoSimbolos.CONCLUIDO,
                EstadoMetodoSimbolos.NAO_DETECCAO,
                EstadoMetodoSimbolos.FORA_DOMINIO,
            }
            for coverage in self.coberturas
        )


def _coverage_contains(coverage: CoberturaMetodoSimbolos, observation: ObservacaoSimbolo) -> bool:
    if coverage.fonte != observation.fonte:
        return False
    known_classes = {
        alternative.classe
        for alternative in observation.alternativas
        if alternative.classe is not None
    }
    if not known_classes <= set(coverage.classes_avaliadas):
        return False
    xs = [point.x for point in coverage.regiao_normalizada]
    ys = [point.y for point in coverage.regiao_normalizada]
    return all(
        min(xs) <= point.x <= max(xs) and min(ys) <= point.y <= max(ys)
        for point in observation.geometria.pontos_normalizados
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class RegistroMetodosSimbolos:
    metodos: tuple[PerfilMetodoSimbolos, ...] = ()

    def __post_init__(self) -> None:
        methods = tuple(sorted(self.metodos, key=lambda method: method.assinatura()))
        if len({method.assinatura() for method in methods}) != len(methods):
            raise DomainValidationError("Método/configuração já registrado")
        object.__setattr__(self, "metodos", methods)

    def obter(self, assinatura: str) -> PerfilMetodoSimbolos:
        for method in self.metodos:
            if method.assinatura() == assinatura:
                return method
        raise KeyError(assinatura)

    def assinatura(self) -> str:
        return _signature(self)
