# Zeny Project Handler

Cliente Windows e servidor protegido para organizar, visualizar e analisar projetos de expansão da
rede de distribuição elétrica. O servidor mantém cópias gerenciadas dos PDFs, extrai evidências,
interpreta elementos técnicos e executa verificações de conformidade rastreáveis. O cliente magro
apresenta os DTOs e rasters recebidos pela API autenticada.

## Estado atual

- Painel **Projeto** remoto: NS, múltiplos PDFs, ordem de folhas, remoção e exclusão usam
  exclusivamente o gateway HTTP autenticado e a fonte principal do servidor.
- Visualizador remoto progressivo: o cliente Qt apresenta prévias/tiles, paginação, zoom e rotação,
  enquanto o servidor autenticado abre e rasteriza os PDFs. PDFs avulsos usam sessão temporária e
  senha somente em memória.
- Extração de texto, vetores, imagens, anotações, Form XObjects e OCR Tesseract no servidor quando
  necessário.
- Pipeline do projeto executado como job persistente no worker único do servidor, com criação
  idempotente, polling entre 250 e 500 ms, progresso monotônico, cancelamento cooperativo e bloqueio
  global visível a todos os clientes.
- Interpretação versionada de postes, estruturas MT/BT, cabos e equipamentos, além de relações entre
  os elementos. Resultados catalogados são promovidos automaticamente e continuam auditáveis.
- Painel **Resultados** remoto: sessão, catálogo, regiões, vãos, propostas, relações, decisões e
  auditoria chegam como DTOs prontos da API; aceitar, corrigir, rejeitar e criar itens manuais são
  persistidos no servidor com controle de conflito entre revisores.
- Regiões de ocorrência, vãos, rótulos e vínculos são derivados exclusivamente no servidor; o
  cliente conserva navegação e controle independente de visibilidade dos elementos no desenho.
- Painel **Documentação e conformidade** remoto: inspeção de cabeçalho, servidão, carimbos e
  assinaturas, reanálise, histórico, estado desatualizado e regras chegam como DTOs do servidor.
- Motor declarativo de conformidade executado no servidor, com quatro famílias de provedores de
  fatos, snapshots persistidos e callouts normalizados compilados para a camada vetorial do cliente.
  O seed atual é
  `cemig-normas-distribuicao-2025.6`, com 39 regras habilitadas.
- Importação e exportação remotas de projetos `.zphproj` e backup completo `.zphbackup`: o servidor
  valida e processa pacotes em jobs, enquanto o cliente só transmite streams e publica downloads
  conferidos por tamanho e SHA-256.
- Temas claro e escuro, painéis acopláveis e restauração do estado da interface.

As 39 regras são executáveis, mas um achado só é criado para alvos que satisfazem todas as condições
de aplicabilidade declaradas. Por isso o registro usa fatos de guarda para não aplicar uma obrigação
fora do subconjunto que o pipeline consegue caracterizar. Em um alvo aplicável, a ausência de um
fato declarado como requisito pode produzir divergência — por exemplo, quando a própria regra exige
a presença de um campo.

## Obter, abrir e conectar

O artefato oficial do cliente é o ZIP portátil Windows x64 em `dist/client/<versão>`. Ele é
autocontido e não exige Python, Tesseract, banco ou dependências do servidor:

1. extraia o ZIP inteiro;
2. execute `ZenyProjectHandler.exe`;
3. informe a URL e a senha fornecidas pelo administrador;
4. se a conexão cair, use **Conexão > Reconectar** sem reiniciar a interface.

A URL pode ser lembrada. A senha do servidor e as senhas de PDFs permanecem somente em memória e
não são lidas de `.env` nem gravadas nas preferências.

Para executar o cliente a partir do código-fonte, use o setup abaixo.

Requisitos:

- Windows;
- Python 3.11, 3.12 ou 3.13;
- acesso à internet somente na preparação inicial das dependências do cliente.

Na primeira execução:

```powershell
.\setup.bat
```

O setup cria `.venv`, instala somente `requirements-client.lock` e o manifesto independente em
`client/`. Ele não instala SQLAlchemy, Alembic, PyMuPDF, OCR ou o pacote do servidor.

Abra sem console com duplo clique em `ZenyProjectHandler.vbs`. Para diagnóstico pelo terminal:

```powershell
.\ZenyProjectHandler.bat
```

## Fluxo de uso

1. No painel **Projeto**, crie ou abra um projeto usando a NS.
2. Adicione um ou mais PDFs e ajuste a ordem das folhas, se necessário.
3. Clique em **Analisar projeto** e acompanhe o progresso. A operação pode ser cancelada em um ponto
   seguro.
4. Use **Resultados** para inspecionar regiões, elementos, relações e vãos e localizar cada evidência
   no PDF.
5. Em **Documentação e conformidade**, confira os dados documentais, execute a conformidade e revise
   os callouts.
6. Use **Importar, exportar e backup** para transportar um projeto ou proteger o estado persistido
   no servidor. Preflights destrutivos exibem o resumo remoto antes da confirmação.

O pipeline principal executa, em ordem, a extração documental, a interpretação semântica, a
promoção dos resultados e a conformidade. A ação **Analisar conformidade** reaplica as regras aos
resultados semânticos persistidos; ela não abre o PDF nem repete OCR.

## Dados e integridade

Por padrão, preferências visuais, logs do cliente e downloads escolhidos pelo usuário ficam no
computador cliente. Use `ZENY_DATA_DIR` para escolher a raiz local da interface; essa pasta não
contém banco nem cache de análise. Os painéis
**Projeto**, **Resultados**, **Documentação e conformidade** e **Importar, exportar e backup** usam o
servidor como fonte principal; banco, PDFs gerenciados, cache, jobs, pacotes temporários e logs do
servidor ficam em `ZENY_SERVER_DATA_DIR` (normalmente o volume `/data`).

- O SQLite e suas migrações existem somente no servidor.
- PDFs adicionados pelo painel Projeto são enviados por streaming e publicados em cópia gerenciada
  pelo servidor. A origem escolhida no cliente não é alterada nem apagada.
- O aplicativo registra identidade, tamanho e SHA-256 da origem antes de analisar ou transportar o
  conteúdo.
- `.zphproj` transporta um projeto com seus dados auditáveis e arquivos disponíveis. Exportação e
  importação executam no servidor; o cliente nunca abre o ZIP.
- `.zphbackup` protege o banco completo do servidor, arquivos gerenciados e cópias verificadas dos
  PDFs externos. O cliente nunca abre o snapshot SQLite.
- Uploads possuem limite de tamanho, nome saneado e temporário gerenciado; downloads autenticados
  têm TTL, podem ser repetidos enquanto válidos e só substituem o destino local após conferir
  tamanho e SHA-256.
- Pacotes validam manifesto, caminhos, tipos, tamanhos e hashes. Uma origem ausente, alterada ou
  ilegível só pode ser omitida depois de confirmação explícita e deixa o pacote marcado como
  degradado.
- A importação de projeto e a limpeza de arquivos possuem journals recuperáveis. A restauração de
  backup usa publicação atômica por arquivo e compensação para falhas capturadas; a troca conjunta
  de banco e anexos ainda não possui journal durável contra encerramento abrupto.

## OCR no servidor

O pipeline prioriza conteúdo nativo do PDF. O Tesseract é usado pelo servidor como fallback em
páginas ou regiões que precisam de reconhecimento raster; a ausência do OCR não impede os demais
extratores.

O modelo português provisionado vem de `tesseract-ocr/tessdata_fast`, revisão imutável
`65727574dfcd264acbb0c3e07860e4e9e9b22185`, com SHA-256
`c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb`. A licença é Apache-2.0 e os
avisos de terceiros estão em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Essas opções são administradas no host do servidor e não fazem parte do setup ou do artefato do
cliente.

## Configuração

As opções são lidas na inicialização:

| Variável | Padrão | Uso |
|---|---:|---|
| `ZENY_DATA_DIR` | `%LOCALAPPDATA%\ZenyProjectHandler` | raiz dos dados locais |
| `ZENY_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` ou `CRITICAL` |
| `ZENY_PDF_RENDER_DPI` | `600` | teto de detalhe do visualizador, entre 36 e 600 DPI |
| `ZENY_PDF_RENDER_MAX_PIXELS` | `8000000` | limite de pixels por solicitação de renderização |
| `ZENY_PDF_RENDER_MAX_BYTES` | `67108864` | limite estimado de memória por solicitação |
| `ZENY_PDF_TILE_CACHE_MAX_BYTES` | `134217728` | limite do cache visual de tiles |
| `ZENY_CLIENT_SERVER_URL` | `http://127.0.0.1:8000` | URL inicial do diálogo em desenvolvimento |
| `ZENY_SERVER_PASSWORD` | sem padrão | segredo obrigatório, lido somente pelo processo servidor |
| `ZENY_SERVER_VIEWER_SESSION_TTL_SECONDS` | `900` | inatividade até limpar PDF avulso no servidor |
| `ZENY_SERVER_VIEWER_MAX_FILES` | `20` | máximo de PDFs por sessão avulsa |
| `ZENY_SERVER_JOB_RETENTION_SECONDS` | `86400` | retenção renovada do histórico terminal de jobs |
| `ZENY_SERVER_JOB_MAX_RETAINED` | `100` | máximo de jobs terminais mantidos no servidor |
| `ZENY_TESSERACT_PATH` | descoberta automática | caminho do `tesseract.exe` |
| `ZENY_TESSDATA_DIR` | pasta gerenciada | diretório gravável de idiomas do Tesseract |
| `ZENY_BOOTSTRAP_PYTHON` | descoberta automática | Python usado por `setup.bat` |

As opções de renderização afetam somente o visualizador, não os parâmetros ou resultados da análise.
O servidor aplica seus próprios tetos equivalentes (`ZENY_SERVER_RENDER_DPI`,
`ZENY_SERVER_RENDER_MAX_PIXELS` e `ZENY_SERVER_RENDER_MAX_BYTES`). Somente leituras idempotentes dos
gateways são repetidas automaticamente depois de uma falha transitória; criação/alteração, uploads,
senha, cancelamento e encerramento não são. Repetir deliberadamente a criação de um job com a mesma
`Idempotency-Key` devolve o mesmo job sem executar o pipeline novamente.

## Testes e qualidade

Execute o gate padrão:

```powershell
.\IniciarTestes.bat
```

Ele valida dependências, Ruff, formatação, Mypy, a suíte Pytest com cobertura e o limite de
complexidade ciclomática. A cobertura mínima configurada é superior a 85%. O relatório local é
gravado em `relatorio-testes.txt` e ignorado pelo Git.

Comandos individuais:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest --cov
```

Os testes normais usam fixtures sintéticas e não dependem dos PDFs locais de `examples/`. Para um
smoke opcional, somente leitura, sobre todos os exemplos disponíveis:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_examples.py
```

## Limites conhecidos

- O reconhecimento é determinístico e auditável, mas ainda depende da qualidade e das convenções do
  desenho; casos ambíguos continuam sujeitos à revisão humana.
- Cálculos elétricos ou mecânicos completos, autenticidade de assinaturas e validações que dependem
  de documentos restritos não são inferidos sem fonte e evidência suficientes.
- Algumas regras de pacote documental ou topologia permanecem não avaliáveis quando os anexos ou as
  associações necessárias não aparecem no projeto analisado.
- O ZIP portátil ainda não possui assinatura de código nem instalador; a verificação automatizada
  comprova inicialização autocontida no Windows x64 sem usar o Python do host.

## Documentação

- [Especificação funcional](docs/especificacao-funcional.md): comportamento e limites do produto.
- [Modelo de entidades](docs/modelo-entidades.mmd): visão estrutural do domínio.
- [Arquitetura de conformidade](docs/arquitetura-conformidade.md): fluxo de fatos, regras, snapshots e
  callouts.
- [Catálogo de regras](docs/catalogo-regras-conformidade.md): as 39 regras do seed e suas fontes.
- [Inventário normativo](docs/inventario-fontes-normativas.md): documentos, revisões, hashes e escopo
  da auditoria normativa.
- [ADRs](docs/adr): decisões arquiteturais; textos substituídos são mantidos somente quando o status
  os identifica explicitamente como histórico.
- [Exemplos locais](examples/README.md): política da bancada de PDFs não versionados.

O código segue a separação entre domínio, casos de uso, portas, adaptadores e interface Qt. O
detalhamento histórico de implementação permanece no Git; a documentação viva descreve apenas o
comportamento vigente.
