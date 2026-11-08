# mypy: disable-error-code="no-untyped-call"
"""E06.2.2.1: o método sobre o modelo de desenho como quinto método do runner opt-in."""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import math
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pymupdf
import pytest
from tests.fixtures.symbol_grammars.stem_bars import (
    CASOS_HASTE,
    DECRESCENTES,
    DesenhoHaste,
    desenhar_positivo,
)

from zeny_project_handler.adapters.analysis import (
    declarative_symbols,
    model_symbols,
    pymupdf_drawing_model,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationEntry,
    CalibrationPolicy,
)
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler_server import symbol_execution
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.deliverable_exports import _symbol_status
from zeny_project_handler_server.symbol_execution import (
    SymbolCompositionError,
    SymbolCompositionRunner,
)

pytestmark = pytest.mark.integration

_METODO_NOVO = "declarative-drawing-model"
_MOLDURA_CT = (101.0, 115.0, 169.0, 149.0)
_PRETO = (0, 0, 0)
_VARIANTE_CT = "cemig-eo-r3-s06-v001"
_CLASSE_DE_ATIVO = "TRANSFORMADOR"
_PROBABILIDADE = Decimal("0.995")


def _settings(data: Path, **opcoes: Any) -> ServerSettings:
    return ServerSettings(
        password="senha segura do metodo do modelo",
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=data,
        symbol_composition=True,
        **{"symbol_profile": "vector-only", **opcoes},
    )


def _pdf(
    caminho: Path, *, paginas: int = 2, ocg: bool = False, imagem: bool = False, ct: bool = True
) -> Path:
    with pymupdf.open() as documento:
        oc = documento.add_ocg("REDE") if ocg else 0
        for _ in range(paginas):
            pagina = documento.new_page(width=300, height=300)
            if imagem:
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
                pixmap.clear_with(128)
                pagina.insert_image(pymupdf.Rect(10, 10, 30, 30), pixmap=pixmap)
            if ct:
                pagina.draw_rect(pymupdf.Rect(_MOLDURA_CT), color=_PRETO, width=1, oc=oc)
                pagina.insert_text((_MOLDURA_CT[0] + 6, _MOLDURA_CT[1] + 25), "CT", fontsize=11)
        documento.save(caminho)
    return caminho


def _fonte(pdf: Path) -> tuple[DocumentoProjeto, ReferenciaFontePdf]:
    documento = PyMuPdfReader().inspecionar(pdf).documento
    return documento, ReferenciaFontePdf(
        documento_id=documento.id,
        projeto_id=uuid4(),
        caminho_canonico=pdf.resolve(),
        sha256=documento.sha256,
        tamanho_bytes=pdf.stat().st_size,
        modificado_em_ns=pdf.stat().st_mtime_ns,
    )


def _journals(runner: SymbolCompositionRunner) -> list[dict[str, Any]]:
    """Todos os journals, sem ordem: o mtime não distingue duas gravações no mesmo tique."""
    arquivos = runner.partial_directory.glob("*.json")
    return [json.loads(arquivo.read_text(encoding="utf-8")) for arquivo in arquivos]


def _journal(runner: SymbolCompositionRunner, status: str) -> dict[str, Any]:
    """O único journal com esse `status`."""
    (achado,) = [j for j in _journals(runner) if j["status"] == status]
    return achado


def _cobertura_do_novo(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        cobertura
        for resultado in journal["results"]
        if resultado["method_id"] == _METODO_NOVO
        for cobertura in resultado["coverage"]
    ]


def test_quinto_metodo_roda_e_entra_na_assinatura(tmp_path: Path) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf"))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    runner.run(documento, fonte)

    (journal,) = _journals(runner)
    assert journal["status"] == "completed"
    assert [item["page"] for item in _cobertura_do_novo(journal)] == [1, 2]
    assert len(runner._profiles) == 5
    assert _METODO_NOVO in {profile.metodo_id for profile in runner._profiles}
    assert [item["status"] for item in _cobertura_do_novo(journal)] == ["CONCLUIDO"] * 2


@pytest.mark.parametrize("ocg", [False, True], ids=["sem-ocg", "com-ocg"])
def test_mesmo_desenho_nao_duplica_na_reconciliacao(tmp_path: Path, ocg: bool) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=1, ocg=ocg))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()

    composto = runner.run(documento, fonte)

    com_o_novo = [
        ocorrencia
        for ocorrencia in composto.occurrences
        if any(o.metodo_assinatura == novo for o in ocorrencia.observations)
    ]
    assert len(com_o_novo) == 1
    assert len({o.metodo_assinatura for o in com_o_novo[0].observations}) == 2


