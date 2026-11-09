"""Ataque à ancoragem do poste no disco e às relações por regime (E07.2.1, Task 4)."""

from __future__ import annotations

import math
import random
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from tests.unit.test_ancoragem_poste import (
    EXECUCAO,
    OUTRA_PAGINA,
    PAGINA,
    ROXO,
    VERDE,
    _atributos,
    _centro,
    _disco,
    _ligado_ao,
    _ponto,
    _poste,
    _poste_ancorado_longe_do_texto,
    _rotulo,
    _solicitacao_relacoes,
)

from zeny_project_handler.adapters.interpretation import ancoragem_poste as modulo_ancoragem
from zeny_project_handler.adapters.interpretation.ancoragem_poste import (
    ancorar_postes_no_desenho,
)
from zeny_project_handler.adapters.interpretation.ficha_poste import InterpretadorFichaPoste
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
)
from zeny_project_handler.domain.values import GeometriaDocumento


def _por_id(resultado: tuple[PropostaElemento, ...]) -> dict[UUID, PropostaElemento]:
    return {item.id: item for item in resultado}


def _assert_pendente_na_posicao_do_texto(
    original: PropostaElemento, resultado: PropostaElemento
) -> None:
    assert resultado.geometria == original.geometria
    assert _atributos(resultado)["poste_ancorado_disco"] is False
    assert _atributos(resultado)["associacao_pendente"] == "poste_disco"


def _ancorado_em(resultado: PropostaElemento, x: float, y: float = 0.30) -> bool:
    return _atributos(resultado).get("poste_ancorado_disco") is True and _centro(
        resultado
    ) == pytest.approx((x, y), abs=1e-6)


def test_empate_exato_de_dois_p_em_dois_sitios_deixa_os_dois_pendentes() -> None:
    primeiro = _poste("a", "P1", 0.32, 0.30)
    segundo = _poste("b", "P2", 0.32, 0.34)
    discos = (_disco("d1", 0.30, 0.32), _disco("d2", 0.34, 0.32))

    resultado = _por_id(ancorar_postes_no_desenho((primeiro, segundo), discos))

    _assert_pendente_na_posicao_do_texto(primeiro, resultado[primeiro.id])
    _assert_pendente_na_posicao_do_texto(segundo, resultado[segundo.id])


@pytest.mark.parametrize(
    ("folga", "disputado"),
    [
        pytest.param(0.0039, True, id="dentro-da-margem"),
        pytest.param(0.0041, False, id="fora-da-margem"),
    ],
)
def test_margem_de_disputa_de_um_sitio_por_dois_p(folga: float, disputado: bool) -> None:
    perto = _poste("a", "P1", 0.47, 0.30)
    longe = _poste("b", "P2", 0.53 + folga, 0.30)

    resultado = _por_id(ancorar_postes_no_desenho((perto, longe), (_disco("d1", 0.50, 0.30),)))

    if disputado:
        _assert_pendente_na_posicao_do_texto(perto, resultado[perto.id])
        _assert_pendente_na_posicao_do_texto(longe, resultado[longe.id])
    else:
        assert _ancorado_em(resultado[perto.id], 0.50)
        assert resultado[longe.id].geometria == longe.geometria
        assert _atributos(resultado[longe.id])["poste_ancorado_disco"] is False
        assert "associacao_pendente" not in _atributos(resultado[longe.id])


@pytest.mark.parametrize(
    ("folga", "ambiguo"),
    [
        pytest.param(0.0039, True, id="dentro-da-margem"),
        pytest.param(0.0041, False, id="fora-da-margem"),
    ],
)
def test_margem_do_rotulo_entre_dois_sitios(folga: float, ambiguo: bool) -> None:
    poste = _poste("a", "P1", 0.50, 0.30)
    discos = (_disco("d1", 0.47, 0.30), _disco("d2", 0.53 + folga, 0.30))

    resultado = ancorar_postes_no_desenho((poste,), discos)

    if ambiguo:
        _assert_pendente_na_posicao_do_texto(poste, resultado[0])
    else:
        assert _ancorado_em(resultado[0], 0.47)


