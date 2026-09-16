# Zeny Project Handler — Mercado editável, painéis e leitura de redes

Data: 10/09/2026. Base inicial: `336afba`. E01 diagnosticada em `4ce5b50`; E02 entregue
em `101c721`; E03 integrada em `4f48c93`; E04 integrada em `897d85c`.
E05 concluída sobre `7dd6fbe`, com correções sem commit. Demais estados conforme o índice.

Extensão em 14/09/2026, base `9cb0ef7`: E10–E15 tratam a leitura do novo exemplo
1256407599. O [diagnóstico reproduzido](diagnostico-rede-1256407599.md) confirma leitura
parcial com OCR. Estados e evidências de E01–E09 permanecem preservados; os limites
históricos de tempo são substituídos, para trabalho futuro, pela diretriz abaixo.

## Diretriz vigente: confiabilidade, evolução vertical e horizontal

Atualizada por solicitação do usuário em 14/09/2026. Esta diretriz prevalece sobre
metas de tempo nos prompts, critérios e handoffs antigos, inclusive em retomadas
de E08/E09. Tempos e aprovações anteriores permanecem como registro histórico.

- **Vertical:** aprimorar precisão e cobertura dos algoritmos atuais, incluindo
  segmentação/OCR, camadas do PDF, situações, deduplicação, associação e topologia.
- **Horizontal:** implementar e experimentar algoritmos distintos dos atuais,
  compará-los na mesma referência e integrar os que apresentarem ganho comprovado.
  Alterar apenas DPI, parâmetros ou heurísticas do mesmo método não cumpre essa
  frente. E12A e E12B tornam experimentação e reconciliação entregas obrigatórias.
- **Tempo:** não é critério de aceite, ranking de métodos ou bloqueio. Uma análise
  de cinco minutos é aceitável; 300 segundos não é um teto. Não encerrar tentativas,
  reduzir resolução/cobertura ou escolher método menos confiável para cumprir os
  antigos 25/60 segundos. Medir duração apenas para observabilidade e planejamento.
- **Operação:** manter memória controlada, progresso, cancelamento e recuperação de
  falhas. Timeouts servem para detectar travamento, devem ser adequados ao método e
  permitir análise longa saudável. Um limite atingido produz resultado incompleto
  explícito, nunca confirmação de leitura integral ou reutilização como sucesso.
- **Confiabilidade:** exigir evidência por item e avaliar falsos positivos, omissões,
  código/situação exatos, relações, medidas e resultados completos. Confiança declarada
  pelo OCR e concordância entre métodos não bastam; medir erros também nos casos
  confirmados automaticamente. Preservar divergências e encaminhar ambiguidades
  reais à revisão, sem transformar defeitos de software em exclusões do inventário.

O objetivo é leitura integral confiável no conjunto validado. Aprovar um PDF ou
um conjunto finito não demonstra infalibilidade em projetos nunca vistos; manter
casos de avaliação separados dos ajustes e registrar os limites da evidência.

## Objetivo e uso

Permitir que o técnico ajuste a classificação inicial do banco para Rural, Urbano ou Ambos;
aplicar as duas famílias de normas em Ambos; manter cartões legíveis com rolagem independente
por painel; substituir os colchetes dos elementos por marca-texto por situação; e melhorar a
extração e a associação de elementos e vãos usando a NS 1256148225 como caso de verificação.
O escopo adicional usa a NS 1256407599 para cobrir revisões técnicas em anotações,
ocorrências, associações e topologia que o primeiro exemplo não homologou.

Execute uma etapa por sessão limpa aberta na raiz do repositório, copiando seu prompt. Leia as
instruções locais e confira dependências, código e Git antes de trabalhar. Atualize a tag no
índice e no detalhe, e registre evidências. Use somente `#pendente`, `#em-andamento`, `#concluida`
e `#bloqueada`. Dependência incompleta mantém a etapa pendente. Não conclua etapa com validação
obrigatória falhando ou não executada. Um bloqueio exige causa, evidência, impacto e ação de
desbloqueio. A ordem padrão é a do índice; o paralelismo listado é possibilidade técnica, não
instrução para criar agentes ou tarefas.

## Contexto confirmado na elaboração (antes de E02)

- Python 3.11–3.13; cliente PySide6, contratos Pydantic, servidor FastAPI, persistência
  SQLAlchemy/Alembic/SQLite, extração PyMuPDF e OCR Tesseract. Comandos em `README.md`,
  `pyproject.toml` e `IniciarTestes.bat`.
- Domínio, casos de uso e adaptadores em `src/zeny_project_handler/`; cliente em
  `src/zeny_project_handler_client/`; HTTP em `src/zeny_project_handler_server/`; DTOs em
  `src/zeny_project_handler_contracts/`. API canônica em `src/zeny_project_handler_api_spec/`
  e `docs/api/openapi-v1.json`.
- `domain/market.py` aceita somente Rural/Urbano do cadastro externo. Atualmente
  `application/compliance_analysis.py` consulta SQL Server a cada execução, depois de verificar
  divergência entre NS do projeto e cabeçalhos. Não existe escolha manual de mercado nos DTOs
  de projeto inspecionados.
- `application/project_compliance.py` produz um fato de contexto por mercado. Há também
  desvios de lógica exclusivos de Rural/Urbano, como `_existing_post_transformer_facts`.
  Portanto, acrescentar Ambos ao seletor ou apenas emitir dois fatos não basta.
- `src/zeny_project_handler_server/compliance_api.py` projeta o mercado do GMAX a partir dos
  fatos; a distinção entre cadastro e escolha efetiva precisa atravessar essa projeção.
- `ui/main_window.py` monta cinco docks: Projeto, Resultados, Documentação e conformidade,
  GMAX e Exportar. Os widgets são instalados diretamente nos docks. Não foram encontradas
  áreas `QScrollArea` no cliente; Resultados combina abas, tabelas e editor no mesmo layout.
- `ui/pdf_viewer.py` desenha colchetes em `_review_link_path` e
  `_polygon_review_link_path`, com estilo por estado de revisão. `ReviewOverlayDto` já
  fornece `situation`, `geometry` e `link_geometry`: a situação operacional pode definir a
  cor sem inferência no cliente.
- `SituacaoProjeto` inclui `INSTALAR`, `EXISTENTE`, `REMOVER` e `ALTERAR`. Os conceitos de
  ponto de entrega, ramal e comprimento substituído estão registrados no ADR 0015 e no código.
- Extração em `adapters/analysis/`, interpretação em `adapters/interpretation/`, promoção em
  `application/automatic_promotion.py`, regiões em `application/analysis_regions.py` e vãos
  em `application/spans.py`. `detectar_vaos` depende de cabos confirmados e endpoints: nem toda
  omissão de vão é falha de OCR. Versões observadas: extrator `1.11.0`, interpretador `21.1`.
- Não havia alterações rastreadas no Git nem roadmap Markdown presente. O ADR 0015 cita um
  roadmap histórico que não está no checkout. Este plano usa a documentação geral `docs/`,
  com nome específico, sem recriar ou sobrescrever o plano histórico.

### Evidência inicial da NS 1256148225

Fonte local: `examples/PROJETO DE REDE 1256148225.pdf`, 1.607.552 bytes, uma página,
SHA-256 `1e824e972d5cfc0b19fbcae774321d371cff30f6a8d1dfcb3673db858e6c77df`.

Na inspeção com PyMuPDF, `page.get_text('words')` retornou 21 palavras;
`page.get_drawings()` retornou 3.197 desenhos. O texto nativo contém caracteres inválidos.
O smoke `scripts.smoke_examples.executar_smoke_pdf`, chamado somente para esse arquivo,
retornou 3.320 evidências, **zero propostas, zero relações e zero diagnósticos**. O smoke
desabilita OCR e não executa promoção nem a projeção final de vãos. Esses números não medem
o resultado do pipeline completo do servidor e não estabelecem a contagem esperada de ativos.

A página inteira foi renderizada com Poppler e inspecionada visualmente: há uma rede extensa,
rótulos pequenos e inclinados, pontos, indicações de vãos, quadros e fotografias. O desenho
aparece deitado na página. Poppler gerou a imagem com código de saída zero, mas registrou
avisos de stream Flate e fontes Symbol/ArialUnicode. Investigar a relevância desses avisos
comparando com a rasterização usada pelo servidor; não presumir corrupção impeditiva nem
reescrever o PDF para ocultá-los. A imagem de inspeção é temporária, em `tmp/pdfs/`.

**Hipótese técnica:** a discrepância entre a leitura visual e o texto nativo torna a cobertura
de rasterização/OCR, inclusive orientação e recortes, uma prioridade. Ainda falta localizar
as perdas no pipeline completo e revisar o inventário esperado; E01 resolve essa incógnita.

## Escopo, restrições e decisões

Inclui persistência, contratos e UI da classificação, conformidade combinada, rolagem dos cinco
painéis, sobreposições visuais, diagnóstico reproduzível, extração e interpretação de redes,
regressões e documentação junto das mudanças.

Fora de escopo: implementação durante a escrita deste plano, publicação/release, alteração do
cadastro SQL Server, OCR em serviço externo, substituição geral do motor, normas novas sem
fonte identificada, edição do PDF original e obrigatoriedade dos PDFs privados no gate público.

Invariantes para todas as etapas:

- Cliente permanece magro: nenhum banco, parser, OCR ou regra normativa local. Mutações passam
  pela API autenticada e mantêm versionamento e tratamento de conflitos entre clientes.
- Preservar originais, identidades determinísticas, decisões humanas, proveniência, histórico
  e snapshots. Reanálise não pode reaplicar silenciosamente uma decisão a outro ativo.
- Manter distinção entre situação operacional e estado de revisão; entre poste e padrão do
  consumidor; entre rede e ramal; entre comprimento vigente e substituído. Cor não cria fato.
- Preservar validação da NS e verificações SQL de impacto ambiental/servidão. Escolha manual
  do mercado não dispensa essas verificações nem converte falha SQL em resultado válido.
- Manter orçamentos de renderização, cancelamento, jobs e cache. Versionar comportamento de
  extração, interpretação e conformidade quando alterado; não reutilizar cache incompatível.
- Conforme `examples/README.md`, PDFs reais e recortes ficam locais e ignorados. Regressões
  públicas usam fixtures pequenas e sintéticas. O gate deve passar com `examples/` vazio.

Hipóteses de produto adotadas para tornar o plano executável, ajustáveis com evidência:

1. **Inicialização por NS:** a primeira consulta SQL bem-sucedida inicializa e persiste a
   classificação. Reabrir e reanalisar preserva a escolha efetiva; não a sobrescreve pelo
   banco. Sem consulta inicial válida, permanece não inicializada, sem mercado presumido.
   E02 deve documentar tentativas após erro e migração de projetos existentes. Alterar NS
   invalida a classificação anterior e exige inicialização para a nova NS. Impacto: substitui
   a política atual de consultar mercado a cada análise; consultas de ações continuam atuais.
2. **Proveniência:** guardar separadamente mercado recebido do banco, classificação efetiva
   e origem/instante da escolha. Ambos pertence à classificação do projeto, não é um valor
   fictício retornado pelo SQL. A UI edita no painel Projeto; GMAX distingue banco e efetivo.
3. **Ambos no projeto inteiro:** aplicar a união das regras rurais e urbanas aos alvos que
   satisfaçam seus demais requisitos. Não exige delimitar zonas geográficas. Regras comuns
   não duplicam achados; regras distintas permanecem rastreáveis, mesmo se divergirem.
   Nenhuma nova prioridade normativa será inventada para resolver divergências.
4. **Marca-texto:** mudança na camada visual do visualizador, sem gravação na origem. Verde
   instalar, amarelo existente, vermelho remover. Para o estado já existente Alterar, adotar
   azul com legenda explícita; não reclassificá-lo. Opacidade inicial proposta: 25%, ajustada
   por inspeção, com valor final documentado. Não se exige um novo controle de opacidade.
   Incluir os novos realces no PDF exportado fica fora deste escopo; preservar os callouts
   exportados atuais. Se esse requisito mudar, planejar explicitamente a exportação.
5. **Cobertura:** realce significa ocorrência identificada, não garantia de interpretação
   completa ou aprovação técnica. A ausência de marca não prova ausência de ativo. E01 deve
   fixar inventário revisável e metas numéricas antes das correções, sem definir sucesso
   apenas por aumento do número de propostas.

## Definição global de pronto

- A classificação inicial vem do banco; técnico salva Rural/Urbano/Ambos e a seleção persiste
  ao reabrir, reconectar e reanalisar. Troca de NS e conflitos não reutilizam contexto indevido.
- Ambos ativa as duas famílias com guardas preservadas, sem duplicar regra comum. Mudanças
  tornam resultados anteriores desatualizados; nova conformidade usa a escolha persistida.
- Cada painel pode rolar sozinho em janela reduzida, com cartões legíveis e ações alcançáveis.
- Marca-texto cobre evidência/traçado identificado nas cores definidas, deixa o desenho legível
  e mantém seleção, navegação, filtros, zoom, rotação e callouts.
- Cada omissão confirmada na NS 1256148225 tem causa e correção verificadas. Itens legíveis e
  inequívocos do inventário são recuperados; ambiguidades ficam explícitas. Metas fixadas em
  E01 são cumpridas e regressões sintéticas impedem falsos positivos e duplicações conhecidos.
- Gate público completo aprovado, cobertura mínima de 85,01%, documentação e contrato coerentes.
  Benchmark local completo com OCR e inspeção visual registrados. Ausência do PDF/OCR impede
  concluir a homologação local, mas não cria dependência privada nos testes públicos.

## Índice

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Diagnóstico e referência da NS 1256148225 | #concluida | Nenhuma | Inventário e perdas por fase |
| E02 | Classificação persistida e API | #concluida | Nenhuma | Inicialização SQL e alteração versionada |
| E03 | Conformidade Rural, Urbano e Ambos | #concluida | E02 | Aplicabilidade e snapshots coerentes |
| E04 | Escolha do técnico na interface | #concluida | E02, E03 | Seletor e proveniência em Projeto/GMAX |
| E05 | Rolagem independente dos painéis | #concluida | Nenhuma | Cinco painéis; matriz 8/8 e gate aprovados |
| E06 | Marca-texto por situação | #concluida | Nenhuma | Realce 25%; matriz 24/24 e gate aprovados |
| E07 | Extração robusta de evidências | #concluida | E01 | 95 ocorrências, 18 identificadores e 19 comprimentos com evidência recuperada |
| E08 | Associação de elementos e vãos | #bloqueada | E01, E07 | 95 ocorrências; 18/19 comprimentos; classificação/topologia pendentes |
| E09 | Homologação integrada | #bloqueada | E03, E04, E05, E06, E08 | Gate aprovado; E08 e realce simbólico impedem aceite |
| E10 | Referência integral do segundo PDF | #concluida | Nenhuma | 139 registros, revisão definida e três medições isoladas |
| E11 | Revisões técnicas e conteúdo vigente | #concluida | E10 | Conflitos rastreáveis, decisão persistida e gate aprovado |
| E12 | Precisão dos extratores atuais | #concluida | E10, E11 | Leituras por cor, lotes contínuos e comparação vertical validada |
| E12A | Experimentação de algoritmos alternativos | #concluida | E12 | OCR neural e grafo global comparados; ganhos e regressões auditados |
| E12B | Reconciliação e confiança entre métodos | #concluida | E12A | OCR documental auxiliar integrado; ablações e 167 testes aprovados |
| E13 | Ocorrências e associação aos pontos corretos | #concluida | E12B | 29/29 no núcleo; D02–D05 rastreáveis, revisão e identidades preservadas |
| E14 | Topologia e projeção dos trechos | #concluida | E13 | 10 trechos, 9 pontos físicos, 6 medidas e 3 continuidades rastreáveis |
| E15A | Consolidação documental e vigência por campo | #pendente | E11, E12B, E14 | 64 itens rastreáveis sem valores errados silenciosos |
| E15B | Classificação e cobertura automática comprovada | #pendente | E13, E14 | Promoção exata, revisão explícita e metas E10 |
| E15C | Identidade de ocorrências entre páginas | #pendente | E13 | Não fundir ocorrências de folhas distintas |
| E15D | Exclusão contextual de falsos ativos | #pendente | E13 | Tabelas, fotos e carimbos sem promoção indevida |
| E15E | Topologia de circuitos cruzados | #pendente | E14 | Endpoints, medidas e cabos exatos em circuitos distintos |
| E15 | Aceite integral do segundo PDF | #bloqueada | E11, E12, E12A, E12B, E13, E14; retomada após E15A–E15E | Metas E10 reprovadas; evidências no handoff E15 |

## E01 — Diagnóstico e referência da NS 1256148225 — #concluida

**Objetivo:** estabelecer a lista revisável do que o PDF contém e localizar onde elementos e
vãos desaparecem. **Por que agora:** o smoke nativo produz zero propostas, mas o resultado com
OCR e a contagem esperada são desconhecidos; alterar limiares sem isso não permite medir correção.

**Dependências e paralelismo:** nenhuma; independente de E02/E05/E06. Evitar edição simultânea
dos mesmos arquivos de testes/documentação. **Escopo:** PDF local, `scripts/smoke_examples.py`,
`adapters/analysis/`, `adapters/interpretation/`, `application/interpretation_pipeline.py`,
`application/automatic_promotion.py`, `application/spans.py`, `tests/pdf_fixtures.py` e
`tests/interpretation_factories.py`, todos sob as raízes já identificadas.
**Fora de escopo:** corrigir heurísticas de produção ou executar SQL real para medir OCR.

**Passos de implementação:**

1. Registrar hash, configurações, versões, disponibilidade/idiomas do Tesseract e tempos.
   Comparar renderização PyMuPDF/Poppler, orientação visual, caixas da página e avisos.
2. Inspecionar recortes em resolução legível de toda a rede. Inventariar por ocorrência:
   página/geometria, categoria/código/situação, endpoints, comprimento vigente, evidência e
   grau de ambiguidade. Incluir padrões, ramais e regiões com textos próximos ou sobrepostos.
3. Executar extração nativa e pipeline semântico com OCR real, promoção e projeção de vãos em
   ambiente temporário isolado. Registrar evidências, propostas, confirmação, regiões e vãos;
   classificar perdas por fase. Não usar o smoke sem OCR como medida do sistema completo.
4. Fixar denominadores e metas antes de corrigir: recuperar 100% das omissões confirmadas de
   ocorrências legíveis e inequívocas; listar ambiguidades excluídas com motivo. Medir precisão,
   recall por categoria/situação, endpoints, comprimentos, duplicatas, tempo e memória. Fixar
   orçamento numérico de desempenho com base na máquina e no baseline, sem elevá-lo depois
   para esconder regressão. Destilar padrões para fixtures sintéticas.
5. Registrar protocolo sanitizado e comandos exatos no handoff. Artefatos reais permanecem em
   `tmp/` ou `examples/`; caminho de eventual utilitário novo deve ser documentado como novo.

**Prompt para uma sessão limpa:**

```text
Execute E01 — Diagnóstico e referência da NS 1256148225 de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro AGENTS.md aplicáveis, o roadmap, README.md, examples/README.md, scripts/smoke_examples.py, os adaptadores de análise/interpretação e o pipeline de promoção/vãos; confira git status e divergência do código. Não há dependências. Preserve mudanças preexistentes e limite-se ao diagnóstico e às fixtures necessárias, sem corrigir heurísticas de produção. Marque E01 em andamento no índice e detalhe. Inspecione o PDF examples/PROJETO DE REDE 1256148225.pdf, inventarie todas as ocorrências e vãos legíveis com geometria, compare o fluxo nativo com o pipeline completo usando OCR real e localize perdas por fase. Fixe denominadores, metas e orçamento de desempenho antes das correções. Mantenha dados reais fora do Git e registre comandos reproduzíveis. Crie/atualize testes das ferramentas ou fixtures adicionadas e execute a validação obrigatória da etapa. Só marque concluída com inventário, baseline completo e validações aprovados; se houver impedimento real, marque bloqueada e registre causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos e resultados. Não declare sucesso com validações falhando ou não executadas. Não crie commit nem publique. Termine com resumo conciso de resultados, validações e pendências.
```

**Critérios de aceite:**

- [x] Inventário cobre toda a rede visível, com ocorrências inequívocas e ambiguidades separadas.
- [x] Há comparação por fase do fluxo completo com OCR real, incluindo promoção e vãos.
- [x] Metas, denominadores, casos negativos e orçamento numérico foram fixados e registrados.
- [x] PDF permanece com o mesmo SHA-256 e nenhuma informação privada foi adicionada ao Git.