@pytest.mark.parametrize(
    "modulo",
    ["symbol_matcher", "glyph_signature", "pymupdf_annotations"],
)
def test_assinatura_muda_com_tabela_e_com_modulo_do_nucleo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modulo: str
) -> None:
    configuracao = _settings(tmp_path / "dados")
    original = SymbolCompositionRunner(configuracao).signature
    tabela: TabelaGlifos = carregar_tabela_glifos()
    outra = replace(tabela, sha256="b" * 64)
    assert SymbolCompositionRunner(configuracao, glyph_table=outra).signature != original

    digest_original = symbol_execution._module_digest

    def digest(alvo: Any) -> str:
        if alvo.__name__.rsplit(".", 1)[-1] == modulo:
            return "alterado"
        return digest_original(alvo)

    monkeypatch.setattr(symbol_execution, "_module_digest", digest)

    assert SymbolCompositionRunner(configuracao).signature != original


def test_teto_no_metodo_novo_e_cacheado_e_nao_derruba_os_outros(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=1))
    monkeypatch.setattr(symbol_execution, "LIMITE_CONSULTAS_PAGINA", 1)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    runner.run(documento, fonte)
    runner.run(documento, fonte)

    primeiro = _journal(runner, "completed")
    assert _journal(runner, "cache_hit")["cache_status"] == "hit"
    (cobertura,) = _cobertura_do_novo(primeiro)
    assert (cobertura["status"], cobertura["reason"]) == ("FORA_DOMINIO", "teto_consultas")
    outros = [r for r in primeiro["results"] if r["method_id"] != _METODO_NOVO]
    assert len(outros) == 4
    assert any(r["observations"] for r in outros)


def test_falha_de_fonte_aborta_e_nao_entra_no_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=1))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    def falhar(_pagina: Any) -> Any:
        raise RuntimeError("falha de caminhos")

    monkeypatch.setattr(pymupdf_drawing_model, "_caminhos_e_glifos", falhar)

    with pytest.raises(SymbolCompositionError, match=r"modelo.caminhos_falhou"):
        runner.run(documento, fonte)

    assert not list(runner.cache_directory.glob("*.json"))
    assert _journal(runner, "failed")["error"]


_RAIZ_DO_FECHO = "zeny_project_handler.adapters.analysis"


def _fecho_de_imports() -> set[str]:
    """Módulos de `adapters.analysis` que `model_symbols` importa, direta ou transitivamente."""
    vistos: set[str] = set()
    fila = [f"{_RAIZ_DO_FECHO}.model_symbols"]
    while fila:
        nome = fila.pop()
        if nome in vistos:
            continue
        vistos.add(nome)
        spec = importlib.util.find_spec(nome)
        if spec is None or spec.origin is None or not spec.origin.endswith(".py"):
            continue
        pacote = nome if spec.submodule_search_locations else nome.rsplit(".", 1)[0]
        for no in ast.walk(ast.parse(Path(spec.origin).read_text(encoding="utf-8"))):
            fila.extend(_alvos_de_import(no, pacote))
    return {nome for nome in vistos if nome.startswith(f"{_RAIZ_DO_FECHO}.")}


def _alvos_de_import(no: ast.AST, pacote: str) -> list[str]:
    if isinstance(no, ast.Import):
        candidatos = [alias.name for alias in no.names]
    elif isinstance(no, ast.ImportFrom):
        base = no.module or ""
        if no.level:
            partes = pacote.split(".")[: len(pacote.split(".")) - (no.level - 1)]
            base = ".".join([*partes, *([no.module] if no.module else [])])
        candidatos = [base, *(f"{base}.{alias.name}" for alias in no.names)]
    else:
        return []
    return [
        nome for nome in candidatos if nome.startswith(f"{_RAIZ_DO_FECHO}.") and _e_modulo(nome)
    ]


def _e_modulo(nome: str) -> bool:
    """`from m import Nome` também gera o candidato `m.Nome`, que só às vezes é um submódulo."""
    try:
        return importlib.util.find_spec(nome) is not None
    except ModuleNotFoundError:
        return False


