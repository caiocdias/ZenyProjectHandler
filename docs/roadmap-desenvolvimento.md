# Roadmap de desenvolvimento

Este documento mostra somente o estado atual e as próximas decisões. O histórico detalhado de
implementação, testes e correções permanece no Git.

## Direção do produto

O Zeny Project Handler deve transformar projetos em PDF em uma revisão técnica navegável:

1. organizar projetos e folhas sem modificar os originais;
2. extrair evidências nativas e usar OCR apenas quando necessário;
3. identificar elementos, relações e vãos com rastreabilidade;
4. localizar cada resultado no desenho;
5. avaliar regras de conformidade apenas quando os fatos forem suficientes;
6. manter revisão humana para ambiguidade, exceções e critérios sem fonte confirmada.

Os projetos comissionados em `examples/` são referências dinâmicas do resultado desejado. Eles não
formam uma especificação normativa nem um gate congelado.

## Princípios de implementação

- Entregar fluxos completos acessíveis pela interface.
- Manter PDFs originais somente leitura.
- Preferir funções e objetos concretos a novas abstrações especulativas.
- Criar uma porta ou adaptador apenas quando houver uma fronteira real de infraestrutura ou um
  segundo uso comprovado.
- Reproduzir regressões descobertas em arquivos reais com fixtures sintéticas mínimas.
- Não registrar conteúdo de PDF, senha ou caminho absoluto em logs versionados.
- Usar estados não avaliáveis em vez de inferir informação normativa ausente.
- Documentar o comportamento atual uma vez; decisões históricas ficam no Git ou em ADRs ainda
  relevantes.

## Estado atual

| Área | Estado | Entregue | Próximo passo útil |
|---|---|---|---|
| Fundação, catálogo e domínio | Entregue | Domínio independente, catálogo versionado e validações | Ajustar somente quando uma necessidade de produto exigir |
| Persistência local | Entregue | SQLite, migrações e unidades de trabalho | Manter compatibilidade quando houver primeira versão distribuída |
| PDF e visualizador | Entregue | Várias folhas, rotação, zoom, render progressivo, PDFs protegidos e callouts | Refinar usabilidade a partir do uso real |
| Extração | Em desenvolvimento | Texto, vetores, imagens, anotações, símbolos e OCR condicional | Ampliar casos reais com regressões sintéticas |
| Exemplos locais | Em desenvolvimento | Smoke dinâmico e somente leitura | Usar os exemplos para priorizar lacunas, sem congelar arquivos |
| Interpretação semântica | Em desenvolvimento | Regras explícitas, propostas, relações, promoção e vãos | Melhorar associação geométrica e reduzir ambiguidades |
| Resultados na interface | Em desenvolvimento | Navegação lista ↔ PDF, filtros, correções e visibilidade | Simplificar densidade e validar clareza no uso diário |
| Conformidade | Em desenvolvimento | Registro importável/exportável, fatos, snapshots e callouts | Implementar provedores somente para regras normativamente confirmadas |
| Portabilidade | Entregue | Pacotes de projeto, backup, restauração, validação e recuperação | Validar em outra máquina e preparar distribuição |
| Empacotamento | Próximo | Launchers locais disponíveis | Criar instalador e testar em Windows limpo |

## Prioridades

### 1. Aproximar a análise dos projetos comissionados

- Classificar documento fora do domínio para não apresentar uma análise vazia como sucesso técnico.
- Melhorar associação de cabos, rótulos de vão e postes em desenhos densos.
- Produzir fatos rastreáveis para esforço, topologia, aterramento e consistência documental quando
  houver fonte e dados suficientes.
- Manter notas curtas, ajustes genéricos e observações sem critério inequívoco em revisão humana.

### 2. Completar regras hoje parciais

- Produzir evidência positiva da exceção aplicável a vãos entre 45 e 60 m.
- Produzir ângulo planejado e demais fatos geométricos sem inferência frágil.
- Separar cabo urbano, cabo rural, tronco, extensão e reparo.
- Comparar desenho, orçamento, materiais e anexos somente quando os dois lados estiverem presentes.

### 3. Melhorar a experiência de uso

- Reduzir textos técnicos nas ações principais e deixar detalhes auditáveis sob demanda.
- Destacar projeto, análise e achados como fluxo principal.
- Manter estados vazios, progresso, cancelamento e falha claros.
- Verificar contraste, navegação por teclado e comportamento em telas menores.

### 4. Distribuir com segurança

- Criar instalador para Windows sem exigir Python pré-instalado.
- Exercitar backup, restauração e pacote de projeto em uma segunda máquina.
- Definir a licença de distribuição de PyMuPDF/MuPDF antes da primeira entrega externa.

## O que não será antecipado

- Aprendizado de máquina, serviço externo ou GPU sem benchmark que demonstre necessidade.
- Editor genérico de regras ou catálogos sem um fluxo de usuário definido.
- Novo protocolo de recuperação para riscos que o produto ainda não enfrenta em distribuição.
- Compatibilidade indefinida com formatos antigos antes da primeira versão distribuível.
- Dashboards, métricas ou relatórios que não orientem uma decisão concreta.

## Critério simples de conclusão

Um incremento está concluído quando o fluxo funciona pela interface, persiste quando necessário,
possui regressões proporcionais ao risco e não deixa uma limitação conhecida capaz de produzir um
resultado técnico incorreto. Validação humana continua importante para clareza e domínio, mas não
exige formulários, manifesto congelado ou registro repetido de comandos.
