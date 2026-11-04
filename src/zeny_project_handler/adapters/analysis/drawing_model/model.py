"""Tipos imutáveis do modelo de desenho, no espaço da página visual (y para baixo, pontos PDF)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from zeny_project_handler.domain.catalog import JsonPrimitive

VERSAO_MODELO_DESENHO: Final = "modelo-desenho-v2"

Ponto = tuple[float, float]
Caixa = tuple[float, float, float, float]
Cor = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class Estilo:
    camada: str
    cor: Cor | None
    preenchimento: Cor | None
    espessura: float
    tracejado: str


@dataclass(frozen=True, slots=True)
class ItemCaminho:
    """Segmento "l" (2 pontos) ou Bézier cúbica "c" (p0, c1, c2, p1)."""

    tipo: Literal["l", "c"]
    pontos: tuple[Ponto, ...]


@dataclass(frozen=True, slots=True)
class Caminho:
    subcaminhos: tuple[tuple[ItemCaminho, ...], ...]
    estilo: Estilo
    tipo: Literal["traco", "preenchimento", "traco_e_preenchimento"]
    ordem: int


@dataclass(frozen=True, slots=True)
class Polilinha:
    pontos: tuple[Ponto, ...]
    fechada: bool
    estilo: Estilo
    origens: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Circulo:
    centro: Ponto
    raio: float
    estilo: Estilo
    origens: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Arco:
    """Ângulos em graus, a partir do eixo x positivo, no sentido horário visual."""

    centro: Ponto
    raio: float
    angulo_inicial: float
    angulo_final: float
    estilo: Estilo
    origens: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TextoModelo:
    texto: str
    bbox: Caixa
    origem: Literal["nativo", "shx", "glifo"]
    rotacao: float
    altura: float
    fonte: str
    camada: str


@dataclass(frozen=True, slots=True)
class ImagemModelo:
    bbox: Caixa
    largura_px: int
    altura_px: int
    sha256: str
    de_anotacao: bool


@dataclass(frozen=True, slots=True)
class GrupoCandidato:
    bbox: Caixa
    indices_primitivas: tuple[int, ...]
    indices_caminhos: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PaginaModelo:
    indice: int
    largura: float
    altura: float
    caminhos: tuple[Caminho, ...]
    textos: tuple[TextoModelo, ...]
    primitivas: tuple[Polilinha | Circulo | Arco, ...]
    grupos: tuple[GrupoCandidato, ...]
    imagens: tuple[ImagemModelo, ...]
    diagnosticos: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PerfilFamilia:
    familia: str
    sinais: tuple[tuple[str, JsonPrimitive], ...]
    diagnosticos: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ModeloDesenho:
    versao: str
    documento_sha256: str
    familia: PerfilFamilia
    paginas: tuple[PaginaModelo, ...]
