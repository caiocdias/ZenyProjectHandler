# Roadmap — GMAX, busca de NS e proteção das consultas SQL

## Objetivo e resultado esperado

Adicionar ao Zeny Project Handler uma aba superior **GMAX**, posicionada entre
**Documentação e conformidade** e **Exportar**, para apresentar de forma auditável o mercado da
Nota de Serviço, os gatilhos encontrados nos PDFs e o resultado das consultas operacionais de
impacto ambiental e servidão. O mesmo conjunto de mudanças deve tornar a seleção de projetos
pesquisável, impedir a criação interativa de uma NS já cadastrada e oferecer os fluxos simétricos
de abrir o projeto existente ou criar uma NS ainda inexistente.

Antes de qualquer `SELECT` no SQL Server, a NS de dez dígitos do projeto deve ser comparada com
todas as NS válidas encontradas nos cabeçalhos dos PDFs. Se ao menos uma for diferente, a execução
de conformidade deve falhar de forma segura e compreensível, sem chamar nem o classificador de
mercado nem o verificador de ações e sem publicar snapshot parcial.

## Como usar este roadmap

Execute uma etapa por sessão limpa do Codex. Leia as instruções do repositório, este arquivo inteiro
e os arquivos citados na etapa antes de editar. Ao iniciar, sincronize a tag da etapa no índice e no
detalhe para `#em-andamento`; só use `#concluida` quando todos os critérios e validações obrigatórias
passarem. Registre arquivos, decisões, comandos e resultados em **Evidências e handoff**. Uma
dependência ainda pendente não é bloqueio.

## Contexto confirmado

- A raiz usa Python 3.11–3.13, FastAPI no servidor, PySide6 no cliente, Pydantic nos contratos e
  SQLite/Alembic como persistência principal. `README.md`, `pyproject.toml` e
  `IniciarTestes.bat` registram os comandos oficiais.
- Não há `AGENTS.md` no repositório na criação deste roadmap. A branch é `main` e
  `git status --short --branch` estava limpo.
- A NS é uma string de exatamente dez dígitos ASCII, normalizada por
  `src/zeny_project_handler/domain/project_metadata.py::normalizar_numero_ns` e persistida em
  `Projeto.nome` e em `projects.name`.
- `ProjectPanelWidget`, em
  `src/zeny_project_handler_client/ui/project_panel.py`, usa um `QComboBox` não editável, carrega no
  máximo 200 projetos e mantém um `QLineEdit` separado para criar ou alterar a NS. O botão **Abrir**
  ignora o texto desse campo e só abre o ID selecionado no combo.
- `ProjectApiService.create_project`, em
  `src/zeny_project_handler_server/project_api.py`, deriva o ID da chave de idempotência e não
  procura outro projeto com a mesma NS. `projects.name` não possui restrição única; portanto chaves
  de idempotência diferentes podem criar NS duplicadas.
- A API pública de projetos está em `zeny_project_handler_contracts/projects.py`,
  `zeny_project_handler_server/app.py`, `zeny_project_handler_api_spec/app.py` e
  `zeny_project_handler_client/ui/project_gateway.py`. E01 estabeleceu a versão `1.2.0`; a política
  permite operações e códigos de erro aditivos dentro da v1.
- `MainWindow`, em `src/zeny_project_handler_client/ui/main_window.py`, tabifica na direita, nesta
  ordem, **Resultados**, **Documentação e conformidade** e **Exportar**. Os docks são móveis,
  destacáveis, persistidos e registrados no menu **Exibir**.
- `ExecutarAnaliseConformidade.executar`, em
  `src/zeny_project_handler/application/compliance_analysis.py`, carrega a sessão semântica e chama
  imediatamente `ClassificadorMercadoPort.classificar`; só depois detecta impacto/servidão e chama
  `VerificadorAcoesConcluidasPort`. Logo, uma divergência de NS hoje não impede o primeiro `SELECT`.
- A extração vigente já limita a NS à zona de cabeçalho, aceita dez dígitos e exclui comentários de
  revisão em `project_compliance.py`. A execução também persiste fatos para o contexto rural/urbano,
  códigos de serviço, impacto ambiental, servidão e resultado booleano das duas ações.
- O snapshot atual permite distinguir uma consulta executada de uma consulta não aplicável: sem
  gatilho não existe o fato positivo correspondente; com gatilho e sem códigos não há fatos
  `projeto.codigo_servico`; com gatilho e códigos, o fato booleano da ação representa o resultado do
  `SELECT`. Esses dados ainda não são expostos pelo contrato público de conformidade.
- O endpoint `GET /api/v1/projects/{project_id}/compliance/latest` expõe achados, mas não os fatos
  necessários ao GMAX. `DocumentationComplianceApiService` tem acesso ao snapshot e à sessão
  semântica e é a fronteira confirmada para criar uma projeção somente leitura.
- `DocumentationPanelWidget` possui `limpar()` e já acompanha jobs explícitos de conformidade. O
  painel Projeto emite `project_opened`, mas não existe sinal equivalente para “nenhum projeto
  ativo” nem sinal público de conclusão/falha de uma reanálise de conformidade.
- O gate completo é `.\IniciarTestes.bat`; comandos individuais confirmados são Ruff, verificação de
  formatação, Mypy e `pytest --cov` pelo executável `.\.venv\Scripts\python.exe`.
- `docs/roadmap-acoes-impacto-servidao.md` cobre a implementação já concluída das consultas de ações.
  Este arquivo é um roadmap novo e distinto: reutiliza aquele comportamento como base, sem alterar
  seus estados ou evidências históricas.

## Escopo incluído

- Resolução exata e remota de projeto por NS normalizada, sem depender de a NS estar entre os 200
  itens carregados no combo.
- Código de erro público e específico para tentativa de criação de projeto com NS já existente,
  incluindo o ID do projeto que pode ser aberto.
- Proteção da criação e da alteração interativas contra uma segunda NS igual, preservando replay
  idempotente e coordenação global.
- Combo de projetos pesquisável por texto, sem inserir itens locais fictícios.
- Confirmação para abrir um projeto existente ao tentar criá-lo e confirmação para criar um projeto
  ao tentar abrir uma NS inexistente.
- Retorno explícito ao estado inicial quando o usuário recusar a ação proposta, sem criar, alterar
  ou excluir dados no servidor.
- Detector único de NS de cabeçalho reutilizado pela proteção pré-SQL e pela projeção GMAX.
- Bloqueio de todos os `SELECT`s de mercado e ações quando qualquer NS válida de cabeçalho divergir
  da NS do projeto.
- Projeção pública GMAX do último snapshot: mercado, detecção no PDF, estado de execução da consulta,
  linha encontrada ou não, data/execução e indicação de resultado desatualizado.
- Nova aba/dock **GMAX** somente leitura, na ordem visual solicitada, sincronizada com o projeto e
  com as análises de conformidade.
- Testes de domínio/aplicação, servidor, contratos, gateways, Qt, OpenAPI e fluxo integrado, além de
  atualização da documentação viva.

## Fora de escopo

- Alterar os SQLs parametrizados de `TB_NOTAS` ou `vBIAcoes`, escrever no SQL Server ou expor SQL,
  string de conexão, timeout ou credenciais ao cliente.
- Executar consulta nova ao abrir/atualizar a aba GMAX; ela projeta somente sessão semântica e
  snapshots persistidos.
- Mudar os gatilhos atuais: impacto continua sendo o valor normalizado exatamente `SIM` no
  cabeçalho, e servidão continua aceitando os termos positivos já documentados fora de comentários.
- Deduplicar, mesclar ou excluir automaticamente projetos históricos que já compartilhem uma NS.
- Alterar a política de colisão da importação/restauração de projetos ou adicionar índice único a
  `projects.name` sem uma estratégia separada para dados históricos e pacotes portáteis.
- Exportar uma planilha GMAX, modificar os entregáveis existentes ou mover a aba GMAX para dentro do
  `QTabWidget` interno do painel de documentação.
- Consultar um SQL Server real, publicar release, implantar ou alterar infraestrutura.

## Restrições e invariantes

- A NS permanece string de dez dígitos em domínio, contrato, URL, cliente e SQLite; conversão física
  para inteiro continua exclusiva do adaptador SQL Server.
- A resolução por NS é exata depois da normalização. Busca visual parcial serve apenas para filtrar
  sugestões; nunca autoriza abrir ou criar a partir de uma NS incompleta.
- Replay com a mesma chave e o mesmo payload continua devolvendo o projeto originalmente criado.
  Uma chave nova para uma NS existente não cria recurso e devolve conflito específico.
- A checagem de duplicidade acontece dentro da mesma coordenação global da escrita. Se dados
  históricos contiverem mais de um projeto com a mesma NS, a API falha com integridade e não escolhe
  silenciosamente um deles.
- “Estado inicial” significa: nenhum projeto ativo/selecionado, textos de busca e NS limpos, códigos
  e páginas vazios, visualizador e painéis dependentes limpos e `last_project_id` removido. Nenhum
  dado remoto é apagado.
- Todas as NS válidas extraídas dos cabeçalhos participam da guarda. Zero NS identificada permite a
  execução; todas iguais à NS do projeto permitem; uma ou mais diferentes bloqueiam, mesmo que outra
  folha contenha a NS correta.
- A guarda de cabeçalho roda depois de carregar a sessão semântica e antes da primeira chamada a
  `ClassificadorMercadoPort` ou `VerificadorAcoesConcluidasPort`.
