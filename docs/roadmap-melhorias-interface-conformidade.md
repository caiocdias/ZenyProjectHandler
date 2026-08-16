# Roadmap — legibilidade das conformidades e identidade visual

## Objetivo

Entregar as melhorias abaixo sem reestruturar a arquitetura existente:

- apresentar nomes compreensíveis em vez de chaves internas como
  `projeto.documentacao_gd_identificada` e `regiao.chave_fusivel_presente`;
- mostrar no PDF uma caixa legível para toda divergência que tenha localização rastreável,
  inclusive alvos pontuais como `P2`;
- posicionar caixas próximas ao erro, em espaço livre, sem sobreposição entre caixas;
- permitir ativar e desativar a quebra de linha em todas as tabelas de dados;
- alternar entre tema claro e escuro e lembrar a escolha na máquina;
- usar um ícone minimalista próprio, disponibilizado em PNG e ICO.

O roteiro considera o estado do projeto no commit `2f375ef`. Se os arquivos mudarem, os critérios de
aceite abaixo prevalecem sobre os nomes e linhas citados.

## Situação atual que deve ser preservada

- A aplicação é PySide6 e aplica apenas o tema claro em `ui/theme.py`.
- `bootstrap.py` já define nome/organização do `QApplication` e passa
  `%LOCALAPPDATA%\ZenyProjectHandler\ui-state.ini` à janela. O mesmo arquivo pode guardar o tema;
  não é necessária uma nova base de dados.
- `application/compliance_callouts.py` já projeta divergências, quebra texto e tenta posições ao redor
  do alvo e em uma grade. `ui/pdf_viewer.py` já desenha caixa, texto e setas em camada própria. A
  implementação deve evoluir esse fluxo, não criar uma segunda camada de anotações.
- `DocumentationPanelWidget` já sincroniza a linha da conformidade com o callout e possui controles
  para exibir/ocultar marcações.
- O vocabulário de fatos em `domain/compliance_facts.py` já associa cada chave técnica a uma
  descrição em português.
- As tabelas visíveis são principalmente `QTreeWidget` e `QTableWidget` em
  `ui/documentation_panel.py` e `ui/review_panel.py`. Hoje usam linhas uniformes ou não recalculam a
  altura para exibir textos longos.
- Não há assets próprios nem ícone configurado no `QApplication`/`MainWindow`.

## Regras para todas as etapas

- Antes de editar, conferir `git status` e preservar alterações não relacionadas.
- Manter chaves e IDs técnicos no domínio, persistência, importação/exportação, auditoria e logs. A
  tradução é de apresentação; não deve exigir migração de dados nem alterar o formato dos registros
  JSON.
- Não modificar o PDF original. Caixas e setas continuam sendo sobreposições da interface.
- Usar fixtures sintéticas pequenas nos testes; `examples/` serve apenas para inspeção manual
  opcional e não entra no gate.
- Em cada etapa, rodar primeiro os testes focados e depois `./IniciarTestes.bat`. Uma etapa só é
  aceita com o gate completo verde e sem regressão visual/funcional do fluxo existente.
- Atualizar este roadmap marcando a etapa como concluída apenas depois de cumprir todos os critérios
  de aceite. Não adicionar frameworks ou abstrações genéricas sem uso imediato.

---

## Etapa 1 — linguagem amigável em conformidades e regras

### Resultado esperado

Nenhuma tela, tooltip ou caixa do PDF exibe chaves internas de fatos. O usuário lê frases em
português, valores booleanos como “Sim”/“Não”, operadores traduzidos e alvos com nomes naturais.

### Implementação

- Criar um pequeno formatador de apresentação de conformidade, próximo da UI, que consulte
  `fato_conformidade_por_chave` em `domain/compliance_facts.py` e transforme uma chave conhecida em
  seu nome/descrição amigável. Não duplicar um dicionário separado com todas as chaves.
