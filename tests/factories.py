"""Fábricas determinísticas de agregados completos para testes de persistência."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from zeny_project_handler.domain.analysis import (
    ArtefatoExtraido,
    DecisaoRevisao,
    EvidenciaDocumento,
    ExecucaoAnalise,
    OrigemObjetoPdf,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoConexao,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    NivelRede,
    SituacaoProjeto,
    TipoDecisaoRevisao,
    TipoEvidencia,
    TipoOrigemPdf,
    TipoVinculoObra,
)
from zeny_project_handler.domain.operations import VinculoObra
from zeny_project_handler.domain.project import (
    Cabo,
    ConexaoInternaEquipamento,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    FotoElemento,
    PontoRede,
    Poste,
    Projeto,
    TerminalEquipamento,
)
from zeny_project_handler.domain.project_metadata import ContatoSolicitante, MetadadosProjeto
from zeny_project_handler.domain.values import (
    CaixaPagina,
    CoordenadaCampo,
    GeometriaDocumento,
    PontoNormalizado,
)


def _item_id(catalog: CatalogoTecnico, category: CategoriaElemento) -> UUID:
    return catalog.itens_ativos(category)[0].id


def _option_id(catalog: CatalogoTecnico, group_key: str, label: str) -> UUID:
    group = next(group for group in catalog.grupos_opcao if group.chave == group_key)
    return next(option.id for option in group.opcoes if option.rotulo == label)


def complete_project(catalog: CatalogoTecnico) -> Projeto:
    box = CaixaPagina(Decimal(0), Decimal(0), Decimal(1000), Decimal(700))
    page = PaginaDocumento(
        id=uuid4(),
        numero=1,
        largura_pontos=Decimal(1000),
        altura_pontos=Decimal(700),
        rotacao_graus=0,
        media_box=box,
        crop_box=box,
    )
    document = DocumentoProjeto(
        id=uuid4(),
        nome_arquivo="projeto-completo.pdf",
        sha256="c" * 64,
        paginas=(page,),
        tamanho_bytes=123456,
        versao_pdf="1.7",
        produtor="AutoCAD",
    )
    coordinate = CoordenadaCampo(
        leste=Decimal("397617.2"),
        norte=Decimal("7725802.1"),
        sistema_referencia="SIRGAS 2000",
        zona="23K",
    )
    pole_type = _item_id(catalog, CategoriaElemento.POSTE)
    existing_pole = Poste(
        id=uuid4(),
        tipo_catalogo_id=pole_type,
        situacao=SituacaoProjeto.EXISTENTE,
        referencia_desenho="P1",
        geometria=GeometriaDocumento.ponto(
            page.id, PontoNormalizado(Decimal("0.2"), Decimal("0.4"))
        ),
        coordenada_campo=coordinate,
        fotos=(FotoElemento(id=uuid4(), caminho_relativo="fotos/p1.jpg", legenda="Poste 1"),),
    )
    removed_pole = Poste(id=uuid4(), tipo_catalogo_id=pole_type, situacao=SituacaoProjeto.REMOVER)
    installed_pole = Poste(
        id=uuid4(), tipo_catalogo_id=pole_type, situacao=SituacaoProjeto.INSTALAR
    )
    mono_phase = _option_id(catalog, "configuracao_fases", "MONOFÁSICA")
    mt_voltage = _option_id(catalog, "nivel_tensao", "MT")
    bt_voltage = _option_id(catalog, "nivel_tensao", "BT")
    mt_point = PontoRede(
        id=uuid4(),
        poste_id=existing_pole.id,
        nome="P1-MT",
        nivel_rede=NivelRede.MT,
        nivel_tensao_opcao_id=mt_voltage,
        configuracao_fases_opcao_id=mono_phase,
    )
    destination_point = PontoRede(
        id=uuid4(),
        poste_id=installed_pole.id,
        nome="P2-MT",
        nivel_rede=NivelRede.MT,
        nivel_tensao_opcao_id=mt_voltage,
        configuracao_fases_opcao_id=mono_phase,
    )
    bt_point = PontoRede(
        id=uuid4(),
        poste_id=existing_pole.id,
        nome="P1-BT",
        nivel_rede=NivelRede.BT,
        nivel_tensao_opcao_id=bt_voltage,
        configuracao_fases_opcao_id=mono_phase,
    )
    structure_mt = EstruturaMt(
        id=uuid4(),
        tipo_catalogo_id=_item_id(catalog, CategoriaElemento.ESTRUTURA_MT),
        situacao=SituacaoProjeto.EXISTENTE,
        poste_id=existing_pole.id,
        pontos_fixados_ids=(mt_point.id,),
    )
    structure_bt = EstruturaBt(
        id=uuid4(),
        tipo_catalogo_id=_item_id(catalog, CategoriaElemento.ESTRUTURA_BT),
        situacao=SituacaoProjeto.EXISTENTE,
        poste_id=existing_pole.id,
        pontos_fixados_ids=(bt_point.id,),
    )
    cable = Cabo(
        id=uuid4(),
        tipo_catalogo_id=_item_id(catalog, CategoriaElemento.CABO),
        situacao=SituacaoProjeto.INSTALAR,
        ponto_origem_id=mt_point.id,
        ponto_destino_id=destination_point.id,
        comprimento_m=Decimal("31.5"),
        geometria=GeometriaDocumento.polilinha(
            page.id,
            (
                PontoNormalizado(Decimal("0.2"), Decimal("0.4")),
                PontoNormalizado(Decimal("0.8"), Decimal("0.4")),
            ),
        ),
    )
    equipment = Equipamento(
        id=uuid4(),
        tipo_catalogo_id=_item_id(catalog, CategoriaElemento.EQUIPAMENTO),
        situacao=SituacaoProjeto.EXISTENTE,
        poste_id=existing_pole.id,
        identificador_operacional="TR-01",
    )
    mt_terminal = TerminalEquipamento(
        id=uuid4(),
        equipamento_id=equipment.id,
        nome="MT",
        nivel_rede=NivelRede.MT,
        nivel_tensao_opcao_id=mt_voltage,
        configuracao_fases_opcao_id=mono_phase,
        ponto_rede_id=mt_point.id,
    )
    bt_terminal = TerminalEquipamento(
        id=uuid4(),
        equipamento_id=equipment.id,
        nome="BT",
        nivel_rede=NivelRede.BT,
        nivel_tensao_opcao_id=bt_voltage,
        configuracao_fases_opcao_id=mono_phase,
        ponto_rede_id=bt_point.id,
    )
    internal_connection = ConexaoInternaEquipamento(
        id=uuid4(),
        equipamento_id=equipment.id,
        terminal_origem_id=mt_terminal.id,
        terminal_destino_id=bt_terminal.id,
        estado=EstadoConexao.CONECTADA,
    )
    relocation = VinculoObra(
        id=uuid4(),
        tipo=TipoVinculoObra.REALOCACAO,
        elemento_origem_id=removed_pole.id,
        elemento_destino_id=installed_pole.id,
    )
    return Projeto(
        id=uuid4(),
        nome="Projeto completo",
        catalogo_versao_id=catalog.id,
        criado_em=datetime(2026, 7, 21, 10, tzinfo=UTC),
        documentos=(document,),
        elementos=(
            existing_pole,
            removed_pole,
            installed_pole,
            structure_mt,
            structure_bt,
            cable,
            equipment,
        ),
        pontos_rede=(mt_point, destination_point, bt_point),
        terminais=(mt_terminal, bt_terminal),
        conexoes_internas=(internal_connection,),
        vinculos_obra=(relocation,),
        metadados=MetadadosProjeto(
            nota_servico="1234567890",
            municipio="Belo Horizonte",
            escala="1:1000",
            data_projeto=date(2026, 7, 21),
            atributos_extras=(("projetista", "equipe interna"),),
        ),
        contato_solicitante=ContatoSolicitante(nome="Solicitante", telefone="3100000000"),
    )


def complete_analysis(
    project: Projeto,
) -> tuple[
    ExecucaoAnalise,
    EvidenciaDocumento,
    PropostaElemento,
    PropostaRelacao,
    DecisaoRevisao,
]:
    started = datetime(2026, 7, 21, 11, tzinfo=UTC)
    execution = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=project.id,
        metodo="vetores-pdf",
        versao_metodo="1.0",
        parametros=(("dpi", 300),),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=started,
        finalizada_em=datetime(2026, 7, 21, 11, 1, tzinfo=UTC),
    )
    page_id = project.documentos[0].paginas[0].id
    geometry = GeometriaDocumento.ponto(page_id, PontoNormalizado(Decimal("0.2"), Decimal("0.4")))
    evidence = EvidenciaDocumento(
        id=uuid4(),
        execucao_id=execution.id,
        pagina_id=page_id,
        tipo=TipoEvidencia.VETOR,
        geometria=geometry,
        metodo="vetores-pdf",
        versao_metodo="1.0",
        parametros=(),
        conteudo_bruto="P1",
        criada_em=started,
        origem_pdf=OrigemObjetoPdf(
            tipo=TipoOrigemPdf.APARENCIA_ANOTACAO,
            numero_objeto=42,
            indice_anotacao=0,
            subtipo_anotacao="Stamp",
        ),
        artefato=ArtefatoExtraido(
            caminho_relativo="artefatos/recorte.png",
            sha256="d" * 64,
            mime_type="image/png",
            tamanho_bytes=512,
        ),
        atributos_extraidos=(("cor", "#008000"),),
    )
    element_proposal = PropostaElemento(
        id=uuid4(),
        execucao_id=execution.id,
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=SituacaoProjeto.EXISTENTE,
        estado_revisao=EstadoRevisao.CONFIRMADA,
        evidencia_ids=(evidence.id,),
        geometria=geometry,
        tipo_catalogo_sugerido_id=project.elementos[0].tipo_catalogo_id,
        confianca=Decimal("0.95"),
    )
    relation_proposal = PropostaRelacao(
        id=uuid4(),
        execucao_id=execution.id,
        origem_referencia_id=project.pontos_rede[0].id,
        destino_referencia_id=project.pontos_rede[1].id,
        tipo_relacao="CABO_ENTRE_PONTOS",
        evidencia_ids=(evidence.id,),
        confianca=Decimal("0.80"),
    )
    decision = DecisaoRevisao(
        id=uuid4(),
        proposta_id=element_proposal.id,
        decisao=TipoDecisaoRevisao.ACEITAR,
        revisor="revisor local",
        decidida_em=datetime(2026, 7, 21, 11, 2, tzinfo=UTC),
        elemento_confirmado_id=project.elementos[0].id,
    )
    return execution, evidence, element_proposal, relation_proposal, decision
