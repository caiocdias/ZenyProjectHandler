# ADR 0006 - Pipeline semântico versionado e idempotente

## Status

Aceita em 21/07/2026.

## Contexto

A extração nativa produz evidências auditáveis, mas não deve criar elementos confirmados. A
interpretação precisa evoluir sem acoplar domínio, PDF, persistência ou interface e deve poder ser
cancelada e retomada sem duplicar propostas. O conjunto de avaliação ainda não está congelado, logo
os limiares atuais não podem ser tratados como baseline definitivo.

## Decisão

- Manter regras de reconhecimento e relação em JSON com schema e assinatura SHA-256.
- Usar uma `ExecucaoAnalise` própria para cada combinação de projeto, extração, interpretador,
  registro e configuração. A identidade UUID5 determinística torna a repetição idempotente.
- Permitir que propostas da execução semântica referenciem evidências de outra execução do mesmo
  projeto. As chaves estrangeiras continuam impedindo referências entre projetos.
- Isolar analisadores de poste, estrutura MT, estrutura BT, cabo e equipamento atrás de um contrato.
- Na versão inicial, exigir código do catálogo em texto ou OCR. Vetores e imagens próximos fornecem
  geometria, situação e proveniência contextual, mas não são classificados isoladamente.
- Inferir situação pelas assinaturas de cor do catálogo e relações por proximidade, extremidades e
  compatibilidade estrutura-cabo. Toda conclusão permanece como proposta revisável.
- Persistir início, término, estado, versão, parâmetros, diagnósticos e erro fatal. Resultados só são
  publicados atomicamente ao concluir a execução.
- Expor um adaptador sem persistência para o benchmark usar exatamente o pipeline real.

## Consequências

Novas estratégias podem ser adicionadas sem alterar entidades confirmadas ou a interface. Uma falha
de analisador vira diagnóstico localizado; falha fatal e cancelamento permanecem retomáveis e
auditáveis. O reconhecimento exclusivamente visual por forma ou imagem fica para novas regras,
depois de anotação humana e baseline congelado. Os limites atuais são iniciais e não comprovam a
qualidade sobre projetos reais.
