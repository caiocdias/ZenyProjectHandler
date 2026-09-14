# E10 — Referência integral do segundo PDF

Auditoria local iniciada em 14/09/2026 sobre `80dc6fd`. Git inicialmente limpo,
`HEAD...origin/main = 0 0` contra a referência local, sem fetch. Nenhum `AGENTS.md`
na hierarquia aplicável ou nas pastas envolvidas. Desde a base `9cb0ef7` do
diagnóstico mudaram somente os dois documentos do plano/diagnóstico. E08 e E09
continuam bloqueadas; não são dependências de execução de E10.

Esta etapa estabelece a referência e mede o comportamento. Não homologa a leitura
automática nem modifica o pipeline. A duração não constitui critério de aceite.

## Fonte e inventário

Fonte local: `examples/PROJETO DE REDE 1256407599.pdf`, SHA-256
`0793c292df9722ff48df31ab052018d4233ad3541706f50f53e994cc1670af06`,
988.018 bytes, uma página de 595 × 842 pontos, rotação 0. O formato físico A4
e o texto “A3” no carimbo devem permanecer distintos, sem corrigir a origem.

Artefatos privados em `tmp/rede-1256407599/e10/`. `build_inventory.py` transcreve
a referência visual em `inventory.json`, antes da auditoria das saídas. `render.py`
gera as duas camadas de toda a folha e três bandas sobrepostas que cobrem todo o
domínio normalizado, além de detalhes dos pontos, rede existente e rodapé.
`rois.json` fixa as ROIs; centros manuais têm tolerância de 0,01 e não são máscaras
dos glifos. `annotations.json` preserva as 28 anotações, xrefs, tipos e metadados;
`annotations-audit.json` classifica cada objeto e o vincula aos itens pertinentes
(nove Stamp, quinze Ink, três FreeText e um Square). Três traços isolados ficam
indeterminados, sem fato técnico confirmável; não são removidos do registro.
Dados pessoais, coordenadas, imagens e transcrição integral ficam somente em `tmp/`.

O inventário distingue código/qualificador, situação, ponto físico, trecho,
representação auxiliar, comentário, revisão e campo documental. Duas estruturas
adjacentes com o mesmo código no mesmo ponto são duas ocorrências; uma ampliação
do quadro de P5 é outra representação do mesmo ponto. Fase e neutro são cabos
distintos, mas não multiplicam o trecho físico. Pontos sem identificador recebem
IDs locais de referência, nunca números operacionais inventados no produto.

Denominador operacional **sem conflito entre camadas**, congelado antes de correções:

| Categoria | Instalar | Existente | Remover | Total |
|---|---:|---:|---:|---:|
| Poste com código | 4 | 1 | 1 | 6 |
| Estrutura MT | 5 | 1 | 0 | 6 |
| Estrutura BT | 4 | 2 | 0 | 6 |
| Cabo com código integral | 6 | 5 | 0 | 11 |
| Total | 19 | 9 | 1 | 29 |

“Sem conflito” qualifica a leitura da fonte, não a correção da saída. Código de
poste sem material/formato não autoriza escolher um item de catálogo arbitrário.
Ausência de catálogo é defeito/limitação a resolver, não motivo para retirar item
do denominador. Equivalências de código só serão aceitas se explicitamente
justificadas, preservando o texto observado e a localização.

Estratos adicionais, que não podem desaparecer da avaliação:

- Nove pontos físicos: cinco identificados (incluindo uma entrega, que não é
  poste) e quatro sem identificador; três suportes não têm código legível declarado.
- Dez trechos físicos: quatro novos e seis existentes. Sete têm ambos os endpoints
  visíveis; três continuam fora da folha. Seis comprimentos explícitos; quatro
  desconhecidos. Há ainda três ângulos e duas alturas em anotações, que não são vãos.
- Dois grupos de revisão: um cabo com dois valores alternativos e um conjunto MT
  existente substituído visualmente por duas operações. Medir cinco alternativas
  observadas e dois conflitos; a aprovação técnica ainda não foi estabelecida.
- Três rótulos de equipamento legíveis, com classificação operacional completa
  reservada à revisão; oito grupos simbólicos auxiliares, sem quantidade de
  equipamentos deduzida de círculos/cores. Um código de cabo é cortado pelo rodapé.
