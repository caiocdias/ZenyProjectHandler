# Roadmap de melhorias de estabilidade e qualidade

> Guia operacional para implementar os achados selecionados na revisão de 05/08/2026. Cada etapa
> foi dimensionada para ser executada em um chat novo do Codex, sobre a `main` deixada pela etapa
> anterior. Este documento não substitui `docs/roadmap-desenvolvimento.md`; ele detalha um ciclo de
> estabilização transversal do produto existente.

## Objetivo e escopo

Este ciclo cobre os achados 1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 14 e 15 da revisão técnica:

| Achado | Tema | Etapas deste roadmap |
|---|---|---|
| 1 | Caminhos temporários longos no Windows | 2 |
| 2 | Separação dos testes privados do gate básico | 1 |
| 3 | Confirmação de backup com problemas de integridade | 5 |
| 4 | Concorrência e bloqueio da UI nas operações de portabilidade | 6 e 7 |
| 5 | Memória, responsividade e qualidade do visualizador | 12 e 13 |
| 6 | SHA-256 recalculado a cada renderização | 11 |
| 7 | Arquivos gerenciados órfãos após exclusões | 10 |
| 8 | Identidade incompleta do motor OCR e do cache | 14 |
| 9 | Ausência do idioma português no Tesseract | 15 |
| 12 | Janela de inconsistência na substituição de projetos | 8 e 9 |
| 14 | PDFs protegidos sem fluxo completo na interface | 16 |
| 15 | Logging, recursos SQLite e complexidade | 3, 4 e 17 |

## Regras para todas as etapas

1. Executar apenas uma etapa por chat e começar lendo este documento, os ADRs citados e o estado
   atual do código. Não presumir que os nomes ou as linhas observadas em 05/08/2026 continuam iguais.
2. Trabalhar sobre a `main` atualizada pela etapa anterior. Conferir `git status` antes de editar e
   preservar alterações do usuário que não pertençam ao escopo.
3. Implementar incrementos verticais: contratos, aplicação, adaptadores, interface e testes devem ser
   alterados juntos quando o comportamento atravessar essas camadas.
4. Não reduzir `fail_under`, não ignorar warnings de forma ampla e não mascarar falhas com skips.
5. A suíte básica deve continuar offline, determinística e independente de PDFs privados.
6. PDFs originais permanecem somente leitura. Senhas, conteúdo extraído, coordenadas, caminhos
   absolutos e outros dados sensíveis não podem aparecer em logs ou commits.
7. Qualquer operação de arquivos deve validar que o destino resolvido está dentro da raiz gerenciada.
   Trocas destrutivas precisam ser recuperáveis ou compensadas.
8. Otimizações do visualizador não podem reduzir a resolução usada pela análise ou pelo OCR. A
   visualização deve oferecer detalhe equivalente a 600 DPI sob demanda, sem criar um raster integral
   de uma prancha grande nessa resolução.
9. Atualizar este roadmap ao concluir uma etapa: mudar o estado, registrar commits, comandos
   executados, resultados, decisões e limitações remanescentes.
10. Antes de encerrar cada etapa, executar os testes focados e o gate básico completo. Se o gate não
    passar por causa introduzida pela etapa, ela não está concluída.

## Gates comuns

Após a Etapa 1, o comando canônico do gate básico continuará sendo:

```powershell
.\IniciarTestes.bat
```

