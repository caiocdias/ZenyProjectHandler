# Roadmap — Curadoria de simbologia paralela por ondas com Claude Code

> Arquivo: `docs/roadmap-curadoria-simbologia-paralela.md` · criado em 2026-10-15 · última revisão 2026-10-15

## Como usar

Forma recomendada — **uma única execução automática**: cole o prompt da seção "Execução automática" numa sessão limpa do Claude Code, na raiz do repositório. Ela executa todas as etapas em sequência (um subagente implementador e um verificador por etapa), roda a primeira rodada completa de curadoria sobre `examples/` e termina com o "Encerramento", que apaga este roadmap. Só para diante de bloqueio real, divergência do plano ou duas reprovações seguidas do verificador. Para não parar em cada pedido de permissão, libere antes nas permissões do Claude Code os comandos `.venv/Scripts/python.exe -m pytest`, `-m ruff`, `-m mypy`, `-m scripts.*` e `cmd.exe //c IniciarTestes.bat`, ou use um modo de permissão mais autônomo.

Alternativa manual: cole o prompt de uma etapa numa sessão limpa, uma etapa por sessão, na ordem do índice.

Em ambas, quem executa segue o "Protocolo de execução", atualiza a tag da etapa e preenche "Evidências e handoff". Não pule dependências. Nenhuma sessão faz commit; revise o diff final e faça commit quando quiser.

## Encerramento

Este roadmap é um artefato de construção, não documentação permanente. O fluxo reaproveitável é a skill `/curadoria-simbologia` com seus CLIs e o contrato `docs/fluxo-curadoria-incremental-simbologia.md`, que não guardam histórico de execução. Depois que E11 receber parecer APROVADO do verificador, quem a executou (o orquestrador, no modo automático):

1. confirma que nenhum arquivo do repositório fora deste roadmap cita `roadmap-curadoria-simbologia-paralela`, IDs de etapa deste roadmap (E01–E11) como trabalho feito, ou resultados da rodada em prosa (`grep -rn "roadmap-curadoria-simbologia-paralela" --exclude-dir=.git --exclude-dir=.venv --exclude-dir=tmp .`);
2. apaga `docs/roadmap-curadoria-simbologia-paralela.md`;
3. responde com o resumo final (etapas, pareceres, resultados da rodada com o caminho do relatório local em `tmp/`, `git status --short`).

O histórico deste roadmap fica só no Git, se o usuário commitar antes do encerramento, e no relatório final da sessão.

## Objetivo

Substituir a curadoria estritamente sequencial (um PDF ativo por vez, equipe A/B/C reutilizada, gates completos por PDF) por um fluxo em **ondas de 3 a 5 PDFs processados em paralelo por subagentes do Claude Code**, mantendo a referência visual cega, a medição determinística e os gates de regressão. Ao final, uma rodada é iniciada por uma skill de projeto (`/curadoria-simbologia`), os passos mecânicos (manifesto, renderização, inferência, comparação, amostragem, backlog) são CLIs testados em `scripts/`, o contrato vivo em `docs/fluxo-curadoria-incremental-simbologia.md` descreve o novo fluxo sem referências a GPT/Codex e sem histórico de execução, e a primeira rodada completa sobre os PDFs atuais de `examples/` já foi executada com o fluxo novo. Colocar mais PDFs em `examples/` e invocar `/curadoria-simbologia` de novo inicia outra rodada, que parte da matriz de cobertura publicada pela anterior.

## Contexto confirmado

- Stack: Python 3.11–3.13, PyMuPDF, Pillow, pytest, Ruff, mypy strict (`pyproject.toml`). Ambiente Windows; `.venv` criado por `setup.bat`.
- Contrato atual: `docs/fluxo-curadoria-incremental-simbologia.md` (566 linhas). Etapas C01–C04, "exatamente um PDF de projeto ativo por vez", equipe A (algoritmos), B (fixtures/testes), C (revisão visual), comparação feita pelo agente, gates completos e reinferência sequencial de todo o corpus no fim. Cita "GPT ativo", "Codex" e a documentação de visão da OpenAI.
- CLIs existentes (argumentos conferidos no código):
  - `scripts/benchmark_symbols.py` — modos `synthetic`, `examples --root DIR --output DIR [--include-*]` e `comparison --reference --predictions --output`. O modo `examples` descobre **todos** os PDFs de uma pasta (`run_examples` em `scripts/symbol_benchmark_runner.py:1395`); não há opção de arquivo único, por isso o fluxo atual copia o PDF para uma `input/` isolada.
  - `scripts/benchmark_network_pdf.py SOURCE --output JSON [--runtime-directory] [--native-only] [--telemetry] [--complementary-ocr]`.
  - `scripts/curation_coverage_e16.py plan|compare`, `scripts/coverage_matrix_e16.py`, `scripts/benchmark_packages_e07.py`, `scripts/benchmark_review_e14.py`, `scripts/reconcile_symbol_benchmark.py`, `scripts/audit_symbol_packages.py`.
- Avaliador: `scripts/symbol_benchmark_evaluator.py`, protocolo congelado `symbols-e02-v1` (bbox normalizada [0,1], IoU ≥ 0,5 ou critério de traço fino, casamento 1:1 por documento/página/camada/classe). `_validate` **recusa referência com `annotation_scope` diferente de `complete`** — referências regionais exigem um comparador próprio que reutilize `geometry_match`.
- Ocupação visual: `src/zeny_project_handler/application/visual_occupancy.py` (grade de células não brancas, Pillow).
- Fixtures sintéticas de PDF: `tests/pdf_fixtures.py`, `tests/symbol_benchmark_fixtures.py`. Testes relacionados em `tests/unit/test_benchmark_symbols.py`, `test_curation_coverage_e16.py`, `test_e16_coverage_matrix.py`, `test_symbol_inventory.py`, `test_declarative_symbol_packages.py`.
- Dados: `docs/data/inventario-simbologia-v1.json` (427 IDs, 33 famílias), `docs/data/matriz-simbologia-e16.csv` e resumo. `docs/data/matriz-simbologia-curadoria-atual.csv` ainda não existe (nenhuma rodada C01–C04 foi executada).
- `tmp/` e `examples/**` são ignorados pelo Git (`.gitignore`). Em 2026-10-15, `examples/` contém 16 PDFs na raiz (`PROJETO DE REDE NS *.pdf`), todos com 1 página (A4 ou A3), de 1,2 MB a 21 MB.
- Não há `.claude/` nem `AGENTS.md` no repositório.
- Comandos confirmados (fonte: `README.md`, `IniciarTestes.bat`, `pyproject.toml`): `.venv/Scripts/python.exe -m ruff check .`, `-m ruff format --check .`, `-m mypy`, `-m pytest --cov`, `scripts/complexity_gate.py src`, `scripts/client_artifact_gate.py --source-only`, gate completo `IniciarTestes.bat` (no Git Bash: `cmd.exe //c IniciarTestes.bat`).
- Documentos de referência: `docs/adr/0005-exemplos-locais-dinamicos.md`, `docs/schemas/pacotes-simbologia.schema.json`, `docs/schemas/inventario-simbologia.schema.json`, `CLAUDE.md`.

## Desenho do fluxo-alvo

Esta seção é o contrato que as etapas implementam. A etapa E09 o transfere para o documento vivo.

**Por que o fluxo atual é lento.** Três gargalos estruturais: (1) só um PDF anda por vez, embora leitura visual, inferência e comparação de PDFs diferentes não editem os mesmos arquivos; (2) o agente faz trabalho mecânico — copiar entrada, renderizar, comparar listas, contar denominadores — que um script faz de forma determinística e mais barata; (3) correções são feitas PDF a PDF, com reinferência e gates repetidos a cada documento, em vez de agrupar a mesma causa vista em vários PDFs.

**Princípio.** Separar o que é **leitura** (por PDF, somente leitura sobre o código, paralelizável) do que é **correção** (por módulo, edita código, paralelizável só entre módulos disjuntos).

**Rodada → ondas → fases.** Uma rodada descobre o corpus e o divide em ondas de N PDFs (N = 3 por padrão, até 5). Em cada onda:

1. **Preparar (CLI, paralelo):** manifesto, renderização em visão geral + tiles com sobreposição, descarte automático de tiles em branco, inferência congelada de todos os métodos em processos paralelos.
2. **Ler (subagentes, paralelo):** um leitor visual por PDF lê os tiles PNG com a ferramenta Read e grava a referência regional; ele nunca recebe o caminho das inferências. A referência é validada e congelada por CLI (hash registrado).
3. **Medir (CLI):** comparador regional determinístico calcula TP_IA/FP_IA/FN_IA por família/método, com denominadores, só dentro das regiões revisadas.
4. **Auditar (subagentes, paralelo):** um auditor visual independente relê uma amostra estratificada de tiles (15% por padrão); a concordância decide se a referência é usável ou se a amostra precisa crescer.
5. **Agregar (CLI):** divergências de todos os PDFs da onda viram um backlog por causa (tipo × família × classe × método), priorizado por número de PDFs afetados, com o módulo dono de cada grupo.
6. **Corrigir (subagentes, paralelo por módulo):** uma pista de correção por módulo disjunto, cada uma em worktree próprio, com fixture sintética positiva/negativa antes do ajuste. A sessão orquestradora integra em série e roda os testes focados.
7. **Reinferir e fechar:** só os PDFs afetados pelos módulos alterados são reinferidos (em paralelo) e recomparados contra a mesma referência congelada.

No fim da rodada: código congelado, gates completos uma vez, reinferência paralela de todo o corpus para regressão e matriz de cobertura.

**Alavancas de velocidade e o que protege a precisão:**

| Alavanca | Ganho esperado | Salvaguarda de precisão |
|---|---|---|
| N PDFs por onda em paralelo | tempo de parede da onda ≈ o do PDF mais lento | leitura e inferência não editam código; correção só por módulo disjunto |
| Reuso de referência congelada para PDF com mesmo SHA-256 (H1) | PDF inalterado não é relido | auditoria amostral também cobre referências reutilizadas |
| Tiles em branco descartados por ocupação | menos imagens lidas pelo modelo | descarte registrado no índice; limiar conservador; auditor amostra também descartados |
| Referência regional em vez de censo integral obrigatório (H2) | o leitor declara o que viu em vez de varrer pixels sem conteúdo | métricas só dentro das regiões revisadas; sem recall global quando o escopo não é completo |
| Comparação, contagem e backlog por script | o modelo só investiga divergências | casamento pelo protocolo `symbols-e02-v1` (mesmo `geometry_match`) |
| Correções agrupadas por causa entre PDFs | uma correção resolve vários PDFs | fixture sintética autoral com positivo e negativos; sem memorizar nome/hash/coordenadas |
| Gates focados durante a onda, completos só no fechamento | menos execuções da suíte integral | reinferência de regressão de todo o corpus e gate completo antes de publicar a matriz |

**Invariantes herdados que continuam valendo:** ADR 0005 (PDFs reais e relatórios só em `tmp/curadoria-simbologia/`, nunca no Git nem em fixtures); referência congelada antes de comparar e o leitor sem acesso a predições; detector recebe só o PDF e a configuração normal; ambiguidade gera uma ocorrência com alternativas, nunca vários ativos; legenda/norte/§33 são informativos; referência gerada por IA não é gabarito, confirmação humana nem norma; reservas E16 seladas não são usadas para ajuste; métodos indisponíveis são falha, não zero; nenhum commit/publicação sem autorização.

**Adaptação ao Claude Code:** subagentes declarados em `.claude/agents/`, orquestração em `.claude/skills/curadoria-simbologia/SKILL.md`, leitura de imagens pela ferramenta Read (PNG), subagentes em segundo plano para paralelismo, `isolation: worktree` para pistas de correção, retomada após compactação pelo `rodada.json`, e permissões de projeto em `.claude/settings.json` para os CLIs da curadoria. Subagentes não disparam outros subagentes: toda a distribuição parte da sessão de nível superior que conduz a rodada. Agentes e skill criados durante uma sessão podem não estar registrados nela; a skill prevê o modo de reserva — disparar subagentes `general-purpose` com o corpo do arquivo do agente como instrução.

**Reaproveitamento sem histórico em documentação:** cada rodada vive inteira em `tmp/curadoria-simbologia/RODADA/` (manifesto, checkpoints, referências, comparações, relatório final). O que persiste no Git entre rodadas é só conhecimento e dados: código, pacotes, inventário, fixtures/testes e a matriz `docs/data/matriz-simbologia-curadoria-atual.csv` com seu resumo, que a rodada seguinte usa como ponto de partida. O contrato, a skill e os agentes descrevem o procedimento no presente e não registram rodadas executadas, resultados nem etapas deste roadmap.

**Layout da rodada** (todas sob `tmp/curadoria-simbologia/RODADA/`, fora do Git): `rodada.json` (corpus, ondas, N, checkpoint de código, rodada anterior), `pdfs/ORDEM-HASH12/checkpoint.json` (fase e histórico), `render/` (visão geral, tiles, `indice-tiles.json`), `referencia/` (versões `referencia-v001.json`…), `inferencia-vNNN/`, `comparacao-vNNN.json`, `auditoria/`, e por onda `ondas/K/backlog.json`.

## Escopo

**Incluído:** CLIs de rodada/onda/checkpoint, renderização com triagem, inferência paralela de arquivo único, formato e congelamento da referência regional, comparador regional, auditoria por dupla leitura amostral, backlog agregado, subagentes/skill/permissões do Claude Code, reescrita do contrato vivo sem histórico, a primeira rodada completa sobre todos os PDFs atuais de `examples/` (com as correções que ela justificar nos detectores, pacotes e testes) e o encerramento que apaga este roadmap.

**Fora de escopo:** alterar o protocolo `symbols-e02-v1` ou o avaliador; nova reserva independente ou aceite integrado; automação via ferramenta Workflow do Claude Code; medir o tempo do fluxo antigo (não há registro; o relatório local da rodada traz a primeira medição); limpar o histórico de etapas E05–E16 presente no `README.md` (documentação de produto, fora da curadoria).

## Restrições e invariantes

- Os invariantes herdados listados em "Desenho do fluxo-alvo" valem para toda etapa.
- Arquitetura: novos CLIs ficam em `scripts/` e podem importar `zeny_project_handler` e `scripts.*`; nada novo em `src/zeny_project_handler_client` nem em `src/zeny_project_handler_contracts`. `scripts/client_artifact_gate.py --source-only` continua passando.
- `scripts/symbol_benchmark_evaluator.py` e seu `PROTOCOL` não mudam; o comparador regional reutiliza `geometry_match`.
- Mudanças em `scripts/symbol_benchmark_runner.py` e `scripts/benchmark_symbols.py` são aditivas: os modos e saídas atuais continuam idênticos.
- Testes usam apenas fixtures sintéticas versionadas; nenhum teste depende de `examples/`.
- Preservar mudanças preexistentes do usuário, em particular `tests/fixtures/e10_characterization/` e `tests/unit/test_characterization_support.py` (não rastreados em 2026-10-15).
- Código e docs em português, como o restante do repositório; Ruff (linha 100), mypy strict e o gate de complexidade (CC < 31) valem para o código novo.
- Nenhum arquivo que permanece no repositório (código, skill, agentes, contrato, `CLAUDE.md`, `README.md`, `examples/README.md`) cita este roadmap, seus IDs de etapa ou resultados de rodada em prosa.
- O usuário optou por uma única execução sem pausas de revisão: nenhuma etapa tem revisão humana; a salvaguarda é o verificador independente obrigatório em toda etapa.

## Hipóteses e decisões em aberto

| # | Hipótese ou decisão | Impacto se errada / sem decisão | Etapa afetada |
|---|---|---|---|
| H1 | Reusar por padrão a referência congelada de um PDF cujo SHA-256 não mudou, com auditoria amostral; o fluxo atual exige reler tudo salvo autorização. | Se o usuário preferir reler tudo, `init` passa a marcar reuso só com `--reusar-referencias` explícito. | E01 |
| H2 | Referência regional (o leitor declara tiles revisados e regiões ilegíveis) substitui o censo integral obrigatório. | Se o censo integral for exigido, o leitor recebe todos os tiles e o comparador ainda funciona com escopo completo. | E04 |
| H3 | Tiles com lado maior de cerca de 1536 px rendem leitura legível pelo Claude sem redimensionamento agressivo; detalhe pequeno exige DPI maior em vez de tile maior. | Tamanho e DPI ficam configuráveis; a rodada de E11 ajusta se necessário. | E03, E11 |
| H4 | A máquina comporta 4 inferências simultâneas dos PDFs atuais (1 página cada; os dois maiores têm ~21 MB); 5 pode exigir mais memória. | `--jobs` padrão 3; a rodada usa N = 4 (4 ondas de 4 PDFs) e reduz se faltar memória, registrando no relatório local. | E02, E11 |
| H5 | Concordância de classe ≥ 0,90 na amostra auditada é suficiente para usar a referência; abaixo disso a amostra dobra uma vez e, persistindo, o PDF fecha com pendência. | Limiar configurável; a rodada registra a concordância observada no relatório local. | E06, E11 |
| H6 | Sintaxe de permissões `Bash(...)` em `.claude/settings.json` para liberar os CLIs; conferir com a skill `update-config` antes de escrever. | Permissões erradas só geram prompts extras, sem risco ao código. | E08 |
| H7 | Agentes e skill criados em E08 podem não ficar disponíveis por nome na mesma sessão que conduz E11. | A skill tem modo de reserva (subagente `general-purpose` com o corpo do arquivo do agente); E11 lê o `SKILL.md` diretamente. | E08, E11 |

## Definição global de pronto

- [ ] Os CLIs `scripts/curation_round.py`, `curation_render.py`, `curation_infer.py`, `curation_reference.py`, `curation_compare.py`, `curation_audit.py` e `curation_backlog.py` existem, têm testes unitários sintéticos e passam em Ruff, formatação e mypy.
- [ ] `benchmark_symbols examples` aceita um único PDF sem cópia para `input/`, com saídas idênticas às atuais nos modos existentes.
- [ ] `.claude/agents/` contém leitor visual, auditor visual, investigador, corretor e verificador da curadoria; `.claude/skills/curadoria-simbologia/SKILL.md` orquestra ondas de 3 a 5 PDFs citando apenas CLIs existentes.
- [ ] `docs/fluxo-curadoria-incremental-simbologia.md` descreve o fluxo por ondas, sem "GPT", "Codex" ou links da OpenAI e sem histórico de execução, preservando os invariantes; links Markdown sem quebras.
- [ ] `IniciarTestes.bat` aprovado e a matriz recalculada a partir do checkpoint anterior à rodada reproduz delta zero.
- [ ] A primeira rodada completa sobre todos os PDFs de `examples/` foi executada pela skill: todos os PDFs fechados ou encerrados com pendência, correções com fixtures/testes, gates completos aprovados e matriz de curadoria atual publicada em `docs/data/`; relatório com tempos, concordância e métricas somente em `tmp/`.
- [ ] Este roadmap foi apagado e nenhum arquivo restante o cita.

## Protocolo de execução

Vale para toda etapa, executada manualmente ou pelo orquestrador. Cada etapa declara sua estratégia em "Estratégia de execução".

**Papéis**

- **Sessão principal** (no modo automático, o subagente implementador): a única que edita código e este roadmap. Implementa, testa, atualiza tags e handoff.
- **Investigação** (subagente `Explore`, somente leitura): para material extenso que será lido mas não editado. Recebe as perguntas listadas na etapa e devolve um resumo com caminhos e linhas. Arquivos que serão editados são lidos diretamente pela sessão principal.
- **Implementação paralela** (subagentes `general-purpose`, só na estratégia `paralela`): cada um recebe uma parte com os arquivos listados na etapa, disjuntos dos demais; roda só os testes focados da sua parte; não toca arquivos compartilhados (build, configuração, este roadmap).
- **Verificação independente** (subagente `general-purpose` novo, que não participou da implementação): confere a etapa contra os critérios de aceite. Não edita nada.

**Estratégias:** `direta` — sem subagentes, a sessão principal valida · `padrão` — investigação quando indicada + verificação independente obrigatória · `paralela` — `padrão` + partes paralelas.

**Passo a passo**

1. **Preparação:** leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho deste roadmap, a seção da etapa e o handoff das dependências; rode `git status`. Confirme que as dependências estão `#concluida`, que a etapa não está `#bloqueada` e que o código bate com o handoff das dependências; se não, pare e relate.
2. **Snapshot inicial:** registre o estado da árvore de trabalho, sem commit e sem alterar o índice do git (no Git Bash):

   ```bash
   idx=$(mktemp -u); cp "$(git rev-parse --git-path index)" "$idx" 2>/dev/null; GIT_INDEX_FILE="$idx" git add -A && GIT_INDEX_FILE="$idx" git write-tree; rm -f "$idx"
   ```

   Anote o hash impresso como "Snapshot inicial" no handoff da etapa (no modo automático, use o hash recebido do orquestrador em vez de tirar outro). Para ver tudo o que a etapa mudou, rode o mesmo comando de novo e compare: `git diff HASH_INICIAL HASH_ATUAL`. Se `git status` mostrar artefatos de build não ignorados, corrija o `.gitignore` antes do snapshot — senão o diff fica lento e poluído.
3. **Início:** troque a tag da etapa para `#em-andamento` no índice e no título.
4. **Investigação** (se a etapa listar perguntas): dispare um subagente `Explore` com essas perguntas.
5. **Implementação:** quando os critérios descrevem comportamento verificável, escreva os testes primeiro e confirme que falham. Implemente em passos pequenos; na estratégia `paralela`, dispare as partes paralelas e integre-as. Rode as validações obrigatórias da etapa.
6. **Verificação independente** (`padrão` e `paralela`): dispare um subagente `general-purpose` novo com o "Prompt do verificador" abaixo, trocando ETAPA pelo ID da etapa e HASH_INICIAL pelo snapshot. Se o parecer for REPROVADO, corrija e verifique de novo com um verificador novo. Após duas reprovações, pare e relate, mantendo `#em-andamento`.
7. **Fechamento:** marque `#concluida` (índice e título) só com todos os critérios atendidos e, quando houver verificação, parecer APROVADO. Diante de impedimento real, marque `#bloqueada` e preencha "Bloqueios" com causa, evidência, impacto e ação de desbloqueio. Preencha "Evidências e handoff" e responda com um resumo curto. Não faça commit, push ou deploy.

**Prompt do verificador**

```text
Você é o verificador independente da etapa ETAPA do roadmap docs/roadmap-curadoria-simbologia-paralela.md. Você não participou da implementação e não deve editar nenhum arquivo.
1. Leia CLAUDE.md, o cabeçalho do roadmap (inclusive "Desenho do fluxo-alvo" e "Restrições e invariantes") e a seção ETAPA inteira (objetivo, escopo, fora de escopo, estratégia, critérios de aceite, validação obrigatória).
2. Veja o que mudou desde o início da etapa: gere um snapshot do estado atual com o comando da seção "Protocolo de execução" e rode git diff --stat HASH_INICIAL seguido do hash gerado; depois leia o diff completo dos arquivos relevantes.
3. Rode todos os comandos da validação obrigatória da etapa e guarde a saída relevante.
4. Para cada critério de aceite, decida APROVADO ou REPROVADO com evidência concreta (arquivo:linha, nome do teste, saída de comando). Critério sem evidência é REPROVADO.
5. Ataque os pontos listados em "Foco do verificador" na etapa e aponte também: mudanças fora do escopo, testes que não exercitam o comportamento (passariam mesmo com o código errado), PDFs ou caminhos privados versionados, segredos expostos e violações das restrições do roadmap.
Responda com: parecer geral (APROVADO só se todos os critérios forem APROVADO e não houver problema grave), tabela critério → resultado → evidência, problemas por gravidade e comandos executados.
```

## Execução automática

Cole o prompt abaixo numa sessão limpa do Claude Code, na raiz do repositório. Uma execução cobre o roadmap inteiro, inclusive a rodada de curadoria e o encerramento.

```text
Você é o orquestrador do roadmap docs/roadmap-curadoria-simbologia-paralela.md neste repositório. Nas etapas E01 a E10 seu papel é coordenar subagentes, não implementar: não edite código e mantenha seu contexto enxuto (leia o roadmap e os relatórios dos subagentes, não o código). A etapa E11 é a exceção descrita abaixo.

Esta execução deve cobrir todas as etapas, sem limite de quantidade e sem pausas de revisão humana.

Preparação:
1. Leia CLAUDE.md (e AGENTS.md, se existir) e, no roadmap, o cabeçalho (inclusive "Encerramento"), o "Protocolo de execução" e o índice.
2. Rode git status. Se alguma etapa estiver #em-andamento, retome-a: leia o handoff dela, gere um snapshot novo como HASH e continue pelo passo 3 com um implementador novo que recebe o handoff atual.

Para E01 a E10, repita, uma etapa por vez (nunca em paralelo):
1. Escolha a primeira etapa, na ordem do documento, marcada #pendente e com todas as dependências #concluida. Etapas #bloqueada e as que dependem delas ficam para trás.
2. Gere o snapshot inicial com o comando do protocolo e guarde o hash.
3. Dispare um subagente general-purpose com o prompt da etapa copiado literalmente da seção dela, acrescido deste adendo: "Você está rodando como subagente do orquestrador; este adendo prevalece sobre o prompt acima. O snapshot inicial já foi tirado: use HASH e não tire outro. Não dispare subagentes: faça a investigação você mesmo, implemente em sequência as partes paralelas, se houver, e pule a verificação independente, que o orquestrador fará. Não marque a etapa como #concluida: ao terminar, deixe-a #em-andamento com 'Evidências e handoff' preenchido e relate o resultado das validações. Diante de bloqueio real, marque #bloqueada como o prompt manda." Substitua HASH pelo hash do passo 2.
4. Se o subagente relatar bloqueio, divergência do plano ou validação falhando que não conseguiu resolver, pare.
5. Qualquer que seja a estratégia, dispare um subagente general-purpose novo com o "Prompt do verificador" do protocolo (ETAPA e HASH_INICIAL preenchidos). Se REPROVADO, mande os problemas ao mesmo implementador, se puder retomá-lo; senão, dispare um implementador novo com o prompt da etapa, o adendo, o parecer do verificador e o handoff atual. Verifique de novo com um verificador novo; após duas reprovações, pare.
6. Com o aceite, troque a tag da etapa para #concluida no índice e no título e acrescente ao handoff o parecer do verificador.

E11 (rodada de curadoria): subagentes não conseguem disparar outros subagentes, e a rodada precisa de leitores, auditores e corretores em paralelo. Por isso você mesmo conduz E11 como a sessão principal: gere o snapshot, siga o prompt de E11 e o arquivo .claude/skills/curadoria-simbologia/SKILL.md lido diretamente, dispare os subagentes que a skill pede (usando o modo de reserva da skill se os agentes de .claude/agents/ não estiverem registrados nesta sessão) e, ao terminar, dispare o verificador independente de E11. Use o rodada.json da skill para retomar após compactação. Com parecer APROVADO, execute a seção "Encerramento" do roadmap; ela apaga o roadmap, então não há tag a atualizar depois.

Pare antes do fim só por bloqueio real, divergência do plano ou duas reprovações seguidas do verificador. Nunca faça commit, push ou deploy e não altere tags de etapas que não executou.

Ao terminar ou parar, responda com: etapas concluídas e seus pareceres, a etapa atual e seu estado (se parou), o motivo da parada, os resultados da rodada (PDFs fechados e com pendência, concordância, TP_IA/FP_IA/FN_IA com denominadores, correções feitas, delta de cobertura, tempos por fase e o caminho do relatório local em tmp/), os arquivos alterados (git status --short) e o próximo passo sugerido — normalmente revisar o diff e fazer commit.
```

## Índice de etapas

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Rodada, ondas e checkpoints | #concluida | — | `scripts/curation_round.py` com manifesto, ondas, reuso por hash e máquina de fases |
| E02 | Inferência de arquivo único em paralelo | #concluida | E01 | opção de PDF único no runner e `scripts/curation_infer.py` com processos paralelos (paralelizável com a renderização) |
| E03 | Renderização e triagem de tiles | #concluida | E01 | `scripts/curation_render.py` com visão geral, tiles com sobreposição e descarte de brancos |
| E04 | Referência visual regional | #concluida | E03 | esquema, validação, congelamento e versionamento da referência |
| E05 | Comparador regional | #concluida | E02, E04 | `scripts/curation_compare.py` com TP_IA/FP_IA/FN_IA e divergências rastreáveis |
| E06 | Auditoria por dupla leitura amostral | #concluida | E04 | `scripts/curation_audit.py` com amostra estratificada e concordância |
| E07 | Backlog agregado por onda | #concluida | E05 | `scripts/curation_backlog.py` agrupando divergências por causa e módulo dono |
| E08 | Integração com Claude Code | #concluida | E06, E07 | subagentes, skill `/curadoria-simbologia` e permissões de projeto |
| E09 | Contrato vivo do fluxo por ondas | #concluida | E08 | reescrita de `docs/fluxo-curadoria-incremental-simbologia.md` e referências |
| E10 | Gate técnico final | #concluida | E09 | suíte completa e matriz com delta zero |
| E11 | Primeira rodada completa de curadoria | #bloqueada | E10 | todos os PDFs de `examples/` curados pelo fluxo novo, correções testadas e matriz de curadoria publicada |

---

## E01 — Rodada, ondas e checkpoints — #concluida

**Objetivo:** criar `scripts/curation_round.py`, a base que todos os outros CLIs usam: descobre o corpus, divide em ondas de N PDFs, detecta reuso por hash e mantém um checkpoint por PDF com transições de fase validadas.

**Por que agora:** layout de diretórios, identificadores de PDF e fases são o contrato que as demais etapas leem e escrevem; errar aqui se propaga a tudo.

**Dependências e paralelismo:** nenhuma. Não paraleliza com outras etapas.

**Escopo:**

- `scripts/curation_round.py` (a criar), executável como `python -m scripts.curation_round`, com subcomandos:
  - `init --rodada DIR --raiz examples --concorrencia N [--anterior DIR] [--reusar-referencias|--sem-reuso]`: descobre PDFs recursivamente (inclusive `.PDF`), ordena pelo caminho relativo sem diferenciar maiúsculas, registra SHA-256, tamanho, páginas (PyMuPDF), duplicatas por hash sem omitir caminhos, estado novo/modificado/inalterado frente à rodada anterior e o checkpoint de código (snapshot `git write-tree` com índice temporário + digest de `src/zeny_project_handler/adapters/analysis/symbol_packages/`). Divide em ondas de N (1 ≤ N ≤ 5). Cria `pdfs/ORDEM-HASH12/checkpoint.json` para cada PDF. Com reuso (padrão, H1), PDF inalterado com referência congelada na rodada anterior recebe cópia da referência, verificada por hash, e entra em `referencia_congelada` com origem `reuso`.
  - `status --rodada DIR [--onda K]`: tabela de PDFs por fase e pendências.
  - `avancar --rodada DIR --pdf ID --fase FASE [--artefato CAMINHO ...] [--nota TEXTO]`: transição validada, grava hash dos artefatos e histórico com horário.
- Fases: `preparado`, `renderizado`, `inferido`, `referencia_congelada`, `comparado`, `auditado`, `em_correcao`, `fechado`, `encerrado_com_pendencias`. `inferido` e `referencia_congelada` podem ocorrer em qualquer ordem; `comparado` exige as duas; `fechado` exige `comparado` e `auditado`.
- Escrita atômica (arquivo temporário + `os.replace`); cada PDF tem seu próprio checkpoint para que agentes paralelos não disputem o mesmo arquivo; `rodada.json` só é reescrito por `init` e pelo orquestrador.
- Biblioteca reutilizável (funções para carregar rodada, localizar diretório do PDF e transicionar) que os demais CLIs importam.
- Testes em `tests/unit/test_curation_round.py` (a criar), com PDFs sintéticos de `tests/pdf_fixtures.py` em `tmp_path`.

