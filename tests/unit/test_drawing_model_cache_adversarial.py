# mypy: disable-error-code="no-untyped-call"
"""Ataques ao cache do modelo de desenho: fidelidade, esquema, falhas e atomicidade."""

from __future__ import annotations

import copy
import json
import threading
from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model import cache as modulo_cache
from zeny_project_handler.adapters.analysis.drawing_model.cache import (
    JsonDrawingModelCache,
    chave_modelo_desenho,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    VERSAO_MODELO_DESENHO,
    Arco,
    Caminho,
    Circulo,
    Estilo,
    GrupoCandidato,
    ImagemModelo,
    ItemCaminho,
    ModeloDesenho,
    PaginaModelo,
    PerfilFamilia,
    Polilinha,
    TextoModelo,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import obter_modelo_desenho

_CHAVE = chave_modelo_desenho("a" * 64, "pymupdf-teste")


def _modelo_completo() -> ModeloDesenho:
    estilo = Estilo("CAMADA-É", (1.0, 0.5, 0.0), None, 0.25, "tracejado")
    estilo2 = Estilo("", None, (0.0, 0.0, 1.0), 0.0, "")
    caminho = Caminho(
        subcaminhos=(
            (ItemCaminho("l", ((0.0, 0.0), (1.5, 2.5))), ItemCaminho("c", ((1.0, 1.0),) * 3)),
            (),
            (ItemCaminho("l", ((-3.25, 1e-9), (7.0, 1e9))),),
        ),
        estilo=estilo,
        tipo="traco_e_preenchimento",
        ordem=7,
    )
    caminho2 = Caminho((), estilo2, "preenchimento", 8)
    pagina = PaginaModelo(
        indice=3,
        largura=841.89,
        altura=595.28,
        caminhos=(caminho, caminho2),
        textos=(
            TextoModelo("Poste ção 12\n", (1.0, 2.0, 3.0, 4.0), "shx", 270.0, 3.5, "romans", "T"),
            TextoModelo("", (0.0, 0.0, 0.0, 0.0), "nativo", -0.0, 0.0, "", ""),
        ),
        primitivas=(
            Polilinha(((0.0, 0.0), (1.0, 1.0)), True, estilo, (0, 2)),
            Circulo((5.0, 6.0), 2.5, estilo2, ()),
            Arco((1.0, 1.0), 4.0, 0.0, 3.141592653589793, estilo, (9,)),
            Arco((1.0, 1.0), 4.0, 359.999, -45.5, estilo, (1, 2, 3)),
        ),
        grupos=(
            GrupoCandidato((0.0, 0.0, 9.0, 9.0), (0, 1, 2), (0,)),
            GrupoCandidato((1.0, 1.0, 1.0, 1.0), (), ()),
        ),
        imagens=(
            ImagemModelo((0.0, 0.0, 1.0, 1.0), 10, 20, "f" * 64, True),
            ImagemModelo((0.0, 0.0, 1.0, 1.0), 1, 1, "0" * 64, False),
        ),
        diagnosticos=("modelo.x", "outro"),
    )
    familia = PerfilFamilia(
        "familia-x",
        (
            ("d", Decimal("0.10")),
            ("e", Decimal("1E+3")),
            ("neg", Decimal("-0.000001234567890123456789")),
            ("s", "texto"),
            ("i", 5),
            ("t", True),
            ("f", False),
            ("n", None),
            ("dup", 1),
            ("dup", 2),
        ),
        ("d1", "d2"),
    )
    return ModeloDesenho(
        VERSAO_MODELO_DESENHO, "b" * 64, familia, (pagina, replace(pagina, indice=4))
    )


def _salvar(
    tmp_path: Path, modelo: ModeloDesenho | None = None
) -> tuple[JsonDrawingModelCache, Path]:
    cache = JsonDrawingModelCache(tmp_path / "c")
    cache.salvar(_CHAVE, modelo or _modelo_completo())
    return cache, next((tmp_path / "c" / "modelo-desenho").glob("*.json"))


def test_ida_e_volta_preserva_todos_os_campos_sinteticos(tmp_path: Path) -> None:
    modelo = _modelo_completo()
    cache, _ = _salvar(tmp_path, modelo)
    lido = cache.obter(_CHAVE)
    assert lido == modelo
    assert lido is not None
    sinais = dict(lido.familia.sinais)
    assert sinais["d"] == Decimal("0.10")
    assert str(sinais["d"]) == "0.10"
    assert str(sinais["e"]) == "1E+3"
    assert isinstance(sinais["d"], Decimal)
    assert sinais["t"] is True
    assert sinais["f"] is False
    assert type(sinais["i"]) is int
    assert [k for k, _ in lido.familia.sinais].count("dup") == 2
    assert lido.paginas[0].imagens[0].de_anotacao is True
    assert lido.paginas[0].imagens[1].de_anotacao is False
    sub = lido.paginas[0].caminhos[0].subcaminhos
    assert isinstance(sub, tuple) and all(isinstance(s, tuple) for s in sub)
    assert sub[1] == ()
    assert isinstance(lido.paginas[0].primitivas[0], Polilinha)
    assert isinstance(lido.paginas[0].primitivas[1], Circulo)
    assert isinstance(lido.paginas[0].primitivas[2], Arco)
    arco = lido.paginas[0].primitivas[3]
    assert isinstance(arco, Arco)
    assert arco.angulo_final == -45.5
    assert arco.angulo_inicial == 359.999


def test_inteiros_em_campos_float_voltam_como_float(tmp_path: Path) -> None:
    modelo = _modelo_completo()
    pagina = replace(modelo.paginas[0], largura=200.0, altura=100.0)
    cache, _ = _salvar(tmp_path, replace(modelo, paginas=(pagina,)))
    lido = cache.obter(_CHAVE)
    assert lido is not None
    assert type(lido.paginas[0].largura) is float
    assert type(lido.paginas[0].caminhos[0].estilo.espessura) is float


def test_chave_depende_de_sha_modelo_e_leitor_e_e_sha256() -> None:
    chaves = {
        chave_modelo_desenho("a" * 64, "l"),
        chave_modelo_desenho("b" * 64, "l"),
        chave_modelo_desenho("a" * 64, "m"),
        chave_modelo_desenho("a" * 64, "l", versao="v-outra"),
    }
    assert len(chaves) == 4
    assert all(len(c) == 64 and int(c, 16) >= 0 for c in chaves)
    assert chave_modelo_desenho("a" * 64, "l") == chave_modelo_desenho(
        "a" * 64, "l", versao=VERSAO_MODELO_DESENHO
    )


def test_chaves_diferentes_nao_se_misturam_no_disco(tmp_path: Path) -> None:
    cache = JsonDrawingModelCache(tmp_path)
    outra = chave_modelo_desenho("c" * 64, "x")
    cache.salvar(_CHAVE, _modelo_completo())
    assert cache.obter(outra) is None
    cache.salvar(outra, replace(_modelo_completo(), documento_sha256="d" * 64))
    assert cache.obter(_CHAVE) == _modelo_completo()
    lido = cache.obter(outra)
    assert lido is not None
    assert lido.documento_sha256 == "d" * 64


def test_salvar_substitui_entrada_anterior(tmp_path: Path) -> None:
    cache, _ = _salvar(tmp_path)
    novo = replace(_modelo_completo(), documento_sha256="e" * 64)
    cache.salvar(_CHAVE, novo)
    assert cache.obter(_CHAVE) == novo


def _pag(b: dict[str, Any]) -> dict[str, Any]:
    return b["modelo"]["paginas"][0]  # type: ignore[no-any-return]


def _sinais(b: dict[str, Any]) -> list[Any]:
    return b["modelo"]["familia"]["sinais"]  # type: ignore[no-any-return]


_CORRUPCOES: dict[str, Callable[[dict[str, Any]], object]] = {
    "schema_ausente": lambda b: b.pop("schema_version"),
    "schema_antigo": lambda b: b.__setitem__("schema_version", 0),
    "schema_futuro": lambda b: b.__setitem__("schema_version", 2),
    "schema_string": lambda b: b.__setitem__("schema_version", "1"),
    "modelo_ausente": lambda b: b.pop("modelo"),
    "modelo_lista": lambda b: b.__setitem__("modelo", []),
    "modelo_nulo": lambda b: b.__setitem__("modelo", None),
    "versao_do_modelo_antiga": lambda b: b["modelo"].__setitem__("versao", "antiga"),
    "versao_ausente": lambda b: b["modelo"].pop("versao"),
    "sha_ausente": lambda b: b["modelo"].pop("documento_sha256"),
    "familia_ausente": lambda b: b["modelo"].pop("familia"),
    "paginas_ausente": lambda b: b["modelo"].pop("paginas"),
    "paginas_nulo": lambda b: b["modelo"].__setitem__("paginas", None),
    "pagina_sem_caminhos": lambda b: _pag(b).pop("caminhos"),
    "pagina_sem_diagnosticos": lambda b: _pag(b).pop("diagnosticos"),
    "pagina_indice_texto": lambda b: _pag(b).__setitem__("indice", "x"),
    "caminho_tipo_invalido": lambda b: _pag(b)["caminhos"][0].__setitem__("tipo", "zzz"),
    "item_tipo_invalido": lambda b: _pag(b)["caminhos"][0]["subcaminhos"][0][0].__setitem__(
        "tipo", "q"
    ),
    "ponto_com_tres_coordenadas": lambda b: _pag(b)["caminhos"][0]["subcaminhos"][0][0]["pontos"][
        0
    ].append(1.0),
    "ponto_com_uma_coordenada": lambda b: _pag(b)["caminhos"][0]["subcaminhos"][0][0][
        "pontos"
    ].__setitem__(0, [1.0]),
    "bbox_curta": lambda b: _pag(b)["textos"][0].__setitem__("bbox", [1.0, 2.0]),
    "texto_origem_invalida": lambda b: _pag(b)["textos"][0].__setitem__("origem", "ocr"),
    "texto_sem_fonte": lambda b: _pag(b)["textos"][0].pop("fonte"),
    "estilo_ausente": lambda b: _pag(b)["caminhos"][0].pop("estilo"),
    "cor_com_dois_canais": lambda b: _pag(b)["caminhos"][0]["estilo"].__setitem__("cor", [1, 2]),
    "espessura_texto": lambda b: _pag(b)["caminhos"][0]["estilo"].__setitem__("espessura", "x"),
    "primitiva_sem_origens": lambda b: _pag(b)["primitivas"][0].pop("origens"),
    "arco_sem_angulo_final": lambda b: _pag(b)["primitivas"][2].pop("angulo_final"),
    "circulo_sem_raio": lambda b: _pag(b)["primitivas"][1].pop("raio"),
    "grupo_sem_indices": lambda b: _pag(b)["grupos"][0].pop("indices_caminhos"),
    "imagem_sem_de_anotacao": lambda b: _pag(b)["imagens"][0].pop("de_anotacao"),
    "imagem_largura_texto": lambda b: _pag(b)["imagens"][0].__setitem__("largura_px", "a"),
    "familia_sem_sinais": lambda b: b["modelo"]["familia"].pop("sinais"),
    "sinal_com_float": lambda b: _sinais(b).append(["x", 1.5]),
    "sinal_com_lista": lambda b: _sinais(b).append(["x", [1]]),
    "sinal_dict_desconhecido": lambda b: _sinais(b).append(["x", {"outro": "1"}]),
    "sinal_decimal_invalido": lambda b: _sinais(b).append(["x", {"decimal": "abc"}]),
    "sinal_sem_valor": lambda b: _sinais(b).append(["x"]),
    "sinal_dict_com_campo_extra": lambda b: _sinais(b).append(["x", {"decimal": "1", "extra": 1}]),
}


@pytest.mark.parametrize("nome", sorted(_CORRUPCOES))
def test_json_estruturalmente_invalido_equivale_a_cache_vazio(tmp_path: Path, nome: str) -> None:
    cache, alvo = _salvar(tmp_path)
    bruto: dict[str, Any] = json.loads(alvo.read_text(encoding="utf-8"))
    original = copy.deepcopy(bruto)
    _CORRUPCOES[nome](bruto)
    assert bruto != original, "a corrupção precisa alterar o arquivo"
    alvo.write_text(json.dumps(bruto), encoding="utf-8")
    assert cache.obter(_CHAVE) is None


@pytest.mark.parametrize(
    "conteudo",
    ["", "   ", "null", "[]", "[1,2]", "42", '"texto"', "{}", '{"schema_version":1}', "\x00\x01"],
)
def test_conteudos_degenerados_equivalem_a_cache_vazio(tmp_path: Path, conteudo: str) -> None:
    cache, alvo = _salvar(tmp_path)
    alvo.write_text(conteudo, encoding="utf-8")
    assert cache.obter(_CHAVE) is None


def test_bytes_nao_utf8_equivalem_a_cache_vazio(tmp_path: Path) -> None:
    cache, alvo = _salvar(tmp_path)
    alvo.write_bytes(b"\xff\xfe\x00{")
    assert cache.obter(_CHAVE) is None


def test_arquivo_truncado_equivale_a_cache_vazio(tmp_path: Path) -> None:
    cache, alvo = _salvar(tmp_path)
    dados = alvo.read_bytes()
    for corte in (1, len(dados) // 3, len(dados) // 2, len(dados) - 1):
        alvo.write_bytes(dados[:corte])
        assert cache.obter(_CHAVE) is None


def test_campos_extras_desconhecidos_nao_alteram_o_modelo(tmp_path: Path) -> None:
    modelo = _modelo_completo()
    cache, alvo = _salvar(tmp_path, modelo)
    bruto = json.loads(alvo.read_text(encoding="utf-8"))
    bruto["extra_raiz"] = 1
    bruto["modelo"]["extra"] = [1]
    _pag(bruto)["extra"] = {"a": 1}
    alvo.write_text(json.dumps(bruto), encoding="utf-8")
    assert cache.obter(_CHAVE) == modelo


@pytest.mark.parametrize(
    "mutar",
    [
        lambda b: _pag(b)["textos"][0].__setitem__("texto", None),
        lambda b: _pag(b)["textos"][0].__setitem__("texto", 5),
        lambda b: _pag(b).__setitem__("diagnosticos", "abc"),
        lambda b: _pag(b)["imagens"][0].__setitem__("de_anotacao", "false"),
        lambda b: _pag(b)["imagens"][0].__setitem__("de_anotacao", None),
        lambda b: _pag(b)["imagens"][0].__setitem__("sha256", None),
        lambda b: _pag(b)["primitivas"][0].__setitem__("fechada", "nao"),
        lambda b: _pag(b).__setitem__("indice", 1.9),
        lambda b: _pag(b).__setitem__("indice", True),
        lambda b: b["modelo"].__setitem__("documento_sha256", None),
    ],
    ids=[
        "texto_nulo",
        "texto_numero",
        "diagnosticos_string",
        "de_anotacao_string",
        "de_anotacao_nulo",
        "sha_imagem_nulo",
        "fechada_string",
        "indice_float",
        "indice_bool",
        "sha_documento_nulo",
    ],
)
def test_tipos_errados_nao_sao_coagidos_silenciosamente(
    tmp_path: Path, mutar: Callable[[dict[str, Any]], object]
) -> None:
    cache, alvo = _salvar(tmp_path)
    bruto = json.loads(alvo.read_text(encoding="utf-8"))
    mutar(bruto)
    alvo.write_text(json.dumps(bruto), encoding="utf-8")
    assert cache.obter(_CHAVE) is None


def test_diretorio_inexistente_e_arquivo_no_lugar_do_diretorio(tmp_path: Path) -> None:
    assert JsonDrawingModelCache(tmp_path / "nao" / "existe").obter(_CHAVE) is None
    bloqueio = tmp_path / "arquivo"
    bloqueio.write_text("x", encoding="utf-8")
    cache = JsonDrawingModelCache(bloqueio)
    assert cache.obter(_CHAVE) is None
    with pytest.raises(OSError):
        cache.salvar(_CHAVE, _modelo_completo())


def test_alvo_que_e_diretorio_equivale_a_cache_vazio(tmp_path: Path) -> None:
    cache = JsonDrawingModelCache(tmp_path)
    (tmp_path / "modelo-desenho" / f"{_CHAVE}.json").mkdir(parents=True)
    assert cache.obter(_CHAVE) is None


@pytest.mark.parametrize(
    "chave", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65, "a" * 64 + "\n"]
)
def test_chaves_invalidas_sao_rejeitadas_em_obter_e_salvar(tmp_path: Path, chave: str) -> None:
    cache = JsonDrawingModelCache(tmp_path)
    with pytest.raises(ValueError):
        cache.obter(chave)
    with pytest.raises(ValueError):
        cache.salvar(chave, _modelo_completo())
    assert not list(tmp_path.rglob("*.json"))


def test_salvar_nao_deixa_temporarios(tmp_path: Path) -> None:
    _salvar(tmp_path)
    arquivos = sorted(p.name for p in (tmp_path / "c" / "modelo-desenho").iterdir())
    assert arquivos == [f"{_CHAVE}.json"]


def test_falha_na_troca_preserva_entrada_valida_e_limpa_temporario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache, alvo = _salvar(tmp_path)
    antes = alvo.read_bytes()
    novo = replace(_modelo_completo(), documento_sha256="e" * 64)

    def _falha(self: Path, destino: Any) -> Path:
        raise OSError("falha na troca")

    with monkeypatch.context() as parcial:
        parcial.setattr(Path, "replace", _falha)
        with pytest.raises(OSError):
            cache.salvar(_CHAVE, novo)
    assert alvo.read_bytes() == antes
    assert cache.obter(_CHAVE) == _modelo_completo()
    assert [p.name for p in alvo.parent.iterdir()] == [alvo.name]


def test_falha_ao_escrever_temporario_nao_cria_arquivo_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = JsonDrawingModelCache(tmp_path)

    def _falha(self: Path, *_a: Any, **_k: Any) -> int:
        raise OSError("disco cheio")

    with monkeypatch.context() as parcial:
        parcial.setattr(Path, "write_text", _falha)
        with pytest.raises(OSError):
            cache.salvar(_CHAVE, _modelo_completo())
    assert cache.obter(_CHAVE) is None
    assert list((tmp_path / "modelo-desenho").iterdir()) == []


def test_modelo_nao_serializavel_nao_deixa_arquivo(tmp_path: Path) -> None:
    modelo = _modelo_completo()
    familia = replace(modelo.familia, sinais=(("x", object()),))  # type: ignore[arg-type]
    cache = JsonDrawingModelCache(tmp_path)
    with pytest.raises(TypeError):
        cache.salvar(_CHAVE, replace(modelo, familia=familia))
    assert cache.obter(_CHAVE) is None
    assert not list(tmp_path.rglob("*.json"))


def test_gravacoes_concorrentes_nunca_expoem_arquivo_parcial(tmp_path: Path) -> None:
    cache = JsonDrawingModelCache(tmp_path)
    a = _modelo_completo()
    b = replace(a, documento_sha256="e" * 64)
    cache.salvar(_CHAVE, a)
    parar = threading.Event()
    erros: list[str] = []
    leituras = [0]

    def escritor(modelo: ModeloDesenho) -> None:
        for _ in range(40):
            try:
                cache.salvar(_CHAVE, modelo)
            except PermissionError:
                pass  # Windows recusa a troca enquanto outro handle abre o alvo
            except Exception as exc:
                erros.append(f"escrita: {exc!r}")
                return

    def leitor() -> None:
        while not parar.is_set():
            lido = cache.obter(_CHAVE)
            leituras[0] += 1
            if lido is not None and lido != a and lido != b:
                erros.append("leitura de modelo parcial ou misturado")
                return

    leitores = [threading.Thread(target=leitor) for _ in range(2)]
    escritores = [threading.Thread(target=escritor, args=(m,)) for m in (a, b, a, b)]
    for t in leitores + escritores:
        t.start()
    for t in escritores:
        t.join()
    parar.set()
    for t in leitores:
        t.join()
    assert erros == []
    assert leituras[0] > 0
    assert cache.obter(_CHAVE) in (a, b)
    assert [p.name for p in (tmp_path / "modelo-desenho").iterdir()] == [f"{_CHAVE}.json"]


# --- obter_modelo_desenho ---------------------------------------------------------------


def _pdf(caminho: Path, texto: str = "POSTE 12") -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=200, height=200)
        pagina.draw_line((10, 10), (100, 10), color=(1, 0, 0), width=2)
        pagina.insert_text((30, 180), texto, fontsize=10)
        documento.save(caminho)
    return caminho


