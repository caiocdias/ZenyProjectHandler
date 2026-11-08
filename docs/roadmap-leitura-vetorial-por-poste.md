# Roadmap — Leitura vetorial por poste

> Arquivo: `docs/roadmap-leitura-vetorial-por-poste.md` · branches de execução: `roadmap/leitura-vetorial-por-poste` (trilha A), `roadmap/leitura-vetorial-por-poste-b` e `roadmap/leitura-vetorial-por-poste-c` · criado em 2026-10-30 · última revisão 2026-11-05

## Como usar

As etapas pendentes estão agrupadas em trilhas (A — analisador, B — medição, C — aprendizado; ver "Índice de etapas"), mas um único orquestrador executa todas. Inicie uma sessão limpa do Claude Code na raiz do repositório com `claude --agent orquestrador` e cole o "Prompt de execução". Não abra uma segunda sessão de orquestrador enquanto essa estiver aberta. A própria sessão abre até 2 etapas de trilhas diferentes ao mesmo tempo, cada uma no worktree da sua trilha, e roda as tarefas independentes em ondas. Cada execução conclui até 3 etapas, planejadas pelo plugin superpowers e executadas pelas souls (subagentes do Second Brain), e para para revisão. No fim do lote, o orquestrador integra as branches das trilhas na `main` com merge local e deixa pronto o `git push origin main`, que fica com você. A ordem em que as etapas abrem está em "Janelas", no índice. Para não parar em cada pedido de permissão, libere antes os comandos de build/teste do projeto nas permissões do Claude Code.

## Objetivo

A análise entrega, para cada poste da folha, a ficha correta: identificador, estrutura, poste, coordenada UTM, vãos e símbolos associados. Isso vale para as quatro famílias de PDF observadas. A leitura parte do vetor como desenho, com texto em contorno lido por forma, e não por OCR. Coordenadas e vãos são conferidos pela geometria UTM. Um detector visual local treinado cobre o resíduo. A precisão é medida por poste, contra referência congelada.

## Contexto confirmado

- **Stack:** Python 3.11–3.13; servidor FastAPI + SQLite/Alembic + PyMuPDF + Tesseract; cliente PySide6 (`pyproject.toml`, `CLAUDE.md`).
- **Design:**
  - `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md`, fonte deste roadmap;
  - `docs/adr/0016-leitura-vetorial-com-modelo-de-desenho.md`;
  - `docs/adr/0017-detector-visual-local-e-rotulagem-assistida.md`;
  - `docs/superpowers/specs/2026-11-04-execucao-acelerada-leitura-vetorial-design.md`, fonte das trilhas, do laboratório, do orçamento e das etapas E14–E16 (com a evidência de tempo das E03–E05).
- **Souls:** as regras de execução vigentes vivem na soul `orquestrador` do vault (`99 System/Souls/agents/orquestrador.md`, commit `93f0c68`, D8): ciclo por tarefa, ondas paralelas, testador condicional, suíte por fase, decisões pela opção recomendada e fechamento com merge. Onde o design de execução acelerada diverge delas (integração do lote e propostas P1–P3), valem as souls.
- **Custo do gate** (2026-11-04):
  - a suíte tem 5330 testes e leva 1578 s com cobertura, em série, sem `pytest-xdist` (`relatorio-testes.txt`). A máquina tem 20 núcleos lógicos;
  - o `.bat` de `main` reprova num teste de tempo de parede, `test_glyph_text_orcamento.py::test_pagina_hostil_acima_do_teto_de_resolucoes_e_limitada_em_tempo_limitado` (29,7 s contra o limite de 20 s);
  - as souls `desenvolvedor` e `testador` rodavam a suíte inteira antes de cada commit e no fim da tarefa. Desde 2026-11-05 (D8), o desenvolvedor roda os testes da área a cada commit e a suíte inteira uma vez por tarefa, e o testador só entra nas tarefas `Risco: alto`, nas lacunas da revisão e uma vez por etapa. Depois da E14, a suíte paralela leva 189–233 s.
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
- **Second Brain:** o projeto não está registrado (não há hub nem hook). O vault tem só a nota de tema `ZenyProjectHandler - Leitura vetorial por poste e detector local` e uma captura pendente da execução acelerada. O bloco "Second Brain" do protocolo não se aplica até o registro.

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
- atualização das dependências vulneráveis (E13, decisão D3);
- gate de testes paralelo (E14), ficha predita das propostas (E15) e conjunto de avaliação cego em etapa própria (E16), conforme a decisão D6;
- fechamento do cliente com servidor lento (E17), achado da revisão final da E14.

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
| H1 | Nas famílias sem texto nativo, cada forma pequena preenchida é um glifo de fonte fixa. Resultado da E05: se sustenta. Há 0 grupos compostos e 0 fragmentos; o resíduo misto é de cerca de 1,1% dos glifos. 88% (Electric Office) e 96% (Ghostscript) dos candidatos caem em trecho. Maiúscula e minúscula de mesmo desenho só se separam pela escala, e o leitor falha fechado quando ela não decide | a leitura por assinatura precisa segmentar glifos compostos ou tolerar variação de curva | E05 |
| H2 | Os símbolos da rede são vetoriais em todas as famílias. Resultado da E06.3.2.1: refutada no sentido estrito. Nas 16 folhas há 1 símbolo da rede em raster (folha 004, iText: disco laranja com "~" no fim de um ramal, classe fora da ficha), e `residuos_raster` o marca. Para as classes da ficha ela se sustenta: nenhuma das 179 referências é raster | símbolos rasterizados vão direto para o resíduo do detector (E12) | E06, E12 |
| H3 | As imagens das folhas Print To PDF e iText são só ladrilhos da ortofoto. Resultado da E04: os ladrilhos são só ortofoto e nenhum símbolo é raster, mas as folhas iText trazem tabelas (CHI, servidão, APP) como imagem e a folha Ghostscript traz um rótulo de poste em imagem de anotação | se carregarem símbolos ou texto, o OCR não pode sair em E09 — há texto em raster: a E09 precisa tratá-lo ou declará-lo fora da ficha | E04, E09 |
| H4 | O usuário reserva folhas novas, ainda não vistas, para o conjunto de avaliação antes de E09. Em 2026-11-04 o usuário disse que consegue as folhas em breve | sem elas, a E16 fica bloqueada e a E09 não tem prova cega | E16, E09 |
| H5 | PyTorch com ROCm treina na RX 9070 XT desta máquina (Windows nativo ou WSL2). Resultado da E11: não se sustenta no Windows nativo com o release oficial ROCm 7.2.1 (torch 2.9.1). O BatchNorm de treino falha no MIOpen para a gfx1201. O WSL2 não foi ensaiado. O treino vai para a CPU, com 7,5 a 10,5 h na carga de referência (ADR 0017) | o treino cai para CPU ou para GPU alugada (D1) | E11 |
| D1 | Treinar em GPU alugada por hora, se ROCm e CPU forem inviáveis | sem decisão, E12 só treina em CPU | E12 (só se E11 concluir que o treino local é inviável) |
| D2 | Decidido em 2026-11-02: a ficha predita vem do projeto promovido (R2 da E02), e o formato v1 e o casamento guloso 0,02/0,05 são mantidos, com calibração na E03 | se a E03 pedir outra fonte, entra nova `versao_extracao` no `gerador` | E03 |
| D3 | Decidido em 2026-11-02: uma etapa própria de atualização de dependências entra antes da E03, com prioridade para o Pillow do lock do servidor. Criada como E13 | sem ela, a E03 roda sobre locks com vulnerabilidades conhecidas | E13, E03 |
| D4 | Decidido em 2026-11-02: o usuário libera os agentes `curadoria-*` do projeto na soul `orquestrador` (lista de subagentes e pré-condição), para a leitura dupla cega da E03 rodar na sessão do orquestrador | sem isso, a E03 não roda pelo protocolo | E03 |
| D5 | Decidido em 2026-11-04: a ficha predita ganha uma `versao_extracao` a partir das propostas, porque o projeto promovido não tem postes nas folhas reais (baseline 0/107). Vira a etapa E15, separada da E07 | sem ela, a E07 não tem baseline informativo para comparar | E15, E07 |
| D6 | Decidido em 2026-11-04 por entrevista: execução acelerada. São trilhas paralelas, gate paralelo antes da E06 (E14), laboratório paralelo para calibração contra folhas reais, orçamento de ~3h por etapa e E15/E16 como etapas próprias. As alternativas descartadas e a evidência estão no design de execução acelerada (seção "Decisões") | — | protocolo, E06–E16 |
| D7 | Decidido em 2026-11-04: os worktrees de laboratório são descartáveis, e o orquestrador os remove no fechamento da tarefa sem pedir confirmação | sem isso, cada remoção pararia o lote | protocolo |
| D8 | Decidido em 2026-11-05 pelo usuário, numa sessão do vault, e aplicado nas souls (as regras vivem no `orquestrador`). P1 adotada: testes da área por commit e suíte inteira uma vez por tarefa e por rodada devolvida. P2 adotada como ondas paralelas: tarefas sem dependência e com arquivos disjuntos, até 3 por onda, cada uma em worktree próprio, integradas em série com a suíte inteira por onda. P3 descartada, porque a revisão é ~8% do tempo dos subagentes. Junto: testador condicional (`Risco: alto`, lacunas da revisão e uma vez por etapa), tarefas de até ~45 min, intervenções decididas pela opção recomendada (só arquitetura espera o usuário) e lote que termina com merge local na `main`, sem push | se as ondas criarem conflito ou teste intermitente sob carga, baixe o limite da onda no prompt (por exemplo, "ondas de até 2") | todas as etapas |
| D9 | Decidido em 2026-11-05 pelo arquiteto, revisto com a D11: um orçamento de máquina para o paralelismo empilhado (etapas simultâneas × ondas × laboratório), com teto de ~4 desenvolvedores ativos na sessão. Com uma etapa aberta, as ondas têm até 3 tarefas; com duas, até 2 em cada. O laboratório ocupa a cota da etapa dele, e `-n` e `--processos` repartem os 20 núcleos pelas suítes simultâneas da sessão (protocolo, "Orçamento de máquina"). Descartadas: limite fixo de ondas, porque a etapa longa ficaria sem ondas depois que a curta fecha; e nenhum teto, porque duas etapas com ondas de 3 dariam 6 desenvolvedores e ~36 workers do pytest em 20 núcleos, rumo à carga de 60 processos em que a E14 viu workers Qt morrerem (I-2) | teto baixo demais deixa a E06 com ondas de 2 enquanto a E15 ou a E17 estão abertas; teto alto demais traz de volta a instabilidade de Qt sob carga. Em ambos os casos, ajuste a tabela do protocolo | protocolo, prompt |
| D10 | Decidido em 2026-11-05 pelo arquiteto: a E17 passa da trilha A para a C, que já tem worktree com `.venv` e está ociosa até a E07. Assim a trilha A vai direto à E06, no caminho crítico E06 → E07 → E08 → E09, e a E17 abre como segunda etapa quando a E15 fechar. Descartadas: a E17 na A antes da E06, porque atrasaria o caminho crítico em uma etapa; e a E17 na B depois da E15, porque misturaria cliente e medição na mesma branch, sem ganho de tempo | nenhum além de uma branch a mais no fim do lote. A E17 pode voltar para a A depois da E06 sem mudar o escopo | E17 |
| D11 | Decidido em 2026-11-05 pelo usuário: um orquestrador aberto por vez, e o paralelismo entre etapas é feito por ele. Isso substitui as sessões paralelas por trilha da D6. Desenho do arquiteto: as trilhas continuam como agrupamento, com os mesmos worktrees e branches, e a sessão abre até 2 etapas de trilhas diferentes ao mesmo tempo (protocolo, "Trilhas, branch e etapas simultâneas"). Descartadas: uma sessão por trilha (a D6 original, recusada pelo usuário); uma sessão sem etapas simultâneas, só com ondas de tarefas, que perderia a E15 e a E17 em paralelo com a E06; e 3 etapas abertas, porque três planos, três ledgers e três revisões finais no mesmo contexto aumentam a compactação e o risco de confundir etapas, e o teto de ~4 desenvolvedores já não comporta ondas em três etapas | se a sessão se confundir entre as etapas abertas (despacho no worktree errado, ledger trocado), baixe para 1 etapa aberta no prompt; as ondas de tarefas continuam | protocolo, prompt, índice |
| D12 | Decidido em 2026-11-06 pelo usuário, por entrevista: o método de pacotes sobre o modelo de desenho liga só no `SymbolCompositionRunner` (`symbol_composition`, opt-in), como os métodos atuais, e passa pela reconciliação com eles. O analisador padrão só muda na E09, depois da prova cega. Descartada: ligar também no analisador padrão, que anteciparia a troca sem prova cega, duplicaria com o legado (o job padrão não reconcilia), subiria o custo de toda análise e invalidaria caches | a E07 e a E08 leem os símbolos com o runner ligado até a E09 | E06.2, E07, E08 |

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
| Implementador | `desenvolvedor`, subagente por tarefa; tarefas independentes em ondas paralelas | `superpowers:subagent-driven-development`, prompt implementer |
| Testador | `testador`, subagente nas tarefas `Risco: alto`, nas lacunas da revisão e uma vez por etapa | testes, sem tocar em código de produção |
| Revisor de plano | `revisor-arquitetura`, subagente novo por etapa, modelo mais capaz | revisão do plano antes da execução |
| Revisor de tarefa | `revisor-seguranca`, subagente novo por tarefa | revisão da `subagent-driven-development` |
| Revisor final | `revisor-seguranca`, subagente novo, modelo mais capaz | revisão final da `subagent-driven-development` |
| Captura no brain | `brain-escriba` | publica a captura de atualização em `00 Inbox/` |

Souls: este protocolo exige `orquestrador`, `desenvolvedor`, `testador`, `revisor-seguranca` e `revisor-arquitetura`. Não há fallback: se a sessão não roda como `orquestrador` ou alguma dessas souls não está instalada, pare e diga ao usuário para configurar a máquina (skill `configurar-maquina`) ou iniciar com `claude --agent orquestrador`. O caminho inline (`superpowers:executing-plans`) não vale aqui.

**Trilhas, branch e etapas simultâneas** (D11)

As trilhas agrupam as etapas por cadeia de dependência e por arquivos, mas **um único orquestrador** executa todas. Nunca abra uma segunda sessão `claude --agent orquestrador` para este roadmap enquanto houver uma aberta. As regras abaixo resumem a seção "Trilhas" do design de execução acelerada, com duas trocas: a integração segue a D8 (o fim do lote integra cada branch na `main`, sem esperar o usuário), e as sessões paralelas da D6 viram etapas simultâneas na mesma sessão (D11). No resto, em caso de dúvida, vale o design.

- **Branch e worktree:** cada trilha tem os seus, criados ou retomados com `superpowers:using-git-worktrees`:
  - trilha A em `roadmap/leitura-vetorial-por-poste`;
  - trilha B em `roadmap/leitura-vetorial-por-poste-b`;
  - trilha C em `roadmap/leitura-vetorial-por-poste-c`.

  Nunca execute na branch principal.
- **Etapas simultâneas:** até 2 etapas abertas (`#em-andamento`) ao mesmo tempo, de trilhas diferentes, cada uma no worktree da sua trilha, com plano, ledger e workspace do SDD próprios. Uma trilha nunca tem duas etapas abertas. As duas correm em paralelo, com despachos em segundo plano.
- **Retomada:** se a branch de uma trilha existir com trabalho não integrado, continue nela. Se o lote anterior dela já foi integrado, a branch já está na principal (o fechamento a avança), ou é recriada a partir da principal atualizada. Fora do fechamento do lote (passo 6 do `orquestrador`), o orquestrador não faz merge da principal numa branch de trilha nem rebase dela. Os rebases das branches de tarefa sobre a branch da trilha, nas ondas (passo 3a), são permitidos.
- **Dependência na mesma trilha** não precisa de integração. **Dependência de outra trilha** só vale `#concluida` e integrada na branch principal: confira com `git merge-base --is-ancestor <commit de fechamento> main`. Se ainda não está integrada, a etapa fica para o próximo lote, porque o fechamento integra todas as trilhas de uma vez.
- **Arquivos disjuntos:** duas etapas abertas nunca editam o mesmo arquivo versionado. A regra vale para `src/`, `tests/` (inclusive `conftest.py`), `scripts/`, `pyproject.toml`, locks, `.bat`, `CLAUDE.md`, contrato de curadoria e ADRs. Antes da revisão do plano da segunda etapa, compare a "File Structure" dele com a do plano da etapa aberta. Se cruzar, ajuste o plano para contornar ou deixe a etapa esperar a outra fechar, com ruling. A exceção é este roadmap: cada etapa edita só a sua seção, a sua linha no índice e as linhas de hipótese que fecha. O "Histórico de revisões" é do arquiteto. Se houver conflito no merge do roadmap, mantenha as duas versões.
- **Estado depois de compactação:** confie nos ledgers dos planos abertos e em `git show <branch>:docs/roadmap-leitura-vetorial-por-poste.md` de cada trilha, não na lembrança.
- **Roadmap na branch:** ele é atualizado dentro da branch da trilha da etapa, e tags e handoffs viajam com o código.
- **Dados locais:** os PDFs de `examples/` e os artefatos de `tmp/` são ignorados pelo Git e não existem no worktree. Etapas que leem folhas reais apontam para o `examples/` do checkout principal, só para leitura, e gravam rodadas no `tmp/` dele.
- **Conjunto cego:** `examples/avaliacao-cega/` (E16) não é lido por nenhuma etapa, laboratório, benchmark nem fixture antes da comparação da E09.

**Laboratório** (seção "Laboratório" do design)

- **Quando:** na tarefa cujo aceite depende de ajuste contra folhas reais (limiares, tabelas, heurísticas, recall por família). O plano a marca `Laboratório: sim`.
- **O que o plano traz:**
  - de 2 a 3 hipóteses concorrentes;
  - o comando e a métrica do benchmark sobre as referências congeladas;
  - o critério de vitória (leitura errada afirmada = 0 é obrigatório) e o de parada;
  - a caixa de tempo por hipótese (padrão 60 min).
- **Execução:** antes do ciclo da tarefa, o orquestrador despacha em paralelo um `desenvolvedor` por hipótese, cada um com `isolation: "worktree"`. Esse desenvolvedor:
  - não commita e não roda a suíte inteira;
  - entrega em `tmp/laboratorio/eNN/<hipotese>/` do checkout principal o patch, as métricas por iteração e as conclusões.
- **Seleção:** o orquestrador escolhe pela métrica e registra a ruling no ledger.
- **Ciclo:** a tarefa roda uma vez pelo ciclo completo do `orquestrador`, partindo do patch vencedor. Toda rodada de correção que mexe no comportamento medido repete o benchmark.
- **Limpeza:** os worktrees de laboratório são removidos no fechamento da tarefa (D7).
- **Guardas:** as referências estão congeladas antes e não são editadas; leitores visuais não participam.
- **Por que não fere a SDD:** a proibição de implementadores em paralelo é por conflito no mesmo worktree, e nada do laboratório entra na branch da etapa.

**Orçamento** (seção "Orçamento" do design)

- **Relógio:** vai do commit `#em-andamento` ao commit `#concluida`, sem a espera pelo usuário.
- **No plano:** o plano estima a duração por tarefa. Acima de ~3h, divida a etapa antes de executar em subetapas `Eyy.1`, `Eyy.2`… Cada subetapa tem seção própria, critérios repartidos e ruling no handoff. Ela é uma etapa completa, com plano, revisão de arquitetura, revisão final, `.bat` e handoff. Quem dependia de `Eyy` passa a depender da última subetapa.
- **Estouro:** ao passar de 4h30 no relógio, o orquestrador escolhe dividir, estacionar ou continuar pela opção recomendada, depois de pesar prós e contras, registra a ruling no handoff e segue.

**Orçamento de máquina** (D9)

A máquina tem 20 núcleos lógicos, e etapas simultâneas, ondas e laboratório se somam. O teto da sessão é de ~4 desenvolvedores ativos ao mesmo tempo.
- **Ondas:** com uma etapa aberta, até 3 tarefas por onda (limite da soul); com duas, até 2 em cada. O orquestrador recalcula o limite antes de abrir cada onda. Um número no prompt só baixa esse limite.
- **Laboratório:** ocupa a cota da etapa dele, e ela não abre onda de tarefas enquanto ele roda. São de 2 a 3 hipóteses, e 2 quando há duas etapas abertas.
- **Processos:** a suíte inteira usa `-n` = 20 ÷ suítes que a sessão roda ao mesmo tempo, arredondado para baixo, com mínimo de 2. O orquestrador informa esse número em cada despacho. Os scripts de corpus usam a mesma conta em `--processos`.
- **`.bat`:** usa `-n auto`. Antes de rodá-lo, a sessão espera terminarem as suítes e benchmarks da outra etapa aberta e não despacha novos enquanto ele roda (são 3 a 4 min). Worker morto no `.bat` é defeito (CLAUDE.md), não carga.
- **Leitores visuais** da curadoria só leem imagens e ficam fora da conta.

**Por etapa**

1. **Escolha:** sempre que houver vaga (menos de 2 etapas abertas) e nenhuma parada em curso, abra a primeira etapa `#pendente`, com todas as dependências satisfeitas (regra de trilhas acima), de uma trilha sem etapa aberta. A ordem é A, B, C entre as trilhas (a A é o caminho crítico) e a do documento dentro da trilha. Etapas `#bloqueada` e as que dependem delas ficam para trás.
2. **Conferência:**
   - leia a seção da etapa, os handoffs das dependências e o código que eles citam. Se o código divergiu do que a etapa supõe de um jeito que muda arquitetura ou contrato, pare e relate; divergência menor vira ruling e ajuste no plano;
   - com outra etapa aberta, leia o plano dela ("File Structure") para a regra de arquivos disjuntos;
   - confira que nenhum plano ou script desta etapa lê `examples/avaliacao-cega/` antes da E09.
3. **Início:** troque a tag para `#em-andamento` (índice e título) e commite. Esse commit inicia o relógio.
4. **Plano:**
   - use `superpowers:writing-plans`. A spec é a seção desta etapa mais o design citado em "Contexto confirmado", e as "Restrições e invariantes" entram como Global Constraints;
   - o plano traz a "File Structure" completa, os campos por tarefa do `orquestrador` (`Estimativa`, `Depende de`, `Risco`) e a marca `Laboratório: sim` onde couber. A soma das estimativas decide a divisão da etapa ("Orçamento"). Com outra etapa aberta, a "File Structure" passa pela regra de arquivos disjuntos antes da revisão;
   - salve em `docs/superpowers/plans/AAAA-MM-DD-leitura-vetorial-por-poste-eNN.md`;
   - antes de executar, o plano passa pela revisão de arquitetura do `orquestrador` (`revisor-arquitetura`). As regras (rodadas, veredito, seção no plano) vivem só nele;
   - a execução já está definida (abaixo): não pergunte ao usuário o método, apenas siga.
5. **Execução:**
   - use `superpowers:subagent-driven-development` com esse plano, executado pelas souls conforme o ciclo por tarefa, a verificação mecânica dos testes e a revisão final da etapa definidos no `orquestrador`. As regras de encaixe vivem só nele;
   - o laboratório (acima) precede o ciclo das tarefas marcadas; ondas e laboratório seguem o "Orçamento de máquina";
   - escolha o modelo de cada despacho explicitamente, conforme "Model Selection" da SDD;
   - rode benchmarks de corpus em paralelo (processos ou comandos em segundo plano, com o `--processos` do "Orçamento de máquina"), nunca folha a folha em série;
   - não invoque `superpowers:finishing-a-development-branch` ao fim da etapa: ele roda uma vez, no fim do lote.
6. **Fechamento:** publique a captura de atualização do brain, se o bloco "Second Brain" se aplica. Marque `#concluida` (índice e título) só com a revisão final limpa e cada critério de aceite verificado com evidência. Diante de impedimento real, marque `#bloqueada` e preencha "Bloqueios" com causa, evidência, impacto e ação de desbloqueio. Preencha "Evidências e handoff". Rulings do ledger que mudam contrato, escopo, segurança, dados ou algo caro de desfazer vão para "Decisões para o usuário".

**Second Brain**

Vale se o `CLAUDE.md` tiver a seção "Conhecimento do projeto no Second Brain"; senão, ignore este bloco.

- O contexto da sessão precisa trazer a linha `BRAIN: carregado (ZenyProjectHandler)`, injetada pelo hook. Sem ela, pare e relate.
- Na conferência de cada etapa, leia as notas de tema do brain ligadas a ela e as capturas pendentes do projeto que tratem do assunto: são a referência técnica do projeto.
- No fechamento de cada etapa que mudou algo descrito no brain (inclusive o estado do roadmap), o orquestrador manda o `brain-escriba` publicar em `00 Inbox/` do vault a captura `ZenyProjectHandler - atualização leitura-vetorial-por-poste Eyy`, com o texto novo ou alterado de cada nota afetada e qual nota ele substitui ou complementa; o contrato de agente externo do vault fica com o `brain-escriba`. Nunca edite notas do brain nem registre referência técnica no `CLAUDE.md`.

