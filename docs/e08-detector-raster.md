# E08 — Detector raster por templates e Hough

O adapter opt-in `adapters/analysis/raster_symbols.py` varre a página base inteira
em tiles sobrepostos. Ele não recebe caixas do detector vetorial, OCR, ROIs do
revisor ou rótulos do benchmark. Cada tile é renderizado pelo PyMuPDF dentro de
um orçamento explícito; candidatos voltam a pontos da página e à geometria
normalizada do contrato E03. Repetições nas bordas e nas variações de escala ou
rotação são reunidas por localização, conservando tiles, variantes e alternativas
de classe na observação. Saturação ou orçamento insuficiente produzem cobertura
`FALHA`, sem transformar uma varredura parcial em conclusão.
O filtro rápido usa um conjunto de âncoras escuras suficiente para preservar
todo candidato que passaria o limiar amostrado, inclusive quando um pixel da
figura se perde. Um orçamento de propostas excedido sinaliza falha parcial.
Os testes incluem rotação do próprio PDF: a caixa visual é desrotacionada para
o sistema original da página e a matriz inversa recompõe os pontos originais.

## Fonte e alcance

Os dois templates distribuídos nesta etapa são **controles autorais** de
`ATERRAMENTO` e `PARA_RAIOS_MT`, derivados dos segmentos públicos de
`tests/symbol_benchmark_fixtures.py`. Cada um tem identidade e SHA-256 próprios
no perfil do método. Não reproduzem a arte da IT-EO-008 nem homologam variantes
CEMIG. O registro E01 continua a identificar famílias e variantes; um template
novo precisa de imagem, procedência e revisão verificáveis antes de entrar no
adapter. O perfil e o manifesto do runner registram os hashes efetivamente
usados. Os PDFs reais em `examples/` continuam somente como desenvolvimento.

O correlator binário funciona com PyMuPDF e Pillow, disponíveis no ambiente local.
`raster-hough-generalizado` ensaia Generalized Hough Ballard via OpenCV, quando
`cv2` estiver disponível. OpenCV não é dependência do runtime padrão atual; se
ausente, o método devolve `INDISPONIVEL` com motivo. Correlação e Hough
compartilham raster e templates, logo suas saídas não são votos independentes.
Similaridade e votos Hough são scores brutos, sem interpretação probabilística.
O checkpoint local usou Python 3.13.14, PyMuPDF 1.28.0 e Pillow 12.2; `cv2` e
NumPy não estavam instalados na `.venv`. A assinatura distingue versões das
bibliotecas, DPI, tiles, sobreposição, escalas, rotações, limites, thresholds
efetivos e hashes dos templates.

## Execução e comparação

O comando E02 sem opções conserva o baseline legado. A opção nova ativa raster:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e08-simbologia/benchmark-a5 --include-raster
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e08-simbologia/vp-raster-a5 --include-raster
```

O avaliador E02 conserva exclusivos na união bruta; sua equivalência entre
métodos exige classe, contexto e caixa exatamente iguais. Caixas quase
coincidentes de uma mesma ocorrência podem aparecer como FP de duplicata na
união de controle. Associação física, contexto de legenda e política de
promoção pertencem a E10–E13. A projeção raster para o esquema E02 usa a classe
primária e mantém alternativas e scores brutos em `provenance`.
O tempo no manifesto inclui toda a varredura. Para manter o custo da auditoria
viável, o runner suspende seu `tracemalloc` durante a busca raster; portanto
`python_peak_bytes` cobre apenas a parte fora dessa busca e não representa o
pico de memória do processo. O adapter impõe limites próprios para tiles e
candidatos; o teste de orçamento valida o estado `FALHA` quando o limite é
insuficiente.

## Evidência e limites

No desenvolvimento sintético A5, 4 PDFs/6 páginas, o legado produziu
11 TP/1 FP/11 FN; o template raster, 9 TP/1 FP/13 FN; a união bruta,
13 TP/9 FP/9 FN. `dev-raster-p1-o00` e `dev-raster-p1-o01` são TP exclusivos do
raster em PDF sem desenhos vetoriais. A união E02 ainda contabiliza caixas
quase coincidentes dos dois métodos como duplicatas de controle. Não
interpretar os 22 FN que o avaliador atribui ao Hough indisponível como recall
medido do método. O FP de legenda do raster é uma limitação registrada; o
adapter não infere contexto operacional a partir da forma isolada.
O checkpoint A4 foi rejeitado porque uma página com foto densa excedeu o
orçamento de propostas. Em A5, o filtro rápido calcula em operações nativas
do Pillow as mesmas contagens amostradas de pixels escuros e claros antes
de contabilizar propostas. A página problemática passou de 136 s e cobertura
`FALHA` para 66 s e `NAO_DETECCAO` completo; um controle raster todo preto
também passou sem falsos candidatos. A comparação diferencial de 5.760
janelas válidas não encontrou divergências no predicado de triagem.

No V-P local A5, os 11 PDFs e 11 páginas foram processados sem falha. A
inspeção visual independente abriu 66 imagens originais antes das predições e
23 folhas de contato depois. O vetor emitiu 220 candidatos; o template raster
emitiu zero e Hough ficou indisponível por ausência de OpenCV. A união preservou
os 220 vetoriais. Há falsos positivos vetoriais claros e símbolos de terra
visíveis que estes templates não recuperaram. Todos os PDFs reais disponíveis
contêm redes vetoriais, portanto a coleção não testa diretamente recuperação
em raster puro e não sustenta precisão ou recall real do método raster. O
relatório [V-P](../tmp/e08-simbologia/visual/reconciliation-a5.md) localiza
esses casos e separa as ambiguidades. A inferência combinada levou 552,19 s
somados nos 11 documentos (máximo 142,92 s em uma página); otimização de
desempenho permanece uma pendência para coleções maiores.

Os comandos e resultados V-S/V-N/V-Q, a auditoria V-P de todas as páginas,
o checkpoint, os hashes e as pendências constam no handoff E08 do
[roadmap](roadmap-analise-simbologia.md).
