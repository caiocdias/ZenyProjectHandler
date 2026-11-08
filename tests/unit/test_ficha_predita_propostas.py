from __future__ import annotations

import ast
import json
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from scripts import benchmark_ficha_poste
from scripts.benchmark_ficha_poste import (
    VERSAO_EXTRACAO,
    VERSAO_EXTRACAO_PROPOSTAS,
    VERSOES_EXTRACAO,
    executar,
    ficha_predita,
    main,
)
from scripts.ficha_poste import validar_ficha
from scripts.ficha_poste_avaliador import avaliar
from scripts.ficha_predita_propostas import CHAVES_PENDENCIA, ficha_predita_propostas
from tests.factories import complete_project
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica

from zeny_project_handler.domain.analysis import PropostaElemento, PropostaRelacao
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao, SituacaoProjeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

SHA_QUALQUER = "a" * 64
RAIZ = Path(__file__).resolve().parents[2]

POSTE = CategoriaElemento.POSTE
ESTRUTURA_MT = CategoriaElemento.ESTRUTURA_MT
EQUIPAMENTO = CategoriaElemento.EQUIPAMENTO
CABO = CategoriaElemento.CABO


def _decimal(valor: float) -> Decimal:
    return Decimal(str(round(valor, 6)))


class _Cena:
    """Variante sintética de ``run_variant`` com projeto promovido vazio e propostas à mão."""

    def __init__(self, catalogo: CatalogoTecnico) -> None:
        base = complete_project(catalogo)
        self.projeto = replace(
            base,
            elementos=(),
            pontos_rede=(),
            terminais=(),
            conexoes_internas=(),
            vinculos_obra=(),
            relacoes_confirmadas=(),
        )
        self.pagina_id: UUID = base.documentos[0].paginas[0].id
        self.elementos: list[PropostaElemento] = []
        self.relacoes: list[PropostaRelacao] = []

    def elemento(
        self,
        categoria: CategoriaElemento,
        *,
        codigo: str | None = None,
        estado: EstadoRevisao = EstadoRevisao.PROPOSTA,
        atributos: dict[str, Any] | None = None,
        x: float = 0.2,
        y: float = 0.4,
        lado: float = 0.05,
        como_ponto: bool = False,
    ) -> PropostaElemento:
        canto = PontoNormalizado(_decimal(x), _decimal(y))
        geometria = (
            GeometriaDocumento.ponto(self.pagina_id, canto)
            if como_ponto
            else GeometriaDocumento.caixa(
                self.pagina_id, canto, PontoNormalizado(_decimal(x + lado), _decimal(y + lado))
            )
        )
        proposta = PropostaElemento(
            id=uuid4(),
            execucao_id=uuid4(),
            categoria=categoria,
            situacao_projeto=SituacaoProjeto.EXISTENTE,
            estado_revisao=estado,
            evidencia_ids=(uuid4(),),
            geometria=geometria,
            codigo_observado=codigo,
            atributos_sugeridos=tuple((atributos or {}).items()),
        )
        self.elementos.append(proposta)
        return proposta

    def relacao(
        self,
        origem: PropostaElemento,
        destino: PropostaElemento,
        tipo: str,
        *,
        estado: EstadoRevisao = EstadoRevisao.PROPOSTA,
    ) -> PropostaRelacao:
        relacao = PropostaRelacao(
            id=uuid4(),
            execucao_id=uuid4(),
            origem_referencia_id=origem.id,
            destino_referencia_id=destino.id,
            tipo_relacao=tipo,
            evidencia_ids=(uuid4(),),
            estado_revisao=estado,
        )
        self.relacoes.append(relacao)
        return relacao

    def variante(self) -> dict[str, Any]:
        return {
            "project": self.projeto,
            "decisions": (),
            "semantic": SimpleNamespace(
                elementos=tuple(self.elementos), relacoes=tuple(self.relacoes)
            ),
            "analyzer": {"version": "a1", "signature": "assinatura"},
            "interpreter_version": "i1",
            "registry_signature": "registro",
        }

    def ficha(self) -> dict[str, Any]:
        return ficha_predita_propostas(self.variante(), SHA_QUALQUER, native_only=True)


