# ADR 0009 - Promoção automática de resultados catalogados

- Estado: aceito
- Data: 2026-07-22
- Substitui parcialmente: ADR 0001 e ADR 0006

## Contexto

O fluxo inicial exigia aceitar ou rejeitar cada proposta antes que o elemento participasse do
projeto. Isso repetia uma decisão que o próprio analisador já havia tomado e impedia as
etapas seguintes de usar resultados válidos. A tabela plana também ocultava relações importantes,
como transformador e estruturas novas instalados em um poste novo próximo de outro poste a remover.

## Decisão

`PropostaElemento` e `PropostaRelacao` continuam sendo a trilha auditável da análise. Ao concluir uma
execução, todo resultado com item ativo de catálogo e dependências de domínio resolvíveis será
promovido automaticamente ao agregado do projeto, acompanhado de uma decisão automática. IDs UUID5
garantem que repetir ou reabrir a execução não duplique elementos, pontos, relações ou decisões.

Quando uma nomenclatura de poste informa altura e resistência, mas omite o formato, o primeiro tipo
canônico do catálogo é escolhido deterministicamente e os demais candidatos permanecem nos
atributos da proposta. Resultados sem item exato de catálogo continuam auditáveis, mas não são
materializados em uma entidade inválida.

Relações de estrutura ou equipamento com poste priorizam a mesma situação de obra antes da distância.
A interface apresenta os resultados em árvore, com postes como pais e seus dependentes como filhos;
o PDF mantém um sublinhado clicável para cada elemento. A confirmação item a item e seus campos de
decisão deixam de fazer parte do fluxo principal.

## Consequências

- Regiões de ocorrência e etapas posteriores recebem os resultados assim que a análise termina.
- Uma instalação nova não se vincula a um poste a remover apenas por pequena diferença de distância.
- A auditoria continua informando evidências, regra, confiança, inferências e alternativas de catálogo.
- Erros de análise passam a exigir um fluxo excepcional de correção, não uma confirmação obrigatória
  para todos os itens.
- Propostas sem catálogo resolvido permanecem visíveis e não corrompem as invariantes do domínio.
