"""Vocabulário explícito e validação semântica dos fatos de conformidade."""

from __future__ import annotations

from decimal import Decimal

from zeny_project_handler.domain.compliance import (
    CondicaoConformidade,
    DefinicaoFatoConformidade,
    DisponibilidadeProvedorFato,
    OperadorCondicao,
    RegistroRegrasConformidade,
    TipoEscopoConformidade,
    TipoValorFato,
)
from zeny_project_handler.domain.errors import DomainValidationError

_PRESENCA = frozenset({OperadorCondicao.EXISTE, OperadorCondicao.AUSENTE})
_IGUALDADE = frozenset(
    {
        OperadorCondicao.IGUAL,
        OperadorCondicao.DIFERENTE,
        OperadorCondicao.EM,
        OperadorCondicao.NAO_EM,
    }
)
_ORDEM = frozenset(
    {
        OperadorCondicao.MENOR,
        OperadorCondicao.MENOR_OU_IGUAL,
        OperadorCondicao.MAIOR,
        OperadorCondicao.MAIOR_OU_IGUAL,
    }
)
_TEXTO = _PRESENCA | _IGUALDADE | {OperadorCondicao.CONTEM}
_NUMERO = _PRESENCA | _IGUALDADE | _ORDEM
_BOOLEANO = _PRESENCA | _IGUALDADE


def _fact(
    key: str,
    scopes: tuple[TipoEscopoConformidade, ...],
    value_type: TipoValorFato,
    operators: frozenset[OperadorCondicao],
    description: str,
    *,
    available: bool = True,
) -> DefinicaoFatoConformidade:
    return DefinicaoFatoConformidade(
        chave=key,
        escopos=frozenset(scopes),
        tipo_valor=value_type,
        operadores=operators,
        descricao=description,
        disponibilidade=(
            DisponibilidadeProvedorFato.DISPONIVEL
            if available
            else DisponibilidadeProvedorFato.PLANEJADO
        ),
    )


_PROJECT = (TipoEscopoConformidade.PROJETO,)
_DOCUMENT = (TipoEscopoConformidade.DOCUMENTO,)
_REGION = (TipoEscopoConformidade.REGIAO,)
_PROJECT_REGION = (TipoEscopoConformidade.PROJETO, TipoEscopoConformidade.REGIAO)

