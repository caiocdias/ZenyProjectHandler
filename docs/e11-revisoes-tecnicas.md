# E11 — Revisões técnicas e conteúdo vigente

Execução em 14/09/2026 sobre `c85bebe`. Git inicialmente limpo, sem `AGENTS.md`
aplicável. E10 concluída em índice/detalhe, inventário e política conferidos em
`e10-referencia-segundo-pdf.md`. O commit posterior ao início da E10 contém sua
instrumentação/documentação, sem alteração do pipeline. E08/E09 mantêm seus estados.

## Implementação e decisões

- `pymupdf_revisions.py` compara pixels na região de um rótulo ABCN/N1–N4 tocado
  por anotação e extrai a aparência visível em recorte separado. Guarda literal base,
  leitura OCR visível, PNGs, máscara de pixels alterados, hashes, página, xrefs,
  cores/traços e grupo ligado ao conteúdo da fonte. Diferença de pixels demonstra
  sobreposição, não autoridade. O raster semântico continua `annots=False`.
- `pymupdf_page_extractors.py`: o PyMuPDF 1.28 instalado inclui FreeText/Stamp em
  `get_text()`. A lista de exibição sem anotações elimina essa origem falsamente
  nativa. Coordenadas são extraídas sem rotação e normalizadas após restaurá-la em
  memória, como no leitor da biblioteca; nenhum arquivo é salvo/modificado.
- `technical_revisions.py`, `rule_based.py` e `automatic_promotion.py` vinculam o
  conflito à proposta antes da promoção. Evidência de anotação continua excluída dos
  analisadores de categoria; não nasce um segundo ativo por OCR da revisão. A imagem
  repetida de um Stamp conserva os xrefs das representações, sem nova ocorrência.
- `human_review.py`: a escolha da camada exige responsável e motivo. É independente
  da criação do ativo e pode ficar concluída com catalogação pendente. A decisão
  preserva as alternativas, data e versão; reanálise só a transfere para grupo,
  categoria e código base iguais. O grupo incorpora hash integral da fonte e rasters;
  mudança de conteúdo não herda autoridade. Um ativo já confirmado não é recriado.
  A visão vigente retira alternativas legadas com a mesma categoria, código base e
  geometria quando não pertencem à decisão atual; o agregado persistido e suas
  relações históricas permanecem intactos. Salvar a escolha também avança a versão
  do projeto, protegendo consumidores concorrentes.
- `review.py`, `review_api.py` e `review_panel.py`: campo opcional de conflito,
  concorrência pela sessão corrente, comparação dos dois recortes e seleção inicialmente
  pendente. O cliente apresenta dados do servidor, sem interpretar PDF ou catálogo.
- `deliverable_exports.py`: seis colunas aditivas após as existentes em Elementos,
  com grupo, base, visível, decisão, valor efetivo e hash. Pendente tem valor efetivo
  vazio. A auditoria distingue a escolha da camada da confirmação do ativo.

## Compatibilidade e persistência

Extrator **1.15.0**, interpretador **23.0**, API/piso **1.5.0**. O cache inclui a
versão/capacidade e hash da fonte; o hash abrange conteúdo e aparências de anotações.
A sessão semântica muda ao persistir a decisão. Falha OCR de revisão mantém a
comparação pendente, produz diagnóstico e impede gravar cache como leitura completa.
Falha de renderização da comparação falha a análise, sem promover valores encobertos.

Os JSONs dos payloads atuais guardam `revisao_tecnica`; não há Alembic, backfill ou
migração de produção. Campos ausentes em sessões antigas não significam aprovação.
Histórico existente permanece intacto. As constantes dos scripts de release estavam
em 1.3 e foram sincronizadas com a API atual; nenhum artefato foi publicado.

Rollback exige restaurar cliente/servidor compatíveis juntos e preservar o banco/cache
novos. Versões anteriores não entendem a política; não devem reanalisar/promover esses
grupos. Uma restauração operacional deve usar backup anterior, mantendo o banco novo
como histórico consultável. Não apagar decisões para permitir downgrade.

## Evidência real e limites

Fonte privada `examples/PROJETO DE REDE 1256407599.pdf`, SHA-256
`0793c292df9722ff48df31ab052018d4233ad3541706f50f53e994cc1670af06`.
O benchmark confere hash, tamanho e mtime antes/depois. Artefatos ficam ignorados em
`tmp/rede-1256407599/e11/`; nenhum dado privado entra nas fixtures públicas.

D01 passa a apresentar base `ABCN-35(70)` e aparência `ABCN-16(16)`, sem confirmar
nenhuma alternativa automaticamente. O catálogo atual não contém `ABCN-16(16)`;
não foi inventado/substituído um item. A escolha humana pode registrar esse literal,
mas a criação do ativo aguarda catalogação. Não foi tomada decisão técnica sobre a
fonte privada nesta implementação.

N4 tem comparação e conflito explícitos; remover/instalar não são deduzidos da mera
presença de N4 no OCR. A escolha revisada permanece indisponível enquanto as operações
estiverem indeterminadas, mantendo a base como alternativa, nunca confirmação silenciosa.
A imagem compartilhada pelos xrefs 138/146 identifica a ampliação. Reconhecimento das
operações pertence a E12/E13; sua pendência não foi convertida em ativo aprovado.

A detecção desta etapa cobre os rótulos ABCN/N1–N4 dos conflitos E10. Não homologa
todas as classes de anotações nem a leitura integral da folha. D02/D03/D05/D06 e os
estratos documentais continuam com as etapas seguintes; denominadores E10 preservados.

## Validações e handoff

