# Curadoria incremental de leitura e simbologia — rodadas em ondas

Este é o contrato operacional para melhorar a leitura, a interpretação e os pacotes de símbolos,
medindo a cobertura integrada. O usuário adiciona PDFs localmente em `examples/` e inicia uma
rodada no Claude Code com a skill de projeto `/curadoria-simbologia` (ver "Como executar"). O
procedimento passo a passo está na
[skill](../.claude/skills/curadoria-simbologia/SKILL.md); os papéis visuais, de investigação e
de correção estão nos [agentes de projeto](../.claude/agents/); os passos mecânicos são CLIs
testados em `scripts/curation_*.py`. Este documento fixa o que toda rodada precisa respeitar.

Uma rodada **não treina o assistente de forma permanente**. Conhecimento duradouro é uma
mudança revisável nos algoritmos, nos pacotes, no inventário quando necessário e nas
fixtures/testes versionados. O chat, os PDFs e os arquivos da rodada, ignorados pelo Git, não
são uma base de conhecimento persistente.

O fluxo usa a capacidade visual do **modelo ativo da sessão do Claude Code**: subagentes leem
as páginas renderizadas em PNG e criam uma referência visual de desenvolvimento por ponto. Essa
referência é congelada, com hash registrado, antes de qualquer comparação com os algoritmos; o
leitor nunca recebe as saídas deles. Scripts comparam, contam e agrupam as divergências; os
agentes investigam as causas e incorporam correções testadas. A referência não se torna
gabarito infalível por ter sido produzida por um modelo; sua evidência, sua cobertura e suas
incertezas ficam registradas.

Cada rodada parte das lacunas publicadas na matriz de cobertura vigente, dá prioridade aos
casos observados nos PDFs e termina com uma nova matriz local e um delta de cobertura.
Melhorias de OCR, leitura de anotações, relações, contagem ou redução de FP também são
resultados, mesmo sem ganho de IDs na matriz. Uma rodada pode reduzir uma lacuna, revelar
regressão ou apenas registrar que faltou evidência; não há garantia de ganho a cada execução.
O resultado da rodada é ganho validado, regressão ou pendência documentada, com denominadores.

## Ponto de partida e critério de melhoria

O inventário congelado em [`data/inventario-simbologia-v1.json`](data/inventario-simbologia-v1.json),
validado por [`schemas/inventario-simbologia.schema.json`](schemas/inventario-simbologia.schema.json),
define os IDs e as famílias que formam o denominador. Cada rodada parte de
`docs/data/matriz-simbologia-curadoria-atual.csv` e do resumo dela; enquanto essa matriz não
existir, parte do checkpoint histórico
[`data/matriz-simbologia-e16.csv`](data/matriz-simbologia-e16.csv) e do seu
[`resumo`](data/matriz-simbologia-e16-resumo.json). A rodada **lê os números** da matriz de
partida — IDs por status, variantes `enabled` e `pending` por pacote, destinos informativos — e
os registra no relatório local; este documento não fixa contagens. Nenhum `pending` é
reconhecimento. Esses números são o começo, não metas reduzidas nem estimativas de campo. Se o
inventário crescer, a rodada recalcula o denominador e justifica cada ID novo.

Um localizador `SRC-LOCAL.url` do inventário congelado aponta para documentação histórica
retirada; ele é metadado de origem e não instrui este fluxo. O arquivo permanece byte a byte
igual para conservar os hashes da referência.

As reservas independentes já abertas estão consumidas: não servem para ajuste, calibração nem
teste cego repetido. No desenvolvimento e nos exemplos, uma rodada demonstra o delta de
cobertura, TP/FP/FN sintéticos, TP_IA/FP_IA/FN_IA de desenvolvimento, exclusivos,
ambiguidades, custos e regressões; isso não equivale a homologação de campo nem a aceite
integrado.

Para um **novo aceite integrado**, após melhorias em desenvolvimento e calibração
independente, congelar código/configuração e uma nova reserva independente de desenho, validar
o esquema e as famílias do inventário antes de lacrá-la e medir uma única vez sem ajuste sobre a
referência. As metas herdadas são recall de candidatos e precisão final **≥95% por família
avaliável**, zero FP nos negativos críticos, zero fusão entre páginas e zero promoção com
conflito técnico. A composição preserva acertos exclusivos válidos, supera o baseline no mesmo
conjunto e tem contribuições exclusivas de pelo menos duas famílias algorítmicas distintas.
Promoção automática exige precisão observada ≥99% em amostra independente suficiente;
subconjunto vazio não satisfaz a meta. Executar V-P integral, V-Q, V-G, benchmark reservado e
inspeção manual da UI/exportações. Se faltar teste, calibração ou meta, publicar a pendência,
sem declarar aceite. As rodadas de curadoria podem continuar enquanto isso.

## Contrato e limites

- `examples/` é uma bancada local dinâmica conforme
  [ADR 0005](adr/0005-exemplos-locais-dinamicos.md). PDFs reais, PNG renderizados,
  referências, comparações e relatórios com caminhos/recortes ficam fora do Git, em
  `tmp/curadoria-simbologia/`. A análise visual pelo modelo ativo da sessão é parte deste fluxo
  autorizado: renderizar páginas e tiles e apresentar seus pixels ao modelo com a ferramenta
  Read. Ler o binário ou extrair texto do PDF não apresenta as páginas ao modelo e não conta
  como revisão. Não enviar os documentos a APIs ou serviços adicionais sem autorização nem
  copiar PDFs, recortes ou PNG privados para fixtures, `tests/` ou `docs/`. O gate portátil
  continua sintético.
- Adicionar um PDF **não ensina automaticamente** o detector. Primeiro é preciso ver as
  páginas, identificar ocorrências e negativos, conferir a fonte/legenda e testar uma regra ou
  template. A referência feita por IA pode orientar desenvolvimento quando sustentada por
  evidência, mas não equivale a confirmação humana, norma ou avaliação independente de campo.
  Falta de confirmação humana não bloqueia a investigação dos outros casos do PDF.
- Uma forma que admite vários IDs gera **uma observação física com alternativas explícitas**.
  O ID exato só pode ser emitido quando texto, cor, camada, legenda ou contexto verificável o
  distingue. Ambiguidade não vira vários ativos. Alternativas só contam como reconhecimento do
  grupo visual se o pacote e seus positivos/negativos estiverem verificados; sem isso, o grupo
  continua pendente. Desconhecido continua desconhecido e não conta como variante reconhecida.
