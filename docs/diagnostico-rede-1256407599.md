# Diagnóstico de leitura do projeto 1256407599

Complemento E10: [referência integral, política de revisão e métricas](e10-referencia-segundo-pdf.md).
O diagnóstico amostral abaixo permanece como registro de sua execução. A referência
E10 distingue as camadas, inclui documentação e amplia D04: a anotação de P5 muda
N4 existente para remover/instalar, e o quadro ampliado à direita repete o mesmo
ponto. O estado e as validações vigentes de E10 constam do roadmap.

Verificação de 14/09/2026 no checkout `9cb0ef7`, inicialmente limpo. Pacote `0.4.0`,
extrator `1.14.0`, interpretador `22.0`. Nenhum `AGENTS.md` aplicável encontrado.
Teste do código atual, não do executável distribuído na release 0.4.

## Resultado

**Leitura parcial; não atende à leitura integral do projeto.** O PDF abre e renderiza.
OCR recupera os cinco identificadores P1–P5, quatro identificadores de vãos e as medidas
14, 100, 80, 57, 36 e 83 m. Entretanto, há informação visível ignorada, associação
ao ponto errado, duplicação e topologia incompleta. Não foi produzido um denominador
integral de ocorrências: as contagens abaixo não são métricas de precisão/recall.

Fonte: `examples/PROJETO DE REDE 1256407599.pdf`, 988.018 bytes, uma página de
595 × 842 pontos. SHA-256:
`0793c292df9722ff48df31ab052018d4233ad3541706f50f53e994cc1670af06`.
Hash, tamanho e mtime preservados pelo benchmark. A cópia contém carimbo de revisão
de 14/09/2026; não foi comparada byte a byte à cópia usada na release anterior.
Logo, não se atribui toda diferença observada exclusivamente à evolução do código.

