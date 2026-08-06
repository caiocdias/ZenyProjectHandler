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
| 6. Coordenador central de operações | CONCLUÍDA | 3, 4 | Operações incompatíveis não concorrem |
| 7. Portabilidade assíncrona e UI não reentrante | CONCLUÍDA | 6 | UI responsiva, sem `processEvents()` manual |
| 8. Preflight de substituição antes de mutar arquivos | CONCLUÍDA | 6, 7 | Confirmação ocorre antes da troca física |
| 9. Journal e recuperação de importações interrompidas | CONCLUÍDA | 8 | Banco e arquivos reconciliados após queda |
| 10. Limpeza segura de arquivos gerenciados | CONCLUÍDA | 6, 9 | Exclusões não deixam fotos órfãs |
| 11. Identidade verificada da origem por sessão | CONCLUÍDA | 1 | Navegação não recalcula o PDF inteiro |
| 12. Renderização por orçamento e região | CONCLUÍDA | 11 | Pranchas grandes não exigem raster integral de 600 DPI |
| 13. Visualizador progressivo e assíncrono | CONCLUÍDA | 6, 12 | Zoom detalhado sem congelamento ou resultados obsoletos |
| 14. Assinatura reprodutível do OCR | CONCLUÍDA | 1 | Cache muda com motor, idioma e configuração |
| 15. Provisionamento e diagnóstico do português | CONCLUÍDA | 14 | Instalação funcional com `por`, ou erro acionável |
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
**Estado:** CONCLUÍDA.
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

### Registro de conclusão — 05/08/2026

- Foi adotado um bloqueio global conservador e não bloqueante na camada de aplicação. Análise do
  projeto, importação de PDFs/projetos, exportação, backup, restauração, exclusão de projeto/PDF/foto
  e demais alterações expostas pelos mesmos serviços adquirem exclusividade antes de logging,
  transação, temporário, cópia ou publicação. Preflights somente leitura permanecem livres; a
  operação mutável revalida o estado depois de adquirir o coordenador.
- A aquisição retorna um token que também é context manager. A saída normal, exceção e cancelamento
  passam por `__exit__` e liberam em `finally`. Liberação repetida ou tardia é idempotente e nunca
  libera um token posterior. O lock interno protege apenas a troca do token ativo e não permanece
  retido durante o caso de uso; como há um único lock, nenhuma espera e nenhuma aquisição aninhada,
  não existe ciclo de locks capaz de produzir deadlock. Reentrada acidental é recusada imediatamente.
- `OperacaoEmAndamentoError` é um erro de aplicação específico, preserva a operação solicitada e a
  operação ativa e produz uma mensagem amigável para aguardar conclusão ou cancelamento. Como os
  painéis já tratam erros de aplicação, chamadas atuais e futuras recebem a mesma recusa sem depender
  de desabilitação de botões.
- O bootstrap cria exatamente um `CoordenadorOperacoes` e compartilha a instância entre
  `ServicoFluxoMvp`, `ImportarPdfsNoProjeto` e `ServicoPortabilidadeProjeto`. O worker Qt existente
  continua chamando `ServicoFluxoMvp.executar_pipeline`; o serviço mantém o token durante toda a
  extração e interpretação, de modo que o worker também é protegido e uma recusa ocorre antes de
  qualquer execução de análise persistida.
- Testes unitários exercitam sucesso, exceção, conflito entre threads, reentrada, mensagem, dupla
  liberação, token obsoleto e independência de Qt/infraestrutura. Testes de integração comprovam a
  instância única do bootstrap, recusa no worker e na portabilidade sem mutação do banco/destino,
  sucesso subsequente, liberação após exceção e liberação após cancelamento cooperativo.
- Validações concluídas: conjunto focado final (`34 passed`); `pip check`; Ruff completo;
  `ruff format --check`; Mypy (`167 source files`); e gate básico canônico. O resultado final foi
  `292 passed, 20 deselected`, cobertura `85,37%`, complexidade média A (`3,9747`) e
  `RESULTADO FINAL: APROVADO`. O único aviso foi um `PytestCacheWarning` ambiental por falta de
  permissão para atualizar `.pytest_cache`; não houve `ResourceWarning` nem falha de teste.
- Limitação deliberada: operações potencialmente compatíveis também são serializadas. A
  portabilidade continua síncrona na thread da UI e ainda usa `QApplication.processEvents()`; essa
  responsividade e a desabilitação coordenada dos controles pertencem à Etapa 7.
