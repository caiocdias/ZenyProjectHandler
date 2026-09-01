# Especificação funcional

Este documento descreve o comportamento vigente do Zeny Project Handler. Decisões de arquitetura e
seu histórico ficam nos [ADRs](adr); detalhes exclusivos do motor de conformidade ficam em
[arquitetura-conformidade.md](arquitetura-conformidade.md).

## Escopo do produto

O produto combina um cliente Windows magro com um servidor protegido. O servidor mantém projetos
de expansão da rede de distribuição, recebe folhas PDF, extrai e interpreta evidências do desenho e
avalia regras de conformidade; o cliente apresenta os resultados e permite revisão humana. Todas as
conclusões automáticas conservam a versão do método, a origem e a evidência que as sustentam.

Estado versionado relevante:

| Componente | Versão atual |
|---|---|
| Pacote Python | `0.3.0` |
| Catálogo técnico | `2` |
| Registro de interpretação | `1.3.0` |
| Registro de conformidade distribuído | `cemig-normas-distribuicao-2025.7` |
| Método de conformidade | `10` |
| Migração SQLite mais recente | `0009_remote_jobs` |

## Modelo de domínio

`Projeto` é o agregado persistido. Ele reúne:

- coleção ordenada e sem duplicatas de códigos de serviço com quatro dígitos ASCII;
- documentos e páginas na ordem de leitura escolhida;
- elementos confirmados: `Poste`, `EstruturaMt`, `EstruturaBt`, `Cabo` e `Equipamento`;
- relações confirmadas entre elementos;
- pontos de rede, terminais e conexões internas quando disponíveis;
- registros de revisão manual e fotos gerenciadas associadas a elementos.

Cada elemento possui ID, item do catálogo quando classificado, situação `EXISTENTE`, `INSTALAR` ou
`REMOVER`, geometria opcional e proveniência. Referências internas são validadas pelo agregado: não
podem apontar para outro projeto, documento ou página.

O diagrama resumido está em [modelo-entidades.mmd](modelo-entidades.mmd). O domínio fica em
`src/zeny_project_handler/domain` e não depende de Qt, SQLAlchemy, PyMuPDF ou Tesseract.

## Projetos e documentos

- Um projeto é criado a partir de uma NS normalizada e pode ter a NS alterada depois.
- O seletor de projetos aceita pesquisa local por até dez dígitos da NS, sem inserir opções
  provisórias nem dissociar cada opção de seu ID remoto. Uma NS completa também é resolvida
  exatamente no servidor, mesmo quando o projeto não está entre os 200 itens carregados.
- A caixa **Serviços do projeto**, entre **Projeto** e **Folhas PDF**, consulta e substitui uma
  coleção canônica pelo servidor. Cada código possui exatamente quatro dígitos ASCII, conserva
  zeros à esquerda, e projetos legados abrem com coleção vazia.
- Um ou vários PDFs podem ser adicionados na mesma seleção.
- Conteúdo duplicado, identificado por hash, não pode entrar duas vezes no mesmo projeto.
- A ordem de leitura é uma sequência de páginas persistida e pode intercalar páginas de PDFs
  diferentes.
- Remover um PDF elimina do projeto as páginas e os resultados dependentes, mas preserva o arquivo
  externo original.
- Excluir o projeto remove seus dados e arquivos pertencentes à área gerenciada, também preservando
  origens externas.

O painel Projeto usa somente o gateway HTTP. Cada PDF é enviado por streaming para uma área
temporária limitada, validado e publicado atomicamente na área gerenciada do servidor. O contrato
leva bytes e nome de exibição, nunca caminho local. A origem escolhida no cliente não é alterada e a
cópia gerenciada continua disponível se essa origem for movida ou apagada.

**Abrir** usa o ID de uma opção realmente selecionada ou exige os dez dígitos pesquisados. Se a NS
completa não existir, a interface informa a ausência e pergunta se deve criar o projeto; aceitar
faz uma única criação e abre o resultado. **Criar** resolve primeiro a NS informada: quando ela já
existe, não envia criação e pergunta se deve abrir o ID existente. Um conflito
`PROJECT_ALREADY_EXISTS` ocorrido entre a resolução e o `POST` usa o mesmo diálogo e não repete a
criação automaticamente.

Recusar qualquer uma dessas propostas retorna ao estado inicial: não há projeto ativo, pesquisa,
NS, serviços nem folhas selecionados; `last_project_id` é removido; visualizador, Resultados,
Documentação/conformidade e Exportar deixam de apontar para o projeto; ações dependentes ficam
desabilitadas. Essa transição é somente local e não exclui nem altera projeto no servidor.

