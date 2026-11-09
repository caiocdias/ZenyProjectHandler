"""Ancoragem do poste no disco do desenho: uma proposta por disco, P atribuído 1:1 ao sítio."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Final, TypeAlias
from uuid import UUID

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    SituacaoProjeto,
    TipoEvidencia,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

from .rule_support import center

_ROXO: Final = (0x4F, 0x1A, 0x4D)
_PALETA: Final = ((0, 0x70, 0), (0, 0xB3, 0), (0, 0x80, 0), _ROXO, (0xFF, 0, 0), (0, 0, 0))
_TOLERANCIA_COR: Final = 0.03
_ASPECTO: Final = (0.85, 1.15)
_DIAMETRO_PT: Final = (0.9, 7.0)
_RAIO_PAR: Final = 0.013
_RAIO_LEITURA: Final = 0.02
_RAIO_ATRIBUICAO: Final = 0.14
# Roxo (marca de retirada) é ruído frequente no entorno do poste: só vale colado ao rótulo.
_RAIO_ROXO: Final = 0.04
_MARGEM_AMBIGUIDADE: Final = 0.004
_ROTULO_POSTE: Final = re.compile(r"^(?:P\d{1,4}|\d{1,2}\s*-\s*\d{2,4})$", re.IGNORECASE)
# Tetos contra página hostil: acima deles a página não é ancorada (folhas reais têm dezenas).
_MAXIMO_DISCOS_POR_PAGINA: Final = 2_000
_MAXIMO_ROTULOS_POR_PAGINA: Final = 2_000
_MAXIMO_LEITURAS_POR_PAGINA: Final = 1_000
_MAXIMO_GRUPOS_POR_PAGINA: Final = 500
_CELULA_ROTULOS: Final = 0.05

_Caixa: TypeAlias = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class _Disco:
    id: UUID
    x: float
    y: float
    largura: float
    altura: float
    roxo: bool


@dataclass(frozen=True, slots=True)
class _Sitio:
    indice: int
    x: float
    y: float
    largura: float
    altura: float
    disco_ids: tuple[UUID, ...]
    so_roxo: bool


@dataclass(frozen=True, slots=True)
class _GrupoLeitura:
    indice: int
    identificador: str
    x: float
    y: float
    leitura_x: float
    leitura_y: float
    propostas: tuple[PropostaElemento, ...]


@dataclass(frozen=True, slots=True)
class _EvidenciasIndexadas:
    discos: dict[UUID, list[_Disco]]
    rotulos: dict[UUID, list[_Caixa]]
    centros_de_texto: dict[UUID, tuple[float, float]]


@dataclass(frozen=True, slots=True)
class _Candidaturas:
    pares: tuple[tuple[float, int, int], ...]
    por_grupo: dict[int, list[tuple[float, int]]]
    por_sitio: dict[int, list[tuple[float, int]]]


@dataclass(frozen=True, slots=True)
class _Atribuicao:
    sitios: dict[int, _Sitio]
    pendentes: frozenset[int]


@dataclass(frozen=True, slots=True)
class _Pilha:
    sobrevivente: PropostaElemento
    leituras: tuple[PropostaElemento, ...]
    decidida: bool


class _Grade:
    def __init__(self, celula: float) -> None:
        self._celula = celula
        self._itens: dict[tuple[int, int], list[int]] = defaultdict(list)

    def inserir(self, x: float, y: float, indice: int) -> None:
        self._itens[self._chave(x, y)].append(indice)

    def vizinhos(self, x: float, y: float) -> tuple[int, ...]:
        cx, cy = self._chave(x, y)
        return tuple(
            indice
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for indice in self._itens.get((cx + dx, cy + dy), ())
        )

    def _chave(self, x: float, y: float) -> tuple[int, int]:
        return (math.floor(x / self._celula), math.floor(y / self._celula))


def ancorar_postes_no_desenho(
    propostas: tuple[PropostaElemento, ...],
    evidencias: tuple[EvidenciaDocumento, ...],
) -> tuple[PropostaElemento, ...]:
    postes = _postes_ancoraveis(propostas)
    if not postes:
        return propostas
    paginas = frozenset(proposta.geometria.pagina_id for proposta in postes)
    indexadas = _indexar_evidencias(evidencias, paginas)
    substituicoes: dict[UUID, PropostaElemento | None] = {}
    for pagina_id, grupos in _grupos_de_leitura(postes, indexadas.centros_de_texto).items():
        sitios = _sitios_da_pagina(
            indexadas.discos.get(pagina_id, []),
            indexadas.rotulos.get(pagina_id, []),
            quantidade_de_grupos=len(grupos),
        )
        if sitios:
            substituicoes.update(_aplicar(grupos, _atribuir(grupos, sitios)))
    return tuple(
        novo
        for proposta in propostas
        if (novo := substituicoes.get(proposta.id, proposta)) is not None
    )


def _postes_ancoraveis(
    propostas: tuple[PropostaElemento, ...],
) -> tuple[PropostaElemento, ...]:
    """Postes identificados, fora de página acima do teto de leituras (agrupar é quadrático)."""
    identificados = tuple(
        proposta
        for proposta in propostas
        if proposta.categoria is CategoriaElemento.POSTE
        and isinstance(dict(proposta.atributos_sugeridos).get("identificador_operacional"), str)
    )
    por_pagina = Counter(proposta.geometria.pagina_id for proposta in identificados)
    return tuple(
        proposta
        for proposta in identificados
        if por_pagina[proposta.geometria.pagina_id] <= _MAXIMO_LEITURAS_POR_PAGINA
    )


def _sitios_da_pagina(
    discos: list[_Disco],
    rotulos: list[_Caixa],
    *,
    quantidade_de_grupos: int,
) -> list[_Sitio]:
    if (
        len(discos) > _MAXIMO_DISCOS_POR_PAGINA
        or len(rotulos) > _MAXIMO_ROTULOS_POR_PAGINA
        or quantidade_de_grupos > _MAXIMO_GRUPOS_POR_PAGINA
    ):
        return []
    return _sitios(_sem_glifos(discos, rotulos))


def _indexar_evidencias(
    evidencias: tuple[EvidenciaDocumento, ...],
    paginas: frozenset[UUID],
) -> _EvidenciasIndexadas:
    discos: dict[UUID, list[_Disco]] = defaultdict(list)
    rotulos: dict[UUID, list[_Caixa]] = defaultdict(list)
    centros_de_texto: dict[UUID, tuple[float, float]] = {}
    for evidencia in evidencias:
        if evidencia.pagina_id not in paginas:
            continue
        if evidencia.tipo is TipoEvidencia.VETOR:
            disco = _disco_de_poste(evidencia)
            if disco is not None:
                discos[evidencia.pagina_id].append(disco)
        elif evidencia.tipo in {TipoEvidencia.TEXTO, TipoEvidencia.OCR}:
            centros_de_texto[evidencia.id] = center(evidencia.geometria)
            if _ROTULO_POSTE.match((evidencia.conteudo_bruto or "").strip()):
                rotulos[evidencia.pagina_id].append(_caixa(evidencia.geometria))
    return _EvidenciasIndexadas(discos, rotulos, centros_de_texto)


def _disco_de_poste(evidencia: EvidenciaDocumento) -> _Disco | None:
    atributos = dict(evidencia.atributos_extraidos)
    cor = _componentes(atributos.get("cor_preenchimento"))
    if atributos.get("operacoes") != "c,c,c,c" or cor is None:
        return None
    if not any(_cor_proxima(cor, base) for base in _PALETA):
        return None
    pontos = _pontos_pdf(evidencia.conteudo_bruto)
    if not pontos:
        return None
    xs = [ponto[0] for ponto in pontos]
    ys = [ponto[1] for ponto in pontos]
    largura, altura = max(xs) - min(xs), max(ys) - min(ys)
    if altura <= 0 or not _ASPECTO[0] <= largura / altura <= _ASPECTO[1]:
        return None
    if not _DIAMETRO_PT[0] <= (largura + altura) / 2 <= _DIAMETRO_PT[1]:
        return None
    x0, y0, x1, y1 = _caixa(evidencia.geometria)
    if x1 <= x0 or y1 <= y0:
        return None
    return _Disco(
        evidencia.id, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0, _cor_proxima(cor, _ROXO)
    )


def _componentes(cor: object) -> tuple[int, int, int] | None:
    if not isinstance(cor, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", cor):
        return None
    return int(cor[1:3], 16), int(cor[3:5], 16), int(cor[5:7], 16)


def _cor_proxima(cor: tuple[int, int, int], base: tuple[int, int, int]) -> bool:
    return all(
        abs(observado - referencia) / 255 <= _TOLERANCIA_COR
        for observado, referencia in zip(cor, base, strict=True)
    )


def _pontos_pdf(conteudo: str | None) -> list[tuple[float, float]]:
    """Pontos em unidades de PDF do caminho; vazio se o conteúdo não for um caminho legível."""
    try:
        comandos = json.loads(conteudo or "")
        return [(float(valor[0]), float(valor[1])) for comando in comandos for valor in comando[1:]]
    except (TypeError, ValueError, LookupError, OverflowError, RecursionError):
        return []


def _sem_glifos(discos: list[_Disco], rotulos: list[_Caixa]) -> list[_Disco]:
    """Disco com o centro dentro da caixa de um rótulo de poste é fragmento de glifo."""
    por_celula: dict[tuple[int, int], list[_Caixa]] = defaultdict(list)
    for caixa in rotulos:
        x0, y0, x1, y1 = caixa
        for cx in range(_celula(x0), _celula(x1) + 1):
            for cy in range(_celula(y0), _celula(y1) + 1):
                por_celula[(cx, cy)].append(caixa)
    return [
        disco
        for disco in discos
        if not any(
            x0 <= disco.x <= x1 and y0 <= disco.y <= y1
            for x0, y0, x1, y1 in por_celula.get((_celula(disco.x), _celula(disco.y)), ())
        )
    ]


def _celula(valor: float) -> int:
    return math.floor(valor / _CELULA_ROTULOS)


def _sitios(discos: list[_Disco]) -> list[_Sitio]:
    """Une discos a até 0,013: o par das duas pontas do traço duplo é uma posição só."""
    pai = list(range(len(discos)))

    def raiz(indice: int) -> int:
        while pai[indice] != indice:
            pai[indice] = pai[pai[indice]]
            indice = pai[indice]
        return indice

    grade = _Grade(_RAIO_PAR)
    for indice, disco in enumerate(discos):
        grade.inserir(disco.x, disco.y, indice)
    for indice, disco in enumerate(discos):
        for outro in grade.vizinhos(disco.x, disco.y):
            if (
                outro > indice
                and math.dist((disco.x, disco.y), (discos[outro].x, discos[outro].y)) <= _RAIO_PAR
            ):
                pai[raiz(indice)] = raiz(outro)
    grupos: dict[int, list[_Disco]] = defaultdict(list)
    for indice, disco in enumerate(discos):
        grupos[raiz(indice)].append(disco)
    return [
        _Sitio(
            indice=posicao,
            x=sum(item.x for item in membros) / len(membros),
            y=sum(item.y for item in membros) / len(membros),
            largura=max(item.largura for item in membros),
            altura=max(item.altura for item in membros),
            disco_ids=tuple(sorted((item.id for item in membros), key=str)),
            so_roxo=all(item.roxo for item in membros),
        )
        for posicao, membros in enumerate(
            sorted(grupos.values(), key=lambda membros: min(str(item.id) for item in membros))
        )
    ]


def _grupos_de_leitura(
    postes: tuple[PropostaElemento, ...],
    centros_de_texto: dict[UUID, tuple[float, float]],
) -> dict[UUID, tuple[_GrupoLeitura, ...]]:
    """Leituras do mesmo P que vão disputar um único disco, por página."""
    por_identificador: dict[tuple[UUID, str], list[PropostaElemento]] = defaultdict(list)
    for proposta in postes:
        identificador = str(dict(proposta.atributos_sugeridos)["identificador_operacional"])
        por_identificador[(proposta.geometria.pagina_id, identificador)].append(proposta)
    agrupados: dict[UUID, list[_GrupoLeitura]] = defaultdict(list)
    for (pagina_id, identificador), itens in sorted(
        por_identificador.items(), key=lambda par: (str(par[0][0]), par[0][1])
    ):
        for membros in _agrupar_leituras(itens):
            xs, ys = zip(
                *(_origem_da_atribuicao(item, centros_de_texto) for item in membros),
                strict=True,
            )
            agrupados[pagina_id].append(
                _GrupoLeitura(
                    indice=len(agrupados[pagina_id]),
                    identificador=identificador,
                    x=sum(xs) / len(xs),
                    y=sum(ys) / len(ys),
                    leitura_x=sum(center(item.geometria)[0] for item in membros) / len(membros),
                    leitura_y=sum(center(item.geometria)[1] for item in membros) / len(membros),
                    propostas=tuple(membros),
                )
            )
    return {pagina_id: tuple(grupos) for pagina_id, grupos in agrupados.items()}


def _agrupar_leituras(itens: list[PropostaElemento]) -> list[list[PropostaElemento]]:
    """Mesmo rótulo P é um poste só; sem o rótulo, vale a proximidade de 0,02 das leituras."""
    por_rotulo: dict[str, list[PropostaElemento]] = defaultdict(list)
    sem_rotulo: list[PropostaElemento] = []
    for item in sorted(itens, key=lambda item: str(item.id)):
        rotulo = dict(item.atributos_sugeridos).get("evidencia_identificador_id")
        if isinstance(rotulo, str) and rotulo:
            por_rotulo[rotulo].append(item)
        else:
            sem_rotulo.append(item)
    grupos = [por_rotulo[rotulo] for rotulo in sorted(por_rotulo)]
    grupos.extend(_agrupar_proximos(sem_rotulo))
    return grupos


def _agrupar_proximos(ordenados: list[PropostaElemento]) -> list[list[PropostaElemento]]:
    grupos: list[list[PropostaElemento]] = []
    for item in ordenados:
        posicao = center(item.geometria)
        grupo = next(
            (
                existente
                for existente in grupos
                if any(
                    math.dist(posicao, center(outro.geometria)) <= _RAIO_LEITURA
                    for outro in existente
                )
            ),
            None,
        )
        if grupo is None:
            grupos.append([item])
        else:
            grupo.append(item)
    return grupos


def _origem_da_atribuicao(
    proposta: PropostaElemento,
    centros_de_texto: dict[UUID, tuple[float, float]],
) -> tuple[float, float]:
    """O rótulo P aponta o disco melhor que a nomenclatura; sem ele, vale o centro da proposta."""
    identificador = dict(proposta.atributos_sugeridos).get("evidencia_identificador_id")
    if isinstance(identificador, str):
        try:
            centro = centros_de_texto.get(UUID(identificador))
        except ValueError:
            centro = None
        if centro is not None:
            return centro
    return center(proposta.geometria)


def _atribuir(grupos: tuple[_GrupoLeitura, ...], sitios: list[_Sitio]) -> _Atribuicao:
    """P vai ao sítio mais próximo, com exclusão mútua; empate real (0,004) fica pendente."""
    candidaturas = _candidaturas(grupos, sitios)
    por_indice = {grupo.indice: grupo for grupo in grupos}
    atribuidos: dict[int, _Sitio] = {}
    pendentes: set[int] = set()
    tomados: set[int] = set()
    bloqueados: set[int] = set()
    for distancia, grupo_indice, sitio_indice in candidaturas.pares:
        if grupo_indice in atribuidos or grupo_indice in pendentes:
            continue
        if sitio_indice in bloqueados:
            # O sítio melhor que restava está em disputa: migrar seria cair no vizinho errado.
            pendentes.add(grupo_indice)
            continue
        if sitio_indice in tomados:
            continue
        resolvidos = atribuidos.keys() | pendentes
        rivais = _empatados(
            candidaturas.por_sitio[sitio_indice], grupo_indice, distancia, resolvidos
        )
        alternativas = _empatados(
            candidaturas.por_grupo[grupo_indice], sitio_indice, distancia, tomados
        )
        escolhido = sitio_indice
        if alternativas and not rivais:
            grupo = por_indice[grupo_indice]
            desempate = _desempate_pela_nomenclatura(grupo, [sitio_indice, *alternativas], sitios)
            if desempate is not None:
                escolhido, alternativas = desempate, []
                rivais = _empatados(
                    candidaturas.por_sitio[escolhido],
                    grupo_indice,
                    math.dist((grupo.x, grupo.y), (sitios[escolhido].x, sitios[escolhido].y)),
                    resolvidos,
                )
        if rivais or alternativas or escolhido in bloqueados:
            pendentes.update((grupo_indice, *rivais))
            bloqueados.update((sitio_indice, escolhido, *alternativas))
            continue
        atribuidos[grupo_indice] = sitios[escolhido]
        tomados.add(escolhido)
    return _Atribuicao(atribuidos, frozenset(pendentes))


def _candidaturas(grupos: tuple[_GrupoLeitura, ...], sitios: list[_Sitio]) -> _Candidaturas:
    grade = _Grade(_RAIO_ATRIBUICAO)
    for sitio in sitios:
        grade.inserir(sitio.x, sitio.y, sitio.indice)
    por_grupo: dict[int, list[tuple[float, int]]] = defaultdict(list)
    por_sitio: dict[int, list[tuple[float, int]]] = defaultdict(list)
    pares: list[tuple[float, int, int]] = []
    for grupo in grupos:
        for indice in grade.vizinhos(grupo.x, grupo.y):
            sitio = sitios[indice]
            distancia = math.dist((grupo.x, grupo.y), (sitio.x, sitio.y))
            if distancia <= (_RAIO_ROXO if sitio.so_roxo else _RAIO_ATRIBUICAO):
                pares.append((distancia, grupo.indice, sitio.indice))
                por_grupo[grupo.indice].append((distancia, sitio.indice))
                por_sitio[sitio.indice].append((distancia, grupo.indice))
    return _Candidaturas(tuple(sorted(pares)), por_grupo, por_sitio)


def _empatados(
    entradas: list[tuple[float, int]],
    proprio: int,
    distancia: float,
    excluidos: set[int],
) -> list[int]:
    return [
        outro
        for outra, outro in entradas
        if outro != proprio and outro not in excluidos and outra - distancia <= _MARGEM_AMBIGUIDADE
    ]


def _desempate_pela_nomenclatura(
    grupo: _GrupoLeitura,
    candidatos: list[int],
    sitios: list[_Sitio],
) -> int | None:
    """Rótulo P entre dois sítios: a nomenclatura decide, se apontar um deles com folga."""
    distancias = sorted(
        (math.dist((grupo.leitura_x, grupo.leitura_y), (sitios[i].x, sitios[i].y)), i)
        for i in candidatos
    )
    if distancias[1][0] - distancias[0][0] > _MARGEM_AMBIGUIDADE:
        return distancias[0][1]
    return None


def _aplicar(
    grupos: tuple[_GrupoLeitura, ...],
    atribuicao: _Atribuicao,
) -> dict[UUID, PropostaElemento | None]:
    repetidos = _identificadores_em_mais_de_um_sitio(grupos, atribuicao)
    substituicoes: dict[UUID, PropostaElemento | None] = {}
    for grupo in grupos:
        sitio = atribuicao.sitios.get(grupo.indice)
        if sitio is None:
            pendente = grupo.indice in atribuicao.pendentes
            for proposta in grupo.propostas:
                substituicoes[proposta.id] = _sem_ancora(proposta, pendente=pendente)
            continue
        pilha = _pilha_no_sitio(grupo.propostas, sitio)
        ids_da_pilha = {item.id for item in pilha.leituras}
        for proposta in grupo.propostas:
            # Leitura distante do mesmo rótulo P: outro poste, mantém posição e vínculos.
            substituicoes[proposta.id] = (
                None if proposta.id in ids_da_pilha else _sem_ancora(proposta, pendente=False)
            )
        substituicoes[pilha.sobrevivente.id] = _ancorado(
            _fundir_pilha(pilha),
            sitio,
            mesmo_identificador=grupo.identificador in repetidos,
        )
    return substituicoes


def _identificadores_em_mais_de_um_sitio(
    grupos: tuple[_GrupoLeitura, ...],
    atribuicao: _Atribuicao,
) -> set[str]:
    sitios_por_identificador: dict[str, set[int]] = defaultdict(set)
    for grupo in grupos:
        sitio = atribuicao.sitios.get(grupo.indice)
        if sitio is not None:
            sitios_por_identificador[grupo.identificador].add(sitio.indice)
    return {
        identificador
        for identificador, sitios in sitios_por_identificador.items()
        if len(sitios) > 1
    }


def _sem_ancora(proposta: PropostaElemento, *, pendente: bool) -> PropostaElemento:
    atributos = dict(proposta.atributos_sugeridos)
    atributos["poste_ancorado_disco"] = False
    if pendente and not atributos.get("associacao_pendente"):
        atributos["associacao_pendente"] = "poste_disco"
    return replace(proposta, atributos_sugeridos=tuple(atributos.items()))


def _pilha_no_sitio(propostas: tuple[PropostaElemento, ...], sitio: _Sitio) -> _Pilha:
    """A leitura mais próxima do disco situa a pilha; dentro dela, só a situação decide."""
    por_confianca = tuple(
        sorted(propostas, key=lambda item: (-(item.confianca or Decimal(0)), str(item.id)))
    )
    referencia = min(
        _que_permanecem(por_confianca),
        key=lambda item: (math.dist(center(item.geometria), (sitio.x, sitio.y)), str(item.id)),
    )
    leituras = tuple(
        item
        for item in por_confianca
        if math.dist(center(item.geometria), center(referencia.geometria)) <= _RAIO_LEITURA
    )
    permanecem = _que_permanecem(leituras)
    concordam = len({(item.codigo_observado, item.situacao_projeto) for item in permanecem}) == 1
    return _Pilha(permanecem[0], leituras, decidida=concordam)


def _que_permanecem(
    propostas: tuple[PropostaElemento, ...],
) -> tuple[PropostaElemento, ...]:
    return (
        tuple(item for item in propostas if item.situacao_projeto is not SituacaoProjeto.REMOVER)
        or propostas
    )


def _fundir_pilha(pilha: _Pilha) -> PropostaElemento:
    sobrevivente = pilha.sobrevivente
    if len(pilha.leituras) == 1:
        return sobrevivente
    atributos = dict(sobrevivente.atributos_sugeridos)
    alternativos = {
        item.codigo_observado
        for item in pilha.leituras
        if item.codigo_observado
        and (item.codigo_observado, item.situacao_projeto)
        != (sobrevivente.codigo_observado, sobrevivente.situacao_projeto)
    }
    if alternativos:
        atributos["poste_codigo_alternativo"] = ",".join(sorted(alternativos))
    fundida = replace(
        sobrevivente,
        evidencia_ids=tuple(
            sorted(
                {evidencia for item in pilha.leituras for evidencia in item.evidencia_ids}, key=str
            )
        ),
        atributos_sugeridos=tuple(atributos.items()),
    )
    if pilha.decidida:
        return fundida
    atributos["classificacao_pendente"] = True
    return replace(
        fundida,
        estado_revisao=EstadoRevisao.CONFLITANTE,
        tipo_catalogo_sugerido_id=None,
        atributos_sugeridos=tuple(atributos.items()),
    )


def _ancorado(
    proposta: PropostaElemento,
    sitio: _Sitio,
    *,
    mesmo_identificador: bool,
) -> PropostaElemento:
    atributos = dict(proposta.atributos_sugeridos)
    x, y = center(proposta.geometria)
    atributos["poste_ancorado_disco"] = True
    atributos["poste_texto_centro"] = f"{x:.6g},{y:.6g}"
    if mesmo_identificador and not atributos.get("associacao_pendente"):
        atributos["associacao_pendente"] = "poste_mesmo_identificador"
    return replace(
        proposta,
        evidencia_ids=tuple(sorted({*proposta.evidencia_ids, *sitio.disco_ids}, key=str)),
        geometria=_geometria_do_sitio(proposta.geometria.pagina_id, sitio),
        atributos_sugeridos=tuple(atributos.items()),
    )


def _geometria_do_sitio(pagina_id: UUID, sitio: _Sitio) -> GeometriaDocumento:
    meia_largura = sitio.largura / 2
    meia_altura = sitio.altura / 2
    return GeometriaDocumento.caixa(
        pagina_id,
        _ponto(sitio.x - meia_largura, sitio.y - meia_altura),
        _ponto(sitio.x + meia_largura, sitio.y + meia_altura),
    )


def _ponto(x: float, y: float) -> PontoNormalizado:
    return PontoNormalizado(
        Decimal(str(max(0.0, min(1.0, x)))),
        Decimal(str(max(0.0, min(1.0, y)))),
    )


def _caixa(geometria: GeometriaDocumento) -> _Caixa:
    xs = [float(ponto.x) for ponto in geometria.pontos]
    ys = [float(ponto.y) for ponto in geometria.pontos]
    return min(xs), min(ys), max(xs), max(ys)


__all__ = ["ancorar_postes_no_desenho"]
