# E06 — Marca-texto por situação

Execução em 10/09/2026 sobre `80caf33` (`main`). Git inicial limpo;
`git rev-list --left-right --count HEAD...origin/main` retornou `0 0`, usando a
referência remota local, sem fetch. Nenhum AGENTS.md aplicável encontrado na
hierarquia ou no repositório. E06 não tem dependências. Sem commit ou publicação.

## Implementação e decisões

- `src/zeny_project_handler_client/ui/pdf_viewer.py`: substitui colchetes por
  preenchimentos localizados. `geometry` permanece como geometria editável;
  `link_geometry` fornece a área identificada. BOX usa os cantos normalizados;
  POLYGON preserva todos os vértices e a inclinação, sem caixa envolvente; POLYLINE
  vira faixa aberta com largura de 6 pontos PDF e extremidades arredondadas;
  POINT vira disco de diâmetro de 6 pontos. O plano da prévia escala essas medidas;
  os realces são recortados nos limites da página e ficam acima dos tiles.
- `src/zeny_project_handler_client/ui/visibility.py`: mapa único da legenda e cores.
  Instalar `#22c55e`, Existente `#facc15`, Remover `#ef4444`, Alterar `#3b82f6`.
  **Opacidade final validada: 25%** (`QColor.setAlphaF(0.25)`). Não foi necessário
  ajustar o valor inicial. A quantização raster pode produzir alpha 64/255.
- Cada situação tem um preenchimento com união dos caminhos. Duplicatas e
  interseções da mesma situação não acumulam alpha. Situações distintas compõem
  no máximo quatro camadas em ordem determinística; a mistura não é uma quinta
  situação. Tooltip e seleção em Resultados permitem identificar cada ocorrência.
- Itens de clique permanecem individuais. Contorno escuro de 2,5 pixels cosméticos
  identifica seleção sem mudar a situação; rejeitada fica sem preenchimento e
  com contorno cinza tracejado. A área de clique inclui margem de 14 pixels de
  cena, também considerada em `boundingRect`, para pontos pequenos a 50%.
  Seleção é restaurada após reconstrução da prévia, sem reenviar navegação.
- `src/zeny_project_handler_client/ui/review_panel.py`: ao selecionar um elemento,
  retira o contorno genérico de região anterior. O agrupamento pode ser localizado
  por contorno, mas nunca recebe preenchimento de situação. Filtros e controles
  existentes de região/elemento/vão continuam a determinar os overlays visíveis.
- `src/zeny_project_handler_server/review_api.py`: rótulo explícito de cabo precisa
  pertencer às evidências da proposta e estar na mesma página. Caso inválido usa
  o fallback existente, que exclui identificadores e comprimentos. A geometria
  editável do cabo não muda. Não houve alteração de DTO, OpenAPI ou exportador.

## Evidência automatizada

Comandos usam `.\.venv\Scripts\python.exe` (Python 3.12.14).

- Testes novos: `tests/integration/test_review_highlights.py`, 46 casos de cores ×
  revisão, pixels/alpha, BOX, polígonos inclinados, linhas/pontos, clipping nas
  bordas, zoom × rotações, clique/seleção, rejeição, outra página, legenda e 80
  ocorrências sobrepostas limitadas às quatro camadas. Execução final isolada:
  `python -m pytest tests/integration/test_review_highlights.py -q -p no:cacheprovider`:
  **46 passed**.
- `tests/server/test_review_api.py`: 16 combinações adicionais de situações e
  rótulos válidos/alheios/de outra página/ausentes; exclusão de identificador e
  comprimento. Módulo completo: **22 passed**.
- `tests/integration/test_pdf_viewer_progressive.py`: alinha o traçado real às
  quatro rotações e verifica seleção preservada e clique. Substitui expectativa
  antiga de posição do colchete por inclusão/exclusão geométrica.
- `tests/integration/test_review_panel.py`: navegação PDF↔Resultados, filtros,
  visibilidade sem preenchimento órfão e retirada do contorno de região.
- `tests/integration/test_compliance_callout_viewer.py`: realces e callouts coexistem;
  troca efetiva de tiles não muda caminho, página não deixa marca órfã, retorno
  à primeira página preserva geometria e bytes do PDF.
- Suite obrigatória E06 mais Resultados e casos novos: **141 passed** na primeira
  rodada consolidada (`tmp/e06/required3.log`). Depois do reforço do clique, tiles
  e navegação: **82 passed** nos quatro módulos afetados (`tmp/e06/final-targeted.log`).
- Rodada final de toda a validação obrigatória e testes complementares: **142 passed
  in 18.80s**, saída 0, `tmp/e06/required-final.log`.
