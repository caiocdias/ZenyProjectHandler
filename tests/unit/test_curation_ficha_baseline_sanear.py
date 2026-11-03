"""Ataques ao saneamento do erro de falha do ``baseline``: o resumo não vaza caminho nem nome."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import scripts.curation_ficha as curation_ficha
from scripts.curation_ficha import main
from scripts.curation_round import carregar_rodada, iniciar_rodada
from tests.pdf_fixtures import create_network_benchmark_pdf
from tests.unit.test_benchmark_ficha_poste import _referencia_sintetica
from tests.unit.test_curation_ficha_baseline import _argv, _congelar_referencia, _resumo

AGORA = "2026-10-15T12:00:00+00:00"
Mensagem = Callable[[Path], str]

MENSAGENS: dict[str, Mensagem] = {
    "caminho_completo": lambda pdf: f"nao abriu {pdf}",
    "barras_posix": lambda pdf: f"nao abriu {pdf.as_posix()}",
    "barras_invertidas_duplas": lambda pdf: f"nao abriu {str(pdf).replace(chr(92), chr(92) * 2)}",
    "repr_do_caminho": lambda pdf: f"[Errno 2] No such file: {str(pdf)!r}",
    "aspas_com_nome": lambda pdf: f'arquivo "{pdf.name}" corrompido',
    "so_nome": lambda pdf: f"falha em {pdf.name}",
    "nome_sem_extensao": lambda pdf: f"falha em {pdf.stem}",
    "caixa_diferente": lambda pdf: f"falha em {pdf.name.upper()}",
    "dentro_de_outra_palavra": lambda pdf: f"x{pdf.stem}y e prefixo{pdf}",
    "relativo": lambda pdf: f"falha em ..\\corpus\\{pdf.name} e ./corpus/{pdf.name}",
    "unc": lambda pdf: f"falha em \\\\servidor\\share\\{pdf.name}",
    "unc_barras_normais": lambda pdf: f"falha em //servidor/share/{pdf.name}",
    "diretorio_da_rodada": lambda pdf: f"sem espaco em {pdf.parent.parent / 'rodada'}",
}


def _montar(tmp_path: Path, nome: str) -> tuple[Path, str, Path]:
    (tmp_path / "corpus").mkdir()
    pdf = create_network_benchmark_pdf(tmp_path / "corpus" / nome)
    rodada_dir = tmp_path / "rodada"
    iniciar_rodada(
        rodada_dir,
        tmp_path / "corpus",
        concorrencia=3,
        raiz_repositorio=tmp_path / "sem-git",
        agora=AGORA,
    )
    pdf_id = str(carregar_rodada(rodada_dir)["pdfs"][0]["pdf_id"])
    _congelar_referencia(
        rodada_dir, pdf_id, _referencia_sintetica(sha256(pdf.read_bytes()).hexdigest())
    )
    return rodada_dir, pdf_id, pdf


def _falhar_com(monkeypatch: pytest.MonkeyPatch, construir: Mensagem) -> None:
    def quebra(pdf: Path, *_: Any, **__: Any) -> None:
        raise RuntimeError(construir(pdf.resolve()))

    monkeypatch.setattr(curation_ficha, "executar_benchmark", quebra)


@pytest.mark.parametrize("chave", sorted(MENSAGENS))
@pytest.mark.parametrize("nome", ["rede-secreta.pdf", "A+B(1)[x]$.pdf", "nome com espaco.pdf"])
def test_baseline_falha_nao_vaza_caminho_nem_nome_do_pdf_no_json_nem_no_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chave: str, nome: str
) -> None:
    rodada_dir, pdf_id, pdf = _montar(tmp_path, nome)
    _falhar_com(monkeypatch, MENSAGENS[chave])
    assert main(_argv(rodada_dir, "--native-only")) == 1
    bloco = _resumo(rodada_dir, "baseline-v001")["por_pdf"][pdf_id]
    assert bloco["situacao"] == "falha" and bloco["erro"]
    for sufixo in ("json", "md"):
        texto = (rodada_dir / "fichas" / f"baseline-v001-resumo.{sufixo}").read_text("utf-8")
        assert pdf.name.lower() not in texto.lower()
        assert pdf.stem.lower() not in texto.lower()
        assert str(tmp_path) not in texto
        assert str(tmp_path).replace("\\", "\\\\") not in texto
        assert tmp_path.as_posix() not in texto


@pytest.mark.parametrize(
    "chave", ["caminho_completo", "so_nome", "aspas_com_nome", "repr_do_caminho"]
)
def test_baseline_falha_com_nome_curto_de_pdf_nao_vaza_o_nome_com_extensao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, chave: str
) -> None:
    rodada_dir, pdf_id, _ = _montar(tmp_path, "ab.pdf")
    _falhar_com(monkeypatch, MENSAGENS[chave])
    assert main(_argv(rodada_dir, "--native-only")) == 1
    erro = _resumo(rodada_dir, "baseline-v001")["por_pdf"][pdf_id]["erro"]
    assert "ab.pdf" not in erro.lower()
    assert str(tmp_path) not in erro


def test_baseline_falha_com_nome_curto_sem_extensao_vaza_por_desenho(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Documenta o limite: stem < 4 caracteres não é trocado (evita corromper a mensagem)."""
    rodada_dir, pdf_id, _ = _montar(tmp_path, "ab.pdf")
    _falhar_com(monkeypatch, lambda pdf: f"falha em {pdf.stem}")
    assert main(_argv(rodada_dir, "--native-only")) == 1
    assert _resumo(rodada_dir, "baseline-v001")["por_pdf"][pdf_id]["erro"] == "falha em ab"
