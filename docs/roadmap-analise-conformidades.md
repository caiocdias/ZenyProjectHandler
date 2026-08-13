# Roadmap da análise de conformidades e do comissionamento visual

> Guia operacional para desenvolver a funcionalidade em sessões limpas do Codex. Execute uma etapa
> por sessão e sobre a `main` deixada pela etapa anterior. Este documento detalha a parte de
> conformidades da Etapa 12 de `docs/roadmap-desenvolvimento.md`.

## Objetivo

Ao concluir este ciclo, o usuário deve conseguir, pela aba **Conformidade**:

1. importar, ativar, desativar ou remover regras antes de analisar, sem alterar o código;
2. executar a análise com uma revisão imutável das regras ativas;
3. ver cada possível divergência com regra, mensagem, alvo, evidências e fonte;
4. localizar no visualizador uma caixa vermelha com o texto do erro e seta(s) para o alvo;
5. exibir ou ocultar cada marcação como já ocorre com os identificadores de elementos;
6. consultar um catálogo Markdown incremental que explique todas as regras existentes.

Os PDFs de exemplo mostram predominantemente anotações PDF `FreeTextCallout`: caixa e texto
vermelhos, uma linha de chamada com ponta de seta e, em alguns casos, mais de uma seta ou apenas a
caixa. Os comentários cobrem famílias diferentes - documentação ausente, compatibilidade de
materiais, dimensionamento, topologia e condições rural/urbano. Eles são evidência de como um
comissionador comunica um problema, mas **não são fonte normativa suficiente para criar uma regra**.

## Estado atual relevante

- `domain/compliance.py` já modela alvos, fatos, condições, regras e achados auditáveis.
- `adapters/compliance/json_registry.py` carrega o seed
  `adapters/compliance/data/regras_conformidade_v1.json`, hoje somente leitura.
- `application/compliance_evaluation.py` avalia `when`, `unless` e `must` de modo determinístico.
- `application/project_compliance.py` deriva fatos e resultados em memória ao abrir o painel.
- `ui/documentation_panel.py` lista documentação e conformidade, mas não gerencia regras nem mantém
  resultados de uma execução.
- `ui/pdf_viewer.py` desenha contornos e links de revisão; `ui/review_panel.py` já possui o padrão de
  botões de olho para ocultar região ou elemento.
- `docs/arquitetura-conformidade.md`, ADR 0011 e o schema em
  `docs/schemas/regras-conformidade.schema.json` são os contratos de referência.
- `docs/catalogo-regras-conformidade.md` mantém a lista incremental das oito entradas do seed; a
  Etapa 2 confirmou as fontes, inativou a escala até suas exceções terem fatos positivos e incluiu
  cabo novo urbano e a compatibilidade rural simples entre estrutura e poste.

## Decisões e limites para todas as etapas

1. O PDF original permanece somente leitura. Caixas e setas são uma camada do visualizador; exportar
   um novo PDF anotado não faz parte deste ciclo.
2. O SQLite é canônico. O JSON continua como seed e formato de importação/exportação.
3. Cada alteração de regras cria uma revisão imutável. “Remover” significa retirar da nova revisão
   ativa; revisões usadas em análises anteriores continuam recuperáveis.
4. A análise captura a assinatura e a versão das regras no início. Alterar regras nunca reinterpreta
   silenciosamente um resultado antigo.
5. Arquivos de regras só declaram condições do vocabulário suportado. Nunca execute Python,
   expressões ou scripts recebidos no JSON. Geometria, topologia e cálculos complexos pertencem a
   avaliadores Python pequenos e testáveis que publicam fatos.
6. Uma regra com chave fora do vocabulário deve ser recusada com diagnóstico claro. Chave conhecida
   cujo provedor ainda está planejado pode ser aceita com aviso e resulta em `NAO_AVALIAVEL`, não em
   reprovação, até que existam fatos suficientes.
7. Toda regra incorporada pelo projeto deve constar em `docs/catalogo-regras-conformidade.md`, com
   número sequencial estável, ID técnico, explicação do processo de análise, fonte exata, fatos,
   aplicabilidade, exceções, resultado e estado de automação. Regra alterada ou removida não some do
   histórico: é marcada como substituída, inativa ou removida. A mesma alteração de código/regras e
   catálogo deve ocorrer no mesmo commit. Registros importados pelo usuário também devem gerar uma
   versão Markdown local do catálogo ativo, sem editar silenciosamente os arquivos do repositório.
8. Uma marcação só recebe seta quando há página e geometria rastreáveis. Achado sem localização
   continua visível na lista com o estado **Sem localização no PDF**; não invente coordenadas.
9. A suíte pública usa apenas fixtures sintéticas. PDFs e anotações reais de `examples/` permanecem
   fora do Git e só podem participar do gate privado opt-in, sem nomes, texto, imagens, coordenadas ou
   caminhos nos relatórios.