**Validação obrigatória:** `python` nos comandos deste plano significa executar
`.\.venv\Scripts\python.exe`. Rodar `python -m pytest tests/unit/test_smoke_examples.py`
e os testes das novas fixtures/ferramentas; todos devem passar. Repetir o smoke específico
com `python -c "from pathlib import Path; from scripts.smoke_examples import executar_smoke_pdf; print(executar_smoke_pdf(Path('examples/PROJETO DE REDE 1256148225.pdf')))"`.
Para o fluxo completo, identificar a composição em `src/zeny_project_handler_server/composition.py`
e os padrões de `tests/integration/test_interpretation_pipeline.py`, montar execução isolada e
registrar o comando efetivamente usado; ainda não existe comando confirmado para esse benchmark.
Exigir inspeção visual e hash pré/pós; sucesso do smoke sozinho não atende o aceite.

**Bloqueios:** nenhum impedimento remanescente para o diagnóstico. Português ausente foi
provisionado em `tmp/e01/runtime`; foi necessário copiar `configs/tsv` da instalação local
para esse runtime temporário. Sem ele, Tesseract retorna texto simples e o adaptador descarta
a saída sem diagnóstico. A falha foi preservada e encaminhada a E07, sem alterar produção.
**Riscos e mitigação:** inventário errado ou ajuste específico à NS; revisar recortes, manter
ambiguidades explícitas e produzir padrões sintéticos sem NS/coordenadas reais.
**Evidências e handoff:** concluídos em 10/09/2026; protocolo, decisões, comandos e limites em
[e01-diagnostico-leitura-rede.md](e01-diagnostico-leitura-rede.md).

- Git inicial limpo, divergência local `HEAD...origin/main = 0 0`; somente o roadmap difere de
  `336afba`. Nenhum `AGENTS.md` aplicável encontrado. Código de produção preservado.
- Inventário privado: `tmp/e01/inventory.json`; 95 ocorrências inequívocas (17 postes,
  22 estruturas MT, 19 BT, 37 cabos), 18 identificadores, 20 trechos físicos, 18 pares de
  endpoints visíveis e 19 comprimentos explícitos. Sete rótulos de equipamento e 13 grupos
  simbólicos têm ambiguidades explícitas, sem presumir quantidade/classe/situação.
- Baseline `tmp/e01/baseline-final.json`: nativo 3.320 evidências, 8 propostas brutas,
  zero finais; OCR real 3.593 evidências (273 OCR), 8 propostas brutas, 3 finais sem catálogo,
  zero confirmações, 4 regiões e zero vãos. Filtros, promoção e projeção executados em bases
  SQLite novas. Controle de orientação e probes do runtime preservados localmente.
- Recall das 95 ocorrências = 0%; precisão nas categorias inequívocas indefinida (0/0).
  Metas: 100% das ocorrências/endpoints/comprimentos inequívocos e zero duplicatas/invenções.
  Orçamento congelado: 25 s nativo, 60 s OCR, RSS Python 768 MiB, OCR 256 MiB, agregado 1 GiB.
  Medidos 15,882 s e 38,468 s; memória dentro do orçamento, com limites de amostragem documentados.
- Ferramenta pública nova `scripts/benchmark_network_pdf.py`; fixture sintética nova em
  `tests/pdf_fixtures.py`; testes em `tests/unit/test_benchmark_network_pdf.py`.
  Nenhum PDF real, recorte, transcrição ou coordenada adicionado aos arquivos versionáveis.
- Validação final: 8 testes públicos e 3 verificações privadas aprovados (11 no total);
  smoke específico aprovado; benchmark completo com código zero; inspeção visual e hash
  pré/pós aprovados. Ruff/formatação aprovados; Mypy sem erros em 308 arquivos;
  `git diff --check` aprovado. Falhas iniciais de ambiente/fixture/checks foram resolvidas
  e repetidas; resultados finais e escopo exato constam no relatório.
- Handoff E07: runtime TSV, orientação e guardas dos recortes; E08: filtros por identificador,
  catálogo de símbolos, relações, entrega e endpoints. A conclusão certifica o diagnóstico,
  não a recuperação automática dos ativos. Gate global de cobertura/UI fica para E09.
  Nenhum commit ou publicação realizado.

## E02 — Classificação persistida e API — #concluida

**Objetivo:** inicializar pelo SQL e permitir alteração versionada da classificação efetiva.
**Por que agora:** a conformidade e a interface precisam de uma fonte persistida comum.
**Dependências e paralelismo:** nenhuma; pode acompanhar E01/E05/E06, sem editar seus arquivos.
**Escopo:** `domain/market.py`, `domain/project.py`, persistência/codec e migrações em
`adapters/persistence/`, `application/compliance_analysis.py`, portas de mercado/persistência,
`src/zeny_project_handler_server/project_api.py`, `stage3_store.py`, contratos de projetos e
API canônica. **Fora de escopo:** seletor Qt e habilitação das regras de Ambos.

**Passos de implementação:**

1. Representar separadamente mercado externo Rural/Urbano, escolha efetiva Rural/Urbano/Ambos,
   origem e instantes. Definir estado não inicializado sem transformar erro SQL em default.
2. Persistir a primeira consulta bem-sucedida, vinculada à NS. Integrar o consumidor atual
   de mercado para respeitar a inicialização; reanálise não sobrescreve a escolha. Invalidar
   contexto ao alterar NS, inclusive ao voltar a uma NS anterior; evitar corrida entre job,
   inicialização e edição. Consultas de ações mantêm a política atual.
3. Expor leitura e mutação autenticadas com `expected_project_version`, validação fechada e
   conflito explícito. Reutilizar controles de jobs e auditoria disponíveis; não inventar
   identidade de técnico que o modelo de autenticação não fornece.
4. Incluir mudança nas assinaturas/checagens de desatualização sem alterar snapshots antigos.
   Antes de E03, Ambos pode ser salvo, mas sua avaliação deve ser recusada explicitamente;
   nunca calcular silenciosamente só uma família. Retirar essa guarda em E03.
5. Atualizar contratos, snapshot OpenAPI, documentação da inicialização e testes de regressão.

**Migração e compatibilidade:** leitura aditiva de dados antigos como não inicializados;
primeira análise compatível consulta o banco. Não inferir escolha humana de snapshot antigo.
Verificar necessidade de migração Alembic e atualização do lifecycle do volume conforme o
formato efetivamente escolhido. Testar banco antigo em cópia. Registrar compatibilidade de
cliente/servidor; rollback de dados por backup consistente anterior, sem downgrade destrutivo
ou reescrita dos snapshots. A implementação não autoriza migrar volume operacional.

**Prompt para uma sessão limpa:**

```text
Execute E02 — Classificação persistida e API de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro instruções AGENTS.md, roadmap, README.md, domínio de projeto/mercado, persistência, application/compliance_analysis.py, project_api.py, stage3_store.py, contratos e testes relacionados; confira git status e divergências. Não há dependências. Preserve alterações preexistentes e marque E02 em andamento no índice e detalhe. Implemente inicialização SQL única por NS bem-sucedida e classificação efetiva editável Rural/Urbano/Ambos, com origem, persistência, versão, conflito, invalidação ao trocar NS e desatualização dos resultados. Não altere o SQL externo nem as verificações de ações; não construa o seletor Qt. Integre a política de inicialização ao consumidor atual, mas recuse avaliação de Ambos até E03, sem cair em uma família por default. Implemente compatibilidade/migração apenas necessária, testes e documentação; atualize OpenAPI e execute todas as validações obrigatórias de E02. Só marque concluída após todos os critérios passarem. Se houver impedimento real, marque bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões de contrato/migração, comandos e resultados. Não declare sucesso com testes falhando ou não executados, não crie commit nem publique ou migre produção. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Primeira classificação válida é persistida; falha inicial não grava mercado fictício.
- [x] Alteração e releitura preservam as três opções; concorrência e troca de NS são testadas.
- [x] Reanálise não sobrescreve a escolha e resultado antigo aparece desatualizado.
- [x] Dados antigos são legíveis e Ambos não produz avaliação parcial antes de E03.

**Validação obrigatória:** `python scripts/generate_openapi_v1.py`; depois
`python -m pytest tests/contracts tests/server/test_project_document_api.py tests/server/test_compliance_api.py tests/integration/test_persistence.py tests/unit/test_persistence_codec.py tests/unit/test_sql_server_market.py tests/server/test_volume_lifecycle.py`.
Adicionar e executar casos para todas as transições acima, com SQL fake; se modificar portabilidade,
incluir `tests/integration/test_project_portability.py`. Resultado esperado: todos aprovados e
diff OpenAPI limitado ao contrato planejado, sem necessidade de SQL real.
**Bloqueios:** nenhum bloqueio conhecido.
**Riscos e mitigação:** valor manual perdido por job concorrente; checar versão no servidor e
guardar proveniência. Dados antigos; testar leitura, inicialização e atualização em cópia.
**Evidências e handoff — 10/09/2026:**

- Base verificada: `HEAD=2b00d0b`, `main...origin/main` sem divergência (`0 0` pela referência
  local), sem alterações preexistentes. Não foi realizado fetch. Não havia `AGENTS.md` na
  hierarquia consultada nem no checkout. README, roadmap, domínio, persistência/codec,
  consumidor, API, `stage3_store.py`, contratos e testes foram lidos antes da implementação.
  Não há dependência de E01 para esta entrega.
- Domínio em `src/zeny_project_handler/domain/{market,project}.py`: `Mercado` externo continua
  Rural/Urbano; `ClassificacaoMercado` acrescenta Ambos apenas à escolha. `ClassificacaoProjeto`
  registra NS, mercado inicial, efetivo, origem SQL/MANUAL, instantes, versão e UUID de revisão.
  Campo ausente/nulo é não inicializado. Mesmo salvar a mesma escolha registra revisão nova.
  Trocar NS invalida o campo no agregado, inclusive retorno à NS anterior; manter a NS preserva.
- Persistência em `adapters/persistence/{domain_json,project_repository}.py` e
  `ports/persistence.py`: armazenamento aditivo em `projects.payload`, utilizando a versão
  existente do projeto. Escrita condicional compara o agregado esperado e o payload original,
  inclusive JSON legado com campo ausente. Nenhum DDL: Alembic permanece `0009_remote_jobs`,
  formato do volume 1; `stage3_store.py` e lifecycle permanecem inalterados. Cópia consistente
  de banco com payload anterior foi aberta, inicializada, atualizada e relida. Não se infere
  escolha humana de snapshots; rollback incompatível exige backup anterior em volume separado.
- Consumidor em `application/compliance_analysis.py`: primeira resposta SQL válida persiste
  antes das ações; falha inicial permite nova tentativa. Falha posterior nas ações ou
  cancelamento conserva a inicialização válida, sem snapshot parcial. Reanálise/reinício
  não consultam novamente nem sobrescrevem a escolha. NS de cabeçalho continua validada antes
  do SQL. Chamadas diretas ao mesmo consumidor são serializadas; jobs/mutações HTTP conservam
  o coordenador global. Testes provocam duas edições e troca de NS durante SQL, sem perda de
  atualização nem gravação de contexto antigo.
- Contrato: `GET/PUT /api/v1/projects/{project_id}/market`, implementado em
  `src/zeny_project_handler_server/{project_api,app}.py`, DTOs em
  `src/zeny_project_handler_contracts/projects.py`, especificação em
  `src/zeny_project_handler_api_spec/app.py` e `docs/api/openapi-v1.json`. Leitura sem SQL;
  escrita exige `expected_project_version`. Respostas 401/404/422, `409 STALE_STATE` e
  `409 OPERATION_CONFLICT` verificadas. Proveniência não inventa identidade individual para
  o Bearer compartilhado. API/piso 1.3.0 preservados: duas operações e três schemas novos,
  nenhum schema ou operação anterior alterado (comparação estrutural UTF-8 com `git show`).
- Método de conformidade **13**: `application/project_compliance.py` inclui revisão, origem,
  mercado inicial/efetivo e instantes nos fatos/assinatura. `compliance_analysis.py` e
  `src/zeny_project_handler_server/compliance_api.py` detectam desatualização por revisão.
  Histórico anterior permanece imutável; escolha Rural→Urbano→Rural não revive snapshot antigo.
  Ambos salvo é recusado com `VALIDATION_ERROR` explícito pelo job, sem executar uma família
  por default e sem publicar resultado parcial. GMAX conserva o último snapshot marcado stale.
- Regressões novas em `tests/integration/test_persisted_market.py` e
  `tests/server/test_project_market_api.py`; atualizadas em
  `tests/integration/test_compliance_analysis.py`, `tests/server/test_jobs_api.py`,
  `tests/unit/{test_compliance,test_persistence_codec}.py` e
  `tests/contracts/test_openapi_snapshot.py`. Cobrem erro/tentativa, origem, todas as escolhas,
  conflitos, reabertura, cópia legada, NS ida/volta, ações ainda atuais e bloqueio de Ambos.
- Documentação atualizada: `README.md`, `docs/api/README.md`,
  `docs/especificacao-funcional.md`, `docs/arquitetura-conformidade.md` e este roadmap.

Comandos finais executados na raiz, todos com saída zero:

```powershell
.venv/Scripts/python.exe scripts/generate_openapi_v1.py
.venv/Scripts/python.exe -m pytest tests/contracts tests/server/test_project_document_api.py tests/server/test_compliance_api.py tests/integration/test_persistence.py tests/unit/test_persistence_codec.py tests/unit/test_sql_server_market.py tests/server/test_volume_lifecycle.py tests/server/test_project_market_api.py tests/integration/test_persisted_market.py tests/integration/test_compliance_analysis.py tests/unit/test_compliance.py tests/integration/test_project_portability.py tests/server/test_jobs_api.py --basetemp=tmp/e3 -p no:cacheprovider -q --tb=short
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe scripts/complexity_gate.py src
.venv/Scripts/python.exe scripts/client_artifact_gate.py --source-only
git diff --check
```

Resultado: **280 testes aprovados em 68,35 s**, incluindo toda a validação obrigatória de E02,
novas regressões, consumidor, jobs e portabilidade. Ruff aprovado; 326 arquivos formatados;
Mypy sem erros em 310 arquivos; dependências íntegras; complexidade aprovada (2.673 funções,
nenhuma E/F); fronteira do cliente aprovada. Log local ignorado: `tmp/e02-validation-final.txt`.
Rodadas exploratórias corrigiram duas expectativas antigas de consulta/versão, a fixture de
backup e a serialização de publicação concorrente. Temporários padrão e `C:/tmp` tiveram
restrição de escrita; uma raiz longa no workspace causou `WinError 3` na portabilidade.
Usar `tmp/e2` confirmou os 25 testes de portabilidade, e `tmp/e3` aprovou a rodada final completa,
sem alterar código de portabilidade nem configurações do Windows. Não restam falhas de E02.
O gate integral com cobertura do roadmap continua pertencendo a E09; não foi executado em E02.

Handoff: E03 deve consumir `classificacao_mercado.efetiva`, implementar união das famílias e
retirar a guarda de Ambos somente depois das regressões normativas, preservando revisão e
proveniência. E04 deve usar a nova rota e reler `project_version` após analisar (inicialização
também incrementa a versão); distinguir mercado inicial/efetivo e tratar rota ausente em
servidor antigo como indisponibilidade. Não foi criado seletor Qt. Adaptador/SQL externo e
verificações de ações não foram alterados. Nenhum commit, publicação ou migração operacional.

## E03 — Conformidade Rural, Urbano e Ambos — #concluida

**Objetivo:** avaliar a união das regras de Rural e Urbano usando o contexto efetivo persistido.
**Por que agora:** E02 fornece a classificação e suas transições.
**Dependências e paralelismo:** E02; independente de E05/E06/E07, com atenção a testes comuns.
**Escopo:** `application/project_compliance.py`, `compliance_analysis.py`, provedores e avaliação
de fatos, registro declarativo, `src/zeny_project_handler_server/compliance_api.py`, contratos
GMAX/conformidade, exportações e `docs/arquitetura-conformidade.md`.
**Fora de escopo:** novas obrigações normativas e escolha automática de norma prevalente.

**Passos de implementação:**

1. Consumir a classificação efetiva em todos os provedores, substituindo decisões binárias
   por pertencimento explícito aos contextos. Auditar especialmente transformador em poste
   existente, alvos de projeto/região/vão e fatos usados como guardas.
2. Em Ambos, emitir ambos os contextos aplicáveis sem falso impeditivo de um ramo sobre o
   outro. Preservar evidências requeridas, não avaliável e exclusões de ramais.
3. Avaliar cada regra/alvo uma vez. Conservar achados distintos de regras diferentes e sua
   origem; não fundir divergências técnicas em uma resposta arbitrária.
4. Atualizar projeções GMAX, snapshots, resumos e exportações para refletir contexto do banco
   e efetivo; versionar método e desatualização, preservando história. Retirar guarda de E02.
5. Atualizar documentação e testes de matriz Rural/Urbano/Ambos para as famílias existentes.

**Prompt para uma sessão limpa:**

```text
Execute E03 — Conformidade Rural, Urbano e Ambos de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro AGENTS.md aplicáveis, roadmap, domínio de mercado, compliance_analysis.py, project_compliance.py, provedores, regras, compliance_api.py e testes; confira git status. Verifique E02 concluída e contrato real sem divergência. Preserve mudanças preexistentes e marque E03 em andamento no índice e detalhe. Implemente avaliação da união rural/urbana em Ambos no projeto inteiro, incluindo desvios binários dos provedores e projeção GMAX. Mantenha guardas, não avaliável, ramais e achados rastreáveis; regra comum não duplica, regras distintas não são apagadas. Remova a guarda temporária de E02, preserve consulta inicial e escolhas manuais, atualize versão/assinaturas e exportações afetadas sem reescrever histórico. Não acrescente normas nem invente precedência entre elas. Crie/atualize testes de matriz, documentação e contrato quando necessário, e execute as validações obrigatórias. Só marque concluída após aceite completo; diante de impedimento real, marque bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos e resultados. Não declare sucesso com validação falhando ou não executada. Não crie commit nem publique. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Fixtures aplicáveis geram os achados rurais e urbanos em Ambos, incluindo guardas especiais.
- [x] Rural e Urbano isolados preservam resultados esperados; regras comuns não duplicam.
- [x] Alteração da escolha invalida o snapshot; reexecução e exportação refletem o novo contexto.
- [x] Falta de evidência, conflito de NS e falhas nas ações mantêm tratamento explícito.

**Validação obrigatória:** `python -m pytest tests/unit/test_compliance.py tests/unit/test_transformer_compliance_provider.py tests/unit/test_span_compliance_provider.py tests/unit/test_topology_compliance.py tests/unit/test_compliance_catalog_parity.py tests/integration/test_compliance_analysis.py tests/server/test_compliance_api.py tests/server/test_deliverable_exports.py`.
Se DTOs mudarem, regenerar OpenAPI com `python scripts/generate_openapi_v1.py` e executar
`python -m pytest tests/contracts`. Exigir comparação de conjuntos de achados por regra/alvo,
não somente contagem total; todos os testes devem passar.
**Bloqueios:** nenhum bloqueio conhecido.
**Riscos e mitigação:** emitir os dois fatos e esquecer exclusões binárias; revisar todos os
consumidores de mercado e testar contextos combinados, com e sem evidência suficiente.
**Evidências e handoff — 10/09/2026:**

- Base `HEAD=101c721`, Git inicial limpo, `HEAD...origin/main = 0 0` pela referência local,
  sem fetch. Nenhum `AGENTS.md` encontrado na hierarquia aplicável ou no checkout. E02 estava
  concluída e integrada; a indicação inicial de alterações locais de E02 foi corrigida no
  cabeçalho, preservando suas evidências históricas. Domínio, consumidor, provedores regionais,
  documentais, de vãos e topologia, avaliador, registro, GMAX, contratos, exportador e testes
  foram inspecionados; os consumidores de mercado foram auditados com `rg` em todo `src`.
  E03 passou por `#em-andamento` no índice/detalhe antes da implementação.
- `domain/market.py`: `ClassificacaoMercado.contextos` representa Rural/Urbano e a união em
  Ambos. `Mercado` externo continua binário. `application/{project_compliance,
  compliance_fact_providers}.py`: a classificação persistida prevalece na entrada, ambos os
  fatos positivos chegam ao projeto e a todas as regiões, e o desvio do transformador em
  poste existente usa presença do contexto urbano. Não há fato rural falso que impeça o ramo
  urbano. Documento/vão/topologia não têm outros desvios binários a alterar.
