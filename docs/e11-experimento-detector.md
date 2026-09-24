# E11 — Detector visual treinável isolado

Este experimento acrescenta uma fonte de candidatos **somente ao benchmark
offline**. Nenhum peso, dependência neural ou método E11 entra em `src/`, no
cliente ou na composição. O aceite e a decisão de adoção constam no handoff E11
do roadmap; este documento descreve a execução reproduzível da frente A.

## Arquitetura escolhida e alcance

O candidato F07 é Faster R-CNN/FPN do Torchvision. A
[documentação oficial](https://docs.pytorch.org/vision/main/models/faster_rcnn.html)
expõe builders com ou sem pesos pré-treinados e avisa que o módulo de detecção
está em beta. `torch` e `torchvision` não estão na `.venv` local, não há
`nvidia-smi`, e os únicos 22 positivos operacionais da referência E02 de
desenvolvimento pertencem a um ancestral de desenho. Não foi iniciado download
de pesos nem instalação implícita. Pesos genéricos, mesmo se existissem, não
definem classes técnicas CEMIG. F07 fica **não executado**, sem métrica atribuída.

Para medir uma família aprendida executável com as dependências locais,
`scripts/experiments/e11_detector.py` treina do zero um classificador logístico
linear por classe em janelas raster. PyMuPDF renderiza a página base inteira;
Pillow reduz cada janela a 12 × 12 níveis de cinza; 145 atributos (pixels e
média) alimentam SGD determinístico. Cinco classes têm rótulos operacionais
confirmados de desenvolvimento: aterramento, para-raios MT/BT, transformador e
estai MT. `POSTE`, famílias/variantes sem rótulos de desenvolvimento e o símbolo
desconhecido ficam fora do domínio do modelo. A classe do desenho sintético não
certifica equivalência normativa.

Inferência varre janelas de dimensão mediana aprendida por classe, com passo de
pelo menos 6 pixels. O maior lado
da página renderizada tem no máximo 900 pixels; a página toda continua coberta,
mas símbolos muito pequenos podem desaparecer nessa resolução. O escore é a
saída logística **bruta e não calibrada**. O limiar 0,8, NMS 0,3 e teto global
de 40 candidatos por página foram fixados antes de consultar calibração ou PDFs
reais. O manifesto registra resolução, janelas com tinta examinadas, propostas
acima do limiar, supressões de NMS/tetos, tempo e working set do processo.
Este limite pode reduzir recall e precisa constar na decisão de integração.

## Dados e fronteiras

`prepare` usa o gerador autoral E02 para materializar apenas `development` e
`calibration`. `train` aceita somente a referência *completa e exatamente igual*
ao snapshot versionado `tests/fixtures/symbols/reference-development.json`,
confere SHA-256 de cada PDF e exige todos os documentos com split development e
um ancestral. Somente ocorrências base, operacionais e confirmadas geram
positivos. As outras regiões anotadas são excluídas das amostras negativas; o
fundo vem de janelas aleatórias com tinta, sem cruzar as caixas conhecidas.
São 21 ocorrências base de treino antes da augmentação; a ocorrência confirmada
da camada de anotação E02 fica fora do domínio deste raster.
Augmentação usa pequenos deslocamentos dos mesmos positivos de desenvolvimento.
Os controles negativos anotados foram excluídos da amostragem, não usados como
hard negatives; por isso o treinamento não ensina explicitamente a rejeitar
legenda, grade e glifos, uma limitação relevante diante dos FP medidos.
Calibração não altera pesos, limiar ou seleção de arquitetura. A reserva E02 não
é listada, aberta, renderizada ou inferida. PDFs de `examples/` são diagnóstico
exposto, não teste cego nem material de treino nesta etapa.

`infer` recebe somente modelo e raiz de PDFs; não tem parâmetro para referência,
ROI ou classe esperada. A saída é `predictions.json` E02 com documentos/SHA,
método, candidatos, cobertura base e anotação fora de domínio. IDs de corpus
sintético são os stems E02; com raiz `examples`, IDs são
`example:<caminho relativo POSIX com extensão>`. `compare` exige mapas
documento→SHA idênticos, IDs únicos de métodos/predições e uma execução por
documento/página/camada/método; preserva a união crua e chama o avaliador E02
quando recebe referência completa. O adapter separado
`scripts/experiments/e11_adapter.py` traduz uma página congelada para
`ResultadoMetodoSimbolos` E03, com assinatura/modelo e geometria reversível
no sistema da **página renderizada**. Em páginas rotacionadas, essa geometria
não afirma recuperar as coordenadas PDF não rotacionadas; o chamador deve passar
as dimensões da página exibida.
Não registra o método no pipeline.

## Comandos

Na raiz do repositório, com o Python da `.venv`:

```powershell
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector prepare --output tmp/e11-simbologia/data
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector train --reference tmp/e11-simbologia/data/development/reference.json --root tmp/e11-simbologia/data/development --output tmp/e11-simbologia/train --seed 20260924
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector infer --model tmp/e11-simbologia/train/model.json --root tmp/e11-simbologia/data/calibration --output tmp/e11-simbologia/eval-calibration
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector infer --model tmp/e11-simbologia/train/model.json --root tmp/e11-simbologia/data/development --output tmp/e11-simbologia/eval-development
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector infer --model tmp/e11-simbologia/train/model.json --root examples --output tmp/e11-simbologia/vp
```

Comparação V-P executada, sem filtrar candidatos nem fabricar referência global
a partir da revisão visual parcial:

```powershell
.\.venv\Scripts\python.exe -m scripts.experiments.e11_detector compare --baseline tmp/e11-simbologia/integration/baseline-all-examples/predictions.json --learned tmp/e11-simbologia/vp/predictions.json --output tmp/e11-simbologia/integration/union-examples
```

`compare` exige `--reference` completo para produzir relatório E02; sem essa
opção, une as saídas V-P e registra IDs/SHA sem produzir métrica global.
Esta união tem 11 documentos, 10 métodos e 569 candidatos (240 existentes +
329 E11), SHA-256
`590f3fc1595be91d64658f015c2d9789611eec4cd2f56117c720c14dddd92e4e`.
Modelo e relatórios ficam
somente em `tmp/e11-simbologia/`, fora do versionamento e do pacote do cliente.

## Ambiente e evidências de execução

Medição local: Windows 11, Python 3.13.14, PyMuPDF 1.28.0, Pillow 12.2.0;
`torch`, `torchvision`, NumPy, SciPy, OpenCV, scikit-learn e psutil ausentes na
`.venv`. E11 usa os pins já presentes para Pillow/PyMuPDF em
`requirements-experiments.lock` e a biblioteca padrão. O código do Torchvision
tem [licença BSD](https://github.com/pytorch/vision/blob/main/LICENSE); nenhum
código ou peso Torchvision foi incorporado. A titularidade das fixtures E02 é
autoral conforme `docs/e02-dados-benchmark-simbologia.md`; não se usam variantes
E07 `pending` como rótulos.

O primeiro treino gerou modelo SHA `dbe5940b…`, mas a telemetria de RAM veio
`null` por assinatura WinAPI incompleta. Esse resultado foi **invalidado antes
de qualquer inferência**. A instrumentação foi corrigida, testada com um
working set não nulo, e o treino refeito no mesmo corpus e seed. O código final
normalizado LF tem SHA-256
`fc563db2e40dda554a2aa1cba5833717498ce5945308e798b7c47646cfe61d28`.

| Saída congelada | PDF / páginas / candidatos | SHA-256 | Tempo 1 / 2 (s) | Pico working set 1 / 2 (MB) |
|---|---:|---|---:|---:|
| `train/model.json` | 4 / 6 / 5 classes | `ca1058ae22c900de1e173673b26e79643ec8cd5a000f4a60326b7f354739df1a` | 2,076 / 2,047 | 79,57 / 79,90 |
| `eval-development/predictions.json` | 4 / 6 / 73 | `6704f1654fd12552f2ef07698440fbfffbf7798247841ba7dc7a4dcae1d6aa62` | 1,029 / 1,032 | 94,02 / 94,29 |
| `eval-calibration/predictions.json` | 2 / 2 / 21 | `01c703baf217b628c6562c788776c063c0afe987eb4423631cad660dbddc2a4b` | 0,286 / 0,272 | 88,90 / 85,29 |
| `vp/predictions.json` | 11 / 11 / 329 | `56d962e583cd091ee527888d71e409c1d372246a9655aaae299c46fe0d73e738` | 10,985 / 10,639 | 197,78 / 194,43 |

Cada segunda execução escreveu em diretório `*-repeat`; modelo e cada JSON de
predições tiveram SHA **idêntico** nas duas execuções, diferença numérica de
candidatos/classes/caixas/scores **zero**. Tempo variou no máximo 0,346 s e
pico working set até 3,61 MB entre execuções; esses campos variáveis pertencem
aos manifestos e não ao modelo/predições. Todos os 19 percursos de página
(6 + 2 + 11) foram executados sem falha e PDFs tiveram SHA antes/depois igual.

Avaliação E02 independente das saídas congeladas:

| Partição | TP | FP | FN | Precisão | Recall | Interpretação |
|---|---:|---:|---:|---:|---:|---|
| Desenvolvimento | 8 | 65 | 14 | 0,1096 | 0,3636 | In-sample, um único ancestral; não mede generalização. |
| Calibração | 0 | 21 | 4 | 0 | 0 | Outro ancestral; dois `TRANSFORMADOR` da classe treinada e dois `POSTE` sem suporte. |

`POSTE` não foi treinado: seus dois FN de calibração não representam falha de
classificação de uma classe suportada. Os dois transformadores de calibração
também não foram localizados. Os 21 FP da calibração são 5 `ATERRAMENTO`,
12 `PARA_RAIOS_BT` e 4 `PARA_RAIOS_MT`; não houve predição de transformador.
Famílias sem ocorrência avaliável mantêm
denominador zero/recall `null`; nenhuma métrica da linha de desenvolvimento é
usada para votar adoção. A varredura teve 13.604 janelas com tinta no
desenvolvimento, 2.422 na calibração e 241.339 em V-P. O teto global suprimiu
10 candidatos em uma página de desenvolvimento e 347 em seis páginas V-P;
houve ainda 1.629 propostas V-P truncadas por tetos locais antes do teto
global. Esses números impedem alegar recall visual completo mesmo com todas
as páginas rasterizadas. O relatório visual V-P e a matriz de exclusivos,
produzidos após congelar outputs, fundamentam a decisão final no roadmap.