- A legenda local limita o significado ao documento/revisão. Ela é referência, não ocorrência
  operacional. Símbolos informativos, norte e desenhos §33 continuam informativos, mesmo quando
  parecem equipamento. PDF de projeto revela casos e estilos, mas não cria norma ou obrigação de
  conformidade.
- Cada inferência usa uma versão congelada dos pacotes e do código, registrada no checkpoint de
  código da rodada. A referência visual e as regiões do revisor ficam fora da entrada do
  detector: ele recebe só o PDF e a configuração normal, nunca ROI, rótulo, contagem ou lista
  de achados. Silêncio de outro método não veta um candidato exclusivo; concordância não é
  probabilidade.
- A visão do modelo pode falhar em texto pequeno, traços, contagem e localização precisa.
  Renderizar em resolução legível e ler por tiles com sobreposição; não confiar apenas na visão
  geral ou em OCR. Registrar ilegibilidade e alternativas sem inventar precisão ou confiança
  probabilística. Coordenadas estimadas pelo modelo são localizadores de revisão, não medidas
  de engenharia.
- Os subagentes herdam o modelo ativo da sessão; nenhum papel troca para outro modelo por
  economia. O identificador do modelo exposto pela sessão é registrado em `revisor.modelo` e no
  relatório; se a sessão não expuser nenhum, registrar `indisponivel`, sem inventar nome ou
  versão.
- Um PDF já visto passa a ser desenvolvimento. Uma reserva futura precisa de seleção, esquema
  validado e congelamento próprios, sem receber regras ou rótulos do desenvolvimento.
- A matriz E16 é o **ponto de partida histórico** só enquanto não houver matriz de curadoria
  atual. `docs/data/matriz-simbologia-curadoria-atual.csv` e o resumo dela são substituídos
  somente depois dos gates aprovados de uma rodada; a matriz e o resumo E16 históricos
  permanecem preservados. O delta de IDs não comprova recall real, ganho da união nem aceite
  reservado; medir cada um em seu conjunto apropriado.
- Método indisponível, com falha ou sem registro de execução conta como **falha**, nunca como
  zero detecção.
- Nenhuma rodada faz commit, push, deploy ou publicação externa sem autorização explícita. O
  usuário revisa o diff da árvore de trabalho e decide.

## Desenho do fluxo

**Leitura × correção.** O que é leitura (por PDF, somente leitura sobre o código) roda em
paralelo; o que é correção (por módulo, edita código) roda em série. Leitura visual, inferência
e comparação de PDFs diferentes não editam os mesmos arquivos; correções sim.

**Rodada → ondas → fases.** Uma rodada descobre o corpus inteiro de `examples/` e o divide em
ondas de N PDFs (N = 3 por padrão, entre 3 e 5). Em cada onda:

1. **Preparar** (CLIs em paralelo): renderização em visão geral e tiles com sobreposição, com
   triagem de tiles em branco, e inferência congelada de todos os métodos em processos
   paralelos.
2. **Ler** (subagentes em paralelo): um leitor visual por PDF lê os tiles e grava a referência
   regional, validada e congelada por CLI.
3. **Medir** (CLI): comparador regional determinístico calcula TP_IA/FP_IA/FN_IA por método,
   família e união, com denominadores, só dentro das regiões revisadas.
4. **Auditar** (subagentes em paralelo): um auditor visual independente relê uma amostra
   estratificada de tiles; a concordância decide se a referência é usável.
5. **Agregar** (CLI): as divergências da onda viram um backlog por causa, priorizado por número
   de PDFs afetados, com o módulo dono de cada grupo e pistas de correção disjuntas.
6. **Investigar** (subagentes em paralelo): um investigador por grupo priorizado confirma ou
   refuta a causa, sem editar.
7. **Corrigir e integrar** (em série): uma pista por vez, na árvore principal, com fixture
   sintética positiva/negativa antes do ajuste, integração conferida, testes focados e
   verificador independente.
8. **Reinferir e fechar a onda:** só os PDFs afetados pelas pistas integradas são reinferidos e
   recomparados contra a mesma referência congelada.

No fim da rodada: código congelado, gates completos uma vez, reinferência de regressão de todo o
corpus, fechamento dos PDFs e matriz de cobertura.

**Por que a correção não usa worktree.** O worktree de um subagente parte de um commit: não
traz os arquivos não rastreados nem as mudanças locais, não tem a `.venv` (ignorada pelo Git), e
a instalação editável continua importando o `src/` da árvore principal. Testes rodados nele
mediriam o código errado. Por isso as pistas rodam em série na árvore principal, e o paralelismo
da onda fica em preparar, ler, auditar e investigar.

**Layout da rodada** (tudo sob `tmp/curadoria-simbologia/RODADA/`, fora do Git):

- `rodada.json` — corpus (caminho relativo, SHA-256, bytes, páginas), duplicatas, ondas, N,
  checkpoint de código e rodada anterior; `relatorio.md` — relatório local da rodada.
- `matriz-antes.csv`, `plano-lacunas.json`, `demanda.json`, `inicial/`, `fechamento/`,
  `matriz-depois.csv`, `matriz-depois-resumo.json` e `delta-cobertura.json`.
- `pdfs/ORDEM-HASH12/` por PDF: `checkpoint.json` (fase, marcos e histórico), `render/` (visões,
  tiles e `indice-tiles.json`), `leitura/` (rascunho do leitor), `referencia/`
  (`referencia-vNNN.json`, só gravadas pelo CLI), `inferencia-vNNN/`, `comparacao-vNNN.json`,
  `auditoria/` (amostras), `leitura-auditoria/` (leituras do auditor) e `concordancia-vNNN.json`.
- `ondas/K/backlog.json` e `backlog.md`; `ondas/K/pistas/pista-NN/antes/` (base de reversão
  de cada pista).

Todas as versões são preservadas: nenhum CLI sobrescreve uma versão anterior para melhorar o
resultado. A versão vigente de inferência, referência, comparação e concordância de um PDF é a
registrada no marco do checkpoint, nunca "a de maior número".

**Fases do checkpoint** (`curation_round`): `preparado`, `renderizado`, `inferido`,
`referencia_congelada`, `comparado`, `auditado`, `em_correcao`, `fechado` e
`encerrado_com_pendencias`. `comparado` exige `inferido` e `referencia_congelada`; `fechado`
exige `comparado` e `auditado` vigentes. Nova inferência ou correção invalida `comparado`; uma
nova versão da referência invalida `comparado` e `auditado`. Depois dela, a concordância pode
ser recalculada com a mesma leitura do auditor contra a versão vigente, exceto quando uma
concordância anterior do PDF decidiu `encerrar_com_pendencia`: essa decisão é terminal para a
auditoria e o CLI recusa recalcular. `fechado` e
`encerrado_com_pendencias` são terminais, então os PDFs só passam a `fechado` no fechamento da
rodada, depois da reinferência de regressão.

