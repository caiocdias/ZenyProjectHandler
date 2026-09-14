# E09 — Homologação integrada

**Estado: #bloqueada para aceite.** Gate público aprovado; E08 e a falha de
realce simbólico demonstrada na inspeção real impedem concluir a homologação.

Execução em 14/09/2026 sobre `cd598bc`. Git inicialmente limpo. Não foi encontrado
`AGENTS.md` aplicável na hierarquia nem no repositório. Foram conferidos o roadmap
inteiro, os handoffs E01–E08, README, especificação funcional e testes de
integração/e2e. E01–E07 estão concluídas; o código e o handoff bloqueado de E08
estão integrados nessa revisão, sem divergência posterior não tratada. A inspeção
complementar encontrou um realce amplo de equipamento, detalhado adiante.

Por solicitação explícita, E09 passou a `#em-andamento` para executar as validações
independentes. Isso não concedeu aceite à dependência E08. Nenhuma meta, guarda,
norma, fixture pública ou assinatura foi reduzida para obter aprovação.

## Comportamento e documentação

O SQL fake inicializa a classificação; a escolha salva pelo técnico prevalece nas
reanálises. Rural/Urbano/Ambos persistem com proveniência e controle de versão.
Conflitos retornam `409 STALE_STATE`; reconexão reconcilia o estado sem repetir a
mutação. Troca de NS exige nova inicialização e descarta respostas antigas.

Ambos aplica a união das famílias, preservando os requisitos de cada regra.
Alterar o mercado torna a conformidade anterior desatualizada, conservando o
contexto histórico. A nova execução usa a escolha persistida. GMAX e a exportação
apresentam o snapshot correspondente; ler os painéis não consulta SQL.

Os cinco painéis mantêm rolagem própria e tabelas navegáveis. Marca-textos usam
25% de opacidade: verde instalar, amarelo existente, vermelho remover e azul
alterar. Seleção, rejeição e visibilidade têm estados próprios. O PDF exportado
preserva o contrato de anotações/callouts; não incorpora a camada de marca-textos
do visualizador nem modifica o original.

Foram corrigidas apenas divergências documentais: método de conformidade **14**,
extrator **1.14.0**, interpretador **22.0**, API/piso **1.4.0**, descrição dos
marca-textos e terceira aba **Contexto da execução** no XLSX de conformidade.
README agora registra o resultado e os limites atuais de E08. Contrato e versões
de execução permanecem os já validados; catálogo 2 e registro 1.6.0.

Arquivos alterados: `README.md`, `docs/especificacao-funcional.md`, índice/detalhe
de E09 no roadmap e este handoff. Não houve alteração de produção ou novo teste
público: os fluxos de integração já têm regressões sintéticas no gate; o caso
visual descoberto exige corrigir a evidência simbólica, sem ajuste arbitrário
da apresentação. Harnesses e capturas do PDF real permanecem em `tmp/e09/`.

## Gate público e integração isolada

`IniciarTestes.bat`: **saída 0**, **1.250 testes aprovados em 449,12 s**, cobertura
**87,71%**, acima do mínimo **85,01%**. Dependências, Ruff, formatação, Mypy,
fronteira do cliente magro e complexidade aprovados; **2.770 funções**, nenhuma
complexidade E/F. Relatório: `tmp/e09/gate-final.log` e `relatorio-testes.txt`.

O gate executa somente testes públicos/sintéticos. A busca nas fontes dos testes
não encontrou dependência do PDF motivador; a referência a `examples/` verifica
justamente que apenas seu README é rastreado. Não se utilizou banco operacional.

| Verificação | Evidência pública aprovada no gate |
| --- | --- |
| Inicialização SQL, falha/retry, cópia legada e restart | `tests/integration/test_persisted_market.py` |
| Escolhas, snapshots desatualizados, contexto histórico, NS ida/volta e concorrência | `tests/integration/test_persisted_market.py` |
| HTTP real, conflito, reanálise/restart e ausência de retry de PUT | `tests/integration/test_project_market_http.py` |
| Salvar/cancelar/falhar, reconectar, resposta atrasada, projeto/NS distintos | `tests/integration/test_project_market_ui.py` |
| União de mercados, regras comuns, resultados divergentes e guardas | `tests/unit/test_combined_market_compliance.py` |
| Criar/importar/analisar/revisar/reabrir; serviços e ações ambientais | `tests/e2e/test_mvp_ui.py` |
| Revisão humana, identidade, associação e negativos | `tests/integration/test_human_review.py`, `test_interpretation_pipeline.py`, `tests/unit/test_e08_association.py` |
| DTOs, XLSX e PDF anotado, inclusive folha rotacionada | `tests/server/test_deliverable_exports.py` |
| Rolagem e renderização/interação | `tests/integration/test_panel_scroll.py`, `test_pdf_viewer_progressive.py`, `test_compliance_callout_viewer.py`, `test_compliance_visibility.py` |

