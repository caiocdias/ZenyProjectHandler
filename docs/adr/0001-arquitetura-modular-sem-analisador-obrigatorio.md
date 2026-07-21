# ADR 0001 - Arquitetura modular sem analisador proprietário obrigatório

- Estado: aceito
- Data: 2026-07-20

## Contexto

O aplicativo deverá interpretar documentos PDF e produzir propostas de elementos e relações da rede elétrica. A tecnologia adequada para essa interpretação ainda dependerá da qualidade dos PDFs reais, das informações vetoriais disponíveis e de benchmarks posteriores.

Vincular o domínio ou a interface a um mecanismo específico criaria dependências prematuras de licença, hardware, formato de saída e ciclo de atualização.

## Decisão

O domínio, os casos de uso e a interface não conhecerão bibliotecas ou motores concretos de análise. A aplicação definirá portas próprias e adaptadores substituíveis.

A primeira implementação deverá priorizar informações nativas do PDF, processamento local e regras explícitas. Resultados automáticos serão armazenados como propostas auditáveis e somente entrarão no modelo confirmado após revisão humana.

Nenhum serviço externo ou motor de aprendizado de máquina será adicionado sem nova decisão arquitetural que avalie licença, privacidade, desempenho, qualidade e manutenção.

## Consequências

- Testes comuns serão determinísticos, locais e independentes de serviços externos.
- Novos analisadores poderão ser avaliados sem alterar o domínio.
- A aplicação continuará funcional para revisão manual quando um analisador estiver ausente.
- Haverá custo inicial para definir contratos, proveniência e adaptadores, reduzindo acoplamento nas etapas posteriores.
