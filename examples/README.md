# Exemplos locais

Use esta pasta como bancada para PDFs de verificação exploratória. Todo o conteúdo abaixo de
`examples/` é local e ignorado pelo Git; somente este guia pertence ao repositório.

Não existe lista fixa nem conjunto privado obrigatório para o gate portátil. A pasta pode estar
vazia e esse gate continuará usando apenas fixtures sintéticas versionadas. A
[curadoria contínua de simbologia](../docs/fluxo-curadoria-incremental-simbologia.md)
descobre recursivamente todos os PDFs disponíveis e registra cobertura por
arquivo e página.

Para ampliar a cobertura depois, coloque PDFs em qualquer subpasta de `examples/` e envie em uma
nova tarefa o [prompt one-shot de curadoria incremental](../docs/fluxo-curadoria-incremental-simbologia.md#prompt-one-shot-para-usar-após-adicionar-pdfs).
Esse fluxo tem etapas e evidências próprias e pode ser repetido a cada nova amostragem.
Adicionar arquivos por si só não treina nem atualiza o detector: o conhecimento duradouro são
pacotes e testes versionados após revisão visual, fontes e validação.

Para exercitar, sob demanda, todos os PDFs encontrados também em subpastas:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_examples.py
```

O smoke abre cada arquivo, renderiza a primeira página, extrai evidências nativas, executa o
interpretador e confirma que tamanho e data de modificação da origem não mudaram. Ele não habilita
OCR nem grava relatórios. A ausência de PDFs é válida; uma falha não impede a inspeção dos arquivos
seguintes, mas faz o comando terminar com código diferente de zero.

O smoke não cumpre a auditoria visual: ele renderiza somente a primeira página
e não faz revisão por IA. A curadoria registra hashes, imagens da base/aparência
anotada e achados de todas as páginas em `tmp/curadoria-simbologia/`, ignorado
pelo Git. FP/FN, duplicatas e exclusivos só são avaliados após revisão visual e
inferência congelada. Uma página sem achado continua no denominador.

Para inferir simbologia em todos os arquivos/páginas:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --include-packages --include-raster --include-structural --include-legend --output tmp/curadoria-simbologia/predictions
```

O [fluxo de curadoria](../docs/fluxo-curadoria-incremental-simbologia.md)
descreve os artefatos, a inspeção independente de imagens e o baseline sintético
portátil. O comando acima apenas infere; não realiza revisão visual automática.
Referência parcial de IA não autoriza calcular recall global ou considerar regiões
não anotadas como FP. A ausência de PDFs é registrada com `completed=false`/exit 1.

Os exemplos vistos são desenvolvimento/diagnóstico, inclusive os que já tenham
sido chamados de reserva em relatórios históricos. As reservas sintéticas
anteriores já foram consumidas e não podem servir como teste cego repetido.
Anotações e regiões do revisor não podem alimentar a inferência. Ausência de arquivos, falha de
leitura ou páginas não inspecionadas devem constar no relatório; não equivalem a aprovação.

Resultados observados em documentos reais são diagnósticos locais. Uma garantia permanente deve ser
reproduzida por uma fixture sintética pequena, pública e determinística. Comentários de revisão podem
priorizar investigação, mas regras técnicas só podem vir de fonte normativa identificada.

Não adicione PDFs reais ao Git: eles podem conter dados pessoais, coordenadas, fotografias e outras
informações sensíveis.
