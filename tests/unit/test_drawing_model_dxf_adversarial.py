# mypy: disable-error-code="no-untyped-call"
"""Testes adversariais do DXF de depuração (Task 5, E04). Só PDFs sintéticos gerados aqui."""

from __future__ import annotations

import ast
import math
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest
from ezdxf.filemanagement import readfile
from scripts import drawing_model_dxf
from scripts.drawing_model_dxf import exportar_dxf, main

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Estilo,
    GrupoCandidato,
    ModeloDesenho,
    PaginaModelo,
    PerfilFamilia,
    Polilinha,
)

_RAIZ_SRC = Path(__file__).resolve().parents[2] / "src"


def _estilo(camada: str) -> Estilo:
    return Estilo(camada=camada, cor=None, preenchimento=None, espessura=1.0, tracejado="")


def _pagina(
    *,
    primitivas: tuple[Polilinha | Arco, ...] = (),
    grupos: tuple[GrupoCandidato, ...] = (),
) -> PaginaModelo:
    return PaginaModelo(
        indice=0, largura=100.0, altura=100.0, caminhos=(), textos=(), primitivas=primitivas,
        grupos=grupos, imagens=(), diagnosticos=(),
    )  # fmt: skip


def _modelo(pagina: PaginaModelo) -> ModeloDesenho:
    return ModeloDesenho(
        versao="t",
        documento_sha256="0" * 64,
        familia=PerfilFamilia(familia="x", sinais=(), diagnosticos=()),
        paginas=(pagina,),
    )


def _linha(camada: str) -> Polilinha:
    return Polilinha(
        pontos=((0.0, 0.0), (5.0, 5.0)), fechada=False, estilo=_estilo(camada), origens=(0,)
    )


def _arco(inicial: float, final: float) -> Arco:
    return Arco(
        centro=(50.0, 60.0), raio=5.0, angulo_inicial=inicial, angulo_final=final,
        estilo=_estilo("A"), origens=(0,),
    )  # fmt: skip


def _pdf(
    caminho: Path,
    desenhar: Callable[[pymupdf.Page], None],
    *,
    largura: int = 200,
    altura: int = 100,
) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=largura, height=altura)
        desenhar(pagina)
        documento.save(caminho)
    return caminho


def _circulo(pagina: pymupdf.Page) -> None:
    pagina.draw_circle((10, 10), 3)


def _rodar(pdf: Path, raiz: Path, saida: Path, *extra: str) -> int:
    return main([str(pdf), "--saida", str(saida), *extra, "--raiz-repositorio", str(raiz)])


def test_texto_rotacionado_anti_horario_sai_com_rotacao_dxf_90_e_y_invertido(
    tmp_path: Path,
) -> None:
    pdf = _pdf(
        tmp_path / "r.pdf",
        lambda p: p.insert_text((50, 60), "ABC", fontsize=10, fontname="helv", rotate=90),
    )
    destino = tmp_path / "tmp" / "r.dxf"

    assert _rodar(pdf, tmp_path, destino) == 0

    texto = readfile(destino).modelspace().query("TEXT").first
    assert texto is not None
    assert texto.dxf.rotation % 360 == pytest.approx(90.0)
    assert texto.dxf.align_point.x == pytest.approx(45.6, abs=1.0)
    assert texto.dxf.align_point.y == pytest.approx(100 - 49.7, abs=1.0)


def test_pagina_com_rotate_usa_dimensoes_e_posicao_visuais(tmp_path: Path) -> None:
    def desenhar(p: pymupdf.Page) -> None:
        p.draw_circle((30, 20), 5)
        p.set_rotation(90)

    pdf = _pdf(tmp_path / "rot.pdf", desenhar)
    destino = tmp_path / "tmp" / "rot.dxf"

    assert _rodar(pdf, tmp_path, destino) == 0

    circulo = readfile(destino).modelspace().query("CIRCLE").first
    assert circulo is not None
    assert circulo.dxf.center.x == pytest.approx(80.0, abs=0.5)
    assert circulo.dxf.center.y == pytest.approx(200 - 30.0, abs=0.5)