- Usar o formatador nas colunas **Observado** e **Esperado**, nos detalhes de regras e em qualquer
  tooltip/mensagem apresentada ao usuário. Traduzir também operadores, quantificadores, enumerações
  e booleanos. Preservar unidades e valores numéricos.
- Substituir `when`, `unless` e `must` por **Aplicável quando**, **Exceto quando** e **Deve atender**.
- Remover a exposição normal de **ID técnico** e `ID:` no painel de regras. O ID continua disponível
  internamente e no JSON exportado. Se for necessário para suporte, pode ficar em uma ação explícita
  de copiar detalhes técnicos, não na visualização comum.
- Garantir que rótulos de alvo usem nomes como “Projeto …”, “Documento …”, “Página …”, “Região …” ou
  “Poste P2”, sem enumerações em caixa alta nem caminhos de objeto.
- Fazer o texto enviado ao callout usar a mesma apresentação amigável da tabela, para evitar duas
  descrições diferentes do mesmo achado.

Arquivos candidatos: `ui/documentation_panel.py`, um novo módulo pequeno em `ui/`,
`domain/compliance_facts.py`, `application/compliance_callouts.py` e testes de conformidade/UI.

### Testes e aceite

- Teste unitário cobre chave conhecida, booleanos, texto, número/unidade, operador e valor ausente.
- Teste de integração monta uma regra com
  `projeto.documentacao_gd_identificada` e outra com `regiao.chave_fusivel_presente`; as chaves não
  aparecem em textos de células, detalhes, tooltips nem callouts.
- O JSON importado/exportado e os snapshots persistidos continuam contendo as chaves originais.
- Uma regra e um achado continuam selecionáveis/navegáveis pelo ID interno, mesmo sem mostrá-lo.
- Busca de regressão sugerida:
  `rg -n "chave_fato|\.chave_fato|when:|unless:|must:" src/zeny_project_handler/ui` não encontra
  renderização direta para o usuário.

### Mensagem para uma sessão limpa do Codex

```text
Implemente a Etapa 1 de docs/roadmap-melhorias-interface-conformidade.md. Leia o roadmap inteiro e
inspecione principalmente domain/compliance_facts.py, domain/compliance.py,
ui/documentation_panel.py, application/compliance_callouts.py e os testes relacionados. Confira git
status e preserve mudanças não relacionadas.

Crie uma camada pequena de apresentação que reutilize o catálogo de fatos para exibir nomes
amigáveis. Aplique-a às colunas Observado/Esperado, aos detalhes das regras, tooltips, alvos e textos
de callout. Traduza booleanos, operadores e títulos when/unless/must. IDs e chaves técnicas devem
continuar intactos no domínio, persistência, logs e JSON, mas não podem aparecer na interface normal.
Não crie migração nem um segundo catálogo duplicado.

Implemente os testes e critérios de aceite da etapa. Rode os testes focados e depois
./IniciarTestes.bat. Ao terminar, informe os arquivos alterados, os comandos executados e qualquer
critério que não tenha sido comprovado; não declare a etapa concluída com teste vermelho.
```

---

## Etapa 2 — callouts para P2 e posicionamento sem sobreposição

### Resultado esperado

Toda divergência com geometria rastreável, inclusive uma conformidade cujo alvo seja um ponto como
`P2`, recebe caixa e seta. Em uma página com vários erros, as caixas ficam próximas aos respectivos
alvos, dentro da folha, em áreas brancas sempre que houver espaço, e nunca ficam uma sobre a outra.

### Implementação

- Evoluir `projetar_callouts_conformidade` e o modelo `CalloutConformidade` existentes. Preservar a
  prioridade de geometrias decisivas, mas garantir fallback efetivo para evidência e geometria do
  alvo pontual. Uma região ampla não deve esconder a geometria mais específica do poste/ponto que
  causou o achado.
- Ordenar os achados da página de forma espacial e determinística antes de posicionar as caixas, em
  vez de depender apenas do UUID.
- Para cada caixa, testar um conjunto pequeno de posições próximas à âncora e depois uma grade de
  espaços livres. O custo deve priorizar, nesta ordem: nenhuma interseção com caixas já colocadas,
  permanência dentro da página, menor cobertura de conteúdo conhecido e menor distância ao alvo.
