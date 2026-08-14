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
primeira execução, as 39 entradas abaixo recebem os números 1 a 39 a partir do seed. A interface
oferece somente importação e exportação. Importar gera atomicamente outro catálogo Markdown na pasta
de dados do usuário; pode alterar o estado `enabled` declarado por um ID, mas nunca remove regras
omitidas do arquivo. Este arquivo versionado documenta o seed; ações da interface não o modificam
silenciosamente.

## Resumo

| Número | ID técnico | Título | Registro | Automação | Revisão normativa |
|---|---|---|---|---|---|
| Regra 1 | `nd31.desenho.numero-projeto` | NS do cabeçalho corresponde ao projeto | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 2 | `nd31.desenho.formato` | Formato de folha padronizado | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 3 | `nd31.desenho.escala` | Escala urbana de apresentação | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 4 | `nd31.equipamento.estrutura-angulo` | Equipamento em estrutura de ângulo | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 5 | `nd31.equipamento.risco-abalroamento` | Avaliação de abalroamento em equipamento no ângulo | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 6 | `nd31.vao.urbano-compacto-isolado` | Vão máximo de rede compacta ou isolada urbana | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 7 | `nd31.cabo.convencional-novo-urbano` | Cabo nu convencional em obra nova urbana | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 8 | `nd93.compatibilidade.estrutura-poste-duplo-t` | Estrutura compacta rural incompatível com poste duplo T | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 9 | `nd31.transformador.poste-existente-30-75` | Poste existente para transformador trifásico de 30 a 75 kVA | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 10 | `nd31.transformador.poste-existente-150-300` | Poste existente para transformador trifásico de 150 ou 300 kVA | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 11 | `nd31.desenho.numero-folha` | Número da folha informado | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 12 | `nd31.desenho.data-projeto` | Data do projeto informada | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 13 | `nd31.desenho.circuito` | Circuito ou alimentador informado | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 14 | `nd31.poste.urbano-altura-minima` | Poste urbano novo com altura mínima | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 15 | `nd31.poste.urbano-formato-circular` | Poste urbano novo de seção circular | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 16 | `nd31.equipamento.poste-novo-altura` | Poste novo com equipamento acima de 11 m | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 17 | `nd31.equipamento.poste-novo-resistencia` | Poste novo com equipamento de 600 daN | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 18 | `catalogo.compatibilidade.estrutura-cabo` | Estrutura compatível com o cabo | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 19 | `nd31.transformador.chave-fusivel` | Chave fusível no transformador | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 20 | `nd31.transformador.para-raios-bt` | Para-raios de BT no transformador | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 21 | `nd31.transformador.para-raios-mt` | Para-raios de MT no transformador | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 22 | `nd31.transformador.aterramento` | Aterramento no transformador | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 23 | `nd31.documentacao.relacao-materiais-orcamento` | Relação de materiais e orçamento identificada | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 24 | `nd31.documentacao.memoria-calculo` | Memória de cálculo identificada | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 25 | `nd31.desenho.numeracao-postes` | Postes numerados de P1 a Pn | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 26 | `nd22.projeto.prordr-acima-300` | PRORDR em extensão rural acima de 300 m | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 27 | `nd22.cabo.rural-vao-maior-80-caa` | Cabo CAA em vão rural acima de 80 m | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 28 | `nd93.transformador.poste-novo-rural` | Poste novo rural de transformador | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 29 | `nd93.rede.transicao-sem-angulo` | Transição de rede sem deflexão | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 30 | `nd31.rede.para-raios-mt-fim-transicao` | Para-raios MT em fim ou transição de rede | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 31 | `nd93.rede.compacta-ancoragem-500m` | Ancoragem periódica da rede compacta | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 32 | `pacote.coerencia.transformador-potencia` | Potência do transformador coerente entre desenho e orçamento | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 33 | `pacote.coerencia.fases` | Fases coerentes entre desenho e orçamento | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 34 | `pacote.coerencia.codigo` | Código técnico coerente entre desenho e orçamento | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 35 | `pacote.coerencia.circuito` | Circuito coerente entre desenho e orçamento | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 36 | `pacote.documentacao.gd` | Documentação de acesso para geração distribuída | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 37 | `pacote.documentacao.prordr-fotos` | Registro fotográfico no pacote PRORDR | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 38 | `nd31.rede.neutro-aterramento-200m` | Aterramento periódico do neutro | ATIVA | OPERACIONAL | IMPLEMENTADA |
| Regra 39 | `nd31.rede.compacta-aterramento-temporario-160m` | Pontos periódicos de aterramento temporário da rede compacta | ATIVA | OPERACIONAL | IMPLEMENTADA |

