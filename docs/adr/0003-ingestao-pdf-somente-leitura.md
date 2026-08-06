# ADR 0003 - Ingestão PDF somente leitura e coordenadas reversíveis

- Status: aceita
- Data: 2026-07-21
- Atualizada: 2026-08-06

## Contexto

O PDF é simultaneamente a origem visual do projeto e um arquivo potencialmente sensível. A
aplicação precisa inventariar sua estrutura, renderizar páginas e posicionar geometrias sem alterar
o original, sem acoplar casos de uso ao leitor escolhido e sem antecipar a interpretação semântica
da etapa 4.

As páginas podem ter `CropBox` diferente de `MediaBox`, rotação intrínseca e conteúdo visível em
anotações, appearance streams, Form XObjects e Optional Content Groups. Portanto, relacionar uma
geometria apenas à largura e altura raster não é suficiente para garantir posicionamento reversível.

## Decisão

1. `LeitorPdfPort` é o contrato da aplicação. O primeiro adaptador usa PyMuPDF 1.28.x e somente APIs
   públicas de leitura, inventário e rasterização. Para navegação repetida, a porta fornece uma
   `SessaoLeituraPdfPort` explicitamente encerrável.
2. A abertura/inspeção calcula SHA-256 uma vez em fluxo e captura tamanho, `mtime`, `ctime`, dispositivo
   e identidade do arquivo. Os metadados são conferidos depois do hash e da inspeção; divergência
   invalida a operação sem aceitar o inventário produzido.
3. `PaginaDocumento` registra as matrizes públicas PDF -> página e página -> página rotacionada,
   além de `MediaBox`, `CropBox`, dimensões e rotação. `TransformadorCoordenadasPagina` faz round-trip
   entre espaço PDF, coordenadas normalizadas, pixels e cena gráfica.
4. A coordenada normalizada canônica usa origem no canto superior esquerdo da página visual já com a
   rotação intrínseca aplicada. A rotação adicional do visualizador não muda a geometria canônica.
5. A inspeção retorna inventários de texto, vetores, imagens, anotações/aparências, Form XObjects e
   OCGs. Eles são dados derivados e não são a evidência semântica da etapa 4.
6. Falhas de um extrator ou objeto isolado geram `DiagnosticoPdf` com página e `xref` quando
   disponível. Os demais extratores e a renderização continuam.
7. A referência absoluta da origem fica na tabela local `document_sources`, separada do agregado e
   validada por hash. O PDF só é anexado ao projeto após inspeção bem-sucedida e o projeto e a
   referência são confirmados na mesma unidade de trabalho.
8. `PdfGraphicsView` exibe raster RGB e sobreposições na mesma cena. Zoom é uma transformação da
   visão; rotação gera um novo raster e reaplica as geometrias pela transformação registrada. O DPI
   visual solicitado aceita no máximo 600 e representa teto de detalhe, não resolução integral
   obrigatória.
9. A sessão retém somente a inspeção, os metadados verificados e a credencial efêmera. Antes e
   depois de cada rasterização ela faz uma comparação barata desses metadados. Cada uso abre e fecha
   seu próprio `fitz.Document`; nenhum descritor permanece aberto entre usos, e a sessão é invalidada
   definitivamente diante de remoção, substituição ou modificação da origem.
10. Não existe cache global por caminho. O visualizador possui as sessões dos documentos atualmente
    abertos e as encerra ao limpar, substituir ou fechar a interface. Inspeção/importação, análise e
    portabilidade continuam calculando e comparando hashes integrais em suas fronteiras de integridade.
11. Toda rasterização visual recebe `OrcamentoRenderizacaoPdf`, com limites independentes de pixels e
    bytes. `PlanoRenderizacaoPdf` calcula, antes de `Page.get_pixmap()`, o `IRect` exato da página e do
    clip após escala/rotação. O limite de bytes considera pico conservador de 7 bytes por pixel: RGB
    compartilhado por PyMuPDF/QImage e armazenamento esperado do QPixmap. Se uma página integral não
    couber, o plano escolhe por busca a maior prévia em DPI inteiro que satisfaça ambos os limites; se
    nem 1 DPI couber, a solicitação é rejeitada antes da alocação.
