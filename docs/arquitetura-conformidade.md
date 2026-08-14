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

O provedor especializado de vãos consome essa projeção e publica `vao.comprimento_m` na região da
proposta que originou o cabo confirmado. A ligação usa a decisão de revisão; a identidade
determinística da promoção é apenas o fallback. Uma anotação conserva a evidência e a geometria do
rótulo; uma medida por coordenadas conserva as evidências dos postes e usa a geometria do cabo. Se
não houver comprimento, região inequívoca ou página coerente, nenhum valor é inventado. A exceção
`vao.excecao_45_60_demonstrada` só existe quando um marcador booleano positivo aponta para uma
evidência rastreável na mesma página e o comprimento está acima de 45 m e até 60 m. O fato
`vao.aplicabilidade_excecao_45_60_resolvida` é publicado fora dessa faixa ou junto da prova positiva;
dentro dela, a falta de prova mantém a regra não avaliável. Ângulos e cálculo mecânico continuam sem
detector ativo.

## Regras normativas iniciais

O registro `cemig-normas-distribuicao-2025.5` permanece pequeno e conservador após a revisão
integral, a salvaguarda da faixa excepcional da Regra 6 e a promoção dos dois subconjuntos
inequívocos de transformador em posteação existente:

| Tema | Fatos necessários | Resultado possível |
|---|---|---|
| Número do projeto | NS de 10 dígitos | presença ou possível divergência |
| Formato | A1, A2, A3 ou A4 | conforme, divergência ou não avaliável |
| Escala | escala, caso extraordinário e eventual órgão competente | regra inativa até as exceções terem fatos positivos |
| Equipamento em ângulo | equipamento, classe e ângulo | acima de 30° diverge; chave fusível é exceção |
| Risco de abalroamento | equipamento não fusível, ângulo até 30° e nota de avaliação | presença obrigatória |
| Vão urbano compacto/isolado | contexto, tecnologia, comprimento e aplicabilidade da exceção resolvida | até 45 m conforme; acima de 60 m possível divergência |
| Exceção de vão | área periférica/baixa densidade/chácaras, perfil favorável e evidência positiva | acima de 45 m e até 60 m fica não avaliável sem prova; com prova suspende a regra ordinária |
| Cabo novo urbano | contexto e tecnologia da proposta `INSTALAR` | cabo nu convencional diverge; reparo não é reclassificado |
| Estrutura/poste rural | contexto, código da estrutura e formato do único poste associado | CE1/CE1S/CEJ1/CEJ2/CEM4 divergem em duplo T |
| Transformador trifásico 30/45/75 kVA em posteação existente | contexto, potência catalogada, situação explícita, relação 1:1, resistência e formato não inferido | mínimo 300 daN; DT ou circular no subconjunto representável |
| Transformador trifásico 150/300 kVA em posteação existente | os mesmos fatos correlacionados | mínimo 600 daN e seção circular no subconjunto representável |

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
permanente por ID técnico dentro da linhagem daquele banco e não permite atualizar, apagar ou
reutilizar números.

O seed empacotado inicializa bancos sem revisão ativa. Na atualização `2025.3` → `2025.4`, o serviço
substitui somente a Regra 6 que ainda seja exatamente igual à versão oficial anterior; regras
adicionais são preservadas e qualquer edição do usuário nessa regra impede a migração automática.
Na atualização `2025.4` → `2025.5`, uma lista explícita acrescenta somente os IDs oficiais das
Regras 9 e 10 que ainda não existam. Uma definição local com o mesmo ID vence e nenhuma Regra 1–8
nem ID personalizado é reescrito. O procedimento é idempotente; o rótulo `2025.5` só é usado quando
a sequência resultante coincide exatamente com o seed, caso contrário a versão conserva a
proveniência com `+adicoes-2025.5`.
Importar mescla regras por ID e produz outro snapshot sem editar o seed. O usuário não dispõe de operação individual de
ativação, desativação ou remoção: o estado declarativo `enabled` só muda quando o ID correspondente
vem em um JSON importado, e omitir um ID do arquivo preserva a regra corrente. A cada revisão ativa,
o aplicativo publica atomicamente `catalogo-regras-conformidade.md` na pasta de dados do usuário. O
arquivo explica `when`, `unless` e `must` em linguagem humana; eventuais ausências criadas por versões
legadas continuam identificáveis no histórico. O JSON nunca contém expressões executáveis: geometria,
topologia e cálculos continuam em provedores Python compostos explicitamente.

Como defesa adicional, `SqlComplianceRuleRegistryRepository.salvar_ativa` recusa qualquer snapshot
novo cujo conjunto de IDs não contenha todos os IDs da revisão corrente. A restrição não reescreve
snapshots legados e complementa os triggers que proíbem alterar ou apagar revisões já persistidas.
Uma restauração de backup captura antes da troca a revisão ativa e, ainda dentro do bloco coberto
pelo rollback de banco e arquivos, acrescenta ao registro restaurado todo ID local ausente. Conteúdo
restaurado vence para IDs coincidentes, exceto pela migração imediata da Regra 6 oficial legada.
Primeiro são recuperados os IDs locais ausentes e só depois são anexados IDs oficiais novos ainda
ausentes, evitando que uma adição oficial esconda uma definição local pós-backup com o mesmo ID.
IDs adicionais do backup também permanecem. A numeração é estável dentro da mesma linhagem de banco;
ao combinar históricos independentes, colisões podem exigir novos números sem alterar os IDs. A mesma etapa
republica o catálogo Markdown, e qualquer falha restaura o snapshot e a projeção anteriores.

