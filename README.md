# Zeny Project Handler

Aplicativo desktop em Python para representar, revisar e futuramente interpretar projetos de expansão da rede de distribuição elétrica da CEMIG.

## Ambiente de desenvolvimento

Requisitos:

- Python 3.11 ou 3.12;
- Windows para a aplicação desktop.

O `setup.bat` procura primeiro o Python Launcher (`py`) e depois o comando `python`. Quando o executável não estiver no `PATH`, defina `ZENY_BOOTSTRAP_PYTHON` com seu caminho completo antes de executar o setup.

## Preparação e execução no Windows

Execute uma vez:

```powershell
.\setup.bat
```

O script cria `.venv`, instala todas as versões fixadas em `requirements.lock` e instala o aplicativo no ambiente virtual.

Para abrir o aplicativo sem uma janela de console, dê dois cliques em `ZenyProjectHandler.vbs` ou
execute:

```powershell
.\ZenyProjectHandler.vbs
```

O inicializador usa diretamente `.venv\Scripts\pythonw.exe`, portanto não depende de compilação ou
empacotamento em EXE. Erros de ambiente e de inicialização são apresentados em uma caixa de diálogo.
Para diagnóstico pelo terminal, `ZenyProjectHandler.bat` continua disponível e preserva a saída do
Python enquanto o aplicativo estiver aberto.

Para executar todos os gates de qualidade:

```powershell
.\IniciarTestes.bat
```

O resultado completo é salvo em `relatorio-testes.txt` na raiz. O comando falha se lint, formatação, tipagem, dependências, testes ou cobertura falharem. A cobertura deve permanecer estritamente acima de 85%. O relatório também apresenta complexidade ciclomática, índice de manutenibilidade e métricas de linhas de código.

## Preparação manual

Crie um ambiente virtual e instale as dependências de desenvolvimento:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

Execute a aplicação:

```powershell
.\.venv\Scripts\python.exe -m zeny_project_handler
```

