# Roadmap de análise e conformidade

Este roadmap registra apenas capacidades atuais, lacunas observáveis e a ordem recomendada de
implementação. O catálogo detalhado é a fonte única para regras e candidatos.

## Objetivo

Entregar uma revisão semelhante à leitura de um projeto comissionado: apontar no desenho o fato
observado, explicar a expectativa normativa e separar claramente:

- conforme;
- possível divergência;
- não avaliável por falta de contexto ou evidência;
- observação que ainda depende de revisão humana.

Um comentário existente no PDF demonstra o que um revisor procurou naquele caso, mas não cria uma
norma. Toda regra automática precisa de fonte confirmada, aplicabilidade explícita e fatos produzidos
com segurança.

## Situação atual

O motor já possui:

- registro JSON importável e exportável, com revisões imutáveis;
- proteção contra remoção de IDs por importação, persistência ou restauração de backup;
- vocabulário tipado de fatos;
- avaliador de aplicabilidade, exceções e requisitos;
- resultados persistidos e invalidados quando método ou regras mudam;
- controles documentais e fatos regionais/de vão;
- callouts navegáveis entre lista e PDF;
- estados não avaliáveis para informação insuficiente.

As oito regras distribuídas estão descritas em
[`catalogo-regras-conformidade.md`](catalogo-regras-conformidade.md). Algumas permanecem parciais
porque seus fatos ainda não possuem produtor real.

## O que os exemplos mostraram

Em uma revisão local pontual de agosto de 2026, nenhum dos comentários de comissionamento examinados
possuía cobertura operacional integral pelas regras atuais. Um documento fora do domínio ficou
corretamente sem propostas técnicas. Esse retrato orientou as lacunas abaixo, mas não congela o
conteúdo atual de `examples/`.

As principais famílias observadas foram:

- poste, altura, resistência, vão e esforço;
- escolha de estrutura e estai;
- aterramento e espaçamento;
- cabo de tronco e cabo rural coberto;
- consistência entre desenho, orçamento, materiais, potência e fases;
- simbologia de poste;
- presença de documentos e fotografias;
- orientações curtas ou ambíguas que não permitem regra segura.

Os candidatos correspondentes ficam em `REVISAO_HUMANA` no catálogo até a confirmação da fonte e a
implementação dos fatos. Os arquivos em `examples/` podem mudar sem atualizar este documento; novos
achados só alteram o produto quando resultarem em uma decisão técnica concreta.

## Prioridade de implementação

### P0 — evitar conclusões incorretas

- Preservar a exclusão de comentários de revisão da interpretação e dos fatos, sem descartar texto
  técnico AutoCAD SHX.
- Rejeitar altura, engastamento, área e capacidade como comprimento de vão.
- Exigir contexto urbano/rural confirmado ou campo rotulado de cabeçalho.
- Tratar conflito, negação e ausência como não avaliável.
- Manter lógica ternária correta em condições compostas: qualquer dependência desconhecida que ainda
  possa mudar o resultado deve manter o resultado desconhecido.

### P1 — ampliar fatos úteis

- Poste × vão: altura, resistência, cabo, relevo e exceções.
- Estrutura e esforço: ângulo, comprimentos adjacentes, direção do esforço e estai.
- Aterramento: símbolos, situação da obra, continuidade e distância acumulada.
- Consistência documental: materiais, potência, fases e anexos presentes nos dois lados da comparação.
- Cabos: função topológica, tecnologia, seção, fases, contexto e tipo de intervenção.

### P2 — refinamentos

- Comparar símbolo vetorial e rótulo do poste.
- Classificar tipos documentais e anexos de forma positiva.
- Melhorar agrupamento e filtros dos achados na interface.
- Oferecer um fluxo real assíncrono que atravesse lista, página, callout e detalhes sem sessão injetada.

## Regra de vão urbano protegido

O comportamento seguro atual é:

- até 45 m: o limite principal pode ser avaliado normalmente;
- acima de 45 m e até 60 m: sem prova positiva da exceção, o resultado é `NAO_AVALIAVEL`;
- acima de 60 m: a regra diverge, mesmo se houver um marcador de exceção indevido.

A regra permanece parcial enquanto não existir produtor real para a prova excepcional.

## Processo para acrescentar uma regra

1. Identificar a obrigação em uma fonte normativa confirmada.
2. Definir aplicabilidade, exceções e resultado esperado em linguagem simples.
3. Verificar se o PDF ou metadado fornece os fatos sem inferência ambígua.
4. Criar fixtures sintéticas para limites, ausência, conflito e exceções.
5. Implementar o produtor de fatos e só então ativar a regra.
6. Conferir o comportamento em examples locais como exploração, sem fixar o arquivo ao teste.

Se o passo 3 falhar, o item permanece candidato de revisão humana. Isso não bloqueia outras regras e
não exige manifesto, aprovação de corpus ou congelamento de exemplos.

## Fora de escopo imediato

- usar comentários de comissionamento como fonte normativa;
- emitir divergência pela simples ausência de um dado que o scanner não consegue provar aplicável;
- criar um framework genérico de plugins para poucos provedores internos;
- automatizar cálculo mecânico sem entradas e fórmula auditáveis;
- perseguir cobertura nominal de comentários em detrimento da precisão.

## Verificação contínua

O gate padrão usa fixtures sintéticas e não depende de arquivos locais. O script
`scripts/smoke_examples.py`
abre e percorre qualquer PDF presente em `examples/` somente quando solicitado. Uma regressão real
deve ser reduzida ao menor caso sintético que a reproduza antes de entrar no gate permanente.