- Se o tamanho inicial não couber sem colisão, tentar poucas variações predefinidas de largura,
  altura e fonte. Definir um limite mínimo legível e testá-lo. Não aceitar sobreposição entre caixas
  como fallback; quando a página realmente não comportar todas, usar uma faixa lateral interna ou
  distribuição vertical determinística com caixas compactas, mantendo setas para os alvos.
- Medir o texto com as métricas reais da fonte usada pelo Qt ou manter no modelo informação de fonte
  suficiente para que projeção e renderização concordem. Não cortar nem esconder o texto.
- Continuar evitando regiões conhecidas de texto/evidência quando existir alternativa. A caixa pode
  cobrir conteúdo apenas no caso comprovadamente inevitável, nunca outra caixa.
- Preservar zoom, rotação, tiles, troca de página, seleção e controles de visibilidade já existentes.

Arquivos candidatos: `application/compliance_callouts.py`, `ui/pdf_viewer.py`, produtores de fatos ou
alvos em `application/project_compliance.py`/provedores especializados, além dos testes de callout.

### Testes e aceite

- Teste puro: achado divergente cujo único local rastreável é o alvo `P2` gera um callout na página
  correta, com seta terminando na geometria de `P2`.
- Testes puros com 2, 5 e 10 erros na mesma página comprovam que a área de interseção entre qualquer
  par de caixas é zero, todas ficam dentro da folha e duas execuções produzem o mesmo layout.
- Fixtures A4 e A3, em retrato e paisagem, cobrem alvo junto às quatro bordas, textos curtos e longos
  e áreas ocupadas próximas ao erro.
- Teste `pytest-qt` comprova que todo o texto cabe na caixa no menor tamanho de fonte permitido e
  continua legível após zoom, rotação, redimensionamento, tiles e troca de página.
- Selecionar a linha abre a página e realça a caixa; clicar na caixa ou seta seleciona a mesma linha.
- Achado sem página/geometria continua listado como **Sem localização no PDF** e não ganha uma caixa
  inventada.
- Fazer inspeção visual das imagens sintéticas renderizadas e registrar no resumo da sessão onde os
  PNGs temporários foram gerados.

### Mensagem para uma sessão limpa do Codex

```text
Implemente a Etapa 2 de docs/roadmap-melhorias-interface-conformidade.md sobre o estado que já contém
a Etapa 1. Leia o roadmap inteiro, application/compliance_callouts.py, ui/pdf_viewer.py,
application/project_compliance.py, os provedores de fatos e os testes unitários/de integração de
callouts. Confira git status e preserve mudanças não relacionadas.

Refine a projeção já existente para que toda divergência rastreável — inclusive alvo pontual P2 —
tenha caixa e seta. Posicione por página de forma espacial e determinística, perto do alvo e em área
livre. Adapte algumas geometrias e tamanhos de fonte predefinidos quando necessário. Caixas nunca
podem se sobrepor, devem ficar dentro da folha e não podem cortar texto. Preserve a camada vetorial,
o PDF original, zoom, rotação, tiles, visibilidade e seleção bidirecional. Não crie um otimizador ou
um novo sistema de anotações.

Implemente todos os testes e critérios de aceite, incluindo os cenários densos e P2. Gere e
inspecione os renders sintéticos, rode os testes focados e depois ./IniciarTestes.bat. Ao terminar,
informe os arquivos alterados, comandos executados, resultado da inspeção visual e qualquer critério
não comprovado; não declare a etapa concluída com teste vermelho.
```

---

## Etapa 3 — toggle de quebra de linha em todas as tabelas

### Resultado esperado

Cada tabela de dados oferece um controle **Quebrar linhas**. Desligado, mantém a visualização compacta
atual; ligado, mostra todo o conteúdo das células em múltiplas linhas e ajusta a altura das linhas,
como no recurso de quebra de texto do Excel.

