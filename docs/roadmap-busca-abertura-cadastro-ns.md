# Roadmap — Busca, abertura e cadastro unificados de NS

## Objetivo e uso

Oferecer um único campo no painel **Projeto** para pesquisar projetos do servidor, abrir uma NS
existente ou informar uma NS nova para criação. Ao tentar cadastrar uma NS existente, abrir
diretamente o projeto correspondente, sem criar duplicata e sem perguntar se o usuário deseja abri-lo.

Este documento planeja o desenvolvimento; não altera o comportamento do aplicativo. Execute uma
etapa por sessão limpa do Codex, confirme suas dependências e atualize o índice, a tag da etapa e
**Evidências e handoff**. Dependência pendente não é bloqueio. Use somente `#pendente`,
`#em-andamento`, `#concluida` e `#bloqueada`; mantenha no máximo uma etapa em andamento neste plano.

## Contexto confirmado em 10/09/2026

- Repositório Python 3.11–3.13, cliente PySide6, servidor FastAPI, contratos Pydantic e SQLite no
  servidor. Referências: `pyproject.toml`, `client/pyproject.toml`, `server/pyproject.toml`,
  `README.md` e `docs/adr/0013-arquitetura-cliente-servidor.md`.
- O Git estava limpo antes deste documento. Não foram encontrados `AGENTS.md` na hierarquia
  aplicável ou dentro do projeto durante a inspeção. Verifique novamente ao executar cada etapa.
- A convenção existente é `docs/roadmap-<escopo>.md`. O roadmap de interpretação e topologia tem
  outro escopo e deve ser preservado.
- `src/zeny_project_handler_client/ui/project_panel.py` já implementa um `QComboBox` editável
  (`mvpProjectCombo`), com `QCompleter` por ocorrência de trecho e entrada de até dez dígitos ASCII.
  `atualizar_projetos()` carrega somente `limit=200, offset=0`; as sugestões são locais.
- O mesmo painel ainda tem outro campo, `mvpProjectNameEdit` (`_service_note`), usado por
  `criar_projeto()` e `alterar_numero_ns()`. `abrir_selecionado()` usa o seletor. Portanto, busca e
  criação ainda recebem texto de lugares diferentes.
- `criar_projeto()` consulta a NS exata antes do POST; `_offer_open_existing()` pergunta se deve
  abrir a existente. `_offer_create_missing()` pede confirmação para criar uma NS ausente.
  A recusa hoje limpa a sessão ativa e os painéis, conforme `docs/especificacao-funcional.md`.
- `src/zeny_project_handler_client/ui/project_gateway.py` contém `list_projects()`,
  `find_project_by_service_note()`, `create_project()` e `get_project()`. Somente o erro exato
  `404 RESOURCE_NOT_FOUND` da resolução de NS vira `None`; outros erros são propagados.
- `src/zeny_project_handler_server/project_api.py` e `app.py` oferecem
  `GET /api/v1/projects/by-service-note/{service_note}`: resposta única, ausência com 404 ou
  ambiguidade histórica com `409 INTEGRITY_ERROR`. Essa resolução alcança projetos fora da
  primeira página. A listagem atual não recebe filtro de NS.
- A criação no servidor já usa idempotência, coordenação de alteração de projeto e verificação de
  disponibilidade de NS. `409 PROJECT_ALREADY_EXISTS` inclui `project_id` e `service_note` seguros.
  Há testes de criação concorrente e colisão na alteração de NS em
  `tests/server/test_project_document_api.py`. Não é necessário inventar uma nova regra de unicidade.
- `src/zeny_project_handler/domain/project_metadata.py` exige dez dígitos ASCII e preserva zeros à
  esquerda. Fragmentos são entradas de pesquisa, não NS válidas para cadastro.
- Ativação, restauração e limpeza usam `_select_and_activate()`, `_activate()`,
  `_reset_to_initial_state()`, `last_project_id` e sinais consumidos por
  `src/zeny_project_handler_client/ui/main_window.py`. `_apply_operation_state()` bloqueia o painel
  durante operações locais ou globais.
- A API declarativa está em `src/zeny_project_handler_api_spec/app.py`; o snapshot é
  `docs/api/openapi-v1.json`. `docs/api/README.md` documenta geração e compatibilidade v1.
- Já existem regressões de seletor, diálogos e corrida em `tests/e2e/test_mvp_ui.py`, gateways em
  `tests/integration/test_project_http_gateway.py` e fronteira em
  `tests/unit/test_project_panel_remote_boundary.py`. Esses testes foram inspecionados, não
  executados para criar este plano; sua presença não comprova que a suíte passe no ambiente atual.

## Escopo e invariantes

Incluído: entrada única de busca/cadastro; sugestões remotas por trecho de NS; resolução exata;
redirecionamento direto em duplicidade; estados de pesquisa, erro e criação; teclado; preservação de
“Alterar NS”; testes, contratos e documentação associados.

Fora de escopo: interpretação de PDFs, GMAX/SQL Server de mercado, regras de conformidade,
importação/mesclagem de projetos, saneamento de duplicatas históricas, alteração do formato da NS,
migração de banco, distribuição ou implantação. Os painéis dependentes entram apenas na regressão
de troca e limpeza do projeto ativo.

Todas as etapas devem preservar:

- Servidor como fonte de existência e unicidade; cliente sem banco ou regras de negócio locais.
- Pesquisa não cria, renomeia nem abre projeto apenas porque o usuário digitou dez dígitos.
- Apenas resolução exata bem-sucedida ou ausência exata confirmada decide entre abrir e criar.
  Lista vazia, falha HTTP, autenticação, timeout e resultado antigo não comprovam ausência.
- POST único por ação explícita, sem retry automático; conflito de criação leva ao projeto
  existente. Integridade ambígua nunca autoriza escolher arbitrariamente um projeto ou criar outro.
- NS como texto; dez dígitos ASCII para criação e alteração; zeros iniciais preservados.
- IDs remotos associados às sugestões, sem aproveitar o ID de uma seleção anterior após edição.
- Bloqueio de operações, controle de versão da alteração de NS e sincronização dos painéis.

## Decisões propostas e hipóteses

Estas decisões orientam a implementação; não descrevem funcionalidades já existentes.

1. **Campo e ação únicos:** usar o seletor editável como “Pesquisar ou cadastrar NS” e uma ação
   “Abrir ou criar”. Enter executa a mesma ação. Selecionar uma sugestão e confirmar abre o projeto;
   a digitação isolada só pesquisa. Isso evita criação involuntária e dispensa alternar entre campos.
2. **NS ausente:** manter confirmação explícita com a NS completa antes da criação. A recusa mantém
   a limpeza local já especificada no produto. **NS existente:** abrir diretamente e mostrar uma
   mensagem de status, inclusive se a intenção inicial era criar. O diálogo de duplicidade deixa
   de fazer parte desse fluxo.
3. **Alterar NS:** preservar o botão e mover a entrada da nova NS para um diálogo específico,
   preenchido a partir do projeto ativo. A busca nunca renomeia o projeto ativo. Cancelar esse
   diálogo preserva a sessão; colisão continua sendo erro de alteração, sem mesclar projetos.
4. **Busca completa no servidor:** manter correspondência por trecho, coerente com o completer
   atual, e filtrar antes de paginar. Sugestões podem ser limitadas a 200, mas devem informar o total
   e orientar a refinar quando houver mais resultados. Não baixar todos os projetos a cada tecla.
