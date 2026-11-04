# Roadmap — Leitura vetorial por poste

> Arquivo: `docs/roadmap-leitura-vetorial-por-poste.md` · branch de execução: `roadmap/leitura-vetorial-por-poste` · criado em 2026-10-30 · última revisão 2026-11-03

## Como usar

Inicie uma sessão limpa do Claude Code na raiz do repositório com `claude --agent orquestrador` e cole o "Prompt de execução". Ele executa até 3 etapas em sequência na branch `roadmap/leitura-vetorial-por-poste`, cada uma planejada pelo plugin superpowers e executada pelas souls (subagentes do Second Brain), e para para revisão. No fim do lote você decide como integrar a branch (merge, PR, manter ou descartar). Para não parar em cada pedido de permissão, libere antes os comandos de build/teste do projeto nas permissões do Claude Code.

## Objetivo

A análise entrega, para cada poste da folha, a ficha correta: identificador, estrutura, poste, coordenada UTM, vãos e símbolos associados. Isso vale para as quatro famílias de PDF observadas. A leitura parte do vetor como desenho, com texto em contorno lido por forma, e não por OCR. Coordenadas e vãos são conferidos pela geometria UTM. Um detector visual local treinado cobre o resíduo. A precisão é medida por poste, contra referência congelada.

## Contexto confirmado

- **Stack:** Python 3.11–3.13; servidor FastAPI + SQLite/Alembic + PyMuPDF + Tesseract; cliente PySide6 (`pyproject.toml`, `CLAUDE.md`).
- **Design:**
  - `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md`, fonte deste roadmap;
  - `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md`;
  - `docs/adr/0017-detector-visual-local-e-rotulagem-assistida.md`.
- **Estrutura relevante:**
  - `src/zeny_project_handler/adapters/analysis/`: analisador PyMuPDF, OCR, detectores e `symbol_packages/`;
  - `src/zeny_project_handler/ports/analysis.py`: `AnalisadorDocumentoPort`, `MetodoSimbolosPort`, `ExtratorComplementarPort`;
  - `src/zeny_project_handler/application/`: `interpretation_pipeline.py`, `analysis_regions.py` (já produz `CoordenadaCampo` UTM), `symbol_reconciliation.py`, `spans.py`, `human_review.py`.
- **Curadoria:**
  - skill `.claude/skills/curadoria-simbologia/SKILL.md`, agentes `.claude/agents/curadoria-*.md` e contrato `docs/fluxo-curadoria-incremental-simbologia.md`;
  - os CLIs `scripts/curation_*.py` usam `benchmark_symbols`, `benchmark_network_pdf` e `symbol_benchmark_evaluator`;
  - o fechamento da skill usa `benchmark_transformers_e05`, `benchmark_guys_e06`, `benchmark_packages_e07`, `benchmark_review_e14`, `curation_coverage_e16` e `coverage_matrix_e16` (verificado por grep em 2026-10-30).
- **Comandos confirmados** (fonte: `CLAUDE.md`, `IniciarTestes.bat`):
  - gate completo `.\IniciarTestes.bat` (Git Bash: `cmd.exe //c IniciarTestes.bat`), que termina com `RESULTADO FINAL: APROVADO`;
  - `.venv/Scripts/python.exe -m pytest` (aceita arquivo ou `arquivo::teste`), `-m ruff check .`, `-m mypy`;
  - `scripts/complexity_gate.py src`, `scripts/client_artifact_gate.py --source-only`, `scripts/generate_openapi_v1.py`, `scripts/smoke_examples.py`.
- **Dados locais:** `examples/` tem 16 PDFs de uma página (8 Electric Office via Print To PDF, 6 iText, 1 Ghostscript, 1 AutoCAD com 11 OCGs), ignorados pelo Git e todos já vistos no desenvolvimento.
- **Second Brain:** o projeto não está registrado (não há hub nem hook). O bloco "Second Brain" do protocolo não se aplica até o registro.

## Escopo

**Incluído:** fases F0–F7 do design:
- limpeza;
- medição por poste;
- modelo de desenho e texto por glifo;
- símbolos e ficha do poste;
- conferência UTM;
- troca do analisador e remoção do legado;
- fábrica de rótulos;
- detector visual local;
- atualização das dependências vulneráveis (E13, decisão D3).

**Fora de escopo:**
- gerar DWG;
- Claude chamado pelo servidor;
- mudanças em conformidade, exportação, portabilidade e cliente, além de campos aditivos para mostrar pendências da ficha;
- novas regras normativas.

## Restrições e invariantes

- Arquitetura hexagonal:
  - domínio e aplicação não importam PyMuPDF, ONNX Runtime nem ezdxf;
  - o cliente não importa nada do servidor (`client_artifact_gate`);
  - DTOs seguem `tests/contracts/test_architecture.py`.
- A saída da análise continua sendo `EvidenciaDocumento` e `PropostaElemento`/`PropostaRelacao`. A ficha do poste não é entidade persistida nova, e nenhuma migração SQLite é feita sem etapa que a justifique.
- Mudança de comportamento de saída incrementa a versão do extrator ou do interpretador correspondente (ADR 0006).
- Mudança de API só por campos aditivos, com `docs/api/openapi-v1.json` regenerado.
- PDFs reais, recortes, rótulos, conjuntos de dados e pesos treinados nunca entram no Git. Todo comportamento novo tem fixture sintética positiva e negativa.
- Leitura de avaliação é sempre cega, sem predições à vista. Pré-marcação vale só para o conjunto de treino. O conjunto de avaliação nunca alimenta o treino.
- Pytest roda com `--strict-markers` e trata `ResourceWarning` como erro: feche documentos PyMuPDF e arquivos.
- Documentação enxuta: nada de histórico de execução em arquivo versionado. Atualize só o que a mudança torna falso (`CLAUDE.md`, contrato de curadoria, especificação funcional).
- Dependências novas: ONNX Runtime e ezdxf só em locks do servidor, de desenvolvimento ou de experimentos, nunca no cliente nem no runtime sem consumidor. Treino com lock próprio e opt-in. Licença Apache-2.0, BSD ou MIT; YOLO Ultralytics (AGPL) está excluído.

## Hipóteses e decisões em aberto

| # | Hipótese ou decisão | Impacto se errada / sem decisão | Etapa afetada |
|---|---|---|---|
| H1 | Nas famílias sem texto nativo, cada forma pequena preenchida é um glifo de fonte fixa | a leitura por assinatura precisa segmentar glifos compostos ou tolerar variação de curva | E05 |
| H2 | Os símbolos da rede são vetoriais em todas as famílias | símbolos rasterizados vão direto para o resíduo do detector (E12) | E06 |
| H3 | As imagens das folhas Print To PDF e iText são só ladrilhos da ortofoto. Resultado da E04: os ladrilhos são só ortofoto e nenhum símbolo é raster, mas as folhas iText trazem tabelas (CHI, servidão, APP) como imagem e a folha Ghostscript traz um rótulo de poste em imagem de anotação | se carregarem símbolos ou texto, o OCR não pode sair em E09 — há texto em raster: a E09 precisa tratá-lo ou declará-lo fora da ficha | E04, E09 |
| H4 | O usuário reserva folhas novas, ainda não vistas, para o conjunto de avaliação antes de E09 | sem elas, E09 não tem prova cega e fica bloqueada | E09 |
| H5 | PyTorch com ROCm treina na RX 9070 XT desta máquina (Windows nativo ou WSL2) | o treino cai para CPU ou para GPU alugada (D1) | E11 |
| D1 | Treinar em GPU alugada por hora, se ROCm e CPU forem inviáveis | sem decisão, E12 só treina em CPU | E12 (só se E11 concluir que o treino local é inviável) |
| D2 | Decidido em 2026-11-02: a ficha predita vem do projeto promovido (R2 da E02), e o formato v1 e o casamento guloso 0,02/0,05 são mantidos, com calibração na E03 | se a E03 pedir outra fonte, entra nova `versao_extracao` no `gerador` | E03 |
| D3 | Decidido em 2026-11-02: uma etapa própria de atualização de dependências entra antes da E03, com prioridade para o Pillow do lock do servidor. Criada como E13 | sem ela, a E03 roda sobre locks com vulnerabilidades conhecidas | E13, E03 |
| D4 | Decidido em 2026-11-02: o usuário libera os agentes `curadoria-*` do projeto na soul `orquestrador` (lista de subagentes e pré-condição), para a leitura dupla cega da E03 rodar na sessão do orquestrador | sem isso, a E03 não roda pelo protocolo | E03 |
| D5 | Recomendado em 2026-11-04 (E03), pendente de confirmação do usuário: a ficha predita ganha uma `versao_extracao` a partir das propostas, porque o projeto promovido não tem postes nas folhas reais (baseline 0/107) | sem ela, a E07 não tem baseline informativo para comparar | E07 |

## Definição global de pronto

- [ ] O benchmark por poste, no conjunto de avaliação cego, mostra o analisador novo ≥ o atual em todas as métricas, sem regressão por folha não justificada.
- [ ] O analisador novo é o padrão do servidor, e os detectores substituídos foram removidos.
- [ ] Fichas com conferência UTM divergente aparecem como pendência de revisão, nunca como valor confiável.
- [ ] A fábrica de rótulos processa um lote mensal com taxa de erro de rótulo medida.
- [ ] O detector local está integrado com pesos versionados por hash, ou E11 registrou por que ainda não.
- [ ] `.\IniciarTestes.bat` termina com `RESULTADO FINAL: APROVADO`.

## Protocolo de execução

Vale para toda execução deste roadmap. O planejamento e a execução de cada etapa são feitos pelo plugin superpowers; este protocolo diz como encadear as etapas e manter o roadmap em dia.