**Fora de escopo:** renderizar, inferir, comparar; alterar `examples/`; qualquer dado em `docs/data/`.

**Passos de implementação:**

1. Testes para descoberta/ordenação/duplicatas, divisão em ondas, reuso por hash (e recusa quando o hash da referência anterior diverge), transições válidas e inválidas, escrita atômica.
2. Implementar descoberta, manifesto, checkpoint de código e ondas.
3. Implementar máquina de fases e `avancar`/`status`.

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação (`Explore`): "quais funções de hash, escrita JSON e identidade de documento `scripts/symbol_benchmark_runner.py` já oferece (`file_sha256`, `write_json`, `_identity`) e qual o formato de `document_id` no modo examples?"; "como `tests/pdf_fixtures.py` gera PDFs sintéticos com N páginas?".
- Partes paralelas: nenhuma.
- Foco do verificador: transição inválida aceita; reuso de referência com hash divergente; duplicatas por hash omitidas ou contadas como um só; caminho absoluto ou privado gravado fora de `tmp/`; ordenação não determinística.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E01 — "Rodada, ondas e checkpoints" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Desenho do fluxo-alvo", "Restrições e invariantes" e o "Protocolo de execução" — e a seção E01 inteira. Rode git status e preserve mudanças preexistentes que não sejam suas (em especial tests/fixtures/e10_characterization/ e tests/unit/test_characterization_support.py). Esta etapa não tem dependências; se o código divergir do que o roadmap descreve, pare e relate sem implementar.

Objetivo: criar scripts/curation_round.py (init, status, avancar) com manifesto do corpus, ondas de 1 a 5 PDFs, reuso de referência por SHA-256 e checkpoint por PDF com máquina de fases validada e escrita atômica. Não toque em detectores, no avaliador, em docs/data/ nem em examples/.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E01 para #em-andamento no índice e no título;
- investigação: um subagente Explore responde às perguntas listadas em "Estratégia de execução" de E01;
- escreva tests/unit/test_curation_round.py primeiro, com PDFs sintéticos em tmp_path, e confirme que falham; depois implemente;
- verificação independente com o Prompt do verificador, com foco em transições inválidas, reuso com hash divergente, duplicatas e determinismo.

Critérios de aceite (detalhes na seção E01):
- init gera rodada.json e um checkpoint por PDF com ondas do tamanho pedido, duplicatas listadas e reuso só com hash conferido;
- avancar recusa transições inválidas e grava hash dos artefatos;
- testes, Ruff, formatação e mypy passam.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com todos os critérios atendidos e parecer APROVADO do verificador; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E01 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador, notas para a próxima etapa — inclusive a API da biblioteca que as próximas etapas devem importar) e responda com um resumo curto de mudanças, validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] `init` sobre um diretório com 4 PDFs sintéticos (um duplicado por hash) e `--concorrencia 3` gera 2 ondas, lista o duplicado com ambos os caminhos e cria 4 checkpoints em `fase = preparado`.
- [ ] Com `--anterior` apontando para uma rodada com referência congelada do mesmo hash, o PDF entra em `referencia_congelada` com origem `reuso`; com hash de referência adulterado, `init` falha com mensagem explícita; com `--sem-reuso`, nenhum PDF é reutilizado.
- [ ] `avancar` para `comparado` sem `inferido` e `referencia_congelada` termina com código ≠ 0 e não altera o checkpoint.
- [ ] Concorrência fora de 1–5 é recusada.
- [ ] Testes novos, Ruff, formatação e mypy passam.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_round.py -q` → todos passam.
- `.venv/Scripts/python.exe -m ruff check .` e `.venv/Scripts/python.exe -m ruff format --check .` → sem erros.
- `.venv/Scripts/python.exe -m mypy` → sem erros.
- Inspeção manual: `rodada.json` de um teste não contém caminhos absolutos fora da rodada.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Snapshot `git write-tree` falha fora de um repositório git → registrar `checkpoint_codigo: indisponivel` com motivo em vez de abortar, e testar esse caminho.

**Evidências e handoff:**

- Snapshot inicial: `22395d77b4ad37eee97e675027a528cb28e97fbc` (recebido do orquestrador). Snapshot ao fim da implementação: `823e8855e55d86d1e985a65175f0059335baede9`.
- Arquivos alterados: `scripts/curation_round.py` (novo), `tests/unit/test_curation_round.py` (novo, 50 casos), este roadmap (tags e handoff de E01). `tests/fixtures/e10_characterization/` e `tests/unit/test_characterization_support.py` preservados intactos.
- Decisões:
  - Investigação feita diretamente (adendo do orquestrador): `scripts/symbol_benchmark_runner.py` oferece `canonical_json`/`write_json` (JSON ordenado, `indent=2`, sem NaN, escrita **não** atômica), `file_sha256` (lê o arquivo inteiro) e `_identity` (bytes, mtime, SHA-256); no modo examples `document_id = "example:" + caminho relativo POSIX à raiz`, com ordenação por `casefold`. `tests/pdf_fixtures.py` não tem gerador de N páginas: os testes usam `create_feature_pdf` (3 páginas) e `create_catalog_pdf(path, code)` (1 página, conteúdo distinto por código).
  - O módulo **não importa** o runner (que carrega todos os detectores): reimplementa a mesma serialização canônica (`json_canonico`) e hash em fluxo. Só depende de stdlib e PyMuPDF (contagem de páginas).
  - ID do PDF: `ORDEM-HASH12`, ordem com 3 dígitos (cresce se houver mais de 999 PDFs). Ordenação por (`casefold`, caminho exato) para desempate determinístico. Duplicatas por hash recebem IDs, checkpoints e ondas próprios e são listadas em `duplicatas` com todos os caminhos e IDs.
  - Caminhos gravados são sempre relativos ao diretório da rodada: `raiz_corpus` (ex.: `../corpus`), `rodada_anterior.caminho`, artefatos (`pdfs/ID/...`). Corpus e rodada em unidades diferentes no Windows → erro explícito. Mensagens de checkpoint de código são saneadas para não gravar o caminho do repositório.
  - Estado frente à anterior é por caminho relativo + SHA-256 (`novo`/`modificado`/`inalterado`); reuso (padrão) só para `inalterado` cujo checkpoint anterior tem `referencia`. O arquivo é lido uma vez, o hash desses bytes é conferido contra o registrado, a cópia vira `pdfs/NOVO_ID/referencia/referencia-v001.json` e é re-hasheada. Hash divergente ou arquivo ausente abortam o `init` com mensagem que cita o caminho do PDF. A referência reutilizada mantém o conteúdo original (inclusive o `pdf_id` antigo, se houver); a identidade confiável é o SHA-256 do PDF.
  - `init` monta a rodada num diretório irmão temporário e só o renomeia para o destino no fim: falha não deixa rodada parcial. Recusa destino com `rodada.json` ou não vazio, corpus sem PDFs e concorrência fora de 1–5.
  - Checkpoint de código: `git write-tree` com índice temporário (cópia do índice real + `git add -A`; índice real intocado, conferido com `git ls-files -s` antes/depois) e digest de (caminho, SHA-256) dos arquivos de `symbol_packages/` sem `__pycache__`. Indisponível → valor `indisponivel` e campo `motivo`, sem abortar.
  - Máquina de fases (marcos válidos + invalidação): `renderizado` e `inferido` sem requisitos; `referencia_congelada` exige `renderizado` (o reuso entra por `init` sem render); `comparado` exige `inferido` + `referencia_congelada`; `auditado` exige `renderizado` + `referencia_congelada`; `em_correcao` exige `comparado`; `fechado` exige `comparado` + `auditado`; `encerrado_com_pendencias` exige `--nota`. Fases terminais não aceitam nada; `preparado` só via `init`. Reentrar em `inferido` (nova versão), `referencia_congelada` (revisão) ou `em_correcao` invalida `comparado`, forçando nova comparação antes de fechar; `auditado` não é invalidado pela revisão da referência. `renderizado` pode se repetir até a referência ser congelada; depois disso é recusado (os tiles são a base da referência), salvo a primeira renderização de um PDF com referência reutilizada.
  - `referencia_congelada` via `avancar` exige exatamente um artefato arquivo em `pdfs/ID/referencia/referencia-vNNN.json` e preenche `checkpoint.referencia` (`origem` `leitura` por padrão; `revisao` aceito pela biblioteca; `reuso` só via `init`).
  - Concorrência no mesmo PDF (render e inferência em paralelo): trava por checkpoint (`checkpoint.json.lock` com `O_EXCL`, espera até 30 s, erro explícito depois) + escrita atômica (temporário no mesmo diretório, `fsync`, `os.replace` com novas tentativas curtas para `PermissionError` no Windows). Exceções renomeadas para o padrão do Ruff (`N818`): `RodadaError` e `TransicaoInvalidaError`.
- Validações executadas:
  - Testes escritos antes do módulo: `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_round.py -q` falhou com `ModuleNotFoundError: No module named 'scripts.curation_round'`; após a implementação → `50 passed`.
  - `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`; `-m ruff format --check .` → `450 files already formatted`.
  - `.venv/Scripts/python.exe -m mypy` → 2 erros, ambos em `tests/unit/test_characterization_support.py` (arquivo não rastreado preexistente do usuário: importa `tests.characterization`, que não existe, e um `no-any-return`); nenhum erro nos arquivos de E01. `-m mypy --exclude 'test_characterization_support\.py$'` → `Success: no issues found in 406 source files`. O mesmo arquivo também falha na coleta do pytest; não foi alterado (restrição de preservação).
  - Radon: maior CC do módulo novo é 12 (`validar_transicao`); `scripts/client_artifact_gate.py --source-only` → APROVADO.
  - Inspeção manual: `init` via `python -m scripts.curation_round` sobre 4 PDFs sintéticos em `tmp/roadmap-e01/` (removido depois) gerou 2 ondas (3+1), duplicata com os dois caminhos, `git_write_tree` real e `rodada.json` sem `C:`/`Users`/caminho absoluto; `avancar` para `comparado` saiu com código 1 citando os marcos faltantes; `avancar --artefato --nota` e `status`/`status --json` conferidos. O teste `test_rodada_json_nao_grava_caminhos_absolutos` automatiza a inspeção.
- Parecer do verificador: APROVADO (verificador independente do orquestrador; snapshot de verificação f03c3010b6c6d253380f23b651e5f4a63ec28408). 5/5 critérios aprovados: 50 testes passam, Ruff/formatação limpos, mypy limpo exceto os 2 erros preexistentes em tests/unit/test_characterization_support.py (arquivo do usuário, presente no snapshot inicial; mypy com ele excluído: Success em 406 arquivos), rodada.json sem caminhos absolutos, 13/15 mutações detectadas. Ressalvas menores: ordenação sem diferenciar maiúsculas não tem teste que a distinga; requisito renderizado→referencia_congelada sem teste dedicado; revisar a referência não invalida auditado (E06 deve reavaliar); acentos corrompidos no stderr do Git Bash.
- Notas para a próxima etapa:
  - API a importar de `scripts.curation_round`: `iniciar_rodada(rodada_dir, raiz, *, concorrencia, anterior=None, reusar_referencias=True, raiz_repositorio=ROOT, agora=None)`; `carregar_rodada(rodada_dir)`; `selecionar_pdfs(rodada_dir, *, onda=None, pdf_ids=())` (implementa `(--onda K | --pdf ID ...)`); `pdfs_da_onda(rodada, numero)`; `diretorio_pdf(rodada_dir, pdf_id)` → `RODADA/pdfs/ID` (valida o ID); `caminho_pdf_fonte(rodada_dir, pdf_id)` → PDF original absoluto; `raiz_corpus(rodada_dir)`; `carregar_checkpoint(rodada_dir, pdf_id)`; `transicionar(rodada_dir, pdf_id, fase, *, artefatos=(), nota=None, dados=None, origem_referencia="leitura", agora=None)` → checkpoint novo (recusa com `TransicaoInvalidaError` sem alterar nada); `validar_transicao(checkpoint, fase, *, nota=None)`; `registrar_artefato(rodada_dir, caminho)`; `checkpoint_codigo(raiz_repositorio=ROOT, *, git_executavel="git")`; `escrever_json_atomico`, `escrever_bytes_atomico`, `json_canonico`, `ler_json`, `hash_arquivo`, `hash_diretorio`, `hash_artefato`; `resumo_status(rodada_dir, *, onda=None)`; constantes `FASES`, `FASES_TERMINAIS`, `REQUISITOS`, `INVALIDA`, `CONCORRENCIA_MAXIMA`; exceções `RodadaError` e `TransicaoInvalidaError`.
  - `rodada.json` (`curadoria-rodada-v1`): `checkpoint_codigo` {`git_write_tree`, `digest_pacotes`, `caminho_pacotes`, `motivo`?}, `concorrencia`, `criada_em`, `duplicatas` [{`sha256`, `caminhos`, `pdf_ids`}], `ondas` [{`numero`, `pdfs`}], `pdfs` [{`pdf_id`, `ordem`, `onda`, `caminho_relativo`, `sha256`, `bytes`, `paginas`, `erro_paginas`, `estado_frente_anterior`, `reuso_referencia`}], `raiz_corpus`, `reuso_referencias`, `rodada_anterior` ({`caminho`, `criada_em`, `checkpoint_codigo`} ou `null`), `totais`.
  - `checkpoint.json` (`curadoria-checkpoint-v1`): `pdf_id`, `ordem`, `onda`, `caminho_relativo`, `sha256`, `fase`, `marcos` {fase: {`horario`, `artefatos`}} (só marcos válidos), `referencia` ({`origem`, `arquivo`, `versao`, `sha256`, `horario`, `rodada_anterior`?} ou `null`) e `historico` [{`de`, `para`, `horario`, `artefatos` [{`caminho`, `tipo` arquivo|diretorio, `sha256`, `bytes`, `arquivos`?}], `nota`, `dados`}].
  - E02/E03 devem chamar `transicionar(..., "inferido"/"renderizado", artefatos=[pasta_ou_indice])` com artefatos dentro da rodada; E04 `congelar` deve gravar `pdfs/ID/referencia/referencia-v001.json` e chamar `transicionar(..., "referencia_congelada", artefatos=[arquivo])`; `revisar` passa `origem_referencia="revisao"` e pode registrar a exposição em `dados`.
  - Pendência fora do escopo de E01: `mypy` e a coleta do pytest falham por `tests/unit/test_characterization_support.py` (não rastreado, preexistente, depende de `tests.characterization` ausente). Cabe ao usuário completar ou remover esse arquivo; E10 (gate final) será afetada se ele continuar assim.

---

## E02 — Inferência de arquivo único em paralelo — #concluida

**Objetivo:** permitir inferir um único PDF sem copiá-lo para uma pasta isolada e executar a inferência de todos os PDFs de uma onda em processos paralelos, com checkpoint de código e custos registrados.

**Por que agora:** a cópia para `input/` e a inferência sequencial são dois dos maiores custos mecânicos do fluxo atual.

**Dependências e paralelismo:** E01. Pode correr em paralelo com E03 (em worktree separado); não há arquivo em comum.

**Escopo:**

- `scripts/benchmark_symbols.py` e `scripts/symbol_benchmark_runner.py`: no modo `examples`, nova opção `--pdf CAMINHO` (repetível), mutuamente exclusiva com a descoberta por pasta; `--root` passa a ser a base de identidade, de modo que o `document_id` continua `example:` + caminho relativo à raiz. Sem `--pdf`, comportamento e saída idênticos aos atuais.
- `scripts/curation_infer.py` (a criar): `--rodada DIR (--onda K | --pdf ID ...) --jobs N [--metodos ...] [--pipeline] [--native-only]`. Para cada PDF, roda em subprocesso `benchmark_symbols examples --root RAIZ --pdf ARQUIVO --output pdfs/ID/inferencia-vNNN/simbolos` com todos os `--include-*` por padrão e, com `--pipeline`, `benchmark_network_pdf` em `inferencia-vNNN/pipeline.json`. Limita a N processos simultâneos (padrão 3, máximo 5). Grava `inferencia-vNNN/execucao.json` com checkpoint de código, comando, duração, código de saída e falhas; falha de um PDF não interrompe os demais. Avança o checkpoint para `inferido` só em sucesso; versões nunca são sobrescritas.
- Testes em `tests/unit/test_benchmark_symbols.py` (opção `--pdf`) e `tests/unit/test_curation_infer.py` (a criar), com o comando de inferência injetável para não executar detectores reais.

**Fora de escopo:** alterar detectores ou métodos; mudar formato de `predictions.json`/`manifest.json`; OCR complementar por padrão.

**Passos de implementação:**

1. Teste de regressão: saída do modo `examples` sem `--pdf` sobre fixtures sintéticas permanece igual.
2. Teste e implementação de `--pdf` com identidade relativa à raiz.
3. Testes e implementação de `curation_infer.py` com executor injetável, limite de concorrência, falha isolada e versionamento.

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação (`Explore`): "quais campos de `manifest.json` e `predictions.json` dependem da raiz de descoberta em `run_examples`/`_run` (`scripts/symbol_benchmark_runner.py:1178` e `:1395`)?"; "quais testes de `tests/unit/test_benchmark_symbols.py` cobrem o modo examples?".
- Partes paralelas: nenhuma.
- Foco do verificador: regressão na saída do modo examples sem `--pdf`; `document_id` diferente do atual para o mesmo arquivo; concorrência acima do limite; falha de um PDF derrubando a onda; sobrescrita de versão anterior.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E02 — "Inferência de arquivo único em paralelo" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Restrições e invariantes" e o "Protocolo de execução" —, a seção E02 inteira e o "Evidências e handoff" de E01. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E01 está #concluida e que scripts/curation_round.py bate com o handoff; se não, ou se o código divergiu do plano, pare e relate sem implementar.

Objetivo: adicionar --pdf ao modo examples de scripts/benchmark_symbols.py (identidade relativa a --root, saída atual inalterada sem a opção) e criar scripts/curation_infer.py, que infere os PDFs de uma onda em até N processos paralelos, registra checkpoint de código, durações e falhas, e avança o checkpoint para inferido. Não altere detectores, o avaliador nem o formato das saídas.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E02 para #em-andamento no índice e no título;
- investigação: um subagente Explore responde às perguntas de "Estratégia de execução" de E02;
- escreva primeiro o teste de regressão do modo examples e os testes de curation_infer com executor injetável; depois implemente;
- verificação independente com o Prompt do verificador, com foco em regressão do modo examples, document_id, limite de concorrência e falha isolada.

Critérios de aceite (detalhes na seção E02):
- examples sem --pdf produz saída idêntica à anterior; com --pdf, o document_id é o mesmo da descoberta por pasta;
- curation_infer respeita --jobs, isola falhas e nunca sobrescreve versão;
- testes, Ruff, formatação e mypy passam.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com todos os critérios atendidos e parecer APROVADO do verificador; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E02 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador, notas para a próxima etapa) e responda com um resumo curto de mudanças, validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] Sobre as fixtures sintéticas, `benchmark_symbols examples --root DIR` produz `predictions.json` e `manifest.json` idênticos (excluindo carimbos de tempo/duração já variáveis hoje) aos produzidos antes da mudança.
- [ ] `benchmark_symbols examples --root DIR --pdf DIR/sub/a.pdf` gera só `a.pdf`, com `document_id` `example:sub/a.pdf`.
- [ ] `curation_infer --jobs 2` com 3 PDFs e executor injetável nunca tem mais de 2 execuções simultâneas (verificado no teste); uma falha simulada marca só aquele PDF e os outros chegam a `inferido`.
- [ ] Segunda execução cria `inferencia-v002` sem tocar `inferencia-v001`.
- [ ] Testes, Ruff, formatação e mypy passam.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_symbols.py tests/unit/test_curation_infer.py tests/unit/test_curation_round.py -q` → todos passam.
- `.venv/Scripts/python.exe -m ruff check .`, `-m ruff format --check .`, `-m mypy` → sem erros.
- `.venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output tmp/roadmap-e02/sintetico` → termina com código 0.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Memória com 5 processos (H4) → padrão 3 e registro de pico de memória quando disponível; a rodada de E11 calibra.

**Evidências e handoff:**

- Snapshot inicial: `84b5a9783ce19ba2508bea01290755d9e947fc1b` (recebido do orquestrador). Snapshot ao fim da implementação (antes deste handoff): `5a75356bd9714bb53b03aceb7a79f0a505b54cd2`.
- Arquivos alterados: `scripts/symbol_benchmark_runner.py` (nova `select_example_pdfs`, parâmetro `pdfs` em `run_examples`), `scripts/benchmark_symbols.py` (opção `--pdf` no modo `examples`), `scripts/curation_infer.py` (novo), `tests/unit/test_benchmark_symbols.py` (+9 casos), `tests/unit/test_curation_infer.py` (novo, 21 casos), este roadmap (tags e handoff de E02). `tests/fixtures/e10_characterization/`, `tests/unit/test_characterization_support.py` e `scripts/curation_round.py` intocados.
- Decisões:
  - Preparação: E01 `#concluida`; `scripts/curation_round.py` confere com o handoff de E01 (`selecionar_pdfs`, `diretorio_pdf`, `caminho_pdf_fonte`, `raiz_corpus`, `transicionar`, `validar_transicao`, `checkpoint_codigo`, `escrever_json_atomico`, `json_canonico`, `hash_arquivo`; `REQUISITOS["inferido"] = ()`, `INVALIDA["inferido"] = ("comparado",)`). Investigação feita diretamente (adendo do orquestrador): em `run_examples`/`_run` dependem da raiz `documents[].id` (`example:` + relativo POSIX), `documents[].path` (absoluto resolvido), `discovery_root`/`discovery_root_exists` e a ordenação por `casefold` do relativo; entre execuções idênticas variam só `seconds`, `memory.*`, `legend_reference.seconds` e, por consequência, `predictions_sha256`. Testes que já cobriam o modo examples: `test_runner_recurses_all_pages_and_keeps_equal_content_paths_distinct`, `test_runner_records_unreadable_source_and_continues_other_pdfs`, `test_empty_examples_are_explicit_and_do_not_claim_completion`.
  - `--pdf` (repetível; caminhos relativos ao diretório atual) troca a descoberta por pasta pela lista explícita; `--root` continua a base de identidade. Validação antes de rodar (`select_example_pdfs`): raiz existente, arquivo existente, sufixo `.pdf` sem caixa, dentro de `--root` após `resolve()`, sem repetição; a CLI converte o erro em `parser.error` (código 2) sem criar a saída. A lista é ordenada pela mesma chave da descoberta, e o `resolve()` normaliza a caixa no Windows (`EXAMPLES/SUB/COPIA.PDF` → `example:sub/copia.pdf`, conferido à mão). Só com `--pdf` o manifesto ganha o campo aditivo `explicit_pdfs` (relativos POSIX); sem `--pdf` não há campo novo.
  - Regressão sem `--pdf`: além dos testes, comparação diferencial com o runner anterior (HEAD) sobre 6 PDFs sintéticos (aninhados, `.PDF`, cópia byte a byte), sem opções e com os seis `--include-*`: `predictions.json` e `manifest.json` só diferem em `seconds`, `memory.*`, `predictions_sha256` (já variáveis hoje) e em `environment.runner_sha256_lf`, o hash do próprio arquivo do runner, que muda por definição com qualquer edição dele (procedência, não formato de saída). Com `--pdf`, a visão do documento (predições, execuções, entrada do manifesto, métodos) é idêntica à da descoberta por pasta para o mesmo arquivo.
  - `curation_infer`: `ThreadPoolExecutor(max_workers=jobs)` em que cada tarefa é um PDF e roda suas etapas (símbolos e, com `--pipeline`, `benchmark_network_pdf`) em série, então nunca há mais de N subprocessos. `--jobs` 1–5 (padrão 3); `--metodos` (nargs `*`, padrão os seis opcionais; o método legado sempre roda; `--legend-ocr` e `--complementary-ocr` nunca são passados); `--native-only` exige `--pipeline`. O executor é um `Protocol` `(comando, *, cwd, log) -> ResultadoComando(codigo_saida)` injetável em `inferir()` e `main()`.
  - Por PDF: valida a transição para `inferido` antes de tudo (fase terminal → `recusado`, sem criar versão); reserva `inferencia-vNNN` com `mkdir` exclusivo depois da maior existente (nome ocupado por diretório ou arquivo nunca é reutilizado, nem após falha); confere o SHA-256 do PDF fonte com o checkpoint antes de rodar; depois de cada etapa exige código 0 e as saídas (`simbolos/predictions.json` + `manifest.json`, com `documents` igual a exatamente `example:` + `caminho_relativo` e o SHA-256 do checkpoint; `pipeline.json`). Qualquer exceção vira falha só daquele PDF. `execucao.json` (`curadoria-inferencia-v1`) é gravado de forma atômica antes de `transicionar(..., "inferido", artefatos=[versao], dados={versao, execucao})`; se a transição for recusada, o registro é regravado como falha.
  - `execucao.json` grava comandos sem caminhos locais (`python` no lugar do executável; caminhos relativos à rodada, ex.: `../corpus/sub/a.pdf`, `pdfs/ID/inferencia-v001/simbolos`), `checkpoint_codigo` (calculado uma vez por chamada), `jobs`, `metodos`, `pipeline`, `native_only`, `iniciado_em`/`concluido_em`, `duracao_s` total e por etapa, `codigo_saida`, `log` (`simbolos.log`/`pipeline.log` com stdout+stderr), `falhas` e `status` `sucesso|falha`.
  - Memória: tentei medir o pico nativo do subprocesso com Job Object do Windows, mas o `python.exe` do venv é um lançador cujo interpretador real escapa do job (conferido: `TotalProcesses = 1` e ~2 MB pelo lançador; ~206 MB com `sys._base_executable`). Para não gravar número enganoso, a etapa `simbolos` registra `memoria_python_pico_bytes` (maior `memory.python_peak_bytes` do manifesto do runner, tracemalloc) com `escopo_memoria` explícito (exclui MuPDF nativo/RSS). O pico nativo segue indisponível; E11 calibra H4 observando a máquina.
  - Saída da CLI: JSON canônico `{jobs, pdfs: [{pdf_id, versao, status, falhas, duracao_s}], totais: {sucesso, falha, recusado}}` na ordem pedida; código 0 só se todos tiverem sucesso, 1 caso contrário ou em erro de uso (`RodadaError`).
- Validações executadas:
  - Testes escritos antes do código: os de `--pdf` falharam (`TypeError: run_examples() got an unexpected keyword argument 'pdfs'` e argparse recusando `--pdf`); o de regressão sem `--pdf` passou já contra o código antigo, como deve; `tests/unit/test_curation_infer.py` falhou na coleta (`ModuleNotFoundError: scripts.curation_infer`). Depois da implementação: `.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_symbols.py tests/unit/test_curation_infer.py tests/unit/test_curation_round.py -q` → `129 passed`.
  - Testes ligados aos critérios: `test_examples_cli_without_pdf_keeps_discovery_sources_and_output_format` (fontes passadas a `_run`, conjunto exato de chaves de `manifest.json`/`predictions.json`, ids, caminhos e igualdade CLI × biblioteca), `test_examples_pdf_option_runs_only_selected_file_with_folder_document_id` (`--pdf DIR/sub/a.pdf` → só `example:sub/a.pdf`, visão igual à da pasta), `test_examples_pdf_option_accepts_cwd_relative_paths_and_orders_like_discovery`, `test_examples_pdf_option_rejects_invalid_selection_without_running[...]`; `test_jobs_limita_concorrencia_e_falha_isolada` (3 PDFs, `jobs=2`: máximo simultâneo observado = 2; um PDF falha e fica `preparado`, os outros chegam a `inferido`), `test_jobs_um_executa_em_serie`, `test_pipeline_conta_como_o_mesmo_processo_do_pdf`, `test_segunda_execucao_cria_v002_sem_tocar_v001` (hash do diretório e bytes de `execucao.json` da v001 iguais), `test_versao_com_falha_tambem_nao_e_reutilizada`, `test_reserva_concorrente_gera_versoes_distintas`, `test_excecao_do_executor_fica_isolada_no_pdf`, `test_saida_ausente_ou_inconsistente_e_falha[...]`, `test_pdf_alterado_desde_init_falha_sem_executar`, `test_fase_terminal_recusa_sem_criar_versao`, `test_jobs_fora_do_intervalo_e_recusado[0/6]`, testes da CLI e do executor padrão.
  - `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`; `-m ruff format --check .` → `452 files already formatted`.
  - `.venv/Scripts/python.exe -m mypy` → 2 erros, ambos em `tests/unit/test_characterization_support.py` (arquivo não rastreado preexistente do usuário, presente no snapshot inicial; importa `tests.characterization`, que não existe); `-m mypy --exclude 'test_characterization_support\.py$'` → `Success: no issues found in 407 source files`.
  - `.venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output tmp/roadmap-e02/sintetico` → código 0 (`tp 14, fp 3, fn 8`).
  - Suíte inteira sem o arquivo preexistente (`pytest --ignore=tests/unit/test_characterization_support.py`): `2153 passed` e 1 falha não relacionada, `tests/unit/test_windows_app_identity.py::test_window_identity_sets_taskbar_relaunch_icon_and_clears_properties` (cliente Qt, módulo não tocado; diferença só de caixa `C:\zeny` × `C:\Zeny` no ícone, ambiental desta máquina).
  - Radon: maior CC em `curation_infer.py` é 9 (`_falhas_das_saidas`); `select_example_pdfs` 8, `run_examples` 9, `main` de `benchmark_symbols` 7 (os F preexistentes `infer_pdf`/`_run` do runner não mudaram). `scripts/complexity_gate.py src` e `scripts/client_artifact_gate.py --source-only` → aprovados.
  - Execução real fora dos testes, em `tmp/roadmap-e02/` (removido depois): `curation_round init` com 6 PDFs sintéticos e `curation_infer --onda 1 --jobs 3 [--pipeline --native-only]` → todos `sucesso`, checkpoints em `inferido`, `document_id` `example:sub/a.pdf` etc.; segunda chamada em um PDF criou `inferencia-v002` com a v001 de hash idêntico; `rodada.json`, `checkpoint.json` e `execucao.json` sem `Users` nem caminho absoluto.
- Parecer do verificador: APROVADO (verificador independente do orquestrador; snapshot de verificação d7feeed8e75e3fd4d8e4386e414c49b1f93d4551). 5/5 critérios aprovados: teste diferencial runner antigo × novo sem --pdf idêntico salvo carimbos variáveis; --pdf preserva document_id; --jobs 2 nunca excede 2 e falha fica isolada; v002 não toca v001; 129 testes focados passam, Ruff/formatação limpos, mypy limpo exceto o arquivo preexistente do usuário. Correção ao handoff: scripts/complexity_gate.py src NÃO passa — reprova com 5 funções preexistentes em src/ (declarative_symbols._validate_package F65, observar_pacotes E40, legend_symbols._extract_pairs E33, observar_legenda_documental F51, symbol_review.project_symbol E40), sem mudança em src/ nesta etapa; código novo tem CC ≤ 9. Pendências preexistentes para E10: esse gate, tests/unit/test_characterization_support.py e test_windows_app_identity (caixa C:\zeny × C:\Zeny). Baixos: teste de regressão não compara valores com saída de referência anterior; OSError fora do try em inferir_pdf pode derrubar o resumo; symlinks via resolve().
- Notas para a próxima etapa:
  - Layout produzido: `pdfs/ID/inferencia-vNNN/{execucao.json, simbolos/{predictions.json, manifest.json}, simbolos.log[, pipeline.json, pipeline.log]}`. A versão vigente de um PDF é a citada em `checkpoint.marcos.inferido.artefatos[0].caminho` (e em `dados.versao` do evento); versões com `status: falha` podem ter número maior que a vigente, então E05 deve ler a versão do marco `inferido`, não a de maior número.
  - API de `scripts.curation_infer`: `inferir(rodada_dir, pdf_ids, *, jobs=3, metodos=METODOS, pipeline=False, native_only=False, executor=executar_subprocesso, raiz_repositorio=ROOT, codigo=None, agora=...)`, `inferir_pdf(contexto, pdf_id)`, `comandos_inferencia(...)`, `reservar_versao(pdf_dir)`, `executar_subprocesso`, `ResultadoComando`, `Executor`; constantes `METODOS`, `JOBS_PADRAO`, `JOBS_MAXIMO`, `ESQUEMA_EXECUCAO`, `NOME_VERSAO`. No runner: `select_example_pdfs(root, pdfs)` e `run_examples(root, output, *, pdfs=None, ...)`.
  - O `document_id` das predições é `example:` + `caminho_relativo` do `rodada.json`; o comparador regional pode casar referência e predição por ele e pelo SHA-256 do checkpoint.
  - Pendências fora do escopo: `tests/unit/test_characterization_support.py` (preexistente) continua quebrando mypy e a coleta do pytest; `test_windows_app_identity` falha nesta máquina por caixa de caminho. Os dois afetarão E10 se o usuário não os resolver. O pico de memória nativo dos subprocessos não é medido (ver decisão acima).

