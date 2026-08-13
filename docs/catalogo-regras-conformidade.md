# Catálogo incremental de regras de conformidade

Fonte humana e auditável das regras distribuídas com o analisador e dos candidatos encontrados na
revisão normativa. O inventário de documentos, hashes e cobertura de páginas está em
`docs/inventario-fontes-normativas.md`.

## Preceito obrigatório

1. Regra incorporada, alterada, inativada ou substituída é atualizada neste arquivo no mesmo commit
   do registro e dos testes.
2. Cada ID técnico recebe um número `Regra N` sequencial e permanente. Números não são apagados nem
   reutilizados.
3. A entrada registra fonte oficial, aplicabilidade, exceções, fatos, resultado, automação e testes.
   Citação incompleta, ambiguidade ou ausência de detector não autorizam divergência.
4. Mudança normativa de obrigação, aplicabilidade ou exceção cria novo ID. Correção de localizador ou
   redação que não muda a obrigação permanece no histórico do mesmo ID.
5. O JSON é declarativo. Geometria, topologia, associação e cálculo ficam em provedores pequenos e
   testáveis que publicam fatos rastreáveis.

Estados da revisão normativa:

- `IMPLEMENTADA`: incorporada ao registro versionado e acompanhada por testes;
- `PRONTA_PARA_REGRA`: obrigação e fatos estão definidos, aguardando incorporação;
- `AGUARDA_FATO`: a obrigação é relevante, mas falta fato confiável ou associação necessária;
- `REVISAO_HUMANA`: validade ou aplicabilidade exige juízo técnico/documental;
- `DESCARTADA`: não deve virar regra nas condições examinadas.

Estados de automação: `OPERACIONAL`, `PARCIAL`, `AGUARDA_FATO`, `INATIVA` e `SUBSTITUIDA`. O estado
da revisão e o de automação são independentes.

## Catálogo local configurável

O SQLite mantém a numeração permanente por ID técnico e snapshots imutáveis do registro. Na
primeira execução, as oito entradas abaixo recebem os números 1 a 8 a partir do seed. A interface
oferece somente importação e exportação. Importar gera atomicamente outro catálogo Markdown na pasta
de dados do usuário; pode alterar o estado `enabled` declarado por um ID, mas nunca remove regras
omitidas do arquivo. Este arquivo versionado documenta o seed; ações da interface não o modificam
silenciosamente.

## Resumo

| Número | ID técnico | Título | Registro | Automação | Revisão normativa |
|---|---|---|---|---|---|
| Regra 1 | `nd31.desenho.numero-projeto` | Número do projeto com 10 dígitos | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 2 | `nd31.desenho.formato` | Formato de folha padronizado | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 3 | `nd31.desenho.escala` | Escala urbana de apresentação | INATIVA | INATIVA | AGUARDA_FATO |
| Regra 4 | `nd31.equipamento.estrutura-angulo` | Equipamento em estrutura de ângulo | ATIVA | AGUARDA_FATO | IMPLEMENTADA |
| Regra 5 | `nd31.equipamento.risco-abalroamento` | Avaliação de risco no ângulo | ATIVA | AGUARDA_FATO | IMPLEMENTADA |
| Regra 6 | `nd31.vao.urbano-compacto-isolado` | Vão máximo urbano | ATIVA | PARCIAL | IMPLEMENTADA |
| Regra 7 | `nd31.cabo.convencional-novo-urbano` | Cabo nu convencional em obra nova urbana | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 8 | `nd93.compatibilidade.estrutura-poste-duplo-t` | Estrutura compacta rural e poste duplo T | ATIVA | OPERACIONAL | IMPLEMENTADA |

## Regras existentes

### Regra 1 - Número do projeto com 10 dígitos

- **ID:** `nd31.desenho.numero-projeto`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 2.4, página PDF
  88, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** projeto com contexto urbano positivamente identificado.
- **Fatos:** `rede.contexto_urbano`; `projeto.nota_servico`. O extrator aceita somente dez dígitos.
- **Condição:** número válido presente resulta conforme; contexto conhecido sem número válido pode
  resultar em divergência; contexto desconhecido é não avaliável.
- **Exceções:** nenhuma na obrigação examinada.
- **Testes:** presença válida, ausência e contexto desconhecido.

### Regra 2 - Formato de folha padronizado