10. Preserve a separação `domain -> application/ports -> adapters -> ui`, a execução offline, a
   cobertura acima de 85,01%, Ruff, formatação e Mypy.
11. Antes de editar, confira `git status` e preserve alterações alheias. Não use reset ou descarte de
    arquivos do usuário.
12. Ao finalizar cada etapa, atualize a tabela e o registro de execução deste documento. Execute os
    testes focados e `.\IniciarTestes.bat`. Se todos os testes e critérios de aceite passarem, faça o
    commit convencional indicado. Se não passarem, não crie o commit e relate a pendência.

## Ordem de execução

| Etapa | Estado inicial | Depende de | Entrega principal |
|---|---|---|---|
| 1. Registro configurável de regras | CONCLUÍDA | - | Importar/remover regras pela interface com revisão persistida |
| 2. Pesquisa normativa integral e expansão inicial | CONCLUÍDA | 1 | Inventário oficial e regras automatizáveis já incorporadas |
| 3. Execução e histórico de conformidade | CONCLUÍDA | 1, 2 | Resultado vinculado à análise e à revisão de regras |
| 4. Caixas e setas no visualizador | CONCLUÍDA | 3 | Callouts vermelhos ancorados em geometria rastreável |
| 5. Visibilidade e sincronização | CONCLUÍDA | 4 | Olho por achado e navegação bidirecional lista/PDF |
| 6. Primeiro avaliador técnico e aceite ponta a ponta | PENDENTE | 5 | Extensão comprovada sem codificar regras no motor |

Estados permitidos: `PENDENTE`, `EM ANDAMENTO`, `BLOQUEADA` e `CONCLUÍDA`.

## Etapa 1 - Registro configurável de regras

### Implementar

- Criar um catálogo explícito do vocabulário de fatos, incluindo as chaves planejadas já usadas pelo
  seed. Registrar chave, escopo, tipo de valor, operadores aceitos, descrição e disponibilidade do
  provedor. Validar uma regra importada contra esse catálogo, além das validações atuais do domínio.
- Persistir no SQLite snapshots imutáveis do registro: ID da revisão, versão informada, assinatura
  canônica, JSON canônico, data e indicador da revisão ativa. Sem normalizar cada condição em várias
  tabelas nesta etapa.
- No primeiro uso, criar a revisão ativa a partir do seed empacotado. Não modificar o seed ao editar.
- Criar porta, repositório SQLAlchemy e serviço de aplicação para consultar a revisão ativa, listar
  histórico, importar/mesclar regras, ativar/desativar e remover uma regra em uma nova revisão.
- Manter numeração incremental estável por ID de regra e gerar atomicamente, na pasta de dados do
  usuário, um `catalogo-regras-conformidade.md` legível para cada nova revisão ativa. Novas regras
  recebem o próximo número; números removidos nunca são reutilizados.
- Adicionar uma visão **Regras** ao painel de conformidade com tabela, detalhes e botões **Importar**,
  **Exportar**, **Ativar/desativar** e **Remover**. Importação deve mostrar resumo e pedir confirmação
  antes de substituir IDs existentes; remoção também exige confirmação.
- Aceitar pela interface o mesmo formato versionado de
  `docs/schemas/regras-conformidade.schema.json`. Mensagens de erro devem apontar regra, campo e
  motivo sem incluir o caminho absoluto do arquivo.

### Testes e aceite

- Migração sobe em banco vazio e em banco existente; o seed é criado uma única vez.
- Assinatura igual não cria revisão duplicada; uma mudança real cria outra revisão e preserva a
  anterior.
- Chave desconhecida, ID duplicado, operador incompatível e valor com tipo incorreto são
  recusados de forma atômica.
- Teste `pytest-qt`: importar uma regra sintética, desativá-la, reativá-la, removê-la, exportar o
  registro e reiniciar o painel; o estado persiste e nenhuma etapa exige editar JSON manualmente.
- O catálogo Markdown local é regenerado em cada revisão, conserva a numeração e descreve em
  linguagem humana `when`, `unless` e `must`; falha de escrita não deixa arquivo parcial.
- O painel deixa claro qual revisão está ativa e quantas regras ativas/inativas existem.

### Prompt para uma sessão limpa do Codex

