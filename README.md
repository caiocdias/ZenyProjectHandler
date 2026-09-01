# Zeny Project Handler

Cliente Windows e servidor protegido para organizar, visualizar e analisar projetos de expansão da
rede de distribuição elétrica. O servidor mantém cópias gerenciadas dos PDFs, extrai evidências,
interpreta elementos técnicos e executa verificações de conformidade rastreáveis. O cliente magro
apresenta os DTOs e rasters recebidos pela API autenticada.

## Estado atual

- Painel **Projeto** remoto: NS, coleção canônica de códigos de serviço com quatro dígitos, múltiplos
  PDFs, ordem de folhas, remoção e exclusão usam exclusivamente o gateway HTTP autenticado e a fonte
  principal do servidor. A caixa **Serviços do projeto** fica entre **Projeto** e **Folhas PDF** e
  preserva zeros à esquerda.
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
- Painel **GMAX** somente leitura: acompanha o projeto ativo e apresenta mercado, NS identificadas
  nos cabeçalhos e os checks fixos de impacto ambiental e servidão, distinguindo consulta não
  executada, sem linha, com linha, resultado desatualizado e bloqueio por divergência da NS.
- Motor declarativo de conformidade executado no servidor, com quatro famílias de provedores de
  fatos, snapshots persistidos e callouts normalizados compilados para a camada vetorial do cliente.
  O seed atual é `cemig-normas-distribuicao-2025.7`, com 41 regras habilitadas, e o método de
  conformidade está na versão `10`. O mercado rural/urbano e a conclusão das ações operacionais
  aplicáveis vêm exclusivamente do SQL Server.
- Painel **Exportar**: o servidor compila o PDF na ordem das folhas, incorpora as anotações de
  conformidade e gera planilhas Excel de **Resultados** (Elementos e Vãos), **Documentação** e
  **Conformidade** (Conformidade e Regras). O cliente apenas escolhe o destino e confere tamanho e
  SHA-256 antes de publicar o download local.
- Lifecycle fail-closed do volume: manifesto de formato versionado, verificação SQLite pré/pós,
  Alembic somente quando necessário e rejeição de revisão futura, corrupção ou falta de escrita
  antes da prontidão.
- Temas claro e escuro, painéis acopláveis e restauração do estado da interface.

As 41 regras são executáveis, mas um achado só é criado para alvos que satisfazem todas as condições
de aplicabilidade declaradas. Por isso o registro usa fatos de guarda para não aplicar uma obrigação
fora do subconjunto que o pipeline consegue caracterizar. Em um alvo aplicável, a ausência de um
fato declarado como requisito pode produzir divergência — por exemplo, quando a própria regra exige
a presença de um campo.

## Obter, abrir e conectar

A release oficial fica em `dist/release/<versão>/` e separa fisicamente o que cada público recebe.
O usuário final recebe somente `client/` (mais os arquivos comuns de integridade, quando
necessário); o administrador recebe somente `server/` e os mesmos arquivos comuns. O ZIP portátil
Windows x64 é autocontido e não exige Python, Tesseract, banco ou dependências do servidor:

1. extraia o ZIP inteiro;
2. execute `ZenyProjectHandler.exe`;
3. informe a URL e a senha fornecidas pelo administrador;
4. se a conexão cair, use **Conexão > Reconectar** sem reiniciar a interface.

A URL pode ser lembrada. A senha do servidor e as senhas de PDFs permanecem somente em memória e
não são lidas de `.env` nem gravadas nas preferências.

Para trabalhar no projeto a partir do código-fonte, prepare o ambiente de desenvolvimento abaixo.

Requisitos:

- Windows;
- Python 3.11, 3.12 ou 3.13;
- Docker Desktop com Docker Compose;
- acesso à internet somente na preparação inicial das dependências de desenvolvimento.

Na primeira execução:

```powershell
.\setup.bat
```

O setup valida Docker e Docker Compose, cria `.venv`, instala `requirements-development.lock` (que
agrega os runtimes fixados de cliente e servidor e as ferramentas de qualidade) e registra o projeto
completo em modo editável.

Para iniciar o ambiente integrado de desenvolvimento:

```powershell
.\ZenyProjectHandler.bat
```

