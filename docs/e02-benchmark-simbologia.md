# E02 — Benchmark de cobertura e complementaridade

Este benchmark mede o detector simbólico vetorial legado e a correção do avaliador
independente. O [contrato](e02-contrato-benchmark-simbologia.md) fixa o formato,
pareamento e responsabilidades; o [roadmap](roadmap-analise-simbologia.md) registra
o aceite e as validações executadas. Não modifica detectores nem política de
promoção da aplicação.

## Protocolo congelado

Documento, página (base 1), camada e classe precisam coincidir para um TP.
O pareamento é um-a-um: repetir uma predição não aumenta TP. IoU mínimo 0,5;
símbolos finos também admitem o critério de extremos do contrato. O relatório
mantém o critério usado, geometria e IDs dos pares, FP, FN e duplicatas.

O denominador operacional confirmado é separado de ambiguidades e de exemplos
em legenda, tabela ou contexto informativo. Classes sem referência avaliável
têm recall nulo e denominador zero; isso não significa cobertura de 100%.
As 33 famílias E01 continuam na matriz mesmo quando não têm fixtures nesta versão.
Cobertura do inventário de 427 variantes e cobertura de ocorrências de benchmark
são medidas distintas.

A união conserva candidatos exclusivos. Equivalências exatas entre métodos
podem compartilhar uma ocorrência de avaliação, mantendo as observações; caixas
próximas não são justificativa para fundir objetos distintos. A interseção existe
apenas como controle. Enquanto não existe política de filtragem/fusão E12,
`filtered_union` e `final` são aliases declarados da união de benchmark.
Acertos exclusivos, FP exclusivos, erros compartilhados e ablações identificam
contribuições; não convertem concordância em probabilidade.

Os controles A/B com saídas conhecidas verificam a matemática da avaliação.
Eles não são detectores implementados, nem demonstram ganho real de uma futura
composição. O único método visual de baseline é o legado de aterramento e
para-raios MT/BT. Seu score fixo 0,88 permanece bruto. Brier/ECE só são cabíveis
com probabilidade explicitamente calibrada; ausência de calibração ou amostra
insuficiente precisa aparecer no relatório.

## Execução portátil e dados

O runner sintético não depende de `examples/`, rede, OCR ou modelos externos.
Dados autorais ficam em `tests/fixtures/symbols/`, com partições de desenvolvimento,
calibração e reserva por ancestral e família de desenho. Derivados não atravessam
partições. A reserva é um lacre operacional com hashes, sem alegação de criptografia;
não é aberta, inspecionada nem avaliada até E16. Suas metas continuam as do roadmap:
recall de candidatos e precisão final >=95% por família avaliável, com os negativos
críticos e demais condições do gate. E02 mede o baseline, sem exigir que o detector
legado já alcance as metas de E16.

Inferência e avaliação são comandos/fronteiras separados. O detector recebe só
o PDF e configuração fixa, nunca os rótulos ou ROIs do avaliador. O gerador roda
em subprocesso, e o runner grava predições antes de carregar a referência para
medição. A CLI abaixo foi confirmada com `--help` e executada na integração.

```powershell
# V-B: gera corpus autoral, infere legado e avalia desenvolvimento.
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e02-simbologia/baseline-final

# V-P: todos os PDFs/páginas; não faz inspeção visual por conta própria.
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e02-simbologia/predictions

# Avaliação independente das predições congeladas, sem nova inferência.
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols evaluate --reference tmp/e02-simbologia/baseline-final/reference.json --predictions tmp/e02-simbologia/baseline-final/predictions.json --output tmp/e02-simbologia/integracao/re-evaluation.json
```

Cada diretório de execução conserva `manifest.json` e `predictions.json`;
V-B acrescenta corpus, referência e `report.json`. O manifesto inclui hashes,
assinaturas, configuração, tempos, falhas e memória de alocações Python via
tracemalloc (não RSS nem memória nativa MuPDF). O mapa `documents` das predições
vincula IDs aos SHA-256 das fontes; referência divergente é recusada. Ausência de
PDFs termina com estado `no_examples`, `completed=false` e exit 1; não é aprovação.

## Baseline público medido

O [snapshot público](data/benchmark-simbologia-e02-baseline.json) contém método,
predições e relatório integral, sem tempos variáveis por execução. SHA-256:
`fd30cb3fa3cbe34e86b36660b5d794b6c3a6ec371849166188c6d9bcc1d5eeae`.
As [partições e limitações dos dados](e02-dados-benchmark-simbologia.md) documentam
o seed 20260918 (sem aleatoriedade), hashes e reserva lacrada.

Medição de desenvolvimento: **4 PDFs/6 páginas**, 27 registros (22 operacionais
confirmados, um ambíguo, uma legenda, três negativos), 33 famílias no denominador,
9 predições. Apenas quatro famílias têm positivos operacionais nesta versão.

| Classe | Referências operacionais | TP | FP | FN |
|---|---:|---:|---:|---:|
| Aterramento | 9 | 0 | 6 | 9 |
| Para-raios MT | 3 | 0 | 2 | 3 |
| Para-raios BT | 3 | 0 | 1 | 3 |
| Transformador | 4 | 0 | 0 | 4 |
| Estai MT | 3 | 0 | 0 | 3 |
| **Micro** | **22** | **0** | **9** | **22** |