## Como executar

Numa sessão do Claude Code aberta na raiz do repositório, com a `.venv` criada por `setup.bat`:

```text
/curadoria-simbologia
```

Opcionalmente informe N (PDFs por onda, de 3 a 5) ou peça releitura total (sem reuso de
referências). A skill conduz a rodada inteira a partir da sessão principal, retoma pelo
`rodada.json` depois de compactação ou interrupção e termina com o caminho do relatório local
e `git status --short`. `.claude/settings.json` libera, regra a regra, os CLIs `curation_*`,
`curation_coverage_e16`, `coverage_matrix_e16`, `benchmark_symbols`, `benchmark_packages_e07`,
`benchmark_transformers_e05`, `benchmark_guys_e06`, `benchmark_review_e14`,
`reconcile_symbol_benchmark`, pytest, Ruff e mypy. Pedem aprovação: `audit_symbol_packages`,
`IniciarTestes.bat`, `git status`/`git diff`, cópias de arquivo e a validação independente
dos esquemas.

**Prompt de reserva** para uma sessão em que a skill não aparece (por exemplo, criada ou
alterada na própria sessão):

```text
Conduza uma rodada de curadoria de simbologia sobre os PDFs de examples/ neste repositório. Leia CLAUDE.md, docs/fluxo-curadoria-incremental-simbologia.md e .claude/skills/curadoria-simbologia/SKILL.md, e siga a skill diretamente como sessão orquestradora, com ondas de 3 PDFs. Se os agentes curadoria-* não estiverem registrados nesta sessão, use o modo de reserva descrito na skill: subagentes general-purpose cujo prompt é o corpo inteiro de .claude/agents/NOME.md, seguido do bloco da tarefa e da lista de ferramentas do campo tools. Se houver rodada anterior em tmp/curadoria-simbologia/, use-a como --anterior; se houver rodada inacabada, retome-a pelo rodada.json em vez de criar outra. Preserve mudanças preexistentes, mantenha PDFs, imagens e relatórios só em tmp/curadoria-simbologia/ e não faça commit, push nem deploy. No fim, responda com o resumo da rodada, o caminho de RODADA/relatorio.md e git status --short.
```

Os agentes `curadoria-*` registrados numa sessão usam a definição carregada no início dela. Se
os arquivos de `.claude/agents/` forem alterados durante a rodada, os disparos seguintes usam o
modo de reserva (`general-purpose` com o corpo atual do arquivo), e as regras novas são passadas
por mensagem aos agentes já em execução. O ambiente limita os subagentes simultâneos: quando um
disparo é recusado por esse limite, a orquestradora espera uma vaga e não dispara de novo o que
já está em execução.

Sem subagentes disponíveis, a sessão executa as funções em sequência e registra a limitação no
relatório: lê e congela a referência antes de abrir inferências ou comparações, e não chama de
independente uma auditoria feita pelo mesmo contexto que já viu a referência ou as predições.

Os comandos abaixo são os que a skill executa, no Git Bash, com valores literais (`RODADA`,
`ID`, `K`, `N`, `vNNN`). No PowerShell, troque o prefixo por `.\.venv\Scripts\python.exe`.

## Preparação da rodada

Ler `CLAUDE.md`, este fluxo, ADR 0005, o inventário e os esquemas, e rodar `git status`;
preservar alterações preexistentes. Verificar o interpretador e a inicialização dos CLIs antes
dos gates; se a `.venv` estiver indisponível, seguir as instruções de ambiente do repositório ou
registrar o impedimento. Conferir argumentos no código não aprova uma execução.

```bash
.venv/Scripts/python.exe -m scripts.curation_round init --rodada RODADA --raiz examples --concorrencia N --anterior RODADA_ANTERIOR
.venv/Scripts/python.exe -m scripts.curation_round status --rodada RODADA --json
```

- `init` descobre recursivamente todos os PDFs de `examples/` (inclusive `.PDF`), ordena pelo
  caminho relativo sem distinguir maiúsculas/minúsculas e registra caminho relativo, SHA-256,
  tamanho e páginas, mais o checkpoint de código (árvore de trabalho e digest dos pacotes).
  Arquivo ilegível fica no manifesto com o erro. Sem rodada anterior, omitir `--anterior`.
- Duplicatas por hash mantêm todos os caminhos, recebem checkpoints próprios e ficam
  declaradas nos denominadores.
- Frente à rodada anterior, cada PDF é novo, modificado ou inalterado (caminho relativo +
  SHA-256). Por padrão, um PDF inalterado reutiliza a referência congelada anterior, cuja
  cópia só é aceita com o hash conferido; a referência reutilizada passa pela auditoria
  amostral como as demais. `--sem-reuso` força a releitura de todos. Arquivo ausente na rodada
  atual não é presumido validado.
- Rodada anterior com relatório: as "Pendências acionáveis" dela (ver §8) são lidas agora; os
  grupos `grp-...` têm id estável e, ao reaparecerem num backlog, são investigados primeiro.

Copiar a matriz de partida (`docs/data/matriz-simbologia-curadoria-atual.csv` ou, se ela não
existir, `docs/data/matriz-simbologia-e16.csv`) para `RODADA/matriz-antes.csv`, registrar qual
arquivo foi copiado e seu SHA-256, e gerar a fila de lacunas por ID, com dono e denominador:

```bash
.venv/Scripts/python.exe -m scripts.curation_coverage_e16 plan --matrix RODADA/matriz-antes.csv --output RODADA/plano-lacunas.json
```

A fila prioriza investigação; não é rótulo e nunca chega ao leitor visual.

Antes da primeira correção da rodada, guardar o checkpoint sintético inicial dos métodos
isolados e da união/composição, para comparar com o fechamento nos mesmos casos e denominadores:

```bash
.venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output RODADA/inicial/baseline
.venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output RODADA/inicial/uniao
.venv/Scripts/python.exe -m scripts.reconcile_symbol_benchmark --predictions RODADA/inicial/uniao/predictions.json --reference RODADA/inicial/uniao/reference.json --exclude-method structural-raster-graph --exclude-method structural-vector-graph --output RODADA/inicial/composicao
```

Fixtures acrescentadas durante a rodada recebem avaliação separada. Se o conjunto mudar,
mostrar a interseção comparável e o conjunto ampliado, sem atribuir uma mudança de denominador a
ganho do algoritmo.

## Ciclo de cada onda

### 1. Preparar