O único lançador local é `ZenyProjectHandler.bat`; não há lançador `.vbs`. Ele constrói e sobe o
servidor em Docker somente em `127.0.0.1`, espera a API ficar pronta e então abre o cliente com a
conexão e a senha de desenvolvimento já preenchidas. A credencial fica definida exclusivamente no
`.bat`, que gera um valor aleatório novo para cada sessão: o Compose apenas a recebe em runtime e o
lançador e seu pequeno adaptador de interface não integram os artefatos de release.

O SQL Server de mercado também é obrigatório no ambiente local integrado. Crie o `.env` ignorado a
partir de `.env-example` e substitua somente os placeholders; o Compose lê a conexão para o
container. O lançador não imprime nem copia seu valor, e o adaptador que abre o cliente remove a
conexão e o timeout do ambiente do processo Qt.

Essa execução é deliberadamente efêmera. O servidor monta `/data` em `tmpfs`, o cliente usa uma pasta
exclusiva da sessão sob `%TEMP%` e o encerramento executa `docker compose down --volumes`. Fechar o
cliente encerra o servidor; pressionar `Ctrl+C` ou fechar o terminal também interrompe o Compose
anexado. Projetos, alterações, uploads e preferências dessa sessão são descartados e não reaparecem
na próxima execução local. O `compose.yaml` operacional continua separado e persistente.

## Fluxo de uso

1. No painel **Projeto**, crie ou abra um projeto usando a NS.
2. Em **Serviços do projeto**, cadastre os códigos aplicáveis com exatamente quatro dígitos; por
   exemplo, `0007` permanece texto e conserva o zero inicial.
3. Adicione um ou mais PDFs e ajuste a ordem das folhas, se necessário.
4. Clique em **Analisar projeto** e acompanhe o progresso. A operação pode ser cancelada em um ponto
   seguro.
5. Use **Resultados** para inspecionar regiões, elementos, relações e vãos e localizar cada evidência
   no PDF.
6. Em **Documentação e conformidade**, confira os dados documentais, execute a conformidade e revise
   os callouts.
7. Em **GMAX**, confira o mercado, a NS dos cabeçalhos e se cada `SELECT` aplicável foi executado e
   encontrou linha. A aba apenas lê o último resumo persistido e não inicia uma análise.
8. Use **Exportar** para baixar o PDF anotado ou as planilhas `.xlsx` na própria máquina.

O seletor de projetos pesquisa até dez dígitos da NS e resolve uma NS completa diretamente no
servidor, inclusive fora da primeira página carregada. **Criar** uma NS existente oferece abrir o
projeto encontrado; **Abrir** uma NS inexistente oferece criá-la. Recusar qualquer proposta volta ao
estado inicial sem mutação remota. Se outro cliente vencer a corrida de criação, o conflito do
servidor segue o mesmo fluxo e não repete o `POST`.

O pipeline principal executa, em ordem, a extração documental, a interpretação semântica, a
promoção dos resultados e a conformidade. A ação **Analisar conformidade** reaplica as regras aos
resultados semânticos persistidos; ela não abre o PDF nem repete OCR. Cada uma dessas execuções
consulta uma vez o mercado da NS vigente no SQL Server, sem cache ou fallback por metadado/PDF.
Quando o PDF contém `Impacto Ambiental: Sim` no cabeçalho ou uma menção positiva a servidão, a
execução também consulta no máximo uma vez a ação correspondente com a NS e a coleção de serviços
vigentes. Assim, depois que o mercado, a NS, os serviços ou as ações externas mudarem, execute
**Analisar conformidade** novamente para produzir um snapshot coerente com as entradas atuais.

Antes da primeira consulta SQL, todas as NS válidas dos cabeçalhos PDF são comparadas com a NS do
projeto. Qualquer divergência encerra a conformidade como erro de validação, sem consultar mercado
ou ações e sem publicar snapshot parcial. O GMAX apresenta o bloqueio e não reutiliza mercado ou
resultado de linha anterior como se fossem atuais.

## Dados e integridade

Por padrão, preferências visuais, logs do cliente e downloads escolhidos pelo usuário ficam no
computador cliente. Use `ZENY_DATA_DIR` para escolher a raiz local da interface; essa pasta não
contém banco nem cache de análise. Os painéis
**Projeto**, **Resultados**, **Documentação e conformidade**, **GMAX** e **Exportar** usam o servidor
como fonte principal; banco, PDFs gerenciados, cache, jobs, arquivos temporários e logs do servidor
ficam em `ZENY_SERVER_DATA_DIR` (normalmente o volume `/data`).