CATALOGO_FATOS_CONFORMIDADE = (
    _fact(
        "rede.contexto_urbano",
        _PROJECT_REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica contexto urbano confirmado para o projeto ou região.",
    ),
    _fact(
        "rede.contexto_rural",
        _PROJECT_REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica contexto rural confirmado para a região.",
    ),
    _fact(
        "projeto.nota_servico",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Nota de Serviço usada como nome do projeto.",
    ),
    _fact(
        "projeto.codigo_servico",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Código de serviço consultado, preservado como texto canônico de quatro dígitos.",
    ),
    _fact(
        "projeto.impacto_ambiental_sim",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica campo Impacto Ambiental com valor normalizado exatamente SIM no cabeçalho.",
    ),
    _fact(
        "projeto.servidao_mencionada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica menção positiva a servidão ou faixa de domínio no pacote PDF.",
    ),
    _fact(
        "projeto.acao_avaliar_impacto_ambiental_concluida",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica conclusão da ação AVALIAR IMPACTO AMBIENTAL para a NS e serviços atuais.",
    ),
    _fact(
        "projeto.acao_falta_servidao_concluida",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica conclusão da ação FALTA SERVIDÃO para a NS e serviços atuais.",
    ),
    _fact(
        "projeto.nota_servico_cabecalho",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Nota de Serviço extraída de um cabeçalho PDF do projeto.",
    ),
    _fact(
        "projeto.nota_servico_divergencia",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Descreve uma diferença entre a NS do cabeçalho PDF e o nome do projeto.",
    ),
    _fact(
        "projeto.escala",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Escala declarada no projeto.",
    ),
    _fact(
        "projeto.formato_folha",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Formato de folha consolidado para o projeto.",
    ),
    _fact(
        "projeto.numero_folha",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Número de folha identificado no projeto.",
    ),
    _fact(
        "projeto.data_projeto",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Data do projeto em representação textual normalizada.",
    ),
    _fact(
        "projeto.circuito",
        _PROJECT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Circuito ou alimentador identificado no projeto.",
    ),
    _fact(
        "projeto.relacao_materiais_orcamento_identificada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica relação de materiais e orçamento identificada no pacote PDF.",
    ),
    _fact(
        "projeto.memoria_calculo_identificada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica memória de cálculo elétrico e mecânico identificada no pacote PDF.",
    ),
    _fact(
        "projeto.postes_total",
        _PROJECT,
        TipoValorFato.INTEIRO,
        _NUMERO,
        "Quantidade de postes ativos no modelo confirmado.",
    ),
    _fact(
        "projeto.postes_numeracao_sequencial",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica numeração P1..Pn completa, única e sequencial.",
    ),
    _fact(
        "projeto.extensao_rede_instalar_m",
        _PROJECT,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Extensão conhecida de percursos a instalar, sem contar cabos paralelos em duplicidade.",
    ),
    _fact(
        "projeto.extensao_rede_instalar_avaliada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica cobertura completa dos comprimentos após deduplicar percursos paralelos.",
    ),
    _fact(
        "projeto.prordr_identificado",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica referência ao PRORDR no pacote PDF.",
    ),
    _fact(
        "projeto.coerencia_potencia_transformador_avaliada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica potência comparável no desenho e no orçamento/relação de materiais.",
    ),
    _fact(
        "projeto.coerencia_potencia_transformador",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica igualdade da potência do transformador entre os documentos comparados.",
    ),
    _fact(
        "projeto.coerencia_fases_avaliada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica configuração de fases comparável entre desenho e orçamento.",
    ),
    _fact(
        "projeto.coerencia_fases",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica igualdade da configuração de fases entre os documentos comparados.",
    ),
    _fact(
        "projeto.coerencia_codigo_avaliada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica código técnico comparável entre desenho e orçamento.",
    ),
    _fact(
        "projeto.coerencia_codigo",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica igualdade do código técnico entre os documentos comparados.",
    ),
    _fact(
        "projeto.coerencia_circuito_avaliada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica circuito comparável entre desenho e orçamento.",
    ),
    _fact(
        "projeto.coerencia_circuito",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica igualdade do circuito ou alimentador entre os documentos comparados.",
    ),
    _fact(
        "projeto.geracao_distribuida_identificada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica menção inequívoca a geração distribuída, microgeração ou minigeração.",
    ),
    _fact(
        "projeto.documentacao_gd_identificada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica documento de acesso, conexão ou comissionamento de GD no pacote.",
    ),
    _fact(
        "projeto.registro_fotografico_identificado",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica registro ou relatório fotográfico no pacote PDF.",
    ),
    _fact(
        "projeto.rede_compacta_extensao_m",
        _PROJECT,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Extensão conhecida da rede compacta ativa.",
    ),
    _fact(
        "projeto.rede_compacta_maior_componente_m",
        _PROJECT,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Extensão do maior componente topológico contínuo de rede compacta.",
    ),
    _fact(
        "projeto.rede_compacta_ancoragem_avaliada",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica percurso acíclico e comprimentos completos para avaliar ancoragem periódica.",
    ),
    _fact(
        "projeto.rede_compacta_maior_trecho_sem_ancoragem_m",
        _PROJECT,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Maior percurso contínuo de rede compacta sem atravessar estrutura de ancoragem.",
    ),
    _fact(
        "projeto.rede_compacta_ancoragem_suficiente",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica percurso máximo entre estruturas de ancoragem compatível com 500 m.",
    ),
    _fact(
        "projeto.neutro_maior_componente_m",
        _PROJECT,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Extensão do maior componente contínuo formado por cabos catalogados de neutro.",
    ),
    _fact(
        "projeto.neutro_aterramento_periodico_avaliado",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica percurso de neutro acíclico e comprimentos completos para avaliar aterramento.",
    ),
    _fact(
        "projeto.neutro_maior_trecho_sem_aterramento_m",
        _PROJECT,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Maior percurso contínuo do neutro sem atravessar símbolo de aterramento "
        "associado a poste.",
    ),
    _fact(
        "projeto.neutro_aterramento_periodico_suficiente",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica espaçamento máximo de aproximadamente 200 m entre pontos de aterramento do neutro.",
    ),
    _fact(
        "projeto.rede_compacta_aterramento_temporario_avaliado",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica percurso compacto acíclico e comprimentos completos para a aproximação "
        "de aterramento temporário.",
    ),
    _fact(
        "projeto.rede_compacta_maior_trecho_sem_aterramento_m",
        _PROJECT,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Maior percurso compacto sem símbolo genérico de aterramento associado a poste.",
    ),
    _fact(
        "projeto.rede_compacta_aterramento_temporario_suficiente",
        _PROJECT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Aproxima a periodicidade de 160 m usando ATERRAMENTO, pois o modelo não "
        "distingue alça temporária.",
    ),
    _fact(
        "documento.nota_servico",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Nota de Serviço encontrada no documento.",
    ),
    _fact(
        "documento.escala",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Escala encontrada no documento.",
    ),
    _fact(
        "documento.formato_folha",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Formato informado ou inferido pelas dimensões do documento.",
    ),
    _fact(
        "documento.numero_folha",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Número de folha encontrado no documento.",
    ),
    _fact(
        "documento.data_projeto",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Data do projeto encontrada no documento.",
    ),
    _fact(
        "documento.circuito",
        _DOCUMENT,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Circuito ou alimentador encontrado no documento.",
    ),
    _fact(
        "documento.servidao_mencionada",
        _DOCUMENT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica menção positiva a servidão ou faixa de domínio.",
    ),
    _fact(
        "documento.carimbo_candidato_quantidade",
        _DOCUMENT,
        TipoValorFato.INTEIRO,
        _NUMERO,
        "Quantidade de anotações PDF candidatas a carimbo.",
    ),
    _fact(
        "documento.assinatura_pdf_preenchida",
        _DOCUMENT,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica campo PDF de assinatura positivamente preenchido.",
    ),
    _fact(
        "regiao.equipamento_instalar",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica equipamento a instalar reconhecido na região.",
    ),
    _fact(
        "regiao.equipamento_classe",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Classe catalogada do equipamento reconhecido na região.",
    ),
    _fact(
        "regiao.risco_abalroamento_avaliado",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica evidência positiva de avaliação de risco de abalroamento.",
    ),
    _fact(
        "cabo.tecnologia",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Tecnologia catalogada do cabo reconhecido na região.",
    ),
    _fact(
        "cabo.instalar_tecnologia",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Tecnologia catalogada de cada cabo reconhecido como instalação na região.",
    ),
    _fact(
        "regiao.estrutura_mt_instalar_codigo",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Código da única estrutura de MT reconhecida como instalação na região.",
    ),
    _fact(
        "regiao.poste_ativo_formato",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Formato do único poste reconhecido e não marcado para remoção na região.",
    ),
    _fact(
        "regiao.transformador_trifasico_poste_existente_avaliavel",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica associação urbana inequívoca entre transformador trifásico a instalar "
        "e poste existente.",
    ),
    _fact(
        "regiao.transformador_potencia_kva",
        _REGION,
        TipoValorFato.INTEIRO,
        _NUMERO,
        "Potência nominal do transformador, normalizada de um código catalogado exato.",
    ),
    _fact(
        "regiao.poste_transformador_resistencia_dan",
        _REGION,
        TipoValorFato.INTEIRO,
        _NUMERO,
        "Resistência nominal do poste inequivocamente associado ao transformador, em daN.",
    ),
    _fact(
        "regiao.poste_transformador_formato",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Formato canônico do poste associado ao transformador.",
    ),
    _fact(
        "conexao.angulo_graus",
        _REGION,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Deflexão calculada entre arestas resolvidas da rede de distribuição, em graus.",
    ),
    _fact(
        "regiao.topologia_mt_avaliavel",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica que a topologia MT no poste possui componente completo e pode concluir fim ou "
        "transição.",
    ),
    _fact(
        "regiao.componente_mt_completo",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica que endpoints, nível e tecnologia de todas as arestas do componente MT foram "
        "resolvidos.",
    ),
    _fact(
        "regiao.fim_rede",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica grau topológico um em componente MT completo da rede de distribuição.",
    ),
    _fact(
        "regiao.poste_instalar_altura_m",
        _REGION,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Altura do poste a instalar.",
    ),
    _fact(
        "regiao.poste_instalar_resistencia_dan",
        _REGION,
        TipoValorFato.INTEIRO,
        _NUMERO,
        "Resistência do poste a instalar.",
    ),
    _fact(
        "regiao.poste_instalar_formato",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Formato do poste a instalar.",
    ),
    _fact(
        "regiao.poste_equipamento_instalar_altura_m",
        _REGION,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Altura do poste associado a equipamento a instalar.",
    ),
    _fact(
        "regiao.poste_equipamento_instalar_resistencia_dan",
        _REGION,
        TipoValorFato.INTEIRO,
        _NUMERO,
        "Resistência do poste associado a equipamento a instalar.",
    ),
    _fact(
        "regiao.poste_equipamento_instalar_formato",
        _REGION,
        TipoValorFato.TEXTO,
        _TEXTO,
        "Formato do poste novo associado a equipamento a instalar.",
    ),
    _fact(
        "regiao.estrutura_cabo_avaliada",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica que ao menos um par estrutura/cabo foi avaliado.",
    ),
    _fact(
        "regiao.estrutura_cabo_incompativel",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica incompatibilidade catalogada entre estrutura e cabo.",
    ),
    _fact(
        "regiao.transformador_instalar",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica transformador a instalar.",
    ),
    _fact(
        "regiao.chave_fusivel_presente",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica presença de chave fusível.",
    ),
    _fact(
        "regiao.para_raios_mt_presente",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica presença de para-raios MT.",
    ),
    _fact(
        "regiao.transformador_para_raios_mt_presente",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica para-raios MT em todos os postes de transformador a instalar da região.",
    ),
    _fact(
        "regiao.para_raios_mt_requisito_presente",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica para-raios MT em todos os postes de fim ou transição identificados na região.",
    ),
    _fact(
        "regiao.para_raios_bt_presente",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica presença de para-raios BT.",
    ),
    _fact(
        "regiao.aterramento_presente",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica presença de aterramento.",
    ),
    _fact(
        "regiao.transicao_rede",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica transição entre rede convencional e compacta no poste.",
    ),
    _fact(
        "regiao.para_raios_mt_requerido",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica fim de rede MT ou transição que requer para-raios.",
    ),
    _fact(
        "vao.comprimento_m",
        _REGION,
        TipoValorFato.NUMERO,
        _NUMERO,
        "Comprimento rastreável do vão, em metros.",
    ),
    _fact(
        "vao.aplicabilidade_excecao_45_60_resolvida",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica que a aplicabilidade da faixa excepcional de 45 m a 60 m foi resolvida.",
    ),
    _fact(
        "vao.excecao_45_60_demonstrada",
        _REGION,
        TipoValorFato.BOOLEANO,
        _BOOLEANO,
        "Indica demonstração positiva da exceção de vão entre 45 m e 60 m.",
    ),
)

