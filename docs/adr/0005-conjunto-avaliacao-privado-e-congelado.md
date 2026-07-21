# ADR 0005 - Conjunto de avaliação privado e congelado

## Contexto

O interpretador semântico ainda não existe. Otimizá-lo sem referência congelada permitiria ajustar
regras ao próprio teste e esconder regressões. Os PDFs reais também contêm dados pessoais,
coordenadas e fotografias que não podem acompanhar o código-fonte.

## Decisão

1. O manifesto identifica PDFs somente por ID anônimo e SHA-256 e separa as partições
   `DESENVOLVIMENTO` e `TESTE` antes da criação de regras.
2. PDFs, miniaturas e anotações reais permanecem sob acesso controlado. Git recebe somente contratos,
   critérios, política, metadados anônimos e exemplos sintéticos.
3. Anotações usam geometria normalizada 0..1, categoria, situação, código opcional e relações entre
   IDs locais. Anotadores e revisores são pseudônimos.
4. Amostras designadas recebem anotações primária e secundária independentes. Divergências acima do
   limite exigem adjudicação; apenas o consenso revisado pode ser congelado.
5. A auditoria bloqueia o congelamento se faltar diversidade do corpus, consenso, dupla anotação,
   cobertura das cinco classes ou aprovação dos critérios.
6. O benchmark final recusa manifesto não congelado ou critérios não aprovados. A mesma combinação
   de conjunto, interpretador, regras e configuração deve produzir a mesma assinatura semântica.
7. Precisão, recall e F1 são calculados por classe e para relações. Recursos registram falhas de
   extração, latência p95 e pico de memória rastreada pelo Python.

## Consequências

- A partição final não pode orientar regras da Etapa 6.
- Alterar amostra, anotação de consenso ou critério exige nova versão e novo congelamento.
- `tracemalloc` mede alocações Python, não toda a memória nativa de PyMuPDF/Qt. Um medidor de processo
  poderá substituir essa implementação sem alterar os contratos.
- O corpus atual permanece em preparação porque só possui escala 1:1000 e ainda não recebeu revisão
  humana. Essa pendência é explícita e impede avanço indevido do roadmap.