- O SQLite e suas migrações existem somente no servidor.
- A mesma conexão SQL Server e o mesmo timeout atendem mercado e ações no processo servidor: não
  entram no SQLite, PDFs, volume `/data`, backup, API ou pacote cliente.
- PDFs adicionados pelo painel Projeto são enviados por streaming e publicados em cópia gerenciada
  pelo servidor. A origem escolhida no cliente não é alterada nem apagada.
- O aplicativo registra identidade, tamanho e SHA-256 da origem antes de analisar ou compilar o
  conteúdo.
- O PDF exportado preserva as páginas originais, a ordem definida no projeto e as anotações já
  existentes, além de receber os callouts de conformidade disponíveis.
- As planilhas `.xlsx` são geradas no servidor a partir das mesmas projeções canônicas exibidas nos
  painéis, sem banco, caminhos internos ou arquivos de projeto no computador cliente.
- Backup, restauração e retenção do volume são responsabilidades administrativas do servidor e não
  aparecem como ações do usuário final.
- Uploads possuem limite de tamanho, nome saneado e temporário gerenciado; downloads autenticados
  têm TTL, podem ser repetidos enquanto válidos e só substituem o destino local após conferir
  tamanho e SHA-256.
- `/data/.zeny-volume.json` registra somente formato/revisão/instantes do lifecycle, nunca segredo.
  `docker compose down` preserva dados; `down -v` não pertence ao procedimento operacional.

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
| `ZENY_SERVER_PASSWORD` | sem padrão | segredo obrigatório do servidor; no fluxo local, o `.bat` o repassa em memória para preencher o cliente |
| `ZENY_MARKET_SQLSERVER_CONNECTION_STRING` | sem padrão | string ODBC completa e secreta dos cadastros de mercado e ações; obrigatória somente no servidor |
| `ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS` | `15` | timeout inteiro positivo de conexão e consultas de mercado/ações |
| `ZENY_SERVER_HOST` | `0.0.0.0` | socket do processo servidor; o lançador de desenvolvimento força `127.0.0.1` |
| `ZENY_SERVER_BIND_ADDRESS` | `127.0.0.1` | endereço do host que publica a porta; use IPv4 privado específico para LAN |
| `ZENY_SERVER_VIEWER_SESSION_TTL_SECONDS` | `900` | inatividade até limpar PDF avulso no servidor |
| `ZENY_SERVER_VIEWER_MAX_FILES` | `20` | máximo de PDFs por sessão avulsa |
| `ZENY_SERVER_JOB_RETENTION_SECONDS` | `86400` | retenção renovada do histórico terminal de jobs |
| `ZENY_SERVER_JOB_MAX_RETAINED` | `100` | máximo de jobs terminais mantidos no servidor |
| `ZENY_SERVER_TMPFS_SIZE` | `268435456` | limite em bytes do `/tmp` efêmero do container |
| `ZENY_SERVER_PIDS_LIMIT` | `256` | limite de processos/threads imposto pelo Compose |
| `ZENY_SERVER_MEMORY_LIMIT` | `2g` | limite de memória do container |
| `ZENY_TESSERACT_PATH` | descoberta automática | caminho do `tesseract.exe` |
| `ZENY_TESSDATA_DIR` | pasta gerenciada | diretório gravável de idiomas do Tesseract |
| `ZENY_BOOTSTRAP_PYTHON` | descoberta automática | Python usado por `setup.bat` |

As opções de renderização afetam somente o visualizador, não os parâmetros ou resultados da análise.
O servidor aplica seus próprios tetos equivalentes (`ZENY_SERVER_RENDER_DPI`,
`ZENY_SERVER_RENDER_MAX_PIXELS` e `ZENY_SERVER_RENDER_MAX_BYTES`). Somente leituras idempotentes dos
gateways são repetidas automaticamente depois de uma falha transitória; criação/alteração, uploads,
senha, cancelamento e encerramento não são. Repetir deliberadamente a criação de um job com a mesma
`Idempotency-Key` devolve o mesmo job sem executar o pipeline novamente.