**Papéis**

| Papel | Soul | Usa |
|---|---|---|
| Orquestrador | `orquestrador` (a sessão principal, iniciada com `claude --agent orquestrador`) | este protocolo; atualiza tags e handoffs; roda a verificação mecânica dos testes |
| Planejador | `orquestrador` | `superpowers:writing-plans` |
| Implementador | `desenvolvedor`, subagente por tarefa | `superpowers:subagent-driven-development`, prompt implementer |
| Testador | `testador`, subagente por tarefa, depois do implementador | testes da tarefa, sem tocar em código de produção |
| Revisor de plano | `revisor-arquitetura`, subagente novo por etapa, modelo mais capaz | revisão do plano antes da execução |
| Revisor de tarefa | `revisor-seguranca`, subagente novo por tarefa | revisão da `subagent-driven-development` |
| Revisor final | `revisor-seguranca`, subagente novo, modelo mais capaz | revisão final da `subagent-driven-development` |
| Captura no brain | `brain-escriba` | publica a captura de atualização em `00 Inbox/` |

Souls: este protocolo exige `orquestrador`, `desenvolvedor`, `testador`, `revisor-seguranca` e `revisor-arquitetura`. Não há fallback: se a sessão não roda como `orquestrador` ou alguma dessas souls não está instalada, pare e diga ao usuário para configurar a máquina (skill `configurar-maquina`) ou iniciar com `claude --agent orquestrador`. O caminho inline (`superpowers:executing-plans`) não vale aqui.

**Branch**

- Toda execução acontece no worktree/branch `roadmap/leitura-vetorial-por-poste`, criado ou retomado com `superpowers:using-git-worktrees`. Nunca execute na branch principal.
- Se a branch já existir com trabalho não integrado, continue nela. Se o lote anterior já foi integrado, crie a branch de novo a partir da branch principal atualizada.
- Este roadmap é atualizado dentro da branch: tags e handoffs viajam com o código.
- Os PDFs de `examples/` e os artefatos de `tmp/` são ignorados pelo Git e não existem no worktree. Etapas que leem folhas reais apontam para o `examples/` do checkout principal, só para leitura, e gravam rodadas no `tmp/` dele.

**Por etapa**

1. **Escolha:** a primeira etapa, na ordem do documento, marcada `#pendente` e com todas as dependências `#concluida`. Etapas `#bloqueada` e as que dependem delas ficam para trás.
2. **Conferência:** leia a seção da etapa, os handoffs das dependências e o código que eles citam. Se o código divergiu do que a etapa supõe, pare e relate.
3. **Início:** troque a tag para `#em-andamento` (índice e título).
4. **Plano:** use `superpowers:writing-plans`. A spec é a seção desta etapa mais o design citado em "Contexto confirmado"; as "Restrições e invariantes" entram como Global Constraints. Salve em `docs/superpowers/plans/AAAA-MM-DD-leitura-vetorial-por-poste-eNN.md`. Antes de executar, o plano passa pela revisão de arquitetura do `orquestrador` (`revisor-arquitetura`); as regras (rodadas, veredito, seção no plano) vivem só nele. A execução já está definida (abaixo): não pergunte ao usuário o método, apenas siga.
5. **Execução:** use `superpowers:subagent-driven-development` com esse plano, executado pelas souls conforme o ciclo por tarefa, a verificação mecânica dos testes e a revisão final da etapa definidos no `orquestrador` (as regras de encaixe vivem só nele). Não invoque `superpowers:finishing-a-development-branch` ao fim da etapa: ele roda uma vez, no fim do lote.
6. **Fechamento:** publique a captura de atualização do brain, se o bloco "Second Brain" se aplica. Marque `#concluida` (índice e título) só com a revisão final limpa e cada critério de aceite verificado com evidência. Diante de impedimento real, marque `#bloqueada` e preencha "Bloqueios" com causa, evidência, impacto e ação de desbloqueio. Preencha "Evidências e handoff". Rulings do ledger que mudam contrato, escopo, segurança, dados ou algo caro de desfazer vão para "Decisões para o usuário".

**Second Brain**

Vale se o `CLAUDE.md` tiver a seção "Conhecimento do projeto no Second Brain"; senão, ignore este bloco.

- O contexto da sessão precisa trazer a linha `BRAIN: carregado (ZenyProjectHandler)`, injetada pelo hook. Sem ela, pare e relate.
- Na conferência de cada etapa, leia as notas de tema do brain ligadas a ela e as capturas pendentes do projeto que tratem do assunto: são a referência técnica do projeto.
- No fechamento de cada etapa que mudou algo descrito no brain (inclusive o estado do roadmap), o orquestrador manda o `brain-escriba` publicar em `00 Inbox/` do vault a captura `ZenyProjectHandler - atualização leitura-vetorial-por-poste Eyy`, com o texto novo ou alterado de cada nota afetada e qual nota ele substitui ou complementa; o contrato de agente externo do vault fica com o `brain-escriba`. Nunca edite notas do brain nem registre referência técnica no `CLAUDE.md`.

**Paradas**

O lote para ao concluir uma etapa com **Revisão humana: sim**, diante de etapa `#bloqueada` ou divergência do plano, nas paradas do próprio superpowers (operação destrutiva, ação sensível de segurança, efeito fora da branch, plano sem caminho viável) e ao atingir o limite de etapas do prompt.

**Fim do lote**

1. Use `superpowers:finishing-a-development-branch`: o usuário decide merge, PR, manter ou descartar a branch. Nunca faça push, merge ou deploy sem essa decisão.
2. Apresente as "Decisões para o usuário" acumuladas como entrevista: perguntas de múltipla escolha, cada uma com uma opção recomendada e justificada (no Claude Code, `AskUserQuestion` com a recomendada em primeiro lugar e o rótulo "(Recomendado)"). Registre as respostas no handoff das etapas e em "Hipóteses e decisões em aberto".

## Prompt de execução

```text
Execute o roadmap docs/roadmap-leitura-vetorial-por-poste.md deste repositório seguindo a seção "Protocolo de execução" dele, com o plugin superpowers.

Limite desta execução: no máximo 3 etapas concluídas.

1. Confira a pré-condição do protocolo: esta sessão roda como orquestrador e as souls desenvolvedor, testador, revisor-seguranca e revisor-arquitetura estão disponíveis; se não, pare e diga como resolver. Leia CLAUDE.md (e AGENTS.md, se existir) e, no roadmap, o cabeçalho inteiro, o protocolo e o índice. Se o CLAUDE.md exigir o Second Brain, confira a linha BRAIN: carregado no contexto e leia o hub. Rode git status e git branch -a.
2. Se alguma etapa estiver #em-andamento, retome-a a partir do ledger do superpowers e do handoff; não recomece tarefas já commitadas.
3. Crie ou retome o worktree/branch roadmap/leitura-vetorial-por-poste com superpowers:using-git-worktrees. Não trabalhe na branch principal.
4. Repita, uma etapa por vez: escolha a próxima etapa elegível, marque #em-andamento, planeje com superpowers:writing-plans (spec = seção da etapa + design citado), execute com superpowers:subagent-driven-development, feche a etapa e preencha o handoff conforme o protocolo.
5. Pare nas paradas do protocolo ou ao atingir o limite.
6. No fim, rode superpowers:finishing-a-development-branch e deixe a decisão de integração comigo. Depois, apresente as decisões para o usuário como entrevista com opção recomendada.

Nunca faça push, merge ou deploy sem minha decisão. Não altere tags de etapas que não executou.

Ao parar, responda com: etapas concluídas e o resultado da revisão final de cada uma, a etapa atual e seu estado, o motivo da parada, as etapas #bloqueada com a ação de desbloqueio, a branch e os commits do lote e o próximo passo sugerido.
```

## Índice de etapas

Bloco A — base e medição

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Limpeza do projeto | #concluida | — | scripts, testes e docs de etapas encerradas removidos, gate verde |
| E02 | Ficha de referência e benchmark por poste | #concluida | E01 | formato da ficha, avaliador por poste e baseline sintético |
| E13 | Atualização de dependências vulneráveis | #concluida | E01 | locks sem vulnerabilidade corrigível nos pacotes apontados pelo scanner, gate verde |
| E03 | Rotulagem v0 e baseline real | #concluida | E02, E13 | fichas de referência das 16 folhas e baseline do analisador atual em `tmp/` |

Bloco B — leitura vetorial

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E04 | Modelo de desenho e perfis de família | #concluida | E01 | modelo de desenho por página, perfil por família e DXF de depuração |
| E05 | Texto por contorno de glifo | #pendente | E04, E03 | tabela de glifos e texto recuperado sem OCR nas 4 famílias |
| E06 | Símbolos sobre o modelo de desenho | #pendente | E05 | pacotes declarativos avaliados sobre o modelo vetorial |
| E07 | Ficha do poste | #pendente | E06 | associação texto/símbolo/vão → poste, benchmark acima do baseline |
| E08 | Conferência UTM | #pendente | E07 | transformação página → UTM, checagem de posição e vão, pendências |
| E09 | Troca do analisador e remoção do legado | #pendente | E08 | analisador novo como padrão; detectores e, se provado, OCR removidos |

Bloco C — aprendizado

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E10 | Fábrica de rótulos contínua | #pendente | E07 | fluxo mensal com pré-marcação, leitura dupla, amostra humana e dataset por hash |
| E11 | Spike de treino na GPU AMD | #pendente | E10 | decisão registrada sobre onde e como treinar |
| E12 | Detector visual local | #pendente | E11, E09 | detector ONNX em CPU para o resíduo, ganho medido por poste |

---

## E01 — Limpeza do projeto — #concluida

