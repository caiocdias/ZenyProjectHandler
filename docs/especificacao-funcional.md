# Especificação funcional — domínio do projeto de rede

## Objetivo e escopo

O domínio representa os elementos confirmados de um projeto de expansão da rede de distribuição da CEMIG e mantém separadas as evidências e propostas produzidas por análises automáticas. As classes principais continuam sendo `Poste`, `EstruturaMt`, `EstruturaBt`, `Cabo` e `Equipamento`.

O diagrama completo está em [`modelo-entidades.mmd`](./modelo-entidades.mmd). A implementação correspondente está em `src/zeny_project_handler/domain` e não depende de Qt, banco de dados, leitor de PDF ou biblioteca de visão computacional.

## Documento e coordenadas

- `PaginaDocumento` também guarda as seis componentes das matrizes públicas PDF -> página e de
  rotação intrínseca. Isso preserva a transformação exata mesmo com origem deslocada, `CropBox`
  diferente de `MediaBox` ou página girada.
- A coordenada normalizada canônica tem origem no canto superior esquerdo da página visual. Zoom,
  DPI e rotação adicional são estados de apresentação e não alteram a geometria salva.

- `Projeto` contém zero ou mais `DocumentoProjeto`; o documento preserva nome, SHA-256, tamanho,
  versão PDF, produtor e páginas.
- `PaginaDocumento` preserva dimensões, rotação, `MediaBox` e `CropBox`.
- `GeometriaDocumento` referencia uma página e representa ponto, caixa, polilinha ou polígono em
  coordenadas normalizadas de 0 a 1.
- Pontos e caixas devem permanecer dentro da página. Caixas têm área positiva, polilinhas possuem
  ao menos dois pontos e polígonos ao menos três pontos distintos.
- `CoordenadaCampo` preserva coordenadas georreferenciadas separadamente da posição gráfica no
  PDF. O sistema de referência e a zona permanecem explícitos; o programa não os presume.
- `Cabo` usa polilinha estruturada e pode registrar um percurso ordenado por pontos de rede, além de
  postes usados apenas como apoio intermediário.

## Elementos confirmados e relações

- Todo `ElementoProjeto` possui identificador, item do catálogo, `SituacaoProjeto`, geometria opcional e lista de fotos.
- `MetadadosProjeto` registra os campos técnicos comuns do desenho: Nota de Serviço, circuito,
  município, bairro, tipo de serviço, escala, formato, folha, data, impacto ambiental e dispositivo
  de seccionamento. A Nota de Serviço, quando conhecida, possui 10 dígitos.
- `ContatoSolicitante` mantém nome e telefone em um objeto separado, classificado como dado
  sensível e proibido em logs e manifestos versionados.
- `SituacaoProjeto` descreve exclusivamente a obra: `EXISTENTE`, `INSTALAR` ou `REMOVER`.
- `Poste` suporta estruturas MT/BT, equipamentos e pontos de rede.
- `PontoRede` representa o papel elétrico `POSTE`, `DERIVACAO`, `CONEXAO`, `ENTREGA`,
  `CAIXA_PASSAGEM`, `TRANSICAO` ou `OUTRO`. Somente o primeiro exige um poste; os demais podem
  existir fora dele e possuir geometria e coordenada próprias.
- `EstruturaMt` só fixa pontos MT; `EstruturaBt` só fixa pontos BT. O ponto precisa estar no mesmo poste da estrutura.
- Cada `Cabo` conecta duas extremidades distintas do mesmo projeto e pode registrar pontos
  intermediários ordenados. Derivações devem possuir seu próprio ponto para que o grafo não perca
  topologia.
- `Equipamento` possui `TerminalEquipamento`. Transformadores, chaves e outros dispositivos representam continuidade ou seccionamento por `ConexaoInternaEquipamento`.
- Terminais conectados a pontos devem possuir o mesmo nível de rede e as mesmas opções catalogadas de tensão e fases.
- `VinculoObra` associa uma retirada a uma instalação da mesma categoria. `REALOCACAO` também
  exige o mesmo tipo catalogado; `SUBSTITUICAO` permite mudança de tipo.
- Fotos usam caminhos relativos internos ao projeto; caminhos absolutos ou com `..` são inválidos.

