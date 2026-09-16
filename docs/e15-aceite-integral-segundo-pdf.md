# E15 — Aceite integral do segundo PDF

Auditoria iniciada em 16/09/2026 sobre `d6b206b`, Git limpo. Nenhum `AGENTS.md`
aplicável encontrado nos ancestrais ou nas pastas do repositório. E11, E12,
E12A, E12B, E13 e E14 conferidas como concluídas em índice/detalhe e no código:
extrator 1.17.0, interpretador 25.0, API/piso 1.6.0. E08/E09 permanecem bloqueadas.
O diagnóstico original 1.14.0/22.0 é histórico, não a versão auditada.

**O aceite integral está reprovado por qualidade.** As metas congeladas de E10
continuam obrigatórias. As 29 ocorrências corretas nas propostas e o êxito de
execução não demonstram leitura integral, classificação completa ou automação.
Integração e reservas foram executadas separadamente do benchmark; seus resultados
e limites estão abaixo. E15 passou de #em-andamento para #bloqueada no índice/detalhe.

## Fonte e cadeia de evidências

PDF privado local de 988.018 bytes, uma página 595 × 842 pontos, SHA-256
`0793c292df9722ff48df31ab052018d4233ad3541706f50f53e994cc1670af06`.
As três execuções isoladas conferiram hash, tamanho e mtime antes/depois.
Nenhuma consulta SQL operacional, envio do PDF, commit, release ou publicação.
Bases, snapshots, transcrições, capturas e planilhas ficam ignorados em
`tmp/rede-1256407599/e15/`; a fonte e o inventário E10 não foram alterados.

Foram lidos roadmap, diagnóstico, handoffs E10/E11/E12/E12A/E12B/E13/E14,
README, política de exemplos, pipeline, projeções e testes. A inspeção das
bandas `upper`, `middle` e `lower`, com e sem anotações, cobre a folha inteira.
Os detalhes P3/P4 e P1/P5 conferem códigos, situações, cópia ampliada e conflitos.
Quadros CHI/regulador, cinco notas, fotos, assinaturas, vazios, rodapé e controles
da cerca continuam no inventário, sem autenticação de imagem/assinatura.

`audit.json` conserva **139 linhas**, primeira perda, propostas/evidências,
referências de DTO/células e pareamento reverso das 43 propostas. `topology.json`
faz a verificação estrita separada dos endpoints, nomes, medidas e continuidade.
`methods.json` conserva a comparação e ablações pós-inferência. A referência
nunca entra no algoritmo de produção. Correspondência por proximidade localiza
candidatos; somente literal/valor e contexto corretos contam como acerto.

## D01–D06 e estratos completos

| Estrato | Resultado e limite |
|---|---|
| D01 / R01 | Base `ABCN-35(70)` e revisão `ABCN-16(16)` preservadas, vigência pendente e zero confirmação conflitante. O catálogo revisado continua não resolvido. |
| D02 | Um neutro em V2-3, distinto da fase; sem duplicação do ativo. |
| D03 | Poste/MT/BT/chave do ponto existente têm contexto próprio; não herdam P5. Modelo de poste continua pendente. |
| D04 / R02 | Base N4 e alternativas instalar/remover conservadas; cópia ampliada não vira outro ativo. Decisão de autoridade permanece pendente. |
| D05 | `TR-3-45` literal e capacidade/fases observadas presentes; não há modelo arbitrário confirmado. Q3 continua com associação pendente. |
| D06 | 10 trechos físicos, nove pontos, sete pares visíveis exatos, três continuidades e seis medidas corretas. 36/83 m em Vãos; 14 m visível no trecho físico revisável. |
| Medidas ausentes | Quatro comprimentos desconhecidos; três ângulos e duas alturas não viram comprimento. Esses cinco campos ainda não têm projeção individual. |
| Equipamentos/símbolos | Três literais recuperados; seis propostas simbólicas. Os oito grupos de símbolos da referência permanecem sujeitos à convenção técnica, sem inferir quantidade pela contagem de círculos. |
| Código cortado | Preserva prefixo/evidência e continuidade, sem completar o cabo por catálogo. |
| Negativos | Cerca e sua coordenada não viram ativo. Leitura neural da coordenada da cerca permanece candidata auxiliar, não ponto confirmado. |

