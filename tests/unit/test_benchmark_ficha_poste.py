from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from scripts.benchmark_ficha_poste import VERSAO_EXTRACAO, executar, ficha_predita, main
from scripts.ficha_poste import validar_ficha
from tests.factories import complete_project
from tests.pdf_fixtures import create_network_benchmark_pdf

from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, SituacaoProjeto
from zeny_project_handler.domain.project import Equipamento, Poste, Projeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

SHA_QUALQUER = "a" * 64


def _referencia_sintetica(sha: str) -> dict[str, Any]:
    def poste(id_: str, identificador: str, x: float, largura: float) -> dict[str, Any]:
        return {
            "id": id_,
            "pagina": 1,
            "bbox": [x, 0.2275, x + largura, 0.318],
            "identificador": identificador,
            "estruturas": [],
            "poste": "P-9M-150DAN-CIRCULAR",
            "coordenada": None,
            "simbolos": [],
            "pendentes": [],
        }

    return {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": sha,
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [poste("r1", "P1", 80 / 600, 0.16), poste("r2", "P2", 430 / 600, 0.16)],
        "vaos": [
            {"de": "r1", "para": "r2", "comprimento_m": 35.0, "cabo": "ABC-4 CA", "pendentes": []}
        ],
    }


def _grava(caminho: Path, dados: dict[str, Any]) -> Path:
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return caminho


def _projeto_com(
    catalogo: CatalogoTecnico, *construtores: Any
) -> tuple[Projeto, UUID, GeometriaDocumento]:
    base = complete_project(catalogo)
    pagina_id = base.documentos[0].paginas[0].id
    geometria = GeometriaDocumento.caixa(
        pagina_id,
        PontoNormalizado(Decimal("0.2"), Decimal("0.4")),
        PontoNormalizado(Decimal("0.3"), Decimal("0.5")),
    )
    poste = Poste(
        id=uuid4(),
        tipo_catalogo_id=base.elementos[0].tipo_catalogo_id,
        situacao=SituacaoProjeto.EXISTENTE,
        codigo_observado="POSTE",
        identificador_operacional="P1",
        geometria=geometria,
    )
    equipamentos = tuple(
        Equipamento(
            id=uuid4(),
            tipo_catalogo_id=next(
                item.tipo_catalogo_id
                for item in base.elementos
                if item.categoria is CategoriaElemento.EQUIPAMENTO
            ),
            situacao=SituacaoProjeto.EXISTENTE,
            poste_id=poste.id,
            geometria=construtor(geometria),
        )
        for construtor in construtores
    )
    projeto = replace(
        base,
        elementos=(poste, *equipamentos),
        pontos_rede=(),
        terminais=(),
        conexoes_internas=(),
        vinculos_obra=(),
        relacoes_confirmadas=(),
    )
    return projeto, poste.id, geometria


def _variante(
    projeto: Projeto, atributos_por_elemento: dict[UUID, dict[str, Any]]
) -> dict[str, Any]:
    propostas = []
    decisoes = []
    for elemento_id, atributos in atributos_por_elemento.items():
        proposta = SimpleNamespace(id=uuid4(), atributos_sugeridos=tuple(atributos.items()))
        propostas.append(proposta)
        decisoes.append(
            SimpleNamespace(proposta_id=proposta.id, elemento_confirmado_id=elemento_id)
        )
    return {
        "project": projeto,
        "decisions": (*decisoes, None),
        "semantic": SimpleNamespace(elementos=tuple(propostas)),
        "analyzer": {"version": "a1", "signature": "assinatura"},
        "interpreter_version": "i1",
        "registry_signature": "registro",
    }


def test_ficha_predita_da_rede_sintetica_e_valida(tmp_path: Path) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    saida = tmp_path / "saida"

    executar(
        pdf,
        _grava(tmp_path / "ref.json", _referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())),
        saida,
        native_only=True,
        runtime_directory=tmp_path / "runtime",
    )

    ficha = json.loads((saida / "ficha-predita.json").read_text(encoding="utf-8"))
    assert validar_ficha(ficha) == []
    assert ficha["tipo"] == "predicao"
    assert ficha["pdf_sha256"] == sha256(pdf.read_bytes()).hexdigest()
    assert ficha["gerador"]["versao_extracao"] == "projeto-promovido-v1" == VERSAO_EXTRACAO
    assert ficha["gerador"]["native_only"] is True


