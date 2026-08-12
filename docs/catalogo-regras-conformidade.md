# Catálogo incremental de regras de conformidade

> Fonte humana e auditável das regras de erro conhecidas pelo analisador. Este catálogo começa com o
> seed atual; a verificação integral das fontes e a expansão normativa pertencem à Etapa 2 de
> `docs/roadmap-analise-conformidades.md`.

## Preceito obrigatório

1. Toda regra incorporada, alterada, desativada, substituída ou removida deve ser atualizada aqui no
   mesmo commit do registro e dos testes.
2. Cada ID técnico recebe um número `Regra N` sequencial e permanente. Números removidos não são
   apagados nem reutilizados.
3. Mudança editorial conserva o número e entra no histórico da regra. Mudança normativa que altera a
   obrigação, a aplicabilidade ou a exceção cria novo ID/número e marca a anterior como substituída.
4. A descrição deve explicar o processo real de análise, não apenas repetir o título da norma.
5. Toda entrada informa fonte, fatos, condições, exceções, conclusão possível, estado de automação e
   testes. Uma citação incompleta não autoriza reprovação automática.
6. Regras importadas pelo usuário em execução aparecem no catálogo Markdown local gerado a partir da
   revisão ativa. Este arquivo versionado documenta as regras distribuídas com o produto.

Estados de automação:

- `OPERACIONAL`: os fatos necessários já são produzidos e a regra pode concluir.
- `PARCIAL`: apenas alguns contextos ou fatos são produzidos; os demais ficam não avaliáveis.
- `AGUARDA_FATO`: a regra existe, mas falta um provedor confiável para ao menos um fato essencial.
- `INATIVA`, `SUBSTITUIDA` ou `REMOVIDA`: preservada somente para histórico/auditoria.

## Resumo

| Número | ID técnico | Título | Registro | Automação |
|---|---|---|---|---|
| Regra 1 | `nd31.desenho.numero-projeto` | Número do projeto com 10 dígitos | ATIVA | OPERACIONAL |
| Regra 2 | `nd31.desenho.formato` | Formato de folha padronizado | ATIVA | OPERACIONAL |
| Regra 3 | `nd31.desenho.escala` | Escala urbana de apresentação | ATIVA | OPERACIONAL |
| Regra 4 | `nd31.equipamento.estrutura-angulo` | Equipamento em estrutura de ângulo | ATIVA | AGUARDA_FATO |
| Regra 5 | `nd31.equipamento.risco-abalroamento` | Avaliação de risco no ângulo | ATIVA | AGUARDA_FATO |
| Regra 6 | `nd31.vao.urbano-compacto-isolado` | Vão máximo urbano | ATIVA | AGUARDA_FATO |

## Regras existentes

### Regra 1 - Número do projeto com 10 dígitos

- **ID:** `nd31.desenho.numero-projeto`
- **Processo de análise:** a Regra 1 consiste em verificar, quando o projeto foi identificado como
  urbano, se existe uma Nota de Serviço válida. O analisador
  procura a Nota de Serviço/número do projeto no metadado confirmado ou no cabeçalho por texto/OCR.
  O domínio e o extrator só aceitam o formato de dez dígitos.
- **Fatos:** `rede.contexto_urbano`; `projeto.nota_servico`.
- **Condição/erro:** se o contexto urbano for conhecido e o número válido não existir, gera possível
  divergência. Sem contexto suficiente, retorna não avaliável.
