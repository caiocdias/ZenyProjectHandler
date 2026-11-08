"""Mede o analisador vigente contra uma ficha de referência por poste (etapa E02).

Uso::

    python -m scripts.benchmark_ficha_poste PDF --referencia REF --saida DIR \
        [--native-only] [--runtime-directory DIR] \
        [--versao-extracao projeto-promovido-v1|propostas-v1] [--simbolos-modelo]

Roda o analisador no PDF, monta a ficha predita, avalia contra a referência e grava
``ficha-predita.json`` e ``avaliacao.json`` em ``DIR``.

Fontes da ficha predita (``--versao-extracao``):

- ``projeto-promovido-v1`` (padrão): o projeto promovido (``Poste``, ``EstruturaMt/Bt``,
  ``Equipamento``, ``Cabo`` e ``detectar_vaos``); propostas pendentes não entram.
- ``propostas-v1``: as propostas da interpretação (``scripts.ficha_predita_propostas``);
  propostas pendentes entram, com o campo em ``pendentes``.

A referência precisa ser do mesmo PDF (``pdf_sha256``); do contrário o comando é
recusado antes de rodar o analisador. Os arquivos gravados não têm caminho absoluto nem o nome
do PDF. Símbolos de suporte, como estai, nunca são promovidos: o recall deles é 0 por construção.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Final
from uuid import UUID

from scripts.benchmark_network_pdf import run_variant, verify_ocr
from scripts.ficha_poste import _erro_classe, carregar_ficha, validar_ficha
from scripts.ficha_poste_avaliador import avaliar
from zeny_project_handler.adapters.analysis import TesseractCliOcr
from zeny_project_handler.adapters.analysis.tesseract_runtime import inspect_tesseract_runtime
from zeny_project_handler.application.spans import detectar_vaos
from zeny_project_handler.domain.project import Cabo, Equipamento, EstruturaBt, EstruturaMt, Poste
from zeny_project_handler.domain.values import GeometriaDocumento
from zeny_project_handler.ports.analysis import MotorOcrPort

VERSAO_EXTRACAO: Final = "projeto-promovido-v1"
VERSAO_EXTRACAO_PROPOSTAS: Final = "propostas-v1"
VERSOES_EXTRACAO: Final = (VERSAO_EXTRACAO, VERSAO_EXTRACAO_PROPOSTAS)
PERFIL_SIMBOLOS: Final = "vector-only"


def _json(valor: Any) -> Any:
    return valor if valor is None or isinstance(valor, str | int | float | bool) else str(valor)


def _bbox(geometria: GeometriaDocumento) -> list[float]:
    """Mesma conversão de ``symbol_benchmark_runner``: extremos dos pontos normalizados."""
    xs = [float(ponto.x) for ponto in geometria.pontos]
    ys = [float(ponto.y) for ponto in geometria.pontos]
    return [min(xs), min(ys), max(xs), max(ys)]


def _atributos_de_origem(variante: Mapping[str, Any]) -> dict[UUID, dict[str, Any]]:
    """Atributos da proposta que originou cada elemento promovido."""
    propostas = {proposta.id: proposta for proposta in variante["semantic"].elementos}
    origem: dict[UUID, dict[str, Any]] = {}
    for decisao in variante["decisions"]:
        if decisao is None or decisao.elemento_confirmado_id is None:
            continue
        proposta = propostas.get(decisao.proposta_id)
        if proposta is not None:
            origem[decisao.elemento_confirmado_id] = dict(proposta.atributos_sugeridos)
    return origem


def _gerador(
    variante: Mapping[str, Any], *, native_only: bool, versao_extracao: str = VERSAO_EXTRACAO
) -> dict[str, Any]:
    gerador: dict[str, Any] = {
        "versao_extracao": versao_extracao,
        "analisador_versao": _json(variante["analyzer"]["version"]),
        "analisador_assinatura": _json(variante["analyzer"]["signature"]),
        "interpretador_versao": _json(variante["interpreter_version"]),
        "registro_assinatura": _json(variante["registry_signature"]),
        "native_only": native_only,
    }
    if "symbol_configuration_signature" in variante:
        gerador["simbolos_modelo"] = {
            "perfil": PERFIL_SIMBOLOS,
            "assinatura": _json(variante["symbol_configuration_signature"]),
        }
    return gerador


def _poste(
    elemento: Poste, pagina: int, estruturas: list[str], origem: Mapping[str, Any]
) -> dict[str, Any]:
    assert elemento.geometria is not None
    coordenada = elemento.coordenada_campo
    de_simbolo = "origem_simbolo_ocorrencia_id" in origem
    return {
        "id": str(elemento.id),
        "pagina": pagina,
        "bbox": _bbox(elemento.geometria),
        "identificador": elemento.identificador_operacional,
        # Poste vindo de símbolo: codigo_observado é a classe do símbolo, não a nomenclatura.
        "poste": None if de_simbolo else elemento.codigo_observado,
        "coordenada": None
        if coordenada is None
        else {
            "leste": float(coordenada.leste),
            "norte": float(coordenada.norte),
            "zona": coordenada.zona,
        },
        "estruturas": sorted(estruturas),
        "simbolos": [],
        "pendentes": [],
        "atributos_extras": (
            {"origem": "simbolo", "classe_simbolo": elemento.codigo_observado} if de_simbolo else {}
        ),
    }


def _anexar_simbolos(
    postes: Mapping[UUID, dict[str, Any]],
    equipamentos: list[Equipamento],
    origens: Mapping[UUID, dict[str, Any]],
) -> dict[str, int]:
    contagens = {
        "equipamentos_sem_simbolo": 0,
        "simbolos_sem_area": 0,
        "simbolos_fora_do_inventario": 0,
    }
    for equipamento in equipamentos:
        poste = postes.get(equipamento.poste_id)
        classe = origens.get(equipamento.id, {}).get("simbolo_classe")
        if classe is None:
            contagens["equipamentos_sem_simbolo"] += 1
            continue
        if poste is None:
            # Chave só aparece quando ocorre, para a raiz da ficha sem ocorrência seguir enxuta.
            contagens["simbolos_de_poste_fora_da_ficha"] = (
                contagens.get("simbolos_de_poste_fora_da_ficha", 0) + 1
            )
            continue
        classe = str(classe)
        if _erro_classe("simbolo", classe) is not None:
            contagens["simbolos_fora_do_inventario"] += 1
            continue
        bbox = _bbox(equipamento.geometria) if equipamento.geometria is not None else None
        if bbox is None or bbox[0] == bbox[2] or bbox[1] == bbox[3]:
            contagens["simbolos_sem_area"] += 1
            continue
        poste["simbolos"].append({"id": str(equipamento.id), "classe": classe, "bbox": bbox})
    return contagens


def ficha_predita(
    variante: Mapping[str, Any], pdf_sha256: str, *, native_only: bool
) -> dict[str, Any]:
    """Ficha ``predicao`` do projeto promovido de uma variante de ``run_variant``."""
    projeto = variante["project"]
    origens = _atributos_de_origem(variante)
    paginas = {
        pagina.id: pagina.numero for documento in projeto.documentos for pagina in documento.paginas
    }
    estruturas: dict[UUID, list[str]] = {}
    for elemento in projeto.elementos:
        if isinstance(elemento, EstruturaMt | EstruturaBt) and elemento.codigo_observado:
            estruturas.setdefault(elemento.poste_id, []).append(elemento.codigo_observado)
    postes = {
        elemento.id: _poste(
            elemento,
            paginas[elemento.geometria.pagina_id],
            estruturas.get(elemento.id, []),
            origens.get(elemento.id, {}),
        )
        for elemento in projeto.elementos
        if isinstance(elemento, Poste) and elemento.geometria is not None
    }
    contagens = _anexar_simbolos(
        postes,
        [item for item in projeto.elementos if isinstance(item, Equipamento)],
        origens,
    )
    cabos = {item.id: item for item in projeto.elementos if isinstance(item, Cabo)}
    vaos: list[dict[str, Any]] = [
        {
            "de": str(vao.poste_origem_id),
            "para": str(vao.poste_destino_id),
            "comprimento_m": None if vao.comprimento_m is None else float(vao.comprimento_m),
            "cabo": cabos[vao.cabo_id].codigo_observado,
            "pendentes": [],
            "atributos_extras": {
                "origem_comprimento": None
                if vao.origem_comprimento is None
                else vao.origem_comprimento.value
            },
        }
        for vao in detectar_vaos(projeto)
        if vao.poste_origem_id in postes and vao.poste_destino_id in postes
    ]
    sem_geometria = sum(
        1 for item in projeto.elementos if isinstance(item, Poste) and item.geometria is None
    )
    if sem_geometria:
        contagens["postes_sem_geometria"] = sem_geometria
    return {
        "schema_version": 1,
        "tipo": "predicao",
        "pdf_sha256": pdf_sha256,
        "escopo_anotacao": {"tipo": "completo"},
        "gerador": _gerador(variante, native_only=native_only),
        "postes": list(postes.values()),
        "vaos": vaos,
        "atributos_extras": contagens,
    }


def _impressao(pdf: Path) -> tuple[int, int, str]:
    estado = pdf.stat()
    return estado.st_size, estado.st_mtime_ns, sha256(pdf.read_bytes()).hexdigest()


def _preparar_ocr(runtime_directory: Path, *, native_only: bool) -> MotorOcrPort | None:
    if native_only:
        return None
    runtime = inspect_tesseract_runtime(runtime_directory)
    if not runtime.portugues_pronto:
        raise RuntimeError(f"OCR português obrigatório: {runtime.diagnostico}")
    assert runtime.executavel is not None and runtime.diretorio_tessdata is not None
    ocr = TesseractCliOcr(
        runtime.executavel,
        language="+".join(runtime.idiomas_selecionados),
        tessdata_directory=runtime.diretorio_tessdata,
    )
    verify_ocr(ocr)
    return ocr


def _grava(caminho: Path, dados: Mapping[str, Any]) -> None:
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )


def executar(
    pdf: Path,
    referencia: Path,
    saida: Path,
    *,
    native_only: bool,
    runtime_directory: Path,
    versao_extracao: str = VERSAO_EXTRACAO,
    simbolos_modelo: bool = False,
) -> dict[str, Any]:
    """Roda o analisador, avalia contra a referência e grava ficha e avaliação em ``saida``."""
    if versao_extracao not in VERSOES_EXTRACAO:
        raise ValueError(f"versao_extracao desconhecida: {versao_extracao}")
    if simbolos_modelo and versao_extracao == VERSAO_EXTRACAO:
        raise ValueError(f"{VERSAO_EXTRACAO} não usa símbolos: use {VERSAO_EXTRACAO_PROPOSTAS}")
    pdf = pdf.resolve(strict=True)
    ficha_referencia = carregar_ficha(referencia)
    antes = _impressao(pdf)
    if ficha_referencia["pdf_sha256"] != antes[2]:
        raise ValueError("referência é de outro PDF: pdf_sha256 diferente do arquivo")
    ocr = _preparar_ocr(runtime_directory, native_only=native_only)
    saida.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="ficha-poste-", dir=saida) as temporario:
        # A flag só é repassada quando ligada: a chamada padrão segue idêntica à anterior.
        opcoes_variante = {"simbolos_modelo": True} if simbolos_modelo else {}
        variante = run_variant(pdf, Path(temporario), ocr=ocr, **opcoes_variante)
    if versao_extracao == VERSAO_EXTRACAO_PROPOSTAS:
        # Importado aqui porque o módulo das propostas importa este (sem ciclo no topo).
        from scripts.ficha_predita_propostas import ficha_predita_propostas

        predita = ficha_predita_propostas(variante, antes[2], native_only=native_only)
    else:
        predita = ficha_predita(variante, antes[2], native_only=native_only)
    erros = validar_ficha(predita)
    if erros:
        raise ValueError("ficha predita inválida: " + "; ".join(erros))
    relatorio = avaliar(ficha_referencia, predita)
    if _impressao(pdf) != antes:
        raise RuntimeError("Origem mudou durante o benchmark")
    _grava(saida / "ficha-predita.json", predita)
    _grava(saida / "avaliacao.json", relatorio)
    return relatorio


def main(argumentos: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--referencia", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    parser.add_argument("--runtime-directory", type=Path, default=Path("tmp/benchmark-runtime"))
    parser.add_argument("--native-only", action="store_true")
    parser.add_argument("--versao-extracao", choices=VERSOES_EXTRACAO, default=VERSAO_EXTRACAO)
    parser.add_argument("--simbolos-modelo", action="store_true")
    opcoes = parser.parse_args(argumentos)
    # Versão e flag só são repassadas quando diferem do padrão: a chamada padrão segue idêntica.
    extras: dict[str, Any] = (
        {}
        if opcoes.versao_extracao == VERSAO_EXTRACAO
        else {"versao_extracao": opcoes.versao_extracao}
    )
    if opcoes.simbolos_modelo:
        extras["simbolos_modelo"] = True
    executar(
        opcoes.pdf,
        opcoes.referencia,
        opcoes.saida,
        native_only=opcoes.native_only,
        runtime_directory=opcoes.runtime_directory,
        **extras,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
