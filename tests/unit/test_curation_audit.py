from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from scripts.curation_audit import (
    DECISOES,
    ESQUEMA_AMOSTRA,
    ESQUEMA_CONCORDANCIA,
    AuditoriaRecusadaError,
    ParametrosAmostra,
    amostrar,
    amostrar_pdf,
    carregar_amostra,
    concordancia,
    decidir,
    estratos,
    main,
    populacao,
    sortear,
)
from scripts.curation_reference import (
    ESQUEMA_REFERENCIA,
    ReferenciaInvalidaError,
    congelar,
    revisar,
)
from scripts.curation_render import ParametrosRender, carregar_indice, renderizar
from scripts.curation_round import (
    RodadaError,
    TransicaoInvalidaError,
    carregar_checkpoint,
    carregar_rodada,
    diretorio_pdf,
    iniciar_rodada,
    transicionar,
)

AGORA = "2026-10-15T12:00:00+00:00"
DEPOIS = "2026-10-15T13:00:00+00:00"
Registro = dict[str, Any]
# A4 a 72 DPI com tiles de 256 px e 38 px de sobreposição: grade 3 x 4 por camada. A página 1
# tem anotação (camadas diferentes: 13 tiles a_revisar e 11 descartados nas duas camadas); a
# página 2 não tem (camada anotada igual à base: 2 a_revisar e 10 descartados só na base).
RAPIDO = ParametrosRender(lado_tile_px=256, sobreposicao=0.15, dpi_detalhe=72)
LARGURA, ALTURA = 595.0, 842.0
TRAFO = "cemig-eo-r3-s18-v001"
TRAFO_OUTRO = "cemig-eo-r3-s18-v002"
REGULADOR = "cemig-eo-r3-s18-v024"
ESTAI_MT = "cemig-eo-r3-s14-v001"
ESTAI_AT = "cemig-eo-r3-s15-v001"
FAMILIA = {
    "TRANSFORMADOR": "family-f02-18",
    "REGULADOR_TENSAO": "family-f02-18",
    "ESTAI": "family-f02-14",
    "CABO_AEREO": "family-f02-16",
}
ID_PADRAO = {
    "TRANSFORMADOR": TRAFO,
    "REGULADOR_TENSAO": REGULADOR,
    "ESTAI": ESTAI_MT,
    "CABO_AEREO": "cemig-eo-r3-s16-v001",
}
# Posições relativas dentro de um tile (frações da largura/altura do tile), sem sobreposição.
POSICOES = [(0.25, 0.25), (0.5, 0.25), (0.75, 0.25), (0.25, 0.65), (0.6, 0.65)]


def _retangulo(x0: float, y0: float, x1: float, y1: float) -> pymupdf.Rect:
    return pymupdf.Rect(x0, y0, x1, y1)  # type: ignore[no-untyped-call]


def _criar_pdf(caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    preto = (0, 0, 0)
    with pymupdf.open() as documento:  # type: ignore[no-untyped-call]
        pagina = documento.new_page(width=LARGURA, height=ALTURA)
        for caixa in ((100, 50, 110, 60), (300, 300, 400, 400), (50, 500, 60, 510)):
            pagina.draw_rect(_retangulo(*caixa), color=preto, fill=preto)
        pagina.draw_rect(_retangulo(20, 700, 200, 800), color=preto, fill=preto)
        pagina.draw_line((450, 700), (500, 700), color=preto, width=1)
        pagina.add_rect_annot(_retangulo(480, 100, 520, 140))
        # Marcas quase brancas (acima do limiar de branco): todo tile anotado da página 1 difere
        # do gêmeo da base nos bytes sem mudar ocupação nem triagem.
        for x in range(10, int(LARGURA), 60):
            for y in range(10, int(ALTURA), 60):
                marca = pagina.add_rect_annot(_retangulo(x, y, x + 20, y + 20))
                marca.set_colors(stroke=(0.995, 0.995, 0.995))
                marca.update()
        segunda = documento.new_page(width=LARGURA, height=ALTURA)
        segunda.draw_rect(_retangulo(300, 300, 320, 320), color=preto, fill=preto)
        segunda.draw_line((100, 100), (150, 100), color=preto, width=1)
        documento.save(caminho)


@pytest.fixture(scope="module")
def modelo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    base = tmp_path_factory.mktemp("modelo-auditoria")
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


# --- auxiliares -----------------------------------------------------------------------------


def _tiles(rodada_dir: Path, pdf_id: str) -> dict[str, Registro]:
    return {str(t["id"]): t for t in carregar_indice(rodada_dir, pdf_id)["tiles"]}


def _a_revisar(rodada_dir: Path, pdf_id: str) -> list[str]:
    return [i for i, t in _tiles(rodada_dir, pdf_id).items() if t["estado"] == "a_revisar"]


def _ids(amostra: Registro) -> list[str]:
    return [str(tile["id"]) for tile in amostra["tiles"]]


def _amostra(rodada_dir: Path, pdf_id: str, **opcoes: Any) -> Registro:
    resultado = amostrar_pdf(rodada_dir, pdf_id, **opcoes)
    assert resultado["status"] == "sucesso", resultado
    amostra, _ = carregar_amostra(rodada_dir, pdf_id, resultado["versao"])
    return amostra


def _caixa_no_tile(tile: Registro, fx: float, fy: float, lado: float = 0.08) -> list[float]:
    x0, y0, x1, y1 = tile["bbox"]
    largura, altura = x1 - x0, y1 - y0
    cx, cy = x0 + fx * largura, y0 + fy * altura
    return [
        cx - lado * largura / 2,
        cy - lado * altura / 2,
        cx + lado * largura / 2,
        cy + lado * altura / 2,
    ]


def _observacao(
    identidade: str, tile: Registro, posicao: tuple[float, float], classe: str, **campos: Any
) -> Registro:
    registro: Registro = {
        "id": identidade,
        "pagina": tile["pagina"],
        "camada": tile["camada"],
        "bbox": _caixa_no_tile(tile, *posicao),
        "familia": FAMILIA[classe],
        "class_id": classe,
        "id_inventario": ID_PADRAO[classe],
        "papel": "operacional",
        "texto_original": None,
        "interpretacao": None,
        "estado": "sustentado_por_evidencia",
        "tile_evidencia": tile["id"],
        "fonte_significado": {"tipo": "inventario", "localizador": None},
    }
    registro.update(campos)
    return registro


def _leitura(
    rodada_dir: Path,
    pdf_id: str,
    tiles_revisados: Sequence[str],
    observacoes: Sequence[Registro],
    regioes: Sequence[Registro] = (),
) -> Registro:
    checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
    return {
        "schema_version": ESQUEMA_REFERENCIA,
        "pdf": {
            "pdf_id": pdf_id,
            "sha256": checkpoint["sha256"],
            "caminho_relativo": checkpoint["caminho_relativo"],
        },
        "revisor": {"origem": "revisao_ia", "modelo": "indisponivel"},
        "escopo": "regional",
        "tiles_revisados": list(tiles_revisados),
        "regioes_ilegiveis": list(regioes),
        "observacoes": list(observacoes),
    }


def _gravar(caminho: Path, valor: Any) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(valor, ensure_ascii=False), encoding="utf-8")
    return caminho


def _primeiro_a_revisar(rodada_dir: Path, pdf_id: str, amostra: Registro) -> Registro:
    tiles = _tiles(rodada_dir, pdf_id)
    for tile_id in _ids(amostra):
        if tiles[tile_id]["estado"] == "a_revisar":
            return tiles[tile_id]
    raise AssertionError("amostra sem tile a_revisar")


def _cinco(tile: Registro, prefixo: str = "O") -> list[Registro]:
    classes = ["TRANSFORMADOR", "TRANSFORMADOR", "REGULADOR_TENSAO", "ESTAI", "TRANSFORMADOR"]
    return [
        _observacao(f"{prefixo}{n + 1}", tile, POSICOES[n], classe)
        for n, classe in enumerate(classes)
    ]


def _congelar_principal(rodada_dir: Path, pdf_id: str, observacoes: Sequence[Registro]) -> Registro:
    principal = _leitura(rodada_dir, pdf_id, _a_revisar(rodada_dir, pdf_id), observacoes)
    arquivo = _gravar(rodada_dir.parent / "leitor" / "referencia.json", principal)
    congelar(rodada_dir, pdf_id, arquivo, agora=AGORA)
    return principal