Quando for útil diagnosticar individualmente:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest -m "not private_samples" --cov
```

O gate privado criado na Etapa 1 é complementar: ele só deve ser executado em ambiente autorizado e
com o corpus completo. Seus resultados não substituem o gate básico.

```powershell
.\IniciarTestesPrivados.bat
```

## Ordem e estado

| Etapa | Estado atual | Depende de | Resultado principal |
|---|---|---|---|
| 1. Gate básico independente do corpus privado | CONCLUÍDA | - | Suíte pública verde e gate privado opt-in |
| 2. Arquivos temporários compatíveis com Windows | CONCLUÍDA | 1 | Cópias atômicas sem exceder o caminho do destino |
| 3. Logging estruturado nas fronteiras | CONCLUÍDA | 1 | Falhas diagnosticáveis sem dados sensíveis |
| 4. Ciclo de vida de SQLite e ResourceWarnings | CONCLUÍDA | 1 | Engines e conexões sempre encerradas |
| 5. Backup degradado com confirmação explícita | CONCLUÍDA | 2, 3 | Nenhuma omissão silenciosa de PDF |
| 6. Coordenador central de operações | PENDENTE | 3, 4 | Operações incompatíveis não concorrem |
| 7. Portabilidade assíncrona e UI não reentrante | PENDENTE | 6 | UI responsiva, sem `processEvents()` manual |
| 8. Preflight de substituição antes de mutar arquivos | PENDENTE | 6, 7 | Confirmação ocorre antes da troca física |
| 9. Journal e recuperação de importações interrompidas | PENDENTE | 8 | Banco e arquivos reconciliados após queda |
| 10. Limpeza segura de arquivos gerenciados | PENDENTE | 6, 9 | Exclusões não deixam fotos órfãs |
| 11. Identidade verificada da origem por sessão | PENDENTE | 1 | Navegação não recalcula o PDF inteiro |
| 12. Renderização por orçamento e região | PENDENTE | 11 | Pranchas grandes não exigem raster integral de 600 DPI |
| 13. Visualizador progressivo e assíncrono | PENDENTE | 6, 12 | Zoom detalhado sem congelamento ou resultados obsoletos |
| 14. Assinatura reprodutível do OCR | PENDENTE | 1 | Cache muda com motor, idioma e configuração |
| 15. Provisionamento e diagnóstico do português | PENDENTE | 14 | Instalação funcional com `por`, ou erro acionável |
| 16. Credenciais efêmeras para PDFs protegidos | PENDENTE | 6, 11, 13 | Importação, visualização e análise protegidas funcionam |
| 17. Redução e gate de complexidade | PENDENTE | Todas as anteriores | Sem funções E/F e regressão bloqueada |

Estados permitidos: `PENDENTE`, `EM ANDAMENTO`, `BLOQUEADA` e `CONCLUÍDA`.

---

## Etapa 1 — Gate básico independente do corpus privado

**Achado original:** 2.  
**Estado:** CONCLUÍDA.  
**Arquivos prováveis:** `pyproject.toml`, `IniciarTestes.bat`, novo launcher do gate privado,
`tests/integration/test_real_pdf_samples.py`, testes sintéticos relacionados e documentação.

### Contexto e decisões

- Em 05/08/2026, a coleção tinha 265 testes: 249 passaram e 16 foram ignorados quando executada com
  um `basetemp` curto. A cobertura pública resultante foi 84,74%, abaixo de 85,01%.
- Os PDFs descritos em `evaluation/manifesto-amostras.json` são privados por decisão da ADR 0005 e
  não podem ser requisito de um clone limpo.
- Criar o marcador `private_samples`. O gate básico deve excluir esse marcador explicitamente.
- Criar um gate privado opt-in. Quando acionado, a ausência de amostra exigida deve ser falha clara,
  e não `skip`; no gate básico, os testes sequer devem tentar abrir o corpus.
- Não baixar amostras, não versionar PDFs reais e não baixar o limite de cobertura. Recuperar a
  cobertura com testes públicos/sintéticos para os ramos atualmente descobertos.
- Se `IniciarTestes.bat` criar um caminho de temporários próprio, ele deve ser curto e descartável,
  mas isso não pode substituir a correção funcional da Etapa 2.

### Critérios de aceite

- `IniciarTestes.bat` passa em clone sem `examples/*.pdf` privado e mantém cobertura > 85%.
- O relatório informa claramente que o corpus privado não pertence ao gate básico.
- O gate privado possui comando documentado, valida pré-condições e falha se o corpus autorizado
  estiver incompleto ou adulterado.
- Um teste impede que futuros testes privados sejam adicionados sem o marcador correto.
- README, política de acesso e ADR 0005 continuam coerentes.

### Registro de conclusão — 05/08/2026

- O marcador `private_samples` foi registrado e os testes reais foram isolados em
  `tests/private_samples/`. O gate básico usa explicitamente `-m "not private_samples"`; a coleta
  lê somente o manifesto público e não calcula hashes nem abre o corpus.
- `IniciarTestesPrivados.bat` executa apenas o marcador privado, interrompe na primeira falha e
  valida previamente presença, legibilidade, tamanho e SHA-256 por ID anônimo. O fluxo não usa
  `skip` e mantém relatório local separado em `relatorio-testes-privados.txt`.
- `IniciarTestes.bat` preserva `relatorio-testes.txt`, declara o escopo público e usa um `basetemp`
  curto e aleatório sob `%SystemDrive%\tmp`. Isso mantém o gate operacional até a correção
  funcional de nomes temporários da Etapa 2.
- A cobertura perdida foi recuperada com testes públicos de correspondência geométrica, contratos
  do manifesto/auditoria e detecção de vãos. Nenhum PDF foi baixado, copiado ou versionado e o
  limite permaneceu em `85.01`.
- Validações concluídas: testes focados (`25 passed`, mais `2 passed` da auditoria), Ruff completo,
  `ruff format --check`, Mypy (`161 source files`), `pip check` e o gate básico canônico. O resultado
  final foi `259 passed, 20 deselected`, cobertura `85,08%` e `RESULTADO FINAL: APROVADO`, incluindo
  as três seções Radon no relatório consolidado.
- O gate privado foi exercitado no ambiente local e reprovou claramente na pré-condição porque uma
  amostra anônima requerida está ausente ou com hash divergente. Esse é o comportamento esperado;
  o arquivo não foi buscado nem reconstruído.
- Limitações remanescentes: sete `ResourceWarning` de conexões SQLite continuam visíveis e pertencem
  à Etapa 4; a dependência do `basetemp` curto não substitui a correção de caminhos da Etapa 2.
- Commits: não criados neste chat.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 1 do arquivo docs/roadmap-melhorias-estabilidade.md: torne o gate básico totalmente independente do corpus privado. Leia primeiro pyproject.toml, IniciarTestes.bat, tests/integration/test_real_pdf_samples.py, evaluation/POLITICA-ACESSO.md e a ADR 0005. Crie o marcador private_samples, exclua-o explicitamente do gate básico e crie um gate privado opt-in que falhe claramente quando o corpus autorizado estiver ausente ou inválido. O gate básico deve passar offline em um clone limpo e manter cobertura estritamente acima de 85,01%; não reduza o limite, não baixe nem versione PDFs reais e cubra os ramos faltantes com fixtures sintéticas ou testes públicos. Preserve o relatório consolidado e documente os dois fluxos. Atualize o estado e o registro desta etapa no roadmap. Execute os testes focados, Ruff, formatação, Mypy, pip check e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 2 — Arquivos temporários compatíveis com caminhos do Windows

**Achado original:** 1.  
**Estado:** CONCLUÍDA.
**Arquivos prováveis:** `application/project_portability.py`, `adapters/portability/zip_archive.py`,
`adapters/persistence/backup.py` e seus testes.

### Contexto e decisões

- `_copy_atomic` criava o temporário a partir do nome final — que pode ser um SHA-256 — e ainda
  acrescentava UUID. Sob o caminho temporário normal do pytest no Windows, isso causou `WinError 3`.
- Usar nomes temporários curtos e imprevisíveis, criados no mesmo diretório do destino para manter a
  atomicidade de `replace`. Não usar o nome final completo como prefixo.
- Aplicar a mesma política a todos os helpers de publicação/cópia atômica. Centralizar a solução se
  isso reduzir duplicação sem acoplar camadas indevidas.
- Preservar permissões/metadados necessários, `fsync` quando já aplicável, rollback e limpeza de
  resíduos. Um destino cujo próprio caminho é inválido deve gerar erro de domínio compreensível.

### Critérios de aceite

- Os testes de portabilidade passam usando o diretório temporário padrão e um caminho aninhado que
  reproduza a margem do limite do Windows.
- O temporário não aumenta materialmente o comprimento do nome do destino.
- Sucesso e falha não deixam arquivos `.tmp` ou substituições parciais.
- Linux e outros ambientes continuam funcionando sem lógica destrutiva específica do Windows.

### Registro de conclusão — 05/08/2026

- Foi criada uma primitiva comum para arquivos e diretórios temporários irmãos, com prefixo curto
  `.z-`, aleatoriedade fornecida por `tempfile`, criação exclusiva e limpeza por gerenciador de
  contexto. Arquivos usam nomes de até 15 caracteres e diretórios, de até 11, sem incorporar o nome
  final ao temporário.
- Cópias de fotos, pacotes ZIP, snapshots e restaurações SQLite passaram a publicar com temporário
  no mesmo diretório do destino. `copy2` continua preservando metadados; a verificação de
  integridade SQLite foi mantida e a limpeza agora inclui também sidecars `-journal`, `-wal` e
  `-shm` dos bancos temporários.
- Os stagings e diretórios de recuperação da importação/restauração também foram movidos para o
  diretório irmão da raiz gerenciada. Isso evita troca entre volumes no Windows e preserva o estado
  anterior quando a publicação do novo staging é interrompida.
- A busca pelas ocorrências equivalentes encontrou as publicações JSON do cache de análise e do
  dataset de avaliação. Ambas usam agora a mesma primitiva; os `TemporaryDirectory` restantes
  constroem conteúdo interno sem substituir diretamente um destino final e permanecem curtos.
- Os testes constroem destinos absolutos entre 245 e 259 caracteres no diretório temporário padrão,
  sem depender do `basetemp` curto do gate. Eles observam os caminhos realmente entregues a
  `os.replace` e comprovam unicidade, tamanho, diretório irmão, metadados, rollback e ausência de
  resíduos após falhas de cópia, pacote, backup, restauração e publicação do staging.
- Validações concluídas: testes focados de temporários, cache, dataset, backup e portabilidade
  (`24 passed`); Ruff completo; `ruff format --check`; Mypy (`164 source files`); e o gate básico
  canônico. O resultado final foi `266 passed, 20 deselected`, cobertura `85,16%`, complexidade média
  A (`4,0338`) e `RESULTADO FINAL: APROVADO`.
- Permanecem sete `ResourceWarning` de conexões SQLite, já registrados para a Etapa 4. Nenhum aviso
  novo ou limitação específica de plataforma foi introduzido nesta etapa.
- Commits: `c53561c` (`fix(portability): use short sibling temporaries`) e `5d69bf7`
  (`test(portability): cover near-limit Windows paths`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 2 de docs/roadmap-melhorias-estabilidade.md. Corrija as rotinas atômicas que constroem temporários longos em application/project_portability.py, adapters/portability/zip_archive.py e adapters/persistence/backup.py. Use nomes temporários curtos, únicos e no mesmo diretório do destino, preservando atomicidade, rollback, metadados necessários e limpeza em qualquer falha. Procure outras ocorrências equivalentes no repositório antes de editar. Adicione testes que reproduzam no Windows um destino válido próximo do limite de caminho e comprovem que não ficam resíduos; não masque o problema apenas alterando o basetemp do pytest. Mantenha mensagens de erro compreensíveis e comportamento multiplataforma. Atualize o registro da etapa no roadmap e execute os testes focados de backup/portabilidade e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 3 — Logging estruturado nas fronteiras da aplicação

**Achado original:** 15, parte de observabilidade.  
**Estado:** CONCLUÍDA.
**Arquivos prováveis:** `logging_config.py`, `bootstrap.py`, painéis Qt, workers e casos de uso que
encerram operações externas.

### Contexto e decisões

- O projeto já configura arquivo JSON rotativo e testa redação, mas quase não emite registros nas
  fronteiras. Muitas exceções são convertidas apenas em mensagens da UI.
- Registrar início, conclusão, cancelamento e falha de operações com um identificador de correlação.
  Preferir IDs de projeto/documento, hashes abreviados e códigos de erro; não registrar caminhos
  absolutos, texto do PDF, coordenadas, fotos ou senhas.
- Erros esperados de validação devem usar nível adequado e continuar com mensagem amigável na UI.
  Falhas inesperadas devem guardar traceback no log.
- Instalar tratamento de exceções não capturadas do processo e integrar erros dos workers sem tocar
  widgets fora da thread principal.

### Critérios de aceite

- Falhas em importação, análise, visualização, portabilidade, restauração e inicialização deixam um
  registro correlacionável e redigido.
- Senhas e outros campos sensíveis nunca aparecem, inclusive em `repr`, `extra` ou traceback.
- Não há duplicação de handlers após reinicialização em testes.
- Testes validam estrutura JSON, níveis, correlação, traceback e redação.

### Registro de conclusão — 05/08/2026

- O formatter JSON passou a aceitar apenas um esquema explícito de campos operacionais. Eventos de
  início, sucesso e cancelamento usam `INFO`; falhas esperadas usam `WARNING` sem traceback; falhas
  inesperadas usam `ERROR` com pilha, e exceções não capturadas usam `CRITICAL`.
- Cada operação recebe uma correlação aleatória propagada por `ContextVar`. Somente UUIDs de
  projeto, documento e execução, listas de UUIDs, contagens e o indicador de cache podem acompanhar
  o evento; caminhos, nomes de arquivo, conteúdo, coordenadas, fotos e credenciais não são campos do
  esquema.
- A redação não serializa `extra` desconhecido, não interpola argumentos nem chama `repr`/`str` de
  objetos arbitrários. Tracebacks preservam arquivo-base, linha, função, tipo e encadeamento, mas
  removem caminhos absolutos, linhas-fonte e detalhes das exceções. A redação textual complementar
  cobre atribuições de senha/token/conteúdo e caminhos Windows/POSIX.
- Foram instrumentados o bootstrap, importação e análise de PDF, abertura e renderização no
  visualizador, exportação/importação/backup/restauração, seleções e confirmações canceláveis da UI
  e o worker Qt de análise. As mensagens amigáveis existentes foram mantidas e nenhum widget é
  acessado pelos hooks ou pela lógica de logging do worker.
- `sys.excepthook` e `threading.excepthook` são instalados de forma idempotente e apenas registram a
  falha sanitizada. A configuração repetida substitui e fecha handlers anteriores, sem acumular
  streams ou arquivos rotativos.
- Os testes cobrem o contrato JSON, níveis, correlação aninhada, traceback, campos extras hostis,
  `repr` hostil, hooks, handlers duplicados, cancelamentos Qt e as fronteiras de PDF, visualizador,
  portabilidade, restauração e bootstrap. Os testes focados finalizaram com `29 passed`.
- Validações concluídas: Ruff completo, `ruff format --check`, Mypy (`165 source files`), `pip check`
  e gate básico canônico. O resultado final foi `272 passed, 20 deselected`, cobertura `85,20%`, as
  três seções Radon aprovadas e `RESULTADO FINAL: APROVADO`.
- Permanecem os sete `ResourceWarning` de conexões SQLite já atribuídos à Etapa 4; a observabilidade
  não os promove a erro nem introduz novo aviso.
- Commits: `aef9468` (`feat(logging): add safe structured operation telemetry`) e `e082afd`
  (`feat(observability): instrument application boundaries`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 3 de docs/roadmap-melhorias-estabilidade.md. Parta da configuração existente em logging_config.py e acrescente observabilidade estruturada nas fronteiras reais: bootstrap, importação/análise de PDF, visualizador, operações de portabilidade e workers Qt. Registre início, sucesso, cancelamento e falha com correlação e IDs não sensíveis; preserve traceback para falhas inesperadas. Não registre senha, conteúdo do PDF, coordenadas, fotos nem caminhos absolutos e fortaleça a redação para extra, repr e exceções. Instale um tratamento seguro de exceções não capturadas sem manipular widgets fora da thread principal. Não transforme erros esperados em ruído e mantenha as mensagens amigáveis existentes. Adicione testes de formato, níveis, correlação, traceback, ausência de handlers duplicados e redação. Atualize o registro da etapa no roadmap e execute os testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 4 — Ciclo de vida de SQLite e eliminação de ResourceWarnings

**Achado original:** 15, parte de recursos.  
**Estado:** CONCLUÍDA.
**Arquivos prováveis:** fixtures e testes de integração que criam engines, `bootstrap.py`,
`adapters/persistence/database.py` e fábricas de unidade de trabalho.

### Contexto e decisões

- A suíte completa emitia sete `ResourceWarning` por conexões SQLite não fechadas.
- Inventariar cada criação de engine/conexão/sessão e definir proprietário explícito. Fixtures devem
  usar `yield`/`finally`; produção deve encerrar recursos na saída normal, erro e fechamento da UI.
- Depois de corrigir a origem, promover `ResourceWarning` a erro no gate quando isso for estável. Não
  adicionar um filtro amplo de ignore. Se uma biblioteca externa gerar warning inevitável, documentar
  e restringir qualquer exceção ao módulo/mensagem exatos.
- Testar especialmente backup/restauração, que dispõem engines antes da troca do arquivo no Windows.

### Critérios de aceite

- Suíte básica completa sem `ResourceWarning` próprio.
- Arquivos SQLite temporários podem ser movidos/removidos logo após cada teste no Windows.
- Fechar a janela e falhar durante o bootstrap sempre chama `dispose()` exatamente quando apropriado.
- O gate impede regressões de recursos sem esconder warnings de terceiros.

### Registro de conclusão — 05/08/2026

- A reprodução em Python 3.13 confirmou sete conexões SQLite não fechadas: três engines pertenciam à
  fixture `interpretation_context` e quatro à fixture `database`. Ambas passaram a usar
  `yield`/`finally`; a fixture `workflow` recebeu o mesmo contrato preventivo. As aplicações Qt dos
  testes passaram a ser criadas por uma factory que mantém todas as janelas e descarta seus recursos
  no teardown, antes da coleta forçada do pytest.
- O inventário de produção deixou owners explícitos. O engine principal pertence ao ciclo de vida
  composto no bootstrap; engines de bancos portáteis pertencem a `managed_sqlite_engine`; e o engine
  criado internamente pelo Alembic é descartado no próprio ambiente de migração, enquanto um engine
  fornecido pelo chamador continua pertencendo ao chamador. Todas as `Connection` são delimitadas por
  `with`; cada `Session` pertence a `SqlAlchemyUnitOfWork`, que faz rollback e close na saída; e as
  conexões `sqlite3` diretas de backup/restauração permanecem sob `closing`.
- O owner do engine principal é idempotente e cobre falha em qualquer ponto posterior à criação do
  armazenamento, `aboutToQuit`, destruição e fechamento aceito da janela, além do `finally` de
  `run()`. A janela mantém um callback tipado de liberação; assim, uma tentativa de fechamento
  recusada durante análise ativa não descarta prematuramente o banco.
- A restauração continua descartando o pool antes da substituição física do banco e volta a descartá-lo
  antes do rollback. Os testes comprovam uma chamada na troca bem-sucedida e duas quando a primeira
  restauração falha e o snapshot de recuperação precisa ser publicado.
- No Windows, testes reais moveram e excluíram imediatamente arquivos SQLite após fechamento normal,
  exceção dentro de sessão/conexão, saída do aplicativo e rollback de restauração. Sucesso e exceção
  do context manager liberam `Session`, `Connection` e `Engine` sem depender do coletor de lixo.
- O pytest agora trata `ResourceWarning` como erro. Python 3.13 emite o aviso de `sqlite3.Connection`
  dentro de `__del__`; nesse caso o pytest o encapsula em `PytestUnraisableExceptionWarning`, que
  também foi promovido a erro para o gate não produzir falso verde. Não foi adicionado nenhum
  `ignore`, amplo ou estreito, e nenhuma exceção de biblioteca externa foi necessária.
- Validações concluídas: conjunto focado final (`36 passed`); suíte pública com warnings visíveis e
  `tracemalloc` (`276 passed, 20 deselected`, sem warnings); Ruff, `ruff format --check`, Mypy
  (`165 source files`) e `pip check`; e gate básico canônico. O resultado final do gate foi
  `276 passed, 20 deselected`, cobertura `85,31%`, complexidade média A (`3,9985`) e
  `RESULTADO FINAL: APROVADO`.
- Commits: `7e09908` (`fix(persistence): close owned SQLite resources`) e `531cfcf`
  (`test(persistence): gate resource lifecycle regressions`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 4 de docs/roadmap-melhorias-estabilidade.md. Reproduza os ResourceWarnings da suíte e rastreie todos os proprietários de SQLAlchemy Engine, Connection e Session em produção e testes. Corrija fixtures com yield/finally ou context managers e garanta dispose no fechamento normal, em exceções de bootstrap e nas trocas de banco de backup/restauração. No Windows, valide que os arquivos SQLite podem ser movidos e excluídos imediatamente após o uso. Depois de eliminar as causas, faça o gate tratar ResourceWarning como falha; não use ignore amplo e justifique qualquer exceção estreita inevitável de biblioteca externa. Adicione testes de ciclo de vida e regressão, atualize o registro da etapa no roadmap e execute a suíte com warnings visíveis e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 5 — Backup degradado com confirmação explícita

**Achado original:** 3.  
**Estado:** CONCLUÍDA.
**Arquivos prováveis:** `application/project_portability.py`, modelos/portas de portabilidade,
`ui/portability_panel.py`, manifesto do pacote, ADR 0008 e testes.

### Contexto e decisões

- O serviço atualmente pode ignorar PDFs ausentes ou alterados e a UI ainda anunciar “Backup íntegro”.
- Criar um preflight de integridade sem efeitos colaterais. Classificar problemas, listar documentos
  afetados por identificador seguro e informar exatamente o que será omitido ou permanecerá externo.
- Backup íntegro segue direto. Backup com problema crítico só começa após uma confirmação explícita e
  específica; cancelar não deve criar pacote nem temporários.
- Se o usuário continuar, o resultado e o manifesto devem registrar `DEGRADADO` e as omissões. A UI
  deve dizer “criado com ressalvas”, nunca “íntegro”. Avaliar versão do formato e atualizar ADR/README.
- Importação/exportação devem aproveitar a mesma semântica de relatório quando aplicável, sem misturar
  essa etapa com a proteção contra ZIP bomb que ficou fora deste ciclo.

### Critérios de aceite

- Nenhuma origem ausente/adulterada é omitida silenciosamente.
- Testes cobrem íntegro, ausente, hash divergente, cancelamento e aceite explícito.
- Restauração de backup degradado mantém estado previsível e expõe limitações, sem inventar caminhos.
- O usuário recebe detalhes suficientes sem exposição desnecessária de caminho completo.

### Registro de conclusão — 05/08/2026

- O serviço ganhou `preflight_backup`, que percorre projetos e origens PDF somente para leitura,
  classifica `PDF_AUSENTE`, `PDF_ADULTERADO` e `PDF_ILEGIVEL` e produz referências auditáveis por IDs
  de projeto/documento. O teste substitui o construtor de diretório temporário por uma falha sentinela
  e comprova que o preflight não cria snapshots, stagings, pacotes ou resíduos.
- A criação reexecuta e compara o relatório antes de qualquer temporário. Um relatório degradado sem
  `confirmar_degradado=True` é recusado; confirmação obsoleta também é recusada. Cancelar na UI não
  chama a criação, preserva um destino anterior e não deixa `.z-*`.
- Novas exportações e backups usam o manifesto de formato 2; o leitor mantém compatibilidade com o
  formato 1. O formato 2 assina `INTEGRO`/`DEGRADADO` e omissões com código, tipo, tratamento e IDs
  seguros. Exportação reaproveita o relatório da origem, enquanto importação e restauração mantêm
  separados os avisos declarados e a integridade física dos arquivos recebidos.
- O diálogo Qt lista somente IDs abreviados e as classes ausente, alterado ou ilegível, além de dizer
  se não há origem registrada ou se a referência permanecerá externa. Nenhum nome de documento ou
  caminho absoluto é apresentado. O aceite usa “Backup criado com ressalvas”; o fluxo íntegro diz
  apenas “Backup criado” e nunca anuncia integridade total.
- A restauração exige que snapshot e todos os membros declarados estejam íntegros, inclusive quando o
  manifesto é `DEGRADADO`. PDFs copiados recebem caminhos gerenciados; omissões preservam a referência
  externa preexistente ou a ausência de origem, e o resultado/UI expõem quantos continuam
  indisponíveis sem inventar caminhos.
- Validações concluídas: conjunto focado de serviço, ZIP e Qt (`15 passed`); `pip check`; Ruff;
  `ruff format --check`; Mypy (`165 source files`); e gate básico canônico. O resultado final foi
  `283 passed, 20 deselected`, cobertura `85,26%`, complexidade média A (`4,0214`) e
  `RESULTADO FINAL: APROVADO`. O único aviso foi um `PytestCacheWarning` ambiental por falta de
  permissão para atualizar `.pytest_cache`; não houve `ResourceWarning` nem falha de teste.
- Commits: `9ff2607` (`feat(portability): confirm degraded backups`) e `9aabd23`
  (`test(portability): cover degraded backup consent`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 5 de docs/roadmap-melhorias-estabilidade.md. Crie um preflight de integridade sem efeitos colaterais para backup completo e faça a UI exigir confirmação explícita quando houver PDF ausente, alterado ou ilegível. Cancelar não pode publicar pacote nem deixar temporários. Se o usuário prosseguir, marque o resultado e o manifesto como degradados, registre omissões de forma auditável e use a mensagem “criado com ressalvas”; nunca anuncie integridade total. Garanta comportamento previsível na restauração e reaproveite o relatório de integridade na exportação quando fizer sentido. Preserve privacidade ao apresentar documentos e avalie/versione o formato se a estrutura do manifesto mudar. Atualize ADR 0008, README e o registro da etapa. Cubra serviço e Qt com testes para backup íntegro, problemas diferentes, cancelamento e confirmação; execute o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 6 — Coordenador central de operações incompatíveis

**Achado original:** 4, parte de coordenação.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** novo módulo de aplicação, `bootstrap.py`, `project_panel.py`, serviços de
análise/portabilidade e testes unitários.

### Contexto e decisões

- Uma análise pode permanecer ativa enquanto importação ou restauração troca banco e arquivos.
- Criar um coordenador independente de Qt, injetado nos casos de uso. Um bloqueio global conservador
  é aceitável inicialmente; se houver escopos, documentar matriz de compatibilidade e evitar deadlock.
- Aquisição deve produzir token/context manager liberado em `finally`. Reentrada acidental e dupla
  liberação precisam ser controladas.
- O guard deve existir no serviço, não apenas em botões, para proteger chamadas futuras e testes.
- Definir erro de aplicação próprio e mensagem amigável que informe a operação em andamento.

### Critérios de aceite

- Análise, importação, exportação, backup, restauração e exclusões relevantes usam o coordenador.
- Operações incompatíveis são recusadas antes de qualquer mutação.
- Falha, cancelamento e exceção liberam o token; testes concorrentes comprovam isso.
- O coordenador não importa PySide6 nem infraestrutura de persistência.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 6 de docs/roadmap-melhorias-estabilidade.md. Introduza um coordenador de operações na camada de aplicação, sem dependência de Qt, para impedir concorrência incompatível entre análise, importação/exportação, backup/restauração e exclusões que alterem o mesmo estado. Injete uma única instância pelo bootstrap. Use token ou context manager com liberação garantida em finally, erro de aplicação específico, mensagem amigável e sem mutação antes da aquisição. Um bloqueio global conservador é aceitável; se optar por escopos, documente uma matriz simples e prove ausência de deadlock, reentrada indevida e dupla liberação. Integre também o worker de análise existente, não apenas os botões. Adicione testes unitários e de integração para sucesso, recusa, exceção e cancelamento. Atualize o registro da etapa e execute o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 7 — Portabilidade assíncrona e interface não reentrante

**Achado original:** 4, parte de execução Qt.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** `ui/portability_panel.py`, workers/controladores Qt, `bootstrap.py` e testes
com `pytest-qt`.

### Contexto e decisões

- Exportar, importar, copiar e restaurar são operações de disco pesadas executadas hoje na thread da
  UI. O callback de progresso chama `QApplication.processEvents()`, permitindo reentrância.
- Executar serviço em `QThread`/`QThreadPool`; sinais carregam progresso, resultado, falha e conclusão.
  Somente a thread principal altera widgets.
- Remover `processEvents()`. Enquanto ocupada, a UI deve desabilitar todas as ações incompatíveis,
  inclusive nos outros painéis, usando o coordenador da Etapa 6 como fonte de verdade.
- Fechamento da janela deve cancelar em pontos seguros ou aguardar conclusão com limite e mensagem.
  Nunca terminar thread à força durante transação ou troca atômica.

### Critérios de aceite

- A janela continua respondendo durante cópia demorada e não aceita uma segunda operação conflitante.
- Progresso é monotônico; sinais atrasados de uma execução antiga não alteram estado atual.
- Sucesso, erro e cancelamento restauram botões e liberam o coordenador uma única vez.
- Testes Qt usam serviço falso bloqueável e não dependem de `sleep` frágil.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 7 de docs/roadmap-melhorias-estabilidade.md. Mova importação, exportação, backup e restauração do PortabilityPanel para workers Qt adequados e remova completamente QApplication.processEvents() desse fluxo. Sinais devem transportar progresso, sucesso, erro e finalização; somente a thread principal pode tocar widgets. Integre o coordenador da Etapa 6 para desabilitar todas as ações incompatíveis na janela, rejeitar duplo clique/reentrância e liberar estado exatamente uma vez. Trate fechamento da aplicação com cancelamento cooperativo em pontos seguros ou espera limitada; nunca finalize uma thread à força durante transação ou replace. Ignore sinais obsoletos por identidade de execução. Escreva testes pytest-qt com serviços falsos controláveis, sem sleeps frágeis, cobrindo responsividade, progresso, sucesso, falha, cancelamento e fechamento. Atualize o roadmap e execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 8 — Preflight de substituição antes de alterar arquivos

**Achado original:** 12, parte de ordenação.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** `application/project_portability.py`, DTOs/erros de importação,
`ui/portability_panel.py`, ADR 0008 e testes.

### Contexto e decisões

- A implementação atual prepara e troca a pasta final antes de descobrir no banco se o projeto já
  existe e se a substituição foi autorizada. O rollback normal funciona, mas queda de processo deixa
  janela de inconsistência.
- Separar importação em `inspecionar/preparar plano` e `aplicar plano`. O preflight valida pacote,
  identifica conflito e retorna resumo sem modificar banco, pasta final ou backups.
- A confirmação acontece sobre um plano imutável. Na aplicação, revalidar que pacote e estado alvo
  não mudaram; caso tenham mudado, exigir novo preflight.
- Falha ou recusa antes de aplicar não pode criar `.previous`, trocar raízes nem alterar SQLite.

### Critérios de aceite

- Primeira tentativa sobre projeto existente retorna necessidade de confirmação sem mutações físicas.
- Plano possui identidade/fingerprint e não pode ser aplicado a pacote ou estado diferente.
- Corridas entre preflight e aplicação são detectadas sob o coordenador.
- Testes inspecionam banco, raiz gerenciada e resíduos antes/depois de cada cenário.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 8 de docs/roadmap-melhorias-estabilidade.md. Reestruture a importação de projeto em preflight sem efeitos colaterais e aplicação de um plano validado. O preflight deve validar pacote/banco, detectar projeto existente e produzir resumo/fingerprint; a UI deve pedir confirmação antes de qualquer troca de pasta ou banco. Ao aplicar, revalide pacote e estado alvo sob o coordenador da Etapa 6 e recuse planos obsoletos. Uma recusa ou falha de confirmação não pode criar .previous, publicar arquivos, alterar SQLite nem deixar temporários. Preserve IDs e semântica de substituição da ADR 0008. Adicione testes que fotografem banco e sistema de arquivos em projeto novo, conflito recusado, conflito aceito e corrida entre preflight/aplicação. Atualize ADR, documentação e registro do roadmap; execute os testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 9 — Journal persistente e recuperação de importação interrompida

**Achado original:** 12, parte de recuperação.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** serviço de portabilidade, novo journal na pasta de dados, sequência de
bootstrap, ADR 0008 e testes de injeção de falha.

### Contexto e decisões

- Mesmo com preflight, banco e filesystem não compartilham transação. É preciso tornar a sequência
  recuperável diante de encerramento abrupto entre `replace`, commit e limpeza.
- Criar journal pequeno, versionado e publicado atomicamente, com caminhos relativos/validados,
  identidade da operação e estados como preparado, arquivos trocados, banco confirmado e limpeza.
- Antes de aceitar novas operações, o bootstrap reconcilia journal pendente de forma idempotente:
  concluir quando houver prova de commit ou restaurar o anterior quando não houver.
- Validar contenção de todos os caminhos do journal. Journal corrompido deve bloquear a mutação e
  orientar recuperação, nunca provocar exclusão ampla.

### Critérios de aceite

- Injeção de falha em cada fronteira deixa um estado que a próxima inicialização resolve.
- Reexecutar recuperação várias vezes produz o mesmo resultado.
- O último estado consistente do banco e dos arquivos é preservado; resíduos são limpos somente após
  confirmação.
- Logs registram operação e fase sem caminhos sensíveis.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 9 de docs/roadmap-melhorias-estabilidade.md. Acrescente um journal persistente, versionado e escrito atomicamente para tornar substituições de projetos recuperáveis entre troca de arquivos e commit do SQLite. Registre identidade e fases suficientes, usando somente caminhos relativos validados dentro da raiz gerenciada. Integre uma reconciliação idempotente no bootstrap antes de liberar novas operações: conclua quando houver prova do commit ou restaure o estado anterior quando não houver. Journal corrompido ou ambíguo deve bloquear mutações com diagnóstico acionável, nunca disparar exclusão ampla. Crie pontos de injeção de falha testáveis e cubra interrupções antes/depois de cada fase, recuperação repetida, resíduos e contenção de caminhos. Atualize ADR 0008, logging, documentação e o registro do roadmap; execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 10 — Limpeza transacional de arquivos gerenciados

**Achado original:** 7.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** `application/mvp_workflow.py`, abstração de armazenamento gerenciado,
repositórios, UI de projeto e testes.

### Contexto e decisões

- Excluir projeto, documento ou elementos remove o banco, mas pode deixar fotos em `project-files`.
- Centralizar a política de armazenamento. Nunca excluir o PDF original externo. Arquivos gerenciados
  só podem ser removidos depois de calcular referências vivas; blobs por digest podem ser compartilhados.
- Para exclusão de projeto, renomear a raiz para tombstone dentro da mesma raiz gerenciada, confirmar a
  transação e então limpar. Em rollback, restaurar. Integrar com coordenador e journal quando adequado.
- Para exclusões parciais, coletar lixo apenas depois do commit e somente se nenhuma entidade viva
  referenciar o digest. Falha de limpeza deve ser registrada e recuperável.

### Critérios de aceite

- Excluir projeto elimina sua raiz gerenciada, mas não toca PDFs externos.
- Excluir documento/elemento remove somente fotos sem referência restante.
- Rollback restaura tombstone; falha pós-commit deixa tarefa de limpeza recuperável.
- Testes cobrem arquivos compartilhados, caminho hostil, raiz inexistente e interrupções.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 10 de docs/roadmap-melhorias-estabilidade.md. Centralize a exclusão de arquivos gerenciados usada por projeto, documento e elementos/fotos. Nunca apague PDFs originais externos. Valide containment na raiz de dados, considere blobs por digest compartilhados e remova somente arquivos sem referência viva após a transação. Para projeto inteiro, use tombstone por rename recuperável: restaure em rollback e limpe apenas depois do commit; integre coordenador e journal existentes sem duplicar protocolo. Falhas pós-commit devem ficar registradas para nova limpeza, não ser ocultadas. Ajuste o texto da UI para refletir exatamente o que é removido. Adicione testes de compartilhamento, rollback, interrupção, raiz ausente e caminhos maliciosos. Atualize documentação e o registro da etapa; execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 11 — Identidade verificada da origem durante a sessão

**Achado original:** 6.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** porta PDF, `adapters/pdf/pymupdf_reader.py`, controlador/estado do visualizador
e testes.

### Contexto e decisões

- `renderizar()` recalcula SHA-256 do arquivo inteiro a cada página/rotação, bloqueando a UI em PDFs
  grandes.
- Criar uma sessão/handle de documento verificado. Ao abrir, calcular hash uma vez e capturar tamanho,
  `mtime` e identidade necessária. Antes de cada uso, fazer verificação barata; mudança invalida sessão
  e exige inspeção/hash novamente.
- Não criar cache global eterno por caminho. Fechar handles de forma determinística e não impedir que
  backup/restauração mova arquivos no Windows.
- Análise, importação e portabilidade continuam fazendo verificação forte em suas fronteiras. A
  otimização vale para navegação/renderização repetida, não enfraquece integridade canônica.

### Critérios de aceite

- Navegar, girar e ampliar várias vezes calcula o hash integral uma vez por abertura estável.
- Substituir ou modificar o arquivo invalida a sessão antes de renderizar conteúdo divergente.
- Fechar/trocar documento libera recursos e dados de sessão.
- Testes usam hasher instrumentado e arquivo modificado, sem depender apenas de tempo de execução.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 11 de docs/roadmap-melhorias-estabilidade.md. Elimine o SHA-256 integral repetido a cada renderização criando uma sessão ou handle de origem verificada na porta PDF e no adaptador PyMuPDF. Calcule o hash uma vez ao abrir, capture metadados estáveis e faça checagem barata antes dos usos; qualquer alteração deve invalidar a sessão e exigir nova inspeção. Não crie cache global eterno por caminho, feche documentos/handles deterministicamente e não mantenha locks que impeçam backup ou restauração no Windows. Mantenha verificação forte nas fronteiras de análise, importação e portabilidade. Adapte o visualizador sem mudar geometrias. Teste com hasher instrumentado, múltiplas páginas/rotações, modificação do arquivo, troca de documento e encerramento. Atualize ADR 0003 se o contrato mudar, registre a etapa e execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 12 — Renderização por orçamento de pixels e regiões

**Achado original:** 5, parte do backend de visualização.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** configuração, porta PDF, `adapters/pdf/pymupdf_reader.py`, modelos de raster,
transformações geométricas e testes golden.

### Contexto e decisões

- Uma folha A0 a 600 DPI mede aproximadamente 19.860 × 28.080 pixels e exige cerca de 1,67 GB apenas
  para um buffer RGB. As cópias entre PyMuPDF, Python, QImage e QPixmap elevam muito o pico real.
- Manter 600 DPI como teto de detalhe visual, não como obrigação de rasterizar a folha inteira.
- Introduzir renderização por `clip`/tile em coordenadas da página e um orçamento explícito de pixels
  e bytes antes de alocar. Páginas pequenas podem continuar em raster integral; páginas grandes usam
  prévia limitada e regiões detalhadas sob demanda.
- Preservar transformações reversíveis, CropBox, rotação intrínseca/adicional e alinhamento de
  overlays. O pipeline de análise/OCR e seus DPIs não podem ser alterados nesta etapa.
- Evitar cópias desnecessárias, mas manter a vida útil correta do buffer que sustenta `QImage`.

### Critérios de aceite

- Nenhuma solicitação pode alocar raster acima do orçamento configurado sem ser dividida/reduzida.
- É possível obter detalhe efetivo de 600 DPI de uma região ampliada.
- Goldens comprovam pixels, dimensões, clips e geometrias em 0/90/180/270 graus.
- Teste sintético A0/A1 prova que a prévia não cria buffer integral de 600 DPI.
- Resultados do analisador e configurações de OCR permanecem semanticamente idênticos.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 12 de docs/roadmap-melhorias-estabilidade.md. Redesenhe o backend de renderização do visualizador para usar orçamento explícito de pixels/bytes e renderização por clip ou tiles. Mantenha 600 DPI como teto de detalhe disponível sob demanda, mas nunca aloque uma prancha A0/A1 inteira nessa resolução. Páginas pequenas podem usar raster integral; páginas grandes devem ter prévia limitada e regiões de alta resolução. Preserve CropBox, rotações, transformações normalizadas e alinhamento de overlays, e cuide da vida útil do buffer ao reduzir cópias entre PyMuPDF, bytes, QImage e QPixmap. Não altere DPI, decisões ou resultados do pipeline de análise/OCR. Adicione goldens para clips e rotações e teste sintético de A0/A1 que verifique dimensões solicitadas sem alocar gigabytes. Atualize ADR 0003, README/configuração e o registro da etapa; execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 13 — Visualizador progressivo, assíncrono e com cache limitado

**Achado original:** 5, parte da experiência Qt.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** `ui/pdf_viewer.py`, workers de renderização, cache de tiles, configuração e
testes `pytest-qt`.

### Contexto e decisões

- Renderização e conversões ocorrem hoje na thread principal. O backend regional da Etapa 12 permite
  compor prévia rápida e tiles detalhados para o viewport.
- Renderizar fora da UI. Cada solicitação recebe geração, documento, página, rotação, escala, DPR e
  região; resultados obsoletos são descartados.
- Usar cache LRU limitado por bytes, não apenas por quantidade. Limpar ao trocar/alterar documento e
  manter chaves coerentes com identidade verificada da Etapa 11.
- Exibir prévia enquanto tiles chegam sem piscar, deslocar overlay ou bloquear navegação. Priorizar
  viewport visível e uma margem pequena; não pré-renderizar a folha inteira em detalhe.
- Cancelamento é cooperativo. QPixmap continua sendo criado/usado somente na thread principal quando
  exigido pelo Qt.

### Critérios de aceite

- Navegação e zoom continuam respondendo enquanto tiles são produzidos.
- Resultado antigo nunca substitui página/zoom atual.
- Cache respeita limite de bytes e é invalidado corretamente.
- Overlays continuam clicáveis e alinhados em todas as rotações.
- Aceite manual inclui uma prancha grande autorizada: visão geral legível e texto pequeno nítido ao
  ampliar, sem crescimento de memória proporcional ao raster integral de 600 DPI.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 13 de docs/roadmap-melhorias-estabilidade.md. Use o backend regional da Etapa 12 para tornar o PdfViewer progressivo e assíncrono: prévia rápida e tiles de alta resolução priorizados pelo viewport. Identifique cada solicitação por geração, documento, página, rotação, zoom, devicePixelRatio e região; descarte resultados obsoletos. Crie cache LRU limitado por bytes e coerente com a identidade verificada da Etapa 11, limpando-o em troca ou alteração do documento. Não toque widgets ou QPixmap fora da thread permitida, preserve overlays clicáveis/alinhados e use cancelamento cooperativo. Não reduza qualidade da análise nem o detalhe visual disponível em zoom. Escreva testes pytest-qt determinísticos para responsividade, ordenação fora de sequência, invalidação, limite do cache, rotação e fechamento. Documente um roteiro de aceite manual com prancha grande, atualize o roadmap e execute o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 14 — Assinatura reprodutível do motor OCR e invalidação de cache

**Achado original:** 8.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** porta de OCR, `adapters/analysis/tesseract_ocr.py`,
`adapters/analysis/pymupdf_analyzer.py`, cache derivado, execução persistida e testes.

### Contexto e decisões

- O adaptador declara versão estática `5`, embora versão real, idioma selecionado e dados treinados
  possam mudar o resultado.
- Definir uma assinatura estável de capacidade: implementação/versão real normalizada, idiomas
  efetivamente selecionados, identidade dos traineddata relevantes e parâmetros que alteram saída
  (`OEM`, `PSM`, pré-processamento e configuração do adaptador).
- Não incluir caminhos específicos da máquina na assinatura. Consultas externas devem ocorrer uma vez
  por instância/sessão, com timeout e diagnóstico.
- Incluir a assinatura na chave do cache e na identidade/proveniência da execução. Cache antigo é dado
  derivado: rejeitar formato incompatível de forma limpa, sem migração arriscada.

### Critérios de aceite

- Mudar versão, idioma, traineddata ou parâmetro semântico gera nova chave/execução.
- Mesma capacidade em outra pasta produz a mesma assinatura.
- Tesseract ausente/defeituoso gera diagnóstico determinístico e não quebra extratores nativos.
- Testes usam motores falsos e subprocesso simulado; não dependem do Tesseract local.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 14 de docs/roadmap-melhorias-estabilidade.md. Substitua a versão estática do Tesseract por uma assinatura reprodutível de capacidade na porta de OCR. Inclua versão real normalizada, idiomas efetivamente selecionados, identidade dos traineddata relevantes e todos os parâmetros do adaptador que alterem a saída, sem incorporar caminhos específicos da máquina. Consulte capacidades uma vez por instância com timeout e diagnóstico. Use essa assinatura tanto na chave do cache derivado quanto na identidade/proveniência da execução; invalide caches antigos incompatíveis de modo limpo. Ausência do Tesseract não pode impedir os extratores nativos. Adicione testes com motores/subprocessos falsos provando invalidação por versão, idioma, traineddata e configuração e estabilidade entre caminhos diferentes. Atualize ADR 0004, README e o registro da etapa; execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 15 — Provisionamento e diagnóstico do idioma português

**Achado original:** 9.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** `setup.bat`, possível helper Python/PowerShell testável, configuração do
Tesseract, diagnóstico de inicialização, README e testes.

### Contexto e decisões

- Em 05/08/2026, o executável local era Tesseract 5.4, mas `--list-langs` retornava apenas `eng`.
- Setup bem-sucedido para OCR em português deve comprovar `por`. Não considerar apenas a existência
  do `.exe`.
- Não escrever em `Program Files` sem necessidade nem baixar artefato sem versão/hash. Preferir pasta
  gravável controlada pelo aplicativo/ambiente e configurar `TESSDATA_PREFIX` apenas para o processo.
- Qualquer provisionamento deve usar origem confiável, revisão fixada, licença documentada e SHA-256
  fixado. Se estiver offline ou falhar, preservar a venv e emitir instrução acionável; não alegar que o
  OCR português está pronto.
- Extrair descoberta/validação para código testável, evitando depender de testes frágeis do batch.

### Critérios de aceite

- Após caminho de sucesso, diagnóstico confirma `por` e o adaptador seleciona `por+eng`.
- Instalação sem permissão administrativa funciona ou apresenta alternativa explícita.
- Download adulterado é rejeitado antes de uso.
- Falha offline não danifica setup Python e é visível na inicialização/UI.
- README descreve origem, versão, licença, cache e remoção do traineddata provisionado.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 15 de docs/roadmap-melhorias-estabilidade.md. Faça o setup e o diagnóstico de inicialização verificarem tesseract --list-langs e garantirem o idioma por, em vez de aceitar somente a presença do executável. Provisione por.traineddata em pasta gravável controlada pelo aplicativo ou ambiente, sem exigir escrita em Program Files, usando origem confiável, revisão fixada, licença documentada e SHA-256 pinado; configure TESSDATA_PREFIX somente para os subprocessos necessários. Se rede ou provisionamento falhar, preserve a venv, não declare sucesso do OCR português e mostre remediação acionável na instalação e na UI. Extraia descoberta/validação para componente testável e faça por+eng ser selecionado quando ambos existirem. Teste idioma presente/ausente, instalação sem admin, offline, checksum inválido e integração com a assinatura da Etapa 14. Atualize setup.bat, README, documentação de licença e o roadmap; execute o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 16 — Credenciais efêmeras para PDFs protegidos

**Achado original:** 14.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** erros/portas PDF, casos de uso de importação/análise, estado de sessão,
`project_panel.py`, `pdf_viewer.py`, diálogo seguro e testes.

### Contexto e decisões

- Leitor e analisador aceitam senha, mas os fluxos normais da UI não solicitam nem propagam uma senha
  por documento. O visualizador guarda hoje no máximo uma senha compartilhada.
- Criar provedor de credenciais somente em memória, indexado por identidade segura do documento, com
  ciclo de vida da sessão. Nunca persistir, logar, incluir em exceção, pacote, `QSettings` ou crash dump
  controlado pela aplicação.
- Detectar `PdfProtegidoError`, solicitar senha em campo mascarado na thread principal e repetir apenas
  o documento afetado. Seleção múltipla pode ter senhas diferentes. Cancelamento deve pular/cancelar de
  forma explícita e apresentar resumo sem perder importações já confirmadas.
- Após reiniciar ou limpar a sessão, visualização/análise deve solicitar novamente antes de iniciar o
  worker; worker não pode abrir modal.
- Limitar tentativas de forma amigável e distinguir senha ausente, incorreta e PDF inválido sem vazar
  detalhes sensíveis.

### Critérios de aceite

- Importar vários PDFs protegidos com senhas diferentes funciona pela interface.
- Visualização e análise reutilizam a credencial durante a sessão e repetem a solicitação após
  reinício/limpeza.
- Senha não aparece em banco, logs, cache, manifesto, configurações ou mensagens.
- Cancelamento, senha errada, troca de arquivo e fechamento limpam estado corretamente.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 16 de docs/roadmap-melhorias-estabilidade.md. Complete o fluxo de PDFs protegidos na interface para importação, visualização e análise. Introduza um provedor de credenciais estritamente em memória e por identidade do documento; nunca persista ou registre senhas em banco, log, cache, manifesto, QSettings ou exceções. Ao receber PdfProtegidoError, solicite a senha em diálogo mascarado na thread principal e repita somente o documento afetado; múltiplos PDFs podem usar senhas diferentes. Workers não podem abrir modais: faça preflight das credenciais antes da análise. Após reinício, limpeza ou mudança de identidade, solicite novamente. Defina comportamento claro para senha errada, limite de tentativas e cancelamento com resumo. Teste fluxos unitários e pytest-qt, incluindo busca por vazamento da senha nos artefatos. Atualize documentação e o registro do roadmap; execute o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 17 — Redução e gate de complexidade ciclomática

**Achado original:** 15, parte de manutenção.  
**Estado:** PENDENTE.  
**Arquivos prováveis:** `application/project_compliance.py`, `application/mvp_workflow.py`,
`adapters/analysis/pymupdf_ocr.py`, `adapters/analysis/tesseract_ocr.py`,
`adapters/interpretation/span_rules.py`, `IniciarTestes.bat` e testes de caracterização.

### Contexto e decisões

- A revisão encontrou `_document_control_facts` com rank F, `_region_facts` com E,
  `_project_without_documents` com F, `_associate_operational_span_endpoints` com D,
  `_conditional_ocr` com D e `_parse_tsv` com D, além de outros analisadores D.
- Refatorar com testes de caracterização antes de mover decisões. Extrair funções puras e estruturas de
  dados coesas; não introduzir abstrações genéricas apenas para reduzir a métrica.
- Quebrar módulos grandes somente em fronteiras conceituais, preservando APIs públicas e proveniência.
- Depois de remover E/F, fazer o gate falhar se uma função nova atingir E ou F. Continuar relatando D
  para redução futura. Manter os relatórios de manutenibilidade e LOC.

### Critérios de aceite

- Nenhuma função de `src/` possui rank E/F.
- Comportamento semântico, IDs determinísticos, diagnósticos e ordenação permanecem iguais.
- Testes de caracterização cobrem os ramos antes complexos.
- `IniciarTestes.bat` falha de forma demonstrável diante de uma fixture/função E/F controlada ou o
  checker possui teste próprio equivalente.
- Gate básico, cobertura e benchmark público/sintético permanecem verdes.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 17 de docs/roadmap-melhorias-estabilidade.md. Recalcule a complexidade atual e elimine todas as funções rank E/F, começando por _document_control_facts, _region_facts e _project_without_documents; trate também os hotspots D mais frágeis como _associate_operational_span_endpoints, _conditional_ocr e _parse_tsv quando a extração melhorar coesão. Antes de refatorar, acrescente testes de caracterização para ramos, ordenação, IDs, diagnósticos e resultados semânticos. Extraia funções puras e módulos por fronteiras conceituais, sem abstrações artificiais ou mudança funcional. Depois, faça IniciarTestes.bat bloquear regressões E/F de forma testável e continuar relatando D, manutenibilidade e LOC. Preserve cobertura acima de 85,01%. Atualize documentação e marque esta etapa no roadmap somente após Ruff, formatação, Mypy, testes focados, relatório Radon e gate básico completo passarem.

Crie commits seccionados para as alterações, mantenha na branch main.
```

## Encerramento do ciclo

O ciclo pode ser considerado concluído quando as 17 etapas estiverem `CONCLUÍDAS`, o gate básico
passar em clone limpo sem corpus privado, o gate privado estiver documentado e executável em ambiente
autorizado, e os seguintes aceites manuais forem registrados:

1. backup degradado recusado e aceito conscientemente;
2. importação interrompida recuperada na reinicialização;
3. análise e portabilidade concorrentes corretamente bloqueadas;
4. prancha grande navegada com detalhe, overlays e memória controlada;
5. OCR em português diagnosticado e executado;
6. PDF protegido importado, visualizado e analisado sem persistência da senha;
7. exclusão de projeto confirmada sem resíduos gerenciados nem remoção do PDF original.
