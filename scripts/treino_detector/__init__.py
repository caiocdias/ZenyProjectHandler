"""Spike E11: ensaio de treino de um detector visual local, fora do produto.

Nada aqui entra no runtime do servidor ou do cliente: o código serve só para
medir viabilidade de treino (dados sintéticos, métricas e paridade numérica) e
não pode ser importado por `src/`. A decisão e os números estão no ADR 0017,
seção "Caminho de treino (E11)".

Módulos: `dados_sinteticos` e `metricas` (puros), `ambiente` (sonda), `decisao`
(regra de escolha do caminho, pura) e `ensaio` (torch/onnx; nunca importado por
testes nem por `src/`).

Como rodar, da raiz do repositório, em série e sem outro processo pesado, com as
saídas em `tmp/treino-e11/` (fora do Git). O venv ROCm sai de
`requirements-treino.lock` (ver o cabeçalho do lock); o venv CPU usa os wheels
`+cpu` de torch/torchvision com os mesmos onnx e onnxruntime:

    set ROCM=tmp\\treino-e11\\venv-rocm\\Scripts\\python.exe
    set CPU=tmp\\treino-e11\\venv-cpu\\Scripts\\python.exe
    %ROCM% -m scripts.treino_detector.ambiente --saida tmp/treino-e11/ambiente-rocm.json
    %ROCM% -m scripts.treino_detector.ensaio paridade --saida tmp/treino-e11/paridade-treino
    %ROCM% -m scripts.treino_detector.ensaio treino --dispositivo cuda --minutos-max 30 ^
        --paridade-treino tmp/treino-e11/paridade-treino/relatorio.json ^
        --saida tmp/treino-e11/ensaio-cuda
    %CPU% -m scripts.treino_detector.ensaio treino --dispositivo cpu --epocas 3 ^
        --minutos-max 15 --saida tmp/treino-e11/ensaio-cpu
    .venv\\Scripts\\python.exe -m scripts.treino_detector.decisao ^
        --rocm tmp/treino-e11/ensaio-cuda/relatorio.json ^
        --cpu tmp/treino-e11/ensaio-cpu/relatorio.json --saida tmp/treino-e11/decisao.json

O ensaio WSL2 só entra com `--wsl2 RELATORIO` quando houver relatório; sem ele,
`--motivo-wsl2 TEXTO` registra por que não foi ensaiado.
"""