- Uma divergência de NS encerra o job com erro seguro e não publica novo snapshot. Um snapshot
  anterior pode permanecer armazenado, mas GMAX deve marcá-lo como não atual/bloqueado e nunca
  apresentá-lo como resultado vigente.
- GMAX não infere que um `SELECT` retornou falso quando ele não foi executado. Os estados
  “sem execução”, “sem gatilho”, “sem códigos de serviço” e “executado” são distintos; somente o
  último admite `row_found=True/False`.
- Para snapshot vigente, mercado deve ser derivado exclusivamente do fato de escopo projeto
  `rede.contexto_rural=True` ou `rede.contexto_urbano=True`. Cardinalidade inconsistente é erro de
  integridade, não fallback.
- O cliente continua sem importar domínio de conformidade, `pyodbc` ou lógica SQL. A interpretação
  dos fatos em DTO GMAX pertence ao servidor.
- Toda adição de rota, DTO ou enum é aditiva na v1, atualiza OpenAPI e incrementa `API_VERSION` para
  `1.2.0`; os limites de compatibilidade continuam `1.0.0`–`1.999.999`.
- A mudança pré-SQL altera a semântica da conformidade e incrementa
  `VERSAO_METODO_CONFORMIDADE` de `9` para `10`.

## Hipóteses e decisões em aberto

1. **Significado de “aba de conformidade”:** o plano interpreta o pedido como uma nova aba de dock
   de nível superior entre `documentationComplianceDock` e `projectExportDock`, porque essa é a
   estrutura que hoje posiciona conformidade ao lado de exportação. Impacto: GMAX será móvel,
   destacável e persistido como os outros painéis; não será uma quarta aba interna ao lado de
   **Documentação**, **Conformidade** e **Regras**.
2. **Resultado do select:** o plano apresenta a classificação `RURAL`/`URBANO` de `TB_NOTAS` e, para
   cada ação de `vBIAcoes`, distingue `não executado`, `executado sem linha` e `executado com linha`.
   Impacto: ausência do gatilho no PDF não será exibida como resultado negativo do banco.
3. **NS ausente no cabeçalho:** o pedido proíbe consultas quando as notas são diferentes, não quando
   o cabeçalho não permite identificar a NS. O plano permite a consulta no caso ausente e conserva
   a inspeção documental vigente. Impacto: se o produto exigir NS obrigatória no PDF, isso precisará
   de uma regra/requisito separado.
4. **Projetos históricos duplicados:** não há evidência de duplicatas no banco do repositório e não
   há autorização para mesclar ou excluir dados. O plano bloqueia novas duplicatas nos fluxos
   interativos e trata múltiplos resultados históricos como integridade. Impacto: um administrador
   precisará resolver dados ambíguos em atividade separada antes que a opção **Abrir este projeto**
   possa apontar para um único ID.
5. **Pesquisa do combo:** o combo editável usa filtro local por conteúdo para resposta imediata e a
   resolução exata remota para uma NS completa. Impacto: sugestões parciais continuam limitadas à
   página carregada, mas abrir/criar uma NS completa funciona mesmo fora dos primeiros 200 itens.

## Definição global de pronto

- [ ] A aba **GMAX** aparece exatamente entre **Documentação e conformidade** e **Exportar**, é
  restaurável pelo menu **Exibir** e acompanha o projeto ativo.
- [ ] GMAX mostra mercado, presença de impacto/servidão no PDF, ação consultada e resultado do
  `SELECT`, distinguindo claramente consulta não executada, sem linha e com linha.
- [ ] GMAX mostra estado vazio sem snapshot, estado desatualizado e bloqueio por NS divergente sem
  apresentar resultado antigo como atual.
- [x] O menu suspenso de projetos permite pesquisar NS e mantém associação correta entre texto e ID.
- [x] Criar uma NS existente não faz `POST` efetivo adicional; o usuário pode abrir o único projeto
  encontrado ou recusar e voltar ao estado inicial.
- [x] Abrir uma NS inexistente informa que a nota não existe; aceitar cria exatamente um projeto e
  recusar não cria nenhum e volta ao estado inicial.
- [x] Conflito detectado no servidor depois de uma corrida recebe o mesmo tratamento visual da
  detecção antecipada no cliente.
- [x] Qualquer NS válida divergente no cabeçalho impede todas as chamadas aos dois ports SQL e não
  publica snapshot parcial; cabeçalho ausente ou totalmente coincidente preserva o fluxo atual.
- [x] API `1.2.0`, OpenAPI, contratos, gateways, documentação funcional/arquitetural e testes estão
  sincronizados.
- [ ] `.\IniciarTestes.bat` termina com código zero, inclusive Ruff, formatação, Mypy, Pytest,
  cobertura e complexidade.

## Índice das etapas

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Resolução exata e conflito de NS existente | #concluida | nenhuma | API capaz de resolver NS e impedir duplicidade interativa |
| E02 | Pesquisa e diálogos do painel Projeto | #concluida | E01 | Fluxos abrir/criar simétricos e retorno ao estado inicial |
| E03 | Guarda de NS antes dos SELECTs | #concluida | nenhuma | Divergência de cabeçalho bloqueia mercado e ações sem snapshot |
| E04 | Projeção e contrato remoto GMAX | #concluida | E03 | DTO/endpoint somente leitura com estados auditáveis |
| E05 | Aba GMAX e sincronização Qt | #pendente | E02, E04 | Dock GMAX na ordem solicitada, atualizado e testado |
| E06 | Fluxo integrado, documentação e gate final | #pendente | E01, E02, E03, E04, E05 | Regressão completa e definição global de pronto comprovada |

## E01 — Resolução exata e conflito de NS existente — #concluida

### Objetivo

Permitir que o cliente resolva uma NS completa para um único projeto e garantir que criação ou
alteração interativa não produza uma segunda NS igual, com resposta suficiente para oferecer a
abertura do projeto existente.

### Por que agora

O fluxo visual de E02 precisa de uma fonte remota autoritativa e de um conflito específico para
cobrir listas paginadas e corridas entre clientes. E01 e E03 são independentes e podem ser
executadas em paralelo, desde que não editem simultaneamente documentação/OpenAPI.

### Dependências e paralelismo

- Dependências: nenhuma.
- Pode avançar em paralelo com E03.
- Conflitos prováveis: `project_api.py`, `server/app.py`, `api_spec/app.py`, contratos, gateway de
  projeto, OpenAPI e respectivos testes. E04 não deve atualizar OpenAPI enquanto E01 estiver ativa.

### Escopo

- `src/zeny_project_handler_contracts/errors.py`
- `src/zeny_project_handler_contracts/projects.py`
- `src/zeny_project_handler_contracts/versioning.py`
- `src/zeny_project_handler_server/project_api.py`
- `src/zeny_project_handler_server/app.py`
- `src/zeny_project_handler_api_spec/app.py`
- `src/zeny_project_handler_client/ui/project_gateway.py`
- `tests/remote_gateways.py`
- `tests/server/test_project_document_api.py`
- `tests/integration/test_project_http_gateway.py`
- `tests/contracts/test_models.py` e `tests/contracts/test_openapi_snapshot.py`
- `docs/api/openapi-v1.json` e `docs/api/README.md`

### Fora de escopo

- Alterar widgets ou exibir diálogos.
- Deduplicar projetos históricos, adicionar migração/índice único ou mudar importação/restauração.
- Fazer busca parcial remota; a rota desta etapa resolve somente uma NS completa e exata.

### Passos de implementação

1. Adicionar `PROJECT_ALREADY_EXISTS` a `ErrorCode`, mantendo os códigos existentes e a serialização
   do envelope.
2. Implementar em `ProjectApiService` uma resolução exata por NS normalizada que devolva detalhe
   quando houver exatamente um projeto, `RESOURCE_NOT_FOUND` quando não houver e `INTEGRITY_ERROR`
   quando dados históricos forem ambíguos.
3. Expor `GET /api/v1/projects/by-service-note/{service_note}` antes da rota dinâmica por UUID na
   aplicação real e na especificação. O path recebe dez dígitos e nunca converte a NS no cliente.
4. Dentro da coordenação de `create_project`, procurar a NS antes de salvar. Com outro projeto,
   abandonar corretamente o registro idempotente e devolver `409 PROJECT_ALREADY_EXISTS`, com
   `details` contendo apenas `project_id` e `service_note`. Replay legítimo da mesma chave continua
   retornando a resposta original.
5. Aplicar a mesma precondição a `update_project`, ignorando o próprio ID, para que **Alterar NS** não
   invalide a resolução exata. Não mudar a semântica de importação/restore nesta etapa.
6. Adicionar `find_project_by_service_note` ao protocolo e gateways HTTP/direto. O gateway converte
   somente `RESOURCE_NOT_FOUND` em `None`; conflito, integridade e transporte permanecem erros.
7. Incrementar a API para `1.2.0`, regenerar OpenAPI e documentar rota, erro, idempotência e
   compatibilidade.
8. Cobrir criação inicial, replay, segunda chave para a mesma NS, dois clientes concorrentes,
   resolução fora da primeira página, rename conflitante, zero/um/múltiplos resultados e ausência
   de vazamento de detalhes internos.

### Compatibilidade e rollback

- A rota e o código de erro são aditivos na v1; clientes 1.1 continuam válidos, mas verão o envelope
  novo como um erro não tratado se tentarem duplicar a NS.
