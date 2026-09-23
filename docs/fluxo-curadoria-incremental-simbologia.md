# Curadoria incremental de simbologia — fluxo independente

Este fluxo pode ser executado a qualquer momento, inclusive depois do
[roadmap de análise de simbologia](roadmap-analise-simbologia.md). O usuário
adiciona PDFs localmente em `examples/` e envia o prompt ao fim deste arquivo.
Uma execução **não treina o assistente de forma permanente**. Conhecimento
duradouro é uma mudança revisável nos pacotes, no inventário quando necessário
e nas fixtures/testes versionados. O chat e os PDFs ignorados pelo Git não são
uma base de conhecimento persistente.

O fluxo já pode ser feito por agentes com as ferramentas atuais. Automatizar
rotulagem, treino ou reexecuções é uma melhoria futura, não uma pré-condição.
Nenhuma execução deste fluxo altera os estados E01–E16 por conta própria nem
é dependência para continuar E08–E16.

## Contrato e limites

- `examples/` é uma bancada local dinâmica conforme
  [ADR 0005](adr/0005-exemplos-locais-dinamicos.md). PDFs reais e relatórios
  com caminhos/recortes ficam fora do Git, em `tmp/curadoria-simbologia/`.
  Não copiar PDFs privados para fixtures ou enviar seu conteúdo a serviços
  externos. O gate portátil continua sintético.
- Adicionar um PDF **não ensina automaticamente** o detector. Primeiro é
  preciso ver as páginas, identificar ocorrências e negativos, conferir a
  fonte/legenda e testar uma regra ou template. Um rótulo sugerido por IA é
  hipótese de revisão, não verdade confirmada pelo usuário.
- Uma forma que admite vários IDs gera **uma observação física com alternativas
  explícitas**. O ID exato só pode ser emitido quando texto, cor, camada, legenda
  ou contexto verificável o distingue. Ambiguidade não vira vários ativos.
  Alternativas só contam como reconhecimento do grupo visual se o pacote e seus
  positivos/negativos estiverem verificados; sem isso, o grupo continua pendente.
  Desconhecido continua desconhecido e não conta como variante reconhecida.
- A legenda local limita o significado ao documento/revisão. Ela é referência,
  não ocorrência operacional. Símbolos informativos, norte e desenhos §33
  continuam informativos, mesmo quando parecem equipamento. PDF de projeto
  revela casos e estilos, mas não cria norma ou obrigação de conformidade.
- Cada execução usa uma versão congelada dos pacotes e da inferência. A
  referência visual/ROI do revisor fica fora da entrada do detector. Silêncio
  de outro método não veta um candidato exclusivo; concordância não é
  probabilidade.
- Um PDF já visto passa a ser desenvolvimento. Preservar a reserva sintética
  do roadmap até E16; depois de aberta, ela não serve como teste cego repetido
  deste fluxo. Uma reserva futura precisa de seleção e congelamento próprios.

## Etapas repetíveis para uma execução

As etapas C01–C04 pertencem **a cada execução**, não ao índice E01–E16. Seu
estado, cobertura, hashes e impedimentos são registrados no relatório local
da execução. Uma etapa sem evidência não é marcada como concluída.

### C01 — Descobrir e congelar entradas

**Dono:** coordenador. Ler instruções do repositório, este fluxo, ADR 0005,
inventário E01, pacotes/esquema, comandos e `git status/diff`. Descobrir
recursivamente todos os PDFs de `examples/`, inclusive `.PDF`, e registrar
caminho relativo, SHA-256, tamanho, páginas, legibilidade e versão/configuração.
Comparar com o manifesto local anterior quando existir, mas não presumir que
arquivo ausente foi validado. Duplicatas por hash mantêm todos os caminhos.

**Saída:** manifesto completo em `tmp/curadoria-simbologia/<execucao>/`,
lista de PDFs/páginas novos, modificados, inalterados e ilegíveis. Não escrever
no Git nesta etapa.

