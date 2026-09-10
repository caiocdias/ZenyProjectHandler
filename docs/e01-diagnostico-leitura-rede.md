# E01 — Referência de leitura de rede

Diagnóstico realizado em 10/09/2026, sobre `4ce5b50`. Não altera extração, interpretação,
promoção, catálogo ou projeção de produção. O checkout inicial estava limpo; `HEAD...origin/main`
era `0 0` contra a referência local, sem fetch. Entre a base do plano, `336afba`, e o checkout,
somente o roadmap foi acrescentado. Não foram encontrados `AGENTS.md` na hierarquia aplicável.

## Referência revisada e limites

Inventário privado em `tmp/e01/inventory.json`, transcrição em `tmp/e01/build_inventory.py`.
Ambos ficam ignorados, junto do PDF original, dos rasters, dos snapshots e dos logs. O inventário
registra página, geometria normalizada, ROI de revisão, código observado, situação, vínculo com
ponto/trecho, comprimento, ambiguidade e primeira fase de perda. Os centros são aproximações
manuais, com tolerância declarada de 0,01; as ROIs cobrem evidência e contexto, não são máscaras
de glifos. A geometria usa a página original, origem superior esquerda, sem modificar o PDF.

Revisão: página inteira, cinco recortes contíguos/sobrepostos a 1200 DPI, extremidades superior
e inferior e comparação das renderizações. Há 18 identificadores operacionais: 17 postes e um
endpoint de entrega junto à casa. Há também um endpoint existente sem identificador operacional
da mesma família. Não inferir material/formato de poste somente a partir de altura/resistência.

Denominadores congelados **antes de qualquer correção de produção**:

| Categoria | Instalar | Existente | Ocorrências inequívocas |
|---|---:|---:|---:|
| Poste | 14 | 3 | 17 |
| Estrutura MT | 18 | 4 | 22 |
| Estrutura BT | 16 | 3 | 19 |
| Cabo | 28 | 9 | 37 |
| Total | 76 | 19 | 95 |

Uma ocorrência é um código, categoria, situação e localização. Qualificadores de estruturas
permanecem distintos. Cabos distintos no mesmo trecho contam separadamente; não multiplicar
vãos físicos pelo número de condutores. Há 20 trechos físicos: 16 identificados e quatro
existentes sem rótulo de vão. Dezoito têm ambos os endpoints visíveis; dois continuam além da
folha. Dezenove têm comprimento explícito; um não tem comprimento legível. Nenhum comprimento
substituído foi identificado de forma inequívoca nesta fonte.

As **20 exclusões** são sete rótulos de equipamento e 13 grupos de símbolos: texto, geometria
e motivo estão preservados individualmente. A combinação de chaves reaproveitadas, referências
riscadas, discos coloridos e símbolos sem legenda não permite fixar classe/situação/quantidade
de equipamentos com segurança. Não confundir esses grupos com 13 equipamentos comprovados.
Os sete textos são legíveis; a exclusão se refere à classificação operacional completa.
Seu número não pode ser usado como recall de equipamento. Resolver essas ambiguidades exige
legenda/convenção do desenho e revisão técnica, sem diminuir os denominadores já fixados.

Casos negativos registrados: cercas e seus círculos, vegetação e instruções de poda/limpeza,
diâmetro/deflexão/esforço que não representam comprimento, cabeçalho e notas, fotografias e
carimbos de revisão, endpoint do consumidor que não é poste e continuidade fora da folha.

## Execução e perdas por fase

Composição conferida em `src/zeny_project_handler_server/composition.py` e padrão de persistência
em `tests/integration/test_interpretation_pipeline.py`. A ferramenta nova
`scripts/benchmark_network_pdf.py` usa `ExecutarAnaliseDocumento`,
`ExecutarPipelineInterpretacao` (incluindo promoção), `agrupar_regioes_da_analise` e
`detectar_vaos`, em SQLite novo por variante e sem cache. Não executa conformidade/SQL, HTTP,
jobs ou UI: a comparação mede a cadeia semântica solicitada, não a latência do servidor inteiro.
O observador dos analisadores delega as chamadas e mantém os resultados anteriores ao filtro
de identificadores. IDs estáveis permitem repetir a comparação. Snapshots incluem propostas,
decisões, evidências, diagnósticos, projeto promovido, regiões e vãos.

