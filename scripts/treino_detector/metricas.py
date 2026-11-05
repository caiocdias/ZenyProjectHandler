"""Métricas puras do ensaio de treino do detector (só biblioteca padrão)."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.treino_detector.dados_sinteticos import Anotacao

Caixa = tuple[float, float, float, float]


def iou(a: Caixa, b: Caixa) -> float:
    """Interseção sobre união de duas caixas (x0, y0, x1, y1)."""
    largura = min(a[2], b[2]) - max(a[0], b[0])
    altura = min(a[3], b[3]) - max(a[1], b[1])
    if largura <= 0 or altura <= 0:
        return 0.0
    interseccao = largura * altura
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return interseccao / (area_a + area_b - interseccao)


@dataclass(frozen=True)
class Deteccao:
    caixa: Caixa
    rotulo: int
    score: float


@dataclass(frozen=True)
class ResultadoAvaliacao:
    verdadeiros: int
    falsos_positivos: int
    falsos_negativos: int

    @property
    def precisao(self) -> float:
        total = self.verdadeiros + self.falsos_positivos
        return self.verdadeiros / total if total else 0.0

    @property
    def recall(self) -> float:
        total = self.verdadeiros + self.falsos_negativos
        return self.verdadeiros / total if total else 0.0


def avaliar(
    predicoes: Sequence[Sequence[Deteccao]],
    verdade: Sequence[Sequence[Anotacao]],
    iou_minimo: float = 0.5,
    score_minimo: float = 0.5,
) -> ResultadoAvaliacao:
    """Casamento guloso por imagem, por score decrescente e mesma classe."""
    verdadeiros = falsos_positivos = falsos_negativos = 0
    for deteccoes, anotacoes in zip(predicoes, verdade, strict=True):
        livres = list(anotacoes)
        aceitas = sorted(
            (d for d in deteccoes if d.score >= score_minimo), key=lambda d: d.score, reverse=True
        )
        for deteccao in aceitas:
            melhor = max(
                (a for a in livres if a.rotulo == deteccao.rotulo),
                key=lambda a: iou(deteccao.caixa, a.caixa),
                default=None,
            )
            if melhor is not None and iou(deteccao.caixa, melhor.caixa) >= iou_minimo:
                livres.remove(melhor)
                verdadeiros += 1
            else:
                falsos_positivos += 1
        falsos_negativos += len(livres)
    return ResultadoAvaliacao(verdadeiros, falsos_positivos, falsos_negativos)


def _casa(a: Deteccao, b: Deteccao, iou_minimo: float) -> bool:
    return a.rotulo == b.rotulo and iou(a.caixa, b.caixa) >= iou_minimo


def _obrigatorias_casam(
    obrigatorias: Sequence[Deteccao], reserva: Sequence[Deteccao], iou_minimo: float
) -> bool:
    """Emparelhamento um a um (caminhos aumentantes) cobrindo todas as obrigatórias."""
    dono: dict[int, int] = {}

    def tenta(i: int, visitados: set[int]) -> bool:
        for j, candidata in enumerate(reserva):
            if j in visitados or not _casa(obrigatorias[i], candidata, iou_minimo):
                continue
            visitados.add(j)
            if j not in dono or tenta(dono[j], visitados):
                dono[j] = i
                return True
        return False

    return all(tenta(i, set()) for i in range(len(obrigatorias)))


def deteccoes_equivalentes(
    referencia: Sequence[Deteccao],
    candidata: Sequence[Deteccao],
    score_minimo: float = 0.30,
    margem: float = 0.05,
    iou_minimo: float = 0.99,
) -> bool:
    """Equivalência simétrica com margem de score; a referência é o PyTorch em CPU."""
    alto = score_minimo + margem
    baixo = score_minimo - margem
    for lado_a, lado_b in ((referencia, candidata), (candidata, referencia)):
        obrigatorias = [d for d in lado_a if d.score >= alto]
        reserva = [d for d in lado_b if d.score >= baixo]
        if not _obrigatorias_casam(obrigatorias, reserva, iou_minimo):
            return False
    return True


def perdas_equivalentes(
    referencia: Sequence[float],
    candidata: Sequence[float],
    tolerancia_relativa: float = 0.05,
) -> bool:
    """Perdas por iteração dentro da tolerância relativa, todas finitas."""
    if not referencia or len(referencia) != len(candidata):
        return False
    return all(
        math.isfinite(r)
        and math.isfinite(c)
        and abs(c - r) <= tolerancia_relativa * max(abs(r), 1e-6)
        for r, c in zip(referencia, candidata, strict=True)
    )


@dataclass(frozen=True)
class ResumoTempo:
    amostras: int
    mediana_s: float
    p95_s: float
    total_s: float


def resumir_tempos(tempos_s: Sequence[float]) -> ResumoTempo:
    """Mediana, p95 (nearest-rank) e total de uma série de tempos."""
    if not tempos_s:
        raise ValueError("sequência de tempos vazia")
    ordenados = sorted(tempos_s)
    posicao = math.ceil(0.95 * len(ordenados)) - 1
    return ResumoTempo(
        amostras=len(ordenados),
        mediana_s=statistics.median(ordenados),
        p95_s=ordenados[posicao],
        total_s=math.fsum(ordenados),
    )


def ladrilhos_por_folha(
    largura_px: int, altura_px: int, lado: int = 320, sobreposicao: float = 0.10
) -> int:
    """Quantidade de ladrilhos de `lado` px com sobreposição para cobrir a folha."""
    passo = round(lado * (1 - sobreposicao))

    def por_eixo(dimensao: int) -> int:
        return math.ceil(max(dimensao - lado, 0) / passo) + 1

    return por_eixo(largura_px) * por_eixo(altura_px)
