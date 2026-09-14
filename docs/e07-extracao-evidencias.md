# E07 — Extração robusta de evidências

Execução inicial em 10/09/2026 sobre `77258cf`; retomada em 11/09/2026 sobre `7fd1b7f`.
**Concluída em 14/09/2026 sobre `f82b1c2`**, conforme o aceite no
[roadmap](roadmap-mercado-paineis-leitura-rede.md). A recuperação integral exigida por E01
ainda estava pendente na retomada de 11/09; as correções e a validação final estão abaixo.
E08 permanece pendente, com suas dependências atendidas. Sem commit ou publicação.

## Retomada de 14/09/2026

Base `f82b1c2`, Git inicialmente limpo. Neste ambiente foram recuperados o inventário
original, o baseline e o runtime de E01. As três verificações privadas de integridade
passaram. A reprodução da versão 1.13.0 confirmou 312 evidências OCR, 33 propostas,
27 confirmações e seis vãos, em 16,426 s nativo e 47,177 s com OCR.

### Correções de extração

- Extrator **1.14.0**, com invalidação das assinaturas e caches anteriores. Os contornos
  preenchidos de caracteres próximos e consecutivos são isolados em rasters temporários.
  Molduras, traçados cruzados e fotografias não entram nessa camada. A fonte, os vetores
  originais e o OCR geral permanecem disponíveis.
- A orientação usa a sequência dos glifos e seus segmentos retos. O raster retorna por
  transformação inversa à geometria da página, incluindo sua rotação declarada. Contadores
  internos de caracteres mantêm a orientação dos subcaminhos; não são preenchidos por engano.
- Linhas curtas têm no máximo 16 contornos, 384 regiões por página e oito milhões de pixels
  de conteúdo. Cada lote mantém os limites de 48 linhas e oito milhões de pixels. Quando
  um lote consome menos linhas pelo limite de pixels, o seguinte começa no primeiro recorte
  ainda não processado. Limites excedidos e falhas geram diagnósticos; resultados anteriores
  são preservados, e falhas transitórias continuam fora do cache.
- Lotes aproximam larguras para reduzir pixels brancos, mantendo os índices e a ordem final
  das ocorrências originais. As margens entre recortes são de 20 pixels, além da margem própria
  do raster; os caracteres não são reamostrados. Uma nova tentativa com confiança de pelo
  menos 0,90 encerra as repetições daquele recorte.
- Para esses contornos, o Tesseract usa inglês somente quando esse idioma já está habilitado
  na capacidade verificada. O OCR geral mantém os idiomas configurados. Leituras fracas
  recebem tentativas limitadas; texto e confiança são preservados sem consulta ao catálogo.
- Confusões entre dígitos e letras também podem ser resolvidas pela concordância dos
  próprios contornos: duas outras regiões, leituras com confiança mínima de 0,85, mesma
  estrutura de caminhos e nenhuma discordância. Reflexão e meia-volta são rejeitadas.
  O texto anterior fica em `texto_ocr_original`; a confiança original não é inflada.
- Leituras localizadas já cobertas por glifos não repetem os mesmos recortes. A lista de
  desenho usada para rasterizar é reutilizada somente durante o OCR daquela página.
  Testes comparam bytes, origem, dimensões e DPI com o rasterizador original, nas quatro
  rotações, sem incluir anotações.
- A deduplicação mantém ocorrências iguais em posições distintas. Leituras gerais compostas
  continuam disponíveis quando contêm outros tokens; a presença de um rótulo localizado não
  apaga a linha inteira nem altera seu texto bruto.

### Reconciliação da referência e inspeção

O inventário original permanece intacto. A cópia `tmp/e07-complete/inventory-reconciled.json`
registra seu hash, as alterações e os mesmos denominadores: **95 ocorrências** (17 postes,
22 estruturas MT, 19 BT, 37 cabos), **18 identificadores**, **20 trechos físicos**,
**18 pares de endpoints visíveis**, **19 comprimentos** e as mesmas 20 exclusões.

A revisão do PDF original corrigiu uma transcrição de cabo (`ABC-2 CAA` para `ABC-4 CAA`).
Três ROIs de cabos apontavam para o centro do trecho, longe do rótulo; foram substituídas
por caixas de revisão do texto. Geometrias físicas, endpoints, situações e denominadores
não foram alterados. Identificadores e comprimentos ganharam caixas de rótulo separadas
dos pontos e traçados físicos; não foi ampliada a tolerância original de 0,01.

