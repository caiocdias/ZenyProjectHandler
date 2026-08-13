# ADR 0005 - Exemplos locais dinâmicos e regressão sintética

## Status

Revisada em 2026-08-13. Esta decisão substitui o manifesto privado congelado e seu gate separado.

## Contexto

PDFs reais ajudam a encontrar formatos inesperados, mas mudam entre computadores e não são uma base
reprodutível para o gate do projeto. O antigo manifesto exigia um conjunto específico que já não
correspondia aos arquivos disponíveis e sustentava contratos, testes e documentação sem participar
do fluxo produtivo.

## Decisão

1. `examples/` é uma área local dinâmica. Todo o seu conteúdo é ignorado pelo Git, exceto o guia da
   própria pasta.
2. O gate padrão usa somente fixtures sintéticas públicas e não consulta `examples/`.
3. Um smoke local opcional descobre recursivamente os PDFs presentes, executa inspeção, renderização,
   extração nativa e interpretação sem persistir resultados nem modificar as origens.
4. Não existe manifesto versionado, lista obrigatória, partição privada, marcador Pytest especial ou
   gate paralelo. Uma pasta vazia é válida.
5. Um comportamento observado localmente só vira regressão depois de ser reproduzido por fixture
   sintética determinística. Conteúdo real não é copiado para a fixture.
6. Regras técnicas exigem fonte normativa rastreável. PDFs de projeto podem revelar uma lacuna, mas
   não são autoridade para criar obrigação ou exceção.

## Consequências

- Qualquer computador pode usar seus próprios exemplos sem atualizar metadados do repositório.
- O gate continua offline, reproduzível e independente de arquivos locais.
- O smoke detecta incompatibilidades práticas sem prometer métricas ou cobertura sem anotações
  humanas confiáveis.
- Garantias duradouras ficam próximas do código, em testes sintéticos revisáveis.
