# E13 — Ocorrências e associação aos pontos corretos

Execução em 16/09/2026 sobre `f990c1b`, Git inicialmente limpo. Nenhum `AGENTS.md`
encontrado no repositório ou ancestrais. Roadmap, D02–D05, E10/E12A/E12B, ADR 0015,
intérprete, promoção e regiões conferidos. E12B está concluída e integrada em
`f990c1b`; E08/E09 permanecem bloqueadas, sem correção posterior de seus bloqueios.
A divergência histórica 1.14.0/22.0 do diagnóstico corresponde às entregas E11–E12B;
a base efetiva desta execução era extrator 1.17.0 e interpretador 23.0. A tabela
funcional também foi reconciliada com a API/piso 1.5.0 já existente; nenhum contrato mudou.

**Resultado:** critérios específicos de E13 aprovados; interpretador **24.0**.
Não há aceite integral do documento, da topologia ou dos modelos não resolvidos.
As 139 referências E10 foram preservadas, sem alterar denominadores ou usar os
casos reservados H01/H02/H03. Não houve commit, publicação, migração ou consulta SQL real.

## Implementação e decisões

- `adapters/interpretation/occurrence_rules.py`: consolida leituras de cabo pela
  combinação código/tipo, situação, traçado, identificador, comprimento, origem PDF
  e sobreposição do rótulo. Preserva IDs das leituras consolidadas e união das
  evidências. Traçado comum, distância ou igualdade de comprimento não bastam.
- `rule_based.py`: aplica a consolidação antes de relações/promoção. Estruturas
  usam sobreposição da ocorrência, substituindo a tolerância entre centros que
  podia fundir rótulos físicos próximos. Identidade de tokens da mesma fonte continua
  distinta. Grupos de ponto também respeitam o contexto sem numeração.
- `category_analyzers.py`: separa extensões de tokens repetidos ao longo da linha
  OCR; conserva fonte/offsets. Recupera `N-4` como literal sem completar CA/CAA.
  Reconhece `TR-<fases>-<capacidade>` com código e capacidade observados, sem escolha
  arbitrária de modelo. Analisadores de estrutura/cabo/equipamento: 2.1/4.2/3.4.
- `operational_labels.py`: a legenda conjunta de poste/estrutura sustenta contexto
  sem P quando não há identificador local. Componentes próximos com contexto
  inequívoco usam essa evidência; empate fica pendente, sem recorrer ao P distante.
  Não cria ponto de domínio, coordenada, modelo ou nome U1/P6. U1 é apenas o nome da
  referência de avaliação. Equipamento literal descartado pelo filtro continua
  visível, conflitante e sem vínculo presumido.
- `relation_rules.py`: instalação não atravessa contextos; propostas com associação
  pendente não geram vínculos. As estratégias de extremidades mantêm seus próprios
  critérios, sem suprimir por regra geral o suporte sem número dos cabos existentes.
- `analysis_regions.py`: contexto próprio não herda P5 nem é unido à sua região.
  Equipamentos de associação pendente permanecem separados de regiões numeradas.
- `application/technical_revisions.py`: mantém base N4 e acrescenta operações da
  aparência colorida, com texto, caixa, xref e identidade próprios. Vermelho exige
  risco horizontal. Fragmentos e passagens tratadas permanecem no envelope original;
  leituras da mesma operação não multiplicam ativos. Qualificadores discordantes e
  operações em caixas distintas não são fundidos. Todas exigem decisão técnica.
  Preservação de decisão exige a mesma identidade de operação, além do grupo/código.
- A promoção existente já bloqueia revisão técnica, conflito E12B, associação e
  reconciliação de reanálise pendentes; suas guardas foram mantidas e testadas.
  Não foi necessário modificar `automatic_promotion.py` nem contratos/codec/banco.
- `scripts/experiments/compare.py`: avalia a representação nova de contexto sem
  número pela legenda de poste inventariada, código/situação, evidência referenciada
  e contexto compartilhado. Não aceita somente retirar P5 ou apontar para geometria
  próxima. A referência continua separada da inferência de produção.

## Reconciliação por ocorrência