A comparação por token com correspondência um a um atingiu **95/95**, **18/18** e **19/19**.
Os 132 recortes correspondentes do PDF original foram inspecionados em seis folhas locais
(`qa-1.png` a `qa-6.png`), incluindo sobreposições, textos inclinados, situações existentes
e instaladas e o identificador corrigido por concordância. Isso certifica presença textual
e localização; associação, classificação de ambiguidades e topologia permanecem em E08.

### Validação

O conjunto obrigatório, ampliado com as regressões de glifos, concordância, rasterização,
orientação, molduras, falhas e benchmark, passou em **197 testes** (18,73 s).
Ruff e Mypy passaram, com 333 arquivos verificados pelo Mypy. A primeira execução do gate
integral abortou no Qt durante `test_pdf_export_forwards_current_callout_positions`.
O módulo isolado passou nos seis testes; o log inicial foi preservado como
`tmp/e07-complete/gate-first.log`. Um gate intermediário passou em 1.234 testes
(`gate-before-packing.log`), mas o aborto voltou após a otimização de lotes, em
`PortabilityPanelWidget._thread_finished`, ao liberar `_worker`. Esse segundo aborto está
em `gate-qt-recurrence.log`; a aprovação intermediária não foi usada como aceite final.

O sinal `QThread.finished` pode chegar enquanto ainda há limpeza na thread nativa.
O painel agora chama `wait()` antes de soltar os wrappers e emitir o estado disponível,
conforme o contrato de [sincronização do Qt](https://doc.qt.io/qt-6/qthread.html#isFinished).
Uma regressão com finalização controlada por eventos falhou antes da correção
(`thread-before.log`) e passou depois, junto dos sete testes do painel (`thread-fixed.log`).
Uma execução dirigida de portabilidade com temporários longos no workspace também falhou
com `WinError 3`; o gate oficial usa a raiz curta `C:\tmp` para esses casos.
O gate integral final passou com captura Qt padrão e sem exclusões de testes:
**1.238 testes em 421,83 s, cobertura 87,72%, saída 0**. Dependências, Ruff, formatação,
Mypy (333 arquivos), fronteira do cliente e complexidade E/F (2.768 funções e métodos)
também passaram. Log: `tmp/e07-complete/gate-final.log`. A etapa não tem bloqueios pendentes.

Uma primeira medição ficou em 57,930 s com OCR, mas a repetição atingiu **61,257 s**,
acima do limite. Esse resultado está preservado em `benchmark-over-budget.json`. O agrupamento
por largura e a parada de tentativas confiáveis resolveram o custo restante: na revisão final,
o fluxo nativo levou **15,511 s** e o fluxo completo com OCR, promoção e vãos **55,313 s**.

O monitor final cobriu 377 amostras, com no máximo dois processos Python (launcher e intérprete)
e um Tesseract: high-water do Python **548,36 MiB**, high-water observado do Tesseract
**85,30 MiB** e pico agregado amostrado **481,08 MiB**. O pico dos subprocessos depende da
amostragem de 200 ms. Todos ficaram dentro dos limites congelados de 25/60 s, 768 MiB para
Python, 256 MiB para Tesseract e 1 GiB agregado. Hash, tamanho e mtime da fonte foram preservados;
o SHA-256 continua `1e824e972d5cfc0b19fbcae774321d371cff30f6a8d1dfcb3673db858e6c77df`.

A auditoria final repetiu **95/95 ocorrências, 18/18 identificadores e 19/19 comprimentos**.
Quatro folhas visuais ficaram idênticas por SHA-256; as duas com diferenças de recorte
(`qa-3.png` e `qa-5.png`) foram inspecionadas novamente, sem perda de evidência.

O resultado tem **3.719 evidências, incluindo 399 OCR**, sem diagnósticos. O pipeline
produz 107 propostas brutas, 105 finais, 97 confirmações automáticas e 30 vãos. Essas contagens
não homologam associação: a saída semântica tem 21 estruturas MT para 22 no inventário, além
de 11 propostas de equipamento fora das 95 ocorrências. E08 deve usar as evidências recuperadas
para conferir normalização, situação, promoção e endpoints, incluindo as ambiguidades.

Reprodução nesta máquina, com Python 3.12.14, PyMuPDF 1.28.0 e Tesseract 5.4.0.20240606:

```powershell
# Gate público com captura Qt padrão, sem excluir testes.
$env:PYTEST_ADDOPTS='-o cache_dir=tmp/e07-complete/gate-cache'
.\IniciarTestes.bat *> tmp/e07-complete/gate-final.log
Remove-Item Env:PYTEST_ADDOPTS

# Rodar sozinho, sem outro processo de teste/benchmark Python ou Tesseract.
# O monitor local invoca este comando e amostra memória a cada 200 ms:
.\.venv\Scripts\python.exe -m scripts.benchmark_network_pdf `
  "examples/PROJETO DE REDE 1256148225.pdf" `
  --output tmp/e07-complete/benchmark-final.json `
  --runtime-directory tmp/e01/runtime
.\.venv\Scripts\python.exe tmp/e07-complete/reconcile_inventory.py `
  tmp/e07-complete/benchmark-final.json
```

Os logs direcionados estão em `required-packed.log` e `export-recheck.log`; benchmark,
amostragem e auditoria em `benchmark-final.json`, `memory-final.json` e `audit-reconciled.json`.
O monitor local é `monitor_benchmark.ps1`; as seis folhas visuais usam o raster do PDF original.

Artefatos privados, probes e snapshots ficam em `tmp/e07-complete/`, ignorados pelo Git.
O caso real continua opt-in; os testes públicos usam somente figuras sintéticas.

## Retomada de 11/09/2026

O checkout estava limpo. O PDF original continua disponível, mas `tmp/e01/`, `tmp/e07/`
e `tmp/e07-review/` citados na execução anterior não estão neste checkout. Portanto, o
inventário por ocorrência, o baseline privado e os scripts locais anteriores não puderam
ser revalidados. Os denominadores e limites publicados de E01 foram preservados. Uma nova
execução da versão 1.12.0 reproduziu exatamente suas contagens publicadas: 3.590 evidências,
270 OCR, sete propostas, uma confirmação e zero vãos. Isso recupera um ponto de comparação
do código anterior, mas não substitui a revisão geométrica das 95 ocorrências.

O ambiente `.venv` usa Python 3.13.14; o acesso ao executável da Microsoft Store exige
execução fora do isolamento do Codex nesta máquina. Não foi necessário recriar o ambiente.
O português do Tesseract foi provisionado pelo mecanismo existente, com hash fixado, em
`tmp/e07-unblock/runtime`. Nenhum dado do PDF foi enviado a serviço externo.

### Mudanças da retomada

- Extrator **1.13.0**: invalida o cache da versão anterior. As molduras que passam pelos
  limites geométricos existentes, mas ficam fora dos grupos de cabos, recebem uma leitura
  em lote. Não foram relaxados os limites de dimensão, cor ou proporção dos símbolos.
- Novo `pymupdf_ocr_batch.py`: empacota no máximo 48 recortes e oito milhões de pixels por
  página, com margens brancas, sem reamostragem e com uma chamada adicional de OCR. Textos
  que cruzam recortes ou caem nas margens são rejeitados. A ordem devolvida pelo Tesseract
  não interfere na associação espacial; códigos iguais em posições diferentes permanecem.
- A geometria retorna ao recorte retificado e depois aos quatro cantos na página original.
  Texto bruto, confiança, DPI, índice do recorte, giro e processamento ficam registrados.
  O lote não presume categoria ou situação, nem corrige caracteres para produzir um código
  esperado. Também não apaga texto geral diferente apenas por proximidade.
- Molduras além do orçamento mantêm diagnóstico de cobertura parcial. Falha no lote conserva
  as evidências anteriores e usa o diagnóstico de falha transitória já excluído do cache.
- O teste HTTP/Qt espera a pesquisa inicial terminar no servidor e no Qt antes de limpar a
  observação e iniciar o cenário atrasado. As verificações de edição, reconexão e fechamento
  permanecem. Forçar essa pesquisa inicial reproduziu o erro nas três variantes antes da
  correção; os 13 testes do módulo passaram após corrigir a sincronização.

### Auditoria local

A inspeção visual das 42 molduras explica a perda anterior: há rótulos reais de postes,
estruturas e cabos abaixo dos 12 pontos que iniciavam os grupos localizados. Uma moldura
tem sobreposição de símbolos e foi excluída somente da nova auditoria exploratória, sem
alterar qualquer exclusão ou denominador de E01. Nas outras 41, a conferência exige o código
intacto e o centro da evidência dentro da moldura, com correspondência um a um. Essa é uma
métrica de presença textual em um subconjunto; não certifica situação, catálogo ou topologia.

| Medida nesta máquina | 1.12.0 reproduzida | 1.13.0 final |
|---|---:|---:|
| Evidências OCR | 270 | 312 |
| Propostas finais | 7 | 33 |
| Confirmações automáticas | 1 | 27 |
| Vãos projetados, sem homologação de associação | 0 | 6 |
| Rótulos intactos no subconjunto visual | 1/41 | 33/41 |
| Tempo nativo, limite 25 s | 12,435 s | 19,652 s |
| Tempo com OCR, limite 60 s | 29,537 s | 47,957 s |

Os oito rótulos restantes do subconjunto têm troca de caracteres, parênteses mal lidos ou
dígitos truncados. Os outros itens do inventário integral não foram homologados nesta auditoria.
O lote leu todas as 42 molduras selecionadas, por isso o diagnóstico anterior de molduras
não processadas desapareceu; isso não significa ausência de erros de reconhecimento.

Medição final isolada: **515,88 MiB** de high-water Python (limite 768 MiB), **445,88 MiB**
de RSS Python amostrado, **80,26 MiB** de Tesseract (limite 256 MiB) e **445,88 MiB**
agregados amostrados (limite 1 GiB). Foram 339 amostras, com no máximo dois processos Python,
`python` e `python3.13`. O primeiro monitor contava apenas o launcher; sua medição inválida
foi preservada em `memory-incomplete.json` e substituída pela repetição em `memory-final.json`.
Os picos amostrados podem subestimar eventos menores que 200 ms, como no protocolo E01.

Os tempos variaram também no caminho nativo, cujo comportamento não mudou; a diferença
total não deve ser atribuída apenas à chamada adicional de OCR. Ambos os limites congelados
foram atendidos. O snapshot final, sua auditoria e o stderr vazio estão em
`benchmark-final.json`, `audit-frames.json` e `benchmark-final-stderr.log`. Hash, tamanho e
mtime da origem foram preservados; SHA-256 permanece
`1e824e972d5cfc0b19fbcae774321d371cff30f6a8d1dfcb3673db858e6c77df`.

### Validação da retomada

- Conjunto obrigatório de extração, fixtures novas e ferramentas: **162 aprovados**,
  `tmp/e07-unblock/required.log` (19,99 s).
- Módulo HTTP/Qt: **13 aprovados**, `http-green.log` (22,70 s). A reprodução determinística
  anterior registrou **três falhas** com a consulta da preparação indevidamente contada,
  `http-red.log` (12,05 s).
- Suíte pública completa: **1.202 aprovados**, **87,71%** de cobertura, 409,40 s,
  `gate.log`; a falha HTTP/Qt anterior não se repetiu. Dependências, cliente magro e
  complexidade E/F passaram na mesma execução.
- Ruff e formatação finais: **343 arquivos**, aprovados. Mypy final: **326 arquivos sem
  erros**. O primeiro `IniciarTestes.bat` terminou reprovado exclusivamente por uma anotação
  de tipo no teste novo (`replace` com dicionário genérico), encontrada antes da correção.
  Após corrigir a anotação, Mypy foi repetido com aprovação (`mypy-final.log`); lint,
  formatação e Mypy foram conferidos novamente após a suíte. O log original foi preservado,
  sem apresentá-lo como uma execução integral aprovada do `.bat`.

Comandos reproduzíveis, na raiz:

```powershell
.\.venv\Scripts\python.exe -c 'from pathlib import Path; from zeny_project_handler.adapters.analysis.tesseract_runtime import provision_portuguese_language; print(provision_portuguese_language(Path("tmp/e07-unblock/runtime")))'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_project_http_gateway.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_tesseract_ocr.py tests/unit/test_tesseract_runtime.py tests/unit/test_analysis_cache.py tests/unit/test_pdf_coordinates.py tests/integration/test_document_analysis.py tests/unit/test_pymupdf_orientation.py tests/unit/test_pymupdf_frames.py tests/unit/test_pymupdf_ocr_failures.py tests/unit/test_pymupdf_ocr_batch.py tests/unit/test_benchmark_network_pdf.py tests/unit/test_smoke_examples.py -q
.\IniciarTestes.bat
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy --cache-dir tmp/e07-unblock/mypy-cache
.\tmp\e07-unblock\monitor_benchmark.ps1
.\.venv\Scripts\python.exe tmp/e07-unblock/audit_frames.py
git diff --check
```

O monitor executa `python -m scripts.benchmark_network_pdf` com o PDF de E01, saída
`tmp/e07-unblock/benchmark-final.json`, runtime `tmp/e07-unblock/runtime` e SQLite novo,
sem cache, SQL, HTTP ou UI. Mede a cada 200 ms e deve rodar sem outros processos Python ou
Tesseract. A auditoria e o monitor permanecem privados e locais, como a referência E01.
`git diff --check` final aprovado; nenhum PDF, raster, snapshot ou inventário privado foi
incluído nos arquivos versionados. Sem commit ou publicação.

### Bloqueio remanescente

Para concluir E07 ainda é necessário recuperar o `inventory.json` original ou reconstruí-lo
por revisão integral do mesmo PDF, reconciliando explicitamente os 95 itens, 18 identificadores,
18 pares de endpoints e 19 comprimentos com os denominadores publicados. Depois, corrigir as
leituras incompletas e as classes fora dessas molduras, medir a correspondência por ocorrência
e repetir a aceitação completa. Não reduzir metas nem confundir as confirmações automáticas
do pipeline com homologação humana. E08 continua pendente até esse aceite.

Arquivos privados desta retomada ficam em `tmp/e07-unblock/`: `benchmark-before.json`,
`benchmark-after.json` (exploratório), `inspect_frames.py`, `frames.json`, `frames.png`,
`probe_batch.py`, `batch-result.json`, `audit_frames.py` e os logs. O snapshot exploratório
foi feito antes de conservar textos gerais divergentes na deduplicação; não é a medição
final da versão 1.13.0.

## Registro da execução inicial de 10/09/2026

## Dependência e limites

Git inicial limpo; nenhum `AGENTS.md` encontrado nos ancestrais ou no projeto. Foram lidos
roadmap, handoff E01, adaptadores de análise, porta de análise, cache e testes relacionados.
O extrator e `ports/analysis.py` não divergiam da versão diagnosticada em E01. As alterações
posteriores de mercado/UI foram preservadas. As três verificações privadas de E01 passaram,
confirmando inventário, denominadores, baseline completo, runtime e integridade da fonte.

Mantidos: 95 ocorrências inequívocas, 18 identificadores, 18 trechos com endpoints visíveis,
19 comprimentos explícitos e 20 exclusões por ambiguidade. Meta continua 100%, sem duplicatas
ou invenções; limites continuam 25 s nativo, 60 s OCR, 768 MiB Python, 256 MiB Tesseract e
1 GiB agregado. Sem alteração em interpretação, promoção, topologia, SQL ou PDF original.
Somente Tesseract local; nenhum OCR externo ou aumento global de DPI.

## Mudanças e decisões

- `pymupdf_analyzer.py`: extrator **1.11.0 → 1.12.0**, invalidando assinatura/cache derivado.
  Resultados com falha transitória de OCR não são gravados no cache, permitindo nova tentativa.
- `tesseract_ocr.py`: solicita TSV por `tessedit_create_tsv=1` e desativa texto simples por
  `tessedit_create_txt=0`. Dispensa o arquivo opcional `configs/tsv`, ausente no provisionamento
  observado por E01. Cabeçalho TSV obrigatório: saída vazia, texto simples ou esquema inválido
  gera falha observável; TSV válido sem palavras continua sendo resultado vazio legítimo.
  A capacidade incorpora `geracao_tsv` e `validacao_tsv`, invalidando caches do renderer antigo.
  `tesseract_runtime.py` e a porta neutra não precisaram mudar.
- Novo `pymupdf_orientation.py`: nas páginas densas, usa os eixos do texto parcial para orientar
  os nove recortes existentes. Exige pelo menos 20 caracteres e concordância de 80% em eixo
  cardinal, com tolerância angular de 5°; sem sinal suficiente mantém o giro original. O giro
  declarado da página é considerado. Não se deduz orientação pela NS, tamanho da folha ou
  conteúdo esperado. Na fonte de E01, as sete linhas nativas têm eixo `(0,-1)`, compatível com
  o controle visual de giro horário de 90°. Não acrescenta passagens OCR.
- `pymupdf_ocr.py`: desfaz o giro antes de normalizar caixas e usa origem/dimensões reais do
  pixmap, incluindo arredondamento dos pixels nas bordas do recorte. Evidências mantêm texto,
  confiança, assinatura/idiomas do motor, recorte e giro aplicado. A deduplicação de texto igual exige
  sobreposição espacial; códigos iguais próximos, mas sem sobreposição, continuam distintos.
  Em empate de confiança, prefere a caixa mais completa. Falha durante a grade preserva os
  recortes concluídos e informa onde parou e quantos ficaram sem leitura; não repete chamadas
  no runtime defeituoso nem apresenta o OCR localizado como concluído.
- Molduras `qu/re` com linha que retrace a mesma borda passam a ser reconhecidas. Segmento
  cruzado ou fora da borda continua rejeitado. Retificação corrige espelhamento e conserva os
  quatro cantos normalizados em polígono, inclusive em páginas com rotação declarada.
  Os limites de dimensão/vizinhança permanecem. Molduras excluídas da seleção localizada
  geram `analise.ocr_cobertura_parcial`; OCR geral não garante leitura dessas regiões.

A inspeção diferenciou símbolos pequenos de caixas de texto. Os 13 quadriláteros verdes
pequenos citados em E01 não justificam diminuir indiscriminadamente o limite de 7 pontos.
Há 76 caminhos verdes `qu+l`; 42 satisfazem os limites de moldura, mas nenhum inicia o grupo
de cabos que exige largura de 12 pontos. Ativar todas essas regiões acrescentaria dezenas
de chamadas; essa ampliação não foi adotada sem comprovar cobertura e custo. A decisão já
existente de executar OCR em página vetorial densa com cabeçalho nativo foi preservada.

Fixtures públicas: `tests/e07_pdf_fixtures.py`, `test_pymupdf_orientation.py`,
`test_pymupdf_frames.py`, `test_pymupdf_ocr_failures.py` e extensões em
`test_tesseract_ocr.py`. Cobrem giros cardinais, inclinação, texto parcial/vetores, recortes e
bordas, códigos repetidos por ocorrência, molduras retraçadas e controles negativos,
confiança/proveniência, falhas TSV/timeout, cancelamento e invalidação/recuperação de cache.
Os controles existentes de imagens/anotações permanecem no conjunto obrigatório.

## Comparação local e limites da avaliação

A auditoria textual privada compara o snapshot novo com `tmp/e01/inventory.json` e
`tmp/e01/baseline-final.json`, preservando correspondência um a um por evidência/offset.
Ela procura tokens intactos e localização na ROI com tolerância de 0,01. Isso mede presença
textual aproximada: não homologa categoria, situação ou associação operacional.

O inventário E01 guarda centros físicos dos anchors, que não são centros dos rótulos.
Usar distância centro-a-centro de 0,01 isoladamente rejeitaria textos deslocados junto ao
símbolo. Essa limitação está registrada no JSON da auditoria, sem alterar coordenadas,
denominadores ou tolerância de E01. Tokens ausentes de toda a extração demonstram omissão
independentemente dessa limitação. Ganho em propostas não substitui essa verificação.

Benchmark final isolado: `tmp/e07/benchmark-final.json`, logs `benchmark-final.log` e
`benchmark-final-stderr.txt` (vazio), memória `memory-final.json`, resumo `summary-final.json`.
Auditoria: `tmp/e07-review/extraction-coverage.json`, reproduzida por `compare_extraction.py`.
Não havia outros processos Python/Tesseract ao iniciar; 419 amostras, no máximo dois processos
Python (launcher e intérprete). Execução retornou zero e confirmou tamanho/mtime/SHA-256
inalterados: `1e824e972d5cfc0b19fbcae774321d371cff30f6a8d1dfcb3673db858e6c77df`.

| Medida | E01 | E07 final |
|---|---:|---:|
| Evidências nativas | 3.320 | 3.320 |
| Evidências com OCR | 3.593 | 3.590 |
| Evidências OCR | 273 | 270 |
| Propostas brutas com OCR | 8 | 12 |
| Propostas finais / relações | 3 / 0 | 7 / 1 |
| Confirmações / regiões / vãos | 0 / 4 / 0 | 1 / 7 / 0 |
| Diagnósticos com OCR | 0 | 1: cobertura parcial de 42 molduras |
| Tokens de ocorrência com correspondência um a um na ROI | 0/95 | 3/95 |
| Ocorrências sem código intacto em qualquer texto extraído | 95/95 | 80/95 |
| Identificadores intactos encontrados, sem certificar associação | 4/18 | 7/18 |
| Comprimentos textuais próximos ao segmento, sem certificar associação | 0/19 | 7/19 |
| Tempo total nativo (limite 25 s) | 15,882 s | 23,406 s |
| Tempo total OCR (limite 60 s) | 38,468 s | 53,959 s |

As três correspondências aproximadas de códigos são duas de poste e uma de estrutura MT.
Todos os 37 cabos continuam sem código intacto; sete comprimentos explícitos também não têm
token intacto em qualquer texto extraído. Os sete identificadores encontrados não atendem
à comparação estrita com o centro físico do anchor, pelas limitações de anotação já descritas.
Não se declara recall/precisão homologados, associação correta de endpoints ou zero duplicatas
na fonte real. A quantidade menor de linhas OCR, por si só, não mede ganho nem perda de leitura.

Tempos de extração/persistência: nativo 12,851 → 19,139 s; OCR 34,580 → 48,337 s.
Interpretação/promoção: nativo 2,549 → 3,516 s; OCR 3,282 → 4,901 s. O desempenho ficou
mais lento que E01, embora ainda dentro dos limites congelados. Não sobra orçamento para
acrescentar dezenas de chamadas sem redesenhar e medir a estratégia de recortes.

| Memória | E01 | E07 final | Limite |
|---|---:|---:|---:|
| RSS Python amostrado | 524,27 MiB | 493,95 MiB | 768 MiB |
| High-water do intérprete | 571,15 MiB | 539,85 MiB | 768 MiB |
| RSS Tesseract amostrado | 78,18 MiB | 81,79 MiB | 256 MiB |
| RSS agregado amostrado | 524,27 MiB | 493,95 MiB | 1.024 MiB |

Versões medidas: Python 3.12.14, PyMuPDF 1.28.0, Tesseract 5.4.0.20240606, `por+eng`,
OEM 3, PSM 11/10/7/6 e timeout de 90 s. DPI 450/1200/1800, grade 3 × 3 e sobreposição
0,025 preservados; interpretador continua 21.1. Assinatura do analisador OCR:
`ccd634c71a2110acede474bb66fdbc8311e87f7332781f4bede554f7a9f43f1a`.
Assinatura da capacidade Tesseract:
`a78dae0aa932b45a80a3cd128ad555e926cafd8ed16e7270e78902a6fae6a9d1`.
Hashes dos idiomas, configurações completas e assinatura nativa constam do resumo JSON.
O controle sintético real sem `configs/` recuperou o texto completo com confiança 0,90646,
registrado em `tmp/e07/tesseract-tsv-probe.json`. A execução exploratória anterior em
`orientation-benchmark.json` teve trabalho concorrente e não foi usada para aceitar desempenho.

**Bloqueio de aceite:** as omissões acima demonstram perda anterior à interpretação; as metas
de extração de E01 não foram atingidas. Os limites de tempo/memória e o hash foram atendidos,
mas isso não conclui E07. A ação de desbloqueio está no handoff abaixo.

## Validação e comandos

Conjunto obrigatório de E07, novas regressões e ferramentas de benchmark/smoke:
**151 aprovados em 27,31 s**, log `tmp/e07/required-tests.log`. Verificações privadas de
integridade E01: **3 aprovadas**. Ruff global e formatação: aprovados (341 arquivos).
Mypy: **324 arquivos, sem erros**. Integridade de dependências, fronteira do cliente magro
e complexidade E/F: aprovadas. `git diff --check`: aprovado.

Durante o desenvolvimento, testes novos revelaram duplicação de ocorrência na borda de
recortes e Mypy apontou imports/tipo de tupla nos testes. Esses problemas foram corrigidos
e os comandos repetidos com aprovação; os resultados finais acima substituem essas tentativas.
Uma tentativa da suíte pública com `--basetemp tmp/e07/pytest-public` falhou em portabilidade
por `WinError 3` em `CopyFile2`, devido aos caminhos temporários longos no Windows; foi
interrompida, sem ser considerada aprovada. O controle dos mesmos 25 testes passou com
`--basetemp C:\tmp\zph-e07-pathcheck-2156` (23,84 s; aviso de escrita no cache antigo).
A repetição integral usa diretório/cache curtos novos, seguindo `IniciarTestes.bat`, e arquivo
de cobertura próprio. Código de portabilidade não foi modificado.

Suíte pública completa adicional: **1.190 aprovados, 1 falha em 576,81 s**, cobertura
**87,69%** (mínimo 85,01% atingido), log `tmp/e07/public-tests-final.log`. O gate global
**não está aprovado**. A falha é
`test_qt_http_delayed_search_cannot_cross_input_or_connection_context[close]`, linha 904:
a lista de buscas inclui a consulta inicial além da consulta atrasada esperada. Esse teste
não lê PDFs nem exercita extração; o mesmo código passou na tentativa anterior e na
repetição isolada (**1 aprovado em 4,80 s**, `tmp/e07/http-retry.log`). Há evidência de
dependência de temporização, mas a estabilidade da suíte continua pendente; nenhum código
HTTP/Qt foi alterado nesta etapa. Desbloqueio: isolar a fase de preparação da busca atrasada
e verificar a sincronização do teste/fechamento, depois repetir o gate completo.

Todos os comandos abaixo partem da raiz, em PowerShell, com `.venv`. Dados reais, runtimes,
rasters, snapshots, scripts de transcrição e logs permanecem locais/ignorados sob `tmp/`.

```powershell
.\.venv\Scripts\python.exe -m pytest tmp/e01/test_inventory_local.py --basetemp tmp/e07/pytest-e01 -o cache_dir=tmp/e07/pytest-cache
.\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_tesseract_ocr.py tests/unit/test_tesseract_runtime.py tests/unit/test_analysis_cache.py tests/unit/test_pdf_coordinates.py tests/integration/test_document_analysis.py tests/unit/test_pymupdf_orientation.py tests/unit/test_pymupdf_frames.py tests/unit/test_pymupdf_ocr_failures.py tests/unit/test_benchmark_network_pdf.py tests/unit/test_smoke_examples.py --basetemp tmp/e07/pytest-required -o cache_dir=tmp/e07/pytest-cache
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy --cache-dir tmp/e07/mypy-cache
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/client_artifact_gate.py --source-only
.\.venv\Scripts\python.exe scripts/complexity_gate.py src
$env:QT_QPA_PLATFORM='offscreen'
$env:COVERAGE_FILE='tmp/e07/.coverage-final'
.\.venv\Scripts\python.exe -m pytest --cov --cov-report=term-missing --cov-fail-under=85.01 --basetemp C:\tmp\zph-e07-final-2158 -o cache_dir=C:\tmp\zph-e07-cache-2158
.\.venv\Scripts\python.exe -m pytest 'tests/integration/test_project_http_gateway.py::test_qt_http_delayed_search_cannot_cross_input_or_connection_context[close]' -q --basetemp tmp/e07/pytest-http-retry -o cache_dir=tmp/e07/pytest-http-cache
.\.venv\Scripts\python.exe tmp/e07/tesseract_tsv_probe.py
.\tmp\e07\monitor_benchmark.ps1
.\.venv\Scripts\python.exe tmp/e07-review/compare_extraction.py
.\.venv\Scripts\python.exe tmp/e07/summarize_benchmark.py
git diff --check
Get-FileHash -Algorithm SHA256 -LiteralPath 'examples/PROJETO DE REDE 1256148225.pdf'
```

O monitor reproduz `python -m scripts.benchmark_network_pdf` com a fonte de E01, saída em
`tmp/e07/benchmark-final.json` e runtime completo `tmp/e01/runtime`; inclui cadeia semântica,
promoção, regiões/vãos e controle sintético OCR real, com SQLite novo e sem cache.
Não inclui conformidade/SQL, HTTP/jobs ou UI. Monitor de memória a cada 200 ms; high-water
Python e picos amostrados dos subprocessos possuem os mesmos limites metodológicos de E01.
A repetição final deve ocorrer sem testes ou outros processos Python concorrentes.

## Handoff

Para desbloquear E07, implementar e medir uma estratégia de recortes para os códigos pequenos
e inclinados ainda omitidos, incluindo as molduras que não iniciam os grupos atuais. Avaliar
agrupamento regional e retificação que evitem uma chamada por rótulo, com controles negativos
e correspondência geométrica por ocorrência. Corrigir a avaliação dos rótulos de identificador
sem confundi-los com os centros físicos dos pontos. Repetir inventário/benchmark real e todos
os testes, cumprindo integralmente cobertura e orçamento antes de concluir E07.

E08 permanece pendente: descarte por identificadores, catálogo, associação poste/entrega,
múltiplos condutores e continuidades fora da folha não foram corrigidos nesta etapa. A
insuficiência da extração precede essas associações e não deve ser ocultada como falha de vão.
