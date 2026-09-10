# E05 — Rolagem independente dos painéis

Execução em 10/09/2026 sobre `897d85c`. Estado: **#bloqueada para aceite**.
Implementação disponível no checkout, sem commit ou publicação. A matriz reduzida e o gate
público ainda impedem marcar a etapa concluída.

## Estado inicial e arquivos

Não foram encontrados `AGENTS.md` na raiz, ancestrais aplicáveis ou sob `src/`, `tests/` e
`docs/`. `git status --short` estava vazio; `git rev-list --left-right --count HEAD...origin/main`
retornou `0 0`. E04 já estava em `897d85c`; nenhuma alteração preexistente foi sobrescrita.
O índice e o detalhe de E05 passaram por `#em-andamento` antes da implementação.

Arquivos de produção alterados, sob `src/zeny_project_handler_client/ui/`:

- `panel_scroll.py` (novo): área independente, limites de tamanho, teclado e encaminhamento
  da roda. `main_window.py` instala esse wrapper nos cinco docks existentes.
- `responsive_row.py` (novo): layout de ações que calcula altura conforme a largura e
  empilha controles quando a linha não cabe, sem ocultar botões ou mudar sua ordem.
- `project_panel.py`, `review_panel.py`, `documentation_panel.py`, `gmax_panel.py` e
  `project_market.py`: somente uso do layout de linhas adaptáveis. Em E04, a alteração do
  mercado limita-se ao layout; chamadas, persistência e estados permanecem intactos.
- `portability_panel.py` e `theme.py` não precisaram de alteração: Exportar recebe o wrapper
  na janela, e as áreas/barras herdam a paleta e os estilos existentes nos dois temas.
- `pdf_viewer.py` termina **sem diff**. O ensaio local de quebra da barra central foi
  revertido após inspeção mostrar o PDF estreito demais; sobreposições de E06 não foram editadas.

Testes: `tests/integration/test_panel_scroll.py` (novo) e correção da fixture em
`tests/integration/test_review_panel.py`: NS sintética `0001234567` substitui nome livre
incompatível com a inicialização de mercado já integrada. Nenhuma regra do pipeline mudou.
Documentação: este handoff, README e índice/detalhe do roadmap.

## Decisões de interação

Cada `QDockWidget` conserva nome, título, recursos, abas e chamadas de `saveState/restoreState`.
O mínimo de conteúdo pertence ao scroll, em vez de impor a altura inteira à janela. Os cartões
e rótulos mantêm seus layouts; mensagens longas quebram linhas e o mínimo é recalculado.
Não há scroll global nem alteração na ordem dos docks.

Tabelas/árvores/texto têm mínimo de nove linhas tipográficas mais 40 unidades lógicas e máximo
de quatorze linhas mais 40; listas usam cinco/dez linhas mais 40. Mínimos maiores já existentes
são respeitados. O número de registros não aumenta esses limites. As colunas continuam com
rolagem horizontal própria; uma barra horizontal externa serve de fallback caso o usuário
reduza o dock abaixo da largura intrínseca de uma ação indivisível.

Roda sobre combo fechado ou spin encaminha ao painel mesmo com foco, sem alterar o valor.
O popup mantém roda e teclado nativos. Tabelas, árvores, listas e texto usam a própria rolagem
enquanto houver espaço no sentido solicitado; nas bordas, encaminham ao painel. Deltas de
pixels também são tratados pelo wrapper. Tab deixa a tabela sem exigir percorrer centenas de
células; setas preservam navegação interna. O foco é revelado pela área de rolagem.

## Validações e comandos

Ambiente: Python 3.12.14, PySide6/Qt 6.11.1, Windows. Nos comandos abaixo,
`python` significa `.\.venv\Scripts\python.exe`. Logs e capturas ficam em `tmp/`, ignorado.

```powershell
python -m pytest tests/integration/test_window.py tests/integration/test_theme.py tests/integration/test_review_panel.py tests/integration/test_gmax_panel.py tests/integration/test_compliance_rules_panel.py tests/integration/test_portability_panel.py tests/integration/test_project_market_ui.py tests/integration/test_panel_scroll.py -q -o cache_dir=tmp/e05-handoff-retry-cache --basetemp=tmp/e05-handoff-retry
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pip check
python scripts/client_artifact_gate.py --source-only
python scripts/complexity_gate.py src
git diff --check
```