def _contar_extracoes(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    chamadas: list[Path] = []
    real = pymupdf_drawing_model.extrair_modelo_desenho

    def _espiao(pdf: Path) -> ModeloDesenho:
        chamadas.append(pdf)
        return real(pdf)

    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", _espiao)
    return chamadas


def test_primeira_chamada_extrai_e_grava_uma_vez_e_segunda_nao_extrai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "c")
    chamadas = _contar_extracoes(monkeypatch)
    primeiro = obter_modelo_desenho(pdf, cache)
    assert len(chamadas) == 1
    assert len(list((tmp_path / "c").rglob("*.json"))) == 1
    segundo = obter_modelo_desenho(pdf, cache)
    assert len(chamadas) == 1
    assert segundo == primeiro


def test_pdf_com_conteudo_diferente_nao_reaproveita_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = JsonDrawingModelCache(tmp_path / "c")
    chamadas = _contar_extracoes(monkeypatch)
    um = obter_modelo_desenho(_pdf(tmp_path / "a.pdf", "UM"), cache)
    dois = obter_modelo_desenho(_pdf(tmp_path / "b.pdf", "DOIS"), cache)
    assert len(chamadas) == 2
    assert um.documento_sha256 != dois.documento_sha256
    assert um.paginas[0].textos != dois.paginas[0].textos


