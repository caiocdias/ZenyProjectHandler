# E14 — Revisão visual, API e exportações de símbolos

Execução iniciada em 24/09/2026 sobre `e95ce140574f90fdd2f1c32d5d0ec3e767db8c6e`,
com árvore limpa. Nenhum `AGENTS.md` aplicável foi encontrado nos ancestrais ou
no repositório. Os cinco módulos centrais de E13 conferiram com os hashes do
handoff; seus 36 testes passaram antes da implementação. A primeira tentativa
de pytest teve 19 aprovações e 17 erros por diretório temporário inexistente;
criar o diretório e repetir resolveu os erros. O Python existente da `.venv`
exigiu execução fora do sandbox por restrição do launcher WindowsApps. Não
houve instalação de dependências.

## Contrato e comportamento

`ReviewProposalDto.symbol` é opcional e representa uma ocorrência visual.
Alternativas de classe/subtipo e referências possíveis permanecem nessa mesma
ocorrência. Estado visual, exclusividade, papel observacional, suporte da família,
revisão humana, situação efetiva, quantidade e probabilidade calibrada são campos
separados. Score bruto pertence à observação e não é porcentagem de acerto.
Assinaturas identificam métodos; família e versão ficam nulas quando a evidência
persistida não permite recuperá-las, sem atribuição por adivinhação.

O pipeline passa a persistir score bruto, vínculo observação/evidência e matriz de
apoio, conflito, silêncio, falha e cobertura nos atributos da proposta. Isso também
funciona quando a evidência legada já existe e deve permanecer imutável. A versão
`e14-symbol-review-1` invalida somente a projeção semântica antiga com símbolos;
não altera detectores, calibração ou a política de união. Sessões históricas sem
esses metadados não ganham scores inventados. Reprocessamento pode completar os
metadados com novas propostas, mantendo o histórico e os controles de revisão.

O placeholder interno `EXISTENTE` de uma situação não resolvida aparece como
**Pendente** no cliente e nas exportações. A revisão continua individual, com
conflito de sessão, catálogo e situação explícitos na correção. A projeção dos
valores confirmados usa o elemento persistido; as alternativas originais seguem
como evidência da detecção, sem ativos extras por alternativa.

`ReviewSessionResponse.symbol_support` apresenta capacidade instalada por pacote,
separada do resultado do projeto: 27 famílias, 365 IDs, 21 habilitados e 344
pendentes no snapshot E07 atual. Habilitação não prova detecção nem homologação;
essa tabela não cobre implicitamente as famílias dos outros detectores. A
assinatura do pacote acompanha o registro. Nenhuma linha de capacidade cria uma
proposta, uma quantidade ou um ativo.

O cliente usa apenas DTOs e rasters remotos. Filtros e navegação distinguem
exclusivos, conflitos, desconhecidos, informativos e famílias não suportadas.
A planilha contém estados, alternativas, métodos, pendências, página e geometria;
o PDF derivado incorpora anotações de revisão nas páginas correspondentes. Os
PDFs de origem permanecem intactos.

## Compatibilidade HTTP

`GET /api/v1/projects/{project_id}/review-session` entrega `symbol` e
`symbol_support` quando recebe `X-Zeny-Review-Symbols: 1`. Sem esse header, omite
os dois campos e preserva a estrutura consumida por clientes anteriores que
rejeitam campos desconhecidos. O gateway atualizado pede os detalhes e ignora
adições futuras nas respostas, inclusive objetos aninhados; comandos continuam
estritos. Um servidor anterior pode ignorar o header e devolver a resposta
antiga, aceita pelos defaults do cliente novo. Não houve mudança de enum legado,
migração DDL ou aumento de piso da API. OpenAPI documenta o header e os DTOs.

## Delegação e integração