A comparação topológica reproduziu E14: zero trajetos físicos duplicados ou sem
correspondência. O grafo E12A sobre a saída atual conserva somente 1/7 pares
completos, 1/6 medidas com endpoints/nomes e 5/9 identidades físicas consistentes;
zero continuidades. Sua rejeição para integração permanece justificada por erros.
Tipo/modalidade dos dez trechos continuam desconhecidos com motivo explícito.

## Metas E10, com denominadores preservados

| Métrica | Medição atual | Meta / conclusão |
|---|---|---|
| Ocorrências do núcleo, código/qualificador/situação/contexto | 29 TP, 0 FN, 0 FP | 100%; atendida neste escopo |
| Poste / MT / BT / cabo | 6/6, 6/6, 6/6, 11/11 | Propostas; não confirmações completas |
| Confirmações automáticas | Oito cabos; zero erro conhecido de ocorrência entre oito | 0/8 não certifica classificação completa |
| Cobertura automática por campos | 8/29 = 27,59%; poste/MT/BT 0/6 cada, cabo 8/11 = 72,73% | Abaixo de ≥95% global e ≥90% por categoria |
| Cobertura automática integral comprovada | 0/29 | Classificação/tipo/modalidade não homologados |
| Revisão do núcleo | 21/29 = 72,41% | Reprova máximo 5%; omissões não contam como revisões realizadas |
| Revisão das propostas | 35/43 = 81,40% | Denominador distinto do núcleo |
| Observações auxiliares | 29 exigem conferência, zero confirmação | Não são 29 objetos nem decisões executadas |
| Revisões técnicas | Dois grupos visíveis, cinco alternativas preservadas, zero promoção conflitante | Autoridade pendente explícita |
| Leitura exata do documento | 0/1 | Reprovada; não generalizar a outros projetos |

O comparador histórico E12B registra cobertura integral zero como limite de seu
escopo, não como medição independente. Aqui a não homologação é também sustentada
pela auditoria documental e pelos tipos/modelos não resolvidos. Não se atribui
precisão integral de 100% às oito confirmações só porque não há duplicata conhecida.

## Documentação: 64 itens, sem exclusões

Resultado por item: **16 corretos na projeção**, **11 duplicados** (oito desses
também contêm valores errados), **36 sem representação individual** e **um como
leitura auxiliar revisável**, sem campo documental/decisão equivalente. Ter uma
alternativa correta ao lado de outra errada marcada `IDENTIFICADO` não é aceite.

- Corretos: data, cidade, dispositivo, levantamento, projetista, telefone do
  rodapé, formato, escala, NS; dois proprietários, duas faixas e um início de
  servidão; coordenadas P2/P5 em Resultados. A4 físico e A3 literal permanecem distintos.
- Duplicados: impacto, circuito, bairro, cliente, serviço, coordenada do rodapé,
  folha, aprovação vazia e três campos de coordenadas da servidão. Há truncamento,
  fragmentação, dígitos errados e variantes com/sem acento. A menção à servidão
  não substitui a consulta fake de ações nem aprova a fonte revisada.
- Sem campo individual: identificador de equipamento e designação de suporte,
  slogan/norte, município anotado, QR/logo, três assinaturas, carimbo de revisão,
  CHI/dispositivo/cinco recursos vazios, duas fotos, serviço/cliente/telefone/disjuntor
  junto à entrega, duas linhas do regulador, cinco notas, placeholder/concessionária
  e coordenadas P1/P3/U1. Os IDs completos permanecem em `audit.json`.
- Complemento neural: coordenada da entrega como literal integral, geometria e
  camada em Leituras auxiliares. Não equivale a confirmação do campo ou de padrão.

O controle de assinatura informa que não encontrou campo/rótulo, embora haja três
assinaturas visíveis em aparências. Não é prova de ausência nem de autenticidade.
O sistema não representa individualmente todos os campos CHI/regulador/fotos/notas
ou seus vazios; o benchmark não pode preencher essa lacuna com sua inspeção humana.
E11 compara conflitos de cabos/estruturas, sem política geral de vigência documental.
Por isso a limitação documental exige E15A antes de nova tentativa de aceite.