def test_mesmo_conteudo_em_outro_caminho_reaproveita_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = JsonDrawingModelCache(tmp_path / "c")
    a = _pdf(tmp_path / "a.pdf")
    b = tmp_path / "copia.pdf"
    b.write_bytes(a.read_bytes())
    chamadas = _contar_extracoes(monkeypatch)
    obter_modelo_desenho(a, cache)
    obter_modelo_desenho(b, cache)
    assert len(chamadas) == 1


def test_versao_do_modelo_diferente_reextrai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "c")
    obter_modelo_desenho(pdf, cache)
    chamadas = _contar_extracoes(monkeypatch)
    monkeypatch.setattr(
        modulo_cache.chave_modelo_desenho, "__defaults__", ("modelo-desenho-futuro",)
    )
    obter_modelo_desenho(pdf, cache)
    assert len(chamadas) == 1
    assert len(list((tmp_path / "c").rglob("*.json"))) == 2


def test_versao_do_leitor_diferente_reextrai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "c")
    obter_modelo_desenho(pdf, cache)
    chamadas = _contar_extracoes(monkeypatch)
    monkeypatch.setattr(pymupdf, "VersionBind", "0.0.0-outra")
    obter_modelo_desenho(pdf, cache)
    assert len(chamadas) == 1
    assert len(list((tmp_path / "c").rglob("*.json"))) == 2


