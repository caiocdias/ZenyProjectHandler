# Roadmap de desenvolvimento do Zeny Project Handler

> Documento operacional para orientar o Codex. Ele define a ordem de implementação e os testes mínimos de cada etapa. Não é um cronograma nem uma especificação comercial.

## Diretriz sobre análise automática

O projeto não inclui um motor de aprendizado de máquina predefinido, código de inferência, pesos ou requisitos de GPU. A interpretação automática será construída por uma porta genérica e testável, começando por informações nativas do PDF, processamento de imagem e regras de domínio.

Nenhum serviço externo ou modelo específico deve ser introduzido sem uma decisão futura explícita, registrada em ADR e acompanhada de avaliação de licença, privacidade, hardware, qualidade e manutenção.

## Regras de execução para o Codex

1. Trabalhar em apenas uma etapa por vez, respeitando as dependências indicadas.
2. Antes de iniciar uma etapa, conferir seus critérios de entrada e registrar decisões novas neste documento ou em um ADR.
3. Não marcar uma etapa como `CONCLUÍDA` enquanto seus critérios de saída, testes e aceites humanos
   indicados na tabela não estiverem satisfeitos. O desenvolvimento técnico de uma etapa posterior só
   pode começar antes disso por instrução explícita do usuário e quando as dependências técnicas
   necessárias já estiverem disponíveis; o aceite pendente deve continuar registrado.
4. Manter domínio, interface, persistência, processamento de PDF e análise desacoplados por portas e adaptadores.
5. A suíte padrão deve executar sem rede, serviços externos ou arquivos confidenciais.
6. Toda ocorrência automática mantém uma proposta auditável; quando o catálogo e as dependências
   estiverem resolvidos, ela é promovida deterministicamente ao conjunto confirmado sem confirmação
   item a item.
7. Fixar versões das dependências. Enquanto o produto permanecer em desenvolvimento, bancos e
   pacotes antigos podem ser descartados; compatibilidade entre versões passa a ser exigida somente
   após a definição explícita da primeira versão distribuível.
8. Ao concluir o desenvolvimento técnico de uma etapa, atualizar a tabela de estado e registrar
   arquivos alterados, comandos de teste, limitações, fluxo disponível na interface, roteiro de
   aceite humano e próximo passo.
9. Uma capacidade necessária ao aceite não pode existir somente como caso de uso, adaptador, script,
   teste ou dado inserido diretamente no SQLite. Ela deve ser alcançável pela interface do aplicativo
   iniciado pelos launchers normais do usuário.
10. Cada incremento deve preservar um caminho utilizável de MVP. Se uma etapa depender de uma
    capacidade interna ainda não exposta, o escopo da etapa deve incluir a integração mínima de
    interface necessária ou registrar uma etapa intermediária antes do aceite.

## Processo de desenvolvimento e aceite do MVP

O roadmap distingue implementação técnica de conclusão da etapa:

- `PENDENTE`: o desenvolvimento técnico ainda não começou.
- `EM ANDAMENTO`: há implementação em curso ou tecnicamente pronta aguardando integração/aceite.
- `BLOQUEADA`: existe impedimento objetivo registrado, sem alternativa segura dentro do escopo.
- `CONCLUÍDA`: gates automatizados aprovados e todos os aceites humanos indicados foram realizados.

Para etapas que produzam comportamento usado por uma pessoa, o Codex deve entregar um **incremento
vertical**: domínio, persistência, aplicação e interface conectados. O usuário não deve precisar de
terminal, pytest, edição de JSON, acesso direto ao banco ou fixtures para executar o roteiro de aceite.

Cada registro de desenvolvimento deve conter:

1. **Fluxo MVP disponível:** de onde o usuário parte e qual resultado consegue obter pela interface.
2. **Como aceitar:** passos curtos, dados necessários e resultado visível esperado.
3. **Persistência e recuperação:** o que deve sobreviver ao fechamento e à reabertura.
4. **Gates automatizados:** testes, cobertura, qualidade e falhas ambientais não relacionadas.
5. **Limitações:** tudo que ainda exige etapa futura, decisão humana ou dado autorizado.

Interpretação das próximas instruções do usuário:

- **“Desenvolva a etapa X”**: implementar o incremento vertical completo, integrar à interface,
  testar e documentar; manter `EM ANDAMENTO` se ainda faltar aceite humano.
- **“Prepare o aceite da etapa X”**: deixar dados e navegação acessíveis pela interface e fornecer o
  roteiro de validação, sem exigir ferramentas de desenvolvimento.
- **“Aceito/Aprovei a etapa X”**: registrar o aceite informado, conferir pendências remanescentes e
  marcar `CONCLUÍDA` somente se nenhuma permanecer.
- **“Corrija o aceite da etapa X”**: tratar os problemas observados, repetir gates proporcionais e
  emitir um novo roteiro de aceite.
- **“Desenvolva a próxima etapa”**: escolher a primeira etapa com trabalho técnico acionável e
  dependências técnicas satisfeitas; pendências exclusivamente humanas continuam registradas e não
  são presumidas como aprovadas.

## Estado das etapas

| Etapa | Estado inicial | Depende de | O que falta para considerar concluída |
|---|---|---|---|
| 0. Fundação do projeto Python | CONCLUÍDA | - | Nada; critérios de saída e testes já foram atendidos pelo Codex. |
| 1. Revisão do domínio e catálogo | CONCLUÍDA | 0 | Nada; critérios de saída e testes já foram atendidos pelo Codex. |
| 1.1 Calibração com projetos reais | CONCLUÍDA | 1 | Nada; critérios de saída e testes já foram atendidos pelo Codex. |
| 2. Persistência local | CONCLUÍDA | 1.1 | Nada; critérios de saída e testes já foram atendidos pelo Codex. |
| 3. Ingestão e visualização de PDF | CONCLUÍDA | 1.1, 2 | Nada; critérios de saída e testes já foram atendidos pelo Codex. |
| 4. Extração de evidências do PDF | CONCLUÍDA | 3 | Nada; critérios de saída e testes já foram atendidos pelo Codex. |
| 5. Conjunto de avaliação | EM ANDAMENTO | 3, 4 | **Humano:** fornecer ao menos uma amostra autorizada em escala diferente, concluir anotações primárias/secundárias e consensos e aprovar os critérios numéricos. **Codex:** validar a auditoria e congelar manifesto e anotações. |
| 6. Pipeline modular de interpretação | EM ANDAMENTO | 1, 4, 5 | **Humano:** concluir e aprovar a Etapa 5. **Codex:** executar o benchmark no conjunto congelado, ajustar apenas com a partição de desenvolvimento e comprovar os limites aprovados. |
| 7. Resultados da análise na interface | EM ANDAMENTO | 3, 6 | **Codex:** promoção automática, regiões de ocorrência, links no PDF e testes concluídos. **Humano:** validar uma página real inteira e a clareza dos agrupamentos. |
| 7.1 Fluxo operacional do MVP pela interface | EM ANDAMENTO | 2, 3, 4, 6, 7 | **Codex:** implementação técnica e gates concluídos. **Humano:** executar e aprovar o roteiro ponta a ponta em um projeto autorizado. PDFs exploratórios adicionais em `examples/` são aceitos e testados automaticamente. |
| 8. Agrupamento por regiões do PDF | EM ANDAMENTO | 4, 6, 7 | **Codex:** agrupamento espacial, coordenadas, vínculos internos, navegação e remoção do grafo concluídos. **Humano:** validar as regiões em páginas reais. |
| 9. Gestão do catálogo pela interface | PENDENTE | 2, 7.1 | **Codex:** implementar CRUD, versionamento, importação/exportação e testes. **Humano:** validar que alterações podem ser feitas sem recompilar e sem mudar projetos antigos. |
| 10. Transporte e recuperação | EM ANDAMENTO | 2, 7.1, 8 | **Codex:** implementação técnica, transporte, recuperação, integração Qt e gates concluídos. **Humano:** executar o roteiro de aceite em outra pasta ou máquina autorizada. |
| 11. Empacotamento e aceite | PENDENTE | 8, 9, 10 | **Codex:** gerar instalador, diagnóstico, documentação e executar testes E2E, privacidade e benchmark final. **Humano:** realizar o aceite do fluxo completo em uma máquina-alvo limpa e decidir a licença de distribuição do PyMuPDF/MuPDF. |
| 12. Comissionamento e conformidade | EM ANDAMENTO | 4, 6, 7, 8 | **Codex:** abstração de fatos/regras, scanner documental e painel inicial implementados. O detector de vãos/ângulos foi removido e aguarda uma nova abstração. Falta persistir fatos/achados, ampliar avaliadores técnicos e comparar projeto com campo. **Humano:** aprovar fontes, severidades e critérios antes de promover possíveis divergências. |