def _auditar(
    rodada_dir: Path,
    pdf_id: str,
    amostra: Registro,
    observacoes: Sequence[Registro],
    *,
    nome: str = "leitura.json",
    **opcoes: Any,
) -> Registro:
    leitura = _leitura(rodada_dir, pdf_id, _ids(amostra), observacoes)
    arquivo = _gravar(rodada_dir.parent / "auditor" / nome, leitura)
    return concordancia(rodada_dir, pdf_id, arquivo, agora=DEPOIS, **opcoes)


def _relatorio(rodada_dir: Path, resultado: Registro) -> Registro:
    dados = json.loads((rodada_dir / resultado["arquivo"]).read_text(encoding="utf-8"))
    assert isinstance(dados, dict)
    return dados


def _sem_lineares(classe: Registro) -> Registro:
    """Bloco de classe sem o detalhamento dos lineares (conferido nos testes próprios)."""
    assert classe["lineares"]["concordantes"] == 0
    return {chave: valor for chave, valor in classe.items() if chave != "lineares"}


def _caso_08(rodada_dir: Path, pdf_id: str, amostra: Registro) -> list[Registro]:
    """Leitura do auditor que discorda da classe de uma das cinco observações (4/5)."""
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    auditor = _cinco(tile, "A")
    auditor[1] = _observacao("A2", tile, POSICOES[1], "REGULADOR_TENSAO")
    return auditor


# --- amostrar ------------------------------------------------------------------------------


def test_mesma_semente_gera_arquivos_identicos(modelo: tuple[Path, str], tmp_path: Path) -> None:
    base, pdf_id = modelo
    conteudos = []
    for nome in ("um", "dois"):
        shutil.copytree(base, tmp_path / nome)
        rodada_dir = tmp_path / nome / "rodada"
        resultado = amostrar_pdf(rodada_dir, pdf_id, parametros=ParametrosAmostra(semente=7))
        conteudos.append((rodada_dir / resultado["arquivo"]).read_bytes())
    assert conteudos[0] == conteudos[1]

    rodada_dir = tmp_path / "um" / "rodada"
    repetido = amostrar_pdf(rodada_dir, pdf_id, parametros=ParametrosAmostra(semente=7))
    assert repetido["reutilizada"] is True
    assert repetido["versao"] == "amostra-v001"
    assert sorted(p.name for p in (diretorio_pdf(rodada_dir, pdf_id) / "auditoria").iterdir()) == [
        "amostra-v001.json"
    ]


