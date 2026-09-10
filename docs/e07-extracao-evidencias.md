# E07 — Extração robusta de evidências

Execução em 10/09/2026 sobre `77258cf`, sem commit. Estado e aceite no
[roadmap](roadmap-mercado-paineis-leitura-rede.md). A recuperação integral exigida por E01
ainda não foi demonstrada; os ganhos abaixo não certificam a leitura completa da rede.

## Dependência e limites

Git inicial limpo; nenhum `AGENTS.md` encontrado nos ancestrais ou no projeto. Foram lidos
roadmap, handoff E01, adaptadores de análise, porta de análise, cache e testes relacionados.
O extrator e `ports/analysis.py` não divergiam da versão diagnosticada em E01. As alterações
posteriores de mercado/UI foram preservadas. As três verificações privadas de E01 passaram,
confirmando inventário, denominadores, baseline completo, runtime e integridade da fonte.

Mantidos: 95 ocorrências inequívocas, 18 identificadores, 18 trechos com endpoints visíveis,
19 comprimentos explícitos e 20 exclusões por ambiguidade. Meta continua 100%, sem duplicatas
ou invenções; limites continuam 25 s nativo, 60 s OCR, 768 MiB Python, 256 MiB Tesseract e
1 GiB agregado. Sem alteração em interpretação, promoção, topologia, SQL ou PDF original.
Somente Tesseract local; nenhum OCR externo ou aumento global de DPI.

## Mudanças e decisões

- `pymupdf_analyzer.py`: extrator **1.11.0 → 1.12.0**, invalidando assinatura/cache derivado.
  Resultados com falha transitória de OCR não são gravados no cache, permitindo nova tentativa.
- `tesseract_ocr.py`: solicita TSV por `tessedit_create_tsv=1` e desativa texto simples por
  `tessedit_create_txt=0`. Dispensa o arquivo opcional `configs/tsv`, ausente no provisionamento
  observado por E01. Cabeçalho TSV obrigatório: saída vazia, texto simples ou esquema inválido
  gera falha observável; TSV válido sem palavras continua sendo resultado vazio legítimo.
  A capacidade incorpora `geracao_tsv` e `validacao_tsv`, invalidando caches do renderer antigo.
  `tesseract_runtime.py` e a porta neutra não precisaram mudar.
- Novo `pymupdf_orientation.py`: nas páginas densas, usa os eixos do texto parcial para orientar
  os nove recortes existentes. Exige pelo menos 20 caracteres e concordância de 80% em eixo
  cardinal, com tolerância angular de 5°; sem sinal suficiente mantém o giro original. O giro
  declarado da página é considerado. Não se deduz orientação pela NS, tamanho da folha ou
  conteúdo esperado. Na fonte de E01, as sete linhas nativas têm eixo `(0,-1)`, compatível com
  o controle visual de giro horário de 90°. Não acrescenta passagens OCR.
- `pymupdf_ocr.py`: desfaz o giro antes de normalizar caixas e usa origem/dimensões reais do
  pixmap, incluindo arredondamento dos pixels nas bordas do recorte. Evidências mantêm texto,
  confiança, assinatura/idiomas do motor, recorte e giro aplicado. A deduplicação de texto igual exige
  sobreposição espacial; códigos iguais próximos, mas sem sobreposição, continuam distintos.
  Em empate de confiança, prefere a caixa mais completa. Falha durante a grade preserva os
  recortes concluídos e informa onde parou e quantos ficaram sem leitura; não repete chamadas
  no runtime defeituoso nem apresenta o OCR localizado como concluído.
- Molduras `qu/re` com linha que retrace a mesma borda passam a ser reconhecidas. Segmento
  cruzado ou fora da borda continua rejeitado. Retificação corrige espelhamento e conserva os
  quatro cantos normalizados em polígono, inclusive em páginas com rotação declarada.
  Os limites de dimensão/vizinhança permanecem. Molduras excluídas da seleção localizada
  geram `analise.ocr_cobertura_parcial`; OCR geral não garante leitura dessas regiões.

