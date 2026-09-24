# E15 — Execução, cache e ativação controlada no servidor

Execução iniciada em 24/09/2026 sobre `f9832ca1e75ec446ceeb4f9c0c613c529ca68329`.
A árvore Git estava limpa; a primeira alteração foi sincronizar `#em-andamento`
no índice e detalhe de `docs/roadmap-analise-simbologia.md`. Não há `AGENTS.md`
aplicável. Nenhum PDF de `examples/` será enviado a serviço externo, e a reserva
sintética E16 permanece lacrada.

## Pré-condições e divisão

E13 e E14 constam como `#concluida` no roadmap e têm handoffs em
`docs/e13-semantica-simbologia.md` e `docs/e14-revisao-simbologia.md`.
Quatro dos cinco módulos centrais documentados de E13 mantêm seus hashes;
`interpretation_pipeline.py` mudou em E14 para a apresentação e persistência
aditivas, conforme o handoff da etapa seguinte. Pré-teste E13:
`36 passed` após criar o diretório temporário de pytest. A primeira tentativa
teve 19 aprovações e 17 erros de preparação causados somente pela ausência
desse diretório; não foi falha de asserção.

| Frente | Responsável e fronteira de escrita |
|---|---|
| A — código | `/root/codigo`: módulos de composição/job/configuração do servidor, workflow e análise/cache; `symbol_execution.py` e `raster_symbols.py` liberados após contrato. |
| B — testes/desempenho | `/root/testes`: novos `tests/**/test_e15_*.py` e `tmp/e15-simbologia/testes/`; banco/worker isolados. |
| C — PDFs/V-P | `/root/pdfs`: somente `tmp/e15-simbologia/visual/`; imagens originais antes das predições e revisão do checkpoint final. |
| Coordenação | `/root`: roadmap, este handoff, integração, agenda de execuções pesadas e gates finais. |

O contrato acordado começa com opt-in no servidor (`ZENY_SERVER_SYMBOL_COMPOSITION`,
default desabilitado), assinatura do snapshot de métodos e configuração e
composição por página. O checkpoint de A deve estabilizar a interface antes dos
testes finais de B e da comparação operacional de C. Nenhuma frente disputa o
mesmo banco, worker ou UI; V-B pesado será agendado pelo coordenador.

## Implementação e decisões

A habilitação é exclusiva do servidor e tem padrão desabilitado. O perfil
`balanced` executa legado, E05, E06, pacotes E07 habilitados, template E08 e
legenda documental E10; `vector-only` evita renderização raster. Hough E08,
estrutural E09 e neural E11 permanecem explicitamente desabilitados para
operação. Um `ZENY_SERVER_SYMBOL_MODEL_PATH` configurado causa falha explícita:
E11 foi rejeitado no experimento e nenhum modelo é instalado no cliente.

`SymbolCompositionRunner` verifica SHA/tamanho/páginas da fonte, percorre
página/método/tile com liberação do raster e cancelamento cooperativo, agrega
resultados de mesmo método entre páginas e entrega a união E12 ao interpretador
E13. `FORA_DOMINIO` é cobertura legítima; `FALHA`/`INDISPONIVEL` de método
habilitado impedem interpretação e sucesso do job. Exclusivos continuam na
união; ausência de outro método não vira veto, e score bruto/acordo não vira
probabilidade. O progresso do job avança por extração e composição e só chega
a 100% após conformidade bem-sucedida.

A assinatura incorpora perfil, identidade e versão dos métodos, SHA dos
módulos de detecção/orquestração, pacotes/templates por conteúdo, política e
versão de calibração, caminho/hash de modelo quando configurado, renderização,
tile, PyMuPDF e Pillow. A chave do job opt-in recebe essa assinatura; opt-out
preserva a identidade anterior. O cache integral de símbolos fica sob o
diretório de cache derivado e exige documento/SHA/assinatura/cobertura completos,
payload com hash e verificação da fonte antes/depois. Nova chave de job com
entrada idêntica reutiliza esse cache; mudança de configuração invalida a
combinação. Não há leitura de journal parcial como cache.

O journal `symbol_partial_runs/<attempt UUID>.json` guarda assinatura, fonte,
resultado/cobertura/observações de cada método concluído, tiles, duração e
estado da tentativa; é escrito atomicamente. Falha ou cancelamento preserva o
journal e resultados anteriores, sem criar sucesso/propostas E13 da parte
incompleta. Nova tentativa reprocessa desde o começo, sem retomada do tile.
Não foi acrescentada limpeza automática do journal; monitorar crescimento
antes de definir retenção futura. O banco e histórico de jobs não precisaram
de migração. Configuração, `.env-example`, três arquivos Compose e README
exibem o opt-in e o rollback.