```text
Implemente a Etapa 1 de docs/roadmap-analise-conformidades.md no repositório atual. Leia integralmente
esse roadmap, docs/arquitetura-conformidade.md, docs/adr/0011-conformidade-baseada-em-fatos.md,
docs/adr/0002-persistencia-sqlite-hibrida.md, o schema de regras e o código atual de domain/compliance.py,
adapters/compliance, ports/persistence.py, adapters/persistence e ui/documentation_panel.py. Confira
git status e preserve alterações não relacionadas.

Entregue um incremento vertical: catálogo das chaves de fatos suportadas e validação semântica;
snapshot imutável do registro no SQLite com migração, porta/repositório/serviço; seed idempotente; e
uma visão Regras no painel para importar, exportar, ativar/desativar e remover regras. Mantenha um
número incremental estável por ID e gere atomicamente no diretório de dados do usuário o arquivo
catalogo-regras-conformidade.md, explicando o processo de análise de cada regra. A importação usa o
schema JSON existente, mostra um resumo antes da confirmação e cria uma nova revisão ativa. Remover
nunca apaga revisões históricas nem reutiliza números. Não execute código vindo do JSON, não
normalize condições em excesso e não implemente ainda histórico de análises ou callouts no PDF.

Adicione testes unitários, de persistência e pytest-qt para os critérios da etapa. Atualize a
documentação afetada e o registro da etapa. Execute os testes focados e `.\IniciarTestes.bat`. Se
todos os testes e critérios de aceite passarem, faça o commit em inglês
`feat(compliance): add configurable rule registries`. Não faça commit com gate vermelho.
```

## Etapa 2 - Pesquisa normativa integral e expansão inicial das regras

### Implementar

- Fazer pesquisa web nas fontes primárias e oficiais vigentes. Começar pelo portal oficial de normas
  técnicas da CEMIG, pelas fontes já citadas no registro ativo e pelos documentos oficiais que elas
  referenciem diretamente quando essa referência afetar projeto, material, compatibilidade ou
  comissionamento. Não usar blogs, respostas de fóruns ou resumos comerciais como fonte normativa.
- Criar `docs/inventario-fontes-normativas.md` com documento, órgão emissor, revisão/data, URL oficial,
  data de acesso, SHA-256 do arquivo consultado, total de páginas, escopo lido e situação
  vigente/substituída/indisponível. Se uma norma exigir acesso licenciado, registrar a lacuna e não
  contornar o acesso.
- Ler integralmente cada documento incluído no escopo, página por página. Usar extração de texto para
  busca e índice, mas também renderizar e inspecionar tabelas, diagramas, notas, rodapés e páginas em
  que a extração falhe. Trechos de busca isolados não bastam para criar regra.
- Levantar candidatos de todas as famílias relevantes, incluindo presença documental, limites,
  estruturas, cabos, postes, equipamentos, proteção, aterramento, vãos, ambiente rural/urbano,
  topologia, cálculo e compatibilidade entre componentes. Para incompatibilidades, registrar os dois
  lados da combinação e todas as condições que alterem a conclusão.
- Classificar cada candidato no catálogo como `IMPLEMENTADA`, `PRONTA_PARA_REGRA`, `AGUARDA_FATO`,
  `REVISAO_HUMANA` ou `DESCARTADA`, sempre com justificativa. Só incorporar automaticamente regras
  cuja obrigação, aplicabilidade e exceções tenham citação oficial exata e cujos fatos já sejam
  produzidos com segurança. As demais entram no backlog documentado, nunca como reprovação genérica.
- Incluir no registro versionado as regras já automatizáveis, inclusive compatibilidades simples que
  possam ser expressas por `when`/`unless`/`must`. Criar um provedor determinístico pequeno apenas se
  o fato necessário for direto e o escopo continuar cabendo nesta etapa; cálculos ou visão
  computacional novos ficam para etapa própria.
- Atualizar `docs/catalogo-regras-conformidade.md` no mesmo commit. Cada entrada deve explicar
  “Regra N consiste em...”, processo de análise, fatos observados, condições, exceções, possível erro,
  fonte exata, estado de automação e testes. Não copiar extensos trechos protegidos da norma.

### Testes e aceite

- O inventário comprova leitura de todas as páginas de cada fonte no escopo e registra claramente
  documentos inacessíveis, substituídos ou fora de escopo; nenhuma lacuna vira regra presumida.
- Toda regra incorporada possui documento, revisão, item e página verificáveis na fonte oficial, mais
  casos sintéticos de conforme, divergência, não avaliável e exceção quando aplicável.
- Teste automático garante correspondência um-para-um entre IDs das regras incorporadas e entradas
  ativas do catálogo, além de números sequenciais únicos e nunca reutilizados.
- Pelo menos uma família de compatibilidade entre elementos é examinada integralmente. Se houver
  combinação automatizável com os fatos atuais, ela é incluída e testada; caso contrário, o catálogo
  registra exatamente quais fatos/provedores faltam.
- URLs, hashes, IDs, contagens e paráfrases podem ser versionados; PDFs normativos baixados e material
  licenciado só são versionados quando a licença permitir expressamente.

### Prompt para uma sessão limpa do Codex

