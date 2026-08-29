# Roadmap — ações concluídas para impacto ambiental e servidão

## Objetivo e resultado esperado

Adicionar ao Zeny Project Handler um cadastro persistente de códigos de serviço por projeto e usar
esses códigos, junto com a NS que nomeia o projeto, para verificar no SQL Server se ações
operacionais obrigatórias já foram concluídas. Quando o PDF trouxer **Impacto Ambiental: Sim** no
cabeçalho, deve existir ao menos uma ação concluída `AVALIAR IMPACTO AMBIENTAL`. Quando houver
menção positiva a servidão em qualquer PDF, deve existir ao menos uma ação concluída
`FALTA SERVIDÃO`. A ausência da linha aplicável deve produzir, respectivamente, uma divergência
`IMPACTO AMBIENTAL PENDENTE` ou `FALTA SERVIDÃO PENDENTE`, com navegação e callout ancorados na
evidência do PDF.

O resultado final deve preservar a arquitetura cliente-servidor: o cliente Qt apenas edita e
apresenta os códigos; o servidor valida, persiste, consulta o SQL Server, produz fatos, avalia regras
e compila os callouts.

## Como usar este roadmap

Execute uma etapa por sessão limpa do Codex. Antes de editar código, leia as instruções do
repositório, este arquivo inteiro, os arquivos citados na etapa e `git status --short`. Atualize a
tag da etapa e do índice para `#em-andamento` ao iniciar, registre as evidências durante o trabalho e
use `#concluida` somente depois de cumprir todos os critérios e validações obrigatórias. Uma
dependência pendente não é bloqueio. Use `#bloqueada` apenas com causa, evidência, impacto e ação de
desbloqueio documentados.

## Contexto confirmado

- O repositório usa Python 3.11–3.13, domínio/aplicação/portas/adaptadores, FastAPI no servidor,
  PySide6 no cliente e SQLite/Alembic na fonte principal do servidor. Os comandos oficiais estão em
  `pyproject.toml`, `README.md` e `IniciarTestes.bat`.
- A NS é validada por `domain/project_metadata.py::normalizar_numero_ns` como texto de exatamente
  10 dígitos, preserva zeros à esquerda e é persistida em `Projeto.nome`.
- `Projeto` é um agregado imutável serializado no `payload` da tabela `projects` por
  `adapters/persistence/domain_json.py`. `SqlProjectRepository.salvar` incrementa a versão do projeto
  a cada alteração. Um novo campo com valor padrão pode ser lido de payloads antigos sem exigir, em
  princípio, coluna ou migração Alembic.
- O contrato remoto de projetos está em `zeny_project_handler_contracts/projects.py`; o cliente usa
  exclusivamente `client/ui/project_gateway.py`; `ProjectApiService` e as rotas de
  `zeny_project_handler_server/app.py` são a fronteira de escrita no servidor.
- `ProjectPanelWidget._build_ui` cria hoje a caixa **Projeto** e, imediatamente abaixo, a caixa
  **Folhas PDF**. O campo da NS já filtra clipboard, limita comprimento e usa um validador de dígitos.
- `project_compliance.py` já extrai campos rotulados do cabeçalho, reconhece o rótulo
  `IMPACTO AMBIENTAL`, limita `_header_labeled_fields` à zona de cabeçalho e exclui comentários de
  revisão antes de derivar fatos técnicos. Ainda não publica um fato positivo para o valor `Sim`.
- O mesmo arquivo já publica `documento.servidao_mencionada=True`, com evidência e geometria, quando
  encontra `SERVIDÃO`, `FAIXA DE SERVIDÃO` ou `FAIXA DE DOMÍNIO` em texto/OCR que não seja comentário
  de revisão.
- `ExecutarAnaliseConformidade` carrega uma sessão semântica, consulta uma vez a classificação de
  mercado pelo `ClassificadorMercadoPort`, deriva fatos, avalia o registro ativo e só então publica
  um snapshot atômico. Falhas externas não publicam snapshot parcial.
- O adaptador `adapters/market/sql_server.py` já usa `pyodbc`, conexão curta somente leitura,
  timeout, parâmetros posicionais `?`, mensagens seguras e fechamento determinístico de cursor e
  conexão. A string ODBC e o timeout já pertencem somente ao servidor.
- O avaliador declarativo trabalha por alvo: todas as condições `when` precisam ser atendidas e a
  ausência ou falsidade de um requisito `must` numa regra aplicável produz `DIVERGENCIA`.
- `compliance_callouts.py` compila somente divergências. Quando o fato decisivo não possui
  geometria, ele pode recorrer às evidências do achado; portanto uma regra cujo requisito vem do SQL
  pode continuar apontando para o fato-gatilho extraído do PDF.
- O registro distribuído atual é `cemig-normas-distribuicao-2025.6`, possui 39 regras habilitadas e
  o método de conformidade está em `VERSAO_METODO_CONFORMIDADE = "8"`.
- A branch atual é `main`. Na criação deste roadmap, a única mudança listada era a exclusão
  preexistente de `ROADMAP.md`; ela pertence ao usuário e não deve ser revertida, recriada nem
  incorporada por acidente. Este plano usa um arquivo novo e específico em `docs/`.

## Escopo incluído

- Valor canônico de código de serviço com exatamente quatro dígitos ASCII e preservação de zeros à
  esquerda.
- Coleção persistente, ordenada e sem duplicatas de códigos de serviço no agregado `Projeto`.
- Contratos e rotas aditivas para consultar e substituir atomicamente a coleção, com controle de
  versão otimista e sem quebrar o DTO atual de detalhe do projeto.
- Nova caixa **Serviços do projeto** entre **Projeto** e **Folhas PDF**, com campo de quatro dígitos,
  botões para adicionar/remover e lista dos códigos do projeto ativo.
- Porta e adaptador somente leitura para verificar existência de ação concluída em `vBIAcoes`, com
  NS, lista de serviços e descrição da ação sempre vinculadas como parâmetros.
- Detecção do rótulo `Impacto Ambiental` com valor normalizado exatamente igual a `SIM` na zona de
  cabeçalho e agregação de qualquer menção positiva a servidão no projeto.
- Fatos auditáveis para códigos consultados, gatilhos documentais e resultado das duas consultas.
- Duas regras de conformidade com os títulos exatos solicitados e callouts localizáveis no PDF.
- Distinção entre “consulta válida sem linha” e “dependência SQL indisponível”: a primeira produz
  divergência; a segunda interrompe a análise sem snapshot novo.
- Compatibilidade de leitura de projetos antigos, round trip de persistência/portabilidade, API,
  cliente, testes, OpenAPI e documentação operacional/arquitetural.
- Marcação de snapshot anterior como desatualizado quando a NS ou os códigos de serviço atuais não
  coincidirem com os fatos operacionais registrados na execução.

## Fora de escopo

- Criar, alterar, excluir, concluir ou administrar ações no SQL Server.
- Alterar schema, índices, view, permissões ou dados de `vBIAcoes`.
- Expor string de conexão, timeout, SQL ou credenciais na API, no cliente, no SQLite ou no PDF.
- Permitir código de serviço com tamanho variável, caractere não numérico ou valor vindo do PDF.
- Inferir que a ação foi concluída por texto do PDF, metadado local, snapshot anterior ou fallback.
- Tratar comentários/anotações de revisão como evidência técnica de impacto ambiental ou servidão.
- Alterar a classificação rural/urbana existente ou a semântica genérica do avaliador de regras.
- Executar implantação, escrita externa ou homologação real sem autorização e dados de teste
  fornecidos fora do repositório.

## Restrições e invariantes

- A NS permanece string de 10 dígitos e o código de serviço permanece string de 4 dígitos no
  domínio, na API, no SQLite e no cliente. Conversão para o tipo físico do SQL Server acontece
  somente no adaptador.
- Valores da NS, serviços e descrição da ação nunca são interpolados no SQL. Somente a quantidade de
  placeholders `?` do `IN` pode ser montada pelo programa depois da validação da coleção.
- A consulta operacional deve ser semanticamente equivalente a:

  ```sql
  SELECT TACOES_DES
  FROM vBIAcoes
  WHERE NOTAS_NUM_NS = ?
    AND TSERVICOS_CT_COD IN (?, ...)
    AND TACOES_DES = ?
    AND ACOES_DAT_CONCLUSAO IS NOT NULL;
  ```

- Uma ou mais linhas significam “ação concluída”; zero linhas é um resultado válido e significa
  “pendente”. Duplicidade de linhas não é erro porque o requisito é existencial.
- Cada descrição aplicável é consultada no máximo uma vez por execução de conformidade, mesmo que o
  gatilho apareça em vários PDFs. Sem o gatilho correspondente, a ação não é consultada e a regra
  não produz achado.
- Se um gatilho existir e a coleção de serviços estiver vazia, não se gera `IN ()`: o requisito é
  tratado como não atendido, com explicação de que faltam códigos, e a divergência continua ancorada
  no PDF.
- Erro de conexão, timeout, erro do driver ou falha de execução é dependência indisponível, nunca
  equivalente a zero linhas. O job falha com mensagem segura e não publica snapshot parcial.