Resultado direcionado da implementação mantida: **81 aprovados**, 82,80 s, em
`tmp/e05-handoff-retry.log`, incluindo regressão contra sobreposição das ações de mercado.
Uma tentativa anterior abortou no encerramento da thread de Exportar (`_thread_finished`,
linha 399), log `tmp/e05-handoff.log`; a repetição integral passou. Não se afirma ter corrigido
essa instabilidade, e o arquivo de Exportar não foi alterado.
Ruff e formatação passaram; Mypy aprovou 318 arquivos; dependências e fronteira do cliente
passaram; complexidade aprovou 2.720 funções/métodos, sem ranks E/F. Logs
`tmp/e05-{ruff,format,mypy,complexity,pip,client}-final.log`. `git diff --check` passou.
Testes novos verificam cinco docks,
PDF sintético carregado, posição/zoom, roda angular/pixels, combos/spins, popup, bordas de
tabela/texto, ações finais por Tab, redimensionamento, flutuação, abas e restauração.

O gate amplo inicial usou:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest --cov --cov-report=term-missing --cov-fail-under=85.01 -o cache_dir=tmp/e05-full-cache --basetemp=tmp/e05-full
```

Resultado: **1.064 aprovados, 15 falhas, 86,75% de cobertura**, 514,23 s;
`tmp/e05-full.log`. Quatro falhas são E2E; onze envolvem publicação/cópia de arquivos de
portabilidade em caminhos longos. Esse resultado é diagnóstico intermediário, não aceite.

Repetição com caminho curto, como prevê `IniciarTestes.bat`:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHONUTF8 = '1'
python -m pytest --cov --cov-report=term-missing --cov-fail-under=85.01 -o cache_dir=tmp/e05-final-cache --basetemp=C:\tmp\zph-e05-final-20260910
```

Log: `tmp/e05-final-full.log`: **1.076 aprovados, quatro falhas, cobertura 87,08%**, 472,53 s.
O caminho curto eliminou as falhas de portabilidade. Permaneceram exatamente os quatro E2E
listados abaixo; o gate é **reprovado**, apesar da cobertura acima do mínimo. Essa execução
precede o última correção do layout de ações responsivas; depois dele foram repetidos
os testes direcionados e a matriz, não todo o gate já bloqueado pelas mesmas quatro falhas.
O uso de `C:\tmp` foi autorizado
pela revisão automática da execução; não foi necessário alterar sandbox, pipeline ou arquivos
do usuário. O script `.bat` não foi chamado diretamente, para manter o relatório anterior.

Controle de divergência: `git archive --format=zip --output=tmp/e05-baseline.zip HEAD` e
`Expand-Archive -LiteralPath tmp/e05-baseline.zip -DestinationPath tmp/e05-baseline`.
Na cópia, com `PYTHONPATH` apontando para seu próprio `src`, executar o Python da `.venv`
principal em `tests/e2e/test_mvp_ui.py tests/integration/test_project_portability.py` reproduziu
as quatro falhas E2E e falhas de cópia: **34 aprovados, 16 falhas**, `tmp/e05-baseline.log`.
O caminho ainda mais longo dessa cópia explica uma falha de portabilidade adicional; a
comparação não é apresentada como gate limpo nem como correção de portabilidade.

Falhas preexistentes confirmadas em `tests/e2e/test_mvp_ui.py`:

- `test_rename_dialog_preserves_session_on_cancel_and_uses_current_version`: compara
  identidade (`is`) de um DTO substituído pela leitura assíncrona do mercado.
- `test_project_service_codes_ui_is_remote_canonical_accessible_and_conflict_safe`: espera
  a sequência de cartões anterior à introdução de Mercado.
- `test_environmental_actions_full_client_matrix_uses_current_service_codes`: estado GMAX
  indisponível quando o teste exige resultado atual.
- `test_user_can_create_import_analyze_review_and_reopen_from_ui`: estado de conformidade
  ainda atualizando quando o teste exige resultado atual.

Não foram modificados esses testes nem o fluxo de E04 para fazer o gate passar em E05.

## Matriz visual

