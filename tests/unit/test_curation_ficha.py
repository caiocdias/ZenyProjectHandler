from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts.curation_ficha import (
    LEITORES,
    carregar_congelada,
    congelar_leitura,
    diretorio_ficha,
    erros_leitura,
    main,
)
from scripts.curation_reference import tiles_nao_cobertos
from scripts.curation_render import ParametrosRender, carregar_indice, renderizar
from scripts.curation_round import (
    carregar_rodada,
    escrever_json_atomico,
    hash_arquivo,
    iniciar_rodada,
)

AGORA = "2026-10-15T12:00:00+00:00"
Registro = dict[str, Any]
# 1 pt = 1 px, tiles de 256 px com 38 px de sobreposição: grade 3 x 4 numa página A4.
RAPIDO = ParametrosRender(lado_tile_px=256, sobreposicao=0.15, dpi_detalhe=72)
LARGURA, ALTURA = 595.0, 842.0
REGIAO_C = (90.0, 40.0, 125.0, 70.0)
REGIAO_CONFERENCIA = (50.0, 20.0, 200.0, 120.0)


def _norm(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    return [x0 / LARGURA, y0 / ALTURA, x1 / LARGURA, y1 / ALTURA]


def _retangulo(x0: float, y0: float, x1: float, y1: float) -> pymupdf.Rect:
    return pymupdf.Rect(x0, y0, x1, y1)  # type: ignore[no-untyped-call]


def _criar_pdf(caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=LARGURA, height=ALTURA)
        pagina.draw_rect(_retangulo(100, 50, 110, 60), color=(0, 0, 0), fill=(0, 0, 0))
        pagina.draw_line((300, 400), (340, 400), color=(0, 0, 0), width=1)
        pagina.add_rect_annot(_retangulo(400, 600, 440, 640))
        documento.save(caminho)


@pytest.fixture(scope="module")
def modelo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    base = tmp_path_factory.mktemp("modelo-ficha")
    _criar_pdf(base / "corpus" / "a.pdf")
    rodada = base / "rodada"
    iniciar_rodada(
        rodada, base / "corpus", concorrencia=3, raiz_repositorio=base / "sem-git", agora=AGORA
    )
    pdf_id = str(carregar_rodada(rodada)["pdfs"][0]["pdf_id"])
    resultado = renderizar(rodada, [pdf_id], parametros=RAPIDO, jobs=1)
    assert resultado["totais"]["sucesso"] == 1
    return base, pdf_id


@pytest.fixture
def rodada(modelo: tuple[Path, str], tmp_path: Path) -> tuple[Path, str]:
    base, pdf_id = modelo
    copia = tmp_path / "base"
    shutil.copytree(base, copia)
    return copia / "rodada", pdf_id


def _tiles_a_revisar(indice: Registro) -> list[str]:
    return [str(t["id"]) for t in indice["tiles"] if t["estado"] == "a_revisar"]


def _tiles_que_cobrem(indice: Registro, bbox: list[float]) -> list[str]:
    return [
        str(t["id"])
        for t in indice["tiles"]
        if t["bbox"][0] <= bbox[0]
        and t["bbox"][1] <= bbox[1]
        and bbox[2] <= t["bbox"][2]
        and bbox[3] <= t["bbox"][3]
    ]


def _poste(identidade: str = "p1") -> Registro:
    return {
        "id": identidade,
        "pagina": 1,
        "bbox": _norm(100, 50, 110, 60),
        "identificador": "P1",
        "estruturas": [],
        "poste": None,
        "coordenada": None,
        "simbolos": [],
        "pendentes": [],
    }


def _ficha(
    rodada_dir: Path,
    pdf_id: str,
    leitor: str,
    *,
    escopo: Registro | None = None,
    tiles: list[str] | None = None,
    ilegiveis: list[Registro] | None = None,
) -> Registro:
    indice = carregar_indice(rodada_dir, pdf_id)
    return {
        "schema_version": 1,
        "tipo": "referencia",
        "pdf_sha256": indice["sha256_pdf"],
        "escopo_anotacao": escopo or {"tipo": "completo"},
        "postes": [_poste()],
        "vaos": [],
        "atributos_extras": {
            "leitura": {
                "leitor": leitor,
                "modelo": "modelo-sintetico",
                "origem": "revisao_ia",
                "tiles_revisados": (
                    tiles if tiles is not None else [str(t["id"]) for t in indice["tiles"]]
                ),
                "regioes_ilegiveis": ilegiveis or [],
            }
        },
    }


def _ficha_regional(rodada_dir: Path, pdf_id: str, leitor: str) -> Registro:
    indice = carregar_indice(rodada_dir, pdf_id)
    regiao = _norm(*REGIAO_C)
    return _ficha(
        rodada_dir,
        pdf_id,
        leitor,
        escopo={"tipo": "regional", "regioes": [{"pagina": 1, "bbox": regiao}]},
        tiles=_tiles_que_cobrem(indice, regiao),
    )


def _gravar_conferencia(rodada_dir: Path, pdf_id: str) -> None:
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    escrever_json_atomico(
        pasta / "regioes-conferencia.json",
        {
            "schema_version": "curadoria-ficha-regioes-v1",
            "pdf_id": pdf_id,
            "regioes": [{"id": "r001", "pagina": 1, "bbox": _norm(*REGIAO_CONFERENCIA)}],
        },
    )


def _rascunho(rodada_dir: Path, pdf_id: str, leitor: str, ficha: Registro) -> Path:
    arquivo = diretorio_ficha(rodada_dir, pdf_id) / f"rascunho-{leitor}" / "ficha.json"
    escrever_json_atomico(arquivo, ficha)
    return arquivo


def _tile_base_a_revisar(indice: Registro) -> Registro:
    return next(t for t in indice["tiles"] if t["estado"] == "a_revisar" and t["camada"] == "base")


def test_leitores_sao_a_b_e_c() -> None:
    assert LEITORES == ("a", "b", "c")


def test_tiles_nao_cobertos_lista_o_tile_nao_revisado_nem_ilegivel(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    alvo = _tile_base_a_revisar(indice)
    revisados = [i for i in _tiles_a_revisar(indice) if i != alvo["id"]]
    assert tiles_nao_cobertos(indice, revisados, []) != []
    assert alvo["id"] in tiles_nao_cobertos(indice, revisados, [])
    assert alvo["id"] not in tiles_nao_cobertos(
        indice, revisados, [(alvo["pagina"], alvo["camada"], alvo["bbox"])]
    )
    assert tiles_nao_cobertos(indice, _tiles_a_revisar(indice), []) == []


def test_validar_aceita_leitura_a_completa(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    assert erros_leitura(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a")) == []
    assert erros_leitura(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b")) == []


def test_validar_recusa_escopo_regional_para_a_e_b(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    for leitor in ("a", "b"):
        erros = erros_leitura(
            rodada_dir, pdf_id, leitor, _ficha_regional(rodada_dir, pdf_id, leitor)
        )
        assert any("escopo" in e for e in erros), erros


def test_validar_recusa_completo_com_tile_a_revisar_nao_coberto(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    alvo = _tile_base_a_revisar(indice)
    revisados = [str(t["id"]) for t in indice["tiles"] if t["id"] != alvo["id"]]
    ficha = _ficha(rodada_dir, pdf_id, "a", tiles=revisados)
    erros = erros_leitura(rodada_dir, pdf_id, "a", ficha)
    assert any(str(alvo["id"]) in e for e in erros), erros

    ficha["atributos_extras"]["leitura"]["regioes_ilegiveis"] = [
        {
            "pagina": alvo["pagina"],
            "camada": alvo["camada"],
            "bbox": alvo["bbox"],
            "motivo": "região ilegível no tile",
        }
    ]
    assert erros_leitura(rodada_dir, pdf_id, "a", ficha) == []


def test_validar_recusa_sha_de_outro_pdf(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha(rodada_dir, pdf_id, "a")
    ficha["pdf_sha256"] = "0" * 64
    erros = erros_leitura(rodada_dir, pdf_id, "a", ficha)
    assert any("pdf_sha256" in e for e in erros), erros


def test_validar_recusa_tile_inexistente(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha(rodada_dir, pdf_id, "a")
    ficha["atributos_extras"]["leitura"]["tiles_revisados"].append("tile-que-nao-existe")
    erros = erros_leitura(rodada_dir, pdf_id, "a", ficha)
    assert any("tiles_revisados" in e and "tile-que-nao-existe" in e for e in erros), erros


def test_validar_recusa_leitor_trocado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha(rodada_dir, pdf_id, "b")
    erros = erros_leitura(rodada_dir, pdf_id, "a", ficha)
    assert any("leitor" in e for e in erros), erros


def test_validar_recusa_ficha_sem_bloco_de_leitura_origem_errada_e_tipo_predicao(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    sem_bloco = _ficha(rodada_dir, pdf_id, "a")
    del sem_bloco["atributos_extras"]
    assert any(
        "atributos_extras.leitura" in e for e in erros_leitura(rodada_dir, pdf_id, "a", sem_bloco)
    )

    origem = _ficha(rodada_dir, pdf_id, "a")
    origem["atributos_extras"]["leitura"]["origem"] = "humana"
    assert any("origem" in e for e in erros_leitura(rodada_dir, pdf_id, "a", origem))

    predicao = _ficha(rodada_dir, pdf_id, "a")
    predicao["tipo"] = "predicao"
    predicao["gerador"] = {"nome": "x"}
    assert any("tipo" in e for e in erros_leitura(rodada_dir, pdf_id, "a", predicao))

    vazia = _ficha(rodada_dir, pdf_id, "a", tiles=[])
    assert any("tiles_revisados" in e for e in erros_leitura(rodada_dir, pdf_id, "a", vazia))


@pytest.mark.parametrize(
    "regiao",
    [
        {"pagina": 9, "camada": "base", "bbox": [0.1, 0.1, 0.2, 0.2], "motivo": "borrado"},
        {"pagina": 1, "camada": "outra", "bbox": [0.1, 0.1, 0.2, 0.2], "motivo": "borrado"},
        {"pagina": 1, "camada": "base", "bbox": [0.3, 0.1, 0.2, 0.2], "motivo": "borrado"},
        {"pagina": 1, "camada": "base", "bbox": [0.1, 0.1, 1.2, 0.2], "motivo": "borrado"},
        {"pagina": 1, "camada": "base", "bbox": [0.1, 0.1, 0.2], "motivo": "borrado"},
        {"pagina": 1, "camada": "base", "bbox": [0.1, 0.1, 0.2, 0.2], "motivo": ""},
    ],
)
def test_validar_recusa_regiao_ilegivel_mal_formada(
    rodada: tuple[Path, str], regiao: Registro
) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha(rodada_dir, pdf_id, "a", ilegiveis=[regiao])
    erros = erros_leitura(rodada_dir, pdf_id, "a", ficha)
    assert any("regioes_ilegiveis" in e for e in erros), erros


def test_validar_aceita_regiao_ilegivel_bem_formada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    regiao = {"pagina": 1, "camada": "base", "bbox": [0.1, 0.1, 0.2, 0.2], "motivo": "borrado"}
    ficha = _ficha(rodada_dir, pdf_id, "a", ilegiveis=[regiao])
    assert erros_leitura(rodada_dir, pdf_id, "a", ficha) == []


def test_validar_c_exige_regioes_de_conferencia_e_regioes_contidas(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha_regional(rodada_dir, pdf_id, "c")
    erros = erros_leitura(rodada_dir, pdf_id, "c", ficha)
    assert any("regioes-conferencia.json" in e for e in erros), erros

    _gravar_conferencia(rodada_dir, pdf_id)
    assert erros_leitura(rodada_dir, pdf_id, "c", ficha) == []

    fora = copy.deepcopy(ficha)
    fora_bbox = _norm(300, 400, 340, 410)
    fora["escopo_anotacao"]["regioes"] = [{"pagina": 1, "bbox": fora_bbox}]
    fora["postes"][0]["bbox"] = _norm(310, 402, 320, 408)
    fora["atributos_extras"]["leitura"]["tiles_revisados"] = _tiles_que_cobrem(
        carregar_indice(rodada_dir, pdf_id), fora_bbox
    )
    erros = erros_leitura(rodada_dir, pdf_id, "c", fora)
    assert any("conferência" in e for e in erros), erros


def test_validar_c_recusa_escopo_completo(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _gravar_conferencia(rodada_dir, pdf_id)
    erros = erros_leitura(rodada_dir, pdf_id, "c", _ficha(rodada_dir, pdf_id, "c"))
    assert any("escopo" in e for e in erros), erros


def test_validar_c_exige_tiles_revisados_que_cubram_as_regioes(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _gravar_conferencia(rodada_dir, pdf_id)
    ficha = _ficha_regional(rodada_dir, pdf_id, "c")
    cobrem = list(ficha["atributos_extras"]["leitura"]["tiles_revisados"])
    ficha["atributos_extras"]["leitura"]["tiles_revisados"] = []
    sem_tiles = erros_leitura(rodada_dir, pdf_id, "c", ficha)
    assert any("tiles_revisados" in e for e in sem_tiles), sem_tiles

    ficha["atributos_extras"]["leitura"]["tiles_revisados"] = cobrem
    assert erros_leitura(rodada_dir, pdf_id, "c", ficha) == []


def test_validar_c_recusa_regiao_sem_tile_revisado_que_a_cubra(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    _gravar_conferencia(rodada_dir, pdf_id)
    indice = carregar_indice(rodada_dir, pdf_id)
    ficha = _ficha_regional(rodada_dir, pdf_id, "c")
    # só um tile distante da região foi aberto
    longe = next(
        str(t["id"]) for t in indice["tiles"] if t["bbox"][1] > 0.5 and t["camada"] == "base"
    )
    ficha["atributos_extras"]["leitura"]["tiles_revisados"] = [longe]
    erros = erros_leitura(rodada_dir, pdf_id, "c", ficha)
    assert any("região" in e and "tiles_revisados" in e for e in erros), erros


def test_congelar_grava_copia_e_sha_e_recusa_segunda_vez(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    rascunho = _rascunho(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    item = congelar_leitura(rodada_dir, pdf_id, "a", rascunho)
    assert item["sha256"] == hash_arquivo(diretorio_ficha(rodada_dir, pdf_id) / "leitura-a.json")
    assert item["exposicao"] is False
    assert item["leitor"] == "a"
    assert item["arquivo"] == "leitura-a.json"
    with pytest.raises(ValueError, match="já congelada"):
        congelar_leitura(rodada_dir, pdf_id, "a", rascunho)


def test_congelar_recusa_leitura_invalida_sem_gravar(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha(rodada_dir, pdf_id, "a")
    ficha["pdf_sha256"] = "1" * 64
    rascunho = _rascunho(rodada_dir, pdf_id, "a", ficha)
    with pytest.raises(ValueError, match="pdf_sha256"):
        congelar_leitura(rodada_dir, pdf_id, "a", rascunho)
    assert not (diretorio_ficha(rodada_dir, pdf_id) / "leitura-a.json").exists()
    assert not (diretorio_ficha(rodada_dir, pdf_id) / "congelamento.json").exists()


def test_congelar_registra_varios_leitores_no_mesmo_manifesto(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    for leitor in ("a", "b"):
        rascunho = _rascunho(rodada_dir, pdf_id, leitor, _ficha(rodada_dir, pdf_id, leitor))
        congelar_leitura(rodada_dir, pdf_id, leitor, rascunho)
    manifesto = carregar_manifesto(rodada_dir, pdf_id)
    assert manifesto["schema_version"] == "curadoria-ficha-congelamento-v1"
    assert [i["leitor"] for i in manifesto["itens"]] == ["a", "b"]
    assert set(manifesto["itens"][0]) == {"leitor", "arquivo", "sha256", "horario", "exposicao"}


def carregar_manifesto(rodada_dir: Path, pdf_id: str) -> Registro:
    texto = (diretorio_ficha(rodada_dir, pdf_id) / "congelamento.json").read_text(encoding="utf-8")
    dados = json.loads(texto)
    assert isinstance(dados, dict)
    return dados


def test_congelar_recusa_depois_da_consolidacao(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    escrever_json_atomico(diretorio_ficha(rodada_dir, pdf_id) / "referencia.json", {})
    rascunho = _rascunho(rodada_dir, pdf_id, "b", _ficha(rodada_dir, pdf_id, "b"))
    with pytest.raises(ValueError, match="consolidada"):
        congelar_leitura(rodada_dir, pdf_id, "b", rascunho)
    assert not (diretorio_ficha(rodada_dir, pdf_id) / "leitura-b.json").exists()


def test_carregar_congelada_devolve_a_ficha_e_detecta_adulteracao(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    ficha = _ficha(rodada_dir, pdf_id, "a")
    congelar_leitura(rodada_dir, pdf_id, "a", _rascunho(rodada_dir, pdf_id, "a", ficha))
    assert carregar_congelada(rodada_dir, pdf_id, "a") == ficha

    copia = diretorio_ficha(rodada_dir, pdf_id) / "leitura-a.json"
    copia.write_text(copia.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="sha256"):
        carregar_congelada(rodada_dir, pdf_id, "a")


def test_carregar_congelada_recusa_leitor_nao_congelado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    with pytest.raises(ValueError, match="não congelada"):
        carregar_congelada(rodada_dir, pdf_id, "b")


def _argv(comando: str, rodada_dir: Path, pdf_id: str, leitor: str, arquivo: Path) -> list[str]:
    return [
        comando,
        "--rodada",
        str(rodada_dir),
        "--pdf",
        pdf_id,
        "--leitor",
        leitor,
        "--arquivo",
        str(arquivo),
    ]


def test_cli_validar_e_congelar_codigos_de_saida(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    valido = _rascunho(rodada_dir, pdf_id, "a", _ficha(rodada_dir, pdf_id, "a"))
    assert main(_argv("validar", rodada_dir, pdf_id, "a", valido)) == 0
    saida = capsys.readouterr()
    assert "ok" in saida.out
    assert saida.err == ""

    assert main(_argv("congelar", rodada_dir, pdf_id, "a", valido)) == 0
    assert "ok" in capsys.readouterr().out

    assert main(_argv("congelar", rodada_dir, pdf_id, "a", valido)) == 1
    assert "erro:" in capsys.readouterr().err

    invalida = _ficha(rodada_dir, pdf_id, "b")
    invalida["pdf_sha256"] = "2" * 64
    arquivo = _rascunho(rodada_dir, pdf_id, "b", invalida)
    assert main(_argv("validar", rodada_dir, pdf_id, "b", arquivo)) == 1
    saida = capsys.readouterr()
    assert saida.out == ""
    assert "erro:" in saida.err
    assert "pdf_sha256" in saida.err
    assert str(rodada_dir) not in saida.err


def test_cli_validar_arquivo_inexistente_ou_json_invalido_sem_caminho(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    ausente = rodada_dir / "nao-existe.json"
    assert main(_argv("validar", rodada_dir, pdf_id, "a", ausente)) == 1
    erro = capsys.readouterr().err
    assert erro.startswith("erro:")
    assert str(rodada_dir) not in erro

    quebrado = rodada_dir / "quebrado.json"
    quebrado.write_text("{ não é json", encoding="utf-8")
    assert main(_argv("validar", rodada_dir, pdf_id, "a", quebrado)) == 1
    erro = capsys.readouterr().err
    assert erro.startswith("erro:")
    assert str(rodada_dir) not in erro


def test_cli_recusa_pdf_desconhecido(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, _ = rodada
    arquivo = rodada_dir / "x.json"
    arquivo.write_text("{}", encoding="utf-8")
    assert main(_argv("validar", rodada_dir, "pdf-que-nao-existe", "a", arquivo)) == 1
    assert capsys.readouterr().err.startswith("erro:")


def _argv_comparar(rodada_dir: Path, pdf_id: str) -> list[str]:
    return ["comparar", "--rodada", str(rodada_dir), "--pdf", pdf_id]


def test_cli_comparar_exige_a_e_b_congeladas_e_nao_sobrescreve(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    assert main(_argv_comparar(rodada_dir, pdf_id)) == 1
    assert "não congelada" in capsys.readouterr().err

    leitura_a = _ficha(rodada_dir, pdf_id, "a")
    congelar_leitura(rodada_dir, pdf_id, "a", _rascunho(rodada_dir, pdf_id, "a", leitura_a))
    assert main(_argv_comparar(rodada_dir, pdf_id)) == 1
    assert "leitura b não congelada" in capsys.readouterr().err
    assert not (pasta / "comparacao.json").exists()

    leitura_b = _ficha(rodada_dir, pdf_id, "b")
    leitura_b["postes"][0]["estruturas"] = ["N3"]
    congelar_leitura(rodada_dir, pdf_id, "b", _rascunho(rodada_dir, pdf_id, "b", leitura_b))
    assert main(_argv_comparar(rodada_dir, pdf_id)) == 0
    saida = capsys.readouterr()
    assert saida.err == ""
    assert "campo=1" in saida.out
    assert "poste_so_a=0" in saida.out

    comparacao = json.loads((pasta / "comparacao.json").read_text(encoding="utf-8"))
    assert comparacao["schema_version"] == "curadoria-ficha-comparacao-v1"
    assert [d["tipo"] for d in comparacao["divergencias"]] == ["campo"]
    regioes = json.loads((pasta / "regioes-conferencia.json").read_text(encoding="utf-8"))
    assert regioes["schema_version"] == "curadoria-ficha-regioes-v1"
    assert regioes["pdf_id"] == pdf_id
    assert [set(r) for r in regioes["regioes"]] == [{"id", "pagina", "bbox"}]
    for nome in ("comparacao.json", "regioes-conferencia.json"):
        texto = (pasta / nome).read_text(encoding="utf-8")
        assert str(rodada_dir) not in texto
        assert str(rodada_dir).replace("\\", "/") not in texto
        assert "a.pdf" not in texto

    # o leitor C já pode ser validado contra as regiões geradas
    assert erros_leitura(rodada_dir, pdf_id, "c", _ficha_regional(rodada_dir, pdf_id, "c")) == []

    antes = {nome: (pasta / nome).read_bytes() for nome in ("comparacao.json",)}
    assert main(_argv_comparar(rodada_dir, pdf_id)) == 1
    erro = capsys.readouterr().err
    assert "já existe" in erro
    assert str(rodada_dir) not in erro
    assert {nome: (pasta / nome).read_bytes() for nome in antes} == antes


def test_cli_comparar_recusa_regioes_de_conferencia_ja_gravadas(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    for leitor in ("a", "b"):
        rascunho = _rascunho(rodada_dir, pdf_id, leitor, _ficha(rodada_dir, pdf_id, leitor))
        congelar_leitura(rodada_dir, pdf_id, leitor, rascunho)
    _gravar_conferencia(rodada_dir, pdf_id)
    pasta = diretorio_ficha(rodada_dir, pdf_id)
    antes = (pasta / "regioes-conferencia.json").read_bytes()
    assert main(_argv_comparar(rodada_dir, pdf_id)) == 1
    assert "já existe" in capsys.readouterr().err
    assert (pasta / "regioes-conferencia.json").read_bytes() == antes
    assert not (pasta / "comparacao.json").exists()
