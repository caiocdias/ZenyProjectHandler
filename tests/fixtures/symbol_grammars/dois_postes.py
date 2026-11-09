"""Cena autoral de dois postes próximos com símbolos entre eles (E07.2.2.1, Task 5).

Nenhuma coordenada vem de folha real. Os postes ficam a 0,04 um do outro, na mesma altura, e cada
símbolo é uma caixa de 0,008 de lado cuja posição é escolhida pela distância que ela guarda dos
dois postes (o raio de suporte é 0,020 da caixa ao ponto do poste e a margem de empate é 0,004):

- `CAIXA_PERTO_ESQUERDO`: 0,004 do poste esquerdo e 0,028 do direito, só o esquerdo alcança;
- `CAIXA_NO_MEIO`: 0,016 de cada poste, empate, nenhum dos dois é suporte;
- `CAIXA_PERTO_DIREITO`: sobre o poste direito, só ele alcança.

A cena é montada como observações de símbolo (método do modelo e método legado), prontas para o
`reconcile_symbols`; os textos e discos do desenho ficam no teste de cadeia.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Final

from tests.unit.test_symbol_reconciliation import _observation, _profile

from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.enums import SituacaoProjeto
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    FonteObservacaoSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
)

POSTE_ESQUERDO: Final = ("0.30", "0.30")
POSTE_DIREITO: Final = ("0.34", "0.30")
LADO: Final = "0.008"

# Canto superior esquerdo de cada caixa; a altura 0,296 a 0,304 contém a linha dos postes.
CAIXA_PERTO_ESQUERDO: Final = ("0.304", "0.296")
CAIXA_NO_MEIO: Final = ("0.316", "0.296")
CAIXA_PERTO_DIREITO: Final = ("0.332", "0.296")

# Estai longe dos dois postes: caixa do pictograma do modelo (lado 0,020) e caixa do eixo do
# legado (lado 0,008), com o centro do legado (0,509) dentro da caixa do modelo (0,500 a 0,520).
CAIXA_ESTAI_MODELO: Final = ("0.500", "0.500")
LADO_ESTAI_MODELO: Final = "0.020"
CAIXA_ESTAI_LEGADO: Final = ("0.505", "0.505")

# Disco disputado pelos dois postes, no meio deles, e um terceiro poste com disco próprio a 0,016
# do símbolo que cai sobre o disputado. O rótulo do terceiro fica à direita, longe dos discos.
DISCO_DISPUTADO: Final = (0.32, 0.30)
CAIXA_NO_DISCO: Final = ("0.318", "0.298")
LADO_NO_DISCO: Final = "0.004"
POSTE_TERCEIRO: Final = ("0.32", "0.325")
ROTULO_TERCEIRO: Final = ("0.36", "0.325")
DISCO_TERCEIRO: Final = (0.32, 0.318)

_CLASSES_EXTRAS: Final = ("EQUIPAMENTO_INTERRUPCAO",)


@dataclass(frozen=True, slots=True)
class FolhaDeSimbolos:
    """Documento e página de onde vêm as observações."""

    documento_id: str
    documento_sha256: str
    pagina_numero: int = 1


def _perfil(nome: str) -> PerfilMetodoSimbolos:
    base = _profile(nome)
    return replace(base, classes_suportadas=(*base.classes_suportadas, *_CLASSES_EXTRAS))


PERFIL_MODELO: Final = _perfil("declarative-drawing-model")
PERFIL_LEGADO: Final = _perfil("pymupdf-guys")


def observacao(
    perfil: PerfilMetodoSimbolos,
    classe: str,
    canto: tuple[str, str],
    folha: FolhaDeSimbolos,
    *,
    lado: str = LADO,
    subtipo: str | None = None,
    atributos: ExtraAttributes = (),
    situacao: SituacaoProjeto | None = None,
) -> ObservacaoSimbolo:
    """Observação em caixa quadrada de `lado`, com o canto superior esquerdo em `canto`."""
    base = _observation(
        perfil,
        classe,
        x=canto[0],
        y=canto[1],
        width=lado,
        height=lado,
        page=folha.pagina_numero,
        attributes=atributos,
        situation=situacao,
        primitive=f"{perfil.metodo_id}:{classe}:{canto[0]}:{canto[1]}",
    )
    return replace(
        base,
        fonte=FonteObservacaoSimbolo(
            documento_id=folha.documento_id,
            documento_sha256=folha.documento_sha256,
            pagina_numero=folha.pagina_numero,
            camada="base",
            origem_pdf=base.fonte.origem_pdf,
        ),
        alternativas=(
            AlternativaClasseSimbolo(classe=classe, subtipo=subtipo, score_bruto=Decimal(0)),
        ),
    )
