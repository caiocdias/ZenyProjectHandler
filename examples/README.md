# Exemplos locais

Use esta pasta para qualquer PDF que ajude numa verificação exploratória. Todo o conteúdo abaixo de
`examples/` é local e ignorado pelo Git; somente este guia pertence ao repositório. Não há manifesto,
lista fixa, divisão de corpus ou requisito de completar um conjunto específico.

O gate padrão usa apenas fixtures sintéticas e funciona igual com a pasta vazia ou cheia. Para
exercitar, sob demanda, todos os PDFs locais encontrados também em subpastas, execute:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_examples.py
```

O smoke inspeciona, renderiza a primeira página, extrai evidências nativas e executa o interpretador.
Ele não habilita OCR, não grava relatório e verifica que tamanho e data de modificação da origem não
mudaram. A ausência de PDFs é um resultado válido; uma falha em um arquivo não impede a inspeção dos
demais e faz o comando terminar com código diferente de zero.

Resultados observados em arquivos reais são diagnósticos locais. Uma garantia permanente deve ser
representada por uma fixture sintética pública e determinística. Regras técnicas só podem nascer de
fonte normativa identificada, nunca apenas de comentários ou padrões vistos nesses PDFs.