```bash
.venv/Scripts/python.exe -m scripts.curation_render --rodada RODADA --onda K --jobs N
.venv/Scripts/python.exe -m scripts.curation_infer --rodada RODADA --onda K --jobs N --pipeline
```

- `curation_render` grava em `render/` a visão geral e a grade de tiles de cada página, nas
  camadas base e anotada, com sobreposição, bbox normalizada na página exibida (convenção do
  protocolo `symbols-e02-v1`) e `indice-tiles.json` com hash de cada PNG. Tiles sem conteúdo
  pelo limiar de ocupação viram `descartado_branco`: o descarte é registrado no índice, os PNG
  continuam disponíveis e a auditoria também os amostra. Tamanho do tile, sobreposição, DPI e
  limiar são parâmetros do CLI. O padrão de `--dpi-detalhe` é 400: a 200 dpi os símbolos de
  rede de folhas A4/A3 ficam com poucas dezenas de pixels e ilegíveis na leitura visual;
  detalhe ainda menor pede DPI maior.
- `curation_infer` roda os métodos sobre um PDF por vez, sem cópia para pasta isolada, em até N
  processos, numa nova `inferencia-vNNN/` com comandos, checkpoint de código, durações e
  status. **Toda inferência da rodada usa `--pipeline`** — a inicial, as reinferências da onda
  e a de regressão do fechamento: além dos símbolos, ela roda `benchmark_network_pdf` no mesmo
  PDF e grava em `pipeline.json` os snapshots da leitura/interpretação nas variantes nativa e
  OCR, com o runtime padrão `tmp/benchmark-runtime` (inspecionado pelo próprio CLI antes da
  execução). Os mesmos `--metodos` e as mesmas opções de pipeline valem em todas as
  inferências da rodada e ficam registrados.
- OCR indisponível: sem OCR português pronto, `benchmark_network_pdf` falha (o `pipeline.log`
  diz "OCR português obrigatório"). Nesse caso a rodada inteira passa a
  `--pipeline --native-only`, inclusive refazendo as inferências já feitas, e o OCR fica
  registrado como pendência; uma execução `--native-only` não aprova OCR. Não instalar nem
  baixar modelos implicitamente.
- **Lacunas de medição** (registradas como pendência no relatório, não prometidas):
  `curation_infer` não aciona o OCR complementar (`--complementary-ocr`) nem o OCR de legenda
  (`--legend-ocr`), então eles não são medidos na rodada; `curation_compare` mede só símbolos —
  textos, atributos, estados, quantidades/unidades e relações registrados na referência não têm
  métrica automática. O investigador confere esses itens no `pipeline.json` quando o grupo os
  envolve, e as melhorias de leitura entram no relatório à parte do delta de IDs, com evidência
  antes/depois.
- **Sucesso parcial** (`sucesso_parcial`): quando só métodos falham — o runner grava
  predições e manifesto válidos, toda falha do manifesto tem `method_id` e aparece também como
  falha em `executions` das predições, e ao menos um método executou —, o PDF avança para
  `inferido` com `falhas_metodos` registradas. Os demais métodos são medidos; o método que
  falhou é medido como falha, nunca como zero. Qualquer outra saída com erro é falha do PDF.
- PDF com falha: ler o log, repetir com `--pdf ID` e, persistindo, registrar como pendência
  daquele PDF. Falta de memória: repetir com `--jobs` menor e registrar no relatório.
- Se o harness não expuser um resultado necessário, instrumentar o módulo responsável com
  snapshot/telemetria e teste, em vez de afirmar que o resultado foi verificado.

### 2. Ler — referência visual regional

Um subagente `curadoria-leitor-visual` por PDF sem referência recebe **apenas** a rodada, o ID,
o SHA-256, o caminho relativo, o nome do modelo, o arquivo de saída
`RODADA/pdfs/ID/leitura/referencia.json` e as regras gerais de leitura abaixo (critério de
estado, completude, camada anotada e extensão da bbox), que valem também para o auditor e não
trazem nada do PDF. Ele lê os PNG de `render/` e o índice, o esquema e o
inventário; nunca recebe nem abre inferências, comparações, auditorias, checkpoints, backlog,
a fila de lacunas ou contagens esperadas. O Claude Code restringe ferramentas, não caminhos:
a cegueira depende de a orquestradora nunca passar esses caminhos, das proibições do agente e
do registro de exposição feito pelo CLI.

Regras da leitura (formato `curadoria-referencia-visual-v1`,
[`schemas/referencia-visual-curadoria.schema.json`](schemas/referencia-visual-curadoria.schema.json)):

- Abrir a visão geral e depois os tiles `a_revisar`, em **duas passagens**: primeiro levantar
  pontos, desenhos, textos, legenda e notas; depois conferir elementos de cada ponto, relações,
  quantidades, unidades e áreas sem ativos, inspecionando desenhos parecidos para registrar
  negativos além dos positivos.
- `escopo: regional` declara os `tiles_revisados` e as `regioes_ilegiveis`; `completo` só
  quando todos os tiles `a_revisar` foram revisados ou cobertos por regiões ilegíveis. Tile não
  aberto não é declarado. Uma lista esparsa de âncoras não é um censo.
- Cada observação traz página, camada, bbox e tile de evidência, família e `class_id` do
  inventário, `id_inventario` só quando a evidência distingue a variante, ou `alternativas`
  com motivo; papel `operacional`, `informativo`, `desconhecido` ou `negativo`; texto original
  separado da interpretação; quantidades e relações só quando visíveis; estado
  `sustentado_por_evidencia`, `provisorio` ou `ilegivel`, com motivo fora do primeiro; fonte
  do significado (legenda, nota ou norma com localizador). Elemento fora do inventário usa
  `local-unknown`, sem ID nem alternativas. Revisor com origem `revisao_ia` e o modelo
  informado pela sessão; confirmação humana, se houver, fica separada.
- **Critério de estado:** `sustentado_por_evidencia` quando a família/classe é determinada pela
  evidência; dúvida só da variante exata vai em `alternativas` e não torna a observação
  provisória; `provisorio` só quando a presença do elemento ou a sua classe dependem de
  suposição.
- **Completude:** nos tiles revisados, todo elemento de rede visível é registrado; o que fica de
  fora vira FP para uma detecção correta.
- **Camada anotada:** o desenho comum às duas camadas fica só na `base`; na camada `annotation`
  entra apenas o que existe só na anotação.