5. **Contrato aditivo proposto:** criar `GET /api/v1/projects/search` com `query` de 1–10 dígitos
   ASCII, `limit` e `offset`, retornando o DTO de lista existente. Nome novo proposto para o gateway:
   `search_projects()`. Campo vazio usa a listagem existente. A rota dedicada evita um servidor
   antigo ignorar silenciosamente um parâmetro de filtro desconhecido.
6. **Responsividade:** consultas disparadas pela digitação ficam fora da thread gráfica, com
   debounce inicial de 300 ms e descarte de respostas de pesquisas anteriores. O intervalo é
   ajustável na implementação; não é uma exigência de negócio.
7. **Compatibilidade:** servidor sem a rota nova apresenta pesquisa indisponível, nunca “NS não
   existe”. A resolução exata atual pode continuar disponível pelo campo único. Não exigir versão
   principal nova apenas por adicionar uma operação; registrar a decisão conforme a política v1.

Não há decisão de produto crítica bloqueando o início. O volume real de projetos e a latência da
LAN não foram medidos: validar o mecanismo com fixtures acima de 200 projetos e rede lenta simulada.
Se a UI exigir mais complexidade do que cabe em E02, dividir essa etapa antes de iniciá-la, preservando
os IDs de etapas já executadas e explicitando as novas dependências.

## Definição global de pronto

- [x] A mesma entrada busca, abre e inicia cadastro; nenhum segundo campo permanente disputa essa função.
- [x] Trechos encontram projetos além dos 200 iniciais; NS completa é resolvida exatamente.
- [x] NS existente abre diretamente, inclusive após conflito concorrente; não surge uma duplicata.
- [x] NS ausente só é criada após confirmação e abre com o ID retornado pelo servidor.
- [x] Erros, ambiguidade, respostas atrasadas e ações repetidas não criam nem ativam projeto indevido.
- [ ] Alteração de NS, restauração e painéis dependentes passam nas regressões e no teste manual.
- [ ] Contrato e documentação descrevem o fluxo entregue; validações de E01–E03 foram executadas e aprovadas.


Evidências dos cinco requisitos funcionais em E03 (T1–T3 e percurso nativo). Alteração de NS,
restauração e sincronização passaram nos casos específicos, mas o teste obrigatório de troca de
tema com projeto/PDF ativo falhou na seleção dirigida. Os dois últimos aceites permanecem abertos
até sua resolução e repetição integral das validações; o gate completo aprovado não substitui isso.

## Índice de etapas

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Pesquisa remota por trecho de NS | #concluida | Nenhuma | API e gateway com busca paginada global |
| E02 | Entrada única para buscar, abrir e criar | #concluida | E01 | Fluxo Qt unificado e redirecionamento direto |
| E03 | Integração do fluxo e aceite final | #bloqueada | E01, E02 | Regressões de integração e gate global aprovado |

Execução sequencial: E01 altera gateways e contratos consumidos por E02; E02 e E03 compartilham
testes de UI e documentação. Não há paralelismo de implementação previsto.

## E01 — Pesquisa remota por trecho de NS — #concluida

**Objetivo:** permitir pesquisar em todos os projetos do servidor, sem depender da página já carregada.

**Por que agora:** a UI precisa distinguir sugestões globais de uma lista local incompleta.

**Dependências e paralelismo:** nenhuma; executar antes de E02. Não editar o fluxo visual nesta etapa.

**Escopo:** `src/zeny_project_handler_server/project_api.py`,
`src/zeny_project_handler_server/app.py`, `src/zeny_project_handler_api_spec/app.py`,
`src/zeny_project_handler_client/ui/project_gateway.py`, `tests/remote_gateways.py`,
`tests/server/test_project_document_api.py`, `tests/integration/test_project_http_gateway.py`,
`tests/contracts/test_openapi_snapshot.py`, `docs/api/README.md` e `docs/api/openapi-v1.json`.
Reutilizar DTOs em `src/zeny_project_handler_contracts/projects.py` quando suficientes.

**Fora de escopo:** mudança de esquema SQLite, criação de índice único, saneamento histórico,
mudança da semântica dos endpoints de criação/resolução existentes e widgets.

**Passos de implementação:**

1. Implementar a rota proposta `/projects/search` antes da rota dinâmica `/projects/{project_id}`,
   com autenticação, validação, paginação e envelope de erro compatíveis com o restante da API.
2. Filtrar por trecho de NS antes de contar e paginar; manter ordenação determinística com desempate
   por ID. Reutilizar acesso servidor existente, evitando hidratar todos os projetos a cada consulta
   quando for possível selecionar IDs e contar no SQLite antes da projeção.
3. Adicionar a operação ao protocolo/gateway HTTP e ao gateway direto de testes pertinente.
   Um 404 da rota de pesquisa não pode ser convertido em lista vazia ou ausência exata de NS.
4. Cobrir correspondência, zeros iniciais, entrada inválida, paginação, autenticação e paridade dos
   gateways. Preservar testes de unicidade, idempotência, resolução e ambiguidade já existentes.
5. Atualizar a API declarativa, gerar/revisar o snapshot e documentar semântica e compatibilidade.
   Atualizar expectativas de quantidade de operações no teste de contrato quando necessário.

**Critérios de aceite:**

- [x] Fragmento localiza um projeto fora da primeira página em fixture com mais de 200 projetos.
- [x] `total` conta somente correspondências; offsets consecutivos não repetem IDs com dados estáveis.
- [x] Busca aceita 1–10 dígitos ASCII, preserva zeros e rejeita letras, excesso de tamanho e consulta vazia.
- [x] Sem correspondência retorna lista vazia; erro/autenticação/rota ausente continuam erros distintos.
- [x] Listagem sem pesquisa, resolução exata, conflito e replay mantêm os contratos anteriores.
- [x] Gateway direto e HTTP devolvem resultados equivalentes; snapshot representa a rota real.

**Validação obrigatória:** a partir da raiz, executar:

```powershell
.\.venv\Scripts\python.exe scripts\generate_openapi_v1.py
.\.venv\Scripts\python.exe -m pytest tests/server/test_project_document_api.py tests/integration/test_project_http_gateway.py tests/contracts/test_openapi_snapshot.py tests/contracts/test_models.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

Esperado: saída zero em todos os comandos; diff do snapshot restrito à adição revisada. Os comandos
vêm do README, da documentação da API e do gate existente; não foram executados na criação do plano.

**Bloqueios:** nenhum bloqueio conhecido.

**Riscos e mitigação:** colisão da rota estática com UUID, coberta por teste HTTP; custo de busca por
trecho, mitigado por debounce na próxima etapa e filtragem antes da projeção; servidor antigo,
tratado como recurso indisponível sem falso resultado negativo.

**Compatibilidade e rollback:** alteração aditiva sem migração de dados. Reverter a nova rota requer
restaurar cliente compatível ou manter sua mensagem de indisponibilidade; não remover endpoints
anteriores nem alterar o banco. Nenhuma implantação é autorizada por este roadmap.

**Prompt para uma sessão limpa:**

```text
Execute E01 — Pesquisa remota por trecho de NS — do arquivo docs/roadmap-busca-abertura-cadastro-ns.md, nesta raiz do ZenyProjectHandler. Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, git status, project_api.py e app.py do servidor, a API declarativa, project_gateway.py do cliente, tests/remote_gateways.py e os testes/documentos indicados em E01. Confirme que não há dependências anteriores e que o código não divergiu do contexto. Preserve mudanças preexistentes e limite-se a esta etapa.

