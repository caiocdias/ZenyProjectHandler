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
- O treino roda fora do servidor, na máquina do usuário (GPU AMD, PyTorch com ROCm, a confirmar por
  spike), com lock próprio e opt-in. Dados, rótulos e pesos ficam fora do Git; os pesos são artefato
  de release com SHA-256.
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
