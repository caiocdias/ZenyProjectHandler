# Task 4 (E07.1) - relatorio do testador

Status: SUITE VERMELHA com 4 testes documentando 3 defeitos (2 reais, 1 de robustez).
Arquivo: tests/unit/test_ficha_predita_propostas_v2_vao_composto_ataque.py (49 casos; 45 verdes, 4 vermelhos). Nenhum teste existente tocado; producao intocada.

## Analise
Li o diff 5325b69..250ff60 (`_posicao_rotulos`, `_vaos_v2`), o brief e os 12 testes do dev. Atacado: ordem (y antes de x, empate total, rotulos distintos de mesma caixa, sem rotulo por codigo, codigo normalizado), determinismo (ids de relacao, ordem dos elementos), evidencia_rotulo_id invalido/ausente/sem geometria, extracao ausente, pendentes, comprimento, situacao None, pares, 3 postes, REJEITADA (cabo e relacao), A-B/B-A, v1 intocada.

## Testes novos (um por comportamento; parametrizados entre parenteses)
- ordena por y antes de x; empate total pelo codigo (direta/invertida); rotulos distintos de mesma caixa pelo codigo (2); sem rotulo ordena por codigo; ordem usa codigo normalizado
- de/para nao depende dos ids das relacoes (VERMELHO); vao nao depende da ordem dos elementos (2); cabos totalmente empatados deterministicos (2, 1 VERMELHO)
- evidencia de rotulo invalida vai depois (6: None, int, vazio, branco, nao-uuid, uuid inexistente); sem a chave; extracao ausente/None/sem atributo/vazia (4); evidencia sem geometria (2, VERMELHOS)
- pendentes: uniao sem repeticao; vazios; por poste pendente
- comprimento: primeiro anotado na ordem do rotulo vence; anotado sem rotulo vence coordenadas; anotado invalido cai para coordenadas (7); sem comprimento fica None/None
- agrupamento: situacao None nao funde com definida; dois None fundem; pares diferentes; cabo com 3 postes; cabo REJEITADO fora; so rejeitado sem vao; relacao REJEITADA; A-B/B-A com relacao repetida; valida contra o esquema da ficha
- v1: nao le evidencias nem reordena; nao funde A-B/B-A nem normaliza

## Suite inteira
Comando: `.venv\Scripts\python.exe -m pytest -n 6 -q --no-cov -p no:cacheprovider`
Saida: `4 failed, 11288 passed, 5 xfailed in 316.67s` (so os 4 vermelhos abaixo; 5 xfailed pre-existentes). ruff check/format e mypy (624 arquivos) limpos.

## Vermelhos
1. test_v2_de_para_do_vao_composto_nao_depende_dos_ids_das_relacoes
   Falha: `assert ('219096bf-62...') == ('89954d0c-12...')` (de/para invertem).
   Esperado: mesmos cabos/postes/rotulos, so ids de relacao trocados, geram o mesmo de/para.
   Causa: `_vaos_v2` usa `candidatos[0]` (de/para do primeiro cabo), e `_ligacoes` ordena os extremos de cada cabo por `str(relacao.id)`, aleatorio. Com A (p1->p2) e B (p2->p1) o sentido do vao composto muda a cada execucao. Sugestao: fixar de/para canonico (ex.: ordenar o par de ids de poste) no vao composto.
2. test_v2_cabos_totalmente_empatados_com_comprimentos_distintos_sao_deterministicos[ordem-invertida]
   Falha: `assert 20.0 == 10.0`. Mesmo codigo e mesmo rotulo, comprimentos anotados 10 e 20: o escolhido depende da ordem dos elementos na entrada (sorted estavel). Menor gravidade; o brief nao define o desempate final, entao e um defeito de determinismo (acrescentar chave de desempate, p.ex. comprimento/id).
3. test_v2_evidencia_de_rotulo_sem_geometria_nao_derruba_a_ficha[geometria-none, geometria-sem-pontos]
   Falha: `AttributeError: 'NoneType' object has no attribute 'pontos'` / `ValueError: min() arg is an empty sequence` em `_bbox` via `_posicao_rotulos`. Esperado: evidencia sem caixa tratada como sem rotulo. Robustez: o dominio real (EvidenciaDocumento.geometria obrigatoria; GeometriaDocumento valida pontos) nao produz esses casos, entao e baixa prioridade; decisao do orquestrador (corrigir com guarda ou aceitar e converter o teste em xfail documentado).

## Observacoes (nao sao bugs)
- Pendentes: a uniao inclui "comprimento_m" de um cabo pendente mesmo quando o comprimento escolhido e o anotado de outro cabo; segue o brief literalmente, mas pode superestimar pendencias.
- Rotulos de paginas diferentes comparam y/x sem considerar a pagina (ficha por poste costuma ter pagina unica).
- Situacao None: PropostaElemento tipa o campo como enum; testei via replace e funciona (grupo proprio).
- Nenhum teste existente parece errado.

## Commits
- 7b9129b test: ataque ao vao composto da fonte propostas-v2 (4 vermelhos documentam defeitos)
- (relatorio) commit seguinte: docs: relatorio do testador da Task 4 da E07.1
