# ADR 0015 — Pontos de entrega, ramais e alteração de vão

- Estado: aceita
- Data: 2026-09-01
- Escopo: contrato de domínio para as etapas E04, E05, E06, E07 e E08 de
  `docs/roadmap-correcao-interpretacao-topologia-ramais.md`
- Relações: preserva os ADRs 0005, 0009, 0011 e 0013

## Contexto

O domínio vigente possui `SituacaoProjeto.EXISTENTE`, `INSTALAR` e `REMOVER`, já admite
`TipoPontoRede.ENTREGA`, mas não distingue rede de distribuição de ramal de conexão em `Cabo` ou
`VaoDetectado`. Isso permite que uma medida substituída contamine a situação de todo o cabo, que o
padrão do consumidor seja confundido com um poste da rede e que o ramal participe do grau e das
regras topológicas da rede.

A auditoria da ND-5.1 Mar/2026 registrada em `docs/inventario-fontes-normativas.md` separa o ramal de
conexão da rede da CEMIG, situa o ponto de conexão junto ao padrão e prescreve requisitos próprios
para o ramal. A norma usa o termo “ponto de conexão”; `ENTREGA` é o nome já existente no domínio para
o endpoint do consumidor e não renomeia o conceito normativo.

## Decisão

### 1. Alteração é uma situação pública própria

`SituacaoProjeto` ganhará o valor `ALTERAR`. Ele identifica um ativo físico que permanece no projeto,
mas cujo traçado, comprimento, configuração ou outro atributo observado é substituído. Uma redução
de comprimento nunca será representada como `REMOVER`, nem como `EXISTENTE` acompanhado apenas por
texto livre.

No caso de uma medida anterior riscada e outra vigente, o `Cabo.comprimento_m` recebe somente a
medida vigente, a situação é `ALTERAR` e a medida anterior permanece como evidência de supersessão na
proposta/auditoria. A marca sobre a medida não se propaga como situação de remoção do cabo. A
alteração só pode ser concluída quando o ativo sobrevivente, a medida substituída e a medida vigente
estiverem associados com evidências navegáveis; em ambiguidade, não se inventa `ALTERAR`.

### 2. O padrão do consumidor é um ponto de entrega, não um poste

Um identificador operacional cujo agrupamento contém evidência inequívoca de `PADRÃO` materializa
`PontoRede(tipo=TipoPontoRede.ENTREGA, poste_id=None)`. O nome de apresentação será “Padrão do
cliente”; o localizador normativo pode descrevê-lo como ponto de conexão.

`ENTREGA` é um endpoint elétrico. Ele não integra a coleção de `Poste`, não recebe estruturas ou
equipamentos por relações de instalação e não herda elementos de um poste próximo. Proximidade ou um
identificador `P<n>` isolado não bastam: sem evidência coerente do padrão, o tipo permanece não
resolvido.

### 3. Tipo topológico e modalidade são dimensões separadas

Será criado um enum fechado `TipoTrechoRede` com:

- `REDE_DISTRIBUICAO`: trecho resolvido entre pontos da rede, em regra postes da distribuidora;
- `RAMAL_CONEXAO`: trecho resolvido entre a rede e um endpoint `ENTREGA`;
- `DESCONHECIDO`: evidência insuficiente ou conflitante.

`Cabo` passa a persistir `tipo_trecho`; `VaoDetectado` propaga esse valor e preserva os IDs dos dois
endpoints, mesmo quando um deles não é poste. O rótulo operacional `V<n>-<n>` não decide o tipo por si
só. Um endpoint `ENTREGA` com vínculo geométrico coerente decide `RAMAL_CONEXAO`; dois endpoints de
rede resolvidos decidem `REDE_DISTRIBUICAO`; qualquer outra combinação é `DESCONHECIDO`.

A modalidade física será outro enum fechado, `ModalidadeTrecho`, com `AEREO`, `SUBTERRANEO` e
`DESCONHECIDO`. Ela não será inferida do tipo topológico. Regras que dependem de modalidade, como o
limite de 30 m do ramal aéreo, exigirão fato positivo; `DESCONHECIDO` resulta não avaliável.