- **Exceções:** nenhuma registrada.
- **Fonte registrada no seed:** CEMIG ND-3.1, revisão Jul/2025, “Apresentação do Projeto”, item 2.4,
  página 88, [URL registrada](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
  A Etapa 2 deve reconfirmar revisão, item e página na fonte oficial integral.
- **Testes mínimos:** número válido; número ausente; contexto desconhecido.

### Regra 2 - Formato de folha padronizado

- **ID:** `nd31.desenho.formato`
- **Processo de análise:** a Regra 2 consiste em ler, em projeto urbano, o formato informado no
  cabeçalho/metadado e, quando necessário, inferir A1-A4 pelas dimensões físicas da página. Compara
  o valor com o conjunto permitido `A1`, `A2`, `A3` e `A4`.
- **Fatos:** `rede.contexto_urbano`; `projeto.formato_folha`.
- **Condição/erro:** formato conhecido fora do conjunto gera possível divergência; formato ausente ou
  contexto desconhecido gera não avaliável.
- **Exceções:** nenhuma registrada.
- **Fonte registrada no seed:** CEMIG ND-3.1, revisão Jul/2025, “Apresentação do Projeto”, item 2.3,
  página 88, [URL registrada](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
  A Etapa 2 deve reconfirmar a fonte integral.
- **Testes mínimos:** cada formato permitido; formato inválido; dado ausente.

### Regra 3 - Escala urbana de apresentação

- **ID:** `nd31.desenho.escala`
- **Processo de análise:** a Regra 3 consiste em extrair, em projeto urbano, a escala do metadado ou
  cabeçalho e verificar se pertence ao conjunto `1:1000` ou `1:500`.
- **Fatos:** `rede.contexto_urbano`; `projeto.escala`.
- **Condição/erro:** escala conhecida fora do conjunto gera possível divergência; escala ausente ou
  contexto desconhecido gera não avaliável.
- **Exceções:** o texto do seed menciona casos extraordinários, mas nenhuma exceção declarativa está
  implementada. Até a revisão integral, esses casos exigem decisão humana.
- **Fonte registrada no seed:** CEMIG ND-3.1, revisão Jul/2025, “Apresentação do Projeto”, item 2.1,
  página 88, [URL registrada](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
  A Etapa 2 deve reconfirmar condições e exceções na fonte integral.
- **Testes mínimos:** duas escalas aceitas; escala divergente; dado ausente; exceção não presumida.

### Regra 4 - Equipamento em estrutura de ângulo

- **ID:** `nd31.equipamento.estrutura-angulo`
- **Processo de análise:** a Regra 4 consiste em identificar, em cada região, equipamento a instalar
  e sua classe. Para equipamento diferente de chave fusível, precisa calcular o ângulo da conexão e
  verificar se ele é menor ou igual a 30 graus.
- **Fatos:** `regiao.equipamento_instalar`; `regiao.equipamento_classe`;
  `conexao.angulo_graus`.
- **Condição/erro:** equipamento não fusível aplicável com ângulo acima do limite gera possível
  divergência. Sem ângulo confiável, retorna não avaliável.
- **Exceções:** chave fusível fica fora da aplicabilidade registrada.
- **Fonte registrada no seed:** CEMIG ND-3.1, revisão Jul/2025, “Dimensionamento Mecânico”, observação
  j, página 66, [URL registrada](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
  A Etapa 2 deve reconfirmar texto, contexto e página.
- **Automação pendente:** ainda não existe provedor de `conexao.angulo_graus`.
- **Testes mínimos:** chave fusível; equipamento não fusível até/acima do limite; ângulo ausente.

### Regra 5 - Avaliação de risco de abalroamento no ângulo

- **ID:** `nd31.equipamento.risco-abalroamento`
- **Processo de análise:** a Regra 5 consiste em procurar evidência da avaliação de risco para
  equipamento não fusível a instalar com deflexão maior que zero e até 30 graus. O analisador usa
  evidência textual próxima ao equipamento.
- **Fatos:** `regiao.equipamento_instalar`; `regiao.equipamento_classe`;
  `conexao.angulo_graus`; `regiao.risco_abalroamento_avaliado`.
- **Condição/erro:** quando a regra é aplicável e não existe prova da avaliação, gera possível
  divergência. Sem ângulo confiável, retorna não avaliável.
- **Exceções:** chave fusível fica fora da aplicabilidade registrada.
- **Fonte registrada no seed:** CEMIG ND-3.1, revisão Jul/2025, “Dimensionamento Mecânico”, observação
  j, página 67, [URL registrada](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf).
  A Etapa 2 deve reconciliar esta página com a usada pela Regra 4.
- **Automação pendente:** o fato de risco textual existe, mas o ângulo ainda não é produzido.
- **Testes mínimos:** avaliação presente/ausente; chave fusível; ângulos fora da faixa; ângulo ausente.

### Regra 6 - Vão máximo de rede compacta ou isolada urbana

- **ID:** `nd31.vao.urbano-compacto-isolado`
- **Processo de análise:** a Regra 6 consiste em obter, em região urbana com cabo de tecnologia
  protegida ou isolada, o comprimento do vão e verificar o limite ordinário de 45 metros. Uma exceção
  só suspende a regra quando suas condições estiverem positivamente demonstradas.
- **Fatos:** `rede.contexto_urbano`; `cabo.tecnologia`; `vao.comprimento_m`;
  `vao.excecao_45_60_demonstrada`.
- **Condição/erro:** vão aplicável acima de 45 metros, sem exceção comprovada, gera possível
  divergência. Comprimento ausente gera não avaliável.
- **Exceções:** exceção de 45-60 metros somente com evidência positiva; ausência não é tratada como
  `false` inventado.
- **Fonte registrada no seed:** CEMIG ND-3.1, revisão Jul/2025, “Locação de Postes”, item 3, alíneas b
  e c, página 26,
  [URL registrada](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf). A Etapa 2
  deve reconfirmar tecnologia, contexto e condições da exceção.
- **Automação pendente:** `detectar_vaos` já calcula comprimentos, mas ainda não publica o fato para a
  região; isso está previsto na Etapa 6.
- **Testes mínimos:** comprimento abaixo/no/acima do limite; tecnologia não aplicável; exceção
  comprovada; comprimento ausente.

## Modelo para a próxima regra

```text
### Regra N - Título humano

- ID:
- Estado no registro:
- Estado de automação:
- Processo de análise:
- Fatos:
- Aplicabilidade:
- Condição/erro:
- Exceções:
- Fonte oficial: documento, revisão, item, página e URL.
- Evidência/localização esperada no PDF:
- Testes mínimos: conforme, divergência, não avaliável e exceções.
- Histórico: data, revisão anterior/substituída e motivo.
```
