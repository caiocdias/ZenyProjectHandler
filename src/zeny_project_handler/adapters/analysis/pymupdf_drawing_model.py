# mypy: disable-error-code="no-untyped-call"
"""Leitura PyMuPDF do modelo de desenho: caminhos, textos, imagens e família do documento.

Tudo sai no espaço da página visual (`page.rotation_matrix` aplicada, y para baixo). Cada
fonte de uma página é uma unidade de falha: a exceção vira `modelo.<fonte>_falhou` em
`PaginaModelo.diagnosticos`, a fonte fica vazia e o resto continua. Com uma tabela de glifos,
o texto desenhado como contorno de glifo entra em `PaginaModelo.textos` com origem "glifo".
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, TypeVar, cast

import pymupdf

from .drawing_model.cache import JsonDrawingModelCache, chave_modelo_desenho
from .drawing_model.family import ImpressaoEstrutural, reconhecer_familia
from .drawing_model.geometry import reconstruir_polilinhas, recuperar_circulos_e_arcos
from .drawing_model.glyph_table import TabelaGlifos
from .drawing_model.glyph_text import LeituraGlifos, ler_texto_glifos
from .drawing_model.groups import agrupar_candidatos
from .drawing_model.model import (
    VERSAO_MODELO_DESENHO,
    Arco,
    Caixa,
    Caminho,
    Circulo,
    Cor,
    Estilo,
    GrupoCandidato,
    ImagemModelo,
    ItemCaminho,
    ModeloDesenho,
    PaginaModelo,
    Polilinha,
    Ponto,
    TextoModelo,
)
from .drawing_model.symbol_grammars import PaginaGramatica
from .pymupdf_annotations import (
    _annotation_info,
    _annotation_subtype,
    _appearance_objects,
    _appearance_roots,
    _is_technical_annotation,
)
from .pymupdf_glyphs import _is_glyph, _path_points
from .pymupdf_page_extractors import _native_textpage
from .pymupdf_support import _optional_string

_TIPOS_CAMINHO: Final[dict[str, Literal["traco", "preenchimento", "traco_e_preenchimento"]]] = {
    "s": "traco",
    "f": "preenchimento",
    "fs": "traco_e_preenchimento",
}
_PROFUNDIDADE_APARENCIA: Final = 12
# Preenchimento com opacidade abaixo disso deixa ver o que está por baixo.
_OPACIDADE_OPACA: Final = 0.99
_CELULA_TEXTO: Final = 20.0
_MAXIMO_CELULAS_TEXTO: Final = 256
_MARGEM_TEXTO: Final = 2.0
# Teto de pixels (/Width x /Height declarados) para decodificar a imagem de um /AP só pelo
# digest: acima dele, a identidade é o sha256 do fluxo bruto, sem decodificar (PDF hostil).
# Mesma ordem de grandeza de MAXIMUM_GLYPH_PIXELS.
_MAXIMO_PIXELS_IMAGEM_ANOTACAO: Final = 16_000_000
# Elos de referência indireta seguidos ao ler /Width e /Height; além disso, ou num ciclo, a
# dimensão é desconhecida e a imagem vai pelo fluxo bruto.
_PROFUNDIDADE_REFERENCIA: Final = 32
_NUMERO_PDF: Final = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)")
_REFERENCIA_PDF: Final = re.compile(r"(\d+) \d+ R")

_T = TypeVar("_T")
_Transformar = Callable[[Any], Ponto]
_CaminhosLidos = tuple[tuple[Caminho, ...], tuple[int, ...], frozenset[int], int, int]


@dataclass(slots=True)
class _Fontes:
    caminhos: tuple[Caminho, ...] = ()
    indices_crus: tuple[int, ...] = ()
    translucidos: frozenset[int] = frozenset()
    total_desenhos: int = 0
    formas_glifo: int = 0
    textos_nativos: tuple[TextoModelo, ...] = ()
    textos_shx: tuple[TextoModelo, ...] = ()
    anotacoes_shx: int = 0
    imagens: tuple[ImagemModelo, ...] = ()
    diagnosticos: list[str] = field(default_factory=list)


class _DesenhosFiltrados(list[dict[str, Any]]):
    """Desenhos de traço/preenchimento, com a posição de cada um em `get_drawings`."""

    indices_crus: tuple[int, ...]

    def __init__(self, filtrados: Iterable[tuple[int, dict[str, Any]]]) -> None:
        pares = list(filtrados)
        super().__init__(desenho for _, desenho in pares)
        self.indices_crus = tuple(indice for indice, _ in pares)


@dataclass(slots=True)
class _Contagens:
    spans_texto_nativo: int = 0
    formas_glifo: int = 0
    anotacoes_shx: int = 0
    imagens: int = 0

    def somar(self, fontes: _Fontes) -> None:
        self.spans_texto_nativo += len(fontes.textos_nativos)
        self.formas_glifo += fontes.formas_glifo
        self.anotacoes_shx += fontes.anotacoes_shx
        self.imagens += len(fontes.imagens)


def pagina_modelo_com_indices(
    pagina: pymupdf.Page, indice: int, tabela: TabelaGlifos | None = None
) -> tuple[PaginaModelo, tuple[int, ...]]:
    """Página `indice` do modelo e, por caminho, a posição do desenho de origem em `get_drawings`.

    O modelo é o mesmo de `extrair_modelo_desenho(...).paginas[indice]`. `caminhos[i]` veio do
    desenho cru `indices[i]`: `get_drawings` traz também `clip` e `group`, que o modelo descarta.
    """
    fontes = _ler_fontes(pagina)
    return _montar_pagina(indice, pagina, fontes, tabela), fontes.indices_crus


def pagina_para_gramaticas(
    pagina: pymupdf.Page, indice: int, tabela: TabelaGlifos | None = None
) -> PaginaGramatica:
    """Página `indice` do modelo para as gramáticas de símbolos.

    Além do modelo, traz por caminho a posição do desenho de origem em `get_drawings` e quais
    caminhos são translúcidos (posições em `modelo.caminhos`).
    """
    fontes = _ler_fontes(pagina)
    return PaginaGramatica(
        _montar_pagina(indice, pagina, fontes, tabela), fontes.indices_crus, fontes.translucidos
    )


def impressao_estrutural(documento: pymupdf.Document) -> ImpressaoEstrutural:
    contagens = _Contagens()
    for indice in range(documento.page_count):
        contagens.somar(_ler_fontes(documento.load_page(indice)))
    return _impressao(documento, contagens)


def _sha256_do_arquivo(pdf: Path) -> str:
    with pdf.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest()


def obter_modelo_desenho(
    pdf: Path, cache: JsonDrawingModelCache | None, tabela: TabelaGlifos | None = None
) -> ModeloDesenho:
    """Modelo do cache ou extraído; `tabela=None` não lê texto de glifo."""
    if cache is None:
        return _extrair(pdf, tabela)
    sha = _sha256_do_arquivo(pdf)
    chave = chave_modelo_desenho(sha, _versao_leitor(tabela))
    try:
        em_cache = cache.obter(chave)
    except Exception:
        em_cache = None
    # A extração refaz o hash; se o arquivo mudou entre as leituras, a chave não vale.
    if em_cache is not None and em_cache.documento_sha256 == sha:
        return em_cache
    modelo = _extrair(pdf, tabela)
    if modelo.documento_sha256 == sha and not _tem_fonte_falha(modelo):
        # o cache é descartável: falha de gravação não derruba a extração
        with suppress(Exception):
            cache.salvar(chave, modelo)
    return modelo


def _versao_leitor(tabela: TabelaGlifos | None) -> str:
    """Identidade do leitor na chave do cache: a versão da PyMuPDF e o conteúdo da tabela."""
    leitor = f"pymupdf-{pymupdf.VersionBind}"
    return leitor if tabela is None else f"{leitor}:glifos-{tabela.sha256}"


def _extrair(pdf: Path, tabela: TabelaGlifos | None) -> ModeloDesenho:
    # sem tabela, a chamada é a de um argumento, a mesma de antes da leitura de glifos
    return extrair_modelo_desenho(pdf) if tabela is None else extrair_modelo_desenho(pdf, tabela)


def _tem_fonte_falha(modelo: ModeloDesenho) -> bool:
    # Uma falha de fonte pode ser transitória e deve ser tentada de novo.
    return any(
        codigo.startswith("modelo.") and codigo.endswith("_falhou")
        for pagina in modelo.paginas
        for codigo in pagina.diagnosticos
    )


def extrair_modelo_desenho(pdf: Path, tabela: TabelaGlifos | None = None) -> ModeloDesenho:
    """Modelo de desenho do PDF; com `tabela`, também o texto em contorno de glifo."""
    documento_sha256 = _sha256_do_arquivo(pdf)
    with pymupdf.open(pdf) as documento:
        contagens = _Contagens()
        paginas: list[PaginaModelo] = []
        for indice in range(documento.page_count):
            pagina = documento.load_page(indice)
            fontes = _ler_fontes(pagina)
            contagens.somar(fontes)
            paginas.append(_montar_pagina(indice, pagina, fontes, tabela))
        familia = reconhecer_familia(_impressao(documento, contagens))
    return ModeloDesenho(VERSAO_MODELO_DESENHO, documento_sha256, familia, tuple(paginas))


def _impressao(documento: Any, contagens: _Contagens) -> ImpressaoEstrutural:
    metadados = documento.metadata or {}
    ocgs = cast(dict[int, dict[str, Any]], documento.get_ocgs() or {})
    return ImpressaoEstrutural(
        produtor=str(metadados.get("producer") or ""),
        criador=str(metadados.get("creator") or ""),
        nomes_ocg=tuple(str(ocgs[xref].get("name") or "") for xref in sorted(ocgs)),
        spans_texto_nativo=contagens.spans_texto_nativo,
        formas_glifo=contagens.formas_glifo,
        anotacoes_shx=contagens.anotacoes_shx,
        imagens=contagens.imagens,
    )


def _fonte(nome: str, diagnosticos: list[str], leitura: Callable[[], _T], vazio: _T) -> _T:
    try:
        return leitura()
    except Exception:
        diagnosticos.append(f"modelo.{nome}_falhou")
        return vazio


def _ler_fontes(pagina: Any) -> _Fontes:
    fontes = _Fontes()
    diagnosticos = fontes.diagnosticos
    sem_caminhos: _CaminhosLidos = ((), (), frozenset(), 0, 0)
    sem_textos: tuple[TextoModelo, ...] = ()
    sem_shx: tuple[tuple[TextoModelo, ...], int] = ((), 0)
    sem_imagens: tuple[ImagemModelo, ...] = ()
    (
        fontes.caminhos,
        fontes.indices_crus,
        fontes.translucidos,
        fontes.total_desenhos,
        fontes.formas_glifo,
    ) = _fonte("caminhos", diagnosticos, lambda: _caminhos_e_glifos(pagina), sem_caminhos)
    fontes.textos_nativos = _fonte(
        "textos_nativos", diagnosticos, lambda: _textos_nativos(pagina), sem_textos
    )
    fontes.textos_shx, fontes.anotacoes_shx = _fonte(
        "textos_shx", diagnosticos, lambda: _textos_shx(pagina), sem_shx
    )
    imagens_pagina = _fonte(
        "imagens", diagnosticos, lambda: _imagens_da_pagina(pagina), sem_imagens
    )
    imagens_anotacao = _fonte(
        "imagens_anotacao", diagnosticos, lambda: _imagens_de_anotacoes(pagina), sem_imagens
    )
    fontes.imagens = (*imagens_pagina, *imagens_anotacao)
    return fontes


def _montar_pagina(
    indice: int, pagina: Any, fontes: _Fontes, tabela: TabelaGlifos | None
) -> PaginaModelo:
    diagnosticos = fontes.diagnosticos
    caminhos = fontes.caminhos
    vazias: tuple[Polilinha | Circulo | Arco, ...] = ()
    primitivas = _fonte(
        "primitivas",
        diagnosticos,
        lambda: (*reconstruir_polilinhas(caminhos), *recuperar_circulos_e_arcos(caminhos)),
        vazias,
    )
    sem_grupos: tuple[GrupoCandidato, ...] = ()
    grupos = _fonte(
        "grupos", diagnosticos, lambda: agrupar_candidatos(primitivas, caminhos), sem_grupos
    )
    textos_glifo = _textos_glifo(caminhos, fontes.total_desenhos, tabela, diagnosticos)
    return PaginaModelo(
        indice=indice,
        largura=float(pagina.rect.width),
        altura=float(pagina.rect.height),
        caminhos=caminhos,
        textos=(*fontes.textos_nativos, *fontes.textos_shx, *textos_glifo),
        primitivas=primitivas,
        grupos=grupos,
        imagens=fontes.imagens,
        diagnosticos=tuple(diagnosticos),
    )


def _textos_glifo(
    caminhos: Sequence[Caminho],
    total_desenhos: int,
    tabela: TabelaGlifos | None,
    diagnosticos: list[str],
) -> tuple[TextoModelo, ...]:
    if tabela is None:
        return ()
    sem_leitura = LeituraGlifos((), 0, 0, limitada=False)
    leitura = _fonte(
        "glifos",
        diagnosticos,
        lambda: ler_texto_glifos(caminhos, tabela, total_desenhos),
        sem_leitura,
    )
    if leitura.limitada:
        diagnosticos.append("modelo.glifos_limitados")
    if leitura.desconhecidos or leitura.ambiguos:
        diagnosticos.append("modelo.glifos_desconhecidos")
    fonte = f"{tabela.versao}:{tabela.sha256[:12]}"
    return tuple(
        TextoModelo(texto.texto, texto.bbox, "glifo", texto.rotacao, texto.altura, fonte, "")
        for texto in leitura.textos
    )


def _transformacao(pagina: Any) -> _Transformar:
    """Ponto da página sem rotação → página visual (`page.rotation_matrix`)."""
    m = pagina.rotation_matrix
    a, b, c, d, e, f = (float(v) for v in (m.a, m.b, m.c, m.d, m.e, m.f))

    def transformar(ponto: Any) -> Ponto:
        x, y = float(ponto[0]), float(ponto[1])
        return (a * x + c * y + e, b * x + d * y + f)

    return transformar


def _caixa(transformar: _Transformar, caixa: Any) -> Caixa:
    x0, y0, x1, y1 = (float(v) for v in tuple(caixa))
    cantos = [transformar(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    xs = [p[0] for p in cantos]
    ys = [p[1] for p in cantos]
    return (min(xs), min(ys), max(xs), max(ys))


# --- caminhos -----------------------------------------------------------------------------


def _desenhos(pagina: Any) -> _DesenhosFiltrados:
    """Caminhos de traço/preenchimento; entradas `clip` e `group` ficam de fora."""
    return _DesenhosFiltrados(
        (indice, desenho)
        for indice, desenho in enumerate(pagina.get_drawings(extended=True))
        if desenho.get("type") in _TIPOS_CAMINHO
    )


def caminhos_da_pagina(pagina: Any) -> tuple[Caminho, ...]:
    """Caminhos da página visual; um desenho malformado sai sozinho, sem esvaziar a página."""
    return caminhos_e_total_da_pagina(pagina)[0]


def caminhos_e_total_da_pagina(pagina: Any) -> tuple[tuple[Caminho, ...], int]:
    """Caminhos da página visual e quantos desenhos de traço/preenchimento ela tem, contando
    os descartados: um salto no fim da numeração (`Caminho.ordem`) só aparece com o total."""
    desenhos = _desenhos(pagina)
    return _caminhos(desenhos, _transformacao(pagina)), len(desenhos)


def _caminhos(desenhos: Sequence[dict[str, Any]], transformar: _Transformar) -> tuple[Caminho, ...]:
    caminhos = []
    for ordem, desenho in enumerate(desenhos):
        try:
            subcaminhos = _subcaminhos(desenho.get("items") or (), transformar)
            estilo = _estilo(desenho)
        except Exception:
            continue
        if subcaminhos and _finitos(subcaminhos):
            caminhos.append(Caminho(subcaminhos, estilo, _TIPOS_CAMINHO[desenho["type"]], ordem))
    return tuple(caminhos)


def _finitos(subcaminhos: tuple[tuple[ItemCaminho, ...], ...]) -> bool:
    return all(
        math.isfinite(x) and math.isfinite(y)
        for subcaminho in subcaminhos
        for item in subcaminho
        for x, y in item.pontos
    )


def _translucido(desenho: dict[str, Any]) -> bool:
    opacidade = desenho.get("fill_opacity")
    return (
        isinstance(opacidade, int | float)
        and math.isfinite(opacidade)
        and opacidade < _OPACIDADE_OPACA
    )


def _caminhos_e_glifos(pagina: Any) -> _CaminhosLidos:
    desenhos = _desenhos(pagina)
    caminhos = _caminhos(desenhos, _transformacao(pagina))
    indices = tuple(desenhos.indices_crus[caminho.ordem] for caminho in caminhos)
    translucidos = frozenset(
        posicao for posicao, caminho in enumerate(caminhos) if _translucido(desenhos[caminho.ordem])
    )
    glifos = sum(1 for desenho in desenhos if _is_glyph(desenho))
    return caminhos, indices, translucidos, len(desenhos), glifos


def _subcaminhos(
    itens: Iterable[Any], transformar: _Transformar
) -> tuple[tuple[ItemCaminho, ...], ...]:
    """Separa subcaminhos onde um item não continua o anterior; `re`/`qu` fecham sozinhos."""
    subcaminhos: list[tuple[ItemCaminho, ...]] = []
    atual: list[ItemCaminho] = []
    for item in itens:
        operacao = str(item[0])
        if operacao in {"re", "qu"}:
            if atual:
                subcaminhos.append(tuple(atual))
                atual = []
            cantos = [transformar(p) for p in _path_points(item)]
            subcaminhos.append(
                tuple(ItemCaminho("l", (p, cantos[(i + 1) % 4])) for i, p in enumerate(cantos))
            )
            continue
        if operacao == "l":
            novo = ItemCaminho("l", (transformar(item[1]), transformar(item[2])))
        elif operacao == "c":
            if len(item) < 5:
                raise ValueError("Bézier sem os quatro pontos.")
            novo = ItemCaminho("c", tuple(transformar(p) for p in item[1:5]))
        else:
            continue
        if atual and atual[-1].pontos[-1] != novo.pontos[0]:
            subcaminhos.append(tuple(atual))
            atual = []
        atual.append(novo)
    if atual:
        subcaminhos.append(tuple(atual))
    return tuple(subcaminhos)


def _cor(valor: Sequence[float] | None) -> Cor | None:
    """Cor RGB; aridade diferente de 3 ou componente não finito vira None."""
    try:
        componentes = tuple(float(v) for v in valor or ())
    except (TypeError, ValueError):
        return None
    if len(componentes) != 3 or not all(math.isfinite(v) for v in componentes):
        return None
    return (componentes[0], componentes[1], componentes[2])


def _estilo(desenho: dict[str, Any]) -> Estilo:
    return Estilo(
        camada=str(desenho.get("layer") or ""),
        cor=_cor(desenho.get("color")),
        preenchimento=_cor(desenho.get("fill")),
        espessura=float(desenho.get("width") or 0.0),
        tracejado=str(desenho.get("dashes") or ""),
    )


# --- textos -------------------------------------------------------------------------------


class _CamadasDoTexto:
    """Casa um span do RAWDICT com o trecho do `get_texttrace()` de maior sobreposição.

    A grade só indexa a parte das caixas dentro da página (com margem), e uma caixa que
    cobriria mais de `_MAXIMO_CELULAS_TEXTO` células vai para uma lista percorrida
    linearmente: um `Tm` gigante não multiplica entradas na grade.
    """

    def __init__(self, trechos: Iterable[dict[str, Any]], limite: Caixa) -> None:
        self._limite = (
            limite[0] - _MARGEM_TEXTO,
            limite[1] - _MARGEM_TEXTO,
            limite[2] + _MARGEM_TEXTO,
            limite[3] + _MARGEM_TEXTO,
        )
        self._trechos: list[tuple[Caixa, str, str, float]] = []
        self._celulas: dict[tuple[int, int], list[int]] = defaultdict(list)
        self._grandes: list[int] = []
        for trecho in trechos:
            caixa = cast(Caixa, tuple(float(v) for v in trecho["bbox"]))
            recorte = self._recortar(caixa)
            if recorte is None:
                continue
            indice = len(self._trechos)
            self._trechos.append(
                (
                    caixa,
                    str(trecho.get("layer") or ""),
                    str(trecho.get("font") or ""),
                    float(trecho.get("size") or 0.0),
                )
            )
            celulas = self._celulas_de(recorte)
            if celulas is None:
                self._grandes.append(indice)
                continue
            for celula in celulas:
                self._celulas[celula].append(indice)

    def _recortar(self, caixa: Caixa) -> Caixa | None:
        x0, y0 = max(caixa[0], self._limite[0]), max(caixa[1], self._limite[1])
        x1, y1 = min(caixa[2], self._limite[2]), min(caixa[3], self._limite[3])
        return (x0, y0, x1, y1) if x0 <= x1 and y0 <= y1 else None

    @staticmethod
    def _celulas_de(caixa: Caixa) -> list[tuple[int, int]] | None:
        """Células da caixa (já recortada), ou None acima do teto."""
        x0, y0, x1, y1 = (math.floor(v / _CELULA_TEXTO) for v in caixa)
        if (x1 - x0 + 1) * (y1 - y0 + 1) > _MAXIMO_CELULAS_TEXTO:
            return None
        return [(cx, cy) for cx in range(x0, x1 + 1) for cy in range(y0, y1 + 1)]

    def _candidatos(self, caixa: Caixa) -> Iterable[int]:
        recorte = self._recortar(caixa)
        if recorte is None:
            return ()
        celulas = self._celulas_de(recorte)
        if celulas is None:
            return range(len(self._trechos))
        candidatos = {i for celula in celulas for i in self._celulas.get(celula, ())}
        candidatos.update(self._grandes)
        return sorted(candidatos)

    def camada(self, caixa: Caixa, fonte: str, tamanho: float) -> str:
        melhor: tuple[bool, float] | None = None
        camada = ""
        for indice in self._candidatos(caixa):
            (tx0, ty0, tx1, ty1), camada_trecho, fonte_trecho, tamanho_trecho = self._trechos[
                indice
            ]
            largura = min(caixa[2], tx1) - max(caixa[0], tx0)
            altura = min(caixa[3], ty1) - max(caixa[1], ty0)
            if largura <= 0 or altura <= 0:
                continue
            pontuacao = (
                fonte_trecho == fonte and abs(tamanho_trecho - tamanho) < 0.01,
                largura * altura,
            )
            if melhor is None or pontuacao > melhor:
                melhor, camada = pontuacao, camada_trecho
        return camada


def _textos_nativos(pagina: Any) -> tuple[TextoModelo, ...]:
    bruto = cast(
        dict[str, Any], _native_textpage(pagina, pymupdf.TEXTFLAGS_RAWDICT).extractRAWDICT()
    )
    sem_rotacao = pagina.rect * pagina.derotation_matrix
    camadas = _CamadasDoTexto(
        pagina.get_texttrace(),
        (sem_rotacao.x0, sem_rotacao.y0, sem_rotacao.x1, sem_rotacao.y1),
    )
    transformar = _transformacao(pagina)
    origem = transformar((0.0, 0.0))
    textos: list[TextoModelo] = []
    for bloco in bruto.get("blocks", ()):
        if int(bloco.get("type", -1)) != 0:
            continue
        for linha in bloco.get("lines", ()):
            dx, dy = (float(v) for v in linha.get("dir", (1.0, 0.0)))
            vx, vy = transformar((dx, dy))
            rotacao = round(math.degrees(math.atan2(vy - origem[1], vx - origem[0])), 6) % 360.0
            for span in linha.get("spans", ()):
                texto = "".join(str(char.get("c", "")) for char in span.get("chars", ()))
                if not texto.strip():
                    continue
                fonte = str(span.get("font") or "")
                tamanho = float(span.get("size") or 0.0)
                caixa_bruta = cast(Caixa, tuple(float(v) for v in span["bbox"]))
                textos.append(
                    TextoModelo(
                        texto=texto,
                        bbox=_caixa(transformar, caixa_bruta),
                        origem="nativo",
                        rotacao=rotacao,
                        altura=tamanho,
                        fonte=fonte,
                        camada=camadas.camada(caixa_bruta, fonte, tamanho),
                    )
                )
    return tuple(textos)


def _textos_shx(pagina: Any) -> tuple[tuple[TextoModelo, ...], int]:
    """Portadores SHX do AutoCAD: texto do conteúdo, caixa da anotação, sem rotação conhecida."""
    documento = pagina.parent
    transformar = _transformacao(pagina)
    textos: list[TextoModelo] = []
    portadores = 0
    for xref_bruto, tipo_reserva, _campo in pagina.annot_xrefs():
        xref = int(xref_bruto)
        info = _annotation_info(pagina, xref)
        if not _is_technical_annotation(
            _annotation_subtype(documento, xref, int(tipo_reserva)), info
        ):
            continue
        portadores += 1
        conteudo = _optional_string(info.get("content"))
        if conteudo is None:
            continue
        caixa = _caixa(transformar, pagina.load_annot(xref).rect)
        textos.append(TextoModelo(conteudo, caixa, "shx", 0.0, caixa[3] - caixa[1], "", ""))
    return tuple(textos), portadores


# --- imagens ------------------------------------------------------------------------------


def _sha256_do_digest(digest: object) -> str:
    """Identidade da imagem: sha256 do digest de pixels da PyMuPDF (igual na página e no /AP)."""
    return hashlib.sha256(bytes(cast(bytes, digest or b""))).hexdigest()


def _imagens_da_pagina(pagina: Any) -> tuple[ImagemModelo, ...]:
    """Equivale a `get_image_info(hashes=True)`, mas sem as appearance streams de anotações."""
    informacoes = _native_textpage(pagina, pymupdf.TEXT_PRESERVE_IMAGES).extractIMGINFO(hashes=True)
    transformar = _transformacao(pagina)
    return tuple(
        ImagemModelo(
            bbox=_caixa(transformar, info["bbox"]),
            largura_px=int(info.get("width") or 0),
            altura_px=int(info.get("height") or 0),
            sha256=_sha256_do_digest(info.get("digest")),
            de_anotacao=False,
        )
        for info in informacoes
    )


def _numero_arredondado(texto: str) -> int:
    """Número PDF (inteiro ou real) arredondado para cima; o resto vale 0, como na MuPDF."""
    return math.ceil(float(texto)) if _NUMERO_PDF.fullmatch(texto) else 0


def _dimensao_da_imagem(documento: Any, xref: int, chave: str) -> int | None:
    """/Width ou /Height com referências indiretas resolvidas; None se a cadeia não termina."""
    tipo, texto = documento.xref_get_key(xref, chave)
    if tipo not in {"int", "float", "xref"}:
        return 0
    for _ in range(_PROFUNDIDADE_REFERENCIA):
        referencia = _REFERENCIA_PDF.fullmatch(texto)
        if referencia is None:
            return _numero_arredondado(texto)
        texto = str(documento.xref_object(int(referencia.group(1)), compressed=True)).strip()
    return None


def _sha256_da_imagem_de_anotacao(
    documento: Any, xref: int, largura: int | None, altura: int | None
) -> str:
    if largura is None or altura is None or largura * altura > _MAXIMO_PIXELS_IMAGEM_ANOTACAO:
        return hashlib.sha256(bytes(documento.xref_stream_raw(xref) or b"")).hexdigest()
    return _sha256_do_digest(pymupdf.Pixmap(documento, xref).digest)


def _imagem_de_anotacao(documento: Any, xref: int, caixa: Caixa) -> ImagemModelo:
    largura = _dimensao_da_imagem(documento, xref, "Width")
    altura = _dimensao_da_imagem(documento, xref, "Height")
    return ImagemModelo(
        bbox=caixa,
        largura_px=largura or 0,
        altura_px=altura or 0,
        sha256=_sha256_da_imagem_de_anotacao(documento, xref, largura, altura),
        de_anotacao=True,
    )


def _imagens_de_anotacoes(pagina: Any) -> tuple[ImagemModelo, ...]:
    """Imagens das appearance streams; a caixa é a da anotação (geometria aproximada)."""
    documento = pagina.parent
    transformar = _transformacao(pagina)
    imagens: list[ImagemModelo] = []
    for xref_bruto, _tipo, _campo in pagina.annot_xrefs():
        xref = int(xref_bruto)
        xrefs_imagem = dict.fromkeys(
            objeto
            for raiz, nome in _appearance_roots(documento, xref)
            for objeto, _recurso, _profundidade, subtipo in _appearance_objects(
                documento, raiz, nome, _PROFUNDIDADE_APARENCIA
            )
            if subtipo == "Image"
        )
        if not xrefs_imagem:
            continue
        caixa = _caixa(transformar, pagina.load_annot(xref).rect)
        imagens.extend(_imagem_de_anotacao(documento, imagem, caixa) for imagem in xrefs_imagem)
    return tuple(imagens)