A inspeção diferenciou símbolos pequenos de caixas de texto. Os 13 quadriláteros verdes
pequenos citados em E01 não justificam diminuir indiscriminadamente o limite de 7 pontos.
Há 76 caminhos verdes `qu+l`; 42 satisfazem os limites de moldura, mas nenhum inicia o grupo
de cabos que exige largura de 12 pontos. Ativar todas essas regiões acrescentaria dezenas
de chamadas; essa ampliação não foi adotada sem comprovar cobertura e custo. A decisão já
existente de executar OCR em página vetorial densa com cabeçalho nativo foi preservada.

Fixtures públicas: `tests/e07_pdf_fixtures.py`, `test_pymupdf_orientation.py`,
`test_pymupdf_frames.py`, `test_pymupdf_ocr_failures.py` e extensões em
`test_tesseract_ocr.py`. Cobrem giros cardinais, inclinação, texto parcial/vetores, recortes e
bordas, códigos repetidos por ocorrência, molduras retraçadas e controles negativos,
confiança/proveniência, falhas TSV/timeout, cancelamento e invalidação/recuperação de cache.
Os controles existentes de imagens/anotações permanecem no conjunto obrigatório.

## Comparação local e limites da avaliação

A auditoria textual privada compara o snapshot novo com `tmp/e01/inventory.json` e
`tmp/e01/baseline-final.json`, preservando correspondência um a um por evidência/offset.
Ela procura tokens intactos e localização na ROI com tolerância de 0,01. Isso mede presença
textual aproximada: não homologa categoria, situação ou associação operacional.

O inventário E01 guarda centros físicos dos anchors, que não são centros dos rótulos.
Usar distância centro-a-centro de 0,01 isoladamente rejeitaria textos deslocados junto ao
símbolo. Essa limitação está registrada no JSON da auditoria, sem alterar coordenadas,
denominadores ou tolerância de E01. Tokens ausentes de toda a extração demonstram omissão
independentemente dessa limitação. Ganho em propostas não substitui essa verificação.

Benchmark final isolado: `tmp/e07/benchmark-final.json`, logs `benchmark-final.log` e
`benchmark-final-stderr.txt` (vazio), memória `memory-final.json`, resumo `summary-final.json`.
Auditoria: `tmp/e07-review/extraction-coverage.json`, reproduzida por `compare_extraction.py`.
Não havia outros processos Python/Tesseract ao iniciar; 419 amostras, no máximo dois processos
Python (launcher e intérprete). Execução retornou zero e confirmou tamanho/mtime/SHA-256
inalterados: `1e824e972d5cfc0b19fbcae774321d371cff30f6a8d1dfcb3673db858e6c77df`.

| Medida | E01 | E07 final |
|---|---:|---:|
| Evidências nativas | 3.320 | 3.320 |
| Evidências com OCR | 3.593 | 3.590 |
| Evidências OCR | 273 | 270 |
| Propostas brutas com OCR | 8 | 12 |
| Propostas finais / relações | 3 / 0 | 7 / 1 |
| Confirmações / regiões / vãos | 0 / 4 / 0 | 1 / 7 / 0 |
| Diagnósticos com OCR | 0 | 1: cobertura parcial de 42 molduras |
| Tokens de ocorrência com correspondência um a um na ROI | 0/95 | 3/95 |
| Ocorrências sem código intacto em qualquer texto extraído | 95/95 | 80/95 |
| Identificadores intactos encontrados, sem certificar associação | 4/18 | 7/18 |
| Comprimentos textuais próximos ao segmento, sem certificar associação | 0/19 | 7/19 |
| Tempo total nativo (limite 25 s) | 15,882 s | 23,406 s |
| Tempo total OCR (limite 60 s) | 38,468 s | 53,959 s |

As três correspondências aproximadas de códigos são duas de poste e uma de estrutura MT.
Todos os 37 cabos continuam sem código intacto; sete comprimentos explícitos também não têm
token intacto em qualquer texto extraído. Os sete identificadores encontrados não atendem
à comparação estrita com o centro físico do anchor, pelas limitações de anotação já descritas.
Não se declara recall/precisão homologados, associação correta de endpoints ou zero duplicatas
na fonte real. A quantidade menor de linhas OCR, por si só, não mede ganho nem perda de leitura.

