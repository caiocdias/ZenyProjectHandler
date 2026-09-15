# E12 — Precisão dos extratores atuais

Execução em 15/09/2026 sobre `66b6146`. Git inicialmente limpo; nenhum `AGENTS.md`
aplicável encontrado na hierarquia ou nas pastas envolvidas. E10/E11 concluídas e
seus handoffs conferidos; a base corresponde à implementação E11 (extrator 1.15.0,
interpretador 23.0). As diferenças do diagnóstico antigo são as revisões E11,
não uma divergência não tratada do código. E08/E09 permanecem bloqueadas.

## Implementação vertical

- `pymupdf_revision_ocr.py` separa cores, linhas e células de molduras na aparência
  de uma revisão N4 já detectada. Preserva texto literal, confiança do motor,
  caixa normalizada, DPI, xref, presença de risco e transformação aplicada.
  Uma passagem adicional interpola somente linhas horizontais internas quase
  completas. A leitura sem tratamento também permanece no grupo; nenhuma consulta
  ao catálogo completa letras/algarismos. Cores de elementos vizinhos não são
  propagadas para outra célula. Molduras e sublinhados não viram riscos internos.
- `pymupdf_revisions.py` incorpora `color_readings` e sua versão ao JSON existente.
  Os dois grupos, hashes dos rasters, alternativas base/visível, cópia ampliada,
  autoridade desconhecida e decisão pendente são preservados. As novas leituras
  pertencem ao grupo de revisão, não entram como novos ativos. N4 continua com
  `operation_review_pending=true`: interpretar/reconciliar operações é trabalho
  posterior. Falha de uma passagem conserva as concluídas, marca `ocr_failed` e
  gera diagnóstico pelo mecanismo E11; o cache não prende essa falha transitória.
- `pymupdf_glyph_ocr.py` aceita os grupos longos já identificados pelo segmentador,
  antes descartados acima de 16 contornos. Lotes de códigos curtos mantêm sua
  composição; linhas longas usam lotes separados e não suprimem leituras curtas
  pelo critério de cobertura. Não entram no atlas de referência dos códigos curtos.
  A cor original dos contornos passa a acompanhar a evidência.
- Os glifos fracos deixam de ter corte nas primeiras 24 regiões. Podem receber
  passagens na resolução configurada, 1200 e 2400 DPI; confiança decide a tentativa
  conservada pelo mecanismo existente, sem equivaler a autoridade ou certeza.
  Correspondência de contornos existente continua sem catálogo.
- `pymupdf_ocr.py` processa sucessivos lotes de molduras. O limite de 48 regiões
  passa a valer por lote, com índices globais estáveis. Falha posterior conserva
  os lotes anteriores; região que não cabe ainda produz cobertura parcial explícita.
- `pymupdf_ocr_batch.py`, `pymupdf_symbols.py` e os demais extratores foram lidos.
  O contrato de mapeamento dos lotes e as classes de símbolos não precisaram mudar.
  Os oito grupos simbólicos E10 continuam sujeitos à revisão de convenção; não
  foram reclassificados para elevar contagens. Catálogo, associação e topologia
  não foram implementados nesta etapa.

## Memória, tempo, cancelamento e cache

O orçamento de glifos passa a ser por recorte/lote, sem somar todos os rasters já
concluídos. Dimensões são verificadas antes de renderizar o lote. Após OCR, `_Reading`
guarda somente dimensões/DPI e texto; o RGB é liberado. Permanecem os limites de
8 milhões de pixels por recorte/lote e 384 grupos elegíveis por página, com
diagnóstico para os grupos que excederem esses limites. O segmentador mantém seus
limites geométricos e grupos de até 64 caminhos: isso não prova cobertura universal.

`TesseractCliOcr` passa de 90 para **900 segundos por chamada**, configurável pelo
construtor e incluído na assinatura de capacidade. Não há teto global de execução,
nem seleção/aceite por duração. Esse timeout é uma proteção por subprocesso, não
uma promessa de leitura completa ao atingir o limite. Exceções de OCR preservam
evidência parcial e impedem reutilização como sucesso; diagnósticos estruturais
cacheáveis continuam explícitos, conforme o contrato existente.

