# E04 — Robustez vetorial de aterramento e para-raios

Implementação da etapa E04 do [roadmap](roadmap-analise-simbologia.md), limitada
a aterramento e para-raios MT/BT. O score `0.88` continua bruto, sem calibração.
Os exemplos locais são desenvolvimento; a reserva sintética E02 permanece lacrada.

## Contrato de normalização

O extrator aceita `normalizations=None` para executar todas as normalizações,
ou um `frozenset` dos nomes `grouping`, `fragments`, `scale` e `styles` para
ablação. A configuração vazia desliga as quatro normalizações; não restaura
bugs de geometria ou a inferência automática de situação pelo preto.

Cada candidato conserva os índices dos drawings em `vetores_origem`, os pares
drawing/item em `primitives_origem`, a caixa original em
`simbolo_limites_originais`, a versão e as normalizações executadas. A caixa
usa extremos de todas as primitives, inclusive segmentos de área zero.
Drawing agrupado pode conter ocorrências distintas, com chaves e geometrias
separadas. Deduplicação precisa de suporte geométrico compatível.

Preto/cinza sem convenção comprovada resulta em situação indeterminada,
separada da classificação. O contrato E03 representa essa situação por `None`.
A cor canônica não é prova de vigência de um ativo. As propostas legadas de
classe sem tipo catalogado continuam conflitantes e sem confirmação automática;
a resolução semântica completa do consumidor pertence a E13.

O adaptador interno `legacy_symbols.py` acompanha o novo contrato de geometria,
suporte e assinatura. Essa alteração e seus testes são a extensão mínima do
escopo necessária para não transportar caixas de drawings inteiros para
observações de símbolos agrupados. Não há mudança do DTO público ou do codec.

## Validação

Os comandos V-S, V-N e V-Q estão registrados no handoff da etapa. V-B usa o
protocolo e os dados E02 sem alteração de tolerâncias, classes ou partições.
O comando portátil permanece:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e04-simbologia/baseline-final
```

Ablação por configuração, com referência carregada somente depois de salvar
predições, é executada pelo harness local:

```powershell
.\.venv\Scripts\python.exe tmp/e04-simbologia/integracao/ablate.py
```

O harness registra cada normalização removida, assinatura e relatórios integrais
por classe/estrato. A descrição textual histórica `unmodified legacy defaults`
do runner E02 não descreve E04; a versão e o hash de código identificam a execução
portátil, e o harness de ablação registra a configuração real explicitamente.

V-P exige inferência congelada e inspeção real independente, antes e depois das
predições, de todos os PDFs/páginas descobertos em `examples/`:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e04-simbologia/predictions
```

Artefatos privados, manifesto, imagens e decisões ficam em
`tmp/e04-simbologia/visual/`. O runner não declara aprovação visual.
O primeiro checkpoint integrado foi rejeitado: V-S (211 testes), V-N (60),
lint e mypy passaram, mas o benchmark apontou dois FP novos em cerca e perda
de um vizinho; a revisão independente também reproduziu clipping herdado
ignorado em Form XObject. O gate de formatação encontrou um arquivo pendente.
Logs e resultados foram preservados em
`tmp/e04-simbologia/checkpoint-rejected-1/`; a inferência V-P parcial foi
interrompida e não conta como cobertura. Correções e nova integração são
necessárias antes do aceite.

## Checkpoints e resultado sintético

A3 passou nos gates automatizados, mas foi **rejeitado na auditoria visual**.
Em todos os 11 PDFs/11 páginas, a inferência produziu 138 candidatos, sem falhas
de leitura. A inspeção encontrou perda de símbolos com barras largas e trocas
de aterramento por MT quando segmentos do círculo eram contados como barras.
Quatro contraprovas autorais independentes reproduziram a primeira regressão;
suportes originais estavam presentes, afastando clipping como causa.
Resultados completos desse checkpoint ficam em
`tmp/e04-simbologia/checkpoint-a3/`; os números abaixo não constituem aceite.

