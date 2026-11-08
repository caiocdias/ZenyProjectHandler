"""Ficha predita do benchmark por poste a partir das propostas da interpretação.

Fontes: ``propostas-v1`` (padrão) e ``propostas-v2``. A v2 difere só em três regras: estruturas
pelo ``token_estrutura`` (queda para ``codigo_observado``), código de cabo sem espaço depois de
hífen e estai sem relação ``INSTALADO_EM`` no poste de ``suporte_proposta_id``.

Lê ``variante["semantic"]`` (``PropostaElemento`` e ``PropostaRelacao`` depois da promoção
automática), não o projeto promovido. Uma proposta é presente em ``PROPOSTA``, ``CONFIRMADA`` ou
``CONFLITANTE``; ``REJEITADA`` nunca entra. Os vínculos vêm só das relações propostas
(``INSTALADA_EM``, ``INSTALADO_EM`` e ``CONECTA`` a poste da ficha), sem casamento geométrico.

Campo fornecido por proposta pendente (``CONFLITANTE`` ou com alguma das ``CHAVES_PENDENCIA``)
entra com o valor e o nome em ``pendentes`` do poste ou do vão, em ordem alfabética.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

from scripts.benchmark_ficha_poste import (
    VERSAO_EXTRACAO_PROPOSTAS,
    VERSAO_EXTRACAO_PROPOSTAS_V2,
    _bbox,
    _gerador,
)
from scripts.ficha_poste import _erro_classe
from zeny_project_handler.domain.analysis import PropostaElemento, PropostaRelacao
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    OrigemComprimentoVao,
)

# Cópia de ``pending_keys`` em ``automatic_promotion._promotable_proposals``; um teste compara
# as duas tuplas lendo o fonte.
CHAVES_PENDENCIA: Final[tuple[str, ...]] = (
    "revisao_tecnica_pendente",
    "revisao_tecnica_decidida",
    "reconciliacao_reanalise_pendente",
    "associacao_pendente",
    "comprimento_pendente",
    "reconciliacao_metodos_pendente",
    "verificacao_metodos_incompleta",
    "situacao_pendente",
    "quantidade_pendente",
    "catalogo_nao_localizado",
    "simbolo_legenda",
    "simbolo_familia_nao_suportada",
)

_ESTADOS_PRESENTES: Final = frozenset(
    {EstadoRevisao.PROPOSTA, EstadoRevisao.CONFIRMADA, EstadoRevisao.CONFLITANTE}
)
_ESTRUTURAS: Final = (CategoriaElemento.ESTRUTURA_MT, CategoriaElemento.ESTRUTURA_BT)

Ligacoes = Mapping[UUID, list[UUID]]


def _atributos(proposta: PropostaElemento) -> dict[str, Any]:
    return dict(proposta.atributos_sugeridos)


def _pendente(proposta: PropostaElemento) -> bool:
    atributos = _atributos(proposta)
    return proposta.estado_revisao is EstadoRevisao.CONFLITANTE or any(
        atributos.get(chave) for chave in CHAVES_PENDENCIA
    )


def _texto(valor: object) -> str | None:
    normalizado = str(valor).strip() if valor is not None else ""
    return normalizado or None


def _decimal_finito(valor: object) -> Decimal | None:
    """Decimal finito e representável como ``float`` finito; qualquer outro valor é ausente."""
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return None
    return numero if numero.is_finite() and math.isfinite(float(numero)) else None


def _coordenada(proposta: PropostaElemento) -> tuple[Decimal, Decimal] | None:
    atributos = _atributos(proposta)
    leste = _decimal_finito(atributos.get("coordenada_leste"))
    norte = _decimal_finito(atributos.get("coordenada_norte"))
    return None if leste is None or norte is None else (leste, norte)


def _elementos_presentes(propostas: Iterable[PropostaElemento]) -> dict[UUID, PropostaElemento]:
    presentes: dict[UUID, PropostaElemento] = {}
    for proposta in propostas:
        if proposta.estado_revisao in _ESTADOS_PRESENTES:
            presentes.setdefault(proposta.id, proposta)
    return presentes


def _ligacoes(
    relacoes: Iterable[PropostaRelacao], tipo: str, destinos: Mapping[UUID, Any]
) -> Ligacoes:
    """Destinos em poste da ficha, por origem, na ordem dos ids das relações presentes."""
    unicas = {
        relacao.id: relacao
        for relacao in relacoes
        if relacao.estado_revisao in _ESTADOS_PRESENTES and relacao.tipo_relacao == tipo
    }
    ligacoes: dict[UUID, list[UUID]] = {}
    for relacao in sorted(unicas.values(), key=lambda item: str(item.id)):
        if relacao.destino_referencia_id in destinos:
            ligacoes.setdefault(relacao.origem_referencia_id, []).append(
                relacao.destino_referencia_id
            )
    return ligacoes


def _poste(proposta: PropostaElemento, pagina: int) -> dict[str, Any]:
    atributos = _atributos(proposta)
    de_simbolo = "origem_simbolo_ocorrencia_id" in atributos
    coordenada = _coordenada(proposta)
    return {
        "id": str(proposta.id),
        "pagina": pagina,
        "bbox": _bbox(proposta.geometria),
        "identificador": _texto(atributos.get("identificador_operacional")),
        # Poste vindo de símbolo: codigo_observado é a classe do símbolo, não a nomenclatura.
        "poste": None if de_simbolo else proposta.codigo_observado,
        "coordenada": None
        if coordenada is None
        else {"leste": float(coordenada[0]), "norte": float(coordenada[1]), "zona": None},
        "estruturas": [],
        "simbolos": [],
        "pendentes": [],
        "atributos_extras": (
            {"origem": "simbolo", "classe_simbolo": proposta.codigo_observado} if de_simbolo else {}
        ),
    }


def _anexar_estruturas(
    elementos: Mapping[UUID, PropostaElemento],
    postes: Mapping[UUID, dict[str, Any]],
    ligacoes: Ligacoes,
    pendencias: dict[UUID, set[str]],
) -> int:
    sem_poste = 0
    for proposta in elementos.values():
        if proposta.categoria not in _ESTRUTURAS or not proposta.codigo_observado:
            continue
        destinos = ligacoes.get(proposta.id)
        if not destinos:
            sem_poste += 1
            continue
        postes[destinos[0]]["estruturas"].append(proposta.codigo_observado)
        if _pendente(proposta):
            pendencias[destinos[0]].add("estruturas")
    for poste in postes.values():
        poste["estruturas"].sort()
    return sem_poste


def _estrutura_v2(proposta: PropostaElemento) -> str | None:
    """Token da estrutura (com qualificador); sem ele, o código observado.

    Só texto ou número (não ``bool``) vira token; lista, dict, tupla, objeto e ``bool`` são
    atributo hostil e contam como ausente, em vez de virar o ``repr``.
    """
    token = _atributos(proposta).get("token_estrutura")
    textual = isinstance(token, str | int | float) and not isinstance(token, bool)
    return (_texto(token) if textual else None) or proposta.codigo_observado


def _codigo_cabo_v2(codigo: str | None) -> str | None:
    """Remove espaços depois de hífen e colapsa os demais (``N- (1N2)`` vira ``N-(1N2)``)."""
    if codigo is None:
        return None
    normalizado = re.sub(r"\s+", " ", re.sub(r"-\s+", "-", codigo)).strip()
    return normalizado or None


def _anexar_estruturas_v2(
    elementos: Mapping[UUID, PropostaElemento],
    postes: Mapping[UUID, dict[str, Any]],
    ligacoes: Ligacoes,
    pendencias: dict[UUID, set[str]],
) -> int:
    sem_poste = 0
    for proposta in elementos.values():
        estrutura = _estrutura_v2(proposta)
        if proposta.categoria not in _ESTRUTURAS or not estrutura:
            continue
        destinos = ligacoes.get(proposta.id)
        if not destinos:
            sem_poste += 1
            continue
        postes[destinos[0]]["estruturas"].append(estrutura)
        if _pendente(proposta):
            pendencias[destinos[0]].add("estruturas")
    for poste in postes.values():
        poste["estruturas"].sort()
    return sem_poste


def _com_estai_pelo_suporte(
    elementos: Mapping[UUID, PropostaElemento],
    postes: Mapping[UUID, Any],
    relacoes: Iterable[PropostaRelacao],
    ligacoes: Ligacoes,
) -> Ligacoes:
    """Acrescenta o poste de ``suporte_proposta_id`` ao estai sem relação ``INSTALADO_EM``."""
    com_relacao = {
        relacao.origem_referencia_id
        for relacao in relacoes
        if relacao.estado_revisao in _ESTADOS_PRESENTES and relacao.tipo_relacao == "INSTALADO_EM"
    }
    por_texto = {str(poste_id): poste_id for poste_id in postes}
    ampliadas = dict(ligacoes)
    for proposta in elementos.values():
        atributos = _atributos(proposta)
        suporte = atributos.get("suporte_proposta_id")
        if (
            proposta.categoria is CategoriaElemento.EQUIPAMENTO
            and atributos.get("simbolo_classe") == "ESTAI"
            and proposta.id not in com_relacao
            and suporte is not None
            and str(suporte) in por_texto
        ):
            ampliadas[proposta.id] = [por_texto[str(suporte)]]
    return ampliadas


def _anexar_simbolos(
    elementos: Mapping[UUID, PropostaElemento],
    postes: Mapping[UUID, dict[str, Any]],
    ligacoes: Ligacoes,
    pendencias: dict[UUID, set[str]],
) -> dict[str, int]:
    contagens = {
        "equipamentos_sem_simbolo": 0,
        "simbolos_sem_area": 0,
        "simbolos_fora_do_inventario": 0,
    }
    for proposta in elementos.values():
        if proposta.categoria is not CategoriaElemento.EQUIPAMENTO:
            continue
        classe = _atributos(proposta).get("simbolo_classe")
        if classe is None:
            contagens["equipamentos_sem_simbolo"] += 1
            continue
        destinos = ligacoes.get(proposta.id)
        if not destinos:
            contagens["simbolos_de_poste_fora_da_ficha"] = (
                contagens.get("simbolos_de_poste_fora_da_ficha", 0) + 1
            )
            continue
        classe = str(classe)
        if _erro_classe("simbolo", classe) is not None:
            contagens["simbolos_fora_do_inventario"] += 1
            continue
        bbox = _bbox(proposta.geometria)
        if bbox[0] == bbox[2] or bbox[1] == bbox[3]:
            contagens["simbolos_sem_area"] += 1
            continue
        postes[destinos[0]]["simbolos"].append(
            {"id": str(proposta.id), "classe": classe, "bbox": bbox}
        )
        if _pendente(proposta):
            pendencias[destinos[0]].add("simbolos")
    return contagens


def _comprimento(
    cabo: PropostaElemento, extremos: list[PropostaElemento]
) -> tuple[float | None, str | None, bool]:
    """Comprimento, origem e se ele depende de poste pendente (regra de ``_cable_length``)."""
    anotado = _decimal_finito(_atributos(cabo).get("comprimento_m"))
    if anotado is not None and anotado > 0:
        return float(anotado), OrigemComprimentoVao.ANOTACAO_DESENHO.value, False
    if len(extremos) != 2:
        return None, None, False
    inicio, fim = _coordenada(extremos[0]), _coordenada(extremos[1])
    if inicio is None or fim is None:
        return None, None, False
    try:
        distancia = ((fim[0] - inicio[0]) ** 2 + (fim[1] - inicio[1]) ** 2).sqrt()
        comprimento = float(distancia.quantize(Decimal("0.01")))
    except InvalidOperation:  # coordenadas astronômicas estouram a precisão do contexto
        return None, None, False
    if comprimento <= 0 or not math.isfinite(comprimento):
        return None, None, False
    return (
        comprimento,
        OrigemComprimentoVao.COORDENADAS.value,
        any(_pendente(extremo) for extremo in extremos),
    )


def _vao(
    cabo: PropostaElemento, ids: list[UUID], elementos: Mapping[UUID, PropostaElemento]
) -> dict[str, Any]:
    comprimento, origem, comprimento_pendente = _comprimento(cabo, [elementos[i] for i in ids])
    pendentes = {"cabo", "comprimento_m"} if _pendente(cabo) else set()
    if comprimento_pendente:
        pendentes.add("comprimento_m")
    return {
        "de": str(ids[0]),
        "para": str(ids[1]),
        "comprimento_m": comprimento,
        "cabo": cabo.codigo_observado,
        "pendentes": sorted(pendentes),
        "atributos_extras": {"origem_comprimento": origem},
    }


def _vaos(
    elementos: Mapping[UUID, PropostaElemento], ligacoes: Ligacoes
) -> tuple[list[dict[str, Any]], int]:
    vaos: list[dict[str, Any]] = []
    sem_vao = 0
    for proposta in elementos.values():
        if proposta.categoria is not CategoriaElemento.CABO:
            continue
        distintos = list(dict.fromkeys(ligacoes.get(proposta.id, ())))
        if len(distintos) == 2:
            vaos.append(_vao(proposta, distintos, elementos))
        else:
            sem_vao += 1
    return vaos, sem_vao


def ficha_predita_propostas(
    variante: Mapping[str, Any],
    pdf_sha256: str,
    *,
    native_only: bool,
    versao: str = VERSAO_EXTRACAO_PROPOSTAS,
) -> dict[str, Any]:
    """Ficha ``predicao`` das propostas presentes de uma variante de ``run_variant``."""
    if versao not in (VERSAO_EXTRACAO_PROPOSTAS, VERSAO_EXTRACAO_PROPOSTAS_V2):
        raise ValueError(f"versao desconhecida: {versao}")
    v2 = versao == VERSAO_EXTRACAO_PROPOSTAS_V2
    semantica = variante["semantic"]
    elementos = _elementos_presentes(semantica.elementos)
    paginas = {
        pagina.id: pagina.numero
        for documento in variante["project"].documentos
        for pagina in documento.paginas
    }
    candidatas = [item for item in elementos.values() if item.categoria is CategoriaElemento.POSTE]
    entregas = {
        item.id for item in candidatas if _atributos(item).get("tipo_ponto_rede") == "ENTREGA"
    }
    sem_pagina = {
        item.id
        for item in candidatas
        if item.id not in entregas and item.geometria.pagina_id not in paginas
    }
    postes = {
        item.id: _poste(item, paginas[item.geometria.pagina_id])
        for item in candidatas
        if item.id not in entregas and item.id not in sem_pagina
    }
    pendencias: dict[UUID, set[str]] = {
        poste_id: (
            {"identificador", "poste", "coordenada"} if _pendente(elementos[poste_id]) else set()
        )
        for poste_id in postes
    }
    relacoes = tuple(semantica.relacoes)
    anexar_estruturas = _anexar_estruturas_v2 if v2 else _anexar_estruturas
    estruturas_sem_poste = anexar_estruturas(
        elementos, postes, _ligacoes(relacoes, "INSTALADA_EM", postes), pendencias
    )
    instalados = _ligacoes(relacoes, "INSTALADO_EM", postes)
    if v2:
        instalados = _com_estai_pelo_suporte(elementos, postes, relacoes, instalados)
    contagens = _anexar_simbolos(elementos, postes, instalados, pendencias)
    vaos, cabos_sem_vao = _vaos(elementos, _ligacoes(relacoes, "CONECTA", postes))
    if v2:
        for vao in vaos:
            vao["cabo"] = _codigo_cabo_v2(vao["cabo"])
    for poste_id, poste in postes.items():
        poste["pendentes"] = sorted(pendencias[poste_id])
    # Estas chaves só aparecem quando ocorrem, para a raiz da ficha sem ocorrência seguir enxuta.
    contagens.update(
        {
            chave: valor
            for chave, valor in (
                ("postes_entrega", len(entregas)),
                ("postes_sem_pagina", len(sem_pagina)),
                ("estruturas_sem_poste", estruturas_sem_poste),
                ("cabos_sem_vao", cabos_sem_vao),
            )
            if valor
        }
    )
    return {
        "schema_version": 1,
        "tipo": "predicao",
        "pdf_sha256": pdf_sha256,
        "escopo_anotacao": {"tipo": "completo"},
        "gerador": _gerador(variante, native_only=native_only, versao_extracao=versao),
        "postes": list(postes.values()),
        "vaos": vaos,
        "atributos_extras": contagens,
    }
