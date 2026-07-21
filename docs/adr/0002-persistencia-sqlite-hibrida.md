# ADR 0002 — Persistência SQLite híbrida e versionada

- Estado: aceita
- Data: 2026-07-21

## Contexto

O domínio muda com a calibração dos projetos reais, mas a aplicação precisa manter integridade
referencial, consultar entidades individuais e reabrir projetos sem perda. Mapear cada atributo do
domínio diretamente em classes ORM tornaria as entidades dependentes da infraestrutura e aumentaria
o custo de cada evolução.

## Decisão

SQLite é o armazenamento canônico, acessado por SQLAlchemy Core atrás de portas e repositórios. As
tabelas mantêm identidades, pertença ao projeto, ordem e chaves estrangeiras. Cada entidade também
possui um payload JSON canônico, reconstruído por um codec com registro explícito de tipos — nunca
por importação dinâmica.

Projetos e catálogos são agregados de escrita. Documentos e elementos são projeções atualizadas na
mesma transação e podem ser consultados por repositórios próprios. Evidências, propostas e decisões
possuem tabelas e repositórios auditáveis.

As mudanças de schema usam Alembic embarcado. A unidade de trabalho exige `commit` explícito e faz
rollback ao sair do contexto. Catálogos publicados são protegidos por validação no repositório e por
triggers SQLite. O backup usa a API de snapshot do SQLite, executa `PRAGMA integrity_check` e somente
então substitui atomicamente o arquivo de destino.

## Consequências

- O domínio continua sem imports de SQLAlchemy, SQLite ou Alembic.
- Campos novos podem ser acrescentados ao payload sem desmontar imediatamente todo o schema.
- Relações críticas continuam protegidas por chaves estrangeiras e índices relacionais.
- Alterações em projeções devem ocorrer pelo repositório do projeto, nunca isoladamente.
- Migrações são testadas pelo comportamento do banco; seus arquivos declarativos ficam fora da
  medição de cobertura de linhas.