Estados permitidos: `PENDENTE`, `EM ANDAMENTO`, `BLOQUEADA` e `CONCLUÍDA`.

## Stack de referência

- Linguagem: Python 3.11.
- Aplicativo desktop: PySide6 com Qt Widgets e `QGraphicsView` para PDF, sobreposições e edição gráfica.
- Domínio: classes Python sem dependência de Qt, ORM ou bibliotecas de análise; `dataclasses` e Pydantic somente nas fronteiras de entrada e saída.
- Persistência: SQLite como armazenamento canônico, SQLAlchemy 2.x como adaptador ORM e Alembic para migrações. JSON será formato de importação e exportação, não o banco principal.
- PDF: PyMuPDF para metadados, texto incorporado, vetores, imagens, renderização e recortes.
- Imagem: Pillow como base; OpenCV poderá ser adotado no adaptador de análise raster se os testes demonstrarem necessidade.
- OCR: porta independente e implementação escolhida somente após benchmark com projetos reais.
- Regiões: projeção espacial determinística dos resultados por página; as análises persistidas continuam sendo a fonte de verdade.
- Testes e qualidade: pytest, pytest-cov, pytest-qt, Ruff e verificação estática de tipos.
- Distribuição: avaliar `pyside6-deploy` primeiro e manter os dados do usuário fora da pasta do executável.

Estrutura esperada, sujeita a pequenos ajustes durante a etapa 0:

```text
src/zeny_project_handler/
  domain/
  application/
  ports/
  adapters/
    persistence/
    pdf/
    analysis/
  ui/
tests/
  unit/
  integration/
  e2e/
  fixtures/
```

## Revisões necessárias no modelo atual

Estas revisões devem ser realizadas na etapa 1 e refletidas em `modelo-entidades.mmd` e `especificacao-funcional.md`:

1. Trocar `Projeto.arquivoPdfOrigem` por `DocumentoProjeto` e `PaginaDocumento`, preservando hash, dimensões, rotação e caixas `MediaBox` e `CropBox`.
2. Substituir a posição pontual de `ElementoProjeto` por `GeometriaDocumento`, capaz de representar ponto, caixa e polilinha em coordenadas normalizadas.
3. Trocar `Cabo.geometria: String` por uma polilinha estruturada. Um cabo continuará ligando dois `PontoRede`, mas poderá possuir apoios intermediários.
4. Acrescentar `ExecucaoAnalise`, `EvidenciaDocumento`, `PropostaElemento`, `PropostaRelacao` e `DecisaoRevisao`.
5. Registrar a proveniência de cada evidência: documento, página, recorte, transformação de coordenadas, tipo de origem, método, versão, parâmetros e data.
6. Separar claramente objetos `PROPOSTOS`, produzidos pela análise, de elementos `CONFIRMADOS` do projeto.
7. Substituir strings livres de tensão, fases e tecnologia por referências ao catálogo sempre que o valor for controlado.
8. Tornar explícitas as ligações internas dos equipamentos. Um transformador conecta terminais MT e BT; chaves ligam ou seccionam terminais conforme seu estado.
9. Agrupar resultados por região da folha, sem depender de um poste como item-pai e sem produzir nós ou arestas.
10. Adotar SQLite desde a primeira persistência. JSON deve permanecer para seed, intercâmbio e diagnóstico.
11. Permitir pontos de derivação, conexão, entrega, caixa de passagem e transição sem obrigá-los a
    pertencer a um poste.
12. Preservar percurso ordenado de cabos, coordenadas georreferenciadas e metadados técnicos do
    desenho.
13. Representar realocação e substituição como vínculo entre retirada e instalação.
14. Distinguir conteúdo de página, anotação, appearance stream e Form XObject na proveniência PDF.
15. Preservar código não mapeado, atributos sugeridos, confiança e justificativa nas propostas.
16. Separar simbologia canônica da aplicação das múltiplas assinaturas usadas no reconhecimento.
17. Manter PDFs reais fora do Git e versionar somente manifesto anônimo com hashes.

## Etapa 0 - Fundação do projeto Python

### Desenvolver

- Criar `pyproject.toml`, pacote em `src/`, lockfile e grupos separados para aplicação e desenvolvimento.
- Implantar a arquitetura por portas e adaptadores e impedir dependências de infraestrutura dentro de `domain/`.
- Criar uma janela PySide6 mínima, configuração local e logging estruturado sem dados sensíveis.
- Configurar Ruff, tipos, pytest, cobertura e marcadores `integration`, `slow` e `e2e`.
- Criar ADR inicial documentando a decisão de começar sem um analisador proprietário obrigatório.
- Criar `setup.bat` para preparar `.venv`, instalar o lockfile e deixar o pacote pronto para execução.
- Criar `ZenyProjectHandler.bat` para ativar a `.venv` e abrir o aplicativo.
- Criar `ZenyProjectHandler.vbs` para uso cotidiano com `pythonw.exe`, sem manter uma janela de
  console junto à interface.
- Criar `IniciarTestes.bat` para executar todas as verificações e salvar `relatorio-testes.txt` na raiz.
- Exigir cobertura estritamente superior a 85% e registrar complexidade ciclomática, índice de manutenibilidade e métricas brutas do código.

### Testar

- Importação limpa do pacote no Windows.
- Teste arquitetural garantindo que o domínio não importe PySide6, SQLAlchemy, PyMuPDF, NetworkX ou bibliotecas de visão computacional.
- Smoke test da janela desktop.
- Suíte padrão executada sem rede.
- `setup.bat` funciona tanto na primeira instalação quanto quando a `.venv` já existe.
- `ZenyProjectHandler.bat` inicia a aplicação usando o Python da `.venv`.
- `ZenyProjectHandler.vbs` inicia a janela Qt sem criar console e informa graficamente a ausência da
  `.venv`.
- `IniciarTestes.bat` retorna erro quando qualquer gate falha e sempre deixa um relatório analisável na raiz.

### Critério de saída

Aplicativo vazio abre, ferramentas de qualidade passam e a separação entre módulos está protegida por testes.

### Registro de conclusão

- Data: 2026-07-21.
- Resultado: janela PySide6, pacote instalável, configuração local, logging JSON, arquitetura por
  camadas e os inicializadores `ZenyProjectHandler.vbs` (uso sem console) e
  `ZenyProjectHandler.bat` (diagnóstico), além de `setup.bat` e `IniciarTestes.bat`.
- Validações executadas: preparação completa por `setup.bat`, abertura pelo launcher em modo smoke e suíte completa por `IniciarTestes.bat`.
- Testes: 12 aprovados; cobertura total de 89,63%; smoke test da janela executado com Qt em modo offscreen.
- Qualidade: complexidade ciclomática média A (2,62), todos os blocos na classe A e relatório consolidado aprovado em `relatorio-testes.txt`.
- Ambiente validado: Windows, Python 3.12.13, PySide6/Qt 6.11.1.
- Limitação conhecida: a compatibilidade declarada com Python 3.11 ainda deve ser exercitada antes da primeira distribuição.
- Próximo passo registrado à época: etapa 1, concluída em 2026-07-21.

## Etapa 1 - Revisão do domínio e catálogo

### Desenvolver

- Aplicar as revisões listadas acima ao diagrama e à especificação.
- Implementar entidades, value objects, identificadores e invariantes.
- Criar seed versionado do catálogo a partir de `NOMENCLATURAS.xlsx`.
- Normalizar cabeçalhos, transformar `-` em nulo, sinalizar a duplicidade `CEM4` e converter compatibilidades textuais em relações explícitas.
- Manter situação do projeto (`EXISTENTE`, `INSTALAR`, `REMOVER`) separada da situação de revisão de uma proposta.

### Testar

- Testes unitários de todas as invariantes do documento funcional.
- Teste de importação com contagens esperadas: 38 postes, 50 linhas MT de origem, 13 estruturas BT, 72 cabos e 25 equipamentos.
- Teste de duplicidade de `CEM4`, valores nulos e preservação dos códigos originais.
- Testes de serialização compatível entre versões do catálogo.

### Critério de saída

Domínio e catálogo carregam sem infraestrutura, rejeitam estados inválidos e os documentos refletem o código.

### Registro de conclusão

- Data: 2026-07-21.
- Resultado: entidades de documento, projeto, análise e catálogo implementadas como dataclasses de domínio sem dependências de infraestrutura.
- Catálogo: seed JSON schema v1 com 198 itens preservados, 197 ativos, cinco grupos de opções, 314 compatibilidades explícitas e 15 regras de simbologia.
- Origem: `NOMENCLATURAS.xlsx`, aba `Planilha1`, inspecionada sem alteração; contagens 38/50/13/72/25 confirmadas e SHA-256 registrado.
- Normalização: `CEM4` das linhas 40 e 46 preservado com apenas a primeira ocorrência ativa; fatores `-` convertidos para nulo; códigos originais mantidos.
- Documentação: `modelo-entidades.mmd` e `especificacao-funcional.md` alinhados ao código.
- Validações: `IniciarTestes.bat` aprovado com Ruff, mypy, pytest, cobertura e Radon.
- Testes: 46 aprovados e cobertura total de 87,50%.
- Qualidade: complexidade média A (3,99), maior bloco na classe C (14) e nenhum bloco D, E ou F após a modularização das relações do projeto.
- Limites: persistência SQLite, importação interativa de planilha e telas de edição permanecem para etapas posteriores.
- Próximo passo registrado à época: calibração com projetos reais, concluída na etapa 1.1.