_FACTS_BY_KEY = {item.chave: item for item in CATALOGO_FATOS_CONFORMIDADE}


def fato_conformidade_por_chave(chave: str) -> DefinicaoFatoConformidade | None:
    return _FACTS_BY_KEY.get(chave)


def validar_semantica_registro(
    registro: RegistroRegrasConformidade,
) -> tuple[str, ...]:
    """Recuse declarações incompatíveis e avise sobre provedores ainda planejados."""
    warnings: list[str] = []
    for rule in registro.regras:
        planned_keys: set[str] = set()
        for group_name, conditions in (
            ("when", rule.aplicabilidade),
            ("unless", rule.excecoes),
            ("must", rule.requisitos),
        ):
            for index, condition in enumerate(conditions, start=1):
                definition = _FACTS_BY_KEY.get(condition.chave_fato)
                field = f"{group_name}[{index}]"
                if definition is None:
                    raise _semantic_error(rule.id, field, "fact", "chave de fato desconhecida")
                if rule.escopo not in definition.escopos:
                    raise _semantic_error(
                        rule.id,
                        field,
                        "fact",
                        f"fato não está disponível no escopo {rule.escopo.value}",
                    )
                _validate_condition(rule.id, field, condition, definition)
                if definition.disponibilidade is DisponibilidadeProvedorFato.PLANEJADO:
                    planned_keys.add(definition.chave)
        if planned_keys:
            warnings.append(
                f"Regra {rule.id}: provedor planejado para " + ", ".join(sorted(planned_keys))
            )
    return tuple(warnings)


def _validate_condition(
    rule_id: str,
    field: str,
    condition: CondicaoConformidade,
    definition: DefinicaoFatoConformidade,
) -> None:
    if condition.operador not in definition.operadores:
        raise _semantic_error(
            rule_id,
            field,
            "operator",
            f"operador {condition.operador.value} incompatível com {definition.tipo_valor.value}",
        )
    for value_index, value in enumerate(condition.valores_esperados):
        if not _matches_type(value, definition.tipo_valor):
            raise _semantic_error(
                rule_id,
                field,
                f"expected[{value_index}]",
                f"valor incompatível com {definition.tipo_valor.value}",
            )


def _matches_type(value: object, expected: TipoValorFato) -> bool:
    if expected is TipoValorFato.TEXTO:
        return isinstance(value, str)
    if expected is TipoValorFato.BOOLEANO:
        return isinstance(value, bool)
    if expected is TipoValorFato.INTEIRO:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, (int, Decimal)) and not isinstance(value, bool)


def _semantic_error(
    rule_id: str,
    condition: str,
    field: str,
    reason: str,
) -> DomainValidationError:
    return DomainValidationError(f"Regra '{rule_id}' · campo {condition}.{field}: {reason}")
