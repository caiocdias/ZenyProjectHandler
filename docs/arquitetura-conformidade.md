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
- tecnologia do cabo e classe do equipamento resolvidas pelo catálogo;
- notas próximas que demonstrem avaliação de abalroamento.

A análise semântica também produz a projeção `VaoDetectado` quando uma polilinha de cabo possui
relações `CONECTA` com dois postes distintos. A medida anotada junto à linha tem precedência; sem
anotação, usa-se a distância euclidiana entre as coordenadas dos postes. `Cabo` preserva o valor e a
origem `ANOTACAO_DESENHO`, `COORDENADAS` ou `INFORMADO`, e a aba **Vãos** expõe essa proveniência.
Essa projeção foi desenhada para alimentar futuramente fatos `vao.comprimento_m`; o scanner
normativo ainda não publica o fato nem avalia regras de vão automaticamente. Ângulos continuam sem
detector ativo.

## Regras normativas iniciais

O registro `cemig-nd31-2025.2` começa pequeno e conservador:

| Tema | Fatos necessários | Resultado possível |
|---|---|---|
| Número do projeto | NS de 10 dígitos | presença ou possível divergência |
| Formato | A1, A2, A3 ou A4 | conforme, divergência ou não avaliável |
| Escala | 1:1000 ou 1:500 | candidato; exceções de órgãos externos exigem contexto futuro |
| Equipamento em ângulo | equipamento, classe e ângulo | acima de 30° diverge; chave fusível é exceção |
| Risco de abalroamento | equipamento não fusível, ângulo até 30° e nota de avaliação | presença obrigatória |
| Vão urbano compacto/isolado | contexto, tecnologia e comprimento | máximo ordinário de 45 m |
| Exceção de vão | área periférica/baixa densidade/chácaras e perfil favorável | suspende a regra ordinária |

A ND-3.1 trata redes urbanas. Limites de redes rurais não devem reutilizar essas regras: a ND-9.3,
por exemplo, contém tabelas dependentes de cabo, altura e resistência do poste. A mesma cautela vale
para os ângulos admissíveis das estruturas, que variam com modalidade de rede, tensão, seção,
estrutura e direção da deflexão.

Fontes oficiais consultadas:

- [página de normas técnicas de redes de distribuição da CEMIG](https://www.cemig.com.br/normas-tecnicas/normas-tecnicas-de-redes-de-distribuicao/);
- [ND-3.1 — Projetos de Redes de Distribuição Aéreas Urbanas, Jul/2025](https://www.cemig.com.br/wp-content/uploads/2025/10/ND_3_1_2025.pdf);
- [ND-9.3 — Programa Minas Trifásico](https://www.cemig.com.br/wp-content/uploads/2022/03/ND-9.3-programa-minas-trifasico.pdf).

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

## Painel de documentação e conformidade

O painel próprio possui três visões:

1. **Documentação:** todos os campos rotulados de cabeçalho e servidão, carimbos e assinaturas, com
   estado e confiança;
2. **Conformidade:** regras conformes, possíveis divergências e casos não avaliáveis, com a fonte
   normativa.
3. **Regras:** revisão ativa, contagem de regras ativas/inativas, tabela e detalhes, com ações para
   importar, exportar, ativar/desativar e remover. Importação e remoção exigem confirmação; erros
   identificam regra, campo e motivo sem revelar o caminho absoluto do arquivo.

Selecionar um item com página e geometria abre a folha e destaca a evidência ou região. A fase
seguinte deverá persistir fatos e achados, permitir confirmação humana e comparar projeto com coleta
de campo sem perder as duas origens.

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