| Frente | Propriedade exclusiva |
|---|---|
| A `/root/codigo` | DTO de símbolo, `review_api.py`, `symbol_review.py`, `review_panel.py`, `review_gateway.py`, `deliverable_exports.py`. Contrato publicado antes dos consumidores. |
| B `/root/testes` | `tests/e14_symbol_review_fixtures.py`, testes E14 de contratos/servidor/UI e expectativas aditivas dos testes legados de UI/exportação. Revisão independente do código e runner. |
| C `/root/pdfs_ui` | `tmp/e14-simbologia/visual/`; imagens originais, achados, realces, recortes e sessão visual Qt, sem editar código de produto. |
| Coordenador `/root` | Metadados mínimos em `interpretation_pipeline.py`, guarda patrimonial em `human_review.py`, DTO de capacidade e `symbol_support.py`, negociação em `app.py`/API spec, snapshot OpenAPI, `scripts/benchmark_review_e14.py`, integração e documentação. |

Alterações pontuais compartilhadas em DTO/API foram serializadas e anunciadas a A.
Testes Qt e a sessão visual de C foram coordenados. O revisor não forneceu ROIs,
rótulos ou decisões à inferência. A reserva sintética permaneceu lacrada.

## Validação e evidências

E14 concluída em 24/09/2026: gates automatizados e aceite visual passaram no
checkpoint integrado, após conferência das três frentes. Evidências locais ficam em
`tmp/e14-simbologia/`; essa pasta é ignorada pelo Git, portanto os relatórios e
imagens devem acompanhar a transferência do workspace. Os testes, runner e este
handoff são versionáveis.

| Gate do coordenador | Resultado |
|---|---|
| Pré-condição E13 | 36 passed; hashes dos cinco módulos centrais conferidos. |
| V-U + V-N integrados | **175 passed**, 43,03 s, exit 0. Inclui todos os comandos V-U e os 22 testes novos (cinco contratos, dez servidor, sete Qt); não somar subconjuntos como testes distintos. |
| Regressão semântica/revisão/gateway + V-O | **58 passed**, 12,45 s, exit 0. Inclui snapshot OpenAPI e fronteira remota do cliente. |
| V-Q lint | `All checks passed`, exit 0. |
| V-Q formato | **430 files already formatted**, exit 0. |
| V-Q tipos | **392 source files**, sem erros, exit 0. |
| Exportação real E14 | **11 PDFs, 11 páginas, 237 propostas, 11 XLSX e 11 PDFs derivados**, exit 0; fonte, sessão e hashes de 11 arquivos de código invariantes durante a execução. |
| V-P + UI manual | **137 imagens aceitas realmente inspecionadas por C**; 11/11 páginas reais e fixture autoral de duas páginas com zoom/rotação. Seis linhas e seis anotações após decisões correspondem à sessão reaberta. Nenhum bloqueio visual remanescente. |

