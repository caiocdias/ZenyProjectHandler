"""Casos de uso da reconstrução e revisão de conexões do grafo."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid5

from zeny_project_handler.application.errors import (
    ProjetoNaoEncontradoError,
    ReconstrucaoGrafoError,
)
from zeny_project_handler.domain.enums import TipoAcaoRevisaoManual
from zeny_project_handler.domain.graph import ResultadoReconstrucaoGrafo
from zeny_project_handler.domain.project import (
    Equipamento,
    Projeto,
    RegistroRevisaoManual,
    RelacaoConfirmada,
)
from zeny_project_handler.domain.values import GeometriaDocumento
from zeny_project_handler.ports.graph import ReconstrutorGrafoPort
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler.ports.persistence import UnitOfWorkPort


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumoProjetoGrafo:
    projeto_id: UUID
    nome: str
    elementos_confirmados: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SessaoGrafoProjeto:
    projeto: Projeto
    resultado: ResultadoReconstrucaoGrafo
    fontes_pdf: tuple[ReferenciaFontePdf, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class DestinoPdfGrafo:
    folha_numero: int
    geometria: GeometriaDocumento


class ServicoGrafoProjeto:
    def __init__(
        self,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        reconstrutor: ReconstrutorGrafoPort,
        *,
        relogio: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work = unidade_de_trabalho
        self._builder = reconstrutor
        self._clock = relogio or (lambda: datetime.now(UTC))

    def listar_projetos(self) -> tuple[ResumoProjetoGrafo, ...]:
        with self._unit_of_work() as work:
            return tuple(
                ResumoProjetoGrafo(
                    projeto_id=project.id,
                    nome=project.nome,
                    elementos_confirmados=len(project.elementos),
                )
                for project in work.projetos.listar()
            )

    def reconstruir(self, projeto_id: UUID) -> SessaoGrafoProjeto:
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para reconstrução do grafo")
            catalog = work.catalogos.obter(project.catalogo_versao_id)
            if catalog is None:
                raise ReconstrucaoGrafoError("Catálogo do projeto não está disponível")
            sources = tuple(
                source
                for document in project.documentos
                if (source := work.fontes_pdf.obter(document.id)) is not None
            )
            return SessaoGrafoProjeto(
                projeto=project,
                resultado=self._builder.reconstruir(project, catalog),
                fontes_pdf=sources,
            )

    def confirmar_sugestao(
        self,
        projeto_id: UUID,
        sugestao_id: UUID,
        *,
        assinatura_esperada: str,
        revisor: str,
    ) -> SessaoGrafoProjeto:
        reviewer = revisor.strip()
        if not reviewer:
            raise ReconstrucaoGrafoError("Informe o responsável pela confirmação")
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para confirmação")
            catalog = work.catalogos.obter(project.catalogo_versao_id)
            if catalog is None:
                raise ReconstrucaoGrafoError("Catálogo do projeto não está disponível")
            current = self._builder.reconstruir(project, catalog)
            if current.assinatura != assinatura_esperada:
                raise ReconstrucaoGrafoError(
                    "O projeto mudou desde a reconstrução; reconstrua o grafo antes de confirmar"
                )
            suggestion = next(
                (item for item in current.sugestoes if item.id == sugestao_id),
                None,
            )
            if suggestion is None:
                raise ReconstrucaoGrafoError("Sugestão não pertence ao grafo atual")
            pair = frozenset((suggestion.origem_id, suggestion.destino_id))
            if any(
                frozenset((item.origem_id, item.destino_id)) == pair
                for item in project.relacoes_confirmadas
            ):
                raise ReconstrucaoGrafoError("A conexão já foi confirmada")
            relation = RelacaoConfirmada(
                id=uuid5(suggestion.id, "relacao-confirmada"),
                tipo_relacao="CONEXAO_ELETRICA_CONFIRMADA",
                origem_id=suggestion.origem_id,
                destino_id=suggestion.destino_id,
            )
            record = RegistroRevisaoManual(
                id=uuid5(relation.id, "registro-revisao"),
                acao=TipoAcaoRevisaoManual.CRIAR_RELACAO,
                referencia_criada_id=relation.id,
                revisor=reviewer,
                realizada_em=self._aware_now(),
                motivo=suggestion.justificativa,
            )
            work.projetos.salvar(
                replace(
                    project,
                    relacoes_confirmadas=(*project.relacoes_confirmadas, relation),
                    historico_revisao_manual=(*project.historico_revisao_manual, record),
                )
            )
            work.commit()
        return self.reconstruir(projeto_id)

    def localizar_referencia(
        self, session: SessaoGrafoProjeto, referencias: tuple[UUID, ...]
    ) -> DestinoPdfGrafo | None:
        for reference in referencias:
            geometry = _reference_geometry(session.projeto, reference)
            if geometry is None:
                continue
            page_number = _project_page_number(session.projeto, geometry.pagina_id)
            if page_number is not None:
                return DestinoPdfGrafo(folha_numero=page_number, geometria=geometry)
        return None

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Relógio da aplicação deve retornar data com fuso horário")
        return value


def _reference_geometry(project: Projeto, reference_id: UUID) -> GeometriaDocumento | None:
    element = next((item for item in project.elementos if item.id == reference_id), None)
    if element is not None:
        return element.geometria
    point = next((item for item in project.pontos_rede if item.id == reference_id), None)
    if point is not None:
        if point.geometria is not None:
            return point.geometria
        pole = next((item for item in project.elementos if item.id == point.poste_id), None)
        return pole.geometria if pole is not None else None
    terminal = next((item for item in project.terminais if item.id == reference_id), None)
    if terminal is None:
        return None
    equipment = next(
        (
            item
            for item in project.elementos
            if isinstance(item, Equipamento) and item.id == terminal.equipamento_id
        ),
        None,
    )
    return equipment.geometria if equipment is not None else None


def _project_page_number(project: Projeto, page_id: UUID) -> int | None:
    number = 0
    for document in project.documentos:
        for page in document.paginas:
            number += 1
            if page.id == page_id:
                return number
    return None