def test_pagina_vazia_gera_dxf_valido_sem_entidades(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "v.pdf", lambda p: None)
    destino = tmp_path / "tmp" / "v.dxf"

    assert _rodar(pdf, tmp_path, destino) == 0

    assert len(readfile(destino).modelspace()) == 0


def test_varias_paginas_pagina_n_exporta_so_a_pagina_pedida(tmp_path: Path) -> None:
    pdf = tmp_path / "m.pdf"
    with pymupdf.open() as documento:
        documento.new_page(width=100, height=100).draw_circle((10, 10), 3)
        segunda = documento.new_page(width=100, height=100)
        segunda.draw_circle((70, 30), 4)
        segunda.draw_circle((80, 80), 4)
        documento.save(pdf)
    p0, p1 = tmp_path / "tmp" / "p0.dxf", tmp_path / "tmp" / "p1.dxf"

    assert _rodar(pdf, tmp_path, p0) == 0
    assert _rodar(pdf, tmp_path, p1, "--pagina", "1") == 0

    assert len(readfile(p0).modelspace().query("CIRCLE")) == 1
    assert len(readfile(p1).modelspace().query("CIRCLE")) == 2


def test_pagina_inexistente_devolve_2_sem_criar_arquivo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pdf = _pdf(tmp_path / "a.pdf", _circulo)
    saida = tmp_path / "tmp" / "x.dxf"

    assert _rodar(pdf, tmp_path, saida, "--pagina", "1") == 2
    assert not saida.exists()
    assert "pagina" in capsys.readouterr().err


def test_pagina_negativa_devolve_2_sem_criar_arquivo(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "a.pdf", _circulo)
    saida = tmp_path / "tmp" / "x.dxf"

    assert _rodar(pdf, tmp_path, saida, "--pagina", "-1") == 2
    assert not saida.exists()


def test_pdf_inexistente_devolve_2_sem_criar_arquivo(tmp_path: Path) -> None:
    saida = tmp_path / "tmp" / "x.dxf"

    assert _rodar(tmp_path / "nao.pdf", tmp_path, saida) == 2
    assert not saida.exists()


def test_nome_de_camada_vazio_ou_de_espacos_vira_zero() -> None:
    assert drawing_model_dxf.nome_de_camada("") == "0"
    assert drawing_model_dxf.nome_de_camada("   ") == "0"


def test_camada_vazia_na_primitiva_vai_para_camada_zero(tmp_path: Path) -> None:
    destino = tmp_path / "z.dxf"

    exportar_dxf(_modelo(_pagina(primitivas=(_linha(""),))), 0, destino)

    linha = readfile(destino).modelspace().query("LWPOLYLINE").first
    assert linha is not None
    assert linha.dxf.layer == "0"


def test_camadas_que_colidem_apos_saneamento_continuam_distintas(tmp_path: Path) -> None:
    destino = tmp_path / "col.dxf"
    modelo = _modelo(_pagina(primitivas=(_linha("A/B"), _linha("A:B"))))

    exportar_dxf(modelo, 0, destino)

    camadas = [e.dxf.layer for e in readfile(destino).modelspace().query("LWPOLYLINE")]
    assert len(camadas) == 2
    assert camadas[0] != camadas[1], "A/B e A:B foram fundidas na mesma camada DXF"


def test_camada_do_pdf_chamada_grupos_candidatos_nao_se_mistura_com_a_dos_grupos(
    tmp_path: Path,
) -> None:
    destino = tmp_path / "g.dxf"
    grupo = GrupoCandidato(
        bbox=(1.0, 2.0, 30.0, 40.0), indices_primitivas=(0,), indices_caminhos=()
    )
    modelo = _modelo(_pagina(primitivas=(_linha("GRUPOS_CANDIDATOS"),), grupos=(grupo,)))

    exportar_dxf(modelo, 0, destino)

    entidades = readfile(destino).modelspace().query("LWPOLYLINE")
    abertas = {e.dxf.layer for e in entidades if not e.dxf.flags & 1}
    fechadas = {e.dxf.layer for e in entidades if e.dxf.flags & 1}
    assert abertas.isdisjoint(fechadas)