**Paradas**

Qualquer outra necessidade de intervenção é decidida pelo orquestrador pela opção recomendada, depois de avaliar prós e contras, com a ruling registrada; só decisão de arquitetura ou system design espera o usuário (regras em "Decisões" do `orquestrador`). O lote para nos casos abaixo. Com outra etapa aberta, parar significa não abrir etapa nova, terminar a que está aberta e então fechar o lote:
- ao concluir uma etapa com **Revisão humana: sim**;
- diante de decisão de arquitetura ou system design sem a qual nada mais anda;
- nas paradas que ficam com o usuário: push, deploy, publicação, instalação na máquina, apagar trabalho fora da etapa e segredo exposto;
- quando não resta etapa elegível;
- ao atingir o limite de etapas do prompt. Não abra etapa nova se as concluídas mais as abertas já somam o limite.

Etapa que fica `#bloqueada` não para o lote: o orquestrador segue para a próxima elegível que não depende dela.

**Fim do lote**

1. Use `superpowers:finishing-a-development-branch` com a integração já decidida: merge local na branch principal de cada branch de trilha com trabalho no lote, uma por vez, na ordem A, B, C, conforme o passo de fechamento do `orquestrador`. Cada branch é atualizada com a `main`, que já traz as anteriores, passa no gate e entra com `merge --no-ff`; no fim, o repositório fica limpo e pronto para o próximo orquestrador. Push e deploy ficam com o usuário: o relatório termina com o comando `git push origin main` pronto.
2. Liste as "Decisões para o usuário" acumuladas, que já foram tomadas pela opção recomendada, com prós e contras, para revisão. As de arquitetura que esperam o usuário vão como entrevista: perguntas de múltipla escolha, cada uma com uma opção recomendada e justificada (no Claude Code, `AskUserQuestion` com a recomendada em primeiro lugar e o rótulo "(Recomendado)"). Registre as respostas no handoff das etapas e em "Hipóteses e decisões em aberto".

## Prompt de execução

```text
Execute o roadmap docs/roadmap-leitura-vetorial-por-poste.md deste repositório seguindo a seção "Protocolo de execução" dele, com o plugin superpowers.

Esta é a única sessão de orquestrador deste roadmap: execute aqui todas as trilhas, com até 2 etapas abertas ao mesmo tempo, de trilhas diferentes, cada uma no worktree da sua trilha.
Limite desta execução: no máximo 3 etapas concluídas.
Ondas de tarefas: limite do "Orçamento de máquina" do protocolo (um número aqui só baixa esse limite).

1. Confira a pré-condição do protocolo: esta sessão roda como orquestrador e as souls desenvolvedor, testador, revisor-seguranca e revisor-arquitetura estão disponíveis; se não, pare e diga como resolver. Leia CLAUDE.md (e AGENTS.md, se existir) e, no roadmap, o cabeçalho inteiro, o protocolo e o índice. Se o CLAUDE.md exigir o Second Brain, confira a linha BRAIN: carregado no contexto e leia o hub. Rode git status, git branch -a e git worktree list.
2. Se alguma etapa estiver #em-andamento, retome-a no worktree da trilha dela, a partir do ledger do superpowers e do handoff; não recomece tarefas já commitadas.
3. Para cada etapa que abrir, crie ou retome o worktree/branch da trilha dela (protocolo, "Trilhas, branch e etapas simultâneas") com superpowers:using-git-worktrees. Não trabalhe na branch principal.
4. Enquanto houver vaga e etapa elegível (protocolo, "Escolha"), abra a próxima: marque #em-andamento, planeje com superpowers:writing-plans (spec = seção da etapa + design citado; File Structure, estimativa, dependência e risco por tarefa e laboratório no plano; divida se passar de ~3h), confira os arquivos contra a outra etapa aberta, rode o laboratório das tarefas marcadas, execute com superpowers:subagent-driven-development em ondas dentro do Orçamento de máquina, feche a etapa e preencha o handoff conforme o protocolo. As etapas abertas correm em paralelo.
5. Pare nas paradas do protocolo ou ao atingir o limite: não abra etapa nova e termine a que estiver aberta.
6. No fim, rode superpowers:finishing-a-development-branch para cada branch de trilha com trabalho no lote, uma por vez (A, B, C), com merge local na main conforme o fechamento do orquestrador: tudo commitado, pronto para git push origin main e o repositório pronto para o próximo orquestrador. Depois, liste as decisões tomadas e apresente como entrevista com opção recomendada só as de arquitetura que esperam por mim.

Qualquer necessidade de intervenção: escolha a opção recomendada depois de uma avaliação crítica dos prós e contras e registre a ruling; intervenção humana só para decisão de arquitetura ou system design. Nunca faça push ou deploy. Não altere tags de etapas que não executou.

Ao parar, responda com: etapas concluídas, o relógio e o resultado da revisão final de cada uma, as etapas ainda abertas e seu estado, o motivo da parada, as etapas #bloqueada com a ação de desbloqueio, as branches e os commits do lote e o próximo passo sugerido.
```

## Índice de etapas

Bloco A — base e medição

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Limpeza do projeto | #concluida | — | scripts, testes e docs de etapas encerradas removidos, gate verde |
| E02 | Ficha de referência e benchmark por poste | #concluida | E01 | formato da ficha, avaliador por poste e baseline sintético |
| E13 | Atualização de dependências vulneráveis | #concluida | E01 | locks sem vulnerabilidade corrigível nos pacotes apontados pelo scanner, gate verde |
| E03 | Rotulagem v0 e baseline real | #concluida | E02, E13 | fichas de referência das 16 folhas e baseline do analisador atual em `tmp/` |

Bloco B — leitura vetorial (concluídas)

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E04 | Modelo de desenho e perfis de família | #concluida | E01 | modelo de desenho por página, perfil por família e DXF de depuração |
| E05 | Texto por contorno de glifo | #concluida | E04, E03 | tabela de glifos e texto recuperado sem OCR nas 4 famílias |

Trilha A — analisador (branch `roadmap/leitura-vetorial-por-poste`)

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E14 | Gate de testes paralelo | #concluida | E05 | suíte paralela no `.bat` sem perder teste, `main` verde, scripts de corpus com processos |
| E06.1 | Medição de símbolos e base do modelo | #concluida | E05, E14 | benchmark diagnóstico de símbolos contra as fichas, página do modelo com índice cru, guarda contra memorização |
| E06.2.1 | Núcleo de gramáticas sobre o modelo | #concluida | E06.1 | núcleo puro com índice espacial e teto, 6 gramáticas portadas, paridade no corpus sintético |
| E06.2.2.1 | Método versionado no runner | #concluida | E06.2.1 | método de pacotes sobre o modelo no runner opt-in, resíduo raster marcado, agrupamento sem laço quadrático fora de teto |
| E06.2.2.2 | Medição do método nas 16 folhas | #concluida | E06.2.2.1 | benchmark ao lado do atual e diff por variante, com cada "só no núcleo" classificado |
| E06.3.1 | Pacotes das classes da ficha | #concluida | E06.2.2.2 | 58 variantes do inventário de ESTAI, TRANSFORMADOR, ATERRAMENTO e PARA_RAIOS_MT/BT nos pacotes, como `pending`; auditor e matriz aceitam outro `owner_stage` |
| E06.3.2.1 | Base da haste, leituras erradas e H2 | #concluida | E06.3.1 | tipo de gramática só do modelo, métrica de leitura errada afirmada, resíduos raster por folha e veredito da H2 |
| E06.3.2.2 | Gramática de haste com barras | #concluida | E06.3.2.1 | gramática de haste com barras, com laboratório, ATERRAMENTO e PARA_RAIOS_MT acima do atual |
| E06.3.3.1 | Para-raios BT | #concluida | E06.3.2.2 | gramática do retângulo com diagonal, com laboratório, PARA_RAIOS_BT acima do atual (que não casa nenhuma) |
| E06.3.3.2.1 | Marcas: envolvente e X | #concluida | E06.3.3.1 | envolvente por subcaminho, X perto do símbolo e concordância de situação medida |
| E06.3.3.2.2 | Transformador | #em-andamento | E06.3.3.2.1 | gramática do triângulo em círculo, com laboratório, TRANSFORMADOR acima do atual |
| E06.3.4 | Estai | #pendente | E06.3.3.2.2 | gramática de estai, com laboratório, acima do atual |
| E06.3.5 | Equipamento de interrupção | #pendente | E06.3.4 | gramática de interrupção, acima do atual (que não emite a classe) |
| E07 | Ficha do poste | #pendente | E06.3.5, E15 | associação texto/símbolo/vão → poste, benchmark acima do baseline |
| E08 | Conferência UTM | #pendente | E07 | transformação página → UTM, checagem de posição e vão, pendências |
| E09 | Troca do analisador e remoção do legado | #pendente | E08, E16 | analisador novo como padrão; detectores e, se provado, OCR removidos |

Trilha B — medição (branch `roadmap/leitura-vetorial-por-poste-b`)

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E15 | Ficha predita a partir das propostas | #concluida | E14 | nova `versao_extracao` e baseline real informativo nas 16 folhas |
| E16 | Conjunto de avaliação cego | #bloqueada | E03 | fichas de referência congeladas das folhas novas, antes de qualquer predição |

Trilha C — aprendizado, e a E17 enquanto a trilha espera a E07 (D10) (branch `roadmap/leitura-vetorial-por-poste-c`)

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E11 | Spike de treino na GPU AMD | #concluida | E01 | decisão registrada sobre onde e como treinar |
| E17 | Fechamento do cliente com servidor lento | #concluida | E14 | fechar a janela nunca destrói `QThread` viva, sem o monkeypatch de 60 s no `conftest` |
| E10 | Fábrica de rótulos contínua | #pendente | E07 | fluxo mensal com pré-marcação, leitura dupla, amostra humana e dataset por hash |
| E12 | Detector visual local | #pendente | E11, E09, E10 | detector ONNX em CPU para o resíduo, ganho medido por poste |

Janelas (ordem em que a sessão única abre as etapas, até 2 ao mesmo tempo; a elegibilidade real vem das dependências). Até 2026-11-05 elas se chamavam "ondas"; o nome agora fica reservado às ondas de tarefas do `orquestrador` e às da curadoria:

| Janela | Ao mesmo tempo | Observação |
|---|---|---|
| 1 | E14 (A), E11 (C) | concluída, ainda em duas sessões (antes da D11): as duas estão integradas em `main` |
| 2 | E06 (A) e E15 (B); depois E17 (C), quando a E15 fechar; E16 (B) quando as folhas chegarem | duas etapas abertas, com ondas de até 2 em cada ("Orçamento de máquina"). A E06 mexe em `src/` de análise, a E15 em `scripts/benchmark_ficha_poste.py` e a E17 no cliente e em `tests/conftest.py`. Com o limite de 3 etapas, o lote tende a fechar com as três e a integrar as três branches |
| 3 | E07 (A) | com E06 e E15 integradas |
| 4 | E08 (A), E10 (C) | |
| 5 | E09 (A) | com E08 e E16 integradas |
| 6 | E12 (C) | com E09, E10 e E11 integradas |

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
  - Retomada: a próxima elegível é a E05 (dependências E04 e E03 concluídas). O `.venv` do checkout principal já tem o lock de desenvolvimento com ezdxf (2026-11-04); o `.bat` roda no worktree chamado pelo caminho completo (`cmd.exe //c "<caminho>\IniciarTestes.bat"`). O worktree `.claude/worktrees/roadmap-leitura-vetorial-por-poste` e a branch estão no mesmo commit de `main`.
  - A onda final mudou a saída em casos de borda (dimensão real/indireta, identidade acima do teto) sem incrementar `modelo-desenho-v1`, porque não havia consumidor nem cache publicado; caches em `tmp/` gravados antes de 019dfa8 podem ter a identidade antiga — apague-os antes de reaproveitar.

---

## E05 — Texto por contorno de glifo — #concluida

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

- [x] Uma fixture sintética com texto convertido em contorno, a partir de uma fonte livre, produz o mesmo texto que a versão nativa da mesma folha.
- [x] Glifo ausente da tabela gera diagnóstico e não produz caractere.
- [x] Nas 16 folhas, o recall de identificador, estrutura, poste e coordenada da ficha está registrado em `tmp/` contra o baseline de E03. Nas famílias de contorno, ele é maior que o baseline.
- [x] A tabela versionada não contém recorte nem bitmap de PDF real, só assinaturas e caracteres.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- Benchmark por poste de E02 sobre as 16 folhas → relatório em `tmp/`.

**Revisão humana:** não

**Notas para o plano:** a rotulagem dos representantes de glifo reutiliza a leitura dupla adaptada em E03.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- H1 falsa, com glifos compostos ou fundidos → segmentar por subcaminho e registrar no handoff. Se a recuperação ficar abaixo do baseline numa família, essa família continua com OCR.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-04-leitura-vetorial-por-poste-e05.md`.
  - A revisão de arquitetura (opus) bloqueou nas rodadas 0 (C1: package-data do servidor; I1–I6) e 1 (N1: granularidade da cobertura OCR × glifo) e aprovou com notas na rodada 2.
  - A revisão final acrescentou notas M1/M2 ao plano: as decisões de desenho foram substituídas pelas rulings; a SKILL de curadoria entrou fora do File Structure.
- Entregas:
  - Assinatura, tabela e leitura de glifo em `drawing_model/glyph_signature.py`, `glyph_table.py` e `glyph_text.py`.
  - Tabela `adapters/analysis/data/tabela-glifos-v1.json`: 354 entradas, 74 caracteres, sha `39a80899b21d…`, parâmetros 0.08/0.02/0.48/1.5.
  - Leitor PyMuPDF `pymupdf_glyph_text.py`; texto de glifo como evidência `origem="glifo"`.
  - Analisador 1.21.0 e cache `modelo-desenho-v2`, com o sha da tabela na assinatura de capacidade.
  - Servidor com `tabela_glifos="pacote"`; `analysis.data` e `symbol_packages` no package-data dos dois pyproject.
  - CLI `scripts/curation_glifos.py` (agrupar, validar, consolidar, publicar) e benchmark `scripts/benchmark_texto_ficha.py`.
  - Modo glifo do `curadoria-leitor-visual` e seção "Rodada de glifos" do contrato de curadoria.
- Commits (731ca5c..7096b76):
  - plano 463a5b3, b978d46, 188645f, de56831, 70cc595, 31ca3d3, 92b467c, a3d8527;
  - Task 1 d8c9aef..0e3d21b; Task 2 3942ea2..b730db7; Task 3 511ae55..32753a8; Task 4 78242af..d1854f9; Task 5 8968335..978c301;
  - Task 6 14bbddc..e0aa3b9, com 5 rodadas de correção da tabela real;
  - onda final 9ce488f, 5cb7f2e, c8ebfde, 0aa6986, b82fee7, 7096b76.
- Cada tarefa passou pelo ciclo completo: desenvolvedor, testador, verificação mecânica e revisão da `revisor-seguranca`. O testador achou defeitos reais em todas as tarefas menos a 5. Na Task 6, 5 rodadas eliminaram leituras erradas afirmadas: maiúscula/minúscula de mesmo desenho, letra ausente da tabela casando outra, "11" partido.
- Revisão final (`revisor-seguranca`, opus) sobre 731ca5c..e0aa3b9: aprovado com ressalvas, sem Crítico.
  - I1: baseline E02 no HEAD.
  - I2: custo da leitura sem teto por página.
  - I3: runtime 3.13 nunca exercido.
  - Onda única: teto `LIMITE_RESOLUCOES_PAGINA = 4000`, rótulo do `publicar`, docs; o testador refez o baseline e mediu o pior caso.
  - Re-revisão (sonnet): aprovado com ressalvas, sem defeito novo.
- Gate de fechamento no 7096b76, pelos mesmos passos do `.bat` rodados um a um, porque o harness recusou `cmd.exe` neste worktree:
  - `pip check` sem quebra; ruff, format, mypy (488 arquivos), gate do cliente e complexidade (3512 funções) aprovados;
  - `pytest --basetemp --cov --cov-fail-under=85.01` → 5330 passed, 1 xfailed, cobertura 88,81%, exit 0.
- `osv-scanner` nos 6 locks: `No issues found` (166 pacotes).
- `check_test_integrity --base 731ca5c`: 7 `SEM_SOUL` e 5 `DEV_TESTE_DO_TESTADOR`, todos justificados pela revisora.
  - Os `SEM_SOUL` são commits `docs:` do orquestrador e o 42cb156, com o trailer separado por linha em branco; o histórico não foi reescrito.
  - Os `DEV_TESTE_DO_TESTADOR` são sha e contagens da tabela republicada, autorizados.
- Benchmark nas 16 folhas (`tmp/curadoria-simbologia/20261104-1055-glifos/benchmark/` do worktree, copiado para o `tmp/` principal): novo 469/543 contra base 209/543.
  - Por campo: identificador 71/77 (base 25), poste 85/85 (32), estruturas 151/213 (82), coordenada 162/168 (70).
  - Por família: electric_office_print 232/293 (base 20/293); ghostscript 48/58 (0/58); iText sem glifo; AutoCAD igual à base.
  - 1 erro afirmado, verificado visualmente como falso positivo da heurística: a referência "P2", rótulo em círculo que não sai como texto, casou com o glifo "22m", comprimento do vão, lido certo. Há 0 leituras erradas reais.
  - Baseline E02 `--native-only` no HEAD (`baseline-v003`): 0/107 postes, 16/16 medidos, igual à v002.
- **H1 — resultado: se sustenta.**
  - 11.754 candidatos; 88,2% (electric_office_print) e 96,0% (ghostscript) caem em trecho.
  - Subcaminhos por candidato: 1–3, nenhum com 4 ou mais. Grupos `composto`: 0; `fragmento`: 0; `misto`: 2 grupos (~1,1% dos glifos).
  - 4,5% saem por quadro incerto.
  - Leitura dupla cega A = B em 361/361 grupos, rodada só nas 10 folhas de contorno (6 iText e 1 AutoCAD excluídas). 347 grupos com menos de 3 membros (472 glifos) ficaram sem rótulo.
- Critérios verificados:
  - fixture de fonte livre em contorno = nativa: `test_glyph_text.py:96`, `test_pymupdf_glyph_text.py:158` e integração `test_texto_glifo_interpretacao.py` (mesmas propostas nos dois PDFs);
  - glifo ausente gera diagnóstico e não produz caractere: `test_pymupdf_glyph_text.py:215`, `test_glyph_text.py:220`, ataques em `test_glyph_text_adversarial.py` e, contra a tabela real, `test_tabela_glifos_real_ataque.py` (letras ausentes falham fechado em 11 contextos × 3 corpos × 4 rotações);
  - recall: acima, com as duas famílias de contorno acima da base;
  - tabela sem dado de folha: carga estrita (só chaves do formato, ids `gNNNN`, números relativos) e teste estrutural;
  - gate: linha "Gate de fechamento".
- Decisões para o usuário (tomadas pela opção recomendada, conforme a instrução da execução):
  - **Leitura do critério 3:** recall "presente na página", medido na própria amostra que gerou a tabela, sem amostra humana.
  - **`espaco` 0,48, sem faixa de dúvida.** Espaços reais entre 0,357 e 0,48 h saem colados ("24m VR:24m" → "24mVR:24m"). A faixa derrubava o poste de 85 para 40 sem tirar erro.
  - **Opção A — falhar fechado entre maiúscula e minúscula de mesmo desenho:** −9 acertos (estruturas −7, coordenada −2) em troca de 0 letras trocadas afirmadas.
  - **Âncora de escala estreita.** Trecho todo em altura-x feito só de letras com par de mesmo desenho ("sov", "cos") pode sair em maiúsculas; afeta só texto livre, sem teste.
  - **Orçamento de 5 s por folha estourado** em 6 de 9 folhas de contorno (até ~12 s).
  - **Teto de 4000 conta instâncias** (glifos × quadros), porque a memória só poupa cópias idênticas (`xfail(strict=True)` em `test_glyph_text_orcamento_ataque.py`). Uma folha com ~1,8× os glifos da mais pesada sai sem texto de glifo, com `analise.glifos_limitados`. Um PDF hostil ainda custa ~62 s por página no worker único.
  - **`symbol_packages` passou a ir no wheel do servidor.** Também entraram o allow novo `curation_glifos *` em `.claude/settings.json` e o modo glifo do leitor visual.
  - **Corte `--min-membros 3`** e exclusão das folhas iText e AutoCAD da rodada de glifos.
  - **A folha AutoCAD emite `analise.glifos_desconhecidos`** (756 formas): é ruído para o usuário do servidor.
  - **Python 3.13 do container não verificado:** não há runtime nesta máquina e o Docker está parado. Rode os testes `test_glyph_*` e `test_tabela_glifos_real_ataque.py` na imagem antes de publicar a imagem nova.
  - **`IniciarTestes.bat` real:** rode-o em `main` depois do merge, porque aqui ele foi substituído pelos mesmos passos.
- Notas para a próxima etapa:
  - **Memória tolerante na resolução**, com balde grosso e igualdade a menos de ε. Ela permite recalibrar o teto para formas distintas e tira o `xfail`. Corrija também o comentário e a docstring do teto (`glyph_text.py:195-198`, `:390`), que ainda dizem "resoluções distintas" e "~2×".
  - **Recuperar os −9 acertos:** ancorar a escala do trecho nos algarismos ou reescalar as minúsculas no `publicar`. As duas exigem refazer o `agrupar`.
  - **Altura típica:** é a mediana das duas escalas (`glyph_text.py:534`, `:619`). Uma republicação que inverta a maioria de um algarismo pode partir "11"; os testes da tabela real pegam isso.
  - **`test_tabela_glifos_real_ataque.py` fixa o sha e as contagens** da tabela. Toda republicação exige atualizá-los, e o `publicar` tem de reproduzir os bytes.
  - **Trecho com mais de 64 glifos** cai sem diagnóstico. A carga aceita caractere de controle ou invisível, que o `validar` recusa. `agrupar --rodada` e `publicar --saida` gravam em qualquer caminho novo.
  - **Escrita fora de `tmp/` durante a etapa:** o baseline acha os PDFs por `raiz_corpus` relativo e exigiu copiar os PDFs para `examples/` do worktree, cópia apagada em seguida. Uma `baseline-v002` com falhas foi apagada antes de ser regravada.
  - **Retomada:** a próxima elegível é a E06. A rodada de glifos (`20261104-1055-glifos`) e a cópia da rodada E03 estão no `tmp/curadoria-simbologia/` do worktree e foram copiadas para o `tmp/` principal.

---

## E14 — Gate de testes paralelo — #concluida

**Objetivo:** a suíte inteira roda em processos paralelos no gate e nas souls, sem perder teste nem cobertura. O `main` volta a passar no `.bat` (decisão D6).

**Por que agora:**
- a suíte leva 26 min em série e roda antes de cada commit do desenvolvedor e no fim de cada tarefa do testador;
- a E05 teve 45 commits desses;
- o `main` reprova hoje num teste de tempo de parede.

Toda etapa seguinte paga esse custo.

**Dependências:** E05.

**Escopo:**
- **Teste que reprova o `main`:** a asserção de tempo de parede de `test_glyph_text_orcamento.py::test_pagina_hostil_acima_do_teto_de_resolucoes_e_limitada_em_tempo_limitado` vira contagem de trabalho determinística. Faça o mesmo nos demais testes que medem tempo de parede, se não aguentarem a carga paralela.
- **Paralelismo:**
  - `pytest-xdist` (MIT) no extra `dev` e em `requirements-development.lock`;
  - a invocação do pytest no `IniciarTestes.bat` em processos paralelos, com a cobertura combinada e o mínimo de 85,01%;
  - o comando paralelo documentado no `CLAUDE.md`.
- **Isolamento** dos testes que não aguentam processo paralelo. Se algum não puder ser isolado, ele vai para uma passada serial no mesmo `.bat`, com a cobertura acumulada.
- **Scripts de corpus:** `--processos N` em `scripts/benchmark_texto_ficha.py` e `scripts/drawing_model_report.py`, com saída idêntica à serial.

**Fora de escopo:**
- `scripts/benchmark_ficha_poste.py` (E15);
- mudar comportamento do produto;
- remover, pular ou desmarcar testes;
- mudar as souls (D8).

**Critérios de aceite:**

- [x] O total de testes coletados pelo `.bat` depois da etapa é ≥ o de antes. Nenhum teste fica de fora por marcador ou `deselect`.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`, com cobertura ≥ 85,01%.
- [x] O passo pytest do `.bat` leva ≤ 8 min nesta máquina. O tempo antes e depois e as 15 durações mais lentas (`--durations=15`) estão no handoff.
- [x] Três execuções paralelas seguidas da suíte inteira saem verdes, e uma execução serial sai verde.
- [x] Os scripts de corpus com `--processos 4` produzem saída byte a byte igual à serial numa fixture sintética de várias folhas.
- [x] `.venv/Scripts/python.exe -m pip check` sem quebra, e `osv-scanner` no lock de desenvolvimento sem vulnerabilidade nova.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- Execução repetida da suíte (critério 4), com as saídas na revisão final.

