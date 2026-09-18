# Zeny Project Handler — Roadmap de análise de simbologia

Criado em 18/09/2026; revisado para execução com subagentes e V-P em 18/09/2026. Base inspecionada: `bfb47f7`, com alterações locais preexistentes.
Documento de planejamento; nenhuma etapa abaixo foi implementada nesta tarefa.

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
| Exemplos | `examples/README.md` | PDFs reais são opcionais, locais e ignorados; gate padrão deve funcionar sem eles. Nenhum conjunto privado obrigatório. |

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
| Cobertura infinita de símbolos | E01 congela famílias e variantes das fontes escolhidas, com versão e totalizadores; símbolos novos seguem como desconhecidos e expansão explícita. Nenhuma classe some do denominador por baixo desempenho. |
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
- Cobertura de todas as famílias de E01 tem destino verificável em E07/E13/E14. Registro
  de “não suportado” é transparente, mas não equivale a reconhecimento concluído. Se faltar
  uma família do inventário, o aceite integral fica pendente/bloqueado com ação concreta.
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
| V-B | Benchmark novo a criar em E02, proposto `scripts/benchmark_symbols.py`; não existe na inspeção. E02 deve documentar CLI real, seed, partições, hashes e comando exato. E04–E16 executam esse comando registrado; não inventar flags. |
| V-P | Auditoria visual por IA de todos os PDFs/páginas em `examples/`, conforme protocolo acima; runner/comando real a entregar em E02. E01 realiza inventário visual e E03 confere o contrato usando baseline congelado. |
| V-N | Testes novos da etapa: criar em `tests/unit/` ou `tests/integration/` conforme fronteira e registrar os caminhos/comandos exatos no handoff. Validar comportamento e falhas, não só espelhar a implementação. |

V-Q é obrigatório para mudanças de código de cada etapa. Falha preexistente não pode ser
apagada nem atribuída à etapa sem análise: registrar comparação e impedimento de aceite.
E16 executa V-G; não repetir toda a suíte após mera edição do roadmap.

## Índice de etapas

| ID | Etapa | Estado | Dependências | Entrega principal |
|---|---|---|---|---|
| E01 | Inventário de símbolos e perfis de referência | #pendente | Nenhuma | Criar inventário versionado e verificável de famílias, variantes e convenções, incluindo símbolos sem equivalente patrimonial. |
| E02 | Benchmark de cobertura e complementaridade | #pendente | E01 | Entregar avaliador independente e baseline reproduzível de símbolos, com reserva e métricas de união. |
| E03 | Contrato de observações e registro de métodos | #pendente | E01, E02 | Introduzir contrato interno aditivo para observações de símbolos, cobertura e estados de cada método. |
| E04 | Robustez vetorial de aterramento e para-raios | #pendente | E03 | Melhorar o detector existente para primitives fragmentadas/agrupadas, escala e estilos, sem ampliar sua lista de classes. |
| E05 | Reconhecimento visual de transformadores | #pendente | E04 | Detectar variantes gráficas de transformador e conjuntos sem depender da existência de um literal reconhecido. |
| E06 | Reconhecimento de estais e ancoragens | #pendente | E04 | Reconhecer as variantes de estai e seus vínculos geométricos sem confundi-las com condutores. |
| E07 | Pacotes extensíveis das demais famílias | #pendente | E04, E05, E06 | Entregar representação declarativa e pacotes de reconhecimento para as famílias restantes do inventário, com cobertura auditável. |
| E08 | Detector raster por templates e Hough | #pendente | E03, E04 | Acrescentar família raster capaz de detectar símbolos sem vetores aproveitáveis. |
| E09 | Detector por contornos e grafo de traços | #pendente | E03, E04 | Implementar alternativa estrutural de reconhecimento de formas distinta de correlação de pixels e das heurísticas legadas. |
| E10 | Adaptação à legenda e símbolos desconhecidos | #pendente | E03, E08 | Usar a legenda do próprio documento como fonte local de templates/semântica e oferecer desconhecidos revisáveis. |
| E11 | Experimento de detector visual treinável | #pendente | E02, E03, E07 | Medir um detector local aprendido como fonte adicional, com decisão reproduzível de adoção ou rejeição. |
| E12 | União, validação cruzada e calibração | #pendente | E05, E06, E07, E08, E09, E10, E11 | Entregar reconciliador de símbolos que aproveite exclusivos e resolva duplicatas/conflitos sem quórum. |
| E13 | Associação semântica e promoção por campo | #pendente | E12 | Converter hipóteses reconciliadas em propostas úteis, com associação e promoção coerentes com a evidência. |
| E14 | Revisão visual, API e exportações | #pendente | E13 | Expor símbolos, métodos, exclusivos e conflitos de modo revisável no cliente e nos arquivos exportados. |
| E15 | Execução, cache e ativação controlada no servidor | #pendente | E13, E14 | Integrar a composição habilitada ao job do servidor com memória limitada, cancelamento e assinaturas completas. |
| E16 | Aceite integrado e matriz final de cobertura | #pendente | E15 | Demonstrar a melhoria de cobertura por união e o atendimento integral ao inventário e às regressões, com limites explícitos. |

