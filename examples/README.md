# Amostras locais de projetos

Esta pasta pode receber PDFs reais para testes locais. Os arquivos `*.pdf` são ignorados pelo Git
porque podem conter dados pessoais, coordenadas e fotografias.

O arquivo `../evaluation/manifesto-amostras.json` registra somente identificadores anônimos, hashes,
partição e características técnicas. Para localizar uma amostra, calcule o SHA-256 do PDF local e
compare com o manifesto. Nomes de arquivos, nomes de clientes, telefones e coordenadas não devem ser
incluídos no manifesto, em logs ou em relatórios versionados.

As amostras reais serão usadas inicialmente como corpus de smoke/regressão. Fixtures sintéticas
continuam necessárias para cenários ausentes, como PDF multipágina, rotacionado, protegido,
corrompido, escaneado e com `CropBox` diferente de `MediaBox`.
