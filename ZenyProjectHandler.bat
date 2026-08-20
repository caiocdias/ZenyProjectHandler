@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "VENV_ACTIVATE=%CD%\.venv\Scripts\activate.bat"
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

python -m zeny_project_handler_client %*
set "APP_EXIT_CODE=%ERRORLEVEL%"
call deactivate >nul 2>nul
exit /b %APP_EXIT_CODE%

