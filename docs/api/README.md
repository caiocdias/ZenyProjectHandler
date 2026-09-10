# API v1

O snapshot oficial da fronteira cliente-servidor é `openapi-v1.json`. Ele é produzido pela aplicação
declarativa `zeny_project_handler_api_spec`, que não compõe casos de uso nem implementa servidor.

Gere o arquivo com:

```powershell
.\.venv\Scripts\python.exe scripts\generate_openapi_v1.py
```

O teste `tests/contracts/test_openapi_snapshot.py` compara o JSON gerado com o arquivo versionado e
falha diante de qualquer alteração não revisada.

## Compatibilidade

- versão atual: `1.3.0`;
- prefixo protegido: `/api/v1`;
- faixa negociada: `1.3.0` a `1.999.999`;
- adições compatíveis podem introduzir rotas e campos opcionais dentro de v1;
- novos valores de enum fechado ou campos obrigatórios elevam o piso compatível antes de serem
  emitidos; remoção, renomeação ou mudança semântica de rota, campo, enum ou código de erro exige
  nova versão principal;
- o cliente consulta `GET /api/v1/session` antes de carregar dados e recusa uma faixa incompatível.

A versão `1.3.0` eleva o piso nos dois lados porque a sessão de revisão passa a emitir `CHANGE` em
`ElementSituation`, o enum fechado `SpanType` e campos obrigatórios de tipo e endpoints no
`DetectedSpanDto`. Assim, cliente `1.2.x` não recebe o novo valor fechado e cliente `1.3.x` não tenta
interpretar uma sessão antiga sem esses campos. Projetos persistidos continuam legíveis; sem nova
análise, tipos de trecho ausentes são projetados como `UNKNOWN`, conforme o ADR 0015.

Na sessão de revisão, `SpanType` possui `DISTRIBUTION_NETWORK`, `CONNECTION_BRANCH` e `UNKNOWN`. Cada
vão inclui `span_type`, `span_type_label`, `start_point_id` e `end_point_id`; os campos antigos
`start_element_id` e `end_element_id` permanecem para postes e ficam nulos quando o endpoint não é
um elemento. Um `TipoPontoRede.ENTREGA` recebe do servidor o rótulo público `Padrão do cliente`.
`ReviewOverlayDto` também recebe `situation_label`, permitindo que o cliente apresente `A alterar`
sem reinterpretar a situação.

Os códigos de serviço usam as operações aditivas `GET` e `PUT`
`/api/v1/projects/{project_id}/service-codes`. O detalhe do projeto e o PATCH da NS preservam a
forma anterior. `ProjectServiceCodesResponse` devolve `service_codes` e `project_version`; o PUT
recebe `ReplaceProjectServiceCodesRequest`, substitui toda a coleção e exige
`expected_project_version`. Cada item segue `^[0-9]{4}$`, inclusive valores como `0007`; coleção
vazia é válida. Uma versão obsoleta retorna `409 STALE_STATE` e nenhuma mutação recebe retry
automático cego.

A resolução exata de uma NS usa
`GET /api/v1/projects/by-service-note/{service_note}` com os dez dígitos preservados. Exatamente um
projeto devolve `ProjectDetailResponse`, ausência devolve `404 RESOURCE_NOT_FOUND` e registros
históricos ambíguos devolvem `409 INTEGRITY_ERROR` sem escolher um ID. Criar ou renomear para a NS
de outro projeto devolve `409 PROJECT_ALREADY_EXISTS`; `details` contém somente `project_id` e
`service_note`. Replay com a mesma chave e o mesmo payload continua idempotente, enquanto uma chave
nova não cria uma segunda NS.

## Classificação persistida do projeto

`GET /api/v1/projects/{project_id}/market` retorna `project_id`, `project_version` e
`classification`, nula enquanto não inicializada. O GET não consulta SQL nem grava dados.
Após a primeira análise com mercado SQL válido, `classification` contém `service_note`,
`database_market` (RURAL/URBANO), `effective_market` (RURAL/URBANO/AMBOS), `source` (SQL/MANUAL),
`initialized_at`, `updated_at`, `revision_id` e `classification_version`.