---

## E03 — Renderização e triagem de tiles — #concluida

**Objetivo:** criar `scripts/curation_render.py`, que gera para cada página uma visão geral e tiles com sobreposição, nas camadas base e com anotações, descarta tiles em branco e publica um índice de cobertura que o leitor visual e o comparador usam.

**Por que agora:** a referência regional (E04) é definida em termos dos tiles; o leitor visual só lê o que este CLI produz.

**Dependências e paralelismo:** E01. Pode correr em paralelo com E02 (em worktree separado); não há arquivo em comum.

**Escopo:**

- `scripts/curation_render.py` (a criar): `--rodada DIR (--onda K | --pdf ID ...) [--lado-tile-px 1536] [--sobreposicao 0.15] [--dpi-detalhe 200] [--limiar-ocupacao ...] [--jobs N]`.
- Por página: `render/pNNN-visao-base.png` e `render/pNNN-visao-anotada.png` com lado maior ≤ `--lado-tile-px`; tiles de detalhe `render/pNNN-CAMADA-tLLCC.png` em grade com sobreposição cobrindo a página inteira; base sem anotações (`annots=False`) e anotada.
- Triagem: tile cuja fração de pixels não brancos fica abaixo do limiar é marcado `descartado_branco` (sem apagar o PNG), reaproveitando a lógica de `src/zeny_project_handler/application/visual_occupancy.py` quando servir.
- `render/indice-tiles.json`: para cada tile, id estável, página, camada, bbox normalizada na página exibida (mesma convenção do avaliador: [0,1], rotação aplicada), DPI, dimensões, SHA-256, ocupação e estado (`a_revisar` ou `descartado_branco`); totais por página. Avança o checkpoint para `renderizado`.
- Testes em `tests/unit/test_curation_render.py` (a criar) com PDFs sintéticos.

**Fora de escopo:** chamar o modelo; OCR; mudar renderização do servidor.

**Passos de implementação:**

1. Testes: união dos bboxes de tiles cobre [0,1]²; página em branco gera só tiles descartados; página com um traço gera ao menos um tile `a_revisar` que contém o traço; hashes determinísticos; página rotacionada mantém a convenção normalizada.
2. Implementar grade, renderização, triagem e índice.

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação (`Explore`): "como o avaliador e o runner normalizam coordenadas para a página exibida, inclusive rotação (`scripts/symbol_benchmark_runner.py`, `src/zeny_project_handler/adapters/pdf/coordinates.py`)?"; "a API de `MapaOcupacaoVisual` serve para calcular fração ocupada de um tile?".
- Partes paralelas: nenhuma.
- Foco do verificador: lacuna de cobertura entre tiles; bbox em convenção diferente da do avaliador; tile com conteúdo descartado; resultado não determinístico.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E03 — "Renderização e triagem de tiles" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Desenho do fluxo-alvo" e o "Protocolo de execução" —, a seção E03 inteira e o "Evidências e handoff" de E01. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E01 está #concluida e que scripts/curation_round.py bate com o handoff; se não, ou se o código divergiu do plano, pare e relate sem implementar.

Objetivo: criar scripts/curation_render.py, que gera visão geral e tiles com sobreposição nas camadas base e anotada, marca tiles em branco como descartados e grava render/indice-tiles.json com bbox normalizada na convenção do avaliador. Não altere a renderização do servidor nem chame modelos.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E03 para #em-andamento no índice e no título;
- investigação: um subagente Explore responde às perguntas de "Estratégia de execução" de E03;
- escreva tests/unit/test_curation_render.py primeiro (cobertura total, página branca, traço único, rotação, determinismo); depois implemente;
- verificação independente com o Prompt do verificador, com foco em lacunas de cobertura, convenção de bbox e descarte indevido.

Critérios de aceite (detalhes na seção E03):
- tiles cobrem a página inteira com a sobreposição pedida, nas duas camadas;
- página branca não gera tile a_revisar; traço isolado gera;
- índice com bbox normalizada, hash e estado; checkpoint em renderizado;
- testes, Ruff, formatação e mypy passam.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com todos os critérios atendidos e parecer APROVADO do verificador; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E03 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador, notas para a próxima etapa — inclusive o formato do índice de tiles) e responda com um resumo curto de mudanças, validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] Para página sintética A4, a união dos bboxes dos tiles de cada camada cobre [0,1]² e tiles vizinhos se sobrepõem na fração pedida (tolerância de 1 px).
- [ ] Página totalmente branca gera 0 tiles `a_revisar`; página com um único segmento gera ≥ 1 tile `a_revisar` cujo bbox contém o segmento.
- [ ] Em página com rotação 90°, o bbox do tile que contém um marcador sintético coincide com a posição do marcador na página exibida.
- [ ] Duas execuções produzem SHA-256 idênticos.
- [ ] Testes, Ruff, formatação e mypy passam.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_render.py tests/unit/test_curation_round.py -q` → todos passam.
- `.venv/Scripts/python.exe -m ruff check .`, `-m ruff format --check .`, `-m mypy` → sem erros.
- Inspeção manual: abrir com a ferramenta Read dois tiles gerados de um PDF sintético e confirmar legibilidade do texto da fixture.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Texto pequeno ilegível em 1536 px (H3) → DPI de detalhe configurável; a rodada de E11 ajusta.

**Evidências e handoff:**

- Snapshot inicial: `51b64c6c21336df009200b694c19f5d8ac3ebe64` (recebido do orquestrador). Snapshot ao fim da implementação (antes deste handoff): `afd166a4010fabc548f78601eafa5ee7eabd9e79`; `git diff --stat` entre os dois mostra só os três arquivos abaixo.
- Arquivos alterados: `scripts/curation_render.py` (novo), `tests/unit/test_curation_render.py` (novo, 60 casos), este roadmap (tags e handoff de E03). `scripts/curation_round.py`, `scripts/curation_infer.py`, `tests/fixtures/e10_characterization/` e `tests/unit/test_characterization_support.py` intocados; nenhuma mudança em `src/` (renderização do servidor inalterada).
- Decisões:
  - Preparação: E01 `#concluida`; `scripts/curation_round.py` confere com o handoff de E01 (`carregar_checkpoint`, `validar_transicao`, `transicionar`, `selecionar_pdfs`, `diretorio_pdf`, `caminho_pdf_fonte`, `escrever_json_atomico`, `json_canonico`; `REQUISITOS["renderizado"] = ()` e recusa de `renderizado` depois de `referencia_congelada`). Investigação feita diretamente (adendo do orquestrador): o avaliador (`symbols-e02-v1`) exige bbox `[x0, y0, x1, y1]` finita em [0,1] na página exibida; o servidor normaliza com `page.rotation_matrix` e divide por `page.rect` (já girado), origem no canto superior esquerdo (`legacy_symbols.py:95-104`). `get_pixmap` do PyMuPDF renderiza a página exibida (rotação aplicada), então `bbox = bbox_px / detalhe_px` da renderização de detalhe da página inteira cai na mesma convenção (conferido: marcador em (100,50) numa página girada 90° → (782,100) pt exibidos, igual a `Rect * rotation_matrix`). `MapaOcupacaoVisual` responde só "região totalmente branca?" em células de 4 px, não fração; reaproveitei o critério dele (canal mais escuro < 248, constante `LIMIAR_BRANCO`, com teste que a amarra a `visual_occupancy._LIMIAR_BRANCO`) e contei pixels pelo histograma do Pillow.
  - Layout em `pdfs/ID/render/`: `pNNN-visao-base.png`, `pNNN-visao-anotada.png`, `pNNN-base-tLLCC.png`, `pNNN-anotada-tLLCC.png` (LL = linha, CC = coluna, 2 dígitos; mais de 99 por eixo é recusado com mensagem) e `indice-tiles.json`. A camada no índice segue o avaliador (`base`/`annotation`, como o esquema de E04); nos nomes de arquivo, `base`/`anotada`. Base com `annots=False`, anotada com `annots=True` (widgets incluídos nas anotações).
  - Grade de passo fixo: `sobreposicao_px = round(lado * sobreposicao)`, `passo = lado - sobreposicao_px`; o último tile de cada eixo é truncado na borda (não deslocado), então todo par vizinho se sobrepõe exatamente `sobreposicao_px` e o último sempre acrescenta pixels novos. Página menor que o tile num eixo → um tile com a extensão inteira. Visão geral: zoom `min((lado - 1) / maior_lado_pt, dpi_detalhe / 72)` (nunca maior que o detalhe; lado maior ≤ `--lado-tile-px`).
  - Detalhe renderizado uma vez por camada (página inteira a `--dpi-detalhe`) e recortado com Pillow; PNG via Pillow `compress_level=6`, sem metadados. Memória: A3 a 200 DPI ≈ 23 MB por camada; páginas muito grandes a DPI alto podem pesar (não há limite explícito além de 99 tiles por eixo).
  - Triagem: `estado = descartado_branco` se `ocupacao <= --limiar-ocupacao`, senão `a_revisar`; padrão `0.000001` (≈ 2 pixels não brancos em 1536²), conservador — um traço de 0,5 pt a 72 DPI numa página inteira continua `a_revisar` (teste). `--limiar-ocupacao 0` descarta só tiles absolutamente brancos. Os PNG descartados não são apagados.
  - Opções validadas (erro → `RodadaError`, código 1, sem tocar checkpoint): `--lado-tile-px` 64–8192, `--sobreposicao` 0–0,5, `--dpi-detalhe` 36–1200, `--limiar-ocupacao` [0, 1), `--jobs` 1–5 (padrão 3).
  - Por PDF: valida a transição para `renderizado` antes de tudo (recusa → `recusado`, nada escrito); lê o PDF uma vez, confere o SHA-256 com o checkpoint e abre a partir dos mesmos bytes; renderiza num diretório temporário irmão (`.render-*`), grava o índice, revalida a transição e só então troca `render/` (o anterior é restaurado se a troca falhar) e chama `transicionar(..., "renderizado", artefatos=[render/indice-tiles.json, render/], dados={indice, parametros, totais})`. Falhas e exceções ficam isoladas no PDF; temporários são removidos. Rerenderizar antes de congelar a referência substitui `render/` (bytes idênticos com os mesmos parâmetros) e acrescenta outro evento `renderizado`. Resta uma janela de corrida entre a revalidação e o `transicionar` (referência congelada exatamente nesse intervalo): o `transicionar` recusa e o PDF sai como `falha`, mas `render/` já foi trocado.
  - Paralelismo: `ProcessPoolExecutor(max_workers=min(jobs, n))` (PyMuPDF não é seguro entre threads); `jobs=1` ou um só PDF roda no próprio processo. Falha do processo (ex.: pool quebrado) vira `falha` daquele PDF.
  - Determinismo: o índice não tem horários nem caminhos absolutos (`arquivo` relativo à rodada); durações só na saída da CLI e no evento do checkpoint.
- Validações executadas:
  - Testes escritos antes do módulo: `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_render.py -q` falhou na coleta com `ModuleNotFoundError: No module named 'scripts.curation_render'`; depois da implementação → passam.
  - `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_render.py tests/unit/test_curation_round.py -q` → `110 passed` (60 novos + 50 de E01).
  - Testes ligados aos critérios: `test_tiles_cobrem_pagina_a4_com_sobreposicao_pedida_nas_duas_camadas[0.15/0.3]` (A4 com parâmetros padrão: grade completa, primeiro e último intervalo nas bordas, sobreposição de vizinhos = `round(1536 * s)` ± 1 px, união das bbox normalizadas cobre [0,1] nos dois eixos, bbox = bbox_px/detalhe_px, PNG com as dimensões declaradas, nas duas camadas) e `test_grade_eixo_cobre_tudo_com_sobreposicao_exata[...]` (28 combinações); `test_pagina_branca_nao_gera_tile_a_revisar_mas_mantem_os_png`; `test_segmento_unico_gera_tile_a_revisar_que_o_contem` (o tile contém o segmento e exatamente os tiles que o intersectam ficam `a_revisar`); `test_traco_de_um_pixel_nao_e_descartado_pelo_limiar_padrao`; `test_camada_anotada_inclui_anotacoes_e_base_nao`; `test_rotacao_90_mantem_bbox_na_pagina_exibida` (único tile `a_revisar` por camada contém o marcador e a posição medida nos pixels do PNG, mapeada pela bbox, coincide com `Rect * rotation_matrix / page.rect` com tolerância de 1,5 px); `test_duas_execucoes_produzem_hashes_identicos` (duas rodadas → `indice-tiles.json` byte a byte igual e mesmo hash de diretório; rerender na mesma rodada também); `test_indice_tem_ids_estaveis_hash_estado_e_totais`; `test_checkpoint_avanca_para_renderizado_com_hash_do_indice`; `test_renderizar_depois_de_congelar_referencia_e_recusado_sem_tocar_render`; `test_pdf_alterado_desde_init_falha_sem_renderizar`; `test_pdf_ilegivel_falha_isolado_e_os_demais_renderizam`; `test_jobs_em_processos_paralelos_renderizam_todos`; validação de parâmetros e jobs; `carregar_indice`; CLI.
  - Mutações manuais (todas detectadas, arquivo restaurado depois): bbox x dividido pela altura; passo da grade +1 px; base renderizada com anotações; limiar de branco 128 em vez de 248; matriz de renderização desfazendo a rotação.
  - `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`; `-m ruff format --check .` → `454 files already formatted`.
  - `.venv/Scripts/python.exe -m mypy` → 2 erros, ambos em `tests/unit/test_characterization_support.py` (arquivo não rastreado preexistente do usuário, presente no snapshot inicial: importa `tests.characterization`, inexistente, e um `no-any-return`; não alterado); `-m mypy --exclude 'test_characterization_support\.py$'` → `Success: no issues found in 408 source files`. Esse arquivo também quebra a coleta do pytest da suíte inteira; os comandos focados acima não o coletam.
  - Radon: maior CC do módulo novo é 10 (`renderizar`); `scripts/client_artifact_gate.py --source-only` → APROVADO. Cobertura de linhas do módulo pelos testes (processo principal): 88%.
  - Inspeção manual: `curation_round init` + `python -m scripts.curation_render --rodada tmp/roadmap-e03/rodada --onda 1 --jobs 2` (parâmetros padrão) sobre `create_network_benchmark_pdf` e um A3 sintético girado 90° com texto de 6 a 9 pt → código 0, 2 `sucesso`, checkpoints em `renderizado`. Abri com a ferramenta Read `pdfs/002-…/render/p001-base-t0000.png` ("P1", "V1-2", "P2", "P-9M-150DAN-CIRCULAR", "ABC-4 CA", "35m" legíveis) e `pdfs/001-…/render/p001-anotada-t0001.png` (título girado "PROJETO SINTETICO NS 0001 - POSTE P-9M-150DAN" e "ABC-4 CA 35m" em 6 pt legíveis, na orientação da página exibida). Índices e checkpoints sem `Users`/`C:`. `tmp/roadmap-e03/` removido depois.
- Parecer do verificador: APROVADO (verificador independente do orquestrador; snapshot de verificação 70c77c34ff6c587fcbf7bc13c1b9784e6858f852). 5/5 critérios aprovados: cobertura 2D sem lacunas (A4, A3 girada 90/180/270, tamanho ímpar) nas duas camadas; página branca sem a_revisar e segmento único detectado; rotação coerente com rotation_matrix; hashes idênticos entre execuções e entre jobs=1/3; 110 testes focados, Ruff/formatação limpos, mypy limpo exceto o arquivo preexistente do usuário; mutações detectadas. Baixos: limiar 1e-6 descarta tile com até ~2 px escuros; corrida estreita entre revalidação e transicionar; bbox normalizada por detalhe_px inteiro (<1 px); última tira pode sair estreita; teste de cobertura de A4 é por projeção por eixo.
- Notas para a próxima etapa:
  - API de `scripts.curation_render`: `renderizar(rodada_dir, pdf_ids, *, parametros=None, jobs=3)` → `{jobs, parametros, pdfs: [{pdf_id, status sucesso|falha|recusado, falhas, tiles, a_revisar, descartado_branco, duracao_s}], totais: {sucesso, falha, recusado}}`; `renderizar_pdf(rodada_dir, pdf_id, parametros)`; `gerar_indice(conteudo_pdf, destino, parametros, *, pdf_id, sha256_pdf, caminho_relativo, prefixo)`; `caminho_indice(rodada_dir, pdf_id)` e `carregar_indice(rodada_dir, pdf_id)` (confere esquema e `pdf_id`; E04/E05/E06 devem usá-los); `grade_eixo`, `medir_ocupacao`, `ParametrosRender(lado_tile_px=1536, sobreposicao=0.15, dpi_detalhe=200, limiar_ocupacao=1e-6)` com `.validar()` e `.registro()`; constantes `ESQUEMA_INDICE`, `DIRETORIO_RENDER`, `ARQUIVO_INDICE`, `ESTADO_REVISAR`, `ESTADO_DESCARTADO`, `CAMADAS`, `LIMIAR_BRANCO`, `JOBS_MAXIMO`.
  - Formato de `pdfs/ID/render/indice-tiles.json` (`curadoria-indice-tiles-v1`, JSON canônico): `schema_version`, `pdf_id`, `sha256_pdf`, `caminho_relativo`, `convencao_bbox` {`protocolo: symbols-e02-v1`, `espaco`, `formato`, `origem_pixels`}, `parametros` {`lado_tile_px`, `sobreposicao`, `dpi_detalhe`, `limiar_ocupacao`, `limiar_branco`}, `renderizador` {`pymupdf`, `mupdf`, `pillow`}, `paginas` [{`pagina`, `largura_pt`, `altura_pt` (página exibida), `rotacao`, `anotacoes`, `widgets`, `detalhe_px` [W, H], `grade` {`colunas`, `linhas`, `sobreposicao_px`}, `camada_anotada_igual_base`, `totais` {`base`|`annotation`: {`tiles`, `a_revisar`, `descartado_branco`}}}], `visoes` [{`id` (`pNNN-visao-base|anotada`), `arquivo`, `pagina`, `camada`, `bbox` [0,0,1,1], `dpi`, `largura_px`, `altura_px`, `sha256`, `bytes`}], `tiles` [{`id` (`pNNN-base|anotada-tLLCC`, igual ao nome do PNG sem extensão), `arquivo` (relativo à rodada, `pdfs/ID/render/ID.png`), `pagina`, `camada` (`base`|`annotation`), `linha`, `coluna`, `bbox` (normalizada na página exibida), `bbox_px` (na renderização de detalhe), `dpi`, `largura_px`, `altura_px`, `sha256`, `bytes`, `ocupacao`, `pixels_ocupados`, `estado` (`a_revisar`|`descartado_branco`)}] na ordem página → camada (base, depois annotation) → linha → coluna, e `totais` {`paginas`, `tiles`, `a_revisar`, `descartado_branco`} somando as duas camadas.
  - O marco `renderizado` do checkpoint registra dois artefatos: `pdfs/ID/render/indice-tiles.json` (arquivo, SHA-256 do índice) e `pdfs/ID/render` (diretório); `dados` traz `indice`, `parametros` e `totais`. E04 pode conferir o índice vigente pelo SHA-256 do marco.
  - `camada_anotada_igual_base = true` (página sem anotações visíveis) indica que os tiles `annotation` repetem os `base` byte a byte; a skill (E08) pode instruir o leitor a revisar só a camada base nesse caso, decisão que fica para E04/E08.
  - Pendência fora do escopo: `tests/unit/test_characterization_support.py` (preexistente) continua quebrando o mypy do repositório e a coleta do pytest da suíte inteira; afetará E10 se o usuário não resolver.

---

## E04 — Referência visual regional — #concluida

**Objetivo:** definir o formato da referência que o leitor visual produz e criar `scripts/curation_reference.py` para validar, congelar e versionar essa referência.

**Por que agora:** o comparador, a auditoria e os subagentes dependem desse formato; a cegueira do leitor é garantida no congelamento.

**Dependências e paralelismo:** E03. Não paraleliza.

**Escopo:**

- `docs/schemas/referencia-visual-curadoria.schema.json` (a criar), Draft 2020-12, com: `schema_version`, PDF (`pdf_id`, `sha256`, caminho relativo), revisor (`origem: revisao_ia`, modelo informado pela sessão ou `indisponivel`), `escopo` (`regional` ou `completo`), `tiles_revisados` (ids do índice), `regioes_ilegiveis` (bbox + motivo), `observacoes` com id local estável, página, camada `base|annotation`, bbox normalizada, `familia` e `class_id` compatíveis com o inventário/avaliador, `id_inventario` ou `alternativas` com motivo, `papel` (`operacional|informativo|desconhecido|negativo`), texto original legível, interpretação, quantidades/unidades, relações por id, estado (`sustentado_por_evidencia|provisorio|ilegivel`), tile de evidência e fonte do significado.
- `scripts/curation_reference.py` (a criar):
  - `validar --rodada DIR --pdf ID --arquivo JSON`: esquema + regras semânticas (bbox dentro de um tile revisado da mesma página/camada; família/ID existentes em `docs/data/inventario-simbologia-v1.json`; ids únicos; relações apontam para ids existentes; todo tile `a_revisar` está em `tiles_revisados` ou coberto por `regioes_ilegiveis` quando `escopo = completo`).
  - `congelar`: copia para `referencia/referencia-v001.json`, grava SHA-256 e horário no checkpoint (fase `referencia_congelada`) e registra se já havia inferência no diretório do PDF (transparência; não é erro).
  - `revisar --motivo TEXTO --exposicao`: cria `referencia-vNNN` nova preservando as anteriores e marca a exposição a predições.
- Testes em `tests/unit/test_curation_reference.py` (a criar).

**Fora de escopo:** produzir referências (é tarefa dos subagentes); mudar o inventário; mudar o avaliador.

**Passos de implementação:**

1. Investigar o mapeamento entre IDs do inventário, `family` e `class_id` usados nas predições.
2. Escrever esquema e testes de validação (válidos e inválidos), congelamento e versionamento.
3. Implementar.

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação (`Explore`): "como `docs/data/inventario-simbologia-v1.json` organiza famílias e IDs e como as predições do runner preenchem `family` e `class_id` (`scripts/symbol_benchmark_runner.py`, funções `_prediction`, `_package_prediction`)?"; "quais regras de ambiguidade/alternativas o fluxo atual exige (`docs/fluxo-curadoria-incremental-simbologia.md`, seção C02)?".
- Partes paralelas: nenhuma.
- Foco do verificador: referência aceita com família inexistente; observação fora dos tiles revisados; congelamento que sobrescreve versão; ausência do registro de exposição; ambiguidade convertida em ID exato.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E04 — "Referência visual regional" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Desenho do fluxo-alvo", "Restrições e invariantes" e o "Protocolo de execução" —, a seção E04 inteira e o "Evidências e handoff" de E01 e E03. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E03 está #concluida e que o índice de tiles bate com o handoff; se não, ou se o código divergiu do plano, pare e relate sem implementar.

Objetivo: criar docs/schemas/referencia-visual-curadoria.schema.json e scripts/curation_reference.py (validar, congelar, revisar), com regras semânticas ligadas ao índice de tiles e ao inventário, congelamento com hash no checkpoint e versões preservadas. Não altere o inventário nem scripts/symbol_benchmark_evaluator.py.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E04 para #em-andamento no índice e no título;
- investigação: um subagente Explore responde às perguntas de "Estratégia de execução" de E04;
- escreva tests/unit/test_curation_reference.py primeiro (referências válidas e inválidas, congelamento, nova versão com exposição); depois implemente;
- verificação independente com o Prompt do verificador, com foco em família inexistente, observação fora dos tiles revisados, sobrescrita de versão e exposição não registrada.

Critérios de aceite (detalhes na seção E04):
- validar aceita a referência sintética válida e recusa cada caso inválido listado, com mensagem que cita o id;
- congelar grava hash e fase sem sobrescrever; revisar cria nova versão com motivo e exposição;
- testes, Ruff, formatação e mypy passam.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com todos os critérios atendidos e parecer APROVADO do verificador; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E04 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador, notas para a próxima etapa — inclusive o mapeamento família/class_id adotado) e responda com um resumo curto de mudanças, validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] Uma referência sintética válida passa em `validar`; são recusadas, cada uma com mensagem que cita o id: família fora do inventário, bbox fora de qualquer tile revisado, id duplicado, relação para id inexistente, `escopo = completo` com tile `a_revisar` não revisado.
- [ ] Observação com `alternativas` e sem `id_inventario` é aceita; com ambos preenchidos de forma contraditória é recusada.
- [ ] `congelar` grava `referencia-v001.json`, SHA-256 e fase `referencia_congelada`; segunda chamada falha sem alterar nada.
- [ ] `revisar` cria `referencia-v002.json` com motivo e `exposicao_predicoes: true`, preservando v001.
- [ ] Testes, Ruff, formatação e mypy passam.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_reference.py tests/unit/test_curation_round.py tests/unit/test_symbol_inventory.py -q` → todos passam.
- `.venv/Scripts/python.exe -m ruff check .`, `-m ruff format --check .`, `-m mypy` → sem erros.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Mapeamento inventário ↔ `class_id` ambíguo → registrar no handoff a tabela adotada e testar um caso por família usada nas fixtures.

**Evidências e handoff:**

- Snapshot inicial: `d1197ca0446540f6ca5d1b4162f6a29de99b91a0` (recebido do orquestrador). Snapshot ao fim da implementação (antes deste handoff): `02106d1eefe2da117d9edfd3ab8b09d4f22c00e8`; `git diff --stat` entre os dois mostra só os quatro arquivos abaixo.
- Arquivos alterados: `docs/schemas/referencia-visual-curadoria.schema.json` (novo), `scripts/curation_reference.py` (novo), `tests/unit/test_curation_reference.py` (novo, 70 casos), este roadmap (tag e handoff de E04). Inventário, `scripts/symbol_benchmark_evaluator.py`, `scripts/curation_round.py`, `scripts/curation_render.py`, `tests/fixtures/e10_characterization/` e `tests/unit/test_characterization_support.py` intocados.
- Decisões:
  - Preparação: E03 `#concluida`; o índice real gerado por `curation_render` (sondagem em diretório temporário, removido depois) confere com o handoff de E03 (`curadoria-indice-tiles-v1`, ids `pNNN-base|anotada-tLLCC`, `camada` `base|annotation`, `bbox` normalizada, `estado`, `paginas[].camada_anotada_igual_base`, marco `renderizado` com o SHA-256 de `render/indice-tiles.json`). Investigação feita diretamente (adendo do orquestrador): ver o mapeamento abaixo; as regras de ambiguidade vêm de "Contrato e limites" e C02 de `docs/fluxo-curadoria-incremental-simbologia.md` (uma observação com alternativas explícitas, ID exato só quando a evidência distingue, desconhecido continua desconhecido, legenda/§33 informativos, texto original separado da interpretação, estado com motivo, fonte do significado com localizador).
  - **Mapeamento família/class_id adotado** (conferido no código do runner e dos detectores): `familia` = `families[].id` do inventário (`family-f02-NN`), o mesmo valor que as predições gravam em `family` (`CLASS_FAMILY` do método legado e `atributos.familia_inventario` dos demais); `class_id` = `variants[].class_code` de alguma variante dessa família, o mesmo que `class_id` das predições (`primary.classe`); `id_inventario` e `alternativas.ids_inventario` = `variants[].id` (o mesmo de `provenance.variant_id` do método de pacotes). Classes em mais de uma família são aceitas em cada uma delas (`TRANSFORMADOR`: f02-18/24/25; `ESTAI`: f02-14/15; `CONJUNTO_EO`: f02-20/23/25/32; `CONVENCAO_EO`: f02-01/02/04/13). Elemento sem família no inventário usa o par do método de legenda local do runner, `local-unknown`/`UNKNOWN_LOCAL`, sem `id_inventario` nem `alternativas` (fica fora das métricas por família, como no avaliador). Teste parametrizado confirma que todos os pares de `CLASS_FAMILY` do runner existem no inventário; fixtures cobrem f02-18 (`TRANSFORMADOR`, `REGULADOR_TENSAO`), f02-14/f02-15 (`ESTAI`) e `local-unknown`.
  - Esquema (`curadoria-referencia-visual-v1`, Draft 2020-12): `schema_version`, `pdf` {`pdf_id`, `sha256`, `caminho_relativo`}, `revisor` {`origem: revisao_ia`, `modelo`}, `escopo` `regional|completo`, `tiles_revisados` (ids do índice), `regioes_ilegiveis` [{`id`, `pagina`, `camada`, `bbox`, `motivo`}], `observacoes` [{`id`, `pagina`, `camada`, `bbox`, `trace`?, `familia`, `class_id`, `id_inventario`?, `alternativas`? {`ids_inventario` (≥ 2), `motivo`}, `papel` `operacional|informativo|desconhecido|negativo`, `ponto`?, `descricao_visual`?, `texto_original`, `interpretacao`, `quantidades`? [{`valor`, `unidade`, `texto_original`?}], `relacoes`? [{`tipo`, `alvo`}], `estado` `sustentado_por_evidencia|provisorio|ilegivel`, `motivo_estado`?, `tile_evidencia`, `fonte_significado` {`tipo` `legenda_local|nota_documento|inventario|norma|contexto_visual|indisponivel`, `localizador`}}], `notas`? e `congelamento`? (escrito só pelo CLI). `additionalProperties: false` em todos os objetos. Não há `jsonschema` no venv: o módulo traz um validador do subconjunto usado (`PALAVRAS_ESQUEMA`; palavra fora dele é recusada com `ValueError`, testado), com `$ref` aplicado junto das palavras irmãs como no 2020-12 e `number` recusando NaN/infinito; a leitura do JSON também recusa `NaN`/`Infinity`.
  - Regras semânticas (`validar_referencia`), cada mensagem citando o id da observação/região ou do tile: identidade do PDF igual ao índice e ao checkpoint; `tiles_revisados` existentes no índice, sem repetição (tiles `descartado_branco` podem ser revisados); ids únicos num só espaço (observações + regiões); página existente; bbox não invertida nem ponto (como o avaliador); **bbox contida na união dos tiles revisados da mesma página e camada** (permite objeto longo que atravessa tiles; folga `TOLERANCIA_BBOX = 1e-6`); `tile_evidencia` revisado, da mesma página/camada e tocando a bbox; família existente, `class_id` da família, `id_inventario` existente e coerente com família/classe ("contradiz"); **`id_inventario` e `alternativas` mutuamente exclusivos** (ambiguidade não vira ID exato); alternativas existentes, sem repetição e com ao menos uma de mesma família/classe da observação; família do inventário exige `id_inventario` ou `alternativas`, salvo `papel = negativo` ou `estado = ilegivel`; relações para observação existente e não para si mesma; `motivo_estado` obrigatório fora de `sustentado_por_evidencia`; `legenda_local`/`nota_documento`/`norma` exigem `localizador`; com `escopo = completo`, todo tile `a_revisar` revisado, ou coberto pela união das regiões ilegíveis da mesma página/camada, ou — tile `annotation` de página com `camada_anotada_igual_base = true` — com o tile `base` gêmeo (mesma linha/coluna) revisado. Erros de esquema interrompem as regras semânticas. `tiles_permitidos` (opcional) restringe os tiles declaráveis, para E06.
  - `validar_arquivo` exige o marco `renderizado` e confere o SHA-256 atual de `render/indice-tiles.json` com o registrado no marco (índice alterado → recusa).
  - Versões: arquivo `pdfs/ID/referencia/referencia-vNNN.json` = JSON canônico da entrada + bloco `congelamento` {`versao`, `origem` `leitura|revisao`, `exposicao_predicoes`, `motivo`, `versao_anterior` ({`arquivo`, `sha256`} ou `null`), `inferencias_presentes`, `indice_tiles_sha256`, `sha256_entrada`}; o arquivo congelado passa de novo em `validar`. Sem horário no arquivo (o horário fica no checkpoint). Entrada que já traz `congelamento` é recusada (o leitor não declara a própria exposição).
  - `congelar`: sob a trava `pdfs/ID/referencia.lock` (mesma `_trava` de `curation_round`, arquivo distinto da trava do checkpoint), valida a transição para `referencia_congelada` (fase terminal → recusa), recusa se o checkpoint já tem `referencia` ("use revisar") ou se já existe qualquer `referencia-vNNN.json` órfã, valida a entrada e só então cria a pasta e grava a v001 de forma exclusiva (temporário + `os.link`, que falha se o destino existir; `open("xb")` se o sistema de arquivos não tiver hard link) e chama `transicionar(..., "referencia_congelada", artefatos=[v001], origem_referencia="leitura", dados=...)`; se a transição falhar, o arquivo recém-criado é removido. `exposicao_predicoes: false` na v001; `inferencias_presentes` lista as pastas `inferencia-vNNN` já existentes (transparência, não erro).
  - `revisar`: exige `motivo` não vazio e exposição explícita — na CLI `--exposicao sim|nao` é **obrigatório** (em vez de um sinalizador que, ausente, registraria `false` em silêncio); exige referência congelada, confere o SHA-256 da versão vigente (adulterada → recusa), grava a **próxima versão livre** depois da maior existente (órfãs nunca são reutilizadas nem sobrescritas), `versao_anterior` aponta para a vigente do checkpoint e `origem_referencia="revisao"`. Pela máquina de fases de E01, a revisão invalida `comparado` (testado) e não invalida `auditado`.
  - Dados do evento no checkpoint: `versao`, `versao_anterior`, `exposicao_predicoes`, `motivo`, `inferencias_presentes`, `indice_tiles_sha256`, `escopo`, `observacoes`, `tiles_revisados`; `checkpoint.referencia` segue o formato de E01 (`arquivo`, `horario`, `origem`, `sha256`, `versao`).
