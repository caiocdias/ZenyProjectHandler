# ADR 0003 - Ingestão PDF somente leitura e coordenadas reversíveis

- Status: aceita
- Data: 2026-07-21

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
   públicas de leitura, inventário e rasterização.
2. A inspeção calcula SHA-256 em fluxo, captura tamanho e data de modificação, abre o PDF sem salvar
   e confirma novamente que o arquivo não mudou durante a operação.
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
   visão; rotação gera um novo raster e reaplica as geometrias pela transformação registrada.

## Verificação

- O golden test usa uma página sintética de 72 x 48 pontos a 72 DPI. Dimensões devem ser exatas e
  as amostras RGB branca/vermelha admitem tolerância máxima de 8 níveis por canal para acomodar
  antialiasing controlado.
- O round-trip geométrico é exercitado em 72, 144 e 300 DPI e nas rotações 0, 90, 180 e 270 graus.
- As nove amostras privadas são endereçadas exclusivamente pelos hashes do manifesto; nomes e
  conteúdo sensível não entram nos testes versionados.

## Consequências

- A etapa 3 pode exibir e localizar geometrias sem conhecer postes, cabos ou o futuro analisador.
- O caminho local pode ficar indisponível se o usuário mover o arquivo. Empacotamento e relocalização
  serão tratados na etapa 10; até lá a ausência ou divergência de hash é reportada sem substituir a
  referência silenciosamente.
- Inventários podem ser recriados a partir do PDF e não aumentam o payload canônico do projeto.
- A interface desta etapa abre um PDF avulso. Vincular a importação a um projeto escolhido na
  interface depende das telas de gestão de projeto posteriores, embora o caso de uso transacional já
  esteja disponível.

## Licenciamento a resolver antes da distribuição

[PyMuPDF/MuPDF é oferecido sob GNU AGPL e licença comercial](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright).
Antes de distribuir o aplicativo, o responsável pelo produto deve confirmar formalmente a
conformidade com a AGPL ou contratar a licença comercial adequada. A porta `LeitorPdfPort` mantém
viável substituir o adaptador caso a decisão de licenciamento exija outra biblioteca.
