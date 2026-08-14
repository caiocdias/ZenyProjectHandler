# Amostras locais de projetos

Esta pasta pode receber PDFs reais para testes locais. Os arquivos `*.pdf` são ignorados pelo Git
porque podem conter dados pessoais, coordenadas e fotografias.

O arquivo `../evaluation/manifesto-amostras.json` registra somente identificadores anônimos, hashes,
partição e características técnicas. Para localizar uma amostra, calcule o SHA-256 do PDF local e
compare com o manifesto. Nomes de arquivos, nomes de clientes, telefones e coordenadas não devem ser
incluídos no manifesto, em logs ou em relatórios versionados.

O manifesto, e não a contagem desta pasta, define o corpus formal. Na auditoria de 14/08/2026, os
dez PDFs locais tinham hashes distintos entre si e nenhum correspondia aos nove hashes formais;
eles devem ser tratados como amostras exploratórias até aprovação e atualização explícita do
manifesto.

As amostras reais serão usadas inicialmente como corpus de smoke/regressão. Fixtures sintéticas
continuam necessárias para cenários ausentes, como PDF multipágina, rotacionado, protegido,
corrompido, escaneado e com `CropBox` diferente de `MediaBox`.

O gate básico (`..\IniciarTestes.bat`) ignora integralmente esta pasta. Em um ambiente autorizado,
o gate privado deve ser acionado de forma explícita com `..\IniciarTestesPrivados.bat`; ele compara
as amostras locais ao manifesto por tamanho e SHA-256 e falha claramente se o conjunto requerido
estiver ausente ou divergente. Os arquivos continuam locais e não devem ser adicionados ao Git.
