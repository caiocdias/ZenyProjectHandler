# ADR 0008 - Projeto portátil verificável e backup atômico

## Status

Aceita em 21/07/2026; revisada em 05/08/2026.

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
silenciosamente e a interface nunca apresenta um backup degradado como íntegro.