## Correção limitada de integração

`deliverable_exports.py` acrescenta ao fim de Elementos **Token de estrutura
observado** e **Qualificador de estrutura**, usando os atributos já existentes
no DTO. Preserva Código observado, posições das colunas anteriores e identidades;
não expande `(2)` em duas estruturas nem altera o catálogo. Campos ausentes ficam
vazios. `review_api.py` usa o token literal no rótulo de MT/BT, que chega à árvore
de Resultados e aos realces sem novo parser no cliente. Três regressões sintéticas
em `test_review_api.py` conferem rótulo HTTP/overlay e leitura do XLSX gravado para
qualificadores 1/2 e ausência de atributo. `test_benchmark_network_pdf.py` deixa de
confundir a terceira aba, Trechos físicos de E14, com Documentação; verifica ambas.

Nenhum algoritmo de inferência, contrato HTTP, versão semântica, cache, migração
ou snapshot persistido mudou. O trabalho documental/classificação foi subdividido
em **E15A/E15B antes de ampliar implementação**, conforme o pedido. As perdas novas
nas reservas motivaram **E15C/E15D/E15E**, também sem ampliar inferência. As correções
de integração não resolvem as metas de automação ou as perdas documentais.

## Benchmark isolado e ablações

Python 3.12.14, PyMuPDF 1.28.0, Tesseract local `por+eng`, controle OCR funcional.
Modelos neurais opcionais do runtime E12A, sem instalação/download nesta execução.
Cada variante usou SQLite novo e fonte íntegra. As três rodaram sequencialmente,
sem testes, outro Python ou rasterização concorrente. Tempos são observabilidade;
não houve teto global, redução de cobertura ou escolha por velocidade.

| Composição | Propostas / confirmações / Vãos | Diagnósticos | Total até projeção / incluindo XLSX |
|---|---|---:|---|
| Vertical atual | 43 / 8 / 8 | 0 | 151,394 / 154,408 s |
| Vertical + neural auxiliar | 43 / 8 / 8 | 0 | 209,635 / 212,226 s |
| Nativo + neural auxiliar sem Tesseract | 0 / 0 / 0 | 0 | 78,408 / 80,909 s |

Vertical e combinação têm pareamento operacional idêntico, 29/0/0; a ablação sem
Tesseract omite 29/29, sem transformar ausência de confirmação em precisão 100%.
O neural mantém um ganho novo de literal completo na entrega; pares de coordenadas
completos passam de 4/11 para 6/11. As 328 observações brutas e 29 selecionadas
preservam erros/repetições. Desligar o neural retira esse complemento; desligar
Tesseract perde a leitura operacional. Nenhum acordo promove valor automaticamente.

Baselines históricos auditáveis permanecem E10 24 TP/5 FN/4 FP, dois erros conhecidos
em dez confirmações; vertical E12 24/5/4, um erro em nove. E13/E14 corrigem o núcleo
para 29/0/0. A comparação de generalização usa as reservas e revisões congeladas
separadamente; repetir este PDF conhecido não constitui avaliação cega.

## Casos reservados E10

Nove sementes das três famílias congeladas foram geradas após o congelamento dos
métodos: H01 910101–910103, H02 910201–910203 e H03 910301–910303. Manifesto, fonte,
hash e referência em `reserved-manifest.json`; 45 inferências, todas com saída zero
e fonte íntegra, em `reserved/`. Original usa arquivo de `c85bebe`, vertical usa
`172afd5`, final usa `d6b206b` mais as correções de apresentação desta sessão.
As mudanças desta sessão não alteraram inferência. Esses casos agora estão expostos;
uma nova rodada de ajuste exige reservas novas. Os candidatos documentais reais
1250832231/1256347479 não foram usados: ausência de referência no histórico pesquisado
não prova ausência de exposição anterior. A generalização medida é sintética.

