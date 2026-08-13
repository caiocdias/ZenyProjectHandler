# ADR 0004 - Evidências nativas, OCR condicional e cache derivado

- Status: aceita
- Data: 2026-07-21
- Atualizada: 2026-08-06

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
7. OCR é uma porta opcional (`MotorOcrPort`). Antes de reconhecer, o motor fornece uma consulta de
   capacidade que retorna uma capacidade válida ou diagnósticos sanitizados. Ausência, timeout,
   executável defeituoso, idioma inválido ou `traineddata` inacessível desativam somente o OCR; os
   extratores nativos continuam e não há instalação nem acesso à rede durante a análise.
8. `CapacidadeMotorOcr` produz uma assinatura SHA-256 canônica a partir da implementação, versão real
   normalizada, ordem dos idiomas efetivamente selecionados, SHA-256 dos `traineddata` relevantes e
   todos os parâmetros semânticos do adaptador. No Tesseract isso inclui OEM, PSM de cada perfil,
   whitelists, formato/agregação TSV, pré-processamento PPM e timeout de reconhecimento.
9. Caminhos do executável e de `tessdata` nunca entram na capacidade. O adaptador consulta
   `--version` e `--list-langs` uma vez por instância, com timeout; depois fixa o diretório de dados
   identificado para que o reconhecimento use exatamente os arquivos que foram assinados.
   `TESSDATA_PREFIX` existe somente no ambiente dos subprocessos de metadados/reconhecimento.
10. O cache JSON guarda candidatos normalizados, nunca IDs de uma execução. Sua chave combina
    SHA-256 do PDF, configuração e a assinatura de capacidade do analisador, que incorpora a
    assinatura OCR. O schema incompatível anterior é rejeitado como cache vazio e reconstruído sob
    demanda, sem migração de dado derivado.
11. A mesma assinatura do analisador participa do UUID v5 estável da extração e é persistida nos
    parâmetros de `ExecucaoAnalise` e `EvidenciaDocumento`. Assim, versão, idioma, `traineddata` ou
    configuração diferente cria outra execução e deixa proveniência verificável.
12. Na materialização, IDs de evidência usam UUID v5 dentro do ID da execução e uma chave estável do
    recurso. O caso de uso valida a referência local e grava execução e evidências em uma transação
    SQLite. O PDF permanece somente leitura.
13. A inicialização consulta um componente de runtime separado e só compõe o adaptador quando
    `tesseract --list-langs` confirma `por`. O setup pode provisionar o `por.traineddata` oficial de
    `tessdata_fast` 4.1.0, revisão `65727574dfcd264acbb0c3e07860e4e9e9b22185`, em pasta gravável de
    dados do aplicativo. SHA-256 é conferido antes da substituição atômica; análise e inicialização
    nunca baixam dados. Quando `eng` já está instalado, uma cópia local permite selecionar
    `por+eng` na mesma raiz sem escrever em `Program Files`.

## Verificação

- O PDF sintético cobre texto horizontal e rotacionado, linha, Bézier, polígono, cores, imagem de
  página, imagem em Form aninhado e imagem adicionada ao appearance stream de um carimbo.
- O mesmo arquivo também contém `Stamp`, `Popup`, `FreeText` e `Square`.
- Um motor OCR falso prova que uma página com texto nativo não é rasterizada e uma página apenas com
  imagem é rasterizada uma única vez.
- Motores falsos provam que versão, idiomas, `traineddata` e OEM diferentes invalidam cache e
  identidade de execução. Subprocessos simulados provam consulta única, timeout diagnosticável e
  assinatura igual para instalações de conteúdo idêntico em caminhos diferentes.
- O cache rejeita explicitamente o schema anterior, e a execução/evidências persistem a mesma
  assinatura usada pela chave derivada.
- Testes de contrato exercitam o adaptador real e um falso. Testes de integração verificam
  persistência, reaproveitamento do cache e registro de falha fatal.

## Consequências

- O smoke dos exemplos e as regressões sintéticas podem consumir evidências estáveis sem depender de
  widgets ou detalhes do PyMuPDF.
- O cache pode crescer e será tratado como dado temporário; ele não participa de backup nem de
  portabilidade do projeto.
- Tesseract continua substituível por outro mecanismo que implemente a mesma consulta de capacidade;
  uma implementação sem identidade reproduzível não satisfaz mais a porta.
- Falha de rede ou de provisionamento não remove a `.venv` nem bloqueia os extratores nativos. O
  setup retorna erro e a interface mantém uma remediação visível até `por` ser validado.
- Calcular hashes dos `traineddata` tem custo de I/O, limitado à primeira consulta de cada instância.
  O ganho é impedir reaproveitamento silencioso de resultados produzidos por dados diferentes.
- A decisão de licenciamento do PyMuPDF registrada no ADR 0003 continua pendente antes da
  distribuição do aplicativo.

## Referências técnicas

- [Estrutura de `rawdict` e propriedades de texto](https://pymupdf.readthedocs.io/en/latest/textpage.html)
- [Extração de desenhos vetoriais](https://pymupdf.readthedocs.io/en/latest/recipes-drawing-and-graphics.html)
- [Objetos, streams e recursos PDF](https://pymupdf.readthedocs.io/en/latest/document.html)
- [`tessdata_fast` e licença Apache-2.0](https://github.com/tesseract-ocr/tessdata_fast/tree/65727574dfcd264acbb0c3e07860e4e9e9b22185)
- [Configuração de `TESSDATA_PREFIX`](https://tesseract-ocr.github.io/tessdoc/Compiling-%E2%80%93-GitInstallation.html)
