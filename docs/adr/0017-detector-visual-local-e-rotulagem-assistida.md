# ADR 0017 - Detector visual local e rotulagem assistida por IA

- Estado: aceito
- Data: 2026-10-30
- Substitui parcialmente: ADR 0001 (proibição de aprendizado de máquina)
- Design: `docs/superpowers/specs/2026-10-30-leitura-vetorial-por-poste-design.md`

## Contexto

Parte dos símbolos pode não ser resolvida pela geometria vetorial (ADR 0016). Chegam cerca de 50
folhas por mês. O usuário autorizou enviar as folhas à Anthropic para rotulagem (LGPD e contrato).

## Decisão

- Um detector treinado roda localmente, em CPU, via ONNX Runtime, só onde o vetor não resolveu. Ele
  entra como evidência com confiança, e o hash dos pesos entra na assinatura do analisador.
- Modelo e código de treino com licença Apache-2.0, BSD ou MIT. YOLO Ultralytics (AGPL) está
  excluído.
- O treino roda fora do servidor, na máquina do usuário, no caminho medido na seção "Caminho de
  treino (E11)", com lock próprio e opt-in. Dados, rótulos e pesos ficam fora do Git; os pesos são
  artefato de release com SHA-256.
- O Claude rotula, não analisa em produção. O conjunto de treino usa pré-marcação vetorial, leitura
  dupla e amostra humana de cerca de 5 folhas em 50. O conjunto de avaliação é de folhas novas,
  separado por folha, lido às cegas, congelado e nunca usado no treino. Os rótulos podem alimentar o
  treino, o que revisa o invariante correspondente do contrato de curadoria.

## Alternativas descartadas

- Claude no servidor a cada análise: custo por folha, resultado não determinístico e serviço externo
  em produção.
- Treinar antes de medir o vetor: com 16 folhas não há volume para treinar, e a maior parte do erro
  é resolvida pelo vetor.

## Consequências

Entra uma dependência de inferência no servidor e um ciclo de dados contínuo. A qualidade do detector
fica limitada pela taxa de erro medida dos rótulos.

## Caminho de treino (E11)