A execução das etapas deve usar subagentes conforme a divisão abaixo, por solicitação do usuário em 18/09/2026. Paralelismo entre etapas continua sujeito às dependências; paralelismo dentro de uma etapa segue as responsabilidades e fronteiras de escrita definidas para ela.

## E01 — Inventário de símbolos e perfis de referência — #pendente

**Objetivo:** Criar inventário versionado e verificável de famílias, variantes e convenções, incluindo símbolos sem equivalente patrimonial.

**Por que agora:** A cobertura e a semântica precisam de referência antes de criar detectores ou contar acertos.

**Dependências e paralelismo:** Nenhuma. Sem paralelismo nesta etapa inicial.

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

- [ ] Inventário inclui transformador, para-raios MT/BT, aterramento, estai e todas as famílias restantes da F02, com dono e fonte por variante.
- [ ] Perfis CEMIG/externos não compartilham significado por simples aparência; limitações de acesso e revisão constam no registro.
- [ ] Símbolos não patrimoniais e compostos têm destino explícito; nenhum ID aparece duas vezes.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. Inspeção dos localizadores e desenhos, comparação do inventário com o índice completo F02, verificação de IDs/fontes e links. Acrescentar testes de esquema se o registro já for legível por código; sem execução de benchmark nesta etapa. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Fonte textual não captura desenhos: conferir páginas renderizadas e guardar localizadores; lacuna numa variante limita essa variante, não paralisa as demais.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E02 — Benchmark de cobertura e complementaridade — #pendente

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

- [ ] Uma execução sem examples/ gera métricas por família e denominadores, com FP/FN localizáveis.
- [ ] Controle A-acerta/B-falha demonstra ganho da união; duplicatas não aumentam TP e interseção não filtra o candidato.
- [ ] Baseline e reserva têm hashes/partições; CLI exata está documentada, sem métricas inventadas de generalização.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q e execução inaugural V-B. Testar avaliador com saídas-oráculo conhecidas: duplicatas, páginas diferentes, classes ausentes e símbolos finos. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E03 — Contrato de observações e registro de métodos — #pendente

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

- [ ] Round-trip preserva fonte, página, camada, geometria, score bruto e alternativas.
- [ ] Motor fora de domínio ou indisponível não produz voto negativo.
- [ ] Adapter legado passa nos controles e identidade é determinística para a mesma entrada/configuração.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q e V-B em modo legado; testar serialização, assinaturas distintas e origens correlacionadas. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E04 — Robustez vetorial de aterramento e para-raios — #pendente

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

- [ ] Aterramento e para-raios MT/BT mantêm os TP e negativos legados, incluindo barras preenchidas e glifos.
- [ ] Rotação/escala, desenho fragmentado/agrupado e instâncias repetidas mantêm identidade/localização no conjunto E02.
- [ ] Monocromático com situação indeterminada não é confirmado automaticamente como existente.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q, V-B com ablação das normalizações; comparar TP/FP e localização com baseline por estrato. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E05 — Reconhecimento visual de transformadores — #pendente

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

