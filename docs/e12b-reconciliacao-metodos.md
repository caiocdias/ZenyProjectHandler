# E12B — Reconciliação e confiança entre métodos

Execução em 15/09/2026 sobre `67a5457`, Git inicialmente limpo, sincronizado com
`origin/main` (`0 0`). Nenhum AGENTS.md encontrado no repositório ou ancestrais.
Roadmap/diretriz, E10/E12A, portas, extração, interpretação, promoção, cache, revisão,
DTOs e composição conferidos. E12A efetivamente executou DB/SVTR e grafo global;
os relatórios, matriz de erros e rejeições estão preservados em seu handoff.
Nenhuma alteração anterior foi sobrescrita. E08/E09 permanecem bloqueadas.

## Decisão de integração

- **Vertical:** mantém interpretação operacional e as regras E11 de revisão técnica.
- **DB/SVTR:** integrado como fonte documental auxiliar **opt-in**, pelo ganho de
  leitura integral de uma coordenada observado em E12A. Não substitui o Tesseract
  nem alimenta automaticamente catálogo, associação, situação ou topologia.
- **Grafo global:** continua rejeitado para integração direta. E13 recebe as três
  correções U1 e regressões P3 de E12A; E14 recebe `scripts/experiments/global_graph.py`,
  solver global com abstenção, nós/arestas e seus testes. Antes de ativar, resolver
  identidade física dos suportes e condutores paralelos; nenhuma aresta vira fato
  porque a distância ou o comprimento coincide. Nenhum método foi escolhido por tempo.

Há ganho real, portanto não se aplica a condição de ampliar E12A por ausência de
qualquer candidato útil. O ganho é de evidência documental revisável, não de ativos
automaticamente confirmados nem de leitura integral do projeto.

## Arquivos e contratos

- `adapters/analysis/rapid_ocr.py`: motor local de E12A movido sem trocar modelo ou
  algoritmo; a entrada antiga em `scripts/experiments/rapid_ocr.py` reexporta a classe.
  RapidOCR 1.4.4, ONNX Runtime 1.30.0, três modelos e hashes conforme E12A.
- `rapid_evidence.py`: adaptador complementar; grade independente da referência,
  3×4 com sobreposição 0,02, 600 DPI, base/aparência separadas. Preserva os 328
  registros brutos do ensaio, inclusive leituras fora do escopo e repetições.
- `ports/analysis.py`: porta complementar aditiva e callbacks opcionais de progresso
  e cancelamento na solicitação. Adaptadores antigos não precisam implementá-los.
- `application/method_reconciliation.py`: composição
  `documentary-coordinate-review-1`. Seleciona pares completos de seis/sete dígitos
  pela estrutura literal, sem lista de valores esperados nem consulta ao inventário.
  Prefixos/pontuação não são parte do valor numérico, mas o literal original permanece.
  Não corrige dígitos ou completa fragmentos por catálogo.
- Cada observação possui identidade derivada de hash da fonte, página, camada,
  assinatura de método/modelos, polígono e literal. Igualdade textual e proximidade
  não fundem objetos físicos. Leituras repetidas continuam observações separadas;
  o número de leituras não equivale ao número de ocorrências ou decisões humanas.
- A sobreposição localiza alternativas de coordenadas completas na mesma página
  e camada base. Preserva chaves/IDs, método, assinatura, versão de extração, literal
  e geometria da base. Origem, raster SHA-256 e transformação inversa do neural
  permanecem no envelope `leitura_metodo` dos atributos de evidência.
- Resoluções: `complement_requires_review`, `agreement_uncalibrated`,
  `conflict_requires_review`, `technical_layer_review`, `outside_selected_scope`.
  Acordo não confirma; erro calibrado é `null`. Score bruto tem origem própria e
  `score_is_probability=false`, sem média, votação ou comparação entre motores.
- `interpretation_pipeline.py` anexa discordâncias às propostas que usam exatamente
  a evidência base afetada. Mantém as alternativas em `reconciliacao_metodos`, marca
  conflito e impede promoção por `reconciliacao_metodos_pendente`. A revisão humana
  existente continua explícita; nenhuma decisão é transferida por geometria parecida.