def test_nome_de_camada_longo_e_saneado_e_gera_dxf_legivel(tmp_path: Path) -> None:
    destino = tmp_path / "l.dxf"

    exportar_dxf(_modelo(_pagina(primitivas=(_linha("X" * 400),))), 0, destino)

    linha = readfile(destino).modelspace().query("LWPOLYLINE").first
    assert linha is not None
    assert 0 < len(linha.dxf.layer) <= 255


def test_dois_grupos_geram_dois_retangulos_com_coordenadas_invertidas(tmp_path: Path) -> None:
    destino = tmp_path / "gg.dxf"
    grupos = (
        GrupoCandidato(bbox=(10.0, 20.0, 30.0, 40.0), indices_primitivas=(), indices_caminhos=()),
        GrupoCandidato(bbox=(50.0, 60.0, 70.0, 90.0), indices_primitivas=(), indices_caminhos=()),
    )

    exportar_dxf(_modelo(_pagina(grupos=grupos)), 0, destino)

    retangulos = readfile(destino).modelspace().query('LWPOLYLINE[layer=="GRUPOS_CANDIDATOS"]')
    assert len(retangulos) == 2
    caixas = set()
    for r in retangulos:
        xs = [p[0] for p in r.get_points()]  # type: ignore[attr-defined]
        ys = [p[1] for p in r.get_points()]  # type: ignore[attr-defined]
        assert len(xs) == 4
        caixas.add((min(xs), min(ys), max(xs), max(ys)))
    assert caixas == {(10.0, 60.0, 30.0, 80.0), (50.0, 10.0, 70.0, 40.0)}


@pytest.mark.parametrize(
    ("inicial", "final", "esperado"),
    [
        (0.0, 90.0, (270.0, 0.0)),
        (90.0, 180.0, (180.0, 270.0)),
        (300.0, 60.0, (300.0, 60.0)),
    ],
)
def test_arco_em_posicao_conhecida_sai_com_angulos_e_centro_corretos(
    tmp_path: Path, inicial: float, final: float, esperado: tuple[float, float]
) -> None:
    destino = tmp_path / "arc.dxf"

    exportar_dxf(_modelo(_pagina(primitivas=(_arco(inicial, final),))), 0, destino)

    arco = readfile(destino).modelspace().query("ARC").first
    assert arco is not None
    assert (arco.dxf.center.x, arco.dxf.center.y) == pytest.approx((50.0, 40.0))
    assert math.isclose(arco.dxf.start_angle % 360, esperado[0], abs_tol=1e-9)
    assert math.isclose(arco.dxf.end_angle % 360, esperado[1], abs_tol=1e-9)


def test_dxf_nao_traz_caminho_absoluto_nem_nome_do_pdf(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "segredo_nome.pdf", _circulo)
    destino = tmp_path / "tmp" / "o.dxf"

    assert _rodar(pdf, tmp_path, destino) == 0

    conteudo = destino.read_text(encoding="utf-8", errors="replace")
    assert "segredo_nome" not in conteudo
    assert str(tmp_path) not in conteudo


def test_saida_absoluta_fora_de_tmp_e_recusada(tmp_path: Path) -> None:
    raiz = tmp_path / "repo"
    (raiz / "tmp").mkdir(parents=True)
    pdf = _pdf(tmp_path / "a.pdf", _circulo)
    fora = tmp_path / "outro" / "x.dxf"

    assert _rodar(pdf, raiz, fora) == 2
    assert not fora.parent.exists()


def test_saida_em_diretorio_irmao_com_prefixo_de_tmp_e_recusada(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "a.pdf", _circulo)
    parecido = tmp_path / "tmp_extra" / "x.dxf"

    assert _rodar(pdf, tmp_path, parecido) == 2
    assert not parecido.exists()


def test_saida_com_ponto_ponto_duplo_escapando_e_recusada(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "a.pdf", _circulo)

    assert _rodar(pdf, tmp_path, tmp_path / "tmp" / ".." / ".." / "x.dxf") == 2