- [ ] Transformadores sem texto geram observações em fixtures de suas variantes cadastradas.
- [ ] Símbolo composto não vira múltiplos ativos por contagem de componentes.
- [ ] Texto incompatível fica como alternativa/conflito e não altera o desenho observado.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-S, V-N, V-Q, V-B por variante de transformador; incluir casos sem literal, duplicados e em legenda. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E06 — Reconhecimento de estais e ancoragens — #pendente

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

- [ ] Estais do inventário geram observações com geometria própria, inclusive sem texto.
- [ ] Controles de estai não criam cabo, vão ou junção elétrica.
- [ ] Ambiguidade de suporte/subtipo é visível e não elimina candidato visual válido.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E07 — Pacotes extensíveis das demais famílias — #pendente

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

- [ ] Toda família E01 tem pacote verificável e testes positivos/negativos ou pendência explícita que impede o aceite integral.
- [ ] Adicionar uma família por dados não exige modificar o reconciliador.
- [ ] Símbolos de legenda, norte e outros informativos não são promovidos a equipamento por estarem reconhecidos.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q e V-B para cada pacote; validar esquema, fontes e cobertura contra inventário. E07 só conclui com os pacotes de todo seu escopo entregues, sem contar desconhecido como reconhecimento. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Escopo grande: lotes por família com IDs estáveis e totalizadores impedem encerramento parcial disfarçado.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E08 — Detector raster por templates e Hough — #pendente

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

- [ ] PDF raster sem vetores produz candidatos corretos que o legado perde.
- [ ] Símbolo na borda do tile mantém caixa na página e uma hipótese, com observações preservadas.
- [ ] Variação de DPI/rotação não gera votação independente nem score declarado probabilidade.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E09 — Detector por contornos e grafo de traços — #pendente

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
2. Comparar subestruturas/descritores com gramáticas E01/E07, tolerando lacunas limitadas e registrando penalidades.
3. Limitar busca combinatória com orçamento explícito; falha/abstenção preservam a observação dos demais.
4. Medir erros correlacionados quando o grafo reutilizar primitives E04 e ganhos de sua entrada raster independente.

**Critérios de aceite:**

- [ ] Casos de traços quebrados/deformados têm acertos exclusivos identificados ou rejeição experimental documentada com ação de melhoria.
- [ ] Grafos visuais não criam junções elétricas automaticamente.
- [ ] A medição distingue diversidade algorítmica de entrada compartilhada.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q, V-B e teste de limite/falha em grafo denso; executar controles de símbolos semelhantes e de componentes separados. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E10 — Adaptação à legenda e símbolos desconhecidos — #pendente

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

- [ ] Convenção local não cadastrada pode gerar candidato através da legenda, com origem e descrição revisáveis.
- [ ] Legenda ausente ou OCR errado não veta candidatos dos demais motores.
- [ ] Símbolo da legenda não vira ativo; template não vaza para outros projetos nem para a reserva.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q, V-B em casos com/sem legenda, descrição trocada, múltiplas legendas e revisões; inspecionar isolamento por documento. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E11 — Experimento de detector visual treinável — #pendente

**Objetivo:** Medir um detector local aprendido como fonte adicional, com decisão reproduzível de adoção ou rejeição.

**Por que agora:** Testa uma família de generalização diferente sem torná-la dependência obrigatória da solução.

**Dependências e paralelismo:** E02, E03, E07. Pode ocorrer em paralelo a E08–E10; treino isolado e sem editar dados/partições congelados.

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
3. Avaliar objetos pequenos, desconhecidos e estilos inéditos, além de complementaridade com E04–E10.
4. Entregar adapter experimental e resultado de adoção por estrato, ou rejeição fundamentada; se faltar dado para executar, registrar bloqueio e ação, sem alegar ensaio concluído.

**Critérios de aceite:**