**Objetivo:** remover do repositório o que pertence a etapas encerradas, sem mudar o comportamento do produto.

**Por que agora:** o usuário pediu a limpeza como primeira etapa. Ela reduz o contexto que todas as etapas seguintes leem.

**Dependências:** nenhuma.

**Escopo:**
- **Scripts sem uso pelo fluxo vivo, com seus testes:** `benchmark_method_reconciliation`, `benchmark_network_alternatives`, `benchmark_reserve_e16`, `benchmark_reserve_e16r2`, `stage10_operational_gate`, `stage11_client_matrix`, `stage11_parity_gate`, `stage12_release_gate`, `visual_qa_review_highlights` e `scripts/experiments/` inteiro, com o que só ele usa no `requirements-experiments.lock`.
- **Roadmap encerrado:** `docs/roadmap-curadoria-simbologia-paralela.md`. A E11 dele fica sem efeito, porque o detector que a bloqueava será substituído.
- **README:** perde o histórico narrativo de etapas e fica com uso e operação.
- **Referências:** `CLAUDE.md`, `.claude/settings.json` (allow-list) e `examples/README.md` ajustados para não citar nada removido.

**Fora de escopo:**
- scripts usados pela skill de curadoria ou pelos CLIs `curation_*`: `benchmark_symbols`, `benchmark_network_pdf`, `symbol_benchmark_*`, `benchmark_transformers_e05`, `benchmark_guys_e06`, `benchmark_packages_e07`, `benchmark_review_e14`, `benchmark_semantic_e13`, `reconcile_symbol_benchmark`, `curation_coverage_e16`, `coverage_matrix_e16` e `audit_symbol_packages`, revistos em E03 e E09;
- código de `src/`;
- ADRs.

**Critérios de aceite:**

- [x] `git grep -n` por cada nome removido não encontra referência fora do histórico de revisões deste roadmap.
- [x] `build_release.py` e os gates `release_artifact_gate`, `server_artifact_gate` e `client_artifact_gate` continuam funcionando, ou o plano provou que não dependiam dos removidos.
- [x] `.\IniciarTestes.bat` termina com `RESULTADO FINAL: APROVADO`, com a cobertura mínima mantida. Prova: o gate equivalente passou, e o usuário rodou o `.bat` na branch em 2026-11-02, já com a E02, com `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- `.venv/Scripts/python.exe scripts/client_artifact_gate.py --source-only` → aprovado.

**Revisão humana:** não

**Notas para o plano:**
- Antes de apagar, confira com grep quem importa cada script. `stage12_release_gate` é citado em `tests/unit/test_project_scripts.py`, e pode haver gate de release que dependa da cadeia `stage1N`. Se algo vivo depender dele, mantenha-o e registre no handoff.
- Remover testes pode baixar a cobertura abaixo de 85,01%. Confira o efeito antes de concluir.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Remover um script que um gate de release usa indiretamente → o gate completo e um `build_release.py` de ensaio, se o plano julgar seguro, detectam a quebra.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-02-leitura-vetorial-por-poste-e01.md`, revisão de arquitetura aprovada com notas na rodada 1 (seção "Revisão de arquitetura" do plano).
- Commits:
  - plano: 8c381a6, e942afc, 003d42f, e398c02;
  - Task 1: 3488ad8, ac4f6e6 (experimentos e benchmarks dependentes);
  - Task 2: 1ea736f (harnesses de reserva, gates `stage1N` e QA visual);
  - Task 3: cad3834 (README, CLAUDE.md, roadmap encerrado);
  - correção final: 732471e (pin órfão de `scipy`).
- Revisão final: `revisor-seguranca` (opus), aprovado com ressalvas, sem Crítico nem Importante de código em aberto depois da onda única de correção.
  - O Importante de supply chain era o pin órfão de `scipy`; foi removido.
  - Ficam opcionais estes Menores:
    - narrativa de etapa em `docs/especificacao-funcional.md` (seção de homologação);
    - o termo "composição vertical" no README;
    - o ZIP "autocontido", que deixou de ter verificação dinâmica.
- Critérios verificados:
  - (1) `git grep` dos nomes removidos, fora deste roadmap, de `docs/superpowers/specs/` e de `docs/superpowers/plans/` → sem ocorrência.
  - (2) `build_release.py`, `build_client.py` e os gates `release_artifact_gate`, `server_artifact_gate` e `client_artifact_gate` não citam nenhum removido. `client_artifact_gate --source-only` aprovado e `tests/unit/test_release_build.py` verde na suíte. O ensaio de `build_release.py` não foi executado: exige Docker e PyInstaller.
  - (3) Gate equivalente ao `IniciarTestes.bat` (pip check, ruff, format, mypy, gate do cliente, pytest com cobertura e complexidade), tudo com exit 0: 2588 passed, cobertura 88,24%. O `.bat` em si não rodou, porque o harness recusa `cmd.exe` no worktree.
  - Verificação mecânica `--base 4ed342d`: 165 apontamentos, todos remoções de teste de código removido e justificados nas revisões.
- Decisões para o usuário:
  - Rodar `.\IniciarTestes.bat` no worktree antes de integrar.
  - A Task 2 removeu `stage11_parity_gate`/`stage12_release_gate` e, com eles, a validação automatizada do ZIP e do kit em host limpo. Ela pode ser recuperada do histórico do Git.
  - O scanner (`osv-scanner -L requirements.txt:<lock>` nos 6 locks) aponta vulnerabilidades pré-existentes, não introduzidas pela branch. A mais grave é Pillow 12.2.0 no lock do servidor (CVSS até 9.8, corrigido em 12.3.0/13.0.0). Também aparecem Mako 1.3.12, setuptools 80.10.2, wheel 0.45.1, httpx2 2.10.0 (limitado por `pyproject.toml` a `<2.11`) e pytest 8.4.2. Sugere-se uma etapa própria de atualização de dependências.
- Notas para a próxima etapa:
  - `allow_reserve` e as mensagens "sealed until E16" em `scripts/symbol_benchmark_evaluator.py`, além de `pywinauto` no `pyproject.toml`/lock de dev, ficam sem uso: revisar em E03/E09.
  - O `osv-scanner -r .` não reconhece os `requirements-*.lock`: use `-L requirements.txt:<arquivo>`.

---

## E02 — Ficha de referência e benchmark por poste — #concluida

**Objetivo:** definir o formato da ficha do poste de referência e um avaliador que compara fichas preditas e de referência com as métricas da decisão 7 do design.

**Por que agora:** todas as etapas seguintes provam ganho com essa métrica. O formato da ficha é o contrato que a rotulagem, o analisador e o detector vão repetir.

**Dependências:** E01.

**Escopo:**
- **Schema da ficha de referência**, com JSON Schema em `docs/schemas/` (a criar). Campos por folha: postes com identificador, estrutura, poste, coordenada, bbox normalizada e símbolos associados (classe do inventário e bbox), e vãos entre postes com comprimento e cabo. Também o escopo de anotação (completo ou regional).
- **Avaliador determinístico por poste**, com casamento de postes por proximidade e identificador. Métricas:
  - precisão e recall de poste;
  - acerto exato por campo;
  - acerto de vão;
  - precisão e recall de símbolos associados ao poste certo.
- **Extração da ficha predita a partir das propostas atuais,** para medir o analisador vigente.
- **Fixtures sintéticas** com casos de acerto, troca de associação, poste faltante e vão divergente.

**Fora de escopo:** rotular folhas reais (E03); mudar o analisador.

**Critérios de aceite:**

- [x] O schema valida uma ficha sintética completa e rejeita campo extra.
- [x] O avaliador, sobre fixtures sintéticas, produz as métricas esperadas em cada caso (acerto total, símbolo associado ao poste vizinho, poste ausente, vão errado).
- [x] Um CLI roda predição + avaliação de um PDF e grava o relatório em um diretório informado. O relatório não traz caminho absoluto nem conteúdo da folha além do necessário.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`. Prova: o gate equivalente passou, e o usuário rodou o `.bat` no worktree em 2026-11-02 com `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m pytest` nos testes novos → passam.
- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** sim

**Notas para o plano:**
- `scripts/benchmark_network_pdf.py` já mede postes, identificadores e comprimentos, e `scripts/symbol_benchmark_evaluator.py` tem `geometry_match`. Reaproveite em vez de duplicar.
- O avaliador atual recusa referência com `annotation_scope` diferente de `complete`. O novo precisa aceitar referência regional sem contar o não anotado como erro.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Um formato rígido demais força retrabalho em E07 → incluir no schema uma versão e, no avaliador, um campo para atributos extras ignorados na métrica.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-02-leitura-vetorial-por-poste-e02.md`, revisão de arquitetura aprovada com notas na rodada 1 (seção "Revisão de arquitetura" do plano).
- Commits:
  - plano: 0989bab, 10af2df, c96d629;
  - Task 1 (formato e validação): eb346e7, ca06d80, 7b6f9de, b03eef9, ede7e76;
  - Task 2 (avaliador): 010bf5b, 26e7e66, c16b2ef, 1130cba, 50eb4d4, b19898a;
  - Task 3 (CLI, ficha predita e baseline): 751c5bf, 71411bb, 9aff345;
  - correção final: 1ba82a5, 5d6f3ad.
