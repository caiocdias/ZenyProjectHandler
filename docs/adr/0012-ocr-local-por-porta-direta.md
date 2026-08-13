# ADR 0012 - OCR local por porta direta, sem MCP no pipeline

## Status

Aceita em 23/07/2026. A adoção do Unlimited-OCR permanece experimental e condicionada a benchmark.

## Contexto

O scanner já recebe `PaginaRasterOcr` por `MotorOcrPort` e espera trechos de texto com caixa
normalizada. O Tesseract atende esse contrato localmente. Foi avaliado usar o
`baidu/Unlimited-OCR` no LM Studio e acessá-lo por MCP.

O Unlimited-OCR é um modelo visual de 3 bilhões de parâmetros, BF16 e com código customizado. A
distribuição oficial documenta Transformers em GPU NVIDIA, vLLM e SGLang; o exemplo de servidor usa
uma API compatível com OpenAI e parâmetros próprios para processamento de imagem e supressão de
repetição. Existem quantizações de terceiros anunciadas para llama.cpp/LM Studio, mas isso não
equivale a suporte ou paridade oficial.

O LM Studio pode servir modelos locais, aceitar imagens e integrar servidores MCP a uma conversa. O
MCP, porém, é o caminho para um modelo chamar ferramentas. Ele não acrescenta valor entre o scanner
determinístico e um serviço OCR e introduziria protocolo, orquestração e outra camada de falha.

## Decisão

- Não integrar Unlimited-OCR por LM Studio + MCP no pipeline principal.
- Manter `MotorOcrPort` como fronteira do aplicativo e o Tesseract como implementação funcional
  atual.
- Se o Unlimited-OCR for testado, criar um adaptador opcional que chame diretamente um endpoint
  local compatível com OpenAI exposto por vLLM ou SGLang, com `temperature = 0`, timeout, cancelamento
  e registro da versão do modelo.
- Não enviar documentos pela rede e desabilitar uso de proxy no cliente local.
- Converter a resposta de parsing para trechos e caixas normalizadas; quando a saída não fornecer
  geometria confiável, usá-la somente como evidência textual de página ou como segunda passagem para
  cabeçalhos e layouts difíceis.
- Manter fallback e comparação com texto nativo e Tesseract. O modelo só poderá substituir uma etapa
  depois de avaliação local reproduzível e regressões sintéticas para os campos críticos.
- Usar MCP apenas se, no futuro, o OCR for deliberadamente exposto como ferramenta para um agente,
  fora do caminho determinístico de extração.

## Critérios do experimento

O benchmark deve medir separadamente:

- caracteres, palavras e campos críticos corretos;
- recall de NS, escala, formato, vãos, ângulos e rótulos de assinatura;
- qualidade das caixas e navegação até a evidência;
- alucinações, omissões e repetição em plantas densas;
- desempenho por página, pico de VRAM/RAM e tempo de inicialização;
- estabilidade em recortes, página inteira e múltiplas páginas;
- operação offline, licença e reprodutibilidade da versão/quantização.

Os PDFs locais podem revelar lacunas, mas não devem fixar sozinhos prompt, limiar ou seleção de
modelo. Casos decisivos precisam de uma referência revisável ou fixture sintética.

## Consequências

A arquitetura não fica acoplada ao LM Studio e pode testar o servidor oficialmente documentado pelo
modelo. Perde-se a conveniência de uma única interface gráfica para modelos, mas reduz-se a
ambiguidade de compatibilidade e preserva-se o contrato espacial exigido pelo aplicativo. Até o
benchmark, Unlimited-OCR é complemento possível, não dependência nem fonte canônica.

Fontes:

- [repositório oficial do Unlimited-OCR](https://github.com/baidu/Unlimited-OCR);
- [modelo oficial no Hugging Face](https://huggingface.co/baidu/Unlimited-OCR);
- [servidor local do LM Studio](https://lmstudio.ai/docs/developer/core/server);
- [API de chat do LM Studio com imagens e integração MCP](https://lmstudio.ai/docs/developer/rest/chat).