### C02 — Revisar visualmente antes de comparar predições

**Dono:** agente visual independente C, em lotes de páginas sem lacunas. Abrir
imagens renderizadas de **todas as páginas novas ou modificadas**, em visão
geral e recortes legíveis, considerando base e anotações. Registrar ocorrência,
ausência, papel operacional/informativo, possíveis IDs, negativos próximos,
contexto que desambigua e incerteza. JSON, OCR e lista de predições não
substituem a visão real. Reutilizar revisão anterior de página inalterada
somente com hash e configuração compatíveis, declarando o reuso.

**Saída:** observações congeladas antes da comparação com predições. Se o ID
exato não for comprovável, registrar conjunto de alternativas ou desconhecido.

### C03 — Confrontar, curar e testar

**Dono:** coordenador congela a interface e distribui arquivos com um único
responsável: A edita apenas pacotes/runner que lhe forem atribuídos; B edita
fixtures/testes separados; C compara imagens e saídas sem editar detector.
Inferir com os PDFs e o snapshot congelado **antes** de ler a referência do
revisor no comparador. Registrar TP, FP, FN, duplicatas, exclusivos, casos
ambíguos e falta de positivo por família, com denominadores. Resolver
divergências pela imagem e fonte; não ajustar regra pela ROI do revisor.

Promover conhecimento apenas quando houver fonte rastreável, gramática/template
ou contexto discriminante, positivo e negativos independentes e papel correto.
Uma nova família/revisão altera o inventário com ID estável e fonte conferida.
Caso real reproduzível vira fixture sintética autoral pequena; PDF/recorte
privado não é copiado. O que não pode ser decidido permanece `pending`
com motivo e próximos dados necessários. Não marcar 344 variantes como
reconhecidas só porque estão cadastradas.

**Saída:** diff revisável de pacotes/inventário/testes, relatório por família
e lista explícita de pendências. Não modificar o reconciliador para cadastrar
uma família por dados nem criar regra de conformidade a partir do exemplo.

### C04 — Integrar e registrar o checkpoint

**Dono:** coordenador. Conferir retornos A/B/C, integrar registro central
serialmente, congelar arquivos e repetir os gates afetados. Para o contrato
atual, conferir ao menos:

```powershell
.\.venv\Scripts\python.exe -m scripts.audit_symbol_packages --output tmp/curadoria-simbologia/audit.json
.\.venv\Scripts\python.exe -m scripts.benchmark_packages_e07 --output tmp/curadoria-simbologia/benchmark
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output tmp/curadoria-simbologia/baseline
.\.venv\Scripts\python.exe -m pytest tests/unit/test_declarative_symbol_packages.py tests/unit/test_benchmark_symbols.py tests/unit/test_symbol_inventory.py -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --include-packages --output tmp/curadoria-simbologia/predictions
```

O último comando só produz inferência; C ainda precisa reconciliar visualmente
as páginas e predições afetadas. Validar o esquema Draft 2020-12 com
implementação independente disponível, em instalação isolada se necessário,
e registrar comando/versão. Se a fonte normativa F02 estiver disponível,
repetir a auditoria com `--source-pdf` apontando para ela e conferir hash,
páginas e localizadores; ausência da fonte impede validar novos IDs que dela
dependem. Se o código ou os comandos mudarem, descobrir os
novos comandos no repositório e registrar a substituição; não fingir que um
gate ausente passou. Fazer `git diff --check` e conferir hashes/totalizadores.

**Aceite da execução:** todos os PDFs/páginas descobertos estão no manifesto;
novos/modificados foram realmente vistos; predições e comparação pertencem ao
mesmo checkpoint; positivos, negativos e alternativas das mudanças passaram;
fontes intactas; regressões antigas não foram escondidas. Sem exemplos novos,
registrar execução sem mudança, não inventar ganho. Uma execução pode terminar
com pendências explícitas; elas não contam como reconhecimento nem reprovam
automaticamente uma etapa diferente do roadmap principal. Não criar commit,
publicar ou implantar sem autorização explícita.