H01 combina três páginas, uma rasterizada, rotações 0/90/180 e escalas 0,5/1/2;
H02 cruza dois circuitos, usa duas revisões, cópia e variantes preta/verde/vermelha;
H03 contém tabela, cerca, carimbo, foto, altura/ângulo e linha saindo da folha.
As folhas foram inspecionadas em `reserved-contact.png` e `reserved-multipage.png`.
A primeira pontuação de H01 usava coordenadas antes da rotação. O avaliador foi
corrigido para o espaço da página renderizada; originais ficaram no manifesto.
Nenhuma fonte, método ou denominador mudou. A conclusão de perda de 18/27 persiste.

| Método | H01 TP / FN / FP, em 27 | H02 grupos / 6; confirmações conflitantes | H03 FP; confirmados errados / confirmados |
|---|---|---|---|
| Original | 9 / 18 / 0 | 0 / 6; 6 | 3; 3 / 3 |
| Vertical E12 | 9 / 18 / 0 | 6 / 6; 0 | 3; 3 / 3 |
| Final vertical | 9 / 18 / 0 | 6 / 6; 0 | 6; 3 / 3 |
| Final + neural auxiliar | 9 / 18 / 0 | 6 / 6; 0 | 6; 3 / 3 |
| Sem Tesseract, nativo + neural auxiliar | 9 / 18 / 0 | 6 / 6; 0 | 6; 3 / 3 |

H01: nove propostas exigem revisão e 18 ocorrências estão omitidas; não contar
omissões como revisão realizada. Zero confirmação tem precisão indefinida.
H02: original tem 15 propostas, seis bases confirmadas sem resolver a revisão e
nove em revisão; métodos posteriores têm seis propostas, todas em revisão.
Essa é uma auditoria de autoridade/grupos, não um denominador de recall de códigos.
H03: original/vertical não deixam propostas em revisão; final/combinado deixam
três em revisão, além dos três cabos indevidamente confirmados sobre linhas de
tabela. O aumento de FP inclui três transformadores propostos, sem confirmação.
Logo o ganho no PDF principal não demonstra melhora global nem zero erro automático.

`reserved-topology.json` pontua H02 por geometria, nomes e medida conjuntamente.
Final/combinado têm zero TP/6 FN/3 FP: um trecho P3–P2 por caso reúne os dois cabos.
O grafo independente sobre cada composição conserva 6/6 pares geométricos nomeados,
sem junção fictícia no cruzamento, mas zero par com medida correta (0 TP/6 FN/6 FP
nesse critério conjunto). As versões antigas não ofereciam DTO de trecho físico;
ausência dessa projeção não mede isoladamente toda a capacidade topológica antiga.
Não integrar o grafo só por seu acerto geométrico parcial.

Também foi repetida a alternativa neural E12A através de `interpret_rapid`, com
as leituras reais armazenadas e sem nova execução OCR: nove interpretações, sem
diagnósticos. H01 9/18/0, H02 seis grupos pendentes, H03 12 propostas negativas.
É saída experimental sem promoção/persistência; zero confirmação é imposto pelo
experimento, não acerto automático. Não há ganho operacional demonstrado que
justifique substituir o pipeline. Ablações final/combinado não mostram ganho
no núcleo reservado; o ganho documental do neural limita-se ao PDF principal.

`reserved-rejection.json` completa o cenário de rejeição anterior: três projetos
HTTP novos, OCR real, uma rejeição persistida por caso H02, seguida de análise
com cache, forçada e reabertura. **3/3 preservadas**, nenhuma reativação automática;
três consultas de mercado fake e zero conexão operacional. O grafo não recebe
autoridade de promover nem substituir decisões humanas.

Tempos das reservas ocorreram com gate/integração concorrentes: não são benchmark
isolado nem base de ranking. As três medições isoladas da seção anterior permanecem
separadas. Pico de memória não foi novamente medido em E15; medições E10 são históricas.

## Integração real e inspeção

`http_acceptance.py` usa Uvicorn em loopback, cliente HTTP autenticado, gateways
reais, viewer e painéis Qt. Tesseract/neurais são reais; serviços de mercado/ações
são fake, e `pyodbc.connect` foi substituído por falha obrigatória. O PDF foi
enviado apenas ao servidor local. Foram conferidos:

- 43 propostas, oito Vãos, dez trechos físicos e 29 leituras auxiliares;
- navegação dos dez trechos e 12 combinações de zoom/rotação (0,5/1/2 × 0/90/180/270);
- planilhas de resultados (43/8/10/29 linhas nas abas correspondentes), documentação
  (39 linhas) e conformidade (nove achados, 42 regras, 12 fatos de contexto);
- análise inicial/cache/forçada concluídas; cancelamento em execução sem publicar
  resultado parcial e sem perder a sessão anterior; IDs preservados e reabertura exata;
- documentação Qt igual ao DTO, incluindo duplicatas/erros visíveis; isso valida
  transporte/apresentação, não a correção dos campos;
- conferência final dos tokens em árvore Qt, rótulos HTTP/realces e XLSX salvo;
  consulta fake de ações para serviço 0007 e servidão, registrada em `final-projection.json`.

Capturas `http-ui-physical.png`, `http-ui-documentation.png`, `http-ui-gmax.png` e
`ui-final-qualifiers.png` foram inspecionadas. A captura inicial GMAX ainda mostrava
a consulta assíncrona em andamento; a conclusão da consulta fake foi verificada
posteriormente no DTO final, sem reivindicar captura visual de seu estado final.
Os scripts de inspeção tiveram ajustes de API/fixture (httpx2, parâmetros do viewer,
árvore em vez de tabela de apoio, nome review_state e NS sintética de dez dígitos);
as tentativas interrompidas não foram contadas como aprovações. Artefatos finais:
`http-report.json`, `final-projection.json`, `reserved-rejection.json`, todos passed=true.

## Comandos e validações

Todos executados na raiz. `python` nos testes é `.venv/Scripts/python.exe`; o
runtime neural é `tmp/e12a-runtime/Scripts/python.exe`, com `src`, raiz do checkout
e `.venv/Lib/site-packages` no `PYTHONPATH`. Os scripts privados não são gate CI.

```powershell
.venv/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e15/vertical.json --runtime-directory tmp/e01/runtime --telemetry
tmp/e12a-runtime/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e15/combined.json --runtime-directory tmp/e01/runtime --telemetry --complementary-ocr
tmp/e12a-runtime/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e15/neural.json --runtime-directory tmp/e01/runtime --telemetry --native-only --complementary-ocr
.venv/Scripts/python.exe tmp/rede-1256407599/e15/audit.py
.venv/Scripts/python.exe -m scripts.experiments.topology_audit --baseline tmp/rede-1256407599/e13/benchmark-final.json --current tmp/rede-1256407599/e15/combined.json --reference tmp/rede-1256407599/e10/inventory.json --output tmp/rede-1256407599/e15/topology.json
.venv/Scripts/python.exe -m scripts.benchmark_method_reconciliation --reference tmp/rede-1256407599/e10/inventory.json --vertical tmp/rede-1256407599/e15/vertical.json --combined tmp/rede-1256407599/e15/combined.json --neural-only tmp/rede-1256407599/e15/neural.json --output tmp/rede-1256407599/e15/methods.json
tmp/e12a-runtime/Scripts/python.exe tmp/rede-1256407599/e15/http_acceptance.py
.venv/Scripts/python.exe tmp/rede-1256407599/e15/reserved.py generate
tmp/e12a-runtime/Scripts/python.exe tmp/rede-1256407599/e15/reserved.py run
.venv/Scripts/python.exe tmp/rede-1256407599/e15/reserved_neural_substitution.py
.venv/Scripts/python.exe tmp/rede-1256407599/e15/reserved.py score
.venv/Scripts/python.exe tmp/rede-1256407599/e15/reserved_topology.py
tmp/e12a-runtime/Scripts/python.exe tmp/rede-1256407599/e15/reserved_rejection.py
.venv/Scripts/python.exe tmp/rede-1256407599/e15/final_projection.py
.venv/Scripts/python.exe -m pytest tests/server/test_review_api.py tests/server/test_deliverable_exports.py tests/integration/test_review_panel.py -q -p no:cacheprovider --basetemp tmp/e15-projection-final
.venv/Scripts/python.exe scripts/smoke_examples.py tmp/rede-1256407599/e15/smoke-known
.\IniciarTestes.bat
```

