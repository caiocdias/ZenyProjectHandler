@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "VENV_DIR=%CD%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

echo [1/5] Verificando o ambiente virtual do cliente...
if not exist "%VENV_PYTHON%" goto create_environment

call :ensure_supported_python "%VENV_PYTHON%"
if not errorlevel 1 goto activate_environment

echo Ambiente virtual existente usa uma versao de Python incompativel com o projeto.
echo Recriando "%VENV_DIR%" com Python 3.11, 3.12 ou 3.13...
rmdir /s /q "%VENV_DIR%"
if exist "%VENV_DIR%" goto venv_cleanup_error

:create_environment
echo [1/5] Criando o ambiente virtual do cliente em "%VENV_DIR%"...
if defined ZENY_BOOTSTRAP_PYTHON goto use_configured_python

where py >nul 2>nul
if errorlevel 1 goto try_python_command

py -3.11 --version >nul 2>nul
if not errorlevel 1 goto create_with_py311

py -3.12 --version >nul 2>nul
if not errorlevel 1 goto create_with_py312

py -3.13 --version >nul 2>nul
if not errorlevel 1 goto create_with_py313

goto try_python_command

:use_configured_python
if not exist "%ZENY_BOOTSTRAP_PYTHON%" goto configured_python_not_found
call :ensure_supported_python "%ZENY_BOOTSTRAP_PYTHON%"
if errorlevel 1 goto configured_python_unsupported
"%ZENY_BOOTSTRAP_PYTHON%" -m venv "%VENV_DIR%"
if errorlevel 1 goto venv_error
goto activate_environment

:create_with_py311
py -3.11 -m venv "%VENV_DIR%"
if errorlevel 1 goto venv_error
goto activate_environment

:create_with_py312
py -3.12 -m venv "%VENV_DIR%"
if errorlevel 1 goto venv_error
goto activate_environment

:create_with_py313
py -3.13 -m venv "%VENV_DIR%"
if errorlevel 1 goto venv_error
goto activate_environment

:try_python_command
where python >nul 2>nul
if errorlevel 1 goto python_not_found
call :ensure_supported_python "python"
if errorlevel 1 goto python_not_found
python -m venv "%VENV_DIR%"
if errorlevel 1 goto venv_error

:activate_environment
echo [2/5] Ativando o ambiente virtual...
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 goto activation_error

echo [3/5] Instalando somente as dependencias fixadas do cliente...
python -m pip install --disable-pip-version-check -r "%CD%\requirements-client.lock"
if errorlevel 1 goto dependency_error

echo [4/5] Instalando o pacote independente do cliente...
python -m pip install --disable-pip-version-check --no-build-isolation --no-deps -e "%CD%\client"
if errorlevel 1 goto application_error

echo [5/5] Verificando a instalacao do cliente...
python -m pip check
if errorlevel 1 goto dependency_error

echo.
echo Cliente preparado com sucesso, sem dependencias do servidor ou OCR local.
echo Abra ZenyProjectHandler.vbs para iniciar sem uma janela de console.
echo Use ZenyProjectHandler.bat somente quando quiser acompanhar a saida no terminal.
exit /b 0

:python_not_found
echo ERRO: Python 3.11, 3.12 ou 3.13 nao foi encontrado.
echo Instale o Python com o Python Launcher e execute este arquivo novamente.
echo Como alternativa, defina ZENY_BOOTSTRAP_PYTHON com o caminho do python.exe.
exit /b 1

:configured_python_not_found
echo ERRO: ZENY_BOOTSTRAP_PYTHON nao aponta para um arquivo existente.
exit /b 1

:configured_python_unsupported
echo ERRO: ZENY_BOOTSTRAP_PYTHON deve apontar para Python 3.11, 3.12 ou 3.13.
exit /b 1

:venv_cleanup_error
echo ERRO: nao foi possivel remover o ambiente virtual incompativel.
echo Feche terminais ou aplicativos usando a pasta ".venv" e execute setup.bat novamente.
exit /b 1

:venv_error
echo ERRO: nao foi possivel criar o ambiente virtual.
exit /b 1

:activation_error
echo ERRO: nao foi possivel ativar o ambiente virtual.
exit /b 1

:dependency_error
echo ERRO: nao foi possivel instalar ou validar as dependencias.
exit /b 1

:application_error
echo ERRO: nao foi possivel instalar o aplicativo no ambiente virtual.
exit /b 1

:ensure_supported_python
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 11), (3, 12), (3, 13)) else 1)" >nul 2>nul
exit /b %ERRORLEVEL%
