# mypy: disable-error-code="no-untyped-call"
"""Evidências TEXTO lidas do contorno de glifo de uma página PyMuPDF e a cobertura por OCR.

A leitura usa só os caminhos da página (`caminhos_da_pagina`, na página visual) e a tabela de
glifos; a geometria da evidência são os cantos do texto divididos pelo tamanho da página, sem
`_normalized_points` (que giraria de novo). `rotacao_graus` segue a convenção do texto nativo:
a direção do texto levada ao espaço sem rotação pela parte linear de `page.derotation_matrix`.

Cobertura: um texto de glifo é comparado no nível do glifo com as leituras (OCR ou texto
nativo) que o tocam. A leitura é concordante se o seu texto, sem espaços, é a concatenação na
ordem de leitura dos glifos cujo centro cai na caixa dela. Texto de glifo com todos os glifos
cobertos por leituras concordantes sai; senão fica, e os OCR concordantes dentro dele saem
(fragmentos que ele já contém), exceto o token do motor de contornos. OCR divergente fica
junto com o glifo e é contado. O texto nativo nunca sai e não conta divergência.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

from zeny_project_handler.domain.analysis import DiagnosticoAnalise, OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.analysis import CandidatoEvidenciaDocumento, GeometriaNormalizada

from .drawing_model.glyph_table import TabelaGlifos
from .drawing_model.glyph_text import LeituraGlifos, TextoGlifo, ler_texto_glifos
from .drawing_model.model import Caixa, Ponto
from .pymupdf_drawing_model import caminhos_da_pagina
from .pymupdf_support import (
    _extras,
    _normalized_point,
    _pdf_color,
    _without_consecutive_duplicates,
)

ORIGEM_TEXTO_GLIFO: Final = "contorno_glifo"
_EXTRATOR: Final = "texto_glifos"
_MOTOR_CONTORNOS: Final = "tesseract-contornos-vetoriais"
_TOLERANCIA: Final = 0.0005
_CASAS: Final = 6


@dataclass(frozen=True, slots=True)
class GlifosDaPagina:
    """Candidatos TEXTO de glifo e, no mesmo índice, o texto lido em coordenadas 0..1."""

    candidatos: tuple[CandidatoEvidenciaDocumento, ...]
    textos: tuple[TextoGlifo, ...]
    diagnosticos: tuple[DiagnosticoAnalise, ...]

    def apenas(self, indices: Sequence[int]) -> GlifosDaPagina:
        return GlifosDaPagina(
            tuple(self.candidatos[i] for i in indices),
            tuple(self.textos[i] for i in indices),
            self.diagnosticos,
        )


@dataclass(frozen=True, slots=True)
class Cobertura:
    mantidos: tuple[CandidatoEvidenciaDocumento, ...]
    glifos: tuple[int, ...]
    divergentes: int


def eh_texto_de_glifo(candidato: CandidatoEvidenciaDocumento) -> bool:
    return dict(candidato.atributos_extraidos).get("origem_texto") == ORIGEM_TEXTO_GLIFO


def candidatos_texto_glifos(
    pagina: Any, numero_pagina: int, tabela: TabelaGlifos
) -> tuple[tuple[CandidatoEvidenciaDocumento, ...], tuple[DiagnosticoAnalise, ...]]:
    glifos = ler_glifos_da_pagina(pagina, numero_pagina, tabela)
    return glifos.candidatos, glifos.diagnosticos


def ler_glifos_da_pagina(pagina: Any, numero_pagina: int, tabela: TabelaGlifos) -> GlifosDaPagina:
    leitura = ler_texto_glifos(caminhos_da_pagina(pagina), tabela)
    largura, altura = float(pagina.rect.width), float(pagina.rect.height)
    derotacao = pagina.derotation_matrix
    candidatos: list[CandidatoEvidenciaDocumento] = []
    textos: list[TextoGlifo] = []
    for indice, texto in enumerate(leitura.textos):
        pontos = _poligono(texto.cantos, largura, altura)
        if pontos is None:  # texto fora da página: nada a localizar
            continue
        candidatos.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=f"p{numero_pagina}:texto_glifo:{indice}",
                pagina_numero=numero_pagina,
                tipo=TipoEvidencia.TEXTO,
                geometria=GeometriaNormalizada(tipo=TipoGeometria.POLIGONO, pontos=pontos),
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=texto.texto,
                atributos_extraidos=_extras(
                    origem_texto=ORIGEM_TEXTO_GLIFO,
                    tabela_glifos=tabela.versao,
                    tabela_glifos_sha256=tabela.sha256,
                    quantidade_glifos=texto.quantidade_glifos,
                    rotacao_graus=_rotacao_nativa(texto.rotacao, derotacao),
                    altura=_decimal(texto.altura),
                    cor=_pdf_color(texto.cor),
                ),
            )
        )
        textos.append(_normalizado(texto, largura, altura))
    return GlifosDaPagina(tuple(candidatos), tuple(textos), _diagnosticos(leitura, numero_pagina))


def _decimal(valor: float) -> Decimal:
    return Decimal(str(round(valor, _CASAS)))


def _poligono(
    cantos: Sequence[Ponto], largura: float, altura: float
) -> tuple[PontoNormalizado, ...] | None:
    """Cantos na ordem do quadrilátero nativo (topo-início, topo-fim, base-fim, base-início)."""
    inicio_base, fim_base, fim_topo, inicio_topo = cantos
    pontos = _without_consecutive_duplicates(
        tuple(
            _normalized_point(x / largura, y / altura)
            for x, y in (inicio_topo, fim_topo, fim_base, inicio_base)
        )
    )
    return pontos if len(set(pontos)) >= 3 else None


def _rotacao_nativa(rotacao: float, derotacao: Any) -> Decimal:
    """Direção visual (graus horários, y para baixo) → `rotacao_graus` do texto nativo."""
    dx, dy = math.cos(math.radians(rotacao)), math.sin(math.radians(rotacao))
    ux = float(derotacao.a) * dx + float(derotacao.c) * dy
    uy = float(derotacao.b) * dx + float(derotacao.d) * dy
    return _decimal(math.degrees(math.atan2(-uy, ux)))


def _escalar(caixa: Caixa, largura: float, altura: float) -> Caixa:
    return (caixa[0] / largura, caixa[1] / altura, caixa[2] / largura, caixa[3] / altura)


def _normalizado(texto: TextoGlifo, largura: float, altura: float) -> TextoGlifo:
    """O mesmo texto em coordenadas 0..1 da página, para comparar com as leituras."""
    a, b, c, d = ((x / largura, y / altura) for x, y in texto.cantos)
    return TextoGlifo(
        texto=texto.texto,
        bbox=_escalar(texto.bbox, largura, altura),
        cantos=(a, b, c, d),
        rotacao=texto.rotacao,
        altura=texto.altura,
        quantidade_glifos=texto.quantidade_glifos,
        cor=texto.cor,
        glifos=tuple((c, _escalar(caixa, largura, altura)) for c, caixa in texto.glifos),
    )


def _diagnosticos(leitura: LeituraGlifos, numero_pagina: int) -> tuple[DiagnosticoAnalise, ...]:
    diagnosticos: list[DiagnosticoAnalise] = []
    if leitura.limitada:
        diagnosticos.append(
            DiagnosticoAnalise(
                codigo="analise.glifos_limitados",
                mensagem=(
                    "A página tem formas de glifo demais para a leitura por contorno; "
                    "o texto de glifo não foi lido nesta página."
                ),
                extrator=_EXTRATOR,
                pagina_numero=numero_pagina,
            )
        )
    if leitura.desconhecidos or leitura.ambiguos:
        diagnosticos.append(
            DiagnosticoAnalise(
                codigo="analise.glifos_desconhecidos",
                mensagem=(
                    f"{leitura.desconhecidos} glifo(s) desconhecido(s) e {leitura.ambiguos} "
                    "ambíguo(s) na tabela; os textos que os contêm não foram emitidos."
                ),
                extrator=_EXTRATOR,
                pagina_numero=numero_pagina,
            )
        )
    return tuple(diagnosticos)


def diagnostico_divergencia(numero_pagina: int, divergentes: int) -> DiagnosticoAnalise:
    return DiagnosticoAnalise(
        codigo="analise.glifo_ocr_divergente",
        mensagem=(
            f"{divergentes} leitura(s) OCR divergem do texto de glifo que cobrem; "
            "as duas leituras foram mantidas."
        ),
        extrator=_EXTRATOR,
        pagina_numero=numero_pagina,
    )


# --- cobertura ------------------------------------------------------------------------------


def _caixa_candidato(candidato: CandidatoEvidenciaDocumento) -> Caixa:
    xs = [float(p.x) for p in candidato.geometria.pontos]
    ys = [float(p.y) for p in candidato.geometria.pontos]
    return (
        min(xs) - _TOLERANCIA,
        min(ys) - _TOLERANCIA,
        max(xs) + _TOLERANCIA,
        max(ys) + _TOLERANCIA,
    )


def _centro(caixa: Caixa) -> Ponto:
    return ((caixa[0] + caixa[2]) / 2.0, (caixa[1] + caixa[3]) / 2.0)


def _contem_ponto(caixa: Caixa, ponto: Ponto) -> bool:
    return caixa[0] <= ponto[0] <= caixa[2] and caixa[1] <= ponto[1] <= caixa[3]


def _dentro(interna: Caixa, externa: Caixa) -> bool:
    """`interna` (já com a tolerância) dentro de `externa` acrescida da mesma tolerância."""
    return (
        externa[0] - 2 * _TOLERANCIA <= interna[0]
        and externa[1] - 2 * _TOLERANCIA <= interna[1]
        and interna[2] <= externa[2] + 2 * _TOLERANCIA
        and interna[3] <= externa[3] + 2 * _TOLERANCIA
    )


@dataclass(frozen=True, slots=True)
class _Toque:
    """Texto de glifo tocado por uma leitura e os índices dos seus glifos sob ela."""

    texto: int
    glifos: tuple[int, ...]
    leitura_dentro: bool


def _toques(caixa: Caixa, glifos: Sequence[TextoGlifo]) -> list[_Toque]:
    toques: list[_Toque] = []
    for indice, texto in enumerate(glifos):
        sob = tuple(
            i for i, (_, glifo) in enumerate(texto.glifos) if _contem_ponto(caixa, _centro(glifo))
        )
        dentro = _dentro(caixa, texto.bbox)
        if sob or dentro:
            toques.append(_Toque(indice, sob, dentro))
    return toques


def _esperado(toques: Sequence[_Toque], glifos: Sequence[TextoGlifo]) -> str:
    """Glifos sob a leitura, na ordem de leitura: os textos em sequência pela direção do
    primeiro texto tocado, e dentro de cada texto na ordem dos seus glifos."""
    (ax, ay), (bx, by) = glifos[toques[0].texto].cantos[:2]
    dx, dy = bx - ax, by - ay

    def posicao(toque: _Toque) -> float:
        texto = glifos[toque.texto]
        x, y = _centro(texto.glifos[toque.glifos[0]][1]) if toque.glifos else texto.cantos[0]
        return x * dx + y * dy

    return "".join(
        glifos[toque.texto].glifos[i][0]
        for toque in sorted(toques, key=posicao)
        for i in toque.glifos
    )


def _do_motor_de_contornos(candidato: CandidatoEvidenciaDocumento) -> bool:
    return dict(candidato.atributos_extraidos).get("motor_ocr") == _MOTOR_CONTORNOS


def _resolver_cobertura(
    leituras: Sequence[CandidatoEvidenciaDocumento],
    glifos: Sequence[TextoGlifo],
    *,
    nativo: bool = False,
) -> Cobertura:
    """Aplica a regra de cobertura entre leituras (OCR, ou texto nativo com `nativo=True`) e os
    textos de glifo da página (coordenadas 0..1). Devolve as leituras mantidas, os índices dos
    textos de glifo mantidos e quantas leituras OCR divergem do glifo que tocam."""
    cobertos: list[set[int]] = [set() for _ in glifos]
    concordantes: list[tuple[int, list[_Toque]]] = []
    divergentes = 0
    for indice, leitura in enumerate(leituras):
        lido = "".join((leitura.conteudo_bruto or "").split())
        if not lido:  # leitura vazia ou só de espaços não compara com glifo nenhum
            continue
        toques = _toques(_caixa_candidato(leitura), glifos)
        if not toques:
            continue
        if _esperado(toques, glifos) != lido:
            divergentes += 0 if nativo else 1
            continue
        concordantes.append((indice, toques))
        for toque in toques:
            cobertos[toque.texto].update(toque.glifos)
    removidos = {i for i, texto in enumerate(glifos) if len(cobertos[i]) == len(texto.glifos)}
    fragmentos = {
        indice
        for indice, toques in concordantes
        if not nativo
        and not _do_motor_de_contornos(leituras[indice])
        and any(t.leitura_dentro and t.texto not in removidos for t in toques)
    }
    return Cobertura(
        mantidos=tuple(c for i, c in enumerate(leituras) if i not in fragmentos),
        glifos=tuple(i for i in range(len(glifos)) if i not in removidos),
        divergentes=divergentes,
    )