Cancelamento permanece cooperativo nos pontos seguros do fluxo; não foi prometida
interrupção imediata de um subprocesso OCR. Regressões verificam propagação de
cancelamento, preservação de resultados parciais e cancelamento de um job com
relógio avançado em 20 minutos. Não foi usado sono de 20 minutos no teste.

Extrator **1.16.0**, interpretador **23.0**, contrato HTTP **1.5.0**. A versão e a
capacidade invalidam cache/snapshots derivados incompatíveis. Campos novos são
aditivos no JSON de revisão; não há migração SQL, escolha técnica automática ou
alteração do hash do grupo somente para acrescentar as leituras por cor. Regressões
conferem cache 1.15 incompatível, round-trip das leituras e repetição após falha.

## Comparação real isolada

Fonte E10 preservada: 988.018 bytes; SHA-256
`0793c292df9722ff48df31ab052018d4233ad3541706f50f53e994cc1670af06`.
Hash, tamanho e mtime iguais antes/depois. Python 3.12.14, PyMuPDF 1.28.0 e
Tesseract 5.4.0.20240606, `por+eng`, OEM 3, no runtime privado E10;
controle sintético funcional executado em cada benchmark.
Cada variante usa SQLite novo, sem cache de análise, até Resultados/XLSX.
Não houve Python/Tesseract concorrente durante as medições isoladas.

| Medida | Baseline E11 | Vertical final |
|---|---:|---:|
| Evidências totais / OCR | 2.047 / 228 | 2.065 / 246 |
| Propostas brutas / finais | 48 / 38 | 50 / 38 |
| Confirmações / linhas de Vãos | 9 / 7 | 9 / 7 |
| Chamadas OCR do PDF | 85 | 127 |
| Chamadas falhas / diagnósticos | 0 / 0 | 0 / 0 |
| Nativo até regiões/vãos (s) | 11,745 | 8,954 |
| Nativo incluindo exportação (s) | 14,485 | 10,903 |
| Extração/persistência OCR (s) | 124,567 | 115,267 |
| Pipeline OCR até regiões/vãos (s) | 129,464 | 119,290 |
| OCR incluindo exportação (s) | 132,632 | 121,711 |
| Pico Python por processo (MiB) | 380,16 | 379,94 |
| Pico Tesseract por processo (MiB) | 217,22 | 217,22 |
| RSS agregado amostrado (MiB) | 482,82 | 484,08 |

Amostragem de memória a cada 200 ms pode perder picos curtos; high-water por
processo e agregado amostrado são medidas diferentes. Uma execução de cada variante
não demonstra ganho de desempenho. Tempos são observabilidade, nunca critério de aceite.

### Ganhos e controles por ocorrência

| Referência | Baseline | Vertical / limite |
|---|---|---|
| R02, N4 verde/vermelho | Texto agregado sem caixas por cor; vermelho mal reconhecido | `N4(1)` em duas caixas, verde sem risco e vermelho com risco, preservados no grupo pendente |
| R02, células adjacentes | `N4(1)IN3(2)`, `S4RS3R` agregados | `N3(2)`, `S3R`, `11-600` verdes separados; `10-150` vermelho riscado; seis leituras exatas inspecionadas |
| R02, leituras sem tratamento | Não rastreadas por célula | `N4` parcial e `9-456` incorreto permanecem ao lado das tentativas tratadas, com revisão obrigatória; não são sucesso literal |
| R01, cabo revisado | Conflito E11 | `ABCN-35(70)` / `ABCN-16(16)` preservados; dois grupos com IDs iguais ao baseline, zero promoção conflitante |
| S3R inclinado | Caixa inclui margem/vizinhança | Polígono mais justo sobre as letras; recorte final inspecionado |
| N3 repetido em P1 | Duas inscrições adjacentes | Texto e representação repetida preservados; nova caixa inspecionada, sem fundir ativos |
| Bairro e cliente do rodapé | Literais truncados no OCR | Literais completos recuperados nos grupos longos, com ROIs inspecionadas; bairro ainda tem projeção truncada |
| Serviço/notas/quadro documental | Leitura geral e fragmentos | Vinte evidências de grupos longos adicionais; há variantes sem acento, fragmentos e duplicação documental a reconciliar |
| CA/CAA, TR-3-45, N-4 | Literais já presentes | Preservados sem completar/selecionar catálogo; defeitos de interpretação continuam |
| Identificadores e medidas | Cinco P e seis comprimentos | Preservados; extrair a medida não certifica vínculo, endpoints nem projeção |

