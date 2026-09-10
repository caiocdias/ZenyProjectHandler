# E05 — Rolagem independente dos painéis

Estado: **#concluida**, com aceite em 10/09/2026 após a retomada sobre `7dd6fbe`.
Os bloqueios da primeira execução foram resolvidos: gate completo aprovado, cobertura
87,32% e matriz visual aprovada nas oito combinações. O usuário autorizou as correções
e a conclusão após as validações, com subagentes. Nenhum commit ou publicação foi criado
nesta retomada.

## Estado inicial e coordenação

A primeira execução partiu de `897d85c`, com E04 integrada, Git limpo e divergência `0 0`.
Na retomada, a implementação anterior já estava no commit `7dd6fbe`; `git status --short`
continuava vazio e `git rev-list --left-right --count HEAD...origin/main` retornou `0 0`.
Não foram encontrados `AGENTS.md` na raiz, ancestrais aplicáveis ou sob os diretórios de
código, testes e documentação. Alterações preexistentes foram preservadas.

O índice e o detalhe foram recolocados em `#em-andamento` antes das correções. Um subagente
tratou exclusivamente os E2E; outro diagnosticou altura dos rótulos e corrigiu
`responsive_row.py`. A janela/PDF, testes de rolagem e documentação ficaram com o agente
principal. As inspeções visuais foram divididas por escala. Não houve edição simultânea
dos mesmos arquivos nem alteração das sobreposições previstas em E06.

## Arquivos e decisões da implementação

Sob `src/zeny_project_handler_client/ui/`:

- `panel_scroll.py`: viewport independente por painel, limites das tabelas, foco e roda.
  A retomada remove o alinhamento forçado `AlignTop` dos layouts internos: ele limitava
  rótulos ao `sizeHint()` mesmo quando o cartão tinha altura suficiente para o texto.
- `responsive_row.py`: empilha ações quando a largura não basta e recupera a linha ao
  expandir. Mensagens com quebra de linha usam a largura preferida para decidir a quebra,
  sem aumentar o mínimo intrínseco do painel. Isso evita uma coluna estreita de texto ao
  lado do botão de conformidade. Ordem, rótulos e operações permanecem preservados.
- `main_window.py`: instala os wrappers nos cinco docks, mantendo nomes, títulos, abas,
  flutuação e chamadas de `saveState/restoreState`. Sem alteração adicional na retomada.
- `project_panel.py`, `review_panel.py`, `documentation_panel.py`, `gmax_panel.py` e
  `project_market.py`: usam as linhas adaptáveis da primeira execução. Nenhuma mudança
  adicional nesses arquivos durante a retomada.
- `pdf_viewer.py`: a barra mantém os mesmos controles e callbacks, agrupados em navegação
  e zoom/rotação. Quando necessário, os dois grupos ocupam duas linhas. O mínimo central
  é 360 unidades lógicas; a regressão exige viewport do PDF de pelo menos 330×200.
  Isso resolve a soma dos mínimos em 911×512 sem comprimir o documento em uma faixa.
- `portability_panel.py` e `theme.py`: sem alteração. Exportar recebe o wrapper pela janela;
  barras, áreas e controles conservam paleta e estilos existentes nos dois temas.

O pipeline, API, persistência, renderização, jobs, cache, normas e sobreposições não mudaram.
A adaptação central limita-se à geometria da barra; não antecipa os realces de E06.

Tabelas, árvores e texto têm mínimo de nove linhas tipográficas mais 40 unidades e máximo
normal de quatorze linhas mais 40; listas usam cinco/dez linhas mais 40. Mínimos maiores
já existentes são respeitados. Adicionar registros não aumenta esses limites. As tabelas
conservam scroll horizontal próprio; o painel admite fallback horizontal se o usuário
reduzir um dock abaixo da largura intrínseca de uma ação indivisível.

A roda percorre a tabela/lista/texto até a borda e então continua no painel. Combos fechados
e campos numéricos não mudam pelo simples movimento da roda, mesmo com foco. O popup mantém
interação nativa. Tab sai das tabelas, as setas navegam internamente e o painel revela o foco.
Deltas de pixels também são tratados. Cada painel mantém posição independente do PDF/demais.

## Testes alterados e causas dos bloqueios

`tests/integration/test_panel_scroll.py` cobre os cinco docks com PDF sintético carregado,
roda angular/pixels, controles fechados e popup, bordas de tabela/texto, Tab até ações finais,
redimensionamento, flutuação, abas e restauração. A retomada acrescenta:

- Verificação de altura de cada rótulo visível contra `heightForWidth()`, em todas as abas.
  O mínimo geométrico do cartão, sozinho, não detectava o recorte interno.
- PDF carregado na matriz, dimensões úteis do viewport e recuperação da barra ao reduzir,
  expandir e restaurar o layout. O teste respeita a largura lógica disponível no monitor.