- **ID:** `nd31.desenho.formato`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 2.3, página PDF
  88, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** projeto urbano.
- **Fatos:** `rede.contexto_urbano`; `projeto.formato_folha`, obtido de cabeçalho/metadado ou das
  dimensões físicas da página.
- **Condição:** `A1`, `A2`, `A3` ou `A4`; dado ausente é não avaliável.
- **Exceções:** nenhuma na obrigação examinada.
- **Testes:** formatos permitidos, formato inválido e dado ausente.

### Regra 3 - Escala urbana de apresentação

- **ID:** `nd31.desenho.escala`.
- **Estado:** `AGUARDA_FATO`; registro preservado, porém `INATIVA` após a revisão integral.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 2.1, página PDF
  88, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** projeto urbano ordinário.
- **Fatos:** `rede.contexto_urbano`; `projeto.escala`; faltam
  `projeto.escala_500_caso_extraordinario` e `projeto.escala_orgao_externo_aplicavel`.
- **Condição:** a regra geral usa 1:1000. A revisão constatou que 1:500 depende de caso urbano
  extraordinário e que órgãos externos podem determinar outra escala.
- **Exceções:** caso extraordinário e escala indicada pelo órgão competente precisam de prova
  positiva. Sem esses fatos, uma divergência automática poderia ser falsa.
- **Testes antes de reativar:** regra geral, cada exceção, escala inválida e fatos ausentes.

### Regra 4 - Equipamento em estrutura de ângulo

- **ID:** `nd31.equipamento.estrutura-angulo`.
- **Estado:** `IMPLEMENTADA`; automação `AGUARDA_FATO`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, observação j,
  páginas PDF 66–67, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** equipamento não fusível a instalar em região com conexão reconhecida.
- **Fatos:** `regiao.equipamento_instalar`; `regiao.equipamento_classe`;
  `conexao.angulo_graus`.
- **Condição:** deflexão acima de 30 graus produz possível divergência; ângulo ausente é não
  avaliável.
- **Exceções:** chave fusível fica fora da aplicabilidade; até 30 graus depende também da Regra 5.
- **Testes:** chave fusível, até/acima do limite e ângulo ausente.

### Regra 5 - Avaliação de risco de abalroamento no ângulo

- **ID:** `nd31.equipamento.risco-abalroamento`.
- **Estado:** `IMPLEMENTADA`; automação `AGUARDA_FATO`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, observação j,
  páginas PDF 66–67, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** equipamento não fusível a instalar, com deflexão maior que zero e de até 30
  graus.
- **Fatos:** os da Regra 4 e `regiao.risco_abalroamento_avaliado`.
- **Condição:** evidência positiva permite concluir conforme. A falta de evidência publicada é não
  avaliável, pois não comprova que a avaliação inexiste.
- **Exceções:** chave fusível e conexões fora da faixa declarada.
- **Testes:** evidência presente, ausente, chave fusível, faixa e ângulo desconhecido.

### Regra 6 - Vão máximo de rede compacta ou isolada urbana

- **ID:** `nd31.vao.urbano-compacto-isolado`.
- **Estado:** `IMPLEMENTADA`; automação `PARCIAL`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Locação de Postes”, item 3, alíneas b e c,
  página PDF 27, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** região urbana com cabo protegido ou isolado.
- **Fatos:** `rede.contexto_urbano`; `cabo.tecnologia`; `vao.comprimento_m`;
  `vao.aplicabilidade_excecao_45_60_resolvida`; `vao.excecao_45_60_demonstrada`.
- **Condição:** até 45 m resulta conforme; acima de 60 m produz possível divergência. Sem
  comprimento rastreável, o resultado é não avaliável. Acima de 45 m e até 60 m, a regra só é
  aplicável quando as condições excepcionais foram positivamente resolvidas; sem essa prova, fica não
  avaliável, nunca divergente por mera ausência de evidência.
- **Exceções:** acima de 45 m e até 60 m somente com contexto periférico/baixa densidade ou chácaras, perfil favorável
  e demais condições positivamente demonstradas.
