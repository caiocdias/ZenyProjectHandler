# E01 — Revisão independente do inventário

Frente B, agente `b_inventario`, em 18/09/2026. Base recebida:
`5ee65d38cefc8a5344206c714cd6ff2d2360ebcd`. O coordenador é o responsável pelo registro,
esquema e integração; A pelo relatório de referências; C pelo inventário visual dos exemplos.
Esta frente escreve somente este relatório e `tests/unit/test_symbol_inventory.py`.

## Contrato e limites

O registro em `docs/data/inventario-simbologia-v1.json` é documental. O esquema em
`docs/schemas/inventario-simbologia.schema.json` não ativa detectores, altera conformidade
ou vincula automaticamente classes a itens patrimoniais. A inspeção do módulo legado
`pymupdf_symbols.py` confirmou três classes e a origem literal `SIMBOLOGIA.pdf`; esse literal
não comprova correspondência com F02.

O teste usa apenas biblioteca padrão e pytest. Seu helper implementa o subconjunto explícito
de JSON Schema usado pelo documento e rejeita keywords não suportadas. Não é uma biblioteca
geral de JSON Schema nem um consumidor operacional. A verificação estrutural não comprova
correção visual, acesso remoto, vigência ou licença das fontes.

Os IDs únicos são definições de fontes, perfis, famílias e variantes. Referências a esses IDs
e linhas de totalizadores podem repeti-los. O denominador de variantes é separado dos
33 itens do índice F02 e de quantidades físicas de ativos. Cada perfil, inclusive sem variantes
acessíveis, deve aparecer no totalizador; toda família cadastrada deve ter variantes.

## Checagens da primeira onda

- Nenhum `AGENTS.md` aplicável foi encontrado nos ancestrais, raiz, docs ou testes.
- Lidos o roadmap, inventário de fontes normativas, guia de exemplos, módulo legado e
  convenções de pytest, ruff e mypy. Na leitura inicial desta frente, o único diff era a
  atualização do roadmap pelo coordenador.
- Contrato alinhado com o coordenador antes da escrita dos testes: proveniência por variante,
  perfil explícito, destino, função, situação, cardinalidade, limitações e totais verificáveis.
- Cobertura implementada: esquema, unicidade global, referências internas, localizadores em
  páginas válidas, isolamento por perfil, destinos não patrimoniais/compostos, índice completo
  F02 e totalizadores. Casos inválidos são introduzidos por mutação de cópias do registro.
- Nenhum motor, benchmark ou reserva sintética foi executado/consultado nesta frente.

## Checkpoint final

Registro consolidado conferido após as entregas A/C, sem editar o registro ou os relatórios
dessas frentes. **Aprovado na revisão B:** 427 variantes, 33 famílias, cinco perfis e seis fontes;
471 IDs de definição globalmente únicos. Os quatro perfis sem variantes aparecem com total
zero, sem incorporar desenhos externos ou origem legada como equivalentes de CEMIG.

| Artefato | SHA-256 conferido |
|---|---|
| `docs/data/inventario-simbologia-v1.json` | `e3d49d9b0072f9f30ea98e2171c0cd520a819a15b329590cfbf35f508f042fcd` |
| `docs/schemas/inventario-simbologia.schema.json` | `afe4f05257d0bb8c6743de9738cd68aa105f30d17ed0a2d2a05b1cfed43760b8` |
| `tests/unit/test_symbol_inventory.py` | `dc5e7027c7a694cd46cebf5490514d6958aaa36eddb3b2ea498027fdd6eb12af` |
| `docs/e01-referencias-simbologia.md` | `e8b771561da21c255d562ab3622c7dda3f7103d9a0613101efd221575978bdf4` |
| `tmp/e01-simbologia/visual/relatorio.md` | `deca10f16405e46437961b2e6e975b68cfea43bb915436a7d99599482e84d1aa` |
| `tmp/e01-simbologia/revisao/checkpoint.json` | `9e367ec1b832834a48347043c26058d9105cd9445caa06f67ebabd114c969cb3` |

A auditoria independente comparou todas as 427 células do registro ao congelamento A por
página e localizador. Nome, tipo de fonte, nota visual, mundo, situações alternativas,
posição operada, ambiguidade e seção/família foram preservados. Nenhuma célula foi perdida,
repetida ou situada fora da seção. Os testes congelam o denominador por seção, rejeitam
localizadores repetidos mesmo com IDs distintos e rejeitam perda com totais recalculados.

Os 17 estais operacionais têm destino de relação mecânica e dono E06. Aterramento permanente
e para-raios MT/BT têm variantes explícitas e dono E04; transformadores vão para E05. Os
reguladores incluídos na seção 18 conservam classe própria e dono E07. Os 89 rascunhos de
§33 permanecem informativos. Cargas externas em §27 têm destino de contexto e não adquirem
correspondência ao catálogo da distribuição. Os 81 registros de compostos/associados/componentes
mantêm revisão do conjunto; sua quantidade de formas não determina quantidade física.

