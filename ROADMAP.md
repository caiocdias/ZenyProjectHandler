# Roadmap — classificação rural/urbana pelo SQL Server externo

## Objetivo e resultado esperado

Substituir a classificação rural/urbana inferida de `MetadadosProjeto.tipo_servico` ou de campos
do PDF por uma consulta somente leitura ao SQL Server do sistema de Notas de Serviço. Em toda
execução de conformidade, o servidor deve usar a NS de 10 dígitos que é o nome do projeto, executar
uma consulta parametrizada equivalente a:

```sql
SELECT NOTAS_COD_MERCADO FROM TB_NOTAS WHERE NOTAS_NUM_NS = ?;
```

e aceitar somente `RURAL` ou `URBANO`. O resultado deve produzir os fatos
`rede.contexto_rural` ou `rede.contexto_urbano` nos alvos de projeto e região, preservando o motor
de regras como responsável por aplicar apenas as regras cujo `when` é atendido.

## Como usar este roadmap

Execute uma etapa por sessão limpa do Codex, na ordem permitida pelas dependências. Ao iniciar,
sincronize a tag do índice e do detalhe para `#em-andamento`; só use `#concluida` depois de cumprir
todo o aceite e executar as validações obrigatórias. Registre comandos, resultados e decisões em
“Evidências e handoff”.

## Contexto confirmado

- A raiz Git é este diretório e estava limpa na criação do roadmap, na branch `main`, commit
  `8b4babb`.
- O projeto usa Python 3.11–3.13, arquitetura em domínio/aplicação/portas/adaptadores, FastAPI no
  servidor, cliente Qt e SQLite apenas como persistência própria. Dependências e comandos estão em
  `pyproject.toml`, `server/pyproject.toml` e nos arquivos `requirements-*.lock`.
- A NS é validada por `domain/project_metadata.py::normalizar_numero_ns` como texto com exatamente
  10 dígitos e é persistida em `Projeto.nome`. A coluna externa `NOTAS_NUM_NS` é `bigint`; portanto,
  zeros à esquerda devem continuar preservados no domínio, mas o valor vinculado ao SQL deve ser
  convertido para inteiro somente no adaptador.
- Hoje `application/project_compliance.py::_network_context` classifica pelo
  `MetadadosProjeto.tipo_servico` ou por campo rotulado extraído do cabeçalho PDF. O mesmo arquivo
  publica o contexto para alvos de projeto e região e usa esse contexto em provedores regionais.
- `application/compliance_evaluation.py` já ignora uma regra quando alguma condição `when` falha
  ou não possui fato. O seed `adapters/compliance/data/regras_conformidade_v1.json` tem 39 regras;
  22 já usam `rede.contexto_urbano` ou `rede.contexto_rural` em `when`. Portanto não é necessário
  criar um filtro paralelo no avaliador: é necessário trocar e tornar obrigatória a fonte dos fatos
  de contexto, além de proteger a paridade do catálogo por teste.
- `application/compliance_analysis.py::ExecutarAnaliseConformidade` é a fronteira transacional que
  cria o snapshot. Ela é usada tanto pelo pipeline completo em `application/mvp_workflow.py` quanto
  pela reanálise explícita servida por `zeny_project_handler_server/compliance_api.py`.
- A identidade do snapshot inclui a assinatura dos fatos. Uma mudança de `RURAL` para `URBANO`
  deve, portanto, gerar nova execução quando a conformidade for reaplicada. A versão atual do método
  é `7` e precisa ser incrementada ao mudar a semântica.
- O servidor roda em container Linux baseado em Debian slim, como usuário não root. Configuração
  entra por `ServerSettings`, Compose e `.env`; `.env` é ignorado pelo Git e pelo contexto Docker.
  O arquivo local existente não foi lido, para não expor segredos.
- O kit de release é gerado por `scripts/build_release.py` a partir de
  `server/compose.release.yaml`, `server/env.release.example` e `server/LEIA-ME-SERVIDOR.md`.
- A documentação oficial da Microsoft confirma o pacote `msodbcsql18` para Debian 12/13 e a
  necessidade do gerenciador ODBC no Linux. O projeto oficial `pyodbc` implementa DB-API 2.0 e usa
  parâmetros posicionais `?`, adequados à consulta requerida.

## Escopo incluído

- Tipo de domínio e porta para classificar o mercado de uma NS.
- Adaptador SQL Server somente leitura, parametrizado, com timeout e encerramento determinístico da
  conexão.
- Configuração secreta no ambiente do servidor, suporte no container, Compose local/operacional e
  kit de release.
- Consulta em cada execução de conformidade, tanto no pipeline completo quanto na ação de
  reanálise.
- Substituição completa da inferência por metadado/OCR pelos fatos vindos do banco externo.
- Propagação do mesmo mercado aos alvos de projeto e região.
- Falha fechada e segura para indisponibilidade, NS ausente, valor nulo/inválido ou resultado
  ambíguo, sem publicar snapshot parcial e sem revelar a string de conexão.
- Testes unitários, de integração, servidor, arquitetura/release e teste opt-in contra SQL Server
  real.
- Atualização da documentação de arquitetura, configuração, operação e regras.

## Fora de escopo

- Escrever, migrar ou administrar o banco externo.
- Replicar `TB_NOTAS`, criar cache durável ou persistir a credencial no SQLite, backup, DTO ou
  cliente.
