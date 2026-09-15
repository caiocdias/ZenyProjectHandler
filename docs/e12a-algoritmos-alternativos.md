# E12A — Experimentação de algoritmos alternativos

Execução em 15/09/2026 sobre `172afd5`. Git inicialmente limpo; nenhum `AGENTS.md`
aplicável encontrado. E12 concluída, extrator 1.16.0 e interpretador 23.0 conferidos.
Roadmap, diretriz vigente, diagnóstico, handoffs E10/E11/E12, portas, adaptadores,
benchmark e fixtures lidos. As diferenças em relação ao diagnóstico 1.14/22.0 são
as entregas documentadas E11/E12; nenhuma divergência adicional não tratada.

**Resultado:** dois candidatos distintos executados, incluindo controles reais.
Nenhum substitui o pipeline atual com segurança. O OCR neural fornece um ganho
documental complementar; o grafo corrige três associações e regride em outras.
Conclusão de experimentação não significa aceite da leitura integral ou integração.

## Isolamento e referência

- Fonte de desenvolvimento E10 preservada: 988.018 bytes, SHA-256
  `0793c292df9722ff48df31ab052018d4233ad3541706f50f53e994cc1670af06`.
  Hash, tamanho e mtime conferidos antes/depois. Nenhum PDF enviado a serviço externo.
- Referência congelada: `tmp/rede-1256407599/e10/inventory.json`, 139 registros,
  29 ocorrências operacionais, 64 itens documentais, nove pontos, dez trechos,
  seis comprimentos e dois conflitos. Denominadores preservados.
- `evaluation-split.json` foi lido somente para identificar a separação. Os dois
  documentos candidatos à reserva e as famílias H01/H02/H03 não foram abertos,
  gerados, ajustados ou avaliados. Este ensaio não mede generalização.
- Algoritmos recebem PDF/evidências, nunca inventário/ROIs de referência. O
  comparador separado usa a referência **depois** da inferência. Recortes de
  inspeção foram gerados depois das saídas, sem nova calibração nesses recortes.
- Novos arquivos em `scripts/experiments/`, entrada opt-in
  `scripts/benchmark_network_alternatives.py`, testes em
  `tests/unit/test_network_alternatives.py`. Nenhuma alteração em `src/`, bootstrap,
  contratos, cache ou promoção. As portas existentes foram suficientes; não se
  anunciou uma implementação completa de `InterpretadorEvidenciasPort` para o grafo.
- Runtime/modelos, transcrições, relatórios, cópia histórica do código e recortes
  ficam ignorados em `tmp/`. O lock experimental não participa de builds/releases.

## Candidatos e fontes primárias

### R — Detector DB e reconhecedor visual PP-OCRv4/SVTR

