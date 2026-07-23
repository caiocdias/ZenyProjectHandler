# ADR 0008 - Projeto portátil verificável e backup atômico

## Status

Aceita em 21/07/2026.

## Contexto

Um projeto precisa circular entre pastas ou máquinas sem depender dos caminhos absolutos em que os
PDFs foram inicialmente encontrados. O usuário também precisa recuperar todo o ambiente local depois
de uma falha. Um arquivo compactado sem inventário verificável poderia ocultar conteúdo ausente ou
adulterado; copiar apenas o SQLite deixaria os PDFs externos fora do backup.

## Decisão

- Adotar `.zphproj` como pacote ZIP de formato 1, com manifesto canônico assinado por SHA-256,
  SQLite restrito a um projeto, PDFs e resultados auditáveis.
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
- Publicar pacote e banco restaurado por substituição atômica. Validar o SQLite temporário antes da
  troca e restaurar banco e arquivos anteriores se uma etapa posterior falhar.
- Manter a validação de integridade como detalhe interno dessas operações. Gestão de fotos,
  localização manual de arquivos e relatório separado não fazem parte da interface.

## Consequências

O pacote permanece autocontido depois de movido e sua integridade é validada internamente. A
recuperação não depende da sobrevivência dos PDFs em seus diretórios originais, e uma gravação
interrompida não invalida o último destino íntegro. O custo é duplicar os PDFs dentro de exportações
e backups e manter uma versão explícita do formato. Arquivos inválidos não são aplicados
silenciosamente; o usuário deve produzir uma nova exportação válida.