`PUT` na mesma rota recebe somente `effective_market` e `expected_project_version`. Escolha
inválida, campos extras ou edição antes de inicializar retornam `422 VALIDATION_ERROR`;
versão obsoleta retorna `409 STALE_STATE`. Job ou mutação concorrente usa o bloqueio global
existente e retorna `409 OPERATION_CONFLICT`. As duas rotas exigem Bearer; projeto ausente é 404.
O PUT devolve a mesma projeção com nova versão, revisão e origem MANUAL, conservando o mercado
inicial do SQL e seu instante. Mesmo salvar a mesma opção registra uma nova escolha. Não há
identidade individual de técnico no Bearer compartilhado; nenhuma é inventada para auditoria.

Inicialização ocorre no consumidor de conformidade após validar as NS dos cabeçalhos. Uma
resposta SQL válida é persistida antes de consultar ações; falha posterior de ação, cancelamento
ou avaliação não desfaz a inicialização nem publica conformidade parcial. Erro de mercado deixa
o estado nulo e a próxima análise tenta novamente. Reanálise/reinício preservam a escolha. Troca
de NS invalida o estado; retornar à NS anterior também exige consulta inicial nova. Ambos pode
ser salvo, mas o job de conformidade falha com `VALIDATION_ERROR` explícito até E03.

A revisão da classificação participa dos fatos/assinatura do método 13 e da desatualização em
documentação, conformidade e GMAX. Snapshots anteriores são imutáveis. O GMAX ainda mostra o
mercado efetivo do último snapshot Rural/Urbano; E04 apresentará a distinção banco/escolha na UI.

A adição mantém API 1.3.0 e o piso negociado, sem novos campos em DTOs antigos. Clientes atuais
continuam funcionando e precisam reler a versão do projeto após analisar, pois inicializar
também incrementa `project_version`. O futuro seletor deve tratar a ausência da rota em servidor
antigo como recurso indisponível, sem escolha local presumida.

Persistência aditiva no JSON `projects.payload`, sem DDL: campo ausente é não inicializado.
O head Alembic continua `0009_remote_jobs` e o lifecycle mantém formato 1. Não há conversão de
snapshots em escolhas humanas. A leitura/atualização foi testada numa cópia de banco legado.
Um runtime anterior pode desconhecer o novo campo/tipo JSON; rollback usa backup consistente
anterior em volume separado, sem downgrade destrutivo. Nenhum volume operacional é migrado por E02.

## Pesquisa de projetos por trecho de NS

`GET /api/v1/projects/search?query=001&limit=50&offset=0` é uma operação autenticada,
somente leitura, que retorna o DTO existente `ProjectSummaryListResponse` (`items` e `page`).
`query` é obrigatório e aceita de 1 a 10 dígitos ASCII, sem espaços ou normalização numérica;
zeros iniciais são preservados. Consulta vazia, letras, dígitos Unicode e mais de dez caracteres
retornam `422 VALIDATION_ERROR`. Campo vazio deve usar a listagem existente `/projects`.

A correspondência é por trecho em qualquer posição da NS, em todos os projetos. O SQLite filtra
antes de contar e paginar; somente os IDs da página são carregados para projeção. A ordem é
`created_at` crescente, com desempate por ID crescente. `limit` vai de 1 a 200 (padrão HTTP 50),
`offset` é não negativo (padrão 0) e `page.total` conta somente as correspondências. Sem resultados,
retorna `200` com `items=[]` e total zero; offset além do fim retorna lista vazia preservando o total.
Com dados estáveis, páginas consecutivas não repetem IDs. Alterações entre requisições podem mudar
o total e a composição das páginas; esta paginação não reserva um snapshot entre requisições.