`rapid_ocr.py`, versão experimental `e12a-1`, implementa a porta OCR mínima e
mantém uma saída adicional com quadriláteros. RapidOCR 1.4.4 executa modelos ONNX
locais de detecção, orientação e reconhecimento. É uma família distinta de
Tesseract, não uma variação de DPI/PSM. A implementação e o pacote instalado foram
inspecionados. A [documentação de modelos RapidOCR 1.4.4](https://rapidai.github.io/RapidOCRDocs/v1.4.4/model_list/)
identifica os modelos locais e sua origem PaddleOCR; a arquitetura é descrita no
[relatório PP-OCRv4](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version2.x/ppocr/blog/PP-OCRv4_introduction.md).

RapidOCR e PaddleOCR usam Apache-2.0; os modelos convertidos preservam os termos
do projeto de origem. Foram conferidos o metadata/LICENSE do wheel e as fontes
[RapidOCR](https://github.com/RapidAI/RapidOCR) e
[PaddleOCR LICENSE](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE).
ONNX Runtime usa MIT. Não há distribuição de modelos nesta entrega.

Modelos incluídos no wheel, sem download durante inferência:

| Arquivo | SHA-256 |
|---|---|
| `ch_PP-OCRv4_det_infer.onnx` | `d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9` |
| `ch_PP-OCRv4_rec_infer.onnx` | `48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b` |
| `ch_ppocr_mobile_v2.0_cls_infer.onnx` | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |

Reconhecedor chinês/inglês: não se presume suporte adequado a acentos portugueses.
O controle riscado chegou a produzir um caractere estranho ao literal. O adapter
não corrige esse texto pelo catálogo nem converte confiança em autoridade.

Segmentação adicional independente: grade fixa 3×4, sobreposição normalizada 0,02,
600 DPI, camadas sem/com anotações separadas. As 24 regiões cobrem a página inteira;
não são recortes escolhidos pelo inventário. O DB detecta polígonos dentro delas.
Transformação inversa usa a origem inteira real do pixmap, escala e tamanho da
página. Guarda texto, confiança, polígono, página, camada, tile e hash do raster.
O teto de 8 MP é de memória por tile, não temporal; maior raster é falha explícita.
Máximo observado: 3.770.672 pixels. RGB é liberado por tile; o runtime neural tem
alocações adicionais, cujo pico total não foi medido neste ensaio.

`interpret_rapid.py` reaplica o **mesmo interpretador 23.0** às evidências nativas
sem OCR e aos 133 registros neurais da camada base. Os 195 registros da aparência
ficam no relatório, aguardando reconciliação E11/E12B. Não são promovidos como
conteúdo vigente. Não há promoção/persistência de nenhuma proposta neural.
Métodos existentes especializados em Tesseract/contornos não foram simulados:
as perdas semânticas medem também essa incompatibilidade de integração.

### G — Grafo de extremidades e atribuição global com abstenção

`global_graph.py`, versão `e12a-1`: extrai polilinhas das evidências nativas,
consolida extremidades por página, cria identidades compartilhadas de nó e atribui
rótulos P e medidas pelo problema global de custo mínimo. Usa caminhos aumentantes
do algoritmo húngaro, implementado em Python, com destinos de abstenção. Ao proibir
cada associação vencedora, resolve novamente: ótimos empatados ficam sem escolha.
Cruzamentos internos não geram junção elétrica. Código/situação continuam provenientes
das propostas verticais; associação elemento→nó/traçado ainda usa geometria local.
Logo, é um protótipo híbrido: a novidade global não elimina todos os passos locais.

Não exige modelo treinado nem GPU. A formulação e o oráculo foram conferidos na
[documentação SciPy de atribuição](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linear_sum_assignment.html).
SciPy 1.15.3, [BSD-3-Clause](https://github.com/scipy/scipy/blob/v1.15.3/LICENSE.txt),
serviu de oráculo em 100 matrizes de desenvolvimento; os ótimos coincidiram.
O solver público também passou contra enumeração exaustiva de matrizes pequenas.
O grafo em si não depende de SciPy. Não há modelo/treino escondido no algoritmo.

Filtros experimentais fixados antes da comparação: polilinhas não brancas com
extremidades separadas por ≥0,035, agrupamento de extremidades até 0,006; abstenção
de atribuição global em 0,055. Não reconhece automaticamente poste/padrão nem
continuidade fora da folha. Distâncias entre condutores do mesmo ponto podem
exceder o agrupamento; isso foi medido como defeito, sem aumentar tolerâncias até
acertar a referência. A consolidação por símbolos físicos fica para E14.

## Ambiente e reprodução

Windows 11 x64, Python 3.12.14, CPU AMD64 Family 23 Model 104 Stepping 1,
16 processadores lógicos, RAM física 16.486.035.456 bytes (consulta Win32 local).
ONNX Runtime 1.30.0, CPUExecutionProvider, quatro threads intra-op e uma inter-op;
CUDA/DirectML desligados. PyMuPDF 1.28.0 e Pillow 12.2.0 nos três reconhecedores.
Tesseract 5.4.0.20240606, `por+eng`. Versões efetivas adicionais:
NumPy 2.3.5, OpenCV 5.0.0.93, SciPy 1.15.3, Pyclipper 1.4.0, Shapely 2.1.2,
PyYAML 6.0.3. Dependências fixadas em `requirements-experiments.lock`.

Comandos executados na raiz. As entradas foram definidas/registradas nas chamadas
antes da comparação. `python` dos testes é sempre o da `.venv` do projeto.

```powershell
# Preparação realizada; instalação inicialmente bloqueada por socket WinError 10013.
# A repetição com download autorizado dos pacotes públicos passou.
.venv/Scripts/python.exe -m venv --system-site-packages tmp/e12a-runtime
tmp/e12a-runtime/Scripts/python.exe -m pip install --disable-pip-version-check --no-cache-dir rapidocr-onnxruntime==1.4.4 scipy==1.15.3
# Para reproduzir as versões efetivas registradas, usar requirements-experiments.lock.

# Original E10, com código c85bebe isolado e SQLite temporário novo:
git archive --format=zip --output=tmp/rede-1256407599/e12a/original-c85bebe.zip c85bebe src scripts
.venv/Scripts/python.exe -m zipfile -e tmp/rede-1256407599/e12a/original-c85bebe.zip tmp/rede-1256407599/e12a/original
.venv/Scripts/python.exe -c "import sys,runpy; from pathlib import Path; root=Path.cwd(); archive=root/'tmp/rede-1256407599/e12a/original'; sys.path[:0]=[str(archive),str(archive/'src')]; sys.argv=['benchmark',str(root/'examples/PROJETO DE REDE 1256407599.pdf'),'--output',str(root/'tmp/rede-1256407599/e12a/original.json'),'--runtime-directory',str(root/'tmp/e01/runtime'),'--telemetry']; runpy.run_module('scripts.benchmark_network_pdf',run_name='__main__')"

# Vertical atual, medido depois do original:
.venv/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e12a/vertical.json --runtime-directory tmp/e01/runtime --telemetry

# Modelos opcionais somente no runtime experimental; libs do projeto preservadas:
$env:PYTHONPATH = "$((Get-Location).Path)\src;$((Get-Location).Path)\.venv\Lib\site-packages"
tmp/e12a-runtime/Scripts/python.exe -m scripts.benchmark_network_alternatives ocr 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e12a/rapid.json --runtime-directory tmp/e01/runtime
.venv/Scripts/python.exe -m scripts.experiments.interpret_rapid --snapshot tmp/rede-1256407599/e12a/vertical.json --readings tmp/rede-1256407599/e12a/rapid.json --output tmp/rede-1256407599/e12a/rapid-semantic.json
.venv/Scripts/python.exe -m scripts.benchmark_network_alternatives graph tmp/rede-1256407599/e12a/vertical.json --output tmp/rede-1256407599/e12a/graph.json
.venv/Scripts/python.exe -m scripts.experiments.compare --runs tmp/rede-1256407599/e12a --reference tmp/rede-1256407599/e10/inventory.json --output tmp/rede-1256407599/e12a/comparison.json
.venv/Scripts/python.exe tmp/rede-1256407599/e12a/audit.py
```

O arquivo original E10 está na versão 1.14.0/22.0; o baseline E11 de E12 continua
preservado em sua pasta. Não se comparou só contra o baseline intermediário E11.
Original/vertical executaram seus pipelines isolados até DTO/XLSX, sem cache.
Não houve execução concorrente de outro benchmark durante essas duas medições.
R executa OCR e interpretação sem promoção; G reutiliza os insumos verticais.
Seus tempos têm escopos diferentes e **não são ranking**:
original até regiões/vãos 124,648 s; com exportação 127,629 s; vertical 167,464 s
e 171,934 s; OCR neural das 24 regiões 76,564 s. Não há teto de cinco minutos.
Progresso/JSON parcial são gravados por tile; exceção ou interrupção deixa
`completed=false`, saída não aceita. Cancelamento é entre chamadas, não imediato
dentro de uma inferência ONNX. Não há recuperação automática de tile interrompido.

## Comparação executada

O comparador conserva 139 linhas com referência, candidatos e geometria/IDs.
No núcleo, pareia propostas uma a uma por classe e geometria do rótulo, antes de
avaliar código/qualificador, situação e ponto/traçado. Normaliza apenas espaços e
caixa; não corrige dígitos, acentos ou pontuação. Saída errada associada conta FP e
FN; omissão/abstenção conta FN. Denominador zero de precisão resulta `null`.
Equipamentos, revisões e código cortado são estratos separados, retidos nos snapshots.

| Método | Poste TP/FN/FP | MT TP/FN/FP | BT TP/FN/FP | Cabo TP/FN/FP | Precisão núcleo | Recall núcleo |
|---|---|---|---|---|---:|---:|
| Original | 5/1/1 | 5/1/1 | 5/1/1 | 9/2/1 | 24/28 = 85,71% | 24/29 = 82,76% |
| Vertical | 5/1/1 | 5/1/1 | 5/1/1 | 9/2/1 | 24/28 = 85,71% | 24/29 = 82,76% |
| R + interpretador atual | 3/3/2 | 1/5/3 | 1/5/2 | 2/9/1 | 7/15 = 46,67% | 7/29 = 24,14% |
| G sobre vertical | 5/1/0 | 5/1/1 | 5/1/1 | 3/8/1 | 18/21 = 85,71% | 18/29 = 62,07% |

As classes e taxas individuais estão em `comparison.json/operational/*/classes`.
Código, situação e associação têm resultados booleanos **separados por item**;
a coluna TP exige todos. Para G, localização física não certifica o nome P nem
topologia completa. Associação de cabo é conferida contra a geometria vertical;
esta dependência é explicitada e a topologia também é comparada à referência abaixo.

Cobertura de candidatos textuais literais, **não TP de ativo**: original/vertical
29/29; R 21/29 (poste 6/6, MT 6/6, BT 4/6, cabo 5/11). Leituras agregadas podem
conter dois códigos; esses localizadores não medem precisão global do OCR nem
certificam 64 campos documentais. Todas as 328 leituras R permanecem disponíveis,
inclusive repetições entre tiles/camadas e textos errados. R não tem confiança
operacional própria; a situação vem do interpretador e foi avaliada separadamente.

| Escopo geométrico/topológico | Original | Vertical | R | G |
|---|---:|---:|---:|---:|
| Pares com ambos endpoints localizados / 7 | 7 | 7 | 4 | 4 |
| Geometria + nomes P corretos onde presentes / 7 | 4 | 4 | 3 | 1 |
| Medidas corretas no traçado / 6 | 6 | 6 | 4 | 4 |
| Continuidades fora da folha explicitamente tipadas / 3 | 0 | 0 | 0 | 0 |

Nomes corretos onde presentes não comprovam identidade compartilhada dos suportes
sem nome. G produziu 33 nós geométricos e cinco arestas suportadas, não nove pontos
físicos validados; há extremidades duplicadas de condutores e nós documentais.
Nenhum desses números demonstra topologia integral. Comprimento desconhecido não
é preenchido. Medidas nas propostas também não garantem presença na tabela Vãos:
original/vertical mantêm as perdas de projeção de 36/83 m documentadas em E10.

### Ganhos, perdas, erros correlacionados e negativos

- **G:** A06/A12/A18, no suporte sem identificador U1, deixam de receber P5 e
  localizam o nó físico correto. Em contrapartida, A10/A15 passam ao endpoint
  errado e A03 fica sem associação. Empates/perdas de cabos reduzem cobertura.
- **R:** recupera integralmente `doc-delivery-coordinate`, ausente como literal
  integral no vertical. ROI inspecionada em `coordinate-inspection.png`; nenhum
  valor pessoal foi copiado para fixtures/docs públicas. Saída candidata ganha
  evidência, sem homologar a projeção documental ou a classe de ponto de entrega.
- **R:** perde A16/A17 e seis rótulos de cabos no localizador. Nem leitura parcial,
  alto score neural, nem mais leituras da aparência são contados como acerto.
- Erro conjunto operacional por ocorrência: seis corretas nos quatro métodos;
  nove falham só em R; oito em R/G; três em original/vertical/R (corrigidas por G);
  uma só em G; duas falham nos quatro. As duas comuns são os neutros existentes
  ainda omitidos pelo interpretador. Matriz integral em `operational_failure_patterns`.
- Sete controles de imagem executados com **ambos motores reais**: cinco textos
  claros corretos, uma moldura vazia sem texto (negativo correto), um código riscado
  incorreto. Resultado de literal inteiro: **6/7 em cada motor**. No riscado,
  Tesseract omite o texto e R acrescenta caractere: erro de ambos, sem consenso.
- Cerca e coordenada da cerca E10 não geram propostas nos três conjuntos semânticos.
  Testes de grafo excluem altura com unidade, contexto sem proposta, cruzamento sem
  junção e mistura entre páginas. Não se gera fato porque o OCR leu um número.
- Erros **conhecidos** nas confirmações de baseline: original 2/10 = 20%
  (revisão não tratada e neutro duplicado); vertical 1/9 = 11,11% (duplicata).
  IDs auditados em `verified-audit.json`. As demais confirmações não foram
  certificadas como integralmente corretas. R/G não promovem: taxa indefinida,
  jamais 100% de precisão por denominador zero.

## Decisão e handoff

1. **Rejeitar R como substituto geral**: pior recall/precisão operacional, perdas
   de BT/cabos, idioma/modelo e integração com consumidores especializados limitados.
   **Encaminhar a E12B como fonte auxiliar candidata**, especialmente para coordenadas
   documentais, preservando polígonos/camada e exigindo avaliação e reconciliação.
   Não aprovar automaticamente um valor porque dois motores concordam.
2. **Rejeitar G para integração direta**: ganho U1 real, mas regressões em P3,
   medidas/traçados e identidades físicas. E14 recebe o solver e os casos sintéticos,
   além dos grafos reais; precisa detectar suportes físicos, tratar condutores
   paralelos e apoiar associação por restrições adicionais. E13 recebe as três
   correções e as novas perdas como exemplos de associação, sem regra promovida.
3. **Manter todas as divergências** para E12B: original/vertical/R, por item;
   saídas com/sem anotações permanecem distintas. Revisões R01/R02 continuam
   pendentes de decisão técnica. Nenhum catálogo foi completado por inferência.
4. Não experimentar H01/H02/H03 para consertar as perdas. Congelar novos métodos
   antes da avaliação reservada E15. Leitura integral permanece **0/1**; E08/E09
   continuam nos estados anteriores e E12B/E13/E14/E15 não foram executadas.

## Validações e evidências

Fechamento aprovado: **106 testes em 11,49 s**, Ruff e formatação (sete arquivos)
aprovados; Mypy em **346 arquivos** sem erros; auditoria real e `git diff --check`
aprovados. **E12A concluída** no escopo de experimentação, com as rejeições acima.

Testes sintéticos cobrem atribuição global versus gulosa, empate/abstenção,
enumeração exaustiva, continuidade de identidade entre arestas, cruzamentos,
separação por página, medida versus altura, contexto vazio, transformação inversa
de polígonos, limites de memória/stride, códigos exatos sem completar sufixo,
interpretação da base sem promoção da aparência e rejeição de OCR incompleto.

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_network_pdf.py tests/unit/test_pymupdf_analyzer.py tests/unit/test_rule_based_interpreter.py tests/unit/test_network_alternatives.py -q -p no:cacheprovider --basetemp tmp/e12a-required-close
.venv/Scripts/python.exe -m ruff check scripts/experiments scripts/benchmark_network_alternatives.py tests/unit/test_network_alternatives.py
.venv/Scripts/python.exe -m ruff format --check scripts/experiments scripts/benchmark_network_alternatives.py tests/unit/test_network_alternatives.py
.venv/Scripts/python.exe -m mypy src tests scripts/experiments scripts/benchmark_network_alternatives.py --cache-dir tmp/e12a-mypy-full
git diff --check
```

Logs em `tmp/rede-1256407599/e12a/`: baselines original/vertical, `rapid.json`,
`rapid-semantic.json`, `graph.json`, `comparison.json`, `verified-audit.json`,
`machine-and-oracle.json`, testes e tipagem. Relatórios contêm dados privados.
O manifesto final registra hashes dos insumos, scripts e artefatos.

Falhas intermediárias resolvidas: instalação bloqueada pela rede; construtor do
interpretador inicialmente sem registro; importação do script privado sem raiz;
tipagem de variáveis reutilizadas e resolução Mypy fora do comando completo;
formatação. O controle riscado **continua sendo erro dos candidatos**, não falha
ocultada de validação. Não houve corte de execução para atender tempo.
Gate integral/UI/SQL não repetidos: E12A exige a suíte direcionada e os experimentos;
nenhuma mudança de produção exige nova homologação integral nesta etapa.

Sem commit, publicação, consulta SQL operacional, instalação em produção ou edição do PDF.