def _cena_completa(
    catalogo: CatalogoTecnico, estados: dict[str, EstadoRevisao] | None = None
) -> tuple[_Cena, dict[str, PropostaElemento]]:
    """P1 e P2, estrutura N3 em P1, estai em P2 e cabo ABC de 35 m entre os dois."""
    ruim = estados or {}
    proposta = EstadoRevisao.PROPOSTA
    cena = _Cena(catalogo)
    p1 = cena.elemento(
        POSTE,
        codigo="POSTE",
        estado=ruim.get("p1", proposta),
        atributos={
            "identificador_operacional": "P1",
            "coordenada_leste": 100.5,
            "coordenada_norte": 200.25,
        },
    )
    p2 = cena.elemento(
        POSTE,
        codigo="POSTE",
        x=0.6,
        atributos={"identificador_operacional": "P2"},
    )
    estrutura = cena.elemento(ESTRUTURA_MT, codigo="N3", estado=ruim.get("estrutura", proposta))
    equipamento = cena.elemento(
        EQUIPAMENTO,
        estado=ruim.get("equipamento", proposta),
        atributos={"simbolo_classe": "ESTAI"},
        x=0.6,
    )
    cabo = cena.elemento(
        CABO,
        codigo="ABC",
        estado=ruim.get("cabo", proposta),
        atributos={"comprimento_m": 35},
    )
    cena.relacao(estrutura, p1, "INSTALADA_EM", estado=ruim.get("rel-estrutura", proposta))
    cena.relacao(equipamento, p2, "INSTALADO_EM", estado=ruim.get("rel-equipamento", proposta))
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, p2, "CONECTA", estado=ruim.get("conecta", proposta))
    return cena, {
        "p1": p1,
        "p2": p2,
        "estrutura": estrutura,
        "equipamento": equipamento,
        "cabo": cabo,
    }


def _contagens(ficha: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        len(ficha["postes"]),
        sum(len(poste["estruturas"]) for poste in ficha["postes"]),
        sum(len(poste["simbolos"]) for poste in ficha["postes"]),
        len(ficha["vaos"]),
    )


def test_propostas_presentes_viram_ficha(catalogo_inicial: CatalogoTecnico) -> None:
    cena, elementos = _cena_completa(catalogo_inicial)

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["tipo"] == "predicao"
    assert ficha["gerador"]["versao_extracao"] == "propostas-v1" == VERSAO_EXTRACAO_PROPOSTAS
    assert [poste["id"] for poste in ficha["postes"]] == [
        str(elementos["p1"].id),
        str(elementos["p2"].id),
    ]
    p1, p2 = ficha["postes"]
    assert (p1["pagina"], p1["identificador"], p1["poste"]) == (1, "P1", "POSTE")
    assert p1["bbox"] == [0.2, 0.4, 0.25, 0.45]
    assert p1["coordenada"] == {"leste": 100.5, "norte": 200.25, "zona": None}
    assert p2["coordenada"] is None
    assert p1["estruturas"] == ["N3"]
    assert p2["estruturas"] == []
    assert p1["simbolos"] == []
    assert [(s["id"], s["classe"]) for s in p2["simbolos"]] == [
        (str(elementos["equipamento"].id), "ESTAI")
    ]
    assert p1["pendentes"] == p2["pendentes"] == []
    (vao,) = ficha["vaos"]
    assert vao["comprimento_m"] == 35.0
    assert vao["cabo"] == "ABC"
    assert vao["atributos_extras"] == {"origem_comprimento": "ANOTACAO_DESENHO"}
    assert vao["pendentes"] == []
    assert sorted((vao["de"], vao["para"])) == sorted((p1["id"], p2["id"]))
    assert ficha["atributos_extras"] == {
        "equipamentos_sem_simbolo": 0,
        "simbolos_sem_area": 0,
        "simbolos_fora_do_inventario": 0,
    }


