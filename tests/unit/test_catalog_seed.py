from collections import Counter
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from zeny_project_handler.adapters.catalog.json_catalog import (
    carregar_catalogo_json,
    catalogo_de_dict,
    catalogo_para_dict,
)
from zeny_project_handler.domain.catalog import (
    AssinaturaSimbologia,
    CatalogoTecnico,
    TipoCabo,
    TipoEstruturaMt,
)
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    SituacaoProjeto,
    StatusCatalogo,
)
from zeny_project_handler.domain.errors import DomainValidationError


def test_seed_preserves_source_counts_and_original_codes(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    counts = catalogo_inicial.fonte.contagens
    assert (counts.postes, counts.estruturas_mt, counts.estruturas_bt) == (38, 50, 13)
    assert (counts.cabos, counts.equipamentos) == (72, 25)
    assert catalogo_inicial.fonte.sha256 == (
        "4ba9bd5cb284f6d18c3ee000a6064061d0d814bd23ec29d8630c2b15e58f8867"
    )

    item_counts = Counter(item.categoria for item in catalogo_inicial.itens)
    assert item_counts == {
        CategoriaElemento.POSTE: 38,
        CategoriaElemento.ESTRUTURA_MT: 50,
        CategoriaElemento.ESTRUTURA_BT: 13,
        CategoriaElemento.CABO: 72,
        CategoriaElemento.EQUIPAMENTO: 25,
    }


def test_duplicate_cem4_is_auditable_and_only_one_definition_is_active(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cem4_items = [
        item
        for item in catalogo_inicial.itens
        if isinstance(item, TipoEstruturaMt) and item.codigo == "CEM4"
    ]

    assert [item.linha_origem for item in cem4_items] == [40, 46]
    assert [item.ativo for item in cem4_items] == [True, False]
    assert len(catalogo_inicial.avisos_importacao) == 1
    warning = catalogo_inicial.avisos_importacao[0]
    assert warning.codigo == "DUPLICATE_ITEM_CODE"
    assert warning.valor == "CEM4"
    assert warning.linhas_origem == (40, 46)


def test_dash_condemnation_factor_becomes_null_without_changing_codes(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cables = {item.codigo: item for item in catalogo_inicial.itens if isinstance(item, TipoCabo)}

    assert cables["A-4 CA"].fator_condenacao is not None
    assert str(cables["A-4 CA"].fator_condenacao) == "1.7"
    assert cables["(N- 1N5)"].fator_condenacao is None
    assert cables['AM-50(3/8")'].fator_condenacao is None


def test_seed_contains_explicit_valid_compatibilities(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    active_structures = {
        item.id
        for item in catalogo_inicial.itens
        if item.ativo
        and item.categoria in {CategoriaElemento.ESTRUTURA_MT, CategoriaElemento.ESTRUTURA_BT}
    }
    structures_with_cables = {
        compatibility.tipo_estrutura_id for compatibility in catalogo_inicial.compatibilidades
    }

    assert len(catalogo_inicial.compatibilidades) == 314
    assert structures_with_cables == active_structures


def test_seed_has_configurable_options_and_all_symbol_combinations(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    groups = {group.chave: group for group in catalogo_inicial.grupos_opcao}

    assert set(groups) == {
        "formato_poste",
        "configuracao_fases",
        "tecnologia_rede",
        "nivel_tensao",
        "classe_equipamento",
    }
    assert {option.rotulo for option in groups["formato_poste"].opcoes} == {
        "CIRCULAR",
        "DUPLO T",
        "MADEIRA",
    }
    assert len(catalogo_inicial.regras_simbologia) == 15
    assert catalogo_inicial.versao_schema == 2
    assert len(catalogo_inicial.assinaturas_simbologia) == 5
    assert {
        signature.situacao_projeto for signature in catalogo_inicial.assinaturas_simbologia
    } == set(SituacaoProjeto)
    assert all(
        signature.categoria_elemento is None
        for signature in catalogo_inicial.assinaturas_simbologia
    )

    canonical_colors = {
        rule.situacao_projeto: rule.cor for rule in catalogo_inicial.regras_simbologia
    }
    assert canonical_colors == {
        SituacaoProjeto.EXISTENTE: "#000000",
        SituacaoProjeto.INSTALAR: "#008000",
        SituacaoProjeto.REMOVER: "#FF0000",
    }


def test_catalog_json_round_trip_preserves_domain(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    restored = catalogo_de_dict(catalogo_para_dict(catalogo_inicial))

    assert restored == catalogo_inicial


def test_catalog_rejects_unsupported_schema(catalogo_inicial: CatalogoTecnico) -> None:
    payload = catalogo_para_dict(catalogo_inicial)
    payload["schema_version"] = 999

    with pytest.raises(DomainValidationError, match="não suportado"):
        catalogo_de_dict(payload)


def test_catalog_loader_remains_compatible_with_schema_v1(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    payload = catalogo_para_dict(catalogo_inicial)
    payload["schema_version"] = 1
    payload.pop("recognition_signatures")

    restored = catalogo_de_dict(payload)

    assert restored.versao_schema == 1
    assert restored.assinaturas_simbologia == ()


def test_catalog_loader_reports_invalid_json(tmp_path: Path) -> None:
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{", encoding="utf-8")

    with pytest.raises(DomainValidationError, match="Não foi possível carregar"):
        carregar_catalogo_json(invalid_file)


def test_published_catalog_is_immutable_and_can_create_a_new_draft(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    with pytest.raises(DomainValidationError, match="imutáveis"):
        catalogo_inicial.com_itens(catalogo_inicial.itens)

    draft = catalogo_inicial.criar_rascunho(novo_id=uuid4(), criado_em=catalogo_inicial.criado_em)

    assert draft.status is StatusCatalogo.RASCUNHO
    assert draft.versao == catalogo_inicial.versao + 1
    assert draft.publicado_em is None
    assert draft.com_itens(draft.itens) == draft
    assert draft.com_simbologia(draft.regras_simbologia, draft.assinaturas_simbologia) == draft
    assert catalogo_inicial.status is StatusCatalogo.PUBLICADO
    assert catalogo_inicial.item_por_id(catalogo_inicial.itens[0].id) == catalogo_inicial.itens[0]
    assert catalogo_inicial.item_por_id(uuid4()) is None
    with pytest.raises(DomainValidationError, match="Somente um catálogo publicado"):
        draft.criar_rascunho(novo_id=uuid4(), criado_em=draft.criado_em)
    with pytest.raises(DomainValidationError, match="imutáveis"):
        catalogo_inicial.com_simbologia(
            catalogo_inicial.regras_simbologia,
            catalogo_inicial.assinaturas_simbologia,
        )


def test_catalog_rejects_two_active_cem4_definitions(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    duplicate = next(
        item
        for item in catalogo_inicial.itens
        if isinstance(item, TipoEstruturaMt) and item.codigo == "CEM4" and not item.ativo
    )
    invalid_items = tuple(
        replace(item, ativo=True) if item.id == duplicate.id else item
        for item in catalogo_inicial.itens
    )

    with pytest.raises(DomainValidationError, match="Códigos ativos"):
        replace(catalogo_inicial, itens=invalid_items)


def test_catalog_rejects_duplicate_or_incomplete_visual_signatures(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    signature = catalogo_inicial.assinaturas_simbologia[0]
    duplicate = replace(signature, id=uuid4())
    with pytest.raises(DomainValidationError, match="não podem ser duplicadas"):
        replace(
            catalogo_inicial,
            assinaturas_simbologia=(*catalogo_inicial.assinaturas_simbologia, duplicate),
        )

    existing_only = AssinaturaSimbologia(
        id=uuid4(),
        situacao_projeto=SituacaoProjeto.EXISTENTE,
        cor="#000000",
        tolerancia_cor=10,
        prioridade=1,
        origem="teste",
    )
    with pytest.raises(DomainValidationError, match="cobrir todas"):
        replace(catalogo_inicial, assinaturas_simbologia=(existing_only,))