## PDFs protegidos

PDFs protegidos solicitam senha individualmente. Cada arquivo admite até três tentativas; cancelar
pula apenas o arquivo atual numa seleção múltipla.

A senha correta é indexada pela identidade verificável da cópia gerenciada e permanece apenas na
memória do processo servidor. Ela é descartada no restart ou quando a identidade deixa de
corresponder. Senhas não entram no banco, cache, logs, pacotes, backups nem estado da interface.

## Visualização

O visualizador central oferece paginação, zoom, rotação e navegação entre as folhas do projeto. A
abertura, a verificação de identidade e a rasterização ocorrem no servidor autenticado. O cliente Qt
recebe metadados e PNGs, apresenta uma prévia integral limitada e solicita tiles de detalhe conforme
o viewport. A fila antiga é cancelada quando página, zoom, rotação, DPR ou origem mudam; qualquer
resposta pertencente a uma geração anterior é descartada.

Um PDF avulso é enviado para uma sessão temporária do servidor, limitada em quantidade e tamanho.
Atividade renova o TTL; encerramento explícito ou expiração fecha o leitor e apaga a cópia. O
cliente conserva somente pixmaps no cache LRU visual e não usa PyMuPDF para abrir, inspecionar ou
renderizar o documento.

Os padrões são 600 DPI como teto de detalhe, 8.000.000 pixels e 64 MiB por solicitação e 128 MiB de
cache visual. Esses limites são configuráveis pelas variáveis descritas no README e não alteram o
pipeline de análise.

Sublinhos de elementos, contornos temporários e callouts de conformidade são camadas vetoriais
independentes. Nenhuma delas é escrita no PDF original.

## Extração documental

`PyMuPdfDocumentAnalyzer` produz execuções e evidências auditáveis a partir de:

- texto nativo, com fonte, tamanho, rotação e geometria;
- desenhos vetoriais, comandos e cores;
- imagens incorporadas;
- anotações e appearance streams;
- Form XObjects e grupos de conteúdo opcionais;
- OCR local, quando a página ou uma região precisa de reconhecimento raster.

Coordenadas são normalizadas no espaço visual da página com a rotação intrínseca aplicada. Objetos
sem geometria exata são identificados como aproximação e continuam rastreáveis por seus metadados
PDF.

Falhas localizadas viram diagnósticos e não descartam recursos extraídos com sucesso. O resultado
pode ser reconstruído pelo hash e pela assinatura real do extrator. O cache JSON em
`cache/analysis` é derivado e descartável.

Comentários de revisão PDF são preservados para auditoria, mas não originam elementos, regiões ou
fatos técnicos. Portadores identificados como `AutoCAD SHX Text` permanecem conteúdo do desenho e
não são filtrados como comentários.

## OCR

O Tesseract é um adaptador opcional do servidor. Sua assinatura inclui a versão real do executável,
idiomas selecionados, hashes dos arquivos `traineddata`, perfis, pré-processamento e parâmetros de
reconhecimento. Instalações equivalentes em caminhos diferentes produzem a mesma identidade.

O analisador decide quando aplicar OCR geral ou localizado. Há tratamentos específicos para
identificadores operacionais `P<n>` e `V<n>-<n>`, caixas de nomenclatura, rótulos inclinados de rede,
comprimentos e símbolos vetoriais. A falta ou falha do Tesseract desativa somente o OCR e gera um
diagnóstico; texto e recursos nativos continuam disponíveis.

## Interpretação semântica

O registro `regras_interpretacao_v1.json`, hoje na versão `1.3.0`, possui cinco regras de
reconhecimento por categoria e sete regras de relação. O pipeline:

1. filtra conteúdo que não pode fundamentar resultado técnico;
2. reconhece códigos e nomenclaturas contra os 199 itens do catálogo técnico;
3. associa cor e convenção gráfica à situação do elemento;
4. cria `PropostaElemento` e `PropostaRelacao` com confiança, justificativa e evidências;
5. promove deterministicamente resultados catalogados e relações resolvíveis ao projeto;
6. conserva propostas ambíguas ou não catalogadas para revisão.

Postes aceitam código do catálogo e nomenclaturas de altura e resistência. Estruturas, cabos e
equipamentos usam analisadores próprios. Identificadores de ponto e coordenadas próximas enriquecem
o contexto, mas coordenadas isoladas não criam um elemento elétrico.

Uma execução concluída é idempotente para o mesmo projeto, extração, catálogo, registro e
configuração. Cancelamento ou falha não publica um conjunto parcial como concluído.