### Implementação

- Inventariar os widgets tabulares antes de editar. O escopo mínimo atual inclui:
  - **Elementos** (`analysisRelationshipTree`) em `ReviewPanelWidget`;
  - **Vãos** em `ReviewPanelWidget`;
  - **Documentação**, **Conformidade** e **Regras** em `DocumentationPanelWidget`.
  O `reviewProposalTable` atualmente fica sempre oculto e não precisa de um controle enquanto não
  fizer parte da interface alcançável pelo usuário.
- Adicionar um `QToolButton` checkable **Quebrar linhas** junto de cada tabela ou de cada grupo de
  tabelas quando o controle afetar claramente somente a tabela visível. Incluir tooltip e nome
  acessível; o estado visual deve deixar claro se está ligado.
- Reutilizar uma função/controlador pequeno para `QTreeWidget` e `QTableWidget`. Ao ligar: habilitar
  word wrap, remover elisão, desativar altura uniforme e recalcular as linhas pelo conteúdo. Ao
  desligar: restaurar elisão, altura compacta e comportamento de rolagem atual.
- Recalcular alturas quando a largura de coluna mudar, quando dados forem recarregados e quando uma
  aba passar a ficar visível. Evitar recalcular continuamente durante cada pixel do arraste; um
  `QTimer.singleShot` curto já é suficiente.
- O toggle é preferência de visualização da sessão e não precisa de banco nem migração. Não persistir
  por projeto nesta etapa.

Arquivos candidatos: `ui/review_panel.py`, `ui/documentation_panel.py`, um helper pequeno em `ui/` e
testes `pytest-qt` dos dois painéis.

### Testes e aceite

- Cada uma das cinco tabelas listadas possui controle alcançável por teclado, checkable, com
  texto/tooltip/nome acessível.
- Com o controle ligado, uma célula longa não usa reticências, a altura da linha aumenta e todo o
  texto cabe após redimensionar a coluna para mais estreita.
- Ao desligar, a linha volta ao modo compacto e não conserva alturas excessivas.
- Recarregar projetos/resultados enquanto o toggle está ligado preserva o comportamento da tabela.
- Seleção, ordenação, botões de visibilidade, navegação ao PDF e desempenho com as fixtures atuais
  continuam funcionando.

### Mensagem para uma sessão limpa do Codex

```text
Implemente a Etapa 3 de docs/roadmap-melhorias-interface-conformidade.md sobre o estado com as etapas
anteriores concluídas. Leia o roadmap inteiro e inspecione ui/review_panel.py,
ui/documentation_panel.py, ui/theme.py e seus testes pytest-qt. Confira git status e preserve
mudanças não relacionadas.

Adicione um toggle Quebrar linhas às tabelas de Elementos, árvore de resultados, Vãos,
Documentação, Conformidade e Regras. Ligado, todo o texto deve aparecer em múltiplas linhas com altura
ajustada; desligado, restaure o modo compacto. Reutilize apenas um helper pequeno para QTreeWidget e
QTableWidget, recalcule após mudança de largura ou recarga e preserve seleção, navegação e botões
embutidos. Não persista essa opção nem crie um framework de tabelas.

Implemente os testes e critérios de aceite. Rode os testes focados e depois ./IniciarTestes.bat. Ao
terminar, informe arquivos alterados, comandos executados e qualquer critério não comprovado; não
declare a etapa concluída com teste vermelho.
```

---

## Etapa 4 — temas claro e escuro com preferência local

**Status: concluída em 16/08/2026.**

### Resultado esperado

O menu da aplicação permite alternar imediatamente entre **Claro** e **Escuro**. A escolha é salva em
`%LOCALAPPDATA%\ZenyProjectHandler\ui-state.ini` (ou no diretório definido por `ZENY_DATA_DIR`) e é
restaurada antes de a janela aparecer na próxima execução.

### Implementação

- Transformar `ui/theme.py` em duas paletas/folhas de estilo explícitas com a mesma identidade
  visual. Manter `Fusion` e uma única função pública para aplicar o tema escolhido.
