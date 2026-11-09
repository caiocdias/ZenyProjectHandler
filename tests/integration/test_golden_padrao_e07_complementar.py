"""Golden complementar da análise padrão (`simbolos=None`) da E07.1.

Acrescenta ao golden principal (`golden_padrao_e07.json`) os casos que ele não exercita e que
deixavam vazamentos de comportamento passarem em branco: fusão real de leituras duplicadas, empate
dentro da tolerância de 0,004, cabo pendente junto de poste, preferência pela mesma situação e os
raios de associação do identificador localizado por OCR e da coordenada de contexto.

Para regenerar de propósito (somente com mudança de comportamento aprovada), rode
``python -m tests.integration.test_golden_padrao_e07_complementar`` a partir da raiz.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from sqlalchemy import Engine
from tests.integration.test_golden_padrao_e07 import (
    _EXTRACAO_ID,
    _PAGINA_ID,
    _VERDE,
    _VERMELHO,
    _projeto,
    _serializar,
)
from tests.interpretation_factories import text_evidence, vector_evidence

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
    upgrade_database,
)
from zeny_project_handler.application.interpretation_pipeline import (
    ExecutarPipelineInterpretacao,
    ResultadoExecucaoInterpretacao,
)
from zeny_project_handler.domain.analysis import EvidenciaDocumento, ExecucaoAnalise
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoExecucaoAnalise

pytestmark = pytest.mark.integration

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "golden_padrao_e07_complementar.json"
_OCR_LOCALIZADO = "tesseract-identificador-localizado"


def _texto(chave: str, conteudo: str, x: str, y: str, **extra: str) -> EvidenciaDocumento:
    return text_evidence(
        execution_id=_EXTRACAO_ID,
        page_id=_PAGINA_ID,
        key=chave,
        text=conteudo,
        x=x,
        y=y,
        **extra,
    )


def _ocr_localizado(chave: str, conteudo: str, x: str, y: str) -> EvidenciaDocumento:
    base = _texto(chave, conteudo, x, y)
    return replace(
        base,
        atributos_extraidos=(*base.atributos_extraidos, ("motor_ocr", _OCR_LOCALIZADO)),
    )


def _evidencias(catalogo: CatalogoTecnico) -> tuple[EvidenciaDocumento, ...]:
    postes = tuple(item.codigo for item in catalogo.itens_ativos(CategoriaElemento.POSTE))
    cabo = catalogo.itens_ativos(CategoriaElemento.CABO)[1].codigo
    return (
        # Duplicata real: a mesma leitura de P5 em dois textos sobrepostos deve virar uma só.
        _texto("dup-a", f"POSTE {postes[0]}", "0.10", "0.10", color=_VERDE),
        _texto("dup-b", f"POSTE {postes[0]}", "0.10", "0.10", color=_VERDE),
        _texto("dup-rotulo", "P5", "0.10", "0.07"),
        # Empate dentro da tolerância de 0,004: duas leituras de P6 e uma estrutura a 0,050 e 0,053.
        _texto("p6-a", f"POSTE {postes[1]}", "0.30", "0.10", color=_VERDE),
        _texto("p6-b", f"POSTE {postes[2]}", "0.403", "0.10", color=_VERDE),
        _texto("p6-rotulo", "P6", "0.35", "0.07"),
        _texto("p6-estrutura", "U1", "0.35", "0.10", color=_VERDE, rotation="90"),
        # Identificador OCR localizado: a 0,065 do poste é rejeitado (limite 0,06); a 0,055 vale.
        _texto("ocr-longe-poste", f"POSTE {postes[0]}", "0.60", "0.10", color=_VERDE),
        _ocr_localizado("ocr-longe-rotulo", "P7", "0.665", "0.10"),
        _texto("ocr-perto-poste", f"POSTE {postes[1]}", "0.80", "0.10", color=_VERDE),
        _ocr_localizado("ocr-perto-rotulo", "P8", "0.855", "0.10"),
        # Coordenada de contexto: a 0,125 do poste não vale (limite 0,12); a ~0,106 vale.
        _texto("coord-longe-poste", f"POSTE {postes[2]}", "0.60", "0.30", color=_VERDE),
        _texto("coord-longe-rotulo", "P9", "0.60", "0.27"),
        _texto("coord-longe-leste", "0465702", "0.725", "0.30"),
        _texto("coord-longe-norte", "7772468", "0.725", "0.31"),
        _texto("coord-perto-poste", f"POSTE {postes[3]}", "0.20", "0.30", color=_VERDE),
        _texto("coord-perto-rotulo", "P10", "0.20", "0.27"),
        _texto("coord-perto-leste", "0465750", "0.305", "0.30"),
        _texto("coord-perto-norte", "7772490", "0.305", "0.31"),
        # Leituras do mesmo identificador a 0,115 uma da outra: componentes separados.
        _texto("comp-a", f"POSTE {postes[0]}", "0.20", "0.50", color=_VERDE),
        _texto("comp-b", f"POSTE {postes[1]}", "0.315", "0.50", color=_VERDE),
        _texto("comp-rotulo", "P11", "0.26", "0.47"),
        # Cabo pendente (dois traçados paralelos) com o rótulo junto de um poste.
        _texto("pend-poste", f"POSTE {postes[3]}", "0.60", "0.58", color=_VERDE),
        _texto("pend-poste-rotulo", "P12", "0.60", "0.61"),
        _texto("pend-cabo", cabo, "0.60", "0.555", color=_VERDE),
        vector_evidence(
            execution_id=_EXTRACAO_ID,
            page_id=_PAGINA_ID,
            key="pend-tracado-a",
            points=(("0.50", "0.55"), ("0.70", "0.55")),
            color=_VERDE,
        ),
        vector_evidence(
            execution_id=_EXTRACAO_ID,
            page_id=_PAGINA_ID,
            key="pend-tracado-b",
            points=(("0.50", "0.56"), ("0.70", "0.56")),
            color=_VERDE,
        ),
        # Mesma situação: estrutura a instalar prefere o poste a instalar, mesmo mais distante.
        _texto("sit-rotulo", "P13", "0.21", "0.82"),
        _texto("sit-estrutura", "U1", "0.21", "0.85", color=_VERDE, rotation="90"),
        _texto("sit-poste-remover", f"POSTE {postes[2]}", "0.18", "0.85", color=_VERMELHO),
        _texto("sit-poste-instalar", f"POSTE {postes[3]}", "0.26", "0.85", color=_VERDE),
        # Raio do rótulo do poste (0,14): o rótulo a 0,135 vale; a 0,145 não.
        _texto("raio-perto-poste", f"POSTE {postes[0]}", "0.50", "0.85", color=_VERDE),
        _texto("raio-perto-rotulo", "P14", "0.635", "0.85"),
        _texto("raio-longe-poste", f"POSTE {postes[1]}", "0.80", "0.85", color=_VERDE),
        _texto("raio-longe-rotulo", "P15", "0.945", "0.85"),
        # Estruturas MT com qualificadores diferentes sobrepostas não se fundem.
        _texto("qual-rotulo", "P16", "0.10", "0.93"),
        _texto("qual-a", "N(2)", "0.10", "0.96", color=_VERDE),
        _texto("qual-b", "N(3)", "0.10", "0.96", color=_VERDE),
        *_duplicata_por_confianca(postes),
        *_cabos_e_limite_de_extremidade(postes, cabo),
        *_contextos_locais(),
    )


def _duplicata_por_confianca(postes: tuple[str, ...]) -> tuple[EvidenciaDocumento, ...]:
    """Duas leituras do mesmo poste existente: a de nomenclatura (0,86) vence o código (0,82)."""
    codigo = next(item for item in postes if item.startswith("P-11M-300DAN-CIRCULAR"))
    return (
        _texto("conf-codigo", f"POSTE {codigo}", "0.45", "0.22"),
        _texto("conf-nomenclatura", "11M-300 CIRCULAR", "0.45", "0.22"),
        _texto("conf-rotulo", "P24", "0.45", "0.19"),
    )


def _poste_rotulado(
    chave: str, codigo: str, identificador: str, x: str, y: str, lado: str
) -> tuple[EvidenciaDocumento, ...]:
    """Poste verde com o rótulo P<n> a 0,02 à direita (`+`) ou à esquerda (`-`)."""
    deslocamento = Decimal("0.02") if lado == "+" else Decimal("-0.02")
    return (
        _texto(f"{chave}-poste", f"POSTE {codigo}", x, y, color=_VERDE),
        _texto(f"{chave}-rotulo", identificador, str(Decimal(x) + deslocamento), y),
    )


def _tracado(
    chave: str, pontos: tuple[tuple[str, str], ...], cabo: str, rotulo: tuple[str, str]
) -> tuple[EvidenciaDocumento, ...]:
    return (
        vector_evidence(
            execution_id=_EXTRACAO_ID,
            page_id=_PAGINA_ID,
            key=f"{chave}-tracado",
            points=pontos,
            color=_VERDE,
        ),
        _texto(f"{chave}-cabo", cabo, rotulo[0], rotulo[1], color=_VERDE),
    )


def _cabos_e_limite_de_extremidade(
    postes: tuple[str, ...], cabo: str
) -> tuple[EvidenciaDocumento, ...]:
    """Polilinha com vértice intermediário, extremos a 0,098 e 0,102 do poste (limite 0,10)
    e cabo com um extremo só.

    Nos cabos do limite o traçado nasce no poste de número maior: o extremo achado a 0,098 faz o
    traçado ser orientado do menor para o maior número; o achado a 0,102 não, e o traçado fica.
    """
    return (
        # Um extremo só: o outro, em (0.16, 0.62), fica a 0,112 ou mais de qualquer poste.
        *_poste_rotulado("um-extremo", postes[0], "P17", "0.05", "0.64", "+"),
        *_tracado("um-extremo", (("0.05", "0.64"), ("0.16", "0.62")), cabo, ("0.10", "0.63")),
        # Polilinha de três pontos, com vértice intermediário fora da reta dos extremos.
        *_poste_rotulado("vertice-a", postes[1], "P18", "0.05", "0.70", "+"),
        *_poste_rotulado("vertice-b", postes[2], "P19", "0.25", "0.70", "-"),
        *_tracado(
            "vertice",
            (("0.05", "0.70"), ("0.15", "0.73"), ("0.25", "0.70")),
            cabo,
            ("0.15", "0.72"),
        ),
        # Extremo a 0,098 do poste (dentro do limite de 0,10).
        *_poste_rotulado("limite-dentro-a", postes[0], "P21", "0.35", "0.68", "+"),
        *_poste_rotulado("limite-dentro-b", postes[1], "P20", "0.648", "0.68", "-"),
        *_tracado("limite-dentro", (("0.35", "0.68"), ("0.55", "0.68")), cabo, ("0.45", "0.67")),
        # Extremo a 0,102 do poste (fora do limite de 0,10).
        *_poste_rotulado("limite-fora-a", postes[2], "P23", "0.35", "0.76", "+"),
        *_poste_rotulado("limite-fora-b", postes[3], "P22", "0.652", "0.76", "-"),
        *_tracado("limite-fora", (("0.35", "0.76"), ("0.55", "0.76")), cabo, ("0.45", "0.75")),
    )


def _legenda_conjunta(chave: str, x: str, y: str) -> tuple[EvidenciaDocumento, ...]:
    """Estrutura e poste sem P<n> na mesma legenda: um contexto local."""
    return (_texto(chave, "N2-10-300", x, y),)


def _contextos_locais() -> tuple[EvidenciaDocumento, ...]:
    """Tolerância de 0,004 de `_local_context`, em três ensaios isolados em 0,14 uns dos outros."""
    return (
        # Empate: dois contextos a 0,020 e 0,023 da estrutura BT (diferença 0,003): pendência.
        *_legenda_conjunta("ctx-empate-a", "0.430", "0.40"),
        *_legenda_conjunta("ctx-empate-b", "0.473", "0.40"),
        _texto("ctx-empate-sonda", "S3R", "0.450", "0.40"),
        # Sem empate: 0,020 e 0,026 (diferença 0,006): o mais próximo vale.
        *_legenda_conjunta("ctx-claro-a", "0.430", "0.52"),
        *_legenda_conjunta("ctx-claro-b", "0.476", "0.52"),
        _texto("ctx-claro-sonda", "S3R", "0.450", "0.52"),
        # P<n> nomeado a 0,053 da sonda contra contexto a 0,050 (diferença 0,003): o P vale.
        *_legenda_conjunta("ctx-nome-a", "0.830", "0.45"),
        _texto("ctx-nome-sonda", "S3R", "0.880", "0.45"),
        _texto("ctx-nome-rotulo", "P25", "0.933", "0.45"),
        # P<n> nomeado a 0,056 contra contexto a 0,050 (diferença 0,006): o contexto vale.
        *_legenda_conjunta("ctx-sem-nome-a", "0.830", "0.60"),
        _texto("ctx-sem-nome-sonda", "S3R", "0.880", "0.60"),
        _texto("ctx-sem-nome-rotulo", "P26", "0.936", "0.60"),
    )


def _executar(engine: Engine, catalogo: CatalogoTecnico) -> ResultadoExecucaoInterpretacao:
    projeto = _projeto(catalogo)
    extracao = ExecucaoAnalise(
        id=_EXTRACAO_ID,
        projeto_id=projeto.id,
        metodo="fixture-extraction",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 7, 21, 12, tzinfo=UTC),
        finalizada_em=datetime(2026, 7, 21, 12, 1, tzinfo=UTC),
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo)
        work.projetos.salvar(projeto)
        work.execucoes_analise.salvar(extracao)
        for item in _evidencias(catalogo):
            work.evidencias.salvar(item)
        work.commit()
    registro = carregar_registro_regras_inicial()
    return ExecutarPipelineInterpretacao(
        InterpretadorRegrasExplicitas(registro),
        registro,
        lambda: SqlAlchemyUnitOfWork(engine),
        relogio=lambda: datetime(2026, 7, 21, 13, tzinfo=UTC),
    ).executar(projeto.id, extracao.id)


def _atributos(elemento: dict[str, Any]) -> dict[str, Any]:
    return dict(elemento["atributos_sugeridos"])


def _postes(resultado: dict[str, Any], identificador: str) -> list[dict[str, Any]]:
    return [
        item
        for item in resultado["elementos"]
        if item["categoria"] == "POSTE"
        and _atributos(item).get("identificador_operacional") == identificador
    ]


def _relacoes_de(resultado: dict[str, Any], identificador: str) -> list[dict[str, Any]]:
    """Relações cuja origem é a estrutura MT rotulada com o identificador."""
    origens = {
        item["id"]
        for item in resultado["elementos"]
        if item["categoria"] == "ESTRUTURA_MT"
        and _atributos(item).get("identificador_operacional") == identificador
    }
    return [item for item in resultado["relacoes"] if item["origem_referencia_id"] in origens]


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    motor = create_sqlite_engine(tmp_path / "golden.sqlite3")
    upgrade_database(motor)
    try:
        yield motor
    finally:
        motor.dispose()


@pytest.fixture
def resultado(engine: Engine, catalogo_inicial: CatalogoTecnico) -> dict[str, Any]:
    return _serializar(_executar(engine, catalogo_inicial))


def test_analise_padrao_complementar_mantem_saida_congelada(resultado: dict[str, Any]) -> None:
    assert resultado == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_complementar_e_da_opcao_desligada(resultado: dict[str, Any]) -> None:
    parametros = dict(resultado["parametros"])
    assert resultado["versao_metodo"] == "25.0"
    assert "semantica_simbolos_versao" not in parametros
    assert "simbolos_reconciliados_assinatura" not in parametros
    assert "configuracao_simbolos_assinatura" not in parametros


def test_leituras_duplicadas_do_mesmo_poste_viram_um_so_com_evidencias_unidas(
    resultado: dict[str, Any],
) -> None:
    (poste,) = _postes(resultado, "P5")

    # texto A + texto B + rótulo P5
    assert len(poste["evidencia_ids"]) == 3


def test_identificador_ocr_localizado_so_vale_dentro_de_0_06(resultado: dict[str, Any]) -> None:
    assert _postes(resultado, "P7") == []
    assert len(_postes(resultado, "P8")) == 1


def test_coordenada_de_contexto_so_vale_dentro_de_0_12(resultado: dict[str, Any]) -> None:
    (longe,) = _postes(resultado, "P9")
    (perto,) = _postes(resultado, "P10")

    assert "coordenada_leste" not in _atributos(longe)
    assert _atributos(perto)["coordenada_leste"] == 465750


def test_empate_dentro_da_tolerancia_de_0_004_nao_gera_instalada_em(
    resultado: dict[str, Any],
) -> None:
    assert _relacoes_de(resultado, "P6") == []


def test_estrutura_a_instalar_prefere_o_poste_a_instalar_mesmo_mais_distante(
    resultado: dict[str, Any],
) -> None:
    (relacao,) = _relacoes_de(resultado, "P13")
    destino = next(
        item for item in resultado["elementos"] if item["id"] == relacao["destino_referencia_id"]
    )

    assert destino["situacao_projeto"] == "INSTALAR"


def test_rotulo_do_poste_so_vale_dentro_de_0_14(resultado: dict[str, Any]) -> None:
    assert len(_postes(resultado, "P14")) == 1
    assert _postes(resultado, "P15") == []


def test_estruturas_com_qualificadores_diferentes_nao_se_fundem(resultado: dict[str, Any]) -> None:
    qualificadores = sorted(
        str(_atributos(item).get("qualificador_estrutura"))
        for item in resultado["elementos"]
        if item["categoria"] == "ESTRUTURA_MT"
        and _atributos(item).get("identificador_operacional") == "P16"
    )

    assert qualificadores == ["2", "3"]


def test_cabo_pendente_junto_de_poste_nao_gera_relacao(resultado: dict[str, Any]) -> None:
    pendentes = [
        item
        for item in resultado["elementos"]
        if _atributos(item).get("associacao_pendente") == "tracado"
    ]
    ids = {item["id"] for item in pendentes}

    assert len(pendentes) == 1
    assert not any(
        {item["origem_referencia_id"], item["destino_referencia_id"]} & ids
        for item in resultado["relacoes"]
    )


def _cabos_com_extremo(resultado: dict[str, Any], x: str, y: str) -> list[dict[str, Any]]:
    ponto = {"x": x, "y": y}
    return [
        item
        for item in resultado["elementos"]
        if item["categoria"] == "CABO"
        and ponto in (item["geometria"]["pontos"][0], item["geometria"]["pontos"][-1])
        and _atributos(item).get("associacao_pendente") is None
    ]


def _postes_ligados_ao_cabo(resultado: dict[str, Any], x: str, y: str) -> list[str]:
    """Identificadores dos postes ligados (CONECTA) ao cabo com um extremo em (x, y)."""
    cabos = {item["id"] for item in _cabos_com_extremo(resultado, x, y)}
    destinos = {
        item["destino_referencia_id"]
        for item in resultado["relacoes"]
        if item["tipo_relacao"] == "CONECTA" and item["origem_referencia_id"] in cabos
    }
    return sorted(
        str(_atributos(item)["identificador_operacional"])
        for item in resultado["elementos"]
        if item["id"] in destinos
    )


def test_polilinha_de_cabo_com_vertice_intermediario_mantem_os_tres_pontos(
    resultado: dict[str, Any],
) -> None:
    (cabo,) = _cabos_com_extremo(resultado, "0.05", "0.70")

    assert len(cabo["geometria"]["pontos"]) == 3
    assert _postes_ligados_ao_cabo(resultado, "0.05", "0.70") == ["P18", "P19"]


def test_extremo_do_cabo_so_liga_ao_poste_dentro_de_0_10(resultado: dict[str, Any]) -> None:
    (dentro,) = _cabos_com_extremo(resultado, "0.35", "0.68")
    (fora,) = _cabos_com_extremo(resultado, "0.35", "0.76")

    assert _postes_ligados_ao_cabo(resultado, "0.35", "0.68") == ["P20", "P21"]
    assert _postes_ligados_ao_cabo(resultado, "0.35", "0.76") == ["P23"]
    # extremo achado a 0,098: orientado do P20 para o P21; a 0,102: o traçado fica como nasceu
    assert dentro["geometria"]["pontos"][0] == {"x": "0.55", "y": "0.68"}
    assert fora["geometria"]["pontos"][0] == {"x": "0.35", "y": "0.76"}


def test_cabo_com_um_extremo_so_liga_apenas_o_poste_do_extremo(resultado: dict[str, Any]) -> None:
    assert _postes_ligados_ao_cabo(resultado, "0.05", "0.64") == ["P17"]


def test_duplicata_decidida_por_confianca_fica_com_a_leitura_mais_confiante(
    resultado: dict[str, Any],
) -> None:
    (poste,) = _postes(resultado, "P24")

    assert poste["confianca"] == "0.86"
    assert poste["codigo_observado"] == "11-300"
    # texto do código + texto da nomenclatura + rótulo P24
    assert len(poste["evidencia_ids"]) == 3


def _estruturas_bt_em(resultado: dict[str, Any], x: str, y: str) -> dict[str, Any]:
    (estrutura,) = (
        item
        for item in resultado["elementos"]
        if item["categoria"] == "ESTRUTURA_BT"
        and item["geometria"]["pontos"][0] == {"x": x, "y": y}
    )
    return _atributos(estrutura)


def test_contextos_locais_a_menos_de_0_004_um_do_outro_ficam_em_empate(
    resultado: dict[str, Any],
) -> None:
    atributos = _estruturas_bt_em(resultado, "0.450", "0.40")

    assert atributos["associacao_pendente"] == "contextos_locais_em_empate"
    assert "contexto_ponto_id" not in atributos


def test_contexto_local_a_mais_de_0_004_do_segundo_vale_sem_empate(
    resultado: dict[str, Any],
) -> None:
    atributos = _estruturas_bt_em(resultado, "0.450", "0.52")

    assert "associacao_pendente" not in atributos
    assert "contexto_ponto_id" in atributos


def test_identificador_nomeado_so_vence_o_contexto_local_dentro_de_0_004(
    resultado: dict[str, Any],
) -> None:
    nomeado = _estruturas_bt_em(resultado, "0.880", "0.45")
    contextual = _estruturas_bt_em(resultado, "0.880", "0.60")

    assert nomeado["identificador_operacional"] == "P25"
    assert "contexto_ponto_id" not in nomeado
    assert "identificador_operacional" not in contextual
    assert "contexto_ponto_id" in contextual


def _gerar_golden() -> None:
    with TemporaryDirectory() as pasta:
        motor = create_sqlite_engine(Path(pasta) / "golden.sqlite3")
        upgrade_database(motor)
        try:
            dados = _serializar(_executar(motor, carregar_catalogo_inicial()))
        finally:
            motor.dispose()
    GOLDEN.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    _gerar_golden()