- Não existe migração de dados. Antes de uma release, o rollback pode remover rota/código/guarda sem
  transformar dados. Depois de depender do comportamento em produção, o rollback deve preservar a
  rota e o código ou publicar uma versão compatível; não reutilizar o valor do enum com outra
  semântica.

### Prompt para uma sessão limpa

```text
Na raiz do repositório ZenyProjectHandler, execute somente a E01 — Resolução exata e conflito de NS
existente — de docs/roadmap-gmax-fluxos-ns.md. Leia primeiro eventuais AGENTS.md, o roadmap inteiro,
README.md, pyproject.toml, os contratos de projetos/erros/versionamento, project_api.py, as rotas real
e de especificação, project_gateway.py, tests/remote_gateways.py e os testes citados na E01. Confira
git status --short --branch, preserve mudanças preexistentes e verifique se o código ainda
corresponde ao contexto do plano e se as dependências estão satisfeitas.

Sincronize E01 no índice e no detalhe para #em-andamento. Implemente resolução exata de uma NS
normalizada por GET /api/v1/projects/by-service-note/{service_note}, devolvendo detalhe para um
único projeto, RESOURCE_NOT_FOUND para nenhum e INTEGRITY_ERROR para múltiplos históricos. Adicione
PROJECT_ALREADY_EXISTS e faça create_project e update_project, sob a coordenação existente,
recusarem uma NS pertencente a outro ID. O conflito de criação deve ser 409 e trazer apenas
project_id e service_note em details; preserve replay idempotente e abandone registros incompletos
quando houver conflito. Adicione o método aos gateways HTTP/direto, converta somente 404 em None,
suba API_VERSION para 1.2.0 e sincronize OpenAPI e docs/api. Não crie índice, migração, deduplicação
ou mudança de importação.

Crie/ajuste os testes de contratos, servidor e gateway para zero/um/múltiplos resultados, criação,
replay, corrida, rename e detalhes seguros. Execute todas as validações da E01. Não declare sucesso
com teste obrigatório falhando ou não executado. Se o aceite passar, marque E01 #concluida no índice
e no detalhe; se houver impedimento real, marque #bloqueada e registre causa, evidência, impacto e
ação de desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos e resultados e
termine com resumo conciso. Não crie commit, não publique e não implante sem autorização.
```

### Critérios de aceite

- [x] Resolver NS inexistente produz `RESOURCE_NOT_FOUND`; exatamente uma devolve o detalhe correto.
- [x] Mais de um projeto histórico com a mesma NS produz `INTEGRITY_ERROR` e nenhum ID é escolhido.
- [x] Segunda criação com chave nova produz `PROJECT_ALREADY_EXISTS`, informa o ID existente e não
  altera a quantidade de projetos.
- [x] Replay da mesma criação continua idempotente.
- [x] Dois clientes concorrentes não conseguem publicar dois projetos interativos com a mesma NS.
- [x] Alterar um projeto para a NS de outro é recusado; manter a própria NS continua permitido.
- [x] Clientes/gateways distinguem ausência, duplicidade e falha de transporte.
- [x] API `1.2.0`, snapshot OpenAPI e documentação da rota estão sincronizados.

### Validação obrigatória

```powershell
.\.venv\Scripts\python.exe -m pytest tests/server/test_project_document_api.py tests/integration/test_project_http_gateway.py tests/contracts/test_models.py tests/contracts/test_openapi_snapshot.py
.\.venv\Scripts\python.exe -m ruff check src/zeny_project_handler_contracts src/zeny_project_handler_server src/zeny_project_handler_client/ui/project_gateway.py tests/remote_gateways.py tests/server/test_project_document_api.py tests/integration/test_project_http_gateway.py tests/contracts
.\.venv\Scripts\python.exe -m mypy
```

Resultado esperado: comandos com código zero; OpenAPI contém a rota exata, resposta e novo código
sem remover operações existentes.

### Bloqueios

Nenhum bloqueio conhecido.

### Riscos e mitigação

- **Corrida entre clientes:** manter busca e gravação dentro do coordenador global e testar duas
  chamadas concorrentes.
- **Ambiguidade histórica:** falhar fechado com integridade; nunca usar `next()` ou o primeiro item.
- **Rota capturada como UUID:** declarar a rota literal antes de `/projects/{project_id}` e cobrir a
  aplicação real e a especificação.

### Evidências e handoff

- Estado inicial: etapa iniciada em 2026-09-01; dependências inexistentes e contexto técnico do
  plano confirmados contra o código atual. A remoção preexistente de
  `docs/roadmap-acoes-impacto-servidao.md` será preservada sem intervenção.
- Arquivos de contrato/API: `src/zeny_project_handler_contracts/errors.py`,
  `src/zeny_project_handler_contracts/versioning.py`,
  `src/zeny_project_handler_server/api_errors.py`,
  `src/zeny_project_handler_server/project_api.py`, `src/zeny_project_handler_server/app.py` e
  `src/zeny_project_handler_api_spec/app.py`.
- Arquivos de cliente/teste: `src/zeny_project_handler_client/ui/project_gateway.py`,
  `tests/remote_gateways.py`, `tests/server/test_project_document_api.py`,
  `tests/integration/test_project_http_gateway.py`, `tests/contracts/test_models.py` e
  `tests/contracts/test_openapi_snapshot.py`.
- Documentação sincronizada: `docs/api/openapi-v1.json`, `docs/api/README.md` e este roadmap.
- Decisões: igualdade exata sobre a NS normalizada e persistida em `projects.name`, sem índice ou
  migração; cardinalidade zero/um/múltiplos tratada antes de selecionar ID; replay completo
  precede a checagem de conflito; criação abandona reserva idempotente incompleta em qualquer
  falha; `PROJECT_ALREADY_EXISTS` expõe somente `project_id` e `service_note`; gateways convertem
  somente `404 RESOURCE_NOT_FOUND` em `None`.
- Cobertura adicional: o teste de servidor persiste 201 projetos, comprova que a última NS não está
  nos 200 itens da primeira página e ainda assim a resolve pela rota exata.
- Validação: `scripts/generate_openapi_v1.py` regenerou o snapshot com código zero. O comando Pytest
  obrigatório passou com 65 testes (`65 passed`); por restrição do sandbox, usou `TEMP/TMP` local e
  `PYTEST_ADDOPTS=--basetemp=tmp/e01c` para evitar o diretório temporário global e o limite de path
  do Windows. O único aviso foi a impossibilidade preexistente de escrever `.pytest_cache`.
- Validação: o comando Ruff obrigatório terminou com `All checks passed!`; o Mypy obrigatório
  terminou com `Success: no issues found in 303 source files`; `git diff --check` retornou código
  zero.
- Handoff para E02: usar `ProjectGateway.find_project_by_service_note`; ausência é `None`, enquanto
  integridade, conflito e transporte permanecem `ProjectGatewayError`. Em corrida de criação,
  `details.project_id` é o único ID seguro a oferecer para abertura. Nenhum widget foi alterado.
- Escopo preservado: nenhuma migração, índice, deduplicação, mudança de importação, commit,
  publicação ou implantação foi realizada.

## E02 — Pesquisa e diálogos do painel Projeto — #concluida

### Objetivo

Transformar o combo de projetos em um seletor pesquisável e implementar os dois fluxos solicitados:
criar uma NS existente oferece abrir o projeto; abrir uma NS inexistente oferece criá-lo.

### Por que agora

E01 fornece resolução autoritativa e conflito de corrida. Sem isso, o cliente ficaria limitado aos
200 itens locais e poderia criar duplicidade entre a verificação e o `POST`.

### Dependências e paralelismo

- Dependência: E01 `#concluida`.
- Pode avançar em paralelo com E03 ou E04 após E01.
- Conflitos prováveis: `project_panel.py`, `main_window.py`, testes Qt e `tests/remote_gateways.py`.
  E05 deve aguardar porque reutilizará o novo sinal de estado vazio.

### Escopo

- `src/zeny_project_handler_client/ui/project_panel.py`
- `src/zeny_project_handler_client/ui/main_window.py`
- `src/zeny_project_handler_client/ui/documentation_panel.py`
- `src/zeny_project_handler_client/ui/portability_panel.py`
- `tests/e2e/test_mvp_ui.py`
- `tests/integration/test_window.py`
- `tests/unit/test_project_panel_remote_boundary.py`
- `docs/especificacao-funcional.md`

### Fora de escopo

- Criar novo endpoint, código de erro ou regra servidor.
- Pesquisar por texto livre que não seja dígito da NS.
- Alterar a UI de códigos de serviço, PDFs ou análise.

### Passos de implementação

1. Tornar `mvpProjectCombo` editável para busca, com `NoInsert`, validador ASCII, limite de dez
   dígitos e `QCompleter`/modelo filtrado por conteúdo sem perder o `project_id` dos itens.
2. Manter a opção “Selecione um projeto” e separar texto pesquisado de seleção real; texto parcial
   nunca dispara abertura ou criação.
3. Ao clicar **Abrir**, abrir o ID selecionado; sem seleção e com dez dígitos, resolver remotamente.
   Se não existir, exibir pergunta “A Nota de Serviço não existe. Deseja criar o projeto da nota?”.
   **Sim** cria uma vez e ativa; **Não** chama a transição única para estado inicial.