Somente `REDE_DISTRIBUICAO` participa de grau, fim/transição, deflexão de equipamento e
compatibilidade estrutura–cabo da rede. `RAMAL_CONEXAO` e `DESCONHECIDO` ficam fora desses cálculos.
O ramal recebe apenas regras próprias sustentadas por fatos resolvidos.

### 4. Ocorrência e qualificador não representam quantidade

`N(2)` representa uma ocorrência da estrutura `N` com qualificador observado `2`. `CM3(1)` e
`CM3(2)`, assim como dois rótulos `S3R` em geometrias distintas, são ocorrências físicas distintas.
Duplicatas de extração da mesma ocorrência podem ser consolidadas; o qualificador entre parênteses
não é expandido como cardinalidade.

### 5. Compatibilidade e reanálise

A evolução será aditiva para dados persistidos existentes:

1. Leitores do codec aceitarão a ausência de `tipo_trecho` e `modalidade`, materializando ambos como
   `DESCONHECIDO`; os três valores antigos de `SituacaoProjeto` mantêm o mesmo significado.
2. Não haverá backfill heurístico nem reescrita silenciosa de agregados, propostas ou snapshots
   históricos. Dados antigos continuam legíveis, porém não ganham classificação nova por suposição.
3. As versões/assinaturas do extrator ou interpretador afetado e do método de conformidade serão
   incrementadas nas etapas que mudarem seu comportamento. Sessões e snapshots anteriores permanecem
   imutáveis e são marcados como desatualizados pelo mecanismo vigente.
4. Para obter `ALTERAR`, `ENTREGA`, `tipo_trecho` ou `modalidade` resolvidos em projeto existente, o
   usuário deve executar nova análise semântica; a conformidade deve ser reexecutada depois dela.
5. A API, o cliente e as exportações serão atualizados em conjunto antes de o servidor emitir
   `ALTERAR`. Campos novos usarão valores fechados e explícitos; cliente antigo que não reconheça o
   novo enum não é considerado compatível com a versão do servidor que o produz.
6. UUIDs determinísticos e decisões históricas são preservados quando a mesma identidade física
   continua resolvida. Uma nova sessão registra qualquer mudança de interpretação sem editar a
   sessão anterior.

## Consequências

- Redução de vão fica visível como alteração e não como retirada do ativo.
- Rede, ramal e modalidade deixam de ser inferências misturadas; falta de evidência permanece
  explícita em `DESCONHECIDO`/não avaliável.
- O ponto do padrão pode ser exibido e navegado sem criar poste fictício.
- Regras topológicas deixam de consumir ramais, e regras do ramal podem citar a ND-5.1 com
  aplicabilidade própria.
- A adição de `ALTERAR` exige atualização coordenada do contrato HTTP, filtros, UI e exportações;
  compatibilidade não é obtida traduzindo o valor para `EXISTENTE` ou `REMOVER`.

## Alternativas rejeitadas

### `EXISTENTE` mais texto livre de alteração

Rejeitada porque filtros, resumos, API e exportações continuariam ocultando a alteração e cada
consumidor precisaria reinterpretar atributos livres.

### Reutilizar `REMOVER`

Rejeitada porque comunica retirada do cabo sobrevivente e transforma uma medida substituída em
situção física do ativo.

### Tratar o padrão como poste

Rejeitada porque mistura propriedade e função elétrica, permite relações de instalação indevidas e
faz o ramal aparentar ser um vão comum da rede.

### Inferir ramal por proximidade, BT ou rótulo `V`

Rejeitada porque essas evidências isoladas também ocorrem em trechos de rede. A classificação exige
endpoints e vínculo geométrico coerentes; caso contrário permanece `DESCONHECIDO`.

### Migrar silenciosamente todos os dados existentes

Rejeitada porque os JSON e snapshots antigos não contêm os fatos necessários para uma classificação
segura. Reanálise explícita conserva a proveniência e a versão que produziu cada resultado.