- 64 itens documentais/presenças/valores, incluindo vazios explícitos, notas,
  cabeçalho, servidão, CHI, vão regulador, fotografias, assinaturas e coordenadas.
  Dois itens negativos da cerca e sua coordenada impedem confundir contexto com rede.

O inventário não transforma assinaturas raster em autenticação, fotos em prova de
conformidade, QR em autorização de acesso, nem o carimbo “Revised” em aprovação.
O quadro de vão regulador deve ser lido literalmente e confrontado com o desenho;
seus valores não substituem automaticamente os comprimentos dos trechos.

## Política de revisão técnica para E11

1. Detectar e apresentar conflito antes de catalogar/promover. Comparar base e
   aparência das anotações na mesma geometria. Preservar texto anterior, novo texto,
   cores/riscos, máscara de oclusão, documento/hash, página, xrefs e evidências.
2. Classificar cada anotação como comentário/apresentação, conteúdo documental,
   candidata a revisão técnica ou indeterminada. Tipo `Stamp`, data e autor informado
   não comprovam autoridade. A referência visual identifica candidatos, não os aprova.
3. Revisão candidata conflitante exige decisão explícita do técnico: aceitar nova
   versão, manter anterior ou deixar pendente, com motivo, autor e versão. Até lá,
   nenhuma alternativa conflitante pode ser confirmada silenciosamente. Conteúdo
   não afetado continua processável; não bloquear a página inteira por dois conflitos.
4. Preservar histórico e proveniência de ambas as alternativas após a decisão.
   Uma cópia ampliada de uma revisão deve referenciar o mesmo grupo, sem gerar ativo.
   Altura acrescentada em anotação é fato candidato separado do comprimento.
5. UI: comparação com/sem anotações, realce da área afetada e escolha explícita;
   situação operacional continua distinta do estado de revisão. DTO: grupo estável
   de conflito, versões, evidências, decisão e valor efetivo, com versionamento e
   concorrência. Não reutilizar `requires_review` como único registro do conflito.
6. Cache: assinatura inclui política/versão do extrator, hash da fonte, conteúdo e
   aparência das anotações, revisão da decisão e dependências semânticas. Reanálise
   preserva a decisão somente para identidade comprovadamente igual; mudança de
   fonte/conteúdo invalida resultados dependentes. Exportações distinguem pendente,
   anterior e efetivo, sem apresentar o anterior como vigente aprovado.

São requisitos para E11, sem alteração de contratos, UI, cache ou regras em E10.
Não se liga indiscriminadamente `annots=True` no OCR de produção.

## Métricas e metas congeladas

Emparelhamento um a um por ocorrência: documento/página, ROI, classe,
código/qualificador, situação e vínculo ao ponto/trecho. Sobreposição de caixas ou
igualdade de contagens só localiza candidatos; não comprova correspondência.
Registrar primeira fase divergente e toda a cadeia até o XLSX, inclusive ausência
explícita de proposta/ativo e destino documental não aplicável.

- Precisão e recall: 100% das 29 ocorrências, por categoria e situação; zero
  duplicatas. TP exige os campos corretos e a ocorrência correta. FN não pode ser
  removido por falha de OCR, catálogo, associação ou ausência de DTO.
- Código/qualificador/situação exatos: 100% dos campos legíveis, incluindo os três
  códigos de equipamento e as cinco alternativas de revisão. Dois conflitos
  detectados e encaminhados, zero alternativas conflitantes confirmadas sem decisão.
- Topologia: nove pontos corretos, sete pares de endpoints visíveis corretos,
  três continuidades explícitas, dez trechos representados sem multiplicação por
  condutor e seis comprimentos corretamente associados. Quatro comprimentos
  desconhecidos permanecem desconhecidos. Alturas e ângulos não viram comprimentos.
- Documentação: 100% dos 64 itens representados ou com limitação/revisão explícita
  e rastreável; erro de valor ou omissão silenciosa reprova leitura integral.
- Erro entre confirmações automáticas = confirmações incorretas ou duplicadas /
  todas as confirmações; meta 0%. Versão conflitante sem decisão conta como erro.
  Denominador zero produz “não definido”, nunca 100% de precisão.