- **Extensão da bbox:** em aterramento e para-raios, a bbox cobre o pictograma (envolvente e
  barras), sem a linha de ligação até o poste; em transformador, cobre o símbolo, sem o rótulo
  de texto. Em discos e marcas pequenas (1 a 5 pt), a bbox cobre só a marca (preenchimento e contorno), justa, sem rótulo, linha, círculo de identificação nem moldura vizinha: um pixel de folga a 400 dpi já derruba o IoU abaixo de 0,5. Em estai de âncora, a bbox vai do centro do poste até o fim do símbolo (haste e círculo ou forquilha incluídos), uma por estai.
- Não preencher atributo ilegível pelo que se esperaria no projeto; ausência não é zero quando
  a região não foi suficientemente vista. Não converter confiança verbal em probabilidade.
- Uma ocorrência física tem uma identidade: não duplicar entre base e anotação nem entre tiles
  sobrepostos, e não fundir pontos ou páginas por semelhança sem prova. Legenda, norte e
  desenhos informativos entram com seu papel e fora da contagem operacional.

Validar e congelar; a orquestradora não edita a leitura antes do congelamento:

```bash
.venv/Scripts/python.exe -m scripts.curation_reference validar --rodada RODADA --pdf ID --arquivo RODADA/pdfs/ID/leitura/referencia.json
.venv/Scripts/python.exe -m scripts.curation_reference congelar --rodada RODADA --pdf ID --arquivo RODADA/pdfs/ID/leitura/referencia.json
```

`congelar` grava `referencia/referencia-v001.json` com o SHA-256 no checkpoint, exposição a
predições falsa e a lista das inferências já existentes (transparência). A referência congelada
é referência de desenvolvimento gerada por IA, com cobertura e incertezas declaradas: um achado
sustentado pode orientar testes e correções sem esperar confirmação humana do documento
inteiro, e casos provisórios ficam separados. Não afirmar que o modelo descobriu a verdade de
campo ou garantiu censo perfeito.

### 3. Medir — comparador regional

```bash
.venv/Scripts/python.exe -m scripts.curation_compare --rodada RODADA --onda K
```

- Recusa referência não congelada, versão não registrada, SHA-256 divergente de referência,
  inferência, PDF ou índice de tiles; recusa indica entrada faltando ou adulterada e deve ser
  corrigida na causa, não contornada.
- Casamento pelo protocolo `symbols-e02-v1` (mesmo `geometry_match` do avaliador, que não muda).
  `TP_IA`, `FP_IA` e `FN_IA` são **relativos à referência de desenvolvimento sustentada por
  evidência**, por método, família e união, separando classe/grupo visual de ID exato.
  Observações provisórias, de papel desconhecido, ilegíveis ou locais ficam fora dos
  denominadores e são contadas à parte; divergência contra rótulo provisório não justifica
  correção sozinha. Um ID ambíguo nunca é TP exato; desconhecido não é reconhecimento;
  controles informativos e negativos contam FP de papel.
- **Classes suportadas** (esquema `curadoria-comparacao-v2`): o FN_IA de cada método conta só
  nas `supported_classes` que ele declara; o FP_IA do método conta todas as predições dele.
  Método sem `supported_classes` é medido contra todas as ocorrências e gera alerta. A união
  continua medida sobre todas as ocorrências avaliáveis; o FN da união cuja classe nenhum
  método cobre vira divergência `sem_metodo`: lacuna de cobertura, não defeito de método.
- **Convenção de bbox do detector:** o detector vetorial legado reporta aterramento e
  para-raios pela bbox do pictograma, a mesma convenção da leitura; a extensão da haste de
  ligação fica no atributo `simbolo_limites_suporte`, fora do casamento.
- **Escopo regional:** predição e observação entram quando o centro da bbox cai num tile
  revisado da mesma página e camada, fora das regiões ilegíveis. Esse critério tem efeito de
  borda: um objeto que atravessa o limite de um tile revisado entra ou sai inteiro pelo centro.
  Em escopo regional não existe revocação global; publicar só a revocação regional e os
  denominadores (ocorrências avaliáveis, candidatos, negativos, tiles revisados, descartados e
  não revisados, regiões ilegíveis, duplicatas, exclusivos, ambiguidades).
- Método com falha ou sem registro de execução é falha, não zero; os números desse método
  ficam marcados e não entram como desempenho.
- Cada divergência é rastreável (id estável, tipo, método, observação, predição, tile de
  evidência) e a soma por método reproduz FP_IA/FN_IA. Essas métricas não são
  precisão/recall de campo nem aceite independente.

### 4. Auditar — dupla leitura amostral

```bash
.venv/Scripts/python.exe -m scripts.curation_audit amostrar --rodada RODADA --onda K
.venv/Scripts/python.exe -m scripts.curation_audit concordancia --rodada RODADA --pdf ID --auditoria RODADA/pdfs/ID/leitura-auditoria/amostra-vNNN.json
```

- A amostra é estratificada por página e faixa de ocupação, inclui tiles descartados, é
  determinística pela semente e não depende da referência (padrão: 15% dos tiles, com mínimo).
  Ficam fora da população os tiles anotados com os mesmos bytes do gêmeo da base (mesma
  página, linha e coluna), além da camada anotada de página igual à base.
- Um `curadoria-auditor-visual` **novo** por PDF recebe só a ficha da amostra (id, arquivo,
  página, camada, bbox e dimensões de cada tile, sem estado, ocupação, estratos ou contagens) e
  as mesmas regras gerais de leitura do leitor (§2), e grava sua leitura em
  `leitura-auditoria/`. Ele nunca vê a referência principal, a leitura do
  leitor, o índice de tiles, inferências, comparações nem concordâncias anteriores.
- A concordância de classe (com denominador) decide: `referencia_confiavel` com concordância
  ≥ 0,90 (limiar configurável); abaixo disso, `ampliar_amostra` uma vez
  (`curation_audit amostrar --rodada RODADA --pdf ID --ampliar`: amostra dobrada, nova
  instância do auditor, nova concordância); persistindo, `encerrar_com_pendencia` e o PDF vai
  para `encerrado_com_pendencias` com nota — as divergências dele não justificam correção
  sozinhas:

  ```bash
  .venv/Scripts/python.exe -m scripts.curation_round avancar --rodada RODADA --pdf ID --fase encerrado_com_pendencias --nota "concordância abaixo do limiar na amostra ampliada"
  ```

  A concordância de ID exato é reportada com denominador. Tile descartado em que o auditor viu
  conteúdo gera alerta de falha de triagem, registrado como pendência.