4. Ao clicar **Criar**, resolver a NS antes do `POST`. Se existir, informar que já há projeto e
   perguntar se deseja abri-lo. **Sim** abre o ID; **Não** não cria e volta ao estado inicial.
5. Se a resolução não encontrar e a criação receber `PROJECT_ALREADY_EXISTS` por corrida, extrair o
   ID seguro do envelope e apresentar exatamente o mesmo diálogo; nunca repetir `POST`
   automaticamente.
6. Centralizar `_reset_to_initial_state`: limpar sessão, seleção/textos, QSettings do último projeto,
   serviços, páginas, viewer e review; emitir um novo sinal `project_cleared` para limpar
   documentação e exportação sem apagar dados remotos.
7. Adicionar `limpar()` ao painel Exportar se necessário e conectar os sinais na janela. O estado
   vazio deve desabilitar ações dependentes e não reabrir automaticamente o projeto recusado.
8. Cobrir busca parcial, seleção após filtro, NS fora da página local, todos os ramos Sim/Não,
   corrida, ausência de chamadas indevidas e limpeza coordenada dos painéis.
9. Documentar a pesquisa, os diálogos e o significado do estado inicial na especificação funcional.

### Prompt para uma sessão limpa

```text
Na raiz do repositório ZenyProjectHandler, execute somente a E02 — Pesquisa e diálogos do painel
Projeto — de docs/roadmap-gmax-fluxos-ns.md. Leia eventuais AGENTS.md, o roadmap inteiro, README.md,
project_panel.py, main_window.py, documentation_panel.py, portability_panel.py, project_gateway.py e
os testes Qt citados. Confira git status --short --branch, preserve mudanças preexistentes, confirme
que E01 está #concluida e que a API/gateway de resolução por NS não divergiu do plano.

Sincronize E02 para #em-andamento. Torne mvpProjectCombo pesquisável somente por até dez dígitos,
sem inserir item fictício e preservando o ID de cada opção. Abrir deve usar a seleção ou resolver uma
NS completa: se inexistente, informar e perguntar se deve criar; Sim cria exatamente uma vez e abre,
Não volta ao estado inicial. Criar deve resolver primeiro: se já existe, informar e perguntar se
deve abrir; Sim abre o ID existente, Não não envia criação e volta ao estado inicial. Trate também
PROJECT_ALREADY_EXISTS recebido depois de corrida com o mesmo diálogo, sem repetir POST. Centralize
o estado inicial como nenhum projeto ativo, entradas/seleção limpas, last_project_id removido,
viewer/review/documentação/exportação limpos e ações dependentes desabilitadas. Emita e conecte um
sinal project_cleared; não exclua nada no servidor.

Atualize testes e docs/especificacao-funcional.md, execute todas as validações da E02 e não declare
sucesso com teste falhando ou não executado. Marque #concluida somente após o aceite; em impedimento
real, use #bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff e
resuma mudanças, validações e pendências. Não crie commit, não publique e não implante.
```

### Critérios de aceite

- [x] Digitar parte de uma NS filtra/localiza sugestões sem alterar ou inventar IDs.
- [x] Uma NS completa fora dos itens carregados pode ser resolvida e aberta remotamente.
- [x] **Criar** com NS existente mostra a mensagem e o diálogo; **Sim** abre, **Não** não cria.
- [x] **Abrir** com NS inexistente mostra a mensagem e o diálogo; **Sim** cria uma vez, **Não** não
  cria.
- [x] Um conflito de corrida `PROJECT_ALREADY_EXISTS` segue o mesmo fluxo e não repete `POST`.
- [x] Todos os ramos de recusa deixam a aplicação no estado inicial definido, sem mutação remota.
- [x] Viewer, Resultados, Documentação/conformidade e Exportar não permanecem apontando para um
  projeto depois do reset.
- [x] Campo incompleto ou inválido produz aviso e nenhuma requisição de abertura/criação.

### Validação obrigatória

```powershell
.\.venv\Scripts\python.exe -m pytest tests/e2e/test_mvp_ui.py tests/integration/test_window.py tests/unit/test_project_panel_remote_boundary.py
.\.venv\Scripts\python.exe -m ruff check src/zeny_project_handler_client/ui tests/e2e/test_mvp_ui.py tests/integration/test_window.py tests/unit/test_project_panel_remote_boundary.py
.\.venv\Scripts\python.exe -m mypy
```

Resultado esperado: testes Qt passam sem diálogo pendente, chamadas indevidas ou painel com projeto
residual; Ruff e Mypy terminam com código zero.

### Bloqueios

Nenhum bloqueio conhecido depois de E01.

### Riscos e mitigação

- **Sinais recursivos ao filtrar/repopular o combo:** bloquear sinais durante atualização e testar
  texto, `currentData` e índice.
- **Diálogo duplicado por corrida:** concentrar a decisão numa única função e contar chamadas do
  gateway nos testes.
- **Estado visual inconsistente:** usar uma transição central e um sinal explícito, não limpezas
  parciais em cada ramo.

### Evidências e handoff

- Estado inicial: etapa iniciada em 2026-09-01 sobre `main`, com
  `git status --short --branch` limpo; não havia mudanças preexistentes a preservar nesta sessão.
- Dependência confirmada: E01 permanece `#concluida`; rota, contrato e gateway de resolução exata
  por NS continuam aderentes ao plano (`API_VERSION=1.2.0`, ausência convertida em `None` e
  `PROJECT_ALREADY_EXISTS` com `project_id`/`service_note`).
- Implementação: `project_panel.py` tornou `mvpProjectCombo` editável com `NoInsert`, validador
  ASCII de zero a dez dígitos e `QCompleter` por conteúdo sobre o modelo real; a seleção só é usada
  quando texto e item/ID permanecem associados, e uma NS completa sem item usa a resolução remota.
- Fluxos: **Criar** resolve antes do `POST`; **Abrir** resolve uma pesquisa completa sem seleção;
  os diálogos Sim/Não são simétricos. `PROJECT_ALREADY_EXISTS` extrai apenas o `project_id` seguro,
  reutiliza o diálogo de projeto existente e nunca repete a criação automaticamente.
- Estado inicial: `_reset_to_initial_state` remove sessão e `last_project_id`, limpa pesquisa, NS,
  serviços, páginas, progresso e seleção, desabilita ações dependentes e emite `project_cleared`.
  `main_window.py` conecta o sinal ao visualizador, Resultados e Exportar; a conexão de sessão já
  existente limpa Documentação/conformidade. `portability_panel.py` ganhou `limpar()` e os combos
  dependentes deixam de selecionar projeto. Nenhuma chamada de exclusão remota participa do reset.
- Arquivos alterados: `src/zeny_project_handler_client/ui/project_panel.py`,
  `src/zeny_project_handler_client/ui/main_window.py`,
  `src/zeny_project_handler_client/ui/documentation_panel.py`,
  `src/zeny_project_handler_client/ui/portability_panel.py`,
  `src/zeny_project_handler_client/ui/review_panel.py`, `tests/e2e/test_mvp_ui.py`,
  `docs/especificacao-funcional.md` e este roadmap.
- Cobertura: testes Qt verificam filtro parcial e máximo de dez dígitos, ausência de item fictício,
  IDs preservados, opção selecionada, resolução fora da lista local, Sim/Não para criação e
  abertura, corrida Sim/Não com um único `POST` por tentativa, entradas inválidas e limpeza de
  visualizador/Resultados/Documentação/Exportar/ações/QSettings.
- Validação obrigatória final: Pytest passou com `29 passed` em 32,72 s; Ruff terminou com
  `All checks passed!`; Mypy terminou com `Success: no issues found in 303 source files`.
  Para contornar a restrição local já conhecida de `.pytest_cache`, Pytest usou `TEMP/TMP` no
  workspace e `PYTEST_ADDOPTS=--basetemp=tmp/e02-final/pytest`; restou somente o aviso não fatal
  de cache. `git diff --check` também retornou código zero.
- Handoff para E05: conectar `project_cleared` diretamente ao futuro `GmaxPanelWidget.limpar`;
  `project_opened` continua emitindo o UUID remoto tanto para seleção local quanto para resolução
  fora dos 200 itens. O estado vazio não apaga dados do servidor.
- Escopo preservado: nenhum endpoint/contrato/regra servidor, commit, publicação ou implantação foi
  criado ou alterado.

## E03 — Guarda de NS antes dos SELECTs — #concluida

### Objetivo

Comparar a NS do projeto com as NS válidas dos cabeçalhos antes de qualquer acesso ao SQL Server e
interromper a conformidade de forma atômica quando houver divergência.

### Por que agora

É a redução de risco mais importante do pedido e pode ser implementada independentemente da UX de
projetos. E04 reutilizará exatamente o mesmo detector para explicar o bloqueio no GMAX.

### Dependências e paralelismo

- Dependências: nenhuma.
- Pode avançar em paralelo com E01; E04 depende desta etapa.
- Conflitos prováveis: `compliance_analysis.py`, `project_compliance.py`, erros de aplicação e testes
  de conformidade/jobs. Não executar E04 simultaneamente nesses arquivos.

### Escopo

- `src/zeny_project_handler/application/project_compliance.py`
- `src/zeny_project_handler/application/compliance_analysis.py`
- `src/zeny_project_handler/application/errors.py`
- `src/zeny_project_handler_server/job_manager.py` somente se o mapeamento seguro exigir ajuste
- `tests/integration/test_compliance_analysis.py`
- `tests/server/test_jobs_api.py`
- `tests/server/test_compliance_api.py`
- `tests/market_fakes.py`
- `docs/arquitetura-conformidade.md` e `docs/especificacao-funcional.md`

