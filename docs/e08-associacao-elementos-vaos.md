# E08 — Associação de elementos e vãos

Retomada em 17/09/2026: veja a [validação da release 0.4.0](validacao-e08-e09-0.4.0.md)
para as correções, métricas e pendências atuais. O conteúdo abaixo preserva a execução
histórica de 14/09/2026; seus limites de tempo não são critérios de aceite vigentes.

**Estado: #bloqueada para aceite.** Correções e gate de código validados; associação
integral de comprimentos e classificação/topologia ainda não atendem o aceite.

Execução em 14/09/2026 sobre `bb457ef`. Git inicialmente limpo, sem `AGENTS.md`
aplicável na hierarquia ou nas pastas de código. E01 e E07 concluídas e conferidas;
o commit atual integra a entrega E07 sobre `f82b1c2`, sem divergência posterior na
interpretação/topologia. Nenhum commit, publicação ou modificação do PDF original.

## Correções e invariantes

Interpretador **22.0**, com invalidação da assinatura semântica anterior. Extrator
permanece **1.14.0**. Não há mudança de contrato HTTP ou de norma.

- A normalização conserva a separação depois de parênteses: dois tokens como
  `CM3(1) U3(2)` continuam duas ocorrências. Qualificador não vira quantidade.
- Cabos sem associação inequívoca continuam como propostas conflitantes, com
  justificativa e `associacao_pendente`. A promoção não transforma caixa ou ponto
  de OCR em linha física.
- A situação observada no rótulo precede a cor do traçado compartilhado. Para OCR
  de contornos, a cor só é recuperada de pelo menos dois contornos preenchidos
  contidos na região do texto e em concordância, com seus IDs na proveniência.
- A orientação dos polígonos de OCR é medida nas mesmas coordenadas normalizadas
  dos traçados. Vetores curtos exigem segmentos quase retos, contorno e suporte
  de identificadores; fragmentos preenchidos de glifos não viram traçados.
- A guarda de comprimento perto de endpoint é proporcional ao tamanho do traçado,
  limitada pelo teto anterior. Diâmetro, altura nominal e áreas continuam negativos.
  Caixas/círculos não são riscos de supersessão; alterações legítimas continuam
  preservando a medida vigente e a substituída.
- Promoção não escolhe poste por proximidade quando falta relação. Relação dirigida
  à entrega não é transferida ao poste vizinho. Endpoints respeitam rótulo, distância
  máxima e ambiguidade; ausência de classe mantém tipo desconhecido.
- Altura/resistência sem formato não escolhe automaticamente um item circular,
  duplo T ou madeira. A ocorrência e os candidatos permanecem revisáveis, sem
  materializar um poste de classe inventada.
- Reutilizar a mesma sessão é leitura: não repromove rejeições nem regrava decisões.
  Nova interpretação de folha com decisões anteriores fica pendente de reconciliação;
  não copia decisões para novos UUIDs nem acrescenta automaticamente ativos duplicados.
  Sessões, decisões e agregado anteriores permanecem intactos. A reconciliação entre
  versões é explícita, não uma correspondência heurística silenciosa.

## Referência e comparação

São mantidos os denominadores E01: 95 ocorrências, 18 identificadores, 20 trechos
físicos, 18 pares de endpoints visíveis, 19 comprimentos e 20 exclusões.
Fonte da comparação: `tmp/e07-complete/inventory-reconciled.json`, com o inventário
original e suas correções auditadas por E07 preservados.

A auditoria usa código/qualificador normalizado, categoria, situação, evidência
textual da própria ocorrência e correspondência um a um, com a tolerância 0,01
original. Evidência auxiliar de coordenada, identificador ou comprimento não conta
como reconhecimento de um código. Precisão de ocorrência e correção de vínculo
são medidas separadamente. As 11 propostas de equipamento estão fora do denominador
inequívoco; não recebem precisão artificial.

Comparação final com a saída E07, reavaliada pelo mesmo auditor:

| Métrica | E07 | E08 | Meta E01 |
|---|---:|---:|---:|
| Ocorrências completas, situação e evidência próprias | 92 | 95 | 95 |
| Vínculos operacionais corretos dessas ocorrências | 90 | 95 | 95 |
| Trechos com ambos os endpoints visíveis corretos geometricamente | 16 | 18 | 18 |
| Comprimentos vigentes no traçado correto | 3 | 18 | 19 |
| Propostas elegíveis sem par no inventário | 2 | 0 | 0 |
| Ocorrências elegíveis confirmadas automaticamente | 92 | 35 | Sem meta isolada |

Precisão/recall das propostas E08 são **100%/100%** em cada grupo:
POSTE instalar 14/14, existente 3/3; MT instalar 18/18, existente 4/4;
BT instalar 16/16, existente 3/3; CABO instalar 28/28, existente 9/9.
Não se confunde recuperação revisável com confirmação física. As 35 confirmações
são cabos; 17 postes sem classe única, 41 estruturas sem poste materializado,
11 equipamentos ambíguos e 2 cabos com comprimento pendente totalizam 71 propostas
conflitantes. A queda de confirmações retira escolhas de catálogo e promoção não
sustentadas, em vez de ocultar essas ocorrências.

Os 37 cabos correspondem a **20 traçados vetoriais distintos**, com os 18 pares
visíveis corretos. Os dois endpoints fora da folha permanecem fora do denominador,
como fixado por E01: mede-se sua extremidade visível, não uma coordenada inventada
para a continuação. A primeira auditoria aplicava por engano o erro também a essas
extremidades excluídas; a correção foi aplicada igualmente a E07 e E08, sem mudar
inventário, tolerância ou metas. `audit-before.json` e `audit-final.json` guardam o
pareamento. O único comprimento originalmente desconhecido continua desconhecido.

As **28 linhas de Vãos** são projeções por cabo confirmado e segmento, não os
20 trechos físicos do inventário. A classificação topológica dessas linhas continua
`DESCONHECIDO`, pois os endpoints não têm classe suficiente. Portanto, os resultados
acima **não certificam a topologia elétrica completa nem o aceite E08**.

O benchmark agora carrega `ServicoRevisaoHumana`, projeta os DTOs de Resultados,
gera as abas Elementos/Vãos por `_results_sheets`, grava XLSX e reabre seu ZIP/XML.
Registra DTOs, linhas exportadas, hash e tamanho; compara as linhas com a sessão.
Não executa conformidade/SQL operacional, HTTP/jobs ou implantação. O tempo E01
continua medindo exatamente o escopo original; Resultados/exportação têm tempo
adicional explícito e total expandido. A memória cobre ambas as fases.

## Validação e artefatos

Artefatos reais e scripts de auditoria ficam somente em `tmp/e08/`, ignorado pelo Git.
Regressões públicas em `tests/unit/test_e08_association.py`, complementadas pelos
testes de interpretação, promoção, reanálise, revisão e exportação existentes.
As quatro primeiras regressões falharam antes da correção, em
`test-before-valid.log`. Uma tentativa anterior tinha uma chave incorreta na fixture;
foi corrigida antes de registrar o teste válido contra produção.

Conjunto obrigatório mais regressões e benchmark sintético: **125 aprovados em
13,80 s**, em `required-accepted.log`. Inclui controles de identificadores repetidos/qualificadores,
traçados paralelos, símbolos, medidas inválidas, ramal/entrega e revisão histórica.
Depois das extrações de helpers e da comparação integral das células XLSX, os
testes E08/benchmark passaram novamente: **16 aprovados em 2,70 s**. Mypy passou
em 334 arquivos; complexidade passou em 2.770 funções. O primeiro gate integral
teve 1.247 testes aprovados e cobertura de 87,40%, mas **foi reprovado** por
complexidade. Os helpers foram extraídos, sem relaxar o limite; esse gate inicial
não serve como aceite. A repetição integral final está registrada separadamente.

**Gate final aprovado**, saída zero em `gate-final.log`: **1.250 testes em 435,65 s**,
cobertura **87,71%** (mínimo 85,01%), integridade de dependências, Ruff check/format,
Mypy e complexidade aprovados. Nenhuma validação obrigatória deixou de ser executada.
As três verificações privadas do inventário E01 passaram novamente em 0,91 s,
em `reference-check.log`; os 18 identificadores mantêm evidência espacial na saída
final (`anchors-final.json`). `git diff --check` passou e os artefatos privados
continuam ignorados. Somente documentação foi editada após o gate final.

