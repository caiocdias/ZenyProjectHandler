"""Estados fechados do domínio, distintos dos valores configuráveis do catálogo."""

from enum import StrEnum


class SituacaoProjeto(StrEnum):
    EXISTENTE = "EXISTENTE"
    INSTALAR = "INSTALAR"
    REMOVER = "REMOVER"


class EstadoRevisao(StrEnum):
    PROPOSTA = "PROPOSTA"
    CONFIRMADA = "CONFIRMADA"
    REJEITADA = "REJEITADA"
    CONFLITANTE = "CONFLITANTE"


class StatusCatalogo(StrEnum):
    RASCUNHO = "RASCUNHO"
    PUBLICADO = "PUBLICADO"
    ARQUIVADO = "ARQUIVADO"


class CategoriaElemento(StrEnum):
    POSTE = "POSTE"
    ESTRUTURA_MT = "ESTRUTURA_MT"
    ESTRUTURA_BT = "ESTRUTURA_BT"
    CABO = "CABO"
    EQUIPAMENTO = "EQUIPAMENTO"


class TipoGeometria(StrEnum):
    PONTO = "PONTO"
    CAIXA = "CAIXA"
    POLILINHA = "POLILINHA"
    POLIGONO = "POLIGONO"


class NivelRede(StrEnum):
    MT = "MT"
    BT = "BT"


class TipoPontoRede(StrEnum):
    POSTE = "POSTE"
    DERIVACAO = "DERIVACAO"
    CONEXAO = "CONEXAO"
    ENTREGA = "ENTREGA"
    CAIXA_PASSAGEM = "CAIXA_PASSAGEM"
    TRANSICAO = "TRANSICAO"
    OUTRO = "OUTRO"


class TipoVinculoObra(StrEnum):
    REALOCACAO = "REALOCACAO"
    SUBSTITUICAO = "SUBSTITUICAO"


class TipoEvidencia(StrEnum):
    TEXTO = "TEXTO"
    VETOR = "VETOR"
    IMAGEM = "IMAGEM"
    OCR = "OCR"


class TipoOrigemPdf(StrEnum):
    CONTEUDO_PAGINA = "CONTEUDO_PAGINA"
    ANOTACAO = "ANOTACAO"
    APARENCIA_ANOTACAO = "APARENCIA_ANOTACAO"
    FORM_XOBJECT = "FORM_XOBJECT"


class EstadoExecucaoAnalise(StrEnum):
    INICIADA = "INICIADA"
    CONCLUIDA = "CONCLUIDA"
    FALHOU = "FALHOU"
    CANCELADA = "CANCELADA"


class TipoDecisaoRevisao(StrEnum):
    ACEITAR = "ACEITAR"
    REJEITAR = "REJEITAR"
    AJUSTAR = "AJUSTAR"


class TipoAcaoRevisaoManual(StrEnum):
    CRIAR_ELEMENTO = "CRIAR_ELEMENTO"
    CRIAR_RELACAO = "CRIAR_RELACAO"


class EstadoConexao(StrEnum):
    CONECTADA = "CONECTADA"
    DESCONECTADA = "DESCONECTADA"
    DESCONHECIDA = "DESCONHECIDA"


class ParticaoAvaliacao(StrEnum):
    DESENVOLVIMENTO = "DESENVOLVIMENTO"
    TESTE = "TESTE"


class EstadoConjuntoAvaliacao(StrEnum):
    EM_PREPARACAO = "EM_PREPARACAO"
    CONGELADO = "CONGELADO"


class PapelAnotacao(StrEnum):
    PRIMARIA = "PRIMARIA"
    SECUNDARIA = "SECUNDARIA"
    CONSENSO = "CONSENSO"


class EstadoAnotacao(StrEnum):
    RASCUNHO = "RASCUNHO"
    REVISADA = "REVISADA"
    CONGELADA = "CONGELADA"


class EstadoCriteriosAvaliacao(StrEnum):
    PROPOSTO = "PROPOSTO"
    APROVADO = "APROVADO"


class ModoBenchmark(StrEnum):
    DESENVOLVIMENTO = "DESENVOLVIMENTO"
    TESTE_FINAL = "TESTE_FINAL"