- `application/compliance_analysis.py`: retirada a guarda provisória; método **14** consome
  a escolha persistida, mantendo SQL inicial, NS antes do SQL, ações atuais, cancelamento e
  publicação atômica. Revisão/origem/banco/efetivo/instantes continuam nos fatos e assinatura.
  Método 13 ou anterior é stale, sem modificar execuções existentes. Os testes comprovam
  histórico imutável, reanálise determinística, preservação das escolhas e leitura legada.
- O avaliador e o catálogo de **42 regras** permanecem intactos. Uma passagem por regra/alvo
  conserva regras comuns uma vez e regras distintas separadas, sem nova norma ou precedência.
  A matriz nova `tests/unit/test_combined_market_compliance.py` compara mapas de achados
  completos por `(regra_id, alvo_id)`, incluindo resultado, fonte, condições e referências.
  Cobre múltiplas regiões, fonte persistida, topologia rural/urbana, transformadores 75/150 kVA,
  poste novo/existente, vínculos ausentes/ambíguos, limiares/exceções de vãos e ramais
  aéreos/subterrâneos/desconhecidos. Um cabo CAA acima de 80 m conserva simultaneamente o
  achado rural conforme e o urbano divergente no mesmo alvo, com fontes/IDs distintos.
- `src/zeny_project_handler_server/compliance_api.py`: GMAX aceita exatamente os contextos
  da escolha efetiva do snapshot, rejeita duplicatas e proveniência parcial/inválida, e
  projeta `classification` a partir dos fatos. Esse mesmo campo aparece nos resumos/histórico.
  Stale conserva a proveniência anterior; projeto atual não é sobreposto ao snapshot.
  Histórico anterior a E02 tem classificação nula; bloqueio de NS/sem execução não expõe
  classificação. Leituras não fazem SQL nem escrevem dados.
- `src/zeny_project_handler_contracts/{gmax,compliance,versioning}.py`: novo enum fechado
  `GmaxMarket.AMBOS` e campo opcional `classification`, reutilizando
  `ProjectMarketClassificationDto`. API/piso **1.4.0**, conforme política do repositório para
  enums fechados. OpenAPI regenerada: rotas idênticas, nenhum schema novo/removido; somente
  `GmaxMarket`, `GmaxSummaryResponse`, `ComplianceExecutionSummaryDto` e `info.version` mudaram.
  Negociação rejeita API 1.3; cliente recebe somente o mapeamento básico do rótulo Ambos em
  `ui/gmax_panel.py`, sem antecipar o seletor E04.
- `src/zeny_project_handler_server/deliverable_exports.py`: XLSX de conformidade acrescenta
  Contexto da execução, com identidade/método/assinatura/stale e proveniência. Achados e
  callouts continuam vindo do snapshot. Teste HTTP real com SQL fake inicializa, salva Ambos,
  exporta o snapshot stale, reexecuta e baixa XLSX; IDs e quantidade de achados são iguais aos
  da API, com Ambos/MANUAL/banco original e método 14. PDF anotado e demais planilhas mantidos.
- Regressões atualizadas em `tests/integration/{test_compliance_analysis,test_persisted_market,
  test_gmax_panel}.py`, `tests/server/{test_jobs_api,test_deliverable_exports}.py`,
  `tests/contracts/{test_models,test_openapi_snapshot}.py` e
  `tests/unit/test_client_connection.py`. Comprovam falha de ações em Ambos e divergência de NS
  sem publicação parcial, escolhas/versionamento, GMAX consistente, DTO/legado e negociação.
  Documentação: `README.md`, `docs/{arquitetura-conformidade,especificacao-funcional}.md`,
  `docs/api/README.md`, OpenAPI e este roadmap.

Comandos executados na raiz (Python da `.venv`), todos aprovados na validação final:

```powershell
.venv/Scripts/python.exe scripts/generate_openapi_v1.py
.venv/Scripts/python.exe -m pytest tests/unit/test_compliance.py tests/unit/test_transformer_compliance_provider.py tests/unit/test_span_compliance_provider.py tests/unit/test_topology_compliance.py tests/unit/test_compliance_catalog_parity.py tests/integration/test_compliance_analysis.py tests/server/test_compliance_api.py tests/server/test_deliverable_exports.py tests/contracts tests/unit/test_combined_market_compliance.py tests/unit/test_topology_path_compliance.py tests/integration/test_persisted_market.py tests/server/test_project_market_api.py tests/server/test_jobs_api.py tests/unit/test_client_connection.py tests/integration/test_gmax_panel.py --basetemp=tmp/e37 -p no:cacheprovider -q --tb=short
.venv/Scripts/python.exe -m pytest tests/unit/test_combined_market_compliance.py tests/integration/test_persisted_market.py --basetemp=tmp/e38 -p no:cacheprovider -q --tb=short
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe scripts/complexity_gate.py src
.venv/Scripts/python.exe scripts/client_artifact_gate.py --source-only
git diff --check
```

Resultado consolidado: **277 testes aprovados em 30,56 s**, cobrindo todos os obrigatórios e
contratos. Rodada focada final: **43 aprovados em 6,73 s**, após explicitar a fixture com duas
regiões e o estreitamento de tipo da resposta legada. Ruff aprovado; **327 arquivos formatados**;
Mypy sem erros em **311 arquivos**; dependências íntegras; complexidade aprovada (**2.676 funções**,
nenhuma E/F); fronteira do cliente aprovada. Logs locais ignorados:
`tmp/e03-final-tests.txt`, `tmp/e03-final-regressions.txt`. Rodadas exploratórias ajustaram
expectativas antigas do enum/guarda, o payload do teste do job para `expected_semantic_signature`,
tipos de propostas e formatação. Todas essas falhas foram corrigidas e verificadas; nenhuma
validação obrigatória ficou pendente. Nenhum dado privado ou arquivo operacional foi adicionado.

Handoff E04: usar API 1.4.0 e a rota `/market` para a escolha atual; reler `project_version`
após inicialização/análise. GMAX `classification` pertence ao último snapshot e pode diferir da
escolha atual enquanto stale; jamais misturar suas proveniências. Exibir banco/efetivo/origem e
permitir as três opções no seletor, com conflito de versão e reexecução. Novos resultados usam
método 14; reanalisar projetos com snapshots anteriores. Não há DDL nem migração de dados;
rollback de cliente/servidor deve respeitar o piso compatível e o significado dos snapshots.
O gate integral com cobertura e a homologação visual/local permanecem em E09; não foram
executados nem declarados atendidos por E03. Sem bloqueios remanescentes. Nenhum commit,
publicação ou migração operacional realizada.

## E04 — Escolha do técnico na interface — #concluida

**Objetivo:** permitir salvar Rural, Urbano ou Ambos pelo painel Projeto e conferir a origem.
**Por que agora:** E02/E03 tornam a escolha persistida e avaliável.
**Dependências e paralelismo:** E02 e E03; não editar Projeto/GMAX junto de E05.
**Escopo:** `ui/project_panel.py`, `project_gateway.py`, `gmax_panel.py`,
`documentation_gateway.py`, `main_window.py` e testes de gateways/painéis do cliente.
**Fora de escopo:** executar consulta SQL, OCR ou decisão normativa no cliente.

**Passos de implementação:**

1. Adicionar seletor acessível com Rural/Urbano/Ambos e ação de salvar; exibir carregamento,
   não inicializado, falha, valor do banco e origem da seleção sem linguagem de implementação.
2. Usar gateway autenticado fora da thread gráfica; salvar com versão, tratar cancelamento,
   falha e conflito sem sucesso otimista falso nem repetição automática de mutação.
3. Recarregar ao abrir/trocar projeto e reconectar, descartar respostas antigas; sincronizar
   GMAX e estado desatualizado de conformidade. Não iniciar reanálise pesada implicitamente.
4. Atualizar instruções de uso e testes com servidor fake/HTTP isolado.

**Prompt para uma sessão limpa:**

```text
Execute E04 — Escolha do técnico na interface de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro instruções AGENTS.md, roadmap, README.md, ui/project_panel.py, project_gateway.py, gmax_panel.py, documentation_gateway.py, main_window.py e testes relacionados; confira git status. Verifique E02/E03 concluídas e contratos reais compatíveis. Preserve alterações preexistentes, evite editar os mesmos painéis em paralelo com E05 e marque E04 em andamento no índice e detalhe. Adicione no painel Projeto seleção e salvamento Rural/Urbano/Ambos via gateway versionado, com valor inicial do banco e origem visíveis. Trate não inicializado, erro, cancelamento, conflito, respostas antigas, reabertura e reconexão; GMAX e aviso de conformidade desatualizada devem acompanhar a escolha. Não execute SQL ou regras no cliente nem inicie OCR implicitamente. Crie/atualize testes, documentação e execute a validação obrigatória, inclusive inspeção visual. Só marque concluída após aceite; se houver impedimento real, marque bloqueada e documente causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos e resultados. Não declare sucesso com validações falhando ou não executadas; não crie commit nem publique. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Técnico salva as três opções e as encontra após reabertura/reconexão.
- [x] UI distingue banco e escolha manual e informa falha/conflito sem mostrar salvamento falso.
- [x] Troca rápida de projeto não mistura valores; GMAX/conformidade se atualizam coerentemente.
- [x] Controles têm rótulos e navegação por teclado e não bloqueiam a thread gráfica.

**Validação obrigatória:**
`python -m pytest tests/integration/test_project_http_gateway.py tests/unit/test_project_panel_remote_boundary.py tests/integration/test_gmax_panel.py tests/integration/test_client_reconnection.py tests/integration/test_window.py`.
Acrescentar testes da seleção e inspecionar fluxo de salvar, falhar e reconectar nos temas claro
e escuro; todos aprovados. Não exigir banco operacional para testar UI.
**Bloqueios:** nenhum bloqueio conhecido.
**Riscos e mitigação:** estado local divergir do servidor; recarregar DTO canônico após mutação
e usar descarte de respostas antigas existente.
**Evidências e handoff — 10/09/2026:**

- Base `HEAD=4f48c93`, Git inicial limpo. E02 (`101c721`) e E03 (`4f48c93`) concluídas e
  integradas; cabeçalho corrigido para refletir os commits, sem alterar evidências históricas.
  Nenhum `AGENTS.md` encontrado na hierarquia ou checkout. README, roadmap, painéis, gateways,
  contratos e testes relacionados inspecionados. Execução local única, sem agentes nem trabalho
  paralelo em E05. Estado mudou para `#em-andamento` no índice e detalhe antes da implementação.
- `src/zeny_project_handler_client/ui/project_gateway.py`: `get_market` e `update_market` usam
  GET/PUT autenticados de `/market` e os DTOs existentes, com `expected_project_version`.
  Sem alteração da API 1.4.0, schemas, SQL, domínio, regras, OCR ou persistência do servidor.
  PUT continua sem repetição automática, inclusive após timeout.
- Novo `ui/project_market.py`: cartão `projectMarketGroup`, combo `projectMarketCombo`, ações
  `projectMarketSave`, `projectMarketCancel` e `projectMarketRefresh`, rótulos acessíveis, buddy
  e atalhos. Mostra banco inicial, valor salvo, origem e horário UTC. Cancelar descarta somente
  a seleção ainda não enviada; envio em curso aguarda confirmação. Permite confirmar o mesmo
  valor inicial como escolha manual. Erro/conflito limpa valores não confirmados e exige
  Atualizar mercado antes de novo envio; carregamento/não inicializado não presume uma opção.
- Novo `ui/remote_read.py`: trabalho HTTP finito fora da thread Qt, sem capturar widgets.
  Threads permanecem vivas até término/timeout, mesmo após fechamento; callbacks são invalidados
  por geração. Troca de projeto/NS, atualização, fechamento e desconexão descartam respostas
  antigas. Desconexão durante PUT não promete desfazer a escrita; reconectar relê o valor salvo.
- `ui/project_panel.py`: carrega mercado ao ativar/reabrir, após serviços e término de pipeline
  ou conformidade (sucesso/falha/cancelamento); reconexão relê também o projeto ativo.
  A versão confirmada acompanha a sessão, sem rebaixá-la com resposta anterior. Durante envio,
  CRUD, serviços, folhas e análise ficam bloqueados; Projeto mantém os estados do cartão visíveis.
- `ui/main_window.py`, `gmax_panel.py` e `documentation_panel.py`: leitura confirmada do mercado
  dispara releitura assíncrona de GMAX/conformidade. Isso cobre também atualização após conflito.
  GMAX separa escolha do projeto e banco/efetivo/origem da última execução. Snapshot stale mantém
  sua proveniência anterior; erro não o reapresenta como atual. Gerações impedem aplicar leituras
  anteriores após mudança/reconexão. Não há criação implícita de job nem avaliação local.
  `documentation_gateway.py` foi inspecionado e seu contrato existente permaneceu suficiente.
- Testes novos `tests/integration/test_project_market_ui.py` e `test_project_market_http.py`:
  três escolhas, confirmação do valor inicial, cancelamento de seleção, erro/tentativa, ausência
  de inicialização, 404, conflitos, DTO de outro projeto/NS, respostas atrasadas no mesmo e em
  outro projeto, desconexão durante PUT, responsividade Qt, temas, dois clientes HTTP, snapshot
  stale, reexecução explícita e restauração após reinício de servidor/cliente. SQL fake e PDFs
  sintéticos; nenhuma dependência operacional. `tests/remote_gateways.py` acompanha o protocolo;
  `tests/unit/test_project_panel_remote_boundary.py` inclui os novos módulos.
- A regressão ampliada encontrou em `tests/integration/test_mvp_workflow.py` uma expectativa
  anterior a E02: duas consultas SQL ao repetir o pipeline. `git show HEAD:...` confirmou que
  ela já estava no checkout inicial. Atualizada para uma consulta e igualdade da classificação
  persistida entre retomada/repetição, verificando ainda zero consultas antes do cancelamento.
  Nenhum ajuste no backend. Rodada focada após correção: **18 testes aprovados em 5,57 s**.
- Documentação: `README.md`, `docs/especificacao-funcional.md` e este roadmap.
- Inspeção visual: capturas Qt reais em `tmp/e04-visual/`, com `{claro,escuro}` para `salvo`,
  `falha`, `desconectado`, `reconectado` e `janela-stale`. Os oito estados do cartão e as duas
  janelas completas foram abertos e inspecionados. Texto, rótulos, ações e proveniência legíveis
  nos dois temas; GMAX mostra Projeto Ambos e última execução Urbano/banco, marcada stale.
  O primeiro offscreen não encontrou fontes e gerou quadrados: capturas rejeitadas e substituídas
  após carregar `C:/Windows/Fonts/segoeui.ttf` apenas no teste de captura. Nenhuma alteração de
  fontes de produção. O tamanho mínimo atual dos docks expande a janela; rolagem/janela reduzida
  continua no escopo de E05, sem antecipar suas alterações.

Comandos finais na raiz, todos aprovados:

```powershell
$env:ZENY_E04_CAPTURE_DIR = 'tmp/e04-visual'
.venv/Scripts/python.exe -m pytest tests/integration/test_project_http_gateway.py tests/unit/test_project_panel_remote_boundary.py tests/integration/test_gmax_panel.py tests/integration/test_client_reconnection.py tests/integration/test_window.py tests/integration/test_project_market_ui.py tests/integration/test_project_market_http.py tests/integration/test_mvp_workflow.py tests/integration/test_compliance_visibility.py tests/integration/test_compliance_rules_panel.py tests/server/test_project_market_api.py --basetemp=tmp/e4e -p no:cacheprovider -q --tb=short --show-capture=no
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe scripts/complexity_gate.py src
.venv/Scripts/python.exe scripts/client_artifact_gate.py --source-only
git diff --check
```

Resultado consolidado: **82 testes aprovados em 82,52 s**, incluindo todos os obrigatórios de
E04, 11 casos novos de UI/HTTP, regressões documentais e API de mercado. Log local ignorado:
`tmp/e04-final-tests.txt`. Ruff aprovado; **331 arquivos formatados**; Mypy sem erros em
**315 arquivos**; dependências íntegras; complexidade aprovada (**2.707 funções**, nenhuma E/F);
fronteira do cliente e diff aprovados. Falhas exploratórias de importação, fixture de enum,
retenção do widget de captura, espera por callbacks e formatação foram corrigidas. A expectativa
herdada de repetição SQL também foi corrigida e verificada. Não restam falhas ou validações
obrigatórias de E04 pendentes. Critérios de aceite acima atendidos por testes e inspeção visual;
índice/detalhe atualizados para `#concluida` somente após esses resultados.

Handoff E05: preservar nomes dos controles, a separação banco/projeto/snapshot, descarte por
geração e bloqueios de envio. Incluir o cartão `ProjectMarketWidget` na rolagem do painel Projeto
e impedir que rolar o painel altere inadvertidamente o combo. E09 conserva o gate integral com
cobertura e a homologação do PDF/OCR real; não executados nem reivindicados por E04. Sem commit,
publicação, migração ou alteração de dados operacionais.

## E05 — Rolagem independente dos painéis — #concluida

**Objetivo:** evitar compressão de cartões e permitir acessar todo o conteúdo de cada dock.
**Por que agora:** é independente do pipeline e melhora a revisão de resultados extensos.
**Dependências e paralelismo:** nenhuma; pode acompanhar E01/E02, mas serializar com E04 e
mudanças de E06 que atinjam Resultados. **Escopo:** `ui/main_window.py`, `project_panel.py`,
`review_panel.py`, `documentation_panel.py`, `gmax_panel.py`, `portability_panel.py`, `theme.py`.
**Fora de escopo:** redesign da disposição dos painéis ou scroll global da janela inteira.

**Passos de implementação:**

1. Adotar área vertical independente por painel com políticas de tamanho que preservem a
   altura útil de cartões, títulos, campos e tabelas. Manter nomes/identidade dos docks.
2. Permitir expansão horizontal com o dock, quebra de texto e barra vertical quando necessária.
   Tabelas longas mantêm viewport limitado e scroll próprio; não expandir milhares de linhas.
3. Tratar roda sobre tabelas/combos e alcance de ações finais por teclado; evitar scroll preso
   ou alteração acidental do seletor de mercado apenas ao rolar o painel.
4. Preservar acoplamento, flutuação, abas e restauração de layout; documentar e testar a matriz
   visual abaixo com conteúdo extenso e estados vazio/carregando/erro.

**Prompt para uma sessão limpa:**