Inspeção visual: seis seleções de propostas da saída final, giro de 90°, navegação,
geometria e tiles de detalhe a 450 DPI em `PdfViewerWidget`, via gateway de teste
local que renderiza o PDF real. Arquivos `navigation.json`, `navigation-O*.png` e
`visual-navigation.log`. Amostras: qualificador adjacente O002; dimensão sem classe
O015; cabo existente sobre traçado compartilhado O059; trecho curto O062; cabo
próximo à casa O088; cabo sem medida O095. Destaques e seleção conferidos nos seis.
O teste é do componente com DTO real, não de uma sessão HTTP/SQL operacional.
A fonte da barra do Qt offscreen aparece como quadrados neste ambiente; não foi
usada para certificar tipografia da aplicação. Os rótulos do PDF e overlays são
legíveis nos tiles e foram inspecionados. A primeira execução do harness omitiu
dois argumentos obrigatórios; foi corrigida e repetida antes da inspeção final.

Medição final, sem outros trabalhos Python simultâneos: **15,501 s nativo /
56,904 s OCR** no escopo E01; **18,308 / 59,548 s** incluindo Resultados/exportação.
High-water Python **602,37 MiB**, Tesseract observado **80,46 MiB**, agregado
amostrado **452,55 MiB**, 407 amostras.
Os limites congelados são 25/60 s, 768/256 MiB e 1 GiB agregado. Amostragem de 200 ms
pode perder picos breves do subprocesso. Hash, tamanho e mtime da fonte preservados.

OCR real: 3.719 evidências (399 OCR), 109 propostas brutas, 106 finais,
212 relações, 35 confirmações, 21 regiões, 28 linhas de Vãos e zero diagnósticos
de execução. Nativo: 3.320 evidências, 8 propostas brutas, zero finais.
Resultados/exportação conferidos célula a célula nos dois fluxos. O XLSX OCR
contém 106 linhas de Elementos e 28 de Vãos; 18.066 bytes. DTOs, linhas, SHA-256
do XLSX e assinatura do interpretador estão no benchmark. O XLSX temporário é
descartado com a base isolada; as linhas ficam no snapshot privado.

## Bloqueios e trabalho remanescente para aceite

- O inventário chama o endpoint junto à casa de entrega, mas registra ausência da
  palavra PADRÃO. ADR 0015 exige evidência inequívoca de padrão. Legenda/convenção
  técnica não foi encontrada; a classificação não pode ser criada por proximidade
  com a casa. Solicitação de evidência enviada ao usuário durante a execução,
  sem resposta até o fechamento da medição. **Impacto:** ramal/padrão sem classe
  resolvida; **desbloqueio:** fornecer evidência técnica/convenção documentada ou
  revisar formalmente essa expectativa do inventário. Não alterar a referência
  apenas para melhorar a métrica.
- Os 17 postes têm dimensão, mas não formato/material suficiente para selecionar
  um item único de catálogo. Permanecem revisáveis; estruturas/equipamentos não
  recebem poste fictício para viabilizar promoção. **Evidência:** candidatos de
  catálogo nas propostas e recortes inspecionados, sem formato explícito.
  **Desbloqueio:** classificação técnica rastreável dos candidatos; a existência
  da ocorrência já está reconhecida, mas isso não prova um modelo de catálogo.
- `VaoDetectado` ainda projeta por cabo, com um `cabo_id` e uma situação. Cabos de
  situações diferentes compartilham trechos físicos. A contagem de linhas de Vãos
  não é a contagem de trechos físicos do inventário. Não agregar escolhendo uma
  situação arbitrária nem ocultar condutores. **Trabalho remanescente:** projetar
  agrupamento físico que preserve todos os cabos/situações, se necessário para o
  aceite de Vãos. É uma limitação de representação, não uma contagem de 28 ativos
  físicos inventados. Não houve mudança de contrato para ocultar essa diferença.
