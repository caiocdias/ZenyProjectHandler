# Zeny Project Handler

Aplicativo desktop para organizar, visualizar e analisar projetos de expansão da rede de
distribuição elétrica. O programa mantém o PDF original intacto, extrai evidências nativas e por
OCR, propõe elementos técnicos e apresenta verificações de conformidade rastreáveis.

O produto está em desenvolvimento. Os PDFs de `examples/` mostram a direção desejada para a
análise, mas comentários de comissionamento não são tratados automaticamente como normas.

## Instalar e abrir

Requisitos: Windows e Python 3.11, 3.12 ou 3.13.

Na primeira execução:

```powershell
.\setup.bat
```

O setup cria `.venv`, instala as versões de `requirements.lock` e tenta preparar o Tesseract com o
idioma português. Uma falha apenas no OCR não desfaz o ambiente Python já instalado; a aplicação
continua disponível com a extração nativa de PDFs.

Abra sem console com duplo clique em `ZenyProjectHandler.vbs`. Para diagnóstico pelo terminal:

```powershell
.\ZenyProjectHandler.bat
```

## Fluxo principal

1. No painel **Projeto**, crie ou abra um projeto.
2. Adicione um ou mais PDFs. Os arquivos originais permanecem somente leitura.
3. Ajuste a ordem das folhas, se necessário.
4. Clique em **Analisar projeto**.
5. Confira os elementos e vãos em **Resultados** e navegue para a evidência no PDF.
6. Em **Documentação e conformidade**, execute as verificações disponíveis.

Resultados automáticos são propostas auditáveis. Informações ambíguas ou sem contexto suficiente
permanecem como não avaliáveis e não são apresentadas como certeza técnica.

## Regras de conformidade

O painel de regras permite somente:

- importar um registro JSON;
- exportar o registro ativo.

Não existe ação de remoção. Uma importação pode atualizar uma regra pelo mesmo ID, mas IDs atuais
omitidos são preservados. A persistência e a restauração de backup aplicam a mesma proteção.

As oito regras distribuídas hoje cobrem apenas fatos que o pipeline consegue produzir com segurança.
Novas famílias identificadas nos projetos comissionados permanecem no
[`catálogo de regras`](docs/catalogo-regras-conformidade.md) até existir fonte normativa e evidência
confiável para automatizá-las.

## Projetos locais em `examples/`

`examples/` é uma bancada local e dinâmica. Coloque, substitua ou remova PDFs quando quiser; não há
manifesto, cadastro por hash, partição privada nem congelamento. Todo o conteúdo da pasta, exceto seu
README, é ignorado pelo Git e não vai para o GitHub.

Para executar o smoke somente leitura em todos os PDFs locais:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_examples.py
```

Esse smoke procura PDFs recursivamente, abre, renderiza, extrai e interpreta cada arquivo sem fixar
contagens específicas. Quando um exemplo revela uma regressão, o comportamento mínimo relevante deve
virar uma fixture sintética e versionável. Assim os testes continuam determinísticos sem burocratizar
os documentos usados durante o desenvolvimento.

Veja [`examples/README.md`](examples/README.md) para a política completa, que é deliberadamente curta.

## Testes e qualidade

Execute o gate padrão:

```powershell
.\IniciarTestes.bat
```

Ele verifica dependências, Ruff, formatação, Mypy, testes públicos, cobertura e complexidade. O gate
não depende de arquivos em `examples/`; os testes de comportamento usam PDFs sintéticos pequenos.
O relatório local é salvo em `relatorio-testes.txt` e também é ignorado pelo Git.

Comandos individuais:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest --cov
```

## Dados, transporte e backup

Por padrão, banco e arquivos gerenciados ficam em
`%LOCALAPPDATA%\ZenyProjectHandler`. Defina `ZENY_DATA_DIR` para usar outro diretório.

- Projetos podem ser importados e exportados como `.zphproj`.
- Backups abrangem o banco e os arquivos gerenciados.
- PDFs externos continuam no local escolhido pelo usuário; removê-los do projeto não apaga o
  original.
- A importação valida caminhos, tamanho, tipo e SHA-256 dos arquivos do pacote.
- Restaurações compensam falhas capturadas. Como não há journal durável entre todos os recursos,
  uma interrupção abrupta do processo durante a troca não deve ser chamada de transação atômica.

## OCR

