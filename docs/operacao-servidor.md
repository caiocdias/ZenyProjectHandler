# Operação segura do servidor

Este runbook descreve a instalação e o lifecycle do servidor Docker do Zeny Project Handler. Ele
é suficiente para o administrador operar uma imagem já recebida e conectar clientes de outra
máquina da LAN, sem abrir nem interpretar o código-fonte. O kit oficial sem checkout, com imagem
OCI e Compose de release, será montado somente na Etapa 12; até lá, use a imagem/tag validada e o
`compose.yaml` fornecido junto dela, sempre com `--no-build` no host operacional.

## Limite de confiança

O Bearer simples protege autenticação, não confidencialidade de tráfego. Publique a porta apenas em
uma LAN privada e confiável. Não exponha o serviço à internet. Se clientes atravessarem uma rede não
confiável, coloque TLS em proxy reverso ou use VPN antes de liberar o acesso.

O padrão `ZENY_SERVER_BIND_ADDRESS=127.0.0.1` aceita somente o próprio host. Para outra máquina da
LAN, defina o endereço IPv4 privado específico da placa do servidor, por exemplo `192.168.10.20`.
Evite `0.0.0.0`; quando ele for indispensável, restrinja o firewall à sub-rede confiável.

No Windows, uma regra de exemplo para uma rede privada é:

```powershell
New-NetFirewallRule -DisplayName "Zeny Project Handler LAN" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 `
  -Profile Private -RemoteAddress 192.168.10.0/24
```

Adapte porta e sub-rede. Não crie regra para o perfil Public nem para `Any` sem uma revisão de rede.

## Pré-requisitos e instalação limpa

O host do servidor precisa apenas de Docker Engine/Desktop configurado para containers Linux, da
imagem validada e dos arquivos `compose.yaml` e `.env`. Ele não precisa de Python, Qt, Tesseract no
host nem do pacote do cliente.

1. Instale Docker e confirme `docker info`.
2. Receba a imagem por registry privado ou arquivo autorizado. Para um arquivo OCI/Docker:

   ```powershell
   docker load --input .\ZenyProjectHandler-Server-<versao>.oci.tar
   docker image inspect zeny-project-handler-server:<versao>
   ```

3. Confira o digest recebido com o manifesto da distribuição. Não use `latest` em produção.
4. Defina `ZENY_SERVER_IMAGE=<imagem>@sha256:<digest-aprovado>` no `.env`; essa referência é a
   unidade de atualização e rollback do Compose.
5. Copie `.env-example` para `.env`; gere uma senha longa e aleatória e substitua somente o valor
   de `ZENY_SERVER_PASSWORD`. O placeholder impede o startup.
6. Mantenha `.env` fora de Git, backups genéricos do checkout, tickets e mensagens. O segredo entra
   somente como ambiente runtime; não use `ARG`, `ENV` de Dockerfile nem imagem derivada com senha.
7. Defina `ZENY_SERVER_BIND_ADDRESS`, `ZENY_SERVER_PORT`, memória e PIDs. Não altere
   `ZENY_SERVER_DATA_DIR=/data`.
8. Inicie sem reconstruir a imagem recebida:

   ```powershell
   docker compose --env-file .env up -d --no-build
   docker compose ps
   ```

O serviço usa um worker, UID/GID `10001:10001`, root filesystem somente leitura, `/tmp` em tmpfs,
capabilities removidas, `no-new-privileges`, limites de memória/PIDs e volume nomeado em `/data`.
Não escale réplicas enquanto jobs, coordenação e credenciais efêmeras forem locais ao processo.

No cliente de outra máquina, extraia o ZIP Windows, abra `ZenyProjectHandler.exe` e informe
`http://<ipv4-privado-do-servidor>:<porta>` e a senha. A URL pode ser lembrada; a senha não.

## Health, prontidão e logs

`GET /health/live` é público e responde apenas `{"live":true}`. O container só fica healthy depois
que o lifecycle ASGI terminou; ainda assim, a prova operacional de prontidão é a conexão autenticada
do cliente ou `GET /api/v1/session` com `ready=true`.

Comandos de diagnóstico que não exibem a senha:

```powershell
docker compose ps
docker inspect --format '{{json .State.Health}}' (docker compose ps -q server)
docker compose logs --since 30m server
```

Os logs da aplicação também ficam sob `/data/logs`, com rotação. Headers `Authorization`, senha do
servidor e senhas de PDF não são registrados. Preserve o `correlation_id` mostrado ao usuário ao
abrir um incidente. Não anexe `.env`, banco, backup ou logs sem revisar dados sensíveis do projeto.

Ausência do Tesseract ou do idioma português aparece no diagnóstico OCR autenticado. Ela degrada
somente OCR; o servidor continua ready e mantém extração nativa. Reinstale a imagem oficial para
corrigir pacotes do sistema; não instale software manualmente dentro do container.

## Volume e lifecycle de schema

O volume `/data` contém SQLite, PDFs, fotos, cache, journals, transferências temporárias e logs. A
raiz mantém `.zeny-volume.json`, manifesto atômico de formato 1 com revisão Alembic e instantes de
preparação. Ele não contém senha. Não edite o manifesto nem `alembic_version` manualmente.

Em todo startup, antes de `ready=true`, o servidor:

1. comprova que a raiz é gravável;
2. valida o manifesto, quando existente;
3. executa `PRAGMA quick_check` no SQLite;
4. rejeita revisão desconhecida/futura;
5. executa Alembic somente se a revisão atual ainda não for o `head` da imagem;
6. verifica revisão e integridade depois da migração;
7. publica o manifesto do volume e só então compõe serviços de negócio.