### Fora de escopo

- Tornar a NS de cabeçalho obrigatória.
- Alterar regex, sinônimos, zona de cabeçalho ou tratamento de comentários além do necessário para
  expor o detector já existente.
- Consultar banco para descobrir qual NS está correta.

### Passos de implementação

1. Extrair uma função pública e determinística `detectar_notas_servico_cabecalho` que reutilize a
   extração atual, devolva valores válidos com evidências na ordem de leitura e exclua comentários.
   Reutilizá-la na geração dos fatos para evitar duas interpretações de NS.
2. Adicionar `NotaServicoCabecalhoDivergenteError` como erro esperado de aplicação, com mensagem
   segura que informe NS do projeto e valores divergentes sem detalhes de infraestrutura.
3. Em `ExecutarAnaliseConformidade.executar`, depois de carregar a sessão e antes de
   `_market_classifier.classificar`, bloquear se qualquer valor único divergir de
   `session.projeto.nome`.
4. Garantir que o erro percorra tanto o pipeline completo quanto o job explícito como
   `VALIDATION_ERROR`, não como falha interna, e que não haja novo commit/snapshot.
5. Incrementar `VERSAO_METODO_CONFORMIDADE` de `9` para `10` e ajustar expectativas de versão e
   desatualização nos testes/documentação.
6. Testar cabeçalho ausente, uma ou várias ocorrências coincidentes, uma divergente, mistura de
   coincidente/divergente, comentário de revisão, múltiplos PDFs e ordem das chamadas. Nos casos
   bloqueados, `FakeClassificadorMercado.consultas` e `FakeVerificadorAcoesConcluidas.consultas`
   permanecem vazias e a última execução persistida não muda.
7. Documentar o gate pré-SQL, sua mensagem operacional e a necessidade de corrigir projeto/PDF e
   reexecutar a análise.

### Prompt para uma sessão limpa

```text
Na raiz do repositório ZenyProjectHandler, execute somente a E03 — Guarda de NS antes dos SELECTs —
de docs/roadmap-gmax-fluxos-ns.md. Leia eventuais AGENTS.md, o roadmap inteiro, README.md,
src/zeny_project_handler/application/project_compliance.py,
src/zeny_project_handler/application/compliance_analysis.py,
src/zeny_project_handler/application/errors.py, src/zeny_project_handler/ports/market.py,
src/zeny_project_handler_server/job_manager.py, tests/market_fakes.py e os testes citados. Confira
git status --short --branch, preserve mudanças preexistentes e confirme que o código ainda chama o
mercado antes de validar a NS de cabeçalho.

Sincronize E03 para #em-andamento. Extraia um detector público único das NS válidas encontradas na
zona de cabeçalho, preservando evidências/ordem e excluindo comentários. Reuse esse detector nos
fatos existentes. Depois de carregar a sessão semântica e antes da primeira chamada a qualquer port
SQL, compare todos os valores únicos com session.projeto.nome: ausência ou todos iguais permite;
qualquer diferente lança NotaServicoCabecalhoDivergenteError. Mapeie a falha como validação segura,
não publique snapshot e não chame classificador nem verificador de ações. Incremente o método de 9
para 10. Não torne a NS de cabeçalho obrigatória e não altere os SQLs ou os gatilhos.

Cubra ausência, igualdade, múltiplas folhas, mistura, divergência e comentário, inclusive listas de
consultas vazias e preservação do snapshot anterior. Atualize as duas documentações citadas,
execute todas as validações da E03 e não declare sucesso com teste obrigatório falhando ou não
executado. Marque #concluida apenas após o aceite; se houver impedimento real, marque #bloqueada e
documente causa, evidência, impacto e ação. Preencha Evidências e handoff e forneça resumo final
conciso. Não crie commit, não publique e não implante.
```

### Critérios de aceite

- [x] Nenhuma NS identificada no cabeçalho preserva o comportamento atual.
- [x] Uma ou várias NS iguais à do projeto permitem uma classificação e somente as consultas de
  ação aplicáveis.
- [x] Qualquer NS divergente impede mercado e ações; as listas dos dois fakes ficam vazias.
- [x] Uma folha correta e outra divergente também bloqueiam; comentários de revisão não bloqueiam.
- [x] O job devolve erro de validação compreensível e não expõe conexão, SQL ou stack trace.
- [x] Nenhum snapshot parcial é criado e um snapshot anterior permanece inalterado.
- [x] O método de conformidade é `10` e snapshots de método anterior são desatualizados.

### Validação obrigatória

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_compliance_analysis.py tests/server/test_jobs_api.py tests/server/test_compliance_api.py
.\.venv\Scripts\python.exe -m ruff check src/zeny_project_handler/application/project_compliance.py src/zeny_project_handler/application/compliance_analysis.py src/zeny_project_handler/application/errors.py src/zeny_project_handler_server/job_manager.py tests/integration/test_compliance_analysis.py tests/server/test_jobs_api.py tests/server/test_compliance_api.py tests/market_fakes.py
.\.venv\Scripts\python.exe -m mypy
```

Resultado esperado: todos os comandos retornam zero; os testes comprovam zero chamadas SQL nos
casos divergentes e ausência de publicação parcial.

### Bloqueios

Nenhum bloqueio conhecido.

### Riscos e mitigação

- **Validação tarde demais:** teste de ordem deve falhar se `classificar` for chamado antes do
  detector.
- **Duas extrações divergentes:** uma função compartilhada alimenta guarda, fatos e depois GMAX.
- **Bloqueio por comentário/anotação:** reutilizar a exclusão vigente e ter fixture explícita.

### Evidências e handoff

- Estado inicial: etapa iniciada em 2026-09-01 sobre `main`, com
  `git status --short --branch` limpo; não havia mudanças preexistentes a preservar.
- Contexto confirmado: depois de carregar a sessão semântica,
  `ExecutarAnaliseConformidade.executar` ainda chamava imediatamente
  `ClassificadorMercadoPort.classificar`; a extração da NS de cabeçalho ocorria apenas durante a
  construção posterior dos fatos, portanto não protegia o primeiro `SELECT`.
- Implementação: `project_compliance.py` expõe `detectar_notas_servico_cabecalho` e
  `NotaServicoCabecalhoDetectada`. O detector filtra comentários, usa somente a zona de cabeçalho,
  devolve valores únicos na ordem de leitura e agrega suas evidências; a mesma saída alimenta os
  fatos `documento.nota_servico`, `projeto.nota_servico_cabecalho` e
  `projeto.nota_servico_divergencia`. A ordenação semântica também foi reutilizada pelos gatilhos,
  sem alterar seus critérios.
- Guarda: `compliance_analysis.py` compara todos os valores detectados com
  `session.projeto.nome` imediatamente depois de carregar a sessão e antes do classificador. Zero
  valor ou somente valores iguais continua; qualquer diferente lança
  `NotaServicoCabecalhoDivergenteError`. O erro deriva de `ApplicationError`, então o mapeamento
  existente de `job_manager.py` já o publica como `VALIDATION_ERROR`; não foi necessário alterar o
  gerenciador de jobs.
- Atomicidade e versão: os ramos divergentes deixam vazias as listas de consultas dos fakes de
  mercado e ações, não publicam execução e preservam integralmente o snapshot anterior. O método
  passou de `9` para `10`, e a checagem de desatualização trata snapshots de método `9` como antigos.
- Cobertura: `tests/integration/test_compliance_analysis.py` cobre ausência, uma coincidência,
  coincidência em múltiplas folhas, evidências/ordem, comentário, divergência isolada, mistura de
  folha correta com uma ou mais divergentes, listas de consultas vazias e preservação do snapshot.
  `tests/server/test_jobs_api.py` comprova falha terminal `VALIDATION_ERROR`, mensagem operacional
  segura, zero chamadas aos dois ports e ausência de snapshot.
- Documentação sincronizada: `docs/arquitetura-conformidade.md` e
  `docs/especificacao-funcional.md` descrevem o detector, a guarda pré-SQL, o caso ausente, a
  correção operacional, a atomicidade e o método `10`.
- Validação obrigatória: Pytest dos três arquivos da E03 passou com `31 passed` em 31,19 s; Ruff
  terminou com `All checks passed!`; Mypy terminou com
  `Success: no issues found in 303 source files`.
- Validação adicional: os oito cenários focados novos passaram; nove testes unitários de NS e
  gatilhos passaram; `ruff format --check` confirmou cinco arquivos formatados e
  `git diff --check` retornou código zero (somente avisos informativos de conversão LF/CRLF).
- Handoff para E04: reutilizar exclusivamente `detectar_notas_servico_cabecalho`; cada item fornece
  `valor` e `evidencias` já deduplicados/ordenados. Para estado bloqueado, comparar os valores com a
  NS vigente sem executar os ports nem projetar o snapshot anterior como atual.
- Arquivos alterados: `src/zeny_project_handler/application/project_compliance.py`,
  `src/zeny_project_handler/application/compliance_analysis.py`,
  `src/zeny_project_handler/application/errors.py`,
  `tests/integration/test_compliance_analysis.py`, `tests/server/test_jobs_api.py`, as duas
  documentações citadas e este roadmap. `ports/market.py`, SQLs e gatilhos permaneceram sem mudança
  semântica.
- Escopo preservado: nenhuma NS de cabeçalho se tornou obrigatória; nenhum SQL, migração, contrato,
  commit, publicação ou implantação foi criado ou alterado.

## E04 — Projeção e contrato remoto GMAX — #concluida

### Objetivo

Criar um read model público e somente leitura que converta sessão semântica e último snapshot de
conformidade em estados GMAX explícitos, sem executar acesso externo.

### Por que agora

E03 fixa a fonte única da comparação de NS. Com ela concluída, a projeção pode explicar o bloqueio
e interpretar os fatos persistidos sem duplicar parsing ou permitir que o cliente conheça detalhes
do motor.

### Dependências e paralelismo

- Dependência: E03 `#concluida`.
- Pode avançar em paralelo com E02, evitando edição simultânea de OpenAPI/gateways.
- E05 depende do contrato final desta etapa.