Valide o projeto:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest --cov
```

As decisões arquiteturais estão em [`docs/adr`](docs/adr) e a sequência de implementação está em [`docs/roadmap-desenvolvimento.md`](docs/roadmap-desenvolvimento.md).

## Dados locais e backup

Ao iniciar, o aplicativo cria e migra automaticamente
`%LOCALAPPDATA%\ZenyProjectHandler\zeny-project-handler.sqlite3`. A variável `ZENY_DATA_DIR` permite
usar outra pasta, inclusive em testes. O banco utiliza chaves estrangeiras, transações explícitas e
versionamento Alembic.

Backups são snapshots consistentes do SQLite, validados antes de substituir atomicamente o arquivo
de destino. A pasta padrão reservada para eles é `backups` dentro do diretório de dados. Arquivos do
banco, WAL, temporários e backups não devem ser adicionados ao Git.

## Transporte e recuperação

O painel **Portabilidade e recuperação** contém somente as operações de transporte e proteção dos
dados. Um projeto pode ser exportado como `.zphproj`, com manifesto assinado, banco restrito ao
projeto, PDFs disponíveis e resultados da análise. O pacote usa somente caminhos relativos e valida
internamente SHA-256, tamanho e tipo de cada arquivo ao ser importado. A importação preserva
identidades, catálogo, análises e decisões; substituir um projeto existente exige confirmação
explícita.

O backup completo `.zphbackup` inclui o banco local, arquivos gerenciados e cópias dos PDFs externos.
Sua publicação e restauração usam trocas atômicas e validação do SQLite. Assim, uma gravação
interrompida não substitui o último backup íntegro, e os PDFs recuperados deixam de depender do local
original. Gestão de fotos e relatório de integridade não fazem parte da interface.

## Visualização e origem dos PDFs

A janela principal mantém o leitor de PDF no centro. Fluxo, resultados da análise e portabilidade
continuam dockáveis; resultados e portabilidade compartilham abas à direita para não se
sobreporem. O leitor oferece
paginação, zoom, rotação e sobreposições gráficas.

Todo PDF selecionado no **Fluxo do projeto** é adicionado imediatamente ao projeto. Na lista de
folhas, arraste qualquer página ou use **Subir** e **Descer** para definir a ordem persistida de
leitura, inclusive intercalando páginas de PDFs diferentes. O arquivo original não é copiado nem
regravado: a ordem pertence ao projeto, enquanto o aplicativo calcula o SHA-256, registra metadados
e verifica o conteúdo antes de renderizar ou concluir uma importação.

Cada elemento identificado aparece no PDF como um sublinhado colorido e clicável. O clique abre a
aba **Resultados da análise** e seleciona o elemento correspondente. A visão principal é hierárquica:
cada região da folha reúne coordenada, acontecimentos, estruturas, equipamentos, postes, cabos e
vínculos próximos. Uma mesma região pode descrever simultaneamente retiradas, instalações e
elementos existentes, mesmo quando não há poste catalogado ou coordenada. Não há confirmação item a
item; resultados catalogados são incorporados automaticamente ao projeto e ficam imediatamente
disponíveis para as etapas seguintes.

A resolução padrão é 144 DPI. Ela pode ser alterada entre 36 e 600 DPI antes da inicialização:

```powershell
$env:ZENY_PDF_RENDER_DPI = "200"
.\ZenyProjectHandler.vbs
```

O inventário técnico distingue texto, caminhos vetoriais, imagens incorporadas, anotações e seus
appearance streams, Form XObjects e Optional Content Groups. Uma falha localizada vira diagnóstico
da página e não invalida os demais recursos que ainda podem ser lidos ou renderizados.

O analisador nativo converte esses recursos em `EvidenciaDocumento` com geometria normalizada e
proveniência PDF. Texto preserva fonte, tamanho e rotação; vetores preservam comandos e cores; o
percurso de anotações e Form XObjects inclui imagens em appearance streams. A análise pode ser
recriada pelo hash do PDF e usa um cache JSON descartável em `cache/analysis` dentro da pasta de
dados.

Quando o Tesseract está instalado, o aplicativo o descobre no `PATH`, no local padrão do Windows ou
no caminho indicado por `ZENY_TESSERACT_PATH`. O OCR é executado localmente, sem serviço de rede, em
páginas com pouco texto nativo, área raster relevante ou grande densidade vetorial — caso típico de
letras e números plotados como caminhos pelo AutoCAD. Em páginas com texto nativo suficiente,
pequenas imagens com resolução útil são processadas por recorte, preservando a geometria correta na
folha sem renderizar a página inteira. Sem Tesseract, os demais extratores continuam funcionando e
a execução registra um diagnóstico revisável.

## Documentação e conformidade

O dock **Documentação e conformidade** acompanha o projeto aberto e possui visões próprias para:

- todos os pares `rótulo: informação` encontrados no cabeçalho e no quadro de servidão, além de
  candidatos a carimbo e indícios/campos de assinatura;
- regras conformes, possíveis divergências e casos não avaliáveis, sempre com fonte normativa.

O detector anterior de vãos e ângulos foi removido e não há substituto ativo nesta revisão. O
scanner documental não considera um carimbo ou rótulo de assinatura como prova de autenticidade.
Cada informação vira um fato com origem, confiança, geometria e evidências. Regras ficam em um
registro JSON versionado com condições de aplicabilidade, exceções comprovadas e requisitos. A
arquitetura e os limites estão detalhados em
[`docs/arquitetura-conformidade.md`](docs/arquitetura-conformidade.md).

O Unlimited-OCR foi avaliado como possível segunda passagem local para layouts difíceis. A
integração recomendada, caso o benchmark justifique, é diretamente por `MotorOcrPort` contra um
servidor local vLLM/SGLang. LM Studio + MCP não entra no pipeline determinístico nesta etapa; veja a
[`ADR 0012`](docs/adr/0012-ocr-local-por-porta-direta.md).

## Interpretação semântica por regras

O registro inicial em `adapters/interpretation/data/regras_interpretacao_v1.json` é versionado,
validado e possui assinatura de conteúdo. Cinco analisadores independentes reconhecem códigos ativos
do catálogo em texto nativo ou OCR. Postes também são reconhecidos pela nomenclatura de projeto
`altura-resistência`, por exemplo `11-300`. Também são aceitos `/`, `:`, `x`, espaços e quebra de
linha; na ausência de Circular, Duplo T ou Madeira, uma correspondência canônica do catálogo é usada
e os demais candidatos permanecem registrados na auditoria. Pares de coordenadas de campo próximos
ao poste são reconhecidos em texto nativo ou OCR, inclusive quando estão em linhas ou fragmentos
separados. Leste e norte são pareados uma única vez por fragmento e proximidade, evitando reutilizar
o mesmo número em pontos vizinhos. Vetores e imagens próximos são vinculados como contexto para
geometria, cor e proveniência.

Linhas reconhecidas como cabeçalho, como `Dispositivo:`, `Circuito:` e `Projeto:`, continuam
disponíveis para a inspeção documental, mas não entram no inventário da rede. Nomenclaturas de cabo
coerentes que ainda não possuem item exato no catálogo, como `ABCN-4(4)`, são preservadas como
propostas conflitantes para classificação humana, incluindo a situação instalar/remover derivada da
simbologia.

O interpretador preserva `PropostaElemento` e `PropostaRelacao` como trilha auditável e promove
automaticamente os resultados catalogados ao agregado do projeto. Situação de obra usa as
assinaturas de cor do catálogo; estruturas e equipamentos preferem postes com a mesma situação
(instalar, remover ou existente), antes da distância. Cada resultado mantém evidências, regra,
versão, confiança e justificativa. Uma execução cancelada ou interrompida pode ser retomada com a
mesma identidade sem duplicar resultados nem entidades promovidas.

O mesmo pipeline possui um adaptador para o benchmark. O teste final continua bloqueado enquanto o
conjunto de avaliação não estiver congelado e os critérios não estiverem aprovados.

## Regiões de ocorrência no PDF

Depois da interpretação, os elementos são agrupados por proximidade na mesma folha. Cada região é
uma visão derivada e determinística da análise: ela informa o PDF, a página, eventual par de
coordenadas UTM, tudo o que será instalado ou removido e o que já existe no local. Os vínculos
semânticos permanecem visíveis dentro da região, mas não são transformados em nós ou arestas. O
painel consolida a análise mais recente de cada PDF do projeto e segue a ordem de leitura das páginas.

Coordenadas são coletadas de texto nativo e OCR, inclusive quando leste e norte aparecem separados
por quebra de linha, `:`, `/` ou em fragmentos próximos. Selecionar a região destaca sua extensão;
selecionar um elemento abre a folha correspondente e destaca seu sublinhado clicável. Ícones de olho
permitem ocultar temporariamente no PDF uma região inteira ou somente elementos individuais, sem
apagar o resultado auditável.

## Projetos reais para testes

PDFs reais podem ser colocados em `examples/`, mas são ignorados pelo Git porque podem conter dados
pessoais, coordenadas e fotografias. O repositório mantém somente
`evaluation/manifesto-amostras.json`, com IDs anônimos, hashes, partições e características
técnicas. Consulte `examples/README.md` e `evaluation/POLITICA-ACESSO.md` antes de adicionar ou
substituir uma amostra.

O conjunto de avaliação separa desenvolvimento de teste final e possui formatos JSON explícitos
para manifesto, critérios e anotações. O benchmark compara elementos e relações por geometria
normalizada, calcula precisão e recall por classe, falhas de extração, latência p95 e pico de memória
Python, e gera uma assinatura semântica que ignora variações de tempo de execução. O corpus atual
ainda está em preparação: falta diversidade de escala, revisão humana e aprovação dos limites antes
do congelamento.

O `requirements.lock` foi gerado no Windows com Python 3.12 e deve ser validado também no Python 3.11 antes da primeira distribuição.
