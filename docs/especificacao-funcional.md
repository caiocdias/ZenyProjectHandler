# Especificação funcional

Este documento descreve o comportamento vigente do Zeny Project Handler. Decisões de arquitetura e
seu histórico ficam nos [ADRs](adr); detalhes exclusivos do motor de conformidade ficam em
[arquitetura-conformidade.md](arquitetura-conformidade.md).

## Escopo do produto

O aplicativo desktop mantém projetos de expansão da rede de distribuição, importa referências a
folhas PDF, extrai e interpreta evidências do desenho, permite revisão humana e avalia regras de
conformidade. Todas as conclusões automáticas conservam a versão do método, a origem e a evidência
que as sustentam.

Estado versionado relevante:

| Componente | Versão atual |
|---|---|
| Pacote Python | `0.1.0` |
| Catálogo técnico | `2` |
| Registro de interpretação | `1.3.0` |
| Registro de conformidade distribuído | `cemig-normas-distribuicao-2025.6` |
| Método de conformidade | `6` |
| Migração SQLite mais recente | `0007_compliance_executions` |

## Modelo de domínio

`Projeto` é o agregado persistido. Ele reúne:

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
- Um ou vários PDFs podem ser adicionados na mesma seleção.
- Conteúdo duplicado, identificado por hash, não pode entrar duas vezes no mesmo projeto.
- A ordem de leitura é uma sequência de páginas persistida e pode intercalar páginas de PDFs
  diferentes.
- Remover um PDF elimina do projeto as páginas e os resultados dependentes, mas preserva o arquivo
  externo original.
- Excluir o projeto remove seus dados e arquivos pertencentes à área gerenciada, também preservando
  origens externas.

O fluxo normal não copia nem altera o PDF escolhido. Ele persiste a referência canônica, tamanho,
SHA-256, metadados e páginas. Um PDF importado de pacote pode apontar para a cópia publicada na área
gerenciada.

## PDFs protegidos

PDFs protegidos solicitam senha individualmente. Cada arquivo admite até três tentativas; cancelar
pula apenas o arquivo atual numa seleção múltipla.

A senha correta é indexada pela identidade verificável da origem e permanece apenas em memória.
Ela é descartada ao trocar ou limpar o conjunto visual, fechar o aplicativo ou quando tamanho,
modificação ou hash da origem deixam de corresponder. Senhas não entram no banco, cache, logs,
pacotes, backups nem estado da interface.

## Visualização

O visualizador central oferece paginação, zoom, rotação e navegação entre as folhas do projeto. Uma
prévia integral limitada é complementada por tiles de detalhe solicitados conforme o viewport. A
fila antiga é cancelada quando página, zoom, rotação, DPR ou origem mudam.

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

O Tesseract é um adaptador opcional e local. Sua assinatura inclui a versão real do executável,
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

O seed contém 39 regras habilitadas. A lista normativa completa está em
[catalogo-regras-conformidade.md](catalogo-regras-conformidade.md), e o desenho do motor está em
[arquitetura-conformidade.md](arquitetura-conformidade.md).

O domínio e a interface reconhecem `CONFORME`, `DIVERGENCIA` e `NAO_AVALIAVEL`. O avaliador atual
emite os dois primeiros para alvos aplicáveis e não cria achado quando alguma condição `when` falha.
Dentro de uma regra aplicável, requisito ausente conta como não atendido; por isso o registro inclui
fatos de guarda sempre que a ausência significa “escopo ainda não caracterizado”, e não violação.
Todo resultado com geometria rastreável recebe callout, inclusive resultados conformes e não
avaliáveis. A cor da marcação distingue o resultado sem alterar o PDF.

Uma execução de conformidade guarda a assinatura da sessão semântica, da revisão das regras e do
método. Alterar regras ou incrementar o método marca o snapshot anterior como desatualizado; a
reanálise é sempre explícita e cria ou reutiliza a execução idempotente correspondente.

## Registro de regras

O SQLite mantém revisões imutáveis do registro e números permanentes por ID técnico. Importar um
JSON:

- valida schema, tipos, operadores, escopos e vocabulário de fatos;
- mescla regras por ID;
- preserva todos os IDs atuais omitidos no arquivo;
- cria uma nova revisão assinada sem alterar o seed empacotado;
- republica um catálogo Markdown da revisão ativa na pasta de dados.

Na inicialização, atualizações oficiais são aplicadas seletivamente: definições locais modificadas e
IDs personalizados são preservados. A restauração de backup também reconcilia IDs locais ausentes
antes de liberar o registro restaurado.

## Persistência e recuperação

O banco SQLite fica, por padrão, em `%LOCALAPPDATA%\ZenyProjectHandler`. Alembic aplica as migrações
na inicialização. Entidades de domínio são serializadas por repositórios; modelos SQLAlchemy não são
usados como domínio.

Snapshots de análise, interpretação, decisões, conformidade e revisões de regras preservam
identidade e versão. Dados grandes e pesquisáveis possuem colunas próprias; os agregados completos
são mantidos em JSON canônico quando isso evita duplicar o modelo no schema relacional.

Publicações de arquivos usam temporário irmão, `fsync` quando disponível e substituição atômica. A
importação de projeto e a exclusão/limpeza de arquivos gerenciados mantêm journals reconciliados no
bootstrap. Estado corrompido ou ambíguo bloqueia a inicialização em vez de autorizar uma limpeza por
inferência.

## Portabilidade e backup

`.zphproj` é um ZIP verificável para um projeto. `.zphbackup` contém um snapshot do ambiente local.
Pacotes novos usam manifesto de formato 2 com caminhos relativos, tipos, tamanhos, SHA-256, estado
de integridade e omissões declaradas.

A importação possui preflight somente leitura e aplicação posterior à confirmação. O plano inclui a
identidade do pacote e do destino; qualquer mudança entre inspeção e aplicação exige novo preflight.
IDs, análises, propostas, revisões e resultados são preservados.

Antes do backup, todas as origens PDF são classificadas. Backup íntegro prossegue diretamente;
origens ausentes, alteradas ou ilegíveis exigem confirmação e geram pacote `DEGRADADO`. A restauração
de um pacote degradado ainda exige integridade de tudo que o manifesto declara.

A troca de cada arquivo é atômica e exceções capturadas disparam compensação. A restauração conjunta
de SQLite e árvore gerenciada não possui journal durável contra queda abrupta entre os recursos.

## Interface e concorrência

Análise, importação, exportação, backup e restauração executam fora da thread da interface e expõem
progresso e cancelamento cooperativo. Um coordenador global impede operações destrutivas ou
incompatíveis simultâneas. Objetos Qt visuais permanecem na thread principal.

Os painéis **Projeto**, **Resultados**, **Documentação e conformidade** e
**Importar, exportar e backup** podem ser movidos, desacoplados e restaurados. Tema, geometria e
estado dos docks ficam em `ui-state.ini` na pasta de dados.

## Exemplos e qualidade

`examples/` é uma bancada local dinâmica. Tudo abaixo dela, exceto seu README, é ignorado pelo Git.
Não existe manifesto de corpus ou gate privado. O gate padrão depende apenas de testes e fixtures
sintéticas versionadas.

`scripts/smoke_examples.py` percorre opcionalmente os PDFs locais, abre, renderiza, extrai,
interpreta e confirma que a origem não foi alterada. Um comportamento permanente observado nesses
arquivos deve virar uma fixture sintética. Comentários de comissionamento podem orientar
investigação, mas não substituem fonte normativa.

## Limites atuais

- Não há instalador para execução sem Python nem artefato de distribuição assinado.
- Reconhecimento visual pode permanecer ambíguo; a interface conserva o resultado para revisão em
  vez de forçar uma classificação.
- Cálculos elétricos e mecânicos completos e verificações dependentes de fontes restritas não são
  executados sem todos os fatos e referências necessários.
- Carimbo, rótulo ou campo de assinatura não comprova autoria ou autenticidade.
- Não existe integração ativa com serviços externos de OCR, nuvem ou IA; o pipeline funciona
  localmente com PyMuPDF e Tesseract.