A adição mantém API `1.3.0`, piso negociado e schemas anteriores: não há migração de dados,
novo enum ou campo obrigatório em respostas existentes. Clientes anteriores seguem usando as
operações atuais. `ProjectGateway.search_projects(query, *, limit=200, offset=0)` propaga
`ProjectGatewayError`; não converte falhas em lista vazia, `None` ou NS ausente.

Servidor antigo sem a rota pode responder `404` (com ou sem envelope) ou `422` se sua rota dinâmica
`/projects/{project_id}` interpretar `search` como UUID inválido. Ambos significam pesquisa
indisponível. O cliente preserva status/código de erros com envelope; falha sem envelope usa
`INTERNAL_ERROR` com o status recebido. Autenticação (`401`), falhas do servidor e timeout também
continuam erros, distintos de uma pesquisa vazia. Não há fallback para filtrar os primeiros 200.
A resolução exata existente pode continuar disponível; somente seu `404 RESOURCE_NOT_FOUND`
confirma ausência exata. Mesmo uma pesquisa vazia ou com dez dígitos não substitui essa resolução.
O campo Qt usa debounce e descarta respostas obsoletas. A abertura usa a resolução exata ou o ID
selecionado; Exportar também pode consultar `GET /projects/{project_id}` para acompanhar uma NS
fora da primeira página, sem novo endpoint ou alteração de schema.

## Projeção GMAX

`GET /api/v1/projects/{project_id}/gmax` devolve `GmaxSummaryResponse`, uma projeção autenticada e
somente leitura da sessão semântica atual e do último snapshot de conformidade. O GET não executa
o classificador de mercado nem o verificador de ações, não cria job e não persiste dados.

O cabeçalho usa os estados fechados `NOT_FOUND`, `MATCH` e `MISMATCH`. O snapshot usa
`NEVER_EXECUTED`, `CURRENT`, `STALE` e `BLOCKED_NS_MISMATCH`; `last_execution_id` e
`last_executed_at` identificam a última execução quando ela existe. Uma divergência atual entre a
NS do projeto e qualquer NS válida de cabeçalho tem prioridade: a resposta fica bloqueada, conserva
somente a identidade/data da execução anterior para auditoria e devolve `market=null` e
`row_found=null`, sem apresentar valores antigos como atuais.

A coleção `checks` contém exatamente, nesta ordem, `IMPACTO_AMBIENTAL` e `SERVIDAO`. Cada item
expõe a detecção atual no PDF, a descrição fechada da ação e um dos estados de consulta:
`NOT_EXECUTED`, `NOT_EXECUTED_NO_TRIGGER`, `NOT_EXECUTED_NO_SERVICE_CODES` ou `EXECUTED`.
`row_found` é obrigatoriamente `null` nos três primeiros e booleano somente em `EXECUTED`; `false`
significa SELECT executado sem linha, não ausência de execução. `market` aceita apenas `RURAL` ou
`URBANO` quando comprovado por um snapshot projetável. Cardinalidade impossível dos fatos do alvo
projeto falha com `409 INTEGRITY_ERROR` em vez de escolher ou inferir um valor.

## Decisões transversais

- somente `GET /health/live` é público; todas as operações sob `/api/v1` declaram Bearer;
- erros públicos usam `ErrorEnvelope`; respostas inesperadas não incluem traceback;
- criação de jobs e uploads exige `Idempotency-Key`, e mutações não admitem retry automático cego;
- jobs retornam `202` e informam polling inicial entre 250 e 500 ms;
- uploads são `multipart/form-data`; downloads e raster são binários, nunca caminhos físicos;
- preflight e confirmação são operações separadas para regras, projeto portátil e restauração;
- nomes públicos são nomes de exibição saneados, sem componentes de caminho;
- UUIDs distinguem cada identidade, datas exigem timezone e decimais precisos são strings;
- a implementação futura deve sanear detalhes de erro e nunca registrar Authorization ou senhas.
