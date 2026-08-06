# Zeny Project Handler

Aplicativo desktop em Python para representar, revisar e futuramente interpretar projetos de expansão da rede de distribuição elétrica da CEMIG.

## Ambiente de desenvolvimento

Requisitos:

- Python 3.11, 3.12 ou 3.13;
- Windows para a aplicação desktop.

O `setup.bat` procura primeiro o Python Launcher (`py`) e depois o comando `python`. Quando o executável não estiver no `PATH`, defina `ZENY_BOOTSTRAP_PYTHON` com seu caminho completo antes de executar o setup.

## Preparação e execução no Windows

Execute uma vez:

```powershell
.\setup.bat
```

O script cria `.venv`, instala todas as versões fixadas em `requirements.lock`, instala o aplicativo
no ambiente virtual e só então valida o Tesseract e o idioma português. Se a instalação do
executável, a rede ou o provisionamento do idioma falhar, o setup retorna erro sem remover a
`.venv`: o aplicativo continua disponível com os extratores nativos e mostra na barra de status uma
ação com a remediação do OCR.

Para abrir o aplicativo sem uma janela de console, dê dois cliques em `ZenyProjectHandler.vbs` ou
execute:

```powershell
.\ZenyProjectHandler.vbs
```

O inicializador usa diretamente `.venv\Scripts\pythonw.exe`, portanto não depende de compilação ou
empacotamento em EXE. Erros de ambiente e de inicialização são apresentados em uma caixa de diálogo.
Para diagnóstico pelo terminal, `ZenyProjectHandler.bat` continua disponível e preserva a saída do
Python enquanto o aplicativo estiver aberto.

Para executar todos os gates de qualidade:

```powershell
.\IniciarTestes.bat
```

Esse é o **gate básico**: funciona offline em um clone limpo e exclui explicitamente os testes
marcados com `private_samples`. Ele não procura, calcula hashes nem abre PDFs reais em `examples/`.
O resultado consolidado é salvo em `relatorio-testes.txt` na raiz. O comando falha se lint,
formatação, tipagem, dependências, testes ou cobertura falharem. A cobertura deve permanecer
estritamente acima de 85,01%. O relatório também apresenta complexidade ciclomática, índice de
manutenibilidade e métricas de linhas de código.

Em um ambiente autorizado que possua todas as amostras do manifesto, execute separadamente o
**gate privado opt-in**:

```powershell
.\IniciarTestesPrivados.bat
```

Esse segundo fluxo executa somente `private_samples`, valida antes dos testes a presença, o tamanho
e o SHA-256 anônimo de cada amostra requerida e falha, sem `skip`, quando o corpus está ausente,
incompleto ou adulterado. O relatório local fica em `relatorio-testes-privados.txt`; ele não
substitui o gate básico nem autoriza publicar PDFs, nomes de arquivo ou conteúdo extraído.

## Preparação manual

Crie um ambiente virtual e instale as dependências de desenvolvimento:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps -e .
```

Execute a aplicação:

```powershell
.\.venv\Scripts\python.exe -m zeny_project_handler
```

Valide o projeto:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest -m "not private_samples" --cov
```

As decisões arquiteturais estão em [`docs/adr`](docs/adr) e a sequência de implementação está em [`docs/roadmap-desenvolvimento.md`](docs/roadmap-desenvolvimento.md).

## Dados locais e backup

Ao iniciar, o aplicativo cria e migra automaticamente
`%LOCALAPPDATA%\ZenyProjectHandler\zeny-project-handler.sqlite3`. A variável `ZENY_DATA_DIR` permite
usar outra pasta, inclusive em testes. O banco utiliza chaves estrangeiras, transações explícitas e
versionamento Alembic.

Backups começam por um preflight somente leitura das origens PDF e por um snapshot consistente do
SQLite, validado antes de substituir atomicamente o arquivo de destino. A pasta padrão reservada para
eles é `backups` dentro do diretório de dados. Arquivos do banco, WAL, temporários e backups não devem
ser adicionados ao Git.

Fotos e cópias internas restauradas/importadas ficam em `project-files/<project-id>`. PDFs escolhidos
diretamente pelo usuário permanecem origens externas somente leitura: remover um documento ou o
projeto elimina a referência local, nunca o PDF original. Fotos são blobs identificados por SHA-256;
uma remoção parcial só apaga o arquivo depois do commit e quando nenhuma referência viva do projeto
usa o digest.

## Transporte e recuperação