- Entregas: `docs/schemas/ficha-poste.schema.json`, `scripts/ficha_poste.py`, `scripts/ficha_poste_avaliador.py`, `scripts/benchmark_ficha_poste.py` (`python -m scripts.benchmark_ficha_poste PDF --referencia REF --saida DIR [--native-only]`), parágrafo em `examples/README.md`.
- Revisão final: `revisor-seguranca` (opus), aprovado com ressalvas, sem Crítico nem Importante de código.
  - A onda única de correção resolveu os três Menores que protegem a E03: contagem `postes_sem_geometria`, contagem `simbolos_de_poste_fora_da_ficha` e cópia de `PROTOCOLO_FICHA`/`gerador` no relatório. Re-revisão: tudo resolvido.
  - Os demais Menores foram triados como "pode ficar" (alias sem uso, `_erro_classe` privada importada, traceback do CLI no stderr, U+200B/U+FEFF não removidos por `strip()`, `zona` em branco aceita, helpers de teste importados entre módulos).
  - Scanner (`osv-scanner -L requirements.txt:<lock>` nos 6 locks): sem dependência nova nem lock alterado na E02; vulnerabilidades pré-existentes, as mesmas da E01.
- Critérios verificados:
  - (1) `tests/unit/test_ficha_poste.py` verde: `test_ficha_completa_e_valida` e `test_campo_extra_e_recusado` (raiz, poste, vão, símbolo, coordenada e escopo).
  - (2) `tests/unit/test_ficha_poste_avaliador.py` verde: acerto total, símbolo no poste vizinho, poste ausente e vão errado.
  - (3) `tests/unit/test_benchmark_ficha_poste.py` e o adversarial verdes: o CLI grava `ficha-predita.json` e `avaliacao.json` no diretório informado, sem caminho absoluto nem nome do PDF; referência de outro PDF é recusada antes do analisador.
  - (4) Gate equivalente ao `IniciarTestes.bat` em 5d6f3ad, tudo com exit 0: 3178 passed, cobertura 88,25%. O usuário rodou o `.bat` no worktree em 2026-11-02: `RESULTADO FINAL: APROVADO`.
  - Verificação mecânica `--base 0d8d148`: 1 apontamento (o desenvolvedor acrescentou um teste em arquivo que o testador tinha tocado), julgado justificado na re-revisão.
- Baseline sintético (rede de 2 postes e 1 vão, `native_only`): postes tp 2, fp 0, fn 0; campos 2/2; vão casado, cabo 1/1, comprimento 0/1 (o analisador vigente não liga o "35m" ao cabo); símbolos fn 1 (ESTAI só na referência do teste, para fixar o caminho do FN).
- Decisões para o usuário:
  - **R2, fonte da ficha predita:** vem do projeto promovido, não das "propostas atuais" que a spec cita. Pendências não promovidas ficam fora e o recall de símbolos de suporte (estai) é 0 por construção. Mudar a fonte é uma nova `versao_extracao` no `gerador`.
  - **Formato v1:** `null` (ou lista vazia) é "ausente na folha" e conta na métrica; campo não determinado vai em `pendentes` e sai do denominador na referência (na predição, erro em campo pendente conta à parte). Classe de símbolo validada contra o inventário; `ESTRUTURA_POSTE_MT/AT` (símbolo do próprio poste) excluídas.
  - **R4, casamento de postes:** guloso determinístico (identificador igual primeiro, depois distância), limiares 0,02 e 0,05 no espaço normalizado da página, versionados em `PROTOCOLO_FICHA`; calibráveis na E03.
  - Rodar `.\IniciarTestes.bat` no worktree antes de integrar (feito pelo usuário em 2026-11-02, aprovado).
  - Respostas do usuário (2026-11-02): R2 aceita (projeto promovido); formato v1 e R4 mantidos, com calibração na E03; etapa de atualização de dependências antes da E03 (D3, criada como E13). Integração: primeiro a branch foi mantida; depois do `.bat` aprovado, o usuário pediu a integração em `main` com push.
- Notas para a próxima etapa:
  - Na E03, leia as chaves de diagnóstico da raiz da ficha predita com `.get(chave, 0)`: `postes_sem_geometria` e `simbolos_de_poste_fora_da_ficha` só aparecem quando maiores que 0; `equipamentos_sem_simbolo` conta também equipamento de poste sem geometria.
  - Um cabo com postes intermediários vira um vão só em `detectar_vaos` (comportamento do analisador): nas folhas reais, isso aparece como FN de vãos intermediários, não como erro do avaliador.
  - Fichas rotuladas a partir de texto copiado de PDF podem trazer U+200B/U+FEFF, que `strip()` não remove: normalize na rotulagem.
  - O caminho com OCR do CLI (sem `--native-only`) não tem teste no gate, porque exige Tesseract.

---

## E13 — Atualização de dependências vulneráveis — #concluida

**Objetivo:** atualizar nos locks os pacotes com vulnerabilidade conhecida e versão corrigida disponível, sem mudar o comportamento do produto.

**Por que agora:** decisão do usuário (D3). O servidor processa PDFs e imagens não confiáveis, e o lock do servidor fixa Pillow 12.2.0, com CVSS até 9.8. A E03 em diante roda o analisador sobre folhas reais.

**Dependências:** E01.

**Escopo:**
- **Pacotes apontados pelo scanner em 2026-11-02**, por lock:
  - `pillow` 12.2.0: `requirements-server.lock`, `requirements-development.lock` e `requirements-experiments.lock`;
  - `mako` 1.3.12: server e development;
  - `httpx2` 2.10.0: `requirements.lock` e development;
  - `pytest` 8.4.2: `requirements.lock` e development;
  - `setuptools` 80.10.2: `requirements.lock`, development e `requirements-client-build.lock`;
  - `wheel` 0.45.1: client-build.
- **Coerência:** limites em `pyproject.toml` (inclusive `[build-system]`) ajustados quando a versão corrigida estiver fora deles, e a mesma versão de cada pacote em todos os locks que o fixam.
- Dependências transitivas só quando a versão nova exigir.
- Pacote sem versão corrigida compatível fica registrado no handoff, com o advisory e o motivo.

**Fora de escopo:**
- atualizar pacotes sem vulnerabilidade apontada;
- trocar bibliotecas;
- dependências novas;
- mudar comportamento do produto (se uma atualização mudar a saída da análise, ela entra com a versão do extrator incrementada, conforme o ADR 0006, ou fica de fora com registro).

**Critérios de aceite:**

- [x] `osv-scanner scan source -L requirements.txt:<lock>` sobre os 6 `requirements*.lock` não lista vulnerabilidade com versão corrigida disponível em `pillow`, `mako`, `httpx2`, `pytest`, `setuptools` e `wheel`. Toda vulnerabilidade restante está no handoff, com o motivo.
- [x] `.venv/Scripts/python.exe -m pip check` → sem requisitos quebrados, com o ambiente reinstalado a partir de `requirements-development.lock`.
- [x] A imagem do servidor é construída a partir do `Dockerfile` com o `requirements-server.lock` atualizado.
- [x] `.venv/Scripts/python.exe scripts/client_artifact_gate.py --source-only` → aprovado.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- `osv-scanner` nos 6 locks, com a saída anexada à revisão final.
- `docker build` do `Dockerfile` (exige Docker; se o harness não puder rodar, o usuário roda e registra no handoff).

**Revisão humana:** não

**Notas para o plano:**
- Os locks são listas de pinos mantidas à mão, sem gerador versionado. Há testes que leem os nomes dos locks (`tests/unit/test_project_scripts.py`).
- `pyproject.toml` limita `Pillow<13`, `httpx2<2.11`, `pytest<9` e `setuptools<81` (este no `[build-system]`). Antes de alargar um limite, confira com `git log -S` por que ele foi posto.
- O `osv-scanner -r .` não reconhece os `requirements-*.lock`: use `-L requirements.txt:<arquivo>` (nota da E01).
- `pywinauto`, sem uso segundo a nota da E01, pode sair aqui se o plano provar que nada o usa. Senão, fica para a E09.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Um salto de versão maior do Pillow muda raster, overlay ou exportação → os testes de raster e exportação do gate pegam a mudança. Mudança de saída da análise exige versão do extrator incrementada, ou o pacote fica na versão corrigida mais próxima.
- A versão nova não tem wheel para a plataforma do servidor (Linux/Docker) ou do cliente (Windows) → o `docker build` e o `setup.bat` acusam. Escolha a menor versão corrigida com wheel.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-02-leitura-vetorial-por-poste-e13.md`. A revisão de arquitetura bloqueou na rodada 0 e aprovou com notas na rodada 1 (seção "Revisão de arquitetura" do plano).
- Commits:
  - roadmap e plano: 4a7f60b, c742001, 56759d4, 60bc24b;
  - Task 1 (Pillow 13.0.0, Mako 1.4.2 e guarda `tests/unit/test_dependency_locks.py`): 37bb43b, eaf09d8;
  - Task 2 (httpx2/httpcore2 2.12.0, pytest 9.0.3, saída de pywinauto/comtypes/pywin32, chaves `strict_*` no ini): f3cc587, bb3e73f, 24b1f26, 7e69852;
  - Task 3 (setuptools 84.1.0, wheel 0.46.2, altgraph 0.17.5): 8d4e138, 85fd9fa;
  - correção final: 64942c6 (`minversion = "9.0.3"`), 0c3c254 (nota no CLAUDE.md), 50373d4.
- Revisão final: `revisor-seguranca` (opus), aprovado com ressalvas, sem Crítico.
  - O Important era que um venv antigo (pytest 8) abortava com `Unknown config option: strict_config`. A onda única acrescentou `minversion`, e agora o erro diz `requires pytest-9.0.3`. A re-revisão deu os 3 achados como resolvidos.
  - Os Menores ficam como follow-up: literais de versão repetidos no teste de locks; testes de subprocesso do pytest que poderiam ir para módulo próprio; `git ls-files` sem explicação fora de um checkout git; locks e `Dockerfile` sem hash.
- Critérios verificados:
  - (1) `osv-scanner scan source -L requirements.txt:<lock>` nos 6 locks → `No issues found` (8/9/52/15/22/52 pacotes). Antes eram 343 vulnerabilidades nos 6 pacotes. Nenhuma vulnerabilidade restante.
  - (2) Venv limpo (Python 3.11.9) com `requirements-development.lock` e `-e .` → `pip check`: `No broken requirements found.`
  - (3) `docker build` do `Dockerfile` → exit 0. Dentro da imagem: Pillow 13.0.0, Mako 1.4.2 e Python 3.13.7, e `import zeny_project_handler_server` funciona.
  - (4) e (5) `cmd.exe //c ".\IniciarTestes.bat"` em 50373d4 → `RESULTADO FINAL: APROVADO`, 3299 passed, cobertura 88,24%, `GATE DO CLIENTE: APROVADO`. O `.bat` roda no worktree com o `.\`; sem ele, o `cmd` não acha o arquivo.
  - Comportamento: digest determinístico da análise nos 16 PDFs de `examples/`, rodado antes ×2 e depois. Mede o caminho nativo e os rasters entregues ao OCR (3476 chamadas, motor gravador, porque o Tesseract não está instalado no Windows). Saiu idêntico, e a versão do extrator continua 1.20.0.
  - Builds: `scripts/build_client.py` (wheel, ZIP, manifesto e SBOM) e o espelho do builder do `Dockerfile` → exit 0. `pip download` das wheels `win_amd64` (3.11, 3.12 e 3.13) e `manylinux` cp313 → exit 0.
  - Verificação mecânica `--base 53f74e2`: 2 apontamentos (o desenvolvedor estendeu o teste de locks depois do testador, como o plano manda nas Tasks 2 e 3), julgados justificados na revisão final.
