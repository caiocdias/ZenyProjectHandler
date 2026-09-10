# Zeny Project Handler — Mercado editável, painéis e leitura de redes

Data: 10/09/2026. Base inicial: `336afba`. E01 diagnosticada em `4ce5b50`; E02 entregue
em `101c721`; E03 integrada em `4f48c93`; E04 integrada em `897d85c`.
E05 concluída sobre `7dd6fbe`, com correções sem commit. Demais estados conforme o índice.

## Objetivo e uso

Permitir que o técnico ajuste a classificação inicial do banco para Rural, Urbano ou Ambos;
aplicar as duas famílias de normas em Ambos; manter cartões legíveis com rolagem independente
por painel; substituir os colchetes dos elementos por marca-texto por situação; e melhorar a
extração e a associação de elementos e vãos usando a NS 1256148225 como caso de verificação.

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
| E06 | Marca-texto por situação | #pendente | Nenhuma | Realce navegável com transparência |
| E07 | Extração robusta de evidências | #pendente | E01 | OCR/geometria com cobertura mensurada |
| E08 | Associação de elementos e vãos | #pendente | E01, E07 | Ocorrências e topologia recuperadas |
| E09 | Homologação integrada | #pendente | E03, E04, E05, E06, E08 | Aceite completo e relatório final |

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

## E06 — Marca-texto por situação — #pendente

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

- [ ] As quatro situações têm cor e legenda corretas, sem depender do estado de aprovação.
- [ ] Texto/desenho permanece legível, realce acompanha evidência e colchetes foram substituídos.
- [ ] Seleção PDF↔Resultados, visibilidade e rejeição funcionam sem realce órfão.
- [ ] Zoom, rotação e troca de tiles/página não deslocam marcação nem ocultam callouts.

**Validação obrigatória:** `python -m pytest tests/integration/test_pdf_viewer_progressive.py tests/integration/test_pdf_viewer_http_gateway.py tests/integration/test_compliance_callout_viewer.py tests/integration/test_compliance_visibility.py tests/unit/test_pdf_coordinates.py tests/unit/test_pdf_rendering_budget.py tests/server/test_review_api.py`.
Adicionar casos de polígonos inclinados, linhas/pontos, sobreposição e situações; inspecionar
temas claro/escuro, zoom 50/100/200% e rotações 0/90/180/270°. Usar fixtures com as três cores
pedidas e Alterar; a NS real complementa a inspeção após E08. Todos os testes aprovados.
**Bloqueios:** nenhum bloqueio conhecido.
**Riscos e mitigação:** geometria ampla comunica leitura inexistente; ancorar nas evidências
efetivas e preservar orientação. Cores do PDF se confundem com overlay; validar transparência,
legenda e alternância de visibilidade.
**Evidências e handoff:** ainda não executada. Registrar mapeamento final, opacidade, geometria,
inspeções e eventuais mudanças aditivas no DTO com snapshot/testes de contrato.

## E07 — Extração robusta de evidências — #pendente

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

- [ ] Todas as omissões inequívocas atribuídas à extração em E01 têm evidência recuperada.
- [ ] Evidências preservam posição/orientação e não duplicam a mesma ocorrência.
- [ ] Ausência/falha de OCR é diagnosticada e cache antigo não mascara o novo comportamento.
- [ ] Benchmark com OCR real atende metas/orçamentos de E01 e hash da origem não muda.

**Validação obrigatória:** `python -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_tesseract_ocr.py tests/unit/test_tesseract_runtime.py tests/unit/test_analysis_cache.py tests/unit/test_pdf_coordinates.py tests/integration/test_document_analysis.py`.
Executar também novas fixtures e o comando de benchmark completo registrado por E01, comparando
itens, caixas, diagnósticos e desempenho. Todos os testes devem passar; mocks de OCR não
substituem a comparação local com Tesseract real.
**Bloqueios:** nenhum bloqueio conhecido; dependência E01 permanece pendência normal.
**Riscos e mitigação:** excesso de recortes/DPI e falso texto em fotos; limitar por região,
medir orçamento e testar controles negativos. Se a investigação revelar frentes independentes
que não cabem em uma sessão, subdividir antes de iniciar, preservando IDs já executados.
**Evidências e handoff:** ainda não executada. Registrar perdas recuperadas, remanescentes de
associação para E08, versão/configuração e comparativos do benchmark.