O gate foi executado com autorização da revisão automática para sua raiz
temporária curta `C:\tmp`; não houve rejeição de aprovação. Não foi feita
migração operacional, commit, release ou publicação.

## Benchmark com Tesseract real

PDF local da NS 1256148225, **1.607.552 bytes**, SHA-256
`1e824e972d5cfc0b19fbcae774321d371cff30f6a8d1dfcb3673db858e6c77df`.
O hash completo conferido consta também do JSON do benchmark. Runtime privado
E01 com português disponível e tessdata-fast 4.1.0. Execução isolada dos demais
testes, monitor de processos a cada 200 ms. Origem preservada.

| Tempo em segundos | Nativo | OCR real |
| --- | ---: | ---: |
| Extração/persistência | 12,487 | 46,209 |
| Interpretação/promoção/persistência | 2,497 | 13,009 |
| Total no escopo congelado E01 | **15,476** | **59,953** |
| Projeção de Resultados e exportação adicional | 2,997 | 2,704 |
| Total incluindo Resultados/exportação | **18,473** | **62,657** |

Os limites originais de E01 são 25 s nativo e 60 s OCR. O OCR ficou apenas
**0,047 s** abaixo de 60 s nesta medição; não há evidência de margem estável.
O total ampliado de 62,657 s é registrado separadamente e não é apresentado como
inferior a 60 s. A exportação adicional não existia no escopo temporal congelado;
não se subtraiu trabalho do total E01 nem se aumentou seu orçamento. Tempo dos
jobs HTTP/conformidade da execução complementar não integra essa medição.

Memória: **422 amostras**, high-water Python **598,59 MiB** (limite 768),
high-water observado Tesseract **80,46 MiB** (limite 256), soma simultânea amostrada
**527,93 MiB** (limite 1.024). Soma amostrada não é a soma dos picos individuais e
pode não captar picos entre amostras.

A auditoria repetiu a correspondência um a um por evidência primária, categoria,
código/qualificador e situação, usando as ROIs reconciliadas de E07 sem mudar
denominadores. Resultado: **95/95 ocorrências**, **95/95 vínculos operacionais**,
**18/18 identificadores** com token/geometria reconciliados preservados,
**18/18 pares visíveis de endpoints**, **18/19 comprimentos**. Nenhuma proposta
das categorias pontuadas ficou sem correspondência. A meta de comprimentos
continua reprovada; contagem de propostas não certifica classificação técnica.

Saída OCR: 3.719 evidências (399 OCR), 109 propostas brutas, **106 finais**
(95 inventariadas e 11 equipamentos fora desse denominador), 212 relações,
35 confirmações, 71 propostas conflitantes, 21 regiões, **28 linhas de Vãos** e
zero diagnósticos de execução. As 28 linhas por cabo não equivalem aos 20 trechos
físicos do inventário; tipos continuam desconhecidos onde falta classificação.

Artefatos: `benchmark-final.json`, `benchmark-final.log`,
`benchmark-final-stderr.txt`, `memory-final.json`, `performance-summary.json`,
`audit-final.json`, `audit-final.log` e `anchors-final.json`, sob `tmp/e09/`.
As três verificações privadas do inventário/baseline E01 também passaram em
0,74 s (`reference.log`), sem alterar o inventário original.
Smoke nativo complementar: **1 PDF disponível, 1 aprovado, 0 falhas**;
3.320 evidências, zero diagnósticos. Log `tmp/e09/smoke.log`.

## Fluxo complementar com a NS real

