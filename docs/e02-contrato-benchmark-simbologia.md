# E02 — Contrato do benchmark de simbologia

Checkpoint de coordenação 2, 18/09/2026. Este é um contrato do avaliador offline;
não antecipa o contrato de domínio E03 nem implementa fusão de produção E12.

## Propriedade e entradas

- A: `scripts/benchmark_symbols.py`, `scripts/symbol_benchmark_evaluator.py` e
  `scripts/symbol_benchmark_runner.py`.
- B: `tests/symbol_benchmark_fixtures.py`, `tests/unit/test_benchmark_symbols.py`,
  `tests/fixtures/symbols/` e `docs/e02-dados-benchmark-simbologia.md`.
- C: exclusivamente `tmp/e02-simbologia/visual/` (scripts locais, imagens,
  manifesto, observações anteriores às predições e comparação posterior).
- Coordenador: este contrato, documentação compartilhada, roadmap, integração,
  relatórios públicos do baseline e artefatos `tmp/e02-simbologia/integracao/`.

O avaliador recebe JSON e não importa detectores. A inferência recebe somente o
caminho PDF e configuração fixa: nunca referência, classe esperada, ROI ou caixa
do revisor. O runner persiste predições antes de carregar a referência. Inventário
E01: `docs/data/inventario-simbologia-v1.json`, SHA-256
`e3d49d9b0072f9f30ea98e2171c0cd520a819a15b329590cfbf35f508f042fcd`.

## Esquema JSON 1

Referência: objeto com `schema_version: 1`, `families: [str]`, `documents: [obj]`,
`occurrences: [obj]`. Documento: `id`, `sha256`, `path`, `split`
(`development`, `calibration`, `reserve`), `ancestor_id`, `template_family`,
`pages: [{number, width_pt, height_pt}]`. IDs de documento identificam caminhos,
mesmo quando dois caminhos têm o mesmo conteúdo. Derivados compartilham ancestral
e família de desenho e não atravessam partições. `families` mantém as 33 famílias
E01 mesmo quando não existe ocorrência avaliável nesta versão sintética.
O escopo de anotação é `annotation_scope: "complete"` (default para os oráculos).
Referências declaradas parciais são recusadas para métricas globais. Uma auditoria
de IA com referência parcial registra decisões por predição/ROI e mantém recall
populacional não avaliado, em vez de tratar tudo fora das ROIs como FP.

Ocorrência: `id`, `document_id`, `page` (base 1), `layer` (`base`, `annotation`),
`family`, `class_id`, `bbox: [x0,y0,x1,y1]` normalizada em [0,1],
`context` (`operational`, `legend`, `informative`, `negative`),
`evaluability` (`confirmed`, `ambiguous`, `unassessable`),
`situation` (string ou null), `quantity` (número ou null),
`association` (string ou null), `strata: [str]`. Campos opcionais:
`variant_id`, `trace: [[x,y],...]`, `notes`, `image`.
Ambiguidades ficam em estrato separado; não viram TP/FN certos.

TP/FN primário usa somente `confirmed` + `operational`. Referências em `legend`,
`informative` e `negative` conservam denominadores/contextos separados; uma
predição operacional nesses controles é FP. Predições compatíveis com referência
`ambiguous`/`unassessable` são `unresolved`, com localizador e motivo, fora de FP
certo. Famílias informativas não são chamadas ausentes do inventário por não
terem ocorrência operacional avaliável. Referência visual de IA conserva seu
caráter provisório separado das anotações sintéticas autorais.

Predições: objeto com `schema_version: 1`, `methods: [obj]`, `predictions: [obj]`,
`executions: [obj]`. Método: `id`, `version`, `algorithm_family`,
`shared_sources: [str]`, `supported_classes: [str]`.
Predição: mesmos localizadores da ocorrência, `id`, `method_id`, `family`,
`class_id`, `bbox`, `score` bruto (número ou null), `situation`, `quantity`,
`association`; opcionais `trace`, `context`, `provenance`, `review_required`,
`calibrated_probability`. Não atribuir probabilidade ao score legado 0,88.
Execução: `document_id`, `page`, `layer`, `method_id`, `status`
(`executed`, `not_applicable`, `failed`), `reason`; telemetria e assinaturas
adicionais são permitidas. Silêncio, fora de domínio e falha são distintos.
O runner inclui também `documents: [{id, sha256}]` nas predições, ligando a
avaliação à fonte mesmo nas páginas sem candidatos. Se esse mapa está presente,
o avaliador rejeita divergência em relação à referência. Oráculos puramente
em memória podem omitir o mapa; essa exceção não se aplica a inferência real.

## API e resultados mínimos

`scripts.symbol_benchmark_evaluator.evaluate(reference, outputs) -> dict` é
a API pública dos testes-oráculo. Validação rejeita IDs duplicados, referências
inválidas, geometrias não finitas e vazamento de partições.