### Jobs de análise

O cliente cria a análise com `Idempotency-Key` e recebe `202` com um job em `QUEUED`. O worker único
do servidor conduz `RUNNING`, `WAITING_CONFIRMATION` quando uma operação futura exigir confirmação,
`CANCELLING` e os terminais `SUCCEEDED`, `FAILED` ou `CANCELLED`. Consulta e resultado usam DTOs
seguros; erros inesperados expõem apenas mensagem e `correlation_id`.

O cliente consulta a cada 250–500 ms. O servidor persiste progresso monotônico, resultado terminal e
histórico com retenção por tempo e quantidade. Cancelar apenas sinaliza o job; a execução para numa
fronteira segura e libera a operação global. Repetir a mesma criação devolve o mesmo job e não roda o
pipeline duas vezes. Após restart, qualquer estado ativo remanescente vira `FAILED` recuperável, sem
resultado e sem sucesso presumido.

## Promoção e revisão humana

Resultados catalogados são promovidos automaticamente, sem perder a proposta e a decisão que
originaram a entidade. O painel de resultados permite:

- navegar por regiões, elementos, relações e vãos;
- localizar a geometria correspondente no PDF;
- aceitar ou corrigir uma proposta;
- rejeitar uma proposta;
- criar elemento ou relação manual;
- ocultar temporariamente uma região, um elemento ou um vão no visualizador.

Revisões persistem a autoria, o instante, a decisão, o conteúdo anterior e o conteúdo confirmado.
Uma proposta de outro projeto ou uma referência incompatível é recusada.

O painel consome uma sessão remota versionada que já contém catálogo, referências, regiões, vãos,
rótulos, overlays, evidências de navegação e histórico de auditoria. Aceite, ajuste, rejeição e
criações manuais são comandos HTTP autenticados. O servidor revalida projeto, página, catálogo e
referências; o identificador da sessão impede que uma segunda janela grave sobre uma decisão mais
recente e devolve conflito `409`, após o qual a sessão pode ser recarregada sem perda silenciosa.
Nenhuma região, vão, classificação, vínculo ou rótulo técnico é derivado pelo cliente.

## Regiões e vãos

`RegiaoAnalise` é uma projeção derivada e determinística que agrupa propostas próximas na mesma
página. Ela pode reunir itens existentes, a instalar e a remover, relações e coordenadas UTM. Não é
persistida como uma segunda fonte de verdade.

`VaoDetectado` é derivado quando um cabo liga dois postes distintos ou quando o desenho fornece um
identificador operacional inequívoco. A medida usa, nesta ordem, o comprimento informado no
desenho e a distância entre coordenadas compatíveis dos postes. A origem da medida e as evidências
permanecem registradas; um comprimento não é inventado quando nenhuma fonte é suficiente.

## Documentação e conformidade

O painel **Documentação e conformidade** possui três abas:

1. **Documentação** lista campos rotulados do cabeçalho e da servidão, candidatos a carimbo e campos
   de assinatura. Presença visual ou campo PDF preenchido não prova autenticidade.
2. **Conformidade** mostra a última execução persistida, com divergências primeiro, valores
   observados e esperados, alvo, fonte, revisão e localização. Callouts podem ser exibidos ou
   ocultados sem afetar as outras camadas.
3. **Regras** mostra a revisão ativa e permite importar ou exportar o JSON. Não existe remoção nem
   ativação individual pela interface.

A inspeção, a avaliação das regras, o histórico e a compilação de callouts ocorrem no servidor. O
cliente lista sessões semânticas por `GET /api/v1/documentation/projects`, cria uma reanálise como
job e recebe somente DTOs normalizados. Seleção cruzada, visibilidade e a posição manual efêmera das
caixas permanecem locais. O upload de regras exige preflight e confirmação separados; cancelar no
diálogo não publica revisão.

O seed contém 41 regras habilitadas. As regras 40 e 41 têm, respectivamente, os títulos exatos
`IMPACTO AMBIENTAL PENDENTE` e `FALTA SERVIDÃO PENDENTE`. A lista normativa completa está em
[catalogo-regras-conformidade.md](catalogo-regras-conformidade.md), e o desenho do motor está em
[arquitetura-conformidade.md](arquitetura-conformidade.md).