Arquivos de A: `src/zeny_project_handler_server/{symbol_execution,composition,config,job_manager}.py`,
`src/zeny_project_handler/application/{document_analysis,mvp_workflow,interpretation_pipeline}.py`
e `src/zeny_project_handler/adapters/analysis/{pymupdf_analyzer,raster_symbols,legend_symbols}.py`.
`job_store.py` não precisou de edição. Arquivos de B:
`tests/unit/test_e15_symbol_signatures.py`,
`tests/integration/test_e15_symbol_cache.py`,
`tests/server/test_e15_symbol_jobs.py`. Coordenador: documentação, `.env-example`
e os três Compose. Hashes SHA-256 finais dos módulos e testes E15:

| Arquivo | SHA-256 |
|---|---|
| `server/symbol_execution.py` | `09a1ac727aeeffc2a89383baa8831dcdf4ee2071ab8ff1553359659e8b6e14a7` |
| `server/composition.py` | `1de7646a9fe3ece2ed90de5ce20bf27dabcb903f7d0ea7713a85549a9d2ff7fc` |
| `server/config.py` | `9cd49c8f432162b973b282212dc87b99c67ffb9c97bc8c29ee2f275284fb18f7` |
| `server/job_manager.py` | `9be2ad263b5a5863440d7ff85a3cb9ef4ad790c6a7f5c0341844a71339f94540` |
| `application/document_analysis.py` | `68680043a483652ae4697af0198e30efe9ea8e6ed1854dd23689225222c7e503` |
| `application/mvp_workflow.py` | `2f51e0804facb3bf466d15e0ff34e9777e06b88dc39e0e82acbbacfd0968e8ee` |
| `application/interpretation_pipeline.py` | `894c7d01d4254cceea4a05f63bdb76b2c3ecd90c7d80c3fb0e271d7fb2a8f1e9` |
| `analysis/pymupdf_analyzer.py` | `b968375d1b1afb656684e58d4c491201c0e9afa6768116c156a09309bde84f25` |
| `analysis/raster_symbols.py` | `d8cf172c5678fe73b814af649f27d5696a3ac4f91abae065acce373001fbcbff` |
| `analysis/legend_symbols.py` | `c2cc4c7a2fe3f44baac273afb19db2ea4a44a21d540e643db940138e309b729e` |
| `tests/unit/test_e15_symbol_signatures.py` | `0ee6c9319d8a884f8d784da515cc6a0382c02f5272812929190115cb2645f690` |
| `tests/integration/test_e15_symbol_cache.py` | `65750d71f72762a5d3d2279b91206671c1a12dd3229099419011e9a0b88dff43` |
| `tests/server/test_e15_symbol_jobs.py` | `2fdb392b8425451cd5574e4df1ec6eded0b9088adbf0f968b1fbaeefe7d6f2ea` |

Os prefixos `server/`, `application/` e `analysis/` na tabela abreviam,
respectivamente, `src/zeny_project_handler_server/`,
`src/zeny_project_handler/application/` e
`src/zeny_project_handler/adapters/analysis/`.

## Validações e checkpoint integrado

Todos os comandos abaixo usam a `.venv` da raiz. O launcher Python foi negado
pelo sandbox; as execuções de teste exigiram a permissão local elevada, sem
instalar dependências. Diretórios `--basetemp` foram previamente criados sob
`tmp/e15-simbologia/` para não compartilhar banco entre frentes.

