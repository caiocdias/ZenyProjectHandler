# mypy: disable-error-code="no-untyped-call"
"""Ataques ao ``--processos`` dos scripts de corpus: ordem, erros, pools e normalização."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, ClassVar

import pytest
from scripts import benchmark_texto_ficha, drawing_model_report
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    pdf_texto_nativo,
    tabela_do_alfabeto,
)
from tests.unit.test_benchmark_texto_ficha_processos import _referencia
from tests.unit.test_benchmark_texto_ficha_processos import (
    _sem_medidas_do_processo as _normalizar_benchmark,
)
from tests.unit.test_drawing_model_report import _pdf_completo, _repo
from tests.unit.test_drawing_model_report_processos import (
    _sem_medidas_do_processo as _normalizar_report,
)

_RAIZ = Path(__file__).resolve().parents[2]


class _PoolEspiao(ProcessPoolExecutor):
    """Registra construção, ``max_workers`` e o ``shutdown`` (fechamento) de cada pool."""

    criados: ClassVar[list[_PoolEspiao]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.max_workers_pedido = kwargs.get("max_workers")
        self.fechado = False
        _PoolEspiao.criados.append(self)

    def shutdown(self, *args: Any, **kwargs: Any) -> None:
        super().shutdown(*args, **kwargs)
        self.fechado = True


@pytest.fixture
def pools(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[_PoolEspiao]]:
    _PoolEspiao.criados = []
    monkeypatch.setattr(benchmark_texto_ficha, "ProcessPoolExecutor", _PoolEspiao)
    monkeypatch.setattr(drawing_model_report, "ProcessPoolExecutor", _PoolEspiao)
    yield _PoolEspiao.criados
    _PoolEspiao.criados = []


def _diferencas(a: Any, b: Any, caminho: str = "") -> Iterator[str]:
    """Caminhos onde dois JSON de mesma forma têm valores diferentes."""
    if isinstance(a, dict) and isinstance(b, dict):
        assert a.keys() == b.keys()
        for chave in a:
            yield from _diferencas(a[chave], b[chave], f"{caminho}/{chave}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b)
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            yield from _diferencas(x, y, f"{caminho}[{i}]")
    elif a != b:
        yield caminho


# ------------------------------------------------------------ benchmark_texto_ficha

_Corpus = tuple[Path, Path, Path]


def _corpus_benchmark(raiz: Path, quantidade: int, *, primeira_pesada: bool = False) -> _Corpus:
    raiz.mkdir(parents=True, exist_ok=True)
    tabela_do_alfabeto(raiz)
    pdfs = raiz / "pdfs-origem"
    pdfs.mkdir()
    rodada = raiz / "rodada"
    for indice in range(quantidade):
        linhas = [
            LinhaTexto("P7", (40.0 + indice, 60.0), 5.0),
            LinhaTexto("11-300", (40.0, 120.0 + indice), 5.0),
        ]
        if primeira_pesada and indice == 0:
            linhas += [LinhaTexto("N1 N2 P7", (10.0, 10.0 + 3 * k), 2.0) for k in range(60)]
        escrever = pdf_texto_contorno if indice % 2 else pdf_texto_nativo
        pdf = escrever(pdfs / f"folha-{indice}.pdf", linhas)
        _referencia(rodada, f"{indice + 1:03d}-{chr(97 + indice) * 12}", pdf)
    return rodada, pdfs, raiz / "tabela-alfabeto.json"


def _bench(base: _Corpus, saida: Path, *extras: str) -> int:
    rodada, pdfs, tabela = base
    return benchmark_texto_ficha.main(
        [
            *["--rodada", str(rodada), "--pdfs", str(pdfs), "--saida", str(saida)],
            *["--tabela", str(tabela), *extras],
        ]
    )


def test_benchmark_ordem_segue_a_entrada_mesmo_com_o_primeiro_pdf_mais_lento(
    tmp_path: Path,
) -> None:
    base = _corpus_benchmark(tmp_path, 4, primeira_pesada=True)

    assert _bench(base, tmp_path / "p", "--processos", "4") == 0

    dados = json.loads((tmp_path / "p" / "texto-ficha.json").read_text(encoding="utf-8"))
    ids = list(dados["por_pdf"])
    assert len(ids) == 4
    assert ids == sorted(ids)


def test_benchmark_um_unico_pdf_ou_processos_1_nao_abre_pool(
    tmp_path: Path, pools: list[_PoolEspiao]
) -> None:
    unico = _corpus_benchmark(tmp_path / "u", 1)
    varios = _corpus_benchmark(tmp_path / "v", 3)

    assert _bench(unico, tmp_path / "s1", "--processos", "4") == 0
    assert _bench(varios, tmp_path / "s2", "--processos", "1") == 0
    assert _bench(varios, tmp_path / "s3") == 0

    assert pools == []


def test_benchmark_pool_limita_workers_ao_numero_de_pdfs_e_fecha(
    tmp_path: Path, pools: list[_PoolEspiao]
) -> None:
    base = _corpus_benchmark(tmp_path, 3)

    assert _bench(base, tmp_path / "s", "--processos", "16") == 0

    assert [p.max_workers_pedido for p in pools] == [3]
    assert all(p.fechado for p in pools)


def test_benchmark_pdf_ilegivel_levanta_o_mesmo_erro_da_serial_e_o_pool_fecha(
    tmp_path: Path, pools: list[_PoolEspiao]
) -> None:
    base = _corpus_benchmark(tmp_path, 3)
    rodada, pdfs, _ = base
    corrompido = sorted(pdfs.glob("*.pdf"))[1]
    corrompido.write_bytes(b"isto nao e um pdf")
    ficha = sorted(rodada.rglob("referencia.json"))[1]
    dados = json.loads(ficha.read_text(encoding="utf-8"))
    dados["pdf_sha256"] = hashlib.sha256(corrompido.read_bytes()).hexdigest()
    ficha.write_text(json.dumps(dados), encoding="utf-8")

    with pytest.raises(Exception) as serial:
        _bench(base, tmp_path / "serial")
    with pytest.raises(Exception) as paralelo:
        _bench(base, tmp_path / "paralelo", "--processos", "3")

    assert type(paralelo.value) is type(serial.value)
    assert pools
    assert all(p.fechado for p in pools)


def test_benchmark_tabela_invalida_falha_no_processo_principal_sem_abrir_pool(
    tmp_path: Path, pools: list[_PoolEspiao]
) -> None:
    base = _corpus_benchmark(tmp_path, 3)
    base[2].write_text("{isto nao e json", encoding="utf-8")

    with pytest.raises(ValueError):
        _bench(base, tmp_path / "serial")
    with pytest.raises(ValueError):
        _bench(base, tmp_path / "paralelo", "--processos", "4")

    assert pools == []
    assert not (tmp_path / "paralelo").exists()


@pytest.mark.parametrize("valor", ["abc", "1.5", ""], ids=["texto", "fracao", "vazio"])
def test_benchmark_processos_nao_inteiro_sai_com_2(
    tmp_path: Path, valor: str, capsys: pytest.CaptureFixture[str]
) -> None:
    base = _corpus_benchmark(tmp_path, 2)

    with pytest.raises(SystemExit) as saida:
        _bench(base, tmp_path / "s", "--processos", valor)

    assert saida.value.code == 2
    assert "--processos" in capsys.readouterr().err


def test_benchmark_executar_direto_com_processos_igual_ao_serial(tmp_path: Path) -> None:
    rodada, pdfs, tabela = _corpus_benchmark(tmp_path, 3)

    serial = benchmark_texto_ficha.executar(rodada, pdfs, tmp_path / "a", tabela)
    paralelo = benchmark_texto_ficha.executar(rodada, pdfs, tmp_path / "b", tabela, 2)

    assert list(paralelo["por_pdf"]) == list(serial["por_pdf"])
    assert _normalizar_benchmark(json.dumps(paralelo)) == _normalizar_benchmark(json.dumps(serial))


def test_benchmark_normalizacao_so_apaga_chaves_de_medida(tmp_path: Path) -> None:
    base = _corpus_benchmark(tmp_path, 3)
    assert _bench(base, tmp_path / "s") == 0
    bruto = (tmp_path / "s" / "texto-ficha.json").read_text(encoding="utf-8")

    alterados = list(_diferencas(json.loads(bruto), json.loads(_normalizar_benchmark(bruto))))

    assert alterados, "a normalização não tocou em nada: o teste não prova nada"
    assert all(re.search(r"/(tempo_[a-z_]*s|pico_memoria_bytes)$", c) for c in alterados), alterados


def test_normalizacao_nao_mascara_campo_de_leitura_alterado() -> None:
    a = '{"tempo_s": 1.5, "acertos": 3, "texto": "P7"}'
    mudou_numero = '{"tempo_s": 9.25, "acertos": 4, "texto": "P7"}'
    mudou_texto = '{"tempo_s": 9.25, "acertos": 3, "texto": "P1"}'

    for normalizar in (_normalizar_benchmark, _normalizar_report):
        assert normalizar(a) != normalizar(mudou_numero)
        assert normalizar(a) != normalizar(mudou_texto)
        assert normalizar(a) == normalizar(a.replace("1.5", "7.125"))


# ------------------------------------------------------------ drawing_model_report


def _corpus_report(pasta: Path, nomes: tuple[str, ...]) -> Path:
    pasta.mkdir(parents=True)
    for nome in nomes:
        if nome.endswith("inv.pdf"):
            (pasta / nome).write_bytes(b"isto nao e um pdf")
        else:
            _pdf_completo(pasta / nome)
    return pasta


def _report(pasta: Path, repo: Path, nome: str, *extras: str) -> int:
    return drawing_model_report.main(
        [
            *["--raiz", str(pasta), "--saida", str(repo / "tmp" / nome / "r.json")],
            *["--raiz-repositorio", str(repo), *extras],
        ]
    )


def _json_report(repo: Path, nome: str) -> str:
    return (repo / "tmp" / nome / "r.json").read_text(encoding="utf-8")


def test_report_pdfs_invalidos_nos_extremos_nao_deslocam_as_amostras(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    pasta = _corpus_report(tmp_path / "pdfs", ("0-inv.pdf", "a.pdf", "b.pdf", "z-inv.pdf"))
    for nome, extras in (("s", ()), ("p", ("--processos", "3"))):
        imagens = str(repo / "tmp" / nome / "i")
        assert _report(pasta, repo, nome, "--amostras-imagem", imagens, *extras) == 0

    assert _normalizar_report(_json_report(repo, "p")) == _normalizar_report(
        _json_report(repo, "s")
    )
    assert sum("erro" in p for p in json.loads(_json_report(repo, "p"))["pdfs"]) == 2
    nomes_serial = {p.name: p.read_bytes() for p in (repo / "tmp" / "s" / "i").iterdir()}
    assert nomes_serial
    assert {p.name: p.read_bytes() for p in (repo / "tmp" / "p" / "i").iterdir()} == nomes_serial


def test_report_so_invalidos_com_processos_gera_so_erros(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    pasta = _corpus_report(tmp_path / "pdfs", ("1-inv.pdf", "2-inv.pdf", "3-inv.pdf"))

    assert _report(pasta, repo, "p", "--processos", "2") == 0

    pdfs = json.loads(_json_report(repo, "p"))["pdfs"]
    assert len(pdfs) == 3
    assert all(set(p) == {"sha256", "erro"} for p in pdfs)


def test_report_um_pdf_ou_processos_1_nao_abre_pool(
    tmp_path: Path, pools: list[_PoolEspiao]
) -> None:
    repo = _repo(tmp_path)
    unico = _corpus_report(tmp_path / "um", ("a.pdf",))
    tres = _corpus_report(tmp_path / "tres", ("a.pdf", "b.pdf", "c.pdf"))

    assert _report(unico, repo, "u", "--processos", "4") == 0
    assert _report(tres, repo, "t1", "--processos", "1") == 0
    assert _report(tres, repo, "t2") == 0

    assert pools == []


def test_report_pool_limita_workers_ao_numero_de_pdfs_e_fecha(
    tmp_path: Path, pools: list[_PoolEspiao]
) -> None:
    repo = _repo(tmp_path)
    pasta = _corpus_report(tmp_path / "pdfs", ("a.pdf", "b.pdf", "c.pdf"))

    assert _report(pasta, repo, "p", "--processos", "16") == 0

    assert [p.max_workers_pedido for p in pools] == [3]
    assert all(p.fechado for p in pools)


def test_report_tabela_invalida_sai_com_2_sem_abrir_pool_nem_gravar(
    tmp_path: Path,
    pools: list[_PoolEspiao],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    pasta = _corpus_report(tmp_path / "pdfs", ("a.pdf", "b.pdf"))

    def tabela_quebrada(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("tabela de glifos invalida")

    monkeypatch.setattr(drawing_model_report, "carregar_tabela_glifos", tabela_quebrada)

    assert _report(pasta, repo, "p", "--processos", "4") == 2

    assert "tabela de glifos invalida" in capsys.readouterr().err
    assert pools == []
    assert not (repo / "tmp" / "p" / "r.json").exists()


@pytest.mark.parametrize("valor", ["abc", "2.5"], ids=["texto", "fracao"])
def test_report_processos_nao_inteiro_sai_com_2(
    tmp_path: Path, valor: str, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    pasta = _corpus_report(tmp_path / "pdfs", ("a.pdf",))

    with pytest.raises(SystemExit) as saida:
        _report(pasta, repo, "p", "--processos", valor)

    assert saida.value.code == 2
    assert "--processos" in capsys.readouterr().err


def test_report_normalizacao_so_apaga_medidas_e_deixa_a_leitura(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    pasta = _corpus_report(tmp_path / "pdfs", ("a.pdf", "b.pdf"))
    assert _report(pasta, repo, "s") == 0
    bruto = _json_report(repo, "s")

    alterados = list(_diferencas(json.loads(bruto), json.loads(_normalizar_report(bruto))))

    assert len(alterados) == 4  # tempo_s e pico_memoria_bytes de cada um dos 2 PDFs
    assert all(re.search(r"/(tempo_s|pico_memoria_bytes)$", c) for c in alterados), alterados


def test_report_cli_real_com_processos_funciona_via_spawn(tmp_path: Path) -> None:
    """Executa ``python -m scripts.drawing_model_report`` de verdade (guarda de ``__main__``)."""
    repo = _repo(tmp_path)
    pasta = _corpus_report(tmp_path / "pdfs", ("a.pdf", "b.pdf", "x-inv.pdf"))
    saida = repo / "tmp" / "cli" / "r.json"

    resultado = subprocess.run(
        [
            *[sys.executable, "-m", "scripts.drawing_model_report", "--raiz", str(pasta)],
            *["--saida", str(saida), "--raiz-repositorio", str(repo), "--processos", "2"],
        ],
        cwd=_RAIZ,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr[-2000:]
    assert json.loads(saida.read_text(encoding="utf-8"))["resumo"]["pdfs"] == 3