- T02/V2-3: os dois cabos agora têm traçado e endpoints corretos, mas a medida
  explícita de 13 m permanece sem vínculo inequívoco para o algoritmo. A margem
  entre candidatos é aproximadamente 0,0039918 frente à guarda 0,004; não se
  reduziu o limiar para favorecer esta folha. `comprimento_pendente=True`, estado
  conflitante e justificativa impedem a promoção de ambos. **Impacto:** 18/19
  comprimentos, abaixo da meta congelada. **Trabalho remanescente:** demonstrar
  suporte gráfico adicional para a associação (incluindo chamada/linha auxiliar)
  em fixture sintética com negativos, ou obter revisão técnica do caso. A falha
  da associação automática não transforma uma medida do inventário em negativa.

O impedimento externo é a falta de evidência de classificação; a associação da
medida e a representação de trechos são limitações de software separadas, ainda
não aceitas. Não declarar a etapa concluída nem iniciar o aceite E09 com esses
resultados. Nenhum orçamento ou denominador foi reduzido.

## Arquivos e reprodução

- Normalização/situação/catálogo: `adapters/interpretation/rule_support.py`,
  `category_analyzers.py` e versão em `rule_based.py`.
- Associação: `relation_rules.py` e `span_rules.py`.
- Promoção/revisão: `application/automatic_promotion.py` e
  `interpretation_pipeline.py`. `analysis_regions.py` e `spans.py` foram lidos e
  testados; permanecem sem alteração.
- Benchmark: `scripts/benchmark_network_pdf.py` e teste unitário correspondente.
- Regressões: `tests/unit/test_e08_association.py`,
  `test_rule_based_interpreter.py`, `test_spans.py` e
  `tests/integration/test_interpretation_pipeline.py`.
- Documentação: este handoff, índice/detalhe do roadmap, README e especificação
  funcional. ADR 0015 e inventários anteriores preservados.

Comandos executados na raiz, PowerShell, com Python do projeto:

```powershell
git status --short
git diff bb457ef --stat
$env:PYTHONPATH=(Get-Location).Path
.\.venv\Scripts\python.exe -m pytest tests/unit/test_rule_based_interpreter.py tests/unit/test_spans.py tests/unit/test_analysis_regions.py tests/unit/test_topology_path_compliance.py tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py tests/server/test_review_api.py tests/server/test_deliverable_exports.py tests/e2e/test_span_compliance_ui.py tests/unit/test_e08_association.py tests/unit/test_benchmark_network_pdf.py --basetemp=tmp/e08/required-accepted -p no:cacheprovider -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_benchmark_network_pdf.py tests/unit/test_e08_association.py --basetemp=tmp/e08/final-export -p no:cacheprovider -q
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe scripts/complexity_gate.py src
# Executar isoladamente; o monitor usa Start-Process -WindowStyle Hidden.
& ./tmp/e08/monitor_benchmark.ps1
# Comando invocado pelo monitor:
# .\.venv\Scripts\python.exe -m scripts.benchmark_network_pdf "examples/PROJETO DE REDE 1256148225.pdf" --output tmp/e08/benchmark-final.json --runtime-directory tmp/e01/runtime
.\.venv\Scripts\python.exe tmp/e08/audit_semantic.py tmp/e07-complete/benchmark-final.json
.\.venv\Scripts\python.exe tmp/e08/audit_semantic.py tmp/e08/benchmark-final.json
.\.venv\Scripts\python.exe -m pytest tmp/e01/test_inventory_local.py --basetemp=tmp/e08/reference -p no:cacheprovider -q
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe tmp/e08/visual_navigation.py
$env:PYTEST_ADDOPTS='-o cache_dir=tmp/e08/gate-cache'
.\IniciarTestes.bat *> tmp/e08/gate-final.log
git diff --check
git status --short
```

O gate usa sua raiz temporária curta em `C:\tmp` e precisou execução elevada à
restrição do workspace, autorizada pela revisão automática. Não houve rejeição de
aprovação nem dependência de SQL operacional. Scripts/dados privados e relatórios
de cobertura não devem ser adicionados ao Git. Nenhum commit ou publicação.