| Fase | Nativo | OCR real, runtime completo |
|---|---:|---:|
| Evidências | 3.320 | 3.593 |
| Texto / vetor / imagem / OCR | 10 / 3.294 / 16 / 0 | 10 / 3.294 / 16 / 273 |
| Após excluir anotações de revisão | 3.263 | 3.536 |
| Após excluir cabeçalho | 3.263 | 3.536 |
| Propostas brutas | 8 | 8 |
| Após filtro de identificadores | 0 | 3 |
| Propostas finais / relações | 0 / 0 | 3 / 0 |
| Elementos confirmados | 0 | 0 |
| Regiões / vãos | 0 / 0 | 4 / 0 |
| Diagnósticos retornados | 0 | 0 |

Evidência completa em `baseline-final.json`; a repetição dos filtros está em `phase-replay.json`.
O smoke obrigatório repetiu 3.320 evidências e zero propostas/relações/diagnósticos.

1. **Runtime:** o provisionamento oficial trouxe os idiomas para a pasta local, mas não
   `configs/tsv`. A chamada real registrou `read_params_file: Can't open tsv`, retornou código
   zero e texto simples; `_parse_tsv` produziu vazio. A primeira execução retornou zero OCR
   sem diagnóstico, apesar de versão e idiomas válidos. Preservada como
   `baseline-missing-tsv.json`, com probe/stdout/stderr. Copiar somente o arquivo de configuração
   TSV da instalação existente para a pasta temporária resolveu a dependência da bancada.
   O benchmark agora exige um controle OCR sintético funcional antes de analisar dados reais.
   O problema de provisionamento/diagnóstico do produto continua aberto para E07.
2. **Extração nativa:** 21 palavras PyMuPDF, 10 evidências de texto, glifos inválidos e 3.197
   desenhos. Nenhuma das 95 ocorrências inequívocas virou proposta bruta. As oito propostas
   brutas vieram de reconhecimento simbólico vetorial, não de códigos técnicos legíveis.
3. **Raster/OCR:** página A4 de 595 × 842 pontos, MediaBox = CropBox, rotação declarada zero;
   leitura visual requer giro horário de 90°. OCR geral devolveu 269 linhas sobretudo sem
   sentido técnico; o OCR localizado devolveu quatro identificadores de ponto (4/18), nenhum
   identificador de vão. Os detectores produziram zero círculos-alvo, 11 grupos de glifos azuis,
   zero quadros de cabo, zero quadros de equipamento e zero regiões de equipamento riscado.
   As 13 formas verdes simples `re/qu` medidas não atendem ao mínimo de largura de 7 pontos
   do detector; não generalizar isso como prova de que todas as molduras são retângulos simples.
   Guardas de cor, dimensão, representação vetorial e orientação precisam de fixtures em E07.
4. **Controle de orientação:** no mesmo recorte e a 450 DPI, Tesseract real sem giro produziu
   fragmentos; girado somente na bancada recuperou medidas e identificadores de vãos legíveis.
   `orientation-probe.json` registra ambas as saídas. Esse controle localiza perda na preparação
   do raster, mas não mede recuperação integral nem substitui o baseline sem alterações.
5. **Interpretação:** o filtro de identificadores descartou 8/8 propostas nativas e 5/8 com OCR.
   Depois dele, não houve redução adicional da contagem. As três propostas restantes são
   simbólicas, sem item de catálogo, e seus vínculos por proximidade não estão homologados.
6. **Promoção e vãos:** as três propostas sem catálogo não são promovidas. Não há cabos nem
   endpoints confirmados para `detectar_vaos`. A ausência final de vãos não comprova defeito
   da projeção: a cadeia já perdeu códigos e associações nas fases anteriores.

PyMuPDF e Poppler sem anotações exibiram a mesma rede. Poppler com anotações inclui fotos,
carimbos e quadros adicionais que o raster semântico exclui por design. Poppler retornou zero,
com avisos Flate e fontes Symbol/ArialUnicode; a fonte não foi regravada. Não foi constatada
perda visual da rede que explique o recall zero. Os avisos não devem ser tratados como prova
isolada de corrupção impeditiva.

## Métricas e orçamento congelados

- Meta das 95 ocorrências: recall e precisão de 100%, por categoria/situação, e zero duplicatas.
  Emparelhamento um a um exige categoria, código/qualificador, situação e mesma ocorrência
  geométrica; equivalências de catálogo precisam ser explícitas, sem relaxar a geometria.
- Meta dos 18 identificadores e dos 18 trechos com endpoints visíveis: identificação e associação
  corretas de 100%. Não inventar postes nas duas extremidades fora da folha.
- Meta dos 19 comprimentos explícitos: 100% de valor vigente e associação correta ao trecho.
  Preservar o único comprimento desconhecido; não converter diâmetro, ângulo ou esforço em vão.