def test_entrada_corrompida_e_reextraida_e_regravada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "c")
    primeiro = obter_modelo_desenho(pdf, cache)
    alvo = next((tmp_path / "c").rglob("*.json"))
    alvo.write_text("{lixo", encoding="utf-8")
    chamadas = _contar_extracoes(monkeypatch)
    assert obter_modelo_desenho(pdf, cache) == primeiro
    assert len(chamadas) == 1
    assert json.loads(alvo.read_text(encoding="utf-8"))["schema_version"] == 1
    obter_modelo_desenho(pdf, cache)
    assert len(chamadas) == 1


def test_falha_de_gravacao_real_por_arquivo_no_lugar_do_diretorio(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    bloqueio = tmp_path / "cache"
    bloqueio.write_text("x", encoding="utf-8")
    modelo = obter_modelo_desenho(pdf, JsonDrawingModelCache(bloqueio))
    assert modelo.paginas[0].caminhos


@pytest.mark.parametrize(
    "codigo",
    [
        "modelo.caminhos_falhou",
        "modelo.textos_nativos_falhou",
        "modelo.textos_shx_falhou",
        "modelo.imagens_falhou",
        "modelo.imagens_anotacao_falhou",
        "modelo.primitivas_falhou",
        "modelo.qualquer_coisa_nova_falhou",
    ],
)
def test_diagnostico_de_falha_em_qualquer_pagina_impede_gravacao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, codigo: str
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "c")
    real = pymupdf_drawing_model.extrair_modelo_desenho(pdf)
    boa = replace(real.paginas[0], diagnosticos=("modelo.ok",))
    ruim = replace(real.paginas[0], indice=1, diagnosticos=("modelo.ok", codigo))
    quebrado = replace(real, paginas=(boa, ruim))
    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", lambda _p: quebrado)
    assert obter_modelo_desenho(pdf, cache) == quebrado
    assert not list((tmp_path / "c").rglob("*.json"))
    assert not list((tmp_path / "c").rglob("*.tmp"))