```text
Execute E05 — Rolagem independente dos painéis de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro AGENTS.md aplicáveis, roadmap, ui/main_window.py, os painéis Projeto, Resultados, Documentação e conformidade, GMAX e Exportar, theme.py e testes de janela/tema/painéis; confira git status e divergências. Não há dependências; evite conflitos de edição com E04/E06. Preserve mudanças preexistentes e marque E05 em andamento no índice e detalhe. Implemente rolagem vertical individual nos cinco painéis, preservando altura legível dos cartões, viewport limitado de tabelas, acesso por teclado e largura adaptável. Verifique roda sobre controles e tabelas, docks flutuantes, abas e restauração do layout. Não redesenhe a organização geral nem modifique o pipeline. Atualize testes necessários e documentação; execute as validações obrigatórias, incluindo a matriz visual em janela reduzida e DPI distintos. Só marque concluída após aceite; se houver impedimento real, marque bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e inspeções. Não declare sucesso com validações falhando ou não executadas. Não crie commit nem publique. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Rolar um painel não altera a posição dos demais nem a página/zoom do PDF.
- [x] Cabeçalhos, campos e ações finais ficam acessíveis sem compressão/recorte dos cartões.
- [x] Tabelas extensas mantêm rolagem utilizável e não impõem altura ilimitada.
- [x] Layout restaurado, docks flutuantes, abas e teclado continuam operantes.

**Validação obrigatória:** `python -m pytest tests/integration/test_window.py tests/integration/test_theme.py tests/integration/test_review_panel.py tests/integration/test_gmax_panel.py tests/integration/test_compliance_rules_panel.py tests/integration/test_portability_panel.py`.
Testar cada dock com dados extensos em 1366×768 e 1920×1080, escala Windows 100% e 150%, temas
claro/escuro e janela redimensionada; capturar evidência local da matriz. Verificar alcance
por Tab e scroll com mouse; testes aprovados e nenhuma ação inacessível.
**Bloqueios:** nenhum pendente. Os impedimentos anteriores de largura/recorte e sincronização E2E foram
corrigidos na retomada sobre `7dd6fbe`. A matriz nativa passou nas oito combinações,
incluindo 911×512 lógicos a 150%, com PDF útil e mensagens sem recorte. Os quatro E2E
foram sincronizados com as leituras de E04, preservando suas verificações de resultado.
Gate completo aprovado: 1.081 testes, nenhuma falha e cobertura 87,32%. Histórico e
evidências detalhados no handoff de E05.
**Riscos e mitigação:** scroll aninhado ou altura mínima da janela crescer demais; validar
políticas do conteúdo e do viewport e transição entre tabela e painel.
**Evidências e handoff:** [e05-rolagem-paineis.md](e05-rolagem-paineis.md). Cinco wrappers
independentes, linhas adaptáveis, viewports limitados e encaminhamento de roda/Tab implementados.
Nomes e preferências dos docks preservados, sem mudanças no pipeline ou sobreposições de E06.
A barra central mantém seus controles em um ou dois grupos de linhas conforme a largura.
Testes, comandos, histórico sobre `897d85c` e retomada sobre `7dd6fbe`, matriz nativa Windows,
logs e inspeção de 128 contatos constam no handoff. Aceite: 82 testes direcionados, 25 E2E,
14 testes nativos em cada escala, oito combinações visuais e verificações estáticas aprovados.
Conclusão em 10/09/2026 após essas validações. Nenhum commit/publicação nesta retomada.

## E06 — Marca-texto por situação — #concluida

**Objetivo:** tornar visível o que foi identificado no PDF com cor operacional e transparência.
**Por que agora:** os DTOs já fornecem situação e geometria; é independente das correções de OCR.
**Dependências e paralelismo:** nenhuma; pode acompanhar E01/E02; serializar edição de
`review_panel.py` com E05. **Escopo:** `ui/pdf_viewer.py`, `visibility.py`, `review_panel.py`,
contrato `review.py` e projeção `src/zeny_project_handler_server/review_api.py` se a geometria
existente não representar a área lida. **Fora de escopo:** alterar situação por cor, editar
originais ou adicionar os marca-textos à exportação PDF.

**Passos de implementação:**

1. Substituir colchetes por preenchimento translúcido nas caixas/polígonos de evidência; para
   ponto ou linha, usar área compacta/faixa compatível com a geometria. Conferir `link_geometry`
   versus `geometry` para não pintar a caixa abrangente de uma região inteira ou de um cabo.
2. Usar verde instalar, amarelo existente, vermelho remover e azul alterar. Iniciar com
   opacidade 25%, validar legibilidade e registrar valor final. Evitar escurecimento excessivo
   por sobreposição de ocorrências ou evidências duplicadas.
3. Separar seleção/estado de revisão da cor operacional por contorno, legenda e tooltip.
   Preservar filtro de visibilidade e tratamento de rejeitadas; uma proposta não revisada
   continua identificável como proposta. Cliques navegam para o mesmo item de Resultados.
4. Manter alinhamento com zoom, rotação, página, prévia/tiles e clipping. Preservar callouts,
   links, hit testing e limites de memória; não rasterizar novamente só para trocar realces.
5. Atualizar testes de geometria/interação, legenda e instruções do visualizador.

**Prompt para uma sessão limpa:**

```text
Execute E06 — Marca-texto por situação de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro AGENTS.md aplicáveis, roadmap, ui/pdf_viewer.py, visibility.py, review_panel.py, ReviewOverlayDto, review_api.py e testes do visualizador; confira git status e divergências. Não há dependências. Preserve alterações preexistentes e marque E06 em andamento no índice e detalhe. Substitua o colchete por realce translúcido da área/traçado identificado: verde instalar, amarelo existente, vermelho remover e azul alterar, com legenda. Comece em 25% de opacidade e documente o valor validado. Verifique geometry/link_geometry, seleção separada da situação, rejeição, filtros, sobreposições, zoom, rotações, paginação, tiles e callouts. Preserve navegação até a revisão e evite marcar regiões inteiras como lidas. Não altere originais nem a exportação PDF. Crie/atualize testes necessários e documentação; execute todas as validações obrigatórias e inspeção visual. Só marque concluída com aceite completo; diante de impedimento real, marque bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões de geometria/cor/opacidade, comandos e resultados. Não declare sucesso com validações falhando ou não executadas; não crie commit nem publique. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] As quatro situações têm cor e legenda corretas, sem depender do estado de aprovação.
- [x] Texto/desenho permanece legível, realce acompanha evidência e colchetes foram substituídos.
- [x] Seleção PDF↔Resultados, visibilidade e rejeição funcionam sem realce órfão.
- [x] Zoom, rotação e troca de tiles/página não deslocam marcação nem ocultam callouts.

**Validação obrigatória:** `python -m pytest tests/integration/test_pdf_viewer_progressive.py tests/integration/test_pdf_viewer_http_gateway.py tests/integration/test_compliance_callout_viewer.py tests/integration/test_compliance_visibility.py tests/unit/test_pdf_coordinates.py tests/unit/test_pdf_rendering_budget.py tests/server/test_review_api.py`.
Adicionar casos de polígonos inclinados, linhas/pontos, sobreposição e situações; inspecionar
temas claro/escuro, zoom 50/100/200% e rotações 0/90/180/270°. Usar fixtures com as três cores
pedidas e Alterar; a NS real complementa a inspeção após E08. Todos os testes aprovados.
**Bloqueios:** nenhum pendente. A restrição de escrita em `C:\tmp` foi comprovada e
resolvida por execução autorizada do gate fora do sandbox; diferença de formatação corrigida
antes da execução final integral aprovada.
**Riscos e mitigação:** geometria ampla comunica leitura inexistente; ancorar nas evidências
efetivas e preservar orientação. Cores do PDF se confundem com overlay; validar transparência,
legenda e alternância de visibilidade.
**Evidências e handoff:** concluída em 10/09/2026 sobre `80caf33`, Git inicialmente limpo e
`HEAD...origin/main = 0 0`, sem AGENTS.md aplicável. Implementação, decisões e comandos em
[e06-marca-texto-situacao.md](e06-marca-texto-situacao.md). Realces localizados por situação,
opacidade 25%, união por cor, seleção separada e rejeitadas sem preenchimento. Contrato
preservado; projeção valida vínculo/página do rótulo. Validação direcionada final: 142 testes
aprovados; matriz visual sintética Qt 24/24 inspecionada (temas claro/escuro, zoom 50/100/200%,
rotações 0/90/180/270°, com tiles e callouts). `IniciarTestes.bat`: saída 0, 1.144 testes
aprovados em 549,75 s, cobertura 87,37%; dependências, Ruff, formatação, Mypy, fronteira do cliente
magro e complexidade aprovados. Relatório local `tmp/e06/gate-final.txt`. Sem commit/publicação.
A inspeção complementar da NS permanece em E08/E09 conforme planejado, sem pendência da E06.

## E07 — Extração robusta de evidências — #concluida

**Objetivo:** recuperar evidências legíveis hoje omitidas na extração, conforme E01.
**Por que agora:** baseline e inventário distinguem falha de leitura de falha de associação.
**Dependências e paralelismo:** E01; independente do mercado/UI. Não editar extrator junto de
outro trabalho no mesmo adaptador. **Escopo:** `adapters/analysis/pymupdf_analyzer.py`,
`pymupdf_page_extractors.py`, `pymupdf_ocr.py`, `pymupdf_symbols.py`, `tesseract_ocr.py`,
`ports/analysis.py`, cache e fixtures de PDFs/OCR.
**Fora de escopo:** resolver topologia, acrescentar modelo externo ou aumentar DPI globalmente
sem medição; mudanças ficam condicionadas às perdas demonstradas em E01.

**Passos de implementação:**

1. Converter cada classe de omissão da extração em fixture: pouco texto nativo com desenho
   denso, glifos vetoriais, texto inclinado/rotacionado, recortes e suas bordas, mistura de
   fotos e diagrama; usar apenas os padrões confirmados e controles negativos próximos.
2. Corrigir decisão e cobertura de OCR, orientação e recortes localizados onde o baseline
   indicar necessidade. Verificar formulários/transformações e mapeamento de volta à página;
   texto nativo de cabeçalho não deve impedir OCR necessário no restante da rede.
3. Consolidar evidências duplicadas sem apagar ocorrências distintas, conservar confiança e
   proveniência. Falta de OCR ou região não processada precisa de diagnóstico observável.
4. Preservar timeouts, cancelamento e orçamento mensurado; incrementar versão/assinatura do
   extrator/configuração afetada e comprovar invalidação correta de cache.
5. Reexecutar benchmark E01 e documentar ganhos/perdas de evidências, tempo e memória.

**Prompt para uma sessão limpa:**

```text
Execute E07 — Extração robusta de evidências de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro AGENTS.md aplicáveis, roadmap e handoff de E01, adapters/analysis, ports/analysis.py, testes de PyMuPDF/Tesseract/cache e git status. Verifique E01 concluída com inventário, baseline completo, comandos e metas; confira divergência do código. Preserve mudanças preexistentes e marque E07 em andamento no índice e detalhe. Corrija somente classes de perda na extração demonstradas por E01, criando fixtures sintéticas de orientação, conteúdo vetorial/texto parcial e recortes pertinentes. Preserve geometria normalizada, confiança, proveniência, deduplicação por ocorrência, cancelamento e orçamentos. Exponha falhas de OCR sem aparentar leitura completa; atualize versão/assinatura para não reutilizar cache incompatível. Não corrija topologia nesta etapa nem use OCR externo. Atualize documentação/testes, execute validação obrigatória e repita o benchmark local com OCR real. Só marque concluída após cumprir os critérios e as metas de extração; diante de impedimento real, marque bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, versões, decisões, comandos e comparativo. Não declare sucesso com validação falhando ou não executada; não crie commit nem publique. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Todas as omissões inequívocas atribuídas à extração em E01 têm evidência recuperada.
- [x] Evidências preservam posição/orientação e não duplicam a mesma ocorrência.
- [x] Ausência/falha de OCR é diagnosticada e cache antigo não mascara o novo comportamento.
- [x] Benchmark com OCR real atende metas/orçamentos de E01 e hash da origem não muda.

**Validação obrigatória:** `python -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_tesseract_ocr.py tests/unit/test_tesseract_runtime.py tests/unit/test_analysis_cache.py tests/unit/test_pdf_coordinates.py tests/integration/test_document_analysis.py`.
Executar também novas fixtures e o comando de benchmark completo registrado por E01, comparando
itens, caixas, diagnósticos e desempenho. Todos os testes devem passar; mocks de OCR não
substituem a comparação local com Tesseract real.
**Bloqueios:** nenhum pendente. Em 14/09/2026, inventário, baseline e runtime originais de
E01 foram recuperados. A referência foi reconciliada por inspeção do PDF, mantendo os
denominadores, as geometrias físicas e a tolerância. As omissões de extração foram recuperadas
dentro dos limites congelados. O encerramento prematuro da thread de exportação, que abortava
o gate Qt, foi corrigido e recebeu regressão com falha antes/aprovação depois. E08 está
desbloqueada para tratar associação e topologia. Evidências e limites do aceite em
[e07-extracao-evidencias.md](e07-extracao-evidencias.md).
**Riscos e mitigação:** excesso de recortes/DPI e falso texto em fotos; limitar por região,
medir orçamento e testar controles negativos. Se a investigação revelar frentes independentes
que não cabem em uma sessão, subdividir antes de iniciar, preservando IDs já executados.
**Evidências e handoff:** concluída em 14/09/2026 sobre `f82b1c2`, Git inicialmente limpo.
Extrator **1.14.0**: OCR de contornos originais, transformação inversa, concordância entre
glifos repetidos, lotes por largura e reutilização da lista de desenho por página. Cache
anterior invalidado; erros e limites preservam diagnósticos. Sem alteração na interpretação,
nas normas ou na fonte. Correção adicional de sincronização no encerramento da exportação Qt.

A auditoria por token e ocorrência recuperou **95/95** itens (17 postes, 22 MT, 19 BT e
37 cabos), **18/18 identificadores** e **19/19 comprimentos**. Os 132 recortes do PDF original
foram conferidos; as duas folhas alteradas pela otimização final foram reinspecionadas.
O inventário original permanece intacto; a cópia registra uma correção de transcrição,
três ROIs de cabo e caixas de rótulos separadas das geometrias físicas, sem mudar denominadores.
Leituras compostas gerais preservam os outros tokens; a consolidação de recortes equivalentes
mantém ocorrências distintas. Isso certifica a entrada textual/espacial, não a associação de E08.

Validação final: **197 testes direcionados**, **7 testes do painel de exportação** e gate
integral **1.238 aprovados / 87,72% de cobertura**, saída 0, com todas as verificações de
qualidade aprovadas. Benchmark completo: **15,511 s nativo / 55,313 s OCR**; high-water Python
**548,36 MiB**, Tesseract observado **85,30 MiB**, agregado amostrado **481,08 MiB**.
Hash, tamanho e mtime da origem preservados. Saída: **399 OCR, 105 propostas finais,
97 confirmações e 30 vãos**, sem homologação semântica dessas contagens. Há 21 MT na saída
para 22 no inventário e 11 propostas de equipamento fora das 95 ocorrências; E08 deve conferir
normalização, situações, promoção e endpoints. Reanalisar com a versão nova.

Artefatos privados em `tmp/e07-complete/`, ignorados pelo Git; fixtures públicas sintéticas.
Comandos, memória, auditoria, falhas anteriores e correções no handoff. Sem commit/publicação.
Os registros seguintes são históricos e não representam o aceite vigente.

**Registro de 10/09/2026:** execução sobre `77258cf`, Git inicialmente limpo e
nenhum `AGENTS.md` aplicável. E01 conferida com inventário, baseline, comandos, metas e três
verificações privadas aprovadas; extrator/ports sem divergência desde E01. Especialistas
separaram runtime TSV, retificação/recortes e revisão; integração/validação no trabalho principal.

**Retomada em 11/09/2026 sobre `7fd1b7f`:** extrator **1.13.0**, com lote de até 48 recortes
e oito milhões de pixels, geometria por ocorrência e diagnóstico ao exceder o orçamento.
Nenhuma alteração em interpretação/topologia, normas ou PDF. Runtime português provisionado
localmente. **162 testes obrigatórios aprovados**, **13 HTTP/Qt aprovados**, suíte pública
**1.202 aprovados / 87,71% de cobertura**; Ruff/formatação e Mypy finais aprovados.
A execução do `.bat` havia registrado um erro de tipagem no teste novo; a correção e a
repetição aprovada do Mypy estão documentadas, sem reclassificar o log antigo. Benchmark
final: **312 evidências OCR, 33 propostas, 27 confirmações automáticas e seis vãos**, com
hash/tamanho/mtime preservados. Tempos **19,652 s nativo / 47,957 s OCR**; high-water Python
**515,88 MiB**, Tesseract amostrado **80,26 MiB**, agregado **445,88 MiB**, dentro dos limites.
Contagens não certificam classificação/associação correta.
Artefatos locais da retomada em `tmp/e07-unblock/`; comparação, limites e comandos no handoff.
Os itens abaixo preservam o histórico de 10/09/2026 e não são as métricas atuais.

- Extrator **1.12.0**: orientação dos recortes densos, geometria normalizada com arredondamento
  do raster, molduras retraçadas sem reflexão, deduplicação de texto igual por sobreposição,
  preservação de recortes concluídos em falha e diagnóstico de cobertura parcial.
- Tesseract solicita TSV sem `configs/tsv`, valida o cabeçalho e altera a assinatura de
  capacidade. Falhas transitórias não são salvas no cache. Controle sintético com Tesseract
  real sem `configs/` aprovado. Portas e topologia preservadas.
- Conjunto obrigatório e regressões novas: **151 aprovados**. Ruff/formatação, Mypy
  (324 arquivos), dependências, cliente magro e complexidade aprovados. Suíte pública
  adicional: **1.190 aprovados, 1 falha**, cobertura **87,69%**; repetição isolada da falha:
  **1 aprovado**. Não há aprovação global, nem conclusão de E07.
- Benchmark final com OCR real: **23,406 s nativo / 53,959 s OCR**, dentro dos limites;
  high-water Python **539,85 MiB**, pico Tesseract amostrado **81,79 MiB**, agregado
  **493,95 MiB**. Hash/tamanho/mtime preservados. OCR **273 → 270** evidências, propostas
  **3 → 7**, confirmações **0 → 1**; **80/95** ocorrências continuam sem código intacto,
  incluindo os **37 cabos**. Esses resultados impedem homologar recuperação integral.
- Arquivos, comandos completos, versões, métricas, falhas e ações de desbloqueio em
  [e07-extracao-evidencias.md](e07-extracao-evidencias.md). Fixtures públicas sintéticas;
  PDF, recortes, inventário e snapshots privados permanecem ignorados. Sem commit/publicação.

## E08 — Associação de elementos e vãos — #bloqueada

**Objetivo:** transformar evidências recuperadas em ocorrências, vínculos e vãos corretos.
**Por que agora:** E07 garante entrada espacial/textual verificável para corrigir associação.
**Dependências e paralelismo:** E01 e E07; independente do mercado/UI, exceto testes de projeções
compartilhadas. **Escopo:** `adapters/interpretation/rule_based.py`, `category_analyzers.py`,
`operational_labels.py`, `relation_rules.py`, `span_rules.py`, `application/analysis_regions.py`,
`automatic_promotion.py`, `spans.py`, pipeline e projeções de revisão do servidor.
**Fora de escopo:** criar ativos/comprimentos por mera expectativa ou redesenhar todo o motor.

**Passos de implementação:**

1. Reproduzir cada omissão de interpretação/promoção/vão de E01 em fixture sintética, incluindo
   elementos repetidos em posições distintas e rótulos de pontos, cabos e comprimentos próximos.
2. Corrigir normalização e vínculo entre texto, símbolo, região e catálogo quando sustentados
   por evidência. Preservar qualificadores como `N(2)` sem expandi-los em quantidade.
3. Resolver traçados/endpoints e comprimentos com evidência; preservar segmentação dos vãos,
   medidas substituídas, situações operacionais, pontos de entrega e separação rede/ramal.
   Não preencher lacunas ligando automaticamente os pontos mais próximos.
4. Conferir promoção, identidade e revisão humana: item sem classificação suficiente continua
   revisável e explica por que não originou ativo/vão. Reanálise não duplica nem perde decisões
   silenciosamente. Incrementar versão/assinatura de interpretação quando aplicável.
5. Medir a cadeia completa até DTOs de Resultados e exportação; comparar com inventário E01,
   registrar regressões sintéticas e atualizar documentação de limitações resolvidas.

**Prompt para uma sessão limpa:**

```text
Execute E08 — Associação de elementos e vãos de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro AGENTS.md aplicáveis, roadmap e handoffs de E01/E07, ADR 0015, adaptadores de interpretação, analysis_regions.py, automatic_promotion.py, spans.py, pipeline e testes; confira git status. Verifique E01/E07 concluídas e código sem divergência não tratada. Preserve mudanças preexistentes e marque E08 em andamento no índice e detalhe. Recupere as ocorrências e os vãos inequívocos do inventário, corrigindo apenas perdas demonstradas de normalização, associação, promoção e endpoints. Crie regressões sintéticas com controles negativos, preserve qualificadores, situações, comprimentos substituídos, rede/ramal/padrão, revisão humana e identidades determinísticas. Não invente cabos, medidas ou vínculos por proximidade; torne ambiguidade revisável. Atualize versões/assinaturas, documentação e testes necessários. Execute as validações obrigatórias e benchmark completo até Resultados/exportação, cumprindo metas de qualidade E01. A diretriz vigente substitui os limites históricos de tempo: duração não reprova a leitura, inclusive acima de cinco minutos; preserve progresso, memória e cancelamento. Só marque concluída após aceite; se houver impedimento real, marque bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos, métricas e casos remanescentes. Não declare sucesso com validação falhando ou não executada; não crie commit nem publique. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [ ] Todos os elementos/vãos legíveis e inequívocos do inventário aparecem com vínculos corretos.
- [ ] Endpoints, comprimentos e situações correspondem à evidência; ambiguidades são explícitas.
- [x] Não há falsos ativos/vínculos nos controles negativos nem duplicação ao reanalisar.
- [x] Resultados e exportação concordam; revisões humanas e histórico são preservados.

