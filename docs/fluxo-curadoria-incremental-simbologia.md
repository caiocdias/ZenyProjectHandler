# Curadoria contínua de simbologia — cobertura e qualidade por demanda

Este é o contrato operacional independente para ampliar os pacotes de símbolos
e medir a cobertura integrada. O usuário adiciona PDFs localmente em `examples/`
e envia o prompt ao fim deste arquivo. As antigas frentes E07 (pacotes) e E16
(aceite integrado) são trabalhadas no mesmo ciclo C01–C04; seus rótulos servem
apenas para identificar donos dos métodos e o checkpoint histórico.
Uma execução **não treina o assistente de forma permanente**. Conhecimento
duradouro é uma mudança revisável nos pacotes, no inventário quando necessário
e nas fixtures/testes versionados. O chat e os PDFs ignorados pelo Git não são
uma base de conhecimento persistente.

O fluxo já pode ser feito por agentes com as ferramentas atuais. Cada rodada
parte das lacunas publicadas na matriz E16, dá prioridade aos casos observados
nos PDFs adicionados e termina com uma nova matriz local e um delta de cobertura.
Isso torna a lacuna mensurável e encaminha a correção à etapa dona do método.
Automatizar rotulagem ou treino é uma melhoria futura. Uma rodada pode reduzir
uma lacuna, revelar regressão ou apenas registrar que faltou evidência; não há
garantia de ganho a cada execução. O resultado da rodada é ganho validado,
regressão ou pendência documentada, com denominadores.

## Ponto de partida e critério de melhoria

O inventário congelado em
[`data/inventario-simbologia-v1.json`](data/inventario-simbologia-v1.json),
validado por [`schemas/inventario-simbologia.schema.json`](schemas/inventario-simbologia.schema.json),
contém **427 IDs em 33 famílias**. O checkpoint de cobertura
[`data/matriz-simbologia-e16.csv`](data/matriz-simbologia-e16.csv) e seu
[`resumo`](data/matriz-simbologia-e16-resumo.json) classificam todos: **33
exatos somente sintéticos, 34 alternativas sem ID, 97 informativos, 251 ainda
não suportados e 12 não avaliáveis por ID**. Dos 365 IDs atribuídos a pacotes,
21 estão `enabled` e 344 `pending`; 93 desses últimos têm destino informativo.
Nenhum `pending` é reconhecimento. Esses números são o começo, não metas
reduzidas nem estimativas de campo. Se o inventário crescer, a rodada recalcula
o denominador e justifica cada ID novo.
Um localizador `SRC-LOCAL.url` do inventário congelado aponta para documentação
histórica retirada; ele é metadado de origem e não instrui este fluxo. O arquivo
permanece byte a byte igual para conservar os hashes da referência.

O bloqueio de qualidade também é real: a primeira reserva sintética independente
teve união adotada **1 TP/0 FP/3 FN em 4 positivos**, sem ganho sobre o legado.
Na tentativa posterior, a referência não passou na validação de famílias E01;
as cinco predições operacionais para 30 positivos confirmados limitam o recall
de candidatos a **16,7%**, mas FP e precisão dessa tentativa não são avaliáveis.
As duas reservas estão consumidas. No desenvolvimento e nos exemplos, uma
rodada deve demonstrar o delta de cobertura, TP/FP/FN, exclusivos, ambiguidades,
custos e regressões; isso não equivale a homologação de campo.

Para um **novo aceite integrado**, após melhorias em desenvolvimento e
calibração independente, congelar código/configuração e uma nova reserva
independente de desenho, validar esquema/famílias E01 antes de lacrá-la e medir
uma única vez sem ajuste sobre a referência. As metas herdadas são recall de
candidatos e precisão final **≥95% por família avaliável**, zero FP nos
negativos críticos, zero fusão entre páginas e zero promoção com conflito
técnico. A composição preserva acertos exclusivos válidos, supera o baseline
no mesmo conjunto e tem contribuições exclusivas de pelo menos duas famílias
algorítmicas distintas. Promoção automática exige precisão observada ≥99%
em amostra independente suficiente; subconjunto vazio não satisfaz a meta.
Executar V-P integral, V-Q, V-G, benchmark reservado e inspeção manual da
UI/exportações. Se faltar teste, calibração ou meta, publicar a pendência,
sem declarar aceite. O ciclo C01–C04 pode continuar enquanto isso.

## Contrato e limites

