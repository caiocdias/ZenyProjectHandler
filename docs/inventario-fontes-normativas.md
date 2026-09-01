# Inventário de fontes normativas da análise de conformidade

Auditoria integral realizada em 12 de agosto de 2026, com revisão complementar dirigida em 14 de
agosto de 2026. O ponto de partida foi o
[portal vigente de normas técnicas de redes de distribuição da CEMIG](https://www.cemig.com.br/normas-tecnicas/normas-tecnicas-de-redes-de-distribuicao/).
Somente documentos publicados pela CEMIG e referências primárias oficiais foram considerados.

## Escopo integral declarado

O escopo integral compreende cinco normas públicas, totalizando **493 páginas**. Ele cobre projeto
urbano, programa rural, instalações compactas e isoladas e proteção de sobrecorrentes. Cada PDF foi
baixado para `tmp/pdfs/etapa2_normas`, fora do Git; o arquivo foi identificado por SHA-256, teve todas
as páginas extraídas para texto indexável com `pypdf` e todas as páginas renderizadas com Poppler a
72 dpi. A revisão humana percorreu as renderizações, inclusive tabelas, figuras, notas e páginas sem
texto extraível.

| Documento | Órgão emissor | Revisão | URL oficial | Acesso | Páginas | SHA-256 da cópia de trabalho | Escopo lido | Situação |
|---|---|---|---|---|---:|---|---|---|
| ND-2.7 — Instalações Básicas de Redes de Distribuição Aéreas Isoladas | CEMIG Distribuição | Nov/2016 | [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/nd_2_7-1.pdf) | 12/08/2026 | 125 | `492e2ea6efa830997aa2d9d5000fb49ac47b2758571ae17d0e9cb781a9159417` | páginas 1–125; texto e imagem | vigente no portal |
| ND-2.9 — Instalações Básicas de Redes de Distribuição Compactas | CEMIG Distribuição | Jun/2016 | [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_2-9-Instalacoes_Basicas_RD_Compactas.pdf) | 12/08/2026 | 117 | `16b9c33173cebf024618591707f4f71d40b0ce46b196e9f17dbda311d3bc9225` | páginas 1–117; texto e imagem | vigente no portal |
| ND-3.1 — Projetos de Redes de Distribuição Aéreas Urbanas | CEMIG Distribuição | Jul/2025 | [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf) | 12/08/2026 | 111 | `ea43a729d3edd5896201b292f6fa385071a3f9d980fa0d82653ef5c637e89b77` | páginas 1–111; texto e imagem | vigente no portal |
| ND-4.15 — Proteção de Sobrecorrentes do Sistema de Distribuição de Média Tensão | CEMIG Distribuição | Nov/2017 | [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/nd_4_15_000001p.pdf) | 12/08/2026 | 77 | `98aff32d7efd0c05adf49a4c8fe7e9f78c42af152305001661306008d91c92e6` | páginas 1–77; texto e imagem | vigente no portal |
| ND-9.3 — Programa Minas Trifásico | CEMIG Distribuição | Set/2021 | [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND-9.3-programa-minas-trifasico.pdf) | 12/08/2026 | 63 | `1dd68cce53d17130723ac1ed3f3460317b5f8c5250f4f932b26fca307a5b12bb` | páginas 1–63; texto e imagem | vigente no portal |

As páginas sem camada textual foram conferidas diretamente nas imagens: ND-2.7, páginas 2, 4, 6,
10, 22, 26, 66, 92, 106, 122 e 124; ND-2.9, páginas 2, 4, 6, 10, 14, 82, 90, 94, 108 e 116;
ND-4.15, páginas 2, 4 e 6; ND-9.3, páginas 4, 16, 18, 20, 58 e 60. A ND-3.1 não teve página vazia
na extração. Páginas com pouco texto, desenhos ou tabelas foram revisadas visualmente mesmo quando a
extração não estava vazia.

## Revisão complementar dirigida — 14 de agosto de 2026

A nova leva local de projetos comissionados motivou uma busca dirigida pelas obrigações rurais e
urbanas sugeridas pelos comentários. Esta revisão não amplia retroativamente o escopo integral de
493 páginas: ela registra exatamente as páginas adicionais lidas por texto e imagem, em cópias
temporárias fora do Git.

| Documento | Órgão emissor | Revisão | URL oficial | Acesso | Páginas do PDF | SHA-256 da cópia de trabalho | Escopo adicional lido | Situação |
|---|---|---|---|---|---:|---|---|---|
| ND-2.2 — Instalações Básicas de Redes de Distribuição Aéreas Rurais | CEMIG Distribuição | Out/2016 | [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/nd_2_2.pdf) | 14/08/2026 | 196 | `483805ecbda3d540de7301825617d34e24c324690cc794e72f5a5de7d1ed6f82` | páginas PDF 14–15, 25, 68–69, 144 e 173–174; texto e imagem | vigente no portal; revisão dirigida, não integral |
| ND-3.1 — Projetos de Redes de Distribuição Aéreas Urbanas | CEMIG Distribuição | Jul/2025 | [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf) | 14/08/2026 | 111 | `ea43a729d3edd5896201b292f6fa385071a3f9d980fa0d82653ef5c637e89b77` | páginas PDF 57–60 e 66–67 revalidadas por texto e imagem | vigente no portal; já pertencente ao escopo integral |

A ND-2.2 confirmou obrigações delimitadas para uso do PRORDR, derivações com tração de RDR,
alternativa com condutor CA e tração de RDU, dimensionamento e escolha de estais, e orientação de
poste duplo T. A ND-3.1 confirmou critérios de aterramento, tipo e reaproveitamento de postes,
cálculo de esforços e resistência de postes com equipamentos. A observação t da página 67 sustenta
as Regras 9 e 10 apenas no subconjunto em que código, fase, situações, associação, resistência e
formato são positivamente resolvidos; material PRFV e engastamento permanecem fora da conclusão.
Os demais localizadores e fatos necessários estão no catálogo incremental; nenhum comentário do
corpus foi tratado como fonte.

## Revisão dirigida ND-5.1 — 1º de setembro de 2026

A E01 do roadmap de correção da interpretação de ramais consultou exclusivamente o
[portal oficial de normas técnicas de conexão da CEMIG](https://www.cemig.com.br/normas-tecnicas/normas-tecnicas-de-conexao/)
e o PDF por ele publicado. A cópia temporária permaneceu em `tmp/pdfs/e01_nd51`, fora do Git.

| Documento | Órgão emissor | Revisão | URL oficial | Acesso | Páginas do PDF | SHA-256 da cópia de trabalho | Escopo dirigido lido | Situação |
|---|---|---|---|---|---:|---|---|---|
| ND-5.1 — Fornecimento de energia elétrica em tensão secundária — rede de distribuição aérea — edificações individuais | CEMIG Distribuição | Mar/2026; vigência em 23/03/2026 | [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/nd5_1_000001p.pdf) | 01/09/2026 | 205 | `ffdbd926d0eb331cd3951227482a94534ae8746bff98bfeb7a50afc298972f75` | páginas PDF 18–20 e 32–35; Tabela 5 na página PDF 68; Tabela 16 na página PDF 80; Desenhos 1, 3, 4 e 59 nas páginas PDF 85, 87, 88 e 162; texto e imagem | vigente no portal; revisão dirigida, não integral |

O número impresso no rodapé fica uma unidade abaixo do número da página PDF nesse recorte. A página
PDF 20 foi incluída como referência indispensável porque completa o item 4.2 iniciado na página PDF
19. A inspeção dirigida confirmou:

- página PDF 18, itens 3.32–3.35: RDA/RDR/RDS/RDU são redes da CEMIG; essas definições sustentam a
  separação de domínio entre a rede de distribuição e o trecho de atendimento ao consumidor;
- páginas PDF 19–20, itens 4.2, 4.2.1.1 e 4.2.1.2: o ponto de conexão do atendimento aéreo fica junto
  ao poste ou pontalete do padrão, ou à parede da edificação, e corresponde à conexão do ramal de
  entrada com o ramal de conexão; a posição rural é tratada explicitamente;
- páginas PDF 32–35, itens 5.1.1–5.1.4.7: aquisição, instalação e manutenção do ramal de conexão são
  responsabilidade da CEMIG; o ramal aéreo é uma modalidade própria, tem comprimento máximo de 30 m
  tanto no caso urbano quanto no rural, usa cabo multiplex e possui sistemas próprios de ancoragem e
  encabeçamento;
- Tabela 5, página PDF 68: relaciona o tipo/faixa de fornecimento ao cabo multiplex do ramal aéreo;
  a tabela foi conferida visualmente, mas E01 não transforma seus valores em regra ativa;
- Tabela 16, página PDF 80: relaciona vão, tração e flecha do ramal multiplex e remete ao Desenho 1;
  não estabelece um limite de deflexão angular;
- Desenho 1, página PDF 85: separa graficamente o ramal de conexão, o ramal de entrada, a entrada de
  serviço e os pontos junto ao padrão; o trecho da rede até o padrão não é um vão poste–poste;
- Desenho 3, página PDF 87: mostra configurações urbanas e rurais com o ponto de conexão no fim do
  ramal aéreo e limite de 30 m;
- Desenho 4, página PDF 88, e Desenho 59, página PDF 162: detalham conexões, alça preformada e ferragens
  de ancoragem próprias do ramal aéreo.

Uma busca textual em todas as 205 páginas por `ângulo`, `deflexão`, `30°` e `30 graus` não localizou
limite angular aplicável ao ramal de conexão; as únicas ocorrências semelhantes eram do termo
“triângulo” em tabelas de partida de motores. Portanto, esta revisão não autoriza aplicar ao ramal o
limite angular ou a matriz estrutura–cabo usados para a rede. Requisitos que dependam das referências
ND-2.1, ND-2.2, ND-2.6, ND-2.7 ou NBR 15688 não foram ampliados por inferência nesta revisão; antes de
automatizá-los, o localizador e os fatos correspondentes precisam de auditoria própria.

Os comentários presentes nos PDFs locais de projetos serviram somente para apontar casos de teste.
Nenhuma obrigação, exceção ou interpretação normativa acima foi derivada desses comentários.

## Confirmação das fontes já citadas

- A ND-3.1 do registro continua publicada no endereço de outubro de 2025, com revisão Jul/2025. Os
  localizadores das Regras 1–5 permanecem nas páginas 66–67 e 88. O item de vão das alíneas b e c
  está na página PDF 27, e não na 26; registro e catálogo foram corrigidos.
- A arquitetura citava a ND-9.3 por um endereço antigo de março de 2022. O portal vigente aponta
  para o endereço de outubro de 2025 acima; o conteúdo consultado identifica revisão Set/2021.

## Referências oficiais diretas seguidas

As referências abaixo foram localizadas a partir das normas do escopo e do próprio portal. As cinco
fontes da primeira tabela foram lidas integralmente. As demais delimitam fontes ainda não cobertas;
a única exceção nesta revisão é o recorte dirigido e explicitamente rastreado da ND-2.2.

| Referência | Situação na última consulta | Decisão nesta etapa |
|---|---|---|
| [ND-2.1 — instalações urbanas](https://www.cemig.com.br/wp-content/uploads/2025/10/nd-2-1-instalacoes-basicas-de-redes-de-distribuicao-aereas-urbanas.pdf) | listada no portal oficial | Fora do escopo integral; necessária para aprofundar rede convencional, posteação e afastamentos antes de novas regras |
| [ND-2.2 — instalações rurais](https://www.cemig.com.br/wp-content/uploads/2025/10/nd_2_2.pdf) | listada no portal oficial; páginas selecionadas revisadas em 14/08/2026 | Continua fora do escopo integral; as obrigações localizadas na revisão dirigida sustentam apenas os candidatos explicitamente citados no catálogo |
| [ND-2.4 — instalações urbanas em 23,1 kV](https://www.cemig.com.br/wp-content/uploads/2025/10/nd-2-4-instalacoes-basicas-de-redes-de-distribuicao-aereas-urbanas-23-1-kv.pdf) | listada no portal oficial | Fora do escopo integral; nenhuma regra criada |
| [ND-2.10 — rede compacta 23,1 kV](https://www.cemig.com.br/wp-content/uploads/2025/10/nd2_10.pdf) | listada no portal oficial | Fora do escopo integral; necessária antes de generalizar matrizes de estruturas compactas |
| [ND-2.13 — linhas e redes rurais 34,5 kV](https://www.cemig.com.br/wp-content/uploads/2025/10/nd-2.13_instalacoes-basicas-linhas-e-redes-de-rdr-345-kV-1.pdf) | listada no portal oficial | Fora do escopo integral; nenhuma regra criada |
| ABNT NBR 15688, 15992, 16615, 9511 e referências IEC/ABNT correlatas | acesso pelo catálogo/licença da ABNT | Conteúdo protegido não contornado nem reproduzido; nenhuma obrigação foi inferida apenas da citação bibliográfica |
| ED-2.9, ED-3.3, ED-3.4, ED-3.6 e relatórios CEMIG marcados como reservados | acesso não público indicado pela própria ND-9.3 | `REVISAO_HUMANA`; nenhuma regra automatizada sem acesso autorizado e rastreabilidade |

## Método de seleção e limites

A busca percorreu sistematicamente presença documental, limites, estruturas, cabos, postes,
equipamentos, proteção, aterramento, vãos, contexto rural/urbano, topologia, cálculos e
compatibilidade. Cada candidato está classificado no catálogo incremental com documento, revisão,
item, página, aplicabilidade, exceções e fatos necessários.

Só entraram no registro condições inequívocas cujos fatos preservam a associação necessária. Por
isso, a tecnologia de cabo novo é publicada separadamente da tecnologia de cabos existentes; a
compatibilidade estrutura–poste só é publicada quando há exatamente uma estrutura MT a instalar e
um poste não removido na região. Ambiguidade ou falta de detector resulta em `NAO_AVALIAVEL`, nunca
em divergência inventada.

Os PDFs e os textos integrais extraídos são cópias temporárias de trabalho e não fazem parte do
repositório. A documentação versionada contém apenas metadados, hashes, localizadores e paráfrases
curtas, preservando os direitos autorais e os controles de acesso das fontes.