**Validação obrigatória:** `python -m pytest tests/unit/test_rule_based_interpreter.py tests/unit/test_spans.py tests/unit/test_analysis_regions.py tests/unit/test_topology_path_compliance.py tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py tests/server/test_review_api.py tests/server/test_deliverable_exports.py tests/e2e/test_span_compliance_ui.py`.
Executar novas regressões e benchmark E01 com OCR real, promoção e vãos. Exigir precisão/recall
por categoria, correspondência dos endpoints/comprimentos e duplicatas; registrar duração
apenas como telemetria, além de navegação visual amostrada em cada classe de correção. Testes todos aprovados.
**Bloqueios:** falta evidência técnica de padrão no endpoint junto à casa e de formato/material
para escolher os 17 modelos de poste; a ocorrência não basta para inventar essas classes
(ADR 0015 e candidatos preservados nas propostas). Isso impede certificar ramal/rede resolvidos.
Desbloqueio: classificação rastreável ou revisão técnica formal da expectativa do inventário.
Há também trabalho de software remanescente: comprimento explícito de T02 sem associação segura
(18/19, abaixo da meta) e projeção por cabo/segmento que não equivale aos 20 trechos físicos.
Evidência, impacto e próximos passos detalhados no handoff abaixo; as metas não foram relaxadas.
**Riscos e mitigação:** melhorar recall fabricando relações; testar casos ambíguos e negativos.
Identidade mudar ao corrigir geometria; comprovar comportamento de reanálise e decisões antigas.
Subdividir antes de iniciar se E01 revelar correções independentes além de uma sessão.
**Evidências e handoff:** iniciada e marcada em andamento em 14/09/2026 sobre `bb457ef`, Git limpo e sem
`AGENTS.md` aplicável. E01/E07 concluídas; inventário, baseline e runtime privados presentes.
O commit atual integra o aceite E07 sobre `f82b1c2`; não há divergência de interpretação
ou topologia desde aquela base. Fechamento **bloqueado para aceite**, com código validado,
em [e08-associacao-elementos-vaos.md](e08-associacao-elementos-vaos.md).

- Interpretador 22.0: normalização de qualificadores, situação do rótulo, traçados/endpoints,
  guardas de comprimento/promoção e preservação da revisão na reanálise. Nenhum ativo criado
  para preencher ausência de classificação. Extrator e contrato HTTP preservados.
- Auditoria final: precisão/recall 100% por categoria/situação nas 95 ocorrências, 95 vínculos
  corretos, 18/18 pares visíveis e 18/19 comprimentos; zero propostas elegíveis sem par.
  Há 20 traçados distintos, 35 cabos confirmados e 28 linhas de Vãos ainda de tipo desconhecido.
- Benchmark isolado até Resultados/XLSX: 15,501/56,904 s nativo/OCR no escopo E01;
  18,308/59,548 s incluindo exportação. Python 602,37 MiB, Tesseract 80,46 MiB,
  agregado amostrado 452,55 MiB. Metas de desempenho cumpridas; fonte inalterada.
- 125 testes direcionados, repetição final de 16 testes E08/benchmark, três verificações
  privadas de E01 e seis amostras de navegação visual aprovados. Gate final: **1.250 testes,
  87,71% de cobertura, saída zero**, incluindo dependências, Ruff, Mypy e complexidade.
  O gate intermediário falhou por complexidade e não foi usado como aceite.
- Dados reais e auditorias somente em `tmp/e08/`, ignorado; comandos, arquivos e casos
  remanescentes no handoff. E09 permaneceu pendente naquele encerramento. Sem commit ou publicação.

## E09 — Homologação integrada — #bloqueada

**Objetivo:** comprovar os quatro pedidos juntos no cliente/servidor e consolidar documentação.
**Por que agora:** as mudanças individuais precisam de aceite integrado com o PDF motivador.
**Dependências e paralelismo:** E03/E04/E05/E06/E08 e suas dependências; executar após estabilizar
os arquivos para que resultados pertençam à mesma revisão. **Escopo:** testes de integração/e2e,
`README.md`, `docs/especificacao-funcional.md`, arquitetura/API afetadas, este roadmap e relatório
sanitizado de validação em `docs/` (arquivo novo, se necessário).
**Fora de escopo:** implantação, release, commit ou alteração de dados operacionais.

**Passos de implementação:**

1. Em ambiente isolado com SQL fake, abrir projeto, inicializar mercado, salvar cada opção,
   reabrir/reconectar, reanalisar e comparar regras; testar conflito entre dois clientes e
   troca de NS. Confirmar proveniência, snapshot desatualizado e exportação coerente.
2. Com a NS real e OCR real, repetir inventário/benchmark, navegar elementos/vãos usando
   marca-textos e revisar painéis com dados extensos na matriz de E05/E06. Conferir hash final.
3. Executar o gate público completo e verificar que o caso real continua opcional para CI.
   Corrigir regressões de integração; não reduzir metas/cobertura para concluir.
4. Revisar docs que afirmavam mercado exclusivo do SQL a cada análise, explicar persistência,
   Ambos, rolagem, legenda, reanálise e limites conhecidos. Consolidar evidências sanitizadas;
   manter capturas e dados privados locais. Conferir definição global de pronto item por item.

**Prompt para uma sessão limpa:**

```text
Execute E09 — Homologação integrada de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro AGENTS.md aplicáveis, roadmap inteiro, handoffs E01–E08, README.md, docs/especificacao-funcional.md e testes de integração/e2e; confira git status. Verifique E03/E04/E05/E06/E08 e dependências concluídas e código coerente com as evidências. Preserve alterações preexistentes e marque E09 em andamento no índice e detalhe. Valide em ambiente isolado o fluxo de inicialização SQL, escolha Rural/Urbano/Ambos, persistência, conflitos, reconexão, reanálise, snapshots e exportação. Execute benchmark com OCR real da NS 1256148225 e verifique marca-textos, navegação e rolagem dos cinco painéis conforme as matrizes visuais. Execute o gate público completo; mantenha PDFs reais opcionais e fora do Git. Corrija regressões de integração dentro do escopo e atualize documentação do comportamento final, sem diminuir metas de qualidade. Conforme a diretriz vigente, tempo não é critério de aceite, e cinco minutos não é teto; preserve memória, progresso e cancelamento. Só marque concluída após satisfazer toda a definição global de pronto e validações; se houver impedimento real, marque bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos, métricas e inspeções. Não declare sucesso com validações falhando ou não executadas. Não crie commit, release, publicação ou migração operacional. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [ ] Todos os itens da definição global de pronto possuem evidência rastreável.
- [x] Gate público integral aprovado com cobertura mínima 85,01% e fixtures independentes do PDF.
- [ ] NS 1256148225 atende inventário/metas E01 no pipeline completo e no visualizador.
- [x] Documentação, contrato, histórico e exportações descrevem o comportamento entregue.

**Validação obrigatória:** `.\IniciarTestes.bat`, que cobre integridade das dependências, Ruff,
formatação, Mypy, fronteira do cliente magro, Pytest com cobertura e complexidade. Exigir saída
zero e relatório aprovado. Rodar o benchmark local de E01 e as matrizes visuais E05/E06 no
fluxo integrado; `python scripts/smoke_examples.py` complementa regressão nativa nos exemplos
locais disponíveis, mas não substitui o benchmark com OCR. Verificar diff do Git sem PDFs,
recortes, credenciais ou dados de execução. Não é necessário SQL operacional para esse gate.
**Bloqueios:** E08 continua abaixo do aceite: T02/V2-3 permanece em **18/19 comprimentos**;
faltam classificação técnica de postes/entregas e aceite da representação de trechos por cabo.
A inspeção E09 demonstrou ainda realce amplo de proposta simbólica de Para-raios MT: a caixa
da evidência inclui linha e rótulos vizinhos. **Impacto:** a NS não satisfaz a definição global
de pronto, apesar do gate aprovado. **Desbloqueio:** concluir os casos E08, corrigir a evidência
simbólica com regressão e negativos, verificar os demais equipamentos e repetir benchmark e
inspeção integrada na revisão resultante. Não ocultar propostas nem reduzir metas. Causa,
geometria, capturas e rastreio constam de [e09-homologacao-integrada.md](e09-homologacao-integrada.md).
PDF/OCR estavam disponíveis; SQL operacional não é necessário para este gate.
**Riscos e mitigação:** relato de sucesso apenas de testes sintéticos; exigir os dois conjuntos
de evidência, público e local, sem tornar o segundo requisito de CI.
**Evidências e handoff:** iniciada em 14/09/2026 sobre `cd598bc`, Git limpo e sem
`AGENTS.md` aplicável. E01–E07 concluídas; E08 permanece bloqueada e seu código está integrado
na base. Por solicitação explícita, iniciadas as validações independentes de E09; o aceite
global continua impedido por E08 e pelo caso visual encontrado. Gate completo: **1.250 testes
aprovados em 449,12 s / 87,71% de cobertura**, saída 0, com todas as verificações de qualidade
aprovadas. Benchmark OCR real: **59,953 s** no escopo congelado E01 e **62,657 s** incluindo
Resultados/exportação; nativo **15,476 / 18,473 s**. Python **598,59 MiB**, Tesseract observado
**80,46 MiB**, agregado amostrado **527,93 MiB**. Sem margem estável demonstrada nos 60 s OCR.
Auditoria: **95/95 ocorrências e vínculos, 18/18 identificadores e endpoints visíveis,
18/19 comprimentos**, 106 propostas e 28 linhas de Vãos. Origem preservada.

Escolhas Rural/Urbano/Ambos, snapshots, três conflitos HTTP e exportações reais conferidos;
Ambos equivale à união dos achados sem duplicação. Smoke nativo **1/1** e referência E01 **3/3**
aprovados. Matrizes sintéticas E05 **28 testes / oito cenários** e E06 **24 casos** executadas
e inspecionadas. Complemento HTTP real: **oito testes aprovados** nas duas escalas, 40 navegações
e **24 capturas de zoom/rotação**, oito mosaicos de painéis e dois de marca-textos inspecionados.
Asserções de interação/rolagem passaram; **aceite visual real reprovado pela caixa ampla de
equipamento**. Handoff final: [e09-homologacao-integrada.md](e09-homologacao-integrada.md).
Nenhuma alteração de produção, commit, release, publicação ou migração operacional.
PDFs e dados privados ignorados.

## Contexto e aceite da extensão E10–E15

Esta extensão é planejamento, sem implementação de produção nesta tarefa. Leia
`docs/diagnostico-rede-1256407599.md` antes de executar as etapas. Na base `9cb0ef7`,
o PDF tem uma página, 988.018 bytes e 28 anotações; o extrator é `1.14.0` e o
interpretador `22.0`. O benchmark com OCR real produziu 38 propostas, 10 cabos
confirmados e 8 linhas de Vãos, com erros D01–D06 detalhados no diagnóstico.
Os oito testes das ferramentas passaram; não houve homologação integral.

**Escopo incluído:** camada técnica vigente, extração, interpretação, catalogação,
associação, promoção, topologia, revisão humana, projeções, detecção documental e
exportação das informações suportadas pelo produto. Cada informação relevante
legível deve estar representada ou ter ambiguidade/limitação explícita e navegável.
Inclui evolução vertical dos métodos atuais e horizontal por algoritmos distintos,
com comparação experimental obrigatória e reconciliação orientada por evidências.
**Fora de escopo:** reconstrução artística, interpretação irrestrita de fotografias,
autenticação de assinaturas, inclusão de normas sem fonte, alteração do PDF,
OCR externo, publicação/release e implementação durante a elaboração do roadmap.

**Invariantes:** aplicar as restrições globais acima; manter cliente magro,
identidades e decisões humanas, original intacto e dados reais ignorados. Não
promover texto de comentário, carimbo ou fotografia como ativo; não escolher cabo,
modelo de poste ou padrão por conveniência. Não elevar E08/E09 a concluídas pela
aprovação deste segundo exemplo. Usar fixtures sintéticas públicas e manter o
gate independente de `examples/`. Testes/documentação acompanham cada mudança.

**Hipóteses e decisões em aberto:**

- A cópia atual foi revisada e não tem identidade comprovada com o arquivo da
  release antiga. Impacto: o baseline vale para o hash registrado, sem promessa
  de medir ganho entre releases sobre entrada idêntica.
- Parte do conteúdo vigente está em anotações. A política padrão proposta é
  detectar conflito e exigir revisão técnica explícita quando a autoridade da
  sobreposição for ambígua, preservando os dois valores. E10 documenta essa
  decisão antes de E11; a data de um carimbo não basta para aceitar conteúdo.
- A referência integral de ocorrências/campos e a classificação de pontos ainda
  não foram auditadas. Impacto: E10 fixa denominadores antes de correções; nenhum
  percentual de cobertura pode ser inferido das 38 propostas.
- E08/E09 contêm trabalho e bloqueios relacionados, mas seus estados não impedem
  iniciar o diagnóstico do segundo PDF. E13/E14 devem conferir alterações nessa
  base e reutilizar correções aplicáveis, evitando implementações concorrentes.
- O tempo OCR observado inclui inspeção concorrente. E10 registra duração e memória
  como telemetria; não fixa SLA nem limite de duração. Cinco minutos ou mais são
  aceitáveis se necessários à confiabilidade. A memória e os mecanismos de
  recuperação devem permitir executar o método sem perder evidências.
- Métodos alternativos ainda não foram selecionados nem instalados. E12A verifica
  licença, execução local, hardware e capacidade de produzir evidência antes da
  escolha. Ausência de GPU não justifica omitir a frente horizontal: experimentar
  alternativas compatíveis ou registrar impedimento concreto e opção de desbloqueio.

**Definição de pronto da extensão:** inventário E10 congelado e reconciliado,
100% dos itens legíveis e inequívocos recuperados com código, situação, geometria
e relações corretos; divergências de revisão explícitas; zero duplicatas/falsos
positivos conhecidos nos controles; ambiguidades reais separadas de defeitos de
software, sem reduzir denominadores para aceitar omissões. Verificar rede nova,
existente e ligação ao consumidor, campos documentais suportados, navegação e
concordância HTTP/Resultados/XLSX. Comprovar comparação vertical/horizontal,
reconciliação por evidência e qualidade em casos reservados; preservar cache/cancelamento e
gate público completo com cobertura mínima de 85,01%. O aceite se limita à
informação sustentada pela fonte; classificação não demonstrável deve continuar
revisável, sem ser apresentada como resolvida. E15 registra isso por item.

Execute uma etapa por sessão limpa. A ordem preferencial é
E10→E11→E12→E12A→E12B→E13→E14→E15. Os IDs existentes são preservados; E12A/E12B
são novas etapas, posicionadas antes de seus consumidores. Nesta execução
não há execução paralela de código prevista, pois as etapas compartilham os
extratores e as projeções. As dependências pendentes não são bloqueios reais.

## E10 — Referência integral do segundo PDF — #concluida

**Objetivo:** transformar o diagnóstico amostral em referência auditável de toda a
página e medir o custo real por fase antes de modificar heurísticas.
**Por que agora:** faltam denominadores e a política para revisões sobrepostas.
**Dependências e paralelismo:** nenhuma; ler os resultados de E01/E07/E08/E09 sem
alterar seus estados. Inventário e benchmark usam a mesma cópia identificada.
**Escopo:** diagnóstico do segundo PDF, `scripts/benchmark_network_pdf.py`,
`tests/unit/test_benchmark_network_pdf.py`, `tests/pdf_fixtures.py`, anotações e
DTOs produzidos. Dados completos em `tmp/rede-1256407599/`.
**Fora de escopo:** corrigir extrator, catálogo ou associação nesta etapa.

**Passos de implementação:**

1. Inventariar a página com e sem anotações: ocorrências físicas, qualificadores,
   códigos, situações, pontos sem identificador, cabos, medidas, quadros, cabeçalho,
   notas, servidão, fotos e assinaturas. Separar representação repetida de ocorrência
   distinta, com ROIs e evidência do julgamento.
2. Rastrear cada item até evidências, propostas, promoção, DTO e XLSX; classificar
   perdido, incorreto, duplicado, ambíguo ou correto. Incluir obrigatoriamente D01–D06.
3. Definir contrato de tratamento da revisão técnica: detectar conflito primeiro,
   preservar proveniência/valor anterior e permitir decisão explícita. Documentar
   impacto em UI/DTO/cache antes de E11; não aceitar todo Stamp como técnico.
4. Repetir benchmark isolado, registrar chamadas/tempo OCR, memória Python/Tesseract
   e custo de anotações em três execuções, sem limiar de aprovação por tempo. Acrescentar
   instrumentação opt-in e teste sintético ao benchmark se necessária.
5. Registrar inventário privado e resumo sanitizado no diagnóstico; fixar as metas
   de precisão/recall por categoria, campos e topologia, sem incluir dados pessoais.
6. Separar exemplos de ajuste e avaliação reservada por documento ou família
   sintética, evitando recortes quase idênticos em ambos. Incluir o PDF anterior
   quando disponível, casos negativos e variações de orientação/cor/escala/revisão.
   Fixar também erro entre confirmações automáticas, cobertura automática, taxa de
   revisão e leitura exata do projeto inteiro; não aceitar abstenção generalizada.

**Prompt para uma sessão limpa:**

```text
Execute E10 — Referência integral do segundo PDF de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, roadmap, docs/diagnostico-rede-1256407599.md, docs/e01-diagnostico-leitura-rede.md, scripts/benchmark_network_pdf.py, tests/unit/test_benchmark_network_pdf.py e git status. Não há dependências de execução; confira a revisão atual, divergências do plano e preserve mudanças preexistentes. Marque E10 como #em-andamento no índice e detalhe. Inventarie toda a página do PDF local 1256407599 com e sem anotações, incluindo D01–D06, situações, cabos, pontos, quadros e documentação. Rastreie itens até evidência/proposta/ativo/DTO/XLSX; não infira recall por contagem. Fixe a política de revisão técnica, denominadores e metas de qualidade, com casos reservados por documento/família e métricas de erro entre confirmações, cobertura automática e revisão. Registre três benchmarks isolados e memória; tempo é apenas telemetria, sem teto de 60 ou 300 segundos. Mantenha artefatos privados em tmp e implemente apenas instrumentação opt-in e testes sintéticos necessários, sem corrigir o pipeline. Execute as validações de E10 e atualize documentação. Só use #concluida com todos os critérios e validações aprovados; não declare sucesso com testes falhando ou não executados. Se um impedimento real surgir, use #bloqueada com causa, evidência, impacto e ação de desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e itens para E11. Não faça commit ou ação externa. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Inventário cobre toda a página, distingue camadas e fixa denominadores por classe.
- [x] D01–D06 têm cadeia de evidência e a política de revisão está documentada.
- [x] Três medições isoladas e memória ficam registradas, sem limite de tempo para aceite.
- [x] Casos reservados e métricas de qualidade/confirmados/revisão estão congelados.
- [x] Testes do benchmark passam sem exigir arquivo privado.

**Validação obrigatória:** executar o comando OCR do diagnóstico três vezes, com
saídas distintas em `tmp/rede-1256407599/`; conferir hash/tamanho/mtime. Rodar
`python -m pytest tests/unit/test_benchmark_network_pdf.py tests/unit/test_smoke_examples.py`.
Inspecionar todos os recortes do inventário e conferir cada vínculo ao snapshot.
**Bloqueios:** nenhum impedimento remanescente ao diagnóstico E10. PDF/OCR disponíveis;
as falhas de qualidade abaixo pertencem às correções seguintes e não foram resolvidas.
**Riscos e mitigação:** denominador baseado na saída ocultar perdas; inventariar primeiro
pelo desenho. Confundir revisões com comentários; registrar ambos e a autoridade conhecida.
**Evidências e handoff:** executada em 14/09/2026 sobre `80dc6fd`, Git inicialmente
limpo, sem `AGENTS.md` aplicável. Passou por `#em-andamento` no índice e detalhe.
Desde `9cb0ef7`, somente roadmap/diagnóstico diferiam; E08/E09 preservadas.
Relatório completo: [e10-referencia-segundo-pdf.md](e10-referencia-segundo-pdf.md).

- 139 registros privados cobrem as duas camadas: núcleo de 29 ocorrências, nove
  pontos, dez trechos, seis comprimentos, dois conflitos, 64 itens documentais e
  estratos de símbolos/ambiguidades/negativos. As 28 anotações têm registro próprio.
  D01–D06 e todas as 38 propostas finais rastreadas até evidência/ativo/DTO/XLSX.
- Núcleo na proposta: TP 24, FN 5, FP 4; recall 82,76%, precisão 85,71%, com escopo
  de código/situação/ocorrência explícito. Duas confirmações erradas em dez; oito
  acertam esses campos, mas cobertura automática integral comprovada continua 0/29.
  Os dois conflitos não são representados e a leitura exata do documento é 0/1.
  Isso é baseline para correções, não aceite da leitura automática.