- `ReviewSessionResponse.method_readings` é aditivo, vazio por padrão; apenas
  leituras selecionadas chegam à aba **Leituras auxiliares** e à planilha homônima
  de Resultados. API preserva os detalhes e a navegação à folha. Literais auxiliares
  ficam fora de `conteudo_bruto`, impedindo consumo acidental por regras antigas.
  O novo campo não cria um comando para aprovar coordenada documental isolada:
  esses valores continuam candidatos de conferência, sem alteração do agregado.
  Uma proposta afetada usa a revisão humana já existente; revisões E11 mantêm sua
  escolha de vigência e histórico próprios. E15 recebe a homologação documental.
- `docs/api/openapi-v1.json` regenerado. Não há migração de banco, reescrita de
  snapshots ou alteração dos tipos de ativos. A persistência JSON existente já
  suporta os atributos adicionais. Cliente continua sem modelos/OCR local.

## Cache, análise longa e falhas

Extrator `1.17.0`; interpretador de categorias permanece `23.0`. A composição entra
na assinatura do analisador e na identidade/parâmetros da execução semântica.
O cache inclui modelos SHA-256, versão do motor/runtime, parâmetros, grade, camadas,
limites de memória e fonte; identidades incompatíveis não reutilizam resultados.
A assinatura da sessão de revisão também inclui os envelopes auxiliares.

Cada tile é limitado a 8 MP antes de rasterizar; RGB é liberado após a chamada.
Há limite explícito de 10.000 observações auxiliares e telemetria por tile; atingir
o limite produz falha parcial. O pico total do runtime ONNX não foi medido nesta
etapa e não se confunde com o limite de raster. Não existe teto de duração total.

Falha de tile conserva os demais tiles; motor ausente gera diagnóstico específico.
`document_analysis.py` persiste evidências e estado **FALHOU** ou **CANCELADA**, sem
log de sucesso. Não grava cache da extração incompleta; o pipeline recusa promoção
a partir dela, e o job não chega a sucesso. Retomar permite nova tentativa.
Cancelamento ocorre entre inferências, sem interromper ONNX no meio de uma chamada.
As fronteiras de cancelamento do extrator vertical continuam as existentes.
O teste de job existente avança o relógio em **20 minutos**, mantém progresso e
cancela sem disponibilizar resultado integral.

Rollback: desabilitar `ZENY_SERVER_COMPLEMENTARY_OCR` restaura a composição vertical,
com outra assinatura. Não apaga evidências, decisões ou histórico de execuções novas.
Dependências opcionais permanecem no lock experimental, fora dos builds padrão.

## Medições e validações

Relatórios privados em `tmp/rede-1256407599/e12b/`. Inventário E10 mantém 139 itens,
29 ocorrências operacionais e 64 documentais. Nenhum caso reservado H01/H02/H03 ou
documento candidato à reserva foi aberto, gerado ou usado para ajuste.

Primeira comparação real: 38 propostas, nove confirmações, sete vãos em ambas as
composições; 328 observações auxiliares, 29 selecionadas para conferência, ganho de
`doc-delivery-coordinate`. Não houve alteração de pareamento operacional. A auditoria
identificou três falsos conflitos de formatação com dígitos iguais e motivou a
comparação por valor numérico exato, mantendo os literais. Medição final abaixo.

Validação intermediária: 71 testes passaram. Ao ampliar para UI/adaptador, seis
asserções falharam: a fixture tinha duas páginas (48 tiles, não 24) e o teste antigo
esperava somente duas abas. Expectativas corrigidas para os respectivos contratos;
nenhuma validação foi removida. Rodada corrigida: **98 testes aprovados em 45,18 s**.
Mypy em 347 arquivos e Ruff aprovados. Revalidação final será registrada no fechamento.

### Comandos reproduzíveis

Todos na raiz, sem SQL operacional e sem publicação. O mesmo runtime é usado nas
três composições finais; cada variante cria SQLite temporário e executa até DTO/XLSX.