Conferidos os relatórios A e C. C registra 11 PDFs/11 páginas, base e aparência, 108 imagens
realmente vistas, 22 achados e zero falhas; seu verificador informa 597 checagens. Esta frente
leu a entrega de C, sem alegar uma segunda inspeção visual de todos os exemplos. FP/FN,
exclusivos e benchmark continuam não avaliados em E01; exemplos são desenvolvimento e a
reserva sintética permanece preservada.

## Comandos e resultados desta frente

Executados na raiz, com Python 3.12.14/pytest 8.4.2 da `.venv`:

```powershell
.\.venv\Scripts\python.exe tmp/e01-simbologia/revisao/auditar_checkpoint.py
.\.venv\Scripts\python.exe -m pytest tests/unit/test_symbol_inventory.py
.\.venv\Scripts\python.exe -m ruff check tests/unit/test_symbol_inventory.py
.\.venv\Scripts\python.exe -m ruff format --check tests/unit/test_symbol_inventory.py
.\.venv\Scripts\python.exe -m mypy tests/unit/test_symbol_inventory.py
git diff --check
```

Resultados finais: auditoria 427/427 células, exit 0; **38 testes passam em 1,71 s**, exit 0;
ruff check, format e mypy do arquivo passam, exit 0; `git diff --check` sem erro. Foi usado
`ruff format` antes desse congelamento. Duas anotações de tipo do helper de mutação foram
corrigidas após o primeiro mypy; nenhuma flexibilização do registro foi feita para aprovar teste.

O pytest emitiu `PytestCacheWarning` porque `.pytest_cache/v/cache/nodeids` não permitiu escrita.
A coleta e os 38 testes terminaram normalmente; nenhum dado privado, rede ou detector foi usado.
Os testes são portáteis e não leem os artefatos de `tmp/`; o script adicional de auditoria local
usa o congelamento A e grava apenas `tmp/e01-simbologia/revisao/checkpoint.json`.

Sem pendências impeditivas nesta frente. Limitações remanescentes: fonte IEC somente em
metadados, UKPN histórico sem equivalência/vigência certificada, perfil legado sem original
comprovado, ambiguidades dos exemplos e ausência deliberada de métricas de reconhecimento.
A integração V-N/V-Q do repositório e o aceite da etapa pertencem ao coordenador.

## Conferência dirigida da fonte e denominador

Esta frente abriu com `view_image` as imagens F02 das páginas **3, 4, 15, 22, 27, 28, 29,
30 e 43**. Essa inspeção é dirigida; a auditoria integral do manual pertence à frente A.
As páginas 3–4 confirmam todas as entradas do índice. As demais corroboram os localizadores
prioritários, o tratamento de estados e as seguintes ressalvas:

- Na página 27, BT e MT têm quatro desenhos/estados cada, AT tem uma linha e indicador
  de defeito tem quatro. Resistor e limitador de tensão continuam a seção 21 na página 28:
  são 15 variantes nessa seção, não 13.
- Aterramento e ponto temporário estão na seção 19, página 22. A página 43 apresenta
  rascunhos de existente e retirada; não equivale a uma ocorrência operacional.
- Na página 43, desenhos rotulados como aterramento existente usam vermelho. Nas páginas
  22 e 27, o envoltório de instalação pode ser preto. Essas evidências impedem generalizar
  a regra de cores legada para todo o perfil Electric Office.
- Variantes de estai na página 15 incluem rótulos, traçados e marcações de situação;
  sua geometria não autoriza convertê-las em condutor elétrico.
- As páginas 29–30 distinguem equipamento associado, transformador terciário e de medida;
  componentes e conjuntos não determinam quantidade patrimonial por contagem de formas.

A frente A entregou o congelamento de **427 registros** em 33 seções: uma célula/desenho/estado
por registro, com alternativas semânticas compartilhadas mantidas juntas e sem produto
cartesiano. Inclui um contexto da introdução, três anotações da seção 2 e seis registros
(símbolos e anotações) da seção 13. Portanto, 427 não significa 427 ativos ou geometrias únicas.
As tuplas canônicas seção/título/páginas/contagem foram transcritas no teste e não são lidas
do próprio registro em teste. Um teste negativo retira uma variante, recalcula totais e
confirma que a perda continua detectável.

O congelamento A informou SHA-256 `65a881fd18dad15666dc3094b9b9c3a59f0d72a5c966d1984afe76a0f2e09b39`
para `tmp/e01-simbologia/referencias/variantes-f02.json` e
`deca20c9efdf12d00b4fa87df3de1cdb2d0f4cd0904a3fca2d8b6e594dabd8f4` para
`tmp/e01-simbologia/referencias/indice-f02.json`. A fonte PDF F02 tem hash
`0e29f0ea81827c7235d0893c383fc993c78378c51e930b8b8228de82d564ce04`.