def _dois_p_entre_dois_sitios(
    x_primeiro: float, x_segundo: float
) -> tuple[PropostaElemento, PropostaElemento, tuple[PropostaElemento, ...]]:
    # Rótulos no meio dos discos e nomenclatura de cada poste junto ao disco do vizinho.
    rotulo_1 = _rotulo("r1", "P1", x_primeiro, 0.30)
    rotulo_2 = _rotulo("r2", "P2", x_segundo, 0.30)
    primeiro = _poste("a", "P1", 0.385, 0.33, extras=_ligado_ao(rotulo_1))
    segundo = _poste("b", "P2", 0.315, 0.33, extras=_ligado_ao(rotulo_2))
    resultado = ancorar_postes_no_desenho(
        (primeiro, segundo),
        (rotulo_1, rotulo_2, _disco("d1", 0.30, 0.30), _disco("d2", 0.40, 0.30)),
    )
    return primeiro, segundo, resultado


def test_rotulos_cruzados_a_menos_de_0_004_nunca_vao_ao_vizinho() -> None:
    primeiro, segundo, resultado = _dois_p_entre_dois_sitios(0.34825, 0.35175)

    por_id = _por_id(resultado)
    _assert_pendente_na_posicao_do_texto(primeiro, por_id[primeiro.id])
    _assert_pendente_na_posicao_do_texto(segundo, por_id[segundo.id])


def test_rotulos_entre_dois_sitios_fora_da_margem_ficam_cada_um_no_seu() -> None:
    primeiro, segundo, resultado = _dois_p_entre_dois_sitios(0.3475, 0.3525)

    por_id = _por_id(resultado)
    assert _ancorado_em(por_id[primeiro.id], 0.30)
    assert _ancorado_em(por_id[segundo.id], 0.40)


def test_poste_com_o_sitio_mais_proximo_bloqueado_por_ambiguidade_nao_cai_em_terceiro_sitio() -> (
    None
):
    # P1 fica entre S1 e S2 (pendente). P2 tem S2 como disco mais próximo; S3 é de outro poste.
    ambiguo = _poste("a", "P1", 0.50, 0.30)
    vizinho = _poste("b", "P2", 0.553, 0.30)
    discos = (
        _disco("s1", 0.48, 0.30),
        _disco("s2", 0.523, 0.30),
        _disco("s3", 0.613, 0.30),
    )

    resultado = _por_id(ancorar_postes_no_desenho((ambiguo, vizinho), discos))

    _assert_pendente_na_posicao_do_texto(ambiguo, resultado[ambiguo.id])
    assert not _ancorado_em(resultado[vizinho.id], 0.613)


def test_rival_ja_resolvido_no_proprio_disco_nao_gera_pendencia() -> None:
    # P2 está colado ao próprio disco; também está à mesma distância do disco de P1.
    primeiro = _poste("a", "P1", 0.47, 0.30)
    segundo = _poste("b", "P2", 0.53, 0.30)
    discos = (_disco("d1", 0.50, 0.30), _disco("d2", 0.532, 0.30))

    resultado = _por_id(ancorar_postes_no_desenho((primeiro, segundo), discos))

    assert _ancorado_em(resultado[segundo.id], 0.532)
    assert _ancorado_em(resultado[primeiro.id], 0.50)
    assert "associacao_pendente" not in _atributos(resultado[primeiro.id])


def test_resultado_nao_depende_da_ordem_das_propostas_nem_das_evidencias() -> None:
    rotulo = _rotulo("r1", "P1", 0.30, 0.30)
    postes = (
        _poste("a", "P1", 0.31, 0.30, extras=_ligado_ao(rotulo)),
        _poste("b", "P1", 0.31, 0.306, codigo="12-300", extras=_ligado_ao(rotulo)),
        _poste("c", "P2", 0.60, 0.30),
        _poste("d", "P3", 0.64, 0.30),
        _poste("e", "P4", 0.20, 0.60),
    )
    evidencias = (
        rotulo,
        _disco("d1", 0.33, 0.30),
        _disco("d2", 0.34, 0.30),
        _disco("d3", 0.62, 0.30),
        _disco("d4", 0.18, 0.60),
        _disco("d5", 0.222, 0.60),
    )
    referencia = _por_id(ancorar_postes_no_desenho(postes, evidencias))
    embaralhador = random.Random(7)

    for _ in range(5):
        outras = tuple(embaralhador.sample(postes, len(postes)))
        outras_evidencias = tuple(embaralhador.sample(evidencias, len(evidencias)))
        assert _por_id(ancorar_postes_no_desenho(outras, outras_evidencias)) == referencia