- A alteração da coleção usa a mesma coordenação global e a mesma precondição de versão das demais
  mutações do projeto.
- O cliente continua sem `pyodbc`, SQL, domínio de conformidade ou lógica para decidir pendência.
- Projetos persistidos antes da mudança devem abrir com coleção vazia. Exportação/importação e
  backup/restauração devem preservar a coleção sem migração destrutiva.
- O achado deve conservar todas as evidências do gatilho. O callout usa deterministicamente a
  primeira ocorrência na ordem de leitura; as demais continuam disponíveis na navegação do achado.
- Toda mudança de semântica deve incrementar a versão do método de conformidade. As duas novas regras
  devem receber IDs técnicos novos e números permanentes no registro.

## Hipóteses e decisões em aberto

1. **Tipo físico de `TSERVICOS_CT_COD`:** o pedido descreve códigos numéricos de quatro dígitos e SQL
   sem aspas; o plano assume coluna numérica e conversão para `int` apenas ao vincular os parâmetros.
   Impacto: se a view expuser `char`/`varchar`, a E03 deve manter a string de quatro dígitos no bind e
   registrar a decisão, sem mudar domínio, API ou UI. A homologação deve confirmar o tipo para evitar
   conversão implícita e perda de uso de índice.
2. **Fonte auditável das regras:** na ausência de documento normativo informado, o plano usa
   `Controle operacional de ações BI`, revisão `2026-08-28`, com os itens
   `AVALIAR IMPACTO AMBIENTAL` e `FALTA SERVIDÃO`, sem URL ou página. Impacto: antes de publicar a
   revisão do registro, a E04 deve substituir somente esses metadados se o responsável fornecer uma
   identificação oficial; os IDs e a lógica das regras permanecem estáveis.
3. **Compatibilidade da API:** como os modelos de transporte rejeitam campos desconhecidos, a
   coleção não será adicionada a `ProjectDetailDto`. Serão criadas rotas aditivas `GET` e `PUT` em
   `/api/v1/projects/{project_id}/service-codes`. Impacto: clientes antigos continuam consumindo o
   detalhe atual; o novo cliente faz uma leitura adicional ao abrir o projeto. A versão da API passa
   de `1.0.0` para `1.1.0`, ainda compatível dentro da v1.
4. **Coleção vazia:** a criação do projeto continua permitida sem serviços. A lista se torna
   obrigatória apenas quando um dos gatilhos documentais exige consulta. Impacto: projetos sem
   impacto/servidão continuam analisáveis; projetos com gatilho e lista vazia exibem a pendência em
   vez de falhar com SQL inválido.
5. **Semântica do gatilho de servidão:** o plano reutiliza a detecção positiva vigente de
   `SERVIDÃO`, `FAIXA DE SERVIDÃO` ou `FAIXA DE DOMÍNIO`, sem ampliar reconhecimento de negação ou
   novos sinônimos. Impacto: qualquer refinamento linguístico posterior deve ser outra mudança de
   método e vir acompanhado de fixtures próprias.

## Definição global de pronto

- [x] O projeto aceita zero ou mais códigos únicos de quatro dígitos, preserva zeros à esquerda e
  rejeita qualquer outro formato em todas as fronteiras.
- [x] A caixa **Serviços do projeto** aparece exatamente entre **Projeto** e **Folhas PDF**, carrega a
  coleção persistida e permite adicionar/remover com feedback e controle de conflito.
- [x] Reiniciar servidor/cliente e exportar/importar um projeto preservam os códigos.
- [x] O adaptador produz placeholders de acordo com a quantidade de serviços e vincula todos os
  valores; nenhum dado do usuário entra por concatenação no SQL.
- [x] `Impacto Ambiental: Sim` no cabeçalho consulta somente
  `AVALIAR IMPACTO AMBIENTAL`; menção a servidão consulta somente `FALTA SERVIDÃO`.
- [x] Sem linha aplicável, a lista de problemas e o PDF mostram, com âncora correta, o título exato
  solicitado; com ao menos uma linha, a regra é conforme e não recebe callout.
- [x] Ausência de gatilho não consulta a ação e não cria achado; lista vazia com gatilho produz
  pendência sem executar SQL inválido.
- [x] Falha ODBC não é tratada como pendência e não publica execução parcial.
- [x] Alterar NS ou serviços marca a execução anterior como desatualizada até nova análise.
- [x] O registro distribuído, catálogo de fatos, método, OpenAPI e documentação refletem a mudança.
- [x] `IniciarTestes.bat` termina com código zero, cobertura acima do limite e sem regressões de
  isolamento do cliente.
- [ ] Antes de produção, um smoke autorizado confirma o tipo físico da coluna, permissão de leitura
  e pelo menos um caso com linha e um sem linha, sem registrar credenciais nem dados sensíveis.
  Gate de implantação pendente: esta E05 não recebeu autorização nem massa de homologação.

## Índice das etapas

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Modelo persistente e contrato remoto dos serviços | #concluida | nenhuma | Coleção canônica, rotas GET/PUT e compatibilidade de dados/API |
| E02 | Caixa de serviços no painel Projeto | #concluida | E01 | Inclusão/remoção remota de códigos na posição visual solicitada |
| E03 | Porta e consulta parametrizada de ações | #concluida | E01 | Verificador existencial de `vBIAcoes` seguro e testado |
| E04 | Gatilhos, fatos, regras e callouts | #concluida | E01, E03 | Duas pendências auditáveis e localizáveis no PDF |
| E05 | Integração, documentação e gate final | #concluida | E02, E04 | Fluxo completo validado e documentação operacional pronta |

## E01 — Modelo persistente e contrato remoto dos serviços — #concluida

### Objetivo

Introduzir a coleção canônica de códigos de serviço no agregado `Projeto` e disponibilizar leitura e
substituição remotas por rotas aditivas e versionadas, sem alterar o DTO atual de detalhe nem exigir
migração destrutiva.

### Por que agora

Essa coleção é a entrada compartilhada pela nova caixa Qt e pela consulta SQL. Fixar validação,
persistência, concorrência e contrato primeiro evita que UI e adaptador adotem representações
divergentes. Ao concluir E01, E02 e E03 podem ser executadas em paralelo.

### Dependências e paralelismo

- Dependências: nenhuma.
- E02 e E03 dependem desta etapa e podem avançar em paralelo depois dela.
- Conflitos prováveis: `contracts/projects.py`, `project_api.py`, `server/app.py`,
  `api_spec/app.py`, `project_gateway.py` e testes de projeto/OpenAPI. Nenhuma outra etapa deve editar
  esses arquivos enquanto E01 estiver ativa.

### Escopo

- `src/zeny_project_handler/domain/project_metadata.py`
- `src/zeny_project_handler/domain/project.py`
- `src/zeny_project_handler/adapters/persistence/domain_json.py` apenas se o teste de payload legado
  demonstrar necessidade
- `src/zeny_project_handler_contracts/base.py`
- `src/zeny_project_handler_contracts/projects.py`
- `src/zeny_project_handler_contracts/versioning.py`
- `src/zeny_project_handler_server/project_api.py`
- `src/zeny_project_handler_server/app.py`
- `src/zeny_project_handler_api_spec/app.py`
- `src/zeny_project_handler_client/ui/project_gateway.py`
- `docs/api/openapi-v1.json` e `docs/api/README.md`
- Testes existentes de domínio, codec/persistência, contratos, API de projetos, gateway HTTP,
  portabilidade e OpenAPI.

### Fora de escopo

- Construir a caixa Qt.
- Consultar `vBIAcoes`.
- Criar fatos ou regras de conformidade.
- Adicionar coluna consultável à tabela `projects` sem evidência de que o payload é insuficiente.

### Passos de implementação

1. Criar uma normalização canônica que aceite somente quatro dígitos ASCII, preserve zeros à
   esquerda e produza mensagem de domínio específica. Reutilizar essa função em toda entrada do
   servidor.
2. Adicionar `codigos_servico: tuple[str, ...] = ()` ao agregado `Projeto`. Validar formato,
   unicidade e ordem determinística; a decisão deste plano é persistir em ordem crescente textual e
   rejeitar duplicatas na fronteira de domínio.
3. Comprovar por teste que um payload antigo sem o campo carrega como tupla vazia e que salvar/reabrir
   incrementa versão e conserva os códigos. Incluir round trip de pacote portátil/backup no conjunto
   de regressão relevante.
4. Criar o tipo de contrato de código de serviço e DTOs específicos:
   `ProjectServiceCodesResponse` e `ReplaceProjectServiceCodesRequest`, ambos com versão do projeto;
   o request deve aceitar tupla vazia para remoção total.
5. Implementar no servidor leitura e substituição atômica sob `TipoOperacao.ALTERACAO_PROJETO`, com
   `expected_project_version` e erro `STALE_STATE` coerente com as mutações existentes.
6. Expor `GET` e `PUT /api/v1/projects/{project_id}/service-codes` na aplicação real e na aplicação
   de especificação. Não alterar `ProjectDetailDto` nem `UpdateProjectRequest`.