- Cobertura automática correta = ocorrências elegíveis inteiramente corretas,
  confirmadas uma a uma / 29; meta ≥95% global e ≥90% em cada categoria.
  Taxa de revisão do núcleo = itens do núcleo que exigem decisão /29; meta ≤5%.
  Omissões não contam como revisões realizadas. Reportar também a fração de propostas
  marcadas para revisão, usando todas as propostas como denominador separado.
- Ambiguidades reais têm denominador próprio e revisão obrigatória de 100%; não
  penalizar abstenção justificada nesses itens nem usá-los para esconder defeitos
  do núcleo. A taxa total de revisão inclui esses casos e deve ser publicada.
- Leitura exata do projeto = todos os itens/relacionamentos/medidas/documentos
  corretos e todos os conflitos explicitamente resolvidos ou pendentes visíveis,
  sem omissão silenciosa. Meta 100% dos documentos avaliados; um erro reprova o
  documento inteiro. Avaliação finita não prova infalibilidade em projetos novos.

Separação de dados: os PDFs anterior e atual já foram inspecionados e são casos de
ajuste/regressão, não avaliação cega. Documentos locais ainda não inspecionados
podem ser reservados por hash integral. Famílias sintéticas reservadas devem usar
geradores/sementes distintos dos ajustes: orientação, escala, cor/risco, cópia de
revisão, oclusão, símbolos negativos e continuidade. Nenhum recorte ou variante do
mesmo documento/família atravessa a divisão. Ao consultar um caso reservado para
ajustar código, registrar contaminação e substituí-lo antes de medir generalização.
O manifesto privado fixa a divisão; o gate público continua independente de PDFs.

## Instrumentação e reprodução

`scripts/benchmark_network_pdf.py --telemetry` acrescenta observação dos cinco modos
OCR no ponto comum do Tesseract, com PSM, DPI, dimensões, duração, número de segmentos
e conclusão/falha. O controle sintético fica separado das chamadas do documento.
Não muda capacidade, parâmetros, retorno, exceções ou política OCR.

O modo também mede rasterização com/sem anotações a 150 DPI, em novas aberturas,
separadamente da cadeia semântica. Ordem fixa sem/com: não é ensaio causal de
cache frio, nem custo de OCR sobre anotações. Registra hashes de pixels e bytes.
Projeta os insumos documentais puros pelas mesmas funções de DTO/XLSX do servidor;
não executa conformidade, HTTP, Qt ou SQL e não inventa mercado inicial.
Sem `--telemetry`, permanecem as saídas usuais de Resultados.

`monitor.ps1` lança três processos sequenciais, cada um com SQLite novo por
variante e sem cache de análise. Não havia Python/Tesseract concorrente no início;
nenhuma renderização, teste ou análise Python foi executada durante as medições.
Memória cobre launcher/intérprete e Tesseract, inclusive serialização e sondas.
Amostras de 200 ms podem perder picos curtos; high-water é informado separadamente.
O custo do monitor não foi subtraído. Memória é telemetria, com falhas de recurso
explicitadas; tempo não possui teto de 60, 300 segundos ou outro teto de aceite.

```powershell
git status --short
git rev-list --left-right --count HEAD...origin/main
git diff 9cb0ef7 HEAD --stat
.venv/Scripts/python.exe tmp/rede-1256407599/e10/render.py
.venv/Scripts/python.exe tmp/rede-1256407599/e10/build_inventory.py
& tmp/rede-1256407599/e10/monitor.ps1
# O monitor executa o comando abaixo para N = 1, 2 e 3, sequencialmente:
.venv/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e10/run-N.json --runtime-directory tmp/e01/runtime --telemetry
```

## Resultado da auditoria

Referência final: **139 registros**, com vínculo individual a ROI/camada e às fases
aplicáveis em `audit.json`. As 38 propostas finais também têm pareamento reverso,
incluindo saídas simbólicas fora do núcleo. A revisão final acrescentou dois campos
documentais (identificador de equipamento e abreviação de um suporte); não alterou
as 29 ocorrências operacionais. A integridade dos vínculos e células foi verificada.