```text
Implemente a Etapa 2 de docs/roadmap-analise-conformidades.md sobre a main que contém a Etapa 1. Leia
integralmente esse roadmap, docs/catalogo-regras-conformidade.md, docs/arquitetura-conformidade.md,
ADR 0011, o registro ativo, o catálogo técnico e os schemas. Confira git status e preserve trabalho
alheio.

Esta etapa exige pesquisa web e leitura integral das normas de referência. Use somente fontes
primárias oficiais: comece pelo portal vigente de normas técnicas da CEMIG, confirme revisão e URL
de cada fonte já citada e siga referências oficiais diretas relevantes. Baixe cópias de trabalho em
pasta temporária, registre SHA-256 e total de páginas, extraia texto para indexação e renderize as
páginas para revisar também tabelas, figuras, notas e conteúdo sem texto. Leia todas as páginas do
escopo; não crie regra a partir de snippet de busca, comentário dos PDFs de exemplo ou fonte
secundária. Respeite acesso licenciado e direitos autorais, usando paráfrases curtas no repositório.

Crie docs/inventario-fontes-normativas.md e expanda o catálogo incremental. Pesquise sistematicamente
presença documental, limites, estruturas, cabos, postes, equipamentos, proteção, aterramento, vãos,
contexto rural/urbano, topologia, cálculos e compatibilidade entre componentes. Para cada candidato,
registre citação exata, aplicabilidade, exceções, fatos necessários e estado IMPLEMENTADA,
PRONTA_PARA_REGRA, AGUARDA_FATO, REVISAO_HUMANA ou DESCARTADA. Incorpore ao registro versionado apenas
as regras inequívocas e automatizáveis com fatos confiáveis; inclua compatibilidades simples quando
possível. Não transforme ausência de detector em divergência.

Crie testes sintéticos de conforme, divergência, não avaliável e exceção para cada regra incluída e
um teste de paridade entre registro e docs/catalogo-regras-conformidade.md. Atualize o registro da
etapa, rode os testes focados e `.\IniciarTestes.bat`. Se a pesquisa documentada estiver completa no
escopo declarado e todos os testes/aceites passarem, faça o commit em inglês
`feat(compliance): expand rules from normative review`. Não faça commit com fonte sem rastreabilidade
ou gate vermelho.
```

## Etapa 3 - Execução e histórico de conformidade

### Implementar

- Criar um caso de uso único para analisar conformidade a partir da sessão semântica mais recente e
  de uma revisão explícita de regras. O fluxo principal e o botão do painel devem chamar o mesmo caso
  de uso.
- Capturar a revisão ativa no início da análise. Persistir um snapshot do resultado com projeto,
  execuções semânticas de origem, versão/assinatura das regras, horário, alvos, fatos, achados e itens
  documentais. Um payload canônico com metadados indexados é suficiente; evite tabelas por operador.
- Preservar no achado os fatos relevantes e o resultado de cada condição necessária para explicar a
  decisão e localizar o valor que violou a regra, sem duplicar a evidência bruta.
- Executar esse caso de uso ao final de `ServicoFluxoMvp.executar_pipeline`, antes de anunciar
  conclusão. Cancelamento ou falha não pode deixar uma execução de conformidade parcial.
- Adicionar **Analisar conformidade** ao painel para reaplicar a revisão ativa aos resultados
  semânticos já persistidos, sem reabrir nem regravar o PDF e sem repetir OCR.
- Fazer a aba **Conformidade** ler a última execução persistida. Exibir possíveis divergências
  primeiro e incluir resultado, severidade, texto específico com valor observado/esperado quando
  houver, alvo, fonte, versão das regras e estado de localização.
- Sinalizar resultado desatualizado quando a assinatura ativa for diferente da assinatura usada;
  somente uma ação explícita gera uma nova execução.

### Testes e aceite

- A mesma entrada e revisão produzem IDs e payload determinísticos; nova revisão mantém o histórico.
- Regra removida não aparece na nova execução, mas continua no snapshot anterior.
- Falha/cancelamento faz rollback completo. Reabrir o aplicativo recupera a última execução.
- Teste de integração do fluxo: uma fixture sintética divergente conclui a análise, atualiza o painel
  automaticamente e mostra mensagem observada/esperada; casos conforme e não avaliável continuam
  distintos.
- O botão de reaplicação não chama OCR nem o analisador PyMuPDF.

### Prompt para uma sessão limpa do Codex

