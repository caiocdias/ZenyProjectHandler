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

- [ ] A mesma entrada busca, abre e inicia cadastro; nenhum segundo campo permanente disputa essa função.
- [ ] Trechos encontram projetos além dos 200 iniciais; NS completa é resolvida exatamente.
- [ ] NS existente abre diretamente, inclusive após conflito concorrente; não surge uma duplicata.
- [ ] NS ausente só é criada após confirmação e abre com o ID retornado pelo servidor.
- [ ] Erros, ambiguidade, respostas atrasadas e ações repetidas não criam nem ativam projeto indevido.
- [ ] Alteração de NS, restauração e painéis dependentes passam nas regressões e no teste manual.
- [ ] Contrato e documentação descrevem o fluxo entregue; validações de E01–E03 foram executadas e aprovadas.

## Índice de etapas

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Pesquisa remota por trecho de NS | #concluida | Nenhuma | API e gateway com busca paginada global |
| E02 | Entrada única para buscar, abrir e criar | #pendente | E01 | Fluxo Qt unificado e redirecionamento direto |
| E03 | Integração do fluxo e aceite final | #pendente | E01, E02 | Regressões de integração e gate global aprovado |

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

## E02 — Entrada única para buscar, abrir e criar — #pendente

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

- [ ] Uma única entrada visível recebe NS para buscar, abrir ou criar; botão e Enter são equivalentes.
- [ ] Digitar não cria, renomeia ou troca o projeto ativo; pesquisa parcial remota apresenta resultados.
- [ ] NS completa existente, inclusive fora dos 200 iniciais, abre sem diálogo e sem POST.
- [ ] NS ausente exibe a confirmação correta, faz um POST após aceitar e ativa o ID retornado.
- [ ] Conflito concorrente abre o projeto vencedor; clique/Enter repetidos não duplicam requisições.
- [ ] Erro de consulta e integridade ambígua nunca são tratados como ausência ou sucesso.
- [ ] Resposta antiga não muda sugestões, disponibilidade de criação ou projeto ativo da consulta atual.
- [ ] Alterar NS continua disponível só com projeto ativo; cancelar não renomeia nem limpa a sessão.
- [ ] Teclado, foco, zeros iniciais, bloqueios e limpeza na recusa mantêm comportamento verificável.
- [ ] Recusa e troca sincronizam visualizador, serviços e os demais painéis pelo mecanismo existente.

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

**Evidências e handoff:** não iniciada. Registrar componentes e objectNames finais, transições de
estado, estratégia de workers, validações automáticas/manuais e pendências de integração para E03.

## E03 — Integração do fluxo e aceite final — #pendente

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

- [ ] Base com mais de 200 projetos: fragmento encontra NS fora da página inicial e a ação abre seu ID.
- [ ] NS nova: pesquisa/GETs sem mutação; confirmação faz um POST e mantém exatamente um cadastro.
- [ ] Dois clientes: um projeto persistido, ambos terminam no mesmo ID, nenhum retry de criação.
- [ ] Projeto A ativo, busca por B: digitação mantém A; confirmação de abertura troca todos os painéis para B.
- [ ] Texto editado após selecionar A não abre A por um ID residual; resposta de A não sobrescreve busca por B.
- [ ] Timeout, 401, rota de pesquisa indisponível e ambiguidade não oferecem falsa ausência nem POST.
- [ ] Recusar criação limpa sessão/painéis/last_project_id sem mutação no servidor.
- [ ] Alteração de NS preserva controle de versão e rejeita colisão sem alterar os dois projetos.
- [ ] Restauração abre o último projeto válido mesmo fora da primeira página; ID removido é tratado sem sessão residual.
- [ ] Reconexão/fechamento descartam respostas antigas; bloqueio global continua impedindo ações incompatíveis.
- [ ] Gate completo aprovado e definição global de pronto integralmente satisfeita.

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

**Bloqueios:** nenhum bloqueio conhecido. Ambiente indisponível só será bloqueio quando constatado,
com evidência, impacto e procedimento de desbloqueio registrados.

**Riscos e mitigação:** suíte ampla pode revelar falha preexistente; comparar evidências e separar
causa sem expandir escopo, mantendo o gate como pendência até resolução. Teste só com gateway direto
pode esconder contrato incorreto; exigir ao menos um percurso Qt com gateway HTTP e servidor de teste.

**Prompt para uma sessão limpa:**

```text
Execute E03 — Integração do fluxo e aceite final — de docs/roadmap-busca-abertura-cadastro-ns.md. Leia primeiro instruções do repositório, roadmap, git status, evidências de E01/E02, implementação final do painel/gateway/API e testes de integração/e2e indicados. Confirme dependências realmente concluídas e ausência de divergências impeditivas. Preserve alterações preexistentes, não amplie o escopo e marque E03 #em-andamento no índice e detalhe ao iniciar.

Comprove a composição da UI Qt com gateway HTTP e servidor de teste: campo único, busca além dos 200 projetos, abertura direta de NS existente e criação confirmada. Complete apenas lacunas de regressão, incluindo dois clientes criando a mesma NS com um único projeto persistido e abertura do mesmo ID, ausência de POST repetido, respostas fora de ordem, erros distintos de ausência, troca e limpeza de todos os painéis, alteração de NS com controle de versão, restauração fora da primeira página e reconexão/fechamento. Use fixtures sintéticas e sincronização determinística; não dependa de SQL Server, PDFs privados ou produção. Corrija apenas defeitos do fluxo deste roadmap e revise a documentação correspondente.

Execute os comandos e o percurso manual de Validação obrigatória de E03, incluindo IniciarTestes.bat completo. Preencha cada critério da matriz e a definição global de pronto com evidências. Não declare sucesso com teste obrigatório falhando ou não executado, nem substitua o gate completo por validação parcial. Marque #concluida somente após todos os aceites; se houver impedimento real, marque #bloqueada com causa, evidência, impacto e ação de desbloqueio. Sincronize tags e registre arquivos, decisões, comandos, resultados, cobertura e inspeção manual em Evidências e handoff. Não crie commit, publique ou implante sem autorização explícita. Finalize com resumo conciso do resultado, validações e pendências.
```

**Evidências e handoff:** não iniciada. Registrar regressões acrescentadas, correções, comandos,
resultado do gate, cobertura, inspeção manual e aceite de cada requisito global.
