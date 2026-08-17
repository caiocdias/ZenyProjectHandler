# Catálogo de regras de conformidade

Este catálogo identifica as regras distribuídas com o aplicativo. A definição executável canônica —
incluindo descrição, `when`, `unless`, `must`, operadores e URL — está em
`src/zeny_project_handler/adapters/compliance/data/regras_conformidade_v1.json`. Evitar reproduzir
essas condições aqui reduz o risco de divergência entre documentação e código.

- Versão do seed: `cemig-normas-distribuicao-2025.6`.
- Regras: 39 ativas, 0 inativas.
- Método de conformidade: versão `6`.
- Escopos usados pelo seed: `PROJETO` e `REGIAO`.
- Fontes e cobertura normativa: [inventario-fontes-normativas.md](inventario-fontes-normativas.md).

## Semântica operacional

- IDs técnicos são estáveis e recebem números de exibição permanentes no SQLite.
- Todas as condições `when` precisam ser atendidas para a regra ser aplicada ao alvo.
- Todas as condições `unless` atendidas dispensam a regra naquele alvo.
- Todos os requisitos `must` precisam ser atendidos; ausência, contradição ou valor inválido em um
  requisito de uma regra aplicável produz `DIVERGENCIA`.
- Regras cujo escopo ainda não pode ser caracterizado usam fatos de guarda em `when`; a falha da
  guarda omite o achado em vez de presumir uma divergência.
- Importações mesclam por ID e não removem IDs omitidos. O estado `enabled` só muda por importação do
  próprio ID.

## Regras distribuídas

