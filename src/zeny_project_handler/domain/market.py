"""Valores canônicos do cadastro operacional externo."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.project_metadata import normalizar_numero_ns


class Mercado(StrEnum):
    """Únicos mercados aceitos do cadastro externo de Notas de Serviço."""

    RURAL = "RURAL"
    URBANO = "URBANO"


class ClassificacaoMercado(StrEnum):
    RURAL = "RURAL"
    URBANO = "URBANO"
    AMBOS = "AMBOS"


class OrigemClassificacao(StrEnum):
    SQL = "SQL"
    MANUAL = "MANUAL"


@dataclass(frozen=True, slots=True, kw_only=True)
class ClassificacaoProjeto:
    """Escolha vigente vinculada à NS, separada da resposta inicial do cadastro."""

    numero_ns: str
    mercado_banco: Mercado
    efetiva: ClassificacaoMercado
    origem: OrigemClassificacao
    inicializada_em: datetime
    alterada_em: datetime
    revisao: UUID
    versao: int = 1

    def __post_init__(self) -> None:
        normalizar_numero_ns(self.numero_ns)
        if (
            not isinstance(self.mercado_banco, Mercado)
            or not isinstance(self.efetiva, ClassificacaoMercado)
            or not isinstance(self.origem, OrigemClassificacao)
        ):
            raise DomainValidationError("Classificação de mercado inválida")
        if any(
            date.tzinfo is None or date.utcoffset() is None
            for date in (self.inicializada_em, self.alterada_em)
        ):
            raise DomainValidationError("Instantes da classificação devem possuir fuso horário")
        if self.versao < 1 or self.alterada_em < self.inicializada_em:
            raise DomainValidationError("Versão ou instantes da classificação inválidos")
        if (
            self.origem is OrigemClassificacao.SQL
            and self.efetiva.value != self.mercado_banco.value
        ):
            raise DomainValidationError("Classificação inicial deve corresponder ao SQL")

    @classmethod
    def inicializar(
        cls, numero_ns: str, mercado: Mercado, instante: datetime
    ) -> "ClassificacaoProjeto":
        return cls(
            numero_ns=numero_ns,
            mercado_banco=mercado,
            efetiva=ClassificacaoMercado(mercado.value),
            origem=OrigemClassificacao.SQL,
            inicializada_em=instante,
            alterada_em=instante,
            revisao=uuid4(),
        )

    def editar(self, efetiva: ClassificacaoMercado, instante: datetime) -> "ClassificacaoProjeto":
        return replace(
            self,
            efetiva=efetiva,
            origem=OrigemClassificacao.MANUAL,
            alterada_em=instante,
            revisao=uuid4(),
            versao=self.versao + 1,
        )


class DescricaoAcao(StrEnum):
    """Descrições exatas de ações cuja conclusão pode ser consultada."""

    AVALIAR_IMPACTO_AMBIENTAL = "AVALIAR IMPACTO AMBIENTAL"
    FALTA_SERVIDAO = "FALTA SERVIDÃO"