## Etapa 1.1 - Calibração com projetos reais

### Desenvolver

- Inspecionar visualmente e estruturalmente o corpus local sem modificar os PDFs.
- Generalizar os pontos da rede e o percurso dos cabos para derivações, conexões, entregas, caixas e
  transições fora de postes.
- Acrescentar coordenadas de campo, metadados técnicos e dados sensíveis separados.
- Modelar realocação e substituição como retirada ligada a instalação.
- Preservar anotações PDF, appearance streams, Form XObjects e artefatos extraídos na proveniência.
- Acrescentar código observado, atributos, confiança e justificativa às propostas.
- Migrar o catálogo para schema v2, mantendo leitura do schema v1, e separar apresentação canônica
  de assinaturas visuais múltiplas.
- Ignorar PDFs reais no Git e criar manifesto anônimo versionável.

### Testar

- Pontos sem poste e percursos ordenados de cabos.
- Vínculos válidos e inválidos de realocação/substituição.
- Metadados, Nota de Serviço, escala, coordenadas e geometria poligonal.
- Proveniência de anotação/appearance stream e integridade de artefato extraído.
- Proposta não mapeada e limites de confiança.
- Round-trip do catálogo schema v2, leitura retrocompatível do schema v1 e assinaturas visuais.
- Manifesto sem nomes de arquivos e com hashes correspondentes ao corpus local.

### Critério de saída

O domínio representa sem perda os casos estruturais observados no corpus real antes da definição do
schema SQLite.

### Registro de conclusão

- Data: 2026-07-21.
- Corpus: nove PDFs locais, 25.519.491 bytes, todos com hash único; A3/A4, retrato/paisagem e
  produtores iText, AutoCAD e Microsoft Print to PDF.
- Casos incorporados: pontos fora de postes, ramal subterrâneo, realocação, georreferenciamento,
  anotações PDF, imagens em appearance streams, Optional Content Groups e anotação malformada.
- Catálogo: schema v2 com 15 regras canônicas e cinco assinaturas visuais iniciais; schema v1 continua
  legível. Valores reais ausentes da planilha permanecem como propostas não mapeadas.
- Privacidade: `examples/**/*.pdf` ignorado e manifesto anônimo criado.
- Fundamentação: ND 3.1/2025 e ND 2.7 públicas da CEMIG.
- Validações: `IniciarTestes.bat` aprovado com integridade de dependências, Ruff, mypy, pytest,
  cobertura e Radon.
- Testes: 56 aprovados e cobertura total de 87,27%, acima do limite estrito de 85%.
- Qualidade: complexidade média A (4,10), maior bloco na classe C (14) e nenhum bloco D, E ou F.
- Próximo passo: etapa 2, persistindo o domínio revisado sem acoplamento ao ORM.

## Etapa 2 - Persistência local

### Desenvolver

- Mapear o domínio em SQLite sem acoplar as entidades ao ORM.
- Criar migração inicial e repositórios para projetos, catálogos, documentos, elementos, evidências, propostas e decisões de revisão.
- Implementar transações, desativação lógica de itens referenciados e versionamento imutável de catálogo publicado.
- Definir a pasta de dados da aplicação e política de backup atômico.

### Testar

- CRUD e rollback de cada agregado.
- Migração de banco vazio e atualização a partir da versão anterior.
- Reabertura do banco após interrupção simulada.
- Integridade de referências e leitura de projeto ligado a uma versão antiga do catálogo.

### Critério de saída

Um projeto completo sobrevive a salvar, fechar e reabrir sem perda nem alteração silenciosa.

### Registro de conclusão

- Data: 2026-07-21.
- Armazenamento: SQLite com SQLAlchemy Core, duas revisões Alembic e inicialização automática antes
  da abertura da interface.
- Modelo: agregados completos em JSON canônico e projeções relacionais de catálogos, itens,
  documentos, páginas, elementos, execuções, evidências, propostas e decisões.
- Integridade: chaves estrangeiras por projeto, catálogo e página; catálogos publicados protegidos
  por repositório e triggers; desativação lógica preservada em novas versões de catálogo.
- Transações: unidade de trabalho com `commit` explícito e rollback automático na saída do contexto.
- Recuperação: backup por snapshot SQLite, `integrity_check` e substituição atômica no destino.
- Decisão arquitetural: ADR 0002 registra o mapeamento híbrido e o limite dos agregados de escrita.
- Validações: `IniciarTestes.bat` aprovado com dependências íntegras, Ruff, mypy, pytest, cobertura
  e Radon.
- Testes: 72 aprovados e cobertura total de 89,11%, acima do limite estrito de 85%.
- Qualidade: complexidade média A (3,50), maior bloco na classe C (14), persistência no máximo B
  (10) e nenhum bloco D, E ou F.
- Próximo passo: etapa 3, ingestão e visualização de PDF sobre o armazenamento já versionado.

## Etapa 3 - Ingestão e visualização de PDF

**Status: CONCLUÍDA em 2026-07-21.**

### Desenvolver

- Importar o PDF de modo somente leitura, calcular SHA-256 e registrar metadados.
- Extrair texto, vetores, imagens incorporadas, anotações, appearance streams, Form XObjects e
  Optional Content Groups sem alterar o arquivo original.
- Renderizar miniaturas, páginas e recortes RGB em resolução configurável.
- Implementar coordenadas normalizadas e transformações reversíveis entre PDF, pixels e cena gráfica.
- Exibir página, zoom, rotação e sobreposições no `QGraphicsView`.
- Importar todo PDF selecionado diretamente no projeto e permitir reordenar cada página por arraste
  ou por controles explícitos. A sequência persistida pode intercalar páginas de PDFs diferentes sem
  modificar ou concatenar os arquivos originais.

### Testar

- PDFs vetoriais, escaneados, rotacionados, multipágina e com `CropBox` diferente de `MediaBox`.
- Smoke test parametrizado pelos hashes do manifesto das nove amostras formais e, quando presentes,
  pelos hashes anônimos de PDFs exploratórios adicionais colocados em `examples/`.
- Anotação malformada, fonte ausente e objeto não suportado geram diagnóstico localizado sem impedir
  a renderização válida do restante da página.
- Golden tests de renderização com tolerância documentada.
- Round-trip de coordenadas em diferentes DPI e rotações.
- Arquivo inválido, protegido ou corrompido não altera o projeto existente.
- Seleção múltipla preserva a ordem inicial das folhas; a reordenação de páginas, inclusive entre
  arquivos, sobrevive à reabertura. Arquivo inválido ou conteúdo duplicado impede a importação
  inteira, sem substituir o projeto já aberto.

### Critério de saída

Qualquer geometria registrada no documento aparece na posição correta da página exibida.

### Registro de conclusão

- Leitura: `LeitorPdfPort` e adaptador PyMuPDF 1.28.0 somente leitura, com SHA-256 em fluxo,
  metadados, verificação de origem e erros controlados para arquivo ausente, inválido, corrompido,
  protegido ou alterado.
- Inventário: fragmentos de texto, caminhos vetoriais, imagens incorporadas, anotações, referências
  de appearance streams, Form XObjects e Optional Content Groups, com diagnósticos localizados por
  página e `xref`.
- Renderização: páginas, miniaturas e recortes RGB; DPI configurável por `ZENY_PDF_RENDER_DPI`;
  golden test com dimensões exatas e tolerância de 8 níveis por canal RGB.
- Coordenadas: matrizes PDF/página preservadas no domínio e round-trip PDF, normalizado, pixel e cena
  validado em 72, 144 e 300 DPI e rotações 0, 90, 180 e 270 graus.
- Interface: `QGraphicsView` com paginação, zoom, ajuste, rotação, arraste e sobreposições alinhadas;
  seleção múltipla importa os PDFs diretamente, e a lista reordenável os apresenta como uma sequência
  única de folhas, preservando cada documento de origem.
- Persistência: revisão Alembic `0003_pdf_sources`, repositório da origem e caso de uso que grava
  projeto/documento/referência em uma única transação após validação completa.
- Corpus: smoke test parametrizado pelos hashes das nove amostras reais, sem versionar nomes ou
  conteúdo sensível; todos os originais permaneceram com tamanho e data inalterados.