- Adicionar ao menu **Exibir** uma ação checkable **Modo escuro** (ou submenu **Tema** com Claro e
  Escuro). Alterar o tema sem reiniciar a aplicação.
- Ler a preferência antes de criar/mostrar `MainWindow`, para evitar que a janela abra clara e mude
  depois. Salvar em `ui-state.ini`, por exemplo na chave `appearance/theme`, usando o caminho já
  fornecido por `AppSettings`; não usar banco, registro do Windows nem arquivo dentro do projeto.
- Se o valor salvo estiver ausente ou inválido, usar tema claro e sobrescrever apenas quando o
  usuário fizer uma escolha válida.
- Cobrir widgets comuns, menus, docks, abas, tabelas, inputs, botões, estados disabled/focus/hover,
  tooltips, barra de status e fundo do visualizador. O PDF renderizado e as caixas brancas/vermelhas
  de conformidade não devem ter suas cores alteradas pelo tema.

Arquivos candidatos: `ui/theme.py`, `ui/main_window.py`, `bootstrap.py`, `config.py` apenas se
necessário, `tests/integration/test_theme.py` e `tests/integration/test_window.py`.

### Testes e aceite

- Testes de paleta confirmam cores distintas e contraste legível para texto normal, seleção,
  disabled e botões nos dois temas.
- Teste de integração alterna para escuro, confirma a mudança sem reinício, fecha/recria a aplicação
  com o mesmo diretório de dados e encontra o modo escuro restaurado.
- Preferência inválida não impede a inicialização e resulta em tema claro.
- A troca de tema não perde projeto aberto, seleção, página, zoom, callouts nem estado dos toggles de
  quebra de linha.
- Inspeção visual de uma janela sintética nos dois temas confirma que não há texto escuro sobre fundo
  escuro ou texto claro sobre fundo claro.

### Mensagem para uma sessão limpa do Codex

```text
Implemente a Etapa 4 de docs/roadmap-melhorias-interface-conformidade.md sobre o estado com as etapas
anteriores concluídas. Leia o roadmap inteiro e inspecione ui/theme.py, ui/main_window.py,
bootstrap.py, config.py e os testes de tema/janela. Confira git status e preserve mudanças não
relacionadas.

Ofereça tema Claro e Escuro pela interface e aplique a escolha imediatamente. Persista somente a
preferência local em ui-state.ini dentro do data_directory já existente e carregue-a antes de a
janela aparecer. Valor ausente ou inválido usa Claro. Cubra estados dos widgets e mantenha o PDF e os
callouts com suas cores próprias. Não use banco, registro do Windows, migração ou dependência nova.

Implemente os testes e critérios de aceite, faça inspeção visual nos dois temas, rode os testes
focados e depois ./IniciarTestes.bat. Ao terminar, informe arquivos alterados, comandos executados,
resultado da inspeção e qualquer critério não comprovado; não declare a etapa concluída com teste
vermelho.
```

---

## Etapa 5 — ícone minimalista e assets empacotados

**Status: concluída em 16/08/2026.**

### Resultado esperado

A janela e a aplicação usam um logo próprio e legível em tamanhos pequenos. O mesmo desenho fica
versionado em PNG original e ICO multirresolução dentro do pacote Python.

### Implementação

- Usar a skill `imagegen` do Codex para gerar um ícone quadrado minimalista e original, sem texto
  pequeno, sem fundo fotográfico e sem copiar marcas existentes. Direção visual sugerida: um `Z`
  geométrico simples associado discretamente a projeto/rede elétrica, com silhueta forte e poucas
  cores que funcionem nos temas claro e escuro.
- Escolher uma única versão após verificar a leitura em 16, 24, 32, 48 e 256 px. Não manter variantes
  descartadas no repositório.
- Criar `src/zeny_project_handler/assets/` com o PNG original, preferencialmente 1024×1024 e com
  transparência, e `zeny_project_handler.ico` gerado desse mesmo PNG com frames de 16, 24, 32, 48,
  64, 128 e 256 px. A conversão pode usar o Pillow já instalado; não adicionar dependência.
