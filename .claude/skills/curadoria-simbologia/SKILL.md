---
name: curadoria-simbologia
description: Conduz uma rodada de curadoria de simbologia sobre os PDFs de examples/ em ondas de 3 a 5 PDFs processados em paralelo, com leitores e auditores visuais cegos, comparação regional determinística, backlog agregado por causa, correções por pista com fixtures sintéticas e publicação da matriz de cobertura só com os gates aprovados. Use quando o usuário pedir para curar, reler ou medir a leitura de símbolos dos PDFs de examples/ ou invocar /curadoria-simbologia.
---

# Curadoria de simbologia em ondas

Esta skill é executada pela **sessão de nível superior** (a orquestradora). Ela roda os CLIs
de `scripts/`, distribui o trabalho visual e de correção entre subagentes e integra tudo em
série. O contrato do fluxo está em `docs/fluxo-curadoria-incremental-simbologia.md`; esta
skill é o procedimento operacional. Toda a rodada vive em `tmp/curadoria-simbologia/` (fora
do Git); no repositório só entram correções de código, pacotes, inventário, fixtures e
testes, e a matriz de cobertura publicada no fechamento.

## Limites que valem para a rodada inteira

- PDFs reais, PNG, referências, comparações e relatórios ficam só em
  `tmp/curadoria-simbologia/` (ADR 0005). Nada disso vai para `tests/`, `docs/` ou fixtures.
- A referência visual é congelada **antes** de qualquer comparação, e o leitor nunca recebe o
  caminho das inferências. O detector recebe só o PDF e a configuração normal.
- O Claude Code restringe ferramentas por agente, não caminhos: a cegueira depende de a
  orquestradora **nunca** passar a leitores e auditores caminhos de `inferencia-*`,
  `comparacao-*`, `concordancia-*`, `auditoria/`, backlog ou checkpoints, das instruções dos
  agentes e do registro de exposição feito por `curation_reference` (`congelar` grava
  exposição falsa; `revisar` exige a declaração explícita).
- Referência gerada por IA não é gabarito, confirmação humana nem norma; a concordância mede
  consistência entre duas leituras de IA. Ambiguidade é uma ocorrência com alternativas;
  legenda, norte e símbolos informativos são informativos.
- Método indisponível, com `falha` ou sem registro de execução é **falha**, não zero.
- Reservas independentes já abertas não servem para ajuste nem como teste cego.
- A skill distribui todo o trabalho a partir da sessão principal: os subagentes recebem
  tarefas fechadas e não delegam a outros subagentes.
- **Nunca faça commit**, push, deploy ou publicação externa. Ao terminar, mostre
  `git status --short` e deixe a revisão do diff para o usuário.

## Papéis e modo de reserva

| Agente | Quando | Como disparar |
|---|---|---|
| `curadoria-leitor-visual` | um por PDF sem referência, na fase Ler | segundo plano, N em paralelo |
| `curadoria-auditor-visual` | um por PDF amostrado, na fase Auditar | segundo plano, N em paralelo, instância nova |
| `curadoria-investigador` | um por grupo priorizado do backlog | segundo plano, até N em paralelo |
| `curadoria-corretor` | um por pista com causa confirmada | em série, na árvore principal, uma pista por vez |
| `curadoria-verificador` | um por pista integrada | instância nova, depois da integração |

Dispare com a ferramenta Agent (`subagent_type` = nome do agente, `run_in_background: true`
para o paralelismo) e mande todas as chamadas paralelas na mesma mensagem. Corretores e
verificadores nunca rodam em paralelo. Não passe o parâmetro `model`: os subagentes
herdam o modelo ativo da sessão, e nenhum papel troca para outro modelo por economia. O "nome
do modelo" passado a leitores e auditores é o identificador que a sessão expõe; se ela não
expuser nenhum, passe `indisponivel` e registre isso no relatório, sem inventar nome ou versão.

