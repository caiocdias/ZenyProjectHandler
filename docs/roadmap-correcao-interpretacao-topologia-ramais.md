# Roadmap de correção da interpretação, topologia e ramais dos projetos comissionados

## Objetivo e resultado esperado

Corrigir, com regressões públicas e determinísticas, os problemas observados nos projetos locais
`1255651475` e `1255839633`: redução de vão classificada como remoção de cabo, ponto de padrão
misturado com poste, ramal tratado como vão de rede, chave em bolsa ausente ou existente, estrutura
`N(x)` ausente, estruturas repetidas colapsadas e falso fim/transição de rede. O resultado esperado é
uma análise que preserve ocorrências físicas, reconstrua a topologia elétrica antes de inferir regras
e aplique ao ramal de conexão somente requisitos normativos próprios.

Este documento planeja a correção; ele não implementa nenhuma etapa. Execute uma etapa por sessão
limpa do Codex, atualize sua tag e preencha **Evidências e handoff** antes de iniciar a próxima.

## Contexto confirmado

- A raiz é um projeto Python 3.11–3.13 com cliente Qt, servidor FastAPI, contratos Pydantic,
  persistência SQLite e gate principal `IniciarTestes.bat`.
- O servidor é a única fonte das interpretações, relações, regiões, vãos, fatos e callouts. O cliente
  apenas apresenta DTOs, conforme `README.md`, `docs/arquitetura-conformidade.md` e ADR 0013.
- `examples/` é uma bancada local ignorada pelo Git. PDFs reais não entram no gate nem podem ser
  versionados; garantias permanentes usam fixtures sintéticas em `tests/`.
- Em 01/09/2026, o worktree estava limpo antes da criação deste roadmap. Os exemplos locais eram:
  `examples/PROJETO DE REDE - 1255651475.pdf` (1 página A4) e
  `examples/PROJETO DE REDE - 1255839633.pdf` (1 página A3).
- Baseline somente leitura em 01/09/2026:
  - `scripts/smoke_examples.py`: 2 PDFs aprovados; respectivamente 1.323 evidências/10 propostas/4
    relações e 515 evidências/32 propostas/29 relações.
  - suíte dirigida de interpretação, vãos e topologia: 82 testes aprovados; houve apenas aviso de
    permissão do cache do Pytest, sem falha de teste.
- O pipeline relevante está em:
  - extração: `src/zeny_project_handler/adapters/analysis/pymupdf_*.py`;
  - interpretação: `src/zeny_project_handler/adapters/interpretation/`;
  - promoção/domínio: `src/zeny_project_handler/application/automatic_promotion.py` e
    `src/zeny_project_handler/domain/`;
  - vãos/topologia/conformidade: `src/zeny_project_handler/application/spans.py`,
    `span_compliance.py`, `topology_compliance.py` e `project_compliance.py`;
  - registro declarativo: `src/zeny_project_handler/adapters/compliance/data/`;
  - contrato/apresentação: `src/zeny_project_handler_contracts/`,
    `src/zeny_project_handler_server/review_api.py`,
    `src/zeny_project_handler_client/ui/review_panel.py` e
    `src/zeny_project_handler_server/deliverable_exports.py`.
- A inspeção técnica reproduziu os sintomas:
  - em `1255651475`, `B-4 CAA` e `N-(4 CAA)` foram classificados `REMOVER` e associados
    indevidamente a `V1-2`; `100A-10KA-2H` foi classificada `EXISTENTE`; equipamentos simbólicos
    próximos foram associados ao identificador `P1` do padrão;
  - em `1255839633`, `N(2)` não gerou estrutura; somente uma ocorrência de `CM3` e uma de `S3R`
    sobreviveram em postes com duas; `100A-10KA-5H` não sobreviveu como chave, enquanto o fragmento
    `-300A` do dispositivo foi proposto; o trecho `V4-5` terminou no padrão sem tipo próprio;
  - `contains_code()` rejeita códigos de um caractere e `_deduplicate_point_proposals()` colapsa por
    categoria, catálogo, identificador e situação, explicando diretamente parte das perdas;
  - `project_situation_override()` exige que o centro do rótulo esteja dentro de uma bolha vetorial
    muito específica, o que não cobre as bolsas parciais das amostras;
  - `_add_region_connection_facts()` considera `len(incident_mt) == 1` suficiente para fim de rede e
    não possui um gate explícito de completude topológica;
  - `PontoRede` já suporta `TipoPontoRede.ENTREGA`, mas a promoção automática só cria pontos de
    `POSTE` ou `CONEXAO`; `VaoDetectado` não distingue rede de distribuição e ramal de conexão.
