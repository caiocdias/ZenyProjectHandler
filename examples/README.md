# Exemplos locais

Use esta pasta para qualquer PDF que ajude numa verificação exploratória. Todo o conteúdo abaixo de
`examples/` é local e ignorado pelo Git; somente este guia pertence ao repositório. Não há manifesto,
lista fixa, divisão de corpus ou requisito de completar um conjunto específico.

O gate padrão usa apenas fixtures sintéticas e funciona igual com a pasta vazia ou cheia. Para
exercitar, sob demanda, todos os PDFs locais encontrados também em subpastas, execute:

<<<<<<< HEAD
```powershell
.\.venv\Scripts\python.exe scripts\smoke_examples.py
```
=======
O manifesto, e não a contagem desta pasta, define o corpus formal. Na auditoria de 14/08/2026, os
dez PDFs locais tinham hashes distintos entre si e nenhum correspondia aos nove hashes formais;
eles devem ser tratados como amostras exploratórias até aprovação e atualização explícita do
manifesto.

As amostras reais serão usadas inicialmente como corpus de smoke/regressão. Fixtures sintéticas
continuam necessárias para cenários ausentes, como PDF multipágina, rotacionado, protegido,
corrompido, escaneado e com `CropBox` diferente de `MediaBox`.
>>>>>>> 51a97e2ba161a5914a20d6988ea9270393104e55

O smoke inspeciona, renderiza a primeira página, extrai evidências nativas e executa o interpretador.
Ele não habilita OCR, não grava relatório e verifica que tamanho e data de modificação da origem não
mudaram. A ausência de PDFs é um resultado válido; uma falha em um arquivo não impede a inspeção dos
demais e faz o comando terminar com código diferente de zero.

Resultados observados em arquivos reais são diagnósticos locais. Uma garantia permanente deve ser
representada por uma fixture sintética pública e determinística. Regras técnicas só podem nascer de
fonte normativa identificada, nunca apenas de comentários ou padrões vistos nesses PDFs.
