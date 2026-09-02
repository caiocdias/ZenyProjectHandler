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
