# E02 — Dados e oráculos do benchmark de simbologia

Checkpoint B, 18/09/2026. Contrato: `e02-contrato-benchmark-simbologia.md`.
Responsável: subagente `/root/b_testes_dados`. Arquivos exclusivos desta frente:
`tests/symbol_benchmark_fixtures.py`, `tests/unit/test_benchmark_symbols.py`,
`tests/fixtures/symbols/` e este documento. Nenhum detector foi alterado.

## Dados e significado

O gerador materializa PDFs autorais, determinísticos e independentes de `examples/`,
de fontes externas e dos módulos de detecção. A API é
`build_corpus(output_dir: Path, *, split="development") -> dict`; a função
`portable_reference(reference)` substitui caminhos absolutos por nomes relativos,
preservando hashes e localizadores. O gerador encontra o repositório por `__file__`,
não pelo diretório corrente. `split="reserve"` é recusado antes de criar diretórios.

Os nomes de classe descrevem a intenção do desenho sintético. **Não são certificação
de equivalência normativa, variantes homologadas ou catálogo patrimonial.** Os
controles legados reproduzem estruturalmente haste/barras e corpo riscado observáveis
nas regressões existentes, sem importar o detector. O transformador de desenvolvimento
usa estrutura triangular autoral, relacionada apenas à nota estrutural E01 §18;
não recebe `variant_id` normativo. Estai é um controle fino autoral. Os dois círculos
de calibração são um controle abstrato nomeado pelo autor, não cobertura comprovada
da variante CEMIG. Situação desconhecida e cardinalidade de transformador/estai
permanecem `null`; contar IDs de ocorrências não equivale a contar ativos físicos.

As 33 famílias E01 permanecem no relatório. Mapeamento taxonômico desta medição:
ATERRAMENTO → `family-f02-19`; PARA_RAIOS_MT/BT → `family-f02-21`;
TRANSFORMADOR → `family-f02-18`; ESTAI_MT → `family-f02-14`;
POSTE → `family-f02-03`; negativos genéricos → `family-f02-33`.
O mapeamento não atesta procedência do `SIMBOLOGIA.pdf` legado.

| Partição | PDFs / páginas | Ancestral e família de desenho | Uso |
|---|---:|---|---|
| development | 4 / 6 | `dev-author-layout-v1` | Baseline V-B e diagnóstico iterativo |
| calibration | 2 / 2 | `cal-author-circles-v1` | Desenhos distintos; nenhuma calibração estatística alegada |
| reserve | 2 / 2 | `reserve-author-graphs-v1` | Lacrada até E16; nunca inferida/renderizada/inspecionada em E02 |

Todas as derivações de um desenho ficam juntas: escala, rotação, cor, raster,
fragmentação, agrupamento, sobreposição, anotação e objetos próximos são
desenvolvimento. O agrupamento por ancestral é conservador: os quatro documentos
de desenvolvimento contam como **um** ancestral independente, não quatro amostras
de generalização. Calibração e reserva têm grafos/desenhos estruturais distintos,
e não apenas outras rotações/cores do desenho de desenvolvimento.

Desenvolvimento contém 27 registros: 22 operacionais confirmados, um operacional
ambíguo, uma legenda e três negativos (glifos, tabela, cerca). Os 22 positivos
dividem-se em 9 aterramentos, 3 para-raios MT, 3 para-raios BT, 4 transformadores e
3 estais MT. A camada de anotação tem uma ocorrência confirmada; há repetição da
mesma geometria em página diferente. Legenda/negativos não entram no denominador
TP/FN operacional; ambiguidades ficam separadas. Famílias ausentes têm denominador
zero e recall `null`. Esses números descrevem controles, não estimativas de campo.

## Congelamento e reserva

`tests/fixtures/symbols/manifest.json` contém os hashes de cada PDF, referências,
gerador, protocolo e inventário, as partições e os ancestrais. Os PDFs públicos são
reconstruídos, sem necessidade de versionar binários. As referências públicas são
`reference-development.json` e `reference-calibration.json`. Serialização com
PyMuPDF 1.28.0, `no_new_id=True`, sem datas variáveis; seed declarado 20260918,
mas sem aleatoriedade (coordenadas fixas). Hash do código normaliza UTF-8/LF para
evitar diferenças de checkout CRLF; PDF e ZIP usam bytes exatos.
O `.gitattributes` local da pasta de fixtures fixa JSON em LF e ZIP como binário.

| Artefato | SHA-256 |
|---|---|
| Gerador público, texto LF | `fb8f6251e0d8f940fb9a3e2683fb0a0c3a695f297886162d40fe6d75276f0af1` |
| Referência development | `cfdba30492ba3b0c416e97795a240d0413a405aa9d8c4806bd399f489d8b43e3` |
| Referência calibration | `1c2ecd2feb979f3b9bd42cdc1e4dd32bce33474391fee45924876fef6b753af4` |
| Inventário E01 | `e3d49d9b0072f9f30ea98e2171c0cd520a819a15b329590cfbf35f508f042fcd` |
| Reserva lacrada | `6874d0585269a0a68397319268076e8e788aff64fc2bc5d776e80efca739be7b` |
| Protocolo checkpoint 2 | `b00899651b0aadf3ae1cca4baa22affc8a97a39c7d52fc25cacfca37f2d96928` |

