# mypy: disable-error-code="no-untyped-call"
"""Diff por variante entre o motor declarativo e o núcleo sobre o modelo, com gasto por fase.

Uso::

    python -m scripts.diff_simbolos_nucleo_motor --rodada RODADA --saida DIR [--processos N]

Para cada folha de ``RODADA/rodada.json`` acha o PDF por ``raiz_corpus`` + ``caminho_relativo``
(recusando, antes de qualquer leitura, o caminho com o componente ``avaliacao-cega``), confere o
``sha256`` da entrada e, página a página, roda ``observar_pacotes`` (o motor),
``observar_pacotes_modelo`` (o núcleo) e ``gasto_por_fase`` com limite alto, cada um com o seu
tempo. Não lê ficha. Grava ``diff-nucleo-motor.json`` e ``diff-nucleo-motor.md`` em ``--saida``,
sem caminho absoluto nem nome de PDF: a folha é identificada só pelo ``pdf_id`` da rodada.

Comparação (R-E06.2.2.2-2), por página e variante, com as caixas cruas das observações e a chave
``(variante, índice cru)`` em multiconjunto, em passadas gulosas na ordem das observações:

1. mesma chave e caixa a até ``TOLERANCIA_CAIXA`` vão a ``ambos``;
2. do que sobra, mesma chave vai a ``geometria_diverge``;
3. do que sobra, mesma variante e caixa a até ``TOLERANCIA_CAIXA`` vão a ``indice_diverge``;
4. o resto fica em ``so_motor`` e ``so_nucleo``.

A página em que um dos lados falha (cobertura fora de ``CONCLUIDO``/``NAO_DETECCAO`` ou exceção)
sai como ``nao_comparada``, com o motivo, fora dos totais: nunca vira "só no outro". O item de
variante sensível à orientação em página girada leva ``orientacao: true`` (R-E06.2.1-7): o
triângulo em 90, 180 e 270 graus; a barra e o disco terminal (faixas) só em 90 e 270. Cada
``so_nucleo`` recebe um ``id`` opaco (``item-0001``...) na ordem da
rodada, da página e da variante; ele muda entre execuções (R-E06.2.2.2-9).

Variante de gramática só do modelo (``GRAMATICAS_SO_MODELO``, como ``stem_bars``) o motor antigo
não executa: o núcleo e o gasto recebem todas as habilitadas, mas a comparação considera só as
de ``variantes_do_motor``. As do modelo ficam fora de ``ambos`` e de ``so_*``, e o gasto as inclui.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any, Final, TypedDict, TypeVar

import pymupdf

from scripts.curation_round import RodadaError, carregar_rodada
from scripts.simbolos_corpus import (
    FolhaError,
    Registro,
    falha,
    falha_da_cobertura,
    localizar_pdf,
    medir_em_paralelo,
    recusar_rodada_cega,
    sanear,
)
from zeny_project_handler.adapters.analysis.declarative_symbols import (
    Package,
    _enabled,
    carregar_pacotes,
    perfil_pacotes,
    variantes_do_motor,
)
from zeny_project_handler.adapters.analysis.declarative_symbols import (
    observar_pacotes as observar_pacotes,
)
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.groups import _caixa_caminho
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    _GLIFOS_LIMITADOS,
    FonteGramaticaFalhou,
    PaginaGramatica,
    TetoGramaticasExcedido,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    LIMITE_CONSULTAS_PAGINA as LIMITE_CONSULTAS_PAGINA,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import gasto_por_fase
from zeny_project_handler.adapters.analysis.model_symbols import (
    observar_pacotes_modelo as observar_pacotes_modelo,
)
from zeny_project_handler.adapters.analysis.model_symbols import perfil_pacotes_modelo
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import pagina_para_gramaticas
from zeny_project_handler.domain.symbols import PerfilMetodoSimbolos, ResultadoMetodoSimbolos

ESQUEMA: Final = "diff-nucleo-motor-v1"
LIMITE_MEDICAO: Final = 10**12
TOLERANCIA_CAIXA: Final = 0.5
MAXIMO_PROCESSOS: Final = 61
CATEGORIAS: Final = ("ambos", "so_motor", "so_nucleo", "indice_diverge", "geometria_diverge")

# R-E06.2.1-7: estas gramáticas leem a página visual. A barra e as faixas do disco (o disco por
# curva casa nos dois e cai em `ambos`) continuam em pé a 180 graus (emenda de R-E06.2.2.2-2).
_SENSIVEIS_A_ORIENTACAO: Final = frozenset(
    {"triangle_in_frame", "nested_rectangles_bar", "terminal_disc"}
)
_EM_PE_A_180: Final = frozenset({"nested_rectangles_bar", "terminal_disc"})

_T = TypeVar("_T")


# --- comparação pura --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Observada:
    """Uma observação de um dos lados, com a caixa crua (página sem rotação)."""

    variante: str
    classe: str | None
    indice_cru: int
    bbox: Caixa


@dataclass(frozen=True, slots=True)
class Par:
    motor: Observada
    nucleo: Observada


class Comparacao(TypedDict):
    ambos: list[Par]
    so_motor: list[Observada]
    so_nucleo: list[Observada]
    indice_diverge: list[Par]
    geometria_diverge: list[Par]


def _perto(a: Observada, b: Observada) -> bool:
    return max(abs(x - y) for x, y in zip(a.bbox, b.bbox, strict=True)) <= TOLERANCIA_CAIXA


def _mesmo_indice(a: Observada, b: Observada) -> bool:
    return a.indice_cru == b.indice_cru


def _parear(
    motor: Sequence[Observada],
    nucleo: Sequence[Observada],
    criterio: Callable[[Observada, Observada], bool],
) -> tuple[list[Par], list[Observada], list[Observada]]:
    """Pareamento 1-1 guloso na ordem do núcleo; devolve os pares e as sobras dos dois lados."""
    livres = list(motor)
    pares: list[Par] = []
    sobra: list[Observada] = []
    for observada in nucleo:
        posicao = next((i for i, outra in enumerate(livres) if criterio(outra, observada)), None)
        if posicao is None:
            sobra.append(observada)
        else:
            pares.append(Par(livres.pop(posicao), observada))
    return pares, livres, sobra


def _comparar_variante(motor: Sequence[Observada], nucleo: Sequence[Observada]) -> Comparacao:
    ambos, motor_1, nucleo_1 = _parear(
        motor, nucleo, lambda a, b: _mesmo_indice(a, b) and _perto(a, b)
    )
    geometria, motor_2, nucleo_2 = _parear(motor_1, nucleo_1, _mesmo_indice)
    indice, so_motor, so_nucleo = _parear(motor_2, nucleo_2, _perto)
    return {
        "ambos": ambos,
        "so_motor": so_motor,
        "so_nucleo": so_nucleo,
        "indice_diverge": indice,
        "geometria_diverge": geometria,
    }


def comparar_observacoes(
    motor: Sequence[Observada], nucleo: Sequence[Observada]
) -> dict[str, Comparacao]:
    """Por variante (em ordem), as passadas de R-E06.2.2.2-2 sobre as observações de uma página."""
    variantes = sorted({observada.variante for observada in (*motor, *nucleo)})
    return {
        variante: _comparar_variante(
            [o for o in motor if o.variante == variante],
            [o for o in nucleo if o.variante == variante],
        )
        for variante in variantes
    }


def sensivel_a_orientacao(gramatica: str, rotacao: int) -> bool:
    """A variante diverge por decisão (R-E06.2.1-7) quando a página não está em pé para ela."""
    if gramatica not in _SENSIVEIS_A_ORIENTACAO or rotacao % 360 == 0:
        return False
    return not (gramatica in _EM_PE_A_180 and rotacao % 360 == 180)


def observadas(resultado: ResultadoMetodoSimbolos) -> list[Observada]:
    """Observações do resultado, na ordem dele, com a caixa crua de ``pontos_originais``."""
    return [
        Observada(
            variante=str(observacao.template),
            classe=observacao.alternativas[0].classe,
            indice_cru=int(observacao.primitivas[0].indice),
            bbox=_caixa_dos_pontos(observacao.geometria.pontos_originais),
        )
        for observacao in resultado.observacoes
    ]


def _caixa_dos_pontos(pontos: Sequence[tuple[Any, Any]]) -> Caixa:
    xs = [float(x) for x, _ in pontos]
    ys = [float(y) for _, y in pontos]
    return (min(xs), min(ys), max(xs), max(ys))


# --- item -------------------------------------------------------------------------------


class TextoNaCaixa(TypedDict):
    texto: str
    origem: str
    rotacao: float


class Item(TypedDict):
    """Um ``so_nucleo``: o ``id`` é posto depois, na ordem da rodada."""

    id: str | None
    pagina: int
    variante: str
    classe: str | None
    indice_cru: int
    bbox: list[float]
    textos: list[TextoNaCaixa]
    glifos_lidos: list[int]
    diagnosticos: list[str]
    orientacao: bool


def _bbox(caixa: Caixa) -> list[float]:
    return [round(valor, 3) for valor in caixa]


def _intersecta(a: Caixa, b: Caixa) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def caixa_visual(page: pymupdf.Page, caixa_crua: Caixa) -> Caixa:
    """A caixa crua na página visual, o espaço do modelo de desenho."""
    visual = (pymupdf.Rect(caixa_crua) * page.rotation_matrix).normalize()
    return (float(visual.x0), float(visual.y0), float(visual.x1), float(visual.y1))


def item_so_nucleo(
    observada: Observada,
    pagina_numero: int,
    page: pymupdf.Page,
    pagina: PaginaGramatica,
    orientacao: bool,
) -> Item:
    """O item com o que o modelo tem na caixa: textos (origem e rotação), glifos lidos (índices
    crus) e os diagnósticos da página."""
    visual = caixa_visual(page, observada.bbox)
    modelo = pagina.modelo
    return {
        "id": None,
        "pagina": pagina_numero,
        "variante": observada.variante,
        "classe": observada.classe,
        "indice_cru": observada.indice_cru,
        "bbox": _bbox(observada.bbox),
        "textos": [
            {"texto": texto.texto, "origem": texto.origem, "rotacao": texto.rotacao}
            for texto in modelo.textos
            if _intersecta(texto.bbox, visual)
        ],
        "glifos_lidos": sorted(
            pagina.indices_crus[posicao]
            for posicao in pagina.glifos_lidos
            if _intersecta(_caixa_caminho(modelo.caminhos[posicao]), visual)
        ),
        "diagnosticos": list(modelo.diagnosticos),
        "orientacao": orientacao,
    }


def _observada_em_registro(observada: Observada, pagina: int, orientacao: bool) -> Registro:
    return {
        "pagina": pagina,
        "variante": observada.variante,
        "classe": observada.classe,
        "indice_cru": observada.indice_cru,
        "bbox": _bbox(observada.bbox),
        "orientacao": orientacao,
    }


def _par_em_registro(par: Par, pagina: int, orientacao: bool) -> Registro:
    return {
        "pagina": pagina,
        "variante": par.nucleo.variante,
        "classe": par.nucleo.classe,
        "motor": {"indice_cru": par.motor.indice_cru, "bbox": _bbox(par.motor.bbox)},
        "nucleo": {"indice_cru": par.nucleo.indice_cru, "bbox": _bbox(par.nucleo.bbox)},
        "orientacao": orientacao,
    }


# --- página ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Recursos:
    pacotes: tuple[Package, ...]
    variantes: tuple[tuple[Package, Package], ...]
    gramaticas: Mapping[str, str]
    tabela: TabelaGlifos
    perfil_nucleo: PerfilMetodoSimbolos


@cache
def recursos() -> Recursos:
    """Pacotes, tabela de glifos e perfil do núcleo, uma vez por processo."""
    pacotes = carregar_pacotes()
    tabela = carregar_tabela_glifos()
    variantes = _enabled(pacotes)
    return Recursos(
        pacotes=pacotes,
        variantes=variantes,
        gramaticas={
            str(variante["id"]): str(variante["recognition"]["grammar"]["kind"])
            for _, variante in variantes
        },
        tabela=tabela,
        perfil_nucleo=perfil_pacotes_modelo(pacotes, tabela),
    )


@dataclass(frozen=True, slots=True)
class Folha:
    pdf_id: str
    sha256: str
    ocultar: tuple[str, ...]


def _cronometrar(
    funcao: Callable[[], _T], ocultar: Sequence[str]
) -> tuple[_T | None, float, str | None]:
    inicio = perf_counter()
    try:
        resultado = funcao()
    except Exception as erro:
        return None, perf_counter() - inicio, sanear(f"{type(erro).__name__}: {erro}", ocultar)
    return resultado, perf_counter() - inicio, None


def _medir_gasto(
    pagina: PaginaGramatica, variantes: Sequence[tuple[Package, Package]]
) -> tuple[Registro | None, str | None, float]:
    """Gasto real por fase, mesmo acima do teto; ``None`` e o motivo quando o núcleo não mede."""
    inicio = perf_counter()
    try:
        gasto = gasto_por_fase(pagina, variantes, limite=LIMITE_MEDICAO)
    except FonteGramaticaFalhou as erro:
        return None, f"fonte_falhou:{erro.codigo}", perf_counter() - inicio
    except TetoGramaticasExcedido:
        limitados = _GLIFOS_LIMITADOS in pagina.modelo.diagnosticos
        motivo = "glifos_limitados" if limitados else "teto_consultas"
        return None, motivo, perf_counter() - inicio
    registro: Registro = {
        "colagem": gasto.colagem,
        "indices": gasto.indices,
        "gramaticas": gasto.gramaticas,
        "total": gasto.total,
    }
    return registro, None, perf_counter() - inicio


def _cobertura(resultado: ResultadoMetodoSimbolos | None) -> Registro | None:
    if resultado is None:
        return None
    cobertura = resultado.coberturas[0]
    return {"estado": cobertura.estado.value, "motivo": cobertura.motivo}


def _falha_do_lado(
    lado: str,
    resultado: ResultadoMetodoSimbolos | None,
    erro: str | None,
    ocultar: Sequence[str],
) -> str | None:
    if erro is not None:
        return f"{lado}: {erro}"
    assert resultado is not None
    motivos = (falha_da_cobertura(cobertura) for cobertura in resultado.coberturas)
    motivo = next((item for item in motivos if item is not None), None)
    return None if motivo is None else f"{lado}: {sanear(motivo, ocultar)}"


def _variantes_em_registro(
    comparacao: Mapping[str, Comparacao],
    pagina_numero: int,
    page: pymupdf.Page,
    pagina: PaginaGramatica,
    gramaticas: Mapping[str, str],
) -> Registro:
    registro: Registro = {}
    for variante, categorias in comparacao.items():
        orientacao = sensivel_a_orientacao(gramaticas.get(variante, ""), page.rotation)
        registro[variante] = {
            "ambos": [
                {"indice_cru": par.nucleo.indice_cru, "bbox": _bbox(par.nucleo.bbox)}
                for par in categorias["ambos"]
            ],
            "so_motor": [
                _observada_em_registro(o, pagina_numero, orientacao) for o in categorias["so_motor"]
            ],
            "so_nucleo": [
                item_so_nucleo(o, pagina_numero, page, pagina, orientacao)
                for o in categorias["so_nucleo"]
            ],
            "indice_diverge": [
                _par_em_registro(par, pagina_numero, orientacao)
                for par in categorias["indice_diverge"]
            ],
            "geometria_diverge": [
                _par_em_registro(par, pagina_numero, orientacao)
                for par in categorias["geometria_diverge"]
            ],
        }
    return registro


def medir_pagina(page: pymupdf.Page, pagina_numero: int, folha: Folha) -> Registro:
    """Motor, núcleo e gasto de uma página, cada um com o seu tempo; compara se os dois servem."""
    meios = recursos()
    motor, tempo_motor, erro_motor = _cronometrar(
        lambda: observar_pacotes(
            page,
            documento_id=folha.pdf_id,
            documento_sha256=folha.sha256,
            pagina_numero=pagina_numero,
            pacotes=meios.pacotes,
        ),
        folha.ocultar,
    )
    nucleo, tempo_nucleo, erro_nucleo = _cronometrar(
        lambda: observar_pacotes_modelo(
            page,
            documento_id=folha.pdf_id,
            documento_sha256=folha.sha256,
            pagina_numero=pagina_numero,
            pacotes=meios.pacotes,
            tabela=meios.tabela,
            perfil=meios.perfil_nucleo,
        ),
        folha.ocultar,
    )
    pagina = pagina_para_gramaticas(page, pagina_numero - 1, meios.tabela)
    gasto, gasto_motivo, tempo_gasto = _medir_gasto(pagina, meios.variantes)
    falhas = [
        motivo
        for motivo in (
            _falha_do_lado("motor", motor, erro_motor, folha.ocultar),
            _falha_do_lado("nucleo", nucleo, erro_nucleo, folha.ocultar),
        )
        if motivo is not None
    ]
    variantes: Registro = {}
    if not falhas and motor is not None and nucleo is not None:
        ids_motor = {str(variante["id"]) for _, variante in variantes_do_motor(meios.pacotes)}
        comparacao = comparar_observacoes(
            observadas(motor), [o for o in observadas(nucleo) if o.variante in ids_motor]
        )
        variantes = _variantes_em_registro(
            comparacao, pagina_numero, page, pagina, meios.gramaticas
        )
    return {
        "pagina": pagina_numero,
        "rotacao": page.rotation,
        "situacao": "nao_comparada" if falhas else "comparada",
        "motivo": "; ".join(falhas) if falhas else None,
        "cobertura": {"motor": _cobertura(motor), "nucleo": _cobertura(nucleo)},
        "variantes": variantes,
        "gasto": gasto,
        "gasto_motivo": gasto_motivo,
        "tempo_s": {"motor": tempo_motor, "nucleo": tempo_nucleo, "gasto": tempo_gasto},
    }


# --- folha --------------------------------------------------------------------------------


def _ocultar(rodada: Path, raiz_corpus: str, caminho_relativo: str) -> tuple[str, ...]:
    pdf = rodada / raiz_corpus / caminho_relativo
    normalizado = Path(os.path.normpath(pdf))
    nome = Path(caminho_relativo).name
    return (
        str(rodada),
        rodada.as_posix(),
        caminho_relativo,
        str(pdf),
        pdf.as_posix(),
        str(normalizado),
        normalizado.as_posix(),
        nome,
        Path(nome).stem,
    )


@contextmanager
def abrir_folha(
    rodada: Path, raiz_corpus: str, entrada: Mapping[str, Any]
) -> Iterator[pymupdf.Document]:
    """O documento da folha: guarda do conjunto cego antes de qualquer acesso, existência e o
    ``sha256`` da entrada do ``rodada.json``, conferido sobre os mesmos bytes que se abrem."""
    pdf = localizar_pdf(rodada, raiz_corpus, str(entrada["caminho_relativo"]))
    esperado = entrada.get("sha256")
    if not isinstance(esperado, str) or not esperado:
        raise FolhaError("entrada do rodada.json sem sha256")
    if not pdf.is_file():
        raise FolhaError("PDF não encontrado no corpus da rodada")
    dados = pdf.read_bytes()
    if sha256(dados).hexdigest() != esperado.lower():
        raise FolhaError("sha256 do PDF difere do sha256 do rodada.json")
    with pymupdf.open("pdf", dados) as documento:
        yield documento


def _somar(paginas: Sequence[Registro]) -> Registro:
    comparadas = [pagina for pagina in paginas if pagina["situacao"] == "comparada"]
    totais: Registro = {
        categoria: sum(
            len(variante[categoria])
            for pagina in comparadas
            for variante in pagina["variantes"].values()
        )
        for categoria in CATEGORIAS
    }
    totais["paginas_comparadas"] = len(comparadas)
    totais["paginas_nao_comparadas"] = len(paginas) - len(comparadas)
    return totais


def _gasto_maximo(paginas: Sequence[Registro]) -> Registro | None:
    medidas = [pagina for pagina in paginas if pagina["gasto"] is not None]
    if not medidas:
        return None
    maior = max(medidas, key=lambda pagina: int(pagina["gasto"]["total"]))
    total = int(maior["gasto"]["total"])
    return {
        "pagina": maior["pagina"],
        **maior["gasto"],
        "razao_limite": total / LIMITE_CONSULTAS_PAGINA,
    }


def medir_documento(documento: pymupdf.Document, folha: Folha) -> Registro:
    paginas = [
        medir_pagina(documento.load_page(indice), indice + 1, folha)
        for indice in range(documento.page_count)
    ]
    return {
        "situacao": "ok",
        "paginas": paginas,
        "totais": _somar(paginas),
        "gasto_maximo": _gasto_maximo(paginas),
        "tempo_s": {
            chave: sum(float(pagina["tempo_s"][chave]) for pagina in paginas)
            for chave in ("motor", "nucleo", "gasto")
        },
    }


@dataclass(frozen=True, slots=True)
class _Tarefa:
    rodada: Path
    raiz_corpus: str
    entrada: Registro


def _medir_folha(tarefa: _Tarefa) -> Registro:
    caminho_relativo = str(tarefa.entrada.get("caminho_relativo", ""))
    ocultar = _ocultar(tarefa.rodada, tarefa.raiz_corpus, caminho_relativo)
    folha = Folha(str(tarefa.entrada["pdf_id"]), str(tarefa.entrada.get("sha256", "")), ocultar)
    try:
        with abrir_folha(tarefa.rodada, tarefa.raiz_corpus, tarefa.entrada) as documento:
            return medir_documento(documento, folha)
    except FolhaError as erro:
        return falha(str(erro))
    except Exception as erro:
        return falha(sanear(f"{type(erro).__name__}: {erro}", ocultar))


# --- rodada -------------------------------------------------------------------------------


def _numerar_itens(por_pdf: Mapping[str, Registro]) -> None:
    """``id`` opaco de cada ``so_nucleo``, na ordem da rodada, da página e da variante."""
    contador = 0
    for folha in por_pdf.values():
        for pagina in folha.get("paginas", ()):
            for variante in sorted(pagina["variantes"]):
                for item in pagina["variantes"][variante]["so_nucleo"]:
                    contador += 1
                    item["id"] = f"item-{contador:04d}"


def _total(por_pdf: Mapping[str, Registro]) -> Registro:
    chaves = (*CATEGORIAS, "paginas_comparadas", "paginas_nao_comparadas")
    folhas = [folha for folha in por_pdf.values() if folha["situacao"] == "ok"]
    total: Registro = {chave: sum(int(f["totais"][chave]) for f in folhas) for chave in chaves}
    total["folhas_falha"] = len(por_pdf) - len(folhas)
    return total


def _opcoes() -> Registro:
    meios = recursos()
    motor = perfil_pacotes(meios.pacotes)
    return {
        "limite_medicao": LIMITE_MEDICAO,
        "limite_consultas_pagina": LIMITE_CONSULTAS_PAGINA,
        "tolerancia_caixa": TOLERANCIA_CAIXA,
        "metodos": {
            lado: {
                "metodo_id": perfil.metodo_id,
                "versao": perfil.versao,
                "assinatura": perfil.assinatura(),
            }
            for lado, perfil in (("motor", motor), ("nucleo", meios.perfil_nucleo))
        },
        "tabela_glifos": {"versao": meios.tabela.versao, "sha256": meios.tabela.sha256},
        "pymupdf": str(pymupdf.VersionBind),
    }


def medir_diff(rodada: Path, saida: Path, *, processos: int = 1) -> Registro:
    """Compara motor e núcleo nas folhas da rodada e grava ``diff-nucleo-motor.json`` e ``.md``."""
    if processos < 1:
        raise ValueError("processos precisa ser >= 1")
    # Antes de ler o rodada.json: rodada dentro da pasta cega não se abre.
    recusar_rodada_cega(rodada)
    manifesto = carregar_rodada(rodada)
    raiz_corpus = str(manifesto["raiz_corpus"])
    tarefas = [_Tarefa(rodada, raiz_corpus, dict(entrada)) for entrada in manifesto["pdfs"]]
    efetivos = min(processos, len(tarefas), MAXIMO_PROCESSOS)
    medidas = medir_em_paralelo(_medir_folha, tarefas, efetivos, ProcessPoolExecutor)
    por_pdf = {
        str(tarefa.entrada["pdf_id"]): medida
        for tarefa, medida in zip(tarefas, medidas, strict=True)
    }
    _numerar_itens(por_pdf)
    relatorio: Registro = {
        "schema_version": ESQUEMA,
        "opcoes": _opcoes(),
        "por_pdf": por_pdf,
        "total": _total(por_pdf),
    }
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "diff-nucleo-motor.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (saida / "diff-nucleo-motor.md").write_text(
        markdown(relatorio, processos, efetivos), encoding="utf-8"
    )
    return relatorio


# --- markdown -----------------------------------------------------------------------------


def _paginas_ok(relatorio: Registro) -> Iterator[tuple[str, Registro]]:
    for pdf_id, folha in relatorio["por_pdf"].items():
        for pagina in folha.get("paginas", ()):
            yield pdf_id, pagina


def _linha_item(pdf_id: str, item: Mapping[str, Any]) -> str:
    textos = ", ".join(
        f"{json.dumps(t['texto'], ensure_ascii=False)} ({t['origem']}, {t['rotacao']:g}°)"
        for t in item["textos"]
    )
    return (
        f"- `{item['id']}` · {pdf_id} · p. {item['pagina']} · `{item['variante']}` · "
        f"classe {item['classe']} · índice cru {item['indice_cru']} · bbox {item['bbox']} · "
        f"orientação {'sim' if item['orientacao'] else 'não'} · "
        f"textos: {textos or '—'} · glifos lidos: {len(item['glifos_lidos'])} · "
        f"diagnósticos: {', '.join(item['diagnosticos']) or '—'}"
    )


def _secao_so_nucleo(relatorio: Registro) -> list[str]:
    linhas = [
        _linha_item(pdf_id, item)
        for pdf_id, pagina in _paginas_ok(relatorio)
        for variante in sorted(pagina["variantes"])
        for item in pagina["variantes"][variante]["so_nucleo"]
    ]
    return ["## Só no núcleo", "", *(linhas or ["Nenhum."]), ""]


def _por_variante(relatorio: Registro) -> dict[str, dict[str, int]]:
    contagem: dict[str, dict[str, int]] = {}
    for _, pagina in _paginas_ok(relatorio):
        for variante, categorias in pagina["variantes"].items():
            linha = contagem.setdefault(
                variante, {"so_motor": 0, "orientacao": 0, "indice": 0, "geometria": 0}
            )
            linha["so_motor"] += len(categorias["so_motor"])
            linha["orientacao"] += sum(bool(i["orientacao"]) for i in categorias["so_motor"])
            linha["indice"] += len(categorias["indice_diverge"])
            linha["geometria"] += len(categorias["geometria_diverge"])
    return contagem


def _secao_por_variante(relatorio: Registro) -> list[str]:
    contagem = _por_variante(relatorio)
    so_motor = [
        f"| `{variante}` | {linha['so_motor']} | {linha['orientacao']} |"
        for variante, linha in sorted(contagem.items())
        if linha["so_motor"]
    ]
    divergencias = [
        f"| `{variante}` | {linha['indice']} | {linha['geometria']} |"
        for variante, linha in sorted(contagem.items())
        if linha["indice"] or linha["geometria"]
    ]
    tabela_so_motor = ["| variante | so_motor | com orientação |", "|---|---:|---:|", *so_motor]
    return [
        "## Só no motor, por variante",
        "",
        *(tabela_so_motor if so_motor else ["Nenhum."]),
        "",
        "## Índice e geometria divergentes, por variante",
        "",
        "| variante | indice_diverge | geometria_diverge |",
        "|---|---:|---:|",
        *(divergencias or ["| — | 0 | 0 |"]),
        "",
    ]


def _secao_falhas(relatorio: Registro) -> list[str]:
    paginas = [
        f"- {pdf_id} · p. {pagina['pagina']}: {pagina['motivo']}"
        for pdf_id, pagina in _paginas_ok(relatorio)
        if pagina["situacao"] == "nao_comparada"
    ]
    folhas = [
        f"- {pdf_id}: {folha['erro']}"
        for pdf_id, folha in relatorio["por_pdf"].items()
        if folha["situacao"] != "ok"
    ]
    return [
        "## Páginas não comparadas (fora dos totais)",
        "",
        *(paginas or ["Nenhuma."]),
        "",
        "## Folhas com falha",
        "",
        *(folhas or ["Nenhuma."]),
        "",
    ]


def _linha_gasto(pdf_id: str, folha: Registro) -> str:
    motivos = sorted({str(p["gasto_motivo"]) for p in folha["paginas"] if p["gasto"] is None})
    sem_gasto = ", ".join(motivos) or "—"
    tempo = f"{float(folha['tempo_s']['gasto']):.3f}"
    maximo = folha["gasto_maximo"]
    if maximo is None:
        return f"| {pdf_id} | — | — | — | — | — | — | {tempo} | {sem_gasto} |"
    return (
        f"| {pdf_id} | {maximo['pagina']} | {maximo['colagem']} | {maximo['indices']} | "
        f"{maximo['gramaticas']} | {maximo['total']} | {maximo['razao_limite']:.6f} | {tempo} | "
        f"{sem_gasto} |"
    )


def _secao_gasto(relatorio: Registro) -> list[str]:
    linhas = [
        _linha_gasto(pdf_id, folha)
        for pdf_id, folha in relatorio["por_pdf"].items()
        if folha["situacao"] == "ok"
    ]
    return [
        "## Gasto do núcleo por folha (página de maior total)",
        "",
        f"Razão contra `LIMITE_CONSULTAS_PAGINA` = {LIMITE_CONSULTAS_PAGINA}; medição com limite "
        f"{LIMITE_MEDICAO}. `tempo_s` é o de `gasto_por_fase` somado na folha.",
        "",
        "| folha | página | colagem | índices | gramáticas | total | razão | tempo_s | sem gasto |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        *linhas,
        "",
    ]


def markdown(relatorio: Registro, processos: int, efetivos: int) -> str:
    total = relatorio["total"]
    cabecalho = [
        "# Diff de símbolos: núcleo contra motor",
        "",
        f"Esquema `{relatorio['schema_version']}`. Chave `(página, variante, índice cru)` em "
        f"multiconjunto, caixa crua a até {TOLERANCIA_CAIXA} pt. Processos: {processos} pedidos, "
        f"{efetivos} efetivos.",
        "",
        "## Totais (páginas comparadas)",
        "",
        "| ambos | so_motor | so_nucleo | indice_diverge | geometria_diverge | comparadas | "
        "não comparadas | folhas com falha |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {total['ambos']} | {total['so_motor']} | {total['so_nucleo']} | "
        f"{total['indice_diverge']} | {total['geometria_diverge']} | "
        f"{total['paginas_comparadas']} | {total['paginas_nao_comparadas']} | "
        f"{total['folhas_falha']} |",
        "",
    ]
    return "\n".join(
        [
            *cabecalho,
            *_secao_so_nucleo(relatorio),
            *_secao_por_variante(relatorio),
            *_secao_falhas(relatorio),
            *_secao_gasto(relatorio),
        ]
    )


# --- CLI ----------------------------------------------------------------------------------


def _inteiro_positivo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"não é inteiro: {texto!r}") from None
    if valor < 1:
        raise argparse.ArgumentTypeError("precisa ser >= 1")
    return valor


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rodada", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--processos", type=_inteiro_positivo, default=1)
    opcoes = parser.parse_args(argumentos)
    try:
        medir_diff(opcoes.rodada, opcoes.saida, processos=opcoes.processos)
    except RodadaError as erro:
        parser.exit(1, f"{erro}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