- Conjunto avaliado da concordância (esquema `curadoria-concordancia-v2`):
  - da referência, o mesmo conjunto da comparação: observação operacional, sustentada e com
    família do inventário;
  - do lado do auditor, casa qualquer observação operacional com família do inventário que não
    seja ilegível;
  - divergência só de estado com a mesma classe é diagnóstico (`estado_divergente`) e não conta;
  - par avaliável × observação não operacional ou `local-unknown` no mesmo lugar diverge;
  - as bboxes das duas leituras são recortadas à região contígua de tiles amostrados que elas
    tocam, e a observação entra pelo centro da bbox recortada;
  - classes lineares (`CABO_AEREO`) são comparadas por cobertura de comprimento, não por IoU,
    com a tolerância e a cobertura mínima documentadas no módulo; ID exato não é medido para
    elas;
  - `fora_do_denominador` lista, com contagem por motivo, o que ficou de fora.
- A concordância mede consistência entre duas leituras de IA do mesmo modelo: oferece separação
  de tarefas e revisão, não validação estatística independente nem confirmação humana.

### 5. Agregar — demanda e backlog por causa

Primeiro a demanda visual: acrescentar a `RODADA/demanda.json`, no formato
`{"ids": ["<ID do inventário>"]}`, só os IDs observados nas referências congeladas da onda (ID
exato ou alternativas) e os confundidos nas comparações (ID divergente), e regerar a fila de
lacunas. IDs sob demanda sobem na fila sem receber status novo; observação que não resolve
sequer um ID candidato fica fora da demanda e é registrada como desconhecida no relatório, sem
inventar ID para elemento que não é simbologia do inventário.

```bash
.venv/Scripts/python.exe -m scripts.curation_coverage_e16 plan --matrix RODADA/matriz-antes.csv --demand RODADA/demanda.json --output RODADA/plano-lacunas.json
```

Depois da concordância de todos os PDFs da onda, o backlog:

```bash
.venv/Scripts/python.exe -m scripts.curation_backlog --rodada RODADA --onda K
```

- Usa só a comparação vigente de cada PDF. Agrupa as divergências por (tipo, família,
  `class_id`, método), prioriza por PDFs afetados, depois ocorrências e perdas da união, e liga
  cada grupo aos arquivos donos do método e a exemplos com tile de evidência. Um grupo é
  hipótese de causa, não conclusão.
- Pistas reúnem os grupos que compartilham arquivo dono; pistas diferentes nunca compartilham
  arquivo. `dependencias` e `acoplamentos` declaram módulos importados e arquivos donos de
  outras pistas.
- `falhas_execucao` vêm antes dos grupos do mesmo método. Método sem registro, sem dono ou PDF
  com referência não auditada são alertas para a orquestradora: configuração, mapeamento ou
  hipótese rebaixada, nunca divergência comum. Os alertas da comparação (como método sem
  `supported_classes`) são repassados com o PDF.
- `lacunas_de_cobertura` (esquema `curadoria-backlog-v2`) reúne, por família e `class_id`, os
  FN `sem_metodo` (classe que nenhum método cobre), com PDFs afetados e exemplos. Elas ficam
  fora dos grupos, das pistas e de `sem_dono`: são lacuna de cobertura, registrada no
  relatório, não defeito de um módulo dono.

### 6. Investigar

A ordem é a `prioridade` do backlog com dois ajustes: vão para a frente os grupos que
reaparecem das "Pendências acionáveis" da rodada anterior e os grupos cuja família/classe tem
IDs ao mesmo tempo em `demanda.json` e na fila de `plano-lacunas.json` (cruzamento demanda ×
lacunas). Nessa ordem, um `curadoria-investigador` por grupo recebe o trecho do backlog e os
caminhos vigentes de comparação, referência e inferência de cada PDF envolvido — mais o
`pipeline.json` quando o grupo envolve texto, atributo, quantidade ou relação. Ele decide pela
imagem e pela fonte, considerando que a referência também pode estar errada, lê o código dono e
devolve `causa_confirmada`, `causa_refutada`, `referencia_errada` ou `indeterminada`, com a
correção e a fixture sintética propostas. Não edita nada.

Referência errada gera nova versão a partir da leitura congelada, com motivo e evidência, sem
apagar as anteriores. Quem viu predições, comparações ou auditorias do PDF — inclusive de uma
duplicata dele (mesmo SHA-256 em outro caminho) — declara a exposição (na dúvida, `sim`);
revisão exposta não é chamada de cega. Revisão orientada por investigação que viu predições
declara `--exposicao sim` e só muda o que os pixels dos tiles confirmam, nunca o que a predição
sugere sem evidência visual:

```bash
.venv/Scripts/python.exe -m scripts.curation_reference revisar --rodada RODADA --pdf ID --arquivo RODADA/pdfs/ID/leitura/referencia-revisao-NN.json --motivo "MOTIVO COM EVIDÊNCIA" --exposicao sim
```

A nova versão invalida `comparado` e `auditado`: refazer `concordancia` com a mesma leitura do
auditor contra a versão vigente e `curation_compare --rodada RODADA --pdf ID`, comparando antes
e depois contra a mesma versão e explicando o efeito da revisão. Se uma concordância anterior do
PDF decidiu `encerrar_com_pendencia`, a auditoria não é recalculada: o PDF segue para
`encerrado_com_pendencias`.

### 7. Corrigir e integrar — pistas em série

PDFs das pistas entram em `em_correcao`:

```bash
.venv/Scripts/python.exe -m scripts.curation_round avancar --rodada RODADA --pdf ID --fase em_correcao --nota "pista-NN"
```

As pistas rodam **em série, na árvore principal, uma de cada vez**, na ordem de prioridade.
Cada pista tem arquivos permitidos (os donos da pista e os arquivos de teste atribuídos a ela,
sem repetição entre pistas); helpers compartilhados de fixtures e o inventário não são editados
por pista. Pista que precisa mudar uma dependência, um helper ou o inventário é replanejada como
pista própria. Para cada pista, a orquestradora:

1. registra `git status --short` e copia os arquivos permitidos para
   `RODADA/ondas/K/pistas/pista-NN/antes/`;
2. dispara um `curadoria-corretor` com os grupos confirmados, os relatórios, os testes focados e
   os acoplamentos;
3. confere que nada mudou fora dos arquivos permitidos;
4. roda os testes focados da pista e das pistas acopladas, Ruff, formatação e mypy:

   ```bash
   .venv/Scripts/python.exe -m pytest TESTES_FOCADOS -q
   .venv/Scripts/python.exe -m ruff check .
   .venv/Scripts/python.exe -m ruff format --check .
   .venv/Scripts/python.exe -m mypy
   ```

5. dispara um `curadoria-verificador` novo; REPROVADO volta ao corretor ou restaura os arquivos
   de `antes/` e vira pendência;