```text
Implemente a Etapa 3 de docs/roadmap-analise-conformidades.md sobre a main que contém as Etapas 1 e 2. Leia
o roadmap, docs/arquitetura-conformidade.md, ADR 0011 e o estado atual de application/mvp_workflow.py,
application/project_compliance.py, application/compliance_evaluation.py, persistence,
ui/project_panel.py, ui/documentation_panel.py, bootstrap.py e os testes relacionados. Confira git
status e preserve trabalho alheio.

Crie um caso de uso único que capture a revisão ativa no início, avalie a sessão semântica e persista
atomicamente o snapshot auditável da execução de conformidade. Integre-o ao fim do pipeline e a um
botão Analisar conformidade que reaplica regras sem repetir extração/OCR. O painel deve carregar a
última execução, mostrar divergências primeiro, valores observados/esperados, fonte e revisão, e
indicar quando o resultado ficou desatualizado. Preserve históricos e não reinterprete resultados
silenciosamente. Ainda não desenhe caixas ou setas.

Implemente migração, portas, adaptadores, composição e testes unitários/integrados/pytest-qt,
incluindo rollback, determinismo, reinício e prova de que reaplicar não chama OCR. Atualize a
documentação e o registro da etapa. Rode os testes focados e `.\IniciarTestes.bat`. Se tudo passar e
os critérios de aceite estiverem satisfeitos, faça o commit em inglês
`feat(compliance): persist compliance analysis results`. Não faça commit com gate vermelho.
```

## Etapa 4 - Caixas e setas no visualizador

### Implementar

- Criar uma projeção de apresentação, sem Qt no domínio, que converta cada divergência localizável em
  `id`, página, texto, caixa sugerida e uma ou mais âncoras. Priorizar a geometria dos fatos que
  decidiram o achado, depois suas evidências e por fim o alvo; usar somente itens da mesma página e
  com proveniência rastreável.
- Criar uma camada própria de callouts em `PdfGraphicsView`, separada dos links de revisão de
  elementos e do contorno temporário de seleção. Cada callout deve ter caixa branca, borda/texto
  vermelhos e linha(s) com ponta de seta aberta, seguindo visualmente os exemplos.
- Posicionar as caixas por algoritmo determinístico simples: testar posições ao redor da âncora,
  limitar à página e evitar sobreposição entre callouts já colocados. Se não houver posição livre,
  usar a posição válida de menor colisão; não criar um otimizador genérico.
- Quebrar texto, impor largura mínima/máxima e preservar legibilidade em A4/A3, retrato/paisagem,
  zoom, rotação e renderização progressiva por tiles.
- Recalcular a camada ao trocar página ou transformador, sem alterar o PDF e sem entrar no raster de
  cache.

### Testes e aceite

- Testes puros cobrem escolha de posição, contenção na página, colisão, múltiplas âncoras e
  determinismo.
- Testes `pytest-qt` comprovam caixa, texto, linhas e pontas de seta na página correta; zoom, rotação,
  redimensionamento e troca de página não deslocam a âncora.
- Callouts e sublinhados de elementos coexistem na cena, em camadas independentes.
- Achado sem página/geometria não cria item gráfico e permanece listado como **Sem localização no
  PDF**.
- Gerar fixtures sintéticas de A4 e A3 e inspecionar as imagens renderizadas: texto legível, caixa
  dentro da folha, seta no alvo e ausência de sobreposição evitável.

### Prompt para uma sessão limpa do Codex

```text
Implemente a Etapa 4 de docs/roadmap-analise-conformidades.md sobre a main com as Etapas 1 a 3. Leia o
roadmap, ADR 0003, ADR 0011, application/project_compliance.py, domain/values.py,
adapters/pdf/coordinates.py, ui/pdf_viewer.py, ui/pdf_rendering.py e os testes do visualizador.
Confira git status e preserve alterações não relacionadas.

Crie uma projeção testável de callout por divergência localizável e uma camada gráfica independente
no visualizador: caixa branca com borda/texto vermelhos e uma ou mais linhas com seta aberta. Use
somente geometrias rastreáveis, posicione deterministicamente ao redor do alvo, mantenha tudo dentro
da página e reduza colisões com um conjunto pequeno de posições candidatas. Garanta texto quebrado e
legível em A4/A3, retrato/paisagem, zoom, rotação e tiles. Não altere o PDF original e não implemente
ainda os botões de visibilidade da Etapa 5.

Adicione testes puros e pytest-qt, produza fixtures sintéticas e faça verificação visual dos renders.
Atualize a documentação e o registro da etapa. Rode os testes focados e `.\IniciarTestes.bat`. Se
tudo passar e os critérios de aceite estiverem satisfeitos, faça o commit em inglês
`feat(pdf): render compliance callouts`. Não faça commit com gate vermelho.
```

## Etapa 5 - Visibilidade e sincronização entre lista e PDF

### Implementar

- Adicionar uma coluna de visibilidade à árvore de conformidade com `QToolButton` de olho por achado,
  seguindo ícone, estado, tooltip e acessibilidade usados por `ReviewPanelWidget`.
