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
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ArithmeticError,
            RecursionError,
        ):
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


class _CacheInvalidoError(ValueError):
    """O conteúdo lido não tem a forma exata gravada por este módulo."""


def _objeto(valor: object) -> dict[str, Any]:
    if not isinstance(valor, dict):
        raise _CacheInvalidoError("objeto esperado")
    return cast(dict[str, Any], valor)


def _lista(valor: object) -> list[Any]:
    if not isinstance(valor, list):
        raise _CacheInvalidoError("lista esperada")
    return valor


def _texto(valor: object) -> str:
    if not isinstance(valor, str):
        raise _CacheInvalidoError("texto esperado")
    return valor


def _inteiro(valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise _CacheInvalidoError("inteiro esperado")
    return valor


def _natural(valor: object) -> int:
    inteiro = _inteiro(valor)
    if inteiro < 0:
        raise _CacheInvalidoError("valor não negativo esperado")
    return inteiro


def _booleano(valor: object) -> bool:
    if not isinstance(valor, bool):
        raise _CacheInvalidoError("booleano esperado")
    return valor


def _numero(valor: object) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise _CacheInvalidoError("número esperado")
    return float(valor)


def _dimensao(valor: object) -> float:
    numero = _numero(valor)
    if numero < 0:
        raise _CacheInvalidoError("valor não negativo esperado")
    return numero


def _numeros(valor: object, quantidade: int) -> tuple[float, ...]:
    itens = _lista(valor)
    if len(itens) != quantidade:
        raise _CacheInvalidoError("quantidade de números inesperada")
    return tuple(_numero(item) for item in itens)


def _ponto(valor: object) -> tuple[float, float]:
    x, y = _numeros(valor, 2)
    return (x, y)


def _caixa(valor: object) -> tuple[float, float, float, float]:
    a, b, c, d = _numeros(valor, 4)
    return (a, b, c, d)


def _cor(valor: object) -> tuple[float, float, float] | None:
    if valor is None:
        return None
    r, g, b = _numeros(valor, 3)
    return (r, g, b)


def _inteiros(valor: object) -> tuple[int, ...]:
    return tuple(_natural(item) for item in _lista(valor))


def _textos(valor: object) -> tuple[str, ...]:
    return tuple(_texto(item) for item in _lista(valor))


def _estilo(valor: object) -> Estilo:
    bruto = _objeto(valor)
    return Estilo(
        camada=_texto(bruto["camada"]),
        cor=_cor(bruto["cor"]),
        preenchimento=_cor(bruto["preenchimento"]),
        espessura=_numero(bruto["espessura"]),
        tracejado=_texto(bruto["tracejado"]),
    )


def _item(valor: object) -> ItemCaminho:
    bruto = _objeto(valor)
    tipo = bruto["tipo"]
    if tipo not in ("l", "c"):
        raise _CacheInvalidoError("tipo de item inválido")
    pontos = tuple(_ponto(p) for p in _lista(bruto["pontos"]))
    return ItemCaminho(tipo=tipo, pontos=pontos)


def _caminho(valor: object) -> Caminho:
    bruto = _objeto(valor)
    tipo = bruto["tipo"]
    if tipo not in ("traco", "preenchimento", "traco_e_preenchimento"):
        raise _CacheInvalidoError("tipo de caminho inválido")
    return Caminho(
        subcaminhos=tuple(
            tuple(_item(i) for i in _lista(sub)) for sub in _lista(bruto["subcaminhos"])
        ),
        estilo=_estilo(bruto["estilo"]),
        tipo=tipo,
        ordem=_inteiro(bruto["ordem"]),
    )


def _texto_modelo(valor: object) -> TextoModelo:
    bruto = _objeto(valor)
    origem = bruto["origem"]
    if origem not in ("nativo", "shx", "glifo"):
        raise _CacheInvalidoError("origem de texto inválida")
    return TextoModelo(
        texto=_texto(bruto["texto"]),
        bbox=_caixa(bruto["bbox"]),
        origem=origem,
        rotacao=_numero(bruto["rotacao"]),
        altura=_dimensao(bruto["altura"]),
        fonte=_texto(bruto["fonte"]),
        camada=_texto(bruto["camada"]),
    )


def _primitiva(valor: object) -> Polilinha | Circulo | Arco:
    bruto = _objeto(valor)
    estilo = _estilo(bruto["estilo"])
    origens = _inteiros(bruto["origens"])
    if "pontos" in bruto:
        pontos = tuple(_ponto(p) for p in _lista(bruto["pontos"]))
        return Polilinha(pontos, _booleano(bruto["fechada"]), estilo, origens)
    centro = _ponto(bruto["centro"])
    raio = _numero(bruto["raio"])
    if "angulo_inicial" in bruto:
        return Arco(
            centro,
            raio,
            _numero(bruto["angulo_inicial"]),
            _numero(bruto["angulo_final"]),
            estilo,
            origens,
        )
    return Circulo(centro, raio, estilo, origens)


def _grupo(valor: object) -> GrupoCandidato:
    bruto = _objeto(valor)
    return GrupoCandidato(
        _caixa(bruto["bbox"]),
        _inteiros(bruto["indices_primitivas"]),
        _inteiros(bruto["indices_caminhos"]),
    )


def _imagem(valor: object) -> ImagemModelo:
    bruto = _objeto(valor)
    return ImagemModelo(
        _caixa(bruto["bbox"]),
        _natural(bruto["largura_px"]),
        _natural(bruto["altura_px"]),
        _texto(bruto["sha256"]),
        _booleano(bruto["de_anotacao"]),
    )


def _pagina(valor: object) -> PaginaModelo:
    bruto = _objeto(valor)
    return PaginaModelo(
        indice=_natural(bruto["indice"]),
        largura=_dimensao(bruto["largura"]),
        altura=_dimensao(bruto["altura"]),
        caminhos=tuple(_caminho(i) for i in _lista(bruto["caminhos"])),
        textos=tuple(_texto_modelo(i) for i in _lista(bruto["textos"])),
        primitivas=tuple(_primitiva(i) for i in _lista(bruto["primitivas"])),
        grupos=tuple(_grupo(i) for i in _lista(bruto["grupos"])),
        imagens=tuple(_imagem(i) for i in _lista(bruto["imagens"])),
        diagnosticos=_textos(bruto["diagnosticos"]),
    )


def _sinal(valor: object) -> JsonPrimitive:
    if isinstance(valor, dict):
        marcado = _objeto(valor)
        if set(marcado) != {"decimal"}:
            raise _CacheInvalidoError("marcador de tipo desconhecido")
        try:
            return Decimal(_texto(marcado["decimal"]))
        except ArithmeticError as erro:
            raise _CacheInvalidoError("decimal inválido") from erro
    if valor is None or isinstance(valor, (str, int, bool)):
        return valor
    raise _CacheInvalidoError("sinal inválido")


def _par_de_sinal(valor: object) -> tuple[str, JsonPrimitive]:
    par = _lista(valor)
    if len(par) != 2:
        raise _CacheInvalidoError("sinal deve ser um par")
    return (_texto(par[0]), _sinal(par[1]))


def _familia(valor: object) -> PerfilFamilia:
    bruto = _objeto(valor)
    return PerfilFamilia(
        familia=_texto(bruto["familia"]),
        sinais=tuple(_par_de_sinal(i) for i in _lista(bruto["sinais"])),
        diagnosticos=_textos(bruto["diagnosticos"]),
    )


def _decodificar_modelo(valor: object) -> ModeloDesenho:
    bruto = _objeto(valor)
    return ModeloDesenho(
        versao=_texto(bruto["versao"]),
        documento_sha256=_texto(bruto["documento_sha256"]),
        familia=_familia(bruto["familia"]),
        paginas=tuple(_pagina(i) for i in _lista(bruto["paginas"])),
    )