- Comando obrigatório executado:
  `python -m pytest tests/integration/test_pdf_viewer_progressive.py tests/integration/test_pdf_viewer_http_gateway.py tests/integration/test_compliance_callout_viewer.py tests/integration/test_compliance_visibility.py tests/unit/test_pdf_coordinates.py tests/unit/test_pdf_rendering_budget.py tests/server/test_review_api.py tests/integration/test_review_panel.py tests/integration/test_review_highlights.py -q -o cache_dir=tmp/e06/cache --basetemp=tmp/e06/required-final`.
- Mypy global: `python -m mypy --cache-dir tmp/e06/mypy src tests`, **319 arquivos
  sem erros**. Ruff check e formatação passaram nas verificações direcionadas.
- Gate completo `.\IniciarTestes.bat`: **APROVADO**, saída 0. **1.144 testes
  passaram em 549,75 s (9 min 9 s)**; cobertura **87,37%**, acima do mínimo de
  85,01%. Dependências, Ruff, formatação (336 arquivos), Mypy (319 fontes),
  fronteira do cliente magro e complexidade E/F aprovados (2.724 funções/métodos).
  Inclui regressões de contratos/OpenAPI, revisão HTTP, exportação e E2E.
  Relatórios locais: `relatorio-testes.txt`, `tmp/e06/gate-final.txt` e
  `tmp/e06/gate-console-final.log`. Este resultado pertence à implementação final.

Histórico de validação: primeira execução direcionada não tinha o diretório pai
`tmp/e06`; ele foi criado. A rodada seguinte revelou expectativas antigas de
colchete e uma asserção que usava um endpoint como ponto externo após rotação;
foram corrigidas com verificações da faixa real. A revisão adicional reproduziu
clique perdido na margem do ponto e a produção foi corrigida com `boundingRect`.
A primeira execução do gate completo foi interrompida por erros de fixtures:
`PermissionError: [WinError 5] C:\tmp\zph-e06-probe`, reproduzido com um teste.
O gate usa C:\tmp explicitamente; a nova execução recebeu acesso fora do sandbox.
A execução seguinte ainda encontrou diferença de formatação em `pdf_viewer.py`
(após a correção do clique); foi interrompida, formatada e reiniciada integralmente.
`ruff format --check .` confirmou 336 arquivos formatados antes da nova execução.
Essas tentativas não são contabilizadas como aprovações.

## Inspeção visual

Ferramenta nova: `scripts/visual_qa_review_highlights.py`.
Comando: `python -m scripts.visual_qa_review_highlights` (saída 0).
Usa Qt/PySide6 real com plataforma offscreen no Windows, gateway local de testes
para rasterização remota simulada e PDF sintético sem material privado.
Não equivale a inspeção de uma janela nativa nem do PDF real da NS.

Matriz: temas claro e escuro × zoom 50%, 100%, 200% × rotações 0°, 90°, 180°, 270°,
janela 1100×850. Foram geradas e inspecionadas as duas folhas de contato (24 casos),
e também todas as 24 capturas individuais em tamanho original para verificar
os três níveis de zoom, os dois temas e as quatro orientações. Capturas em
`tmp/e06/visual/`, manifesto `matrix.json`, resultado da inspeção em `inspection.json`,
contatos `contact-claro.png` e `contact-escuro.png`. Arquivos locais ignorados.

Resultado visual: cores distinguíveis, legenda legível nos dois temas, transparência
preserva traços e texto, polígonos acompanham a inclinação, faixa não preenche o
interior da linha quebrada, seleção/rejeição diferenciadas e callout visível acima
das marcações. Em 50%, textos muito pequenos exigem zoom para leitura, como no
raster de origem; o realce não os cobre de forma opaca. Mesma situação sobreposta
não escurece; a mistura de vermelho e azul permanece localizada e o texto continua
visível. As oito capturas a 200% contêm 49 tiles cada; as demais usam a prévia.

SHA-256 da fixture durante a inspeção:
`b6ec2b69d9e26e6ba99e1bc12a276989fd45f9cfeeb1b6b2d9abd444dbfb995d`.
A ferramenta verifica igualdade pré/pós. Não foram modificados PDFs originais,
fontes de exportação ou arquivos privados; o gate inclui regressões de exportação.
O manifesto gerado deixa `human_review: pending` deliberadamente: a avaliação
visual é a inspeção registrada neste documento, não uma aprovação automática.

## Handoff

Especificação funcional atualizada em `docs/especificacao-funcional.md`.
A NS 1256148225 complementa a inspeção após E08, como previsto no roadmap; a E06
não afirma recuperar elementos nem corrigir extração. Opacidade final 25% e
limites de mistura/geometria devem ser mantidos na homologação E09.
Aceite completo: quatro critérios da E06 atendidos; índice e detalhe marcados
`#concluida` após o gate final aprovado. Nenhuma pendência da E06. As verificações
Git finais confirmaram diff sem erros de whitespace e somente código, testes,
ferramenta sintética e documentação no conjunto de alterações; nenhum dado privado,
PDF ou artefato de execução incluído. Sem commit ou publicação.