| Número | ID técnico | Título | Estado | Escopo | Severidade | Fonte registrada |
|---|---|---|---|---|---|---|
| Regra 1 | `nd31.desenho.numero-projeto` | NS do cabeçalho corresponde ao projeto | ATIVA | PROJETO | ERRO | CEMIG ND-3.1, Jul/2025, Apresentação do Projeto, 2.4, p. 88 |
| Regra 2 | `nd31.desenho.formato` | Formato de folha padronizado | ATIVA | PROJETO | ALERTA | CEMIG ND-3.1, Jul/2025, Apresentação do Projeto, 2.3, p. 88 |
| Regra 3 | `nd31.desenho.escala` | Escala urbana de apresentação | ATIVA | PROJETO | ALERTA | CEMIG ND-3.1, Jul/2025, Apresentação do Projeto, 2.1, p. 88 |
| Regra 4 | `nd31.equipamento.estrutura-angulo` | Equipamento em estrutura de ângulo | ATIVA | REGIAO | CRITICA | CEMIG ND-3.1, Jul/2025, Dimensionamento Mecânico, observação j, p. 66 |
| Regra 5 | `nd31.equipamento.risco-abalroamento` | Avaliação de abalroamento em equipamento no ângulo | ATIVA | REGIAO | CRITICA | CEMIG ND-3.1, Jul/2025, Dimensionamento Mecânico, observação j, p. 67 |
| Regra 6 | `nd31.vao.urbano-compacto-isolado` | Vão máximo de rede compacta ou isolada urbana | ATIVA | REGIAO | ERRO | CEMIG ND-3.1, Jul/2025, Locação de Postes, 3, alíneas b e c, p. 27 |
| Regra 7 | `nd31.cabo.convencional-novo-urbano` | Cabo nu convencional em obra nova urbana | ATIVA | REGIAO | ERRO | CEMIG ND-3.1, Jul/2025, Tipos de Rede e Critérios de Aplicação, 1.1.3, p. 18 |
| Regra 8 | `nd93.compatibilidade.estrutura-poste-duplo-t` | Estrutura compacta rural incompatível com poste duplo T | ATIVA | REGIAO | ERRO | CEMIG ND-9.3, Set/2021, Instalações Básicas de Rede Compacta em Áreas Rurais, Estruturas, nota 2, p. 43 |
| Regra 9 | `nd31.transformador.poste-existente-30-75` | Poste existente para transformador trifásico de 30 a 75 kVA | ATIVA | REGIAO | ERRO | CEMIG ND-3.1, Jul/2025, Dimensionamento Mecânico, 1.3.2, observação t, p. 67 |
| Regra 10 | `nd31.transformador.poste-existente-150-300` | Poste existente para transformador trifásico de 150 ou 300 kVA | ATIVA | REGIAO | ERRO | CEMIG ND-3.1, Jul/2025, Dimensionamento Mecânico, 1.3.2, observação t, p. 67 |
| Regra 11 | `nd31.desenho.numero-folha` | Número da folha informado | ATIVA | PROJETO | ALERTA | CEMIG ND-3.1, Jul/2025, Apresentação do Projeto, 2.5, p. 89 |
| Regra 12 | `nd31.desenho.data-projeto` | Data do projeto informada | ATIVA | PROJETO | ALERTA | CEMIG ND-3.1, Jul/2025, Apresentação do Projeto, 2.5, p. 89 |
| Regra 13 | `nd31.desenho.circuito` | Circuito ou alimentador informado | ATIVA | PROJETO | ALERTA | CEMIG ND-3.1, Jul/2025, Apresentação do Projeto, 2.5.2, p. 89 |
| Regra 14 | `nd31.poste.urbano-altura-minima` | Poste urbano novo com altura mínima | ATIVA | REGIAO | ERRO | CEMIG ND-3.1, Jul/2025, Dimensionamento Mecânico, Posteação, 1.2, p. 59 |
| Regra 15 | `nd31.poste.urbano-formato-circular` | Poste urbano novo de seção circular | ATIVA | REGIAO | ERRO | CEMIG ND-3.1, Jul/2025, Dimensionamento Mecânico, Posteação, 1.1, p. 58 |
| Regra 16 | `nd31.equipamento.poste-novo-altura` | Poste novo com equipamento acima de 11 m | ATIVA | REGIAO | ERRO | CEMIG ND-3.1, Jul/2025, Dimensionamento Mecânico, Posteação, 1.2, alínea d, p. 59 |
| Regra 17 | `nd31.equipamento.poste-novo-resistencia` | Poste novo com equipamento de 600 daN | ATIVA | REGIAO | ERRO | CEMIG ND-3.1, Jul/2025, Dimensionamento Mecânico, observação r, p. 67 |
| Regra 18 | `catalogo.compatibilidade.estrutura-cabo` | Estrutura compatível com o cabo | ATIVA | REGIAO | ERRO | CEMIG ND-2.7 / ND-2.9, Nov/2016 / Jun/2016, estruturas padronizadas e cabos aplicáveis, p. 27 |
| Regra 19 | `nd31.transformador.chave-fusivel` | Chave fusível no transformador | ATIVA | REGIAO | CRITICA | CEMIG ND-3.1, Jul/2025, Dimensionamento Elétrico, 2.2.7, p. 49 |
| Regra 20 | `nd31.transformador.para-raios-bt` | Para-raios de BT no transformador | ATIVA | REGIAO | CRITICA | CEMIG ND-3.1, Jul/2025, Dimensionamento Elétrico, 1.6, alínea a, p. 40 |
| Regra 21 | `nd31.transformador.para-raios-mt` | Para-raios de MT no transformador | ATIVA | REGIAO | CRITICA | CEMIG ND-3.1, Jul/2025, Dimensionamento Elétrico, 2.2.8, alínea a, p. 51 |
| Regra 22 | `nd31.transformador.aterramento` | Aterramento no transformador | ATIVA | REGIAO | CRITICA | CEMIG ND-3.1, Jul/2025, Dimensionamento Elétrico, 7, alínea g, p. 57 |
| Regra 23 | `nd31.documentacao.relacao-materiais-orcamento` | Relação de materiais e orçamento identificada | ATIVA | PROJETO | ERRO | CEMIG ND-3.1, Jul/2025, Apresentação do Projeto, itens 1 e 2.6, p. 90 |
| Regra 24 | `nd31.documentacao.memoria-calculo` | Memória de cálculo identificada | ATIVA | PROJETO | ERRO | CEMIG ND-3.1, Jul/2025, Apresentação do Projeto, item 1, p. 88 |
| Regra 25 | `nd31.desenho.numeracao-postes` | Postes numerados de P1 a Pn | ATIVA | PROJETO | ERRO | CEMIG ND-3.1, Jul/2025, Apresentação do Projeto, 2.5.2, p. 90 |
| Regra 26 | `nd22.projeto.prordr-acima-300` | PRORDR em extensão rural acima de 300 m | ATIVA | PROJETO | ERRO | CEMIG ND-2.2, Out/2016, Introdução, nota geral 4, p. 14 |
| Regra 27 | `nd22.cabo.rural-vao-maior-80-caa` | Cabo CAA em vão rural acima de 80 m | ATIVA | REGIAO | ERRO | CEMIG ND-2.2, Out/2016, Introdução, nota geral 3, p. 14 |
| Regra 28 | `nd93.transformador.poste-novo-rural` | Poste novo rural de transformador | ATIVA | REGIAO | ERRO | CEMIG ND-9.3, Set/2021, Capítulo 7, nota 16, p. 41 |
| Regra 29 | `nd93.rede.transicao-sem-angulo` | Transição de rede sem deflexão | ATIVA | REGIAO | ERRO | CEMIG ND-9.3, Set/2021, Capítulo 7, nota 10, p. 41 |
| Regra 30 | `nd31.rede.para-raios-mt-fim-transicao` | Para-raios MT em fim ou transição de rede | ATIVA | REGIAO | CRITICA | CEMIG ND-3.1, Jul/2025, Dimensionamento Elétrico, 2.2.8, p. 51 |
| Regra 31 | `nd93.rede.compacta-ancoragem-500m` | Ancoragem periódica da rede compacta | ATIVA | PROJETO | ALERTA | CEMIG ND-9.3, Set/2021, Capítulo 7, nota 17, p. 41 |
| Regra 32 | `pacote.coerencia.transformador-potencia` | Potência do transformador coerente entre desenho e orçamento | ATIVA | PROJETO | ERRO | Controle de coerência do pacote documental, 2025.6, potência entre documentos |
| Regra 33 | `pacote.coerencia.fases` | Fases coerentes entre desenho e orçamento | ATIVA | PROJETO | ERRO | Controle de coerência do pacote documental, 2025.6, fases entre documentos |
| Regra 34 | `pacote.coerencia.codigo` | Código técnico coerente entre desenho e orçamento | ATIVA | PROJETO | ERRO | Controle de coerência do pacote documental, 2025.6, código entre documentos |
| Regra 35 | `pacote.coerencia.circuito` | Circuito coerente entre desenho e orçamento | ATIVA | PROJETO | ERRO | Controle de coerência do pacote documental, 2025.6, circuito entre documentos |
| Regra 36 | `pacote.documentacao.gd` | Documentação de acesso para geração distribuída | ATIVA | PROJETO | ALERTA | Controle documental do projeto, 2025.6, documentos de acesso e conexão de GD |
| Regra 37 | `pacote.documentacao.prordr-fotos` | Registro fotográfico no pacote PRORDR | ATIVA | PROJETO | ALERTA | Controle documental do projeto, 2025.6, pacote PRORDR e registro fotográfico |
| Regra 38 | `nd31.rede.neutro-aterramento-200m` | Aterramento periódico do neutro | ATIVA | PROJETO | ERRO | CEMIG ND-3.1, Jul/2025, Dimensionamento Elétrico, item 7, p. 57 |
| Regra 39 | `nd31.rede.compacta-aterramento-temporario-160m` | Pontos periódicos de aterramento temporário da rede compacta | ATIVA | PROJETO | ALERTA | CEMIG ND-3.1, Jul/2025, Dimensionamento Elétrico, item 7, p. 57 |

## Manutenção

Uma alteração de obrigação, aplicabilidade ou exceção recebe novo ID. Correção de redação ou
localizador que não muda a obrigação mantém o ID. Toda mudança deve atualizar o JSON, este resumo e
os testes de paridade no mesmo commit.

Uma regra nova só entra no seed depois que seus fatos preservam tipo, unidade, alvo, situação,
associação e proveniência. Os testes mínimos cobrem aplicabilidade, exceções, conformidade,
divergência e ausência dos fatos de guarda.
