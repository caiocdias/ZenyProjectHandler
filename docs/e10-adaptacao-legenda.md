# E10 — Legenda local e desconhecidos revisáveis

O adapter opt-in `adapters/analysis/legend_symbols.py` lê cada PDF como uma
unidade. Procura títulos de legenda e pares desenho/descrição no texto nativo,
aceitando leituras OCR locais com caixa e origem explícitas. O exemplar visual
gerado de um par existe apenas durante a execução desse documento. Sua
assinatura inclui o SHA-256 do PDF e dos exemplares; nenhuma correção isolada
altera o inventário E01, os templates E08, outro projeto ou a reserva E16.

A busca visual devolve observações E03 para ocorrências **fora** das regiões de
legenda. A alternativa de classe é `None`: a descrição da própria legenda,
origem, revisão e incerteza de pareamento são dados para revisão, não identidade
de catálogo ou ativo confirmado. Ausência de legenda, OCR indisponível e texto
equivocado não subtraem candidatos dos outros métodos. Similaridade visual é
score bruto, sem interpretação probabilística; concordância entre métodos não
é probabilidade. O método é independente no resultado, mas compartilha raster
e código de busca com E08, portanto não representa um voto estatisticamente
independente.

Sem cabeçalho de legenda, imagens embutidas pequenas com o mesmo conteúdo
repetidas no PDF podem gerar sugestões locais sem descrição. Uma ocorrência
isolada não ensina o método. Esse fallback não cobre desenhos vetoriais
repetidos, e a origem `repeticao-imagem-local` informa que a semântica continua
desconhecida. Cabeçalho reconhecido sem par desativa o fallback; isso evita
tratar um exemplar de legenda ilegível como ocorrência operacional.

O runner E02 foi estendido com `--include-legend` e `--legend-ocr`. A opção OCR
requer a de legenda e tenta o RapidOCR local por página inteira, sem caixas
vindas do avaliador. Falhas produzem diagnósticos; o texto nativo e os demais
motores continuam. As observações desconhecidas ficam em
`predictions.json.local_candidates`, com fonte, caixa, descrição e método. O
avaliador E02 tem famílias congeladas e não atribui TP/FP globais a uma classe
local sem referência; suas `predictions` e métricas permanecem as classes E02.
A união de evidências não elimina os candidatos locais por silêncio de outro
algoritmo. E12/E14 definirão reconciliação e apresentação no produto.

Comandos de desenvolvimento e V-P:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e10-simbologia/vb-e10-final --include-raster --include-legend --legend-ocr
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e10-simbologia/vp-final --include-raster --include-legend --legend-ocr
```

O runner só congela inferência/manifesto. V-P ainda exige inspeção visual
independente das imagens originais antes das predições, comparação por
documento/página e conservação dos PDFs intactos. O handoff E10 no roadmap
registra os comandos realmente executados, hashes, casos e limitações.

No checkpoint de 24/09/2026, os testes autorais e a integração do runner
confirmaram um candidato desconhecido fora da legenda com descrição e origem
revisáveis, inclusive em página sem a legenda. V-B E02 processou 4 PDFs/6
páginas sem falha, mas seu corpus fechado não contém legenda formal positiva;
zero candidatos E10 ali não mede recall do novo método. Em V-P, a revisora
abriu 11 páginas integrais, 44 quadrantes e 9 recortes antes das predições.
Todos os 11 PDFs reais disponíveis estavam sem legenda formal; E10 produziu
zero pares e zero candidatos locais. Os 220 vetoriais do E08 foram preservados
e a comparação visual por página está em
`tmp/e10-simbologia/visual/reconciliation-final.md`. RapidOCR e OpenCV não
estavam instalados; OCR/Hough ficaram indisponíveis explicitamente. Não há
evidência real positiva de adaptação à legenda nesta coleção, nem estimativa
de recall real; os exemplos inspecionados são desenvolvimento.