7. Adicionar os métodos correspondentes ao protocolo e ao `HttpProjectGateway`. O PUT é mutação e
   não recebe retry automático.
8. Incrementar `API_VERSION` para `1.1.0`, regenerar a OpenAPI e ajustar o teste da quantidade de
   operações sem reduzir as invariantes de autenticação, erro ou streaming.

### Prompt para uma sessão limpa

```text
Na raiz do repositório ZenyProjectHandler, execute somente a E01 — Modelo persistente e contrato
remoto dos serviços — do arquivo docs/roadmap-acoes-impacto-servidao.md. Leia primeiro eventuais
AGENTS.md, o roadmap inteiro, README.md, pyproject.toml, domain/project_metadata.py,
domain/project.py, adapters/persistence/domain_json.py, contracts/base.py, contracts/projects.py,
contracts/versioning.py, server/project_api.py, server/app.py, api_spec/app.py,
client/ui/project_gateway.py e os testes relacionados. Confira git status --short, preserve toda
mudança preexistente e confirme que o código ainda corresponde ao diagnóstico do roadmap.

Sincronize a tag E01 no índice e no detalhe para #em-andamento antes de editar. Implemente uma
coleção Projeto.codigos_servico de strings únicas com exatamente quatro dígitos ASCII, zeros à
esquerda preservados, ordem textual determinística e valor padrão vazio compatível com payloads
antigos. Crie DTOs e rotas aditivas GET/PUT /api/v1/projects/{project_id}/service-codes com
expected_project_version, resposta contendo a versão atual, substituição total (inclusive tupla
vazia), coordenação global e erro STALE_STATE. Não acrescente o campo a ProjectDetailDto nem altere
o contrato PATCH da NS. Adicione os métodos ao gateway HTTP, sem retry de PUT, incremente a API para
1.1.0, regenere a OpenAPI e cubra domínio, payload legado, persistência/restart, portabilidade,
contratos, API, gateway e conflitos. Não crie coluna/migração Alembic salvo se um teste demonstrar
necessidade real; documente essa evidência antes de expandir o schema.

Execute todas as validações da E01. Não declare sucesso com teste obrigatório falhando ou não
executado. Se o aceite passar, atualize E01 e o índice para #concluida e preencha Evidências e
handoff com arquivos, decisões, comandos e resultados. Se houver impedimento real, use #bloqueada e
registre causa, evidência, impacto e ação de desbloqueio. Não inicie E02/E03, não crie commit, não
publique e não faça ação externa sem autorização. Termine com resumo conciso de mudanças,
validações e pendências.
```

### Critérios de aceite

- [x] `0001` e `9999` são aceitos como strings; `1`, `001`, `10000`, espaço interno, sinal, letra,
  dígito Unicode e booleano são rejeitados.
- [x] A coleção vazia é válida; duplicatas são rejeitadas; a ordem persistida é determinística.
- [x] Payload anterior à mudança abre com coleção vazia sem migração ou regravação automática.
- [x] Salvar e reabrir, reiniciar o servidor e exportar/importar preservam exatamente a coleção.
- [x] GET retorna coleção e versão; PUT substitui toda a coleção e incrementa uma vez a versão.
- [x] PUT com versão obsoleta retorna `409 STALE_STATE` sem alteração parcial.
- [x] `ProjectDetailDto` e o PATCH de NS continuam com a forma anterior.
- [x] O gateway não repete PUT após falha transitória.
- [x] A OpenAPI possui as duas operações autenticadas, a versão `1.1.0` e nenhum caminho interno.

### Validação obrigatória

Executar na raiz, com a virtualenv já preparada:

```powershell
.\.venv\Scripts\python.exe scripts\generate_openapi_v1.py
.\.venv\Scripts\python.exe -m pytest tests\unit\test_project_domain.py tests\unit\test_persistence_codec.py tests\integration\test_persistence.py tests\contracts\test_models.py tests\contracts\test_openapi_snapshot.py tests\server\test_project_document_api.py tests\integration\test_project_http_gateway.py tests\integration\test_project_portability.py
.\.venv\Scripts\python.exe -m ruff check src\zeny_project_handler\domain src\zeny_project_handler\adapters\persistence src\zeny_project_handler_contracts src\zeny_project_handler_server\project_api.py src\zeny_project_handler_server\app.py src\zeny_project_handler_api_spec\app.py src\zeny_project_handler_client\ui\project_gateway.py tests
git diff --check
```

Resultado esperado: todos os testes passam, o snapshot OpenAPI coincide com o schema gerado, Ruff e
`git diff --check` retornam zero.

### Migração e rollback

- Migração: não há coluna nova. O decoder usa o default vazio quando o payload legado omite o campo;
  um projeto passa a gravar o campo quando sofrer uma mutação normal.
- Compatibilidade API: rotas aditivas preservam clientes antigos e a v1. O cliente novo exige
  servidor com API `>=1.1.0`; confirmar a negociação de versão existente.
- Rollback de binário: uma versão antiga do domínio poderá rejeitar payload novo por campo
  desconhecido. Antes de rollback de produção, usar o backup obrigatório do volume e a política do
  runbook; não apagar os códigos silenciosamente.

### Bloqueios

Nenhum bloqueio conhecido.

### Riscos e mitigação

- Risco: adicionar o campo ao DTO de detalhe quebraria clientes estritos antigos. Mitigação: rotas e
  DTOs específicos.
- Risco: ordenar/deduplicar de modos diferentes em UI e servidor altera versão desnecessariamente.
  Mitigação: servidor é canônico; cliente envia a coleção já ordenada apenas como conveniência.
- Risco: payload novo impede rollback binário ingênuo. Mitigação: teste explícito e procedimento de
  backup/rollback documentado.

### Evidências e handoff

- Estado: concluído em 2026-08-28.
- Arquivos alterados:
  - domínio e persistência: `domain/project_metadata.py`, `domain/project.py` e testes de codec,
    persistência/restart/backup e portabilidade; `domain_json.py` e as migrações não precisaram de
    alteração;
  - contrato e API: `contracts/base.py`, `contracts/projects.py`, `contracts/versioning.py`,
    `server/project_api.py`, `server/app.py`, `api_spec/app.py`, `docs/api/openapi-v1.json` e
    `docs/api/README.md`;
  - cliente e testes: `client/ui/project_gateway.py`, `tests/remote_gateways.py` e testes de domínio,
    contratos, OpenAPI, servidor, gateway HTTP, persistência e portabilidade.
- Decisões tomadas:
  - `Projeto.codigos_servico` é uma tupla vazia por padrão, rejeita duplicatas e mantém ordem textual
    crescente depois de validar cada item com `normalizar_codigo_servico` e `[0-9]{4}`;
  - o transporte usa `ServiceCode`, `ProjectServiceCodesResponse` e
    `ReplaceProjectServiceCodesRequest`, com o campo `service_codes`; `ProjectDetailDto` e
    `UpdateProjectRequest` permaneceram inalterados;
  - o PUT faz substituição total sob `TipoOperacao.ALTERACAO_PROJETO`, verifica
    `expected_project_version`, incrementa a versão uma vez e não recebe retry no gateway;
  - nenhuma coluna/migração foi criada: o teste de payload legado prova o default vazio, e os testes
    de reabertura, backup e portabilidade passam mantendo os códigos dentro do payload do agregado;
    o teste de schema confirma explicitamente a ausência de coluna `service_codes`.
- Validações executadas:
  - `scripts/generate_openapi_v1.py`: concluído; snapshot gerado com API `1.1.0` e 54 operações;
  - matriz Pytest obrigatória da E01, com `TEMP`/`TMP=C:\\tmp` para evitar `MAX_PATH` nas fixtures de
    portabilidade no Windows: `133 passed in 53.35s` na confirmação final;
  - Ruff obrigatório da E01: `All checks passed!`;
  - Mypy adicional: `Success: no issues found in 303 source files`;
  - `git diff --check`: código zero; somente avisos informativos de futura normalização LF/CRLF.
- Observações para E02/E03: usar `get_service_codes`/`replace_service_codes` no gateway,
  `service_codes` nos DTOs e `codigos_servico` no domínio. A resposta do PUT já devolve a nova
  `project_version`; E02 deve preservá-la na sessão. E03 deve consumir as strings canônicas sem
  remover zeros à esquerda fora do adaptador SQL.

## E02 — Caixa de serviços no painel Projeto — #concluida

### Objetivo

Adicionar a caixa visual solicitada entre o seletor/criação de projetos e a gestão de PDFs, permitindo
consultar, adicionar e remover códigos de serviço do projeto ativo exclusivamente pelo gateway HTTP.

### Por que agora

E01 fornece validação, rotas, DTOs e concorrência. A UI pode então ser implementada sem lógica de
persistência ou SQL e sem adivinhar o formato final do contrato.

### Dependências e paralelismo

- Dependência: E01 `#concluida`.
- Pode ser executada em paralelo com E03.
- Não pode editar o adaptador SQL ou a lógica de conformidade.
- Conflitos conhecidos: `project_panel.py` e testes Qt; coordenar com qualquer trabalho simultâneo no
  painel Projeto.

