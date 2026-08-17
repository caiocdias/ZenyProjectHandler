# ADR 0013 — Arquitetura cliente-servidor com fonte principal no container

- Estado: aceita
- Data: 2026-08-17
- Escopo de vigência: arquitetura-alvo da migração descrita em
  `docs/roadmap-arquitetura-cliente-servidor.md`
- Relações: preserva as garantias dos ADRs 0001–0012; substitui, na nova fronteira HTTP, a
  referência a PDFs externos por caminho local descrita no ADR 0003 e a noção de ambiente local do
  ADR 0008. O monólito continua com o comportamento vigente até as etapas que migrarem cada fluxo.

## Contexto

O Zeny Project Handler é hoje uma aplicação Qt monolítica. O mesmo processo compõe a interface,
SQLite e Alembic, catálogos e regras, leitura e renderização PyMuPDF, OCR Tesseract, casos de uso,
portabilidade, recuperação e coordenação de operações. A interface recebe entidades e portas
internas e, em alguns fluxos, calcula projeções que contêm decisões de negócio.

O produto precisa ser distribuído em dois artefatos independentes: um cliente Windows magro para
usuários e um servidor em container administrado separadamente. A separação deve proteger a lógica
interna do cliente distribuído sem reduzir funcionalidade, integridade, proveniência, auditabilidade
ou capacidade de recuperação.

Uma separação apenas por processo não resolve o problema. Se o cliente ainda contiver domínio,
casos de uso, seeds, adaptadores, PyMuPDF, Tesseract, SQLAlchemy ou manipulação de pacotes, a lógica
continuará distribuída. Também não é válido transmitir caminhos de arquivos do Windows e esperar que
o container consiga abri-los: isso criaria uma fronteira dependente de filesystem compartilhado,
permissões e topologia de rede.

## Decisão

### 1. Topologia e artefatos

Adotaremos dois artefatos físicos e independentes:

1. um cliente Windows autocontido, responsável pela interface Qt, interação com arquivos locais,
   apresentação e comunicação HTTP;
2. um servidor executado em container Docker, responsável pelo domínio, casos de uso, regras,
   persistência, análise, OCR, renderização, arquivos gerenciados, portabilidade, recuperação e
   operações longas.

O pacote do cliente não dependerá do pacote de runtime do servidor. O container será construído sem
componentes Qt ou fontes do cliente. A independência será validada sobre os artefatos de release, não
apenas por inspeção do repositório de desenvolvimento.

### 2. Fronteira do cliente

Pode permanecer no cliente:

- widgets, diálogos, tema, ícone, atalhos, docks e geometria da janela;
- seleção de arquivos para upload e escolha de destinos de download;
- gateway HTTP, serialização, DTOs de transporte sem comportamento de negócio e apresentação de
  erros seguros;
- cálculo do viewport, composição de `QImage`/`QPixmap`, desenho de overlays já calculados e cache
  LRU descartável de raster;
- `ui-state.ini`, URL do servidor e preferências não sensíveis;
- senha do servidor e senhas de PDF somente em memória durante a sessão.

Não pode integrar o artefato do cliente:

- `domain`, casos de uso de `application`, portas de negócio ou adaptadores do servidor;
- SQLAlchemy, Alembic, SQLite de negócio, PyMuPDF ou Tesseract;
- seeds JSON de catálogo, interpretação ou conformidade;
- avaliação de regras, interpretação, detecção de regiões ou vãos e compilação de callouts;
- abertura, hashing, validação ou renderização de PDF como regra da aplicação;
- manipulação de ZIP, backup, recuperação ou arquivos gerenciados.

### 3. Fronteira do servidor e contratos

O servidor executará toda regra de negócio e responderá DTOs próprios da API sob `/api/v1`. Entidades
SQLAlchemy, agregados de domínio, objetos PyMuPDF, caminhos físicos e tracebacks não atravessarão a
fronteira. A especificação OpenAPI da API v1 estabilizará nomes e schemas na Etapa 1.

Uploads e downloads serão streams. Operações mutáveis sujeitas a repetição por falha de rede usarão
chaves de idempotência; o cliente não fará retry automático de mutações. Erros usarão envelope
estável com `code`, `message`, `correlation_id` e `details` seguro opcional. Conflitos de operação ou
estado obsoleto serão representados por HTTP 409.

### 4. Autenticação e segredo

