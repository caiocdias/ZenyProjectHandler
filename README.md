# Zeny Project Handler

Aplicativo desktop para organizar, visualizar e analisar projetos de expansão da rede de
distribuição elétrica. O programa mantém o PDF original intacto, extrai evidências nativas e por
OCR, propõe elementos técnicos e apresenta verificações de conformidade rastreáveis.

O produto está em desenvolvimento. Os PDFs de `examples/` mostram a direção desejada para a
análise, mas comentários de comissionamento não são tratados automaticamente como normas.

## Instalar e abrir

Requisitos: Windows e Python 3.11, 3.12 ou 3.13.

Na primeira execução:

```powershell
.\setup.bat
```

O setup cria `.venv`, instala as versões de `requirements.lock` e tenta preparar o Tesseract com o
idioma português. Uma falha apenas no OCR não desfaz o ambiente Python já instalado; a aplicação
continua disponível com a extração nativa de PDFs.

Abra sem console com duplo clique em `ZenyProjectHandler.vbs`. Para diagnóstico pelo terminal:

```powershell
.\ZenyProjectHandler.bat
```

## Fluxo principal

1. No painel **Projeto**, crie ou abra um projeto.
2. Adicione um ou mais PDFs. Os arquivos originais permanecem somente leitura.
3. Ajuste a ordem das folhas, se necessário.
4. Clique em **Analisar projeto**.
5. Confira os elementos e vãos em **Resultados** e navegue para a evidência no PDF.
6. Em **Documentação e conformidade**, execute as verificações disponíveis.

Resultados automáticos são propostas auditáveis. Informações ambíguas ou sem contexto suficiente
permanecem como não avaliáveis e não são apresentadas como certeza técnica.

## Regras de conformidade

O painel de regras permite somente:

- importar um registro JSON;
- exportar o registro ativo.

Não existe ação de remoção. Uma importação pode atualizar uma regra pelo mesmo ID, mas IDs atuais
omitidos são preservados. A persistência e a restauração de backup aplicam a mesma proteção.

As oito regras distribuídas hoje cobrem apenas fatos que o pipeline consegue produzir com segurança.
Novas famílias identificadas nos projetos comissionados permanecem no
[`catálogo de regras`](docs/catalogo-regras-conformidade.md) até existir fonte normativa e evidência
confiável para automatizá-las.

## Projetos locais em `examples/`

`examples/` é uma bancada local e dinâmica. Coloque, substitua ou remova PDFs quando quiser; não há
manifesto, cadastro por hash, partição privada nem congelamento. Todo o conteúdo da pasta, exceto seu
README, é ignorado pelo Git e não vai para o GitHub.

Para executar o smoke somente leitura em todos os PDFs locais:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_examples.py
```

Esse smoke procura PDFs recursivamente, abre, renderiza, extrai e interpreta cada arquivo sem fixar
contagens específicas. Quando um exemplo revela uma regressão, o comportamento mínimo relevante deve
virar uma fixture sintética e versionável. Assim os testes continuam determinísticos sem burocratizar
os documentos usados durante o desenvolvimento.

Veja [`examples/README.md`](examples/README.md) para a política completa, que é deliberadamente curta.

## Testes e qualidade

Execute o gate padrão:

```powershell
.\IniciarTestes.bat
```

Ele verifica dependências, Ruff, formatação, Mypy, testes públicos, cobertura e complexidade. O gate
não depende de arquivos em `examples/`; os testes de comportamento usam PDFs sintéticos pequenos.
O relatório local é salvo em `relatorio-testes.txt` e também é ignorado pelo Git.

Comandos individuais:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest --cov
```

## Dados, transporte e backup

Por padrão, banco e arquivos gerenciados ficam em
`%LOCALAPPDATA%\ZenyProjectHandler`. Defina `ZENY_DATA_DIR` para usar outro diretório.

- Projetos podem ser importados e exportados como `.zphproj`.
- Backups abrangem o banco e os arquivos gerenciados.
- PDFs externos continuam no local escolhido pelo usuário; removê-los do projeto não apaga o
  original.
- A importação valida caminhos, tamanho, tipo e SHA-256 dos arquivos do pacote.
- Restaurações compensam falhas capturadas. Como não há journal durável entre todos os recursos,
  uma interrupção abrupta do processo durante a troca não deve ser chamada de transação atômica.

## OCR

O pipeline usa primeiro texto, vetores, imagens e anotações nativas. O OCR local entra apenas quando
necessário. O idioma português vem de `tesseract-ocr/tessdata_fast`, revisão
`65727574dfcd264acbb0c3e07860e4e9e9b22185`, SHA-256
`c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb`, licença Apache-2.0.
Detalhes de terceiros estão em [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Estrutura e documentação

O código usa domínio independente, casos de uso, portas, adaptadores e interface Qt. Essa separação é
mantida onde protege testes ou troca de infraestrutura; não é requisito criar uma abstração para cada
função interna.

Documentos mantidos:

- [`docs/especificacao-funcional.md`](docs/especificacao-funcional.md): comportamento do produto e
  modelo de domínio;
- [`docs/modelo-entidades.mmd`](docs/modelo-entidades.mmd): visão estrutural;
- [`docs/roadmap-desenvolvimento.md`](docs/roadmap-desenvolvimento.md): estado atual e próximos
  incrementos;
- [`docs/arquitetura-conformidade.md`](docs/arquitetura-conformidade.md): funcionamento do motor de
  fatos e regras;
- [`docs/catalogo-regras-conformidade.md`](docs/catalogo-regras-conformidade.md): regras operacionais
  e candidatos;
- [`docs/adr`](docs/adr): decisões arquiteturais que ainda explicam o código atual.

Histórico detalhado de implementação, comandos já executados e prompts antigos pertencem ao Git, não
aos documentos vivos.

## Limites atuais

- Os exemplos comissionados ainda possuem expectativas sem cobertura automática integral.
- O provedor real de prova para a exceção de vãos entre 45 e 60 m ainda não existe; sem prova, o
  resultado é não avaliável.
- Cálculos mecânicos, ângulos e algumas consistências entre desenho, orçamento e anexos ainda exigem
  revisão humana.
- O empacotamento para uma máquina sem Python continua como etapa futura.