O painel **Portabilidade e recuperação** contém somente as operações de transporte e proteção dos
dados. Um projeto pode ser exportado como `.zphproj`, com manifesto assinado, banco restrito ao
projeto, PDFs disponíveis e resultados da análise. O pacote usa somente caminhos relativos e valida
internamente SHA-256, tamanho e tipo de cada arquivo ao ser importado. A importação preserva
identidades, catálogo, análises e decisões; substituir um projeto existente exige confirmação
explícita. Antes do diálogo, um preflight somente leitura valida manifesto, arquivos e SQLite,
detecta conflito e apresenta um resumo com fingerprint. Recusar preserva integralmente banco e pasta
local. Depois da confirmação, pacote e destino são revalidados sob o coordenador de operações; se
algum deles mudou, o plano é recusado como obsoleto e precisa ser inspecionado novamente, sem criar
`.previous`, publicar arquivos ou deixar staging.

Depois da confirmação, a substituição usa um journal persistente de formato 1 no namespace reservado
`project-files/.import-recovery`. Cada fase é publicada atomicamente e o commit do projeto grava, na
mesma transação SQLite, um comprovante com as identidades da operação, pacote, plano e árvore nova.
Na inicialização seguinte, um comprovante compatível conclui a limpeza; sem ele, os arquivos
anteriores são restaurados. A reconciliação pode ser repetida e termina antes de catálogo, serviços e
janela ficarem disponíveis.

Não edite nem apague manualmente `.import-recovery`. Journal ilegível, versão desconhecida, caminho
fora da raiz, recibo divergente ou árvore ambígua bloqueiam a inicialização para evitar remoção
insegura. Preserve a pasta e restaure um `.zphbackup` confiável ou encaminhe o diagnóstico ao suporte.
O log `logs/application.jsonl` registra `portability.import.recovery`, fase, ação e IDs seguros, mas
nunca caminhos do journal ou dos arquivos.

Exclusões usam o mesmo mecanismo compartilhado de publicação atômica de journals no namespace
separado `project-files/.cleanup-recovery`. A raiz de um projeto é primeiro renomeada para um
tombstone na mesma raiz gerenciada: rollback a restaura, enquanto commit confirmado permite a
remoção. Tarefas parciais registram somente UUID, digest e caminho relativo validado. Na próxima
inicialização, o SQLite decide entre restaurar e repetir a limpeza; uma falha pós-commit continua
visível no log e na UI e conserva o journal para nova tentativa. Não edite nem apague manualmente
`.cleanup-recovery`; caminho hostil, link ou estado ambíguo bloqueia a reconciliação sem alcançar
arquivos externos.

Novos `.zphproj` e `.zphbackup` usam manifesto de formato 2; pacotes antigos de formato 1 continuam
aceitos. O formato 2 registra `INTEGRO` ou `DEGRADADO` e, sem expor nomes ou caminhos, identifica por
IDs anônimos cada arquivo omitido e seu tratamento.

O backup completo `.zphbackup` inclui o banco local, arquivos gerenciados e cópias dos PDFs externos
que passaram no preflight. Se um PDF estiver ausente, alterado ou ilegível, o painel lista somente o
ID abreviado e a classificação e exige confirmação específica. Cancelar não cria pacote nem
temporários. Ao prosseguir, a UI informa que o backup foi **criado com ressalvas**; o manifesto
registra a omissão e, quando existe uma referência externa original, o snapshot a mantém sem
inventar uma cópia recuperável. A restauração ainda exige integridade física de todos os itens
declarados e informa as limitações de um backup degradado. Publicação, restauração e rollback
continuam atômicos.

## Visualização e origem dos PDFs

A janela principal mantém o leitor de PDF no centro. Fluxo, resultados da análise e portabilidade
continuam dockáveis; resultados e portabilidade compartilham abas à direita para não se
sobreporem. O leitor oferece
paginação, zoom, rotação e sobreposições gráficas.

Todo PDF selecionado no **Fluxo do projeto** é adicionado imediatamente ao projeto. Na lista de
folhas, arraste qualquer página ou use **Subir** e **Descer** para definir a ordem persistida de
leitura, inclusive intercalando páginas de PDFs diferentes. O arquivo original não é copiado nem
regravado: a ordem pertence ao projeto, enquanto o aplicativo calcula o SHA-256, registra metadados
e verifica o conteúdo antes de renderizar ou concluir uma importação.

