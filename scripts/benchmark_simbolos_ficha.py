# mypy: disable-error-code="no-untyped-call"
"""Detecção de símbolos contra os símbolos das fichas de referência (E06.1).

Uso::

    python -m scripts.benchmark_simbolos_ficha --rodada RODADA --saida DIR \
        [--metodo atual ...] [--processos N]

Para cada folha de ``RODADA/rodada.json`` lê a referência em ``pdfs/ID/ficha/referencia.json``,
acha o PDF por ``raiz_corpus`` + ``caminho_relativo`` (recusando, antes de qualquer leitura, o
caminho com o componente ``avaliacao-cega``), confere o ``sha256`` contra o da referência e mede
cada método de detecção. Uma rodada cujo próprio diretório tem esse componente é recusada antes de
ler o ``rodada.json``. A guarda é lexical (componentes do caminho, sem ``resolve``): não pega nome
curto 8.3, symlink nem junction para a pasta cega; a proteção real é o protocolo da curadoria.
Grava ``simbolos-ficha.json`` e ``simbolos-ficha.md`` em ``--saida``,
sem caminho absoluto nem nome de PDF: a folha é identificada só pelo ``pdf_id`` da rodada.

O método ``atual`` é a união do runner de benchmark sem raster nem estrutural: detector legado,
estais, transformadores e pacotes declarativos. Essa união não passa por ``reconcile_symbols``, ao
contrário do runner do servidor; por isso o relatório conta as duplicatas por método e classe.

Regras (R-E06.1-2 a R-E06.1-5b do plano):

* dois critérios de casamento, ambos 1-1 e gulosos por (página, classe): ``centro`` (principal; o
  centro da predição na caixa da referência, expandida por ``TOLERANCIA_CENTRO``) e ``iou``
  (diagnóstico; ``geometry_match`` do avaliador E02);
* saem antes do casamento as predições de contexto de legenda ou informativo e as de classe que
  não aparece em nenhuma referência da rodada; dos símbolos de referência, os dos postes com
  ``simbolos`` pendente;
* das predições que sobram, só é FP a que não está fora das regiões anotadas nem perto
  (``RAIO_POSTE_PENDENTE``) de um poste com símbolos pendentes. A precisão é um limite inferior,
  pois a ficha só anota símbolo associado a poste;
* método que falha numa folha fica fora dos totais dele; ``comparacao`` traz os totais de cada
  método restritos às folhas em que todos tiveram sucesso.

Com ``--processos N`` (inteiro >= 1, padrão 1) as folhas são medidas em até ``min(N, folhas, 61)``
processos; a saída mantém a ordem do ``rodada.json`` e o JSON é igual ao serial, salvo ``tempo_s``.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Collection, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any, Final, TypedDict

import pymupdf

import scripts.symbol_benchmark_runner as runner
from scripts.curation_round import RodadaError, carregar_rodada
from scripts.simbolos_corpus import (
    COMPONENTE_CEGO,
    LIMITE_ERRO,
    FolhaError,
    Registro,
    _componentes,
    carregar_referencia,
    falha,
    falha_da_cobertura,
    localizar_pdf,
    medir_em_paralelo,
    recusar_rodada_cega,
    sanear,
)
from scripts.simbolos_ficha_metricas import (
    CONTEXTOS_NAO_DESENHO,
    CRITERIOS,
    RAIO_POSTE_PENDENTE,
    TOLERANCIA_CENTRO,
    _agregar_comparacao,
    _agregar_por_familia,
    _agregar_total,
    _simbolos_validos,
    avaliar_predicoes,
    casar,
    classes_da_ficha,
    normalizar_situacao,
    situacoes_da_variante,
)
from scripts.simbolos_ficha_relatorio import _markdown
from zeny_project_handler.adapters.analysis import (
    declarative_symbols,
    legacy_symbols,
    model_symbols,
    pymupdf_guys,
    pymupdf_transformers,
)
from zeny_project_handler.adapters.analysis.drawing_model.family import reconhecer_familia
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import carregar_tabela_glifos
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    LIMITE_CONSULTAS_PAGINA,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import impressao_estrutural

ESQUEMA: Final = "simbolos-ficha-v1"
MAXIMO_PROCESSOS: Final = 61
# Teto de consultas por página do método `modelo`; lido na chamada, para o teste poder baixá-lo.
LIMITE_MODELO: Final = LIMITE_CONSULTAS_PAGINA

_FolhaError = FolhaError

# Nomes que moraram aqui e que os testes e as outras tarefas ainda leem por este módulo.
__all__ = [
    "COMPONENTE_CEGO",
    "CONTEXTOS_NAO_DESENHO",
    "LIMITE_ERRO",
    "LIMITE_MODELO",
    "RAIO_POSTE_PENDENTE",
    "TOLERANCIA_CENTRO",
    "FolhaError",
    "_FolhaError",
    "_componentes",
    "avaliar_predicoes",
    "casar",
    "classes_da_ficha",
    "localizar_pdf",
    "sanear",
]


class Predicao(TypedDict):
    pagina: int
    classe: str
    bbox: list[float]
    metodo: str
    contexto: str
    variante: str | None
    situacoes_preditas: frozenset[str]


class ResultadoMetodo(TypedDict):
    predicoes: list[Predicao]
    assinatura: dict[str, str]
    falha: str | None


# --- métodos ----------------------------------------------------------------------------


def _falha_do_manifesto(manifesto: Mapping[str, Any]) -> str | None:
    falhas = manifesto.get("failures") or []
    if falhas:
        return str(falhas[0].get("reason") or "falha sem motivo")
    if manifesto.get("status") == "failed":
        return "status failed"
    return None


def _variante_e_situacoes(item: Mapping[str, Any]) -> tuple[str | None, frozenset[str]]:
    """Variante dos pacotes (``provenance.variant_id``) e suas situações; senão a do legado."""
    variante = (item.get("provenance") or {}).get("variant_id")
    if variante is not None:
        return str(variante), situacoes_da_variante(str(variante)) or frozenset()
    situacao = normalizar_situacao(item.get("situation"))
    return None, frozenset() if situacao is None else frozenset({situacao})


def _predicao_do_runner(item: Mapping[str, Any]) -> Predicao:
    variante, situacoes = _variante_e_situacoes(item)
    return {
        "pagina": int(item["page"]),
        "classe": str(item["class_id"]),
        "bbox": [float(valor) for valor in item["bbox"]],
        "metodo": str(item["method_id"]),
        "contexto": str(item["context"]),
        "variante": variante,
        "situacoes_preditas": situacoes,
    }


def _predicoes_atual(pdf: Path, pdf_id: str) -> ResultadoMetodo:
    """União do runner sem raster nem estrutural (R-E06.1-1)."""
    manifesto, previstas, execucoes = runner.infer_pdf(
        pdf, pdf_id, include_transformers=True, include_guys=True, include_packages=True
    )
    return {
        "predicoes": [_predicao_do_runner(item) for item in previstas],
        "assinatura": {
            str(item["method_id"]): str(item["signature"])
            for item in execucoes
            if item.get("signature")
        },
        "falha": _falha_do_manifesto(manifesto),
    }


def _componente(perfil: Any, **extras: Any) -> Registro:
    return {
        "metodo_id": perfil.metodo_id,
        "versao": perfil.versao,
        "assinatura": perfil.assinatura(),
        "parametros": {chave: None if v is None else str(v) for chave, v in perfil.parametros},
        **extras,
    }


def _assinatura_atual() -> Registro:
    pacotes = declarative_symbols.carregar_pacotes()
    hash_pacotes = runner.package_method_metadata(pacotes)["package_sha256"]
    return {
        "metodo_id": "atual",
        "versao": "uniao-runner-v1",
        "composicao": "legado + estais + transformadores + pacotes; sem raster nem estrutural",
        "reconcile_symbols": False,
        "componentes": [
            _componente(legacy_symbols.perfil_simbolos_legados()),
            _componente(pymupdf_guys.perfil_estais()),
            _componente(pymupdf_transformers.perfil_transformadores()),
            _componente(declarative_symbols.perfil_pacotes(pacotes), package_sha256=hash_pacotes),
        ],
    }


def _predicao_de_pacote(item: Any, pdf_id: str, metodo: str | None = None) -> Predicao:
    """Mesma conversão do ramo `include_packages` do runner: `bbox` dos pontos normalizados."""
    predicao = _predicao_do_runner(runner._package_prediction(item, pdf_id))
    if metodo is not None:
        predicao["metodo"] = metodo
    return predicao


def _predicoes_de_paginas(
    pdf: Path,
    pdf_id: str,
    observar: Callable[[Any, int, str], Any],
    metodo: str | None,
) -> ResultadoMetodo:
    """Chama `observar(pagina, numero, sha)` em cada página; a primeira falha vira a da folha."""
    sha = sha256(pdf.read_bytes()).hexdigest()
    predicoes: list[Predicao] = []
    assinatura = ""
    with pymupdf.open(pdf) as documento:
        for indice in range(len(documento)):
            resultado = observar(documento[indice], indice + 1, sha)
            assinatura = resultado.perfil.assinatura()
            for cobertura in resultado.coberturas:
                motivo = falha_da_cobertura(cobertura)
                if motivo is not None:
                    return {
                        "predicoes": [],
                        "assinatura": {},
                        "falha": f"{motivo} (página {indice + 1})",
                    }
            predicoes.extend(
                _predicao_de_pacote(item, pdf_id, metodo) for item in resultado.observacoes
            )
    return {"predicoes": predicoes, "assinatura": {metodo or "pacotes": assinatura}, "falha": None}


def _predicoes_pacotes(pdf: Path, pdf_id: str) -> ResultadoMetodo:
    """Motor declarativo isolado: pacotes calculados uma vez por folha."""
    pacotes = declarative_symbols.carregar_pacotes()

    def observar(pagina: Any, numero: int, sha: str) -> Any:
        return declarative_symbols.observar_pacotes(
            pagina,
            documento_id=pdf_id,
            documento_sha256=sha,
            pagina_numero=numero,
            pacotes=pacotes,
        )

    return _predicoes_de_paginas(pdf, pdf_id, observar, None)


def _predicoes_modelo(pdf: Path, pdf_id: str) -> ResultadoMetodo:
    """Método sobre o modelo de desenho; perfil, pacotes e tabela calculados uma vez por folha."""
    pacotes = declarative_symbols.carregar_pacotes()
    tabela = carregar_tabela_glifos()
    limite = LIMITE_MODELO
    perfil = model_symbols.perfil_pacotes_modelo(pacotes, tabela, limite=limite)

    def observar(pagina: Any, numero: int, sha: str) -> Any:
        return model_symbols.observar_pacotes_modelo(
            pagina,
            documento_id=pdf_id,
            documento_sha256=sha,
            pagina_numero=numero,
            pacotes=pacotes,
            tabela=tabela,
            perfil=perfil,
            limite=limite,
        )

    return _predicoes_de_paginas(pdf, pdf_id, observar, perfil.metodo_id)


def _assinatura_pacotes() -> Registro:
    pacotes = declarative_symbols.carregar_pacotes()
    hash_pacotes = runner.package_method_metadata(pacotes)["package_sha256"]
    return _componente(declarative_symbols.perfil_pacotes(pacotes), package_sha256=hash_pacotes)


def _assinatura_modelo() -> Registro:
    pacotes = declarative_symbols.carregar_pacotes()
    perfil = model_symbols.perfil_pacotes_modelo(
        pacotes, carregar_tabela_glifos(), limite=LIMITE_MODELO
    )
    return _componente(perfil)


METODOS: Final[dict[str, Callable[[Path, str], ResultadoMetodo]]] = {
    "atual": _predicoes_atual,
    "pacotes": _predicoes_pacotes,
    "modelo": _predicoes_modelo,
}
ASSINATURAS: Final[dict[str, Callable[[], Registro]]] = {
    "atual": _assinatura_atual,
    "pacotes": _assinatura_pacotes,
    "modelo": _assinatura_modelo,
}


def _medir_metodo(
    nome: str,
    pdf: Path,
    pdf_id: str,
    referencia: Mapping[str, Any],
    classes: Collection[str],
    ocultar: Sequence[str],
) -> Registro:
    inicio = perf_counter()
    try:
        resultado = METODOS[nome](pdf, pdf_id)
    except Exception as erro:
        return falha(sanear(f"{type(erro).__name__}: {erro}", ocultar))
    tempo = perf_counter() - inicio
    if resultado["falha"]:
        return falha(sanear(resultado["falha"], ocultar))
    bloco = avaliar_predicoes(referencia, resultado["predicoes"], classes)
    return {"situacao": "ok", "tempo_s": tempo, "assinatura": resultado["assinatura"], **bloco}


def _ocultar_pdf(pdf: Path) -> list[str]:
    return [str(pdf), pdf.as_posix(), pdf.name, str(pdf.parent), pdf.parent.as_posix()]


def medir_pdf(
    pdf: Path,
    referencia: Mapping[str, Any],
    pdf_id: str,
    metodos: Sequence[str],
    *,
    classes_avaliadas: Collection[str] | None = None,
) -> Registro:
    """Uma folha: família (fora do ``tempo_s``) e, por método, os dois critérios.

    ``classes_avaliadas`` são as da rodada inteira; sem elas valem as desta referência.
    """
    classes = classes_da_ficha(referencia) if classes_avaliadas is None else classes_avaliadas
    with pymupdf.open(pdf) as documento:
        familia = reconhecer_familia(impressao_estrutural(documento)).familia
    ocultar = _ocultar_pdf(pdf)
    return {
        "situacao": "ok",
        "familia": familia,
        "simbolos_referencia": len(_simbolos_validos(referencia)),
        "metodos": {
            nome: _medir_metodo(nome, pdf, pdf_id, referencia, classes, ocultar) for nome in metodos
        },
    }


@dataclass(frozen=True, slots=True)
class _Tarefa:
    rodada: Path
    raiz_corpus: str
    entrada: Registro
    referencia: Registro
    metodos: tuple[str, ...]
    classes: frozenset[str]


def _medir_folha(tarefa: _Tarefa) -> Registro:
    caminho_relativo = str(tarefa.entrada["caminho_relativo"])
    ocultar = [str(tarefa.rodada), tarefa.rodada.as_posix(), caminho_relativo]
    try:
        pdf = localizar_pdf(tarefa.rodada, tarefa.raiz_corpus, caminho_relativo)
        if not pdf.is_file():
            raise FolhaError("PDF não encontrado no corpus da rodada")
        if sha256(pdf.read_bytes()).hexdigest() != tarefa.referencia["pdf_sha256"]:
            raise FolhaError("sha256 do PDF difere do pdf_sha256 da referência")
        return medir_pdf(
            pdf,
            tarefa.referencia,
            str(tarefa.entrada["pdf_id"]),
            tarefa.metodos,
            classes_avaliadas=tarefa.classes,
        )
    except FolhaError as erro:
        return falha(str(erro))
    except Exception as erro:
        return falha(sanear(f"{type(erro).__name__}: {erro}", ocultar))


def _medir_todas(tarefas: Sequence[_Tarefa], efetivos: int) -> list[Registro]:
    return medir_em_paralelo(_medir_folha, tarefas, efetivos, ProcessPoolExecutor)


def _opcoes(metodos: Sequence[str], classes: Collection[str]) -> Registro:
    return {
        "metodos": list(metodos),
        "metodos_assinatura": {nome: ASSINATURAS[nome]() for nome in metodos},
        "criterios": list(CRITERIOS),
        "tolerancia_centro": TOLERANCIA_CENTRO,
        "raio_poste_pendente": RAIO_POSTE_PENDENTE,
        "classes_avaliadas": sorted(classes),
        "pymupdf": str(pymupdf.VersionBind),
    }


def medir_simbolos(
    rodada: Path,
    saida: Path,
    *,
    metodos: Sequence[str] = ("atual",),
    processos: int = 1,
) -> Registro:
    """Mede os métodos nas folhas da rodada e grava ``simbolos-ficha.json`` e ``.md``."""
    nomes = tuple(dict.fromkeys(metodos))
    desconhecidos = [nome for nome in nomes if nome not in METODOS or nome not in ASSINATURAS]
    if desconhecidos or not nomes:
        raise ValueError(f"método desconhecido ou ausente: {desconhecidos or 'nenhum'}")
    if processos < 1:
        raise ValueError("processos precisa ser >= 1")
    # Antes de ler o rodada.json ou qualquer referência: rodada dentro da pasta cega não se abre.
    recusar_rodada_cega(rodada)
    manifesto = carregar_rodada(rodada)
    raiz_corpus = str(manifesto["raiz_corpus"])
    por_pdf: dict[str, Registro] = {}
    com_ficha: list[tuple[Registro, Registro]] = []
    for entrada in manifesto["pdfs"]:
        pdf_id = str(entrada["pdf_id"])
        carregada = carregar_referencia(rodada, pdf_id)
        por_pdf[pdf_id] = carregada
        if carregada["situacao"] == "ok":
            com_ficha.append((entrada, carregada["ficha"]))
    classes = frozenset().union(*(classes_da_ficha(ficha) for _, ficha in com_ficha))
    tarefas = [
        _Tarefa(rodada, raiz_corpus, entrada, ficha, nomes, classes) for entrada, ficha in com_ficha
    ]
    efetivos = min(processos, len(tarefas), MAXIMO_PROCESSOS)
    medidas = _medir_todas(tarefas, efetivos)
    for tarefa, resultado in zip(tarefas, medidas, strict=True):
        por_pdf[str(tarefa.entrada["pdf_id"])] = resultado
    relatorio: Registro = {
        "schema_version": ESQUEMA,
        "opcoes": _opcoes(nomes, classes),
        "por_pdf": por_pdf,
        "total": _agregar_total(por_pdf, nomes),
        "comparacao": _agregar_comparacao(por_pdf, nomes),
        "por_familia": _agregar_por_familia(por_pdf, nomes),
    }
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "simbolos-ficha.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    (saida / "simbolos-ficha.md").write_text(
        _markdown(relatorio, processos, efetivos), encoding="utf-8"
    )
    return relatorio


def _inteiro_positivo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"não é inteiro: {texto!r}") from None
    if valor < 1:
        raise argparse.ArgumentTypeError("precisa ser >= 1")
    return valor


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rodada", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--metodo", action="append", choices=sorted(METODOS), default=None)
    parser.add_argument("--processos", type=_inteiro_positivo, default=1)
    opcoes = parser.parse_args(argumentos)
    try:
        medir_simbolos(
            opcoes.rodada,
            opcoes.saida,
            metodos=tuple(opcoes.metodo or ("atual",)),
            processos=opcoes.processos,
        )
    except RodadaError as erro:
        parser.exit(1, f"{erro}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