**Revisão humana:** não

**Notas para o plano:**
- Há 9 arquivos de teste com `perf_counter` ou `time.monotonic` (grep de 2026-11-04).
- Riscos de isolamento conhecidos:
  - Qt offscreen (`tests/conftest.py`);
  - o `--basetemp` do `.bat`;
  - `tests/unit/test_dependency_locks.py` e `test_project_scripts.py`, que leem os locks.
- O teto de ~3h vale aqui também: a meta de 8 min é decisão do arquiteto, e o usuário pode ajustá-la.
- Esta etapa não usa laboratório.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- O paralelismo esconde ou cria teste intermitente → critério 4 e a passada serial. Teste intermitente achado é corrigido, nunca marcado para repetir.
- Uma fixture compartilhada falha só em processo paralelo → isolamento por `tmp_path` ou passada serial, registrada no handoff.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-05-leitura-vetorial-por-poste-e14.md`. Revisão de arquitetura (opus): bloqueado na rodada 0 (I1: `.bat` real só pelo espelho; I2: `pico_memoria_bytes` na igualdade), aprovado com notas na rodada 1.
- Relógio: de cce8fda (00:31) ao `#concluida` (04:59): 4h28, dentro do limite de 4h30, que quase foi atingido no fechamento. A parada foi resolvida pela opção recomendada da instrução da execução: continuar até fechar, porque todas as tarefas estavam feitas.
- Entregas:
  - Asserções de tempo de parede viram contagem de trabalho: `resolver_glifo` no teste hostil, renomeado para `…em_trabalho_limitado`; comparações em `_caixas_se_encostam`. Os prazos de espera em `tests/server` e `tests/integration` foram alargados.
  - `pytest-xdist==3.8.0` e `execnet==2.1.2` (MIT) entram só no extra `dev` e em `requirements-development.lock`. O `.bat` roda `python -m pytest -n auto … --cov --cov-fail-under=85.01 --durations=15`, numa passada só; nenhum teste precisou de passada serial. `-n` nunca entra em `addopts`.
  - Os ids de `test_project_document_api.py` ficaram determinísticos (os `uuid4` quebravam a coleta do xdist). Os pytest em subprocesso de `test_dependency_locks.py` ganharam `--basetemp`.
  - `--processos N` em `scripts/benchmark_texto_ficha.py` e `scripts/drawing_model_report.py`: `ProcessPoolExecutor` com `pool.map` na ordem serial, tabela validada no processo principal (exit 2), amostras e `fontes` gravadas em série.
  - **Correção de produto (exceção à restrição "src/ não muda"):** 37bc2ee em `src/zeny_project_handler_client/ui/project_panel.py`.
    - Causa: depois de `shutdown_polling()` + `restart_polling()`, o `destroyed` tardio da thread de observação antiga zerava as referências da thread nova. O fechamento seguinte destruía uma `QThread` viva (qFatal, 0xC0000409), o que derrubava o worker do xdist em `test_mvp_ui.py::test_search_response_is_discarded_after_reconnection_or_close[True]`. Reprovou 2/2 `.bat` no 27d76d5.
    - Correção: só a thread atual limpa as referências. São 8 linhas, com testes de regressão em subprocesso (`test_project_panel_polling_restart*.py`).
- Commits (425104a..010d5f1):
  - roadmap e plano: cce8fda, b389e57, 11883c1, b8a4fc6;
  - Task 1: 91bc22c, 7d8899a;
  - Task 2: 9679153, 77dc135, 69a7a2f, da66c39, f83844a, 37bc2ee, 1b27f91, 13c5496;
  - Task 3: 64807c5, 27d76d5;
  - onda final: 010d5f1.
- Cada tarefa passou por desenvolvedor, testador, verificação mecânica e revisão da `revisor-seguranca`, todas aprovadas.
  - Task 2: 2 rodadas de correção. Na rodada 1, o teardown da fábrica de janelas joinava a thread de observação por só 1 s. Na rodada 2, com desenvolvedor novo (opus), saiu a causa real acima.
  - O Important da revisão da Task 2 (teste que abortava o processo em vez de falhar legível) virou teste em subprocesso.
- Revisão final (`revisor-seguranca`, opus) sobre 425104a..13c5496: aprovado com ressalvas, sem Crítico.
  - I-1: o `closeEvent` do cliente espera a observação por só 1 s. O monkeypatch de 60 s do `conftest` encobre isso; agora está comentado (010d5f1) e vai para as decisões.
  - I-2: o parked do aborto sob carga fica aberto.
  - Re-revisão da onda final (opus, 13c5496..010d5f1, com a serial anexada): **aprovado**. I-1 e I-2 foram resolvidos nos termos acima, e o diff não trouxe nada novo.
- Critérios verificados:
  1. Antes: 5331 node IDs coletados em 425104a. Depois: 5373 itens no `.bat`. Ficam 14 ausentes, todos mapeados: 13 ids `uuid4` aleatórios de `test_every_stage_three_route_requires_bearer` (17 casos antes e depois) e 1 renomeado. Nenhum `-m`, `-k` ou `--deselect`.
  2. `cmd.exe //c IniciarTestes.bat` no 13c5496 → `RESULTADO FINAL: APROVADO`: 5372 passed, 1 xfailed, cobertura 88,80%. Os 2 `.bat` anteriores, no 27d76d5, reprovaram pelo worker morto, e o desenvolvedor rodou 3 `.bat` aprovados no 37bc2ee. O harness recusa `cmd.exe` no modo isolado, por isso o orquestrador saiu do modo worktree (`ExitWorktree keep`) e rodou o `.bat` pelo caminho absoluto, na branch `roadmap/leitura-vetorial-por-poste`.
  3. Passo pytest: 1578 s em série (2026-11-04) contra 189–233 s em paralelo (20 workers, `-n auto`).
     - As 15 durações mais lentas no `.bat` final, todas de 20 a 55 s:
       - `test_tabela_glifos_real_ataque` (ruído de caixa 54,7 s, pares de algarismos 27–30 s);
       - `test_glyph_table` (ruído até a tolerância, 20–44 s);
       - `test_pymupdf_glyph_text_ataque` (dezenas de milhares de preenchimentos, 43,0 s);
       - `test_curation_backlog` (pistas paralelas, 29–42 s);
       - `test_glyph_text` (varredura, 41,1 s);
       - `test_glyph_text_orcamento` (35,2 s);
       - `test_project_http_gateway` (33,5 s).
     - O limite do relógio é a cauda desses testes de glifo, não o número de workers.
  4. Três execuções paralelas verdes seguidas: os 3 `.bat` do desenvolvedor no 37bc2ee (5371 passed; 189,84, 230,48 e 194,38 s; cobertura 88,80–88,81%), mais o `.bat` final e a suíte do testador no 1b27f91 (5372 passed). Serial `-n 0 --cov` no 37bc2ee: 5371 passed, 1 xfailed, 1154 s, cobertura 88,81%. A cobertura paralela (88,80%) e a serial (88,81%) diferem 0,01 p.p.
  5. `test_processos_4_produz_a_mesma_saida_que_a_serial` nos dois scripts. JSON e MD são comparados depois de zerar só `tempo_*` e `pico_memoria_bytes`, que medem o processo (ruling I2), e os PNG byte a byte. Outros 20 ataques ficam em `test_processos_corpus_ataque.py`.
  6. `pip check`: "No broken requirements found". `osv-scanner --lockfile=requirements.txt:requirements-development.lock`: 58 pacotes, "No issues found".
- Decisões do usuário em 2026-11-05, por entrevista, todas pela opção recomendada:
  - integração: merge local em `main`;
  - exceção em `src/`: aceita;
  - I-1: virou a etapa E17.
- Decisões para o usuário (tomadas pela opção recomendada, conforme a instrução da execução):
  - **Exceção em `src/`:** a correção do ciclo de vida da `QThread` de observação (37bc2ee) entrou nesta etapa, embora o escopo dissesse "src/ não muda". Sem ela, o gate paralelo reprovava 2/2. O comportamento só muda no caso defeituoso.
  - **Defeito de produto estacionado (I-1):** com o servidor lento (> 1 s), fechar o cliente pode abortar o processo. `MainWindow.closeEvent` chama `shutdown_polling()` com 1000 ms e ignora o retorno. Nos testes, o monkeypatch de 60 s do `conftest` encobre isso. Proposta: uma etapa curta que faça o fechamento esperar ou cancelar a leitura de sessão.
  - **Aborto sob carga saturada (I-2), provavelmente resolvido:** a rodada 1 viu workers Qt morrerem sob 60 processos de carga, inclusive em série, em mais de um teste. A causa achada explica o caso do gate. Os outros não foram reproduzidos de novo depois da correção, e o risco residual fica aberto.
  - **"Byte a byte" do critério 5:** a comparação zera `tempo_*` e `pico_memoria_bytes`, porque duas execuções seriais já diferem nesses campos.
  - **`test_glyph_text.py`:** a asserção de parede virou `process_time() < 5.0`, tempo de CPU, em vez de contagem de trabalho.
  - **`IniciarTestes.bat` com `-n auto`:** usa todos os núcleos (20 aqui), e máquinas menores ficam mais lentas, mas corretas.
- Notas para a próxima etapa:
  - Minors adiados:
    - `max_workers` sem teto de 61 no Windows (`--processos` ≥ 62 com ≥ 62 PDFs dá traceback);
    - teste de ordem fraco contra `as_completed`;
    - spawn real do `benchmark_texto_ficha` sem teste de CLI;
    - cenários de reinício com `sleep` de 1,2 e 1,6 s contra o prazo padrão de 1000 ms;
    - comentários sem acento em `conftest.py` e `test_panel_scroll.py`;
    - helpers de pool quase duplicados nos dois scripts.
  - O aviso `_readerthread` (`PytestUnhandledThreadExceptionWarning`) em `test_drawing_model_dxf_adversarial.py::test_juncao_dentro_de_tmp_apontando_para_fora_e_recusada`, com `PYTHONUTF8=1`, é anterior à etapa.
  - O `--basetemp` precisa ser curto: um basetemp longo quebra `test_atomic_files.py`.
  - Retomada: a próxima da Trilha A é a E06 (depende de E05 e E14). Pela tabela de ondas, a onda 2 (E06, E15) começa com a E14 integrada em `main`. Integre esta branch antes da próxima execução. A E07 depende da E15 (Trilha B) integrada em `main`.

---

## E17 — Fechamento do cliente com servidor lento — #concluida

**Objetivo:** fechar a janela do cliente nunca destrói uma `QThread` viva. Hoje, com o servidor lento, o processo aborta com qFatal (0xC0000409).

**Por que agora:**
- é o achado I-1 da revisão final da E14: `MainWindow.closeEvent` (`src/zeny_project_handler_client/ui/main_window.py:702-705`) chama `ProjectPanelWidget.shutdown_polling()` com o prazo padrão de 1000 ms e ignora o retorno;
- se a leitura de sessão (`gateway.session()`, HTTP) demora mais de 1 s, a janela é destruída com a thread de observação viva;
- nos testes, o monkeypatch de 60 s do `application_factory` (`tests/conftest.py`) encobre o defeito.

**Dependências:** E14.

**Escopo:**
- O fechamento espera ou cancela a leitura de sessão antes de destruir o painel. Exemplos: adiar a destruição até a thread terminar, ou cancelamento cooperativo da observação. Vale também para as outras `QThread` do cliente que o fechamento encerra com prazo.
- Remover o monkeypatch de 60 s do `conftest`, ou reduzi-lo ao padrão, com o teste de teardown em subprocesso ainda verde.
- Teste de regressão em subprocesso, no padrão de `tests/integration/test_application_factory_teardown.py`: com o servidor lento (> 1 s), fechar a janela termina sem abortar.

**Fora de escopo:** servidor, contratos e API; o ciclo de vida já corrigido na E14 (37bc2ee).

**Critérios de aceite:**

- [x] Teste em subprocesso que fecha a janela com uma leitura de sessão de 1,6 s: vermelho (código 3221226505) antes, verde depois, sem o monkeypatch de 60 s.
- [x] O fechamento não trava a UI além do necessário. O prazo máximo de espera e o comportamento ao estourá-lo ficam documentados no plano.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:**
- Etapa curta, de ~1h. O mecanismo e os testes em subprocesso já existem (handoff da E14, I-1 e I-2).
- Roda na trilha C (D10). A mesma sessão a abre quando a E15 fechar, em paralelo com a E06. Toca o cliente (`src/zeny_project_handler_client/`) e `tests/conftest.py`: confira contra o plano da E06 (arquivos disjuntos). Nenhuma etapa depende da E17.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Esperar a thread sem limite congela o fechamento com o servidor fora do ar → cancelamento cooperativo ou prazo com destruição adiada, nunca destruir a thread viva.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-05-leitura-vetorial-por-poste-e17.md`.
  - A revisão de arquitetura (opus) bloqueou nas rodadas 0 e 1 e aprovou com notas na rodada 2:
    - rodada 0: C1 (pedido invalidado pela perda de conexão) e I1–I6;
    - rodada 1: N1 (o `shutdown_polling` da perda de conexão cancelava o pedido) e N2 (thread de outro painel como última viva).
- Relógio: de 8e54de2 (18:06 de 2026-11-05) ao commit `#concluida` (01:10 de 2026-11-06), 7h04, acima do orçamento de ~3h:
  - até o fim da E15, a etapa correu em paralelo com a E06.1;
  - a Task 3 sozinha levou ~3h, porque o turno do desenvolvedor acabou sem commit enquanto as rodadas de estabilidade rodavam em segundo plano, e ele teve de ser retomado.
- Entregas:
  - `ProjectPanelWidget.pedir_encerramento(timeout_ms)`, `rede_ativa()` e o sinal `rede_encerrada`:
    - o encerramento é por estado, com um token próprio que só o `restart_polling()` cancela;
    - os registros `remote_read` e `project_search` têm notificadores `terminou` emitidos depois do `discard` e contam só threads com `isRunning()`.
  - `MainWindow.closeEvent` espera até 1000 ms. Se a rede continua ativa, ele adia o fechamento com a janela visível, desabilitada e com o texto "Encerrando…". Detalhes:
    - o fechamento conclui no `rede_encerrada` (slot de uso único) ou pelo timer de reconferência de 250 ms;
    - durante o adiamento, `set_connection_available` não faz nada;
    - o `close()` do `finally` de `bootstrap.run()` não libera os recursos de novo.
  - `restart_polling()` com a observação antiga ainda viva adia o reinício até o `finished` dela, controlado por geração (R-E17-11). Era um defeito real: o painel ficava sem observação depois de reconectar.
  - `tests/conftest.py`:
    - sai o monkeypatch `_esperar_threads_do_painel_ate_o_fim` de 60 s;
    - o descarte da fábrica espera o fechamento adiado antes de `release_resources()`; a liberação com rede viva era outro defeito real, com vermelho provado.
  - Helpers de teste: `tests/janela_fechamento.py::esperar_fechamento` e `tests/cenario_subprocesso.py`, que monta o ambiente e o comando dos subprocessos e corrige o `PYTHONPATH` em worktree de tarefa.
- Commits (2dd743e..9993ec7, mais o merge da `main` 55e934f e o fechamento):
  - roadmap e plano: 8e54de2, 1a3bb79, 089fa0d, 7278c6d, 42708eb;
  - Task 1: cb81f38, b01d8d1, 6023e06;
  - Task 2: bdec2a7, 9e0fb81;
  - Task 3: 831aa05, 7cd20c2, 5715ace;
  - Task 4: f006d1f, de7aeec, 8fc3463;
  - onda final: d3fff32, 6d93c89, 9993ec7.
- Ciclo das tarefas: as 4 tarefas eram de risco alto. Cada uma passou por desenvolvedor, testador, verificação mecânica e revisão da `revisor-seguranca`, todas aprovadas.
  - O testador da Task 1 achou o defeito do reinício, corrigido na rodada 1.
  - A Task 4 não reproduziu o intermitente sob carga: 0/10, 0/25 com a suíte simultânea e 0/10 em 17 arquivos com `faulthandler_timeout=120`. O registro fica como "não reproduzido, monitorar".
- Revisão final (`revisor-seguranca`, opus, 2dd743e..8fc3463): aprovado com ressalvas, sem Crítico.
  - I1: os testes de regressão do reinício adiado estavam sem dono. Foram escritos na onda única (d3fff32), com mutações vermelhas.
  - A re-revisão da onda (sonnet) deu tudo ADDRESSED, sem quebra nova.
  - Integridade `--base 2dd743e`: 7 `ASSERCAO_REMOVIDA`, justificadas. São o mesmo `assert panel.shutdown_polling(...)` com prazo explícito de 60 s, igual ao do monkeypatch removido.
  - osv-scanner nos 7 `requirements*.lock` (189 pacotes): `No issues found`.
- Critérios verificados:
  1. `test_main_window_fechamento_servidor_lento.py::test_fechar_com_leitura_de_sessao_de_1_6_s_nao_aborta` roda em subprocesso, sem o conftest. Contra o código anterior saiu com 3221226505 (relatório da Task 2) e hoje sai com 0. A saída é por `exec()` real. `git grep -n "_esperar_threads_do_painel_ate_o_fim" tests/` não acha nada.
  2. Prazo e estouro estão documentados na docstring de `MainWindow.closeEvent` e no plano (R-E17-1/2). A janela espera até 1000 ms e depois adia, visível e desabilitada. Com o servidor mudo, o teto real fica em torno de 60 s (30 s de timeout × 2 tentativas). Com um servidor que goteja bytes, não há teto, e não há `os._exit`.
  3. `.bat`: `cmd.exe //c IniciarTestes.bat` em 55e934f (C com a `main`) → `RESULTADO FINAL: APROVADO`, com 6949 passed, 3 xfailed, cobertura de 88,94% e 186 s.
- Decisões para o usuário (já tomadas e revisáveis):
  - R-E17-2, sobre a espera sem teto com um servidor que goteja bytes: a janela fica em "Encerrando…" até o gateway desistir. As alternativas descartadas foram cancelar o HTTP pelo socket, porque mudaria o gateway inteiro, e `os._exit` com teto. Se isso incomodar em campo, a saída é o cancelamento cooperativo no gateway.
- Notas para a próxima etapa:
  - Ficaram parked (R-E17-14) três `wait()` sem teto no cliente, sem causa comprovada: `portability_panel.py:401`, `pdf_viewer.py:857` e `pdf_rendering.py:258`. São candidatos se um travamento voltar.
  - O travamento de 18 min que o testador da Task 3 viu uma vez não foi reproduzido. Se voltar, rode com `-o faulthandler_timeout=120` para obter o traceback.
  - O teardown da fábrica lê os privados `_fechamento_adiado` e `_fechamento_concluido`. Uma propriedade pública somente leitura, por exemplo `fechamento_pendente`, desacoplaria a fixture.
  - Os cenários de polling ainda dormem de verdade (5 a 10 s por subprocesso). Um gateway controlado por evento deixaria a suíte mais rápida.

---

## E06 — Símbolos sobre o modelo de desenho (dividida em E06.1–E06.3)

**Objetivo:** reconhecer estais, para-raios MT/BT, transformadores e demais símbolos do inventário a partir dos grupos do modelo de desenho, usando os pacotes declarativos.

**Por que agora:** símbolos são a segunda metade da ficha. Os grupos do modelo de desenho dão geometria limpa aos pacotes.

**Dependências:** E05, E14.

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

**Notas para o plano:**
- Os limiares por classe e por família, ajustados contra as 16 folhas, são candidatos a laboratório. Na E05, 5 rodadas desse ajuste dentro do ciclo custaram ~7h45.
- Na mesma sessão, a E15 (trilha B, em `scripts/benchmark_ficha_poste.py`) e depois a E17 (trilha C, no cliente e em `tests/conftest.py`) ficam abertas junto com esta etapa: não toque nesses arquivos.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Pacote que memoriza a folha → exigir fixture sintética autoral, e o verificador procura coordenadas ou hashes de folhas reais.

**Divisão (2026-11-05, orquestrador):**
- **Por que dividir:** o levantamento do código estimou a etapa em 8 a 10 h, mais o laboratório das gramáticas novas. Os pacotes não têm nenhuma das classes da ficha: das 179 referências de símbolo da E03, 177 são de classes sem variante habilitada. Os detectores dedicados só rodam no runner opt-in, e o modelo de desenho não entra no job. Pelo "Orçamento", a etapa vira três subetapas completas.
- **Como os critérios se repartem:**
  - **E06.1**, medição e base do modelo. Leva o baseline do analisador atual do critério 2. A ampliação dos pacotes foi para a E06.3 (R-E06.1-0 do plano).
  - **E06.2**, método sobre o modelo com as gramáticas atuais, ligado no runner.
  - **E06.3**, ampliação dos pacotes e gramáticas das classes da ficha, com laboratório. Leva os critérios 2 ("maiores que os do analisador atual") e 3 (auditor com 0 erros e as variantes novas) e H2.
  - O critério 1 (fixtures sintéticas) vale nas três.
- **Dependência:** a E07 passa a depender da E06.3.

Rulings da divisão, registradas no ledger da E06.1:
- **"Analisador atual" do critério 2:** é a união do runner sem raster (legado, estais, transformadores e pacotes), porque é o que o método novo substitui. O analisador padrão emite só 3 classes.
- **Casamento:** o critério principal é o centro da predição dentro da caixa da referência, e IoU ≥ 0,5 (protocolo E02) fica como diagnóstico. O estai sai como polilinha fina e a ficha anota caixa, então com IoU ele dá 0 de 56 por construção. A precisão medida contra a ficha é um limite inferior, porque a ficha só anota símbolo associado a poste.
- **Onde o método liga:** no `SymbolCompositionRunner` (opt-in), como os métodos atuais. A troca do analisador padrão é da E09.
- **Detectores dedicados:** são o "atual" a superar e saem na E09.

**Evidências e handoff:** ver as subetapas.


---

## E06.1 — Medição de símbolos e base do modelo — #concluida

**Objetivo:** medir a detecção de símbolos do analisador atual contra as fichas de referência da E03 e preparar a base do método sobre o modelo de desenho: a página do modelo, com o índice cru das primitivas.

**Por que agora:** é a primeira subetapa da E06 (ver "Divisão"). Sem a medição, nenhuma gramática nova prova ganho.

**Dependências:** E05, E14. O relógio começa no commit `#em-andamento` da E06 (dfc06e7).

**Escopo:**
- **Benchmark diagnóstico** `scripts/benchmark_simbolos_ficha.py`: precisão e recall por classe, família e folha contra os símbolos das fichas. Mede o "atual" (união do runner sem raster), nos dois critérios de casamento, com `--processos N`.
- **Página do modelo de desenho** a partir da página aberta, com o mapa caminho → índice cru de `get_drawings(extended=True)`, sem mudar o cache nem `VERSAO_MODELO_DESENHO`.
- **Guarda** contra memorização de folha real nos pacotes.

**Fora de escopo:** mudar os pacotes, as gramáticas e o método sobre o modelo (E06.2 e E06.3); ligar algo no runner ou no analisador padrão.

**Critérios de aceite:**

- [x] Fixtures sintéticas positivas e negativas para o benchmark e para a página do modelo.
- [x] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros (pacotes inalterados).
- [x] O baseline diagnóstico do analisador atual nas 16 folhas está em `tmp/`, com precisão e recall por classe, família e folha nos dois critérios. O handoff traz os totais.
- [x] A guarda passa: os pacotes não têm coordenada, hash nem nome de folha real.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- Benchmark de símbolos nas 16 folhas, rodado em paralelo → relatório em `tmp/`.