O grafo é uma projeção, não uma fonte de dados. A visão física usa postes e equipamentos; a visão elétrica usa pontos de rede, terminais, cabos e conexões internas.

## Análise, propostas e revisão

Resultados automáticos não entram diretamente no conjunto confirmado:

1. `ExecucaoAnalise` registra método, versão, parâmetros, duração, estado, eventual erro fatal e
   diagnósticos de falhas parciais por extrator, página e objeto PDF.
2. `EvidenciaDocumento` registra página, geometria, tipo (`TEXTO`, `VETOR`, `IMAGEM` ou `OCR`),
   método, versão, parâmetros, atributos extraídos e conteúdo bruto.
3. `OrigemObjetoPdf` diferencia conteúdo de página, anotação, appearance stream de anotação e Form
   XObject, preservando número do objeto, índice, subtipo e nome do recurso quando disponíveis.
4. `ArtefatoExtraido` referencia binários derivados por caminho relativo, SHA-256, MIME type e
   tamanho. O PDF original continua sendo a fonte imutável.
5. `PropostaElemento` e `PropostaRelacao` referenciam suas evidências e podem registrar confiança e
   justificativa. Uma proposta de elemento também preserva o código observado e atributos sugeridos,
   mesmo quando nenhum item do catálogo corresponde.
6. `DecisaoRevisao` registra quem aceitou, rejeitou ou ajustou uma proposta e, quando aplicável, o ID
   do elemento ou da relação confirmada. Uma decisão final é imutável.
7. `ServicoRevisaoHumana` aplica a decisão, a alteração do agregado e o registro auditável na mesma
   transação. Mudanças de classe, item do catálogo, situação ou geometria são decisões `AJUSTAR`.
8. `RelacaoConfirmada` preserva tipo e extremidades já confirmadas. Elementos e relações criados
   manualmente registram autor, data e motivo opcional em `RegistroRevisaoManual`.
9. O painel lateral exibe sobreposições por estado, filtros por classe/estado, seleção, movimento,
   redimensionamento normalizado, reclassificação, vínculo ao catálogo e atalhos de aceitar/rejeitar.
   Uma proposta equivalente a outra anteriormente rejeitada não pode ser confirmada por nova análise.

`EstadoRevisao` é independente de `SituacaoProjeto`. Por exemplo, uma proposta ainda não revisada pode indicar corretamente que o símbolo representa um poste a remover.

## Catálogo técnico configurável

Os valores da planilha são itens reutilizáveis e não enums da linguagem. O seed inicial, distribuído como JSON versionado, foi extraído de `NOMENCLATURAS.xlsx`, aba `Planilha1`, SHA-256 `4ba9bd5cb284f6d18c3ee000a6064061d0d814bd23ec29d8630c2b15e58f8867`.

| Categoria | Linhas preservadas | Itens ativos |
|---|---:|---:|
| Postes | 38 | 38 |
| Estruturas MT | 50 | 49 |
| Estruturas BT | 13 | 13 |
| Cabos | 72 | 72 |
| Equipamentos | 25 | 25 |

O seed contém 198 itens, dos quais 197 estão ativos. Os valores controlados são organizados em cinco grupos editáveis:

- formato de poste;
- configuração de fases;
- tecnologia de rede;
- nível de tensão;
- classe de equipamento.

As expressões textuais de cabos aceitos pelas estruturas foram normalizadas em 314 relações explícitas `CompatibilidadeEstruturaCabo`, preservando também a expressão original e a linha de origem.

### Tratamentos de importação

- As duas ocorrências idênticas de `CEM4`, nas linhas 40 e 46, são preservadas. A primeira fica ativa, a segunda inativa e um `AvisoImportacao` registra a resolução.
- O valor `-` em fator de condenação vira `nulo`, nunca zero.
- Códigos originais de estruturas, cabos e equipamentos são preservados sem alteração.
- Postes, que não possuíam código, recebem código determinístico formado por altura, resistência e formato.
- IDs do seed são determinísticos; importar novamente a mesma origem produz as mesmas identidades.

## Versionamento e imutabilidade

- O formato JSON atual usa `schema_version = 2`, aceita leitura do schema 1 e rejeita versões
  desconhecidas.