- Consultar o mercado ao criar, abrir ou renomear projeto; a leitura ocorre quando a conformidade é
  executada, usando a NS vigente.
- Expor ou editar a conexão SQL Server pela interface/API.
- Detectar automaticamente que um snapshot antigo ficou desatualizado quando apenas o sistema
  externo mudou; sem versão ou instante de alteração na consulta fornecida, a atualização é
  capturada na próxima execução de conformidade.
- Alterar a semântica genérica de `when`/`unless`/`must` ou reescrever regras que já possuem a guarda
  correta. Uma regra rural/urbana sem guarda encontrada pela auditoria deverá ser corrigida dentro
  deste escopo.
- Manter fallback por metadado, texto/OCR, valor anterior ou padrão local.

## Restrições e invariantes

- Executar exatamente uma leitura de mercado por execução de conformidade; não consultar por alvo
  ou por regra.
- Usar parâmetro vinculado (`?`) e nunca interpolar a NS no SQL.
- Preservar a NS como string de 10 dígitos fora do adaptador e converter para `int` apenas ao ligar o
  parâmetro `bigint`.
- Tratar a string de conexão como segredo: campo com `repr=False`, ausente de logs, mensagens de
  erro, imagem, volume, backups, respostas HTTP e artefato cliente.
- O login externo deve possuir somente permissão de conexão e `SELECT` sobre as colunas necessárias
  de `TB_NOTAS`; o aplicativo não deve executar DDL ou escrita.
- Ausência, `NULL`, valor diferente de `RURAL`/`URBANO`, múltiplas linhas ou falha de conexão/query
  interrompem a conformidade. Nenhum desses casos autoriza inferência local ou aplicação dos dois
  conjuntos de regras.
- Uma falha externa não publica `ExecucaoConformidade` parcial. Resultados semânticos já persistidos
  continuam intactos.
- As duas entradas de conformidade devem receber a mesma dependência composta no servidor.
- O fato deve ter confiança `1`, origem auditável sem dados de conexão e nenhuma evidência PDF.
- O método de conformidade deve mudar de versão para invalidar semanticamente snapshots anteriores.
- O container continua não root, somente leitura fora de `/data` e `/tmp`, e sem segredo em `ARG`,
  `ENV` do Dockerfile ou camadas da imagem.

## Hipóteses e decisões em aberto

1. **Driver proposto:** `pyodbc` com Microsoft ODBC Driver 18 no container Debian. Impacto: adiciona
   dependência Python, repositório/pacote de sistema, licença/EULA e itens à SBOM. Antes de fixar a
   versão, a E01 deve conferir compatibilidade com Python 3.11–3.13 e com o processo de build
   reprodutível do repositório.
2. **Formato proposto da configuração:** uma variável obrigatória e opaca
   `ZENY_MARKET_SQLSERVER_CONNECTION_STRING` no `.env`, contendo a string ODBC completa, e uma
   variável numérica opcional `ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS`. Isso evita montar credenciais
   por concatenação e acomoda servidor, porta/instância, banco, usuário, senha, criptografia e
   certificado. O nome definitivo deve permanecer consistente em código, Compose e documentação.
3. **Autenticação/TLS:** presume-se autenticação SQL com `Encrypt=yes` e validação de certificado
   (`TrustServerCertificate=no`). Autenticação integrada/Kerberos ou CA privada muda a instalação e
   deve ser confirmada pelo responsável do SQL Server antes da homologação E04.
4. **Cardinalidade:** presume-se uma única linha por `NOTAS_NUM_NS`. Como a consulta fornecida não
   declara unicidade, o adaptador deve detectar mais de uma linha e falhar como inconsistência, em
   vez de escolher silenciosamente.
5. **Schema:** a consulta deve usar `TB_NOTAS` sem qualificação, conforme solicitado. Caso o login
   não tenha o schema correto como padrão, o proprietário do banco deve informar a qualificação e
   autorizar a alteração antes da E04.
6. **Disponibilidade:** a decisão é falhar fechado, sem fallback, tanto no pipeline completo quanto
   na reanálise. Isso torna o SQL Server uma dependência operacional da conformidade, mas não das
   consultas de projetos ou snapshots já existentes.

## Definição global de pronto

- Uma execução para uma NS conhecida como `URBANO` publica somente `rede.contexto_urbano` em
  projeto/regiões; uma NS `RURAL` publica somente `rede.contexto_rural`.
- Regras do mercado oposto não geram achado; regras do mercado retornado continuam sendo avaliadas
  conforme seus demais fatos.
- Metadado e texto PDF conflitantes não alteram a classificação externa.
- A consulta é parametrizada com inteiro, usa apenas a coluna/tabela solicitada e fecha cursor e
  conexão em sucesso ou erro.
- Falhas e dados externos inválidos encerram o job com erro seguro e não criam snapshot parcial.
- A configuração está documentada e propagada pelos três Compose, pelo kit servidor e pelo
  lançador local, sem vazar segredo.
- Dependências Python/sistema, notices e SBOM estão coerentes e o container continua atendendo aos
  gates de segurança.
- Ruff, formatação, Mypy, Pytest com cobertura, complexidade, testes de arquitetura/release e smoke
  real aprovado passam com evidências registradas.