def test_digest_cobre_o_fecho_de_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    digeridos: set[str] = set()
    digest_original = symbol_execution._module_digest

    def registrar(alvo: Any) -> str:
        digeridos.add(alvo.__name__)
        return digest_original(alvo)

    monkeypatch.setattr(symbol_execution, "_module_digest", registrar)

    SymbolCompositionRunner(_settings(tmp_path / "dados"))

    fecho = _fecho_de_imports()
    assert len(fecho) > 15
    assert fecho - digeridos == set()


@pytest.mark.parametrize("modulo", sorted(nome.rsplit(".", 1)[-1] for nome in _fecho_de_imports()))
def test_cada_modulo_do_digest_invalida_a_assinatura(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modulo: str
) -> None:
    configuracao = _settings(tmp_path / "dados")
    original = SymbolCompositionRunner(configuracao).signature
    digest_original = symbol_execution._module_digest

    def digest(alvo: Any) -> str:
        return "alterado" if alvo.__name__.rsplit(".", 1)[-1] == modulo else digest_original(alvo)

    monkeypatch.setattr(symbol_execution, "_module_digest", digest)

    assert SymbolCompositionRunner(configuracao).signature != original


def test_assinatura_e_estavel_entre_instancias(tmp_path: Path) -> None:
    configuracao = _settings(tmp_path / "dados")

    assert (
        SymbolCompositionRunner(configuracao).signature
        == SymbolCompositionRunner(configuracao).signature
    )


def test_cancelamento_antes_do_metodo_novo_nao_deixa_resultado_nem_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeny_project_handler.adapters.analysis import declarative_symbols
    from zeny_project_handler.application.errors import FluxoMvpCanceladoError

    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=2))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    cancelar = [False]
    original = declarative_symbols.observar_pacotes

    def observar_e_cancelar(*args: Any, **kwargs: Any) -> Any:
        resultado = original(*args, **kwargs)
        cancelar[0] = True
        return resultado

    monkeypatch.setattr(declarative_symbols, "observar_pacotes", observar_e_cancelar)

    with pytest.raises(FluxoMvpCanceladoError):
        runner.run(documento, fonte, cancelado=lambda: cancelar[0])

    journal = _journal(runner, "cancelled")
    assert _cobertura_do_novo(journal) == []
    assert not list(runner.cache_directory.glob("*.json"))
    # nova execução sem cancelamento reprocessa tudo e conclui
    runner.run(documento, fonte)
    assert _journal(runner, "completed")["cache_status"] == "stored"
    assert len(list(runner.cache_directory.glob("*.json"))) == 1


def test_cancelamento_a_partir_do_metodo_novo_na_pagina_1_nao_grava_cache_parcial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zeny_project_handler.adapters.analysis import model_symbols
    from zeny_project_handler.application.errors import FluxoMvpCanceladoError

    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=2))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    cancelar = [False]
    original = model_symbols.observar_pacotes_modelo

    def cancelando(*args: Any, **kwargs: Any) -> Any:
        cancelar[0] = True  # o pedido chega durante o método novo, na página 1
        return original(*args, **kwargs)

    monkeypatch.setattr(model_symbols, "observar_pacotes_modelo", cancelando)

    with pytest.raises(FluxoMvpCanceladoError):
        runner.run(documento, fonte, cancelado=lambda: cancelar[0])

    journal = _journal(runner, "cancelled")
    assert [c["page"] for c in _cobertura_do_novo(journal)] == [1]
    assert not list(runner.cache_directory.glob("*.json"))


@pytest.mark.parametrize("variante", ["girada", "cropbox"])
def test_reconciliacao_com_pagina_girada_ou_cropbox_nao_duplica(
    tmp_path: Path, variante: str
) -> None:
    pdf = _pdf(tmp_path / "a.pdf", paginas=1)
    with pymupdf.open(pdf) as aberto:
        pagina = aberto[0]
        if variante == "girada":
            pagina.set_rotation(90)
        else:
            pagina.set_cropbox(pymupdf.Rect(50, 50, 280, 280))
        aberto.save(tmp_path / "b.pdf")
    documento, fonte = _fonte(tmp_path / "b.pdf")
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()

    composto = runner.run(documento, fonte)

    com_o_novo = [
        o for o in composto.occurrences if any(x.metodo_assinatura == novo for x in o.observations)
    ]
    assert len(com_o_novo) == 1
    assert len({x.metodo_assinatura for x in com_o_novo[0].observations}) == 2