**Modo de reserva.** Agentes criados ou alterados durante a sessão podem não estar
registrados nela. Se o `subagent_type` não for aceito (ou `/agents` não listar os cinco
`curadoria-*`), dispare um subagente `general-purpose` cujo prompt seja o **corpo inteiro** de
`.claude/agents/NOME.md` (tudo depois do frontmatter), seguido do bloco de entrada da tarefa
e da linha "use apenas as ferramentas: LISTA", com a lista do campo `tools` do arquivo. As
proibições do agente valem do mesmo jeito; não resuma nem omita a seção "Proibido".

Os agentes `curadoria-*` registrados usam a definição carregada no início da sessão. Se algum
arquivo de `.claude/agents/` for alterado durante a rodada, os disparos seguintes daquele papel
usam o modo de reserva com o corpo atual do arquivo, e as regras novas vão por mensagem
(SendMessage) aos agentes desse papel que já estão em execução.

**Limite de subagentes simultâneos.** O ambiente pode recusar um disparo por limite de
subagentes em execução. Nesse caso, espere a notificação de término de um deles antes de
disparar o próximo e não dispare de novo um agente que já está em execução (nem duplique a
tarefa dele em outra instância).

**Regras gerais de leitura** (passe-as no bloco da tarefa de todo leitor e auditor; elas não
trazem nada do PDF e não quebram a cegueira):

- Critério de estado: `sustentado_por_evidencia` quando a família/classe é determinada pela
  evidência; dúvida só da variante exata vai em `alternativas`; `provisorio` só quando a
  presença do elemento ou a sua classe dependem de suposição.
- Completude: registre todo elemento de rede visível nos tiles revisados.
- Camada anotada: o desenho comum às duas camadas fica só na `base`; na `annotation` entra
  apenas o que existe só na anotação.
- Extensão da bbox: em aterramento e para-raios, o pictograma (envolvente e barras), sem a
  linha de ligação até o poste; em transformador, o símbolo, sem o rótulo de texto. Em discos e marcas pequenas (1 a 5 pt), a bbox cobre só a marca (preenchimento e contorno), justa, sem rótulo, linha, círculo de identificação nem moldura vizinha: um pixel de folga a 400 dpi já derruba o IoU abaixo de 0,5. Em estai de âncora, a bbox vai do centro do poste até o fim do símbolo (haste e círculo ou forquilha incluídos), uma por estai.

## Parâmetros

- `N` (PDFs por onda e `--jobs`): 3 por padrão, sempre entre 3 e 5; o CLI aceita até 5. Com
  falta de memória, repita os PDFs que falharam com `--jobs` menor e registre no relatório.
- Limiar de concordância 0,90 e fração da amostra 0,15 (padrões de `curation_audit`).
- Toda inferência da rodada (inicial, reinferências e regressão) usa `--pipeline`, que roda
  também `benchmark_network_pdf` (leitura/interpretação nativa e OCR, runtime padrão
  `tmp/benchmark-runtime`). Se o OCR português não estiver disponível (o `pipeline.log` diz
  "OCR português obrigatório"), a rodada inteira passa a `--pipeline --native-only`: refaça as
  inferências já feitas com essa opção e registre o OCR como pendência no relatório; uma
  execução `--native-only` não aprova OCR. Nunca instale nem baixe modelos de OCR. Os mesmos
  `--metodos` (o padrão roda todos os métodos opcionais) e as mesmas opções de pipeline valem em
  todas as inferências da rodada.
- Correção: no máximo dois ciclos de correção por onda. Divergência acionável que sobrar não
  some: vai para "Pendências acionáveis" do relatório com impedimento comprovado ou dono e
  próximo dado (ver a fase 9).
- `RODADA` nos comandos abaixo é o caminho literal `tmp/curadoria-simbologia/AAAAMMDD-HHMM`
  (nome único da rodada); `ID`, `K` e `vNNN` também são valores literais. Não use variáveis
  de shell: os comandos literais casam com as permissões de `.claude/settings.json`. Rode os
  CLIs pela ferramenta Bash (Git Bash), na raiz do repositório.

## Preparação da rodada