Atualize E01 para #em-andamento no índice e no detalhe. Adicione a operação proposta GET /api/v1/projects/search, query de 1–10 dígitos ASCII, limit/offset e DTO de lista existente; filtre por trecho antes de contar/paginar e mantenha ordem determinística. Atualize gateway HTTP, protocolo e gateway direto pertinente. Não mude a UI nem a unicidade já implementada. Garanta busca além dos 200 primeiros projetos, zeros preservados, autenticação, erro separado de ausência, paridade de gateways e regressões de resolução exata, idempotência e concorrência. Registre a compatibilidade aditiva e o comportamento perante rota indisponível; não transforme 404 da pesquisa em NS ausente.

Crie/atualize os testes, a documentação da API e seu snapshot. Execute a geração, Pytest dirigido, Ruff, formatação e Mypy listados em Validação obrigatória de E01. Não declare sucesso com validação obrigatória falhando ou não executada. Só marque #concluida após todos os critérios; se houver impedimento real, marque #bloqueada com causa, evidência, impacto e ação de desbloqueio. Sincronize as tags e preencha Evidências e handoff com arquivos, decisões, comandos e resultados. Não crie commit, publique ou implante sem autorização explícita. Finalize com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — concluída em 10/09/2026:**

- Contexto conferido antes da implementação: sem dependências anteriores, sem divergência impeditiva
  e sem `AGENTS.md` aplicável. Preservados o roadmap sem rastreamento e a exclusão preexistente de
  `docs/roadmap-correcao-interpretacao-topologia-ramais.md`. Nenhum commit, publicação ou implantação.
- Arquivos de implementação: `src/zeny_project_handler_server/project_api.py` e
  `src/zeny_project_handler_server/app.py`; protocolo e HTTP em
  `src/zeny_project_handler_client/ui/project_gateway.py`; gateway direto em `tests/remote_gateways.py`.
  A rota estática precede `/projects/{project_id}` e exige Bearer. O serviço valida trecho/paginação,
  conta e seleciona IDs no SQLite com o mesmo filtro, ordena por `created_at, id` crescentes e
  projeta somente a página. Sem alteração de widgets, esquema, unicidade ou resolução exata.
- Contrato: `GET /api/v1/projects/search`, `query` obrigatório de 1–10 dígitos ASCII,
  `limit` 1–200 (padrão HTTP 50), `offset` não negativo (padrão 0), resposta
  `ProjectSummaryListResponse` existente. Gateways: `search_projects(query, *, limit=200, offset=0)`.
  `total` é filtrado; offset além do fim preserva o total. Zeros não são normalizados.
- API declarativa em `src/zeny_project_handler_api_spec/app.py`, documentação em `docs/api/README.md`
  e snapshot em `docs/api/openapi-v1.json`. Diff revisado: somente 142 linhas adicionadas à nova rota,
  57 operações no total; nenhum schema ou endpoint anterior alterado. Compatibilidade aditiva v1,
  mantendo versão/piso `1.3.0`, sem migração ou novos campos obrigatórios.
- Testes em `tests/server/test_project_document_api.py`: busca fora dos 200 iniciais, parâmetros
  ausentes/inválidos, letras, Unicode, espaços, newline, curingas, limites, zeros, lista vazia,
  offset além do fim e Bearer ausente/incorreto. Regressões existentes de resolução exata,
  ambiguidade histórica, conflito, rename, replay, reinício e criação/upload concorrentes passaram.
- Testes em `tests/integration/test_project_http_gateway.py`: fixture de 205 projetos com três
  correspondências fora da primeira página, trecho no meio da NS, datas empatadas e inserção fora
  da ordem de ID; páginas sem repetição, total filtrado e paridade de DTOs/erros entre gateways.
  HTTP 404 sem envelope, 404 `RESOURCE_NOT_FOUND`, 422 `VALIDATION_ERROR`, 500 e timeout continuam
  `ProjectGatewayError`; nenhuma falha vira ausência. Contrato e snapshot conferidos em
  `tests/contracts/test_openapi_snapshot.py`; DTOs existentes validados por `tests/contracts/test_models.py`.

Comandos executados na raiz e resultados finais:

| Comando | Resultado |
|---|---|
| `.\.venv\Scripts\python.exe scripts\generate_openapi_v1.py` | Exit 0; snapshot gerado e revisado |
| `.\.venv\Scripts\python.exe -m pytest tests/server/test_project_document_api.py tests/integration/test_project_http_gateway.py tests/contracts/test_openapi_snapshot.py tests/contracts/test_models.py --basetemp=tmp/e01-pytest-20260910-01 -o cache_dir=tmp/e01-pytest-cache-20260910-01` | Exit 0; 78 passed em 28,21 s, sem warnings |
| `.\.venv\Scripts\python.exe -m ruff check .` | Exit 0; All checks passed |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | Exit 0; 321 arquivos formatados |
| `.\.venv\Scripts\python.exe -m mypy` | Exit 0; nenhum erro em 306 arquivos |
| `git diff --check` | Exit 0; nenhuma falha de whitespace |

A primeira execução literal do Pytest teve 44 aprovações e 34 erros de setup por `WinError 5`
no diretório `%TEMP%\pytest-of-Caio Cezar Dias`, além de avisos de permissão no cache existente.
Resolvido usando diretórios novos sob `tmp/`, já ignorado pelo Git; mesma seleção, sem desabilitar
testes ou alterar a configuração versionada. O primeiro Ruff apontou quatro caracteres fullwidth
nas fixtures; substituídos por escapes Unicode, mantendo os cenários. Aplicado `ruff format` aos
oito arquivos Python alterados, com nova formatação dos dois testes após essa correção.
As validações acima passaram sobre o código final; nenhum impedimento permanece na E01.

Para E02: consumir o gateway novo sem fallback para os 200 iniciais; campo vazio usa `list_projects()`.
Servidor antigo pode responder 404 ou 422 ao interpretar `search` na rota dinâmica de UUID.
Tratar como pesquisa indisponível; nem erro nem lista vazia autorizam criar. Somente
`find_project_by_service_note()` com ausência exata confirmada decide esse caminho. A resolução exata
pode continuar disponível em servidor antigo. Debounce, workers, mensagens visuais e campo único
permanecem pendentes em E02; páginas são determinísticas para dados estáveis, sem snapshot reservado
entre requisições. E02/E03 e o aceite global não foram executados nesta etapa.

## E02 — Entrada única para buscar, abrir e criar — #concluida

**Objetivo:** entregar o campo único e abrir diretamente a NS existente em qualquer tentativa de cadastro.

**Por que agora:** E01 fornece sugestões remotas sem limitar a existência à primeira página.

**Dependências e paralelismo:** E01 concluída e contrato confirmado. Execução sequencial; E03 depende
do fluxo final e compartilha testes. Helpers novos, se necessários, devem ficar no pacote de UI do
cliente; seus caminhos serão decididos na implementação, sem mover negócio para o cliente.

**Escopo:** `src/zeny_project_handler_client/ui/project_panel.py`, integração estritamente necessária
em `src/zeny_project_handler_client/ui/main_window.py`, `tests/e2e/test_mvp_ui.py`,
`tests/integration/test_window.py`, `tests/unit/test_project_panel_remote_boundary.py`,
`README.md` e `docs/especificacao-funcional.md`.

**Fora de escopo:** reformular os demais painéis, alterar APIs de mutação, renomear ao pesquisar ou
adicionar um novo sistema geral de tarefas assíncronas.