@pytest.mark.parametrize(
    ("cor", "aceita"),
    [
        pytest.param("#007700", True, id="verde-7-unidades-acima"),
        pytest.param("#007800", False, id="verde-8-unidades-acima"),
        pytest.param("#F80000", True, id="vermelho-7-unidades-abaixo"),
        pytest.param("#F70000", False, id="vermelho-8-unidades-abaixo"),
        pytest.param("#070707", True, id="preto-7-unidades"),
        pytest.param("#080808", False, id="preto-8-unidades"),
        pytest.param("#4f1a4d", True, id="roxo-em-minusculas"),
        pytest.param("#00B300", True, id="verde-claro"),
        pytest.param("#008000", True, id="verde-medio"),
        pytest.param("#0000FF", False, id="azul"),
        pytest.param("#FFFFFF", False, id="branco"),
        pytest.param("#00700", False, id="hex-curto"),
        pytest.param("#0070000", False, id="hex-longo"),
        pytest.param("#GG7000", False, id="hex-invalido"),
        pytest.param("verde", False, id="nome-de-cor"),
    ],
)
def test_cor_do_disco_respeita_a_paleta_com_tolerancia(cor: str, aceita: bool) -> None:
    poste = _poste("a", "P1", 0.30, 0.30)

    resultado = ancorar_postes_no_desenho((poste,), (_disco("d1", 0.31, 0.30, cor=cor),))

    if aceita:
        assert _atributos(resultado[0])["poste_ancorado_disco"] is True
    else:
        assert resultado == (poste,)


def test_disco_sem_atributo_de_cor_nao_ancora() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    disco = replace(_disco("d1", 0.31, 0.30), atributos_extraidos=(("operacoes", "c,c,c,c"),))

    assert ancorar_postes_no_desenho((poste,), (disco,)) == (poste,)


@pytest.mark.parametrize(
    ("diametro", "aceita"),
    [
        pytest.param(0.9, True, id="minimo"),
        pytest.param(0.89, False, id="abaixo-do-minimo"),
        pytest.param(7.0, True, id="maximo"),
        pytest.param(7.01, False, id="acima-do-maximo"),
    ],
)
def test_limites_do_diametro_em_pontos_do_pdf(diametro: float, aceita: bool) -> None:
    poste = _poste("a", "P1", 0.30, 0.30)

    resultado = ancorar_postes_no_desenho(
        (poste,), (_disco("d1", 0.31, 0.30, diametro_pt=diametro),)
    )

    assert (resultado != (poste,)) is aceita


@pytest.mark.parametrize(
    ("razao", "aceita"),
    [
        pytest.param(0.86, True, id="dentro-por-baixo"),
        pytest.param(0.84, False, id="fora-por-baixo"),
        pytest.param(1.14, True, id="dentro-por-cima"),
        pytest.param(1.16, False, id="fora-por-cima"),
    ],
)
def test_limites_da_razao_de_aspecto(razao: float, aceita: bool) -> None:
    poste = _poste("a", "P1", 0.30, 0.30)

    resultado = ancorar_postes_no_desenho((poste,), (_disco("d1", 0.31, 0.30, razao=razao),))

    assert (resultado != (poste,)) is aceita


