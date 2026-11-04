"""Recall de texto por campo da ficha: contagem por instância e CLI sobre PDFs sintéticos."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from scripts.benchmark_texto_ficha import TextoMedido, main, recall_texto
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    pdf_texto_contorno,
    pdf_texto_nativo,
    tabela_do_alfabeto,
)

_SHA = "b" * 64


def _poste(
    identificador: str | None = None,
    *,
    poste: str | None = None,
    estruturas: Sequence[str] = (),
    coordenada: dict[str, Any] | None = None,
    pendentes: Sequence[str] = (),
    centro: tuple[float, float] = (0.5, 0.5),
    pagina: int = 1,
) -> dict[str, Any]:
    x, y = centro
    return {
        "id": f"P{abs(hash((identificador, poste, centro)))}",
        "pagina": pagina,
        "bbox": [x - 0.005, y - 0.005, x + 0.005, y + 0.005],
        "identificador": identificador,
        "estruturas": list(estruturas),
        "poste": poste,
        "coordenada": coordenada,
        "simbolos": [],
        "pendentes": list(pendentes),
    }


def _ref(*postes: dict[str, Any]) -> dict[str, Any]:
    return {"postes": list(postes)}


def _texto(
    texto: str, centro: tuple[float, float] = (0.5, 0.52), origem: str = "nativo"
) -> TextoMedido:
    return TextoMedido(texto, centro, origem)  # type: ignore[arg-type]


def test_um_texto_serve_a_uma_instancia() -> None:
    ref = _ref(
        _poste(estruturas=["N1"], centro=(0.2, 0.2)), _poste(estruturas=["N1"], centro=(0.8, 0.8))
    )
    r = recall_texto(ref, [_texto("N1", (0.21, 0.2))])
    assert r["estruturas"] == {"total": 2, "acertos": 1, "erros_afirmados": 0}


def test_valor_nao_casa_dentro_de_outro_token() -> None:
    r = recall_texto(_ref(_poste(poste="P1")), [_texto("P10")])
    assert r["poste"]["acertos"] == 0
    assert r["poste"]["total"] == 1


def test_valor_com_espaco_e_normalizacao() -> None:
    r = recall_texto(_ref(_poste(poste="dt 11/300")), [_texto("x  DT   11/300 y")])
    assert r["poste"]["acertos"] == 1


def test_coordenada_casa_leste_e_norte() -> None:
    coordenada = {"leste": 612345, "norte": 7801234.5, "zona": "23K"}
    r = recall_texto(
        _ref(_poste(coordenada=coordenada)), [_texto("E=612345"), _texto("N=7801234.5")]
    )
    assert r["coordenada"] == {"total": 2, "acertos": 2, "erros_afirmados": 0}


def test_coordenada_inteira_em_float_casa_sem_ponto_zero() -> None:
    coordenada = {"leste": 612345.0, "norte": 7801234.0, "zona": "23K"}
    r = recall_texto(_ref(_poste(coordenada=coordenada)), [_texto("E=612345 N=7801234")])
    assert r["coordenada"]["acertos"] == 2


def test_pendente_e_nulo_nao_contam() -> None:
    ref = _ref(
        _poste("123", pendentes=["identificador"]),
        _poste(None, poste=None, estruturas=[]),
        _poste(coordenada={"leste": 1, "norte": 2, "zona": "23K"}, pendentes=["coordenada"]),
    )
    r = recall_texto(ref, [])
    assert all(campo["total"] == 0 for campo in r.values())


def test_pendente_de_estruturas_nao_conta() -> None:
    r = recall_texto(_ref(_poste(estruturas=["N1"], pendentes=["estruturas"])), [])
    assert r["estruturas"]["total"] == 0


def test_erro_afirmado_por_troca_de_caractere() -> None:
    r = recall_texto(_ref(_poste(poste="11-300")), [_texto("11-30O", (0.5, 0.51))])
    assert r["poste"] == {"total": 1, "acertos": 0, "erros_afirmados": 1}


def test_erro_afirmado_por_fusao_de_tokens() -> None:
    r = recall_texto(_ref(_poste(estruturas=["N4"])), [_texto("N42", (0.5, 0.51))])
    assert r["estruturas"] == {"total": 1, "acertos": 0, "erros_afirmados": 1}


def test_texto_longe_ou_diferente_demais_nao_e_erro_afirmado() -> None:
    longe = recall_texto(_ref(_poste(poste="11-300")), [_texto("11-30O", (0.9, 0.9))])
    outro = recall_texto(_ref(_poste(poste="11-300")), [_texto("ABCDEF", (0.5, 0.51))])
    assert longe["poste"]["erros_afirmados"] == 0
    assert outro["poste"]["erros_afirmados"] == 0


def test_acerto_nao_e_erro_afirmado_nem_consome_token_alheio() -> None:
    ref = _ref(_poste(estruturas=["N1", "N2"]))
    r = recall_texto(ref, [_texto("N2", (0.5, 0.51))])
    assert r["estruturas"] == {"total": 2, "acertos": 1, "erros_afirmados": 0}


def _tabela_e_pdfs(tmp_path: Path) -> tuple[Path, Path, Path]:
    tabela = tabela_do_alfabeto(tmp_path)
    arquivo = tmp_path / "tabela-alfabeto.json"
    assert arquivo.is_file() and tabela.sha256
    linhas = [
        LinhaTexto("P7", (40.0, 60.0), 5.0),
        LinhaTexto("11-300", (40.0, 120.0), 5.0),
    ]
    pdfs = tmp_path / "pdfs-origem"
    pdfs.mkdir()
    nativo = pdf_texto_nativo(pdfs / "nome-secreto-nativo.pdf", linhas)
    contorno = pdf_texto_contorno(pdfs / "nome-secreto-contorno.pdf", linhas)
    return arquivo, nativo, contorno


def _referencia(rodada: Path, pdf_id: str, pdf: Path) -> None:
    pasta = rodada / "pdfs" / pdf_id / "ficha"
    pasta.mkdir(parents=True)
    poste = _poste(poste="P7", estruturas=["11-300"], centro=(0.10, 0.30))
    poste["id"] = "P1"
    ficha = {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "escopo_anotacao": {"tipo": "completo"},
        "postes": [poste],
        "vaos": [],
    }
    (pasta / "referencia.json").write_text(json.dumps(ficha), encoding="utf-8")


def test_cli_contorno_tem_base_zero_e_novo_positivo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tabela, nativo, contorno = _tabela_e_pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    _referencia(rodada, "002-bbbbbbbbbbbb", contorno)
    saida = tmp_path / "saida"
    codigo = main(
        [
            "--rodada",
            str(rodada),
            "--pdfs",
            str(nativo.parent),
            "--saida",
            str(saida),
            "--tabela",
            str(tabela),
        ]
    )
    assert codigo == 0
    texto_json = (saida / "texto-ficha.json").read_text(encoding="utf-8")
    texto_md = (saida / "texto-ficha.md").read_text(encoding="utf-8")
    dados = json.loads(texto_json)
    nativo_r = dados["por_pdf"]["001-aaaaaaaaaaaa"]["fontes"]
    contorno_r = dados["por_pdf"]["002-bbbbbbbbbbbb"]["fontes"]
    assert sum(c["acertos"] for c in nativo_r["base"].values()) > 0
    assert sum(c["acertos"] for c in contorno_r["base"].values()) == 0
    assert sum(c["acertos"] for c in contorno_r["novo"].values()) > 0
    assert dados["total"]["novo"]["poste"]["total"] == 2
    assert dados["versao_analisador"] == "1.21.0"
    assert len(dados["tabela_sha256"]) == 64
    assert "tempo_glifos_s" in dados["por_pdf"]["002-bbbbbbbbbbbb"]
    assert set(dados["por_familia"]) == {dados["por_pdf"][i]["familia"] for i in dados["por_pdf"]}
    for conteudo in (texto_json, texto_md, capsys.readouterr().out):
        assert str(tmp_path) not in conteudo
        assert "nome-secreto" not in conteudo


def test_cli_recusa_referencia_sem_pdf_correspondente(tmp_path: Path) -> None:
    tabela, nativo, _ = _tabela_e_pdfs(tmp_path)
    rodada = tmp_path / "rodada"
    _referencia(rodada, "001-aaaaaaaaaaaa", nativo)
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    with pytest.raises(ValueError, match="001-aaaaaaaaaaaa"):
        main(
            [
                "--rodada",
                str(rodada),
                "--pdfs",
                str(vazio),
                "--saida",
                str(tmp_path / "s"),
                "--tabela",
                str(tabela),
            ]
        )
