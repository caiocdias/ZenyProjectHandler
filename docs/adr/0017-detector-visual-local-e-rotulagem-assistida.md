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

Medição numa só máquina, em série, com a 1ª medição CPU (torch 2.9.1) sem outro processo pesado;
o reensaio com o lock final rodou sob carga externa (ver abaixo), e os ensaios na GPU falharam no
primeiro lote, sem medida de tempo: Intel Core
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
  lock e o da variante ROCm medida, que continua no torch 2.9.1 (único release oficial da AMD para
  Windows).
- `torch` 2.9.1 tem 4 vulnerabilidades publicadas (osv-scanner 2.7.0, único pacote afetado do lock
  ROCm de 22 pacotes): PYSEC-2026-139 (CVSS 7,8, carregamento de `.pt2`, sem correção listada),
  PYSEC-2026-2286 / GHSA-63cw-57p8-fm3p (8,8, desvio do unpickler `weights_only`, corrigida na
  2.10.0), GHSA-qfhq-4f3w-5fph (5,3, `torch.lstm_cell`, 2.10.0) e GHSA-rrmf-rvhw-rf47 (5,3,
  `torch.jit.script`, 2.13.0). Todas exigem carregar arquivo de modelo ou entrada hostil ou usar as
  funções citadas. Mitigação, válida para qualquer versão: no ambiente de treino nunca se carrega
  `.pt`, `.pt2` ou pickle de terceiros, só pesos próprios; o artefato que sai é o ONNX; não se aplica
  `torch.jit.script` a código ou modelo de terceiros. Gatilho para o ROCm: só voltar quando a AMD
  publicar release para Windows com torch ≥ 2.13 e o defeito do MIOpen corrigido (hoje, torch ≥ 2.13
  com ROCm só existe como pré-release no nightly TheRock, que o spike não usa).
- Ao reconstruir o ambiente ROCm: o pacote `rocm==7.2.1` é um sdist; no build isolado o pip baixa
  `setuptools>=70.2.0` do PyPI sem verificar hash (limite do modo hash do pip). Alternativa
  hermética: instalar com `--no-index --find-links` apontando para uma cópia local dos wheels.
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
reconstruído pelos 22 pinos com hash do apêndice "Pinos da variante ROCm medida (E11)", quando a
AMD corrigir o defeito. Os comandos, em série, estão no docstring de
`scripts/treino_detector/__init__.py`. As saídas ficam em `tmp/treino-e11/`, fora do Git.

## Apêndice: pinos da variante ROCm medida (E11)

Conteúdo de `requirements-treino.lock` na variante ROCm ensaiada (commit 1693569), para
reconstruir o ambiente num venv próprio quando a AMD corrigir o defeito do MIOpen
(`pip install -r` de um arquivo com este bloco, fora do Git):

```text
# Python exigido: 3.12 (os wheels ROCm para Windows só existem em cp312), Windows x64.
--find-links https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1/
filelock==4.2.9 \
    --hash=sha256:a379c50a729e5b68c8519a4d26489f755d9769960a236ecd838190e2a78db2e9
flatbuffers==25.12.19 \
    --hash=sha256:7634f50c427838bb021c2d66a3d1168e9d199b0607e6329399f04846d42e20b4
fsspec==2026.9.0 \
    --hash=sha256:8dd6e646e99ea382bd85f97a45e6b526a442d79423a7dc673f1e2756d05fcb5f
Jinja2==3.1.6 \
    --hash=sha256:85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67
MarkupSafe==3.0.4 \
    --hash=sha256:11935df9bf455ed0c04eb87bcd720f02b1fe5e02128a9430f23aed6f93336fc7
ml_dtypes==0.6.0 \
    --hash=sha256:2a3e9d53925597fbffafd2a37048dadeddd0bdaba58058f6ae0869ed709a184d
mpmath==1.3.0 \
    --hash=sha256:a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c
networkx==3.7 \
    --hash=sha256:e3fd2c13a7814cee3746340d8d7f8598a67f16a58bf47fb7f8793fab6efca1b0
numpy==2.5.4 \
    --hash=sha256:a7b1b6353e36a7e50de2973a38d705c88ee93adcf120673cee7f45a4a3fa223a
onnx==1.23.2 \
    --hash=sha256:9b382ba898a7c142a0801d03cf04ecabced96c1543c7b643a86f0928143802de
onnxruntime==1.31.1 \
    --hash=sha256:ae8a9a351efda685cc59a66226cdefaa37a126c1d66872ca23a2de9425326130
packaging==26.3 \
    --hash=sha256:d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c
Pillow==13.0.0 \
    --hash=sha256:ff3fe9eb621fbb9db4c4be33ab946f6bac5f98ab50ca8d3260503653656c961b
protobuf==7.36.2 \
    --hash=sha256:a300819d441e078a5608c0d3c709796bb548136058fda017ae51d425b44fd353
rocm==7.2.1 \
    --hash=sha256:9084902eaa69213a00a90784ad89e6e5fe73c702df0cc6cc3a70d777c7a6142b
rocm-sdk-core==7.2.1 \
    --hash=sha256:f68989d48df71cbfc3cb68bf705dc37c0f56e9666feddb59a1a0f5ff7539fe1c
rocm-sdk-libraries-custom==7.2.1 \
    --hash=sha256:c7fe0b0731af8896093ff69e11496830d3cb6a4aed73e895c60b7cbdc200be92
setuptools==84.1.0 \
    --hash=sha256:5231689c6ac8156cd155cfb98c3fd6fb252c3e7e9bd3d78b64d3c55f132624c9
sympy==1.14.0 \
    --hash=sha256:e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5
torch==2.9.1+rocm7.2.1 \
    --hash=sha256:e88bf270163b48f7f27f7ea3db5ffb3be4ba107301933022bcb3c6ddedfeeabb
torchvision==0.24.1+rocm7.2.1 \
    --hash=sha256:b5c34d76a2f01fb97e1e0f224bd97fc3a58ec1ee1ef2376af2d72086e9aca34c
typing_extensions==4.16.0 \
    --hash=sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8
```