## Índice de etapas

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Porta e gateway SQL Server | #pendente | nenhuma | Classificador externo isolado, seguro e testado |
| E02 | Troca da fonte no motor de conformidade | #pendente | E01 | Mercado externo governa fatos e aplicabilidade nos dois fluxos |
| E03 | Distribuição, documentação e regressão completa | #pendente | E01, E02 | Operação/release documentados e gate automatizado verde |
| E04 | Homologação com o SQL Server real | #bloqueada | E03 | Evidência real de URBANO, RURAL e falha fechada |

---

## E01 — Porta e gateway SQL Server — #pendente

### Objetivo

Criar uma fronteira de aplicação tipada para obter `RURAL` ou `URBANO` por NS e um adaptador
SQL Server somente leitura que execute a consulta parametrizada, sem ainda substituir a fonte usada
pelo motor.

### Por que agora

Isola o maior risco técnico — driver, contrato de retorno e tratamento de falhas — antes de alterar
a semântica e a identidade das execuções de conformidade.

### Dependências e paralelismo

- Dependências: nenhuma.
- Pode haver pesquisa de compatibilidade do driver em paralelo com os testes de domínio, mas os
  arquivos de dependências e `Dockerfile` devem ter um único responsável para evitar conflito.
- Insumos: documentação oficial do ODBC Driver 18, suporte atual do `pyodbc` e política de locks do
  repositório.

### Escopo

- Novo tipo de domínio, provavelmente em `domain/market.py` ou caminho equivalente coerente.
- Nova porta em `ports/market.py` ou caminho equivalente.
- Novo adaptador em `adapters/market/sql_server.py`.
- `pyproject.toml`, `server/pyproject.toml`, `requirements-server.lock`,
  `requirements-development.lock`, `Dockerfile`, `THIRD_PARTY_NOTICES.md` e geração de SBOM quando
  exigido pela dependência escolhida.
- Testes unitários dedicados ao contrato e adaptador.

### Fora de escopo

- Injetar o gateway no servidor ou alterar `analisar_conformidade_projeto`.
- Alterar JSON de regras, DTOs ou interface.
- Usar um SQL Server real nos testes obrigatórios desta etapa.

### Passos de implementação

1. Definir um enum imutável com valores externos exatos `RURAL` e `URBANO`, e uma porta callable ou
   protocolo que receba a NS normalizada e devolva esse enum.
2. Implementar o adaptador com factory de conexão injetável para testes, conexão curta por consulta,
   timeout configurável e fechamento determinístico.
3. Executar `SELECT NOTAS_COD_MERCADO FROM TB_NOTAS WHERE NOTAS_NUM_NS = ?;` vinculando
   `int(normalizar_numero_ns(ns))`; ler no máximo duas linhas para detectar cardinalidade inválida.
4. Normalizar apenas espaços/capitalização do retorno e recusar zero linhas, `NULL`, valores fora do
   enum ou mais de uma linha com erros de aplicação específicos e mensagens sem infraestrutura.
5. Traduzir exceções do driver em erro esperado de dependência externa, preservando a causa para o
   log estruturado sem incorporar a string de conexão na mensagem pública.
6. Adicionar e fixar dependências Python/sistema; adaptar o build multistage e a SBOM mantendo a
   imagem não root e sem segredos.
7. Cobrir SQL exato, parâmetro inteiro, zeros à esquerda, ambos os retornos, cardinalidade, `NULL`,
   valor inválido, timeout/erro e fechamento de recursos com doubles sem rede.

### Prompt para uma sessão limpa

```text
Na raiz do repositório, execute a etapa E01 — Porta e gateway SQL Server do ROADMAP.md. Leia primeiro
as instruções aplicáveis do repositório, o ROADMAP.md inteiro, README.md, pyproject.toml,
server/pyproject.toml, requirements-server.lock, requirements-development.lock, Dockerfile,
THIRD_PARTY_NOTICES.md, src/zeny_project_handler/domain/project_metadata.py,
src/zeny_project_handler/ports e src/zeny_project_handler/adapters; confira também git status e
preserve qualquer mudança preexistente. Verifique que as dependências da etapa estão satisfeitas e
que o código não divergiu do plano. Atualize E01 no índice e no detalhe para #em-andamento antes de
editar.

Implemente um enum tipado RURAL/URBANO, uma porta que classifica uma NS e um adaptador SQL Server
somente leitura via pyodbc/ODBC Driver 18. A consulta deve ser exatamente
SELECT NOTAS_COD_MERCADO FROM TB_NOTAS WHERE NOTAS_NUM_NS = ?;, deve vincular como inteiro a NS já
validada de 10 dígitos, nunca interpolá-la, e deve detectar zero, uma ou múltiplas linhas. Aceite
somente RURAL/URBANO após normalização limitada, feche cursor/conexão em qualquer caminho e traduza
falhas para erros seguros sem expor a conexão. Torne a conexão injetável para testes. Atualize os
manifestos/locks, Dockerfile, notices e SBOM afetados, confirmando nas fontes oficiais versões
compatíveis com Python 3.11–3.13 e Debian da imagem. Não conecte ainda esse gateway ao motor, não
altere regras/DTOs/UI e não use credencial real em teste ou fixture.

Crie/atualize testes para o SQL e parâmetro enviados, conversão de NS com zero inicial, RURAL,
URBANO, ausência, NULL, valor inválido, duplicidade, erro/timeout e fechamento de recursos. Execute
as validações listadas na etapa. Não declare sucesso com teste obrigatório falhando ou não
executado. Ao final, atualize para #concluida somente se todos os critérios forem atendidos; diante
de impedimento real, use #bloqueada e documente causa, evidência, impacto e ação de desbloqueio.
Preencha “Evidências e handoff” com arquivos, decisões, versões fixadas, comandos e resultados e
resuma mudanças, validações e pendências. Não crie commit, não publique e não implante sem pedido
explícito do usuário.
```