Relatório: `schema_version`, `protocol`, `denominators`, `methods` (mapa por ID),
`compositions` (mapa), `complementarity`, `limitations`.
Cada avaliação de método/composição tem `micro: {tp,fp,fn,precision,recall}`,
`by_family` (inclusive famílias ausentes), `by_class`, `by_stratum`, `macro`,
`fp_per_page`, `matches`, `false_positives`, `false_negatives`, `duplicates`.
Localizadores completos e IDs permanecem em erros e matches. Precisão/recall com
denominador zero são null, nunca 100%. Pareamento máximo um-a-um por
documento/página/camada/classe; IoU >= 0,5. Para símbolos finos (razão entre eixos
<= 0,15), distância entre extremos <= 0,15 do comprimento maior e razão de
comprimento >= 0,70; registrar IoU, distância e critério usado. Identidade explícita
e geometrias originais são preservadas; proximidade não une objetos vizinhos.
Essas distâncias e razões são no espaço normalizado da página (x/y em [0,1]),
não em pontos PDF; não alegam invariância física à razão de aspecto da folha.
Para atribuir o estrato de um FP já identificado, o centro contido em um controle
negativo também pode ligar seu contexto (`context_center_containment`), sem
alterar candidato, TP/FP/FN ou critérios de acerto. Todos os controles compatíveis
são preservados, sem escolha arbitrária de uma única ROI.

`compositions`: `raw_union`, `filtered_union`, `intersection_control`, `final`,
`ablations` por método retirado. Duplicatas não aumentam TP; seus excessos são
reportados como FP/duplicata. A união para medição preserva observações e associa
equivalências exatas entre métodos (mesmos localizadores/classe/caixa); não usa GT
para produzir candidatos. Sem filtro/política implementada, filtered/final são
aliases declarados da união e não alegam promoção implementada.
Interseção é controle analítico e nunca filtra a união. Complementaridade registra
IDs de TP/FP exclusivos, erros compartilhados e pares A-acerta/B-falha.

Reportar confusão, acurácia de situação/quantidade/associação com seus denominadores,
revisão/cobertura e curvas por score sem chamá-las probabilidade. Brier/ECE somente
com probabilidades explicitamente calibradas; sem amostra suficiente, null/motivo.
Intervalos e limites por documento devem explicitar insuficiência amostral.
O protocolo fixa mínimo 30 amostras explicitamente calibradas para Brier/ECE,
cinco ancestrais para intervalos descritivos por bootstrap, seed 0 e 500 repetições.
São decisões do protocolo, não resultados ou garantia de confiabilidade.

## Fixtures, reserva e CLI

B entrega `build_corpus(output_dir: Path, *, split: str = "development") -> dict`
em `tests.symbol_benchmark_fixtures`, materializando PDFs determinísticos autorais
e retornando a referência acima; `portable_reference(reference)` normaliza os
caminhos para serialização independente da máquina. Mantém catálogo/manifesto de partições versionado
com hashes do gerador, protocolo, documentos e reserva, sem publicar resultados
da reserva. A reserva é criada e lacrada por B, sem inferência nem inspeção de suas
imagens; A, C e coordenador não abrem seus rótulos. Derivações da mesma geometria
permanecem juntas; desenhos distintos entre splits exigem ancestral distinto.

A entrega CLI `python -m scripts.benchmark_symbols synthetic --output DIR`
para V-B (development por padrão) e
`python -m scripts.benchmark_symbols examples --root examples --output DIR`
para V-P. Este último descobre todos os PDFs/páginas recursivamente, persiste
manifesto, hashes, predições, tempo/memória, falhas e integridade. Não declara
revisão visual automática. `python -m scripts.benchmark_symbols evaluate
--reference FILE --predictions FILE --output FILE` compara artefatos congelados.
Reserva recusada em E02; nenhuma opção padrão a abre ou a avalia.

Baseline executa somente o detector simbólico vetorial legado disponível,
explicitando as três classes e camada base. OCR/leitor textual e grafo documental
não são métodos de detecção visual independentes. Controles-oráculo A/B testam
o avaliador e não são apresentados como detectores reais.

C primeiro registra inspeção de imagens originais de todas as páginas, base e
aparência, tiles completos e regiões sem detecção. Só recebe predições depois do
checkpoint estável. Registra FP/FN e ambiguidades como hipóteses auditáveis, com
denominador confirmado separado do provisório. Originais permanecem intactos,
exemplos são desenvolvimento e os artefatos privados ficam somente em `tmp/`.

## Pré-voo

Base Git limpa `50204c0dbfedeaf7a8878f7fc27b774bd7fe94d5`. E01: registro,
esquema e detector com hashes compatíveis; teste apresenta CRLF no checkout.
Os 38 testes do inventário passam. Artefatos privados históricos E01 não estão
presentes neste checkout: V-P será executado novamente, sem alegar reuso visual.
O Python da `.venv` requer execução fora do sandbox devido ao launcher da
Microsoft Store; execução autorizada pelo revisor automático funcionou.

## Histórico dos checkpoints

1/1.1 fechou a interface antes de delegar e esclareceu contextos/ambiguidades.
O checkpoint 2 acrescentou vínculo SHA fonte/predições, continuação após erro de
abertura e atribuição contextual de FP com caixa degenerada; os limiares e
contagens TP/FP/FN do smoke permaneceram iguais. Acrescentou também recusa de
referência parcial para evitar métricas globais falsas no V-P. Nenhum detector
foi alterado. A inferência privada congelada pode ser reutilizada porque runner,
método, configuração e fontes permaneceram idênticos; a comparação declara
separadamente a versão do avaliador.
