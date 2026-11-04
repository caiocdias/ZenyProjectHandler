"""Cache JSON do modelo de desenho: derivado, descartável e com versão própria."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import fields, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from zeny_project_handler._atomic_files import sibling_temporary_file
from zeny_project_handler.domain.catalog import JsonPrimitive

from .model import (
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

_CACHE_KEY = re.compile(r"^[0-9a-f]{64}$")
_SCHEMA_VERSION = 1
_SUBDIRETORIO = "modelo-desenho"


def chave_modelo_desenho(
    documento_sha256: str, versao_leitor: str, versao: str = VERSAO_MODELO_DESENHO
) -> str:
    identidade = f"{documento_sha256}:{versao}:{versao_leitor}"
    return hashlib.sha256(identidade.encode("utf-8")).hexdigest()


class JsonDrawingModelCache:
    """Ausência, corrupção ou versão diferente equivalem a cache vazio."""

    def __init__(self, diretorio: Path) -> None:
        self._diretorio = diretorio.expanduser().resolve() / _SUBDIRETORIO

    def obter(self, chave: str) -> ModeloDesenho | None:
        alvo = self._alvo(chave)
        try:
            bruto = json.loads(alvo.read_text(encoding="utf-8"))
            if bruto.get("schema_version") != _SCHEMA_VERSION:
                return None
            modelo = _decodificar_modelo(cast(dict[str, Any], bruto["modelo"]))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None
        return modelo if modelo.versao == VERSAO_MODELO_DESENHO else None

    def salvar(self, chave: str, modelo: ModeloDesenho) -> None:
        alvo = self._alvo(chave)
        self._diretorio.mkdir(parents=True, exist_ok=True)
        conteudo = json.dumps(
            {"schema_version": _SCHEMA_VERSION, "modelo": _codificar(modelo)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with sibling_temporary_file(alvo) as temporario:
            temporario.write_text(conteudo, encoding="utf-8")
            temporario.replace(alvo)

    def _alvo(self, chave: str) -> Path:
        if not _CACHE_KEY.fullmatch(chave):
            raise ValueError("Chave de cache deve ser um SHA-256 hexadecimal")
        return self._diretorio / f"{chave}.json"


def _codificar(valor: object) -> object:
    if isinstance(valor, Decimal):
        return {"decimal": str(valor)}
    if is_dataclass(valor) and not isinstance(valor, type):
        return {campo.name: _codificar(getattr(valor, campo.name)) for campo in fields(valor)}
    if isinstance(valor, tuple):
        return [_codificar(item) for item in valor]
    return valor


def _ponto(valor: Any) -> tuple[float, float]:
    x, y = valor
    return (float(x), float(y))


def _caixa(valor: Any) -> tuple[float, float, float, float]:
    a, b, c, d = valor
    return (float(a), float(b), float(c), float(d))


def _cor(valor: Any) -> tuple[float, float, float] | None:
    if valor is None:
        return None
    r, g, b = valor
    return (float(r), float(g), float(b))


def _inteiros(valor: Any) -> tuple[int, ...]:
    return tuple(int(item) for item in valor)


def _textos(valor: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in valor)


def _estilo(bruto: dict[str, Any]) -> Estilo:
    return Estilo(
        camada=str(bruto["camada"]),
        cor=_cor(bruto["cor"]),
        preenchimento=_cor(bruto["preenchimento"]),
        espessura=float(bruto["espessura"]),
        tracejado=str(bruto["tracejado"]),
    )


def _item(bruto: dict[str, Any]) -> ItemCaminho:
    tipo = bruto["tipo"]
    if tipo not in ("l", "c"):
        raise ValueError("Tipo de item inválido no cache")
    return ItemCaminho(tipo=tipo, pontos=tuple(_ponto(p) for p in bruto["pontos"]))


def _caminho(bruto: dict[str, Any]) -> Caminho:
    tipo = bruto["tipo"]
    if tipo not in ("traco", "preenchimento", "traco_e_preenchimento"):
        raise ValueError("Tipo de caminho inválido no cache")
    return Caminho(
        subcaminhos=tuple(tuple(_item(i) for i in sub) for sub in bruto["subcaminhos"]),
        estilo=_estilo(bruto["estilo"]),
        tipo=tipo,
        ordem=int(bruto["ordem"]),
    )


def _texto(bruto: dict[str, Any]) -> TextoModelo:
    origem = bruto["origem"]
    if origem not in ("nativo", "shx"):
        raise ValueError("Origem de texto inválida no cache")
    return TextoModelo(
        texto=str(bruto["texto"]),
        bbox=_caixa(bruto["bbox"]),
        origem=origem,
        rotacao=float(bruto["rotacao"]),
        altura=float(bruto["altura"]),
        fonte=str(bruto["fonte"]),
        camada=str(bruto["camada"]),
    )


def _primitiva(bruto: dict[str, Any]) -> Polilinha | Circulo | Arco:
    estilo = _estilo(bruto["estilo"])
    origens = _inteiros(bruto["origens"])
    if "pontos" in bruto:
        return Polilinha(
            tuple(_ponto(p) for p in bruto["pontos"]), bool(bruto["fechada"]), estilo, origens
        )
    if "angulo_inicial" in bruto:
        return Arco(
            _ponto(bruto["centro"]),
            float(bruto["raio"]),
            float(bruto["angulo_inicial"]),
            float(bruto["angulo_final"]),
            estilo,
            origens,
        )
    return Circulo(_ponto(bruto["centro"]), float(bruto["raio"]), estilo, origens)


def _grupo(bruto: dict[str, Any]) -> GrupoCandidato:
    return GrupoCandidato(
        _caixa(bruto["bbox"]),
        _inteiros(bruto["indices_primitivas"]),
        _inteiros(bruto["indices_caminhos"]),
    )


def _imagem(bruto: dict[str, Any]) -> ImagemModelo:
    return ImagemModelo(
        _caixa(bruto["bbox"]),
        int(bruto["largura_px"]),
        int(bruto["altura_px"]),
        str(bruto["sha256"]),
        bool(bruto["de_anotacao"]),
    )


def _pagina(bruto: dict[str, Any]) -> PaginaModelo:
    return PaginaModelo(
        indice=int(bruto["indice"]),
        largura=float(bruto["largura"]),
        altura=float(bruto["altura"]),
        caminhos=tuple(_caminho(i) for i in bruto["caminhos"]),
        textos=tuple(_texto(i) for i in bruto["textos"]),
        primitivas=tuple(_primitiva(i) for i in bruto["primitivas"]),
        grupos=tuple(_grupo(i) for i in bruto["grupos"]),
        imagens=tuple(_imagem(i) for i in bruto["imagens"]),
        diagnosticos=_textos(bruto["diagnosticos"]),
    )


def _sinal(valor: object) -> JsonPrimitive:
    if isinstance(valor, dict) and set(valor) == {"decimal"}:
        return Decimal(str(valor["decimal"]))
    if valor is None or isinstance(valor, (str, int, bool)):
        return valor
    raise ValueError("Sinal inválido no cache")


def _familia(bruto: dict[str, Any]) -> PerfilFamilia:
    return PerfilFamilia(
        familia=str(bruto["familia"]),
        sinais=tuple((str(chave), _sinal(valor)) for chave, valor in bruto["sinais"]),
        diagnosticos=_textos(bruto["diagnosticos"]),
    )


def _decodificar_modelo(bruto: dict[str, Any]) -> ModeloDesenho:
    return ModeloDesenho(
        versao=str(bruto["versao"]),
        documento_sha256=str(bruto["documento_sha256"]),
        familia=_familia(bruto["familia"]),
        paginas=tuple(_pagina(i) for i in bruto["paginas"]),
    )