@pytest.mark.parametrize(
    "conteudo",
    [
        pytest.param("null", id="nulo"),
        pytest.param("{}", id="objeto-vazio"),
        pytest.param("5", id="numero"),
        pytest.param('"texto"', id="cadeia"),
        pytest.param("[]", id="lista-vazia"),
        pytest.param("[[]]", id="comando-vazio"),
        pytest.param('[["c"]]', id="comando-sem-pontos"),
        pytest.param('[["c",[1]]]', id="ponto-com-uma-coordenada"),
        pytest.param('[["c",[1,1],[1,1]]]', id="pontos-identicos"),
        pytest.param('[["c",[NaN,NaN],[NaN,NaN]]]', id="nan"),
        pytest.param('[["c",[Infinity,0],[0,Infinity]]]', id="infinito"),
        pytest.param('[{"a":1}]', id="comando-objeto"),
        pytest.param('[["c",{"x":1,"y":2}]]', id="ponto-objeto"),
        pytest.param('[["c",[1' + "0" * 400 + ",0],[0,1]]]", id="numero-gigante"),
        pytest.param("[" * 200_000, id="aninhamento-profundo"),
    ],
)
def test_conteudo_malformado_descarta_so_o_disco_e_o_valido_ainda_ancora(conteudo: str) -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    malformado = _disco("ruim", 0.305, 0.30, conteudo=conteudo)
    valido = _disco("bom", 0.33, 0.30)

    resultado = ancorar_postes_no_desenho((poste,), (malformado, valido))

    assert _ancorado_em(resultado[0], 0.33)


@pytest.mark.parametrize(
    "geometria",
    [
        pytest.param(GeometriaDocumento.ponto(PAGINA, _ponto(0.305, 0.30)), id="ponto"),
        pytest.param(
            GeometriaDocumento.polilinha(PAGINA, (_ponto(0.304, 0.30), _ponto(0.306, 0.30))),
            id="linha-sem-altura",
        ),
        pytest.param(
            GeometriaDocumento.polilinha(PAGINA, (_ponto(0.305, 0.299), _ponto(0.305, 0.301))),
            id="linha-sem-largura",
        ),
    ],
)
def test_disco_com_geometria_sem_area_nao_derruba_a_ancoragem(
    geometria: GeometriaDocumento,
) -> None:
    # A extração devolve PONTO ou POLILINHA quando a caixa colapsa na normalização.
    colapsado = replace(_disco("colapsado", 0.305, 0.30), geometria=geometria)
    distante = _poste("b", "P2", 0.70, 0.70)
    bom = _disco("bom", 0.71, 0.70)

    resultado = _por_id(
        ancorar_postes_no_desenho((_poste("a", "P1", 0.30, 0.30), distante), (colapsado, bom))
    )

    assert _ancorado_em(resultado[distante.id], 0.71, 0.70)


def test_disco_de_glifo_e_filtrado_em_rotulo_que_atravessa_varias_celulas() -> None:
    poste = _poste("a", "P1", 0.40, 0.33)
    rotulo = replace(
        _rotulo("rot", "11-300", 0.375, 0.30),
        geometria=GeometriaDocumento.caixa(PAGINA, _ponto(0.29, 0.296), _ponto(0.46, 0.304)),
    )

    assert ancorar_postes_no_desenho((poste,), (rotulo, _disco("glifo", 0.40, 0.30))) == (poste,)


@pytest.mark.parametrize("texto", ["11 - 300", "p7", " P12 ", "9-150"])
def test_filtro_de_glifo_reconhece_as_variantes_de_rotulo(texto: str) -> None:
    poste = _poste("a", "P1", 0.33, 0.33)
    rotulo = replace(
        _rotulo("rot", texto, 0.33, 0.30),
        geometria=GeometriaDocumento.caixa(PAGINA, _ponto(0.325, 0.296), _ponto(0.34, 0.304)),
    )

    assert ancorar_postes_no_desenho((poste,), (rotulo, _disco("glifo", 0.335, 0.30))) == (poste,)


def test_filtro_de_glifo_vale_para_rotulo_de_ocr() -> None:
    poste = _poste("a", "P1", 0.33, 0.33)
    rotulo = replace(
        _rotulo("rot", "11-300", 0.33, 0.30),
        tipo=TipoEvidencia.OCR,
        geometria=GeometriaDocumento.caixa(PAGINA, _ponto(0.325, 0.296), _ponto(0.34, 0.304)),
    )

    assert ancorar_postes_no_desenho((poste,), (rotulo, _disco("glifo", 0.335, 0.30))) == (poste,)