Comandos completos do checkpoint final:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/contracts tests/server/test_review_api.py tests/server/test_deliverable_exports.py tests/integration/test_review_panel.py tests/integration/test_review_highlights.py tests/server/test_e14_symbol_review.py tests/integration/test_e14_symbol_review_panel.py -q -o cache_dir=tmp/e14-simbologia/cache-final --basetemp=tmp/e14-simbologia/final-ui-2
.\.venv\Scripts\python.exe -m pytest tests/unit/test_e13_semantic_promotion.py tests/integration/test_e13_semantic_pipeline.py tests/integration/test_human_review.py tests/unit/test_review_gateway.py tests/unit/test_review_panel_remote_boundary.py tests/contracts/test_openapi_snapshot.py -q -o cache_dir=tmp/e14-simbologia/cache-final-nonqt --basetemp=tmp/e14-simbologia/final-nonqt
.\.venv\Scripts\python.exe scripts/generate_openapi_v1.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
git diff --check
```

O snapshot foi gerado antes dos testes: diff exclusivamente aditivo, 313 linhas,
mesmas 59 rotas e versão 1.6.0. O teste de snapshot compara o contrato gerado e o
servidor. O conjunto de 58 testes se sobrepõe aos contratos de V-U; os totais não
são somados. V-G e reserva final de E16 não foram executados nesta etapa.

As tentativas intermediárias permanecem explícitas: V-U inicial teve 153 passed
e cinco falhas (órfão legado agrupado indevidamente e quatro expectativas da aba
aditiva). A corrigiu o agrupamento; B acrescentou a aba esperada. A integração
seguinte teve 171 passed e quatro falhas porque a expectativa colocava a nova
aba depois de Trechos físicos. B conferiu a construção e corrigiu a ordem do
teste. O checkpoint final passou os 175 testes. O último format apontou somente
dois finais de linha nesse teste; o coordenador normalizou-os e repetiu o gate
global com sucesso, sem alteração lógica. Os demais achados de B — editor
invisível, separação de famílias e confirmação HTTP de envelope informativo —
foram corrigidos e cobertos por regressão antes do checkpoint final.

V-P usa nova inspeção das imagens originais e reuso declarado da inferência E13:
os detectores e runner não mudaram desde a base E13, e a descoberta recursiva e
os SHA-256 devem coincidir com seu manifesto. A projeção E14 e os arquivos
exportados são produzidos novamente. O runner recusa diferenças de fontes,
cobertura incompleta e diretório de servidor já existente.

Comando novo da integração:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_review_e14 --predictions tmp/e13-simbologia/benchmark-examples/predictions.json --manifest tmp/e13-simbologia/benchmark-examples/manifest.json --root examples --output tmp/e14-simbologia/checkpoint-final
```

Esse diagnóstico usa contexto documental mínimo por PDF: não demonstra associação
real a suportes quando faltam leituras documentais. Os testes autorais exercitam
correção e persistência; a inspeção real não constitui gabarito especialista
exaustivo nem medição de precisão/recall global. Todos os exemplos são dados de
desenvolvimento. Nenhum commit, publicação ou implantação foi autorizado ou feito.

## Evidência visual e limites herdados

V-P recursivo cobre os **11 PDFs e todas as 11 páginas**, incluindo 163 anotações
originais. C abriu 66 imagens originais (panoramas, quadrantes e camada base)
antes de comparar predições. Os arquivos `visual/manifest-e14.json` e
`visual/observacoes-previas.md` preservam a descoberta e a observação prévia.
Depois, C conferiu os contatos e recortes históricos e as exportações derivadas.
Não se atribui inspeção visual à leitura de JSON/OCR.

A inferência E13 contém 240 candidatos brutos: 220 legados, 17 transformadores
exclusivos E05 e três E09 de métodos estruturais excluídos da composição adotada.
As 237 ocorrências adotadas foram preservadas sem converter silêncio em veto.
Os 17 exclusivos têm 14 casos visualmente plausíveis e três ambíguos. Dez FP
legados conhecidos continuam registrados; há FN raster de transformador no ponto P2
de 1251985467 e três omissões do template de aterramento. Omissão por método
não equivale automaticamente a FN da união. Não há afirmação de precisão/recall
global nem de que E14 corrigiu esses detectores.

A matriz `visual/coverage-doc-page-method-layer.csv` possui 198 células
(11 páginas × nove métodos × duas camadas). `visual/reuse-audit.json` e
`visual/visual-findings-e14.json` registram cobertura e achados. A auditoria
`visual/exports-audit.json` conferiu as 237 linhas de símbolos e 237 anotações,
com página, geometria e alternativas, em todas as exportações. O comparador
`visual/final-vs-a1.json` confirmou que o checkpoint final mantém as mesmas
sessões sem timestamps, todos os XML internos XLSX e os pixels/anotações dos
11 PDFs já inspecionados. Não houve alteração dos PDFs de origem.

