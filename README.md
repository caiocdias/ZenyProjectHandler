# Zeny Project Handler

Aplicativo desktop para organizar, visualizar e analisar projetos de expansão da rede de
distribuição elétrica. O Zeny mantém os PDFs de origem somente leitura, extrai evidências nativas e
por OCR, interpreta elementos técnicos e executa verificações de conformidade rastreáveis.

O projeto está em desenvolvimento e hoje é executado diretamente pelo código-fonte no Windows. Não
há instalador ou pacote de distribuição para máquinas sem Python.

## Estado atual

- Projetos locais com NS, múltiplos PDFs, ordem de folhas persistida, remoção de documentos e
  exclusão segura do projeto.
- Visualizador progressivo com paginação, zoom, rotação, tiles sob demanda e suporte a PDFs
  protegidos por senha. A senha existe apenas em memória durante a sessão.
- Extração de texto, vetores, imagens, anotações, Form XObjects e OCR Tesseract local quando
  necessário.
- Interpretação versionada de postes, estruturas MT/BT, cabos e equipamentos, além de relações entre
  os elementos. Resultados catalogados são promovidos automaticamente e continuam auditáveis.
- Revisão humana para aceitar, corrigir ou rejeitar propostas, criar elementos e relações manuais e
  navegar da lista até a evidência no PDF.
- Regiões de ocorrência e vãos derivados da análise, com controle independente de visibilidade dos
  elementos no desenho.
- Inspeção documental de cabeçalho, servidão, carimbos e campos de assinatura.
- Motor declarativo de conformidade com quatro famílias de provedores de fatos, snapshots
  persistidos e callouts vetoriais no PDF. O seed atual é
  `cemig-normas-distribuicao-2025.6`, com 39 regras habilitadas.
- Importação e exportação de projetos `.zphproj`, backup completo `.zphbackup`, validação de
  integridade e recuperação de operações interrompidas sobre arquivos gerenciados.
- Temas claro e escuro, painéis acopláveis e restauração do estado da interface.

As 39 regras são executáveis, mas um achado só é criado para alvos que satisfazem todas as condições
de aplicabilidade declaradas. Por isso o registro usa fatos de guarda para não aplicar uma obrigação
fora do subconjunto que o pipeline consegue caracterizar. Em um alvo aplicável, a ausência de um
fato declarado como requisito pode produzir divergência — por exemplo, quando a própria regra exige
a presença de um campo.

## Instalar e abrir

Requisitos:

- Windows;
- Python 3.11, 3.12 ou 3.13;
- acesso à internet na preparação inicial das dependências e, se necessário, do OCR.

Na primeira execução:

```powershell
.\setup.bat
```

O setup cria `.venv`, instala as versões de `requirements.lock`, instala o projeto em modo editável
e tenta preparar o Tesseract com português. Se apenas o OCR falhar, o ambiente Python já concluído é
preservado e a aplicação continua disponível com a extração nativa.

Abra sem console com duplo clique em `ZenyProjectHandler.vbs`. Para diagnóstico pelo terminal:

```powershell
.\ZenyProjectHandler.bat
```

## Fluxo de uso

1. No painel **Projeto**, crie ou abra um projeto usando a NS.
2. Adicione um ou mais PDFs e ajuste a ordem das folhas, se necessário.
3. Clique em **Analisar projeto** e acompanhe o progresso. A operação pode ser cancelada em um ponto
   seguro.
4. Use **Resultados** para inspecionar regiões, elementos, relações e vãos e localizar cada evidência
   no PDF.
5. Em **Documentação e conformidade**, confira os dados documentais, execute a conformidade e revise
   os callouts.
6. Use **Importar, exportar e backup** para transportar um projeto ou proteger todo o estado local.

O pipeline principal executa, em ordem, a extração documental, a interpretação semântica, a
promoção dos resultados e a conformidade. A ação **Analisar conformidade** reaplica as regras aos
resultados semânticos persistidos; ela não abre o PDF nem repete OCR.

## Dados e integridade

Por padrão, banco, logs, cache derivado, estado da interface e arquivos gerenciados ficam em
`%LOCALAPPDATA%\ZenyProjectHandler`. Use `ZENY_DATA_DIR` para escolher outra raiz.

- O SQLite é migrado automaticamente na inicialização.
- PDFs adicionados pelo fluxo normal permanecem no local escolhido e não são alterados nem apagados
  ao serem removidos do projeto.
- O aplicativo registra identidade, tamanho e SHA-256 da origem antes de analisar ou transportar o
  conteúdo.
- `.zphproj` transporta um projeto com seus dados auditáveis e arquivos disponíveis.
- `.zphbackup` protege o banco local completo, arquivos gerenciados e cópias verificadas dos PDFs
  externos.