A4 corrigiu esses casos com testes autorais: suporte independente por barra,
âncora junto à ponta da haste, contornos fechados/curvos preservados e junções
abertas em T decompostas. MT mantém a variante de cinco barras. O detector usa
`1.19.1:vetorial-3` e o cache do analisador `1.19.1`. No checkpoint A4, V-S tem
269 testes aprovados e V-N 60; Ruff e mypy passaram. A tabela sintética e as
ablações abaixo foram reproduzidas em A4. A auditoria das 221 predições A4
recuperou as perdas anteriores, mas encontrou uma hipótese extra de MT que
combinava traços de aterramento e MT colineares vizinhos. C e coordenador
confirmaram a imagem; A4 foi arquivado em `tmp/e04-simbologia/checkpoint-a4/`
e reaberto para corrigir essa associação antes do aceite.

A5 acrescentou a assinatura do terminal MT e a reunião de hastes redundantes
com terminal compartilhado. A revisão independente encontrou uma interação
com a primeira barra fragmentada: a reunião ocorria antes da reconstrução da
barra e ainda produzia duas hipóteses. A inferência A5 foi interrompida antes
de terminar, não conta como V-P e está documentada em
`tmp/e04-simbologia/checkpoint-a5-interrupted/`. A correção exige reconstruir
os fragmentos antes de identificar suportes redundantes; início de haste comum
sem terminal comum continua representando ocorrências distintas.

O checkpoint final A6 usa detector `1.19.3:vetorial-5` e analisador/cache
`1.19.3`. Reconstrói barras para conferir o terminal e limita a reunião de
sobreimpressões às hastes originais. A primeira tentativa que ampliava caixas
de vizinhos foi barrada pelos testes existentes e corrigida antes do freeze.
V-S: 286 passed; V-N: 60 passed; Ruff e mypy: aprovados. B repetiu 302 testes
com hashes estáveis. Benchmark e seis ablações foram reproduzidos em A6 com os
mesmos resultados abaixo. V-P final foi concluída e reconciliada conforme a
auditoria registrada ao final deste documento.

Os **11 símbolos vetoriais operacionais de base** das três classes de E04 têm
pareamento e localização corretos. O avaliador mantém todos os 22 positivos no
denominador global, incluindo raster, anotação, transformador e estai, que não
foram adicionados ao detector nesta etapa.

| Execução | TP | FP | FN |
|---|---:|---:|---:|
| Baseline E02 | 0 | 9 | 22 |
| E04 completa | 11 | 1 | 11 |
| Sem as quatro normalizações | 8 | 1 | 14 |
| Sem fragmentação | 10 | 1 | 12 |
| Sem agrupamento | 9 | 1 | 13 |
| Sem escala | 11 | 1 | 11 |
| Sem estilos | 11 | 1 | 11 |

O FP remanescente é o símbolo em legenda já detectado pelo baseline.
Cerca, glifos e tabela têm zero FP. Os dois vizinhos E02 mantêm identidade;
fragmentação, agrupamento e as três classes sob rotação/escala têm TP.
Os dois FN do estrato `scale_rotation` são transformador e estai, fora de E04.

Comparação por estrato relevante, na ordem TP/FP/FN (estratos se sobrepõem;
não devem ser somados):

| Estrato | Baseline E02 | A6 |
|---|---:|---:|
| `canonical` | 0/0/5 | 3/0/2 |
| `scale_rotation` | 0/0/5 | 3/0/2 |
| `fragmentation` | 0/0/1 | 1/0/0 |
| `grouped` | 0/0/1 | 1/0/0 |
| `neighbors` | 0/0/2 | 2/0/0 |
| `different_page` | 0/0/1 | 1/0/0 |
| `critical_legend` | 0/1/0 | 0/1/0 |
| `critical_fence`, `critical_glyph`, `critical_table` (cada) | 0/0/0 | 0/0/0 |

Os relatórios `integracao/ablation-comparison.json` e
`integracao/benchmark-acceptance.json` conservam todos os estratos, classes,
pareamentos, IoU, distância normalizada e proporção de comprimento. O baseline
não localizava corretamente as caixas degeneradas; a comparação global inclui
esses falsos positivos, mesmo quando não pertencem a um estrato negativo.
Nos 11 pareamentos, o IoU mínimo foi `0,99999978` e a média `0,99999998`.