- Verificação visual: raster vetorial real revisado com Poppler e mesma página exibida pelo
  visualizador, sem deslocamento, corte ou sobreposição indevida do conteúdo.
- Validações: `IniciarTestes.bat` aprovado com 110 testes e cobertura total de 90,39%, acima do
  limite estrito de 85%; integridade de dependências, Ruff, mypy e Radon aprovados.
- Qualidade: complexidade média A (3,13), maior bloco geral C (14), novo adaptador PDF no máximo B
  (9) e nenhum bloco D, E ou F.
- Decisão arquitetural: ADR 0003 documenta somente leitura, referências locais, coordenadas e
  fronteira entre inventário da etapa 3 e evidência semântica da etapa 4.
- Pendência de distribuição: decidir conformidade AGPL ou licença comercial do PyMuPDF/MuPDF antes
  do empacotamento; `LeitorPdfPort` permite trocar o adaptador sem alterar o domínio.
- Próximo passo: etapa 4, normalizando o inventário rastreável como evidências independentes da UI.

## Etapa 4 - Extração de evidências do PDF

### Desenvolver

- Criar `AnalisadorDocumentoPort` para que a aplicação não dependa de uma implementação específica.
- Implementar o primeiro adaptador usando texto, desenhos vetoriais, imagens incorporadas,
  anotações e propriedades de página fornecidas pelo PyMuPDF.
- Percorrer appearance streams e Form XObjects; não assumir que imagens visíveis aparecem na lista
  de imagens de primeiro nível da página.
- Normalizar cada resultado como `EvidenciaDocumento`, preservando geometria e proveniência.
- Classificar evidências por origem: `TEXTO`, `VETOR`, `IMAGEM` ou `OCR`.
- Avaliar OCR e operações raster somente onde não houver informação nativa suficiente.
- Manter cache derivado descartável e reproduzível a partir do PDF original.

### Testar

- Extração de texto com posição, tamanho e rotação.
- Extração de linhas, curvas, polígonos, cores e imagens incorporadas.
- Extração de `Stamp`, `Popup`, `FreeText`, `Square`, appearance streams e recursos aninhados.
- Mesma entrada e configuração geram evidências semanticamente equivalentes.
- Falha em um extrator é registrada sem perder os resultados válidos dos demais.
- Contract tests para o adaptador real e um adaptador falso.

### Critério de saída

O sistema produz evidências normalizadas e rastreáveis sem depender da interface ou de um serviço externo.

### Registro de conclusão

- Contratos: `AnalisadorDocumentoPort`, `MotorOcrPort` e `CacheAnaliseDocumentoPort` isolam aplicação,
  OCR e armazenamento derivado da implementação PyMuPDF.
- Extração: spans de texto preservam posição, fonte, tamanho, cor, opacidade e rotação; caminhos
  preservam linhas, curvas, polígonos, cores, preenchimento, espessura, camada e comandos originais;
  imagens preservam ocorrência visual, hash, transformação, dimensões e recurso PDF.
- Estrutura PDF: anotações `Stamp`, `Popup`, `FreeText` e `Square`, raízes de appearance streams,
  recursos indiretos, imagens em aparências e Form XObjects aninhados são percorridos com proteção
  contra ciclos e profundidade configurável.
- Normalização: cada candidato é materializado como `EvidenciaDocumento` em coordenadas 0..1 da
  página visual, classificado como `TEXTO`, `VETOR`, `IMAGEM` ou `OCR`, com `xref`, subtipo, índice,
  raiz e nome de recurso quando disponíveis.
- Tolerância a falhas: `DiagnosticoAnalise` registra extrator, página e objeto; a execução concluída
  preserva falhas parciais e resultados válidos, enquanto falhas fatais são persistidas como
  `FALHOU`.
- OCR: nenhuma dependência externa foi adicionada. Um motor é injetável e só recebe raster de página
  abaixo do limite configurado de texto nativo; o comportamento foi provado com adaptador falso.
- Cache: candidatos normalizados são gravados em JSON atômico, fora do SQLite, sob chave derivada do
  hash do PDF, configuração e versão do analisador. Cache ausente ou inválido é recriado.
- Aplicação: `ExecutarAnaliseDocumento` valida projeto, documento e origem, executa a análise e grava
  execução e evidências em uma transação; IDs de evidência são determinísticos dentro da execução.
- Testes: PDFs sintéticos cobrem texto rotacionado, linha, Bézier, polígono, cores, imagens, Forms,
  anotações e aparência com imagem; há regressão de reprodutibilidade, falha localizada, OCR
  condicional, cache e contratos real/falso.
- Corpus real: as nove amostras privadas foram analisadas por hash, inclusive imagem visível em
  appearance stream e anotação com codificação imperfeita, sem alterar tamanho ou data dos PDFs.
- Validações: `IniciarTestes.bat` aprovado com 131 testes e cobertura total de 91,05%, acima do
  limite estrito de 85%; dependências, Ruff, formatação e mypy aprovados.
- Qualidade: complexidade média geral A (3,09), módulos novos com índice de manutenibilidade A,
  maior bloco da extração C (12) e nenhum bloco D, E ou F.
- Decisão arquitetural: ADR 0004 registra as fronteiras, proveniência, geometria aproximada em
  recursos internos de aparências, OCR opcional e cache descartável.
- Próximo passo: etapa 5, congelando um conjunto de avaliação e métricas antes de criar regras de
  interpretação semântica.

## Etapa 5 - Conjunto de avaliação

**Status: EM ANDAMENTO. Implementação concluída; congelamento aguarda revisão humana e ampliação de
escala do corpus.**

### Desenvolver

- Selecionar amostras representativas de projetos CEMIG, incluindo diferentes escalas, qualidades, simbologias e densidades.
- Anotar elementos, geometrias, situação e relações visíveis com revisão humana.
- Separar exemplos usados na criação de regras do conjunto final de teste.
- Manter versionados o manifesto anônimo, hashes e política de acesso; nunca versionar os PDFs reais.
- Definir métricas por classe e critérios de regressão: precisão, recall, falhas de extração, latência e consumo de memória.

### Testar

- Validação do formato e dos limites das anotações.
- Amostragem dupla de anotações para medir divergência humana.
- Reprodutibilidade do benchmark com a mesma versão das regras e configuração.

### Critério de saída

Conjunto de teste congelado e critérios numéricos registrados antes da otimização do pipeline.

### Registro de desenvolvimento

- Corpus: as nove amostras foram revisadas visualmente por miniaturas temporárias, classificadas por
  formato, orientação, qualidade e densidade e divididas em cinco exemplos de desenvolvimento e
  quatro de teste final. Os originais não foram alterados.
- Lacuna objetiva: todas as amostras atuais declaram escala 1:1000. A auditoria emite
  `ESCALAS_INSUFICIENTES`, impedindo o congelamento até existir outra escala autorizada.
- Contratos: `ManifestoAvaliacao`, `AnotacaoAmostra`, `CriteriosRegressaoAvaliacao` e
  `RepositorioConjuntoAvaliacaoPort` mantêm o formato independente da UI e do interpretador futuro.
- Formato: schemas JSON v1 cobrem manifesto, anotações e critérios; o adaptador JSON faz validação de
  domínio, caminhos seguros e gravação atômica das anotações.
- Revisão: duas amostras densas da partição de teste estão marcadas para anotação independente. A
  divergência mede correspondência geométrica, categoria, situação e relações antes do consenso.
- Métricas propostas: precisão/recall mínimos de 0,80 a 0,90 por classe, 0,80 para relações, falha de
  extração máxima de 5%, latência p95 máxima de 30 s, pico de memória Python de 512 MiB e divergência
  humana máxima de 15%.
- Benchmark: `ExecutarBenchmarkAvaliacao` valida hashes, isola as partições, mede recursos, agrega
  métricas e produz assinatura semântica independente das oscilações de tempo e memória.
- Privacidade: PDFs, miniaturas e anotações reais permanecem controlados; relatórios publicáveis usam
  somente IDs anônimos, versões, contagens e métricas, conforme `evaluation/POLITICA-ACESSO.md`.
- Decisão arquitetural: ADR 0005 documenta congelamento, partições, revisão humana e limites da
  medição de memória.
- Validação automatizada: 142 testes aprovados, cobertura total de 88,93%, complexidade média geral
  A (3,11), tipagem, lint, formatação e integridade das dependências aprovados. Todos os módulos
  novos têm índice de manutenibilidade A e nenhum bloco de complexidade D, E ou F.
- Pendências para o critério de saída: obter ao menos uma amostra de escala diferente, concluir as
  anotações primárias/secundárias e consensos humanos, aprovar os critérios propostos e então alterar
  manifesto e anotações para `CONGELADO`.
- A direção explícita do usuário autorizou iniciar a infraestrutura da Etapa 6 antes do congelamento.
  A partição de teste não pode orientar regras e o critério de saída da Etapa 6 continua bloqueado até
  a auditoria da Etapa 5 retornar `pronto_para_congelar = true`.