def test_falha_de_fonte_numa_pagina_tardia_aborta_sem_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=2))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    original = pymupdf_drawing_model._caminhos_e_glifos
    chamadas = [0]

    def segunda_falha(pagina: Any) -> Any:
        chamadas[0] += 1
        if chamadas[0] >= 2:
            raise RuntimeError("falha de caminhos")
        return original(pagina)

    monkeypatch.setattr(pymupdf_drawing_model, "_caminhos_e_glifos", segunda_falha)

    with pytest.raises(SymbolCompositionError, match=r"modelo.caminhos_falhou"):
        runner.run(documento, fonte)

    assert not list(runner.cache_directory.glob("*.json"))
    assert _journal(runner, "failed")["error"]


def test_residuo_raster_sozinho_nao_gera_ocorrencia_nem_observacao(tmp_path: Path) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "com.pdf", paginas=1, imagem=True, ct=False))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    composto = runner.run(documento, fonte)

    assert composto.occurrences == ()
    journal = _journal(runner, "completed")
    (cobertura,) = _cobertura_do_novo(journal)
    assert cobertura["status"] == "NAO_DETECCAO"
    assert cobertura["reason"] == "residuo_raster:1"
    (novo,) = [r for r in journal["results"] if r["method_id"] == _METODO_NOVO]
    assert novo["observations"] == []


def test_ct_com_imagem_compacta_ao_lado_mantem_as_ocorrencias_e_conta_o_residuo(
    tmp_path: Path,
) -> None:
    sem, fonte_sem = _fonte(_pdf(tmp_path / "sem.pdf", paginas=1))
    com, fonte_com = _fonte(_pdf(tmp_path / "com.pdf", paginas=1, imagem=True))
    runner_sem = SymbolCompositionRunner(_settings(tmp_path / "dados-sem"))
    runner_com = SymbolCompositionRunner(_settings(tmp_path / "dados-com"))

    composto_sem = runner_sem.run(sem, fonte_sem)
    composto_com = runner_com.run(com, fonte_com)

    assert len(composto_com.occurrences) == len(composto_sem.occurrences) == 1
    (cobertura,) = _cobertura_do_novo(_journal(runner_com, "completed"))
    assert cobertura["status"] == "CONCLUIDO"
    assert "residuo_raster:1" in cobertura["reason"]
    (cobertura_sem,) = _cobertura_do_novo(_journal(runner_sem, "completed"))
    assert "residuo_raster:1" not in cobertura_sem["reason"]


