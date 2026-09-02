"""Catálogo técnico versionado e independente da persistência."""

from __future__ import annotations

import re
from collections.abc import Collection, Hashable
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, TypeAlias
from uuid import UUID

from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    SituacaoProjeto,
    StatusCatalogo,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import decimal_value, required_text

JsonPrimitive: TypeAlias = str | int | Decimal | bool | None
ExtraAttributes: TypeAlias = tuple[tuple[str, JsonPrimitive], ...]
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass(frozen=True, slots=True, kw_only=True)
class OpcaoCatalogo:
    id: UUID
    codigo: str
    rotulo: str
    ativo: bool = True
    ordem: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "codigo", required_text(self.codigo, field_name="codigo"))
        object.__setattr__(self, "rotulo", required_text(self.rotulo, field_name="rotulo"))
        if self.ordem < 1:
            raise DomainValidationError("Ordem da opção deve ser positiva")


@dataclass(frozen=True, slots=True, kw_only=True)
class GrupoOpcao:
    id: UUID
    chave: str
    nome: str
    ordem: int
    opcoes: tuple[OpcaoCatalogo, ...]

    def __post_init__(self) -> None:
        key = required_text(self.chave, field_name="chave").lower()
        name = required_text(self.nome, field_name="nome")
        options = tuple(self.opcoes)
        if self.ordem < 1:
            raise DomainValidationError("Ordem do grupo deve ser positiva")
        if not options:
            raise DomainValidationError("Grupo de opções não pode ser vazio")
        if len({option.id for option in options}) != len(options):
            raise DomainValidationError(f"Grupo {key} possui IDs de opção duplicados")
        if len({option.codigo.casefold() for option in options}) != len(options):
            raise DomainValidationError(f"Grupo {key} possui códigos de opção duplicados")
        if len({option.ordem for option in options}) != len(options):
            raise DomainValidationError(f"Grupo {key} possui ordens de opção duplicadas")
        object.__setattr__(self, "chave", key)
        object.__setattr__(self, "nome", name)
        object.__setattr__(self, "opcoes", options)


@dataclass(frozen=True, slots=True, kw_only=True)
class ItemCatalogo:
    categoria: ClassVar[CategoriaElemento]

    id: UUID
    codigo: str
    descricao: str
    ativo: bool
    linha_origem: int
    atributos_extras: ExtraAttributes = ()

    def __post_init__(self) -> None:
        code = required_text(self.codigo, field_name="codigo")
        description = required_text(self.descricao, field_name="descricao")
        extras = tuple(sorted(self.atributos_extras, key=lambda item: item[0]))
        if self.linha_origem < 3:
            raise DomainValidationError("Linha de origem deve apontar para uma linha de dados")
        if any(not key.strip() for key, _ in extras):
            raise DomainValidationError("Chaves de atributos extras não podem ser vazias")
        if len({key for key, _ in extras}) != len(extras):
            raise DomainValidationError("Atributos extras não podem repetir chaves")
        object.__setattr__(self, "codigo", code)
        object.__setattr__(self, "descricao", description)
        object.__setattr__(self, "atributos_extras", extras)


@dataclass(frozen=True, slots=True, kw_only=True)
class TipoPoste(ItemCatalogo):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.POSTE

    altura_m: Decimal
    resistencia_dan: int
    formato_opcao_id: UUID

    def __post_init__(self) -> None:
        ItemCatalogo.__post_init__(self)
        height = decimal_value(self.altura_m, field_name="altura_m")
        if height <= 0 or self.resistencia_dan <= 0:
            raise DomainValidationError("Altura e resistência do poste devem ser positivas")
        object.__setattr__(self, "altura_m", height)