Servidor composto com armazenamento isolado em `tmp/e09/real-server`, adapters
SQL fake e OCR real. O upload e o job de análise produziram as mesmas 106
propostas e 28 linhas de Vãos do benchmark, comparadas por categoria, situação,
código, revisão, identificador e comprimento.

Foram salvas as três escolhas e provocados três conflitos de versão. Em cada
caso, o snapshot antigo conservou sua classificação e ficou desatualizado; a
nova conformidade e o XLSX refletiram a escolha salva. Achados: **Rural 1,
Urbano 8, Ambos 8**. A comparação por regra/alvo/estado comprovou que Ambos é a
união dos outros dois, sem duplicação. Esses números descrevem os alvos
disponíveis nessa leitura parcial; as guardas completas são cobertas pelos
testes públicos.

Foram baixados e conferidos por hash os três XLSX de conformidade, Resultados,
Documentação e PDF anotado. As abas de Resultados concordam com os DTOs em
**106 elementos e 28 vãos**. O XLSX de conformidade preserva a classificação na
terceira aba e o número de achados na primeira. A fonte permaneceu intacta.
No PDF exportado, as 13 anotações originais foram preservadas e o único callout
novo corresponde ao texto do snapshot (`real-pdf-verification.json`). A primeira
sondagem de anotações perdeu a referência da página no harness PyMuPDF; repetida
com a página mantida viva, a comparação passou, sem alteração do exportador.

Na primeira execução, o harness privado acessou incorretamente `summary` em vez
de `execution` e terminou com `KeyError` depois da análise e inicialização.
Corrigido o consumidor para o contrato existente, a repetição reutilizou o
projeto persistido e concluiu com saída 0. Isso não exigiu mudança da API.
`real-http-harness-error.log` preserva a falha; `real-http.log` registra a execução
aprovada. Na retomada houve zero consultas ao classificador, confirmando uso da
classificação persistida. Não houve consulta de ações aplicável nesse PDF; os
casos de resposta/falha de ações estão no gate público.

Evidências privadas: `prepare_real.py`, `real-session.json`,
`real-project.json`, `real-snapshots.json`, `real-union.json` e exportações
`real-*.xlsx`/`real-*.pdf`, sob `tmp/e09/`.

## Inspeção visual

Matriz sintética E05 repetida com Qt nativo Windows: 1366×768 e 1920×1080,
temas claro/escuro, escalas 100/150%, cinco painéis e estados vazio, carregando,
erro e dados extensos. **14 testes aprovados por escala** (56,78 s e 56,49 s).
Metadados dos oito cenários sem cartões comprimidos ou rótulos internamente
cortados. Foram geradas 512 capturas da janela e 512 dos painéis; inspeção manual
dos oito mosaicos, com 64 capturas selecionadas. Não se alega inspeção individual
de todas as 1.024 imagens. Elipse de tabela e corte no limite da área rolável são
comportamentos esperados, com conteúdo acessível por navegação/rolagem.

Matriz sintética E06: **24 casos**, dois temas × zoom 50/100/200% × rotações
0/90/180/270°, 11 marca-textos, um callout, 49 tiles a 200%, opacidade 25% e hash
preservado. Dois mosaicos inspecionados, além de detalhes individuais a 200% nos
dois temas. A fonte Segoe UI foi carregada no harness offscreen para a legenda.
Metadados brutos deixam `human_review=pending`; este relatório registra a
inspeção humana efetivamente realizada, sem reescrever o resultado automatizado.

A matriz nativa conectada ao servidor HTTP com a NS real terminou com **oito
testes aprovados**: quatro a 100% em **702,66 s** e quatro a 150% em **738,18 s**.
Asserções de reabertura/reconexão em Ambos, zero consultas SQL na leitura,
106 propostas/28 vãos, seleção e alternância de visibilidade, navegação de vão,
rolagem independente e mínimos de viewport passaram. Os cinco casos de
navegação por cenário cobrem poste, MT, BT e cabos existentes/a instalar.

Foram geradas **296 capturas** (128 janelas, 128 painéis e 40 navegações), além
de **24 capturas reais de zoom/rotação** nos dois temas. Esta matriz usa 106
marcações, um callout e zero/quatro tiles conforme o zoom. As quatro situações
são exercitadas na fixture sintética; a NS contém 83 propostas a instalar e
23 existentes. Inspecionados os oito mosaicos dos painéis, os dois mosaicos de
zoom/rotação reais e dois recortes individuais de navegação (cabo instalar no
claro e poste instalar no escuro). Não se afirma inspeção individual de todas
as capturas, nem troca física entre monitores: a escala Qt é isolada por processo.

