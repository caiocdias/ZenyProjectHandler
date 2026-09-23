# E05 — Reconhecimento visual de transformadores

Implementação da etapa E05 do [roadmap](roadmap-analise-simbologia.md). O método
vetorial novo fica em `adapters/analysis/pymupdf_transformers.py` e retorna o
contrato interno E03 por `perfil_transformadores()` e
`observar_transformadores(page, documento_id=..., documento_sha256=...,
pagina_numero=...)`. O consumidor patrimonial em `category_analyzers.py` permanece
para E13: E05 produz observações, sem promover ativos.

## Decisões do contrato

- A forma é detectada sem exigir literal. Texto próximo é evidência separada;
  incompatibilidade é conservada como alternativa/conflito, sem trocar a
  geometria observada.
- Uma forma composta contém componentes com suporte vetorial rastreável, mas
  não ganha quantidade de ativos pela contagem de círculos, enrolamentos ou
  partes. `cardinalidade` é indeterminada e `quantidade_ativos` é `None`.
- Situação, potência, fases, modelo e uso não são inferidos da forma isolada.
  IDs do inventário E01 graficamente indistinguíveis permanecem em
  `referencias_possiveis` e exigem revisão.
- O método informa perfil/assinatura próprios e fontes de drawings
  compartilhadas com E04. Seus scores brutos não são probabilidades e não
  atravessam o corte legado de `confianca_minima`.
- O runner E02 recebe `--include-transformers` como opção. O modo padrão
  continua reproduzindo o baseline legado; com a opção, salva observações dos
  dois métodos e a união rastreável, sem usar silêncio de um como veto do outro.

## Validação

O corpus portátil E05 em `tests/fixtures/transformers/fixtures.py` é autoral,
independente da implementação, e contempla todos os 29 IDs E05 do inventário,
além de duplicação, vizinhos, legenda, texto conflitante, rotação/escala e
negativos de círculos/postes/glifos. Um segundo PDF autoral B3 contém três
negativos geométricos adicionais e dois setores ciano vetoriais em escala menor
ou parcialmente cobertos. Um terceiro PDF autoral B4 acrescenta três negativos
de círculos com hastes sem espiras e um positivo com enrolamentos circulares
conectados. Um quarto PDF B5 inclui discos preenchidos negativos e laços
vazados positivos para controlar o tratamento do preenchimento. O benchmark
E05 constrói os quatro PDFs e uma referência conjunta em processo separado,
persiste predições antes de ler a referência e mantém a
reserva E16 lacrada.

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_transformers_e05 --output tmp/e05-simbologia/benchmark-final
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --output tmp/e05-simbologia/baseline-final
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --output tmp/e05-simbologia/predictions
```

Os comandos e resultados dos gates V-S, V-N, V-Q, V-B e V-P, checkpoints
rejeitados, hashes, autoria por arquivo e auditoria visual independente ficam
no handoff E05 do roadmap. Os PDFs locais já inspecionados são desenvolvimento;
nenhum resultado desta etapa é uma medida cega de generalização de campo.

No checkpoint A7 (`e05-transformadores-v4`), V-S, V-N, V-Q e V-B passaram:
29/29 variantes e 39 TP/0 FP/0 FN nos quatro PDFs autorais. O V-P cobriu os
11 PDFs e 11 páginas de `examples/`; a revisão visual independente reabriu
17/17 candidatos E05, com 14 formas plausíveis, três ambiguidades e nenhum
FP/FN vetorial seguro. Uma forma em quadro de detalhe ainda exige revisão de
contexto e associação. Um transformador ciano sem saída está em faixa raster
embutida, registrado para E08; o método vetorial E05 não cobre esse conteúdo.
O relatório verificável está em `tmp/e05-simbologia/visual/comparison-a7.md`.
