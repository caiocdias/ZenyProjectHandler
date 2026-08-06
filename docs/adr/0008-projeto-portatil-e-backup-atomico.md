# ADR 0008 - Projeto portátil verificável e backup atômico

## Status

Aceita em 21/07/2026; revisada em 06/08/2026.

## Contexto

Um projeto precisa circular entre pastas ou máquinas sem depender dos caminhos absolutos em que os
PDFs foram inicialmente encontrados. O usuário também precisa recuperar todo o ambiente local depois
de uma falha. Um arquivo compactado sem inventário verificável poderia ocultar conteúdo ausente ou
adulterado; copiar apenas o SQLite deixaria os PDFs externos fora do backup.

## Decisão

- Adotar `.zphproj` como pacote ZIP. O formato 1 permanece aceito para leitura; novas exportações e
  backups usam o formato 2, cujo manifesto canônico assinado por SHA-256 acrescenta estado de
  integridade e omissões auditáveis ao SQLite restrito a um projeto, PDFs e resultados.
- Declarar no manifesto o caminho relativo, tipo MIME, tamanho e SHA-256 de cada arquivo. Rejeitar
  caminhos absolutos ou com travessia, entradas duplicadas, links simbólicos, conteúdo criptografado
  e arquivos não declarados.
- Validar o tipo também pela assinatura binária. Tratar ausência ou adulteração como problema de
  integridade antes de aplicar o pacote.
- Manter o SQLite como fonte canônica. Pacotes novos não incluem projeções derivadas; a importação
  valida o manifesto, o banco e cada arquivo por tamanho, tipo e SHA-256.
- Preservar IDs, catálogo, análises, evidências, propostas e decisões no banco portátil. Exigir
  autorização explícita para substituir um projeto existente e compensar as trocas de arquivos se a
  transação do banco falhar.
- Separar a importação em preflight e aplicação. O preflight extrai o pacote apenas em área
  temporária descartável, valida manifesto, arquivos e SQLite, detecta projeto/pasta gerenciada com o
  mesmo ID e devolve um plano imutável. Ele não cria staging ao lado do destino, `.previous`, raiz
  gerenciada nem transação de escrita no SQLite local.
- Identificar o plano por SHA-256 e tamanho do pacote, resumo do conteúdo e fingerprint do estado
  alvo. O fingerprint do alvo cobre o agregado do projeto e seus registros auditáveis no SQLite,
  referências PDF e a árvore de arquivos gerenciados daquele ID.
- Solicitar confirmação na UI sobre o resumo e a identidade do plano antes de chamar a aplicação.
  Sob o coordenador global, a aplicação confere a identidade do plano, fotografa novamente o alvo,
  recalcula o hash do pacote e repete a validação completa do manifesto e do banco. Qualquer
  divergência produz uma recusa por plano obsoleto e exige novo preflight antes de criar staging ou
  publicar arquivos.
- Registrar cada aplicação autorizada no journal de formato 1
  `project-files/.import-recovery/import-journal-v1.json`. Publicá-lo por arquivo temporário irmão,
  `fsync` e substituição atômica antes de criar o workspace. O documento contém somente UUIDs,
  hashes, fase, horário e caminhos POSIX relativos derivados dos UUIDs; nenhum caminho absoluto ou
  livre vindo do pacote é aceito.
- Reservar o workspace `project-files/.import-recovery/<operation-id>` para `staging` e `previous`.
  Antes de trocar arquivos, assinar separadamente a árvore nova e a árvore anterior sem seguir links
  ou junções. As fases persistidas distinguem preparação, arquivos trocados, banco confirmado,
  restauração anterior e limpeza concluída.
- Inserir em `import_commits` um comprovante com operação, projeto e identidades de pacote, plano e
  arquivos na mesma transação que substitui o agregado. Esse registro é a prova do commit; a fase
  escrita no journal, isoladamente, não é prova suficiente.