1. Leia `CLAUDE.md` e rode `git status --short`; preserve mudanças preexistentes.
2. Rodada anterior: a mais recente em `tmp/curadoria-simbologia/` com `rodada.json`, se
   existir. Crie a rodada (reuso das referências de PDFs inalterados é o padrão; use
   `--sem-reuso` só se o usuário pedir releitura total):

   ```bash
   .venv/Scripts/python.exe -m scripts.curation_round init --rodada RODADA --raiz examples --concorrencia N --anterior RODADA_ANTERIOR
   .venv/Scripts/python.exe -m scripts.curation_round status --rodada RODADA --json
   ```

   Sem rodada anterior, omita `--anterior`.
3. Matriz de partida: copie `docs/data/matriz-simbologia-curadoria-atual.csv` ou, se ela não
   existir, `docs/data/matriz-simbologia-e16.csv` para `RODADA/matriz-antes.csv`, registre
   qual foi copiada e o SHA-256, e gere a fila de lacunas:

   ```bash
   .venv/Scripts/python.exe -m scripts.curation_coverage_e16 plan --matrix RODADA/matriz-antes.csv --output RODADA/plano-lacunas.json
   ```

4. **Checkpoint sintético inicial**, antes de qualquer correção da rodada (métodos isolados,
   união e composição), para o confronto inicial × final do fechamento:

   ```bash
   .venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output RODADA/inicial/baseline
   .venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output RODADA/inicial/uniao
   .venv/Scripts/python.exe -m scripts.reconcile_symbol_benchmark --predictions RODADA/inicial/uniao/predictions.json --reference RODADA/inicial/uniao/reference.json --exclude-method structural-raster-graph --exclude-method structural-vector-graph --output RODADA/inicial/composicao
   ```

5. Rodada anterior com `relatorio.md`: leia a seção "Pendências acionáveis" dela. Os ids
   `grp-...` são estáveis; quando um desses grupos reaparecer num backlog desta rodada, ele é
   investigado antes dos demais de mesma prioridade, com o impedimento e o próximo dado
   registrados.
6. Abra `RODADA/relatorio.md` com o corpus, as ondas, N, a matriz de partida (arquivo e
   SHA-256), as opções de inferência e o horário de início. Anote no relatório o início e o fim
   de cada fase de cada onda e os `duracao_s` dos CLIs.

## Retomada após compactação ou interrupção

`rodada.json` e os checkpoints são a fonte da verdade. Ao retomar, rode
`curation_round status --rodada RODADA --json`, releia `RODADA/relatorio.md` e continue pela
primeira ação que falta em cada PDF: sem marco `renderizado`/`inferido` → Preparar; sem
referência → Ler; sem `comparado` vigente → Medir; sem `auditado` → Auditar; onda sem
`ondas/K/backlog.json` atualizado → Agregar; PDF em `em_correcao` → retomar a pista
registrada no relatório. Nunca recrie uma rodada existente.

## Ciclo de cada onda K

### 1. Preparar (CLIs em paralelo)

Dispare os dois comandos ao mesmo tempo (duas chamadas Bash em segundo plano):

```bash
.venv/Scripts/python.exe -m scripts.curation_render --rodada RODADA --onda K --jobs N
.venv/Scripts/python.exe -m scripts.curation_infer --rodada RODADA --onda K --jobs N --pipeline
```

O padrão de `--dpi-detalhe` de `curation_render` é 400 (a 200 dpi os símbolos de rede de
folhas A4/A3 ficam ilegíveis na leitura visual); não o reduza. Acrescente `--native-only` em
todas as inferências se a rodada estiver sem OCR (ver "Parâmetros"). PDF com `falha`: leia o
log, repita com `--pdf ID`; falha persistente vira pendência do PDF. PDF com
`sucesso_parcial` (só métodos falharam: predições válidas e falhas com `method_id`, presentes
também em `executions`) avança para `inferido` com `falhas_metodos`: os demais métodos são
medidos, e o método que falhou é medido como falha, não zero; registre-o no relatório. A
leitura de um PDF pode começar assim que a renderização dele terminar, sem esperar a
inferência.

### 2. Ler (leitores visuais em paralelo)