def test_disco_com_centro_fora_da_caixa_do_rotulo_continua_candidato() -> None:
    poste = _poste("a", "P1", 0.33, 0.33)
    rotulo = replace(
        _rotulo("rot", "11-300", 0.33, 0.30),
        geometria=GeometriaDocumento.caixa(PAGINA, _ponto(0.325, 0.296), _ponto(0.34, 0.304)),
    )

    resultado = ancorar_postes_no_desenho((poste,), (rotulo, _disco("perto", 0.342, 0.30)))

    assert _ancorado_em(resultado[0], 0.342)


def test_par_verde_e_roxo_vale_com_o_raio_do_verde() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    discos = (_disco("d1", 0.40, 0.30), _disco("d2", 0.41, 0.30, cor=ROXO))

    resultado = ancorar_postes_no_desenho((poste,), discos)

    assert _ancorado_em(resultado[0], 0.405)


def test_par_so_de_roxos_mantem_o_raio_curto() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    discos = (_disco("d1", 0.34, 0.30, cor=ROXO), _disco("d2", 0.35, 0.30, cor=ROXO))

    resultado = ancorar_postes_no_desenho((poste,), discos)

    assert _atributos(resultado[0])["poste_ancorado_disco"] is False


def test_par_de_discos_grava_as_duas_evidencias_e_uma_so_posicao() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    outro = _poste("b", "P2", 0.335, 0.34)
    discos = (_disco("d1", 0.33, 0.30, cor=VERDE), _disco("d2", 0.34, 0.30, cor=VERDE))

    resultado = _por_id(ancorar_postes_no_desenho((poste, outro), discos))

    assert _ancorado_em(resultado[poste.id], 0.335)
    assert {discos[0].id, discos[1].id} <= set(resultado[poste.id].evidencia_ids)
    assert _atributos(resultado[outro.id])["poste_ancorado_disco"] is False


@pytest.mark.parametrize(
    ("situacao_a", "codigo_a", "situacao_b", "codigo_b", "conflito"),
    [
        pytest.param(
            SituacaoProjeto.INSTALAR,
            "11-300",
            SituacaoProjeto.EXISTENTE,
            "11-300",
            True,
            id="situacoes-diferentes-mesmo-codigo",
        ),
        pytest.param(
            SituacaoProjeto.INSTALAR,
            "11-300",
            SituacaoProjeto.ALTERAR,
            "12-300",
            True,
            id="situacoes-e-codigos-diferentes",
        ),
        pytest.param(
            SituacaoProjeto.INSTALAR,
            "11-300",
            SituacaoProjeto.INSTALAR,
            "11-300",
            False,
            id="iguais",
        ),
        pytest.param(
            SituacaoProjeto.INSTALAR,
            "11-300",
            SituacaoProjeto.REMOVER,
            "11-300",
            False,
            id="remover-com-mesmo-codigo",
        ),
        pytest.param(
            SituacaoProjeto.REMOVER,
            "11-300",
            SituacaoProjeto.REMOVER,
            "11-300",
            False,
            id="duas-remover-concordantes",
        ),
        pytest.param(
            SituacaoProjeto.REMOVER,
            "11-300",
            SituacaoProjeto.REMOVER,
            "12-300",
            True,
            id="duas-remover-discordantes",
        ),
    ],
)
def test_duas_leituras_do_mesmo_p_no_mesmo_disco_viram_uma(
    situacao_a: SituacaoProjeto,
    codigo_a: str,
    situacao_b: SituacaoProjeto,
    codigo_b: str,
    conflito: bool,
) -> None:
    primeira = _poste("a", "P1", 0.30, 0.30, codigo=codigo_a, situacao=situacao_a)
    segunda = _poste("b", "P1", 0.30, 0.306, codigo=codigo_b, situacao=situacao_b)

    resultado = ancorar_postes_no_desenho((primeira, segunda), (_disco("d1", 0.33, 0.30),))

    assert len(resultado) == 1
    esperado = EstadoRevisao.CONFLITANTE if conflito else EstadoRevisao.PROPOSTA
    assert resultado[0].estado_revisao is esperado
    assert ("classificacao_pendente" in _atributos(resultado[0])) is conflito
    assert "associacao_pendente" not in _atributos(resultado[0])