@dataclass(frozen=True, slots=True, kw_only=True)
class TipoEstruturaMt(ItemCatalogo):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.ESTRUTURA_MT

    configuracao_fases_opcao_id: UUID
    tecnologia_rede_opcao_id: UUID
    ancoragem: bool
    expressao_cabos_original: str

    def __post_init__(self) -> None:
        ItemCatalogo.__post_init__(self)
        object.__setattr__(
            self,
            "expressao_cabos_original",
            required_text(self.expressao_cabos_original, field_name="expressao_cabos_original"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TipoEstruturaBt(ItemCatalogo):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.ESTRUTURA_BT

    tecnologia_rede_opcao_id: UUID
    ancoragem: bool
    expressao_cabos_original: str

    def __post_init__(self) -> None:
        ItemCatalogo.__post_init__(self)
        object.__setattr__(
            self,
            "expressao_cabos_original",
            required_text(self.expressao_cabos_original, field_name="expressao_cabos_original"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TipoCabo(ItemCatalogo):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.CABO

    configuracao_fases_opcao_id: UUID
    tecnologia_rede_opcao_id: UUID
    nivel_tensao_opcao_id: UUID
    fator_condenacao: Decimal | None
    referencia_condutor: str

    def __post_init__(self) -> None:
        ItemCatalogo.__post_init__(self)
        factor = self.fator_condenacao
        if factor is not None:
            factor = decimal_value(factor, field_name="fator_condenacao")
            if factor <= 0:
                raise DomainValidationError("Fator de condenação deve ser positivo ou nulo")
        object.__setattr__(self, "fator_condenacao", factor)
        object.__setattr__(
            self,
            "referencia_condutor",
            required_text(self.referencia_condutor, field_name="referencia_condutor"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TipoEquipamento(ItemCatalogo):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.EQUIPAMENTO

    configuracao_fases_opcao_id: UUID
    classe_equipamento_opcao_id: UUID

    def __post_init__(self) -> None:
        ItemCatalogo.__post_init__(self)


ItemCatalogoType: TypeAlias = (
    TipoPoste | TipoEstruturaMt | TipoEstruturaBt | TipoCabo | TipoEquipamento
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CompatibilidadeEstruturaCabo:
    id: UUID
    tipo_estrutura_id: UUID
    tipo_cabo_id: UUID
    expressao_origem: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expressao_origem",
            required_text(self.expressao_origem, field_name="expressao_origem"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RegraSimbologia:
    id: UUID
    categoria_elemento: CategoriaElemento
    situacao_projeto: SituacaoProjeto
    icone: str
    cor: str
    padrao_traco: str
    rotulo: str

    def __post_init__(self) -> None:
        icon = required_text(self.icone, field_name="icone")
        color = self.cor.strip().upper()
        if not COLOR_PATTERN.fullmatch(color):
            raise DomainValidationError("Cor de simbologia deve usar o formato hexadecimal #RRGGBB")
        object.__setattr__(self, "icone", icon)
        object.__setattr__(self, "cor", color)
        object.__setattr__(
            self, "padrao_traco", required_text(self.padrao_traco, field_name="padrao_traco")
        )
        object.__setattr__(self, "rotulo", required_text(self.rotulo, field_name="rotulo"))


@dataclass(frozen=True, slots=True, kw_only=True)
class AssinaturaSimbologia:
    id: UUID
    situacao_projeto: SituacaoProjeto
    cor: str
    tolerancia_cor: int
    prioridade: int
    origem: str
    categoria_elemento: CategoriaElemento | None = None
    padrao_traco: str | None = None

    def __post_init__(self) -> None:
        color = self.cor.strip().upper()
        if not COLOR_PATTERN.fullmatch(color):
            raise DomainValidationError("Cor da assinatura deve usar o formato hexadecimal #RRGGBB")
        if not 0 <= self.tolerancia_cor <= 255:
            raise DomainValidationError("Tolerância de cor deve estar entre 0 e 255")
        if self.prioridade < 1:
            raise DomainValidationError("Prioridade da assinatura deve ser positiva")
        object.__setattr__(self, "cor", color)
        object.__setattr__(self, "origem", required_text(self.origem, field_name="origem"))
        stroke_pattern = self.padrao_traco.strip() if self.padrao_traco else None
        object.__setattr__(self, "padrao_traco", stroke_pattern or None)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContagensOrigem:
    postes: int
    estruturas_mt: int
    estruturas_bt: int
    cabos: int
    equipamentos: int

    def __post_init__(self) -> None:
        if (
            min(
                self.postes,
                self.estruturas_mt,
                self.estruturas_bt,
                self.cabos,
                self.equipamentos,
            )
            < 0
        ):
            raise DomainValidationError("Contagens da origem não podem ser negativas")


@dataclass(frozen=True, slots=True, kw_only=True)
class FonteCatalogo:
    nome_arquivo: str
    sha256: str
    planilha: str
    contagens: ContagensOrigem
    importado_em: datetime

    def __post_init__(self) -> None:
        digest = self.sha256.strip().lower()
        if not SHA256_PATTERN.fullmatch(digest):
            raise DomainValidationError("SHA-256 da planilha é inválido")
        if self.importado_em.tzinfo is None:
            raise DomainValidationError("Data de importação deve possuir fuso horário")
        object.__setattr__(
            self, "nome_arquivo", required_text(self.nome_arquivo, field_name="nome_arquivo")
        )
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(self, "planilha", required_text(self.planilha, field_name="planilha"))


@dataclass(frozen=True, slots=True, kw_only=True)
class AvisoImportacao:
    codigo: str
    mensagem: str
    categoria: CategoriaElemento
    valor: str
    linhas_origem: tuple[int, ...]
    resolucao: str

    def __post_init__(self) -> None:
        rows = tuple(self.linhas_origem)
        if not rows or any(row < 3 for row in rows):
            raise DomainValidationError("Aviso de importação deve indicar linhas de dados válidas")
        object.__setattr__(self, "codigo", required_text(self.codigo, field_name="codigo"))
        object.__setattr__(self, "mensagem", required_text(self.mensagem, field_name="mensagem"))
        object.__setattr__(self, "valor", required_text(self.valor, field_name="valor"))
        object.__setattr__(self, "linhas_origem", rows)
        object.__setattr__(self, "resolucao", required_text(self.resolucao, field_name="resolucao"))


@dataclass(frozen=True, slots=True, kw_only=True)
class CatalogoTecnico:
    id: UUID
    versao: int
    versao_schema: int
    status: StatusCatalogo
    criado_em: datetime
    publicado_em: datetime | None
    fonte: FonteCatalogo
    grupos_opcao: tuple[GrupoOpcao, ...]
    itens: tuple[ItemCatalogoType, ...]
    compatibilidades: tuple[CompatibilidadeEstruturaCabo, ...]
    regras_simbologia: tuple[RegraSimbologia, ...]
    avisos_importacao: tuple[AvisoImportacao, ...] = ()
    assinaturas_simbologia: tuple[AssinaturaSimbologia, ...] = ()

    def __post_init__(self) -> None:
        groups = tuple(self.grupos_opcao)
        items = tuple(self.itens)
        compatibilities = tuple(self.compatibilidades)
        symbol_rules = tuple(self.regras_simbologia)
        warnings = tuple(self.avisos_importacao)
        symbol_signatures = tuple(self.assinaturas_simbologia)

        if self.versao < 1 or self.versao_schema < 1:
            raise DomainValidationError("Versões do catálogo e do schema devem ser positivas")
        if self.criado_em.tzinfo is None:
            raise DomainValidationError("Data de criação deve possuir fuso horário")
        if self.status is StatusCatalogo.PUBLICADO and self.publicado_em is None:
            raise DomainValidationError("Catálogo publicado deve registrar a data de publicação")
        if self.status is StatusCatalogo.RASCUNHO and self.publicado_em is not None:
            raise DomainValidationError("Catálogo em rascunho não pode possuir data de publicação")
        if self.publicado_em is not None and self.publicado_em.tzinfo is None:
            raise DomainValidationError("Data de publicação deve possuir fuso horário")

        self._validate_unique_collections(
            groups, items, compatibilities, symbol_rules, symbol_signatures
        )
        option_group_by_id = self._option_group_by_id(groups)
        self._validate_option_references(items, option_group_by_id)
        self._validate_compatibilities(items, compatibilities)
        self._validate_symbol_rules(symbol_rules)
        self._validate_symbol_signatures(symbol_signatures, required=self.versao_schema >= 2)

        object.__setattr__(self, "grupos_opcao", groups)
        object.__setattr__(self, "itens", items)
        object.__setattr__(self, "compatibilidades", compatibilities)
        object.__setattr__(self, "regras_simbologia", symbol_rules)
        object.__setattr__(self, "avisos_importacao", warnings)
        object.__setattr__(self, "assinaturas_simbologia", symbol_signatures)

    @staticmethod
    def _validate_unique_collections(
        groups: tuple[GrupoOpcao, ...],
        items: tuple[ItemCatalogoType, ...],
        compatibilities: tuple[CompatibilidadeEstruturaCabo, ...],
        symbol_rules: tuple[RegraSimbologia, ...],
        symbol_signatures: tuple[AssinaturaSimbologia, ...],
    ) -> None:
        CatalogoTecnico._ensure_unique(
            [group.id for group in groups], "IDs de grupos de opção devem ser únicos"
        )
        CatalogoTecnico._ensure_unique(
            [group.chave for group in groups], "Chaves de grupos de opção devem ser únicas"
        )
        all_option_ids = [option.id for group in groups for option in group.opcoes]
        CatalogoTecnico._ensure_unique(all_option_ids, "IDs de opções devem ser únicos no catálogo")
        CatalogoTecnico._ensure_unique([item.id for item in items], "IDs de itens devem ser únicos")
        active_codes = [(item.categoria, item.codigo.casefold()) for item in items if item.ativo]
        CatalogoTecnico._ensure_unique(
            active_codes, "Códigos ativos devem ser únicos por categoria"
        )
        CatalogoTecnico._ensure_unique(
            [item.id for item in compatibilities],
            "IDs de compatibilidade devem ser únicos",
        )
        CatalogoTecnico._ensure_unique(
            [rule.id for rule in symbol_rules],
            "IDs de regras de simbologia devem ser únicos",
        )
        CatalogoTecnico._ensure_unique(
            [signature.id for signature in symbol_signatures],
            "IDs de assinaturas de simbologia devem ser únicos",
        )

    @staticmethod
    def _ensure_unique(values: Collection[Hashable], message: str) -> None:
        if len(set(values)) != len(values):
            raise DomainValidationError(message)

    @staticmethod
    def _option_group_by_id(groups: tuple[GrupoOpcao, ...]) -> dict[UUID, str]:
        return {option.id: group.chave for group in groups for option in group.opcoes}

    @staticmethod
    def _require_option(
        option_group_by_id: dict[UUID, str], option_id: UUID, expected_group: str
    ) -> None:
        if option_group_by_id.get(option_id) != expected_group:
            raise DomainValidationError(
                f"Opção {option_id} deve pertencer ao grupo {expected_group}"
            )

    @classmethod
    def _validate_option_references(
        cls, items: tuple[ItemCatalogoType, ...], option_group_by_id: dict[UUID, str]
    ) -> None:
        for item in items:
            if isinstance(item, TipoPoste):
                cls._require_option(option_group_by_id, item.formato_opcao_id, "formato_poste")
            elif isinstance(item, TipoEstruturaMt):
                cls._require_option(
                    option_group_by_id,
                    item.configuracao_fases_opcao_id,
                    "configuracao_fases",
                )
                cls._require_option(
                    option_group_by_id, item.tecnologia_rede_opcao_id, "tecnologia_rede"
                )
            elif isinstance(item, TipoEstruturaBt):
                cls._require_option(
                    option_group_by_id, item.tecnologia_rede_opcao_id, "tecnologia_rede"
                )
            elif isinstance(item, TipoCabo):
                cls._require_option(
                    option_group_by_id,
                    item.configuracao_fases_opcao_id,
                    "configuracao_fases",
                )
                cls._require_option(
                    option_group_by_id, item.tecnologia_rede_opcao_id, "tecnologia_rede"
                )
                cls._require_option(option_group_by_id, item.nivel_tensao_opcao_id, "nivel_tensao")
            elif isinstance(item, TipoEquipamento):
                cls._require_option(
                    option_group_by_id,
                    item.configuracao_fases_opcao_id,
                    "configuracao_fases",
                )
                cls._require_option(
                    option_group_by_id,
                    item.classe_equipamento_opcao_id,
                    "classe_equipamento",
                )

    @staticmethod
    def _validate_compatibilities(
        items: tuple[ItemCatalogoType, ...],
        compatibilities: tuple[CompatibilidadeEstruturaCabo, ...],
    ) -> None:
        item_by_id = {item.id: item for item in items}
        seen_pairs: set[tuple[UUID, UUID]] = set()
        for compatibility in compatibilities:
            structure = item_by_id.get(compatibility.tipo_estrutura_id)
            cable = item_by_id.get(compatibility.tipo_cabo_id)
            if not isinstance(structure, (TipoEstruturaMt, TipoEstruturaBt)):
                raise DomainValidationError("Compatibilidade deve referenciar uma estrutura")
            if not isinstance(cable, TipoCabo):
                raise DomainValidationError("Compatibilidade deve referenciar um cabo")
            if not structure.ativo or not cable.ativo:
                raise DomainValidationError("Compatibilidade não pode usar itens inativos")
            pair = (structure.id, cable.id)
            if pair in seen_pairs:
                raise DomainValidationError("Compatibilidade estrutura/cabo duplicada")
            seen_pairs.add(pair)

    @staticmethod
    def _validate_symbol_rules(rules: tuple[RegraSimbologia, ...]) -> None:
        combinations = {(rule.categoria_elemento, rule.situacao_projeto) for rule in rules}
        source_drawing_situations = {
            SituacaoProjeto.EXISTENTE,
            SituacaoProjeto.INSTALAR,
            SituacaoProjeto.REMOVER,
        }
        expected = {
            (category, situation)
            for category in CategoriaElemento
            for situation in source_drawing_situations
        }
        if len(combinations) != len(rules):
            raise DomainValidationError("Regras de simbologia não podem repetir combinações")
        if combinations != expected:
            raise DomainValidationError(
                "Catálogo deve possuir simbologia para toda categoria e situação de origem"
            )

    @staticmethod
    def _validate_symbol_signatures(
        signatures: tuple[AssinaturaSimbologia, ...], *, required: bool
    ) -> None:
        if not signatures:
            if required:
                raise DomainValidationError("Catálogo schema v2 deve possuir assinaturas visuais")
            return
        keys = {
            (
                signature.categoria_elemento,
                signature.situacao_projeto,
                signature.cor,
                signature.padrao_traco,
            )
            for signature in signatures
        }
        if len(keys) != len(signatures):
            raise DomainValidationError("Assinaturas visuais não podem ser duplicadas")
        covered_situations = {signature.situacao_projeto for signature in signatures}
        source_drawing_situations = {
            SituacaoProjeto.EXISTENTE,
            SituacaoProjeto.INSTALAR,
            SituacaoProjeto.REMOVER,
        }
        if covered_situations != source_drawing_situations:
            raise DomainValidationError(
                "Assinaturas visuais devem cobrir todas as situações de origem"
            )

    def itens_ativos(self, categoria: CategoriaElemento) -> tuple[ItemCatalogoType, ...]:
        return tuple(item for item in self.itens if item.ativo and item.categoria is categoria)

    def item_por_id(self, item_id: UUID) -> ItemCatalogoType | None:
        return next((item for item in self.itens if item.id == item_id), None)

    def criar_rascunho(self, *, novo_id: UUID, criado_em: datetime) -> CatalogoTecnico:
        if self.status is not StatusCatalogo.PUBLICADO:
            raise DomainValidationError("Somente um catálogo publicado pode originar novo rascunho")
        return replace(
            self,
            id=novo_id,
            versao=self.versao + 1,
            status=StatusCatalogo.RASCUNHO,
            criado_em=criado_em,
            publicado_em=None,
        )

    def com_itens(self, itens: tuple[ItemCatalogoType, ...]) -> CatalogoTecnico:
        if self.status is not StatusCatalogo.RASCUNHO:
            raise DomainValidationError("Catálogos publicados são imutáveis")
        return replace(self, itens=tuple(itens))

    def com_simbologia(
        self,
        regras: tuple[RegraSimbologia, ...],
        assinaturas: tuple[AssinaturaSimbologia, ...],
    ) -> CatalogoTecnico:
        if self.status is not StatusCatalogo.RASCUNHO:
            raise DomainValidationError("Catálogos publicados são imutáveis")
        return replace(
            self,
            regras_simbologia=tuple(regras),
            assinaturas_simbologia=tuple(assinaturas),
        )