**Passos de implementação:**

1. Usar um único editor para pesquisa e cadastro com ação “Abrir ou criar”. Remover o campo
   permanente duplicado; preservar “Alterar NS” por diálogo específico e seu controle de versão.
2. Consultar sugestões com debounce fora da thread gráfica. Exibir pesquisa em andamento,
   resultados, total/truncamento, ausência de correspondências e erro. Fragmento sem resultado
   não oferece criação até haver uma NS completa resolvida exatamente.
3. Descartar respostas por geração de consulta e contexto de conexão. Limpar seleção vinculada a
   texto antigo; não substituir o que o usuário está digitando quando uma resposta chegar. Encerrar
   workers com o painel e respeitar bloqueios globais sem ativação tardia indevida.
4. Centralizar botão e Enter no mesmo caminho. Para texto completo não selecionado, resolver a NS
   exata; se existir, ativar diretamente; se faltar, confirmar a criação com a NS exibida. Uma
   sugestão selecionada mantém seu ID remoto; não escolher o primeiro resultado implicitamente.
5. No POST, bloquear disparos repetidos. Em `PROJECT_ALREADY_EXISTS`, abrir diretamente o ID
   seguro do conflito, sem novo POST ou diálogo de duplicidade. Se o detalhe do conflito não
   permitir identificar o projeto, admitir apenas resolução exata de leitura ou mostrar erro.
6. Reutilizar ativação/limpeza canônicas. Preservar a limpeza na recusa de criação, a sessão ao
   cancelar alteração de NS e o fluxo de erro sem mutação. Atualizar “Como usar”, README,
   especificação e testes antigos que exigem dois campos ou confirmação para abrir duplicidade.

**Critérios de aceite:**

- [x] Uma única entrada visível recebe NS para buscar, abrir ou criar; botão e Enter são equivalentes.
- [x] Digitar não cria, renomeia ou troca o projeto ativo; pesquisa parcial remota apresenta resultados.
- [x] NS completa existente, inclusive fora dos 200 iniciais, abre sem diálogo e sem POST.
- [x] NS ausente exibe a confirmação correta, faz um POST após aceitar e ativa o ID retornado.
- [x] Conflito concorrente abre o projeto vencedor; clique/Enter repetidos não duplicam requisições.
- [x] Erro de consulta e integridade ambígua nunca são tratados como ausência ou sucesso.
- [x] Resposta antiga não muda sugestões, disponibilidade de criação ou projeto ativo da consulta atual.
- [x] Alterar NS continua disponível só com projeto ativo; cancelar não renomeia nem limpa a sessão.
- [x] Teclado, foco, zeros iniciais, bloqueios e limpeza na recusa mantêm comportamento verificável.
- [x] Recusa e troca sincronizam visualizador, serviços e os demais painéis pelo mecanismo existente.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_mvp_ui.py tests/integration/test_window.py tests/unit/test_project_panel_remote_boundary.py tests/integration/test_client_reconnection.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
```

Esperado: todos aprovados. Usar fixtures e controles determinísticos de respostas atrasadas, sem
depender de sleeps longos. Inspecionar manualmente o painel nos temas claro/escuro e em largura
reduzida: campo, status e ação legíveis, navegação por Tab/setas/Enter e diálogo de alteração sem
segundo campo permanente. Usar ambiente de teste com dados sintéticos; não alterar servidor de produção.

**Bloqueios:** nenhum bloqueio conhecido; E01 concluída com contrato e evidências acima.

**Riscos e mitigação:** sinais Qt duplicados, teste de uma ação/um POST; resposta fora de ordem,
identidade de consulta/contexto; descarte de thread, teste de fechamento; remoção de `_service_note`,
revisão de todos os usos para preservar alteração e reset; confirmação de criação com texto alterado,
vincular a intenção à NS apresentada e invalidar confirmações obsoletas.

**Prompt para uma sessão limpa:**

```text
Execute E02 — Entrada única para buscar, abrir e criar — de docs/roadmap-busca-abertura-cadastro-ns.md. Leia primeiro instruções do repositório, roadmap completo, git status, project_panel.py, main_window.py, project_gateway.py, testes de UI e documentação listados na etapa. Verifique E01 concluída com evidências, contrato implementado e eventuais divergências do código. Preserve mudanças preexistentes e não execute outras etapas.

Marque E02 #em-andamento no índice e no detalhe. Torne o seletor editável a única entrada para pesquisar/cadastrar NS, com ação Abrir ou criar e Enter equivalente. Use sugestões remotas com debounce e trabalho fora da thread gráfica; apresente estados e descarte respostas obsoletas, inclusive após reconexão/fechamento. Digitar não pode criar nem ativar projeto. NS completa existente deve abrir diretamente sem POST ou pergunta; NS ausente precisa de resolução exata e confirmação explícita antes de um único POST. Conflito PROJECT_ALREADY_EXISTS deve abrir diretamente o projeto existente sem repetir POST; erro e ambiguidade nunca significam ausência. Preserve IDs, zeros, bloqueios e sincronização dos painéis. Mova Alterar NS para diálogo específico, preservando versão e sessão no cancelamento; mantenha limpeza local na recusa de criação conforme o roadmap.

Atualize os testes necessários, o guia Como usar, README e especificação funcional com o comportamento final. Execute todos os comandos e a inspeção manual da Validação obrigatória de E02; teste atrasos de resposta e disparos repetidos deterministicamente. Não declare sucesso com validações obrigatórias falhando ou não executadas. Marque #concluida apenas após aceite; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Sincronize as tags e preencha Evidências e handoff com arquivos, decisões, comandos, resultados e observações de UI. Não crie commit, publique ou implante sem autorização explícita. Finalize com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — concluída em 10/09/2026:**

- Entrada conferida: Git limpo, nenhum `AGENTS.md` aplicável encontrado na hierarquia ou no
  repositório. Lidos roadmap, painel/gateway, integração da janela, testes e documentação do fluxo.
  E01 confirmada pelo contrato implementado no protocolo/HTTP/gateway direto, rota filtrada antes
  da paginação e evidências anteriores de 78 testes, snapshot, Ruff e Mypy. As validações de E01
  não foram apresentadas como novas execuções nesta etapa; não houve alteração de API ou servidor.
- Implementação: `src/zeny_project_handler_client/ui/project_panel.py` e novo helper
  `src/zeny_project_handler_client/ui/project_search.py`. Mantidos `mvpProjectCombo` e
  `mvpOpenProjectButton` (agora **Abrir ou criar**); editor único `mvpProjectSearchEdit`, status
  `mvpProjectSearchStatus`, diálogo `mvpRenameServiceNoteDialog` e editor transitório
  `mvpRenameServiceNoteEdit`. Removidos `mvpProjectNameEdit`, `mvpCreateProjectButton` e o diálogo
  de abertura de duplicidade. O título do grupo informa a NS ativa enquanto outra NS é pesquisada.
- Sugestões: debounce de 300 ms; campo vazio lista, trecho usa `search_projects(limit=200, offset=0)`.
  Uma leitura em voo por painel, coalescendo consultas intermediárias. O callable do gateway é
  capturado antes de iniciar a QThread; texto, cursor/seleção, geração e contexto são preservados.
  Estados: aguardando, pesquisando, resultados/total, refinamento, nenhuma correspondência e
  indisponibilidade. Nenhuma primeira sugestão é selecionada automaticamente; editar remove o ID
  vinculado ao texto anterior. A carga inicial/atualização explícita da lista e o CRUD mantêm o
  caminho síncrono existente; as consultas disparadas pela digitação são executadas fora da UI.