6. só então passa à próxima pista.

Regras de correção:

- Reproduzir a causa numa **fixture sintética autoral**, pequena e determinística, com positivo
  e negativos de contraste independentes, e confirmar que o teste falha antes do ajuste.
- Ajustar o módulo responsável: renderização/extração, OCR, geometria, detecção,
  legenda/contexto, anotação, interpretação, associação, deduplicação ou exportação. O algoritmo
  não pode memorizar nome, hash, caminho ou coordenadas do PDF nem tabela de respostas da
  referência; a regra funciona pelo sinal do documento e passa em exemplos sintéticos
  distintos. Mudança de saída incrementa a versão do extrator/detector correspondente.
- Promover conhecimento apenas com fonte rastreável, gramática/template ou contexto
  discriminante, positivo e negativos independentes e papel correto. `enabled` exige
  gramática, fonte e positivos/negativos
  ([`schemas/pacotes-simbologia.schema.json`](schemas/pacotes-simbologia.schema.json));
  `pending` exige motivo e não emite ID. Não marcar variantes `pending` como reconhecidas só
  porque estão cadastradas. Uma nova família/revisão altera o inventário com ID estável e fonte
  conferida, numa pista própria e serial.
- Falta de fonte ou ID exato bloqueia a promoção daquele caso, não o PDF inteiro. Continuar as
  correções comprováveis de leitura, associação, papel informativo, FP, duplicatas, custos e
  grupos visuais, registradas à parte do delta de IDs e com evidência antes/depois e regressão
  sintética.
- Pacotes declarativos só resolvem suas variantes; lacunas de outros métodos, FP da união,
  legenda, anotação, raster ou desempenho voltam ao módulo dono. Não modificar o reconciliador
  para cadastrar uma família por dados nem criar regra de conformidade a partir do exemplo. Não
  alterar detector, referência ou metas usando reservas já abertas.

### 8. Reinferir e fechar a onda

PDFs afetados = os das pistas integradas e das pistas acopladas, inclusive de ondas anteriores
ainda não fechados. Reinferir e recomparar só esses, contra a mesma referência congelada e com
as mesmas opções de inferência da rodada, e regenerar o backlog:

```bash
.venv/Scripts/python.exe -m scripts.curation_infer --rodada RODADA --pdf ID1 ID2 --jobs N --pipeline
.venv/Scripts/python.exe -m scripts.curation_compare --rodada RODADA --pdf ID1 --pdf ID2
.venv/Scripts/python.exe -m scripts.curation_backlog --rodada RODADA --onda K
```

Comparar antes e depois (TP_IA/FP_IA/FN_IA por método e união, com denominadores);
regressão reabre a pista.

Cada onda tem **no máximo dois ciclos de correção** (corrigir → reinferir → recomparar). Toda
divergência acionável — grupo com causa confirmada ou falha de execução — termina a onda
corrigida e verificada ou registrada em "Pendências acionáveis" do relatório com o id do grupo
(`grp-...`, estável entre ondas e rodadas), os PDFs, a pista e os arquivos donos, e um
impedimento comprovado (com a evidência) ou o dono e o próximo dado necessário. A onda
seguinte e a rodada seguinte retomam essas pendências antes dos demais grupos de mesma
prioridade (§6 e "Preparação da rodada"). Não encerrar só com o inventário de diferenças, por
falta de ID exato, por terminar um lote de candidatos ou por concluir que uma pequena amostra
representa o documento; também não exigir concordância perfeita com uma referência que pode
conter erro.

A onda termina quando cada PDF tem comparação vigente posterior à última integração e
auditoria aceita, ou foi encerrado com pendência.

## Fechamento da rodada

1. **Código congelado:** nenhuma correção nova; registrar `git status --short`. O relatório
   final corresponde a um único checkpoint de código/pacotes/configuração. As inferências de
   antes de ondas diferentes podem ter checkpoints distintos, porque as correções entram entre
   as ondas: identificá-los e não apresentar sua soma como inferência global do código inicial.
2. **Gates completos, uma vez e em série:** `IniciarTestes.bat` (no Git Bash,
   `cmd.exe //c IniciarTestes.bat`; resultado em `relatorio-testes.txt`) e:

   ```bash
   .venv/Scripts/python.exe -m scripts.audit_symbol_packages --output RODADA/fechamento/audit.json
   .venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output RODADA/fechamento/baseline
   .venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output RODADA/fechamento/uniao
   .venv/Scripts/python.exe -m scripts.reconcile_symbol_benchmark --predictions RODADA/fechamento/uniao/predictions.json --reference RODADA/fechamento/uniao/reference.json --exclude-method structural-raster-graph --exclude-method structural-vector-graph --output RODADA/fechamento/composicao
   .venv/Scripts/python.exe -m pytest tests/unit/test_declarative_symbol_packages.py tests/unit/test_benchmark_symbols.py tests/unit/test_symbol_inventory.py -q
   ```

   V-N cobre inventário/esquemas, fontes e integridade normativa: validar o esquema Draft
   2020-12 com implementação independente disponível (em instalação isolada, se necessário) e
   registrar comando/versão; se a fonte normativa F02 estiver disponível, repetir a auditoria
   apontando para ela
   (`.venv/Scripts/python.exe -m scripts.audit_symbol_packages --source-pdf CAMINHO_DA_F02 --output RODADA/fechamento/audit-fonte.json`)
   e conferir hash, páginas e localizadores — ausência da fonte impede validar novos IDs que
   dela dependem. V-Q cobre Ruff/mypy; V-G cobre a suíte
   integral, cobertura e contratos de jobs/histórico/exportações. Comparar baseline, isolados,
   união, composição e ablação com o checkpoint `inicial/` nos mesmos denominadores, inclusive
   negativos críticos; a interseção é só controle. Fazer `git diff --check` e conferir
   hashes/totalizadores. Falha preexistente é registrada como tal, com evidência; gate que não
   rodou não passou, e nomes de gate não valem como aprovação sem comando, resultado e
   artefato. Se o código ou os comandos mudarem, descobrir os novos no repositório e registrar
   a substituição.
3. **Reinferência de regressão de todo o corpus** (PDFs não encerrados), em paralelo, com as
   mesmas opções de métodos e pipeline das inferências anteriores:

   ```bash
   .venv/Scripts/python.exe -m scripts.curation_infer --rodada RODADA --pdf ID1 ID2 ID3 --jobs N --pipeline
   .venv/Scripts/python.exe -m scripts.curation_compare --rodada RODADA --pdf ID1 --pdf ID2 --pdf ID3
   ```

   Comparar com a última comparação de cada PDF; perda em qualquer PDF reabre a correção e os
   gates afetados. Não esconder perdas no total agregado.