### Critérios de aceite

- [ ] A aplicação possui um único tipo canônico que não admite mercado diferente de `RURAL` ou
      `URBANO`.
- [ ] A porta não depende de `pyodbc`, SQLAlchemy, FastAPI ou servidor.
- [ ] O adaptador envia o SQL com `?` e o parâmetro Python inteiro, preservando a string da NS fora
      dessa fronteira.
- [ ] Zero/múltiplas linhas, `NULL`, valor inválido e falha técnica têm comportamento determinístico
      e seguro.
- [ ] Nenhum caminho de erro inclui a string de conexão, usuário, senha, host ou detalhe bruto do
      driver na mensagem pública.
- [ ] Dependências e imagem suportam o driver e continuam reproduzíveis/auditáveis.
- [ ] Testes não dependem de rede nem de SQL Server real.

### Validação obrigatória

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy
```

Resultado esperado: todos os comandos retornam código 0; os novos testes comprovam consulta,
binding, retornos e falhas. Se a mudança do Dockerfile não puder ser exercitada nessa sessão,
registrar a limitação para a E03, sem marcar como validada por inferência.

### Bloqueios

Nenhum bloqueio conhecido para implementar e testar com doubles. A escolha final de autenticação e
cadeia de certificados continua aberta para a homologação E04.

### Riscos e mitigação

- **Wheel/ABI ausente:** confirmar wheel ou toolchain para todas as versões Python suportadas e
  exercitar o build no container.
- **Pacote Microsoft não reprodutível:** fixar versão/repositório conforme a disciplina existente e
  registrar componente/licença na SBOM/notices.
- **SQL injection ou conversão implícita lenta:** usar `?` com `int`, sem concatenação.
- **Vazamento em exceção:** encapsular erros do driver e testar `str`/`repr` das exceções públicas.

### Evidências e handoff

- Arquivos alterados: ainda não iniciado.
- Decisões tomadas: ainda não iniciado.
- Validações executadas: ainda não iniciado.
- Observações para E02: ainda não iniciado.

---

## E02 — Troca da fonte no motor de conformidade — #pendente

### Objetivo

Fazer toda execução de conformidade consultar o gateway externo uma vez e usar exclusivamente esse
resultado para fatos e decisões rurais/urbanas em alvos de projeto e região.

### Por que agora

Depende do contrato seguro da E01 e realiza a mudança funcional solicitada sem misturar ainda a
revisão completa de operação/release.

### Dependências e paralelismo

- Dependência obrigatória: E01 `#concluida`.
- A alteração do caso de uso, dos provedores e da composição deve ser coordenada na mesma sessão,
  porque as assinaturas mudam juntas.
- Testes de aplicabilidade podem ser preparados em paralelo somente se não editarem os mesmos
  trechos de `project_compliance.py`.

### Escopo

- `application/compliance_analysis.py`, `application/compliance_fact_providers.py` e
  `application/project_compliance.py`.
- `zeny_project_handler_server/config.py`, `.env-example`, `compose.yaml`, `compose.local.yaml`,
  `server/compose.release.yaml`, `server/env.release.example` e testes de configuração.
- `zeny_project_handler_server/composition.py` e
  `zeny_project_handler_server/compliance_api.py`.
- Erros seguros do job em `zeny_project_handler_server/job_manager.py` e contrato de erro apenas se
  necessário para distinguir dependência externa.
- Testes unitários, de integração e servidor diretamente afetados.

### Fora de escopo

- Consultar o banco ao criar/renomear projeto.
- Persistir mercado no agregado `Projeto` ou em tabela própria.
- Alterar o resultado manualmente pela UI.
- Mudar regras sem evidência da auditoria de guardas.

### Passos de implementação

1. Tornar o classificador uma dependência obrigatória de `ExecutarAnaliseConformidade`; depois de
   carregar a sessão e respeitando cancelamento, consultar uma vez com `sessao.projeto.nome`.
2. Passar o enum obtido como entrada explícita da análise pura e do `ContextoProvedorFatos`, de modo
   que provedores regionais não voltem a ler metadado/OCR por conta própria.
3. Publicar somente o fato correspondente, com confiança `1`, origem “consulta ao cadastro de Notas
   de Serviço” ou texto equivalente estável, sem evidência PDF, em projeto e todas as regiões.
4. Remover `_network_context` baseado em sessão, `_explicit_context_evidence`, padrões exclusivos de
   contexto e qualquer fallback de `MetadadosProjeto.tipo_servico`/cabeçalho. Manter
   `tipo_servico` como metadado geral se ainda for usado fora desta classificação.
5. Garantir que cálculos regionais condicionados por contexto, como transformador/poste, recebam o
   mesmo enum externo.
6. Adicionar a string obrigatória e secreta e o timeout validado a `ServerSettings`, com
   `repr=False`; propagar as variáveis por todos os Compose e exemplos `.env`, sem ler ou alterar o
   `.env` real.