- Validações executadas:
  - Testes escritos antes do módulo: `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_reference.py -q` falhou na coleta com `ModuleNotFoundError: No module named 'scripts.curation_reference'`; depois da implementação → `70 passed`.
  - `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_reference.py tests/unit/test_curation_round.py tests/unit/test_symbol_inventory.py -q` → `158 passed`.
  - Testes ligados aos critérios: `test_referencia_sintetica_valida_passa`; recusas com id na mensagem — `test_familia_fora_do_inventario_e_recusada` (O1 + `family-f02-99`), `test_bbox_fora_de_qualquer_tile_revisado_e_recusada`, `test_bbox_em_tile_revisado_de_outra_camada_e_recusada`, `test_id_duplicado_e_recusado`, `test_relacao_para_id_inexistente_e_recusada` (O2 + O9), `test_escopo_completo_com_tile_a_revisar_nao_revisado_e_recusado` (id do tile; o mesmo caso passa em escopo regional); `test_alternativas_sem_id_inventario_sao_aceitas`, `test_alternativas_e_id_inventario_juntos_sao_recusados`, `test_id_inventario_de_outra_classe_e_recusado`; `test_congelar_grava_v001_hash_e_fase`, `test_segundo_congelar_falha_sem_alterar_nada` (bytes da v001 e do checkpoint iguais); `test_revisar_cria_v002_com_motivo_e_exposicao` (v001 byte a byte preservada), `test_revisar_duas_vezes_preserva_todas_as_versoes`, `test_revisar_pula_numero_ocupado_sem_sobrescrever`; além de cobertura por região ilegível, gêmeo base, objeto atravessando tiles, tiles permitidos, órfã, criação exclusiva, fase terminal, índice adulterado, versão vigente adulterada, NaN e CLI (`--exposicao` obrigatório).
  - Mutações manuais (todas detectadas, arquivo restaurado depois): checagem de família removida; contenção da bbox removida; exclusividade id/alternativas removida; relação inexistente aceita; cobertura do escopo completo removida; `os.link` trocado por `os.replace` (sobrescrita); checagem de órfã removida; exposição forçada a `false`; tile repetido aceito; tile de evidência não revisado aceito; gêmeo base ignorado; segundo `congelar` aceito; conferência de hash da vigente removida.
  - `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`; `-m ruff format --check .` → `456 files already formatted`.
  - `.venv/Scripts/python.exe -m mypy` → 2 erros, ambos em `tests/unit/test_characterization_support.py` (arquivo não rastreado preexistente do usuário, presente no snapshot inicial: importa `tests.characterization`, inexistente, e um `no-any-return`; não alterado); `-m mypy --exclude 'test_characterization_support\.py$'` → `Success: no issues found in 409 source files`. Esse arquivo também quebra a coleta do pytest da suíte inteira; os comandos focados acima não o coletam.
  - Radon: maior CC do módulo novo é 16 (`_erros_escalares`); cobertura de linhas do módulo pelos testes: 93%. `scripts/client_artifact_gate.py --source-only` → APROVADO.
  - Execução real fora dos testes, em diretório temporário do scratchpad (removido depois): `curation_round init` + `curation_render` + `python -m scripts.curation_reference validar` (referência com família inexistente e relação quebrada → código 1, uma linha por erro citando O1/O2/O9; válida → código 0), `congelar` (código 0, v001), segundo `congelar` (código 1, "use revisar"), `revisar --motivo teste --exposicao sim` (código 0, v002, origem `revisao`, `exposicao_predicoes: true`); `curation_round status` mostra `referencia_congelada`/`revisao`; nenhum `Users`/`C:` nos JSON de `referencia/` nem no checkpoint.
- Parecer do verificador: APROVADO (verificador independente do orquestrador; snapshot de verificação f6dd4a21c4d30085e71509173e39bfdc3e589269). 5/5 critérios aprovados: referência válida passa e cada inválida é recusada citando o id; alternativas sem id_inventario aceitas e contradição recusada; congelar grava v001/hash/fase e o segundo congelar falha sem alterar bytes; revisar cria v002 com motivo e exposição preservando v001; 158 testes focados, Ruff/formatação limpos, mypy limpo exceto o arquivo preexistente do usuário; 7 mutações injetadas detectadas e sondas de borda corretas. Baixos: exposição é declarativa (revisar --exposicao nao após comparado é aceito; E08 deve instruir declaração correta ou registrar marcos); validador próprio de subconjunto do Draft 2020-12 (sem jsonschema no venv); basta uma alternativa pertencer à família/classe; limpeza em _gravar_versao em exceção tardia de transicionar.
- Notas para a próxima etapa:
  - API de `scripts.curation_reference`: `validar_arquivo(rodada_dir, pdf_id, arquivo, *, inventario=None, tiles_permitidos=None)` → `ResultadoValidacao(referencia, erros, indice_sha256, entrada_sha256)` com `.valida`; `validar_referencia(referencia, *, indice, inventario, esquema=None, checkpoint=None, tiles_permitidos=None)` → `list[str]`; `congelar(rodada_dir, pdf_id, arquivo, *, inventario=None, agora=None)` e `revisar(rodada_dir, pdf_id, arquivo, *, motivo, exposicao_predicoes, inventario=None, agora=None)` → checkpoint novo; `carregar_referencia_vigente(rodada_dir, pdf_id)` → `(referencia, caminho)` conferida pelo SHA-256 do checkpoint (E05/E06 devem usá-la em vez de escolher a maior versão); `versoes_existentes(pasta_referencia)`, `inferencias_presentes(pasta_pdf)`, `contida_na_uniao(caixa, retangulos)` (útil para E05 restringir predições às regiões revisadas e fora das ilegíveis), `carregar_inventario()` → `Inventario(familias, variantes, classes_por_familia)`, `carregar_esquema()`, `validar_esquema(valor, esquema)`; constantes `ESQUEMA_REFERENCIA`, `CAMINHO_ESQUEMA`, `CAMINHO_INVENTARIO`, `FAMILIA_LOCAL`, `CLASSE_LOCAL`, `DIRETORIO_REFERENCIA`, `TOLERANCIA_BBOX`, `PALAVRAS_ESQUEMA`, `EXPOSICAO`; exceção `ReferenciaInvalidaError(RodadaError)` com `.erros`.
  - CLI: `validar` imprime `erro: ...` por linha no stderr (código 1) ou um resumo (código 0); `congelar`/`revisar` imprimem JSON canônico {`pdf_id`, `versao`, `sha256`, `origem`, `exposicao_predicoes`, `inferencias_presentes`}. `revisar` exige `--motivo` e `--exposicao sim|nao`.
  - E05: casar referência e predição por `familia`↔`family` e `class_id`↔`class_id` (nível classe/grupo) e `id_inventario`↔`provenance.variant_id` (nível ID exato; só o método de pacotes informa variante); observação com `alternativas` nunca conta como TP exato; `local-unknown` fica fora das métricas por família; `papel` mapeia para `context` do avaliador (`operacional`→`operational`, `informativo`→`informative`, `negativo`→`negative`; `desconhecido` não tem equivalente e deve ser contado à parte); `estado = provisorio` contado à parte.
  - E06: validar a referência do auditor com `validar_arquivo(..., tiles_permitidos=amostra)` (tiles descartados podem estar na amostra). A revisão da referência não invalida `auditado` (regra de E01, já apontada pelo verificador de E01).
  - E08: o leitor grava a entrada fora de `referencia/` (ex.: `pdfs/ID/leitura/referencia.json`) sem bloco `congelamento`; nomes `referencia-vNNN.json` dentro de `referencia/` são reservados ao CLI. Em página com `camada_anotada_igual_base = true`, revisar só a camada base basta para o escopo completo.
  - Pendência fora do escopo: `tests/unit/test_characterization_support.py` (preexistente) continua quebrando o mypy do repositório e a coleta do pytest da suíte inteira; afetará E10 se o usuário não resolver.

---

## E05 — Comparador regional — #concluida

**Objetivo:** criar `scripts/curation_compare.py`, que mede de forma determinística a inferência congelada contra a referência congelada, apenas nas regiões revisadas, e lista cada divergência com o que é preciso para investigá-la.

**Por que agora:** é a peça que tira do modelo o trabalho de contar e casar ocorrências; o backlog e a rodada dependem dela.

**Dependências e paralelismo:** E02, E04. Pode correr em paralelo com E06 (em worktree separado); não há arquivo em comum.

**Escopo:**

- `scripts/curation_compare.py` (a criar): `--rodada DIR (--onda K | --pdf ID ...) [--inferencia vNNN] [--referencia vNNN]`.
- Recusa se a referência não estiver congelada ou se o SHA-256 do PDF diferir entre referência e inferência.
- Restringe predições às regiões revisadas (centro dentro de tile revisado da mesma camada e fora de `regioes_ilegiveis`); predições fora ficam em `fora_do_escopo` com contagem.
- Casamento 1:1 por página/camada/classe reutilizando `geometry_match` de `scripts/symbol_benchmark_evaluator.py`, em dois níveis: classe/grupo visual e ID exato.
- Saída `comparacao-vNNN.json`: TP_IA/FP_IA/FN_IA por método, por família e para a união, com numeradores e denominadores (ocorrências operacionais avaliáveis, negativos, tiles revisados, ilegíveis, fora do escopo); observações `provisorio` contadas à parte; divergências com id próprio, tipo (`fp`, `fn`, `id_errado`, `duplicata`, `papel_errado`), id da observação e/ou predição, `method_id`, página, bbox e tile de evidência. Avança o checkpoint para `comparado`.
- Sem recall global quando `escopo = regional`; o relatório declara o escopo.
- Testes em `tests/unit/test_curation_compare.py` (a criar) com registros sintéticos.

**Fora de escopo:** alterar `symbol_benchmark_evaluator.py`; decidir correções.

**Passos de implementação:**

1. Testes: TP/FP/FN conhecidos num caso sintético; predição fora do escopo não vira FP; ambiguidade não vira TP exato; duplicata detectada; recusa por hash/referência não congelada; determinismo.
2. Implementar.

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação (`Explore`): "quais são a assinatura e o retorno de `geometry_match` e como `_pairs`/`_measure` fazem o casamento 1:1 (`scripts/symbol_benchmark_evaluator.py:206-407`)?"; "onde ficam `method_id`, `family`, `class_id`, `layer`, `bbox` em `predictions.json` do runner?".
- Partes paralelas: nenhuma.
- Foco do verificador: predição fora da região revisada contada como FP; denominadores incoerentes; comparação aceita com referência não congelada; métrica de recall global publicada em escopo regional; ambiguidade contada como TP exato.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E05 — "Comparador regional" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Desenho do fluxo-alvo", "Restrições e invariantes" e o "Protocolo de execução" —, a seção E05 inteira e o "Evidências e handoff" de E02 e E04. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E02 e E04 estão #concluida e que o código bate com os handoffs; se não, ou se o código divergiu do plano, pare e relate sem implementar.

Objetivo: criar scripts/curation_compare.py, que compara inferência e referência congeladas só nas regiões revisadas, reutilizando geometry_match, e grava comparacao-vNNN.json com TP_IA/FP_IA/FN_IA por método, família e união, denominadores e divergências rastreáveis. Não altere scripts/symbol_benchmark_evaluator.py.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E05 para #em-andamento no índice e no título;
- investigação: um subagente Explore responde às perguntas de "Estratégia de execução" de E05;
- escreva tests/unit/test_curation_compare.py primeiro com casos sintéticos de resultado conhecido; depois implemente;
- verificação independente com o Prompt do verificador, com foco em escopo regional, denominadores, referência não congelada e ambiguidade.

Critérios de aceite (detalhes na seção E05):
- caso sintético produz exatamente os TP/FP/FN esperados por método e união;
- predição fora do escopo e ambiguidade não distorcem as métricas; duplicata é sinalizada;
- recusa referência não congelada ou hash divergente;
- testes, Ruff, formatação e mypy passam.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com todos os critérios atendidos e parecer APROVADO do verificador; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E05 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador, notas para a próxima etapa — inclusive o formato das divergências) e responda com um resumo curto de mudanças, validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] Caso sintético com 5 ocorrências operacionais e 6 predições de 2 métodos produz exatamente os TP_IA/FP_IA/FN_IA esperados por método e na união, com denominadores no relatório.
- [ ] Predição cujo centro está num tile descartado ou numa região ilegível aparece em `fora_do_escopo` e não em FP.
- [ ] Observação com alternativas casada por classe conta como TP de classe e não como TP de ID exato.
- [ ] Duas predições do mesmo método sobre a mesma ocorrência geram uma divergência `duplicata`.
- [ ] Referência não congelada ou SHA-256 divergente → código de saída ≠ 0 e checkpoint inalterado.
- [ ] Testes, Ruff, formatação e mypy passam.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_compare.py tests/unit/test_curation_reference.py tests/unit/test_benchmark_symbols.py -q` → todos passam.
- `.venv/Scripts/python.exe -m ruff check .`, `-m ruff format --check .`, `-m mypy` → sem erros.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- `geometry_match` privado demais para reuso → importar a função pública existente; se for preciso extrair um auxiliar, fazê-lo sem mudar `PROTOCOL` nem resultados de `evaluate` (o teste existente do avaliador continua passando).

**Evidências e handoff:**

- Snapshot inicial: `712905e319e28f036cfabc8fe14972fb54fa3e07` (recebido do orquestrador). Snapshot ao fim da implementação (antes deste handoff): `41edab85a78f1e8d446727829191c973da6fbec8`; `git diff --stat` entre os dois mostra só os três arquivos abaixo.
- Arquivos alterados: `scripts/curation_compare.py` (novo), `tests/unit/test_curation_compare.py` (novo, 31 casos), este roadmap (tag e handoff de E05). `scripts/symbol_benchmark_evaluator.py` (e `PROTOCOL`), `scripts/curation_round.py`, `scripts/curation_infer.py`, `scripts/curation_render.py`, `scripts/curation_reference.py`, `tests/fixtures/e10_characterization/` e `tests/unit/test_characterization_support.py` intocados.
- Decisões:
  - Preparação: E02 e E04 `#concluida`; o código confere com os handoffs (`curation_infer`: marco `inferido` com artefato `pdfs/ID/inferencia-vNNN` de tipo diretório e `simbolos/predictions.json`; `curation_reference`: `carregar_referencia_vigente`, `_indice_vigente`, `contida_na_uniao`, `FAMILIA_LOCAL`, bloco `congelamento` com `indice_tiles_sha256` e `exposicao_predicoes`; runner: `predictions.json` com `methods`, `documents`, `predictions`, `local_candidates`, `executions`, e `provenance.variant_id` só no método de pacotes). Investigação feita diretamente (adendo do orquestrador): `geometry_match(first, second)` devolve `{eligible, criterion (iou|thin_endpoints|None), iou, endpoint_distance_normalized, length_ratio}`; `_pairs` faz casamento de cardinalidade máxima por caminhos aumentantes, filtrando por `(document_id, page, layer)` e `class_id`; `_measure` separa candidatas operacionais, positivas (`confirmed` + `operational`), incertas (`evaluability != confirmed`, casadas sem classe → `unresolved`) e controles (`confirmed` não operacionais → FP `nonoperational_context`), e marca como `duplicate` (FP) a predição sem par que tinha aresta elegível.
  - **Reuso do avaliador sem alterá-lo:** importa `geometry_match`, `PROTOCOL`, `_measure`, `_union`, `_group_metrics` e `_geometry`. Métricas de classe, união (equivalência exata entre métodos, duplicatas internas mantidas), duplicatas e controles negativos são exatamente os do protocolo `symbols-e02-v1`; `geometry_match` também é usado diretamente para ligar FP/FN a confusões de classe e predições não operacionais a ocorrências. Cada observação vira ocorrência do avaliador: `operacional` sustentada → `confirmed/operational` (positiva); `informativo`/`negativo` sustentados → `confirmed/informative|negative` (controle); `provisorio` e `papel = desconhecido` → `ambiguous`; `estado = ilegivel` e família `local-unknown` → `unassessable`. Esses quatro ficam fora dos denominadores, e predições que só casam com eles vão para `nao_resolvidas` (por categoria), nunca para FP.
  - **Escopo regional:** predição (e observação) entra se o centro da bbox está num tile revisado da mesma página/camada e fora de `regioes_ilegiveis` (tolerância `TOLERANCIA_BBOX` de E04). Em página com `camada_anotada_igual_base = true`, tile `base` revisado também torna revisado o gêmeo `annotation`, e as regiões ilegíveis `base` valem para `annotation` (mesma regra de cobertura de E04). Motivos de `fora_do_escopo`: `regiao_ilegivel`, `tile_descartado` (todos os tiles que contêm o centro são `descartado_branco`), `tile_nao_revisado`, `pagina_fora_do_indice`. Observação com centro em região ilegível sai do denominador (`observacoes.fora_do_escopo`).
  - **ID exato:** segundo `_measure` com chave `class_id#variante`; positivas só as operacionais com `id_inventario`; observação com `alternativas` vira `ambiguous` nesse nível (predição sobre ela fica em `nao_resolvidas.ambigua`, nunca TP nem FP exato); candidatas só as predições operacionais que informam `provenance.variant_id` (na união, a variante dos membros). `aplicavel` só para métodos em `METODOS_COM_ID_EXATO = {declarative-vector-packages}` ou que informem variante em alguma predição; não aplicável → `tp_ia/fp_ia/fn_ia = null` (não zero). `id_errado` vem dos pares de classe com `id_inventario` diferente da variante predita.
  - **Revocação:** cada bloco traz `precisao`, `revocacao_regional` (TP/(TP+FN) dentro do escopo) e `revocacao_global`, que é `null` com `escopo = regional` e igual à regional com `completo`. O relatório declara `escopo` e `limitacoes`.
  - **Métodos:** os de `predictions.json/methods`; método só de `local_candidates` (metadado `evaluation_scope` iniciando por `local_candidates`, hoje `document-local-legend`) e sem predições vai para `metodos_excluidos` com o motivo, em vez de aparecer com FN em tudo. `execucao` por método conta `executions` só nas páginas/camadas revisadas; `failed` → `status: falha` e o método entra em `metodos_com_falha` (falha, não zero).
  - **Recusas** (todas antes de qualquer escrita → `ComparacaoRecusadaError`, código 1 na CLI, checkpoint e comparações intactos): referência sem `checkpoint.referencia`/marco `referencia_congelada`; `--referencia vNNN` sem evento `referencia_congelada` que a registre (órfã ou inexistente → "não foi congelada"); SHA-256 do arquivo diferente do registrado; arquivo sem bloco `congelamento`; inferência sem marco `inferido`, ou `--inferencia vNNN` sem evento `inferido` que a registre; `hash_diretorio` da pasta diferente do registrado; `pdf.sha256` da referência diferente do checkpoint; `documents` de `predictions.json` sem exatamente o `example:CAMINHO` ou com SHA-256 diferente do da referência; índice de tiles diferente do marco `renderizado` (`_indice_vigente`) ou do `indice_tiles_sha256` do congelamento (exceto referência reutilizada de outra rodada, cujo índice muda de `pdf_id`: aceita só se todos os tiles revisados existem, com `indice_tiles.igual_ao_congelamento: false`); predição com bbox/trace inválida pelo `_geometry` do avaliador, método desconhecido, camada/página inválida, id repetido ou de outro documento; transição para `comparado` recusada (ex.: fase terminal). Na referência só o SHA-256 do PDF precisa ser igual (o `pdf_id` de uma referência reutilizada pode ser o da rodada anterior).
  - **Gravação:** `pdfs/ID/comparacao-vNNN.json` = JSON canônico, sem horário nem caminho absoluto (só relativos à rodada), número seguinte ao maior existente sob a trava `pdfs/ID/comparacao.lock`, criação exclusiva (`_criar_exclusivo` de E04); arquivo ocupado nunca é sobrescrito. Mesmas entradas → bytes idênticos. Só quando referência **e** inferência comparadas são as vigentes o checkpoint avança para `comparado` (artefato = o arquivo; `dados` = `versao`, `inferencia`, `referencia`, `escopo`, `uniao` {tp_ia, fp_ia, fn_ia}, `divergencias`, `metodos_com_falha`); se a transição falhar, o arquivo é removido. Com `--inferencia`/`--referencia` não vigentes a comparação é diagnóstica: grava o arquivo com `vigente: false` e não toca o checkpoint.
- Validações executadas:
  - Testes escritos antes do módulo: `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_compare.py -q` falhou na coleta (`ImportError: cannot import name 'curation_compare'`); depois da implementação → passam (um teste corrigido: o FN de O1 aparece também para o segundo método, sem predições, o que é correto; adicionado filtro por método).
  - `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_compare.py tests/unit/test_curation_reference.py tests/unit/test_benchmark_symbols.py -q` → `159 passed`. `tests/unit/test_curation_round.py tests/unit/test_curation_infer.py tests/unit/test_curation_render.py` → `131 passed`.
  - Testes ligados aos critérios: `test_caso_sintetico_produz_tp_fp_fn_esperados_por_metodo_e_uniao` (5 ocorrências operacionais, 6 predições de 2 métodos: pacotes 2/1/3, transformadores 2/1/3, união 3/2/2 com 5 candidatas, também por família) e `test_denominadores_do_caso_sintetico` (tiles, regiões, observações e predições exatos); `test_predicao_fora_do_escopo_nao_vira_fp` (centro em tile descartado, em região ilegível e em tile não revisado → `fora_do_escopo` com os três motivos, nenhum FP nem divergência) e `test_observacao_em_regiao_ilegivel_sai_do_denominador`; `test_alternativas_contam_como_tp_de_classe_e_nunca_como_tp_exato` e `test_variante_igual_a_uma_alternativa_nao_vira_tp_exato`; `test_duas_predicoes_do_mesmo_metodo_geram_uma_duplicata` (exatamente uma divergência `duplicata`); `test_referencia_nao_congelada_e_recusada_sem_alterar_checkpoint`, `test_versao_de_referencia_nao_registrada_e_recusada`, `test_referencia_adulterada_e_recusada`, `test_sha256_do_pdf_divergente_entre_referencia_e_inferencia_e_recusado`, `test_inferencia_adulterada_ou_sem_registro_e_recusada`, `test_sem_inferencia_e_recusado`, `test_fase_terminal_e_recusada`, `test_predicao_com_bbox_invalida_e_recusada` (todos: exceção ou código 1, bytes do checkpoint iguais e nenhum `comparacao-v*.json`); além de `id_errado`, `papel_errado` (controle negativo e predição não operacional), provisória/desconhecida à parte, falha de execução, método só de candidatos locais, gêmeo da camada anotada, escopo completo com revocação global, divergências que somam FP/FN e são rastreáveis, avanço para `comparado`, determinismo e não sobrescrita, versões não vigentes sem tocar o checkpoint, referência revisada, CLI por onda e recusas de argumentos.
  - Mutações manuais (todas detectadas, arquivo restaurado depois): região ilegível ignorada; escopo ignorado (todo centro dentro); alternativa convertida em ID exato; hash da inferência não conferido; SHA-256 do PDF não conferido; revocação global publicada em escopo regional; regra do gêmeo removida; versão de referência sem registro aceita; duplicata tratada como FP comum.
  - `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`; `-m ruff format --check .` → `458 files already formatted`.
  - `.venv/Scripts/python.exe -m mypy` → 2 erros, ambos em `tests/unit/test_characterization_support.py` (arquivo não rastreado preexistente do usuário, presente no snapshot inicial: importa `tests.characterization`, inexistente, e um `no-any-return`; não alterado); `-m mypy --exclude 'test_characterization_support\.py$'` → `Success: no issues found in 410 source files`.
  - Suíte inteira sem o arquivo preexistente (`pytest --ignore=tests/unit/test_characterization_support.py`): `2314 passed` e 1 falha não relacionada e já conhecida, `tests/unit/test_windows_app_identity.py::test_window_identity_sets_taskbar_relaunch_icon_and_clears_properties` (caixa `C:\zeny` × `C:\Zeny`, ambiental).
  - Radon: maior CC do módulo novo é 16 (`montar_escopo`); `comparar` 13. `scripts/client_artifact_gate.py --source-only` → APROVADO. `git diff` de `scripts/symbol_benchmark_evaluator.py` vazio.
  - Execução real fora dos testes, no scratchpad (removido depois): `curation_round init` + `curation_render` + `curation_infer` (runner real, 9 métodos) sobre `dev-symbols.pdf` de `tests/symbol_benchmark_fixtures.build_corpus`, com referência completa feita das 8 ocorrências da fixture. `curation_compare --onda 1` antes do congelamento → código 1, `recusado` ("não tem referência congelada"); depois de `curation_reference congelar` → código 0, checkpoint em `comparado`, união TP 8 / FP 7 / FN 0 (os FP da união são duplicatas entre métodos com geometria não idêntica, semântica do protocolo), `document-local-legend` em `metodos_excluidos`, JSON sem `Users`/`C:`.
- Parecer do verificador: APROVADO (verificador independente do orquestrador; snapshot de verificação 77189e67674a4459b274132f371fbac839eb48d0). 6/6 critérios aprovados: caso sintético 2/1/3 por método e 3/2/2 na união recalculado à mão; fora do escopo não vira FP; alternativas nunca viram TP exato; duplicata sinalizada; recusa referência não congelada e SHA-256 divergente sem alterar checkpoint; 159 testes focados, Ruff/formatação limpos, mypy limpo exceto o arquivo preexistente do usuário; 7 mutações detectadas; avaliador inalterado. Menores: efeito de borda do escopo pelo centro (registrar no contrato em E09); método com execucao.status=sem_registro não entra em metodos_com_falha (E07/skill devem tratar como alerta); método com falha continua publicando TP/FP/FN marcado (consumidores devem filtrar metodos_com_falha).
- Notas para a próxima etapa:
  - API de `scripts.curation_compare`: `comparar_pdf(rodada_dir, pdf_id, *, inferencia=None, referencia=None, agora=None)` → `{pdf_id, status: sucesso, versao, arquivo, vigente, checkpoint_avancado, uniao {tp_ia, fp_ia, fn_ia}, divergencias, metodos_com_falha, falhas}` ou `ComparacaoRecusadaError(RodadaError)`; `carregar_entradas(...)` → `Entradas` (`.argumentos()`, `.vigente`); `comparar(*, referencia, predicoes, indice, metadados)` (pura e determinística); `montar_escopo(indice, referencia)` → `Escopo` (`motivo_fora`, `tile_evidencia`); `variantes(predicao)`; constantes `ESQUEMA_COMPARACAO`, `NOME_COMPARACAO`, `METODOS_COM_ID_EXATO`, `CATEGORIAS_INCERTAS`. A CLI imprime JSON canônico `{pdfs: [...], totais: {sucesso, recusado, falha}}`; código 0 só se todos tiveram sucesso. A comparação vigente de um PDF é a do marco `comparado` (`checkpoint.marcos.comparado.artefatos[0].caminho`), não a de maior número (as diagnósticas também recebem número).
  - Formato de `pdfs/ID/comparacao-vNNN.json` (`curadoria-comparacao-v1`): `schema_version`, `pdf_id`, `document_id`, `sha256_pdf`, `vigente`, `escopo`, `protocolo` {`id`, `sha256`}, `referencia` {`versao`, `arquivo`, `sha256`, `origem`, `reutilizada`, `exposicao_predicoes`, `vigente`}, `inferencia` {`versao`, `arquivo`, `sha256`, `predictions_sha256`, `vigente`}, `indice_tiles` {`sha256`, `sha256_no_congelamento`, `igual_ao_congelamento`}, `denominadores` {`tiles` {`indice`, `a_revisar`, `descartado_branco`, `revisados`, `revisados_por_gemeo`, `revisados_descartados`, `a_revisar_nao_revisados`}, `regioes_ilegiveis`, `observacoes` {`total`, `em_escopo`, `fora_do_escopo`, `operacionais_avaliaveis`, `negativos`, `provisorias`, `ilegiveis`, `papel_desconhecido`, `locais`, `ambiguas`, `com_id_inventario`}, `predicoes` {`total`, `em_escopo`, `fora_do_escopo`, `nao_operacionais_em_escopo`, `candidatos_locais_ignorados`}}, `metodos` {METHOD_ID: {`classe`, `id_exato`, `por_familia`, `execucao` {`status` executado|falha|sem_registro, `por_status`, `falhas` [{pagina, camada}]}}}, `metodos_com_falha`, `metodos_excluidos` {METHOD_ID: motivo}, `uniao` {`classe`, `id_exato`, `por_familia`, `candidatas`, `observacoes_entrada`}, `divergencias` [...], `fora_do_escopo` {`total`, `por_motivo`, `por_metodo`, `predicoes` [{predicao_id, method_id, pagina, camada, motivo}], `observacoes` [{observacao_id, motivo}]}, `limitacoes`. Bloco `classe`: `tp_ia`, `fp_ia`, `fn_ia`, `precisao`, `revocacao_regional`, `revocacao_global`, `predicoes_avaliadas`, `duplicatas`, `papel_errado`, `nao_resolvidas` {total, provisorio, papel_desconhecido, ilegivel, local}, `nao_operacionais`. Bloco `id_exato`: `aplicavel`, os mesmos seis campos de métrica (null se não aplicável), `ocorrencias_com_id`, `ocorrencias_ambiguas`, `predicoes_com_id`, `predicoes_sem_id`, `id_errado`, `nao_resolvidas` (+ `ambigua`), `por_familia`. `por_familia` {FAMILIA: {seis campos de métrica, `ocorrencias`, `predicoes`}}.
  - **Formato das divergências** (lista ordenada por `method_id`, página, camada, tipo, observação, predição; só por método, a união não gera divergências próprias): `id` (`div-` + 16 hex do SHA-256 de `[nivel, tipo, method_id, observacao_id, predicao_id]`, estável entre execuções com as mesmas entradas), `tipo` (`fp` | `fn` | `duplicata` | `papel_errado` | `id_errado`), `nivel` (`classe` | `id_exato`; só `id_errado` é `id_exato`), `conta_em` (`fp_ia` | `fn_ia` | null; a soma por método de `conta_em` reproduz FP_IA/FN_IA de classe; `papel_errado` de predição não operacional e `id_errado` são diagnósticos, com null), `method_id`, `observacao_id` (ou null), `predicao_id` (ou null), `pagina`, `camada`, `familia`, `class_id`, `bbox` (da predição; da observação em `fn`), `tile_evidencia` (o da observação quando há observação; senão o tile revisado que contém o centro da predição), `perdida_pela_uniao` (só em `fn`: true se nenhum método achou a ocorrência; null nos demais) e `detalhe` {`motivo`: em `fp`, `sem_ocorrencia` ou `classe_divergente` (com `classe_referencia` e `observacao_id` da ocorrência confundida); em `fn`, `sem_predicao` ou `classe_divergente` (com `classe_predita` e `predicao_id` da predição confundida); em `duplicata`, `duplicata` + `observacoes_casaveis`; em `papel_errado`, `controle_nao_operacional` (+ `contexto_referencia`, `criterio`; conta como FP) ou `predicao_nao_operacional` (+ `contexto_predito`); em `id_errado`, `id_inventario_divergente` + `id_inventario` e `variantes_preditas`}. Para E07 agrupar por (tipo, família, `class_id`, `method_id`), usar `familia`/`class_id` da própria divergência e filtrar por `conta_em`/`perdida_pela_uniao` conforme a prioridade desejada.
  - Os FP da união incluem duplicatas entre métodos com geometria não idêntica (protocolo `symbols-e02-v1`); a priorização do backlog deve olhar as divergências por método e `perdida_pela_uniao`, não o FP bruto da união.
  - Pendências fora do escopo: `tests/unit/test_characterization_support.py` (preexistente) continua quebrando o mypy do repositório e a coleta do pytest da suíte inteira; `test_windows_app_identity` falha nesta máquina por caixa de caminho. Os dois afetarão E10 se o usuário não os resolver.

