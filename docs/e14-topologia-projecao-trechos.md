# E14 — Topologia e projeção dos trechos

Execução em 16/09/2026 sobre `af8ead2`, Git inicialmente limpo;
`HEAD...origin/main = 0 0` contra a referência local, sem fetch. Nenhum `AGENTS.md`
no repositório ou ancestrais aplicáveis. E13 concluída e integrada em `af8ead2`;
roadmap, diagnóstico D06, E10/E13/E12A, ADR 0015 e módulos solicitados conferidos.
As diferenças desde o diagnóstico 1.14.0/22.0 correspondem a E11–E13: a base efetiva
é extrator 1.17.0 e interpretador 24.0. Não havia alterações locais a preservar.
E08/E09 permanecem bloqueadas; suas correções integradas não foram revertidas.

## Resultado e unidade de contagem

**Dez trechos físicos representados, nove pontos físicos, sete pares visíveis
corretos, três continuidades explícitas e seis comprimentos associados corretamente.**
Os quatro comprimentos ausentes continuam ausentes. A projeção tem dez pontos
elétricos para oito cabos confirmados; eles não equivalem a dez pontos físicos.
A revisão técnica de 14 m, os neutros N-4 sem catálogo, o cabo diagonal com medida
não resolvida e as continuidades continuam pendentes. Nenhum desses registros foi
promovido para satisfazer contagem. Tipo e modalidade permanecem desconhecidos,
com motivo na API/UI/XLSX, inclusive P4: a casa não prova padrão/ENTREGA.

Isso conclui o escopo topológico E14, não o aceite integral E15. A referência
continua com 139 registros. Núcleo E13 preservado: **29 TP / zero FN / zero FP**.
Classificação de modelos, autoridade das revisões, documentação integral,
equipamentos simbólicos e metas de cobertura automática continuam em E15.

## Mudanças e decisões

- `adapters/interpretation/span_rules.py`: orienta o traçado por identificadores
  locais isolados antes de usar as caixas deslocadas das legendas de poste.
  Distância máxima e margem de ambiguidade impedem escolher entre rótulos empatados.
  A geometria de V3-4 passa de P3 em P4 para P3→P4 correto. Não decide tipo de ponto.
- `application/automatic_promotion.py`: quando há vetor associado, o ID do ponto
  elétrico usa endpoint exato/página, tensão, configuração, tipo e poste. Deduplica
  os pontos acrescentados no mesmo lote e preserva elementos/pontos históricos na
  repetição. Tensões/configurações diferentes permanecem separadas. As guardas de
  revisão, associação, comprimento e reconciliação continuam em vigor.
- `application/spans.py`: todos os cabos confirmados com os dois pontos existentes
  podem aparecer; não exige identificador V, classificação de ambos os postes ou
  entrega. Isso corrige o filtro que ocultava 36/83 m sem inventar classificação.
- `application/physical_topology.py` e `physical_spans.py`: IDs físicos independem
  do cabo, usam a geometria completa e aceitam sentido inverso. Igual comprimento,
  proximidade, cruzamento interior ou somente endpoints iguais não fundem caminhos.
  Agrega propostas por traçado, conserva IDs/códigos de cada condutor e prioriza
  comprimento/geometria/situação efetivamente confirmados na revisão humana.
- `application/drawing_continuations.py`: representação parcial na borda exata
  de uma janela branca retangular grande do PDF. Exige continuidade colinear de
  mesmo estilo a um traçado associado, ou rótulo de cabo cortado na borda com
  orientação compatível e candidato único. As três saídas conservam vetor, janela
  e evidências da âncora. Não cria cabo, poste, ponto elétrico ou endpoint externo.
  Empates, linha tracejada auxiliar, frame isolado, página diferente, cruzamento
  e vizinho apenas próximo ficam fora. Janelas sem essa evidência explícita não
  são suportadas por essa regra; não generalizar o resultado deste PDF.
- Contrato `PhysicalSpanDto` e `ReviewSessionResponse.physical_spans`: identidade,
  membros, geometria, medidas, tipo/modalidade, motivos de revisão, continuidade
  e proveniência. `end_point_id=null` representa continuação além do desenho.
- `review_api.py`, `deliverable_exports.py`, `review_panel.py`: nova aba **Trechos
  físicos**, uma linha por caminho; aba **Vãos** permanece uma linha por cabo
  confirmado, com suas colunas antigas. Navegação usa a geometria do servidor e
  não decide fatos no cliente. A seleção de continuidade limpa a revisão anterior.
- `scripts/experiments/topology_audit.py`: comparador público opt-in, separado da
  inferência, com bijeção de endpoints, nome na extremidade correta, medida exata,
  identidades compartilhadas, duplicatas e continuidade explícita. Sem ranking temporal.

## Mapa de endpoints e trechos

U1–U4 são nomes apenas da referência E10, nunca identificadores operacionais
inventados no produto. Cada linha tem IDs completos de trecho/endpoints,
propostas/ativos/fontes, geometria e linha XLSX em `tmp/rede-1256407599/e14/audit-final.json`.