def test_fonte_anterior_nao_muda(catalogo_inicial: CatalogoTecnico) -> None:
    cena, _ = _cena_completa(catalogo_inicial)

    ficha = ficha_predita(cena.variante(), SHA_QUALQUER, native_only=True)

    assert ficha["gerador"]["versao_extracao"] == "projeto-promovido-v1" == VERSAO_EXTRACAO
    assert ficha["postes"] == []
    assert VERSOES_EXTRACAO == (VERSAO_EXTRACAO, VERSAO_EXTRACAO_PROPOSTAS, "propostas-v2")


@pytest.mark.parametrize(
    ("rejeitada", "esperado"),
    [
        pytest.param("p1", (1, 0, 1, 0), id="poste"),
        pytest.param("rel-estrutura", (2, 0, 1, 1), id="relacao-da-estrutura"),
        pytest.param("estrutura", (2, 0, 1, 1), id="estrutura"),
        pytest.param("rel-equipamento", (2, 1, 0, 1), id="relacao-do-equipamento"),
        pytest.param("equipamento", (2, 1, 0, 1), id="equipamento"),
        pytest.param("cabo", (2, 1, 1, 0), id="cabo"),
        pytest.param("conecta", (2, 1, 1, 0), id="uma-das-duas-conecta"),
    ],
)
def test_proposta_rejeitada_nao_vira_campo(
    catalogo_inicial: CatalogoTecnico, rejeitada: str, esperado: tuple[int, int, int, int]
) -> None:
    cena, _ = _cena_completa(catalogo_inicial, {rejeitada: EstadoRevisao.REJEITADA})

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert _contagens(ficha) == esperado