**Revisão humana:** não

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Uma falha de detector baixa a base que a E06.3 precisa superar → o método que falha numa folha sai dos totais, com registro.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-05-leitura-vetorial-por-poste-e06-1.md`.
  - Revisão de arquitetura (opus): bloqueou na rodada 0 e aprovou com notas na rodada 1.
  - Na rodada 0, I1–I4 vinham da ampliação dos pacotes: `negative_examples`, `coverage_matrix_e16`, mudança visível na revisão e nas exportações. A ampliação foi adiada para a E06.3 (R-E06.1-0). O I5 era falha de detector silenciosa.
  - O plano ganhou duas emendas durante a execução: Task 4 (R12) e Task 5 (R14). A Task 4 foi reclassificada para `Risco: alto` (R13).
- Relógio: de dfc06e7 (15:56) até o commit `#concluida` (18:40 de 2026-11-05): 2h44). Correu em paralelo com a E15 e, no fim, com a E17.
- Entregas:
  - `scripts/benchmark_simbolos_ficha.py`, o benchmark diagnóstico de símbolos contra as fichas da rodada:
    - método `atual` (união do runner sem raster);
    - critérios `centro` (principal) e `iou` (diagnóstico);
    - escopo de classe, regiões e postes pendentes fora do FP;
    - falha de método fora dos totais e bloco `comparacao` só com as folhas comuns;
    - `--processos N`;
    - guarda lexical de `avaliacao-cega` antes de qualquer I/O, inclusive no diretório da rodada.
  - `pagina_modelo_com_indices(pagina, indice, tabela=None)` em `pymupdf_drawing_model.py`: a página do modelo vem da página aberta, com o índice cru de `get_drawings(extended=True)` de cada caminho. O cache, o formato e `VERSAO_MODELO_DESENHO` não mudam.
  - `tests/unit/test_symbol_packages_sem_memorizacao.py`, a guarda contra coordenada, hash, `.pdf` e nome de folha nos pacotes, em valores e chaves.
  - Correção do teste intermitente do `job_store` (R12):
    - a causa era o tique de 15,6 ms do relógio do Windows, que empatava o `updated_at`;
    - o `prune` agora desempata por `updated_at, created_at, rowid`;
    - o relógio monotônico global da 1ª tentativa foi removido (R15).
  - As asserções de razão de tempo de parede do modelo viraram contagem de trabalho, em `test_drawing_model_geometry*.py` (R14 e testador de etapa).
- Commits (2dd743e..d875caa, mais o fechamento):
  - roadmap e plano: dfc06e7, e7de2a4, 82916cc, dc433d6, 8039d12, 92df7f7, c32a9c4;
  - Task 1: ef81bba, e421ea0, cf7f949;
  - Task 2: 473844c, bb4b7cd;
  - Task 3: 905f3e9, 568f185;
  - Task 4: série 53d7f4a..ed2ce30, integrada como e37a495;
  - Task 5: 66bbf75;
  - testador de etapa: ffb8be9, 62523c3, dc97548;
  - onda final: d875caa.
- Ciclo por tarefa: desenvolvedor, testador nas tarefas de risco alto, verificação mecânica e revisão da `revisor-seguranca`. Todas aprovadas.
  - O testador achou defeitos reais nas Tasks 1 e 4:
    - a guarda de `avaliacao-cega` era burlada por ponto final no Windows;
    - `sanear` deixava vazar caminho UNC;
    - o `prune` não desempatava `updated_at` vindo do banco.
  - O testador de etapa achou D1–D3 (ver Decisões).
- Revisão final (`revisor-seguranca`, opus, 2dd743e..dc97548): aprovado com ressalvas, sem Crítico.
  - I1, a guarda que não conferia o diretório da rodada, foi corrigido na onda única d875caa.
  - I2, amarrar D1 à E06.2, está aqui e nos riscos da E06.2.
  - Re-revisão da onda: I1 e o minor da docstring ADDRESSED, sem quebra nova; minors: falta teste ponta a ponta de rodada com nome parecido, e o vigia não cobre os.scandir/listdir/iterdir.
- Critérios verificados:
  1. Fixtures sintéticas positivas e negativas.
     - Benchmark: rodada sintética com TP no aterramento desenhado e FN na referência sem desenho, mais o ataque.
     - Página do modelo: `clip`/`group` intercalados e aninhados, rotação, CropBox e página sem desenhos.
  2. `scripts.audit_symbol_packages` → `errors []` (habilitadas 22, pendentes 343). Os pacotes não mudaram.
  3. Baseline diagnóstico do "atual" nas 16 folhas, em `tmp/e06/simbolos-atual/simbolos-ficha.{json,md}`, com `--processos 6`, 190 s e 0 falhas:
     - **centro**, geral: tp 131, fp 58, fn 48, precisão 69,3%, recall 73,2%.
     - **iou**, geral: tp 119, fp 70, fn 60, precisão 63,0%, recall 66,5%.
     - Por classe (centro, tp/fp/fn):
       - ATERRAMENTO 41/32/2; ESTAI 64/2/12; TRANSFORMADOR 14/2/0; PARA_RAIOS_MT 10/4/3;
       - PARA_RAIOS_BT 0/0/10; EQUIPAMENTO_INTERRUPCAO 0/0/20; PONTO_CONEXAO 2/18/0; CONECTOR 0/0/1.
     - Por classe (iou, tp/fp/fn):
       - ATERRAMENTO 33/40/10; ESTAI 63/3/13; TRANSFORMADOR 14/2/0; PARA_RAIOS_MT 7/7/6;
       - PARA_RAIOS_BT 0/0/10; EQUIPAMENTO_INTERRUPCAO 0/0/20; PONTO_CONEXAO 2/18/0; CONECTOR 0/0/1.
     - Por família (centro, tp/fp/fn): electric_office_print 60/15/24, itext 47/38/19, ghostscript 24/4/5, autocad 0/1/0.
     - Fora das regiões: 35. Perto de poste pendente: 53. Duplicatas: ESTAI 3. Os números por folha e o tempo por folha estão no `.json`.
  4. A guarda passa: `test_pacotes_reais_passam_na_guarda` verde. `git grep -n "PROJETO DE REDE NS"` só acha as linhas que citam o critério.
  5. `.bat`: `cmd.exe //c IniciarTestes.bat` em d875caa → `RESULTADO FINAL: APROVADO`: 6598 passed, 3 xfailed, cobertura 88,86%, 197 s.
  - Suíte inteira `-n 10 --cov` em d875caa: 6598 passed, 3 xfailed (1 preexistente e 2 da R18), cobertura 88,82%.
  - `osv-scanner` nos 7 locks: `No issues found`. Nenhum lock mudou.
  - `check_test_integrity --base 2dd743e`: os apontamentos foram todos justificados na revisão final.
    - 7 `SEM_SOUL` em commits docs do orquestrador. Até aqui, os trailers saíam separados por linha em branco; os commits novos já trazem o trailer no último parágrafo.
    - `TESTE_REMOVIDO` e `ASSERCAO_REMOVIDA` vêm das conversões de tempo para contagem. O `len(...) == 200` foi preservado.
    - 1 `SKIP_ADICIONADO`, o alias NTFS, que só existe no Windows.
- Decisões para o usuário (tomadas pela opção recomendada):
  - **"Atual" = união do runner sem raster** (R6/R-E06.1-1): legado, estais, transformadores e pacotes, sem passar por `reconcile_symbols`. O raster do perfil `balanced` ficou fora. É a base que a E06.3 tem de superar.
  - **Critério principal `centro`**, com tolerância de 0,005, e IoU como diagnóstico (R7/R-E06.1-2). Isso substitui, neste gate, o `symbols-e02-v1` só com IoU aprovado na E02. A precisão contra a ficha é um limite inferior.
  - **Divisão da E06** em E06.1–E06.3 (R5), com a E07 passando a depender da E06.3.
  - **Ampliação dos pacotes adiada para a E06.3** (R9): com variantes só `pending`, ela quebraria o fechamento da curadoria e mudaria a tabela de suporte e as exportações.
  - **Tarefas fora do escopo de símbolos**, por estabilidade do gate:
    - Task 4: teste intermitente do `job_store` (R12/R13/R15). Mexeu em `src/zeny_project_handler_server/job_store.py`, só no `ORDER BY` do `prune`.
    - Task 5 e testador de etapa: razões de tempo de parede viraram contagem (R14).
  - **D1 como `xfail(strict=True)`** (R18): `reconstruir_polilinhas` é quadrática em nó de grau alto, em forma de estrela ou com segmento repetido. Hoje o servidor não passa por ela. Corrigir antes da E06.2 ligar o modelo no runner é pré-condição.
- Decisão de system design que espera o usuário (entrevista no fim do lote, antes do plano da E06.2):
  - **Onde o método de símbolos sobre o modelo liga** (R8/R10): só no `SymbolCompositionRunner` opt-in, como os métodos atuais, ou também no analisador padrão. A escolha define de onde a E07 lê os símbolos.
- Notas para a próxima etapa (E06.2):
  - O levantamento do código feito para planejar a E06 (motor declarativo, métodos atuais, modelo de desenho, custo, riscos, hipóteses H-A/H-B/H-C) está em `tmp/e06/levantamento-e06.md` do checkout principal, fora do Git.
  - **Pré-condição:** corrigir D1, a reconstrução quadrática em nó de grau alto (`_polilinhas_do_estilo`, ponteiro por nó), e tirar o `xfail` de `tests/unit/test_e06_1_etapa_ataque.py`.
  - O `fallback getattr(desenhos, "indices_crus", None) or range(...)` em `_caminhos_e_glifos` existe só para monkeypatch de teste e deve falhar alto antes de a E06.2 consumir os índices.
  - O benchmark tem 805 linhas. Na E06.2, quando entrar o método `"modelo"` em `METODOS`, desmembre-o e mova `KeyError` de `rodada.json` malformado para dentro do `try`.
  - Minors adiados:
    - teste de página girada sem cropbox;
    - helpers duplicados nos testes;
    - `Congelado.now` por `fromtimestamp`;
    - a contagem da T5 enxerga só `_desvio_graus`;
    - `SIMBOLOGIA.pdf` em `metodos_assinatura` é id de perfil, não folha.
  - Testes de cliente intermitentes sob carga (polling restart e application_factory_teardown) estão rastreados na E17.
---

## E06.2 — Método de pacotes sobre o modelo de desenho (dividida em E06.2.1 e E06.2.2)

**Objetivo:** executar os pacotes declarativos sobre a página do modelo de desenho como método de símbolos versionado, com as 6 gramáticas atuais portadas e o método ligado no runner.

**Divisão (2026-11-06, orquestrador):**
- **Por que dividir:** as tarefas somam ~5h15 (nota do plano e "Orçamento"). Cada subetapa é uma etapa completa, e a E06.3 passa a depender da E06.2.2.
- **Como os critérios se repartem:** a E06.2.1 leva a pré-condição D1, as fixtures e a paridade no corpus sintético. A E06.2.2 leva o método versionado, a ligação no runner, o resíduo raster e o benchmark nas 16 folhas. Auditor e `.bat` valem nas duas.
- **Onde liga:** só no runner opt-in (D12), como 5º método, ao lado de `declarative_symbols`. O motor antigo sai na E09, junto com os detectores dedicados.

**Decisão de system design do plano (entrevista):** resolvida pela D12.

---

## E06.2.1 — Núcleo de gramáticas sobre o modelo — #concluida

**Objetivo:** portar as 6 gramáticas dos pacotes para um núcleo puro sobre a página do modelo de desenho, com paridade de variantes no corpus sintético e custo limitado por página.

**Dependências:** E06.1. O relógio começa no commit `#em-andamento` da E06.2 (36ec385).

**Escopo:**
- **Pré-condição D1:** `reconstruir_polilinhas` linear em nó de grau alto, sem o `xfail`.
- **Núcleo puro:** molduras a partir de caminhos, polilinhas fechadas e círculos; texto de `TextoModelo` (inclusive glifo), em palavras; índice espacial e teto de trabalho por página.
- **Porte das 6 gramáticas**, com paridade de variantes por página, geometria e índice cru contra o motor atual.
- **Página para as gramáticas** a partir da página aberta, com índice cru e preenchimentos translúcidos, sem mudar o modelo, o cache nem `VERSAO_MODELO_DESENHO`.

**Fora de escopo:** método versionado, ligação no runner, resíduo raster e benchmark (E06.2.2); gramáticas novas (E06.3); analisador padrão (E09).

**Critérios de aceite:**

- [x] Fixtures sintéticas positivas e negativas, e paridade de variantes por página com o motor atual no corpus sintético.
- [x] O teste de nó de grau alto da D1 passa sem `xfail`.
- [x] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** laços O(F²) e `get_text` por moldura no motor atual → índice espacial e teto por página.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-06-leitura-vetorial-por-poste-e06-2-1.md`. Revisão de arquitetura (opus): bloqueou na rodada 0 (C1, I1–I4) e aprovou com notas na rodada 1.
- Relógio: de 36ec385 (11:45 de 2026-11-06) até o commit `#concluida` (16:40), 4h48 sem os 7 min da interrupção. A marca de 4h30 passou na revisão final, e a ruling foi continuar, porque as tarefas já estavam integradas.
- Revisão final (`revisor-seguranca`, opus, 5ed40ed..59ecdf0): aprovada com ressalvas, sem Crítico e sem defeito de código bloqueante. I1–I4 e M1–M8 foram tratados na onda única e neste handoff. Restos sem correção, por limite da onda: uma docstring errada e dois testes de resíduo, listados abaixo para a E06.2.2.
- Critérios verificados:
  1. Paridade: `test_paridade_de_variantes_por_pagina_no_corpus` verde, com fixtures positivas e negativas nas 6 gramáticas.
  2. D1: sem `xfail`; os únicos xfail são R-9 e a memória de glifos da E05.
  3. `scripts.audit_symbol_packages` → `errors []` em 02359d3; depois disso `src/` só mudou em docstring.
  4. `.bat` em 59ecdf0 → `RESULTADO FINAL: APROVADO`: 8412 passed, 2 xfailed, cobertura 89,25%. Depois disso, só docs.
  - `osv-scanner` nos 7 locks → `No issues found`; nenhum lock mudou. `check_test_integrity --base 5ed40ed` → exit 0, sem apontamentos.
- Entregas, todas puras, sem PyMuPDF, salvo o adaptador, e nada ligado no job nem no runner (D12):
  - `reconstruir_polilinhas` linear em nó de grau alto (D1, sem `xfail`);
  - `drawing_model/symbol_grammars.py`: página, orçamento, grade, molduras, palavras e segmentos;
  - `drawing_model/grammar_frames.py` e `grammar_disc.py`: as 6 gramáticas;
  - `drawing_model/symbol_matcher.py`: `casar_variantes`;
  - `pagina_para_gramaticas` em `pymupdf_drawing_model.py`, com índice cru e translúcidos.
- Ciclo: Task 1 e Task 3 sem rodada de correção; Task 2 sem correção; Task 5, 1 rodada; Task 4, 4 rodadas; Task 6 sem correção. Testador em todas (`Risco: alto`). Revisão de cada tarefa aprovada ao fim do ciclo.
- Decisões tomadas (revisáveis):
  - **R-4 emendada três vezes na execução:** a repartição de span por caracteres foi revogada, porque dava falso positivo em fonte proporcional e o texto de glifo também não tem largura fixa. Toda palavra usa a caixa do span. Spans nativos horizontais colados, com lacuna em `[-t, +t]` e `t = max(0.5, 0.2·altura)`, fundem em uma palavra `inteira`. Nas guardas, palavra `inteira` recusa por sobreposição fechada. Custo: recall em rótulo dentro de span maior. Saída se pesar: caixa real da palavra (`TextoGlifo.glifos`, `words`).
  - **R-E06.2.1-1 a 11**, no plano.
- **Para a E06.2.2, além do que o plano lista em "Fechamento operacional":**
  - **Critério novo pedido pela revisão final (I1):** o benchmark por ficha não vê a maior parte dos falsos positivos, porque descarta classes fora das referências e o que está fora das regiões anotadas. As divergências abaixo em que o núcleo afirma a mais só fecham com um diff por variante e folha, núcleo contra motor, sem passar pela ficha, com cada casamento "só no núcleo" listado e classificado.
  - **Primeira tarefa (I3):** fixture de rótulo em contorno real pelo adaptador (`pdf_texto_contorno` e `carregar_tabela_glifos`). O ganho "rótulo em glifo" de R-5 só está provado em página pura. Com `empty_interior`, o contorno de uma letra com 6% ou mais da moldura pode recusar a própria variante, justo na família que motiva a etapa. Não medido em folha real.
  - **Pré-condição:** `_unir_proximos` quadrático (`xfail` de R-9).
  - **Divergências em que o núcleo pode afirmar a mais.** As fixadas em teste como valor de hoje se invertem, não se removem:
    - fixado: `Q`+`DP` com intruso no fluxo;
    - fixado: sobreimpressão acima de `t` no rótulo;
    - fixado: spans colados a 90°, 180° e 270°, no rótulo e na guarda (`_pode_colar` só funde a 0 ± 1°);
    - fixado: `qu` inclinado conta como segmento, e diagonais e barra casam onde o motor não casa. Na direção contrária, `empty_interior` recusa onde o motor casa. O efeito na linha terminal de caminho `fs` não foi testado;
    - fixado: borda, com `ponto_em` fechado contra o `contains` semiaberto do motor;
    - fixado na E06.2.2.1: sobreimpressão acima de `t` na guarda, em (14, helv, -4) e (11, cour, -3). Em (11, helv, -4), a guarda recusa, porque nessa geometria o centro de `12` cai na moldura.
    - medido na E06.2.2.1 e descartado: `C`+`T` simples não diverge, em 3 fontes e tamanhos 8, 11 e 14. Onde `words` separa, a PyMuPDF já põe espaço no segundo span, e a fusão recusa. A concatenação só diverge com outro texto entre os pedaços no fluxo (`Q`+`DP`).
  - **Divergências em que o núcleo perde recall:**
    - família de R-6: linha que dobra no disco, duas linhas de lados opostos e traço solto a menos de 0,5 pt do centro. É o caso mais provável de perda em folha real: um disco com rede dos dois lados no mesmo estilo deixa de casar;
    - losango de 4 `l` sem encadeamento (o X dobrado, recusado de propósito, é falso positivo do motor);
    - lados de losango fora de `grade_segmentos`;
    - rótulo nativo dentro de span maior que ele (R-4);
    - vários `qu` inclinados contam uma banda; disco além de 16 pt da página não casa; segundo retângulo do mesmo caminho; dois discos de dois arcos viram uma elipse.
  - **Custo a medir à parte nas 16 folhas:** a colagem é paga por candidato na janela `±t` e é quadrática em colunas alinhadas; `grandes` com diagonais longas; o orçamento cobra candidato distinto, então o trabalho real chega a 64 vezes o gasto, e a grade guarda até 64 entradas por item.
  - **Fontes:**
    - desenho malformado ou com ponto não finito é descartado sem diagnóstico (`_caminhos`), e a guarda perde esse elemento. Dá para detectar sem tocar no modelo, comparando `total_desenhos` com `len(caminhos)`, tolerando desenho sem subcaminho, que `_caminhos` também não inclui;
    - `tabela=None` em `pagina_para_gramaticas` abre as guardas: considere o parâmetro obrigatório na ligação;
    - glifo anulado pelo leitor (`glifos_desconhecidos`) não bloqueia e deixa a guarda sem aquele texto.
  - **Adiado para a E06.3:** promover a públicos os privados importados entre módulos (`grammar_disc`, `symbol_matcher`), onde as gramáticas vão mudar.

---

## E06.2.2 — Método versionado no runner (dividida em E06.2.2.1 e E06.2.2.2)

**Divisão (2026-11-06, orquestrador):**
- **Por que dividir:** as tarefas somam cerca de 4h, e a E06.2.1 mostrou que o porte consome mais do que a estimativa. Cada subetapa é uma etapa completa, e a E06.3 passa a depender da E06.2.2.2.
- **Como os critérios se repartem:** a E06.2.2.1 leva a pré-condição R-9, a fixture de contorno real, o método versionado, o resíduo raster e a ligação no runner. A E06.2.2.2 leva o benchmark ao lado do atual, o diff por variante e a classificação. Auditor e `.bat` valem nas duas.

---

## E06.2.2.1 — Método versionado no runner — #concluida

**Objetivo:** expor o núcleo da E06.2.1 como método de símbolos versionado, ligado no `SymbolCompositionRunner` opt-in (D12), com o agrupamento do modelo limitado.

**Dependências:** E06.2.1. O relógio começa no commit `#em-andamento` da E06.2.2 (ca9783a).

**Escopo:**
- **Pré-condição R-9:** `_unir_proximos` sem comparação repetida e com teto de visitas.
- **Primeira tarefa do handoff (I3):** rótulo em contorno real pelo adaptador, e a guarda corrigida se o defeito se confirmar.
- **Método versionado:** `VERSAO_MODELO_DESENHO`, o sha dos pacotes e o da tabela de glifos no perfil, primitivas com índice cru, teto e falha de fonte traduzidos em cobertura, e resíduo raster marcado para a E12. "Marcado" é a função pública `residuos_raster(...)`, com caixa e hash, mais a contagem em `motivo` da cobertura; o resíduo não vira observação nem proposta (R-E06.2.2.1-4 do plano).
- **Ligação no `SymbolCompositionRunner`**, com a versão na assinatura.
- **Resíduos herdados da revisão final da E06.2.1:** a docstring errada e os dois testes.

**Fora de escopo:** benchmark e diff (E06.2.2.2); gramáticas novas (E06.3); analisador padrão (E09).

**Critérios de aceite:**

- [x] Fixtures sintéticas positivas e negativas do método e da ligação no runner.
- [x] O teste de agrupamento de R-9 passa sem `xfail`.
- [x] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`. Confira a data do `relatorio-testes.txt`: sem o `.\`, o `cmd` da sessão não acha o `.bat` e o relatório lido é o antigo.

**Revisão humana:** não

**Notas para o plano:** leia o handoff da E06.2.1: traz a primeira tarefa e as divergências a medir.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** o modelo com glifos custa até ~20 s por folha no runner → opt-in até a E09. `_unir_proximos` é quadrático em caixas sobrepostas (R-9) → teto antes de ligar no runner.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-06-leitura-vetorial-por-poste-e06-2-2-1.md`. Revisão de arquitetura (opus): bloqueou nas rodadas 0 e 1 e aprovou com notas na rodada 2.
- Relógio: de ca9783a (16:40 de 2026-11-06) até o commit `#concluida` (17:23 de 2026-11-07), 4h28 sem as duas paradas (16:46–22:46 e 23:00–13:15). Cerca de 80 min são uma suíte do testador da Task 6 que travou com outra suíte ativa; encerrada, a segunda rodou normal. Não reproduzido nem investigado.
- Revisão final (`revisor-seguranca`, opus, ca9783a..d953b28): pronto com correções, sem Crítico. Onda única: I1 e M1 (696d68f), I2, I3 e lacunas de teste (ad0b669). Re-revisão: todos fechados.
- Critérios verificados:
  1. Fixtures: `test_model_symbols.py`, `test_model_symbols_ataque.py`, `test_model_symbols_costuras_etapa.py` e `test_model_symbols_runner.py`.
  2. R-9: sem `xfail`. Os dois xfail são a memória de glifos da E05 e os centros aglomerados (limitação aceita).
  3. `scripts.audit_symbol_packages` em ad0b669 → `errors []`.
  4. `.bat` em ad0b669 → `RESULTADO FINAL: APROVADO`: 8633 passed, 2 xfailed, cobertura 89,28%.
  - `osv-scanner` nos 7 locks, com o formato declarado (189 pacotes) → `No issues found`; nenhum lock mudou. `check_test_integrity --base ca9783a` → exit 1, com 3 apontamentos justificados pela revisora (2 renomeações e 1 acréscimo do desenvolvedor em arquivo do testador).
- Ciclo: Task 1, 2, 5 e 6 sem rodada de correção; Task 3, 2 rodadas; Task 4, 1 rodada de teste. Testador nas tarefas de risco alto, mais o testador de etapa. Onda 1: tasks 1, 2 e 5; onda 2: tasks 3 e 6; onda 3: task 4.
- Entregas:
  - método `declarative-drawing-model`, versão 1.0.0, em `adapters/analysis/model_symbols.py`: `perfil_pacotes_modelo(pacotes, tabela, *, limite)`, `observar_pacotes_modelo`, `residuos_raster`, `ResiduoRaster`;
  - 5º método do `SymbolCompositionRunner` opt-in, `_VERSION = "e06-server-symbol-composition-2"`, com os módulos no digest;
  - agrupamento com um só orçamento de visitas, `LIMITE_VISITAS_AGRUPAMENTO = 50_000_000`;
  - `PaginaGramatica.glifos_lidos`: a guarda de marca pula só o caminho lido como glifo.
