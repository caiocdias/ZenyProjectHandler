# E12 — União e calibração de símbolos

O reconciliador interno está em `application/symbol_reconciliation.py`. Ele recebe
resultados E03 já produzidos pelos métodos, preserva cada observação e retorna
ocorrências, matriz método × ocorrência e ablações. Não altera o reconciliador
documental de coordenadas `application/method_reconciliation.py`, o DTO público,
o consumidor semântico nem a promoção automática (E13–E15).

## Contrato e decisão

- A associação exige documento e SHA, página, camada, contexto gráfico e
  compatibilidade geométrica. Primitivas compartilhadas ajudam quando existem;
  caixas vizinhas sobrepostas não bastam. Uma geometria original é selecionada
  por integridade e procedência; WBF não foi adotado porque não houve evidência
  de ganho frente ao risco de criar uma caixa entre objetos próximos.
- Uma ocorrência conserva observações, alternativas de classe e os IDs de
  referência possíveis (`reference_ids`), score bruto de cada saída, suporte por
  assinatura e probabilidade calibrada em campos distintos. Dois IDs E07 para
  a mesma forma, ou várias referências E05 para um transformador, exigem
  discriminante verificável antes de resolver o ID exato.
  Classes/IDs incompatíveis, legenda, variante `pending` e conflito técnico
  permanecem em revisão. Silêncio, não detecção e falha são estados de cobertura,
  não votos contra a presença física.
- `CalibrationPolicy` usa uma célula por assinatura do método, classe e estrato.
  A política desta etapa exige pelo menos 30 amostras nessa célula e
  probabilidade calibrada ≥0,99 para elegibilidade, sem conflito. Entre células
  aplicáveis a uma ocorrência, seleciona a de maior amostra e expõe o método
  de origem; não calcula média, produto, maioria nem transforma score bruto em
  probabilidade. Elegibilidade aqui é interna: E13 decidirá campos e promoção.
- A partição de calibração E02 disponível tem **2 PDFs, 2 páginas e 4 positivos
  operacionais**; a inferência completa emitiu 1 candidato, TP do método E05,
  sem FP. Nenhuma célula por método/classe/estrato atinge 30 amostras. A política
  real, portanto, tem `entries=[]` e mantém todas as ocorrências em revisão.
  Os testes de política injetam células autorais suficientes apenas para provar
  o ramo de exclusivo elegível; não são estimativas empíricas.

## Métodos e medição

O benchmark E02 executou E04 legado, E05, E06, os 21 pacotes E07 habilitados
no snapshot de 27 pacotes/365 variantes (344 continuam `pending`), E08,
E09 e E10. E09 foi medido como controle experimental e excluído da composição
adotada pela rejeição documentada na própria etapa; E11 permanece isolado em
`scripts/experiments/` pela rejeição documentada. O E08 Hough indisponível
permanece com estado explícito. E10 não gerou candidato local nas fixtures.

O comando `scripts.reconcile_symbol_benchmark` lê predições congeladas,
materializa `composition.json` **antes** de abrir a referência e só então gera
`evaluation.json`. O adaptador reconstrói caixas normalizadas para essa medição;
o reconciliador de produção recebe diretamente os tipos E03. Todo ID de
observação de método adotado deve aparecer exatamente uma vez na composição,
verificado pelo runner. `class_id` incerto permanece `null`; a métrica de classe
exata o exclui e publica a quantidade, preservando o candidato revisável no JSON.

| Desenvolvimento E02, 4 PDFs/6 páginas/22 positivos | TP | FP | FN |
|---|---:|---:|---:|
| União bruta de todos os métodos medidos, inclusive E09 | 16 | 15 | 6 |
| União bruta dos métodos adotados | 16 | 11 | 6 |
| Composição E12, somente classe exata resolvida | 14 | 4 | 8 |

A composição contém 27 observações adotadas em 27 ocorrências e nove
ocorrências com alternativas de classe. Os dois TP que saem da métrica de
classe exata continuam como candidatos com alternativas e revisão; não são
supressões. Não houve fusão de duas saídas distintas nesse corpus após o corte
experimental. A associação e a prevenção de fusão indevida têm controles
independentes nos 25 testes da etapa. Esta partição não prova generalização
real nem elegibilidade automática.

## Validação local e limites

