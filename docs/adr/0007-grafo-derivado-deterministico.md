# ADR 0007 - Grafo derivado, determinístico e revisável

> **Substituída pela ADR 0010 em 2026-07-22.** A projeção de grafo, sua interface e sua dependência
> foram removidas; este arquivo permanece somente como registro histórico.

## Status

Aceita em 21/07/2026.

## Contexto

O projeto precisa oferecer uma leitura física e outra elétrica do mesmo conjunto confirmado,
preservar cabos paralelos, encontrar inconsistências e permitir revisão humana de ligações
incertas. Persistir um grafo independente duplicaria informações e poderia divergir das entidades
confirmadas. Também não há, no modelo atual, evidência suficiente de fonte e sentido de fluxo para
orientar as arestas.

## Decisão

- Tratar o grafo como projeção descartável do agregado `Projeto` e de sua versão de catálogo.
- Manter os tipos da projeção no domínio e o contrato de reconstrução em uma porta, sem dependência
  de NetworkX fora do adaptador.
- Usar `MultiGraph` não direcionado para preservar arestas paralelas. Uma projeção dirigida só será
  introduzida quando origem e fluxo existirem como dados confirmados.
- Produzir separadamente a visão física de postes/equipamentos e a visão elétrica de
  pontos/terminais.
- Ordenar entradas e derivar identificadores por UUID5. Calcular uma assinatura SHA-256 canônica do
  resultado para comprovar idempotência e detectar revisões concorrentes.
- Gerar diagnósticos rastreáveis e propostas de conexão por geometria, proximidade e compatibilidade.
  Propostas nunca alteram o conjunto confirmado automaticamente.
- Persistir somente a `RelacaoConfirmada` aceita e seu `RegistroRevisaoManual`; reconstruir a projeção
  depois da decisão.
- Expor reconstrução, filtros, diagnósticos, destaque, navegação ao PDF e confirmação no painel Qt.

## Consequências

O mesmo conjunto confirmado e a mesma versão do reconstrutor geram a mesma assinatura,
independentemente da ordem de persistência. Não existe sincronização entre duas fontes de verdade e
um grafo pode ser recalculado após qualquer revisão. O custo é reconstruir a projeção sob demanda e
manter explícita a versão do adaptador. Fluxo dirigido, cálculo elétrico e inferência sem evidência
confirmada permanecem fora do escopo atual.