### Escopo

- `src/zeny_project_handler_client/ui/project_panel.py`
- `src/zeny_project_handler_client/ui/project_gateway.py` somente para ajustes decorrentes do
  contrato final da E01
- `tests/e2e/test_mvp_ui.py`
- `tests/integration/test_project_http_gateway.py`
- Testes de tema/janela apenas se a nova caixa afetar layout ou estado habilitado.

### Fora de escopo

- Persistência direta, SQL, fatos, regras ou callouts no cliente.
- Tornar ao menos um serviço obrigatório para criar ou abrir projetos.
- Guardar lista paralela em `QSettings`.

### Passos de implementação

1. Reutilizar o comportamento numérico do campo de NS por uma abstração pequena ou um novo campo
   equivalente, com `maxLength=4`, validador `[0-9]{4}`, clipboard filtrado, placeholder, tooltip e
   nome acessível claros.
2. Criar um `QGroupBox` chamado **Serviços do projeto** depois de `_project_box` e antes de
   `_document_box`, contendo campo, botão **Adicionar**, lista e botão **Remover selecionados**.
3. Ao ativar projeto, chamar o GET da E01, preencher a lista na ordem canônica e habilitar a caixa.
   Ao limpar/excluir projeto, esvaziar e desabilitar a caixa.
4. Adicionar deve exigir projeto ativo e quatro dígitos, rejeitar duplicata com feedback local e
   executar PUT com a coleção completa e a versão vigente. Remover deve exigir seleção e executar o
   mesmo PUT sem os itens selecionados.
5. Após sucesso, atualizar tanto a coleção quanto a versão mantida em `_session`; após
   `STALE_STATE`, informar o conflito e recarregar detalhe + coleção do servidor antes de permitir
   nova mutação.
6. Incluir a nova caixa em `_apply_operation_state`, bloqueando mutações durante jobs/operação global
   como já ocorre com projeto e documentos.
7. Atualizar o guia **Como usar** para mencionar o cadastro de serviços antes da análise.

### Prompt para uma sessão limpa

```text
Na raiz do repositório ZenyProjectHandler, execute somente a E02 — Caixa de serviços no painel
Projeto — de docs/roadmap-acoes-impacto-servidao.md. Leia eventuais AGENTS.md, o roadmap inteiro,
README.md, project_panel.py, project_gateway.py, os DTOs/rotas concluídos pela E01 e os testes Qt/HTTP
relacionados. Confira git status --short, preserve mudanças preexistentes, confirme E01 como
#concluida e verifique se os nomes finais do contrato não divergiram do plano.

Atualize E02 no índice e no detalhe para #em-andamento. Adicione um QGroupBox “Serviços do projeto”
exatamente entre “Projeto” e “Folhas PDF”. Use campo de quatro dígitos ASCII com o mesmo
comportamento de clipboard/validação da NS, botão Adicionar, lista canônica e botão Remover
selecionados. Leia e substitua a coleção somente pelo gateway HTTP da E01, preserve zeros à
esquerda, evite duplicatas, aceite remoção total, mantenha a versão otimista da sessão atualizada e
recarregue após STALE_STATE. Desabilite/esvazie corretamente sem projeto e bloqueie a caixa durante
operações globais ou análise. Não persista a lista em QSettings, não importe domínio/SQL e não
implemente conformidade. Atualize o guia e cubra posição visual, acessibilidade, validação,
add/remove, reabertura/restart, conflito e estado bloqueado.

Execute as validações da E02 e não declare sucesso com falhas. Se tudo passar, marque E02 e o índice
como #concluida e preencha Evidências e handoff. Se houver impedimento real, marque #bloqueada com
causa, evidência, impacto e ação. Não inicie E03/E04, não crie commit nem publique sem autorização.
Finalize com resumo conciso de mudanças, testes e pendências.
```

### Critérios de aceite

- [x] A ordem visual é **Projeto** → **Serviços do projeto** → **Folhas PDF**.
- [x] O campo aceita exatamente quatro dígitos, inclusive zeros iniciais, e rejeita os demais casos.
- [x] Adicionar `0007` mostra `0007`; reabrir o projeto e reiniciar o servidor preservam o valor.
- [x] Duplicata não cria chamada mutável nem nova versão.
- [x] Remover seleção atualiza servidor e lista; remover o último item deixa coleção vazia.
- [x] Trocar de projeto troca a lista; excluir/limpar projeto esvazia e desabilita a caixa.
- [x] `STALE_STATE` não sobrescreve a coleção mais recente de outra janela.
- [x] A caixa não permite mutação durante operação global ou job local.
- [x] Nenhum código de domínio, `pyodbc` ou SQL é introduzido no artefato cliente.

### Validação obrigatória

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest tests\e2e\test_mvp_ui.py tests\integration\test_project_http_gateway.py tests\integration\test_window.py tests\unit\test_project_panel_remote_boundary.py tests\unit\test_client_connection.py
.\.venv\Scripts\python.exe -m ruff check src\zeny_project_handler_client\ui\project_panel.py src\zeny_project_handler_client\ui\project_gateway.py tests\e2e\test_mvp_ui.py tests\integration\test_project_http_gateway.py
.\.venv\Scripts\python.exe scripts\client_artifact_gate.py --source-only
git diff --check
```

Resultado esperado: testes e gates retornam zero; os testes Qt encontram a caixa na posição correta
e provam persistência/conflito sem dependência SQL real.

### Bloqueios

Nenhum bloqueio conhecido.

### Riscos e mitigação

- Risco: versão local fica obsoleta após PUT e quebra upload/análise seguinte. Mitigação: atualizar a
  sessão pelo DTO de resposta e cobrir a sequência em teste HTTP/E2E.
- Risco: chamadas GET durante troca de projeto exibem lista antiga. Mitigação: limpar antes de
  carregar e só aplicar resposta pertencente ao projeto ainda ativo.
- Risco: painel vertical cresce além da área disponível. Mitigação: lista com altura mínima/contida e
  smoke visual no tamanho padrão, sem remover controles existentes.

### Evidências e handoff

- Estado: concluído em 2026-08-28.
- Arquivos alterados:
  - UI: `src/zeny_project_handler_client/ui/project_panel.py`;
  - testes: `tests/e2e/test_mvp_ui.py` e `tests/unit/test_client_connection.py`.
- Decisões tomadas:
  - a NS e o código de serviço compartilham `_AsciiDigitsLineEdit`, preservando filtro ASCII de
    copiar/colar; o código usa `maxLength=4`, validador `[0-9]{4}` e permanece string;
  - a caixa só habilita depois do GET de serviços do projeto ativo e mantém a coleção canônica
    apenas em memória; nenhuma chave de serviço é escrita em `QSettings`;
  - cada add/remove envia substituição total pelo gateway, usa a versão de `_session`, aplica a
    coleção/versão retornadas pelo servidor e aceita tupla vazia;
  - em `STALE_STATE`, a coleção local é invalidada e a UI recarrega primeiro o detalhe e depois os
    serviços; a caixa permanece desabilitada até concluir a recarga;
  - a expectativa de incompatibilidade em `test_client_connection.py` foi alinhada à API `1.1.0`
    já concluída pela E01; o caso incompatível passou a exigir servidor com mínimo `1.2.0`.
- Validações executadas:
  - matriz Pytest obrigatória da E02, com `QT_QPA_PLATFORM=offscreen` e `TEMP`/`TMP` isolados no
    workspace durante a execução: `33 passed in 25.21s`;
  - Ruff obrigatório, incluindo a regressão ajustada de conexão: `All checks passed!`;
  - `scripts/client_artifact_gate.py --source-only`: `GATE DO CLIENTE: APROVADO`;
  - `git diff --check`: código zero; somente avisos informativos de futura normalização LF/CRLF.
- Observações para E05: os `objectName` finais são `mvpProjectServiceCodesBox`,
  `mvpProjectServiceCodeEdit`, `mvpAddServiceCodeButton`, `mvpProjectServiceCodeList` e
  `mvpRemoveServiceCodesButton`; o E2E cobre reabertura do cliente e o teste HTTP cobre restart do
  servidor mantendo `0007`.

## E03 — Porta e consulta parametrizada de ações — #concluida

### Objetivo

Disponibilizar no servidor uma porta independente de infraestrutura e um adaptador SQL Server que
responda se existe ao menos uma ação concluída para NS, serviços e uma das duas descrições permitidas.

### Por que agora

E01 fixa a representação dos serviços. Esta etapa isola cardinalidade existencial, segurança dos
parâmetros e falhas externas antes de acoplar a consulta ao motor de conformidade.

### Dependências e paralelismo

- Dependência: E01 `#concluida`.
- Pode ser executada em paralelo com E02.
- E04 depende desta etapa.
- Conflitos conhecidos: `ports/market.py`, `adapters/market/sql_server.py`,
  `server/composition.py` e fakes SQL. E03 não deve injetar a nova dependência no caso de uso de
  conformidade; isso pertence à E04.

### Escopo

- `src/zeny_project_handler/domain/market.py` ou um módulo de domínio adjacente para o enum fechado
  das duas descrições
