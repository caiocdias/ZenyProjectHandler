# ADR 0004 - Evidências nativas, OCR condicional e cache derivado

- Status: aceita
- Data: 2026-07-21

## Contexto

O inventário da ingestão informa que certos recursos existem, mas a interpretação futura precisa de
objetos uniformes, com geometria normalizada, conteúdo, propriedades e proveniência. A extração deve
continuar útil quando um recurso PDF isolado estiver malformado, não pode depender da interface e
não deve tornar OCR ou um serviço externo obrigatórios.

Imagens visíveis podem estar em Form XObjects ou em appearance streams de anotações. Consultar
somente a lista de imagens da página perde esses casos. Ao mesmo tempo, o material extraído é
derivado do PDF e não deve competir com o original como fonte canônica.

## Decisão

1. `AnalisadorDocumentoPort` é o contrato consumido pelo caso de uso. O primeiro adaptador,
   `PyMuPdfDocumentAnalyzer`, usa PyMuPDF 1.28.x; domínio, aplicação e testes com adaptador falso não
   importam essa biblioteca.
2. Texto é extraído no nível de span e preserva caracteres, fonte, tamanho, cor, opacidade, modo de
   escrita, rotação e quad. Desenhos preservam comandos de linha, curva, retângulo e quad, além de
   cor, preenchimento, espessura, tracejado, camada e ordem de pintura.
3. Ocorrências de imagens usam a geometria efetivamente exibida e registram hash, dimensões,
   espaço de cor, transformação, `xref`, recurso e Form XObject referenciador quando disponíveis.
4. Anotações são percorridas por `xref`, incluindo `Stamp`, `Popup`, `FreeText`, `Square` e outros
   subtipos. As raízes `/AP` e seus recursos indiretos são percorridos com limite configurável e
   proteção contra ciclos. Imagens e Forms encontrados recebem proveniência
   `APARENCIA_ANOTACAO`.
5. Todo candidato usa coordenadas normalizadas da página visual, com a rotação intrínseca aplicada,
   e só depois é materializado como `EvidenciaDocumento`. Um recurso interno de appearance stream
   cuja transformação própria não seja exposta recebe os limites da anotação e o atributo explícito
   `geometria_aproximada = true`; `xref`, raiz, profundidade e nome do recurso preservam o rastreio.
6. Cada extrator é uma unidade de falha. Erros localizados viram `DiagnosticoAnalise` persistido na
   `ExecucaoAnalise`; evidências válidas dos outros extratores são mantidas. Uma falha fatal registra
   a execução como `FALHOU`.
7. OCR é uma porta opcional (`MotorOcrPort`). Rasterização e reconhecimento só são chamados quando a
   página possui menos texto nativo que o limite configurado. A aplicação não inclui nem exige motor
   OCR nesta etapa; a ausência é um diagnóstico, não uma tentativa de instalação ou acesso à rede.
8. O cache JSON guarda candidatos normalizados, nunca IDs de uma execução. Sua chave combina
   SHA-256 do PDF, configuração e nome/versão do analisador. O arquivo fica em `cache/analysis` na
   pasta de dados, é publicado por substituição atômica e pode ser apagado ou reconstruído.
9. Na materialização, IDs de evidência usam UUID v5 dentro do ID da execução e uma chave estável do
   recurso. A mesma entrada, configuração e execução produz o mesmo resultado semântico, inclusive
   quando os candidatos vêm do cache.
10. O caso de uso `ExecutarAnaliseDocumento` valida a referência local, executa o adaptador e grava
    execução e evidências em uma transação SQLite. O PDF permanece somente leitura.

## Verificação

- O PDF sintético cobre texto horizontal e rotacionado, linha, Bézier, polígono, cores, imagem de
  página, imagem em Form aninhado e imagem adicionada ao appearance stream de um carimbo.
- O mesmo arquivo também contém `Stamp`, `Popup`, `FreeText` e `Square`.
- Um motor OCR falso prova que uma página com texto nativo não é rasterizada e uma página apenas com
  imagem é rasterizada uma única vez.
- Testes de contrato exercitam o adaptador real e um falso. Testes de integração verificam
  persistência, reaproveitamento do cache e registro de falha fatal.

## Consequências

- A etapa 5 pode construir um conjunto de avaliação diretamente sobre evidências estáveis, sem
  depender de widgets ou detalhes do PyMuPDF.
- O cache pode crescer e será tratado como dado temporário; ele não participa de backup nem de
  portabilidade do projeto.
- OCR real continua sendo uma decisão substituível. Adicionar Tesseract ou outro mecanismo exigirá
  um adaptador, testes de qualidade e revisão de distribuição, mas não alteração no domínio.
- A decisão de licenciamento do PyMuPDF registrada no ADR 0003 continua pendente antes da
  distribuição do aplicativo.

## Referências técnicas

- [Estrutura de `rawdict` e propriedades de texto](https://pymupdf.readthedocs.io/en/latest/textpage.html)
- [Extração de desenhos vetoriais](https://pymupdf.readthedocs.io/en/latest/recipes-drawing-and-graphics.html)
- [Objetos, streams e recursos PDF](https://pymupdf.readthedocs.io/en/latest/document.html)