| Referência | Endpoints físicos | Medida | Representação e revisão |
|---|---|---:|---|
| V3-4 | P3 → P4 | 14 m | Um traçado; cabo com revisão técnica pendente; zero ativo confirmado |
| V2-3 | P2 → P3 | 100 m | Dois cabos distintos, fase/neutro, um trecho; duas leituras do neutro já consolidadas por E13 |
| V1-2 | P1 → P2 | 80 m | Fase/neutro distintos, um trecho |
| V1-5 | P1 → P5 | 57 m | Fase/neutro distintos, um trecho |
| T36 | P5 → U1 | 36 m | Fase confirmada e N-4 pendente; um trecho, navegável |
| T83 | P5 → U2 | 83 m | Fase confirmada e N-4 pendente; um trecho, navegável |
| Tdiag | U2 → U3 | Desconhecida | Traçado e cabo proposto presentes; não usa altura ou medida vizinha |
| Tbottom | U2 → fora do desenho | Desconhecida | Continuidade explícita, destino nulo, sem cabo/ponto externo criado |
| Tright | U3 → fora do desenho | Desconhecida | Continuidade explícita, destino nulo, sem cabo/ponto externo criado |
| Tleft | U4 → fora do desenho | Desconhecida | Rótulo cortado sustenta candidato revisável; não completa código/catalogação |

P1 compartilha V1-2/V1-5, P2 compartilha V1-2/V2-3, P3 compartilha V2-3/V3-4,
P5 compartilha V1-5/T36/T83, U2 compartilha T83/Tdiag/Tbottom e U3 compartilha
Tdiag/Tright. As três bordas não recebem IDs de pontos físicos externos. Não existe
vínculo fabricado entre U4 e os outros oito pontos. Todos os dez tipos/modalidades
continuam desconhecidos por falta de classificação positiva, com pendência explícita.

## Comparação na mesma referência

| Método | Pares visíveis completos / 7 | Medida + endpoints + nomes / 6 | Pontos com identidade consistente / 9 | Continuidades / 3 |
|---|---:|---:|---:|---:|
| E13, representação por proposta/cabo | 4 | 3 | 2 | 0 |
| Grafo E12A sobre E13 | 1 | 1 | 5 | 0 |
| E14, projeção física | 7 | 6 | 9 | 3 |
| Grafo E12A sobre E14 | 1 | 1 | 5 | 0 |

A métrica de medida é conjunta: E13 já lia seis valores, mas somente três tinham
nome/endpoints corretos nesse teste estrito. Os caminhos por condutor do baseline
produzem cinco repetições de trecho físico; isso não são cinco ativos duplicados.
Sua identidade de candidato usa extremidades por proposta, sem alegar que pontos
isolados já estivessem homologados. O grafo perde um par visível e troca/omite nomes
ou medidas em outros; seus sete pontos cobertos não constituem nove pontos exatos.
E14 tem zero caminhos físicos duplicados ou sem correspondência. Grafo permanece
experimental, sem promoção. Não houve uso/ajuste das reservas H01/H02/H03.

## Validações e inspeções

- Validação ampliada com os sete arquivos obrigatórios E14, regressões E14,
  E13/E12A, revisão humana, Qt e OpenAPI: **162 testes aprovados na repetição final**. A navegação e as regressões
  topológicas também passaram em rodada de **51 testes**, após a correção visual.
- Contratos completos, handshake, fronteira do cliente e regressões E14:
  **76 testes aprovados**. API/piso 1.6.0 validado; regressões mantêm recusas de
  versões futuras/antigas e leitura de JSON sem a coleção nova.
- Mypy aprovado em **352 arquivos**, Ruff e formatação aprovados, complexidade
  aprovada em **2.856 funções/métodos** sem rank E/F; `git diff --check` aprovado.
- Benchmark final real: 2.065 evidências, 246 OCR, 53 propostas brutas, 43 finais,
  47 relações, oito confirmações, 13 regiões, oito linhas de Vãos e dez trechos
  físicos; zero diagnósticos. Exportação XLSX validada célula a célula pelo benchmark.
- Auditoria E10: 139 referências preservadas, 29/29 no núcleo, mapa individual dos
  dez trechos até XLSX, seis medidas corretas e quatro desconhecidas. Nenhum grupo
  de revisão técnica pendente foi confirmado. Fonte preservada: 988.018 bytes,
  SHA-256 `0793c292df9722ff48df31ab052018d4233ad3541706f50f53e994cc1670af06`, mesmo mtime.
- Navegação Qt do snapshot final no PDF real via gateway de teste: **10/10**, com
  sobreposição da geometria conferida. Inspeção Poppler da página e recortes de
  P3/P4, rede existente e U4; capturas privadas `ui-*.png`. Matriz sintética cobre
  as quatro situações e três tipos, sem atribuir essas classes ao PDF real.
- Duração final: 169,932 s até regiões/vãos, 173,088 s incluindo Resultados/XLSX.
  Houve testes independentes durante a execução; não é ensaio isolado de desempenho,
  nem comparação temporal. Não houve timeout, corte de cobertura ou ranking por tempo.