def test_semente_diferente_gera_amostra_diferente(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    primeira = sortear(indice, ParametrosAmostra(semente=0))
    segunda = sortear(indice, ParametrosAmostra(semente=1))
    assert primeira != segunda
    assert sortear(indice, ParametrosAmostra(semente=0)) == primeira

    _amostra(rodada_dir, pdf_id, parametros=ParametrosAmostra(semente=0))
    outra = amostrar_pdf(rodada_dir, pdf_id, parametros=ParametrosAmostra(semente=1))
    assert outra["versao"] == "amostra-v002"
    assert outra["reutilizada"] is False


def test_todos_os_estratos_aparecem_e_cada_pagina_contribui(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    indice = carregar_indice(rodada_dir, pdf_id)
    grupos = estratos(indice)
    assert sorted(grupos) == [
        "p001-descartados",
        "p001-ocupacao-1",
        "p001-ocupacao-2",
        "p001-ocupacao-3",
        "p002-descartados",
        "p002-ocupacao-1",
        "p002-ocupacao-2",
    ]
    for semente in range(5):
        amostra = _amostra(rodada_dir, pdf_id, parametros=ParametrosAmostra(semente=semente))
        escolhidos = set(_ids(amostra))
        for nome, tiles in grupos.items():
            assert escolhidos & {t["id"] for t in tiles}, (semente, nome)
        assert {(e["estrato"], e["populacao"]) for e in amostra["estratos"]} == {
            (nome, len(tiles)) for nome, tiles in grupos.items()
        }
        assert sum(e["amostrados"] for e in amostra["estratos"]) == len(escolhidos)


def test_faixas_de_ocupacao_sao_tercis_por_pagina(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    grupos = estratos(carregar_indice(rodada_dir, pdf_id))
    tamanhos = [len(grupos[f"p001-ocupacao-{n}"]) for n in (1, 2, 3)]
    assert tamanhos == [4, 4, 5]
    maiores = [max(t["ocupacao"] for t in grupos[f"p001-ocupacao-{n}"]) for n in (1, 2)]
    menores = [min(t["ocupacao"] for t in grupos[f"p001-ocupacao-{n}"]) for n in (2, 3)]
    assert maiores[0] <= menores[0] and maiores[1] <= menores[1]
    assert all(t["estado"] == "descartado_branco" for t in grupos["p001-descartados"])


@pytest.mark.parametrize(("minimo", "esperado"), [(4, 5), (8, 8), (12, 12), (40, 15)])
def test_minimo_respeitado(rodada: tuple[Path, str], minimo: int, esperado: int) -> None:
    rodada_dir, pdf_id = rodada
    a_revisar = set(_a_revisar(rodada_dir, pdf_id))
    parametros = ParametrosAmostra(fracao=0.01, minimo=minimo, incluir_descartados=0.0)
    amostra = _amostra(rodada_dir, pdf_id, parametros=parametros)
    # 15 tiles a_revisar na população (sem os gêmeos anotados da página 2); com 5 estratos,
    # a amostra nunca é menor que o número de estratos nem que o mínimo pedido.
    assert len(_ids(amostra)) == esperado
    assert set(_ids(amostra)) <= a_revisar


def test_fracao_define_o_tamanho_quando_supera_o_minimo(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    parametros = ParametrosAmostra(fracao=0.5, minimo=1, incluir_descartados=0.0)
    amostra = _amostra(rodada_dir, pdf_id, parametros=parametros)
    assert len(_ids(amostra)) == 8  # ceil(0,5 x 15)
    parametros = ParametrosAmostra(fracao=0.2, minimo=1, incluir_descartados=0.0)
    assert len(sortear(carregar_indice(rodada_dir, pdf_id), parametros)) == 5  # 3, mas 5 estratos


def test_camada_anotada_igual_a_base_fica_fora_da_populacao(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    ids = {t["id"] for t in populacao(carregar_indice(rodada_dir, pdf_id))}
    assert not any(i.startswith("p002-anotada") for i in ids)
    assert any(i.startswith("p001-anotada") for i in ids)
    assert len(ids) == 24 + 12


def test_tile_anotado_identico_ao_gemeo_da_base_fica_fora_da_populacao() -> None:
    def tile(camada: str, linha: int, coluna: int, sha256: str) -> Registro:
        prefixo = "base" if camada == "base" else "anotada"
        return {
            "id": f"p001-{prefixo}-t{linha:02d}{coluna:02d}",
            "camada": camada,
            "pagina": 1,
            "linha": linha,
            "coluna": coluna,
            "sha256": sha256,
        }

    indice: Registro = {
        "paginas": [{"pagina": 1, "camada_anotada_igual_base": False}],
        "tiles": [
            tile("base", 0, 0, "a"),
            tile("base", 0, 1, "b"),
            tile("annotation", 0, 0, "a"),
            tile("annotation", 0, 1, "carimbo"),
        ],
    }
    ids = [t["id"] for t in populacao(indice)]
    assert ids == ["p001-base-t0000", "p001-base-t0001", "p001-anotada-t0001"]


@pytest.mark.parametrize(("fracao", "pagina1", "pagina2"), [(0.0, 0, 0), (0.05, 1, 1), (0.5, 6, 5)])
def test_descartados_entram_na_fracao_pedida(
    rodada: tuple[Path, str], fracao: float, pagina1: int, pagina2: int
) -> None:
    rodada_dir, pdf_id = rodada
    tiles = _tiles(rodada_dir, pdf_id)
    amostra = _amostra(rodada_dir, pdf_id, parametros=ParametrosAmostra(incluir_descartados=fracao))
    descartados = [i for i in _ids(amostra) if tiles[i]["estado"] == "descartado_branco"]
    assert sum(i.startswith("p001") for i in descartados) == pagina1
    assert sum(i.startswith("p002") for i in descartados) == pagina2


def test_amostra_contem_so_ids_e_caminhos_de_tiles(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    antes = amostrar_pdf(rodada_dir, pdf_id)
    conteudo_antes = (rodada_dir / antes["arquivo"]).read_bytes()
    amostra = json.loads(conteudo_antes)
    assert amostra["schema_version"] == ESQUEMA_AMOSTRA
    assert set(amostra) == {
        "schema_version",
        "pdf_id",
        "sha256_pdf",
        "versao",
        "nivel",
        "amostra_anterior",
        "parametros",
        "indice_tiles_sha256",
        "estratos",
        "tiles",
        "totais",
    }
    for tile in amostra["tiles"]:
        assert set(tile) == {"id", "arquivo", "pagina", "camada"}
        assert tile["arquivo"] == f"pdfs/{pdf_id}/render/{tile['id']}.png"
        assert (rodada_dir / tile["arquivo"]).is_file()
    for entrada in amostra["estratos"]:
        assert set(entrada) == {"estrato", "populacao", "amostrados"}

    # A amostra não depende da referência principal: congelada depois, com observações
    # marcadas, a nova amostragem com os mesmos parâmetros é o mesmo arquivo, sem rastro dela.
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    marcadas = [
        _observacao("MARCA-PRINCIPAL-1", tile, POSICOES[0], "TRANSFORMADOR"),
        _observacao("MARCA-PRINCIPAL-2", tile, POSICOES[1], "ESTAI", texto_original="SEGREDO"),
    ]
    _congelar_principal(rodada_dir, pdf_id, marcadas)
    depois = amostrar_pdf(rodada_dir, pdf_id)
    assert depois["reutilizada"] is True
    texto = (rodada_dir / depois["arquivo"]).read_text(encoding="utf-8")
    assert (rodada_dir / depois["arquivo"]).read_bytes() == conteudo_antes
    for marca in ("MARCA-PRINCIPAL", "SEGREDO", "TRANSFORMADOR", "ESTAI", "observ", "referencia"):
        assert marca not in texto
    assert "Users" not in texto and "C:" not in texto


def test_amostrar_nao_toca_o_checkpoint_e_exige_render(
    rodada: tuple[Path, str], tmp_path: Path
) -> None:
    rodada_dir, pdf_id = rodada
    arquivo = diretorio_pdf(rodada_dir, pdf_id) / "checkpoint.json"
    antes = arquivo.read_bytes()
    amostrar_pdf(rodada_dir, pdf_id)
    assert arquivo.read_bytes() == antes

    _criar_pdf(tmp_path / "outro" / "b.pdf")
    nova = tmp_path / "nova"
    iniciar_rodada(
        nova, tmp_path / "outro", concorrencia=3, raiz_repositorio=tmp_path / "sem-git", agora=AGORA
    )
    outro_id = str(carregar_rodada(nova)["pdfs"][0]["pdf_id"])
    resultado = amostrar(nova, [outro_id])
    assert resultado["pdfs"][0]["status"] == "recusado"
    assert "renderizado" in resultado["pdfs"][0]["falhas"][0]
    assert not (diretorio_pdf(nova, outro_id) / "auditoria").exists()


@pytest.mark.parametrize(
    "parametros",
    [
        ParametrosAmostra(fracao=0.0),
        ParametrosAmostra(fracao=1.5),
        ParametrosAmostra(minimo=0),
        ParametrosAmostra(semente=-1),
        ParametrosAmostra(incluir_descartados=-0.1),
        ParametrosAmostra(incluir_descartados=1.1),
    ],
)
def test_parametros_invalidos_sao_recusados(
    rodada: tuple[Path, str], parametros: ParametrosAmostra
) -> None:
    rodada_dir, pdf_id = rodada
    with pytest.raises(RodadaError):
        amostrar(rodada_dir, [pdf_id], parametros=parametros)
    assert not (diretorio_pdf(rodada_dir, pdf_id) / "auditoria").exists()


# --- decisão --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("concordantes", "total", "nivel", "limiar", "esperado"),
    [
        (5, 5, 1, 0.9, "referencia_confiavel"),
        (9, 10, 1, 0.9, "referencia_confiavel"),
        (4, 5, 1, 0.9, "ampliar_amostra"),
        (4, 5, 2, 0.9, "encerrar_com_pendencia"),
        (4, 5, 2, 0.8, "referencia_confiavel"),
        (0, 0, 1, 0.9, "ampliar_amostra"),
        (0, 0, 2, 0.9, "encerrar_com_pendencia"),
    ],
)
def test_decidir_nos_tres_estados(
    concordantes: int, total: int, nivel: int, limiar: float, esperado: str
) -> None:
    decisao, motivo = decidir(concordantes, total, limiar=limiar, nivel=nivel)
    assert decisao == esperado
    assert decisao in DECISOES
    assert motivo


# --- concordância ---------------------------------------------------------------------------


def test_concordancia_total_gera_referencia_confiavel_e_avanca_para_auditado(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    fora = next(
        _tiles(rodada_dir, pdf_id)[i]
        for i in _a_revisar(rodada_dir, pdf_id)
        if i not in _ids(amostra) and not i.startswith("p002-anotada")
    )
    extra = _observacao("FORA", fora, (0.5, 0.5), "ESTAI")
    _congelar_principal(rodada_dir, pdf_id, [*_cinco(tile), extra])

    resultado = _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A"))

    assert resultado["decisao"] == "referencia_confiavel"
    assert resultado["checkpoint_avancado"] is True
    relatorio = _relatorio(rodada_dir, resultado)
    assert relatorio["schema_version"] == ESQUEMA_CONCORDANCIA
    assert _sem_lineares(relatorio["classe"]) == {
        "concordantes": 5,
        "divergentes": 0,
        "divergentes_por_motivo": {
            "classe": 0,
            "papel_estado_ou_familia": 0,
            "papel_ou_familia": 0,
        },
        "so_referencia": 0,
        "so_auditoria": 0,
        "total": 5,
        "concordancia": 1.0,
    }
    assert any("recortadas" in item for item in relatorio["limitacoes"])
    assert relatorio["id_exato"]["concordancia"] == 1.0
    assert relatorio["id_exato"]["aplicaveis"] == 5
    assert relatorio["observacoes"]["referencia"]["comparaveis"] == 5
    assert relatorio["observacoes"]["referencia"]["fora_da_amostra"] == 1
    assert relatorio["discordancias"] == []
    assert relatorio["falhas_triagem"] == []
    assert relatorio["limiar"] == 0.9
    assert relatorio["amostra"]["nivel"] == 1
    assert any("não é confirmação humana" in item for item in relatorio["limitacoes"])
    checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
    assert checkpoint["fase"] == "auditado"
    evento = checkpoint["historico"][-1]
    assert evento["artefatos"][0]["caminho"] == resultado["arquivo"]
    assert evento["dados"]["decisao"] == "referencia_confiavel"
    assert evento["dados"]["referencia"]["sha256"] == checkpoint["referencia"]["sha256"]
    assert evento["dados"]["concordancia_classe"] == 1.0
    assert resultado["arquivo"] == f"pdfs/{pdf_id}/concordancia-v001.json"
    assert "auditoria/" not in resultado["arquivo"]


def test_concordancia_08_na_primeira_auditoria_pede_ampliar_sem_auditar(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    _congelar_principal(
        rodada_dir, pdf_id, _cinco(_primeiro_a_revisar(rodada_dir, pdf_id, amostra))
    )
    checkpoint = diretorio_pdf(rodada_dir, pdf_id) / "checkpoint.json"
    antes = checkpoint.read_bytes()

    resultado = _auditar(rodada_dir, pdf_id, amostra, _caso_08(rodada_dir, pdf_id, amostra))

    assert resultado["decisao"] == "ampliar_amostra"
    assert resultado["concordancia_classe"] == 0.8
    assert resultado["checkpoint_avancado"] is False
    assert checkpoint.read_bytes() == antes
    relatorio = _relatorio(rodada_dir, resultado)
    assert relatorio["classe"]["concordantes"] == 4
    assert relatorio["classe"]["divergentes"] == 1
    assert relatorio["classe"]["total"] == 5
    assert [d["tipo"] for d in relatorio["discordancias"]] == ["classe_divergente"]


def test_concordancia_08_na_amostra_ampliada_encerra_com_pendencia(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    _congelar_principal(
        rodada_dir, pdf_id, _cinco(_primeiro_a_revisar(rodada_dir, pdf_id, amostra))
    )
    primeira = _auditar(rodada_dir, pdf_id, amostra, _caso_08(rodada_dir, pdf_id, amostra))
    assert primeira["decisao"] == "ampliar_amostra"

    # Sem ampliar não há como trocar de amostra nem repetir a auditoria do nível 1.
    with pytest.raises(AuditoriaRecusadaError, match="--ampliar"):
        amostrar_pdf(rodada_dir, pdf_id, parametros=ParametrosAmostra(semente=3))
    with pytest.raises(AuditoriaRecusadaError, match="ampliada"):
        _auditar(
            rodada_dir,
            pdf_id,
            amostra,
            _cinco(_primeiro_a_revisar(rodada_dir, pdf_id, amostra), "A"),
        )

    ampliada_resultado = amostrar_pdf(rodada_dir, pdf_id, ampliar=True)
    ampliada, _ = carregar_amostra(rodada_dir, pdf_id)
    assert ampliada_resultado["nivel"] == 2
    assert ampliada["nivel"] == 2
    assert set(_ids(amostra)) < set(_ids(ampliada))
    assert ampliada["parametros"]["fracao"] == pytest.approx(0.3)
    assert ampliada["parametros"]["minimo"] == 8
    assert ampliada["amostra_anterior"]["arquivo"] == f"pdfs/{pdf_id}/auditoria/amostra-v001.json"

    segunda = _auditar(
        rodada_dir, pdf_id, ampliada, _caso_08(rodada_dir, pdf_id, amostra), nome="leitura2.json"
    )
    assert segunda["decisao"] == "encerrar_com_pendencia"
    assert segunda["concordancia_classe"] == 0.8
    assert carregar_checkpoint(rodada_dir, pdf_id)["fase"] == "referencia_congelada"
    with pytest.raises(AuditoriaRecusadaError, match="encerr"):
        _auditar(
            rodada_dir, pdf_id, ampliada, _caso_08(rodada_dir, pdf_id, amostra), nome="l3.json"
        )
    with pytest.raises(AuditoriaRecusadaError):
        amostrar_pdf(rodada_dir, pdf_id, ampliar=True)


def test_ampliar_sem_pedido_de_ampliacao_e_recusado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    with pytest.raises(AuditoriaRecusadaError, match="ampliar_amostra"):
        amostrar_pdf(rodada_dir, pdf_id, ampliar=True)
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    assert _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A"))["decisao"] == (
        "referencia_confiavel"
    )
    with pytest.raises(AuditoriaRecusadaError, match="ampliar_amostra"):
        amostrar_pdf(rodada_dir, pdf_id, ampliar=True)


def test_limiar_e_aplicado_a_concordancia_de_classe_e_nao_a_de_id_exato(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    auditor = _cinco(tile, "A")
    # Mesma classe com ID diferente em duas e alternativas numa terceira: ID exato 2/5.
    auditor[0] = _observacao("A1", tile, POSICOES[0], "TRANSFORMADOR", id_inventario=TRAFO_OUTRO)
    auditor[1] = _observacao("A2", tile, POSICOES[1], "TRANSFORMADOR", id_inventario=TRAFO_OUTRO)
    auditor[3] = _observacao(
        "A4",
        tile,
        POSICOES[3],
        "ESTAI",
        id_inventario=None,
        alternativas={"ids_inventario": [ESTAI_MT, ESTAI_AT], "motivo": "tensão ilegível"},
    )

    resultado = _auditar(rodada_dir, pdf_id, amostra, auditor)

    assert resultado["decisao"] == "referencia_confiavel"
    relatorio = _relatorio(rodada_dir, resultado)
    assert relatorio["classe"]["concordancia"] == 1.0
    assert relatorio["id_exato"] == {
        "aplicaveis": 5,
        "concordantes": 2,
        "divergentes": 3,
        "sem_id_exato": 0,
        "concordancia": 0.4,
    }
    assert sorted(d["tipo"] for d in relatorio["discordancias"]) == ["id_divergente"] * 3
    assert all(d["conta_em"] == "id_exato" for d in relatorio["discordancias"])


def test_id_exato_perfeito_nao_salva_concordancia_de_classe_baixa(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    auditor = _cinco(tile, "A")[:4]  # o auditor não viu O5: 4/5 na classe

    resultado = _auditar(rodada_dir, pdf_id, amostra, auditor)

    relatorio = _relatorio(rodada_dir, resultado)
    assert relatorio["id_exato"]["concordancia"] == 1.0
    assert relatorio["classe"]["concordancia"] == 0.8
    assert relatorio["classe"]["so_referencia"] == 1
    assert resultado["decisao"] == "ampliar_amostra"


def test_limiar_configuravel_e_inclusivo(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    _congelar_principal(
        rodada_dir, pdf_id, _cinco(_primeiro_a_revisar(rodada_dir, pdf_id, amostra))
    )
    resultado = _auditar(
        rodada_dir, pdf_id, amostra, _caso_08(rodada_dir, pdf_id, amostra), limiar=0.8
    )
    assert resultado["decisao"] == "referencia_confiavel"
    assert _relatorio(rodada_dir, resultado)["limiar"] == 0.8


def test_discordancias_sao_rastreaveis(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    principal = _cinco(tile)
    _congelar_principal(rodada_dir, pdf_id, principal)
    auditor = _cinco(tile, "A")
    auditor[0] = _observacao("A1", tile, POSICOES[0], "ESTAI")  # classe divergente
    del auditor[4]  # O5 só na referência
    auditor.append(_observacao("A9", tile, (0.85, 0.85), "TRANSFORMADOR"))  # só na auditoria
    auditor[2]["papel"] = "informativo"  # papel divergente: conta na classe

    relatorio = _relatorio(rodada_dir, _auditar(rodada_dir, pdf_id, amostra, auditor))

    assert _sem_lineares(relatorio["classe"]) == {
        "concordantes": 2,
        "divergentes": 2,
        "divergentes_por_motivo": {
            "classe": 1,
            "papel_estado_ou_familia": 0,
            "papel_ou_familia": 1,
        },
        "so_referencia": 1,
        "so_auditoria": 1,
        "total": 6,
        "concordancia": pytest.approx(1 / 3),
    }
    por_tipo = {d["tipo"]: d for d in relatorio["discordancias"]}
    assert set(por_tipo) == {
        "classe_divergente",
        "so_referencia",
        "so_auditoria",
        "papel_divergente",
    }
    divergente = por_tipo["classe_divergente"]
    assert (divergente["observacao_referencia"], divergente["observacao_auditoria"]) == ("O1", "A1")
    assert (divergente["class_referencia"], divergente["class_auditoria"]) == (
        "TRANSFORMADOR",
        "ESTAI",
    )
    assert divergente["tile"] == tile["id"]
    assert divergente["conta_em"] == "classe"
    assert por_tipo["so_referencia"]["observacao_referencia"] == "O5"
    assert por_tipo["so_referencia"]["observacao_auditoria"] is None
    assert por_tipo["so_auditoria"]["observacao_auditoria"] == "A9"
    papel = por_tipo["papel_divergente"]
    assert papel["conta_em"] == "classe"
    assert papel["motivo"] == "papel_ou_familia"
    assert (papel["observacao_referencia"], papel["observacao_auditoria"]) == ("O3", "A3")
    assert (papel["papel_referencia"], papel["papel_auditoria"]) == ("operacional", "informativo")
    assert divergente["motivo"] == "classe"
    ids = [d["id"] for d in relatorio["discordancias"]]
    assert len(set(ids)) == len(ids) and all(i.startswith("disc-") for i in ids)


def test_falha_de_triagem_e_reportada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tiles = _tiles(rodada_dir, pdf_id)
    descartado = next(tiles[i] for i in _ids(amostra) if tiles[i]["estado"] == "descartado_branco")
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    auditor = [*_cinco(tile, "A"), _observacao("A-BRANCO", descartado, (0.5, 0.5), "ESTAI")]

    resultado = _auditar(rodada_dir, pdf_id, amostra, auditor)

    assert resultado["falhas_triagem"] == 1
    relatorio = _relatorio(rodada_dir, resultado)
    assert relatorio["falhas_triagem"] == [
        {
            "observacao_id": "A-BRANCO",
            "tile_id": descartado["id"],
            "pagina": descartado["pagina"],
            "camada": descartado["camada"],
            "class_id": "ESTAI",
            "ocupacao": descartado["ocupacao"],
        }
    ]
    assert any("falha_triagem" in item for item in relatorio["pendencias"])
    # O tile descartado não foi revisado pela referência principal: fica fora da concordância.
    assert relatorio["classe"]["total"] == 5
    assert relatorio["observacoes"]["auditoria"]["excluidas"] == {
        "tile_nao_revisado_pela_referencia": 1
    }
    assert relatorio["decisao"] == "referencia_confiavel"
    evento = carregar_checkpoint(rodada_dir, pdf_id)["historico"][-1]
    assert evento["dados"]["falhas_triagem"] == 1


def test_falha_de_triagem_aparece_na_saida_da_cli(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    assert main(["amostrar", "--rodada", str(rodada_dir), "--pdf", pdf_id]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["totais"]["sucesso"] == 1
    amostra, _ = carregar_amostra(rodada_dir, pdf_id)
    tiles = _tiles(rodada_dir, pdf_id)
    descartado = next(tiles[i] for i in _ids(amostra) if tiles[i]["estado"] == "descartado_branco")
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    leitura = _leitura(
        rodada_dir,
        pdf_id,
        _ids(amostra),
        [*_cinco(tile, "A"), _observacao("A-BRANCO", descartado, (0.5, 0.5), "ESTAI")],
    )
    arquivo = _gravar(rodada_dir.parent / "auditor" / "leitura.json", leitura)
    codigo = main(
        ["concordancia", "--rodada", str(rodada_dir), "--pdf", pdf_id, "--auditoria", str(arquivo)]
    )
    capturado = capsys.readouterr()
    assert codigo == 0
    resumo = json.loads(capturado.out)
    assert resumo["decisao"] == "referencia_confiavel"
    assert resumo["falhas_triagem"] == 1
    assert "falha_triagem" in capturado.err


def test_regioes_ilegiveis_e_estado_ilegivel_saem_da_comparacao(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    principal = _cinco(tile)
    principal[4] = _observacao(
        "O5",
        tile,
        POSICOES[4],
        "TRANSFORMADOR",
        estado="ilegivel",
        motivo_estado="borrado",
        id_inventario=None,
    )
    _congelar_principal(rodada_dir, pdf_id, principal)
    auditor = _cinco(tile, "A")[:4]
    regiao = {
        "id": "R1",
        "pagina": tile["pagina"],
        "camada": tile["camada"],
        "bbox": _caixa_no_tile(tile, *POSICOES[3], lado=0.2),
        "motivo": "texto sobreposto",
    }
    del auditor[3]  # o auditor declarou ilegível a região de O4
    leitura = _leitura(rodada_dir, pdf_id, _ids(amostra), auditor, [regiao])
    arquivo = _gravar(rodada_dir.parent / "auditor" / "leitura.json", leitura)

    relatorio = _relatorio(rodada_dir, concordancia(rodada_dir, pdf_id, arquivo, agora=DEPOIS))

    assert relatorio["classe"]["total"] == 3
    assert relatorio["classe"]["concordancia"] == 1.0
    assert relatorio["observacoes"]["referencia"]["excluidas"] == {
        "estado_ilegivel": 1,
        "regiao_ilegivel_auditoria": 1,
    }


def test_camada_anotada_igual_a_base_compara_como_base(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    parametros = ParametrosAmostra(fracao=1.0, incluir_descartados=0.0)
    amostra = _amostra(rodada_dir, pdf_id, parametros=parametros)
    tiles = _tiles(rodada_dir, pdf_id)
    base = tiles["p002-base-t0101"]
    anotada = tiles["p002-anotada-t0101"]
    assert "p002-anotada-t0101" not in _ids(amostra)
    principal = [_observacao("O1", anotada, (0.5, 0.5), "TRANSFORMADOR")]
    _congelar_principal(rodada_dir, pdf_id, principal)
    auditor = [_observacao("A1", base, (0.5, 0.5), "TRANSFORMADOR")]
    relatorio = _relatorio(rodada_dir, _auditar(rodada_dir, pdf_id, amostra, auditor))
    assert relatorio["classe"]["concordantes"] == 1
    assert relatorio["classe"]["total"] == 1


def test_amostra_sem_observacoes_comparaveis_nao_e_confiavel(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    _congelar_principal(rodada_dir, pdf_id, [])
    resultado = _auditar(rodada_dir, pdf_id, amostra, [])
    assert resultado["concordancia_classe"] is None
    assert resultado["decisao"] == "ampliar_amostra"


def test_concordancia_e_deterministica(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    primeiro = _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A"))
    segundo = _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A"))
    assert (primeiro["versao"], segundo["versao"]) == ("concordancia-v001", "concordancia-v002")
    um = _relatorio(rodada_dir, primeiro)
    dois = _relatorio(rodada_dir, segundo)
    assert {**um, "versao": None} == {**dois, "versao": None}
    assert um["leitura_auditoria"]["observacoes"][0]["id"] == "A1"


# --- conjunto avaliado e recorte à amostra --------------------------------------------------


def _local(identidade: str, tile: Registro, posicao: tuple[float, float]) -> Registro:
    """Elemento sem família no inventário (moldura, QR, carimbo)."""
    return _observacao(
        identidade,
        tile,
        posicao,
        "ESTAI",
        familia="local-unknown",
        class_id="UNKNOWN_LOCAL",
        id_inventario=None,
    )


def _provisoria(
    identidade: str, tile: Registro, posicao: tuple[float, float], classe: str
) -> Registro:
    return _observacao(
        identidade, tile, posicao, classe, estado="provisorio", motivo_estado="traço fraco"
    )


def _por_motivo(relatorio: Registro) -> Registro:
    return dict(relatorio["classe"]["divergentes_por_motivo"])


@pytest.mark.parametrize("familia", ["family-f02-18", "local-unknown"])
@pytest.mark.parametrize("estado", ["sustentado_por_evidencia", "provisorio", "ilegivel"])
@pytest.mark.parametrize("papel", ["operacional", "informativo", "negativo", "desconhecido"])
def test_avaliavel_da_referencia_e_a_regra_de_curation_compare(
    papel: str, estado: str, familia: str
) -> None:
    from scripts.curation_audit import _avaliavel_referencia, _casavel_auditoria
    from scripts.curation_compare import _categoria

    observacao = {"papel": papel, "estado": estado, "familia": familia}
    assert _avaliavel_referencia(observacao) == (_categoria(observacao) == "operacional")
    casavel = papel == "operacional" and familia != "local-unknown" and estado != "ilegivel"
    assert _casavel_auditoria(observacao) == casavel


def test_esquema_da_concordancia_e_v2() -> None:
    assert ESQUEMA_CONCORDANCIA == "curadoria-concordancia-v2"


def test_informativos_locais_e_provisorios_divergentes_nao_derrubam_a_concordancia(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    principal = [
        *_cinco(tile),
        _local("MOLDURA", tile, (0.1, 0.9)),
        _observacao("COTA", tile, (0.9, 0.1), "ESTAI", papel="informativo"),
        _provisoria("OP", tile, (0.4, 0.45), "TRANSFORMADOR"),
        _observacao("CARIMBO", tile, (0.85, 0.85), "ESTAI", papel="informativo"),
    ]
    _congelar_principal(rodada_dir, pdf_id, principal)
    auditor = [
        *_cinco(tile, "A"),
        _local("QR", tile, (0.9, 0.9)),
        _observacao("TEXTO", tile, (0.1, 0.1), "TRANSFORMADOR", papel="negativo"),
        # Os dois incertos no mesmo lugar não pesam.
        _observacao("A-OP", tile, (0.4, 0.45), "ESTAI", papel="desconhecido"),
        # Carimbo local de um lado e informativo do outro: ninguém operacional.
        _local("A-CARIMBO", tile, (0.85, 0.85)),
    ]

    resultado = _auditar(rodada_dir, pdf_id, amostra, auditor)

    relatorio = _relatorio(rodada_dir, resultado)
    assert relatorio["classe"]["total"] == 5
    assert relatorio["classe"]["concordancia"] == 1.0
    assert resultado["decisao"] == "referencia_confiavel"
    fora = relatorio["fora_do_denominador"]
    assert fora["referencia"]["por_motivo"] == {"local": 1, "papel_informativo": 2, "provisorio": 1}
    assert fora["auditoria"]["por_motivo"] == {
        "local": 2,
        "papel_desconhecido": 1,
        "papel_negativo": 1,
    }
    assert fora["referencia"]["total"] == 4 and fora["auditoria"]["total"] == 4
    assert {item["observacao"] for item in fora["referencia"]["observacoes"]} == {
        "MOLDURA",
        "COTA",
        "OP",
        "CARIMBO",
    }
    assert relatorio["discordancias"] == []


def test_operacional_na_referencia_e_informativo_no_auditor_diverge(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    auditor = _cinco(tile, "A")
    auditor[2]["papel"] = "informativo"
    auditor[3] = _local("A4", tile, POSICOES[3])

    relatorio = _relatorio(rodada_dir, _auditar(rodada_dir, pdf_id, amostra, auditor))

    assert relatorio["classe"]["concordantes"] == 3
    assert relatorio["classe"]["divergentes"] == 2
    assert relatorio["classe"]["total"] == 5
    assert _por_motivo(relatorio) == {
        "classe": 0,
        "papel_estado_ou_familia": 0,
        "papel_ou_familia": 2,
    }
    divergencias = [d for d in relatorio["discordancias"] if d["conta_em"] == "classe"]
    assert {(d["observacao_referencia"], d["observacao_auditoria"]) for d in divergencias} == {
        ("O3", "A3"),
        ("O4", "A4"),
    }
    assert {d["motivo"] for d in divergencias} == {"papel_ou_familia"}
    assert {d["papel_auditoria"] for d in divergencias} == {"informativo", "operacional"}
    assert relatorio["fora_do_denominador"]["auditoria"]["total"] == 0
    assert relatorio["decisao"] == "ampliar_amostra"


def test_estado_diferente_com_mesma_classe_concorda(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    auditor = _cinco(tile, "A")
    auditor[0] = _provisoria("A1", tile, POSICOES[0], "TRANSFORMADOR")

    resultado = _auditar(rodada_dir, pdf_id, amostra, auditor)

    relatorio = _relatorio(rodada_dir, resultado)
    assert relatorio["classe"]["concordantes"] == 5
    assert relatorio["classe"]["total"] == 5
    assert _por_motivo(relatorio) == dict.fromkeys(
        ("classe", "papel_estado_ou_familia", "papel_ou_familia"), 0
    )
    assert resultado["decisao"] == "referencia_confiavel"
    (diagnostico,) = relatorio["discordancias"]
    assert diagnostico["tipo"] == "estado_divergente"
    assert diagnostico["conta_em"] is None
    assert (diagnostico["estado_referencia"], diagnostico["estado_auditoria"]) == (
        "sustentado_por_evidencia",
        "provisorio",
    )


def test_auditor_provisorio_sem_par_nao_pesa(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    auditor = [*_cinco(tile, "A"), _provisoria("A9", tile, (0.85, 0.85), "ESTAI")]

    resultado = _auditar(rodada_dir, pdf_id, amostra, auditor)

    relatorio = _relatorio(rodada_dir, resultado)
    assert relatorio["classe"]["so_auditoria"] == 0
    assert relatorio["classe"]["total"] == 5
    assert relatorio["fora_do_denominador"]["auditoria"]["por_motivo"] == {"provisorio": 1}
    assert resultado["decisao"] == "referencia_confiavel"
    # A mesma observação sustentada pesa como só auditoria.
    auditor[-1] = _observacao("A9", tile, (0.85, 0.85), "ESTAI")
    outra = _relatorio(rodada_dir, _auditar(rodada_dir, pdf_id, amostra, auditor, nome="b.json"))
    assert outra["classe"]["so_auditoria"] == 1
    assert outra["classe"]["total"] == 6


def test_referencia_provisoria_e_auditor_sustentado_de_mesma_classe_e_so_diagnostico(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    principal = _cinco(tile)
    principal[4] = _provisoria("O5", tile, POSICOES[4], "TRANSFORMADOR")
    _congelar_principal(rodada_dir, pdf_id, principal)

    relatorio = _relatorio(rodada_dir, _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A")))

    assert relatorio["classe"]["concordantes"] == 4
    assert relatorio["classe"]["divergentes"] == 0
    assert relatorio["classe"]["total"] == 4
    assert relatorio["classe"]["so_auditoria"] == 0
    (diagnostico,) = relatorio["discordancias"]
    assert diagnostico["tipo"] == "estado_divergente"
    assert diagnostico["conta_em"] is None
    assert (diagnostico["observacao_referencia"], diagnostico["observacao_auditoria"]) == (
        "O5",
        "A5",
    )
    assert relatorio["fora_do_denominador"]["referencia"]["total"] == 0


@pytest.mark.parametrize(
    ("classe", "campos"),
    [
        ("REGULADOR_TENSAO", {}),  # classe diferente
        ("TRANSFORMADOR", {"papel": "desconhecido"}),  # papel diferente
    ],
)
def test_referencia_incerta_e_auditor_sustentado_com_classe_ou_papel_diferente_diverge(
    rodada: tuple[Path, str], classe: str, campos: Registro
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    principal = _cinco(tile)
    principal[4] = _observacao(
        "O5", tile, POSICOES[4], classe, estado="provisorio", motivo_estado="x", **campos
    )
    _congelar_principal(rodada_dir, pdf_id, principal)

    relatorio = _relatorio(rodada_dir, _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A")))

    assert relatorio["classe"]["concordantes"] == 4
    assert relatorio["classe"]["divergentes"] == 1
    assert relatorio["classe"]["total"] == 5
    assert _por_motivo(relatorio)["papel_estado_ou_familia"] == 1
    (divergencia,) = [d for d in relatorio["discordancias"] if d["conta_em"] == "classe"]
    assert (divergencia["observacao_referencia"], divergencia["observacao_auditoria"]) == (
        "O5",
        "A5",
    )
    assert divergencia["motivo"] == "papel_estado_ou_familia"


def test_concordancia_baixa_continua_baixa_quando_operacionais_divergem(
    rodada: tuple[Path, str],
) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    grade = [(0.15 + 0.233 * (n % 4), 0.15 + 0.233 * (n // 4)) for n in range(16)]
    principal = [_observacao(f"O{n}", tile, grade[n], "TRANSFORMADOR") for n in range(6)]
    principal += [_local(f"MOLDURA{n}", tile, grade[n]) for n in (8, 9)]
    principal.append(_observacao("COTA", tile, grade[10], "ESTAI", papel="informativo"))
    _congelar_principal(rodada_dir, pdf_id, principal)
    auditor = [_observacao("A0", tile, grade[0], "TRANSFORMADOR")]
    auditor += [_observacao(f"A{n}", tile, grade[n], "ESTAI") for n in range(1, 5)]
    auditor.append(_observacao("A12", tile, grade[12], "REGULADOR_TENSAO"))  # O5 sem par
    auditor += [_local(f"QR{n}", tile, grade[n]) for n in (13, 14)]

    resultado = _auditar(rodada_dir, pdf_id, amostra, auditor)

    relatorio = _relatorio(rodada_dir, resultado)
    classe = relatorio["classe"]
    assert (classe["concordantes"], classe["divergentes"]) == (1, 4)
    assert (classe["so_referencia"], classe["so_auditoria"]) == (1, 1)
    assert classe["total"] == 7
    assert _por_motivo(relatorio)["classe"] == 4
    assert resultado["concordancia_classe"] == pytest.approx(1 / 7)
    assert resultado["decisao"] == "ampliar_amostra"


def _tile_sintetico(identidade: str, coluna: int, bbox: list[float]) -> Registro:
    return {
        "id": identidade,
        "pagina": 1,
        "camada": "base",
        "linha": 0,
        "coluna": coluna,
        "bbox": bbox,
        "estado": "a_revisar",
        "ocupacao": 0.5,
        "sha256": identidade,
    }


TRES_TILES = (
    _tile_sintetico("p001-base-t0000", 0, [0.0, 0.0, 0.4, 0.5]),
    _tile_sintetico("p001-base-t0001", 1, [0.35, 0.0, 0.75, 0.5]),
    _tile_sintetico("p001-base-t0002", 2, [0.7, 0.0, 1.0, 0.5]),
)


def _cabo(identidade: str, bbox: list[float], trace: list[list[float]] | None = None) -> Registro:
    registro = _observacao(identidade, TRES_TILES[1], (0.5, 0.5), "ESTAI", bbox=bbox)
    if trace:
        registro["trace"] = trace
    return registro


def _medir_tres_tiles(
    referencia: Sequence[Registro], auditoria: Sequence[Registro], amostrados: Sequence[int]
) -> Registro:
    """Mede sobre três tiles em linha, todos revisados pela referência; amostra ``amostrados``."""
    from scripts.curation_audit import medir_concordancia

    tiles = [copy.deepcopy(tile) for tile in TRES_TILES]
    ids = [tiles[n]["id"] for n in amostrados]
    return medir_concordancia(
        referencia={
            "tiles_revisados": [t["id"] for t in tiles],
            "regioes_ilegiveis": [],
            "observacoes": list(referencia),
        },
        auditoria={"tiles_revisados": ids, "regioes_ilegiveis": [], "observacoes": list(auditoria)},
        amostra={"nivel": 1, "tiles": [{"id": i} for i in ids]},
        indice={
            "pdf_id": "sintetico",
            "sha256_pdf": "0" * 64,
            "paginas": [{"pagina": 1, "camada_anotada_igual_base": True}],
            "tiles": tiles,
        },
    )


def test_cabo_longo_casa_com_o_trecho_do_auditor_depois_do_recorte() -> None:
    longo = _cabo("CABO", [0.1, 0.2, 0.95, 0.202], [[0.1, 0.201], [0.95, 0.201]])
    vizinho = _observacao("VIZINHO", TRES_TILES[2], (0.6, 0.5), "TRANSFORMADOR")
    trecho = _cabo("A-CABO", [0.36, 0.2, 0.74, 0.202], [[0.36, 0.201], [0.74, 0.201]])

    medida = _medir_tres_tiles([longo, vizinho], [trecho], [1])

    assert medida["classe"]["concordantes"] == 1
    assert medida["classe"]["total"] == 1
    assert medida["observacoes"]["referencia"]["fora_da_amostra"] == 1  # VIZINHO: recorte vazio
    assert medida["observacoes"]["referencia"]["recortadas"] == 1
    assert medida["observacoes"]["auditoria"]["recortadas"] == 0
    # Sem traço, a bbox recortada também casa.
    del longo["trace"], trecho["trace"]
    assert _medir_tres_tiles([longo], [trecho], [1])["classe"]["concordantes"] == 1


def test_cabo_com_centro_original_fora_da_amostra_entra_pelo_centro_recortado() -> None:
    # Centro original x = 0,775 só no tile 2 (não amostrado); recortado ao tile 1, x = 0,65.
    longo = _cabo("CABO", [0.55, 0.2, 1.0, 0.202], [[0.55, 0.201], [1.0, 0.201]])
    trecho = _cabo("A-CABO", [0.555, 0.2, 0.745, 0.202], [[0.555, 0.201], [0.745, 0.201]])

    medida = _medir_tres_tiles([longo], [trecho], [1])

    assert medida["observacoes"]["referencia"]["fora_da_amostra"] == 0
    assert (medida["classe"]["concordantes"], medida["classe"]["total"]) == (1, 1)
    (discordancia,) = _medir_tres_tiles([longo], [], [1])["discordancias"]
    assert discordancia["tipo"] == "so_referencia"
    assert discordancia["tile"] == TRES_TILES[1]["id"]


def test_recorte_usa_so_o_grupo_contiguo_de_tiles_com_mais_da_bbox() -> None:
    from scripts.curation_audit import _recorte

    t0, t1, t2 = (tuple(tile["bbox"]) for tile in TRES_TILES)
    cabo = (0.1, 0.2, 0.95, 0.202)
    assert _recorte(cabo, [t0, t2]) == pytest.approx((0.1, 0.2, 0.4, 0.202))
    assert _recorte(cabo, [t2, t0]) == pytest.approx((0.1, 0.2, 0.4, 0.202))
    assert _recorte(cabo, [t0, t1]) == pytest.approx((0.1, 0.2, 0.75, 0.202))
    adjacentes = [(0.0, 0.0, 0.5, 0.5), (0.5, 0.0, 1.0, 0.5)]
    assert _recorte(cabo, adjacentes) == pytest.approx(cabo)
    assert _recorte((0.42, 0.2, 0.68, 0.3), [t0, t2]) is None

    # Amostra com tiles 0 e 2 (não contíguos): o cabo casa com o trecho do grupo maior.
    trecho = _cabo("A-CABO", [0.1, 0.2, 0.4, 0.202])
    trecho["tile_evidencia"] = TRES_TILES[0]["id"]
    medida = _medir_tres_tiles([_cabo("CABO", list(cabo))], [trecho], [0, 2])
    assert (medida["classe"]["concordantes"], medida["classe"]["total"]) == (1, 1)


# --- objetos lineares por cobertura de comprimento -----------------------------------------


def _linear(
    identidade: str,
    trace: list[list[float]] | None = None,
    *,
    bbox: list[float] | None = None,
    classe: str = "CABO_AEREO",
    **campos: Any,
) -> Registro:
    """Observação linear sobre os três tiles sintéticos (bbox da polilinha, se houver)."""
    if bbox is None:
        assert trace is not None
        xs, ys = [p[0] for p in trace], [p[1] for p in trace]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
    registro = _observacao(identidade, TRES_TILES[1], (0.5, 0.5), classe, bbox=bbox, **campos)
    if trace:
        registro["trace"] = trace
    return registro


def _na_reta(x: float) -> list[float]:
    return [x, 0.2 + 0.1 * (x - 0.1) / 0.8]


TODOS = (0, 1, 2)


def test_cabo_em_vaos_na_referencia_e_trechos_no_auditor_concordam() -> None:
    from scripts.curation_audit import COBERTURA_MINIMA, TOLERANCIA_LINEAR

    referencia = [
        _linear("VAO1", [_na_reta(0.1), _na_reta(0.5)]),
        _linear("VAO2", [_na_reta(0.5), _na_reta(0.9)]),
    ]
    auditoria = [
        _linear("T1", [_na_reta(0.1), _na_reta(0.37)]),
        _linear("T2", [_na_reta(0.37), _na_reta(0.63)]),
        _linear("T3", [_na_reta(0.63), _na_reta(0.9)]),
    ]

    medida = _medir_tres_tiles(referencia, auditoria, TODOS)

    classe = medida["classe"]
    assert classe["lineares"] == {
        "classes_lineares": ["CABO_AEREO"],
        "cobertura_minima": COBERTURA_MINIMA,
        "concordantes": 2,
        "so_auditoria": 0,
        "so_referencia": 0,
        "tol": TOLERANCIA_LINEAR,
    }
    assert (classe["concordantes"], classe["total"], classe["divergentes"]) == (2, 2, 0)
    assert medida["discordancias"] == []


def test_cabo_paralelo_a_tres_tolerancias_nao_concorda() -> None:
    from scripts.curation_audit import TOLERANCIA_LINEAR

    deslocado = 0.2 + 3 * TOLERANCIA_LINEAR
    medida = _medir_tres_tiles(
        [_linear("CABO", [[0.1, 0.2], [0.9, 0.2]])],
        [_linear("A-CABO", [[0.1, deslocado], [0.9, deslocado]])],
        TODOS,
    )
    lineares = medida["classe"]["lineares"]
    contagens = (lineares["concordantes"], lineares["so_referencia"], lineares["so_auditoria"])
    assert contagens == (0, 1, 1)
    assert medida["classe"]["total"] == 2
    # Dentro da tolerância, concorda.
    perto = 0.2 + 0.5 * TOLERANCIA_LINEAR
    medida = _medir_tres_tiles(
        [_linear("CABO", [[0.1, 0.2], [0.9, 0.2]])],
        [_linear("A-CABO", [[0.1, perto], [0.9, perto]])],
        TODOS,
    )
    assert medida["classe"]["lineares"]["concordantes"] == 1


def test_cabo_diagonal_sem_traco_concorda_com_trecho_na_mesma_diagonal() -> None:
    # bbox quase quadrada sem traço: a linha é uma das diagonais (aqui, a descendente).
    referencia = [_linear("CABO", bbox=[0.2, 0.1, 0.5, 0.4])]
    auditoria = [_linear("A-CABO", [[0.25, 0.35], [0.45, 0.15]])]

    medida = _medir_tres_tiles(referencia, auditoria, TODOS)

    assert medida["classe"]["lineares"]["concordantes"] == 1
    assert medida["classe"]["total"] == 1
    # A outra diagonal não é coberta por esse trecho: com traço ascendente, não concorda.
    ascendente = [_linear("CABO", [[0.2, 0.1], [0.5, 0.4]])]
    assert _medir_tres_tiles(ascendente, auditoria, TODOS)["classe"]["concordantes"] == 0


def test_lineares_so_referencia_so_auditoria_e_incertos() -> None:
    referencia = [
        _linear("R1", [[0.1, 0.1], [0.9, 0.1]]),
        _linear("R2", [[0.55, 0.2], [0.95, 0.2]], estado="provisorio", motivo_estado="x"),
    ]
    auditoria = [
        _linear("A1", [[0.1, 0.45], [0.9, 0.45]]),
        _linear("A2", [[0.1, 0.3], [0.5, 0.3]], estado="provisorio", motivo_estado="x"),
        _linear("A3", [[0.55, 0.2], [0.95, 0.2]]),
    ]

    medida = _medir_tres_tiles(referencia, auditoria, TODOS)

    lineares = medida["classe"]["lineares"]
    contagens = (lineares["concordantes"], lineares["so_referencia"], lineares["so_auditoria"])
    assert contagens == (0, 1, 1)
    classe = medida["classe"]
    assert (classe["so_referencia"], classe["so_auditoria"], classe["total"]) == (1, 1, 2)
    fora = medida["fora_do_denominador"]
    assert fora["auditoria"]["por_motivo"] == {"provisorio": 1}
    assert fora["referencia"]["total"] == 0
    por_tipo = {
        (d["tipo"], d["observacao_referencia"], d["observacao_auditoria"]): d
        for d in medida["discordancias"]
    }
    assert set(por_tipo) == {
        ("so_referencia", "R1", None),
        ("so_auditoria", None, "A1"),
        ("estado_divergente", "R2", None),
    }
    assert por_tipo[("estado_divergente", "R2", None)]["conta_em"] is None
    assert por_tipo[("so_referencia", "R1", None)]["motivo"] == "linear"


def test_linear_e_nao_linear_no_mesmo_lugar_nao_sao_comparados() -> None:
    trafo = _observacao(
        "A-TRAFO", TRES_TILES[1], (0.5, 0.5), "TRANSFORMADOR", bbox=[0.3, 0.2, 0.6, 0.3]
    )
    medida = _medir_tres_tiles([_linear("CABO", [[0.3, 0.25], [0.6, 0.25]])], [trafo], TODOS)
    classe = medida["classe"]
    assert (classe["so_referencia"], classe["so_auditoria"], classe["divergentes"]) == (1, 1, 0)
    assert classe["lineares"]["so_referencia"] == 1


# --- recusas --------------------------------------------------------------------------------


def _estado(rodada_dir: Path, pdf_id: str) -> tuple[bytes, list[str]]:
    pasta = diretorio_pdf(rodada_dir, pdf_id)
    return (pasta / "checkpoint.json").read_bytes(), sorted(
        p.name for p in pasta.glob("concordancia-v*.json")
    )


def test_concordancia_sem_referencia_congelada_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    antes = _estado(rodada_dir, pdf_id)
    with pytest.raises(TransicaoInvalidaError, match="referencia_congelada"):
        _auditar(rodada_dir, pdf_id, amostra, [])
    assert _estado(rodada_dir, pdf_id) == antes


def test_concordancia_sem_amostra_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    _congelar_principal(rodada_dir, pdf_id, [])
    arquivo = _gravar(
        rodada_dir.parent / "auditor" / "l.json", _leitura(rodada_dir, pdf_id, [], [])
    )
    with pytest.raises(AuditoriaRecusadaError, match="amostra"):
        concordancia(rodada_dir, pdf_id, arquivo)


def test_leitura_com_tile_fora_da_amostra_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    fora = next(i for i in _a_revisar(rodada_dir, pdf_id) if i not in _ids(amostra))
    leitura = _leitura(rodada_dir, pdf_id, [*_ids(amostra), fora], _cinco(tile, "A"))
    arquivo = _gravar(rodada_dir.parent / "auditor" / "l.json", leitura)
    antes = _estado(rodada_dir, pdf_id)
    with pytest.raises(ReferenciaInvalidaError, match=fora):
        concordancia(rodada_dir, pdf_id, arquivo)
    assert _estado(rodada_dir, pdf_id) == antes


def test_leitura_que_nao_revisa_toda_a_amostra_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    faltando = next(i for i in _ids(amostra) if i != tile["id"])
    revisados = [i for i in _ids(amostra) if i != faltando]
    arquivo = _gravar(
        rodada_dir.parent / "auditor" / "l.json",
        _leitura(rodada_dir, pdf_id, revisados, _cinco(tile, "A")),
    )
    antes = _estado(rodada_dir, pdf_id)
    with pytest.raises(AuditoriaRecusadaError, match=faltando):
        concordancia(rodada_dir, pdf_id, arquivo)
    assert _estado(rodada_dir, pdf_id) == antes


def test_leitura_com_bloco_de_congelamento_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    leitura = _leitura(rodada_dir, pdf_id, _ids(amostra), _cinco(tile, "A"))
    leitura["congelamento"] = {"versao": 1}
    arquivo = _gravar(rodada_dir.parent / "auditor" / "l.json", leitura)
    with pytest.raises(AuditoriaRecusadaError, match="congelamento"):
        concordancia(rodada_dir, pdf_id, arquivo)


def test_amostra_de_indice_diferente_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    caminho = diretorio_pdf(rodada_dir, pdf_id) / "auditoria" / "amostra-v001.json"
    adulterada = json.loads(caminho.read_text(encoding="utf-8"))
    adulterada["indice_tiles_sha256"] = "0" * 64
    caminho.write_text(json.dumps(adulterada), encoding="utf-8")
    with pytest.raises(AuditoriaRecusadaError, match="índice"):
        _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A"))


def test_fase_terminal_e_recusada(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    transicionar(rodada_dir, pdf_id, "encerrado_com_pendencias", nota="x", agora=AGORA)
    antes = _estado(rodada_dir, pdf_id)
    with pytest.raises(TransicaoInvalidaError, match="terminal"):
        _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A"))
    assert _estado(rodada_dir, pdf_id) == antes
    assert amostrar(rodada_dir, [pdf_id])["pdfs"][0]["status"] == "recusado"


def test_revisar_a_referencia_invalida_o_marco_auditado(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    amostra = _amostra(rodada_dir, pdf_id)
    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    principal = _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    assert _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A"))["decisao"] == (
        "referencia_confiavel"
    )
    assert "auditado" in carregar_checkpoint(rodada_dir, pdf_id)["marcos"]

    revisada = copy.deepcopy(principal)
    revisada["observacoes"][0]["class_id"] = "REGULADOR_TENSAO"
    revisada["observacoes"][0]["id_inventario"] = REGULADOR
    arquivo = _gravar(rodada_dir.parent / "leitor" / "revisada.json", revisada)
    revisar(rodada_dir, pdf_id, arquivo, motivo="correção", exposicao_predicoes=False, agora=DEPOIS)

    checkpoint = carregar_checkpoint(rodada_dir, pdf_id)
    assert "auditado" not in checkpoint["marcos"]
    with pytest.raises(TransicaoInvalidaError, match="auditado"):
        transicionar(rodada_dir, pdf_id, "fechado", agora=DEPOIS)
    # A mesma leitura do auditor é medida de novo contra a versão revisada.
    novo = _auditar(rodada_dir, pdf_id, amostra, _cinco(tile, "A"), nome="mesma.json")
    assert novo["concordancia_classe"] == 0.8
    assert _relatorio(rodada_dir, novo)["referencia"]["versao"] == "referencia-v002.json"


# --- CLI ------------------------------------------------------------------------------------


def test_cli_amostrar_por_onda_e_concordancia(
    rodada: tuple[Path, str], capsys: pytest.CaptureFixture[str]
) -> None:
    rodada_dir, pdf_id = rodada
    codigo = main(
        [
            "amostrar",
            "--rodada",
            str(rodada_dir),
            "--onda",
            "1",
            "--fracao",
            "0.5",
            "--semente",
            "3",
        ]
    )
    assert codigo == 0
    saida = json.loads(capsys.readouterr().out)
    item = saida["pdfs"][0]
    assert (item["pdf_id"], item["status"], item["versao"], item["nivel"]) == (
        pdf_id,
        "sucesso",
        "amostra-v001",
        1,
    )
    amostra, _ = carregar_amostra(rodada_dir, pdf_id)
    assert amostra["parametros"]["semente"] == 3
    assert amostra["parametros"]["fracao"] == 0.5

    assert main(["amostrar", "--rodada", str(rodada_dir), "--pdf", pdf_id, "--ampliar"]) == 1
    assert "ampliar_amostra" in capsys.readouterr().err
    assert (
        main(
            [
                "amostrar",
                "--rodada",
                str(rodada_dir),
                "--pdf",
                pdf_id,
                "--ampliar",
                "--semente",
                "1",
            ]
        )
        == 1
    )
    capsys.readouterr()

    tile = _primeiro_a_revisar(rodada_dir, pdf_id, amostra)
    _congelar_principal(rodada_dir, pdf_id, _cinco(tile))
    arquivo = _gravar(
        rodada_dir.parent / "auditor" / "l.json",
        _leitura(rodada_dir, pdf_id, _ids(amostra), _caso_08(rodada_dir, pdf_id, amostra)),
    )
    argumentos = ["concordancia", "--rodada", str(rodada_dir), "--pdf", pdf_id]
    assert main([*argumentos, "--auditoria", str(arquivo), "--limiar", "1.5"]) == 1
    capsys.readouterr()
    assert main([*argumentos, "--auditoria", str(arquivo), "--amostra", "v009"]) == 1
    capsys.readouterr()
    assert main([*argumentos, "--auditoria", str(arquivo), "--amostra", "v001"]) == 0
    resumo = json.loads(capsys.readouterr().out)
    assert resumo["decisao"] == "ampliar_amostra"
    assert resumo["concordancia_classe"] == 0.8


def test_cli_recusa_selecao_invalida(rodada: tuple[Path, str]) -> None:
    rodada_dir, pdf_id = rodada
    assert main(["amostrar", "--rodada", str(rodada_dir)]) == 1
    assert main(["amostrar", "--rodada", str(rodada_dir), "--pdf", "999-inexistente"]) == 1
    assert main(["amostrar", "--rodada", str(rodada_dir), "--pdf", pdf_id, "--fracao", "0"]) == 1
