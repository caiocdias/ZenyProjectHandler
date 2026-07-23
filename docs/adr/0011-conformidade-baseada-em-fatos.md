# ADR 0011 - Conformidade baseada em fatos e regras versionadas

## Status

Aceita em 23/07/2026.

## Contexto

Normas de projeto misturam presença documental, limites numéricos, tabelas condicionais, exceções,
compatibilidade, geometria, topologia e cálculos. Colocar cada verificação diretamente no scanner ou
na interface impediria auditoria, atualização normativa e distinção entre dado ausente e
descumprimento.

## Decisão

- Separar evidência extraída, fato normalizado, regra normativa e achado.
- Escopar cada fato e regra a projeto, documento, página, região ou elemento.
- Exigir origem, confiança e evidências para fatos derivados.
- Versionar o registro JSON, sua fonte normativa e uma assinatura SHA-256 canônica.
- Representar aplicabilidade por `when`, exceções comprovadas por `unless` e requisitos por `must`.
- Produzir `CONFORME`, `DIVERGENCIA` ou `NAO_AVALIAVEL`, mantendo divergência automática como
  candidata até revisão.
- Manter geometria, topologia, compatibilidade e fórmulas em avaliadores especializados que
  publiquem fatos; não executar código arbitrário vindo do registro JSON.
- Preservar a versão usada em cada achado e exigir reavaliação explícita após mudança normativa.

## Consequências

Uma regra pode mudar sem recompilar o domínio, mas somente dentro dos operadores suportados e depois
de validação. A fonte e a explicação permanecem rastreáveis. O custo é manter um vocabulário estável
de fatos e criar avaliadores específicos para regras complexas. Ausência de contexto reduz a
automação, mas evita reprovar projetos por inferência indevida.