Antes de qualquer `SELECT`, a execução compara a NS vigente do projeto com todos os valores válidos
encontrados na zona de cabeçalho das folhas, na ordem de leitura e fora de comentários de revisão.
Nenhum valor identificado permite continuar e a NS de cabeçalho não é obrigatória. Um ou vários
valores todos iguais à NS do projeto também permitem o fluxo normal; qualquer valor diferente,
inclusive quando outra folha contém a NS correta, encerra o job com `VALIDATION_ERROR`. A mensagem
informa somente a NS do projeto, os valores divergentes e a orientação para corrigir projeto/PDF e
reanalisar. Mercado e ações não são consultados, nenhum snapshot parcial é publicado e o snapshot
anterior, quando existe, permanece inalterado.

`Impacto Ambiental: Sim` é gatilho somente quando o rótulo aparece na zona de cabeçalho e o valor
normalizado é exatamente `SIM`. Uma menção positiva aceita a `SERVIDÃO`, `FAIXA DE SERVIDÃO` ou
`FAIXA DE DOMÍNIO` em qualquer folha fora de comentários de revisão. Cada gatilho consulta no máximo
uma vez por execução a ação fechada correspondente — `AVALIAR IMPACTO AMBIENTAL` ou
`FALTA SERVIDÃO` — com a NS e a coleção de serviços vigentes. O cliente não executa nem conhece SQL.

Uma ou mais linhas concluídas torna o requisito conforme; zero linha é uma consulta válida e gera a
pendência. Lista vazia não produz `IN ()`: a porta não é chamada, o requisito fica falso com origem
explicativa e o callout usa a evidência do PDF. Timeout, falha ODBC ou erro de execução interrompem o
job sem snapshot parcial e não são convertidos em pendência. Sem o gatilho, a ação não é consultada
e a regra não cria achado.

O domínio e a interface reconhecem `CONFORME`, `DIVERGENCIA` e `NAO_AVALIAVEL`. O avaliador atual
emite os dois primeiros para alvos aplicáveis e não cria achado quando alguma condição `when` falha.
Dentro de uma regra aplicável, requisito ausente conta como não atendido; por isso o registro inclui
fatos de guarda sempre que a ausência significa “escopo ainda não caracterizado”, e não violação.
Somente divergências são compiladas na lista de problemas e, quando possuem geometria rastreável,
recebem callout. Resultados conformes e não avaliáveis permanecem no snapshot auditável, sem serem
encaminhados ao projetista como pendências. O usuário pode arrastar a caixa dentro da folha; a
âncora permanece fixa e a seta é recalculada durante o movimento. A posição manual é preservada
enquanto o mesmo projeto permanece aberto.

Uma execução de conformidade guarda a assinatura da sessão semântica, da revisão das regras, do
método, da NS, dos códigos de serviço e dos resultados externos consultados. Alterar regras, método,
NS ou serviços marca o snapshot anterior como desatualizado; a reanálise é sempre explícita e cria
ou reutiliza a execução idempotente correspondente.

## Registro de regras

O SQLite mantém revisões imutáveis do registro e números permanentes por ID técnico. Importar um
JSON:

- valida schema, tipos, operadores, escopos e vocabulário de fatos;
- mescla regras por ID;
- preserva todos os IDs atuais omitidos no arquivo;
- cria uma nova revisão assinada sem alterar o seed empacotado no servidor;
- republica um catálogo Markdown da revisão ativa na pasta de dados do servidor.

Na inicialização, atualizações oficiais são aplicadas seletivamente: definições locais modificadas e
IDs personalizados são preservados. A restauração de backup também reconcilia IDs locais ausentes
antes de liberar o registro restaurado.

## Persistência e recuperação

O banco SQLite fica em `ZENY_SERVER_DATA_DIR` (normalmente o volume `/data`). Antes da prontidão, o
servidor prova escrita, valida `.zeny-volume.json`, executa `PRAGMA quick_check`, rejeita revisão
desconhecida e aplica Alembic somente quando o banco ainda não está no `head` embarcado. Revisão,
integridade e manifesto são confirmados depois da migração. Falta de permissão, corrupção, formato
de volume futuro ou erro de migração encerram o startup sem atendimento de negócio. Entidades de
domínio são serializadas por repositórios; modelos SQLAlchemy não são usados como domínio. O
diretório local do cliente contém somente preferências visuais e logs, nunca banco, cache de análise
ou arquivos de projeto gerenciados.

Snapshots de análise, interpretação, decisões, conformidade e revisões de regras preservam
identidade e versão. Dados grandes e pesquisáveis possuem colunas próprias; os agregados completos
são mantidos em JSON canônico quando isso evita duplicar o modelo no schema relacional.

Publicações de arquivos usam temporário irmão, `fsync` quando disponível e substituição atômica. A
importação de projeto e a exclusão/limpeza de arquivos gerenciados mantêm journals reconciliados no
bootstrap. Estado corrompido ou ambíguo bloqueia a inicialização em vez de autorizar uma limpeza por
inferência.