---

## E06 — Auditoria por dupla leitura amostral — #concluida

**Objetivo:** criar `scripts/curation_audit.py`, que sorteia de forma determinística e estratificada uma amostra de tiles para um segundo leitor visual independente e mede a concordância com a referência principal.

**Por que agora:** é a salvaguarda que permite confiar numa referência feita em paralelo e mais depressa, e que dá um número para "sem perder muita precisão".

**Dependências e paralelismo:** E04. Pode correr em paralelo com E05 (em worktree separado); não há arquivo em comum.

**Escopo:**

- `scripts/curation_audit.py` (a criar):
  - `amostrar --rodada DIR (--onda K | --pdf ID ...) [--fracao 0.15] [--minimo 4] [--semente 0] [--incluir-descartados 0.05]`: amostra estratificada por página e faixa de ocupação, com uma fração pequena de tiles descartados para conferir a triagem; grava `auditoria/amostra-vNNN.json`.
  - `concordancia --rodada DIR --pdf ID --auditoria JSON [--limiar 0.90]`: valida a referência do auditor com as mesmas regras de E04 restritas aos tiles amostrados, casa com a referência principal usando o mesmo critério geométrico, calcula concordância de classe e de ID exato, lista discordâncias e decide `referencia_confiavel`, `ampliar_amostra` (primeira vez abaixo do limiar) ou `encerrar_com_pendencia` (segunda vez). Tile descartado com observação do auditor é reportado como falha de triagem. Avança o checkpoint para `auditado`.
- Testes em `tests/unit/test_curation_audit.py` (a criar).

**Fora de escopo:** produzir as leituras (tarefa dos subagentes); estatística inferencial além de proporções com denominador.

**Passos de implementação:**

1. Testes: amostra determinística para a mesma semente; estratos representados; mínimo respeitado; concordância calculada num caso conhecido; decisão nos três estados; falha de triagem reportada.
2. Implementar.

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação: nenhuma (formatos vêm do handoff de E03 e E04).
- Partes paralelas: nenhuma.
- Foco do verificador: amostra que não depende só da semente; auditor com acesso à referência principal pelo formato de saída da amostra (a amostra não pode conter observações da referência); limiar aplicado ao nível errado; falha de triagem silenciosa.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E06 — "Auditoria por dupla leitura amostral" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Desenho do fluxo-alvo" e o "Protocolo de execução" —, a seção E06 inteira e o "Evidências e handoff" de E03 e E04. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E04 está #concluida e que o formato da referência bate com o handoff; se não, ou se o código divergiu do plano, pare e relate sem implementar.

Objetivo: criar scripts/curation_audit.py com amostrar (estratificado, determinístico, inclui fração de tiles descartados) e concordancia (classe e ID exato, decisão referencia_confiavel / ampliar_amostra / encerrar_com_pendencia, falha de triagem reportada). A amostra entregue ao auditor nunca contém observações da referência principal.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E06 para #em-andamento no índice e no título;
- sem investigação delegada: os formatos estão nos handoffs de E03 e E04;
- escreva tests/unit/test_curation_audit.py primeiro; depois implemente;
- verificação independente com o Prompt do verificador, com foco em determinismo, cegueira do auditor, nível do limiar e falha de triagem.

Critérios de aceite (detalhes na seção E06):
- mesma semente gera a mesma amostra; todos os estratos aparecem; mínimo respeitado;
- concordância e decisão corretas em casos sintéticos dos três estados;
- testes, Ruff, formatação e mypy passam.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com todos os critérios atendidos e parecer APROVADO do verificador; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E06 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador, notas para a próxima etapa) e responda com um resumo curto de mudanças, validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] Duas chamadas de `amostrar` com a mesma semente geram arquivos idênticos; semente diferente gera amostra diferente; cada página com tiles `a_revisar` contribui com ao menos um tile; nunca menos que `--minimo`.
- [ ] O arquivo de amostra contém só ids/caminhos de tiles e nenhuma observação da referência principal.
- [ ] Casos sintéticos produzem concordância de classe 1,0 → `referencia_confiavel`; 0,8 na primeira auditoria → `ampliar_amostra`; 0,8 na segunda → `encerrar_com_pendencia`.
- [ ] Observação do auditor num tile descartado aparece como `falha_triagem` no relatório.
- [ ] Testes, Ruff, formatação e mypy passam.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_audit.py tests/unit/test_curation_reference.py -q` → todos passam.
- `.venv/Scripts/python.exe -m ruff check .`, `-m ruff format --check .`, `-m mypy` → sem erros.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Leitor e auditor do mesmo modelo erram de forma correlacionada → o relatório declara que a concordância mede consistência entre leituras, não confirmação humana (invariante herdado).

**Evidências e handoff:**

- Snapshot inicial: `0067f77694f9b2e59aa4ffc246773046ecd1e53e` (recebido do orquestrador). Snapshot ao fim da implementação (antes deste handoff): `54e9bd4038d22c2c5256420d7db8ba7912c6818e`; `git diff --stat` entre os dois mostra só os cinco arquivos abaixo.
- Arquivos alterados: `scripts/curation_audit.py` (novo), `tests/unit/test_curation_audit.py` (novo, 52 casos), `scripts/curation_round.py` (uma linha de regra + comentário: `INVALIDA["referencia_congelada"]` passa a incluir `auditado`), `tests/unit/test_curation_round.py` (1 teste novo dessa regra), este roadmap (tag e handoff de E06). `scripts/curation_reference.py`, `scripts/curation_compare.py`, `scripts/curation_render.py`, `scripts/symbol_benchmark_evaluator.py`, o inventário, `tests/fixtures/e10_characterization/` e `tests/unit/test_characterization_support.py` intocados.
- Decisões:
  - Preparação: E04 `#concluida`; o código confere com os handoffs de E03 e E04 (`carregar_indice`, `_indice_vigente`, `validar_arquivo(..., tiles_permitidos=...)`, `carregar_referencia_vigente`, `_criar_exclusivo`, `_dentro`, ids `pNNN-base|anotada-tLLCC`, `estado`, `ocupacao`, `camada_anotada_igual_base`). Sem investigação delegada (adendo). Reuso de E05 (já `#concluida`) só por importação: `montar_escopo`/`Escopo.motivo_fora`/`tile_evidencia` para a regra de escopo pelo centro (com gêmeo da camada anotada), e `_pairs` do avaliador `symbols-e02-v1` para o casamento 1:1 (o avaliador não muda).
  - **Amostra cega e determinística:** depende só do índice de tiles vigente, dos parâmetros e da semente — nunca lê a referência (testado congelando uma referência com marcas depois de amostrar: o arquivo é byte a byte o mesmo e não contém nada dela). População = todos os tiles do índice, salvo a camada `annotation` de página com `camada_anotada_igual_base = true`. Estratos por página: `pNNN-ocupacao-1..3` (tercis dos `a_revisar` da página por `(ocupacao, id)`, as duas camadas juntas; menos faixas se houver menos de 3 tiles) e `pNNN-descartados`. Tamanho dos `a_revisar` = `min(população, max(--minimo, teto(--fracao × população), nº de estratos))`, um por estrato e o restante pelo maior resto proporcional (empate por nome, aritmética com `Fraction`; teto tolerante a ruído de ponto flutuante: 0,2 × 15 = 3). Descartados por página = `teto(--incluir-descartados × n)` (0 desliga). Dentro do estrato, ordem por SHA-256 de `(semente, SHA-256 do PDF, id)`; a lista final segue a ordem do índice, sem revelar estrato nem estado de cada tile.
  - Arquivo `pdfs/ID/auditoria/amostra-vNNN.json` (`curadoria-amostra-auditoria-v1`, JSON canônico, sem horário nem caminho absoluto): `schema_version`, `pdf_id`, `sha256_pdf`, `versao`, `nivel` (1 base, 2 ampliada), `amostra_anterior` (`null` ou {`arquivo`, `sha256`}), `parametros` {`fracao`, `minimo`, `semente`, `incluir_descartados`}, `indice_tiles_sha256`, `estratos` [{`estrato`, `populacao`, `amostrados`}] (só contagens), `tiles` [{`id`, `arquivo`, `pagina`, `camada`}] e `totais` {`tiles`, `populacao`}. Repetir `amostrar` com os mesmos parâmetros reaproveita a última versão (`reutilizada: true`); parâmetros diferentes criam a próxima versão (criação exclusiva, nunca sobrescreve). `amostrar` exige o marco `renderizado` com o índice conferido, recusa fase terminal e não toca o checkpoint.
  - **Ampliação:** `--ampliar` só é aceito se a última concordância decidiu `ampliar_amostra`; usa a amostra auditada (conferida pelo SHA-256 registrado no relatório), dobra `fracao`, `minimo` e `incluir_descartados` (teto 1), mantém a semente e inclui todos os tiles dela (superconjunto). Parâmetros explícitos com `--ampliar` são recusados. Depois de um `ampliar_amostra` ou `encerrar_com_pendencia`, nova amostra de nível 1 é recusada (impede trocar a semente até passar).
  - **Concordância:** valida a leitura do auditor com `validar_arquivo(..., tiles_permitidos=amostra)` (regras de E04) e exige que ela revise **todos** os tiles amostrados; recusa leitura com bloco `congelamento` (seria uma referência congelada, não uma leitura independente). Entram só observações cujo centro está num tile amostrado revisado pelo auditor **e** num tile revisado pela referência principal, fora das regiões ilegíveis das duas e com `estado ≠ ilegivel`; as demais ficam contadas por motivo (`fora_da_amostra`, `tile_nao_revisado_pela_referencia`, `regiao_ilegivel_auditoria|referencia`, `estado_ilegivel`). Em página com camada anotada igual à base, `annotation` é comparada como `base`. Casamento: `_pairs` na mesma `class_id`, depois `_pairs(classify=False)` entre as sobras (classe divergente); o resto é `so_referencia`/`so_auditoria`. **Concordância de classe** = concordantes / (concordantes + divergentes + só referência + só auditoria), com o denominador no relatório. **ID exato** = sobre os pares de mesma classe em que algum lado tem `id_inventario`: iguais / aplicáveis (alternativas de um lado contra ID exato do outro contam como divergência; par sem ID nos dois lados vai para `sem_id_exato`). `papel` diferente num par concordante vira discordância diagnóstica `papel_divergente`.
  - **Decisão** (só sobre a concordância de classe; o ID exato é apenas reportado): `referencia_confiavel` se concordantes/total ≥ `--limiar` (comparação exata com `Fraction`, inclusiva); abaixo do limiar, `ampliar_amostra` com amostra de nível 1 e `encerrar_com_pendencia` com a ampliada. Denominador zero (nenhuma observação comparável) é tratado como abaixo do limiar (conservador). Só `referencia_confiavel` avança o checkpoint para `auditado` (artefato = relatório; `dados` com `decisao`, concordâncias, `limiar`, `total_classe`, `falhas_triagem`, versão/SHA-256 da referência e da amostra). As outras decisões gravam o relatório e não tocam o checkpoint; `encerrar_com_pendencia` não encerra o PDF sozinho — a skill roda `curation_round avancar --fase encerrado_com_pendencias --nota ...`. Depois de `encerrar_com_pendencia`, nova concordância é recusada; depois de `ampliar_amostra`, concordância sobre amostra de nível 1 é recusada.
  - **Falha de triagem:** observação do auditor cujo `tile_evidencia` é um tile `descartado_branco` amostrado, ou cujo centro só cai em tiles descartados (algum amostrado), vira item de `falhas_triagem` {`observacao_id`, `tile_id`, `pagina`, `camada`, `class_id`, `ocupacao`} e uma linha em `pendencias`; a CLI escreve `alerta: falha_triagem: ...` no stderr e o resumo e o evento do checkpoint trazem a contagem. Não altera a decisão (a observação fica fora da concordância quando a referência principal não revisou o tile).
  - Relatório `pdfs/ID/concordancia-vNNN.json` (`curadoria-concordancia-v1`, fora de `auditoria/` para que um auditor da amostra ampliada não leia o resultado anterior; numeração crescente, criação exclusiva, sem horário): `schema_version`, `pdf_id`, `sha256_pdf`, `versao`, `referencia` {`versao`, `arquivo`, `sha256`, `origem`}, `amostra` {`versao`, `arquivo`, `sha256`, `nivel`, `tiles` {`total`, `a_revisar`, `descartados`, `nao_revisados_pela_referencia`}}, `auditoria` {`arquivo` (relativo à rodada ou só o nome), `sha256`, `modelo`, `observacoes`, `tiles_revisados`}, `indice_tiles_sha256`, `limiar`, `classe` {`concordantes`, `divergentes`, `so_referencia`, `so_auditoria`, `total`, `concordancia`}, `id_exato` {`aplicaveis`, `concordantes`, `divergentes`, `sem_id_exato`, `concordancia`}, `observacoes` {`referencia`|`auditoria`: {`total`, `comparaveis`, `fora_da_amostra`, `excluidas` {motivo: n}}}, `decisao`, `motivo_decisao`, `discordancias` [{`id` (`disc-` + 16 hex estáveis), `tipo` (`classe_divergente`|`so_referencia`|`so_auditoria`|`id_divergente`|`papel_divergente`), `conta_em` (`classe`|`id_exato`|null), `observacao_referencia`, `observacao_auditoria`, `class_referencia`, `class_auditoria`, `id_inventario_referencia`, `id_inventario_auditoria`, `pagina`, `camada`, `tile`}], `falhas_triagem`, `pendencias`, `limitacoes` (declara que a concordância mede consistência entre duas leituras de IA, não confirmação humana nem norma) e `leitura_auditoria` (cópia canônica da leitura, para reprodutibilidade).
  - **Revisão da referência × marco `auditado` (nota do orquestrador):** corrigido dentro do escopo. `INVALIDA["referencia_congelada"]` em `scripts/curation_round.py` agora é `("comparado", "auditado")`: uma nova versão da referência (revisão; congelamento e reuso não têm `auditado` antes) remove o marco `auditado`, e `fechado` volta a exigir uma concordância medida contra a versão vigente. Custo baixo: a mesma leitura do auditor pode ser reavaliada com `concordancia` contra a nova versão, sem nova leitura (testado). `em_correcao` e nova inferência continuam sem invalidar `auditado` (não mudam a referência). Os handoffs de E01/E04 que dizem "não invalida `auditado`" descrevem o estado anterior a esta etapa.
  - Concorrência: `amostrar` e `concordancia` usam a trava `pdfs/ID/auditoria.lock` (`_trava` de E01); a escrita do checkpoint segue sob a trava dele. Recusas acontecem antes de qualquer escrita (`AuditoriaRecusadaError`/`ReferenciaInvalidaError`/`TransicaoInvalidaError`, todas `RodadaError`, código 1 na CLI); se a transição para `auditado` falhar, o relatório recém-criado é removido.
- Validações executadas:
  - Testes escritos antes do módulo: `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_audit.py -q` falhou na coleta (`ModuleNotFoundError: scripts.curation_audit`); depois da implementação → `52 passed` (um ajuste no módulo: `carregar_amostra` aceita `vNNN` e `amostra-vNNN`).
  - Validação obrigatória: `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_audit.py tests/unit/test_curation_reference.py -q` → `122 passed`. Curadoria inteira (`test_curation_audit/reference/round/compare/render/infer`) → `285 passed`.
  - Testes ligados aos critérios: `test_mesma_semente_gera_arquivos_identicos` (duas rodadas → bytes iguais; repetir reaproveita v001), `test_semente_diferente_gera_amostra_diferente`, `test_todos_os_estratos_aparecem_e_cada_pagina_contribui` (5 sementes, 7 estratos), `test_faixas_de_ocupacao_sao_tercis_por_pagina`, `test_minimo_respeitado[4/8/12/40]`, `test_fracao_define_o_tamanho_quando_supera_o_minimo`, `test_descartados_entram_na_fracao_pedida[0/0.05/0.5]`, `test_camada_anotada_igual_a_base_fica_fora_da_populacao`; `test_amostra_contem_so_ids_e_caminhos_de_tiles` (chaves exatas, cada tile só `id/arquivo/pagina/camada`, independência da referência); `test_decidir_nos_tres_estados`; `test_concordancia_total_gera_referencia_confiavel_e_avanca_para_auditado` (1,0), `test_concordancia_08_na_primeira_auditoria_pede_ampliar_sem_auditar` (0,8 → checkpoint byte a byte igual), `test_concordancia_08_na_amostra_ampliada_encerra_com_pendencia` (superconjunto, parâmetros dobrados, recusas de reamostrar/reauditar); `test_limiar_e_aplicado_a_concordancia_de_classe_e_nao_a_de_id_exato` (classe 1,0 com ID 0,4 → confiável) e `test_id_exato_perfeito_nao_salva_concordancia_de_classe_baixa`; `test_limiar_configuravel_e_inclusivo`; `test_falha_de_triagem_e_reportada` e `test_falha_de_triagem_aparece_na_saida_da_cli`; `test_discordancias_sao_rastreaveis`; exclusões por região/estado ilegível; gêmeo anotado; amostra sem observações; determinismo do relatório; recusas (sem referência, sem amostra, tile fora da amostra, amostra não revisada inteira, bloco `congelamento`, índice divergente, fase terminal) sem alterar checkpoint; `test_revisar_a_referencia_invalida_o_marco_auditado`; CLI. Em `test_curation_round.py`: `test_nova_versao_da_referencia_exige_nova_comparacao_e_nova_auditoria`.
  - Mutações manuais (todas detectadas, arquivos restaurados e conferidos com `cmp`): sorteio aleatório; chave sem semente; sem um tile por estrato; mínimo ignorado; descartados ignorados; limiar aplicado ao ID exato; limiar estrito (`>`); nível da amostra ignorado; falha de triagem silenciada; sem guarda de histórico; amostra não revisada inteira aceita; sem `tiles_permitidos`; sem segundo casamento entre classes; `auditado` em qualquer decisão; camada anotada igual não normalizada; região ilegível do auditor ignorada; `INVALIDA` revertida (falham o teste de E06 e o novo de E01).
  - `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`; `-m ruff format --check .` → `460 files already formatted`.
  - `.venv/Scripts/python.exe -m mypy` → 2 erros, ambos em `tests/unit/test_characterization_support.py` (arquivo não rastreado preexistente do usuário, presente no snapshot inicial; não alterado); `-m mypy --exclude 'test_characterization_support\.py$'` → `Success: no issues found in 411 source files`.
  - Suíte inteira sem o arquivo preexistente: `pytest --ignore=tests/unit/test_characterization_support.py --deselect tests/unit/test_windows_app_identity.py::test_window_identity_sets_taskbar_relaunch_icon_and_clears_properties` → `2367 passed, 1 deselected` (o desmarcado é a falha ambiental já conhecida de caixa de caminho, registrada em E05).
  - Radon: maior CC do módulo novo é 15 (`_casar`); cobertura de linhas do módulo pelos testes: 94%.
  - Execução real fora dos testes, no scratchpad (removido depois): `curation_round init` + `curation_render` (PDF sintético de 2 páginas) + `python -m scripts.curation_audit amostrar --onda 1` (código 0, 7 tiles: 5 `a_revisar` + 2 descartados, 7 estratos); `concordancia` antes de congelar → código 1 ("faltam os marcos referencia_congelada"); depois de `curation_reference congelar` → código 0, `ampliar_amostra` com 4/5, ID exato 1,0; `amostrar --ampliar` → `amostra-v002`, nível 2, 11 tiles; `status` continua `referencia_congelada`; nenhum `Users`/`C:` nos JSON de `auditoria/` nem no relatório.
- Parecer do verificador: APROVADO (verificador independente do orquestrador; snapshot de verificação 784efb673fffb93cde97b185072db33d29a363bf). 5/5 critérios aprovados: determinismo por semente, estratos e mínimo; amostra só com ids/caminhos de tiles (cegueira testada com referência marcada); três decisões corretas por nível; falha de triagem reportada; 122 testes focados, Ruff/formatação limpos, mypy limpo exceto o arquivo preexistente do usuário; 7 mutações detectadas. Mudança em INVALIDA de scripts/curation_round.py julgada correta e adequada (pedida pelo orquestrador; nova versão da referência remove auditado). Menores: corrida teórica entre leitura da referência e transicionar(auditado) sem reconferir SHA-256; amostra expõe contagem de descartados por estrato e indice-tiles.json fica acessível em render/ (E08 deve restringir o auditor aos PNGs); handoffs de E01/E04 ainda descrevem a regra antiga.
- Notas para a próxima etapa:
  - API de `scripts.curation_audit`: `ParametrosAmostra(fracao=0.15, minimo=4, semente=0, incluir_descartados=0.05)` (`.validar()`, `.ampliada()`, `.registro()`); `populacao(indice)`, `estratos(indice)`, `sortear(indice, parametros, *, obrigatorios=())`, `montar_amostra(...)`; `amostrar_pdf(rodada_dir, pdf_id, parametros=None, *, ampliar=False)` → {`pdf_id`, `status`, `versao`, `arquivo`, `nivel`, `reutilizada`, `tiles`, `a_revisar`, `descartados`, `falhas`} ou exceção; `amostrar(rodada_dir, pdf_ids, *, parametros=None, ampliar=False)` → {`pdfs`, `totais` {sucesso, recusado, falha}}; `carregar_amostra(rodada_dir, pdf_id, versao=None)`; `medir_concordancia(*, referencia, auditoria, amostra, indice, limiar=0.90)` (pura); `decidir(concordantes, total, *, limiar, nivel)`; `concordancia(rodada_dir, pdf_id, arquivo, *, versao_amostra=None, limiar=0.90, inventario=None, agora=None)` → {`pdf_id`, `versao`, `arquivo`, `decisao`, `motivo_decisao`, `concordancia_classe`, `concordancia_id_exato`, `total_classe`, `falhas_triagem`, `checkpoint_avancado`}; constantes `ESQUEMA_AMOSTRA`, `ESQUEMA_CONCORDANCIA`, `DIRETORIO_AUDITORIA`, `DECISOES`, `LIMIAR_PADRAO`, `CONFIAVEL`, `AMPLIAR`, `ENCERRAR`, `LIMITACOES`; exceção `AuditoriaRecusadaError(RodadaError)`.
  - CLI: `amostrar` imprime JSON canônico {`pdfs`, `totais`} (código 0 só se todos tiveram sucesso; recusas também no stderr); `concordancia` imprime o resumo em JSON canônico (código 0 para qualquer decisão; a decisão está no campo `decisao`) e `alerta: falha_triagem: ...` no stderr quando houver.
  - E08 (skill/agentes): fluxo por PDF = `amostrar` → auditor lê **só** os PNG listados em `auditoria/amostra-vNNN.json` e grava a leitura (formato de E04, `escopo: regional`, `tiles_revisados` = todos os tiles da amostra, sem bloco `congelamento`) fora de `auditoria/`, `referencia/`, `leitura/` do leitor e dos `concordancia-*`/`comparacao-*` (ex.: `pdfs/ID/leitura-auditoria/amostra-vNNN.json`) → `concordancia --auditoria ARQUIVO` → `referencia_confiavel`: segue; `ampliar_amostra`: `amostrar --ampliar` e novo auditor sobre a nova amostra; `encerrar_com_pendencia`: `curation_round avancar --fase encerrado_com_pendencias --nota "concordância X abaixo do limiar na amostra ampliada"`. Com `falhas_triagem > 0`, registrar a pendência de triagem (limiar de ocupação de `curation_render`) no relatório da rodada. Após `curation_reference revisar`, rodar `concordancia` de novo (o marco `auditado` foi invalidado) com a mesma leitura do auditor.
  - E07/E11: a concordância vigente de um PDF é a do marco `auditado` (`checkpoint.marcos.auditado.artefatos[0].caminho`); as decisões `ampliar_amostra`/`encerrar_com_pendencia` só existem nos relatórios `concordancia-vNNN.json`. A concordância observada por PDF (classe e ID exato, com denominadores) vai para o relatório local da rodada (H5).
  - Pendências fora do escopo: `tests/unit/test_characterization_support.py` (preexistente) continua quebrando o mypy do repositório e a coleta do pytest da suíte inteira; `test_windows_app_identity` falha nesta máquina por caixa de caminho. Os dois afetarão E10 se o usuário não os resolver.

---

## E07 — Backlog agregado por onda — #concluida

**Objetivo:** criar `scripts/curation_backlog.py`, que junta as divergências de todos os PDFs de uma onda em grupos por causa provável, prioriza por quantos PDFs cada grupo afeta e indica o módulo dono, para que correções sejam feitas uma vez por causa e em pistas paralelas por módulo.

**Por que agora:** é o que troca "corrigir PDF a PDF" por "corrigir causa a causa"; a skill de orquestração distribui o trabalho a partir deste arquivo.

**Dependências e paralelismo:** E05. Não paraleliza.

**Escopo:**

- `scripts/curation_backlog.py` (a criar): `--rodada DIR --onda K`.
- Lê as comparações mais recentes dos PDFs da onda; agrupa divergências por (tipo, família, `class_id`, `method_id`); para cada grupo: PDFs afetados, total de ocorrências, até 5 exemplos com tile de evidência, e módulo(s) dono(s) por um mapa `method_id` → arquivos em `src/zeny_project_handler/adapters/analysis/` e `symbol_packages/`, mantido no próprio script com teste que garante que todo `method_id` emitido pelo runner tem dono.
- Pistas: agrupa grupos com o mesmo conjunto de arquivos donos numa pista; pistas com arquivos disjuntos podem ser corrigidas em paralelo. Grava `ondas/K/backlog.json` e `ondas/K/backlog.md` (resumo legível).
- Testes em `tests/unit/test_curation_backlog.py` (a criar).

**Fora de escopo:** corrigir divergências; alterar métodos.

**Passos de implementação:**

1. Listar os `method_id` emitidos pelo runner e seus módulos.
2. Testes: agrupamento, prioridade, pistas disjuntas, `method_id` sem dono falha o teste de cobertura do mapa.
3. Implementar.

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação (`Explore`): "quais `method_id` cada função `*_method_metadata` de `scripts/symbol_benchmark_runner.py` emite e qual módulo de `src/zeny_project_handler/adapters/analysis/` implementa cada um?".
- Partes paralelas: nenhuma.
- Foco do verificador: método sem dono; pistas marcadas como disjuntas que compartilham arquivo; prioridade que ignora o número de PDFs; exemplos com caminho fora da rodada.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E07 — "Backlog agregado por onda" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Desenho do fluxo-alvo" e o "Protocolo de execução" —, a seção E07 inteira e o "Evidências e handoff" de E05. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E05 está #concluida e que o formato das divergências bate com o handoff; se não, ou se o código divergiu do plano, pare e relate sem implementar.

Objetivo: criar scripts/curation_backlog.py, que agrupa as divergências da onda por tipo, família, classe e método, prioriza por PDFs afetados, atribui módulo dono por method_id e forma pistas de correção com arquivos disjuntos, gravando ondas/K/backlog.json e backlog.md. Não altere métodos nem detectores.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E07 para #em-andamento no índice e no título;
- investigação: um subagente Explore responde à pergunta de "Estratégia de execução" de E07;
- escreva tests/unit/test_curation_backlog.py primeiro, incluindo o teste de que todo method_id do runner tem dono; depois implemente;
- verificação independente com o Prompt do verificador, com foco em método sem dono, pistas falsamente disjuntas e prioridade.