O pareamento das 38 propostas verificou código, situação, identificador,
qualificador e comprimento. Duas geometrias mudaram (S3R/N3), ambas inspecionadas.
As duas propostas brutas adicionais provêm das leituras de notas (poste/aterramento)
e não passaram ao conjunto final. Não foram contadas como novos ativos corretos.

`comparison.json` percorre os **139 registros** e conserva os vínculos literais por
ROI antes/depois. Esse localizador usa texto/posição e não é um classificador de TP/FN:
centro de ponto físico pode ficar longe do rótulo; várias referências documentais
são descrições de presença, não transcrições literais. Nenhum candidato previamente
encontrado por esse localizador desapareceu. A auditoria adicional valida os campos
das propostas, grupos, literais de controle e medidas. Não se inferiu recall global
pela diferença de contagens. Permanecem os denominadores **29 operacionais, 64
documentais, nove pontos, dez trechos, seis comprimentos e dois grupos de revisão**.
Leitura exata integral continua **0/1**; E10/E15 não foram reclassificadas por esse ganho.

## Experiência rejeitada e falhas intermediárias

A primeira ampliação de grupos manteve o orçamento acumulado de 8 milhões de pixels:
43 grupos ficaram sem leitura, com diagnóstico, e a saída caiu para 19 propostas.
`vertical-1.json` registra essa variante **reprovada**. A correção liberou RGB já
processado e separou lotes curtos/longos; o resultado aceito é `streamed-1.json`.
Não se elevou o orçamento para ocultar a regressão nem se retiraram itens do inventário.

Na primeira suíte obrigatória, 172 testes passaram e dois testes novos falharam
porque o fake OCR geral introduzia outro código na fixture de revisão. O teste foi
isolado na leitura nativa/revisão pretendida e os 174 passaram. Mypy apontou duas
anotações e a assinatura do relógio fake; Ruff apontou formatação/importação;
complexidade reprovou a função de revisão. Tudo corrigido e reverificado.

A primeira tentativa do gate integral teve 776 aprovações e 506 erros de setup por
`PermissionError` em `C:\tmp\zph-basic-8232`; não constitui aceite. A repetição usa a
permissão de filesystem necessária para a raiz curta do gate canônico.

## Validações e comandos

`python` abaixo é `.venv/Scripts/python.exe`. Todos os PDFs, recortes, transcrições,
monitores e relatórios reais permanecem ignorados em `tmp/rede-1256407599/e12/`.
Os testes versionados são sintéticos; não usam as famílias reservadas E10.

```powershell
& tmp/rede-1256407599/e12/monitor-baseline.ps1
& tmp/rede-1256407599/e12/monitor-streamed.ps1
# Cada monitor chama, em processo isolado e observando memória:
.venv/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e12/streamed-1.json --runtime-directory tmp/e01/runtime --telemetry
.venv/Scripts/python.exe tmp/rede-1256407599/e12/compare.py
.venv/Scripts/python.exe tmp/rede-1256407599/e12/inspect_comparison.py
.venv/Scripts/python.exe tmp/rede-1256407599/e12/render_changed.py
.venv/Scripts/python.exe tmp/rede-1256407599/e12/verify_e12.py
.venv/Scripts/python.exe -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_pymupdf_ocr_failures.py tests/unit/test_pymupdf_ocr_batch.py tests/unit/test_tesseract_ocr.py tests/unit/test_analysis_cache.py tests/integration/test_document_analysis.py tests/unit/test_benchmark_network_pdf.py tests/unit/test_pymupdf_revision_ocr.py tests/unit/test_pymupdf_glyphs.py tests/unit/test_pymupdf_glyph_consensus.py tests/unit/test_pymupdf_ocr_page.py tests/unit/test_technical_revisions.py tests/server/test_jobs_api.py -q -p no:cacheprovider --basetemp tmp/e12-required-final
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy --cache-dir tmp/e12-mypy
.venv/Scripts/python.exe scripts/complexity_gate.py src
.\IniciarTestes.bat
git diff --check
```