Cada elemento identificado aparece no PDF como um sublinhado colorido e clicável. O clique abre a
aba **Resultados da análise** e seleciona o elemento correspondente. A visão principal é hierárquica:
cada região da folha reúne coordenada, acontecimentos, estruturas, equipamentos, postes, cabos e
vínculos próximos. Uma mesma região pode descrever simultaneamente retiradas, instalações e
elementos existentes, mesmo quando não há poste catalogado ou coordenada. Não há confirmação item a
item; resultados catalogados são incorporados automaticamente ao projeto e ficam imediatamente
disponíveis para as etapas seguintes.

A resolução solicitada por padrão é 600 DPI, que é o teto de detalhe visual disponível para
regiões. Ela não obriga a rasterizar uma prancha inteira nessa resolução. O visualizador produz uma
prévia integral limitada e, fora da thread da interface, solicita tiles detalhados apenas para o
viewport e uma margem. Tiles visíveis são priorizados pela proximidade do centro; pan, zoom, rotação,
navegação, DPR ou troca de página cancelam cooperativamente a fila anterior. `QPixmap`, cena, widgets
e overlays continuam restritos à thread da interface.

Os limites padrão são 8.000.000 pixels e 64 MiB por solicitação. A estimativa de pico usa 7 bytes
por pixel: 3 do buffer RGB proprietário entregue ao QImage e 4 da conversão para QPixmap. O cache
LRU de `QPixmap` usa no máximo 128 MiB por padrão, contabilizados por dimensões e profundidade. Sua
chave inclui identidade verificada (UUID, SHA-256, tamanho e `mtime`), página, rotação, zoom, DPR,
região e DPI; troca ou alteração da origem limpa integralmente o cache. Os quatro valores podem ser
configurados antes da inicialização; limites devem ser inteiros positivos e o DPI deve permanecer
entre 36 e 600:

```powershell
$env:ZENY_PDF_RENDER_DPI = "600"
$env:ZENY_PDF_RENDER_MAX_PIXELS = "8000000"
$env:ZENY_PDF_RENDER_MAX_BYTES = "67108864"
$env:ZENY_PDF_TILE_CACHE_MAX_BYTES = "134217728"
.\ZenyProjectHandler.vbs
```

Essas opções pertencem somente ao visualizador. Elas não alteram DPI, seleção de regiões,
decisões nem resultados do pipeline de análise/OCR. O roteiro de validação com uma prancha grande
autorizada está em [`docs/aceite-manual-visualizador-progressivo.md`](docs/aceite-manual-visualizador-progressivo.md).

O inventário técnico distingue texto, caminhos vetoriais, imagens incorporadas, anotações e seus
appearance streams, Form XObjects e Optional Content Groups. Uma falha localizada vira diagnóstico
da página e não invalida os demais recursos que ainda podem ser lidos ou renderizados.

O analisador nativo converte esses recursos em `EvidenciaDocumento` com geometria normalizada e
proveniência PDF. Texto preserva fonte, tamanho e rotação; vetores preservam comandos e cores; o
percurso de anotações e Form XObjects inclui imagens em appearance streams. A análise pode ser
recriada pelo hash do PDF e usa um cache JSON descartável em `cache/analysis` dentro da pasta de
dados. A identidade e a versão reais do extrator fazem parte tanto da chave desse cache quanto da
execução persistida, portanto uma atualização do reconhecimento refaz automaticamente resultados
antigos.

Para o Tesseract, essa identidade não é uma versão declarada manualmente. Na primeira consulta de
cada instância, com timeout, o adaptador obtém e normaliza a versão real do executável, fixa os
idiomas efetivamente selecionados, calcula SHA-256 de cada `traineddata` usado e inclui OEM, PSM,
listas permitidas, formato/agregação TSV, pré-processamento do raster e timeout de reconhecimento.
O hash canônico resultante não contém o caminho do executável nem do diretório `tessdata`: duas
instalações equivalentes em pastas diferentes têm a mesma assinatura. O mesmo hash participa da
chave do cache, do ID estável da execução e da proveniência persistida nas execuções e evidências.
Caches do schema anterior são apenas ignorados e reconstruídos sob demanda.