- O catálogo inicial está `PUBLICADO` e é imutável.
- Uma edição começa com `criar_rascunho`, que gera nova identidade e incrementa a versão sem alterar a anterior.
- Apenas rascunhos aceitam troca de itens.
- Códigos ativos são únicos dentro de cada categoria. Duplicatas inativas podem permanecer para auditoria e leitura histórica.
- Projetos referenciam uma versão específica do catálogo. Itens desativados não desaparecem de projetos antigos.
- Há uma regra de apresentação canônica para cada combinação das cinco categorias e das três
  situações de obra, totalizando 15 regras.
- Assinaturas de reconhecimento visual são separadas das regras de apresentação e podem ser
  múltiplas por situação, com categoria opcional, tolerância de cor, padrão de traço opcional,
  prioridade e origem. O seed contém cinco assinaturas iniciais extraídas do corpus real: preto para
  existente, dois verdes para instalar e dois vermelhos para remover. Traço não é usado isoladamente
  para inferir situação.

Valores observados nas amostras, mas ausentes da planilha, não são incluídos silenciosamente no seed.
Entre eles estão `S3N`, religador `560A`, `3#240(240) AL`, `ABx1-150` e `ABCN-120(70)`. A análise
mantém esses códigos como propostas não mapeadas até que o usuário publique uma versão de catálogo
que os reconheça.

## Validações funcionais implementadas

1. IDs são únicos dentro de cada agregado.
2. Datas de domínio possuem fuso horário.
3. Itens apontam apenas para opções do grupo correto.
4. Compatibilidades ligam estruturas e cabos ativos, sem pares duplicados.
5. Elementos de projeto apontam para itens da categoria correta e para a versão de catálogo usada pelo projeto.
6. Geometrias apontam para páginas pertencentes ao projeto.
7. Estruturas, pontos, equipamentos, terminais, percursos de cabos, vínculos de obra e conexões
   internas não podem referenciar entidades externas ao agregado.
8. Catálogos publicados não podem ser alterados silenciosamente.
9. Vínculos de realocação e substituição sempre ligam uma retirada a uma instalação da mesma
   categoria; realocações preservam o tipo.
10. Catálogos schema v2 possuem assinaturas visuais para todas as situações e não aceitam
    assinaturas duplicadas.
11. Serialização seguida de desserialização preserva integralmente o domínio.

## Ingestão e visualização PDF

- `LeitorPdfPort` isola a aplicação da biblioteca concreta. `PyMuPdfReader` é o adaptador inicial e
  abre a origem somente para leitura.
- A inspeção calcula SHA-256, tamanho, data de modificação, versão/produtor e dimensões das páginas.
  O hash e os metadados do arquivo são conferidos novamente antes do commit de uma importação.
- Cada página recebe inventários independentes de fragmentos de texto, caminhos vetoriais, imagens
  incorporadas, anotações, referências de appearance streams e Form XObjects. O documento também
  registra Optional Content Groups.
- Um problema localizado produz `DiagnosticoPdf` com página e `xref` quando disponível. Texto,
  vetores, imagens e renderização válidos continuam utilizáveis.
- Miniaturas, páginas e recortes são renderizados em RGB. O DPI padrão é 144 e pode ser configurado
  por `ZENY_PDF_RENDER_DPI` entre 36 e 600.
- `TransformadorCoordenadasPagina` converte de forma reversível entre espaço PDF, normalizado,
  pixels e cena. A interface reaplica sobreposições após rotação usando essa transformação.
- A abertura aceita um ou vários PDFs. Quando há várias folhas em arquivos separados, o botão
  **Unir arquivos em um só projeto** valida todos os documentos e os apresenta, na ordem selecionada,
  como uma paginação contínua. A união é lógica: nenhum PDF original é concatenado ou modificado, e
  uma falha ou duplicidade mantém intacto o projeto que já estava aberto.
- A origem local é registrada em `document_sources`, fora do payload de domínio. Projeto,
  documento e referência são gravados na mesma transação; entrada inválida, protegida, corrompida,
  duplicada ou alterada não deixa uma importação parcial.
- O inventário é derivado e recriável. `AnalisadorDocumentoPort` normaliza esse material como
  `EvidenciaDocumento` sem depender da interface.

