# Arquitetura de conformidade

## Objetivo

O motor compara fatos rastreáveis do projeto com regras declarativas sem transformar ausência de
evidência em certeza. A revisão distribuída atual é `cemig-normas-distribuicao-2025.6`, com 39 regras
habilitadas, e o método de conformidade está na versão `8`.

O [catálogo de regras](catalogo-regras-conformidade.md) documenta obrigações e fontes. O
[inventário normativo](inventario-fontes-normativas.md) registra documentos, revisões, hashes e
escopo de leitura. Esta página trata somente da implementação.

## Fluxo

```text
Projeto + sessão semântica persistida
                |
                v
 consulta única de mercado por NS no SQL Server
                |
                v
     construção de alvos de conformidade
                |
                v
 provedores documentais, regionais, de vãos e topológicos
                |
                v
        fatos tipados com proveniência
                |
                v
 registro ativo -> avaliador declarativo -> achados
                |
                v
 snapshot SQLite -> DTOs + callouts normalizados -> camada vetorial Qt
```

`ExecutarAnaliseConformidade` é a entrada transacional no processo servidor. O fluxo completo do
projeto e o job criado pelo botão **Analisar conformidade** chamam o mesmo caso de uso. A ação
explícita reutiliza a sessão semântica persistida e não repete leitura do PDF, extração ou OCR. O
cliente não carrega registro, provedores, avaliador, classificador de mercado nem compilador de
callouts.

Depois de carregar a sessão, o caso de uso chama obrigatoriamente `ClassificadorMercadoPort` uma
vez com o nome/NS vigente do projeto. O adaptador SQL Server executa com parâmetro vinculado
`SELECT NOTAS_COD_MERCADO FROM TB_NOTAS WHERE NOTAS_NUM_NS = ?;`, converte a NS de 10 dígitos para
inteiro somente nessa fronteira e aceita exclusivamente `RURAL` ou `URBANO`. A mesma instância
composta atende ao pipeline completo e à reanálise explícita.

## Contratos do domínio

Os tipos ficam em `domain/compliance.py`.

### Alvo

`AlvoConformidade` identifica o objeto avaliado e pode representar projeto, documento, página,
região ou elemento. Ele conserva página e geometria quando essas informações existem.

### Fato

`FatoConformidade` associa uma chave tipada a valor, alvo, origem, confiança, evidências e geometria.
Unidades fazem parte da chave quando necessário, por exemplo uma medida em metros. O fato descreve
o que foi observado; ele não contém a obrigação normativa.

### Regra

`RegraConformidade` contém:

- ID técnico estável, título, descrição, escopo e severidade;
- fonte com documento, revisão, item, página e URL;
- `when`, condições de aplicabilidade;
- `unless`, exceções que precisam de prova positiva;
- `must`, requisitos avaliados quando a regra se aplica;
- estado `enabled`.

Cada condição declara chave de fato, operador, valores esperados e quantificador quando aplicável.
O JSON não aceita expressão executável nem chamada arbitrária de Python.

### Achado

`AchadoConformidade` admite `CONFORME`, `DIVERGENCIA` ou `NAO_AVALIAVEL` e registra a regra e o alvo,
condições avaliadas, fatos participantes, valor observado, valor esperado e fonte. A interface
continua capaz de apresentar os três estados; o avaliador vigente não cria `NAO_AVALIAVEL`.

## Semântica da avaliação

1. Uma regra desabilitada não é executada.
2. Todas as condições `when` são combinadas por E; se alguma falha, o alvo é ignorado para a regra.
3. Condição sem fatos falha, exceto `AUSENTE`, que é atendida justamente quando não há valor.
4. Se todas as condições `unless` são atendidas, a regra é dispensada para o alvo.
5. Todos os requisitos `must` precisam ser atendidos. Falha ou ausência de um requisito produz
   `DIVERGENCIA`; todos atendidos produzem `CONFORME`.
6. O registro deve usar um fato de aplicabilidade resolvida quando a falta de evidência ainda não
   autoriza avaliar o requisito. Essa guarda é o que impede uma divergência presumida fora do escopo
   conhecido.

O avaliador genérico está em `application/compliance_evaluation.py`. Ele não conhece geometria,
topologia, PDF, SQL Server, mercado nem normas específicas. As guardas
`rede.contexto_rural`/`rede.contexto_urbano` permanecem no `when` de cada regra aplicável; não há
filtro paralelo por mercado.