- Medição nas 16 folhas, com a guarda da Task 6 (15 `CONCLUIDO`, 1 `NAO_DETECCAO`, sem `FORA_DOMINIO` nem `FALHA`; máx. 18,59 s por folha sob carga; 19,0 s de parede com 10 processos; 115 resíduos). Medida antes da onda final, que não muda a saída abaixo do teto:

  | Folha | Tempo (s) | Resíduos | Observações |
  |---|---|---|---|
  | 1235863754.1 | 18,59 | 62 | 2 |
  | 1242910617 | 4,88 | 5 | 1 |
  | 1246619503 | 15,81 | 11 | 5 |
  | 1248863234 | 13,72 | 7 | 4 |
  | 1248924977 | 3,17 | 0 | 1 |
  | 1249479371 | 16,05 | 22 | 1 |
  | 1250203925 | 2,27 | 0 | 2 |
  | 1251077960 | 0,27 | 1 | 3 |
  | 1254146081 | 6,90 | 2 | 1 |
  | 1255172677 | 0,38 | 0 | 0 |
  | 1256403718 | 0,16 | 0 | 1 |
  | 1256505864 | 12,58 | 1 | 3 |
  | 1256702690 | 7,53 | 2 | 1 |
  | 1257009501 | 6,87 | 2 | 1 |
  | 1257190578 | 0,14 | 0 | 1 |
  | 1257760087 | 3,52 | 0 | 2 |

- Visitas do agrupamento: máx. ~3,7 milhões por folha (1257760087), 7,4% do teto. Teto medido: 5.000 círculos sobrepostos, ~2,08 s; 11.000 arcos disjuntos num traço, 23,21 s por página (com outra suíte rodando).
- Decisões para o usuário (tomadas pela opção recomendada):
  - **R-1, exceção ao invariante de versão:** o agrupamento mudou sem subir `VERSAO_MODELO_DESENHO`, porque nenhum consumidor lê `grupos`. Custo se errada: o cache do modelo guarda `grupos` antigos até alguém subir a versão.
  - **R-3, fonte nova que falha deixa de ser fail-closed:** só `modelo.caminhos_falhou` aborta. `primitivas`, `textos_nativos`, `textos_shx` e `glifos` viram `FORA_DOMINIO` e entram no cache. Prós: não aborta documento que hoje compõe. Custo se errada: falha transitória fica no cache até a assinatura mudar.
  - **R-4, resíduo raster como dado:** não vira observação nem proposta. Custo se errada: a E12 ganha um caminho de observação depois.
  - **Sinal "Exclusivo" com o 5º método, aceito até a E09, sem mudar produção:** em símbolo de pacote, `exclusive` passa a falso, porque os dois métodos veem o mesmo desenho; em página no teto, volta a verdadeiro. Em símbolo com papel de ativo, o status passa de "Exclusivo" a "Suportado", no XLSX, na anotação do PDF e no cliente. "Suportado" aqui não é corroboração: são dois portes da mesma regra. Hoje as 22 variantes habilitadas têm papel `desconhecido`, então só o `exclusive` muda; o status passa a mudar quando a E06.3 habilitar variante de ativo. Decisão e probabilidade não mudam. Prós: opt-in desligado por padrão; a alternativa, contar por família, exige gravar família em `simbolo_observacoes`. Custo se errada: exportações opt-in com rótulo enganoso; reverter exige nova análise.
  - **Limite de visitas 50 milhões, em vez de redesenhar a união:** folga de ~13× sobre o máximo medido. Custo se errada: página hostil leva até ~23 s antes do teto, e o trabalho continua quadrático em célula densa.
  - **Resíduos acima de 20 por folha (62 e 22), sem regra nova de mosaico:** uma regra "colada em outra imagem" tiraria 87 de 115, mas esconderia um carimbo encostado, justamente o caso que refuta a H2. Custo se errada: triagem a mais na E06.3.
  - **Centros aglomerados numa célula, aceito até a E09:** o custo é N imagens × M casamentos, com N sem teto (`xfail` estrito em `test_model_symbols_ataque.py`; estimativa não medida: minutos em PDF hostil). Custo se errada: job preso no worker único, em execução opt-in.
- **Para a E06.2.2.2:**
  - método: `declarative-drawing-model` 1.0.0, assinatura pelo perfil de `perfil_pacotes_modelo` (modelo, sha dos pacotes, sha da tabela e teto);
  - no diff, separe o gasto de orçamento entre colagem e gramáticas;
  - `fonte_falhou:` conta como falha, não como exclusão; `glifos_desconhecidos` deixa a guarda sem aquele texto;
  - contorno de qualquer letra lida como glifo dentro da moldura não aciona a guarda (inerente a R-5, igual ao texto nativo), sem teste com segundo texto legível: confira nas classificações;
  - a tabela acima é a linha de base do tempo e dos resíduos.
- **Para a E06.3:**
  - a H2 se confirma chamando `residuos_raster` folha a folha, não lendo a ocorrência reconciliada, e página `FORA_DOMINIO` não conta como 0 resíduos;
  - composição dos 115 resíduos: 87 colados em outra imagem de página, 17 de anotação, 11 isolados; hashes em várias folhas: `0084746843` e `debb149f09` (5 folhas, anotação), `a2f1377bd8` e `2cc3d96d36` (3, anotação), `7ccaa4d25c` (3, página), `cfa408d465` (2, página). Causa provável (inferida, imagens não abertas): recortes de borda da ortofoto;
  - quem consumir `grupos` adiciona `modelo.grupos_falhou` às fontes consumidas, sobe a versão (R-1) e põe `LIMITE_VISITAS_AGRUPAMENTO` nos `parametros` do perfil, que hoje só o digest cobre. Docstrings de `_unir_proximos` e `agrupar_candidatos` ainda falam só de entrada de célula; `_item_coberto` levanta sem argumento. A varredura de figuras segue quadrática sob o teto: um índice por item a eliminaria sem mudar a saída (o `any` não depende da ordem);
  - módulos novos entram no digest: troque `_MODULOS_DO_DIGEST` (cópia manual no teste) por um teste de fecho por imports; `drawing_model/model.py` hoje fica fora do digest;
  - habilitar variante de ativo muda o status "Exclusivo" para "Suportado" (decisão acima): reavalie.
- **Para a E12:** `residuos_raster` é o ponto de partida; o contrato do que ela consome é dela.
- **Para a E09, como critério de aceite ao trocar o padrão:**
  - teto para imagens em `_ler_fontes`, decode por anotação (até 16 MP, sem memória entre anotações) e `_CamadasDoTexto` (spans × trechos gigantes), além dos centros aglomerados, com cancelamento interno ou prazo por página: o worker é único e o cancelamento só ocorre entre métodos;
  - R-6 (desenho malformado descartado sem diagnóstico, `tabela` obrigatória); R-E06.2.1-2; `model_symbols` depende de privados de `declarative_symbols`, que ela remove;
  - o digest cobre só adaptadores (`ports`, `domain/symbols.py` e o codec podem mudar a saída cacheada sem invalidar), preexistente;
  - o que fazer com o sinal "Exclusivo" (acima).

---

## E06.2.2.2 — Medição do método nas 16 folhas — #concluida

**Objetivo:** medir o método novo nas 16 folhas, ao lado do atual, e classificar cada divergência em que ele afirma a mais.

**Dependências:** E06.2.2.1.

**Escopo:**
- **Benchmark:** método `modelo` em `scripts/benchmark_simbolos_ficha.py`, com o script desmembrado.
- **Diff por variante e folha**, núcleo contra motor, sem passar pela ficha, com o gasto de orçamento separado entre colagem e gramáticas.
- **Classificação** de cada "só no núcleo", e as decisões que ela pede sobre as divergências do handoff da E06.2.1.

**Fora de escopo:** gramáticas novas (E06.3); analisador padrão (E09).

**Critérios de aceite:**

- [x] O benchmark de símbolos mede o método novo nas 16 folhas, ao lado do atual.
- [x] Diff por variante e folha, núcleo contra motor, sem passar pela ficha, em `tmp/`: cada casamento "só no núcleo" listado e classificado (ver handoff da E06.2.1).
- [x] O gasto real de orçamento e o limite de `LIMITE_CONSULTAS_PAGINA` estão registrados no handoff.
- [x] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** a comparação entre métodos usa o bloco `comparacao` do benchmark (interseção das folhas). Decida o que acontece com um casamento classificado como falso positivo: corrigir, aceitar com ruling ou bloquear.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** o benchmark por ficha não vê a maior parte dos falsos positivos (I1 da E06.2.1) → o diff não passa pela ficha.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-07-leitura-vetorial-por-poste-e06-2-2-2.md`. Revisão de arquitetura (opus): bloqueou nas rodadas 0 e 1 e aprovou com notas na rodada 2.
- Relógio: de 1aec214 (17:23 de 2026-11-07) até o commit `#concluida` (19:21), 1h58.
- Revisão final (`revisor-seguranca`, opus, 1aec214..f751a16): pronto com correções, sem Crítico, e as correções eram só de registro (este handoff, ledger e plano). Depois dela, o `.bat` reprovou no mypy de um teste; a tipagem foi corrigida em c6e1876, só no teste.
- Critérios verificados:
  1. Benchmark (em 7405d16) nas 16 folhas, sem falha, critério `centro`. A tabela é a linha de base:

     | método | tp | fp | fn | precisão | recall | predições |
     |---|---|---|---|---|---|---|
     | `atual` | 131 | 58 | 48 | 69,3% | 73,2% | 277 |
     | `pacotes` | 2 | 18 | 177 | 10,0% | 1,1% | 29 |
     | `modelo` | 2 | 18 | 177 | 10,0% | 1,1% | 29 |

     O benchmark por ficha quase não discrimina: 177 das 179 referências são de classes sem variante habilitada. As 18 FP de `PONTO_CONEXAO` estão nos dois métodos: o novo as herda do motor, e elas não contam como "afirma a mais".
  2. Diff (em f751a16): 16 páginas comparadas, nenhuma girada, sem falha. Resultado: `ambos` 29, `so_nucleo` 0, `so_motor` 0, `indice_diverge` 0, `geometria_diverge` 0. Com 0 itens, o critério "cada só no núcleo listado e classificado" está cumprido sem classificação, porque não houve o que classificar. **Ressalva:** as 29 observações são todas de `cemig-eo-r3-s28-v001` (disco terminal). As outras 21 variantes habilitadas, as gramáticas de moldura, não casam em nenhuma folha, nem no motor nem no núcleo, então esta medição não valida o núcleo em moldura de folha real.
  3. Gasto real (limite de medição 10¹²): o maior foi 133.352 consultas, na folha `016` (colagem 171, índices 45.768, gramáticas 87.413), 6,7% de `LIMITE_CONSULTAS_PAGINA` = 2.000.000. As outras folhas ficaram em ≤ 30.467. O limite fica (R-E06.2.2.2-4: ≤ 200.000).
  4. `scripts.audit_symbol_packages` em c6e1876 → `errors []`.
  5. `.bat` em c6e1876 → `RESULTADO FINAL: APROVADO`: 9048 passed, 2 xfailed, cobertura 89,29%, mypy limpo em 557 arquivos.
  - `osv-scanner` nos 7 locks (189 pacotes) → `No issues found`; nenhum lock mudou. `check_test_integrity --base 1aec214` → exit 1, um apontamento justificado (a linha de `METODOS` que o plano autoriza).
- Ciclo: Onda 1, Tasks 1 e 3; Onda 2, Tasks 2 e 4. Testador nas quatro, todas de risco alto. A Task 1 teve uma rodada de correção (`caminho_cego` público), a Task 2 uma de teste (golden no lugar de `git show`) e a Task 4 uma (orientação do disco em faixas, com emenda de R-E06.2.2.2-2). A Task 3 passou sem correção. As Tasks 5 e 7 e os Steps 2 a 4 da Task 6 foram pulados por ruling, porque o diff deu 0 itens. O testador de etapa não foi despachado: nenhuma tarefa de risco normal produziu código.
- Entregas:
  - `scripts/simbolos_corpus.py`, `simbolos_ficha_metricas.py` e `simbolos_ficha_relatorio.py`, o benchmark desmembrado;
  - métodos `pacotes` e `modelo` no benchmark;
  - `gasto_por_fase` e `GastoPagina` em `symbol_matcher.py`, mais `ContextoGramatica.gasto_colagem`, sem mudar a saída nem o gasto de `casar_variantes`;
  - `scripts/diff_simbolos_nucleo_motor.py` (esquema `diff-nucleo-motor-v1`).
- Linha de base congelada, em `tmp/e06-2-2-2/` do checkout principal: `diff/diff-nucleo-motor.json` (sha256 `20f3b708…6eeeee`) e `simbolos/simbolos-ficha.json` (sha256 `b6a3118d…6008d`). Tempo por página no diff: motor até 3,48 s, núcleo até 26,21 s, com 8 processos e a suíte rodando ao lado. O `tempo_s` de `pacotes` e `modelo` no benchmark inclui a carga de pacotes e tabela por folha; prefira o do diff como linha de base.
- Divergências do handoff da E06.2.1: as que fazem o núcleo afirmar a mais (`Q`+`DP`, sobreimpressão, spans girados, `qu` inclinado, borda) aparecem em 0 itens e ficam sem decisão. As que perdem recall: `so_motor` 0 em todas as variantes. **Não verificado:** o contorno de letra lido como glifo dentro da moldura (handoff da E06.2.2.1), porque nenhuma moldura casou.
- Decisões para o usuário (tomadas pela opção recomendada):
  - **Classificação pulada com 0 itens.** O critério foi cumprido com 0 casamentos "só no núcleo", mas a medição só exercita a variante de disco. Prós: não há o que classificar, e as duas medições independentes concordam (29/29/29). Custo se errada: a E06.3 ou a E09 tomar isto por validação das gramáticas de moldura em folha real.
  - **`LIMITE_CONSULTAS_PAGINA` fica em 2.000.000,** com o maior gasto em 6,7%.
- **Para a E06.3:**
  - as gramáticas novas gastam do mesmo limite; a fase `indices` já chega a 45.768 na folha `016`;
  - a especificação de recortes e fila de classificação (Task 5 do plano) está pronta, mas **não foi construída**: `--recortes`, `--dpi`, `fila.json` e os testes dela não existem;
  - antes de rotular itens, o item do diff precisa da caixa de cada texto (ou de `contido`) e da caixa visual do item, com folga de 0,5 pt, e `textos` precisa passar por `ocultar`. `glifos_lidos` não tem teste positivo. Extraia o markdown do script (853 linhas) antes de pôr os recortes nele;
  - `runner._package_prediction` é privado e usado pelo benchmark: torne-o público ou fixe-o num teste de contrato;
  - `tests/unit/test_gasto_por_fase_ataque.py` guarda uma cópia do corpo antigo de `casar_variantes` como oráculo, que vale só para esta refatoração: remova-o quando os helpers mudarem;
  - o diff casa por guloso (o erro vai para `so_*`, nunca esconde item), e um `pdf_id` repetido na rodada colapsaria uma folha em silêncio (o benchmark faz o mesmo);
  - a comparação depois de mudar gramáticas usa a chave natural `(pdf_id, página, variante, índice cru)`, contra os dois JSON congelados acima.

---

## E06.3 — Gramáticas das classes da ficha (dividida em E06.3.1–E06.3.5)

**Divisão (2026-11-07, orquestrador):**
- **Por que dividir:** a seção pede a divisão por classe acima de 3h. A ampliação dos pacotes sozinha leva cerca de 2h, e cada gramática tem laboratório próprio (na E05, cinco rodadas desse ajuste custaram ~7h45).
- **Subetapas,** cada uma uma etapa completa, em série:
  - E06.3.1, pacotes: as 58 variantes do inventário fora dos pacotes, como `pending`;
  - E06.3.2, ATERRAMENTO e PARA_RAIOS_MT (haste com barras) e a H2, que não depende de gramática nova e pode mudar a abordagem: medir cedo;
  - E06.3.3, PARA_RAIOS_BT e TRANSFORMADOR: molduras;
  - E06.3.4, ESTAI;
  - E06.3.5, EQUIPAMENTO_INTERRUPCAO.
- **Como os critérios se repartem:**
  - A E06.3.1 leva a ampliação do escopo abaixo, sem gramática nova. Por isso as fixtures e o "acima do atual" não se aplicam a ela.
  - Cada subetapa de gramática leva as fixtures e o "acima do atual" das suas classes, e estende a guarda contra memorização às gramáticas dela.
  - A E06.3.2 confirma a H2.
  - O auditor e o `.bat` valem em todas.
- **Dependência:** a E07 passa a depender da E06.3.5.

O objetivo, o escopo e os critérios abaixo valem para o conjunto das subetapas.

**Objetivo:** reconhecer estais, aterramento, para-raios MT/BT, transformadores e equipamento de interrupção sobre o modelo de desenho, acima do analisador atual.

**Dependências:** E06.2.2.2.

**Escopo:**
- Ampliação dos pacotes com as variantes do inventário de ESTAI, TRANSFORMADOR, ATERRAMENTO e PARA_RAIOS_MT/BT, com fonte rastreável e `negative_examples` vindos de `confusable_negatives`. O auditor e `scripts/coverage_matrix_e16.py` passam a aceitar variante de outro `owner_stage` do inventário. A mudança é visível na tabela de suporte da revisão e nas exportações, e vai para "Decisões para o usuário". Os números fixos de `tests/server/test_e14_symbol_review.py:287` entram na File Structure.
- Gramáticas novas e variantes habilitadas, com laboratório para os limiares por classe e por família.
- Confirmar a hipótese H2: símbolos raster ficam marcados como resíduo para a E12.

**Fora de escopo:** associação ao poste (E07); remover detectores antigos (E09).

**Critérios de aceite:**

- [ ] Fixtures sintéticas positivas e negativas para cada classe nova ou alterada.
- [ ] Nas 16 folhas, precisão e recall de símbolo (diagnóstico) estão registrados em `tmp/` e são maiores que os do analisador atual com as mesmas referências.
- [ ] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:**
- O laboratório testa três hipóteses, conforme o levantamento da E06.1: H-A (grupo como unidade), H-B (grupo como semente e consulta espacial) e H-C (limiares por família).
- Na E05, 5 rodadas desse ajuste dentro do ciclo custaram ~7h45. Divida por classe se passar de 3h.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** pacote que memoriza a folha → exigir fixture sintética autoral; a guarda da E06.1 procura coordenadas e hashes, e é estendida às gramáticas novas.

**Evidências e handoff:** nas subetapas.

---

## E06.3.1 — Pacotes das classes da ficha — #concluida

**Objetivo:** pôr nos pacotes, como `pending`, as variantes do inventário das classes da ficha que ainda estão fora deles, com fonte rastreável, para as subetapas de gramática só precisarem habilitar.

**Dependências:** E06.2.2.2. O relógio começa no commit `#em-andamento` da E06.3 (107d89e).

**Escopo:**
- **58 variantes** de `docs/data/inventario-simbologia-v1.json` com `owner_stage` ≠ E07, fora das famílias de convenção (f02-01 e f02-02, E10): f02-14 (15) e f02-15 (2), ESTAI; f02-18 (23), f02-24 (2) e f02-25 (4), TRANSFORMADOR e um CONJUNTO_EO; f02-19 (4), ATERRAMENTO; f02-21 (8), PARA_RAIOS_MT/BT. Todas `pending`, com motivo, `source_ref` do inventário e `negative_examples` vindos de `confusable_negatives`, como as `pending` que já existem.
- **Auditor, `scripts/coverage_matrix_e16.py` e `scripts/curation_coverage_e16.py`** aceitam variante de outro `owner_stage` do inventário, relatada por estágio. O que hoje exige `E07` continua exigindo para as variantes E07. A recusa de `pending` exato no fechamento da curadoria passa a valer só para a variante E07, com a frase correspondente de `docs/fluxo-curadoria-incremental-simbologia.md` ajustada (decisão do plano).
- **Números fixos:** `tests/server/test_e14_symbol_review.py:287` e as contagens de `tests/unit/test_declarative_symbol_packages.py`. A tabela de suporte da revisão e as exportações passam a mostrar as novas `pending`.

**Fora de escopo:** gramáticas e habilitação (E06.3.2 a E06.3.5); a matriz histórica da E16 (`docs/data/matriz-simbologia-e16*`), imutável por contrato; a próxima rodada de curadoria publica a matriz atual a partir dela.

**Critérios de aceite:**

- [x] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros, com as 58 variantes novas como `pending` e o relato por estágio.
- [x] A tabela de suporte da revisão conta as novas `pending`, e os testes fixos foram atualizados com o número novo.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** a mudança visível na revisão e nas exportações vai para "Decisões para o usuário". O levantamento em `tmp/e06/levantamento-e06.md` do checkout principal (§2, §5) mapeia auditor, inventário e testes fixos.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** a matriz da E16 e o fechamento da curadoria contam variantes → relatar por estágio, sem mudar o que já é exigido das E07.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-07-leitura-vetorial-por-poste-e06-3-1.md`. Revisão de arquitetura (opus): bloqueou nas rodadas 0 (C1: as 12 E05 exatas quebrariam o fechamento da curadoria) e 1, e aprovou na rodada 2.
- Relógio: de 107d89e (19:22 de 2026-11-07, `#em-andamento` da E06.3) até o commit `#concluida` (20:37), 1h15. A divisão da E06.3 entra nesse tempo.
- Revisão final (`revisor-seguranca`, opus, 107d89e..8b721b6): pronta com correções de registro, sem Crítico nem código. Onda única: docstring do auditor e mensagem de teste (08b5c3d) e as notas da E06.3.2.
- Critérios verificados:
  1. Auditor em 77f401d: `errors []`, 423 variantes em 31 famílias, 22 `enabled` e 401 `pending`. `by_owner_stage`: E04 12/12, E05 29/29 e E06 17/17, todas `pending`; E07 365, com 22 `enabled`.
  2. Tabela de suporte: 401 `pending` e 22 `enabled` (`tests/server/test_e14_symbol_review.py:287` e `tests/unit/test_pacotes_classes_da_ficha.py`). As 58 foram conferidas uma a uma contra o inventário, as variantes antigas ficaram intactas (golden por id) e as observações não mudam com as `pending`.
  3. `.bat` em 77f401d: `RESULTADO FINAL: APROVADO`, com 9273 passed, 2 xfailed, cobertura de 89,29% e mypy limpo em 561 arquivos.
  - `osv-scanner` nos 7 locks: `No issues found`; nenhum lock mudou. `check_test_integrity --base 107d89e`: exit 1, com 9 apontamentos justificados. São contagens que o plano manda mudar: 343→401, 365→423, 27→31 e 17→21.
- Ciclo:
  - Onda 1: Tasks 1 (auditor) e 2 (matriz e comparador). Onda 2: Task 3 (pacotes), precedida de um Step 0 em que o testador inverteu os próprios testes de "só E07 exigida".
  - Testador nas três tarefas, todas de risco alto. Nenhuma rodada de correção.
- Entregas:
  - 4 famílias novas (f02-14, -15, -24 e -25) e 35 variantes novas em f02-18, -19 e -21, todas `pending`, com `negative_examples` de `confusable_negatives`;
  - o auditor exige todas as variantes não E10 e relata por estágio;
  - a matriz e o comparador aceitam pacote `pending` de outro estágio.
- Decisões para o usuário (tomadas pela opção recomendada):
  - **Contrato da curadoria (R-E06.3.1-2):** a recusa de "`pending` contado como exato" vale só para a variante E07: `status == reconhecido_exato`, `package_status == pending` e `owner_stage == E07`. A frase de `docs/fluxo-curadoria-incremental-simbologia.md:44-45` mudou. Prós: as 12 E05 exatas pela evidência do detector de transformadores continuam exatas. As alternativas eram não empacotá-las (fere o escopo) ou rebaixá-las (perda falsa). Custo se errada: o fechamento aceita uma E05 exata com pacote `pending`, o que é verdade pela evidência E05.
  - **Mudança visível:** a tabela de suporte da revisão e a planilha de capacidade mostram 4 famílias novas, todas pendentes, e 401 `pending`. ESTAI e TRANSFORMADOR aparecem como pendentes no pacote, embora os detectores dedicados do runner opt-in os reconheçam.
  - **`complete_recognition` do auditor** passa a exigir também as variantes E04 a E06 habilitadas. Continua `false`, e nada no fluxo o consome.
  - **`missing family`** aparece só para a família de uma variante que falta. Uma variante empacotada em outra família já gera `family mismatch`, sem erro redundante.
  - **Pacote `enabled` de outro estágio** ganha `id_exato_sintetico` na coluna de pacotes da matriz, com o status vindo do próprio estágio, como na E07. A E06.3.2 decide (nas notas dela).
  - **`read_matrix` mais permissivo:** aceita combinações que o `build` nunca gera (E10 com pacote, E04 ou E10 exata e `pending`). Endurecer o leitor vai além de R-2. Custo se errada: uma matriz montada à mão passa no gate.