- Ativação explícita da janela flutuante antes de verificar foco/Tab no backend Windows.
- Capturas da janela completa e do dock ativo, além de metadados por cenário.

`tests/e2e/test_mvp_ui.py`: quatro testes falhavam também na base anterior. A renomeação
agora aguarda o carregamento inicial do mercado antes de capturar a identidade do DTO;
a ordem esperada inclui o cartão Mercado; GMAX aguarda a mesma execução da conformidade,
com mercado resolvido, e verifica banco/origem; a conformidade aguarda o término da leitura
assíncrona. O diagnóstico confirmou que o estado de erro GMAX observado era transitório
durante invalidação/releitura. As verificações finais de resultados e ações ambientais foram
preservadas; não foi alterada lógica de produção para acomodar esses testes.

A primeira execução também corrigiu a fixture de `tests/integration/test_review_panel.py`
para usar a NS sintética válida `0001234567`, compatível com a inicialização de mercado.

## Validação da retomada

Ambiente: Python 3.12.14, PySide6/Qt 6.11.1, Windows. `python` abaixo significa
`.\.venv\Scripts\python.exe`. Logs e capturas locais ficam em `tmp/`, ignorado pelo Git.

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_SCALE_FACTOR = '1'
$env:PYTHONUTF8 = '1'
python -m pytest tests/integration/test_window.py tests/integration/test_theme.py tests/integration/test_review_panel.py tests/integration/test_gmax_panel.py tests/integration/test_compliance_rules_panel.py tests/integration/test_portability_panel.py tests/integration/test_project_market_ui.py tests/integration/test_panel_scroll.py -q -o cache_dir=tmp/e05-accepted-focused-final-cache --basetemp=tmp/e05-accepted-focused-final
python -m pytest tests/e2e/test_mvp_ui.py -q -o cache_dir=tmp/e05-resume-e2e-cache --basetemp=tmp/e05-resume-e2e-full
python -m pytest --cov --cov-report=term-missing --cov-fail-under=85.01 -o cache_dir=tmp/e05-resume-full-cache --basetemp=C:\tmp\zph-e05-resume-20260910
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
python scripts/client_artifact_gate.py --source-only
python scripts/complexity_gate.py src
git diff --check
```

Resultados finais:

- **1.081 testes aprovados**, nenhuma falha, **87,32% de cobertura**, 647,53 s;
  `tmp/e05-resume-full.log`, saída zero. Toda alteração de produção estava presente antes
  desse gate. O ajuste posterior no teste de redimensionamento distingue o limite físico
  do Windows do backend offscreen; os dois caminhos foram validados nas execuções abaixo.
- **82 direcionados aprovados**, 102,46 s, incluindo a validação obrigatória dos seis
  módulos e as regressões de mercado/rolagem; `tmp/e05-accepted-focused-final.log`.
- **25 E2E aprovados**, 49,23 s, `tmp/e05-resume-e2e-full.log`, também incluídos no gate.
- Ruff e formatação aprovados (334 arquivos), Mypy aprovado (318 arquivos), complexidade
  aprovada (2.720 funções/métodos, nenhum rank E/F); logs
  `tmp/e05-accepted-{ruff,format,mypy,complexity}.log`.
- Dependências e fronteira do cliente aprovadas; `tmp/e05-resume-pip.log` e
  `tmp/e05-resume-client.log`. `git diff --check` aprovado.

As tentativas intermediárias permanecem nos logs: `tmp/e05-resume-focused.log` tinha 81
aprovados antes da última correção; `tmp/e05-accepted-focused.log` expôs a diferença entre
a tela virtual de 800 unidades do offscreen e o limite físico do Windows. A correção mantém
a expansão offscreen a 1920 e respeita o monitor somente no backend nativo. A execução final
de 82 testes substitui essa tentativa reprovada como evidência de aceite.

O gate usa os componentes de `IniciarTestes.bat`, com seu limiar de 85,01%, sem sobrescrever
o relatório anterior. O diretório curto em `C:\tmp` segue o próprio script e foi autorizado
pela revisão automática; evita erros de comprimento de caminho do Windows.

## Matriz visual e inspeções

Backend **Windows nativo**, com `QT_SCALE_FACTOR=1` e `1.5` em processos separados; DPR
medido nos metadados. As resoluções físicas são convertidas para dimensões lógicas. Não se
alterou a escala global do desktop nem se simulou a movimentação física entre monitores.
Essa validação cobre layout e rasterização nos dois DPIs efetivos.

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONUTF8 = '1'
$env:E05_CAPTURE_DIR = 'tmp/e05/accepted-visual'
$env:QT_SCALE_FACTOR = '1'
python -m pytest tests/integration/test_panel_scroll.py -q -o cache_dir=tmp/e05-accepted100-cache --basetemp=tmp/e05-accepted100
$env:QT_SCALE_FACTOR = '1.5'
python -m pytest tests/integration/test_panel_scroll.py -q -o cache_dir=tmp/e05-accepted150-final-cache --basetemp=tmp/e05-accepted150-final
```

