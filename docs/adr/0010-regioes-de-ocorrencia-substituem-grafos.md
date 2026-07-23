# ADR 0010 - Regiões de ocorrência substituem grafos

## Status

Aceita em 2026-07-22. Substitui a ADR 0007.

## Contexto

A projeção em grafo exigia que o usuário interpretasse nós, arestas e diagnósticos para compreender
uma informação que já está localizada no desenho. Nos projetos reais, uma ocorrência relevante pode
conter simultaneamente um poste retirado, outro instalado, estruturas, equipamentos, cabos e uma
coordenada. O poste nem sempre está catalogado e, portanto, não pode ser o item-pai obrigatório.

## Decisão

- Remover a construção, a interface, a porta, o adaptador NetworkX e os artefatos portáteis de grafo.
- Derivar `RegiaoAnalise` diretamente das geometrias das propostas na mesma página.
- Manter `PropostaRelacao` como vínculo semântico auditável, exibido dentro da região, sem
  transformá-lo em aresta.
- Associar coordenadas UTM obtidas de texto nativo ou OCR à região mais próxima. Leste e norte podem
  estar no mesmo fragmento ou separados por quebra de linha, `:`, `/` ou fragmentos próximos.
- Ordenar regiões pela ordem persistida dos PDFs, página e posição na folha.
- Preservar o sublinhado clicável de cada elemento e permitir que o clique navegue para a página
  correta.

## Consequências

O painel passa a responder diretamente “onde” e “o que acontece” em cada local. Uma região continua
útil sem coordenada ou poste reconhecido e pode reunir situações `EXISTENTE`, `INSTALAR` e `REMOVER`.
Pacotes novos ficam menores e deixam de reconstruir uma projeção durante exportação e importação.

A identidade da região é derivada dos IDs da página e dos elementos; por isso ela não é persistida
como nova fonte de verdade. Alterar resultados ou geometrias recalcula naturalmente os agrupamentos.