- [ ] Treino/inferência e avaliação foram executados de forma reproduzível e sem vazamento.
- [ ] Há matriz de acertos/erros exclusivos e decisão de integração por ganho, não por popularidade do modelo.
- [ ] Modelo rejeitado permanece fora da composição; rejeição não elimina obrigações de cobertura restantes.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q e V-B do experimento, com medição de RAM/tempo e repetição determinística quando suportada; registrar comando real de treino, inferência e diferenças numéricas. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Poucos exemplos e custo de CPU: experimento isolado; manter famílias não neurais como composição possível.

**Prompt para uma sessão limpa:**

```text
Execute E11 — Experimento de detector visual treinável de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E02, E03, E07. Objetivo: Medir um detector local aprendido como fonte adicional, com decisão reproduzível de adoção ou rejeição.
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

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.

## E12 — União, validação cruzada e calibração — #pendente

**Objetivo:** Entregar reconciliador de símbolos que aproveite exclusivos e resolva duplicatas/conflitos sem quórum.

**Por que agora:** As saídas independentes e o benchmark permitem avaliar a composição, não apenas motores isolados.

**Dependências e paralelismo:** E05, E06, E07, E08, E09, E10, E11. Integração serial após os handoffs de todos os detectores; E09/E11 podem entregar rejeição experimental válida, nunca falha de execução ocultada.

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
2. Preservar observações, alternativas incompatíveis e rejeições justificadas; ensaiar WBF somente para caixas compatíveis, comparando com seleção da geometria de origem.
3. Calibrar decisões por classe/método/estrato em partição própria, modelando correlação e incluindo ramo de candidato exclusivo elegível.
4. Rodar todos os casos da tabela de política e ablações; congelar composição e thresholds antes do gate reservado.

**Critérios de aceite:**

- [ ] Todos os casos obrigatórios da política passam, inclusive correto exclusivo e maioria correlacionada errada.
- [ ] Composição preserva os exclusivos válidos e não funde objetos distintos/páginas/camadas.
- [ ] Score bruto, probabilidade calibrada, suporte e decisão são campos distintos; falta de amostra mantém revisão.
- [ ] Matriz/ablação mostra contribuição de cada método aplicável; não detecção não vira contradição.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-N, V-Q, V-B completo em desenvolvimento/calibração e regressão `tests/unit/test_method_reconciliation.py`; reserva final permanece lacrada até E16. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Fusão encobre erros ou validação vira consenso circular: manter evidência original, dependências de fonte e justificativa por decisão.

**Prompt para uma sessão limpa:**

```text
Execute E12 — União, validação cruzada e calibração de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E05, E06, E07, E08, E09, E10, E11. Objetivo: Entregar reconciliador de símbolos que aproveite exclusivos e resolva duplicatas/conflitos sem quórum.
Escopo: Novo reconciliador de simbologia em `application/` (proposto), E03 e `application/method_reconciliation.py` como contrato documental a preservar.
Limites: Não exigir unanimidade, fazer média de scores brutos ou reutilizar o filtro de coordenadas de E12B.
Aceite específico: Todos os casos obrigatórios da política passam, inclusive correto exclusivo e maioria correlacionada errada. Composição preserva os exclusivos válidos e não funde objetos distintos/páginas/camadas. Score bruto, probabilidade calibrada, suporte e decisão são campos distintos; falta de amostra mantém revisão. Matriz/ablação mostra contribuição de cada método aplicável; não detecção não vira contradição.
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

1. Conectar resultado E12 à interpretação sem quebrar evidências/documentary readings; mapear todas as famílias E01 para proposta, contexto informativo ou desconhecido.
2. Associar símbolo a suporte/trecho/rotulo considerando documento, página, camada e ambiguidade; separar quantidade de componentes e de ativos.
3. Aplicar política por campo e revisão técnica; preservar exclusivos elegíveis sem quórum, conflitos e classe conhecida com catálogo pendente.
4. Publicar fatos de presença/avaliabilidade somente com origem adequada; distinguir silêncio do detector de ausência física.

**Critérios de aceite:**