Esses são acertos **com localização**, pelo protocolo fixo; não significam que
nenhum nome de classe plausível foi emitido. O legado usa união de `pymupdf.Rect`
em primitives de área zero em `_union_bounds`: algumas caixas ficam reduzidas
à haste; a de BT pode conter só o corpo. O avaliador preservou essas geometrias
e registrou FP/FN, sem ajustar detector ou tolerâncias. O controle de legenda tem
um FP identificado por contexto; não alegar zero FP nos negativos críticos.
E04 deve investigar a geometria emitida antes de ampliar o reconhecimento.

A reprodução em cópia mínima de seis arquivos de benchmark/gerador, sem
`examples/` nem reserva, usando as bibliotecas já instaladas na `.venv`, gerou
referência, predições e relatório idênticos após excluir apenas tempos.
Hash das observações: `ff493710564319ffa02a4a5589a81463bfc1cc16c256f489c697a84fe4580cfc`.
Evidência local: `tmp/e02-simbologia/integracao/reproducibility.json`.
Os PDFs foram reproduzidos com PyMuPDF 1.28.0; bytes idênticos entre versões da
biblioteca não foram prometidos.

O controle-oráculo tem A=1 TP/1 FN e B=1 TP/1 FN; união=2 TP/0 FN e
interseção=0 TP/2 FN. Duplicatas de A não aumentam TP, mesmo com apoio de B.
No baseline real só há um detector: união/final coincidem com ele e não há ganho
de complementaridade real para afirmar. O único ancestral sintético de
desenvolvimento não sustenta intervalo de generalização; score 0,88 não tem
calibração. Famílias com denominador zero permanecem com recall `null`.

## Auditoria local V-P

V-P descobre recursivamente todos os PDFs em `examples/` e todas as páginas.
O manifesto preserva cada caminho, hashes antes/depois, dimensões, falhas e
configuração. Arquivos e relatórios privados permanecem em `tmp/e02-simbologia/`.
Coleção vazia é ausência de avaliação real, nunca aprovação visual.

O revisor examina primeiro imagens originais, base e aparência anotada, com tiles
que cubram também regiões sem detecção. Congela observações antes de comparar as
predições. O runner não faz revisão visual por conta própria. A matriz final
reconcilia documento, página, método e camada; camada não suportada tem motivo
explícito. Achados de IA são evidências revisáveis: ambiguidades não contam como
acertos/erros certos, e os denominadores provisórios não se confundem com a
verdade autoral das fixtures sintéticas.

Uma referência declarada `annotation_scope="partial"` é recusada pelo avaliador
global. Em V-P, a referência localizada por IA é parcial: a comparação visual
registra cada predição, FP/ambiguidades e FN localizados, com denominadores
provisórios; recall populacional permanece não avaliado. Ausência de anotação
fora das ROIs não comprova FP nem ausência de símbolo.

Todos os exemplos já examinados são desenvolvimento/diagnóstico. As medições
locais não estimam generalização de campo, e a auditoria não certifica projeto,
vigência normativa, quantidade patrimonial nem interpretação integral do PDF.

### Execução local de 18/09/2026

**11 PDFs/11 páginas**, zero falha de inferência, fontes intactas e **159 candidatos
inspecionados**. Antes das predições, o revisor viu 154 imagens de base/aparência
e 27 recortes originais; depois examinou os 159 recortes em 20 folhas de contato,
com quatro ampliações individuais adicionais. A matriz tem 22 células: 11 bases
executadas e 11 camadas de anotação inspecionadas, porém não suportadas pelo método.

| Decisão visual por candidato | Quantidade |
|---|---:|
| Classe visualmente plausível, sem aprovação geométrica | 118 |
| FP localizado, incluindo falha de localização | 22 |
| Ambíguo | 15 |
| Não avaliável semanticamente, mas inspecionado | 4 |

Os 22 FP incluem cinco posições reportadas vazias, duas caixas incompletas com
classe plausível e 15 gráficos não operacionais. Há sete caixas degeneradas.
A referência anterior às saídas permite registrar 30 FN mínimos provisórios
localizados: sete aterramentos, sete MT e 16 BT. Outras 16 hipóteses legíveis de
transformador estão fora das classes do método. Esses resultados são achados de
IA revisáveis, com imagens e IDs; **precisão estrita e recall global são null**.
Nenhuma duplicata adicional foi identificada. Com um método, todos os candidatos
são exclusivos de maneira trivial e o ganho empírico da união continua null.

Evidências locais em `tmp/e02-simbologia/visual/relatorio-vp.md`,
`prediction-review.json`, `matrix.json` e `review-artifact-hashes.json`.
O [handoff do roadmap](roadmap-analise-simbologia.md#e02--benchmark-de-cobertura-e-complementaridade--concluida)
registra delegações, verificação independente, hashes, comandos e limitações.
A referência inicial congelada tem SHA-256
`219f11304fc137dd456a6fc0fcc0512412b55ec493ebd3f5ab92a2c781f86104`;
a revisão estruturada, `30efb7bc322af5cb0148acdcc9d4912a4df9fc16226f52c3d9f9248643083b72`.

```powershell
# Integridade e reconciliação; não substituem a inspeção real das imagens.
.\.venv\Scripts\python.exe tmp/e02-simbologia/visual/verify_visual.py
.\.venv\Scripts\python.exe tmp/e02-simbologia/integracao/verify_final_checkpoint.py
```

Ambos passaram. A integração também confirmou que `reference-partial.json` é
recusada pelo avaliador global. Os scripts/artefatos privados de auditoria ficam
em `tmp/`, sem se tornar dependência do gate portátil. E03 pode usar as saídas
congeladas para conferir o round-trip; o problema de localização segue para E04.