- `src/zeny_project_handler/ports/market.py`
- `src/zeny_project_handler/adapters/market/sql_server.py`
- `tests/market_fakes.py`
- `tests/unit/test_sql_server_market.py`
- `tests/unit/test_market_sqlserver_smoke.py` apenas se o smoke existente for ampliado nesta etapa
- Testes de arquitetura das portas/adaptadores.

### Fora de escopo

- Detectar gatilhos no PDF.
- Produzir fatos ou achados.
- Executar consulta quando a lista de serviços estiver vazia.
- Alterar configurações secretas, porque conexão e timeout existentes serão reutilizados.

### Passos de implementação

1. Criar enum/valor fechado para `AVALIAR IMPACTO AMBIENTAL` e `FALTA SERVIDÃO`, impedindo descrição
   arbitrária de chegar ao adaptador.
2. Criar uma porta como `VerificadorAcoesConcluidasPort`, com retorno booleano existencial e erros
   separados para dados inválidos e dependência indisponível.
3. Ampliar ou compor o adaptador SQL existente para gerar `IN (?, ..., ?)` apenas pela quantidade de
   códigos já validados. Vincular parâmetros na ordem: NS, todos os serviços, descrição da ação.
4. Preservar NS/serviços como texto fora do adaptador. Aplicar a hipótese de bind inteiro somente
   depois de confirmar o tipo físico de `TSERVICOS_CT_COD`; registrar a evidência da decisão.
5. Usar `fetchmany(1)` ou operação equivalente: uma linha ou mais retorna `True`; nenhuma retorna
   `False`. Validar a forma mínima da linha sem tratar duplicidade como erro.
6. Reutilizar conexão somente leitura, autocommit, timeout, fechamento e sanitização atuais. Não
   registrar SQL com valores, connection string ou exceção bruta do driver.
7. Recusar coleção vazia antes de abrir conexão; a E04 decidirá o fato de pendência sem chamar o
   adaptador.
8. Criar fake explícito que registre `(NS, serviços, ação)` e permita controlar `True`, `False` e
   exceção sem rede.

### Prompt para uma sessão limpa

```text
Na raiz do ZenyProjectHandler, execute somente a E03 — Porta e consulta parametrizada de ações — de
docs/roadmap-acoes-impacto-servidao.md. Leia eventuais AGENTS.md, o roadmap inteiro, README.md,
domain/project_metadata.py, domain/market.py, ports/market.py, adapters/market/sql_server.py,
server/config.py, os fakes e testes SQL atuais. Confira git status --short, preserve mudanças do
usuário, confirme E01 #concluida e verifique o contrato final do código de serviço.

Marque E03 e o índice como #em-andamento. Implemente um valor fechado para as descrições exatas
“AVALIAR IMPACTO AMBIENTAL” e “FALTA SERVIDÃO”, uma porta de verificação existencial e um adaptador
somente leitura sobre vBIAcoes. A consulta deve equivaler a SELECT TACOES_DES FROM vBIAcoes WHERE
NOTAS_NUM_NS = ? AND TSERVICOS_CT_COD IN (?, ...) AND TACOES_DES = ? AND
ACOES_DAT_CONCLUSAO IS NOT NULL; monte somente os placeholders pela quantidade validada e vincule
NS, cada serviço e ação como parâmetros. Uma ou mais linhas é True, zero é False, duplicidade é
aceita. Lista vazia falha antes da conexão. Preserve timeout, autocommit, readonly, fechamento e
mensagens seguras do adaptador atual. Confirme e documente se TSERVICOS_CT_COD recebe int ou string;
nunca altere a representação de quatro dígitos fora do adaptador. Adicione fake e testes para
quantidades 1/N, zeros à esquerda, parâmetros exatos, zero/uma/múltiplas linhas e cada estágio de
falha/cleanup. Não injete ainda a dependência na conformidade e não use SQL Server real no gate.

Execute as validações da E03. Só marque E03 e o índice #concluida depois de todos os testes; em
impedimento real use #bloqueada com causa, evidência, impacto e ação. Preencha Evidências e handoff.
Não inicie E04, não crie commit, não publique e não acesse banco externo sem autorização. Entregue
resumo conciso de mudanças, validações e pendências.
```

### Critérios de aceite

- [x] A porta não importa `pyodbc`, SQLAlchemy, FastAPI nem cliente.
- [x] Somente as duas descrições exatas podem ser consultadas.
- [x] Para N serviços, o SQL contém N placeholders no `IN` e nenhum valor interpolado.
- [x] Os parâmetros preservam a correspondência NS → serviços → ação e zeros à esquerda fora da
  fronteira SQL.
- [x] Zero linha retorna `False`; uma ou várias retornam `True`.
- [x] Lista vazia e códigos inválidos não abrem conexão.
- [x] Timeout/falha de conexão, cursor, execute, fetch ou cleanup vira erro seguro de dependência.
- [x] Cursor e conexão são fechados em sucesso e em todas as falhas testadas.
- [x] `repr`, logs e mensagens não expõem connection string, servidor, usuário ou senha.
- [x] Testes comuns usam somente fakes e não dependem de rede.

### Validação obrigatória

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_sql_server_market.py tests\unit\test_market_sqlserver_smoke.py tests\unit\test_analysis_ports.py tests\unit\test_architecture.py
.\.venv\Scripts\python.exe -m ruff check src\zeny_project_handler\domain\market.py src\zeny_project_handler\ports\market.py src\zeny_project_handler\adapters\market tests\market_fakes.py tests\unit\test_sql_server_market.py tests\unit\test_market_sqlserver_smoke.py
.\.venv\Scripts\python.exe -m mypy
git diff --check
```

Resultado esperado: testes, Ruff, Mypy e diff-check retornam zero; nenhuma conexão real é aberta.

### Bloqueios

Nenhum bloqueio ativo. O bloqueio transitório do Mypy em `tests/e2e/test_mvp_ui.py:160` foi resolvido
em 2026-08-28 com tratamento explícito do retorno opcional de `panel_layout.itemAt(index)`, sem
alterar a intenção do teste da E02. O Mypy global passou em seguida nos 303 arquivos. A confirmação
documental/DBA do tipo físico de `TSERVICOS_CT_COD` continua sendo validação de homologação da E05
antes da produção, não um bloqueio do gate offline da E03.

### Riscos e mitigação

- Risco: interpolar a lista para reproduzir a aparência do SQL solicitado. Mitigação: interpolar
  apenas `?`; valores continuam no bind.
- Risco: bind com tipo incorreto força conversão da coluna e degrada índice. Mitigação: confirmar o
  tipo da view e testar o tipo dos parâmetros no fake.
- Risco: capturar exceção de dados como ausência de linha. Mitigação: `False` somente após execute e
  fetch válidos sem linha; toda exceção segue a hierarquia de dependência.

### Evidências e handoff

- Estado: concluído em 2026-08-28.
- Arquivos alterados pela E03:
  - `domain/market.py`: `DescricaoAcao` com os dois valores exatos;
  - `ports/market.py`: `VerificadorAcoesConcluidasPort`, `VerificacaoAcoesError`,
    `DadosAcoesInvalidosError` e `DependenciaAcoesError`;
  - `adapters/market/sql_server.py`: `VerificadorAcoesConcluidasSqlServer` e consulta existencial
    parametrizada de `vBIAcoes`;
  - `tests/market_fakes.py` e `tests/unit/test_sql_server_market.py`: fake registrável e matriz de
    contrato, cardinalidade, parâmetros, falhas e cleanup;
  - `tests/e2e/test_mvp_ui.py`: estreitamento explícito de `QLayoutItem | None` autorizado para
    remover o bloqueio do Mypy, sem mudar a asserção de ordem visual da E02;
  - este roadmap. Nenhum arquivo de composição/conformidade/configuração foi alterado.
- Decisões tomadas:
  - não há schema, DDL, documentação do DBA nem acesso autorizado a `vBIAcoes` no repositório para
    comprovar o tipo físico de `TSERVICOS_CT_COD`; conforme a hipótese explícita deste roadmap, a
    E03 vincula cada código como `int` somente dentro do adaptador SQL, mantendo as strings de
    quatro dígitos intactas no domínio, na porta e no fake. A homologação E05 deve confirmar que a
    coluna é numérica antes da produção; se for `char`/`varchar`, somente o bind do adaptador deverá
    mudar para string;
  - a NS segue o adaptador de mercado existente e também é vinculada como `int`; os parâmetros são
    sempre NS, cada serviço na ordem recebida e `DescricaoAcao.value`. Somente a sequência de `?` é
    montada dinamicamente após validar todos os códigos;
  - `fetchmany(1)` implementa a semântica existencial: zero linha é `False`; a primeira linha válida
    é `True`, mesmo que existam duplicatas. Linha incompatível é dado externo inválido, nunca
    ausência.
- Validações executadas:
  - matriz Pytest obrigatória da E03 mais o teste Qt corrigido, com `TEMP`/`TMP=C:\tmp` e
    `QT_QPA_PLATFORM=offscreen`: `62 passed in 1.74s`; nenhuma conexão real foi aberta;
  - Ruff obrigatório, incluindo o teste Qt corrigido: `All checks passed!`;
  - Ruff format adicional nos cinco arquivos Python da E03: `5 files already formatted`;
  - Mypy focado: `Success: no issues found in 5 source files`;
  - Mypy global obrigatório: `Success: no issues found in 303 source files`;
  - `git diff --check`: código zero, somente avisos informativos LF/CRLF.
- Observações para E04: usar `DescricaoAcao`, `VerificadorAcoesConcluidasPort`, o método
  `existe_acao_concluida`, `DadosAcoesInvalidosError` e `DependenciaAcoesError`. O bind de serviços é
  `int` exclusivamente no adaptador; a porta e o fake recebem as strings canônicas com zeros à
  esquerda.

## E04 — Gatilhos, fatos, regras e callouts — #concluida

### Objetivo

Integrar a verificação externa à execução de conformidade, publicar fatos auditáveis e criar as duas
regras que geram pendências localizáveis somente quando seus gatilhos documentais existem.

### Por que agora

E01 fornece NS/serviços persistidos e E03 fornece consulta segura. Esta etapa conecta as duas fontes
sem colocar SQL no provedor/evaluador e usa a infraestrutura de evidência/callout já existente.

### Dependências e paralelismo

- Dependências: E01 e E03 `#concluida`.
- Pode começar mesmo se E02 ainda estiver ativa, desde que E02 não edite contratos/servidor da E01.
- E05 depende desta etapa e da E02.
- Conflitos conhecidos: `project_compliance.py`, `compliance_analysis.py`, catálogo de fatos, seed de
  regras, composição do servidor, fakes e testes de conformidade.