4. **Persistência, revisão e exportação:** sobre o código congelado, inferir o corpus inteiro e
   projetar a inferência congelada pela persistência/revisão e pelos writers reais de
   exportação (diretório novo a cada checkpoint; o CLI recusa sobrescrever uma base).
   `benchmark_review_e14` exige um manifesto que cubra a descoberta recursiva de `--root`, por
   isso roda sobre a inferência do corpus inteiro, não sobre as saídas por PDF de
   `curation_infer`:

   ```bash
   .venv/Scripts/python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output RODADA/fechamento/corpus
   .venv/Scripts/python.exe -m scripts.benchmark_review_e14 --predictions RODADA/fechamento/corpus/predictions.json --manifest RODADA/fechamento/corpus/manifest.json --root examples --output RODADA/fechamento/revisao
   ```

   Isso não substitui a inspeção visual da UI e dos arquivos exportados afetados (elementos por
   ponto, camadas, contagens e vínculos): inspecioná-los se a UI estiver disponível; se não
   puder ser verificada, registrar o gate de UI/exportações como pendente.
5. **Fechar os PDFs:** com `comparado` e `auditado` vigentes, `fechado`; os demais,
   `encerrado_com_pendencias` com a nota do motivo. Registrar `fechado` ou
   `encerrado_com_pendencias`, nunca aprovado por falta de tempo, rótulo ou fonte.

   ```bash
   .venv/Scripts/python.exe -m scripts.curation_round avancar --rodada RODADA --pdf ID --fase fechado
   ```

6. **Matriz de cobertura** a partir de `RODADA/matriz-antes.csv`:

   ```bash
   .venv/Scripts/python.exe -m scripts.benchmark_packages_e07 --output RODADA/fechamento/benchmark
   .venv/Scripts/python.exe -m scripts.coverage_matrix_e16 --baseline-matrix RODADA/matriz-antes.csv --e07-report RODADA/fechamento/benchmark/report.json --output RODADA/matriz-depois.csv --summary RODADA/matriz-depois-resumo.json
   .venv/Scripts/python.exe -m scripts.curation_coverage_e16 compare --before RODADA/matriz-antes.csv --after RODADA/matriz-depois.csv --output RODADA/delta-cobertura.json
   ```

   O relatório de pacotes é o **dessa rodada**. O gerador da matriz recusa inferência de
   pacotes incompleta, FP/FN/duplicatas autorais ou hash de pacote divergente. A evidência de
   transformadores e estais é herdada da matriz de partida somente quando seus detectores e
   fixtures não mudaram; se mudaram, gerar relatórios frescos e passá-los ao gerador:

   ```bash
   .venv/Scripts/python.exe -m scripts.benchmark_transformers_e05 --output RODADA/fechamento/transformadores
   .venv/Scripts/python.exe -m scripts.benchmark_guys_e06 --output RODADA/fechamento/estais
   .venv/Scripts/python.exe -m scripts.coverage_matrix_e16 --baseline-matrix RODADA/matriz-antes.csv --e07-report RODADA/fechamento/benchmark/report.json --e05-report RODADA/fechamento/transformadores/report.json --e06-report RODADA/fechamento/estais/report.json --output RODADA/matriz-depois.csv --summary RODADA/matriz-depois-resumo.json
   ```

   Sem essa evidência, a matriz de partida permanece como checkpoint. O plano não substitui a revisão independente, e o delta não mede FP/FN de
   ocorrências nem ganho da união.
7. **Publicação só com todos os gates e a revisão visual aprovados:** copiar
   `RODADA/matriz-depois.csv` para `docs/data/matriz-simbologia-curadoria-atual.csv` e
   `RODADA/matriz-depois-resumo.json` para
   `docs/data/matriz-simbologia-curadoria-atual-resumo.json`, sem editar a matriz E16
   histórica. Com qualquer gate falhando ou pendente, não publicar e registrar o motivo. Nenhum outro
   arquivo versionado — inclusive este documento, a skill e os agentes — recebe resultados,
   datas, caminhos ou histórico da rodada.
8. **Relatório final** em `RODADA/relatorio.md`, nunca em arquivo versionado: tempos por fase e
   por onda; PDFs fechados e encerrados com pendência, com motivo; concordância de classe e de
   ID exato por PDF; TP_IA/FP_IA/FN_IA por método e união, antes e depois, com escopo e
   denominadores; TP/FP/FN sintéticos inicial × final (`inicial/` × `fechamento/`, isolados,
   união e composição, mesmos denominadores); exclusivos, ambiguidades e custos; melhorias de
   leitura (texto, atributos, relações) à parte do delta de IDs; correções (pistas, arquivos,
   testes, versões) e pareceres dos verificadores; falhas de execução e alertas; "Pendências
   acionáveis" (§8); pendências de triagem, de referência, de OCR, de medição e de gates
   (inclusive UI/exportações); delta de cobertura com os IDs ganhos e perdidos; gates com
   comandos e resultados. Sem ganho validado, dizer isso expressamente, mesmo que todos os PDFs
   tenham sido analisados; não confundir ganho de leitura com ganho de IDs.

## Aceite da rodada

- Todos os PDFs e páginas descobertos estão no manifesto, com duplicatas e ilegíveis
  declarados.
- Cada PDF tem referência congelada antes de qualquer comparação, com tiles revisados, regiões
  ilegíveis e exposição declarados, e auditoria amostral aceita — ou foi encerrado com
  pendência explícita.
- Predições e comparação final pertencem ao mesmo checkpoint de código; métodos com falha
  aparecem como falha.
- Cada correção tem fixture sintética com positivo e negativos, passou nos testes focados e no
  verificador, e as fontes do inventário estão intactas.
- V-N, V-Q e V-G, regressões de contrato, jobs, histórico e exportações passaram, ou a rodada
  não publica a matriz e registra o motivo.
- `delta-cobertura.json` publica IDs ganhos/perdidos e denominadores; o relatório confronta
  também TP/FP/FN sintéticos e TP_IA/FP_IA/FN_IA de desenvolvimento. Se a referência não for
  completa, não publicar recall global do PDF: apresentar o subconjunto avaliável e a cobertura
  faltante.

Uma rodada pode terminar com pendências explícitas; elas não contam como reconhecimento nem
impedem a rodada seguinte. A próxima rodada começa colocando mais PDFs em `examples/` e
invocando `/curadoria-simbologia` de novo: ela parte da matriz publicada e reutiliza as
referências dos PDFs inalterados.