Comandos de E12, na raiz, usando a `.venv` e saídas sob `tmp/e12-simbologia/`:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e12-simbologia/benchmark-development --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root tmp/e11-simbologia/data/calibration --output tmp/e12-simbologia/benchmark-calibration --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend
.\.venv\Scripts\python.exe -m scripts.experiments.e11_calibration_ids --raw tmp/e12-simbologia/benchmark-calibration/predictions.json --output tmp/e12-simbologia/benchmark-calibration/predictions-bound.json
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols evaluate --reference tmp/e11-simbologia/data/calibration/reference.json --predictions tmp/e12-simbologia/benchmark-calibration/predictions-bound.json --output tmp/e12-simbologia/benchmark-calibration/report.json
.\.venv\Scripts\python.exe -m scripts.reconcile_symbol_benchmark --predictions tmp/e12-simbologia/benchmark-development/predictions.json --output tmp/e12-simbologia/composition-development --reference tmp/e12-simbologia/benchmark-development/reference.json --exclude-method structural-raster-graph --exclude-method structural-vector-graph
.\.venv\Scripts\python.exe -m scripts.reconcile_symbol_benchmark --predictions tmp/e12-simbologia/benchmark-calibration/predictions-bound.json --output tmp/e12-simbologia/composition-calibration --reference tmp/e11-simbologia/data/calibration/reference.json --exclude-method structural-raster-graph --exclude-method structural-vector-graph
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e12-simbologia/benchmark-examples --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend
.\.venv\Scripts\python.exe -m scripts.reconcile_symbol_benchmark --predictions tmp/e12-simbologia/benchmark-examples/predictions.json --output tmp/e12-simbologia/composition-examples --exclude-method structural-raster-graph --exclude-method structural-vector-graph
```

Os exemplos reais são dados de desenvolvimento já expostos. O protocolo V-P
exige inspeção visual das imagens originais antes da comparação com predições e
uma matriz completa por PDF, página, método e camada; o runner sozinho não a
fornece. A reserva sintética `reserve.sealed.zip` fica lacrada até E16.

A inferência V-P do checkpoint final completou 11 PDFs/11 páginas, com zero
falhas de documento ou página e SHA das fontes antes/depois idênticos. Emitiu
240 predições: 220 legadas, 17 E05 e três E09 experimentais; E06, E07, E08 e
E10 não emitiram candidatos. A composição adotada contém 237 observações em
237 ocorrências revisáveis, 1.659 linhas da matriz e sete ablações; nenhuma
observação foi descartada. O confronto visual independente por IA fica no
relatório privado `tmp/e12-simbologia/visual/` e no handoff do roadmap, com
FP/FN e ambiguidades separados de métricas sintéticas.

A auditoria V-P abriu 11 panoramas e 44 tiles **antes** de ler as predições;
depois reabriu 23 contatos das 220 caixas legadas, oito contatos dos 17 E05,
três recortes E09 e recortes de omissões. O confronto de registros completos
confirmou identidade de 220/220 saídas legadas com E10, 17/17 E05 com A7 e
3/3 E09 com A2. O relatório contém 198 células de execução por página, método
e camada, além dos IDs, caixas e imagens dos achados localizados. Das 17 saídas
exclusivas E05, 14 são formas plausíveis e três são ambíguas; todas seguem na
união e em revisão. Os três E09 rejeitados são FP; há FP legados e omissões
visuais de terra no template e de um transformador raster no poste P2 de
`1251985467`. A amostra real não tem gabarito exaustivo nem sobreposição
entre métodos adotados; portanto não mede precisão, recall ou deduplicação
real da E12. Os controles V-N/V-B exercitam a associação e os conflitos.

V-N integrado: `pytest tests/unit/test_symbol_reconciliation.py
tests/unit/test_method_reconciliation.py tests/unit/test_benchmark_symbols.py
tests/unit/test_symbol_observations.py
tests/unit/test_declarative_symbol_packages.py -q` → **180 passed**. V-Q:
`ruff check .`, `ruff format --check .` e `mypy` passaram (420 arquivos
formatados, 384 verificados por tipos). `git diff --check` passou. O comando
extra `mypy .` encontrou o módulo duplicado `scripts` sob
`tmp/e02-simbologia/integracao/portable-workspace`; o comando prescrito
`mypy` usa a configuração do projeto e passou.