- Manter conjuntos de IDs ocultos por sessão/projeto. Ocultar não apaga nem altera o achado; a
  preferência temporária sobrevive à troca de página e é reiniciada ao trocar de projeto ou gerar
  nova execução.
- Oferecer **Exibir todos** e **Ocultar todos** para os achados localizáveis, sem afetar
  identificadores de elementos, tiles ou contorno de seleção.
- Selecionar uma linha deve abrir/centralizar a página e realçar seu callout. Clicar na caixa ou seta
  deve selecionar a linha correspondente e trazer o dock de documentação/conformidade para frente.
- Achados sem localização mantêm o olho desabilitado e tooltip explicativo. Filtros ou ordenação não
  podem tornar visível um achado explicitamente ocultado.

### Testes e aceite

- Testes `pytest-qt` cobrem olho individual, ações em lote, troca de página/projeto, nova execução,
  filtro/ordenação, tooltips e nomes acessíveis.
- Ocultar uma marcação não oculta o sublinhado de elemento; ocultar um elemento não oculta a
  marcação de conformidade.
- Seleção funciona nos dois sentidos e não cria ciclos de sinais nem troca de página redundante.
- Com vários erros na mesma página, cada olho controla somente o callout correspondente.

### Prompt para uma sessão limpa do Codex

```text
Implemente a Etapa 5 de docs/roadmap-analise-conformidades.md sobre a main com as Etapas 1 a 4. Leia o
roadmap e o comportamento atual de ui/review_panel.py, ui/documentation_panel.py, ui/pdf_viewer.py,
ui/main_window.py e seus testes. Confira git status e preserve trabalho não relacionado.

Replique para os achados localizáveis o padrão de olho já usado nos identificadores de elementos,
mantendo camadas e estados totalmente independentes. Adicione olho por achado, Exibir todos e
Ocultar todos; preserve ocultação temporária ao navegar e reinicie-a ao trocar projeto ou execução.
Sincronize seleção nos dois sentidos: linha abre/centraliza/realça callout e clique no callout
seleciona a linha e eleva o dock. Achado sem geometria continua listado com controle desabilitado e
diagnóstico. Evite ciclos de sinais e não altere o PDF.

Adicione testes pytest-qt para todos os critérios, atualize a documentação e o registro da etapa.
Rode os testes focados e `.\IniciarTestes.bat`. Se tudo passar e o aceite estiver satisfeito, faça o
commit em inglês `feat(ui): control compliance callout visibility`. Não faça commit com gate
vermelho.
```

## Etapa 6 - Primeiro avaliador técnico e aceite ponta a ponta

### Implementar

- Extrair de `application/project_compliance.py` um contrato pequeno de provedores de fatos por
  família, sem criar descoberta dinâmica de plugins. Os provedores são compostos explicitamente no
  bootstrap e continuam funções/classes Python determinísticas.
- Implementar o primeiro provedor especializado usando capacidade já existente: publicar
  `vao.comprimento_m`, sua origem e a geometria do cabo/rótulo a partir de `detectar_vaos`, associando
  o fato à região correta. Publicar a exceção somente quando houver evidência positiva; caso contrário
  não inventar `false`.
- Fazer a regra de vão já existente produzir conforme/divergência/não avaliável e callout conforme os
  fatos disponíveis. Não implementar ângulo, esforço mecânico ou outras fórmulas sem detector e fonte
  aprovados.
- Documentar o caminho mínimo para a próxima regra: confirmar fonte -> definir fato no catálogo ->
  implementar/testar provedor se necessário -> importar regra declarativa -> executar análise ->
  calibrar apenas na partição privada de desenvolvimento.
- Criar um cenário E2E sintético que use a interface para importar regra, analisar, ver o erro e o
  callout, ocultar/exibir, remover a regra, reaplicar e confirmar que o novo resultado não a contém.

### Testes e aceite

- Casos sintéticos cobrem comprimento anotado, comprimento por coordenadas, dado ausente, exceção
  comprovada e associação à região/página corretas.
- O E2E reinicia o aplicativo e comprova persistência das regras e resultados, sem rede nem corpus
  privado.
- `.\IniciarTestesPrivados.bat` é opcional e somente pode ser executado em ambiente autorizado; seu
  relatório deve conter apenas IDs anônimos e contagens.
- O gate básico completo passa. A documentação deixa explícito o que ainda é não avaliável e como
  acrescentar a próxima família de fatos sem modificar o avaliador declarativo.

### Prompt para uma sessão limpa do Codex