## Execução reproduzível

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/benchmark.json --runtime-directory tmp/e01/runtime
.\.venv\Scripts\python.exe -m pytest tests/unit/test_benchmark_network_pdf.py tests/unit/test_smoke_examples.py -q -p no:cacheprovider --basetemp tmp/rede-1256407599/pytest
pdftoppm -scale-to 2400 -singlefile -png 'examples/PROJETO DE REDE 1256407599.pdf' 'tmp/rede-1256407599/poppler'
```

O runtime local existente usa Tesseract com português e inglês; o controle sintético
funcional do OCR passou. O benchmark usa SQLite novo por variante, extração,
interpretação, promoção, regiões, vãos, DTOs de Resultados e verificação do XLSX.
Não executa HTTP, cliente Qt, inspeção documental completa ou conformidade/SQL.
Se o runtime não estiver disponível em outra máquina, usar o procedimento de
`docs/e01-diagnostico-leitura-rede.md`, sem considerar ausência de OCR como teste aprovado.

| Medida | Sem OCR | Com OCR |
|---|---:|---:|
| Evidências | 1.821 | 2.049 |
| Evidências OCR | 0 | 228 |
| Propostas antes do filtro | 9 | 48 |
| Propostas finais | 0 | 38 |
| Relações propostas | 0 | 48 |
| Elementos confirmados | 0 | 10 |
| Regiões | 0 | 11 |
| Linhas de Vãos | 0 | 8 |
| Diagnósticos do pipeline | 0 | 0 |
| Tempo até regiões/vãos | 11,961 s | 121,184 s |
| Tempo incluindo Resultados/XLSX | 14,354 s | 122,921 s |

Extração/persistência consumiu 116,247 s na variante OCR. Esta execução não foi
um benchmark de desempenho isolado: houve inspeção/renderização concorrente.
Não há medição de pico de memória nem conclusão sobre regressão de desempenho.
Medições futuras isoladas servem à observabilidade e ao planejamento de recursos.
Conforme a diretriz posterior do usuário, duração não é critério de aceite: cinco
minutos ou mais são aceitáveis para obter leitura confiável.

As 38 propostas são 6 postes, 7 estruturas MT, 6 BT, 12 cabos e 7 equipamentos.
Os 10 confirmados são cabos; nenhum poste foi promovido. O XLSX conferiu com os DTOs:
38 linhas em Elementos e 8 em Vãos. Concordância entre saídas não certifica correção.
Oito testes das ferramentas de benchmark/smoke passaram em 4,34 s. O gate completo
não foi repetido: esta tarefa altera somente documentação.

## Divergências verificadas

| Caso | Evidência visual e saída atual | Camada a investigar |
|---|---|---|
| D01 — Revisão do cabo V3-4 | Com anotações, lê-se `ABCN-16(16)`; sem anotações, `ABCN-35(70)`. O segundo foi confirmado, com 14 m, sem diagnóstico da divergência. | Seleção de conteúdo técnico vigente, antes do reconhecimento/catalogação |
| D02 — Neutro de V2-3 | Duas propostas `N- (1N5)` foram confirmadas para o mesmo identificador, situação e geometria, ambas com 100 m. O desenho mostra um rótulo de neutro nesse trecho. | Consolidação por ocorrência e promoção |
| D03 — Ponto existente acima de P5 | `N2-10-300`, `S3R` e `100A-10kA-1H` pertencem visualmente ao ponto existente ligado a P5 pelo trecho de 36 m; propostas recebem identificador P5. | Associação por proximidade e pontos sem `P<n>` |
| D04 — Situações de N4 | P5 mostra N4 riscado em vermelho e N4 verde junto a N3(2); a saída contém apenas N4 `EXISTENTE`, sem as duas ocorrências operacionais correspondentes. | Cor/risco, extração e preservação das ocorrências |
| D05 — Transformador | `TR-3-45` é recuperado como texto OCR, mas não aparece nem nas propostas brutas nem nas finais. | Interpretação do código; catálogo sem escolha arbitrária |
| D06 — Conectividade | Oito linhas de Vãos cobrem quatro traçados com 14/100/80/57 m, todas com tipo e modalidade `DESCONHECIDO`. Cabos existentes de 36 e 83 m são confirmados, mas não chegam à tabela Vãos. | Projeção/topologia e política de exibição de existentes |

D01 não é uma simples troca de algarismos pelo OCR: a comparação dos dois rasters
mostra os dois conteúdos. Há 28 anotações PDF, incluindo Stamp, Ink, FreeText e Square.
`_semantic_page_pixmap` em `adapters/analysis/pymupdf_ocr.py` usa `annots=False`;
`application/document_zones.py` exclui anotações de revisão, com exceção técnica para
AutoCAD SHX. O comportamento evita transformar comentários em ativos, mas precisa
representar explicitamente revisões técnicas e conteúdo encoberto. Não basta ligar
todas as anotações no OCR nem assumir que o último carimbo aprova uma revisão.

D03 é compatível com a busca de identificadores próximos em
`adapters/interpretation/operational_labels.py`; a causa precisa ser reproduzida em
fixture antes de editar. D06 exige distinguir linha por cabo de trecho físico:
duas linhas para fase/neutro não são necessariamente duplicatas; D02 é um caso
separado de repetição do mesmo neutro. A ausência de classificação de poste/padrão
não deve ser preenchida por adivinhação (ADR 0015).

## Cobertura visual e limites

Conferidos a página completa com PyMuPDF e Poppler, recortes de P3/P4, P2, P1/P5 e
rede existente, e o recorte P3/P4 sem anotações. Há também cabeçalho, notas,
servidão, quadro de vão regulador, quadro de CHI, fotografias e assinaturas.
OCR contém NS, impacto ambiental negativo e menção à servidão; não foi verificado
se todos esses campos chegam corretamente ao painel documental. Fotografias e
assinaturas visíveis não constituem comprovação automática de conteúdo/autenticidade.

Poppler saiu com código zero e produziu imagem legível, com avisos de fontes
Symbol/ArialUnicode e streams Flate. Eles não impediram esta inspeção; não houve
reescrita ou reparo da fonte. Os 14 tokens de `get_text('words')`, 1.624 desenhos e
zero imagens de `get_images()` não descrevem sozinhos o conteúdo visível: várias
imagens estão em aparências de anotações.

Artefatos privados em `tmp/rede-1256407599/`: `benchmark.json`, `page-1.txt`,
`page-1.png`, `poppler.png`, `top.png`, `middle.png`, `bottom.png`, `header.png` e
`top-without-annotations.png`. Permanecem ignorados; o PDF real não é fixture pública.
O plano de correção foi incorporado como E10–E15, incluindo E12A/E12B para
experimentação de algoritmos alternativos e reconciliação entre métodos, em
[roadmap-mercado-paineis-leitura-rede.md](roadmap-mercado-paineis-leitura-rede.md).

## Atualização E11 — 14/09/2026

A implementação registra D01 como conflito entre `ABCN-35(70)` da base e
`ABCN-16(16)` visível, com recortes, máscara de alteração, xrefs e hash da fonte.
Nenhuma alternativa é promovida sem decisão humana com responsável e motivo.
O catálogo ainda não contém o código revisado; a escolha da camada pode ser salva,
mas o ativo permanece pendente de catalogação. A inspeção dos dois recortes
confirmou esses literais; hash, tamanho e mtime do PDF permaneceram iguais.

O grupo N4 conserva a comparação e as representações 138/146, sem inferir as
operações instalar/remover do OCR literal. Essa resolução permanece em E12/E13.
O benchmark E11 tem 9 confirmações e 7 vãos: a redução de um cabo/uma linha em
relação à E10 corresponde à retirada da promoção sem autoridade de D01. Isso não
resolve D02–D06 nem homologa a leitura integral. Implementação, validações,
compatibilidade e handoff em [e11-revisoes-tecnicas.md](e11-revisoes-tecnicas.md).

## Atualização E12 — 15/09/2026

O extrator 1.16.0 conserva no grupo R02 as leituras `N4(1)` verde e vermelho,
com caixas distintas e risco horizontal no vermelho, além de `N3(2)`, `S3R`,
`11-600` e `10-150`. A leitura original divergente permanece junto da passagem
tratada. A autoridade e a decisão técnica continuam pendentes; isso não resolve
automaticamente as operações de D04 nem cria novos ativos.

Lotes sucessivos, liberação de RGB concluído e passagens adicionais recuperam
grupos longos e melhoram uma geometria inclinada. O benchmark isolado passa de
228 para 246 evidências OCR; mantém 38 propostas finais, 9 confirmações e 7 vãos,
com zero diagnósticos. Essas contagens não medem a leitura integral. Os dois grupos
E11 mantêm identidade e não são promovidos. Fonte/hash/tamanho/mtime preservados.

Coordenadas fragmentadas, leituras divergentes, campos documentais truncados ou
duplicados e as pendências de interpretação/topologia continuam explícitos.
Denominadores E10 preservados. Comparação por ocorrência, experiência reprovada,
telemetria, validações e handoff E12A/E12B em
[e12-precisao-extratores.md](e12-precisao-extratores.md).

## Atualização E13 — 16/09/2026

Interpretador 24.0: D02 passa a uma ocorrência confirmada de neutro em V2-3,
conservando as duas leituras; os dois N3 físicos de P1 continuam separados. D03
usa contexto próprio da legenda do poste existente, sem identificador P5 e sem
inventar endpoint/modelo. D04 conserva base N4 e alternativas instalar/remover,
com caixas e identidades distintas e decisão técnica pendente. D05 apresenta
`TR-3-45`, fases/capacidade observadas e catálogo não resolvido.

Os dois `N-4` existentes também ficam representados sem completar CA/CAA; Q3
permanece visível com associação pendente. O núcleo E10 passa de 24 TP/5 FN/4 FP
para 29/0/0. Equipamentos, classificação, documentação e topologia não integram
esse denominador. O grafo alternativo continua perdendo associações em P3/cabos.
O benchmark final tem 43 propostas, oito confirmações, seis vãos e zero diagnósticos;
nenhuma confirmação duplicada conhecida. Isso não conclui D06 nem a leitura integral.
Fonte e 139 referências preservadas. Ver [decisões, testes e reconciliação E13](e13-ocorrencias-associacao.md).


## Atualização E14 — 16/09/2026

D06 corrigido no escopo topológico: dez trechos físicos projetados, nove pontos
físicos, sete pares visíveis corretos e três continuidades com destino externo
não inventado. Os seis comprimentos estão nos trechos correspondentes; os quatro
sem medida continuam desconhecidos. V3-4 agora orienta P3/P4 corretamente e fica
visível com revisão técnica pendente, sem confirmar a base. Existentes 36/83 m
chegam à tabela Vãos; fase/neutro aparecem juntos em Trechos físicos sem perder
identidade de cabo nem unir circuitos de tensões/configurações distintas.

API/UI/XLSX concordam. Tipo/modalidade continuam desconhecidos com motivo;
P4 não foi classificado como padrão pela casa. A janela de desenho e os traçados
sustentam continuidades revisáveis, sem poste/cabo confirmado além da folha.
Benchmark final: 43 propostas, oito confirmações, dez pontos elétricos, oito linhas
de Vãos, dez trechos físicos, zero diagnósticos e fonte inalterada. Núcleo E13
preservado: 29 TP, zero FN/FP. Grafo E12A mantém somente 1/7 pares completos e não
foi integrado. Não é aceite integral E15, nem resolução dos bloqueios E08/E09.

Decisões, compatibilidade 25.0/API 1.6.0, limites, comandos e mapa completo em
[e14-topologia-projecao-trechos.md](e14-topologia-projecao-trechos.md).

## Atualização E15 — 16/09/2026 — aceite bloqueado

Auditoria integral das 139 referências preserva os ganhos de E11–E14: núcleo
29 TP/0 FN/0 FP, dez trechos, sete pares visíveis e seis medidas corretas no PDF
principal. Isso não resolve classificação completa, autoridade ou documentação.
Dos 64 itens documentais, 16 estão exatos na projeção, 11 duplicados (oito também
com valores errados), 36 sem representação individual e um somente como leitura
auxiliar revisável. Revisão do núcleo 21/29; cobertura automática por campos no
máximo 8/29. Metas E10 e leitura exata do documento estão reprovadas.

As nove reservas sintéticas E10 foram executadas com baseline original, vertical,
composição atual e ablações. H01 perde 18/27 ocorrências entre páginas; H03 produz
seis falsos positivos na composição atual, três confirmados; H02 mantém revisões
pendentes, mas erra os pares/medidas dos circuitos cruzados. Não extrapolar o êxito
topológico deste PDF às reservas. O grafo independente também erra medidas.

Correções de integração conservam tokens/qualificadores nos rótulos HTTP/Qt/realces
e no XLSX; o teste do benchmark passa a conferir a aba adicionada por E14.
Inferência não ampliada. E15A–E15E separam as perdas antes da implementação.
HTTP real, OCR real, SQL fake, exportações, cancelamento, reanálise e reabertura
foram exercitados; a rejeição anterior foi preservada nos três H02.
Comandos, resultados finais do gate, métricas e limites no
[handoff E15](e15-aceite-integral-segundo-pdf.md). E08/E09 e fontes intactas.