- Incluir os dois arquivos em `tool.setuptools.package-data` e carregá-los com
  `importlib.resources`, sem depender do diretório de trabalho.
- Definir o ícone no `QApplication` antes da janela e no `MainWindow`, cobrindo barra de título,
  alternador de tarefas e diálogos filhos. Falha inesperada ao ler o asset deve produzir diagnóstico
  claro em teste/desenvolvimento, não um caminho absoluto silenciosamente inválido.
- Documentar os assets no README com origem “gerado com OpenAI ImageGen para o projeto” e a data,
  sem atribuir licença de terceiros inexistente.

Arquivos candidatos: novo pacote `src/zeny_project_handler/assets/`, `pyproject.toml`, `bootstrap.py`,
`ui/main_window.py`, README e testes de empacotamento/janela.

### Testes e aceite

- O PNG é quadrado, possui dimensão de fonte adequada e abre sem erro; o ICO contém os tamanhos
  mínimos 16, 32, 48 e 256 px.
- `importlib.resources` encontra os dois assets tanto no checkout quanto após criar/instalar um wheel
  em ambiente temporário.
- `QApplication.windowIcon()` e `MainWindow.windowIcon()` não são nulos e usam o recurso empacotado.
- Inspeção visual no Windows confirma o ícone na barra de título e no alternador de tarefas, em tema
  claro e escuro, com leitura aceitável em tamanho pequeno.
- O gate completo passa sem depender de rede; geração com ImageGen acontece uma única vez durante a
  implementação, não durante testes ou inicialização.

### Mensagem para uma sessão limpa do Codex

```text
Implemente a Etapa 5 de docs/roadmap-melhorias-interface-conformidade.md sobre o estado com as etapas
anteriores concluídas. Leia o roadmap inteiro, pyproject.toml, bootstrap.py, ui/main_window.py e os
testes de portabilidade/empacotamento. Confira git status e preserve mudanças não relacionadas.

Use a skill imagegen para criar um único ícone original, minimalista e quadrado para o Zeny Project
Handler: um Z geométrico com referência discreta a projeto/rede elétrica, poucas cores, sem texto
pequeno e legível sobre temas claro e escuro. Salve apenas a versão escolhida como PNG original em
src/zeny_project_handler/assets e gere do mesmo arquivo um ICO multirresolução com Pillow. Empacote os
assets, carregue-os via importlib.resources e configure o ícone no QApplication e MainWindow. Não
adicione dependência nem gere imagens em runtime/testes.

Implemente os testes e critérios de aceite, incluindo wheel temporário. Faça a inspeção visual no
Windows, rode os testes focados e depois ./IniciarTestes.bat. Atualize o README com a origem do asset.
Ao terminar, informe arquivos alterados, comandos executados, tamanhos presentes no ICO, resultado
da inspeção e qualquer critério não comprovado; não declare a etapa concluída com teste vermelho.
```

---

## Ordem e aceite final

Executar as etapas na ordem indicada. A Etapa 1 fornece os textos que a Etapa 2 precisa medir; a
Etapa 3 altera geometria de widgets e deve existir antes da validação visual dos temas; o ícone é
isolado e fica por último.

Ao concluir a Etapa 5, fazer uma verificação manual curta com um projeto sintético que tenha ao menos
dois erros na mesma página e um alvo `P2`:

1. confirmar nomes amigáveis na tabela, nos detalhes e nas caixas;
2. confirmar caixas separadas, próximas aos alvos, com setas corretas e texto completo;
3. ligar/desligar **Quebrar linhas** em cada tabela;
4. alternar claro/escuro, reiniciar e confirmar a preferência;
5. confirmar o ícone na janela e no alternador de tarefas;
6. executar `./IniciarTestes.bat` uma última vez.

O conjunto é aceito quando os seis itens passam e nenhuma chave de fato interna aparece no fluxo
normal da interface.