| Caso | Cadeia e primeira divergência | Referência privada |
|---|---|---|
| D01 | Base e revisão visível diferem; só o cabo base chega a proposta, ativo, DTO e XLSX, confirmado sem conflito. A aparência técnica vem de Stamp e oclusões Ink. | `R01`; anotação 111 e Ink; proposta 16 de `run-1.json` |
| D02 | Duas leituras do mesmo neutro geram duas propostas, dois ativos e duas linhas em Vãos/Elementos. Mesmo traçado, situação, identificador e comprimento; não são fase/neutro distintos. | `C-V2-3-1`; propostas 29/33 |
| D03 | Poste, MT, BT e chave têm texto/geometria de U1, mas recebem P5. A associação errada permanece nos DTOs e XLSX; os quatro não são promovidos. | `A06`, `A12`, `A18`, `Q2`; propostas 12/4/8/0 |
| D04 | Base contém N4 existente; anotações mostram remover/instalar e cópia ampliada. Só a versão base chega à proposta/DTO/XLSX, com conflito genérico de promoção, sem grupo de revisão técnica. | `R02`; anotações 138/146; proposta 10 |
| D05 | Código do transformador está no OCR da própria ROI; não existe proposta bruta/final, ativo, DTO ou célula correspondente. Catálogo incerto não justifica apagar o literal. | `Q1`; evidência `824ea03e-1442-5aa5-ad04-533178aec707` |
| D06 | Cabos de 36/83 m são promovidos e têm medidas em atributos DTO, mas não em Vãos nem nas células de Elementos. `detectar_vaos` exclui cabos sem ambos os postes, sem identificador V e sem entrega tipada. | `T36`, `T83`, `length-T36`, `length-T83`; propostas 35/30 |

D06 também inclui nomes P3/P4 trocados nas geometrias de origem/destino do cabo de
14 m. Há vinte pontos elétricos materializados para dez cabos, com IDs por cabo;
não constituem vinte pontos físicos do desenho. As oito linhas de Vãos representam
quatro traçados novos, incluindo a duplicata D02. Tipo e modalidade permanecem
`DESCONHECIDO`; não há classificação técnica de padrão demonstrada apenas pela casa.
O inventário chama P4 de endpoint do consumidor por contexto visual, sem homologar
classe normativa `ENTREGA` nem autorizar criação de poste.

Perdas adicionais rastreadas:

- Os dois neutros existentes N-4 têm OCR próprio, mas nenhuma proposta bruta/final.
  São omissões de interpretação, não ambiguidades excluídas do denominador.
- A segunda chave tem OCR e proposta bruta, descartada no filtro de identificadores
  (`Q3`); o transformador perde-se antes desse filtro. Símbolos permanecem sujeitos
  à revisão da convenção, sem presumir classes pela contagem de círculos.
- Cinco qualificadores MT do núcleo sobrevivem em atributos do DTO, porém as células
  XLSX apresentam somente o código-base. Não se confunde igualdade DTO→planilha das
  colunas existentes com exportação integral de todos os atributos do DTO.
- Campos documentais truncados, repetidos e coordenada fragmentada chegam ao XLSX.
  As assinaturas são visíveis nas aparências, mas o controle relata que não localizou
  campo/rótulo; ele não comprova ausência de assinatura. CHI, fotos, vão regulador e
  várias notas permanecem sem campos individuais equivalentes. A menção à servidão
  e seus oito campos são recuperados; isso não substitui a verificação SQL vigente.

Medição por **pareamento explícito**, não por contagem agregada:

| Núcleo na proposta: código/qualificador, situação e ponto/traçado | TP | FN | FP |
|---|---:|---:|---:|
| Poste | 5 | 1 | 1 |
| MT | 5 | 1 | 1 |
| BT | 5 | 1 | 1 |
| Cabo | 9 | 2 | 1 |
| Total | 24 | 5 | 4 |

Recall desse escopo = **24/29 = 82,76%**; precisão = **24/28 = 85,71%**. Os três
itens de U1 associados a P5 são simultaneamente FN no ponto correto e FP no errado;
a duplicata de neutro acrescenta um FP. Instalar: 19/19 recuperados, mais um FP
por duplicação; existente: 4/9 corretos, três associações erradas e duas omissões;
remover: 1/1. O núcleo nativo tem zero propostas finais: recall 0/29, precisão não
definida (0/0). Esses números não certificam promoção, relações elétricas completas
ou projeção integral.