## Provedores de fatos por família

`application/compliance_fact_providers.py` define somente dois elementos compartilhados:
`ContextoProvedorFatos`, com a sessão semântica e seus alvos, e o protocolo chamável
`ProvedorFatosConformidade`, que devolve uma tupla de fatos. O helper de criação mantém identidade e
proveniência consistentes. Não há busca em diretórios, importação por nome ou descoberta dinâmica de
plugins.

O bootstrap compõe explicitamente a família regional existente e a família de vãos. O caso de uso
recebe essa tupla e o orquestrador aplica os provedores antes do avaliador declarativo. Assim, uma
nova família acrescenta fatos sem incluir condições normativas em Python e sem alterar o motor de
`when`/`unless`/`must`. Chamadas diretas usam a mesma composição padrão determinística.

Comentários PDF (`ANOTACAO`) e os objetos de sua aparência (`APARENCIA_ANOTACAO`) permanecem
persistidos como material de auditoria, mas são retirados antes de interpretar elementos, agrupar
pontos/coordenadas e derivar fatos técnicos. Portadores `Square` identificados pelos metadados como
`AutoCAD SHX Text` são conteúdo técnico do desenho e permanecem disponíveis; não são confundidos
com comentários. A rasterização do OCR semântico usa `annots=False`, evitando reintroduzir
visualmente os comentários, enquanto o conteúdo SHX nativo continua na extração. Sessões legadas
deixam de publicar fatos quando a proposta referencia comentário de revisão. O contexto urbano/rural
só é publicado por valor literal integral em `metadados.tipo_servico` ou em campo permitido e
rotulado do cabeçalho; token solto, negação, nome próprio, conflito, ausência e comentário mantêm a
regra não avaliável.

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
idempotente; importar conteúdo ou estado diferente das regras produz outra assinatura e, portanto,
uma nova execução sem substituir as anteriores. A reexecução usa somente os resultados semânticos
persistidos: não abre o PDF, não repete PyMuPDF ou OCR e não modifica a revisão já capturada.
Mudanças no próprio método de extração de fatos e avaliação também incrementam
`VERSAO_METODO_CONFORMIDADE`; uma execução com versão anterior é marcada como desatualizada mesmo
quando a assinatura das regras permanece igual.

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
3. **Regras:** revisão ativa, contagem de regras ativas/inativas, tabela e detalhes, com apenas as
   ações **Importar** e **Exportar**. A importação exige confirmação; erros identificam regra, campo e
   motivo sem revelar o caminho absoluto do arquivo. Não existem comandos de ativação, desativação
   ou remoção individual no painel nem no serviço de aplicação.

Selecionar um achado localizável abre a folha e centraliza seu callout realçado. Clicar na caixa ou
seta seleciona a linha correspondente, abre a visão **Conformidade** e eleva o dock. Itens documentais
continuam destacando a evidência ou região. Se a assinatura ativa divergir daquela usada na última
execução, o painel sinaliza **resultado desatualizado** e continua mostrando o snapshot antigo até
uma reanálise explícita. Confirmação humana e comparação entre projeto e coleta de campo permanecem
evoluções futuras.

## Evolução segura

Para adicionar uma regra ou uma nova família de fatos:

1. confirmar a revisão vigente e registrar documento, item, página e URL;
2. declarar o contexto sem transformar regra urbana em regra universal;
3. definir a chave, escopo, tipo, operadores e disponibilidade em `domain/compliance_facts.py`, com
   unidade na chave quando aplicável;
4. identificar a origem e as evidências capazes de provar o fato; ausência de detector ou de prova
   positiva deve omitir o fato, nunca publicar uma negação presumida;
5. implementar uma função ou classe determinística que satisfaça `ProvedorFatosConformidade`, testar
   valor, origem, evidência, alvo, página, geometria e dado ausente, e adicioná-la explicitamente à
   composição do bootstrap;
6. importar a regra declarativa versionada e exercitar conforme, divergência, não avaliável e exceção
   positiva sem modificar `compliance_evaluation.py`;
7. executar a análise e verificar snapshot, explicação, callout e persistência com fixtures
   sintéticas;
8. conferir o comportamento nos exemplos locais dinâmicos e transformar regressões observadas em
   fixtures sintéticas mínimas; o uso decisório continua condicionado a limites de erro conhecidos e
   revisão humana proporcional ao risco.

Uma atualização normativa nunca reinterpreta silenciosamente uma execução antiga. O achado preserva
a versão do registro usada; uma reavaliação explícita gera achados com a nova assinatura.
