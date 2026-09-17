# Validação E08/E09 e release 0.4.0

Retomada em 17/09/2026 sobre `d60fe05`, inicialmente sem alterações locais.
Solicitação: executar o possível de E08/E09, gerar o próximo deploy e remover o roadmap.
Os relatórios E08/E09 anteriores são históricos; este documento registra a retomada.

## Resultado técnico

O falso realce amplo de para-raios foi corrigido na origem. O detector confundia uma
linha da rede e contornos de letras com haste e barras de equipamento. A extração
**1.18.0** exige linearidade geométrica nas hastes/barras e corpo retangular na
assinatura de para-raios BT; retângulos estreitos preenchidos continuam aceitos como
barras. Curvas não lineares e polígonos angulares de glifos não satisfazem essas
assinaturas. Os vetores originais permanecem disponíveis: a correção não esconde
marcações na UI, corta caixas arbitrariamente nem altera o PDF.

Três regressões sintéticas reproduzem falsos equipamentos no código anterior
(elipse, glifo curvo e glifo angular) e passam com a correção. O controle positivo
preserva aterramento com barras preenchidas; os testes anteriores preservam
aterramento, para-raios MT/BT e suas situações. Os 46 testes do analisador passaram.

A versão semântica continua **25.0**, conformidade **14**, API/piso **1.6.0**.
A versão do extrator invalida o cache anterior. Reanálises com decisões humanas
continuam sujeitas à reconciliação existente, sem transportar decisões para outros IDs.

Os metadados de build e de verificação da release passaram a importar a versão da
API do contrato canônico, eliminando o valor obsoleto 1.5.0. As notas descrevem as
funcionalidades atuais e as pendências de homologação. Os seis testes de release passaram.

## PDF real e topologia

Fonte local: NS 1256148225, SHA-256
`1e824e972d5cfc0b19fbcae774321d371cff30f6a8d1dfcb3673db858e6c77df`.
Inventário E07 reconciliado, denominadores e tolerância 0,01 preservados.

| Verificação | Antes desta retomada | Após a correção |
| --- | ---: | ---: |
| Ocorrências com código, situação e evidência própria | 95/95 | 95/95 |
| Vínculos operacionais dessas ocorrências | 95/95 | 95/95 |
| Pares de endpoints visíveis corretos | 18/18 | 18/18 |
| Comprimentos no traçado correto | 18/19 | 18/19 |
| Trechos físicos com todos os condutores e situações | 20/20 | 20/20 |
| Leituras extras nas categorias pontuadas | 1 | 1 |
| Propostas simbólicas falsas investigadas | 8 | 0 |

A projeção física já entregue em E14 foi validada nesta referência: cada um dos 20
traçados corresponde a exatamente um trecho físico, com conjunto exato de propostas
membro e situações preservadas. A limitação histórica de representação foi superada.
As **35 linhas de Vãos** continuam sendo a projeção por cabo confirmado; não representam
35 trechos físicos. Classificação desconhecida permanece explícita.

A auditoria antiga dependia de IDs de OCR da execução E07 e produziu inicialmente
48 correspondências após as mudanças de extração. O auditor local foi corrigido para
recalcular os candidatos a partir dos mesmos tokens exatos, ROIs e tolerância da
referência. O mesmo procedimento foi aplicado ao baseline e ao resultado final,
sem alterar inventário ou metas. A primeira medição com IDs antigos não é evidência
de perda de 47 ocorrências no produto.

Saída final: 3.724 evidências (419 OCR), 103 propostas brutas, **99 finais**,
189 relações, 35 confirmações e zero diagnósticos de execução. As 99 propostas
compreendem 95 ocorrências inventariadas, uma leitura duplicada e três equipamentos
fora do denominador. As oito propostas falsas removidas eram conflitantes, não
ativos confirmados. DTOs e células das três abas XLSX foram conferidos pelo benchmark.

Tempos observados: nativo 16,506 s (19,839 s com Resultados/exportação); OCR
251,662 s (256,953 s com Resultados/exportação). Build e testes ocorreram parcialmente
em paralelo; esses tempos são observacionais, não comparação de desempenho nem
critério de aceite. Não foi repetido o monitoramento de pico de memória desta rodada.