- **Não verificado:** a rodada real de curadoria de ponta a ponta (`.claude/skills/curadoria-simbologia/SKILL.md:456-458`, com a matriz histórica como "antes"). A prova é sintética, com as 12 E05 nos dois sentidos. O esperado é `transitions: []` e `net_exact_change: 0`.
- **Para a E06.3.2 a E06.3.5:** as notas da E06.3.2 trazem os handoffs a ler e as decisões pendentes. Cada subetapa habilita só as variantes da sua classe, já empacotadas, e troca o `reason` e as contagens `enabled`. O golden das variantes antigas em `tests/unit/test_pacotes_classes_da_ficha.py` muda de propósito ao habilitar. O `compare` não confere se `owner_stage`, `family_id` ou `class_code` de um ID mudou entre as matrizes: uma linha de `raise` resolve, se pesar.

---

## E06.3.2 — Aterramento, para-raios MT e H2 (dividida em E06.3.2.1 e E06.3.2.2)

**Divisão (2026-11-07, orquestrador):**
- **Por que dividir:** o plano, depois de duas rodadas da revisão de arquitetura, soma cerca de 4h em tarefas, mais o laboratório, acima do teto de ~3h do "Orçamento". A divisão da E06.3 já pedia a H2 medida cedo, porque ela pode mudar a abordagem.
- **Subetapas,** cada uma uma etapa completa, em série:
  - E06.3.2.1, base: o tipo de gramática só do modelo (`stem_bars` validado e ignorado pelo motor antigo), a métrica de leitura errada afirmada no benchmark e a medição da H2, com o veredito;
  - E06.3.2.2, gramática: laboratório, gramática de haste com barras, observação com componentes, habilitação das variantes e benchmark nas 16 folhas.
- **Como os critérios se repartem:** a E06.3.2.1 leva a H2 e as fixtures do que ela constrói; a E06.3.2.2 leva as fixtures das duas classes e o "acima do atual". Auditor e `.bat` valem nas duas.
- **Dependência:** a E06.3.3 passa a depender da E06.3.2.2. O relógio da E06.3.2.1 começa no commit `#em-andamento` da E06.3.2 (e609bda).

O objetivo, o escopo e os critérios abaixo valem para o conjunto das subetapas.

**Objetivo:** reconhecer ATERRAMENTO e PARA_RAIOS_MT sobre o modelo de desenho, acima do analisador atual, e confirmar ou refutar a hipótese H2.

**Dependências:** E06.3.1.

**Escopo:**
- Gramática de haste com barras (aterramento: barras decrescentes; para-raios MT: barras alternadas).
- Habilitação das variantes de f02-19 e f02-21 (MT), já empacotadas na E06.3.1.
- Laboratório H-A/H-B/H-C.
- A guarda contra memorização estendida às gramáticas novas.
- A H2: chamar `residuos_raster` folha a folha (handoff da E06.2.2.1), sem contar página `FORA_DOMINIO`, e registrar a contagem por folha em `tmp/`.

**Fora de escopo:** as outras classes (E06.3.3 a E06.3.5).

**Critérios de aceite:**

- [ ] Fixtures sintéticas positivas e negativas das duas classes.
- [ ] Nas 16 folhas, precisão e recall de ATERRAMENTO e PARA_RAIOS_MT em `tmp/`, maiores que os do atual com as mesmas referências.
- [ ] H2 confirmada ou refutada, com a contagem por folha em `tmp/`.
- [ ] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:**
- As notas da E06.3 valem aqui.
- Linha de base, do handoff da E06.2.2.2: atual, ATERRAMENTO 41 tp / 32 fp / 2 fn e PARA_RAIOS_MT 10 / 4 / 3 (critério `centro`).
- Leia os blocos "Para a E06.3" dos handoffs da E06.2.1, da E06.2.2.1 e da E06.2.2.2. Esta é a primeira subetapa que os consome.
- Esta é a primeira subetapa que habilita variante de ativo (`operational`), e por isso o status "Exclusivo" vira "Suportado" no XLSX, na anotação do PDF e no cliente (decisão da E06.2.2.1): reavalie.
- Habilite só as variantes ATERRAMENTO de f02-19 e PARA_RAIOS_MT de f02-21. As famílias também têm CONECTOR (E07) e EQUIPAMENTO_PROTECAO.
- Da E06.3.1, decida:
  - variante não E07 `enabled` ganha `declarative-vector-packages` = `id_exato_sintetico` na matriz (`scripts/coverage_matrix_e16.py:131-136`), sem evidência própria;
  - o status de variante E04 é fixo em `nao_avaliavel` (`:194-196`), então habilitar ATERRAMENTO e PARA_RAIOS_MT nunca aparece como ganho na matriz da curadoria.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** os da E06.3.

**Evidências e handoff:** —

---

## E06.3.2.1 — Base da haste, leituras erradas e H2 — #concluida

**Objetivo:** preparar o tipo de gramática que só o método sobre o modelo executa, medir a leitura errada afirmada no benchmark e confirmar ou refutar a H2.

**Dependências:** E06.3.1.

**Escopo:**
- **Tipo `stem_bars` só do modelo:** validado nos pacotes e no schema, ignorado pelo motor antigo (`variantes_do_motor`), anunciado pelo perfil do método sobre o modelo; `CasamentoGramatica.componentes`.
- **Leitura errada afirmada** calculada pelo benchmark de símbolos, por classe.
- **H2:** `residuos_raster` folha a folha, sem contar página `FORA_DOMINIO` nem com imagens que falharam, cruzado com as referências da ficha, com recortes para triagem; contagem por folha em `tmp/`.

**Fora de escopo:** a gramática e a habilitação (E06.3.2.2).

**Critérios de aceite:**

- [x] Fixtures sintéticas positivas e negativas do tipo só do modelo e das duas medições.
- [x] H2 confirmada ou refutada, com a contagem por folha em `tmp/`.
- [x] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** o plano é `docs/superpowers/plans/2026-11-07-leitura-vetorial-por-poste-e06-3-2-1.md`, recortado do plano da E06.3.2 já revisado.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** os da E06.3.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-07-leitura-vetorial-por-poste-e06-3-2-1.md`. Revisão de arquitetura (opus): bloqueou nas rodadas 0 e 1, sobre o plano da E06.3.2 inteiro (C1: o perfil do modelo herdava as classes do motor; C2: a caixa da haste não era o pictograma do legado), e aprovou com notas na rodada 2, sobre o plano recortado.
- Relógio: de e609bda (21:14 de 2026-11-07, `#em-andamento` da E06.3.2) até o commit `#concluida` (a98d95e, 22:58), 1h44. A divisão da E06.3.2 entra nesse tempo.
- Revisão final (`revisor-seguranca`, opus, 2d9d303..14544d5): aprovada com ressalvas, sem Crítico e sem correção de código. Os dois Importantes eram de registro e estão fechados neste handoff. Os Menores ficaram com ruling no ledger, e nenhum bloqueia.
- Critérios verificados:
  1. Fixtures sintéticas: `tests/unit/test_gramatica_so_modelo*.py`, `test_residuos_raster_folhas*.py` e `test_leituras_erradas*.py`, com positivos e negativos de cada peça.
  2. H2 (em 14544d5, `tmp/e06-3-2-1/h2/residuos-raster.json` do checkout principal, com recortes):
     - 16 folhas medidas, nenhuma `fora_dominio`;
     - 115 resíduos, com 100 hashes distintos. Por folha: 001: 62, 002: 5, 003: 11, 004: 7, 005: 0, 006: 22, 007: 0, 008: 1, 009: 2, 010: 0, 011: 0, 012: 1, 013: 2, 014: 2, 015: 0 e 016: 0;
     - 3 resíduos estão sobre referência, todos ESTAI (001 e 006). Os três são ortofoto com o estai vetorial desenhado por cima;
     - as 92 referências sob alguma imagem têm desenho vetorial na caixa, e as outras 87 não estão sob imagem;
     - triagem visual dos 100 hashes: ortofoto, assinaturas, QR codes, logos, fotos, blocos de texto, um ícone de imagem quebrada (008 e 009) e o rótulo de poste em anotação (012, já descrito na H3);
     - **1 símbolo da rede em raster:** disco laranja com "~" no fim do ramal ABN-16, folha 004 (iText). A classe está fora da ficha (provavelmente geração);
     - **Veredito:** H2 refutada no sentido estrito (critério R-E06.3.2-7) e sustentada para as classes da ficha. A linha H2 de "Hipóteses" foi atualizada.
  3. `scripts.audit_symbol_packages` em 14544d5 → `errors []`, 22 `enabled` e 401 `pending`. Nenhum pacote mudou.
  4. `.bat` em 14544d5 → `RESULTADO FINAL: APROVADO`: 9413 passed, 2 xfailed, cobertura 89,29%, mypy limpo em 567 arquivos.
  - `osv-scanner` nos 7 locks → `No issues found`; nenhum lock mudou. `check_test_integrity --base 2d9d303` → exit 1, com 1 apontamento justificado (a asserção do perfil do modelo, trocada como o plano manda).
- Benchmark de símbolos em 14544d5, `atual` e `modelo` (`tmp/e06-3-2-1/simbolos/`):
  - igual à linha de base congelada `tmp/e06-2-2-2/simbolos/simbolos-ficha.json`: `atual` 131/58/48 e `modelo` 2/18/177 (tp/fp/fn, `centro`), sem divergência em nenhuma folha;
  - **linha de base de leituras erradas** (`centro`): `atual` 19 (ATERRAMENTO 13, PARA_RAIOS_MT 4, PONTO_CONEXAO 2) e `modelo` 2 (PONTO_CONEXAO 2);
  - a unidade é o par (predição, referência de outra classe), e não a predição: uma predição sobre duas referências conta 2. `referencia_id` é o índice local da folha e só identifica a referência dentro do bloco por folha.
- Ciclo: Onda 1 com as Tasks 1, 2 e 3 em paralelo e testador nas três (risco alto). Cada uma teve uma rodada de correção, vinda de um vermelho do testador: `TypeError` com campo de tipo errado; recorte de página girada em branco; predição fora do FP contada como leitura errada. A Task 4 foi a medição. Testador de etapa não foi despachado: nenhuma tarefa de risco normal produziu código.
- Entregas:
  - tipo `stem_bars` só do modelo: `GRAMATICAS_SO_MODELO`, `variantes_do_motor`, ramo no schema `pacotes-simbologia.schema.json`, perfil do método sobre o modelo com todas as habilitadas e `CasamentoGramatica.componentes`;
  - `scripts/residuos_raster_folhas.py` (esquema `residuos-raster-v1`);
  - chave `leituras_erradas` no benchmark de símbolos e uma linha no `.md`.
- Decisões para o usuário (tomadas pela opção recomendada):
  - **Divisão da E06.3.2** em E06.3.2.1 e E06.3.2.2: com os achados da revisão de arquitetura, as tarefas passaram de 4h.
  - **R-E06.3.2-1, tipo de gramática só do modelo:** o motor antigo ignora `stem_bars`. Quando a E06.3.2.2 habilitar as hastes, a tabela de suporte da revisão (`symbol_support.py`), a matriz da curadoria (`coverage_matrix_e16.py`, que vai marcar `fora_do_dominio` no motor antigo), `scripts/symbol_benchmark_runner.py` e `scripts/curation_backlog.py` vão contar como habilitadas variantes que o motor antigo não executa. Prós: o motor antigo sai na E09, e portar a gramática para ele seria trabalho jogado fora. Custo se errada: leitura enganosa nessas tabelas até a E09.
  - **Leitura errada afirmada** conta só a predição que o benchmark já conta como FP. Fora das regiões e perto de poste pendente não conta.
  - **H2 refutada no sentido estrito.** O raster fica como resíduo para a E12, e as gramáticas vetoriais seguem.
- **Pendente, intermitente:** `tests/unit/test_curation_round.py::test_transicoes_concorrentes_no_mesmo_pdf_nao_perdem_eventos` falhou uma vez sob `-n 20`, com nenhum arquivo dele tocado. Passou 6/6 isolado, na 2ª suíte e no `.bat`. Não investigado. Uma perda real de eventos na rodada de curadoria seria defeito de dados.
- **Para a E06.3.2.2:**
  - parta do rascunho do plano. A nota no topo carrega N3, N4, M-a, M-c e M4 da revisão de arquitetura. Ao abrir, tire dele a H2 (já medida aqui) e a CLI `leituras-erradas`: o critério lê a chave `leituras_erradas` do bloco `centro`, com 0 exigido em ATERRAMENTO e PARA_RAIOS_MT contra a linha de base acima;
  - `tests/unit/test_gramatica_so_modelo_ataque.py::test_modelo_ainda_nao_executa_stem_bars_e_falha_alto` fica vermelho de propósito quando o casador ganhar `stem_bars`. Reescreva-o na tarefa da gramática;
  - `scripts/diff_simbolos_nucleo_motor.py` ainda usa `_enabled` (troca prevista na tarefa de habilitação);
  - a docstring de `leituras_erradas` ainda diz "não casadas" para o parâmetro `casadas`, que hoje significa "fora do FP" (corrigir se tocar o arquivo);
  - `residuos_raster_folhas` deixa PNG órfãos quando uma folha falha no meio e soma `referencias_sob_imagem` de página com imagens que falharam. Nenhuma das duas coisas afetou esta medição.
- **Para a E12:** o disco laranja com "~" da folha 004 é o primeiro símbolo da rede raster confirmado (resíduo `2a7dd179c5da`).
- **Para a E09:** `GRAMATICAS_SO_MODELO` e a validação dos pacotes moram em `declarative_symbols.py`, que ela remove. `review_status` e `role` têm `in {...}` sem guarda de tipo: o pior caso é `TypeError` em vez de `ValueError`.

---

## E06.3.2.2 — Gramática de haste com barras — #concluida

**Objetivo:** reconhecer ATERRAMENTO e PARA_RAIOS_MT sobre o modelo de desenho, acima do analisador atual.

**Dependências:** E06.3.2.1.

**Escopo:** laboratório H-A/H-B/H-C; gramática de haste com barras (caixa do pictograma, haste como componente); observação com uma primitiva por caminho e versão 1.1.0 do método; habilitação das variantes de f02-19 e f02-21 (MT); guarda contra memorização estendida; benchmark nas 16 folhas, comparação com os JSON congelados da E06.2.2.2 e taxa de fusão com o legado no runner.

**Fora de escopo:** as outras classes (E06.3.3 a E06.3.5).

**Critérios de aceite:**

- [x] Fixtures sintéticas positivas e negativas das duas classes.
- [x] Nas 16 folhas, precisão e recall de ATERRAMENTO e PARA_RAIOS_MT em `tmp/`, maiores que os do atual com as mesmas referências, e leitura errada afirmada = 0. **Cumprido pelo critério aplicado, não pelo literal** (ver handoff e "Decisões para o usuário"): o literal é inatingível para qualquer leitura correta, por erros da ficha congelada.
- [x] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** parte do rascunho `docs/superpowers/plans/2026-11-07-leitura-vetorial-por-poste-e06-3-2-2.md` (decisões R-E06.3.2-1 a 9, já com os achados das rodadas 0 e 1 da revisão de arquitetura da E06.3.2); leia o handoff da E06.3.2.1, sobretudo o veredito da H2.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** os da E06.3.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-07-leitura-vetorial-por-poste-e06-3-2-2.md`. Revisão de arquitetura (opus): bloqueou na rodada 0 (4 Importantes: testes quebrados fora dos Files, dependência oculta, gasto não medido e caminho da H-A) e aprovou com notas na rodada 1.
- Relógio: de 2b6cc09 (22:58 de 2026-11-07) até o commit `#concluida` (4ad9148, 02:34 de 2026-11-08), 3h36.
- Revisão final (`revisor-seguranca`, opus, a98d95e..a44f68e): aprovada com ressalvas, sem Crítico. A onda única corrigiu M-1 e M-2 (99652b4, só testes), e a re-revisão aprovou. I-1 a I-3 eram de registro e estão neste handoff.
- **Laboratório**, em `tmp/laboratorio/e06-3-2-2/` do checkout principal:
  - H-A: grupo como unidade. Deu 6/20/37 e 0/0/13, porque os grupos quebram o símbolo.
  - H-B: segmento como semente. Deu 41/20/2 e 10/4/3, com gasto de 611 mil.
  - **H-C, escolhida:** H-B com limiares pela origem do texto da página, que serve de proxy da escala do símbolo. A alternativa `PerfilFamilia` do documento foi descartada porque o método roda por página.
- Critérios verificados:
  1. Fixtures: `test_grammar_stem*.py` (positivos das 8 variantes × 3 rotações, negativos, pictograma, componentes, teto), `test_model_symbols_componentes_ataque.py`, `test_model_symbols_haste_ataque.py`, `test_habilitacao_hastes_ataque.py` e `test_haste_costuras_etapa_testador.py`.
  2. Benchmark nas 16 folhas em d62c47c (`tmp/e06-3-2-2/simbolos/`), 0 falhas, critério `centro`. Números brutos:

     | classe | método | tp/fp/fn | precisão | recall | leituras erradas (pares) |
     |---|---|---|---|---|---|
     | ATERRAMENTO | `atual` | 41/32/2 | 56,2% | 95,3% | 13 |
     | ATERRAMENTO | `modelo` | 41/7/2 | **85,4%** | 95,3% | 13 |
     | PARA_RAIOS_MT | `atual` | 10/4/3 | 71,4% | 76,9% | 4 |
     | PARA_RAIOS_MT | `modelo` | 10/4/3 | 71,4% | 76,9% | 4 |

     - O `atual` é igual ao congelado, e as outras classes do `modelo` são iguais ao congelado em todas as folhas.
     - **Critério aplicado** (uma definição só, ruling no ledger):
       - recall sem as 5 referências com rótulo trocado: ≥ atual. Fica 41/41 e 10/10 nos dois métodos;
       - precisão bruta: > atual em ATERRAMENTO, e igual em PARA_RAIOS_MT;
       - leituras erradas de fato: 0.
     - Os 5 FN, nos dois métodos, são referências com rótulo trocado na ficha:
       - 006 `P8-para-raios`, 010 `b-P1-circulo-norte` e 012 `P8-pr-2` são PARA_RAIOS_MT sobre desenho que não tem 4 barras alternadas;
       - 006 `P8-aterramento-1` e 010 `b-P1-aterramento-oval-sul` são ATERRAMENTO sobre 4 barras alternadas.
     - Os 2 FP de PARA_RAIOS_MT que não vêm de troca são para-raios reais (variante com envolvente e X) sem referência correta: 002 está anotado como EQUIPAMENTO_INTERRUPCAO de forma desconhecida, e 007 não está anotado.
     - As 17 leituras erradas (pares) são:
       - 5 as trocas;
       - 8 o terra real na ponta de estai;
       - 2 a haste real na borda da caixa de uma chave;
       - 2 o aterramento real sem anotação da 011.
       - Nenhuma é leitura errada de fato. A triagem está em `tmp/laboratorio/e06-3-2-2/h-c/triagem/` e `tmp/e06-3-2-2/task1-triagem-final/`.
     - Diff núcleo × motor nas 16 páginas, idêntico ao congelado da E06.2.2.2 variante a variante, com o índice cru: `ambos` 29 e `so_*` 0. Gasto máximo de 187.659 consultas (folha 016), sem `teto_consultas`.
  3. `scripts.audit_symbol_packages` → `errors []`, 30 `enabled` e 393 `pending`.
  4. `.bat` em a44f68e → `RESULTADO FINAL: APROVADO`: 9670 passed, 2 xfailed, cobertura 89,37%, mypy limpo em 579 arquivos. Em 99652b4, só testes mudaram, e a suíte deu 9669 passed.
  - `osv-scanner` nos 7 locks → `No issues found`; nenhum lock mudou. `check_test_integrity --base a98d95e` → 24 apontamentos, todos justificados nas revisões: o oráculo e a caracterização removidos, a versão 1.0.0 → 1.1.0, as contagens 401/22 → 393/30 e as inversões mandadas pelo plano.
- Ciclo:
  - Laboratório com 3 hipóteses.
  - Onda A: Task 1, gramática. Uma rodada de correção: pares do X e deduplicação passaram a pagar o orçamento, a cor do X passou a ser comparada pela forma canônica e 4 barras decrescentes passaram a ser recusadas.
  - Onda B: Tasks 2 (matriz e diff), 3 (observação, versão 1.1.0 e digest) e 4 (habilitação), integradas nessa ordem.
  - Onda C: Task 5 (teto, guarda e pureza). Duas rodadas: a guarda de fonte passou a ler literais por AST e a pegar float normalizado.
  - Testador nas tarefas de risco alto e testador de etapa.
- Entregas:
  - `drawing_model/grammar_stem.py`, a gramática `stem_bars`: caixa do pictograma, componentes, perfil por sinal da página e teto pago;
  - despacho explícito por `kind` em `symbol_matcher.py`;
  - `declarative-drawing-model` 1.1.0, com uma primitiva por caminho;
  - digest do runner pelo fecho de imports;
  - 8 variantes habilitadas (f02-19 v001–v004, f02-21 v005–v008);
  - matriz e diff tratando o tipo só do modelo;
  - guarda contra memorização nos fontes, por AST e tokenize.
- **Decisões para o usuário** (tomadas pela opção recomendada; a única de arquitetura é a R-6, em entrevista no fim do lote):
  - **R-4 aplicado com desvio (critério 2):** os números brutos estão acima, e o literal "maiores" é inatingível para qualquer leitura correta. O `atual` já casa todas as referências válidas, e os erros da ficha penalizam os dois métodos igualmente. Em PARA_RAIOS_MT, o método novo **empata** com o atual. Custo se errada: a E06.3.3 começa sobre uma base que você pode considerar não aceita; reabrir custa uma rodada de curadoria das referências.
  - **Referências a corrigir pela curadoria** (a ficha congelada não é editada aqui):
    - as 5 trocas;
    - 002 `P1-s04`;
    - o para-raios sem anotação da 007;
    - o terra sem anotação da 011;
    - os 8 terras de ponta de estai (001 ×2, 006 ×4, 008, 012);
    - as 2 hastes na borda de uma chave (002 e 006).
  - **R-5 e consumidores de `status == "enabled"`:** a tabela de suporte da revisão e a exportação XLSX passam a mostrar 30 habilitadas (as 8 hastes), mas o job padrão não as executa. `symbol_benchmark_runner` informa 30 com o motor executando 22. Na matriz da curadoria, o motor antigo fica `fora_do_dominio` para as hastes.
  - **R-6, decisão de arquitetura:** com a H-C, a gramática reimplementa a consulta do legado. As 8 situações viram "Suportado" com dois métodos no runner opt-in, o que **não** é corroboração independente, e saem do filtro "Exclusivos". A alternativa, exclusividade por família de método, exige gravar a família em `simbolo_observacoes`, o que é uma migração.
  - **R-7, escopo:** a taxa de fusão com o legado nas 16 folhas não foi medida. A fusão está provada com os pacotes reais nas 8 situações, em página sintética.
  - **Limiares escolhidos depois do laboratório:**
    - envolvente poligonal: 8 vértices e desvio de 0,2;
    - braço do X como traço solto;
    - tolerância de cor de 0,02 fora da paleta do legado.
- **Para a E06.3.3:**
  - padrão de tipo só do modelo (`GRAMATICAS_SO_MODELO`), pictograma como caixa e componentes como primitivas;
  - **folga de orçamento de só 6%:** a folha 016 gasta 187.659 de 200.000, e as molduras novas gastam do mesmo teto;
  - o perfil por sinal de página (texto em glifo × nativo) é um proxy de escala. Nenhuma folha é SHX;
  - menores adiados:
    - `Haste` expõe `_Contorno`;
    - `grammar_stem.py` importa privados de `symbol_grammars`;
    - perfil glifo testado só a 0°;
    - `_caixa_do_caminho` sem guarda para caminho vazio.
- **Para a E07:** a fusão com o legado só foi provada em fixture sintética. Uma ocorrência que não funda vira símbolo duplicado para quem lê o runner (D12).
- **Para a E16 e a E09** (risco de recall fora das 16 folhas quando o legado sair): a gramática não portou estas normalizações do legado:
  - item de caminho múltiplo como haste (`_um_traco`);
  - fusão de fragmentos;
  - cinza tratado como preto (a paleta exclui cinza e azul);
  - haste mínima relativa fora das páginas em glifo (6/1/1,5 pt absolutos);
  - o legado não tinha teto de haste, e a gramática tem `_HASTE_MAXIMA` de 24 pt.

  Hoje o legado cobre essas lacunas no runner pela fusão. Também ficam para a E09 `GRAMATICAS_SO_MODELO` e a validação dos pacotes em `declarative_symbols.py`.

---

## E06.3.3 — Para-raios BT e transformador (dividida em E06.3.3.1 e E06.3.3.2)