def test_cache_com_ponto_ponto_fora_de_tmp_e_recusado(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "a.pdf", _circulo)
    saida = tmp_path / "tmp" / "x.dxf"

    codigo = _rodar(pdf, tmp_path, saida, "--cache", str(tmp_path / "tmp" / ".." / "cache"))

    assert codigo == 2
    assert not (tmp_path / "cache").exists()
    assert not saida.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="junção NTFS")
def test_juncao_dentro_de_tmp_apontando_para_fora_e_recusada(tmp_path: Path) -> None:
    raiz = tmp_path / "repo"
    (raiz / "tmp").mkdir(parents=True)
    alvo_fora = tmp_path / "fora"
    alvo_fora.mkdir()
    juncao = raiz / "tmp" / "atalho"
    resultado = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(juncao), str(alvo_fora)],
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode != 0:
        pytest.skip(f"junção indisponível: {resultado.stdout}{resultado.stderr}")
    pdf = _pdf(tmp_path / "a.pdf", _circulo)

    codigo_saida = _rodar(pdf, raiz, juncao / "x.dxf")
    codigo_cache = _rodar(pdf, raiz, raiz / "tmp" / "ok.dxf", "--cache", str(juncao / "c"))

    assert codigo_saida == 2
    assert codigo_cache == 2
    assert list(alvo_fora.iterdir()) == []


def test_segunda_chamada_usa_o_cache_sem_reextrair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf", _circulo)
    cache = ("--cache", str(tmp_path / "tmp" / "cache"))
    assert _rodar(pdf, tmp_path, tmp_path / "tmp" / "1.dxf", *cache) == 0

    def _proibido(*_args: object, **_kwargs: object) -> ModeloDesenho:
        raise AssertionError("o PDF foi reextraido apesar do cache")

    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", _proibido)

    assert _rodar(pdf, tmp_path, tmp_path / "tmp" / "2.dxf", *cache) == 0
    assert len(readfile(tmp_path / "tmp" / "2.dxf").modelspace().query("CIRCLE")) == 1


def test_cache_nao_e_criado_quando_nao_pedido(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "a.pdf", _circulo)

    assert _rodar(pdf, tmp_path, tmp_path / "tmp" / "1.dxf") == 0

    assert sorted(f.name for f in (tmp_path / "tmp").iterdir()) == ["1.dxf"]


def test_arquivo_que_nao_e_pdf_devolve_2_sem_traceback(tmp_path: Path) -> None:
    lixo = tmp_path / "lixo.pdf"
    lixo.write_bytes(b"isto nao e um pdf")
    saida = tmp_path / "tmp" / "x.dxf"

    assert _rodar(lixo, tmp_path, saida) == 2
    assert not saida.exists()


def test_ezdxf_nunca_e_importado_em_src() -> None:
    ofensores: list[str] = []
    for arquivo in _RAIZ_SRC.rglob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            nomes: list[str] = []
            if isinstance(no, ast.Import):
                nomes = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module:
                nomes = [no.module]
            if any(n == "ezdxf" or n.startswith("ezdxf.") for n in nomes):
                ofensores.append(str(arquivo))
    assert ofensores == []


def _camadas_por_ordem(tmp_path: Path, nomes: list[str], nome_arquivo: str = "k.dxf") -> list[str]:
    destino = tmp_path / nome_arquivo
    exportar_dxf(_modelo(_pagina(primitivas=tuple(_linha(n) for n in nomes))), 0, destino)
    return [e.dxf.layer for e in readfile(destino).modelspace().query("LWPOLYLINE")]


def test_tres_nomes_colidentes_ficam_distintos_e_o_primeiro_mantem_o_nome_saneado(
    tmp_path: Path,
) -> None:
    camadas = _camadas_por_ordem(tmp_path, ["A/B", "A:B", "A*B"])

    assert len(set(camadas)) == 3
    assert camadas[0] == "A_B"
    assert all(c.startswith("A_B_") for c in camadas[1:])