@pytest.mark.parametrize(
    "confianca_remover",
    [pytest.param("0.99", id="mais-confiavel"), pytest.param("0.10", id="menos-confiavel")],
)
def test_leitura_remover_nunca_sobrevive_a_uma_instalar_no_mesmo_disco(
    confianca_remover: str,
) -> None:
    instalar = _poste("nova", "P1", 0.30, 0.30)
    remover = _poste(
        "velha",
        "P1",
        0.30,
        0.306,
        situacao=SituacaoProjeto.REMOVER,
        confianca=confianca_remover,
    )

    resultado = ancorar_postes_no_desenho((instalar, remover), (_disco("d1", 0.30, 0.33),))

    assert [item.id for item in resultado] == [instalar.id]
    assert resultado[0].situacao_projeto is SituacaoProjeto.INSTALAR


def test_remover_mais_perto_do_disco_com_o_mesmo_rotulo_nao_toma_o_disco_da_instalar() -> None:
    rotulo = _rotulo("r", "P1", 0.30, 0.30)
    remover = _poste(
        "velha",
        "P1",
        0.32,
        0.30,
        situacao=SituacaoProjeto.REMOVER,
        confianca="0.99",
        extras=_ligado_ao(rotulo),
    )
    instalar = _poste("nova", "P1", 0.36, 0.30, extras=_ligado_ao(rotulo))

    resultado = _por_id(
        ancorar_postes_no_desenho((remover, instalar), (rotulo, _disco("d1", 0.31, 0.30)))
    )

    assert _atributos(resultado[instalar.id])["poste_ancorado_disco"] is True
    assert resultado[remover.id].geometria == remover.geometria
    assert _atributos(resultado[remover.id])["poste_ancorado_disco"] is False


def test_confianca_ausente_conta_como_zero_na_pilha() -> None:
    sem_confianca = replace(_poste("a", "P1", 0.30, 0.30, codigo="10-300"), confianca=None)
    com_confianca = _poste("b", "P1", 0.30, 0.306, codigo="12-300", confianca="0.10")

    resultado = ancorar_postes_no_desenho(
        (sem_confianca, com_confianca), (_disco("d1", 0.33, 0.30),)
    )

    assert [item.id for item in resultado] == [com_confianca.id]
    assert resultado[0].estado_revisao is EstadoRevisao.CONFLITANTE


def test_texto_do_poste_fundido_e_o_da_leitura_sobrevivente() -> None:
    forte = _poste("forte", "P1", 0.30, 0.30, confianca="0.90")
    fraca = _poste("fraca", "P1", 0.30, 0.306, confianca="0.86")

    resultado = ancorar_postes_no_desenho((forte, fraca), (_disco("d1", 0.33, 0.30),))

    assert _atributos(resultado[0])["poste_texto_centro"] == "0.3,0.3"


def test_pendencia_preexistente_nao_e_sobrescrita_pelo_mesmo_identificador() -> None:
    primeiro = _poste("a", "P3", 0.30, 0.30, extras=(("associacao_pendente", "outra_causa"),))
    segundo = _poste("b", "P3", 0.50, 0.30)
    discos = (_disco("d1", 0.33, 0.30), _disco("d2", 0.53, 0.30))

    resultado = _por_id(ancorar_postes_no_desenho((primeiro, segundo), discos))

    assert _atributos(resultado[primeiro.id])["associacao_pendente"] == "outra_causa"
    assert _atributos(resultado[segundo.id])["associacao_pendente"] == "poste_mesmo_identificador"


def test_poste_ancorado_preserva_a_pendencia_preexistente() -> None:
    poste = _poste("a", "P1", 0.30, 0.30, extras=(("associacao_pendente", "outra_causa"),))

    resultado = ancorar_postes_no_desenho((poste,), (_disco("d1", 0.33, 0.30),))

    assert _ancorado_em(resultado[0], 0.33)
    assert _atributos(resultado[0])["associacao_pendente"] == "outra_causa"


