# Arquitetura de conformidade e comissionamento

## Objetivo

O aplicativo deve comparar o que foi projetado, o que foi documentado e, futuramente, o que foi
encontrado em campo. A comparação não pode depender de uma sequência rígida de `if`s nem transformar
ausência de informação em reprovação automática. A unidade de raciocínio adotada é:

```text
evidência -> fato normalizado -> regra versionada -> achado auditável
```

Uma evidência continua sendo o trecho de texto, OCR, vetor, imagem, anotação ou campo PDF original.
Um fato é uma interpretação pequena e verificável dessa evidência, por exemplo
`vao.comprimento_m = 52`, `cabo.tecnologia = PROTEGIDA` ou
`documento.assinatura_pdf_preenchida = true`. A regra declara em que contexto o fato deve existir ou
qual limite deve atender. O achado liga o resultado à regra, à revisão da norma, ao alvo e às
evidências usadas.

## Tipos de regra a cobrir

As normas de projeto combinam padrões diferentes. A abstração deve acomodar ao menos:

1. **presença e completude:** campo, documento, cálculo, assinatura ou detalhe obrigatório;
2. **valor e faixa:** escala, comprimento, tensão, resistência, distância, ângulo ou potência;
3. **obrigação condicional:** um requisito só vale para determinado contexto, tecnologia ou classe;
4. **exceção comprovada:** a regra geral deixa de valer apenas quando os fatos da exceção estão
   documentados;
5. **compatibilidade:** equipamento, cabo, estrutura e poste formam uma combinação permitida;
6. **cardinalidade e periodicidade:** quantidade mínima/máxima ou ancoragem a cada distância;
7. **topologia e sequência:** derivação, proteção, fim de rede, conexão e vizinhança;
8. **geometria e localização:** cruzamento, canteiro, esquina, afastamento e faixa de servidão;
9. **cálculo:** queda de tensão, esforço, vão regulador e fórmulas dependentes de tabelas;
10. **consistência cruzada:** desenho, lista de materiais, memória de cálculo e cadastro devem
    concordar;
11. **evidência visual ou humana:** carimbo, rubrica, condição de campo ou risco cuja presença
    automática não comprova validade.

O motor inicial implementa presença, comparação, conjunto, aplicabilidade, exceções e quantificação
sobre valores repetidos. Compatibilidade, topologia, distância e cálculo devem usar avaliadores
especializados que publiquem seus resultados como fatos; o registro normativo continua declarativo.
Isso evita colocar cálculo mecânico ou geometria complexa dentro do JSON.

## Contratos implementados

### Alvo

`AlvoConformidade` limita o escopo da regra a projeto, documento, página, região ou elemento. O alvo
pode apontar para a entidade original, página e geometria.

### Fato

`FatoConformidade` possui:

- chave com namespace estável, como `projeto.escala` ou `conexao.angulo_graus`;
- valor primitivo e unidade embutida na chave quando aplicável;
- alvo, origem, confiança, geometria e IDs das evidências;
- identidade determinística para que uma nova execução equivalente não duplique resultados.

Confiança não muda um fato em verdade normativa. Ela informa se o fato pode sustentar automação ou
se deve permanecer em revisão.

### Regra

`RegraConformidade` informa ID, título, descrição, escopo, severidade, fonte normativa exata, revisão,
item e URL. Possui três grupos:

- `when`: condições que tornam a regra aplicável;
- `unless`: exceção que precisa estar positivamente demonstrada;
- `must`: requisitos que o alvo aplicável deve atender.

Os operadores iniciais são presença, ausência, igualdade, desigualdade, ordem numérica, pertinência
a conjunto e conteúdo textual. `TODOS` e `QUALQUER` controlam a comparação quando um alvo possui mais
de um valor para a mesma chave.

O registro JSON tem schema explícito, versão funcional e assinatura SHA-256 canônica. Alterar fonte,
condição ou limite produz outra assinatura e deve originar uma nova versão do registro.

### Resultado

Cada regra aplicável produz um dos estados:

- `CONFORME`: os fatos conhecidos atendem à condição verificável;
- `DIVERGENCIA`: os fatos contradizem o requisito ou falta uma presença obrigatória;
- `NAO_AVALIAVEL`: o requisito depende de um fato ainda desconhecido.

Na interface, `DIVERGENCIA` é apresentada como **possível divergência**. Ela só vira não conformidade
de comissionamento depois de revisão ou de uma política futura de promoção automática aprovada.
Aplicabilidade desconhecida não gera conclusão. Exceções ausentes não são presumidas; precisam de
evidência positiva.

## Informações adicionais do scanner

O incremento atual deriva:

- todos os pares `rótulo: informação` da zona de cabeçalho; Nota de Serviço/número do projeto,
  escala, formato, folha, data e circuito também são normalizados como fatos;
- formato A1 a A4 também pelas dimensões físicas da página;
- todos os pares rotulados do quadro de servidão, além da menção a servidão/faixa de domínio;
- candidatos a carimbo em anotações PDF `Stamp`, sem afirmar autenticidade;
- campos PDF `/Sig`, distinguindo campo preenchido, campo vazio e mero rótulo visual;
- tecnologia de todos os cabos e, separadamente, tecnologia dos cabos a instalar, preservando a
  situação da proposta;
- contexto urbano ou rural somente quando confirmado pelo tipo de serviço;
- código da estrutura MT a instalar e formato do poste associado quando a região contém um único
  par inequívoco;
- classe do equipamento resolvida pelo catálogo;
- notas próximas que demonstrem avaliação de abalroamento.

A análise semântica também produz a projeção `VaoDetectado` quando uma polilinha de cabo possui
relações `CONECTA` com dois postes distintos. A medida anotada junto à linha tem precedência; sem
anotação, usa-se a distância euclidiana entre as coordenadas dos postes. `Cabo` preserva o valor e a
origem `ANOTACAO_DESENHO`, `COORDENADAS` ou `INFORMADO`, e a aba **Vãos** expõe essa proveniência.
Essa projeção foi desenhada para alimentar futuramente fatos `vao.comprimento_m`; o scanner
normativo ainda não publica o fato nem avalia regras de vão automaticamente. Ângulos continuam sem
detector ativo.

## Regras normativas iniciais

O registro `cemig-normas-distribuicao-2025.3` permanece pequeno e conservador após a revisão
integral da Etapa 2:

| Tema | Fatos necessários | Resultado possível |
|---|---|---|
| Número do projeto | NS de 10 dígitos | presença ou possível divergência |
| Formato | A1, A2, A3 ou A4 | conforme, divergência ou não avaliável |
| Escala | escala, caso extraordinário e eventual órgão competente | regra inativa até as exceções terem fatos positivos |
| Equipamento em ângulo | equipamento, classe e ângulo | acima de 30° diverge; chave fusível é exceção |
| Risco de abalroamento | equipamento não fusível, ângulo até 30° e nota de avaliação | presença obrigatória |
| Vão urbano compacto/isolado | contexto, tecnologia e comprimento | máximo ordinário de 45 m |
| Exceção de vão | área periférica/baixa densidade/chácaras e perfil favorável | suspende a regra ordinária |
| Cabo novo urbano | contexto e tecnologia da proposta `INSTALAR` | cabo nu convencional diverge; reparo não é reclassificado |
| Estrutura/poste rural | contexto, código da estrutura e formato do único poste associado | CE1/CE1S/CEJ1/CEJ2/CEM4 divergem em duplo T |

A ND-3.1 trata redes urbanas. Limites de redes rurais não devem reutilizar essas regras: a ND-9.3,
por exemplo, contém tabelas dependentes de cabo, altura e resistência do poste. A mesma cautela vale
para os ângulos admissíveis das estruturas, que variam com modalidade de rede, tensão, seção,
estrutura e direção da deflexão.

O inventário de fontes, hashes, páginas e decisões está em
`docs/inventario-fontes-normativas.md`. Fontes oficiais lidas integralmente:

- [página de normas técnicas de redes de distribuição da CEMIG](https://www.cemig.com.br/normas-tecnicas/normas-tecnicas-de-redes-de-distribuicao/);
- [ND-2.7 — Instalações Básicas de Redes de Distribuição Aéreas Isoladas, Nov/2016](https://www.cemig.com.br/wp-content/uploads/2025/10/nd_2_7-1.pdf);
- [ND-2.9 — Instalações Básicas de Redes de Distribuição Compactas, Jun/2016](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_2-9-Instalacoes_Basicas_RD_Compactas.pdf);
- [ND-3.1 — Projetos de Redes de Distribuição Aéreas Urbanas, Jul/2025](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf);
- [ND-4.15 — Proteção de Sobrecorrentes, Nov/2017](https://www.cemig.com.br/wp-content/uploads/2025/10/nd_4_15_000001p.pdf);
- [ND-9.3 — Programa Minas Trifásico, Set/2021](https://www.cemig.com.br/wp-content/uploads/2025/10/ND-9.3-programa-minas-trifasico.pdf).

## Registro configurável e catálogo de fatos

O vocabulário aceito pelo registro é explícito em
`domain/compliance_facts.py`. Cada chave declara os escopos em que pode ser observada, o tipo do
valor, os operadores permitidos, a descrição e se o provedor já está disponível ou apenas
planejado. A importação primeiro valida o schema JSON público e depois essa semântica. Chave
desconhecida, escopo incompatível, operador inválido ou valor de tipo incorreto recusam o arquivo
inteiro. Uma chave conhecida com provedor planejado é aceita com aviso e continua produzindo
`NAO_AVALIAVEL` enquanto o fato não existir.

O SQLite guarda cada configuração como um único snapshot JSON canônico em
`compliance_rule_revisions`, com ID próprio da revisão, ID e versão informados pelo registro,
assinatura SHA-256, data e indicador da revisão ativa. O conteúdo é protegido contra alteração e
remoção por triggers; somente o indicador ativo pode mudar. Assinaturas já existentes são
reutilizadas em vez de duplicadas. A tabela `compliance_rule_numbers` atribui uma sequência
permanente por ID técnico e não permite atualizar, apagar ou reutilizar números.

O seed empacotado só é usado para inicializar um banco sem revisão ativa. Importar mescla regras por
ID, e ativar, desativar ou remover produz outro snapshot sem editar o seed. A cada revisão ativa, o
aplicativo publica atomicamente `catalogo-regras-conformidade.md` na pasta de dados do usuário. O
arquivo explica `when`, `unless` e `must` em linguagem humana e conserva IDs removidos como
histórico. O JSON nunca contém expressões executáveis: geometria, topologia e cálculos continuam em
provedores Python compostos explicitamente.

## Execuções auditáveis

`ExecutarAnaliseConformidade` é a única entrada para avaliar regras. O caso de uso captura a revisão
ativa antes de carregar a sessão semântica mais recente, calcula o resultado e grava uma única
`ExecucaoConformidade` na mesma transação. O fluxo MVP e a ação explícita da interface chamam esse
mesmo caso de uso. Falha ou cancelamento reverte o snapshot inteiro.

A tabela `compliance_executions` mantém metadados indexados e um payload JSON canônico com projeto,
IDs das execuções semânticas de origem, revisão/versão/assinatura das regras, assinatura da sessão,
horário, alvos, fatos, achados e itens documentais. O payload não copia a evidência bruta: fatos e
itens conservam seus vínculos de proveniência. Cada achado registra os IDs dos fatos relevantes e o
resultado observado de cada condição `when`, `unless` e `must`, inclusive operador, valor esperado e
valor observado. Um trigger impede alteração do snapshot.

O ID deriva deterministicamente das assinaturas da sessão e da revisão. Repetir a mesma entrada é
idempotente; ativar, remover ou importar regras produz outra assinatura e, portanto, uma nova
execução sem substituir as anteriores. A reexecução usa somente os resultados semânticos
persistidos: não abre o PDF, não repete PyMuPDF ou OCR e não modifica a revisão já capturada.

## Projeção e camada visual de callouts

`application/compliance_callouts.py` converte somente achados `DIVERGENCIA` localizáveis em uma
projeção sem Qt. Cada entrada conserva o ID do achado, página, texto quebrado, caixa sugerida e uma ou
mais âncoras com tipo de origem, ID de referência e geometria completa. A seleção da geometria segue
uma precedência explícita: fatos que participaram da decisão, evidências referenciadas pelo achado e,
por último, o alvo. A primeira fonte disponível determina a página; geometrias de outras páginas não
são misturadas. Uma ausência de página ou geometria rastreável não produz coordenadas artificiais.

O posicionamento trabalha em pontos físicos e volta a coordenadas normalizadas. Um conjunto pequeno
e ordenado de candidatos ao redor do alvo é contido nas margens da folha e pontuado pela interseção
com o alvo e com caixas já ocupadas. Assim, entradas iguais geram o mesmo layout e uma colisão só é
aceita quando todos os candidatos válidos colidem. Largura, quebra de linha, altura e margens usam
medidas físicas, mantendo a tipografia proporcional em A4/A3, retrato ou paisagem.

`PdfGraphicsView` materializa a projeção em uma camada vetorial própria, acima de prévia e tiles e
separada dos sublinhados de revisão e do contorno temporário. A caixa tem fundo branco, borda e texto
vermelhos; cada âncora recebe uma linha com ponta aberta. A camada é recriada ao trocar página ou
transformador, enquanto zoom e redimensionamento usam a transformação da cena. Ela não entra no
cache raster e não abre nem grava o PDF. A camada mantém seleção e visibilidade próprias: ocultar um
callout não altera sublinhados de elementos, tiles ou contorno temporário, e ocultar um elemento não
altera callouts.

A interface conserva um conjunto temporário de IDs de achados ocultos para o par projeto/execução.
Trocar de folha ou ordenar a lista preserva esse conjunto; trocar de projeto ou carregar outra
execução o reinicia. O viewer recebe somente os callouts visíveis. A seleção programática realça e
centraliza sem reemitir o sinal; somente o clique na caixa, no texto ou na seta emite a seleção de
volta à lista, evitando ciclos.

## Painel de documentação e conformidade

O painel próprio possui três visões:

1. **Documentação:** todos os campos rotulados de cabeçalho e servidão, carimbos e assinaturas, com
   estado e confiança;
2. **Conformidade:** a última execução persistida, com possíveis divergências primeiro, valores
   observados/esperados, alvo, fonte normativa, revisão, estado de localização e olho por callout. As
   ações **Exibir todos** e **Ocultar todos** afetam somente achados localizáveis. O olho de um achado
   sem geometria fica desabilitado com diagnóstico acessível. A ação **Analisar conformidade**
   reaplica explicitamente a revisão ativa à sessão semântica persistida;
3. **Regras:** revisão ativa, contagem de regras ativas/inativas, tabela e detalhes, com ações para
   importar, exportar, ativar/desativar e remover. Importação e remoção exigem confirmação; erros
   identificam regra, campo e motivo sem revelar o caminho absoluto do arquivo.

Selecionar um achado localizável abre a folha e centraliza seu callout realçado. Clicar na caixa ou
seta seleciona a linha correspondente, abre a visão **Conformidade** e eleva o dock. Itens documentais
continuam destacando a evidência ou região. Se a assinatura ativa divergir daquela usada na última
execução, o painel sinaliza **resultado desatualizado** e continua mostrando o snapshot antigo até
uma reanálise explícita. Confirmação humana e comparação entre projeto e coleta de campo permanecem
evoluções futuras.

## Evolução segura

Para adicionar uma regra:

1. confirmar a revisão vigente e registrar documento, item, página e URL;
2. declarar o contexto sem transformar regra urbana em regra universal;
3. identificar os fatos necessários, suas unidades e a evidência capaz de comprová-los;
4. implementar primeiro o extrator ou avaliador especializado;
5. adicionar a regra versionada e casos sintéticos de conforme, divergência, exceção e dado ausente;
6. calibrar somente na partição de desenvolvimento do conjunto autorizado;
7. promover para uso decisório apenas depois dos limites de erro e do aceite humano.

Uma atualização normativa nunca reinterpreta silenciosamente uma execução antiga. O achado preserva
a versão do registro usada; uma reavaliação explícita gera achados com a nova assinatura.