- `examples/` é uma bancada local dinâmica conforme
  [ADR 0005](adr/0005-exemplos-locais-dinamicos.md). PDFs reais e relatórios
  com caminhos/recortes ficam fora do Git, em `tmp/curadoria-simbologia/`.
  Não copiar PDFs privados para fixtures ou enviar seu conteúdo a serviços
  externos. O gate portátil continua sintético.
- Adicionar um PDF **não ensina automaticamente** o detector. Primeiro é
  preciso ver as páginas, identificar ocorrências e negativos, conferir a
  fonte/legenda e testar uma regra ou template. Um rótulo sugerido por IA é
  hipótese de revisão, não verdade confirmada pelo usuário.
- Uma forma que admite vários IDs gera **uma observação física com alternativas
  explícitas**. O ID exato só pode ser emitido quando texto, cor, camada, legenda
  ou contexto verificável o distingue. Ambiguidade não vira vários ativos.
  Alternativas só contam como reconhecimento do grupo visual se o pacote e seus
  positivos/negativos estiverem verificados; sem isso, o grupo continua pendente.
  Desconhecido continua desconhecido e não conta como variante reconhecida.
- A legenda local limita o significado ao documento/revisão. Ela é referência,
  não ocorrência operacional. Símbolos informativos, norte e desenhos §33
  continuam informativos, mesmo quando parecem equipamento. PDF de projeto
  revela casos e estilos, mas não cria norma ou obrigação de conformidade.
- Cada execução usa uma versão congelada dos pacotes e da inferência. A
  referência visual/ROI do revisor fica fora da entrada do detector. Silêncio
  de outro método não veta um candidato exclusivo; concordância não é
  probabilidade.
- Um PDF já visto passa a ser desenvolvimento. As reservas anteriores já foram
  abertas e não servem como teste cego repetido. Uma reserva futura precisa de
  seleção, esquema validado e congelamento próprios, sem receber regras ou
  rótulos do desenvolvimento.
- A matriz E16 preservada no workspace é o **ponto de partida histórico** da primeira rodada.
  Rodadas posteriores partem de `docs/data/matriz-simbologia-curadoria-atual.csv`,
  atualizado somente após os gates da rodada. A matriz e o resumo históricos
  permanecem preservados. O delta de IDs não comprova recall real, ganho da
  união nem aceite reservado; medir cada um em seu conjunto apropriado.

## Etapas repetíveis para uma execução

As etapas C01–C04 pertencem **a cada execução**. Seu
estado, cobertura, hashes e impedimentos são registrados no relatório local
da execução. Uma etapa sem evidência não é marcada como concluída.

### C01 — Descobrir e congelar entradas

**Dono:** coordenador. Ler instruções do repositório, este fluxo, ADR 0005,
inventário JSON/esquema, pacotes/esquema, comandos e `git status/diff`. Descobrir
recursivamente todos os PDFs de `examples/`, inclusive `.PDF`, e registrar
caminho relativo, SHA-256, tamanho, páginas, legibilidade e versão/configuração.
Comparar com o manifesto local anterior quando existir, mas não presumir que
arquivo ausente foi validado. Duplicatas por hash mantêm todos os caminhos.

**Saída:** manifesto completo em `tmp/curadoria-simbologia/<execucao>/`,
lista de PDFs/páginas novos, modificados, inalterados e ilegíveis. Não escrever
no Git nesta etapa. Copiar a matriz anterior (curadoria atual, ou E16 histórica
na primeira rodada) para `matriz-antes.csv`, registrando SHA-256. Gerar
`plano-lacunas.json` com
`scripts.curation_coverage_e16 plan`; ele inclui todos os IDs do inventário em lacuna e
seu dono E04/E05/E06/E07, com denominador. Não tratar a fila como rótulo.

```powershell
$rodada = "tmp/curadoria-simbologia/<execucao>"
New-Item -ItemType Directory -Force -Path $rodada | Out-Null
$anterior = "docs/data/matriz-simbologia-curadoria-atual.csv"
if (-not (Test-Path $anterior)) { $anterior = "docs/data/matriz-simbologia-e16.csv" }
Copy-Item -LiteralPath $anterior -Destination "$rodada/matriz-antes.csv"
.\.venv\Scripts\python.exe -m scripts.curation_coverage_e16 plan --matrix "$rodada/matriz-antes.csv" --output "$rodada/plano-lacunas.json"
```

Substituir `<execucao>` por um nome único e registrar qual arquivo foi copiado.

### C02 — Revisar visualmente antes de comparar predições