Inspeção do componente Qt com DTOs finais: sete seleções iniciais e duas seleções
adicionais em V6-7 passaram; capturas O062, O069 e O071 inspecionadas. O retângulo
amplo de equipamento não reaparece; os realces acompanham os rótulos dos cabos.
O harness offscreen inicial não carregava a fonte Segoe UI; ela foi carregada na
repetição de V6-7. A inspeção não certifica a matriz completa de monitores/escala.

## Pendências de aceite

E08/E09 **continuam sem aceite integral**, apesar da correção do defeito visual e
da validação do agrupamento físico:

- T02/V2-3: 13 m permanece sem associação automática inequívoca. As duas melhores
  candidatas continuam próximas; a margem não foi reduzida para favorecer esta folha.
  Ambos os cabos permanecem conflitantes quanto ao comprimento.
- Os 17 postes não têm formato/material suficiente para escolher um modelo único.
  As entregas não têm evidência inequívoca de PADRÃO. A classe não foi presumida pela
  proximidade com casa ou por necessidade de promover estruturas.
- A extração atual encontra duas leituras sobrepostas de N4(1) em P1: OCR geral
  de baixa confiança e leitura de contornos. A diferença entre as áreas supera a
  guarda atual de deduplicação. Uma proposta excedente permanece conflitante;
  não houve ativo extra confirmado. Resolver exige consolidar evidências sem fundir
  ocorrências legítimas próximas, repetidas ou em páginas distintas.
- Os bloqueios independentes do segundo PDF permanecem no
  [relatório E15](e15-aceite-integral-segundo-pdf.md). Esta release não homologa sua
  documentação integral nem amplia a evidência dos conjuntos reservados.

## Gate público e integração HTTP

`IniciarTestes.bat`: **saída 0, 1.370 testes em 553,34 s, cobertura 87,92%**
(mínimo 85,01%). Dependências, Ruff, formatação, Mypy, fronteira do cliente magro e
complexidade aprovados; 2.857 funções/métodos, nenhum rank E/F. As três verificações
privadas de integridade do inventário passaram, sem tornar PDFs locais dependência
do gate público. `git diff --check` aprovado.

Servidor HTTP com armazenamento isolado, OCR real e adaptadores SQL fake:
upload e job completos, 99 propostas e 35 linhas de Vãos iguais ao benchmark;
20 trechos físicos também conferidos no DTO e na terceira aba de Resultados.
As três escolhas Rural/Urbano/Ambos preservaram o snapshot anterior como desatualizado;
três versões antigas foram recusadas com 409. Os novos snapshots/exportações
registraram 1/8/8 achados, respectivamente. Downloads de Resultados, Documentação,
conformidade e PDF anotado passaram por validação de tamanho e SHA-256.
A inicialização consultou uma vez o classificador fake. Não houve consulta de ação
aplicável nesta folha nem uso de SQL Server operacional. Hash da origem preservado.
A repetição após reiniciar o runtime reutilizou a sessão persistida, refez as três
escolhas/exportações e terminou com **zero consultas ao classificador**. O PDF anotado
conservou as 13 anotações originais e acrescentou um callout (14 no total).

## Distribuição e evidências

Release local em `dist/release/0.4.0/`, separada em cliente Windows e kit servidor.
Contém ZIP autocontido, imagem Docker exportada, Compose sem build, exemplos sem
segredos, guias, SBOMs, notas, manifesto e SHA-256. A release anterior foi preservada.

Build e gate estático: **aprovados**. Gate de distribuição em hosts temporários:
**aprovado**, incluindo `docker load`, executável autenticado sem checkout/Python
no PATH, rejeição de API incompatível, ausência de segredos nos artefatos e
persistência depois de recriar o container. API 1.6.0 antes/depois da recriação.
Imagem: `zeny-project-handler-server:0.4.0`; digest:
`sha256:0c0a81e033c9e7e555ef79f53f6d65ad1c71e61613f1c9e583d955ec76967b09`.

A distribuição foi gerada e ensaiada localmente; nenhum servidor operacional foi
atualizado. O roadmap `docs/roadmap-mercado-paineis-leitura-rede.md` foi removido após
a geração e validação da distribuição, conforme solicitado. Seu histórico permanece
no Git. Não houve commit ou push nesta execução.

Evidências privadas em `tmp/e08-e09-resume/`: `baseline.json`, `final.json`,
`baseline-audit.json`, `final-audit.json`, `physical-final.json`, capturas e logs.
PDFs, dados e resultados privados permanecem ignorados; testes públicos são sintéticos.
