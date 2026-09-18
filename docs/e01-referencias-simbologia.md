# E01 - Referências e conferência visual de simbologia

Revisão em 18/09/2026, frente A (`/root/a_referencias`), a partir do checkpoint
`5ee65d3`. Responsabilidade exclusiva desta frente: este relatório e
`tmp/e01-simbologia/referencias/`. O coordenador consolida o registro versionado,
as atribuições por variante e o roadmap. Não houve alteração de detector,
catálogo ou regra de conformidade nesta frente.

## Fontes e alcance real da revisão

| Fonte | Edição identificada | Acesso e revisão realizados | SHA-256 do PDF |
|---|---|---|---|
| F01 - CEMIG ND-3.1 | Jul/2025; 111 páginas | PDF oficial aberto e baixado; inspeção da imagem da página PDF/impressa 88, item 2.2. Confirma a remissão a IT-EO-008. Não se declara nova leitura integral da ND-3.1. | `ea43a729d3edd5896201b292f6fa385071a3f9d980fa0d82653ef5c637e89b77` |
| F02 - CEMIG IT-EO-008 | Revisão 3, 29/07/2024; 45 páginas | Todas as 45 páginas renderizadas e efetivamente vistas por IA, incluindo capa, revisões, índice, desenhos e rascunhos. Página PDF e impressa coincidem. | `0e29f0ea81827c7235d0893c383fc993c78378c51e930b8b8228de82d564ce04` |
| F03 - IEC 60617 DB | Revisão individual de símbolos não acessada | Página pública TC3 lida em 18/09/2026: confirma acesso da base mediante assinatura. Não houve acesso à base, download pago, revisão de desenhos nem equivalência atribuída. | Não aplicável: nenhum PDF/base adquirido |
| F04 - UK Power Networks, NetMAP Symbols Booklet, East of England | Versão 1.2, out/2010; 15 folhas PDF | Todas as 15 imagens conferidas. A folha 1 contém capa (i) e índice (ii); folhas 2-14 contêm páginas impressas 1-26, duas por folha; folha 15 contém a página 27. Referência histórica, sem confirmação de vigência operacional em 2026. | `fec7a0e6b600db5862f7897cfabbe750a4dfa8c1687544f921eeb93d03343c26` |

Endereços oficiais efetivamente abertos:

