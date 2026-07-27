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

O script cria `.venv`, instala todas as versões fixadas em `requirements.lock` e instala o aplicativo no ambiente virtual.

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

O resultado completo é salvo em `relatorio-testes.txt` na raiz. O comando falha se lint, formatação, tipagem, dependências, testes ou cobertura falharem. A cobertura deve permanecer estritamente acima de 85%. O relatório também apresenta complexidade ciclomática, índice de manutenibilidade e métricas de linhas de código.

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
.\.venv\Scripts\python.exe -m pytest --cov
```

As decisões arquiteturais estão em [`docs/adr`](docs/adr) e a sequência de implementação está em [`docs/roadmap-desenvolvimento.md`](docs/roadmap-desenvolvimento.md).

## Dados locais e backup

Ao iniciar, o aplicativo cria e migra automaticamente
`%LOCALAPPDATA%\ZenyProjectHandler\zeny-project-handler.sqlite3`. A variável `ZENY_DATA_DIR` permite
usar outra pasta, inclusive em testes. O banco utiliza chaves estrangeiras, transações explícitas e
versionamento Alembic.

Backups são snapshots consistentes do SQLite, validados antes de substituir atomicamente o arquivo
de destino. A pasta padrão reservada para eles é `backups` dentro do diretório de dados. Arquivos do
banco, WAL, temporários e backups não devem ser adicionados ao Git.

## Transporte e recuperação

O painel **Portabilidade e recuperação** contém somente as operações de transporte e proteção dos
dados. Um projeto pode ser exportado como `.zphproj`, com manifesto assinado, banco restrito ao
projeto, PDFs disponíveis e resultados da análise. O pacote usa somente caminhos relativos e valida
internamente SHA-256, tamanho e tipo de cada arquivo ao ser importado. A importação preserva
identidades, catálogo, análises e decisões; substituir um projeto existente exige confirmação
explícita.

O backup completo `.zphbackup` inclui o banco local, arquivos gerenciados e cópias dos PDFs externos.
Sua publicação e restauração usam trocas atômicas e validação do SQLite. Assim, uma gravação
interrompida não substitui o último backup íntegro, e os PDFs recuperados deixam de depender do local
original. Gestão de fotos e relatório de integridade não fazem parte da interface.

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

A resolução padrão é 600 DPI, o máximo aceito pela configuração do visualizador, evitando que textos
pequenos de pranchas técnicas fiquem borrados ao ampliar. Ela pode ser reduzida entre 36 e 600 DPI
antes da inicialização quando houver restrição de memória:

```powershell
$env:ZENY_PDF_RENDER_DPI = "400"
.\ZenyProjectHandler.vbs
```

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

O `setup.bat` verifica o Tesseract e, quando ele não está presente, instala automaticamente o pacote
`UB-Mannheim.TesseractOCR` pelo Windows Package Manager (`winget`). O aplicativo o descobre no
`PATH`, no local padrão do Windows ou no caminho indicado por `ZENY_TESSERACT_PATH`. Se a instalação
automática não estiver disponível, o comando equivalente é:

```powershell
winget install --id UB-Mannheim.TesseractOCR
```

Instale também os dados de idioma `por` quando o instalador oferecer essa opção. O aplicativo usa
`por+eng` automaticamente quando ambos estão disponíveis e mantém `eng` como fallback. O OCR é
executado localmente, a 450 DPI e sem serviço de rede, em
páginas com pouco texto nativo, área raster relevante ou grande densidade vetorial — caso típico de
letras e números plotados como caminhos pelo AutoCAD. Desenhos vetoriais densos são divididos em
nove blocos sobrepostos antes do reconhecimento, para
preservar textos pequenos que se perderiam na segmentação da folha inteira. Em páginas com texto
nativo suficiente,
pequenas imagens com resolução útil são processadas por recorte, preservando a geometria correta na
folha sem renderizar a página inteira. Sem Tesseract, os demais extratores continuam funcionando e
a execução registra um diagnóstico revisável.

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
