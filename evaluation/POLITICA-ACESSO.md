# Política de acesso ao corpus de avaliação

1. PDFs reais permanecem somente em armazenamento local ou repositório privado autorizado.
2. Nomes originais, dados cadastrais, telefones, coordenadas, fotografias e conteúdo textual não são
   copiados para Git, logs ou relatórios de benchmark.
3. Identificadores de amostra são anônimos. O pareamento local é feito por SHA-256.
4. Anotadores e revisores usam identificadores pseudônimos; o vínculo com pessoas fica fora do
   conjunto de avaliação.
5. Anotações reais e miniaturas de revisão são material controlado e não devem ser publicadas.
6. A partição `TESTE` só pode ser acessada para execução final, nunca para criar ou ajustar regras.
7. Relatórios publicáveis contêm somente IDs anônimos, contagens, métricas e versões.
8. Inclusão, substituição ou reclassificação de amostra altera a versão e invalida o congelamento.
9. O gate básico exclui `private_samples` explicitamente e nunca acessa os PDFs reais. O gate
   privado é opt-in, roda apenas em ambiente autorizado e deve falhar se uma amostra requerida
   estiver ausente, ilegível, incompleta ou com SHA-256 divergente; ausência não pode virar `skip`.
10. Testes que acessam o corpus devem ficar em `tests/private_samples/`, declarar o marcador
    `private_samples` e emitir somente IDs anônimos e contagens em falhas e relatórios.