## Extração de evidências

- `PyMuPdfDocumentAnalyzer` é o primeiro adaptador do contrato. Texto é extraído por span com quad,
  fonte, tamanho, cor, opacidade e rotação; vetores preservam comandos e estilo; imagens preservam
  ocorrência visual, transformação, hash e recurso.
- Anotações e suas aparências são fontes explícitas. O analisador percorre referências indiretas e
  Form XObjects com limite de profundidade e proteção contra ciclos, incluindo imagens que não estão
  no primeiro nível de recursos da página.
- As geometrias são salvas no espaço normalizado canônico da página. Recursos internos de uma
  aparência que não expõem transformação própria usam os limites da anotação e recebem
  `geometria_aproximada = true`.
- Cada extrator falha isoladamente. `DiagnosticoAnalise` é persistido junto da execução sem descartar
  texto, vetores, imagens ou anotações válidos obtidos por outros extratores.
- OCR permanece desacoplado por `MotorOcrPort`. O adaptador local Tesseract é descoberto no `PATH`,
  no local padrão do Windows ou por `ZENY_TESSERACT_PATH`; nenhum documento é enviado à rede.
- O OCR é acionado quando há menos de 20 caracteres nativos, quando uma ocorrência raster ocupa ao
  menos 10% da página ou quando há pelo menos 1.000 caminhos vetoriais. O terceiro caso cobre textos
  plotados como contornos pelo AutoCAD mesmo quando o carimbo ainda contém texto nativo pesquisável.
- O cache derivado fica em `cache/analysis` na pasta de dados. Sua chave combina hash do PDF,
  configuração e versão do analisador; conteúdo ausente ou inválido é refeito a partir do original.
- `ExecutarAnaliseDocumento` valida a referência do PDF, registra execução concluída ou falha fatal e
  persiste todas as evidências válidas em uma transação.

## Pipeline modular de interpretação

- `RegistroRegrasInterpretacao` versiona regras de reconhecimento e relação e produz uma assinatura
  SHA-256 canônica. O schema atual é 1 e pode ser carregado do recurso embarcado ou de um JSON
  externo validado.
- Existem analisadores independentes para poste, estrutura MT, estrutura BT, cabo e equipamento. A
  correspondência delimitada com códigos ativos continua sendo a evidência mais específica.
- O analisador de postes também interpreta a nomenclatura `altura-resistência` usada nos projetos,
  aceitando separadores `-`, `/` ou `x` e sufixos opcionais `m` e `daN`. Uma combinação como
  `11-300` consulta os 38 postes do catálogo; sem formato explícito, preserva todos os candidatos e
  exige escolha humana entre Circular, Duplo T e Madeira.
- Frases como `POSTE CIRCULAR`, `TRANSFORMADOR`, `CHAVE FACA`, `CHAVE FUSÍVEL` e
  `CHAVE FUSÍVEL REPETIDORA` geram propostas de classe sem inventar um tipo exato. Acentos,
  sublinhados, espaços em torno de separadores e variantes de hífen são normalizados antes da busca.
- Evidências vetoriais e de imagem próximas são agregadas à proposta como contexto. Para cabos, uma
  polilinha próxima substitui a caixa do texto como geometria sugerida. Imagens não são classificadas
  isoladamente nesta versão.
- `AssinaturaSimbologia` classifica `EXISTENTE`, `INSTALAR` e `REMOVER` por cor e tolerância. Sem uma
  assinatura inequívoca, a proposta usa `EXISTENTE` com confiança conservadora e permanece sujeita à
  revisão humana.
- Relações `INSTALADA_EM`, `INSTALADO_EM`, `CONECTA` e `SUPORTADO_POR` são propostas por centro,
  extremidade ou proximidade combinada com `CompatibilidadeEstruturaCabo`.
- IDs UUID5 combinam projeto, extração, interpretador, registro e configuração. Repetir uma execução
  concluída reutiliza o resultado; retomar uma cancelada usa a mesma identidade sem duplicação.
- A extração e a interpretação são execuções auditáveis distintas. Propostas semânticas podem
  referenciar evidências de uma extração anterior do mesmo projeto, mas nunca de outro projeto.
