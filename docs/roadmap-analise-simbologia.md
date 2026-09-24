# Zeny Project Handler — Roadmap de análise de simbologia

Criado em 18/09/2026; revisado para execução com subagentes e V-P em 18/09/2026. Base inspecionada: `bfb47f7`, com alterações locais preexistentes.
Planejamento original preservado. A execução de E01 começou em 18/09/2026 sobre `5ee65d3`,
com Git limpo; estados, validações e entregas efetivas constam no handoff da etapa.

## Objetivo e uso

Ampliar a identificação de **toda a simbologia dos projetos de rede**, começando por
transformadores, para-raios MT/BT, aterramento e estais, sem limitar o mecanismo a essas
classes. Melhorar os algoritmos existentes e acrescentar famílias independentes, capazes
de encontrar ocorrências que outras não encontram. Cada achado deve chegar à revisão com
localização, procedência, alternativas e explicação da decisão.

**Regra central: unir candidatos e validar evidências, sem exigir unanimidade, maioria ou
um mínimo de dois detectores.** Um achado exclusivo pode ser correto e até elegível para
confirmação quando cumprir a política calibrada de seu método/classe e os requisitos
semânticos. A ausência de detecção por outro motor não é um voto contrário.

Executar uma etapa por sessão limpa na raiz do projeto, usando seu prompt. Conferir o
código atual, atualizar índice e detalhe, registrar evidências e encerrar com handoff.
Os IDs E01–E16 pertencem exclusivamente a este roadmap, não às etapas homônimas dos
handoffs históricos. Dependência pendente não significa bloqueio. Caso uma família
exija mais de uma sessão, decompor a etapa antes de iniciá-la em IDs sufixados estáveis,
com critérios próprios e ajuste das dependências; não ocultar trabalho restante.

**Decisão de 23/09/2026 — trilhas independentes.** O usuário aceitou que um
desenho visualmente indistinguível de vários IDs seja apresentado como **uma
ocorrência com alternativas**, sem escolher um ID exato por adivinhação. Este
contrato ainda requer implementação e teste nas etapas pertinentes; não
transforma automaticamente as 344 variantes `pending` de E07 em reconhecidas.
O [fluxo de curadoria incremental](fluxo-curadoria-incremental-simbologia.md)
trata PDFs novos de `examples/` em rodadas one-shot independentes, com seu
próprio prompt e etapas C01–C04. E08–E16 podem avançar usando o snapshot
verificado disponível, mesmo com E07 `#bloqueada` pelo critério histórico
de reconhecimento completo. Cada etapa continua obrigada aos próprios gates;
E16 publicará a cobertura real e as lacunas, sem alegar reconhecimento universal.
Adicionar PDF não treina automaticamente um modelo nem altera o produto até
que um pacote/teste revisado seja versionado.

### Handoff da remodelagem do plano — 23/09/2026

Esta edição é documental; nenhuma etapa E08–E16 foi iniciada e nenhum PDF foi
revalidado por ela. O ponto de partida é o checkpoint E07 documentado adiante:
21 variantes habilitadas e 344 pendentes; o aceite histórico segue `#bloqueada`.
A decisão do usuário sobre figuras indistinguíveis virou contrato planejado de
uma ocorrência com alternativas, a implementar e testar em E12–E14. E07 saiu
das dependências de E11/E12, sem lhes conceder aceite automático. E16 medirá o
inventário na versão congelada e publicará as lacunas; não homologará variantes
pendentes. A curadoria futura tem C01–C04 e prompt one-shot independentes.

Arquivos da decisão: este roadmap,
[`fluxo-curadoria-incremental-simbologia.md`](fluxo-curadoria-incremental-simbologia.md),
`examples/README.md` e ADRs 0013/0015. Foram excluídos quatro handoffs órfãos
de roadmaps removidos: `docs/e01-diagnostico-leitura-rede.md`,
`docs/diagnostico-rede-1256407599.md`, `docs/e06-marca-texto-situacao.md` e
`docs/e09-homologacao-integrada.md`; não havia referências ativas a seus
caminhos. E08 pode iniciar por suas dependências e gates próprios; uma rodada
C01–C04 pode ocorrer antes ou depois.

Validação desta edição: `git diff --check` saiu com código 0; conferência
estrutural encontrou 16 estados no índice e 16 detalhes correspondentes,
quatro etapas C01–C04 e o prompt one-shot; `rg` não encontrou referências
ativas aos quatro arquivos excluídos. Suítes de código e V-P não foram
executados, pois esta edição altera somente documentação e não implementa
os contratos propostos. Cada etapa futura permanece responsável por eles.

## Contexto confirmado

| Área | Evidência no repositório | Consequência para o plano |
|---|---|---|
| Stack | `pyproject.toml`: Python 3.11–3.13; PyMuPDF, Pillow, SQLAlchemy/Alembic, FastAPI e cliente PySide6 | Processamento no servidor; cliente consome DTOs/rasters. |
| Extração atual | `src/zeny_project_handler/adapters/analysis/pymupdf_analyzer.py`, versão **1.18.0**; interpretador `adapters/interpretation/rule_based.py`, **25.0** | Os documentos que citam 1.17.0 são históricos; confirmar novamente ao executar. |
| Detector dedicado | `adapters/analysis/pymupdf_symbols.py`: `_extract_symbolic_equipment`, três classes, primitives por drawing, limite de 60 pontos, score fixo 0,88 | Aterramento e para-raios MT/BT têm detecção geométrica; o score não é probabilidade demonstrada. |
| Limitações concretas | Nesse módulo, aterramento/MT se separam pelo número de barras; preto/vermelho/verde definem situação; deduplicação usa classe, situação, primitives/proximidade | Escala, agrupamento, ruído, símbolos próximos, cópias e cor exigem controles explícitos. |
| Integração | `ports/analysis.py`, `application/document_analysis.py`, `application/interpretation_pipeline.py` | Reusar evidências e persistência, com contrato de simbologia aditivo. |
| Interpretação | `adapters/interpretation/category_analyzers.py`: transformadores por literal/catálogo; reconhece atributos simbólicos | Ler `TR-3-45` não comprova detectar o desenho de transformador. |
| Domínio/catálogo | `domain/enums.py`: cinco categorias; `adapters/catalog/data/catalogo_cemig_v2.json`: classes chave faca, fusível, fusível repetidora e transformador | Símbolo, classe semântica e item de catálogo são entidades distintas. Não forçar estai em cabo nem inventar modelo catalogado. |
| Reconciliação atual | `application/method_reconciliation.py`: `documentary-coordinate-review-1`; `docs/e12b-reconciliacao-metodos.md` | Solução atual é documental; não reaproveitar seus filtros de coordenadas como fusão de símbolos. |
| Alternativas existentes | `rapid_evidence.py`, `rapid_ocr.py`, `scripts/experiments/`, `requirements-experiments.lock` e handoff E12A | OCR neural é leitor auxiliar, não detector de símbolos; grafo experimental não foi homologado como substituto operacional. |
| Regressões conhecidas | `tests/unit/test_pymupdf_analyzer.py`, `test_rule_based_interpreter.py`, `test_topology_compliance.py`; `docs/validacao-e08-e09-0.4.0.md` | Preservar negativos de glifos/molduras e símbolos com barras preenchidas. |
| Aceite histórico | `docs/e15-aceite-integral-segundo-pdf.md` | Êxito do núcleo textual não certifica equipamentos, quantidade de símbolos ou leitura integral. Este roadmap não encerra aquele aceite. |
| Exemplos | `examples/README.md`, ADR 0005 e `docs/fluxo-curadoria-incremental-simbologia.md` | PDFs reais são opcionais, locais e ignorados; gate padrão deve funcionar sem eles. Curadoria contínua é independente deste roadmap e só persiste em dados/testes revisados. |

Os caminhos abreviados acima são relativos a `src/zeny_project_handler/`, salvo os que
já começam por `src/`, `docs/`, `scripts/` ou `tests/`. Não foi encontrado `AGENTS.md`
aplicável nos ancestrais e áreas inspecionadas, nem roadmap existente para este escopo.
`docs/` já abriga os handoffs relacionados; por isso este arquivo segue nesse diretório.
A pesquisa ampla encontrou acesso negado a `.pytest_cache`; cache de testes não foi usado
como fonte de instruções ou evidência. Os arquivos de código e documentação citados foram lidos.

Git inicialmente modificado: `Dockerfile`, `README.md`, os três `pyproject.toml`,
`docs/especificacao-funcional.md`, `scripts/build_client.py`, os `__init__.py` de core e
cliente, `src/zeny_project_handler_server/composition.py`,
`tests/integration/test_package_import.py` e `tests/unit/test_release_build.py`.
Preservar essas alterações; este planejamento adiciona apenas o roadmap versionável.

## Escopo e limites

- Cobrir símbolos de equipamentos, suportes, estais/ancoragens, aterramentos, proteção,
  manobra, regulação, medição, iluminação, conexões, estruturas e convenções gráficas de
  linhas/continuidade; também reconhecer a função informativa de símbolos cartográficos.
- Representar símbolos compostos, subtipos, orientação, situação, camada/revisão e
  cardinalidade desconhecida. A presença de três círculos não significa três ativos.
- Aceitar PDFs vetoriais, rasterizados e mistos, com degradação, escala, rotação, espessura,
  sobreposição, tons de cinza e variações de concessionária/legenda.
- Catálogo extensível e versionado de famílias/variantes; desconhecidos permanecem
  candidatos revisáveis. “Toda a simbologia” significa cobertura rastreável do inventário
  E01 e um caminho de expansão, não garantia de reconhecer qualquer convenção futura.
- Fora de escopo: editar PDFs de origem; dimensionar redes; criar normas por analogia;
  reescrever toda a topologia; corrigir todo OCR documental; encerrar os aceites históricos;
  publicar release, fazer deploy ou enviar PDFs privados a serviços externos.

## Invariantes e desenho proposto

Fluxo: **fontes imutáveis → observações independentes → união rastreável → associação de
hipóteses da mesma ocorrência → validação cruzada → proposta/revisão → promoção controlada**.
As interfaces abaixo são propostas, ainda não APIs existentes.

1. Cada método declara família algorítmica, versão, fontes compartilhadas, domínio de
   aplicação, classes suportadas, cobertura espacial/camada e estado de execução.
   Diferentes DPI/thresholds do mesmo motor são variantes correlacionadas, não novos votos.
2. Cada observação preserva hash da fonte, documento/página/camada, geometria original e
   normalizada, transformação inversa, primitives ou hash do raster, template/modelo,
   score bruto, classe/subtipo alternativos, situação e motivo de abstenção.
3. União não funde observações destrutivamente. Agrupar exige compatibilidade de identidade,
   geometria e contexto. IoU/proximidade sozinhos não unem símbolos vizinhos, páginas ou
   componentes de um conjunto. Preservar caixas originais mesmo quando houver caixa agregada.
4. Comparar todos os métodos aplicáveis através do reconciliador: apoio, complemento,
   contradição positiva, abstenção, fora de domínio, não detecção e falha são estados diferentes.
   Não exigir que cada par execute validação bilateral, nem deixar algoritmos aprovarem uns
   aos outros recursivamente. Rechecagens são limitadas e têm cadeia de procedência.
5. Scores de motores diferentes não são comparáveis sem calibração. Não multiplicar
   probabilidades como se as fontes fossem independentes, somar votos correlacionados ou
   zerar confiança pela falta de apoio. Concordância pode reforçar evidência, sem prová-la.
6. Classificação visual, identidade física, situação, quantidade, associação e catálogo
   têm decisões separadas. Cor cinza/preta não impõe “existente” quando a convenção é
   desconhecida. Classe inequívoca pode coexistir com situação/quantidade pendentes.
   Se a mesma forma sustentar vários IDs, preservar uma ocorrência com alternativas
   e a evidência contextual de cada opção; sem discriminante, não escolher ID nem
   contar o conjunto como múltiplos ativos ou como classe exata reconhecida.
7. Contexto elétrico é verificador e priorizador, nunca gerador de um símbolo inexistente.
   A regra “deveria haver aterramento” não prova presença. Não detecção também não prova
   ausência física; informar cobertura/avaliabilidade aos provedores de conformidade.
8. Fonte normativa e legenda local têm proveniência e escopo. Conflito não é resolvido
   silenciosamente por votação. IEC/concessionária estrangeira não define norma CEMIG.
9. Falhas/cancelamentos preservam evidências, mas não viram sucesso integral/cache completo.
   Modo degradado deve ter composição explícita e assinatura própria. Novos motores ficam
   isolados até o gate; nenhuma dependência neural ou análise vai para o cliente.
10. Preservar decisões humanas, idempotência, revisões técnicas e separação base/anotações.
    Não transferir decisão antiga a nova hipótese só por proximidade.

A integração também deve auditar o corte atual por `confianca_minima` em
`category_analyzers.py`: scores brutos de novos métodos não podem entrar nesse corte
como se usassem a escala legada. E03 preserva o score original; E12 define calibração
e elegibilidade; E13 adapta o consumidor e testa um exclusivo válido com score bruto
numericamente menor que o de um método incorreto. Não inflar scores para contornar o corte.

### Política de união e validação cruzada

| Caso obrigatório | Tratamento esperado |
|---|---|
| Só A encontra um transformador | Preservar candidato; validar A/classe/contexto. B e C silenciosos não o vetam. |
| A e B encontram símbolos distintos, ambos válidos | União contém ambos; interseção vazia não apaga o resultado. |
| A e B encontram a mesma ocorrência | Uma hipótese física com duas observações preservadas. |
| A indica aterramento e B para-raios no mesmo suporte geométrico | Alternativas incompatíveis explícitas; revisão/abstenção conforme política. |
| Três variantes de A repetem um erro e B acerta | Três variantes não ganham por maioria; medir correlação e erro condicionado. |
| B não suporta estai ou falha | Não aplicável/falha, sem evidência negativa contra o estai de A. |
| A encontra o símbolo na legenda e B no desenho | Legenda é referência; só ocorrência operacional pode virar proposta de ativo. |
| Dois símbolos contíguos se sobrepõem nas caixas | Preservar identidades se primitives/máscaras/contexto indicarem dois objetos. |
| Símbolo e texto divergem em potência/situação | Preservar leituras e campos conflitantes; não inventar consenso. |

## Fontes externas consultadas e uso delimitado

Consulta em 18/09/2026; fontes primárias. Pesquisa dirigida textual, não auditoria visual
integral dos manuais. E01 deve conferir desenhos, revisão, localizadores e procedência
antes de produzir templates/regras. Nenhum PDF do usuário foi enviado à internet.

