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

<<<<<<< HEAD
O motor já possui:
=======
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
- `docs/catalogo-regras-conformidade.md` mantém a lista incremental das dez entradas do seed; a
  Etapa 2 confirmou as fontes, inativou a escala até suas exceções terem fatos positivos e incluiu
  cabo novo urbano e a compatibilidade rural simples entre estrutura e poste.
>>>>>>> 51a97e2ba161a5914a20d6988ea9270393104e55

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

<<<<<<< HEAD
O gate padrão usa fixtures sintéticas e não depende de arquivos locais. O script
`scripts/smoke_examples.py`
abre e percorre qualquer PDF presente em `examples/` somente quando solicitado. Uma regressão real
deve ser reduzida ao menor caso sintético que a reproduza antes de entrar no gate permanente.
=======
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
- Sinalizar resultado desatualizado quando a assinatura ativa ou a versão do método for diferente da
  usada; somente uma ação explícita gera uma nova execução.

### Testes e aceite

- A mesma entrada e revisão produzem IDs e payload determinísticos; nova revisão mantém o histórico.
- Regra desativada por um JSON importado não aparece na nova execução, mas continua no snapshot
  anterior; omitir seu ID em uma importação não a remove.
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
  callout, ocultar/exibir, reiniciar, importar uma segunda versão com `enabled=false` e reaplicar. O
  novo resultado não contém o achado, o histórico anterior é preservado e não existem controles
  individuais de ativação, desativação ou remoção.

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
E2E sintético: importar regra, analisar, listar divergência, mostrar callout, ocultar/exibir e
confirmar que a regra e o resultado sobrevivem ao reinício. Depois, importe o mesmo ID com
`enabled=false`, reaplique e confirme a ausência no resultado novo e a preservação do snapshot
anterior. Prove também que não existem controles individuais de ativação, desativação ou remoção.
Não derive novas normas dos comentários dos PDFs reais e não implemente ângulo ou cálculo
mecânico nesta etapa.

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
6. importar uma segunda versão da regra com `enabled=false`, reanalisar e confirmar que o snapshot
   anterior foi preservado e o resultado novo não contém mais o achado, sem comandos individuais de
   remoção, ativação ou desativação;
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
  numeração permanente, publicação atômica e fluxo pytest-qt de importar, substituir um mesmo ID,
  preservar omitidos, exportar e reiniciar — 33 testes aprovados no marco original; a revisão de
  13/08/2026 acrescentou as defesas contra remoção.
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
  `cemig-normas-distribuicao-2025.3` com oito entradas, sete ativas naquele marco; a salvaguarda da
  Regra 6 passou o seed para `2025.4` na revisão de 13/08/2026.
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
- **Testes focados:** domínio, migração, persistência, determinismo, imutabilidade, revisão de regra,
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
- **Limites do aceite:** não existe filtro de achados; somente a ordenação foi implementada e
  testada. A navegação real com renderização assíncrona entre páginas não possui um único E2E que
  percorra lista → viewer → callout → lista → dock; esses elos foram cobertos separadamente e, em
  parte, com stubs.
- **Limitações remanescentes:** o primeiro provedor técnico de vão e o aceite ponta a ponta de
  extensão de regras continuam reservados à Etapa 6.
- **Commit:** `feat(ui): control compliance callout visibility`.

### 2026-08-13 — Etapa 6 concluída

- **Arquivos principais:** contrato pequeno em `application/compliance_fact_providers.py`; composição
  explícita no bootstrap; provedor especializado em `application/span_compliance.py` sobre
  `detectar_vaos`; disponibilidade atualizada em `domain/compliance_facts.py`; E2E sintético em
  `tests/e2e/test_span_compliance_ui.py`.
- **Comportamento entregue:** `vao.comprimento_m` preserva a origem da medida, as evidências, a região,
  a página e a geometria do rótulo ou do cabo. Medidas por coordenadas conservam as evidências dos
  postes. Após a revisão complementar, `vao.excecao_45_60_demonstrada` só é publicado na faixa acima
  de 45 m e até 60 m, quando um marcador positivo referencia evidência existente na mesma página;
  ausência nunca vira `false` e não autoriza divergência nessa faixa.
- **Aceite ponta a ponta:** a interface importa uma regra sintética, analisa o vão divergente, lista o
  resultado, materializa o callout, reinicia e recupera regra/resultado, oculta e exibe a marcação,
  importa o mesmo ID com `enabled=false`, reaplica a conformidade e confirma sua ausência no novo
  snapshot sem apagar o histórico anterior.
- **Testes focados:** 70 testes de conformidade e E2E aprovados; medida anotada, coordenadas, ausência,
  exceção positiva, região/página, conforme/divergência/não avaliável e ciclo E2E com reinício estão
  cobertos.
- **Gate básico:** `IniciarTestes.bat` aprovado no Python 3.13.14 — 482 testes aprovados, 20 privados
  excluídos pelo gate, cobertura de 86,18%; Ruff, formatação, Mypy, dependências e complexidade
  aprovados.