## Prompt one-shot para usar após adicionar PDFs

Cole o bloco inteiro em uma sessão nova, aberta na raiz do Zeny Project Handler.
Os arquivos podem estar em qualquer subpasta de `examples/`; o prompt
descobre os caminhos, sem precisar editar nomes.

```text
Execute uma rodada completa e independente de curadoria incremental de simbologia conforme docs/fluxo-curadoria-incremental-simbologia.md no Zeny Project Handler, aberto na raiz. Os PDFs que eu quero considerar já estão em examples/; descubra todos recursivamente, inclusive .PDF, e compare os hashes com a última rodada local se ela existir.

Leia primeiro as instruções aplicáveis do repositório, docs/adr/0005-exemplos-locais-dinamicos.md, este fluxo, o inventário E01, o esquema/pacotes E07, os scripts/testes de benchmark e git status/diff. Preserve todas as alterações preexistentes. Execute C01–C04 em uma única tarefa, sem depender do estado de docs/roadmap-analise-simbologia.md nem mudar seus estados. Registre manifesto de todos os arquivos/páginas, falhas, hashes e um diretório de evidências local em tmp/curadoria-simbologia/.

Delegue frentes delimitadas a subagentes, se disponíveis: A implementa pacotes/runner por lotes de famílias e possui somente os arquivos que você lhe atribuir; B cria fixtures sintéticas e testes positivos/negativos em arquivos separados; C renderiza e realmente vê todas as páginas novas/modificadas, base e anotações, congelando observações antes de ver predições e depois compara os resultados. Você é o coordenador: define contratos, um dono por arquivo, integra inventário/registro central serialmente, verifica retornos e executa gates finais. Se subagentes não estiverem disponíveis, registre isso e não simule revisão independente.

Trate cada PDF real como desenvolvimento local, nunca como treino automático ou norma. A identificação sugerida por IA sem confirmação é provisória. Para desenhos iguais de IDs diferentes, produza uma observação com alternativas explícitas e contexto comprovável; não force ID exato, não duplique ocorrências, não conte desconhecido como reconhecimento. Legenda, norte e desenhos informativos, inclusive §33, não viram ativos. Não passe ROI/rótulo do revisor ao detector; preserve candidatos exclusivos e não trate concordância como probabilidade. Se faltar rótulo ou fonte para um caso, documente a pendência e avance nos demais.

Congele a inferência antes da comparação visual; confronte FP/FN, duplicatas, exclusivos e ambiguidades por PDF/página/família. Incorpore apenas achados sustentados por fonte, positivo e negativos independentes em pacotes versionados e fixtures sintéticas autorais, preservando PDFs e relatórios privados fora do Git. Rode auditoria E01/esquema, V-N, V-Q, V-B e inferência de todos os PDFs/páginas conforme os comandos atuais deste fluxo; valide visualmente as saídas afetadas, registre comandos/resultados e não declare gate não executado como aprovado. Não abra a reserva sintética do roadmap antes de E16 nem a reutilize como teste cego em rodadas posteriores.

Entregue no fim um resumo conciso com arquivos alterados, IDs/famílias acrescentados, versões/hashes, cobertura de PDFs/páginas, TP/FP/FN e ambiguidades com denominadores, gates executados, pendências e próximo dado necessário. Não crie commit, publique ou implante sem autorização explícita.
```

## Estado do fluxo

Descrição operacional pronta em 23/09/2026. Nenhuma rodada foi iniciada por
esta edição documental. O ponto de partida conhecido é o checkpoint E07 de
21 variantes `enabled` e 344 `pending` em 27 pacotes; conferir novamente
o código antes de cada execução. O [handoff E07](roadmap-analise-simbologia.md)
preserva as evidências históricas, sem transformar o bloqueio antigo em
dependência deste fluxo.