- [ ] Símbolo correto exclusivo chega à proposta e pode seguir a política de promoção sem segundo detector.
- [ ] Estai não vira cabo; texto isolado não prova símbolo; legenda não vira ocorrência de rede.
- [ ] Quantidade/situação/associação incertas ficam pendentes e não são completadas pelo catálogo.
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
Aceite específico: Símbolo correto exclusivo chega à proposta e pode seguir a política de promoção sem segundo detector. Estai não vira cabo; texto isolado não prova símbolo; legenda não vira ocorrência de rede. Quantidade/situação/associação incertas ficam pendentes e não são completadas pelo catálogo. Revisão humana e reanálise preservam histórico, vigência e conflitos; conformidade não recebe presença inventada.
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
2. Exibir recorte, classe/situação/quantidade, origem e resumo legível de acordo/divergência; permitir inspeção técnica dos motores sem sobrecarregar o fluxo principal.
3. Permitir correção/rejeição de símbolo desconhecido ou exclusivo e associação, preservando auditoria e controle de conflito.
4. Exportar mesmos estados/pendências no XLSX/PDF quando aplicável; não apresentar score bruto como porcentagem de acerto.

**Critérios de aceite:**

- [ ] Exclusivo, conflitante, desconhecido e informativo são distinguíveis e localizáveis na página correta.
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
Aceite específico: Exclusivo, conflitante, desconhecido e informativo são distinguíveis e localizáveis na página correta. Correção/rejeição persiste e reabertura/exportação mantém o mesmo resultado. Clientes compatíveis consomem payload aditivo e o snapshot OpenAPI corresponde ao código.
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

**Objetivo:** Demonstrar a melhoria de cobertura por união e o atendimento integral ao inventário e às regressões, com limites explícitos.

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
2. Publicar matriz por família/estrato e cada método: isolado, união, interseção de controle, composição e ablação, incluindo exclusivos preservados e custo.
3. Executar V-G, V-Q e fluxo completo de análise/revisão/exportação/cancelamento; conferir classificação, situação, quantidade e associação separadamente.
4. Registrar V-P obrigatório de todos os exemplos reais disponíveis; apontar classes/estratos que seguem em revisão e confirmar todos os critérios globais.

**Critérios de aceite:**

- [ ] Todos os critérios globais e as metas congeladas aplicáveis passam; família não atendida impede aceite integral.
- [ ] União final demonstra recuperação de acertos exclusivos e ganho sobre baseline, com FP e denominadores publicados.
- [ ] Todos os métodos têm avaliação e decisão de adoção/rejeição; ao menos duas famílias algorítmicas distintas contribuem com acertos exclusivos validados.
- [ ] Não há unanimidade/quórum escondido; contratos, histórico, jobs e exportações passam nos testes obrigatórios.
- [ ] Relatório distingue validação sintética, generalização real disponível e automação não homologada por falta de evidência.

**Validação obrigatória:** V-P e conferência das entregas dos subagentes, com as particularidades acima. V-B reservado, V-Q, V-G e inspeção manual dos casos obrigatórios da política na UI/exportação. Não concluir se teste obrigatório não foi executado ou meta falhou. Os códigos V-* remetem aos comandos completos acima; registrar os comandos efetivamente executados.

**Bloqueios:** Nenhum bloqueio conhecido para iniciar respeitando as dependências. Lacunas de dados/fontes são riscos até impedirem concretamente a execução ou o aceite; nessa ocorrência, registrar causa, evidência, impacto e ação de desbloqueio.

**Riscos e mitigação:** Otimizar no conjunto final ou omitir classes difíceis: lacrar configuração, preservar resultados reprovados e publicar matriz completa.

**Prompt para uma sessão limpa:**