7. Compor uma única instância/configuração de gateway para os analisadores usados pelo pipeline
   completo e pela reanálise explícita; nenhum caminho pode construir um analisador sem a porta.
8. Incrementar `VERSAO_METODO_CONFORMIDADE`, ajustar expectativas e provar que snapshots antigos
   ficam desatualizados.
9. Mapear falha esperada do cadastro externo para job falho com mensagem acionável, correlação e sem
   segredo; confirmar que nenhum snapshot é salvo.
10. Substituir fixtures que usavam `tipo_servico="Rede urbana/rural"` por fakes explícitos do
   classificador e adicionar casos de conflito entre banco, metadado e PDF.

### Prompt para uma sessão limpa

```text
Na raiz do repositório, execute a etapa E02 — Troca da fonte no motor de conformidade do ROADMAP.md.
Leia primeiro as instruções aplicáveis, o ROADMAP.md inteiro, git status e os arquivos relevantes:
src/zeny_project_handler/application/compliance_analysis.py,
compliance_fact_providers.py, project_compliance.py, compliance_evaluation.py,
src/zeny_project_handler_server/config.py, composition.py, compliance_api.py e job_manager.py, além
dos arquivos Compose, exemplos .env e testes de conformidade/configuração/composição. Preserve
mudanças preexistentes. Confirme que E01 está realmente
#concluida e que as interfaces implementadas não divergiram do plano. Atualize E02 no índice e no
detalhe para #em-andamento antes de editar.

Injete obrigatoriamente a porta da E01 em ExecutarAnaliseConformidade, consulte-a exatamente uma vez
por execução usando o nome/NS vigente do projeto e passe o enum externo à análise e aos provedores.
O resultado URBANO deve publicar apenas rede.contexto_urbano e RURAL apenas
rede.contexto_rural, com confiança 1 e origem auditável sem evidência PDF, no alvo projeto e em
todas as regiões. Remova por completo a classificação por MetadadosProjeto.tipo_servico e por
campo/texto/OCR de cabeçalho, sem remover metadados que tenham outra finalidade. Use o mesmo
gateway nos analisadores do pipeline completo e da reanálise explícita. Incremente a versão do
método, mantenha a classificação dentro da assinatura do snapshot e faça falhas externas encerrarem
o job com erro seguro sem publicar ExecucaoConformidade parcial. Adicione a configuração obrigatória
ZENY_MARKET_SQLSERVER_CONNECTION_STRING e o timeout positivo a ServerSettings, com segredo fora de
repr/core settings/logs, e propague as variáveis por todos os Compose e exemplos .env sem tocar no
.env real. Não crie um segundo filtro de regras: preserve a semântica existente de when.

Atualize todos os testes afetados com fakes explícitos e cubra URBANO, RURAL, metadado/PDF
conflitante ignorado, uma consulta por execução, os dois caminhos do servidor, mudança de mercado
gerando nova identidade, snapshot antigo desatualizado, cancelamento e falha sem persistência.
Execute as validações da etapa e não declare sucesso com teste obrigatório falhando ou não
executado. Atualize para #concluida somente após o aceite; se houver impedimento real, use
#bloqueada com causa, evidência, impacto e ação. Preencha “Evidências e handoff” com arquivos,
decisões, comandos e resultados e entregue resumo conciso. Não crie commit, publique ou implante sem
autorização explícita.
```

### Critérios de aceite

- [ ] Cada execução de conformidade consulta uma vez a NS vigente; nenhuma consulta ocorre por
      regra ou alvo.
- [ ] Pipeline completo e reanálise explícita usam a mesma implementação externa.
- [ ] Projeto e todas as regiões recebem somente o fato coerente com o retorno externo.
- [ ] Metadado/PDF ausente ou conflitante não muda nem impede uma classificação externa válida.
- [ ] Nenhum código produtivo ainda usa `tipo_servico` ou texto/OCR para definir rural/urbano.
- [ ] As regras do mercado oposto não aparecem nos achados; as do mercado correto continuam
      avaliadas pelos demais fatos.
- [ ] Mudança do mercado entre execuções produz nova assinatura/execução; repetição do mesmo mercado
      permanece idempotente.
- [ ] Falha externa/cancelamento não publica snapshot e chega ao cliente como erro seguro.
- [ ] A versão do método foi incrementada e snapshots anteriores são considerados desatualizados.
- [ ] Configuração ausente/placeholder/timeout inválido falha cedo, não aparece em `repr` e está
      presente em todos os Compose/exemplos sem valor real.