def test_mesmo_p_em_paginas_diferentes_nao_e_pendencia() -> None:
    nesta = _poste("a", "P1", 0.30, 0.30)
    na_outra = _poste("b", "P1", 0.30, 0.30, pagina=OUTRA_PAGINA)
    discos = (_disco("d1", 0.33, 0.30), _disco("d2", 0.33, 0.30, pagina=OUTRA_PAGINA))

    resultado = ancorar_postes_no_desenho((nesta, na_outra), discos)

    assert all(_atributos(item)["poste_ancorado_disco"] is True for item in resultado)
    assert all("associacao_pendente" not in _atributos(item) for item in resultado)


def test_mesmo_p_com_um_so_disco_nao_vira_mesmo_identificador() -> None:
    perto = _poste("a", "P3", 0.30, 0.30)
    longe = _poste("b", "P3", 0.50, 0.30)

    resultado = _por_id(ancorar_postes_no_desenho((perto, longe), (_disco("d1", 0.31, 0.30),)))

    assert _ancorado_em(resultado[perto.id], 0.31)
    assert "associacao_pendente" not in _atributos(resultado[perto.id])
    assert "associacao_pendente" not in _atributos(resultado[longe.id])


def test_identificador_que_nao_e_texto_nao_entra_na_ancoragem() -> None:
    poste = replace(
        _poste("a", "P1", 0.30, 0.30),
        atributos_sugeridos=(("identificador_operacional", 7),),
    )

    assert ancorar_postes_no_desenho((poste,), (_disco("d1", 0.33, 0.30),)) == (poste,)