Tempos de extração/persistência: nativo 12,851 → 19,139 s; OCR 34,580 → 48,337 s.
Interpretação/promoção: nativo 2,549 → 3,516 s; OCR 3,282 → 4,901 s. O desempenho ficou
mais lento que E01, embora ainda dentro dos limites congelados. Não sobra orçamento para
acrescentar dezenas de chamadas sem redesenhar e medir a estratégia de recortes.

| Memória | E01 | E07 final | Limite |
|---|---:|---:|---:|
| RSS Python amostrado | 524,27 MiB | 493,95 MiB | 768 MiB |
| High-water do intérprete | 571,15 MiB | 539,85 MiB | 768 MiB |
| RSS Tesseract amostrado | 78,18 MiB | 81,79 MiB | 256 MiB |
| RSS agregado amostrado | 524,27 MiB | 493,95 MiB | 1.024 MiB |

Versões medidas: Python 3.12.14, PyMuPDF 1.28.0, Tesseract 5.4.0.20240606, `por+eng`,
OEM 3, PSM 11/10/7/6 e timeout de 90 s. DPI 450/1200/1800, grade 3 × 3 e sobreposição
0,025 preservados; interpretador continua 21.1. Assinatura do analisador OCR:
`ccd634c71a2110acede474bb66fdbc8311e87f7332781f4bede554f7a9f43f1a`.
Assinatura da capacidade Tesseract:
`a78dae0aa932b45a80a3cd128ad555e926cafd8ed16e7270e78902a6fae6a9d1`.
Hashes dos idiomas, configurações completas e assinatura nativa constam do resumo JSON.
O controle sintético real sem `configs/` recuperou o texto completo com confiança 0,90646,
registrado em `tmp/e07/tesseract-tsv-probe.json`. A execução exploratória anterior em
`orientation-benchmark.json` teve trabalho concorrente e não foi usada para aceitar desempenho.

**Bloqueio de aceite:** as omissões acima demonstram perda anterior à interpretação; as metas
de extração de E01 não foram atingidas. Os limites de tempo/memória e o hash foram atendidos,
mas isso não conclui E07. A ação de desbloqueio está no handoff abaixo.

## Validação e comandos

Conjunto obrigatório de E07, novas regressões e ferramentas de benchmark/smoke:
**151 aprovados em 27,31 s**, log `tmp/e07/required-tests.log`. Verificações privadas de
integridade E01: **3 aprovadas**. Ruff global e formatação: aprovados (341 arquivos).
Mypy: **324 arquivos, sem erros**. Integridade de dependências, fronteira do cliente magro
e complexidade E/F: aprovadas. `git diff --check`: aprovado.

Durante o desenvolvimento, testes novos revelaram duplicação de ocorrência na borda de
recortes e Mypy apontou imports/tipo de tupla nos testes. Esses problemas foram corrigidos
e os comandos repetidos com aprovação; os resultados finais acima substituem essas tentativas.
Uma tentativa da suíte pública com `--basetemp tmp/e07/pytest-public` falhou em portabilidade
por `WinError 3` em `CopyFile2`, devido aos caminhos temporários longos no Windows; foi
interrompida, sem ser considerada aprovada. O controle dos mesmos 25 testes passou com
`--basetemp C:\tmp\zph-e07-pathcheck-2156` (23,84 s; aviso de escrita no cache antigo).
A repetição integral usa diretório/cache curtos novos, seguindo `IniciarTestes.bat`, e arquivo
de cobertura próprio. Código de portabilidade não foi modificado.

Suíte pública completa adicional: **1.190 aprovados, 1 falha em 576,81 s**, cobertura
**87,69%** (mínimo 85,01% atingido), log `tmp/e07/public-tests-final.log`. O gate global
**não está aprovado**. A falha é
`test_qt_http_delayed_search_cannot_cross_input_or_connection_context[close]`, linha 904:
a lista de buscas inclui a consulta inicial além da consulta atrasada esperada. Esse teste
não lê PDFs nem exercita extração; o mesmo código passou na tentativa anterior e na
repetição isolada (**1 aprovado em 4,80 s**, `tmp/e07/http-retry.log`). Há evidência de
dependência de temporização, mas a estabilidade da suíte continua pendente; nenhum código
HTTP/Qt foi alterado nesta etapa. Desbloqueio: isolar a fase de preparação da busca atrasada
e verificar a sincronização do teste/fechamento, depois repetir o gate completo.