Concluída em 14/09/2026 após aceite dos três critérios E11, auditoria D01 e validações
abaixo. Nenhum teste obrigatório ficou pendente. Não houve commit ou publicação.
Testes novos usam `create_e11_revision_pdf` e não usam famílias reservadas da E10.
Cobrem sobreposição, comentário, foto, assinatura, carimbo, Ink, SHX, quatro rotações,
falha/ausência OCR, decisão explícita, reabertura, reanálise, concorrência HTTP,
catalogação ausente, projeção Excel e comparação Qt.

Falhas encontradas e corrigidas durante desenvolvimento: chaves repetidas entre
traços do mesmo grupo; conversão da TextPage da biblioteca; fixture que contava texto
de comentário como nativo; fixture de exportação que dependia desse comentário;
seleção inicial de projeto na fixture Qt; expectativas de versão e tipagem estática.
Essas execuções intermediárias não constituem aceite.

| Comando/verificação | Resultado final |
| --- | --- |
| `.\IniciarTestes.bat` | Saída 0; **1.265 testes aprovados**, 462,02 s; cobertura **87,78%**, mínimo 85,01% |
| `python -m pip check` (no gate) | Dependências íntegras |
| `python -m ruff check .` e `python -m ruff format --check .` | Aprovados; 354 arquivos formatados |
| `python -m mypy` (no gate) | Aprovado; 337 arquivos |
| `python scripts/client_artifact_gate.py --source-only` (no gate) | Aprovado |
| `python scripts/complexity_gate.py src` (no gate) | Aprovado; 2.783 funções/métodos, nenhum E/F |
| `python scripts/generate_openapi_v1.py` | Snapshot regenerado; testes de contrato aprovados no gate |
| `python -m pytest tests/integration/test_review_panel.py -q -p no:cacheprovider --basetemp tmp/e11-ui-final` | 16 aprovados em 7,90 s após ajuste final do texto de motivo obrigatório |
| `git diff --check` | Aprovado |

`python` acima é `.\.venv\Scripts\python.exe`. O gate inclui todos os módulos da
validação obrigatória E11 (`test_pymupdf_analyzer`, `test_rule_based_interpreter`,
`test_analysis_cache`, `test_human_review`, `test_review_api`, `test_deliverable_exports`),
as novas regressões em `test_technical_revisions`, os contratos e o painel alterado.
Logs: `relatorio-testes.txt` e `tmp/e11-canonical-gate.log`. A única alteração de código
posterior ao gate foi o placeholder do motivo no painel: passou de opcional para
obrigatório na revisão técnica, sem alteração de lógica. Os 16 testes do painel,
inspeção visual da captura e Ruff foram repetidos depois desse ajuste.

A primeira suíte manual com `--basetemp tmp/e11-all` terminou com 14 falhas e 1.247
aprovações (86,55%): 11 erros de caminho longo no Windows, uma diferença de fonte Qt
induzida por `QT_QPA_FONTDIR` e duas fixtures desatualizadas (smoke/orientação).
As fixtures foram corrigidas; o gate canônico usou ambiente Qt padrão e raiz curta
`C:\tmp\zph-basic-24132`, como definido no script. Os 25 testes de portabilidade também
passaram isoladamente em 24,22 s. O resultado válido de aceite é o gate final aprovado,
não a execução manual com falhas. A formatação do último placeholder foi ajustada e
reverificada sem pendência.

### Handoff para E12/E13

- Reutilizar os grupos e a proveniência de E11 ao melhorar leitura/associação; não
  transformar `authority=nao_comprovada` em aprovação pela confiança do OCR.
- Resolver operações de N4 e catalogação literal de `ABCN-16(16)` com evidência,
  mantendo escolha de camada separada de criação/confirmação do ativo.
- Ampliar classes de revisão apenas com controles sintéticos, sem usar os casos
  reservados E10 como ajuste de heurística. Altura de anotação não substitui comprimento.
- Não há bloqueio remanescente de E11, migração SQL ou alteração da fonte. O aceite
  integral E15 e as pendências anteriores E08/E09 continuam com seus estados próprios.

### Reprodução da auditoria D01

Executar na raiz do checkout, com o runtime OCR privado preparado na E10:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_network_pdf 'examples/PROJETO DE REDE 1256407599.pdf' --output tmp/rede-1256407599/e11/frozen-benchmark.json --runtime-directory tmp/e01/runtime --telemetry
.\.venv\Scripts\python.exe tmp/rede-1256407599/e11/verify_e11.py
```

Ambos concluíram com código zero. A verificação privada exige dois grupos conflitantes,
nenhuma promoção desses grupos, literais D01 exatos, máscara/rasters distintos,
autoridade não comprovada, representação N4 138/146 e igualdade de hash/tamanho/mtime.
O script local e `verified-audit.json` ficam junto ao benchmark ignorado; os testes
públicos reproduzem a política com dados sintéticos, sem depender desse script.
Os recortes `d01-base.png` e `d01-visible.png` foram inspecionados em resolução legível.

Resultado: 2.047 evidências (1.797 vetores, 19 imagens, 3 textos nativos, 228 OCR),
48 propostas brutas, 38 finais, 48 relações propostas, 9 confirmações, 11 regiões,
7 vãos, zero diagnósticos e 85 chamadas OCR. Dois grupos permanecem conflitantes.
Os 106,320 s do pipeline e 109,171 s incluindo exportação são telemetria de execução
simultânea ao gate, sem comparação de desempenho isolado e sem critério temporal de aceite.
Os denominadores e metas integrais da E10 permanecem reservados às etapas seguintes.