Capturas/metadados: `tmp/e09/panels-real/`, `highlights-real/`,
`real-visual-metadata.json` e `visual-inspection-final.json`. Asserções de
interação/rolagem passaram; **o aceite visual da NS falhou** pelo caso a seguir.

**Falha de aceite visual demonstrada:** no recorte de navegação do cabo a instalar
de V6-7, a área verde ampla pertence à proposta conflitante de **Para-raios MT**,
uma das 11 propostas de equipamento fora do denominador de 95. Seu `link_geometry`
é uma caixa normalizada de `(0,448336; 0,566187)` a `(0,488874; 0,634881)`, que
engloba o trecho e rótulos vizinhos. O rótulo do cabo tem polígono próprio pequeno;
não é ele que produz o preenchimento amplo.

Rastreio: `adapters/analysis/pymupdf_symbols.py` emite a união das primitivas
`35,2098,2099,2100,2102,2104` como evidência `PARA RAIOS MT`; a proposta e
`review_api.py` preservam a caixa, e `pdf_viewer.py` preenche `link_geometry`.
O recorte original inspecionado mostra que essa caixa abrange linha e rótulos,
não uma área de identificação localizada. A proposta não foi promovida a ativo;
continua conflitante e revisável. Isso não satisfaz o aceite visual de E09.
A auditoria complementar encontrou oito evidências simbólicas, todas com
primitivas curvas no agrupamento (`symbolic-geometry-audit.json`). Isso orienta
a regressão de glifos/linhas, sem presumir que toda curva seja símbolo inválido.

Evidência privada: `wide-highlight.json`, `wide-highlight-source.png` e
`panels-real/1366x768-1-claro/navigation-CABLE-INSTALL.png`. **Desbloqueio:**
reproduzir a assinatura de primitivas e os glifos vizinhos em fixture com
controles negativos, corrigir reconhecimento/geometria na origem, verificar os
demais equipamentos e repetir projeção/inspeção real. Não ocultar equipamentos,
substituir a caixa pelo poste próximo ou escolher um limite de área só para
aprovar a imagem. É trabalho de extração/interpretação além da correção de
integração de E09 e precisa retornar ao aceite de E07/E08 pertinente.

## Impedimentos e aceite global

O bloqueio é demonstrado em E08 e reproduzido nesta etapa: T02/V2-3 permanece
sem associação automática inequívoca dos **13 m**, resultando em **18/19**.
A diferença de score aproximada 0,0039918 não satisfaz a guarda 0,004. A ocorrência
e a ambiguidade continuam revisáveis; não se alterou o limiar para essa folha.

Também falta evidência técnica para escolher formato/material dos postes e
classe PADRAO nas entregas. Proximidade de casa ou poste não substitui essa
evidência (ADR 0015). A representação por cabo ainda precisa do aceite do
agrupamento físico preservando situações/condutores. São pendências distintas:
classificação exige evidência técnica; associação e representação exigem trabalho
de software e regressões, não apenas autorização.

**Impacto:** E08 não satisfaz seu aceite e E09 não pode afirmar recuperação
integral, conformidade técnica ou aceite visual da NS. **Desbloqueio:** concluir
os casos de E08 e o realce simbólico com evidência, fixtures sintéticas e controles
negativos, preservar revisão humana, repetir benchmark/metas e o aceite integrado
na revisão resultante. PDF/OCR/SQL operacional não são impedimentos desta execução.

| Item da definição global | Estado e evidência |
| --- | --- |
| SQL inicial, escolhas, persistência, reconexão, reanálise, NS/conflitos | Aprovado pelo gate HTTP/Qt e pelo fluxo real complementar |
| Ambos, guardas, unicidade e snapshots | Aprovado pelo gate, união real e três XLSX |
| Rolagem independente e legibilidade | Aprovado: 28 testes sintéticos, oito cenários HTTP reais e mosaicos inspecionados |
| Marca-textos, navegação, seleção, filtros, zoom/rotação/callouts | Interação/geometria sintética aprovada; **aceite visual real reprovado pela caixa ampla de equipamento** |
| Omissões/inventário e metas E01 | **Reprovado: 18/19 comprimentos; classificação/representação pendentes de E08** |
| Gate, documentação/contrato, benchmark/inspeção local | Executados e rastreáveis; gate aprovado, inspeção local com falha explícita |