### Validação obrigatória

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_compliance.py tests\unit\test_transformer_compliance_provider.py tests\unit\test_span_compliance_provider.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_compliance_analysis.py tests\integration\test_mvp_workflow.py -q
.\.venv\Scripts\python.exe -m pytest tests\server\test_config.py tests\server\test_compliance_api.py tests\server\test_jobs_api.py -q
.\.venv\Scripts\python.exe -m mypy
```

Se um caminho listado não existir após a inspeção (por exemplo, teste de composição com outro
nome), localizar o arquivo real com `rg` e registrar a substituição. Resultado esperado: código 0,
provas explícitas dos dois mercados, duas entradas do servidor e falha sem snapshot.

### Bloqueios

Nenhum bloqueio conhecido depois da E01. Credenciais reais não são necessárias: os testes desta
etapa devem injetar fakes e nunca alcançar rede.

### Riscos e mitigação

- **Uma das duas composições ficar no comportamento antigo:** teste de integração para pipeline e
  reanálise, com contador do fake.
- **Contexto não chegar às regiões:** asserção para todos os alvos regionais e regras de ambos os
  escopos.
- **Idempotência esconder reclassificação:** incluir o mercado nos fatos antes da assinatura e testar
  troca de retorno.
- **Regressão por remover OCR:** teste negativo com cabeçalho/metadado conflitantes.
- **Erro externo virar 500 opaco ou vazar detalhe:** erro de aplicação dedicado e teste do envelope
  do job/log seguro.

### Evidências e handoff

- Arquivos alterados: ainda não iniciado.
- Decisões tomadas: ainda não iniciado.
- Validações executadas: ainda não iniciado.
- Observações para E03: ainda não iniciado.

---

## E03 — Distribuição, documentação e regressão completa — #pendente

### Objetivo

Consolidar a dependência externa na distribuição e nos runbooks, auditar todas as regras
rurais/urbanas e fechar a regressão automatizada antes da homologação real.

### Por que agora

A interface e o comportamento já estarão estabilizados pelas E01/E02; esta etapa consolida
segurança de configuração, distribuição e evidência de que o produto completo continua íntegro.

### Dependências e paralelismo

- Dependências obrigatórias: E01 e E02 `#concluida`.
- Documentação pode avançar em paralelo aos testes, mas mudanças em Compose, Dockerfile, locks e
  scripts de release devem ser coordenadas.
- Não depende de acesso ao SQL Server real; use fakes/overrides nos gates automatizados.

### Escopo

- `scripts/build_release.py`, gates de artefato/SBOM e respectivos testes.
- `.env-example`, Compose e configuração implementados na E02, agora sob validação de distribuição.
- `ZenyProjectHandler.bat`/adaptador local se a nova variável exigir ajuste comprovado.
- `README.md`, `server/LEIA-ME-SERVIDOR.md`, `docs/operacao-servidor.md`,
  `docs/arquitetura-conformidade.md` e, se a decisão for arquiteturalmente relevante, novo ADR.
- Catálogo de regras, testes de paridade e suíte completa.

### Fora de escopo

- Inserir credencial real em arquivos versionados, scripts ou logs.
- Fazer deploy no host de produção.
- Considerar o healthcheck HTTP como prova de acesso ao SQL Server.

### Passos de implementação

1. Auditar a configuração feita na E02: variável obrigatória em todos os Compose, placeholder nos
   exemplos e ausência do segredo em `repr`, Dockerfile, imagem, volume, backup, cliente e logs.
2. Confirmar que fixtures e gates usam fakes/overrides sem alcançar rede e que o lançamento local
   repassa a variável sem ler, copiar ou registrar seu conteúdo.
3. Ajustar scripts/gates de release para aceitar a nova variável no kit, preservar o placeholder e
   listar `pyodbc`, ODBC/unixODBC e licenças na SBOM/notices.
4. Criar um teste de paridade que identifique toda regra cujo ID/título/descrição é rural/urbana e
   exija a guarda de mercado adequada; revisar as 22 guardas atuais sem alterar regras não
   relacionadas.
5. Atualizar a documentação para afirmar que SQL Server é a única fonte, descrever consulta,
   timeout/falha fechada, privilégio mínimo, TLS, conectividade do container, rotação do segredo e
   reanálise após mudança externa.
6. Adicionar um smoke opt-in, desabilitado sem ambiente explícito, que aceite NS de homologação e
   execute o adaptador real sem imprimir a conexão. Ele será usado obrigatoriamente na E04.
7. Executar o gate padrão e o build/gate de release; corrigir regressões sem reduzir cobertura,
   remover asserções ou relaxar segurança.

### Prompt para uma sessão limpa

```text
Na raiz do repositório, execute a etapa E03 — Distribuição, documentação e regressão completa do
ROADMAP.md. Leia primeiro as instruções aplicáveis, o ROADMAP.md inteiro, git status, README.md,
src/zeny_project_handler_server/config.py, os três arquivos Compose, .env-example,
server/env.release.example, server/LEIA-ME-SERVIDOR.md, Dockerfile, requirements-server.lock,
scripts/build_release.py, os gates de release/SBOM, docs/operacao-servidor.md,
docs/arquitetura-conformidade.md, o seed de regras e seus testes. Preserve mudanças preexistentes.
Confirme que E01 e E02 estão #concluida e que o código não divergiu. Atualize E03 no índice e no
detalhe para #em-andamento antes de editar.

Audite a configuração operacional implementada na E02: a variável obrigatória e secreta
ZENY_MARKET_SQLSERVER_CONNECTION_STRING e o timeout inteiro positivo devem permanecer fora de repr,
core settings, logs, imagem, volume, backup, API e cliente e estar consistentes em todos os Compose e
exemplos .env. Atualize Docker/dependências, scripts de release, SBOM e notices conforme a solução da
E01. Faça os testes normais usarem fakes/overrides sem rede. Crie um smoke opt-in seguro para a E04. Audite o seed
inteiro: toda regra semanticamente rural ou urbana deve ter a guarda rede.contexto_rural ou
rede.contexto_urbano correspondente; não crie filtro paralelo no avaliador. Atualize README,
operação e arquitetura com fonte única SQL Server, consulta por execução, privilégio SELECT mínimo,
TLS, timeout, falha fechada e reanálise para capturar mudança externa.

Execute as validações obrigatórias, incluindo o gate padrão e o build/gate de release quando Docker
estiver disponível. Não declare sucesso com teste obrigatório falhando ou não executado; registre
claramente qualquer limitação ambiental. Atualize E03 para #concluida somente após todos os critérios;
se houver impedimento real, use #bloqueada e documente causa, evidência, impacto e ação. Preencha
“Evidências e handoff” com arquivos, decisões, comandos e resultados e entregue resumo conciso. Não
crie commit, publique ou implante sem autorização explícita.
```

