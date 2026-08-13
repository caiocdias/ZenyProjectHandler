"""Execute um smoke somente leitura nos PDFs locais disponíveis em ``examples``."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.interpretation import (
    InterpretadorRegrasExplicitas,
    carregar_registro_regras_inicial,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.ports.analysis import (
    ConfiguracaoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
)
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao
from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf, ReferenciaFontePdf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLES_DIRECTORY = PROJECT_ROOT / "examples"
SMOKE_RENDER_BUDGET = OrcamentoRenderizacaoPdf(
    limite_pixels=8_000_000,
    limite_bytes=64 * 1024 * 1024,
)


@dataclass(frozen=True, slots=True)
class ResultadoSmokePdf:
    caminho: Path
    paginas: int
    evidencias: int
    propostas: int
    relacoes: int
    diagnosticos: int


def descobrir_pdfs(diretorio: Path) -> tuple[Path, ...]:
    """Descubra recursivamente os PDFs existentes, sem manifesto ou nomes predefinidos."""
    if not diretorio.is_dir():
        return ()
    return tuple(
        sorted(
            (
                caminho
                for caminho in diretorio.rglob("*")
                if caminho.is_file() and caminho.suffix.casefold() == ".pdf"
            ),
            key=lambda caminho: caminho.as_posix().casefold(),
        )
    )


def executar_smoke_pdf(caminho: Path) -> ResultadoSmokePdf:
    """Leia, renderize e interprete um PDF sem persistir resultados ou alterar a origem."""
    origem = caminho.expanduser().resolve(strict=True)
    antes = origem.stat()
    leitor = PyMuPdfReader()
    inspecao = leitor.inspecionar(origem)
    miniatura = leitor.renderizar_miniatura(
        origem,
        1,
        orcamento=SMOKE_RENDER_BUDGET,
        sha256_esperado=inspecao.documento.sha256,
    )
    if not miniatura.dados_rgb:
        raise RuntimeError("A miniatura não produziu pixels")

    projeto_id = uuid4()
    extracao_id = uuid4()
    fonte = ReferenciaFontePdf(
        documento_id=inspecao.documento.id,
        projeto_id=projeto_id,
        caminho_canonico=origem,
        sha256=inspecao.documento.sha256,
        tamanho_bytes=inspecao.tamanho_bytes,
        modificado_em_ns=inspecao.modificado_em_ns,
    )
    extracao = PyMuPdfDocumentAnalyzer().analisar(
        SolicitacaoAnaliseDocumento(
            projeto_id=projeto_id,
            documento=inspecao.documento,
            fonte=fonte,
            execucao_id=extracao_id,
            criada_em=datetime.now(UTC),
            configuracao=ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False),
        )
    )
    catalogo = carregar_catalogo_inicial()
    registro = carregar_registro_regras_inicial()
    interpretacao = InterpretadorRegrasExplicitas(registro).interpretar(
        SolicitacaoInterpretacao(
            projeto_id=projeto_id,
            execucao_id=uuid4(),
            execucao_extracao_id=extracao_id,
            catalogo=catalogo,
            evidencias=extracao.evidencias,
            registro=registro,
        )
    )

    depois = origem.stat()
    if (antes.st_size, antes.st_mtime_ns) != (depois.st_size, depois.st_mtime_ns):
        raise RuntimeError("O arquivo de origem mudou durante o smoke")
    return ResultadoSmokePdf(
        caminho=origem,
        paginas=len(inspecao.documento.paginas),
        evidencias=len(extracao.evidencias),
        propostas=len(interpretacao.elementos),
        relacoes=len(interpretacao.relacoes),
        diagnosticos=len((*extracao.diagnosticos, *interpretacao.diagnosticos)),
    )


def main(argumentos: list[str] | None = None) -> int:
    _configurar_saida_utf8()
    parser = argparse.ArgumentParser(
        description="Smoke local, dinâmico e somente leitura dos PDFs disponíveis.",
    )
    parser.add_argument(
        "diretorio",
        nargs="?",
        type=Path,
        default=DEFAULT_EXAMPLES_DIRECTORY,
        help="diretório local de PDFs (padrão: examples)",
    )
    opcoes = parser.parse_args(argumentos)
    caminhos = descobrir_pdfs(opcoes.diretorio)
    if not caminhos:
        print(f"Nenhum PDF local encontrado em {opcoes.diretorio}.", flush=True)
        return 0

    falhas = 0
    for caminho in caminhos:
        try:
            resultado = executar_smoke_pdf(caminho)
        except Exception as erro:
            falhas += 1
            print(f"FALHA {caminho.name}: {erro}", file=sys.stderr, flush=True)
            continue
        print(
            f"OK {caminho.name}: {resultado.paginas} página(s), "
            f"{resultado.evidencias} evidência(s), {resultado.propostas} proposta(s), "
            f"{resultado.relacoes} relação(ões), {resultado.diagnosticos} diagnóstico(s).",
            flush=True,
        )
    print(
        f"Smoke concluído: {len(caminhos) - falhas} aprovado(s), {falhas} falha(s).",
        flush=True,
    )
    return 1 if falhas else 0


def _configurar_saida_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