- **Gate privado:** indisponível para os cinco arquivos iniciais, pois eles não correspondem às
  entradas/hashes do manifesto privado registrado. Sem manifesto válido, o gate opt-in não constitui
  aceite e nenhum dado identificável deve ser incluído em relatório.
- **Limites do aceite:** o E2E sintético injeta diretamente no banco a sessão semântica, o cabo, a
  evidência, a proposta e a decisão; portanto não valida extração/interpretação reais do PDF. A
  exceção positiva é exercitada por fixture, mas ainda não existe produtor real de
  `excecao_45_60_demonstrada`/`evidencia_excecao_45_60_id` no fluxo normal.
- **Limitações remanescentes:** não há provedor de ângulo nem cálculo mecânico. Exceções de vão exigem
  evidência positiva estruturada; comentários de PDFs não são fonte normativa nem podem ser
  promovidos a fatos técnicos do desenho.
- **Commit:** `feat(compliance): add span compliance provider`.

### 2026-08-13 — Revisão complementar das Etapas 5 e 6

- **Amostra inicial revisada:** cinco PDFs, seis páginas e quatro projetos de rede, com 20 anotações
  textuais `FreeText` de comissionamento. Um dos projetos também contém portadores `Square` de texto
  técnico AutoCAD SHX, que pertencem ao desenho e não são comentários. Um arquivo é acadêmico e fica
  corretamente fora do domínio de projetos de rede. Este registro conserva apenas contagens
  agregadas, sem nomes, textos, imagens, coordenadas ou caminhos dos arquivos.
- **Valor e limite dos comentários:** as anotações mostram como revisores comunicam lacunas, mas não
  constituem fonte normativa. Nenhum dos 20 comentários possui cobertura operacional integral pelas
  oito regras atuais (`0/20`); assim, a revisão não converteu seu conteúdo em novas obrigações
  automáticas.
- **Problemas encontrados:** conteúdo e aparência de anotações podiam contaminar a interpretação do
  desenho e originar propostas técnicas; uma medida de altura nominal `H.N` foi aceita como
  comprimento de vão; e o pipeline ignorava classificações urbana/rural literais presentes no
  cabeçalho quando `metadados.tipo_servico` estava vazio. A primeira tentativa de correção também
  mostrou que filtrar toda anotação apagaria os portadores SHX e que aceitar a palavra “rural” ou
  “urbana” em qualquer texto ativaria regras indevidamente. Houve ainda comprimentos
  ausentes/duplicados, associações ambíguas e elementos sem classificação suficiente para publicar
  tecnologia de cabo.
- **Correções implementadas e cobertas sinteticamente:** comentários de revisão e suas aparências são
  excluídos da interpretação, das regiões e dos fatos técnicos; anotações `Stamp` permanecem apenas
  como candidatas a evidência de controle documental, enquanto `Square` marcado como
  `AutoCAD SHX Text` é preservado; o OCR semântico usa `annots=False`; `H.N`, altura, engastamento,
  área e capacidade não entram na heurística de vão; servidão e rótulos de assinatura não nascem de
  `FreeText` de revisão; contexto só vem de metadado confirmado ou valor integral em campo permitido
  e rotulado do cabeçalho, rejeitando token solto, negação, nome próprio e conflito. A versão do
  método subiu para 3 e passa a invalidar resultados antigos.
- **Regra 6 e atualização:** automação `PARCIAL`. Até 45 m e acima de 60 m a aplicabilidade é
  resolvida pelo comprimento; acima de 45 m e até 60 m, a falta de prova positiva da exceção produz
  `NAO_AVALIAVEL`. Marcador fora da faixa não elimina divergência acima de 60 m. O seed `2025.4`
  migra apenas uma Regra 6 ainda idêntica ao seed oficial `2025.3`, preservando regras adicionais e
  sem sobrescrever uma Regra 6 personalizada.
- **Catálogo:** coerência desenho↔orçamento/materiais/potência/fases, cabo BT de tronco, cabo coberto
  rural, simbologia de poste e PRODR/fotos foram registrados apenas como candidatos
  `REVISAO_HUMANA`. As observações também reforçam `DOC-01/02`, `POST-01`, `STRUCT-01`, `GROUND-01`,
  `SPAN-R01`, `COMP-02`, `PROT-01` e `TOPO-01`; ajuste genérico de ramal e notas curtas/ambíguas
  continuam em revisão humana. Nenhum localizador ou obrigação foi inventado.
- **Revisão da Etapa 5:** ordenação, visibilidade individual/em lote e sincronização bidirecional
  permanecem cobertas, mas ainda não existe filtro de achados nem um único E2E com renderização
  assíncrona real que percorra toda a sequência lista → página → callout → lista → dock.