### Escopo

- `src/zeny_project_handler/application/project_compliance.py` e, se necessário, um módulo pequeno
  adjacente para detecção compartilhada de gatilhos
- `src/zeny_project_handler/application/compliance_analysis.py`
- `src/zeny_project_handler/application/compliance_fact_providers.py` apenas se o contexto tipado
  precisar carregar o resultado externo
- `src/zeny_project_handler/domain/compliance_facts.py`
- `src/zeny_project_handler/adapters/compliance/data/regras_conformidade_v1.json`
- `src/zeny_project_handler_server/composition.py`
- `src/zeny_project_handler_server/compliance_api.py` apenas para staleness/apresentação necessária
- `tests/market_fakes.py`, testes unitários/integrados de conformidade, callouts, catálogo e
  composição.

### Fora de escopo

- Alterar o avaliador genérico para conhecer ações, SQL ou PDF.
- Consultar a mesma ação por documento, evidência ou regra.
- Gerar callout para resultado conforme.
- Usar texto do PDF como prova de conclusão da ação.

### Passos de implementação

1. Extrair/reutilizar uma detecção pura que percorra evidências sem comentários na ordem de leitura e
   retorne:
   - todas as ocorrências de campo rotulado `IMPACTO AMBIENTAL` na zona de cabeçalho cujo valor
     normalizado seja exatamente `SIM`;
   - todas as evidências já aceitas pela detecção vigente de servidão em qualquer documento.
2. Em `ExecutarAnaliseConformidade`, detectar gatilhos depois de carregar a sessão. Para cada ação
   distinta aplicável e somente se houver serviços, chamar a porta da E03 uma vez. Manter as
   verificações de cancelamento entre consultas.
3. Se não houver serviços, construir resultado tipado “não consultado por lista vazia” que será
   convertido em requisito falso, sem chamar o adaptador. Se houver falha externa, propagar erro
   seguro e não publicar snapshot.
4. Passar ao analisador um contexto imutável com gatilhos, códigos consultados e ações concluídas;
   não permitir que provedores abram conexão.
5. Registrar no catálogo e publicar no alvo de projeto os fatos:
   `projeto.codigo_servico` (um por código), `projeto.impacto_ambiental_sim`,
   `projeto.servidao_mencionada`, `projeto.acao_avaliar_impacto_ambiental_concluida` e
   `projeto.acao_falta_servidao_concluida`. Os gatilhos carregam evidência/geometria; os resultados
   SQL carregam origem auditável sem credencial.
6. Adicionar duas regras de escopo PROJETO e severidade ERRO, com IDs novos e títulos exatos
   `IMPACTO AMBIENTAL PENDENTE` e `FALTA SERVIDÃO PENDENTE`. O `when` usa o gatilho positivo e o
   `must` exige o fato de ação concluída igual a `true`.
7. Usar a fonte interna decidida globalmente, incrementar o seed para
   `cemig-normas-distribuicao-2025.7`, preservar numeração permanente das 39 regras existentes e
   atribuir os próximos números às novas.
8. Incrementar `VERSAO_METODO_CONFORMIDADE` de `8` para `9`.
9. Ampliar a avaliação de staleness: comparar a NS e o conjunto de fatos
   `projeto.codigo_servico` da execução com o estado atual do projeto, além de método/regras.
10. Provar que o achado inclui evidências do `when` e que o compilador de callouts usa essas
    evidências quando o fato decisivo do SQL não possui geometria. A primeira evidência na ordem de
    leitura ancora a caixa; todas permanecem navegáveis.

### Prompt para uma sessão limpa

```text
Na raiz do ZenyProjectHandler, execute somente a E04 — Gatilhos, fatos, regras e callouts — de
docs/roadmap-acoes-impacto-servidao.md. Leia eventuais AGENTS.md, o roadmap inteiro, README.md,
docs/arquitetura-conformidade.md, docs/catalogo-regras-conformidade.md,
application/project_compliance.py, application/compliance_analysis.py,
application/compliance_fact_providers.py, application/compliance_evaluation.py,
application/compliance_callouts.py, domain/compliance_facts.py, o seed JSON, server/composition.py,
server/compliance_api.py e os testes/fakes relacionados. Confira git status --short, preserve
mudanças preexistentes, confirme E01/E03 #concluida e adapte nomes apenas conforme o handoff real.

Marque E04 e o índice como #em-andamento. Detecte de modo puro e determinístico “Impacto Ambiental”
com valor normalizado exatamente SIM somente no cabeçalho e reutilize a detecção vigente de
servidão fora de comentários. Consulte pela porta da E03 no máximo uma vez por ação aplicável e
execução, com a NS atual e a coleção da E01. Sem serviços, não gere IN vazio: publique requisito
falso com origem explicativa; em erro ODBC, falhe sem snapshot. Passe resultados tipados ao
analisador e publique fatos de projeto para cada código, os dois gatilhos com evidência e os dois
resultados de ação sem segredos. Adicione regras PROJETO/ERRO com títulos exatos IMPACTO AMBIENTAL
PENDENTE e FALTA SERVIDÃO PENDENTE, when no gatilho e must na ação concluída. Use IDs novos, fonte
“Controle operacional de ações BI”, revisão 2026-08-28, itens exatos, salvo fonte oficial já
registrada no handoff. Eleve o seed a cemig-normas-distribuicao-2025.7 e o método de 8 para 9.
Mantenha o avaliador genérico sem SQL. Marque execução antiga desatualizada quando NS/serviços
atuais divergirem dos fatos. Cubra sem gatilho, lista vazia, linha ausente/presente, duplicidade de
evidências, dois gatilhos, falha/cancelamento sem snapshot, assinatura, histórico, numeração e
callout ancorado na evidência PDF.

Execute todas as validações da E04. Não declare sucesso com teste falhando ou não executado. Se o
aceite passar, marque E04 e o índice #concluida e preencha Evidências e handoff; em impedimento real,
use #bloqueada com causa, evidência, impacto e ação. Não inicie E05, não crie commit, não publique e
não acesse SQL real sem autorização. Termine com resumo conciso de mudanças, testes e pendências.
```

### Critérios de aceite

- [x] `Impacto Ambiental: Sim`, com variação de caixa/acentos/espaços, produz gatilho somente se o
  rótulo estiver no cabeçalho e o valor normalizado for exatamente `SIM`.
- [x] `Não`, valor vazio, `SIMULAÇÃO`, ocorrência fora do cabeçalho ou comentário de revisão não
  produz o gatilho ambiental.
- [x] Qualquer detecção de servidão já aceita pelo comportamento vigente produz um único gatilho de
  projeto, conservando todas as evidências ordenadas.
- [x] Sem gatilho, a ação correspondente não é consultada e a regra não cria achado.
- [x] Com gatilho e serviços, cada ação distinta é consultada exatamente uma vez.
- [x] Com ao menos uma linha, a regra é `CONFORME` e não gera callout.
- [x] Sem linha ou sem códigos, a regra é `DIVERGENCIA`, tem o título exato e gera callout na
  evidência do PDF.
- [x] Se ambos os gatilhos existirem e ambas as ações faltarem, existem duas divergências e dois
  callouts independentes.
- [x] Erro externo ou cancelamento entre consultas não publica snapshot parcial nem converte erro em
  pendência.
- [x] Os códigos participam da assinatura auditável sem perder zeros à esquerda.
- [x] Alterar NS ou serviços marca o snapshot anterior como desatualizado; reanalisar produz/reutiliza
  o snapshot coerente com a nova entrada.