Capturas nativas do Qt no Windows, sem alterar a escala global do desktop. `QT_SCALE_FACTOR`
força DPR 1 e 1,5 em processos separados; a janela simula as duas resoluções físicas. Isso
verifica rasterização e layout em DPI distintos, mas não simula mover fisicamente uma janela
entre dois monitores com escalas diferentes.

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:E05_CAPTURE_DIR = 'tmp/e05/handoff-visual'
$env:QT_SCALE_FACTOR = '1'
python -m pytest tests/integration/test_panel_scroll.py -k visual_matrix -q -o cache_dir=tmp/e05-handoff100-cache --basetemp=tmp/e05-handoff100
$env:QT_SCALE_FACTOR = '1.5'
python -m pytest tests/integration/test_panel_scroll.py -k visual_matrix -q -o cache_dir=tmp/e05-handoff150-cache --basetemp=tmp/e05-handoff150
```

Cada uma das oito combinações contém os cinco docks, todas as abas de Resultados/Documentação,
estados sintéticos vazio/extenso/carregando/erro e capturas no topo/fim: 512 PNGs por matriz
completa. Listas/árvores/tabelas recebem 150 entradas, exceto os dois checks fixos do GMAX;
mensagens são longas e o texto de regras tem 150 linhas. Os estados visuais são uma injeção
sintética de conteúdo; os testes existentes cobrem a lógica remota desses estados.

| Resolução física | DPR | Área cliente medida (lógica) | Claro | Escuro |
|---|---:|---|---|---|
| 1366×768 | 1 | 1366×768 | Validada | Validada |
| 1920×1080 | 1 | 1920×1061 | Validada | Validada |
| 1366×768 | 1,5 | **1080×512**, pedido **911×512** | **Reprovada** | **Reprovada** |
| 1920×1080 | 1,5 | 1280×707 | Validada | Validada |

A diferença de 19/13 unidades na altura em tela cheia corresponde à moldura nativa. Já a
diferença de **169 unidades na largura** em 1366×768/150% é um defeito de aceite real.
O visualizador central pede mínimo de 565 unidades lógicas nesse cenário; os mínimos dos
docks/títulos e separadores completam 1080. As capturas dessa linha excedem a resolução
pretendida e **não** comprovam que a aplicação cabe na tela pedida.
Na inspeção desse extremo reprovado também há recorte em mensagens longas de Projeto/GMAX;
o mínimo geométrico de um cartão não prova que todo o texto interno esteja visível.

Metadados por cenário: `metadata.json`, com backend, DPR, largura/altura pedidas e efetivas,
mínimo central e cartões comprimidos. A matriz anterior, válida para diagnóstico desse
limite, está em `tmp/e05/native-final-v2/`; inspeções por contato em `tmp/e05/contact-sheets/`.
A matriz final fica em `tmp/e05/handoff-visual/`; logs `tmp/e05-handoff100.log` e
`tmp/e05-handoff150.log`. A inspeção não aceita como válidos os PNGs de largura excedida.
Resultado: **4/4 casos a 100% aprovados; 2/4 a 150% aprovados**, com as duas falhas de largura
descritas acima. As oito folhas de contato em `tmp/e05/handoff-contacts/` foram inspecionadas
visualmente, cobrindo topo/fim e os cinco painéis em cada combinação. Também foram abertas
capturas integrais de Projeto extenso, Documentação/Conformidade/Regras e dos extremos de DPI.
Há 512 PNGs originais e oito metadados; nenhum dado real do usuário é necessário para reproduzir.

Artefatos experimentais `native-accepted`, `final-visual` e `verified-visual` não representam a
versão entregue. A tentativa de impor política `Minimum` a rótulos/cartões falhou nas quatro
combinações a 100% (`tmp/e05-label.log`) e foi revertida integralmente. Para retomar, usar
exclusivamente `handoff-visual` e `handoff-retry.log` como evidência da implementação mantida.

## Bloqueios, impacto e desbloqueio

1. **Janela reduzida a 150%.** Causa: soma dos mínimos da área central e docks. Evidência:
   matriz Windows registra 1080×512 em vez de 911×512 nos dois temas. Impacto: não é possível
   aceitar a matriz inteira mantendo a apresentação central atual. Desbloqueio: definir uma
   largura mínima útil para o PDF e ajustar a barra/partilha de largura ou a política de docks
   para telas estreitas, coordenando essa alteração com E06. Só reduzir o mínimo produz um PDF
   ilegível, conforme ensaio descartado em `tmp/e05/native-accepted/`.
2. **Gate público.** Causa/evidência inicial: quatro testes E2E já falham em `HEAD`, com
   identidade de sessão substituída pela leitura assíncrona do mercado, ordem de grupos anterior
   ao cartão Mercado e estados assíncronos de conformidade/GMAX. Impacto: o gate global não pode
   ser declarado aprovado. Desbloqueio: corrigir ou sincronizar esses cenários com E04 e repetir
   o gate em caminho curto; não retirar testes nem relaxar o aceite para ocultar falhas.

As ações de rolagem previstas estão implementadas, mas **não há aceite integral**. Preservar
este estado ao retomar: resolver os bloqueios, repetir a suíte direcionada e a matriz completa,
inspecionar as capturas e somente então atualizar índice/detalhe para `#concluida`.