Qualquer falha encerra o processo; não há readiness nem atendimento parcial. O volume não é apagado
ou rebaixado automaticamente. `docker compose down` preserva o volume; **nunca use `down -v` em
produção**. Não use bind mount de pasta Windows, SMB ou caminho do cliente como fonte permanente.

Localize o nome real sem alterá-lo:

```powershell
docker volume ls --filter label=com.docker.compose.volume=zeny-data
docker volume inspect <nome-do-volume>
```

## Backup rotineiro

Crie `.zphbackup` pelo painel **Importar, exportar e backup**. O servidor executa preflight, cria
snapshot SQLite íntegro, coleta arquivos gerenciados e oferece download autenticado; o cliente
confere tamanho/SHA-256 antes da publicação local. Copie o pacote final para armazenamento protegido
fora do host e do volume.

Uma origem ausente, alterada ou ilegível produz preflight `DEGRADADO`. Só prossiga depois de revisar
as omissões e confirmar explicitamente. O pacote continua exigindo integridade de tudo que declara.
Teste regularmente a restauração em um volume descartável, nunca sobre produção apenas para “ver se
abre”.

## Cutover da versão monolítica

Agende janela sem edições concorrentes e registre operador, horário, versões e digest da imagem.

1. Na versão antiga, encerre análises e revisões em andamento.
2. Execute o preflight de backup completo. Se houver origem ausente/alterada, registre projeto e
   documento, decida conscientemente pelo backup degradado e não monte a pasta Windows no servidor.
3. Crie o `.zphbackup`, salve em mídia independente e confira o SHA-256 informado pelo download.
4. Pare a versão antiga sem apagar sua pasta. Ela permanece como rollback até o aceite.
5. Suba a imagem nova com um volume nomeado vazio e aguarde health/readiness.
6. Conecte o cliente ao servidor novo, envie os bytes do `.zphbackup`, execute o preflight remoto e
   confira integridade, quantidade de projetos/documentos/fotos e IDs resumidos.
7. Confirme a restauração vinculada ao fingerprint. Não copie SQLite nem monte a pasta antiga.
8. Compare e registre: projetos/NS/IDs; documentos, hashes e ordem das folhas; análises e snapshots;
   propostas/decisões; revisão ativa e números das regras; fotos e navegação até evidências.
9. Reinicie o container e repita a consulta com dois clientes antes de liberar usuários.

Em backup íntegro, cada PDF passa a apontar para a cópia sob o volume novo. Em backup degradado, a
referência externa antiga é substituída por um destino determinístico sob `project-files` do volume,
mas o arquivo permanece ausente e o estado continua degradado. Reenvie o PDF correto ou remova o
documento pelo fluxo normal; nunca solucione montando o caminho Windows legado.

Se a comparação falhar, pare o servidor novo, preserve seu volume para diagnóstico e reative a
versão antiga. Não tente mesclar manualmente os bancos.

## Atualização de imagem

1. Avise os clientes e aguarde jobs terminarem.
2. Gere e retire do host um `.zphbackup` íntegro ou conscientemente degradado.
3. Registre tag/digest atual, revisão indicada em `.zeny-volume.json` e nome do volume.
4. Carregue/puxe a nova imagem e confira o digest.
5. Leia as notas de schema e compatibilidade.
6. Recrie sem remover o volume:

   ```powershell
   docker compose --env-file .env down
   docker compose --env-file .env up -d --no-build
   ```

7. Aguarde health e valide sessão, projetos, um documento e logs. Uma migração com falha deixa o
   container indisponível; preserve volume e logs e siga o rollback.

## Rollback

Rollback por troca de imagem só é suportado quando a imagem anterior declara suporte ao formato e à
revisão atuais do volume. Nesse caso, restaure a referência imutável anterior no Compose e faça
`up -d --no-build --force-recreate` sobre o mesmo volume.

Se a atualização mudou para schema que a imagem anterior não conhece, **não conecte a imagem antiga
ao volume atualizado e não execute Alembic downgrade**. Pare o container, preserve o volume falho,
crie outro volume e restaure o `.zphbackup` feito antes do upgrade com a imagem anterior. Só remova o
volume falho depois do aceite e da retenção definida pela operação.

## Troca da senha

1. Avise os clientes; a troca encerra a sessão efetiva deles.
2. Substitua `ZENY_SERVER_PASSWORD` em `.env` sem registrar o valor em terminal/log.
3. Recrie o container: `docker compose --env-file .env up -d --no-build --force-recreate`.
4. Confirme que a senha anterior retorna 401 e a nova conecta; peça reconexão aos clientes.

A troca não altera o volume nem inclui a senha em backup. Não mantenha a senha antiga comentada no
arquivo.

## Recuperação de falhas

| Sintoma | Conduta segura |
|---|---|
| volume sem permissão | pare; confirme volume nomeado e UID/GID 10001; corrija ownership de forma controlada; nunca use `chmod 777` |
| banco corrompido | pare; preserve o volume; crie volume novo e restaure o último `.zphbackup` validado |
| revisão futura/incompatível | use a imagem compatível ou restaure backup pré-upgrade em outro volume; não edite `alembic_version` |
| migração falhou | mantenha o container fora de serviço, guarde logs/digest/volume e aplique rollback compatível ou restauração |
| OCR ausente | operações nativas continuam; reinstale a imagem validada antes de depender de OCR |
| senha perdida | defina nova senha runtime e recrie; não existe senha recuperável em banco/imagem |
| job interrompido por restart | consulte o histórico; ativo anterior vira falha recuperável, nunca sucesso presumido |

Para parada planejada, use `docker compose stop` e aguarde até 30 segundos para shutdown cooperativo.
Não copie o SQLite vivo como backup. Não apague journals nem temporários seletivamente sem um
procedimento de suporte: estados ambíguos são deliberadamente fail-closed.