## Comandos de reprodução

Na raiz do repositório, PowerShell, Python 3.12.14 da `.venv`:

```powershell
git status --short
git log -3 --oneline
$env:PYTHONPATH=(Get-Location).Path
$env:PYTHONUTF8='1'
# Executado isoladamente; Start-Process -WindowStyle Hidden, amostragem 200 ms.
& ./tmp/e09/monitor_benchmark.ps1
# Comando invocado pelo monitor:
# .\.venv\Scripts\python.exe -m scripts.benchmark_network_pdf "examples/PROJETO DE REDE 1256148225.pdf" --output tmp/e09/benchmark-final.json --runtime-directory tmp/e01/runtime
.\.venv\Scripts\python.exe tmp/e09/audit_semantic.py tmp/e09/benchmark-final.json
.\.venv\Scripts\python.exe -m pytest tmp/e01/test_inventory_local.py --basetemp=tmp/e09/reference -p no:cacheprovider -q
$env:PYTEST_ADDOPTS='-o cache_dir=tmp/e09/gate-cache'
.\IniciarTestes.bat *> tmp/e09/gate-final.log
$env:QT_QPA_PLATFORM='windows'
$env:E05_CAPTURE_DIR=(Join-Path (Get-Location) 'tmp/e09/panels-synthetic')
$env:QT_SCALE_FACTOR='1'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_panel_scroll.py -q -p no:cacheprovider --basetemp=tmp/e09/p100 *> tmp/e09/panels100.log
$env:QT_SCALE_FACTOR='1.5'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_panel_scroll.py -q -p no:cacheprovider --basetemp=tmp/e09/p150 *> tmp/e09/panels150.log
$env:QT_QPA_PLATFORM='offscreen'
$env:QT_SCALE_FACTOR='1'
@'
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from scripts.visual_qa_review_highlights import capture
app = QApplication.instance() or QApplication([])
QFontDatabase.addApplicationFont('C:/Windows/Fonts/segoeui.ttf')
capture(Path('tmp/e09/highlights-synthetic').resolve())
'@ | .\.venv\Scripts\python.exe - *> tmp/e09/highlights.log
.\.venv\Scripts\python.exe scripts/smoke_examples.py *> tmp/e09/smoke.log
.\.venv\Scripts\python.exe tmp/e09/prepare_real.py *> tmp/e09/real-http.log
$env:QT_QPA_PLATFORM='windows'
$env:ZENY_TESSDATA_DIR=(Resolve-Path tmp/e01/runtime/ocr/tessdata-fast-4.1.0).Path
$env:QT_SCALE_FACTOR='1'
.\.venv\Scripts\python.exe -m pytest tmp/e09/test_real_ui.py -x -q -p no:cacheprovider --basetemp=tmp/e09/r100 *> tmp/e09/real-ui100.log
$env:QT_SCALE_FACTOR='1.5'
.\.venv\Scripts\python.exe -m pytest tmp/e09/test_real_ui.py -x -q -p no:cacheprovider --basetemp=tmp/e09/r150 *> tmp/e09/real-ui150.log
.\.venv\Scripts\python.exe tmp/e09/collect_visual.py
git diff --check
git status --short
```

Scripts privados pressupõem inventário/runtime/artefatos locais E01/E07; não são
requisitos do gate público. Capturas, PDF e dados de execução devem permanecer
ignorados. As métricas acima pertencem à revisão `cd598bc`; alterações posteriores
de comportamento exigem nova validação pertinente.

Conferência final: `git diff --check` aprovado; quatro arquivos documentais no
status, nenhum diff em `src/`, `tests/` ou `scripts/`, nada no índice. PDF,
capturas e relatórios privados confirmados como ignorados. Hash da origem
novamente conferido após as oito sessões HTTP. Nenhuma validação obrigatória
foi omitida; o aceite global permanece reprovado pelos impedimentos descritos.
