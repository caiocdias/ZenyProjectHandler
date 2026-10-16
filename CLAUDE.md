# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Visão geral

Zeny Project Handler interpreta projetos de expansão da rede de distribuição CEMIG a partir de PDFs.
São dois artefatos independentes: um **cliente Windows magro** (PySide6) e um **servidor em
container** (FastAPI + SQLite/Alembic + PyMuPDF + Tesseract) que concentra toda a lógica. Código,
docs, mensagens de erro e nomes de domínio são em português (ex.: `ExecutarAnaliseDocumento`,
`CatalogoTecnico`); mantenha esse padrão.

## Comandos

Ambiente Windows, Python 3.11–3.13, venv em `.venv` (criado por `.\setup.bat`, que instala
`requirements-development.lock` em modo editável).

```powershell
.\IniciarTestes.bat                                   # gate completo; grava relatorio-testes.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy                    # strict, cobre src e tests
.\.venv\Scripts\python.exe -m pytest --cov            # cobertura mínima 85.01%
.\.venv\Scripts\python.exe -m pytest tests/unit/test_x.py::test_nome   # teste único
.\.venv\Scripts\python.exe scripts\complexity_gate.py src              # falha em Radon rank E/F (CC >= 31)
.\.venv\Scripts\python.exe scripts\client_artifact_gate.py --source-only
.\.venv\Scripts\python.exe scripts\generate_openapi_v1.py              # regenera docs/api/openapi-v1.json
.\.venv\Scripts\python.exe scripts\smoke_examples.py                   # smoke opcional sobre examples/
.\.venv\Scripts\python.exe scripts\build_release.py --version 0.5.0
.\ZenyProjectHandler.bat                              # sobe servidor via compose.local.yaml + abre cliente
```

- Testes de UI usam `QT_QPA_PLATFORM=offscreen` (definido em `tests/conftest.py`).
- Pytest roda com `--strict-markers` e transforma `ResourceWarning`/unraisable em erro: feche
  arquivos, documentos PyMuPDF e conexões explicitamente.
- Marcadores: `integration`, `slow`, `e2e`.
- O gate normal usa apenas fixtures sintéticas versionadas; nunca dependa de PDFs em `examples/`
  (ignorado pelo Git, bancada local — ADR 0005).
- O `.bat` local exige `.env` (copiado de `.env-example`) com a string ODBC do SQL Server de mercado.
  A sessão local é efêmera (`/data` em tmpfs, `down --volumes` ao sair).

## Arquitetura

Pacotes em `src/` com fronteiras verificadas por testes:

- `zeny_project_handler` — núcleo do servidor em arquitetura hexagonal:
  - `domain/` entidades e valores puros;
  - `application/` casos de uso (análise documental, pipeline de interpretação, promoção
    automática, revisão humana, conformidade, regiões/vãos/topologia física, portabilidade);
  - `ports/` protocolos; `adapters/` implementações (PyMuPDF/OCR em `analysis/`, regras de
    interpretação em `interpretation/`, SQLAlchemy+Alembic em `persistence/`, SQL Server em
    `market/`, catálogos/regras JSON em `*/data/` e `analysis/symbol_packages/`);
  - `composition.py` monta o grafo de dependências.
- `zeny_project_handler_server` — FastAPI: routers `*_api.py`, autenticação bearer,
  `job_manager`/`job_store` (worker único, jobs persistentes, idempotência por `Idempotency-Key`,
  cancelamento cooperativo), `volume_lifecycle` (manifesto `/data/.zeny-volume.json`, migração
  fail-closed), exportações PDF/XLSX. `composition.py` liga adaptadores aos casos de uso.
- `zeny_project_handler_contracts` — DTOs Pydantic de transporte compartilhados. Regras em
  `tests/contracts/test_architecture.py`: importam só stdlib/pydantic, **sem funções/métodos**,
  `extra="forbid"`, nenhum campo/`Path` contendo caminho.
- `zeny_project_handler_api_spec` — gera a OpenAPI v1 sem importar o runtime. Mudanças de API
  devem regenerar `docs/api/openapi-v1.json` (snapshot comparado em
  `tests/contracts/test_openapi_snapshot.py`).
- `zeny_project_handler_client` — UI Qt; cada painel (`ui/*_panel.py`) fala com o servidor via um
  `ui/*_gateway.py` HTTP. **O cliente não pode importar** `zeny_project_handler`, `_server`,
  `_api_spec`, PyMuPDF, SQLAlchemy, Alembic, `sqlite3` ou `zipfile`
  (`scripts/client_artifact_gate.py`). Projeções, regiões, vãos e decisões são calculados no
  servidor; o cliente só apresenta DTOs, rasters e overlays prontos (ADR 0013).

Fluxo principal de análise (job no servidor): extração documental → interpretação semântica
versionada → promoção automática dos resultados catalogados → conformidade declarativa
(provedores de fatos → regras do seed JSON → snapshot persistido → callouts). Versões de
extrator/interpretador/método de conformidade entram na identidade/cache da execução; ao mudar
comportamento de saída, incremente a versão correspondente. "Analisar conformidade" reaplica
regras sobre resultados persistidos sem reabrir o PDF.

Decisões arquiteturais estão em `docs/adr/` (0001–0015); comportamento vigente em
`docs/especificacao-funcional.md` e `docs/arquitetura-conformidade.md`.

## Curadoria de simbologia

Melhorias de leitura/símbolos seguem o contrato `docs/fluxo-curadoria-incremental-simbologia.md`.
Uma rodada é iniciada pela skill de projeto `/curadoria-simbologia`
(`.claude/skills/curadoria-simbologia/SKILL.md`), que processa os PDFs de `examples/` em ondas de
3 a 5 com os subagentes de `.claude/agents/curadoria-*.md` e os CLIs `scripts/curation_round.py`,
`curation_render.py`, `curation_infer.py`, `curation_reference.py`, `curation_compare.py`,
`curation_audit.py` e `curation_backlog.py` (`python -m scripts.curation_*`). Invariantes: o
leitor visual nunca vê predições e a referência é congelada antes de qualquer comparação;
correções rodam em série na árvore principal, com fixture sintética positiva/negativa; tudo da
rodada (PDFs, PNG, referências, relatório) fica em `tmp/curadoria-simbologia/` (fora do Git); a
matriz `docs/data/matriz-simbologia-curadoria-atual*` só é publicada com os gates aprovados; e o
conhecimento persiste apenas como mudanças versionadas em pacotes, algoritmos e fixtures/testes.
Não declare aceite/homologação sem as métricas exigidas no documento. Benchmarks e experimentos
ficam em `scripts/` e `scripts/experiments/` (dependências em `requirements-experiments.lock`,
opt-in).