## E08 — Associação de elementos e vãos — #pendente

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
Execute E08 — Associação de elementos e vãos de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro AGENTS.md aplicáveis, roadmap e handoffs de E01/E07, ADR 0015, adaptadores de interpretação, analysis_regions.py, automatic_promotion.py, spans.py, pipeline e testes; confira git status. Verifique E01/E07 concluídas e código sem divergência não tratada. Preserve mudanças preexistentes e marque E08 em andamento no índice e detalhe. Recupere as ocorrências e os vãos inequívocos do inventário, corrigindo apenas perdas demonstradas de normalização, associação, promoção e endpoints. Crie regressões sintéticas com controles negativos, preserve qualificadores, situações, comprimentos substituídos, rede/ramal/padrão, revisão humana e identidades determinísticas. Não invente cabos, medidas ou vínculos por proximidade; torne ambiguidade revisável. Atualize versões/assinaturas, documentação e testes necessários. Execute as validações obrigatórias e benchmark completo até Resultados/exportação, cumprindo metas E01. Só marque concluída após aceite; se houver impedimento real, marque bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos, métricas e casos remanescentes. Não declare sucesso com validação falhando ou não executada; não crie commit nem publique. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [ ] Todos os elementos/vãos legíveis e inequívocos do inventário aparecem com vínculos corretos.
- [ ] Endpoints, comprimentos e situações correspondem à evidência; ambiguidades são explícitas.
- [ ] Não há falsos ativos/vínculos nos controles negativos nem duplicação ao reanalisar.
- [ ] Resultados e exportação concordam; revisões humanas e histórico são preservados.

**Validação obrigatória:** `python -m pytest tests/unit/test_rule_based_interpreter.py tests/unit/test_spans.py tests/unit/test_analysis_regions.py tests/unit/test_topology_path_compliance.py tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py tests/server/test_review_api.py tests/server/test_deliverable_exports.py tests/e2e/test_span_compliance_ui.py`.
Executar novas regressões e benchmark E01 com OCR real, promoção e vãos. Exigir precisão/recall
por categoria, correspondência dos endpoints/comprimentos, duplicatas e desempenho dentro das
metas, além de navegação visual amostrada em cada classe de correção. Testes todos aprovados.
**Bloqueios:** nenhum bloqueio conhecido.
**Riscos e mitigação:** melhorar recall fabricando relações; testar casos ambíguos e negativos.
Identidade mudar ao corrigir geometria; comprovar comportamento de reanálise e decisões antigas.
Subdividir antes de iniciar se E01 revelar correções independentes além de uma sessão.
**Evidências e handoff:** ainda não executada. Registrar comparativo por item/fase, versões,
regressões, ambiguidades justificadas e instruções de reanálise para homologação.

## E09 — Homologação integrada — #pendente

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
Execute E09 — Homologação integrada de docs/roadmap-mercado-paineis-leitura-rede.md. Leia primeiro AGENTS.md aplicáveis, roadmap inteiro, handoffs E01–E08, README.md, docs/especificacao-funcional.md e testes de integração/e2e; confira git status. Verifique E03/E04/E05/E06/E08 e dependências concluídas e código coerente com as evidências. Preserve alterações preexistentes e marque E09 em andamento no índice e detalhe. Valide em ambiente isolado o fluxo de inicialização SQL, escolha Rural/Urbano/Ambos, persistência, conflitos, reconexão, reanálise, snapshots e exportação. Execute benchmark com OCR real da NS 1256148225 e verifique marca-textos, navegação e rolagem dos cinco painéis conforme as matrizes visuais. Execute o gate público completo; mantenha PDFs reais opcionais e fora do Git. Corrija regressões de integração dentro do escopo e atualize documentação do comportamento final, sem diminuir metas. Só marque concluída após satisfazer toda a definição global de pronto e validações; se houver impedimento real, marque bloqueada com causa, evidência, impacto e desbloqueio. Preencha Evidências e handoff com arquivos, decisões, comandos, métricas e inspeções. Não declare sucesso com validações falhando ou não executadas. Não crie commit, release, publicação ou migração operacional. Termine com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [ ] Todos os itens da definição global de pronto possuem evidência rastreável.
- [ ] Gate público integral aprovado com cobertura mínima 85,01% e fixtures independentes do PDF.
- [ ] NS 1256148225 atende inventário/metas E01 no pipeline completo e no visualizador.
- [ ] Documentação, contrato, histórico e exportações descrevem o comportamento entregue.

**Validação obrigatória:** `.\IniciarTestes.bat`, que cobre integridade das dependências, Ruff,
formatação, Mypy, fronteira do cliente magro, Pytest com cobertura e complexidade. Exigir saída
zero e relatório aprovado. Rodar o benchmark local de E01 e as matrizes visuais E05/E06 no
fluxo integrado; `python scripts/smoke_examples.py` complementa regressão nativa nos exemplos
locais disponíveis, mas não substitui o benchmark com OCR. Verificar diff do Git sem PDFs,
recortes, credenciais ou dados de execução. Não é necessário SQL operacional para esse gate.
**Bloqueios:** nenhum bloqueio conhecido. Se uma dependência, PDF ou runtime necessário faltar
na homologação, registrar o impedimento real e concluir apenas o trabalho independente.
**Riscos e mitigação:** relato de sucesso apenas de testes sintéticos; exigir os dois conjuntos
de evidência, público e local, sem tornar o segundo requisito de CI.
**Evidências e handoff:** ainda não executada. Registrar revisão testada, resultados completos,
relatório sanitizado, métricas antes/depois, matrizes visuais e pendências efetivas. Conclusão
do roadmap exige todos os aceites; não marcar pronto apenas porque o gate público passou.