def test_poste_vindo_de_simbolo_nao_grava_classe_como_poste(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    projeto, poste_id, _ = _projeto_com(catalogo_inicial)

    de_simbolo = ficha_predita(
        _variante(projeto, {poste_id: {"origem_simbolo_ocorrencia_id": "oc-1"}}),
        SHA_QUALQUER,
        native_only=True,
    )
    de_texto = ficha_predita(_variante(projeto, {poste_id: {}}), SHA_QUALQUER, native_only=True)

    assert validar_ficha(de_simbolo) == []
    assert de_simbolo["postes"][0]["poste"] is None
    assert de_simbolo["postes"][0]["atributos_extras"] == {
        "origem": "simbolo",
        "classe_simbolo": "POSTE",
    }
    assert de_texto["postes"][0]["poste"] == "POSTE"
    assert de_texto["postes"][0]["atributos_extras"] == {}


def test_equipamento_sem_simbolo_ou_fora_do_inventario_fica_fora_e_e_contado(
    catalogo_inicial: CatalogoTecnico,
) -> None:
    def caixa(geometria: GeometriaDocumento) -> GeometriaDocumento:
        return geometria

    def ponto(geometria: GeometriaDocumento) -> GeometriaDocumento:
        return GeometriaDocumento.ponto(
            geometria.pagina_id, PontoNormalizado(Decimal("0.2"), Decimal("0.4"))
        )

    projeto, poste_id, _ = _projeto_com(catalogo_inicial, caixa, caixa, caixa, ponto, caixa)
    sem_simbolo, fora, bom, sem_area, poste_como_simbolo = (
        item.id for item in projeto.elementos[1:]
    )
    variante = _variante(
        projeto,
        {
            poste_id: {},
            sem_simbolo: {},
            fora: {"simbolo_classe": "CLASSE_INEXISTENTE"},
            bom: {"simbolo_classe": "ESTAI"},
            sem_area: {"simbolo_classe": "ESTAI"},
            poste_como_simbolo: {"simbolo_classe": "POSTE"},
        },
    )

    ficha = ficha_predita(variante, SHA_QUALQUER, native_only=True)

    assert validar_ficha(ficha) == []
    assert [(s["id"], s["classe"]) for s in ficha["postes"][0]["simbolos"]] == [(str(bom), "ESTAI")]
    assert ficha["atributos_extras"] == {
        "equipamentos_sem_simbolo": 1,
        "simbolos_fora_do_inventario": 2,
        "simbolos_sem_area": 1,
    }


def test_cli_grava_ficha_e_avaliacao_sem_caminho_absoluto(tmp_path: Path) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede-secreta.pdf")
    referencia = _grava(
        tmp_path / "ref.json", _referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())
    )
    saida = tmp_path / "saida"

    codigo = main(
        [
            str(pdf),
            "--referencia",
            str(referencia),
            "--saida",
            str(saida),
            "--native-only",
            "--runtime-directory",
            str(tmp_path / "runtime"),
        ]
    )

    assert codigo == 0
    assert sorted(item.name for item in saida.iterdir()) == ["avaliacao.json", "ficha-predita.json"]
    for nome in ("ficha-predita.json", "avaliacao.json"):
        texto = (saida / nome).read_text(encoding="utf-8")
        assert str(tmp_path) not in texto
        assert tmp_path.as_posix() not in texto
        assert "rede-secreta" not in texto


def test_referencia_de_outro_pdf_e_recusada(tmp_path: Path) -> None:
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    saida = tmp_path / "saida"

    with pytest.raises(ValueError, match="sha256"):
        executar(
            pdf,
            _grava(tmp_path / "ref.json", _referencia_sintetica(SHA_QUALQUER)),
            saida,
            native_only=True,
            runtime_directory=tmp_path / "runtime",
        )

    assert not (saida / "ficha-predita.json").exists()


def test_baseline_sintetico_do_analisador_atual(tmp_path: Path) -> None:
    """Baseline: muda só com mudança deliberada do analisador ou do protocolo.

    Erros esperados: o 35m do vão não vira comprimento do cabo no analisador (um erro de
    comprimento) e o ESTAI da referência não tem contraparte: o PDF sintético não desenha estai,
    é uma anotação posta só para fixar o caminho do FN de símbolo (fn=1 sairia igual mesmo que o
    analisador promovesse estais). A R2 (estai nunca promovido) só seria exercitada com um estai
    real na fixture. Cabo com postes intermediários viraria um vão só em detectar_vaos (M5); a rede
    sintética não tem intermediários.
    """
    pdf = create_network_benchmark_pdf(tmp_path / "rede.pdf")
    referencia = _referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())
    referencia["postes"][0]["simbolos"] = [
        {"id": "s1", "classe": "ESTAI", "bbox": [0.1, 0.35, 0.15, 0.4]}
    ]

    relatorio = executar(
        pdf,
        _grava(tmp_path / "ref.json", referencia),
        tmp_path / "saida",
        native_only=True,
        runtime_directory=tmp_path / "runtime",
    )

    assert (relatorio["postes"]["tp"], relatorio["postes"]["fp"], relatorio["postes"]["fn"]) == (
        2,
        0,
        0,
    )
    for campo in ("identificador", "estruturas", "poste", "coordenada"):
        assert (relatorio["campos"][campo]["acertos"], relatorio["campos"][campo]["total"]) == (
            2,
            2,
        )
    vaos = relatorio["vaos"]
    assert (vaos["tp"], vaos["fp"], vaos["fn"]) == (1, 0, 0)
    assert (vaos["cabo"]["acertos"], vaos["cabo"]["total"]) == (1, 1)
    assert (vaos["comprimento"]["acertos"], vaos["comprimento"]["total"]) == (0, 1)
    assert vaos["comprimento"]["erros_sem_pendencia"] == 1
    simbolos = relatorio["simbolos"]
    assert (simbolos["tp"], simbolos["fp"], simbolos["fn"]) == (0, 0, 1)
    assert simbolos["recall"] == 0.0
    assert simbolos["precisao"] is None
