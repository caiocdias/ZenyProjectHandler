# Roadmap de desenvolvimento do Zeny Project Handler

> Documento operacional para orientar o Codex. Ele define a ordem de implementação e os testes mínimos de cada etapa. Não é um cronograma nem uma especificação comercial.

## Diretriz sobre análise automática

O projeto não inclui um motor de aprendizado de máquina predefinido, código de inferência, pesos ou requisitos de GPU. A interpretação automática será construída por uma porta genérica e testável, começando por informações nativas do PDF, processamento de imagem e regras de domínio.

Nenhum serviço externo ou modelo específico deve ser introduzido sem uma decisão futura explícita, registrada em ADR e acompanhada de avaliação de licença, privacidade, hardware, qualidade e manutenção.

## Regras de execução para o Codex

1. Trabalhar em apenas uma etapa por vez, respeitando as dependências indicadas.
2. Antes de iniciar uma etapa, conferir seus critérios de entrada e registrar decisões novas neste documento ou em um ADR.
3. Não avançar enquanto os critérios de saída e os testes da etapa atual não estiverem satisfeitos.
4. Manter domínio, interface, persistência, processamento de PDF, análise e grafo desacoplados por portas e adaptadores.
5. A suíte padrão deve executar sem rede, serviços externos ou arquivos confidenciais.
6. Toda ocorrência automática é uma proposta revisável. Ela não pode alterar diretamente o conjunto confirmado do projeto.
7. Fixar versões das dependências e manter migrações compatíveis com projetos já salvos.
8. Ao concluir uma etapa, atualizar a tabela de estado e registrar arquivos alterados, comandos de teste, limitações e próximo passo.

## Estado das etapas

| Etapa | Estado inicial | Depende de |
|---|---|---|
| 0. Fundação do projeto Python | CONCLUÍDA | - |
| 1. Revisão do domínio e catálogo | CONCLUÍDA | 0 |
| 1.1 Calibração com projetos reais | CONCLUÍDA | 1 |
| 2. Persistência local | CONCLUÍDA | 1.1 |
| 3. Ingestão e visualização de PDF | CONCLUÍDA | 1.1, 2 |
| 4. Extração de evidências do PDF | CONCLUÍDA | 3 |
| 5. Conjunto de avaliação | EM ANDAMENTO | 3, 4 |
| 6. Pipeline modular de interpretação | EM ANDAMENTO | 1, 4, 5 |
| 7. Revisão humana na interface | PENDENTE | 3, 6 |
| 8. Reconstrução e validação do grafo | PENDENTE | 1, 7 |
| 9. Gestão do catálogo pela interface | PENDENTE | 2, 7 |
| 10. Projeto portátil, fotos e recuperação | PENDENTE | 2, 7, 8 |
| 11. Empacotamento e aceite | PENDENTE | 8, 9, 10 |

Estados permitidos: `PENDENTE`, `EM ANDAMENTO`, `BLOQUEADA` e `CONCLUÍDA`.

## Stack de referência

- Linguagem: Python 3.11.
- Aplicativo desktop: PySide6 com Qt Widgets e `QGraphicsView` para PDF, sobreposições e edição gráfica.
- Domínio: classes Python sem dependência de Qt, ORM ou bibliotecas de análise; `dataclasses` e Pydantic somente nas fronteiras de entrada e saída.
- Persistência: SQLite como armazenamento canônico, SQLAlchemy 2.x como adaptador ORM e Alembic para migrações. JSON será formato de importação e exportação, não o banco principal.
- PDF: PyMuPDF para metadados, texto incorporado, vetores, imagens, renderização e recortes.
- Imagem: Pillow como base; OpenCV poderá ser adotado no adaptador de análise raster se os testes demonstrarem necessidade.
- OCR: porta independente e implementação escolhida somente após benchmark com projetos reais.
- Grafo: NetworkX como projeção e mecanismo de validação; as entidades persistidas continuam sendo a fonte de verdade.
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
    graph/
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
9. Revisar a projeção do grafo: postes servem à visão física; pontos de rede e terminais servem à visão elétrica. Equipamentos também podem produzir arestas internas.
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

### Testar

- PDFs vetoriais, escaneados, rotacionados, multipágina e com `CropBox` diferente de `MediaBox`.
- Smoke test parametrizado pelos hashes do manifesto das nove amostras reais.
- Anotação malformada, fonte ausente e objeto não suportado geram diagnóstico localizado sem impedir
  a renderização válida do restante da página.
- Golden tests de renderização com tolerância documentada.
- Round-trip de coordenadas em diferentes DPI e rotações.
- Arquivo inválido, protegido ou corrompido não altera o projeto existente.

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
- Interface: `QGraphicsView` com paginação, zoom, ajuste, rotação, arraste e sobreposições alinhadas.
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
- Gerar `PropostaElemento` e `PropostaRelacao`; nunca criar diretamente um elemento confirmado.
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
- Segurança: resultados são sempre propostas. Código ausente ou evidência visual isolada não produz
  entidade confirmada.
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

## Etapa 7 - Revisão humana na interface

### Desenvolver

- Exibir propostas sobre o PDF com filtros por classe e estado.
- Permitir aceitar, rejeitar, mover, redimensionar, reclassificar e vincular ao catálogo.
- Permitir criar manualmente elementos e relações ausentes.
- Registrar autor, data, motivo opcional e histórico de cada decisão.
- Diferenciar visualmente proposta, confirmada, rejeitada e conflitante.

### Testar