### Escopo

- Novo arquivo planejado `src/zeny_project_handler_contracts/gmax.py`
- `src/zeny_project_handler_server/compliance_api.py`
- `src/zeny_project_handler_server/app.py`
- `src/zeny_project_handler_api_spec/app.py`
- `src/zeny_project_handler_client/ui/documentation_gateway.py`
- `tests/remote_gateways.py`
- `tests/contracts/test_models.py`
- `tests/contracts/test_openapi_snapshot.py`
- `tests/server/test_compliance_api.py`
- `tests/integration/test_compliance_analysis.py`
- `docs/api/openapi-v1.json`, `docs/api/README.md` e `docs/arquitetura-conformidade.md`

### Fora de escopo

- Construir widgets Qt.
- Persistir uma segunda tabela/snapshot GMAX.
- Chamar classificador/verificador durante `GET`.
- Expor a coleção genérica de fatos ou permitir consulta arbitrária por chave.

### Passos de implementação

1. Definir contratos fechados para: estado da NS de cabeçalho (`NOT_FOUND`, `MATCH`, `MISMATCH`),
   estado do snapshot (`NEVER_EXECUTED`, `CURRENT`, `STALE`, `BLOCKED_NS_MISMATCH`) e estado de cada
   ação (`NOT_EXECUTED`, `NOT_EXECUTED_NO_TRIGGER`, `NOT_EXECUTED_NO_SERVICE_CODES`, `EXECUTED`).
2. Definir `GmaxCheckDto` com tipo fixo (`IMPACTO_AMBIENTAL`/`SERVIDAO`), rótulo, detecção no PDF,
   descrição exata da ação, estado da consulta e `row_found: bool | None`. `row_found` só pode ser
   booleano quando o estado for `EXECUTED`.
3. Definir `GmaxSummaryResponse` com projeto/NS, NS de cabeçalho, estado/bloqueio, execução/data,
   `is_stale`, mercado opcional e exatamente os dois checks na ordem canônica.
4. Implementar projeção em `DocumentationComplianceApiService`: detectar cabeçalhos/gatilhos na
   sessão atual; obter o último snapshot; localizar o alvo projeto; extrair exclusivamente os fatos
   fechados. Com gatilho+códigos, o booleano da ação é resultado do `SELECT`; sem gatilho ou códigos,
   `row_found=None`. Zero snapshot usa `NEVER_EXECUTED`.
5. Se a guarda atual estiver divergente, usar `BLOCKED_NS_MISMATCH`; não apresentar mercado/linha do
   snapshot antigo como atual. Para snapshot desatualizado por método/regras/NS/serviços, marcar
   `STALE` e identificar visualmente que os valores pertencem à última execução.
6. Validar cardinalidade: exatamente um contexto de mercado no alvo projeto e exatamente um fato de
   resultado por ação quando a inferência exigir. Inconsistência devolve integridade em vez de
   adivinhar.
7. Expor `GET /api/v1/projects/{project_id}/gmax` na aplicação real/especificação e adicionar
   `get_gmax` ao `DocumentationGateway`, HTTP e direto. O método executa somente `GET` e mantém o
   retry de leitura vigente.
8. Cobrir rural/urbano, gatilho ausente, serviços ausentes, linha ausente/presente, zero snapshot,
   stale, divergência de NS e snapshot inconsistente. Espionar os ports e comprovar que o endpoint
   GMAX não os chama.
9. Regenerar OpenAPI e documentar os estados, nulabilidade e a origem auditável. Manter API
   `1.2.0` estabelecida em E01; se E04 for executada primeiro em uma branch isolada, fazer o mesmo
   incremento aqui e reconciliar sem segundo bump.

### Compatibilidade e rollback

- O contrato e a rota são aditivos na v1. Campos obrigatórios devem nascer com semântica fechada;
  extensões futuras usam novos valores apenas com negociação/versionamento apropriado.
- Não há migração ou escrita. Antes da release, rollback remove rota/DTO/gateway. Depois de clientes
  dependerem dela, preservar a rota ou responder explicitamente como capacidade indisponível; não
  reutilizar os enums com significado diferente.

### Prompt para uma sessão limpa

```text
Na raiz do repositório ZenyProjectHandler, execute somente a E04 — Projeção e contrato remoto GMAX —
de docs/roadmap-gmax-fluxos-ns.md. Leia eventuais AGENTS.md, o roadmap inteiro, README.md,
src/zeny_project_handler_contracts/compliance.py,
src/zeny_project_handler_contracts/enums.py,
src/zeny_project_handler_server/compliance_api.py, src/zeny_project_handler_server/app.py,
src/zeny_project_handler_api_spec/app.py,
src/zeny_project_handler_client/ui/documentation_gateway.py,
src/zeny_project_handler/application/project_compliance.py,
src/zeny_project_handler/application/compliance_analysis.py, tests/remote_gateways.py e os testes
citados. Confira git status --short --branch, preserve mudanças preexistentes, confirme E03
`#concluida` e valide que o detector de NS/gatilhos e o método 10 não divergiram.

Sincronize E04 para #em-andamento. Crie src/zeny_project_handler_contracts/gmax.py com enums fechados para cabeçalho,
snapshot e consulta e DTOs que exponham NS do projeto/cabeçalhos, bloqueio, última execução, stale,
mercado e exatamente dois checks: impacto ambiental e servidão. Cada check deve distinguir sem
execução, sem gatilho, sem códigos e executado; row_found é None salvo em EXECUTED. Projete os dados
no servidor a partir da sessão semântica e do último snapshot, filtrando fatos do alvo projeto e
falhando por integridade em cardinalidade impossível. Divergência atual usa BLOCKED_NS_MISMATCH e
não apresenta valores antigos como atuais. Exponha GET /api/v1/projects/{project_id}/gmax e o método
no gateway de documentação HTTP/direto. O GET jamais chama os ports SQL e não persiste nada.
Sincronize API 1.2.0, OpenAPI e docs/api/arquitetura.

Cubra todos os estados, rural/urbano, linha encontrada/não encontrada, snapshot inconsistente e
prova de zero I/O SQL. Execute todas as validações da E04; não declare sucesso com teste obrigatório
falhando ou não executado. Marque #concluida apenas após o aceite ou #bloqueada com causa, evidência,
impacto e desbloqueio. Preencha Evidências e handoff e encerre com resumo conciso. Não crie commit,
não publique e não implante.
```

### Critérios de aceite

- [x] A resposta possui exatamente os checks de impacto e servidão, na ordem canônica.
- [x] Mercado é `RURAL` ou `URBANO` somente quando comprovado pelo snapshot aplicável.
- [x] Sem gatilho e sem serviços são distintos de `EXECUTED` com `row_found=False`.
- [x] Linha ausente produz `EXECUTED/False`; uma ou mais linhas produzem `EXECUTED/True`.
- [x] Sem snapshot, stale e NS divergente possuem estados explícitos e não parecem atuais.
- [x] Snapshot inconsistente falha fechado por integridade.
- [x] Chamar `GET /api/v1/projects/{project_id}/gmax` não chama nenhum port SQL nem grava
  persistência.
- [x] Contrato, gateway, aplicação real, especificação, OpenAPI e docs estão sincronizados em 1.2.0.

### Validação obrigatória

```powershell
.\.venv\Scripts\python.exe -m pytest tests/server/test_compliance_api.py tests/integration/test_compliance_analysis.py tests/contracts/test_models.py tests/contracts/test_openapi_snapshot.py
.\.venv\Scripts\python.exe -m ruff check src/zeny_project_handler_contracts src/zeny_project_handler_server/compliance_api.py src/zeny_project_handler_server/app.py src/zeny_project_handler_api_spec/app.py src/zeny_project_handler_client/ui/documentation_gateway.py tests/remote_gateways.py tests/server/test_compliance_api.py tests/contracts
.\.venv\Scripts\python.exe -m mypy
```

Resultado esperado: código zero; OpenAPI contém a rota GMAX e os enums; testes comprovam todos os
estados e nenhuma chamada SQL no `GET`.

### Bloqueios

Nenhum bloqueio conhecido depois de E03.

### Riscos e mitigação

- **Confundir fato ausente com `False`:** codificar invariantes de nulabilidade nos DTOs e testar
  cada estado.
- **Ler fato regional como mercado do projeto:** filtrar pelo alvo de escopo projeto.
- **Mostrar snapshot antigo como atual:** estado explícito e prioridade ao bloqueio de cabeçalho.

### Evidências e handoff

- Estado inicial: E04 iniciada em 2026-09-01 sobre `main` depois de confirmar E03
  `#concluida`. O `git status --short --branch` já continha oito arquivos modificados por E03
  (`docs/arquitetura-conformidade.md`, `docs/especificacao-funcional.md`, este roadmap,
  `application/compliance_analysis.py`, `application/errors.py`,
  `application/project_compliance.py`, `tests/integration/test_compliance_analysis.py` e
  `tests/server/test_jobs_api.py`); todas as mudanças preexistentes foram preservadas.