Cada cenário inclui os cinco docks, todas as abas de Resultados/Documentação e estados
sintéticos vazio/extenso/carregando/erro, no topo e no fim da rolagem. Listas, árvores e
tabelas recebem 150 entradas; GMAX conserva seus dois checks fixos. Mensagens são longas;
o texto de regras tem 150 linhas. Esses estados são injeções visuais; os testes existentes
validam a lógica remota. O PDF sintético permite conferir a área central junto dos painéis.

Resultado nativo: **14 aprovados em 100% (78,01 s)** e **14 aprovados em 150% (81,39 s)**,
logs `tmp/e05-accepted100.log` e `tmp/e05-accepted150-final.log`. Além dos quatro cenários
visuais por escala, essas execuções validam roda, foco, popup, docks e restauração.

| Resolução física | DPR | Área cliente lógica | Viewport PDF lógico | Claro | Escuro |
|---|---:|---|---|---|---|
| 1366×768 | 1 | 1366×768 | 488×556 | Aprovado | Aprovado |
| 1920×1080 | 1 | 1920×1061 | 1042×889 | Aprovado | Aprovado |
| 1366×768 | 1,5 | 911×512 | 334×300 | Aprovado | Aprovado |
| 1920×1080 | 1,5 | 1280×707 | 402×495 | Aprovado | Aprovado |

A diferença de altura em tela cheia corresponde à moldura nativa. Todas as larguras são
exatamente as pedidas; os oito metadados registram listas vazias de cartões comprimidos
e rótulos recortados. O antigo excesso de 169 unidades na largura foi eliminado.

Evidência final: `tmp/e05/accepted-visual/`, com **512 imagens da janela, 512 imagens
dos docks** em `panels/` e **oito metadados**. Os **128 contatos** de
`tmp/e05/accepted-contacts/`, gerados por `tmp/e05-build-contacts.py`, foram todos abertos
e inspecionados: 64 por escala, cobrindo os quatro estados e ambos os temas/resoluções.
Relatórios: `tmp/e05-visual-review100.md` e `tmp/e05-visual-review150.md`.
Não houve recorte interno, sobreposição ou ação final oculta; tabelas/listas/regras
conservaram viewport limitado. Cortes nas bordas do viewport e elisão de colunas/abas
continuam sendo comportamentos normais com acesso por rolagem/teclado.
O agente principal conferiu também capturas da janela inteira, incluindo o PDF em 150%,
Conformidade/GMAX na janela menor, Projeto escuro, Resultados e Exportar na janela maior.
As imagens são evidência estática; a interação foi verificada pelos testes acima.

## Histórico e bloqueios resolvidos na retomada

A implementação original em `897d85c` terminou bloqueada: a janela exigia 1080×512 quando
o cenário pedia 911×512; mensagens também podiam sofrer recorte. O gate amplo com caminho
curto teve 1.076 aprovados, quatro falhas E2E e 87,08% de cobertura. Esses resultados eram
reprovados e não foram apresentados como aceite. Logs `tmp/e05-final-full.log`,
`tmp/e05-baseline.log`, `tmp/e05-handoff-retry.log`; capturas `tmp/e05/handoff-visual/`.
Uma tentativa anterior com caminho longo teve onze falhas adicionais de portabilidade.
Houve também um aborto isolado no encerramento da thread de Exportar, seguido de repetição
direcionada aprovada; não se atribui sua correção a mudanças inexistentes nesse arquivo.

Na retomada, a barra central em dois grupos resolve a largura; a remoção de `AlignTop`
resolve a altura dos rótulos; a largura preferida na decisão de empilhar resolve o status
de Conformidade. Evidência diagnóstica: `tmp/e05-review-hfw-{baseline,fixed}.log`,
`tmp/e05-review-row-matrix.log`, `tmp/e05-v2-150.log`. O teste novo de redimensionamento
inicialmente pediu 1920 unidades lógicas em monitor com aproximadamente 1280 disponíveis
a 150%; foi corrigido para usar a largura disponível, mantendo a exigência de 911 na redução.
Capturas `resume-visual`, `resume-visual-v2` e logs anteriores ao aceite são intermediários.

## Aceite e handoff

Não restam bloqueios ou validações obrigatórias pendentes de E05. A conclusão foi registrada
no índice e no detalhe somente após gate, testes direcionados, matriz nativa e inspeção
visual aprovados. A organização geral dos docks e o pipeline permanecem preservados.

Para E06, conservar os wrappers e a barra em dois grupos ao modificar `pdf_viewer.py`;
não reintroduzir mínimos que impeçam 911×512 nem alinhamento que recorte rótulos. Preservar
as regressões de roda/foco/abas e a separação entre banco, escolha do projeto e execução
histórica do GMAX. A migração física entre monitores não integra a evidência desta matriz.
Os artefatos locais são sintéticos e ignorados; nenhuma publicação ou commit foi realizado.