Para cada PDF da onda sem referência (os reutilizados por hash já chegam com
`referencia_congelada`), dispare `curadoria-leitor-visual` passando **apenas**: `RODADA`,
`ID`, `sha256`, `caminho_relativo`, o nome do modelo, a saída
`RODADA/pdfs/ID/leitura/referencia.json` e as regras gerais de leitura (ver "Papéis e modo de
reserva"). Quando cada leitor voltar, valide e congele:

```bash
.venv/Scripts/python.exe -m scripts.curation_reference validar --rodada RODADA --pdf ID --arquivo RODADA/pdfs/ID/leitura/referencia.json
.venv/Scripts/python.exe -m scripts.curation_reference congelar --rodada RODADA --pdf ID --arquivo RODADA/pdfs/ID/leitura/referencia.json
```

Não edite a leitura do leitor antes de congelar. Leitura incompleta volta ao mesmo leitor
(SendMessage) antes do congelamento.

### 3. Medir (CLI)

Com inferência e referência congeladas em todos os PDFs da onda:

```bash
.venv/Scripts/python.exe -m scripts.curation_compare --rodada RODADA --onda K
```

Recusa indica entrada faltando ou adulterada: corrija a causa, não contorne. Em escopo
regional não existe revocação global; relate só `revocacao_regional` e os denominadores.

A comparação (esquema `curadoria-comparacao-v2`) conta o FN_IA de cada método só nas
`supported_classes` dele, e o FP_IA sobre todas as predições do método. O FN da união cuja
classe nenhum método cobre vira divergência `sem_metodo` (lacuna de cobertura, não defeito de
método). Método sem `supported_classes` gera alerta e é medido contra todas as ocorrências.
O detector vetorial legado reporta aterramento e para-raios pela bbox do pictograma, a mesma
convenção da leitura; a extensão da haste fica em `simbolo_limites_suporte`.

### 4. Auditar (auditores visuais em paralelo)

Pode rodar junto com a fase Medir, pois depende só da renderização e da referência:

```bash
.venv/Scripts/python.exe -m scripts.curation_audit amostrar --rodada RODADA --onda K
```

A população da amostra exclui os tiles anotados com os mesmos bytes do gêmeo da base (e a
camada anotada de página igual à base). Para cada PDF, leia
`RODADA/pdfs/ID/auditoria/amostra-vNNN.json` e o índice de tiles e monte
a ficha da amostra: para cada tile amostrado, `id`, `arquivo`, `pagina`, `camada`, `bbox`,
`largura_px` e `altura_px` — **sem** `estado`, `ocupacao`, estratos ou contagens. Dispare um
`curadoria-auditor-visual` novo por PDF com `RODADA`, `ID`, `sha256`, `caminho_relativo`,
modelo, versão da amostra, a ficha, as regras gerais de leitura e a saída
`RODADA/pdfs/ID/leitura-auditoria/amostra-vNNN.json`. Depois:

```bash
.venv/Scripts/python.exe -m scripts.curation_audit concordancia --rodada RODADA --pdf ID --auditoria RODADA/pdfs/ID/leitura-auditoria/amostra-vNNN.json
```

- `referencia_confiavel`: segue.
- `ampliar_amostra`: `curation_audit amostrar --rodada RODADA --pdf ID --ampliar`, novo
  auditor (instância nova) sobre a nova amostra e nova `concordancia`.
- `encerrar_com_pendencia`: o PDF fecha com pendência; as divergências dele não justificam
  correção sozinhas:

  ```bash
  .venv/Scripts/python.exe -m scripts.curation_round avancar --rodada RODADA --pdf ID --fase encerrado_com_pendencias --nota "concordância abaixo do limiar na amostra ampliada"
  ```

- `alerta: falha_triagem`: registre a pendência de triagem (limiar de ocupação de
  `curation_render`) no relatório.

Registre a concordância de classe e de ID exato de cada PDF, com os denominadores. Como a
concordância (esquema `curadoria-concordancia-v2`) mede:

1. Da referência, avalia o mesmo conjunto da comparação: observação operacional, sustentada e
   com família do inventário.
2. Do lado do auditor, casa qualquer observação operacional com família do inventário que não
   seja ilegível.
3. Divergência só de estado com a mesma classe é diagnóstico (`estado_divergente`) e não conta.
4. Par avaliável × observação não operacional ou `local-unknown` no mesmo lugar diverge.
5. As bboxes são recortadas à região contígua de tiles amostrados que tocam, e a observação
   entra pelo centro da bbox recortada.
6. Classes lineares (`CABO_AEREO`) são comparadas por cobertura de comprimento, não por IoU
   (tolerância e cobertura mínima documentadas em `scripts/curation_audit.py`); ID exato não é
   medido para elas.
7. `fora_do_denominador` lista o que ficou de fora, com contagem por motivo; consulte-o antes
   de atribuir uma concordância baixa à referência.

### 5. Agregar (CLI)

Primeiro atualize a demanda visual da rodada: acrescente a `RODADA/demanda.json`, no formato
`{"ids": ["ID_DO_INVENTARIO"]}`, os IDs observados nas referências congeladas da onda
(`id_inventario` e `alternativas.ids_inventario`) e os IDs confundidos nas comparações
(`id_errado`), sem inventar ID para elemento fora do inventário (esses ficam como desconhecidos
no relatório). Regere a fila de lacunas com a demanda; IDs sob demanda sobem na fila sem
receber status novo:

```bash
.venv/Scripts/python.exe -m scripts.curation_coverage_e16 plan --matrix RODADA/matriz-antes.csv --demand RODADA/demanda.json --output RODADA/plano-lacunas.json
```

Depois da concordância de todos os PDFs da onda:

```bash
.venv/Scripts/python.exe -m scripts.curation_backlog --rodada RODADA --onda K
```

Leia `RODADA/ondas/K/backlog.md` (e o `.json` quando precisar dos detalhes). Trate primeiro
os alertas e as `falhas_execucao`: método com `falha` é falha de execução a corrigir antes
dos grupos do mesmo método; `metodo_sem_registro` e `metodo_sem_dono` são problemas de
configuração ou de mapeamento que a orquestradora resolve; `referencia_nao_auditada` rebaixa
o grupo para hipótese. Os alertas da comparação (como `metodo_sem_classes_suportadas`) chegam
repassados com o PDF. A seção `lacunas_de_cobertura` (esquema `curadoria-backlog-v2`) reúne os
FN `sem_metodo` por família e `class_id`: ficam fora dos grupos, das pistas e de `sem_dono`,
não vão a investigadores nem corretores e entram no relatório como lacunas de cobertura.

### 6. Investigar (investigadores em paralelo)

Ordem de investigação: a `prioridade` do backlog, com dois ajustes — sobem para a frente os
grupos que reaparecem das "Pendências acionáveis" da rodada anterior e os grupos cuja
família/classe tem IDs que estão ao mesmo tempo em `demanda.json` e na fila de
`plano-lacunas.json` (cruzamento demanda × lacunas). Nessa ordem, dispare um
`curadoria-investigador` por grupo (até N por vez), com
o trecho do grupo no backlog e os caminhos vigentes de comparação, referência e inferência
de cada PDF envolvido (do marco do checkpoint, nunca "a de maior número"); quando o grupo
envolve texto, atributo, quantidade ou relação, passe também o `pipeline.json` da inferência
vigente. Resultados:

- `causa_confirmada`: o grupo entra na pista dele para correção.
- `referencia_errada`: monte a nova versão a partir da leitura congelada, com a evidência, em
  `RODADA/pdfs/ID/leitura/referencia-revisao-NN.json`, e revise declarando exposição. Quem
  viu predições, comparações ou auditorias do PDF — inclusive de uma duplicata dele (mesmo
  SHA-256 em outro caminho) — declara `--exposicao sim`; na dúvida, `sim`. Revisão orientada
  pela investigação, que viu predições, declara `--exposicao sim` e só muda o que os pixels dos
  tiles confirmam:

  ```bash
  .venv/Scripts/python.exe -m scripts.curation_reference revisar --rodada RODADA --pdf ID --arquivo RODADA/pdfs/ID/leitura/referencia-revisao-NN.json --motivo "MOTIVO COM EVIDÊNCIA" --exposicao sim
  ```

  Depois, refaça `concordancia` com a mesma leitura do auditor contra a versão vigente (a nova
  versão invalida `comparado` e `auditado`) e `curation_compare --rodada RODADA --pdf ID`. Se
  uma concordância anterior do PDF decidiu `encerrar_com_pendencia`, essa decisão é terminal
  para a auditoria: não recalcule a concordância e mantenha o PDF encerrado com pendência.

- `causa_refutada` ou `indeterminada`: pendência no relatório, sem correção.

### 7. Corrigir (corretores por pista)

Selecione as pistas com ao menos um grupo confirmado ou uma falha de execução. Para os PDFs
de cada pista (os que não estão encerrados):

```bash
.venv/Scripts/python.exe -m scripts.curation_round avancar --rodada RODADA --pdf ID --fase em_correcao --nota "pista-NN"
```

Atribua a cada pista os arquivos de teste e fixture que ela pode criar ou editar, sem
repetição entre pistas; helpers compartilhados (`tests/pdf_fixtures.py`,
`tests/symbol_benchmark_fixtures.py`) não são editados por nenhuma pista.

**As pistas rodam em série, na árvore principal, uma de cada vez**, na ordem de `prioridade`
do backlog: um `curadoria-corretor` por pista, disparado só depois que a pista anterior foi
integrada, testada e verificada. O paralelismo da onda fica na preparação, na leitura, na
auditoria e na investigação; a correção é serial porque edita código.

Não use `isolation` de worktree para os corretores: o worktree de subagente parte de um
commit, traz só arquivos rastreados (sem os CLIs e as mudanças locais não commitadas, sem a
`.venv`, que é ignorada) e a instalação editável continua importando o `src/` da árvore
principal, então os testes do corretor mediriam o código errado.

- `paralela: true` no backlog só garante que as pistas não compartilham arquivo dono; aqui
  serve para confirmar que a pista seguinte não toca o que a anterior mudou.
- Pista que precisa editar uma dependência, um helper compartilhado ou o inventário é
  replanejada pela orquestradora (vira pista própria) antes de seguir.
- `acoplamentos` são restrição: a pista não edita a dependência, e depois da integração os
  testes focados das pistas acopladas rodam de novo.

### 8. Integração serial (orquestradora)

Para cada pista, antes de disparar o corretor:

1. Registre `git status --short` e copie os arquivos permitidos da pista para
   `RODADA/ondas/K/pistas/pista-NN/antes/` (base para reverter e para o diff da pista).
2. Dispare o `curadoria-corretor` com os arquivos permitidos, os grupos confirmados, os
   relatórios dos investigadores, os testes focados e os `acoplamentos`.

Quando o corretor voltar:

3. Confira `git status --short` e `git diff -- ARQUIVOS_PERMITIDOS`: nada mudou fora dos
   arquivos permitidos além do que já estava no registro do passo 1.
4. Rode os testes focados da pista e das pistas acopladas, Ruff, formatação e mypy:

   ```bash
   .venv/Scripts/python.exe -m pytest TESTES_FOCADOS -q
   .venv/Scripts/python.exe -m ruff check .
   .venv/Scripts/python.exe -m ruff format --check .
   .venv/Scripts/python.exe -m mypy
   ```

5. Dispare um `curadoria-verificador` novo com a lista de arquivos alterados, os relatórios e
   os testes. Se REPROVADO, devolva os problemas ao corretor (SendMessage) ou restaure os
   arquivos de `RODADA/ondas/K/pistas/pista-NN/antes/`, apague os arquivos novos da pista e
   registre a pendência.
6. Só então passe à próxima pista.

### 9. Reinferir e fechar a onda

PDFs afetados = os `pdfs` das pistas integradas mais os das pistas acopladas, inclusive de
ondas anteriores que ainda não foram fechados. Reinfira e recompare só esses, contra a mesma
referência congelada e com as mesmas opções de inferência da rodada, e regenere o backlog:

```bash
.venv/Scripts/python.exe -m scripts.curation_infer --rodada RODADA --pdf ID1 ID2 --jobs N --pipeline
.venv/Scripts/python.exe -m scripts.curation_compare --rodada RODADA --pdf ID1 --pdf ID2
.venv/Scripts/python.exe -m scripts.curation_backlog --rodada RODADA --onda K
```

Compare antes e depois (TP_IA/FP_IA/FN_IA por método e união, com denominadores). Regressão
reabre a pista. Faça no máximo dois ciclos de correção por onda. Toda divergência acionável
(grupo com causa confirmada ou falha de execução) que não foi corrigida e verificada nesses
dois ciclos entra em "Pendências acionáveis" do relatório com: id do grupo (`grp-...`, estável
entre ondas e rodadas), PDFs, pista e arquivos donos, e um impedimento comprovado (com a
evidência) ou o dono e o próximo dado necessário. A próxima onda e a próxima rodada retomam
essas pendências primeiro (fase 6 e preparação). Não encerre uma divergência só por falta de ID
exato, por terminar um lote ou por julgar que uma pequena amostra representa o documento.

A onda termina quando cada PDF tem comparação vigente posterior à última integração e
auditoria aceita, ou foi encerrado com pendência. **Não** mova PDFs para `fechado` aqui: a fase
é terminal e impediria a reinferência de regressão do fechamento.

## Fechamento da rodada

1. **Código congelado:** nenhuma correção nova. Registre `git status --short`.
2. **Gates completos, uma vez e em série** (no Git Bash, `cmd.exe //c IniciarTestes.bat`;
   resultado em `relatorio-testes.txt`), mais:

   ```bash
   .venv/Scripts/python.exe -m scripts.audit_symbol_packages --output RODADA/fechamento/audit.json
   .venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output RODADA/fechamento/baseline
   .venv/Scripts/python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output RODADA/fechamento/uniao
   .venv/Scripts/python.exe -m scripts.reconcile_symbol_benchmark --predictions RODADA/fechamento/uniao/predictions.json --reference RODADA/fechamento/uniao/reference.json --exclude-method structural-raster-graph --exclude-method structural-vector-graph --output RODADA/fechamento/composicao
   .venv/Scripts/python.exe -m pytest tests/unit/test_declarative_symbol_packages.py tests/unit/test_benchmark_symbols.py tests/unit/test_symbol_inventory.py -q
   ```

   - Confronte `RODADA/fechamento/{baseline,uniao,composicao}` com `RODADA/inicial/` nos mesmos
     casos e denominadores (métodos isolados, união, composição e ablação, inclusive negativos
     críticos); fixtures novas à parte; se o conjunto mudou, mostre a interseção comparável e o
     conjunto ampliado. A interseção é só controle.
   - V-N: valide os esquemas JSON (Draft 2020-12) com uma implementação independente
     disponível, em instalação isolada se preciso, e registre comando e versão; se a fonte
     normativa F02 estiver disponível, rode também
     `.venv/Scripts/python.exe -m scripts.audit_symbol_packages --source-pdf CAMINHO_DA_F02 --output RODADA/fechamento/audit-fonte.json`
     e confira hash, páginas e localizadores (sem a fonte, novos IDs que dependem dela não são
     validados). Rode `git diff --check` e confira hashes e totalizadores.
   - Falha preexistente é registrada como tal, com evidência; gate que não rodou não passou.
3. **Reinferência de regressão de todo o corpus** (PDFs não encerrados), em paralelo e com as
   mesmas opções de inferência da rodada:

   ```bash
   .venv/Scripts/python.exe -m scripts.curation_infer --rodada RODADA --pdf ID1 ID2 ID3 --jobs N --pipeline
   .venv/Scripts/python.exe -m scripts.curation_compare --rodada RODADA --pdf ID1 --pdf ID2 --pdf ID3
   ```

   Compare com a última comparação de cada PDF; perda em qualquer PDF reabre a correção (e os
   gates). Não esconda perdas no total agregado.
4. **Persistência, revisão e exportação:** `benchmark_review_e14` exige um manifesto que cubra a
   descoberta recursiva de `--root`, então ele roda sobre uma inferência do corpus inteiro com
   o código congelado (não sobre as saídas por PDF), num diretório novo:

   ```bash
   .venv/Scripts/python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output RODADA/fechamento/corpus
   .venv/Scripts/python.exe -m scripts.benchmark_review_e14 --predictions RODADA/fechamento/corpus/predictions.json --manifest RODADA/fechamento/corpus/manifest.json --root examples --output RODADA/fechamento/revisao
   ```

   Isso não substitui a inspeção visual da UI e dos arquivos exportados afetados pelas
   correções (elementos por ponto, camadas, contagens e vínculos). Inspecione-os se a UI
   estiver disponível; se não puder, registre no relatório o gate de UI/exportações como
   pendente.
5. **Fechar os PDFs:** com `comparado` e `auditado` válidos, `fechado`; os demais,
   `encerrado_com_pendencias` com a nota do motivo:

   ```bash
   .venv/Scripts/python.exe -m scripts.curation_round avancar --rodada RODADA --pdf ID --fase fechado
   ```

6. **Matriz de cobertura** a partir de `RODADA/matriz-antes.csv`:

   ```bash
   .venv/Scripts/python.exe -m scripts.benchmark_packages_e07 --output RODADA/fechamento/benchmark
   .venv/Scripts/python.exe -m scripts.coverage_matrix_e16 --baseline-matrix RODADA/matriz-antes.csv --e07-report RODADA/fechamento/benchmark/report.json --output RODADA/matriz-depois.csv --summary RODADA/matriz-depois-resumo.json
   .venv/Scripts/python.exe -m scripts.curation_coverage_e16 compare --before RODADA/matriz-antes.csv --after RODADA/matriz-depois.csv --output RODADA/delta-cobertura.json
   ```

   Se a rodada alterou os detectores de transformadores ou de estais (ou suas fixtures),
   gere relatórios frescos e passe-os ao gerador da matriz:

   ```bash
   .venv/Scripts/python.exe -m scripts.benchmark_transformers_e05 --output RODADA/fechamento/transformadores
   .venv/Scripts/python.exe -m scripts.benchmark_guys_e06 --output RODADA/fechamento/estais
   .venv/Scripts/python.exe -m scripts.coverage_matrix_e16 --baseline-matrix RODADA/matriz-antes.csv --e07-report RODADA/fechamento/benchmark/report.json --e05-report RODADA/fechamento/transformadores/report.json --e06-report RODADA/fechamento/estais/report.json --output RODADA/matriz-depois.csv --summary RODADA/matriz-depois-resumo.json
   ```

7. **Publicação da matriz só com todos os gates e a revisão visual aprovados:** copie
   `RODADA/matriz-depois.csv` para `docs/data/matriz-simbologia-curadoria-atual.csv` e
   `RODADA/matriz-depois-resumo.json` para
   `docs/data/matriz-simbologia-curadoria-atual-resumo.json`. Com qualquer gate falhando ou
   pendente, não publique e registre o motivo. Nenhum outro arquivo versionado recebe
   resultados, datas ou histórico da rodada.
8. **Relatório final** em `RODADA/relatorio.md` (nunca em arquivo versionado): tempos por
   fase e por onda; PDFs fechados e encerrados com pendência, com motivo; concordância de
   classe e de ID exato por PDF com denominadores; TP_IA/FP_IA/FN_IA por método e união,
   antes e depois, com denominadores e escopo; **TP/FP/FN sintéticos inicial × final**
   (`inicial/` × `fechamento/`, isolados, união e composição, mesmos denominadores); exclusivos,
   ambiguidades e custos; melhorias de leitura (texto, atributos, relações) separadas do delta
   de IDs; correções (pistas, arquivos, testes, versões) e pareceres dos verificadores; falhas
   de execução e alertas; "Pendências acionáveis" (fase 9); pendências de triagem, de
   referência, de OCR, de medição e de gates (inclusive UI/exportações); delta de cobertura com
   os IDs ganhos e perdidos; gates com comandos e resultados. **Sem ganho validado, escreva
   isso expressamente**, mesmo que todos os PDFs tenham sido analisados; não confunda ganho de
   leitura com ganho de IDs.
9. Responda ao usuário com o resumo, o caminho de `RODADA/relatorio.md` e
   `git status --short`. Nunca faça commit nem push; o usuário revisa o diff e decide.