## Etapa 6 - Pipeline modular de interpretação

**Status: EM ANDAMENTO. Implementação técnica inicial concluída; validação no baseline real aguarda
o congelamento da Etapa 5.**

### Desenvolver

- Criar registro versionado de regras de interpretação e parâmetros.
- Relacionar evidências de texto, vetores, imagens e OCR com itens do catálogo.
- Implementar analisadores pequenos e independentes para postes, estruturas MT, estruturas BT, cabos e equipamentos.
- Combinar resultados por regras explícitas de geometria, proximidade, compatibilidade e contexto.
- Gerar `PropostaElemento` e `PropostaRelacao` como trilha auditável e promover automaticamente os
  resultados catalogados para o conjunto confirmado.
- Persistir configuração, tempos, erros e proveniência de cada execução.
- Permitir novos adaptadores no futuro sem alterar domínio, persistência ou interface.

### Testar

- Unitários com adaptador falso e fixtures determinísticas.
- Integração com o conjunto congelado, comparando contra o baseline aprovado.
- Regressão para símbolos pequenos, sobrepostos, rotacionados e páginas densas.
- Cancelamento e retomada sem duplicar propostas.
- Teste arquitetural impedindo que o domínio conheça o mecanismo de análise.

### Critério de saída

O pipeline atinge os limites aprovados e toda proposta é rastreável até as evidências e regras que a originaram.

### Registro de desenvolvimento

- Registro: JSON schema v1, versão e assinatura canônica cobrem cinco regras de reconhecimento e
  sete regras de relação. Um carregador externo permite substituir o registro sem alterar o motor.
- Reconhecimento: analisadores separados por classe relacionam códigos delimitados em texto/OCR com
  itens ativos do catálogo; vetores e imagens próximos entram como contexto e proveniência.
- Situação: assinaturas configuráveis de cor do catálogo diferenciam existente, instalar e remover.
- Relações: proximidade de centros associa estruturas/equipamentos a postes; extremidades associam
  cabos; compatibilidades do catálogo restringem suporte por estruturas MT/BT.
- Promoção automática: resultados com item ativo de catálogo e dependências resolvíveis são
  materializados com IDs determinísticos; propostas e decisões automáticas preservam a auditoria.
- Postes: nomenclaturas como `10-150` e `11-300` aceitam `-`, `/`, `:`, `x`, espaço e quebra de linha;
  coordenadas próximas são combinadas a partir de texto nativo ou OCR.
- Execução: UUID5 inclui projeto, extração, interpretador, regras e configuração. Cancelamento,
  retomada e repetição não duplicam propostas; falhas ficam persistidas e auditáveis.
- Persistência: extração e interpretação usam execuções distintas, com referências de evidência
  permitidas somente dentro do mesmo projeto e publicação atômica dos resultados concluídos.
- Avaliação: adaptador executa o pipeline real sem persistência e já é testado com PDF sintético. O
  teste final permanece recusado até manifesto congelado, consensos humanos e critérios aprovados.
- Normas: a ND 3.1 exige escala 1:1000 em regra geral, admite 1:500 em casos urbanos extraordinários
  e remete à simbologia padronizada; as heurísticas gráficas permanecem configuráveis e revisáveis.
- Decisão arquitetural: ADR 0006 registra o pipeline versionado, idempotência e fronteira entre
  evidência, proposta e confirmação.
- Validação automatizada: 155 testes aprovados, cobertura total de 89,06%, complexidade média geral
  A (3,15), tipagem, lint, formatação e dependências aprovados. Todos os módulos do interpretador têm
  índice de manutenibilidade A e nenhum bloco novo possui complexidade D, E ou F.
- Pendência do critério de saída: executar o benchmark final sobre o conjunto congelado, ajustar
  somente pela partição de desenvolvimento e demonstrar os limites aprovados.

## Etapa 7 - Resultados da análise na interface

**Status: EM ANDAMENTO. Implementação técnica concluída em 2026-07-21; o aceite humano depende do
fluxo operacional da Etapa 7.1.**

### Desenvolver

- Exibir resultados sobre o PDF com filtros por classe e estado.
- Organizar regiões da folha como itens-pai e mostrar abaixo delas todos os elementos e vínculos
  próximos, exista ou não um poste reconhecido.
- Permitir criar manualmente elementos e relações ausentes.
- Registrar autor, data, motivo opcional e histórico de cada decisão.
- Diferenciar visualmente proposta, confirmada, rejeitada e conflitante.

### Testar

- Testes de estado da revisão e histórico imutável.
- Testes Qt de seleção, edição de geometria, zoom e atalhos.
- Reabrir projeto preserva exatamente as decisões.
- Proposta rejeitada nunca reaparece como confirmada após nova análise.

### Critério de saída

Um usuário consegue inspecionar no PDF tudo que a análise já incorporou ao projeto e entender os
vínculos sem confirmar item a item.

### Registro de desenvolvimento

- Aplicação: `ServicoRevisaoHumana` consolida a execução mais recente de cada PDF do projeto e mantém
  aceitar, ajustar, rejeitar, confirmar relação e criações manuais como operações excepcionais
  atômicas.
- Interface: painel lateral de resultados com filtros por classe e estado e uma árvore de vínculos.
  Cada região agrupa elementos próximos e mostra situação, catálogo, confiança e vínculos; os antigos
  campos de decisão e confirmação item a item não fazem parte do fluxo visível.
- PDF: cada proposta de elemento aparece como um sublinhado colorido e clicável; o clique abre a aba
  de resultados e seleciona o nó correspondente. Proposta, confirmada, rejeitada e conflitante usam
  cores e traços distintos. A paginação, o zoom e a rotação permanecem disponíveis durante a revisão.
- Decisões: autor, data, motivo opcional e referência confirmada são persistidos em histórico
  imutável. Aceitação com mudança de classe, catálogo, situação ou geometria é registrada como
  `AJUSTAR`.
- Relações: `RelacaoConfirmada` passou a integrar o agregado do projeto e a projeção SQLite pela
  migração `0004_human_review`; relações propostas só podem ser confirmadas depois de suas
  extremidades estarem confirmadas.
- Criação manual: elementos e relações ausentes podem ser acrescentados pela interface, com autor,
  data e motivo preservados em `RegistroRevisaoManual`.
- Segurança: uma decisão final não pode ser sobrescrita; proposta semanticamente equivalente a uma
  rejeição anterior não pode ser confirmada por uma execução posterior.
- Cabos: quando ainda não existem pontos de rede selecionáveis, a confirmação materializa duas
  extremidades determinísticas a partir da geometria revisada e preserva a polilinha confirmada.
- Atalhos: `A` aceita/salva o ajuste selecionado e `R` rejeita; os controles existentes continuam
  cobrindo seleção, paginação, zoom e rotação.
- Testes: domínio, migração, persistência, reabertura, histórico imutável, rejeição entre execuções,
  filtros Qt, sobreposições e ajuste de geometria estão cobertos por testes automatizados.
- Validação original da entrega: Ruff, formatação e mypy aprovados; 161 de 162 testes aprovados e
  cobertura total de 87,22%, acima do limite estrito de 85%. A reprovação registrada naquele momento
  revelou que PDFs exploratórios adicionais precisavam ser permitidos; a política foi corrigida na
  Etapa 7.1 sem alterar nem registrar automaticamente os arquivos privados.
- Fluxo MVP disponível hoje: projetos e propostas que já estejam persistidos podem ser carregados no
  painel de revisão. Ainda não é possível criar o projeto, importar seus PDFs e disparar
  extração/interpretação pela interface; essa ponte é o escopo da Etapa 7.1.
- Como aceitar após a Etapa 7.1: iniciar pelos launchers normais, criar ou abrir um projeto autorizado,
  importar suas folhas, executar a análise, revisar todas as propostas de uma página, criar uma
  ausência manual, salvar, fechar e reabrir conferindo que as decisões foram preservadas.
- Próximo passo técnico: etapa 7.1, tornando o caminho completo até esta revisão utilizável sem
  terminal, fixtures ou acesso direto ao banco.

## Etapa 7.1 - Fluxo operacional do MVP pela interface

**Status: EM ANDAMENTO. Implementação técnica concluída em 2026-07-21; aguarda aceite humano pela
interface.**

### Desenvolver

- Criar uma tela inicial para listar, criar, abrir e renomear projetos persistidos, usando uma versão
  publicada do catálogo sem exigir acesso direto ao SQLite.
- Integrar a seleção de um ou vários PDFs diretamente ao caso de uso de importação, preservando cada
  documento, e permitir editar a ordem de qualquer página; essa sequência deve sobreviver ao
  fechamento e à reabertura.