**Dono:** agente visual independente C, em lotes de páginas sem lacunas. Abrir
imagens renderizadas de **todas as páginas novas ou modificadas**, em visão
geral e recortes legíveis, considerando base e anotações. Registrar ocorrência,
ausência, papel operacional/informativo, possíveis IDs, negativos próximos,
contexto que desambigua e incerteza. JSON, OCR e lista de predições não
substituem a visão real. Reutilizar revisão anterior de página inalterada
somente com hash e configuração compatíveis, declarando o reuso.

**Saída:** observações congeladas antes da comparação com predições. Se o ID
exato não for comprovável, registrar conjunto de alternativas ou desconhecido.
Após congelar a revisão, produzir `demanda.json` local no formato
`{"ids": ["<ID E01>"]}` só com IDs observados ou confundidos. Regerar o plano
com `--demand`; IDs citados sob demanda sobem na fila sem receber status novo.
Se a observação não resolve sequer um ID candidato, mantê-la fora dessa lista
e registrá-la como desconhecida no relatório visual.

### C03 — Confrontar, curar e testar

**Dono:** coordenador congela a interface e distribui arquivos com um único
responsável: A edita apenas pacotes/runner que lhe forem atribuídos; B edita
fixtures/testes separados; C compara imagens e saídas sem editar detector.
Inferir com os PDFs e o snapshot congelado **antes** de ler a referência do
revisor no comparador. Registrar TP, FP, FN, duplicatas, exclusivos, casos
ambíguos e falta de positivo por família, com denominadores. Resolver
divergências pela imagem e fonte; não ajustar regra pela ROI do revisor.

Promover conhecimento apenas quando houver fonte rastreável, gramática/template
ou contexto discriminante, positivo e negativos independentes e papel correto.
Uma nova família/revisão altera o inventário com ID estável e fonte conferida.
Caso real reproduzível vira fixture sintética autoral pequena; PDF/recorte
privado não é copiado. O que não pode ser decidido permanece `pending`
com motivo e próximos dados necessários. Não marcar 344 variantes como
reconhecidas só porque estão cadastradas.

Priorizar o cruzamento entre a demanda visual e a fila de lacunas. Pacotes E07 só
resolvem suas variantes; lacunas E04/E05/E06, FP da união, legenda, anotação,
raster ou desempenho voltam ao módulo/etapa responsável e recebem checkpoint
novo antes da integração. Uma correção fora dos pacotes exige seus próprios
relatórios de benchmark atualizados. Não alterar detector, referência ou metas
usando reservas E16 já abertas.

**Saída:** diff revisável de pacotes/inventário/testes, relatório por família
e lista explícita de pendências. Não modificar o reconciliador para cadastrar
uma família por dados nem criar regra de conformidade a partir do exemplo.

### C04 — Integrar e registrar o checkpoint

**Dono:** coordenador. Conferir retornos A/B/C, integrar registro central
serialmente, congelar arquivos e repetir os gates afetados. O esquema de pacotes
é [`schemas/pacotes-simbologia.schema.json`](schemas/pacotes-simbologia.schema.json):
`enabled` requer gramática, fonte e positivos/negativos; `pending` requer motivo
e não emite ID. Confrontar seu SHA com o relatório do benchmark da mesma rodada.
Para o contrato atual, conferir ao menos:

```powershell
.\.venv\Scripts\python.exe -m scripts.audit_symbol_packages --output "$rodada/audit.json"
.\.venv\Scripts\python.exe -m scripts.benchmark_packages_e07 --output "$rodada/benchmark"
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output "$rodada/baseline"
.\.venv\Scripts\python.exe -m pytest tests/unit/test_declarative_symbol_packages.py tests/unit/test_benchmark_symbols.py tests/unit/test_symbol_inventory.py -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output "$rodada/predictions"
.\.venv\Scripts\python.exe -m pytest --cov -o cache_dir=C:\tmp\curadoria-vg-cache --basetemp=C:\tmp\curadoria-vg
```