- Baseline das 95 ocorrências: TP = 0, FN = 95, recall = 0% em ambos os fluxos, em todas as
  categorias/situações. Precisão dessas categorias é indefinida (0/0), não 100%. Há três
  propostas simbólicas fora desse denominador, sem precisão homologada. Confirmações e vãos
  recuperados = 0; endpoints = 0/18; comprimentos = 0/19. Duplicatas de ocorrências elegíveis
  = 0 porque nenhuma foi recuperada; isso não constitui aceite de deduplicação.

Máquina: Ryzen 7 5700U, 8 núcleos/16 threads, 16.486.035.456 bytes de RAM, Windows,
Python 3.12.14, PyMuPDF 1.28.0, Tesseract 5.4.0.20240606, `por+eng`, OEM 3,
PSM 11/10/7/6 e timeout de 90 s por chamada. Português com hash fixado do projeto;
hashes dos dois idiomas e assinatura do registro estão no snapshot. Extração 1.11.0,
interpretação 21.1; configurações padrão 450/1200/1800 DPI, grade 3 × 3, sobreposição 0,025.

| Medida | Nativo | OCR |
|---|---:|---:|
| Extração e persistência | 12,851 s | 34,580 s |
| Interpretação, promoção e persistência | 2,549 s | 3,282 s |
| Regiões e vãos | 0,0028 s | 0,0042 s |
| Total da variante | 15,882 s | 38,468 s |

Limites para E07/E08 nesta máquina e fonte: **25 s nativo; 60 s OCR; 768 MiB de RSS Python;
256 MiB de RSS Tesseract; 1 GiB de RSS agregado**. Congelados após medir o baseline, antes de
correções. Não aumentar esses limites para absorver regressão. O total inclui inicialização da
base e execução, mas exclui serialização final do JSON e controle OCR sintético; o monitor de
memória cobre também serialização e subprocessos. Comparações futuras devem usar esse escopo.

Monitor a cada 200 ms, sem outros trabalhos Python na execução final: 296 amostras, no máximo
dois processos Python (launcher do venv e intérprete) e um Tesseract. Pico Python amostrado
549.740.544 bytes; high-water do intérprete 598.896.640 bytes; pico Tesseract amostrado
81.973.248 bytes; pico agregado amostrado 549.740.544 bytes. O high-water não depende de capturar
o instante exato da amostra; o pico dos subprocessos é amostrado e pode subestimar picos curtos.
Arquivos: `memory-final.json`, `performance.json`, `cpu.json`, `ram.json`.

## Reprodução

Executar na raiz, em PowerShell. Todos os caminhos de dados abaixo são locais e ignorados.
O provisionamento precisa de rede para baixar somente o modelo público, nunca o PDF.

```powershell
git status --short
git rev-list --left-right --count HEAD...origin/main
git diff 336afba HEAD --stat
Get-FileHash -Algorithm SHA256 -LiteralPath 'examples/PROJETO DE REDE 1256148225.pdf'
.\.venv\Scripts\python.exe -c "from pathlib import Path; from zeny_project_handler.adapters.analysis.tesseract_runtime import provision_portuguese_language; print(provision_portuguese_language(Path('tmp/e01/runtime')))"
New-Item -ItemType Directory -Path tmp/e01/runtime/ocr/tessdata-fast-4.1.0/configs -Force
Copy-Item -LiteralPath 'C:/Program Files/Tesseract-OCR/tessdata/configs/tsv' -Destination tmp/e01/runtime/ocr/tessdata-fast-4.1.0/configs/tsv
.\.venv\Scripts\python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256148225.pdf' --output tmp/e01/baseline-final.json --runtime-directory tmp/e01/runtime
.\.venv\Scripts\python.exe -c "from pathlib import Path; from scripts.smoke_examples import executar_smoke_pdf; print(executar_smoke_pdf(Path('examples/PROJETO DE REDE 1256148225.pdf')))"
pdftoppm -f 1 -singlefile -scale-to 1500 -png 'examples/PROJETO DE REDE 1256148225.pdf' tmp/e01/poppler
pdftoppm -hide-annotations -f 1 -singlefile -scale-to 1500 -png 'examples/PROJETO DE REDE 1256148225.pdf' tmp/e01/poppler-semantic
.\.venv\Scripts\python.exe tmp/e01/build_inventory.py
.\.venv\Scripts\python.exe tmp/e01/reproduce_inspection.py
.\.venv\Scripts\python.exe tmp/e01/orientation_probe.py
.\tmp\e01\monitor_benchmark.ps1
.\.venv\Scripts\python.exe -m pytest tests/unit/test_smoke_examples.py tests/unit/test_benchmark_network_pdf.py --basetemp tmp/e01/pytest-run-validation -o cache_dir=tmp/e01/pytest-cache
.\.venv\Scripts\python.exe -m pytest tmp/e01/test_inventory_local.py --basetemp tmp/e01/pytest-inventory-validation -o cache_dir=tmp/e01/pytest-cache
.\.venv\Scripts\python.exe -m ruff check scripts/benchmark_network_pdf.py tests/unit/test_benchmark_network_pdf.py tests/pdf_fixtures.py
.\.venv\Scripts\python.exe -m ruff format --check scripts/benchmark_network_pdf.py tests/unit/test_benchmark_network_pdf.py tests/pdf_fixtures.py
.\.venv\Scripts\python.exe -m mypy
git diff --check
git check-ignore tmp/e01/inventory.json tmp/e01/baseline-final.json 'examples/PROJETO DE REDE 1256148225.pdf'
Get-FileHash -Algorithm SHA256 -LiteralPath 'examples/PROJETO DE REDE 1256148225.pdf'
```

