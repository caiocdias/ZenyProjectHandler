"""Ataque ao corpus do benchmark de símbolos: guarda cega, saneamento, pool e cobertura."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar

import pytest
import scripts.benchmark_simbolos_ficha as bench
import scripts.simbolos_corpus as corpus
from scripts.curation_round import RodadaError

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import CoberturaMetodoSimbolos, FonteObservacaoSimbolo
from zeny_project_handler.domain.values import PontoNormalizado

_ACEITOS = {EstadoMetodoSimbolos.CONCLUIDO, EstadoMetodoSimbolos.NAO_DETECCAO}

# --- guarda do conjunto cego -------------------------------------------------------------

_VARIANTES_CEGAS = [
    "avaliacao-cega",
    "AVALIACAO-CEGA",
    "Avaliacao-Cega",
    "avaliacao-cega.",
    "avaliacao-cega ",
    "avaliacao-cega:fluxo",
    "pdfs\\avaliacao-cega\\x.pdf",
    "pdfs/avaliacao-cega/x.pdf",
    "a//avaliacao-cega//x.pdf",
    "a\\/avaliacao-cega",
]


@pytest.mark.parametrize("caminho", _VARIANTES_CEGAS)
def test_caminho_cego_detecta_variantes(caminho: str) -> None:
    assert corpus._caminho_cego(caminho) is True


def test_caminho_cego_detecta_em_qualquer_argumento() -> None:
    assert corpus._caminho_cego("a", "b/c", "x\\avaliacao-cega") is True


@pytest.mark.parametrize(
    "caminho",
    ["", "avaliacao-cega-2", "x-avaliacao-cega", "avaliacao", "avaliacao_cega", "a/b/c.pdf"],
)
def test_caminho_cego_nao_pega_nome_parecido(caminho: str) -> None:
    assert corpus._caminho_cego(caminho) is False


def test_caminho_cego_e_publico_no_corpus() -> None:
    """O brief da tarefa define ``caminho_cego`` como interface pública do módulo."""
    modulo = importlib.import_module("scripts.simbolos_corpus")
    assert callable(getattr(modulo, "caminho_cego", None))


@pytest.mark.parametrize(
    "parte",
    [
        "avaliacao-cega",
        "AVALIACAO-CEGA",
        "avaliacao-cega.",
        "avaliacao-cega:x",
        "sub\\avaliacao-cega",
        "sub/avaliacao-cega/fundo",
    ],
)
def test_recusar_rodada_cega_recusa_variantes_antes_de_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, parte: str
) -> None:
    def proibido(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("I/O antes da recusa")

    monkeypatch.setattr(Path, "is_file", proibido)
    monkeypatch.setattr(Path, "read_text", proibido)
    monkeypatch.setattr(Path, "exists", proibido)
    monkeypatch.setattr(Path, "open", proibido)
    alvo = Path(str(tmp_path) + "/" + parte)
    with pytest.raises(RodadaError, match="avaliacao-cega"):
        corpus.recusar_rodada_cega(alvo)


def test_recusar_rodada_cega_recusa_componente_no_meio_relativo() -> None:
    with pytest.raises(RodadaError):
        corpus.recusar_rodada_cega(Path("rodadas") / "avaliacao-cega" / "r1")


def test_recusar_rodada_cega_recusa_rodada_relativa_dentro_da_cega(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "avaliacao-cega").mkdir()
    monkeypatch.chdir(tmp_path / "avaliacao-cega")
    with pytest.raises(RodadaError):
        corpus.recusar_rodada_cega(Path("."))
    with pytest.raises(RodadaError):
        corpus.recusar_rodada_cega(Path("sub") / "..")


def test_recusar_rodada_cega_recusa_unc() -> None:
    with pytest.raises(RodadaError):
        corpus.recusar_rodada_cega(Path(r"\\servidor\share\avaliacao-cega\r1"))


def test_recusar_rodada_cega_aceita_rodada_comum(tmp_path: Path) -> None:
    corpus.recusar_rodada_cega(tmp_path / "rodada-1")
    corpus.recusar_rodada_cega(Path("rodada-relativa"))


def test_recusar_rodada_cega_nao_cria_nem_le_nada(tmp_path: Path) -> None:
    alvo = tmp_path / "avaliacao-cega"
    with pytest.raises(RodadaError):
        corpus.recusar_rodada_cega(alvo)
    assert not alvo.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("raiz", "relativo"),
    [
        ("avaliacao-cega", "x.pdf"),
        ("corpus", "avaliacao-cega/x.pdf"),
        ("corpus", "avaliacao-cega\\x.pdf"),
        ("corpus", "AVALIACAO-CEGA/x.pdf"),
        ("corpus", "sub/../avaliacao-cega/x.pdf"),
        ("corpus/avaliacao-cega.", "x.pdf"),
        ("..", "avaliacao-cega/x.pdf"),
        ("corpus", "avaliacao-cega:alt/x.pdf"),
        ("C:\\dados\\avaliacao-cega", "x.pdf"),
    ],
)
def test_localizar_pdf_recusa_sem_tocar_o_disco(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raiz: str, relativo: str
) -> None:
    def proibido(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("I/O antes da recusa")

    monkeypatch.setattr(Path, "is_file", proibido)
    monkeypatch.setattr(Path, "exists", proibido)
    monkeypatch.setattr(Path, "resolve", proibido)
    with pytest.raises(corpus.FolhaError, match="avaliacao-cega"):
        corpus.localizar_pdf(tmp_path, raiz, relativo)


def test_localizar_pdf_recusa_rodada_dentro_da_pasta_cega(tmp_path: Path) -> None:
    with pytest.raises(corpus.FolhaError):
        corpus.localizar_pdf(tmp_path / "avaliacao-cega" / "r", "corpus", "x.pdf")


def test_localizar_pdf_recusa_unc_cego() -> None:
    with pytest.raises(corpus.FolhaError):
        corpus.localizar_pdf(Path("r"), r"\\srv\share\avaliacao-cega", "x.pdf")


def test_localizar_pdf_devolve_caminho_composto_para_caso_comum(tmp_path: Path) -> None:
    esperado = tmp_path / "corpus" / "a" / "b.pdf"
    assert corpus.localizar_pdf(tmp_path, "corpus", "a/b.pdf") == esperado


def test_mensagem_da_recusa_nao_vaza_caminho_nem_nome_de_pdf(tmp_path: Path) -> None:
    with pytest.raises(corpus.FolhaError) as info:
        corpus.localizar_pdf(tmp_path, "corpus", "avaliacao-cega/segredo-cliente.pdf")
    assert "segredo-cliente" not in str(info.value)
    assert str(tmp_path) not in str(info.value)
    with pytest.raises(RodadaError) as info2:
        corpus.recusar_rodada_cega(tmp_path / "avaliacao-cega" / "segredo")
    assert "segredo" not in str(info2.value)
    assert str(tmp_path) not in str(info2.value)


# --- saneamento --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bruto", "proibidos"),
    [
        ("falhou em C:\\Users\\Caio\\Meus Docs\\cliente secreto.pdf agora", ["Caio", "secreto"]),
        ("erro c:/dados/cliente/projeto final.pdf", ["dados", "projeto final"]),
        ("erro \\\\srv\\share\\pasta\\x.pdf", ["srv", "share", "x.pdf"]),
        ("erro \\\\?\\C:\\a\\b\\c.pdf", ["\\a\\", "c.pdf"]),
        ("erro /home/caio/cliente/obra.pdf", ["caio", "obra"]),
        ("erro obra-secreta.PDF solto", ["obra-secreta"]),
        ("linha1 ok\nC:\\segredo\\a.pdf", ["segredo"]),
        ("erro: 'cliente-x.pdf' inválido", ["cliente-x"]),
    ],
)
def test_sanear_direto_nao_vaza_caminho_nem_pdf(bruto: str, proibidos: list[str]) -> None:
    saida = corpus.sanear(bruto)
    for item in proibidos:
        assert item not in saida, saida


def test_sanear_so_primeira_linha_nao_vazia() -> None:
    assert corpus.sanear("\n\n  primeira\nsegunda C:\\x\\y.pdf") == "primeira"


def test_sanear_limita_tamanho() -> None:
    assert len(corpus.sanear("a" * 5000)) == corpus.LIMITE_ERRO


def test_sanear_oculta_trecho_conhecido_sem_caixa_e_mais_longo_primeiro() -> None:
    saida = corpus.sanear("falha RODADA-Sub-a e rodada", ["rodada", "RODADA-Sub", ""])
    assert saida == "falha <oculto>-a e <oculto>"


def test_sanear_vazio() -> None:
    assert corpus.sanear("") == ""


# --- pool --------------------------------------------------------------------------------


class _PoolFalso:
    """Executor síncrono: ``pool.map`` com ordem preservada."""

    criados: ClassVar[list[int]] = []

    def __init__(self, max_workers: int) -> None:
        type(self).criados.append(max_workers)

    def __enter__(self) -> _PoolFalso:
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def map(self, funcao: Callable[[Any], Any], tarefas: Any) -> Any:
        return map(funcao, tarefas)


class _PoolQuebraNoTerceiro(_PoolFalso):
    def map(self, funcao: Callable[[Any], Any], tarefas: Any) -> Any:
        def gerador() -> Any:
            for indice, tarefa in enumerate(tarefas):
                if indice == 2:
                    raise BrokenProcessPool("morreu")
                yield funcao(tarefa)

        return gerador()


class _PoolQuebraNaEntrada(_PoolFalso):
    def __enter__(self) -> _PoolFalso:
        raise BrokenProcessPool("x")


class _PoolProibido:
    def __init__(self, *_a: object, **_k: object) -> None:
        raise AssertionError("executor criado")


def _eco(tarefa: Any) -> dict[str, Any]:
    return {"situacao": "ok", "tarefa": tarefa}


def test_medir_em_paralelo_mantem_a_ordem() -> None:
    _PoolFalso.criados = []
    saida = corpus.medir_em_paralelo(_eco, [5, 3, 9, 1], 3, _PoolFalso)  # type: ignore[arg-type]
    assert [item["tarefa"] for item in saida] == [5, 3, 9, 1]
    assert _PoolFalso.criados == [3]


@pytest.mark.parametrize(("efetivos", "tarefas"), [(1, [1, 2, 3]), (0, [1, 2]), (4, [7]), (4, [])])
def test_medir_em_paralelo_serial_nao_cria_executor(efetivos: int, tarefas: list[int]) -> None:
    saida = corpus.medir_em_paralelo(_eco, tarefas, efetivos, _PoolProibido)  # type: ignore[arg-type]
    assert [item["tarefa"] for item in saida] == tarefas


def test_medir_em_paralelo_pool_quebrado_completa_com_falhas_na_ordem() -> None:
    saida = corpus.medir_em_paralelo(
        _eco,
        [10, 11, 12, 13, 14],
        2,
        _PoolQuebraNoTerceiro,  # type: ignore[arg-type]
    )
    assert len(saida) == 5
    assert [item["tarefa"] for item in saida[:2]] == [10, 11]
    assert all(item["situacao"] == "falha" for item in saida[2:])
    assert all("pool" in item["erro"] for item in saida[2:])


def test_medir_em_paralelo_pool_quebrado_na_entrada_falha_todas() -> None:
    saida = corpus.medir_em_paralelo(_eco, [1, 2, 3], 2, _PoolQuebraNaEntrada)  # type: ignore[arg-type]
    assert [item["situacao"] for item in saida] == ["falha"] * 3


def test_medir_em_paralelo_propaga_excecao_que_nao_e_pool_quebrado() -> None:
    def explode(_t: Any) -> dict[str, Any]:
        raise KeyError("x")

    with pytest.raises(KeyError):
        corpus.medir_em_paralelo(explode, [1, 2], 2, _PoolFalso)  # type: ignore[arg-type]


def test_medir_todas_do_benchmark_usa_o_executor_do_modulo_bench(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _PoolFalso.criados = []
    monkeypatch.setattr(bench, "ProcessPoolExecutor", _PoolFalso)
    monkeypatch.setattr(bench, "_medir_folha", _eco)
    saida = bench._medir_todas([1, 2], 2)  # type: ignore[list-item]
    assert _PoolFalso.criados == [2]
    assert [item["tarefa"] for item in saida] == [1, 2]


def test_executor_padrao_e_process_pool_executor() -> None:
    assert bench.ProcessPoolExecutor is ProcessPoolExecutor  # type: ignore[attr-defined]


# --- falha_da_cobertura ------------------------------------------------------------------


def _cobertura(estado: EstadoMetodoSimbolos, motivo: str | None) -> CoberturaMetodoSimbolos:
    return CoberturaMetodoSimbolos(
        fonte=FonteObservacaoSimbolo(
            documento_id="doc", documento_sha256="0" * 64, pagina_numero=1, camada="c"
        ),
        regiao_normalizada=(PontoNormalizado(Decimal("0.1"), Decimal("0.1")),),
        classes_avaliadas=("poste",),
        estado=estado,
        motivo=motivo,
    )


def test_falha_da_cobertura_tem_sete_estados() -> None:
    assert len(list(EstadoMetodoSimbolos)) == 7


@pytest.mark.parametrize("estado", sorted(_ACEITOS, key=str), ids=str)
def test_falha_da_cobertura_estado_aceito_sem_motivo_nao_e_falha(
    estado: EstadoMetodoSimbolos,
) -> None:
    assert corpus.falha_da_cobertura(_cobertura(estado, None)) is None


@pytest.mark.parametrize("estado", list(EstadoMetodoSimbolos), ids=lambda e: e.value)
def test_falha_da_cobertura_com_motivo_so_falha_fora_da_lista_branca(
    estado: EstadoMetodoSimbolos,
) -> None:
    esperado = None if estado in _ACEITOS else "porque sim"
    assert corpus.falha_da_cobertura(_cobertura(estado, "porque sim")) == esperado


# --- compatibilidade dos nomes antigos ---------------------------------------------------


@pytest.mark.parametrize(
    "nome",
    [
        "COMPONENTE_CEGO",
        "LIMITE_ERRO",
        "FolhaError",
        "_FolhaError",
        "_componentes",
        "sanear",
        "localizar_pdf",
        "CONTEXTOS_NAO_DESENHO",
        "RAIO_POSTE_PENDENTE",
        "TOLERANCIA_CENTRO",
        "avaliar_predicoes",
        "casar",
        "classes_da_ficha",
        "ProcessPoolExecutor",
        "_medir_todas",
        "_medir_folha",
        "medir_simbolos",
        "main",
        "medir_pdf",
        "_markdown",
        "_agregar_total",
        "_agregar_comparacao",
        "_agregar_por_familia",
        "_simbolos_validos",
    ],
)
def test_nomes_antigos_continuam_no_benchmark(nome: str) -> None:
    assert hasattr(bench, nome), nome


def test_aliases_do_benchmark_sao_os_mesmos_objetos_do_corpus() -> None:
    assert bench._FolhaError is corpus.FolhaError
    assert bench.FolhaError is corpus.FolhaError
    assert bench.sanear is corpus.sanear
    assert bench.localizar_pdf is corpus.localizar_pdf