## Exportação de entregáveis

O painel **Exportar** não transporta o agregado nem oferece backup/restauração ao usuário. O servidor
compila quatro entregáveis a partir do projeto atual: PDF na ordem das folhas com anotações de
conformidade, Resultados `.xlsx` com abas Elementos e Vãos, Documentação `.xlsx` e Conformidade
`.xlsx` com abas Conformidade e Regras.

O PDF mantém o conteúdo e as anotações originais e recebe callouts FreeText nas coordenadas
normalizadas da execução mais recente. Posições ajustadas na interface são enviadas como overrides
validados contra os IDs de callout atuais. As planilhas usam as mesmas projeções DTO mostradas nos
painéis e tratam todo conteúdo como texto, inclusive valores iniciados por `=`, para não executar
fórmulas vindas dos documentos.

Cada artefato é publicado como download autenticado com metadados de tamanho, SHA-256 e expiração;
o cliente grava em temporário irmão e só substitui o destino após validar a identidade. Downloads
expirados são removidos pela política de TTL. A proteção integral do banco e dos arquivos é uma
responsabilidade administrativa do servidor, por snapshot consistente do volume com o serviço
parado, e não uma ação da interface do usuário.

## Interface e concorrência

A análise do painel Projeto executa no servidor e é observada por polling fora da thread da
interface. Um segundo cliente recebe o mesmo progresso/bloqueio global e conflito HTTP 409 ao tentar
uma operação incompatível. A revisão humana também usa estado otimista remoto: duas sessões podem
ler a mesma proposta, mas somente a primeira decisão válida persiste; a segunda recebe `409` e deve
recarregar os DTOs. A compilação e o download dos entregáveis executam fora da thread visual; o
cliente mantém a interface responsiva, permite cancelar antes da publicação local e preserva o
arquivo anterior em caso de falha. Objetos Qt visuais permanecem na thread principal.

Os códigos de serviço usam `GET` e `PUT /api/v1/projects/{project_id}/service-codes`. O PUT substitui
toda a coleção com `expected_project_version`; uma segunda janela com versão obsoleta recebe
`409 STALE_STATE`, recarrega detalhe e coleção e não sobrescreve os valores vigentes. A resposta
devolve `ProjectServiceCodesResponse`; o DTO de detalhe do projeto e o PATCH da NS permanecem
inalterados.

O procedimento operacional usa snapshot administrativo antes de upgrade, `docker compose down` sem
remoção de volume e migração fail-closed antes de `ready=true`. Rollback no mesmo volume é permitido
somente para imagem compatível com seu formato/revisão; rollback incompatível cria volume novo e
restaura o snapshot pré-upgrade. Não há downgrade automático nem edição de `alembic_version`.

Os painéis **Projeto**, **Resultados**, **Documentação e conformidade** e
**Exportar** podem ser movidos, desacoplados e restaurados. Tema, geometria e
estado dos docks ficam em `ui-state.ini` na pasta de dados.

Antes de construir os painéis de dados, o cliente exige URL e senha e valida a rota de sessão. A URL
pode ser persistida; a senha fica somente em memória e não é obtida de `.env`. Uma desconexão ou
resposta `401` bloqueia ações remotas e permite reconectar na mesma janela.

## Exemplos e qualidade

`examples/` é uma bancada local dinâmica. Tudo abaixo dela, exceto seu README, é ignorado pelo Git.
Não existe manifesto de corpus ou gate privado. O gate padrão depende apenas de testes e fixtures
sintéticas versionadas.

`scripts/smoke_examples.py` percorre opcionalmente os PDFs locais, abre, renderiza, extrai,
interpreta e confirma que a origem não foi alterada. Um comportamento permanente observado nesses
arquivos deve virar uma fixture sintética. Comentários de comissionamento podem orientar
investigação, mas não substituem fonte normativa.

## Limites atuais

- O cliente possui ZIP portátil Windows x64 autocontido, mas ainda não possui instalador nem
  assinatura de código.
- Reconhecimento visual pode permanecer ambíguo; a interface conserva o resultado para revisão em
  vez de forçar uma classificação.
- Cálculos elétricos e mecânicos completos e verificações dependentes de fontes restritas não são
  executados sem todos os fatos e referências necessários.
- Carimbo, rótulo ou campo de assinatura não comprova autoria ou autenticidade.
- Não existe integração ativa com serviços externos de OCR, nuvem ou IA; o pipeline funciona no
  servidor com PyMuPDF e Tesseract.
