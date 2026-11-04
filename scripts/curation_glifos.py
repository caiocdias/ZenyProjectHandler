# mypy: disable-error-code="no-untyped-call"
"""Rodada de glifos da curadoria: agrupa formas de texto em contorno e as rotula com leitura dupla.

Uso:
    python -m scripts.curation_glifos agrupar --pdfs DIR --rodada DIR [--limiar 0.04]
        [--excluir-sha ARQ]
    python -m scripts.curation_glifos validar --rodada DIR --leitor {a,b,c} --arquivo JSON
    python -m scripts.curation_glifos consolidar --rodada DIR
    python -m scripts.curation_glifos publicar --rodada DIR --saida ARQ [--tolerancia 0.08]
        [--margem 0.02] [--espaco 0.48] [--quebra 1.5]

``agrupar`` lê os PDFs, extrai os trechos de glifos de cada página e agrupa as formas de trechos
de quadro confirmado (``quadro_incerto = False``) pelo líder (frequência decrescente, distância
``min(d(a, b), d(b, a))`` até o limiar). Grava em ``RODADA``: ``grupos.json`` (ids ``c0001…``),
``h1.json`` (contagens por família, inclusive a fração excluída por quadro incerto),
``celulas.json`` (desenhos das células, só números) e as folhas de contato
``contato/folha-NNN.png``. Nenhum JSON leva nome de PDF nem caminho absoluto: a folha é
identificada por ``sha256[:12]``. ``--excluir-sha`` lista sha256 de folhas reservadas para
avaliação, que ficam de fora.

Cada leitor (IA) lê só os PNG de contato e grava ``curadoria-glifos-v1`` com um rótulo por grupo
(``caractere`` ou ``marca``); ``validar`` confere e copia para ``leituras/leitura-LEITOR.json``,
sem sobrescrever. ``consolidar`` aceita A = B; havendo divergência, grava ``divergencias.json`` e
``contato-divergencias/`` e sai com código 3 até existir a leitura C (que cobre só as
divergências e desempata com um dos dois). ``publicar`` escreve a tabela de glifos
(``tabela-glifos-v1``) com os grupos aceitos.
"""

from __future__ import annotations

import argparse
import math
import sys
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import pymupdf