### Critérios de aceite

- [ ] Configuração ausente/placeholder/timeout inválido falha cedo e de modo seguro.
- [ ] A variável secreta está em todos os fluxos de Compose/kit e nunca em Dockerfile, imagem,
      cliente, backup ou log.
- [ ] Desenvolvimento e testes automatizados não requerem SQL Server real.
- [ ] O kit inclui driver/dependências/licenças/SBOM necessários e ainda passa os gates de artefato.
- [ ] Teste de paridade cobre todas as regras rurais/urbanas e confirma as 22 guardas atuais ou
      registra/corrige divergência comprovada.
- [ ] Documentação operacional permite a um administrador configurar conexão, TLS, privilégio e
      diagnóstico sem conhecer o código-fonte.
- [ ] Existe smoke opt-in que não roda acidentalmente e nunca imprime a conexão.
- [ ] Gate padrão completo e validação de release passam sem redução dos controles existentes.

### Validação obrigatória

```powershell
.\IniciarTestes.bat
docker compose --env-file .env-example -f compose.local.yaml config --quiet
.\.venv\Scripts\python.exe scripts\build_release.py --version 0.2.0
```

Resultado esperado: gate padrão com código 0; Compose válido com os placeholders versionados;
release recomposta com inspeções, SBOM e artefatos aprovados. Não ler nem registrar o conteúdo do
`.env` real na evidência. Se Docker não estiver disponível, a etapa não pode ser concluída até o
build ser executado em ambiente apto.

### Bloqueios

Nenhum bloqueio conhecido para automação e documentação. A configuração real permanece reservada à
E04 e não deve ser necessária para concluir esta etapa.

### Riscos e mitigação

- **`docker compose config` expandir segredo na saída:** usar `--quiet` e nunca capturar configuração
  renderizada.
- **Gates locais tentarem o banco real:** injeção explícita de fake e smoke protegido por marcador e
  variáveis próprias.
- **Release omitir pacote nativo:** inspeção por `dpkg-query`, import de `pyodbc` no container e SBOM.
- **Regra específica sem guarda:** teste de paridade baseado na definição, revisão humana do catálogo
  e correção localizada no JSON/documentação.

### Evidências e handoff

- Arquivos alterados: ainda não iniciado.
- Decisões tomadas: ainda não iniciado.
- Validações executadas: ainda não iniciado.
- Observações para E04: ainda não iniciado.

---

## E04 — Homologação com o SQL Server real — #bloqueada

### Objetivo

Validar, a partir do container de release, conectividade/TLS, consulta, classificação e aplicação de
regras com dados reais controlados antes de liberar a mudança para produção.

### Por que agora

É o gate final e depende do produto empacotado da E03. Somente o ambiente real confirma driver,
rede, autenticação, schema, certificado, permissões e dados.

### Dependências e paralelismo

- Dependência obrigatória: E03 `#concluida`.
- Não pode ser paralelizada com alterações de implementação; se falhar, retornar à etapa dona da
  causa e repetir o gate completo pertinente.
- Insumos externos necessários: conexão de homologação, uma NS conhecida `RURAL`, uma NS conhecida
  `URBANO`, autorização de leitura e rota de rede a partir do container.

### Escopo

- Smoke opt-in criado na E03.
- Imagem/Compose de release aprovados.
- Verificação somente leitura e evidências sanitizadas.
- Teste de falha fechada por NS inexistente e, se autorizado pelo responsável do ambiente, por
  indisponibilidade controlada.

### Fora de escopo

- Alterar dados, permissões, schema, índices ou configuração do SQL Server.
- Usar credencial de produção em log, relatório, linha de comando persistida ou Git.
- Implantação definitiva ou migração do volume do servidor.

### Passos de implementação

1. Obter do responsável pelo banco uma string de conexão de homologação com TLS e login de menor
   privilégio, além das duas NS de fixture e confirmação do schema padrão.
2. Carregar a configuração apenas no `.env` local/seguro e validar o Compose com saída silenciosa.
3. Executar o smoke real dentro da imagem de release para cada NS e confirmar exatamente um valor
   `RURAL`/`URBANO`.
4. Executar conformidade end-to-end para projetos controlados dos dois mercados e comparar os
   achados com as guardas: nenhuma regra do mercado oposto pode aparecer.
5. Validar NS inexistente, retorno inválido/duplicado quando houver fixture segura e falha de conexão
   controlada; confirmar job falho, mensagem segura, correlação e ausência de novo snapshot.
6. Conferir logs sanitizados, tempo da consulta, fechamento de conexão e ausência do segredo em
   imagem/volume/backup/artefatos.
7. Registrar somente IDs/horários/resultados permitidos e atualizar o runbook com qualquer detalhe
   ambiental não secreto descoberto.