- Fechamento/desconexão invalidam consultas e confirmações e solicitam interrupção do worker.
  Uma leitura HTTP já em voo não é terminada à força: pode concluir pelo timeout/retry de leitura
  já definido no gateway. A thread sem parent de widget é retida até terminar, não acessa widgets
  no trabalho remoto e descarta entregas obsoletas. A consulta mais recente aguarda a leitura
  anterior terminar, sem bloquear a thread gráfica. Não existe retry automático de `POST`.
- Divergência relevante encontrada na integração: o proxy reconectável emitia perda de conexão
  por falha de qualquer alvo antigo. Ajuste restrito em `src/zeny_project_handler_client/connection.py`:
  a entrega da falha na thread Qt verifica se o alvo ainda é o vigente, inclusive quando o sinal
  já estava enfileirado durante a reconexão. Dois testes determinísticos em
  `tests/integration/test_client_reconnection.py` cobrem erro após substituição e erro já enfileirado;
  falhas do alvo vigente continuam bloqueando a conexão.
- Ação única: ID explicitamente selecionado ou resolução exata dos dez dígitos. Existente abre sem
  pergunta/POST; ausência exata pede confirmação exibindo a NS e padrão **Não**. Guarda de ação
  cobre modal, criação e sinais duplicados de Enter no mesmo evento Qt. A confirmação é invalidada
  mesmo ao editar e voltar ao texto original. Conflito abre o ID seguro; sem ID válido, somente
  resolução exata de leitura. Ausência ou ambiguidade nessa leitura não repete `POST`.