- Três benchmarks novos, sequenciais, sem análise Python concorrente: OCR até
  regiões/vãos 94,130 / 89,407 / 94,104 s; com DTOs/XLSX documental 96,488 / 91,741 /
  96,706 s. Cada um realizou 81 chamadas OCR, mais controle separado. Memória
  simultânea máxima amostrada 490,69 MiB; Python high-water observado até 374,74 MiB,
  Tesseract até 216,11 MiB. Hash, tamanho e mtime preservados em todas as execuções.
  Duração somente telemetria, sem teto de aceite. Sonda CIM negada foi substituída;
  isso não impediu medir memória dos processos. Limitações de amostragem documentadas.
- `scripts/benchmark_network_pdf.py`: `--telemetry` observa os cinco modos OCR,
  renderização das anotações e insumos documentais puros até DTO/XLSX. Instrumentação
  opt-in, sem mudar produção, catálogo, parâmetros OCR, contratos ou pipeline.
  `tests/unit/test_benchmark_network_pdf.py`: controles sintéticos de transparência,
  falhas e camadas. Nenhum PDF privado é necessário nos testes públicos.
- Validação final: **17 aprovados em 5,42 s** (11 públicos + seis privados), Ruff,
  formatação, Mypy (334 arquivos), diff e isolamento dos artefatos aprovados. Comandos
  exatos e falhas iniciais corrigidas no relatório. Gate global/HTTP/Qt e avaliação
  reservada pertencem às etapas posteriores e não foram reivindicados em E10.
- Artefatos ignorados em `tmp/rede-1256407599/e10/`: `inventory.json`, `audit.json`,
  rasters, anotações, `run-1/2/3.json`, `memory-1/2/3.json`, `performance.json`, logs,
  scripts privados e `evaluation-split.json`. Três famílias sintéticas/nove sementes
  reservadas; PDFs conhecidos são ajuste/regressão. Dois outros PDFs são candidatos
  à reserva documental, sujeitos à auditoria de exposição anterior.
- E11 recebe conflito de cabo e N4, oclusões, cópia ampliada, decisão técnica explícita
  e impactos em UI/DTO/cache. E12/E13 recebem neutros N-4 omitidos, transformador,
  chave descartada, vínculo U1/P5 e qualificadores perdidos na exportação; E14 recebe
  endpoints P3/P4 invertidos, IDs por cabo e supressão de existentes. E15 recebe
  campos documentais truncados/repetidos/ausentes e homologação integrada.
  Nenhuma correção do pipeline, commit ou ação externa realizada.

## E11 — Revisões técnicas e conteúdo vigente — #concluida

**Objetivo:** representar conteúdo técnico sobreposto e conflitos com a camada base,
sem promover anotações comuns nem usar silenciosamente valores encobertos.
**Por que agora:** D01 impede considerar o raster técnico atual igual ao PDF exibido.
**Dependências e paralelismo:** E10; implementação sequencial, pois altera origem de
evidências e revisão consumidas pelas etapas seguintes.
**Escopo:** `adapters/analysis/pymupdf_ocr.py`, `pymupdf_page_extractors.py`,
`application/document_zones.py`, `human_review.py`, `automatic_promotion.py`,
`src/zeny_project_handler_server/review_api.py`, contratos/clientes afetados pela
política E10. Paths de domínio e persistência adicionais serão localizados antes de editar.
**Fora de escopo:** considerar toda anotação aprovada ou reescrever/achatar o PDF original.

**Passos de implementação:**

1. Criar fixture sintética de código base coberto por revisão, mais comentários,
   Stamp de revisão, assinatura, foto, Ink e SHX como controles separados.
2. Extrair aparências técnicas com proveniência e detectar ocultação/conflito.
   Preservar valor base e sobreposto; aplicar somente a decisão rastreável prevista
   por E10. Na ambiguidade, impedir confirmação automática do valor encoberto.
3. Persistir e projetar a decisão de revisão necessária em API/UI e exportação;
   tornar ambos os valores navegáveis e preservar histórico/reanálises.
4. Versionar assinaturas afetadas, documentar comportamento e executar regressões.

**Prompt para uma sessão limpa:**

```text
Execute E11 — Revisões técnicas e conteúdo vigente de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, roadmap, diagnóstico e handoff E10, adapters/analysis/pymupdf_ocr.py e pymupdf_page_extractors.py, application/document_zones.py, human_review.py, automatic_promotion.py, review_api.py e git status. Confirme E10 concluída, política definida e código sem divergência não tratada. Preserve mudanças existentes e marque E11 #em-andamento no índice e detalhe. Implemente evidência da revisão técnica sobreposta e tratamento explícito do conflito ABCN base/revisado, com proveniência e revisão humana quando necessário; comentários comuns não viram ativos. Atualize persistência/DTO/UI somente conforme a política E10, mantendo histórico e compatibilidade. Crie fixtures sintéticas de sobreposição, comentários, fotos, carimbo e SHX; atualize versões, documentação e execute validações E11. Não reescreva o PDF. Só marque #concluida após aceite e todos os testes obrigatórios aprovados; não declare sucesso com testes falhando ou não executados. Use #bloqueada apenas para impedimento real, documentando causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, migração se necessária, comandos e resultados. Não faça commit nem publicação. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] D01 apresenta os valores base e visível com origem; não confirma o antigo silenciosamente.
- [x] Decisão técnica persiste e sobrevive à reanálise; comentários/fotos/carimbo não criam ativos.
- [x] SHX continua recuperável e cache antigo não oculta a mudança.

**Validação obrigatória:** `python -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_rule_based_interpreter.py tests/unit/test_analysis_cache.py tests/integration/test_human_review.py tests/server/test_review_api.py tests/server/test_deliverable_exports.py`.
Acrescentar novas regressões sintéticas e teste da UI alterada; descobrir seu comando
nos testes existentes do painel antes de editar. Repetir D01 sobre a fonte real.
**Migração/rollback:** se o contrato mudar, evolução aditiva com campos antigos
legíveis e decisão ausente como não resolvida; sem backfill de autoridade. Incrementar
compatibilidade se necessário; documentar retorno de versão sem perder decisões.
**Bloqueios:** nenhum impedimento remanescente de E11; política E10 conferida e aplicada.
**Riscos e mitigação:** sobreposição mal classificada gerar ativo; revisão explícita,
negativos e rastreabilidade. Não usar a anotação como instrução executável.
**Evidências e handoff — 14/09/2026:**

- Base `c85bebe`, Git inicialmente limpo e nenhum `AGENTS.md` aplicável. E10 concluída
  e política conferida; divergências encontradas no texto nativo do PyMuPDF e nas
  constantes de compatibilidade dos scripts de release foram tratadas. E08/E09 preservadas.
- `pymupdf_revisions.py` registra base/aparência, máscara, página, xrefs, hashes e
  grupo estável. `technical_revisions.py`, intérprete/promoção e `human_review.py`
  exigem escolha rastreável e preservam identidade, histórico e decisões na reanálise.
  `review_api.py`, contratos, painel e exportação apresentam conflito/decisão/efetivo.
- Fixtures sintéticas em `tests/pdf_fixtures.py` e regressões de análise, revisão,
  HTTP/Qt/XLSX cobrem comentários, fotos, carimbo, assinatura, Ink, SHX e rotações.
  Extrator 1.15.0, interpretador 23.0 e API/piso 1.5.0; OpenAPI atualizado.
  Persistência aditiva nos payloads JSON existentes, sem migração SQL ou backfill.
- D01 real conferido: `ABCN-35(70)` base, `ABCN-16(16)` visível, zero promoção
  conflitante. Dois grupos pendentes; N4 referencia as representações 138/146.
  Benchmark: 2.047 evidências, 38 propostas, 9 confirmações e 7 vãos; fonte com
  hash/tamanho/mtime preservados. Sem decisão técnica tomada sobre o PDF privado.
- `.\IniciarTestes.bat`: saída zero, **1.265 testes aprovados**, **87,78% de cobertura**;
  Ruff, Mypy, dependências, cliente magro e complexidade aprovados. Após ajuste
  final exclusivamente no texto de motivo obrigatório, 16 testes do painel,
  inspeção visual e Ruff aprovados. Todos os módulos obrigatórios E11 passaram.
- Comandos, resultados, falhas intermediárias resolvidas, arquivos privados ignorados,
  compatibilidade/rollback e limites em [e11-revisoes-tecnicas.md](e11-revisoes-tecnicas.md).
  Catalogação de ABCN revisado e operações N4 seguem E12/E13; não houve aceite
  integral E15, commit, publicação ou reescrita do PDF.

## E12 — Precisão dos extratores atuais — #concluida

**Objetivo:** recuperar os tokens técnicos do inventário com geometria, cor e risco
preservados, aprimorando os algoritmos atuais sem limitar a duração da análise.
Esta etapa mede a frente vertical; perdas que exigem método diferente passam
explicitamente a E12A/E12B, sem serem declaradas resolvidas.
**Por que agora:** E11 define quais camadas podem fornecer evidência técnica vigente.
**Dependências e paralelismo:** E10/E11; conflita com qualquer edição paralela nos extratores.
**Escopo:** `adapters/analysis/pymupdf_glyph_ocr.py`, `pymupdf_ocr.py`,
`pymupdf_ocr_batch.py`, `pymupdf_symbols.py`, `tesseract_ocr.py`, cache e benchmark.
**Fora de escopo:** promover ativos para elevar contagens, escolher catálogo ou conectar pontos.

**Passos de implementação:**

1. Reproduzir perdas E10 em fixtures, incluindo N4 verde/vermelho, rótulos inclinados,
   códigos CA/CAA, medidas, quadros e objetos sobrepostos. Conservar cor/risco como
   evidência por ocorrência, sem propagar a situação a elementos vizinhos.
2. Corrigir segmentação/recortes e reconciliação das leituras; código incerto não
   deve ser completado usando o catálogo. TR-3-45 já extraído segue para E13.
3. Explorar resolução, múltiplas passagens, orientação e recortes adicionais quando
   melhorarem a qualidade. Agrupar trabalho somente sem perda de evidências;
   preservar cancelamento, cobertura parcial explícita e memória controlada.
   Ajustar timeouts que interrompam trabalho saudável, sem criar teto global.
4. Versionar cache/extrator, medir novamente e documentar ganhos/perdas por item.

**Prompt para uma sessão limpa:**

```text
Execute E12 — Precisão dos extratores atuais de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, roadmap, diagnóstico, handoffs E10/E11, adapters/analysis/pymupdf_glyph_ocr.py, pymupdf_ocr.py, pymupdf_ocr_batch.py, pymupdf_symbols.py, tesseract_ocr.py, testes de extração/cache e git status. Confirme E10/E11 concluídas e verifique divergências do código. Preserve mudanças preexistentes e marque E12 #em-andamento no índice e detalhe. Corrija somente perdas de tokens/geometria/cor/risco demonstradas no inventário, mantendo situações separadas e códigos literais; não implemente catálogo ou associação. Priorize qualidade: permita mais resolução e passagens, não use tempo como limite ou aceite e ajuste timeouts para execução longa saudável. Preserve memória, diagnóstico e cancelamento. Compare o baseline com as melhorias verticais e entregue perdas remanescentes à experimentação E12A, sem alegar que foram resolvidas. Crie regressões sintéticas positivas e negativas, atualize versões/cache/documentação e execute validações E12 com benchmark real isolado. Só marque #concluida com correções verticais previstas e validações aprovadas; registre explicitamente lacunas para E12A/E12B, sem alterar o denominador global; não declare sucesso com testes falhando ou não executados. Se houver impedimento real, use #bloqueada e registre causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos, tempos, memória e tokens remanescentes. Não faça commit nem ação externa. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Casos atribuídos às correções verticais têm evidência correta e navegável;
      baseline/melhorias são comparados e perdas para métodos alternativos ficam listadas.
- [x] Leituras parciais/ambíguas são explícitas; controles não criam texto técnico falso.
- [x] Cancelamento, memória e cache mantêm os contratos em análise longa; tempo não reprova.

**Validação obrigatória:** `python -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_pymupdf_ocr_failures.py tests/unit/test_pymupdf_ocr_batch.py tests/unit/test_tesseract_ocr.py tests/unit/test_analysis_cache.py tests/integration/test_document_analysis.py tests/unit/test_benchmark_network_pdf.py`.
Executar novas regressões e benchmark isolado E10; comparar inventário e inspecionar
as ROIs corrigidas. Registrar duração sem gate e conferir fonte intacta.
**Bloqueios:** nenhum impedimento remanescente ao aceite vertical E12. As perdas de leitura listadas no handoff seguem explicitamente para E12A/E12B; não foram declaradas resolvidas nem retiradas dos denominadores E10.
**Riscos e mitigação:** melhorar só os casos conhecidos; comparar por ocorrência e
reservar a avaliação final. Não truncar tentativas por velocidade.
**Evidências e handoff — 15/09/2026:** concluída sobre `66b6146`, Git inicialmente
limpo e sem `AGENTS.md` aplicável. E10/E11 e código conferidos. Relatório completo:
[e12-precisao-extratores.md](e12-precisao-extratores.md).

- Extrator **1.16.0**: leituras por cor/célula e risco no grupo N4, glifos longos,
  tentativas adicionais até 2400 DPI e lotes sucessivos, com RGB concluído liberado.
  Timeout Tesseract **900 s por chamada**, sem teto global; cache/cancelamento e
  diagnósticos preservados. Catálogo, associação e topologia não foram implementados.
- Baseline isolado **2.047/228 evidências/OCR**; final **2.065/246**. São **85/127**
  chamadas, todas concluídas, zero diagnósticos. As **38 propostas finais** mantêm
  códigos/situações/identificadores/qualificadores/comprimentos; permanecem **9
  confirmações e 7 vãos**. Dois grupos E11 estáveis e nenhuma promoção conflitante.
- Seis leituras coloridas exatas e respectivas ROIs inspecionadas, incluindo N4(1)
  verde e vermelho riscado. Leituras originais divergentes mantidas para revisão;
  decisão técnica ainda pendente. S3R inclinado tem geometria mais justa; dois
  campos documentais recuperam o literal completo, sem homologar suas projeções.
- OCR até regiões/vãos **129,464 → 119,290 s**; incluindo exportação **132,632 →
  121,711 s**. Pico Python **380,16 → 379,94 MiB**, Tesseract **217,22 MiB** e RSS
  agregado amostrado **482,82 → 484,08 MiB**. Telemetria, sem critério temporal.
  Fonte/hash/tamanho/mtime preservados; dados reais somente em `tmp/`, ignorados.
- **174 testes direcionados aprovados em 12,38 s** e auditoria real aprovada.
  Gate final `.\IniciarTestes.bat`: **1.282 testes em 433,48 s, cobertura 87,83%,
  saída zero**, com Ruff, Mypy, dependências, cliente magro e complexidade aprovados.
  A primeira variante perdeu 43 grupos por orçamento acumulado e foi reprovada;
  corrigida com memória por lote. A primeira execução do gate falhou no setup por
  permissão de `C:\tmp`; a repetição canônica autorizada passou. Nenhuma falha
  intermediária foi tratada como aceite.
- E12A recebe coordenadas/textos truncados, quadros e limites de segmentação;
  E12B recebe reconciliação original/tratada e geral/contornos, inclusive leituras
  erradas preservadas. E13/E14/E15 recebem catálogo, associação, topologia e
  projeções ainda incompletas. **139 registros, 29 ocorrências operacionais e 64
  itens documentais** preservados; leitura integral continua **0/1**. Famílias
  reservadas não usadas; E08/E09 mantidas. Sem commit ou ação externa.

## E12A — Experimentação de algoritmos alternativos — #concluida

**Objetivo:** executar uma comparação reproduzível com pelo menos duas abordagens
algoritmicamente distintas das atuais, identificando ganhos complementares e erros.
**Por que agora:** E10 fixa a referência, E11 trata revisões e E12 mede o limite da
melhoria vertical; trocar parâmetros do mesmo método já não basta para este aceite.
**Dependências e paralelismo:** E12; usar E10/E11 como insumos. Experimentos não
alteram a promoção de produção; executar medições separadamente para atribuir resultados.
**Escopo:** `src/zeny_project_handler/ports/analysis.py`, `ports/interpretation.py`,
adaptadores de análise/interpretação, `scripts/benchmark_network_pdf.py` e fixtures.
Protótipos em `scripts/experiments/`, entrada `scripts/benchmark_network_alternatives.py`
e testes em `tests/unit/test_network_alternatives.py`; runtime opcional isolado em `tmp/`.
**Fora de escopo:** listar alternativas sem executá-las, usar somente variações de
Tesseract, enviar PDFs a serviços externos ou promover saídas experimentais.

**Passos de implementação:**

1. Inspecionar as portas reais e definir matriz de candidatos: obrigatoriamente
   um reconhecedor local independente de Tesseract e uma abordagem diferente para
   associação e topologia, com segmentação adicional se necessária. Exemplos de famílias a investigar são
   reconhecimento visual de sequências, componentes/glifos vetoriais e associação
   global por grafo/restrições em vez de apenas decisões locais por proximidade.
   Confirmar capacidades na documentação primária durante a execução; nomes de
   ferramentas, licenças, modelos e requisitos de hardware ainda são decisões abertas.
2. Implementar protótipos isolados, com dependências/modelos versionados e execução
   local, preservando código literal, coordenadas e origem. Transformar resposta
   sem evidência localizável em hipótese não confirmável, nunca fato técnico.
3. Rodar os candidatos e os baselines original/vertical sobre a mesma referência
   de desenvolvimento e controles sintéticos. Registrar precisão/recall por classe,
   código/situação exatos, endpoints, medidas, duplicatas e falhas correlacionadas.
   Manter os casos reservados sem ajustes; a avaliação final ocorre em E15.
4. Produzir matriz por ocorrência de acerto/erro exclusivo ou compartilhado. Escolher
   candidatos por ganho de qualidade, documentando os rejeitados e motivos; registrar
   tempo apenas como telemetria, mesmo acima de cinco minutos. Entregar os candidatos
   úteis para E12B/E13/E14, com protocolo reproduzível.

**Prompt para uma sessão limpa:**