### Prompt para uma sessão limpa

```text
Na raiz do repositório, execute a etapa E04 — Homologação com o SQL Server real do ROADMAP.md. Leia
primeiro as instruções aplicáveis, o ROADMAP.md inteiro, git status, README.md,
docs/operacao-servidor.md, o smoke opt-in, os Compose e o manifesto da release produzida. Preserve
mudanças preexistentes. Confirme que E03 está realmente #concluida, que a imagem testada corresponde
ao manifesto e que o código não divergiu. Verifique se estão disponíveis, por canal seguro, uma
conexão de homologação com SELECT mínimo, uma NS RURAL, uma NS URBANO, schema confirmado e rota/TLS
do container. Se esses insumos ainda faltarem, mantenha E04 #bloqueada e atualize causa, evidência,
impacto e ação; não peça nem registre segredos no roadmap ou chat.

Quando os insumos existirem, altere E04 no índice e detalhe para #em-andamento. Coloque segredos
somente no .env ignorado, valide Compose com --quiet e rode o smoke dentro da imagem de release para
as duas NS. Depois execute conformidade end-to-end e prove que fatos e achados pertencem apenas ao
mercado retornado. Valide NS inexistente e uma falha controlada autorizada, confirmando erro seguro e
nenhum snapshot parcial. Inspecione logs e artefatos sem imprimir a conexão. Não escreva nem altere
permissões/schema/dados do banco.

Execute todas as validações listadas. Não declare sucesso se algum teste obrigatório falhar ou não
for executado. Atualize para #concluida somente após o aceite; se houver impedimento real, volte a
#bloqueada e documente causa, evidência sanitizada, impacto e ação de desbloqueio. Preencha
“Evidências e handoff” sem segredos e entregue resumo conciso de resultados e pendências. Não crie
commit, publique, implante ou altere o ambiente externo sem autorização explícita.
```

### Critérios de aceite

- [ ] A imagem de release conecta com TLS e login somente leitura a partir do host/container alvo.
- [ ] A NS urbana retorna/publica somente `URBANO`/`rede.contexto_urbano`; a rural somente
      `RURAL`/`rede.contexto_rural`.
- [ ] Achados não contêm regra guardada pelo mercado oposto em projeto nem região.
- [ ] NS inexistente e falha controlada não criam snapshot e produzem mensagem acionável sem segredo.
- [ ] Consulta termina dentro do timeout operacional acordado e não deixa conexão pendente.
- [ ] Logs, imagem, volume, backup e artefatos inspecionados não contêm a string de conexão.
- [ ] Evidências sanitizadas identificam imagem/digest, horário, NS autorizadas e resultados.

### Validação obrigatória

```powershell
docker compose --env-file .env -f server\compose.release.yaml config --quiet
```

Além desse comando, executar o comando exato do smoke opt-in criado e documentado na E03 para as NS
de homologação `RURAL` e `URBANO`, seguido do fluxo end-to-end de conformidade pela API/cliente. O
resultado esperado é o descrito nos critérios acima. Registrar o comando do smoke sem valores
secretos e sem colar a string de conexão.

### Bloqueios

- **Causa:** não foram fornecidos neste trabalho conexão de homologação, método de autenticação/TLS,
  confirmação de schema, rota do container nem duas NS conhecidas.
- **Evidência:** o pedido define a consulta e tipos, mas não contém esses dados operacionais; o
  `.env` local não foi lido por conter segredos.
- **Impacto:** não é possível aceitar conectividade, driver, certificado, permissões e semântica com
  dados reais; implementação e gates com doubles continuam possíveis.
- **Ação de desbloqueio:** o responsável pelo SQL Server deve disponibilizar os insumos por canal
  seguro e autorizar a execução somente leitura no ambiente de homologação.

### Riscos e mitigação

- **NS de teste conter dado sensível:** usar fixtures autorizadas e registrar somente o mínimo.
- **Credencial possuir privilégio excessivo:** DBA deve comprovar login dedicado com `SELECT` mínimo.
- **Certificado privado não confiável no container:** instalar CA pública da organização por processo
  aprovado; não usar `TrustServerCertificate=yes` como correção silenciosa.
- **Teste de falha afetar outros consumidores:** simular somente em janela/ambiente de homologação
  autorizado, sem interromper produção.

### Plano de rollback/cutover

- Antes do cutover, preservar a imagem/digest anterior e o snapshot administrativo do volume,
  conforme `docs/operacao-servidor.md`.
- Em falha da dependência externa após o cutover, reverter para a imagem anterior somente conforme a
  compatibilidade de volume documentada; não habilitar fallback local na nova versão.
- Rotacionar imediatamente a credencial se houver qualquer suspeita de exposição e recriar o
  container sem gravá-la na imagem ou no volume.

### Evidências e handoff

- Arquivos alterados: nenhum; etapa bloqueada.
- Decisões tomadas: falha fechada e homologação somente leitura.
- Validações executadas: nenhuma; faltam insumos externos.
- Ação necessária: obter conexão/TLS/schema e NS rural/urbana autorizadas por canal seguro.

## Referências externas confirmadas

- Microsoft Learn — instalação do Microsoft ODBC Driver for SQL Server em Linux/Debian:
  <https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server>
- Projeto oficial `pyodbc` — implementação DB-API 2.0, instalação e suporte de plataforma:
  <https://github.com/mkleehammer/pyodbc>