## Catálogo de fatos

`domain/compliance_facts.py` é o vocabulário aceito pelo registro. Cada definição informa:

- chave e descrição;
- escopos permitidos;
- tipo de valor;
- operadores permitidos;
- disponibilidade do provedor.

A importação recusa chave desconhecida, escopo incompatível, operador não permitido e valor do tipo
errado. Uma chave conhecida marcada como planejada pode ser aceita, mas continuará sem produzir uma
conclusão enquanto nenhum provedor publicar o fato.

## Provedores atuais

Os provedores implementam o protocolo de `application/compliance_fact_providers.py` e recebem uma
sessão semântica e seus alvos. A composição é explícita no bootstrap:

| Família | Implementação | Exemplos de fatos |
|---|---|---|
| documental | `application/document_compliance.py` | nomes e conteúdo de documentos, anexos identificados |
| regional | `application/project_compliance.py` | cabeçalho, formato, escala, contexto, elementos associados |
| vãos | `application/span_compliance.py` | tecnologia, comprimento, origem da medida e exceções comprovadas |
| topológica | `application/topology_compliance.py` | ângulos, continuidade, componentes, periodicidade e coerência entre elementos |

Os provedores publicam fatos e proveniência; condições normativas permanecem no JSON. Adicionar uma
família não exige alterar o avaliador.

Comentários PDF (`ANOTACAO`) e objetos derivados de sua aparência não podem alimentar fatos
técnicos. Objetos `AutoCAD SHX Text` identificados como conteúdo técnico são preservados. Contexto
urbano ou rural vem exclusivamente do enum retornado pelo SQL Server, nunca de metadado, campo
rotulado, OCR ou token do PDF. O provedor publica somente o fato correspondente, com confiança 1,
origem auditável sem dados de conexão e nenhuma evidência PDF, no projeto e em todas as regiões.

## Fronteira operacional do mercado

`ServerSettings` exige `ZENY_MARKET_SQLSERVER_CONNECTION_STRING` fora de `repr` e valida
`ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS` como inteiro positivo também fora de `repr`. A projeção de
core settings, contratos HTTP e pacote cliente não carregam esses campos. O segredo entra somente
como ambiente runtime do container: não pertence a Dockerfile/camadas, SQLite, `/data`, backups,
DTOs, respostas ou logs.

O login externo deve possuir somente conexão ao banco e `SELECT` nas duas colunas consultadas de
`TB_NOTAS`. Microsoft ODBC Driver 18 usa `Encrypt=yes` e `TrustServerCertificate=no`; CA privada
deve ser confiada na imagem, sem ignorar o certificado. O timeout é aplicado tanto à abertura
quanto ao cursor/consulta, e cursor e conexão são fechados em sucesso e falha.

Zero/múltiplas linhas, `NULL`, valor inválido, timeout ou erro ODBC geram erros de aplicação seguros
e interrompem o job antes do commit. Não existe snapshot parcial, fallback, cache persistente ou
publicação dos dois contextos. O healthcheck HTTP não consulta essa dependência. Testes normais
injetam fakes; o adaptador real é exercitado apenas pelo smoke opt-in da homologação.

## Registro configurável

O seed está em
`adapters/compliance/data/regras_conformidade_v1.json`. O adaptador valida o schema estrutural e o
serviço de aplicação valida o vocabulário semântico.

O SQLite mantém:

- snapshots JSON canônicos e imutáveis em `compliance_rule_revisions`;
- assinatura SHA-256, versão informada e indicador da revisão ativa;
- número de exibição permanente por ID técnico em `compliance_rule_numbers`.

Importar regras é uma operação autenticada do servidor: o preflight valida e prepara o merge por ID,
preserva IDs atuais omitidos e exige uma confirmação separada antes de publicar. O usuário pode
alterar `enabled` apenas ao importar o mesmo ID; não há comando de remoção, ativação ou desativação
individual. O download devolve a revisão ativa sem expor caminho físico.

Cada mudança republica `catalogo-regras-conformidade.md` na pasta de dados do usuário. Esse arquivo é
uma projeção explicativa da revisão local; o catálogo versionado no repositório descreve o seed.

## Atualização do seed e restauração

`ServicoRegistroRegrasConformidade.inicializar` aplica correções e adições oficiais de maneira
seletiva. Uma definição local modificada não é sobrescrita por uma correção automática e IDs
personalizados são preservados. Se o conjunto final divergir do seed, a versão recebe tags que
registram as adições aplicadas.