Critérios de aceite (detalhes na seção E07):
- divergências sintéticas de 3 PDFs viram grupos corretos, ordenados por PDFs afetados;
- pistas com arquivos em comum nunca são marcadas como paralelas;
- todo method_id emitido pelo runner tem dono no mapa;
- testes, Ruff, formatação e mypy passam.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com todos os critérios atendidos e parecer APROVADO do verificador; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E07 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador, notas para a próxima etapa — inclusive o mapa method_id → módulos) e responda com um resumo curto de mudanças, validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] Divergências sintéticas de 3 PDFs com um FN de transformador em todos e um FP de pacote em um só geram 2 grupos, o de transformador primeiro, cada um com PDFs afetados e exemplos.
- [ ] Dois grupos que dependem do mesmo arquivo ficam na mesma pista; pistas listadas como paralelas não compartilham arquivo.
- [ ] Teste falha se um `method_id` emitido pelas funções `*_method_metadata` do runner não tiver dono no mapa.
- [ ] Testes, Ruff, formatação e mypy passam.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_backlog.py tests/unit/test_curation_compare.py -q` → todos passam.
- `.venv/Scripts/python.exe -m ruff check .`, `-m ruff format --check .`, `-m mypy` → sem erros.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Mesma divergência com causas diferentes em PDFs diferentes → o grupo é hipótese de causa; o investigador confirma antes de corrigir (registrado na skill de E08).

**Evidências e handoff:**

- Snapshot inicial: `4729050cea7ff7dd94f2c67a186a06b72cb51410` (recebido do orquestrador). Snapshot ao fim da implementação (antes deste handoff): `d0fbf0bf179f99eccfc218b4689d99531f92abd4`; `git diff --stat` entre os dois mostra só os três arquivos abaixo.
- Arquivos alterados: `scripts/curation_backlog.py` (novo), `tests/unit/test_curation_backlog.py` (novo, 36 casos), este roadmap (tag e handoff de E07). Métodos, detectores, pacotes, `scripts/symbol_benchmark_runner.py`, `scripts/curation_compare.py`, `scripts/curation_round.py`, `tests/fixtures/e10_characterization/` e `tests/unit/test_characterization_support.py` intocados.
- Decisões:
  - Preparação: E05 `#concluida`; o formato de `comparacao-vNNN.json` e das divergências confere com o handoff de E05 (campos de `_divergencia` em `scripts/curation_compare.py:420-463`; `metodos[M].execucao.status` ∈ executado|falha|sem_registro; `metodos_com_falha`; marco `comparado` com um artefato `pdfs/ID/comparacao-vNNN.json`). Investigação feita diretamente (adendo): `method_metadata`, `transformer_`, `guy_`, `package_`, `raster_` (2 perfis de `raster_symbols._profile`), `structural_` (2 perfis de `perfil_simbolos_estruturais`) e `legend_method_metadata` emitem 9 `method_id` (mapa nas notas abaixo).
  - **Entradas:** para cada PDF da onda, só a comparação vigente — a do marco `comparado` (`artefatos[0]`), não a de maior número (diagnósticas ficam de fora; testado). O arquivo precisa estar em `pdfs/ID/comparacao-vNNN.json` e ter o SHA-256 registrado no marco; esquema `curadoria-comparacao-v1`, `pdf_id` igual, `vigente: true`, divergências com todos os campos de E05, tipo conhecido e ids únicos. Qualquer violação → `BacklogRecusadoError(RodadaError)`, código 1, nada gravado (nem `ondas/`). PDF sem marco `comparado` não recusa: entra em `pdfs` com `comparacao: null` e alerta `sem_comparacao_vigente`; PDF sem marco `auditado` gera alerta `referencia_nao_auditada` (as divergências entram, sinalizadas).
  - **Grupos:** chave (tipo, família, `class_id`, `method_id`) com `familia`/`class_id` da própria divergência; id `grp-` + 12 hex do SHA-256 da chave (estável entre ondas). Cada grupo: `pdfs_afetados`, `pdfs` (ordem da onda), `ocorrencias`, `ocorrencias_por_pdf`, `perdidas_pela_uniao`, `conta_em` (contagem por `fp_ia`/`fn_ia`/`diagnostico`), `diagnostico` (todas com `conta_em` null, ex.: `id_errado`), `motivos`, `donos`, `pista` e até 5 `exemplos` intercalados entre PDFs (primeiro de cada PDF, depois o segundo…), cada um com `pdf_id`, `divergencia_id`, `comparacao` (caminho relativo), página, camada, bbox, `tile_evidencia`, `tile_arquivo` (do índice de tiles vigente, aceito só se relativo, sem `..` e dentro de `pdfs/ID/`; senão null + alerta `tile_sem_arquivo`), observação, predição, motivo e `perdida_pela_uniao`.
  - **Prioridade:** `pdfs_afetados` desc, depois `ocorrencias` desc, `perdidas_pela_uniao` desc e a chave; `prioridade` = posição (1…n). Diagnósticos não são rebaixados (a chave já os separa).
  - **Falha e sem registro (nota do orquestrador):** tratados explicitamente, sem misturar com divergência comum. Um método é indisponível num PDF se `execucao.status` é `falha` ou `sem_registro`, ou se está em `metodos_com_falha`; todas as divergências dele naquele PDF ficam **retidas** (contadas em `pdfs[].divergencias_retidas` e `totais.divergencias_retidas`) e o método entra em `falhas_execucao` (`falha-…` ou `sem-registro-…`, com PDFs, `locais` das falhas e retidas) e em `alertas` (`metodo_com_falha` / `metodo_sem_registro`). As divergências do mesmo método em outros PDFs, onde executou, continuam nos grupos. Falha tem dono e entra nas pistas (corrigir o detector); `sem_registro` fica sem dono e fora das pistas (pode ser configuração da inferência), só como alerta para o investigador.
  - **Donos:** mapa `DONOS` no script = arquivos que a correção do método edita (o detector e, no legado, também o arquivo da versão do extrator); para `declarative-vector-packages` soma-se `symbol_packages/<família>.json` quando existe (família com `/` ou `..` é ignorada). Método desconhecido → `donos: []`, `pista: null`, id em `sem_dono` e alerta `metodo_sem_dono`; nunca entra em pista.
  - **Pistas:** fecho transitivo por arquivo dono em comum (união-busca), então dois grupos/falhas que dependem do mesmo arquivo sempre ficam na mesma pista e pistas diferentes nunca compartilham arquivo. `paralela` é ainda conferida par a par (`arquivos_compartilhados`, sempre vazio; uma pista conflitante seria `paralela: false`). Ordem: mais PDFs, mais ocorrências, arquivos; ids `pista-01`…; cada pista traz `arquivos`, `grupos`, `falhas_execucao`, `pdfs`, `prioridade` (melhor grupo), `dependencias` (módulos do pacote de análise importados transitivamente, lidos por AST, menos os próprios) e `acoplamentos` (dependência que é arquivo dono de outra pista, ex.: `pymupdf_transformers` depende de `pymupdf_symbols`, dono do legado). Regra registrada em `paralelismo.regra`: o corretor só edita os arquivos da própria pista; mudar uma dependência exige pista própria, em série; depois de integrar uma pista, rodar de novo os testes focados das pistas acopladas.
  - **Gravação:** `ondas/K/backlog.json` (`curadoria-backlog-v1`, JSON canônico) e `ondas/K/backlog.md` (alertas, grupos, pistas, falhas, exemplos), sob a trava `ondas/K/backlog.lock`, com escrita atômica; são uma visão derivada e são **substituídos** a cada execução (mesmas entradas → mesmos bytes; sem horário nem caminho absoluto). Limitações declaradas: grupo é hipótese de causa; referência de IA; retenção por falha; acoplamentos.
- Validações executadas:
  - Testes escritos antes do módulo: `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_backlog.py -q` falhou na coleta (`ImportError: cannot import name 'curation_backlog'`); depois da implementação → `36 passed`.
  - Validação obrigatória: `.venv/Scripts/python.exe -m pytest tests/unit/test_curation_backlog.py tests/unit/test_curation_compare.py -q` → `67 passed`.
  - Testes ligados aos critérios: `test_tres_pdfs_geram_dois_grupos_com_transformador_primeiro` (rodada real de 3 PDFs com checkpoints até `auditado`; FN de transformador nos três + FP de pacote num só → 2 grupos, transformador com prioridade 1, PDFs afetados e exemplos com tile existente dentro da rodada; via CLI, com `backlog.md`), `test_prioridade_e_por_pdfs_afetados_e_nao_por_ocorrencias` (2 PDFs × 1 antes de 1 PDF × 10), `test_desempate_por_ocorrencias_e_perdidas_pela_uniao`, `test_chave_do_grupo_separa_tipo_familia_classe_e_metodo`, `test_exemplos_ficam_limitados_e_distribuidos_entre_pdfs`; `test_grupos_que_dependem_do_mesmo_arquivo_ficam_na_mesma_pista` (raster template/Hough juntos; pacotes de famílias diferentes juntos por `declarative_symbols.py`; 3 pistas disjuntas), `test_pistas_paralelas_nunca_compartilham_arquivo[2/3/4]` (todas as combinações de 2, 3 e 4 dos 9 métodos), `test_formar_pistas_une_por_arquivo_comum_transitivamente`, `test_acoplamento_por_dependencia_editada_por_outra_pista_e_declarado`, `test_dependencias_sao_transitivas_dentro_do_pacote_de_analise`; `test_todo_method_id_emitido_pelo_runner_tem_dono` (chama as 7 funções `*_method_metadata`, inclusive raster e estruturais com as configurações do runner, exige o conjunto exato de funções — nova função faz o teste falhar — e `set(DONOS) ==` ids emitidos, sem dono obsoleto), `test_cobertura_do_mapa_detecta_metodo_sem_dono`, `test_arquivos_donos_existem_e_ficam_na_analise`, `test_dono_de_pacotes_inclui_o_arquivo_da_familia_quando_existe`, `test_metodo_sem_dono_fica_fora_das_pistas_e_gera_alerta`; falha/sem registro (`test_metodo_com_falha_vira_falha_de_execucao_e_nao_divergencia_comum`, `test_metodo_listado_em_metodos_com_falha_tambem_e_falha`, `test_metodo_sem_registro_gera_alerta_e_retem_divergencias`); entradas (sem comparação vigente, referência não auditada, marco × maior número, comparação adulterada recusada sem criar `ondas/`, 4 recusas de formato, divergência repetida, tile fora da rodada); `test_formato_das_divergencias_do_comparador_e_aceito` (divergência gerada por `curation_compare._divergencia`); determinismo/sem caminho absoluto; CLI (resumo, alertas no stderr, onda inexistente → 1); Markdown.
  - Mutações manuais (todas detectadas, módulo restaurado e conferido com `cmp`): prioridade por ocorrências antes de PDFs; pista por conjunto exato de donos; idem com `paralela` sempre verdadeira; dono de `raster-hough-generalizado` removido (falha `test_todo_method_id_emitido_pelo_runner_tem_dono`); falha misturada às divergências comuns; `sem_registro` ignorado; `metodos_com_falha` ignorado; SHA-256 da comparação não conferido; caminho de tile sem validação; exemplos sem intercalar PDFs; pacote da família ignorado; dependências não transitivas.
  - Execução real fora dos testes, no scratchpad (removida depois): 3 PDFs sintéticos com `curation_round init` + `curation_render` + referência congelada + inferência (helpers de `test_curation_compare`) + `curation_compare` real → `python -m scripts.curation_backlog --rodada … --onda 1` código 0: 24 divergências em 7 grupos, 2 pistas paralelas (`pymupdf_transformers.py`; `declarative_symbols.py` + `symbol_packages/family-f02-18.json`), 3 alertas `referencia_nao_auditada` (não houve auditoria), nenhum `Users`/`C:` nos dois arquivos.
  - `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`; `-m ruff format --check .` → `462 files already formatted`.
  - `.venv/Scripts/python.exe -m mypy` → 2 erros, ambos em `tests/unit/test_characterization_support.py` (arquivo não rastreado preexistente do usuário, presente no snapshot inicial: importa `tests.characterization`, inexistente, e um `no-any-return`; não alterado); `-m mypy --exclude 'test_characterization_support\.py$'` → `Success: no issues found in 412 source files`.
  - Suíte inteira sem o arquivo preexistente: `pytest --ignore=tests/unit/test_characterization_support.py --deselect tests/unit/test_windows_app_identity.py::test_window_identity_sets_taskbar_relaunch_icon_and_clears_properties` → `2403 passed, 1 deselected` (o desmarcado é a falha ambiental de caixa de caminho já registrada em E05).
  - Radon: maior CC do módulo novo é 19 (`agregar`); cobertura de linhas/ramos do módulo pelos testes: 95%. `scripts/complexity_gate.py src` e `scripts/client_artifact_gate.py --source-only` aprovados.
- Parecer do verificador: APROVADO (verificador independente do orquestrador; snapshot de verificação 75f8d505323c2e0e324c2844739754faeab4db15). 4/4 critérios aprovados: 3 PDFs geram 2 grupos com transformador primeiro e prioridade por PDFs afetados; pistas por união-busca nunca compartilham arquivo (todas as combinações de 2–4 dos 9 métodos); todo method_id do runner tem dono (conjunto exato de funções de metadados); 67 testes focados, Ruff/formatação limpos, mypy limpo exceto o arquivo preexistente do usuário; tratamento de falha/sem_registro adequado ao invariante. Correção ao handoff: scripts/complexity_gate.py src NÃO passa (exit 1, 18 funções E/F preexistentes em src/, nenhuma mudança em src/ nesta etapa); o módulo novo passa (CC máx. 19). Pendências para E10: esse gate e test_windows_app_identity (caixa de caminho). Baixos: DONOS não cobre dados auxiliares/domínio; status desconhecido tratado como disponível; _importados não captura from . import x nem imports de nível 2; pistas paralelas podem ter acoplamentos por dependência (E08 deve tratá-los como restrição de reinferência).
- Notas para a próxima etapa:
  - **Mapa `method_id` → arquivos donos** (`DONOS` em `scripts/curation_backlog.py`, prefixo `src/zeny_project_handler/adapters/analysis/`): `legacy-vector-symbols` → `pymupdf_symbols.py` + `pymupdf_analyzer.py` (versão `PyMuPdfDocumentAnalyzer.versao`); `transformer-vector-shapes` → `pymupdf_transformers.py`; `guy-vector-shapes` → `pymupdf_guys.py`; `declarative-vector-packages` → `declarative_symbols.py` (+ `symbol_packages/<família>.json` quando existe); `raster-template` e `raster-hough-generalizado` → `raster_symbols.py`; `structural-raster-graph` e `structural-vector-graph` → `structural_symbols.py`; `document-local-legend` → `legend_symbols.py` (fica em `metodos_excluidos` nas comparações, mas tem dono). Dependências compartilhadas (não donas): `pymupdf_support.py` (transformadores, estais, pacotes, legado), `pymupdf_symbols.py` (transformadores, estais), `raster_symbols.py` (legenda). Novo método no runner exige entrada no mapa (o teste falha).
  - API: `gerar_backlog(rodada_dir, onda)` → {`onda`, `arquivos`, `backlog`}; `agregar(onda, entradas)` (puro); `carregar_entrada(rodada_dir, pdf_id)` → `EntradaPdf`; `validar_comparacao`; `donos(method_id, familia)`; `dependencias(arquivos)`; `formar_pistas(itens)`; `arquivos_compartilhados(pistas)`; `metodos_sem_dono(ids)`; `renderizar_markdown(backlog)`; constantes `ESQUEMA_BACKLOG`, `DONOS`, `MAX_EXEMPLOS`, `REGRA_PARALELISMO`, `LIMITACOES`; exceção `BacklogRecusadoError`. CLI: `python -m scripts.curation_backlog --rodada DIR --onda K` imprime JSON canônico {`onda`, `arquivos`, `grupos`, `pistas`, `pistas_paralelas`, `falhas_execucao`, `sem_dono`, `alertas` (contagem)} e `alerta: TIPO: campos` no stderr; código 0 com backlog gravado (inclusive com alertas), 1 em recusa.
  - Formato de `ondas/K/backlog.json`: `schema_version`, `onda`, `pdfs` [{`pdf_id`, `fase`, `referencia_auditada`, `comparacao` {`arquivo`, `sha256`, `versao`} | null, `escopo`, `divergencias`, `divergencias_retidas` {método: n}, `metodos_com_falha`, `metodos_sem_registro`}], `grupos` (ordenados por `prioridade`), `falhas_execucao` [{`id`, `method_id`, `status` falha|sem_registro, `pdfs_afetados`, `pdfs`, `locais`, `divergencias_retidas`, `donos`, `pista`}], `pistas`, `paralelismo` {`regra`, `pistas_paralelas`, `arquivos_compartilhados`}, `sem_dono`, `alertas` [{`tipo` (`sem_comparacao_vigente` | `referencia_nao_auditada` | `metodo_com_falha` | `metodo_sem_registro` | `metodo_sem_dono` | `tile_sem_arquivo` | `indice_tiles_indisponivel`), …}], `totais`, `limitacoes`.
  - E08 (skill/agentes): rodar o backlog depois de `concordancia` de todos os PDFs da onda; investigadores por grupo na ordem de `prioridade` (o grupo é hipótese de causa); um corretor por pista com `paralela: true`, em `isolation: worktree`, restrito aos `arquivos` da pista; tratar `falhas_execucao` antes dos grupos do mesmo método; `sem_registro`, `sem_dono` e `referencia_nao_auditada` como alertas a resolver pelo orquestrador; após integrar uma pista, rodar de novo os testes focados das pistas listadas em `acoplamentos`; regenerar o backlog após reinferência/recomparação (os arquivos são substituídos).
  - Pendências fora do escopo: `tests/unit/test_characterization_support.py` (preexistente) continua quebrando o mypy do repositório e a coleta do pytest da suíte inteira; `test_windows_app_identity` falha nesta máquina por caixa de caminho. Os dois afetarão E10 se o usuário não os resolver.

---

## E08 — Integração com Claude Code — #concluida

**Objetivo:** criar os subagentes da curadoria, a skill de projeto que orquestra uma rodada em ondas de 3 a 5 PDFs e as permissões que deixam os CLIs rodarem sem interrupção.

**Por que agora:** todos os CLIs existem; falta a camada que o usuário invoca e que distribui o trabalho entre agentes.

**Dependências e paralelismo:** E06, E07. Não paraleliza.

**Escopo:**

- `.claude/agents/` (a criar), um arquivo Markdown com frontmatter (`name`, `description`, `tools`) por papel:
  - `curadoria-leitor-visual`: lê `render/` de um PDF com a ferramenta Read (visão geral, depois tiles `a_revisar`, duas passagens), grava a referência no formato de E04 e roda `curation_reference validar`; instruído a nunca abrir `inferencia-*`, `comparacao-*` nem `auditoria/`; ferramentas mínimas (Read, Write, Glob, Bash para o validador).
  - `curadoria-auditor-visual`: mesma leitura restrita à amostra de E06, sem acesso à referência principal.
  - `curadoria-investigador`: recebe um grupo do backlog, confere tiles e predições, confirma ou refuta a causa e propõe a correção e a fixture sintética; não edita código de produção.
  - `curadoria-corretor`: implementa a correção de uma pista nos arquivos donos, com fixture sintética autoral positiva/negativa primeiro, e roda os testes focados.
  - `curadoria-verificador`: confere uma correção contra fixture, negativos e regressões, sem editar.
- `.claude/skills/curadoria-simbologia/SKILL.md` (a criar): procedimento da rodada para a sessão orquestradora — `init` com N (3 por padrão, até 5); por onda: `curation_render` e `curation_infer` em paralelo; N leitores visuais em segundo plano; `congelar`; `curation_compare`; amostragem e auditores em paralelo; `concordancia`; `curation_backlog`; investigadores por grupo prioritário; corretores por pista em `isolation: worktree` só para pistas disjuntas; integração serial pelo orquestrador; testes focados; reinferência dos PDFs afetados; fechamento. No fim da rodada: gates completos, reinferência paralela do corpus, matriz (`benchmark_packages_e07`, `coverage_matrix_e16`, `curation_coverage_e16 compare`) partindo de `docs/data/matriz-simbologia-curadoria-atual.csv` ou, se ela não existir, de `docs/data/matriz-simbologia-e16.csv`; publicação da nova matriz e resumo em `docs/data/matriz-simbologia-curadoria-atual*.{csv,json}` só com os gates aprovados; relatório final da rodada (tempos por fase, concordância, métricas, correções, pendências, delta) em `tmp/curadoria-simbologia/RODADA/relatorio.md`, nunca em arquivos versionados. Retomada após compactação lendo `rodada.json`/`status`. Lembra que subagentes não disparam subagentes, descreve o modo de reserva (subagente `general-purpose` cujo prompt é o corpo do arquivo do agente, quando o agente não estiver registrado na sessão) e que nada é commitado. A skill e os agentes não citam este roadmap, IDs de etapa nem resultados de rodadas.
- `.claude/settings.json` (a criar): permissões `allow` para `.venv/Scripts/python.exe -m scripts.curation_*`, `-m scripts.benchmark_*`, `-m scripts.coverage_matrix_e16`, `-m scripts.curation_coverage_e16`, `-m pytest`, `-m ruff`, `-m mypy` (conferir sintaxe com a skill `update-config`, H6).
- `tests/unit/test_claude_curation_assets.py` (a criar): frontmatter válido de cada agente e da skill; todo `scripts.X` citado na skill existe como módulo; nenhum agente leitor/auditor lista ferramentas de edição de código além de Write.

**Fora de escopo:** ferramenta Workflow; executar uma rodada; alterar o contrato vivo (E09).

**Passos de implementação:**

1. Ler os handoffs de E01–E07 para obter comandos e formatos reais.
2. Escrever o teste de assets.
3. Escrever agentes, skill e permissões.

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação (`Explore`): "quais são, segundo os handoffs de E01 a E07 no roadmap, os comandos exatos, formatos de saída e fases de cada CLI da curadoria?"; "quais regras de C02/C03 de `docs/fluxo-curadoria-incremental-simbologia.md` o leitor visual e o corretor precisam carregar (cegueira, duas passagens, ambiguidade, fixture sem memorizar o PDF)?".
- Partes paralelas: nenhuma.
- Foco do verificador: leitor visual com caminho para predições ou ferramenta que permita lê-las sem restrição declarada; skill citando comando inexistente; corretores paralelos em pistas que compartilham arquivo; permissões amplas demais (por exemplo `Bash(*)`); qualquer instrução de commit; menção a este roadmap, a IDs de etapa ou a resultados de rodada; ausência do modo de reserva.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E08 — "Integração com Claude Code" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Desenho do fluxo-alvo", "Restrições e invariantes" e o "Protocolo de execução" —, a seção E08 inteira e o "Evidências e handoff" de E01 a E07. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E06 e E07 estão #concluida e que os CLIs scripts/curation_*.py existem como descritos nos handoffs; se não, ou se o código divergiu do plano, pare e relate sem implementar.

Objetivo: criar .claude/agents/ (leitor visual, auditor visual, investigador, corretor, verificador da curadoria), .claude/skills/curadoria-simbologia/SKILL.md que orquestra ondas de 3 a 5 PDFs com os CLIs reais, e .claude/settings.json com permissões restritas aos CLIs, pytest, ruff e mypy. Antes de escrever settings.json, use a skill update-config para confirmar a sintaxe. Não altere docs/fluxo-curadoria-incremental-simbologia.md nesta etapa.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E08 para #em-andamento no índice e no título;
- investigação: um subagente Explore responde às perguntas de "Estratégia de execução" de E08;
- escreva tests/unit/test_claude_curation_assets.py primeiro; depois os agentes, a skill e as permissões;
- verificação independente com o Prompt do verificador, com foco em cegueira do leitor, comandos inexistentes, pistas não disjuntas, permissões amplas e instruções de commit.

Critérios de aceite (detalhes na seção E08):
- cinco agentes e a skill com frontmatter válido; a skill cita só módulos existentes e tem modo de reserva;
- leitor e auditor proibidos de abrir inferências, comparações e a referência principal (auditor);
- nada em .claude/ cita este roadmap, IDs de etapa ou resultados de rodada; relatório da rodada só em tmp/;
- permissões sem curingas amplos; teste de assets, Ruff, formatação e mypy passam.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com todos os critérios atendidos e parecer APROVADO do verificador; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E08 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador, notas para a próxima etapa) e responda com um resumo curto de mudanças, validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] Existem `.claude/agents/curadoria-leitor-visual.md`, `curadoria-auditor-visual.md`, `curadoria-investigador.md`, `curadoria-corretor.md` e `curadoria-verificador.md`, cada um com `name`, `description` e `tools` explícitos.
- [ ] `.claude/skills/curadoria-simbologia/SKILL.md` descreve ondas com N entre 3 e 5, retomada pelo `rodada.json`, modo de reserva para agentes não registrados, corretores em worktree só para pistas disjuntas, integração serial, gates no fechamento, publicação da matriz só com gates aprovados, relatório da rodada só em `tmp/` e proibição de commit.
- [ ] `grep -rni "roadmap" .claude/` não retorna nada, e a leitura dos arquivos confirma que IDs como E04–E07/E10 só aparecem como rótulos de domínio já usados por `scripts/curation_coverage_e16.py`, nunca como etapas deste roadmap.
- [ ] `tests/unit/test_claude_curation_assets.py` passa e falharia se a skill citasse um módulo `scripts.*` inexistente (verificado alterando temporariamente uma cópia em `tmp_path`).
- [ ] `.claude/settings.json` não contém `Bash(*)` nem permissões fora dos comandos listados no escopo.
- [ ] Ruff, formatação e mypy passam.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m pytest tests/unit/test_claude_curation_assets.py -q` → todos passam.
- `.venv/Scripts/python.exe -m ruff check .`, `-m ruff format --check .`, `-m mypy` → sem erros.
- Inspeção manual: numa sessão nova, `/agents` lista os cinco agentes e `/curadoria-simbologia` aparece entre as skills.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- O Claude Code não restringe caminhos por agente, só ferramentas → a cegueira depende de instrução, de o orquestrador nunca passar caminhos de inferência ao leitor e do registro de exposição em E04; declarar isso na skill.

**Evidências e handoff:**

- Snapshot inicial: `37f6d84db36145481d69d5770ef54ced4f929dd6` (recebido do orquestrador). Snapshot ao fim da primeira implementação: `e7a9b159f2e0b54480c691a61ed87f663e24a33b`; ao fim da correção pedida pelo verificador (antes desta atualização do handoff): `9d3da96df3621cc92c965255c64a71817455701b`; `git diff --stat` entre o inicial e este mostra só os dez arquivos abaixo.
- Arquivos alterados: `.claude/agents/curadoria-leitor-visual.md`, `curadoria-auditor-visual.md`, `curadoria-investigador.md`, `curadoria-corretor.md`, `curadoria-verificador.md` (novos), `.claude/skills/curadoria-simbologia/SKILL.md` (novo), `.claude/settings.json` (novo), `tests/unit/test_claude_curation_assets.py` (novo, 44 casos), `.gitignore` (+ `.claude/settings.local.json` e `.claude/worktrees/`), este roadmap (tag e handoff de E08). `docs/fluxo-curadoria-incremental-simbologia.md`, `scripts/`, `src/`, `tests/fixtures/e10_characterization/` e `tests/unit/test_characterization_support.py` intocados.
- Decisões:
  - Preparação: E06 e E07 `#concluida`; os sete `scripts/curation_*.py` existem e os argumentos conferem com os handoffs (lidos no `argparse` de cada um: `curation_round init|status|avancar`, `curation_render`/`curation_infer` `--onda|--pdf`, `curation_reference validar|congelar|revisar` com `--exposicao sim|nao` obrigatório, `curation_compare --onda/--pdf (append)/--inferencia/--referencia`, `curation_audit amostrar|concordancia` com `--ampliar`, `curation_backlog --onda`). Investigação feita diretamente (adendo): handoffs de E01–E07, "Contrato e limites" e as seções de leitura/comparação/fechamento de `docs/fluxo-curadoria-incremental-simbologia.md` (cegueira, duas passagens, ambiguidade como alternativas, negativos, fixture autoral sem memorizar o PDF, versão do extrator, comandos da matriz) e o esquema de referência.
  - Sintaxe de permissões conferida com a skill `update-config`: `Bash(prefixo *)` com curinga só no fim. `settings.json` tem só `permissions.allow` com 16 regras, uma por módulo explícito (`curation_round/render/infer/reference/compare/audit/backlog/coverage_e16`, `coverage_matrix_e16`, `benchmark_symbols/packages_e07/transformers_e05/guys_e06`) e `-m pytest|ruff|mypy`, todas com o prefixo `.venv/Scripts/python.exe` do Git Bash; nenhum `scripts.curation_*` genérico nem `Bash(*)`. Sem regras `PowerShell(...)` (sintaxe não confirmada): a skill manda rodar os CLIs pela ferramenta Bash com caminhos literais (sem variáveis de shell, para casar com as regras). `audit_symbol_packages`, `git status`/`git diff` e `IniciarTestes.bat` ficam fora da lista (pedem aprovação), como o escopo exige.
  - **Fechamento terminal adiado:** `fechado` é fase terminal e `curation_infer` recusa PDF terminal, o que impediria a reinferência de regressão do fechamento e a reabertura de PDF de onda anterior afetado por pista posterior. A skill só move PDFs para `fechado` no fechamento da rodada, depois da reinferência de todo o corpus; durante as ondas, "onda fechada" = comparação vigente posterior à última integração + `auditado`. Só `encerrar_com_pendencia` da auditoria leva a `encerrado_com_pendencias` na hora (nota do handoff de E06).
  - Cegueira (notas de E04/E06): leitor lê `render/` (PNGs e `indice-tiles.json`) e grava em `pdfs/ID/leitura/referencia.json`; auditor lê **só** os PNGs de uma ficha montada pela orquestradora a partir da amostra e do índice (id, arquivo, página, camada, bbox, largura/altura, sem `estado`/`ocupacao`/estratos), grava em `pdfs/ID/leitura-auditoria/amostra-vNNN.json` e é proibido de abrir `auditoria/`, `referencia/`, `leitura/`, `indice-tiles.json`, `comparacao-*`, `concordancia-*`, `inferencia-*`, `checkpoint.json`, `ondas/`. Ambos com `tools: Read, Write, Glob, Bash` e Bash só para `curation_reference validar`. A skill declara que a cegueira é por instrução e que `revisar` exige `--exposicao sim` de quem viu predições/comparações/auditorias (na dúvida, `sim`).
  - Pistas (notas de E05/E07): `falhas_execucao` antes dos grupos do mesmo método e tratadas como falha; `sem_registro`/`sem_dono`/`referencia_nao_auditada` como alertas da orquestradora; **corretores em série, na árvore principal, uma pista de cada vez** (correção após o primeiro parecer REPROVADO): worktree de subagente parte de um commit, traz só arquivos rastreados (sem os `scripts/curation_*` não rastreados, sem as mudanças locais e sem a `.venv`, ignorada) e a instalação editável continua importando o `src/` principal, então testes no worktree mediriam o código errado e a conferência por `git hash-object` dava falsa segurança. A skill explica por que não usa `isolation` de worktree e o teste exige que nenhum arquivo de `.claude/` o peça. O paralelismo da onda fica em preparar, ler, auditar e investigar. Cada pista recebe arquivos de teste próprios (helpers `tests/pdf_fixtures.py`/`tests/symbol_benchmark_fixtures.py` não são editados); pista que precise editar dependência, helper ou inventário é replanejada; `acoplamentos` restringem a edição e exigem rodar de novo os testes das pistas acopladas; PDFs dessas pistas entram na reinferência. Integração por pista: a orquestradora registra `git status --short`, copia os arquivos permitidos para `RODADA/ondas/K/pistas/pista-NN/antes/` (base de reversão), dispara o corretor, confere o diff contra os arquivos permitidos, roda testes focados, Ruff/formatação/mypy e um verificador novo; REPROVADO → volta ao corretor ou restaura os arquivos.
  - Modo de reserva: `general-purpose` com o corpo inteiro do arquivo do agente + bloco da tarefa + "use apenas as ferramentas: LISTA" do `tools`. A frase sobre subagentes virou política da skill ("a skill distribui todo o trabalho a partir da sessão principal"), sem afirmar limitação técnica.
  - O teste de assets confere de forma determinística: frontmatter plano (recusa valor que quebraria o YAML), `name` = nome do arquivo, `tools` conhecidas e sem `Agent`; leitor/auditor ⊆ {Read, Write, Glob, Bash}; seção "Proibido" com os caminhos de predição/resultado; investigador/verificador sem edição; corretor com edição e fixture positiva/negativa; skill com os termos obrigatórios e os cinco agentes; **todo `scripts.X` citado em `.claude/` existe e, em linhas `python.exe -m scripts.X`, o subcomando existe e cada `--opção` pertence ao parser principal ou ao do subcomando citado**, lidos do `argparse` real (`_parser()` do módulo ou o parser que `main()` monta, capturado com `mock.patch.object(ArgumentParser, "parse_args")` antes de qualquer trabalho; 28 comandos da skill conferidos); nada em `.claude/` com "roadmap", `E01`–`E11`, `git commit|push`, `--no-verify`, `isolation: "worktree"`, `hash-object` ou caminho `C:\Users`; conjunto exato de arquivos versionáveis em `.claude/`, **ignorando o estado local do Claude Code** (`settings.local.json` e `worktrees/`, ambos no `.gitignore`, com teste em `tmp_path` e teste do `.gitignore`); permissões só `allow`, uma por regra prevista, sem repetição e cobrindo todos os `curation_*` e os gates.