def test_proposta_ausente_nao_vira_campo(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE", atributos={"identificador_operacional": "P1"})
    cena.elemento(POSTE, codigo="POSTE", x=0.6, atributos={"identificador_operacional": "P2"})

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert len(ficha["postes"]) == 2
    assert all(poste["estruturas"] == [] for poste in ficha["postes"])
    assert ficha["vaos"] == []
    assert "cabos_sem_vao" not in ficha["atributos_extras"]
    assert "estruturas_sem_poste" not in ficha["atributos_extras"]


def test_ponto_de_entrega_nao_vira_poste(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(POSTE, codigo="POSTE", atributos={"identificador_operacional": "P1"})
    entrega = cena.elemento(POSTE, codigo="POSTE", x=0.6, atributos={"tipo_ponto_rede": "ENTREGA"})
    cabo = cena.elemento(CABO, codigo="ABC")
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, entrega, "CONECTA")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert [poste["id"] for poste in ficha["postes"]] == [str(p1.id)]
    assert ficha["vaos"] == []
    assert ficha["atributos_extras"]["postes_entrega"] == 1
    assert ficha["atributos_extras"]["cabos_sem_vao"] == 1


@pytest.mark.parametrize("alvo", ["poste", "estrutura", "equipamento", "cabo"])
@pytest.mark.parametrize("motivo", ["conflitante", "chave"])
def test_proposta_pendente_vai_para_pendentes(
    catalogo_inicial: CatalogoTecnico, alvo: str, motivo: str
) -> None:
    cena, elementos = _cena_completa(catalogo_inicial)
    original = elementos["p1" if alvo == "poste" else alvo]
    if motivo == "conflitante":
        pendente = replace(original, estado_revisao=EstadoRevisao.CONFLITANTE)
    else:
        pendente = replace(
            original,
            atributos_sugeridos=(*original.atributos_sugeridos, ("comprimento_pendente", True)),
        )
    cena.elementos[cena.elementos.index(original)] = pendente

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    p1, p2 = ficha["postes"]
    (vao,) = ficha["vaos"]
    if alvo == "poste":
        assert (p1["identificador"], p1["poste"]) == ("P1", "POSTE")
        assert p1["coordenada"] == {"leste": 100.5, "norte": 200.25, "zona": None}
        assert p1["pendentes"] == ["coordenada", "identificador", "poste"]
        assert p2["pendentes"] == []
        assert vao["pendentes"] == []
    elif alvo == "estrutura":
        assert p1["estruturas"] == ["N3"]
        assert p1["pendentes"] == ["estruturas"]
        assert p2["pendentes"] == []
    elif alvo == "equipamento":
        assert [s["classe"] for s in p2["simbolos"]] == ["ESTAI"]
        assert p2["pendentes"] == ["simbolos"]
        assert p1["pendentes"] == []
    else:
        assert (vao["cabo"], vao["comprimento_m"]) == ("ABC", 35.0)
        assert vao["pendentes"] == ["cabo", "comprimento_m"]
        assert p1["pendentes"] == p2["pendentes"] == []


@pytest.mark.parametrize(
    ("destinos", "vaos", "cabos_sem_vao"),
    [
        pytest.param(("p1", "p2", "equipamento"), 1, 0, id="dois-postes-e-um-equipamento"),
        pytest.param(("p1",), 0, 1, id="um-poste-so"),
        pytest.param(("p1", "p1"), 0, 1, id="duas-conecta-ao-mesmo-poste"),
        pytest.param(("equipamento",), 0, 1, id="so-equipamento"),
    ],
)
def test_vao_so_conta_conecta_a_poste(
    catalogo_inicial: CatalogoTecnico, destinos: tuple[str, ...], vaos: int, cabos_sem_vao: int
) -> None:
    cena = _Cena(catalogo_inicial)
    alvos = {
        "p1": cena.elemento(POSTE, codigo="POSTE", atributos={"identificador_operacional": "P1"}),
        "p2": cena.elemento(
            POSTE, codigo="POSTE", x=0.6, atributos={"identificador_operacional": "P2"}
        ),
        "equipamento": cena.elemento(EQUIPAMENTO, x=0.4),
    }
    cabo = cena.elemento(CABO, codigo="ABC")
    for destino in destinos:
        cena.relacao(cabo, alvos[destino], "CONECTA")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert len(ficha["vaos"]) == vaos
    assert ficha["atributos_extras"].get("cabos_sem_vao", 0) == cabos_sem_vao


def test_vao_segue_a_ordem_dos_ids_das_relacoes(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(POSTE, codigo="POSTE")
    p2 = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    cabo = cena.elemento(CABO, codigo="ABC")
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, p2, "CONECTA")
    ordenadas = sorted(cena.relacoes, key=lambda item: str(item.id))

    (vao,) = cena.ficha()["vaos"]

    assert (vao["de"], vao["para"]) == tuple(str(item.destino_referencia_id) for item in ordenadas)


def test_estrutura_sem_poste_da_ficha_e_contada(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE")
    cena.elemento(ESTRUTURA_MT, codigo="N3")  # sem relação: conta
    sem_codigo = cena.elemento(ESTRUTURA_MT, x=0.5)  # ignorada, mesmo ligada ao poste
    cena.relacao(sem_codigo, cena.elementos[0], "INSTALADA_EM")

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["atributos_extras"]["estruturas_sem_poste"] == 1
    assert ficha["postes"][0]["estruturas"] == []


def test_estruturas_do_poste_saem_ordenadas(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    poste = cena.elemento(POSTE, codigo="POSTE")
    for codigo in ("N3", "CE1", "N1"):
        cena.relacao(cena.elemento(ESTRUTURA_MT, codigo=codigo), poste, "INSTALADA_EM")

    assert cena.ficha()["postes"][0]["estruturas"] == ["CE1", "N1", "N3"]


def test_comprimento_por_coordenadas(catalogo_inicial: CatalogoTecnico) -> None:
    def cena_com_cabo_sem_comprimento(estado_p2: EstadoRevisao) -> dict[str, Any]:
        cena = _Cena(catalogo_inicial)
        p1 = cena.elemento(
            POSTE, codigo="POSTE", atributos={"coordenada_leste": 0, "coordenada_norte": 0}
        )
        p2 = cena.elemento(
            POSTE,
            codigo="POSTE",
            x=0.6,
            estado=estado_p2,
            atributos={"coordenada_leste": 3, "coordenada_norte": 4},
        )
        cabo = cena.elemento(CABO, codigo="ABC")
        cena.relacao(cabo, p1, "CONECTA")
        cena.relacao(cabo, p2, "CONECTA")
        return cena.ficha()

    (vao,) = cena_com_cabo_sem_comprimento(EstadoRevisao.PROPOSTA)["vaos"]
    assert vao["comprimento_m"] == 5.0
    assert vao["atributos_extras"] == {"origem_comprimento": "COORDENADAS"}
    assert vao["pendentes"] == []

    ficha = cena_com_cabo_sem_comprimento(EstadoRevisao.CONFLITANTE)
    (pendente,) = ficha["vaos"]
    assert pendente["comprimento_m"] == 5.0
    assert "comprimento_m" in pendente["pendentes"]
    assert validar_ficha(ficha) == []


def test_comprimento_sem_anotacao_nem_coordenadas_e_nulo(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    p1 = cena.elemento(POSTE, codigo="POSTE")
    p2 = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    cabo = cena.elemento(CABO, codigo="ABC", atributos={"comprimento_m": 0})
    cena.relacao(cabo, p1, "CONECTA")
    cena.relacao(cabo, p2, "CONECTA")

    (vao,) = cena.ficha()["vaos"]

    assert vao["comprimento_m"] is None
    assert vao["atributos_extras"] == {"origem_comprimento": None}


def test_poste_de_simbolo_nao_grava_classe_como_poste(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE_AT", atributos={"origem_simbolo_ocorrencia_id": "oc-1"})

    (poste,) = cena.ficha()["postes"]

    assert poste["poste"] is None
    assert poste["atributos_extras"] == {"origem": "simbolo", "classe_simbolo": "POSTE_AT"}


def test_equipamento_sem_classe_sem_area_ou_fora_do_inventario_e_contado(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    cena = _Cena(catalogo_inicial)
    poste = cena.elemento(POSTE, codigo="POSTE")
    casos = [
        ({}, False),  # sem classe
        ({"simbolo_classe": "CLASSE_INEXISTENTE"}, False),
        ({"simbolo_classe": "POSTE"}, False),  # classe do próprio poste
        ({"simbolo_classe": "ESTAI"}, True),  # geometria de ponto: sem área
        ({"simbolo_classe": "ESTAI"}, False),  # o único que vira símbolo
    ]
    for atributos, como_ponto in casos:
        equipamento = cena.elemento(EQUIPAMENTO, atributos=atributos, como_ponto=como_ponto)
        cena.relacao(equipamento, poste, "INSTALADO_EM")
    cena.elemento(EQUIPAMENTO, atributos={"simbolo_classe": "ESTAI"})  # sem relação

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert len(ficha["postes"][0]["simbolos"]) == 1
    assert ficha["atributos_extras"] == {
        "equipamentos_sem_simbolo": 1,
        "simbolos_fora_do_inventario": 2,
        "simbolos_sem_area": 1,
        "simbolos_de_poste_fora_da_ficha": 1,
    }


def test_proposta_duplicada_nao_repete_ids(catalogo_inicial: CatalogoTecnico) -> None:
    cena, _ = _cena_completa(catalogo_inicial)
    cena.elementos.extend(cena.elementos)
    cena.relacoes.extend(cena.relacoes)

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert _contagens(ficha) == (2, 1, 1, 1)


def test_chaves_de_pendencia_iguais_as_da_promocao() -> None:
    fonte = RAIZ / "src" / "zeny_project_handler" / "application" / "automatic_promotion.py"
    arvore = ast.parse(fonte.read_text(encoding="utf-8"))
    tuplas = [
        tuple(elemento.value for elemento in no.value.elts if isinstance(elemento, ast.Constant))
        for no in ast.walk(arvore)
        if isinstance(no, ast.Assign)
        and isinstance(no.value, ast.Tuple)
        and any(isinstance(alvo, ast.Name) and alvo.id == "pending_keys" for alvo in no.targets)
    ]

    assert len(tuplas) == 1
    assert tuplas[0] == CHAVES_PENDENCIA


def test_metricas_nas_duas_fontes(catalogo_inicial: CatalogoTecnico) -> None:
    referencia = _referencia_sintetica(SHA_QUALQUER)
    cena = _Cena(catalogo_inicial)
    propostos = []
    for ref in referencia["postes"]:
        x0, y0, x1, _ = ref["bbox"]
        proposta = cena.elemento(
            POSTE,
            codigo="POSTE",
            x=x0,
            y=y0,
            lado=x1 - x0,
            atributos={"identificador_operacional": ref["identificador"]},
        )
        propostos.append(proposta)
    cabo = cena.elemento(CABO, codigo="ABC-4 CA", atributos={"comprimento_m": 35})
    for proposta in propostos:
        cena.relacao(cabo, proposta, "CONECTA")
    variante = cena.variante()

    do_projeto = avaliar(referencia, ficha_predita(variante, SHA_QUALQUER, native_only=True))
    das_propostas = avaliar(
        referencia, ficha_predita_propostas(variante, SHA_QUALQUER, native_only=True)
    )

    assert do_projeto["postes"]["tp"] == 0
    assert das_propostas["postes"]["tp"] == 2
    assert das_propostas["postes"]["fp"] == 0


def _executar_cli(tmp_path: Path, extras: list[str]) -> Path:
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-sintetico")
    referencia = tmp_path / "ref.json"
    referencia.write_text(
        json.dumps(_referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())), encoding="utf-8"
    )
    saida = tmp_path / "saida"
    argumentos = [
        str(pdf),
        "--referencia",
        str(referencia),
        "--saida",
        str(saida),
        "--native-only",
        *extras,
    ]
    assert main(argumentos) == 0
    return saida


def test_executar_recusa_versao_desconhecida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falha(*_: Any, **__: Any) -> dict[str, Any]:
        raise AssertionError("o analisador não deveria rodar")

    monkeypatch.setattr(benchmark_ficha_poste, "run_variant", falha)
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-sintetico")
    referencia = tmp_path / "ref.json"
    referencia.write_text(
        json.dumps(_referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="versao_extracao desconhecida: propostas-v9"):
        executar(
            pdf,
            referencia,
            tmp_path / "saida",
            native_only=True,
            runtime_directory=tmp_path / "runtime",
            versao_extracao="propostas-v9",
        )

    assert not (tmp_path / "saida").exists()


def test_cli_aceita_versao_extracao(
    catalogo_inicial: CatalogoTecnico, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cena, _ = _cena_completa(catalogo_inicial)
    monkeypatch.setattr(benchmark_ficha_poste, "run_variant", lambda *_, **__: cena.variante())

    saida = _executar_cli(tmp_path, ["--versao-extracao", "propostas-v1"])

    ficha = json.loads((saida / "ficha-predita.json").read_text(encoding="utf-8"))
    assert ficha["gerador"]["versao_extracao"] == "propostas-v1"
    assert len(ficha["postes"]) == 2


def test_cli_sem_flag_mantem_o_projeto_promovido(
    catalogo_inicial: CatalogoTecnico, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cena, _ = _cena_completa(catalogo_inicial)
    monkeypatch.setattr(benchmark_ficha_poste, "run_variant", lambda *_, **__: cena.variante())

    saida = _executar_cli(tmp_path, [])

    ficha = json.loads((saida / "ficha-predita.json").read_text(encoding="utf-8"))
    assert ficha["gerador"]["versao_extracao"] == "projeto-promovido-v1"
    assert ficha["postes"] == []


def test_poste_em_pagina_desconhecida_e_pulado_e_contado(catalogo_inicial: CatalogoTecnico) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(POSTE, codigo="POSTE")
    fora = cena.elemento(POSTE, codigo="POSTE", x=0.6)
    desconhecida = GeometriaDocumento.caixa(
        uuid4(),
        PontoNormalizado(Decimal("0.1"), Decimal("0.1")),
        PontoNormalizado(Decimal("0.2"), Decimal("0.2")),
    )
    cena.elementos[1] = replace(fora, geometria=desconhecida)

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert len(ficha["postes"]) == 1
    assert ficha["atributos_extras"]["postes_sem_pagina"] == 1


@pytest.mark.parametrize("valor", ["1e400", "nan", "abc", float("inf")])
def test_coordenada_nao_finita_vira_ausente(catalogo_inicial: CatalogoTecnico, valor: Any) -> None:
    cena = _Cena(catalogo_inicial)
    cena.elemento(
        POSTE, codigo="POSTE", atributos={"coordenada_leste": valor, "coordenada_norte": 1}
    )

    ficha = cena.ficha()

    assert validar_ficha(ficha) == []
    assert ficha["postes"][0]["coordenada"] is None