O manifesto final `checkpoint-final/manifest.json` tem SHA-256
`e2e604725078a10157fbbc76765a2a671a45d303b2e291e54f72bf4e51850eb4`.
Ele inclui hashes de código, PDFs originais, sessões e cada exportação.
O coordenador reconferiu mecanicamente os 11 conjuntos e todos os hashes de
código desse manifesto. `integration-file-hashes.json` registra os arquivos
novos/alterados no fechamento. Hashes dos handoffs dos agentes são checkpoints
intermediários; o manifesto integrado prevalece, inclusive após a normalização
de finais de linha do DTO/teste pelo coordenador.

Os handoffs de A e B estão em `a/handoff.md` e `b/handoff.md`, com comandos,
resultados e fronteiras de escrita. O relatório final C está em
`visual/relatorio-vp-e14.md`, SHA-256
`59e7613fb23564d72287491071a01e23a406f97e85d785c827e6f35e134fbd49`.
`visual/visual-inspection-results.json` registra os hashes das 137 imagens:
66 originais antes das predições, 37 contatos/focos históricos, 22 exportações,
dez capturas Qt legíveis e duas páginas PDF da fixture após decisões.
A reserva sintética permanece lacrada até
E16; os 344 IDs pendentes dos pacotes E07 continuam visíveis como capacidade
pendente, não como reconhecimento. E15 permanece fora desta implementação.

A sessão visual usa widgets reais em Qt offscreen e leitura dos arquivos reais,
sem alegar interação com aplicativos nativos de PDF/Excel. Poppler estava
indisponível; C usou PyMuPDF existente. A primeira captura Qt tinha fonte ausente
e um frame anterior ao raster: foi rejeitada, preservada em `fixture-ui/` e
substituída pela captura legível em `fixture-ui-readable/`, com Arial carregada e
espera do pixmap. As imagens rejeitadas não entram nas 137. A fixture corrigida
de B respeita a transformação inversa da página de 90°. O coordenador abriu
também três capturas legíveis, dois focos de PDFs reais e a primeira página
exportada da fixture; essa conferência dirigida não substitui a cobertura C.

As decisões individuais persistiram: rejeição não alterou as outras cinco
ocorrências; correção explícita de hipótese desconhecida criou exatamente um
ativo. C conferiu reabertura do serviço e seis linhas/seis anotações pós-decisão,
em `visual/fixture-ui-readable/exports-after-audit.json`; B testou também novo
runtime e HTTP. A cor da anotação PDF identifica a detecção; sua revisão humana
aparece no conteúdo da anotação e na coluna Revisão da planilha.

Comandos diagnósticos novos de C, preservados no handoff com tentativas e saídas:

```powershell
.\.venv\Scripts\python.exe tmp/e14-simbologia/visual/render_originals.py
.\.venv\Scripts\python.exe tmp/e14-simbologia/visual/render_base.py
.\.venv\Scripts\python.exe tmp/e14-simbologia/visual/audit_reuse.py
.\.venv\Scripts\python.exe tmp/e14-simbologia/visual/audit_exports.py
.\.venv\Scripts\python.exe tmp/e14-simbologia/visual/compare_final.py
.\.venv\Scripts\python.exe tmp/e14-simbologia/visual/capture_fixture.py
.\.venv\Scripts\python.exe tmp/e14-simbologia/visual/audit_fixture_exports.py
.\.venv\Scripts\python.exe tmp/e14-simbologia/visual/finalize_evidence.py
```

Todos tiveram checkpoint final exit 0. Para repetir a fixture, configurar um
diretório novo no harness, preservando o SQLite da evidência. Os scripts não
aprovam imagens: campos `visual_review: pending` nos JSON gerados precedem a
inspeção; a adjudicação posterior está no relatório C e no registro de imagens.
`integration-results.json` resume os resultados observados pelo coordenador.

Não há bloqueio de aceite E14. Hough sem OpenCV, ausência de exemplos positivos
de estai/legenda, FP/FN conhecidos e variantes E07 pendentes não foram mascarados
como cobertura: permanecem limites dos métodos apresentados. O próximo passo é
E15, com este DTO e sem alterar os contratos de união/procedência/decisão humana.