- Expor na interface as ações de extrair evidências e executar a interpretação, com progresso,
  cancelamento, retomada, mensagens de erro localizadas e indicação clara da execução ativa.
- Encadear o resultado concluído ao painel da Etapa 7, consolidando a execução mais recente de cada
  PDF sem preparação manual de banco, scripts ou fixtures.
- Exibir o estado operacional do projeto: documentos, última extração, última interpretação,
  propostas pendentes, decisões realizadas e falhas que exigem ação.
- Fornecer um modo ou roteiro visível de aceite do MVP, com passos e resultados esperados, sem enviar
  dados a serviços externos.
- Garantir que fechar e reabrir o aplicativo restaure o projeto, documentos, execuções, propostas,
  decisões e página de trabalho de forma coerente.

### Testar

- E2E Qt partindo de uma pasta de dados vazia: criar projeto, importar um PDF, executar extração e
  interpretação, inspecionar os resultados promovidos, fechar e reabrir.
- E2E com várias folhas em arquivos separados, reordenação persistida, fontes e paginação do projeto.
- Falha, proteção, corrupção ou alteração de um PDF não deixa projeto, execução ou interface em estado
  parcialmente publicado.
- Cancelar e retomar análise pela interface não duplica execuções, evidências ou propostas.
- Projeto sem proposta, sem origem disponível ou com execução falha apresenta orientação acionável,
  sem traceback ou necessidade de terminal.
- Smoke test pelos launchers cotidianos, usando somente controles visíveis da aplicação.

### Critério de saída

Um usuário de MVP inicia o aplicativo pelos launchers normais e, sem ferramentas de desenvolvimento,
consegue criar ou abrir um projeto, importar uma ou várias folhas, executar o pipeline, chegar aos
resultados relacionados, fechar e reabrir preservando o trabalho.

### Roteiro de aceite humano esperado

1. Abrir o aplicativo por `ZenyProjectHandler.vbs` ou `ZenyProjectHandler.bat`.
2. Criar um projeto e selecionar um ou vários PDFs autorizados.
3. Executar extração e interpretação acompanhando estado, progresso e eventuais diagnósticos.
4. Abrir os resultados, expandir uma região e conferir estruturas/equipamentos vinculados no PDF.
5. Fechar o aplicativo, abri-lo novamente e conferir documentos, página e resultados promovidos.
6. Informar aprovação ou problemas observados; somente a aprovação explícita permite concluir as
   Etapas 7 e 7.1.

### Registro de desenvolvimento

- Tela inicial: o painel **Fluxo do projeto** lista, cria, abre e renomeia projetos persistidos. O
  catálogo inicial publicado é instalado automaticamente em uma pasta de dados vazia.
- Exclusão: um projeto pode ser excluído pela interface após confirmação explícita. A remoção abrange
  os dados locais do projeto por cascata transacional, mas nunca apaga os PDFs originais no disco.
- Importação: a seleção de um ou vários PDFs usa o caso de uso transacional real. Todos os arquivos
  são validados antes da publicação, duplicidades são recusadas e documento, origem e sequência de
  páginas são preservados sem concatenar ou modificar os PDFs.
- Remoção de folhas: o usuário seleciona um ou vários PDFs já importados. Uma confirmação informa que
  extrações, propostas, decisões e elementos dependentes serão removidos; documentos e resultados não
  relacionados permanecem no projeto e os arquivos originais são preservados.
- Pipeline: **Executar análise completa** processa cada documento em uma thread de trabalho, exibe
  progresso e execução ativa e encadeia extração, interpretação, promoção e resultados sem bloquear
  a janela.
- Cancelamento e retomada: o cancelamento ocorre em pontos seguros entre documentos ou dentro da
  interpretação. IDs determinísticos reutilizam extrações concluídas e o pipeline idempotente impede
  execuções, evidências e propostas duplicadas na retomada.
- Estado operacional: a interface mostra quantidade de PDFs e folhas, estados da última extração e
  interpretação, propostas pendentes e decisões realizadas. Falhas esperadas aparecem como mensagens
  localizadas, sem traceback.
- Resultados: projetos analisados são abertos diretamente no painel da Etapa 7. Projetos com vários
  documentos consolidam a execução mais recente de cada PDF; regiões agrupam os elementos e vínculos
  relacionados seguindo a sequência de páginas do projeto.
- Recuperação: o último projeto e a última folha aberta ficam em `ui-state.ini` na pasta local da
  aplicação; projeto, documentos, fontes, execuções, propostas e decisões continuam no SQLite.
- Aceite: o botão **Como validar este MVP** apresenta o roteiro dentro da própria aplicação.
- Testes adicionados: importação múltipla atômica, ordem e reabertura das fontes, cancelamento e
  retomada sem duplicação, remoção seletiva com limpeza das dependências, exclusão integral do projeto
  e E2E Qt partindo de pasta vazia até propostas revisáveis, reabertura e remoções pela interface.
- Corpus local: novos PDFs em `examples/` são amostras exploratórias permitidas e entram
  automaticamente em um smoke test anônimo somente leitura. O manifesto permanece reservado ao
  conjunto formal, que exige classificação e anotação; nenhum arquivo privado é alterado ou incluído
  automaticamente no Git.
- Correção de aceite: a exclusão de projeto e a remoção de PDF agora eliminam explicitamente
  decisões, propostas, evidências e demais dependências na ordem segura antes do registro principal.
  Isso evita violação de chave estrangeira em projetos que já possuem propostas confirmadas e
  funciona nos bancos existentes sem migração destrutiva.
- Revisão de reconhecimento de postes: a planilha fornecida foi conferida contra o seed e possui o
  mesmo SHA-256, 38 postes e as mesmas opções de formato; portanto, não foi necessário apagar nem
  migrar o banco. A falha estava na diferença entre códigos internos como
  `P-11M-300DAN-CIRCULAR` e anotações reais como `11-300`.
- Interpretação 3.0: postes aceitam nomenclatura altura-resistência em texto nativo ou OCR, inclusive
  com `:`, `/`, espaço e quebra de linha. O formato explícito resolve o item do catálogo; sem formato,
  o tipo canônico é escolhido e os candidatos permanecem auditáveis. Coordenadas próximas são
  combinadas entre fragmentos nativos/OCR, e relações preferem postes com a mesma situação de obra.
- Interpretação 4.0: equipamentos aceitam nomenclaturas abreviadas observadas nos desenhos, como
  `3-150` para o item `-3-150` e `1-37.5 KVA` para `-1-37,5`; coordenadas contíguas separadas por
  quebra de linha, `:` ou `/` deixam de ser confundidas como um único número.
- OCR local: o Tesseract instalado é descoberto automaticamente e recebe a página por memória. Além
  de páginas rasterizadas, páginas com mais de 1.000 vetores são processadas para recuperar textos
  plotados como caminhos, mesmo quando o carimbo possui texto nativo. Nenhum PDF é enviado à rede.
- Verificação exploratória: os dez PDFs privados atualmente em `examples/` passaram a produzir ao
  menos uma proposta de poste; nove foram resolvidos pelo texto nativo e o décimo pelo OCR da página
  vetorial. Isso é smoke test, não substitui o benchmark anotado e o aceite humano das Etapas 5 e 6.
- Referência normativa: a ND 3.1/2025 exige a simbologia do Electric Office, identificação do tipo de
  poste/estrutura e numeração sequencial. A IT-EO-008 distingue postes Circular, Duplo T e Madeira e
  os estados existente, instalar/substituir/retirar/abandonar; as propostas continuam sujeitas à
  revisão humana quando o desenho não oferece evidência suficiente.
- Validação atual: Ruff, formatação, mypy e os 175 testes aprovados; cobertura total de 87,00%,
  acima do limite estrito de 85,01%. O PDF exploratório adicional foi lido e renderizado pelo smoke
  test sem modificação de tamanho ou data do arquivo; os testes de exclusão também confirmam que os
  PDFs originais permanecem no disco.
- Próximo passo: executar o roteiro de aceite humano acima pelos launchers normais e validar as
  regiões de ocorrência em páginas autorizadas.

## Etapa 8 - Agrupamento por regiões do PDF

**Status: EM ANDAMENTO. Implementação técnica concluída em 2026-07-22; aguarda validação humana em
projetos reais.**

### Desenvolver

- Agrupar elementos próximos na mesma página sem depender de um poste como item-pai.
- Associar coordenadas UTM lidas de texto nativo ou OCR, inclusive em fragmentos separados.
- Resumir instalações, retiradas e elementos existentes dentro da mesma região.
- Mostrar catálogo e vínculos semânticos em cada elemento, preservando o sublinhado clicável no PDF.
- Remover projeções, dependências, pacotes portáteis e painéis de grafo.

### Testar