- Testes de estado da revisão e histórico imutável.
- Testes Qt de seleção, edição de geometria, zoom e atalhos.
- Reabrir projeto preserva exatamente as decisões.
- Proposta rejeitada nunca reaparece como confirmada após nova análise.

### Critério de saída

Um usuário consegue transformar todas as propostas de uma página em um conjunto confirmado, corrigindo erros sem editar arquivos manualmente.

## Etapa 8 - Reconstrução e validação do grafo

### Desenvolver

- Gerar visão física com postes e equipamentos e visão elétrica com pontos e terminais.
- Representar cabos paralelos com `MultiGraph`; derivar direção apenas quando origem e fluxo forem conhecidos.
- Propor conexões por geometria, vetores do PDF, proximidade e regras de compatibilidade.
- Exigir revisão humana para conexões ambíguas.
- Detectar componentes desconectados, pontas órfãs, tensões ou fases incompatíveis, ciclos inesperados e equipamentos sem terminais.

### Testar

- Topologias canônicas: radial simples, derivação, transformador MT/BT, chave, cabo paralelo, ilha e ciclo.
- Independência da ordem de inserção dos elementos.
- Idempotência da geração do grafo.
- Erros indicam os elementos de origem e não corrompem o projeto.

### Critério de saída

O mesmo conjunto confirmado sempre gera o mesmo grafo, com inconsistências explicáveis e navegáveis até o PDF.

## Etapa 9 - Gestão do catálogo pela interface

### Desenvolver

- CRUD de rascunho para tipos, opções, compatibilidades e regras de simbologia.
- Publicação imutável de nova versão, comparação entre versões e desativação segura.
- Importação e exportação JSON e nova importação de planilha com prévia de alterações.
- Impedir exclusão física de valores usados por projetos.

### Testar

- Editar rascunho não altera projetos existentes.
- Publicar cria nova versão consistente.
- Importar dados inválidos produz relatório e rollback completo.
- Interface de compatibilidade impede relações duplicadas.

### Critério de saída

O usuário altera as possibilidades do sistema sem recompilar e sem modificar o significado de projetos antigos.

## Etapa 10 - Projeto portátil, fotos e recuperação

### Desenvolver

- Definir pacote de projeto com manifesto, banco, PDF, fotos e artefatos derivados.
- Salvar caminhos relativos e validar hash e tipo de arquivo.
- Implementar anexar, remover, localizar arquivo ausente e deduplicar fotos.
- Implementar exportação, importação, backup e recuperação após falha.

### Testar

- Mover o pacote para outra pasta ou máquina mantém referências válidas.
- Arquivo ausente ou adulterado é sinalizado sem impedir a abertura.
- Exportação seguida de importação preserva IDs, catálogo, decisões e grafo.
- Backup interrompido não substitui a última versão íntegra.

### Critério de saída

O projeto é transportável e recuperável, com integridade verificável dos arquivos associados.

## Etapa 11 - Empacotamento e aceite

### Desenvolver

- Gerar instalador do aplicativo para Windows.
- Criar diagnóstico de primeiro uso para pastas, permissões, banco e dependências locais.
- Garantir operação totalmente local e sem tráfego de dados do projeto.
- Documentar atualização de banco, catálogo e aplicativo de forma independente.

### Testar

- Instalação limpa em máquina-alvo sem ambiente de desenvolvimento.
- Atualização e desinstalação preservam os projetos do usuário.
- Teste ponta a ponta: importar PDF, extrair evidências, revisar propostas, gerar grafo, anexar foto, salvar, fechar e reabrir.
- Teste de privacidade confirma ausência de tráfego externo durante o processamento.
- Benchmark final no conjunto congelado e comparação com os limites definidos na etapa 5.

### Critério de saída

Fluxo ponta a ponta aprovado na máquina-alvo, documentação atualizada e nenhuma limitação crítica sem tratamento ou aviso explícito.

## Estratégia global de testes

- Unitários: domínio, catálogo, extração, transformações geométricas e regras do grafo; rápidos e sem I/O externo.
- Contrato: todos os adaptadores devem respeitar suas portas, especialmente persistência, PDF e análise.
- Integração: SQLite, PyMuPDF, adaptador de análise falso e componentes Qt.
- Golden: renderizações e projeções de coordenadas com tolerâncias controladas.
- Regressão de interpretação: conjunto congelado, versão das regras fixada e métricas por classe.
- E2E: fluxos completos com banco e diretórios temporários.
- Desempenho: tempo de abertura, renderização, extração, interpretação, memória e tamanho do projeto.

## Condições de parada

O Codex deve interromper o avanço e registrar bloqueio quando ocorrer qualquer uma destas condições:

- necessidade de enviar PDF, imagem ou dados do projeto a serviço externo sem autorização explícita;
- tentativa de introduzir um modelo ou biblioteca cuja licença seja incompatível com a finalidade do aplicativo;
- qualidade do pipeline abaixo do critério aprovado;
- migração com risco de perda de projetos existentes;
- relação elétrica ambígua sem regra ou revisão humana disponível;
- necessidade de mudar uma decisão estrutural sem atualizar o diagrama, a especificação e este roadmap.

## Fontes técnicas de referência

- [Qt for Python](https://doc.qt.io/qtforpython-6/): bindings oficiais PySide6 e requisitos.
- [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/): renderização, recortes, texto, vetores, imagens e OCR.
- [SQLAlchemy 2.x](https://docs.sqlalchemy.org/en/20/): persistência e mapeamento ORM.
- [NetworkX](https://networkx.org/documentation/stable/): estruturas e algoritmos de grafos.
- [pytest](https://docs.pytest.org/en/stable/): testes, fixtures e parametrização.
