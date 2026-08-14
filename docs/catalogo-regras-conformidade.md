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
primeira execução, as dez entradas abaixo recebem os números 1 a 10 a partir do seed. A interface
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
| Regra 9 | `nd31.transformador.poste-existente-30-75` | Poste existente para transformador trifásico de 30 a 75 kVA | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 10 | `nd31.transformador.poste-existente-150-300` | Poste existente para transformador trifásico de 150 ou 300 kVA | ATIVA | OPERACIONAL | IMPLEMENTADA |

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
- **Revisão em 14/08/2026:** uma folha exploratória contém mais de uma escala associada a vistas
  diferentes. Antes de reativar a regra, o fato deve preservar vista/região; uma única string global
  pode produzir falso positivo.
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
- **Limite revisto em 14/08/2026:** o alvo ainda é a região. Antes de avaliar uma região que reúna
  vários vãos, comprimento, tecnologia e prova excepcional precisam conservar a associação por vão;
  uma exceção positiva de 45–60 m não pode suprimir a análise de outro vão, sobretudo acima de 60 m.
  Vãos rurais não entram nesta regra.
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
- **Revisão em 14/08/2026:** as novas folhas reforçam que cabos existentes, removidos e instalados
  podem coexistir na mesma área; a situação deve permanecer associada à tecnologia de cada trecho.
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
- **Limite revisto em 14/08/2026:** a regra cobre somente a incompatibilidade listada com poste
  duplo T. Uma crítica de escolha entre duas estruturas rurais não é resolvida por esta regra; um
  resultado `CONFORME` aqui não aprova a escolha geral da estrutura.
- **Testes:** poste circular, poste duplo T, poste ausente/ambíguo e contexto não rural.

### Regra 9 - Poste existente para transformador trifásico de 30 a 75 kVA