- **Revisão da Etapa 6:** o E2E continua sintético e injeta a sessão semântica; não prova a extração
  real dos PDFs. Não existe produtor real da prova excepcional acima de 45 m e até 60 m, nem provedor de ângulo ou
  cálculo mecânico. Por isso, a faixa excepcional e os novos candidatos permanecem conservadores.
- **Verificação desta revisão:** 130 testes públicos focados aprovados. O gate básico final aprovou
  512 testes, excluiu 20 privados, alcançou 86,39% de cobertura e passou em Ruff, formatação, Mypy,
  integridade das dependências e complexidade. A inspeção e o replay local dos cinco PDFs foram
  diagnósticos somente leitura, não expectativas derivadas do corpus.
- **Gate privado:** os cinco arquivos não correspondem ao manifesto privado autorizado; portanto o
  gate opt-in não foi usado como aceite. Novos candidatos exigem fonte oficial exata antes de qualquer
  automação.

### 2026-08-14 — Revisão da nova leva de PDFs comissionados

- **Escopo local:** dez PDFs de uma página, 51 anotações `FreeText` e leitura visual completa. Como
  os PDFs são ignorados pelo Git, a nova leva não é demonstrável por histórico; a correspondência
  exata das 20 anotações anteriores sustenta a inferência de seis folhas novas e 31 comentários
  adicionais. O registro mantém somente contagens agregadas.
- **Corpus formal:** os dez hashes locais são distintos entre si e nenhum corresponde aos nove
  hashes de `evaluation/manifesto-amostras.json`. As folhas permanecem exploratórias; o manifesto e
  o gate privado não foram alterados nem usados como aceite.
- **Revisão normativa dirigida:** a ND-2.2 Out/2016 foi consultada por texto e imagem nas páginas PDF
  14–15, 25, 68–69, 144 e 173–174; as páginas 57–60 e 66–67 da ND-3.1 Jul/2025 foram revalidadas.
  URL oficial, acesso, páginas e SHA-256 estão em `docs/inventario-fontes-normativas.md`.
- **Candidatos acrescentados:** `POST-TYPE-U01`, `RURAL-PRODR-01`, `RURAL-DERIV-01`,
  `RURAL-STAY-01` e `POST-ORIENT-R01` permanecem `AGUARDA_FATO`. `POST-EQUIP-U01` passou a
  `PARCIAL`: seus dois subconjuntos de transformador em posteação existente originaram as Regras 9
  e 10. `DOC-GD-01`, `COER-CAMPO-01` e `TOPO-DES-01` entraram como
  `REVISAO_HUMANA`. A indicação isolada de aterramento a cada 250 m foi recusada porque a ND-3.1
  vigente estabelece aproximadamente 200 m para o neutro urbano.
- **Oito regras preexistentes:** nenhuma obrigação foi alterada. Foram documentadas as limitações de
  escala global da Regra 3, associação de múltiplos vãos/exceções da Regra 6, situação por trecho da
  Regra 7 e escopo estrito da Regra 8. Regras 4 e 5 continuam sem provedor de ângulo; grandes vãos
  rurais não podem ativar a Regra 6 urbana.
- **Registro ativo:** o JSON passou a `2025.5` com as Regras 9 e 10. O provedor exige contexto urbano,
  transformador trifásico a instalar com código exato, poste existente positivamente identificado,
  uma relação confirmada e cardinalidade regional 1:1. Potência, resistência e formato permanecem
  correlacionados; formato canônico inferido não sustenta conformidade. Os demais candidatos ainda
  dependem de cálculo, tração, estai, documentos externos, estado de campo ou orientação. A versão
  do método de conformidade passou a `4`, invalidando explicitamente os snapshots anteriores.
- **Verificação:** o teste focado de paridade do catálogo aprovou `1/1`. O gate básico offline
  aprovou 525 testes, excluiu 20 privados, alcançou 86,46% de cobertura e passou em integridade das
  dependências, Ruff, formatação, Mypy e complexidade. Houve apenas aviso não bloqueante de cache do
  Pytest por permissão local.
- **Reavaliação topológica:** foram recusadas as formulações “toda derivação trifásica exige poste
  11 m/300 daN” e “todo vão rural CA novo tem máximo de 80 m”. A ND-2.2 condiciona os 80 m à
  alternativa sem estai contrário, com tração RDU e dimensionamento para vento máximo; a topologia
  existente não prova essas condições. Cabos e vãos conectados continuam fatos diagnósticos, não
  atalhos para uma obrigação mais ampla.
- **Migração:** bancos `2025.4` recebem somente os dois IDs oficiais ausentes. Conteúdo local com ID
  coincidente, Regras 1–8 e IDs personalizados são preservados; o mesmo vale após restauração, com
  merge local anterior às adições oficiais.
- **Commit:** não criado; mensagem sugerida: `feat(compliance): add existing-post transformer rules`.
>>>>>>> 51a97e2ba161a5914a20d6988ea9270393104e55
