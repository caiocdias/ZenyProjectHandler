# mypy: disable-error-code="no-untyped-call"
"""Ataques ao teto de resoluções distintas por página (`LIMITE_RESOLUCOES_PAGINA`) da leitura
de texto por contorno de glifo: limite exato, soma entre trechos, parada no primeiro trecho que
passa, isolamento entre páginas, memória diante de repetições e o diagnóstico no analisador."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf
import pytest
from tests.fixtures.glyphs.fonte_livre import (
    LinhaTexto,
    caminhos_do_pdf,
    pdf_texto_contorno,
    tabela_do_alfabeto,
)

from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer
from zeny_project_handler.adapters.analysis.drawing_model import glyph_text
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import TabelaGlifos
from zeny_project_handler.adapters.analysis.drawing_model.glyph_text import (
    LeituraGlifos,
    ler_texto_glifos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Estilo,
    ItemCaminho,
)
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import extrair_modelo_desenho
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.enums import TipoEvidencia
from zeny_project_handler.ports.analysis import (
    ConfiguracaoAnaliseDocumento,
    ResultadoAnaliseDocumento,
    SolicitacaoAnaliseDocumento,
)
from zeny_project_handler.ports.pdf import ReferenciaFontePdf

_LIMITADA = LeituraGlifos((), 0, 0, limitada=True)
_VARREDURAS = ("resolver_glifo", "forma_sem_escala_confirma")
# três trechos; o último tem caracteres que os anteriores não têm (passa do teto só nele)
_TRES_LINHAS = (
    LinhaTexto("P10N1", (40.0, 60.0), 5.0),
    LinhaTexto("E=612", (40.0, 90.0), 5.0),
    LinhaTexto("U4 S7", (40.0, 120.0), 5.0),
)


@pytest.fixture(scope="module")
def tabela(tmp_path_factory: pytest.TempPathFactory) -> TabelaGlifos:
    return tabela_do_alfabeto(tmp_path_factory.mktemp("alfabeto-orcamento-ataque"))


def _contar(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    """Conta as varreduras da tabela (as funções que a leitura chama pelo módulo)."""
    chamadas: Counter[str] = Counter()

    def contando(nome: str, funcao: Callable[..., Any]) -> Callable[..., Any]:
        def chamar(*args: Any) -> Any:
            chamadas[nome] += 1
            return funcao(*args)

        return chamar

    for nome in _VARREDURAS:
        monkeypatch.setattr(glyph_text, nome, contando(nome, getattr(glyph_text, nome)))
    return chamadas


def _distintas(caminhos: Sequence[Caminho], tabela: TabelaGlifos) -> int:
    with pytest.MonkeyPatch.context() as contexto:
        chamadas = _contar(contexto)
        ler_texto_glifos(caminhos, tabela)
    return sum(chamadas.values())


def _caminhos(tmp_path: Path, nome: str, linhas: Sequence[LinhaTexto]) -> tuple[Any, ...]:
    return caminhos_do_pdf(pdf_texto_contorno(tmp_path / f"{nome}.pdf", list(linhas)))


def _textos(leitura: LeituraGlifos) -> list[str]:
    return [t.texto for t in leitura.textos]


# --- limite exato e soma entre trechos ------------------------------------------------------


def test_pagina_exatamente_no_teto_com_varios_trechos_le_todos_os_textos(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminhos = _caminhos(tmp_path, "tres", _TRES_LINHAS)
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", _distintas(caminhos, tabela))

    leitura = ler_texto_glifos(caminhos, tabela)

    assert _textos(leitura) == ["P10N1", "E=612", "U4 S7"]
    assert (leitura.limitada, leitura.desconhecidos, leitura.ambiguos) == (False, 0, 0)


def test_teto_soma_os_trechos_da_pagina_e_estourar_no_ultimo_descarta_os_anteriores(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    caminhos = _caminhos(tmp_path, "tres", _TRES_LINHAS)
    total = _distintas(caminhos, tabela)
    sozinhas = [
        _distintas(_caminhos(tmp_path, f"l{i}", [linha]), tabela)
        for i, linha in enumerate(_TRES_LINHAS)
    ]
    # cada trecho cabe sozinho no teto: só a soma da página passa dele
    assert max(sozinhas) <= total - 1
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", total - 1)

    # nada dos dois primeiros trechos (já lidos quando o terceiro passa) sai como texto parcial
    assert ler_texto_glifos(caminhos, tabela) == _LIMITADA


def _pagina_de_formas_distintas(tamanhos: Sequence[int], semente: int = 7) -> list[Caminho]:
    """Trechos com os tamanhos dados; cada glifo é uma forma diferente (nada se repete na
    memória) e nenhuma é reconhecida na tabela do alfabeto: uma varredura por glifo."""
    sorteio = random.Random(semente)
    estilo = Estilo("", None, (0.0, 0.0, 0.0), 0.0, "")
    caminhos: list[Caminho] = []
    for trecho, tamanho in enumerate(tamanhos):
        for posicao in range(tamanho):
            x = 1.0 * posicao + 15.0 * (trecho % 40)
            y = 3.0 * (trecho // 40)
            largura = 0.5 + 0.3 * sorteio.random()
            meio = (x + largura * sorteio.random(), y + 0.2 + 0.6 * sorteio.random())
            pontos = [(x, y), (x + largura, y), meio, (x + largura, y + 1.0), (x, y + 1.0)]
            itens = tuple(
                ItemCaminho("l", (a, b))
                for a, b in zip(pontos, pontos[1:] + pontos[:1], strict=True)
            )
            caminhos.append(Caminho((itens,), estilo, "preenchimento", len(caminhos)))
    return caminhos


def test_teto_padrao_le_a_pagina_com_exatamente_o_teto_de_varreduras(
    tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    limite = glyph_text.LIMITE_RESOLUCOES_PAGINA
    caminhos = _pagina_de_formas_distintas([8] * (limite // 8 - 1) + [8 + limite % 8])
    chamadas = _contar(monkeypatch)

    leitura = ler_texto_glifos(caminhos, tabela)

    assert sum(chamadas.values()) == limite  # a página faz exatamente o teto de varreduras
    assert not leitura.limitada
    assert leitura.desconhecidos == limite


def test_teto_padrao_limita_a_pagina_com_uma_varredura_a_mais(
    tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    limite = glyph_text.LIMITE_RESOLUCOES_PAGINA
    # mesmos trechos de 8 e, no fim, um de 7 e um de 2: a página soma o teto + 1
    caminhos = _pagina_de_formas_distintas([8] * (limite // 8 - 1) + [7 + limite % 8, 2])
    chamadas = _contar(monkeypatch)

    leitura = ler_texto_glifos(caminhos, tabela)

    assert sum(chamadas.values()) == limite + 1
    assert leitura == _LIMITADA


def test_leitura_para_no_primeiro_trecho_que_passa_do_teto(
    tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    limite = 100
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", limite)
    chamadas = _contar(monkeypatch)
    marcos: list[int] = []
    coerente = glyph_text._com_escala_coerente

    def marcando(*args: Any) -> Any:
        resultado = coerente(*args)
        marcos.append(sum(chamadas.values()))  # varreduras somadas ao fim de cada trecho
        return resultado

    monkeypatch.setattr(glyph_text, "_com_escala_coerente", marcando)

    leitura = ler_texto_glifos(_pagina_de_formas_distintas([8] * 250, semente=11), tabela)

    assert leitura == _LIMITADA
    assert all(marco <= limite for marco in marcos[:-1])
    assert marcos[-1] > limite
    # nenhuma varredura depois do trecho que passou: a página não é varrida até o fim
    assert sum(chamadas.values()) == marcos[-1]


def test_teto_e_de_cada_pagina_e_nao_se_acumula_entre_leituras(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pagina_a = _caminhos(tmp_path, "a", [LinhaTexto("P10N1 E=612", (40.0, 60.0), 5.0)])
    pagina_b = _caminhos(tmp_path, "b", [LinhaTexto("T3U4S7", (40.0, 60.0), 5.0)])
    limite = max(_distintas(pagina_a, tabela), _distintas(pagina_b, tabela))
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", limite)

    leituras = [ler_texto_glifos(p, tabela) for p in (pagina_a, pagina_b, pagina_a, pagina_b)]

    assert [_textos(leitura) for leitura in leituras] == [
        ["P10N1 E=612"],
        ["T3U4S7"],
        ["P10N1 E=612"],
        ["T3U4S7"],
    ]
    assert not any(leitura.limitada for leitura in leituras)


# --- memória diante de repetições -----------------------------------------------------------


def test_repeticoes_exatas_em_posicoes_quebradas_nao_consomem_o_teto(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    texto = "P10N1 E=612"
    uma = _distintas(_caminhos(tmp_path, "uma", [LinhaTexto(texto, (40.0, 60.0), 5.0)]), tabela)
    linhas = [
        LinhaTexto(texto, (40.0 + 0.1234567 * i + 61.3 * (i % 3), 20.0 + 9.0123457 * i), 5.0)
        for i in range(30)
    ]
    copias = _caminhos(tmp_path, "copias", linhas)
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", 2 * uma)

    leitura = ler_texto_glifos(copias, tabela)

    assert not leitura.limitada
    assert _textos(leitura) == [texto] * 30


def _copias_com_ruido(
    base: Sequence[Caminho], quantidade: int, amplitude: float, semente: int = 3
) -> list[Caminho]:
    """`quantidade` cópias do texto `base`, uma por linha, com cada coordenada deslocada por um
    ruído uniforme de até `amplitude` pontos."""
    sorteio = random.Random(semente)
    caminhos: list[Caminho] = []
    for copia in range(quantidade):
        for caminho in base:
            subcaminhos = tuple(
                tuple(
                    ItemCaminho(
                        item.tipo,
                        tuple(
                            (
                                x + sorteio.uniform(-amplitude, amplitude),
                                y + 9.0 * copia + sorteio.uniform(-amplitude, amplitude),
                            )
                            for x, y in item.pontos
                        ),
                    )
                    for item in subcaminho
                )
                for subcaminho in caminho.subcaminhos
            )
            caminhos.append(Caminho(subcaminhos, caminho.estilo, caminho.tipo, len(caminhos)))
    return caminhos


def test_repeticoes_com_ruido_invisivel_de_coordenada_nao_consomem_o_teto(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 20 cópias do mesmo texto; 0,0001 pt de ruído (1/50 000 do corpo de 5 pt) não muda nada
    # na leitura: todas são lidas iguais sem o teto apertado
    base = _caminhos(tmp_path, "base", [LinhaTexto("P10N1", (40.0, 20.0), 5.0)])
    exatas = _distintas(_copias_com_ruido(base, 20, 0.0), tabela)
    com_ruido = _copias_com_ruido(base, 20, 1e-4)
    assert _textos(ler_texto_glifos(com_ruido, tabela)) == ["P10N1"] * 20
    varreduras_com_ruido = _distintas(com_ruido, tabela)
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", 2 * exatas)

    leitura = ler_texto_glifos(com_ruido, tabela)

    # formas iguais a menos de ruído invisível são as mesmas para a memória: a página que cabe
    # no teto sem o ruído continua cabendo com ele
    assert not leitura.limitada, (
        f"limitada: {varreduras_com_ruido} varreduras com ruído de 1e-4 pt, {exatas} sem ruído"
    )
    assert _textos(leitura) == ["P10N1"] * 20


# --- analisador e modelo de desenho ---------------------------------------------------------


_SEM_OCR = ConfiguracaoAnaliseDocumento(habilitar_ocr_condicional=False)


def _analisar(pdf: Path, tabela: TabelaGlifos) -> tuple[ResultadoAnaliseDocumento, dict[Any, int]]:
    """Resultado do analisador e o número de cada página pelo id."""
    inspecao = PyMuPdfReader().inspecionar(pdf)
    numeros = {pagina.id: pagina.numero for pagina in inspecao.documento.paginas}
    projeto = uuid4()
    solicitacao = SolicitacaoAnaliseDocumento(
        projeto_id=projeto,
        documento=inspecao.documento,
        fonte=ReferenciaFontePdf(
            documento_id=inspecao.documento.id,
            projeto_id=projeto,
            caminho_canonico=pdf,
            sha256=inspecao.documento.sha256,
            tamanho_bytes=inspecao.tamanho_bytes,
            modificado_em_ns=inspecao.modificado_em_ns,
        ),
        execucao_id=uuid4(),
        criada_em=datetime(2026, 11, 4, 9, tzinfo=UTC),
        configuracao=_SEM_OCR,
    )
    return PyMuPdfDocumentAnalyzer(tabela_glifos=tabela).analisar(solicitacao), numeros


def _duas_paginas(tmp_path: Path, tabela: TabelaGlifos) -> tuple[Path, int]:
    """PDF com a página 1 densa (três trechos) e a página 2 curta ("P7"); devolve o PDF e um
    teto em que só a curta cabe."""
    densa = pdf_texto_contorno(tmp_path / "densa.pdf", list(_TRES_LINHAS))
    curta = pdf_texto_contorno(tmp_path / "curta.pdf", [LinhaTexto("P7", (40.0, 60.0), 5.0)])
    destino = tmp_path / "duas.pdf"
    with pymupdf.open() as documento:
        for origem in (densa, curta):
            with pymupdf.open(origem) as fonte:
                documento.insert_pdf(fonte)
        documento.save(destino)
    teto = _distintas(caminhos_do_pdf(curta), tabela)
    assert teto < _distintas(caminhos_do_pdf(densa), tabela)
    return destino, teto


def test_pagina_limitada_pelo_teto_sai_sem_texto_de_glifo_e_com_um_diagnostico_so(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf, teto = _duas_paginas(tmp_path, tabela)
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", teto)

    resultado, numeros = _analisar(pdf, tabela)

    glifos = [
        e
        for e in resultado.evidencias
        if e.tipo is TipoEvidencia.TEXTO
        and dict(e.atributos_extraidos).get("origem_texto") == "contorno_glifo"
    ]
    # a página curta (2) é lida; a densa (1) não dá texto nenhum, nem parcial
    assert [(numeros[e.pagina_id], e.conteudo_bruto) for e in glifos] == [(2, "P7")]
    limitados = [d for d in resultado.diagnosticos if d.codigo == "analise.glifos_limitados"]
    assert [d.pagina_numero for d in limitados] == [1]
    # a página limitada não conta glifos desconhecidos/ambíguos que não leu
    assert all(
        d.pagina_numero != 1
        for d in resultado.diagnosticos
        if d.codigo == "analise.glifos_desconhecidos"
    )


def test_modelo_de_desenho_marca_so_a_pagina_limitada_pelo_teto(
    tmp_path: Path, tabela: TabelaGlifos, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf, teto = _duas_paginas(tmp_path, tabela)
    monkeypatch.setattr(glyph_text, "LIMITE_RESOLUCOES_PAGINA", teto)

    primeira, segunda = extrair_modelo_desenho(pdf, tabela).paginas

    assert [t.texto for t in primeira.textos if t.origem == "glifo"] == []
    assert primeira.diagnosticos.count("modelo.glifos_limitados") == 1
    assert "modelo.glifos_desconhecidos" not in primeira.diagnosticos
    assert [t.texto for t in segunda.textos if t.origem == "glifo"] == ["P7"]
    assert "modelo.glifos_limitados" not in segunda.diagnosticos