- Regiões com e sem coordenada, múltiplas situações e diferentes páginas.
- Coordenadas separadas por quebra de linha, `:`, `/` ou fragmentos próximos.
- Múltiplos pares próximos são associados um a um, sem reutilizar leste ou norte entre pontos.
- Pequenas regiões rasterizadas em páginas com texto nativo recebem OCR localizado.
- Itens distantes na mesma página não são unidos.
- Clique em elemento navega para a folha correta e destaca o sublinhado.

### Critério de saída

O usuário compreende o que acontece em cada local da folha sem confirmar item a item e sem precisar
interpretar nós, arestas ou diagnósticos de grafo.

## Histórico supersedido - reconstrução e validação do grafo

> Esta seção registra a implementação anterior apenas como histórico. Ela foi substituída pela Etapa
> 8 de regiões em 2026-07-22; o código, a dependência NetworkX e a interface descritos abaixo foram
> removidos do produto.

**Status: EM ANDAMENTO. Implementação técnica concluída em 2026-07-21; aguarda aceite humano pela
interface.**

### Desenvolver

- Gerar visão física com postes e equipamentos e visão elétrica com pontos e terminais.
- Representar cabos paralelos com `MultiGraph`; derivar direção apenas quando origem e fluxo forem conhecidos.
- Propor conexões por geometria, vetores do PDF, proximidade e regras de compatibilidade.
- Exigir revisão humana para conexões ambíguas.
- Detectar componentes desconectados, pontas órfãs, tensões ou fases incompatíveis, ciclos inesperados e equipamentos sem terminais.
- Disponibilizar pela interface as visões física e elétrica, a reconstrução, os filtros e a lista de
  diagnósticos; selecionar um diagnóstico deve destacar seus elementos e permitir navegar até a
  evidência correspondente no PDF.

### Testar

- Topologias canônicas: radial simples, derivação, transformador MT/BT, chave, cabo paralelo, ilha e ciclo.
- Independência da ordem de inserção dos elementos.
- Idempotência da geração do grafo.
- Erros indicam os elementos de origem e não corrompem o projeto.
- Teste Qt do fluxo de reconstruir, alternar visão, filtrar diagnóstico e navegar do grafo ao PDF.

### Critério de saída

O mesmo conjunto confirmado sempre gera o mesmo grafo e um usuário consegue, somente pela
interface, compreender as inconsistências, revisar ambiguidades e navegar até suas evidências no PDF.

### Roteiro de aceite humano esperado

1. Abrir pela interface um projeto da Etapa 7.1 com elementos confirmados.
2. Reconstruir o grafo e alternar entre as visões física e elétrica.
3. Inspecionar ao menos um diagnóstico e navegar dele até os elementos e o PDF de origem.
4. Resolver ou justificar uma conexão ambígua, reconstruir novamente e conferir o resultado
   persistido após reabrir o projeto.

### Registro de desenvolvimento

- Arquitetura: `ResultadoReconstrucaoGrafo` é uma projeção imutável do conjunto confirmado. O
  domínio e a aplicação dependem de uma porta própria; o adaptador NetworkX materializa
  `MultiGraph` somente durante a reconstrução e o SQLite continua armazenando as entidades de
  origem, não uma segunda fonte de verdade.
- Visão física: postes e equipamentos são nós; instalação de equipamento, percurso de cabo por
  postes e relações físicas confirmadas formam as arestas. A geometria confirmada posiciona os nós
  na mesma disposição normalizada das folhas.
- Visão elétrica: pontos de rede e terminais são nós; cabos, ligações terminal-ponto, conexões
  internas conectadas e relações confirmadas formam arestas. Cabos paralelos permanecem arestas
  distintas. Os grafos são não direcionados porque o modelo confirmado atual não informa fonte nem
  sentido de fluxo.
- Determinismo: UUID5 identifica nós, arestas, sugestões e diagnósticos; ordenação canônica e uma
  assinatura SHA-256 permitem comprovar idempotência e rejeitar confirmações feitas sobre uma
  reconstrução desatualizada.
- Sugestões: uma ponta órfã pode receber candidatos da mesma folha dentro da tolerância geométrica,
  desde que nível, tensão e fases sejam compatíveis. Geometrias confirmadas podem ter sido obtidas
  de texto, OCR, imagens ou vetores do PDF na etapa de interpretação. Um candidato único vira
  conexão sugerida; vários candidatos permanecem ambíguos e exigem escolha humana.
- Diagnósticos: componentes desconectados, pontas órfãs, ciclos inesperados, tensão/fases
  incompatíveis, incompatibilidade estrutura-cabo, equipamento sem terminais e continuidade interna
  desconhecida indicam as entidades de origem e a visão afetada.
- Persistência da revisão: **Confirmar conexão** cria uma `RelacaoConfirmada` e um
  `RegistroRevisaoManual` com responsável, data e justificativa, em uma transação. Reabrir o projeto
  e reconstruir reproduz a mesma topologia confirmada.
- Interface: o painel **Grafo do projeto** lista projetos, reconstrói sob comando, alterna as visões,
  filtra tipos de nó e severidades, destaca referências ao selecionar um diagnóstico e abre a folha
  correta no visualizador com sobreposição. Ao trocar de projeto, as fontes PDF corretas substituem
  qualquer documento anteriormente aberto.
- Testes: topologia radial, derivação, transformador MT/BT, chave aberta/desconhecida, cabos
  paralelos, ilha, ciclo, incompatibilidade, equipamento sem terminais, sugestão por proximidade,
  independência da ordem, idempotência, confirmação/reabertura SQLite e fluxo Qt estão cobertos. A
  suíte completa possui 183 testes aprovados e cobertura de 86,68%, acima do limite estrito de
  85,01%. O gate oficial
  `IniciarTestes.bat` também aprovou integridade das dependências, Ruff, formatação, mypy e métricas.
- Limitação intencional: sentido de fluxo não é inferido sem evidência confirmada. A projeção não
  promove propostas da análise semântica; primeiro elas precisam passar pela revisão da Etapa 7.
- Próximo passo: executar o roteiro de aceite acima em um projeto autorizado. Somente a aprovação
  explícita permite marcar a Etapa 8 como `CONCLUÍDA`.

## Etapa 9 - Gestão do catálogo pela interface

### Desenvolver

- CRUD de rascunho para tipos, opções, compatibilidades e regras de simbologia.
- Publicação imutável de nova versão, comparação entre versões e desativação segura.
- Importação e exportação JSON e nova importação de planilha com prévia de alterações.
- Impedir exclusão física de valores usados por projetos.
- Oferecer pela interface uma área de rascunhos, comparação, validação e publicação, com mensagens
  acionáveis e confirmação explícita antes de disponibilizar uma nova versão.

### Testar

- Editar rascunho não altera projetos existentes.
- Publicar cria nova versão consistente.
- Importar dados inválidos produz relatório e rollback completo.
- Interface de compatibilidade impede relações duplicadas.
- E2E Qt cria um rascunho, importa uma alteração, revisa a prévia, publica e comprova que um projeto
  anterior continua vinculado à versão antiga.

### Critério de saída

O usuário altera e publica as possibilidades do sistema somente pela interface, sem recompilar e sem
modificar o significado de projetos antigos.

### Roteiro de aceite humano esperado

1. Abrir a gestão do catálogo pela interface e criar um rascunho a partir da versão publicada.
2. Alterar um item e uma compatibilidade, conferir validações e comparar as versões.
3. Publicar a nova versão e usá-la em um novo projeto.
4. Reabrir um projeto antigo e confirmar que ele preserva a versão e o significado originais.

## Etapa 10 - Transporte e recuperação

**Status: EM ANDAMENTO. Implementação técnica concluída em 21/07/2026; aguarda aceite humano pela interface.**

### Desenvolver

- Definir pacote de projeto com manifesto, banco, PDFs e resultados auditáveis.
- Salvar caminhos relativos e validar hash e tipo de arquivo.
- Implementar exportação, importação, backup e recuperação após falha.
- Expor exportação, importação, backup e restauração pela interface, com progresso, destino explícito
  e confirmação para substituições. Fotos e relatório de integridade não fazem parte do fluxo.

### Testar

- Mover o pacote para outra pasta ou máquina mantém referências válidas.
- Pacotes ausentes ou adulterados são recusados pelas validações internas.
- Exportação seguida de importação preserva IDs, catálogo, análises e decisões.
- Backup interrompido não substitui a última versão íntegra.
- E2E Qt exporta um projeto, importa-o em uma pasta de dados vazia e restaura um backup sem recorrer
  ao terminal ou manipular o pacote manualmente.

### Critério de saída

O projeto é transportável e recuperável pela interface; pacotes e backups são validados internamente
antes de alterar os dados locais.

### Roteiro de aceite humano esperado

1. Exportar o projeto pela interface.
2. Importar o pacote em outra pasta ou máquina autorizada e conferir PDFs, análises e decisões.
3. Criar e restaurar um backup, validando que a última versão íntegra pode ser recuperada.

### Registro de desenvolvimento