Escala e estilos não mostram ganho isolado neste corpus E02 pequeno; controles
autorais adicionais verificam a necessidade de cada normalização, inclusive
escala acima do antigo limite, cinza, barras preenchidas e rotação arbitrária.
Não há ajuste de limiar do avaliador nem abertura da reserva para sustentar o ganho.

### Proveniência, clipping e recuperação

`get_drawings` inclui aparências de anotações. Páginas com anotações são copiadas
em memória, mantendo o catálogo do documento, e a cópia perde somente a entrada
de anotações da página analisada. Caminhos da base são conferidos por sequência,
itens e estilos exatos contra os originais, mantendo seus índices. Divergência
gera falha explícita; não produz uma correspondência aproximada por posição.

Clipping herdado é propagado pela hierarquia. Uma assinatura que depende de
primitives cortadas não comprova um símbolo completo visível. Por isso o antigo
controle E03 que preservava uma assinatura fora do crop agora exige abstenção;
a cobertura continua sem comprovar ausência física. Máscaras de clipping
arbitrárias não foram reconstruídas e limites conservadores são registrados.

Falha do extrator de símbolos conserva as demais evidências e impede gravar
aquela extração no cache. A tentativa seguinte pode recuperar o resultado e
voltar a usar o cache normalmente. Esse controle não implementa a orquestração E15.

O índice espacial usa células por escala e procura somente células ocupadas,
sem limitar o número de candidatos. Em uma página real, o perfil instrumentado
caiu de 53,46 s para 20,30 s, mantendo 35 candidatos. A cópia do documento inteiro
tem custo de memória proporcional ao documento; `tracemalloc` do runner não mede
RSS nem memória nativa do MuPDF. Esses números não são um limite operacional.
A soma dos tempos por documento na inferência A4 dos 11 PDFs foi 197,68 s;
metadados de ambiente e memória por documento estão no manifesto V-P.

## Auditoria final A6

Inferência completa: **11 PDFs recursivos, 11 páginas, 220 candidatos, zero
falhas**, fontes intactas, 269,62 s somados por documento. C viu realmente
154 imagens originais antes das predições e todos os 221 recortes A4. A6 retirou
exatamente o FP extra de associação entre vizinhos. Para os 220 restantes,
documento, página, camada, classe, caixa, suporte, situação, revisão e hashes
do PDF e do PNG rerenderizado são idênticos aos inspecionados. São 220 inspeções
reaproveitadas com prova, não 220 novas leituras; delta visual novo zero.

Todos os **118 candidatos visualmente plausíveis do baseline** mantiveram
classe/localização. Há 143 pareamentos por suporte original exato, 16 remoções
adjudicadas (15 FP e um ambíguo) e 77 candidatos novos plausíveis. A classificação
visual final contém **197 plausíveis, cinco FP herdados, 14 ambíguos e quatro
não avaliáveis**, sem FP novo. A referência parcial mantém ao menos 19 FN
(um aterramento, dois MT, 16 BT), antes 30. Não há denominador exaustivo nem
verdade-terreno especialista para estimar recall global ou precisão de campo.

137 candidatos pretos preservam situação indeterminada; zero confirmação
automática como existente. Há um método vetorial base, portanto os exclusivos
são triviais e não demonstram ganho de união entre algoritmos. A aparência foi
realmente inspecionada em todas as páginas, sem se tornar uma segunda inferência.
Quantidade física, associação e interpretação normativa das cores seguem sem
homologação. Os exemplos são desenvolvimento e a reserva E16 permanece lacrada.

O coordenador repetiu os verificadores de checkpoint e visual com exit 0.
Manifesto, matriz de 22 células, decisões por candidato/perda e prova de reuso:
`tmp/e04-simbologia/visual/review-final.json`,
`tmp/e04-simbologia/visual/checkpoint-a6/delta-proof.json`,
`tmp/e04-simbologia/visual/verification.json` e relatório final local.
Hashes, comandos completos, propriedade de arquivos e handoff estão em E04 no
roadmap. A etapa está concluída pelos critérios definidos, com as limitações
herdadas explícitas; não significa reconhecimento integral ou homologação.