- Pesquisa primária feita em 01/09/2026:
  - o [portal oficial de normas de conexão da CEMIG](https://www.cemig.com.br/normas-tecnicas/normas-tecnicas-de-conexao/)
    aponta a [ND-5.1 vigente](https://www.cemig.com.br/wp-content/uploads/2025/10/nd5_1_000001p.pdf),
    revisão Mar/2026;
  - itens 4.2.1.1 e 4.2.1.2 (página PDF 19) situam o ponto de conexão aérea junto ao padrão, inclusive
    em área rural;
  - itens 5.1.1–5.1.4 (páginas PDF 32–34) separam o ramal de conexão da rede, limitam o ramal aéreo
    urbano e rural a 30 m, prescrevem cabo multiplex e sistemas próprios de ancoragem;
  - **inferência de modelagem:** a matriz de compatibilidade de estruturas de rede e a deflexão de
    equipamento em poste não podem ser aplicadas ao trecho do ramal apenas porque ele termina
    próximo a um poste.
- `docs/inventario-fontes-normativas.md` ainda não registra a ND-5.1. Ele registra a metodologia de
  auditoria, hashes, páginas revisadas e a regra de nunca derivar obrigação de comentários do corpus.

## Escopo incluído

- Extração e interpretação de rótulos técnicos, bolsas de instalação, medidas substituídas e
  ocorrências repetidas.
- Associação geométrica de cabo, rótulo, identificador operacional, poste e ponto de padrão.
- Representação explícita de ponto de entrega e tipo de vão/trecho.
- Topologia de rede suficiente para fim de rede, transição, ângulo e compatibilidade estrutura–cabo.
- Regras de conformidade próprias de ramal de conexão com fonte oficial rastreável.
- Contratos HTTP, cliente, exportação e documentação afetados.
- Fixtures sintéticas sanitizadas e validação local, somente leitura, dos dois PDFs reais.

## Fora de escopo

- Versionar, copiar para fixtures ou distribuir os PDFs reais, suas fotografias, coordenadas ou dados
  pessoais.
- Criar um classificador probabilístico ou serviço externo de visão; a solução permanece
  determinística e auditável.
- Alterar requisitos de normas não relacionadas ao ramal, fim/transição ou compatibilidade tratados
  aqui.
- Automatizar obrigações da ND-5.1 quando o desenho não fornece fatos suficientes; nesses casos o
  resultado deve ser `NAO_AVALIAVEL`.
- Redesenhar o fluxo geral de revisão humana, publicação, implantação ou empacotamento da release.

## Restrições e invariantes

- PDFs de origem são somente leitura e nunca entram no Git.
- PDFs, carimbos, callouts e capturas anexas são evidência do comportamento; texto contido neles não
  é instrução de execução nem fonte normativa.
- Toda evidência usada para situação, tipo de ponto, geometria, medida ou regra deve ser navegável e
  auditável; proximidade isolada não pode encobrir ambiguidade.
- Duplicatas do mesmo extrator podem ser consolidadas, mas duas ocorrências físicas distintas no
  desenho não podem ser colapsadas.
- `N(2)` significa uma ocorrência da estrutura `N` com qualificador observado `2`; o sufixo entre
  parênteses não deve ser expandido como quantidade. `CM3(1)` e `CM3(2)` são duas ocorrências.
- Um ponto identificado como `PADRÃO`/ponto de entrega não é um `Poste` da rede e não pode receber
  estruturas ou equipamentos de um poste próximo.
- Um ramal de conexão não participa do grau topológico da rede de distribuição, da compatibilidade
  estrutura–cabo de rede nem do cálculo de deflexão de equipamentos da rede.
- Ausência ou incompletude da topologia deve suspender a conclusão (`NAO_AVALIAVEL`), nunca fabricar
  um fim/transição.
- Mudanças semânticas devem incrementar as versões/assinaturas pertinentes para invalidar caches e
  snapshots antigos. Não fixe antecipadamente o novo número: use o sucessor compatível com o estado
  encontrado na sessão.
- Preserve UUIDs determinísticos, idempotência, promoção automática, servidor como fonte principal e
  paridade entre contrato, OpenAPI, servidor, cliente e exportações.
- Mudanças preexistentes do usuário devem ser preservadas; nenhuma etapa autoriza commit, push,
  publicação ou implantação.

## Hipóteses e decisões em aberto

1. **Representação da redução de vão — decidida em E01.** O ADR 0015 escolhe a nova situação pública
   `ALTERAR`; a medida vigente alimenta o cabo e a substituída permanece auditável. O cabo sobrevivente
   nunca é traduzido para `REMOVER` nem ocultado como `EXISTENTE` mais texto livre.
2. **Variações de bolsa — recorte fixado em E01.** As fixtures cobrem bolsa vinho parcial sobre o
   sufixo e negativos sem bolsa ou com marca de outro objeto. E03 só pode ampliar formas com evidência
   sintética positiva e negativa; proximidade de qualquer vetor vermelho não basta.
3. **Ramal aéreo versus subterrâneo — decidida em E01.** O ADR 0015 separa `TipoTrechoRede` de
   `ModalidadeTrecho`; modalidade desconhecida permanece fail-closed e torna a obrigação dependente
   dela não avaliável.
4. **Norma de ângulo — decidida em E01.** A auditoria integral de termos nas 205 páginas da ND-5.1 e
   a revisão visual dirigida não localizaram limite angular para o ramal. Ramais ficam excluídos da
   regra de ângulo da rede, e nenhum novo limite será criado sem outra fonte oficial inequívoca.

## Definição global de pronto

- Todos os oito relatos do pedido (sete famílias de defeito, com a chave reproduzida nos dois
  projetos) estão cobertos por testes sintéticos positivos e
  negativos.
- Os dois exemplos locais produzem a matriz esperada sem alteração dos arquivos:
  - `1255651475`: cabo principal não removido, medida antiga `321 m` marcada como substituída,
    medida vigente `269 m`, `V1-2` classificado como ramal, padrão `P1` separado e chave
    `100A-10KA-2H` a instalar;
  - `1255839633`: estrutura `N(2)` presente, duas `CM3` e duas `S3R` preservadas onde desenhadas,
    chave `100A-10KA-5H` a instalar, `V4-5` classificado como ramal, padrão `P5` separado e ausência
    dos falsos callouts de fim/transição, ângulo e compatibilidade derivados do ramal;
  - nenhum fragmento de identificação de dispositivo é promovido como equipamento catalogado sem
    evidência completa.
- Regras de rede ignoram ramais; regras de ramal citam ND-5.1 Mar/2026 e só avaliam fatos resolvidos.
- Contratos, OpenAPI, cliente, Excel e documentação exibem coerentemente o tipo do vão/ponto e a
  representação escolhida para alteração.
- Testes dirigidos, `scripts/smoke_examples.py` e `IniciarTestes.bat` passam. A validação dos PDFs
  reais é registrada no handoff sem incorporar seu conteúdo ao repositório.

## Índice das etapas

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Contrato normativo, decisão de domínio e fixtures | #concluida | nenhuma | ADR, inventário ND-5.1 e corpus sintético sanitizado |
| E02 | Estruturas `N(x)` e ocorrências repetidas | #pendente | E01 | parser contextual e cardinalidade física preservada |
| E03 | Chaves e bolsas de instalação | #pendente | E01, E02 | nomenclatura completa e situação de instalação robusta |
| E04 | Redução de vão e associação cabo–traçado | #pendente | E01, E02, E03 | medida vigente, alteração explícita e cabo no traçado correto |
| E05 | Ponto de padrão e ramal no domínio topológico | #pendente | E01, E04 | ponto `ENTREGA` e tipo de vão/trecho derivados |
| E06 | Fim/transição, ângulo e compatibilidade pela topologia | #pendente | E05 | fatos fail-closed apenas sobre rede resolvida |
| E07 | Conformidade específica do ramal | #pendente | E05, E06 | registro ND-5.1 e guardas de aplicabilidade |
| E08 | Contratos, cliente e exportações | #pendente | E04, E05, E07 | DTO/UI/XLSX/OpenAPI coerentes |
| E09 | Gate integrado e homologação dos exemplos | #pendente | E02–E08 | validação global e handoff final |

### Matriz de cobertura do pedido

| Projeto/relato | Etapas responsáveis | Evidência final esperada |
|---|---|---|
| `1255651475` — redução de vão aparece como remoção | E01, E04, E08, E09 | alteração explícita, `269 m` vigente e cabo fora de `A remover` |
| `1255651475` — padrão recebe elementos de poste | E01, E05, E08, E09 | `P1` como entrega; elementos permanecem no poste real |
| `1255651475` — chave em bolsa aparece existente | E03, E09 | `100A-10KA-2H` a instalar |
| `1255839633` — estrutura `N(x)` ausente | E02, E09 | uma estrutura `N` com qualificador `2` |
| `1255839633` — chave em bolsa ausente | E03, E09 | `100A-10KA-5H` a instalar, sem fragmento `-300A` |
| `1255839633` — falso fim/transição no P2 | E05, E06, E07, E09 | topologia completa sem requisito indevido de para-raios |
| `1255839633` — ramal tratado como vão de rede | E01, E05, E06, E07, E08, E09 | `V4-5` como ramal e somente regras ND-5.1 aplicáveis |
| `1255839633` — duas `CM3` e duas `S3R` | E02, E09 | quatro ocorrências preservadas com evidências próprias |

## E01 — Contrato normativo, decisão de domínio e fixtures — #concluida

**Objetivo:** fechar o significado de alteração de vão, ponto de entrega e ramal; auditar as páginas
necessárias da ND-5.1 Mar/2026; criar fixtures sintéticas sem dados pessoais que reproduzam todos os
sintomas antes de mudar a heurística.

**Por que agora:** as regras de ramal e a representação pública de alteração afetam todas as etapas
seguintes. A norma e os casos precisam virar um contrato observável, não pressupostos espalhados.

**Dependências e paralelismo:** nenhuma. É dependência de todas as demais. Não deve rodar em paralelo
com outra etapa que altere documentação normativa ou `tests/pdf_fixtures.py`.

**Escopo:** `docs/inventario-fontes-normativas.md`, `docs/especificacao-funcional.md`,
`docs/arquitetura-conformidade.md`, novo ADR em `docs/adr/` (usar
`0015-pontos-de-entrega-ramais-e-alteracao-de-vao.md` se o número continuar livre),
`tests/pdf_fixtures.py`, testes de extração/interpretação que consumam fixtures sanitizadas e os dois
PDFs locais apenas para inspeção somente leitura.

**Fora de escopo:** corrigir analisadores, adicionar regra ativa, copiar pixels/textos identificáveis
dos PDFs reais ou fazer teste padrão depender de `examples/`.

**Passos de implementação:**

1. Baixar a ND-5.1 somente da URL oficial, registrar revisão, data de acesso, quantidade de páginas e
   SHA-256; renderizar e revisar por texto e imagem as páginas 18–19, 32–35, Tabelas 5 e 16, Desenhos
   1, 3, 4 e 59, além de qualquer página diretamente referenciada por esses itens.
2. Documentar, sem transcrição extensa, ponto de conexão, responsabilidade, modalidade, limite de
   comprimento, condutor e ancoragem; registrar explicitamente que nenhum limite de ângulo de rede
   foi localizado para o ramal no recorte auditado.
3. Registrar no ADR a representação escolhida para redução de vão, o uso de
   `TipoPontoRede.ENTREGA`, a derivação de tipo do vão e a estratégia de compatibilidade com projetos
   persistidos/reanálise.
4. Criar fixtures mínimas para: `N(2)`, `CM3(1)+CM3(2)`, duas `S3R`, chaves `2H` e `5H` com bolsa
   parcial, medida `321 m` riscada e `269 m` vigente, cabo colinear e ramal oblíquo, rótulo `PADRÃO`,
   topologia completa/incompleta, fim real e transição real.
5. Validar que as fixtures não contêm nomes, telefones, NS, coordenadas, fotos, logos ou assinaturas
   dos projetos reais.

**Prompt para uma sessão limpa:**

```text
Na raiz do ZenyProjectHandler, execute a etapa E01 — Contrato normativo, decisão de domínio e fixtures do arquivo docs/roadmap-correcao-interpretacao-topologia-ramais.md. Leia primeiro todas as instruções AGENTS.md aplicáveis, o roadmap inteiro, README.md, docs/inventario-fontes-normativas.md, docs/arquitetura-conformidade.md, docs/especificacao-funcional.md, os ADRs 0005, 0009, 0011 e 0013, tests/pdf_fixtures.py e o estado atual do git. Confirme que E01 continua pendente e que o código não divergiu; preserve alterações preexistentes e limite-se ao escopo desta etapa. Atualize E01 no índice e no detalhe para #em-andamento ao iniciar.

Audite a ND-5.1 Mar/2026 exclusivamente na fonte oficial da CEMIG. Registre URL, revisão, acesso, páginas e SHA-256 em docs/inventario-fontes-normativas.md; revise texto e renderização das páginas 18–19, 32–35, Tabelas 5 e 16, Desenhos 1, 3, 4 e 59 e referências indispensáveis. Não derive obrigações dos comentários dos PDFs reais. Registre em ADR a decisão sobre alteração de vão (o resultado deve ficar explicitamente alterado e nunca A remover), o uso de TipoPontoRede.ENTREGA, a classificação rede versus ramal e a compatibilidade/reanálise de dados existentes. Use docs/adr/0015-pontos-de-entrega-ramais-e-alteracao-de-vao.md se 0015 estiver livre; se não estiver, use o próximo número e atualize o roadmap com o caminho real.

Crie em tests/pdf_fixtures.py fixtures sintéticas mínimas e sanitizadas para cada caso listado no escopo de E01, com testes que validem apenas a construção/extração dos insumos, sem congelar como correto o comportamento defeituoso atual e sem xfail permanente. Não copie dados, imagens ou coordenadas dos PDFs reais e não faça o gate depender de examples/. Execute as validações de E01. Não declare sucesso com teste obrigatório falhando ou não executado. Ao concluir todos os critérios, atualize E01 para #concluida no índice e no detalhe e preencha Evidências e handoff com arquivos, decisões, fontes, comandos e resultados. Se houver impedimento real, marque #bloqueada e documente causa, evidência, impacto e ação de desbloqueio. Não crie commit, não publique e não implante. Finalize com resumo conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [x] ND-5.1 Mar/2026 possui metadados, hash, páginas auditadas e paráfrases rastreáveis no inventário.
- [x] O ADR resolve a representação da alteração e a compatibilidade/reanálise sem deixar decisão
  material para E04/E08.
- [x] O contrato diferencia poste, ponto de entrega, ramal de conexão e rede de distribuição.
- [x] Os oito relatos do pedido possuem fixture sintética positiva e ao menos um negativo
  contra generalização indevida.
- [x] Nenhuma fixture contém dado identificável ou material copiado dos PDFs locais.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_pymupdf_analyzer.py tests\unit\test_rule_based_interpreter.py tests\unit\test_spans.py tests\unit\test_topology_compliance.py
.\.venv\Scripts\python.exe scripts\smoke_examples.py
```

Resultado esperado: testes dirigidos passam; os dois PDFs locais continuam legíveis e inalterados.
A inspeção visual das páginas normativas selecionadas deve concordar com o texto registrado.

**Bloqueios:** nenhum bloqueio conhecido. Se a URL oficial ou revisão mudar, registrar a nova versão
antes de continuar; não usar cópia de terceiros.

**Riscos e mitigação:** interpretar `(2)` como quantidade; mitigar fixando no ADR e nas fixtures que é
qualificador. Generalizar bolsa a qualquer marca vermelha; mitigar com negativos de medida riscada e
vetor vermelho não relacionado.

**Evidências e handoff (01/09/2026):**

- **Fonte normativa:** portal oficial de normas de conexão e PDF oficial da ND-5.1, revisão Mar/2026,
  vigência 23/03/2026, 205 páginas, 8.407.204 bytes e SHA-256
  `ffdbd926d0eb331cd3951227482a94534ae8746bff98bfeb7a50afc298972f75`. Foram extraídas e
  renderizadas as páginas PDF 18–20, 32–35, 68 (Tabela 5), 80 (Tabela 16), 85 (Desenho 1), 87
  (Desenho 3), 88 (Desenho 4) e 162 (Desenho 59). Texto e imagem concordaram. A busca nas 205 páginas
  não encontrou limite angular para ramal. Metadados, localizadores, paráfrases e limites estão em
  `docs/inventario-fontes-normativas.md`.
- **Decisões:** `docs/adr/0015-pontos-de-entrega-ramais-e-alteracao-de-vao.md` define
  `SituacaoProjeto.ALTERAR`, `TipoPontoRede.ENTREGA` com `poste_id=None`, `TipoTrechoRede` separado de
  `ModalidadeTrecho`, exclusão de ramal/desconhecido do grafo da rede e leitura compatível como
  desconhecido com reanálise explícita, sem backfill heurístico. O contrato futuro, ainda não
  implementado nesta etapa, também foi registrado em `docs/arquitetura-conformidade.md` e
  `docs/especificacao-funcional.md`.
- **Fixtures e testes:** `tests/pdf_fixtures.py` ganhou cinco construtores sanitizados cobrindo
  `N(2)` e negativos contextuais; `CM3(1)`/`CM3(2)` e duas `S3R`; chaves 2H/5H com bolsa parcial,
  versões sem bolsa, marca não relacionada e identificador sintético maior; `321 m` riscado,
  `269 m` vigente e medida não cruzada; rede colinear, ramal oblíquo, `PADRÃO` e legenda negativa;
  topologia completa/incompleta, fim real e transição real. O rótulo visual `PADRÃO` usa texto
  extraível `PADRAO` e til vetorial sintético, sem depender de fonte externa. Os dez testes novos em
  `tests/unit/test_pymupdf_analyzer.py` validam somente texto/vetores/geometrias brutos e sanitização;
  não chamam o interpretador, não possuem `xfail` e não acessam `examples/`.
- **Validações:** `ruff check` passou nos dois arquivos Python alterados e `ruff format --check`
  confirmou a formatação após o ajuste mecânico. A execução Pytest obrigatória, com os mesmos quatro
  arquivos e `-p no:cacheprovider --basetemp tmp\\pytest-e01-required` por restrição de escrita do
  sandbox no temporário global, terminou com `100 passed in 3.97s`; os dez testes de E01 isolados
  terminaram com `10 passed in 0.72s`. `scripts/smoke_examples.py` terminou com 2 aprovados e 0
  falhas: 1.323 evidências/10 propostas/4 relações e 515 evidências/32 propostas/29 relações.
- **Integridade dos exemplos:** antes e depois do smoke, tamanho, `mtime` e SHA-256 permaneceram
  idênticos: `b1d6bd3d9f4b3fff8334ffbfb22b56e79f8a88f231ea237408c17ca551569c6d` e
  `ab6c8fb160f1b454fa605791dbdc0379e571fff61e397e347371b40447f7ab6d`. Nenhum conteúdo real entrou
  nas fixtures ou na documentação.
- **Handoff para E02:** consumir `create_e01_structure_occurrences_pdf` para implementar parser de
  qualificador e identidade de ocorrência; preservar o contrato do ADR 0015 e não alterar ainda
  ponto de entrega, ramal, `ALTERAR` ou regra normativa. A exclusão preexistente de
  `docs/roadmap-gmax-fluxos-ns.md` foi preservada e não pertence a E01.

## E02 — Estruturas `N(x)` e ocorrências repetidas — #pendente

**Objetivo:** reconhecer códigos de estrutura de um caractere somente em sintaxe contextual segura e
preservar cada ocorrência física repetida no mesmo poste sem duplicar leituras equivalentes.

**Por que agora:** é uma correção isolável do parser e remove a perda direta causada por
`contains_code()` e `_deduplicate_point_proposals()` antes das associações mais complexas.

**Dependências e paralelismo:** E01 concluída. Não executar em paralelo com E03 ou E04, pois as três
tocam `category_analyzers.py`, `rule_based.py`, `operational_labels.py` e seus testes.

**Escopo:** `category_analyzers.py`, `rule_support.py`, `rule_based.py`,
`operational_labels.py`, registro de interpretação e `tests/unit/test_rule_based_interpreter.py`.

**Fora de escopo:** situação de chave, classificação do padrão/ramal, conformidade e UI.

**Passos de implementação:**

1. Introduzir parser de token de estrutura com código, qualificador opcional e identidade de
   ocorrência; aceitar `N(2)` e rejeitar `N-(4 CAA)`, palavras com `N` e rótulos de cabo.
2. Preservar `CM3(1)` e `CM3(2)` como propostas diferentes e duas evidências `S3R` como duas
   ocorrências, mesmo com categoria/catálogo/poste/situação iguais.
3. Substituir a deduplicação por chave sem ocorrência por consolidação baseada na mesma ocorrência
   geométrica/semântica, mantendo fusão de OCR e texto nativo que descrevem o mesmo objeto.
4. Manter IDs determinísticos e registrar qualificador/evidência da ocorrência nos atributos.
5. Incrementar a versão do interpretador/registro pertinente e testar idempotência e ordem estável.

**Prompt para uma sessão limpa:**

```text
Na raiz do ZenyProjectHandler, execute E02 — Estruturas N(x) e ocorrências repetidas em docs/roadmap-correcao-interpretacao-topologia-ramais.md. Leia AGENTS.md aplicáveis, o roadmap, o ADR produzido por E01, category_analyzers.py, rule_support.py, rule_based.py, operational_labels.py, o registro de interpretação, tests/pdf_fixtures.py e tests/unit/test_rule_based_interpreter.py; confira git status, preserve mudanças preexistentes e verifique que E01 está realmente #concluida. Atualize E02 no índice e no detalhe para #em-andamento.

Implemente reconhecimento contextual de estrutura N com qualificador, sem permitir que N-(4 CAA) ou texto comum gere estrutura. Preserve como ocorrências físicas distintas CM3(1), CM3(2) e duas S3R no mesmo poste; consolide apenas duplicatas de extração da mesma ocorrência. IDs devem continuar determinísticos, o qualificador deve permanecer auditável e a ordem da entrada não pode alterar o resultado. Atualize as versões semânticas pertinentes conforme a convenção atual e adicione testes positivos e negativos usando as fixtures sanitizadas de E01. Execute todas as validações listadas. Não declare sucesso com teste falhando ou omitido. Concluído o aceite, marque E02 #concluida no índice e no detalhe e preencha Evidências e handoff; em impedimento real, marque #bloqueada com causa, evidência, impacto e ação. Não faça commit, push, publicação ou implantação. Entregue resumo conciso.
```

**Critérios de aceite:**

- [ ] `N(2)` produz exatamente uma estrutura `N` com qualificador `2`.
- [ ] `N-(4 CAA)` e variantes de cabo não produzem estrutura `N`.
- [ ] `CM3(1)` e `CM3(2)` produzem duas propostas distintas no mesmo `P`.
- [ ] Duas `S3R` físicas permanecem duas; texto nativo + OCR da mesma ocorrência permanece uma.
- [ ] IDs, ordenação e atributos são determinísticos em reexecução e permutação das evidências.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_rule_based_interpreter.py tests\unit\test_interpretation_registry_resources.py tests\integration\test_interpretation_pipeline.py
.\.venv\Scripts\python.exe -m ruff check src\zeny_project_handler\adapters\interpretation tests\unit\test_rule_based_interpreter.py
```

Resultado esperado: testes passam e os casos de cardinalidade distinguem ocorrência física de
duplicata de extração.

**Bloqueios:** nenhum bloqueio conhecido após E01.

**Riscos e mitigação:** explosão de propostas por `N`; mitigar exigindo sintaxe qualificada como `N(2)`
e contexto de identificador operacional. Perder deduplicação OCR; mitigar usando interseção
geométrica, origem e evidência-alvo em vez de código/poste apenas.

**Evidências e handoff:** ainda não iniciado.

## E03 — Chaves e bolsas de instalação — #pendente

**Objetivo:** reconhecer as nomenclaturas completas `100A-10KA-2H` e `100A-10KA-5H`, associar a
bolsa à ocorrência correta mesmo quando parcial/rotacionada e impedir promoção de fragmentos de
identificador de dispositivo.

**Por que agora:** E02 estabiliza identidade e deduplicação; E03 pode então corrigir situação e
nomenclatura sem esconder ocorrências válidas.

**Dependências e paralelismo:** E01 e E02 concluídas. Conflita com E04 nos analisadores; executar
sequencialmente.

**Escopo:** `pymupdf_page_extractors.py`, `pymupdf_ocr.py`, `pymupdf_analyzer.py` se a geometria de
extração precisar mudar; `category_analyzers.py`, `rule_support.py`, `operational_labels.py`, catálogo
de equipamentos e testes unitários/integrados relacionados.

**Fora de escopo:** rede versus ramal, regra de para-raios e UI final.

**Passos de implementação:**

1. Normalizar separadores/rotação sem truncar o padrão amperagem–kA–capacidade e exigir a assinatura
   completa para essa classe de chave.
2. Associar bolsa por sobreposição/continuidade da ocorrência ou vínculo geométrico explícito,
   admitindo bolsa sobre o sufixo, sem usar uma simples cor vermelha próxima.
3. Fazer a bolsa prevalecer sobre a cor do texto/símbolo somente para o equipamento vinculado.
4. Rejeitar fragmentos como `-300A` extraídos de `280835-300A-12T` como chave catalogada isolada.
5. Incrementar a assinatura do analisador se a extração mudar e a versão do interpretador se a
   semântica mudar; cobrir cache antigo versus reextração.

**Prompt para uma sessão limpa:**

```text
Execute E03 — Chaves e bolsas de instalação do roadmap docs/roadmap-correcao-interpretacao-topologia-ramais.md na raiz do ZenyProjectHandler. Antes de editar, leia AGENTS.md, o roadmap, o ADR de E01, os handoffs E01/E02, pymupdf_page_extractors.py, pymupdf_ocr.py, pymupdf_analyzer.py, category_analyzers.py, rule_support.py, operational_labels.py, o catálogo de equipamentos e os testes correspondentes; confira git status, dependências concluídas e divergências. Preserve mudanças preexistentes e marque E03 #em-andamento no índice e no detalhe.

Garanta que 100A-10KA-2H e 100A-10KA-5H sejam ocorrências completas de chave e que uma bolsa de instalação parcial ou rotacionada determine INSTALAR apenas para a ocorrência geometricamente vinculada. Não trate marca vermelha próxima, medida riscada ou fragmento -300A de um identificador maior como bolsa/chave. Adicione negativos para ausência de bolsa, bolsa de outro objeto, medida riscada e identificador 280835-300A-12T. Invalide cache e incremente versões somente nas camadas efetivamente alteradas. Execute as validações; teste obrigatório falhando ou não executado impede conclusão. Ao aceitar, marque E03 #concluida nos dois lugares e registre arquivos, decisões, comandos e resultados em Evidências e handoff. Se bloqueada, documente causa, evidência, impacto e ação. Não crie commit nem execute ação externa. Resuma ao final.
```

**Critérios de aceite:**

- [ ] As chaves `2H` e `5H` são reconhecidas como uma ocorrência completa cada.
- [ ] Com bolsa vinculada, a situação é instalar; sem bolsa e sem outra marca, não é inferida
  instalação.
- [ ] Bolsa parcial/rotacionada funciona; bolsa de objeto vizinho não vaza situação.
- [ ] `280835-300A-12T` não produz proposta fragmentária `-300A` como chave.
- [ ] Cache/versões impedem reutilizar evidência antiga incompatível.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_pymupdf_analyzer.py tests\unit\test_tesseract_ocr.py tests\unit\test_rule_based_interpreter.py tests\integration\test_interpretation_pipeline.py
.\.venv\Scripts\python.exe -m ruff check src\zeny_project_handler\adapters\analysis src\zeny_project_handler\adapters\interpretation tests
```

Resultado esperado: todos passam, incluindo negativos contra fragmento e vazamento de bolsa.

**Bloqueios:** nenhum bloqueio conhecido. Se a bolsa depender de vetor perdido na extração nativa,
documentar a evidência e corrigir a extração nesta etapa, não compensar com distância ampla.

**Riscos e mitigação:** aumentar recall e criar falsas chaves; mitigar exigindo assinatura completa e
contexto operacional. Alterar cache sem versão; mitigar com teste explícito da assinatura.

**Evidências e handoff:** ainda não iniciado.

## E04 — Redução de vão e associação cabo–traçado — #pendente

**Objetivo:** separar evidência de situação, rótulo, traçado e medida para reconhecer a redução de vão
como alteração do cabo sobrevivente, associar `269 m` como vigente, rejeitar `321 m` substituído e não
atribuir os cabos principais ao ramal `V1-2`.

**Por que agora:** depende de identidade e bolsas estabilizadas; fornece a geometria correta para a
classificação topológica de E05.

**Dependências e paralelismo:** E01, E02 e E03 concluídas. Não executar em paralelo com E05.

**Escopo:** `span_rules.py`, `operational_labels.py`, `category_analyzers.py`, `rule_support.py`,
`relation_rules.py`, `rule_based.py`, domínio/contratos somente na extensão decidida pelo ADR de E01,
testes de interpretação e vãos.

**Fora de escopo:** materializar ponto de entrega, avaliar fim/transição e ativar regras ND-5.1.

**Passos de implementação:**

1. Associar rótulo de cabo ao traçado por distância perpendicular, colinearidade/orientação,
   continuidade e extremidades; associar `Vx-y` somente ao traçado correspondente.
2. Permitir cabo de rede fisicamente ancorado/traçado sem forçá-lo ao identificador de ramal mais
   próximo.
3. Classificar a marca sobre `321 m` como supersessão de medida, não como situação de todo cabo;
   vincular `269 m` ao traçado principal.
4. Implementar a representação de alteração decidida em E01 em todas as camadas necessárias para
   manter a etapa integrável e auditável.
5. Cobrir cruzamento, linhas paralelas, rótulo entre dois traçados e ordem invertida de pontos.

**Prompt para uma sessão limpa:**

```text
Execute E04 — Redução de vão e associação cabo–traçado em docs/roadmap-correcao-interpretacao-topologia-ramais.md. Leia AGENTS.md, o roadmap e handoffs, o ADR de E01, span_rules.py, operational_labels.py, category_analyzers.py, rule_support.py, relation_rules.py, rule_based.py, domain/project.py, domain/enums.py, os codecs/contratos afetados pela decisão do ADR e testes de interpretação/vãos. Verifique E01–E03 concluídas, git status e divergências; preserve alterações preexistentes. Marque E04 #em-andamento no índice e no detalhe.

Implemente associação geométrica de rótulo, traçado, identificador e comprimento para que o cabo principal dos casos sintéticos não seja capturado pelo ramal V1-2. A marca vermelha que risca 321 m deve superseder apenas essa medida; 269 m deve ser a medida vigente e o cabo sobrevivente deve usar a representação de alteração fixada pelo ADR, nunca A remover. Um cabo de rede com traçado válido pode permanecer sem identificador V se o desenho não lhe atribuir um. Preserve evidências navegáveis, determinismo e idempotência. Adicione testes negativos para paralelas, cruzamento e rótulo ambíguo e incremente versões semânticas pertinentes. Rode as validações; não conclua com falhas ou omissões. Após o aceite, marque E04 #concluida nos dois locais e complete Evidências e handoff. Em bloqueio real, use #bloqueada com causa, evidência, impacto e desbloqueio. Não faça commit/push/publicação/implantação. Resuma mudanças e testes.
```

**Critérios de aceite:**

- [ ] A medida vigente é `269 m`; `321 m` permanece auditável como substituída e não vira comprimento.
- [ ] Cabos principais não recebem situação `REMOVER` por causa da medida riscada.
- [ ] Cabos principais não recebem `identificador_operacional=V1-2` se não pertencem ao traçado.
- [ ] O ramal e os cabos de rede usam geometrias distintas e relações coerentes.
- [ ] Casos ambíguos não são resolvidos apenas pela menor distância.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_rule_based_interpreter.py tests\unit\test_spans.py tests\unit\test_span_compliance_provider.py tests\integration\test_interpretation_pipeline.py
.\.venv\Scripts\python.exe -m mypy
```

Resultado esperado: testes passam e a fixture de redução demonstra medida vigente, supersessão e
associação ao traçado correto.

**Bloqueios:** a representação deve estar decidida no ADR de E01; dependência incompleta mantém E04
pendente, não bloqueada.

**Riscos e mitigação:** tolerâncias dependentes do formato A3/A4; mitigar usando coordenadas
normalizadas e testes em proporções diferentes. Geometria excessivamente rígida; mitigar com casos
rotacionados e ordem de pontos invertida.

**Evidências e handoff:** ainda não iniciado.

## E05 — Ponto de padrão e ramal no domínio topológico — #pendente

**Objetivo:** materializar `PADRÃO` como ponto de entrega sem poste, derivar rede versus ramal pela
topologia dos endpoints e impedir que estruturas/equipamentos do poste próximo migrem para o padrão.

**Por que agora:** E04 fornece traçados confiáveis; E05 cria o contrato que E06/E07 usarão para
selecionar a rede correta.

**Dependências e paralelismo:** E01 e E04 concluídas. Pode preparar testes de contrato em paralelo
com E06, mas não editar os mesmos arquivos; a implementação deve terminar antes de E06/E07.

**Escopo:** `domain/enums.py`, `domain/project.py`, codec JSON, `automatic_promotion.py`,
`relation_rules.py`, `spans.py`, `analysis_regions.py`, persistência/reanálise e testes de domínio,
codec, promoção e vãos.

**Fora de escopo:** regras de conformidade, DTO/UI final e mudança do significado normativo da
ND-5.1.

**Passos de implementação:**

1. Reconhecer o qualificador textual `PADRÃO` no cluster do identificador `P` e propagá-lo como tipo
   de ponto operacional auditável.
2. Materializar endpoint com `TipoPontoRede.ENTREGA` e `poste_id=None`; manter poste real separado.
3. Adicionar tipo fechado de vão/trecho derivado, no mínimo rede de distribuição, ramal de conexão e
   desconhecido, sem confundir modalidade aérea/subterrânea.
4. Classificar um trecho que termina em `ENTREGA` como ramal somente com evidências coerentes; em
   ambiguidade usar desconhecido.
5. Impedir relações `INSTALADA_EM`/`INSTALADO_EM` com ponto de entrega e escolher o poste real pelo
   cluster/traçado, não pela etiqueta `P` mais próxima.
6. Definir leitura compatível ou reanálise obrigatória para projetos persistidos conforme ADR E01.

**Prompt para uma sessão limpa:**

```text
Execute E05 — Ponto de padrão e ramal no domínio topológico em docs/roadmap-correcao-interpretacao-topologia-ramais.md. Leia AGENTS.md, roadmap/handoffs, ADR E01, domain/enums.py, domain/project.py, adapters/persistence/domain_json.py, automatic_promotion.py, relation_rules.py, spans.py, analysis_regions.py e testes de domínio/persistência/promoção/vãos. Verifique E01 e E04 concluídas, git status e divergências; preserve o trabalho do usuário e marque E05 #em-andamento nos dois locais.

Use TipoPontoRede.ENTREGA para um identificador P cujo cluster contém PADRÃO, com poste_id=None. Mantenha o poste real próximo como entidade independente e não associe estruturas/equipamentos ao ponto de entrega. Introduza o tipo fechado de vão/trecho decidido no ADR, distinguindo REDE_DISTRIBUICAO, RAMAL_CONEXAO e DESCONHECIDO, e derive ramal de endpoint ENTREGA apenas com evidência suficiente. Não confunda esse tipo com modalidade aérea/subterrânea. Preserve codec, IDs, promoção idempotente e compatibilidade/reanálise definida no ADR. Teste P1/P5 padrão, poste próximo, endpoint desconhecido e reexecução. Execute as validações e não declare sucesso com qualquer obrigatório falhando ou omitido. Ao aceitar, marque E05 #concluida no índice e no detalhe e atualize Evidências e handoff; se impedida, marque #bloqueada com causa/evidência/impacto/ação. Não faça commit ou ação externa. Finalize com resumo conciso.
```

**Critérios de aceite:**

- [ ] `P1/P5 PADRÃO` materializa ponto `ENTREGA` sem criar `Poste` fictício.
- [ ] O poste próximo mantém estruturas/equipamentos corretos; o padrão não os herda.
- [ ] Trecho poste–entrega vira `RAMAL_CONEXAO`; poste–poste resolvido vira
  `REDE_DISTRIBUICAO`; ambíguo vira `DESCONHECIDO`.
- [ ] `detectar_vaos()` preserva endpoint de entrega e tipo sem exigir dois postes.
- [ ] Codec/persistência e promoção repetida passam sem duplicação ou quebra de dados anteriores.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_project_domain.py tests\unit\test_persistence_codec.py tests\unit\test_spans.py tests\unit\test_rule_based_interpreter.py tests\integration\test_persistence.py tests\integration\test_interpretation_pipeline.py
.\.venv\Scripts\python.exe -m mypy
```

Resultado esperado: todos passam; fixtures demonstram ponto de entrega separado e tipos fail-closed.

**Bloqueios:** nenhum após E01/E04. Se o codec antigo não admitir evolução aditiva, implementar a
estratégia de reanálise/migração registrada no ADR nesta etapa.

**Riscos e mitigação:** todo rótulo “PADRÃO” na página capturar o `P` errado; mitigar por cluster e
geometria. Inferir ramal só por cabo BT; mitigar exigindo endpoint `ENTREGA` ou evidência equivalente.

**Evidências e handoff:** ainda não iniciado.

## E06 — Fim/transição, ângulo e compatibilidade pela topologia — #pendente

**Objetivo:** calcular terminal, transição, ângulo e compatibilidade somente sobre componentes de rede
de distribuição completos, excluindo ramais e suspendendo conclusões quando faltarem arestas.

**Por que agora:** depende do tipo de trecho e do ponto de entrega de E05.

**Dependências e paralelismo:** E05 concluída. Não executar em paralelo com E07 sobre
`topology_compliance.py`/fatos.

**Escopo:** `topology_compliance.py`, provedores de fatos, `spans.py`, testes de topologia e integração
de conformidade.

**Fora de escopo:** conteúdo declarativo final da regra ND-5.1 e UI.

**Passos de implementação:**

1. Montar o grafo ativo apenas com trechos `REDE_DISTRIBUICAO`; manter ramal/desconhecido fora do
   grau, percurso, ângulo e pares de compatibilidade.
2. Definir completude local: arestas incidentes, endpoints e nível/tecnologia resolvidos; publicar
   fatos explícitos de avaliabilidade.
3. Fim real exige componente completo e exatamente uma aresta MT ativa; estrutura de ancoragem por
   si só não é prova.
4. Transição exige duas arestas MT incidentes da rede, tecnologias distintas reconhecidas e
   continuidade no mesmo poste.
5. Deflexão e compatibilidade usam apenas os cabos fisicamente suportados pelo poste na rede.
6. Cobrir P2 intermediário, derivação com ramal, fim real, transição real e topologia incompleta.

**Prompt para uma sessão limpa:**

```text
Execute E06 — Fim/transição, ângulo e compatibilidade pela topologia do roadmap docs/roadmap-correcao-interpretacao-topologia-ramais.md. Leia AGENTS.md, roadmap/handoffs, ADR E01, topology_compliance.py, spans.py, provedores de fatos, registro atual das regras de fim/transição/ângulo/compatibilidade e testes test_topology_compliance.py, test_topology_path_compliance.py e integrações relacionadas. Confirme E05 concluída, confira git status e preserve mudanças preexistentes. Marque E06 #em-andamento no índice e no detalhe.

Refatore os fatos para operar somente sobre trechos REDE_DISTRIBUICAO. RAMAL_CONEXAO e DESCONHECIDO não contam no grau, não formam pares de transição, não entram no ângulo e não são cabos suportados para a matriz estrutura–cabo da rede. Publique avaliabilidade/completude e só conclua fim com componente MT completo e grau um; só conclua transição com duas arestas MT contínuas de tecnologias diferentes. Estrutura U4/CM3/S3R isolada nunca prova terminal ou transição. Teste o P2 intermediário sintético, derivação com ramal, terminal verdadeiro, transição verdadeira e ausência de aresta. Execute validações; falha ou teste não executado impede conclusão. Aceito o trabalho, marque E06 #concluida nos dois locais e preencha Evidências e handoff. Em impedimento real, use #bloqueada com causa, evidência, impacto e ação. Não faça commit/publicação/implantação. Resuma ao final.
```

**Critérios de aceite:**

- [ ] Poste intermediário com duas arestas MT de mesma tecnologia não é fim nem transição.
- [ ] Estrutura de ancoragem sem topologia completa não gera para-raios obrigatório.
- [ ] Ramal não altera grau, ângulo nem compatibilidade da rede.
- [ ] Fim real e transição real continuam reconhecidos com evidência navegável.
- [ ] Topologia incompleta publica não avaliabilidade e não um booleano falso/verdadeiro inventado.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_topology_compliance.py tests\unit\test_topology_path_compliance.py tests\integration\test_compliance_analysis.py tests\integration\test_compliance_visibility.py
.\.venv\Scripts\python.exe -m ruff check src\zeny_project_handler\application\topology_compliance.py tests
```

Resultado esperado: todos passam e os testes demonstram verdadeiros positivos e supressão dos falsos.

**Bloqueios:** nenhum após E05.

**Riscos e mitigação:** suprimir fim verdadeiro por completude excessiva; mitigar com fixture positiva
com todas as arestas resolvidas. Contar cabos paralelos como grau múltiplo; mitigar agrupando percurso
físico conforme `_route_groups()`.

**Evidências e handoff:** ainda não iniciado.

## E07 — Conformidade específica do ramal — #pendente

**Objetivo:** excluir ramais das regras de vãos/estruturas/ângulos de rede e ativar somente regras
ND-5.1 sustentadas por fatos resolvidos, incluindo limite de 30 m para ramal aéreo.

**Por que agora:** E05 classifica trecho e E06 fornece avaliabilidade topológica; o registro pode ser
alterado sem mascarar falha de interpretação.

**Dependências e paralelismo:** E05 e E06 concluídas. Conflita com E08 em contratos de fatos/regras;
executar primeiro.

**Escopo:** `span_compliance.py`, `topology_compliance.py`, `compliance_registry.py`,
`project_compliance.py`, `adapters/compliance/data/regras_conformidade_v1.json`, schemas, catálogo e
inventário de regras, testes de registro/persistência/análise.

**Fora de escopo:** automatizar distância ao solo, seção de condutor, demanda ou ancoragem sem fato
positivo; incorporar conteúdo ABNT protegido.

**Passos de implementação:**

1. Publicar fatos de tipo/modalidade/comprimento do trecho com evidência e avaliabilidade.
2. Guardar regras de rede por `REDE_DISTRIBUICAO` e impedir que ramal produza os fatos incompatíveis.
3. Adicionar fonte ND-5.1 Mar/2026 e regra de comprimento máximo de 30 m para ramal aéreo rural ou
   urbano, com modalidade e comprimento resolvidos.
4. Modelar condutor multiplex e ancoragem como regras somente se os fatos correspondentes forem
   extraídos; caso contrário documentar candidatos e deixar `NAO_AVALIAVEL`.
5. Não criar limite de ângulo para ramal sem item normativo inequívoco; registrar essa decisão.
6. Incrementar versão do registro, seed e método de conformidade; atualizar schemas/documentação.

**Prompt para uma sessão limpa:**

```text
Execute E07 — Conformidade específica do ramal em docs/roadmap-correcao-interpretacao-topologia-ramais.md. Leia AGENTS.md, roadmap e handoffs, ADR/inventário de E01, span_compliance.py, topology_compliance.py, compliance_registry.py, project_compliance.py, regras_conformidade_v1.json, schemas, docs/catalogo-regras-conformidade.md e testes de registro/análise. Verifique E05/E06 concluídas e o git; preserve alterações do usuário e marque E07 #em-andamento no índice e no detalhe.

Faça regras de rede consumirem apenas fatos de REDE_DISTRIBUICAO. Adicione a fonte oficial ND-5.1 Mar/2026 e uma regra ativa para comprimento máximo de 30 m de RAMAL_CONEXAO AEREO, urbano ou rural, somente quando modalidade e comprimento estiverem resolvidos. Não aplique ao ramal a matriz estrutura–cabo ou o ângulo de equipamento da rede. Só ative requisitos de cabo multiplex/ancoragem se os fatos positivos existirem; caso contrário deixe-os documentados e NAO_AVALIAVEL. Não invente limite de ângulo nem reproduza conteúdo ABNT protegido. Incremente de forma coerente registro, seed e método e atualize inventário, catálogo e schemas. Teste ramal de 10/23/30 m conforme, 30,01 m divergente, modalidade desconhecida não avaliável, e regressões de rede. Execute as validações; não conclua com falha ou omissão. Ao aceitar, marque E07 #concluida nos dois locais e registre Evidências e handoff. Se bloqueada, documente causa/evidência/impacto/ação. Não faça commit ou ação externa. Resuma.
```

**Critérios de aceite:**

- [ ] Ramais de 10 m, 23 m e 30 m não geram divergência de comprimento; 30,01 m gera quando aéreo.
- [ ] Modalidade ou comprimento desconhecido resulta `NAO_AVALIAVEL`, não conformidade presumida.
- [ ] Nenhuma regra de rede de vão, ângulo ou compatibilidade consome ramal.
- [ ] Fonte, localizador, revisão e paráfrase da ND-5.1 são auditáveis no registro e documentação.
- [ ] Versões e snapshots antigos não são confundidos com o novo método.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_span_compliance_provider.py tests\unit\test_compliance_registry.py tests\unit\test_compliance_catalog_parity.py tests\integration\test_compliance_registry_persistence.py tests\integration\test_compliance_analysis.py tests\integration\test_compliance_visibility.py
.\.venv\Scripts\python.exe -m mypy
```

Resultado esperado: todos passam; cenários de limiar e não avaliabilidade ficam explícitos.

**Bloqueios:** ativar condutor/ancoragem fica bloqueado apenas se os fatos não puderem ser extraídos;
isso não bloqueia a regra de 30 m nem a exclusão das regras de rede.

**Riscos e mitigação:** regra duplicada com o limite genérico de vão; mitigar por tipo de trecho nas
duas aplicabilidades. Fonte mudar; mitigar registrando hash/revisão de E01.

**Evidências e handoff:** ainda não iniciado.

## E08 — Contratos, cliente e exportações — #pendente

**Objetivo:** expor tipo do vão/ponto e alteração escolhida em E01 de forma coerente no contrato,
servidor, painel Resultados e planilhas, sem derivação semântica no cliente.

**Por que agora:** depende dos conceitos estabilizados em E04/E05/E07 para não publicar contrato
transitório.

**Dependências e paralelismo:** E04, E05 e E07 concluídas. Não executar em paralelo com E09.

**Escopo:** `zeny_project_handler_contracts/enums.py`, `review.py`, servidor `review_api.py`, cliente
`review_panel.py`, `deliverable_exports.py`, OpenAPI, inventário de paridade, documentação funcional e
testes de contrato/servidor/UI/exportação.

**Fora de escopo:** nova heurística de análise e redesenho geral do painel.

**Passos de implementação:**

1. Adicionar enum/fields fechados para tipo e rótulo do vão; expor endpoint de entrega com rótulo
   inequívoco.
2. Propagar a representação de alteração definida no ADR por contrato, filtros, resumos, overlays e
   exportação, mantendo compatibilidade/versionamento previsto.
3. Acrescentar coluna **Tipo** à tabela/planilha de vãos e endpoint `Padrão do cliente` no início/fim.
4. Garantir que árvore do ponto de padrão não liste estruturas/equipamentos do poste real.
5. Atualizar OpenAPI, documentação e testes de paridade; cliente não pode recalcular tipo.

**Prompt para uma sessão limpa:**

```text
Execute E08 — Contratos, cliente e exportações em docs/roadmap-correcao-interpretacao-topologia-ramais.md. Leia AGENTS.md, roadmap/handoffs, ADR E01, os modelos em src/zeny_project_handler_contracts, review_api.py, review_panel.py, deliverable_exports.py, OpenAPI e testes de contrato/API/UI/exportação. Confirme E04, E05 e E07 concluídas, examine git status e preserve mudanças preexistentes. Marque E08 #em-andamento no índice e no detalhe.

Exponha pelo servidor o tipo fechado de vão e seu rótulo, identifique endpoint ENTREGA como Padrão do cliente e propague a representação pública de alteração definida pelo ADR. O cliente deve apenas apresentar esses campos. Inclua Tipo na tabela de vãos e na planilha Resultados/Vãos, ajuste filtros/resumos/overlays e impeça que a árvore do padrão mostre elementos do poste vizinho. Atualize contratos, serialização HTTP, snapshot OpenAPI, inventário de paridade e documentação funcional de modo atômico. Cubra consumidores antigos conforme a estratégia de compatibilidade do ADR. Execute todos os testes; não conclua com obrigatório falhando ou não executado. Depois do aceite, marque E08 #concluida nos dois locais e preencha Evidências e handoff. Em impedimento real, use #bloqueada com detalhes acionáveis. Não faça commit, push, publicação ou implantação. Finalize com resumo conciso.
```

**Critérios de aceite:**

- [ ] DTO/OpenAPI distinguem rede, ramal e desconhecido; cliente não deriva o valor.
- [ ] Endpoint de entrega aparece como `Padrão do cliente`, não `-` ou poste.
- [ ] Redução de vão não aparece `A remover` e sua alteração é visível conforme ADR.
- [ ] Tabela e XLSX possuem coluna Tipo; valores coincidem com a sessão do servidor.
- [ ] Estruturas/equipamentos não aparecem sob o nó do padrão incorreto.
- [ ] Contratos, API, cliente e exportação têm testes de paridade.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\contracts\test_models.py tests\contracts\test_openapi_snapshot.py tests\server\test_review_api.py tests\server\test_deliverable_exports.py tests\e2e\test_span_compliance_ui.py tests\integration\test_review_panel.py
.\.venv\Scripts\python.exe -m mypy
```

Se algum caminho de teste citado tiver sido renomeado antes da etapa, localizar o teste equivalente
com `rg --files tests` e registrar o comando real. Resultado esperado: todos os testes equivalentes
passam e o snapshot OpenAPI contém apenas as mudanças planejadas.

**Bloqueios:** nenhum após as dependências. Uma mudança incompatível não prevista exige registrar a
estratégia no ADR e atualizar este roadmap antes de prosseguir.

**Riscos e mitigação:** quebrar cliente antigo ao adicionar enum; mitigar com a estratégia de versão
do ADR e teste de contrato. Desalinhamento XLSX/UI; mitigar projetando ambos do mesmo DTO canônico.

**Evidências e handoff:** ainda não iniciado.

## E09 — Gate integrado e homologação dos exemplos — #pendente

**Objetivo:** provar a definição global de pronto no gate versionado e nos dois PDFs locais, revisar
visualmente resultados/callouts e deixar documentação/handoff final reproduzíveis.

**Por que agora:** é o gate de integração após todas as mudanças funcionais.

**Dependências e paralelismo:** E02–E08 concluídas. Etapa final, sem paralelismo de edição.

**Escopo:** testes regressivos, documentação já afetada, versões/assinaturas, execução local dos dois
exemplos e `IniciarTestes.bat`.

**Fora de escopo:** corrigir defeito novo não relacionado sem antes adicionar etapa própria ao
roadmap; publicar ou implantar.

**Passos de implementação:**

1. Auditar a matriz da definição global de pronto nos testes sintéticos e remover lacunas/duplicação.
2. Executar análise completa dos PDFs locais, inspecionar DTOs e callouts dos pontos/vãos citados e
   registrar contagens e resultados técnicos sem dados pessoais.
3. Confirmar por hash/tamanho/data que os PDFs não mudaram.
4. Executar smoke, testes dirigidos e gate completo; resolver apenas regressões dentro do escopo.
5. Revisar versões, inventários, OpenAPI, documentação e estados deste roadmap; registrar qualquer
   limitação residual como risco explícito, não como sucesso implícito.

**Prompt para uma sessão limpa:**

```text
Execute E09 — Gate integrado e homologação dos exemplos do roadmap docs/roadmap-correcao-interpretacao-topologia-ramais.md. Leia AGENTS.md, o roadmap inteiro, todos os handoffs, ADR E01, README.md, documentação normativa/funcional e git status. Verifique que E02–E08 estão realmente #concluídas e que o código não divergiu; preserve alterações preexistentes. Marque E09 #em-andamento no índice e no detalhe.

Confira que cada item da definição global de pronto possui regressão sintética. Execute análise completa e somente leitura de examples/PROJETO DE REDE - 1255651475.pdf e examples/PROJETO DE REDE - 1255839633.pdf. Valide tecnicamente, sem registrar PII: cabo principal alterado e não removido, 269 m vigente/321 m substituído, V1-2 e V4-5 como ramais, P1/P5 como pontos de entrega, chaves 2H/5H a instalar, N(2), duas CM3 e duas S3R, e ausência dos falsos callouts de fim/transição, ângulo e compatibilidade. Confirme hash/tamanho/mtime antes e depois. Rode scripts/smoke_examples.py, as suítes dirigidas e IniciarTestes.bat. Não declare sucesso com teste falhando, não executado ou exemplo não inspecionado; se examples/ não estiver disponível, marque E09 #bloqueada e indique que os testes sintéticos passaram mas a homologação real exigida está pendente.

Atualize documentação, versões e o roadmap apenas se necessário para refletir o estado real. Quando todos os critérios e gates passarem, marque E09 #concluida no índice e no detalhe e preencha Evidências e handoff com arquivos, comandos, resultados e limitações. Se houver impedimento, use #bloqueada com causa, evidência, impacto e ação de desbloqueio. Não crie commit, não publique e não implante. Entregue resumo final conciso de mudanças, validações e pendências.
```

**Critérios de aceite:**

- [ ] Cada item da definição global de pronto possui teste sintético e resultado local correspondente.
- [ ] Ambos os PDFs passam a matriz esperada e permanecem byte a byte inalterados.
- [ ] Nenhum falso callout citado pelo usuário permanece; verdadeiros positivos de controle permanecem.
- [ ] Smoke, suítes dirigidas e gate completo passam sem teste obrigatório omitido.
- [ ] Roadmap, ADR, inventários, catálogo de regras, OpenAPI e README/especificação estão coerentes.

**Validação obrigatória:**

```powershell
.\.venv\Scripts\python.exe scripts\smoke_examples.py
.\.venv\Scripts\python.exe -m pytest -q tests\unit\test_rule_based_interpreter.py tests\unit\test_spans.py tests\unit\test_span_compliance_provider.py tests\unit\test_topology_compliance.py tests\unit\test_topology_path_compliance.py tests\integration\test_interpretation_pipeline.py tests\integration\test_compliance_analysis.py tests\contracts\test_openapi_snapshot.py tests\server\test_review_api.py
.\IniciarTestes.bat
```

Resultado esperado: códigos de saída zero, nenhuma alteração nos PDFs e inspeção visual/DTO conforme
a matriz. Aviso de cache do Pytest deve ser registrado e corrigido se comprometer o gate, mas não é
sozinho evidência de falha funcional.

**Bloqueios:** os dois PDFs locais são obrigatórios para a homologação final, embora nunca sejam
versionados. Ausência deles bloqueia somente E09 e deve ser resolvida recolocando as cópias locais
autorizadas em `examples/`.

**Riscos e mitigação:** smoke atual verifica contagens, não semântica; mitigar com inspeção dos DTOs e
callouts e registrar o procedimento/comando no handoff. Corrigir nova regressão ampliando escopo;
mitigar criando etapa adicional com ID novo antes de editar comportamento não planejado.

**Evidências e handoff:** ainda não iniciado.