| Ocorrência | Resultado final e evidência | Limite preservado |
|---|---|---|
| D02 / C-V2-3-1 | Uma proposta/confirmado `N-(1N5)`, 100 m; duas leituras e mesmo traçado preservados | Fase e demais cabos não fundidos; identidade de endpoints é E14 |
| N3 físicos de P1 / A07–A08 | Duas ocorrências `N3(1)` em geometrias distintas, incluindo leitura da linha com ambos os tokens | Qualificador não vira quantidade |
| D03 / A06, A12, A18, Q2 | `10-300`, `N2`, `S3R`, `100A-10kA-1H` no contexto da legenda `N2-10-300`; nenhum recebe P5 | Não escolhe formato/material de poste; contexto não cria endpoint |
| D04 / R02 | Base N4 existente e duas alternativas `N4(1)` instalar/remover, caixas distintas e todas conflitantes | Autoridade/vigência pendentes; representação ampliada não vira outro ativo |
| D05 / Q1 | `TR-3-45`, fases 3, capacidade observada 45 kVA, evidência textual e contexto P3 | Modelo não resolvido, sem promoção |
| C-T36-1 e C-T83-1 | Dois `N-4` com rótulos/traçados próprios, sem completar nomenclatura | Catálogo pendente; projeção/identidade dos trechos em E14 |
| Q3 | `100A-10kA-3H` agora preservado com a própria geometria; sem P nem relação automática | Associação exige revisão; E10 já exclui classe/situação completas por convenção técnica insuficiente |
| R01 | Conflito base/revisão do cabo preservado e não promovido | E13 não decide vigência |

O JSON privado `audit-final.json` contém as **139 linhas E10**, a avaliação individual
das 29 ocorrências do núcleo, IDs/fontes/geometrias de cada equipamento, propostas
D02–D05 e os resultados de ambos os métodos. Os outros estratos permanecem explicitamente
fora da métrica do núcleo, sem serem classificados como acerto por ausência de avaliação.

## Comparação de associação, sem ranking temporal

Mesmas evidências E12B no baseline e benchmark novo com Tesseract real; grafo E12A
executado novamente sobre cada snapshot, sem promoção de suas hipóteses.

| Método | TP | FN | FP | Precisão | Recall |
|---|---:|---:|---:|---:|---:|
| Baseline 23.0 | 24 | 5 | 4 | 85,71% | 82,76% |
| Grafo E12A sobre baseline | 18 | 11 | 3 | 85,71% | 62,07% |
| E13 24.0 | 29 | 0 | 0 | 100% | 100% |
| Grafo E12A sobre E13 | 20 | 9 | 2 | 90,91% | 68,97% |

Essas métricas exigem código/qualificador, situação e contexto/traçado corretos nas
**29 ocorrências elegíveis**, não modelos completos, equipamentos, documentação ou
topologia. Baseline reproduziu exatamente 24/5/4 antes da comparação. O grafo mantém
regressões A03/A10/A15 em P3 e seis cabos; permanece experimental. Ganho de U1 não
justifica substituir a associação de produção nem confirmar por acordo entre métodos.
Os conflitos E12B sobrevivem pela união de evidências, com regressão específica que
coloca a discordância na leitura descartada pela consolidação.

## Benchmark, promoção e inspeção

Final `benchmark-final.json`: 2.065 evidências, 246 OCR, 53 propostas brutas,
**43 finais, 47 relações, oito confirmações, 13 regiões, seis linhas de Vãos** e
zero diagnósticos. Exportação de Resultados/Documentação conferida pelo benchmark.
As oito confirmações são cabos; o erro conhecido de duplicação cai de **1/9 para 0/8**.
Isso não afirma correção integral dessas confirmações: endpoints e projeções ainda
dependem de E14. As duas alternativas N4, os dois neutros não catalogados, Q1 e Q3
não representam confirmação automática adicional.

Auditoria dos **nove equipamentos**: Q1/Q2/Q3 usam suas caixas textuais corretas;
três propostas de aterramento/para-raios em P3, um aterramento em P1 e dois símbolos
no contexto existente correspondem às fontes vetoriais preservadas. São seis
propostas simbólicas, sem homologação do tipo exato e sem promoção. Inspecionadas as
nove caixas no mosaico privado `equipment-geometry.png`, além dos recortes de
V2-3, P3 e P1/P5/rede existente. Caixas textuais não foram substituídas por símbolos
próximos. Os defeitos simbólicos do primeiro PDF em E08/E09 não foram declarados resolvidos.

Fonte preservada: 988.018 bytes, SHA-256
`0793c292df9722ff48df31ab052018d4233ad3541706f50f53e994cc1670af06`, tamanho e mtime
iguais antes/depois. Tudo privado em `tmp/rede-1256407599/e13/` e ignorado no Git.
Benchmark final: 145,173 s até regiões/vãos, 148,356 s incluindo Resultados/XLSX.
Tempo é observabilidade, nunca critério de escolha ou corte. A primeira rodada real
também concluiu; a final foi repetida após reforços de identidade e regiões.