- O formato portátil `.zphproj` contém manifesto assinado, SQLite restrito ao projeto e PDFs. Todos os
  caminhos internos são relativos e cada arquivo possui tipo, tamanho e SHA-256 verificáveis.
- A leitura do pacote rejeita caminhos inseguros, entradas duplicadas, links simbólicos e conteúdo
  criptografado. Arquivos ausentes, alterados ou incompatíveis impedem que um pacote inválido altere
  os dados locais.
- Exportar e importar preserva IDs, catálogo, execuções, evidências, propostas e decisões. Substituir
  um projeto existente exige confirmação e a troca do
  banco e dos arquivos possui rollback em caso de falha.
- O formato `.zphbackup` reúne um snapshot íntegro do banco, arquivos gerenciados e cópias dos PDFs
  externos. A publicação é atômica; a restauração valida o pacote e preserva a versão anterior se a
  troca não puder ser concluída.
- O painel **Portabilidade e recuperação** oferece exportação, importação, backup, restauração e
  progresso sem exigir terminal ou edição manual do pacote.
- Gates oficiais de 21/07/2026: dependências íntegras, Ruff e formatação aprovados, mypy sem erros em
  150 arquivos, 188 testes aprovados e cobertura total de 85,44%.
- O aceite humano continua pendente e, por isso, a etapa permanece `EM ANDAMENTO` mesmo após a
  conclusão dos testes automatizados.

## Etapa 11 - Empacotamento e aceite

### Desenvolver

- Gerar instalador do aplicativo para Windows.
- Criar diagnóstico de primeiro uso para pastas, permissões, banco e dependências locais.
- Garantir operação totalmente local e sem tráfego de dados do projeto.
- Documentar atualização de banco, catálogo e aplicativo de forma independente.
- Incluir na própria aplicação acesso ao guia do fluxo MVP, versão instalada, diagnóstico local,
  diretório dos projetos e instruções de recuperação, sem depender do ambiente de desenvolvimento.

### Testar

- Instalação limpa em máquina-alvo sem ambiente de desenvolvimento.
- Atualização e desinstalação preservam os projetos do usuário.
- Teste ponta a ponta: importar PDF, extrair evidências, revisar regiões, exportar, salvar, fechar e
  reabrir.
- Teste de privacidade confirma ausência de tráfego externo durante o processamento.
- Benchmark final no conjunto congelado e comparação com os limites definidos na etapa 5.

### Critério de saída

Fluxo ponta a ponta aprovado na máquina-alvo, documentação atualizada e nenhuma limitação crítica sem tratamento ou aviso explícito.

### Roteiro de aceite humano esperado

1. Instalar em uma máquina-alvo limpa e iniciar pelo atalho instalado.
2. Executar o fluxo completo das Etapas 7.1, 7, 8, 9 e 10 usando apenas a aplicação instalada.
3. Fechar, atualizar e reabrir o aplicativo, conferindo a preservação dos projetos.
4. Revisar diagnóstico, privacidade, desempenho e limitações exibidas e registrar o aceite final.

## Etapa 12 - Comissionamento e conformidade

### Desenvolver

- Normalizar evidências em fatos auditáveis por projeto, documento, página, região e elemento.
- Manter regras normativas versionadas com fonte, revisão, aplicabilidade, exceções e requisitos.
- Extrair cabeçalho, servidão, carimbos, assinaturas, comprimentos de vão e ângulos.
- Relacionar tecnologia, tensão, seção, estrutura, poste e equipamento antes de aplicar tabelas.
- Exibir documentação, vãos/ângulos e conformidade em um painel próprio com navegação para o PDF.
- Persistir fatos, achados, confirmações e a versão do registro usada.
- Criar um modelo de coleta de campo com proveniência independente e comparação
  `projetado x encontrado x exigido`.
- Implementar avaliadores especializados para compatibilidade, topologia, afastamentos, cardinalidade
  e cálculos, publicando resultados como fatos.
- Experimentar Unlimited-OCR somente atrás de `MotorOcrPort`, com servidor local direto e benchmark;
  MCP não faz parte do pipeline determinístico.

### Testar

- Casos sintéticos de conforme, possível divergência, não avaliável e exceção comprovada.
- Repetição produz as mesmas assinaturas e não mistura fatos de alvos diferentes.
- Ângulos geométricos usam dois vãos conectados no poste, as dimensões físicas da folha e não são
  deformados pela normalização; um vértice isolado dentro de um cabo não forma ângulo.
- Vão urbano não é aplicado a projeto rural nem a tecnologia desconhecida.
- Chave fusível respeita a exceção; outros equipamentos até 30° exigem avaliação de abalroamento.
- Ausência de assinatura visual ou servidão não é convertida em reprovação universal.
- Alterar revisão ou condição normativa muda a assinatura sem reinterpretar histórico.
- O benchmark OCR mede texto crítico, caixas, alucinação, latência, memória e operação offline apenas
  na partição autorizada de desenvolvimento.

### Critério de saída

O sistema compara fatos persistidos de projeto e campo com um registro normativo aprovado, explica
cada achado até a evidência e a fonte e não confunde dado ausente, exceção ou baixa confiança com
descumprimento confirmado.

### Registro de desenvolvimento

- Criados domínio, carregador JSON, schema e avaliador determinístico em três estados.
- Registro inicial baseado na ND-3.1 Jul/2025 inclui numeração, formato, escala, vão urbano,
  equipamento em ângulo, chave fusível, exceção entre 45 e 60 m e risco de abalroamento.
- Scanner inicial deriva campos documentais e controles PDF; medidas de vão e ângulo aguardam a
  próxima implementação.
- Dock próprio integrado à janela principal com as três visões e navegação até a folha.
- Cabeçalhos são excluídos do inventário sem perder a inspeção documental; nomenclaturas de cabo
  ainda não catalogadas são preservadas para revisão.
- Campos de cabeçalho e do quadro de servidão são enumerados genericamente por
  `rótulo: informação`, sem limitar a interface ao vocabulário normativo inicial.
- A árvore de resultados permite ocultar no PDF o ponto inteiro ou elementos individuais por ícones
  de olho, sem excluir as propostas.
- O detector de vãos, comprimentos e ângulos foi removido integralmente; sua reconstrução depende da
  próxima definição de modelo e não reutilizará as heurísticas anteriores.
- ADRs 0011 e 0012 registram respectivamente a arquitetura normativa e a decisão sobre OCR local.
- Persistência, coleta de campo, validadores criptográficos e promoção de achados permanecem futuros.

## Estratégia global de testes

- Unitários: domínio, catálogo, extração, transformações geométricas e agrupamento de regiões; rápidos e sem I/O externo.
- Contrato: todos os adaptadores devem respeitar suas portas, especialmente persistência, PDF e análise.
- Integração: SQLite, PyMuPDF, adaptador de análise falso e componentes Qt.
- Golden: renderizações e projeções de coordenadas com tolerâncias controladas.
- Regressão de interpretação: conjunto congelado, versão das regras fixada e métricas por classe.
- E2E técnico: fluxos completos com banco e diretórios temporários, incluindo falhas e retomadas.
- E2E do incremento vertical: partir da tela inicial e alcançar o resultado da etapa somente por
  controles visíveis, sem fixtures preparadas diretamente no banco.
- Smoke dos launchers: validar que o mesmo caminho usado nos testes pode ser iniciado pelos atalhos
  cotidianos do MVP.
- Aceite humano: executar o roteiro documentado com dados autorizados, registrar problemas e manter
  a etapa `EM ANDAMENTO` até a aprovação explícita do usuário.
- Desempenho: tempo de abertura, renderização, extração, interpretação, memória e tamanho do projeto.

## Condições de parada

O Codex deve interromper o avanço e registrar bloqueio quando ocorrer qualquer uma destas condições:

- necessidade de enviar PDF, imagem ou dados do projeto a serviço externo sem autorização explícita;
- tentativa de introduzir um modelo ou biblioteca cuja licença seja incompatível com a finalidade do aplicativo;
- qualidade do pipeline abaixo do critério aprovado;
- migração com risco de perda de projetos existentes;
- relação elétrica ambígua sem regra ou revisão humana disponível;
- critério de aceite que dependa de terminal, fixture, edição direta do banco ou outra capacidade não
  exposta pela interface do MVP;
- necessidade de mudar uma decisão estrutural sem atualizar o diagrama, a especificação e este roadmap.

## Fontes técnicas de referência

- [Qt for Python](https://doc.qt.io/qtforpython-6/): bindings oficiais PySide6 e requisitos.
- [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/): renderização, recortes, texto, vetores, imagens e OCR.
- [SQLAlchemy 2.x](https://docs.sqlalchemy.org/en/20/): persistência e mapeamento ORM.
- [pytest](https://docs.pytest.org/en/stable/): testes, fixtures e parametrização.
