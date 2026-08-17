# Exemplos locais

Use esta pasta como bancada para PDFs de verificação exploratória. Todo o conteúdo abaixo de
`examples/` é local e ignorado pelo Git; somente este guia pertence ao repositório.

Não existe manifesto, lista fixa, partição privada ou conjunto obrigatório. A pasta pode estar vazia
e o gate padrão continuará usando apenas fixtures sintéticas versionadas.

Para exercitar, sob demanda, todos os PDFs encontrados também em subpastas:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_examples.py
```

O smoke abre cada arquivo, renderiza a primeira página, extrai evidências nativas, executa o
interpretador e confirma que tamanho e data de modificação da origem não mudaram. Ele não habilita
OCR nem grava relatórios. A ausência de PDFs é válida; uma falha não impede a inspeção dos arquivos
seguintes, mas faz o comando terminar com código diferente de zero.

Resultados observados em documentos reais são diagnósticos locais. Uma garantia permanente deve ser
reproduzida por uma fixture sintética pequena, pública e determinística. Comentários de revisão podem
priorizar investigação, mas regras técnicas só podem vir de fonte normativa identificada.

Não adicione PDFs reais ao Git: eles podem conter dados pessoais, coordenadas, fotografias e outras
informações sensíveis.