- **ID:** `nd31.transformador.poste-existente-30-75`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL` no subconjunto representável.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, item 1.3.2,
  observação t, página PDF 67,
  [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** região urbana com um transformador trifásico de código exato `-3-30`,
  `-3-45` ou `-3-75` a instalar, ligado por uma única relação confirmada a um único poste existente
  na mesma região. A situação existente do poste precisa estar positivamente sustentada pela
  simbologia; o valor padrão do interpretador não basta.
- **Fatos:** `regiao.transformador_trifasico_poste_existente_avaliavel`;
  `regiao.transformador_potencia_kva`; `regiao.poste_transformador_resistencia_dan`;
  `regiao.poste_transformador_formato`.
- **Condição:** capacidade nominal mínima de 300 daN e formato `DUPLO_T` ou `CIRCULAR`.
  Resistência insuficiente ou formato `MADEIRA` conhecido produz possível divergência.
- **Limite:** o resultado atesta somente a parcela automatizável da observação t. O catálogo não
  distingue material PRFV, concreto e formato do topo; formato escolhido canonicamente, relação
  ambígua ou situação não comprovada deixam a regra não avaliável.
- **Testes:** limites de resistência, circular/duplo T/madeira, potência exata, contexto rural,
  situação sem prova, formato inferido, proveniência e cardinalidade 1:1.

### Regra 10 - Poste existente para transformador trifásico de 150 ou 300 kVA

- **ID:** `nd31.transformador.poste-existente-150-300`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL` no subconjunto representável.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, item 1.3.2,
  observação t, página PDF 67,
  [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** as mesmas salvaguardas da Regra 9, para códigos exatos `-3-150` e `-3-300`.
- **Fatos:** os mesmos quatro fatos correlacionados da Regra 9.
- **Condição:** capacidade nominal mínima de 600 daN e formato `CIRCULAR`. Poste duplo T, madeira
  ou resistência inferior, quando positivamente identificados, produzem possível divergência.
- **Limite:** `CIRCULAR` prova a seção representada no catálogo, não o material PRFV/concreto nem o
  engastamento. A ausência dessa prova resulta não avaliável, ainda que a resistência esteja
  disponível.
- **Testes:** capacidades 300/600 daN, circular/duplo T, potência exata, formato inferido,
  associação ambígua e fatos ausentes.

## Matriz de candidatos das revisões normativa e dirigida

Os localizadores abaixo são citações bibliográficas exatas; as descrições são paráfrases curtas. Um
candidato `IMPLEMENTADA` aponta para a regra correspondente. Os demais não produzem divergência.

| Candidato e tema | Citação exata | Aplicabilidade | Exceções/condições | Fatos necessários | Estado |
|---|---|---|---|---|---|
| `DOC-01` conjunto documental | ND-3.1 Jul/2025, Apresentação do Projeto, item 1, p. 88 | todo projeto urbano | complementares somente quando cabíveis | desenho, relação de materiais/orçamento, memória elétrica e mecânica, tipo de complemento | AGUARDA_FATO |
| `DOC-02` detalhes do desenho | ND-3.1 Jul/2025, Apresentação do Projeto, itens 2.5–2.7, pp. 88–93 | conforme o tipo de obra e travessia | detalhes variam por instalação e órgão | campos estruturados, geometria, travessia, validade e autoria | REVISAO_HUMANA |
| `LIM-01` escala e suas exceções | ND-3.1 Jul/2025, Apresentação do Projeto, item 2.1, p. 88 | projeto urbano | caso extraordinário ou escala de órgão competente | escala, tipo do caso, órgão e determinação documental | AGUARDA_FATO |
| `POST-01` comprimento mínimo em expansão | ND-3.1 Jul/2025, Dimensionamento Mecânico, item 1.2, p. 59 | poste novo em projeto de expansão | situações que exigem poste maior; instalações sem previsão de MT têm arranjo próprio | tipo de projeto, poste associado, altura, previsão MT e situação especial | AGUARDA_FATO |
| `POST-TYPE-U01` tipo, substituição e reaproveitamento de poste urbano | ND-3.1 Jul/2025, Dimensionamento Mecânico, itens 1.1–1.2, pp. 58–59 | expansão, reforma ou troca de poste em área urbana | PRFV depende de acesso/abalroamento; situação existente não equivale a reaproveitamento de poste removido | contexto, classe da obra, situação individual, tipo/material, acesso, risco e vínculo entre poste retirado e proposto | AGUARDA_FATO |
| `POST-EQUIP-U01` resistência do poste associado a equipamento | ND-3.1 Jul/2025, Dimensionamento Mecânico, observações r–u, p. 67 | equipamento em extensão nova ou transformador em posteação existente/reforma | mínimos variam por tipo, potência, material/formato e necessidade de troca | situação da obra, equipamento, potência, poste associado, resistência, material e formato | PARCIAL — Regras 9 e 10 cobrem transformadores trifásicos a instalar em posteação existente; extensão nova, troca de poste, PRFV e engastamento aguardam fatos |
| `STRUCT-01` escolha por esforço/ângulo | ND-3.1 Jul/2025, Dimensionamento Mecânico, item 1.3.1, pp. 59–60, e item 2/tabelas 22–33, pp. 66–78 | estrutura urbana dimensionada | rede, cabo, seção, tensão, direção, telecomunicações e ancoragem alteram o cálculo | estrutura, pares de vãos, ângulos, cabos, poste, vento, cargas e esforço resultante | AGUARDA_FATO |
| `CABLE-01` cabo nu em instalação urbana | ND-3.1 Jul/2025, Tipos de Rede, item 1.1.3, p. 18 | obra nova urbana | reparo | contexto e tecnologia por proposta de instalação | IMPLEMENTADA — Regra 7 |
| `EQUIP-01` equipamento em ângulo | ND-3.1 Jul/2025, Dimensionamento Mecânico, observação j, pp. 66–67 | equipamento não fusível a instalar | chave fusível; até 30° exige avaliação de abalroamento | classe, situação, conexão, ângulo e avaliação | IMPLEMENTADA — Regras 4 e 5 |
| `PROT-01` proteção de transformador e elo | ND-3.1 Jul/2025, Dimensionamento Elétrico, item 2.2.7 e Tabela 8, pp. 48–51; ND-4.15 Nov/2017, capítulos 5–8, pp. 20–74 | rede MT e dispositivo especificados | filosofia, carga, inrush, curto e coordenação mudam o ajuste | topologia, potência, tensão, correntes, curvas, dispositivos a montante/jusante | AGUARDA_FATO |
| `GROUND-01` aterramento urbano | ND-3.1 Jul/2025, Dimensionamento Elétrico, item 7, p. 57 | neutro, rede compacta/isolada e equipamentos conforme o caso | neutro a aproximadamente 200 m; aterramento temporário da compacta a aproximadamente 160 m; para-raios e pontos existentes alteram o arranjo | continuidade, distância acumulada, hastes, mensageiro, neutro, equipamento, conexão e tipo de aterramento | AGUARDA_FATO |
| `SPAN-U01` vão urbano compacto/isolado | ND-3.1 Jul/2025, Locação de Postes, item 3, p. 27 | rede urbana protegida/isolada | faixa 45–60 m com fatos positivos | contexto, tecnologia, comprimento, perfil e exceção | PARCIAL — Regra 6 |
| `SPAN-R01` vãos rurais | ND-9.3 Set/2021, Projetos de RDP Compactas em Áreas Rurais, seção “Vão”, itens 1–5 e Tabelas 2–3, pp. 24–25; ND-2.2 Out/2016, Introdução, pp. 14–15 | rede rural conforme tecnologia e classe | travessia, topografia, compartilhamento, condutor e autorização técnica alteram limites | cabo/seção, classe RDR, poste/altura/resistência, relevo, ângulo, compartilhamento, autorização e cálculo mecânico | AGUARDA_FATO |
| `RURAL-PRODR-01` uso do PRORDR | ND-2.2 Out/2016, Introdução, Notas Gerais, nota 4, p. 14 | projeto rural com extensão acima de 300 m | em locais difíceis para estais deve ser escolhida a opção própria sem estais laterais | contexto, extensão total, programa/memória utilizada, terreno e alternativa selecionada | AGUARDA_FATO |
| `RURAL-DERIV-01` estai ou tração RDU em derivação | ND-2.2 Out/2016, Derivações, Notas Gerais, notas 2–3, p. 68 | estrutura de derivação rural com tração de RDR | sem estai contrário, a alternativa exige condutor CA, tração de RDU, vão de até 80 m e poste dimensionado para vento máximo | topologia da derivação, tração, condutor, vão, estai, esforço, vento, poste e memória de cálculo | AGUARDA_FATO |
| `RURAL-STAY-01` escolha e dimensionamento de estais rurais | ND-2.2 Out/2016, Estaiamento, notas 5 e 9–15, p. 144, e Gráficos, notas 4–11, pp. 173–174 | estrutura rural sujeita a esforço e condição de terreno conhecidos | capacidade, solo, declive, risco agrícola e alternativa sem estai lateral mudam o arranjo; esta última exige poste um metro maior | esforços lateral/longitudinal, vento, vãos adjacentes, solo, declive, risco, tipo/capacidade do estai, poste e engastamento | AGUARDA_FATO |
| `POST-ORIENT-R01` orientação de poste duplo T rural | ND-2.2 Out/2016, Primário, Notas Gerais, notas 7–10, p. 25 | poste duplo T rural em alinhamento, deflexão ou fim de rede | orientação varia por faixa angular, maior vão/esforço, fase e presença de estai longitudinal | formato, ângulo, direção dos vãos, esforços, fim de rede, fases, estais e orientação geométrica do poste | AGUARDA_FATO |
| `RURAL-01` contexto e traçado | ND-9.3 Set/2021, capítulos 5–7, pp. 19–40 | projeto do Programa Minas Trifásico | urbano, faixa de domínio, licenciamento e planejamento alteram o fluxo | classificação rural/urbana, traçado, servidão, relevo, vento, demanda e autorizações | REVISAO_HUMANA |
| `COMP-01` estruturas compactas e poste duplo T | ND-9.3 Set/2021, capítulo 8, “Estruturas”, nota 2, p. 43 | estrutura compacta indicada em região rural | códigos fora da lista e associação ambígua | contexto, estrutura instalada e formato do poste associado | IMPLEMENTADA — Regra 8 |
| `COMP-02` matriz estrutura–cabo | ND-2.7 Nov/2016, capítulos 3–10, pp. 27–121; ND-2.9 Jun/2016, capítulos 3–12, pp. 19–114 | instalação isolada ou compacta específica | desenhos, nível, fase, seção, derivação, transição e equipamento | IDs normativos, relação elemento–região e matriz oficial normalizada | AGUARDA_FATO |
| `TOPO-01` coordenação e seletividade | ND-4.15 Nov/2017, capítulos 5–8, pp. 20–74 | sistema MT com proteção em série | filosofia e dispositivos variam por alimentador | grafo elétrico, correntes de falta/carga, curvas, ajustes e sequência operacional | REVISAO_HUMANA |
| `CALC-01` queda de tensão | ND-3.1 Jul/2025, Dimensionamento Elétrico, item 3 e tabelas 10–14, pp. 52–55 | circuito dimensionado | limite depende de subestação AT/MT e cenário de carga/geração | topologia, demanda, distância, condutor, transformador, tensão e cenário | AGUARDA_FATO |
| `ABS-01` reprovar por ausência de carimbo, assinatura visual ou símbolo não detectado | ND-3.1 Jul/2025, Apresentação do Projeto, pp. 88–93 | não estabelecida de forma universal pelo detector | autenticidade, formato e exigência contratual variam | seria necessário provar obrigação e cobertura do detector | DESCARTADA |

### Lacunas observadas nos exemplos de comissionamento

A revisão de 14/08/2026 encontrou dez PDFs locais de uma página e 51 anotações textuais `FreeText`.
Como os arquivos são ignorados pelo Git, a identificação da nova leva é inferencial: quatro folhas
atuais reproduzem as 20 anotações e as famílias da revisão anterior, enquanto seis folhas somam 31
anotações adicionais. Nenhum dos dez hashes corresponde ao manifesto formal de nove amostras.

Os comentários de comissionamento servem apenas para priorizar investigação: não são fonte
normativa, não comprovam obrigação universal e não autorizam criar divergências. A revisão dirigida
da ND-2.2 e a revalidação da ND-3.1 permitiram acrescentar à matriz os candidatos normativos
`POST-TYPE-U01`, `POST-EQUIP-U01`, `RURAL-PRODR-01`, `RURAL-DERIV-01`, `RURAL-STAY-01` e
`POST-ORIENT-R01`. A revisão posterior dos fatos já materializados promoveu dois subconjuntos de
`POST-EQUIP-U01` às Regras 9 e 10. O provedor só publica o par quando contexto, potência trifásica,
situações, relação confirmada e cardinalidade 1:1 são inequívocos; os demais candidatos continuam em
`AGUARDA_FATO`.

A topologia confirmada já permite observar cabos, extremos, postes e comprimentos, mas isso não
torna universais as condições rurais sugeridas pelos comentários. O limite de 80 m da ND-2.2,
página 68, só integra a alternativa sem estai contrário, com cabo CA sob tração de RDU e poste
dimensionado para vento máximo. Do mesmo modo, a norma não estabelece 11 m/300 daN como aprovação
universal de toda derivação trifásica. Sem tração, estai, esforço e memória mecânica, essas duas
formulações foram recusadas para evitar falsos positivos; os fatos topológicos continuam úteis como
diagnóstico e futura aplicabilidade composta.

As observações também reforçam `DOC-01`, `DOC-02`, `POST-01`, `STRUCT-01`, `GROUND-01`,
`SPAN-R01`, `COMP-02`, `PROT-01` e `TOPO-01`. A indicação isolada de aterramento a cada 250 m não foi
incorporada: a ND-3.1 vigente estabelece aproximadamente 200 m para o neutro urbano. Notas curtas,
ajustes genéricos e critérios dependentes de documentos externos permanecem em revisão humana.

### Resultado da revisão das oito regras preexistentes

| Regras | Resultado em 14/08/2026 | Decisão |
|---|---|---|
| 1 e 2 | as folhas reconhecidas continuam nos formatos A3/A4 e não alteram as obrigações de número e formato | manter; a Regra 2 continua conservadora quando um formato inválido não é reconhecido pelo extrator |
| 3 | foi observada folha com escalas distintas por vista/região | manter inativa até modelar escala associada, não uma string global |
| 4 e 5 | comentários de ângulo/equipamento não fornecem ângulo calculado nem avaliação de risco | manter em `AGUARDA_FATO`; comentários de revisão ficam excluídos da semântica |
| 6 | os grandes vãos observados são rurais e dependem de cálculo, tração e estai; não pertencem ao limite urbano | manter parcial e urbana; corrigir associação por vão antes de confiar em região com vários vãos |
| 7 | coexistem cabos existentes, removidos e a instalar na mesma folha | manter; preservar situação por trecho e ampliar regressão sintética antes de qualquer mudança no extrator |
| 8 | a regra verifica somente cinco códigos compactos contra poste duplo T | manter; não inferir aprovação geral da estrutura nem converter uma recomendação pontual entre estruturas em obrigação |

| Candidato e lacuna | Fonte normativa | Escopo a confirmar | Fatos necessários antes de automatizar | Estado |
|---|---|---|---|---|
| `COER-01` coerência desenho↔orçamento/relação de materiais | não confirmada; comentários dos exemplos não são fonte | documentos que descrevem a mesma revisão de obra | identidade e revisão documental, código, quantidade, situação e associação inequívoca do item | REVISAO_HUMANA |
| `COER-02` potência de transformador no desenho↔orçamento | não confirmada; comentários dos exemplos não são fonte | transformador representado e item orçado da mesma revisão | identidade do equipamento, potência com unidade, situação, versões e associação entre documentos | REVISAO_HUMANA |
| `COER-03` número de fases coerente entre desenho e documentos complementares | não confirmada; comentários dos exemplos não são fonte | trecho/circuito e documentos da mesma revisão | circuito, trecho, fases, tensão, situação, versões e proveniência por documento | REVISAO_HUMANA |
| `CABLE-BT-01` cabo de baixa tensão do tronco | não confirmada; comentários dos exemplos não são fonte | trecho BT inequivocamente classificado como tronco | topologia, função do trecho, tecnologia, material, seção, fases, situação e exceções | REVISAO_HUMANA |
| `CABLE-R-01` emprego de cabo coberto em contexto rural | não confirmada para a condição percebida; comentários dos exemplos não são fonte | trecho rural e classe de obra ainda a delimitar | contexto rural explícito, tecnologia, seção, tensão, situação, ambiente e exceções | REVISAO_HUMANA |
| `SYMB-POST-01` simbologia de poste coerente com sua especificação | não confirmada; comentários dos exemplos não são fonte | poste inequivocamente identificado no desenho e nos documentos associados | símbolo, tipo, material, altura, resistência, situação, legenda e associação geométrica | REVISAO_HUMANA |
| `DOC-PRODR-01` PRODR e registro fotográfico | o subconjunto PRORDR foi confirmado em `RURAL-PRODR-01`; a obrigação fotográfica não foi confirmada | tipo de obra, fase do processo e pacote documental a delimitar | exigência aplicável, tipo documental, identidade do projeto, data, autoria, completude e vínculo entre fotos e alvos | REVISAO_HUMANA |
| `DOC-GD-01` nota/condição operacional de geração distribuída | não confirmada em fonte pública oficial; repetição nos exemplos não é fonte | serviço de GD e parecer técnico aplicável à mesma revisão | identidade do parecer, condição operacional, marco da obra, presença/conteúdo da nota e proveniência | REVISAO_HUMANA |
| `COER-CAMPO-01` coerência desenho↔levantamento/fotos/estado físico | não confirmada como regra universal; comentários dependem do levantamento específico | desenho e levantamento de campo da mesma revisão, com ativos individualizados | versão, data, foto e geometria associadas, estado existente/proposto e identidade do ativo | REVISAO_HUMANA |
| `TOPO-DES-01` coerência topológica MT↔transformador/ramal/AF | princípios parciais na ND-2.2 não bastam para a condição ampla percebida | circuito e documentos complementares da mesma revisão | grafo elétrico, transformador, AF, ramal, extremos dos vãos, situação e associação entre documentos | REVISAO_HUMANA |

## Regra para futuras incorporações

Uma entrada `AGUARDA_FATO` só avança após o fato preservar unidade, situação, alvo, associação e
proveniência. Depois são exigidos casos sintéticos de conforme, divergência, não avaliável e cada
exceção aplicável, além da paridade automática entre este catálogo e o registro.
