"""Agregado de projeto e relações físicas/elétricas confirmadas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import PurePosixPath, PureWindowsPath
from typing import ClassVar, TypeAlias
from uuid import UUID

from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoConexao,
    NivelRede,
    SituacaoProjeto,
    TipoAcaoRevisaoManual,
    TipoGeometria,
    TipoPontoRede,
    TipoVinculoObra,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.operations import VinculoObra
from zeny_project_handler.domain.project_metadata import ContatoSolicitante, MetadadosProjeto
from zeny_project_handler.domain.values import (
    CoordenadaCampo,
    GeometriaDocumento,
    decimal_value,
    required_text,
)


def _optional_text(value: str | None) -> str | None:
    normalized = value.strip() if value else None
    return normalized or None


@dataclass(frozen=True, slots=True, kw_only=True)
class FotoElemento:
    id: UUID
    caminho_relativo: str
    legenda: str | None = None
    sha256: str | None = None
    tipo_mime: str | None = None
    tamanho_bytes: int | None = None

    def __post_init__(self) -> None:
        normalized = required_text(
            self.caminho_relativo.replace("\\", "/"), field_name="caminho_relativo"
        )
        posix_path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(normalized)
        if posix_path.is_absolute() or windows_path.is_absolute() or ".." in posix_path.parts:
            raise DomainValidationError("Fotos devem usar caminhos relativos internos ao projeto")
        caption = self.legenda.strip() if self.legenda else None
        digest = self.sha256.strip().lower() if self.sha256 else None
        mime_type = self.tipo_mime.strip().lower() if self.tipo_mime else None
        metadata = (digest, mime_type, self.tamanho_bytes)
        if any(item is not None for item in metadata) and any(item is None for item in metadata):
            raise DomainValidationError("Foto deve registrar hash, tipo MIME e tamanho em conjunto")
        if digest is not None and not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise DomainValidationError("SHA-256 da foto é inválido")
        if mime_type is not None and mime_type not in {
            "image/jpeg",
            "image/png",
            "image/tiff",
            "image/webp",
        }:
            raise DomainValidationError("Tipo de arquivo da foto não é aceito")
        if self.tamanho_bytes is not None and self.tamanho_bytes <= 0:
            raise DomainValidationError("Tamanho da foto deve ser positivo")
        object.__setattr__(self, "caminho_relativo", posix_path.as_posix())
        object.__setattr__(self, "legenda", caption or None)
        object.__setattr__(self, "sha256", digest)
        object.__setattr__(self, "tipo_mime", mime_type)


@dataclass(frozen=True, slots=True, kw_only=True)
class ElementoProjeto:
    categoria: ClassVar[CategoriaElemento]

    id: UUID
    tipo_catalogo_id: UUID
    situacao: SituacaoProjeto
    referencia_desenho: str | None = None
    codigo_observado: str | None = None
    identificador_operacional: str | None = None
    geometria: GeometriaDocumento | None = None
    coordenada_campo: CoordenadaCampo | None = None
    fotos: tuple[FotoElemento, ...] = ()

    def __post_init__(self) -> None:
        reference = self.referencia_desenho.strip() if self.referencia_desenho else None
        photos = tuple(self.fotos)
        if len({photo.id for photo in photos}) != len(photos):
            raise DomainValidationError("IDs de fotos devem ser únicos por elemento")
        if len({photo.caminho_relativo.casefold() for photo in photos}) != len(photos):
            raise DomainValidationError("Um elemento não pode repetir o mesmo caminho de foto")
        object.__setattr__(self, "referencia_desenho", reference or None)
        object.__setattr__(self, "codigo_observado", _optional_text(self.codigo_observado))
        object.__setattr__(
            self,
            "identificador_operacional",
            _optional_text(self.identificador_operacional),
        )
        object.__setattr__(self, "fotos", photos)


@dataclass(frozen=True, slots=True, kw_only=True)
class Poste(ElementoProjeto):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.POSTE

    def __post_init__(self) -> None:
        ElementoProjeto.__post_init__(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class EstruturaMt(ElementoProjeto):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.ESTRUTURA_MT

    poste_id: UUID
    pontos_fixados_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        ElementoProjeto.__post_init__(self)
        fixed_points = tuple(self.pontos_fixados_ids)
        if len(set(fixed_points)) != len(fixed_points):
            raise DomainValidationError("Estrutura MT não pode repetir pontos fixados")
        object.__setattr__(self, "pontos_fixados_ids", fixed_points)


@dataclass(frozen=True, slots=True, kw_only=True)
class EstruturaBt(ElementoProjeto):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.ESTRUTURA_BT

    poste_id: UUID
    pontos_fixados_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        ElementoProjeto.__post_init__(self)
        fixed_points = tuple(self.pontos_fixados_ids)
        if len(set(fixed_points)) != len(fixed_points):
            raise DomainValidationError("Estrutura BT não pode repetir pontos fixados")
        object.__setattr__(self, "pontos_fixados_ids", fixed_points)


@dataclass(frozen=True, slots=True, kw_only=True)
class Cabo(ElementoProjeto):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.CABO

    ponto_origem_id: UUID
    ponto_destino_id: UUID
    comprimento_m: Decimal | None = None
    postes_apoio_ids: tuple[UUID, ...] = ()
    pontos_intermediarios_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        ElementoProjeto.__post_init__(self)
        if self.ponto_origem_id == self.ponto_destino_id:
            raise DomainValidationError("Cabo deve conectar dois pontos distintos")
        length = self.comprimento_m
        if length is not None:
            length = decimal_value(length, field_name="comprimento_m")
            if length <= 0:
                raise DomainValidationError("Comprimento do cabo deve ser positivo")
        supports = tuple(self.postes_apoio_ids)
        intermediate_points = tuple(self.pontos_intermediarios_ids)
        if len(set(supports)) != len(supports):
            raise DomainValidationError("Cabo não pode repetir postes de apoio")
        if len(set(intermediate_points)) != len(intermediate_points):
            raise DomainValidationError("Cabo não pode repetir pontos intermediários")
        if {self.ponto_origem_id, self.ponto_destino_id} & set(intermediate_points):
            raise DomainValidationError("Extremidades não podem se repetir no percurso do cabo")
        if self.geometria is not None and self.geometria.tipo is not TipoGeometria.POLILINHA:
            raise DomainValidationError("Geometria de cabo deve ser uma polilinha")
        object.__setattr__(self, "comprimento_m", length)
        object.__setattr__(self, "postes_apoio_ids", supports)
        object.__setattr__(self, "pontos_intermediarios_ids", intermediate_points)

    @property
    def percurso_pontos_ids(self) -> tuple[UUID, ...]:
        return (self.ponto_origem_id, *self.pontos_intermediarios_ids, self.ponto_destino_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class Equipamento(ElementoProjeto):
    categoria: ClassVar[CategoriaElemento] = CategoriaElemento.EQUIPAMENTO

    poste_id: UUID

    def __post_init__(self) -> None:
        ElementoProjeto.__post_init__(self)


ElementoProjetoType: TypeAlias = Poste | EstruturaMt | EstruturaBt | Cabo | Equipamento


@dataclass(frozen=True, slots=True, kw_only=True)
class RelacaoConfirmada:
    id: UUID
    tipo_relacao: str
    origem_id: UUID
    destino_id: UUID

    def __post_init__(self) -> None:
        if self.origem_id == self.destino_id:
            raise DomainValidationError("Relação confirmada deve ligar referências distintas")
        object.__setattr__(
            self,
            "tipo_relacao",
            required_text(self.tipo_relacao, field_name="tipo_relacao"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RegistroRevisaoManual:
    id: UUID
    acao: TipoAcaoRevisaoManual
    referencia_criada_id: UUID
    revisor: str
    realizada_em: datetime
    motivo: str | None = None

    def __post_init__(self) -> None:
        if self.realizada_em.tzinfo is None:
            raise DomainValidationError("Data da revisão manual deve possuir fuso horário")
        object.__setattr__(self, "revisor", required_text(self.revisor, field_name="revisor"))
        object.__setattr__(self, "motivo", _optional_text(self.motivo))


@dataclass(frozen=True, slots=True, kw_only=True)
class PontoRede:
    id: UUID
    poste_id: UUID | None
    nome: str
    nivel_rede: NivelRede
    nivel_tensao_opcao_id: UUID
    configuracao_fases_opcao_id: UUID
    tipo: TipoPontoRede = TipoPontoRede.POSTE
    geometria: GeometriaDocumento | None = None
    coordenada_campo: CoordenadaCampo | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "nome", required_text(self.nome, field_name="nome"))
        if self.tipo is TipoPontoRede.POSTE and self.poste_id is None:
            raise DomainValidationError("Ponto de poste deve referenciar um poste")


@dataclass(frozen=True, slots=True, kw_only=True)
class TerminalEquipamento:
    id: UUID
    equipamento_id: UUID
    nome: str
    nivel_rede: NivelRede
    nivel_tensao_opcao_id: UUID
    configuracao_fases_opcao_id: UUID
    ponto_rede_id: UUID | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "nome", required_text(self.nome, field_name="nome"))


@dataclass(frozen=True, slots=True, kw_only=True)
class ConexaoInternaEquipamento:
    id: UUID
    equipamento_id: UUID
    terminal_origem_id: UUID
    terminal_destino_id: UUID
    estado: EstadoConexao

    def __post_init__(self) -> None:
        if self.terminal_origem_id == self.terminal_destino_id:
            raise DomainValidationError("Conexão interna deve usar terminais distintos")


@dataclass(frozen=True, slots=True, kw_only=True)
class Projeto:
    id: UUID
    nome: str
    catalogo_versao_id: UUID
    criado_em: datetime
    documentos: tuple[DocumentoProjeto, ...] = ()
    ordem_leitura_paginas: tuple[UUID, ...] = ()
    elementos: tuple[ElementoProjetoType, ...] = ()
    pontos_rede: tuple[PontoRede, ...] = ()
    terminais: tuple[TerminalEquipamento, ...] = ()
    conexoes_internas: tuple[ConexaoInternaEquipamento, ...] = ()
    vinculos_obra: tuple[VinculoObra, ...] = ()
    relacoes_confirmadas: tuple[RelacaoConfirmada, ...] = ()
    historico_revisao_manual: tuple[RegistroRevisaoManual, ...] = ()
    metadados: MetadadosProjeto | None = None
    contato_solicitante: ContatoSolicitante | None = None

    def __post_init__(self) -> None:
        name = required_text(self.nome, field_name="nome")
        if self.criado_em.tzinfo is None:
            raise DomainValidationError("Data de criação do projeto deve possuir fuso horário")

        documents = tuple(self.documentos)
        page_ids = tuple(page.id for document in documents for page in document.paginas)
        reading_order = tuple(self.ordem_leitura_paginas) or page_ids
        if len(reading_order) != len(page_ids) or set(reading_order) != set(page_ids):
            raise DomainValidationError(
                "Ordem de leitura deve conter todas as páginas do projeto uma única vez"
            )
        elements = tuple(self.elementos)
        points = tuple(self.pontos_rede)
        terminals = tuple(self.terminais)
        internal_connections = tuple(self.conexoes_internas)
        work_links = tuple(self.vinculos_obra)
        confirmed_relations = tuple(self.relacoes_confirmadas)
        manual_review_history = tuple(self.historico_revisao_manual)

        self._validate_unique_ids(
            documents,
            elements,
            points,
            terminals,
            internal_connections,
            work_links,
            confirmed_relations,
            manual_review_history,
        )
        self._validate_relationships(
            documents,
            elements,
            points,
            terminals,
            internal_connections,
            work_links,
            confirmed_relations,
            manual_review_history,
        )

        object.__setattr__(self, "nome", name)
        object.__setattr__(self, "documentos", documents)
        object.__setattr__(self, "ordem_leitura_paginas", reading_order)
        object.__setattr__(self, "elementos", elements)
        object.__setattr__(self, "pontos_rede", points)
        object.__setattr__(self, "terminais", terminals)
        object.__setattr__(self, "conexoes_internas", internal_connections)
        object.__setattr__(self, "vinculos_obra", work_links)
        object.__setattr__(self, "relacoes_confirmadas", confirmed_relations)
        object.__setattr__(self, "historico_revisao_manual", manual_review_history)

    @staticmethod
    def _validate_unique_ids(
        documents: tuple[DocumentoProjeto, ...],
        elements: tuple[ElementoProjetoType, ...],
        points: tuple[PontoRede, ...],
        terminals: tuple[TerminalEquipamento, ...],
        internal_connections: tuple[ConexaoInternaEquipamento, ...],
        work_links: tuple[VinculoObra, ...],
        confirmed_relations: tuple[RelacaoConfirmada, ...],
        manual_review_history: tuple[RegistroRevisaoManual, ...],
    ) -> None:
        entity_ids = [
            *[document.id for document in documents],
            *[element.id for element in elements],
            *[point.id for point in points],
            *[terminal.id for terminal in terminals],
            *[connection.id for connection in internal_connections],
            *[link.id for link in work_links],
            *[relation.id for relation in confirmed_relations],
            *[record.id for record in manual_review_history],
        ]
        if len(set(entity_ids)) != len(entity_ids):
            raise DomainValidationError("IDs de entidades devem ser únicos no projeto")
        page_ids = [page.id for document in documents for page in document.paginas]
        if len(set(page_ids)) != len(page_ids):
            raise DomainValidationError("IDs de páginas devem ser únicos no projeto")

    @staticmethod
    def _validate_relationships(
        documents: tuple[DocumentoProjeto, ...],
        elements: tuple[ElementoProjetoType, ...],
        points: tuple[PontoRede, ...],
        terminals: tuple[TerminalEquipamento, ...],
        internal_connections: tuple[ConexaoInternaEquipamento, ...],
        work_links: tuple[VinculoObra, ...],
        confirmed_relations: tuple[RelacaoConfirmada, ...],
        manual_review_history: tuple[RegistroRevisaoManual, ...],
    ) -> None:
        page_ids = {page.id for document in documents for page in document.paginas}
        Projeto._validate_geometry_pages(elements, points, page_ids)

        poles = {element.id: element for element in elements if isinstance(element, Poste)}
        equipment = {
            element.id: element for element in elements if isinstance(element, Equipamento)
        }
        point_by_id = {point.id: point for point in points}
        terminal_by_id = {terminal.id: terminal for terminal in terminals}

        Projeto._validate_points(points, poles)
        Projeto._validate_elements(elements, poles, point_by_id)
        Projeto._validate_terminals(terminals, equipment, point_by_id)
        Projeto._validate_internal_connections(internal_connections, terminal_by_id)
        Projeto._validate_work_links(work_links, {element.id: element for element in elements})
        reference_ids = {
            *[element.id for element in elements],
            *[point.id for point in points],
            *[terminal.id for terminal in terminals],
        }
        for relation in confirmed_relations:
            if relation.origem_id not in reference_ids or relation.destino_id not in reference_ids:
                raise DomainValidationError(
                    "Relação confirmada deve referenciar entidades existentes no projeto"
                )
        created_ids = {element.id for element in elements} | {
            relation.id for relation in confirmed_relations
        }
        if any(record.referencia_criada_id not in created_ids for record in manual_review_history):
            raise DomainValidationError(
                "Histórico de revisão manual deve referenciar uma criação existente"
            )

    @staticmethod
    def _validate_geometry_pages(
        elements: tuple[ElementoProjetoType, ...],
        points: tuple[PontoRede, ...],
        page_ids: set[UUID],
    ) -> None:
        geometries = [element.geometria for element in elements]
        geometries.extend(point.geometria for point in points)
        for geometry in geometries:
            if geometry is not None and geometry.pagina_id not in page_ids:
                raise DomainValidationError("Geometria deve apontar para uma página do projeto")

    @staticmethod
    def _validate_points(points: tuple[PontoRede, ...], poles: dict[UUID, Poste]) -> None:
        for point in points:
            if point.poste_id is not None and point.poste_id not in poles:
                raise DomainValidationError("Poste associado ao ponto de rede deve existir")

    @staticmethod
    def _validate_elements(
        elements: tuple[ElementoProjetoType, ...],
        poles: dict[UUID, Poste],
        point_by_id: dict[UUID, PontoRede],
    ) -> None:
        for element in elements:
            if (
                isinstance(element, (EstruturaMt, EstruturaBt, Equipamento))
                and element.poste_id not in poles
            ):
                raise DomainValidationError("Estruturas e equipamentos devem pertencer a um poste")
            if isinstance(element, Cabo):
                Projeto._validate_cable(element, poles, point_by_id)
            if isinstance(element, (EstruturaMt, EstruturaBt)):
                Projeto._validate_structure(element, point_by_id)

    @staticmethod
    def _validate_cable(
        cable: Cabo, poles: dict[UUID, Poste], point_by_id: dict[UUID, PontoRede]
    ) -> None:
        if cable.ponto_origem_id not in point_by_id or cable.ponto_destino_id not in point_by_id:
            raise DomainValidationError("Extremidades do cabo devem existir no projeto")
        if any(post_id not in poles for post_id in cable.postes_apoio_ids):
            raise DomainValidationError("Postes de apoio do cabo devem existir no projeto")
        if any(point_id not in point_by_id for point_id in cable.pontos_intermediarios_ids):
            raise DomainValidationError("Pontos intermediários do cabo devem existir no projeto")

    @staticmethod
    def _validate_structure(
        structure: EstruturaMt | EstruturaBt, point_by_id: dict[UUID, PontoRede]
    ) -> None:
        expected_level = NivelRede.MT if isinstance(structure, EstruturaMt) else NivelRede.BT
        for point_id in structure.pontos_fixados_ids:
            fixed_point = point_by_id.get(point_id)
            if fixed_point is None:
                raise DomainValidationError("Ponto fixado pela estrutura deve existir")
            if (
                fixed_point.poste_id != structure.poste_id
                or fixed_point.nivel_rede is not expected_level
            ):
                raise DomainValidationError(
                    "Ponto fixado deve estar no mesmo poste e nível da estrutura"
                )

    @staticmethod
    def _validate_terminals(
        terminals: tuple[TerminalEquipamento, ...],
        equipment: dict[UUID, Equipamento],
        point_by_id: dict[UUID, PontoRede],
    ) -> None:
        for terminal in terminals:
            if terminal.equipamento_id not in equipment:
                raise DomainValidationError("Terminal deve pertencer a um equipamento")
            if terminal.ponto_rede_id is not None:
                connected_point = point_by_id.get(terminal.ponto_rede_id)
                if connected_point is None:
                    raise DomainValidationError(
                        "Terminal conectado deve apontar para um ponto existente"
                    )
                if (
                    terminal.nivel_rede is not connected_point.nivel_rede
                    or terminal.nivel_tensao_opcao_id != connected_point.nivel_tensao_opcao_id
                    or terminal.configuracao_fases_opcao_id
                    != connected_point.configuracao_fases_opcao_id
                ):
                    raise DomainValidationError("Terminal e ponto conectado devem ser compatíveis")

    @staticmethod
    def _validate_internal_connections(
        internal_connections: tuple[ConexaoInternaEquipamento, ...],
        terminal_by_id: dict[UUID, TerminalEquipamento],
    ) -> None:
        for connection in internal_connections:
            origin = terminal_by_id.get(connection.terminal_origem_id)
            destination = terminal_by_id.get(connection.terminal_destino_id)
            if origin is None or destination is None:
                raise DomainValidationError("Conexão interna deve referenciar terminais existentes")
            if (
                origin.equipamento_id != connection.equipamento_id
                or destination.equipamento_id != connection.equipamento_id
            ):
                raise DomainValidationError(
                    "Conexão interna deve unir terminais do mesmo equipamento"
                )

    @staticmethod
    def _validate_work_links(
        work_links: tuple[VinculoObra, ...],
        element_by_id: dict[UUID, ElementoProjetoType],
    ) -> None:
        pairs: set[tuple[UUID, UUID]] = set()
        for link in work_links:
            origin = element_by_id.get(link.elemento_origem_id)
            destination = element_by_id.get(link.elemento_destino_id)
            if origin is None or destination is None:
                raise DomainValidationError("Vínculo de obra deve referenciar elementos existentes")
            if origin.categoria is not destination.categoria:
                raise DomainValidationError(
                    "Vínculo de obra deve preservar a categoria do elemento"
                )
            if origin.situacao is not SituacaoProjeto.REMOVER:
                raise DomainValidationError("Origem do vínculo de obra deve ser uma retirada")
            if destination.situacao is not SituacaoProjeto.INSTALAR:
                raise DomainValidationError("Destino do vínculo de obra deve ser uma instalação")
            if (
                link.tipo is TipoVinculoObra.REALOCACAO
                and origin.tipo_catalogo_id != destination.tipo_catalogo_id
            ):
                raise DomainValidationError("Realocação deve preservar o tipo catalogado")
            pair = (origin.id, destination.id)
            if pair in pairs:
                raise DomainValidationError("Vínculo de obra duplicado")
            pairs.add(pair)


def validar_projeto_com_catalogo(projeto: Projeto, catalogo: CatalogoTecnico) -> None:
    """Valide referências configuráveis sem acoplar o projeto à persistência."""
    if projeto.catalogo_versao_id != catalogo.id:
        raise DomainValidationError("Projeto deve referenciar a versão de catálogo validada")

    item_by_id = {item.id: item for item in catalogo.itens}
    option_group_by_id = {
        option.id: group.chave for group in catalogo.grupos_opcao for option in group.opcoes
    }

    for element in projeto.elementos:
        item = item_by_id.get(element.tipo_catalogo_id)
        if item is None or item.categoria is not element.categoria:
            raise DomainValidationError("Elemento deve referenciar item da categoria correta")

    for point in projeto.pontos_rede:
        if option_group_by_id.get(point.nivel_tensao_opcao_id) != "nivel_tensao":
            raise DomainValidationError("Ponto de rede deve usar uma opção de nível de tensão")
        if option_group_by_id.get(point.configuracao_fases_opcao_id) != "configuracao_fases":
            raise DomainValidationError("Ponto de rede deve usar uma opção de fases")

    for terminal in projeto.terminais:
        if option_group_by_id.get(terminal.nivel_tensao_opcao_id) != "nivel_tensao":
            raise DomainValidationError("Terminal deve usar uma opção de nível de tensão")
        if option_group_by_id.get(terminal.configuracao_fases_opcao_id) != "configuracao_fases":
            raise DomainValidationError("Terminal deve usar uma opção de fases")
