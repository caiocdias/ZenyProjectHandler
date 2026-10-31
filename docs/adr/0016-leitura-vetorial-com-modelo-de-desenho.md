# ADR 0016 - Leitura vetorial com modelo de desenho e ficha do poste

- Estado: aceito
- Data: 2026-10-30
- Design: `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md`

## Contexto

Só o PDF chega, exportado do Electric Office (via "Microsoft Print To PDF"), do AutoCAD ou repassado
por sistemas de carimbo (iText). Na metade Electric Office o texto da rede é contorno vetorial, não
texto. Por isso a leitura atual depende de OCR sobre raster, e falha em símbolos e na associação
texto → poste.

## Decisão

- Cada página vira um modelo de desenho derivado e descartável, guardado no cache do ADR 0004. Ele
  reúne texto recuperado, polilinhas e arcos reconstruídos, grupos candidatos a símbolo e camadas.
  Símbolos e associação rodam sobre ele.
- A família do PDF é reconhecida por impressão estrutural e escolhe o perfil de recuperação.
- O texto em contorno é lido por assinatura de forma contra uma tabela de glifos versionada. Glifo
  desconhecido vira diagnóstico, nunca palpite.
- O resultado é a ficha do poste, montada com as propostas e relações atuais. A coordenada UTM
  escrita e a escala ajustam a transformação página → UTM; posição e vãos divergentes viram
  pendência de revisão.
- O analisador novo tem versão própria e só substitui o atual, e os detectores e o OCR que ele
  tornar inúteis, quando for ≥ em todas as métricas por poste, sem regressão por folha.

## Alternativas descartadas

- Converter PDF em DWG: não traz informação nova e exige SDK proprietário.
- OCR em DPI maior: lê de forma aproximada o que já é geometria exata.

## Consequências

A precisão passa a ser medida por poste. O OCR e o Tesseract podem sair do servidor se nenhuma
família precisar deles. A tabela de glifos é um novo dado a curar, específico por fonte.
