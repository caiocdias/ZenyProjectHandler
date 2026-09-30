# Curadoria incremental de leitura e simbologia — um PDF por vez

Este é o contrato operacional para melhorar a leitura, a interpretação e os
pacotes de símbolos, medindo a cobertura integrada. O usuário adiciona PDFs
localmente em `examples/` e envia o prompt ao fim deste arquivo. As antigas
frentes E07 (pacotes) e E16
(aceite integrado) são trabalhadas no mesmo ciclo C01–C04; seus rótulos servem
apenas para identificar donos dos métodos e o checkpoint histórico.
Uma execução **não treina o assistente de forma permanente**. Conhecimento
duradouro é uma mudança revisável nos algoritmos, nos pacotes, no inventário
quando necessário e nas fixtures/testes versionados. O chat e os PDFs ignorados
pelo Git não são uma base de conhecimento persistente.

O fluxo usa a capacidade visual do **modelo ativo da sessão** para criar uma
lista por ponto do que aparece em cada PDF. Essa referência de desenvolvimento
é congelada antes de executar os algoritmos no mesmo documento. O agente
compara os resultados, investiga as diferenças e incorpora correções testadas
antes de passar ao próximo PDF. A lista não se torna gabarito infalível só por
ter sido produzida por GPT; sua evidência e suas incertezas ficam registradas.

Cada rodada parte das lacunas publicadas na matriz E16, dá prioridade aos casos
observados nos PDFs e termina com uma nova matriz local e um delta de cobertura.
Melhorias de OCR, leitura de anotações, relações, contagem ou redução de FP
também são resultados, mesmo sem ganho de IDs na matriz. Uma rodada pode reduzir
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
  A análise visual pelo modelo ativo no Codex é parte deste fluxo autorizado:
  renderizar páginas e recortes e apresentar seus pixels ao modelo com as
  ferramentas da sessão. Se houver leitura nativa de PDF disponível, usá-la
  com a mesma verificação visual. Não pressupor que ler o binário ou extrair
  texto já apresentou as páginas ao modelo. Não enviar os documentos a APIs
  ou serviços adicionais sem autorização nem copiar PDFs privados para
  fixtures. O gate portátil continua sintético.