O pipeline usa primeiro texto, vetores, imagens e anotações nativas. O OCR local entra apenas quando
necessário. O idioma português vem de `tesseract-ocr/tessdata_fast`, revisão
`65727574dfcd264acbb0c3e07860e4e9e9b22185`, SHA-256
`c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb`, licença Apache-2.0.
Detalhes de terceiros estão em [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Estrutura e documentação

O código usa domínio independente, casos de uso, portas, adaptadores e interface Qt. Essa separação é
mantida onde protege testes ou troca de infraestrutura; não é requisito criar uma abstração para cada
função interna.

Documentos mantidos:

- [`docs/especificacao-funcional.md`](docs/especificacao-funcional.md): comportamento do produto e
  modelo de domínio;
- [`docs/modelo-entidades.mmd`](docs/modelo-entidades.mmd): visão estrutural;
- [`docs/roadmap-desenvolvimento.md`](docs/roadmap-desenvolvimento.md): estado atual e próximos
  incrementos;
- [`docs/arquitetura-conformidade.md`](docs/arquitetura-conformidade.md): funcionamento do motor de
  fatos e regras;
- [`docs/catalogo-regras-conformidade.md`](docs/catalogo-regras-conformidade.md): regras operacionais
  e candidatos;
- [`docs/adr`](docs/adr): decisões arquiteturais que ainda explicam o código atual.

Histórico detalhado de implementação, comandos já executados e prompts antigos pertencem ao Git, não
aos documentos vivos.

## Limites atuais

<<<<<<< HEAD
- Os exemplos comissionados ainda possuem expectativas sem cobertura automática integral.
- O provedor real de prova para a exceção de vãos entre 45 e 60 m ainda não existe; sem prova, o
  resultado é não avaliável.
- Cálculos mecânicos, ângulos e algumas consistências entre desenho, orçamento e anexos ainda exigem
  revisão humana.
- O empacotamento para uma máquina sem Python continua como etapa futura.
=======
O backup completo `.zphbackup` inclui o banco local, arquivos gerenciados e cópias dos PDFs externos
que passaram no preflight. Se um PDF estiver ausente, alterado ou ilegível, o painel lista somente o
ID abreviado e a classificação e exige confirmação específica. Cancelar não cria pacote nem
temporários. Ao prosseguir, a UI informa que o backup foi **criado com ressalvas**; o manifesto
registra a omissão e, quando existe uma referência externa original, o snapshot a mantém sem
inventar uma cópia recuperável. A restauração ainda exige integridade física de todos os itens
declarados e informa as limitações de um backup degradado. A publicação de cada arquivo é atômica;
a restauração conjunta usa compensação para exceções capturadas, mas ainda não possui journal durável
contra encerramento abrupto entre banco e anexos. Ao restaurar, o registro de regras do backup permanece como base, mas todo ID
presente na revisão ativa anterior e ausente do backup é reaplicado antes de liberar a operação.
IDs coincidentes mantêm o conteúdo restaurado, salvo a migração de segurança de uma Regra 6 oficial
legada; se a reconciliação falhar, banco, arquivos e catálogo voltam ao estado anterior. Ao combinar
backups de bancos independentes, o ID técnico permanece, mas uma colisão entre sequências locais pode
atribuir outro número de exibição.

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

PDFs protegidos solicitam a senha em campo mascarado, individualmente por arquivo. Cada item permite
até três senhas digitadas; **Cancelar** pula somente aquele PDF durante uma seleção múltipla e o
resumo informa quantos foram adicionados, cancelados, ficaram sem senha válida ou falharam. Senhas
corretas são reutilizadas somente na sessão atual e pela identidade SHA-256, tamanho e `mtime` da
origem. Limpar/trocar o conjunto visual, fechar ou reiniciar o aplicativo, ou alterar a identidade do
arquivo exige nova solicitação.

Antes de criar a thread de análise, a interface faz o preflight de todos os documentos e resolve as
credenciais na thread principal; workers nunca abrem diálogos. Senhas não são gravadas no SQLite,
log, cache de análise/visual, manifesto de pacote, backup, `QSettings` ou mensagens de erro. Elas
existem apenas no provedor em memória e nas chamadas transitórias do leitor/analisador.

Cada elemento identificado aparece no PDF como um sublinhado colorido e clicável. O clique abre a
aba **Resultados da análise** e seleciona o elemento correspondente. A visão principal é hierárquica:
cada região da folha reúne coordenada, acontecimentos, estruturas, equipamentos, postes, cabos e
vínculos próximos. Uma mesma região pode descrever simultaneamente retiradas, instalações e
elementos existentes, mesmo quando não há poste catalogado ou coordenada. Não há confirmação item a
item; resultados catalogados são incorporados automaticamente ao projeto e ficam imediatamente
disponíveis para as etapas seguintes.

Possíveis divergências com geometria rastreável aparecem em uma camada independente como caixas
brancas de texto vermelho e linhas com seta aberta para os fatos, evidências ou alvos que sustentam a
localização. As caixas são posicionadas deterministicamente dentro da folha e reduzem colisões entre
si. Achados sem geometria continuam na lista como **Sem localização no PDF**. Essa apresentação é
somente da cena gráfica: não altera o PDF e não participa do raster ou do cache de tiles. Cada achado
localizável possui um olho próprio, além das ações **Exibir todos** e **Ocultar todos**; esses
controles não afetam os identificadores de elementos nem o contorno temporário.

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
- o registro ativo de regras, com importação e exportação. Não há controles para ativar,
  desativar ou remover regras individualmente; o estado `enabled` pode mudar somente por um JSON
  importado e IDs omitidos no arquivo permanecem na revisão ativa.

Ao concluir o pipeline, o aplicativo persiste atomicamente uma execução auditável de conformidade
ligada à sessão semântica e à revisão exata das regras. A aba carrega esse último snapshot, ordena
possíveis divergências primeiro e mostra valores observados/esperados, fonte, revisão e localização.
Selecionar uma linha abre e centraliza o callout realçado; clicar na caixa ou seta seleciona a linha
e traz o dock para frente. A ocultação temporária sobrevive à navegação e à ordenação, mas é
reiniciada ao trocar projeto ou execução. Achados sem callout permanecem listados com olho
desabilitado e diagnóstico. Se o registro ativo mudar, o resultado é marcado como desatualizado sem
ser reinterpretado. Mudanças na versão do próprio método de conformidade também invalidam o
snapshot anterior.

O botão **Analisar conformidade** cria uma nova execução explícita a partir dos resultados semânticos
já persistidos. Essa operação não reabre o PDF e não repete extração ou OCR; execuções anteriores
permanecem no histórico.

O analisador identifica vãos por uma linha com extremidades associadas ou pelo identificador
operacional explícito `V<n>-<n>`. O segundo caso mantém o vão revisável mesmo quando uma das
extremidades ainda não possui poste classificado. O comprimento usa primeiro a anotação próxima ao
cabo e, quando ela não existe, a distância entre as coordenadas dos postes; a aba **Vãos** mostra o
identificador original e a fonte da medida. Ângulos ainda não são derivados. O scanner documental
não considera um carimbo ou rótulo de assinatura como prova de autenticidade. Cada informação vira
um fato com origem, confiança, geometria e evidências.

Comentários de revisão PDF não podem originar elementos, regiões ou fatos técnicos; portadores
`AutoCAD SHX Text` do próprio desenho são preservados. Contexto urbano/rural só é aceito por
metadado confirmado ou campo permitido e rotulado do cabeçalho. Na Regra 6, vãos acima de 45 m e até
60 m ficam não avaliáveis sem prova positiva da exceção; acima de 60 m, um marcador de exceção
indevido não suprime a possível divergência.
Regras ficam em um registro JSON versionado com condições de aplicabilidade, exceções comprovadas e
requisitos. O SQLite preserva revisões imutáveis e números permanentes por ID dentro da linhagem do
banco; cada mudança também gera atomicamente um catálogo Markdown explicativo na pasta de dados do usuário. A arquitetura e os
limites estão detalhados em
[`docs/arquitetura-conformidade.md`](docs/arquitetura-conformidade.md).
Ao atualizar o seed `2025.3` para `2025.4`, somente a Regra 6 ainda idêntica à versão oficial anterior
é migrada; IDs adicionais e regras personalizadas são preservados.
Na atualização `2025.4` para `2025.5`, somente os IDs oficiais ausentes das duas regras de
transformador em posteação existente são anexados. Colisões conservam a definição local e reiniciar
o aplicativo não cria outra revisão.

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
o mesmo número em pontos vizinhos. As coordenadas enriquecem somente elementos vinculados a um
identificador operacional `P<n>`; sozinhas, não promovem referenciais elétricos a elementos do
projeto. Vetores e imagens próximos são vinculados como contexto para geometria, cor e proveniência.

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
>>>>>>> 51a97e2ba161a5914a20d6988ea9270393104e55