```text
Execute E16 — Aceite integrado e matriz final de cobertura de docs/roadmap-analise-simbologia.md no Zeny Project Handler, aberto na raiz.
Leia primeiro as instruções aplicáveis do repositório, o roadmap completo, os arquivos de escopo desta etapa e git status/diff. Preserve alterações preexistentes. Verifique divergências do código e evidências de conclusão das dependências antes de iniciar.
Dependências: E15. Objetivo: Demonstrar a melhoria de cobertura por união e o atendimento integral ao inventário e às regressões, com limites explícitos.
Escopo: Este roadmap, fixtures/avaliador E02, pipeline, API/UI/exportações e handoffs relacionados; novo relatório final em `docs/` (proposto).
Limites: Não baixar metas, ajustar sobre a reserva ou declarar concluídos aceites históricos de outro escopo.
Aceite específico: Todos os critérios globais e as metas congeladas aplicáveis passam; família não atendida impede aceite integral. União final demonstra recuperação de acertos exclusivos e ganho sobre baseline, com FP e denominadores publicados. Todos os métodos têm avaliação e decisão de adoção/rejeição; ao menos duas famílias algorítmicas distintas contribuem com acertos exclusivos validados. Não há unanimidade/quórum escondido; contratos, histórico, jobs e exportações passam nos testes obrigatórios. Relatório distingue validação sintética, generalização real disponível e automação não homologada por falta de evidência.
Validação: V-B reservado, V-Q, V-G e inspeção manual dos casos obrigatórios da política na UI/exportação. Não concluir se teste obrigatório não foi executado ou meta falhou. Consulte a seção de validações do roadmap para os comandos completos; descubra somente os comandos novos indicados e registre-os.
Delegue a etapa a subagentes com estas frentes: A — Integração: preparar checkpoint/configuração e reproduzir o fluxo completo; nesta frente não ajustar algoritmos sobre a reserva. B — Testes: executar V-Q/V-G/V-B reservado, auditar métricas/ablações e confirmar independência da reserva. C — PDFs: validação final independente de toda a coleção, páginas/camadas e saídas da composição, com cobertura reconciliada ao manifesto. Coordene assim: Coordenador consolida aceite e relatório; correção necessária volta à etapa responsável, recebe novo checkpoint e revalidação antes de fechar o gate. Atribua um responsável por arquivo, use ondas conforme a capacidade e entregue contratos/checkpoints estáveis aos consumidores. Você integra e atualiza o roadmap.
Execute V-P no escopo desta etapa: todos os PDFs recursivos em examples/ e todas as páginas, com manifesto, inspeção real de imagens por IA antes de comparar predições e registro de FP/FN, exclusivos e ambiguidades. Não alegue revisão visual a partir de JSON/OCR apenas; não alimente o algoritmo com a referência do revisor. Em E01 faça o inventário; em E02 construa o runner/baseline; em E03 confira o round-trip. Preserve a reserva sintética até E16; exemplos já inspecionados são desenvolvimento. Registre cobertura/falhas, ausência de exemplos ou de ferramenta de subagentes, sem simular validação concluída.
Exija retornos verificáveis dos agentes, resolva divergências por evidência e rode a integração no checkpoint final; registre delegações, arquivos e resultados no handoff.
Ao iniciar, sincronize #em-andamento no índice e detalhe. Implemente somente esta etapa, acrescente/atualize os testes necessários e a documentação correspondente. Preserve a união dos candidatos exclusivos: silêncio de outro algoritmo não é veto, e concordância não é probabilidade.
Não declare sucesso com validação obrigatória falhando ou não executada. Atualize para #concluida somente após todos os critérios; impedimento real exige #bloqueada com causa, evidência, impacto e ação de desbloqueio. Dependência ainda pendente mantém #pendente. Preencha Evidências e handoff com arquivos, decisões, comandos, resultados e limitações. Não crie commit, publique ou implante sem autorização explícita. Termine com resumo conciso de mudanças, validações e pendências.
```

**Evidências e handoff:** ainda não executada. Registrar também agentes/papéis, fronteiras de escrita, checkpoint integrado, revisão independente, manifesto V-P e total de PDFs/páginas conferidos/bloqueados. Ao trabalhar, registrar arquivos alterados, versão/configuração, decisões, fontes/fixtures, comandos e resultados, métricas comparadas, limitações e próximo passo.