def test_teto_de_discos_ainda_ancora_no_limite() -> None:
    poste = _poste("a", "P1", 0.02, 0.98)
    distantes = tuple(
        _disco(f"d{indice}", 0.20 + (indice % 50) * 0.015, 0.05 + (indice // 50) * 0.02)
        for indice in range(1_999)
    )

    resultado = ancorar_postes_no_desenho((poste,), (*distantes, _disco("perto", 0.03, 0.98)))

    assert _ancorado_em(resultado[0], 0.03, 0.98)


def test_teto_de_rotulos_ainda_ancora_no_limite() -> None:
    poste = _poste("a", "P1", 0.30, 0.30)
    rotulos = tuple(_rotulo(f"r{indice}", "P9", 0.70, 0.70) for indice in range(2_000))

    resultado = ancorar_postes_no_desenho((poste,), (*rotulos, _disco("d1", 0.31, 0.30)))

    assert _ancorado_em(resultado[0], 0.31)


def test_teto_de_grupos_ainda_ancora_no_limite() -> None:
    postes = tuple(
        _poste(
            f"p{indice}",
            f"P{indice}",
            0.05 + (indice % 20) * 0.045,
            0.05 + (indice // 20) * 0.037,
        )
        for indice in range(500)
    )
    discos = tuple(
        _disco(f"d{indice}", _centro(item)[0] + 0.004, _centro(item)[1])
        for indice, item in enumerate(postes)
    )

    resultado = ancorar_postes_no_desenho(postes, discos)

    assert all(_atributos(item)["poste_ancorado_disco"] is True for item in resultado)


def test_agrupar_leituras_sem_rotulo_nao_tem_custo_quadratico_fora_do_teto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Duas nuvens de leituras do mesmo P: nenhum teto limita a quantidade de leituras.
    quantidade = 3_000
    leituras = tuple(
        _poste(
            f"p{indice}",
            "P1",
            0.10 if indice % 2 else 0.90,
            0.10 if indice % 2 else 0.90,
        )
        for indice in range(quantidade)
    )
    chamadas = {"dist": 0}

    def dist_contada(primeiro: Any, segundo: Any) -> float:
        chamadas["dist"] += 1
        return math.dist(primeiro, segundo)

    monkeypatch.setattr(
        modulo_ancoragem, "math", SimpleNamespace(dist=dist_contada, floor=math.floor)
    )

    ancorar_postes_no_desenho(leituras, ())

    assert chamadas["dist"] <= 20 * quantidade


def _estrutura(x: float, categoria: CategoriaElemento) -> PropostaElemento:
    return replace(_poste("e", "P1", x, 0.30, codigo="N1"), categoria=categoria)


def _cabo_no_disco() -> PropostaElemento:
    return replace(
        _poste("c", "P1", 0.5, 0.5),
        categoria=CategoriaElemento.CABO,
        geometria=GeometriaDocumento.polilinha(PAGINA, (_ponto(0.51, 0.30), _ponto(0.70, 0.30))),
        atributos_sugeridos=(),
    )


def test_mesma_execucao_liga_a_estrutura_pelo_texto_e_o_cabo_pelo_disco(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    solicitacao = _solicitacao_relacoes(catalogo_inicial)
    poste = _poste_ancorado_longe_do_texto()
    estrutura = _estrutura(0.36, CategoriaElemento.ESTRUTURA_MT)
    cabo = _cabo_no_disco()

    relacoes = InterpretadorFichaPoste(solicitacao.registro)._gerar_relacoes(
        EXECUCAO, (poste, estrutura, cabo), solicitacao
    )

    assert {
        (item.tipo_relacao, item.origem_referencia_id, item.destino_referencia_id)
        for item in relacoes
    } == {("INSTALADA_EM", estrutura.id, poste.id), ("CONECTA", cabo.id, poste.id)}


def test_id_da_relacao_nao_depende_da_posicao_do_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    solicitacao = _solicitacao_relacoes(catalogo_inicial)
    interpretador = InterpretadorFichaPoste(solicitacao.registro)
    ancorado = _poste_ancorado_longe_do_texto()
    no_texto = _poste("a", "P1", 0.30, 0.30, extras=(("poste_ancorado_disco", False),))
    estrutura = _estrutura(0.36, CategoriaElemento.ESTRUTURA_MT)

    com_disco = interpretador._gerar_relacoes(EXECUCAO, (ancorado, estrutura), solicitacao)
    sem_disco = interpretador._gerar_relacoes(EXECUCAO, (no_texto, estrutura), solicitacao)

    assert ancorado.id == no_texto.id
    assert [item.id for item in com_disco] == [item.id for item in sem_disco]
    assert com_disco


def test_poste_texto_centro_em_notacao_exponencial_e_aceito(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    solicitacao = _solicitacao_relacoes(catalogo_inicial)
    poste = _poste(
        "a",
        "P1",
        0.50,
        0.30,
        extras=(("poste_ancorado_disco", True), ("poste_texto_centro", "1e-05,0.3")),
    )
    estrutura = _estrutura(0.05, CategoriaElemento.ESTRUTURA_MT)

    relacoes = InterpretadorFichaPoste(solicitacao.registro)._gerar_relacoes(
        EXECUCAO, (poste, estrutura), solicitacao
    )

    assert [item.tipo_relacao for item in relacoes] == ["INSTALADA_EM"]


def test_regra_inativa_nao_gera_relacao_por_regime(catalogo_inicial: CatalogoTecnico) -> None:
    solicitacao = _solicitacao_relacoes(catalogo_inicial)
    registro = replace(
        solicitacao.registro,
        regras_relacao=tuple(
            replace(regra, ativa=False) for regra in solicitacao.registro.regras_relacao
        ),
    )
    poste = _poste_ancorado_longe_do_texto()
    estrutura = _estrutura(0.36, CategoriaElemento.ESTRUTURA_MT)

    assert (
        InterpretadorFichaPoste(registro)._gerar_relacoes(
            EXECUCAO, (poste, estrutura, _cabo_no_disco()), solicitacao
        )
        == ()
    )


def test_poste_texto_centro_guarda_precisao_de_seis_digitos() -> None:
    poste = replace(
        _poste("a", "P1", 0.30, 0.30),
        geometria=GeometriaDocumento.caixa(
            PAGINA,
            _ponto(0.123456, 0.654321),
            _ponto(0.123458, 0.654323),
        ),
    )

    resultado = ancorar_postes_no_desenho((poste,), (_disco("d1", 0.13, 0.66),))

    x, y = _atributos(resultado[0])["poste_texto_centro"].split(",")
    assert float(Decimal(x)) == pytest.approx(0.123457, abs=1e-6)
    assert float(Decimal(y)) == pytest.approx(0.654322, abs=1e-6)