```text
Implemente a Etapa 6 de docs/roadmap-analise-conformidades.md sobre a main com as Etapas 1 a 5. Leia o
roadmap, docs/arquitetura-conformidade.md, ADR 0011, application/project_compliance.py,
application/spans.py, ui/documentation_panel.py, ui/pdf_viewer.py e os testes E2E existentes. Confira
git status e preserve mudanças alheias.

Crie um contrato explícito e pequeno para provedores de fatos e extraia o necessário do módulo
monolítico sem alterar resultados atuais. Implemente como primeiro provedor especializado o fato
vao.comprimento_m usando detectar_vaos, preservando origem, evidência, região, página e geometria.
Exceção só existe com prova positiva. Faça a regra de vão atual atravessar o fluxo completo e crie um
E2E sintético: importar regra, analisar, listar divergência, mostrar callout, ocultar/exibir, remover
regra, reaplicar e confirmar sua ausência; reinicie a aplicação para provar persistência. Não derive
novas normas dos comentários dos PDFs reais e não implemente ângulo ou cálculo mecânico nesta etapa.

Atualize a documentação com a receita para futuras famílias de fatos e o registro da etapa. Execute
testes focados, E2E e `.\IniciarTestes.bat`. Rode `.\IniciarTestesPrivados.bat` apenas se o ambiente
autorizado estiver completo, sem expor conteúdo. Se todos os testes e critérios de aceite passarem,
faça o commit em inglês `feat(compliance): add span compliance provider`. Não faça commit com gate
vermelho.
```

## Definição de pronto do ciclo

O ciclo está tecnicamente pronto quando as seis etapas estiverem concluídas e o seguinte fluxo
funcionar sem terminal:

1. abrir **Documentação e conformidade > Regras** e importar uma regra válida;
2. executar a análise do projeto ou reaplicar somente a conformidade;
3. encontrar a possível divergência com explicação e fonte na aba **Conformidade**;
4. selecionar o achado e ver caixa/seta corretamente ancoradas no PDF;
5. ocultar e exibir a marcação sem afetar os identificadores de elementos;
6. remover a regra, reanalisar e confirmar que o histórico antigo foi preservado e o resultado novo
   não contém mais o achado;
7. abrir o catálogo Markdown e localizar a descrição incremental de cada regra usada na análise.

## Registro de execução

Ao concluir uma etapa, acrescente uma entrada curta com data, arquivos principais, testes executados,
resultado do gate, limitações remanescentes e mensagem do commit. Toda alteração de regra também
atualiza `docs/catalogo-regras-conformidade.md`. Não copie conteúdo dos PDFs reais.

### 2026-08-12 — Etapa 1 concluída

- **Arquivos principais:** catálogo de fatos em `domain/compliance_facts.py`; validação JSON em
  `adapters/compliance`; serviço em `application/compliance_registry.py`; migração e repositório em
  `adapters/persistence`; visão **Regras** em `ui/documentation_panel.py`.
- **Testes focados:** validação semântica/schema, snapshots e migração, seed idempotente, assinatura,
  numeração permanente, publicação atômica e fluxo pytest-qt de importar, desativar, reativar,
  remover, exportar e reiniciar — 33 testes aprovados.
- **Gate básico:** `IniciarTestes.bat` aprovado; corpus privado não acessado.
- **Limitações remanescentes:** histórico de execuções de conformidade, callouts no PDF e provedores
  de ângulo/vão continuam reservados às Etapas 3, 4 e 6.
- **Commit:** `feat(compliance): add configurable rule registries`.

### 2026-08-12 — Etapa 2 concluída

- **Fontes e escopo:** portal oficial vigente conferido; ND 2.7, ND 2.9, ND 3.1, ND 4.15 e ND 9.3
  lidas integralmente, totalizando 493 páginas. URLs, revisões, SHA-256, páginas sem camada textual,
  referências diretas e limites de acesso estão em `docs/inventario-fontes-normativas.md`.
- **Arquivos principais:** inventário normativo e catálogo incremental em `docs`; fatos positivos em
  `domain/compliance_facts.py`; provedores em `application/project_compliance.py`; seed versionado
  `cemig-normas-distribuicao-2025.3` com oito entradas, sete ativas.
- **Regras incorporadas:** proibição de cabo convencional em construção urbana nova e
  incompatibilidade rural inequívoca entre cinco estruturas MT e poste de concreto duplo T. A regra
  de escala foi inativada até que suas exceções possam ser representadas por fatos confiáveis; a
  ausência de detector de risco passou a produzir `NAO_AVALIAVEL`.
- **Testes focados:** conforme, divergência, não avaliável e exceção de contexto para cada regra nova,
  além da paridade registro/catálogo — 30 testes aprovados.
- **Gate básico:** `IniciarTestes.bat` aprovado no Python 3.13.14 — 451 testes aprovados, 20 privados
  excluídos pelo gate, cobertura de 85,48%; Ruff, formatação, Mypy e complexidade aprovados.
