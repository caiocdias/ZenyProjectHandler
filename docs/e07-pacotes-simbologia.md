# E07 — Pacotes declarativos de simbologia

Esta etapa registra cada variante E07 do [inventário E01](data/inventario-simbologia-v1.json)
em um pacote JSON por família. O [esquema](schemas/pacotes-simbologia.schema.json)
e `declarative_symbols.py` distinguem variantes com gramática executável de células
pendentes. Cadastro documental, observação de forma e confirmação de ativo são
decisões distintas. O método é opt-in; não altera o reconciliador nem o consumidor
patrimonial.

## Contrato

Cada pacote declara `family_id`, `profile_id`, `source_id` e variantes com ID,
classe aberta, destino, papel, localizador da fonte e um dos estados:

- `enabled`: gramática vetorial concreta e exemplos negativos; só este estado
  entra em `classes_suportadas` e pode emitir uma observação E03.
- `pending`: motivo verificável e exemplos confundíveis; não emite reconhecimento.

O loader rejeita campos/gramáticas desconhecidos, IDs repetidos, fonte divergente,
papel incompatível com destino e estados falsos. O perfil assina o conteúdo dos
pacotes, portanto mudanças de dados alteram a identidade do método. Novas famílias
podem ser acrescentadas por um arquivo JSON conforme o esquema, sem alterar o
reconciliador. O escopo ativo atual é PDF vetorial com texto e primitives na base;
anotações, raster e semântica de legenda local exigem as etapas posteriores.

`observar_pacotes(...)` devolve `ResultadoMetodoSimbolos`: fonte/hash, geometria,
primitives, ID E01, fonte/localizador, papel, destino e cobertura. O score bruto
é `None`; não é probabilidade. `papel=informative` permanece informativo mesmo
quando uma forma casa com a gramática. Nenhuma observação desta etapa vira ativo
por si só. `contexto=unknown` exige revisão; na projeção diagnóstica E02, a classe
operacional vai ao bucket operacional para não apagar candidatos exclusivos, com
o contexto original preservado na procedência. Exemplares de legenda podem,
portanto, aparecer como FP diagnosticável; isso não é promoção patrimonial.
O fallback `regioes_desconhecidas` requer regiões de formas fechadas fornecidas
explicitamente pelo chamador e emite alternativa `classe=None`. Ele preserva
um candidato revisável sem aumentar a cobertura reconhecida do inventário;
não faz varredura irrestrita de todos os desenhos da página.

## Auditoria e execução

```powershell
.\.venv\Scripts\python.exe -m scripts.audit_symbol_packages --output tmp/e07-simbologia/package-audit.json
.\.venv\Scripts\python.exe -m scripts.audit_symbol_packages --source-pdf tmp/e07-simbologia/reference/IT-EO-008_Simbologia_EO.pdf --output tmp/e07-simbologia/source-audit.json
.\.venv\Scripts\python.exe -m scripts.audit_symbol_packages --require-complete
.\.venv\Scripts\python.exe -m scripts.benchmark_packages_e07 --output tmp/e07-simbologia/benchmark
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols synthetic --include-transformers --include-guys --include-packages --output tmp/e07-simbologia/baseline
.\.venv\Scripts\python.exe -m scripts.benchmark_symbols examples --root examples --include-transformers --include-guys --include-packages --output tmp/e07-simbologia/predictions
```

O primeiro comando confere IDs, fontes, localizadores e papéis contra o
inventário; `--require-complete` só termina com saída zero se não houver variantes
pendentes. `--source-pdf` é opcional e exige uma cópia local da fonte F02;
compara seu SHA-256 ao inventário e verifica as páginas de todos os
localizadores. O corpus sintético E02 mede regressão e composição, mas não contém
positivos para todos os pacotes E07. Testes autorais por gramática e a auditoria
visual independente dos PDFs locais complementam o V-B. As predições são salvas
antes de qualquer comparação com a referência visual. A reserva sintética E16
permanece lacrada; PDFs de `examples/` já inspecionados são desenvolvimento.
O loader e testes de mutação validam os dados atuais. A validação independente
com `jsonschema==4.25.1` (Draft 2020-12) passou para o esquema e os 27 pacotes,
incluindo a rejeição de 13 mutações inválidas no checkpoint atual. O validador foi instalado
somente em `tmp/e07-simbologia/jsonschema-validator`, sem alterar as
dependências do projeto; o relatório está em `tmp/e07-simbologia/jsonschema-gate.json`.

O [roadmap](roadmap-analise-simbologia.md)
contém contagens finais, comandos/resultados, delegações, V-P e pendências.

## Estado A5

O denominador E01 desta etapa é **365 variantes em 27 famílias**, incluindo
quatro reguladores de §18 cuja família principal pertence a E05. Há **12
gramáticas habilitadas em oito famílias** e **353 variantes pendentes**;
19 famílias não têm nenhuma gramática habilitada. O benchmark autoral A5 cobriu
as 12 variantes habilitadas em 58 páginas (12 positivos, 46 negativos):
12 TP, 0 FP, 0 FN e 0 duplicatas. O gate `--require-complete` retorna 1 por
essas 353 pendências; E07 não atende ao aceite integral. O conjunto de PDFs
locais não substitui os positivos/negativos faltantes das famílias pendentes.

## Continuação de 23/09/2026

A fonte oficial F02 foi conferida localmente: SHA-256
`0e29f0ea81827c7235d0893c383fc993c78378c51e930b8b8228de82d564ce04`,
45 páginas, e os 365 localizadores E07 dentro do documento. A revisão visual
das páginas 6–45 mapeou as 27 famílias; o mesmo glifo aparece em IDs e famílias
distintos. Nas páginas F02 p9–14 e p27–33 testadas com o runner, os símbolos
relevantes estão incorporados como imagens e não produziram positivos vetoriais.
A seção 33 declara seus
89 desenhos sem conectividade elétrica e excluídos da publicação; esses
registros permanecem informativos mesmo quando imitam equipamentos.

Gramáticas para três câmaras CT/CL/CM, dois símbolos de plataforma e quatro
conjuntos em painel cinza elevaram a cobertura a **21 variantes habilitadas em
dez famílias**. As outras **344 variantes**, incluindo 17 famílias sem gramática,
mantêm motivo de pendência e não contam como reconhecimento. Os negativos
incluem X de retirada, preenchimento incompatível e colisões com torre e
outros quadros. O benchmark autoral atual tem 23 casos com predição esperada,
95 negativos vazios e 23 TP/0 FP/0 FN/0 duplicatas. Há 21 positivos diretos
e duas páginas em que o negativo de preenchimento da variante alvo é positivo
válido para a variante irmã.

O runner de benchmark agora usa um único snapshot dos pacotes em toda a
execução e marca `package_configuration_unchanged=false` se arquivos de dados
mudarem durante a inferência. O V-P final inspecionou os 11 PDFs/11 páginas de
`examples/`: zero falhas, 237 predições E04/E05 idênticas ao checkpoint A5 e
zero E07. Isso não demonstra recall E07 em projetos reais; o corpus não contém
positivo inequívoco das gramáticas habilitadas. `--require-complete` retorna 1
pelas 344 pendências, de modo que E07 continua sem aceite integral.