Para medir a união completa e seus exclusivos, executar também o benchmark com
os métodos operacionalmente disponíveis e reconciliar no mesmo checkpoint:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output "$rodada/uniao"
.\.venv\Scripts\python.exe -m scripts.reconcile_symbol_benchmark --predictions "$rodada/uniao/predictions.json" --reference "$rodada/uniao/reference.json" --exclude-method structural-raster-graph --exclude-method structural-vector-graph --output "$rodada/composicao"
```

Registrar métodos indisponíveis como tal, não como zero detecção. Comparar
baseline, isolados, união, composição e ablação com os mesmos denominadores,
inclusive negativos críticos. A interseção é só controle; silêncio de outro
método não veta exclusivo.

Para fechar o **retorno de cobertura** da rodada, executar depois dos gates acima:

```powershell
.\.venv\Scripts\python.exe -m scripts.curation_coverage_e16 plan --matrix "$rodada/matriz-antes.csv" --demand "$rodada/demanda.json" --output "$rodada/plano-lacunas.json"
.\.venv\Scripts\python.exe -m scripts.coverage_matrix_e16 --baseline-matrix "$rodada/matriz-antes.csv" --e07-report "$rodada/benchmark/report.json" --output "$rodada/matriz-depois.csv" --summary "$rodada/matriz-depois-resumo.json"
.\.venv\Scripts\python.exe -m scripts.curation_coverage_e16 compare --before "$rodada/matriz-antes.csv" --after "$rodada/matriz-depois.csv" --output "$rodada/delta-e16.json"
```

`benchmark/report.json` é a saída **dessa rodada** de
`scripts.benchmark_packages_e07`, não a de E07 histórica. O gerador da matriz
recusa inferência E07 incompleta, FP/FN/duplicatas autorais ou hash de pacote
divergente. A evidência E05/E06 é herdada da matriz anterior somente quando
seus detectores/fixtures não mudaram. Se forem alterados, executar seus
benchmarks e passar relatórios frescos em `--e05-report`/`--e06-report`;
a matriz anterior permanece como checkpoint se faltar essa evidência.
Nenhum relatório de etapa guardado em `tmp/` é dependência da primeira rodada.
Depois de todos os gates e da revisão
visual aprovados, copiar `matriz-depois.csv` e `matriz-depois-resumo.json` para
`docs/data/matriz-simbologia-curadoria-atual.csv` e
`docs/data/matriz-simbologia-curadoria-atual-resumo.json`; registrar a rodada,
os SHA e o delta sem caminhos privados na seção **Estado do fluxo** abaixo.
Essas cópias
preservam a cobertura verificada para a próxima rodada, sem editar a E16
histórica. O plano não substitui a revisão independente, e o delta não mede
FP/FN de ocorrências nem ganho da união.

O comando `benchmark_symbols examples` só produz inferência; C ainda precisa
reconciliar visualmente as páginas e predições afetadas. Validar o esquema Draft 2020-12 com
implementação independente disponível, em instalação isolada se necessário,
e registrar comando/versão. Se a fonte normativa F02 estiver disponível,
repetir a auditoria com `--source-pdf` apontando para ela e conferir hash,
páginas e localizadores; ausência da fonte impede validar novos IDs que dela
dependem. Se o código ou os comandos mudarem, descobrir os
novos comandos no repositório e registrar a substituição; não fingir que um
gate ausente passou. Fazer `git diff --check` e conferir hashes/totalizadores.

**Aceite da execução:** todos os PDFs/páginas descobertos estão no manifesto;
novos/modificados foram realmente vistos; predições e comparação pertencem ao
mesmo checkpoint; positivos, negativos e alternativas das mudanças passaram;
fontes intactas; V-Q/V-G, regressões de contrato, jobs, histórico e exportações
passaram. `delta-e16.json`
publica IDs ganhos/perdidos e denominadores; o relatório da rodada confronta
também TP/FP/FN, exclusivos e custo da união com o checkpoint anterior, sem
inferir desempenho real quando falta gabarito exaustivo. Sem exemplos novos,
registrar execução sem mudança, não inventar ganho. Uma execução pode terminar
com pendências explícitas; elas não contam como reconhecimento nem impedem a
rodada seguinte. Não criar commit,
publicar ou implantar sem autorização explícita.

## Prompt one-shot para usar após adicionar PDFs

Cole o bloco inteiro em uma sessão nova, aberta na raiz do Zeny Project Handler.
Os arquivos podem estar em qualquer subpasta de `examples/`; o prompt
descobre os caminhos, sem precisar editar nomes.

```text
Execute uma rodada completa e independente de curadoria incremental de simbologia conforme docs/fluxo-curadoria-incremental-simbologia.md no Zeny Project Handler, aberto na raiz. Os PDFs que eu quero considerar já estão em examples/; descubra todos recursivamente, inclusive .PDF, e compare os hashes com a última rodada local se ela existir.

