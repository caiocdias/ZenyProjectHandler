"""Relatório em Markdown do benchmark de símbolos."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from scripts.simbolos_ficha_metricas import CRITERIOS


def _pct(valor: float | None) -> str:
    return "n/d" if valor is None else f"{valor:.1%}"


def _linhas_criterio(criterio: str, bloco: Mapping[str, Any]) -> list[str]:
    linhas = [
        f"**{criterio}**",
        "",
        "| classe | tp | fp | fn | precisão | recall |",
        "|---|---|---|---|---|---|",
    ]
    itens = [*bloco["por_classe"].items(), ("(geral)", bloco["geral"])]
    linhas += [
        f"| {classe} | {i['tp']} | {i['fp']} | {i['fn']} | {_pct(i['precisao'])} "
        f"| {_pct(i['recall'])} |"
        for classe, i in itens
    ]
    return [
        *linhas,
        "",
        f"Fora do escopo: {bloco['fora_do_escopo'] or 'nenhuma'}; "
        f"fora das regiões: {bloco['fora_das_regioes']}; "
        f"perto de poste pendente: {bloco['perto_de_poste_pendente']}.",
        "",
    ]


def _linhas_metodo(titulo: str, bloco: Mapping[str, Any]) -> list[str]:
    linhas = [
        f"#### {titulo}",
        "",
        f"Folhas medidas: {bloco['folhas_medidas']}; com falha: {bloco['folhas_com_falha']}; "
        f"predições: {bloco['predicoes']}; contexto não desenho: {bloco['contexto_nao_desenho']}; "
        f"duplicatas: {bloco['duplicatas'] or 'nenhuma'}.",
        "",
    ]
    for criterio in CRITERIOS:
        linhas += _linhas_criterio(criterio, bloco[criterio])
    return linhas


def _linhas_bloco(titulo: str, por_metodo: Mapping[str, Mapping[str, Any]]) -> list[str]:
    linhas = [f"### {titulo}", ""]
    for nome, bloco in por_metodo.items():
        linhas += _linhas_metodo(nome, bloco)
    return linhas


def _markdown(relatorio: Mapping[str, Any], processos: int, efetivos: int) -> str:
    opcoes = relatorio["opcoes"]
    linhas = [
        "# Símbolos contra as fichas de referência",
        "",
        f"Esquema {relatorio['schema_version']}. Métodos: {', '.join(opcoes['metodos'])}. "
        f"PyMuPDF {opcoes['pymupdf']}.",
        f"Processos: {processos} (efetivos: {efetivos}).",
        f"Classes avaliadas: {', '.join(opcoes['classes_avaliadas']) or 'nenhuma'}.",
        "",
        "- `atual` é a união legado, estais, transformadores e pacotes de `infer_pdf`, sem raster "
        "nem estrutural. Ela não passa por `reconcile_symbols`, ao contrário do runner do "
        "servidor; as duplicatas por método e classe estão contadas.",
        "- Casamento 1-1 guloso por página e classe. `centro` (principal): centro da predição na "
        f"caixa da referência, com tolerância {opcoes['tolerancia_centro']}. `iou` (diagnóstico): "
        "`geometry_match` do avaliador E02.",
        "- A precisão é um limite inferior: a ficha só anota símbolo associado a poste. Não são FP "
        "a predição de legenda ou informativa, de classe fora do escopo, fora das regiões "
        f"anotadas ou perto (raio {opcoes['raio_poste_pendente']}) de poste com símbolos "
        "pendentes.",
        "- `tempo_s` (só em `por_pdf` do JSON) inclui o `tracemalloc` de `infer_pdf`.",
        "",
        "## Total",
        "",
        *_linhas_bloco("Todas as folhas medidas", relatorio["total"]),
        *_linhas_bloco(
            f"Comparação, mesmas folhas ({len(relatorio['comparacao']['folhas'])})",
            relatorio["comparacao"]["metodos"],
        ),
        "## Por família",
        "",
    ]
    for familia, por_metodo in relatorio["por_familia"].items():
        linhas += _linhas_bloco(f"Família {familia}", por_metodo)
    linhas += ["## Folhas", ""]
    for pdf_id, folha in relatorio["por_pdf"].items():
        if folha["situacao"] != "ok":
            linhas.append(f"- {pdf_id}: {folha['situacao']} {folha.get('erro', '')}".rstrip())
            continue
        falhas = [n for n, b in folha["metodos"].items() if b["situacao"] != "ok"]
        resumo = ", ".join(f"{n}: {folha['metodos'][n]['erro']}" for n in falhas)
        linhas.append(
            f"- {pdf_id}: família {folha['familia']}" + (f"; falha: {resumo}" if falhas else "")
        )
    return "\n".join(linhas) + "\n"