- **Processo automático:** `detectar_vaos` fornece a medida já materializada no cabo. O provedor liga
  o cabo confirmado à região pela decisão de revisão, conserva `ANOTACAO_DESENHO`, `COORDENADAS` ou
  `INFORMADO`, ancora anotação no rótulo e coordenadas na geometria do cabo. A exceção só é publicada
  para medida acima de 45 m e de até 60 m, com indicador positivo e evidência existente na mesma
  página. Fora dessa faixa, a aplicabilidade é resolvida pelo comprimento. Dentro dela, sem produtor
  real da prova excepcional, o fato de aplicabilidade não é publicado e o resultado é não avaliável.
- **Histórico:** localizador corrigido de página 26 para 27 em 12/08/2026, sem mudar a obrigação.
- **Testes:** medida anotada, medida por coordenadas, limites 45/60, acima de 60 m mesmo com marcador
  indevido, tecnologia não aplicável, exceção positiva, comprimento ausente, região/página/geometria,
  migração seletiva do seed anterior e E2E com callout e persistência.

### Regra 7 - Cabo nu convencional em obra nova urbana

- **ID:** `nd31.cabo.convencional-novo-urbano`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Tipos de Rede e Critérios de Aplicação”, item
  1.1.3, página PDF 18, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** cabo catalogado como instalação em região urbana confirmada.
- **Fatos:** `rede.contexto_urbano`; `cabo.instalar_tecnologia`. O fato novo mantém a situação da
  proposta associada à tecnologia, sem misturar cabo existente e cabo novo da mesma região.
- **Condição:** qualquer instalação com tecnologia `CONVENCIONAL_CA`, `CONVENCIONAL_CA_CAA` ou
  `CONVENCIONAL_CAA` produz possível divergência; protegida ou isolada resulta conforme.
- **Exceções:** reparo com cabo nu. Propostas `EXISTENTE` ou `REMOVER` não publicam o fato de
  instalação; contexto não urbano fica fora da regra.
- **Testes:** conforme, divergência, tecnologia ausente e contexto não urbano/reparo.

### Regra 8 - Estrutura compacta rural incompatível com poste duplo T