```text
Execute E12A — Experimentação de algoritmos alternativos de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, roadmap e diretriz vigente, diagnóstico, handoffs E10/E11/E12, src/zeny_project_handler/ports/analysis.py, ports/interpretation.py, adaptadores, scripts/benchmark_network_pdf.py, fixtures e git status. Confirme E12 concluída, insumos disponíveis e ausência de divergência não tratada; preserve mudanças existentes e marque E12A #em-andamento no índice e detalhe. Implemente e execute pelo menos dois candidatos distintos: um reconhecedor local independente de Tesseract e um algoritmo alternativo de associação e topologia, com segmentação adicional se necessária. Mudança de parâmetros não conta. Investigue documentação primária, licença, hardware e modelos; não envie PDFs a serviços externos. Preserve evidência geométrica, mantenha experimentos fora da promoção de produção e compare original, vertical e alternativas na mesma referência de desenvolvimento com controles negativos. Registre métricas por item e erros correlacionados; reserve casos E10 sem ajustar neles. Escolha por confiabilidade, não por tempo; cinco minutos não é teto. Crie testes sintéticos, registre comandos reais dos novos adaptadores e execute validações E12A. Atualize documentação e Evidências e handoff com arquivos, versões, modelos, decisões, métricas, rejeições e candidatos para integração. Só use #concluida com comparação executada e validações aprovadas; não declare sucesso com testes falhando ou não executados. Se houver impedimento real, use #bloqueada com causa, evidência, impacto e desbloqueio. Não faça commit ou publicação. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Dois candidatos das famílias exigidas implementados e efetivamente executados.
- [x] Baselines e candidatos comparados por ocorrência com controles positivos/negativos.
- [x] Versões, dependências, comandos, erros complementares/correlacionados e decisões registrados.
- [x] Casos reservados preservados; nenhum candidato aceito por rapidez ou confiança autodeclarada.

**Validação obrigatória:** `python -m pytest tests/unit/test_benchmark_network_pdf.py tests/unit/test_pymupdf_analyzer.py tests/unit/test_rule_based_interpreter.py tests/unit/test_network_alternatives.py`.
Entradas e argumentos reais de cada candidato no [handoff E12A](e12a-algoritmos-alternativos.md).
Executar controles com os motores reais; mocks não validam capacidade. Repetir a comparação
local da referência E10 sem tocar a origem.
**Bloqueios:** nenhum impedimento remanescente da experimentação. A primeira instalação
foi impedida pela restrição de rede; o download autorizado passou. Regressões dos candidatos
impedem sua integração direta, mas foram medidas e não são declaradas resolvidas.
**Riscos e mitigação:** erros correlacionados parecerem consenso; registrar sua
distribuição. Sobreajuste ao PDF; separar casos reservados por documento/família.
**Evidências e handoff — 15/09/2026:** [e12a-algoritmos-alternativos.md](e12a-algoritmos-alternativos.md).

- Base `172afd5`, Git inicialmente limpo, nenhum `AGENTS.md` aplicável. E12 e insumos
  confirmados; diferenças históricas tratadas em E11/E12. Nenhuma mudança em `src/`.
- RapidOCR 1.4.4/ONNX Runtime 1.30.0, modelos PP-OCRv4 locais com hashes registrados,
  segmentação DB em 24 tiles, duas camadas e polígonos preservados. Grafo de extremidades
  com atribuição global húngara e abstenção; solver confere com SciPy em 100 matrizes.
- Original 1.14/22.0 reexecutado de `c85bebe`; vertical 1.16/23.0 reexecutado. Núcleo:
  original/vertical **24 TP, 5 FN, 4 FP**; neural com interpretador atual **7/22/8**;
  grafo sobre vertical **18/11/3**. Os **139 registros** e denominadores E10 preservados.
- Neural recupera uma coordenada documental integral inspecionada: candidato auxiliar
  para E12B, rejeitado como substituto geral. Grafo corrige três associações U1, mas
  regride em P3/traçados: rejeitado para integração direta, entregue como experimento E14.
  Matriz de erros exclusivos/compartilhados, duplicatas, endpoints e medidas registrada.
- Sete controles reais por motor: **6/7 literais corretos**; ambos erram o riscado,
  erro preservado na avaliação. Negativos da cerca não geram propostas. Erros conhecidos
  entre confirmações: original **2/10**, vertical **1/9**; candidatos não promovem.
- **106 testes aprovados em 11,49 s**; Ruff/formatação e Mypy (**346 arquivos**) aprovados;
  auditoria privada e `git diff --check` aprovados. Sem gate integral/UI/SQL nesta etapa.
  Fonte/hash/tamanho/mtime preservados, modelos e dados reais somente em `tmp/` ignorado.
- Casos reservados não usados. Leitura integral continua **0/1**, revisões técnicas
  pendentes e E08/E09 preservadas. Sem commit, publicação ou promoção de produção.

## E12B — Reconciliação e confiança entre métodos — #concluida

**Objetivo:** incorporar contribuições úteis das abordagens alternativas ao pipeline,
preservando divergências e impedindo confirmações automáticas sem sustentação.
**Por que agora:** múltiplas leituras só ajudam se a combinação não duplicar objetos
nem converter concordância frágil em certeza.
**Dependências e paralelismo:** E12A; receber matriz de erros e candidatos executados.
Implementação sequencial por alterar evidências consumidas por E13/E14.
**Escopo:** portas de análise/interpretação, adaptadores selecionados em E12A,
`application/document_analysis.py`, `interpretation_pipeline.py`,
`automatic_promotion.py`, cache, revisão e DTOs afetados. Novo módulo de reconciliação
é possibilidade de implementação, não arquivo existente confirmado.
**Fora de escopo:** votação cega, substituição automática pelo catálogo ou integração
de todos os candidatos sem benefício demonstrado.

**Passos de implementação:**

1. Associar hipóteses à mesma região/ocorrência e à mesma versão da camada técnica;
   guardar método, versão, geometria, leitura literal e transformação aplicada.
2. Integrar candidatos com ganho demonstrado como complemento, verificação ou
   substituição por classe. Comparar saída isolada e combinada; não fundir dois
   objetos físicos só porque seus códigos ou geometrias são parecidos.
3. Definir confirmação por evidência e erro observado na referência de desenvolvimento,
   sem comparar diretamente scores incompatíveis nem contar métodos correlacionados
   como votos independentes. Conflito relevante exige nova leitura ou revisão explícita.
4. Versionar composição, modelos e parâmetros no cache/assinaturas; permitir análises
   longas com progresso e cancelamento. Falha de um motor preserva resultados e informa
   verificação incompleta, sem parecer aprovação de todas as passagens.
5. Criar regressões de discordância, acordo errado, revisão sobreposta e método
   indisponível; documentar decisões e impacto em confirmações/revisão. Candidatos de
   associação/topologia ficam preparados para integração específica em E13/E14.

**Prompt para uma sessão limpa:**

```text
Execute E12B — Reconciliação e confiança entre métodos de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, roadmap/diretriz vigente, handoffs E10/E12A, portas de análise/interpretação, adaptadores selecionados, application/document_analysis.py, interpretation_pipeline.py, automatic_promotion.py, cache, revisão, DTOs e git status. Confirme E12A concluída com candidatos realmente executados e matriz de erros; confira divergências e preserve mudanças existentes. Marque E12B #em-andamento no índice e detalhe. Integre contribuições úteis com identidade por ocorrência/camada, proveniência e resolução explícita de discordâncias. Não use votação cega, scores de motores como probabilidades comparáveis ou catálogo para completar leitura incerta. Meça erro entre confirmações, cobertura e revisão, preserve os casos reservados e prepare contribuições de associação/topologia para E13/E14. Não escolha por tempo; mantenha memória, progresso, cancelamento e falhas parciais explícitas em análise longa. Versione métodos/modelos/composição no cache, atualize documentação e crie testes de acordo errado, conflito, revisão e motor indisponível. Execute validações E12B e registre contribuição de cada método. Se nenhum candidato melhorar a leitura, registre o resultado negativo e amplie E12A com outra família antes de declarar a integração concluída; não force um método pior. Só marque #concluida após aceite e testes aprovados; não declare sucesso com validação falhando ou não executada. Diante de impedimento real, use #bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos, métricas e mudanças de contrato. Não faça commit nem publique. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Alternativa com ganho demonstrado incorporada como leitura, verificação ou
      associação; contribuição medida desligando cada método separadamente.
- [x] Conflitos, acordos errados e falhas de motor não geram confirmação silenciosa.
- [x] Proveniência, decisões humanas, cache e identidade sobrevivem à reanálise.
- [x] Qualidade e cobertura melhoram sem esconder erro com abstenção generalizada;
      integração não regride os controles previamente corretos.

**Validação obrigatória:** `python -m pytest tests/unit/test_analysis_cache.py tests/unit/test_benchmark_network_pdf.py tests/integration/test_document_analysis.py tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py tests/server/test_review_api.py` e testes sintéticos de reconciliação adicionados. Rodar benchmark com motores reais e comparar cada contribuição habilitada/desabilitada. Registrar comandos novos no handoff; executar análise acima de cinco minutos com duração simulada no teste de job/cancelamento, localizando antes o teste existente correspondente. Nenhum corte temporal pode apresentar leitura integral sem completar as verificações.
**Migração/rollback:** versionar composição e eventual contrato aditivo, preservar
snapshots anteriores; voltar à composição anterior não apaga evidências/decisões
novas nem reaproveita cache incompatível. Documentar alterações de persistência se houver.
**Bloqueios:** nenhum bloqueio confirmado. Candidatos sem ganho exigem novas
experiências; resultado negativo não autoriza integração artificial ou aceite integral.
**Riscos e mitigação:** combinar leituras aumentar falsos positivos; validar por item
e medir confirmações erradas. Confiança mal calibrada; usar erro observado, não score bruto.
**Evidências e handoff — 15/09/2026:** [e12b-reconciliacao-metodos.md](e12b-reconciliacao-metodos.md).
Base `67a5457`, Git inicialmente limpo e E12A revalidada. Extrator 1.17.0 e composição
`documentary-coordinate-review-1`: proveniência por observação/camada, cache com modelos,
confirmação vedada por acordo e conflitos ligados às evidências exatas da proposta.
Motor opcional no servidor, aba/DTO/XLSX de leituras auxiliares; falhas e cancelamentos
persistem evidência parcial sem sucesso/cache. Três composições reais executadas:
vertical e combinação mantêm 24 TP/5 FN/4 FP, nove confirmações, erro conhecido 1/9
e revisão do núcleo 19/29; neural recupera um literal documental adicional sem promover
ativos. 328 observações preservadas, 29 selecionadas para conferência; não equivalem
a 29 novos objetos. A ablação sem Tesseract conserva o ganho documental, mas perde
a leitura operacional; substituição geral continua rejeitada. **167 testes aprovados**,
Mypy em 347 arquivos, Ruff/formatação, contratos, complexidade e fonte do cliente aprovados.
139 referências preservadas; casos reservados intocados. Grafo e pendências operacionais
seguem para E13/E14; leitura integral permanece 0/1 e gate integral reservado a E15.
Não houve commit, publicação ou instalação no servidor operacional.

## E13 — Ocorrências e associação aos pontos corretos — #concluida

**Objetivo:** interpretar códigos/situações e associar cada ocorrência ao ponto físico
correto, evitando o neutro duplicado e a transferência de ativos existentes para P5.
**Por que agora:** E12B entrega evidências reconciliadas entre métodos.
**Dependências e paralelismo:** E12B; conferir eventuais correções novas de E08/E09.
Não editar intérprete/promoção simultaneamente com outra etapa.
**Escopo:** `adapters/interpretation/category_analyzers.py`, `operational_labels.py`,
`rule_based.py`, `relation_rules.py`, `application/automatic_promotion.py`,
`analysis_regions.py` e catálogo/regras existentes.
**Fora de escopo:** inventar modelos de poste, expandir qualificadores em quantidade,
renumerar pontos existentes ou resolver a projeção de vãos nesta etapa.

**Passos de implementação:**

1. Reproduzir D02–D05 em fixtures: mesmo neutro lido duas vezes versus dois cabos
   distintos, dois N3 físicos, ponto existente sem P, N4 instalado/removido e TR-3-45.
2. Comparar a associação atual com o candidato alternativo de E12A, reutilizando
   a reconciliação de E12B; escolher por erros demonstrados e não por velocidade.
   Deduplicar apenas leituras da mesma ocorrência. Ancorar ativos no ponto e na
   geometria sustentados pela fonte, sem anexar ao único P próximo por conveniência.
3. Normalizar TR-3-45 sem escolher equipamento arbitrário; preservar código e
   capacidade observados quando o catálogo não puder resolver o modelo.
4. Preservar ambas as situações de N4 e relações válidas; manter casos incertos
   revisáveis, com motivo específico. Versionar interpretação e conferir reanálise.

**Prompt para uma sessão limpa:**

```text
Execute E13 — Ocorrências e associação aos pontos corretos de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, roadmap, diagnóstico D02–D05, handoffs E12A/E12B, ADR 0015, category_analyzers.py, operational_labels.py, rule_based.py, relation_rules.py, automatic_promotion.py, analysis_regions.py e git status. Confirme E12B concluída, confira mudanças posteriores de E08/E09 e divergências do código; preserve alterações preexistentes. Marque E13 #em-andamento no índice e detalhe. Corrija o neutro repetido em V2-3 sem fundir cabos distintos, preserve N3 repetidos físicos e N4 instalar/remover, represente TR-3-45 com evidência e vincule o ponto existente de 36 m ao seu próprio contexto sem atribuí-lo a P5. Compare a associação atual e a alternativa E12A por precisão, preservando conflitos conforme E12B. Não invente modelos, códigos ou pontos por proximidade. Implemente regressões sintéticas e revisão/identidades preservadas, atualize versão e documentação e execute validações E13. Só marque #concluida com todos os critérios e testes obrigatórios aprovados; não declare sucesso se falharem ou não rodarem. Em impedimento real, use #bloqueada com causa, evidência, impacto e ação de desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos e reconciliação por ocorrência. Não faça commit nem publique. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] D02–D05 resolvidos por evidência, sem falsos vínculos nem omissões de ocorrências.
- [x] TR-3-45 fica representado com código literal; catálogo não resolvido é explícito.
- [x] Reanálise não duplica e não transfere decisões humanas para outro ativo.

**Validação obrigatória:** `python -m pytest tests/unit/test_rule_based_interpreter.py tests/unit/test_e08_association.py tests/unit/test_analysis_regions.py tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py tests/server/test_review_api.py`.
Adicionar regressões positivas/negativas; repetir benchmark com auditoria E10 das
propostas, promoções e geometrias, incluindo todos os equipamentos.
**Bloqueios:** nenhum bloqueio conhecido; classificação sem evidência deve ser
registrada como ambiguidade técnica, não preenchida para passar o teste.
**Riscos e mitigação:** fundir ocorrências iguais em locais diferentes; validar identidade
e posição. Catálogo insuficiente; preservar proposta literal e candidatos sem promoção falsa.
**Evidências e handoff — 16/09/2026:** [e13-ocorrencias-associacao.md](e13-ocorrencias-associacao.md).
Base `f990c1b`, Git inicialmente limpo; E12B confirmada e E08/E09 preservadas.
Interpretador 24.0: neutro V2-3 consolidado por rótulo/traçado/situação, dois N3 físicos
preservados, contexto existente separado de P5, TR-3-45 e N-4 literais sem modelo
inventado, N4 base/instalar/remover com autoridade pendente e identidades próprias.
**147 testes aprovados**, Mypy em 348 arquivos, Ruff/formatação, complexidade e
`git diff --check` aprovados. Benchmark real: 43 propostas, oito confirmações,
47 relações, 13 regiões, seis vãos e zero diagnósticos; fonte e exportações verificadas.
Auditoria preserva 139 referências e inspeciona nove equipamentos. Núcleo: 29 TP,
zero FN/FP, contra 24/5/4 no baseline; grafo E12A sobre E13: 20/9/2, rejeitado para
integração por perdas em P3/cabos. Nenhuma confirmação duplicada conhecida (0/8);
isso não homologa topologia, classificação ou leitura integral. Q3 fica visível com
associação pendente; revisões técnicas e modelos incertos exigem decisão humana.
E14/E15 recebem essas limitações conforme handoff. Sem commit ou publicação.

## E14 — Topologia e projeção dos trechos — #concluida

**Objetivo:** representar conectividade coerente, medidas e rede existente/novas ligações
na projeção de vãos, distinguindo trecho físico e cabo.
**Por que agora:** a topologia depende das ocorrências e dos pontos corrigidos em E13.
**Dependências e paralelismo:** E13; coordenar alterações de `span_rules.py`/`spans.py`
com retomadas de E08. Não depende de declarar a homologação do outro PDF concluída.
**Escopo:** `adapters/interpretation/span_rules.py`, `application/spans.py`,
`automatic_promotion.py`, `src/zeny_project_handler_server/review_api.py`,
`deliverable_exports.py`, domínio e codecs correspondentes se necessários.
**Fora de escopo:** ligar vizinhos sem traçado ou concluir padrão/ramal apenas pela casa desenhada.

**Passos de implementação:**

1. Rastrear por que cabos existentes de 36/83 m não geram linhas em Vãos; diferenciar
   regra de apresentação documentada de omissão e tornar os trechos navegáveis.
2. Avaliar hipóteses de conectividade com o método alternativo de E12A frente à
   associação atual, usando restrições geométricas e evidência de continuidade.
   Resolver identidade de endpoints compartilhados por fase/neutro a partir do
   ponto físico; não criar continuidade só porque os comprimentos coincidem.
3. Representar 14/100/80/57/36/83 m nos trechos correspondentes; distinguir cabo,
   trecho, tipo topológico e modalidade. Para P4, seguir evidência e ADR 0015.
4. Sincronizar projeções HTTP/XLSX/UI afetadas, revisão e versões; documentar
   incertezas reais e a unidade de contagem na tabela Vãos.

**Prompt para uma sessão limpa:**

```text
Execute E14 — Topologia e projeção dos trechos de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, roadmap, diagnóstico D06, handoffs E10/E13, ADR 0015, span_rules.py, application/spans.py, automatic_promotion.py, review_api.py, deliverable_exports.py e git status. Confirme E13 concluída, confira divergências e alterações de E08; preserve mudanças preexistentes e marque E14 #em-andamento no índice e detalhe. Compare o método atual e o candidato alternativo de E12A por conectividade exata, sem ranking por tempo. Corrija projeção dos trechos existentes de 36/83 m, conectividade dos pontos compartilhados e correspondência dos trechos de 14/100/80/57 m, distinguindo cabo e trecho físico. Preserve tipo/modalidade desconhecidos quando faltar evidência; não invente padrão ou rede por proximidade. Atualize contratos/projeções/codecs somente se necessário, com compatibilidade documentada, e preserve revisão humana. Crie regressões sintéticas, execute validações E14 e auditoria E10, atualize documentação. Só marque #concluida com todos os critérios e testes aprovados; não declare sucesso com testes falhando ou não executados. Em impedimento real, use #bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos e mapa de endpoints/trechos. Não faça commit ou publicação. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] Trechos inequívocos do inventário têm endpoints/medidas corretos e projeção navegável.
- [x] Fase/neutro mantêm identidade física coerente, sem vãos ou ativos duplicados.
- [x] Tipo/modalidade têm evidência ou motivo de indeterminação; HTTP/UI/XLSX concordam.

**Validação obrigatória:** `python -m pytest tests/unit/test_spans.py tests/unit/test_topology_path_compliance.py tests/unit/test_e08_association.py tests/integration/test_interpretation_pipeline.py tests/server/test_review_api.py tests/server/test_deliverable_exports.py tests/e2e/test_span_compliance_ui.py`.
Executar novos casos de conectividade e comparar cada trecho E10 até XLSX; navegar
um caso de cada situação/tipo e conferir a geometria no PDF.
**Migração/rollback:** mudança de identidade ou contrato exige compatibilidade explícita,
sem reescrita de snapshots; preservar sessões antigas e reconciliar novas propostas.
Se novos campos forem necessários, documentar valores ausentes e leitura da versão anterior.
**Bloqueios:** nenhum bloqueio conhecido.
**Riscos e mitigação:** gráficos desconectados por UUIDs por cabo; testar continuidade
real e circuitos próximos sem conexão. Não relaxar ADR para aumentar contagens.
**Evidências e handoff:** concluída em 16/09/2026 sobre `af8ead2`, Git inicialmente
limpo. E13 integrada, sem AGENTS.md aplicável; divergências E11–E13 conferidas,
correções e bloqueios E08/E09 preservados. Ver
[e14-topologia-projecao-trechos.md](e14-topologia-projecao-trechos.md).

Interpretador 25.0/API e piso 1.6.0: existentes 36/83 m visíveis, V3-4 orientado
corretamente, pontos elétricos compartilhados somente em configuração compatível;
projeção física separa dez traçados de seus condutores. Nove pontos físicos, sete
pares visíveis, três continuidades na borda explícita e seis medidas corretas;
quatro medidas continuam ausentes. Tipo/modalidade e decisões técnicas incertas
permanecem pendentes. HTTP/Qt/XLSX coerentes; nenhum ativo criado por proximidade.
Compatibilidade coordenada por DTOs estritos; sem codec/migração/backfill ou
reescrita de snapshots. Guarda de reconciliação de reanálise preservada.

**162 testes ampliados aprovados**, incluindo os sete arquivos obrigatórios;
**76 de contratos/handshake/fronteira/regressões** e **51 de navegação/topologia**
aprovados (rodadas com sobreposição). Mypy em 352 arquivos, Ruff/formatação,
complexidade em 2.856 funções/métodos e `git diff --check` aprovados.
Benchmark OCR final: 43 propostas, oito confirmações, dez pontos elétricos, oito
linhas de Vãos, dez trechos físicos e zero diagnósticos; fonte/hash/mtime e XLSX
conferidos. Auditoria preserva 139 referências E10 e núcleo E13 29/29, com mapa
individual até XLSX e navegação real 10/10. Comparação estrita: E14 7/7 pares
completos contra 1/7 do grafo E12A; sem ranking por duração. Grafo não integrado.
E15 recebe o gate integral/cobertura, classificação, autoridade, documentação,
equipamentos e reservas; E08/E09 não foram re-homologadas. Sem commit/publicação.

## E15A — Consolidação documental e vigência por campo — #pendente

**Objetivo:** representar os 64 itens documentais E10, com valor, fonte/camada,
presença/vazio, limitação e decisão explícitos nos DTOs, painéis e XLSX.
**Por que agora:** o aceite E15 reproduziu 11 itens duplicados, oito com valor
errado entre as alternativas, 36 sem campo individual e um apenas auxiliar.
São perdas próprias do processamento documental, além da exportação de estruturas.
**Dependências e paralelismo:** E11, E12B, E14 concluídas; não editar projeções
simultaneamente com E15. A auditoria E15 é insumo, não dependência de seu aceite.
**Escopo:** `application/project_compliance.py`, `document_compliance.py`,
`document_zones.py`, `coordinate_pairs.py`, revisão documental, contratos,
`compliance_api.py`, `documentation_panel.py`, `deliverable_exports.py`.
**Fora de escopo:** autenticar assinaturas/fotos, consultar SQL operacional,
aprovar revisões pela data/cor ou alterar o inventário para acomodar perdas.