Os scripts privados contêm a transcrição e o recorte observado; não existem em um clone público.
`reproduce_inspection.py` refaz os rasters e a contagem dos filtros a partir do snapshot;
`monitor_benchmark.ps1` reproduz o comando monitorado efetivamente usado, incluindo o launcher
do venv. Executá-lo sem outros processos Python/Tesseract para não contaminar a medição.
O benchmark público aceita qualquer PDF fornecido explicitamente, e os testes não exigem
`examples/`, Tesseract, português, rede ou dados privados. A nova fixture sintética é
`tests.pdf_fixtures.create_network_benchmark_pdf`: dois postes, cabo, identificador e comprimento.
Ela comprova promoção, persistência, regiões e vão, além de repetição com IDs estáveis.

## Validações e handoff

- Testes obrigatórios e novos testes: **8 aprovados**. Cobrem cadeia nativa sintética até vão,
  integridade da origem, limpeza da base temporária, IDs estáveis, recusa de sobrescrever a
  fonte, ausência do OCR português e saída vazia silenciosa do OCR.
- Fixture privada: **3 verificações locais aprovadas**, conferindo denominadores/exclusões,
  geometrias/endpoints e integridade/completude do baseline. Execução final conjunta:
  `python -m pytest tests/unit/test_smoke_examples.py tests/unit/test_benchmark_network_pdf.py tmp/e01/test_inventory_local.py --basetemp tmp/e01/pytest-final -o cache_dir=tmp/e01/pytest-cache`:
  **11 aprovados em 2,75 s**, log `tmp/e01/validation-final.log`.
- Smoke da fonte: aprovado, resultado acima; benchmark final com OCR real: código zero,
  controle sintético funcional e hash/mtime/tamanho pré/pós iguais.
- Ruff e formatação dos três arquivos Python: aprovados. Mypy: 308 arquivos, sem erros.
  `git diff --check`: aprovado. Nenhum código de produção modificado.
- Primeira tentativa Pytest falhou por acesso à pasta temporária/cache do usuário; foi repetida
  usando diretórios novos sob `tmp/e01/`, com aprovação. A primeira fixture escolhida não tinha
  item promovível; foi substituída por uma fixture sintética que realmente confirma e gera vão.
  Falhas iniciais de tipagem/formatação da ferramenta foram corrigidas e os checks repetidos.
- SHA-256 pré/pós coincide com o já documentado no roadmap. PDF, transcrição, coordenadas,
  fotos, rasters e snapshots permanecem ignorados. Sem commit, publicação ou alteração SQL.
- Gate global com cobertura/UI não executado: não é obrigatório para E01 e pertence à homologação
  integrada. Esta conclusão certifica o diagnóstico, não a qualidade atual da leitura automática.

E07 recebe: runtime TSV silencioso, orientação semântica, elegibilidade dos recortes por
dimensão/representação, cobertura de identificadores e códigos, manutenção das geometrias ao
girar/retificar. E08 recebe: descarte por identificadores, propostas simbólicas sem catálogo,
distinção entre poste/entrega, múltiplos condutores por trecho e continuidades sem endpoint.
As 20 ambiguidades continuam listadas e não podem desaparecer da avaliação. Novas fixtures de
produção devem ser sintéticas; não copiar texto, coordenadas, fotografias ou recortes reais.