Antes de restaurar um backup, o serviço captura a revisão local ativa. Depois da troca, reaplica ao
registro restaurado os IDs locais ausentes, sem substituir o conteúdo de IDs coincidentes. Só então
adiciona IDs oficiais ainda ausentes e republica o catálogo. Falha nessa reconciliação participa da
compensação da restauração.

## Execuções persistidas

`compliance_executions` guarda um snapshot canônico com:

- projeto e execuções semânticas de origem;
- ID, versão e assinatura da revisão das regras;
- versão do método e assinatura da sessão;
- alvos, fatos, itens documentais e achados;
- avaliação detalhada de `when`, `unless` e `must`.

O ID deriva das assinaturas da entrada. Repetir a mesma sessão, revisão e método é idempotente;
alterar regras ou método cria outra identidade e conserva o histórico. Um trigger impede a edição do
snapshot concluído.

O fato de mercado participa da assinatura da sessão. Se a consulta seguinte mudar de `RURAL` para
`URBANO` ou vice-versa, a reanálise cria outra identidade. Uma alteração apenas no sistema externo
não marca automaticamente o snapshot antigo como desatualizado, porque a consulta disponível não
expõe versão ou evento; é necessário acionar **Analisar conformidade** para capturá-la.

O painel considera desatualizado um resultado cuja assinatura das regras ou versão do método não
corresponde ao estado ativo. O snapshot antigo continua visível até uma reanálise explícita.

## Callouts e interface

No servidor, `application/compliance_callouts.py` converte somente divergências localizáveis em
`ComplianceCalloutDto` sem Qt.
Resultados conformes e não avaliáveis permanecem no snapshot auditável, mas não são apresentados
como problemas de comissionamento nem recebem callout.
A geometria é escolhida, em ordem, entre fatos participantes, evidências referenciadas e alvo. Uma
ausência real de página ou geometria não recebe coordenadas inventadas.

O posicionador calcula caixas próximas às âncoras, respeita as margens da folha e minimiza colisões
de modo determinístico. Texto, largura, margens e pontas de seta usam medidas físicas para manter
legibilidade entre formatos e orientações.

`PdfGraphicsView` desenha caixa branca, borda/texto coloridos conforme o resultado e setas numa
camada vetorial separada da prévia, dos tiles, dos sublinhados de elementos e do contorno
temporário. Zoom e rotação não rasterizam o callout nem modificam o PDF.

As caixas são itens gráficos arrastáveis e contidos nos limites da folha. Durante o arraste, somente
a caixa muda de posição: a âncora normalizada continua fixa e o caminho da seta é reconstruído da
borda da caixa até essa âncora. O visualizador mantém overrides de posição em memória para que
ocultar/exibir, zoom, rotação e troca de página não desfaçam o ajuste manual.

Na aba **Conformidade**:

- somente divergências aparecem na lista de problemas;
- selecionar a linha abre e centraliza o callout;
- clicar na caixa ou seta seleciona o achado correspondente;
- o olho individual e **Exibir todos/Ocultar todos** afetam somente callouts localizáveis;
- a visibilidade temporária é preservada ao trocar página ou ordenar a lista e reiniciada ao trocar
  projeto ou execução.

## Como acrescentar uma regra

1. Confirmar documento, revisão, item, página, URL, aplicabilidade e exceções numa fonte autorizada.
2. Definir os fatos necessários e verificar se preservam alvo, unidade, situação, associação e
   proveniência.
3. Adicionar ao catálogo de fatos qualquer chave nova, com tipo, escopo e operadores mínimos.
4. Implementar ou ampliar um provedor determinístico quando o fato ainda não existir.
5. Incluir a regra no JSON com novo ID quando a obrigação mudar; correção apenas editorial mantém o
   ID.
6. Atualizar [catalogo-regras-conformidade.md](catalogo-regras-conformidade.md) no mesmo commit.
7. Testar casos conforme, divergente, não avaliável e todas as exceções, além da paridade entre JSON
   e catálogo.
8. Verificar persistência, explicação e callout com fixtures sintéticas.

Uma atualização normativa nunca reinterpreta silenciosamente uma execução anterior. Reaplicar a
nova revisão é uma ação explícita e produz um snapshot associado à nova assinatura.
