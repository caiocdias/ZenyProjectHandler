# ADR 0014 — Lifecycle e migração fail-closed do volume servidor

- Estado: aceita
- Data: 2026-08-20
- Relações: detalha a seção de fonte principal do ADR 0013 e preserva as garantias dos ADRs 0002 e
  0008.

## Contexto

O volume `/data` é a única fonte de verdade do servidor. Apenas executar `alembic upgrade head` em
todo startup não distingue volume novo, revisão já preparada, revisão futura de uma imagem mais nova,
corrupção ou manifesto de lifecycle incompatível. Uma falha não pode permitir que o socket de
negócio fique pronto, nem autorizar limpeza, downgrade ou reconstrução implícita do volume.

O rollback também não pode ser descrito como simples troca de tag: uma imagem antiga pode não
entender o schema deixado pela nova. Além disso, cutover de backup originado no monólito não deve
preservar um caminho Windows como dependência permanente do container.

## Decisão

1. `/data/.zeny-volume.json` é um manifesto pequeno, canônico e publicado atomicamente. O formato 1
   registra revisão Alembic, inicialização, última preparação e última migração; nunca registra
   segredo ou caminho do cliente.
2. Antes de compor serviços e ficar ready, o servidor prova escrita na raiz, lê/valida o manifesto,
   executa `PRAGMA quick_check`, identifica o único head embarcado e rejeita revisão desconhecida.
3. Alembic só é chamado quando a revisão atual difere do head. Depois da execução, revisão e
   integridade são verificadas novamente antes da publicação do manifesto.
4. Manifesto sem banco, revisão divergente, formato futuro, volume sem escrita, SQLite corrompido ou
   erro de migração encerram o startup. O processo não atende rotas de negócio e não altera a revisão
   futura para fazê-la caber.
5. A operação cria `.zphbackup` antes de upgrade. Não existe downgrade automático de schema.
   Rollback no mesmo volume é permitido apenas para imagem compatível; caso contrário usa volume
   novo e o backup pré-upgrade.
6. `docker compose down` é permitido e preserva o volume. `down -v`, bind mount Windows/SMB como
   fonte e edição manual de manifesto/`alembic_version` não pertencem ao procedimento operacional.
7. Na restauração, todas as referências PDF são recalculadas para o namespace gerenciado do volume
   atual. Arquivos omitidos continuam ausentes e declaradamente degradados, mas o caminho legado não
   permanece como dependência nem justifica montar a origem Windows.
8. A imagem usa base por digest, UID/GID fixos, root filesystem somente leitura no Compose, tmpfs
   limitado, capabilities removidas, `no-new-privileges`, limites de memória/PIDs, healthcheck e
   shutdown com grace period. O segredo continua exclusivamente runtime.

## Consequências

- Restart sem mudança de schema revalida o volume sem executar novamente a migração.
- Upgrade antigo→head é observável e acontece antes da prontidão; corrupção e downgrade acidental
  falham de forma explícita.
- O manifesto agrega uma segunda verificação de coerência, mas não substitui `.zphbackup` nem é
  editável pelo operador.
- Uma restauração degradada recupera estado auditável e mantém a ausência visível. O PDF precisa ser
  reenviado/removido pelo fluxo normal, não recuperado por compartilhamento de filesystem.
- O rollback incompatível consome um volume novo e tempo de restauração, em troca de não arriscar o
  volume atualizado.

## Alternativas rejeitadas

- Rodar Alembic incondicionalmente e considerar a existência do processo como readiness: não
  diferencia incompatibilidade/corrupção nem prova o head final.
- Executar downgrade automático ao trocar a imagem: pode destruir colunas ou dados que a imagem
  antiga desconhece.
- Corrigir `alembic_version` manualmente: mascara incompatibilidade sem transformar o schema.
- Montar a pasta Windows antiga: reintroduz caminho compartilhado, permissões e topologia como parte
  da fonte principal.
- Incorporar senha na imagem para simplificar health/instalação: deixa segredo recuperável em
  camadas e metadados.