- Início, fim, estado, configuração, versões, diagnósticos e falha fatal são persistidos. Propostas
  somente são publicadas atomicamente após a conclusão.
- `InterpretadorRegrasAvaliacao` executa leitura, extração e interpretação sem persistência para que o
  benchmark meça exatamente o pipeline real.

## Amostras reais e privacidade

Todos os PDFs locais em `examples/` são ignorados pelo Git. Nove deles compõem o conjunto formal
atual; o arquivo `evaluation/manifesto-amostras.json` contém apenas seus IDs anônimos, hashes e
características técnicas. PDFs adicionais podem ser colocados nessa pasta a qualquer momento como
amostras exploratórias: eles participam automaticamente do smoke test local somente leitura, sem
precisar entrar no manifesto. Nomes de arquivos, nomes de clientes, telefones, coordenadas e
fotografias não são versionados.

O corpus cobre A3/A4, retrato/paisagem, iText, AutoCAD, Microsoft Print to PDF, texto, vetores,
imagens, anotações `Stamp`, `Popup`, `FreeText`, `Square`, appearance streams e Optional Content
Groups. Uma amostra possui texto de anotação malformado e outra contém imagens visíveis apenas em
appearance streams. Esses casos serão obrigatórios nos testes das etapas de ingestão e extração.

## Conjunto de avaliação semântica

- `ManifestoAvaliacao` separa amostras de desenvolvimento e teste por hash, sem nomes de arquivo.
- `AnotacaoAmostra` registra elementos, categoria, situação, geometria normalizada e relações. Os
  papéis `PRIMARIA`, `SECUNDARIA` e `CONSENSO` distinguem rotulagem independente de adjudicação.
- Uma anotação congelada deve ser de consenso, possuir revisor pseudônimo e referenciar somente
  páginas e elementos existentes na amostra correspondente.
- Amostras marcadas para dupla anotação medem divergência de contagem, categoria, situação,
  geometria e relações antes da adjudicação.
- O pareamento de pontos usa distância normalizada; caixas e polígonos usam IoU da caixa envolvente;
  polilinhas usam distância simétrica aos segmentos. A associação é um-para-um e determinística.
- O benchmark registra precisão, recall e F1 por classe, relações, falhas de extração, latência p95 e
  pico de memória rastreada pelo Python. A medição não inclui toda memória nativa de bibliotecas C.
- A assinatura semântica inclui conjunto, critérios, interpretador, regras, configuração e contagens,
  mas exclui latência e memória para permanecer reproduzível entre execuções equivalentes.
- O teste final é recusado enquanto manifesto ou critérios não estiverem congelados/aprovados.
- A auditoria impede o congelamento sem consenso de todas as amostras, cobertura das cinco classes,
  dupla anotação exigida e diversidade mínima de escala, formato, orientação, qualidade e densidade.

O corpus atual satisfaz formato, orientação, qualidade e densidade, mas todas as amostras declaram a
mesma escala. Ele permanece em preparação até a inclusão autorizada de outra escala e a conclusão da
revisão humana. As regras iniciais foram construídas somente com catálogo, contratos e fixtures
sintéticas; a partição de teste privada não foi usada para criá-las.

## Persistência local

- SQLite é a fonte canônica e fica em `zeny-project-handler.sqlite3` dentro da pasta local da
  aplicação, substituível por `ZENY_DATA_DIR`.
- A aplicação executa as migrações Alembic antes de abrir a janela. Bancos vazios e bancos na revisão
  anterior são atualizados para a revisão corrente.
- O mapeamento é híbrido: tabelas e chaves estrangeiras preservam identidades e relações críticas;
  payloads JSON canônicos preservam o agregado completo sem acoplar o domínio ao SQLAlchemy.
- Projetos e catálogos são agregados de escrita. Documentos e elementos são projeções sincronizadas
  na mesma transação; evidências, propostas e decisões possuem repositórios auditáveis.
- A tabela `document_sources` guarda o caminho local e a impressão verificável do PDF separadamente
  do agregado; sua linha acompanha o ciclo de vida do documento por chave estrangeira.
- Uma unidade de trabalho exige `commit` explícito. Sair sem commit ou por uma exceção executa
  rollback e fecha a sessão.
