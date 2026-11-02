"""Ataques adversariais à ficha predita e ao CLI do benchmark por poste (E02, Task 3).

Valores calculados à mão; só fixtures sintéticas. O analisador real só roda nos testes de
``executar`` que usam a rede sintética; o mapeamento é atacado com projetos montados em memória.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
import scripts.benchmark_ficha_poste as modulo
from scripts.benchmark_ficha_poste import ficha_predita, main
from scripts.benchmark_network_pdf import run_variant as run_variant_real
from scripts.ficha_poste import validar_ficha
from tests.factories import _item_id, _option_id, complete_project
from tests.pdf_fixtures import create_network_benchmark_pdf

from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    NivelRede,
    OrigemComprimentoVao,
    SituacaoProjeto,
    TipoPontoRede,
)
from zeny_project_handler.domain.project import (
    Cabo,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    PontoRede,
    Poste,
    Projeto,
)
from zeny_project_handler.domain.values import (
    CoordenadaCampo,
    GeometriaDocumento,
    PontoNormalizado,
)

SHA = "b" * 64


def _pn(x: str, y: str) -> PontoNormalizado:
    return PontoNormalizado(Decimal(x), Decimal(y))


class _Cenario:
    """Projeto em memória com duas páginas (1 e 2) e fábricas de elementos."""

    def __init__(self, catalogo: CatalogoTecnico) -> None:
        base = complete_project(catalogo)
        pagina = base.documentos[0].paginas[0]
        self.p1 = replace(pagina, id=uuid4(), numero=1)
        self.p2 = replace(pagina, id=uuid4(), numero=2)
        documento = replace(base.documentos[0], paginas=(self.p1, self.p2))
        self.projeto = replace(
            base,
            documentos=(documento,),
            ordem_leitura_paginas=(self.p1.id, self.p2.id),
            elementos=(),
            pontos_rede=(),
            terminais=(),
            conexoes_internas=(),
            vinculos_obra=(),
            relacoes_confirmadas=(),
        )
        self.catalogo = catalogo
        self.fases = _option_id(catalogo, "configuracao_fases", "MONOFÁSICA")
        self.tensao = _option_id(catalogo, "nivel_tensao", "MT")
        self.elementos: list[Any] = []
        self.pontos: list[PontoRede] = []

    def caixa(self, pagina: Any, a: tuple[str, str], b: tuple[str, str]) -> GeometriaDocumento:
        return GeometriaDocumento.caixa(pagina.id, _pn(*a), _pn(*b))

    def poste(self, **kw: Any) -> Poste:
        kw.setdefault("geometria", self.caixa(self.p1, ("0.1", "0.1"), ("0.2", "0.2")))
        elemento = Poste(
            id=uuid4(),
            tipo_catalogo_id=_item_id(self.catalogo, CategoriaElemento.POSTE),
            situacao=SituacaoProjeto.EXISTENTE,
            **kw,
        )
        self.elementos.append(elemento)
        return elemento

    def ponto(self, poste: Poste | None) -> PontoRede:
        ponto = PontoRede(
            id=uuid4(),
            poste_id=None if poste is None else poste.id,
            nome="ponto",
            nivel_rede=NivelRede.MT,
            nivel_tensao_opcao_id=self.tensao,
            configuracao_fases_opcao_id=self.fases,
            tipo=TipoPontoRede.POSTE if poste is not None else TipoPontoRede.ENTREGA,
        )
        self.pontos.append(ponto)
        return ponto

    def estrutura(self, classe: Any, poste: Poste, codigo: str | None) -> Any:
        categoria = (
            CategoriaElemento.ESTRUTURA_MT
            if classe is EstruturaMt
            else CategoriaElemento.ESTRUTURA_BT
        )
        elemento = classe(
            id=uuid4(),
            tipo_catalogo_id=_item_id(self.catalogo, categoria),
            situacao=SituacaoProjeto.EXISTENTE,
            poste_id=poste.id,
            codigo_observado=codigo,
        )
        self.elementos.append(elemento)
        return elemento

    def equipamento(self, poste: Poste, **kw: Any) -> Equipamento:
        elemento = Equipamento(
            id=uuid4(),
            tipo_catalogo_id=_item_id(self.catalogo, CategoriaElemento.EQUIPAMENTO),
            situacao=SituacaoProjeto.EXISTENTE,
            poste_id=poste.id,
            **kw,
        )
        self.elementos.append(elemento)
        return elemento

    def cabo(self, origem: PontoRede, destino: PontoRede, **kw: Any) -> Cabo:
        elemento = Cabo(
            id=uuid4(),
            tipo_catalogo_id=_item_id(self.catalogo, CategoriaElemento.CABO),
            situacao=SituacaoProjeto.EXISTENTE,
            ponto_origem_id=origem.id,
            ponto_destino_id=destino.id,
            **kw,
        )
        self.elementos.append(elemento)
        return elemento

    def montar(self) -> Projeto:
        return replace(
            self.projeto, elementos=tuple(self.elementos), pontos_rede=tuple(self.pontos)
        )


def _variante(
    projeto: Projeto,
    atributos: dict[UUID, dict[str, Any]] | None = None,
    **extras: Any,
) -> dict[str, Any]:
    propostas = []
    decisoes: list[Any] = []
    for elemento_id, valores in (atributos or {}).items():
        proposta = SimpleNamespace(id=uuid4(), atributos_sugeridos=tuple(valores.items()))
        propostas.append(proposta)
        decisoes.append(
            SimpleNamespace(proposta_id=proposta.id, elemento_confirmado_id=elemento_id)
        )
    variante: dict[str, Any] = {
        "project": projeto,
        "decisions": (*decisoes, None),
        "semantic": SimpleNamespace(elementos=tuple(propostas)),
        "analyzer": {"version": "a1", "signature": "assinatura"},
        "interpreter_version": "i1",
        "registry_signature": "registro",
    }
    variante.update(extras)
    return variante


def _ficha(
    cenario: _Cenario, atributos: dict[UUID, dict[str, Any]] | None = None
) -> dict[str, Any]:
    ficha = ficha_predita(_variante(cenario.montar(), atributos), SHA, native_only=True)
    assert validar_ficha(ficha) == []
    return ficha


# ---------------------------------------------------------------------------------------------
# Mapeamento da ficha predita
# ---------------------------------------------------------------------------------------------


def test_pagina_do_poste_vem_do_pagina_id_da_geometria(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    na_um = cenario.poste(identificador_operacional="A")
    na_dois = cenario.poste(
        identificador_operacional="B",
        geometria=cenario.caixa(cenario.p2, ("0.3", "0.3"), ("0.4", "0.4")),
    )

    ficha = _ficha(cenario)

    paginas = {poste["id"]: poste["pagina"] for poste in ficha["postes"]}
    assert paginas == {str(na_um.id): 1, str(na_dois.id): 2}


def test_bbox_de_polilinha_desordenada_e_o_envelope_dos_pontos(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    cenario.poste(
        geometria=GeometriaDocumento.polilinha(
            cenario.p1.id, (_pn("0.3", "0.6"), _pn("0.1", "0.2"), _pn("0.5", "0.4"))
        )
    )

    assert _ficha(cenario)["postes"][0]["bbox"] == [0.1, 0.2, 0.5, 0.6]


def test_bbox_de_poste_em_ponto_tem_area_zero_e_e_aceita(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    cenario.poste(geometria=GeometriaDocumento.ponto(cenario.p1.id, _pn("0.25", "0.75")))

    assert _ficha(cenario)["postes"][0]["bbox"] == [0.25, 0.75, 0.25, 0.75]


def test_coordenada_presente_e_ausente_e_zona_nula(catalogo_inicial: CatalogoTecnico) -> None:
    cenario = _Cenario(catalogo_inicial)
    com = cenario.poste(
        coordenada_campo=CoordenadaCampo(
            leste=Decimal("397617.25"), norte=Decimal("7725802.5"), zona="23K"
        )
    )
    sem_zona = cenario.poste(
        coordenada_campo=CoordenadaCampo(leste=Decimal("1.5"), norte=Decimal("2.5"))
    )
    sem = cenario.poste()

    por_id = {poste["id"]: poste["coordenada"] for poste in _ficha(cenario)["postes"]}

    assert por_id[str(com.id)] == {"leste": 397617.25, "norte": 7725802.5, "zona": "23K"}
    assert por_id[str(sem_zona.id)] == {"leste": 1.5, "norte": 2.5, "zona": None}
    assert por_id[str(sem.id)] is None


def test_estruturas_ordenadas_sem_nulos_e_so_do_proprio_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    poste = cenario.poste()
    outro = cenario.poste(geometria=cenario.caixa(cenario.p1, ("0.5", "0.5"), ("0.6", "0.6")))
    cenario.estrutura(EstruturaMt, poste, "M2")
    cenario.estrutura(EstruturaBt, poste, "B1")
    cenario.estrutura(EstruturaMt, poste, None)
    cenario.estrutura(EstruturaMt, poste, "A9")
    cenario.estrutura(EstruturaMt, outro, "Z0")

    por_id = {item["id"]: item["estruturas"] for item in _ficha(cenario)["postes"]}

    assert por_id[str(poste.id)] == ["A9", "B1", "M2"]
    assert por_id[str(outro.id)] == ["Z0"]


def test_poste_sem_estrutura_tem_lista_vazia_e_pendentes_vazio(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    cenario.poste()

    poste = _ficha(cenario)["postes"][0]

    assert poste["estruturas"] == []
    assert poste["pendentes"] == []
    assert poste["simbolos"] == []
    assert poste["identificador"] is None
    assert poste["poste"] is None


def test_poste_sem_geometria_fica_fora_e_seu_equipamento_e_ignorado_sem_contagem(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    cenario.poste(identificador_operacional="COM")
    sem_geometria = cenario.poste(identificador_operacional="SEM", geometria=None)
    cenario.equipamento(
        sem_geometria, geometria=cenario.caixa(cenario.p1, ("0.1", "0.1"), ("0.2", "0.2"))
    )
    equipamento_id = cenario.elementos[-1].id

    ficha = _ficha(cenario, {equipamento_id: {"simbolo_classe": "ESTAI"}})

    assert [poste["identificador"] for poste in ficha["postes"]] == ["COM"]
    assert ficha["atributos_extras"] == {
        "equipamentos_sem_simbolo": 0,
        "simbolos_fora_do_inventario": 0,
        "simbolos_sem_area": 0,
    }


def test_simbolos_vao_para_o_poste_dono_com_bbox_envelope(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    a = cenario.poste(identificador_operacional="A")
    b = cenario.poste(
        identificador_operacional="B",
        geometria=cenario.caixa(cenario.p1, ("0.5", "0.5"), ("0.6", "0.6")),
    )
    ea = cenario.equipamento(
        a, geometria=cenario.caixa(cenario.p1, ("0.1", "0.2"), ("0.15", "0.3"))
    )
    eb = cenario.equipamento(b, geometria=cenario.caixa(cenario.p1, ("0.7", "0.7"), ("0.8", "0.9")))

    ficha = _ficha(
        cenario,
        {ea.id: {"simbolo_classe": "ESTAI"}, eb.id: {"simbolo_classe": "ESTAI"}},
    )

    por_identificador = {poste["identificador"]: poste["simbolos"] for poste in ficha["postes"]}
    assert por_identificador["A"] == [
        {"id": str(ea.id), "classe": "ESTAI", "bbox": [0.1, 0.2, 0.15, 0.3]}
    ]
    assert por_identificador["B"] == [
        {"id": str(eb.id), "classe": "ESTAI", "bbox": [0.7, 0.7, 0.8, 0.9]}
    ]


@pytest.mark.parametrize(
    "classe",
    [
        "POSTE",
        "POSTE_AT",
        "ESTRUTURA_POSTE_MT",
        "ESTRUTURA_POSTE_AT",
        "",
        "estai",
        "NAO_EXISTE",
    ],
)
def test_classe_do_proprio_poste_ou_fora_do_inventario_nao_vira_simbolo(
    catalogo_inicial: CatalogoTecnico, classe: str
) -> None:
    cenario = _Cenario(catalogo_inicial)
    poste = cenario.poste()
    equipamento = cenario.equipamento(
        poste, geometria=cenario.caixa(cenario.p1, ("0.1", "0.1"), ("0.2", "0.2"))
    )

    ficha = _ficha(cenario, {equipamento.id: {"simbolo_classe": classe}})

    assert ficha["postes"][0]["simbolos"] == []
    assert ficha["atributos_extras"]["simbolos_fora_do_inventario"] == 1
    assert ficha["atributos_extras"]["simbolos_sem_area"] == 0
    assert ficha["atributos_extras"]["equipamentos_sem_simbolo"] == 0


def test_simbolo_sem_geometria_ou_com_bbox_sem_area_e_contado_como_sem_area(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    poste = cenario.poste()
    sem_geometria = cenario.equipamento(poste, geometria=None)
    em_ponto = cenario.equipamento(
        poste, geometria=GeometriaDocumento.ponto(cenario.p1.id, _pn("0.3", "0.3"))
    )
    linha_horizontal = cenario.equipamento(
        poste,
        geometria=GeometriaDocumento.polilinha(
            cenario.p1.id, (_pn("0.1", "0.4"), _pn("0.5", "0.4"))
        ),
    )
    linha_vertical = cenario.equipamento(
        poste,
        geometria=GeometriaDocumento.polilinha(
            cenario.p1.id, (_pn("0.4", "0.1"), _pn("0.4", "0.5"))
        ),
    )

    ficha = _ficha(
        cenario,
        {
            item.id: {"simbolo_classe": "ESTAI"}
            for item in (sem_geometria, em_ponto, linha_horizontal, linha_vertical)
        },
    )

    assert ficha["postes"][0]["simbolos"] == []
    assert ficha["atributos_extras"]["simbolos_sem_area"] == 4


def test_equipamento_sem_proposta_ou_com_simbolo_classe_nulo_conta_como_sem_simbolo(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    poste = cenario.poste()
    caixa = cenario.caixa(cenario.p1, ("0.1", "0.1"), ("0.2", "0.2"))
    sem_proposta = cenario.equipamento(poste, geometria=caixa)
    classe_nula = cenario.equipamento(poste, geometria=caixa)

    ficha = _ficha(cenario, {classe_nula.id: {"simbolo_classe": None}})

    assert sem_proposta.id != classe_nula.id
    assert ficha["postes"][0]["simbolos"] == []
    assert ficha["atributos_extras"]["equipamentos_sem_simbolo"] == 2


def test_decisao_sem_elemento_ou_com_proposta_inexistente_nao_atribui_origem(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    poste = cenario.poste(codigo_observado="P-9M")
    projeto = cenario.montar()
    proposta = SimpleNamespace(
        id=uuid4(), atributos_sugeridos=(("origem_simbolo_ocorrencia_id", "x"),)
    )
    variante = _variante(projeto)
    variante["semantic"] = SimpleNamespace(elementos=(proposta,))
    variante["decisions"] = (
        SimpleNamespace(proposta_id=proposta.id, elemento_confirmado_id=None),
        SimpleNamespace(proposta_id=uuid4(), elemento_confirmado_id=poste.id),
        None,
    )

    ficha = ficha_predita(variante, SHA, native_only=True)

    assert ficha["postes"][0]["poste"] == "P-9M"
    assert ficha["postes"][0]["atributos_extras"] == {}


def test_poste_de_simbolo_com_atributo_de_origem_nulo_ainda_e_de_simbolo(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    poste = cenario.poste(codigo_observado="ESTRUTURA_POSTE_MT")

    ficha = _ficha(cenario, {poste.id: {"origem_simbolo_ocorrencia_id": None}})

    assert ficha["postes"][0]["poste"] is None
    assert ficha["postes"][0]["atributos_extras"] == {
        "origem": "simbolo",
        "classe_simbolo": "ESTRUTURA_POSTE_MT",
    }


# ---------------------------------------------------------------------------------------------
# Vãos
# ---------------------------------------------------------------------------------------------


def _dois_postes(cenario: _Cenario, **kw: Any) -> tuple[Poste, Poste, PontoRede, PontoRede]:
    a = cenario.poste(identificador_operacional="A", **kw)
    b = cenario.poste(
        identificador_operacional="B",
        geometria=cenario.caixa(cenario.p1, ("0.5", "0.5"), ("0.6", "0.6")),
    )
    return a, b, cenario.ponto(a), cenario.ponto(b)


def test_vao_usa_ids_dos_postes_e_nao_dos_pontos_de_rede(catalogo_inicial: CatalogoTecnico) -> None:
    cenario = _Cenario(catalogo_inicial)
    a, b, pa, pb = _dois_postes(cenario)
    cenario.cabo(pa, pb, codigo_observado="ABC-4 CA", comprimento_m=Decimal("35.5"))

    (vao,) = _ficha(cenario)["vaos"]

    assert (vao["de"], vao["para"]) == (str(a.id), str(b.id))
    assert vao["cabo"] == "ABC-4 CA"
    assert vao["comprimento_m"] == 35.5
    assert vao["pendentes"] == []
    assert vao["atributos_extras"] == {"origem_comprimento": "INFORMADO"}


def test_origem_do_comprimento_anotacao_do_desenho_e_preservada(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    _, _, pa, pb = _dois_postes(cenario)
    cenario.cabo(
        pa,
        pb,
        comprimento_m=Decimal("12.25"),
        origem_comprimento=OrigemComprimentoVao.ANOTACAO_DESENHO,
    )

    (vao,) = _ficha(cenario)["vaos"]

    assert vao["comprimento_m"] == 12.25
    assert vao["atributos_extras"] == {"origem_comprimento": "ANOTACAO_DESENHO"}
    assert vao["cabo"] is None


def test_comprimento_calculado_das_coordenadas_3_4_5_vale_500(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    a = cenario.poste(
        identificador_operacional="A",
        coordenada_campo=CoordenadaCampo(leste=Decimal("1000"), norte=Decimal("2000")),
    )
    b = cenario.poste(
        identificador_operacional="B",
        geometria=cenario.caixa(cenario.p1, ("0.5", "0.5"), ("0.6", "0.6")),
        coordenada_campo=CoordenadaCampo(leste=Decimal("1300"), norte=Decimal("2400")),
    )
    cenario.cabo(cenario.ponto(a), cenario.ponto(b), codigo_observado="CA")

    (vao,) = _ficha(cenario)["vaos"]

    assert vao["comprimento_m"] == 500.0
    assert vao["atributos_extras"] == {"origem_comprimento": "COORDENADAS"}


def test_vao_sem_comprimento_nem_coordenadas_tem_nulos(catalogo_inicial: CatalogoTecnico) -> None:
    cenario = _Cenario(catalogo_inicial)
    _, _, pa, pb = _dois_postes(cenario)
    cenario.cabo(pa, pb, codigo_observado="CA")

    (vao,) = _ficha(cenario)["vaos"]

    assert vao["comprimento_m"] is None
    assert vao["atributos_extras"] == {"origem_comprimento": None}


def test_dois_cabos_no_mesmo_par_geram_dois_vaos(catalogo_inicial: CatalogoTecnico) -> None:
    cenario = _Cenario(catalogo_inicial)
    a, b, pa, pb = _dois_postes(cenario)
    cenario.cabo(pa, pb, codigo_observado="MT", comprimento_m=Decimal("10"))
    cenario.cabo(pa, pb, codigo_observado="BT", comprimento_m=Decimal("11"))

    vaos = _ficha(cenario)["vaos"]

    assert sorted((v["cabo"], v["comprimento_m"]) for v in vaos) == [("BT", 11.0), ("MT", 10.0)]
    assert {(v["de"], v["para"]) for v in vaos} == {(str(a.id), str(b.id))}


def test_vao_com_ponta_em_poste_fora_da_ficha_ou_em_ponto_de_entrega_e_descartado(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    a, b, pa, pb = _dois_postes(cenario)
    sem_geometria = cenario.poste(identificador_operacional="X", geometria=None)
    px = cenario.ponto(sem_geometria)
    entrega = cenario.ponto(None)
    cenario.cabo(pa, pb, codigo_observado="OK", comprimento_m=Decimal("1"))
    cenario.cabo(pa, px, codigo_observado="PONTA_ORIGEM_FORA", comprimento_m=Decimal("2"))
    cenario.cabo(px, pb, codigo_observado="PONTA_DESTINO_FORA", comprimento_m=Decimal("3"))
    cenario.cabo(pa, entrega, codigo_observado="ENTREGA", comprimento_m=Decimal("4"))

    vaos = _ficha(cenario)["vaos"]

    assert [v["cabo"] for v in vaos] == ["OK"]
    assert (vaos[0]["de"], vaos[0]["para"]) == (str(a.id), str(b.id))


def test_vao_so_entre_postes_da_ficha_mesmo_com_cabo_ligando_ponto_do_proprio_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    a = cenario.poste(identificador_operacional="A")
    cenario.cabo(cenario.ponto(a), cenario.ponto(a), codigo_observado="LACO")

    assert _ficha(cenario)["vaos"] == []


# ---------------------------------------------------------------------------------------------
# Gerador e raiz
# ---------------------------------------------------------------------------------------------


def test_gerador_converte_para_tipos_json_e_preserva_native_only(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cenario = _Cenario(catalogo_inicial)
    cenario.poste()
    identidade = uuid4()
    variante = _variante(
        cenario.montar(),
        analyzer={"version": 3, "signature": identidade},
        interpreter_version=Path("v2"),
        registry_signature=None,
    )

    nativo = ficha_predita(variante, SHA, native_only=True)
    com_ocr = ficha_predita(variante, SHA, native_only=False)

    assert nativo["gerador"] == {
        "versao_extracao": "projeto-promovido-v1",
        "analisador_versao": 3,
        "analisador_assinatura": str(identidade),
        "interpretador_versao": str(Path("v2")),
        "registro_assinatura": None,
        "native_only": True,
    }
    assert com_ocr["gerador"]["native_only"] is False
    json.dumps(nativo)


def test_ficha_vazia_e_valida_e_tem_raiz_completa(catalogo_inicial: CatalogoTecnico) -> None:
    cenario = _Cenario(catalogo_inicial)

    ficha = _ficha(cenario)

    assert ficha["postes"] == []
    assert ficha["vaos"] == []
    assert ficha["schema_version"] == 1
    assert ficha["tipo"] == "predicao"
    assert ficha["pdf_sha256"] == SHA
    assert ficha["escopo_anotacao"] == {"tipo": "completo"}
    assert ficha["atributos_extras"] == {
        "equipamentos_sem_simbolo": 0,
        "simbolos_fora_do_inventario": 0,
        "simbolos_sem_area": 0,
    }


def test_ficha_mista_e_valida_e_serializavel(catalogo_inicial: CatalogoTecnico) -> None:
    cenario = _Cenario(catalogo_inicial)
    a, b, pa, pb = _dois_postes(cenario, codigo_observado="POSTE")
    cenario.estrutura(EstruturaMt, a, "N1")
    cenario.cabo(pa, pb, codigo_observado="CA", comprimento_m=Decimal("7"))
    equipamento = cenario.equipamento(
        a, geometria=cenario.caixa(cenario.p2, ("0.1", "0.1"), ("0.2", "0.2"))
    )

    ficha = _ficha(
        cenario,
        {a.id: {"origem_simbolo_ocorrencia_id": "o"}, equipamento.id: {"simbolo_classe": "ESTAI"}},
    )

    assert json.loads(json.dumps(ficha)) == ficha
    assert b.id != a.id


# ---------------------------------------------------------------------------------------------
# executar / main
# ---------------------------------------------------------------------------------------------


def _referencia_para(pdf: Path, tmp_path: Path, sha: str | None = None) -> Path:
    from tests.unit.test_benchmark_ficha_poste import _grava, _referencia_sintetica

    return _grava(
        tmp_path / "ref.json", _referencia_sintetica(sha or sha256(pdf.read_bytes()).hexdigest())
    )


def _impressao(pdf: Path) -> tuple[int, int, str]:
    estado = pdf.stat()
    return estado.st_size, estado.st_mtime_ns, sha256(pdf.read_bytes()).hexdigest()


def test_sha_diferente_e_recusado_antes_de_preparar_ocr_e_rodar_o_analisador(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    chamadas: list[str] = []

    def analisador(*_: Any, **__: Any) -> Any:
        chamadas.append("run_variant")
        raise AssertionError("o analisador não pode rodar")

    def ocr(*_: Any, **__: Any) -> Any:
        chamadas.append("ocr")
        raise AssertionError("o OCR não pode ser preparado")

    monkeypatch.setattr(modulo, "run_variant", analisador)
    monkeypatch.setattr(modulo, "inspect_tesseract_runtime", ocr)
    saida = tmp_path / "saida"

    with pytest.raises(ValueError, match="outro PDF"):
        modulo.executar(
            pdf,
            _referencia_para(pdf, tmp_path, "c" * 64),
            saida,
            native_only=False,
            runtime_directory=tmp_path / "runtime",
        )

    assert chamadas == []
    assert not saida.exists()


def test_referencia_invalida_e_recusada_antes_de_rodar_o_analisador(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    chamadas: list[str] = []

    def nao_deve_rodar(*_: Any, **__: Any) -> Any:
        chamadas.append("run")
        raise AssertionError("o analisador não pode rodar")

    monkeypatch.setattr(modulo, "run_variant", nao_deve_rodar)
    referencia = tmp_path / "ref.json"
    referencia.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

    with pytest.raises(ValueError):
        modulo.executar(
            pdf, referencia, tmp_path / "saida", native_only=True, runtime_directory=tmp_path
        )

    assert chamadas == []
    assert not (tmp_path / "saida").exists()


def test_pdf_inexistente_levanta_filenotfound_sem_criar_saida(tmp_path: Path) -> None:
    saida = tmp_path / "saida"

    with pytest.raises(FileNotFoundError):
        modulo.executar(
            tmp_path / "nao-existe.pdf",
            tmp_path / "ref.json",
            saida,
            native_only=True,
            runtime_directory=tmp_path,
        )

    assert not saida.exists()


def test_pdf_fica_intacto_e_saida_so_tem_os_dois_arquivos(tmp_path: Path) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    os.utime(pdf, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
    antes = _impressao(pdf)
    saida = tmp_path / "a" / "b" / "saida"

    modulo.executar(
        pdf,
        _referencia_para(pdf, tmp_path),
        saida,
        native_only=True,
        runtime_directory=tmp_path / "runtime",
    )

    assert _impressao(pdf) == antes
    assert sorted(item.name for item in saida.iterdir()) == ["avaliacao.json", "ficha-predita.json"]


@pytest.mark.parametrize("mudanca", ["anexa_bytes", "mesmo_tamanho_e_mtime", "so_mtime"])
def test_pdf_alterado_durante_o_benchmark_falha_sem_gravar_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mudanca: str
) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    original = run_variant_real
    estado = pdf.stat()

    def mexendo(source: Path, directory: Path, **kw: Any) -> Any:
        resultado = original(source, directory, **kw)
        conteudo = source.read_bytes()
        if mudanca == "anexa_bytes":
            source.write_bytes(conteudo + b"\n%lixo")
        elif mudanca == "mesmo_tamanho_e_mtime":
            # Só o SHA-256 denuncia: tamanho e mtime voltam ao valor original.
            source.write_bytes(conteudo[:-1] + bytes([conteudo[-1] ^ 1]))
            os.utime(source, ns=(estado.st_atime_ns, estado.st_mtime_ns))
        else:
            os.utime(source, ns=(estado.st_atime_ns, estado.st_mtime_ns + 5_000_000_000))
        return resultado

    monkeypatch.setattr(modulo, "run_variant", mexendo)
    saida = tmp_path / "saida"

    with pytest.raises(RuntimeError, match="Origem mudou"):
        modulo.executar(
            pdf,
            _referencia_para(pdf, tmp_path),
            saida,
            native_only=True,
            runtime_directory=tmp_path / "runtime",
        )

    assert list(saida.iterdir()) == []


@pytest.mark.parametrize("etapa", ["run_variant", "ficha_predita", "validar_ficha", "avaliar"])
def test_falha_no_meio_nao_deixa_diretorio_temporario_nem_arquivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, etapa: str
) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")

    def explode(*_: Any, **__: Any) -> Any:
        raise RuntimeError("falha injetada")

    if etapa == "validar_ficha":
        monkeypatch.setattr(modulo, "validar_ficha", lambda _: ["erro injetado"])
    else:
        monkeypatch.setattr(modulo, etapa, explode)
    saida = tmp_path / "saida"

    with pytest.raises((RuntimeError, ValueError)):
        modulo.executar(
            pdf,
            _referencia_para(pdf, tmp_path),
            saida,
            native_only=True,
            runtime_directory=tmp_path / "runtime",
        )

    assert list(saida.iterdir()) == []


def test_arquivos_gravados_sao_json_ordenado_utf8_sem_escape_e_sem_caminhos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "documento-sigiloso.pdf")
    original = modulo.ficha_predita

    def com_acentos(*args: Any, **kw: Any) -> dict[str, Any]:
        ficha = original(*args, **kw)
        ficha["postes"][0]["atributos_extras"] = {"zeta": "ção", "alfa": "açaí"}
        return ficha

    monkeypatch.setattr(modulo, "ficha_predita", com_acentos)
    saida = tmp_path / "saida"
    runtime = tmp_path / "pasta-runtime-secreta"

    modulo.executar(
        pdf,
        _referencia_para(pdf, tmp_path),
        saida,
        native_only=True,
        runtime_directory=runtime,
    )

    for nome in ("ficha-predita.json", "avaliacao.json"):
        bruto = (saida / nome).read_bytes()
        # write_text em Windows grava CRLF: o brief não fixa a quebra de linha, então normalizo.
        texto = bruto.decode("utf-8").replace("\r\n", "\n")
        dados = json.loads(texto)
        assert texto == json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True)
        assert "\\u" not in texto
        for proibido in (
            str(tmp_path),
            tmp_path.as_posix(),
            str(tmp_path).replace("\\", "\\\\"),
            "documento-sigiloso",
            "pasta-runtime-secreta",
            ".pdf",
        ):
            assert proibido not in texto
    ficha = json.loads((saida / "ficha-predita.json").read_text(encoding="utf-8"))
    assert "ção" in (saida / "ficha-predita.json").read_text(encoding="utf-8")
    assert list(ficha["postes"][0]["atributos_extras"]) == ["alfa", "zeta"]


def test_execucao_repetida_produz_arquivos_identicos(tmp_path: Path) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    referencia = _referencia_para(pdf, tmp_path)
    textos = []
    for nome in ("um", "dois"):
        modulo.executar(
            pdf,
            referencia,
            tmp_path / nome,
            native_only=True,
            runtime_directory=tmp_path / "runtime",
        )
        textos.append(
            tuple(
                (tmp_path / nome / arquivo).read_text(encoding="utf-8")
                for arquivo in ("ficha-predita.json", "avaliacao.json")
            )
        )

    assert textos[0] == textos[1]


def test_ficha_predita_gravada_valida_e_relatorio_devolvido_e_o_gravado(tmp_path: Path) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    saida = tmp_path / "saida"

    relatorio = modulo.executar(
        pdf,
        _referencia_para(pdf, tmp_path),
        saida,
        native_only=True,
        runtime_directory=tmp_path / "runtime",
    )

    gravado = json.loads((saida / "avaliacao.json").read_text(encoding="utf-8"))
    assert gravado == json.loads(json.dumps(relatorio))
    ficha = json.loads((saida / "ficha-predita.json").read_text(encoding="utf-8"))
    assert validar_ficha(ficha) == []
    # Rede sintética: dois postes P1/P2, um vão MT.
    assert sorted(poste["identificador"] for poste in ficha["postes"]) == ["P1", "P2"]
    assert len(ficha["vaos"]) == 1
    assert ficha["vaos"][0]["cabo"] == "ABC-4 CA"
    assert {poste["pagina"] for poste in ficha["postes"]} == {1}
    assert ficha["gerador"]["native_only"] is True


def test_sem_native_only_exige_portugues_e_nao_roda_o_analisador(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    chamadas: list[str] = []
    monkeypatch.setattr(
        modulo,
        "inspect_tesseract_runtime",
        lambda _: SimpleNamespace(portugues_pronto=False, diagnostico="sem pt"),
    )

    def nao_deve_rodar(*_: Any, **__: Any) -> Any:
        chamadas.append("run")
        raise AssertionError("o analisador não pode rodar")

    monkeypatch.setattr(modulo, "run_variant", nao_deve_rodar)

    with pytest.raises(RuntimeError, match="OCR português obrigatório: sem pt"):
        modulo.executar(
            pdf,
            _referencia_para(pdf, tmp_path),
            tmp_path / "saida",
            native_only=False,
            runtime_directory=tmp_path / "runtime",
        )

    assert chamadas == []


def test_sem_native_only_monta_ocr_verifica_e_passa_ao_analisador(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    construcoes: list[tuple[Any, ...]] = []
    verificados: list[Any] = []
    recebido: dict[str, Any] = {}

    class OcrFalso:
        def __init__(self, executavel: Any, **kw: Any) -> None:
            construcoes.append((executavel, kw))

    monkeypatch.setattr(
        modulo,
        "inspect_tesseract_runtime",
        lambda diretorio: SimpleNamespace(
            portugues_pronto=True,
            executavel=Path("tess.exe"),
            diretorio_tessdata=Path("tessdata"),
            idiomas_selecionados=("por", "eng"),
            diagnostico="ok",
        ),
    )
    monkeypatch.setattr(modulo, "TesseractCliOcr", OcrFalso)
    monkeypatch.setattr(modulo, "verify_ocr", verificados.append)
    original = run_variant_real

    def espiao(source: Path, directory: Path, *, ocr: Any) -> Any:
        recebido["ocr"] = ocr
        return original(source, directory, ocr=None)

    monkeypatch.setattr(modulo, "run_variant", espiao)

    modulo.executar(
        pdf,
        _referencia_para(pdf, tmp_path),
        tmp_path / "saida",
        native_only=False,
        runtime_directory=tmp_path / "runtime",
    )

    assert construcoes == [
        (Path("tess.exe"), {"language": "por+eng", "tessdata_directory": Path("tessdata")})
    ]
    assert verificados == [recebido["ocr"]]
    assert isinstance(recebido["ocr"], OcrFalso)
    ficha = json.loads((tmp_path / "saida" / "ficha-predita.json").read_text(encoding="utf-8"))
    assert ficha["gerador"]["native_only"] is False


def test_native_only_nao_inspeciona_tesseract_e_roda_sem_ocr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    recebido: dict[str, Any] = {}

    def nao_deve(*_: Any, **__: Any) -> Any:
        raise AssertionError("native_only não pode tocar no Tesseract")

    monkeypatch.setattr(modulo, "inspect_tesseract_runtime", nao_deve)
    original = run_variant_real

    def espiao(source: Path, directory: Path, *, ocr: Any) -> Any:
        recebido["ocr"] = ocr
        return original(source, directory, ocr=ocr)

    monkeypatch.setattr(modulo, "run_variant", espiao)

    modulo.executar(
        pdf,
        _referencia_para(pdf, tmp_path),
        tmp_path / "saida",
        native_only=True,
        runtime_directory=tmp_path / "runtime",
    )

    assert recebido["ocr"] is None


def test_main_repassa_argumentos_e_padroes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def falso(*args: Any, **kw: Any) -> dict[str, Any]:
        capturado.append((args, kw))
        return {}

    monkeypatch.setattr(modulo, "executar", falso)

    assert main(["entrada.pdf", "--referencia", "ref.json", "--saida", "out"]) == 0
    assert (
        main(
            [
                "entrada.pdf",
                "--referencia",
                "ref.json",
                "--saida",
                "out",
                "--native-only",
                "--runtime-directory",
                "rt",
            ]
        )
        == 0
    )

    assert capturado[0] == (
        (Path("entrada.pdf"), Path("ref.json"), Path("out")),
        {"native_only": False, "runtime_directory": Path("tmp/benchmark-runtime")},
    )
    assert capturado[1] == (
        (Path("entrada.pdf"), Path("ref.json"), Path("out")),
        {"native_only": True, "runtime_directory": Path("rt")},
    )


@pytest.mark.parametrize(
    "argumentos",
    [
        [],
        ["entrada.pdf"],
        ["entrada.pdf", "--referencia", "ref.json"],
        ["--referencia", "ref.json", "--saida", "out"],
        ["entrada.pdf", "--referencia", "ref.json", "--saida", "out", "--desconhecida"],
    ],
)
def test_main_com_argumentos_incompletos_sai_com_codigo_2(
    argumentos: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(modulo, "executar", lambda *a, **k: pytest.fail("não deve executar"))

    with pytest.raises(SystemExit) as saida:
        main(argumentos)

    assert saida.value.code == 2


def test_main_nao_devolve_zero_quando_a_referencia_e_de_outro_pdf(tmp_path: Path) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    saida = tmp_path / "saida"

    with pytest.raises(ValueError, match="outro PDF"):
        main(
            [
                str(pdf),
                "--referencia",
                str(_referencia_para(pdf, tmp_path, "d" * 64)),
                "--saida",
                str(saida),
                "--native-only",
            ]
        )

    assert not saida.exists()
