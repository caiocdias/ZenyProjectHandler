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

- versão atual: `1.1.0`;
- prefixo protegido: `/api/v1`;
- faixa inicialmente negociada: `1.0.0` a `1.999.999`;
- adições compatíveis podem introduzir rotas e campos opcionais dentro de v1;
- remoção, renomeação ou mudança semântica de rota, campo obrigatório, enum ou código de erro exige
  nova versão principal;
- o cliente consulta `GET /api/v1/session` antes de carregar dados e recusa uma faixa incompatível.

Os códigos de serviço usam as operações aditivas `GET` e `PUT`
`/api/v1/projects/{project_id}/service-codes`. O detalhe do projeto e o PATCH da NS preservam a
forma anterior.

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
