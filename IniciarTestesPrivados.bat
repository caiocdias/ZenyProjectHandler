@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "QT_QPA_PLATFORM=offscreen"
set "REPORT_FILE=%CD%\relatorio-testes-privados.txt"
set "VENV_ACTIVATE=%CD%\.venv\Scripts\activate.bat"
set "PYTEST_TEMP_ROOT=%SystemDrive%\tmp"
set "PYTEST_BASETEMP=!PYTEST_TEMP_ROOT!\zph-private-!RANDOM!"

> "%REPORT_FILE%" echo RELATORIO DO GATE PRIVADO - ZENY PROJECT HANDLER
>> "%REPORT_FILE%" echo Data: %DATE% %TIME%
>> "%REPORT_FILE%" echo Escopo: somente testes marcados como private_samples.
>> "%REPORT_FILE%" echo Este gate exige acesso autorizado ao corpus completo e autentico.

if not exist "%PYTEST_TEMP_ROOT%" mkdir "%PYTEST_TEMP_ROOT%" >nul 2>&1
if not exist "%PYTEST_TEMP_ROOT%" (
    >> "%REPORT_FILE%" echo.
    >> "%REPORT_FILE%" echo RESULTADO FINAL: REPROVADO
    >> "%REPORT_FILE%" echo Nao foi possivel criar a raiz temporaria curta %PYTEST_TEMP_ROOT%.
    type "%REPORT_FILE%"
    exit /b 1
)

if not exist "%VENV_ACTIVATE%" (
    >> "%REPORT_FILE%" echo.
    >> "%REPORT_FILE%" echo RESULTADO FINAL: REPROVADO
    >> "%REPORT_FILE%" echo Ambiente virtual nao encontrado. Execute setup.bat primeiro.
    type "%REPORT_FILE%"
    exit /b 1
)

call "%VENV_ACTIVATE%"
if errorlevel 1 (
    >> "%REPORT_FILE%" echo.
    >> "%REPORT_FILE%" echo RESULTADO FINAL: REPROVADO
    >> "%REPORT_FILE%" echo Nao foi possivel ativar o ambiente virtual.
    type "%REPORT_FILE%"
    exit /b 1
)

>> "%REPORT_FILE%" echo.
>> "%REPORT_FILE%" echo ============================================================
>> "%REPORT_FILE%" echo PRE-CONDICOES E TESTES DO CORPUS PRIVADO
>> "%REPORT_FILE%" echo Comando: python -m pytest -m private_samples --maxfail=1
>> "%REPORT_FILE%" echo ============================================================
python -m pytest -m private_samples --maxfail=1 --tb=short ^
    --basetemp="!PYTEST_BASETEMP!" >> "%REPORT_FILE%" 2>&1
set "SUITE_STATUS=!ERRORLEVEL!"
>> "%REPORT_FILE%" echo Codigo de saida: !SUITE_STATUS!

>> "%REPORT_FILE%" echo.
if "!SUITE_STATUS!"=="0" (
    >> "%REPORT_FILE%" echo RESULTADO FINAL: APROVADO
    >> "%REPORT_FILE%" echo Corpus autorizado completo e testes privados aprovados.
) else (
    >> "%REPORT_FILE%" echo RESULTADO FINAL: REPROVADO
    >> "%REPORT_FILE%" echo Corpus ausente, incompleto, adulterado ou com regressao.
)

call deactivate >nul 2>nul
type "%REPORT_FILE%"
exit /b !SUITE_STATUS!