Todos os comandos abaixo partem da raiz, em PowerShell, com `.venv`. Dados reais, runtimes,
rasters, snapshots, scripts de transcrição e logs permanecem locais/ignorados sob `tmp/`.

```powershell
.\.venv\Scripts\python.exe -m pytest tmp/e01/test_inventory_local.py --basetemp tmp/e07/pytest-e01 -o cache_dir=tmp/e07/pytest-cache
.\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_tesseract_ocr.py tests/unit/test_tesseract_runtime.py tests/unit/test_analysis_cache.py tests/unit/test_pdf_coordinates.py tests/integration/test_document_analysis.py tests/unit/test_pymupdf_orientation.py tests/unit/test_pymupdf_frames.py tests/unit/test_pymupdf_ocr_failures.py tests/unit/test_benchmark_network_pdf.py tests/unit/test_smoke_examples.py --basetemp tmp/e07/pytest-required -o cache_dir=tmp/e07/pytest-cache
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy --cache-dir tmp/e07/mypy-cache
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/client_artifact_gate.py --source-only
.\.venv\Scripts\python.exe scripts/complexity_gate.py src
$env:QT_QPA_PLATFORM='offscreen'
$env:COVERAGE_FILE='tmp/e07/.coverage-final'
.\.venv\Scripts\python.exe -m pytest --cov --cov-report=term-missing --cov-fail-under=85.01 --basetemp C:\tmp\zph-e07-final-2158 -o cache_dir=C:\tmp\zph-e07-cache-2158
.\.venv\Scripts\python.exe -m pytest 'tests/integration/test_project_http_gateway.py::test_qt_http_delayed_search_cannot_cross_input_or_connection_context[close]' -q --basetemp tmp/e07/pytest-http-retry -o cache_dir=tmp/e07/pytest-http-cache
.\.venv\Scripts\python.exe tmp/e07/tesseract_tsv_probe.py
.\tmp\e07\monitor_benchmark.ps1
.\.venv\Scripts\python.exe tmp/e07-review/compare_extraction.py
.\.venv\Scripts\python.exe tmp/e07/summarize_benchmark.py
git diff --check
Get-FileHash -Algorithm SHA256 -LiteralPath 'examples/PROJETO DE REDE 1256148225.pdf'
```

O monitor reproduz `python -m scripts.benchmark_network_pdf` com a fonte de E01, saída em
`tmp/e07/benchmark-final.json` e runtime completo `tmp/e01/runtime`; inclui cadeia semântica,
promoção, regiões/vãos e controle sintético OCR real, com SQLite novo e sem cache.
Não inclui conformidade/SQL, HTTP/jobs ou UI. Monitor de memória a cada 200 ms; high-water
Python e picos amostrados dos subprocessos possuem os mesmos limites metodológicos de E01.
A repetição final deve ocorrer sem testes ou outros processos Python concorrentes.

## Handoff

Para desbloquear E07, implementar e medir uma estratégia de recortes para os códigos pequenos
e inclinados ainda omitidos, incluindo as molduras que não iniciam os grupos atuais. Avaliar
agrupamento regional e retificação que evitem uma chamada por rótulo, com controles negativos
e correspondência geométrica por ocorrência. Corrigir a avaliação dos rótulos de identificador
sem confundi-los com os centros físicos dos pontos. Repetir inventário/benchmark real e todos
os testes, cumprindo integralmente cobertura e orçamento antes de concluir E07.

E08 permanece pendente: descarte por identificadores, catálogo, associação poste/entrega,
múltiplos condutores e continuidades fora da folha não foram corrigidos nesta etapa. A
insuficiência da extração precede essas associações e não deve ser ocultada como falha de vão.