- Decisões para o usuário:
  - Depois de integrar, rode `.\setup.bat` no checkout principal. O `.venv` dele ainda tem pytest 8.4.2, e o gate falha com `requires pytest-9.0.3`. O `pip install -r` não desinstala `pywinauto`, `comtypes` e `pywin32`, que ficam órfãos e inofensivos no venv antigo.
  - **altgraph 0.17.4 → 0.17.5** no lock de build do cliente. É uma transitiva exigida pela versão nova do setuptools: o altgraph 0.17.4 importa `pkg_resources`, que saiu no setuptools 82, e o PyInstaller quebrava. Fica fora da lista do scanner.
  - **pytest 9.0 ignora `--strict-markers`/`--strict-config` vindos de `addopts`** (regressão corrigida no 9.1, pytest#14442). Por isso o ini ganhou `strict_markers`, `strict_config`, `error::pytest.PytestUnknownMarkWarning` e `minversion`.
  - Não verificado em folhas reais: o pipeline de símbolos raster (`raster_symbols`, `legend_symbols`, `structural_symbols`) com Pillow 13. O cache dele já inclui `pillow_version`. A E03 mede o baseline já sobre o Pillow 13.
  - A imagem local `zeny-server:e13-check` ficou no Docker desta máquina. Pode ser removida com `docker image rm zeny-server:e13-check`.
  - Respostas do usuário (2026-11-02): altgraph 0.17.5 e chaves `strict_*`/`minversion` aceitos; pipeline raster aceito, com medição na E03 sobre o Pillow 13; integração por merge local em `main`; para a E03, o usuário libera os agentes `curadoria-*` na soul `orquestrador` (D4).
- Notas para a próxima etapa:
  - Os limites alargados (`Pillow<13`, `httpx2<2.11`, `pytest<9`, `setuptools<81`) vinham dos commits iniciais de setup (`fecc5be`, `e9e5559`, `2641ed3`), sem motivo registrado (`git log -S`).
  - A nota da E01 sobre `pywinauto` está resolvida: o pacote saiu. `allow_reserve` em `symbol_benchmark_evaluator.py` continua para a E03/E09.
  - `tests/unit/test_dependency_locks.py` guarda versão mínima, igualdade entre locks e limites dos manifestos. Na próxima correção de segurança, atualize `VERSOES_CORRIGIDAS` e os literais de setuptools/wheel do mesmo arquivo.
  - O Tesseract não está instalado no Windows desta máquina; o OCR real só existe na imagem Docker.
  - A E03 não começou. Na conferência, a sessão `claude --agent orquestrador` só expõe as souls, sem `curadoria-leitor-visual`/`curadoria-auditor-visual` e sem o `general-purpose` do modo de reserva da skill. Ela roda depois que a soul `orquestrador` oferecer esses agentes (D4).

---

## E03 — Rotulagem v0 e baseline real — #concluida

**Objetivo:** produzir fichas de referência das 16 folhas de `examples/` por leitura dupla cega com amostra humana, e medir o analisador atual contra elas.

**Por que agora:** sem a linha de base real não há como provar que a leitura vetorial melhora.

**Dependências:** E02, E13.

**Escopo:**
- **Adaptação da curadoria:** a skill `curadoria-simbologia`, os agentes `curadoria-leitor-visual` e `curadoria-auditor-visual` e o contrato `docs/fluxo-curadoria-incremental-simbologia.md` passam a produzir a ficha do poste.
- **Leitura dupla cega:** dois leitores independentes. As divergências são resolvidas por um terceiro leitor ou ficam pendentes, sem palpite.
- **Amostra humana:** o usuário confere uma amostra de fichas e a taxa de erro é registrada.
- **Baseline:** referências congeladas e o baseline do analisador atual em `tmp/`.
- **Invariante revisado:** o contrato passa a permitir que rótulos alimentem treino (ADR 0017), mantendo a leitura de avaliação cega.

**Fora de escopo:** corrigir detectores; conjunto de avaliação de folhas novas (E09); fábrica contínua (E10).

**Critérios de aceite:**

- [x] As 16 folhas têm ficha de referência congelada antes de qualquer comparação, com escopo de anotação declarado.
- [x] A amostra conferida pelo usuário e a taxa de erro de rótulo estão registradas no relatório local.
- [x] O baseline por poste do analisador atual existe em `tmp/` com denominadores.
- [x] Nenhuma ficha, recorte ou nome de folha entrou em arquivo versionado (`git grep -n "PROJETO DE REDE NS"` vazio).
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- Inspeção manual: o usuário confere a amostra de fichas sobre os recortes renderizados.

**Revisão humana:** sim

**Notas para o plano:**
- Os leitores e auditores são subagentes. Por isso, a leitura roda na sessão de nível superior, que é o orquestrador, como já fazia a curadoria anterior.
- Os PDFs ficam no `examples/` do checkout principal, não no worktree.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Taxa de erro alta da leitura por IA → aumentar a amostra humana e registrar. O baseline vale com o erro declarado.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-03-leitura-vetorial-por-poste-e03.md`. A revisão de arquitetura bloqueou nas rodadas 0 e 1 e aprovou com notas na rodada 2 (seção "Revisão de arquitetura" do plano).
- Estado em 2026-11-04 (3ª sessão): **execução operacional feita e etapa fechada.** Rodada local `tmp/curadoria-simbologia/20261103-2300-fichas/` do checkout principal, com `relatorio.md` completo (concordância, consolidação, calibração R4, taxa, baseline, pendências).
- Commits:
  - roadmap e plano: 6b26843, 9aa127f, b301975, 1d1411e, 97ac1f3;
  - Task 1 (validar/congelar, `tiles_nao_cobertos`, allow novo): 3ea49b1, 4a180a5;
  - Task 2 (comparar A × B, regiões de conferência): 9053dc9, 1c459ca, b0478f4, bfcede6, d58063f;
  - Task 3 (consolidar sem palpite): a96e7ac, a78d25a, 95d3da1, 51c779c;
  - Task 4 (baseline por poste): 3c1cea4, 391d34f, 2911f81, d80d324;
  - Task 5 (amostra humana, responder, taxa): 0c5af8c, 231a1a6;
  - Task 6 (leitor em modo ficha, skill, contrato, CLAUDE.md): 36822f2, 929ac98;
  - onda de correção final (M1–M3 da revisão final): ad8cb2d (desenvolvedor) e ec4a8a7 (testador, 70 testes de ataque). M1 e M3 corrigidos. Em M2 o recorte já estava certo e só ganhou teste com /Rotate 0/90/180/270.
- Onda final fechada: gate equivalente ao `.bat` em ec4a8a7 → `RESULTADO FINAL: APROVADO`, 3799 passed, cobertura 88,25%; `check_test_integrity --base 9f50e35` → exit 0 (só os 5 `SEM_SOUL` dos commits do orquestrador, já justificados na revisão final); re-revisão escopada (`revisor-seguranca`, 929ac98..ec4a8a7): M1, M2 e M3 ADDRESSED, sem Crítico nem Importante novo. Menores deferidos: `file:///home/...` não é saneado; `?c=/d` numa URL vira `?c=<caminho>`; caminho absoluto sem aspas, com espaço e fora dos diretórios conhecidos deixa a cauda relativa (limitação travada em teste).
- Cada tarefa passou por desenvolvedor, testador, verificação mecânica (`check_test_integrity`, exit 0) e revisão limpa da `revisor-seguranca`. Gate equivalente ao `.bat` em 929ac98: 3694 passed, cobertura 88,24%, APROVADO. Scanner (`osv-scanner -L requirements.txt:<lock>` nos 6 locks): `No issues found`; nenhum lock mudou.
- Revisão final (`revisor-seguranca`, opus) sobre 9f50e35..929ac98: aprovado com ressalvas, sem Crítico nem Importante. Pediu na onda única: M1 (empate a favor de A quando C confirma A e B dentro da tolerância vira `pendentes`), M2 (recorte da amostra em página com `/Rotate`) e M3 (`_sanear` também remove `runtime_directory` e caminhos absolutos). Os demais Menores ficaram deferidos com triagem.
- Execução operacional (2026-11-03/04):
  - 16 PDFs, 48 leituras validadas e congeladas (A e B em todos, C em 15). Concordância A × B: postes 120/120 sem fp, campos 468/471, vãos 103/103, símbolos 198/262 (30 só em A). Distância de casamento A × B: mediana 0,0003, p90 0,0016, máx 0,0070 (R4: nenhum indício para mudar 0,02/0,05).
  - Consolidação: 16/16 referências congeladas antes de qualquer comparação; 9 folhas com escopo `completo` e 7 `regional`; 25 divergências resolvidas por C, 35 pendentes, 30 zonas excluídas. 016 (pdfplot, símbolos esmaecidos) ficou com 1 poste e 12 zonas excluídas.
  - Amostra: v001 (20 itens) conferida pelo usuário por entrevista → 5/20 (25%), acima de 20% → v002 (20 itens): 01–04 pelo usuário, 05–20 conferidos por IA (orquestrador) com autorização do usuário. **taxa-v002: 8/40 postes com erro = 20%, Wilson 95% [10,5%; 34,8%]**; parte humana 5/24. Nenhum erro em campo afirmado (0 em 35 avaliados por campo); os erros são 4 pontos de ligação do cliente registrados como poste e 4 postes com símbolos pendentes (o usuário decidiu contá-los como erro). Omissões 1/40.
  - Baseline `baseline-v001 --native-only` (sem OCR português; Pillow 13.0.0, PyMuPDF 1.28.0, analisador 1.20.0, interpretador 25.0): postes 0/107, vãos 0/83, símbolos 0/179 em todas as folhas. Causa verificada: `run_variant` propõe postes, estruturas e equipamentos, mas a promoção automática só confirma cabos; a ficha predita vem do projeto promovido (R2) e não tem postes nas folhas reais. O baseline mede a promoção, não a leitura.
- Critérios verificados:
  - 1: `referencia.json` das 16 folhas, sha em `congelamento.json`, escopo declarado (9 completo, 7 regional).
  - 2: `fichas/amostra-humana/taxa-v002.json` e `relatorio.md` (com a parte conferida por IA declarada).
  - 3: `fichas/baseline-v001-resumo.{json,md}` com denominadores por PDF e total.
  - 4: `git grep -n "PROJETO DE REDE NS"` só acha as linhas que citam o próprio critério (este roadmap e o passo 8 do plano).
  - 5: gate de fechamento, `IniciarTestes.bat` real no worktree em e678d1d + documentos (2026-11-04 01:17): 3799 passed, cobertura 88,25%, `RESULTADO FINAL: APROVADO`.
- Decisões para o usuário (tomadas pela opção recomendada, por instrução do usuário em 2026-11-03):
  - **Conferência pelo leitor C, não pelo auditor:** a spec citava o `curadoria-auditor-visual`; no modo ficha a conferência é um terceiro leitor e a auditoria amostral não roda (seção "Decisões de desenho" do plano).
  - **Allow novo** em `.claude/settings.json`: `Bash(.venv/Scripts/python.exe -m scripts.curation_ficha *)`, no padrão das regras `curation_*`. Ele também deixa o leitor tecnicamente rodar os outros subcomandos; a barreira é o texto do agente.
  - **Folha sem área anotável** (zonas excluídas cobrem todas as páginas) não gera referência: `consolidar` recusa, e a folha aparece como `sem_referencia` no baseline (exige `--parcial`).
  - **Baseline nativo:** sem OCR português nesta máquina, o baseline roda `--native-only` e subestima as famílias sem texto nativo; a alternativa é rodá-lo na imagem Docker, que tem o Tesseract.
  - **Gate pelo equivalente bash:** na 2ª sessão o harness recusou `cmd.exe` no worktree; na 3ª o `.bat` rodou pelo caminho completo.
- Decisões para o usuário (2026-11-04, tomadas pela opção recomendada por instrução do usuário):
  - **Fonte da ficha predita (D2 revista):** o baseline do projeto promovido é 0 por construção nas folhas reais. Recomendado: nova `versao_extracao` a partir das propostas (postes, estruturas, equipamentos e cabos propostos), implementada no início da E07, que é a etapa que compara com o baseline; E04–E06 não dependem dele. Alternativa: implementar já como tarefa extra da E03.
  - **Conferência por IA:** 16 dos 40 itens da amostra foram conferidos pelo orquestrador, com autorização do usuário; a taxa só humana (5/24) fica registrada ao lado.
  - **Pontos de ligação do cliente:** o usuário julgou "não é poste"; a convenção da próxima rodada de leitura deve excluí-los.
  - **Símbolos pendentes visíveis contam como erro** (decisão do usuário na entrevista).
  - **Parada de revisão humana dispensada:** o usuário pediu para seguir com mais etapas depois da E03.
- Notas para a próxima etapa:
  - Pendências acionáveis do relatório: o CLI `amostra` recorta com margem 0,04 e corta o rótulo do poste (a conferência usou recortes auxiliares com margem 0,12 e, quando a camada anotada cobre o poste, sem anotações); `ficha_leitura_dupla` poderia normalizar separador e ordem do cabo; baseline com OCR na imagem Docker.
  - Minors deferidos relevantes para a operação: vão entre postes de páginas diferentes vira zona excluída nos dois extremos; o leitor A/B não é proibido por texto de abrir `regioes-conferencia.json`; queda no meio de um comando exige recuperação manual.

---

## E04 — Modelo de desenho e perfis de família — #concluida

**Objetivo:** transformar cada página num modelo de desenho derivado e reconhecer a família do PDF, conforme as decisões 1 e 2 do design.

**Por que agora:** é a base de texto, símbolos e ficha (E05–E08).

**Dependências:** E01.

**Escopo:**
- **Reconhecimento da família** por impressão estrutural: Electric Office/Print To PDF, iText, Ghostscript, AutoCAD e um perfil genérico.
- **Modelo de desenho:**
  - texto nativo e SHX;
  - polilinhas reconstruídas;
  - círculos e arcos recuperados de Béziers;
  - grupos candidatos a símbolo;
  - camada, cor e espessura.
- **Cache e versão:** o modelo entra no cache derivado do ADR 0004, com versão própria.
- **DXF de depuração:** um script exporta o modelo em DXF com ezdxf, como dependência de experimentos ou de desenvolvimento.
- **Hipótese H3:** conferir se as imagens são só ortofoto.

**Fora de escopo:** ler contorno de glifo (E05); classificar símbolos (E06); trocar o analisador padrão.

**Critérios de aceite:**

- [x] Fixtures sintéticas de cada família são reconhecidas corretamente, e uma família desconhecida cai no genérico com diagnóstico.
- [x] Uma fixture com segmentos colineares fragmentados vira uma polilinha, e uma fixture com círculo em 4 Béziers vira um círculo.
- [x] O DXF de depuração de uma fixture abre com ezdxf e preserva camadas e textos.
- [x] O resultado de H3 está no handoff.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- Inspeção manual: DXF de 2 folhas reais de famílias diferentes aberto no AutoCAD ou num visualizador DXF pelo usuário, quando possível. Os arquivos ficam só em `tmp/`.

**Revisão humana:** não

**Notas para o plano:**
- A inspeção de 2026-10-30 viu: Print To PDF com cerca de 600–2.200 formas pequenas preenchidas e 0–4 rótulos nativos; iText com 11–45 rótulos nativos; AutoCAD com 11 OCGs (`P`, `NOTAS`, `ESTRUEXI`…). O campo `producer` sozinho não identifica o Electric Office.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Custo de memória e tempo em folhas com cerca de 40 mil primitivas → medir em folhas reais e registrar. O ResourceWarning do pytest pega documento não fechado.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-04-leitura-vetorial-por-poste-e04.md`. A revisão de arquitetura bloqueou nas rodadas 0 e 1 e aprovou com notas na rodada 2 (seção "Revisão de arquitetura" do plano).
- Entregas: pacote puro `adapters/analysis/drawing_model/` (modelo com caminhos brutos, polilinhas, círculos/arcos, grupos candidatos, textos nativo/SHX, imagens; perfil por família; cache derivado `modelo-desenho-v1`), leitor `adapters/analysis/pymupdf_drawing_model.py`, scripts `drawing_model_dxf` (ezdxf só no lock de desenvolvimento) e `drawing_model_report`; guardas de import em `tests/unit/test_architecture.py`. O analisador padrão não mudou.
- Commits: plano 83b0dc8, 526861c, 1c9aa27, d6b842c; Task 1 461d10f, 602b9de, de8b4fe, 406f2ae; Task 2 a13da40, 7b23406, 5abf36c, bb25bf9, 9a5cfc3; Task 3 6e37cae, 3694105, 11ed33c, 091fe29; Task 4 a4e8637, e653a73, 0a76c05/1bb063c (relatório do workspace versionado por engano e retirado), b23066d, e9a893d, 277d311, 904a95a, 41f58bc; Task 5 90bc49c, ae4240d, 1315bfb, 78f478f, 2b2fd89; Task 6 cbc03d4, 9b80de4; onda final f7e82da, 6d8f641, 29a6e4e, b8498dd, 019dfa8.
- Revisão final (`revisor-seguranca`, opus) sobre 6a1f438..9b80de4: aprovado com ressalvas, sem Crítico; pediu o registro de H3 e handoff (feito aqui) e o teto de pixels na imagem de anotação. Onda única: teto de pixels, cache conferindo o sha256 no hit e antes de gravar, relatório com `erro_amostras`, `fonte_pixels` e `is_file`, linha de arquitetura no `CLAUDE.md`; o testador achou 2 contornos do teto (/Width real e indireto) e um despacho curto a mais corrigiu (exceção registrada para não deixar a suíte vermelha). Re-revisão escopada: os 6 achados resolvidos, sem quebra nova. Scanner `osv-scanner` nos 6 locks: `No issues found`. `check_test_integrity --base 6a1f438`: 1 apontamento (skip da junção NTFS fora do Windows, justificado; o teste roda nesta máquina). Gate de fechamento: `IniciarTestes.bat` real em 019dfa8 → 4229 passed, cobertura 88,51%, `RESULTADO FINAL: APROVADO`.
- Cada tarefa passou por desenvolvedor, testador (que achou defeitos reais em todas as tarefas menos a 6: segmento duplicado, remoção quadrática, grade de camada sem limite com `Tm` gigante, coerção de tipos e estouros no cache, colisão de camadas no DXF), verificação mecânica e revisão limpa da `revisor-seguranca`. O gate de complexidade reprovou a Task 2 depois da revisão (CC 32) e ela foi reaberta e refatorada.
- Execução nas 16 folhas reais (`tmp/e04/` do checkout principal): famílias 8 `electric_office_print`, 6 `itext`, 1 `ghostscript`, 1 `autocad` (bate com o esperado); 0,24–6,4 s por folha, pico Python até 44 MB (o `tracemalloc` não conta a memória nativa do MuPDF); nenhum diagnóstico de fonte; DXF de uma folha Electric Office e da folha AutoCAD (12 camadas = OCGs) em `tmp/e04/`, abrem no ezdxf.
- **H3 — resultado:** os ladrilhos das folhas são só ortofoto (retangulares e triangulares de meia diagonal, sem rede, símbolo ou texto queimado), e nenhum símbolo da rede é raster. **Mas há texto em raster:** nas folhas iText, a tabela "CHI previsto / dispositivo de seccionamento", o quadro de servidão e a nota de intervenção em APP são imagens coladas (confirmado pela extração crua das imagens); na folha Ghostscript, uma correção de rótulo de poste chega como imagem de anotação. Nas folhas Electric Office essas tabelas são texto nativo. Impacto: o OCR não sai na E09 sem tratar esses blocos ou declará-los fora da ficha. O classificador `ladrilho` do relatório não pega os ladrilhos triangulares e de borda (caem em `outra`), então `ladrilho` e `fracao_ladrilhos` subestimam a cobertura de ortofoto.
- Critérios verificados:
  - famílias: `test_fixture_de_cada_familia_e_reconhecida` e testes de `family.py` (4 famílias + genérico com `familia.desconhecida`/`familia.print_to_pdf_sem_glifos`);
  - polilinha e círculo: `test_segmentos_fragmentados_do_pdf_viram_uma_polilinha` e `test_circulo_desenhado_com_beziers_vira_circulo`;
  - DXF: `test_dxf_da_fixture_abre_com_ezdxf_e_preserva_camadas_e_textos` (camadas `P` e `NOTAS`, texto em `NOTAS`);
  - H3: acima;
  - gate: `IniciarTestes.bat` → `RESULTADO FINAL: APROVADO` (linha "Revisão final").
- Decisões para o usuário (tomadas pela opção recomendada):
  - **ezdxf** só em `requirements-development.lock` e no extra `dev` (gate verifica o DXF; o servidor e o cliente não recebem a dependência); numpy fixado em 2.3.5 para o lock de desenvolvimento continuar instalável junto com o de experimentos. A linha de "Fronteiras" do design sobre locks fica como pendência do arquiteto.
  - **Elementos grandes fora do agrupamento** e cobertura de curvas por item (sem isso, uma linha da rede encostada num símbolo apagava o símbolo).
  - **Cache estrito:** qualquer tipo errado ou negativo em índice/dimensão = cache corrompido.
- Notas para a próxima etapa (obrigatórias quando o modelo entrar no job do servidor, E05–E07):
  - `VERSAO_MODELO_DESENHO` entra na assinatura de capacidade e na versão do extrator (ADR 0004/0006); se `application/` precisar dos tipos do modelo, eles migram para `ports/`.
  - Robustez contra PDF hostil antes do servidor: orçamento no casamento de camada do texto (resíduo O(N²) com muitos trechos gigantes; diagnóstico `modelo.camadas_texto_limitadas`), limite de tamanho antes de ler o cache, NaN/Infinity no cache (quebram JSON estrito), custo de célula densa no union-find, unidade de falha mais fina (uma anotação malformada ou uma cor de aridade ≠ 3 esvazia a fonte inteira da página).
  - Desenhos de anotação (bordas de carimbo, vetores do portador SHX) entram em `caminhos`; no AutoCAD o SHX também chega como traço vetorial e gera polilinhas e grupos que duplicam o texto (E06).
  - Texto SHX sai com rotação 0, altura = altura da caixa e camada vazia; `ImagemModelo.sha256` é o sha256 do digest de pixels da PyMuPDF, exceto para imagem de anotação acima do teto de 16 MP ou com dimensão indeterminada, que usa o sha256 do stream bruto (não decodifica).
  - O teto de pixels confia em /Width e /Height do dicionário: imagem JPX (dimensionada pelo codestream) e /SMask com dimensões próprias ainda escapam; tratar junto com os demais itens de PDF hostil.
  - A onda final mudou a saída em casos de borda (dimensão real/indireta, identidade acima do teto) sem incrementar `modelo-desenho-v1`, porque não havia consumidor nem cache publicado; caches em `tmp/` gravados antes de 019dfa8 podem ter a identidade antiga — apague-os antes de reaproveitar.

---

## E05 — Texto por contorno de glifo — #pendente

**Objetivo:** recuperar o texto desenhado como contorno por assinatura de forma contra uma tabela de glifos versionada, sem OCR (decisão 3 do design).

**Por que agora:** metade das folhas tem o texto da rede só como contorno. Esse texto é a base da ficha.

**Dependências:** E04, E03.

**Escopo:**
- Assinatura de glifo invariante a translação, escala e rotação, com tolerância à variação de curva.
- Montagem de palavras e rótulos, com posição, rotação e altura.
- Tabela de glifos versionada em `src/zeny_project_handler/adapters/analysis/data/` (a criar), com o mecanismo de inicialização: agrupar assinaturas, renderizar representantes e rotulá-los por leitura dupla.
- O texto recuperado entra como evidência de texto com atributo de origem, e a versão do extrator é incrementada.
- Glifo desconhecido gera diagnóstico.
- Confirmar a hipótese H1.

**Fora de escopo:** remover OCR (E09).

**Critérios de aceite:**

- [ ] Uma fixture sintética com texto convertido em contorno, a partir de uma fonte livre, produz o mesmo texto que a versão nativa da mesma folha.
- [ ] Glifo ausente da tabela gera diagnóstico e não produz caractere.
- [ ] Nas 16 folhas, o recall de identificador, estrutura, poste e coordenada da ficha está registrado em `tmp/` contra o baseline de E03. Nas famílias de contorno, ele é maior que o baseline.
- [ ] A tabela versionada não contém recorte nem bitmap de PDF real, só assinaturas e caracteres.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- Benchmark por poste de E02 sobre as 16 folhas → relatório em `tmp/`.

**Revisão humana:** não

**Notas para o plano:** a rotulagem dos representantes de glifo reutiliza a leitura dupla adaptada em E03.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- H1 falsa, com glifos compostos ou fundidos → segmentar por subcaminho e registrar no handoff. Se a recuperação ficar abaixo do baseline numa família, essa família continua com OCR.

**Evidências e handoff:**

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E06 — Símbolos sobre o modelo de desenho — #pendente

**Objetivo:** reconhecer estais, para-raios MT/BT, transformadores e demais símbolos do inventário a partir dos grupos do modelo de desenho, usando os pacotes declarativos.

**Por que agora:** símbolos são a segunda metade da ficha. Os grupos do modelo de desenho dão geometria limpa aos pacotes.

**Dependências:** E05.

**Escopo:**
- Execução dos pacotes de `symbol_packages/` sobre os grupos do modelo, como método de símbolos versionado.
- Ampliação dos pacotes para as classes do escopo da ficha que faltam, só com fonte rastreável no inventário.
- Confirmar a hipótese H2. Símbolos raster ficam marcados como resíduo para E12.

**Fora de escopo:** associação ao poste (E07); remover detectores antigos (E09).

**Critérios de aceite:**

- [ ] Fixtures sintéticas positivas e negativas para cada classe nova ou alterada.
- [ ] Nas 16 folhas, precisão e recall de símbolo (diagnóstico) estão registrados em `tmp/` e são maiores que os do analisador atual com as mesmas referências.
- [ ] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** nenhuma.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Pacote que memoriza a folha → exigir fixture sintética autoral, e o verificador procura coordenadas ou hashes de folhas reais.

**Evidências e handoff:**

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E07 — Ficha do poste — #pendente

**Objetivo:** associar texto, símbolos e vãos ao poste certo e expressar a ficha nas propostas e relações atuais.

**Por que agora:** a associação é um dos erros que mais custam ao usuário. Com texto e símbolos limpos, ela passa a ser geométrica.

**Dependências:** E06.

**Escopo:**
- Associação geométrica por proximidade, linhas de chamada e convenções de layout, com vãos ligados à polilinha da rede entre dois postes.
- Montagem da ficha como propostas e relações atuais (sem entidade persistida nova), com a versão do interpretador incrementada.
- Ambiguidade de associação vira pendência, não escolha arbitrária.

**Fora de escopo:** conferência UTM (E08).

**Critérios de aceite:**

- [ ] Uma fixture sintética com dois postes próximos e rótulos entre eles associa corretamente ou marca pendência. Nunca associa ao vizinho errado com confiança.
- [ ] O benchmark por poste sobre as 16 folhas supera o baseline de E03 em todas as métricas, com relatório em `tmp/`.
- [ ] Promoção, regiões, vãos e conformidade continuam funcionando sobre as propostas novas (testes de integração existentes passam).
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** sim

**Notas para o plano:** `application/symbol_reconciliation.py`, `analysis_regions.py` e `spans.py` já fazem associação e vãos. Decida no plano o que é reaproveitado e o que é substituído. O baseline da E03 (projeto promovido) é 0/107 porque a promoção automática não confirma postes: comece pela fonte da ficha predita a partir das propostas (D5) e refaça o baseline sobre as referências da rodada da E03 antes de comparar.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Ganho nas 16 folhas por sobreajuste → a prova definitiva fica para o conjunto cego de E09.

**Evidências e handoff:**

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E08 — Conferência UTM — #pendente

**Objetivo:** ajustar a transformação página → UTM com as coordenadas lidas e a escala, e conferir posição de poste e comprimento de vão (decisão 4 do design).

**Por que agora:** é o que torna a ficha confiável e evita o antiobjetivo de errar com segurança.

**Dependências:** E07.

**Escopo:**
- Ajuste com rejeição de outliers.
- Resíduo por poste e diferença por vão.
- Pendências de revisão pelo mecanismo de `human_review`.
- Calibração das tolerâncias iniciais, `max(2 m, 3%)` para vão e 3 m para posição, nas 16 folhas.
- Campos aditivos de API apenas se a pendência precisar aparecer no cliente.

**Fora de escopo:** novas regras de conformidade.

**Critérios de aceite:**

- [ ] Fixtures sintéticas cobrem quatro casos: folha consistente sem pendência, uma coordenada trocada (só esse poste pendente), vão escrito errado (só esse vão pendente) e menos de 2 coordenadas (conferência não avaliável, com diagnóstico).
- [ ] Nas 16 folhas, toda ficha divergente da referência que a conferência poderia detectar está marcada como pendência. Os números ficam em `tmp/`.
- [ ] As tolerâncias calibradas estão registradas no design (seção "Decisões", item 4).
- [ ] Se a API mudou, `docs/api/openapi-v1.json` foi regenerado e o teste de snapshot passa.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** `analysis_regions.py` já monta `CoordenadaCampo` UTM a partir do texto.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Folhas em fuso UTM diferente ou com coordenadas parciais → tratar como não avaliável, sem pendência falsa.

**Evidências e handoff:**

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E09 — Troca do analisador e remoção do legado — #pendente

**Objetivo:** tornar o analisador novo o padrão do servidor quando ele vencer o atual no conjunto cego, e remover o que ele substituiu (decisão 7 do design).

**Por que agora:** fecha o bloco B e cumpre a parte de limpeza que dependia de prova.

**Dependências:** E08.

**Escopo:**
- **Conjunto de avaliação:** folhas novas reservadas pelo usuário (H4), lidas às cegas com o fluxo de E03 e congeladas antes de qualquer predição.
- **Comparação:** atual × novo pelo benchmark por poste.
- **Troca do padrão em `composition.py`.**
- **Remoção:**
  - detectores substituídos;
  - os scripts de fechamento da curadoria que ficarem obsoletos (`benchmark_*_e05`/`e06`/`e07`/`e13`/`e14`, `*_e16`), com a skill e o contrato atualizados;
  - se nenhuma família precisar, OCR, Tesseract, dependências e etapa do `Dockerfile`.

**Fora de escopo:** detector treinado (E12).

**Critérios de aceite:**

- [ ] No conjunto cego, o analisador novo é ≥ o atual em todas as métricas por poste, sem regressão de folha não justificada no relatório local.
- [ ] O analisador padrão do servidor é o novo, com versões de extrator e interpretador incrementadas.
- [ ] `git grep` não encontra referência a módulo removido.
- [ ] Se o OCR saiu, a imagem do servidor é construída sem Tesseract e o smoke `scripts/smoke_examples.py` passa.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- `.venv/Scripts/python.exe scripts/smoke_examples.py` → código 0.
- Inspeção manual: o usuário abre 2 projetos no cliente (`.\ZenyProjectHandler.bat`, exige `.env`) e confere fichas e pendências.

**Revisão humana:** sim

**Notas para o plano:** a inspeção na UI exige `.env` com a string ODBC do SQL Server de mercado. Isso já bloqueou uma etapa antes, então confira cedo.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Remover OCR e descobrir depois uma família raster → a remoção do OCR só acontece se H3 e H2 se confirmaram. Caso contrário, o OCR fica como reserva com diagnóstico.

**Rollback / migração:** a troca é por composição. Reverter o padrão para o analisador anterior é uma mudança em `composition.py`, enquanto ele não tiver sido removido. Por isso, a remoção vem em commit separado, depois da troca medida.

**Evidências e handoff:**

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E10 — Fábrica de rótulos contínua — #pendente

**Objetivo:** fluxo repetível para cerca de 50 folhas por mês que produz conjunto de treino rotulado, com taxa de erro medida e versão por hash, fora do Git (decisão 6 do design).

**Por que agora:** o detector (E12) precisa de volume. A pré-marcação usa o pipeline vetorial já pronto em E07.

**Dependências:** E07.

**Escopo:**
- Pré-marcação vetorial, só para treino.
- Leitura dupla e encaminhamento de divergências.
- Amostra humana de cerca de 5 folhas em 50.
- Separação por folha entre treino e avaliação, com avaliação cega e congelada.
- Manifesto do conjunto de dados com hashes.
- Local de armazenamento fora do Git, decidido no plano.
- Atualização da skill e do contrato de curadoria.

**Fora de escopo:** treinar (E11, E12).

**Critérios de aceite:**

- [ ] Um lote com as folhas disponíveis passa pelo fluxo inteiro e gera o manifesto, com taxa de erro de rótulo medida.
- [ ] Nenhuma folha aparece ao mesmo tempo em treino e avaliação (verificado por script).
- [ ] Nenhum rótulo, recorte ou folha está em arquivo versionado.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- Inspeção manual: o usuário confere a amostra do lote.

**Revisão humana:** não

**Notas para o plano:** nenhuma.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Pré-marcação enviesando o treino com os erros do vetor → a leitura dupla corrige, e a amostra humana mede o efeito.

**Evidências e handoff:**

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E11 — Spike de treino na GPU AMD — #pendente

**Objetivo:** decidir onde e como treinar o detector, provando ou descartando PyTorch com ROCm na RX 9070 XT desta máquina (H5).

**Por que agora:** a viabilidade do treino local decide o custo e o desenho de E12.

**Dependências:** E10.

**Escopo:**
- Ensaio, fora do produto, de um treino mínimo de detecção com licença Apache, BSD ou MIT na GPU, nativo no Windows e/ou via WSL2.
- Exportação para ONNX e inferência em CPU com ONNX Runtime.
- Medição de tempo.

**Fora de escopo:** código de produção; dependência nova nos locks do servidor.

**Critérios de aceite:**

- [ ] A decisão está registrada no ADR 0017, com o caminho escolhido (ROCm nativo, WSL2, CPU ou GPU alugada), versões, tempos medidos e alternativas descartadas.
- [ ] Um modelo mínimo exportado para ONNX roda em CPU com ONNX Runtime.

**Validação obrigatória:**

- Inspeção manual: tempos e versões do ensaio no handoff.

**Revisão humana:** sim

**Notas para o plano:** spike sem código de produção. Os scripts do ensaio ficam fora de `src/` e o lock de treino é opt-in.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- ROCm sem suporte à GPU → registrar e propor D1 ao usuário, por entrevista.

**Evidências e handoff:**

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E12 — Detector visual local — #pendente

**Objetivo:** treinar e integrar um detector local para o resíduo que o vetor não resolve, com ganho medido por poste (decisão 5 do design, ADR 0017).

**Por que agora:** é a última camada de precisão, com o volume de E10 e o caminho de treino de E11.

**Dependências:** E11, E09.

**Escopo:**
- **Treino** com o conjunto de E10, pelo caminho decidido em E11.
- **Adaptador** de inferência ONNX Runtime em CPU no servidor, que só atua onde o vetor não resolveu.
- **Assinatura:** o hash dos pesos entra na assinatura do analisador, e as evidências levam confiança.
- **Pesos** como artefato de release com SHA-256, fora do Git.
- **Orçamento:** até 60 s por folha em CPU.

**Fora de escopo:** treino contínuo automático; GPU no servidor.

**Critérios de aceite:**

- [ ] No conjunto de avaliação cego, o benchmark por poste com detector é ≥ sem detector em todas as métricas e maior em pelo menos uma.
- [ ] Sem os pesos, o servidor sobe e analisa só com o vetor, com diagnóstico.
- [ ] A inferência fica dentro do orçamento por folha, medida em `tmp/`.
- [ ] `client_artifact_gate` aprova, sem ONNX Runtime no cliente.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- `.venv/Scripts/python.exe scripts/client_artifact_gate.py --source-only` → aprovado.

**Revisão humana:** sim

**Notas para o plano:** os testes do gate usam um modelo ONNX sintético minúsculo, gerado no teste. Os pesos reais nunca são exigidos no gate.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- O detector piora alguma métrica → ele fica desligado por padrão e o ganho é registrado como não alcançado.

**Rollback / migração:** o detector é opcional por composição. Desligá-lo devolve o comportamento de E09.

**Evidências e handoff:**

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## Histórico de revisões

- 2026-10-30 — roadmap criado a partir do design `2026-10-30-leitura-vetorial-por-poste-design.md`, com 12 etapas em três blocos.
- 2026-11-02 — E13 (atualização de dependências vulneráveis) incluída antes da E03, por decisão do usuário (D3). A E03 passa a depender de E13.