Há **2/10 = 20% de erros conhecidos entre confirmações** (D01 e duplicata D02).
As oito outras confirmações acertam os campos da ocorrência, mas continuam com
pendências de identidade/topologia e, em dois casos, de projeção. Cobertura automática
nesses campos = 8/29 = 27,59%; **cobertura automática integral comprovada = 0/29**.
Não se declara precisão integral de 80% para as confirmações. Revisão marcada no
núcleo = 19/29 = 65,52%; duas omissões não viram revisões realizadas. Na saída total,
28/38 = 73,68% das propostas exigem revisão. Conflitos técnicos representados = 0/2.
Os seis comprimentos chegam aos ativos, mas só quatro chegam a Vãos; o par nome/
geometria de 14 m está errado. Leitura exata do documento inteiro = **0/1**.

Dos 64 itens documentais, 20 têm valor/presença corretamente projetado (18 na aba
Documentação e duas coordenadas em Resultados), quatro têm valor incorreto, três
apresentam duplicação e 37 não têm campo individual equivalente até a exportação.
Há 31 linhas documentais produzidas; esse número não foi usado como recall.
Figuras/metadados de anotações foram preservados como evidências, sem atribuir-lhes
leitura semântica inexistente. Metas E10 permanecem **não atendidas pelo pipeline**;
a conclusão desta etapa certifica a referência e as medições, não a leitura integral.

## Três medições isoladas

Python 3.12.14, PyMuPDF 1.28.0, Tesseract 5.4.0.20240606, `por+eng`, OEM 3;
extrator 1.14.0 e interpretador 22.0. Parâmetros de extração permanecem 450/1200/1800
DPI, grade 3×3 e sobreposição 0,025. Cada execução realizou 81 chamadas OCR do
PDF (68 PSM 11 e 13 PSM 7), além de um controle sintético separado. Todas concluíram;
nenhum timeout/diagnóstico ocorreu. O timeout existente de 90 s é por chamada,
não teto do benchmark; não foi alterado nem usado para abreviar esta análise.

| Medida (s) | Execução 1 | Execução 2 | Execução 3 |
|---|---:|---:|---:|
| Nativo até regiões/vãos | 7,966 | 8,456 | 8,099 |
| OCR extração/persistência | 90,333 | 85,608 | 89,710 |
| OCR interpretação/promoção/persistência | 3,455 | 3,451 | 3,964 |
| OCR regiões/vãos | 0,021 | 0,026 | 0,041 |
| OCR total até regiões/vãos | 94,130 | 89,407 | 94,104 |
| OCR incluindo DTOs e XLSX documental | 96,488 | 91,741 | 96,706 |
| Dentro das chamadas OCR do PDF | 74,028 | 69,928 | 73,171 |
| Raster 150 DPI sem anotações | 0,0374 | 0,0366 | 0,0363 |
| Raster 150 DPI com anotações | 0,0592 | 0,0592 | 0,0590 |

| Memória (MiB) | Execução 1 | Execução 2 | Execução 3 |
|---|---:|---:|---:|
| Python RSS amostrado (inclui launcher) | 348,73 | 328,57 | 303,15 |
| Python high-water do intérprete | 372,87 | 374,74 | 374,42 |
| Tesseract RSS amostrado | 207,90 | 214,47 | 207,75 |
| Tesseract high-water observado | 216,11 | 214,47 | 216,10 |
| Agregado RSS simultâneo | 483,46 | 490,69 | 483,70 |
| Amostras | 513 | 491 | 514 |

Resultados reproduzidos nas três execuções: 2.049 evidências, 228 OCR, 48 propostas
brutas, 38 finais, 48 relações, 10 cabos confirmados, 11 regiões, oito linhas de Vãos.
IDs, propostas e contagens coincidem, com hash/tamanho/mtime da fonte preservados.
Os arquivos `run-1/2/3.json`, logs, `memory-1/2/3.json` e `performance.json` registram
os resultados completos. Bases temporárias são descartadas após cada variante.

A consulta CIM de CPU/RAM foi negada antes de iniciar os benchmarks. O monitor foi
adaptado para coletar identificação de CPU e 16 processadores lógicos sem CIM;
memória dos processos foi medida normalmente. RAM física de E01 é somente registro
histórico, não nova medição. PyMuPDF e Poppler foram comparados visualmente nos dois
modos após o benchmark. Poppler gerou as duas imagens com saída zero; avisos de
fontes/Flate permanecem nos logs, sem reescrita do PDF ou perda visual impeditiva.