- Projetos somente usam catálogos publicados. Uma versão publicada não pode ser alterada ou removida,
  e versões antigas continuam legíveis pelos projetos que as referenciam.
- A desativação de item ocorre em nova versão de catálogo; o item permanece no histórico com
  `ativo = false`.
- O backup usa um snapshot consistente do SQLite, valida a integridade do arquivo temporário e só
  então o publica por substituição atômica no mesmo diretório de destino.

## Portabilidade, fotos e recuperação

- Um pacote de projeto usa a extensão `.zphproj` e a versão de formato 1. Seu manifesto assinado
  declara projeto, catálogo, arquivos, tamanhos, tipos e hashes SHA-256.
- O pacote contém um SQLite migrado e restrito ao projeto, seus PDFs disponíveis, fotos gerenciadas e
  a projeção JSON do grafo. O banco continua sendo a fonte canônica; o grafo é derivado e sua
  assinatura é conferida na importação.
- Entradas do arquivo compactado devem possuir caminhos relativos seguros. Caminhos absolutos ou com
  travessia, duplicatas, links simbólicos, conteúdo criptografado e arquivos não declarados são
  recusados antes da aplicação dos dados.
- A ausência ou alteração de um PDF ou foto vira problema acionável de integridade. Ela não impede a
  abertura dos metadados e resultados ainda utilizáveis do projeto.
- Fotos JPEG, PNG, TIFF e WebP são armazenadas sob `project-files/<projeto>/photos`, com nome
  determinado pelo hash. Conteúdo igual é deduplicado fisicamente, embora possa permanecer vinculado
  a mais de um elemento.
- Remover uma foto elimina a cópia gerenciada somente quando nenhum elemento ainda a referencia.
  Localizar uma foto ou PDF exige correspondência exata de conteúdo; anexos antigos sem metadados
  verificáveis são adotados depois da primeira localização válida.
- Exportar e importar preserva IDs, catálogo, execuções, evidências, propostas, decisões de revisão e
  o conjunto confirmado. A substituição de um projeto já existente é explícita e as trocas de banco
  e arquivos possuem compensação em caso de falha.
- O backup completo usa `.zphbackup` e contém snapshot íntegro do banco, arquivos gerenciados e cópias
  dos PDFs externos. As referências do snapshot são reescritas para as cópias recuperáveis. A
  publicação do pacote e a substituição do banco restaurado são atômicas.
- O painel **Portabilidade e recuperação** oferece anexar, remover e localizar arquivos, exportar,
  importar, criar e restaurar backup e consultar o relatório, sempre com progresso, destino explícito
  e confirmação para operações de substituição.

## Fluxo operacional do MVP pela interface

- O painel **Fluxo do projeto** lista, cria, abre e renomeia projetos no SQLite. Em uma instalação
  vazia, o catálogo inicial publicado é persistido automaticamente antes da criação do primeiro
  projeto.
- Um ou vários PDFs podem ser selecionados e importados no projeto em uma transação única. A ordem
  selecionada define a paginação lógica, enquanto cada arquivo e sua referência verificável continuam
  independentes.
- Projetos podem ser excluídos após confirmação explícita. A exclusão remove banco, análises e estado
  local associados, preservando todos os arquivos PDF originais no sistema de arquivos.
- Um ou vários PDFs importados podem ser removidos seletivamente. A mesma transação elimina execuções,
  evidências, propostas, decisões e elementos confirmados cuja geometria ou dependências pertençam às
  folhas removidas; documentos e resultados independentes permanecem válidos.
- **Executar análise completa** processa todos os documentos do projeto fora da thread da interface,
  apresenta progresso e encadeia extração, interpretação e abertura da revisão humana.
- O usuário pode solicitar cancelamento. Resultados completos são preservados e a retomada reutiliza
  identidades determinísticas, sem duplicar execuções, evidências ou propostas.
- O painel apresenta documentos, folhas, estados das execuções, propostas pendentes e decisões. Cada
  execução de interpretação com propostas pode ser selecionada separadamente na revisão.
- O último projeto e a última folha são restaurados por estado local da interface. Os dados canônicos
  permanecem no SQLite; `ui-state.ini` guarda somente preferências de navegação reproduzíveis.