- Alterar NS usa diálogo com **Alterar NS**/**Cancelar**, validação ASCII e a versão da sessão.
  Cancelamento preserva a mesma sessão/versão; colisão não troca nem mescla projetos. A abertura
  reutiliza ativação canônica e sincroniza Resultados antes de restaurar a folha salva. Restauração
  consulta o ID salvo diretamente, sem depender de estar na lista inicial. A recusa remove seleção,
  sessão e `last_project_id` e emite a limpeza canônica. `main_window.py` foi inspecionado; seus
  sinais existentes atendem à sincronização, sem necessidade de editar a janela.
- Testes: `tests/e2e/test_mvp_ui.py` cobre 201 projetos, busca remota, abertura exata fora da página
  sem POST/pergunta, zeros, ID residual, total 200/201, lista vazia, timeout, 401/404/422/500,
  ambiguidade, conflitos com/sem ID, um POST apesar de disparos repetidos, invalidadores de
  confirmação, atrasos com `threading.Event`, reconexão/fechamento, versão/cancelamento/colisão
  da alteração, recusa e painéis. `tests/integration/test_window.py` migra a regressão de clipboard
  para o campo único; `tests/unit/test_project_panel_remote_boundary.py` inclui o novo helper.
  A remoção de controles exigiu adaptar apenas os helpers de criação em
  `tests/e2e/test_span_compliance_ui.py` e `tests/integration/test_protected_pdf_ui.py`, com confirmação
  explícita nas fixtures e espera pelo fim da ação; nenhuma regra desses fluxos foi alterada.
- Documentação final: guia **Como usar** do painel, `README.md` e `docs/especificacao-funcional.md`.

Comandos finais executados na raiz:

| Comando | Resultado |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/e2e/test_mvp_ui.py tests/integration/test_window.py tests/unit/test_project_panel_remote_boundary.py tests/integration/test_client_reconnection.py --basetemp=tmp/e02-acceptance-15 -o cache_dir=tmp/e02-cache-15` | Exit 0; 52 passed em 66,70 s, sem warnings |
| `.\.venv\Scripts\python.exe -m ruff check .` | Exit 0; All checks passed |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | Exit 0; 322 arquivos formatados |
| `.\.venv\Scripts\python.exe -m mypy` | Exit 0; nenhum erro em 307 arquivos |
| `.\.venv\Scripts\python.exe -m pytest tests/e2e/test_span_compliance_ui.py tests/integration/test_protected_pdf_ui.py --basetemp=tmp/e02-adapted-12 -o cache_dir=tmp/e02-cache-12` | Exit 0; 3 passed em 9,93 s |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_client_connection.py --basetemp=tmp/e02-connection-13 -o cache_dir=tmp/e02-cache-13` | Exit 0; 7 passed em 0,23 s |
| `$env:QT_QPA_PLATFORM = 'windows'` seguido de `.\.venv\Scripts\python.exe -m pytest tmp/e02_visual_inspection.py --basetemp=tmp/e02-visual-native-14 -o cache_dir=tmp/e02-cache-14` | Exit 0; 1 passed em 6,08 s, sem warnings; capturas e navegação Qt nativa |
| `git diff --check` | Exit 0; sem falhas de whitespace |

A execução literal do Pytest obrigatório também foi tentada: 1 passed, 48 erros de setup e dois
avisos de cache por `WinError 5` em `%TEMP%\pytest-of-Caio Cezar Dias` e no cache preexistente.
Resolvido com diretórios novos sob `tmp/`, mantendo a seleção completa e a configuração versionada.
Na primeira rodada funcional houve duas regressões, corrigidas e revalidadas: ID residual na recusa
e perda da folha salva pela atualização de Resultados. Uma expectativa antiga de lista estática foi
ajustada para aguardar a pesquisa remota. Ruff/formatação intermediários foram corrigidos; os
resultados da tabela correspondem à validação final (a última formatação só ajustou concatenação
de strings, sem mudança de comportamento).

Inspeção visual manual das capturas dos widgets Qt reais, com fixtures sintéticas e plataforma
`windows`: `tmp/e02-ui/claro-janela.png`, `escuro-janela.png`, `claro-inicial.png`,
`escuro-inicial.png`, `claro-estreito.png`, `escuro-estreito.png`, `escuro-sem-correspondencia.png`,
`claro-alterar-ns.png` e `escuro-alterar-ns.png`; observações em `tmp/e02-ui/observacoes.txt`.
Campo, status, ação e diálogo legíveis nos dois temas, sem segundo campo permanente de NS;
conferidas janela normal e largura reduzida de 340 px. O título mantém a NS ativa enquanto `999`
não encontra correspondências. Eventos Qt de teclado verificaram: digitar `0007` só pesquisa;
seta para baixo seleciona sem ativar; Enter abre o ID correto; Tab leva à ação; Escape no diálogo
preserva sessão nos dois temas. A primeira captura `offscreen` não tinha fontes utilizáveis e o
foco do dock flutuante não estava ativo: foi descartada e substituída pelas capturas nativas.
Observação fora dos controles de E02: em altura restrita, o texto auxiliar de **Folhas PDF** pode
ficar cortado verticalmente; não houve reformulação desse bloco. As evidências e o harness em
`tmp/` são locais/ignorados, não constituem arquivos de distribuição.

Nenhum impedimento permanece para os critérios de E02. E03 e o gate global `IniciarTestes.bat`
continuam pendentes e não foram executados; a composição Qt + HTTP completa e o aceite global
pertencem à próxima etapa. Nenhum commit, publicação, implantação ou alteração em produção.

## E03 — Integração do fluxo e aceite final — #bloqueada

**Objetivo:** comprovar que busca, ativação e criação funcionam juntas através do servidor real de
teste e mantêm todos os painéis coerentes em concorrência, reconexão e restauração.

**Por que agora:** E01 valida o contrato e E02 valida a UI; o aceite precisa cobrir a composição de
ambos, além dos gateways diretos usados em parte dos testes existentes.

**Dependências e paralelismo:** E01 e E02 concluídas, com evidências. Sem execução paralela.

**Escopo:** `tests/integration/test_project_http_gateway.py`,
`tests/integration/test_client_reconnection.py`, `tests/integration/test_window.py`,
`tests/e2e/test_mvp_ui.py`, `tests/server/test_project_document_api.py`; correções restritas ao fluxo
alterado em E01/E02 e revisão de `README.md`, `docs/especificacao-funcional.md`, `docs/api/README.md`.

**Fora de escopo:** adicionar funcionalidades, corrigir problemas independentes do roadmap, executar
smokes de SQL Server ou exemplos privados, build de release, publicação e implantação.

**Passos de implementação:**

1. Reutilizar fixtures de servidor HTTP e aplicação Qt existentes para cobrir o campo único contra
   a API real de teste. Complementar apenas lacunas entre E01/E02; evitar duplicar testes equivalentes.
2. Verificar dois clientes concorrentes: ambos observam ausência, só um cria, o outro recebe
   conflito e abre o mesmo ID. Usar barreiras/eventos determinísticos; não presumir a ordem pela latência.
3. Exercitar troca de projeto, restauração fora da primeira página e reconexão com pesquisa em
   andamento. Corrigir exclusivamente resíduos de seleção, requisição ou painéis decorrentes do fluxo.
4. Aplicar a matriz abaixo, revisar a documentação final e executar o gate padrão completo.

**Critérios de aceite e matriz integrada:**

- [x] Base com mais de 200 projetos: fragmento encontra NS fora da página inicial e a ação abre seu ID.
- [x] NS nova: pesquisa/GETs sem mutação; confirmação faz um POST e mantém exatamente um cadastro.
- [x] Dois clientes: um projeto persistido, ambos terminam no mesmo ID, nenhum retry de criação.
- [x] Projeto A ativo, busca por B: digitação mantém A; confirmação de abertura troca todos os painéis para B.
- [x] Texto editado após selecionar A não abre A por um ID residual; resposta de A não sobrescreve busca por B.
- [x] Timeout, 401, rota de pesquisa indisponível e ambiguidade não oferecem falsa ausência nem POST.
- [x] Recusar criação limpa sessão/painéis/last_project_id sem mutação no servidor.
- [x] Alteração de NS preserva controle de versão e rejeita colisão sem alterar os dois projetos.
- [x] Restauração abre o último projeto válido mesmo fora da primeira página; ID removido é tratado sem sessão residual.
- [x] Reconexão/fechamento descartam respostas antigas; bloqueio global continua impedindo ações incompatíveis.
- [ ] Gate completo aprovado e definição global de pronto integralmente satisfeita. **Parcial:** gate aprovado; seleção dirigida obrigatória reprovada (bloqueio abaixo).

**Validação obrigatória:** executar os testes dirigidos antes do gate para diagnosticar regressões:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_project_http_gateway.py tests/integration/test_client_reconnection.py tests/integration/test_window.py tests/e2e/test_mvp_ui.py tests/server/test_project_document_api.py
.\IniciarTestes.bat
```

Esperado: todos aprovados; `IniciarTestes.bat` retorna zero e informa aprovação de dependências,
Ruff, formatação, Mypy, fronteira do cliente, Pytest com cobertura mínima de 85,01% e complexidade.
Registrar resultados a partir de `relatorio-testes.txt`, que é ignorado pelo Git. O script usa
temporários sob `%SystemDrive%\tmp`; se o ambiente impedir uma validação obrigatória, registrar o
impedimento e a ação para liberar um ambiente de teste adequado, sem declarar a etapa concluída.

Repetir manualmente o percurso central em Qt: pesquisar existente, abrir, pesquisar nova, recusar,
criar após aceitar e alterar NS pelo diálogo. Confirmar visualizador, Serviços, Resultados,
Documentação/conformidade, GMAX e Exportar com o mesmo projeto. A inspeção requer ambiente de teste
disponível; o lançador integrado documentado é efêmero e exige Docker e SQL Server configurados.
Preferir a aplicação com fixtures sintéticas usada nos testes para não depender dessas integrações.

**Bloqueio de aceite B01 — regressão obrigatória de tema/visualizador:**

- **Causa constatada:** o teste `test_theme_switch_preserves_project_pdf_callout_zoom_selection_and_wrap_toggles`
  falha na seleção dirigida e isoladamente, inclusive no HEAD anterior a E03. O centro horizontal
  do visualizador muda de 358,857 para 300 ao trocar o tema (tolerância ±30). A causa técnica
  dessa diferença e da aprovação na suíte completa ainda não foi isolada; não atribuir somente
  ao sandbox ou a E03.
- **Evidência:** `tests/integration/test_window.py:372`; `tmp/e03-theme.log`, reprodução do HEAD
  `311ebefc15d710c59eeadab99135cd5a969625be` em `tmp/e03-baseline-result.log` e repetição literal
  fora do sandbox em `tmp/e03-directed-final.log`: **1 failed, 94 passed, exit 1**. O gate completo
  em `relatorio-testes.txt` passou com 994 testes/87,13%, mas não elimina a falha dirigida.
- **Impacto:** os dez critérios funcionais de E03 têm evidência; o aceite obrigatório e a definição
  global de pronto não estão integralmente satisfeitos. E03 não pode ser declarada concluída.
- **Desbloqueio:** investigar a dependência de ordem/estado Qt desse teste comparando execução
  isolada, dirigida e completa no mesmo ambiente, incluindo fontes, layout e eventos pendentes;
  corrigir a fixture ou o defeito identificado no escopo apropriado, sem relaxar tolerância ou
  excluir teste. Depois executar novamente a seleção literal de E03 e `IniciarTestes.bat` completo,
  registrar ambos com exit 0 e só então sincronizar a conclusão. Mudanças independentes no
  visualizador/tema não foram feitas por estarem fora deste roadmap.

**Riscos e mitigação:** suíte ampla pode revelar falha preexistente; comparar evidências e separar
causa sem expandir escopo, mantendo o gate como pendência até resolução. Teste só com gateway direto
pode esconder contrato incorreto; exigir ao menos um percurso Qt com gateway HTTP e servidor de teste.

**Prompt para uma sessão limpa:**

```text
Execute E03 — Integração do fluxo e aceite final — de docs/roadmap-busca-abertura-cadastro-ns.md. Leia primeiro instruções do repositório, roadmap, git status, evidências de E01/E02, implementação final do painel/gateway/API e testes de integração/e2e indicados. Confirme dependências realmente concluídas e ausência de divergências impeditivas. Preserve alterações preexistentes, não amplie o escopo e marque E03 #em-andamento no índice e detalhe ao iniciar.

Comprove a composição da UI Qt com gateway HTTP e servidor de teste: campo único, busca além dos 200 projetos, abertura direta de NS existente e criação confirmada. Complete apenas lacunas de regressão, incluindo dois clientes criando a mesma NS com um único projeto persistido e abertura do mesmo ID, ausência de POST repetido, respostas fora de ordem, erros distintos de ausência, troca e limpeza de todos os painéis, alteração de NS com controle de versão, restauração fora da primeira página e reconexão/fechamento. Use fixtures sintéticas e sincronização determinística; não dependa de SQL Server, PDFs privados ou produção. Corrija apenas defeitos do fluxo deste roadmap e revise a documentação correspondente.

Execute os comandos e o percurso manual de Validação obrigatória de E03, incluindo IniciarTestes.bat completo. Preencha cada critério da matriz e a definição global de pronto com evidências. Não declare sucesso com teste obrigatório falhando ou não executado, nem substitua o gate completo por validação parcial. Marque #concluida somente após todos os aceites; se houver impedimento real, marque #bloqueada com causa, evidência, impacto e ação de desbloqueio. Sincronize tags e registre arquivos, decisões, comandos, resultados, cobertura e inspeção manual em Evidências e handoff. Não crie commit, publique ou implante sem autorização explícita. Finalize com resumo conciso do resultado, validações e pendências.
```

**Evidências e handoff — implementação validada, aceite bloqueado em 10/09/2026:**

- Entrada conferida: Git limpo no HEAD `311ebefc15d710c59eeadab99135cd5a969625be`;
  nenhum `AGENTS.md` aplicável na hierarquia ou no repositório. Lidos roadmap completo,
  evidências de E01/E02, README/especificação/API, painel/helper de busca, gateway HTTP,
  servidor, composição da janela e testes indicados. E01/E02 realmente concluídas: rota,
  validação, paginação, resolução exata, unicidade, campo único, debounce e invalidadores
  presentes. Nenhuma divergência impeditiva de dependência. E03 foi marcada em andamento
  no índice e no detalhe antes das alterações; nenhuma mudança preexistente precisou ser movida.
- Regressões acrescentadas somente em `tests/integration/test_project_http_gateway.py`:
  **T1** = `test_qt_http_search_open_create_switch_rename_and_restore`;
  **T2** = `test_two_qt_http_clients_observe_absence_then_open_one_persisted_project`;
  **T3** = `test_qt_http_delayed_search_cannot_cross_input_or_connection_context`
  (`edit`, `reconnect`, `close`). São cinco casos novos. Todos os painéis usam gateways HTTP
  reais contra Uvicorn em loopback/porta efêmera e SQLite isolado. A fixture semeia 201 projetos,
  acrescenta B fora da página e produz PDFs públicos sintéticos com item do catálogo; as
  análises usam classificador de mercado fake, sem SQL Server ou PDFs privados.
- T1 registra métodos, caminhos e status HTTP. A busca de trecho é somente GET, mantém A
  ativo, encontra B entre 202 projetos e abre seu ID sem POST/pergunta. Verifica Serviços,
  visualizador, sessão de Resultados, Documentação, GMAX, Exportar e preferências; recusa limpa
  tudo sem mutação. A confirmação com reentrada/Enter produz exatamente um POST 201 e total
  203. Reabrir B e criar um projeto sem análise também verifica ausência de dados residuais.
  O diálogo de alteração rejeita colisão e versão obsoleta; após recarga incrementa a versão
  uma vez. Reabrir a janela restaura B fora dos 200; remover B no servidor e restaurar limpa
  sessão e `last_project_id`.
- T2 usa a confirmação modal como barreira determinística entre duas janelas Qt: os dois
  GETs reais de resolução retornam 404 antes de qualquer POST. A segunda janela confirma e
  vence enquanto a primeira espera; depois a primeira recebe o conflito real. Resultado:
  dois POSTs, um por cliente, chaves distintas, status 201/409, um projeto persistido, ambos
  no mesmo ID, nenhuma pergunta de duplicidade e nenhum retry. A simultaneidade dos POSTs
  no servidor também permanece coberta por
  `test_two_concurrent_project_creations_publish_only_one_service_note`.
- T3 retém a resposta HTTP de `111` com `threading.Event`, libera-a somente após editar para
  `222`, reconectar ou fechar, e usa esperas por condição/evento. A consulta antiga não troca
  texto, sugestões ou projeto; a nova devolve somente B, sem seleção implícita. Bloqueio global
  impede a ação. Mantidas as regressões complementares de E02 para entrega Qt já enfileirada,
  invalidadores de confirmação, erro de gateway antigo, timeout, 401/404/422/500, ambiguidade
  e conflito sem ID seguro; não foram duplicadas com novos mocks equivalentes.
- Defeitos reproduzidos por T1 e corrigidos dentro do fluxo: Exportar mantinha A ao abrir B
  fora da primeira página; Resultados/Documentação podiam reter a sessão de A ao abrir uma NS
  sem análise. `portability_panel.py` limpa a seleção e busca detalhe/versão pelo ID ausente
  da lista; `portability_gateway.py` e `tests/remote_gateways.py` reutilizam o GET de detalhe
  existente, sem novo endpoint/schema. `review_panel.py` limpa a sessão antes da abertura e
  resolve por ID quando ausente da lista; `documentation_panel.py` limpa antes da troca.
  O gateway direto de revisão passou a traduzir `ApiError` em `ReviewGatewayError` nessa
  leitura, assim como a fronteira HTTP. Nenhuma regra de interpretação/conformidade foi alterada.
- Documentação revisada: `README.md`, `docs/especificacao-funcional.md`, `docs/api/README.md`
  e este roadmap. API, snapshot e servidor de produção não foram modificados.

**Matriz de aceite com evidência:**

| Critério | Evidência verificável |
|---|---|
| Mais de 200 projetos e abertura do ID encontrado | T1: B excluído da listagem inicial, fragmento `123456` retorna B; Enter abre B; percurso nativo com 202 projetos |
| NS nova, GETs sem mutação e um POST confirmado | T1: métodos somente GET antes da confirmação, recusa sem POST, confirmação/reentrada com um 201 e total 203; captura manual da confirmação |
| Dois clientes, um cadastro e nenhum retry | T2: dois 404 antes dos POSTs, chaves distintas, 201/409, um ID persistido e ativo nas duas janelas; concorrência real no teste de servidor existente |
| Digitar B preserva A; abrir troca os painéis | T1 e `_assert_http_panels`: IDs, sessões, Serviços e preferências; inspeção nativa de Resultados, Documentação, GMAX e Exportar |
| Sem ID residual ou resposta antiga aplicada | T1 edita a sugestão selecionada antes de recusar/criar; T3 e testes de debounce/geração de E02 descartam a entrega antiga |
| Erros distintos de ausência | Testes `test_http_search_errors_never_become_absence`, `test_project_gateway_retries_reads_but_never_mutations`, `test_search_error_and_exact_error_never_authorize_creation`, `test_search_timeout_allows_exact_open_but_global_operation_blocks_the_action`, resolução ambígua do servidor; todos no gate |
| Recusa limpa sessão/painéis/preferência sem mutação | T1 e percurso nativo: sessão/seleção/folhas/serviços vazios, revisão/documentação sem sessão, GMAX sem ID, Exportar sem seleção, `last_project_id` removido e nenhum POST |
| Alterar NS preserva versão e rejeita colisão | T1: colisão sem mudar A/B, escrita obsoleta rejeitada, recarga e incremento de versão; teste do diálogo em E02 e alteração nativa `0000000777` → `0000000778` |
| Restauração fora da página e ID removido | T1 com fechamento/reabertura e remoção remota; inspeção nativa de restauração da NS `0000000778`, mesmo ID e Exportar sincronizado |
| Reconexão/fechamento e bloqueio global | T3 nos três contextos; testes existentes de reconexão autenticada, gateway substituído e sinal já enfileirado; nenhuma criação/ativação indevida |
| Gate e definição global de pronto | **Bloqueado (B01):** gate completo 994 passed/87,13%, todas as seções exit 0; seleção literal obrigatória 94 passed/1 failed. Não há aceite global |

**Definição global de pronto — vínculo com as evidências:** entrada única = T1/inspeção Qt;
consulta global/exata = T1/E01; existente/conflito = T1/T2; criação confirmada = T1/T2/percurso
nativo; erros/ambiguidade/atrasos/repetição = regressões E01/E02 + T2/T3; alteração/restauração/
painéis = T1 e inspeção nativa; contrato/documentação/qualidade = snapshot/contratos no gate,
documentação revisada e resultados abaixo. Os cinco primeiros requisitos globais estão comprovados;
os dois últimos permanecem abertos por B01. Nenhuma validação falha foi substituída pelo gate completo.

**Comandos e resultados:**

| Comando na raiz | Resultado/evidência |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/integration/test_project_http_gateway.py -k 'test_qt_http or test_two_qt' --basetemp=tmp/e03-fixes -o cache_dir=tmp/e03-cache --tb=short` | Exit 0; 2 passed em 19,29 s após correções de fluxo; `tmp/e03-target.log` |
| Seleção obrigatória de cinco arquivos com `--basetemp=tmp/e03-directed2 -o cache_dir=tmp/e03-cache --tb=short` | No sandbox: exit 1, 94 passed e 1 failed em 136,32 s; `tmp/e03-directed2.log` |
| `.\IniciarTestes.bat` (primeira execução, sandbox) | Exit 1; 577 passed, 417 erros de setup por WinError 5 em `C:\tmp\zph-basic-3038`, 2 avisos, cobertura 49,84%; também faltava formatar `tests/remote_gateways.py`, corrigido. Relatório preservado em `tmp/e03-gate-first.txt`; não utilizado como aceite |
| `.\IniciarTestes.bat` (repetição integral fora do sandbox) | Exit 0, **APROVADO**; **994 passed em 347,78 s**, sem warnings; **87,13%** de cobertura com ramos, piso 85,01%; `relatorio-testes.txt` e `tmp/e03-gate-console2.log` |
| Seções internas do gate completo | `pip check`, Ruff, formatação (322 arquivos), Mypy (307 arquivos), `client_artifact_gate.py --source-only`, Pytest/cobertura e `complexity_gate.py src`: todos exit 0; 2660 funções/métodos, nenhum E/F |
| `.\.venv\Scripts\python.exe -m pytest tests/integration/test_project_http_gateway.py tests/integration/test_client_reconnection.py tests/integration/test_window.py tests/e2e/test_mvp_ui.py tests/server/test_project_document_api.py` | **Exit 1; 94 passed, 1 failed em 118,25 s**, sem warnings; falha B01 persistiu fora do sandbox. `tmp/e03-directed-final.log` |
| `.\.venv\Scripts\python.exe -m tmp.e03_manual` e `.\.venv\Scripts\python.exe -m tmp.e03_manual_restore` | Aplicação nativa `windows`, servidor loopback sintético; percurso manual e restauração executados, janelas/servidores encerrados |
| `git diff --check` | Exit 0; sem erros de whitespace |

**Diagnóstico, tentativas anteriores e limitação pendente:**

- A primeira seleção dirigida foi interrompida após detectar exceção não traduzida no gateway
  direto de revisão; a tradução foi corrigida e toda a seleção reexecutada. As primeiras rodadas
  de T1 identificaram Exportar residual e sessão de Resultados residual; foram corrigidas, não
  consideradas aprovações parciais. O PDF inicialmente só gráfico não produzia resultados de
  revisão; a fixture final usa texto sintético do catálogo para verificar sessões reais.
- No sandbox, `test_theme_switch_preserves_project_pdf_callout_zoom_selection_and_wrap_toggles`
  falhou em `tests/integration/test_window.py:372` (centro X 300 contra 358,857 ± 30), junto de
  aviso de fontes Qt indisponíveis. Reproduzido no HEAD intacto por `git archive` em
  `tmp/e03-baseline`, com `PYTHONPATH` apontando para seu `src`; comando do teste isolado e
  resultado em `tmp/e03-baseline-result.log`. Não se alterou visualizador/tema nem tolerância.
  A mesma regressão passou na execução integral fora do sandbox, mas voltou a falhar na seleção
  literal dirigida também fora dele. B01 permanece pendente; a diferença entre seleções não foi
  atribuída ao código de E03 nem resolvida pela troca de ambiente.
- O gate foi repetido integralmente com acesso aos temporários exigidos pelo próprio script;
  não houve edição do `.bat`, redução de seleção, retirada de gate ou redução de cobertura.
  A primeira janela nativa lançada no sandbox não era visível ao controle de desktop; o ambiente
  sintético foi relançado na sessão interativa, sem mudar arquivos ou dados reais do usuário.

**Inspeção manual nativa:** realizada com `computer-use` sobre a janela
**E03 — Aceite Qt HTTP — dados sintéticos**, Qt 6.11.1, tema claro, cerca de 1500 × 1000 px.
Campo único, status e ação legíveis; sem segundo campo permanente. Digitado `123456`, observado
um resultado `0012345678` fora da primeira página sem ativação; seta e Enter abriram diretamente
PDF/Resultados. Visitadas Documentação/conformidade, GMAX e Exportar: mesma NS do projeto.
Digitado `0000000777`, confirmado que o anterior permanece ativo; diálogo mostra a NS inteira e
recusa padrão. Escape recusou e limpou visualizador/painéis/preferência sem POST. Repetida a NS,
selecionado **Yes** e confirmado: um POST 201 abriu o cadastro. **Alterar NS** exibiu editor
transitório preenchido; digitação de `0000000778` e Enter enviaram um PATCH 200, mantendo o ID
`b6e9aa6f-c8b1-5cff-b247-04678006392e`, inclusive em Exportar. Resultados e Documentação vazios
foram conferidos visualmente. GMAX sem análise apresentou indisponibilidade e removeu os dados
anteriores, comportamento existente do endpoint; não houve consulta SQL. Fechada e reaberta a
aplicação/servidor, a NS alterada foi restaurada pelo mesmo ID fora dos 200, com Exportar correto.

Evidências locais ignoradas: harnesses `tmp/e03_manual.py`, `tmp/e03_manual_restore.py`, 17 estados
em `tmp/e03-manual-02/states.json`, capturas `state-01.png` a `state-17.png`, requisições em
`requests.json` e `restauracao.txt`; inspeções das abas e dos diálogos também foram realizadas
pelas capturas do controle nativo. O registro HTTP separa os POSTs de preparação da fixture
(projeto, PDF e análise) do único POST de cadastro manual e do PATCH. Nenhum uso de SQL Server,
PDFs privados, produção, commit, publicação, build de release ou implantação.

**Handoff final:** dez arquivos alterados (quatro documentos, quatro arquivos de UI/gateway,
`tests/integration/test_project_http_gateway.py` e `tests/remote_gateways.py`). Ruff, formatação,
Mypy, fronteira do cliente, contratos, cobertura e complexidade aprovados no gate completo;
inspeção manual e cinco novos casos HTTP aprovados. Pendência única de aceite: B01 na seleção
dirigida, sem modificação do teste preexistente ou do visualizador/tema. Índice/detalhe em
`#bloqueada`; não há outra etapa em andamento. Nenhum commit, publicação ou implantação.