## Validações e handoff

- Testes públicos obrigatórios e instrumentação: **11 aprovados**; sem PDF privado,
  Tesseract real, rede ou idioma instalado. Cobrem caminho nativo até Vãos, fonte
  intacta, limpeza, IDs, runtime obrigatório, controle OCR vazio, ambos os modos de
  anotação, projeção documental e transparência dos cinco modos OCR/erros.
- Auditoria privada: **6 verificações aprovadas**, cobrindo os 139 registros, ROIs,
  denominadores, pareamento de códigos/situações/geometria, todos os IDs/células,
  D01–D06 como falhas diagnosticadas, estabilidade das três medições e separação.
- Fechamento: **17 testes aprovados em 5,42 s** (11 públicos + seis privados), em
  `verified-tests.log`; Ruff, formatação, Mypy e `git diff --check` aprovados. O primeiro
  comando Mypy com caminhos isolados não resolveu os pacotes locais; o comando
  canônico identificou três chamadas PyMuPDF sem tipagem. Foram anotadas somente
  essas chamadas externas com `no-untyped-call`; o Mypy canônico passou em 334 arquivos.
  Não houve alteração de produção nem relaxamento global das verificações.
- Gate integral, UI/HTTP e avaliação dos casos reservados não foram executados;
  pertencem às etapas posteriores, não são validações obrigatórias de E10. Os
  defeitos conhecidos acima continuam abertos e não foram transformados em aceite.

```powershell
.venv/Scripts/python.exe tmp/rede-1256407599/e10/audit.py
.venv/Scripts/python.exe tmp/rede-1256407599/e10/performance.py
.venv/Scripts/python.exe tmp/rede-1256407599/e10/verify_geometry.py
.venv/Scripts/python.exe -m pytest tests/unit/test_benchmark_network_pdf.py tests/unit/test_smoke_examples.py tmp/rede-1256407599/e10/test_audit_local.py -q -p no:cacheprovider --basetemp tmp/rede-1256407599/e10/pytest-verified
.venv/Scripts/python.exe -m ruff check scripts/benchmark_network_pdf.py tests/unit/test_benchmark_network_pdf.py
.venv/Scripts/python.exe -m ruff format --check scripts/benchmark_network_pdf.py tests/unit/test_benchmark_network_pdf.py
.venv/Scripts/python.exe -m mypy --cache-dir tmp/rede-1256407599/e10/mypy-full
git diff --check
git check-ignore tmp/rede-1256407599/e10/inventory.json tmp/rede-1256407599/e10/audit.json tmp/rede-1256407599/e10/run-1.json 'examples/PROJETO DE REDE 1256407599.pdf'
```

O manifesto `evaluation-split.json`, criado por `freeze_split.ps1`, reserva três
famílias sintéticas distintas, nove sementes fixas (H01/H02/H03), para gerar e avaliar
somente depois de congelar métodos. Há dois documentos integrais candidatos à
reserva; como seu histórico em outras sessões é desconhecido, auditar exposição
antes de chamá-los de avaliação cega. Eles não foram abertos em E10. A reserva
sintética não depende desses candidatos. Os dois PDFs conhecidos são ajuste e
regressão, vinculados às referências E01/E08 e E10, sem reclassificar histórico como
teste cego. Nenhum caso reservado foi usado para calibrar a instrumentação.

E11 recebe os dois conflitos, não somente o cabo: rastrear aparência/oclusão e
cópia ampliada, preservar ambas as versões e exigir decisão técnica conforme a
política acima. Incluir controles de fotos, assinatura, CHI, regulador, Stamp não
técnico, Ink, Square e SHX. Não promover o carimbo de revisão. E12/E13 recebem neutros
N-4, transformador, chave descartada, associação U1/P5 e qualificadores. E14 recebe
endpoints invertidos, identidade por cabo e guarda que suprime existentes. E15
recebe as perdas documentais e de exportação, inspeção HTTP/Qt, avaliação reservada
e gate integral. E08/E09 mantêm seus estados anteriores. Sem commit ou ação externa.