- Commits: `d739531` (`feat(application): coordinate incompatible operations`) e `f9f5f32`
  (`test(application): cover operation coordination`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 6 de docs/roadmap-melhorias-estabilidade.md. Introduza um coordenador de operações na camada de aplicação, sem dependência de Qt, para impedir concorrência incompatível entre análise, importação/exportação, backup/restauração e exclusões que alterem o mesmo estado. Injete uma única instância pelo bootstrap. Use token ou context manager com liberação garantida em finally, erro de aplicação específico, mensagem amigável e sem mutação antes da aquisição. Um bloqueio global conservador é aceitável; se optar por escopos, documente uma matriz simples e prove ausência de deadlock, reentrada indevida e dupla liberação. Integre também o worker de análise existente, não apenas os botões. Adicione testes unitários e de integração para sucesso, recusa, exceção e cancelamento. Atualize o registro da etapa e execute o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 7 — Portabilidade assíncrona e interface não reentrante

**Achado original:** 4, parte de execução Qt.  
**Estado:** CONCLUÍDA.
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

### Registro de conclusão — 05/08/2026

- Importação, exportação, backup e restauração passaram a executar em um `QObject` dedicado movido
  para uma `QThread`. Progresso, pedido de confirmação, sucesso, falha/cancelamento e finalização
  carregam a identidade hexadecimal da execução; os slots do painel descartam qualquer callback que
  não pertença à execução ativa. O worker não importa nem acessa widgets.
- O preflight potencialmente demorado do backup também roda no worker. Confirmações de backup
  degradado e substituição de projeto são solicitadas por sinal e exibidas somente na thread
  principal; a resposta usa sincronização por `Event`, que o cancelamento também libera. Seletores de
  arquivo e diálogos permanecem na GUI.
- `QApplication.processEvents()` foi removido por completo do fluxo. O painel rejeita reentrada antes
  de abrir outro diálogo ou criar outra thread, desabilita suas ações imediatamente e oferece um
  botão de cancelamento. Atualizações regressivas de progresso são ignoradas, mantendo a apresentação
  monotônica inclusive quando a importação exige uma segunda tentativa confirmada.
- O coordenador da Etapa 6 ganhou observadores independentes de Qt, chamados fora do lock e incapazes
  de interferir no ciclo do token. Uma ponte Qt transforma essas transições em sinais enfileirados; a
  janela combina o estado confirmado do coordenador com o curto estado local de inicialização para
  desabilitar portabilidade, fluxo do projeto, revisão e documentação sem impedir o botão de cancelar
  da operação proprietária. A guarda dos serviços continua sendo a fonte de verdade contra corridas.
- Os casos de uso aceitam cancelamento cooperativo e o verificam entre unidades seguras de trabalho,
  antes da publicação do ZIP e antes da primeira troca física de importação/restauração. Depois que
  uma sequência de `replace`, restauração SQLite ou publicação atômica começa, ela termina ou executa
  seu rollback sem interrupção. O fechamento solicita cancelamento e espera no máximo 300 ms; se o
  trecho crítico ainda estiver ativo, mantém a janela aberta e orienta nova tentativa. Nenhum caminho
  usa `QThread.terminate()` ou outra finalização forçada.
- A finalização visual é idempotente por identidade. Quando o fechamento já aguardou a thread, a
  identidade é invalidada antes de liberar recursos, de modo que resultados enfileirados antigos não
  atualizam a janela. Sucesso, falha, cancelamento e recusa pelo coordenador liberam o token no
  `finally` do serviço, e observadores/testes comprovam uma única transição de liberação.
- Os testes `pytest-qt` usam serviços falsos controlados por `threading.Event`, sem `sleep`. Eles
  comprovam que um `QTimer` da GUI dispara enquanto o serviço está bloqueado, progresso monotônico,
  execução fora da thread principal, sucesso, erro, cancelamento, reentrada recusada, sinais
  obsoletos ignorados, desabilitação dos demais painéis e fechamento limitado sem destruir a thread.
  Os testes de integração existentes aguardam a conclusão real das quatro operações.
- Validações concluídas: conjunto focado de coordenação, serviço, workers, painel e janela
  (`42 passed`); `pip check`; Ruff completo; `ruff format --check`; Mypy (`169 source files`); e gate
  básico canônico. O resultado final foi `297 passed, 20 deselected`, cobertura `85,08%`, complexidade
  média A (`3,9606`) e `RESULTADO FINAL: APROVADO`. O único aviso foi um `PytestCacheWarning`
  ambiental por falta de permissão para atualizar `.pytest_cache`; não houve `ResourceWarning`.
- Limitação deliberada: chamadas monolíticas de bibliotecas externas, como a escrita final do ZIP ou
  o backup SQLite em andamento, não são interrompidas no meio. O pedido permanece registrado e o
  fechamento aguarda de forma limitada; isso preserva transações, publicações atômicas e rollback.
- Commits: `31094a3` (`feat(portability): run Qt operations asynchronously`) e `8a990ea`
  (`test(portability): cover asynchronous Qt lifecycle`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 7 de docs/roadmap-melhorias-estabilidade.md. Mova importação, exportação, backup e restauração do PortabilityPanel para workers Qt adequados e remova completamente QApplication.processEvents() desse fluxo. Sinais devem transportar progresso, sucesso, erro e finalização; somente a thread principal pode tocar widgets. Integre o coordenador da Etapa 6 para desabilitar todas as ações incompatíveis na janela, rejeitar duplo clique/reentrância e liberar estado exatamente uma vez. Trate fechamento da aplicação com cancelamento cooperativo em pontos seguros ou espera limitada; nunca finalize uma thread à força durante transação ou replace. Ignore sinais obsoletos por identidade de execução. Escreva testes pytest-qt com serviços falsos controláveis, sem sleeps frágeis, cobrindo responsividade, progresso, sucesso, falha, cancelamento e fechamento. Atualize o roadmap e execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 8 — Preflight de substituição antes de alterar arquivos

**Achado original:** 12, parte de ordenação.  
**Estado:** CONCLUÍDA.
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

### Registro de conclusão — 06/08/2026

- A importação foi separada em `preflight_importacao` e `aplicar_plano_importacao`. O preflight
  valida manifesto, todos os arquivos e o SQLite portátil em temporário descartável, detecta projeto
  e pasta gerenciada com o mesmo ID e devolve `PlanoImportacaoProjeto`, um DTO congelado com resumo,
  integridade, omissões, SHA-256/tamanho do pacote, fingerprint do alvo e fingerprint combinado.
- O fingerprint do alvo cobre o agregado e os registros auditáveis relacionados no SQLite, as
  referências PDF e a árvore gerenciada do ID. A identidade do pacote é calculada antes e depois da
  inspeção para detectar troca durante o próprio preflight. Nenhuma dessas leituras cria staging na
  raiz de dados, `.previous`, projeto, escrita no SQLite local ou resíduo temporário.
- O worker Qt apresenta o resumo e o fingerprint na thread principal e só chama a aplicação depois
  da resposta afirmativa. Recusa e cancelamento terminam no worker sem segunda chamada ao serviço.
  O atalho público anterior `importar_projeto` foi preservado, mas agora também passa obrigatoriamente
  pelo plano e não depende de reconhecer texto de exceção para decidir se confirma.
- A aplicação adquire o coordenador da Etapa 6 antes da revalidação. Ela recusa plano adulterado,
  confirmação ausente, mudança semântica do alvo e mudança de hash/tamanho do pacote antes de criar
  temporário de aplicação. Depois repete a validação completa do ZIP e do banco e compara o novo
  plano; `PlanoImportacaoObsoletoError` orienta executar outro preflight. Staging e publicação só
  começam quando todas as verificações coincidem.
- A persistência continua removendo o agregado anterior e gravando o conteúdo portátil com os mesmos
  IDs de projeto, catálogo, documentos, análises, evidências, propostas e decisões. A compensação de
  arquivos existente foi mantida para falhas posteriores ao início autorizado da publicação, em
  conformidade com a ADR 0008.
- Os testes fotografam todas as tabelas do banco e a árvore do diretório de dados, separadamente, em
  projeto novo, conflito recusado, conflito aceito e corridas por alteração do alvo e do pacote.
  Também comprovam no worker e no painel que a confirmação recebe o plano depois do preflight e que
  uma recusa não chama a aplicação. O conjunto focado final terminou com `25 passed`.
- Validações concluídas: `pip check`; Ruff completo; `ruff format --check` (`169 files`); Mypy
  (`169 source files`); e gate básico canônico. O resultado final foi `305 passed, 20 deselected`,
  cobertura `85,28%`, complexidade média A (`3,9536`) e `RESULTADO FINAL: APROVADO`. O único aviso
  foi o `PytestCacheWarning` ambiental já conhecido por falta de permissão para atualizar
  `.pytest_cache`; não houve `ResourceWarning` nem falha de teste.
- Commits de implementação e prova: `5f170b0` (`feat(portability): add validated import preflight
  plans`), `099afc0` (`feat(ui): confirm import plan before replacement`) e `0126f08`
  (`test(portability): snapshot import plan safety`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 8 de docs/roadmap-melhorias-estabilidade.md. Reestruture a importação de projeto em preflight sem efeitos colaterais e aplicação de um plano validado. O preflight deve validar pacote/banco, detectar projeto existente e produzir resumo/fingerprint; a UI deve pedir confirmação antes de qualquer troca de pasta ou banco. Ao aplicar, revalide pacote e estado alvo sob o coordenador da Etapa 6 e recuse planos obsoletos. Uma recusa ou falha de confirmação não pode criar .previous, publicar arquivos, alterar SQLite nem deixar temporários. Preserve IDs e semântica de substituição da ADR 0008. Adicione testes que fotografem banco e sistema de arquivos em projeto novo, conflito recusado, conflito aceito e corrida entre preflight/aplicação. Atualize ADR, documentação e registro do roadmap; execute os testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 9 — Journal persistente e recuperação de importação interrompida

**Achado original:** 12, parte de recuperação.  
**Estado:** CONCLUÍDA.
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

### Registro de conclusão — 06/08/2026

- A aplicação cria primeiro um journal JSON de formato 1 em
  `project-files/.import-recovery/import-journal-v1.json`, com publicação por temporário irmão,
  `fsync` e `os.replace`. Operação, projeto, pacote, plano, estado alvo, árvores anterior/nova, fase e
  horário formam sua identidade. Os quatro caminhos persistidos são POSIX relativos e precisam
  coincidir exatamente com os UUIDs sob a raiz gerenciada.
- O workspace reservado por operação contém apenas `staging` e `previous`. Fingerprints de conteúdo
  são calculados sem seguir links ou junções. Remoção de uma pasta publicada exige identidade
  verificada; limpezas retomadas só alcançam o workspace exato já confirmado pela fase persistida.
  Estrutura inesperada, árvore alterada, caminho hostil, versão desconhecida, JSON duplicado ou
  resíduo sem journal bloqueia o bootstrap e orienta preservar `.import-recovery`, restaurar backup
  ou solicitar suporte.
- A migração `0005_import_commits` acrescenta o comprovante de operação, projeto e hashes do pacote,
  plano e arquivos. Ele é inserido na mesma sessão e no mesmo commit do agregado importado. Na
  reconciliação, comprovante integralmente compatível conserva a árvore nova e conclui a limpeza;
  sua ausência restaura a árvore anterior. A fase declarada pelo journal nunca substitui essa prova
  transacional.
- O bootstrap migra o banco, reconcilia e só então persiste o catálogo inicial ou compõe serviços,
  coordenador e janela. Falha de leitura, contenção ou ambiguidade descarta o engine e impede a
  liberação de operações. Uma nova queda durante rollback ou limpeza deixa fases retomáveis; repetir
  a recuperação depois do término é inerte.
- Dez failpoints estáveis cobrem antes/depois da preparação, troca de arquivos, commit e limpeza,
  incluindo a janela após o commit e antes da atualização do journal. Os testes também cobrem
  recuperação interrompida nas duas decisões, repetição, resíduos órfãos, journal corrompido,
  caminhos relativos hostis, estado ambíguo, escrita atômica e liberação do SQLite no bloqueio.
- O logging estruturado aceita `phase`, `recovery_action` e `journal_version`. Eventos
  `portability.import.journal` e `portability.import.recovery` permanecem correlacionáveis e não
  incluem caminho absoluto, nome de arquivo ou conteúdo. README, especificação funcional e ADR 0008
  documentam o protocolo e o procedimento acionável para bloqueio seguro.
- Validações concluídas: conjunto focado de journal, persistência, portabilidade, logging e bootstrap
  (`63 passed`); `pip check`; Ruff completo; `ruff format --check` (`173 files`); Mypy
  (`173 source files`); e gate básico canônico. O resultado final foi `325 passed, 20 deselected`,
  cobertura `85,19%`, complexidade média A (`3,9145`) e `RESULTADO FINAL: APROVADO`. O único aviso
  foi o `PytestCacheWarning` ambiental já conhecido por falta de permissão para atualizar
  `.pytest_cache`; não houve `ResourceWarning` nem falha de teste.
- Commits de implementação e prova: `e7053cc` (`feat(portability): recover interrupted project
  imports`) e `329ccfd` (`test(portability): cover journal crash recovery`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 9 de docs/roadmap-melhorias-estabilidade.md. Acrescente um journal persistente, versionado e escrito atomicamente para tornar substituições de projetos recuperáveis entre troca de arquivos e commit do SQLite. Registre identidade e fases suficientes, usando somente caminhos relativos validados dentro da raiz gerenciada. Integre uma reconciliação idempotente no bootstrap antes de liberar novas operações: conclua quando houver prova do commit ou restaure o estado anterior quando não houver. Journal corrompido ou ambíguo deve bloquear mutações com diagnóstico acionável, nunca disparar exclusão ampla. Crie pontos de injeção de falha testáveis e cubra interrupções antes/depois de cada fase, recuperação repetida, resíduos e contenção de caminhos. Atualize ADR 0008, logging, documentação e o registro do roadmap; execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 10 — Limpeza transacional de arquivos gerenciados

**Achado original:** 7.  
**Estado:** CONCLUÍDA.
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

### Registro de conclusão — 06/08/2026

- `GerenciadorArquivosGerenciados` centraliza a exclusão usada por projeto, remoção de documentos
  e fotos/localização de anexos. O bootstrap injeta a mesma instância nos serviços do MVP e de
  portabilidade, sob o coordenador global existente. PDFs originais continuam apenas como
  referências externas e nunca entram na lista de candidatos.
- A exclusão integral publica um journal de formato 1 em `.cleanup-recovery`, valida que a árvore é
  regular e renomeia a raiz UUID para um tombstone derivado da operação. Falha do commit restaura o
  rename; commit concluído permite remover somente o tombstone. Raiz originalmente ausente é um caso
  idempotente e não amplia o alvo.
- Exclusões parciais registram fotos candidatas antes da transação e recalculam os SHA-256 vivos no
  agregado confirmado. Caminho, contenção na raiz de dados, arquivo regular e digest são conferidos
  antes do `unlink`; duas referências ao mesmo digest preservam o blob até a última ser removida.
- Journals de importação e limpeza mantêm semânticas e namespaces independentes, mas compartilham
  a implementação de JSON canônico sem chaves duplicadas, limite de tamanho, temporário irmão,
  `fsync`, `replace` e caminho POSIX seguro. O bootstrap reconcilia ambos antes de liberar a UI.
- Interrupção com projeto ainda vivo restaura o tombstone; projeto ausente conclui a limpeza. Falha
  de I/O depois do commit retorna `limpeza_pendente`, emite `managed_files.cleanup.failed` com ação
  `retry_cleanup` e conserva o journal. Corrupção, link, travessia ou estado ambíguo bloqueia a
  reconciliação sem tocar o caminho hostil.
- A UI agora distingue cadastro/análises/revisões, fotos e cópias internas gerenciadas dos PDFs
  originais externos. Remoção seletiva informa que fotos compartilhadas só são apagadas sem
  referência viva e apresenta explicitamente qualquer limpeza pendente.
- Testes focados aprovados: journals, compartilhamento, rollback do banco, interrupção nas duas
  decisões, nova tentativa pós-commit, raiz ausente, caminho malicioso, serviços, janela e UI
  (`64 passed` no conjunto não-E2E e `2 passed` no E2E isolado).
- Gate básico canônico aprovado: `pip check`; Ruff; `ruff format --check` (`176 files`); Mypy
  (`176 source files`); `337 passed, 20 deselected`, cobertura `85,10%`; complexidade média A
  (`3,9074`); e `RESULTADO FINAL: APROVADO`. O único aviso foi o `PytestCacheWarning` ambiental já
  conhecido por falta de permissão para atualizar `.pytest_cache`; não houve `ResourceWarning` nem
  falha de teste.
- Commits seccionados de implementação e prova: `06b5347` (`feat(storage): make managed file cleanup
  recoverable`), `7248914` (`test(storage): cover transactional managed cleanup`) e `179b697`
  (`test(storage): harden cleanup retry coverage`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 10 de docs/roadmap-melhorias-estabilidade.md. Centralize a exclusão de arquivos gerenciados usada por projeto, documento e elementos/fotos. Nunca apague PDFs originais externos. Valide containment na raiz de dados, considere blobs por digest compartilhados e remova somente arquivos sem referência viva após a transação. Para projeto inteiro, use tombstone por rename recuperável: restaure em rollback e limpe apenas depois do commit; integre coordenador e journal existentes sem duplicar protocolo. Falhas pós-commit devem ficar registradas para nova limpeza, não ser ocultadas. Ajuste o texto da UI para refletir exatamente o que é removido. Adicione testes de compartilhamento, rollback, interrupção, raiz ausente e caminhos maliciosos. Atualize documentação e o registro da etapa; execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 11 — Identidade verificada da origem durante a sessão

**Achado original:** 6.  
**Estado:** CONCLUÍDA.

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

### Registro de conclusão — 06/08/2026

- A porta PDF passou a expor `SessaoLeituraPdfPort`, criada por `abrir_sessao()`. A abertura calcula
  SHA-256 uma vez, inventaria o documento e registra tamanho, `mtime`, `ctime`, dispositivo e inode.
  Os metadados são comparados depois do hash e da inspeção para rejeitar uma origem que mude durante
  a abertura.
- A sessão do adaptador PyMuPDF guarda somente inspeção, identidade e credencial efêmera. Cada
  rasterização confere os metadados antes e depois, abre seu próprio `fitz.Document` e o fecha em
  `finally`. Alteração, substituição ou remoção invalida a sessão definitivamente e exige nova
  abertura/inspeção, sem hash implícito nem cache global por caminho.
- O visualizador mantém uma sessão por PDF do projeto aberto. Candidatas são encerradas quando uma
  abertura composta falha; as anteriores são encerradas na troca; e todas são liberadas em `limpar()`
  e `closeEvent()`. Documentos persistidos ainda validam o SHA-256 esperado ao abrir. O raster e o
  `TransformadorCoordenadasPagina` continuaram recebendo os mesmos DPI, dimensões e rotações, sem
  mudança de geometria ou overlays.
- O hasher instrumentado comprovou uma chamada em uma sessão com três páginas, recorte e rotações.
  Os testes também cobrem modificação e reabertura, uso posterior de sessão encerrada/invalidada,
  troca de documento, encerramento do widget e movimentação real do PDF enquanto a sessão existe,
  demonstrando a ausência de lock persistente no Windows.
- `inspecionar()`, `verificar_origem()` e a renderização avulsa com hash esperado continuam fazendo
  verificação integral. Os verificadores independentes de análise, importação e portabilidade não
  foram convertidos para a checagem barata. O conjunto focado ampliado dessas fronteiras e da UI
  aprovou `77 passed`.
- O primeiro gate expôs uma falha nativa reproduzível do Qt 6.11 no painel de portabilidade: o
  `QThread` recebia `deleteLater()` antes da finalização dos widgets. A ordem foi corrigida em commit
  isolado, o arquivo focado aprovou `7 passed` e o gate canônico seguinte passou integralmente.
- Gate básico aprovado: `pip check`; Ruff; `ruff format --check` (`176 files`); Mypy (`176 source
  files`); `343 passed, 20 deselected`, cobertura `85,16%`; complexidade média A (`3,8665`); e
  `RESULTADO FINAL: APROVADO`. Permaneceu somente o `PytestCacheWarning` ambiental já conhecido por
  falta de permissão para atualizar `.pytest_cache`; não houve `ResourceWarning`.
- Commits seccionados: `220d432` (`feat(pdf): add verified source sessions`), `31886df`
  (`test(pdf): cover verified session lifecycle`) e `a2dc5dc`
  (`fix(ui): defer portability thread deletion`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 11 de docs/roadmap-melhorias-estabilidade.md. Elimine o SHA-256 integral repetido a cada renderização criando uma sessão ou handle de origem verificada na porta PDF e no adaptador PyMuPDF. Calcule o hash uma vez ao abrir, capture metadados estáveis e faça checagem barata antes dos usos; qualquer alteração deve invalidar a sessão e exigir nova inspeção. Não crie cache global eterno por caminho, feche documentos/handles deterministicamente e não mantenha locks que impeçam backup ou restauração no Windows. Mantenha verificação forte nas fronteiras de análise, importação e portabilidade. Adapte o visualizador sem mudar geometrias. Teste com hasher instrumentado, múltiplas páginas/rotações, modificação do arquivo, troca de documento e encerramento. Atualize ADR 0003 se o contrato mudar, registre a etapa e execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 12 — Renderização por orçamento de pixels e regiões

**Achado original:** 5, parte do backend de visualização.  
**Estado:** CONCLUÍDA.

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

### Registro de conclusão — 06/08/2026

- `OrcamentoRenderizacaoPdf` tornou obrigatórios limites independentes de pixels e bytes em toda
  rasterização visual. `PlanoRenderizacaoPdf` calcula o `IRect` exato da página/clip após escala e
  rotação, antes de `Page.get_pixmap()`. O pico conservador considera 7 bytes por pixel: 3 do RGB
  compartilhado por PyMuPDF/QImage e 4 esperados do QPixmap.
- Páginas integrais que excedem qualquer limite recebem o maior DPI inteiro que caiba em ambos. O
  teto solicitado continua em 600 DPI; clips normalizados que cabem preservam esse detalhe. A
  configuração padrão ficou em 8.000.000 pixels e 64 MiB e ganhou as variáveis
  `ZENY_PDF_RENDER_MAX_PIXELS` e `ZENY_PDF_RENDER_MAX_BYTES`, sem alterar
  `ZENY_PDF_RENDER_DPI` nem qualquer configuração de análise/OCR.
- O plano regional registra dimensões da página, dimensões do clip e sua origem no raster
  rotacionado. `TransformadorCoordenadasPagina` passou a considerar esses valores; goldens
  assimétricos comprovaram pixels, clips, round-trip e alinhamento nas rotações 0/90/180/270 graus.
  Um caso adicional preservou `CropBox` com rotação intrínseca e adicional.
- `PaginaPdfRenderizada` retém o `Pixmap` dono de `samples_mv` e entrega uma `memoryview` ao QImage.
  Foram removidas as cópias intermediárias para `bytes` e `QImage.copy()`; o resultado permanece vivo
  até `QPixmap.fromImage()` concluir a conversão na thread da interface.
- PDFs sintéticos A0/A1 registraram solicitações integrais entre 270 e 550 milhões de pixels a
  600 DPI sem alocar esses rasters. As prévias reais ficaram em até 120.000 pixels/840.000 bytes de
  pico estimado, enquanto clips de 1% foram efetivamente rasterizados a 600 DPI.
- Testes focados finais: `76 passed`. O gate básico canônico aprovou `pip check`, Ruff,
  `ruff format --check` (`177 files`), Mypy (`177 source files`), `361 passed, 20 deselected`, cobertura
  `85,17%`, complexidade média A (`3,8449`) e `RESULTADO FINAL: APROVADO`. Permaneceu somente o
  `PytestCacheWarning` ambiental já conhecido por falta de permissão em `.pytest_cache`; o corpus
  privado não foi acessado.
- Commits seccionados: `f264ae7` (`feat(pdf): add budgeted regional rendering`) e `55be25d`
  (`test(pdf): cover budgeted clips and large sheets`).
- Limitação remanescente deliberada: a interface desta etapa usa a prévia integral orçada. A
  composição progressiva/assíncrona dos clips detalhados, a priorização do viewport e o cache LRU
  limitado por bytes pertencem à Etapa 13.

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 12 de docs/roadmap-melhorias-estabilidade.md. Redesenhe o backend de renderização do visualizador para usar orçamento explícito de pixels/bytes e renderização por clip ou tiles. Mantenha 600 DPI como teto de detalhe disponível sob demanda, mas nunca aloque uma prancha A0/A1 inteira nessa resolução. Páginas pequenas podem usar raster integral; páginas grandes devem ter prévia limitada e regiões de alta resolução. Preserve CropBox, rotações, transformações normalizadas e alinhamento de overlays, e cuide da vida útil do buffer ao reduzir cópias entre PyMuPDF, bytes, QImage e QPixmap. Não altere DPI, decisões ou resultados do pipeline de análise/OCR. Adicione goldens para clips e rotações e teste sintético de A0/A1 que verifique dimensões solicitadas sem alocar gigabytes. Atualize ADR 0003, README/configuração e o registro da etapa; execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 13 — Visualizador progressivo, assíncrono e com cache limitado

**Achado original:** 5, parte da experiência Qt.  
**Estado:** CONCLUÍDA.

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

### Registro de conclusão — 06/08/2026

- `PdfViewerWidget` passou a abrir cada página com uma prévia integral orçada e a refiná-la com
  clips detalhados assíncronos somente no viewport e em uma margem de um tile. A prioridade combina
  visibilidade e distância ao centro; pan, zoom, rotação, navegação e mudança de DPR iniciam nova
  geração e cancelam cooperativamente a anterior.
- Toda solicitação identifica geração, UUID/SHA-256/tamanho/`mtime` verificados, página, rotação,
  zoom, DPR, região canônica, DPI e tipo prévia/tile. Só respostas que ainda correspondem ao estado
  corrente chegam à cena. Regiões visuais são convertidas de volta ao espaço canônico nas rotações
  90/180/270 antes de chamar o backend regional da Etapa 12.
- A fila serial priorizada rasteriza em `QThread`, sem acessar widgets, cena ou `QPixmap`. O worker
  materializa uma única cópia RGB proprietária e libera o `Pixmap` nativo do PyMuPDF na thread que o
  criou; `QImage`, `QPixmap` e todas as mutações visuais ficam na UI. Isso elimina proprietários
  nativos entre threads sem elevar o pico conservador de 7 bytes por pixel.
- O cache visual é LRU com limite estrito em bytes de `QPixmap`, 128 MiB por padrão via
  `ZENY_PDF_TILE_CACHE_MAX_BYTES`. A chave contém a identidade verificada e todo o estado visual
  reutilizável; troca de documentos, limpeza ou alteração detectada da origem esvazia o cache.
- Prévia e tiles usam camadas abaixo dos overlays e links de revisão. Testes confirmaram alinhamento
  e clique nas rotações 0/90/180/270. O DPI de detalhe deriva do zoom e DPR e continua limitado pelo
  teto visual configurado de até 600 DPI; análise/OCR, seus DPIs e suas decisões não foram alterados.
- O conjunto `pytest-qt` determinístico cobre responsividade com backend bloqueado por `Event`,
  execução fora da UI, resultado fora de sequência, invalidação por troca/alteração, limite e
  evicção LRU, prioridade/conversão de regiões, rotação com overlay clicável e fechamento durante
  raster ativo. O fechamento da janela principal também possui regressão para encerramento explícito
  da fila e das sessões.
- O roteiro `docs/aceite-manual-visualizador-progressivo.md` registra o aceite com A0/A1 autorizada,
  incluindo nitidez em zoom, prioridade do viewport, DPR, memória, quatro rotações, invalidação e
  fechamento. A prancha privada não integra nem foi acessada pelo gate automatizado.
- Gate básico aprovado: `pip check`; Ruff; `ruff format --check` (`179 files`); Mypy (`179 source
  files`); `371 passed, 20 deselected`, cobertura `85,03%`; complexidade média A (`3,8006`); e
  `RESULTADO FINAL: APROVADO`. Permaneceu somente o `PytestCacheWarning` ambiental já conhecido por
  falta de permissão em `.pytest_cache`; não houve falha ou aviso de ciclo de vida Qt.
- Commits seccionados: `2bf9c56` (`feat(viewer): add progressive regional rendering`), `c2d1fa0`
  (`test(viewer): cover progressive rendering lifecycle`), `14dd784`
  (`style(viewer): apply canonical formatting`), `0a2e3f4`
  (`fix(viewer): stop render queue with main window`) e `d4f4de6`
  (`fix(viewer): own raster buffers across worker boundary`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 13 de docs/roadmap-melhorias-estabilidade.md. Use o backend regional da Etapa 12 para tornar o PdfViewer progressivo e assíncrono: prévia rápida e tiles de alta resolução priorizados pelo viewport. Identifique cada solicitação por geração, documento, página, rotação, zoom, devicePixelRatio e região; descarte resultados obsoletos. Crie cache LRU limitado por bytes e coerente com a identidade verificada da Etapa 11, limpando-o em troca ou alteração do documento. Não toque widgets ou QPixmap fora da thread permitida, preserve overlays clicáveis/alinhados e use cancelamento cooperativo. Não reduza qualidade da análise nem o detalhe visual disponível em zoom. Escreva testes pytest-qt determinísticos para responsividade, ordenação fora de sequência, invalidação, limite do cache, rotação e fechamento. Documente um roteiro de aceite manual com prancha grande, atualize o roadmap e execute o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 14 — Assinatura reprodutível do motor OCR e invalidação de cache

**Achado original:** 8.  
**Estado:** CONCLUÍDA.
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

### Registro de conclusão — 06/08/2026

- A porta de OCR passou a expor uma capacidade canônica com implementação, versão real normalizada,
  idiomas ordenados efetivamente selecionados, SHA-256 dos `traineddata` correspondentes e parâmetros
  semânticos. O Tesseract declara explicitamente OEM, PSM dos quatro perfis, whitelists, formato e
  agregação TSV, pré-processamento PPM e timeout de reconhecimento; nenhum caminho entra no payload.
- `--version` e `--list-langs` são executados uma vez por instância com timeout. O diretório
  `tessdata` identificado é fixado para o reconhecimento subsequente. Timeout, subprocesso inválido,
  idioma ausente ou dados ilegíveis retornam códigos determinísticos e desativam somente o OCR; os
  extratores nativos permanecem ativos.
- A assinatura OCR compõe uma assinatura de capacidade do analisador. Esse mesmo valor entra na
  chave do cache, no UUID v5 estável da extração e nos parâmetros persistidos de execução e
  evidência. O cache JSON avançou para o schema 2 e trata o schema 1 como dado derivado ausente,
  reconstruindo-o sem migração.
- Motores falsos cobrem invalidação independente por versão, idioma, hash de `traineddata` e OEM.
  Subprocessos simulados cobrem normalização da versão, identidade igual em pastas diferentes,
  consulta única, timeouts e falhas sanitizadas. A ausência de motor preserva texto, vetores,
  imagens, anotações e Forms.
- Validações focadas concluídas: `58 passed`. O gate básico final aprovou `391 passed, 20 deselected`,
  cobertura `85,11%`, Ruff, `ruff format --check`, Mypy (`179 source files`), `pip check` e métricas
  Radon. Uma primeira execução encontrou uma violação de acesso nativa e intermitente do Qt; o teste
  isolado passou, a repetição prosseguiu e os testes públicos ficaram verdes. A cobertura então foi
  recuperada de `84,88%` com testes dos novos ramos, sem alterar o limite de `85,01%`.
- Limitação remanescente: provisionamento e diagnóstico orientado especificamente ao idioma `por`
  continuam pertencendo à Etapa 15. O custo de ler e hashear os `traineddata` ocorre uma vez por
  instância.
- Commits: `2e59ef6` (`feat(ocr): derive reproducible capability identity`), `2b76151`
  (`test(ocr): cover capability-driven invalidation`) e `b885bbf`
  (`test(ocr): cover capability failure diagnostics`).

### Mensagem para um novo chat do Codex

```text
Implemente a Etapa 14 de docs/roadmap-melhorias-estabilidade.md. Substitua a versão estática do Tesseract por uma assinatura reprodutível de capacidade na porta de OCR. Inclua versão real normalizada, idiomas efetivamente selecionados, identidade dos traineddata relevantes e todos os parâmetros do adaptador que alterem a saída, sem incorporar caminhos específicos da máquina. Consulte capacidades uma vez por instância com timeout e diagnóstico. Use essa assinatura tanto na chave do cache derivado quanto na identidade/proveniência da execução; invalide caches antigos incompatíveis de modo limpo. Ausência do Tesseract não pode impedir os extratores nativos. Adicione testes com motores/subprocessos falsos provando invalidação por versão, idioma, traineddata e configuração e estabilidade entre caminhos diferentes. Atualize ADR 0004, README e o registro da etapa; execute testes focados e o gate básico completo.

Crie commits seccionados para as alterações, mantenha na branch main.
```

---

## Etapa 15 — Provisionamento e diagnóstico do idioma português

**Achado original:** 9.  
**Estado:** CONCLUÍDA.
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

### Registro de conclusão — 06/08/2026

- `tesseract_runtime.py` centralizou descoberta do executável, execução limitada de
  `tesseract --list-langs`, seleção de idiomas e diagnóstico sanitizado. A inicialização só compõe
  o adaptador se `por` foi observado; quando `por` e `eng` estão disponíveis na mesma raiz, a ordem
  efetiva é `por+eng`. Ausência ou defeito do OCR mantém os extratores nativos e cria na barra de
  status uma ação “como corrigir” com remediação completa.
- O setup agora conclui dependências, instalação editável e `pip check` antes da etapa OCR. Por isso,
  falha de `winget`, rede, pasta ou validação preserva a `.venv` e retorna erro sem declarar o OCR
  português pronto. O executável é tentado com escopo de usuário; instalações autorizadas podem ser
  indicadas por `ZENY_TESSERACT_PATH`.
- Quando a instalação selecionada não contém `por`, o provisionador grava em
  `<dados>/ocr/tessdata-fast-4.1.0` ou `ZENY_TESSDATA_DIR`, sem escrever em `Program Files`. A origem
  é `tesseract-ocr/tessdata_fast` 4.1.0, revisão
  `65727574dfcd264acbb0c3e07860e4e9e9b22185`, Apache-2.0, com SHA-256 pinado
  `c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb`. Download temporário só é
  promovido atomicamente após o hash; `eng` já instalado é copiado para a raiz gerenciada para
  permitir `por+eng`.
- `TESSDATA_PREFIX` não é publicado no processo do aplicativo nem no sistema: cada consulta de
  idiomas e reconhecimento recebe uma cópia de ambiente própria. O adaptador continua hasheando os
  arquivos efetivamente usados, portanto a assinatura, o cache e a proveniência da Etapa 14 mudam
  quando o conteúdo provisionado muda.
- Testes simulados cobrem idioma presente/ausente, caminho inválido, timeout, pasta sem permissão,
  instalação sem admin, offline com `.venv` preservada, checksum adulterado, cópia de `eng`,
  `por+eng`, ambiente filho, CLI/setup, aviso acionável na UI e integração com a assinatura da Etapa
  14. Os testes focados finais aprovaram `60 passed`.
- O gate básico canônico aprovou Python 3.13.14, `pip check`, Ruff, `ruff format --check` (`183
  files`), Mypy (`183 source files`), `408 passed, 20 deselected`, cobertura `85,16%`, complexidade
  média A (`3,7938`) e `RESULTADO FINAL: APROVADO`. Permaneceu somente o `PytestCacheWarning`
  ambiental já conhecido por falta de permissão em `.pytest_cache`; o corpus privado não foi
  acessado.
- Commits seccionados: `b823871` (`feat(ocr): provision pinned Portuguese tessdata`), `4729cf7`
  (`test(ocr): cover Portuguese provisioning diagnostics`) e `553dea0` (`test(ocr): cover runtime
  remediation branches`).

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