- Adicionar um PDF **não ensina automaticamente** o detector. Primeiro é
  preciso ver as páginas, identificar ocorrências e negativos, conferir a
  fonte/legenda e testar uma regra ou template. A referência feita por IA pode
  orientar desenvolvimento quando sustentada por evidência, mas não equivale
  a confirmação humana, norma ou avaliação independente de campo. Falta de
  confirmação humana não bloqueia a investigação dos outros casos do PDF.
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
- A visão do GPT pode falhar em texto pequeno, traços, contagem e localização
  precisa. Renderizar em resolução legível e ampliar por recortes; não confiar
  apenas na miniatura ou em OCR. Registrar ilegibilidade e alternativas sem
  inventar precisão ou confiança probabilística. Esses limites estão descritos
  na [documentação de visão da OpenAI](https://developers.openai.com/api/docs/guides/images-vision).
- Um PDF já visto passa a ser desenvolvimento. As reservas anteriores já foram
  abertas e não servem como teste cego repetido. Uma reserva futura precisa de
  seleção, esquema validado e congelamento próprios, sem receber regras ou
  rótulos do desenvolvimento.
- A matriz E16 preservada no workspace é o **ponto de partida histórico** da primeira rodada.
  Rodadas posteriores partem de `docs/data/matriz-simbologia-curadoria-atual.csv`,
  atualizado somente após os gates da rodada. A matriz e o resumo históricos
  permanecem preservados. O delta de IDs não comprova recall real, ganho da
  união nem aceite reservado; medir cada um em seu conjunto apropriado.

## Execução sequencial e equipe reutilizada

Existe **exatamente um PDF de projeto ativo por vez**. C01 descobre e registra
o corpus inteiro; depois C02, C03 e o fechamento local C04 são executados para
um PDF até encerrar seu checkpoint. Só então os mesmos agentes passam ao
próximo. A ordem é determinística pelo caminho relativo, sem distinguir
maiúsculas/minúsculas. Ler metadados/hashes do corpus em C01 não autoriza
renderizar, rotular, inferir ou ajustar dois PDFs de projeto em paralelo.

- Analisar nesta rodada **todos os PDFs e todas as páginas**, inclusive arquivos
  inalterados. Revisões anteriores ajudam a comparar hashes e resultados;
  não substituem a nova leitura visual, salvo autorização expressa para reuso.
  Dois caminhos com o mesmo hash permanecem no manifesto e são tratados
  sequencialmente, com a duplicidade declarada nos denominadores.
- O coordenador mantém `manifest.json`, a fila e `checkpoint.json` com o
  `pdf_ativo`, fases, responsáveis, versões, hashes, comandos e pendências.
  Cada PDF recebe `pdfs/<ordem>-<hash-curto>/` dentro da rodada, com `input/`,
  renderizações, referência, inferências, comparações e logs. Preservar todas
  as versões; não sobrescrever evidência anterior para melhorar o resultado.
- Reutilizar A, B e C durante a rodada, sem criar outra equipe para o próximo
  PDF. Respeitar os slots efetivamente disponíveis, incluindo o coordenador.
  Frentes adicionais trabalham em ondas dentro desse limite; não multiplicar
  agentes recursivamente. Cada agente herda o modelo ativo da sessão, sem
  substituir por outro modelo por economia. Registrar o identificador exposto
  pelas ferramentas; se indisponível, declarar isso sem inventar uma versão.
- A pode implementar algoritmos, pacotes e runner nos arquivos atribuídos;
  B possui fixtures/testes separados; C faz revisão visual e comparação.
  Um único dono por arquivo. Inventário, registro compartilhado e integração
  ficam com o coordenador e são alterados serialmente. A/B podem trabalhar
  no PDF ativo em paralelo; inferências e gates que disputem recursos ou
  checkpoints são executados serialmente. Sem subagentes, registrar a limitação
  e executar as funções em sequência, sem simular revisão independente.
- C não recebe predições, contagens esperadas nem a fila de lacunas antes de
  congelar a referência. Recebe as imagens, inventário, legenda e fontes
  necessárias à identificação. Depois do congelamento pode comparar saídas.
  Inicializar C com contexto delimitado, sem histórico de predições do documento.
  Se já houver exposição a resultados, inclusive de uma duplicata do mesmo PDF,
  declarar a exposição e não chamar essa revisão de cega.
  Subagentes do mesmo modelo oferecem separação de tarefas e revisão; não
  constituem, por isso, validação estatística independente ou confirmação humana.
- Fechar um PDF exige cobertura visual de todas as suas páginas, referência
  congelada, inferência antes/depois, investigação das divergências, testes
  das correções e inspeção das saídas afetadas. Toda divergência acionável deve
  ser corrigida e verificada ou ter impedimento comprovado, próximo dado e dono.
  Caso ilegível ou sem fonte pode encerrar com pendência; não conta como aprovado.
  Não encerrar só por falta de ID exato, por terminar um lote de candidatos ou
  por concluir que uma pequena amostra representa o documento inteiro.
- Após o último PDF, congelar o código final, executar os gates da rodada e
  repetir a inferência de todos os PDFs **sequencialmente** para procurar
  regressões introduzidas pelas correções posteriores. Se houver regressão,
  reabrir um PDF por vez, corrigir/testar e renovar os gates afetados.
  Na retomada após interrupção ou compactação, ler o checkpoint e continuar
  o mesmo PDF com a mesma equipe; não iniciar uma segunda fila.

As etapas C01–C04 pertencem **a cada execução**. Estado, cobertura, hashes e
impedimentos ficam no relatório local. Uma etapa sem evidência não é concluída.

## Etapas repetíveis para uma execução

### C01 — Descobrir e congelar entradas

**Dono:** coordenador. Ler instruções do repositório, este fluxo, ADR 0005,
inventário JSON/esquema, pacotes/esquema, matrizes, scripts/testes de benchmark
e `git status/diff`. Preservar alterações preexistentes. Descobrir
recursivamente todos os PDFs de `examples/`, inclusive `.PDF`, e registrar
caminho relativo, SHA-256, tamanho, páginas, legibilidade e versão/configuração.
Comparar com o manifesto local anterior quando existir, mas não presumir que
arquivo ausente foi validado. Duplicatas por hash mantêm todos os caminhos.
Verificar interpretador/dependências e a inicialização dos CLIs antes dos gates.
Se a `.venv` estiver indisponível, seguir as instruções de ambiente do repositório
ou registrar o impedimento; conferir argumentos no código não aprova a execução.

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

Preparar a entrada isolada apenas quando o PDF virar ativo. O comando atual
`benchmark_symbols examples --root` recebe uma **pasta** e descobre todos os
PDFs nela; apontá-lo para `examples/` processaria o corpus inteiro. Criar uma
pasta `input/` nova no diretório local desse PDF, contendo exatamente uma cópia
privada do original, sem outros PDFs em subpastas. Conferir SHA-256 antes/depois
da cópia e registrar a relação entre caminho original, cópia e identidade usada
nos relatórios. Saídas ficam fora de `input/`. Não alterar os originais nem
inventar uma opção `--pdf` que o CLI não suporta. Verificar essa pré-condição
antes de cada inferência; não reutilizar uma pasta de entrada de outro PDF.

Antes do primeiro ajuste, guardar também o checkpoint sintético inicial dos
métodos isolados e da união/composição, usando os CLIs de C04 com saídas em
`<rodada>/inicial/`. Comparar com o checkpoint final nos mesmos casos e
denominadores; fixtures acrescentadas recebem avaliação separada. Se o conjunto
mudar, mostrar a interseção comparável e o conjunto ampliado, sem atribuir uma
mudança de denominador a ganho do algoritmo. Isso não abre outro PDF de projeto.

### C02 — O modelo ativo lê o PDF e congela a lista por ponto

**Dono:** C, usando a visão do GPT ativo, antes de receber qualquer saída dos
algoritmos desta rodada. Renderizar e **realmente abrir/ver** todas as páginas
do PDF ativo, base e anotações. Usar visão geral e varredura sistemática por
recortes legíveis, com sobreposição e índice de cobertura, até cobrir todas as
regiões do desenho, legenda e notas. Registrar página, dimensões, resolução,
transformação de coordenadas, hashes e quais imagens/recortes foram vistos.
Uma página renderizada mas não vista não foi revisada; OCR ou JSON não
substituem pixels. Uma lista esparsa de âncoras não é um censo por ponto.

Fazer duas passagens: primeiro levantar os pontos, desenhos e textos; depois
conferir elementos de cada ponto, relações, quantidades e áreas sem ativos.
Identificar pelo contexto comprovável, legenda local e fontes disponíveis.
Não preencher atributos ilegíveis pelo que se esperaria encontrar no projeto.
Inspecionar regiões de ausência e desenhos parecidos para registrar negativos,
além dos positivos. Se uma região continuar ilegível após ampliação, marcá-la
como não avaliável e manter seu denominador explícito.

**Saída por PDF:** `referencia-visual-v001.json`, `lista-por-ponto.tsv` e índice
de páginas/recortes, todos locais. O JSON é a referência canônica; a tabela
permite revisar a lista. Cada observação contém no mínimo:

- SHA-256 do PDF, caminho relativo, página, camada/base/anotação e ID local
  estável da observação; identificação textual do ponto ou `desconhecido`.
- Região/coordenadas na página com convenção e transformação documentadas,
  imagem/recorte de evidência e descrição visual. Coordenadas estimadas pelo
  modelo são localizadores de revisão, não medidas precisas de engenharia.
- Papel `operacional`, `informativo` ou `desconhecido`; classe/família visual;
  ID do inventário quando distinguível, ou alternativas explícitas e seu motivo.
- Texto realmente legível, elementos encontrados, quantidades/unidades e
  relações entre estruturas, equipamentos, cabos e anotações. Estado existente,
  instalar/retirar e demais atributos só quando a evidência os distinguir.
  Guardar texto original e interpretação separadamente; ausência não é zero
  quando a região não foi suficientemente vista.
- Fonte do significado: legenda/nota com página e localizador, ou fonte
  normativa conferida. Registrar evidência para desambiguar e negativos próximos.
- Estado `sustentado_por_evidencia`, `provisorio` ou `ilegivel`, com motivo,
  origem `revisao_ia`, revisor/modelo informado pela sessão e eventual confirmação
  humana separada. Não converter uma avaliação verbal de confiança em probabilidade.

Uma ocorrência física tem uma identidade. Alternativas de ID, base/anotação e
detalhes repetidos se vinculam a essa ocorrência quando há contexto que prova
a relação; não gerar ativos duplicados. Também não fundir pontos ou páginas
por semelhança sem prova. Legenda, norte e desenhos informativos, inclusive §33,
entram na lista com seu papel e não na contagem operacional.

Salvar e registrar SHA-256 da referência **antes de iniciar a inferência**.
Ela é referência de desenvolvimento gerada por IA, com cobertura e incertezas
declaradas. Um achado sustentado pode orientar testes e correções sem esperar
confirmação humana de todo o documento; casos provisórios continuam separados.
Não afirmar que o modelo descobriu a verdade de campo ou garantiu censo perfeito.

Após congelar a revisão, produzir `demanda.json` local no formato
`{"ids": ["<ID E01>"]}` só com IDs observados ou confundidos. Regerar o plano
com `--demand`; IDs citados sob demanda sobem na fila sem receber status novo.
Se a observação não resolve sequer um ID candidato, mantê-la fora dessa lista
e registrá-la como desconhecida no relatório visual. Agregar a demanda da
rodada sem inventar IDs para elementos que não são simbologia do inventário.

### C03 — Executar no mesmo PDF, comparar e corrigir o processo

**Dono:** coordenador congela a interface e distribui arquivos com um único
responsável. A implementa somente nos arquivos atribuídos; B edita fixtures e
testes separados; C compara imagens e saídas sem editar o detector. Os três
trabalham exclusivamente no PDF ativo.

Congelar o checkpoint **antes** das correções: código/diff preexistente,
configuração, pacotes, versões e hashes. Executar os algoritmos no mesmo PDF
sem acesso à referência do revisor. Guardar a inferência completa e seu hash
antes de abrir o comparador. O snapshot deve cobrir todos os métodos/páginas
disponíveis, falhas e custos. Não confundir contagens de um smoke com resultados
completos de leitura. Usar os CLIs existentes, verificando seus argumentos:

```powershell
# Definidos a partir do manifesto do PDF ativo; input/ contém exatamente um PDF.
$pdfRodada = "$rodada/pdfs/<ordem>-<hash-curto>"
$entradaPdf = "$pdfRodada/input"
$pdfOriginal = "<caminho-absoluto-do-PDF-ativo>"
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root "$entradaPdf" --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output "$pdfRodada/antes/simbolos"
.\.venv\Scripts\python.exe -m scripts.benchmark_network_pdf "$pdfOriginal" --output "$pdfRodada/antes/pipeline.json" --runtime-directory "tmp/benchmark-runtime"
```

`benchmark_network_pdf` recebe um arquivo e grava **um JSON**, com snapshots
da leitura/interpretação nas variantes nativa e OCR. Inspecionar o runtime
configurado antes da execução. OCR indisponível é pendência registrada; a
execução suplementar com `--native-only` vai para outro JSON e não aprova OCR.
Usar `--complementary-ocr` só quando aplicável ao runtime e ao caso; registrar
a configuração e mantê-la na comparação antes/depois. Não instalar ou baixar
modelos implicitamente. Se o harness não expuser um resultado necessário,
instrumentar o módulo responsável com snapshot/telemetria e teste, em vez de
afirmar que o resultado foi verificado.

Comparar por PDF/página/ponto/família e etapa: símbolos, textos e atributos,
anotações, unidades/quantidades, relações, contagem, base/proposta, candidatos
exclusivos, duplicatas e papel informativo. Guardar `comparacao-antes.json`,
com cada divergência ligada à observação e à saída do método, causa investigada,
dono, ação e pendência. O comparador pode usar os localizadores da referência;
o detector recebe só o PDF e configuração normal, nunca ROI, rótulo, contagem
ou lista de achados do GPT.

Reportar `TP_IA`, `FP_IA` e `FN_IA` **relativos à referência de desenvolvimento
sustentada por evidência**, separando nível de classe/grupo visual e ID exato.
Informar numeradores e denominadores: ocorrências operacionais avaliáveis,
candidatos adotados, negativos, páginas/regiões vistas e não avaliáveis,
duplicatas, exclusivos e ambiguidades. Um ID ambíguo não é TP exato; desconhecido
não é reconhecimento. Divergências contra rótulos provisórios são contadas
separadamente e não justificam uma correção sozinhas. Essas métricas não são
precisão/recall de campo nem aceite independente. Resolver diferenças pela
imagem e fonte, incluindo a possibilidade de a referência GPT estar errada.

Para cada erro acionável, reproduzir a causa numa fixture sintética autoral,
pequena e determinística, com positivo e negativos de contraste independentes.
Ajustar o módulo responsável: renderização/extração, OCR, geometria, detecção,
legenda/contexto, anotação, interpretação, associação, deduplicação ou
exportação. O algoritmo não pode memorizar nome/hash do PDF, coordenadas de
ativos desse projeto ou tabela de respostas do revisor. A regra deve funcionar
pelo sinal do documento e passar em exemplos sintéticos distintos.

Reexecutar o PDF ativo em `iteracao-<n>/`, usando a mesma configuração comparável
e a referência congelada. Testar o módulo afetado, seus negativos e a união,
comparar antes/depois e C inspecionar visualmente as saídas alteradas. Repetir
até verificar as correções acionáveis ou comprovar os impedimentos restantes.
Não encerrar após apenas listar diferenças; não exigir concordância perfeita
com uma referência que possa conter erro. Se a revisão precisar de correção,
criar `referencia-visual-v002.json` com motivo/evidência, preservando v001 e
declarando que a revisão ocorreu após ver predições. Recalcular antes e depois
contra a mesma versão e explicar o efeito da alteração de referência.

Promover conhecimento apenas quando houver fonte rastreável, gramática/template
ou contexto discriminante, positivo e negativos independentes e papel correto.
Uma nova família/revisão altera o inventário com ID estável e fonte conferida.
Caso real reproduzível vira fixture sintética autoral pequena; PDF/recorte
privado não é copiado. O que não pode ser decidido permanece `pending`
com motivo e próximos dados necessários. Não marcar 344 variantes como
reconhecidas só porque estão cadastradas.

Falta de fonte ou ID exato bloqueia a promoção desse caso específico, não
todo o PDF. Continuar correções comprováveis de leitura, associação, papel
informativo, FP, duplicatas, custos e grupos visuais. Registrar esses ganhos
separados do delta de IDs. Um resultado pode melhorar o mecanismo sem acrescentar
um ID E16; a melhoria ainda precisa de evidência antes/depois e regressão sintética.

Priorizar o cruzamento entre a demanda visual e a fila de lacunas. Pacotes E07 só
resolvem suas variantes; lacunas E04/E05/E06, FP da união, legenda, anotação,
raster ou desempenho voltam ao módulo/etapa responsável e recebem checkpoint
novo antes da integração. Uma correção fora dos pacotes exige seus próprios
relatórios de benchmark atualizados. Não alterar detector, referência ou metas
usando reservas E16 já abertas.

**Saída:** diff revisável dos módulos/pacotes/inventário/testes,
`comparacao-antes.json`, `comparacao-depois.json`, relatório por ponto/família/etapa,
log de correções com versões/hashes e lista explícita de pendências.
Não modificar o reconciliador para cadastrar
uma família por dados nem criar regra de conformidade a partir do exemplo.

### C04 — Fechar cada PDF e validar a rodada final

**Dono:** coordenador. Conferir retornos A/B/C, integrar registro central
serialmente, congelar arquivos e repetir os gates afetados. O esquema de pacotes
é [`schemas/pacotes-simbologia.schema.json`](schemas/pacotes-simbologia.schema.json):
`enabled` requer gramática, fonte e positivos/negativos; `pending` requer motivo
e não emite ID. Confrontar seu SHA com o relatório do benchmark da mesma rodada.

Antes de avançar ao próximo PDF, salvar seu checkpoint local: páginas/recortes
vistos, referência e inferências com hashes, comparação antes/depois, correções,
fixtures, testes executados, revisão visual das saídas e pendências comprovadas.
Registrar `concluido` ou `encerrado_com_pendencias`, nunca `aprovado` por falta
de tempo, rótulo ou fonte. Liberar/reutilizar a mesma equipe no próximo PDF.

Após processar a fila inteira, congelar o código/configuração finais e executar
serialmente os gates da rodada. V-N cobre inventário/esquemas, fontes e
integridade normativa; V-Q cobre Ruff/mypy; V-G cobre suíte integral, cobertura
e contratos de jobs/histórico/exportações. Não usar esses nomes como aprovação
sem comando, resultado e artefato. Para o contrato atual, conferir ao menos:

```powershell
.\.venv\Scripts\python.exe -m scripts.audit_symbol_packages --output "$rodada/audit.json"
.\.venv\Scripts\python.exe -m scripts.benchmark_packages_e07 --output "$rodada/benchmark"
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output "$rodada/baseline"
.\.venv\Scripts\python.exe -m pytest tests/unit/test_declarative_symbol_packages.py tests/unit/test_benchmark_symbols.py tests/unit/test_symbol_inventory.py -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest --cov -o "cache_dir=$rodada/gates/vg-cache" --basetemp "$rodada/gates/vg-temp"
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

Na revisão final do corpus, repetir os comandos abaixo **para um PDF por vez**,
com `$pdfRodada`, `$entradaPdf` e `$pdfOriginal` definidos pelo manifesto.
Não usar `--root examples` nesta rodada sequencial. A pasta de entrada continua
contendo exatamente o PDF ativo. Usar diretórios novos a cada checkpoint;
`benchmark_review_e14` recusa sobrescrever uma base existente.

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root "$entradaPdf" --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output "$pdfRodada/final/simbolos"
.\.venv\Scripts\python.exe -m scripts.benchmark_network_pdf "$pdfOriginal" --output "$pdfRodada/final/pipeline.json" --runtime-directory "tmp/benchmark-runtime"
.\.venv\Scripts\python.exe -m scripts.benchmark_review_e14 --predictions "$pdfRodada/final/simbolos/predictions.json" --manifest "$pdfRodada/final/simbolos/manifest.json" --root "$entradaPdf" --output "$pdfRodada/final/revisao"
```

Manter as opções de OCR equivalentes às usadas no antes, registrando qualquer
mudança e sua justificativa. Comparar o resultado final com a referência e com
o checkpoint antes de cada PDF, preservando falhas de métodos como falhas.
E14 reutiliza inferência congelada e exercita persistência/revisão e os writers
reais de exportação; não substitui a inspeção visual de UI e arquivos exportados.
C deve ver as sobreposições/saídas afetadas e conferir elementos por ponto,
camadas, contagens e vínculos. Se a UI não puder ser verificada, registrar o
gate pendente. Consolidar o manifesto do corpus a partir das execuções isoladas,
sem perder a identidade original dos documentos.

Qualquer regressão em PDF já fechado reabre esse documento, um por vez.
Não esconder perdas no total agregado. Após uma nova correção, renovar os gates
afetados e a inferência dos PDFs potencialmente afetados; o relatório final
precisa corresponder a um único checkpoint de código/pacotes/configuração.
Os resultados locais de antes podem ter checkpoints diferentes, pois os PDFs
foram curados em sequência; identificá-los e não apresentar sua soma como uma
inferência global do código inicial. O antes/depois sintético usa o checkpoint
inicial preservado e os casos comparáveis.

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
Os CLIs atuais são `scripts.benchmark_transformers_e05 --output <diretorio>` e
`scripts.benchmark_guys_e06 --output <diretorio>`; usar seus `report.json` frescos.
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
todos foram realmente vistos, com regiões não avaliáveis declaradas; referências
por ponto foram salvas antes das inferências; predições e comparação pertencem ao
mesmo checkpoint; positivos, negativos e alternativas das mudanças passaram;
fontes intactas; V-Q/V-G, regressões de contrato, jobs, histórico e exportações
passaram. `delta-e16.json`
publica IDs ganhos/perdidos e denominadores; o relatório da rodada confronta
também TP/FP/FN sintéticos e TP_IA/FP_IA/FN_IA de desenvolvimento, exclusivos,
ambiguidades, custos e melhorias de leitura com seus denominadores. Se a referência
não for exaustiva, não publicar recall global do PDF; apresentar o subconjunto
avaliável e a cobertura faltante. Sem ganho validado, declarar isso mesmo que
todos os PDFs tenham sido analisados. Uma execução pode terminar
com pendências explícitas; elas não contam como reconhecimento nem impedem a
rodada seguinte. Não criar commit,
publicar ou implantar sem autorização explícita.

## Prompt one-shot para usar após adicionar PDFs

Cole o bloco inteiro em uma sessão nova, aberta na raiz do Zeny Project Handler.
Os arquivos podem estar em qualquer subpasta de `examples/`; o prompt
descobre os caminhos, sem precisar editar nomes.

```text
Execute uma rodada completa de curadoria incremental de leitura e simbologia conforme docs/fluxo-curadoria-incremental-simbologia.md no Zeny Project Handler, aberto na raiz. Use a capacidade visual do GPT ativo nesta sessão para analisar cada PDF e criar uma referência de desenvolvimento por ponto; depois execute os algoritmos no mesmo documento, compare e implemente correções testadas. Os PDFs estão em examples/; descubra todos recursivamente, inclusive .PDF, e compare hashes com a última rodada local, se existir. Analise todos os arquivos e páginas nesta rodada, inclusive inalterados; não substitua a leitura atual por observações antigas sem minha autorização.

Leia primeiro as instruções aplicáveis do repositório, docs/adr/0005-exemplos-locais-dinamicos.md, este fluxo, o inventário JSON e esquemas, os pacotes, as matrizes históricas/de curadoria, scripts/testes de benchmark e git status/diff. Preserve todas as alterações preexistentes. Execute C01–C04 em uma única tarefa. C01 registra metadados/hashes de todo o corpus, copia a última matriz validada e gera o plano inicial de lacunas por ID. Mantenha manifesto de todos os arquivos/páginas, falhas, fontes, hashes, versões/configuração e uma fila determinística por caminho relativo em tmp/curadoria-simbologia/<execucao>/. Registre duplicatas por hash sem omitir caminhos ou inflar denominadores silenciosamente.

Mantenha exatamente um PDF de projeto ativo por vez. Para ele, conclua C02, C03 e seu fechamento C04 antes de passar ao próximo. Não renderize, rotule, infira ou ajuste outro PDF enquanto este estiver ativo. Salve checkpoint.json com pdf_ativo, fase, responsáveis, artefatos e pendências; retome esse checkpoint após interrupção ou compactação. Cada documento tem diretório próprio pdfs/<ordem>-<hash-curto>/, referências e inferências versionadas. O CLI benchmark_symbols examples --root descobre todos os PDFs de uma pasta: use uma input/ local contendo exatamente uma cópia privada do PDF ativo, confirme seu hash e mapeie sua identidade ao original no manifesto. Guarde saídas fora de input/; nunca altere o original nem use --root examples para inferir o corpus em lote neste fluxo.

Delegue ao mesmo conjunto de subagentes, se disponíveis, e reutilize-o no próximo PDF: A implementa nos módulos de leitura/OCR/detecção/interpretação/pacotes/runner apenas os arquivos atribuídos; B cria fixtures sintéticas autorais e testes positivos/negativos em arquivos separados; C realiza a leitura visual e depois compara resultados, sem editar detector. Você coordena, define contratos e um dono por arquivo, integra inventário/registro central serialmente, verifica retornos e executa gates. Respeite o limite real de agentes incluindo você; novas frentes trabalham em ondas, sem duplicar equipes por PDF ou criar agentes recursivamente. Os subagentes herdam o modelo ativo; registre o identificador disponível ou a indisponibilidade, sem inventar nome/versão nem trocar de modelo. Execute inferências e gates que disputem recursos serialmente. Sem subagentes, registre e cumpra as funções em sequência; não simule revisão independente.

Antes do primeiro ajuste, preserve benchmarks sintéticos iniciais isolados e de união/composição para comparar com o checkpoint final nos mesmos casos. Separe fixtures novas e mudanças de denominador. Os resultados de antes de PDFs curados em sequência podem ter checkpoints distintos; identifique-os e não apresente sua soma como inferência global do código inicial.

Inicialize C com contexto delimitado, sem histórico de predições do documento. Se já houver exposição a resultados, inclusive de duplicatas do PDF, registre e não chame a revisão de cega. A revisão por subagentes do mesmo modelo não equivale a validação estatística independente ou confirmação humana.

No PDF ativo, C usa a visão do GPT desta sessão para realmente ver todas as páginas, base e anotações, antes de receber predições, contagens esperadas ou a fila de lacunas. Renderize páginas e recortes legíveis e apresente seus pixels ao modelo com as ferramentas disponíveis; extrair texto ou ler o binário não substitui ver as imagens. Faça visão geral, varredura por recortes com sobreposição e uma segunda passagem por todos os pontos e regiões, inclusive negativos, legenda e notas. Registre quais regiões foram vistas e as ilegíveis. Não aceite uma pequena lista de âncoras como censo do PDF. Salve referencia-visual-v001.json e lista-por-ponto.tsv com identidade da ocorrência, página/ponto/camada/região, evidência, papel operacional/informativo, classe/família, ID ou alternativas, texto original, interpretação, elementos, quantidades/unidades, relações e atributos comprováveis. Mantenha origem revisao_ia, fonte e estados sustentado_por_evidencia/provisorio/ilegivel; congele o SHA-256 antes de iniciar inferência.

Trate cada PDF real como desenvolvimento local. A referência do GPT pode orientar correções sustentadas por evidência, mas não é gabarito infalível, confirmação humana, treino permanente ou norma. Não presuma precisão extrema: amplie texto/traços pequenos, confira contagem e localização e preserve incertezas. Para desenhos iguais de IDs diferentes, registre uma ocorrência física com alternativas e contexto verificável; não force ID exato, duplique ativos ou conte desconhecido como reconhecimento. Vincule detalhes/base/anotações só quando comprovado; não funda páginas ou pontos por semelhança. Legenda, norte e desenhos informativos, inclusive §33, não viram ativos. Um caso sem rótulo/fonte não bloqueia os demais nem impede melhorias comprováveis de leitura, FP, contagem ou relações. Não envie documentos a serviços/APIs adicionais nem copie PDF/recorte privado para Git ou fixtures.

Congele código/configuração/pacotes e execute a inferência de símbolos e o pipeline completo de leitura/interpretação no PDF ativo usando os comandos atuais do fluxo. O algoritmo recebe só o PDF e sua configuração normal, nunca ROI/rótulo/lista/contagem do revisor. Registre falhas e indisponibilidade de OCR/métodos; uma execução native-only suplementar não aprova OCR. Congele saídas e hashes antes de abrir o comparador. Confronte por página/ponto/família/etapa símbolos, textos, atributos, estados, unidades, relações, TP/FP/FN, duplicatas, exclusivos, ambiguidades e custos. Preserve exclusivos válidos; concordância não é probabilidade. Separe TP_IA/FP_IA/FN_IA relativos à referência sustentada de divergências provisórias, classe/grupo visual de ID exato e ocorrências avaliáveis de regiões sem referência suficiente. Informe denominadores e não apresente essas métricas como desempenho independente de campo.

Investigue e corrija cada divergência acionável no módulo responsável. B reproduz a causa com fixture sintética autoral e positivo/negativos de contraste independentes; A implementa a correção geral; C confere visualmente antes/depois. Não memorize nome/hash/coordenadas desse projeto nem ajuste respostas para concordar com um rótulo duvidoso. Teste o módulo, negativos, métodos isolados e união, e reexecute o mesmo PDF em novas iterações até verificar as correções ou documentar impedimentos comprovados com dono e próximo dado. Se a referência estiver errada, preserve v001, crie revisão com motivo/evidência e declare a exposição às predições; compare antes/depois contra a mesma versão. Não encerre apenas com inventário de diferenças, por falta de ID exato ou ao terminar um lote. Incorpore conhecimento em algoritmos/pacotes versionados e fixtures/testes; novos IDs exigem fonte rastreável. Registre demanda local por IDs observados/confundidos e priorize seu cruzamento com o plano de lacunas; achados de outros métodos voltam ao dono correspondente.

Feche o checkpoint do PDF com lista por ponto, cobertura visual, inferências antes/depois, comparações, correções testadas e inspeção das saídas afetadas, UI/exportações. Pendências explícitas não são aprovação. Só então os mesmos agentes seguem ao próximo PDF. Ao acabar a fila, congele o checkpoint final e execute auditoria de inventário/esquemas/fontes, V-N, V-Q, V-G e benchmarks sintéticos isolados, união, composição e exclusivos. Reexecute todos os PDFs/páginas sequencialmente com esse checkpoint; compare com suas referências e resultados anteriores e reabra regressões uma por vez. Registre comandos, versões, resultados e gates pendentes, sem declarar gate não executado como aprovado. Gere matriz local com relatório de pacotes fresco e relatórios E05/E06 frescos se afetados; compare ganhos/perdas e denominadores, preservando a matriz histórica. Não use reservas já abertas para ajuste/teste cego nem declare aceite integrado sem nova reserva independente.

Entregue resumo conciso com arquivos alterados, melhorias do processo de leitura, IDs/famílias acrescentados, versões/hashes, cobertura de PDFs/páginas/pontos/regiões, TP/FP/FN sintéticos e TP_IA/FP_IA/FN_IA de desenvolvimento, exclusivos e ambiguidades com denominadores, delta E16 de IDs ganhos/perdidos, regressões, gates executados, pendências e próximo dado necessário. Se não houver ganho validado, diga isso expressamente; não confunda ganho de leitura com ganho de IDs. Preserve PDFs e relatórios privados fora do Git. Não crie commit, publique ou implante sem autorização explícita.
```

## Estado do fluxo

Contrato revisado em 30/09/2026 para leitura visual pelo modelo ativo, referência
por ponto, correções de todo o processo e processamento sequencial de um PDF
por vez com equipe reutilizada. Esta edição altera o fluxo e seu prompt;
não executa uma nova rodada, não acrescenta IDs e não declara ganho de desempenho.

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