Falhas intermediárias foram corrigidas: fixtures sem limpar terminais antigos,
chave de atributo repetida em fixture, campo de estado Qt incorreto, expectativa de
abas/handshake desatualizada, tipagem/formatação e revisão anterior ainda visível ao
selecionar continuidade. Nenhuma dessas rodadas foi usada para concluir a etapa.
Gate público integral e cobertura não foram repetidos: pertencem ao aceite E15.
Não há alegação de leitura integral do projeto ou de generalização a outros PDFs.

Comandos executados na raiz com Python da `.venv`:

```powershell
git status --short
git log -6 --oneline
git rev-list --left-right --count HEAD...origin/main
.venv/Scripts/python.exe -m scripts.generate_openapi_v1
.venv/Scripts/python.exe -m pytest tests/unit/test_spans.py tests/unit/test_topology_path_compliance.py tests/unit/test_e08_association.py tests/integration/test_interpretation_pipeline.py tests/server/test_review_api.py tests/server/test_deliverable_exports.py tests/e2e/test_span_compliance_ui.py tests/unit/test_e14_topology.py tests/integration/test_review_panel.py tests/contracts/test_openapi_snapshot.py tests/unit/test_e13_occurrences.py tests/unit/test_network_alternatives.py tests/integration/test_human_review.py -q -p no:cacheprovider --basetemp tmp/e14-final-verified
.venv/Scripts/python.exe -m pytest tests/contracts tests/unit/test_client_connection.py tests/unit/test_e14_topology.py tests/unit/test_review_panel_remote_boundary.py -q -p no:cacheprovider --basetemp tmp/e14-contracts-final
.venv/Scripts/python.exe -m pytest tests/integration/test_review_panel.py tests/unit/test_e14_topology.py -q -p no:cacheprovider --basetemp tmp/e14-navigation-final
.venv/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e14/benchmark-final.json --runtime-directory tmp/e01/runtime --telemetry
.venv/Scripts/python.exe -m scripts.experiments.topology_audit --baseline tmp/rede-1256407599/e13/benchmark-final.json --current tmp/rede-1256407599/e14/benchmark-final.json --reference tmp/rede-1256407599/e10/inventory.json --output tmp/rede-1256407599/e14/topology-audit-final.json
$env:PYTHONPATH=(Get-Location).Path
.venv/Scripts/python.exe tmp/rede-1256407599/e14/audit.py
.venv/Scripts/python.exe tmp/rede-1256407599/e14/inspect_ui.py
pdftoppm -scale-to 2800 -singlefile -png 'examples/PROJETO DE REDE 1256407599.pdf' 'tmp/rede-1256407599/e14/source'
.venv/Scripts/python.exe -m ruff check src tests scripts/experiments/topology_audit.py
.venv/Scripts/python.exe -m ruff format --check src tests scripts/experiments/topology_audit.py
.venv/Scripts/python.exe -m mypy src tests scripts/experiments/topology_audit.py --cache-dir tmp/e14-mypy-final
.venv/Scripts/python.exe scripts/complexity_gate.py src
git diff --check
```

Logs/artefatos privados em `tmp/rede-1256407599/e14/`: `required-final-verified.log`,
`contracts-final.log`, `navigation-final.log`, `mypy-final.log`, `benchmark-final.json`,
`topology-audit-final.json`, `audit-final.json`, `ui-navigation.json`, `ui.log` e PNGs.
PDFs, rasters, transcrições e dados privados continuam ignorados no Git. Testes
públicos usam fixtures sintéticas; nenhum depende do PDF ou do runtime OCR real.

## Compatibilidade, rollback e handoff

Interpretador **25.0**, API/piso **1.6.0**. A mudança de contrato foi necessária para
expor agrupamento físico, propostas pendentes e destino externo ausente sem mudar
`cable_element_id` obrigatório das linhas legadas de Vãos. DTO novo é aditivo e
sua coleção ausente é lida como vazia, mas clientes antigos usam `extra=forbid`;
por isso o handshake exige atualização coordenada, sem anunciar compatibilidade
binária falsa. Nenhuma alteração em domínio persistido, codec, banco ou snapshots.

Novas análises corrigem orientação e IDs elétricos; a guarda existente exige
reconciliação quando a folha tem decisões anteriores. A sessão e os ativos antigos
não são reescritos. Rollback exige voltar cliente/servidor juntos; o agregado antigo
continua legível, sem apagar decisões ou converter pendências em confirmações.
Os IDs de cabos continuam por ocorrência; a coleção física é projeção de leitura.

E15 recebe classificação/modelos, autoridade de revisões, equipamentos, documentação,
metas de automação, casos reservados e gate completo. E08/E09 mantêm seus bloqueios
históricos, inclusive T02 do primeiro PDF e classificação de padrão/postes. As
regressões E08 passaram; o primeiro PDF não foi re-homologado nesta etapa.
Não houve commit, publicação, consulta SQL operacional ou envio de PDF externo.
