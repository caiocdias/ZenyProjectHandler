# mypy: disable-error-code="no-untyped-call"
"""Pacotes de símbolos sobre o modelo de desenho: o método versionado ao lado do motor.

Os casamentos do núcleo puro de `drawing_model/` viram observações com a geometria do motor
`declarative_symbols`. A falha de fonte vira cobertura (R-E06.2.2.1-3), nunca observação parcial
nem não detecção, e a imagem compacta sem casamento é dado, não observação (R-E06.2.2.1-4).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Final

import pymupdf

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    FonteObservacaoSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    PontoOriginalSimbolo,
    PrimitivaObservadaSimbolo,
    ResultadoMetodoSimbolos,
)
from zeny_project_handler.domain.values import PontoNormalizado

from .declarative_symbols import (
    Package,
    _enabled,
    _geometry,
    _validate_page_size,
    perfil_pacotes,
)
from .drawing_model.glyph_table import TabelaGlifos
from .drawing_model.grammar_disc import _caixa_arredondada
from .drawing_model.model import VERSAO_MODELO_DESENHO, Caixa, ImagemModelo, Ponto
from .drawing_model.symbol_grammars import (
    _GLIFOS_LIMITADOS,
    LIMITE_CONSULTAS_PAGINA,
    FonteGramaticaFalhou,
    PaginaGramatica,
    TetoGramaticasExcedido,
    contem,
    ponto_em,
)
from .drawing_model.symbol_matcher import CasamentoGramatica, casar_variantes
from .pymupdf_drawing_model import pagina_para_gramaticas

_METODO_ID: Final = "declarative-drawing-model"
_VERSAO: Final = "1.0.0"
_DOMINIO: Final = "PDF vetorial lido pelo modelo de desenho; contexto não inferido"
_FONTES: Final = (
    "pymupdf:get_drawings:extended",
    "pymupdf:get_text:rawdict",
    "pymupdf:annotations",
    "modelo-desenho:glifos",
)
_CAMADA: Final = "base"
_PAGINA_INTEIRA: Final = (
    PontoNormalizado(Decimal(0), Decimal(0)),
    PontoNormalizado(Decimal(1), Decimal(1)),
)
_SEM_VARIANTE: Final = "Nenhuma variante com gramática habilitada"

_CAMINHOS_FALHOU: Final = "modelo.caminhos_falhou"
_IMAGENS_FALHOU: Final = frozenset({"modelo.imagens_falhou", "modelo.imagens_anotacao_falhou"})
_LADO_MINIMO_RESIDUO: Final = 4.0
_LADO_MAXIMO_RESIDUO: Final = 72.0
_MAXIMO_HASHES_POR_DIMENSAO: Final = 8
# Do tamanho do maior lado do resíduo: cada imagem consulta no máximo 2 x 2 células.
_CELULA_CENTROS: Final = _LADO_MAXIMO_RESIDUO


@dataclass(frozen=True, slots=True)
class ResiduoRaster:
    """Imagem compacta sem casamento em cima, no espaço da página visual."""

    caixa: Caixa
    sha256: str
    de_anotacao: bool


def perfil_pacotes_modelo(
    pacotes: tuple[Package, ...], tabela: TabelaGlifos, *, limite: int = LIMITE_CONSULTAS_PAGINA
) -> PerfilMetodoSimbolos:
    """Mesmas classes, família e referência do motor; a identidade inclui modelo, tabela e teto."""
    motor = perfil_pacotes(pacotes)
    return replace(
        motor,
        metodo_id=_METODO_ID,
        versao=_VERSAO,
        dominio_aplicacao=_DOMINIO,
        fontes_compartilhadas=_FONTES,
        parametros=(
            *motor.parametros,
            ("modelo_desenho", VERSAO_MODELO_DESENHO),
            ("tabela_glifos_versao", tabela.versao),
            ("tabela_glifos_sha256", tabela.sha256),
            ("limite_consultas", limite),
        ),
    )


# --- resíduo raster (R-E06.2.2.1-4) ---------------------------------------------------------


def _dimensoes_de_mosaico(imagens: Iterable[ImagemModelo]) -> set[tuple[int, int]]:
    """Dimensões em pixels com hashes distintos demais: ladrilho de ortofoto, não símbolo.

    Vale para as imagens da página toda, e dimensão 0 é anotação sem pixels medidos.
    """
    hashes: defaultdict[tuple[int, int], set[str]] = defaultdict(set)
    for imagem in imagens:
        if imagem.largura_px > 0 and imagem.altura_px > 0:
            hashes[imagem.largura_px, imagem.altura_px].add(imagem.sha256)
    return {
        dimensao
        for dimensao, distintos in hashes.items()
        if len(distintos) > _MAXIMO_HASHES_POR_DIMENSAO
    }


def _compacta(caixa: Caixa) -> bool:
    largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    return (
        _LADO_MINIMO_RESIDUO <= largura <= _LADO_MAXIMO_RESIDUO
        and _LADO_MINIMO_RESIDUO <= altura <= _LADO_MAXIMO_RESIDUO
    )


def _centro(caixa: Caixa) -> Ponto:
    return ((caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2)


def _celula_de_centro(valor: float) -> int:
    return math.floor(valor / _CELULA_CENTROS)


def _grade_de_centros(
    casamentos: Iterable[CasamentoGramatica],
) -> dict[tuple[int, int], list[Ponto]]:
    """Centros por célula; o não finito não está em caixa nenhuma e fica de fora."""
    grade: defaultdict[tuple[int, int], list[Ponto]] = defaultdict(list)
    for casamento in casamentos:
        x, y = _centro(casamento.caixa)
        if math.isfinite(x) and math.isfinite(y):
            grade[_celula_de_centro(x), _celula_de_centro(y)].append((x, y))
    return grade


def _tem_centro(caixa: Caixa, grade: Mapping[tuple[int, int], Sequence[Ponto]]) -> bool:
    """Só para caixa compacta: é o que limita as células consultadas."""
    return any(
        ponto_em(caixa, centro)
        for cx in range(_celula_de_centro(caixa[0]), _celula_de_centro(caixa[2]) + 1)
        for cy in range(_celula_de_centro(caixa[1]), _celula_de_centro(caixa[3]) + 1)
        for centro in grade.get((cx, cy), ())
    )


def residuos_raster(
    pagina: PaginaGramatica, casamentos: Sequence[CasamentoGramatica]
) -> tuple[ResiduoRaster, ...]:
    """Imagens compactas, dentro da página e sem centro de casamento, na ordem de `modelo.imagens`.

    Determinístico: é o contrato para quem precisa de caixa e hash, folha a folha. A contagem pode
    superestimar em folha com ortofoto: recortes de borda têm dimensão quase única e escapam da
    regra de mosaico, que exige a mesma dimensão exata.
    """
    modelo = pagina.modelo
    limites: Caixa = (0.0, 0.0, modelo.largura, modelo.altura)
    mosaicos = _dimensoes_de_mosaico(modelo.imagens)
    centros = _grade_de_centros(casamentos)
    residuos: list[ResiduoRaster] = []
    vistos: set[tuple[str, Caixa]] = set()
    for imagem in modelo.imagens:
        chave = (imagem.sha256, _caixa_arredondada(imagem.bbox))
        if (
            chave in vistos
            or (imagem.largura_px, imagem.altura_px) in mosaicos
            or not _compacta(imagem.bbox)
            or not contem(limites, imagem.bbox)
            or _tem_centro(imagem.bbox, centros)
        ):
            continue
        vistos.add(chave)
        residuos.append(ResiduoRaster(imagem.bbox, imagem.sha256, imagem.de_anotacao))
    return tuple(residuos)


def _motivo_medido(pagina: PaginaGramatica, casamentos: Sequence[CasamentoGramatica]) -> str:
    """`residuo_raster:0` é "medido, zero"; `imagens_falhou` diz que o zero não é evidência."""
    termos = [f"residuo_raster:{len(residuos_raster(pagina, casamentos))}"]
    if _IMAGENS_FALHOU.intersection(pagina.modelo.diagnosticos):
        termos.append("imagens_falhou")
    return ";".join(termos)


# --- observações ----------------------------------------------------------------------------


def _pontos_originais(caixa: pymupdf.Rect) -> tuple[PontoOriginalSimbolo, ...]:
    return tuple(
        (Decimal(str(ponto.x)), Decimal(str(ponto.y)))
        for ponto in (caixa.tl, caixa.tr, caixa.br, caixa.bl)
    )


def _atributos(pacote: Mapping[str, Any], variante: Mapping[str, Any]) -> tuple[Any, ...]:
    """Os mesmos de `_known_observation`: a reconciliação compara os dois métodos."""
    referencia = variante["source_ref"]
    return tuple(
        sorted(
            {
                "familia_inventario": pacote["family_id"],
                "variante_inventario": variante["id"],
                "referencias_possiveis": variante["id"],
                "papel": variante["role"],
                "destino": variante["destination"],
                "contexto": "unknown",
                "fonte_referencia": referencia["source_id"],
                "localizador_referencia": referencia["locator"],
                "gramatica": variante["recognition"]["grammar"]["kind"],
            }.items()
        )
    )


def _observacao(
    page: Any,
    fonte: FonteObservacaoSimbolo,
    assinatura: str,
    pagina: PaginaGramatica,
    casamento: CasamentoGramatica,
) -> ObservacaoSimbolo:
    """A caixa do casamento é visual, e a do motor é crua (R-E06.2.1-7).

    `Estilo.camada` é "" sem OCG e o motor grava None: "" duplicaria a ocorrência na reconciliação.
    """
    variante = casamento.variante
    caixa_crua = pymupdf.Rect(casamento.caixa) * page.derotation_matrix
    camada = pagina.modelo.caminhos[casamento.caminho].estilo.camada
    return ObservacaoSimbolo(
        fonte=fonte,
        metodo_assinatura=assinatura,
        geometria=_geometry(page, caixa_crua),
        alternativas=(AlternativaClasseSimbolo(classe=variante["class_code"]),),
        score_bruto=None,
        primitivas=(
            PrimitivaObservadaSimbolo(
                indice=str(pagina.indices_crus[casamento.caminho]),
                camada=camada or None,
                pontos_originais=_pontos_originais(caixa_crua),
            ),
        ),
        template=variante["id"],
        atributos=_atributos(casamento.pacote, variante),
    )


def _resultado(
    perfil: PerfilMetodoSimbolos,
    fonte: FonteObservacaoSimbolo,
    estado: EstadoMetodoSimbolos,
    motivo: str,
    observacoes: tuple[ObservacaoSimbolo, ...] = (),
) -> ResultadoMetodoSimbolos:
    """Uma só cobertura por página, como o motor. `classes_avaliadas` são as suportadas mesmo fora
    do domínio, para a matriz da reconciliação dar `not_applicable`, e não `uncovered`."""
    cobertura = CoberturaMetodoSimbolos(
        fonte=fonte,
        regiao_normalizada=_PAGINA_INTEIRA,
        classes_avaliadas=perfil.classes_suportadas,
        estado=estado,
        motivo=motivo,
    )
    return ResultadoMetodoSimbolos(perfil=perfil, coberturas=(cobertura,), observacoes=observacoes)


def observar_pacotes_modelo(
    page: Any,
    *,
    documento_id: str,
    documento_sha256: str,
    pagina_numero: int,
    pacotes: tuple[Package, ...],
    tabela: TabelaGlifos,
    perfil: PerfilMetodoSimbolos | None = None,
    limite: int = LIMITE_CONSULTAS_PAGINA,
) -> ResultadoMetodoSimbolos:
    """Observa a página pelo núcleo das gramáticas; `perfil` evita recalcular o sha a cada página.

    Só `modelo.caminhos_falhou` é `FALHA`: é o `get_drawings` que o motor também lê. As demais
    fontes, o teto e os glifos limitados são `FORA_DOMINIO` (R-E06.2.2.1-3), sem contagem de
    resíduos. Exceção inesperada não é capturada: o runner é fail-closed.
    """
    _validate_page_size(page)
    metodo = perfil_pacotes_modelo(pacotes, tabela, limite=limite) if perfil is None else perfil
    fonte = FonteObservacaoSimbolo(
        documento_id=documento_id,
        documento_sha256=documento_sha256,
        pagina_numero=pagina_numero,
        camada=_CAMADA,
    )
    variantes = _enabled(pacotes)
    if not variantes:
        return _resultado(metodo, fonte, EstadoMetodoSimbolos.FORA_DOMINIO, _SEM_VARIANTE)
    pagina = pagina_para_gramaticas(page, pagina_numero - 1, tabela)
    diagnosticos = pagina.modelo.diagnosticos
    # `FonteGramaticaFalhou` traz só o primeiro código: os caminhos decidem antes dele.
    if _CAMINHOS_FALHOU in diagnosticos:
        motivo = f"fonte_falhou:{_CAMINHOS_FALHOU}"
        return _resultado(metodo, fonte, EstadoMetodoSimbolos.FALHA, motivo)
    try:
        casamentos = casar_variantes(pagina, variantes, limite=limite)
    except FonteGramaticaFalhou as falha:
        motivo = f"fonte_falhou:{falha.codigo}"
        return _resultado(metodo, fonte, EstadoMetodoSimbolos.FORA_DOMINIO, motivo)
    except TetoGramaticasExcedido:
        motivo = "glifos_limitados" if _GLIFOS_LIMITADOS in diagnosticos else "teto_consultas"
        return _resultado(metodo, fonte, EstadoMetodoSimbolos.FORA_DOMINIO, motivo)
    assinatura = metodo.assinatura()
    observacoes = tuple(
        _observacao(page, fonte, assinatura, pagina, casamento) for casamento in casamentos
    )
    estado = EstadoMetodoSimbolos.CONCLUIDO if observacoes else EstadoMetodoSimbolos.NAO_DETECCAO
    return _resultado(metodo, fonte, estado, _motivo_medido(pagina, casamentos), observacoes)