O `setup.bat` verifica o Tesseract e, quando ele não está presente, tenta instalar para o usuário o
pacote `UB-Mannheim.TesseractOCR` pelo Windows Package Manager (`winget`). O aplicativo o descobre no
`PATH`, no local padrão do Windows ou no caminho indicado por `ZENY_TESSERACT_PATH`. Se o pacote não
admitir instalação sem elevação nessa máquina, solicite a instalação ao administrador ou indique uma
instalação autorizada em pasta gravável por essa variável. O comando equivalente é:

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact --scope user
```

Encontrar o `.exe` não basta: tanto o setup quanto o diagnóstico de inicialização executam
`tesseract --list-langs` e só declaram o OCR português pronto quando `por` aparece. Se o idioma já
estiver na instalação selecionada, ele é usado no lugar. Caso contrário, o setup baixa somente
`por.traineddata` para a pasta gravável
`<dados-do-aplicativo>\ocr\tessdata-fast-4.1.0`; `ZENY_DATA_DIR` controla a raiz de dados e
`ZENY_TESSDATA_DIR` pode indicar outra pasta gravável. Não há tentativa de escrever em
`Program Files`. Quando `eng` existe na instalação, ele é copiado para a pasta gerenciada e o
adaptador seleciona `por+eng`; sem `eng`, seleciona `por`. Ausência de `por` desativa o OCR, sem
aceitar `eng` sozinho como sucesso da instalação.

O artefato provisionado vem do repositório oficial
[`tesseract-ocr/tessdata_fast`](https://github.com/tesseract-ocr/tessdata_fast), release assinada
`4.1.0`, revisão imutável `65727574dfcd264acbb0c3e07860e4e9e9b22185`:

- origem: [`por.traineddata`](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/65727574dfcd264acbb0c3e07860e4e9e9b22185/por.traineddata);
- tamanho observado: `1.982.756` bytes;
- SHA-256 obrigatório: `c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb`;
- licença: Apache-2.0, registrada em [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

O download é gravado primeiro em arquivo temporário na pasta gerenciada. Somente um conteúdo com o
SHA-256 fixado substitui `por.traineddata`; um arquivo inválido é descartado antes de qualquer uso.
`TESSDATA_PREFIX` é acrescentado apenas ao ambiente dos subprocessos `tesseract --list-langs` e de
reconhecimento, sem alterar o ambiente do aplicativo, do terminal ou do sistema.

Em uma máquina offline, obtenha o arquivo da origem acima por um canal autorizado, confira
`Get-FileHash .\por.traineddata -Algorithm SHA256`, copie-o para `ZENY_TESSDATA_DIR` (ou para a pasta
gerenciada padrão) e repita:

```powershell
.\.venv\Scripts\python.exe -m zeny_project_handler.tesseract_setup --provision
```

O comando ainda confirma o resultado pelo próprio `--list-langs`; não imprime sucesso se a rede,
o acesso à pasta, o checksum ou essa validação falhar. A inicialização exibe “OCR português
indisponível — como corrigir”, e a ação apresenta os mesmos passos. Para remover o dado provisionado,
feche o aplicativo e exclua somente `por.traineddata` e a cópia de `eng.traineddata` dessa pasta, ou
a pasta versionada `tessdata-fast-4.1.0` inteira. Ela é um recurso reconstruível, não participa dos
backups de projetos e funciona como cache local versionado do modelo: será recriada pelo próximo
setup. Não remova a raiz de dados do aplicativo.

O OCR é executado localmente, a 450 DPI e sem serviço de rede, em
páginas com pouco texto nativo, área raster relevante ou grande densidade vetorial — caso típico de
letras e números plotados como caminhos pelo AutoCAD. Desenhos vetoriais densos são divididos em
nove blocos sobrepostos antes do reconhecimento, para
preservar textos pequenos que se perderiam na segmentação da folha inteira. Em páginas com texto
nativo suficiente,
pequenas imagens com resolução útil são processadas por recorte, preservando a geometria correta na
folha sem renderizar a página inteira. Sem Tesseract, os demais extratores continuam funcionando e
a execução registra um diagnóstico revisável. Um executável defeituoso, uma consulta que exceda o
timeout, ausência de `por` ou um `traineddata` inacessível também desativa somente o OCR, com
diagnóstico sanitizado e remediação na interface;
texto, vetores, imagens, anotações e Form XObjects continuam sendo extraídos.

Marcadores de ponto desenhados como texto azul dentro de círculos vermelhos recebem uma segunda
passagem localizada a 1200 DPI. Quando as letras foram convertidas em contornos vetoriais, seus
glifos azuis são agrupados por geometria antes do OCR; isso recupera identificadores `P<n>` e
`V<n>-<n>`, inclusive inclinados. O fundo e os traços de outras cores são removidos, e marcadores
inclinados são alinhados antes do reconhecimento. Assim, identificadores como `P1`, `P10`, `P11` e
`V10-11` não dependem de posição fixa na folha. Um ponto reconhecido permanece listado no painel
mesmo quando nenhum poste, estrutura ou equipamento pôde ser associado a ele.

As caixas vetoriais verdes imediatamente abaixo de cada ponto também são usadas como guias. Cada
linha é isolada por cor e reconhecida separadamente a 1200 DPI, evitando que códigos pequenos como
`CM2(1)`, `S1N` e `11-300` sejam confundidos com textos vizinhos. Quando não há caixas, o bloco
escuro abaixo do marcador recebe uma leitura localizada, como ocorre em `P13`.

Rótulos lineares verdes ao longo da rede recebem um tratamento próprio a 1800 DPI. A caixa
inclinada é retificada por transformação afim antes da leitura, preservando pontuação técnica como
em `CM-50(3/8")`, `N- (1N2)` e `ABN-16(16)`. O mesmo eixo orienta uma leitura isolada dos textos
escuros de comprimento, como `54m (VR-49m)`. O identificador `V<n>-<n>` fixa as extremidades em
`P<n>` e permite que os dois cabos do mesmo trecho compartilhem o traçado e o comprimento.

Caixas vinho que envolvem nomenclaturas de equipamento também são usadas como guias geométricas,
inclusive quando inclinadas. O recorte é retificado a 1800 DPI, a borda colorida é removida e o
texto neutro é lido isoladamente. Pela convenção do projeto, qualquer elemento contido nessa
“bolha” é classificado como **a instalar**, independentemente da cor do próprio texto. Já uma
nomenclatura atravessada por um traço vinho recebe um recorte sem o traço e é classificada como
**a remover**.

Equipamentos sem nomenclatura textual também entram na análise. As assinaturas vetoriais da
`SIMBOLOGIA.pdf` reconhecem aterramento, para-raios MT e para-raios BT por proporções, paralelismo e
ângulos, tolerando rotação e as variações usuais de escala. Preto indica existente, verde indica
instalação e vermelho indica retirada. O resultado registra o tipo identificado, a confiança, a
situação e os vetores que originaram a evidência.

## Documentação e conformidade

O dock **Documentação e conformidade** acompanha o projeto aberto e possui visões próprias para:

- todos os pares `rótulo: informação` encontrados no cabeçalho e no quadro de servidão, além de
  candidatos a carimbo e indícios/campos de assinatura;
- regras conformes, possíveis divergências e casos não avaliáveis, sempre com fonte normativa.

O analisador identifica vãos por uma linha com extremidades associadas ou pelo identificador
operacional explícito `V<n>-<n>`. O segundo caso mantém o vão revisável mesmo quando uma das
extremidades ainda não possui poste classificado. O comprimento usa primeiro a anotação próxima ao
cabo e, quando ela não existe, a distância entre as coordenadas dos postes; a aba **Vãos** mostra o
identificador original e a fonte da medida. Ângulos ainda não são derivados. O scanner documental
não considera um carimbo ou rótulo de assinatura como prova de autenticidade. Cada informação vira
um fato com origem, confiança, geometria e evidências.
Regras ficam em um registro JSON versionado com condições de aplicabilidade, exceções comprovadas e
requisitos. A arquitetura e os limites estão detalhados em
[`docs/arquitetura-conformidade.md`](docs/arquitetura-conformidade.md).

O Unlimited-OCR foi avaliado como possível segunda passagem local para layouts difíceis. A
integração recomendada, caso o benchmark justifique, é diretamente por `MotorOcrPort` contra um
servidor local vLLM/SGLang. LM Studio + MCP não entra no pipeline determinístico nesta etapa; veja a
[`ADR 0012`](docs/adr/0012-ocr-local-por-porta-direta.md).

## Interpretação semântica por regras

O registro inicial em `adapters/interpretation/data/regras_interpretacao_v1.json` é versionado,
validado e possui assinatura de conteúdo. Cinco analisadores independentes reconhecem códigos ativos
do catálogo em texto nativo ou OCR. Postes também são reconhecidos pela nomenclatura de projeto
`altura-resistência`, por exemplo `11-300`. Também são aceitos `/`, `:`, `x`, espaços e quebra de
linha; na ausência de Circular, Duplo T ou Madeira, uma correspondência canônica do catálogo é usada
e os demais candidatos permanecem registrados na auditoria. Pares de coordenadas de campo próximos
ao poste são reconhecidos em texto nativo ou OCR, inclusive quando estão em linhas ou fragmentos
separados. Leste e norte são pareados uma única vez por fragmento e proximidade, evitando reutilizar
o mesmo número em pontos vizinhos. Vetores e imagens próximos são vinculados como contexto para
geometria, cor e proveniência.

Linhas reconhecidas como cabeçalho, como `Dispositivo:`, `Circuito:` e `Projeto:`, continuam
disponíveis para a inspeção documental, mas não entram no inventário da rede. Nomenclaturas de cabo
coerentes que ainda não possuem item exato no catálogo, como `ABCN-4(4)`, são preservadas como
propostas conflitantes para classificação humana, incluindo a situação instalar/remover derivada da
simbologia.

Nomenclaturas de equipamento como `100A/10KA/2H` aceitam barras, dois-pontos ou hífens e são
normalizadas para o código canônico do catálogo, como `100A-10KA-2H`. Quando uma nomenclatura válida,
como `100A/2KA/2H`, ainda não existe no catálogo publicado, ela continua visível como proposta
conflitante em vez de ser descartada.

Aterramento e para-raios BT/MT reconhecidos somente pela simbologia geram propostas de equipamento
com a classe exibida diretamente em **Elementos**. Como a legenda não informa modelo ou capacidade,
essas propostas permanecem não catalogadas e conflitantes para a revisão humana, sem inventar um
tipo técnico mais específico.

O interpretador preserva `PropostaElemento` e `PropostaRelacao` como trilha auditável e promove
automaticamente os resultados catalogados ao agregado do projeto. Situação de obra usa as
assinaturas de cor do catálogo; estruturas e equipamentos preferem postes com a mesma situação
(instalar, remover ou existente), antes da distância. Cada resultado mantém evidências, regra,
versão, confiança e justificativa. Uma execução cancelada ou interrompida pode ser retomada com a
mesma identidade sem duplicar resultados nem entidades promovidas.

O mesmo pipeline possui um adaptador para o benchmark. O teste final continua bloqueado enquanto o
conjunto de avaliação não estiver congelado e os critérios não estiverem aprovados.

## Regiões de ocorrência no PDF

Depois da interpretação, os elementos são agrupados por proximidade na mesma folha. Cada região é
uma visão derivada e determinística da análise: ela informa o PDF, a página, eventual par de
coordenadas UTM, tudo o que será instalado ou removido e o que já existe no local. Os vínculos
semânticos permanecem visíveis dentro da região, mas não são transformados em nós ou arestas. O
painel consolida a análise mais recente de cada PDF do projeto e segue a ordem de leitura das páginas.
Componentes sem identificador só são anexados a uma região `P<n>` quando estão suficientemente
próximos do conjunto rotulado; isso evita atribuir, por exemplo, uma estrutura isolada acima do ponto
ao ponto apenas por encadeamento espacial.

Coordenadas são coletadas de texto nativo e OCR, inclusive quando leste e norte aparecem separados
por quebra de linha, `:`, `/` ou em fragmentos próximos. Selecionar a região destaca sua extensão;
selecionar um elemento abre a folha correspondente e destaca seu sublinhado clicável. Ícones de olho
permitem ocultar temporariamente no PDF uma região inteira ou somente elementos individuais, sem
apagar o resultado auditável.

## Projetos reais para testes

PDFs reais podem ser colocados em `examples/`, mas são ignorados pelo Git porque podem conter dados
pessoais, coordenadas e fotografias. O repositório mantém somente
`evaluation/manifesto-amostras.json`, com IDs anônimos, hashes, partições e características
técnicas. Consulte `examples/README.md` e `evaluation/POLITICA-ACESSO.md` antes de adicionar ou
substituir uma amostra.

O conjunto de avaliação separa desenvolvimento de teste final e possui formatos JSON explícitos
para manifesto, critérios e anotações. O benchmark compara elementos e relações por geometria
normalizada, calcula precisão e recall por classe, falhas de extração, latência p95 e pico de memória
Python, e gera uma assinatura semântica que ignora variações de tempo de execução. O corpus atual
ainda está em preparação: falta diversidade de escala, revisão humana e aprovação dos limites antes
do congelamento.

O `requirements.lock` foi gerado no Windows com Python 3.12 e deve ser validado também no Python 3.11 antes da primeira distribuição.