def test_falha_de_fonte_e_reextraida_na_chamada_seguinte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "c")
    real = pymupdf_drawing_model.extrair_modelo_desenho(pdf)
    quebrado = replace(
        real, paginas=(replace(real.paginas[0], diagnosticos=("modelo.textos_shx_falhou",)),)
    )
    respostas = [quebrado, real]
    monkeypatch.setattr(
        pymupdf_drawing_model, "extrair_modelo_desenho", lambda _p: respostas.pop(0)
    )
    assert obter_modelo_desenho(pdf, cache) == quebrado
    assert obter_modelo_desenho(pdf, cache) == real
    chave = chave_modelo_desenho(real.documento_sha256, f"pymupdf-{pymupdf.VersionBind}")
    assert cache.obter(chave) == real


def test_diagnostico_de_outro_dominio_nao_bloqueia_gravacao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "c")
    real = pymupdf_drawing_model.extrair_modelo_desenho(pdf)
    modelo = replace(
        real, paginas=(replace(real.paginas[0], diagnosticos=("analise.x_falhou", "modelo.ok")),)
    )
    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", lambda _p: modelo)
    obter_modelo_desenho(pdf, cache)
    assert len(list((tmp_path / "c").rglob("*.json"))) == 1


def test_falha_de_extracao_propaga_e_nao_grava(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "c")

    def _falha(_p: Path) -> ModeloDesenho:
        raise RuntimeError("pdf ruim")

    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", _falha)
    with pytest.raises(RuntimeError):
        obter_modelo_desenho(pdf, cache)
    assert not list((tmp_path / "c").rglob("*.json"))


def test_pdf_inexistente_propaga_erro_com_e_sem_cache(tmp_path: Path) -> None:
    for cache in (None, JsonDrawingModelCache(tmp_path / "c")):
        with pytest.raises(OSError):
            obter_modelo_desenho(tmp_path / "nao.pdf", cache)