- [x] As 39 regras antigas mantêm IDs/números; as novas recebem os próximos números e o catálogo passa
  a 41 regras.

### Validação obrigatória

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest tests\unit\test_compliance.py tests\unit\test_compliance_catalog_parity.py tests\unit\test_compliance_callouts.py tests\integration\test_compliance_analysis.py tests\integration\test_compliance_callout_viewer.py tests\integration\test_compliance_registry_persistence.py tests\server\test_composition.py tests\server\test_compliance_api.py
.\.venv\Scripts\python.exe -m ruff check src\zeny_project_handler\application\project_compliance.py src\zeny_project_handler\application\compliance_analysis.py src\zeny_project_handler\application\compliance_fact_providers.py src\zeny_project_handler\domain\compliance_facts.py src\zeny_project_handler_server\composition.py src\zeny_project_handler_server\compliance_api.py tests
.\.venv\Scripts\python.exe -m mypy
git diff --check
```

Resultado esperado: todas as matrizes de consulta/fato/regra/callout passam; Ruff, Mypy e diff-check
retornam zero; nenhum teste abre rede real.

### Bloqueios

Nenhum bloqueio conhecido além de E01/E03. Se a fonte auditável oficial for obrigatória para o seed
e divergir da hipótese registrada, documentar a informação recebida e atualizar apenas os metadados
antes do aceite.

### Riscos e mitigação

- Risco: duplicar a extração de campos entre inspeção documental e gatilho. Mitigação: fatorar/reusar
  a mesma função pura e testar paridade.
- Risco: fato SQL sem geometria gera divergência não localizável. Mitigação: conservar as evidências
  do `when` no achado e testar o fallback real do compilador.
- Risco: lista vazia se confunde com indisponibilidade externa. Mitigação: origem/estado tipados
  distintos e mensagens separadas.
- Risco: novo resultado externo não altera identidade do snapshot. Mitigação: fatos de códigos e
  ação entram na assinatura e o método é incrementado.

### Evidências e handoff

- Estado: concluído em 2026-08-29.
- Arquivos alterados pela E04:
  - `application/compliance_fact_providers.py`: estados e contexto imutável tipado para gatilhos,
    códigos e resultados das duas ações;
  - `application/project_compliance.py`: detecção pura/ordenada, publicação dos cinco fatos novos e
    preservação de todas as evidências positivas;
  - `application/compliance_analysis.py`: composição das consultas por ação, cancelamento entre
    consultas, método `9`, snapshot atômico e staleness por NS/serviços;
  - `domain/compliance_facts.py`, seed JSON, `application/compliance_registry.py` e catálogo
    versionado: vocabulário, duas regras e upgrade aditivo `2025.6` → `2025.7`;
  - `server/composition.py`: composição do verificador da E03 com a mesma configuração ODBC já
    pertencente ao servidor;
  - `tests/market_fakes.py` e testes unitários, integrados, servidor/E2E relacionados: resultados e
    erros controláveis por ação, matriz de gatilhos/consultas/snapshot/callout/staleness e contagens
    atualizadas para 41 regras.
- Decisões tomadas:
  - IDs finais: `bi.acoes.impacto-ambiental` (Regra 40) e `bi.acoes.falta-servidao` (Regra 41);
  - chaves finais: `projeto.codigo_servico`, `projeto.impacto_ambiental_sim`,
    `projeto.servidao_mencionada`, `projeto.acao_avaliar_impacto_ambiental_concluida` e
    `projeto.acao_falta_servidao_concluida`;
  - sem fonte oficial adicional no handoff, foram usados `Controle operacional de ações BI`, revisão
    `2026-08-28`, e os itens exatos de cada ação, sem URL/página;
  - lista vazia usa `EstadoVerificacaoAcao.SEM_CODIGOS_SERVICO`, publica requisito `False` com origem
    explicativa e nunca chama a porta; gatilho ausente usa `NAO_APLICAVEL`;
  - os resultados consultados usam somente `PENDENTE`/`CONCLUIDA`; origem, fatos e snapshots não
    carregam SQL, configuração ODBC ou credenciais;
  - a inicialização oficial adiciona seletivamente as duas regras a registros `2025.6`, conserva a
    revisão anterior no histórico, mantém números 1–39 e reserva 40–41 para os novos IDs.
- Validações executadas:
  - Pytest obrigatório da E04, com `QT_QPA_PLATFORM=offscreen`: `114 passed in 11.97s`; fixtures
    sintéticas somente, sem conexão SQL Server real;
  - Ruff obrigatório: `All checks passed!`;
  - Ruff format adicional nos 16 arquivos Python alterados/relevantes: `16 files already formatted`;
  - Mypy global: `Success: no issues found in 303 source files`;
  - `git diff --check`: código zero; apenas avisos informativos LF/CRLF.
- Observações para E05: seed final `cemig-normas-distribuicao-2025.7`, método `9`, fake final
  `FakeVerificadorAcoesConcluidas` com mapas `resultados`/`erros`. Atualizar a documentação viva que
  ainda resume o baseline 2025.6/39 regras e executar o gate global. O smoke autorizado continua
  responsável por confirmar o tipo físico de `TSERVICOS_CT_COD`; nenhum acesso real ocorreu na E04.

## E05 — Integração, documentação e gate final — #concluida

### Objetivo

Validar o fluxo completo cliente → API → persistência → análise → SQL fake → regra → DTO → callout,
atualizar toda documentação viva e executar o gate oficial antes de considerar a alteração pronta.

### Por que agora

Somente depois de UI e conformidade concluídas é possível provar que versões, restart, navegação,
histórico e documentação descrevem o mesmo comportamento ponta a ponta.

### Dependências e paralelismo

- Dependências: E02 e E04 `#concluida`.
- Não possui etapa paralela neste roadmap.
- Deve integrar as implementações existentes, sem reescrever componentes aprovados apenas por
  preferência local.

### Escopo

- Testes E2E/HTTP/servidor necessários para o fluxo completo.
- `README.md`
- `docs/especificacao-funcional.md`
- `docs/arquitetura-conformidade.md`
- `docs/catalogo-regras-conformidade.md`
- `docs/inventario-paridade-cliente-servidor.md`
- `docs/operacao-servidor.md`
- `server/LEIA-ME-SERVIDOR.md` e exemplos de ambiente somente se o smoke operacional ganhar entrada
  nova
- `docs/api/openapi-v1.json`
- Gate oficial `IniciarTestes.bat` e inspeções de isolamento já existentes.

### Fora de escopo

- Conectar à produção ou alterar permissões/dados externos.
- Mascarar falha de teste reduzindo cobertura, removendo regra antiga ou relaxando isolamento.
- Construir/publicar release ou commit sem pedido explícito.

### Passos de implementação

1. Criar/ajustar um cenário integrado com projeto de NS conhecida, serviços incluindo zero inicial,
   PDF sintético com `Impacto Ambiental: Sim` e seção de servidão, fake de ações e servidor real de
   teste. Provar as quatro combinações presente/ausente das duas ações.
2. Provar pelo cliente Qt que os códigos persistem após reabertura/restart e que os dois achados
   aparecem com títulos exatos, navegam para página/geometria corretas e controlam visibilidade dos
   callouts.
3. Provar conflito de versão entre dois clientes e que a análise usa a coleção vigente, não o estado
   visual de uma janela antiga.
4. Atualizar OpenAPI e documentação: caixa nova, formato dos códigos, rotas, consulta parametrizada,
   frequência, semântica de zero linha, lista vazia, falha fechada, permissões `SELECT` mínimas sobre
   `vBIAcoes`, 41 regras, seed `2025.7`, método `9`, staleness e callouts.
5. Revisar README/runbook para deixar claro que o mesmo segredo/timeout SQL Server atende mercado e
   ações, sem ir para API/cliente/volume. Não inserir string real, NS de produção ou códigos
   sensíveis.
6. Se houver acesso autorizado de homologação, executar smoke sanitizado dentro da imagem aprovada
   com uma combinação que retorna linha e outra que não retorna. Confirmar tipo de
   `TSERVICOS_CT_COD`, plano/permissão de leitura e ausência de escrita. Sem autorização, registrar o
   smoke como pendência de implantação, não falsificar evidência nem bloquear o gate automatizado.
7. Executar o gate completo e corrigir regressões dentro do escopo. Conferir `git diff` para garantir
   que `ROADMAP.md` removido pelo usuário permanece intocado e que nenhum segredo/artefato temporário
   entrou na mudança.

### Prompt para uma sessão limpa

