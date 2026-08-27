# Zeny Project Handler — Kit servidor @RELEASE_VERSION@

Este kit é autocontido para o host de produção: ele contém a imagem Docker exportada, o Compose
sem build, a configuração de exemplo, este guia e a SBOM. O host não precisa e não deve receber o
checkout, Python, Qt, Tesseract ou o pacote cliente.

Imagem aprovada: `@IMAGE_REFERENCE@`  
ID/digest da imagem: `@IMAGE_DIGEST@`  
Arquivo para carga: `@IMAGE_ARCHIVE@`

Antes de operar, confira o SHA-256 do arquivo no `release-manifest.json`/`SHA256SUMS.txt` recebidos
por canal confiável. A extensão `.oci.tar` identifica o artefato de imagem da release; o conteúdo é
um archive Docker compatível com `docker load`.

## Instalação e início

O host precisa somente de Docker Engine/Desktop com containers Linux e Docker Compose v2.

```powershell
docker load --input .\@IMAGE_ARCHIVE@
docker image inspect @IMAGE_REFERENCE@
Copy-Item .env-example .env
```

Edite `.env`: substitua os placeholders de `ZENY_SERVER_PASSWORD` e
`ZENY_MARKET_SQLSERVER_CONNECTION_STRING`. A conexão ODBC é segredo; não a coloque no comando,
Compose, imagem ou ticket. `ZENY_MARKET_SQLSERVER_TIMEOUT_SECONDS` deve ser um inteiro positivo
(padrão `15`). Não altere `ZENY_SERVER_IMAGE`, salvo numa atualização/rollback conferidos. Para
clientes de outra máquina, defina `ZENY_SERVER_BIND_ADDRESS` com o IPv4 privado específico do
servidor.

```powershell
docker compose --env-file .env -f compose.release.yaml config --quiet
docker compose --env-file .env -f compose.release.yaml up -d --no-build
docker compose --env-file .env -f compose.release.yaml ps
```

O Compose nunca constrói imagem nem monta código-fonte. O volume nomeado `zeny-data` é a fonte de
verdade e sobrevive a restart, recreate e `docker compose down`.

## Cadastro SQL Server de mercado

O SQL Server de Notas de Serviço é a única fonte de `RURAL`/`URBANO`. Cada execução de
conformidade abre uma conexão curta, executa uma vez a consulta parametrizada
`SELECT NOTAS_COD_MERCADO FROM TB_NOTAS WHERE NOTAS_NUM_NS = ?;` e fecha cursor/conexão. Não há
cache, cópia no SQLite ou fallback por metadado/PDF.

Crie um login dedicado com permissão de conexão ao banco e somente `SELECT` sobre
`TB_NOTAS.NOTAS_NUM_NS` e `TB_NOTAS.NOTAS_COD_MERCADO`. Não conceda escrita, DDL ou administração.
A string ODBC deve usar Microsoft ODBC Driver 18, `Encrypt=yes` e
`TrustServerCertificate=no`. Instale a CA da organização na imagem por processo aprovado quando a
cadeia não for pública; não desative a validação de certificado. Confirme DNS/rota/firewall do
container até o SQL Server e o schema padrão que resolve `TB_NOTAS`.

Ausência, placeholder, timeout não positivo, NS sem linha, `NULL`, valor fora de
`RURAL`/`URBANO`, duplicidade ou falha ODBC encerram a conformidade sem snapshot parcial. Projetos e
snapshots já persistidos continuam consultáveis. O health HTTP prova somente o servidor Zeny; não
prova rede, TLS, permissão ou dados do SQL Server. Depois de uma mudança externa de mercado,
execute **Analisar conformidade** novamente para capturá-la em outro snapshot.

Na homologação E04, rode o smoke somente leitura dentro da imagem aprovada. A conexão continua
vindo do `.env`; apenas o opt-in e a NS autorizada são repassados separadamente:

```powershell
$env:ZENY_MARKET_SQLSERVER_SMOKE_ENABLED = "1"
$env:ZENY_MARKET_SQLSERVER_SMOKE_NS = "<NS-de-homologacao-com-10-digitos>"
docker compose --env-file .env -f compose.release.yaml run --rm --no-deps `
  -e ZENY_MARKET_SQLSERVER_SMOKE_ENABLED -e ZENY_MARKET_SQLSERVER_SMOKE_NS `
  --entrypoint python server -m zeny_project_handler_server.market_smoke
Remove-Item Env:ZENY_MARKET_SQLSERVER_SMOKE_ENABLED, Env:ZENY_MARKET_SQLSERVER_SMOKE_NS
```

Sem `ZENY_MARKET_SQLSERVER_SMOKE_ENABLED=1`, o comando não abre conexão e retorna código `2`.
Execute uma vez para a NS `RURAL` e outra para a NS `URBANO`; a saída mostra somente o mercado, sem
NS ou string ODBC.

## LAN, firewall e health

Bearer em HTTP protege autenticação, não confidencialidade. Restrinja a porta a uma LAN confiável;
para outra rede, use TLS por proxy reverso ou VPN. Evite `0.0.0.0`. No Windows, adapte IP/sub-rede:

```powershell
New-NetFirewallRule -DisplayName "Zeny Project Handler LAN" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 `
  -Profile Private -RemoteAddress 192.168.10.0/24
```

`GET /health/live` é público e informa somente vida. Prontidão da API é a conexão autenticada do
cliente ou `GET /api/v1/session` com `ready=true`; nenhum desses sinais consulta o SQL Server.

```powershell
docker compose --env-file .env -f compose.release.yaml ps
docker compose --env-file .env -f compose.release.yaml logs --since 30m server
```

## Parada, recreate e troca de senha

```powershell
docker compose --env-file .env -f compose.release.yaml stop
docker compose --env-file .env -f compose.release.yaml up -d --no-build --force-recreate
docker compose --env-file .env -f compose.release.yaml down
```

Nunca use `down -v`: isso remove o volume de dados. Para trocar a senha, substitua apenas
`ZENY_SERVER_PASSWORD` no `.env` e execute o recreate. Para rotacionar a conexão SQL Server,
substitua somente `ZENY_MARKET_SQLSERVER_CONNECTION_STRING`, recrie e valide com o smoke de
homologação. Senha, conexão e timeout não entram na imagem, no volume ou no backup; clientes devem
reconectar apenas após troca da senha da API.

## Backup e atualização

Backup não é uma ação do usuário final. Antes de qualquer upgrade, o administrador deve parar o
serviço, criar um snapshot consistente do volume nomeado `zeny-data` usando a política de backup do
host e guardar a cópia fora da máquina. Registre o hash do snapshot, o digest atual da imagem e o
nome do volume; reinicie o serviço somente depois que a cópia tiver sido validada. Não inclua
`.env` nesse snapshot ou em backups genéricos: segredos devem usar cofre/canal administrativo
próprio.

Para atualizar, carregue o novo archive, confira hashes/digest, leia as notas de schema, altere
`ZENY_SERVER_IMAGE` no `.env` para a referência aprovada e recrie sem build e sem remover o volume:

```powershell
docker compose --env-file .env -f compose.release.yaml down
docker compose --env-file .env -f compose.release.yaml up -d --no-build
```

Valide health, sessão, projetos e logs. Migração, revisão futura, corrupção ou falta de permissão
falham antes da prontidão e preservam o volume para recuperação.

## Rollback e recuperação

Trocar a referência para a imagem anterior no mesmo volume só é permitido quando ela declara
compatibilidade com o formato/revisão atuais. Caso contrário, preserve o volume atualizado, crie um
volume novo com a imagem anterior e restaure o snapshot administrativo pré-upgrade. Não execute
downgrade do Alembic e não edite `.zeny-volume.json` ou `alembic_version`.

Banco corrompido, volume sem permissão ou revisão incompatível exigem parada, preservação do volume
e restauração controlada. Não use `chmod 777`, bind mount Windows/SMB ou cópia de SQLite vivo.
