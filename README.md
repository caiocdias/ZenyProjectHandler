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

## Visualização e origem dos PDFs

A janela principal abre PDFs locais em modo somente leitura e oferece paginação, zoom, rotação e
sobreposições gráficas. O arquivo original não é copiado nem regravado: o aplicativo calcula o
SHA-256, registra metadados e verifica o conteúdo antes de renderizar ou concluir uma importação.

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

OCR não é uma dependência do aplicativo. Há um contrato para motores locais opcionais, chamado
somente em páginas sem texto nativo suficiente. Nenhum serviço de rede ou mecanismo OCR é iniciado
automaticamente.

## Interpretação semântica por regras

O registro inicial em `adapters/interpretation/data/regras_interpretacao_v1.json` é versionado,
validado e possui assinatura de conteúdo. Cinco analisadores independentes reconhecem códigos ativos
do catálogo em texto nativo ou OCR. Vetores e imagens próximos são vinculados como contexto para
geometria, cor e proveniência; nada é confirmado automaticamente.

O interpretador gera somente `PropostaElemento` e `PropostaRelacao`. Situação de obra usa as
assinaturas de cor do catálogo; relações usam proximidade de centros, extremidades de cabos e as
compatibilidades estrutura-cabo. Cada proposta mantém evidências, regra, versão, confiança e
justificativa. Uma execução cancelada ou interrompida pode ser retomada com a mesma identidade sem
duplicar resultados.

O mesmo pipeline possui um adaptador para o benchmark. O teste final continua bloqueado enquanto o
conjunto de avaliação não estiver congelado e os critérios não estiverem aprovados.

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
