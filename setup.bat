@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "VENV_DIR=%CD%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

echo [1/4] Verificando o ambiente virtual...
if exist "%VENV_PYTHON%" goto activate_environment

echo [2/4] Criando o ambiente virtual em "%VENV_DIR%"...
if defined ZENY_BOOTSTRAP_PYTHON (
    if not exist "%ZENY_BOOTSTRAP_PYTHON%" goto configured_python_not_found
    "%ZENY_BOOTSTRAP_PYTHON%" -m venv "%VENV_DIR%"
    if errorlevel 1 goto venv_error
    goto activate_environment
)

where py >nul 2>nul
if errorlevel 1 goto try_python_command

py -3.11 --version >nul 2>nul
if not errorlevel 1 (
    py -3.11 -m venv "%VENV_DIR%"
    if errorlevel 1 goto venv_error
    goto activate_environment
)

py -3.12 --version >nul 2>nul
if not errorlevel 1 (
    py -3.12 -m venv "%VENV_DIR%"
    if errorlevel 1 goto venv_error
    goto activate_environment
)

:try_python_command
where python >nul 2>nul
if errorlevel 1 goto python_not_found
python -m venv "%VENV_DIR%"
if errorlevel 1 goto venv_error

:activate_environment
echo [2/4] Ativando o ambiente virtual...
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 goto activation_error

echo [3/4] Instalando as dependências fixadas...
python -m pip install --disable-pip-version-check -r "%CD%\requirements.lock"
if errorlevel 1 goto dependency_error

python -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e "%CD%"
if errorlevel 1 goto application_error

echo [4/4] Verificando a instalação...
python -m pip check
if errorlevel 1 goto dependency_error

echo.
echo Ambiente preparado com sucesso.
echo Abra ZenyProjectHandler.vbs para iniciar sem uma janela de console.
echo Use ZenyProjectHandler.bat somente quando quiser acompanhar a saida no terminal.
echo Execute IniciarTestes.bat para gerar o relatório de qualidade.
exit /b 0

:python_not_found
echo ERRO: Python 3.11 ou 3.12 não foi encontrado.
echo Instale o Python com o Python Launcher e execute este arquivo novamente.
echo Como alternativa, defina ZENY_BOOTSTRAP_PYTHON com o caminho do python.exe.
exit /b 1

:configured_python_not_found
echo ERRO: ZENY_BOOTSTRAP_PYTHON não aponta para um arquivo existente.
exit /b 1

:venv_error
echo ERRO: não foi possível criar o ambiente virtual.
exit /b 1

:activation_error
echo ERRO: não foi possível ativar o ambiente virtual.
exit /b 1

:dependency_error
echo ERRO: não foi possível instalar ou validar as dependências.
exit /b 1

:application_error
echo ERRO: não foi possível instalar o aplicativo no ambiente virtual.
exit /b 1

