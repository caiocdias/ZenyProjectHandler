# Inventário de fontes normativas da análise de conformidade

Auditoria realizada em 12 de agosto de 2026 para a Etapa 2 do roadmap de conformidades. O ponto de
partida foi o [portal vigente de normas técnicas de redes de distribuição da CEMIG](https://www.cemig.com.br/normas-tecnicas/normas-tecnicas-de-redes-de-distribuicao/).
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

## Confirmação das fontes já citadas

- A ND-3.1 do registro continua publicada no endereço de outubro de 2025, com revisão Jul/2025. Os
  localizadores das Regras 1–5 permanecem nas páginas 66–67 e 88. O item de vão das alíneas b e c
  está na página PDF 27, e não na 26; registro e catálogo foram corrigidos.
- A arquitetura citava a ND-9.3 por um endereço antigo de março de 2022. O portal vigente aponta
  para o endereço de outubro de 2025 acima; o conteúdo consultado identifica revisão Set/2021.

## Referências oficiais diretas seguidas

As referências abaixo foram localizadas a partir das normas do escopo e do próprio portal. As cinco
fontes da primeira tabela foram lidas integralmente. As demais delimitam dependências futuras e não
sustentam regra nova nesta etapa.

| Referência | Situação em 12/08/2026 | Decisão nesta etapa |
|---|---|---|
| [ND-2.1 — instalações urbanas](https://www.cemig.com.br/wp-content/uploads/2025/10/nd-2-1-instalacoes-basicas-de-redes-de-distribuicao-aereas-urbanas.pdf) | listada no portal oficial | Fora do escopo integral; necessária para aprofundar rede convencional, posteação e afastamentos antes de novas regras |
| [ND-2.2 — instalações rurais](https://www.cemig.com.br/wp-content/uploads/2025/10/nd_2_2.pdf) | listada no portal oficial | Fora do escopo integral; dependência futura para aterramento e estaiamento rural |
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