def test_sufixo_e_deterministico_entre_execucoes_e_independe_do_processo(
    tmp_path: Path,
) -> None:
    primeira = _camadas_por_ordem(tmp_path, ["A/B", "A:B"], "1.dxf")
    segunda = _camadas_por_ordem(tmp_path, ["A/B", "A:B"], "2.dxf")
    saida = subprocess.run(
        [
            sys.executable,
            "-c",
            "from scripts.drawing_model_dxf import _Camadas;"
            "from ezdxf.filemanagement import new;"
            "c=_Camadas(new('R2010'));print(c('A/B'), c('A:B'))",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
        env={**__import__("os").environ, "PYTHONHASHSEED": "12345"},
    )

    assert primeira == segunda
    assert saida.stdout.split() == primeira


def test_mesmo_nome_original_repetido_reutiliza_a_mesma_camada(tmp_path: Path) -> None:
    camadas = _camadas_por_ordem(tmp_path, ["A/B", "A:B", "A:B", "A/B"])

    assert camadas[1] == camadas[2]
    assert camadas[0] == camadas[3]
    assert camadas[0] != camadas[1]


def test_sufixo_que_gera_nova_colisao_ainda_resulta_em_camadas_distintas(tmp_path: Path) -> None:
    sufixado = _camadas_por_ordem(tmp_path, ["A_B", "A/B"], "s.dxf")[1]
    assert sufixado != "A_B"

    camadas = _camadas_por_ordem(tmp_path, ["A_B", "A/B", sufixado], "t.dxf")

    assert len({c.casefold() for c in camadas}) == 3


def test_colisao_que_so_difere_por_caixa_fica_distinta(tmp_path: Path) -> None:
    camadas = _camadas_por_ordem(tmp_path, ["rede", "REDE"])

    assert len({c.casefold() for c in camadas}) == 2


def test_nome_longo_colidente_respeita_limite_de_255_caracteres(tmp_path: Path) -> None:
    camadas = _camadas_por_ordem(tmp_path, ["X" * 300, "X" * 301])

    assert len(set(camadas)) == 2
    assert all(0 < len(c) <= 255 for c in camadas)


def test_camada_literal_grupos_candidatos_em_caixa_diferente_nao_se_mistura(
    tmp_path: Path,
) -> None:
    destino = tmp_path / "gc.dxf"
    grupo = GrupoCandidato(bbox=(1.0, 2.0, 3.0, 4.0), indices_primitivas=(), indices_caminhos=())
    modelo = _modelo(_pagina(primitivas=(_linha("grupos_candidatos"),), grupos=(grupo,)))

    exportar_dxf(modelo, 0, destino)

    ents = list(readfile(destino).modelspace().query("LWPOLYLINE"))
    fechadas = {e.dxf.layer.casefold() for e in ents if e.dxf.flags & 1}
    abertas = {e.dxf.layer.casefold() for e in ents if not e.dxf.flags & 1}
    assert fechadas == {"grupos_candidatos"}
    assert abertas.isdisjoint(fechadas)


def test_arquivo_vazio_devolve_2_sem_gravar(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio.pdf"
    vazio.write_bytes(b"")
    saida = tmp_path / "tmp" / "x.dxf"

    assert _rodar(vazio, tmp_path, saida) == 2
    assert not saida.exists()


def test_pdf_truncado_devolve_2_sem_gravar_e_sem_traceback(tmp_path: Path) -> None:
    inteiro = _pdf(tmp_path / "ok.pdf", _circulo).read_bytes()
    truncado = tmp_path / "trunc.pdf"
    truncado.write_bytes(inteiro[: len(inteiro) // 3])
    saida = tmp_path / "tmp" / "x.dxf"

    assert _rodar(truncado, tmp_path, saida) == 2
    assert not saida.exists()


def test_nao_pdf_com_cache_nao_cria_entrada_no_cache(tmp_path: Path) -> None:
    lixo = tmp_path / "lixo.pdf"
    lixo.write_bytes(b"isto nao e um pdf")
    cache = tmp_path / "tmp" / "cache"

    assert _rodar(lixo, tmp_path, tmp_path / "tmp" / "x.dxf", "--cache", str(cache)) == 2
    assert not any(cache.rglob("*.json")) if cache.exists() else True