- Reconciliar o journal depois das migrações e antes de compor catálogo, serviços ou janela. Um
  comprovante compatível conclui a limpeza e conserva os arquivos novos. Sem comprovante, restaurar
  a árvore anterior e descartar somente o workspace identificado. As duas rotas são idempotentes e
  deixam o journal até a limpeza terminar.
- Bloquear a inicialização quando versão, estrutura, identidade, recibo, contenção ou estado físico
  forem corrompidos ou ambíguos. O diagnóstico orienta preservar `.import-recovery` e recuperar por
  backup ou suporte; ele nunca tenta inferir outro destino nem executa exclusão ampla. Logs registram
  operação, fase, ação, versão e IDs seguros, sem caminhos.
- Adotar `.zphbackup` para o ambiente local completo: snapshot íntegro do SQLite, arquivos
  gerenciados e cópias dos PDFs originalmente externos. Reescrever no snapshot as referências dos
  PDFs para caminhos gerenciados recuperáveis.
- Executar antes do backup completo um preflight somente leitura sobre todas as referências PDF. Ele
  classifica cada documento como disponível, ausente, alterado ou ilegível e identifica problemas
  apenas por IDs de projeto/documento. Nenhum snapshot, staging ou pacote é criado nessa fase.
- Prosseguir diretamente quando o preflight for íntegro. Quando houver PDF indisponível, exigir
  confirmação explícita antes de criar temporários; uma recusa preserva inclusive um destino já
  existente. A criação revalida o relatório confirmado para não aceitar omissões novas.
- Marcar o manifesto e o resultado como `DEGRADADO` quando uma confirmação permitir omissões. Cada
  omissão registra código, tipo, IDs seguros e tratamento. Em backup, o tratamento
  `PERMANECE_EXTERNO` deixa no snapshot a referência canônica já existente e não inventa um caminho
  gerenciado para uma cópia ausente; `OMITIDO` informa que não há origem registrada ou que um anexo
  de exportação não foi incluído.
- Publicar pacote e banco restaurado por substituição atômica. Validar o SQLite temporário antes da
  troca e restaurar banco e arquivos anteriores se uma etapa posterior falhar.
- Separar limitações declaradas pela origem da integridade física do pacote recebido. Mesmo um
  backup `DEGRADADO` precisa ter manifesto, snapshot e todos os arquivos declarados íntegros para ser
  restaurado; o resultado da restauração expõe as omissões sem tratá-las como corrupção do ZIP.
- Mostrar no diálogo apenas identificadores abreviados e a classificação do problema, nunca nome de
  arquivo nem caminho absoluto. Gestão de fotos e localização manual de arquivos permanecem fora do
  painel de portabilidade.

## Consequências

Um pacote sem omissões permanece autocontido depois de movido e sua integridade é validada
internamente. Um pacote degradado é deliberadamente incompleto, mas deixa essa condição verificável e
restaurável de modo previsível: dados canônicos são recuperados e as origens omitidas continuam
externas ou indisponíveis conforme registrado. Uma gravação interrompida não invalida o último
destino publicado. O custo é duplicar PDFs íntegros, manter compatibilidade de leitura com o formato
1 e distinguir degradação declarada de corrupção real. Nenhuma origem inválida é omitida
silenciosamente e a interface nunca apresenta um backup degradado como íntegro. A substituição
continua removendo o agregado anterior e persistindo o pacote com seus IDs originais; o plano apenas
antecipa a autorização e não altera essa semântica. O preflight calcula a identidade do pacote antes
e depois da validação para detectar troca durante a inspeção, e a aplicação repete esse custo para
fechar a janela entre confirmação e publicação.

Uma queda durante a substituição deixa um protocolo pequeno e autocontido para o bootstrap. A tabela
de comprovantes cresce uma linha por importação confirmada e o namespace `.import-recovery` permanece
reservado mesmo quando vazio. Isso troca um pequeno custo de armazenamento e migração pela decisão
determinística entre concluir e restaurar, inclusive depois de outra queda durante a própria
reconciliação. Corrupção externa deixa de ser tratada como rollback presumivelmente seguro e passa a
exigir intervenção explícita.