- [F01 - ND-3.1](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
- [F02 - IT-EO-008](https://www.cemig.com.br/wp-content/uploads/2025/10/IT-EO-008_Simbologia_EO.pdf).
  O [portal CEMIG PART](https://www.cemig.com.br/normas-tecnicas/construcao-de-redes-de-distribuicao-por-particulares/)
  foi conferido e seu link de anexo IT-EO-008 foi seguido até esse mesmo PDF.
- [F03 - IEC TC3](https://tc3.iec.ch/tc-activity/graphical-symbols-for-diagrams/).
- [F04 - cópia publicada pelo governo britânico](https://assets.publishing.service.gov.uk/media/66daf995e87ad2f121826583/UK_Power_Networks_4_checked.pdf).

Os PDFs, textos extraídos e rasters ficam somente em `tmp/`. Disponibilidade pública
não é autorização de redistribuição dos desenhos: o registro versionado contém
metadados, localizadores e observações, sem incorporar biblioteca gráfica normativa.
F02 traz a classificação documental “Direcionado”, embora publicado no portal público.
F04 marca vários quadros para uso UKPN e alerta sobre variações locais. Nenhum desses
avisos foi convertido em licença de reutilização. A IEC mantém acesso por assinatura.

## Denominador de F02 e contrato entregue

O inventário entrega **427 registros de referência em 33 seções**, definidos por
célula/desenho e estado mostrado, mais convenções textuais. Não são 427 ativos nem
427 formas geometricamente distintas. A introdução conta como um registro de contexto;
as anotações de objetos contam três registros; a seção de montagem conta três símbolos
e três anotações. Esta definição impede apagar os elementos informativos do índice.

Cada célula que mostra um desenho com vários materiais, subtipos, propriedades ou
situações alternativas mantém essas alternativas juntas no nome/campo de situação.
Não se inventou um produto cartesiano de combinações não desenhadas. Por exemplo, a
mesma célula de concreto retangular/madeira duplo U/ferro/desconhecido não autoriza
deduzir material pela forma; os templates de aterramento mono/trifásico do final de
§32 compartilham uma célula. Estados visualmente distintos têm registros distintos.

`variantes-f02.json` contém `section`, `family`, `name`, `source_kind`, `pdf_page`,
`printed_page`, `locator`, `visual_note`, `kind`, `world`, `situation`,
`operating_state` e `ambiguity`. `source_kind` conserva EC/AEC/INS/AV/CNX/CTR/DES,
ou contexto/anotação. G/I são conservados como valores do manual, sem converter
mundo de desenho em camada inferida. Lista `situation` vazia significa que a linha
não declara situação, não “existente”. N/A e traço permanecem marcadores de origem.

O localizador numera os desenhos/anotações da seção presentes naquela página, de
cima para baixo, sem contar cabeçalhos. A célula contínua na página seguinte é
localizada na página em que o desenho é mostrado. A única mudança de ordem de
transcrição irrelevante ao conteúdo seria detectável pelo nome e página; os
localizadores entregues seguem a sequência visual conferida.

| § | Família/tópico | Páginas PDF/impressas com conteúdo | Registros |
|---:|---|---|---:|
| 1 | Introdução | 5 | 1 |
| 2 | Anotações de objetos | 5 | 3 |
| 3 | Poste | 6-8 | 25 |
| 4 | Rota subterrânea | 8 | 1 |
| 5 | Caixa subterrânea | 9-10 | 13 |
| 6 | Câmara | 10-11 | 9 |
| 7 | Plataforma | 11 | 5 |
| 8 | Poste AT | 12 | 6 |
| 9 | Subestação | 12 | 4 |
| 10 | Estrutura poste MT | 13 | 5 |
| 11 | Torre AT | 13 | 3 |
| 12 | Estrutura poste AT | 14 | 3 |
| 13 | Estrutura montagem MT/BT | 14 | 6 |
| 14 | Estai MT | 15 | 15 |
| 15 | Estai AT | 16 | 2 |
| 16 | Cabo aéreo | 16-17 | 22 |
| 17 | Cabo subterrâneo | 18-19 | 17 |
| 18 | Transformador | 19-21 | 27 |
| 19 | Conector | 22-23 | 17 |
| 20 | Equipamento interrupção | 23-26 | 40 |
| 21 | Equipamento proteção | 27-28 | 15 |
| 22 | Equipamento regulação | 28 | 5 |
| 23 | Equipamento associado | 29-30 | 16 |
| 24 | Transformador terciário | 30 | 2 |
| 25 | Transformador de medida | 30-31 | 4 |
| 26 | Usina | 31 | 1 |
| 27 | Iluminação pública | 31-32 | 13 |
| 28 | Ponto conexão | 32 | 4 |
| 29 | Ponto medição | 32 | 1 |
| 30 | Concentrador primário | 33 | 1 |
| 31 | Concentrador secundário | 33 | 1 |
| 32 | Equipamento composto | 33-38 | 51 |
| 33 | Desenho rascunhos | 38-45 | 89 |
| | **Total** | **33/33 seções** | **427** |

Os limites finais foram conferidos pelas imagens, não estimados a partir do próximo
início no sumário. Por função: 249 candidatos patrimoniais sujeitos a revisão, 81
compostos/associados/componentes, 89 não patrimoniais e oito convenções. Candidato
patrimonial não implica correspondência ao catálogo atual: mobiliário urbano, apoio,
conectividade e estai precisam de destino próprio na consolidação.

## Evidências que limitam a interpretação

- **Aterramento:** §19, página 22, quatro estados; três barras decrescentes. Ponto de
  aterramento temporário é outra linha, com extremidade aberta; não é sinônimo de
  aterramento permanente. Os equivalentes de rascunho estão em §33, página 43.
- **Para-raios:** §21, página 27: BT com retângulo/diagonal e MT com quatro barras
  alternadas, cada um com quatro estados. AT tem outro desenho. Indicador de defeito
  também consta nessa página. Resistor e SLV continuam na página 28. Rascunhos MT/BT
  ficam na página 44 e não herdam conectividade.
- **Transformador:** §18, páginas 19-21, distingue uso, chave deslocada, mundo G/I,
  autotransformador e estado. A seção também contém regulador de tensão; não reduzir
  sua semântica ao título. §23 tem o transformador associado e religador+transformador;
  §24/§25 tratam terciário/medida. Rascunhos ficam nas páginas 39-40 e 44.
- **Estai:** §14, página 15, tem âncora, cruzeta-cruzeta, poste-poste, cruzeta-poste
  com seccionamento e cruzeta-poste, cada qual em três grupos de situação. §15,
  página 16, mostra duas variantes AT. §33 páginas 42-43 inclui rascunhos, com
  diferenças visuais de extremidade; não tratá-los como cabo ou ativo automático.
- **Situação não é posição operada:** §20 usa vermelho/verde para fechado/aberto.
  Poste a instalar pode usar preenchimento preto; cabo AT usa cor para tensão e
  situação N/A; anotações usam caixa/tachado. Em §33, vermelho ocorre até em desenhos
  chamados existentes. Logo, cor isolada não define a situação global do perfil.
- **Compostos:** §32 apresenta 51 células/templates, incluindo barramentos, QDP,
  caixas, BTX/BQX, terminais e chaves de múltiplas vias. Cada conjunto preserva sua
  identidade; círculos, fusíveis e terminais não viram quantidade automática de ativos.
- **Não patrimoniais:** o texto introdutório de §33 na página 38 informa que os
  rascunhos não têm conectividade elétrica e são excluídos da publicação. Todos os
  seus 89 desenhos têm destino informativo. Elipse, marca X, árvore, casa, cerca,
  ônibus, obstáculo, base e cópias de equipamentos precisam permanecer no denominador.
- **Negativos confundíveis:** tabelas, molduras, letras, símbolos de legenda, pontos
  de inserção magenta, barras de cortes, cercas, rascunhos e componentes de conjuntos
  devem ser reconhecidos como contextos possíveis; sem detector executado nesta etapa,
  nenhum deles recebe contagem inventada de FP/FN.

A leitura de `src/zeny_project_handler/adapters/analysis/pymupdf_symbols.py`
confirmou o literal `_SYMBOL_SOURCE = "SIMBOLOGIA.pdf"`, score fixo `0.88`, três
classes e `_situation_from_color` associando verde/vermelho/preto a
instalar/remover/existente. O arquivo não contém URL, revisão ou hash que prove
identidade com F02. As cores e envolventes observadas em F02 mostram que essa regra
legada não pode ser atribuída ao perfil inteiro. Isso é uma divergência documental
para E03/E04, não uma correção de algoritmo ou medição de erro realizada na E01.

## F04: perfil externo revisado, sem equivalência automática

A cópia é inteiramente raster: 15 imagens, zero desenhos vetoriais e zero páginas com
texto extraível por PyMuPDF. A revisão acima foi feita olhando as 15 imagens, inclusive
as colunas NetMAP/escaneado, não inferida dessa extração vazia. A capa delimita East of
England, admite variações locais e pede confirmação da edição junto à operadora.

| Folha PDF | Páginas impressas | Conteúdo conferido visualmente |
|---:|---|---|
| 1 | i-ii | Capa, versão, escopo e índice |
| 2 | 1-2 | Notas de uso e mapa de abrangência |
| 3 | 3-4 | Cartografia: grade, cerca, prédio, meio-fio, limites, áreas e água |
| 4 | 5-6 | Áreas históricas/ambientais e sensibilidade de cabos com fluido |
| 5 | 7-8 | Cabos primários/secundários, tensão, piloto; diferenças cor/escaneado |
| 6 | 9-10 | Serviços, terminações, iluminação e dutos vazios/ocupados/múltiplos |
| 7 | 11-12 | Subestações, link boxes, feeder pillars, postes, transformador e avisos |
| 8 | 13-14 | Emendas, derivações, terminais, reparos e pontas de cabo |
| 9 | 15-16 | Cortes, setas, cabos, dutos e camadas de proteção |
| 10 | 17-18 | Abreviações e terminologia |
| 11 | 19-20 | Rede aérea por escala, poste, estai, escora, regulador e identificação |
| 12 | 21-22 | Estais/apoios e rede HV; torre, transformador, fusível e religador |
| 13 | 23-24 | Diagrama LV: linhas/cabos por material/tipo e ligação de postes |
| 14 | 25-26 | Emendas, subestações, transformadores e exemplos de conjuntos |
| 15 | 27 | Link boxes e feeder pillars, exemplos com ponto aberto e vistas ampliadas |

Controle concreto de diferença: o triângulo da página impressa 11 identifica um
*service turret*; o triângulo com aviso da página 12 indica informação ausente. Nenhum
recebe classe CEMIG por parecer transformador. Círculos podem combinar aparelhos na
página 22 e representar transformadores/apoios no diagrama LV. Sem escala, vista,
região e legenda compatíveis, o resultado permanece hipótese do perfil externo.
Nenhum template UKPN foi habilitado; a revisão visual não certifica licença,
vigência em 2026 ou equivalência operacional brasileira.

## Checkpoint, comandos e entregas verificáveis

Foram usados PyMuPDF 1.28.0 e Python 3.12 da `.venv`. Os PDFs são as cópias oficiais
listadas; a extração textual serviu para soletrar rótulos depois da inspeção das
imagens. O primeiro `Invoke-WebRequest` no sandbox falhou por permissão de socket;
a repetição com permissão de rede aprovada concluiu os três downloads (exit 0).

```powershell
Invoke-WebRequest -Uri 'https://www.cemig.com.br/wp-content/uploads/2025/10/IT-EO-008_Simbologia_EO.pdf' -OutFile 'tmp/e01-simbologia/referencias/F02.pdf'
Invoke-WebRequest -Uri 'https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf' -OutFile 'tmp/e01-simbologia/referencias/F01.pdf'
Invoke-WebRequest -Uri 'https://assets.publishing.service.gov.uk/media/66daf995e87ad2f121826583/UK_Power_Networks_4_checked.pdf' -OutFile 'tmp/e01-simbologia/referencias/F04.pdf'
.\.venv\Scripts\python.exe tmp/e01-simbologia/referencias/render_fontes.py
.\.venv\Scripts\python.exe tmp/e01-simbologia/referencias/build_variantes.py
Get-FileHash -Algorithm SHA256 tmp/e01-simbologia/referencias/variantes-f02.json,tmp/e01-simbologia/referencias/indice-f02.json,tmp/e01-simbologia/referencias/totais-f02.json
```

Renderização: F01 1 página, F02 45, F04 15, exit 0. As 61 imagens foram abertas
na ferramenta `view_image` da sessão, em lotes de até seis; não há declaração de
revisão visual automatizada pelo script. `build_variantes.py` passou seus asserts:
33 seções, 427 localizadores únicos, todas as páginas dentro dos intervalos e todos
os PNGs presentes. Os testes finais de esquema e integração são responsabilidade
da coordenação/frente B.

Entregas locais congeladas para consolidação:

- `tmp/e01-simbologia/referencias/variantes-f02.json`: 427 registros;
  SHA-256 `65a881fd18dad15666dc3094b9b9c3a59f0d72a5c966d1984afe76a0f2e09b39`.
- `tmp/e01-simbologia/referencias/indice-f02.json`: 33 entradas e intervalos reais;
  SHA-256 `deca20c9efdf12d00b4fa87df3de1cdb2d0f4cd0904a3fca2d8b6e594dabd8f4`.
- `tmp/e01-simbologia/referencias/totais-f02.json`: denominador por seção/função;
  SHA-256 `b591556be5be05e583194460d79f1cba0bd4a07e34340f895697ed162cf8255b`.
- `tmp/e01-simbologia/referencias/manifesto-fontes.json`: hashes dos PDFs, páginas
  renderizadas/vistas, metadados, contagens de imagens/vetores/texto.
- `F01.pdf`, `F02.pdf`, `F04.pdf`, `Fxx-pNN.png` e `Fxx-pNN.txt`: cópias e evidência
  temporárias, fora do Git. Scripts locais reconstroem a transcrição/renderização,
  mas não substituem nova inspeção se o hash da fonte mudar.

Limitações entregues: IEC somente metadados; UKPN histórico sem vigência/licença
certificada; literal legado `SIMBOLOGIA.pdf` não identificado por esta frente.
A coordenação mantém o perfil legado separado. Nenhum benchmark, detector, TP/FP/FN,
exclusivo de motor ou reserva sintética foi executado/consumido. A auditoria dos PDFs
locais de `examples/` pertence à frente C e não é substituída pela leitura normativa.