- Dependência verificada: `detectar_notas_servico_cabecalho` continua sendo o detector único das NS
  de cabeçalho, `detectar_gatilhos_acoes_projeto` reutiliza a mesma ordenação semântica e
  `VERSAO_METODO_CONFORMIDADE` permanece `10`. A guarda segue antes da primeira chamada ao
  classificador de mercado.
- Contrato: o novo `src/zeny_project_handler_contracts/gmax.py` fecha estados de cabeçalho,
  snapshot, consulta, mercado e tipo de check. `GmaxSummaryResponse` exige exatamente impacto e
  servidão na ordem canônica; os validadores garantem `row_found` booleano somente em `EXECUTED`,
  identidade/data de execução coerentes, bloqueio explícito e nulabilidade de mercado.
- Projeção: `DocumentationComplianceApiService.get_gmax` lê a sessão atual e o último snapshot,
  filtra fatos pelo único alvo de escopo projeto e aceita exatamente um contexto rural/urbano.
  Gatilho mais códigos exige exatamente um fato booleano por ação; cardinalidade impossível devolve
  `409 INTEGRITY_ERROR`. `STALE` conserva valores identificados como pertencentes à última execução;
  `BLOCKED_NS_MISMATCH` tem prioridade e remove mercado/resultados antigos da resposta atual.
- Fronteiras remotas: a aplicação real e a especificação expõem
  `GET /api/v1/projects/{project_id}/gmax`; `DocumentationGateway`, o adaptador HTTP e os gateways
  direto/síncrono oferecem `get_gmax`. O HTTP usa o retry já limitado a leitura. API permaneceu em
  `1.2.0`, sem segundo incremento.
- Prova de somente leitura: os testes capturam os contadores de `FakeClassificadorMercado` e
  `FakeVerificadorAcoesConcluidas` e o histórico antes/depois de `get_gmax`; nenhum contador muda e
  nenhuma execução é criada. A rota autenticada também possui teste de delegação exclusivo ao read
  model.
- Cobertura: testes cobrem zero snapshot, cabeçalho ausente/coincidente/divergente, bloqueio com
  snapshot anterior, `CURRENT`/`STALE`, rural/urbano, gatilho ausente, códigos ausentes, linha
  encontrada/não encontrada, os dois checks fixos, mercado/resultados com cardinalidade impossível,
  nulabilidade do contrato, gateway HTTP/direto, rota real e schema OpenAPI.
- Documentação: `docs/api/README.md`, `docs/api/openapi-v1.json` e
  `docs/arquitetura-conformidade.md` registram rota, fontes, estados, nulabilidade, integridade e
  ausência de I/O SQL/escrita. O snapshot OpenAPI contém a operação `getProjectGmax`, os enums
  fechados e versão `1.2.0`.
- Validação obrigatória final: Pytest dos quatro arquivos da E04 passou com `71 passed` em 17,88 s;
  Ruff terminou com `All checks passed!`; Mypy terminou com
  `Success: no issues found in 304 source files`. O aviso não fatal foi apenas a impossibilidade
  preexistente de gravar `.pytest_cache`; `TEMP`/`TMP` e `--basetemp` ficaram sob `tmp/e04-final`.
- Validações adicionais: geração da OpenAPI retornou código zero; seus nove testes passaram; os 12
  testes focados GMAX e o teste isolado da rota passaram; Ruff do arquivo de integração passou;
  `ruff format --check` confirmou dez arquivos formatados e `git diff --check` retornou código zero
  (somente avisos informativos LF/CRLF).
- Handoff para E05: consumir somente `DocumentationGateway.get_gmax`. Exibir os checks na ordem do
  DTO e tratar `NEVER_EXECUTED`, `STALE` e `BLOCKED_NS_MISMATCH` antes de mercado/resultado; no
  bloqueio, `market` e `row_found` são nulos mesmo quando `last_execution_id` existe.
- Arquivos da E04: novo contrato `gmax.py`; `compliance_api.py`; rotas real/especificação;
  `documentation_gateway.py`; `tests/remote_gateways.py`; testes de servidor, integração e
  contratos; OpenAPI, docs da API, arquitetura e este roadmap. Nenhum widget Qt, SQL, migração,
  commit, publicação ou implantação foi criado ou alterado.

## E05 — Aba GMAX e sincronização Qt — #pendente

### Objetivo

Criar o painel GMAX somente leitura, inseri-lo na ordem de docks solicitada e mantê-lo sincronizado
com abertura, limpeza e reanálise do projeto.

### Por que agora

E04 estabiliza o DTO que o cliente deve apenas apresentar; E02 fornece a transição explícita para
estado vazio que o novo painel também precisa respeitar.

### Dependências e paralelismo

- Dependências: E02 e E04 `#concluida`.
- Não possui etapa paralela recomendada por editar `main_window.py`, gateway de documentação e
  testes de janela compartilhados.

### Escopo

- Novo arquivo planejado `src/zeny_project_handler_client/ui/gmax_panel.py`
- `src/zeny_project_handler_client/ui/main_window.py`
- `src/zeny_project_handler_client/ui/documentation_panel.py`
- `src/zeny_project_handler_client/ui/__init__.py` somente se o pacote exportar widgets
- `tests/conftest.py` e `tests/remote_gateways.py` se o fixture exigir ajuste
- Novo teste planejado `tests/integration/test_gmax_panel.py`
- `tests/integration/test_window.py`
- `tests/e2e/test_mvp_ui.py`
- `tests/unit/test_architecture.py` e testes de isolamento remoto aplicáveis
- `docs/especificacao-funcional.md` e `README.md`

### Fora de escopo

- Executar conformidade ou SQL diretamente no painel.
- Editar resultados, regras, PDFs, ações ou NS a partir de GMAX.
- Exportar o conteúdo GMAX.

### Passos de implementação

1. Criar `GmaxPanelWidget` com estado vazio, resumo da NS/cabeçalho/execução, mercado em destaque e
   uma tabela ou dois grupos fixos para impacto e servidão. Colunas mínimas: **PDF**, **Ação**,
   **Consulta** e **Resultado do SELECT**.
2. Mapear cada enum do contrato para texto português inequívoco: “Não executado”, “Não executado —
   gatilho ausente”, “Não executado — sem códigos de serviço”, “Sem linha” e “Linha encontrada”.
   Não usar apenas cor; garantir nomes acessíveis e `objectName`s estáveis.
3. Mostrar claramente `NEVER_EXECUTED`, `STALE` e `BLOCKED_NS_MISMATCH`. No bloqueio, indicar que
   projeto/PDF precisam ser corrigidos e reanalisados; não mascarar com último resultado.
4. Implementar `abrir_projeto`, `atualizar` e `limpar` usando somente
   `DocumentationGateway.get_gmax`; erros mostram estado seguro e mensagem/correlação existente.
5. Em `MainWindow`, criar `QDockWidget("GMAX")` com `objectName="gmaxDock"`, registrá-lo no menu
   **Exibir** e inseri-lo em `right_docks` depois de documentação e antes de exportação. Preservar
   tabificação, desacoplamento e restauração de estado.
6. Conectar `project_opened` ao GMAX e `project_cleared` a `limpar`. Adicionar ao painel de
   documentação um sinal de término de conformidade com projeto/status; emitir em sucesso e falha
   terminal para que GMAX recarregue inclusive o bloqueio por NS. O pipeline completo já reativa o
   projeto e deve atualizar sem duplicar chamadas desnecessárias.
7. Integrar habilitação/desabilitação na indisponibilidade de conexão e no estado global sem iniciar
   worker de escrita.
8. Testar todos os textos/estados, ausência de chamada SQL/escrita, troca/limpeza de projeto,
   término de job, ordem real das tabs, menu Exibir e persistência de layout.
9. Documentar a nova aba, fontes dos valores, estados e caráter somente leitura no README e na
   especificação funcional.

### Prompt para uma sessão limpa

```text
Na raiz do repositório ZenyProjectHandler, execute somente a E05 — Aba GMAX e sincronização Qt — de
docs/roadmap-gmax-fluxos-ns.md. Leia eventuais AGENTS.md, o roadmap inteiro, README.md,
src/zeny_project_handler_contracts/gmax.py,
src/zeny_project_handler_client/ui/documentation_gateway.py,
src/zeny_project_handler_client/ui/main_window.py,
src/zeny_project_handler_client/ui/documentation_panel.py,
src/zeny_project_handler_client/ui/project_panel.py, os padrões dos painéis existentes e os
testes/fixtures citados. Confira git status --short --branch, preserve mudanças preexistentes e
confirme E02 e E04 em `#concluida` e o contrato GMAX vigente.