`reserve.sealed.zip` foi criado uma única vez, sem chamadas de renderização ou
inferência e sem inspeção de imagens. O arquivo inclui os PDFs, sua referência e
fonte de autoria; **não deve ser listado, descompactado ou lido até E16**. O lacre
é uma regra operacional com integridade SHA-256, não criptografia nem controle
de acesso. Os testes leem somente bytes opacos para verificar o hash. Rótulos e
desenhos da reserva não foram compartilhados com runner, revisor visual ou
coordenador. A reserva é pequena e não cobre integralmente o inventário: E16 não
pode apresentá-la como homologação de todas as famílias. Expansão futura exige
desenhos independentes e novo manifesto; não alterar silenciosamente este lacre.

## Revisão visual pública antes da comparação

Em 18/09/2026, B renderizou via Poppler e inspecionou efetivamente as imagens:

| Documento | Páginas | Constatações visuais |
|---|---|---|
| `dev-symbols.pdf` | 1–2 | Cinco controles isolados; cores, rotação e escala visíveis; triângulo e estai fino preservados |
| `dev-raster.pdf` | 1 | Mesma composição da página 1 rasterizada a 108 DPI; perda de nitidez intencional |
| `dev-contexts.pdf` | 1–2 | Fragmentos, grupo único, vizinhos sobrepostos, anotação, linha cruzando triângulo e repetição entre páginas; ambiguidades explícitas |
| `dev-negatives.pdf` | 1 | Legenda, glifos, grade e cerca identificáveis, sem cortes |
| `cal-vector.pdf`, `cal-raster.pdf` | 1 cada | Desenhos circulares isolados; versão raster com degradação intencional |

Imagens intermediárias: `tmp/e02-simbologia/b/development/` e `calibration/`.
Poppler emitiu avisos de fontes de fallback Symbol/ArialUnicode; as imagens abertas
confirmaram legibilidade da única linha textual, glifos e geometrias. Os artefatos
da reserva não foram renderizados. A auditoria V-P de PDFs privados pertence à
frente C e é registrada separadamente.

## Testes e isolamento

Os testes usam saídas-oráculo, nunca resultados produzidos pelo detector como
verdade-terreno. Cobrem máximo um-a-um em caso não guloso; duplicatas dentro de
método; equivalência exata entre métodos preservando observações; vizinhos;
camadas/páginas; IoU e extremos de símbolos finos; classes ausentes; classes
erradas e confusão; situações/quantidades/associações; negativos e ambiguidades;
IDs repetidos; NaN/inf; vazamento por ancestral, família de desenho e conteúdo;
integridade e bloqueio da reserva.

O checkpoint 2 acrescenta a recusa de referência `annotation_scope="partial"`
para evitar recall/precisão globais com anotações incompletas. Também testa a haste
degenerada dentro da ROI de legenda: continua FP com IoU zero, recebendo apenas
atribuição contextual por centro contido. A regra não muda TP/FN nem a geometria;
preserva todas as ROIs contextuais compatíveis e identifica o critério no relatório.

O controle A-acerta/B-falha tem dois positivos em posições distintas: cada método
obtém TP=1/FN=1 e a união TP=2/FN=0; interseção TP=0/FN=2. É um teste do avaliador,
não ganho medido de dois detectores reais. Duas observações idênticas de A mais uma
de B resultam em TP=1/FP=1, com as três observações preservadas; concordância não
produz probabilidade.

Os testes do runner verificam `.PDF` recursivo, cópias de mesmo hash com IDs de
caminho distintos, todas as páginas, falha de leitura seguida de arquivo válido,
falha da primeira página com continuação, ausência explícita de exemplos e
imutabilidade da fonte. Um espião com assinatura `(Path, str)` verifica a fronteira
de inferência; leitura da referência só acontece após as quatro inferências e
persistência dos 12 registros de execução. A geração de rótulos ocorre em processo
separado. O JSON de predição pode declarar `documents: [{id, sha256}]`; quando
presente, fonte divergente é rejeitada antes de medir.

Comandos executados por B na raiz (Python da `.venv` exigiu execução autorizada
fora do sandbox devido ao launcher Microsoft Store):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_benchmark_symbols.py -q
.\.venv\Scripts\python.exe -m ruff check tests/unit/test_benchmark_symbols.py tests/symbol_benchmark_fixtures.py
.\.venv\Scripts\python.exe -m ruff format --check tests/unit/test_benchmark_symbols.py tests/symbol_benchmark_fixtures.py
.\.venv\Scripts\python.exe -m mypy src tests/unit/test_benchmark_symbols.py tests/symbol_benchmark_fixtures.py
```

O checkpoint final B produziu **47 testes aprovados em 2,77 s**; ruff check e
format check passaram nos dois arquivos Python da frente, e mypy passou com o
`src` local incluído (217 arquivos). A integração final V-S/V-N/V-Q de todas as
frentes é responsabilidade do coordenador e está no handoff do roadmap. A CLI
pública exata V-B/V-P e o baseline medido ficam nos documentos de contrato e
integração do coordenador. Nenhum ajuste de detector ou limiar foi feito para
melhorar a pontuação destes controles.
