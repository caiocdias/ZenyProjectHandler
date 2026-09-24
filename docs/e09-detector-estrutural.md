# E09 — Contornos e grafo visual de traços

O adapter opt-in `adapters/analysis/structural_symbols.py` produz observações
E03 de `ATERRAMENTO` e `PARA_RAIOS_MT` a partir de uma gramática **autoral** de
haste e três/quatro barras. Ele não representa as 427 variantes do inventário
E01 nem afirma equivalência com desenhos normativos. O grafo descreve apenas
geometria visual; não é transmitido ao construtor de topologia elétrica, não
promove ativo e não cria junções elétricas.

## Entradas, grafo e limites

`observar_simbolos_estruturais` aceita `ConfiguracaoDetectorEstrutural` com
`entrada="raster"` ou `"vetor"`. A primeira renderiza a página base, encontra
traços horizontais e verticais por corridas de tinta binária e consolida traços
fragmentados. Para cada proposta raster, afina a tinta da região local em duas
fases Zhang-Suen. A contagem de extremidades/junções do esqueleto participa
do aceite, e ramificações excedentes penalizam o score bruto. O recorte vem
apenas da proposta do algoritmo, limitado a 16.384 pixels e ao orçamento de
expansões; não recebe ROI nem referência do revisor. A segunda entrada extrai
linhas dos desenhos PyMuPDF sem invocar o detector legado. A busca usa índices
locais para procurar haste, barras em sequência e espaçamento/altura
compatíveis. O candidato conserva número de extremidades, junções visuais e
ciclos do seu suporte local. Isso compara estrutura e relações de forma, sem
correlação de patches de pixels e sem as heurísticas de classe do detector
legado. O [material F05 da OpenCV sobre
contornos](https://docs.opencv.org/4.13.0/d5/d45/tutorial_py_contours_more_functions.html)
fundamenta a alternativa de comparação de formas; esta implementação usa
PyMuPDF e Pillow já presentes, sem exigir OpenCV.

Pixels, traços e expansões têm orçamentos explícitos. Excedê-los retorna
`FALHA` com motivo, nunca `NAO_DETECCAO` ou sucesso parcial. O runner E02
ativa as duas entradas somente com `--include-structural`; o baseline sem a
opção permanece legado. No runner, ambas usam 72 DPI e limite de 5 milhões de
pixels para cobrir as páginas A1 locais. A API direta usa 144 DPI e 4 milhões
de pixels por padrão. Os perfis assinam essa diferença. A resolução menor
pode perder barras finas, portanto resultados de 72 e 144 DPI não são tratados
como votos independentes. Raster estrutural e E08 compartilham a origem de
rasterização; vetor estrutural e E04 compartilham `get_drawings`. A família
algorítmica estrutural é distinta em ambos os casos, mas origem compartilhada
impede inferir independência estatística. O token de origem raster comum
`pymupdf:rgb-page-tiles:e08` marca essa correlação: E09 renderiza a página
inteira em cinza, enquanto E08 usa tiles RGB; os bytes e as resoluções não
são idênticos. A nomenclatura do token é uma limitação documental da versão.
Scores são ajuste bruto da gramática, sem calibração probabilística.

## Controles e benchmark de desenvolvimento

O teste autoral `tests/unit/test_structural_symbols.py` reproduz uma haste
quebrada e deformada em PDF puramente raster: E09 em 144 DPI encontra um
aterramento com caixa completa (início x=42), enquanto legado e E08 não
retornam candidato. Outro controle inclina levemente a figura e varia a
espessura: o esqueleto local recupera a classe; a ablação de sua junção remove
a detecção. Há controles de três/quatro barras semelhantes, peças separadas,
figura negativa sem afunilamento, falha em grafo denso e invariância do
construtor de vãos elétricos.
Este exclusivo é um controle de desenvolvimento e não comprova ganho em campo.

| Método no V-B E02, 4 PDFs/6 páginas | TP | FP | FN | TP exclusivo entre os métodos executados |
|---|---:|---:|---:|---:|
| Legado vetorial | 11 | 1 | 11 | 2 |
| Template E08 | 9 | 1 | 13 | 2 |
| Hough E08 | indisponível | — | — | — |
| Grafo E09 raster, 72 DPI | 3 | 0 | 19 | 0 |
| Grafo E09 vetor | 7 | 2 | 15 | 0 |

A união bruta E02 preservou 13 TP/13 FP/9 FN no ensaio com E08 e E09, ante
13 TP/9 FP/9 FN com E08 sem E09. Os FP adicionais incluem caixas quase
coincidentes que o avaliador E02 conta como duplicatas por exigir igualdade
exata; E12 ainda definirá associação física. O resultado não autoriza ativar
E09 para promoção automática. O exclusivo deformado do teste foi medido a
144 DPI e não está no corpus E02 de 72 DPI.

Na auditoria local V-P do checkpoint A1, `e09-stroke-graph-1` processou os 11 PDFs
recursivos e suas 11 páginas, sem falhas de execução. Houve 220 candidatos
legados, **três do grafo vetorial e zero do grafo raster**. O revisor examinou
as imagens originais antes das predições e depois ampliou as três regiões
estruturais. As três caixas recaem sobre marcadores de cerca/divisa:
`5 FL DIVISA` em `1251386294` e `CERCA DIVISA`/`4FF` em `1256407599`.
São três FP de classe/localização, todos também emitidos pelo legado como
aterramento na mesma região (IoU 1,00/0,99/0,94). Assim o erro é compartilhado
pela entrada vetorial; a forma diferente do algoritmo não produziu ganho real
comprovado nesta coleção. A entrada raster concluiu a varredura em 72 DPI, mas
seus zero candidatos não demonstram ausência dos símbolos físicos. O relatório
visual em `tmp/e09-simbologia/visual/` preserva ambiguidades e omissões
identificáveis sem inventar verdade-terreno completa.

No checkpoint A2 `e09-stroke-graph-2`, o esqueleto real foi integrado ao
reconhecimento raster. V-P repetiu 11/11 páginas, zero falhas; a comparação
congelada encontrou zero candidatos espaciais novos/removidos. Os três FP
vetoriais e as duas omissões visuais mínimas permaneceram; o raster emitiu
zero. Os 220 candidatos legados foram idênticos aos A1/E08. A inspeção A2
reabriu os três recortes de FP e os dois de omissão e reutilizou as 11 imagens
originais pela identidade SHA-256 das fontes, sem alegar nova leitura cega.

**Decisão experimental final:** rejeitar a adoção de E09 na composição operacional
neste checkpoint A2. A implementação segue apenas opt-in para diagnóstico. A
ação de melhoria é construir controles autorais de marcadores de cerca/divisa,
acrescentar discriminação estrutural/contextual e medir resolução adaptativa
para entrada raster; uma versão nova deverá repetir V-N, V-B e V-P antes de
qualquer ativação. O acerto exclusivo sintético justifica a investigação, mas
não compensa os três FP reais ou valida precisão de campo.

Comandos de desenvolvimento e V-P:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e09-simbologia/baseline-a2
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e09-simbologia/structural-a2 --include-structural
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e09-simbologia/comparison-a2 --include-structural --include-raster
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e09-simbologia/vp-a2 --include-structural
```

O runner grava predições antes de qualquer referência/revisão. O corpus
sintético reservado permanece lacrado até E16. A auditoria visual V-P e as
decisões de FP/FN da coleção local ficam no handoff do roadmap e em
`tmp/e09-simbologia/visual/`. Esses PDFs são desenvolvimento, não teste cego.

## Limitações e ação seguinte

A gramática atual ignora curvas, ângulos maiores que a tolerância axial,
para-raios BT, transformadores e pacotes E07. A entrada raster a 72 DPI pode
perder formas pequenas; a vetorial depende da existência e fidelidade dos
desenhos do PDF. Uma revisão futura de E09 deverá avaliar descritores locais
mais discriminantes e regiões com resolução adaptativa. A associação de
observações pertence a E12 e não pode transformar concordância em probabilidade
ou silêncio de outro método em veto. Qualquer ampliação de classes requer
figuras de referência verificadas e novos controles negativos.