O servidor exigirá um segredo definido exclusivamente pela variável de ambiente
`ZENY_SERVER_PASSWORD`:

- Docker Compose lerá `.env` e injetará o segredo no container em runtime;
- `.env` permanecerá ignorado pelo Git e será excluído do contexto/imagem Docker;
- `.env-example` conterá somente placeholder e orientação, nunca um segredo real;
- não serão usados `ARG`, `ENV` com valor real nem `COPY .env` no `Dockerfile`;
- senha ausente, vazia ou igual ao placeholder impedirá a inicialização;
- rotas protegidas exigirão `Authorization: Bearer <senha>`;
- a comparação será feita em tempo constante com `hmac.compare_digest`;
- senha ausente ou incorreta produzirá a mesma resposta 401 genérica, com
  `WWW-Authenticate: Bearer`;
- `GET /health/live` poderá ser público, mas informará apenas que o processo está vivo;
- senha do servidor, header `Authorization` e senhas de PDF não serão persistidos nem registrados.

O cliente poderá lembrar a URL, mas nunca a senha. A senha será solicitada no diálogo de conexão e
mantida somente em memória.

### 5. Armazenamento gerenciado e uploads

O servidor será o único proprietário dos dados da aplicação. SQLite, PDFs, fotos, cache, temporários,
journals e logs ficarão em um volume persistente montado em `/data`.

Todo upload novo será copiado por streaming para uma área temporária controlada pelo servidor,
validado e publicado atomicamente em armazenamento gerenciado. O servidor escolherá o caminho físico
e persistirá a identidade verificável do conteúdo. O request poderá conter nome de exibição e bytes,
mas nunca um caminho local absoluto ou destino arbitrário no servidor.

Uma referência a caminho externo do Windows não atravessará a nova fronteira. O container não abrirá
um caminho recebido em JSON, não dependerá de compartilhamento SMB e não montará a árvore local do
cliente como fonte permanente. Depois de aceito, o conteúdo gerenciado continuará disponível mesmo
que a cópia original do cliente seja movida ou apagada.

### 6. Worker único, jobs e coordenação

Enquanto o coordenador global, tokens de cancelamento e credenciais efêmeras permanecerem em memória,
o servidor executará com um único processo worker. Vários workers sem um mecanismo distribuído
permitiriam operações incompatíveis simultâneas e estados divergentes de progresso ou credenciais.

Operações longas serão expostas como jobs com, no mínimo, os estados `QUEUED`, `RUNNING`,
`WAITING_CONFIRMATION`, `CANCELLING`, `SUCCEEDED`, `FAILED` e `CANCELLED`. A criação retornará HTTP
202, o progresso será monotônico e o cancelamento será cooperativo em fronteiras seguras. O cliente
observará jobs por polling limitado, inicialmente entre 250 e 500 ms, até que outra estratégia seja
decidida.

Reinício do processo não poderá fabricar sucesso. Journals e comprovantes persistidos continuarão
determinando reconciliação, e cada etapa posterior documentará quais jobs podem ser retomados ou
devem terminar em estado recuperável após restart.

### 7. Fonte principal e lifecycle

O container será a fonte principal e única fonte de verdade para dados de negócio. Isso implica:

- clientes diferentes observam o mesmo estado e o mesmo coordenador;
- nenhum cliente mantém SQLite de negócio ou cópia autoritativa de projeto;
- backup, importação, restauração, migrações e recuperação acontecem no servidor;
- o volume `/data` precisa sobreviver a restart e recreate do container;
- o servidor deve ficar indisponível para negócio quando migração, integridade ou recuperação estiver
  em estado ambíguo;
- indisponibilidade do servidor impede operações de negócio no cliente, embora preferências visuais
  locais e downloads já concluídos permaneçam acessíveis.

### 8. Rede e limite de confiança

A autenticação Bearer simples foi escolhida para uma LAN confiável. Em HTTP puro, qualquer agente com
acesso ao tráfego pode observar a senha. A porta não deve ser exposta à internet nem a uma rede não
confiável. Se esse limite mudar, TLS por proxy reverso ou VPN passa a ser requisito antes da
exposição.

A imagem Docker dificulta o acesso à lógica pelo usuário comum da API, mas não protege contra um
administrador do host Docker ou alguém com acesso à própria imagem. Essa é uma limitação explícita do
modelo de distribuição, não uma garantia de sigilo contra o operador da infraestrutura.

### 9. Migração incremental