```powershell
$env:PYTHONPATH = "$((Get-Location).Path)\src;$((Get-Location).Path)\.venv\Lib\site-packages"
tmp/e12a-runtime/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e12b/vertical-final.json --runtime-directory tmp/e01/runtime --telemetry
tmp/e12a-runtime/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e12b/neural-only-final.json --runtime-directory tmp/e01/runtime --native-only --complementary-ocr
tmp/e12a-runtime/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e12b/combined-final.json --runtime-directory tmp/e01/runtime --telemetry --complementary-ocr
.venv/Scripts/python.exe -m scripts.benchmark_method_reconciliation --reference tmp/rede-1256407599/e10/inventory.json --vertical tmp/rede-1256407599/e12b/vertical-final.json --combined tmp/rede-1256407599/e12b/combined-final.json --neural-only tmp/rede-1256407599/e12b/neural-only-final.json --output tmp/rede-1256407599/e12b/comparison-final.json
.venv/Scripts/python.exe -m pytest tests/unit/test_analysis_cache.py tests/unit/test_benchmark_network_pdf.py tests/integration/test_document_analysis.py tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py tests/server/test_review_api.py tests/unit/test_method_reconciliation.py tests/unit/test_rapid_evidence.py tests/unit/test_network_alternatives.py tests/server/test_jobs_api.py tests/integration/test_review_panel.py tests/server/test_deliverable_exports.py -q -p no:cacheprovider --basetemp tmp/e12b-verified
.venv/Scripts/python.exe -m mypy src tests scripts/benchmark_network_pdf.py scripts/benchmark_method_reconciliation.py --cache-dir tmp/e12b-mypy
.venv/Scripts/python.exe -m scripts.generate_openapi_v1
git diff --check
```

O comparador é pós-inferência: guarda 139 linhas, pareamento de código/situação/
associação, erros conhecidos entre confirmações, cobertura correta por campos e
revisão com denominadores explícitos. A precisão integral das confirmações continua
não demonstrada; cobertura integral automática e projeto integral permanecem zero.
Não transformar omissões em revisões realizadas nem denominador zero em acerto.

### Medição final e contribuição de cada método

As três execuções reais terminaram com saída zero, nenhum diagnóstico e fonte
intacta: 988.018 bytes, SHA-256
`0793c292df9722ff48df31ab052018d4233ad3541706f50f53e994cc1670af06`.
Modelos conferidos contra E12A. A auditoria E12A foi reexecutada e passou novamente.

| Composição | TP/FN/FP no núcleo | Confirmações | Erros conhecidos entre confirmações | Revisão do núcleo |
|---|---|---:|---|---|
| Vertical, neural desligado | 24/5/4 | 9 | 1/9 = 11,11% | 19/29 = 65,52% |
| Neural auxiliar, Tesseract desligado | 0/29/0 | 0 | Indefinido | 0/29; omissões, não revisões feitas |
| Vertical + neural auxiliar | 24/5/4 | 9 | 1/9 = 11,11% | 19/29 = 65,52% |

- **Contribuição neural:** recupera `doc-delivery-coordinate` como literal integral
  adicional, agora persistido e presente no DTO, na interface e no XLSX como candidato
  de conferência. Desligar o neural perde esse complemento; desligar o Tesseract
  mantém o complemento, mas perde a leitura operacional. A variante neural isolada
  avalia o escopo auxiliar selecionado; não é a reexecução do interpretador neural
  geral de E12A (aquele teve 7/29 e continua rejeitado).
- **Coordenadas em um único fragmento:** pares numéricos completos exatos em 4/11
  referências documentais com vertical e 6/11 com neural/combinação. Esse denominador
  é um subconjunto explícito dos 64 itens; não mede toda a documentação ou a capacidade
  do pareador de reunir fragmentos. `doc-coordinate` já tinha literal localizável no
  vertical; não é contado como segundo ganho novo de literal.