Spike de 2026-11-05. Escolhido: **CPU**, pela regra fixa de
`scripts/treino_detector/decisao.py` aplicada aos relatórios dos ensaios (motivo registrado no
reensaio com o lock final: "paridade ONNX ok; 15.8 img/s; 10.5 h na carga de referência; qualidade
confirmada"). O
treino roda na CPU com PyTorch e exporta ONNX; a GPU AMD fica fora até o defeito abaixo ser
corrigido numa release oficial.

Medição numa só máquina, em série, com a medição da CPU sem outro processo pesado (os ensaios na
GPU falharam no primeiro lote, sem medida de tempo): Intel Core
i7-12700KF (12 núcleos, 20 threads; `os.cpu_count()` = 20, `torch.get_num_threads()` = 12), 63,8 GB
de RAM, AMD Radeon RX 9070 XT (gfx1201), Windows 11 Home 10.0.26300, driver AMD Adrenalin
26.20.15.07 (DriverVersion 32.0.32015.7029). Versões: ambiente ROCm com Python 3.12.10, torch
2.9.1+rocm7.2.1, torchvision 0.24.1+rocm7.2.1, HIP 7.2.53211-158bd99533, wheels do índice de
release oficial da AMD (`repo.radeon.com/rocm/windows/rocm-rel-7.2.1/`, não o nightly); ambiente CPU
com Python 3.11.9, torch 2.14.1+cpu e torchvision 0.29.2+cpu (lock final; a primeira medição usou
torch 2.9.1+cpu e torchvision 0.24.1+cpu); ambos com onnx 1.23.2 e onnxruntime 1.31.1. Modelo
`ssdlite320_mobilenet_v3_large` (torchvision, BSD-3) sem pesos pré-treinados, 5 classes (4 símbolos
sintéticos + fundo), SGD (lr 0,01 com aquecimento linear nos 100 primeiros lotes, momentum 0,9,
weight decay 4e-5), lote 16, ladrilhos sintéticos de 320 px.

| Medida | GPU ROCm nativo | CPU (torch 2.14.1, lock final) |
| --- | --- | --- |
| Vazão de treino (img/s, sem os 10 lotes de aquecimento) | sem medida: erro no 1º lote | 15,8 (22,3 com torch 2.9.1, sem carga) |
| Aquecimento (10 primeiros lotes) | — | 8,2 s |
| Segundos por época (2000 ladrilhos) | — | 109,1 / 163,9 / 104,6 |
| Paridade de treino na 1ª iteração (tolerância 1e-3) | sem resultado: erro no 1º passo na GPU | não se aplica |
| Qualidade após o ensaio (precisão / recall) | — | 0,99 / 0,90 (3 épocas) |
| Exportação ONNX (opset 18) | não alcançada | ok, TorchScript (`dynamo=False`) em 1,0 s; o exportador dynamo falhou por falta de `onnxscript`, fora do lock |
| Paridade ONNX × PyTorch CPU (20 imagens) | não alcançada | ok, 0 divergentes, 48 detecções de referência com score ≥ 0,25 |
| ONNX Runtime CPU por ladrilho de 320 px (100 execuções, 12 threads intra-op) | — | mediana 5,0 ms, p95 6,6 ms |
| Estimativa por folha A1 (teto, 875 ladrilhos) | — | 4,4 s contra 60 s da E12 |
| Carga de referência (20 000 ladrilhos × 30 épocas) | — | 10,5 h (7,5 h a 22,3 img/s) |

O reensaio com o lock final coincidiu com uma suíte e2e de outra sessão rodando em laço; a época 1
levou 163,9 s contra cerca de 105 s das outras. Por isso, 15,8 img/s é um limite pessimista. A
medição sem carga, com torch 2.9.1, deu 22,3 img/s (épocas de 92,8, 89,4 e 87,4 s; ONNX Runtime com
mediana de 4,4 ms). Com qualquer dos dois números, a CPU fica abaixo de 12 h.

Premissas da regra (não são especificação; mudam com o conjunto real):

- Carga de referência: 20 000 ladrilhos × 30 épocas (ordem de grandeza de um conjunto de ~50 folhas
  rotuladas com aumento de dados); `horas = 20 000 × 30 ÷ vazão ÷ 3600`.
- Limite de 12 h: um treino cabe numa noite.
- Razão mínima de 3× entre GPU e CPU para justificar o caminho GPU quando ele passa de 12 h.
- Folha A1 a 300 dpi = 9933 × 7016 px = 875 ladrilhos de 320 px com 10% de sobreposição. A
  estimativa por folha é um teto (todos os ladrilhos; a E12 só atua no resíduo do vetor) e foi
  medida nesta máquina, não no container do servidor; o orçamento da E12 é de 60 s por folha.
- A vazão exclui os 10 primeiros lotes (aquecimento, inclui compilação de kernels) e é medida em
  lotes completos depois deles. A qualidade (recall e precisão ≥ 0,80 a IoU 0,5 e score 0,5) só
  confirma que a cadeia aprende; não reprova caminho.

Alternativas descartadas:

- GPU AMD com ROCm nativo no Windows: ensaiada e inviável. O primeiro passo de treino na GPU falha
  com `RuntimeError: miopenStatusUnknownError` no `batch_norm` em modo treino, tanto na paridade de
  treino quanto no ensaio, e não há vazão medida. Causa isolada: o MIOpen compila o kernel
  `MIOpenBatchNormFwdTrainSpatialHIP.cpp` em tempo de execução (hipRTC/comgr) e a compilação para
  gfx1201 falha com `fatal error: 'type_traits' file not found`. Convolução com MIOpen e BatchNorm
  de treino com o MIOpen desligado (`torch.backends.cudnn.enabled = False`) rodam. Depois do erro, o
  processo trava no encerramento, dentro do driver, e precisa ser finalizado à força. Contornos (MIOpen
  desligado só no BatchNorm, normalização sem BatchNorm, wheels nightly do TheRock) não foram
  ensaiados. Reavaliar quando a AMD publicar release para Windows com o defeito corrigido.
- GPU AMD com ROCm no WSL2: não ensaiada. A sonda não rodou (o harness recusou `wsl.exe`), e instalar
  distro ou pacotes no WSL exige decisão do usuário.
- GPU alugada (D1): desnecessária, porque a CPU cumpre o limite de 12 h.

Riscos aceitos:

- O lock CPU final (torch 2.14.1+cpu, torchvision 0.29.2+cpu, 19 pacotes) sai limpo no osv-scanner
  2.7.0 ("No issues found"). As vulnerabilidades abaixo são do torch 2.9.1, o da primeira versão do
  lock e o da variante ROCm medida, que segue nele (único release oficial da AMD para Windows).
- `torch` 2.9.1 tem 4 vulnerabilidades publicadas (osv-scanner 2.7.0, único pacote afetado do lock
  ROCm de 22 pacotes): PYSEC-2026-139 (CVSS 7,8, carregamento de `.pt2`, sem correção listada),
  PYSEC-2026-2286 / GHSA-63cw-57p8-fm3p (8,8, desvio do unpickler `weights_only`, corrigida na
  2.10.0), GHSA-qfhq-4f3w-5fph (5,3, `torch.lstm_cell`, 2.10.0) e GHSA-rrmf-rvhw-rf47 (5,3,
  `torch.jit.script`, 2.13.0). Todas exigem carregar arquivo de modelo ou entrada hostil ou usar as
  funções citadas. Mitigação, válida para qualquer versão: no ambiente de treino nunca se carrega
  `.pt`, `.pt2` ou pickle de terceiros, só pesos próprios; o artefato que sai é o ONNX; o exportador
  usado é o TorchScript por rastreamento (`torch.jit.trace`), não `torch.jit.script`. Gatilho para o
  ROCm: só voltar quando a AMD publicar release para Windows com torch ≥ 2.13 e o defeito do MIOpen
  corrigido (hoje, torch ≥ 2.13 com ROCm só existe como pré-release no nightly TheRock, que o spike
  não usa).
- O pacote `rocm==7.2.1` é um sdist; no build isolado o pip baixa `setuptools>=70.2.0` do PyPI sem
  verificar hash (limite do modo hash do pip). Alternativa hermética: instalar com
  `--no-index --find-links` apontando para uma cópia local dos wheels.
- Licenças do que o lock de treino instala (inventário feito no ambiente ROCm; o lock CPU tem os
  mesmos pacotes, menos os três `rocm*`): torch 2.9.1 e torchvision BSD-3 (o torch 2.14.1 declara
  Apache-2.0, Apache-2.0 com exceção LLVM, BSD-2, BSD-3, BSL-1.0 e MIT), onnx Apache-2.0, onnxruntime
  MIT, numpy BSD-3 (com partes 0BSD/MIT/Zlib/CC0), Pillow MIT-CMU, protobuf BSD-3, flatbuffers e
  ml_dtypes Apache-2.0, filelock e setuptools MIT, typing_extensions PSF-2.0, packaging Apache-2.0 ou
  BSD-2, jinja2, markupsafe, fsspec, networkx, sympy e mpmath BSD. `rocm`, `rocm-sdk-core` e
  `rocm-sdk-libraries-custom` não declaram licença no METADATA; os textos embutidos são Apache-2.0
  com exceção LLVM (comgr) e MIT (hipcc). A restrição Apache-2.0, BSD ou MIT vale para o modelo e o
  código de treino; as dependências acima são ferramenta do ambiente de treino, que não é
  redistribuído.

Como reproduzir: `requirements-treino.lock` fixa a variante CPU medida (Python 3.11,
`torch==2.14.1+cpu` e `torchvision==0.29.2+cpu` do índice `https://download.pytorch.org/whl/cpu`, demais
pinos do PyPI, todos com hash). O ambiente ROCm ensaiado (Python 3.12, `rocm-rel-7.2.1`) é
reconstruído a partir dos pinos e hashes registrados em `tmp/treino-e11/instalacao.md` quando a AMD
corrigir o defeito. Os comandos, em série, estão no docstring de `scripts/treino_detector/__init__.py`.
As saídas ficam em `tmp/treino-e11/`, fora do Git.