- Validações executadas:
  - Teste escrito antes dos assets: `.venv/Scripts/python.exe -m pytest tests/unit/test_claude_curation_assets.py -q` → `32 failed, 1 passed` sem `.claude/`; depois → `39 passed`; após a correção do parecer → `44 passed`.
  - Cenário do verificador reproduzido: com `.claude/settings.local.json` e `.claude/worktrees/agente-x/README.md` (cópia do `README.md`, com IDs de etapa) criados temporariamente → `44 passed`; `git status` mostra os dois como ignorados; removidos depois.
  - Mutações após a correção (restauradas e conferidas com `diff -r`): `--ampliar` (opção de `amostrar`) num comando `concordancia` → 7 falhas (antes passaria, pois a opção existe no arquivo); `isolation: "worktree"` de volta na skill → 1; auditor com `Edit` → 1. O teste em cópia agora inclui `concordancia --ampliar` e `coverage_matrix_e16 --matrix`.
  - Mutações nos assets reais (restaurados e conferidos com `diff -r`): leitor com `Edit` → 1 falha; leitor sem `comparacao-` em "Proibido" → 1; `Bash(*)` em `settings.json` → 2; opção inexistente `--todas` no backlog → 5; "Modo de reserva" removido → 1; módulo `scripts.curation_amostra` → 5. O teste parametrizado `test_verificacao_de_comandos_detecta_erro_numa_copia` faz o mesmo numa cópia em `tmp_path` (módulo inexistente em comando e em prosa, subcomando e opção inexistentes).
  - `grep -rni "roadmap" .claude/` → nada; `grep -rnE "\bE(0[0-9]|1[0-9])\b" .claude/` → nada.
  - `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`; `-m ruff format --check .` → `463 files already formatted`.
  - `.venv/Scripts/python.exe -m mypy` → 2 erros, ambos em `tests/unit/test_characterization_support.py` (arquivo não rastreado preexistente do usuário, presente no snapshot inicial: importa `tests.characterization`, inexistente, e um `no-any-return`; não alterado); `-m mypy --exclude 'test_characterization_support\.py$'` → `Success: no issues found in 413 source files`.
  - Suíte inteira sem o arquivo preexistente: `pytest --ignore=tests/unit/test_characterization_support.py --deselect tests/unit/test_windows_app_identity.py::test_window_identity_sets_taskbar_relaunch_icon_and_clears_properties` → `2442 passed, 1 deselected` (o desmarcado é a falha ambiental de caixa de caminho já registrada), na primeira implementação. Após a correção (só testes de assets, `.claude/` e `.gitignore` mudaram): `pytest tests/unit/test_project_scripts.py tests/unit/test_claude_curation_assets.py tests/unit/test_curation_round.py tests/unit/test_curation_backlog.py -q` → `142 passed`; Ruff `All checks passed!`, formatação `463 files already formatted`, mypy com o arquivo preexistente excluído `Success: no issues found in 413 source files` (sem exclusão, os mesmos 2 erros preexistentes).
  - Inspeção manual `/agents` e `/curadoria-simbologia` numa sessão nova: **não executada** (subagente não abre sessão nova); fica para o verificador/orquestrador ou para E11, que já prevê o modo de reserva.
- Parecer do verificador: APROVADO na segunda verificação (verificador independente do orquestrador; snapshot de verificação 1c81ac95894d8fa382028a03efa6483d03839f30). A primeira verificação REPROVOU por (ALTO) pistas de correção em worktree inexequíveis — a base do worktree não tem os CLIs não rastreados, as mudanças locais nem .venv, e a instalação editável aponta para o src principal — e (MÉDIO) teste de assets quebrando com .claude/settings.local.json ou .claude/worktrees/; o implementador corrigiu ambos e os dois baixos (opções conferidas por subcomando via argparse; frase sobre subagentes como política). 6/6 critérios aprovados: 44 testes de assets, Ruff/formatação limpos, mypy limpo exceto o arquivo preexistente do usuário, permissões só com 16 regras explícitas, nada de roadmap/IDs de etapa em .claude/. Decisão do orquestrador sobre a divergência apontada (worktree no Desenho/E08/E11 × correção em série na skill): aceita a correção em série na árvore principal como restrição mais segura dentro de 'worktree só para pistas disjuntas' (nenhuma pista usa worktree), por inviabilidade técnica comprovada; E09 deve descrever o fluxo com correções em série e E11 segue a skill. Não executado: conferência manual de /agents e /curadoria-simbologia numa sessão nova (impossível por subagente; layout e frontmatter conferidos estaticamente; a skill tem modo de reserva). Baixos: comandos em prosa não têm opções conferidas; proteção contra worktree só casa o texto literal com aspas; cegueira de leitor/auditor via Bash depende de instrução.
- Notas para a próxima etapa:
  - E09: o contrato vivo deve descrever o mesmo fluxo da skill — fases por onda, fechamento terminal adiado para depois da reinferência de regressão, ficha da amostra sem estado para o auditor, `leitura/` e `leitura-auditoria/`, exposição declarada, correções em série na árvore principal (sem worktree) com integração e verificação por pista, matriz a partir de `matriz-simbologia-curadoria-atual.csv` ou `matriz-simbologia-e16.csv`, publicação só com gates aprovados e relatório só em `tmp/`. A seção "Estado do fluxo" do contrato atual manda registrar a rodada no documento; a skill não faz isso (sem histórico em versionados), então E09 deve remover essa instrução.
  - E11: a skill pode não estar registrada na sessão que a cria; ler `.claude/skills/curadoria-simbologia/SKILL.md` diretamente e usar o modo de reserva se `subagent_type` `curadoria-*` for recusado. Comandos fora da lista de permissões (`git status`/`git diff`, cópias de arquivos, `audit_symbol_packages`, `cmd.exe //c IniciarTestes.bat`) pedirão aprovação. As correções rodam em série na árvore principal; não usar worktree de subagente enquanto o estado relevante (CLIs, mudanças locais, `.venv`) não existir nele.
  - Pendências preexistentes fora do escopo: `tests/unit/test_characterization_support.py` (mypy e coleta do pytest), `scripts/complexity_gate.py src` (funções antigas E/F em `src/`) e `test_windows_app_identity` (caixa de caminho) afetarão E10 se o usuário não os resolver.

---

## E09 — Contrato vivo do fluxo por ondas — #concluida

**Objetivo:** reescrever `docs/fluxo-curadoria-incremental-simbologia.md` para o fluxo por ondas com Claude Code, preservando os invariantes e sem histórico de execução, e atualizar as referências em `examples/README.md`, `CLAUDE.md` e `README.md`.

**Por que agora:** o documento vivo só pode descrever o que existe; com CLIs, agentes e skill prontos, ele deixa de descrever o fluxo sequencial.

**Dependências e paralelismo:** E08. Não paraleliza.

**Escopo:**

- `docs/fluxo-curadoria-incremental-simbologia.md`: substituir "Execução sequencial e equipe reutilizada", C01–C04 e o "Prompt one-shot" pelas fases do "Desenho do fluxo-alvo" com os comandos reais; manter "Contrato e limites" (sem a dependência de GPT) e os critérios de aceite da rodada; reescrever "Ponto de partida e critério de melhoria" para dizer que cada rodada parte da matriz de curadoria atual (ou da E16 histórica, se ainda não houver) e lê os números dela, em vez de fixar contagens no texto; remover menções a GPT, Codex e o link da OpenAI; **remover a seção "Estado do fluxo"** e qualquer frase que registre edições, consolidações, rodadas executadas ou resultados — o documento descreve só o procedimento vigente, e o histórico fica no Git.
- Uma seção curta "Como executar": invocar `/curadoria-simbologia` e um prompt de reserva para sessões sem a skill.
- `examples/README.md`: atualizar o parágrafo e os comandos de curadoria.
- `CLAUDE.md`: ajustar a seção "Curadoria de simbologia" para apontar a skill e os CLIs.
- `README.md`: conferir o link e o texto da curadoria contínua.

**Fora de escopo:** alterar dados em `docs/data/`; mudar ADRs.

**Passos de implementação:**

1. Listar os invariantes do documento atual e conferir que cada um continua no novo texto.
2. Reescrever e atualizar referências.
3. Conferir links Markdown e menções proibidas.

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação: nenhuma (a sessão principal edita o documento e deve lê-lo inteiro).
- Partes paralelas: nenhuma.
- Foco do verificador: invariante herdado removido ou enfraquecido; comando citado que não existe; menção residual a GPT/Codex/OpenAI; link quebrado; ganho de desempenho declarado sem medição; texto que dê a entender que uma rodada ou etapa já foi executada; menção a este roadmap.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E09 — "Contrato vivo do fluxo por ondas" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Desenho do fluxo-alvo", "Restrições e invariantes" e o "Protocolo de execução" —, a seção E09 inteira, o "Evidências e handoff" de E08 e o documento docs/fluxo-curadoria-incremental-simbologia.md inteiro. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E08 está #concluida e que a skill e os agentes existem; se não, ou se o código divergiu do plano, pare e relate sem implementar.

Objetivo: reescrever docs/fluxo-curadoria-incremental-simbologia.md para o fluxo por ondas com Claude Code (comandos reais, skill /curadoria-simbologia, prompt de reserva), preservando todos os invariantes, sem GPT/Codex/OpenAI e sem histórico de execução (remova "Estado do fluxo" e contagens fixas de cobertura); atualizar examples/README.md, CLAUDE.md e README.md. Nenhum desses arquivos pode citar este roadmap. Não altere docs/data/ nem ADRs.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E09 para #em-andamento no índice e no título;
- sem investigação delegada: leia o documento inteiro você mesmo;
- monte antes uma lista dos invariantes do texto atual e confira cada um no texto novo;
- verificação independente com o Prompt do verificador, com foco em invariantes, comandos inexistentes, menções residuais e links.

Critérios de aceite (detalhes na seção E09):
- nenhuma ocorrência de GPT, Codex ou openai.com no documento; sem "Estado do fluxo" nem registro de rodadas;
- todo comando citado corresponde a um módulo existente;
- invariantes preservados (lista no handoff); links Markdown sem quebras;
- Ruff, formatação e o teste de assets continuam passando.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com todos os critérios atendidos e parecer APROVADO do verificador; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E09 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador, notas para a próxima etapa) e responda com um resumo curto de mudanças, validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] `grep -niE "gpt|codex|openai" docs/fluxo-curadoria-incremental-simbologia.md` não retorna nada.
- [ ] Todo `scripts.X` citado no documento existe em `scripts/X.py`.
- [ ] O handoff lista os invariantes do texto anterior e onde cada um está no texto novo.
- [ ] Links Markdown relativos em `README.md`, `examples/README.md`, `CLAUDE.md` e `docs/` apontam para arquivos existentes.
- [ ] `examples/README.md` e `CLAUDE.md` citam `/curadoria-simbologia`.
- [ ] O documento não tem seção "Estado do fluxo", não fixa contagens de cobertura no texto e não contém frases sobre rodadas, edições ou consolidações já feitas; `grep -rn "roadmap-curadoria-simbologia-paralela"` fora do próprio roadmap não retorna nada.

**Validação obrigatória:**

- `grep -niE "gpt|codex|openai" docs/fluxo-curadoria-incremental-simbologia.md` → sem saída.
- `.venv/Scripts/python.exe -m pytest tests/unit/test_claude_curation_assets.py -q` → passa.
- `.venv/Scripts/python.exe -m ruff check .` e `-m ruff format --check .` → sem erros.
- Inspeção manual: checagem de links relativos (script ad hoc ou leitura) registrada no handoff.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Encolher demais o contrato e perder regra importante → a lista de invariantes no handoff é o controle.

**Evidências e handoff:**

- Snapshot inicial: `27a89b84643e088fe27456e96951a3c579d2a17d` (recebido do orquestrador). Snapshot ao fim da primeira implementação: `68b50c549b280a65736ab3050385fb659f2de90f`; ao fim da correção pedida pelo verificador (antes desta atualização do handoff): `1c03b3df45f6264501ca52cde57c1adbf85d0c6f`; `git diff --stat` entre o inicial e este mostra só os oito arquivos abaixo.
- Arquivos alterados: `docs/fluxo-curadoria-incremental-simbologia.md` (reescrito, 672 linhas), `examples/README.md` (parágrafo da curadoria: skill `/curadoria-simbologia` e link para o prompt de reserva no lugar da âncora do antigo prompt one-shot; nota sobre `curation_infer`), `CLAUDE.md` (seção "Curadoria de simbologia": skill, agentes, os sete CLIs e invariantes), `README.md` (item da curadoria na lista de documentos cita as ondas e a skill), este roadmap (tag e handoff de E09) e, na correção, `.claude/skills/curadoria-simbologia/SKILL.md`, `.claude/settings.json` e `tests/unit/test_claude_curation_assets.py`. Agentes, `scripts/`, `src/`, `docs/data/`, `docs/adr/`, `tests/fixtures/e10_characterization/` e `tests/unit/test_characterization_support.py` intocados.
- **Ampliação de escopo (decisão do orquestrador na correção):** para manter um único procedimento executável, a skill passou a executar o que o contrato exige; isso autorizou editar `.claude/skills/curadoria-simbologia/SKILL.md`, `.claude/settings.json` e `tests/unit/test_claude_curation_assets.py`, além dos arquivos de escopo de E09.
- Decisões:
  - Preparação: E08 `#concluida`; os cinco agentes e a skill existem e conferem com o handoff de E08 (correções em série na árvore principal, sem worktree; modo de reserva; fechamento terminal adiado). Sem investigação delegada: li o contrato antigo inteiro, a skill, os cinco agentes e os handoffs de E01–E08.
  - Estrutura nova do contrato: introdução (sem GPT), "Ponto de partida e critério de melhoria" (lê os números da matriz de partida, sem contagens fixas), "Contrato e limites", "Desenho do fluxo" (leitura × correção, oito fases, por que não há worktree, layout da rodada, fases do checkpoint), "Como executar" (`/curadoria-simbologia`, permissões, prompt de reserva, modo sem subagentes, convenção de comandos), "Preparação da rodada", "Ciclo de cada onda" (1–8), "Fechamento da rodada" (1–8) e "Aceite da rodada". Removidos: "Execução sequencial e equipe reutilizada", C01–C04, "Prompt one-shot", "Estado do fluxo", resultados das reservas (1 TP/0 FP/3 FN; 16,7%), contagens 427/33/21/344/93/297, a nota da OpenAI e todas as frases de edição/consolidação.
  - Fluxo descrito como a skill o implementa (decisão do orquestrador registrada em E08): correções em série, na árvore principal, por pista disjunta, com base de reversão, conferência do diff, testes focados e verificador por pista; "Desenho do fluxo" explica por que não há worktree. Limitações dos verificadores registradas no contrato: escopo regional pelo centro da bbox com efeito de borda (§3 Medir); métodos com falha ou sem registro contam como falha, não zero ("Contrato e limites" e §3); nova versão da referência invalida `comparado` e `auditado` (fases do checkpoint e §6).
  - Mudanças deliberadas de política, todas previstas no "Desenho do fluxo-alvo": (a) "exatamente um PDF ativo por vez" virou ondas de 3 a 5 PDFs; (b) "reler todos os inalterados salvo autorização" virou reuso por SHA-256 conferido como padrão, com auditoria amostral também sobre as reutilizadas e `--sem-reuso` para releitura total (H1); (c) "salvar a referência antes de iniciar a inferência" virou "referência congelada antes de qualquer comparação, leitor sem acesso às inferências", com `inferencias_presentes` registrado no congelamento; (d) "cobertura visual de todas as páginas" virou referência regional com tiles revisados e regiões ilegíveis declarados e sem recall global fora do escopo completo (H2); (e) cópia do PDF para `input/` substituída por `curation_infer` (`benchmark_symbols examples --pdf`); (f) equipe A/B/C substituída pelos cinco agentes; (g) PowerShell substituído pelos comandos literais do Git Bash da skill, com a nota para o prompt do PowerShell.
  - Rótulos de domínio mantidos só onde nomeiam arquivos/CLIs (matriz E16, `*_e05/_e06/_e07/_e14/_e16`); "famílias E01", "pacotes E07", "relatórios E05/E06" e "E14" do texto antigo viraram descrições. Os gates V-N/V-P/V-Q/V-G mantêm os nomes (rótulos do contrato, não etapas).
  - **Correção após o primeiro parecer REPROVADO** (P1–P6):
    - P1 (paridade contrato↔skill): a skill ganhou (a) o checkpoint sintético inicial em `RODADA/inicial/` (baseline, união e `reconcile_symbol_benchmark`) na preparação; (b) no fechamento, a união/composição sintética com `reconcile_symbol_benchmark`, o confronto com `inicial/` e os itens V-N (validação independente dos esquemas, `audit_symbol_packages --source-pdf` se a F02 existir, `git diff --check`, hashes/totalizadores); (c) `demanda.json` + `curation_coverage_e16 plan --demand` no início da fase Agregar e a ordem de investigação demanda × lacunas; (d) no fechamento, `benchmark_symbols examples --root examples` + `benchmark_review_e14` sobre a inferência do corpus inteiro (o CLI exige que o manifesto cubra a descoberta recursiva de `--root`, `scripts/benchmark_review_e14.py:71-74`) com inspeção de UI/exportações ou gate pendente; (e) no relatório, TP/FP/FN sintéticos inicial × final e "Sem ganho validado, escreva isso expressamente". Opções conferidas por `--help` (`reconcile_symbol_benchmark`, `benchmark_review_e14`, `curation_infer`) e pelo verificador de argparse do teste. `.claude/settings.json` ganhou duas regras explícitas (`scripts.benchmark_review_e14 *` e `scripts.reconcile_symbol_benchmark *`, 18 no total, sem curinga amplo); o padrão `REGRA_PERMITIDA` do teste passou a aceitar `reconcile_symbol_benchmark`. A frase de "Como executar" sobre aprovação agora lista as regras liberadas e o que pede aprovação (`audit_symbol_packages`, `IniciarTestes.bat`, `git status`/`git diff`, cópias de arquivo, validação independente dos esquemas). A paridade é verificada por teste: o conjunto de comandos `python.exe -m scripts.X` (módulo + argumentos normalizados) do contrato é **igual** ao da skill (37 comandos de cada lado).
    - P2 (pipeline obrigatório): contrato e skill exigem `--pipeline` em todas as inferências (onda, reinferência e regressão); runtime padrão `tmp/benchmark-runtime` inspecionado por `benchmark_network_pdf`; sem OCR português (o CLI falha com "OCR português obrigatório"), a rodada inteira passa a `--pipeline --native-only`, refazendo as inferências já feitas, com OCR como pendência e `--native-only` sem aprovar OCR. Lacunas de medição declaradas no contrato como pendência (não prometidas): `curation_infer` não aciona `--complementary-ocr` nem `--legend-ocr`; `curation_compare` só mede símbolos (textos, atributos, estados, quantidades e relações sem métrica automática); o investigador recebe `pipeline.json` quando o grupo envolve esses itens.
    - P3 (limite de ciclos): o limite de dois ciclos de correção por onda ficou e está no contrato (§8); cada divergência acionável que sobrar vai para "Pendências acionáveis" do relatório com id `grp-...` (estável entre ondas e rodadas), PDFs, pista, arquivos donos e impedimento comprovado ou dono e próximo dado; a onda seguinte e a próxima rodada (preparação) retomam esses grupos primeiro.
    - P4: subagentes herdam o modelo da sessão, sem troca por economia; identificador registrado ou `indisponivel`, sem inventar ("Contrato e limites"; na skill, em "Papéis e modo de reserva").
    - P5: exposição via duplicata do mesmo PDF (mesmo SHA-256) exige `--exposicao sim` (contrato §6 e skill fase 6).
    - P6: a demanda passou para o início de §5 Agregar, antes do backlog, como na skill; o parágrafo duplicado de §8 saiu.
  - Testes novos/alterados em `tests/unit/test_claude_curation_assets.py`: termos obrigatórios da skill (inicial, `--demand`, "Pendências acionáveis", "no máximo dois ciclos", confronto sintético inicial, "Sem ganho validado", UI/exportações, herança do modelo, duplicata); a skill invoca todos os CLIs do fechamento (`CLIS_DO_FECHAMENTO`); `test_contrato_e_skill_executam_os_mesmos_clis` (paridade linha a linha e comandos do contrato válidos no argparse); `test_toda_inferencia_da_rodada_roda_o_pipeline` (skill e contrato); `test_benchmark_review_roda_sobre_a_inferencia_do_corpus_inteiro`; as permissões precisam cobrir `benchmark_symbols`, `benchmark_review_e14` e `reconcile_symbol_benchmark`.
- Invariantes do texto anterior e onde estão no novo (seções do documento novo):
  1. Rodada não treina o assistente; conhecimento duradouro só em algoritmos, pacotes, inventário e fixtures/testes; chat e PDFs ignorados não são base persistente → introdução.
  2. Referência congelada antes de comparar; leitor sem predições, contagens esperadas nem fila de lacunas; recebe imagens, inventário e esquema → introdução, "Contrato e limites", §2 Ler, "Preparação" (fila nunca chega ao leitor).
  3. Referência de IA não é gabarito, confirmação humana, norma nem avaliação de campo; achado sustentado orienta correção sem esperar confirmação humana; provisórios separados; não afirmar verdade de campo nem censo perfeito → introdução, "Contrato e limites", §2.
  4. Rodada parte das lacunas da matriz; melhorias de leitura/OCR/relações/contagem/FP contam sem ganho de IDs; sem garantia de ganho; resultado = ganho validado, regressão ou pendência com denominadores → introdução.
  5. Inventário + esquema como denominador; `pending` não é reconhecimento; números são o começo, não metas; inventário que cresce recalcula e justifica cada ID → "Ponto de partida".
  6. `SRC-LOCAL.url` é metadado e o inventário fica byte a byte igual → "Ponto de partida".
  7. Reservas abertas consumidas, sem ajuste nem teste cego; rodada demonstra delta, TP/FP/FN, exclusivos, ambiguidades, custos, regressões, sem homologação → "Ponto de partida", "Contrato e limites", §7 (regras de correção).
  8. Novo aceite integrado com nova reserva lacrada e medida uma vez; metas ≥95% por família avaliável, zero FP em negativos críticos, zero fusão entre páginas, zero promoção com conflito, composição com exclusivos e duas famílias, ≥99% para promoção automática, subconjunto vazio não vale; V-P/V-Q/V-G, benchmark reservado, UI/exportações; pendência sem declarar aceite → "Ponto de partida".
  9. ADR 0005: PDFs reais e relatórios só em `tmp/curadoria-simbologia/`; não enviar a serviços sem autorização; não copiar PDF/recorte para fixtures; gate portátil sintético → "Contrato e limites" (1º item), fechamento item 7.
  10. Pixels apresentados ao modelo; ler binário ou extrair texto não é revisão → "Contrato e limites" (1º item), §2.
  11. Adicionar PDF não ensina o detector; falta de confirmação humana não bloqueia os demais casos → "Contrato e limites".
  12. Ambiguidade = uma observação com alternativas; ID exato só com evidência distintiva; alternativas só reconhecem o grupo com pacote verificado; desconhecido não conta → "Contrato e limites", §2, §3 (ID ambíguo nunca é TP exato).
  13. Legenda local limita o significado; informativos, norte e §33 continuam informativos; PDF não cria norma → "Contrato e limites", §2.
  14. Versão congelada de pacotes/inferência; referência/ROI fora do detector; silêncio de outro método não veta exclusivo; concordância não é probabilidade → "Contrato e limites", §7 (regras).
  15. Limites da visão (texto pequeno, traços, contagem, localização); resolução legível, tiles, não confiar só na miniatura/OCR; sem precisão ou probabilidade inventadas; coordenadas são localizadores → "Contrato e limites", §2.
  16. PDF visto é desenvolvimento; reserva futura com seleção, esquema e congelamento próprios → "Contrato e limites".
  17. Matriz E16 é ponto de partida histórico; curadoria atual só substituída após gates; históricos preservados; delta de IDs não comprova recall real, união nem aceite → "Contrato e limites", "Ponto de partida", fechamento itens 6-7.
  18. Todos os PDFs e páginas no manifesto; descoberta recursiva com `.PDF`; ordem por caminho relativo sem caixa; ilegíveis registrados; ausente não presumido validado → "Preparação" (`init`), "Aceite".
  19. Duplicatas por hash mantêm todos os caminhos e ficam nos denominadores → "Preparação", "Aceite".
  20. Manifesto/checkpoints com fases, versões, hashes, comandos e pendências; diretório por PDF; todas as versões preservadas, sem sobrescrever evidência → "Desenho do fluxo" (layout e versões).
  21. Um dono por arquivo; inventário e registro compartilhado alterados em série; inferências que disputam recursos limitadas → §7 (pistas em série, inventário em pista própria), §1 (`--jobs`).
  22. Subagentes herdam o modelo ativo, sem troca por outro modelo por economia; identificador registrado em `revisor.modelo` ou declarado `indisponivel`, sem inventar nome/versão; sem subagentes, funções em sequência sem simular revisão independente → "Contrato e limites" (item do modelo), §2 (revisor), "Como executar" (modo sem subagentes).
  23. Exposição declarada, inclusive via duplicata do mesmo PDF, e revisão exposta não é cega; subagentes do mesmo modelo não são validação estatística nem confirmação humana → §6 (`revisar --exposicao`), §4 (concordância).
  24. Fechar PDF exige referência congelada, inferência antes/depois, investigação, correções testadas e inspeção das saídas; divergência acionável corrigida ou com impedimento, dono e próximo dado (no máximo dois ciclos por onda; o restante vai para "Pendências acionáveis" e é retomado na onda e na rodada seguintes); ilegível/sem fonte encerra com pendência; não encerrar por falta de ID exato, lote ou amostra pequena; não exigir concordância perfeita → §8, "Preparação" (pendências da rodada anterior), §6 (ordem), fechamento itens 4-5, "Aceite".
  25. Código congelado, gates, reinferência de regressão de todo o corpus; regressão reabre; retomada pelo checkpoint sem segunda fila → fechamento itens 1-3, "Como executar" (retomada pelo `rodada.json`; o prompt de reserva proíbe recriar a rodada).
  26. Preservar alterações preexistentes; verificar interpretador/CLIs; `.venv` indisponível é impedimento; conferir argumentos não aprova execução → "Preparação".
  27. Matriz anterior copiada para `matriz-antes.csv` com SHA-256; plano de lacunas com dono e denominador; fila não é rótulo → "Preparação".
  28. Checkpoint sintético inicial isolados + união/composição; fixtures novas separadas; mudança de denominador não é ganho → "Preparação", fechamento item 2 (confronto com `inicial/`), item 8 (relatório inicial × final).
  29. Duas passagens, visão geral + tiles com sobreposição, negativos, regiões ilegíveis com denominador, lista esparsa não é censo → §2.
  30. Campos mínimos da observação (identidade, página/camada/região, papel, classe/família, ID ou alternativas, texto original × interpretação, quantidades/relações, fonte com localizador, estado com motivo, origem `revisao_ia`, confirmação humana separada, sem probabilidade) → §2 (formato da referência).
  31. Uma ocorrência física = uma identidade; sem duplicar base/anotação; sem fundir por semelhança; legenda/norte fora da contagem operacional → §2.
  32. `demanda.json` só com IDs observados/confundidos, `plan --demand`, IDs sobem sem status novo, desconhecidos fora → §5 (início); prioridade do cruzamento demanda × lacunas → §6 (ordem de investigação).
  33. Pipeline de leitura/interpretação em **todo** PDF, antes e depois: `--pipeline` obrigatório em todas as inferências da rodada (onda, reinferência, regressão), com o runtime padrão `tmp/benchmark-runtime` inspecionado pelo CLI; OCR indisponível leva a rodada inteira a `--pipeline --native-only` e fica como pendência; native-only não aprova OCR; não baixar modelos; mesma configuração antes/depois; instrumentar em vez de afirmar. OCR complementar e comparação de textos/atributos/relações/quantidades não têm suporte nos CLIs atuais e estão declarados como lacunas de medição registradas como pendência, com o investigador consultando o `pipeline.json` → §1 Preparar, §6, §8, fechamento item 3 e item 8.
  34. TP_IA/FP_IA/FN_IA relativos à referência sustentada, classe × ID exato, numeradores e denominadores, ambíguo não é TP exato, provisórios à parte, não são precisão/recall de campo, a referência pode estar errada → §3, §6.
  35. Fixture sintética autoral com positivo e negativos antes do ajuste; sem memorizar nome/hash/coordenadas; regra pelo sinal do documento; módulo responsável → §7 (regras de correção).
  36. Revisão da referência com nova versão, motivo/evidência, preservando a anterior, exposição declarada, antes/depois contra a mesma versão → §6.
  37. Promoção de conhecimento com fonte, gramática e positivos/negativos; `enabled`/`pending` pelo esquema; nova família no inventário com ID estável e fonte; variantes `pending` não viram reconhecidas → §7 (regras).
  38. Falta de fonte bloqueia só o caso; ganhos de leitura/FP/duplicatas registrados à parte do delta de IDs → §7, fechamento item 8.
  39. Pacotes só resolvem suas variantes; outros métodos voltam ao dono; correção fora dos pacotes exige relatórios frescos; não usar reservas para ajustar → §7, fechamento item 6.
  40. Não modificar o reconciliador para cadastrar família nem criar regra de conformidade a partir do exemplo → §7.
  41. Gates V-N (esquemas, fontes, Draft 2020-12 independente, `--source-pdf` F02), V-Q, V-G; nomes de gate não valem sem comando/resultado/artefato; comandos novos descobertos e registrados; `git diff --check` e totalizadores → fechamento item 2.
  42. Métodos indisponíveis são falha, não zero; comparar baseline, isolados, união, composição e ablação com os mesmos denominadores, inclusive negativos críticos; interseção é controle → "Contrato e limites", §3, fechamento item 2.
  43. Persistência/revisão/exportação reais (`benchmark_review_e14`, diretório novo, recusa sobrescrever, corpus inteiro) não substituem a inspeção da UI/exportações; UI não verificada é gate pendente → fechamento item 4.
  44. Relatório final com um único checkpoint; checkpoints de antes diferentes identificados, sem somar como inferência global do código inicial; não esconder perdas no agregado → fechamento itens 1 e 3.
  45. Relatório de pacotes da própria rodada; o gerador recusa inferência incompleta/FP/FN autorais/hash divergente; evidência de transformadores/estais herdada só sem mudança, senão relatórios frescos; matriz anterior permanece se faltar evidência; plano não substitui revisão; delta não mede FP/FN → fechamento item 6.
  46. Publicação da matriz só com gates e revisão visual aprovados (gate falhando ou pendente impede), sem editar a E16 histórica → fechamento item 7. A instrução antiga de registrar a rodada em "Estado do fluxo" foi **removida** (nenhum arquivo versionado recebe histórico).
  47. Aceite: manifesto completo, referências antes das comparações, mesmo checkpoint, positivos/negativos das mudanças, fontes intactas, V-Q/V-G/contratos/jobs/histórico/exportações, delta com denominadores, TP/FP/FN sintéticos e TP_IA, sem recall global com referência não completa, sem ganho dito expressamente, pendências não são reconhecimento → fechamento item 8 e "Aceite da rodada".
  48. Nenhum commit/publicação/implantação sem autorização → "Contrato e limites" (último item).
