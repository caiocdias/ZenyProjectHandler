# E13 — Associação semântica e promoção por campo

Execução de 24/09/2026 sobre `c0de8b5f9911cc9ffc08950757784ee7c506e0c3`.
A árvore estava limpa antes de E13. E12 estava `#concluida`; sua calibração
real não tinha célula elegível. E07 segue historicamente bloqueada, com 21
variantes habilitadas e 344 `pending`; E13 não altera esse inventário.

## Contrato entregue

`ExecutarPipelineInterpretacao.executar(..., simbolos=...)` recebe o resultado
imutável da E12 opcionalmente. A assinatura completa desse resultado entra na
identidade da execução e nos parâmetros persistidos. O fluxo sem símbolos
conserva sua identidade e seus resultados anteriores. Observações reconciliadas
recebem evidências VETOR/IMAGEM ligadas à execução de extração; cada ocorrência
produz no máximo uma proposta com os IDs das observações, alternativas,
referências e motivos. O score bruto permanece separado da probabilidade
calibrada. A classe visível não escolhe item do catálogo: só um ID explícito
da observação, conferido contra a classe e o catálogo vigente, pode sugeri-lo.

Situação exige convenção local verificada ou situação validada; quantidade
exige cardinalidade de ativos explícita em todas as observações. Suporte exige
poste documental único na mesma página e camada, com margem geométrica para
vizinhos. Cor, círculos, texto, necessidade normativa, proximidade ambígua e
silêncio de outro detector não completam campos. Legenda e contexto informativo
ficam fora das regiões de rede. Estai e família desconhecida ficam visíveis
como proposta pendente: o enum legado não tem categoria observacional, então
usam envelope `EQUIPAMENTO` com `simbolo_papel` e sem catálogo/ativo; jamais
viram `CABO`. Esta limitação requer representação pública própria em E14.
Leituras originais de situação e quantidade, seus IDs e candidatos de suporte
permanecem em JSON de revisão mesmo quando entram em conflito. O adaptador de
benchmark E12 passou a transportar `prediction.situation` para a observação,
sem marcá-la como situação validada; cor e origem bruta são pistas, não vigência.

Promoção automática de proposta E13 exige `eligible` da E12, elegibilidade
patrimonial, catálogo explícito compatível e identidade, classe, situação,
quantidade e associação resolvidas separadamente. Conflito, camada anotada,
variante pendente e qualquer campo incerto barram a promoção. Topologia só
publica presença de símbolo E13 com classe, identidade, situação e associação
resolvidas, contexto operacional e elegibilidade E12 ou confirmação humana.
Não converte não detecção em presença. O fluxo legado mantém sua política e
testes anteriores. Revisão/reanálise conservam decisões e evidências por ID,
com base e anotação separadas; revisão anterior na folha torna nova proposta
pendente até reconciliação.

`relation_rules.py` não precisou de mudança: já bloqueava `associacao_pendente`.
Não houve alteração de enum/domínio público nem de DTO/API nesta etapa.

## Delegação e checkpoint

| Frente | Propriedade exclusiva e retorno |
|---|---|
| A `/root/codigo` | `application/interpretation_pipeline.py`, `application/analysis_regions.py`, `adapters/interpretation/category_analyzers.py`. Reportou 54 testes legados + 6 de regiões, Ruff/mypy dirigidos; fechou o contrato antes dos testes finais. |
| B `/root/testes` | Novos `tests/unit/test_e13_semantic_promotion.py` e `tests/integration/test_e13_semantic_pipeline.py`. Oráculos de exclusivo, pendências, revisão, reabertura, páginas/camadas/vizinhos e topologia; 36 testes no checkpoint. Corrigiu apenas suas fixtures exploratórias. |
| C `/root/pdfs` | Apenas `tmp/e13-simbologia/visual/`. Congelou observações visuais antes das predições: 11 panoramas e 44 tiles realmente abertos, com manifesto de 11 PDFs/11 páginas e SHA por fonte/imagem. Auditou o checkpoint semântico final e registrou achados localizados no relatório abaixo. |
| Coordenador `/root` | `application/automatic_promotion.py`, `application/topology_compliance.py`, `scripts/reconcile_symbol_benchmark.py`, `scripts/benchmark_semantic_e13.py`, este handoff e o roadmap. Integração serial e gates finais. |

O checkpoint de código está identificado pelos SHA-256 dos arquivos:

| Arquivo | SHA-256 |
|---|---|
| `application/interpretation_pipeline.py` | `9409b24f7962878cc7cc62f2099b8182b3b1867ad4413077171f0da283c79433` |
| `application/analysis_regions.py` | `9671cad788f7e62896ffcdb32604329d479c71eb2986dbbacd806b7cfb768e0f` |
| `adapters/interpretation/category_analyzers.py` | `f86a2641a75dbb486682ef7a525889f6c820fc5f46fc16e7415eafb20184b2cd` |
| `application/automatic_promotion.py` | `aa336f98c74a2d6ae3c30af4b6f62764de68a4e4a5bede0cae3198828703f38c` |
| `application/topology_compliance.py` | `078391d2a862c3f27302c569406263f7e29f14a5b6cc020b48ad3d0c378a67d7` |
| `scripts/reconcile_symbol_benchmark.py` | `ea1d5d298b92d44a05aaeba16e1006cfcaa8c0163c47f24037ece9e7508fa93a` |
| `scripts/benchmark_semantic_e13.py` | `94c29d16b1892f39af62f6f102f366ef4071fe568865ab16a99dc92fe585fcbf` |
| `tests/unit/test_e13_semantic_promotion.py` | `2640c475b36417ad133b5924c400a15ea38a31af268a287662791137b988b327` |
| `tests/integration/test_e13_semantic_pipeline.py` | `edd3de008e3b035fa05607356ecf875a49ff337800d8818deaf6da8d4d6fb143` |

## Validação integrada

Comandos na raiz usando `.venv`: `pytest` e `python -m scripts.*` nas linhas
abaixo significam, respectivamente, `.\.venv\Scripts\python.exe -m pytest` e
`.\.venv\Scripts\python.exe -m scripts.*`. Ruff e mypy foram chamados como
módulos pelo mesmo executável da `.venv`. Para V-I foram acrescentados
`-q -o cache_dir=tmp/e13-simbologia/pytest-cache --basetemp=tmp/e13-simbologia/v-i-a2`;
para V-N, `-q -o cache_dir=tmp/e13-simbologia/pytest-cache --basetemp=tmp/e13-simbologia/v-n-a2`.
O sandbox inicial negou o Python da Windows
Store apontado pela `.venv`; a execução aprovada fora dessa restrição usou a
mesma `.venv` existente, sem instalar pacotes. A tentativa com Python 3.12
bundled e pacotes 3.13 da `.venv` falhou em `pydantic_core`, por ABI diferente;
não conta como teste. O primeiro V-Q formato apontou um arquivo de topologia;
ele foi formatado e o recheck passou.

| Gate | Comando e resultado |
|---|---|
| V-I | `pytest tests/unit/test_rule_based_interpreter.py tests/unit/test_method_reconciliation.py tests/unit/test_topology_compliance.py tests/unit/test_topology_path_compliance.py tests/unit/test_e13_occurrences.py tests/unit/test_e14_topology.py tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py -q` com cache/basetemp em `tmp/e13-simbologia/`: **144 passed**, exit 0. |
| V-N | `pytest tests/unit/test_e13_semantic_promotion.py tests/integration/test_e13_semantic_pipeline.py -q` com cache/basetemp em `tmp/e13-simbologia/`: **36 passed**, exit 0. |
| V-Q | `ruff check .` exit 0; `ruff format --check .` no recheck: **423 arquivos formatados**, exit 0; `mypy` **386 fontes sem erro**, exit 0; `git diff --check` exit 0. |
| V-B inferência | `python -m scripts.benchmark_symbols synthetic --output tmp/e13-simbologia/benchmark-synthetic --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend`: 4 PDFs/6 páginas, 16 TP/15 FP/6 FN na união bruta com E09 experimental; exit 0. |
| V-B composição | `python -m scripts.reconcile_symbol_benchmark --predictions tmp/e13-simbologia/benchmark-synthetic/predictions.json --output tmp/e13-simbologia/composition-synthetic-a2 --reference tmp/e13-simbologia/benchmark-synthetic/reference.json --exclude-method structural-raster-graph --exclude-method structural-vector-graph`: 27 observações/27 ocorrências, 14 TP/4 FP/8 FN de classe exata, nove alternativas revisáveis; exit 0. |
| V-B semântico | `python -m scripts.benchmark_semantic_e13 --predictions tmp/e13-simbologia/benchmark-synthetic/predictions.json --output tmp/e13-simbologia/semantic-synthetic-a2.json --exclude-method structural-raster-graph --exclude-method structural-vector-graph`: 27 propostas/6 páginas, todas pendentes por falta de calibração/campos; exit 0. Teste sintético de exclusivo elegível com score bruto 0,20 e probabilidade calibrada 0,995 prova o ramo positivo ponta a ponta. |
| V-P inferência | `python -m scripts.benchmark_symbols examples --root examples --output tmp/e13-simbologia/benchmark-examples --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend`: **11 PDFs/11 páginas**, zero falhas, 240 predições; exit 0. |
| V-P composição | `python -m scripts.reconcile_symbol_benchmark --predictions tmp/e13-simbologia/benchmark-examples/predictions.json --output tmp/e13-simbologia/composition-examples-a2 --exclude-method structural-raster-graph --exclude-method structural-vector-graph`: 237/237 observações adotadas em 237 ocorrências; exit 0. |
| V-P semântico | `python -m scripts.benchmark_semantic_e13 --predictions tmp/e13-simbologia/benchmark-examples/predictions.json --output tmp/e13-simbologia/semantic-examples-a2.json --exclude-method structural-raster-graph --exclude-method structural-vector-graph`: 237 propostas, todas pendentes, zero ID catalogado, 237 quantidades pendentes; preserva 154 situações nulas, 63 `INSTALAR` e 20 `REMOVER` como pistas sem vigência validada; exit 0. |

