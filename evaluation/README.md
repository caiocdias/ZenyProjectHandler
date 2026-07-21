# Conjunto de avaliação

Este diretório contém apenas contratos, critérios e metadados anônimos. Os PDFs e as anotações reais
não são publicados aqui. O manifesto separa `DESENVOLVIMENTO` de `TESTE`; amostras de teste não podem
ser consultadas durante a criação ou ajuste de regras da Etapa 6.

## Estado atual

- O manifesto está em `EM_PREPARACAO` e os critérios estão `PROPOSTO`.
- A auditoria automática identifica a ausência de variedade de escala no corpus atual.
- As amostras marcadas com `double_annotation` exigem dois anotadores independentes e adjudicação.
- O conjunto só pode mudar para `CONGELADO` depois que todas as anotações de consenso estiverem
  revisadas, as cinco categorias estiverem presentes no teste e não houver lacunas de cobertura.

## Arquivos

- `manifesto-amostras.json`: identidade por hash, partição e cobertura técnica.
- `criterios-regressao.json`: limites numéricos propostos antes do pipeline semântico.
- `annotation-template.json`: exemplo sintético sem conteúdo de projeto real.
- `schemas/`: descrição pública dos três formatos JSON.
- `POLITICA-ACESSO.md`: regras para corpus e resultados derivados.

As anotações operacionais usam o caminho `annotations/<amostra>/<papel>.json` dentro de um diretório
privado fornecido ao `JsonEvaluationDataset`. Os papéis válidos são `primaria`, `secundaria` e
`consenso`.
