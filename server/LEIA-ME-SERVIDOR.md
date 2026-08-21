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

Edite `.env`: substitua o placeholder de `ZENY_SERVER_PASSWORD` por uma senha longa e aleatória.
Não altere `ZENY_SERVER_IMAGE`, salvo numa atualização/rollback conferidos. Para clientes de outra
máquina, defina `ZENY_SERVER_BIND_ADDRESS` com o IPv4 privado específico do servidor.

```powershell
docker compose --env-file .env -f compose.release.yaml config --quiet
docker compose --env-file .env -f compose.release.yaml up -d --no-build
docker compose --env-file .env -f compose.release.yaml ps
```

O Compose nunca constrói imagem nem monta código-fonte. O volume nomeado `zeny-data` é a fonte de
verdade e sobrevive a restart, recreate e `docker compose down`.

## LAN, firewall e health

Bearer em HTTP protege autenticação, não confidencialidade. Restrinja a porta a uma LAN confiável;
para outra rede, use TLS por proxy reverso ou VPN. Evite `0.0.0.0`. No Windows, adapte IP/sub-rede:

```powershell
New-NetFirewallRule -DisplayName "Zeny Project Handler LAN" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 `
  -Profile Private -RemoteAddress 192.168.10.0/24
```

`GET /health/live` é público e informa somente vida. Prontidão real é a conexão autenticada do
cliente ou `GET /api/v1/session` com `ready=true`.

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
`ZENY_SERVER_PASSWORD` no `.env` e execute o recreate. A senha não entra na imagem, no volume ou no
backup; clientes devem reconectar.

## Backup e atualização

Crie e retire do host um `.zphbackup` pelo painel **Importar, exportar e backup** antes de qualquer
upgrade. O cliente confere tamanho e SHA-256 do download. Registre o digest atual e o nome do volume.

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
volume novo com a imagem anterior e restaure o `.zphbackup` pré-upgrade. Não execute downgrade do
Alembic e não edite `.zeny-volume.json` ou `alembic_version`.

Banco corrompido, volume sem permissão ou revisão incompatível exigem parada, preservação do volume
e restauração controlada. Não use `chmod 777`, bind mount Windows/SMB ou cópia de SQLite vivo.