- **Erros e revisão auxiliares:** 328 observações mantidas; 14 de coordenadas na base
  e 15 na aparência selecionadas. Na base, oito observações têm par exato em referência
  documental, uma corresponde ao controle negativo da cerca e cinco não têm par
  próximo na referência. Nenhuma vira ativo. Isso não certifica cinco leituras como
  corretas nem exclui o negativo. As 15 leituras da aparência exigem conferência de
  vigência. São **29 observações**, incluindo repetições, e não 29 objetos físicos ou
  decisões humanas já realizadas. Taxa de erro entre confirmações auxiliares: indefinida,
  pois houve zero confirmações. Não se anuncia precisão de 100%.
- Resoluções finais na base: dez acordos não calibrados e quatro complementos pendentes;
  aparência: 15 pendências de camada técnica. Zero conflitos numéricos reais neste
  subconjunto; conflitos e acordos errados são exercitados pelos controles sintéticos.
- **Não regressão:** pareamento individual operacional idêntico, não apenas contagens.
  Precisão do núcleo permanece 24/28 = 85,71%, recall 24/29 = 82,76%; quatro FP e cinco
  FN não foram ocultados. Cobertura automática correta **por campos** 8/29 = 27,59%;
  cobertura integral automática comprovada 0/29. Revisão de propostas totais 29/38 =
  76,32%, sem aumento. A duplicata de neutro permanece erro conhecido de E13.
  Leitura integral do documento continua **0/1**; E12B não homologa E15.
- Durações até regiões/vãos e incluindo exportação: vertical 117,398/119,805 s;
  neural auxiliar isolado 77,077/78,910 s; combinação 184,656/187,282 s. São observações,
  não ranking nem limites. O benchmark de telemetria também inclui a aba Documentação,
  além das abas de Resultados; a auditoria final verifica nomes/conteúdo de cada aba.

### Fechamento e handoff

**E12B #concluida no escopo de integração auxiliar e reconciliação.** Critérios conferidos
com ganho documental, ablações reais, ausência de regressão operacional e guardas
sintéticas de discordância/acordo errado/falha. **167 testes aprovados em 24,40 s**:
validações obrigatórias, novos testes, jobs, UI, exportação, configuração e contratos.
Mypy passou em **347 arquivos**; Ruff e formatação passaram em **369 arquivos**;
complexidade passou em **2.819 funções/métodos**; gate de fonte do cliente magro e
`git diff --check` aprovados. OpenAPI regenerada e teste do snapshot aprovado.

Comandos adicionais de fechamento:

```powershell
# Mesma lista de 12 módulos do comando pytest acima, acrescida de:
# tests/server/test_config.py tests/contracts
# com --basetemp tmp/e12b-finish
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe scripts/complexity_gate.py src
.venv/Scripts/python.exe scripts/client_artifact_gate.py --source-only
.venv/Scripts/python.exe tmp/rede-1256407599/e12b/verify_final.py
.venv/Scripts/python.exe tmp/rede-1256407599/e12a/audit.py
```

Evidências finais: `vertical-final.json`, `neural-only-final.json`, `combined-final.json`,
`comparison-final.json` (139 linhas por composição e matriz por ocorrência), logs
homônimos e `manifest-final.json`, com hashes, modelos/fonte íntegros e auditoria aprovada.
Validações em `tmp/e12b-finish-tests.log`, `tmp/e12b-mypy.log`; artefatos privados ignorados.
Somente o comparador recebe a referência, após inferência; os adaptadores nunca a recebem.

Pendências: decisão documental de valores isolados permanece conferência, sem comando
de aceitação de coordenadas novas; E13/E14 recebem associação/topologia e duplicata,
conforme rejeição do grafo acima. E15 recebe leitura integral, inspeção visual completa,
avaliação reservada, fluxo HTTP/Qt real e gate público completo com cobertura, que não
foram repetidos nesta etapa. A nova aba foi validada com Qt offscreen; não se declara
homologação visual integral do PDF. Nenhum bloqueio impede o aceite restrito de E12B.
Sem commit, publicação, SQL operacional ou instalação no servidor operacional.