from scripts.curation_round import (
    RodadaError,
    descobrir_pdfs,
    escrever_bytes_atomico,
    escrever_json_atomico,
    hash_arquivo,
    json_canonico,
    ler_json,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import (
    AssinaturaGlifo,
    achatar_subcaminho,
    diferenca_caixa,
    distancia_assinaturas,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    EntradaGlifo,
    carregar_tabela_glifos,
    serializar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import (
    TrechoGlifos,
    _eh_candidato,
    extrair_trechos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    caminhos_da_pagina,
    extrair_modelo_desenho,
)

Registro = dict[str, Any]
Poligono = list[list[float]]

FORMATO_LEITURA: Final = "curadoria-glifos-v1"
FORMATO_GRUPOS: Final = "curadoria-glifos-grupos-v1"
FORMATO_H1: Final = "curadoria-glifos-h1-v1"
FORMATO_CELULAS: Final = "curadoria-glifos-celulas-v1"
FORMATO_CONSOLIDACAO: Final = "curadoria-glifos-consolidacao-v1"
LEITORES: Final = ("a", "b", "c")
MARCAS: Final = ("ignorar", "ilegivel", "composto", "fragmento", "misto")
MARCAS_CONTADAS: Final = ("composto", "fragmento", "misto")
LIMIAR_PADRAO: Final = 0.04
GRUPOS_POR_FOLHA: Final = 40
CODIGO_DIVERGENCIAS: Final = 3
LIMITE_EXCLUSAO_INCERTA: Final = 0.30
_CASAS_CHAVE: Final = 3
_CASAS_JSON: Final = 4
_CASAS_DESENHO: Final = 2
_JANELA_CONTEXTO: Final = 6
_ERROS_MOSTRADOS: Final = 20

_COLUNAS: Final = 5
_LARGURA_CELULA: Final = 170.0
_ALTURA_CELULA: Final = 150.0
_DPI_FOLHA: Final = 110
_PRETO: Final = (0.0, 0.0, 0.0)
_VERMELHO: Final = (0.8, 0.0, 0.0)
_CINZA: Final = (0.7, 0.7, 0.7)


# --- agrupamento ----------------------------------------------------------------------------

_ChaveForma = tuple[int, tuple[float, ...], tuple[tuple[float, ...], ...]]


@dataclass(frozen=True, slots=True)
class _Referencia:
    """Onde achar o glifo de novo (índices na lista de PDFs, página, trecho e glifo)."""

    pdf: int
    pagina: int
    trecho: int
    glifo: int


@dataclass(slots=True)
class _Forma:
    assinatura: AssinaturaGlifo
    chave: _ChaveForma
    instancias: list[_Referencia] = field(default_factory=list)
    familias: Counter[str] = field(default_factory=Counter)
    folhas: set[int] = field(default_factory=set)


@dataclass(slots=True)
class _Grupo:
    representante: _Forma
    formas: list[tuple[_Forma, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.formas.append((self.representante, 0.0))

    @property
    def membros(self) -> int:
        return sum(len(forma.instancias) for forma, _ in self.formas)

    @property
    def distante(self) -> _Forma:
        return max(self.formas, key=lambda par: par[1])[0]


@dataclass(slots=True)
class _Estatistica:
    candidatos: int = 0
    trechos: int = 0
    glifos_em_trecho: int = 0
    excluidos: int = 0


@dataclass(slots=True)
class _Colheita:
    formas: dict[_ChaveForma, _Forma] = field(default_factory=dict)
    incertas: dict[str, set[_ChaveForma]] = field(default_factory=dict)
    familias: dict[str, _Estatistica] = field(default_factory=dict)
    subcaminhos: Counter[int] = field(default_factory=Counter)
    folhas: list[str] = field(default_factory=list)


def _arredondar(valor: float, casas: int) -> float:
    return round(valor, casas) + 0.0


def _chave_da_forma(assinatura: AssinaturaGlifo) -> _ChaveForma:
    return (
        assinatura.subcaminhos,
        tuple(_arredondar(v, _CASAS_CHAVE) for v in assinatura.caixa),
        tuple(
            tuple(_arredondar(c, _CASAS_CHAVE) for ponto in contorno for c in ponto)
            for contorno in assinatura.contornos
        ),
    )


def _distancia(a: AssinaturaGlifo, b: AssinaturaGlifo) -> float:
    return min(distancia_assinaturas(a, b), distancia_assinaturas(b, a))


def _colher_trecho(
    colheita: _Colheita, familia: str, ref: tuple[int, int, int], trecho: TrechoGlifos
) -> None:
    estatistica = colheita.familias[familia]
    estatistica.trechos += 1
    estatistica.glifos_em_trecho += len(trecho.glifos)
    for indice, glifo in enumerate(trecho.glifos):
        if glifo.assinatura is None:
            if trecho.quadro_incerto:
                estatistica.excluidos += 1
            continue
        colheita.subcaminhos[glifo.assinatura.subcaminhos] += 1
        chave = _chave_da_forma(glifo.assinatura)
        if trecho.quadro_incerto:
            estatistica.excluidos += 1
            colheita.incertas.setdefault(familia, set()).add(chave)
            continue
        forma = colheita.formas.setdefault(chave, _Forma(glifo.assinatura, chave))
        forma.instancias.append(_Referencia(*ref, indice))
        forma.familias[familia] += 1
        forma.folhas.add(len(colheita.folhas) - 1)


def _colher_pdf(colheita: _Colheita, indice: int, caminho: Path) -> None:
    familia = extrair_modelo_desenho(caminho).familia.familia
    colheita.folhas.append(hash_arquivo(caminho)[:12])
    estatistica = colheita.familias.setdefault(familia, _Estatistica())
    with pymupdf.open(caminho) as documento:
        for numero in range(documento.page_count):
            caminhos = caminhos_da_pagina(documento[numero])
            estatistica.candidatos += sum(1 for c in caminhos if _eh_candidato(c))
            for posicao, trecho in enumerate(extrair_trechos(caminhos)):
                _colher_trecho(colheita, familia, (indice, numero, posicao), trecho)


def _agrupar_formas(formas: Sequence[_Forma], limiar: float) -> list[_Grupo]:
    ordenadas = sorted(formas, key=lambda f: (-len(f.instancias), f.chave))
    grupos: list[_Grupo] = []
    for forma in ordenadas:
        melhor: _Grupo | None = None
        menor = math.inf
        for grupo in grupos:
            base = grupo.representante.assinatura
            if base.subcaminhos != forma.assinatura.subcaminhos:
                continue
            if diferenca_caixa(base, forma.assinatura) > limiar:
                continue
            distancia = _distancia(base, forma.assinatura)
            if distancia <= limiar and distancia < menor:
                melhor, menor = grupo, distancia
        if melhor is None:
            grupos.append(_Grupo(forma))
        else:
            melhor.formas.append((forma, menor))
    return sorted(grupos, key=lambda g: -g.membros)


def _assinatura_json(assinatura: AssinaturaGlifo) -> Registro:
    return {
        "subcaminhos": assinatura.subcaminhos,
        "caixa": [_arredondar(v, _CASAS_JSON) for v in assinatura.caixa],
        "contornos": [
            [[_arredondar(x, _CASAS_JSON), _arredondar(y, _CASAS_JSON)] for x, y in contorno]
            for contorno in assinatura.contornos
        ],
    }


def assinatura_de_json(dados: Any) -> AssinaturaGlifo:
    try:
        contornos = tuple(
            tuple((float(x), float(y)) for x, y in contorno) for contorno in dados["contornos"]
        )
        c0, c1, c2 = (float(v) for v in dados["caixa"])
        return AssinaturaGlifo(int(dados["subcaminhos"]), (c0, c1, c2), contornos)
    except (KeyError, TypeError, ValueError) as erro:
        raise RodadaError("assinatura do grupo malformada em grupos.json") from erro


def _identificador(numero: int) -> str:
    return f"c{numero:04d}"


def _registro_do_grupo(numero: int, grupo: _Grupo, nomes: Sequence[str]) -> Registro:
    familias: Counter[str] = Counter()
    folhas: set[int] = set()
    for forma, _ in grupo.formas:
        familias.update(forma.familias)
        folhas |= forma.folhas
    return {
        "id": _identificador(numero),
        "subcaminhos": grupo.representante.assinatura.subcaminhos,
        "membros": grupo.membros,
        "familias": dict(sorted(familias.items())),
        "folhas": len({nomes[i] for i in folhas}),
        "distancia_maxima_interna": _arredondar(max(d for _, d in grupo.formas), _CASAS_JSON),
        "assinatura": _assinatura_json(grupo.representante.assinatura),
    }


def _fracao(parte: int, todo: int) -> float:
    return _arredondar(parte / todo, _CASAS_JSON) if todo else 0.0


def _h1(colheita: _Colheita, excluidas: int) -> Registro:
    certas = set(colheita.formas)
    por_familia: Registro = {}
    for familia, e in sorted(colheita.familias.items()):
        so_incertas = colheita.incertas.get(familia, set()) - certas
        por_familia[familia] = {
            "candidatos": e.candidatos,
            "trechos": e.trechos,
            "glifos_em_trecho": e.glifos_em_trecho,
            "fracao_candidatos_em_trecho": _fracao(e.glifos_em_trecho, e.candidatos),
            "glifos_excluidos_quadro_incerto": e.excluidos,
            "fracao_excluida_quadro_incerto": _fracao(e.excluidos, e.glifos_em_trecho),
            "formas_so_em_trechos_incertos": len(so_incertas),
        }
    totais = list(colheita.familias.values())
    glifos = sum(e.glifos_em_trecho for e in totais)
    excluidos = sum(e.excluidos for e in totais)
    return {
        "formato": FORMATO_H1,
        "folhas": sorted(colheita.folhas),
        "folhas_excluidas": excluidas,
        "candidatos": sum(e.candidatos for e in totais),
        "trechos": sum(e.trechos for e in totais),
        "glifos_em_trecho": glifos,
        "fracao_excluida_quadro_incerto": _fracao(excluidos, glifos),
        "distribuicao_subcaminhos": {str(n): c for n, c in sorted(colheita.subcaminhos.items())},
        "por_familia": por_familia,
    }


# --- desenho --------------------------------------------------------------------------------


def _glifo_no_quadro(
    caminho: Caminho, cosseno: float, seno: float
) -> list[list[tuple[float, float]]]:
    return [
        [
            (x * cosseno + y * seno, -x * seno + y * cosseno)
            for x, y in achatar_subcaminho(subcaminho)
        ]
        for subcaminho in caminho.subcaminhos
    ]


def _desenho(caminhos: Sequence[Caminho], trecho: TrechoGlifos, indice: int) -> Registro:
    """Glifo e vizinhos do trecho em pé (quadro do trecho), com origem em (0, 0)."""
    angulo = math.radians(trecho.rotacao)
    cosseno, seno = math.cos(angulo), math.sin(angulo)
    inicio = max(0, indice - _JANELA_CONTEXTO)
    fim = min(len(trecho.glifos), indice + _JANELA_CONTEXTO + 1)
    glifos = [
        _glifo_no_quadro(caminhos[trecho.glifos[i].indice_caminho], cosseno, seno)
        for i in range(inicio, fim)
    ]
    pontos = [p for glifo in glifos for poligono in glifo for p in poligono]
    origem_x, origem_y = min(x for x, _ in pontos), min(y for _, y in pontos)
    normalizados = [
        [
            [
                [
                    _arredondar(x - origem_x, _CASAS_DESENHO),
                    _arredondar(y - origem_y, _CASAS_DESENHO),
                ]
                for x, y in poligono
            ]
            for poligono in glifo
        ]
        for glifo in glifos
    ]
    marcado = indice - inicio
    return {
        "glifo": normalizados[marcado],
        "contexto": {"glifos": normalizados, "marcado": marcado},
    }


def _desenhos(
    pdfs: Sequence[Path], referencias: Sequence[_Referencia]
) -> dict[_Referencia, Registro]:
    """Um desenho por referência, relendo cada página uma só vez."""
    desenhos: dict[_Referencia, Registro] = {}
    ordenadas = sorted(set(referencias), key=lambda r: (r.pdf, r.pagina, r.trecho, r.glifo))
    pagina_atual: tuple[int, int] | None = None
    caminhos: tuple[Caminho, ...] = ()
    trechos: tuple[TrechoGlifos, ...] = ()
    for ref in ordenadas:
        if pagina_atual != (ref.pdf, ref.pagina):
            with pymupdf.open(pdfs[ref.pdf]) as documento:
                caminhos = caminhos_da_pagina(documento[ref.pagina])
            trechos = extrair_trechos(caminhos)
            pagina_atual = (ref.pdf, ref.pagina)
        desenhos[ref] = _desenho(caminhos, trechos[ref.trecho], ref.glifo)
    return desenhos


def _celulas(pdfs: Sequence[Path], grupos: Sequence[_Grupo]) -> list[Registro]:
    desenhos = _desenhos(
        pdfs,
        [g.representante.instancias[0] for g in grupos]
        + [g.distante.instancias[0] for g in grupos],
    )
    celulas: list[Registro] = []
    for numero, grupo in enumerate(grupos, 1):
        representante = desenhos[grupo.representante.instancias[0]]
        distante = desenhos[grupo.distante.instancias[0]]
        celulas.append(
            {
                "id": _identificador(numero),
                "membros": grupo.membros,
                "folhas": len({i for forma, _ in grupo.formas for i in forma.folhas}),
                "representante": representante["glifo"],
                "distante": distante["glifo"],
                "contexto": representante["contexto"],
            }
        )
    return celulas


def _ajustar(
    glifos: Sequence[Sequence[Poligono]], caixa: tuple[float, float, float, float]
) -> tuple[float, float, float]:
    pontos = [p for glifo in glifos for poligono in glifo for p in poligono]
    if not pontos:
        return 1.0, caixa[0], caixa[1]
    x0, x1 = min(p[0] for p in pontos), max(p[0] for p in pontos)
    y0, y1 = min(p[1] for p in pontos), max(p[1] for p in pontos)
    escala = min(
        (caixa[2] - caixa[0]) / max(x1 - x0, 1e-6), (caixa[3] - caixa[1]) / max(y1 - y0, 1e-6)
    )
    deslocamento_x = caixa[0] + ((caixa[2] - caixa[0]) - (x1 - x0) * escala) / 2.0 - x0 * escala
    deslocamento_y = caixa[1] + ((caixa[3] - caixa[1]) - (y1 - y0) * escala) / 2.0 - y0 * escala
    return escala, deslocamento_x, deslocamento_y


def _desenhar(
    pagina: Any,
    glifos: Sequence[Sequence[Poligono]],
    caixa: tuple[float, float, float, float],
    cores: Sequence[tuple[float, float, float]],
) -> None:
    pagina.draw_rect(pymupdf.Rect(*caixa), color=_CINZA, width=0.3)
    escala, dx, dy = _ajustar(glifos, caixa)
    for glifo, cor in zip(glifos, cores, strict=True):
        forma = pagina.new_shape()
        for poligono in glifo:
            forma.draw_polyline(
                [pymupdf.Point(x * escala + dx, y * escala + dy) for x, y in poligono]
            )
        forma.finish(color=None, fill=cor, even_odd=True, closePath=True)
        forma.commit()


def _desenhar_celula(pagina: Any, celula: Mapping[str, Any], coluna: int, linha: int) -> None:
    ox, oy = coluna * _LARGURA_CELULA, linha * _ALTURA_CELULA
    pagina.draw_rect(
        pymupdf.Rect(ox, oy, ox + _LARGURA_CELULA, oy + _ALTURA_CELULA), color=_PRETO, width=0.5
    )
    pagina.insert_text(
        (ox + 4, oy + 11),
        f"{celula['id']}  n={celula['membros']}  f={celula['folhas']}",
        fontsize=8,
        fontname="helv",
    )
    _desenhar(pagina, [celula["representante"]], (ox + 4, oy + 16, ox + 80, oy + 92), [_PRETO])
    _desenhar(pagina, [celula["distante"]], (ox + 90, oy + 16, ox + 166, oy + 92), [_PRETO])
    contexto = celula["contexto"]
    cores = [
        _VERMELHO if i == contexto["marcado"] else _PRETO for i in range(len(contexto["glifos"]))
    ]
    _desenhar(pagina, contexto["glifos"], (ox + 4, oy + 98, ox + 166, oy + 144), cores)


def _gravar_folha(celulas: Sequence[Mapping[str, Any]], destino: Path) -> None:
    linhas = math.ceil(len(celulas) / _COLUNAS)
    with pymupdf.open() as documento:
        pagina = documento.new_page(
            width=_COLUNAS * _LARGURA_CELULA, height=linhas * _ALTURA_CELULA
        )
        for posicao, celula in enumerate(celulas):
            _desenhar_celula(pagina, celula, posicao % _COLUNAS, posicao // _COLUNAS)
        destino.parent.mkdir(parents=True, exist_ok=True)
        pagina.get_pixmap(dpi=_DPI_FOLHA).save(destino)


def _gravar_folhas(celulas: Sequence[Mapping[str, Any]], pasta: Path) -> int:
    total = 0
    for inicio in range(0, len(celulas), GRUPOS_POR_FOLHA):
        total += 1
        _gravar_folha(celulas[inicio : inicio + GRUPOS_POR_FOLHA], pasta / f"folha-{total:03d}.png")
    return total


# --- agrupar --------------------------------------------------------------------------------


def _folhas_reservadas(arquivo: Path | None) -> set[str]:
    if arquivo is None:
        return set()
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
    except OSError as erro:
        raise RodadaError(f"lista de folhas reservadas ilegível: {arquivo.name}") from erro
    return {linha.strip().lower() for linha in linhas if linha.strip()}


def agrupar(
    pdfs_dir: Path, rodada: Path, limiar: float = LIMIAR_PADRAO, excluir_sha: Path | None = None
) -> Registro:
    if not limiar > 0:
        raise RodadaError("--limiar deve ser positivo")
    if (rodada / "grupos.json").exists():
        raise RodadaError("a rodada de glifos já existe: escolha outro diretório")
    reservadas = _folhas_reservadas(excluir_sha)
    todos = descobrir_pdfs(pdfs_dir)
    pdfs = [p for p in todos if hash_arquivo(p) not in reservadas]
    if not pdfs:
        raise RodadaError("todas as folhas estão reservadas: nada a agrupar")
    colheita = _Colheita()
    for indice, caminho in enumerate(pdfs):
        _colher_pdf(colheita, indice, caminho)
    if not colheita.formas:
        raise RodadaError("nenhum glifo em trecho de quadro confirmado nas folhas")
    grupos = _agrupar_formas(list(colheita.formas.values()), limiar)
    registros = [_registro_do_grupo(n, g, colheita.folhas) for n, g in enumerate(grupos, 1)]
    celulas = _celulas(pdfs, grupos)
    h1 = _h1(colheita, len(todos) - len(pdfs))
    h1["folhas_de_contato"] = _gravar_folhas(celulas, rodada / "contato")
    escrever_json_atomico(
        rodada / "grupos.json", {"formato": FORMATO_GRUPOS, "limiar": limiar, "grupos": registros}
    )
    escrever_json_atomico(rodada / "celulas.json", {"formato": FORMATO_CELULAS, "celulas": celulas})
    escrever_json_atomico(rodada / "h1.json", h1)
    return h1


# --- leituras -------------------------------------------------------------------------------


def _objeto(dados: Any, nome: str) -> Registro:
    if not isinstance(dados, dict):
        raise RodadaError(f"{nome} deve ser um objeto JSON")
    return dados


def _carregar_grupos(rodada: Path) -> list[Registro]:
    arquivo = rodada / "grupos.json"
    if not arquivo.is_file():
        raise RodadaError("grupos.json ausente: rode agrupar antes")
    grupos = _objeto(ler_json(arquivo), "grupos.json").get("grupos")
    if not isinstance(grupos, list):
        raise RodadaError("grupos.json malformado")
    return grupos


def _carregar_divergencias(rodada: Path) -> list[str] | None:
    arquivo = rodada / "divergencias.json"
    if not arquivo.is_file():
        return None
    grupos = _objeto(ler_json(arquivo), "divergencias.json").get("grupos")
    if not isinstance(grupos, list):
        raise RodadaError("divergencias.json malformado")
    return [str(g) for g in grupos]


def _erro_do_caractere(caractere: Any) -> str | None:
    if not isinstance(caractere, str):
        return "caractere deve ser texto"
    normal = unicodedata.normalize("NFC", caractere)
    if len(normal) != 1 or normal.isspace() or not normal.isprintable():
        return f"caractere {caractere!r} deve ser um único caractere imprimível sem espaço"
    return None


def _erros_do_rotulo(posicao: int, rotulo: Any) -> list[str]:
    nome = f"rotulos[{posicao}]"
    if not isinstance(rotulo, dict) or not isinstance(rotulo.get("grupo"), str):
        return [f"{nome} deve ser um objeto com grupo"]
    extras = set(rotulo) - {"grupo", "caractere", "marca"}
    if extras:
        return [f"{nome} tem chaves desconhecidas: {sorted(extras)}"]
    if ("caractere" in rotulo) == ("marca" in rotulo):
        return [f"{nome} deve ter exatamente um de caractere ou marca"]
    if "marca" in rotulo and rotulo["marca"] not in MARCAS:
        return [f"{nome}: marca desconhecida {rotulo['marca']!r}; use {', '.join(MARCAS)}"]
    if "caractere" in rotulo and (erro := _erro_do_caractere(rotulo["caractere"])):
        return [f"{nome}: {erro}"]
    return []


def _erros_de_cobertura(
    vistos: Sequence[str], validos: Sequence[str], conhecidos: set[str]
) -> list[str]:
    erros = [f"grupo repetido: {g}" for g, n in Counter(vistos).items() if n > 1]
    for grupo in dict.fromkeys(vistos):
        if grupo in validos:
            continue
        erros.append(
            f"grupo fora das divergências: {grupo}"
            if grupo in conhecidos
            else f"grupo desconhecido: {grupo}"
        )
    faltando = [g for g in validos if g not in set(vistos)]
    if faltando:
        mostrados = ", ".join(faltando[:_ERROS_MOSTRADOS])
        resto = (
            f" (+{len(faltando) - _ERROS_MOSTRADOS})" if len(faltando) > _ERROS_MOSTRADOS else ""
        )
        erros.append(f"grupos faltando: {mostrados}{resto}")
    return erros


def _normalizar(rotulo: Mapping[str, Any]) -> Registro:
    if "caractere" in rotulo:
        return {
            "grupo": rotulo["grupo"],
            "caractere": unicodedata.normalize("NFC", rotulo["caractere"]),
        }
    return {"grupo": rotulo["grupo"], "marca": rotulo["marca"]}


def _validos_do_leitor(rodada: Path, leitor: str, ids: list[str]) -> list[str]:
    if leitor != "c":
        return ids
    divergencias = _carregar_divergencias(rodada)
    if divergencias is None:
        raise RodadaError("divergencias.json ausente: rode consolidar antes da leitura c")
    return divergencias


def validar(rodada: Path, leitor: str, arquivo: Path) -> Registro:
    if (rodada / "consolidacao.json").exists():
        raise RodadaError("rodada já consolidada: não aceita novas leituras")
    ids = [str(g["id"]) for g in _carregar_grupos(rodada)]
    validos = _validos_do_leitor(rodada, leitor, ids)
    dados = _objeto(ler_json(arquivo), "a leitura")
    erros: list[str] = []
    if dados.get("formato") != FORMATO_LEITURA:
        erros.append(f"formato deve ser {FORMATO_LEITURA}")
    if dados.get("leitor") != leitor:
        erros.append(f"leitor do arquivo deve ser {leitor}")
    rotulos = dados.get("rotulos")
    if not isinstance(rotulos, list):
        raise RodadaError("rotulos deve ser uma lista")
    for posicao, rotulo in enumerate(rotulos):
        erros.extend(_erros_do_rotulo(posicao, rotulo))
    if not erros:
        erros.extend(_erros_de_cobertura([r["grupo"] for r in rotulos], validos, set(ids)))
    if erros:
        raise RodadaError("\nerro: ".join(erros))
    destino = rodada / "leituras" / f"leitura-{leitor}.json"
    if destino.exists():
        raise RodadaError(f"leitura {leitor} já existe e não é sobrescrita")
    copia = {
        "formato": FORMATO_LEITURA,
        "leitor": leitor,
        "rotulos": [_normalizar(r) for r in rotulos],
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("x", encoding="utf-8") as saida:
        saida.write(json_canonico(copia))
    return copia


# --- consolidar -----------------------------------------------------------------------------

_Rotulo = tuple[str, str]


def _rotulos_da_leitura(rodada: Path, leitor: str) -> dict[str, _Rotulo] | None:
    arquivo = rodada / "leituras" / f"leitura-{leitor}.json"
    if not arquivo.is_file():
        return None
    rotulos = _objeto(ler_json(arquivo), arquivo.name)["rotulos"]
    return {
        r["grupo"]: ("caractere", r["caractere"]) if "caractere" in r else ("marca", r["marca"])
        for r in rotulos
    }


def _aceito(grupo: str, rotulo: _Rotulo) -> Registro:
    return {"grupo": grupo, rotulo[0]: rotulo[1]}


def _gravar_divergencias(rodada: Path, divergentes: Sequence[str]) -> None:
    celulas = _objeto(ler_json(rodada / "celulas.json"), "celulas.json")["celulas"]
    escolhidas = [c for c in celulas if c["id"] in set(divergentes)]
    escrever_json_atomico(rodada / "divergencias.json", {"grupos": list(divergentes)})
    _gravar_folhas(escolhidas, rodada / "contato-divergencias")


def _decidir(
    ids: Sequence[str],
    a: Mapping[str, _Rotulo],
    b: Mapping[str, _Rotulo],
    c: Mapping[str, _Rotulo] | None,
) -> tuple[list[Registro], list[str]]:
    aceitos: list[Registro] = []
    pendentes: list[str] = []
    for grupo in ids:
        if a[grupo] == b[grupo]:
            aceitos.append(_aceito(grupo, a[grupo]))
        elif c is not None and c[grupo] in (a[grupo], b[grupo]):
            aceitos.append(_aceito(grupo, c[grupo]))
        else:
            pendentes.append(grupo)
    return aceitos, pendentes


def _contagens(
    aceitos: Sequence[Mapping[str, Any]], grupos: Sequence[Mapping[str, Any]]
) -> Registro:
    familias = {g["id"]: g["familias"] for g in grupos}
    contagens: dict[str, Counter[str]] = {marca: Counter() for marca in MARCAS_CONTADAS}
    for aceito in aceitos:
        if aceito.get("marca") in contagens:
            contagens[aceito["marca"]].update(familias[aceito["grupo"]])
    return {marca: dict(sorted(c.items())) for marca, c in contagens.items()}


def consolidar(rodada: Path) -> Registro | None:
    """Grava a consolidação e a devolve; `None` se a divergência espera a leitura C."""
    if (rodada / "consolidacao.json").exists():
        raise RodadaError("rodada já consolidada")
    grupos = _carregar_grupos(rodada)
    ids = [str(g["id"]) for g in grupos]
    a, b = _rotulos_da_leitura(rodada, "a"), _rotulos_da_leitura(rodada, "b")
    if a is None or b is None:
        raise RodadaError("faltam a leitura a e a leitura b: rode validar para cada leitor")
    divergentes = [g for g in ids if a[g] != b[g]]
    c = _rotulos_da_leitura(rodada, "c") if divergentes else None
    if divergentes and c is None:
        if _carregar_divergencias(rodada) is None:
            _gravar_divergencias(rodada, divergentes)
        return None
    if c is not None and _carregar_divergencias(rodada) != divergentes:
        raise RodadaError("divergencias.json não confere com as leituras a e b")
    aceitos, pendentes = _decidir(ids, a, b, c)
    consolidacao = {
        "formato": FORMATO_CONSOLIDACAO,
        "aceitos": aceitos,
        "pendentes": pendentes,
        "contagens": _contagens(aceitos, grupos),
        "concordancia_ab": {"concordantes": len(ids) - len(divergentes), "total": len(ids)},
    }
    escrever_json_atomico(rodada / "consolidacao.json", consolidacao)
    return consolidacao


# --- publicar -------------------------------------------------------------------------------


def publicar(
    rodada: Path, saida: Path, *, tolerancia: float, margem: float, espaco: float, quebra: float
) -> int:
    if saida.exists():
        raise RodadaError("a saída já existe e não é sobrescrita")
    arquivo = rodada / "consolidacao.json"
    if not arquivo.is_file():
        raise RodadaError("consolidacao.json ausente: rode consolidar antes")
    assinaturas = {
        str(g["id"]): assinatura_de_json(g["assinatura"]) for g in _carregar_grupos(rodada)
    }
    aceitos = {a["grupo"]: a for a in _objeto(ler_json(arquivo), arquivo.name)["aceitos"]}
    publicaveis = [
        (grupo, aceitos[grupo].get("caractere"))
        for grupo in assinaturas
        if grupo in aceitos and (aceitos[grupo].get("marca") in (None, "ignorar"))
    ]
    entradas = [
        EntradaGlifo(f"g{numero:04d}", caractere, assinaturas[grupo])
        for numero, (grupo, caractere) in enumerate(publicaveis, 1)
    ]
    if not entradas:
        raise RodadaError("nenhum grupo aceito com caractere ou ignorar: nada a publicar")
    texto = serializar_tabela_glifos(
        tolerancia=tolerancia,
        margem_ambiguidade=margem,
        espaco=espaco,
        quebra=quebra,
        glifos=entradas,
    )
    escrever_bytes_atomico(saida, texto.encode("utf-8"))
    try:
        carregar_tabela_glifos(saida)
    except ValueError as erro:
        saida.unlink(missing_ok=True)
        raise RodadaError(str(erro)) from erro
    return len(entradas)


# --- CLI ------------------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    comando = sub.add_parser(
        "agrupar", help="agrupa as formas de glifo e gera as folhas de contato"
    )
    comando.add_argument("--pdfs", type=Path, required=True)
    comando.add_argument("--rodada", type=Path, required=True)
    comando.add_argument("--limiar", type=float, default=LIMIAR_PADRAO)
    comando.add_argument("--excluir-sha", type=Path)
    comando = sub.add_parser("validar", help="valida e copia a leitura de um leitor")
    comando.add_argument("--rodada", type=Path, required=True)
    comando.add_argument("--leitor", required=True, choices=LEITORES)
    comando.add_argument("--arquivo", type=Path, required=True)
    comando = sub.add_parser("consolidar", help="consolida as leituras a, b e (se preciso) c")
    comando.add_argument("--rodada", type=Path, required=True)
    comando = sub.add_parser("publicar", help="escreve a tabela de glifos com os grupos aceitos")
    comando.add_argument("--rodada", type=Path, required=True)
    comando.add_argument("--saida", type=Path, required=True)
    comando.add_argument("--tolerancia", type=float, default=0.08)
    comando.add_argument("--margem", type=float, default=0.02)
    comando.add_argument("--espaco", type=float, default=0.48)
    comando.add_argument("--quebra", type=float, default=1.5)
    return parser


def _imprimir_agrupamento(h1: Mapping[str, Any]) -> None:
    print(f"ok: {h1['glifos_em_trecho']} glifos em {h1['trechos']} trechos")
    print(f"folhas de contato: {h1['folhas_de_contato']}")
    fracao = h1["fracao_excluida_quadro_incerto"]
    print(f"excluídos por quadro incerto: {fracao:.1%}")
    if fracao > LIMITE_EXCLUSAO_INCERTA:
        print("aviso: mais de 30% dos glifos em quadro incerto; decida antes dos leitores")


def _executar(args: argparse.Namespace) -> int:
    if args.comando == "agrupar":
        _imprimir_agrupamento(agrupar(args.pdfs, args.rodada, args.limiar, args.excluir_sha))
        return 0
    if args.comando == "validar":
        validar(args.rodada, args.leitor, args.arquivo)
        print(f"ok: leitura {args.leitor} válida")
        return 0
    if args.comando == "consolidar":
        consolidacao = consolidar(args.rodada)
        if consolidacao is None:
            divergentes = _carregar_divergencias(args.rodada) or []
            print(f"divergências entre a e b: {len(divergentes)}: {', '.join(divergentes)}")
            print("próximo passo: leitor c sobre contato-divergencias/")
            return CODIGO_DIVERGENCIAS
        aceitos, pendentes = len(consolidacao["aceitos"]), len(consolidacao["pendentes"])
        print(f"ok: {aceitos} aceitos, {pendentes} pendentes")
        return 0
    entradas = publicar(
        args.rodada,
        args.saida,
        tolerancia=args.tolerancia,
        margem=args.margem,
        espaco=args.espaco,
        quebra=args.quebra,
    )
    print(f"ok: tabela gravada com {entradas} entradas")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _executar(args)
    except (RodadaError, ValueError, OSError) as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