A reserva `tests/fixtures/symbols/reserve.sealed.zip` permaneceu fechada,
SHA-256 `6874d0585269a0a68397319268076e8e788aff64fc2bc5d776e80efca739be7b`.
Exemplos já inspecionados são desenvolvimento e não medem precisão de campo.

## V-P: auditoria visual independente

O relatório `tmp/e13-simbologia/visual/relatorio-vp-e13.md` (SHA-256
`349721d986fbf55945ba4f20207cf70b43a2b403d240068a72eac127e667e9ba`)
documenta a inspeção real pré-predição de 55 imagens (11 panoramas e 44 tiles)
dos 11 PDFs/11 páginas, zero bloqueios, e 198 células por documento/página/
camada/método. O manifesto visual pré-predição está em
`tmp/e13-simbologia/visual/manifest-e13.json`
(SHA-256 `cda3faef21dbe3949f20f975933f9bf19f248a43b34b97527cf565ae3e253a01`)
e as notas congeladas em `observacoes-previas.md` (SHA-256
`f42c97673faa194344afd2fce7beedd33699fa8a4736cde1346537e265139dd5`).
O runner V-P não substitui a inspeção visual. Artefatos finais para comparar:
manifesto `76f489626f649e6f4ec1fc0e7ae15012de003bd50a44b205d51eee1890b926a3`,
predições `b1ed2ac9413be163b75135d9f267e83e856114636708b5fad8c23a7a905f0d51`,
composição a2 `c0db7ef89b4c5228fd55fb6715c48f4f8933e94d272d330ba8e156e3b7469144`,
propostas E13 a2 `bf679866897f9fb3cc35e98f858e404d44ebeff73e532e1b7a28138a94be730e`.
As auditorias `python tmp/e13-simbologia/visual/audit_checkpoint.py` e
`python tmp/e13-simbologia/visual/audit_semantic.py` passaram (exit 0), com
`checkpoint-identity.json` SHA-256
`8b8b535140a769b8d3a373cf3ca14fcba003d7f7ac954fb164551ac8d0779e87`
e `semantic-audit.json` SHA-256
`ed91342aea85eef52dabf519daaf04f87e079bfee047619debc1a56cb501ba15`.
Confirmaram 240/240 predições E12 idênticas, 237/237 observações brutas
pareadas e 237/237 propostas vinculadas, sem divergência de classe, decisão ou
das 83 pistas de situação (63 `INSTALAR`, 20 `REMOVER`). Os 220 IDs canônicos
legados mudaram com o transporte dessas pistas; a comparação usou predição
original, geometria e classe, não o ID canônico superado.

Entre os 17 exclusivos E05, 14 têm forma visual plausível e três são ambíguos;
todos chegaram à proposta sem segundo detector. Três FPs experimentais E09
ficaram fora da composição. Dez FPs legados visualmente claros continuam
revisáveis e sem promoção. O transformador raster junto a P2 em `1251985467`
continua FN da união; o template de terra omite três glifos visíveis, sem
equivaler sempre a FN da união. Estai textual e legenda não geraram ocorrência
nessa amostra. O relatório explicita os localizadores e que os 192 legados
restantes foram vistos em contatos, com adjudicações anteriores reaproveitadas
sob identidade estrita; não mede precisão nem recall global.

## Limites e próximo passo

A inferência E12 em exemplos reais não calibrou nenhuma célula; portanto
**nenhum ativo real foi promovido automaticamente**. O runner semântico de
benchmark usa um projeto mínimo por PDF e não recebe leituras documentais;
assim, associação real a suportes continua pendente nesse artefato. Os testes
integrados usam evidências documentais autorais para exercitar suporte único,
vizinhos ambíguos e reabertura SQLite. E14 deverá expor alternativas, papéis
observacionais e pendências na UI/API/exportação sem chamar o envelope de estai
de equipamento patrimonial. O enum atual exige `EXISTENTE` como placeholder
nas 237 propostas reais; consumidores devem verificar `situacao_pendente` e
`simbolo_situacao_resolvida=false`, preservando as pistas originais de situação.

Nenhum commit, publicação ou implantação foi feito.
