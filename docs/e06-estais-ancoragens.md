# E06 — Estais e ancoragens

Etapa E06 do [roadmap](roadmap-analise-simbologia.md). O método vetorial
`adapters/analysis/pymupdf_guys.py` produz observações internas E03 de relações
mecânicas. Ele não cria `Cabo`, vão, junção elétrica ou dimensionamento de estai.

## Contrato

`perfil_estais()` descreve a versão e o escopo do método.
`observar_estais(page, documento_id=..., documento_sha256=...,
pagina_numero=...)` observa a base de uma página e devolve
`ResultadoMetodoSimbolos`. A classe aberta é `ESTAI`; o traçado é uma
`POLILINHA`, com primitivas de origem e componentes preservados.

As alternativas representam subtipo gráfico e referências E01 possíveis.
Quando forma, texto ou suporte não permitem separar MT/AT, subtipo ou situação,
essa incerteza permanece na observação. `suportes_possiveis` descreve posições
e papéis geométricos, sem identificar suportes físicos ou conectar a rede.
`vinculo=mecanico_possivel`, `conectividade_eletrica=False` e cardinalidade
indeterminada impedem a interpretação da observação como um vão elétrico.

O runner E02 expõe `--include-guys` somente como método opt-in. Sua projeção
preserva traçado, alternativas, referência, suporte e assinatura, sem calibrar
score bruto ou exigir concordância com outro detector. O silêncio de outro
método não veta um estai. O consumidor patrimonial e a promoção continuam
fora desta etapa.

## Dados e validação

O inventário E01 contém 17 células CEMIG EO revisão 3 em §14 e §15. Células
de situação e MT/AT podem compartilhar a mesma assinatura visual; o teste
por variante exige observação e preservação da referência possível, sem
presumir 17 formas geométricas distintas. Fixtures autorais em
`tests/fixtures/guys/` verificam âncora bifurcada, cruzeta-cruzeta, poste a
poste, cruzeta-poste, seccionamento, tracejado, sobreposição, vizinhos e
negativos de condutor, cerca, cota, líder, rosa dos ventos, contorno fechado,
corredor sólido/tracejado e texto isolado.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_guys.py tests/unit/test_benchmark_symbols.py tests/unit/test_e14_topology.py
.\.venv\Scripts\python.exe -m scripts.benchmark_guys_e06 --output tmp/e06-simbologia/benchmark-a7-b11
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --output tmp/e06-simbologia/baseline-a7
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --output tmp/e06-simbologia/predictions-a7
```

O benchmark autoral grava predições antes de ler referência, usa o avaliador
E02 sem alterar tolerâncias e não abre a reserva sintética E16. A inspeção V-P
de todos os PDFs e páginas em `examples/` é uma revisão visual separada do
runner; os exemplos inspecionados são dados de desenvolvimento. Resultados,
checkpoints rejeitados, hashes, comandos finais e limitações constam no
handoff E06 do roadmap. Artefatos privados ficam em `tmp/e06-simbologia/`.

No checkpoint final, V-B cobriu 17/17 variantes e obteve 33 TP, 0 FP e 0 FN
em 67 páginas autorais; os testes E06/E14 e do runner passaram. V-P examinou
os 11 PDFs/11 páginas de `examples/` e terminou com zero candidatos E06,
zero FP e zero FN verificáveis, depois de corrigir falsos positivos de
condutores e rosa dos ventos. Não há estai operacional confirmado nesses
exemplos, de modo que o recall em projetos reais não é estimável. Duas
relações linha/ponto continuam visualmente incertas, sem promoção a positivo.
O baseline E02 mantém a classe legada `ESTAI_MT`; a comparação diagnóstica
pós-inferência registra dois encontros geométricos, sem alterar a classe
aberta `ESTAI` emitida pelo detector.