- Validações executadas (após a correção):
  - `grep -niE "gpt|codex|openai"` no documento, `examples/README.md`, `CLAUDE.md`, `README.md` e `.claude/` → sem saída. `grep -n "Estado do fluxo"` no documento → sem saída.
  - `grep -rn "roadmap-curadoria-simbologia-paralela" --exclude-dir=.git --exclude-dir=.venv --exclude-dir=tmp .` fora do próprio roadmap → sem saída; `grep -rniE roadmap` em `.claude/`, no documento, `examples/README.md` e `CLAUDE.md` → sem saída; `grep -rnE "\bE(0[1-9]|1[01])\b"` nos mesmos → sem saída.
  - Módulos citados: todos os `scripts.X` do documento existem em `scripts/X.py` (laço `grep -oE` + `test -f`). Verificador real de argparse do teste (`problemas_de_comandos`): documento → 37 comandos, 0 problemas; skill → 37 comandos, 0 problemas; `examples/README.md` → 1 comando, 0 problemas. Comparação ad hoc das linhas de comando normalizadas contrato × skill → nenhuma só de um lado (automatizada em `test_contrato_e_skill_executam_os_mesmos_clis`). Comandos em prosa conferidos à mão: `curation_audit amostrar --rodada --pdf --ampliar`, `audit_symbol_packages --source-pdf --output`.
  - Links Markdown (script ad hoc: links relativos fora de blocos de código, arquivo e âncora no estilo do GitHub) sobre `README.md`, `examples/README.md`, `CLAUDE.md` e todos os `.md` de `docs/` → 26 arquivos, 38 links relativos, 0 quebrados. Controle: com o `examples/README.md` antigo numa cópia isolada, o script acusou a âncora `#prompt-one-shot-para-usar-após-adicionar-pdfs` e os destinos ausentes.
  - `.venv/Scripts/python.exe -m pytest tests/unit/test_claude_curation_assets.py tests/unit/test_project_scripts.py -q` → `59 passed` (o arquivo de assets sozinho: `48 passed`).
  - Mutações (restauradas e conferidas com `cmp`): `--pipeline` removido de uma inferência da skill → 2 falhas; comando do contrato divergente da skill → 1; regra `reconcile_symbol_benchmark` removida de `settings.json` → 1; `benchmark_review_e14 --root` fora de `examples` → 2; "Pendências acionáveis" removido da skill → 1.
  - `.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`; `-m ruff format --check .` → `463 files already formatted`.
  - `.venv/Scripts/python.exe -m mypy --exclude 'test_characterization_support\.py$'` → `Success: no issues found in 413 source files`; sem a exclusão, os mesmos 2 erros preexistentes em `tests/unit/test_characterization_support.py` (arquivo não rastreado do usuário, presente no snapshot inicial; não alterado nem coletado nos testes focados).
  - `git diff --check` nos arquivos rastreados alterados → limpo; sem espaços finais na skill, em `settings.json` e no documento.
- Parecer do verificador: APROVADO na segunda verificação (verificador independente do orquestrador; snapshot de verificação c8f744c42ce3760c1c3dd8321f9c1a93de89b6ee). A primeira verificação REPROVOU por (ALTO) afirmação falsa de paridade contrato↔skill — a skill não executava inicial/, união/composição com reconcile, demanda.json, benchmark_symbols examples + benchmark_review_e14 nem o confronto sintético no relatório —, (MÉDIO) pipeline opcional e (MÉDIO) limite de dois ciclos sem respaldo no contrato; o orquestrador autorizou editar SKILL.md, settings.json (+2 regras explícitas: benchmark_review_e14 e reconcile_symbol_benchmark) e o teste de assets, e o implementador corrigiu P1–P6. 6/6 critérios aprovados: sem GPT/Codex/OpenAI; 16 módulos existentes e 37 comandos sem problemas no contrato e na skill (conjuntos idênticos); 48 invariantes mapeados; 38 links sem quebra; sem Estado do fluxo, contagens fixas nem citação do roadmap; 48 testes de assets, Ruff/formatação limpos, mypy limpo exceto o arquivo preexistente do usuário. Baixos para E11: benchmark_review_e14 falha ('Projeto não possui propostas concluídas para revisão') se algum PDF do corpus não tiver proposta adotada — tratar como gate pendente; cruzamento demanda × lacunas reduz-se à demanda (plan --demand põe toda a demanda em targets; IDs repetidos são recusados); invariante 24 levemente afrouxado (impedimento OU dono+próximo dado); algumas mutações de texto não detectadas pelo teste de paridade; linhas 630/636 do contrato com mais de 100 colunas.
- Notas para a próxima etapa:
  - E10: o arquivo de assets passou de 44 para 48 casos; nada desta etapa muda código de produção. Pendências preexistentes continuam (`tests/unit/test_characterization_support.py`, `scripts/complexity_gate.py src` com funções E/F antigas e `test_windows_app_identity` por caixa de caminho).
  - E11: a rodada segue a skill, que agora executa os mesmos comandos do contrato. Toda inferência usa `--pipeline`; se o OCR português não estiver pronto em `tmp/benchmark-runtime`, a rodada inteira usa `--pipeline --native-only` e registra a pendência. O fechamento roda uma inferência extra do corpus inteiro (`benchmark_symbols examples --root examples`) para `benchmark_review_e14`, que custa tempo de máquina. `audit_symbol_packages`, `IniciarTestes.bat`, `git status`/`git diff` e cópias de arquivo continuam pedindo aprovação. A âncora `#como-executar` do contrato é o alvo do link de `examples/README.md`.

---

## E10 — Gate técnico final — #concluida

**Objetivo:** confirmar que o repositório inteiro continua verde e que o recálculo da cobertura a partir do checkpoint atual reproduz delta zero, já que este roadmap não altera detectores.

**Por que agora:** fecha a parte de engenharia antes da primeira rodada com os PDFs reais.

**Dependências e paralelismo:** E09. Não paraleliza.

**Escopo:** executar o gate completo e a cadeia de cobertura em `tmp/roadmap-e10/`; corrigir apenas falhas causadas por este roadmap.

**Fora de escopo:** correções em código não tocado por este roadmap (registrar como pendência).

**Passos de implementação:**

1. Rodar `IniciarTestes.bat` e ler `relatorio-testes.txt`.
2. Rodar a cadeia de cobertura e comparar com `docs/data/matriz-simbologia-e16.csv`.

**Estratégia de execução:** `direta` · Revisão humana: não

- Investigação: nenhuma.
- Partes paralelas: nenhuma.
- Foco do verificador: falha de gate omitida; delta diferente de zero sem explicação; cobertura abaixo de 85,01%.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E10 — "Gate técnico final" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap e o "Protocolo de execução", a seção E10 inteira e o "Evidências e handoff" de E09. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E09 está #concluida; se não, ou se o código divergiu do plano, pare e relate.

Objetivo: rodar o gate completo (IniciarTestes.bat) e a cadeia benchmark_packages_e07 → coverage_matrix_e16 → curation_coverage_e16 compare contra docs/data/matriz-simbologia-e16.csv, esperando delta zero. Corrija só falhas causadas por arquivos deste roadmap; o resto vira pendência registrada.

Siga o Protocolo de execução com a estratégia direta:
- tire o snapshot inicial e troque a tag de E10 para #em-andamento no índice e no título;
- rode os comandos da "Validação obrigatória" de E10 e guarde as saídas relevantes;
- sem verificação independente na execução manual (no modo automático o orquestrador a fará).

Critérios de aceite (detalhes na seção E10):
- IniciarTestes.bat termina com RESULTADO FINAL: APROVADO;
- delta-e16.json mostra zero IDs ganhos e zero perdidos.

Não declare sucesso com validação falhando ou não executada. Marque #concluida só com os critérios atendidos; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios".

No fim, preencha "Evidências e handoff" de E10 (snapshot, arquivos alterados, comandos e resultados, notas para a próxima etapa) e responda com um resumo curto de validações e pendências. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [x] `relatorio-testes.txt` termina com `RESULTADO FINAL: APROVADO` (Ruff, formatação, mypy, gate do cliente magro, pytest com cobertura > 85,01%, complexidade).
- [x] `tmp/roadmap-e10/delta-e16.json` registra zero IDs ganhos e zero perdidos em relação a `docs/data/matriz-simbologia-e16.csv`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` (no PowerShell: `.\IniciarTestes.bat`) → `RESULTADO FINAL: APROVADO`.
- `.venv/Scripts/python.exe -m scripts.benchmark_packages_e07 --output tmp/roadmap-e10/benchmark` → código 0.
- `.venv/Scripts/python.exe -m scripts.coverage_matrix_e16 --baseline-matrix docs/data/matriz-simbologia-e16.csv --e07-report tmp/roadmap-e10/benchmark/report.json --output tmp/roadmap-e10/matriz-depois.csv --summary tmp/roadmap-e10/matriz-depois-resumo.json` → código 0.
- `.venv/Scripts/python.exe -m scripts.curation_coverage_e16 compare --before docs/data/matriz-simbologia-e16.csv --after tmp/roadmap-e10/matriz-depois.csv --output tmp/roadmap-e10/delta-e16.json` → delta zero.

**Bloqueios:**

- Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Falha preexistente sem relação com o roadmap → registrar como pendência com evidência, sem corrigir fora do escopo.

**Evidências e handoff:**

- Snapshot inicial (retomada): `52868c61b45f74686ecb2e652053d684ca7af9da` (recebido do orquestrador). Snapshot ao fim da retomada: `84904036eeee143e2f13ac6222892a8067d27587`; `git diff --stat` entre os dois mostra só este roadmap (2 linhas: as tags), antes do preenchimento deste handoff.
- Registro histórico — bloqueio anterior resolvido com autorização do usuário. A primeira execução (snapshot `c76e26e2b5bdd6cbe05bfbbb0bb2b910cec72dcf`) marcou E10 `#bloqueada` porque `IniciarTestes.bat` reprovava só por três falhas preexistentes fora do roadmap: (1) mypy e coleta do pytest quebrados por `tests/unit/test_characterization_support.py`, que importava o inexistente `tests.characterization`; (2) `test_windows_app_identity::test_window_identity_sets_taskbar_relaunch_icon_and_clears_properties` dependente da caixa do caminho (`C:\Zeny` × `C:\zeny`); (3) 18 funções rank E/F em `src/` no gate de complexidade. Na primeira execução o delta da matriz já era zero.
- Mudanças fora do escopo do roadmap, autorizadas explicitamente pelo usuário e feitas antes desta retomada (já presentes no snapshot inicial; esta sessão não as editou, só conferiu):
  1. `tests/unit/test_characterization_support.py` e `tests/fixtures/e10_characterization/` (órfãos; `tests.characterization` não existe nem no histórico do Git) foram movidos para `tmp/preservado-caracterizacao/` (ignorado pelo Git). Conferido nesta sessão: `sha256sum -c SHA256SUMS` → 3 arquivos `OK`; os caminhos originais não existem mais.
  2. `tests/unit/test_windows_app_identity.py` (diff de 7 linhas contra o HEAD): o teste cria um ícone real em `tmp_path` e espera `f"{icon_path.resolve()},0"`, sem depender da caixa do caminho da máquina.
  3. Refatoração sem mudança de comportamento das 18 funções E/F em 11 arquivos de `src/`: `adapters/analysis/{declarative_symbols,legend_symbols,pymupdf_guys,pymupdf_transformers,raster_symbols,structural_symbols}.py`, `application/{interpretation_pipeline,symbol_reconciliation}.py`, `zeny_project_handler_client/ui/review_panel.py`, `zeny_project_handler_server/{deliverable_exports,symbol_review}.py`. Oráculo de regressão em `tmp/refator-complexidade/` (`antes/` × `depois/`, comparadores `comparar.py`, que ignora tempos, memória, hashes de código/fonte, caminhos e hashes de exportação e compara células de XLSX, e `difjson.py`). Reexecutado nesta sessão com `python -I`:
     - `benchmark_symbols` com todos os `--include-*`: `examples` (16 PDFs) → `DIFERENÇAS: 0`; `corpus-sint` → `0`; `sintetico` → só `manifest.json`, e `difjson.py` mostra que as 30 diferenças são `seconds`, `memory/*`, `path`, `mtime_ns`, `predictions_sha256` e `report_sha256`.
     - `benchmark_review_e14` sobre o corpus sintético e sobre `examples/`, excluindo o estado efêmero `server/` → só `manifest.json`, cujas diferenças são `code_sha256` dos quatro arquivos refatorados, `exports[]/path`/`sha256`, `session`, `manifest_sha256` e `predictions_sha256`; `review-session.json` e células de `results.xlsx` idênticos. Em `server/` só diferem UUIDs de revisão/job, carimbos de tempo e arquivos com nome de UUID.
- Arquivos alterados nesta retomada: só este roadmap (tags de E10 no índice e no título, critérios de aceite, "Bloqueios" e este handoff). Saídas geradas: `relatorio-testes.txt` (ignorado pelo Git) e, em `tmp/roadmap-e10/`, `relatorio-testes.txt` (cópia), `retomada/iniciar-testes-console.txt`, `retomada/iniciar-testes-exit.txt`, `benchmark/`, `benchmark.log`, `matriz.log`, `delta.log`, `matriz-depois.csv`, `matriz-depois-resumo.json` e `delta-e16.json`. As saídas da primeira execução foram movidas para `tmp/roadmap-e10/anterior/`.
- Validações executadas (do zero, nesta retomada):
  - **Gate completo** `.\IniciarTestes.bat` pelo PowerShell: código 0 em 514 s, `RESULTADO FINAL: APROVADO`.

    | Seção | Resultado |
    |---|---|
    | Python | 3.13.14, código 0 |
    | `pip check` | `No broken requirements found.`, código 0 |
    | Ruff | `All checks passed!`, código 0 |
    | Formatação | `462 files already formatted`, código 0 |
    | mypy | `Success: no issues found in 413 source files`, código 0 |
    | Gate do cliente magro | `GATE DO CLIENTE: APROVADO`, código 0 |
    | pytest --cov | `2452 passed in 508.05s`, `TOTAL 88.20%`, `Required test coverage of 85.01% reached`, código 0 |
    | Complexidade | `GATE DE COMPLEXIDADE E/F: APROVADO`, 3236 funções, nenhuma E/F, código 0 |

  - **Cadeia de cobertura:**
    - `scripts.benchmark_packages_e07 --output tmp/roadmap-e10/benchmark` → código 0; 10 famílias, 23 positivos, 95 negativos, TP 23, FP 0, FN 0, 0 duplicatas.
    - `scripts.coverage_matrix_e16 …` → código 0; `reconhecido_exato` 33, `alternativa_sem_id_resolvido` 34, `informativo` 97, `nao_avaliavel` 12, `ainda_nao_suportado` 251.
    - `scripts.curation_coverage_e16 compare …` → código 0; `added_ids`, `newly_exact_ids`, `lost_exact_ids` e `transitions` vazios, `net_exact_change` 0, 427 IDs no denominador antes e depois, mesmas contagens por status. **Delta zero.**
    - `matriz-depois.csv` tem o mesmo SHA-256 da primeira execução (`f9a8a172…`), e `delta-e16.json` é idêntico byte a byte ao anterior. `before_sha256` ≠ `after_sha256` pelo motivo já registrado: só a coluna livre `evidence` difere em 46 linhas, por texto do gerador existente; nenhuma coluna de status muda (o mesmo arquivo sai da cópia do HEAD).
- Parecer do verificador: APROVADO (verificador independente do orquestrador; snapshot de verificação c31e98e60426b6876d772624d99f3eaed52b51bd). 2/2 critérios aprovados com execução própria: .\IniciarTestes.bat pelo PowerShell com código 0 em 537 s e RESULTADO FINAL: APROVADO (2452 testes, cobertura 88,20%, complexidade E/F aprovada); cadeia E07 → coverage_matrix_e16 → compare com delta zero, delta-e16.json e matriz-depois.csv idênticos byte a byte aos da retomada. As três resoluções autorizadas pelo usuário foram julgadas bem feitas: arquivos de caracterização preservados com SHA-256 conferido; teste de identidade independente da caixa do caminho; refatoração das 18 funções restrita às funções-alvo (comparação de AST), helpers com CC ≤ 29, oráculo antes/depois sem diferenças além de campos voláteis, PDFs exportados com texto e desenhos iguais e fuzz diferencial de _validate_package com 59.110 pacotes sem divergência. Menores: um documento de examples/ falha com 'Limite de traços raster alcançado' igualmente antes e depois; arquivos preservados vivem só em tmp/; alguns comentários citam a forma anterior do código.
- Notas para a próxima etapa:
  - Os dois critérios de aceite estão atendidos; falta a verificação independente do orquestrador para fechar E10.
  - E11: o gate completo leva cerca de 8,5 min nesta máquina e deve ser rodado pelo PowerShell (`.\IniciarTestes.bat`); no Git Bash, `cmd.exe //c IniciarTestes.bat` saiu sem executar nada. A cadeia de cobertura leva poucos segundos.
  - Os arquivos de caracterização preservados em `tmp/preservado-caracterizacao/` não fazem parte do gate; cabe ao usuário decidir se os descarta.

---

## E11 — Primeira rodada completa de curadoria — #bloqueada

**Objetivo:** executar com `/curadoria-simbologia` uma rodada completa sobre todos os PDFs de `examples/`, em ondas de N = 4, corrigindo as divergências acionáveis nos módulos donos com fixtures sintéticas, e terminar com gates completos, reinferência de regressão e a matriz de curadoria atual publicada em `docs/data/`.

**Por que agora:** é a validação de ponta a ponta do fluxo novo e a curadoria que motivou este roadmap; os PDFs já estão em `examples/`.

**Dependências e paralelismo:** E10. Não paraleliza com outras etapas; o paralelismo é interno à rodada.

**Quem executa:** a sessão de nível superior (no modo automático, o próprio orquestrador), porque a rodada dispara leitores, auditores, investigadores e corretores como subagentes e subagentes não disparam outros.

**Escopo:**

- Rodada em `tmp/curadoria-simbologia/` seguindo `.claude/skills/curadoria-simbologia/SKILL.md` lido diretamente, com N = 4 (reduzir se faltar memória, H4) e sem rodada anterior (todos os PDFs são lidos).
- Correções nos detectores, pacotes, inventário (só com fonte rastreável) e fixtures/testes que o backlog justificar, cada uma com fixture sintética autoral positiva e negativa, sem memorizar nome, hash ou coordenadas dos PDFs.
- Ajuste dos padrões de N, tile, DPI e limiar de concordância na skill e nos CLIs, se a rodada mostrar necessidade, descrito no presente, sem citar a rodada.
- Fechamento: gates completos, reinferência paralela de todos os PDFs com o código final, matriz e resumo publicados em `docs/data/matriz-simbologia-curadoria-atual.csv` e `docs/data/matriz-simbologia-curadoria-atual-resumo.json` só com gates aprovados, e `relatorio.md` da rodada em `tmp/`.
- Depois do parecer APROVADO: seção "Encerramento" do cabeçalho.

**Fora de escopo:** declarar aceite integrado ou recall de campo; usar reservas E16 seladas; escrever resultados da rodada em arquivos versionados além da matriz e do resumo; copiar PDFs, recortes ou caminhos privados para o Git.

**Passos de implementação:**

1. Ler a skill e o contrato vivo; conferir `git status` e o número de PDFs em `examples/`.
2. Executar as ondas conforme a skill, com leitores e auditores em paralelo e corretores em worktrees por pista disjunta.
3. Fechar a rodada: gates, reinferência de regressão, matriz, relatório local.
4. Verificação independente; com APROVADO, executar o "Encerramento".

**Estratégia de execução:** `padrão` · Revisão humana: não

- Investigação: nenhuma além da própria rodada (a skill conduz).
- Partes paralelas: as do próprio fluxo — leitores visuais e auditores por PDF, corretores por pista com arquivos disjuntos em `isolation: worktree` —, todas disparadas pela sessão de nível superior.
- Foco do verificador: referência congelada depois de exposição a predições sem registro; métricas sem denominador; correção que memoriza o PDF ou sem negativo; regressão escondida no agregado; matriz publicada sem gates aprovados; PDF, recorte ou caminho privado versionado; resultado de rodada escrito em arquivo versionado.

**Prompt para uma sessão limpa:**

```text
Execute a etapa E11 — "Primeira rodada completa de curadoria" do roadmap docs/roadmap-curadoria-simbologia-paralela.md, neste repositório. Esta sessão é a sessão de nível superior da rodada: você mesmo dispara os subagentes que a skill pede.

Antes de alterar qualquer coisa, leia CLAUDE.md (e AGENTS.md, se existir), o cabeçalho do roadmap — incluindo "Desenho do fluxo-alvo", "Restrições e invariantes", "Encerramento" e o "Protocolo de execução" —, a seção E11 inteira, o "Evidências e handoff" de E08 a E10, docs/fluxo-curadoria-incremental-simbologia.md e .claude/skills/curadoria-simbologia/SKILL.md. Rode git status e preserve mudanças preexistentes que não sejam suas. Confirme que E10 está #concluida e que examples/ tem PDFs; se não, ou se o código divergiu do plano, pare e relate.

Objetivo: rodada completa sobre todos os PDFs de examples/ com N = 4, seguindo a skill (modo de reserva se os agentes de .claude/agents/ não estiverem registrados nesta sessão): render e inferência paralelos, leitores visuais cegos, congelamento, comparação, auditoria amostral, backlog, correções por pista com fixtures sintéticas, reinferência, gates completos e matriz publicada em docs/data/ só com gates aprovados. Relatório da rodada só em tmp/. Nenhum PDF, recorte, caminho privado ou resultado em prosa entra em arquivo versionado.

Siga o Protocolo de execução com a estratégia padrão:
- tire o snapshot inicial e troque a tag de E11 para #em-andamento no índice e no título;
- conduza as ondas pela skill, retomando pelo rodada.json após compactação;
- verificação independente com o Prompt do verificador, com foco em exposição não registrada, denominadores, correções que memorizam o PDF, regressões, matriz sem gates e dados privados versionados.

Critérios de aceite (detalhes na seção E11):
- todos os PDFs em fechado ou encerrado_com_pendencias, com referência, inferência, comparação e auditoria;
- correções com fixture sintética e testes; IniciarTestes.bat aprovado no código final;
- matriz e resumo de curadoria atual publicados; delta registrado no relatório local;
- nenhum dado privado ou resultado em prosa versionado.

Não declare sucesso com validação falhando ou não executada. Em vez de marcar #concluida, com parecer APROVADO do verificador execute a seção "Encerramento" do roadmap, que o apaga; diante de impedimento real, marque #bloqueada e registre causa, evidência, impacto e ação de desbloqueio em "Bloqueios", sem encerrar.

Antes do encerramento, preencha "Evidências e handoff" de E11 (snapshot, arquivos alterados, decisões, comandos e resultados, parecer do verificador). No fim, responda com um resumo curto: PDFs fechados e com pendência, concordância, TP_IA/FP_IA/FN_IA com denominadores, correções, delta de cobertura, tempos por fase, caminho do relatório em tmp/ e git status --short. Não faça commit, push ou deploy.
```

**Critérios de aceite:**

- [ ] `curation_round status` da rodada mostra todos os PDFs descobertos em `examples/` (16 em 2026-10-15) em `fechado` ou `encerrado_com_pendencias`, cada um com referência congelada antes da comparação, inferência, comparação e auditoria registradas.
- [ ] Toda correção feita tem fixture sintética autoral com positivo e negativo e teste focado passando; cada PDF afetado foi reinferido e recomparado contra a mesma referência congelada.
- [ ] A reinferência final de todos os PDFs com o código final não mostra perda de TP_IA em nenhum PDF sem justificativa registrada no relatório local.
- [ ] `relatorio-testes.txt` do código final termina com `RESULTADO FINAL: APROVADO`.
- [ ] `docs/data/matriz-simbologia-curadoria-atual.csv` e `docs/data/matriz-simbologia-curadoria-atual-resumo.json` existem e foram gerados por `coverage_matrix_e16` com o relatório de pacotes da própria rodada; o delta está em `tmp/` e no relatório.
- [ ] `tmp/curadoria-simbologia/RODADA/relatorio.md` traz tempos por fase, concordância por PDF, TP_IA/FP_IA/FN_IA com denominadores, correções, pendências e delta.
- [ ] `git status --short` não mostra nada sob `examples/` ou `tmp/`, e nenhum arquivo versionado contém nome de PDF de `examples/` nem resultados da rodada em prosa.

**Validação obrigatória:**

- `.venv/Scripts/python.exe -m scripts.curation_round status --rodada` seguido do diretório da rodada → estados finais de todos os PDFs.
- `cmd.exe //c IniciarTestes.bat` (no PowerShell: `.\IniciarTestes.bat`) → `RESULTADO FINAL: APROVADO`.
- `.venv/Scripts/python.exe -m scripts.curation_coverage_e16 compare --before docs/data/matriz-simbologia-e16.csv --after docs/data/matriz-simbologia-curadoria-atual.csv --output` seguido de um arquivo em `tmp/` → código 0.
- `git grep -n "PROJETO DE REDE NS"` → sem resultados.
- Inspeção visual pelo verificador: abrir com Read os tiles de evidência de ao menos 3 divergências corrigidas e 3 pendentes e conferir a classificação registrada.

**Bloqueios:**

- **Causa:** a matriz de curadoria atual não pode ser publicada, porque a skill (Fechamento, item 7) exige todos os gates e a revisão visual aprovados, e dois gates de fechamento ficaram abertos:
  1. **E14 (persistência, revisão e exportação) falha.** `benchmark_symbols examples --root examples` com todos os includes termina `failed`: 1 página falhou, `structural-raster-graph` "Limite de traços raster alcançado" num único PDF do corpus. A falha já ocorria no baseline antes da rodada. `benchmark_review_e14` recusa então o checkpoint ("Cannot reuse an incomplete inference checkpoint").
  2. **Inspeção visual da UI e das exportações não realizada.** Não existe `.env` com a string ODBC do SQL Server de mercado, então `ZenyProjectHandler.bat` não sobe a sessão local; a inspeção é visual no cliente Qt.
- **Evidência:** `tmp/curadoria-simbologia/20261015-2106/fechamento/corpus.log`, `revisao.log` e `corpus/manifest.json` (falha do método); ausência de `.env` na raiz; seção "Pendências de referência, OCR, medição e gates" de `tmp/curadoria-simbologia/20261015-2106/relatorio.md`. Como evidência suplementar, sem substituir o gate, o E14 sem os métodos estruturais passa: 16 documentos, 277 propostas (`fechamento/revisao-sem-estruturais`).
- **Impacto:** o critério de aceite da matriz publicada não é atendido e o "Encerramento" não pode ser executado. Os demais artefatos da rodada estão completos: PDFs fechados ou encerrados, gate completo aprovado, regressão sem perda e matriz gerada em `tmp/`.
- **Ação de desbloqueio:**
  1. Corrigir a falha de execução de `structural-raster-graph`, dono `src/zeny_project_handler/adapters/analysis/structural_symbols.py`, como pista própria com fixture sintética (limite atingido sem falhar a página, ou limite adequado), seguida de verificador.
  2. Refazer o fechamento da skill: gates, regressão, corpus e E14.
  3. O usuário cria `.env` a partir de `.env-example`, roda `.\ZenyProjectHandler.bat` e inspeciona na UI e nas exportações os elementos afetados pelas correções. São eles: estais com anel, discos de ponto de conexão, caixas de pictograma de aterramento e para-raios, transformadores e associação símbolo → poste. O usuário registra o resultado.
  4. Com tudo aprovado, publicar `RODADA/matriz-depois.csv` e `-resumo.json` em `docs/data/matriz-simbologia-curadoria-atual*`.
  5. Rodar o verificador de E11 e, com APROVADO, executar o "Encerramento".

**Riscos e mitigação:**

- Contexto da sessão de nível superior esgota numa rodada longa → a skill mantém o estado em `rodada.json` e nos checkpoints; após compactação, retomar pelo `status`.
- Memória insuficiente com 4 inferências (H4) → reduzir `--jobs` e registrar no relatório local.
- Correção que melhora um PDF e piora outro → a reinferência final de todos os PDFs detecta; reabrir a pista e corrigir antes de publicar a matriz.

**Evidências e handoff:**

- Snapshot inicial: `4c595adf20e1265f19280c7d18a79d4525a62003`.
- Arquivos alterados, todos sem commit:
  - **Pistas de detector:**
    - `pymupdf_symbols.py` e `pymupdf_analyzer.py` (1.20.0:vetorial-6 / 1.20.0);
    - `pymupdf_transformers.py` (v5);
    - `pymupdf_guys.py` (e06-estais-v3);
    - `declarative_symbols.py`, `symbol_packages/family-f02-28.json` e `docs/schemas/pacotes-simbologia.schema.json` (perfil 1.1.0, s28-v001 habilitado);
    - `interpretation_pipeline.py`, `symbol_reconciliation.py` e `topology_compliance.py` (e16-symbol-support-anchor-2).
  - **Fixtures e testes:** `tests/fixtures/{declarative_symbols,guys,transformers}/`, `tests/unit/test_{pymupdf_guys,pymupdf_transformers,pymupdf_analyzer,declarative_symbol_packages,legacy_symbol_adapter,benchmark_symbols,symbol_support_association}.py` e `tests/server/test_e14_symbol_review.py` (343/22).
  - **CLIs e testes:** `scripts/curation_{render,audit,compare,backlog,infer}.py`.
  - **Regras de leitura:** `.claude/skills/curadoria-simbologia/SKILL.md`, `.claude/agents/curadoria-{leitor,auditor}-visual.md` e `docs/fluxo-curadoria-incremental-simbologia.md` (critério de estado, completude, camada anotada, bbox justa de disco, bbox de estai de âncora, DPI 400).
- **Decisões:**
  - `--native-only` em toda a rodada, porque o Tesseract está ausente.
  - DPI de detalhe 400.
  - Concordância v2 e comparação/backlog v2 (classes suportadas, lacunas de cobertura).
  - Encerramentos adiados até o fechamento, para que esses PDFs entrem na regressão.
  - Correções em série na árvore principal, sem worktree, como manda a skill; o passo 2 da etapa diverge disso, e prevalece a skill.
  - Convenção de bbox de estai de âncora (do centro do poste ao fim do símbolo); revisões de referência sempre com `--exposicao sim`.
  - Ablação com as referências finais fixas, para separar o ganho do detector do efeito das revisões.
- **Validações executadas:**
  - `curation_round status`: 6 `fechado`, 10 `encerrado_com_pendencias`.
  - `.\IniciarTestes.bat`: `RESULTADO FINAL: APROVADO` (2611 passed, cobertura 88,24%, complexidade E/F aprovada).
  - Regressão de todos os PDFs com o código final: idêntica ao pós-ciclo 2, sem perda de TP em nenhum PDF. A união, com 445 avaliáveis, ficou em TP 140 / FP 66 / FN 305; com as mesmas referências e a inferência inicial era 16/119/429.
  - `audit_symbol_packages`: 0 erros.
  - Sintético: baseline e composição iguais ao inicial; união bruta FP +7, todas `duplicate`.
  - V-N com jsonschema 4.26.0: 94 instâncias válidas.
  - `git diff --check` limpo.
  - `git grep -n "PROJETO DE REDE NS"` sem resultados.
  - `git status --short` mostra sob `examples/` só `examples/README.md`, alterado por E09; nada sob `tmp/`.
  - Gate E14: FALHOU (ver "Bloqueios").
  - Matriz gerada em `tmp/` com delta de +1 ID exato (s28-v001) e nenhum perdido. Não foi publicada e `curation_coverage_e16 compare` contra `docs/data/` não foi executado.
- **Parecer do verificador:** não disparado, porque a etapa está bloqueada antes de cumprir o critério da matriz publicada. Pareceres das pistas: as 6 APROVADO; `pista-estais-anel` só depois de uma reprovação.
- **Notas para a próxima etapa:**
  - Retomar pelo "Ação de desbloqueio".
  - O relatório completo da rodada está em `tmp/curadoria-simbologia/20261015-2106/relatorio.md`.

---

## Histórico de revisões

- 2026-10-15 — roadmap criado.
- 2026-10-15 — execução única sem pausas de revisão humana; piloto de 3 PDFs substituído pela primeira rodada completa sobre os 16 PDFs de `examples/`; contrato vivo sem histórico; seção "Encerramento" apaga o roadmap ao final.
