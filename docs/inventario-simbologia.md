# Inventário de símbolos e perfis de referência

Este inventário pertence à E01 do [roadmap de simbologia](roadmap-analise-simbologia.md).
O [registro JSON](data/inventario-simbologia-v1.json) é dado documental versionado, separado dos
catálogos comerciais, regras de conformidade e detectores. O
[esquema](schemas/inventario-simbologia.schema.json) define os campos; a
[revisão independente](e01-revisao-inventario.md) confere integridade e cobertura.

Versão **2026.09.18.1**, esquema **1.0.0**, conferida em 18/09/2026: **427 variantes de
referência em 33 famílias/tópicos F02**, seis fontes e cinco perfis. Há 249 candidatos
patrimoniais ainda sujeitos a revisão/catálogo, 81 compostos/associados/componentes,
89 desenhos não patrimoniais e oito convenções. A
[tabela completa das 33 seções](e01-referencias-simbologia.md#denominador-de-f02-e-contrato-entregue)
mostra páginas e denominadores; o JSON conserva cada célula com ID, dono e fonte.

| Perfil | Variantes nesta versão | Limite |
|---|---:|---|
| CEMIG EO revisão 3 | 427 | Denominador completo F02; não afirma reconhecimento por detector. |
| IEC 60617 | 0 | Somente metadados; desenhos da base paga não acessados. |
| UKPN East of England 1.2/2010 | 0 | Guia inteiro inspecionado como comparação; sem templates habilitados. |
| Legado não comprovado | 0 | Comportamento do código documentado; original não identificado. |
| Documento local | 0 | Fronteira reservada a E10; cada documento exigirá fonte/revisão própria. |

O zero dos perfis auxiliares delimita este inventário, não ausência de símbolos nas fontes.

| Pacote responsável | Variantes | Recortes prioritários |
|---|---:|---|
| E04 | 12 | Aterramento §19/p22 (4); para-raios BT/MT §21/p27 (4+4). |
| E05 | 29 | Transformadores §18 (23), terciários §24 (2) e medida §25 (4, incluindo conjunto). |
| E06 | 17 | Estai MT §14/p15 (15); AT §15/p16 (2). |
| E07 | 365 | Demais desenhos, compostos e convenções; inclui reguladores dentro de §18. |
| E10 | 4 | Contexto introdutório e anotações gerais; também recebe futuros desconhecidos. |

As quatro variantes de aterramento permanente são `cemig-eo-r3-s19-v001` a `v004`;
as oito de para-raios BT/MT são `cemig-eo-r3-s21-v001` a `v008`. Os desenhos parecidos
de §33 têm IDs próprios e destino informativo. Ponto de aterramento temporário e para-raios
AT permanecem variantes próprias do pacote E07; não são classes suportadas pelo detector legado.

## Unidade de inventário e identidade

Cada variante identifica uma célula de desenho/estado ou uma convenção localizada na fonte.
Alternativas apresentadas na mesma célula ficam juntas em `situation`; não se gera um produto
cartesiano de cores, fases e estados ausentes da fonte. `world` preserva G/I, `operating_state`
distingue aberto/fechado de situação de projeto, e uma lista de situação vazia não significa
existente. O denominador é o número de
variantes registradas, não o número de ativos, componentes geométricos ou exemplares de legenda.
O índice completo F02 conserva todas as seções, inclusive introdução, anotações e rascunhos.

IDs de fontes, perfis, famílias e variantes são únicos entre suas definições. Referências aos
mesmos IDs podem aparecer em várias entradas. Não reutilizar ID removido para outro significado;
uma revisão da fonte ou expansão do denominador exige nova versão e justificativa. `owner` e
`owner_stage` atribuem o pacote futuro; não afirmam que seu detector já está implementado.

Cada variante contém classe/subtipo, perfil, função, destino, cardinalidade, situação,
ambiguidades, negativos confundíveis e referência com página PDF (base 1) e localizador. Os
totalizadores por família e perfil são recalculáveis. A cobertura do índice é uma relação
explícita `f02_index`, não uma inferência pelo nome das famílias.

## Destino semântico

| Destino | Tratamento futuro |
|---|---|
| `equipment_review` | Candidato de equipamento; catálogo e campos técnicos dependem de evidência própria. |
| `support_review` | Poste/suporte/estrutura revisável; não inventar item de catálogo. |
| `mechanical_relation` | Estai/ancoragem e possível suporte; não cria cabo nem conectividade elétrica. |
| `network_context` | Traçado/conexão/infraestrutura; manter função, tensão e associações pendentes quando incertas. |
| `informative_only` | Cartografia, legendas e outros elementos não patrimoniais; não promover a ativo. |
| `composite_review` | Conjunto com componentes preservados; a contagem de traços não determina quantidade de ativos. |
| `document_convention` | Regra de leitura/estilo local; escopo por fonte, página, família e revisão. |
| `unknown_review` | Símbolo sem semântica resolvida; preservar candidato e contexto para E10. |

E04 recebe aterramento e para-raios MT/BT; E05, transformadores; E06, estais/ancoragens; E07,
as demais famílias verificadas. E10 trata convenções locais e desconhecidos. E13 faz associação
e promoção e E14 expõe revisão. Nenhum destino implementa detecção nesta etapa.

## Perfis, autoridade e limites

A forma visual não transporta significado entre perfis. F01 aponta a fonte de simbologia;
F02 documenta Electric Office CEMIG; F03 delimita a referência IEC com acesso por assinatura;
F04 é controle estrangeiro, sem autoridade para definir regra CEMIG. Revisão observada e acesso
estão no registro e no [relatório F01–F04](e01-referencias-simbologia.md). Publicação acessível
não equivale a licença de redistribuição de desenhos. Este registro contém metadados,
localizadores e descrições, sem incorporar os PDFs externos.

O perfil legado conserva a procedência **não comprovada** de `SIMBOLOGIA.pdf`. A busca no Git
e nos arquivos de escopo não localizou esse original; a pesquisa ampla em `tmp/` encontrou
diretório histórico inacessível, portanto não prova inexistência absoluta. O código atual usa
score fixo 0,88, limite de 60 pontos e três classes, com preto/existente, verde/instalar e
vermelho/remover. Esses fatos descrevem a implementação, não a autoridade F02. Cores de tensão,
preenchimentos e status específicos da F02 impedem equivalência automática. Resolver o legado
exige original autorizado, revisão e comparação de hash/desenhos; isso não impede inventariar F02.

O perfil de legenda local delimita interpretação ao documento/revisão, sem aprendizado global
automático. Legenda é referência, não ocorrência patrimonial. Fontes inacessíveis ou não revisadas
ficam explícitas, sem copiar formas ou completar semântica por analogia.

## Validação e consumo

V-P local cobriu **11 PDFs/11 páginas**, base e aparência anotada: **108 imagens realmente
vistas**, 163 anotações e 22 achados de página/região. O manifesto, log de imagens, geometria,
hashes e relatório privado estão em `tmp/e01-simbologia/visual/`. A conferência de integridade
reconciliou todas as páginas e fontes; o script não substitui a inspeção visual.

Essa entrega acrescentou negativos e ambiguidades de cerca, árvores/glifos, detalhes repetidos,
menções textuais sem símbolo e oclusão por anotações. Formas auxiliares V/Y/U e subtipos MT/BT
permanecem hipóteses; não foram convertidos automaticamente em variantes CEMIG ou ativos.
Contagem física por ocorrência e comparação de predições pertencem à E02. Os exemplos vistos
são desenvolvimento; não fornecem uma reserva cega nem uma medida de acurácia da E01.

O teste portátil `tests/unit/test_symbol_inventory.py` valida esquema e integridade referencial,
IDs, fontes/localizadores, totais, índice F02 e limites entre perfis. Casos de mutação verificam
rejeição de registros inválidos. Nenhum teste exige PDFs privados ou rede.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_symbol_inventory.py
```

E02 deve usar esta versão para construir o avaliador, manter entradas e referência do revisor
separadas e não abrir a reserva sintética antes de E16. A união preserva candidatos exclusivos;
silêncio de outro método não é veto, e concordância não é probabilidade. A inventariação visual
de E01 não mede FP/FN nem desempenho. Evidências privadas e comandos de inspeção ficam em
`tmp/e01-simbologia/`; o handoff do roadmap registra cobertura e validações efetivamente feitas.