## Regras existentes

### Regra 1 - NS do cabeçalho corresponde ao projeto

- **ID:** `nd31.desenho.numero-projeto`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 2.4, página PDF
  88, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** cabeçalho do PDF com `projeto.nota_servico_cabecalho` extraída.
- **Fatos:** `projeto.nota_servico`, `projeto.nota_servico_cabecalho` e
  `projeto.nota_servico_divergencia`; os dois números são normalizados para dez dígitos.
- **Condição:** ausência de `projeto.nota_servico_divergencia` resulta conforme; diferença entre a
  NS do cabeçalho e a NS usada como nome do projeto produz divergência.
- **Exceções:** nenhuma na obrigação examinada.
- **Testes:** números iguais, números diferentes, cabeçalho ausente e normalização de dígitos.

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
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 2.1, página PDF
  88, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** projeto urbano positivamente identificado.
- **Fatos:** `rede.contexto_urbano`; `projeto.escala` extraída do cabeçalho e normalizada.
- **Condição:** `1:1000` ou `1:500` resulta conforme; outra escala conhecida produz divergência.
- **Exceções:** nenhuma exceção adicional está declarada no registro atual.
- **Testes:** escalas admitidas, escala divergente, ausência e contexto não urbano.

### Regra 4 - Equipamento em estrutura de ângulo

- **ID:** `nd31.equipamento.estrutura-angulo`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, observação j,
  páginas PDF 66–67, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** equipamento não fusível a instalar em região com ângulo calculado.
- **Fatos:** `regiao.equipamento_instalar`; `regiao.equipamento_classe`;
  `conexao.angulo_graus`.
- **Condição:** deflexão acima de 30 graus produz divergência; até 30 graus atende a esta regra.
- **Exceções:** chave fusível fica fora da aplicabilidade; até 30 graus depende também da Regra 5.
- **Testes:** chave fusível, até/acima do limite e ausência de ângulo fora da aplicabilidade.

### Regra 5 - Avaliação de abalroamento em equipamento no ângulo

- **ID:** `nd31.equipamento.risco-abalroamento`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, observação j,
  páginas PDF 66–67, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** equipamento não fusível a instalar, com deflexão maior que zero e de até 30
  graus.
- **Fatos:** os da Regra 4 e `regiao.risco_abalroamento_avaliado`.
- **Condição:** avaliação positiva resulta conforme; ausência ou valor negativo no caso aplicável
  produz divergência.
- **Exceções:** chave fusível e conexões fora da faixa declarada.
- **Testes:** evidência presente, ausente, chave fusível, faixa e ângulo desconhecido.

### Regra 6 - Vão máximo de rede compacta ou isolada urbana