Testes localizados antes da execução: pipeline/revisão em
`tests/integration/test_interpretation_pipeline.py` e `test_human_review.py`;
Projeto/GMAX em `test_project_market_http.py`, `test_gmax_panel.py`;
Resultados/documentação em `test_review_panel.py`, `tests/e2e/test_mvp_ui.py`;
Vãos em `test_span_compliance_ui.py`; realces/zoom/rotação em
`test_review_highlights.py`; reabertura/reconexão em `test_client_reconnection.py`;
jobs/cancelamento em `tests/server/test_jobs_api.py`; exportações em
`test_deliverable_exports.py`. Todos fazem parte do gate público.

A primeira tentativa do gate teve 833 aprovações e 532 erros de preparação por
`PermissionError` em `C:\tmp\zph-basic-27087`, cobertura 52,65%, saída 1; **reprovada**.
Ruff também detectou formatação/imports, corrigidos. O comando canônico foi repetido
com a permissão da pasta temporária, sem alterar seu escopo ou o piso 85,01%.
O teste novo inicialmente comparava célula vazia com `None`; corrigida a fixture
para conferir código-base, token e ausência explicitamente. Esse resultado inicial
(27 aprovados/3 falhos) não constitui aceite.

A segunda execução completa, iniciada antes da correção dessa fixture, terminou
com 1361 aprovados/quatro falhos, 87,77% e saída 1 (`gate-final.log`): três casos da
fixture antiga e a expectativa desatualizada da terceira aba no benchmark de E14.
Não foi aprovada nem teve falhas excluídas. Após as correções, a validação focada
passou com **60 testes em 42,31 s** (`projection-final.log`).

**Gate completo final: saída 0, 1365 testes aprovados em 539,48 s, cobertura 87,92%**,
acima de 85,01%. Dependências, Ruff, formatação (376 arquivos), Mypy (351 arquivos),
fronteira do cliente e complexidade (2856 funções/métodos, nenhum E/F) aprovados.
Registro integral em `gate-complete.log` e `relatorio-testes.txt`. Nenhum teste foi
pulado para obter aprovação e nenhum piso foi reduzido. A duração não é gate.

Smoke complementar: saída 0, um PDF conhecido, zero diagnósticos. Executado sobre
cópia byte a byte do segundo PDF em `smoke-known/`, para não expor os candidatos
reais à reserva. O modo nativo retorna zero propostas; isso comprova execução,
não leitura OCR. Auditoria final repete 139/64 itens e confirma os seis tokens MT
no XLSX do benchmark e 15 tokens MT/BT na projeção HTTP/Qt/XLSX final.

## Bloqueio e retomada

**Causa:** perdas documentais, classificação/promoção insuficiente e falhas de
identidade/contexto/topologia em famílias reservadas.
**Evidência:** 139 itens preservados em `audit.json`, 36 documentais sem campo,
11 duplicados, oito com valor errado e cobertura automática limitada a 8/29;
H01 perde 18/27, H03 confirma três falsos ativos, H02 erra seis pares completos.
**Impacto:** leitura exata 0/1 e metas de revisão/cobertura/erro E10 reprovadas,
apesar do gate público e da integração aprovados. São bloqueios de qualidade
reproduzidos, não falta de acesso ao PDF nem uma dependência histórica pendente.
**Ação:** executar E15A–E15E com seus critérios, preservar reservas expostas como
regressões, congelar nova composição e medir reservas novas antes de repetir E15.
Se a fonte não sustentar modelo/modalidade/autoridade necessários às metas,
documentar o impedimento com evidência e necessidade técnica, sem inventar valores.
Nenhuma pendência técnica foi resolvida por inferência de autoridade ou rebaixamento
do inventário. E08/E09 e os PDFs privados permanecem preservados.
`final-verification.json` confirma hash/tamanho/mtime originais, 139 itens, dependências
concluídas e texto integral das seções E08/E09 idêntico ao HEAD. `git diff --check`
passou; Git mantém somente os oito arquivos públicos desta entrega alterados/novo,
com fonte, planilhas e auditorias privadas ignoradas. HEAD permanece `d6b206b`.
