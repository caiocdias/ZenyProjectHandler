"""Backlog agregado da onda: divergências agrupadas por causa provável e módulo dono.

Uso:
    python -m scripts.curation_backlog --rodada DIR --onda K

Lê, para cada PDF da onda, a comparação vigente (a do marco ``comparado`` do checkpoint,
conferida pelo SHA-256 registrado) e junta as divergências de todos os PDFs em grupos por
(tipo, família, ``class_id``, ``method_id``). Os grupos são priorizados pelo número de PDFs
afetados; em empate, pelo número de ocorrências e pelas ocorrências que nenhum método achou.
Cada grupo recebe os arquivos donos do método (mapa ``DONOS``, em
``src/zeny_project_handler/adapters/analysis/`` e ``symbol_packages/``) e até
``MAX_EXEMPLOS`` exemplos com tile de evidência. Grupos que compartilham algum arquivo dono
ficam na mesma pista de correção; por construção, pistas diferentes nunca compartilham arquivo
e podem ser corrigidas em paralelo. Método com falha de execução (ou sem registro de execução)
num PDF não mistura as divergências daquele PDF com as comuns: elas ficam retidas e o método
aparece em ``falhas_execucao`` (falha, não zero). O resultado vai para ``ondas/K/backlog.json``
e ``ondas/K/backlog.md`` (sem horário nem caminho absoluto; mesmas entradas, mesmos bytes).
Um grupo é hipótese de causa: o investigador confirma antes de corrigir.

Lacunas de cobertura (``curadoria-backlog-v2``, sobre ``curadoria-comparacao-v2``): como o
comparador só conta FN de um método nas classes que ele declara suportar, grupos FN de método
existem só para classes suportadas. As divergências ``sem_metodo`` (FN da união em classe que
nenhum método cobre) não viram grupo: ficam em ``lacunas_de_cobertura``, agrupadas por
(família, ``class_id``) com PDFs afetados, ocorrências e exemplos, ordenadas por PDFs afetados e
depois ocorrências, sem dono e sem pista (não entram em ``pistas`` nem em ``sem_dono``). Os
alertas da comparação (por exemplo ``metodo_sem_classes_suportadas``) são repassados com o
``pdf_id``. Comparação ``curadoria-comparacao-v1`` é recusada: gere de novo com curation_compare.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.curation_compare import ESQUEMA_COMPARACAO, METODO_UNIAO, NOME_COMPARACAO
from scripts.curation_reference import _indice_vigente
from scripts.curation_round import (
    PACOTES_SIMBOLOGIA,
    ROOT,
    RodadaError,
    _trava,
    carregar_checkpoint,
    carregar_rodada,
    escrever_bytes_atomico,
    hash_arquivo,
    json_canonico,
    ler_json,
    pdfs_da_onda,
)

# v2: ``lacunas_de_cobertura``, totais ``lacunas_de_cobertura``/``divergencias_em_lacunas``,
# ``pdfs[].divergencias_em_lacunas`` e alertas repassados da comparação.
ESQUEMA_BACKLOG = "curadoria-backlog-v2"
NIVEL_UNIAO = "uniao"
DIRETORIO_ONDAS = "ondas"
ARQUIVO_JSON = "backlog.json"
ARQUIVO_MD = "backlog.md"
MAX_EXEMPLOS = 5
ANALISE = "src/zeny_project_handler/adapters/analysis"
PACOTE_ANALISE = "zeny_project_handler.adapters.analysis"
METODO_PACOTES = "declarative-vector-packages"
STATUS_FALHA = "falha"
STATUS_SEM_REGISTRO = "sem_registro"
TIPOS_DIVERGENCIA = frozenset({"fp", "fn", "duplicata", "papel_errado", "id_errado"})
CAMPOS_DIVERGENCIA = frozenset(
    {
        "id",
        "tipo",
        "nivel",
        "conta_em",
        "method_id",
        "observacao_id",
        "predicao_id",
        "pagina",
        "camada",
        "familia",
        "class_id",
        "bbox",
        "tile_evidencia",
        "perdida_pela_uniao",
        "sem_metodo",
        "detalhe",
    }
)

# Arquivos que uma correção do método edita: o módulo que implementa o detector e, quando a
# versão do método mora em outro arquivo, também esse arquivo (mudar a saída exige incrementar a
# versão). Para ``declarative-vector-packages`` o pacote JSON da família entra em ``donos``.
# Dependências (módulos auxiliares importados) não são donas: ficam em ``dependencias``.
DONOS: Mapping[str, tuple[str, ...]] = {
    "legacy-vector-symbols": (f"{ANALISE}/pymupdf_analyzer.py", f"{ANALISE}/pymupdf_symbols.py"),
    "transformer-vector-shapes": (f"{ANALISE}/pymupdf_transformers.py",),
    "guy-vector-shapes": (f"{ANALISE}/pymupdf_guys.py",),
    "declarative-vector-packages": (f"{ANALISE}/declarative_symbols.py",),
    "raster-template": (f"{ANALISE}/raster_symbols.py",),
    "raster-hough-generalizado": (f"{ANALISE}/raster_symbols.py",),
    "structural-raster-graph": (f"{ANALISE}/structural_symbols.py",),
    "structural-vector-graph": (f"{ANALISE}/structural_symbols.py",),
    "document-local-legend": (f"{ANALISE}/legend_symbols.py",),
}
REGRA_PARALELISMO = (
    "grupos e falhas que compartilham algum arquivo dono ficam na mesma pista (fecho "
    "transitivo); pistas paralelas nunca compartilham arquivo dono; o corretor de uma pista só "
    "edita os arquivos dela; mudar uma dependência listada exige pista própria, em série"
)
LIMITACOES = (
    "Cada grupo é hipótese de causa: a mesma divergência pode ter causas diferentes em PDFs "
    "diferentes; o investigador confirma a causa antes de corrigir.",
    "As divergências vêm de referências de desenvolvimento geradas por IA (TP_IA/FP_IA/FN_IA), "
    "não de confirmação humana nem de norma.",
    "Divergências de método com falha ou sem registro de execução no PDF ficam retidas em "
    "falhas_execucao e não entram nos grupos (método indisponível é falha, não zero).",
    "Acoplamentos indicam dependência de arquivo editado por outra pista: depois de integrar "
    "uma pista, rode de novo os testes focados das pistas acopladas a ela.",
    "Lacunas de cobertura são faltas da união em classes que nenhum método declara suportar: "
    "não apontam defeito de detector, não têm dono nem pista e pedem decisão de cobertura "
    "(método novo ou suporte declarado), fora das correções da onda.",
)

Registro = dict[str, Any]


class BacklogRecusadoError(RodadaError):
    """Entrada inválida ou adulterada; nada é gravado."""


# --- donos e dependências ---------------------------------------------------------------------


def metodos_sem_dono(metodos: Iterable[str]) -> list[str]:
    """``method_id`` sem arquivo dono no mapa ``DONOS`` (ordenados)."""
    return sorted({metodo for metodo in metodos if not DONOS.get(metodo)})


def donos(method_id: str, familia: str | None, *, raiz: Path = ROOT) -> tuple[str, ...]:
    """Arquivos donos de uma divergência; vazio quando o método não tem dono."""
    arquivos = list(DONOS.get(method_id, ()))
    if arquivos and method_id == METODO_PACOTES and familia:
        pacote = PurePosixPath(PACOTES_SIMBOLOGIA, f"{familia}.json")
        if pacote.parent.as_posix() == PACOTES_SIMBOLOGIA and (raiz / pacote).is_file():
            arquivos.append(pacote.as_posix())
    return tuple(sorted(set(arquivos)))


def _importados(arquivo: str, raiz: Path) -> set[str]:
    caminho = raiz / arquivo
    if caminho.suffix != ".py" or not caminho.is_file():
        return set()
    arvore = ast.parse(caminho.read_text(encoding="utf-8"), filename=caminho.name)
    pasta = PurePosixPath(arquivo).parent
    achados: set[str] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.ImportFrom) or not no.module:
            continue
        if no.level == 1:
            alvo = pasta / f"{no.module.replace('.', '/')}.py"
        elif no.level == 0 and no.module.startswith(f"{PACOTE_ANALISE}."):
            alvo = PurePosixPath(ANALISE, *no.module.split(".")[4:]).with_suffix(".py")
        else:
            continue
        if (raiz / alvo).is_file():
            achados.add(alvo.as_posix())
    return achados


def dependencias(arquivos: Iterable[str], *, raiz: Path = ROOT) -> list[str]:
    """Módulos do pacote de análise importados (transitivamente) pelos arquivos, menos eles."""
    proprios = set(arquivos)
    vistos: set[str] = set()
    pendentes = list(proprios)
    while pendentes:
        for importado in _importados(pendentes.pop(), raiz):
            if importado not in vistos:
                vistos.add(importado)
                pendentes.append(importado)
    return sorted(vistos - proprios)


# --- pistas -----------------------------------------------------------------------------------


def _componentes(itens: Sequence[Registro]) -> list[list[Registro]]:
    """Fecho transitivo por arquivo dono em comum (união-busca sobre os arquivos)."""
    pai: dict[str, str] = {}

    def raiz_de(arquivo: str) -> str:
        while pai[arquivo] != arquivo:
            pai[arquivo] = pai[pai[arquivo]]
            arquivo = pai[arquivo]
        return arquivo

    for item in itens:
        arquivos = list(item["donos"])
        for arquivo in arquivos:
            pai.setdefault(arquivo, arquivo)
        for arquivo in arquivos[1:]:
            pai[raiz_de(arquivo)] = raiz_de(arquivos[0])
    por_raiz: dict[str, list[Registro]] = defaultdict(list)
    for item in itens:
        por_raiz[raiz_de(item["donos"][0])].append(item)
    return list(por_raiz.values())


def _pista(membros: Sequence[Registro]) -> Registro:
    arquivos = sorted({arquivo for item in membros for arquivo in item["donos"]})
    pdfs = sorted({pdf for item in membros for pdf in item["pdfs"]})
    return {
        "arquivos": arquivos,
        "itens": [str(item["id"]) for item in membros],
        "pdfs": pdfs,
        "pdfs_afetados": len(pdfs),
        "ocorrencias": sum(int(item["ocorrencias"]) for item in membros),
    }


def arquivos_compartilhados(pistas: Sequence[Registro]) -> list[Registro]:
    """Pares de pistas que compartilham arquivo (sempre vazio quando as pistas são corretas)."""
    conflitos = []
    for posicao, primeira in enumerate(pistas):
        for segunda in pistas[posicao + 1 :]:
            comuns = sorted(set(primeira["arquivos"]) & set(segunda["arquivos"]))
            if comuns:
                conflitos.append({"pistas": [primeira["id"], segunda["id"]], "arquivos": comuns})
    return conflitos


def formar_pistas(itens: Sequence[Registro], *, raiz: Path = ROOT) -> list[Registro]:
    """Pistas a partir de itens ``{id, donos, pdfs, ocorrencias}`` com ao menos um dono.

    Ordem: mais PDFs afetados, mais ocorrências, arquivos. ``paralela`` é conferida par a par
    (arquivos não vazios e disjuntos de todas as outras pistas).
    """
    com_dono = [item for item in itens if item["donos"]]
    pistas = sorted(
        (_pista(membros) for membros in _componentes(com_dono)),
        key=lambda p: (-p["pdfs_afetados"], -p["ocorrencias"], p["arquivos"]),
    )
    for numero, pista in enumerate(pistas, start=1):
        pista["id"] = f"pista-{numero:02d}"
    conflitantes = {pid for item in arquivos_compartilhados(pistas) for pid in item["pistas"]}
    dono_de = {arquivo: pista["id"] for pista in pistas for arquivo in pista["arquivos"]}
    for pista in pistas:
        pista["paralela"] = bool(pista["arquivos"]) and pista["id"] not in conflitantes
        pista["dependencias"] = dependencias(pista["arquivos"], raiz=raiz)
        pista["acoplamentos"] = [
            {"arquivo": arquivo, "pista": dono_de[arquivo]}
            for arquivo in pista["dependencias"]
            if arquivo in dono_de and dono_de[arquivo] != pista["id"]
        ]
    return pistas


# --- entradas ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class EntradaPdf:
    """Comparação vigente de um PDF (ou ``None``) com o mapa tile → arquivo do índice."""

    pdf_id: str
    fase: str
    auditado: bool
    comparacao: Registro | None
    arquivo: str | None
    sha256: str | None
    tiles: Mapping[str, str] = field(default_factory=dict)
    alertas: tuple[Registro, ...] = ()


def _validar_divergencia(pdf_id: str, item: Any) -> None:
    if not isinstance(item, dict) or not item.keys() >= CAMPOS_DIVERGENCIA:
        raise BacklogRecusadoError(f"{pdf_id}: divergência sem os campos de curation_compare")
    if item["tipo"] not in TIPOS_DIVERGENCIA or not isinstance(item["method_id"], str):
        raise BacklogRecusadoError(
            f"{pdf_id}: divergência {item['id']} com tipo ou método inválido"
        )
    lacuna = item["sem_metodo"]
    coerente = (
        (item["tipo"], item["nivel"], item["method_id"]) == ("fn", NIVEL_UNIAO, METODO_UNIAO)
        if lacuna is True
        else lacuna is False and item["nivel"] != NIVEL_UNIAO
    )
    if not coerente:
        raise BacklogRecusadoError(
            f"{pdf_id}: divergência {item['id']} com sem_metodo incoerente (só FN do nível "
            f"{NIVEL_UNIAO}, method_id {METODO_UNIAO}, tem sem_metodo = true)"
        )


def _validar_alertas(pdf_id: str, alertas: Any) -> None:
    if not isinstance(alertas, list) or not all(
        isinstance(item, dict) and isinstance(item.get("tipo"), str) for item in alertas
    ):
        raise BacklogRecusadoError(f"{pdf_id}: alertas da comparação inválidos")


def validar_comparacao(pdf_id: str, dados: Any) -> Registro:
    """Confere esquema, PDF, vigência e o formato das divergências (``curadoria-comparacao-v2``)."""
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_COMPARACAO:
        esquema = dados.get("schema_version") if isinstance(dados, dict) else None
        raise BacklogRecusadoError(
            f"{pdf_id}: comparação com esquema {esquema!r} (esperado {ESQUEMA_COMPARACAO}); "
            "gere a comparação de novo com curation_compare"
        )
    if dados.get("pdf_id") != pdf_id:
        raise BacklogRecusadoError(f"{pdf_id}: comparação de outro PDF")
    if dados.get("vigente") is not True:
        raise BacklogRecusadoError(f"{pdf_id}: comparação do marco não é vigente")
    divergencias = dados.get("divergencias")
    if not isinstance(divergencias, list) or not isinstance(dados.get("metodos"), dict):
        raise BacklogRecusadoError(f"{pdf_id}: comparação sem divergências ou métodos")
    if not isinstance(dados.get("metodos_com_falha", []), list):
        raise BacklogRecusadoError(f"{pdf_id}: metodos_com_falha inválido")
    _validar_alertas(pdf_id, dados.get("alertas", []))
    for item in divergencias:
        _validar_divergencia(pdf_id, item)
    ids = Counter(str(item["id"]) for item in divergencias)
    repetidas = sorted(chave for chave, total in ids.items() if total > 1)
    if repetidas:
        raise BacklogRecusadoError(f"{pdf_id}: divergência repetida: {', '.join(repetidas)}")
    return dados


def _tiles(rodada_dir: Path, pdf_id: str, checkpoint: Registro) -> tuple[dict[str, str], bool]:
    try:
        indice, _ = _indice_vigente(rodada_dir, pdf_id, checkpoint)
    except (RodadaError, OSError, ValueError):
        return {}, False
    return {str(t["id"]): str(t["arquivo"]) for t in indice.get("tiles", [])}, True


def _arquivo_do_marco(pdf_id: str, marco: Registro) -> Registro:
    artefatos = marco.get("artefatos") or []
    if len(artefatos) != 1 or artefatos[0].get("tipo") != "arquivo":
        raise BacklogRecusadoError(f"{pdf_id}: marco comparado sem exatamente um arquivo")
    caminho = PurePosixPath(str(artefatos[0]["caminho"]))
    if caminho.parent != PurePosixPath("pdfs", pdf_id) or not NOME_COMPARACAO.fullmatch(
        caminho.name
    ):
        raise BacklogRecusadoError(f"{pdf_id}: marco comparado aponta para fora de pdfs/{pdf_id}")
    return dict(artefatos[0])


def carregar_entrada(rodada_dir: Path, pdf_id: str) -> EntradaPdf:
    """Lê a comparação do marco ``comparado``; recusa arquivo ausente ou com SHA-256 diferente."""
    raiz = Path(rodada_dir).resolve()
    checkpoint = carregar_checkpoint(raiz, pdf_id)
    marcos = checkpoint["marcos"]
    tiles, indice_ok = _tiles(raiz, pdf_id, checkpoint)
    alertas = () if indice_ok else (_alerta("indice_tiles_indisponivel", pdf_id=pdf_id),)
    marco = marcos.get("comparado")
    if marco is None:
        return EntradaPdf(
            pdf_id=pdf_id,
            fase=checkpoint["fase"],
            auditado="auditado" in marcos,
            comparacao=None,
            arquivo=None,
            sha256=None,
            tiles=tiles,
            alertas=alertas,
        )
    registro = _arquivo_do_marco(pdf_id, marco)
    arquivo = raiz / registro["caminho"]
    if not arquivo.is_file() or hash_arquivo(arquivo) != registro["sha256"]:
        raise BacklogRecusadoError(
            f"{pdf_id}: comparação vigente difere do registrado no marco comparado"
        )
    return EntradaPdf(
        pdf_id=pdf_id,
        fase=checkpoint["fase"],
        auditado="auditado" in marcos,
        comparacao=validar_comparacao(pdf_id, ler_json(arquivo)),
        arquivo=str(registro["caminho"]),
        sha256=str(registro["sha256"]),
        tiles=tiles,
        alertas=alertas,
    )


# --- agregação --------------------------------------------------------------------------------


def _alerta(tipo: str, **campos: Any) -> Registro:
    return {"tipo": tipo, **campos}


def _hash_curto(valor: Any) -> str:
    return sha256(json_canonico(valor).encode("utf-8")).hexdigest()[:12]


def _status_metodos(comparacao: Registro) -> dict[str, str]:
    status = {
        str(metodo): str((dados.get("execucao") or {}).get("status"))
        for metodo, dados in comparacao["metodos"].items()
        if isinstance(dados, dict)
    }
    for metodo in comparacao.get("metodos_com_falha", []):
        status[str(metodo)] = STATUS_FALHA
    return status


def _locais_de_falha(comparacao: Registro, metodo: str) -> list[Registro]:
    dados = comparacao["metodos"].get(metodo) or {}
    falhas = (dados.get("execucao") or {}).get("falhas") or []
    return [{"camada": item.get("camada"), "pagina": item.get("pagina")} for item in falhas]


def _tile_arquivo(entrada: EntradaPdf, tile: Any) -> str | None:
    if not isinstance(tile, str) or tile not in entrada.tiles:
        return None
    caminho = PurePosixPath(entrada.tiles[tile])
    prefixo = PurePosixPath("pdfs", entrada.pdf_id)
    if caminho.is_absolute() or ".." in caminho.parts or not caminho.is_relative_to(prefixo):
        return None
    return caminho.as_posix()


@dataclass
class _Acumulador:
    ordem: Mapping[str, int]
    grupos: dict[tuple[str, ...], list[tuple[EntradaPdf, Registro]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    falhas: dict[tuple[str, str], list[tuple[EntradaPdf, int]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    lacunas: dict[tuple[str, str], list[tuple[EntradaPdf, Registro]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    alertas: list[Registro] = field(default_factory=list)
    resumos: list[Registro] = field(default_factory=list)


def _chave(item: Registro) -> tuple[str, str, str, str]:
    return (
        str(item["tipo"]),
        str(item["familia"]),
        str(item["class_id"]),
        str(item["method_id"]),
    )


def _resumo_pdf(entrada: EntradaPdf) -> Registro:
    comparacao = None
    if entrada.arquivo is not None:
        comparacao = {
            "arquivo": entrada.arquivo,
            "sha256": entrada.sha256,
            "versao": PurePosixPath(entrada.arquivo).name,
        }
    return {
        "pdf_id": entrada.pdf_id,
        "fase": entrada.fase,
        "referencia_auditada": entrada.auditado,
        "comparacao": comparacao,
        "escopo": (entrada.comparacao or {}).get("escopo"),
        "divergencias": len((entrada.comparacao or {}).get("divergencias", [])),
        "divergencias_retidas": {},
        "divergencias_em_lacunas": 0,
        "metodos_com_falha": [],
        "metodos_sem_registro": [],
    }


def _acumular(acc: _Acumulador, entrada: EntradaPdf) -> None:
    resumo = _resumo_pdf(entrada)
    acc.resumos.append(resumo)
    acc.alertas.extend(entrada.alertas)
    if entrada.comparacao is None:
        acc.alertas.append(_alerta("sem_comparacao_vigente", pdf_id=entrada.pdf_id))
        return
    comparacao = validar_comparacao(entrada.pdf_id, entrada.comparacao)
    if not entrada.auditado:
        acc.alertas.append(_alerta("referencia_nao_auditada", pdf_id=entrada.pdf_id))
    acc.alertas.extend(
        {**alerta, "pdf_id": entrada.pdf_id} for alerta in comparacao.get("alertas", [])
    )
    status = _status_metodos(comparacao)
    indisponiveis = {m: s for m, s in status.items() if s in {STATUS_FALHA, STATUS_SEM_REGISTRO}}
    retidas: Counter[str] = Counter()
    for item in comparacao["divergencias"]:
        if item["sem_metodo"]:
            acc.lacunas[(str(item["familia"]), str(item["class_id"]))].append((entrada, item))
            resumo["divergencias_em_lacunas"] += 1
        elif item["method_id"] in indisponiveis:
            retidas[item["method_id"]] += 1
        else:
            acc.grupos[_chave(item)].append((entrada, item))
    for metodo, estado in sorted(indisponiveis.items()):
        acc.falhas[(estado, metodo)].append((entrada, retidas[metodo]))
        campo = "metodos_com_falha" if estado == STATUS_FALHA else "metodos_sem_registro"
        resumo[campo].append(metodo)
        tipo = "metodo_com_falha" if estado == STATUS_FALHA else "metodo_sem_registro"
        acc.alertas.append(
            _alerta(tipo, pdf_id=entrada.pdf_id, method_id=metodo, retidas=retidas[metodo])
        )
    resumo["divergencias_retidas"] = dict(sorted(retidas.items()))


def _exemplos(acc: _Acumulador, membros: Sequence[tuple[EntradaPdf, Registro]]) -> list[Registro]:
    """Até ``MAX_EXEMPLOS``, alternando entre os PDFs na ordem da onda."""
    por_pdf: dict[str, list[tuple[EntradaPdf, Registro]]] = defaultdict(list)
    for entrada, item in sorted(
        membros,
        key=lambda par: (
            acc.ordem[par[0].pdf_id],
            par[1]["pagina"],
            par[1]["camada"],
            par[1]["id"],
        ),
    ):
        por_pdf[entrada.pdf_id].append((entrada, item))
    filas = [por_pdf[pdf] for pdf in sorted(por_pdf, key=acc.ordem.__getitem__)]
    escolhidos = [par for rodada in _intercalar(filas) for par in rodada][:MAX_EXEMPLOS]
    exemplos = []
    for entrada, item in escolhidos:
        tile = _tile_arquivo(entrada, item["tile_evidencia"])
        if tile is None:
            acc.alertas.append(
                _alerta(
                    "tile_sem_arquivo",
                    pdf_id=entrada.pdf_id,
                    divergencia_id=item["id"],
                    tile_evidencia=item["tile_evidencia"],
                )
            )
        exemplos.append(
            {
                "pdf_id": entrada.pdf_id,
                "divergencia_id": item["id"],
                "comparacao": entrada.arquivo,
                "pagina": item["pagina"],
                "camada": item["camada"],
                "bbox": item["bbox"],
                "tile_evidencia": item["tile_evidencia"],
                "tile_arquivo": tile,
                "observacao_id": item["observacao_id"],
                "predicao_id": item["predicao_id"],
                "motivo": (item.get("detalhe") or {}).get("motivo"),
                "perdida_pela_uniao": item["perdida_pela_uniao"],
            }
        )
    return exemplos


def _intercalar(filas: Sequence[Sequence[tuple[EntradaPdf, Registro]]]) -> list[list[Any]]:
    """Intercala as filas: o primeiro item de cada uma, depois o segundo, e assim por diante."""
    maior = max((len(fila) for fila in filas), default=0)
    return [[fila[n] for fila in filas if n < len(fila)] for n in range(maior)]


def _grupo(
    acc: _Acumulador, chave: tuple[str, ...], membros: Sequence[tuple[EntradaPdf, Registro]]
) -> Registro:
    tipo, familia, classe, metodo = chave
    por_pdf = Counter(entrada.pdf_id for entrada, _ in membros)
    pdfs = sorted(por_pdf, key=acc.ordem.__getitem__)
    conta_em = Counter(str(item["conta_em"] or "diagnostico") for _, item in membros)
    return {
        "id": "grp-" + _hash_curto(list(chave)),
        "tipo": tipo,
        "familia": familia,
        "class_id": classe,
        "method_id": metodo,
        "pdfs_afetados": len(pdfs),
        "pdfs": pdfs,
        "ocorrencias": len(membros),
        "ocorrencias_por_pdf": {pdf: por_pdf[pdf] for pdf in pdfs},
        "perdidas_pela_uniao": sum(1 for _, item in membros if item["perdida_pela_uniao"]),
        "conta_em": dict(sorted(conta_em.items())),
        "diagnostico": set(conta_em) == {"diagnostico"},
        "motivos": dict(
            sorted(Counter(str((i.get("detalhe") or {}).get("motivo")) for _, i in membros).items())
        ),
        "donos": list(donos(metodo, familia)),
        "exemplos": _exemplos(acc, membros),
    }


def _ordenar_grupos(grupos: list[Registro]) -> list[Registro]:
    grupos.sort(
        key=lambda g: (
            -g["pdfs_afetados"],
            -g["ocorrencias"],
            -g["perdidas_pela_uniao"],
            g["tipo"],
            g["familia"],
            g["class_id"],
            g["method_id"],
        )
    )
    for posicao, grupo in enumerate(grupos, start=1):
        grupo["prioridade"] = posicao
    return grupos


def _lacuna(
    acc: _Acumulador, chave: tuple[str, str], membros: Sequence[tuple[EntradaPdf, Registro]]
) -> Registro:
    """Lacuna de cobertura (família e classe sem método): sem dono, sem pista, sem método."""
    familia, classe = chave
    por_pdf = Counter(entrada.pdf_id for entrada, _ in membros)
    pdfs = sorted(por_pdf, key=acc.ordem.__getitem__)
    return {
        "id": "lac-" + _hash_curto(["lacuna", familia, classe]),
        "familia": familia,
        "class_id": classe,
        "pdfs_afetados": len(pdfs),
        "pdfs": pdfs,
        "ocorrencias": len(membros),
        "ocorrencias_por_pdf": {pdf: por_pdf[pdf] for pdf in pdfs},
        "exemplos": _exemplos(acc, membros),
    }


def _ordenar_lacunas(lacunas: list[Registro]) -> list[Registro]:
    lacunas.sort(
        key=lambda g: (-g["pdfs_afetados"], -g["ocorrencias"], g["familia"], g["class_id"])
    )
    for posicao, lacuna in enumerate(lacunas, start=1):
        lacuna["prioridade"] = posicao
    return lacunas


def _falha(acc: _Acumulador, chave: tuple[str, str], membros: Sequence[Any]) -> Registro:
    estado, metodo = chave
    pdfs = sorted({e.pdf_id for e, _ in membros}, key=acc.ordem.__getitem__)
    locais = {
        e.pdf_id: _locais_de_falha(e.comparacao or {"metodos": {}}, metodo) for e, _ in membros
    }
    return {
        "id": f"{'falha' if estado == STATUS_FALHA else 'sem-registro'}-" + _hash_curto(metodo),
        "method_id": metodo,
        "status": estado,
        "pdfs_afetados": len(pdfs),
        "pdfs": pdfs,
        "locais": {pdf: locais[pdf] for pdf in pdfs if locais[pdf]},
        "divergencias_retidas": sum(int(total) for _, total in membros),
        # Sem registro não aponta defeito no detector (pode ser configuração da inferência):
        # fica fora das pistas até o investigador decidir.
        "donos": list(donos(metodo, None)) if estado == STATUS_FALHA else [],
        "ocorrencias": len(pdfs),
    }


def _ligar_pistas(grupos: list[Registro], falhas: list[Registro]) -> list[Registro]:
    itens = [*grupos, *falhas]
    pistas = formar_pistas(itens)
    pista_de = {item_id: pista["id"] for pista in pistas for item_id in pista["itens"]}
    for item in itens:
        item["pista"] = pista_de.get(item["id"])
    ids_falhas = {falha["id"] for falha in falhas}
    for pista in pistas:
        membros = pista.pop("itens")
        pista["grupos"] = [m for m in membros if m not in ids_falhas]
        pista["falhas_execucao"] = [m for m in membros if m in ids_falhas]
        pista["prioridade"] = min(
            (g["prioridade"] for g in grupos if g["pista"] == pista["id"]), default=None
        )
    return pistas


def _ordenar_alertas(alertas: Iterable[Registro]) -> list[Registro]:
    unicos = {json_canonico(item): item for item in alertas}
    return [unicos[chave] for chave in sorted(unicos)]


def agregar(onda: int, entradas: Sequence[EntradaPdf]) -> Registro:
    """Backlog da onda a partir das comparações vigentes (puro e determinístico)."""
    acc = _Acumulador(ordem={entrada.pdf_id: n for n, entrada in enumerate(entradas)})
    for entrada in entradas:
        _acumular(acc, entrada)
    grupos = _ordenar_grupos([_grupo(acc, chave, m) for chave, m in acc.grupos.items()])
    lacunas = _ordenar_lacunas([_lacuna(acc, chave, m) for chave, m in acc.lacunas.items()])
    falhas = sorted(
        (_falha(acc, chave, m) for chave, m in acc.falhas.items()),
        key=lambda f: (f["status"] != STATUS_FALHA, -f["pdfs_afetados"], f["method_id"]),
    )
    pistas = _ligar_pistas(grupos, falhas)
    sem_dono = [grupo["id"] for grupo in grupos if not grupo["donos"]]
    for metodo in sorted({g["method_id"] for g in grupos if not g["donos"]}):
        acc.alertas.append(_alerta("metodo_sem_dono", method_id=metodo))
    for falha in falhas:
        falha.pop("ocorrencias")
    total = sum(resumo["divergencias"] for resumo in acc.resumos)
    agrupadas = sum(grupo["ocorrencias"] for grupo in grupos)
    em_lacunas = sum(lacuna["ocorrencias"] for lacuna in lacunas)
    return {
        "schema_version": ESQUEMA_BACKLOG,
        "onda": onda,
        "pdfs": acc.resumos,
        "grupos": grupos,
        "lacunas_de_cobertura": lacunas,
        "falhas_execucao": falhas,
        "pistas": pistas,
        "paralelismo": {
            "regra": REGRA_PARALELISMO,
            "pistas_paralelas": [pista["id"] for pista in pistas if pista["paralela"]],
            "arquivos_compartilhados": arquivos_compartilhados(pistas),
        },
        "sem_dono": sem_dono,
        "alertas": _ordenar_alertas(acc.alertas),
        "totais": {
            "pdfs": len(entradas),
            "pdfs_com_comparacao": sum(1 for e in entradas if e.comparacao is not None),
            "divergencias": total,
            "divergencias_agrupadas": agrupadas,
            "divergencias_em_lacunas": em_lacunas,
            "divergencias_retidas": total - agrupadas - em_lacunas,
            "grupos": len(grupos),
            "lacunas_de_cobertura": len(lacunas),
            "pistas": len(pistas),
            "pistas_paralelas": sum(1 for pista in pistas if pista["paralela"]),
            "falhas_execucao": len(falhas),
        },
        "limitacoes": list(LIMITACOES),
    }


# --- Markdown ---------------------------------------------------------------------------------


def _celula(valor: Any) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, list | tuple):
        return "<br>".join(f"`{item}`" for item in valor) or "—"
    return str(valor).replace("|", "\\|")


def _tabela(cabecalho: Sequence[str], linhas: Iterable[Sequence[Any]]) -> list[str]:
    saida = [
        "| " + " | ".join(cabecalho) + " |",
        "|" + "|".join("---" for _ in cabecalho) + "|",
    ]
    saida.extend("| " + " | ".join(_celula(v) for v in linha) + " |" for linha in linhas)
    return saida


def _secao_grupos(backlog: Registro) -> list[str]:
    linhas = [
        (
            g["prioridade"],
            g["id"],
            g["tipo"],
            g["familia"],
            g["class_id"],
            g["method_id"],
            g["pdfs_afetados"],
            g["ocorrencias"],
            g["perdidas_pela_uniao"],
            g["pista"],
        )
        for g in backlog["grupos"]
    ]
    cabecalho = (
        "Prioridade",
        "Grupo",
        "Tipo",
        "Família",
        "Classe",
        "Método",
        "PDFs",
        "Ocorrências",
        "Perdidas pela união",
        "Pista",
    )
    return ["## Grupos", "", *(_tabela(cabecalho, linhas) if linhas else ["Nenhum grupo."]), ""]


def _secao_pistas(backlog: Registro) -> list[str]:
    linhas = [
        (
            p["id"],
            "sim" if p["paralela"] else "não",
            p["pdfs_afetados"],
            p["grupos"],
            p["falhas_execucao"],
            p["arquivos"],
            [f"{a['arquivo']} ({a['pista']})" for a in p["acoplamentos"]],
        )
        for p in backlog["pistas"]
    ]
    cabecalho = ("Pista", "Paralela", "PDFs", "Grupos", "Falhas", "Arquivos donos", "Acoplamentos")
    corpo = _tabela(cabecalho, linhas) if linhas else ["Nenhuma pista."]
    return ["## Pistas", "", REGRA_PARALELISMO + ".", "", *corpo, ""]


def _secao_falhas(backlog: Registro) -> list[str]:
    linhas = [
        (f["id"], f["method_id"], f["status"], f["pdfs"], f["divergencias_retidas"], f["pista"])
        for f in backlog["falhas_execucao"]
    ]
    cabecalho = ("Falha", "Método", "Status", "PDFs", "Divergências retidas", "Pista")
    corpo = _tabela(cabecalho, linhas) if linhas else ["Nenhuma falha de execução."]
    return ["## Falhas de execução", "", *corpo, ""]


def _secao_lacunas(backlog: Registro) -> list[str]:
    linhas = [
        (
            item["prioridade"],
            item["id"],
            item["familia"],
            item["class_id"],
            item["pdfs_afetados"],
            item["ocorrencias"],
            item["pdfs"],
        )
        for item in backlog["lacunas_de_cobertura"]
    ]
    cabecalho = (
        "Prioridade",
        "Lacuna",
        "Família",
        "Classe",
        "PDFs",
        "Ocorrências",
        "PDFs afetados",
    )
    corpo = _tabela(cabecalho, linhas) if linhas else ["Nenhuma lacuna de cobertura."]
    nota = (
        "Faltas da união em classes que nenhum método declara suportar: sem dono e sem pista; "
        "pedem decisão de cobertura, não correção de método."
    )
    exemplos: list[str] = []
    for item in backlog["lacunas_de_cobertura"]:
        exemplos.extend(
            f"- `{item['id']}` {e['pdf_id']} p{e['pagina']} {e['camada']} "
            f"`{e['divergencia_id']}`: tile `{e['tile_evidencia']}` → {_celula(e['tile_arquivo'])}"
            for e in item["exemplos"]
        )
    return [
        "## Lacunas de cobertura",
        "",
        nota,
        "",
        *corpo,
        "",
        *exemplos,
        *([""] * bool(exemplos)),
    ]


def _secao_alertas(backlog: Registro) -> list[str]:
    linhas = [
        "- `{}`: {}".format(
            a["tipo"], ", ".join(f"{k}={v}" for k, v in sorted(a.items()) if k != "tipo")
        )
        for a in backlog["alertas"]
    ]
    return ["## Alertas", "", *(linhas or ["Nenhum alerta."]), ""]


def _secao_exemplos(backlog: Registro) -> list[str]:
    saida = ["## Exemplos", ""]
    for grupo in backlog["grupos"]:
        saida.append(f"### {grupo['prioridade']}. `{grupo['id']}`")
        saida.append("")
        for e in grupo["exemplos"]:
            saida.append(
                f"- {e['pdf_id']} p{e['pagina']} {e['camada']} `{e['divergencia_id']}` "
                f"({e['motivo']}): tile `{e['tile_evidencia']}` → {_celula(e['tile_arquivo'])}"
            )
        saida.append("")
    return saida


def renderizar_markdown(backlog: Registro) -> str:
    """Resumo legível do backlog (mesmas entradas, mesmo texto)."""
    totais = backlog["totais"]
    linhas = [
        f"# Backlog da onda {backlog['onda']}",
        "",
        *(f"> {texto}" for texto in backlog["limitacoes"]),
        "",
        "## Resumo",
        "",
        f"- PDFs na onda: {totais['pdfs']} (com comparação vigente: "
        f"{totais['pdfs_com_comparacao']})",
        f"- Divergências: {totais['divergencias']} (agrupadas: "
        f"{totais['divergencias_agrupadas']}; em lacunas de cobertura: "
        f"{totais['divergencias_em_lacunas']}; retidas por falha ou sem registro: "
        f"{totais['divergencias_retidas']})",
        f"- Grupos: {totais['grupos']} · Pistas: {totais['pistas']} (paralelas: "
        f"{totais['pistas_paralelas']}) · Falhas de execução: {totais['falhas_execucao']}",
        f"- Lacunas de cobertura: {totais['lacunas_de_cobertura']} (divergências: "
        f"{totais['divergencias_em_lacunas']})",
        "",
        *_secao_alertas(backlog),
        *_secao_grupos(backlog),
        *_secao_pistas(backlog),
        *_secao_falhas(backlog),
        *_secao_lacunas(backlog),
        *_secao_exemplos(backlog),
    ]
    return "\n".join(linhas).rstrip() + "\n"


# --- gravação e CLI ---------------------------------------------------------------------------


def gerar_backlog(rodada_dir: Path, onda: int) -> Registro:
    """Lê as comparações vigentes da onda e grava ``ondas/K/backlog.{json,md}``.

    Toda recusa acontece antes de qualquer escrita.
    """
    raiz = Path(rodada_dir).resolve()
    pdf_ids = pdfs_da_onda(carregar_rodada(raiz), onda)
    entradas = [carregar_entrada(raiz, pdf_id) for pdf_id in pdf_ids]
    backlog = agregar(onda, entradas)
    conteudo_json = json_canonico(backlog).encode("utf-8")
    conteudo_md = renderizar_markdown(backlog).encode("utf-8")
    destino = raiz / DIRETORIO_ONDAS / str(onda)
    destino.mkdir(parents=True, exist_ok=True)
    with _trava(destino / "backlog"):
        escrever_bytes_atomico(destino / ARQUIVO_JSON, conteudo_json)
        escrever_bytes_atomico(destino / ARQUIVO_MD, conteudo_md)
    relativo = PurePosixPath(DIRETORIO_ONDAS, str(onda))
    return {
        "onda": onda,
        "arquivos": [(relativo / ARQUIVO_JSON).as_posix(), (relativo / ARQUIVO_MD).as_posix()],
        "backlog": backlog,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--rodada", type=Path, required=True)
    parser.add_argument("--onda", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        resultado = gerar_backlog(args.rodada, args.onda)
    except RodadaError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    backlog = resultado["backlog"]
    for alerta in backlog["alertas"]:
        detalhe = ", ".join(f"{k}={v}" for k, v in sorted(alerta.items()) if k != "tipo")
        print(f"alerta: {alerta['tipo']}: {detalhe}", file=sys.stderr)
    resumo = {
        "onda": resultado["onda"],
        "arquivos": resultado["arquivos"],
        **{
            chave: backlog["totais"][chave]
            for chave in ("grupos", "pistas", "falhas_execucao", "lacunas_de_cobertura")
        },
        "pistas_paralelas": backlog["paralelismo"]["pistas_paralelas"],
        "sem_dono": len(backlog["sem_dono"]),
        "alertas": len(backlog["alertas"]),
    }
    print(json_canonico(resumo), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
