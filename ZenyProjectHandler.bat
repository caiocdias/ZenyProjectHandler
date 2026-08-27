@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo ERRO: ambiente virtual não encontrado.
    echo Execute setup.bat antes de iniciar o aplicativo.
    exit /b 1
)

where docker >nul 2>nul
if errorlevel 1 goto docker_not_found

docker compose version >nul 2>nul
if errorlevel 1 goto compose_not_found

docker info >nul 2>nul
if errorlevel 1 goto docker_not_running

rem Credencial aleatória exclusiva desta execução local; nunca é gravada nem enviada como build arg.
for /f "usebackq delims=" %%S in (`powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "[Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')"`) do set "ZENY_SERVER_PASSWORD=%%S"
if not defined ZENY_SERVER_PASSWORD goto password_generation_error
set "ZENY_LOCAL_SERVER_PORT=8000"
set "ZENY_CLIENT_SERVER_URL=http://127.0.0.1:8000"
set "ZENY_LOCAL_COMPOSE_FILE=%CD%\compose.local.yaml"
set "ZENY_LOCAL_COMPOSE_PROJECT=zeny-local-%RANDOM%-%RANDOM%"
set "ZENY_LOCAL_SESSION_DIR=%TEMP%\ZenyProjectHandler\%ZENY_LOCAL_COMPOSE_PROJECT%"
set "ZENY_DATA_DIR=%ZENY_LOCAL_SESSION_DIR%\client"
set "ZENY_LOCAL_STOP_FILE=%ZENY_LOCAL_SESSION_DIR%\stop"
set "ZENY_LOCAL_RESULT_FILE=%ZENY_LOCAL_SESSION_DIR%\client-exit-code"
set "APP_EXIT_CODE=1"

mkdir "%ZENY_DATA_DIR%" >nul 2>nul
if errorlevel 1 goto temporary_directory_error

echo Construindo a imagem local do servidor...
docker compose --project-name "%ZENY_LOCAL_COMPOSE_PROJECT%" --file "%ZENY_LOCAL_COMPOSE_FILE%" build
if errorlevel 1 goto server_build_error

echo Iniciando o cliente assim que o servidor estiver pronto...
start "" /b "%VENV_PYTHON%" "%CD%\scripts\run_development_client.py" %*
if errorlevel 1 goto client_start_error

echo Subindo o servidor Docker local e efêmero...
echo Feche o cliente ou pressione Ctrl+C para encerrar toda a sessão.
docker compose --project-name "%ZENY_LOCAL_COMPOSE_PROJECT%" --file "%ZENY_LOCAL_COMPOSE_FILE%" up --no-build --force-recreate --remove-orphans
set "COMPOSE_EXIT_CODE=%ERRORLEVEL%"

type nul > "%ZENY_LOCAL_STOP_FILE%"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
    "$deadline = (Get-Date).AddSeconds(10);" ^
    "while ((Get-Date) -lt $deadline -and -not (Test-Path -LiteralPath $env:ZENY_LOCAL_RESULT_FILE)) { Start-Sleep -Milliseconds 100 }" >nul 2>nul

if exist "%ZENY_LOCAL_RESULT_FILE%" set /p APP_EXIT_CODE=<"%ZENY_LOCAL_RESULT_FILE%"
if not "%COMPOSE_EXIT_CODE%"=="0" set "APP_EXIT_CODE=%COMPOSE_EXIT_CODE%"
goto cleanup

:docker_not_found
echo ERRO: Docker não foi encontrado.
echo Instale o Docker Desktop e execute setup.bat novamente.
exit /b 1

:compose_not_found
echo ERRO: o plugin Docker Compose não foi encontrado.
echo Instale ou atualize o Docker Desktop e execute setup.bat novamente.
exit /b 1

:docker_not_running
echo ERRO: o mecanismo do Docker não está disponível.
echo Abra o Docker Desktop e tente novamente.
exit /b 1

:temporary_directory_error
echo ERRO: não foi possível criar o diretório temporário da sessão local.
exit /b 1

:password_generation_error
echo ERRO: não foi possível gerar a credencial efêmera da sessão local.
exit /b 1

:server_build_error
echo ERRO: não foi possível construir a imagem local do servidor.
goto cleanup

:client_start_error
echo ERRO: não foi possível iniciar o cliente local.
goto cleanup

:cleanup
echo Descartando o servidor e todos os dados da sessão local...
docker compose --project-name "%ZENY_LOCAL_COMPOSE_PROJECT%" --file "%ZENY_LOCAL_COMPOSE_FILE%" down --volumes --remove-orphans --timeout 30 >nul 2>nul
if exist "%ZENY_LOCAL_SESSION_DIR%" rmdir /s /q "%ZENY_LOCAL_SESSION_DIR%" >nul 2>nul
exit /b %APP_EXIT_CODE%