- Falhas de PDF ou pipeline são convertidas em mensagens visíveis e acionáveis. Nenhum fluxo de uso
  ou aceite requer terminal, fixture, edição de JSON ou acesso direto ao banco.

## Reconstrução do conjunto confirmado

A reconstrução é uma projeção derivada e reproduzível, nunca uma nova fonte de verdade. A visão
física usa postes e equipamentos; a visão elétrica usa pontos de rede e terminais. Cabos, ligações
terminal-ponto, conexões internas e relações confirmadas produzem arestas. Cabos paralelos são
preservados separadamente por um multigrafo. A projeção permanece não direcionada enquanto o
projeto não contiver origem e sentido de fluxo confirmados.

Uma assinatura canônica inclui entidades, relações, catálogo e geometria usados. Assim, a ordem de
inserção não altera o resultado e uma confirmação feita sobre uma versão desatualizada é recusada.
Conexões ausentes podem ser propostas pela proximidade entre geometrias confirmadas na mesma folha,
desde que nível, tensão e fases coincidam. Mais de um candidato compatível é tratado como ambíguo
e nenhuma proposta modifica o projeto sem confirmação humana registrada.

Os diagnósticos abrangem componentes desconectados, pontas órfãs, ciclos inesperados,
incompatibilidade de tensão/fases, incompatibilidade entre estrutura e cabo, equipamentos sem
terminais e continuidade interna desconhecida. Cada diagnóstico referencia as entidades envolvidas,
destaca-as na visão apropriada e, quando há geometria, permite navegar até a folha do PDF.

O painel **Grafo do projeto** expõe reconstrução, visões, filtros, diagnósticos, navegação e
confirmação de conexão. Somente a relação aceita e seu registro de revisão são persistidos; o grafo
é recalculado do conjunto confirmado sempre que solicitado.

## Fundamentação normativa

- A ND 3.1 vigente define expansão, reforma, reforço, modificação, manutenção e desativação como
  finalidades de projeto; exige dados georreferenciados e detalhamento de postes, vãos, equipamentos,
  cabos, pontos de entrega e caixas subterrâneas.
- A mesma norma estabelece que uma substituição não prevista seja tratada como uma retirada e uma
  instalação, origem do modelo `VinculoObra`.
- A ND 2.7 descreve derivações, junções, acessórios e terminais capazes de conectar cabos a outros
  cabos ou equipamentos, fundamento para `PontoRede` não depender sempre de um poste.

Fontes públicas oficiais: [normas de redes de distribuição da CEMIG](https://www.cemig.com.br/normas-tecnicas/normas-tecnicas-de-redes-de-distribuicao/),
[ND 3.1/2025](https://www.cemig.com.br/wp-content/uploads/2025/09/ND_3_1_2025.pdf),
[IT-EO-008 — Simbologia EO](https://www.cemig.com.br/wp-content/uploads/2025/10/IT-EO-008_Simbologia_EO.pdf)
e [ND 2.7](https://www.cemig.com.br/wp-content/uploads/2025/10/nd_2_7-1.pdf).

## Limites desta etapa

O pipeline ainda não classifica uma forma vetorial isolada sem texto ou OCR: caminhos de glifos,
carimbos e símbolos do AutoCAD são visualmente semelhantes e uma regra geométrica simples geraria
falsos positivos. Os limiares ainda precisam do conjunto formal anotado e do consenso humano da
Etapa 5; a verificação exploratória apenas comprovou que todos os dez PDFs locais atuais passaram a
gerar ao menos uma proposta de poste. A reconstrução do grafo ocorre sob comando e considera apenas
o conjunto confirmado; o pipeline nunca confirma propostas por conta própria. A confirmação
acontece exclusivamente pelos painéis de revisão humana. A importação, a extração, a interpretação,
a revisão, a reconstrução e a portabilidade estão integradas à interface do MVP, mas as Etapas 7,
7.1, 8 e 10 continuam aguardando o aceite humano em um projeto autorizado.

Como referência normativa geral, permanecem aplicáveis as [normas técnicas públicas de redes de distribuição da CEMIG](https://www.cemig.com.br/normas-tecnicas/normas-tecnicas-de-redes-de-distribuicao/), especialmente as famílias ND 2.x e ND 3.1 já levantadas para o projeto.