| Gate | Comando efetivo / resultado no checkpoint |
|---|---|
| Pré-condição E13 | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_e13_semantic_promotion.py tests/integration/test_e13_semantic_pipeline.py -q -o cache_dir=tmp/e15-simbologia/preflight-pytest-cache --basetemp=tmp/e15-simbologia/preflight-basetemp`: 36 passed. Primeira tentativa teve 19 passed/17 erros de preparação por diretório pai ausente; foi corrigido e repetido. |
| V-R | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_analysis_cache.py tests/unit/test_rapid_evidence.py tests/integration/test_document_analysis.py tests/server/test_jobs_api.py -q -o cache_dir=tmp/e15t/vr-c --basetemp=tmp/e15t/vr-t`: 20 passed, exit 0 no checkpoint final. A execução anterior em `tmp/e15-simbologia/integration/` também passou 20/20. |
| V-N E15 | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_e15_symbol_signatures.py tests/integration/test_e15_symbol_cache.py tests/server/test_e15_symbol_jobs.py -q -o cache_dir=tmp/e15t/vn-c --basetemp=tmp/e15t/vn-t`: 8 passed, exit 0 no checkpoint final. B repetiu os mesmos oito após o último refino de telemetria. |
| V-Q | `.\.venv\Scripts\python.exe -m ruff check .`: passou; `.\.venv\Scripts\python.exe -m ruff format --check .`: 434 arquivos formatados; `.\.venv\Scripts\python.exe -m mypy`: 396 fontes sem erro; `git diff --check`: exit 0. |
| Regressão E13/workflow/E14 | `.\.venv\Scripts\python.exe -m pytest tests/integration/test_e13_semantic_pipeline.py tests/integration/test_mvp_workflow.py tests/server/test_e14_symbol_review.py -q -o cache_dir=tmp/e15t/c --basetemp=tmp/e15t/t`: **37 passed**, exit 0. Primeira tentativa teve 36 passed/1 failed pela mensagem sem “Retomar”; A corrigiu só o texto de cancelamento. A segunda teve 36 passed/1 `FileNotFoundError` em caminho temporário longo no Windows; com caminho curto, todos passaram. |
| V-B operacional | `.\.venv\Scripts\python.exe tmp/e15-simbologia/testes/measure_operational.py`: exit 0 no SHA congelado de `symbol_execution.py`; detalhes abaixo. |
| V-P operacional | `.\.venv\Scripts\python.exe tmp/e15-simbologia/operational/run_examples.py`: 11 PDFs/11 páginas completos, 11 miss→stored→hit, 237 ocorrências/1.422 linhas de matriz, SHA da fonte invariável, exit 0. Manifesto SHA-256 `2984b0991d157c0f4d95724894968b4965e2285e6d7331fc0f1f452b1dfd45bd`. |
| V-P runner | `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e15-simbologia/benchmark-examples --include-transformers --include-guys --include-packages --include-raster --include-legend`: 11 PDFs/11 páginas, 237 predições, zero falhas, exit 0. Manifesto SHA-256 `55505504a91beb4eef704eb6b10d8797ea38c5ce11be5e9dbe5b8bb46338bfe6`, predições SHA-256 `9e8be4ce9d84def1679efacafd55128a41328adba66b4a3f52a90e78b9c7fef7`. O runner declara corretamente revisão visual pendente. |

B injetou OOM, tile `FALHA`, modelo ausente e cancelamento; nenhum caso
terminou com job/cache integral de sucesso. Cobriu assinatura por
modelo/template/perfil/calibração/render, reuso em nova chave, opt-out→opt-in→
opt-out no mesmo banco, histórico e reabertura. Evidências, hashes dos três
testes e comandos em `tmp/e15-simbologia/testes/handoff-b.md` (SHA-256
`58a0264977119642975f5684cc92cca2fcda9ebafe6ea7712638f49764918ed0`).

V-B final em Windows 11 build 26200, Python 3.13.14, PyMuPDF 1.28.0, CPU sem
GPU: PDF autoral de duas páginas, perfil balanced, 144 DPI, tile 256 px,
orçamento 16 MB. Tempo 9,420 s; working set inicial 134.402.048 B, pico
136.138.752 B e final 134.737.920 B; alocações Python pico 1.877.647 B.
Foram 48 eventos/tile (24 por página), 11 resultados método/página, progresso
monotônico 11.000/11.000, journal `completed` e cache `stored`. SHA-256 do PDF
antes/depois `01d2cb6c5090d00b0609c2da7c7cc9cd7bc1e78c94fdfc644499382001e1f969`.
O desenho produziu zero ocorrências: mede operação, não acurácia. Métricas JSON
SHA-256 `09856c0d84f1d675c2f5effd70d0eb94ac72b83088375be65f3a98b633e72e97`.

## V-P visual, integridade e parciais

O manifesto operacional final e cada composição por PDF estão em
`tmp/e15-simbologia/operational/checkpoint-final/`; a inferência V-P por método
está em `tmp/e15-simbologia/benchmark-examples/`. A frente C executou os
quatro comandos novos abaixo, todos exit 0:

```powershell
.\.venv\Scripts\python.exe tmp/e15-simbologia/visual/audit_checkpoint.py
.\.venv\Scripts\python.exe tmp/e15-simbologia/visual/compare_predictions.py
.\.venv\Scripts\python.exe tmp/e15-simbologia/visual/audit_partials.py
.\.venv\Scripts\python.exe tmp/e15-simbologia/visual/build_findings.py
```

C inventariou e abriu as imagens originais das 11 páginas
**antes** de consultar predições: 11 panoramas, 28 tiles e 11 vistas sem
anotações. O manifesto pré-inferência SHA-256
`21ba00c416ea4954f84894d246ae0a45942094f1aceba2b2ef57c5af7be843c9`
e as notas SHA-256 `0c07ea17ce815b980fc6f7ffebfb7b4356669ade1f6ff72459810e2ef7007238`
foram congelados antes da comparação, sem alimentar os detectores. Depois C
abriu 24 folhas de contato com os 237/237 candidatos; os 11 hashes dos PDFs
permaneceram idênticos antes/depois. A identidade classe+caixa entre CLI e
composição foi exata em 237/237, e as 11 repetições foram `stored`→`hit` com
resultado idêntico.

A matriz documento×página×método×camada contém 132 células: 66 coberturas base
de seis métodos (19 `CONCLUIDO`, 47 `NAO_DETECCAO`) e 66 camadas de anotação
`NOT_APPLICABLE`, pois a composição E15 analisa o desenho base. As 163
anotações de origem foram inspecionadas na aparência, sem virar referência do
detector. O checkpoint gerou 220 observações legadas e 17 E05; E06, E07, E08
template e E10 produziram zero, com cobertura explícita. Todos os 237
candidatos são exclusivos preservados para revisão, sem probabilidade calibrada
nem promoção automática. Não houve conflito ou duplicata entre métodos nesta
coleção, portanto essas propriedades não são demonstradas por ela.

C localizou 45 casos selecionados: 10 FP claros do aterramento legado, dois
prováveis erros de classe, 14 formas E05 plausíveis e três ambíguas, além de
outros tipos de ambiguidade. Há um FN visual da união no detalhe P2 de
`1251985467`; três omissões do template E08 não foram automaticamente
classificadas como FN da união. Esses achados são limites conhecidos dos
detectores, sujeitos a revisão de domínio, e **não** formam estimativa exaustiva
de precisão/recall ou homologação. Nenhuma regressão nova da ativação E15 foi
identificada frente ao baseline de identidade comprovada.

C auditou os journals isolados de tile falho, modelo ausente, OOM e
cancelamento: estados `failed`/`cancelled`, cache `miss`, resultado parcial
preservado e nenhum cache integral da tentativa interrompida. No caso OOM, o
cache do snapshot final foi criado apenas na nova tentativa bem-sucedida,
seguida de `hit`; B verificou ausência de cache imediatamente após a falha.

| Evidência C em `tmp/e15-simbologia/visual/` | SHA-256 |
|---|---|
| `relatorio-vp-e15.md` | `862a03e45a1d4441841a0d43341a79bf9f8cdb1a9643694bbc0bb36b42ee1198` |
| `visual-findings-e15.json` | `3599114ae737295c95c601903ef875a6519412b04f05941fbe26f8acc7325b79` |
| `coverage-doc-page-method-layer.csv` | `c19b0f421de419a55f55aae14824a0b3eed383b1a363078ef76079932a655dda` |
| `checkpoint-identity.json` | `c52b75343756db91eb7696b45447b6d46d1c7ffdaf673138888234e255156ba1` |
| `comparison-identity.json` | `8b96478c1fe493ae525162ec4432e5b575b49ee5df1767c97fc2235be2b613d6` |
| `partial-audit.json` | `bc6c47cb8d5316ceeee0cbb0b48fdefe86b5fb493e854efa59d93aeac0a84963` |

## Limites e próximo passo

Os artefatos V-P/V-B ficam em `tmp/` e são ignorados pelo Git; sua auditoria
requer preservar esse workspace. O conjunto real inspecionado é de
desenvolvimento. A reserva sintética permanece lacrada para E16. A E15 não
reivindica ganho de acurácia, resolução de IDs pendentes E07, homologação de
campo nem aceitação integrada E16. Retenção dos journals parciais e os FP/FN
conhecidos são pontos de acompanhamento futuro. Não houve commit, publicação
ou implantação.