- **F01 — CEMIG ND-3.1, jul/2025**, página PDF 88, item 2.2: remete ao documento
  IT-EO-008 para simbologia. Serve para identificar a referência aplicável; não copiar
  automaticamente figuras de edições antigas.
  [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- **F02 — CEMIG IT-EO-008, Simbologia EO**, 45 páginas; quadro de revisão consultado
  indica revisão 3 de 29/07/2024. Índice localiza estai MT/AT nas páginas 15–16,
  transformador em 19–21, proteção em 27 e equipamento associado em 29. O restante
  do manual também entra no inventário, inclusive desenhos e símbolos não patrimoniais.
  Fonte para perfis CEMIG, sem presumir que o literal `SIMBOLOGIA.pdf` no código a identifica.
  [PDF oficial](https://www.cemig.com.br/wp-content/uploads/2025/10/IT-EO-008_Simbologia_EO.pdf)
  e [portal que o publica](https://www.cemig.com.br/normas-tecnicas/construcao-de-redes-de-distribuicao-por-particulares/).
- **F03 — IEC 60617**, referência internacional de símbolos de diagramas. A página
  oficial informa acesso à base por assinatura. Usar taxonomia/metadados e referências
  acessíveis; não pressupor acesso ou redistribuição dos desenhos. Ausência dessa base
  não impede implementar a fonte CEMIG disponível.
  [IEC TC3](https://tc3.iec.ch/tc-activity/graphical-symbols-for-diagrams/).
- **F04 — UK Power Networks**, guia de símbolos hospedado pelo governo britânico:
  candidato a controle de convenções estrangeiras e diferenças vetorial/escaneado.
  O PDF foi localizado, mas a conferência visual não foi concluída nesta pesquisa;
  não usar seus símbolos como templates validados antes de E01.
  [Documento](https://assets.publishing.service.gov.uk/media/66daf995e87ad2f121826583/UK_Power_Networks_4_checked.pdf).
- **F05 — OpenCV**, correlação de templates, Hough generalizado e comparação de
  contornos: bases técnicas para mecanismos raster/forma, não garantia de acerto em
  redes. Escala e rotação precisam ser tratadas e medidas explicitamente.
  [Template matching](https://docs.opencv.org/4.13.0/d4/dc6/tutorial_py_template_matching.html),
  [Generalized Hough](https://docs.opencv.org/4.12.0/d7/dd4/classcv_1_1GeneralizedHough.html),
  [Contornos](https://docs.opencv.org/4.13.0/d5/d45/tutorial_py_contours_more_functions.html).
- **F06 — Solovyev et al., Weighted Boxes Fusion**, alternativa experimental para
  localização de detecções compatíveis. WBF não resolve identidade, autoridade,
  cardinalidade nem calibração; comparar preservação de exclusivos antes de adotá-la.
  [Artigo original](https://arxiv.org/abs/1910.13302).
- **F07 — Torchvision, Faster R-CNN**, candidato concreto de arquitetura treinável
  para E11. Pesos genéricos não fornecem as classes técnicas deste projeto; treino,
  licença, dados, dependências e inferência local precisam de verificação própria.
  [Documentação oficial](https://docs.pytorch.org/vision/main/models/faster_rcnn.html).

## Hipóteses, decisões e riscos globais

| Questão | Decisão de planejamento / impacto / responsável |
|---|---|
| Cobertura infinita de símbolos | E01 congela famílias e variantes das fontes escolhidas, com versão e totalizadores; símbolos novos seguem como desconhecidos e expansão explícita no fluxo independente de curadoria. Nenhuma classe some do denominador por baixo desempenho. E08–E16 podem usar apenas pacotes habilitados, mantendo pendências visíveis. |
| Fonte local `SIMBOLOGIA.pdf` | Literal encontrado no código; conteúdo/revisão não comprovados. E01 resolve a correspondência ou marca perfil legado com procedência desconhecida. |
| Representação de estai e símbolos informativos | Preferir observação semântica separada de item patrimonial; E03 decide o contrato e E13 mapeia categorias sem converter estai em cabo. Mudança pública exige compatibilidade. |
| Capacidade de dados para treino | Ainda não medida. E11 entrega experimento reprodutível e decisão justificada; rejeitar o neural pode concluir o experimento, mas não a cobertura das famílias que faltarem. |
| Hardware e orçamento | Não presumir GPU. E02 registra ambiente e baseline; E15 fixa limites de memória/tiles com dados, sem teto arbitrário de duração global. |
| Metas numéricas | Metas propostas abaixo são decisões deste plano, não resultados medidos. E02 congela protocolo antes dos ajustes; insuficiência amostral é explícita. |
| Generalização | Sintéticos são gate permanente; todos os exemplos reais disponíveis exigem V-P; uso iterativo mede diagnóstico, não reserva independente. Sem avaliação real, resultado deve dizer “validado em sintéticos”, sem alegar homologação de campo. |
| Fontes externas | Registrar termos para qualquer asset/modelo redistribuído. Links/metadados e fixtures autorais evitam depender de um pacote externo indisponível. |

## Protocolo de medição e definição global de pronto

E02 implementa os critérios abaixo e congela dados/limiares antes de E04–E11:

- Particionar por documento/projeto e família de desenho/template, mantendo derivações,
  rotações e rasterizações do mesmo original na mesma partição. Separar desenvolvimento,
  calibração e reserva. Referências e ROIs de verdade-terreno nunca entram na inferência.
- Anotar por ocorrência: classe/variantes, caixa ou máscara/traçado, camada, situação,
  contexto operacional/legenda, associação, quantidade conhecida ou indeterminada e
  avaliabilidade. Ambíguos não têm rótulo inventado; aparecem em estrato separado.
- Pareamento um-a-um por página/camada e identidade. Reportar IoU e critério de forma/
  distância normalizada para símbolos finos; E02 fixa tolerâncias antes de avaliar.
- Medir TP/FP/FN, precisão/recall por classe, macro e micro, FP/página, localização,
  confusão, situação, quantidade, associação, duplicatas, revisão e cobertura automática.
  Mostrar contagens/denominadores; classe ausente não recebe recall 100%.
- Comparar baseline, cada método isolado, união bruta, união filtrada, interseção de
  controle e composição final; ablação retirando cada método. Mostrar acertos exclusivos
  `TP(A) − união(TP(outros))`, falsos positivos exclusivos, erros compartilhados e
  pares “A acertou/B falhou”. Interseção é controle, nunca requisito de produção.
- Medir calibração por classe/método/estrato, curvas precisão–recall e risco–cobertura,
  Brier/ECE quando houver probabilidade calibrada. Poucas amostras não autorizam promover
  o score bruto a probabilidade. Usar intervalos por documento; sintéticos correlacionados
  não contam como evidências independentes de confiabilidade de campo.
- Metas para a reserva sintética versionada: **recall de candidatos ≥95% e precisão final
  ≥95% em cada família avaliável**, com todos os estratos difíceis reportados; zero FP nos
  negativos críticos fixos (legenda/tabela/glifos/cerca), zero fusão entre páginas e zero
  promoção com conflito técnico não resolvido. Não reduzir a meta após ver a reserva.
- Para famílias já atendidas, não perder TP nem acrescentar FP nos controles fixos do
  baseline. Composição final deve preservar todos os exclusivos válidos dos controles e
  demonstrar ganho de recall sobre o baseline no conjunto expandido. Remover candidato
  exige motivo rastreável independente do silêncio alheio.
- Confirmar automaticamente somente campos sustentados, com catálogo/revisão resolvidos
  e política congelada na calibração. Meta de precisão observada do subconjunto promovido:
  ≥99%, sempre com tamanho da amostra e intervalo. Subconjunto vazio não cumpre essa meta;
  estratos insuficientes permanecem em revisão e não são chamados de homologados para
  automação. Nenhum quórum de detectores é necessário.
- Toda família de E01 tem destino verificável em E07/E13/E14: reconhecida,
  alternativa ambígua, informativa ou ainda não suportada. Registro de “não
  suportado” é transparente e **não** equivale a reconhecimento concluído.
  Uma família sem destino ou ocultada do denominador impede E16; variantes
  pendentes declaradas permanecem no backlog do fluxo independente e não
  bloqueiam a execução ou o aceite deste roadmap por si sós. E16 deve
  publicar cobertura reconhecida e lacunas com todos os IDs da versão
  congelada do inventário no denominador (427 no checkpoint atual).
- Gate padrão sem PDFs privados; fontes intactas, decisões preservadas, API/UI/exportação
  consistentes, execução cancelável e cache versionado. Aprovação deste roadmap não
  certifica projeto elétrico nem substitui revisão de vigência normativa.

## Execução com subagentes e auditoria por IA dos PDFs

Esta revisão organiza a execução futura; não inicia implementação nem auditoria dos
algoritmos nesta tarefa de planejamento. Cada etapa deve usar a equipe indicada no seu
detalhe. **O agente principal coordena e integra; subagentes assumem frentes delimitadas
de implementação, testes e validação independente por IA**, além de pesquisa, dados,
desempenho ou documentação quando a etapa justificar. Não criar tarefas separadas no
aplicativo para substituir subagentes.

### Coordenação, propriedade dos arquivos e checkpoints

1. O coordenador lê instruções, dependências e git, define contratos e atribui um único
   responsável por arquivo/lote editável. Só ele integra alterações compartilhadas,
   decide o aceite e atualiza índice, tags e handoff do roadmap. Faz trabalho útil de
   integração enquanto agentes executam tarefas independentes.
2. Para cada subagente, emitir uma ordem autocontida: ID/objetivo, entradas e versão/hash
   do checkpoint, diretórios/arquivos permitidos, restrições, dependências, entrega,
   validações e condição de término. Caminhos novos continuam propostos até criados.
   Compartilhar decisões de interface antes de liberar mudanças dependentes.
3. Respeitar a capacidade disponível. Nesta sessão há quatro posições contando o agente
   principal; nas próximas, consultar o limite real. Usar ondas/reutilizar agentes para
   lotes de documentos ou famílias. Não abrir um agente por PDF indiscriminadamente.
   Papéis independentes podem trabalhar simultaneamente; execução dos testes finais e
   auditoria das saídas aguardam um checkpoint estável do código/resultado.
4. Implementação edita os módulos atribuídos; testes edita suas fixtures/testes separados,
   sem alterar a implementação para fazer o teste passar; validador por IA lê fontes,
   imagens e resultados, escrevendo apenas seu relatório. Um autor não é o único
   revisor de sua mudança. Correções voltam ao responsável e exigem nova verificação
   dos casos afetados no checkpoint corrigido.
5. Dividir PDFs por documento/página e famílias por pacote, com cobertura sem lacunas.
   Resultados de agentes não são votos: cada achado precisa de evidência verificável;
   divergências são reconciliadas pelo coordenador, preservando incertezas. Isso também
   vale para a validação cruzada dos algoritmos: não introduzir unanimidade de agentes.
6. No retorno, exigir arquivos alterados, comandos/resultados, hashes, achados e pendências.
   O coordenador inspeciona o diff e os artefatos, resolve colisões, executa validações de
   integração e registra delegações/decisões. Mensagem “passou” sem evidência não basta.
7. Se a ferramenta de subagentes estiver indisponível, registrar a limitação, manter as
   frentes separadas e executar o trabalho sequencial possível. Não alegar revisão
   independente feita; aceite que dependa dela fica pendente até executá-la.

### V-P — Auditoria visual por IA em todos os PDFs de exemplo

**Por instrução do usuário, a validação local deve abranger todos os PDFs encontrados
recursivamente em `examples/`, com todas as páginas, inclusive documentos sem a classe
alvo.** A etapa determina o que comparar, não quais arquivos omitir. Os 11 caminhos PDF
encontrados na inspeção desta revisão são somente uma contagem momentânea, não uma lista
fixa nem evidência de PDFs já abertos/validados. Redescobrir a coleção a cada etapa.

Isso acrescenta aceite local às etapas, mantendo o gate portátil sintético de
`examples/README.md` independente de dados privados. A disponibilidade continua variável;
**havendo PDFs, sua conferência não é opcional**. Se não houver nenhum, registrar zero
arquivos e cobertura real não executada; isso não é “todos os PDFs aprovados”. Quando a
etapa exigir comprovação real, a ausência/ilegibilidade impede esse aceite específico,
sem impedir avanços independentes nas fixtures e no código.

1. **Descoberta e manifesto local:** enumerar com `rg --files --hidden --no-ignore examples`
   e filtrar extensão `.pdf` sem diferenciar maiúsculas/minúsculas, ou equivalente.
   Registrar caminho relativo, SHA-256, tamanho, número de páginas, versão do código,
   métodos/configuração, data e estado. Contabilizar cada caminho; conteúdo duplicado pode
   reutilizar inspeção pelo mesmo hash com vínculo explícito, sem sumir do inventário.
   PDF protegido, corrompido ou ilegível deve aparecer com motivo e ação de desbloqueio.
2. **Separação de dados:** todos os exemplos inspecionados iterativamente tornam-se
   corpus de desenvolvimento/diagnóstico. Um exemplo anteriormente reservado, após
   exposição, não sustenta alegação de teste cego; registrar a exposição e reclassificação
   na avaliação atual, preservando os relatórios históricos. A reserva sintética E02
   permanece separada e lacrada até E16. Não alimentar detectores com anotações/ROIs do
   avaliador nem ajustar thresholds com resultados da reserva final.
3. **Inferência reprodutível:** em E02 construir o runner local/relatório de V-P e documentar
   seu comando real. Usar os métodos disponíveis na etapa, individualmente e em composição
   quando implementada; nenhum método não implementado é reportado como executado. Guardar
   saídas antes da inspeção, tempo/memória, falhas e assinaturas. E01 faz inventário visual;
   E03 pode conferir round-trip com as saídas congeladas do baseline, sem reexecutar motores
   inalterados. Checkpoints de auditoria devem corresponder à versão final aceita da etapa.
4. **Inspeção visual independente:** usar skill/ferramentas de PDF e visualização disponíveis
   para renderizar e realmente examinar todas as páginas. O validador por IA primeiro
   inspeciona as imagens originais sem overlays/predições para registrar símbolos e
   ambiguidades; só depois compara saídas, recortes e realces. Texto extraído ou JSON sozinho
   não comprova validação visual. Usar visão geral da página e recortes ampliados/tiles de
   leitura, cobrindo também regiões sem detecção para encontrar omissões. Quando houver
   anotações técnicas, conferir base e aparência separadas, sem aprovar vigência pela imagem.
5. **Registro de achados:** por PDF/página e região, guardar imagem/recorte, geometria,
   observação visual inicial, predição por método, decisão da união, classe, situação,
   quantidade/associação quando avaliáveis, FP/FN/duplicata/conflito, severidade e motivo.
   Ligar cada achado a fonte/hash e IDs de resultado. Incluir acertos exclusivos e
   contraexemplos que validem o ganho da união, além de negativos de legenda/cerca/glifos.
6. **IA como revisão baseada em evidência:** a leitura da IA é uma hipótese auditável,
   não verdade-terreno automática nem aprovação normativa. Registrar ambiguidades e
   discordâncias; rever imagem/fonte com coordenador ou segundo revisor quando necessário.
   Não exigir consenso de agentes nem contar casos incertos como acertos/erros certos.
   Métricas confirmadas e resultados ainda provisórios da IA têm denominadores separados.
7. **Cobertura e aceite:** produzir tabela documento × página × método × camada, com
   executado, visualmente conferido, não aplicável ou bloqueado e justificativa. A soma
   deve reconciliar com o manifesto; não aplicável exige inspeção que o sustente, não
   exclusão prévia. Nenhuma página omitida, falha de renderização ou resultado sem revisão
   conta como concluído. E04–E15 auditam o comportamento afetado em toda a coleção; E16
   audita a composição completa e suas saídas finais. Relatórios anteriores só podem ser
   reutilizados com mesmas entradas, configurações e artefatos comprovadamente inalterados;
   declarar reuso, não execução nova.
8. **Correção e conservação:** salvar PDFs derivados, imagens, manifestos e relatórios
   privados somente em `tmp/`, por etapa/checkpoint/lote. Conferir integridade da fonte
   antes/depois e não enviar PDFs privados a serviços externos. Transformar regressões
   reproduzíveis em fixtures sintéticas autorais; retestar achados corrigidos e impactos
   correlatos. No handoff indicar total de arquivos/páginas, cobertura, problemas resolvidos,
   pendências e caminhos das evidências. Não repetir indefinidamente a coleção sem mudança:
   uma rodada completa por checkpoint aceito, com rodadas dirigidas adicionais justificadas.

**Critério transversal de aceite das etapas:** divisão de subagentes executada conforme
o detalhe, retornos integrados e evidências registradas; V-P com cobertura completa do
escopo da etapa quando houver PDFs, sem omissões silenciosas ou falhas críticas não
resolvidas. Em E01/E02, limitações do baseline são achados esperados, não obrigação de
corrigir os algoritmos nessa etapa. Nas demais, a meta específica e a comparação com o
baseline decidem se um achado impede aceite. E16 exige cobertura completa, resolução de
achados impeditivos e distinção explícita entre comprovação real e apenas sintética.

## Validações reutilizáveis

Comandos confirmados pela configuração, arquivos e README; executá-los na etapa indicada,
não durante o mero planejamento. Usar o Python da `.venv`. Dependências faltantes devem
ser registradas, sem instalar ferramentas/modelos implicitamente para fazer o resultado parecer aprovado.

| Código | Comando / inspeção e resultado esperado |
|---|---|
| V-S | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_pdf_coordinates.py tests/unit/test_pdf_rendering_budget.py` — regressões de extração, coordenadas e memória passam. |
| V-I | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_rule_based_interpreter.py tests/unit/test_method_reconciliation.py tests/unit/test_topology_compliance.py tests/unit/test_topology_path_compliance.py tests/unit/test_e13_occurrences.py tests/unit/test_e14_topology.py tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py` — sem regressões semânticas/revisão. |
| V-U | `.\.venv\Scripts\python.exe -m pytest tests/contracts tests/server/test_review_api.py tests/server/test_deliverable_exports.py tests/integration/test_review_panel.py tests/integration/test_review_highlights.py` — contratos, revisão e exportações passam. |
| V-R | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_analysis_cache.py tests/unit/test_rapid_evidence.py tests/integration/test_document_analysis.py tests/server/test_jobs_api.py` — cache, falhas e jobs passam. |
| V-Q | `.\.venv\Scripts\python.exe -m ruff check .`; `.\.venv\Scripts\python.exe -m ruff format --check .`; `.\.venv\Scripts\python.exe -m mypy` — comandos separados, sem erros. |
| V-G | `.\.venv\Scripts\python.exe -m pytest --cov` — suíte completa e piso de cobertura configurado, atualmente 85,01%, passam. |
| V-O | Se mudar contrato: `.\.venv\Scripts\python.exe scripts/generate_openapi_v1.py`, revisar diff e executar `tests/contracts/test_openapi_snapshot.py` pelo pytest. |
| V-B | `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e02-simbologia/baseline-final` — CLI entregue em E02; desenvolvimento autoral, sem `examples/`. Protocolo/seed/partições/hashes em `docs/e02-benchmark-simbologia.md` e `tests/fixtures/symbols/manifest.json`; reserva recusada até E16. |
| V-P | `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e02-simbologia/predictions` — inferência de todos os PDFs/páginas. Exige também inspeção real independente de imagens e registro por predição/ROI conforme protocolo; o runner não declara aprovação visual. E03 pode reutilizar o baseline congelado com hashes/configuração idênticos. |
| V-N | Testes novos da etapa: criar em `tests/unit/` ou `tests/integration/` conforme fronteira e registrar os caminhos/comandos exatos no handoff. Validar comportamento e falhas, não só espelhar a implementação. |

V-Q é obrigatório para mudanças de código de cada etapa. Falha preexistente não pode ser
apagada nem atribuída à etapa sem análise: registrar comparação e impedimento de aceite.
E16 executa V-G; não repetir toda a suíte após mera edição do roadmap.

## Índice de etapas

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Inventário de símbolos e perfis de referência | #concluida | Nenhuma | Criar inventário versionado e verificável de famílias, variantes e convenções, incluindo símbolos sem equivalente patrimonial. |
| E02 | Benchmark de cobertura e complementaridade | #concluida | E01 | Entregar avaliador independente e baseline reproduzível de símbolos, com reserva e métricas de união. |
| E03 | Contrato de observações e registro de métodos | #concluida | E01, E02 | Introduzir contrato interno aditivo para observações de símbolos, cobertura e estados de cada método. |
| E04 | Robustez vetorial de aterramento e para-raios | #concluida | E03 | Melhorar o detector existente para primitives fragmentadas/agrupadas, escala e estilos, sem ampliar sua lista de classes. |
| E05 | Reconhecimento visual de transformadores | #concluida | E04 | Detectar variantes gráficas de transformador e conjuntos sem depender da existência de um literal reconhecido. |
| E06 | Reconhecimento de estais e ancoragens | #concluida | E04 | Reconhecer as variantes de estai e seus vínculos geométricos sem confundi-las com condutores. |
| E07 | Pacotes extensíveis das demais famílias | #bloqueada | E04, E05, E06 | Pacotes auditáveis entregues; reconhecimento integral permanece histórico/pendente e sua expansão segue o fluxo independente, sem travar E08–E16. |
| E08 | Detector raster por templates e Hough | #concluida | E03, E04 | Acrescentar família raster capaz de detectar símbolos sem vetores aproveitáveis. |
| E09 | Detector por contornos e grafo de traços | #concluida | E03, E04 | Implementar alternativa estrutural de reconhecimento de formas distinta de correlação de pixels e das heurísticas legadas. |
| E10 | Adaptação à legenda e símbolos desconhecidos | #concluida | E03, E08 | Usar a legenda do próprio documento como fonte local de templates/semântica e oferecer desconhecidos revisáveis. |
| E11 | Experimento de detector visual treinável | #concluida | E02, E03 | Medir um detector local aprendido como fonte adicional, com decisão reproduzível de adoção ou rejeição; E07 é insumo opcional versionado. |
| E12 | União, validação cruzada e calibração | #pendente | E05, E06, E08, E09, E10, E11 | Entregar reconciliador de símbolos que aproveite exclusivos e resolva duplicatas/conflitos sem quórum, consumindo apenas pacotes E07 habilitados. |
| E13 | Associação semântica e promoção por campo | #pendente | E12 | Converter hipóteses reconciliadas em propostas úteis, com associação e promoção coerentes com a evidência. |
| E14 | Revisão visual, API e exportações | #pendente | E13 | Expor símbolos, métodos, exclusivos e conflitos de modo revisável no cliente e nos arquivos exportados. |
| E15 | Execução, cache e ativação controlada no servidor | #pendente | E13, E14 | Integrar a composição habilitada ao job do servidor com memória limitada, cancelamento e assinaturas completas. |
| E16 | Aceite integrado e matriz final de cobertura | #pendente | E15 | Demonstrar ganho da união, rastrear todos os IDs E01 e publicar reconhecimento, alternativas e pendências sem alegar cobertura não comprovada. |

A execução das etapas deve usar subagentes conforme a divisão abaixo, por solicitação do usuário em 18/09/2026. Paralelismo entre etapas continua sujeito às dependências; paralelismo dentro de uma etapa segue as responsabilidades e fronteiras de escrita definidas para ela.

## E01 — Inventário de símbolos e perfis de referência — #concluida

**Objetivo:** Criar inventário versionado e verificável de famílias, variantes e convenções, incluindo símbolos sem equivalente patrimonial.

**Por que agora:** A cobertura e a semântica precisam de referência antes de criar detectores ou contar acertos.

**Dependências e paralelismo:** Nenhuma; nenhuma outra etapa iniciada. Frentes A e C em paralelo; B confere o contrato e revisa o registro consolidado no checkpoint final.

**Subagentes e integração:**

- Subagente A — Referências: conferir F01–F04 e registrar famílias/localizadores em relatório próprio; não alterar detectores.
- Subagente B — Inventário: conferir IDs, totalizadores, variantes e lacunas do registro proposto, sem editar o relatório de fontes.
- Subagente C — PDFs: inventariar visualmente todas as páginas de examples/ e registrar famílias, negativos e ambiguidades, sem avaliar motores ainda.
- Coordenação e sincronização — Fontes e inventário visual podem iniciar em paralelo; coordenador consolida o registro após as duas entregas e a checagem de consistência. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `docs/inventario-fontes-normativas.md`, `examples/README.md`, F01–F04 e `pymupdf_symbols.py`; novos inventário e registro de perfis em `docs/` e área de dados a definir (propostos).

**Fora de escopo:** Não implementar detecção, baixar bases pagas ou alterar regras de conformidade.

**Passos de implementação:**

1. Conferir visualmente as famílias F02, seus localizadores e revisões; associar fontes acessíveis internacionais sem equivalência automática.
2. Registrar ID, classe/subtipo, perfil, função operacional/informativa, situação, cardinalidade, ambiguidades e fonte de cada variante; separar símbolo e item de catálogo.
3. Mapear todas as famílias ao lote E04–E07, E10 ou tratamento de desconhecidos; registrar total por família e negativos confundíveis, inclusive legenda.
4. Resolver a origem legada SIMBOLOGIA.pdf; documentar lacunas de fonte sem inventar geometria ou encerrar cobertura incompleta.

**Critérios de aceite:**

- [x] Inventário inclui transformador, para-raios MT/BT, aterramento, estai e todas as famílias restantes da F02, com dono e fonte por variante.
- [x] Perfis CEMIG/externos não compartilham significado por simples aparência; limitações de acesso e revisão constam no registro.
- [x] Símbolos não patrimoniais e compostos têm destino explícito; nenhum ID aparece duas vezes.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. Inspeção dos localizadores e desenhos, comparação do inventário com o índice completo F02, verificação de IDs/fontes e links. Acrescentar testes de esquema se o registro já for legível por código; sem execução de benchmark nesta etapa. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum impeditivo remanescente para E01. V-P, revisão independente,
esquema/integridade e V-Q concluídos; limites de IEC, UKPN e origem legada estão
explicitamente registrados, sem atribuir a eles desenhos ou autoridade não comprovados.

**Riscos e mitigação:** Fonte textual não captura desenhos: páginas efetivamente vistas,
localizadores e hashes preservados; variantes ambíguas continuam revisáveis. A E01 não
constitui benchmark, reconhecimento implementado ou homologação dos projetos de exemplo.

**Prompt para uma sessão limpa:**

```text
Execute E01 — Inventário de símbolos e perfis de referência de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: Nenhuma. Objetivo: Criar inventário versionado e verificável de famílias, variantes e convenções, incluindo símbolos sem equivalente patrimonial.
Escopo: `docs/inventario-fontes-normativas.md`, `examples/README.md`, F01–F04 e `pymupdf_symbols.py`; novos inventário e registro de perfis em `docs/` e área de dados a definir (propostos).
Limites: Não implementar detecção, baixar bases pagas ou alterar regras de conformidade.
Aceite específico: Inventário inclui transformador, para-raios MT/BT, aterramento, estai e todas as famílias restantes da F02, com dono e fonte por variante. Perfis CEMIG/externos não compartilham significado por simples aparência; limitações de acesso e revisão constam no registro. Símbolos não patrimoniais e compostos têm destino explícito; nenhum ID aparece duas vezes.
Validação: Inspeção dos localizadores e desenhos, comparação do inventário com o índice completo F02, verificação de IDs/fontes e links. Acrescentar testes de esquema se o registro já for legível por código; sem execução de benchmark nesta etapa. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Referências: conferir F01–F04 e registrar famílias/localizadores em relatório próprio; não alterar detectores. B — Inventário: conferir IDs, totalizadores, variantes e lacunas do registro proposto, sem editar o relatório de fontes. C — PDFs: inventariar visualmente todas as páginas de examples/ e registrar famílias, negativos e ambiguidades, sem avaliar motores ainda. Coordene assim: Fontes e inventário visual podem iniciar em paralelo; coordenador consolida o registro após as duas entregas e a checagem de consistência. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — execução de 18/09/2026:**

- Base efetiva `5ee65d38cefc8a5344206c714cd6ff2d2360ebcd`; `git status --short`,
  `git diff` e `git diff --cached` inicialmente vazios. A lista de modificações no contexto
  global é histórica do planejamento, não desta execução. Nenhum `AGENTS.md` aplicável
  encontrado nos ancestrais/áreas de escopo; pesquisa ampla acusou acesso negado a cache
  de testes e a um diretório histórico em `tmp/`, sem ocultar fonte/instrução de escopo.
  Dependências: nenhuma. Roadmap completo, escopo e código conferidos; versões continuam
  extrator 1.18.0/interpretador 25.0. Nenhum detector ou regra de conformidade alterado.
- Entrega: [inventário documentado](inventario-simbologia.md),
  [registro JSON](data/inventario-simbologia-v1.json),
  [esquema](schemas/inventario-simbologia.schema.json),
  [relatório A](e01-referencias-simbologia.md),
  [revisão B](e01-revisao-inventario.md) e `tests/unit/test_symbol_inventory.py`.
  Atualizados também `docs/inventario-fontes-normativas.md`, `examples/README.md` e
  este roadmap. Área de dados definida como `docs/data/`, sem consumidor de runtime.
- Denominador congelado: **427 variantes/células em 33 famílias/tópicos F02**, seis
  fontes e cinco perfis; 249 candidatos sujeitos a catálogo/revisão, 81 compostos,
  89 não patrimoniais e oito convenções. Total por pacote: E04=12, E05=29, E06=17,
  E07=365, E10=4. Todos têm dono, fonte, localizador, situação, cardinalidade e destino.
  IDs de definição e localizadores não se repetem; referências a IDs podem se repetir.
  Esses números não são quantidade de ativos nem cobertura de reconhecimento.

**Delegação e checkpoints:**

| Frente / agente | Propriedade exclusiva | Entrega conferida |
|---|---|---|
| A `/root/a_referencias` | `docs/e01-referencias-simbologia.md`, `tmp/e01-simbologia/referencias/` | 45/45 páginas F02, 15/15 F04 e F01 p88 vistas; IEC só metadados; 33 seções/427 células, fontes/hashes/localizadores. |
| C `/root/c_pdfs` | `tmp/e01-simbologia/visual/` | 11 PDFs/11 páginas, base/aparência, 108 imagens vistas, 22 achados, 597 checagens de integridade/cobertura. |
| B `/root/b_inventario` | `docs/e01-revisao-inventario.md`, `tests/unit/test_symbol_inventory.py`, `tmp/e01-simbologia/revisao/` | Contrato, índice visual dirigido, comparação independente 1:1 das 427 células, testes negativos e totais congelados. |
| Coordenador `/root` | Registro, esquema, inventário, guias compartilhados e roadmap; scripts em `tmp/e01-simbologia/` | Consolidação somente após A+C e checagem de consistência; inspeção dirigida das fontes e quatro imagens privadas; integração final. |

A e C iniciaram em paralelo; B preparou o contrato e só validou dados após o checkpoint
consolidado. Quatro posições usadas, sem arquivos com dois escritores. A voltou em uma
segunda onda para revisar o mapeamento semântico do consolidador; B fez a revisão
independente final e congelou o teste antes de V-N/V-Q do coordenador.

Checkpoint de dados `2026.09.18.1` / esquema `1.0.0`:

- Registro SHA-256 `e3d49d9b0072f9f30ea98e2171c0cd520a819a15b329590cfbf35f508f042fcd`.
- Esquema SHA-256 `afe4f05257d0bb8c6743de9738cd68aa105f30d17ed0a2d2a05b1cfed43760b8`.
- Teste congelado SHA-256 `dc5e7027c7a694cd46cebf5490514d6958aaa36eddb3b2ea498027fdd6eb12af`.
- Origem A: `variantes-f02.json` SHA-256
  `65a881fd18dad15666dc3094b9b9c3a59f0d72a5c966d1984afe76a0f2e09b39`; índice e
  PDFs têm hashes no relatório A. Integração preservou nomes, mundo, estados, notas e
  localizadores de todas as células; B também conferiu ambiguidades e famílias.
- Código `pymupdf_symbols.py` intacto, SHA-256
  `a10df79930951c81c3a17fdc51a9e1960f5adc6aa90a8d7edd50b92f1164fa6e`.

**Decisões e divergências resolvidas por evidência:** aterramento está em §19/p22;
para-raios MT/BT, §21/p27, com continuação da seção na p28. Os intervalos de seções
foram conferidos pelas imagens, não calculados pelo próximo título do sumário.
Reguladores dentro de §18 vão a E07; mobiliário/cargas externas de §27 vão a contexto,
sem catálogo presumido. Todos os rascunhos de §33 são informativos e sem conectividade;
81 compostos preservam componentes sem multiplicar ativos. Convenções não têm
cardinalidade patrimonial, e situação vazia difere do `N/A` declarado na fonte.
Cor/estado operado/situação são eixos distintos: vermelho também aparece em rascunho
existente, e envoltório preto pode indicar instalação. O perfil legado permanece
não comprovado; aparência não estabelece equivalência CEMIG/UKPN/IEC/local.

**V-P efetivamente executado:** descoberta recursiva reconciliada com **11 PDFs e
11 páginas**, todos com anotações (163 no total). Base sem anotações e aparência
anotada vistas separadamente; **108 imagens** (22 visões gerais, 64 tiles de cobertura
integral e 22 recortes de 11 regiões). Zero página omitida, falha de renderização ou
mudança de fonte. Há 22 registros de página/região, com imagens, geometria, hashes,
negativos e ambiguidades. Não são rótulos exaustivos por ocorrência ou contagem física.

Manifesto `tmp/e01-simbologia/visual/manifesto.json`, SHA-256
`9b69d430b6680612c2ef54893cbb98900b46b4e579e76e3b2d750920b1e03b2f`;
achados `tmp/e01-simbologia/visual/achados.json`, SHA-256
`2f24947378f6b96c8d5e7608c964a1ebb7d71e698fbefab4340d7b837e66a050`.
Relatório, log das 108 imagens e `validacao.json` ficam nesse diretório privado ignorado.
Todos os exemplos vistos são **desenvolvimento**. A reserva sintética não foi acessada.
Sem predições na E01, FP/FN/duplicatas/exclusivos são **não avaliados**, não zero.

**Comandos e resultados da integração pelo coordenador:**

| Comando na raiz | Resultado |
|---|---|
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_symbol_inventory.py` | **38 passed**, exit 0. Um `PytestCacheWarning`: `.pytest_cache` preexistente sem escrita; todos os testes foram executados. |
| `.\.venv\Scripts\python.exe -m ruff check .` | **All checks passed**, exit 0. |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | **377 files already formatted**, exit 0. |
| `.\.venv\Scripts\python.exe -m mypy` | **Success**, 352 arquivos, exit 0. |
| `.\.venv\Scripts\python.exe tmp/e01-simbologia/check_integration.py` | 427 células preservadas, 427 localizadores únicos, hashes de F01/F02/F04 e 15 links locais válidos, exit 0. |
| `.\.venv\Scripts\python.exe tmp/e01-simbologia/visual/verify_inventory.py` | **PASS, 597 checagens**, 11 PDFs/11 páginas/108 imagens/22 achados, exit 0. Não substitui visão nem mede detecção. |
| `git diff --check` | Sem erro de whitespace, exit 0. |
| `git diff --exit-code -- src scripts pyproject.toml` | Sem alteração de runtime/detectores/dependências, exit 0. |

Logs V-N/V-Q em `tmp/e01-simbologia/integracao-resultados.json`. Os comandos novos de
download/renderização/transcrição constam no relatório A; renderização/recortes e
materialização da inspeção, no relatório privado C. Preparação local executada com
`python tmp/e01-simbologia/build_schema.py` e `python tmp/e01-simbologia/build_inventory.py`,
usando o Python da `.venv`; são scripts de documentação, não runner E02. Scripts e
evidências `tmp/` são locais; o teste versionado funciona sem exemplos privados ou rede.
Não foram executados V-B nem os gates de etapas posteriores; não eram aplicáveis à E01.

**Limitações e próxima sessão:** IEC somente metadados por assinatura; UKPN edição
histórica sem vigência/licença de templates certificada; original `SIMBOLOGIA.pdf`
não identificado, com perfil legado separado. Subtipos visuais locais, identidade física,
repetição em detalhes e oclusões por anotação permanecem revisáveis, sem bloqueio do
inventário E01. E02 continua **#pendente**: construir runner/baseline e referência por
ocorrência sem alimentar inferência com o revisor; preservar exclusivos e lacrar a
reserva sintética até E16. Nenhum commit, publicação ou implantação realizado.

## E02 — Benchmark de cobertura e complementaridade — #concluida

**Objetivo:** Entregar avaliador independente e baseline reproduzível de símbolos, com reserva e métricas de união.

**Por que agora:** Mede ganho real e impede ajustar detectores à própria referência.

**Dependências e paralelismo:** E01. Sequencial após E01.

**Subagentes e integração:**

- Subagente A — Código: implementar o avaliador/runner V-B e V-P nos scripts novos atribuídos.
- Subagente B — Testes/dados: criar fixtures, partições e testes-oráculo do avaliador em arquivos próprios; conferir isolamento dos dados.
- Subagente C — PDFs: executar auditoria visual independente do baseline em toda a coleção e entregar manifesto/achados por página.
- Coordenação e sincronização — Fechar esquema de entrada/relatório primeiro; fixtures e inventário visual avançam em paralelo; comparar saídas somente após runner e baseline estáveis. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `scripts/benchmark_network_pdf.py`, `scripts/benchmark_network_alternatives.py`, `tests/unit/test_benchmark_network_pdf.py`, `tests/unit/test_pymupdf_analyzer.py`; novo benchmark e fixtures de simbologia (propostos).

**Fora de escopo:** Não ajustar detectores nem tornar arquivos privados uma dependência do gate portátil/CI; o aceite local V-P usa todos os exemplos disponíveis.

**Passos de implementação:**

1. Criar fixtures autorais do inventário com controles de escala, rotação, cor, raster, fragments, sobreposição, camada e objetos próximos; separar famílias de desenho entre partições.
2. Implementar pareamento um-a-um e métricas globais deste roadmap, incluindo exclusivos, união/interseção e ablação.
3. Executar baseline atual, congelar manifesto público, tolerâncias, seeds, metas e protocolo; manter os manifestos e relatórios locais V-P em tmp/.
4. Registrar comando real V-B, ambiente e hashes; testar que referência/ROIs não entram no detector e que splits não vazam derivados.

**Critérios de aceite:**

- [x] Uma execução sem examples/ gera métricas por família e denominadores, com FP/FN localizáveis.
- [x] Controle A-acerta/B-falha demonstra ganho da união; duplicatas não aumentam TP e interseção não filtra o candidato.
- [x] Baseline e reserva têm hashes/partições; CLI exata está documentada, sem métricas inventadas de generalização.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q e execução inaugural V-B. Testar avaliador com saídas-oráculo conhecidas: duplicatas, páginas diferentes, classes ausentes e símbolos finos. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum impedimento de E02 após o checkpoint integrado. As limitações
do detector legado e da referência visual parcial estão medidas no handoff;
não equivalem ao cumprimento das metas de reconhecimento de E16.

**Riscos e mitigação:** Sintéticos derivados do próprio template superestimam resultado: usar desenhos independentes e manter partições por ancestral.

**Prompt para uma sessão limpa:**

```text
Execute E02 — Benchmark de cobertura e complementaridade de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E01. Objetivo: Entregar avaliador independente e baseline reproduzível de símbolos, com reserva e métricas de união.
Escopo: `scripts/benchmark_network_pdf.py`, `scripts/benchmark_network_alternatives.py`, `tests/unit/test_benchmark_network_pdf.py`, `tests/unit/test_pymupdf_analyzer.py`; novo benchmark e fixtures de simbologia (propostos).
Limites: Não ajustar detectores nem tornar arquivos privados uma dependência do gate portátil/CI; o aceite local V-P usa todos os exemplos disponíveis.
Aceite específico: Uma execução sem examples/ gera métricas por família e denominadores, com FP/FN localizáveis. Controle A-acerta/B-falha demonstra ganho da união; duplicatas não aumentam TP e interseção não filtra o candidato. Baseline e reserva têm hashes/partições; CLI exata está documentada, sem métricas inventadas de generalização.
Validação: V-S, V-N, V-Q e execução inaugural V-B. Testar avaliador com saídas-oráculo conhecidas: duplicatas, páginas diferentes, classes ausentes e símbolos finos. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: implementar o avaliador/runner V-B e V-P nos scripts novos atribuídos. B — Testes/dados: criar fixtures, partições e testes-oráculo do avaliador em arquivos próprios; conferir isolamento dos dados. C — PDFs: executar auditoria visual independente do baseline em toda a coleção e entregar manifesto/achados por página. Coordene assim: Fechar esquema de entrada/relatório primeiro; fixtures e inventário visual avançam em paralelo; comparar saídas somente após runner e baseline estáveis. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — concluída em 18/09/2026:**

- Base `50204c0dbfedeaf7a8878f7fc27b774bd7fe94d5`, Git inicialmente limpo;
  `git status --short`, `git diff` e `git diff --cached` conferidos. Nenhum
  `AGENTS.md` encontrado nos ancestrais/áreas de escopo. Roadmap completo e
  quatro arquivos de escopo lidos antes da implementação. Sem mudança de detector.
- Dependência E01 confirmada pelos artefatos versionados, hashes de registro,
  esquema e detector e **38 passed** em `tests/unit/test_symbol_inventory.py`.
  Hash do teste difere apenas por LF/CRLF: normalizado permanece
  `dc5e7027c7a694cd46cebf5490514d6958aaa36eddb3b2ea498027fdd6eb12af`.
  Os artefatos privados E01 não existem neste checkout; V-P recebeu nova inspeção.
- Contrato fechado antes da delegação em
  [e02-contrato-benchmark-simbologia.md](e02-contrato-benchmark-simbologia.md),
  checkpoint 1.1. A semântica primária usa confirmado/operacional; ambiguidades
  e contexto informativo conservam denominadores separados.
- A `/root/a_codigo`: exclusivo dos três scripts novos de avaliador/runner/CLI.
  B `/root/b_testes_dados`: fixtures, partições, testes-oráculo e documento de dados.
  C `/root/c_pdfs`: exclusivamente `tmp/e02-simbologia/visual/`, inspeção de imagens
  antes das predições. Coordenador: contratos, documentação, integração e roadmap.
  Quatro posições, sem dois escritores por arquivo; comparação liberada somente
  após estabilizar as saídas e congelar a referência visual inicial.
- Pré-voo: Python 3.13.14, PyMuPDF 1.28.0, Pillow 12.2.0, pytest 8.4.2,
  ruff 0.15.22, mypy 1.20.2, Windows 11. O launcher Microsoft Store da `.venv`
  requer execução fora do sandbox; a revisão automática autorizou os comandos,
  sem instalar dependências ou alterar ambiente. Detalhes/hashes em
  `tmp/e02-simbologia/integracao/environment.json`.
- Entregas públicas: [protocolo e CLI](e02-benchmark-simbologia.md),
  [contrato checkpoint 2](e02-contrato-benchmark-simbologia.md),
  [dados e oráculos](e02-dados-benchmark-simbologia.md),
  [baseline integral](data/benchmark-simbologia-e02-baseline.json), três scripts
  novos `benchmark_symbols.py`, `symbol_benchmark_evaluator.py` e
  `symbol_benchmark_runner.py`, gerador `tests/symbol_benchmark_fixtures.py`,
  `tests/unit/test_benchmark_symbols.py` e `tests/fixtures/symbols/`.
  `docs/data/.gitattributes` fixa LF somente no baseline novo; o atributo local
  das fixtures preserva seus hashes. Os quatro arquivos legados de escopo foram
  lidos/retestados e permaneceram intactos; também não mudaram `src/` ou dependências.
- Protocolo: matching máximo um-a-um, IoU 0,5 e critério fino congelado; união
  exata entre métodos conserva observações/duplicatas e interseção não filtra.
  Classes ausentes têm recall null. Aliases filtered/final são explicitamente
  controle de benchmark, não implementação de E12. GT parcial é recusada para
  métricas globais; score 0,88 não é probabilidade. Nenhuma família E01 foi retirada.
- Revisões resolveram por evidência: fixture de transformador arbitrária substituída
  por controle triangular autoral não normativo; quantidade composta ficou null;
  erros de abertura agora preservam continuidade; mapa SHA fonte/predição rejeita
  referência trocada. No checkpoint 2, centro contido serve só para atribuir o
  contexto de um FP, sem alterar candidato/TP/FP/FN. O smoke original foi preservado.
- B entregou **47 testes** e revisou independentemente runner/avaliador. Na segunda
  onda A reconstruiu os dados públicos de B: **6 PDFs/8 páginas/31 registros**,
  referências e hashes idênticos, **15 grupos de checagens** aprovados. Evidência:
  `tmp/e02-simbologia/a/data-review.md` (SHA
  `3f757535c6efdd1dc3b09d90e73b20f31d8dfe2d003e742affcff2694c6f6761`).
  A não abriu/leu/enumerou a reserva. Coordenador revisou código/fixtures e integrou
  sobre os arquivos congelados, não sobre árvore em mutação.

**V-B e reserva:** desenvolvimento com 4 PDFs/6 páginas, 27 registros, 22 positivos
operacionais confirmados, uma ambiguidade, uma legenda e três negativos; 33 famílias
no relatório, quatro com positivos. O legado emitiu 9 predições: **0 TP/9 FP/22 FN**
pelo critério fixo de localização. `_union_bounds` usa união de retângulos de área
zero, produzindo caixas restritas à haste/corpo; classe visual plausível não basta
para TP localizado. Esse achado não foi corrigido em E02. Há um FP no controle
de legenda; não se declara cumprimento das metas futuras E16. Transformador/estai
e raster não têm método visual implementado no baseline.

Controle-oráculo: A=1 TP/1 FN, B=1 TP/1 FN, união=2 TP/0 FN e interseção=0 TP/2 FN;
duplicatas não aumentam TP. Isso demonstra o avaliador, não ganho entre detectores
reais (somente um foi executado). Calibração tem 2 PDFs/2 páginas; reserva, 2/2,
com ancestral/desenho distinto e lacre operacional sem criptografia. Nenhuma
inferência/renderização/inspeção da reserva em E02. Sua cobertura pequena não
homologa todas as famílias; expansão exige novo manifesto e desenhos independentes.

Reprodução pelo coordenador em workspace mínimo sem `examples/` nem reserva:
referência, predições e relatório idênticos, excluindo apenas tempos variáveis.
Ambiente PyMuPDF 1.28.0; não foi testada identidade binária entre versões.

| Artefato congelado | SHA-256 |
|---|---|
| Baseline público, LF | `fd30cb3fa3cbe34e86b36660b5d794b6c3a6ec371849166188c6d9bcc1d5eeae` |
| Observações V-B | `ff493710564319ffa02a4a5589a81463bfc1cc16c256f489c697a84fe4580cfc` |
| Manifesto de partições | `2175799853d0e3e9a2fdf2dcd9fe96457bcc82706a22fa95de6cc531b4d7e8ce` |
| Reserva opaca | `6874d0585269a0a68397319268076e8e788aff64fc2bc5d776e80efca739be7b` |
| Protocolo canonical JSON | `b00899651b0aadf3ae1cca4baa22affc8a97a39c7d52fc25cacfca37f2d96928` |
| CLI / texto LF | `9c6c5818dc893b4c9e3910011c63efbb67fb3ebd59d85bd886cbae1f1fba98d4` |
| Avaliador / texto LF | `1e5683f18f8312dc59c8437f724dcbe5f1c04ae57995773f124afba9a61511a9` |
| Runner / texto LF | `af084e4dabb1b5b26f88259dbbeb0880c457215f9cc158d31598e525d6bb3e75` |

**Comandos de integração executados pelo coordenador:**

| Comando na raiz | Resultado |
|---|---|
| V-S, comando integral da tabela global | **75 passed**, exit 0, repetido no checkpoint final. |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_benchmark_symbols.py tests/unit/test_benchmark_network_pdf.py` | V-N: **55 passed**, exit 0. |
| `.\.venv\Scripts\python.exe -m ruff check .` | All checks passed, exit 0. |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | 382 arquivos formatados, exit 0. |
| `.\.venv\Scripts\python.exe -m mypy` | Success, 354 arquivos, exit 0. |
| `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e02-simbologia/baseline` | Inaugural: 4 PDFs/6 páginas/9 predições, zero falha; 0 TP/9 FP/22 FN. Preservado após correção de atribuição contextual. |
| `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e02-simbologia/baseline-final` | Checkpoint 2: mesmos totais; erros/estratos localizáveis; exit 0. |
| `.\.venv\Scripts\python.exe tmp/e02-simbologia/integracao/reproduce_and_freeze.py` | Executa a mesma CLI em cópia mínima sem exemplos/reserva; referências/predições/relatórios reproduzidos; exit 0. |
| `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols evaluate --reference tmp/e02-simbologia/baseline-final/reference.json --predictions tmp/e02-simbologia/baseline-final/predictions.json --output tmp/e02-simbologia/integracao/re-evaluation.json` | Avaliação sem inferência reproduz hash integral do relatório `a01444a135774eba74e5b6c3b08f1af32fbef8cf5575d981c45a416dc2944912`, exit 0. |
| `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e02-simbologia/predictions` | 11 PDFs/11 páginas/159 predições, zero falha e fontes intactas, exit 0. Inferência não equivale a aprovação visual. |
| `git diff --check` | Sem erro de whitespace. |
| `git diff --exit-code -- src scripts/benchmark_network_pdf.py scripts/benchmark_network_alternatives.py tests/unit/test_benchmark_network_pdf.py tests/unit/test_pymupdf_analyzer.py pyproject.toml` | Sem mudanças nos detectores, legados ou dependências. |

Logs de integração em `tmp/e02-simbologia/integracao/validation-results.json` e
arquivos V-S/V-N/V-Q, reprodutibilidade em `reproducibility.json`. Comando auxiliar
do registro: `.\.venv\Scripts\python.exe tmp/e02-simbologia/integracao/run_validation.py`.
V-G não era obrigatório nesta etapa e não foi alegado.

**V-P concluída no escopo E02:** 11 PDFs recursivos, 11 páginas, zero documento/página
bloqueado ou falha de inferência, 159 predições e fontes intactas. C inspecionou
154 visões gerais/tiles de base/aparência e mais 27 recortes originais antes de
receber predições; congelou 87 hipóteses (75 operacionais legíveis provisórias,
10 ambíguas, dois controles). Depois inspecionou todos os 159 recortes a 1200 DPI
em 20 folhas de contato, com quatro ampliações individuais adicionais. Os logs
registram inspeção real de imagens, não só renderização, OCR ou leitura de JSON.

Resultado por candidato: **118 classes visualmente plausíveis, 22 FP localizados,
15 ambiguidades e quatro casos semanticamente não avaliáveis, também inspecionados**.
As 118 classes plausíveis não são TP geométricos. Dos 22 FP, cinco são posições
reportadas vazias, dois são falhas de localização com classe plausível e 15 são
gráficos não operacionais. Sete caixas degeneradas no total. A comparação conserva
as caixas emitidas; não deduz se a causa de uma posição vazia é pintura invisível,
coordenada incorreta ou detecção espúria. Há **30 FN mínimos provisórios localizados**
nas ROIs iniciais: sete aterramentos, sete MT, 16 BT; 16 hipóteses legíveis de
transformador ficam fora das classes do método. Precisão estrita e recall global
permanecem null: varrer todas as páginas não torna a anotação por ocorrência
exaustiva nem homologada por especialista.

Matriz com **22 células documento/página/método/camada**: 11 bases executadas e
11 camadas de anotação inspecionadas mas `not_applicable` ao método, com motivo.
Duas páginas têm zero saída apesar de hipóteses visuais. Há apenas um método real:
exclusividade é trivial, ganho empírico da união é null. Nenhuma duplicata adicional
identificada; detalhes distantes não foram fundidos em uma identidade física.
O coordenador fez revisão dirigida de sete imagens (uma visão geral, três recortes
originais, dois candidatos e um contato); isso não é segunda auditoria integral.
Essa revisão apoiou a correção da hipótese inicial do candidato 040 e manteve
ambiguidades do inset raster e da composição de aterramento junto à cerca.

Artefatos privados em `tmp/e02-simbologia/visual/`: `relatorio-vp.md`, `handoff-c.md`,
`manifesto.json`, `inspection-log.json`, `crop-inspection-log.json`,
`original-findings.json`, `reference-initial.json`, `reference-partial.json`,
`prediction-crops.json`, `prediction-review-decisions.json`, `prediction-review.json`,
`matrix.json` e `review-artifact-hashes.json`. A cópia contextual declara
`annotation_scope=partial`; o coordenador confirmou sua recusa pelo avaliador global.
A referência original permanece intacta. Nenhuma ROI/rótulo foi entrada do detector.

| Artefato local | SHA-256 |
|---|---|
| Predições V-P | `e11993a21cbce8ab81ec1ceeba7c4f749e20d522b2825d406305b72ef9a332e9` |
| Manifesto do runner V-P | `b103f391d996f524aec43552b6c6f1a79bbb7d345e05888042602056f98f8fb6` |
| Referência visual inicial | `219f11304fc137dd456a6fc0fcc0512412b55ec493ebd3f5ab92a2c781f86104` |
| Referência explicitamente parcial | `9c40e98b6b32da1c86804511895f9dca6b12d59768abf1d5b668d6df79d5fff7` |
| Revisão dos 159 candidatos | `30efb7bc322af5cb0148acdcc9d4912a4df9fc16226f52c3d9f9248643083b72` |

Os comandos de renderização/congelamento/comparação estão integralmente em
`tmp/e02-simbologia/visual/relatorio-vp.md`. Integração final pelo coordenador:

```powershell
.\.venv\Scripts\python.exe tmp/e02-simbologia/visual/verify_visual.py
.\.venv\Scripts\python.exe tmp/e02-simbologia/integracao/verify_final_checkpoint.py
git diff --check
git diff --exit-code -- src scripts/benchmark_network_pdf.py scripts/benchmark_network_alternatives.py tests/unit/test_benchmark_network_pdf.py tests/unit/test_pymupdf_analyzer.py pyproject.toml
```

Todos terminaram com exit 0. `final-checkpoint.json` confirma hashes das fontes,
artefatos públicos, código congelado e reserva opaca, cobertura dos 159 IDs/22 células,
FN mínimos localizados, resultados dos gates e rejeição de GT parcial. Os verificadores
provam integridade/cobertura, não verdade semântica. Inferência V-P foi preservada do
checkpoint 1: runner, CLI e detector têm os mesmos hashes no checkpoint final; a
única alteração posterior foi no diagnóstico contextual do avaliador, que não é
invocado pelo comando `examples`. Não foi necessária nova inferência.

**Limitações e próximo passo:** dados públicos pequenos e autorais não normativos,
apenas quatro famílias com positivos; nenhuma estimativa de generalização/calibração.
Reserva permanece lacrada até E16, e todos os exemplos inspecionados são desenvolvimento.
E03 deve conferir round-trip usando as saídas congeladas, mantendo fonte/geometria,
score bruto, exclusivos e estados; E04 deve investigar as caixas degeneradas antes
de ajustar reconhecimento. E03 e demais etapas continuam pendentes. E02 não ajustou
detectores, criou commit, publicou ou implantou.

## E03 — Contrato de observações e registro de métodos — #concluida

**Objetivo:** Introduzir contrato interno aditivo para observações de símbolos, cobertura e estados de cada método.

**Por que agora:** Os novos motores precisam devolver evidências compatíveis sem ficar presos às três classes legadas.

**Dependências e paralelismo:** E01, E02. Sequencial após E02; estabiliza contratos compartilhados.

**Subagentes e integração:**

- Subagente A — Código: implementar contrato interno/registro e adapter legado nos módulos atribuídos.
- Subagente B — Testes: cobrir round-trip, identidade, score bruto e estados sem voto negativo em testes separados.
- Subagente C — PDFs: conferir imagens e localização/procedência das observações de todas as páginas, comparando o round-trip ao baseline E02.
- Coordenação e sincronização — Congelar contrato antes do adapter; validador recebe outputs serializados do checkpoint final; coordenador resolve interfaces compartilhadas. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `src/zeny_project_handler/ports/analysis.py`, `domain/analysis.py`, `domain/enums.py`, `adapters/analysis/pymupdf_symbols.py` e persistência JSON existente; novos módulos internos propostos.

**Fora de escopo:** Não alterar DTO público, inferir catálogo nem fundir resultados neste passo.

**Passos de implementação:**

1. Definir observação, hipótese, perfil e registro de capacidades com os campos dos invariantes; diferenciar desconhecido, abstenção, não aplicável, falha e ausência de detecção.
2. Adaptar o detector legado ao contrato, preservando saída e atributos compatíveis; manter score 0,88 como bruto não calibrado.
3. Definir identidade de observação e assinatura de método/modelo/template/configuração; separar identidade de observação e identidade física.
4. Documentar decisão de representação de estai, símbolos informativos e famílias ausentes do enum, sem adicionar ativo arbitrário.

**Critérios de aceite:**

- [x] Round-trip preserva fonte, página, camada, geometria, score bruto e alternativas.
- [x] Motor fora de domínio ou indisponível não produz voto negativo.
- [x] Adapter legado passa nos controles e identidade é determinística para a mesma entrada/configuração.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q e V-B em modo legado; testar serialização, assinaturas distintas e origens correlacionadas. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios e aceite final E03:** nenhum bloqueio remanescente. V-S, V-N, V-Q, V-B legado e
V-P passaram no checkpoint A1, com retorno verificável das três frentes e
integração executada pelo coordenador. Limitações de reconhecimento herdadas
do E02 permanecem documentadas e não são apresentadas como melhoria de detecção.

**Riscos e mitigação:** Mudança interna vaza como alteração pública: manter adapter de compatibilidade e adiar projeção para E14.

**Prompt para uma sessão limpa:**

```text
Execute E03 — Contrato de observações e registro de métodos de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E01, E02. Objetivo: Introduzir contrato interno aditivo para observações de símbolos, cobertura e estados de cada método.
Escopo: `src/zeny_project_handler/ports/analysis.py`, `domain/analysis.py`, `domain/enums.py`, `adapters/analysis/pymupdf_symbols.py` e persistência JSON existente; novos módulos internos propostos.
Limites: Não alterar DTO público, inferir catálogo nem fundir resultados neste passo.
Aceite específico: Round-trip preserva fonte, página, camada, geometria, score bruto e alternativas. Motor fora de domínio ou indisponível não produz voto negativo. Adapter legado passa nos controles e identidade é determinística para a mesma entrada/configuração.
Validação: V-S, V-N, V-Q e V-B em modo legado; testar serialização, assinaturas distintas e origens correlacionadas. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: implementar contrato interno/registro e adapter legado nos módulos atribuídos. B — Testes: cobrir round-trip, identidade, score bruto e estados sem voto negativo em testes separados. C — PDFs: conferir imagens e localização/procedência das observações de todas as páginas, comparando o round-trip ao baseline E02. Coordene assim: Congelar contrato antes do adapter; validador recebe outputs serializados do checkpoint final; coordenador resolve interfaces compartilhadas. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff:** execução de 18/09/2026 registrada abaixo.

### Registro de execução E03 — integração A1

- Início em 18/09/2026 sobre `3a2609c2171f835b3df0e61f8c762e21edc1f26e`,
  Git limpo (`status`, diff de trabalho e staged). Nenhum `AGENTS.md` aplicável
  encontrado nos ancestrais ou no repositório. Roadmap completo e módulos de
  escopo conferidos. Extrator continua 1.18.0; detector legado será preservado.
- Dependências E01/E02 verificadas por hashes do inventário, baseline público e
  predições privadas congeladas; testes `test_symbol_inventory.py` e
  `test_benchmark_symbols.py`: **85 passed**. Pré-voo em
  `tmp/e03-simbologia/integracao/preflight.json`. Launcher Python Microsoft Store
  não executa no sandbox; execução externa autorizada pela revisão automática.
- A `/root/a_codigo`: `domain/symbols.py`, `domain/enums.py`, `ports/analysis.py`,
  `adapters/analysis/legacy_symbols.py`, `adapters/persistence/domain_json.py`.
  B `/root/b_testes`: dois testes unitários novos e teste de compatibilidade JSON
  de integração. C `/root/c_pdfs`: somente `tmp/e03-simbologia/visual/`.
  Coordenador: documentação, exportador e gates de integração. Quatro posições;
  nenhum arquivo com dois escritores.
- Contrato v1 congelado antes do adapter em `tmp/e03-simbologia/a/contrato.md`;
  B revisou a interface antes de implementar testes. Documento público:
  [contrato E03](e03-contrato-observacoes-simbologia.md). C recebe as saídas
  serializadas somente após congelar sua leitura visual das imagens originais.
- Decisões: classes/subtipos abertos, sem criar categorias patrimoniais;
  desconhecido é alternativa explícita. Identidade de observação inclui fonte,
  conteúdo e assinatura, sem equivaler à identidade física. Cobertura separa
  estados e nunca comprova ausência; falha parcial mantém observações. Registro
  conserva família/fontes correlacionadas sem votação. Score bruto usa Decimal
  sem faixa probabilística. Perfil legado fixo não aceita configuração fictícia.
- Geometria original, normalizada, transformação inversa, clipping e primitives
  com OCG ficam preservados. Camada de análise base/anotação é eixo separado.
  O wrapper em `legacy_symbols.py` mantém `pymupdf_symbols.py` byte intacto;
  `domain/analysis.py`, cache, DTO, OpenAPI e pipeline público também intactos.
  A persistência usa registro explícito aditivo em `domain_json.py`, sem migração.
  `confianca_minima` foi auditado; observações novas não entram nesse consumidor.
- Testes B: `tests/unit/test_symbol_observations.py` (27),
  `tests/unit/test_legacy_symbol_adapter.py` (14),
  `tests/integration/test_symbol_observation_json.py` (1): **42 passed**.
  Cobrem assinaturas/modelo/template/perfil/parâmetros tipados, origem correlacionada,
  score negativo e acima de um, alternativas abertas, JSON legado, estados,
  cobertura incompatível, quatro rotações, OCG, barras preenchidas, glifos,
  clipping e caixas degeneradas. A revisou testes e exportador em segunda onda.
- Divergências resolvidas por evidência: fixture inicial declarava só ESTAI mas
  emitia também alternativa informativa; cobertura da fixture corrigida, com
  negativo específico para manter a rejeição. Exportador inicialmente comparava
  tuple Python a list JSON; comparação passou ao JSON materializado. A identificou
  que a projeção E02 hardcodeia camada e lê score dos atributos: acrescentadas
  assertivas diretas de fonte/página/camada/bruto/alternativa/situação/primitives.
  O relatório público E02 remove tempos; comparador exclui somente `seconds` das
  execuções antes da igualdade. Nenhuma tolerância/métrica/detecção foi alterada.

**Comandos finais executados pelo coordenador (Python da `.venv`):**

| Validação / comando na raiz | Resultado |
|---|---|
| V-S, comando integral da tabela global | **75 passed**, exit 0. |
| `.\.venv\Scripts\python.exe -m pytest tests/unit/test_symbol_observations.py tests/unit/test_legacy_symbol_adapter.py tests/integration/test_symbol_observation_json.py tests/unit/test_persistence_codec.py tests/unit/test_analysis_cache.py` | V-N + regressão codec/cache: **58 passed**, exit 0. |
| `.\.venv\Scripts\python.exe -m ruff check .` | All checks passed, exit 0. |
| `.\.venv\Scripts\python.exe -m ruff format --check .` | 387 arquivos formatados, exit 0. |
| `.\.venv\Scripts\python.exe -m mypy` | Success, 359 arquivos, exit 0. |
| `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e03-simbologia/baseline-final` | V-B legado: 4 PDFs/6 páginas/9 predições; zero falha, **0 TP/9 FP/22 FN**, idêntico ao baseline E02. |
| `.\.venv\Scripts\python.exe tmp/e03-simbologia/integracao/export_checkpoint.py` | **11 PDFs/11 páginas/159 observações**, round-trip e IDs exatos; projeção integral idêntica ao E02, fontes intactas. |
| `.\.venv\Scripts\python.exe tmp/e03-simbologia/integracao/verify_final.py` | Gates, hashes de código/fontes/reserva, métricas e observações E02 preservados, exit 0. |
| `.\.venv\Scripts\python.exe tmp/e03-simbologia/visual/verify_visual.py` | V-P final: **11 PDFs/11 páginas/159 observações/22 células**, hashes e cobertura reconciliados, exit 0 pelo coordenador após inspeção real de C. |
| `git diff --check` | Sem erro de whitespace. |
| `git diff --exit-code -- src/zeny_project_handler/adapters/analysis/pymupdf_symbols.py src/zeny_project_handler/domain/analysis.py src/zeny_project_handler_contracts src/zeny_project_handler_api_spec docs/api/openapi-v1.json tests/fixtures/symbols` | Sem alteração do detector, contratos públicos ou fixtures/reserva, exit 0. |

Gates registrados por
`.\.venv\Scripts\python.exe tmp/e03-simbologia/integracao/run_validation.py`.
Após os últimos reforços dos testes B, repetidos apenas os gates afetados com
`run_validation.py V-N V-Q-lint V-Q-format V-Q-types`, todos exit 0.
Logs/comandos completos em `integracao/validation-results.json`; provas de
integridade em `integracao/final-checkpoint.json`. V-G não é exigido pela E03;
V-O não se aplica sem mudança de DTO/OpenAPI. Não foram alegados como executados.

**Checkpoints verificáveis:**

| Artefato | SHA-256 |
|---|---|
| `tmp/e03-simbologia/checkpoint/manifest.json` | `b328ec2372a7e4ec355c1bddd25ee4aebf22861361f772432f336e98dae7232a` |
| `domain/symbols.py` | `46669dfd51b5175aaaaf013f42b4fe30ae28ced5cd5f1874b9fe2303d3897743` |
| `adapters/analysis/legacy_symbols.py` | `62b6de98425fd03cacebbc4acc9132942bf6221d570490b76eed4a5af225f8b4` |
| `adapters/persistence/domain_json.py` | `12122b76e3f7c1cbb2020f6fcadf8fce924f69ea7ad9ff4097f962289143c600` |
| Leitura visual original E03 | `464411ae226acdfc99b17c608c29d4921a53194ad47c1d880a7157938259aa5f` |
| Validação visual final E03 | `16506db7658288b35c090635d1a00a5d6074fccfdc58f8b83d1e3db7a2e7c46d` |
| Revisão das 159 observações E03 | `d82309d0222529f35ee3beaff01fca6d7c19095fb68ea0b456b245597aeb4c16` |
| Matriz final E03 | `80df8c2022c08e9648f1c6886a28dbe50c118f86effd2c1b805272e74e106220` |

Os caminhos de código abreviados são relativos a `src/zeny_project_handler/`.
Manifesto pinado inclui também enum, porta, detector, suporte geométrico, runner
e exportador. `checkpoint/observation-index.json` vincula cada ID E02 ao ID de
observação e payload JSON com hash; inclui páginas sem detecção no manifesto.
Handoffs e revisões A/B: `tmp/e03-simbologia/a/{handoff.md,checkpoint-a1.json,
revisao-integracao.md,revisao-hashes.json}` e
`tmp/e03-simbologia/b/{handoff.md,checkpoint-hashes.json}`.

**V-P — escopo E03:** descoberta recursiva reconciliada com **11 PDFs/11 páginas**,
163 anotações, zero arquivo/página omitido ou bloqueado. C inspecionou realmente
**154 imagens originais** (base/aparência, visão geral e seis tiles por camada),
incluindo regiões sem detecção; congelou sua leitura antes de abrir predições.
Depois viu **20 folhas de contato, cobrindo todas as 159 observações**. Imagens
E02 foram reutilizadas após verificação de hashes, com nova inspeção visual
nesta sessão. Fontes preservadas; matriz de **22 células** distingue base
executada/não detecção e anotações não aplicáveis ao método, sem voto negativo.
Estados finais da matriz: **9 CONCLUIDO, 2 NAO_DETECCAO, 11 not_applicable**.

O round-trip preservou fonte, página, camada, geometria original/normalizada,
transformação, primitivas, score bruto, alternativas e identidade. As decisões
semânticas parciais E02 são transportadas explicitamente: **118 classes plausíveis,
22 FP localizados, 15 ambiguidades e quatro não avaliáveis**; não são 118 TP
geométricos. Os **30 FN mínimos provisórios** (7 aterramento/7 MT/16 BT) são
reuso da referência parcial E02; seus 27 recortes extras não receberam segunda
inspeção isolada nesta sessão. Todas as páginas/regiões integrais foram vistas.
Não se afirma nova contagem exaustiva, precisão estrita ou recall global.
Com um método real, exclusividade é trivial e ganho da união permanece null.

Coordenador inspecionou diretamente uma folha com oito recortes; as posições
006/007 vazias corroboram manter os FP legados. Essa revisão dirigida está em
`integracao/coordinator-visual-review.json` e não equivale a segunda auditoria
integral. Na revisão do verificador C, a matriz inicialmente rotulava toda base
como concluída; exigido usar o estado real da cobertura para páginas sem saída.
A correção foi integrada e o coordenador reexecutou o verificador com exit 0.

Artefatos locais: `tmp/e03-simbologia/visual/{manifesto.json,original-findings.json,
prediction-review.json,matrix.json,validation.json,artifact-hashes.json}`.
O script `verify_visual.py` confere cobertura/integridade/round-trip; visão real
está documentada nos registros do revisor, não é produzida pelo script.
O handoff completo C está em `visual/handoff-c.md`, com comandos de inventário,
congelamento da leitura e verificação, hashes e limites do reuso E02.

**Limitações e próximo passo:** nenhum ganho de detecção/calibração é reivindicado.
As falhas geométricas E02 permanecem para E04; cobertura retangular não é máscara
arbitrária, e a inversa não desfaz clipping. O SHA da fonte é responsabilidade do
chamador e foi conferido na integração. Cancelamento/orquestração/cache da nova
composição ficam para E15. Todos os exemplos vistos são desenvolvimento; reserva
sintética preservada, somente hash opaco conferido, sem abrir seus conteúdos.
E03 está concluída; E04 permanece pendente para uma próxima sessão.
Não houve commit, publicação ou implantação.

## E04 — Robustez vetorial de aterramento e para-raios — #concluida

**Objetivo:** Melhorar o detector existente para primitives fragmentadas/agrupadas, escala e estilos, sem ampliar sua lista de classes.

**Por que agora:** Resolve fragilidades comprovadas e fornece infraestrutura geométrica para novas famílias.

**Dependências e paralelismo:** E03. Sequencial após E03; estabiliza infraestrutura geométrica.

**Subagentes e integração:**

- Subagente A — Código: normalização, assinaturas e deduplicação de aterramento/para-raios nos módulos vetoriais.
- Subagente B — Testes: negativos, preenchimento, escala/rotação, agrupamento e vizinhança, sem alterar thresholds da implementação.
- Subagente C — PDFs: procurar perdas/FP e conferir geometria/situação de aterramento e para-raios em todos os PDFs/páginas.
- Coordenação e sincronização — Testes podem ser preparados com o contrato E03; rodar V-P sobre extração congelada após integração do código. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `adapters/analysis/pymupdf_symbols.py`, `pymupdf_analyzer.py`, `pymupdf_support.py` e `tests/unit/test_pymupdf_analyzer.py`, relativos ao core quando omitido o prefixo.

**Fora de escopo:** Não adicionar transformador/estai nem compensar falhas com coordenadas do benchmark.

**Passos de implementação:**

1. Normalizar segmentos, curvas, retângulos e transforms preservando primitive original; tratar clipping, paths compostos e instâncias de Form XObject.
2. Substituir dependência exclusiva de medidas absolutas/contagem bruta de barras por relações geométricas e perfis versionados.
3. Separar classificação e situação; preservar cor original e incerteza, sem assumir que preto em cópia monocromática prova existente.
4. Rever deduplicação para objetos vizinhos e acrescentar índices espaciais quando necessário; medir custo sem truncar silenciosamente.

**Critérios de aceite:**

- [x] Aterramento e para-raios MT/BT mantêm os TP e negativos legados, incluindo barras preenchidas e glifos.
- [x] Rotação/escala, desenho fragmentado/agrupado e instâncias repetidas mantêm identidade/localização no conjunto E02.
- [x] Monocromático com situação indeterminada não é confirmado automaticamente como existente.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q, V-B com ablação das normalizações; comparar TP/FP e localização com baseline por estrato. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum impeditivo remanescente para E04 no checkpoint A6. V-S,
V-N, V-Q, V-B com ablações e V-P passaram. Os cinco FP herdados e pelo menos
19 FN da referência visual parcial permanecem limitações de cobertura do detector,
sem perda dos controles válidos legados nem FP novos; não constituem homologação
de campo ou avaliação da reserva E16.

**Riscos e mitigação:** Normalização une traços distintos: registrar vínculo a primitives e testar símbolos contíguos e caminhos compostos.

**Prompt para uma sessão limpa:**

```text
Execute E04 — Robustez vetorial de aterramento e para-raios de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E03. Objetivo: Melhorar o detector existente para primitives fragmentadas/agrupadas, escala e estilos, sem ampliar sua lista de classes.
Escopo: `adapters/analysis/pymupdf_symbols.py`, `pymupdf_analyzer.py`, `pymupdf_support.py` e `tests/unit/test_pymupdf_analyzer.py`, relativos ao core quando omitido o prefixo.
Limites: Não adicionar transformador/estai nem compensar falhas com coordenadas do benchmark.
Aceite específico: Aterramento e para-raios MT/BT mantêm os TP e negativos legados, incluindo barras preenchidas e glifos. Rotação/escala, desenho fragmentado/agrupado e instâncias repetidas mantêm identidade/localização no conjunto E02. Monocromático com situação indeterminada não é confirmado automaticamente como existente.
Validação: V-S, V-N, V-Q, V-B com ablação das normalizações; comparar TP/FP e localização com baseline por estrato. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: normalização, assinaturas e deduplicação de aterramento/para-raios nos módulos vetoriais. B — Testes: negativos, preenchimento, escala/rotação, agrupamento e vizinhança, sem alterar thresholds da implementação. C — PDFs: procurar perdas/FP e conferir geometria/situação de aterramento e para-raios em todos os PDFs/páginas. Coordene assim: Testes podem ser preparados com o contrato E03; rodar V-P sobre extração congelada após integração do código. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — execução iniciada em 21/09/2026:**

- Base `4bf1d9f9670f46fc5d7131298bd8875c9985db08`; Git inicialmente limpo,
  diff de trabalho e staged vazios. Nenhum `AGENTS.md` aplicável encontrado.
  Roadmap e módulos de escopo conferidos; estado sincronizado no índice/detalhe.
- E03 verificada por hashes dos módulos centrais e checkpoint de integração;
  reprodução de `test_symbol_observations.py`, `test_legacy_symbol_adapter.py`
  e `test_symbol_observation_json.py`: **42 passed**. Pré-voo em
  `tmp/e04-simbologia/integracao/preflight.json`. Launcher Windows da `.venv`
  falhou no sandbox; revisão automática autorizou execução externa, sem instalar
  dependências. A mudança de HEAD desde E03 não alterou esses contratos.
- A `/root/a_codigo`: exclusivo dos três módulos vetoriais do escopo.
  B `/root/b_testes`: exclusivo de `tests/unit/test_pymupdf_analyzer.py`.
  C `/root/c_pdfs`: somente `tmp/e04-simbologia/visual/`, leitura independente
  das imagens antes de receber predições. Coordenador: integração, documentação,
  ajuste mínimo de `legacy_symbols.py` e `test_legacy_symbol_adapter.py` para
  preservar o contrato E03 com caixas agrupadas e situação indeterminada.
  Quatro posições, sem dois escritores por arquivo.
- Contrato acordado: normalizações `grouping`, `fragments`, `scale`, `styles`,
  configuração explícita para ablação, suporte por drawing/item, caixa original
  por ocorrência, score bruto preservado, preto/cinza sem convenção com situação
  `None`. Referências do revisor não entram na inferência; reserva intocada.
- C redescobriu 11 PDFs/11 páginas/163 anotações; hashes dos renders E02
  conferidos para reuso com nova inspeção real de 154 imagens de base/aparência.
  Referência parcial congelada antes das predições, SHA-256
  `e83887bbae775faa4f64804088158bd74ec1c6e1bfb2dffa52a7fe2cc18fcec4`.
  A3: V-S 221 passed, V-N 60 passed, lint/format/mypy aprovados; V-B 11 TP,
  1 FP, 11 FN globais, incluindo classes/camadas fora de E04 no denominador.
  V-P leu 11 PDFs/11 páginas, produziu 138 candidatos e foi realmente inspecionada
  por C, mas **rejeitou o checkpoint** por barras largas perdidas e aterramentos
  trocados por MT após decompor círculos. Coordenador confirmou uma troca em imagem.
  A3 preservado em `tmp/e04-simbologia/checkpoint-a3/` e
  `tmp/e04-simbologia/visual/review-a3.json`. Correções voltaram a A; B acrescentou
  contraprovas autorais. O aceite daquele checkpoint ficou pendente de correção,
  resolvida e revalidada no A6 final abaixo.
- Documento técnico: [robustez vetorial E04](e04-robustez-vetorial.md).
  A4 corrige os dois grupos de regressões e acrescenta junção em T e MT de cinco
  barras. Versões `1.19.1:vetorial-3`/cache `1.19.1`; configuração completa das
  quatro normalizações. V-P inspecionou realmente os 221 candidatos e apontou
  um FP novo de associação entre dois símbolos colineares. C e coordenador
  confirmaram em imagem; A4 foi arquivado e reaberto como A5. Uma interação
  comprovada entre haste redundante e barra fragmentada interrompeu a inferência
  A5 antes de terminar; não conta como V-P. A6 corrige a ordem de reconstrução
  e limita a reunião às hastes originais, preservando vizinhos. B encerrou
  a revisão com 302 passed e hashes estáveis; gates abaixo são os finais A6.

**Comandos efetivamente executados no checkpoint final A6:**

| Validação | Comando relativo à raiz | Resultado |
|---|---|---|
| V-S | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_pdf_coordinates.py tests/unit/test_pdf_rendering_budget.py` | 286 passed, 7,92 s. |
| V-N | `.\.venv\Scripts\python.exe -m pytest tests/unit/test_symbol_observations.py tests/unit/test_legacy_symbol_adapter.py tests/integration/test_symbol_observation_json.py tests/unit/test_persistence_codec.py tests/unit/test_analysis_cache.py` | 60 passed. |
| V-Q | `.\.venv\Scripts\python.exe -m ruff check .`; `.\.venv\Scripts\python.exe -m ruff format --check .`; `.\.venv\Scripts\python.exe -m mypy` | Todos exit 0; 387 arquivos formatados e 359 verificados por mypy. O primeiro format apontou finais de linha do analyzer, corrigidos e revalidados. |
| V-B | `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e04-simbologia/baseline-final` | 11 TP / 1 FP / 11 FN globais; 11/11 positivos vetoriais de base de E04 pareados. |
| Ablação nova | `.\.venv\Scripts\python.exe tmp/e04-simbologia/integracao/ablate.py` | Completa 11/1/11; sem todas 8/1/14; sem fragmentos 10/1/12; sem agrupamento 9/1/13; sem escala e sem estilos 11/1/11, na ordem TP/FP/FN. |
| Aceite E02 novo | `.\.venv\Scripts\python.exe tmp/e04-simbologia/integracao/verify_benchmark.py` | Exit 0: todos os 11 suportados, sem duplicatas e sem aumento de FP nos negativos críticos. |
| V-P | `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e04-simbologia/predictions` | A6 completo: 11 PDFs/11 páginas/220 candidatos, zero falhas, fontes intactas e auditoria visual reconciliada. |

O harness `tmp/e04-simbologia/integracao/run_validation.py` registra comandos,
saídas e códigos em `validation-results.json`; os comandos novos de apoio são
locais e não substituem o runner E02. `checkpoint.py` congela runtime, assinatura
e hash opaco da reserva; `checkpoint.py verify` confere gates, fontes e descoberta
após a inferência. Nenhum desses verificadores certifica a semântica das imagens.

**Integridade final A6:** configuração assinada
`5dfa257155ff88fea773c4da4f789759eab3358f505dc7a3c22b3ce4d83fd0e6`;
versões detector `1.19.3:vetorial-5` e analisador/cache `1.19.3`.
O arquivo principal passou de 46 para 257 casos, incluindo 211 casos E04.
Os lotes de B se sobrepõem a V-S/V-N e não são somados como testes distintos.
Handoffs A/B e logs permanecem em
`tmp/e04-simbologia/a/handoff.md` e `tmp/e04-simbologia/b/handoff.md`.

| Artefato | SHA-256 |
|---|---|
| `pymupdf_symbols.py` | `957f672b669e9ce6fb6bd8cff066138b3e81c749681720e1f9974b4edb112a92` |
| `pymupdf_analyzer.py` | `036ef48f8a216bd1783ee9173302d9352851148fbb20cdacbc103b0eb2c5881c` |
| `legacy_symbols.py` | `56825a6cf3342c2f6f90f45730eee8eb1d51ef4e0b181d95500386d64938e15d` |
| `test_pymupdf_analyzer.py` | `41b078063984afb495674b836d6cae8428eaed4589a86b489cf4a18d20985984` |
| Predições V-P A6 | `5d1f67d002dbd5277831b57413a06fa0c7ab0642069fc9891eadd81e4816a605` |
| Manifesto V-P A6 | `bacca11678516a0686f9eb430bedc8cb9a308c16124aef56f014be02082e9092` |
| Reserva E02, somente hash opaco | `6874d0585269a0a68397319268076e8e788aff64fc2bc5d776e80efca739be7b` |

`pymupdf_support.py`, DTO/codec E03, avaliador, runner, fixtures, tolerâncias e
baseline público E02 permaneceram inalterados. Fontes finais também foram
copiadas para `tmp/e04-simbologia/integracao/source-a6/`. Nenhum commit,
publicação ou implantação foi realizado.

**Aceite final e V-P — 21/09/2026:** o coordenador reproduziu
`checkpoint.py verify` e `.\.venv\Scripts\python.exe tmp/e04-simbologia/visual/verify_visual.py`,
ambos exit 0. A frente B encerrou a revisão A5→A6 com **302 passed**, hashes
antes/depois idênticos e nenhum achado impeditivo. Os gates finais de integração
constam da tabela acima; nenhuma execução parcial foi usada como validação.

C inspecionou realmente 154 imagens originais de base/aparência antes das
predições, 159 recortes do baseline, 27 recortes de referência E02, oito recortes
próprios e todas as 221 predições A4. A6 foi inferido integralmente: **220
inspeções reaproveitadas com igualdade exata** de documento/página/camada,
classe, caixa, suporte, situação e revisão, além de SHA-256 idêntico do PDF e
do PNG rerenderizado. Delta visual novo: zero. Foi removido exclusivamente o
FP A4 #92, confirmado em imagem por C e coordenador; não se alega nova leitura
dos 220 recortes. Manifesto, matriz de 22 células, hashes e decisões individuais
estão em `tmp/e04-simbologia/visual/review-final.json`,
`checkpoint-a6/delta-proof.json`, `relatorio-final.md` e `verification.json`.

- Baseline 159 → A6 220: 143 pareamentos por suporte original exato, 16 perdas
  adjudicadas (15 FP herdados removidos e um ambíguo), 77 candidatos novos
  visualmente plausíveis. Todos os **118 candidatos plausíveis legados** foram
  preservados na mesma classe/localização; caixas degeneradas foram corrigidas.
- A6: **197 classes plausíveis, cinco FP herdados, 14 ambiguidades e quatro não
  avaliáveis**. Zero FP novo e nenhuma perda plausível. Classe plausível não
  equivale a TP estrito com verdade-terreno especialista. A referência parcial
  mantém **19 FN mínimos** (um aterramento, dois MT, 16 BT), antes 30; 11 ROIs
  passaram a ter candidato da mesma classe, sem transformar interseção em TP.
- 137 candidatos pretos permanecem com situação indeterminada e revisão; zero
  confirmação automática como existente. Quantidade física, associação e vigência
  de convenções coloridas não foram homologadas. Apenas um método vetorial base
  foi executado: exclusivos são triviais, ganho de união e recall global são
  indefinidos. Silêncio de outro algoritmo não foi veto e score não virou probabilidade.
- V-B final: 11/11 positivos vetoriais de base suportados, zero duplicatas,
  IoU mínimo 0,99999978; comparação por estrato e seis ablações no documento E04
  e JSONs locais. Os 11 FN globais mantêm raster/anotação e classes fora desta
  etapa no denominador. Um FP de legenda herdado continua explícito.

Comandos novos da frente C, registrados com seus resultados no handoff:
`.\.venv\Scripts\python.exe tmp/e04-simbologia/visual/prepare_comparison.py checkpoint-a6 tmp/e04-simbologia/predictions/predictions.json`,
`.\.venv\Scripts\python.exe tmp/e04-simbologia/visual/prepare_a5_delta.py tmp/e04-simbologia/predictions/predictions.json 5d1f67d002dbd5277831b57413a06fa0c7ab0642069fc9891eadd81e4816a605 checkpoint-a6`
e `.\.venv\Scripts\python.exe tmp/e04-simbologia/visual/finalize_a5.py checkpoint-a6`;
os nomes históricos dos scripts não mudam o checkpoint A6 indicado nos argumentos
e artefatos. Verificador final executado também pelo coordenador. A inferência
somou 269,62 s nos 11 documentos; memória é `tracemalloc`, não RSS/MuPDF.
Retorno final da frente C: `tmp/e04-simbologia/visual/handoff.json`, conferido
pelo coordenador contra o relatório, manifesto e prova de delta. As três frentes
encerraram suas entregas; `git diff --check` passou e não há validação obrigatória
pendente ou falhando no checkpoint final.

Limitações: todos os exemplos são desenvolvimento, reserva permanece lacrada;
clipping arbitrário não é máscara exata e cópia do documento tem custo de memória
proporcional. Não há alegação de precisão de campo ou de cobertura integral das
famílias. Próxima etapa: seguir as dependências do índice, levando os FP/FN e
ambiguidades registrados para reconhecimento/composição posteriores, sem alterar
E02 ou abrir a reserva antecipadamente.


## E05 — Reconhecimento visual de transformadores — #concluida

**Objetivo:** Detectar variantes gráficas de transformador e conjuntos sem depender da existência de um literal reconhecido.

**Por que agora:** É uma lacuna explícita entre o interpretador textual atual e a análise de simbologia desejada.

**Dependências e paralelismo:** E04. Pode ocorrer em paralelo a E06/E08/E09 após E04, com módulos e fixtures separados.

**Subagentes e integração:**

- Subagente A — Código: detector de transformadores no módulo de família atribuído.
- Subagente B — Testes: variantes sem texto, conjuntos, círculos negativos e cardinalidade em fixtures próprias.
- Subagente C — PDFs: conferir todos os documentos/páginas buscando transformadores omitidos, conjuntos e conflitos com literais.
- Coordenação e sincronização — Não editar normalizador E04 em paralelo; compartilhar pedidos de alteração com coordenador e validar o checkpoint resultante. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** Registro E01, contrato E03, infraestrutura E04 e `adapters/interpretation/category_analyzers.py` como consumidor futuro; novo detector de família em `adapters/analysis/` (proposto).

**Fora de escopo:** Não atribuir potência, fases, quantidade ou modelo somente pela contagem de círculos.

**Passos de implementação:**

1. Implementar assinaturas de forma/arranjo das variantes verificadas em E01, com orientação e escala relativas.
2. Devolver classe, componentes e hipótese de conjunto preservando cardinalidade indeterminada quando necessário.
3. Usar texto próximo como evidência separada de atributos, nunca requisito obrigatório de detecção.
4. Adicionar negativos de poste, círculos decorativos, glifos e componentes sobrepostos.

**Critérios de aceite:**

- [x] Transformadores sem texto geram observações em fixtures de suas variantes cadastradas.
- [x] Símbolo composto não vira múltiplos ativos por contagem de componentes.
- [x] Texto incompatível fica como alternativa/conflito e não altera o desenho observado.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q, V-B por variante de transformador; incluir casos sem literal, duplicados e em legenda. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum impeditivo remanescente para o escopo vetorial E05: V-S,
V-N, V-Q, V-B e auditoria V-P vetorial passaram no checkpoint A7. A auditoria
integral dos PDFs ainda contém um FN comprovado em conteúdo raster, registrado
para E08; isto limita a cobertura visual do produto e não foi contado como
acerto E05. Contexto de detalhe, cardinalidade entre desenhos e três casos
ambíguos permanecem para revisão nas etapas consumidoras.

**Riscos e mitigação:** Confusão de círculos e interpretação de banco: exigir forma/arranjo documentados, mantendo quantidade separada.

**Prompt para uma sessão limpa:**

```text
Execute E05 — Reconhecimento visual de transformadores de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E04. Objetivo: Detectar variantes gráficas de transformador e conjuntos sem depender da existência de um literal reconhecido.
Escopo: Registro E01, contrato E03, infraestrutura E04 e `adapters/interpretation/category_analyzers.py` como consumidor futuro; novo detector de família em `adapters/analysis/` (proposto).
Limites: Não atribuir potência, fases, quantidade ou modelo somente pela contagem de círculos.
Aceite específico: Transformadores sem texto geram observações em fixtures de suas variantes cadastradas. Símbolo composto não vira múltiplos ativos por contagem de componentes. Texto incompatível fica como alternativa/conflito e não altera o desenho observado.
Validação: V-S, V-N, V-Q, V-B por variante de transformador; incluir casos sem literal, duplicados e em legenda. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: detector de transformadores no módulo de família atribuído. B — Testes: variantes sem texto, conjuntos, círculos negativos e cardinalidade em fixtures próprias. C — PDFs: conferir todos os documentos/páginas buscando transformadores omitidos, conjuntos e conflitos com literais. Coordene assim: Não editar normalizador E04 em paralelo; compartilhar pedidos de alteração com coordenador e validar o checkpoint resultante. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — execução iniciada em 22/09/2026:**

- Base `4f68ba5`; Git limpo antes da atualização do roadmap. Nenhum `AGENTS.md`
  aplicável encontrado. E04 A6 foi conferida: `pymupdf_symbols.py`,
  `pymupdf_analyzer.py`, `legacy_symbols.py` e seu teste central têm os hashes
  publicados em E04. O baseline E04 reproduzido antes das mudanças deu
  **11 TP / 1 FP / 11 FN** em 4 PDFs/6 páginas, sem abrir a reserva E16.
- Propriedade: A `/root/codigo_transformador`, exclusivo de
  `adapters/analysis/pymupdf_transformers.py`; B `/root/testes_transformador`,
  exclusivo de `tests/fixtures/transformers/` e
  `tests/unit/test_pymupdf_transformers.py`; C `/root/pdfs_transformador`,
  somente `tmp/e05-simbologia/visual/`, leitura de imagens antes das predições.
  Coordenador: runner/CLI, benchmark E05, documentação, índice e integração.
  `pymupdf_symbols.py`/normalizador E04 e `category_analyzers.py` não foram
  editados. Contrato A→B: `perfil_transformadores()` e
  `observar_transformadores(...) -> ResultadoMetodoSimbolos` E03.
- A1 foi rejeitado por V-N (16 falhas/20 aprovações), incluindo observações
  duplicadas para triângulos ciano e falhas de enrolamentos/conjunto. A2 passou
  37 testes, mas V-B encontrou **20/29 variantes**, 25 TP / 9 FP / 9 FN:
  caixas de círculo/X/terminais não cobriam o símbolo composto. A3 congelado
  em `0895dc5409b15ab6d1d36851aa8c40b35a21d0b0` corrigiu essas caixas;
  B repetiu **37 passed** com hash estável e IoU ≥0,5 por variante.
- V-B A3 autoral: `python -m scripts.benchmark_transformers_e05 --output
  tmp/e05-simbologia/benchmark-a3`, **29/29 variantes**, 34 TP / 0 FP / 0 FN
  do método E05 em 35 páginas, incluindo controles de legenda, duplicação e
  círculos negativos. E02 com `--include-transformers`: união **14 TP / 1 FP /
  8 FN**, ante 11/1/11 de E04; três acertos exclusivos de transformador, sem
  apagar os 11 acertos legados. Um transformador raster permanece fora do
  domínio vetorial. A referência autoral é lida somente após persistir
  predições, sem entrada no detector; reserva opaca intacta.
- V-S A3: **286 passed**; V-N integrado
  `test_pymupdf_transformers.py test_benchmark_symbols.py`: **84 passed**;
  V-Q: Ruff check exit 0, format check **392 arquivos**, mypy **363 arquivos**,
  exit 0. O runner legado isolado manteve **47 passed**. O launcher `.venv`
  exigiu execução escalada aprovada pelo auto-review do sandbox, sem instalar
  dependências. Comandos exatos e gate final serão registrados ao fechar.
- V-P A3 executou `python -m scripts.benchmark_symbols examples --root
  examples --include-transformers --output tmp/e05-simbologia/predictions-a3`:
  **11 PDFs recursivos/11 páginas**, zero falhas, 492 predições (220 legado,
  272 E05). Manifesto SHA-256 `fcb215997266b15e5de0c9c87932f017d85fcd41e0a56ba856bb72d666202e50`;
  predições `cb786e4a7fff55d99ee8ef296f25b1b4d769fd4b4b649047b45f48d6e8ff8a34`.
  C abriu realmente 11 imagens gerais, 44 quadrantes e quatro recortes de
  origem **antes** das predições; depois abriu 11 mapas e 20 folhas de contato
  com os 272 recortes. Fontes SHA intactas; 220/220 predições E04 byte a byte
  idênticas. `tmp/e05-simbologia/visual/review-a3.json` decide cada ID:
  **20 correspondências gráficas provisórias, 9 duplicatas, 192 FP confirmados,
  51 ambíguos e ao menos 1 FN visual seguro**. Exemplos são desenvolvimento,
  não verdade normativa exaustiva. Relatório em
  `tmp/e05-simbologia/visual/comparison-a3.md`.
- **A3 rejeitado:** V-P confirmou confusão sistemática com rosa dos ventos,
  postes/marcadores, círculos vermelhos 4F/4FF e detalhes, além de FN do setor
  ciano. A/B receberam categorias, sem ROIs privadas, para criar negativos e
  positivo autorais B2 e corrigir assinatura A4. O método ainda não entra no
  consumidor patrimonial; `confianca_minima` não recebe scores novos.
  Nenhuma alegação de sucesso ou homologação neste checkpoint.
- B2 congelou 41 páginas/42 casos em um PDF autoral (SHA-256
  `e61c9dbf029e5d04229e3153e1d2e875f7c25a80d6b6011c3e18972a5b635dc4`):
  29 variantes, duplicação, legenda, conflito textual, círculo com setor ciano,
  rosa dos ventos, postes e anotações vermelhas. A3 falhou nesse gate com
  **34 TP / 14 FP / 1 FN**. A4 (`d6d250a7c04c5fb12bba790ee0fccc4f4d8b3b4a`)
  passou B2 com **35 TP / 0 FP / 0 FN**. B3, congelado em PDF separado de
  5 páginas/5 casos (SHA-256
  `b1de1ef50b5caba441efc2f5608654a7690381585d51aaa7ba19ffcf5e57efc7`),
  acrescentou três negativos de lóbulos/anotação e dois setores ciano vetoriais.
  B confirmou **48 passed** no V-N A4, sem modificar o PDF B2. O benchmark
  integrado de ambos os PDFs, `python -m scripts.benchmark_transformers_e05
  --output tmp/e05-simbologia/benchmark-b3-a4`, passou **29/29 variantes,
  37 TP / 0 FP / 0 FN**, em 46 páginas. São controles sintéticos de
  desenvolvimento, não evidência de acurácia real.
- **A4 também rejeitado em V-P:** inferência de 11 PDFs/11 páginas sem falha,
  com 220 candidatos legados idênticos e 135 E05. Predições SHA-256
  `388fb5b413b3d121b7f9e36a07988de5116d58a64efb3fee0ada5e97f62a7cdb`;
  manifesto `e1d604fb172621e77937152df89b753712091d4ed83f6b1a08928b44a436483d`.
  C abriu as 12 folhas de contato A4, revisou 24 candidatos novos e reconciliou
  os 111 objetos idênticos com os recortes já vistos A3: **14 formas plausíveis,
  117 FP confirmados, 4 ambíguos**, 0 duplicatas E05 comprovadas. A revisão
  135/135 IDs está em `tmp/e05-simbologia/visual/review-a4.json` (SHA-256
  `c94e2c3f70cbacd147a236fd9e99cef0680bea4f8cfb9e3401db28556c2f3faf`);
  a matriz por página, FN e limites em `comparison-a4.md` (SHA-256
  `e0d67814c90cba8ac8b3c679dc594c383039481e105804f040ba1f5175507dfa`).
  O FN seguro de círculo com setor ciano pertence a faixas **raster** embutidas:
  `get_drawings()` não oferece a forma na região. E08 deverá tratar o raster;
  E05 ainda falha por 117 FP vetoriais reais, independentemente desse limite.
  A recebeu apenas categorias morfológicas gerais, sem ROI/rótulo de revisão.
- A5 (`42f3d1fcaa4fda79ac1273a56592bbfdaaf46309`, perfil E03 v2) trocou
  atalhos por contagem por conectividade de arcos, terminais e leads. B repetiu
  revisão independente: **48 testes próprios passaram**, hashes do detector e
  fixtures estáveis. Integração: V-S **286 passed**, V-N combinado **96 passed**
  após excluir apenas tempo variável de execução da comparação do runner,
  Ruff check/format **392 arquivos** e mypy **363 arquivos** passaram. V-B
  autoral B2+B3: **29/29 variantes, 37 TP / 0 FP / 0 FN** em 2 PDFs/46 páginas;
  E02 sintético com método opt-in: união **14 TP / 1 FP / 8 FN**.
- V-P A5: `python -m scripts.benchmark_symbols examples --root examples
  --include-transformers --output tmp/e05-simbologia/predictions-a5`, **11/11
  PDFs/páginas, zero falhas**, 220 saídas legadas exatas + 20 E05 = 240 na
  união bruta. Manifesto SHA-256
  `217a557b89b996b8e2209fa6a3ecd2e9faaf7d1af7fc9a7c580b97ed0cc9f9c2`;
  predições `b1c95e1d16f719fda3377731660d39d1716ee7d5610fbcbf95f843cd6bb1d7df`.
  C não reutilizou decisões dos novos IDs: abriu 8 mapas/8 contatos e decidiu
  **20/20**: 14 formas plausíveis, 3 ambíguas, **3 FP certos**, sem FN vetorial
  seguro demonstrado; 135 candidatos A4 removidos reconciliados. Revisão
  `tmp/e05-simbologia/visual/review-a5.json` SHA-256
  `e1b9c75d6bf8b1d3b2dd6a7e2ce7b59338310653cbb1e1d7f28ca7b32c1a81e6`;
  relatório `comparison-a5.md` SHA-256
  `9ed0fd29bc541d5db373f992867a63653247da6086250846754015c9ec5a8f3d`.
  Os 3 FP são uma causa morfológica no ramo de enrolamentos circulares
  (fragmento circular/haste e círculos de poste sem espiras). A6/B4 receberam
  somente essa categoria geral para correção/controle autoral. O FN raster
  seguro segue separado como limitação E08; V-P A5 **não foi aprovado**.
- B4 acrescentou um terceiro PDF autoral de 4 páginas/4 casos, SHA-256
  `e771fa0bf0eb8ed30dd3459df0f02e0cb95b897a733f6d1f7b6541a913e6f878`,
  com três negativos círculo/haste e um par positivo. A5 já passava esses
  controles, então eles protegem regressão, mas não reproduzem os FP reais.
  A6 (`43e091db527bcb1fd2c457ba2c8601d42b66831d60717ea0aaca1e6bf85a14d1`,
  perfil E03 v3) exigiu circularidade completa, cores coerentes e rejeição de
  haste perpendicular. V-B B2+B3+B4 passou **29/29, 38 TP / 0 FP / 0 FN** em
  3 PDFs/50 páginas; V-N integrado **100 passed**, V-S **286 passed**, Ruff
  check/format e mypy passaram. B confirmou **52 passed** próprios com hash
  estável. E02 sintético opt-in permaneceu **14 TP / 1 FP / 8 FN**.
- **A6 rejeitado em V-P:** 11 PDFs/11 páginas, zero falhas, 240 candidatos
  (220 legados exatos + 20 E05); predições SHA-256
  `dddb7fd02c0dfebfe053dfcd9070ee5453a4ff7054e05440869519177ef60994`,
  manifesto `975e8e788b22c5d73622392a78fde0e503def76afc0cf2b8254cad79489074b36`.
  C reabriu 20/20 novos IDs em 8 contatos: mesmos 20 bboxes/classes/variantes e
  componentes de A5 apesar dos IDs novos, portanto **14 formas plausíveis,
  3 ambíguos, 3 FP certos**. Seis âncoras vetoriais pré-predição seguem
  cobertas; nenhum FN vetorial seguro demonstrado. A7/B5 investigam a
  distinção geral entre marcas preenchidas de poste/ponto e espiras vazadas,
  sem normalizador E04 ou ROIs privadas no algoritmo. O FN raster E08 permanece.
- A7 (`9938265175122057ce6adb9fe65ba77213f467fd5d5d9a1b6736d2f97e202553`,
  perfil E03 v4) passou a carregar o preenchimento dos caminhos separado do
  contorno e exigir laços vazados no ramo de enrolamentos circulares. O
  diagnóstico read-only de A6 mostrou que os três FP eram pares de caminhos
  `type=fs` preenchidos, embora o contorno fosse escuro; essa propriedade
  havia sido perdida em `_Round`. B5 congelou um quarto PDF autoral de
  3 páginas/3 casos, SHA-256
  `818c5d7da77e916d8a2bf50cdb0fc25e5be8069bb7d8f4013b862c18bf24f486`,
  com discos preenchidos negativos e laços vazados positivos. B repetiu **55
  passed** próprios e confirmou hashes estáveis. Integração A7: V-B **29/29
  variantes, 39 TP / 0 FP / 0 FN** em 4 PDFs/53 páginas; V-N **103 passed**,
  V-S **286 passed**, Ruff check/format **392 arquivos**, mypy **363 arquivos**;
  E02 sintético opt-in **14 TP / 1 FP / 8 FN**. V-P inferiu **11 PDFs/11
  páginas, zero falhas, 237 candidatos**; predições SHA-256
  `65304c683304aeaa40d733c2b6438abf0edcbfada117ba880f2d26399e86be75`,
  manifesto `8b2e459bfc5a98fcbf1b97efdea8358d2a7cad92456030d88ed27ebb50fa53aa`.
  Auditoria visual A7 por C fechada: 17/17 novos IDs reabertos em 8 mapas e
  8 contatos, além das três posições FP retiradas e das regiões sem saída.
  A reconciliação provou 220/220 predições legadas idênticas e 11 fontes
  intactas. Os 17 suportes restantes conservam caixa, classe e componentes
  de A6; saíram exatamente os três FP certos. Resultado restrito à ocorrência
  gráfica vetorial: **14 formas plausíveis, 3 ambíguas, 0 FP vetorial certo,
  0 FN vetorial seguro**; seis âncoras vetoriais da referência inicial seguem
  cobertas. As 14 formas não são 14 ativos físicos confirmados. Uma forma em
  quadro de detalhe ainda reporta `operational`; contexto/associação reais
  exigem revisão. O FN seguro do setor ciano raster continua contabilizado
  no V-P integral e pertence à infraestrutura E08, não a uma saída E05.
  Artefatos locais privados: `tmp/e05-simbologia/visual/comparison-a7.md`
  SHA-256 `1593f48f5e1bfef08f727a4e524d0f0d9b58dfc8818d101e23906833f73f5349`;
  `review-a7.json` `02477897381b0ea9209edf078b6961b646abc88b4f1de06143db4244c7d76345`;
  `delta-a7.json` `240c5035d3659ca75fbac8789c87fae45dff3ddfb6e1970bfd2523c46fde1e8c`;
  `reconcile-a7.json` `f9ddbf4e67f9894d551a3feaa3a0a0a20dde1c7fe43132974ad0b23df7a10638`.
- **Comandos finais efetivos (todos exit 0):**

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_pdf_coordinates.py tests/unit/test_pdf_rendering_budget.py
  .\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_transformers.py tests/unit/test_benchmark_symbols.py
  .\.venv\Scripts\python.exe -m ruff check .
  .\.venv\Scripts\python.exe -m ruff format --check .
  .\.venv\Scripts\python.exe -m mypy
  .\.venv\Scripts\python.exe -m scripts.benchmark_transformers_e05 --output tmp/e05-simbologia/benchmark-a7
  .\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --output tmp/e05-simbologia/baseline-a7
  .\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --output tmp/e05-simbologia/predictions-a7
  ```

  V-S 286 passed; V-N 103 passed; V-Q Ruff check e format 392 arquivos sem
  diferenças, mypy 363 arquivos sem erros; V-B 29/29 variantes, 39 TP/0 FP/0
  FN em 4 PDFs autorais/53 páginas; V-P 11 PDFs/11 páginas e 17/17 candidatos
  E05 inspecionados. O comando E02 sintético mede união 14 TP/1 FP/8 FN
  contra 11/1/11 E04. Scripts/runner opt-in, detector, fixtures B2–B5 e
  testes estão no workspace; `pymupdf_symbols.py`, normalizador E04,
  `category_analyzers.py` e reserva E16 ficaram sem alteração. E05 termina no
  escopo vetorial; E08 trata o FN raster, e as etapas consumidoras tratam
  contexto, associação e cardinalidade. Nenhum commit, publicação ou
  implantação foi feito.

## E06 — Reconhecimento de estais e ancoragens — #concluida

**Objetivo:** Reconhecer as variantes de estai e seus vínculos geométricos sem confundi-las com condutores.

**Por que agora:** Estai exige representação própria e usa forma/contexto distintos de equipamento pontual.

**Dependências e paralelismo:** E04. Pode ocorrer em paralelo a E05/E08/E09 após E04; não editar infraestrutura compartilhada sem coordenação.

**Subagentes e integração:**

- Subagente A — Código: detector de estais/ancoragens e geometria em módulo próprio.
- Subagente B — Testes: tracejado, contraposte, cerca, líderes e isolamento de topologia elétrica.
- Subagente C — PDFs: conferir estais/ancoragens em todas as páginas, distinguindo cabos e relações apenas possíveis.
- Coordenação e sincronização — Compartilhar representação com coordenador; testes não escrevem no detector e auditoria aguarda as saídas estáveis. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** Registro E01, contrato E03, infraestrutura E04, `application/physical_topology.py` como fronteira a preservar; novo detector de estai em `adapters/analysis/` (proposto).

**Fora de escopo:** Não transformar estai em vão elétrico nem calcular dimensionamento mecânico.

**Passos de implementação:**

1. Implementar variantes documentadas de estai MT/BT/AT e ancoragem aplicáveis; conservar subtipo desconhecido quando a figura não o resolve.
2. Representar traçado/componentes e possíveis suportes como hipóteses, sem inferir conectividade elétrica.
3. Tratar tracejado, terminações, contraposte e sobreposição com cabos conforme perfil confirmado.
4. Cobrir cercas, cotas, líderes de anotação e ligações entre postes como negativos difíceis.

**Critérios de aceite:**

- [x] Estais do inventário geram observações com geometria própria, inclusive sem texto.
- [x] Controles de estai não criam cabo, vão ou junção elétrica.
- [x] Ambiguidade de suporte/subtipo é visível e não elimina candidato visual válido.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q, V-B por variante; executar também `tests/unit/test_e14_topology.py` pelo pytest para garantir fronteira elétrica. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Estai parece condutor tracejado: usar assinatura própria e manter contexto como apoio não obrigatório.

**Prompt para uma sessão limpa:**

```text
Execute E06 — Reconhecimento de estais e ancoragens de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E04. Objetivo: Reconhecer as variantes de estai e seus vínculos geométricos sem confundi-las com condutores.
Escopo: Registro E01, contrato E03, infraestrutura E04, `application/physical_topology.py` como fronteira a preservar; novo detector de estai em `adapters/analysis/` (proposto).
Limites: Não transformar estai em vão elétrico nem calcular dimensionamento mecânico.
Aceite específico: Estais do inventário geram observações com geometria própria, inclusive sem texto. Controles de estai não criam cabo, vão ou junção elétrica. Ambiguidade de suporte/subtipo é visível e não elimina candidato visual válido.
Validação: V-S, V-N, V-Q, V-B por variante; executar também `tests/unit/test_e14_topology.py` pelo pytest para garantir fronteira elétrica. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: detector de estais/ancoragens e geometria em módulo próprio. B — Testes: tracejado, contraposte, cerca, líderes e isolamento de topologia elétrica. C — PDFs: conferir estais/ancoragens em todas as páginas, distinguindo cabos e relações apenas possíveis. Coordene assim: Compartilhar representação com coordenador; testes não escrevem no detector e auditoria aguarda as saídas estáveis. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — execução de 22/09/2026:**

- Base `f97e99376cc185c3df7a180a45625f64d9def2ca`, Git inicialmente
  limpo; nenhum `AGENTS.md` aplicável no repositório ou ancestrais. E04 A6
  estava concluída (`1.19.3:vetorial-5`, cache `1.19.3`). Foram lidos o
  roadmap, o inventário E01 (17 células E06 em §14–15), o contrato E03, o
  runner/baseline E02, o handoff E04 e a fronteira
  `application/physical_topology.py`. Esta fronteira, o normalizador E04 e
  o pacote E05 não foram editados; não houve commit.
- Delegação e propriedade: A `/root/codigo_estais` entregou somente
  `src/zeny_project_handler/adapters/analysis/pymupdf_guys.py` (SHA-256 final
  `50ab9064b94aab791d60b65d38de29de341c2d246861e0adde345992a4d1f6ce`);
  B `/root/testes_estais` entregou `tests/fixtures/guys/fixtures.py`
  (`a52d786708559208ff4476935bb99dfd4251a797f900341fbde39f7fad609d9a`),
  `tests/fixtures/guys/__init__.py` e `tests/unit/test_pymupdf_guys.py`
  (`127e7bac8c5c36790d17d2e738997c9c2cb80c106d6bbf6a929e05499b71c933`);
  C `/root/pdfs_estais` entregou somente relatórios e imagens em
  `tmp/e06-simbologia/visual/`. O coordenador integrou
  `scripts/symbol_benchmark_runner.py`, `scripts/benchmark_symbols.py`,
  `scripts/benchmark_guys_e06.py`, `tests/unit/test_benchmark_symbols.py`,
  `docs/e06-estais-ancoragens.md` e este roadmap. A passou o contrato estável
  `perfil_estais()`/`observar_estais(...)` a B antes dos testes; C recebeu
  somente checkpoints de predição completos.
- O método E03 emite classe aberta `ESTAI`, eixo `POLILINHA`, primitivas e
  componentes de origem, subtipo/referências e suportes **possíveis**,
  `vinculo=mecanico_possivel`, `conectividade_eletrica=False` e cardinalidade
  indeterminada. Os testes verificam round-trip, ambiguidade e ausência de
  cabo, vão e junção elétrica. Runner E02 opt-in `--include-guys` preserva
  candidatos exclusivos sem quórum nem probabilidade; `score` bruto não é
  calibrado. Não há dimensionamento mecânico nem promoção patrimonial.
- Checkpoints rejeitados e correção baseada em evidência: A1/B4 falhou Y
  simples (23 TP/1 FP/1 FN); A2/B4 passou autoral (24/0/0), mas V-P A2
  encontrou 20 FP claros e um ambíguo. A5/B8 passou 32/0/0, porém V-P A5
  apontou 18 FP e dois ambíguos. B9 congelou negativos autorais e reproduziu
  três FP de rosa/cor antes da correção A6; A6/B9 passou 32/0/0, mas V-P A6
  ainda reteve um FP em corredor sólido/tracejado. B10 e B11 congelaram
  negativos independentes vermelhos antes de A7 e preservaram sobreimpressão
  exata/âncora tracejada válidas. A7 eliminou o último corredor; B confirmou
  **73/73 testes E06 e 94/94 com E14**, além de Ruff/mypy. Nenhuma anotação
  ou ROI de C entrou no detector ou nas fixtures. Os relatórios A2/A5/A6 e
  deltas permanecem em `tmp/e06-simbologia/visual/`.
- **V-B final por variante:**
  `.\.venv\Scripts\python.exe -m scripts.benchmark_guys_e06 --output tmp/e06-simbologia/benchmark-a7-b11`
  retornou 0: **17/17 IDs E01, 33 TP / 0 FP / 0 FN em 67 páginas**. O runner
  persistiu predições antes de ler a referência autoral; PDF fonte SHA-256
  `87dbcef34983423c143a6ae51884c447cea320d0825268a2fc5722515e7f34c0`,
  referência `090fb2e7c57c908cb2ac6c22fbe789237ec4a3940c8d48d418f80e6d8b96d3a5`,
  predições `0e243c3a378c02b4e762740fea2ed272b89e7c4a499586f7b61086508b26816e`.
  A reserva sintética E16 não foi aberta. Baseline de desenvolvimento E02
  com `--include-transformers --include-guys` em `baseline-a7` completou
  4 PDFs/6 páginas, união bruta 14 TP/3 FP/8 FN. A taxonomia legada
  `ESTAI_MT` difere da classe aberta E03 `ESTAI`; diagnóstico **após inferência**
  `integracao/e02-taxonomy-crosswalk-a7.json` associa dois estais vetoriais,
  sem alterar o relatório bruto, tolerâncias ou o detector. O terceiro
  estai E02 é raster e permanece fora do domínio vetorial E06.
- **V-S:** `.\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_pdf_coordinates.py tests/unit/test_pdf_rendering_budget.py`
  → 286 passed, exit 0. **V-N/fronteira E14:**
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_guys.py tests/unit/test_benchmark_symbols.py tests/unit/test_e14_topology.py`
  → 143 passed, exit 0. **V-Q:** comandos separados
  `.\.venv\Scripts\python.exe -m ruff check .`,
  `.\.venv\Scripts\python.exe -m ruff format --check .` e
  `.\.venv\Scripts\python.exe -m mypy` → exit 0, 397 arquivos
  formatados, 367 arquivos sem erro de tipo. `git diff --check` sem erro.
- **V-P final:** C congelou a inspeção *antes* das predições: manifesto
  `visual/manifest.json` SHA-256
  `d494462bb6b715ae513e85c0014a8479a0936e556da352ac7e4d27a569424e13`
  e `visual/initial-observations.md`
  `4ccff208fefa17c2a6f32e833b0bab5efa80cebba36d202ba27da9d65505d596`.
  Examinou as 11 páginas renderizadas, 20 quadrantes, oito recortes e 11
  diferenças base/anotação (277 anotações). Comando
  `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --output tmp/e06-simbologia/predictions-a7`
  → 11 PDFs/11 páginas, 0 falhas, fontes intactas, 237 predições (E04 220,
  E05 17, E06 **0**). Manifesto SHA-256
  `c0be646dae120fa4ea3751ae64d060a5d4c08f1923aabf8dc8050a3036707e0b`,
  predições `f4fb7cc5e4d35cf7b478ddcd9216cf4c9ef6a14d497ea380e92dc60b61ce297d`.
  Delta A6→A7: E06 1→0, E04/E05 237 JSON idênticos, 11 fontes idênticas.
  C reabriu o recorte cru e a página inteira do último FP removido; era
  condutor entre suportes. Relatório `visual/reconciliation-a7.md` SHA-256
  `1ade38d0fdb53e668674b29434f196228600160204cd2a6b86268813cb313336`
  registra 66 células (33 base executadas, 33 anotações fora de escopo),
  **0 FP e 0 FN verificáveis** de E06 e nenhuma exclusividade E06 final.
- Limite explícito: nenhum estai operacional foi confirmado nesses 11 PDFs;
  portanto o recall real não é estimável, e os exemplos já inspecionados são
  desenvolvimento. Duas relações linha/ponto e uma foto anotada continuam
  visualmente incertas, sem promoção a positivo; 14 grupos opcionais de PDF
  foram vistos apenas no estado padrão. A conclusão valida geometria e
  negativos do corpus autoral e a precisão observável de V-P no escopo
  inspecionado, **não** sensibilidade em projetos reais com estai. Não há
  bloqueio remanescente para os critérios desta etapa.

## E07 — Pacotes extensíveis das demais famílias — #bloqueada

**Objetivo:** Entregar representação declarativa e pacotes de reconhecimento para as famílias restantes do inventário, com cobertura auditável.

**Por que agora:** Evita que o projeto termine restrito aos exemplos iniciais do pedido.

**Dependências e paralelismo:** E04, E05, E06. Pode ocorrer em paralelo a E08–E10 quando suas dependências estiverem prontas; mudanças no registro precisam de integração serial.

**Subagentes e integração:**

- Subagente A — Pacotes: implementar esquema/runner e lotes de famílias atribuídos, cada arquivo com um dono; usar ondas por família.
- Subagente B — Testes: validar esquema, cobertura E01 e positivos/negativos dos pacotes em arquivos separados.
- Subagente C — PDFs: cobrir todas as páginas por lotes, registrar famílias faltantes e impedir que símbolos informativos virem ativos.
- Coordenação e sincronização — Coordenador integra registro central serialmente; subagentes podem trabalhar em pacotes distintos com contrato congelado. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** Registro E01, infraestrutura E04, `adapters/analysis/`, dados de interpretação e `docs/schemas/`; novos pacotes de templates/gramáticas e esquema (propostos).

**Fora de escopo:** Não criar modelos comerciais nem implementar conformidade nova para cada símbolo.

**Passos de implementação:**

1. Definir pacote por perfil/família com formas/componentes, estilos de linha, variantes, exemplos negativos e metadados de fonte.
2. Cadastrar proteção/manobra/regulação, postes/estruturas, conexões/medição/iluminação, infraestrutura subterrânea e demais famílias E01; mapear geometrias informativas separadamente.
3. Adicionar runner declarativo e fallback de candidato desconhecido; pacotes poderão ser consumidos também por E08–E10.
4. Auditar a matriz completa. Se a implementação exigir vários objetivos independentes, decompor antes em E07A/E07B e demais lotes por família, cada qual com sessão e validação próprias.

**Critérios de aceite:**

- [ ] Toda família E07 do inventário E01 tem pacote verificável, mas 344 variantes em 17 famílias sem qualquer gramática e em outras famílias ainda não têm V-B positivo/negativo; pendência explícita impede o aceite integral.
- [x] Adicionar uma família por dados não exige modificar o reconciliador.
- [x] Símbolos de legenda, norte e outros informativos não são promovidos a equipamento por estarem reconhecidos.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q e V-B para cada pacote; validar esquema, fontes e cobertura contra inventário. E07 só conclui com os pacotes de todo seu escopo entregues, sem contar desconhecido como reconhecimento. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** O aceite integral original de E07 está impedido por 344/365 variantes sem gramática discriminativa e benchmark positivo/negativo, distribuídas por 17 famílias inteiramente pendentes e por variantes restantes de outras dez. A fonte F02 mostra colisões de forma entre famílias e variantes, inclusive figuras idênticas para IDs distintos; atribuição exata exige contexto/alternativas verificáveis. `scripts.audit_symbol_packages --require-complete` retorna 1 com essa contagem; V-P A5 não produziu nenhum candidato E07 real. O cadastro não é reconhecimento. **Este bloqueio histórico não é dependência de E08–E16:** E11/E12 podem consumir somente o snapshot habilitado/verificado, com pendências e alternativas explícitas, e a expansão posterior segue `docs/fluxo-curadoria-incremental-simbologia.md`. Para concluir E07 sob o critério original, criar e validar gramáticas/fixtures autorais para as variantes pendentes por ondas, conferir colisões e negativos da fonte F02, repetir o validador independente Draft 2020-12, V-B por pacote, V-P integral e V-N/V-Q no checkpoint final.

**Riscos e mitigação:** Escopo grande: lotes por família com IDs estáveis e totalizadores impedem encerramento parcial disfarçado.

O prompt E07 abaixo preserva o critério histórico de conclusão integral.
Para acrescentar PDFs e conhecimento de forma incremental, usar o prompt
one-shot do fluxo independente, sem reiniciar E01–E16 nem marcar E07 como
concluída por simples cadastro. A alternativa visual aceita pelo usuário
precisa de contrato/teste efetivo em E12/E13 antes de ser tratada como
comportamento entregue.

**Prompt para uma sessão limpa:**

```text
Execute E07 — Pacotes extensíveis das demais famílias de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E04, E05, E06. Objetivo: Entregar representação declarativa e pacotes de reconhecimento para as famílias restantes do inventário, com cobertura auditável.
Escopo: Registro E01, infraestrutura E04, `adapters/analysis/`, dados de interpretação e `docs/schemas/`; novos pacotes de templates/gramáticas e esquema (propostos).
Limites: Não criar modelos comerciais nem implementar conformidade nova para cada símbolo.
Aceite específico: Toda família E01 tem pacote verificável e testes positivos/negativos ou pendência explícita que impede o aceite integral. Adicionar uma família por dados não exige modificar o reconciliador. Símbolos de legenda, norte e outros informativos não são promovidos a equipamento por estarem reconhecidos.
Validação: V-N, V-Q e V-B para cada pacote; validar esquema, fontes e cobertura contra inventário. E07 só conclui com os pacotes de todo seu escopo entregues, sem contar desconhecido como reconhecimento. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Pacotes: implementar esquema/runner e lotes de famílias atribuídos, cada arquivo com um dono; usar ondas por família. B — Testes: validar esquema, cobertura E01 e positivos/negativos dos pacotes em arquivos separados. C — PDFs: cobrir todas as páginas por lotes, registrar famílias faltantes e impedir que símbolos informativos virem ativos. Coordene assim: Coordenador integra registro central serialmente; subagentes podem trabalhar em pacotes distintos com contrato congelado. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

### Evidências e handoff E07 — checkpoint A5, 23/09/2026

Início: `main` em `2c87d54`, Git limpo, nenhum `AGENTS.md` aplicável encontrado.
E04/E05/E06 estavam `#concluida` e seus módulos atuais conferiam com o handoff:
extrator `1.19.3`, transformadores `e05-transformadores-v4`, estais
`e06-estais-v1`. Pré-teste de dependências: 385 testes E04–E06 passaram. O Python
da `.venv` só iniciou com `require_escalated` neste host, pois o executável base
WindowsApps era inacessível no sandbox; nenhuma instalação ou modificação da
`.venv` foi feita. O inventário E01, SHA-256
`e3d49d9b0072f9f30ea98e2171c0cd520a819a15b329590cfbf35f508f042fcd`,
define **365 variantes E07 em 27 famílias** por `variants.owner_stage`, incluindo
quatro reguladores de §18 cujo `family.owner_stage` é E05. A contagem preliminar
de 28 famílias foi corrigida contra os IDs reais. O inventário global mantém
427 variantes/33 famílias: E04=12, E05=29, E06=17, E07=365 e E10=4. As quatro
E10 continuam futuras e não são contadas como reconhecimento E07. Fonte primária F02 IT-EO-008
revisão 3, 29/07/2024, e localizadores E01 foram preservados; nenhum desenho
normativo foi copiado como asset comercial.

| Frente / propriedade exclusiva | Entrega verificável |
|---|---|
| A `/root/packages` — `declarative_symbols.py`, `analysis/symbol_packages/*.json`, `docs/schemas/pacotes-simbologia.schema.json` | Esquema 1, loader estrito, observações E03, 27 arquivos/365 IDs; 12 gramáticas executáveis em oito famílias e 353 pendências. SHA-256 runner A5 `a0980a5e4ef6930d74f239c3a5f63ec2bac137de8a9e72d743961a0eb724adeb`, esquema `6da709b58cff4a7d7e8a788d096345b8b07816ac4d90ab43f8086ce1f13ec041`; hash agregado dos JSON `ad4c6de1962c91225f9098e0d88d2a41b6c03432b5a657a3abc4d57f7d187625`. |
| B `/root/package_tests` — `tests/unit/test_declarative_symbol_packages.py`, `tests/fixtures/declarative_symbols/` | Matriz independente 365/27, mutações de esquema, positivo/negativo autoral por gramática, exclusivo/vizinhos, família adicionada por dados, informativo/norte/legenda sem promoção. Teste SHA-256 `658dd74878813eaf34f541a50be215224d990a1b4688aac5c2246ff3ef916e4f`; corpus `31c508863256c68e5a8176fc46f59850f6b760a02a71e7609383e7e420b75250`. |
| C `/root/pdf_audit` — somente `tmp/e07-simbologia/visual/` | 11 PDFs/11 páginas inspecionadas visualmente antes de ver predições; manifesto `cb150f80e6d81e8f6b2440681193e7f453f2f35790b3b43784590e374f8ce459`, notas iniciais `74a75c6932ca62c5fc222e843c7da1c141ed4c9017ba064fec2df7261af1826d`, comparação A5 `ef960cf184cfc74a0d925423528d3fd7b1068b65c8ca43ca9fcef5f61cd2c76e`. |
| Coordenador `/root` — registro/integração serial em `scripts/benchmark_symbols.py`, `scripts/symbol_benchmark_runner.py`, `scripts/audit_symbol_packages.py`, `scripts/benchmark_packages_e07.py`, `pyproject.toml`, `docs/e07-pacotes-simbologia.md`, este roadmap | Opt-in `--include-packages`, manifesto por método, empacotamento dos JSON, auditoria E01 e gates integrados; o reconciliador não foi editado. |

Contrato A2 foi congelado antes dos testes e da projeção central. O checkpoint A4
foi rejeitado: B achou booleanos aceitos como inteiros no loader e V-P falhou
no primeiro PDF com `drawing.rect=None`; a execução parcial (2/11) foi
interrompida e **não** conta como V-P. A5 corrigiu ambos, adicionou teste
regressivo e foi congelado antes da inferência final. Pacotes são carregados por
dados; `enabled` exige gramática, `pending` não emite reconhecimento. O fallback
desconhecido exige região explícita, retorna `classe=None` e não aumenta cobertura
E01. `papel=informative` fica separado de equipamento, quantidade e promoção.
Scores não são probabilidades; silêncio de outros métodos não veta exclusivos.

**Validações integradas A5** (comandos na raiz, `.venv` via escalonamento de
execução do runtime existente):

| Gate/comando | Resultado |
|---|---|
| V-N: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_declarative_symbol_packages.py tests/unit/test_benchmark_symbols.py tests/unit/test_symbol_inventory.py -q -o cache_dir=tmp/e07-simbologia/pytest-cache --basetemp=tmp/e07-simbologia/final-pytest` | **132 passed**, saída 0; B isolado 45 passed. Pré-teste E04–E06: **385 passed**. |
| V-Q: `.\.venv\Scripts\python.exe -m ruff check .`; `.\.venv\Scripts\python.exe -m ruff format --check .`; `.\.venv\Scripts\python.exe -m mypy` | Todos saída 0; 404 arquivos formatados, 372 fontes sem erro. |
| Auditoria: `.\.venv\Scripts\python.exe -m scripts.audit_symbol_packages --output tmp/e07-simbologia/package-audit-a5.json` | 27/27 pacotes, 365/365 IDs, fonte/localizador/papel sem divergência, saída 0. Com `--require-complete`: **saída 1**, 12 enabled/353 pending; gate integral não passou. |
| V-B por gramática: `.\.venv\Scripts\python.exe -m scripts.benchmark_packages_e07 --output tmp/e07-simbologia/benchmark-a5` | 58 páginas autorais, 12 positivos/46 negativos em oito famílias: **12 TP, 0 FP, 0 FN, 0 duplicatas**, saída 0. As 19 famílias inteiramente pendentes não têm V-B positivo. |
| V-B regressão/composição: `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output tmp/e07-simbologia/baseline-a5` | 4 PDFs/6 páginas, 17 predições; união bruta 14 TP/3 FP/8 FN, saída 0. Nenhum positivo E07 nesse corpus E02; não é V-B dos pacotes pendentes. |
| V-P inferência: `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --include-packages --output tmp/e07-simbologia/predictions-a5` | **11 PDFs/11 páginas**, zero falhas e 11 fontes intactas; 237 predições (E04 220, E05 17, E06 0, E07 **0**), saída 0. `predictions.json` SHA-256 `045cc707265d33486b1adbd427b0ff88ab13eec03fddc5179c599cda34c3105c`; manifesto `363600250e14662f02150f909d40972634cc6e53a95371d40209d727fb492679`. |

O esquema JSON foi parseado, seus campos/estados e casos inválidos foram
exercitados pelo loader e pelos testes de mutação. Na continuação da etapa,
`jsonschema==4.25.1` foi instalado somente em `tmp/e07-simbologia/jsonschema-validator`;
o gate independente Draft 2020-12 passou para esquema, 27 pacotes/365 variantes
e rejeitou oito mutações inválidas. O relatório é
`tmp/e07-simbologia/jsonschema-gate.json`. O gate será repetido no checkpoint
final após as novas gramáticas.

**V-P visual independente:** C renderizou e viu realmente 11 visões gerais,
44 tiles ampliados com cobertura integral e 11 imagens base **antes** das
predições; não inferiu revisão visual de JSON/OCR. Depois comparou A5 com as
imagens e registrou as 88 células página × método × camada: 44 bases executadas,
44 anotações fora de domínio, nenhuma falha. As 11 sobreposições E07 são iguais
às bases, sem candidato E07. Houve **0 FP emitidos e 0 exclusivos E07**; FN e
recall reais das 12 variantes habilitadas são **não estimáveis**, pois não há
positivo F02 inequívoco delas na coleção. Postes, cabos e conexões amplos são
visíveis, mas não autorizaram rótulos de variante. Norte, detalhes, tabelas
`VÃO REGULADOR`, instruções negativas, fotos, QR, vegetação e futuro de geração
foram mantidos como contexto, não ativos. As 237 predições E04–E06 e estados
coincidem exatamente com E06 A7; sua comparação visual anterior foi reutilizada
por identidade comprovada, sem alegar nova leitura a partir de JSON. Os hashes
das 11 fontes da inspeção inicial coincidem com os de A5. Relatório por página,
ambiguidades e limites de fontes/flate estão em
`tmp/e07-simbologia/visual/reconciliation-a5.md` e `.json` (SHA-256
`b6d87a24389dd99668bca493ec2a3d87cc906ede3327f49fde9f3aacef96b5b3`).
Nenhuma referência/ROI de C entrou no algoritmo; todos os exemplos vistos são
desenvolvimento e a reserva sintética permanece lacrada até E16.

**Decisão:** E07 permanece `#bloqueada` para aceite integral. Os 27 pacotes são
auditáveis, mas 353 variantes ainda não são reconhecidas, 19 famílias não têm
qualquer positivo/negativo executável, e o V-P não demonstrou ganho real E07.
O desbloqueio exige ondas de gramáticas visuais ligadas à fonte e corpus
positivo/negativo independente para cada pacote/variante pendente, seguidas por
V-B, V-N, V-Q e V-P de toda a coleção no mesmo checkpoint. Esquema e loader
podem ser consumidos como base de desenvolvimento; não representam cobertura
homologada. Sem modelo comercial, regra nova de conformidade, commit, publicação
ou implantação.

### Evidências e handoff E07 — continuação e checkpoint integrado, 23/09/2026

A retomada começou com E07 `#em-andamento` sincronizado no índice e detalhe,
preservando os arquivos A5 sem commit. E04/E05/E06 permaneceram concluídas; o
denominador E01 continuou 365 variantes E07 em 27 famílias. A fonte primária
F02 foi obtida do URL oficial para `tmp/e07-simbologia/reference/`, sem entrar
no Git: SHA-256 `0e29f0ea81827c7235d0893c383fc993c78378c51e930b8b8228de82d564ce04`,
igual ao E01; 45 páginas. `scripts.audit_symbol_packages --source-pdf` verificou
esse hash e o intervalo das 365 páginas citadas. O validador independente
`jsonschema==4.25.1` foi instalado somente em
`tmp/e07-simbologia/jsonschema-validator`, sem mudar `.venv` ou dependências.

| Frente e dono dos arquivos | Checkpoint verificável |
| --- | --- |
| A `/root/packages` — `declarative_symbols.py`, `symbol_packages/*.json`, esquema | Ondas §6/§7/§23: CT, CL, CM com quadro rotulado; triângulo vazio/cheio; EH, SF6, BTX, BQX em painel cinza aninhado. 27 JSON/365 IDs, **21 enabled/344 pending** em 10/17 famílias; runner SHA-256 `849cc38d7a8c9cbbeae3afb769dac3435faf8c490484b126bac674657b19a40a`, esquema `6c3896da33243f35aeddbc4e2d51368cd06e8d41822962a99ae9e1c6f46cde17`. Arquivos congelados antes da inferência V-P. |
| B `/root/package_tests` — `tests/unit/test_declarative_symbol_packages.py`, `tests/fixtures/declarative_symbols/` | 69 testes dirigidos, negativos cruzados e regressão CT/X→torre, fill válido para variante irmã, snapshot do runner, 23 TP/0 FP/0 FN/0 duplicatas no corpus autoral. Teste SHA-256 `1a284a54164456b547d5902238aa5d43783f04b584ea3a4bbb0b5da4cb759153`; corpus `58600bc5cef40459acd76246c7bad38e1797ff4c2a6cc0ad7d473b3d462e716b`. |
| C `/root/pdf_audit` — somente `tmp/e07-simbologia/source-review/` e `tmp/e07-simbologia/visual/` | Fonte F02 p6–45: **40/40 páginas realmente vistas** a 300 dpi; p6–14 incluem matriz visual de 80/80 IDs e 15 recortes; relatórios `review-03-13.md` SHA-256 `453fa7f85dc6418942e9b857ce73f3ee3eeb7e9cf1ef1828d896653c3cbde9d6` e `review-14-33.md` `61d0955e82987ff6a04860a5a1f4c4ac45cd003776d227a660fc3fac8c238209`. V-P final `reconciliation-final.md` SHA-256 `d34837b189813be8aa4049e328e4a8d12372f6ad84e51952313016d4602bb053`. Nenhuma ROI do revisor entrou no runner. |
| Coordenador `/root` — scripts centrais, `docs/e07-pacotes-simbologia.md`, este roadmap | Auditoria opcional da fonte/hash/páginas, snapshot único de pacotes durante benchmark e falha explícita por drift; integração serial e gates abaixo. O reconciliador não foi alterado. |

**Decisões de fonte:** F02 p6–45 foi renderizada e aberta como imagem antes de
comparar gramáticas. Há símbolos **idênticos** para poste MT/AT (§3/§8), rota
subterrânea/galeria (§4/§5), duas caixas (§5), pórticos 2/3 (§11), cabos
aéreos/subterrâneos (§16/§17) e subtipos de equipamento (§20/§25/§32).
Nesses casos o ID exato precisa de contexto ou deve permanecer alternativa
explícita; uma forma genérica não conta como reconhecimento específico. Os
glifos das páginas F02 p9–14 e p27–33 testadas com o runner estão incorporados
como imagens e não produziram positivos vetoriais. A própria F02 p38 declara os 89 desenhos §33
sem conectividade elétrica e excluídos da publicação; imitação de equipamento
nessa seção permanece informativa. Os PNGs da fonte ficam somente em `tmp/`.

**Validações no checkpoint congelado** (comandos executados na raiz; `.venv`
existente via `require_escalated` neste host):

| Gate/comando | Resultado |
| --- | --- |
| V-N: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_declarative_symbol_packages.py tests/unit/test_benchmark_symbols.py tests/unit/test_symbol_inventory.py -q -o cache_dir=tmp/e07-simbologia/pytest-cache --basetemp=tmp/e07-simbologia/integration-pytest-bfinal` | **156 passed**, exit 0; B dirigido 69 passed. |
| V-Q: `.\.venv\Scripts\python.exe -m ruff check .`; `.\.venv\Scripts\python.exe -m ruff format --check .`; `.\.venv\Scripts\python.exe -m mypy`; `git diff --check` | Todos exit 0; 404 arquivos formatados, 372 fontes sem erro de tipo. |
| Esquema independente: `.\.venv\Scripts\python.exe tmp/e07-simbologia/validator_gate.py` | Draft 2020-12 `check_schema`, 27 pacotes/365 IDs, **13 mutações inválidas rejeitadas**, exit 0; relatório `tmp/e07-simbologia/jsonschema-gate.json`. |
| Fonte/inventário: `.\.venv\Scripts\python.exe -m scripts.audit_symbol_packages --source-pdf tmp/e07-simbologia/reference/IT-EO-008_Simbologia_EO.pdf --output tmp/e07-simbologia/package-audit-final-wave.json` | 27/365, F02 SHA E01/45 páginas/localizadores válidos, zero erros, exit 0; **21 enabled/344 pending**. O mesmo script com `--require-complete` retornou **exit 1** por 344 pendências; aceite integral falhou. |
| V-B por gramática: `.\.venv\Scripts\python.exe -m scripts.benchmark_packages_e07 --output tmp/e07-simbologia/benchmark-final-wave` | 10 famílias, 21 positivos diretos + dois fills de variante irmã, 95 negativos vazios: **23 TP/0 FP/0 FN/0 duplicatas**, exit 0. As 344 pendentes não têm V-B positivo/negativo aprovado. |
| V-B composição E02: `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output tmp/e07-simbologia/baseline-final-wave` | 4 PDFs/6 páginas, união bruta 14 TP/3 FP/8 FN, exit 0; a reserva E16 não foi aberta. |
| V-P inferência: `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --include-packages --output tmp/e07-simbologia/predictions-final-wave` | **11 PDFs/11 páginas**, 0 falhas, 11 fontes intactas, pacote sem drift, 237 predições (E04 220/E05 17/E06 0/E07 **0**), exit 0. Manifesto SHA-256 `081a8c246ff46fb4287ba91aa2ec1486cdb8e1f0dab964665c671e425c3a5949`; predições `32cc59b79cb847502ffd9fe2c02f09c15109894c97b5b896487e117dff4355ea`. |

**V-P visual final:** C reutilizou a inspeção independente *pré-predição* de
11 páginas completas, 44 tiles e 11 bases de A5; depois abriu três overlays
finais e verificou igualdade de pixels nos 11 overlays E07 contra as bases.
`tmp/e07-simbologia/visual/reconciliation-final.md` e `.json` (SHA-256
`dd56c9a0e25a8024c966e29a606bbefbd10442e43a120ca90463a375b07c2fa9`)
registram 88 células página × método × camada: 44 bases executadas e 44
anotações fora do domínio. Os 237 candidatos anteriores são semanticamente
idênticos a A5 e mantidos na união; silêncio E07 não os veta, concordância não
é probabilidade. E07 emitiu **0 FP, 0 exclusivos e 0 concordantes**; FN/recall
reais das variantes habilitadas são **não estimáveis**, pois não houve positivo
E07 inequívoco nesses PDFs. Grupos amplos, negativos informativos e ambiguidades
estão na matriz por página. JSON/OCR não foram tratados como revisão visual,
nenhuma referência do revisor entrou no algoritmo, e a reserva E16 permanece
lacrada. Os exemplos vistos continuam corpus de desenvolvimento.

**Decisão final:** E07 volta a `#bloqueada`, com o cadastro auditável e nove
gramáticas novas testadas, mas **344/365 variantes** ainda sem reconhecimento
positivo/negativo em **17 famílias inteiramente pendentes**. A fonte demonstra
colisões intrínsecas de forma e o V-P não forneceu positivo real E07; portanto
habilitar tudo por forma genérica ou contar candidato desconhecido mascararia
FP/FN. Desbloqueio: desenvolver por ondas gramáticas/alternativas com contexto
discriminante e corpus autoral por variante/família, inclusive caminho raster
quando necessário, sem promover §33; então repetir fonte/esquema, V-N/V-Q/V-B e
V-P integral no mesmo snapshot. E11/E12 não devem consumir E07 como concluída.
Nenhum commit, publicação ou implantação foi feito.

## E08 — Detector raster por templates e Hough — #concluida

**Objetivo:** Acrescentar família raster capaz de detectar símbolos sem vetores aproveitáveis.

**Por que agora:** Melhorias vetoriais não resolvem PDFs escaneados e trechos rasterizados.

**Dependências e paralelismo:** E03, E04. Pode ocorrer em paralelo a E05/E06/E09; consumir snapshots versionados dos pacotes, sem depender de código em andamento.

**Subagentes e integração:**

- Subagente A — Código: adapter raster, templates/Hough, tiles e transformação inversa.
- Subagente B — Testes: bordas de tile, rotação/escala, ruído, memória e ausência de vetores.
- Subagente C — PDFs: confrontar páginas raster/mistas e vetoriais em toda a coleção, documentando exclusivos e falsos positivos.
- Coordenação e sincronização — Fixtures e inspeção original podem avançar em paralelo; comparação com vetor/união aguarda o mesmo checkpoint de saídas. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `adapters/analysis/`, `ports/analysis.py`, `adapters/pdf/`, registro E01 e pacotes disponíveis; adapter OpenCV e dependências opcionais são propostos, não runtime padrão atual.

**Fora de escopo:** Não usar as caixas do detector vetorial como única área de busca nem adicionar OCR como falso detector independente.

**Passos de implementação:**

1. Criar varredura de página por tiles sobrepostos com transformação inversa, controle de memória e regiões de busca independentes.
2. Implementar correlação multiescala/rotação e ensaio Hough generalizado para templates verificados; registrar ambos como métodos/variantes com origem compartilhada.
3. Preservar candidatos exclusivos e deduplicar bordas de tiles sem apagar ocorrências próximas.
4. Documentar dependências/versionamento e ganho por estrato; templates novos de E07 devem entrar pelo registro.

**Critérios de aceite:**

- [x] PDF raster sem vetores produz candidatos corretos que o legado perde.
- [x] Símbolo na borda do tile mantém caixa na página e uma hipótese, com observações preservadas.
- [x] Variação de DPI/rotação não gera votação independente nem score declarado probabilidade.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q, V-B comparando vetor, raster e união; avaliar página vazia, ruído, templates parecidos e saturação de candidatos. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Templates sensíveis ao estilo: manter múltiplas fontes e não usar um filtro vetorial obrigatório antes da busca.

**Prompt para uma sessão limpa:**

```text
Execute E08 — Detector raster por templates e Hough de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E03, E04. Objetivo: Acrescentar família raster capaz de detectar símbolos sem vetores aproveitáveis.
Escopo: `adapters/analysis/`, `ports/analysis.py`, `adapters/pdf/`, registro E01 e pacotes disponíveis; adapter OpenCV e dependências opcionais são propostos, não runtime padrão atual.
Limites: Não usar as caixas do detector vetorial como única área de busca nem adicionar OCR como falso detector independente.
Aceite específico: PDF raster sem vetores produz candidatos corretos que o legado perde. Símbolo na borda do tile mantém caixa na página e uma hipótese, com observações preservadas. Variação de DPI/rotação não gera votação independente nem score declarado probabilidade.
Validação: V-S, V-N, V-Q, V-B comparando vetor, raster e união; avaliar página vazia, ruído, templates parecidos e saturação de candidatos. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: adapter raster, templates/Hough, tiles e transformação inversa. B — Testes: bordas de tile, rotação/escala, ruído, memória e ausência de vetores. C — PDFs: confrontar páginas raster/mistas e vetoriais em toda a coleção, documentando exclusivos e falsos positivos. Coordene assim: Fixtures e inspeção original podem avançar em paralelo; comparação com vetor/união aguarda o mesmo checkpoint de saídas. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — execução de 23/09/2026, checkpoint A5:**

- Base Git `2ebe388`, `main`, árvore inicialmente limpa; nenhum `AGENTS.md`
  aplicável. E03 e E04 foram conferidas como `#concluida`, inclusive contrato
  E03, round-trip e regressão E04. E07 está `#bloqueada` em sua meta histórica,
  mas não é dependência de E08; nenhum pacote novo foi inventado. Foram lidos
  roadmap integral, registro E01, E02, escopo e diffs antes da implementação.
  Reserva sintética `tests/fixtures/symbols/reserve.sealed.zip` não foi aberta
  (SHA-256 somente: `6874d0585269a0a68397319268076e8e788aff64fc2bc5d776e80efca739be7b`).
- Propriedade/delegação: A `/root/a_codigo` editou somente
  `src/zeny_project_handler/adapters/analysis/raster_symbols.py` (A5 SHA-256
  `568f86cae2785c2a4506fef6c6d467cbe5301ae5dd3e8ef7c2d79995ab8cecbd`);
  B `/root/b_testes` editou somente `tests/unit/test_raster_symbols.py`
  (`051b76fb5eee09b402c858021058c195085a187d244e07f261bee1edbb5bc797`);
  C `/root/c_pdfs` editou somente `tmp/e08-simbologia/visual/` e inspecionou
  fontes/imagens antes de ver predições. O coordenador editou o runner opt-in,
  CLI, `tests/unit/test_benchmark_raster.py`, `docs/e08-detector-raster.md`
  e este roadmap. B recebeu contrato A estável; C aguardou o mesmo checkpoint
  completo para comparar vetor, raster e união. A revisão A/B independente está
  em `tmp/e08-simbologia/b/revisao-a5.md`; não houve commit.
- `raster_symbols.py` versão `e08-raster-3`: varredura completa da página base
  em tiles sobrepostos, transformação inversa, agrupamento de bordas e
  escala/rotação com observações preservadas; não depende de caixas vetoriais,
  OCR ou regiões do revisor. A busca por template e o ensaio Generalized Hough
  Ballard compartilham raster/templates e portanto não são votos independentes.
  OpenCV/NumPy não estão na `.venv`; Hough retorna `INDISPONIVEL`, nunca falso
  recall medido. Scores são similaridade/votos brutos, não probabilidade.
  Os dois templates embarcados são controles autorais E02 de `ATERRAMENTO` e
  `PARA_RAIOS_MT`, com hashes no perfil, sem equivalência normativa E01. Os
  limites de tile, bytes, propostas e candidatos sinalizam `FALHA` se a busca
  ficar parcial. O runner E02 só ativa raster com `--include-raster`; baseline
  legado permanece igual, exclusivos entram na união sem quórum.
- Checkpoints rejeitados: A3 usava uma única âncora e perdeu símbolo com pixel
  apagado (B reproduziu); A4 corrigiu esse caso, mas V-P A4 terminou 11/11
  documentos com **1 página falha** (`1251386294.pdf` p1, foto densa,
  `Limite de candidatos/picos alcançado`, 136 s) e B reproduziu saturação
  indevida em raster todo preto. A5 aplica o mesmo predicado coarse de 16
  amostras escuras e 16 claras em máscaras Pillow nativas **antes** de contar
  propostas. B comparou 5.760 janelas válidas/80 imagens aleatórias contra o
  predicado Python anterior: zero divergências. A página problemática passou
  em 65,991 s, `NAO_DETECCAO` completo/0 candidatos; o negativo todo preto
  também passou, enquanto saturação real com limite baixo ainda gera `FALHA`.
- **V-S final:** `.\.venv\Scripts\python.exe -m pytest tests/unit/test_pymupdf_analyzer.py tests/unit/test_pdf_coordinates.py tests/unit/test_pdf_rendering_budget.py -q`
  → 286 passed, exit 0. **V-N final:**
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_raster_symbols.py tests/unit/test_benchmark_symbols.py tests/unit/test_benchmark_raster.py -q`
  → 66 passed, exit 0. **V-Q:** comandos separados
  `.\.venv\Scripts\python.exe -m ruff check .`, `.\.venv\Scripts\python.exe -m ruff format --check .`,
  `.\.venv\Scripts\python.exe -m mypy` → exit 0, 407 arquivos formatados,
  375 fontes sem erro de tipo.
- **V-B final:** `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e08-simbologia/baseline-a5`
  e `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e08-simbologia/benchmark-a5 --include-raster`
  → exit 0, 4 PDFs/6 páginas/zero falhas. Vetor 11 TP/1 FP/11 FN,
  template 9 TP/1 FP/13 FN, união bruta 13 TP/9 FP/9 FN. Os dois TP
  exclusivos do raster (`dev-raster-p1-o00/o01`) estão em PDF sem desenhos
  vetoriais; o legado os perde. Os 7 FP adicionais de união são caixas
  quase coincidentes que o avaliador E02 não funde, e há 1 FP de legenda do
  template. IDs/proveniência de assinatura diferem de A4 pela versão, mas
  22 predições semânticas ficaram iguais. Hough indisponível não entra como
  comparação de desempenho observada. Reserva E16 continuou lacrada.
- **V-P final:** `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e08-simbologia/vp-raster-a5 --include-raster`
  → exit 0, `completed=true`, **11 PDFs/11 páginas, zero falhas**, 220
  candidatos vetoriais, zero template, Hough `INDISPONIVEL` nas 11 bases;
  união bruta = 220 vetoriais. C congelou `visual/initial-review.md`
  (`ec8553b9db800b1be6adee3462a29ff0de70cdb1caf00ad4581384e8c7694217`)
  antes de ler saídas; abriu realmente 66 imagens originais (11 aparência,
  11 base, 44 quadrantes) e, depois, 23/23 folhas de contato dos 220
  candidatos. `visual/manifest.json` SHA-256
  `f0d01918bb5d446dbfcd52d59539e7c48d6489f723551fe1962131501c8526bf`;
  `visual/reconciliation-a5.md` SHA-256
  `43a80b9c86c83a633beec67ecfccb5564bdc65451fa63924ac8a74365f31541b`;
  `visual/checkpoint-summary.json` SHA-256
  `882628feec7065f4a7a804c38b8e5c18ed4c32c0c469ab9ca476d4ea758f0a88`.
  Comandos novos C: `.\.venv\Scripts\python.exe tmp/e08-simbologia/visual/render_manifest.py`,
  `.\.venv\Scripts\python.exe tmp/e08-simbologia/visual/verify_visual.py` e
  `.\.venv\Scripts\python.exe tmp/e08-simbologia/visual/review_predictions.py tmp/e08-simbologia/vp-raster-a5 --vector-reference tmp/e08-simbologia/vp-vector`
  → exit 0; `verify_visual.py` reportou
  `sources=11 pages=11 full_coverage_tiles=44 hashes_ok=true` e
  `review_predictions.py` `pages=11 predictions=220 contact_sheets=23`;
  11/11 hashes de fonte coincidem com o runner antes/depois; predições A5
  SHA-256 `e7acb83c7e9b884cc3db452fd30366c241111ff8a1f822cfd5c96a6f844994b7`.
  O vetor do mesmo checkpoint reproduziu 220 predições/estados de `vp-vector`;
  a matriz cobre cada página, método e camada. C localizou FP vetoriais claros
  em `1232321190` #7, `1250771080` #4, `1251386294` #18 e `1256407599`
  #4; terra visível sem hipótese raster em `1250771080`, `1250832231` e
  `1256407599`. Classes/ocorrências sobrepostas e detalhes repetidos ficaram
  ambíguos, sem TP/FP/FN exatos inventados. Nenhuma folha real é raster puro;
  todas têm redes vetoriais, embora haja fotos/bitmaps. Assim V-P não comprova
  sensibilidade em raster real local; o ganho sem vetores é do desenvolvimento
  sintético V-B, e não há precisão/recall real declarado. OpenCV opcional não
  foi executado. Os exemplos vistos são desenvolvimento, não reserva cega;
  a reserva E16 permaneceu lacrada. A inferência A5 somou 552,19 s nos 11 PDFs
  (máximo 142,92 s em `1250771080`), uma limitação de desempenho para corpus
  maiores, sem omitir páginas ou atenuar os limites. O pico `tracemalloc` do runner exclui busca
  raster e memória nativa; tempo inclui a busca completa. Ver também
  `docs/e08-detector-raster.md`.

## E09 — Detector por contornos e grafo de traços — #concluida

**Objetivo:** Implementar alternativa estrutural de reconhecimento de formas distinta de correlação de pixels e das heurísticas legadas.

**Por que agora:** Recupera símbolos deformados, quebrados ou com estilo diferente, oferecendo diversidade efetiva.

**Dependências e paralelismo:** E03, E04. Pode ocorrer em paralelo a E05/E06/E08; separar detector, fixtures e benchmark por método.

**Subagentes e integração:**

- Subagente A — Código: detector de contornos/esqueleto/grafo em adapter próprio.
- Subagente B — Testes: deformações, traços quebrados, limites combinatórios e não interferência na topologia elétrica.
- Subagente C — PDFs: verificar detecções estruturais e omissões em todos os PDFs, com evidência de acertos/erros compartilhados.
- Coordenação e sincronização — Não alterar primitives compartilhadas sem coordenação; grafo e testes têm arquivos distintos, validação final usa outputs congelados. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** Novo adapter de análise (proposto), E03/E04 e F05; `scripts/experiments/global_graph.py` apenas como antecedente de infraestrutura, não detector de símbolos pronto.

**Fora de escopo:** Não substituir a topologia elétrica pelo grafo visual nem exigir aprovação do vetor/raster.

**Passos de implementação:**

1. Extrair contornos/esqueleto e primitives locais por fonte, formando grafo de junções, extremidades, ciclos e relações angulares.
2. Comparar subestruturas/descritores com gramáticas E01 e pacotes E07 habilitados, quando houver; tolerar lacunas limitadas e registrar penalidades sem exigir cobertura E07 completa.
3. Limitar busca combinatória com orçamento explícito; falha/abstenção preservam a observação dos demais.
4. Medir erros correlacionados quando o grafo reutilizar primitives E04 e ganhos de sua entrada raster independente.

**Critérios de aceite:**

- [x] Casos autorais de traços quebrados/deformados têm acerto exclusivo; a adoção experimental foi rejeitada diante dos FP reais, com ação de melhoria registrada.
- [x] Grafos visuais não criam junções elétricas automaticamente.
- [x] A medição distingue diversidade algorítmica de entrada compartilhada.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q, V-B e teste de limite/falha em grafo denso; executar controles de símbolos semelhantes e de componentes separados. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios e decisão:** a etapa experimental encerrou seus gates no checkpoint A2;
o método continua opt-in e **não foi aprovado para adoção operacional**. Três FP
reais compartilhados com o legado e zero acerto exclusivo real exigem novos
negativos/descritores e outra V-B/V-P antes de qualquer ativação. A rejeição
documentada é o caminho de aceite experimental previsto acima, sem converter
FP em sucesso de detecção ou esconder limitações da coleção.

**Riscos e mitigação:** Explosão combinatória ou confusão de topologias simples: limitar regiões/expansões e reportar incompletude, sem silêncio.

**Prompt para uma sessão limpa:**

```text
Execute E09 — Detector por contornos e grafo de traços de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E03, E04. Objetivo: Implementar alternativa estrutural de reconhecimento de formas distinta de correlação de pixels e das heurísticas legadas.
Escopo: Novo adapter de análise (proposto), E03/E04 e F05; `scripts/experiments/global_graph.py` apenas como antecedente de infraestrutura, não detector de símbolos pronto.
Limites: Não substituir a topologia elétrica pelo grafo visual nem exigir aprovação do vetor/raster.
Aceite específico: Casos de traços quebrados/deformados têm acertos exclusivos identificados ou rejeição experimental documentada com ação de melhoria. Grafos visuais não criam junções elétricas automaticamente. A medição distingue diversidade algorítmica de entrada compartilhada.
Validação: V-N, V-Q, V-B e teste de limite/falha em grafo denso; executar controles de símbolos semelhantes e de componentes separados. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: detector de contornos/esqueleto/grafo em adapter próprio. B — Testes: deformações, traços quebrados, limites combinatórios e não interferência na topologia elétrica. C — PDFs: verificar detecções estruturais e omissões em todos os PDFs, com evidência de acertos/erros compartilhados. Coordene assim: Não alterar primitives compartilhadas sem coordenação; grafo e testes têm arquivos distintos, validação final usa outputs congelados. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — 24/09/2026, checkpoint A2:**

- Base `9f94cb469a679510e28ddf1ef89d213b3321b492`, `main`, `git status`
  e diffs de trabalho/staged inicialmente vazios; nenhum `AGENTS.md` aplicável
  encontrado nos ancestrais/escopo. E03/E04 estavam `#concluida`, conferidas
  contra contrato E03, código e handoffs A1/A6; `global_graph.py` foi lido só
  como antecedente e F05 [contornos OpenCV](https://docs.opencv.org/4.13.0/d5/d45/tutorial_py_contours_more_functions.html)
  como referência técnica. E07 bloqueada historicamente não é dependência.
  O índice e este detalhe foram marcados `#em-andamento` no início.
- Propriedade e delegação efetivas: A `/root/e09_code` editou somente
  `src/zeny_project_handler/adapters/analysis/structural_symbols.py`; B
  `/root/e09_tests`, somente `tests/unit/test_structural_symbols.py`; C
  `/root/e09_pdfs`, somente `tmp/e09-simbologia/visual/`. O coordenador editou
  `scripts/benchmark_symbols.py`, `scripts/symbol_benchmark_runner.py`,
  `tests/unit/test_benchmark_structural.py`,
  [documento E09](e09-detector-estrutural.md), este roadmap e
  `tmp/e09-simbologia/integracao/verify_checkpoint.py`. Nenhuma primitive
  compartilhada, topologia elétrica, reserva, DTO público ou arquivo de PDF
  fonte foi editado. A/B/C retornaram hashes, comandos, casos e limitações;
  B revisou A sem editar seu módulo. O Python da `.venv` exigiu execução
  escalada porque o launcher WindowsApps negava acesso no sandbox; não houve
  instalação nem modificação da `.venv`.
- Checkpoint A1 foi **rejeitado**: havia grafo de corridas axiais, mas não
  esqueleto/contorno real. Sua V-P completa identificou três FP em marcadores
  de divisa, compartilhados com o legado. A2 (`e09-stroke-graph-2`, adapter
  SHA-256 `88d5abe6e35d01b7668f2b3bb39136c5c052825bdbe3eac5f6e66735fd852880`)
  acrescenta thinning Zhang-Suen em recorte raster proposto pelo algoritmo,
  limitado a 16.384 pixels e ao orçamento global de expansões. Junções e
  extremidades do esqueleto condicionam aceite; ramificações afetam score
  bruto. A busca vetorial permanece separada; perfis declaram família comum
  e origens correlacionadas a E04/E08. O token raster compartilhado nomeia
  a origem de renderização PyMuPDF, **não** identidade de pixels: E09 usa
  página inteira cinza, E08 tiles RGB. A assinatura distingue entrada, DPI,
  limites, versão e algoritmo local. Ambos são opt-in; nenhum score é
  probabilidade ou voto por concordância.
- **V-N final A2:** `.\.venv\Scripts\python.exe -m pytest tests/unit/test_structural_symbols.py tests/unit/test_benchmark_structural.py tests/unit/test_e14_topology.py tests/unit/test_topology_compliance.py -q`
  → **65 passed**, exit 0 (15 detector, 2 runner, 48 topologia). B testou
  traços quebrados, inclinação/espessura, três/quatro barras, componentes
  separados e orçamento de grafo denso com `FALHA` explícita. No raster
  autoral a 144 DPI, E09 achou um aterramento de haste quebrada com caixa
  completa; legado e E08 ficaram silenciosos. Ablação da junção do esqueleto
  retirou o positivo inclinado. `detectar_vaos` antes/depois ficou idêntico:
  junções visuais não viraram junções elétricas. B SHA-256 final
  `5602dd4fd494dacea61e9a1bbc620c58b3da324ed44e85f380746e5759337f28`.
- **V-Q final A2:** `.\.venv\Scripts\python.exe -m ruff check .` → exit 0;
  `.\.venv\Scripts\python.exe -m ruff format --check .` → exit 0,
  410 arquivos formatados; `.\.venv\Scripts\python.exe -m mypy` → exit 0,
  378 fontes sem erro. `git diff --check` → exit 0. Esses gates foram
  reexecutados pelo coordenador no checkpoint congelado A2.
- **V-B final A2:** `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e09-simbologia/baseline-a2`;
  `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e09-simbologia/structural-a2 --include-structural`;
  `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e09-simbologia/comparison-a2 --include-structural --include-raster`
  → todos exit 0, 4 PDFs/6 páginas/zero falhas. Legado 11 TP/1 FP/11 FN;
  grafo raster 3 TP/0 FP/19 FN; grafo vetor 7 TP/2 FP/15 FN;
  template E08 9 TP/1 FP/13 FN. O Hough estava indisponível por ausência
  de OpenCV, não recebeu recall medido. Ambos grafos tiveram **zero TP
  exclusivo** nesse corpus; união com E08+E09 13 TP/13 FP/9 FN, ante
  13/9/9 com E08 sem E09. FP adicionais de união incluem caixas quase
  coincidentes contadas separadamente pelo avaliador E02. O exclusivo
  quebrado/inclinado é controle autoral a 144 DPI; o runner usa 72 DPI,
  diferença assinada e não tratada como votação independente.
- **V-P final A2:** `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e09-simbologia/vp-a2 --include-structural`
  → exit 0, `completed=true`, **11 PDFs/11 páginas, zero falhas**, 220
  predições legadas, três grafo vetor, zero grafo raster; 33/33 células base
  executadas e 33/33 annotation fora de escopo. Manifesto SHA-256
  `7642d72713953df71b6e69cc05938571427cfe2e5d40a9ab2a9144f96c506a5c`,
  predições `f7219e3a62b9aab12e0c06e7e806eb56ee2b2e9d880e8cfe4371d87d857dde5f`.
  O verificador novo `.\.venv\Scripts\python.exe tmp/e09-simbologia/integracao/verify_checkpoint.py`
  → exit 0: 66 células, 11 fontes intactas, 220 legados com classe/caixa
  idênticas ao E08 A5 congelado. Código E04/E08 e 11 hashes PDF coincidiram
  com A5, portanto a revisão de seus 220 recortes foi **reutilizada**, não
  reivindicada como inspeção nova. Inferência dos 11 documentos somou 296,01 s;
  telemetria é `tracemalloc`, sem medir RSS/MuPDF nativo.
- C abriu realmente 11 imagens originais antes de qualquer predição, depois
  recortes ampliados; leitura inicial congelada SHA-256
  `58949d57c2f97499ee37cc8e199d04053fa4a29a4ab453276780c6f7a3c2425f`.
  Na revisão A2 reabriu 3/3 contatos de candidatos e 2/2 omissões mínimas.
  [Relatório A2 privado](../tmp/e09-simbologia/visual/reconciliation-a2.md)
  SHA-256 `b573174b4b9325b56e593465b85fcf2741473bdc93833b6b5716959c5dc9ccdb`;
  comparação `frozen-comparison-a2.json` SHA-256
  `c04ded91c22afeee47ae3516f51fe7a1a9d057486be1e9581497ec025e21826a`.
  A1→A2: **zero candidatos espaciais novos/removidos**, três correspondências;
  IDs mudaram por versão. Os três candidatos vetoriais A2 são FP de
  `ATERRAMENTO` em `5 FL DIVISA` (1251386294) e `CERCA DIVISA`/`4FF`
  (1256407599), sobrepostos a FP legados com IoU 0,9990/0,9939/0,9446:
  **erro compartilhado da entrada vetorial, zero TP exclusivo real**.
  Há pelo menos duas omissões visuais de terra (1250771080 e 1256407599),
  sem denominador exaustivo para recall real. Ambiguidades, detalhes repetidos
  e negativos de árvores/cerca/glifos permanecem registrados, não convertidos
  em acertos. Silêncio alheio não vetou candidatos; a rejeição decorre da
  imagem e do contexto positivo de divisa.
- **Decisão e próximo passo:** os critérios da *etapa experimental* estão
  cobertos por exclusivo autoral, isolamento topológico, medição por entrada
  e **rejeição documentada** após V-P. E09 fica `#concluida` como experimento,
  não como método homologado: não ativar na composição operacional. Uma
  revisão futura deve criar negativos autorais de cerca/divisa, melhorar a
  discriminação estrutural e avaliar raster em resolução adaptativa, depois
  repetir V-N/V-B/V-P antes de ativar. Curvas, rotações arbitrárias, BT e
  E07 seguem fora da gramática; imagens reais são desenvolvimento, não teste
  cego. Reserva E16 permaneceu lacrada (SHA-256 opaco
  `6874d0585269a0a68397319268076e8e788aff64fc2bc5d776e80efca739be7b`).
  Nenhum commit, publicação ou implantação foi feito.

## E10 — Adaptação à legenda e símbolos desconhecidos — #concluida

**Objetivo:** Usar a legenda do próprio documento como fonte local de templates/semântica e oferecer desconhecidos revisáveis.

**Por que agora:** Convenções externas e variantes novas não cabem numa lista fixa de desenhos.

**Dependências e paralelismo:** E03, E08. Pode ocorrer em paralelo a E07/E09/E11 quando dependências permitirem; alterações no OCR compartilhado exigem coordenação.

**Subagentes e integração:**

- Subagente A — Código: pareamento de legenda, templates documentais e desconhecidos em módulos atribuídos.
- Subagente B — Testes: isolamento por projeto, legenda ausente/trocada, revisões e prevenção de vazamento.
- Subagente C — PDFs: conferir todas as legendas e ocorrências fora delas em todos os PDFs/páginas, inclusive páginas sem legenda.
- Coordenação e sincronização — OCR compartilhado e registro central ficam sob integração do coordenador; validador não fornece ROIs ao algoritmo. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `adapters/analysis/`, `rapid_evidence.py`, evidências nativas/OCR, registro E01 e detector E08; módulo de legenda e repetição visual (proposto).

**Fora de escopo:** Não treinar globalmente com uma correção isolada nem promover exemplares da legenda como ativos.

**Passos de implementação:**

1. Localizar legendas e pares símbolo/descrição por layout, conservando OCR e incerteza de pareamento.
2. Extrair template de escopo documental e procurar ocorrências fora da legenda sem consultar a referência de avaliação.
3. Agrupar motivos visuais repetidos desconhecidos como sugestões locais, sem inventar nome/catálogo.
4. Manter conflitos entre legenda, perfil e revisão; correções têm escopo, autor e versão antes de serem reutilizadas.

**Critérios de aceite:**

- [x] Convenção local não cadastrada pode gerar candidato através da legenda, com origem e descrição revisáveis.
- [x] Legenda ausente ou OCR errado não veta candidatos dos demais motores.
- [x] Símbolo da legenda não vira ativo; template não vaza para outros projetos nem para a reserva.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q, V-B em casos com/sem legenda, descrição trocada, múltiplas legendas e revisões; inspecionar isolamento por documento. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios e aceite final E10:** nenhum bloqueio remanescente nos critérios
específicos. V-N demonstra o caminho positivo de legenda em PDFs autorais;
V-P cobre integralmente os 11 PDFs reais disponíveis, todos sem legenda formal.
A sensibilidade real de pareamento permanece não medida, e OCR neural opcional
ficou indisponível no ambiente, sem veto aos demais motores. Essas limitações
não são apresentadas como validação positiva de campo.

**Riscos e mitigação:** Propagação de rótulo errado: conservar pareamento incerto e impedir aprendizado global automático.

**Prompt para uma sessão limpa:**

```text
Execute E10 — Adaptação à legenda e símbolos desconhecidos de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E03, E08. Objetivo: Usar a legenda do próprio documento como fonte local de templates/semântica e oferecer desconhecidos revisáveis.
Escopo: `adapters/analysis/`, `rapid_evidence.py`, evidências nativas/OCR, registro E01 e detector E08; módulo de legenda e repetição visual (proposto).
Limites: Não treinar globalmente com uma correção isolada nem promover exemplares da legenda como ativos.
Aceite específico: Convenção local não cadastrada pode gerar candidato através da legenda, com origem e descrição revisáveis. Legenda ausente ou OCR errado não veta candidatos dos demais motores. Símbolo da legenda não vira ativo; template não vaza para outros projetos nem para a reserva.
Validação: V-N, V-Q, V-B em casos com/sem legenda, descrição trocada, múltiplas legendas e revisões; inspecionar isolamento por documento. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: pareamento de legenda, templates documentais e desconhecidos em módulos atribuídos. B — Testes: isolamento por projeto, legenda ausente/trocada, revisões e prevenção de vazamento. C — PDFs: conferir todas as legendas e ocorrências fora delas em todos os PDFs/páginas, inclusive páginas sem legenda. Coordene assim: OCR compartilhado e registro central ficam sob integração do coordenador; validador não fornece ROIs ao algoritmo. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff — execução de 24/09/2026, checkpoint E10-final:**

- Base Git `a6ecd1d9bf80522393eeb7a298a2f532f694be21` em `main`, árvore
  inicialmente limpa; nenhum `AGENTS.md` aplicável no projeto/ancestrais.
  Roadmap, escopo, `git status/diff` e handoffs E03/E08 foram conferidos antes
  da edição. E03 e E08 tinham aceite `#concluida`; E07 bloqueada não é
  dependência de E10. Índice e detalhe foram sincronizados em `#em-andamento`
  no início. Nenhuma alteração preexistente foi sobrescrita.
- Delegação/propriedade: A `/root/codigo_legenda` editou só
  `src/zeny_project_handler/adapters/analysis/legend_symbols.py` (SHA-256
  `86adae46ab2edb5a124da939eeff4eae37c7750231d4ad2c4221c7bbca441c36`);
  B `/root/testes_legenda` editou só `tests/unit/test_legend_symbols.py`
  (`1432ada40ba337a20b54f0710488f77f6077f87612dc4dc7a94b99cf13386bf7`);
  C `/root/auditoria_pdfs` editou só `tmp/e10-simbologia/visual/` e congelou
  inspeção das imagens originais antes de conhecer predições. O coordenador
  editou `rapid_evidence.py`, runner/CLI, `tests/unit/test_rapid_evidence.py`,
  `tests/unit/test_benchmark_legend.py`,
  [`e10-adaptacao-legenda.md`](e10-adaptacao-legenda.md) e este roadmap.
  Contrato A (`observar_legenda_documental`, `LeituraLegenda`, resultado E03)
  foi entregue a B/runner antes do checkpoint; OCR compartilhado e saída central
  ficaram na integração. B revisou independentemente o runner e apontou que o
  orçamento OCR era checado depois de renderizar. O coordenador corrigiu para
  recusar antes de `get_pixmap`, adicionou teste, e B verificou a correção
  read-only (5 testes OCR passaram). Nenhuma ROI do revisor alimentou o método.
- Implementação: versão `e10-legend-documental-1`, método opt-in
  `document-local-legend`. Texto nativo e leitura OCR local opcional formam
  pares desenho/descrição com origem, revisão e pareamento incerto; busca por
  tiles encontra repetições fora do conteúdo real da legenda. Sem cabeçalho,
  pequenas imagens embutidas repetidas no próprio documento podem sugerir
  motivo desconhecido. Observações têm classe `None`, score bruto e SHA do PDF;
  exemplares não se tornam ativos, não são adicionados a E01/E08 e não têm
  cache global. O runner guarda desconhecidos em `local_candidates` fora das
  métricas fechadas E02, preservando os demais candidatos e os exclusivos.
  OCR errado/indisponível apenas deixa diagnóstico/alternativas revisáveis.
- **V-N final:** `.\.venv\Scripts\python.exe -m pytest tests/unit/test_legend_symbols.py tests/unit/test_benchmark_legend.py tests/unit/test_rapid_evidence.py -q`
  (mesma invocação dos testes novos/afetados) → 15 passed, exit 0; controles
  autorais cobrem legenda positiva e exemplar excluído, página sem legenda,
  descrição OCR conflitante, múltiplas legendas/revisões, ocorrência abaixo da
  legenda, repetição local, documento/projeto isolado, orçamento e falha OCR.
  `.\.venv\Scripts\python.exe -m pytest tests/unit/test_raster_symbols.py tests/unit/test_benchmark_raster.py -q`
  → 17 passed, exit 0. **V-Q final:** `.\.venv\Scripts\python.exe -m ruff check .`,
  `.\.venv\Scripts\python.exe -m ruff format --check .` e
  `.\.venv\Scripts\python.exe -m mypy` → três exits 0, 413 arquivos
  formatados e 381 fontes sem erro. O Python da `.venv` exigiu
  `require_escalated` porque no sandbox seu WindowsApps retornava acesso
  negado; fora do sandbox executou Python 3.13.14 sem instalar dependências.
- **V-B final:** `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e10-simbologia/vb-legacy`
  e `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e10-simbologia/vb-e10-final --include-raster --include-legend --legend-ocr`
  → exits 0; 4 PDFs/6 páginas/zero falhas. Vetor legado conservou
  11 TP/1 FP/11 FN nas duas execuções; E08 template 9 TP/1 FP/13 FN;
  união fechada E02 13 TP/9 FP/9 FN, preservando dois acertos exclusivos
  raster. O corpus E02 não contém legenda formal positiva e emitiu zero
  `local_candidates`; os casos positivos/negativos E10 ficam nos testes
  autorais dirigidos e no teste de integração do runner, não são apresentados
  como ganho mensurado pela métrica E02. Hough/OpenCV e RapidOCR não estão
  instalados; estados/diagnósticos permaneceram explícitos. A reserva
  `reserve.sealed.zip` não foi aberta e mantém SHA-256
  `6874d0585269a0a68397319268076e8e788aff64fc2bc5d776e80efca739be7b`.
- **V-P final:** `.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e10-simbologia/vp-final --include-raster --include-legend --legend-ocr`
  → exit 0, `completed=true`, 11 PDFs/11 páginas, zero falhas e 11/11
  fontes intactas. `predictions.json` SHA-256
  `b1d14f58fa9a46a9bf85ee5aff3f5da6b3904891732e8ba62b5dd75289a056cf`;
  `manifest.json` SHA-256
  `4951eb834fdd7af19a09c4511ff60e428c4019fe2b76c4bad682cdd9a5704225`.
  C abriu 11 imagens integrais, 44 quadrantes e 9 recortes **antes** de ler
  predições, depois 11 overlays. Encontrou zero legendas formais, zero pares
  e zero candidatos E10; OCR opcional indisponível em 11/11 páginas não vetou
  220 candidatos vetoriais exclusivos. Template executou 11/11 e emitiu zero;
  Hough foi indisponível 11/11. Os 220 registros E02 são idênticos ao E08 A5
  (`observations_sha256` igual a
  `2726ee241edd66670b8be546894c5d9bccef56d2dbbcac307852e8462c1444c3`),
  com fontes, versões e assinaturas iguais; C reutilizou o julgamento anterior
  de 23/23 folhas de contato com vínculo verificável. A matriz 11 páginas ×
  4 métodos × 2 camadas = 88 células e FP/FN/ambiguidades por página estão em
  `tmp/e10-simbologia/visual/reconciliation-final.md` (SHA-256
  `314ab2e33b712b4ddeddde2705a203040414874285ee4353ab71140dc5a14e55`),
  com 11/11 PDFs e páginas conferidos, zero bloqueados. Há FP vetoriais claros
  e omissões de template já existentes em E08; nenhum erro novo do método E10
  foi observado. Não há positivo real de legenda para estimar sensibilidade,
  OCR real não executou e recall real por classe não é adjudicável; V-P não
  é apresentado como homologação de campo.
- Limites/próximo passo: fallback desconhecido cobre apenas imagens embutidas
  pequenas repetidas, não motivos vetoriais arbitrários; OCR opcional ausente
  neste ambiente e rótulo de legenda continua hipótese revisável. E12 fará
  reconciliação/calibração e E14 apresentação, sem promover automaticamente.
  Nenhum commit, publicação ou implantação foi feito.

## E11 — Experimento de detector visual treinável — #concluida

**Objetivo:** Medir um detector local aprendido como fonte adicional, com decisão reproduzível de adoção ou rejeição.

**Por que agora:** Testa uma família de generalização diferente sem torná-la dependência obrigatória da solução.

**Dependências e paralelismo:** E02, E03. Pode ocorrer em paralelo a E08–E10; pacotes E07 habilitados e verificados são insumo opcional, nunca gate de início. Treino isolado e sem editar dados/partições congelados.

**Subagentes e integração:**

- Subagente A — Experimento: implementar treino/inferência local e adapter isolado com configuração/artefatos rastreáveis.
- Subagente B — Testes/dados: auditar partições, hashes, dependências/licenças e reprodutibilidade; não ajustar o modelo com reserva.
- Subagente C — PDFs: validar visualmente predições em todos os exemplos e registrar ganho exclusivo, falhas e motivos da decisão experimental.
- Coordenação e sincronização — Testes e auditoria de dados podem avançar durante treino; revisão de resultados só após congelar pesos e outputs, sem usar validação para votar adoção. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `scripts/experiments/`, `requirements-experiments.lock`, protocolo E02 e contrato E03; candidato Faster R-CNN/FPN F07, com seleção final justificada.

**Fora de escopo:** Não usar modelos de linguagem remotos, presumir classes técnicas nos pesos genéricos ou incluir modelo no cliente.

**Passos de implementação:**

1. Conferir licença de código/pesos/dados e capacidade de treino/inferência local; registrar arquitetura, seeds, hashes e ambiente.
2. Treinar com dados autorizados/sintéticos, mantendo ancestrais na mesma partição; não usar a reserva como fonte de augmentation.
3. Avaliar objetos pequenos, desconhecidos e estilos inéditos, além de complementaridade com E04–E10; usar somente classes com referência avaliável e publicar estratos sem dado.
4. Entregar adapter experimental e resultado de adoção por estrato, ou rejeição fundamentada; se faltar dado para executar, registrar bloqueio e ação, sem alegar ensaio concluído.

**Critérios de aceite:**

- [x] Treino/inferência e avaliação foram executados de forma reproduzível e sem vazamento.
- [x] Há matriz de acertos/erros exclusivos e decisão de integração por ganho, não por popularidade do modelo.
- [x] Modelo rejeitado permanece fora da composição; rejeição não elimina obrigações de cobertura restantes.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q e V-B do experimento, com medição de RAM/tempo e repetição determinística quando suportada; registrar comando real de treino, inferência e diferenças numéricas. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Poucos exemplos e custo de CPU: experimento isolado; manter famílias não neurais como composição possível.

**Prompt para uma sessão limpa:**

```text
Execute E11 — Experimento de detector visual treinável de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E02, E03. Pacotes E07 habilitados/verificados são insumo opcional; variantes pendentes não são rótulos de treino. Objetivo: Medir um detector local aprendido como fonte adicional, com decisão reproduzível de adoção ou rejeição.
Escopo: `scripts/experiments/`, `requirements-experiments.lock`, protocolo E02 e contrato E03; candidato Faster R-CNN/FPN F07, com seleção final justificada.
Limites: Não usar modelos de linguagem remotos, presumir classes técnicas nos pesos genéricos ou incluir modelo no cliente.
Aceite específico: Treino/inferência e avaliação foram executados de forma reproduzível e sem vazamento. Há matriz de acertos/erros exclusivos e decisão de integração por ganho, não por popularidade do modelo. Modelo rejeitado permanece fora da composição; rejeição não elimina obrigações de cobertura restantes.
Validação: V-N, V-Q e V-B do experimento, com medição de RAM/tempo e repetição determinística quando suportada; registrar comando real de treino, inferência e diferenças numéricas. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Experimento: implementar treino/inferência local e adapter isolado com configuração/artefatos rastreáveis. B — Testes/dados: auditar partições, hashes, dependências/licenças e reprodutibilidade; não ajustar o modelo com reserva. C — PDFs: validar visualmente predições em todos os exemplos e registrar ganho exclusivo, falhas e motivos da decisão experimental. Coordene assim: Testes e auditoria de dados podem avançar durante treino; revisão de resultados só após congelar pesos e outputs, sem usar validação para votar adoção. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

### Registro de execução E11 — checkpoint experimental de 24/09/2026

**Pré-voo e dependências.** Git inicial limpo em `5dbefee76fbe022349285b4b09cf1cf22c39a3ae`;
nenhum `AGENTS.md` aplicável encontrado. E02/E03 tinham `#concluida` e contratos
implementados; o snapshot público E02, inventário E01 e lacre da reserva conferiram,
respectivamente, SHA-256 `fd30cb3f…`, `e3d49d9b…` e `6874d058…`. As regressões
E03 prévias passaram (44 testes). Nenhuma alteração preexistente precisou ser
incorporada. O lacre foi apenas hasheado como bytes opacos; reserva não foi listada,
aberta, renderizada, inferida ou usada no treino. E07 habilitado foi incluído no
comparador opcional; variantes `pending` não foram rótulos.

**Delegações e propriedade.** `/root/a_experimento` foi responsável exclusivo por
`scripts/experiments/e11_detector.py`, `e11_adapter.py`,
`requirements-experiments.lock` e
[`e11-experimento-detector.md`](e11-experimento-detector.md). `/root/b_testes_dados`
foi responsável por `tests/unit/test_e11_experiment.py` e
`tmp/e11-simbologia/audit/`; auditou partições, hashes, licença e repetibilidade
sem editar o detector. `/root/c_pdfs` foi responsável por
`tmp/e11-simbologia/visual/`; congelou a leitura das imagens originais antes de
receber os pesos e predições. O coordenador editou somente este roadmap,
`scripts/experiments/e11_calibration_ids.py` (vínculo documental de IDs do
baseline de calibração, sem ler ocorrências) e
`tmp/e11-simbologia/integration/`. Treino aguardou o baseline V-P encerrar para
medir recursos sem carga concorrente; C recebeu apenas os hashes do checkpoint
final para a segunda fase. O autor não foi o único revisor do adapter: B encontrou
e A corrigiu motivo obrigatório de `FORA_DOMINIO` e frame da página renderizada.

**Seleção e configuração congeladas.** F07 Faster R-CNN/FPN não foi executado:
Torch/TorchVision não estão na `.venv`, não havia GPU declarada e o corpus de treino
tem 22 positivos de um único ancestral. Pesos COCO genéricos não identificam
classes técnicas; nenhuma instalação ou download ocorreu. Foi medido um classificador
linear de janelas raster com PyMuPDF/Pillow, inicializado do zero, seed `20260924`,
5 classes E02, 12×12 pixels por janela, imagem completa limitada a 900 px no maior
lado, limiar bruto 0,8, NMS 0,3 e teto global de 40 candidatos por página.
Essa seleção mede uma família aprendida executável localmente, sem alegar
equivalência arquitetural a F07. O modelo e seu score não entraram no cliente,
em `src/`, na composição ou em calibração probabilística. Código/licença/pesos e
titularidade dos dados estão detalhados no documento E11 e na auditoria local B.

**Comandos reais do experimento e V-B** (raiz, Python da `.venv`; paths relativos):

```powershell
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector prepare --output tmp/e11-simbologia/data
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector train --reference tmp/e11-simbologia/data/development/reference.json --root tmp/e11-simbologia/data/development --output tmp/e11-simbologia/train --seed 20260924
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector infer --model tmp/e11-simbologia/train/model.json --root tmp/e11-simbologia/data/development --output tmp/e11-simbologia/eval-development
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector infer --model tmp/e11-simbologia/train/model.json --root tmp/e11-simbologia/data/calibration --output tmp/e11-simbologia/eval-calibration
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector infer --model tmp/e11-simbologia/train/model.json --root examples --output tmp/e11-simbologia/vp
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --output tmp/e11-simbologia/integration/baseline-all-synthetic --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --output tmp/e11-simbologia/integration/baseline-all-examples --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root tmp/e11-simbologia/data/calibration --output tmp/e11-simbologia/integration/baseline-calibration-raw --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend
.\.venv\Scripts\python.exe -m scripts.experiments.e11_calibration_ids --raw tmp/e11-simbologia/integration/baseline-calibration-raw/predictions.json --output tmp/e11-simbologia/integration/baseline-calibration-predictions.json
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector compare --reference tmp/e11-simbologia/data/development/reference.json --baseline tmp/e11-simbologia/integration/baseline-all-synthetic/predictions.json --learned tmp/e11-simbologia/eval-development/predictions.json --output tmp/e11-simbologia/integration/development-union
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector compare --reference tmp/e11-simbologia/data/calibration/reference.json --baseline tmp/e11-simbologia/integration/baseline-calibration-predictions.json --learned tmp/e11-simbologia/eval-calibration/predictions.json --output tmp/e11-simbologia/integration/calibration-union
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector compare --baseline tmp/e11-simbologia/integration/baseline-all-examples/predictions.json --learned tmp/e11-simbologia/vp/predictions.json --output tmp/e11-simbologia/integration/examples-union
```

`train-repeat`, `eval-development-repeat`, `eval-calibration-repeat` e `vp-repeat`
repetiram os quatro comandos de treino/inferência com os mesmos argumentos e
diretórios de saída substituídos. Modelo e predições foram byte a byte idênticos:
SHA-256 do modelo `ca1058ae22c900de1e173673b26e79643ec8cd5a000f4a60326b7f354739df1a`,
dev `6704f1654fd12552f2ef07698440fbfffbf7798247841ba7dc7a4dcae1d6aa62`,
cal `01c703baf217b628c6562c788776c063c0afe987eb4423631cad660dbddc2a4b`
e V-P `56d962e583cd091ee527888d71e409c1d372246a9655aaae299c46fe0d73e738`.
Diferença numérica de candidatos/caixas/scores: zero. Tempos 1ª/2ª execução (s):
treino 2,076/2,047; inferência dev 1,029/1,032, cal 0,286/0,272 e V-P
10,985/10,639. Picos de working set 1ª/2ª (MB): 79,57/79,90; 94,02/94,29;
88,90/85,29; 197,78/194,43. O primeiro modelo `dbe5940b…` foi invalidado
antes de inferência porque a chamada WinAPI mediu RAM como `null`; A corrigiu a
instrumentação e retreinou. Referência development/calibration regenerada com
hashes E02 idênticos; origem dos PDFs preservada antes/depois.

| Avaliação E02 | Baseline 9 métodos TP/FP/FN | E11 isolado TP/FP/FN | União crua TP/FP/FN | Exclusivos E11 | Interpretação |
|---|---:|---:|---:|---:|---|
| Desenvolvimento, no treino | 16/15/6 | 8/65/14 | 19/85/3 | 3 TP, 65 FP exclusivos | Ganho in-sample não demonstra generalização; excesso de FP. |
| Calibração, outro ancestral | 1/0/3 | 0/21/4 | 1/21/3 | 0 TP, 21 FP exclusivos | Nenhum ganho independente. Dos 4 FN E11, 2 são `TRANSFORMADOR` suportado; 2 `POSTE` fora do domínio. |

O avaliador E02 preserva todas as observações na união; silêncio dos outros
métodos não veta E11, e concordância não é probabilidade. A calibração não alterou
pesos, arquitetura, limiar ou tetos. A única classe treinada com referência
independente é `TRANSFORMADOR` (2 objetos); `POSTE` não integra as 5 classes
suportadas. Famílias sem amostra continuam com recall `null` por método/estrato,
sem destino implícito de cobertura. O baseline V-P processou 11 PDFs/11 páginas,
240 candidatos e zero falhas em 848,457 s acumulados por documento; E11 processou
os mesmos 11/11, 329 candidatos e zero falhas. A união V-P tem 569 observações,
10 métodos e SHA `590f3fc1595be91d64658f015c2d9789611eec4cd2f56117c720c14dddd92e4e`;
nenhum recall/precisão global foi calculado com referência visual parcial.
E11 suprimiu 347 candidatos pelo teto global em 6 páginas V-P e truncou outras
1.629 propostas pelos tetos locais; cobriu os rasters completos, mas isso não
demonstra recall completo.

**V-N/V-Q do checkpoint:**
`.\.venv\Scripts\python.exe -m pytest tests/unit/test_e11_experiment.py` deu
**7 passed**; integração do coordenador com regressões E03
`.\.venv\Scripts\python.exe -m pytest tests/unit/test_e11_experiment.py tests/unit/test_symbol_observations.py tests/unit/test_legacy_symbol_adapter.py tests/integration/test_symbol_observation_json.py -q`
deu **51 passed**. Separadamente, `.\.venv\Scripts\python.exe -m ruff check .`,
`.\.venv\Scripts\python.exe -m ruff format --check .` e
`.\.venv\Scripts\python.exe -m mypy` saíram 0 (417 arquivos formatados,
382 fontes mypy). `git diff --check` saiu 0. Testes novos cobrem split/hash,
rejeição de calibração no treino, repetição, falhas, round-trip E03 e união
sem veto; B adicionou teste da transformação documental de IDs da calibração.
Uma checagem extra `mypy scripts/experiments/e11_calibration_ids.py` sem `src`
falhou por 13 imports do pacote local vistos como não tipados; repetida com
`.\.venv\Scripts\python.exe -m mypy src scripts/experiments/e11_calibration_ids.py`
passou em 225 arquivos. O V-Q prescrito acima permaneceu sem falhas.

**V-P visual concluída no escopo E11.** C descobriu recursivamente **11 PDFs/11
páginas**, zero bloqueados. Congelou leitura da fonte antes das predições: 74 PNGs
efetivamente abertos (base, aparência e tiles cobrindo toda a folha), com
`source_manifest.json` SHA
`a207137b8faba84931ddaa7afd5fd84810c7af95701a5d7561fb91320cebbc7a`
e `source_observations.md` SHA
`32d184c3cdc197360e844d9bdf14360724e5c90ab67e0bd0815891de8bf42e63`.
Após congelar pesos/outputs, C abriu **33/33 folhas de contato** com **329/329
ROIs E11**; registro por ID, bbox, imagem, motivo e vizinhos em
`tmp/e11-simbologia/visual/e11_review.json` SHA
`cde3be649f1959b99beeae5dc371944b44c077735448def188a3795efe0bbb55`.
A matriz integral tem **11 × 10 × 2 = 220 células**: 99 execuções base, 11
base fora de domínio e 110 anotações fora de domínio, sem converter silêncio em
evidência negativa. O relatório
`tmp/e11-simbologia/visual/e11_visual_results.md` SHA
`d795a65fcef9bb93aa4e70c7f8eb438df5ffc37ded5050fbf6828ee2fa48548e`
registra por página **270 FP visuais localizados, 59 classe/identidade não
resolvida e zero TP E11 exclusivo confirmado**. Esses são juízos provisórios de
IA nos exemplos já expostos, não precisão/recall populacional. Apenas 2 caixas
E11 têm sobreposição IoU ≥0,1 com baseline; ambas têm classe conflitante e
continuam não resolvidas. Outras 327 caixas são espacialmente exclusivas, o que
não as torna acertos. Entre os candidatos E11 há 55 pares de caixas com IoU ≥0,5
e classes diferentes, envolvendo 89 IDs. Dois FN mínimos de `ATERRAMENTO` foram
confirmados em recortes ampliados de `1250771080` e `1256407599`; nenhum bbox E11
cobre seus centros. O coordenador reabriu diretamente duas folhas de contato e
esses dois recortes para conferir os achados.

**Reuso e limites do comparador.** O comando
`.\.venv\Scripts\python.exe tmp/e11-simbologia/integration/verify_baseline_reuse.py`
saiu 0: as 11 fontes SHA coincidem com E05/E09/E10, 220 observações legadas
coincidem integralmente por ID e conteúdo com E10 e 17 transformadores vetoriais
com E05. Os 3 candidatos de grafo E09 conservam fonte/classe/caixa/score, mas
IDs/proveniência mudaram; o coordenador renderizou e abriu novamente os 3 recortes
atuais em `integration/structural-current-crops/`, sem alegar reuso de artefato
idêntico. A frente C não refez a leitura semântica dos 240 candidatos baseline;
para 237 observações imutáveis, os achados visuais anteriores são reutilizáveis
somente nesse escopo, e os 3 divergentes têm inspeção atual. A matriz E11 não
declara aprovação de todos os métodos anteriores ou homologação de campo.
Comando final C:
`.\.venv\Scripts\python.exe tmp/e11-simbologia/visual/compile_visual_review.py`
→ exit 0, 329 registros/220 células, hashes de 11 fontes, referência congelada e
outputs conferidos. Nenhuma ROI do revisor entrou no detector.

**Decisão: rejeitar a integração de E11 ao produto.** Na calibração independente
E11 não acrescentou TP e trouxe 21 FP exclusivos; a união caiu de 1 TP/0 FP
para 1 TP/21 FP, preservando o TP prévio. Em desenvolvimento houve 3 TP
exclusivos apenas no ancestral usado no treino, com FP da união de 15 para 85;
essa melhora in-sample não demonstra generalização. A revisão real não confirmou
TP exclusivo e mostrou 270 FP visuais localizados, 59 incertezas e dois FN
mínimos, sem denominador global. O custo medido (pico até 197,78 MB; 10,985 s
para 11 páginas) não compra ganho comprovado. O modelo experimental permanece
somente em `tmp/`, o adapter em `scripts/experiments/`, sem importação em `src/`,
composição, cliente ou release. Essa rejeição conclui **o experimento E11**, não
reconhece as 344 variantes E07 `pending`, não remove famílias do inventário e
não reduz os gates de cobertura/união de E12–E16. Futuro ensaio exigiria mais
ancestrais autorizados e novas avaliações cegas antes de reconsiderar adoção;
reserva E02 permanece lacrada até E16. Nenhum commit, publicação ou implantação.

## E12 — União, validação cruzada e calibração — #pendente

**Objetivo:** Entregar reconciliador de símbolos que aproveite exclusivos e resolva duplicatas/conflitos sem quórum.

**Por que agora:** As saídas independentes e o benchmark permitem avaliar a composição, não apenas motores isolados.

**Dependências e paralelismo:** E05, E06, E08, E09, E10, E11. Integração serial após os handoffs desses detectores; consumir snapshot E07 somente dos pacotes habilitados/verificados. E09/E11 podem entregar rejeição experimental válida, nunca falha de execução ocultada.

**Subagentes e integração:**

- Subagente A — Código: reconciliador, associação de hipóteses e política calibrada nos módulos atribuídos.
- Subagente B — Testes: exclusivos, maioria correlacionada errada, silêncio/falha, vizinhos e ablações, com oráculos independentes.
- Subagente C — PDFs: comparar cada método e união com imagens de todas as páginas, identificando candidatos válidos perdidos pela fusão.
- Coordenação e sincronização — Calibração/contratos são fixados pelo coordenador; validador não altera thresholds e preserva a reserva final. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** Novo reconciliador de simbologia em `application/` (proposto), E03 e `application/method_reconciliation.py` como contrato documental a preservar.

**Fora de escopo:** Não exigir unanimidade, fazer média de scores brutos ou reutilizar o filtro de coordenadas de E12B.

**Passos de implementação:**

1. Implementar união imutável, associação de ocorrências e matriz de apoio/complemento/contradição/abstenção com cobertura por método.
2. Preservar observações, alternativas incompatíveis e rejeições justificadas. Uma forma indistinguível entre IDs é uma ocorrência com conjunto explícito de alternativas; exigir contexto verificável para escolher ID exato, sem duplicar ativos. Ensaiar WBF somente para caixas compatíveis, comparando com seleção da geometria de origem.
3. Calibrar decisões por classe/método/estrato em partição própria, modelando correlação e incluindo ramo de candidato exclusivo elegível.
4. Rodar todos os casos da tabela de política e ablações; congelar composição e thresholds antes do gate reservado.

**Critérios de aceite:**

- [ ] Todos os casos obrigatórios da política passam, inclusive correto exclusivo e maioria correlacionada errada.
- [ ] Composição preserva os exclusivos válidos e não funde objetos distintos/páginas/camadas.
- [ ] Score bruto, probabilidade calibrada, suporte e decisão são campos distintos; falta de amostra mantém revisão.
- [ ] Matriz/ablação mostra contribuição de cada método aplicável; não detecção não vira contradição.
- [ ] Colisões visuais conhecidas mantêm alternativas na mesma ocorrência até haver discriminante verificável; variante `pending` não vira reconhecida por cadastro ou consenso.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q, V-B completo em desenvolvimento/calibração e regressão `tests/unit/test_method_reconciliation.py`; reserva final permanece lacrada até E16. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Fusão encobre erros ou validação vira consenso circular: manter evidência original, dependências de fonte e justificativa por decisão.

**Prompt para uma sessão limpa:**

```text
Execute E12 — União, validação cruzada e calibração de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E05, E06, E08, E09, E10, E11. Consuma só o snapshot E07 habilitado/verificado; o fluxo de curadoria incremental é independente. Objetivo: Entregar reconciliador de símbolos que aproveite exclusivos e resolva duplicatas/conflitos sem quórum.
Escopo: Novo reconciliador de simbologia em `application/` (proposto), E03 e `application/method_reconciliation.py` como contrato documental a preservar.
Limites: Não exigir unanimidade, fazer média de scores brutos ou reutilizar o filtro de coordenadas de E12B.
Aceite específico: Todos os casos obrigatórios da política passam, inclusive correto exclusivo e maioria correlacionada errada. Composição preserva os exclusivos válidos e não funde objetos distintos/páginas/camadas. IDs visualmente indistinguíveis ficam como alternativas de uma ocorrência até discriminante verificável; `pending` não conta como reconhecimento. Score bruto, probabilidade calibrada, suporte e decisão são campos distintos; falta de amostra mantém revisão. Matriz/ablação mostra contribuição de cada método aplicável; não detecção não vira contradição.
Validação: V-N, V-Q, V-B completo em desenvolvimento/calibração e regressão `tests/unit/test_method_reconciliation.py`; reserva final permanece lacrada até E16. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: reconciliador, associação de hipóteses e política calibrada nos módulos atribuídos. B — Testes: exclusivos, maioria correlacionada errada, silêncio/falha, vizinhos e ablações, com oráculos independentes. C — PDFs: comparar cada método e união com imagens de todas as páginas, identificando candidatos válidos perdidos pela fusão. Coordene assim: Calibração/contratos são fixados pelo coordenador; validador não altera thresholds e preserva a reserva final. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E13 — Associação semântica e promoção por campo — #pendente

**Objetivo:** Converter hipóteses reconciliadas em propostas úteis, com associação e promoção coerentes com a evidência.

**Por que agora:** Detectar um símbolo não basta para identificar ativo, situação, quantidade e suporte.

**Dependências e paralelismo:** E12. Sequencial após E12; alterações em promoção/topologia exigem integração única.

**Subagentes e integração:**

- Subagente A — Código: integração semântica, associação e promoção por campo nos módulos acordados.
- Subagente B — Testes: revisão/reanálise, catálogo pendente, estai versus cabo e presença versus não detecção.
- Subagente C — PDFs: conferir em toda a coleção classe, situação, quantidade, suporte e proposta, inclusive exclusivos e pendências.
- Coordenação e sincronização — Coordenador integra promoção/topologia serialmente; testes usam checkpoint único e retornam regressões ao autor do módulo. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `application/interpretation_pipeline.py`, `automatic_promotion.py`, `analysis_regions.py`, `topology_compliance.py`, `adapters/interpretation/category_analyzers.py`, `relation_rules.py` e domínio.

**Fora de escopo:** Não inferir equipamento para satisfazer uma norma nem inventar catálogo para classe reconhecida.

**Passos de implementação:**

1. Conectar resultado E12 à interpretação sem quebrar evidências/documentary readings; mapear todas as famílias E01 para proposta, alternativas pendentes de revisão, contexto informativo ou ainda não suportado, sem converter este último em reconhecimento.
2. Associar símbolo a suporte/trecho/rotulo considerando documento, página, camada e ambiguidade; separar quantidade de componentes e de ativos.
3. Aplicar política por campo e revisão técnica; preservar exclusivos elegíveis sem quórum, conflitos e classe conhecida com catálogo pendente. Conjunto de IDs alternativos permanece uma única ocorrência e não promove automaticamente ativo de ID incerto.
4. Publicar fatos de presença/avaliabilidade somente com origem adequada; distinguir silêncio do detector de ausência física.

**Critérios de aceite:**

- [ ] Símbolo correto exclusivo chega à proposta e pode seguir a política de promoção sem segundo detector.
- [ ] Estai não vira cabo; texto isolado não prova símbolo; legenda não vira ocorrência de rede.
- [ ] Quantidade/situação/associação incertas ficam pendentes e não são completadas pelo catálogo.
- [ ] Alternativas visuais não geram múltiplos ativos nem promoção de ID não comprovado; famílias sem reconhecimento seguem visíveis como pendentes.
- [ ] Revisão humana e reanálise preservam histórico, vigência e conflitos; conformidade não recebe presença inventada.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-I, V-N, V-Q e V-B semântico; testar persistência/reabertura, pontos próximos, páginas diferentes e revisão base/anotação. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Atributo booleano legado vira autoridade indevida: consumidores devem verificar proveniência e resolução de cada campo.

**Prompt para uma sessão limpa:**

```text
Execute E13 — Associação semântica e promoção por campo de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E12. Objetivo: Converter hipóteses reconciliadas em propostas úteis, com associação e promoção coerentes com a evidência.
Escopo: `application/interpretation_pipeline.py`, `automatic_promotion.py`, `analysis_regions.py`, `topology_compliance.py`, `adapters/interpretation/category_analyzers.py`, `relation_rules.py` e domínio.
Limites: Não inferir equipamento para satisfazer uma norma nem inventar catálogo para classe reconhecida.
Aceite específico: Símbolo correto exclusivo chega à proposta e pode seguir a política de promoção sem segundo detector. Estai não vira cabo; texto isolado não prova símbolo; legenda não vira ocorrência de rede. Alternativas visuais são uma ocorrência pendente, sem múltiplos ativos ou promoção de ID incerto; família não reconhecida permanece visível como pendência. Quantidade/situação/associação incertas ficam pendentes e não são completadas pelo catálogo. Revisão humana e reanálise preservam histórico, vigência e conflitos; conformidade não recebe presença inventada.
Validação: V-I, V-N, V-Q e V-B semântico; testar persistência/reabertura, pontos próximos, páginas diferentes e revisão base/anotação. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: integração semântica, associação e promoção por campo nos módulos acordados. B — Testes: revisão/reanálise, catálogo pendente, estai versus cabo e presença versus não detecção. C — PDFs: conferir em toda a coleção classe, situação, quantidade, suporte e proposta, inclusive exclusivos e pendências. Coordene assim: Coordenador integra promoção/topologia serialmente; testes usam checkpoint único e retornam regressões ao autor do módulo. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E14 — Revisão visual, API e exportações — #pendente

**Objetivo:** Expor símbolos, métodos, exclusivos e conflitos de modo revisável no cliente e nos arquivos exportados.

**Por que agora:** A cobertura adicionada precisa ser conferível e corrigível pelo usuário.

**Dependências e paralelismo:** E13. Sequencial após E13; contrato/API/cliente são uma mudança coordenada.

**Subagentes e integração:**

- Subagente A — Código: DTO/API/cliente/exportações por lotes com interfaces acordadas; coordenador integra snapshot OpenAPI.
- Subagente B — Testes: contratos, persistência de revisão, exportação e regressão da UI em arquivos separados.
- Subagente C — PDFs/UI: conferir realces/recortes e correspondência das propostas com todas as páginas e exportações, guardando evidência visual.
- Coordenação e sincronização — Estabilizar DTO antes de implementar consumidores; usar ondas se separar servidor/cliente exigir mais agentes; uma sessão de UI por vez. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `src/zeny_project_handler_contracts/review.py`, `src/zeny_project_handler_server/review_api.py`, `src/zeny_project_handler_client/ui/review_panel.py`, `review_gateway.py`, exportações e `docs/api/openapi-v1.json`.

**Fora de escopo:** Não executar visão computacional no cliente nem transferir decisões em lote por semelhança.

**Passos de implementação:**

1. Projetar campos aditivos de hipóteses/observações, alternativas, cobertura e motivos; respeitar versionamento e compatibilidade cliente/servidor.
2. Exibir recorte, classe/situação/quantidade, alternativas de ID na mesma ocorrência, origem e resumo legível de acordo/divergência; permitir inspeção técnica dos motores sem sobrecarregar o fluxo principal.
3. Permitir correção/rejeição de símbolo desconhecido ou exclusivo e associação, preservando auditoria e controle de conflito.
4. Exportar mesmos estados/pendências no XLSX/PDF quando aplicável; não apresentar score bruto como porcentagem de acerto.

**Critérios de aceite:**

- [ ] Exclusivo, conflitante, desconhecido e informativo são distinguíveis e localizáveis na página correta.
- [ ] A UI e a exportação distinguem alternativa sem ID resolvido de reconhecimento exato e de família ainda não suportada; nenhuma alternativa é contada como ativo adicional.
- [ ] Correção/rejeição persiste e reabertura/exportação mantém o mesmo resultado.
- [ ] Clientes compatíveis consomem payload aditivo e o snapshot OpenAPI corresponde ao código.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-U, V-O, V-N, V-Q; inspeção manual com fixture de união/exclusivo/conflito em zoom/rotação e conferência das células/exportações. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** UI mascara hipótese como confirmação: rotular campos pendentes e separar score técnico de decisão.

**Compatibilidade e rollback:** Manter campos novos aditivos/defaults e versionar incompatibilidades; rollback desabilita a exibição/composição nova sem apagar observações ou decisões. Se houver migração, testar upgrade e recuperação antes de concluir.

**Prompt para uma sessão limpa:**

```text
Execute E14 — Revisão visual, API e exportações de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E13. Objetivo: Expor símbolos, métodos, exclusivos e conflitos de modo revisável no cliente e nos arquivos exportados.
Escopo: `src/zeny_project_handler_contracts/review.py`, `src/zeny_project_handler_server/review_api.py`, `src/zeny_project_handler_client/ui/review_panel.py`, `review_gateway.py`, exportações e `docs/api/openapi-v1.json`.
Limites: Não executar visão computacional no cliente nem transferir decisões em lote por semelhança.
Aceite específico: Exclusivo, conflitante, desconhecido e informativo são distinguíveis e localizáveis na página correta. UI e exportação mostram alternativas na mesma ocorrência, sem ID exato inventado nem ativo extra, e separam famílias não suportadas. Correção/rejeição persiste e reabertura/exportação mantém o mesmo resultado. Clientes compatíveis consomem payload aditivo e o snapshot OpenAPI corresponde ao código.
Validação: V-U, V-O, V-N, V-Q; inspeção manual com fixture de união/exclusivo/conflito em zoom/rotação e conferência das células/exportações. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: DTO/API/cliente/exportações por lotes com interfaces acordadas; coordenador integra snapshot OpenAPI. B — Testes: contratos, persistência de revisão, exportação e regressão da UI em arquivos separados. C — PDFs/UI: conferir realces/recortes e correspondência das propostas com todas as páginas e exportações, guardando evidência visual. Coordene assim: Estabilizar DTO antes de implementar consumidores; usar ondas se separar servidor/cliente exigir mais agentes; uma sessão de UI por vez. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E15 — Execução, cache e ativação controlada no servidor — #pendente

**Objetivo:** Integrar a composição habilitada ao job do servidor com memória limitada, cancelamento e assinaturas completas.

**Por que agora:** Valida comportamento operacional e recuperação depois de resolver a semântica e apresentação.

**Dependências e paralelismo:** E13, E14. Sequencial após E14; respeitar composição local preexistente.

**Subagentes e integração:**

- Subagente A — Código: orquestração, assinatura, cache e configuração do servidor; preservar mudanças locais.
- Subagente B — Testes/desempenho: injetar falhas/cancelamento, medir recursos e verificar idempotência/rollback em ambiente isolado.
- Subagente C — PDFs: conferir integridade, manifesto e resultados de todas as páginas no checkpoint operacional; auditar reuso de cache e evidências parciais.
- Coordenação e sincronização — Não disputar o mesmo worker/banco/UI; coordenador agenda execuções pesadas e integra configuração compartilhada. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** `src/zeny_project_handler_server/composition.py`, `job_manager.py`, `job_store.py`, configuração do servidor, `application/document_analysis.py`, `pymupdf_analyzer.py` e cache.

**Fora de escopo:** Não publicar/deployar, adicionar modelos ao cliente ou ocultar falha de motor habilitado como execução completa.

**Passos de implementação:**

1. Registrar configuração e assinatura de motores, pacotes, calibração, modelos, perfil, renderização e versões; novas combinações invalidam reutilização incompatível.
2. Orquestrar tarefas por página/tile, liberar rasters, reportar progresso e verificar cancelamento entre chamadas.
3. Distinguir motor desabilitado, não aplicável e falha de motor habilitado; preservar resultados parciais sem promover a execução incompleta.
4. Ensaiar retomada, opt-out e composição degradada explícita; documentar limites observados e instalação opcional dos motores aprovados.

**Critérios de aceite:**

- [ ] Mudança de modelo/template/perfil/calibração altera assinatura; repetição idêntica permanece idempotente.
- [ ] OOM simulado, tile falho, ausência de modelo e cancelamento não produzem sucesso/cache integral.
- [ ] Configuração anterior continua utilizável e histórico permanece íntegro após habilitar/desabilitar.
- [ ] RAM/tiles/progresso estão medidos em ambiente declarado, sem impor GPU nem teto global arbitrário de duração.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-R, V-N, V-Q; teste integrado com falhas injetadas e reabertura; V-B operacional com telemetria e invariância do PDF de origem. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Interação com mudanças locais em composition.py: preservar diferenças preexistentes e revisar o diff específico.

**Compatibilidade e rollback:** Ativação por configuração versionada e opt-in até E16. Desabilitar nova composição retorna à anterior com assinatura própria; não apagar banco/histórico. Migração real, se necessária, exige teste e procedimento de recuperação documentados.

**Prompt para uma sessão limpa:**

```text
Execute E15 — Execução, cache e ativação controlada no servidor de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E13, E14. Objetivo: Integrar a composição habilitada ao job do servidor com memória limitada, cancelamento e assinaturas completas.
Escopo: `src/zeny_project_handler_server/composition.py`, `job_manager.py`, `job_store.py`, configuração do servidor, `application/document_analysis.py`, `pymupdf_analyzer.py` e cache.
Limites: Não publicar/deployar, adicionar modelos ao cliente ou ocultar falha de motor habilitado como execução completa.
Aceite específico: Mudança de modelo/template/perfil/calibração altera assinatura; repetição idêntica permanece idempotente. OOM simulado, tile falho, ausência de modelo e cancelamento não produzem sucesso/cache integral. Configuração anterior continua utilizável e histórico permanece íntegro após habilitar/desabilitar. RAM/tiles/progresso estão medidos em ambiente declarado, sem impor GPU nem teto global arbitrário de duração.
Validação: V-R, V-N, V-Q; teste integrado com falhas injetadas e reabertura; V-B operacional com telemetria e invariância do PDF de origem. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Código: orquestração, assinatura, cache e configuração do servidor; preservar mudanças locais. B — Testes/desempenho: injetar falhas/cancelamento, medir recursos e verificar idempotência/rollback em ambiente isolado. C — PDFs: conferir integridade, manifesto e resultados de todas as páginas no checkpoint operacional; auditar reuso de cache e evidências parciais. Coordene assim: Não disputar o mesmo worker/banco/UI; coordenador agenda execuções pesadas e integra configuração compartilhada. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E16 — Aceite integrado e matriz final de cobertura — #pendente

**Objetivo:** Demonstrar a melhoria de cobertura por união e auditar integralmente o inventário e as regressões, publicando alcance e lacunas reais.

**Por que agora:** É o gate que distingue algoritmos implementados de melhoria demonstrada ponta a ponta.

**Dependências e paralelismo:** E15. Gate serial com configuração congelada.

**Subagentes e integração:**

- Subagente A — Integração: preparar checkpoint/configuração e reproduzir o fluxo completo; nesta frente não ajustar algoritmos sobre a reserva.
- Subagente B — Testes: executar V-Q/V-G/V-B reservado, auditar métricas/ablações e confirmar independência da reserva.
- Subagente C — PDFs: validação final independente de toda a coleção, páginas/camadas e saídas da composição, com cobertura reconciliada ao manifesto.
- Coordenação e sincronização — Coordenador consolida aceite e relatório; correção necessária volta à etapa responsável, recebe novo checkpoint e revalidação antes de fechar o gate. O agente principal define propriedade de arquivos, confere entregas e executa a integração; somente ele atualiza o roadmap.
- Entrega de cada frente — arquivos/relatório, checkpoint, comandos e resultados, evidências verificáveis e pendências. Registrar IDs/papéis efetivos e cobertura V-P no handoff; detalhes operacionais seguem o protocolo global.

**Escopo:** Este roadmap, fixtures/avaliador E02, pipeline, API/UI/exportações e handoffs relacionados; novo relatório final em `docs/` (proposto).

**Fora de escopo:** Não baixar metas, ajustar sobre a reserva ou declarar concluídos aceites históricos de outro escopo.

**Passos de implementação:**

1. Congelar versão/configuração e executar a reserva uma vez para aceite; após falha, registrar correção e criar reserva nova antes de recalibrar.
2. Publicar matriz de todos os IDs da versão E01 congelada (427 no checkpoint atual) por família/estrato e cada método: reconhecido exato, alternativa sem ID resolvido, informativo, ainda não suportado e não avaliável; isolado, união, interseção de controle, composição e ablação, com exclusivos preservados, denominadores e custo. Variante pendente permanece pendente mesmo que sua família tenha outra variante reconhecida.
3. Executar V-G, V-Q e fluxo completo de análise/revisão/exportação/cancelamento; conferir classificação, situação, quantidade e associação separadamente.
4. Registrar V-P obrigatório de todos os exemplos reais disponíveis; apontar classes/estratos que seguem em revisão e confirmar todos os critérios globais aplicáveis ao snapshot suportado. O backlog de curadoria independente não recebe aceite implícito.

**Critérios de aceite:**

- [ ] Todos os critérios globais e as metas congeladas aplicáveis ao snapshot suportado passam; todos os IDs do inventário congelado têm destino explícito, inclusive variantes não suportadas, sem declará-las reconhecidas ou homologadas.
- [ ] União final demonstra recuperação de acertos exclusivos e ganho sobre baseline, com FP e denominadores publicados.
- [ ] Todos os métodos têm avaliação e decisão de adoção/rejeição; ao menos duas famílias algorítmicas distintas contribuem com acertos exclusivos validados.
- [ ] Não há unanimidade/quórum escondido; contratos, histórico, jobs e exportações passam nos testes obrigatórios.
- [ ] Relatório distingue validação sintética, generalização real disponível e automação não homologada por falta de evidência.
- [ ] Matriz publica contagens e denominadores de reconhecimento exato, alternativas, informativos, pendentes e não avaliáveis por família/variante; o aceite desta integração não encerra E07 histórico nem o fluxo de curadoria.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-B reservado, V-Q, V-G e inspeção manual dos casos obrigatórios da política na UI/exportação. Não concluir se teste obrigatório não foi executado ou meta falhou. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Otimizar no conjunto final ou omitir classes difíceis: lacrar configuração, preservar resultados reprovados e publicar matriz completa.

**Prompt para uma sessão limpa:**

```text
Execute E16 — Aceite integrado e matriz final de cobertura de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E15. Objetivo: Demonstrar a melhoria de cobertura por união e auditar todos os IDs da versão E01 congelada (427 no checkpoint atual) e as regressões, publicando alcance e lacunas reais.
Escopo: Este roadmap, fixtures/avaliador E02, pipeline, API/UI/exportações e handoffs relacionados; novo relatório final em `docs/` (proposto).
Limites: Não baixar metas, ajustar sobre a reserva ou declarar concluídos aceites históricos de outro escopo.
Aceite específico: Todos os critérios globais e metas congeladas aplicáveis ao snapshot suportado passam. Cada ID da versão E01 congelada (427 no checkpoint atual; recalcular se o inventário crescer) aparece na matriz como reconhecido exato, alternativa sem ID resolvido, informativo, ainda não suportado ou não avaliável, com denominadores; pendência não vira reconhecimento. União final demonstra recuperação de acertos exclusivos e ganho sobre baseline, com FP e denominadores publicados. Todos os métodos têm avaliação e decisão de adoção/rejeição; ao menos duas famílias algorítmicas distintas contribuem com acertos exclusivos validados. Não há unanimidade/quórum escondido; contratos, histórico, jobs e exportações passam nos testes obrigatórios. Relatório distingue validação sintética, generalização real disponível e automação não homologada por falta de evidência; concluir E16 não conclui E07 histórico nem a curadoria independente.
Validação: V-B reservado, V-Q, V-G e inspeção manual dos casos obrigatórios da política na UI/exportação. Não concluir se teste obrigatório não foi executado ou meta falhou. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Integração: preparar checkpoint/configuração e reproduzir o fluxo completo; nesta frente não ajustar algoritmos sobre a reserva. B — Testes: executar V-Q/V-G/V-B reservado, auditar métricas/ablações e confirmar independência da reserva. C — PDFs: validação final independente de toda a coleção, páginas/camadas e saídas da composição, com cobertura reconciliada ao manifesto. Coordene assim: Coordenador consolida aceite e relatório; correção necessária volta à etapa responsável, recebe novo checkpoint e revalidação antes de fechar o gate. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.