- **ID:** `nd93.compatibilidade.estrutura-poste-duplo-t`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL` no pareamento inequívoco.
- **Citação exata:** CEMIG ND-9.3, Set/2021, “Instalações Básicas de Rede Compacta em Áreas
  Rurais”, seção “Estruturas”, nota 2, página PDF 43,
  [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND-9.3-programa-minas-trifasico.pdf).
- **Aplicabilidade:** região rural confirmada com exatamente uma estrutura MT a instalar de código
  `CE1`, `CE1S`, `CEJ1`, `CEJ2` ou `CEM4` e exatamente um poste não removido.
- **Fatos:** `rede.contexto_rural`; `regiao.estrutura_mt_instalar_codigo`;
  `regiao.poste_ativo_formato`.
- **Condição:** formato `DUPLO_T` produz possível divergência; outro formato resulta conforme.
- **Exceções:** estrutura fora da lista, contexto não rural ou associação ambígua. Ambiguidade não
  publica os fatos de compatibilidade e retorna não avaliável.
- **Testes:** poste circular, poste duplo T, poste ausente/ambíguo e contexto não rural.

## Matriz de candidatos da revisão integral

Os localizadores abaixo são citações bibliográficas exatas; as descrições são paráfrases curtas. Um
candidato `IMPLEMENTADA` aponta para a regra correspondente. Os demais não produzem divergência.

| Candidato e tema | Citação exata | Aplicabilidade | Exceções/condições | Fatos necessários | Estado |
|---|---|---|---|---|---|
| `DOC-01` conjunto documental | ND-3.1 Jul/2025, Apresentação do Projeto, item 1, p. 88 | todo projeto urbano | complementares somente quando cabíveis | desenho, relação de materiais/orçamento, memória elétrica e mecânica, tipo de complemento | AGUARDA_FATO |
| `DOC-02` detalhes do desenho | ND-3.1 Jul/2025, Apresentação do Projeto, itens 2.5–2.7, pp. 88–93 | conforme o tipo de obra e travessia | detalhes variam por instalação e órgão | campos estruturados, geometria, travessia, validade e autoria | REVISAO_HUMANA |
| `LIM-01` escala e suas exceções | ND-3.1 Jul/2025, Apresentação do Projeto, item 2.1, p. 88 | projeto urbano | caso extraordinário ou escala de órgão competente | escala, tipo do caso, órgão e determinação documental | AGUARDA_FATO |
| `POST-01` comprimento mínimo em expansão | ND-3.1 Jul/2025, Dimensionamento Mecânico, item 1.2, p. 59 | poste novo em projeto de expansão | situações que exigem poste maior; instalações sem previsão de MT têm arranjo próprio | tipo de projeto, poste associado, altura, previsão MT e situação especial | AGUARDA_FATO |
| `STRUCT-01` escolha por esforço/ângulo | ND-3.1 Jul/2025, Dimensionamento Mecânico, item 2 e tabelas 22–33, pp. 70–78 | estrutura urbana dimensionada | rede, cabo, seção, tensão, direção e ancoragem alteram a tabela | estrutura, pares de vãos, ângulos, cabo, poste, vento e esforços | AGUARDA_FATO |
| `CABLE-01` cabo nu em instalação urbana | ND-3.1 Jul/2025, Tipos de Rede, item 1.1.3, p. 18 | obra nova urbana | reparo | contexto e tecnologia por proposta de instalação | IMPLEMENTADA — Regra 7 |
| `EQUIP-01` equipamento em ângulo | ND-3.1 Jul/2025, Dimensionamento Mecânico, observação j, pp. 66–67 | equipamento não fusível a instalar | chave fusível; até 30° exige avaliação de abalroamento | classe, situação, conexão, ângulo e avaliação | IMPLEMENTADA — Regras 4 e 5 |
| `PROT-01` proteção de transformador e elo | ND-3.1 Jul/2025, Dimensionamento Elétrico, item 2.2.7 e Tabela 8, pp. 48–51; ND-4.15 Nov/2017, capítulos 5–8, pp. 20–74 | rede MT e dispositivo especificados | filosofia, carga, inrush, curto e coordenação mudam o ajuste | topologia, potência, tensão, correntes, curvas, dispositivos a montante/jusante | AGUARDA_FATO |
| `GROUND-01` aterramento urbano | ND-3.1 Jul/2025, Dimensionamento Elétrico, item 7, p. 57 | neutro, rede compacta/isolada e equipamentos conforme o caso | para-raios e pontos já existentes alteram o arranjo | continuidade, distância acumulada, hastes, mensageiro, neutro, equipamento e conexão | AGUARDA_FATO |
| `SPAN-U01` vão urbano compacto/isolado | ND-3.1 Jul/2025, Locação de Postes, item 3, p. 27 | rede urbana protegida/isolada | faixa 45–60 m com fatos positivos | contexto, tecnologia, comprimento, perfil e exceção | PARCIAL — Regra 6 |
| `SPAN-R01` vãos rurais | ND-9.3 Set/2021, Projetos de RDP Compactas em Áreas Rurais, seção “Vão”, itens 1–5 e Tabelas 2–3, pp. 24–25 | rede rural compacta | travessia, topografia, compartilhamento e análise técnica | cabo/seção, poste/altura/resistência, relevo, ângulo, compartilhamento e cálculo mecânico | AGUARDA_FATO |
| `RURAL-01` contexto e traçado | ND-9.3 Set/2021, capítulos 5–7, pp. 19–40 | projeto do Programa Minas Trifásico | urbano, faixa de domínio, licenciamento e planejamento alteram o fluxo | classificação rural/urbana, traçado, servidão, relevo, vento, demanda e autorizações | REVISAO_HUMANA |
| `COMP-01` estruturas compactas e poste duplo T | ND-9.3 Set/2021, capítulo 8, “Estruturas”, nota 2, p. 43 | estrutura compacta indicada em região rural | códigos fora da lista e associação ambígua | contexto, estrutura instalada e formato do poste associado | IMPLEMENTADA — Regra 8 |
| `COMP-02` matriz estrutura–cabo | ND-2.7 Nov/2016, capítulos 3–10, pp. 27–121; ND-2.9 Jun/2016, capítulos 3–12, pp. 19–114 | instalação isolada ou compacta específica | desenhos, nível, fase, seção, derivação, transição e equipamento | IDs normativos, relação elemento–região e matriz oficial normalizada | AGUARDA_FATO |
| `TOPO-01` coordenação e seletividade | ND-4.15 Nov/2017, capítulos 5–8, pp. 20–74 | sistema MT com proteção em série | filosofia e dispositivos variam por alimentador | grafo elétrico, correntes de falta/carga, curvas, ajustes e sequência operacional | REVISAO_HUMANA |
| `CALC-01` queda de tensão | ND-3.1 Jul/2025, Dimensionamento Elétrico, item 3 e tabelas 10–14, pp. 52–55 | circuito dimensionado | limite depende de subestação AT/MT e cenário de carga/geração | topologia, demanda, distância, condutor, transformador, tensão e cenário | AGUARDA_FATO |
| `ABS-01` reprovar por ausência de carimbo, assinatura visual ou símbolo não detectado | ND-3.1 Jul/2025, Apresentação do Projeto, pp. 88–93 | não estabelecida de forma universal pelo detector | autenticidade, formato e exigência contratual variam | seria necessário provar obrigação e cobertura do detector | DESCARTADA |

### Lacunas observadas nos exemplos de comissionamento

A revisão agregada dos cinco PDFs iniciais encontrou famílias recorrentes que ainda não possuem
cobertura operacional. Os comentários de comissionamento servem apenas para priorizar investigação:
não são fonte normativa, não comprovam uma obrigação universal e não autorizam criar divergências.
Por isso, os candidatos abaixo permanecem em `REVISAO_HUMANA` até que uma fonte oficial, seu
localizador exato, a aplicabilidade e as exceções sejam confirmados. Somente depois podem passar a
`AGUARDA_FATO` e receber provedores.

Além dos sete candidatos novos abaixo, as observações também reforçam lacunas já catalogadas em
`DOC-01`, `DOC-02`, `POST-01`, `STRUCT-01`, `GROUND-01`, `SPAN-R01`, `COMP-02`, `PROT-01` e
`TOPO-01`. Instruções genéricas de ajuste de ramal e notas curtas ou ambíguas permanecem em revisão
humana até que tenham semântica inequívoca, aplicabilidade e fonte normativa oficial.

| Candidato e lacuna | Fonte normativa | Escopo a confirmar | Fatos necessários antes de automatizar | Estado |
|---|---|---|---|---|
| `COER-01` coerência desenho↔orçamento/relação de materiais | não confirmada; comentários dos exemplos não são fonte | documentos que descrevem a mesma revisão de obra | identidade e revisão documental, código, quantidade, situação e associação inequívoca do item | REVISAO_HUMANA |
| `COER-02` potência de transformador no desenho↔orçamento | não confirmada; comentários dos exemplos não são fonte | transformador representado e item orçado da mesma revisão | identidade do equipamento, potência com unidade, situação, versões e associação entre documentos | REVISAO_HUMANA |
| `COER-03` número de fases coerente entre desenho e documentos complementares | não confirmada; comentários dos exemplos não são fonte | trecho/circuito e documentos da mesma revisão | circuito, trecho, fases, tensão, situação, versões e proveniência por documento | REVISAO_HUMANA |
| `CABLE-BT-01` cabo de baixa tensão do tronco | não confirmada; comentários dos exemplos não são fonte | trecho BT inequivocamente classificado como tronco | topologia, função do trecho, tecnologia, material, seção, fases, situação e exceções | REVISAO_HUMANA |
| `CABLE-R-01` emprego de cabo coberto em contexto rural | não confirmada para a condição percebida; comentários dos exemplos não são fonte | trecho rural e classe de obra ainda a delimitar | contexto rural explícito, tecnologia, seção, tensão, situação, ambiente e exceções | REVISAO_HUMANA |
| `SYMB-POST-01` simbologia de poste coerente com sua especificação | não confirmada; comentários dos exemplos não são fonte | poste inequivocamente identificado no desenho e nos documentos associados | símbolo, tipo, material, altura, resistência, situação, legenda e associação geométrica | REVISAO_HUMANA |
| `DOC-PRODR-01` PRODR e registro fotográfico | não confirmada; `DOC-01`/`DOC-02` não estabelecem sozinhos essa obrigação específica | tipo de obra, fase do processo e pacote documental a delimitar | exigência aplicável, tipo documental, identidade do projeto, data, autoria, completude e vínculo entre fotos e alvos | REVISAO_HUMANA |

## Regra para futuras incorporações

Uma entrada `AGUARDA_FATO` só avança após o fato preservar unidade, situação, alvo, associação e
proveniência. Depois são exigidos casos sintéticos de conforme, divergência, não avaliável e cada
exceção aplicável, além da paridade automática entre este catálogo e o registro.
