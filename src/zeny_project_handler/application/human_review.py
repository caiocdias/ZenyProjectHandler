"""Casos de uso transacionais da revisão humana de propostas."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    EvidenciaDocumento,
    ExecucaoAnalise,
    PropostaElemento,
    PropostaRelacao,
    ReferenciaProposta,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, TipoCabo
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    NivelRede,
    SituacaoProjeto,
    TipoAcaoRevisaoManual,
    TipoDecisaoRevisao,
    TipoGeometria,
    TipoPontoRede,
)
from zeny_project_handler.domain.project import (
    Cabo,
    ElementoProjetoType,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    PontoRede,
    Poste,
    Projeto,
    RegistroRevisaoManual,
    RelacaoConfirmada,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler.ports.persistence import UnitOfWorkPort

from .analysis_regions import RegiaoAnalise, agrupar_regioes_da_analise
from .errors import ProjetoNaoEncontradoError, RevisaoHumanaError


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumoProjetoRevisao:
    projeto_id: UUID
    nome: str
    propostas_pendentes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ResumoExecucaoRevisao:
    execucao_id: UUID
    iniciada_em: datetime
    propostas: int
    propostas_pendentes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SessaoRevisao:
    projeto: Projeto
    catalogo: CatalogoTecnico
    execucao: ExecucaoAnalise
    propostas: tuple[ReferenciaProposta, ...]
    regioes: tuple[RegiaoAnalise, ...]
    evidencias: tuple[EvidenciaDocumento, ...]
    decisoes: tuple[DecisaoRevisao, ...]
    fontes_pdf: tuple[ReferenciaFontePdf, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class DadosElementoRevisao:
    categoria: CategoriaElemento
    tipo_catalogo_id: UUID
    situacao: SituacaoProjeto
    geometria: GeometriaDocumento
    codigo_observado: str | None = None
    poste_id: UUID | None = None
    ponto_origem_id: UUID | None = None
    ponto_destino_id: UUID | None = None


class ServicoRevisaoHumana:
    def __init__(
        self,
        unidade_de_trabalho: Callable[[], UnitOfWorkPort],
        *,
        relogio: Callable[[], datetime] | None = None,
        gerar_id: Callable[[], UUID] | None = None,
    ) -> None:
        self._unit_of_work = unidade_de_trabalho
        self._clock = relogio or (lambda: datetime.now(UTC))
        self._generate_id = gerar_id or uuid4

    def listar_projetos(self) -> tuple[ResumoProjetoRevisao, ...]:
        with self._unit_of_work() as work:
            summaries: list[ResumoProjetoRevisao] = []
            for project in work.projetos.listar():
                proposals = self._latest_proposals(work, project.id)
                pending = sum(
                    item.estado_revisao in {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFLITANTE}
                    for item in proposals
                )
                if proposals:
                    summaries.append(
                        ResumoProjetoRevisao(
                            projeto_id=project.id,
                            nome=project.nome,
                            propostas_pendentes=pending,
                        )
                    )
            return tuple(summaries)

    def carregar_sessao(
        self,
        projeto_id: UUID,
        execucao_id: UUID | None = None,
    ) -> SessaoRevisao:
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para revisão")
            catalog = work.catalogos.obter(project.catalogo_versao_id)
            if catalog is None:
                raise RevisaoHumanaError("Catálogo do projeto não está disponível")
            execution = self._review_execution(work, project.id, execucao_id)
            proposals = work.propostas.listar_da_execucao(execution.id)
            evidence_execution_id = _source_evidence_execution_id(execution)
            evidence = work.evidencias.listar_da_execucao(evidence_execution_id)
            if not evidence and evidence_execution_id != execution.id:
                evidence = work.evidencias.listar_da_execucao(execution.id)
            decisions = tuple(
                decision
                for proposal in proposals
                if (decision := work.decisoes_revisao.obter_da_proposta(proposal.id)) is not None
            )
            sources = tuple(
                source
                for document in project.documentos
                if (source := work.fontes_pdf.obter(document.id)) is not None
            )
            return SessaoRevisao(
                projeto=project,
                catalogo=catalog,
                execucao=execution,
                propostas=proposals,
                regioes=agrupar_regioes_da_analise(
                    proposals,
                    evidence,
                    project.documentos,
                ),
                evidencias=evidence,
                decisoes=decisions,
                fontes_pdf=sources,
            )

    def listar_execucoes(self, projeto_id: UUID) -> tuple[ResumoExecucaoRevisao, ...]:
        with self._unit_of_work() as work:
            if work.projetos.obter(projeto_id) is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para revisão")
            summaries: list[ResumoExecucaoRevisao] = []
            for execution in work.execucoes_analise.listar_do_projeto(projeto_id):
                proposals = work.propostas.listar_da_execucao(execution.id)
                if execution.estado is not EstadoExecucaoAnalise.CONCLUIDA or not proposals:
                    continue
                summaries.append(
                    ResumoExecucaoRevisao(
                        execucao_id=execution.id,
                        iniciada_em=execution.iniciada_em,
                        propostas=len(proposals),
                        propostas_pendentes=sum(
                            item.estado_revisao
                            in {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFLITANTE}
                            for item in proposals
                        ),
                    )
                )
            return tuple(summaries)

    def confirmar_elemento(
        self,
        proposta_id: UUID,
        dados: DadosElementoRevisao,
        *,
        revisor: str,
        motivo: str | None = None,
    ) -> DecisaoRevisao:
        now = self._aware_now()
        with self._unit_of_work() as work:
            proposal, project, catalog = self._element_context(work, proposta_id)
            self._ensure_undecided(work, proposal)
            if self._was_rejected_before(work, project.id, proposal):
                raise RevisaoHumanaError(
                    "Uma proposta semanticamente equivalente já foi rejeitada neste projeto"
                )
            self._validate_catalog_item(catalog, dados)
            element_id = uuid5(proposal.id, "elemento-confirmado")
            element, created_points = _build_element(element_id, dados, catalog)
            adjusted = (
                proposal.categoria is not dados.categoria
                or proposal.tipo_catalogo_sugerido_id != dados.tipo_catalogo_id
                or proposal.situacao_projeto is not dados.situacao
                or proposal.geometria != dados.geometria
            )
            updated_proposal = replace(
                proposal,
                categoria=dados.categoria,
                tipo_catalogo_sugerido_id=dados.tipo_catalogo_id,
                situacao_projeto=dados.situacao,
                geometria=dados.geometria,
                codigo_observado=dados.codigo_observado or proposal.codigo_observado,
                estado_revisao=EstadoRevisao.CONFIRMADA,
            )
            updated_project = replace(
                project,
                elementos=(*project.elementos, element),
                pontos_rede=(*project.pontos_rede, *created_points),
            )
            decision = DecisaoRevisao(
                id=uuid5(proposal.id, "decisao-revisao"),
                proposta_id=proposal.id,
                decisao=(TipoDecisaoRevisao.AJUSTAR if adjusted else TipoDecisaoRevisao.ACEITAR),
                revisor=revisor,
                decidida_em=now,
                elemento_confirmado_id=element.id,
                motivo=motivo,
            )
            work.projetos.salvar(updated_project)
            work.propostas.salvar(updated_proposal)
            work.decisoes_revisao.salvar(decision)
            work.commit()
            return decision

    def confirmar_relacao(
        self,
        proposta_id: UUID,
        *,
        revisor: str,
        motivo: str | None = None,
    ) -> DecisaoRevisao:
        now = self._aware_now()
        with self._unit_of_work() as work:
            proposal, project = self._relation_context(work, proposta_id)
            self._ensure_undecided(work, proposal)
            origin = self._confirmed_reference(work, project, proposal.origem_referencia_id)
            destination = self._confirmed_reference(work, project, proposal.destino_referencia_id)
            relation = RelacaoConfirmada(
                id=uuid5(proposal.id, "relacao-confirmada"),
                tipo_relacao=proposal.tipo_relacao,
                origem_id=origin,
                destino_id=destination,
            )
            if any(
                item.tipo_relacao == relation.tipo_relacao
                and item.origem_id == relation.origem_id
                and item.destino_id == relation.destino_id
                for item in project.relacoes_confirmadas
            ):
                raise RevisaoHumanaError("Esta relação já está confirmada no projeto")
            updated_project = replace(
                project,
                relacoes_confirmadas=(*project.relacoes_confirmadas, relation),
            )
            updated_proposal = replace(proposal, estado_revisao=EstadoRevisao.CONFIRMADA)
            decision = DecisaoRevisao(
                id=uuid5(proposal.id, "decisao-revisao"),
                proposta_id=proposal.id,
                decisao=TipoDecisaoRevisao.ACEITAR,
                revisor=revisor,
                decidida_em=now,
                relacao_confirmada_id=relation.id,
                motivo=motivo,
            )
            work.projetos.salvar(updated_project)
            work.propostas.salvar(updated_proposal)
            work.decisoes_revisao.salvar(decision)
            work.commit()
            return decision

    def rejeitar(
        self,
        proposta_id: UUID,
        *,
        revisor: str,
        motivo: str | None = None,
    ) -> DecisaoRevisao:
        now = self._aware_now()
        with self._unit_of_work() as work:
            proposal = work.propostas.obter(proposta_id)
            if proposal is None:
                raise RevisaoHumanaError("Proposta não encontrada")
            self._ensure_undecided(work, proposal)
            decision = DecisaoRevisao(
                id=uuid5(proposal.id, "decisao-revisao"),
                proposta_id=proposal.id,
                decisao=TipoDecisaoRevisao.REJEITAR,
                revisor=revisor,
                decidida_em=now,
                motivo=motivo,
            )
            work.propostas.salvar(replace(proposal, estado_revisao=EstadoRevisao.REJEITADA))
            work.decisoes_revisao.salvar(decision)
            work.commit()
            return decision

    def criar_elemento_manual(
        self,
        projeto_id: UUID,
        dados: DadosElementoRevisao,
        *,
        revisor: str,
        motivo: str | None = None,
    ) -> UUID:
        now = self._aware_now()
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para revisão")
            catalog = work.catalogos.obter(project.catalogo_versao_id)
            if catalog is None:
                raise RevisaoHumanaError("Catálogo do projeto não está disponível")
            self._validate_catalog_item(catalog, dados)
            element, created_points = _build_element(
                self._generate_id(),
                dados,
                catalog,
            )
            record = RegistroRevisaoManual(
                id=self._generate_id(),
                acao=TipoAcaoRevisaoManual.CRIAR_ELEMENTO,
                referencia_criada_id=element.id,
                revisor=revisor,
                realizada_em=now,
                motivo=motivo,
            )
            work.projetos.salvar(
                replace(
                    project,
                    elementos=(*project.elementos, element),
                    pontos_rede=(*project.pontos_rede, *created_points),
                    historico_revisao_manual=(*project.historico_revisao_manual, record),
                )
            )
            work.commit()
            return element.id

    def criar_relacao_manual(
        self,
        projeto_id: UUID,
        *,
        tipo_relacao: str,
        origem_id: UUID,
        destino_id: UUID,
        revisor: str,
        motivo: str | None = None,
    ) -> UUID:
        now = self._aware_now()
        with self._unit_of_work() as work:
            project = work.projetos.obter(projeto_id)
            if project is None:
                raise ProjetoNaoEncontradoError("Projeto não encontrado para revisão")
            relation = RelacaoConfirmada(
                id=self._generate_id(),
                tipo_relacao=tipo_relacao,
                origem_id=origem_id,
                destino_id=destino_id,
            )
            record = RegistroRevisaoManual(
                id=self._generate_id(),
                acao=TipoAcaoRevisaoManual.CRIAR_RELACAO,
                referencia_criada_id=relation.id,
                revisor=revisor,
                realizada_em=now,
                motivo=motivo,
            )
            work.projetos.salvar(
                replace(
                    project,
                    relacoes_confirmadas=(*project.relacoes_confirmadas, relation),
                    historico_revisao_manual=(*project.historico_revisao_manual, record),
                )
            )
            work.commit()
            return relation.id

    def _latest_proposals(
        self,
        work: UnitOfWorkPort,
        project_id: UUID,
    ) -> tuple[ReferenciaProposta, ...]:
        executions = reversed(work.execucoes_analise.listar_do_projeto(project_id))
        for execution in executions:
            proposals = work.propostas.listar_da_execucao(execution.id)
            if proposals:
                return proposals
        return ()

    def _review_execution(
        self,
        work: UnitOfWorkPort,
        project_id: UUID,
        execution_id: UUID | None,
    ) -> ExecucaoAnalise:
        executions = work.execucoes_analise.listar_do_projeto(project_id)
        if execution_id is not None:
            execution = work.execucoes_analise.obter(execution_id)
            if execution is None or execution.projeto_id != project_id:
                raise RevisaoHumanaError("Execução não pertence ao projeto")
            if not work.propostas.listar_da_execucao(execution.id):
                raise RevisaoHumanaError("Execução não possui propostas para revisão")
            return execution
        for execution in reversed(executions):
            has_proposals = bool(work.propostas.listar_da_execucao(execution.id))
            if execution.estado is EstadoExecucaoAnalise.CONCLUIDA and has_proposals:
                return execution
        raise RevisaoHumanaError("Projeto não possui propostas concluídas para revisão")

    def _element_context(
        self,
        work: UnitOfWorkPort,
        proposal_id: UUID,
    ) -> tuple[PropostaElemento, Projeto, CatalogoTecnico]:
        proposal = work.propostas.obter(proposal_id)
        if not isinstance(proposal, PropostaElemento):
            raise RevisaoHumanaError("Proposta de elemento não encontrada")
        execution = work.execucoes_analise.obter(proposal.execucao_id)
        if execution is None:
            raise RevisaoHumanaError("Execução da proposta não está disponível")
        project = work.projetos.obter(execution.projeto_id)
        if project is None:
            raise ProjetoNaoEncontradoError("Projeto da proposta não foi encontrado")
        catalog = work.catalogos.obter(project.catalogo_versao_id)
        if catalog is None:
            raise RevisaoHumanaError("Catálogo do projeto não está disponível")
        return proposal, project, catalog

    def _relation_context(
        self,
        work: UnitOfWorkPort,
        proposal_id: UUID,
    ) -> tuple[PropostaRelacao, Projeto]:
        proposal = work.propostas.obter(proposal_id)
        if not isinstance(proposal, PropostaRelacao):
            raise RevisaoHumanaError("Proposta de relação não encontrada")
        execution = work.execucoes_analise.obter(proposal.execucao_id)
        if execution is None:
            raise RevisaoHumanaError("Execução da proposta não está disponível")
        project = work.projetos.obter(execution.projeto_id)
        if project is None:
            raise ProjetoNaoEncontradoError("Projeto da proposta não foi encontrado")
        return proposal, project

    def _ensure_undecided(self, work: UnitOfWorkPort, proposal: ReferenciaProposta) -> None:
        if work.decisoes_revisao.obter_da_proposta(proposal.id) is not None:
            raise RevisaoHumanaError("Proposta já possui uma decisão imutável")
        if proposal.estado_revisao not in {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFLITANTE}:
            raise RevisaoHumanaError("Proposta não está pendente de revisão")

    @staticmethod
    def _validate_catalog_item(catalog: CatalogoTecnico, data: DadosElementoRevisao) -> None:
        item = catalog.item_por_id(data.tipo_catalogo_id)
        if item is None or not item.ativo or item.categoria is not data.categoria:
            raise RevisaoHumanaError("Item de catálogo ativo não corresponde à categoria escolhida")

    @staticmethod
    def _confirmed_reference(work: UnitOfWorkPort, project: Projeto, reference_id: UUID) -> UUID:
        entity_ids = {
            *[item.id for item in project.elementos],
            *[item.id for item in project.pontos_rede],
            *[item.id for item in project.terminais],
        }
        if reference_id in entity_ids:
            return reference_id
        decision = work.decisoes_revisao.obter_da_proposta(reference_id)
        if decision is None or decision.elemento_confirmado_id is None:
            raise RevisaoHumanaError(
                "Confirme primeiro os elementos usados pelas extremidades da relação"
            )
        return decision.elemento_confirmado_id

    @staticmethod
    def _was_rejected_before(
        work: UnitOfWorkPort,
        project_id: UUID,
        proposal: PropostaElemento,
    ) -> bool:
        signature = _proposal_signature(proposal)
        for execution in work.execucoes_analise.listar_do_projeto(project_id):
            for previous in work.propostas.listar_da_execucao(execution.id):
                if (
                    isinstance(previous, PropostaElemento)
                    and previous.id != proposal.id
                    and previous.estado_revisao is EstadoRevisao.REJEITADA
                    and _proposal_signature(previous) == signature
                ):
                    return True
        return False

    def _aware_now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("Relógio da aplicação deve retornar data com fuso horário")
        return value


def _build_element(
    element_id: UUID,
    data: DadosElementoRevisao,
    catalog: CatalogoTecnico,
) -> tuple[ElementoProjetoType, tuple[PontoRede, ...]]:
    if data.categoria is CategoriaElemento.POSTE:
        return Poste(
            id=element_id,
            tipo_catalogo_id=data.tipo_catalogo_id,
            situacao=data.situacao,
            codigo_observado=data.codigo_observado,
            geometria=data.geometria,
        ), ()
    if data.categoria is CategoriaElemento.ESTRUTURA_MT:
        return EstruturaMt(
            id=element_id,
            tipo_catalogo_id=data.tipo_catalogo_id,
            situacao=data.situacao,
            codigo_observado=data.codigo_observado,
            geometria=data.geometria,
            poste_id=_required(data.poste_id, "poste"),
        ), ()
    if data.categoria is CategoriaElemento.ESTRUTURA_BT:
        return EstruturaBt(
            id=element_id,
            tipo_catalogo_id=data.tipo_catalogo_id,
            situacao=data.situacao,
            codigo_observado=data.codigo_observado,
            geometria=data.geometria,
            poste_id=_required(data.poste_id, "poste"),
        ), ()
    if data.categoria is CategoriaElemento.EQUIPAMENTO:
        return Equipamento(
            id=element_id,
            tipo_catalogo_id=data.tipo_catalogo_id,
            situacao=data.situacao,
            codigo_observado=data.codigo_observado,
            geometria=data.geometria,
            poste_id=_required(data.poste_id, "poste"),
        ), ()
    origin_id = data.ponto_origem_id
    destination_id = data.ponto_destino_id
    geometry = _cable_geometry(data.geometria)
    created_points: tuple[PontoRede, ...] = ()
    if (origin_id is None) != (destination_id is None):
        raise RevisaoHumanaError("Selecione os dois pontos do cabo ou deixe ambos em branco")
    if origin_id is None or destination_id is None:
        cable_type = catalog.item_por_id(data.tipo_catalogo_id)
        if not isinstance(cable_type, TipoCabo):
            raise RevisaoHumanaError("Tipo de catálogo do cabo não está disponível")
        level = _network_level(catalog, cable_type.nivel_tensao_opcao_id)
        origin_id = uuid5(element_id, "ponto-origem")
        destination_id = uuid5(element_id, "ponto-destino")
        created_points = (
            PontoRede(
                id=origin_id,
                poste_id=None,
                nome=f"{element_id}-origem",
                nivel_rede=level,
                nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
                configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
                tipo=TipoPontoRede.CONEXAO,
                geometria=GeometriaDocumento.ponto(geometry.pagina_id, geometry.pontos[0]),
            ),
            PontoRede(
                id=destination_id,
                poste_id=None,
                nome=f"{element_id}-destino",
                nivel_rede=level,
                nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
                configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
                tipo=TipoPontoRede.CONEXAO,
                geometria=GeometriaDocumento.ponto(geometry.pagina_id, geometry.pontos[-1]),
            ),
        )
    return Cabo(
        id=element_id,
        tipo_catalogo_id=data.tipo_catalogo_id,
        situacao=data.situacao,
        codigo_observado=data.codigo_observado,
        geometria=geometry,
        ponto_origem_id=origin_id,
        ponto_destino_id=destination_id,
    ), created_points


def _required(value: UUID | None, label: str) -> UUID:
    if value is None:
        raise RevisaoHumanaError(f"Selecione {label} para confirmar este elemento")
    return value


def _cable_geometry(geometry: GeometriaDocumento) -> GeometriaDocumento:
    if geometry.tipo is TipoGeometria.POLILINHA:
        return geometry
    if geometry.tipo is TipoGeometria.CAIXA:
        return GeometriaDocumento.polilinha(geometry.pagina_id, geometry.pontos)
    point = geometry.pontos[0]
    start_x = max(Decimal(0), point.x - Decimal("0.005"))
    end_x = min(Decimal(1), point.x + Decimal("0.005"))
    if start_x == end_x:
        end_x = min(Decimal(1), start_x + Decimal("0.001"))
    return GeometriaDocumento.polilinha(
        geometry.pagina_id,
        (
            PontoNormalizado(start_x, point.y),
            PontoNormalizado(end_x, point.y),
        ),
    )


def _network_level(catalog: CatalogoTecnico, voltage_option_id: UUID) -> NivelRede:
    option = next(
        (
            item
            for group in catalog.grupos_opcao
            if group.chave == "nivel_tensao"
            for item in group.opcoes
            if item.id == voltage_option_id
        ),
        None,
    )
    if option is None:
        raise RevisaoHumanaError("Nível de tensão do cabo não está disponível no catálogo")
    label = f"{option.codigo} {option.rotulo}".upper()
    return NivelRede.MT if "MT" in label else NivelRede.BT


def _proposal_signature(proposal: PropostaElemento) -> tuple[object, ...]:
    return (
        proposal.categoria,
        proposal.tipo_catalogo_sugerido_id,
        proposal.codigo_observado,
        proposal.situacao_projeto,
        proposal.geometria,
    )


def _source_evidence_execution_id(execution: ExecucaoAnalise) -> UUID:
    raw_value = dict(execution.parametros).get("execucao_extracao_id")
    if raw_value is None:
        return execution.id
    try:
        return UUID(str(raw_value))
    except ValueError:
        return execution.id