**Divisão (2026-11-08, orquestrador):**
- **Por que dividir:** são duas gramáticas novas, cada uma com laboratório. A E06.3.2.2, com uma gramática só, levou 3h36, então as duas juntas passam do teto de ~3h do "Orçamento".
- **Subetapas,** em série:
  - E06.3.3.1, PARA_RAIOS_BT: retângulo atravessado por diagonal (f02-21 v001–v004). O `atual` não casa nenhuma das 10 referências;
  - E06.3.3.2, TRANSFORMADOR: triângulo ou meio preenchido em círculo.
- **Escopo do transformador ajustado** (ruling, vai a "Decisões para o usuário"): ficam `pending` as variantes de enrolamento (f02-18 v019–v023, f02-24 e f02-25, todas E05, com evidência própria do detector de transformadores na matriz da curadoria) e o triângulo roxo com S (f02-18 v016–v018), porque nenhuma é "triângulo ou meio preenchido em círculo".
- **Critérios:** cada subetapa leva as fixtures e o "acima do atual" da sua classe. Auditor e `.bat` valem nas duas.
- **Dependência:** a E06.3.4 passa a depender da E06.3.3.2. O relógio da E06.3.3.1 começa no commit `#em-andamento` da E06.3.3 (80cfff2).

O objetivo, o escopo e os critérios abaixo valem para o conjunto das subetapas.

**Objetivo:** reconhecer PARA_RAIOS_BT e TRANSFORMADOR sobre o modelo de desenho, acima do analisador atual.

**Dependências:** E06.3.2.2.

**Escopo:** gramáticas de moldura (para-raios BT: retângulo com diagonal; transformador: triângulo ou meio preenchido em círculo), habilitação das variantes de f02-21 (BT), f02-18, f02-24 e f02-25, laboratório e guarda.

**Fora de escopo:** as outras classes.

**Critérios de aceite:**

- [ ] Fixtures sintéticas positivas e negativas das duas classes.
- [ ] Nas 16 folhas, precisão e recall de PARA_RAIOS_BT e TRANSFORMADOR em `tmp/`, maiores que os do atual.
- [ ] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** as notas da E06.3 valem aqui. As duas gramáticas compartilham `grammar_frames.py`: em série.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** os da E06.3.

**Evidências e handoff:** nas subetapas.

---

## E06.3.3.1 — Para-raios BT — #concluida

**Objetivo:** reconhecer PARA_RAIOS_BT sobre o modelo de desenho, acima do analisador atual, que não casa nenhuma das 10 referências.

**Dependências:** E06.3.2.2.

**Escopo:**
- tipo de gramática só do modelo para o retângulo atravessado por diagonal, com envolvente e X como na haste;
- laboratório;
- gramática;
- habilitação de f02-21 v001–v004;
- guarda, teto e pureza;
- medição nas 16 folhas.

**Fora de escopo:** TRANSFORMADOR (E06.3.3.2).

**Critérios de aceite:**

- [x] Fixtures sintéticas positivas e negativas de PARA_RAIOS_BT.
- [x] Nas 16 folhas, precisão e recall de PARA_RAIOS_BT em `tmp/`, maiores que os do atual (0 tp, 10 fn), e leitura errada afirmada de fato = 0, com triagem.
- [x] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:**
- Leia o handoff da E06.3.2.2: tipo só do modelo, pictograma, componentes, folga de orçamento de só 6% e o perfil por sinal de página.
- O desenho real é uma elipse com um retângulo girado dentro e uma diagonal com ganchos nas pontas, que passa além do retângulo, ligada ao poste por uma haste.
- A 006 `P8-para-raios` (rotulada PARA_RAIOS_MT) tem esse desenho.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** os da E06.3; o teto de 200.000 consultas por folha (a 016 já gasta 187.659).

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-08-leitura-vetorial-por-poste-e06-3-3-1.md`. A revisão de arquitetura (opus) bloqueou nas rodadas 0 e 1 e aprovou com notas na rodada 2. Os bloqueios foram:
  - testes fora dos Files;
  - o contrato de `grammar_marcas`;
  - o aceite degenerado na precisão;
  - a fusão com o legado sem prova;
  - o compartilhamento de contornos.
- Relógio: de 80cfff2 (02:34 de 2026-11-08, `#em-andamento` da E06.3.3) até o commit `#concluida` (0fb4523, 05:32), 2h58. A divisão da E06.3.3 entra nesse tempo.
- Revisão final (`revisor-seguranca`, opus, 4ad9148..edfc9c5): aprovada com ressalvas, sem Crítico e sem correção de código. O Importante era o registro deste handoff. Os Menores ficaram para a E06.3.3.2, abaixo.
- **Laboratório** (`tmp/laboratorio/e06-3-3-1/` do checkout principal), PARA_RAIOS_BT:
  - H-1, moldura primeiro: 9/1/1 e gasto de 197 mil;
  - **H-2, diagonal primeiro, escolhida:** 10/2/0 e gasto de 192 mil;
  - H-3, envolvente primeiro: 10/1/0, mas com folga de gasto de 305 e sem ler o BT real da 006.
- Critérios verificados:
  1. Fixtures: `test_grammar_rect_diagonal*.py`, `test_gramatica_rect_diagonal_tipo*.py`, `test_grammar_marcas*.py`, `test_habilitacao_bt_ataque.py`, `test_model_symbols_bt_runner*.py` e `test_bt_costuras_etapa_testador.py`.
  2. Benchmark nas 16 folhas em 1aa4e49 (`tmp/e06-3-3-1/simbolos/`), 0 falhas, critério `centro`:
     - **PARA_RAIOS_BT:** `atual` 0/0/10, `modelo` **10/2/0** (precisão 83,3%, recall 100%; o piso de precisão do plano é 50%);
     - as demais classes do `modelo` são iguais às da E06.3.2.2 em todas as folhas, e o `atual` é igual ao congelado;
     - os 2 FP, triados em render, são leituras certas. O da 006 `P8-para-raios` é um BT real que a ficha rotula PARA_RAIOS_MT: é a única leitura errada de BT pela métrica bruta, e é troca de rótulo. O da 014 é um BT real sem poste anotado. Leitura errada de fato: 0;
     - o diff núcleo × motor é igual ao congelado (`ambos` 29, `so_*` 0). Gasto máximo: 192.308 (016).
  3. `scripts.audit_symbol_packages` → `errors []`, 34 `enabled` e 389 `pending`.
  4. `.bat` em edfc9c5 → `RESULTADO FINAL: APROVADO`: 10113 passed, 5 xfailed (3 estritos novos), cobertura 89,45%, mypy limpo em 593 arquivos.
  - `osv-scanner` nos 7 locks → `No issues found`. `check_test_integrity --base 4ad9148` → 31 apontamentos, todos justificados: contagens, versão 1.2.0, a asserção de `GRAMATICAS_SO_MODELO`, renomeações e asserts frouxos trocados por exatos.
- Ciclo:
  - Onda A, Tasks 1 (tipo) e 2 (extração das marcas). A invariância da haste foi conferida nas 16 folhas antes do laboratório: 84 pares sem divergência.
  - Laboratório.
  - Task 3, a gramática. Uma rodada de testes.
  - Onda B, Tasks 4 (habilitação e 1.2.0) e 5 (teto, guarda e pureza). Uma rodada na Task 5.
  - Testador nas tarefas de risco alto e testador de etapa.
- Entregas:
  - `drawing_model/grammar_marcas.py`: envolvente, X, cor canônica, origem da página e `MarcasDaPagina` (contornos pagos uma vez por página);
  - `drawing_model/grammar_rect_diagonal.py`, a gramática `rect_diagonal`;
  - f02-21 v001–v004 habilitadas;
  - `declarative-drawing-model` 1.2.0.
- Decisões para o usuário (tomadas pela opção recomendada):
  - **Piso de precisão de 50% para PARA_RAIOS_BT:** a precisão do `atual` é n/d (0 predições), e o piso é decisão do plano.
  - **R-6, fusão com o legado:** o BT **não** funde no runner opt-in. A caixa do legado inclui a haste; a distância de centro é 0,0167 contra uma tolerância de 0,003–0,004; IoU de 0,47 e 0,36. São duas ocorrências por BT até a E09 (o teste falha de propósito se o par passar a fundir).
  - **Situação (variante) errada até a E06.3.3.2:**
    - a elipse real é um subcaminho fechado de 72 retas, que `reconstruir_polilinhas` parte em polilinhas abertas, e `grammar_marcas` não a vê;
    - por isso, no corpus, 100% dos BT com envolvente saem como v001/v004, sem v002/v003, e as hastes com envolvente provavelmente também;
    - além disso, o X de um vizinho foi atribuído a 3 BT, porque `tem_x` não exige o cruzamento perto do símbolo.
    - A métrica por classe não muda; a situação no runner opt-in sai errada.
  - **Consumidores de `status == "enabled"`:** tabela de suporte, XLSX e `symbol_benchmark_runner` passam a contar 34 habilitadas, contra 22 que o motor antigo executa.
  - **Referências para a curadoria:** além das listadas na E06.3.2.2, o BT real da 014 sem anotação. A 006 `P8-para-raios` (PARA_RAIOS_MT na ficha) é um PARA_RAIOS_BT pelo inventário.
- **Para a E06.3.3.2** (primeira tarefa: consertar `grammar_marcas` para as três gramáticas):
  - envolvente: ler a elipse a partir do subcaminho fechado (ou antes de a polilinha ser partida). As variantes de transformador com círculo envolvente dependem disso;
  - X de vizinho: exigir que o cruzamento do X fique perto do pictograma;
  - R-3 do BT: a haste de ligação que sai da envolvente não é buscada (`grammar_rect_diagonal.py:201-229`, `_haste_de_ligacao`);
  - os 3 `xfail(strict=True)` de `test_grammar_rect_diagonal_ataque.py`:
    - X curto: o braço com 1,5 × o lado maior ou menos vira segunda diagonal;
    - contorno quase duplicado gera dois casamentos;
    - diagonal quase duplicada recusa o símbolo.

    Ponha `raises=AssertionError` neles;
  - `MarcasDaPagina` de outro contexto escapa do teto da página: guardar o contexto e recusar o outro;
  - Menores da revisão final:
    - não há negativo de "célula de tabela" (sem lado maior máximo);
    - um retângulo montado de vários caminhos só leva `origens[0]`;
    - a diagonal não exige a cor do retângulo;
  - a nota da E06.3.3 sobre `grammar_frames.py` está desatualizada: o compartilhado agora é `grammar_marcas.py`;
  - **folga de gasto:** a 016 gasta 192.308 de 200.000, com 3,8% de folga. O transformador soma no mesmo teto.
- **Para a E07:** cada PARA_RAIOS_BT sai em duas ocorrências no runner opt-in (legado e modelo), e a situação dos BT com envolvente sai errada até a E06.3.3.2.

---

## E06.3.3.2 — Transformador (dividida em E06.3.3.2.1 e E06.3.3.2.2)

**Divisão (2026-11-08, orquestrador):**
- **Por que dividir:** o conserto de `grammar_marcas` pedido no handoff da E06.3.3.1 (envolvente, X perto do símbolo, guarda de contexto e os Menores do BT), mais a medição da situação e a gramática do transformador com laboratório, passa do teto de ~3h. O conserto não depende do transformador e muda a situação das duas gramáticas já entregues.
- **Subetapas,** em série:
  - **E06.3.3.2.1, marcas: envolvente e X.** A envolvente é lida do subcaminho fechado, e o X precisa estar perto do símbolo. Entram a guarda de contexto das marcas e os Menores do BT, e a concordância de situação com a ficha passa a ser medida no benchmark;
  - **E06.3.3.2.2, transformador:** a gramática do triângulo em círculo.
- **Achado para a E06.3.3.2.2** (conferido em 1200 dpi na 005): o transformador real é um triângulo girado, partido em metade branca e metade ciano (dois preenchimentos), dentro de um círculo. As variantes "Rede", "Dedicado" e "IP" de f02-18 têm a mesma forma, e o inventário avisa que "a forma isolada não resolve atributos não discriminados na linha". O plano da E06.3.3.2.2 decide como habilitar sem afirmar o uso.
- **Dependência:** a E06.3.4 passa a depender da E06.3.3.2.2. O relógio da E06.3.3.2.1 começa no commit `#em-andamento` da E06.3.3.2 (0529544).

O objetivo, o escopo e os critérios abaixo valem para o conjunto das subetapas.

**Objetivo:** reconhecer TRANSFORMADOR (triângulo ou meio preenchido em círculo) sobre o modelo de desenho, acima do analisador atual (14 tp, 2 fp, 0 fn).

**Dependências:** E06.3.3.1.

**Escopo:** tipo de gramática, laboratório, gramática e habilitação de f02-18 v001–v015; guarda, teto e pureza; medição nas 16 folhas.

**Fora de escopo:** enrolamentos e triângulo roxo com S (ver a divisão da E06.3.3).

**Critérios de aceite:**

- [ ] Fixtures sintéticas positivas e negativas de TRANSFORMADOR.
- [ ] Nas 16 folhas, precisão e recall de TRANSFORMADOR em `tmp/`, maiores que os do atual, e leitura errada afirmada de fato = 0.
- [ ] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** o `atual` (detector de transformadores, E05) já tem recall de 100%, então o ganho possível é de precisão. A primeira tarefa conserta `grammar_marcas` (ver o handoff da E06.3.3.1, "Para a E06.3.3.2"): sem isso, as variantes com círculo envolvente não são reconhecidas. A gramática nova usa `grammar_marcas.py`, e não `grammar_frames.py`.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** os da E06.3.

**Evidências e handoff:** nas subetapas.

---

## E06.3.3.2.1 — Marcas: envolvente e X — #concluida

**Objetivo:** fazer a situação (variante) das gramáticas sobre o modelo sair certa nas folhas reais. A envolvente passa a ser vista, e o X passa a ser o do próprio símbolo. A concordância com a ficha passa a ser medida.

**Dependências:** E06.3.3.1.

**Escopo:**
- envolvente lida do subcaminho fechado do caminho, e não só de polilinha fechada;
- X de retirada com o cruzamento perto do pictograma;
- `MarcasDaPagina` guarda o contexto e recusa outro;
- Menores do BT:
  - todos os caminhos do retângulo nos componentes;
  - a diagonal com a cor do retângulo, se não perder tp;
  - negativo de célula de tabela;
  - `raises=AssertionError` nos xfail;
- concordância de situação no benchmark, entre a variante predita e a situação anotada na ficha;
- versão do método sobre o modelo.

**Fora de escopo:** a gramática do transformador (E06.3.3.2.2).

**Critérios de aceite:**

- [x] Fixtures sintéticas positivas e negativas da envolvente por subcaminho e do X perto do símbolo.
- [x] Nas 16 folhas, tp/fp/fn por classe do `modelo` sem piora em nenhuma folha em relação à E06.3.3.1. A concordância de situação de ATERRAMENTO, PARA_RAIOS_MT e PARA_RAIOS_BT com a ficha tem de ser maior que a de antes, e a leitura errada afirmada de fato tem de ser 0.
- [x] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** leia o handoff da E06.3.3.1 ("Para a E06.3.3.2").

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** a envolvente nova pode mudar a caixa e o gasto da haste e do BT. Por isso o plano mede tp/fp/fn, gasto e diff contra a E06.3.3.1.

**Evidências e handoff (2026-11-08, orquestrador):**

- **Plano:** `docs/superpowers/plans/2026-11-08-leitura-vetorial-por-poste-e06-3-3-2-1.md`.
  - A revisão de arquitetura (opus) aprovou com notas na rodada 2. A rodada 0 bloqueou por 6 Importantes: testes do benchmark, regra do X sem prova, fechamento, tipo, aceite e haste. A rodada 1 bloqueou porque o aceite tinha sido afrouxado para "não piora".
- **Commits:** `0fb4523..1ad2701`, 25 commits. O plano e a revisão estão em `68f1180..119ff0c`.
  - O último, a onda final de correção (`1ad2701`), pôs a elipse inclinada na guarda de fonte e acrescentou os testes de borda de `_ANISOTROPIA_MINIMA`.
  - Depois dele, a suíte deu 10494 passed e 5 xfailed.
- **Relógio:** 0529544 (05:32) até o fechamento, cerca de 3h40 contra a estimativa de 3h00. Os dois Step 0 de medição e a rodada da elipse inclinada ficaram fora da soma.
- **Revisão final** (opus): **aprovada**. Ela veio com reservas: o único Importante era este handoff, e havia dois Menores (guarda de fonte e borda da anisotropia), resolvidos na onda final e confirmados na re-revisão com escopo.
- **Critérios de aceite**, no HEAD 0cab39d, com saídas em `tmp/e06-3-3-2-1/final*`:
  - [x] Fixtures sintéticas positivas e negativas para a envolvente por subcaminho, a elipse inclinada, o X perto do símbolo e a guarda de contexto, todas sob a guarda de fonte.
  - [x] Sem piora de tp/fp/fn por folha nem por classe em relação a `tmp/e06-3-3-1`. Do `modelo` pelo critério centro: ATERRAMENTO 41/7/2, PARA_RAIOS_MT 10/4/3, PARA_RAIOS_BT 10/2/0.
  - [x] A **concordância de situação** do `modelo` (centro) foi de **2/14 (14,3%) a 14/14 (100%)**. Por classe: ATERRAMENTO 1/11 → 11/11, MT 1/2 → 2/2, BT 0/1 → 1/1. Ficam fora da conta 49 TP sem situação anotada na ficha. O `atual` fica em 0/11, com 33 sem situação predita.
  - [x] Leitura errada afirmada de fato = 0: são 20 itens, os mesmos da E06.3.3.1, nenhum novo.
  - [x] `audit_symbol_packages` deu `errors []` e 34 habilitadas.
  - [x] `.\IniciarTestes.bat` deu APROVADO: 10480 passed, 5 xfailed, cobertura de 89,47% e complexidade E/F aprovada.
  - Também conferidos:
    - diff núcleo × motor igual ao congelado (29 em ambos);
    - gasto máximo de 189.097 na 016, contra 192.308 na E06.3.3.1;
    - `osv-scanner` nos 7 locks: `No issues found`;
    - `check_test_integrity --base 0fb4523`: 17 apontamentos, todos justificados (versão 1.3.0, renomes, chaves da predição, dourado de gasto, inversão da cor, xfail que virou teste).
- **Triagem em render** (orquestrador):
  - os 10 tp de PARA_RAIOS_BT saem com a variante do desenho;
  - na amostra de 9 hastes com envolvente, as 9 saem v002/v006;
  - o BT sai com 7 v001, 15 v002 e 1 v004; o ATERRAMENTO passou de 20 para 35 v002 e o MT de 10 para 16 v006.
- **Ciclo:**
  - onda A com as Tasks 2 e 1; depois a Task 3; depois a Task 4, com uma rodada para a cor;
  - testador em cada tarefa e testador de etapa, que achou o D-1: a haste da borda de uma envolvente girada;
  - rodada de correção da Task 1 para a **elipse inclinada**, vista na triagem: 002 e 015 saíam v001.
- **Entregas:**
  - `grammar_marcas.py`:
    - contornos elípticos vindos de subcaminhos fechados de traço, com filtro estrutural antes de pagar gasto, `_TOLERANCIA_FECHAMENTO = 0,05` pt (o oval fecha em 0,0 e o arco aberto mais próximo está a 0,24 pt) e `Contorno.origem`/`subcaminho`;
    - critério elíptico invariante à rotação, pelos momentos do contorno, e "dentro" e "borda" calculados pela elipse girada;
    - X com cruzamento a até `_CRUZAMENTO_X = 1,0`×escala do centro: o X próprio fica a no máximo 0,379 e o de vizinho a pelo menos 1,82;
    - `MarcasDaPagina.contexto` e `marcas_do_contexto`;
  - `grammar_rect_diagonal.py`: `origens` nos componentes, cor canônica da diagonal, lado maior máximo, haste a partir da borda da envolvente;
  - concordância de situação no benchmark (`concordancia_situacao`);
  - `declarative-drawing-model` 1.3.0.
- **Decisões para o usuário** (tomadas pela opção recomendada):
  - **BT da 016 em (0,622; 0,276) lido como v004:**
    - o X é do próprio BT: os braços têm 1,61 e 1,59×escala, com pontos médios no centro, e se cruzam a 0,034×escala;
    - o portão literal da Task 3, "os 3 casos perdem o X", partia da leitura da E06.3.3.1, que o tomava por X de vizinho. Foi dado por cumprido na intenção: 001 e 013 foram resolvidos;
    - esse BT não está na ficha.
  - **Lado maior máximo do BT absoluto em 17,16 pt** (2 × 8,58, o maior corpo medido nas 16 folhas). O BT não tem escala externa. Uma folha plotada em escala maior perderia todos os BT sem aviso.
  - **Limiares novos fora do R-1:** a rodada da elipse inclinada criou `_ANISOTROPIA_MINIMA = 0,02` e `_RUIDO_INCLINACAO = 1e-9`, que só decidem quando a inclinação vale 0. Os limiares de aceitação elíptica não mudaram.
  - **Teto de gasto de 200.000 por folha como requisito não funcional:** a folga é de 5,5% na 016, e o transformador soma no mesmo teto.
  - **Concordância:** o texto livre da ficha fora do vocabulário ("âncora existente", "instalar (verde)") conta como discordante, sem mapa semântico. A normalização corta em "(" ou ";".
- **Para a E06.3.3.2.2:**
  - **Envolvente do transformador:** é um círculo, o caso quase isotrópico; use o mesmo `grammar_marcas`. Os testes de borda de `_ANISOTROPIA_MINIMA` já existem (razões 1,005 e 1,05 a 30°).
  - Rede, Dedicado e IP não se distinguem pela forma (ver a divisão da E06.3.3.2).
  - **Formas de envolvente ainda não lidas:**
    - elipse de Béziers girada, que continua tratada como alinhada aos eixos;
    - oval "explodido", com uma reta por caminho (016 em 0,556; 0,22, que não está na ficha);
    - arco aberto a até 0,5 pt, que vira contorno pela polilinha, já na base. Mudar isso mexe em `VERSAO_MODELO_DESENHO`.
  - **Menores:**
    - tornar `_mesma_cor` pública;
    - a cor da diagonal compara só o traço da âncora: um retângulo só preenchido nunca casa;
    - escolher o par de X mais perto do centro, e não o primeiro;
    - com envolvente grande e excêntrica, o X próprio pode cair além de 1×escala;
    - em 7 dos 13 v002, um toco de 0,5 a 1,5 pt fica fora dos componentes;
    - `casa_hastes`/`casa_retangulos_diagonal(candidatos=)` não guardam o contexto;
    - `variant_id` desconhecido cai em `situacao_nao_declarada`, que hoje dá 0.
- **Para a E07:**
  - **R-7:** `model_symbols._observacao` não preenche `situacao`. No runner opt-in, a situação só é derivável da variante. Falta decidir onde fica o mapa variante → situação, no adaptador ou no consumidor.
  - Cada PARA_RAIOS_BT continua saindo em duas ocorrências (legado e modelo).

---

## E06.3.3.2.2 — Transformador — #em-andamento

**Objetivo:** reconhecer TRANSFORMADOR (triângulo partido ou de contorno, em círculo ou não) sobre o modelo de desenho, acima do analisador atual (14 tp, 2 fp, 0 fn).

**Dependências:** E06.3.3.2.1.

**Escopo:** tipo de gramática, laboratório, gramática e habilitação de f02-18 (variantes a decidir no plano, pelo achado da divisão); guarda, teto e pureza; medição nas 16 folhas.

**Fora de escopo:** enrolamentos e triângulo roxo com S.

**Critérios de aceite:**

- [ ] Fixtures sintéticas positivas e negativas de TRANSFORMADOR.
- [ ] Nas 16 folhas, precisão e recall de TRANSFORMADOR em `tmp/`, maiores que os do atual, e leitura errada afirmada de fato = 0.
- [ ] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** o `atual` já tem recall de 100%, então o ganho possível é de precisão. Rede, Dedicado e IP não se distinguem pela forma (ver a divisão).

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** os da E06.3; a folga de gasto (a 016 gasta 189.097 de 200.000 desde a E06.3.3.2.1).

**Evidências e handoff:** —

---

## E06.3.4 — Estai — #pendente

**Objetivo:** reconhecer ESTAI sobre o modelo de desenho, acima do analisador atual.

**Dependências:** E06.3.3.2.2.

**Escopo:** gramática de estai (traço bifurcado, com ou sem envolvente, e o X de retirada), habilitação das variantes de f02-14 e f02-15, laboratório e guarda.

**Fora de escopo:** as outras classes.

**Critérios de aceite:**

- [ ] Fixtures sintéticas positivas e negativas de ESTAI.
- [ ] Nas 16 folhas, precisão e recall de ESTAI em `tmp/`, maiores que os do atual.
- [ ] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** as notas da E06.3 valem aqui. O atual dá ESTAI 64 tp / 2 fp / 12 fn (`centro`) e 0 por IoU, porque sai como polilinha fina.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** os da E06.3.