Para a dependência operacional, use uma string ODBC com Microsoft ODBC Driver 18, `Encrypt=yes` e
`TrustServerCertificate=no`, confiando a CA correta no container. O login deve ter apenas conexão
ao banco e `SELECT` nas colunas necessárias: `NOTAS_NUM_NS`/`NOTAS_COD_MERCADO` de `TB_NOTAS` e
`NOTAS_NUM_NS`, `TSERVICOS_CT_COD`, `TACOES_DES` e `ACOES_DAT_CONCLUSAO` de `vBIAcoes`; não conceda
escrita, DDL ou acesso às tabelas-base da view. A classificação executa, com parâmetro vinculado,
`SELECT NOTAS_COD_MERCADO FROM TB_NOTAS WHERE NOTAS_NUM_NS = ?;`. Para cada gatilho aplicável, a
verificação existencial usa NS, cada serviço e a descrição fechada da ação como parâmetros e monta
dinamicamente somente os `?` do `IN`:

```sql
SELECT TACOES_DES
FROM vBIAcoes
WHERE NOTAS_NUM_NS = ?
  AND TSERVICOS_CT_COD IN (?, ...)
  AND TACOES_DES = ?
  AND ACOES_DAT_CONCLUSAO IS NOT NULL;
```

Na consulta de ações, zero linha é resultado válido e significa pendência; uma ou mais linhas
significam ação concluída. Coleção vazia não abre conexão nem gera `IN ()`: o requisito fica não
atendido e o achado permanece ancorado no PDF. Timeout, falha ODBC ou resultado inválido são erro de
dependência, nunca “zero linha”, e encerram a conformidade sem snapshot parcial. O healthcheck HTTP
não comprova conectividade SQL Server.

O kit servidor da mesma release contém a imagem exportada, Compose sem `build:`, `.env-example`,
guia e SBOM; o host precisa somente de Docker e não recebe o checkout. Instalação,
exposição LAN/firewall, volume, cutover, backup antes de upgrade, rotação de senha, health/logs,
rollback e recuperação estão no
[runbook de operação do servidor](docs/operacao-servidor.md). A porta HTTP deve permanecer restrita
à LAN confiável; TLS/VPN é obrigatório antes de atravessar esse limite.

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

Para montar cliente e kit servidor oficiais com versão igual aos manifestos do produto:

```powershell
.\.venv\Scripts\python.exe scripts\build_release.py --version 0.3.0
```

O comando recompõe `dist/release/0.3.0/`, gera os dois SBOMs, notas, manifesto e hashes e executa a
inspeção estática dos artefatos. A validação de distribuição carrega o archive num host Docker
temporário sem fonte e abre o executável num diretório cliente sem checkout/Python no `PATH`.

O smoke real do SQL Server é opt-in e pertence à homologação, não ao gate normal. O smoke disponível
para mercado exige
`ZENY_MARKET_SQLSERVER_SMOKE_ENABLED=1` e `ZENY_MARKET_SQLSERVER_SMOKE_NS` explícitos e deve ser
executado dentro da imagem aprovada conforme o runbook. Sem o opt-in exato, termina sem abrir
conexão; sua saída nunca inclui a string ODBC. A homologação de `vBIAcoes` continua um gate de
implantação separado: deve confirmar tipo físico de `TSERVICOS_CT_COD`, permissão mínima e casos
sanitizados com e sem linha antes da produção.

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
- [Catálogo de regras](docs/catalogo-regras-conformidade.md): as 41 regras do seed e suas fontes.
- [Inventário normativo](docs/inventario-fontes-normativas.md): documentos, revisões, hashes e escopo
  da auditoria normativa.
- [Operação do servidor](docs/operacao-servidor.md): instalação, LAN, volume, cutover, atualização,
  rollback, senha, observabilidade e recuperação.
- [ADRs](docs/adr): decisões arquiteturais; textos substituídos são mantidos somente quando o status
  os identifica explicitamente como histórico.
- [Exemplos locais](examples/README.md): política da bancada de PDFs não versionados.

O código segue a separação entre domínio, casos de uso, portas, adaptadores e interface Qt. O
detalhamento histórico de implementação permanece no Git; a documentação viva descreve apenas o
comportamento vigente.