- **ID:** `nd31.vao.urbano-compacto-isolado`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Citação exata:** CEMIG ND-3.1, Jul/2025, “Locação de Postes”, item 3, alíneas b e c,
  página PDF 27, [fonte oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **Aplicabilidade:** região urbana com cabo protegido ou isolado.
- **Fatos:** `rede.contexto_urbano`; `cabo.tecnologia`; `vao.comprimento_m`;
  `vao.aplicabilidade_excecao_45_60_resolvida`; `vao.excecao_45_60_demonstrada`.
- **Condição:** até 45 m resulta conforme; comprimento superior produz divergência quando a
  aplicabilidade da faixa excepcional foi resolvida e nenhuma exceção foi demonstrada.
- **Exceções:** acima de 45 m e até 60 m somente com contexto periférico/baixa densidade ou chácaras, perfil favorável
  e demais condições positivamente demonstradas.
- **Processo automático:** `detectar_vaos` fornece a medida já materializada no cabo. O provedor liga
  o cabo confirmado à região pela decisão de revisão, conserva `ANOTACAO_DESENHO`, `COORDENADAS` ou
  `INFORMADO`, ancora anotação no rótulo e coordenadas na geometria do cabo. A exceção só é publicada
  para medida acima de 45 m e de até 60 m, com indicador positivo e evidência existente na mesma
  página. O provedor resolve a aplicabilidade com comprimento, tecnologia, contexto e evidência da
  exceção associados ao mesmo vão.
- **Histórico:** localizador corrigido de página 26 para 27 em 12/08/2026, sem mudar a obrigação.
- **Associação:** comprimento, tecnologia e prova excepcional preservam a identidade do vão; uma
  exceção positiva de 45–60 m não suprime a análise de outro vão. Vãos rurais não entram nesta regra.
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

### Regra 11 - Número da folha informado

- **ID:** `nd31.desenho.numero-folha`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 2.5, página PDF 89.
- **Aplicabilidade e fatos:** projeto urbano; `rede.contexto_urbano` e
  `projeto.numero_folha` extraído do cabeçalho.
- **Condição:** o número da folha ou prancha deve estar presente.

### Regra 12 - Data do projeto informada

- **ID:** `nd31.desenho.data-projeto`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 2.5, página PDF 89.
- **Aplicabilidade e fatos:** projeto urbano; `rede.contexto_urbano` e
  `projeto.data_projeto` extraído do cabeçalho.
- **Condição:** a data do projeto deve estar presente.

### Regra 13 - Circuito ou alimentador informado

- **ID:** `nd31.desenho.circuito`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 2.5.2, página PDF 89.
- **Aplicabilidade e fatos:** projeto urbano; `rede.contexto_urbano` e `projeto.circuito`
  extraído do cabeçalho.
- **Condição:** o circuito ou alimentador deve estar presente.

### Regra 14 - Poste urbano novo com altura mínima

- **ID:** `nd31.poste.urbano-altura-minima`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, Posteação, item 1.2,
  página PDF 59.
- **Aplicabilidade e fatos:** postes a instalar em região urbana, reconhecidos por simbologia e
  especificação; `rede.contexto_urbano` e `regiao.poste_instalar_altura_m`.
- **Condição:** todos os postes aplicáveis devem possuir altura nominal mínima de 11 m.

### Regra 15 - Poste urbano novo de seção circular

- **ID:** `nd31.poste.urbano-formato-circular`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, Posteação, item 1.1,
  página PDF 58.
- **Aplicabilidade e fatos:** postes a instalar em expansão, reforma ou substituição urbana;
  `rede.contexto_urbano` e `regiao.poste_instalar_formato`.
- **Condição:** todos os postes aplicáveis devem possuir formato `CIRCULAR`.

### Regra 16 - Poste novo com equipamento acima de 11 m

- **ID:** `nd31.equipamento.poste-novo-altura`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, Posteação, item 1.2,
  alínea d, página PDF 59.
- **Aplicabilidade e fatos:** poste novo urbano associado topologicamente a equipamento a instalar;
  `rede.contexto_urbano` e `regiao.poste_equipamento_instalar_altura_m`.
- **Condição:** todos os postes aplicáveis devem possuir altura superior a 11 m.

### Regra 17 - Poste novo com equipamento de 600 daN

- **ID:** `nd31.equipamento.poste-novo-resistencia`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Mecânico”, observação r, página PDF 67.
- **Aplicabilidade e fatos:** poste novo urbano associado topologicamente a equipamento a instalar;
  `rede.contexto_urbano` e `regiao.poste_equipamento_instalar_resistencia_dan`.
- **Condição:** todos os postes aplicáveis devem possuir resistência nominal mínima de 600 daN.

### Regra 18 - Estrutura compatível com o cabo

- **ID:** `catalogo.compatibilidade.estrutura-cabo`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-2.7, Nov/2016, e ND-2.9, Jun/2016, estruturas padronizadas e cabos
  aplicáveis, a partir da página PDF 27.
- **Aplicabilidade e fatos:** pares estrutura–cabo associados por simbologia e topologia;
  `regiao.estrutura_cabo_avaliada` e `regiao.estrutura_cabo_incompativel`.
- **Condição:** nenhum par avaliado pode constar como incompatível na matriz técnica do catálogo.

### Regra 19 - Chave fusível no transformador

- **ID:** `nd31.transformador.chave-fusivel`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Elétrico”, item 2.2.7, página PDF 49.
- **Aplicabilidade e fatos:** transformador a instalar em rede nua ou compacta;
  `regiao.transformador_instalar`, `cabo.tecnologia` e `regiao.chave_fusivel_presente`.
- **Condição:** deve existir chave fusível associada ao transformador.

### Regra 20 - Para-raios de BT no transformador

- **ID:** `nd31.transformador.para-raios-bt`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Elétrico”, item 1.6, alínea a,
  página PDF 40.
- **Aplicabilidade e fatos:** transformador a instalar; `regiao.transformador_instalar` e
  `regiao.para_raios_bt_presente`.
- **Condição:** deve existir para-raios de baixa tensão associado ao transformador.

### Regra 21 - Para-raios de MT no transformador

- **ID:** `nd31.transformador.para-raios-mt`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Elétrico”, item 2.2.8, alínea a,
  página PDF 51.
- **Aplicabilidade e fatos:** transformador a instalar em rede nua ou compacta;
  `regiao.transformador_instalar`, `cabo.tecnologia` e
  `regiao.transformador_para_raios_mt_presente`.
- **Condição:** deve existir para-raios de média tensão associado ao transformador.

### Regra 22 - Aterramento no transformador

- **ID:** `nd31.transformador.aterramento`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Elétrico”, item 7, alínea g,
  página PDF 57.
- **Aplicabilidade e fatos:** transformador a instalar; `regiao.transformador_instalar` e
  `regiao.aterramento_presente`.
- **Condição:** o transformador e seus dispositivos de proteção devem possuir aterramento.

### Regra 23 - Relação de materiais e orçamento identificada

- **ID:** `nd31.documentacao.relacao-materiais-orcamento`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, itens 1 e 2.6,
  página PDF 90.
- **Aplicabilidade e fatos:** pacote de projeto urbano; `rede.contexto_urbano` e
  `projeto.relacao_materiais_orcamento_identificada`.
- **Condição:** o pacote deve conter relação de materiais e orçamento identificáveis.

### Regra 24 - Memória de cálculo identificada

- **ID:** `nd31.documentacao.memoria-calculo`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 1, página PDF 88.
- **Aplicabilidade e fatos:** pacote de projeto urbano; `rede.contexto_urbano` e
  `projeto.memoria_calculo_identificada`.
- **Condição:** o pacote deve conter memória de cálculo elétrico e mecânico identificável.

### Regra 25 - Postes numerados de P1 a Pn

- **ID:** `nd31.desenho.numeracao-postes`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Apresentação do Projeto”, item 2.5.2, página PDF 90.
- **Aplicabilidade e fatos:** projeto urbano com postes ativos; `rede.contexto_urbano`,
  `projeto.postes_total` e `projeto.postes_numeracao_sequencial`.
- **Condição:** a numeração deve ser única, completa e sequencial de `P1` a `Pn`.

### Regra 26 - PRORDR em extensão rural acima de 300 m

- **ID:** `nd22.projeto.prordr-acima-300`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-2.2, Out/2016, Introdução, nota geral 4, página PDF 14.
- **Aplicabilidade e fatos:** projeto rural com mais de 300 m de rede a instalar;
  `rede.contexto_rural`, `projeto.extensao_rede_instalar_m` e `projeto.prordr_identificado`.
- **Condição:** o pacote deve identificar o uso do PRORDR.

### Regra 27 - Cabo CAA em vão rural acima de 80 m

- **ID:** `nd22.cabo.rural-vao-maior-80-caa`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-2.2, Out/2016, Introdução, nota geral 3, página PDF 14.
- **Aplicabilidade e fatos:** vão rural convencional acima de 80 m; `rede.contexto_rural`,
  `vao.comprimento_m` e `cabo.instalar_tecnologia` associados ao mesmo trecho.
- **Condição:** todos os cabos aplicáveis devem usar tecnologia `CONVENCIONAL_CAA`.

### Regra 28 - Poste novo rural de transformador

- **ID:** `nd93.transformador.poste-novo-rural`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-9.3, Set/2021, capítulo 7, nota 16, página PDF 41.
- **Aplicabilidade e fatos:** transformador rural a instalar associado a poste novo;
  `rede.contexto_rural`, `regiao.transformador_instalar`, resistência e formato do poste associado.
- **Condição:** resistência mínima de 600 daN e formato diferente de `DUPLO_T`.

### Regra 29 - Transição de rede sem deflexão

- **ID:** `nd93.rede.transicao-sem-angulo`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-9.3, Set/2021, capítulo 7, nota 10, página PDF 41.
- **Aplicabilidade e fatos:** transição reconhecida entre rede convencional e compacta;
  `regiao.transicao_rede` e `conexao.angulo_graus` calculado pela topologia.
- **Condição:** a deflexão horizontal ou vertical deve ser igual a zero grau.

### Regra 30 - Para-raios MT em fim ou transição de rede

- **ID:** `nd31.rede.para-raios-mt-fim-transicao`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Elétrico”, item 2.2.8,
  página PDF 51.
- **Aplicabilidade e fatos:** fim de rede MT ou transição reconhecida;
  `regiao.para_raios_mt_requerido` e `regiao.para_raios_mt_requisito_presente`.
- **Condição:** deve existir para-raios de média tensão na região aplicável.

### Regra 31 - Ancoragem periódica da rede compacta

- **ID:** `nd93.rede.compacta-ancoragem-500m`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-9.3, Set/2021, capítulo 7, nota 17, página PDF 41.
- **Aplicabilidade e fatos:** rede compacta rural cujo percurso esteja completamente mensurado e
  cujo maior componente seja superior a 500 m; `rede.contexto_rural`,
  `projeto.rede_compacta_ancoragem_avaliada`, `projeto.rede_compacta_maior_componente_m` e
  `projeto.rede_compacta_ancoragem_suficiente`.
- **Condição:** a topologia deve demonstrar ancoragens suficientes para intervalos aproximados de
  500 m.

### Regra 32 - Potência do transformador coerente entre desenho e orçamento

- **ID:** `pacote.coerencia.transformador-potencia`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** controle de coerência do pacote documental, revisão 2025.6.
- **Aplicabilidade e fatos:** potência única reconhecida no desenho e na relação de
  materiais/orçamento; `projeto.coerencia_potencia_transformador_avaliada`.
- **Condição:** `projeto.coerencia_potencia_transformador` deve ser verdadeiro.

### Regra 33 - Fases coerentes entre desenho e orçamento

- **ID:** `pacote.coerencia.fases`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** controle de coerência do pacote documental, revisão 2025.6.
- **Aplicabilidade e fatos:** configuração de fases única reconhecida nos documentos comparados;
  `projeto.coerencia_fases_avaliada`.
- **Condição:** `projeto.coerencia_fases` deve ser verdadeiro.

### Regra 34 - Código técnico coerente entre desenho e orçamento

- **ID:** `pacote.coerencia.codigo`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** controle de coerência do pacote documental, revisão 2025.6.
- **Aplicabilidade e fatos:** código técnico único reconhecido nos documentos comparados;
  `projeto.coerencia_codigo_avaliada`.
- **Condição:** `projeto.coerencia_codigo` deve ser verdadeiro.

### Regra 35 - Circuito coerente entre desenho e orçamento

- **ID:** `pacote.coerencia.circuito`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** controle de coerência do pacote documental, revisão 2025.6.
- **Aplicabilidade e fatos:** circuito ou alimentador único reconhecido nos documentos comparados;
  `projeto.coerencia_circuito_avaliada`.
- **Condição:** `projeto.coerencia_circuito` deve ser verdadeiro.

### Regra 36 - Documentação de acesso para geração distribuída

- **ID:** `pacote.documentacao.gd`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** controle documental do projeto, revisão 2025.6.
- **Aplicabilidade e fatos:** geração distribuída, microgeração ou minigeração identificada;
  `projeto.geracao_distribuida_identificada`.
- **Condição:** o pacote deve publicar `projeto.documentacao_gd_identificada` como verdadeiro.

### Regra 37 - Registro fotográfico no pacote PRORDR

- **ID:** `pacote.documentacao.prordr-fotos`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** controle documental do projeto, revisão 2025.6.
- **Aplicabilidade e fatos:** projeto rural PRORDR com percurso a instalar completamente mensurado
  e extensão superior a 300 m; `rede.contexto_rural`,
  `projeto.extensao_rede_instalar_avaliada`, `projeto.extensao_rede_instalar_m` e
  `projeto.prordr_identificado`.
- **Condição:** o pacote deve conter registro fotográfico identificável.

### Regra 38 - Aterramento periódico do neutro

- **ID:** `nd31.rede.neutro-aterramento-200m`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Elétrico”, item 7, página PDF 57.
- **Aplicabilidade e fatos:** componente urbano do neutro com percurso completamente mensurado e
  extensão superior a 200 m; `projeto.neutro_aterramento_periodico_avaliado` e
  `projeto.neutro_maior_componente_m`.
- **Condição:** o maior trecho sem aterramento não pode superar aproximadamente 200 m.

### Regra 39 - Pontos periódicos de aterramento temporário da rede compacta

- **ID:** `nd31.rede.compacta-aterramento-temporario-160m`.
- **Estado:** `IMPLEMENTADA`; automação `OPERACIONAL`.
- **Fonte:** CEMIG ND-3.1, Jul/2025, “Dimensionamento Elétrico”, item 7, página PDF 57.
- **Aplicabilidade e fatos:** componente urbano de rede compacta com percurso completamente
  mensurado e extensão superior a 160 m; `projeto.rede_compacta_aterramento_temporario_avaliado`
  e `projeto.rede_compacta_maior_componente_m`.
- **Condição:** o maior trecho sem símbolo de aterramento associado não pode superar
  aproximadamente 160 m. O fato registra explicitamente que o modelo atual usa o símbolo genérico
  `ATERRAMENTO` como aproximação do ponto temporário.

## Matriz de candidatos das revisões normativa e dirigida

Os localizadores abaixo são citações bibliográficas exatas; as descrições são paráfrases curtas. Um
candidato `IMPLEMENTADA` aponta para a regra correspondente. Os demais não produzem divergência.

| Candidato e tema | Citação exata | Aplicabilidade | Exceções/condições | Fatos necessários | Estado |
|---|---|---|---|---|---|
| `DOC-01` conjunto documental | ND-3.1 Jul/2025, Apresentação do Projeto, item 1, p. 88 | todo projeto urbano | complementares somente quando cabíveis | desenho, relação de materiais/orçamento, memória elétrica e mecânica, tipo de complemento | PARCIAL — Regras 23 e 24 automatizam relação/orçamento e memória identificáveis |
| `DOC-02` detalhes do desenho | ND-3.1 Jul/2025, Apresentação do Projeto, itens 2.5–2.7, pp. 88–93 | conforme o tipo de obra e travessia | detalhes variam por instalação e órgão | campos estruturados, geometria, travessia, validade e autoria | PARCIAL — Regras 11–13 e 25 automatizam folha, data, circuito e numeração de postes |
| `LIM-01` escala e suas exceções | ND-3.1 Jul/2025, Apresentação do Projeto, item 2.1, p. 88 | projeto urbano | escalas admitidas no registro atual | contexto e escala normalizada | IMPLEMENTADA — Regra 3 |
| `POST-01` comprimento mínimo em expansão | ND-3.1 Jul/2025, Dimensionamento Mecânico, item 1.2, p. 59 | poste novo em projeto de expansão | situações que exigem poste maior; instalações sem previsão de MT têm arranjo próprio | tipo de projeto, poste associado, altura, previsão MT e situação especial | PARCIAL — Regra 14 automatiza a altura mínima urbana representável |
| `POST-TYPE-U01` tipo, substituição e reaproveitamento de poste urbano | ND-3.1 Jul/2025, Dimensionamento Mecânico, itens 1.1–1.2, pp. 58–59 | expansão, reforma ou troca de poste em área urbana | PRFV depende de acesso/abalroamento; situação existente não equivale a reaproveitamento de poste removido | contexto, classe da obra, situação individual, tipo/material, acesso, risco e vínculo entre poste retirado e proposto | PARCIAL — Regra 15 automatiza o formato circular dos postes novos reconhecidos |
| `POST-EQUIP-U01` resistência do poste associado a equipamento | ND-3.1 Jul/2025, Dimensionamento Mecânico, observações r–u, p. 67 | equipamento em extensão nova ou transformador em posteação existente/reforma | mínimos variam por tipo, potência, material/formato e necessidade de troca | situação da obra, equipamento, potência, poste associado, resistência, material e formato | PARCIAL — Regras 9, 10, 16 e 17 automatizam os subconjuntos representáveis por potência, altura, resistência e formato |
| `STRUCT-01` escolha por esforço/ângulo | ND-3.1 Jul/2025, Dimensionamento Mecânico, item 1.3.1, pp. 59–60, e item 2/tabelas 22–33, pp. 66–78 | estrutura urbana dimensionada | rede, cabo, seção, tensão, direção, telecomunicações e ancoragem alteram o cálculo | estrutura, pares de vãos, ângulos, cabos, poste, vento, cargas e esforço resultante | AGUARDA_FATO |
| `CABLE-01` cabo nu em instalação urbana | ND-3.1 Jul/2025, Tipos de Rede, item 1.1.3, p. 18 | obra nova urbana | reparo | contexto e tecnologia por proposta de instalação | IMPLEMENTADA — Regra 7 |
| `EQUIP-01` equipamento em ângulo | ND-3.1 Jul/2025, Dimensionamento Mecânico, observação j, pp. 66–67 | equipamento não fusível a instalar | chave fusível; até 30° exige avaliação de abalroamento | classe, situação, conexão, ângulo e avaliação | IMPLEMENTADA — Regras 4 e 5 |
| `PROT-01` proteção de transformador e elo | ND-3.1 Jul/2025, Dimensionamento Elétrico, item 2.2.7 e Tabela 8, pp. 48–51; ND-4.15 Nov/2017, capítulos 5–8, pp. 20–74 | rede MT e dispositivo especificados | filosofia, carga, inrush, curto e coordenação mudam o ajuste | topologia, potência, tensão, correntes, curvas, dispositivos a montante/jusante | PARCIAL — Regras 19–21 automatizam chave fusível e para-raios representados |
| `GROUND-01` aterramento urbano | ND-3.1 Jul/2025, Dimensionamento Elétrico, item 7, p. 57 | neutro, rede compacta/isolada e equipamentos conforme o caso | neutro a aproximadamente 200 m; aterramento temporário da compacta a aproximadamente 160 m; para-raios e pontos existentes alteram o arranjo | continuidade, distância acumulada, hastes, mensageiro, neutro, equipamento, conexão e tipo de aterramento | IMPLEMENTADA — Regras 22, 38 e 39 automatizam transformador e periodicidade topológica do neutro/compacta |
| `SPAN-U01` vão urbano compacto/isolado | ND-3.1 Jul/2025, Locação de Postes, item 3, p. 27 | rede urbana protegida/isolada | faixa 45–60 m com fatos positivos | contexto, tecnologia, comprimento, perfil e exceção | IMPLEMENTADA — Regra 6 |
| `SPAN-R01` vãos rurais | ND-9.3 Set/2021, Projetos de RDP Compactas em Áreas Rurais, seção “Vão”, itens 1–5 e Tabelas 2–3, pp. 24–25; ND-2.2 Out/2016, Introdução, pp. 14–15 | rede rural conforme tecnologia e classe | travessia, topografia, compartilhamento, condutor e autorização técnica alteram limites | cabo/seção, classe RDR, poste/altura/resistência, relevo, ângulo, compartilhamento, autorização e cálculo mecânico | PARCIAL — Regra 27 automatiza o uso de CAA no subconjunto de vãos acima de 80 m |
| `RURAL-PRODR-01` uso do PRORDR | ND-2.2 Out/2016, Introdução, Notas Gerais, nota 4, p. 14 | projeto rural com extensão acima de 300 m | em locais difíceis para estais deve ser escolhida a opção própria sem estais laterais | contexto, extensão total, programa/memória utilizada, terreno e alternativa selecionada | PARCIAL — Regra 26 automatiza a identificação do PRORDR acima de 300 m |
| `RURAL-DERIV-01` estai ou tração RDU em derivação | ND-2.2 Out/2016, Derivações, Notas Gerais, notas 2–3, p. 68 | estrutura de derivação rural com tração de RDR | sem estai contrário, a alternativa exige condutor CA, tração de RDU, vão de até 80 m e poste dimensionado para vento máximo | topologia da derivação, tração, condutor, vão, estai, esforço, vento, poste e memória de cálculo | AGUARDA_FATO |
| `RURAL-STAY-01` escolha e dimensionamento de estais rurais | ND-2.2 Out/2016, Estaiamento, notas 5 e 9–15, p. 144, e Gráficos, notas 4–11, pp. 173–174 | estrutura rural sujeita a esforço e condição de terreno conhecidos | capacidade, solo, declive, risco agrícola e alternativa sem estai lateral mudam o arranjo; esta última exige poste um metro maior | esforços lateral/longitudinal, vento, vãos adjacentes, solo, declive, risco, tipo/capacidade do estai, poste e engastamento | AGUARDA_FATO |
| `POST-ORIENT-R01` orientação de poste duplo T rural | ND-2.2 Out/2016, Primário, Notas Gerais, notas 7–10, p. 25 | poste duplo T rural em alinhamento, deflexão ou fim de rede | orientação varia por faixa angular, maior vão/esforço, fase e presença de estai longitudinal | formato, ângulo, direção dos vãos, esforços, fim de rede, fases, estais e orientação geométrica do poste | AGUARDA_FATO |
| `RURAL-01` contexto e traçado | ND-9.3 Set/2021, capítulos 5–7, pp. 19–40 | projeto do Programa Minas Trifásico | urbano, faixa de domínio, licenciamento e planejamento alteram o fluxo | classificação rural/urbana, traçado, servidão, relevo, vento, demanda e autorizações | REVISAO_HUMANA |
| `COMP-01` estruturas compactas e poste duplo T | ND-9.3 Set/2021, capítulo 8, “Estruturas”, nota 2, p. 43 | estrutura compacta indicada em região rural | códigos fora da lista e associação ambígua | contexto, estrutura instalada e formato do poste associado | IMPLEMENTADA — Regra 8 |
| `COMP-02` matriz estrutura–cabo | ND-2.7 Nov/2016, capítulos 3–10, pp. 27–121; ND-2.9 Jun/2016, capítulos 3–12, pp. 19–114 | instalação isolada ou compacta específica | desenhos, nível, fase, seção, derivação, transição e equipamento | IDs normativos, relação elemento–região e matriz oficial normalizada | IMPLEMENTADA — Regra 18 |
| `TOPO-01` coordenação e seletividade | ND-4.15 Nov/2017, capítulos 5–8, pp. 20–74 | sistema MT com proteção em série | filosofia e dispositivos variam por alimentador | grafo elétrico, correntes de falta/carga, curvas, ajustes e sequência operacional | REVISAO_HUMANA |
| `CALC-01` queda de tensão | ND-3.1 Jul/2025, Dimensionamento Elétrico, item 3 e tabelas 10–14, pp. 52–55 | circuito dimensionado | limite depende de subestação AT/MT e cenário de carga/geração | topologia, demanda, distância, condutor, transformador, tensão e cenário | AGUARDA_FATO |
| `ABS-01` reprovar por ausência de carimbo, assinatura visual ou símbolo não detectado | ND-3.1 Jul/2025, Apresentação do Projeto, pp. 88–93 | não estabelecida de forma universal pelo detector | autenticidade, formato e exigência contratual variam | seria necessário provar obrigação e cobertura do detector | DESCARTADA |

### Lacunas observadas nos exemplos de comissionamento

<<<<<<< HEAD
Uma revisão local pontual de agosto de 2026 encontrou famílias recorrentes que ainda não possuem
cobertura operacional. Os comentários de comissionamento servem apenas para priorizar investigação:
não são fonte normativa, não comprovam uma obrigação universal e não autorizam criar divergências.
Por isso, os candidatos abaixo permanecem em `REVISAO_HUMANA` até que uma fonte oficial, seu
localizador exato, a aplicabilidade e as exceções sejam confirmados. Somente depois podem passar a
`AGUARDA_FATO` e receber provedores.
=======
A revisão de 14/08/2026 encontrou dez PDFs locais de uma página e 51 anotações textuais `FreeText`.
Como os arquivos são ignorados pelo Git, a identificação da nova leva é inferencial: quatro folhas
atuais reproduzem as 20 anotações e as famílias da revisão anterior, enquanto seis folhas somam 31
anotações adicionais. Nenhum dos dez hashes corresponde ao manifesto formal de nove amostras.
>>>>>>> 51a97e2ba161a5914a20d6988ea9270393104e55

Os comentários de comissionamento servem apenas para priorizar investigação: não são fonte
normativa, não comprovam obrigação universal e não autorizam criar divergências. A revisão dirigida
da ND-2.2 e a revalidação da ND-3.1 permitiram acrescentar à matriz os candidatos normativos
`POST-TYPE-U01`, `POST-EQUIP-U01`, `RURAL-PRODR-01`, `RURAL-DERIV-01`, `RURAL-STAY-01` e
`POST-ORIENT-R01`. A revisão posterior dos fatos materializados promoveu os subconjuntos inferíveis
por cabeçalho, simbologia e topologia às Regras 9–39. As 39 regras oficiais estão ativas e
operacionais; candidatos mais amplos permanecem separados quando exigem condições que não fazem
parte do subconjunto automatizado.

A topologia confirmada permite observar cabos, extremos, postes, comprimentos, ângulos, componentes
e símbolos associados. A Introdução da ND-2.2 estabelece cabo CAA como padrão rural e admite cabo CA
somente no primeiro e no último vão de um novo ramal, ambos com até 80 m; por isso a Regra 27 reprova
automaticamente cabo CA em vão superior a 80 m. A alternativa de derivação sem estai contrário é uma
condição adicional distinta e continua dependendo de tração, esforço e memória mecânica que não
existem no modelo atual.

As observações também reforçam `DOC-01`, `DOC-02`, `POST-01`, `STRUCT-01`, `GROUND-01`,
`SPAN-R01`, `COMP-02`, `PROT-01` e `TOPO-01`. A indicação isolada de aterramento a cada 250 m não foi
incorporada: a ND-3.1 vigente estabelece aproximadamente 200 m para o neutro urbano. Notas curtas,
ajustes genéricos e critérios dependentes de grandezas ainda ausentes permanecem fora do registro
executável, sem produzir estado de revisão humana ou “aguardando fato” nas 39 regras oficiais.

### Estado operacional das oito regras preexistentes

| Regras | Resultado em 14/08/2026 | Decisão |
|---|---|---|
| 1 e 2 | cabeçalho e formato são extraídos do pacote PDF | Regra 1 compara a NS do cabeçalho com o nome do projeto; Regra 2 valida A1–A4 |
| 3 | escala é extraída e normalizada | ativa e operacional para `1:1000` e `1:500` |
| 4 e 5 | ângulo é calculado pela topologia e a avaliação de risco é publicada pelo provedor | ativas e operacionais nos intervalos declarados |
| 6 | comprimento, tecnologia e exceção preservam a associação por vão | ativa e operacional somente no contexto urbano protegido/isolado |
| 7 | situação e tecnologia permanecem associadas a cada trecho | ativa e operacional para cabos reconhecidos como instalação |
| 8 | estrutura e poste são pareados na região confirmada | ativa e operacional para os cinco códigos compactos declarados |

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