```text
Na raiz do ZenyProjectHandler, execute somente a E05 — Integração, documentação e gate final — de
docs/roadmap-acoes-impacto-servidao.md. Leia eventuais AGENTS.md, o roadmap inteiro e os handoffs de
E01–E04, README.md, a especificação funcional, arquitetura/catálogo de conformidade, inventário de
paridade, runbook do servidor, OpenAPI, os testes E2E/HTTP relevantes e git status --short. Preserve
toda mudança preexistente, especialmente a exclusão do ROADMAP.md do usuário. Confirme E02/E04
#concluida e verifique os nomes/versões finais implementados.

Marque E05 e o índice como #em-andamento. Integre e teste o fluxo completo: cadastrar serviços de
quatro dígitos (incluindo zero inicial) pelo cliente, persistir/reabrir/reiniciar, analisar PDF
sintético com Impacto Ambiental: Sim e servidão, controlar pelo fake a presença/ausência das duas
ações, verificar consulta única por ação, títulos exatos, DTOs, navegação e callouts. Cubra dois
clientes com STALE_STATE e uso da coleção vigente. Atualize README.md,
docs/especificacao-funcional.md, docs/arquitetura-conformidade.md,
docs/catalogo-regras-conformidade.md, docs/inventario-paridade-cliente-servidor.md,
docs/operacao-servidor.md, server/LEIA-ME-SERVIDOR.md quando aplicável e OpenAPI com rotas, SQL
parametrizado, zero linha versus erro, lista vazia, permissões mínimas, 41 regras, versão do seed,
método e staleness. Não acesse SQL real sem autorização. Se houver ambiente autorizado, registre
somente resultado sanitizado de um caso com linha e um sem; caso contrário, documente como gate de
implantação pendente.

Execute scripts/gates exatamente como listados na E05, inclusive IniciarTestes.bat. Não declare
sucesso com qualquer validação obrigatória falhando ou não executada. Se tudo passar, marque E05 e o
índice #concluida, confirme a Definição global de pronto e preencha Evidências e handoff com arquivos,
comandos, resultados e pendência de homologação, se houver. Em impedimento real use #bloqueada com
causa, evidência, impacto e ação. Não crie commit, release, publicação ou alteração externa sem
autorização. Finalize com resumo conciso de mudanças, validações e pendências.
```

### Critérios de aceite

- [x] Um teste ponta a ponta prova cadastro, persistência, restart e uso dos serviços na análise.
- [x] A matriz impacto/servidão × ação presente/ausente produz exatamente os achados esperados.
- [x] Os títulos exibidos são exatamente `IMPACTO AMBIENTAL PENDENTE` e
  `FALTA SERVIDÃO PENDENTE`.
- [x] Cada divergência navega e ancora o callout na evidência correta do PDF.
- [x] Dois clientes não perdem atualização e a análise usa NS/serviços vigentes.
- [x] A OpenAPI gerada coincide com o snapshot e permanece livre de paths/segredos.
- [x] README, especificação, arquitetura, catálogo, paridade e runbook não contradizem código ou
  versões.
- [x] A documentação de operação concede somente `SELECT` nas colunas necessárias de `TB_NOTAS` e
  `vBIAcoes`, sem escrita/DDL.
- [x] O artefato cliente continua sem módulos do servidor, `pyodbc`, seeds ou SQL.
- [x] O gate oficial completo passa com cobertura acima de 85,01% e complexidade dentro do limite.
- [x] Homologação real executada com evidência sanitizada ou registrada explicitamente como requisito
  de implantação ainda não autorizado.

### Validação obrigatória

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe scripts\generate_openapi_v1.py
.\.venv\Scripts\python.exe -m pytest tests\contracts tests\server\test_project_document_api.py tests\server\test_compliance_api.py tests\integration\test_project_http_gateway.py tests\integration\test_compliance_analysis.py tests\integration\test_compliance_callout_viewer.py tests\e2e\test_mvp_ui.py tests\e2e\test_span_compliance_ui.py
.\.venv\Scripts\python.exe scripts\client_artifact_gate.py --source-only
.\IniciarTestes.bat
git diff --check
git status --short
```

Resultado esperado: todos os comandos obrigatórios retornam zero, `relatorio-testes.txt` termina em
`RESULTADO FINAL: APROVADO`, cobertura é superior a 85,01%, e o status não contém segredos,
artefatos temporários nem alteração acidental da exclusão preexistente de `ROADMAP.md`.

### Homologação e rollback

- Homologação real é um gate de implantação, não dos testes offline. Usar imagem aprovada, conexão
  por ambiente, NS/serviços autorizados e saída sem valores sensíveis. Confirmar uma consulta com
  linha e outra sem linha para cada descrição quando houver massa disponível.
- Antes da atualização em produção, criar snapshot/backup consistente do volume conforme o runbook.
- Rollback deve restaurar binário e volume compatíveis; não tentar remover manualmente campos do
  payload nem editar SQLite. A mudança não escreve no SQL Server.

### Bloqueios

Nenhum bloqueio automatizado conhecido. A homologação real depende de autorização, conexão e massa
de teste com NS/serviços conhecidos. Se ausentes na execução desta etapa, registrar causa, impacto
(produção ainda não liberada) e ação concreta para DBA/responsável, sem marcar os testes locais como
aprovados por inferência.

### Riscos e mitigação

- Risco: documentação mantém contagem/versão antiga. Mitigação: testes de paridade do catálogo e
  revisão textual explícita.
- Risco: cenário E2E passa com fake, mas coluna real possui tipo/permissão diferente. Mitigação: gate
  de homologação separado e sanitizado antes da implantação.
- Risco: executar todos os gates altera relatórios/artefatos locais. Mitigação: conferir status e não
  incluir saídas geradas fora do escopo.

### Evidências e handoff

- Estado: concluído em 2026-08-29; gate offline aprovado, sem liberação implícita para produção.
- Arquivos alterados pela E05:
  - integração: `tests/e2e/test_mvp_ui.py`, `tests/integration/test_project_http_gateway.py`,
    `tests/pdf_fixtures.py` e `tests/conftest.py`;
  - documentação: `README.md`, `docs/api/README.md`, `docs/especificacao-funcional.md`,
    `docs/arquitetura-conformidade.md`, `docs/catalogo-regras-conformidade.md`,
    `docs/inventario-paridade-cliente-servidor.md`, `docs/operacao-servidor.md` e
    `server/LEIA-ME-SERVIDOR.md`;
  - `docs/api/openapi-v1.json` foi regenerado e permaneceu byte a byte igual ao snapshot vigente;
    este roadmap sincroniza aceite e handoff.
- Decisões e cobertura integrada:
  - a fixture PDF versionada contém `Impacto Ambiental: Sim` no cabeçalho e `FAIXA DE SERVIDAO` em
    outra região, permitindo comprovar âncoras e navegação distintas sem corpus privado;
  - o E2E cadastra `0007` pelo cliente, simula uma segunda sessão vencedora e `STALE_STATE`, recarrega
    `("0007", "1234")` e prova a matriz completa das duas ações pelo
    `FakeVerificadorAcoesConcluidas`, com uma consulta por ação/execução, DTOs, títulos e callouts;
  - o teste HTTP reinicia o runtime, mantém a coleção, usa dois gateways e comprova que a análise
    consulta a NS e os serviços canônicos vigentes, não a tentativa obsoleta;
  - API final `1.1.0`, DTOs `ProjectServiceCodesResponse` e
    `ReplaceProjectServiceCodesRequest`, seed `cemig-normas-distribuicao-2025.7`, método `9` e 41
    regras foram conferidos contra código, OpenAPI e catálogo.
- Validações executadas:
  - `scripts/generate_openapi_v1.py`: código zero; snapshot sem diff e teste contratual aprovado;
  - matriz Pytest obrigatória da E05 com `QT_QPA_PLATFORM=offscreen` e `TEMP`/`TMP=C:\tmp`:
    `99 passed in 35.17s`;
  - `scripts/client_artifact_gate.py --source-only`: `GATE DO CLIENTE: APROVADO`;
  - a primeira execução de `IniciarTestes.bat` detectou três estreitamentos Mypy no novo E2E e um
    arquivo versionado fora do formato; ambos foram corrigidos sem relaxar gates;
  - confirmação final de `IniciarTestes.bat`: `RESULTADO FINAL: APROVADO`, Ruff e formato em 318
    arquivos, Mypy sem problemas em 303 fontes, `856 passed in 178.00s`, cobertura `86.61%`, gate
    do cliente aprovado e 2.542 funções/métodos sem complexidade E/F.
  - `git diff --check`: código zero; somente avisos informativos de futura normalização LF/CRLF;
  - `git status --short`: somente os 13 arquivos intencionais desta E05, sem segredo, artefato
    temporário, alteração staged ou entrada para `ROADMAP.md`.
- Homologação SQL Server: não executada, pois não houve autorização explícita, imagem aprovada nem
  massa conhecida. Causa: acesso real está fora do escopo autorizado. Impacto: produção ainda não
  está liberada. Ação: DBA/responsável deve confirmar o tipo físico de `TSERVICOS_CT_COD`, conceder
  somente `SELECT` nas colunas documentadas e executar, dentro da imagem aprovada, um caso sanitizado
  com linha e outro sem linha para cada ação, sem registrar NS, serviços, SQL, conexão ou credenciais.
- Preservação: nenhum acesso SQL real, commit, release, publicação ou alteração externa foi feito;
  `ROADMAP.md` não foi recriado nem tocado, e `relatorio-testes.txt` permanece ignorado.