- **Limitações remanescentes:** ângulo, vão, proteção, aterramento, topologia e cálculos permanecem
  documentados como candidatos dependentes de novos fatos ou revisão humana; normas licenciadas e
  documentos oficiais reservados não foram contornados nem incorporados.
- **Commit:** `feat(compliance): expand rules from normative review`.

### 2026-08-12 — Etapa 3 concluída

- **Arquivos principais:** execução auditável em `domain/compliance.py`; caso de uso único em
  `application/compliance_analysis.py`; migração `0007_compliance_executions`, repositório e porta de
  persistência; composição no pipeline/bootstrap; leitura e reanálise explícita em
  `ui/documentation_panel.py`.
- **Comportamento entregue:** revisão ativa capturada no início; snapshot canônico e atômico com
  condições observadas/esperadas; IDs determinísticos; histórico imutável; rollback integral; última
  execução recuperada após reinício; divergências primeiro e sinalização de resultado desatualizado.
- **Testes focados:** domínio, migração, persistência, determinismo, imutabilidade, remoção de regra,
  rollback por falha/cancelamento, reinício, integração do pipeline e pytest-qt/E2E de reanálise sem
  PyMuPDF nem OCR — 102 testes focados aprovados.
- **Gate básico:** `IniciarTestes.bat` aprovado no Python 3.13.14 — 457 testes aprovados, 20 privados
  excluídos pelo gate, cobertura de 85,65%; Ruff, formatação, Mypy, dependências e complexidade
  aprovados.
- **Limitações remanescentes:** caixas, setas, visibilidade por achado e sincronização bidirecional
  continuam reservadas às Etapas 4 e 5; coleta de campo e novos avaliadores técnicos permanecem na
  Etapa 6.
- **Commit:** `feat(compliance): persist compliance analysis results`.

### 2026-08-12 — Etapa 4 concluída

- **Arquivos principais:** projeção sem Qt em `application/compliance_callouts.py`; camada vetorial
  independente em `ui/pdf_viewer.py`; integração dos resultados persistidos em
  `ui/documentation_panel.py`; fixtures e testes sintéticos em `tests`.
- **Comportamento entregue:** somente divergências com proveniência rastreável produzem callout;
  fatos decisivos, suas evidências e o alvo formam a precedência; caixas contidas e posicionadas por
  candidatos determinísticos reduzem colisões; texto quebrado, fundo branco, borda/texto vermelhos e
  setas abertas permanecem alinhados em zoom, rotação, troca de página e tiles, sem alterar o PDF.
- **Testes e inspeção visual:** 82 testes focados aprovados; renders sintéticos A4/A3 em retrato e
  paisagem inspecionados com texto legível, caixas contidas e duas setas abertas alinhadas ao alvo.
- **Gate básico:** `IniciarTestes.bat` aprovado no Python 3.13.14 — 466 testes aprovados, 20 privados
  excluídos pelo gate, cobertura de 85,88%; Ruff, formatação, Mypy, dependências e complexidade
  aprovados.
- **Limitações remanescentes:** visibilidade por achado, realce e sincronização bidirecional
  lista/PDF continuam reservados à Etapa 5; novos provedores técnicos permanecem na Etapa 6.
- **Commit:** `feat(pdf): render compliance callouts`.

### 2026-08-12 — Etapa 5 concluída

- **Arquivos principais:** estado e controles por achado em `ui/documentation_panel.py`; seleção,
  realce e clique vetorial em `ui/pdf_viewer.py`; elevação do dock em `ui/main_window.py`; ícone de
  olho compartilhado em `ui/visibility.py`.
- **Comportamento entregue:** olho individual, **Exibir todos** e **Ocultar todos** afetam somente
  callouts localizáveis; a ocultação temporária persiste em navegação e ordenação e reinicia ao
  trocar projeto ou execução; achados sem geometria mantêm controle desabilitado e diagnóstico
  acessível; lista e caixa/seta sincronizam seleção nos dois sentidos sem ciclos de sinais.
- **Testes focados:** projeção, painel, viewer, janela principal, persistência e regras — 48 testes
  aprovados, incluindo dois erros na mesma página, independência das camadas, lote, tooltip, nome
  acessível, troca de página/projeto/execução, ordenação, caixa, seta e elevação do dock.
- **Gate básico:** `IniciarTestes.bat` aprovado no Python 3.13.14 — 470 testes aprovados, 20 privados
  excluídos pelo gate, cobertura de 86,04%; Ruff, formatação, Mypy, dependências e complexidade
  aprovados. O corpus privado não foi acessado.
- **Limitações remanescentes:** o primeiro provedor técnico de vão e o aceite ponta a ponta de
  extensão de regras continuam reservados à Etapa 6.
- **Commit:** `feat(ui): control compliance callout visibility`.