## Validações

**147 testes aprovados em 15,20 s**, incluindo os seis arquivos obrigatórios E13,
19 regressões novas de ocorrências e uma integração de deduplicação/reanálise,
mais regressões E11/E12B e da alternativa E12A. Mypy aprovado em **348 arquivos**;
Ruff e formatação aprovados; complexidade aprovada em **2.834 funções/métodos**,
sem rank E/F. `git diff --check` aprovado. Gate público integral/cobertura e UI
integral não foram repetidos: continuam no aceite E15, sem alegação de homologação. Reinterpretação final das evidências reais confirmou
igualdade dos 43 IDs, atributos, fontes e geometrias com o benchmark; as nove
geometrias de equipamentos inspecionadas permanecem iguais.

As rodadas intermediárias detectaram um teste antigo que esperava descarte de
equipamento literal, seis fixtures novas sem `estado_revisao`, tipagem de retorno
`Any` e complexidade excessiva na função de relações. Expectativa atualizada para
preservar a proposta pendente; fixtures corrigidas; tipagem e função corrigidas
sem relaxar verificações. Todas essas falhas foram superadas nas validações finais.

Comandos na raiz, com Python da `.venv`:

```powershell
git status --short
git log -10 --oneline
.venv/Scripts/python.exe -m pytest tests/unit/test_e13_occurrences.py tests/unit/test_rule_based_interpreter.py tests/unit/test_e08_association.py tests/unit/test_analysis_regions.py tests/integration/test_interpretation_pipeline.py tests/integration/test_human_review.py tests/server/test_review_api.py tests/unit/test_technical_revisions.py tests/unit/test_method_reconciliation.py tests/unit/test_network_alternatives.py -q -p no:cacheprovider --basetemp tmp/e13-final
.venv/Scripts/python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e13/benchmark-final.json --runtime-directory tmp/e01/runtime --telemetry
$env:PYTHONPATH=(Get-Location).Path
.venv/Scripts/python.exe tmp/rede-1256407599/e13/audit.py
.venv/Scripts/python.exe -m ruff check src tests scripts/experiments/compare.py
.venv/Scripts/python.exe -m ruff format --check src tests scripts/experiments/compare.py
.venv/Scripts/python.exe -m mypy src tests scripts/experiments/compare.py --cache-dir tmp/e13-mypy-final
.venv/Scripts/python.exe scripts/complexity_gate.py src
git diff --check
```

Logs finais: `required-final-verified.log`, `benchmark-final.log`, `audit-final.log` e
`mypy-final.log`. Auditoria privada exige o inventário E10/baseline E12B local;
nenhum teste público depende deles, dos PDFs privados ou do runtime OCR real.

## Compatibilidade e handoff

Não há backfill nem edição de snapshots. A versão 24.0 invalida a identidade de
execução semântica antiga; na reanálise, folhas com decisões anteriores exigem
reconciliação antes de promover propostas novas. A sessão antiga, seus ativos e
decisões permanecem preservados, inclusive duplicatas históricas a reconciliar.
Não se transfere uma decisão da base N4 para instalar/remover ou entre essas operações.
Rollback para 23.0 não apaga histórico nem converte alternativas em fatos.

Arquivos públicos: módulos de interpretação e regiões descritos acima,
`occurrence_rules.py`, `technical_revisions.py`, comparador E12A,
`tests/unit/test_e13_occurrences.py`, `tests/unit/test_rule_based_interpreter.py`,
`tests/integration/test_interpretation_pipeline.py`, README, especificação, diagnóstico,
roadmap e este handoff. Não houve alteração no catálogo, extrator, cliente ou API.

E14 recebe os trechos existentes 36/83 m, endpoints/continuidade compartilhados,
o vínculo pendente Q3 e a comparação do grafo. O contexto textual U1 não é ainda
um nó topológico compartilhado; não reutilizar seus IDs de evidência como endpoint
por conveniência. E15 recebe homologação integral, classificação/revisão técnica,
equipamentos simbólicos, exportações completas, casos reservados e gate integral.
E08/E09 mantêm todos os bloqueios anteriores. Nenhum bloqueio dos critérios
específicos de E13 permanece; as limitações acima não foram convertidas em acertos.