**Passos de implementação:**

1. Reproduzir em fixtures próprias campos truncados, duplicados e contraditórios,
   coordenadas fragmentadas, tabelas/valores vazios e presença em aparências.
2. Consolidar por identidade de campo/camada, conservando leituras concorrentes.
   Valor conflitante não pode continuar `IDENTIFICADO` sem pendência específica.
3. Representar notas, CHI, regulador, fotos/assinaturas e demais itens com suporte
   ou limitação individual navegável; incluir decisão de vigência por campo.
4. Validar persistência/reabertura, concorrência, reanálise e HTTP/Qt/XLSX com OCR
   real e SQL fake. Não usar reservas expostas para calibrar e depois medir ganho.

**Prompt para uma sessão limpa:**

```text
Execute E15A — Consolidação documental e vigência por campo de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, README, E10, handoffs E11/E12B/E14/E15, diagnóstico, código e testes documentais e git status. Confirme dependências concluídas e coerentes; preserve alterações existentes e marque E15A #em-andamento no índice e detalhe. Corrija consolidação/representação dos 64 itens documentais E10 com fonte e camada, valores exatos, vazios e limitações individuais navegáveis; preserve alternativas e não confirme conflito ou revisão por confiança do OCR. Não autentique fotos/assinaturas nem consulte SQL operacional. Use fixtures novas de desenvolvimento, OCR real no PDF privado e SQL fake; valide HTTP/Qt/XLSX, revisão, reabertura e reanálise. Não reduza denominadores nem use famílias reservadas já expostas como avaliação cega. Subdivida classes independentes antes de ampliar implementação. Execute validações obrigatórias e registre métricas/evidências/handoff. Só marque #concluida com todos os critérios aprovados; em impedimento real use #bloqueada com causa, evidência, impacto e desbloqueio. Preserve E08/E09 e originais. Não faça commit, release ou publicação. Termine com resumo conciso.
```

**Critérios de aceite:**

- [ ] 64/64 itens têm representação ou limitação explícita individual até XLSX.
- [ ] Nenhum valor errado/duplicado é exibido como campo consolidado correto.
- [ ] Camada/autoridade e decisões sobrevivem a reabertura/reanálise sem transferência.
- [ ] Testes documentais/API/Qt/exportação e gate público aprovados.

**Validação obrigatória:** `python -m pytest tests/unit/test_document_compliance.py
tests/server/test_compliance_api.py tests/server/test_deliverable_exports.py
tests/integration/test_review_panel.py tests/e2e/test_mvp_ui.py`; localizar os testes
de `project_compliance` antes de ampliar a lista. Executar `IniciarTestes.bat` e
auditoria dos 64 itens E10 com fonte/hash preservados, sem gate de duração.
**Bloqueios:** nenhum impedimento de início conhecido; os defeitos acima motivam a etapa.
**Riscos e mitigação:** consolidar variantes apagando conflito; manter proveniência
e regressões negativas. Acrescentar dados em DTO estrito exige compatibilidade explícita.
**Evidências e handoff:** criada durante E15 em 16/09/2026, antes de ampliar a
implementação documental; ver `tmp/rede-1256407599/e15/audit.json` e handoff E15.

## E15B — Classificação e cobertura automática comprovada — #pendente

**Objetivo:** resolver a primeira perda de classificação/promoção por ocorrência
e comprovar as metas automáticas E10 sem fabricar modelos ou autoridade.
**Por que agora:** as propostas acertam 29/29, mas somente oito cabos estão
confirmados; 21/29 itens do núcleo ainda exigem revisão (meta máxima 5%).
**Dependências e paralelismo:** E13/E14 concluídas; independente da consolidação
documental, mas evitar alterações simultâneas em revisão e projeções com E15A.
**Escopo:** catálogo/regras existentes, `automatic_promotion.py`, intérprete,
classificação de pontos/tipo/modalidade, revisão humana e testes associados.
**Fora de escopo:** inventar material/formato de poste, CA/CAA, classe de símbolo,
tipo de entrega, quantidade por qualificador ou aprovação de camada.

**Passos de implementação:**

1. Auditar as 21 pendências do núcleo e os estratos de equipamentos/símbolos;
   separar defeito corrigível de insuficiência real de fonte sem remover referências.
2. Implementar somente resolução sustentada por evidência e catálogo verificado;
   manter abstenção/revisão motivadas quando não houver decisão técnica autorizada.
3. Medir código/situação/localização, classificação completa, FP/FN, confirmações
   erradas e revisão por categoria. Congelar métodos antes de nova avaliação reservada.
4. Se a fonte não sustentar ≥95% global/≥90% por classe e revisão ≤5%, registrar
   incompatibilidade demonstrada e ação necessária; não baixar metas unilateralmente.

**Prompt para uma sessão limpa:**

```text
Execute E15B — Classificação e cobertura automática comprovada de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, README, E10/E13/E14/E15, ADR 0015, catálogo, promoção, revisão, testes e git status. Confirme dependências concluídas e código coerente; preserve alterações e marque E15B #em-andamento no índice e detalhe. Audite as 21 pendências do núcleo e equipamentos/símbolos sem retirar itens da referência. Corrija apenas resoluções sustentadas por fonte/catálogo, preservando abstenção, identidade e decisões humanas. Não invente modelos, modalidade, padrão ou autoridade, nem promova por consenso OCR. Meça cobertura automática completa ≥95% global e ≥90% por categoria, revisão ≤5% e zero confirmações erradas; se a fonte não permitir as metas, documente o impedimento sem relaxá-las. Use testes sintéticos novos e OCR real/SQL fake; preserve reservas expostas e congele novos métodos antes de medir generalização. Subdivida perdas independentes antes de ampliar implementação. Execute testes obrigatórios, benchmark/auditoria E10 e IniciarTestes.bat. Só conclua com toda validação aprovada; use #bloqueada em impedimento real com causa/evidência/impacto/desbloqueio. Preencha Evidências e handoff. Preserve E08/E09 e PDFs privados; não faça commit, release ou publicação. Termine com resumo conciso.
```

**Critérios de aceite:**

- [ ] Todas as pendências têm primeira perda e fonte/decisão rastreáveis.
- [ ] Metas E10 de confirmação/revisão por categoria cumpridas sem erros conhecidos.
- [ ] Tipo/modalidade/modelos exigidos têm evidência, sem transferência de decisão.
- [ ] Reanálise/reabertura/API/XLSX e gate público aprovados.

**Validação obrigatória:** `python -m pytest tests/unit/test_e13_occurrences.py
tests/unit/test_e14_topology.py tests/unit/test_rule_based_interpreter.py
tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py
tests/server/test_review_api.py tests/server/test_deliverable_exports.py`; benchmark
OCR E10 por ocorrência e `IniciarTestes.bat`, sem teto temporal.
**Bloqueios:** nenhum impedimento de início; suficiência da fonte deve ser demonstrada
antes de prometer automação, com decisão do responsável quando faltar dado técnico.
**Riscos e mitigação:** esconder omissões como revisão ou promover catálogo ambíguo;
manter denominadores E10, medir erro das confirmações e abstenção separadamente.
**Evidências e handoff:** criada em E15 em 16/09/2026 antes de ampliar classificação;
os oito confirmados são cabos, nenhum poste/MT/BT confirmado. Ver handoff E15.

## E15C — Identidade de ocorrências entre páginas — #pendente

**Objetivo:** preservar cada ocorrência física de páginas distintas, inclusive
mesmo identificador/código/posição em páginas nativas, rasterizadas e rotacionadas.
**Dependências:** E13 concluída. Executar sem alterações simultâneas em deduplicação.
**Escopo:** identidade, agrupamento, associação e projeção por página; não completar
OCR ausente por cópia de outra folha. Fora de escopo: catálogo e vigência documental.

**Passos:** localizar a primeira fusão entre nove propostas brutas e três finais
em H01; criar fixtures novas de desenvolvimento; corrigir a identidade com página;
validar persistência, revisão, HTTP/Qt/XLSX e reanálise. Congelar a composição antes
de novas reservas; sementes 910101–910103 já estão expostas.

**Prompt para uma sessão limpa:**

```text
Execute E15C de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, README, E10/E13/E15, pipeline, identidade/deduplicação, testes e git status. Confira dependências e preserve mudanças; marque índice/detalhe #em-andamento. Investigue a fusão entre páginas observada em H01, sem retirar omissões do inventário. Corrija com fixtures novas e sem completar textos ausentes por cópia. Valide páginas nativas/raster/rotacionadas, revisão humana, reabertura, reanálise, HTTP/Qt/XLSX, OCR real e SQL fake. Congele antes de novas reservas. Subdivida outras perdas antes de ampliar implementação. Execute testes, benchmark e IniciarTestes.bat. Só conclua com critérios aprovados; bloqueio exige causa/evidência/impacto/desbloqueio e handoff. Preserve E08/E09/PDFs; não faça commit, release ou publicação.
```

**Critérios e validação obrigatória:**

- [ ] Nove ocorrências de cada caso H01 conservadas por página/código/situação/ROI,
      sem falsos positivos nem confirmação indevida; novas reservas separadas.
- [ ] Nenhuma decisão humana migra para ocorrência de outra folha.
- [ ] HTTP/Qt/XLSX, reanálise/reabertura e gate público aprovados; E10 sem regressão.

**Bloqueios:** nenhum de execução; E15 depende da resolução desta perda.
**Risco:** duplicar a mesma representação dentro de uma folha; manter esse controle.
**Evidências/handoff:** E15 mediu 9 TP/18 FN em 27 ocorrências H01, nos três métodos
com Tesseract. `reserved-metrics.json` preserva correspondências e páginas.

## E15D — Exclusão contextual de falsos ativos — #pendente

**Objetivo:** impedir que textos técnicos em tabela, carimbo, foto e cerca sejam
promovidos a ativos da rede sem contexto positivo de desenho.
**Dependências:** E13 concluída; separar alterações de promoção das de E15B.
**Escopo:** discriminação contextual e promoção; preservar os textos como evidência.
Fora de escopo: excluir documentação ou diminuir o denominador para melhorar números.

**Passos:** rastrear cabo confirmado sobre linha de tabela e transformador proposto
em H03; criar controles positivos e negativos novos; corrigir contexto sem apagar
evidências; medir FP, omissões, confirmações erradas e revisão por categoria.

**Prompt para uma sessão limpa:**

```text
Execute E15D de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, README, E10/E13/E15, contexto de extração/interpretação, promoção, testes e git status. Preserve alterações e marque índice/detalhe #em-andamento. Corrija falsos ativos de tabela/carimbo/foto/cerca com contexto positivo e controles sintéticos novos; preserve evidências documentais. Não transforme abstenção generalizada em qualidade nem ajuste às reservas H03 já expostas. Meça FP/FN/confirmações erradas/revisão, valide OCR real/SQL fake, HTTP/Qt/XLSX e persistência. Subdivida perdas independentes. Execute benchmark, testes e IniciarTestes.bat; conclua apenas com todos os critérios aprovados. Registre evidências, bloqueios e handoff. Preserve E08/E09/PDFs; não faça commit, release ou publicação.
```

**Critérios e validação obrigatória:**

- [ ] H03 não produz ativos de rede nem confirmações indevidas; controles positivos
      mantêm recall e campos corretos, incluindo novas reservas após congelamento.
- [ ] Todos os negativos continuam navegáveis como evidência, sem sumir do inventário.
- [ ] HTTP/Qt/XLSX, persistência, E10 e gate público aprovados.

**Bloqueios:** nenhum de execução. **Risco:** excluir cabos legítimos junto a quadros;
contrapor fixtures positivas e negativas. **Evidências/handoff:** E15 registrou seis
FP em três reservas H03, três confirmados erradamente, na composição atual.

## E15E — Topologia de circuitos cruzados — #pendente

**Objetivo:** representar dois circuitos cruzados com endpoints, nomes, comprimentos
e identidades distintos, sem inventar junção ou escolher camada por proximidade.
**Dependências:** E14 concluída; evitar alterações simultâneas em trechos com E15B/C.
**Escopo:** associação cabo/traçado/ponto/medida e sua projeção; comparação com grafo
independente. Fora de escopo: inventar autoridade técnica ou modalidade.

**Passos:** rastrear a fusão de dois cabos em um trecho P3–P2 no H02; comparar a
geometria correta do grafo com seus comprimentos errados; criar novos cruzamentos
de desenvolvimento; corrigir associação e validar revisão/cópia/decisão anterior.

**Prompt para uma sessão limpa:**

```text
Execute E15E de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, README, E10/E12A/E14/E15, ADR 0015, trechos, grafo experimental, testes e git status. Preserve alterações e marque índice/detalhe #em-andamento. Corrija associação em circuitos cruzados com fixtures novas; compare método atual e grafo por geometria/endpoints/nomes/medidas, nunca por tempo. Preserve revisão, cópia, decisão humana e incógnitas. Não una cabos distintos nem invente junção no cruzamento. Valide OCR real/SQL fake, HTTP/Qt/XLSX/reanálise/reabertura, E10 e novas reservas após congelamento. Subdivida novas perdas. Execute testes, benchmark e IniciarTestes.bat. Só conclua com todos os critérios aprovados; registre causa/evidência/impacto/desbloqueio se bloqueada e preencha handoff. Preserve E08/E09/PDFs; não faça commit, release ou publicação.
```

**Critérios e validação obrigatória:**

- [ ] Seis pares/medidas completos nos três H02, sem fusão de circuitos ou junção
      fictícia; revisão/cópia e rejeição anterior preservadas.
- [ ] Contribuição de cada método medida em novas reservas congeladas.
- [ ] HTTP/Qt/XLSX, reanálise/reabertura, E10 e gate público aprovados.

**Bloqueios:** nenhum de execução. **Risco:** ganhar geometria e errar nomes/medidas;
exigir acerto conjunto. **Evidências/handoff:** `reserved-topology.json`: produção
0/6 pares completos, três saídas incorretas; grafo 6/6 pares geométricos nomeados,
0/6 com medida correta. A aprovação restrita de E14 no PDF principal é preservada.

## E15 — Aceite integral do segundo PDF — #bloqueada

**Objetivo:** comprovar a referência integral através dos painéis, API, documentação
e exportações, e registrar com precisão o que o sistema consegue ler.
**Por que agora:** extração correta não garante interpretação, apresentação ou conteúdo vigente.
**Dependências e paralelismo:** E11/E12/E12A/E12B/E13/E14; validar uma única revisão estabilizada.
Dependências originais conferidas como concluídas. Retomada após E15A–E15E,
criadas pelas perdas reproduzidas neste aceite; elas não dependem de E15 concluída.
**Escopo:** pipeline servidor, inspeção documental em
`application/document_compliance.py`, `project_compliance.py`, `document_zones.py`,
revisão/API/cliente/exportação, `README.md`, diagnóstico e este roadmap.
**Fora de escopo:** publicar release, consultar SQL operacional ou certificar fotos/assinaturas.

**Passos de implementação:**

1. Repetir inventário completo, benchmark isolado e hash. Conferir D01–D06 e todos
   os itens E10, contabilizando perdas, falsos positivos e ambiguidades separadamente.
2. Conferir campos documentais suportados: NS, impacto, servidão, notas, tabelas e
   presença de fotos/assinaturas; campos não suportados devem ser explicitamente
   documentados. Verificar conflitos entre camada base e revisão também nesses campos.
3. Validar API/cliente, reabertura, revisão, reanálise/cache, cancelamento, zoom/rotação,
   realces e exportações. Usar SQL fake onde necessário. Corrigir regressões de
   integração com testes; se houver nova classe independente de perda, subdividir
   o trabalho no roadmap antes de implementar, mantendo o aceite pendente.
4. Comparar baseline, melhoria vertical, alternativas isoladas e combinação final
   nos casos reservados E10; desligar cada contribuição separadamente para medir
   seu efeito. Exigir evidência de ganho ou rejeição justificada de cada alternativa.
5. Executar gate público completo e atualizar documentação com resultados medidos,
   sem confundir execução bem-sucedida, ambiguidade técnica e leitura integral.

**Prompt para uma sessão limpa:**

```text
Execute E15 — Aceite integral do segundo PDF de docs/roadmap-mercado-paineis-leitura-rede.md. Leia AGENTS.md aplicáveis, roadmap, diagnóstico e handoffs E10–E14, README, testes do pipeline/API/UI/exportações e git status. Confirme E11/E12/E12A/E12B/E13/E14 concluídas e código coerente, preserve mudanças preexistentes e marque E15 #em-andamento no índice e detalhe. Audite toda a referência E10 do PDF 1256407599, incluindo D01–D06 e campos documentais, camadas revisadas, medidas, situações, pontos e topologia. Valide HTTP/cliente/Resultados/XLSX, reabertura, reanálise, cancelamento e realces com OCR real e SQL fake, sem consulta operacional. Compare baseline, melhoria vertical, alternativas isoladas e combinação final nos casos reservados E10; reporte falsos positivos, omissões, confirmações erradas e revisão, sem usar tempo como gate. Execute benchmark isolado, metas de qualidade E10 e IniciarTestes.bat; corrija regressões de integração com testes e documentação. Para nova classe independente de perda, subdivida o roadmap antes de ampliar implementação; não reduza inventário ou esconda omissões. Só marque #concluida após toda a definição de pronto e validações; não declare sucesso com testes falhando ou não executados. Se impedimento real impedir o aceite, use #bloqueada com causa, evidência, impacto e ação de desbloqueio. Preencha Evidências e handoff com arquivos, comandos, resultados, inspeções, métricas e ambiguidades remanescentes. Preserve estados de E08/E09 e PDFs privados. Não faça commit, release ou publicação. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [ ] Inventário inteiro reconciliado e D01–D06 resolvidos, com ambiguidades técnicas explícitas.
- [ ] Campos documentais suportados e fonte vigente conferidos nos painéis e exportações.
- [x] HTTP/Qt/XLSX, reanálise, cancelamento e inspeção visual passam na mesma revisão.
- [ ] Comparações e contribuição de cada método comprovadas em casos reservados,
      sem confirmações erradas conhecidas ou aumento oculto de revisão manual.
- [ ] Gate público aprovado, metas de qualidade E10 cumpridas, fonte preservada e
      documentação atualizada; tempo não constitui critério de reprovação.

**Validação obrigatória:** `.\IniciarTestes.bat` com saída zero e cobertura mínima
85,01%; benchmark OCR e auditoria integral E10; `python scripts/smoke_examples.py`
apenas como complemento. Usar testes existentes de `tests/server/` e `tests/e2e/`
para o fluxo real: localizar o teste de cada painel antes da execução e registrar
comandos efetivamente usados. Comparar snapshots/planilhas e inspecionar todos os
itens do inventário no PDF, sem elevar sucesso de smoke a homologação.
**Bloqueios:** causa: perdas documentais, classificação insuficiente e falhas nas
reservas. Evidência: dos 64 campos, 36 sem representação, 11 duplicados (oito com
valores errados); cobertura automática por campos no máximo 8/29 e revisão 21/29.
H01 perde 18/27 ocorrências; H03 confirma três falsos ativos; H02 erra seis pares
completos. Impacto: leitura exata e metas E10 reprovadas. Desbloqueio: executar
E15A–E15E, congelar nova composição, reservar casos novos e repetir o aceite.
**Riscos e mitigação:** aceitar números agregados; exigir correspondência por item.
PDF privado nunca se torna dependência do gate público; reservas expostas não
podem ser reapresentadas como cegas. E08/E09 permanecem com os mesmos estados.
**Evidências e handoff:** auditoria de 16/09/2026, transição #em-andamento → #bloqueada;
[relatório E15](e15-aceite-integral-segundo-pdf.md), 139 linhas em `audit.json`,
benchmarks isolados vertical/combinado/neural, inspeção integral da fonte,
reconciliação documental/topológica e 45 execuções nas nove reservas. Integração
real HTTP/Qt/XLSX, cache, reanálise, cancelamento e reabertura registrada em
`http-report.json`; rótulos/qualificadores em `final-projection.json`. Comandos,
resultados completos do gate, métricas e limites constam no handoff; nenhum
critério de qualidade foi relaxado. Correções limitadas em rótulo/exportação e
teste da ordem de abas; inferência não ampliada nesta etapa.
Gate final: **1365 testes aprovados, 87,92% de cobertura, saída 0**; validação
focada de API/XLSX/Resultados: 60 aprovados. Três rejeições anteriores H02
preservadas após cache, reanálise forçada e reabertura. Gate aprovado não supera
as metas de qualidade E10 reprovadas; os demais critérios de aceite ficam abertos.
