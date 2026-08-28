from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from tests.factories import complete_project

from zeny_project_handler.application.mvp_workflow import _project_without_documents
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoConexao,
    NivelRede,
    SituacaoProjeto,
    TipoAcaoRevisaoManual,
    TipoPontoRede,
    TipoVinculoObra,
)
from zeny_project_handler.domain.errors import DomainValidationError
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
    RegistroRevisaoManual,
    RelacaoConfirmada,
    TerminalEquipamento,
    validar_projeto_com_catalogo,
)
from zeny_project_handler.domain.project_metadata import (
    MetadadosProjeto,
    normalizar_codigo_servico,
)
from zeny_project_handler.domain.values import (
    CaixaPagina,
    CoordenadaCampo,
    GeometriaDocumento,
    PontoNormalizado,
)


def test_project_without_documents_preserves_order_and_prunes_transitive_references(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = complete_project(catalogo_inicial)
    existing_pole, retained_removed_pole, retained_installed_pole = project.elementos[:3]
    removed_relation = RelacaoConfirmada(
        id=uuid4(),
        tipo_relacao="REFERENCIA",
        origem_id=existing_pole.id,
        destino_id=retained_removed_pole.id,
    )
    retained_relation = RelacaoConfirmada(
        id=uuid4(),
        tipo_relacao="REFERENCIA",
        origem_id=retained_removed_pole.id,
        destino_id=retained_installed_pole.id,
    )
    removed_history = RegistroRevisaoManual(
        id=uuid4(),
        acao=TipoAcaoRevisaoManual.CRIAR_RELACAO,
        referencia_criada_id=removed_relation.id,
        revisor="fixture",
        realizada_em=datetime(2026, 8, 6, 10, tzinfo=UTC),
    )
    retained_history = RegistroRevisaoManual(
        id=uuid4(),
        acao=TipoAcaoRevisaoManual.CRIAR_RELACAO,
        referencia_criada_id=retained_relation.id,
        revisor="fixture",
        realizada_em=datetime(2026, 8, 6, 10, tzinfo=UTC),
    )
    project = replace(
        project,
        relacoes_confirmadas=(removed_relation, retained_relation),
        historico_revisao_manual=(removed_history, retained_history),
    )
    document = project.documentos[0]
    page_id = document.paginas[0].id

    result = _project_without_documents(project, {document.id}, {page_id})

    assert project.documentos == (document,)
    assert result.documentos == ()
    assert result.ordem_leitura_paginas == ()
    assert [item.id for item in result.elementos] == [
        retained_removed_pole.id,
        retained_installed_pole.id,
    ]
    assert [item.id for item in result.pontos_rede] == [project.pontos_rede[1].id]
    assert result.terminais == ()
    assert result.conexoes_internas == ()
    assert result.vinculos_obra == project.vinculos_obra
    assert result.relacoes_confirmadas == (retained_relation,)
    assert result.historico_revisao_manual == (retained_history,)


def option_id(catalog: CatalogoTecnico, group_key: str, label: str) -> UUID:
    group = next(group for group in catalog.grupos_opcao if group.chave == group_key)
    return next(option.id for option in group.opcoes if option.rotulo == label)


def item_id(catalog: CatalogoTecnico, category: CategoriaElemento) -> UUID:
    return catalog.itens_ativos(category)[0].id


def document() -> DocumentoProjeto:
    box = CaixaPagina(Decimal("0"), Decimal("0"), Decimal("1000"), Decimal("700"))
    page = PaginaDocumento(
        id=uuid4(),
        numero=1,
        largura_pontos=Decimal("1000"),
        altura_pontos=Decimal("700"),
        rotacao_graus=0,
        media_box=box,
        crop_box=box,
    )
    return DocumentoProjeto(id=uuid4(), nome_arquivo="rede.pdf", sha256="b" * 64, paginas=(page,))


def valid_project(catalog: CatalogoTecnico) -> Projeto:
    project_document = document()
    first_pole = Poste(
        id=uuid4(),
        tipo_catalogo_id=item_id(catalog, CategoriaElemento.POSTE),
        situacao=SituacaoProjeto.EXISTENTE,
        geometria=GeometriaDocumento.ponto(
            project_document.paginas[0].id,
            PontoNormalizado(Decimal("0.2"), Decimal("0.4")),
        ),
    )
    second_pole = Poste(
        id=uuid4(),
        tipo_catalogo_id=item_id(catalog, CategoriaElemento.POSTE),
        situacao=SituacaoProjeto.INSTALAR,
    )
    phase_option = option_id(catalog, "configuracao_fases", "MONOFÁSICA")
    voltage_option = option_id(catalog, "nivel_tensao", "MT")
    first_point = PontoRede(
        id=uuid4(),
        poste_id=first_pole.id,
        nome="P1-MT",
        nivel_rede=NivelRede.MT,
        nivel_tensao_opcao_id=voltage_option,
        configuracao_fases_opcao_id=phase_option,
    )
    second_point = PontoRede(
        id=uuid4(),
        poste_id=second_pole.id,
        nome="P2-MT",
        nivel_rede=NivelRede.MT,
        nivel_tensao_opcao_id=voltage_option,
        configuracao_fases_opcao_id=phase_option,
    )
    structure = EstruturaMt(
        id=uuid4(),
        tipo_catalogo_id=item_id(catalog, CategoriaElemento.ESTRUTURA_MT),
        situacao=SituacaoProjeto.EXISTENTE,
        poste_id=first_pole.id,
        pontos_fixados_ids=(first_point.id,),
    )
    cable = Cabo(
        id=uuid4(),
        tipo_catalogo_id=item_id(catalog, CategoriaElemento.CABO),
        situacao=SituacaoProjeto.INSTALAR,
        ponto_origem_id=first_point.id,
        ponto_destino_id=second_point.id,
        comprimento_m=Decimal("25.5"),
        geometria=GeometriaDocumento.polilinha(
            project_document.paginas[0].id,
            (
                PontoNormalizado(Decimal("0.2"), Decimal("0.4")),
                PontoNormalizado(Decimal("0.8"), Decimal("0.4")),
            ),
        ),
    )
    return Projeto(
        id=uuid4(),
        nome="Expansão bairro A",
        catalogo_versao_id=catalog.id,
        criado_em=datetime(2026, 7, 21, tzinfo=UTC),
        documentos=(project_document,),
        elementos=(first_pole, second_pole, structure, cable),
        pontos_rede=(first_point, second_point),
    )


@pytest.mark.parametrize("value", ("0001", "9999"))
def test_service_code_preserves_exactly_four_ascii_digits(value: str) -> None:
    assert normalizar_codigo_servico(value) == value


@pytest.mark.parametrize(
    "value",
    ("1", "001", "10000", "00 1", "+001", "A001", "\uff11\uff12\uff13\uff14", True),
)
def test_service_code_rejects_invalid_values(value: object) -> None:
    with pytest.raises(DomainValidationError, match="4 dígitos ASCII"):
        normalizar_codigo_servico(cast(str, value))


def test_project_service_codes_are_unique_sorted_and_optional(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)

    assert project.codigos_servico == ()
    assert replace(project, codigos_servico=("9999", "0001")).codigos_servico == (
        "0001",
        "9999",
    )
    with pytest.raises(DomainValidationError, match="devem ser únicos"):
        replace(project, codigos_servico=("0001", "0001"))


def test_project_reading_order_contains_every_page_once(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    page_id = project.documentos[0].paginas[0].id

    assert project.ordem_leitura_paginas == (page_id,)
    with pytest.raises(DomainValidationError, match="Ordem de leitura"):
        replace(project, ordem_leitura_paginas=(page_id, page_id))
    with pytest.raises(DomainValidationError, match="Ordem de leitura"):
        replace(project, ordem_leitura_paginas=(uuid4(),))


def test_valid_project_links_poles_structures_points_and_cables(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)

    validar_projeto_com_catalogo(project, catalogo_inicial)

    cable = next(element for element in project.elementos if isinstance(element, Cabo))
    assert cable.comprimento_m == Decimal("25.5")
    assert cable.geometria is not None
    assert len(cable.geometria.pontos) == 2


def test_project_rejects_cable_endpoint_outside_project(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    elements = tuple(
        replace(element, ponto_destino_id=uuid4()) if isinstance(element, Cabo) else element
        for element in project.elementos
    )

    with pytest.raises(DomainValidationError, match="Extremidades"):
        replace(project, elementos=elements)


def test_bt_structure_cannot_fix_mt_point(catalogo_inicial: CatalogoTecnico) -> None:
    project = valid_project(catalogo_inicial)
    pole = next(element for element in project.elementos if isinstance(element, Poste))
    mt_point = project.pontos_rede[0]
    invalid_structure = EstruturaBt(
        id=uuid4(),
        tipo_catalogo_id=item_id(catalogo_inicial, CategoriaElemento.ESTRUTURA_BT),
        situacao=SituacaoProjeto.EXISTENTE,
        poste_id=pole.id,
        pontos_fixados_ids=(mt_point.id,),
    )

    with pytest.raises(DomainValidationError, match="mesmo poste e nível"):
        replace(project, elementos=(*project.elementos, invalid_structure))


def test_project_catalog_validation_rejects_wrong_item_category(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    pole = next(element for element in project.elementos if isinstance(element, Poste))
    invalid_pole = replace(pole, tipo_catalogo_id=item_id(catalogo_inicial, CategoriaElemento.CABO))
    elements = tuple(
        invalid_pole if element.id == pole.id else element for element in project.elementos
    )
    invalid_project = replace(project, elementos=elements)

    with pytest.raises(DomainValidationError, match="categoria correta"):
        validar_projeto_com_catalogo(invalid_project, catalogo_inicial)


def test_photo_paths_are_relative_and_normalized() -> None:
    photo = FotoElemento(
        id=uuid4(),
        caminho_relativo="fotos\\poste-01.jpg",
        legenda=" Poste ",
        sha256="a" * 64,
        tipo_mime="image/jpeg",
        tamanho_bytes=42,
    )

    assert photo.caminho_relativo == "fotos/poste-01.jpg"
    assert photo.legenda == "Poste"
    assert photo.sha256 == "a" * 64
    with pytest.raises(DomainValidationError, match="caminhos relativos"):
        FotoElemento(id=uuid4(), caminho_relativo="C:/fotos/poste.jpg")
    with pytest.raises(DomainValidationError, match="caminhos relativos"):
        FotoElemento(id=uuid4(), caminho_relativo="../poste.jpg")
    with pytest.raises(DomainValidationError, match="em conjunto"):
        FotoElemento(id=uuid4(), caminho_relativo="fotos/poste.jpg", sha256="a" * 64)
    with pytest.raises(DomainValidationError, match="não é aceito"):
        FotoElemento(
            id=uuid4(),
            caminho_relativo="fotos/poste.exe",
            sha256="a" * 64,
            tipo_mime="application/octet-stream",
            tamanho_bytes=42,
        )


def test_cable_requires_distinct_points_and_polyline(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    point_id = uuid4()
    cable_type_id = item_id(catalogo_inicial, CategoriaElemento.CABO)
    with pytest.raises(DomainValidationError, match="pontos distintos"):
        Cabo(
            id=uuid4(),
            tipo_catalogo_id=cable_type_id,
            situacao=SituacaoProjeto.EXISTENTE,
            ponto_origem_id=point_id,
            ponto_destino_id=point_id,
        )

    with pytest.raises(DomainValidationError, match="polilinha"):
        Cabo(
            id=uuid4(),
            tipo_catalogo_id=cable_type_id,
            situacao=SituacaoProjeto.EXISTENTE,
            ponto_origem_id=point_id,
            ponto_destino_id=uuid4(),
            geometria=GeometriaDocumento.ponto(
                uuid4(), PontoNormalizado(Decimal("0.5"), Decimal("0.5"))
            ),
        )


def test_equipment_terminals_and_internal_connection_are_explicit(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    pole = next(element for element in project.elementos if isinstance(element, Poste))
    point = project.pontos_rede[0]
    equipment = Equipamento(
        id=uuid4(),
        tipo_catalogo_id=item_id(catalogo_inicial, CategoriaElemento.EQUIPAMENTO),
        situacao=SituacaoProjeto.EXISTENTE,
        poste_id=pole.id,
    )
    first_terminal = TerminalEquipamento(
        id=uuid4(),
        equipamento_id=equipment.id,
        nome="entrada",
        nivel_rede=point.nivel_rede,
        nivel_tensao_opcao_id=point.nivel_tensao_opcao_id,
        configuracao_fases_opcao_id=point.configuracao_fases_opcao_id,
        ponto_rede_id=point.id,
    )
    second_terminal = replace(first_terminal, id=uuid4(), nome="saída")
    connection = ConexaoInternaEquipamento(
        id=uuid4(),
        equipamento_id=equipment.id,
        terminal_origem_id=first_terminal.id,
        terminal_destino_id=second_terminal.id,
        estado=EstadoConexao.CONECTADA,
    )
    complete_project = replace(
        project,
        elementos=(*project.elementos, equipment),
        terminais=(first_terminal, second_terminal),
        conexoes_internas=(connection,),
    )

    validar_projeto_com_catalogo(complete_project, catalogo_inicial)
    assert complete_project.conexoes_internas[0].estado is EstadoConexao.CONECTADA


def test_equipment_relationships_reject_invalid_references(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    point = project.pontos_rede[0]
    orphan_terminal = TerminalEquipamento(
        id=uuid4(),
        equipamento_id=uuid4(),
        nome="órfão",
        nivel_rede=point.nivel_rede,
        nivel_tensao_opcao_id=point.nivel_tensao_opcao_id,
        configuracao_fases_opcao_id=point.configuracao_fases_opcao_id,
    )

    with pytest.raises(DomainValidationError, match="pertencer a um equipamento"):
        replace(project, terminais=(orphan_terminal,))
    with pytest.raises(DomainValidationError, match="terminais distintos"):
        ConexaoInternaEquipamento(
            id=uuid4(),
            equipamento_id=uuid4(),
            terminal_origem_id=orphan_terminal.id,
            terminal_destino_id=orphan_terminal.id,
            estado=EstadoConexao.DESCONHECIDA,
        )


def test_project_rejects_geometry_and_points_outside_its_aggregate(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    pole = next(element for element in project.elementos if isinstance(element, Poste))
    invalid_geometry_pole = replace(
        pole,
        geometria=GeometriaDocumento.ponto(
            uuid4(), PontoNormalizado(Decimal("0.1"), Decimal("0.1"))
        ),
    )
    invalid_elements = tuple(
        invalid_geometry_pole if element.id == pole.id else element for element in project.elementos
    )

    with pytest.raises(DomainValidationError, match="página do projeto"):
        replace(project, elementos=invalid_elements)
    with pytest.raises(DomainValidationError, match="Poste associado"):
        replace(project, pontos_rede=(replace(project.pontos_rede[0], poste_id=uuid4()),))


def test_network_point_can_represent_delivery_without_a_pole(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    existing_point = project.pontos_rede[0]
    delivery_point = replace(
        existing_point,
        id=uuid4(),
        poste_id=None,
        nome="Ponto de entrega",
        tipo=TipoPontoRede.ENTREGA,
        coordenada_campo=CoordenadaCampo(
            leste=Decimal("397749"),
            norte=Decimal("7725666"),
            zona="23K",
        ),
    )
    branch = Cabo(
        id=uuid4(),
        tipo_catalogo_id=item_id(catalogo_inicial, CategoriaElemento.CABO),
        situacao=SituacaoProjeto.INSTALAR,
        ponto_origem_id=existing_point.id,
        ponto_destino_id=delivery_point.id,
    )
    complete = replace(
        project,
        elementos=(*project.elementos, branch),
        pontos_rede=(*project.pontos_rede, delivery_point),
    )

    validar_projeto_com_catalogo(complete, catalogo_inicial)
    assert delivery_point.poste_id is None
    with pytest.raises(DomainValidationError, match="Ponto de poste"):
        replace(delivery_point, tipo=TipoPontoRede.POSTE)


def test_cable_preserves_ordered_intermediate_network_points(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    cable = next(element for element in project.elementos if isinstance(element, Cabo))
    intermediate = replace(
        project.pontos_rede[0],
        id=uuid4(),
        nome="Derivação intermediária",
        tipo=TipoPontoRede.DERIVACAO,
    )
    updated_cable = replace(cable, pontos_intermediarios_ids=(intermediate.id,))
    elements = tuple(
        updated_cable if element.id == cable.id else element for element in project.elementos
    )
    complete = replace(
        project,
        elementos=elements,
        pontos_rede=(*project.pontos_rede, intermediate),
    )

    assert updated_cable.percurso_pontos_ids == (
        cable.ponto_origem_id,
        intermediate.id,
        cable.ponto_destino_id,
    )
    validar_projeto_com_catalogo(complete, catalogo_inicial)
    with pytest.raises(DomainValidationError, match="pontos intermediários"):
        replace(updated_cable, pontos_intermediarios_ids=(intermediate.id, intermediate.id))


def test_relocation_links_removal_to_installation_of_same_type(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    base_pole = next(element for element in project.elementos if isinstance(element, Poste))
    removed = replace(base_pole, id=uuid4(), situacao=SituacaoProjeto.REMOVER)
    installed = replace(base_pole, id=uuid4(), situacao=SituacaoProjeto.INSTALAR)
    link = VinculoObra(
        id=uuid4(),
        tipo=TipoVinculoObra.REALOCACAO,
        elemento_origem_id=removed.id,
        elemento_destino_id=installed.id,
        observacao=" Mover poste ",
    )
    complete = replace(
        project,
        elementos=(*project.elementos, removed, installed),
        vinculos_obra=(link,),
    )

    assert complete.vinculos_obra[0].observacao == "Mover poste"
    with pytest.raises(DomainValidationError, match=r"Origem.*retirada"):
        replace(
            complete,
            vinculos_obra=(replace(link, elemento_origem_id=base_pole.id),),
        )


def test_project_metadata_follows_cemig_project_identification() -> None:
    metadata = MetadadosProjeto(
        nota_servico="1252773647",
        circuito=" PIUD-209 ",
        municipio=" Capitólio ",
        tipo_servico="Ligação nova",
        escala="1:1000",
        formato_folha="A3",
        numero_folha="1/1",
        data_projeto=date(2026, 6, 23),
        impacto_ambiental=True,
    )

    assert metadata.circuito == "PIUD-209"
    assert metadata.municipio == "Capitólio"
    with pytest.raises(DomainValidationError, match="10 dígitos"):
        replace(metadata, nota_servico="123")
    with pytest.raises(DomainValidationError, match="formato 1:n"):
        replace(metadata, escala="1000")


def test_catalog_validation_rejects_wrong_version_and_option_group(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    project = valid_project(catalogo_inicial)
    with pytest.raises(DomainValidationError, match="versão de catálogo"):
        validar_projeto_com_catalogo(replace(project, catalogo_versao_id=uuid4()), catalogo_inicial)

    phase_option_id = option_id(catalogo_inicial, "configuracao_fases", "MONOFÁSICA")
    invalid_point = replace(project.pontos_rede[0], nivel_tensao_opcao_id=phase_option_id)
    invalid_project = replace(project, pontos_rede=(invalid_point, *project.pontos_rede[1:]))
    with pytest.raises(DomainValidationError, match="nível de tensão"):
        validar_projeto_com_catalogo(invalid_project, catalogo_inicial)