- Pacotes validam manifesto, caminhos, tipos, tamanhos e hashes. Uma origem ausente, alterada ou
  ilegível só pode ser omitida depois de confirmação explícita e deixa o pacote marcado como
  degradado.
- A importação de projeto e a limpeza de arquivos possuem journals recuperáveis. A restauração de
  backup usa publicação atômica por arquivo e compensação para falhas capturadas; a troca conjunta
  de banco e anexos ainda não possui journal durável contra encerramento abrupto.

## OCR local

O pipeline prioriza conteúdo nativo do PDF. O Tesseract é usado localmente como fallback em páginas
ou regiões que precisam de reconhecimento raster; a ausência do OCR não impede os demais
extratores.

O modelo português provisionado vem de `tesseract-ocr/tessdata_fast`, revisão imutável
`65727574dfcd264acbb0c3e07860e4e9e9b22185`, com SHA-256
`c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb`. A licença é Apache-2.0 e os
avisos de terceiros estão em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Se o Tesseract estiver fora dos locais usuais, defina `ZENY_TESSERACT_PATH`. Para usar outro diretório
gravável de idiomas, defina `ZENY_TESSDATA_DIR` e execute novamente:

```powershell
.\.venv\Scripts\python.exe -m zeny_project_handler.tesseract_setup --provision
```

## Configuração

As opções são lidas na inicialização:

| Variável | Padrão | Uso |
|---|---:|---|
| `ZENY_DATA_DIR` | `%LOCALAPPDATA%\ZenyProjectHandler` | raiz dos dados locais |
| `ZENY_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` ou `CRITICAL` |
| `ZENY_PDF_RENDER_DPI` | `600` | teto de detalhe do visualizador, entre 36 e 600 DPI |
| `ZENY_PDF_RENDER_MAX_PIXELS` | `8000000` | limite de pixels por solicitação de renderização |
| `ZENY_PDF_RENDER_MAX_BYTES` | `67108864` | limite estimado de memória por solicitação |
| `ZENY_PDF_TILE_CACHE_MAX_BYTES` | `134217728` | limite do cache visual de tiles |
| `ZENY_TESSERACT_PATH` | descoberta automática | caminho do `tesseract.exe` |
| `ZENY_TESSDATA_DIR` | pasta gerenciada | diretório gravável de idiomas do Tesseract |
| `ZENY_BOOTSTRAP_PYTHON` | descoberta automática | Python usado por `setup.bat` |

As opções de renderização afetam somente o visualizador, não os parâmetros ou resultados da análise.

## Testes e qualidade

Execute o gate padrão:

```powershell
.\IniciarTestes.bat
```

Ele valida dependências, Ruff, formatação, Mypy, a suíte Pytest com cobertura e o limite de
complexidade ciclomática. A cobertura mínima configurada é superior a 85%. O relatório local é
gravado em `relatorio-testes.txt` e ignorado pelo Git.

Comandos individuais:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest --cov
```

Os testes normais usam fixtures sintéticas e não dependem dos PDFs locais de `examples/`. Para um
smoke opcional, somente leitura, sobre todos os exemplos disponíveis:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_examples.py
```

## Limites conhecidos

- O reconhecimento é determinístico e auditável, mas ainda depende da qualidade e das convenções do
  desenho; casos ambíguos continuam sujeitos à revisão humana.
- Cálculos elétricos ou mecânicos completos, autenticidade de assinaturas e validações que dependem
  de documentos restritos não são inferidos sem fonte e evidência suficientes.
- Algumas regras de pacote documental ou topologia permanecem não avaliáveis quando os anexos ou as
  associações necessárias não aparecem no projeto analisado.
- Ainda não há instalador, assinatura de executável nem validação de distribuição em uma máquina
  Windows limpa.

## Documentação

- [Especificação funcional](docs/especificacao-funcional.md): comportamento e limites do produto.
- [Modelo de entidades](docs/modelo-entidades.mmd): visão estrutural do domínio.
- [Arquitetura de conformidade](docs/arquitetura-conformidade.md): fluxo de fatos, regras, snapshots e
  callouts.
- [Catálogo de regras](docs/catalogo-regras-conformidade.md): as 39 regras do seed e suas fontes.
- [Inventário normativo](docs/inventario-fontes-normativas.md): documentos, revisões, hashes e escopo
  da auditoria normativa.
- [ADRs](docs/adr): decisões arquiteturais; textos substituídos são mantidos somente quando o status
  os identifica explicitamente como histórico.
- [Exemplos locais](examples/README.md): política da bancada de PDFs não versionados.

O código segue a separação entre domínio, casos de uso, portas, adaptadores e interface Qt. O
detalhamento histórico de implementação permanece no Git; a documentação viva descreve apenas o
comportamento vigente.
