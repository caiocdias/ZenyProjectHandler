# Roadmap — Leitura vetorial por poste

> Arquivo: `docs/roadmap-leitura-vetorial-por-poste.md` · branch de execução: `roadmap/leitura-vetorial-por-poste` · criado em 2026-10-30 · última revisão 2026-10-30

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
- detector visual local.

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
- Dependências novas: ONNX Runtime e ezdxf só nos locks do servidor ou de experimentos. Treino com lock próprio e opt-in. Licença Apache-2.0, BSD ou MIT; YOLO Ultralytics (AGPL) está excluído.

## Hipóteses e decisões em aberto

| # | Hipótese ou decisão | Impacto se errada / sem decisão | Etapa afetada |
|---|---|---|---|
| H1 | Nas famílias sem texto nativo, cada forma pequena preenchida é um glifo de fonte fixa | a leitura por assinatura precisa segmentar glifos compostos ou tolerar variação de curva | E05 |
| H2 | Os símbolos da rede são vetoriais em todas as famílias | símbolos rasterizados vão direto para o resíduo do detector (E12) | E06 |
| H3 | As imagens das folhas Print To PDF e iText são só ladrilhos da ortofoto | se carregarem símbolos ou texto, o OCR não pode sair em E09 | E04 |
| H4 | O usuário reserva folhas novas, ainda não vistas, para o conjunto de avaliação antes de E09 | sem elas, E09 não tem prova cega e fica bloqueada | E09 |
| H5 | PyTorch com ROCm treina na RX 9070 XT desta máquina (Windows nativo ou WSL2) | o treino cai para CPU ou para GPU alugada (D1) | E11 |
| D1 | Treinar em GPU alugada por hora, se ROCm e CPU forem inviáveis | sem decisão, E12 só treina em CPU | E12 (só se E11 concluir que o treino local é inviável) |

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
| E01 | Limpeza do projeto | #em-andamento | — | scripts, testes e docs de etapas encerradas removidos, gate verde |
| E02 | Ficha de referência e benchmark por poste | #pendente | E01 | formato da ficha, avaliador por poste e baseline sintético |
| E03 | Rotulagem v0 e baseline real | #pendente | E02 | fichas de referência das 16 folhas e baseline do analisador atual em `tmp/` |

Bloco B — leitura vetorial

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E04 | Modelo de desenho e perfis de família | #pendente | E01 | modelo de desenho por página, perfil por família e DXF de depuração |
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

## E01 — Limpeza do projeto — #em-andamento

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

- [ ] `git grep -n` por cada nome removido não encontra referência fora do histórico de revisões deste roadmap.
- [ ] `build_release.py` e os gates `release_artifact_gate`, `server_artifact_gate` e `client_artifact_gate` continuam funcionando, ou o plano provou que não dependiam dos removidos.
- [ ] `.\IniciarTestes.bat` termina com `RESULTADO FINAL: APROVADO`, com a cobertura mínima mantida.

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

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E02 — Ficha de referência e benchmark por poste — #pendente

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

- [ ] O schema valida uma ficha sintética completa e rejeita campo extra.
- [ ] O avaliador, sobre fixtures sintéticas, produz as métricas esperadas em cada caso (acerto total, símbolo associado ao poste vizinho, poste ausente, vão errado).
- [ ] Um CLI roda predição + avaliação de um PDF e grava o relatório em um diretório informado. O relatório não traz caminho absoluto nem conteúdo da folha além do necessário.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

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

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E03 — Rotulagem v0 e baseline real — #pendente

**Objetivo:** produzir fichas de referência das 16 folhas de `examples/` por leitura dupla cega com amostra humana, e medir o analisador atual contra elas.

**Por que agora:** sem a linha de base real não há como provar que a leitura vetorial melhora.

**Dependências:** E02.

**Escopo:**
- **Adaptação da curadoria:** a skill `curadoria-simbologia`, os agentes `curadoria-leitor-visual` e `curadoria-auditor-visual` e o contrato `docs/fluxo-curadoria-incremental-simbologia.md` passam a produzir a ficha do poste.
- **Leitura dupla cega:** dois leitores independentes. As divergências são resolvidas por um terceiro leitor ou ficam pendentes, sem palpite.
- **Amostra humana:** o usuário confere uma amostra de fichas e a taxa de erro é registrada.
- **Baseline:** referências congeladas e o baseline do analisador atual em `tmp/`.
- **Invariante revisado:** o contrato passa a permitir que rótulos alimentem treino (ADR 0017), mantendo a leitura de avaliação cega.

**Fora de escopo:** corrigir detectores; conjunto de avaliação de folhas novas (E09); fábrica contínua (E10).

**Critérios de aceite:**

- [ ] As 16 folhas têm ficha de referência congelada antes de qualquer comparação, com escopo de anotação declarado.
- [ ] A amostra conferida pelo usuário e a taxa de erro de rótulo estão registradas no relatório local.
- [ ] O baseline por poste do analisador atual existe em `tmp/` com denominadores.
- [ ] Nenhuma ficha, recorte ou nome de folha entrou em arquivo versionado (`git grep -n "PROJETO DE REDE NS"` vazio).
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

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

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

---

## E04 — Modelo de desenho e perfis de família — #pendente

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

- [ ] Fixtures sintéticas de cada família são reconhecidas corretamente, e uma família desconhecida cai no genérico com diagnóstico.
- [ ] Uma fixture com segmentos colineares fragmentados vira uma polilinha, e uma fixture com círculo em 4 Béziers vira um círculo.
- [ ] O DXF de depuração de uma fixture abre com ezdxf e preserva camadas e textos.
- [ ] O resultado de H3 está no handoff.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

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

- Plano: —
- Commits: —
- Revisão final: —
- Critérios verificados: —
- Decisões para o usuário: —
- Notas para a próxima etapa: —

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

**Notas para o plano:** `application/symbol_reconciliation.py`, `analysis_regions.py` e `spans.py` já fazem associação e vãos. Decida no plano o que é reaproveitado e o que é substituído.

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
