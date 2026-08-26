@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "VENV_ACTIVATE=%CD%\.venv\Scripts\activate.bat"
set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_ACTIVATE%" (
    echo ERRO: ambiente virtual não encontrado.
    echo Execute setup.bat antes de iniciar o aplicativo.
    exit /b 1
)

call "%VENV_ACTIVATE%"
if errorlevel 1 (
    echo ERRO: não foi possível ativar o ambiente virtual.
    exit /b 1
)

rem Valores exclusivos do ambiente local de desenvolvimento; não entram na release.
set "ZENY_SERVER_HOST=127.0.0.1"
set "ZENY_SERVER_PORT=8000"
set "ZENY_SERVER_PASSWORD=default_text"
set "ZENY_SERVER_DATA_DIR=%CD%\.local\development-server"
set "ZENY_CLIENT_SERVER_URL=http://127.0.0.1:8000"
set "ZENY_DATA_DIR=%CD%\.local\development-client"
set "ZENY_PROJECT_ROOT=%CD%"
set "ZENY_DEV_SERVER_PID="
set "APP_EXIT_CODE=1"

echo Iniciando o servidor local de desenvolvimento...
for /f "usebackq delims=" %%P in (`powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$process = Start-Process -FilePath $env:VENV_PYTHON -ArgumentList '-m','zeny_project_handler_server' -WorkingDirectory $env:ZENY_PROJECT_ROOT -WindowStyle Hidden -PassThru; $process.Id"`) do set "ZENY_DEV_SERVER_PID=%%P"
if not defined ZENY_DEV_SERVER_PID goto server_start_error

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
    "$deadline = (Get-Date).AddSeconds(30);" ^
    "$headers = @{ Authorization = 'Bearer ' + $env:ZENY_SERVER_PASSWORD };" ^
    "while ((Get-Date) -lt $deadline) {" ^
    "  if ($null -eq (Get-Process -Id ([int]$env:ZENY_DEV_SERVER_PID) -ErrorAction SilentlyContinue)) { exit 2 };" ^
    "  try {" ^
    "    $response = Invoke-WebRequest -UseBasicParsing -Uri ($env:ZENY_CLIENT_SERVER_URL + '/api/v1/session') -Headers $headers -TimeoutSec 1;" ^
    "    if ($response.StatusCode -eq 200) { exit 0 }" ^
    "  } catch {};" ^
    "  Start-Sleep -Milliseconds 250" ^
    "}; exit 1"
if errorlevel 2 goto server_stopped
if errorlevel 1 goto server_timeout

echo Servidor pronto. Iniciando o cliente...
"%VENV_PYTHON%" "%CD%\scripts\run_development_client.py" %*
set "APP_EXIT_CODE=%ERRORLEVEL%"
goto cleanup

:server_start_error
echo ERRO: não foi possível iniciar o processo do servidor local.
goto cleanup

:server_stopped
echo ERRO: o servidor local encerrou antes de ficar pronto.
goto cleanup

:server_timeout
echo ERRO: o servidor local não ficou pronto em até 30 segundos.
goto cleanup

:cleanup
if defined ZENY_DEV_SERVER_PID (
    echo Encerrando o servidor local de desenvolvimento...
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$process = Get-Process -Id ([int]$env:ZENY_DEV_SERVER_PID) -ErrorAction SilentlyContinue; if ($null -ne $process) { Stop-Process -Id $process.Id -Force; Wait-Process -Id $process.Id -ErrorAction SilentlyContinue }" >nul 2>nul
)
call deactivate >nul 2>nul
exit /b %APP_EXIT_CODE%

