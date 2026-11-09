"""Ancoragem do poste no disco do desenho e relações por regime da subclasse 26.0."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4, uuid5

import pytest
from tests.interpretation_factories import text_evidence

from zeny_project_handler.adapters.interpretation import carregar_registro_regras_inicial
from zeny_project_handler.adapters.interpretation.ancoragem_poste import (
    ancorar_postes_no_desenho,
)
from zeny_project_handler.adapters.interpretation.ficha_poste import InterpretadorFichaPoste
from zeny_project_handler.adapters.interpretation.rule_support import center
from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico, ExtraAttributes
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
    TipoGeometria,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao

EXECUCAO = UUID(int=1)
PAGINA = UUID(int=2)
OUTRA_PAGINA = UUID(int=3)
VERDE = "#007000"
ROXO = "#4F1A4D"


def _ponto(x: float, y: float) -> PontoNormalizado:
    return PontoNormalizado(Decimal(str(round(x, 6))), Decimal(str(round(y, 6))))


def _caixa(x: float, y: float, meia: float = 0.004, pagina: UUID = PAGINA) -> GeometriaDocumento:
    return GeometriaDocumento.caixa(
        pagina, _ponto(x - meia, y - meia / 2), _ponto(x + meia, y + meia / 2)
    )


def _disco(
    chave: str,
    x: float,
    y: float,
    *,
    cor: str = VERDE,
    diametro_pt: float = 1.7,
    razao: float = 1.0,
    operacoes: str = "c,c,c,c",
    conteudo: str | None = None,
    pagina: UUID = PAGINA,
) -> EvidenciaDocumento:
    meia_w = diametro_pt / 2
    meia_h = meia_w / razao
    curvas: list[list[object]] = [
        ["c", [-meia_w, 0], [-meia_w, 0], [0, -meia_h], [0, -meia_h]],
        ["c", [0, -meia_h], [meia_w, 0], [meia_w, 0], [meia_w, 0]],
        ["c", [meia_w, 0], [0, meia_h], [0, meia_h], [0, meia_h]],
        ["c", [0, meia_h], [-meia_w, 0], [-meia_w, 0], [-meia_w, 0]],
    ]
    return EvidenciaDocumento(
        id=uuid5(EXECUCAO, chave),
        execucao_id=EXECUCAO,
        pagina_id=pagina,
        tipo=TipoEvidencia.VETOR,
        geometria=GeometriaDocumento.caixa(
            pagina, _ponto(x - 0.001, y - 0.001), _ponto(x + 0.001, y + 0.001)
        ),
        metodo="fixture",
        versao_metodo="1",
        parametros=(),
        conteudo_bruto=json.dumps(curvas) if conteudo is None else conteudo,
        criada_em=datetime(2026, 7, 21, 12, tzinfo=UTC),
        atributos_extraidos=(
            ("operacoes", operacoes),
            ("cor_preenchimento", cor),
            ("tipo_caminho", "f"),
        ),
    )


def _poste(
    chave: str,
    identificador: str,
    x: float,
    y: float,
    *,
    codigo: str = "11-300",
    situacao: SituacaoProjeto = SituacaoProjeto.INSTALAR,
    confianca: str = "0.86",
    extras: ExtraAttributes = (),
    tipo_catalogo: UUID | None = None,
    pagina: UUID = PAGINA,
) -> PropostaElemento:
    return PropostaElemento(
        id=uuid5(EXECUCAO, f"prop:{chave}"),
        execucao_id=EXECUCAO,
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=situacao,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(uuid5(EXECUCAO, f"ev:{chave}"),),
        geometria=_caixa(x, y, pagina=pagina),
        tipo_catalogo_sugerido_id=tipo_catalogo,
        codigo_observado=codigo,
        atributos_sugeridos=(("identificador_operacional", identificador), *extras),
        confianca=Decimal(confianca),
    )


def _rotulo(chave: str, texto: str, x: float, y: float) -> EvidenciaDocumento:
    return replace(
        text_evidence(
            execution_id=EXECUCAO, page_id=PAGINA, key=chave, text=texto, x=str(x), y=str(y)
        ),
        geometria=_caixa(x, y),
    )


def _ligado_ao(rotulo: EvidenciaDocumento) -> ExtraAttributes:
    return (("evidencia_identificador_id", str(rotulo.id)),)


def _atributos(proposta: PropostaElemento) -> dict[str, Any]:
    return dict(proposta.atributos_sugeridos)


def _centro(proposta: PropostaElemento) -> tuple[float, float]:
    return center(proposta.geometria)


def _assert_nao_ancorado(original: PropostaElemento, resultado: PropostaElemento) -> None:
    assert resultado.geometria == original.geometria
    assert resultado.evidencia_ids == original.evidencia_ids
    assert _atributos(resultado)["poste_ancorado_disco"] is False
    assert "poste_texto_centro" not in _atributos(resultado)


def test_poste_ancora_numa_caixa_no_centro_do_par_e_guarda_o_texto() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    discos = (_disco("d1", 0.33, 0.30), _disco("d2", 0.34, 0.30))

    resultado = ancorar_postes_no_desenho((poste,), discos)

    assert len(resultado) == 1
    assert resultado[0].geometria.tipo is TipoGeometria.CAIXA
    assert _centro(resultado[0]) == pytest.approx((0.335, 0.30), abs=1e-6)
    atributos = _atributos(resultado[0])
    assert atributos["poste_ancorado_disco"] is True
    assert atributos["poste_texto_centro"] == "0.3,0.3"
    assert "associacao_pendente" not in atributos
    assert set(resultado[0].evidencia_ids) == {*poste.evidencia_ids, discos[0].id, discos[1].id}


def test_caixa_do_poste_ancorado_tem_o_lado_do_diametro() -> None:
    resultado = ancorar_postes_no_desenho(
        (_poste("a", "P1", 0.30, 0.30),), (_disco("d1", 0.33, 0.30),)
    )

    canto, oposto = resultado[0].geometria.pontos
    assert float(oposto.x - canto.x) == pytest.approx(0.002, abs=1e-6)
    assert float(oposto.y - canto.y) == pytest.approx(0.002, abs=1e-6)


@pytest.mark.parametrize(
    ("distancia", "centro_x"),
    [
        pytest.param(0.0125, 0.33625, id="dentro-de-0-013-e-par"),
        pytest.param(0.014, 0.33, id="fora-de-0-013-sao-dois-sitios"),
    ],
)
def test_limite_do_par_de_discos(distancia: float, centro_x: float) -> None:
    discos = (_disco("d1", 0.33, 0.30), _disco("d2", 0.33 + distancia, 0.30))

    resultado = ancorar_postes_no_desenho((_poste("a", "P1", 0.30, 0.30),), discos)

    assert _centro(resultado[0])[0] == pytest.approx(centro_x, abs=1e-6)


@pytest.mark.parametrize(
    ("cor", "distancia", "ancorado"),
    [
        pytest.param(VERDE, 0.135, True, id="verde-dentro-do-raio"),
        pytest.param(VERDE, 0.145, False, id="verde-fora-do-raio"),
        pytest.param(ROXO, 0.039, True, id="roxo-colado-ao-rotulo"),
        pytest.param(ROXO, 0.041, False, id="roxo-afastado-do-rotulo"),
    ],
)
def test_raio_de_atribuicao_por_cor(cor: str, distancia: float, ancorado: bool) -> None:
    poste = _poste("a", "P1", 0.30, 0.30)

    resultado = ancorar_postes_no_desenho(
        (poste,), (_disco("d1", 0.30 + distancia, 0.30, cor=cor),)
    )

    assert _atributos(resultado[0])["poste_ancorado_disco"] is ancorado


def test_poste_sem_disco_por_perto_mantem_posicao_e_nao_pende() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)

    resultado = ancorar_postes_no_desenho((poste,), (_disco("d1", 0.80, 0.80),))

    _assert_nao_ancorado(poste, resultado[0])
    assert "associacao_pendente" not in _atributos(resultado[0])


def test_folha_sem_disco_algum_nao_muda_as_propostas() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)

    assert ancorar_postes_no_desenho((poste,), ()) == (poste,)


def test_disco_de_outra_pagina_nao_ancora() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)

    assert ancorar_postes_no_desenho(
        (poste,), (_disco("d1", 0.33, 0.30, pagina=OUTRA_PAGINA),)
    ) == (poste,)


@pytest.mark.parametrize(
    "disco",
    [
        pytest.param(_disco("fora", 0.33, 0.30, cor="#123456"), id="fora-da-paleta"),
        pytest.param(_disco("grande", 0.33, 0.30, diametro_pt=7.5), id="grande"),
        pytest.param(_disco("miudo", 0.33, 0.30, diametro_pt=0.5), id="miudo"),
        pytest.param(_disco("oval", 0.33, 0.30, razao=1.4), id="nao-redondo"),
        pytest.param(_disco("linha", 0.33, 0.30, operacoes="l,l,l"), id="nao-e-curva"),
        pytest.param(_disco("json", 0.33, 0.30, conteudo="{"), id="conteudo-invalido"),
        pytest.param(
            _disco("ponto-invalido", 0.33, 0.30, conteudo='[["c",["a","b"]]]'),
            id="ponto-nao-numerico",
        ),
        pytest.param(
            _disco("ponto-nulo", 0.33, 0.30, conteudo='[["c",[null,null]]]'),
            id="ponto-nulo",
        ),
    ],
)
def test_disco_que_nao_e_de_poste_nao_ancora(disco: EvidenciaDocumento) -> None:
    poste = _poste("a", "P1", 0.30, 0.30)

    assert ancorar_postes_no_desenho((poste,), (disco,)) == (poste,)


@pytest.mark.parametrize("texto", ["11-300", "P1"])
def test_disco_de_glifo_dentro_do_rotulo_nao_ancora(texto: str) -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    rotulo = replace(
        _rotulo("rot", texto, 0.33, 0.30),
        geometria=GeometriaDocumento.caixa(PAGINA, _ponto(0.325, 0.296), _ponto(0.34, 0.304)),
    )
    glifo = _disco("glifo", 0.335, 0.30)

    assert ancorar_postes_no_desenho((poste,), (rotulo, glifo)) == (poste,)


def test_disco_dentro_de_texto_que_nao_e_rotulo_de_poste_continua_candidato() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    texto = replace(
        _rotulo("obs", "OBSERVACAO", 0.33, 0.30),
        geometria=GeometriaDocumento.caixa(PAGINA, _ponto(0.325, 0.296), _ponto(0.34, 0.304)),
    )

    resultado = ancorar_postes_no_desenho((poste,), (texto, _disco("d1", 0.335, 0.30)))

    assert _atributos(resultado[0])["poste_ancorado_disco"] is True


def test_rotulo_p_e_a_origem_da_atribuicao_quando_conhecido() -> None:
    rotulo = _rotulo("rot-p", "P1", 0.60, 0.30)
    poste = _poste("a", "P1", 0.30, 0.30, extras=_ligado_ao(rotulo))
    # O disco perto do texto da nomenclatura é de outro poste; o do P é o da direita.
    discos = (_disco("d1", 0.32, 0.30), _disco("d2", 0.63, 0.30))

    resultado = ancorar_postes_no_desenho((poste,), (rotulo, *discos))

    assert _centro(resultado[0]) == pytest.approx((0.63, 0.30), abs=1e-6)


@pytest.mark.parametrize("referencia", ["nao-e-uuid", str(UUID(int=99))])
def test_rotulo_p_desconhecido_cai_no_centro_da_proposta(referencia: str) -> None:
    poste = _poste("a", "P1", 0.30, 0.30, extras=(("evidencia_identificador_id", referencia),))

    resultado = ancorar_postes_no_desenho((poste,), (_disco("d1", 0.32, 0.30),))

    assert _centro(resultado[0]) == pytest.approx((0.32, 0.30), abs=1e-6)


def test_dois_postes_vizinhos_ficam_cada_um_no_seu_disco() -> None:
    primeiro = _poste("a", "P1", 0.30, 0.30)
    segundo = _poste("b", "P2", 0.36, 0.30)
    discos = (_disco("d1", 0.31, 0.32), _disco("d2", 0.37, 0.33))

    resultado = {
        _atributos(item)["identificador_operacional"]: item
        for item in ancorar_postes_no_desenho((primeiro, segundo), discos)
    }

    assert _centro(resultado["P1"]) == pytest.approx((0.31, 0.32), abs=1e-6)
    assert _centro(resultado["P2"]) == pytest.approx((0.37, 0.33), abs=1e-6)


def test_rotulos_entre_dois_discos_associam_cada_p_ao_seu_e_nao_ao_da_nomenclatura() -> None:
    # Rótulos juntos no meio; a nomenclatura de cada poste cai perto do disco do vizinho.
    rotulo_1 = _rotulo("r1", "P1", 0.335, 0.30)
    rotulo_2 = _rotulo("r2", "P2", 0.365, 0.30)
    primeiro = _poste("a", "P1", 0.385, 0.33, extras=_ligado_ao(rotulo_1))
    segundo = _poste("b", "P2", 0.315, 0.33, extras=_ligado_ao(rotulo_2))
    discos = (_disco("d1", 0.31, 0.30), _disco("d2", 0.39, 0.30))

    resultado = {
        _atributos(item)["identificador_operacional"]: item
        for item in ancorar_postes_no_desenho((primeiro, segundo), (rotulo_1, rotulo_2, *discos))
    }

    assert _centro(resultado["P1"]) == pytest.approx((0.31, 0.30), abs=1e-6)
    assert _centro(resultado["P2"]) == pytest.approx((0.39, 0.30), abs=1e-6)


def test_disputa_real_de_um_sitio_fica_na_posicao_do_texto_e_pendente() -> None:
    primeiro = _poste("a", "P1", 0.30, 0.30)
    segundo = _poste("b", "P2", 0.34, 0.30)

    resultado = ancorar_postes_no_desenho((primeiro, segundo), (_disco("d1", 0.32, 0.30),))

    for original, item in zip((primeiro, segundo), resultado, strict=True):
        _assert_nao_ancorado(original, item)
        assert _atributos(item)["associacao_pendente"] == "poste_disco"


def test_rotulo_entre_dois_sitios_empatados_fica_pendente() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    discos = (_disco("d1", 0.26, 0.30), _disco("d2", 0.342, 0.30))

    resultado = ancorar_postes_no_desenho((poste,), discos)

    _assert_nao_ancorado(poste, resultado[0])
    assert _atributos(resultado[0])["associacao_pendente"] == "poste_disco"


def test_pendencia_preexistente_nao_e_sobrescrita() -> None:
    poste = _poste("a", "P1", 0.30, 0.30, extras=(("associacao_pendente", "outra_causa"),))
    discos = (_disco("d1", 0.26, 0.30), _disco("d2", 0.342, 0.30))

    resultado = ancorar_postes_no_desenho((poste,), discos)

    assert _atributos(resultado[0])["associacao_pendente"] == "outra_causa"


def test_empate_de_sitios_no_rotulo_p_fica_pendente_com_a_nomenclatura_junto_de_um() -> None:
    rotulo = _rotulo("rot-p", "P1", 0.30, 0.30)
    poste = _poste("a", "P1", 0.33, 0.30, extras=_ligado_ao(rotulo))
    discos = (_disco("d1", 0.27, 0.30), _disco("d2", 0.331, 0.30))

    resultado = ancorar_postes_no_desenho((poste,), (rotulo, *discos))

    _assert_nao_ancorado(poste, resultado[0])
    assert _atributos(resultado[0])["associacao_pendente"] == "poste_disco"


def test_empate_no_rotulo_deixa_pendente_o_outro_p_do_sitio_disputado() -> None:
    rotulo_1 = _rotulo("r1", "P1", 0.30, 0.30)
    rotulo_2 = _rotulo("r2", "P2", 0.362, 0.30)
    primeiro = _poste("a", "P1", 0.33, 0.30, extras=_ligado_ao(rotulo_1))
    segundo = _poste("b", "P2", 0.40, 0.30, extras=_ligado_ao(rotulo_2))
    discos = (_disco("d1", 0.27, 0.30), _disco("d2", 0.331, 0.30))

    resultado = ancorar_postes_no_desenho((primeiro, segundo), (rotulo_1, rotulo_2, *discos))

    for original, item in zip((primeiro, segundo), resultado, strict=True):
        _assert_nao_ancorado(original, item)
        assert _atributos(item)["associacao_pendente"] == "poste_disco"


def test_poste_com_o_sitio_mais_proximo_tomado_nao_migra_e_fica_pendente() -> None:
    primeiro = _poste("a", "P1", 0.335, 0.30)
    segundo = _poste("b", "P2", 0.365, 0.30)
    discos = (_disco("d1", 0.30, 0.30), _disco("d2", 0.345, 0.30))

    resultado = {item.id: item for item in ancorar_postes_no_desenho((primeiro, segundo), discos)}

    assert _centro(resultado[primeiro.id]) == pytest.approx((0.345, 0.30), abs=1e-6)
    assert "associacao_pendente" not in _atributos(resultado[primeiro.id])
    _assert_nao_ancorado(segundo, resultado[segundo.id])
    assert _atributos(resultado[segundo.id])["associacao_pendente"] == "poste_disco"


def test_poste_com_o_proximo_tomado_e_o_seguinte_bloqueado_fica_pendente() -> None:
    # P0 toma T; o sítio seguinte de P2 está bloqueado pela ambiguidade de P1; S3 é de outro poste.
    ambiguo = _poste("a", "P1", 0.50, 0.30)
    dono = _poste("b", "P0", 0.60, 0.30)
    vizinho = _poste("c", "P2", 0.585, 0.30)
    discos = (
        _disco("s1", 0.48, 0.30),
        _disco("s2", 0.523, 0.30),
        _disco("t", 0.601, 0.30),
        _disco("s3", 0.70, 0.30),
    )

    resultado = {
        item.id: item for item in ancorar_postes_no_desenho((ambiguo, dono, vizinho), discos)
    }

    assert _centro(resultado[dono.id]) == pytest.approx((0.601, 0.30), abs=1e-6)
    _assert_nao_ancorado(vizinho, resultado[vizinho.id])
    assert _atributos(resultado[vizinho.id])["associacao_pendente"] == "poste_disco"


def _p1_ambiguo_bloqueando_s1_e_s2() -> tuple[PropostaElemento, tuple[EvidenciaDocumento, ...]]:
    return (
        _poste("a", "P1", 0.50, 0.30),
        (_disco("s1", 0.48, 0.30), _disco("s2", 0.523, 0.30)),
    )


def test_sitio_bloqueado_dentro_da_margem_mantem_a_ambiguidade_do_proprio_p() -> None:
    ambiguo, discos = _p1_ambiguo_bloqueando_s1_e_s2()
    vizinho = _poste("b", "P2", 0.553, 0.30)

    resultado = {
        item.id: item
        for item in ancorar_postes_no_desenho(
            (ambiguo, vizinho), (*discos, _disco("snovo", 0.582, 0.30))
        )
    }

    _assert_nao_ancorado(ambiguo, resultado[ambiguo.id])
    assert _atributos(resultado[ambiguo.id])["associacao_pendente"] == "poste_disco"
    _assert_nao_ancorado(vizinho, resultado[vizinho.id])
    assert _atributos(resultado[vizinho.id])["associacao_pendente"] == "poste_disco"


def test_nomenclatura_junto_de_sitio_bloqueado_nao_ancora() -> None:
    ambiguo, discos = _p1_ambiguo_bloqueando_s1_e_s2()
    rotulo = _rotulo("r2", "P2", 0.553, 0.30)
    vizinho = _poste("b", "P2", 0.523, 0.33, extras=_ligado_ao(rotulo))

    resultado = {
        item.id: item
        for item in ancorar_postes_no_desenho(
            (ambiguo, vizinho), (rotulo, *discos, _disco("snovo", 0.582, 0.30))
        )
    }

    _assert_nao_ancorado(vizinho, resultado[vizinho.id])
    assert _atributos(resultado[vizinho.id])["associacao_pendente"] == "poste_disco"


def test_nomenclatura_junto_de_sitio_livre_nao_resolve_o_empate() -> None:
    ambiguo, discos = _p1_ambiguo_bloqueando_s1_e_s2()
    rotulo = _rotulo("r2", "P2", 0.553, 0.30)
    vizinho = _poste("b", "P2", 0.582, 0.33, extras=_ligado_ao(rotulo))

    resultado = {
        item.id: item
        for item in ancorar_postes_no_desenho(
            (ambiguo, vizinho), (rotulo, *discos, _disco("snovo", 0.582, 0.30))
        )
    }

    _assert_nao_ancorado(vizinho, resultado[vizinho.id])
    assert _atributos(resultado[vizinho.id])["associacao_pendente"] == "poste_disco"


def _sitios_gravados(proposta: PropostaElemento) -> set[str]:
    return set(str(_atributos(proposta)["poste_disco_sitios"]).split(";"))


def test_postes_que_disputam_um_sitio_gravam_esse_sitio() -> None:
    primeiro = _poste("a", "P1", 0.30, 0.30)
    segundo = _poste("b", "P2", 0.34, 0.30)

    resultado = ancorar_postes_no_desenho((primeiro, segundo), (_disco("d1", 0.32, 0.30),))

    assert [_sitios_gravados(item) for item in resultado] == [{"0.32,0.3"}, {"0.32,0.3"}]


def test_p_empatado_entre_dois_sitios_grava_os_dois() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    discos = (_disco("d1", 0.26, 0.30), _disco("d2", 0.342, 0.30))

    resultado = ancorar_postes_no_desenho((poste,), discos)

    assert _sitios_gravados(resultado[0]) == {"0.26,0.3", "0.342,0.3"}


def test_p_barrado_por_sitio_bloqueado_grava_so_esse_sitio() -> None:
    ambiguo, discos = _p1_ambiguo_bloqueando_s1_e_s2()
    vizinho = _poste("b", "P2", 0.55, 0.30)

    resultado = {item.id: item for item in ancorar_postes_no_desenho((ambiguo, vizinho), discos)}

    assert _atributos(resultado[vizinho.id])["associacao_pendente"] == "poste_disco"
    assert _sitios_gravados(resultado[vizinho.id]) == {"0.523,0.3"}


def test_p_pendente_por_sitio_tomado_nao_registra_sitio() -> None:
    primeiro = _poste("a", "P1", 0.335, 0.30)
    segundo = _poste("b", "P2", 0.365, 0.30)
    discos = (_disco("d1", 0.30, 0.30), _disco("d2", 0.345, 0.30))

    resultado = {item.id: item for item in ancorar_postes_no_desenho((primeiro, segundo), discos)}

    assert _atributos(resultado[segundo.id])["associacao_pendente"] == "poste_disco"
    assert "poste_disco_sitios" not in _atributos(resultado[segundo.id])


def test_poste_que_nao_e_disputado_nao_registra_sitio() -> None:
    ancorado = _poste("a", "P1", 0.30, 0.30)
    sem_disco = _poste("b", "P2", 0.80, 0.80)

    resultado = {
        item.id: item
        for item in ancorar_postes_no_desenho((ancorado, sem_disco), (_disco("d1", 0.33, 0.30),))
    }

    assert "poste_disco_sitios" not in _atributos(resultado[ancorado.id])
    assert "poste_disco_sitios" not in _atributos(resultado[sem_disco.id])


def test_pilha_instalar_e_remover_de_mesmo_codigo_preserva_a_outra_leitura() -> None:
    nova = _poste("nova", "P1", 0.30, 0.30)
    retirada = _poste("velha", "P1", 0.30, 0.306, situacao=SituacaoProjeto.REMOVER)

    resultado = ancorar_postes_no_desenho((nova, retirada), (_disco("d1", 0.33, 0.30),))

    assert [item.id for item in resultado] == [nova.id]
    assert resultado[0].estado_revisao is EstadoRevisao.PROPOSTA
    assert _atributos(resultado[0])["poste_codigo_alternativo"] == "11-300"


def test_pilha_de_leituras_com_situacao_decide_pela_que_nao_e_retirada() -> None:
    nova = _poste("nova", "P1", 0.30, 0.30)
    retirada = _poste("velha", "P1", 0.30, 0.306, codigo="10-150", situacao=SituacaoProjeto.REMOVER)
    disco = _disco("d1", 0.33, 0.30)

    resultado = ancorar_postes_no_desenho((nova, retirada), (disco,))

    assert len(resultado) == 1
    assert resultado[0].id == nova.id
    assert resultado[0].codigo_observado == "11-300"
    assert resultado[0].estado_revisao is EstadoRevisao.PROPOSTA
    atributos = _atributos(resultado[0])
    assert atributos["poste_codigo_alternativo"] == "10-150"
    assert "associacao_pendente" not in atributos
    assert "classificacao_pendente" not in atributos
    assert set(resultado[0].evidencia_ids) == {
        *nova.evidencia_ids,
        *retirada.evidencia_ids,
        disco.id,
    }


def test_pilha_sem_sinal_fica_na_leitura_mais_confiavel_e_conflitante() -> None:
    tipo = uuid4()
    forte = _poste("forte", "P1", 0.30, 0.30, confianca="0.90", tipo_catalogo=tipo)
    fraca = _poste("fraca", "P1", 0.30, 0.306, codigo="12-300", confianca="0.86")

    resultado = ancorar_postes_no_desenho((forte, fraca), (_disco("d1", 0.33, 0.30),))

    assert len(resultado) == 1
    item = resultado[0]
    assert item.id == forte.id
    assert item.estado_revisao is EstadoRevisao.CONFLITANTE
    assert item.tipo_catalogo_sugerido_id is None
    atributos = _atributos(item)
    assert atributos["classificacao_pendente"] is True
    assert atributos["poste_codigo_alternativo"] == "12-300"
    assert "associacao_pendente" not in atributos


def test_empate_de_confianca_na_pilha_sem_sinal_fica_no_menor_id() -> None:
    primeira = _poste("x", "P1", 0.30, 0.30, codigo="10-300")
    segunda = _poste("y", "P1", 0.30, 0.306, codigo="12-300")
    menor = min(primeira.id, segunda.id, key=str)

    resultado = ancorar_postes_no_desenho((primeira, segunda), (_disco("d1", 0.33, 0.30),))

    assert [item.id for item in resultado] == [menor]


def test_proximidade_ao_disco_nao_resolve_a_pilha_sem_sinal() -> None:
    forte = _poste("forte", "P1", 0.30, 0.30, confianca="0.90")
    fraca = _poste("fraca", "P1", 0.30, 0.318, codigo="12-300", confianca="0.86")
    disco = _disco("d1", 0.30, 0.33)

    resultado = ancorar_postes_no_desenho((forte, fraca), (disco,))

    assert len(resultado) == 1
    assert resultado[0].id == forte.id
    assert resultado[0].estado_revisao is EstadoRevisao.CONFLITANTE
    assert _atributos(resultado[0])["poste_codigo_alternativo"] == "12-300"


def test_leituras_concordantes_no_mesmo_disco_viram_uma_sem_conflito() -> None:
    tipo = uuid4()
    forte = _poste("forte", "P1", 0.30, 0.30, confianca="0.90", tipo_catalogo=tipo)
    fraca = _poste("fraca", "P1", 0.30, 0.306, confianca="0.86")

    resultado = ancorar_postes_no_desenho((forte, fraca), (_disco("d1", 0.33, 0.30),))

    assert len(resultado) == 1
    assert resultado[0].id == forte.id
    assert resultado[0].estado_revisao is EstadoRevisao.PROPOSTA
    assert resultado[0].tipo_catalogo_sugerido_id == tipo
    assert "poste_codigo_alternativo" not in _atributos(resultado[0])
    assert "classificacao_pendente" not in _atributos(resultado[0])


def test_leitura_a_retirar_mais_confiavel_nao_fica_no_disco_de_pilha_sem_sinal() -> None:
    retirada = _poste(
        "velha", "P1", 0.30, 0.303, codigo="9-150", situacao=SituacaoProjeto.REMOVER, confianca="1"
    )
    forte = _poste("forte", "P1", 0.30, 0.30, codigo="10-300", confianca="0.90")
    fraca = _poste("fraca", "P1", 0.30, 0.306, codigo="12-300", confianca="0.86")

    resultado = ancorar_postes_no_desenho((retirada, forte, fraca), (_disco("d1", 0.33, 0.30),))

    assert [item.id for item in resultado] == [forte.id]
    assert resultado[0].estado_revisao is EstadoRevisao.CONFLITANTE
    assert _atributos(resultado[0])["poste_codigo_alternativo"] == "12-300,9-150"


def test_mesmo_p_em_discos_diferentes_fica_em_duas_propostas_pendentes() -> None:
    primeiro = _poste("a", "P3", 0.30, 0.30)
    segundo = _poste("b", "P3", 0.50, 0.30)
    discos = (_disco("d1", 0.33, 0.30), _disco("d2", 0.53, 0.30))

    resultado = ancorar_postes_no_desenho((primeiro, segundo), discos)

    assert len(resultado) == 2
    assert {_atributos(item)["associacao_pendente"] for item in resultado} == {
        "poste_mesmo_identificador"
    }
    assert all(_atributos(item)["poste_ancorado_disco"] is True for item in resultado)


def test_leitura_distante_do_mesmo_rotulo_mantem_posicao_e_vinculos() -> None:
    rotulo = _rotulo("rot-p", "P1", 0.30, 0.30)
    perto = _poste("perto", "P1", 0.32, 0.30, extras=_ligado_ao(rotulo))
    longe = _poste(
        "longe",
        "P1",
        0.42,
        0.30,
        codigo="10-300",
        situacao=SituacaoProjeto.EXISTENTE,
        extras=_ligado_ao(rotulo),
    )

    resultado = {
        item.id: item
        for item in ancorar_postes_no_desenho((perto, longe), (rotulo, _disco("d1", 0.31, 0.32)))
    }

    assert len(resultado) == 2
    assert _atributos(resultado[perto.id])["poste_ancorado_disco"] is True
    _assert_nao_ancorado(longe, resultado[longe.id])
    assert "associacao_pendente" not in _atributos(resultado[longe.id])


def _postes_em_grade(quantidade: int) -> tuple[PropostaElemento, ...]:
    return tuple(
        _poste(
            f"p{indice}",
            f"P{indice}",
            0.05 + (indice % 20) * 0.045,
            0.05 + (indice // 20) * 0.045,
        )
        for indice in range(quantidade)
    )


def _discos_nos_postes(postes: tuple[PropostaElemento, ...]) -> tuple[EvidenciaDocumento, ...]:
    return tuple(
        _disco(f"d{indice}", _centro(poste)[0] + 0.004, _centro(poste)[1])
        for indice, poste in enumerate(postes)
    )


def test_pagina_densa_dentro_do_teto_ancora_cada_poste_no_seu_disco() -> None:
    postes = _postes_em_grade(400)

    resultado = ancorar_postes_no_desenho(postes, _discos_nos_postes(postes))

    assert all(_atributos(item)["poste_ancorado_disco"] is True for item in resultado)
    for original, item in zip(postes, resultado, strict=True):
        assert _centro(item)[0] == pytest.approx(_centro(original)[0] + 0.004, abs=1e-6)


def test_pagina_hostil_com_discos_acima_do_teto_nao_ancora_nem_pende() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    discos = tuple(_disco(f"d{indice}", 0.31, 0.30) for indice in range(2_001))

    assert ancorar_postes_no_desenho((poste,), discos) == (poste,)


def test_pagina_hostil_com_rotulos_acima_do_teto_nao_ancora_nem_pende() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    rotulos = tuple(_rotulo(f"r{indice}", "P9", 0.70, 0.70) for indice in range(2_001))

    assert ancorar_postes_no_desenho((poste,), (*rotulos, _disco("d1", 0.31, 0.30))) == (poste,)


def test_pagina_hostil_com_postes_acima_do_teto_nao_ancora_nem_pende() -> None:
    postes = tuple(
        _poste(f"p{indice}", f"P{indice}", 0.30, 0.30 + indice * 0.001) for indice in range(501)
    )

    assert ancorar_postes_no_desenho(postes, (_disco("d1", 0.31, 0.40),)) == postes


def test_pagina_hostil_com_leituras_acima_do_teto_nao_ancora_nem_pende() -> None:
    leituras = tuple(_poste(f"p{indice}", "P1", 0.30, 0.30) for indice in range(1_001))

    assert ancorar_postes_no_desenho(leituras, (_disco("d1", 0.31, 0.30),)) == leituras


def test_teto_de_leituras_ainda_ancora_no_limite() -> None:
    leituras = tuple(_poste(f"p{indice}", "P1", 0.30, 0.30) for indice in range(1_000))

    resultado = ancorar_postes_no_desenho(leituras, (_disco("d1", 0.31, 0.30),))

    assert len(resultado) == 1
    assert _atributos(resultado[0])["poste_ancorado_disco"] is True


def test_teto_vale_por_pagina() -> None:
    hostil = _poste("a", "P1", 0.30, 0.30)
    normal = _poste("b", "P2", 0.30, 0.30, pagina=OUTRA_PAGINA)
    discos = (
        *(_disco(f"d{indice}", 0.31, 0.30) for indice in range(2_001)),
        _disco("outra", 0.31, 0.30, pagina=OUTRA_PAGINA),
    )

    resultado = {item.id: item for item in ancorar_postes_no_desenho((hostil, normal), discos)}

    assert resultado[hostil.id] == hostil
    assert _atributos(resultado[normal.id])["poste_ancorado_disco"] is True


def test_nada_muda_para_categorias_que_nao_sao_poste() -> None:
    estrutura = replace(_poste("a", "P1", 0.30, 0.30), categoria=CategoriaElemento.ESTRUTURA_MT)

    assert ancorar_postes_no_desenho((estrutura,), (_disco("d1", 0.33, 0.30),)) == (estrutura,)


def test_poste_sem_identificador_nao_e_tocado() -> None:
    poste = replace(_poste("a", "P1", 0.30, 0.30), atributos_sugeridos=())

    assert ancorar_postes_no_desenho((poste,), (_disco("d1", 0.33, 0.30),)) == (poste,)


def _solicitacao_relacoes(catalogo: CatalogoTecnico) -> SolicitacaoInterpretacao:
    return SolicitacaoInterpretacao(
        projeto_id=uuid4(),
        execucao_id=EXECUCAO,
        execucao_extracao_id=uuid4(),
        catalogo=catalogo,
        evidencias=(),
        registro=carregar_registro_regras_inicial(),
    )


def _poste_ancorado_longe_do_texto() -> PropostaElemento:
    return _poste(
        "a",
        "P1",
        0.50,
        0.30,
        extras=(("poste_ancorado_disco", True), ("poste_texto_centro", "0.3,0.3")),
    )


_ID_DA_ORIGEM = uuid5(EXECUCAO, "prop:e")


def _relacoes_de_estrutura(
    catalogo: CatalogoTecnico,
    poste: PropostaElemento,
    categoria: CategoriaElemento,
) -> list[tuple[str, UUID, UUID]]:
    solicitacao = _solicitacao_relacoes(catalogo)
    origem = replace(_poste("e", "P1", 0.36, 0.30, codigo="N1"), categoria=categoria)
    relacoes = InterpretadorFichaPoste(solicitacao.registro)._gerar_relacoes(
        EXECUCAO, (poste, origem), solicitacao
    )
    return [
        (item.tipo_relacao, item.origem_referencia_id, item.destino_referencia_id)
        for item in relacoes
    ]


@pytest.mark.parametrize(
    ("categoria", "tipo_relacao"),
    [
        pytest.param(CategoriaElemento.ESTRUTURA_MT, "INSTALADA_EM", id="estrutura-mt"),
        pytest.param(CategoriaElemento.ESTRUTURA_BT, "INSTALADA_EM", id="estrutura-bt"),
        pytest.param(CategoriaElemento.EQUIPAMENTO, "INSTALADO_EM", id="equipamento"),
    ],
)
def test_vinculo_ao_poste_usa_a_posicao_do_texto_e_nao_a_do_disco(
    catalogo_inicial: CatalogoTecnico,
    categoria: CategoriaElemento,
    tipo_relacao: str,
) -> None:
    # O disco está a mais de 0,10 da origem; o texto do poste, a menos de 0,10.
    poste = _poste_ancorado_longe_do_texto()

    relacoes = _relacoes_de_estrutura(catalogo_inicial, poste, categoria)

    assert relacoes == [(tipo_relacao, _ID_DA_ORIGEM, poste.id)]


def test_poste_nao_ancorado_vincula_pela_propria_posicao(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    poste = _poste("a", "P1", 0.30, 0.30, extras=(("poste_ancorado_disco", False),))

    relacoes = _relacoes_de_estrutura(catalogo_inicial, poste, CategoriaElemento.ESTRUTURA_MT)

    assert relacoes == [("INSTALADA_EM", _ID_DA_ORIGEM, poste.id)]


def test_cabo_usa_o_poste_no_disco(catalogo_inicial: CatalogoTecnico) -> None:
    solicitacao = _solicitacao_relacoes(catalogo_inicial)
    poste = _poste_ancorado_longe_do_texto()
    cabo = replace(
        _poste("c", "P1", 0.5, 0.5),
        categoria=CategoriaElemento.CABO,
        geometria=GeometriaDocumento.polilinha(PAGINA, (_ponto(0.51, 0.30), _ponto(0.70, 0.30))),
        atributos_sugeridos=(),
    )

    relacoes = InterpretadorFichaPoste(solicitacao.registro)._gerar_relacoes(
        EXECUCAO, (poste, cabo), solicitacao
    )

    assert [
        (item.tipo_relacao, item.origem_referencia_id, item.destino_referencia_id)
        for item in relacoes
    ] == [("CONECTA", cabo.id, poste.id)]


def test_cabo_longe_do_disco_nao_conecta_mesmo_perto_do_texto(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    solicitacao = _solicitacao_relacoes(catalogo_inicial)
    poste = _poste_ancorado_longe_do_texto()
    cabo = replace(
        _poste("c", "P1", 0.5, 0.5),
        categoria=CategoriaElemento.CABO,
        geometria=GeometriaDocumento.polilinha(PAGINA, (_ponto(0.25, 0.30), _ponto(0.31, 0.30))),
        atributos_sugeridos=(),
    )

    relacoes = InterpretadorFichaPoste(solicitacao.registro)._gerar_relacoes(
        EXECUCAO, (poste, cabo), solicitacao
    )

    assert relacoes == ()