Sincronize E05 para #em-andamento. Crie GmaxPanelWidget somente leitura usando get_gmax, com estado
vazio, resumo de NS/cabeçalho/execução, mercado e dois checks fixos de impacto/servidão. Mostre em
português e de forma acessível a detecção no PDF, a ação, se o SELECT não rodou/rodou e se encontrou
linha; diferencie NEVER_EXECUTED, STALE e BLOCKED_NS_MISMATCH sem apresentar dado antigo como atual.
Crie o dock GMAX, objectName gmaxDock, registre no menu Exibir e posicione depois de Documentação e
conformidade e antes de Exportar. Conecte project_opened, project_cleared e um sinal terminal da
reanálise de conformidade para abrir/atualizar/limpar. Respeite desconexão e estado de docks; não
importe domínio/SQL, não grave dados e não inicie consulta de conformidade.

Crie/ajuste testes Qt, isolamento, ordem das tabs e documentação. Execute todas as validações da
E05; não declare sucesso com teste obrigatório falhando ou não executado. Marque #concluida somente
após o aceite ou #bloqueada com causa, evidência, impacto e ação. Preencha Evidências e handoff e
resuma mudanças, validações e pendências. Não crie commit, não publique e não implante.
```

### Critérios de aceite

- [ ] A ordem visível é Resultados, Documentação e conformidade, GMAX, Exportar.
- [ ] GMAX aparece no menu Exibir, pode ser destacado/reacoplado e restaura seu estado.
- [ ] Mercado e os dois checks usam os valores/textos corretos para todos os enums.
- [ ] Estado vazio, stale e bloqueio por NS são compreensíveis sem depender de cor.
- [ ] Abrir/trocar projeto atualiza; recusar fluxo de E02 limpa; sucesso/falha de conformidade
  recarrega o painel correto.
- [ ] Desconexão desabilita acesso remoto de forma coerente e reconexão permite atualizar.
- [ ] O painel não contém SQL, `pyodbc`, regra de inferência de fatos ou operação de escrita.
- [ ] Testes Qt não deixam timers, threads ou diálogos pendentes.

### Validação obrigatória

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_gmax_panel.py tests/integration/test_window.py tests/e2e/test_mvp_ui.py tests/unit/test_architecture.py
.\.venv\Scripts\python.exe -m ruff check src/zeny_project_handler_client/ui tests/integration/test_gmax_panel.py tests/integration/test_window.py tests/e2e/test_mvp_ui.py tests/unit/test_architecture.py
.\.venv\Scripts\python.exe -m mypy
```

Resultado esperado: código zero; testes comprovam ordem, sincronização, estados e isolamento do
cliente. O caminho `tests/integration/test_gmax_panel.py` deve existir ao fim desta etapa.

### Bloqueios

Nenhum bloqueio conhecido depois de E02 e E04.

### Riscos e mitigação

- **Tab adicionada na posição errada:** verificar texto e ordem do `QTabBar`, não apenas associação
  entre docks.
- **Atualização perdida após falha:** emitir sinal terminal também no ramo de erro, com projeto
  conhecido.
- **Apresentação que confunde stale com atual:** estado textual proeminente e testes de conteúdo.

### Evidências e handoff

- Estado inicial: etapa não iniciada; aguarda E02 e E04.
- Evidências de implementação e validação: nenhuma enquanto a tag permanecer `#pendente`.

## E06 — Fluxo integrado, documentação e gate final — #pendente

### Objetivo

Comprovar os cinco pedidos no fluxo cliente-servidor completo, fechar documentação cruzada e executar
o gate oficial sem regressões.

### Por que agora

Somente depois das fronteiras servidor, contrato e Qt concluídas é possível verificar as corridas,
o reset coordenado, o bloqueio pré-SQL e a atualização GMAX como um único comportamento observável.

### Dependências e paralelismo

- Dependências: E01, E02, E03, E04 e E05 `#concluida`.
- Não paralelizar: esta é a consolidação final e pode ajustar testes/documentação de todas as etapas.

### Escopo

- Testes existentes e novos afetados pelas cinco etapas.
- `README.md`
- `docs/especificacao-funcional.md`
- `docs/arquitetura-conformidade.md`
- `docs/api/README.md` e `docs/api/openapi-v1.json`
- `docs/inventario-paridade-cliente-servidor.md` se a nova operação exigir registro no inventário
- Este roadmap, apenas para registrar estados/evidências finais.

### Fora de escopo

- Nova funcionalidade além do necessário para satisfazer critérios já definidos.
- Smoke real do SQL Server, build de release, publicação, implantação ou commit.

### Passos de implementação

1. Criar/estender um cenário integrado com gateway direto: criar NS, tentar duplicar e recusar/abrir;
   tentar abrir NS inexistente e recusar/criar; confirmar contagem e projeto ativo em cada ramo.
2. Validar busca e resolução de uma NS que não está na primeira página, inclusive seleção após
   filtro e estado inicial em todos os cancelamentos.
3. Usar fixtures sintéticas com cabeçalho coincidente para produzir rural/urbano e as quatro
   combinações de impacto/servidão com linha e sem linha; conferir GMAX e quantidade exata de
   chamadas dos fakes.
4. Usar cabeçalho divergente para comprovar zero chamadas a mercado/ações, job de validação, nenhum
   snapshot novo e GMAX bloqueado depois da atualização.
5. Verificar tab order, menu Exibir, limpeza dos painéis, reconexão e ausência de recursos Qt
   pendentes.
6. Revisar toda a documentação para que nomes, API `1.2.0`, método `10`, estados, mensagens e
   invariantes coincidam. Regenerar OpenAPI uma última vez e revisar o diff por remoções acidentais.
7. Executar o gate oficial. Corrigir apenas regressões relacionadas ao escopo; não reduzir cobertura,
   rigor de testes, regras Ruff/Mypy ou limites de complexidade para obter verde.
8. Sincronizar o índice/detalhes do roadmap e registrar evidências objetivas da definição global de
   pronto.

### Prompt para uma sessão limpa

```text
Na raiz do repositório ZenyProjectHandler, execute somente a E06 — Fluxo integrado, documentação e
gate final — de docs/roadmap-gmax-fluxos-ns.md. Leia eventuais AGENTS.md, o roadmap inteiro,
README.md, pyproject.toml, IniciarTestes.bat, os arquivos alterados nas E01–E05, a documentação viva
citada e os testes correspondentes. Confira git status --short --branch, preserve mudanças
preexistentes, confirme todas as dependências #concluida e verifique se o código não divergiu dos
critérios globais.

Sincronize E06 para #em-andamento. Adicione ou consolide testes integrados que provem: busca de NS;
duplicidade com abrir/recusar; NS inexistente com criar/recusar; corrida servidor; estado inicial;
GMAX rural/urbano e impacto/servidão com SELECT executado ou não; divergência de cabeçalho com zero
chamadas SQL, nenhum snapshot novo e GMAX bloqueado; ordem e limpeza dos docks. Use somente fakes e
fixtures sintéticas, sem SQL Server real. Revise README, especificação, arquitetura, API e inventário
de paridade quando aplicável; regenere OpenAPI e mantenha API 1.2.0 e método 10.

Execute os testes focados e .\IniciarTestes.bat. Não declare sucesso se qualquer validação
obrigatória falhar ou não for executada e não enfraqueça gates. Quando toda a definição global de
pronto estiver comprovada, marque E06 e seu índice #concluida e registre arquivos, decisões,
comandos e resultados em Evidências e handoff. Se houver impedimento real, marque #bloqueada com
causa, evidência, impacto e ação de desbloqueio. Termine com resumo conciso. Não crie commit, não
publique, não consulte ambiente real e não implante.
```

### Critérios de aceite

- [ ] Cada item da definição global de pronto possui teste, inspeção ou evidência registrada.
- [ ] O cenário integrado cobre todos os ramos Sim/Não e prova ausência de mutações indevidas.
- [ ] O cenário divergente comprova zero chamadas SQL, nenhum snapshot novo e GMAX bloqueado.
- [ ] API real/especificação/OpenAPI, gateways direto/HTTP e cliente usam o mesmo contrato 1.2.0.
- [ ] README, especificação, arquitetura e inventário aplicável descrevem o comportamento entregue.
- [ ] Não há timers, threads, diálogos ou operações globais pendentes ao encerrar os testes Qt.
- [ ] O gate oficial passa sem redução de qualidade ou cobertura.

### Validação obrigatória

```powershell
.\.venv\Scripts\python.exe -m pytest tests/server/test_project_document_api.py tests/server/test_compliance_api.py tests/server/test_jobs_api.py tests/integration/test_project_http_gateway.py tests/integration/test_compliance_analysis.py tests/integration/test_gmax_panel.py tests/integration/test_window.py tests/e2e/test_mvp_ui.py tests/contracts/test_models.py tests/contracts/test_openapi_snapshot.py
.\IniciarTestes.bat
git diff --check
git status --short
```

Resultado esperado: todos os comandos retornam zero, salvo `git status --short`, que deve listar
somente os arquivos intencionalmente alterados pelas etapas e mudanças preexistentes preservadas.

### Bloqueios

Nenhum bloqueio conhecido depois da conclusão de E01–E05.

### Riscos e mitigação

- **Teste integrado mascarar falha com fake permissivo:** usar contadores/argumentos exatos dos
  fakes de mercado e ações.
- **Documentação divergente do contrato:** regenerar OpenAPI e revisar enums/rotas contra o código.
- **Correção fora de escopo durante o gate:** registrar a falha, localizar a regressão e evitar
  refatoração não necessária.

### Evidências e handoff

- Estado inicial: etapa não iniciada; aguarda E01–E05.
- Evidências de implementação e validação: nenhuma enquanto a tag permanecer `#pendente`.