Resultado direcionado final: **174 aprovados em 12,38 s**, saída zero; auditoria
privada `verified-audit.json` aprovada, fonte intacta. Ruff, formatação, Mypy (339
arquivos) e complexidade aprovados. Gate integral final: **1.282 testes aprovados
em 433,48 s, cobertura 87,83% (mínimo 85,01%), saída zero**. Dependências e cliente
magro também aprovados. Logs: `required-tests-final.log`, `full-gate-final.log` e
`relatorio-testes.txt`. A permissão adicional do gate foi aprovada; não há bloqueio
remanescente de execução. Nenhuma mudança de produção ocorreu após esse gate.

**E12 concluída**, no escopo vertical definido, com as lacunas abaixo entregues às
etapas seguintes. Isso não conclui E12A/E12B nem a leitura integral E15.

Arquivos de regressão: `test_pymupdf_revision_ocr.py`, `test_technical_revisions.py`,
`test_pymupdf_glyphs.py`, `test_pymupdf_ocr_batch.py`, `test_pymupdf_ocr_failures.py`,
`test_tesseract_ocr.py` e `tests/server/test_jobs_api.py`. Cobrem positivos/negativos,
CA/CAA e códigos incertos literais, rotação, geometria inversa, células adjacentes,
molduras vazias, cores não operacionais, falha parcial, orçamento antes do render,
retomada entre lotes, liberação de RGB, cache e cancelamento longo.

## Handoff obrigatório E12A/E12B e consumidores

- **E12A:** experimentar reconhecedor independente de Tesseract sobre coordenadas
  fragmentadas/`7` lido como `/`, cabeçalho/rodapé, notas, quadros de CHI/regulador e
  textos em aparências. O código cortado pelo rodapé continua incompleto: não completar
  seu sufixo por catálogo. Os erros exatos e ROIs privadas estão na comparação e nos
  snapshots; não copiar dados pessoais para fixtures públicas.
- **E12A:** comparar também segmentação de texto inclinado, colorido, sobreposto,
  fontes maiores/menores e riscos não horizontais. A nova passagem por célula é
  delimitada às revisões N4 detectadas e molduras horizontais; não foi homologada
  para qualquer anotação/fotografia ou layout. Símbolos E10 e realce amplo E09
  permanecem sem nova certificação. Não usar somente DPI/PSM como frente horizontal.
- **E12B:** reconciliar tentativas original/tratada, fontes geral/contornos e variantes
  documentais sem apagar as divergências. Acordo entre passagens correlacionadas não
  é voto independente. `N4`/`N4(1)` e `9-456`/`10-150` são exemplos concretos; preservar
  cor, risco, caixa, xref, transformação e grupo, com autoridade ainda desconhecida.
- **E13:** operações N4, TR-3-45, neutros N-4, duplicata D02, chave filtrada e associação
  U1/P5 continuam pendentes. Recuperação do literal não resolve catálogo nem ponto físico.
- **E14/E15:** topologia/identidades/projeção dos 36/83 m, endpoints de 14 m,
  qualificadores no XLSX, campos documentais truncados/duplicados e falta de campos
  individuais continuam pendentes. O novo literal completo de bairro não corrigiu
  sua projeção; serviço possui variantes duplicadas com/sem acento. Não homologar
  documentação ou cobertura automática integral a partir deste benchmark.

Casos reservados E10 não foram usados para ajuste ou avaliação nesta etapa.
Nenhum commit, publicação, consulta SQL operacional ou edição da fonte real.