**Evidências e handoff:** —

---

## E06.3.5 — Equipamento de interrupção — #pendente

**Objetivo:** reconhecer EQUIPAMENTO_INTERRUPCAO sobre o modelo de desenho.

**Dependências:** E06.3.4.

**Escopo:** gramática de interrupção (chevrons e curva sinuosa, f02-20), habilitação das variantes, laboratório e guarda.

**Fora de escopo:** associação ao poste (E07); remover detectores antigos (E09).

**Critérios de aceite:**

- [ ] Fixtures sintéticas positivas e negativas de EQUIPAMENTO_INTERRUPCAO.
- [ ] Nas 16 folhas, precisão e recall de EQUIPAMENTO_INTERRUPCAO em `tmp/`, maiores que os do atual (que não emite a classe: 0 tp, 20 fn).
- [ ] `.venv/Scripts/python.exe -m scripts.audit_symbol_packages` → 0 erros.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:** `cmd.exe //c ".\IniciarTestes.bat"` → `RESULTADO FINAL: APROVADO`.

**Revisão humana:** não

**Notas para o plano:** as notas da E06.3 valem aqui.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:** os da E06.3.

**Evidências e handoff:** —

---

## E15 — Ficha predita a partir das propostas — #concluida

**Objetivo:** dar à ficha predita uma fonte que reflita a leitura, e não a promoção (D5). Assim o baseline real passa a ser informativo.

**Por que agora:** o baseline da E03 é 0/107 postes por construção, porque a promoção automática só confirma cabos. A E07 precisa comparar contra algo que meça a leitura. A etapa não depende da E06 e roda ao mesmo tempo que ela, na trilha B.

**Dependências:** E14.

**Escopo:**
- **Nova `versao_extracao`** do gerador da ficha predita, a partir das propostas: postes, estruturas, equipamentos e cabos propostos. A versão atual (projeto promovido) continua selecionável.
- **Fixtures sintéticas** positiva e negativa: proposta presente vira campo da ficha; proposta ausente ou recusada não vira.
- **Baseline novo** do analisador atual nas 16 folhas, sobre as referências congeladas da E03, em `tmp/` e com denominadores por folha e no total.

**Fora de escopo:**
- mudar o analisador ou a promoção;
- mudar o formato v1 da ficha ou o casamento 0,02/0,05 (D2);
- associação ao poste (E07).

**Critérios de aceite:**

- [x] O relatório de avaliação traz a `versao_extracao` usada, e a versão anterior continua reproduzindo o `baseline-v003`.
- [x] As fixtures sintéticas produzem as métricas esperadas nas duas fontes.
- [x] O baseline novo existe em `tmp/` com denominadores, e o handoff traz os totais por campo e por família.
- [x] Nenhuma ficha, recorte ou nome de folha entra em arquivo versionado (`git grep -n "PROJETO DE REDE NS"` só acha as linhas que citam o critério).
- [x] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.

**Validação obrigatória:**

- `cmd.exe //c IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`.
- Benchmark por poste de E02 sobre as 16 folhas, rodado em paralelo → relatório em `tmp/`.

**Revisão humana:** não

**Notas para o plano:**
- O único gerador hoje é `scripts/benchmark_ficha_poste.py` (`VERSAO_EXTRACAO`, linha 66).
- Na E02, a escolha do projeto promovido foi a ruling R2. Leia as chaves de diagnóstico da raiz com `.get(chave, 0)` (nota da E02).
- A E06 (trilha A) fica aberta junto com esta etapa, na mesma sessão, e mexe em `src/`: esta etapa não toca em `src/` nem em `tests/` compartilhado sem conferir o plano dela.
- Rode o baseline na imagem Docker, que tem o Tesseract, se o plano quiser medir também o caminho com OCR. Sem isso, rode `--native-only`, como na E03.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- Propostas pendentes infladas contam como acerto → a métrica separa campo afirmado de pendente, como no formato v1, e o handoff registra os dois.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-05-leitura-vetorial-por-poste-e15.md`.
  - Revisão de arquitetura (opus) bloqueou nas rodadas 0 e 1 e aprovou com notas na rodada 2:
    - rodada 0: I1 pendência sem mecanismo, I2 entrega virando poste, I3 `CONECTA` a equipamento, I4 import circular, I5 dependência entre tarefas;
    - rodada 1: N1 formato real de `pares`, N2 default de `_executor`.
- Relógio: de ed2759d (15:56) ao commit `#concluida` (18:06 de 2026-11-05): 2h10. Correu em paralelo com a E06.1.
- Entregas:
  - `scripts/ficha_predita_propostas.py`, fonte `propostas-v1` da ficha predita, com estas regras:
    - postes, estruturas (`INSTALADA_EM`), equipamentos (`INSTALADO_EM`) e vãos (`CONECTA` para exatamente 2 postes distintos da ficha) vêm das propostas presentes;
    - `REJEITADA` e ponto de entrega ficam fora;
    - campo de proposta `CONFLITANTE`, ou com chave de pendência da promoção, vai para `pendentes`;
    - atributo hostil vira ausente.
  - `scripts/benchmark_ficha_poste.py`: `--versao-extracao {projeto-promovido-v1,propostas-v1}`, com o default inalterado.
  - `scripts/curation_ficha.py baseline`:
    - `--versao-extracao` e `--processos N`; a saída paralela é igual à serial, com teto de 61 e `BrokenProcessPool` gravando o resumo;
    - chave aditiva `pendencia`, com os acertos afirmados × com pendência dos 4 campos do poste;
    - ficha ilegível conta como ausente.
  - Documentação: `examples/README.md` e o contrato de curadoria (bloco `baseline`).
- Commits (2dd743e..bde10ef, mais o fechamento):
  - roadmap e plano: ed2759d, 7c5d3a9, 68fd0fb, d9bda3a, d2c2f07;
  - Task 1: aa20c5b, 0f5fe87, 6fc67df;
  - Task 2: 087ca74, 9385d28, b8e980d;
  - onda final: 0bd1d0b e bde10ef (gate).
- Ciclo das tarefas: desenvolvedor, testador, verificação mecânica e revisão da `revisor-seguranca`, todas aprovadas.
  - O testador achou defeitos reais nas duas tarefas: atributo hostil derrubava o gerador, e uma `ficha-predita.json` ilegível derrubava o baseline. Cada um custou uma rodada de correção.
- Revisão final (`revisor-seguranca`, opus, 2dd743e..b8e980d): aprovado com ressalvas, sem Crítico.
  - I1 (memória) e I2 (pendência universal) foram para o handoff. M1 (docstring) foi corrigido na onda única 0bd1d0b.
  - Re-revisão da onda (sonnet): M1, contrato e I2 ADDRESSED, sem quebra nova; a correção do gate (bde10ef) foi re-revisada (haiku): ADDRESSED.
- Critérios verificados:
  1. `versao_extracao` no relatório: está em `gerador.versao_extracao` das 16 `ficha-predita.json` e `avaliacao.json` e em `opcoes.versao_extracao` dos resumos. A fonte anterior reproduz a `baseline-v003`: a `baseline-v005` (`projeto-promovido-v1`) tem `total`, `por_pdf` e `gerador` iguais aos da v003, conferido por script e linha a linha pela revisora. A suíte existente passa sem edição.
  2. Fixtures sintéticas nas duas fontes: `test_metricas_nas_duas_fontes` dá tp 0 na promovida e tp 2/fp 0 nas propostas. Positivos e negativos estão em `tests/unit/test_ficha_predita_propostas*.py`.
  3. Baseline novo em `tmp/curadoria-simbologia/20261103-2300-fichas/fichas/baseline-v004-resumo.{json,md}`, com denominadores por PDF e no total. Rodou `--native-only --processos 6` em 119 s.
     - Total: postes tp 43, fp 41, fn 64 (recall 40,2%, precisão 51,2%); vãos 19/83 (fp 37), comprimento 13/19, cabo 0/19; símbolos 0/179.
     - Campos: identificador 43/43, poste 42/43, coordenada 40/43, estruturas 0/43.
     - Pendência: todos os acertos são **com pendência** (afirmados = 0).
     - Por família (postes rec/prec; vãos): electric_office_print (8) 30/59 e 30/50, vãos 15/44; itext (6) 5/37 e 5/20, vãos 1/31; ghostscript (1) 8/10 e 8/8, vãos 3/8; autocad (1) 0/1 e 0/6.
     - Contagens extras da v004: `cabos_sem_vao` 68, `estruturas_sem_poste` 7, `postes_entrega` 3.
  4. `git grep -n "PROJETO DE REDE NS"`: só acha as linhas que citam o critério (roadmap 565, 610 e 1067; planos E03 e E15).
  5. `.bat`: `cmd.exe //c IniciarTestes.bat` em bde10ef → `RESULTADO FINAL: APROVADO`: 6594 passed, 1 xfailed, cobertura 88,80%, 229 s. O 1º `.bat` (0bd1d0b) reprovou em `test_contrato_e_skill_executam_os_mesmos_clis`, por causa de um exemplo de CLI que a onda final pôs no contrato e a skill não executa. Foi corrigido em bde10ef.
  - Suíte inteira `-n 6` em b8e980d: 6594 passed, 1 xfailed (preexistente).
  - `osv-scanner` nos 7 locks: `No issues found` (nenhum lock mudou).
  - `check_test_integrity --base 2dd743e`: 5 `SEM_SOUL` (commits docs do orquestrador com os trailers separados por linha em branco) e 1 `SKIP_ADICIONADO` (premissa do limite de 61 do Windows), todos justificados.
- Decisões para o usuário (tomadas pela opção recomendada):
  - **Default `projeto-promovido-v1`**: a fonte nova é pedida com `--versao-extracao propostas-v1`, e a E07 deve passar o flag.
  - **Pendente = proposta `CONFLITANTE` ou com chave de pendência da promoção.** No dado real, isso marca **todos** os postes. A causa foi diagnosticada na onda final: `mark_conflicts` (`relation_rules.py:26-44`) marca `CONFLITANTE` o poste que divide evidência de texto com uma estrutura ou um equipamento. Em 006, 012 e 014, 9, 8 e 3 postes estão todos `CONFLITANTE`, sem nenhuma chave de pendência e sem tipo de catálogo sugerido, e por isso nunca são promovidos. A alavanca para "afirmado" está na interpretação (E07), não no gerador.
  - **Zeros de estruturas (0/43) e de cabo (0/19):** as estruturas são anexadas, mas o avaliador compara a lista e o texto com igualdade estrita (`ficha_poste_avaliador.py:153-163, 297-298`).
  - **Separação afirmado × pendente só para os 4 campos do poste:** vãos e símbolos ficam sem separação (R-E15-3, opção b versionada).
  - **Pico de memória por processo: não medido.** O baseline não mede memória, e o `tracemalloc` não vê a memória nativa do MuPDF. As 6 folhas simultâneas rodaram ao lado da E06.1 sem falha.
  - **Símbolos 0 por construção nas duas fontes:** `run_variant` não passa símbolos. A E06/E07 não deve ler esse 0 como medida da leitura.
  - **Atributo hostil vira ausente** (R-E15-9), e ficha ilegível conta como ausente no baseline (R-E15-12).
  - **Testes do cliente intermitentes sob carga** (`test_project_panel_polling_restart*`, `test_application_factory_teardown`): vistos várias vezes com 3 suítes simultâneas, fora do diff. Vão para a E17.
- Notas para a próxima etapa:
  - Minors adiados: distância menor que 0,005 m vira `comprimento_m None` (a promoção grava 0.0); `simbolo_classe` sem `strip` (avise a E06 quando ela alimentar a classe); estrutura ou equipamento com várias relações usa a primeira; `main` só repassa `versao_extracao` quando ela difere do padrão; `_pendencia_do_pdf` supõe `par` dict; pool quebrado pode deixar pasta de PDF marcado como falha (`gerador` igual nos 16, sem impacto hoje); `**opcoes: Any`; alias `CAMPOS_COM_PENDENCIA`.
  - Dois testes da E15 dependem de `src/`: `test_chaves_de_pendencia_iguais_as_da_promocao` lê `automatic_promotion.py`, e o spawn real espera tp > 0. Rode a suíte na `main` depois de integrar as trilhas.
  - Retomada: a E07 depende da E06.3 e da E15. A E15 está pronta para integrar no fim do lote.
---

## E07 — Ficha do poste — #pendente

**Objetivo:** associar texto, símbolos e vãos ao poste certo e expressar a ficha nas propostas e relações atuais.

**Por que agora:** a associação é um dos erros que mais custam ao usuário. Com texto e símbolos limpos, ela passa a ser geométrica.

**Dependências:** E06.3.5 (última subetapa da E06.3), E15.

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

**Notas para o plano:**
- `application/symbol_reconciliation.py`, `analysis_regions.py` e `spans.py` já fazem associação e vãos. Decida no plano o que é reaproveitado e o que é substituído.
- Compare contra o baseline das propostas da E15, não contra o 0/107 do projeto promovido.
- Os limiares de associação calibrados nas 16 folhas são candidatos a laboratório.

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

## E16 — Conjunto de avaliação cego — #bloqueada

**Objetivo:** fichas de referência das folhas novas reservadas pelo usuário (H4), lidas às cegas e congeladas antes de qualquer predição. É a prova da E09.

**Por que agora:** a leitura não depende do código das E06–E08. Ela pode rodar em paralelo, na trilha B, assim que as folhas chegarem, em vez de alongar a E09.

**Dependências:** E03.

**Escopo:**
- **Pasta:** as folhas ficam em `examples/avaliacao-cega/`, ignorada pelo Git, onde o usuário as coloca.
- **Leitura:** o fluxo da E03 (leitores A e B em modo ficha, leitor C nas divergências, consolidação sem palpite), já com a convenção de não registrar ponto de ligação do cliente como poste (E03).
- **Amostra humana** com taxa de erro e intervalo de Wilson, como na E03.
- **Congelamento** das referências (sha em `congelamento.json`) antes de qualquer execução de analisador sobre essas folhas.
- **Guarda:** nenhum benchmark, laboratório, fixture ou etapa lê a pasta antes da comparação da E09.

**Fora de escopo:**
- predição ou benchmark sobre as folhas novas (E09);
- treino (E10, E12).

**Critérios de aceite:**

- [ ] Toda folha de `examples/avaliacao-cega/` tem referência congelada, com escopo de anotação declarado. O relatório local traz a família de cada folha.
- [ ] A amostra conferida pelo usuário e a taxa de erro de rótulo estão no relatório local.
- [ ] O relatório da rodada prova que nenhum analisador rodou sobre essas folhas antes do congelamento: não há `ficha-predita.json` nem cache de modelo de desenho delas com data anterior ao sha congelado.
- [ ] Nenhuma ficha, recorte ou nome de folha entra em arquivo versionado.
- [ ] `.\IniciarTestes.bat` → `RESULTADO FINAL: APROVADO`, se a etapa mudou código ou documento versionado.

**Validação obrigatória:**

- Inspeção manual: o usuário confere a amostra de fichas sobre os recortes renderizados.

**Revisão humana:** sim

**Notas para o plano:**
- Pendências acionáveis da E03 que valem aqui:
  - o recorte da amostra com margem 0,12 (o CLI `amostra` usa 0,04 e corta o rótulo);
  - a recuperação manual quando um comando cai no meio;
  - o leitor A/B não pode abrir `regioes-conferencia.json`.
- Os leitores visuais rodam na sessão do orquestrador (D4), em ondas da skill de curadoria.

**Bloqueios:**
- **Causa:** as folhas novas ainda não foram reservadas (H4).
- **Evidência:** resposta do usuário na entrevista de 2026-11-04 ("consigo em breve").
- **Impacto:** sem a E16, a E09 não tem prova cega e não pode começar.
- **Ação de desbloqueio:** o usuário coloca as folhas novas em `examples/avaliacao-cega/` do checkout principal, sem abri-las no analisador. Depois é preciso registrar a entrega em H4 e trocar a tag para `#pendente`.

**Riscos e mitigação:**

- Poucas folhas ou uma família ausente → o relatório declara a cobertura por família, e a E09 compara só onde há folha.

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

**Dependências:** E08, E16.

**Escopo:**
- **Conjunto de avaliação:** as referências congeladas da E16, sem nova leitura.
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

**Notas para o plano:**
- A inspeção na UI exige `.env` com a string ODBC do SQL Server de mercado. Isso já bloqueou uma etapa antes, então confira cedo.
- A troca e a remoção juntas tendem a passar de ~3h: o orçamento do protocolo divide a etapa, e a remoção vai na última subetapa, depois da troca medida (ver "Rollback / migração").

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

## E11 — Spike de treino na GPU AMD — #concluida

**Objetivo:** decidir onde e como treinar o detector, provando ou descartando PyTorch com ROCm na RX 9070 XT desta máquina (H5).

**Por que agora:** a viabilidade do treino local decide o custo e o desenho de E12. O spike prova a cadeia treino → ONNX → CPU e não precisa do volume da fábrica (E10). Por isso roda já, na trilha C, ao mesmo tempo que a trilha A (D6).

**Dependências:** E01.

**Escopo:**
- Ensaio, fora do produto, de um treino mínimo de detecção com licença Apache, BSD ou MIT na GPU, nativo no Windows e/ou via WSL2. O conjunto mínimo é sintético ou vem de recortes das referências da E03 em `tmp/`, nunca do conjunto cego (E16).
- Exportação para ONNX e inferência em CPU com ONNX Runtime.
- Medição de tempo.

**Fora de escopo:** código de produção; dependência nova nos locks do servidor.

**Critérios de aceite:**

- [x] A decisão está registrada no ADR 0017, com o caminho escolhido (ROCm nativo, WSL2, CPU ou GPU alugada), versões, tempos medidos e alternativas descartadas.
- [x] Um modelo mínimo exportado para ONNX roda em CPU com ONNX Runtime.

**Validação obrigatória:**

- Inspeção manual: tempos e versões do ensaio no handoff.

**Revisão humana:** sim

**Notas para o plano:**
- Spike sem código de produção. Os scripts do ensaio ficam fora de `src/` e o lock de treino é opt-in.
- A instalação de ROCm/PyTorch pede confirmação do usuário.
- Na onda 1, a E14 mexe em `pyproject.toml`, nos locks e em `tests/`. O lock opt-in e os scripts do ensaio não podem tocar nesses arquivos enquanto ela estiver em andamento, inclusive `tests/unit/test_dependency_locks.py`.

**Bloqueios:** Nenhum bloqueio conhecido.

**Riscos e mitigação:**

- ROCm sem suporte à GPU → registrar e propor D1 ao usuário, por entrevista.

**Evidências e handoff:**

- Plano: `docs/superpowers/plans/2026-11-05-leitura-vetorial-por-poste-e11.md` (revisão de arquitetura: aprovado com notas, 1 rodada).
- Commits: `9071cc9..460e9a2` na branch `roadmap/leitura-vetorial-por-poste-c` (relógio de 00:33 a 05:34, ≈ 5h01, acima das 4h30; parada tratada como "continuar" pela delegação do usuário).
- Revisão final: aprovada com ressalvas de documentação, corrigidas em `460e9a2` e re-revisadas (5/5 resolvidas). Suíte com cobertura: 6295 passed, 1 xfailed, 88,81%. ruff, format, mypy, `client_artifact_gate` e `complexity_gate` aprovados. `osv-scanner` sobre `requirements-treino.lock`: 19 pacotes, nenhum achado.
- Critérios verificados:
  - ADR 0017, seção "Caminho de treino (E11)": caminho **CPU**, escolhido pela regra pura `scripts/treino_detector/decisao.py` aplicada aos relatórios.
  - ROCm nativo: torch 2.9.1+rocm7.2.1, HIP 7.2.53211, Python 3.12.10, driver 26.20.15.07. Ensaiado e inviável: `miopenStatusUnknownError` no BatchNorm de treino, porque o MIOpen 7.2.1 não compila o kernel para a gfx1201 (`'type_traits' file not found`).
  - WSL2: não ensaiado (o harness recusou `wsl.exe`).
  - GPU alugada: desnecessária.
  - CPU com torch 2.9.1+cpu (i7-12700KF): 22,3 img/s sem carga, 7,5 h na carga de referência.
  - CPU com o lock final (torch 2.14.1+cpu, sob carga externa): 15,8 img/s e 10,5 h, abaixo das 12 h da regra.
  - Modelo `ssdlite320_mobilenet_v3_large`: qualidade 0,99/0,90.
  - Cadeia ONNX: exportação ONNX (TorchScript, opset 18) e paridade com o PyTorch em CPU (0 divergentes em 20 imagens). ONNX Runtime em CPU: 5,0/6,6 ms por ladrilho (mediana/p95), estimativa de 4,4 s por folha A1, contra 60 s da E12.
- Decisões para o usuário (tomadas pela opção recomendada, por delegação do prompt; reversíveis):
  - Instalação sem confirmação explícita: pip em venvs sob `tmp\treino-e11\` e Python 3.12 extraído por `py install -t` (nada no sistema). Recomendado e adotado: ratificar.
  - Evidências em `tmp\treino-e11\` do checkout principal, gravadas por `cp` quando a ferramenta Write recusou o caminho. Recomendado e adotado: ratificar.
  - GPU AMD. Recomendado e adotado: a E12 treina em CPU. A GPU volta quando a AMD publicar release para Windows com o MIOpen corrigido: reensaiar com `ensaio` + `decisao` a partir do apêndice do ADR.
  - Contornos ROCm (MIOpen desligado no BatchNorm, nightly TheRock, WSL2 com distro) ficam como alternativas. Não foram ensaiados.
- Notas para a próxima etapa:
  - E12: usar `requirements-treino.lock` (CPU, modo hash, Python 3.11) e `python -m scripts.treino_detector.ensaio`.
  - A guarda `test_nenhum_lock_de_runtime_fixa_onnxruntime` (`tests/unit/test_treino_detector_sonda_guardas.py`) vai exigir mudança explícita, justificada no commit, quando a E12 puser `onnxruntime` no lock do servidor.
  - Na integração com a E14 (trilha A), rodar de novo `tests/unit/test_dependency_locks.py` sobre o `main`.
  - Ambientes e relatórios do spike ficam em `tmp\treino-e11\` (fora do Git, podem ser apagados).

---

## E12 — Detector visual local — #pendente

**Objetivo:** treinar e integrar um detector local para o resíduo que o vetor não resolve, com ganho medido por poste (decisão 5 do design, ADR 0017).

**Por que agora:** é a última camada de precisão, com o volume de E10 e o caminho de treino de E11.

**Dependências:** E11, E09, E10.

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
- 2026-11-05 — execução acelerada (D6, design `2026-11-04-execucao-acelerada-leitura-vetorial-design.md`):
  - o índice passa a ser por trilhas paralelas A/B/C, com ondas;
  - o protocolo ganha trilhas, laboratório, orçamento de ~3h e duas paradas novas;
  - o prompt passa a ser parametrizado por trilha;
  - etapas novas: E14 (gate paralelo, antes da E06), E15 (ficha predita das propostas, que sai da E07, D5) e E16 (conjunto cego, que sai da E09, `#bloqueada` por H4);
  - a E11 deixa de depender da E10, e a E12 passa a depender explicitamente da E10;
  - ficam pendentes as propostas para as souls (D8).
- 2026-11-05: E17 (fechamento do cliente com servidor lento) incluída na Trilha A, depois da E14, por decisão do usuário sobre o achado I-1 da revisão final da E14.
- 2026-11-05 — D8 decidida pelo usuário (sessão do vault):
  - souls com suíte por fase, testador condicional, tarefas de até ~45 min e ondas paralelas;
  - intervenções decididas pela opção recomendada, e só arquitetura espera o usuário;
  - o lote termina com merge local na `main`, sem push;
  - protocolo (papéis, retomada, estouro, paradas, fim do lote) e prompt atualizados.
- 2026-11-05 — revisão do arquiteto depois da D8, para alinhar o roadmap às souls novas e à decisão do usuário de ter um orquestrador por vez (D11):
  - uma sessão de orquestrador executa todas as trilhas, com até 2 etapas abertas ao mesmo tempo; o prompt perde o parâmetro de trilha, e escolha, paradas e fim do lote passam a valer para a sessão;
  - "Como usar" deixa de reservar a integração ao usuário; a integração segue a D8 e não mais o design de execução acelerada; os rebases de branch de tarefa nas ondas ficam permitidos;
  - o protocolo e o prompt ganham o "Orçamento de máquina" (D9);
  - a E17 passa da trilha A para a C (D10);
  - "Ondas" do índice passam a se chamar "Janelas", e a janela 1 fica registrada como concluída;
  - o plano de cada etapa traz os campos por tarefa do `orquestrador`, e o escopo passa a listar a E17.