12. Clips usam coordenadas normalizadas canônicas e podem conservar 600 DPI quando cabem no orçamento.
    O plano devolve dimensões da página, dimensões do clip e sua origem no raster rotacionado.
    `TransformadorCoordenadasPagina` usa esses dados para manter round-trip e overlays alinhados em
    raster integral ou regional, inclusive com `CropBox`, rotação intrínseca e rotação adicional.
13. `PaginaPdfRenderizada` expõe uma `memoryview` de `Pixmap.samples_mv` e retém o `Pixmap` que possui
    esse buffer. `QImage` apenas o envolve enquanto o resultado está vivo; a cópia intermediária para
    `bytes` e `QImage.copy()` foi removida. `QPixmap.fromImage()` continua sendo a conversão necessária
    na thread da interface. O pipeline de análise/OCR não usa esse contrato nem teve seus DPIs ou
    decisões alterados.

## Verificação

- O golden test usa uma página sintética de 72 x 48 pontos a 72 DPI. Dimensões devem ser exatas e
  as amostras RGB branca/vermelha admitem tolerância máxima de 8 níveis por canal para acomodar
  antialiasing controlado.
- O round-trip geométrico é exercitado em 72, 144 e 300 DPI e nas rotações 0, 90, 180 e 270 graus.
- Goldens assimétricos conferem cores, dimensões, origem dos clips e alinhamento normalizado nas
  rotações adicionais 0, 90, 180 e 270 graus. Um caso separado combina `CropBox` com rotação
  intrínseca.
- PDFs sintéticos A0 e A1 registram as dimensões que uma página integral teria a 600 DPI sem criar
  esse raster. A prévia real permanece sob os dois limites, e um clip de 1% preserva 600 DPI.
- Um hasher instrumentado comprova um único SHA-256 por sessão ao navegar por páginas, recortes e
  rotações. Alteração, remoção e movimentação da origem invalidam a sessão sem novo hash implícito.
- O teste de movimentação ocorre com a sessão ainda viva, comprovando no Windows que nenhum handle
  persistente bloqueia backup, restauração ou substituição do arquivo.
- As nove amostras formais privadas são endereçadas exclusivamente pelos hashes do manifesto.
  PDFs exploratórios adicionais em `examples/` são descobertos e identificados apenas pelo hash em
  smoke tests locais somente leitura, sem exigir inclusão no manifesto. Nomes e conteúdo sensível
  não entram nos testes versionados.

## Consequências

- A etapa 3 pode exibir e localizar geometrias sem conhecer postes, cabos ou o futuro analisador.
- O caminho local pode ficar indisponível se o usuário mover o arquivo. Empacotamento e relocalização
  serão tratados na etapa 10; até lá a ausência ou divergência de hash é reportada sem substituir a
  referência silenciosamente.
- Inventários podem ser recriados a partir do PDF e não aumentam o payload canônico do projeto.
- Uma página grande pode aparecer inicialmente com DPI efetivo menor que o teto configurado. O
  backend regional já fornece clips detalhados; priorização, composição assíncrona e cache limitado
  de tiles pertencem à etapa progressiva seguinte.
- Uma sessão invalidada não tenta se recuperar por caminho nem recalcula o hash silenciosamente: o
  chamador precisa abrir e inspecionar a origem novamente.
- A interface desta etapa abre um PDF avulso. Vincular a importação a um projeto escolhido na
  interface depende das telas de gestão de projeto posteriores, embora o caso de uso transacional já
  esteja disponível.

## Licenciamento a resolver antes da distribuição

[PyMuPDF/MuPDF é oferecido sob GNU AGPL e licença comercial](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright).
Antes de distribuir o aplicativo, o responsável pelo produto deve confirmar formalmente a
conformidade com a AGPL ou contratar a licença comercial adequada. A porta `LeitorPdfPort` mantém
viável substituir o adaptador caso a decisão de licenciamento exija outra biblioteca.