Esta decisão define o alvo, mas não muda o runtime na Etapa 0. Cada fluxo só atravessará HTTP quando
sua etapa implementar contrato, servidor, cliente e testes de paridade. Durante a transição, o
monólito continuará sendo a linha de base funcional; adaptadores temporários não autorizam reduzir
testes ou manter lógica protegida no artefato final do cliente.

## Consequências

### Positivas

- A lógica, os seeds e as dependências pesadas ficam centralizados e deixam de ser distribuídos ao
  usuário do cliente.
- PDFs e anexos tornam-se gerenciados e independentes de caminhos ou disponibilidade da máquina do
  cliente.
- Estado, regras, coordenação e auditoria passam a ter uma fonte única para múltiplos clientes.
- A fronteira HTTP cria contratos verificáveis, versionáveis e testáveis por OpenAPI.
- Cliente e servidor podem ter ciclos de empacotamento distintos, com compatibilidade explícita de
  versão da API.

### Negativas e custos

- A aplicação passa a depender de disponibilidade e latência de rede para qualquer operação de
  negócio.
- Uploads, raster remoto e downloads aumentam tráfego, armazenamento e necessidade de limpeza de
  temporários.
- Um único worker limita paralelismo até que coordenação, credenciais e jobs sejam externalizados de
  forma segura.
- Deploy, volume, migrações, backup e observabilidade do servidor tornam-se responsabilidades
  operacionais explícitas.
- A migração exige DTOs de apresentação; apenas envolver os serviços atuais em endpoints não é
  suficiente.

## Riscos e mitigações

| Risco | Mitigação decidida |
|---|---|
| senha observável em HTTP | restringir à LAN confiável; exigir TLS/VPN antes de ampliar o limite |
| segredo entrar no Git ou na imagem | runtime env, `.env` ignorado e fora do contexto, inspeção de artefato |
| upload parcial, hostil ou repetido | streaming limitado, temporário seguro, hash, nome saneado, publicação atômica e idempotência |
| caminho do cliente vazar ou ser aberto no servidor | contratos sem `Path`; bytes + nome de exibição; caminho sempre escolhido pelo servidor |
| dois clientes iniciarem operações incompatíveis | coordenador único, HTTP 409 e um worker enquanto o estado for local ao processo |
| restart deixar falso sucesso ou estado parcial | jobs sem sucesso presumido, journals/comprovantes e reconciliação fail-closed |
| DTO expor lógica ou detalhes internos | modelos próprios de transporte e gates de imports/artefatos |
| cliente incompatível com servidor | negociação de versão/faixa da API antes de carregar dados |
| perda do volume `/data` | documentação operacional, backup, restore, migrações e testes de lifecycle |
| acesso administrativo à imagem | limitação documentada; distribuição restrita ao administrador do servidor |

## Alternativas rejeitadas

### Manter o monólito como artefato distribuído

Rejeitada porque continuaria entregando lógica, seeds, adaptadores e dependências do servidor a cada
usuário e não estabeleceria uma fonte única para múltiplos clientes.

### Colocar somente os serviços atuais atrás de HTTP

Rejeitada porque a UI ainda recebe tipos internos e executa derivação, validação e renderização. A
separação exige DTOs próprios e remoção de decisões de negócio do cliente.

### Enviar caminhos do Windows ou montar uma pasta compartilhada

Rejeitada por acoplar o contrato a filesystem, permissões, letras de unidade, SMB e topologia da LAN.
Também impediria provar que o servidor possui o conteúdo depois que a origem local é removida.

### Manter PyMuPDF, OCR, regras ou portabilidade também no cliente

Rejeitada por duplicar fontes de verdade e distribuir justamente a lógica e as dependências que a
arquitetura deve centralizar.

### Executar vários workers desde o início

Rejeitada enquanto coordenação, cancelamento e credenciais forem locais ao processo. Aumentar workers
sem estado distribuído quebraria exclusão mútua e observabilidade dos jobs.

### Persistir a senha no cliente ou incorporá-la à imagem

Rejeitada porque criaria segredo recuperável no artefato, configuração local, histórico de build ou
camadas da imagem. A senha será digitada e mantida em memória no cliente e injetada em runtime no
servidor.

### Expor HTTP sem autenticação ou tratar HTTP puro como rede segura por si só

Rejeitada. Bearer é obrigatório, e HTTP puro só é aceitável dentro do limite declarado de LAN
confiável; ele não fornece confidencialidade.