def test_falha_de_fonte_que_nao_e_caminhos_conclui_e_entra_no_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=1))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    def falhar(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("falha de primitivas")

    monkeypatch.setattr(pymupdf_drawing_model, "reconstruir_polilinhas", falhar)

    runner.run(documento, fonte)
    runner.run(documento, fonte)

    primeiro = _journal(runner, "completed")
    assert _journal(runner, "cache_hit")["cache_status"] == "hit"
    (cobertura,) = _cobertura_do_novo(primeiro)
    assert cobertura["status"] == "FORA_DOMINIO"
    assert cobertura["reason"] == "fonte_falhou:modelo.primitivas_falhou"
    (novo,) = [r for r in primeiro["results"] if r["method_id"] == _METODO_NOVO]
    assert novo["observations"] == []
    assert len(list(runner.cache_directory.glob("*.json"))) == 1


def test_raster_de_pagina_girada_nao_muda_por_causa_do_metodo_novo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O método novo roda antes do raster; a página que o raster recebe tem de ser a mesma."""
    from hashlib import sha256

    from zeny_project_handler.adapters.analysis import legacy_symbols, raster_symbols

    pdf = _pdf(tmp_path / "a.pdf", paginas=1)
    with pymupdf.open(pdf) as aberto:
        aberto[0].set_rotation(90)
        aberto.save(tmp_path / "girada.pdf")
    documento, fonte = _fonte(tmp_path / "girada.pdf")
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados", symbol_profile="balanced"))
    if not runner._templates:
        pytest.skip("sem templates raster verificados nesta instalação")
    vistas: dict[str, tuple[int, str, tuple[float, ...]]] = {}

    def instantaneo(page: Any) -> tuple[int, str, tuple[float, ...]]:
        pixmap = page.get_pixmap(dpi=36)
        return page.rotation, sha256(pixmap.samples).hexdigest(), tuple(page.rect)

    original_legado = legacy_symbols.observar_simbolos_legados
    original_raster = raster_symbols.observar_simbolos_raster

    def legado(page: Any, **kwargs: Any) -> Any:
        vistas["antes"] = instantaneo(page)  # nenhum método rodou ainda
        return original_legado(page, **kwargs)

    def raster(page: Any, *args: Any, **kwargs: Any) -> Any:
        vistas["no_raster"] = instantaneo(page)  # o método novo já rodou
        return original_raster(page, *args, **kwargs)

    monkeypatch.setattr(legacy_symbols, "observar_simbolos_legados", legado)
    monkeypatch.setattr(raster_symbols, "observar_simbolos_raster", raster)

    runner.run(documento, fonte)

    assert vistas["antes"][0] == 90
    assert vistas["no_raster"] == vistas["antes"]


@pytest.fixture
def contexto_pipeline(tmp_path: Path, catalogo_inicial: Any) -> Any:
    from datetime import UTC, datetime

    from tests.factories import complete_project

    from zeny_project_handler.adapters.persistence import (
        SqlAlchemyUnitOfWork,
        create_sqlite_engine,
        upgrade_database,
    )
    from zeny_project_handler.domain.analysis import ExecucaoAnalise
    from zeny_project_handler.domain.enums import EstadoExecucaoAnalise

    projeto = complete_project(catalogo_inicial)
    engine = create_sqlite_engine(tmp_path / "pipeline.sqlite3")
    upgrade_database(engine)
    origem = ExecucaoAnalise(
        id=uuid4(),
        projeto_id=projeto.id,
        metodo="fixture-e06",
        versao_metodo="1",
        parametros=(),
        estado=EstadoExecucaoAnalise.CONCLUIDA,
        iniciada_em=datetime(2026, 9, 24, 9, tzinfo=UTC),
        finalizada_em=datetime(2026, 9, 24, 9, 1, tzinfo=UTC),
    )
    with SqlAlchemyUnitOfWork(engine) as work:
        work.catalogos.salvar(catalogo_inicial)
        work.projetos.salvar(projeto)
        work.execucoes_analise.salvar(origem)
        work.commit()
    try:
        yield engine, projeto, origem
    finally:
        engine.dispose()


def _projetar(contexto: Any, composicao: Any) -> Any:
    """Composição -> pipeline de interpretação -> `project_symbol` da única ocorrência."""
    from zeny_project_handler.adapters.interpretation import (
        InterpretadorRegrasExplicitas,
        carregar_registro_regras_inicial,
    )
    from zeny_project_handler.adapters.persistence import SqlAlchemyUnitOfWork
    from zeny_project_handler.application.interpretation_pipeline import (
        ExecutarPipelineInterpretacao,
    )
    from zeny_project_handler_contracts.base import EvidenceId
    from zeny_project_handler_contracts.common import EvidenceNavigationDto
    from zeny_project_handler_server.symbol_review import project_symbol

    engine, projeto, origem = contexto
    composto, documento = composicao
    projeto = replace(projeto, documentos=(documento,))
    with SqlAlchemyUnitOfWork(engine) as work:
        work.projetos.salvar(projeto)
        work.commit()
    registro = carregar_registro_regras_inicial()
    resultado = ExecutarPipelineInterpretacao(
        InterpretadorRegrasExplicitas(registro),
        registro,
        lambda: SqlAlchemyUnitOfWork(engine),
    ).executar(projeto.id, origem.id, simbolos=composto)
    (proposta,) = [
        p
        for p in resultado.elementos
        if dict(p.atributos_sugeridos).get("origem_simbolo_ocorrencia_id")
    ]
    with SqlAlchemyUnitOfWork(engine) as work:
        achadas = (work.evidencias.obter(i) for i in proposta.evidencia_ids)
        evidencias = {e.id: e for e in achadas if e is not None}
    navegacao = tuple(
        EvidenceNavigationDto(
            evidence_id=EvidenceId(e.id), document_id=documento.id, page_id=documento.paginas[0].id
        )
        for e in evidencias.values()
        if e.id in proposta.evidencia_ids
    )
    simbolo = project_symbol(
        proposta, evidencias, navegacao, cast(Any, proposta.situacao_projeto), confirmed=False
    )
    assert simbolo is not None
    return proposta, simbolo


def _compor(
    tmp_path: Path,
    projeto: Any,
    nome: str,
    *,
    sem_novo: bool,
    pacotes: tuple[Any, ...] | None = None,
    calibracao: CalibrationPolicy | None = None,
) -> Any:
    """Roda o runner sobre o PDF do projeto; `sem_novo` reconcilia sem o método novo."""
    from zeny_project_handler.application.symbol_reconciliation import reconcile_symbols

    pdf = _pdf(tmp_path / f"{nome}.pdf", paginas=1)
    documento = replace(
        projeto.documentos[0],
        sha256=PyMuPdfReader().inspecionar(pdf).documento.sha256,
        tamanho_bytes=pdf.stat().st_size,
    )
    fonte = ReferenciaFontePdf(
        documento_id=documento.id,
        projeto_id=projeto.id,
        caminho_canonico=pdf.resolve(),
        sha256=documento.sha256,
        tamanho_bytes=pdf.stat().st_size,
        modificado_em_ns=pdf.stat().st_mtime_ns,
    )
    runner = SymbolCompositionRunner(
        _settings(tmp_path / f"dados-{nome}"), packages=pacotes, calibration=calibracao
    )
    composto = runner.run(documento, fonte)
    if not sem_novo:
        return composto, documento
    agregados = runner._read_cache(documento)
    assert agregados is not None
    filtrados = tuple(r for r in agregados if r.perfil.metodo_id != _METODO_NOVO)
    return reconcile_symbols(filtrados, runner._calibration), documento


def _calibracao_do_motor(pacotes: tuple[Any, ...], classe: str) -> CalibrationPolicy:
    """Uma entrada real, só para o motor declarativo: o método novo não tem célula calibrada."""
    return CalibrationPolicy(
        entries=(
            CalibrationEntry(
                method_signature=declarative_symbols.perfil_pacotes(pacotes).assinatura(),
                class_code=classe,
                stratum="default",
                probability=_PROBABILIDADE,
                sample_size=90,
            ),
        )
    )


def _pacotes_com_ct_de_ativo() -> tuple[Any, ...]:
    """O CT sob uma classe de ativo: nenhuma variante habilitada hoje tem papel de ativo."""
    pacotes = copy.deepcopy(declarative_symbols.carregar_pacotes())
    (variante,) = [v for p in pacotes for v in p["variants"] if v["id"] == _VARIANTE_CT]
    variante["class_code"] = _CLASSE_DE_ATIVO
    return tuple(pacotes)


def _probabilidade(proposta: Any) -> Decimal:
    valor = dict(proposta.atributos_sugeridos).get("simbolo_probabilidade_calibrada")
    assert valor is not None
    return Decimal(str(valor))


def test_caracterizacao_ct_com_o_quinto_metodo_deixa_de_ser_exclusivo(
    tmp_path: Path, contexto_pipeline: Any
) -> None:
    """Comportamento aceito até a E09: um segundo método concordando tira a ocorrência de
    `exclusive`; decisão e probabilidade calibrada não mudam, pois a calibração ainda não usa
    o método novo. Quando a E09 mexer nisso, este teste deve ser revisto, não apagado.

    O CT sintético é a família CAMARA, sem modelo de ativo (papel `desconhecido`): o `status`
    fica `unknown` nos dois casos e só o indicador `exclusive` muda. A troca de status
    `exclusive` para `supported`, com família de papel de ativo, está no teste seguinte.
    """
    _, projeto, _ = contexto_pipeline
    calibracao = _calibracao_do_motor(declarative_symbols.carregar_pacotes(), "CAMARA")
    sem = _compor(tmp_path, projeto, "sem", sem_novo=True, calibracao=calibracao)
    com = _compor(tmp_path, projeto, "com", sem_novo=False, calibracao=calibracao)

    proposta_sem, simbolo_sem = _projetar(contexto_pipeline, sem)
    proposta_com, simbolo_com = _projetar(contexto_pipeline, com)

    assert simbolo_sem.exclusive
    assert not simbolo_com.exclusive
    assert simbolo_sem.status == simbolo_com.status == "unknown"
    assert simbolo_com.symbol_class == simbolo_sem.symbol_class
    attrs_sem = dict(proposta_sem.atributos_sugeridos)
    attrs_com = dict(proposta_com.atributos_sugeridos)
    assert attrs_com["simbolo_decisao_e12"] == attrs_sem["simbolo_decisao_e12"]
    assert _probabilidade(proposta_com) == _probabilidade(proposta_sem) == _PROBABILIDADE


def test_caracterizacao_familia_de_ativo_passa_de_exclusivo_a_suportado(
    tmp_path: Path, contexto_pipeline: Any
) -> None:
    """Comportamento aceito até a E09: com o método novo, o `status` de um ativo vai de "Exclusivo"
    a "Suportado", sem mudar decisão nem probabilidade. Quando a E09 mexer nisso, este teste deve
    ser revisto, não apagado.

    "Suportado" aqui não é corroboração independente: `exclusive` só conta assinaturas distintas
    (`symbol_review.py:54`) e o `status` só lê esse indicador (`symbol_review.py:182`), mas os dois
    métodos aplicam os mesmos pacotes ao mesmo desenho. A probabilidade segue a célula calibrada
    do motor, sem somar o apoio do segundo método (`symbol_reconciliation.py:469-485`).
    """
    _, projeto, _ = contexto_pipeline
    pacotes = _pacotes_com_ct_de_ativo()
    calibracao = _calibracao_do_motor(pacotes, _CLASSE_DE_ATIVO)
    opcoes: dict[str, Any] = {"pacotes": pacotes, "calibracao": calibracao}
    sem = _compor(tmp_path, projeto, "sem", sem_novo=True, **opcoes)
    com = _compor(tmp_path, projeto, "com", sem_novo=False, **opcoes)

    proposta_sem, simbolo_sem = _projetar(contexto_pipeline, sem)
    proposta_com, simbolo_com = _projetar(contexto_pipeline, com)

    assert simbolo_sem.role == simbolo_com.role == "equipamento"
    assert simbolo_sem.exclusive
    assert not simbolo_com.exclusive
    assert _symbol_status(simbolo_sem.status) == "Exclusivo"
    assert _symbol_status(simbolo_com.status) == "Suportado"
    attrs_sem = dict(proposta_sem.atributos_sugeridos)
    attrs_com = dict(proposta_com.atributos_sugeridos)
    assert attrs_sem["simbolo_decisao_e12"] == attrs_com["simbolo_decisao_e12"] == "eligible"
    assert _probabilidade(proposta_com) == _probabilidade(proposta_sem) == _PROBABILIDADE


def test_caracterizacao_variantes_diferentes_na_mesma_caixa_viram_conflitante(
    tmp_path: Path, contexto_pipeline: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Os dois métodos na mesma caixa, cada um com a sua variante, e a classe é a mesma.

    Comportamento aceito até a E09: a referência ambígua manda a ocorrência para revisão, e o
    `status` vira "Conflitante" em vez de "Suportado". O método novo lê aqui um pacote em que o
    id da variante é outro; o desenho e a classe não mudam.
    """
    _, projeto, _ = contexto_pipeline
    pacotes = _pacotes_com_ct_de_ativo()
    outra_id = f"{_VARIANTE_CT}-outra"
    outros = copy.deepcopy(pacotes)
    (variante,) = [v for p in outros for v in p["variants"] if v["id"] == _VARIANTE_CT]
    variante["id"] = outra_id
    original = model_symbols.observar_pacotes_modelo

    def com_outra_variante(*args: Any, **kwargs: Any) -> Any:
        return original(*args, **{**kwargs, "pacotes": outros})

    monkeypatch.setattr(model_symbols, "observar_pacotes_modelo", com_outra_variante)
    composicao = _compor(
        tmp_path,
        projeto,
        "conflito",
        sem_novo=False,
        pacotes=pacotes,
        calibracao=_calibracao_do_motor(pacotes, _CLASSE_DE_ATIVO),
    )

    (ocorrencia,) = composicao[0].occurrences
    assert {o.template for o in ocorrencia.observations} == {_VARIANTE_CT, outra_id}
    assert {a.classe for a in ocorrencia.alternatives} == {_CLASSE_DE_ATIVO}
    assert "ambiguous_reference_id" in ocorrencia.reasons
    assert ocorrencia.decision == "review"
    _, simbolo = _projetar(contexto_pipeline, composicao)
    assert simbolo.role == "equipamento"
    assert _symbol_status(simbolo.status) == "Conflitante"
    assert not simbolo.exclusive


def test_caracterizacao_pagina_que_bate_no_teto_volta_a_exclusivo(
    tmp_path: Path, contexto_pipeline: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem observação do método novo (teto), a ocorrência volta a ter um único método."""
    _, projeto, _ = contexto_pipeline
    monkeypatch.setattr(symbol_execution, "LIMITE_CONSULTAS_PAGINA", 1)
    composto = _compor(tmp_path, projeto, "teto", sem_novo=False)

    _, simbolo = _projetar(contexto_pipeline, composto)

    assert simbolo.exclusive
    assert len(simbolo.methods) == 1


# --- fusão da haste com o legado (R-E06.3.2-3, Review Focus 5) --------------------------------

_PACOTES_REAIS = Path(declarative_symbols.__file__).parent / "symbol_packages"


def _pacotes_com_haste(destino: Path) -> tuple[declarative_symbols.Package, ...]:
    """Cópia dos pacotes reais com as 8 variantes de haste habilitadas (a Task 4 faz no real)."""
    destino.mkdir()
    gramaticas = dict(CASOS_HASTE)
    for caminho in _PACOTES_REAIS.glob("*.json"):
        pacote = json.loads(caminho.read_text(encoding="utf-8"))
        for variante in pacote["variants"]:
            if variante["id"] in gramaticas:
                variante["recognition"] = {
                    "status": "enabled",
                    "grammar": gramaticas[variante["id"]],
                    "negative_examples": variante["recognition"]["negative_examples"],
                }
        (destino / caminho.name).write_text(json.dumps(pacote), encoding="utf-8")
    return declarative_symbols.carregar_pacotes(packages_dir=destino)


def _pdf_de_haste(caminho: Path, variante: str, rotacao: int, linha_longa: float) -> DesenhoHaste:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=300, height=300)
        desenho = desenhar_positivo(pagina, variante, linha_longa=linha_longa)
        pagina.set_rotation(rotacao)
        documento.save(caminho)
    return desenho


def _caixa_do_pictograma(desenho: DesenhoHaste, maior_barra: float) -> tuple[float, ...]:
    """Barras e o trecho da haste até a maior barra, no espaço cru da página."""
    (ax, ay), (bx, by) = desenho.ponta, desenho.base
    vao = math.dist((ax, ay), (bx, by))
    fim = (ax + (bx - ax) / vao * maior_barra, ay + (by - ay) / vao * maior_barra)
    pontos = [desenho.ponta, fim, *(p for barra in desenho.barras for p in barra)]
    xs, ys = [p[0] for p in pontos], [p[1] for p in pontos]
    return (min(xs), min(ys), max(xs), max(ys))


@pytest.mark.parametrize(
    ("variante", "rotacao", "linha_longa"),
    [
        ("cemig-eo-r3-s19-v001", 0, 0.0),
        ("cemig-eo-r3-s19-v001", 0, 60.0),
        ("cemig-eo-r3-s19-v004", 0, 0.0),
        ("cemig-eo-r3-s19-v001", 90, 0.0),
    ],
    ids=["haste-curta", "haste-na-linha-longa", "x-sem-envolvente", "rotate-90"],
)
def test_haste_funde_com_o_legado(
    tmp_path: Path, variante: str, rotacao: int, linha_longa: float
) -> None:
    desenho = _pdf_de_haste(tmp_path / "h.pdf", variante, rotacao, linha_longa)
    documento, fonte = _fonte(tmp_path / "h.pdf")
    pacotes = _pacotes_com_haste(tmp_path / "pacotes")
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"), packages=pacotes)
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()

    composto = runner.run(documento, fonte)

    com_o_novo = [
        o
        for o in composto.occurrences
        if any(obs.metodo_assinatura == novo for obs in o.observations)
    ]
    assert len(com_o_novo) == 1
    (ocorrencia,) = com_o_novo
    assert len({obs.metodo_assinatura for obs in ocorrencia.observations}) >= 2
    assert {alt.classe for alt in ocorrencia.alternatives} == {"ATERRAMENTO"}
    esperado = _caixa_do_pictograma(desenho, max(DECRESCENTES))
    xs = [float(x) for x, _ in ocorrencia.geometry.pontos_originais]
    ys = [float(y) for _, y in ocorrencia.geometry.pontos_originais]
    assert (min(xs), min(ys), max(xs), max(ys)) == pytest.approx(esperado, abs=0.5)
    assert ocorrencia.support_geometry is not None