Leia primeiro as instruções aplicáveis do repositório, docs/adr/0005-exemplos-locais-dinamicos.md, este fluxo, o inventário JSON e os esquemas, os pacotes, as matrizes históricas/de curadoria, os scripts/testes de benchmark e git status/diff. Preserve todas as alterações preexistentes. Execute C01–C04 em uma única tarefa. Registre manifesto de todos os arquivos/páginas, falhas, hashes e um diretório de evidências local em tmp/curadoria-simbologia/. Copie a última matriz validada para a rodada e gere o plano inicial das lacunas por ID.

Delegue frentes delimitadas a subagentes, se disponíveis: A implementa pacotes/runner por lotes de famílias e possui somente os arquivos que você lhe atribuir; B cria fixtures sintéticas e testes positivos/negativos em arquivos separados; C renderiza e realmente vê todas as páginas novas/modificadas, base e anotações, congelando observações antes de ver predições e depois compara os resultados. Você é o coordenador: define contratos, um dono por arquivo, integra inventário/registro central serialmente, verifica retornos e executa gates finais. Se subagentes não estiverem disponíveis, registre isso e não simule revisão independente.

Trate cada PDF real como desenvolvimento local, nunca como treino automático ou norma. A identificação sugerida por IA sem confirmação é provisória. Para desenhos iguais de IDs diferentes, produza uma observação com alternativas explícitas e contexto comprovável; não force ID exato, não duplique ocorrências, não conte desconhecido como reconhecimento. Legenda, norte e desenhos informativos, inclusive §33, não viram ativos. Não passe ROI/rótulo do revisor ao detector; preserve candidatos exclusivos e não trate concordância como probabilidade. Se faltar rótulo ou fonte para um caso, documente a pendência e avance nos demais.

Congele a inferência antes da comparação visual; confronte FP/FN, duplicatas, exclusivos e ambiguidades por PDF/página/família. Depois da revisão, registre demanda local por IDs do inventário e priorize seu cruzamento com o plano de lacunas; achados de outros métodos voltam ao módulo responsável. Incorpore apenas achados sustentados por fonte, positivo e negativos independentes em pacotes versionados e fixtures sintéticas autorais, preservando PDFs e relatórios privados fora do Git. Rode auditoria de inventário/esquema, V-N, V-Q, V-G, benchmarks sintéticos isolados e de união, e inferência de todos os PDFs/páginas conforme os comandos atuais deste fluxo; valide visualmente as saídas afetadas e UI/exportações, registre comandos/resultados e não declare gate não executado como aprovado. Gere matriz local com o relatório de pacotes fresco e compare antes/depois, incluindo regressões e denominadores; não sobrescreva a matriz histórica nem declare aceite integrado sem nova reserva independente. Não reutilize as reservas abertas como teste cego ou dado de ajuste.

Entregue no fim um resumo conciso com arquivos alterados, IDs/famílias acrescentados, versões/hashes, cobertura de PDFs/páginas, TP/FP/FN, exclusivos e ambiguidades com denominadores, delta E16 de IDs ganhos/perdidos, gates executados, pendências e próximo dado necessário. Se a rodada não produzir ganho validado, diga isso expressamente. Não crie commit, publique ou implante sem autorização explícita.
```

## Estado do fluxo

Contrato único independente consolidado em 25/09/2026. Nenhuma rodada C01–C04
foi executada por esta edição. O ponto de partida conhecido é 21 variantes
`enabled` e 344 `pending` em 27 pacotes, com 427 IDs no inventário; conferir
novamente código, matrizes e `examples/` antes de cada execução. Os handoffs de
roadmaps anteriores foram retirados de `docs/`; os dados preservados, o código,
os testes e este fluxo são os contratos vivos.

Na consolidação foram removidos **34 Markdown históricos** da raiz de `docs/`:
handoffs E01–E16, o roadmap de simbologia, o inventário narrativo E01, o
inventário de paridade de outra trilha e a validação de release antiga. Os
documentos de produto, API, operação e ADRs permaneceram. Todos os links
Markdown remanescentes em `README.md`, `examples/README.md` e `docs/` foram
conferidos: **0 quebrados em 24 arquivos**. O recálculo da matriz a partir de
seu próprio checkpoint e do relatório de pacotes compatível reproduziu
**427 IDs, 297 lacunas e delta exato zero**; 45 testes focados, Ruff check,
Ruff format e mypy passaram. Essa verificação prepara as próximas rodadas;
não executou V-P, a suíte integral ou uma nova reserva, nem concede aceite
integrado.
