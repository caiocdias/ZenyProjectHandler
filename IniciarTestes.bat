@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "QT_QPA_PLATFORM=offscreen"
set "REPORT_FILE=%CD%\relatorio-testes.txt"
set "VENV_ACTIVATE=%CD%\.venv\Scripts\activate.bat"
set "SUITE_STATUS=0"

> "%REPORT_FILE%" echo RELATÓRIO DE QUALIDADE - ZENY PROJECT HANDLER
>> "%REPORT_FILE%" echo Data: %DATE% %TIME%
>> "%REPORT_FILE%" echo Diretório: %CD%

if not exist "%VENV_ACTIVATE%" (
    >> "%REPORT_FILE%" echo.
    >> "%REPORT_FILE%" echo RESULTADO FINAL: REPROVADO
    >> "%REPORT_FILE%" echo Ambiente virtual não encontrado. Execute setup.bat primeiro.
    type "%REPORT_FILE%"
    exit /b 1
)

call "%VENV_ACTIVATE%"
if errorlevel 1 (
    >> "%REPORT_FILE%" echo.
    >> "%REPORT_FILE%" echo RESULTADO FINAL: REPROVADO
    >> "%REPORT_FILE%" echo Não foi possível ativar o ambiente virtual.
    type "%REPORT_FILE%"
    exit /b 1
)

call :run_section "VERSÃO DO PYTHON" "python --version"
call :run_section "INTEGRIDADE DAS DEPENDÊNCIAS" "python -m pip check"
call :run_section "LINT - RUFF" "python -m ruff check ."
call :run_section "FORMATAÇÃO - RUFF" "python -m ruff format --check ."
call :run_section "TIPAGEM ESTÁTICA - MYPY" "python -m mypy"
call :run_section "TESTES E COBERTURA" "python -m pytest --cov --cov-report=term-missing --cov-fail-under=85.01"
call :run_section "COMPLEXIDADE CICLOMÁTICA" "python -m radon cc src -s -a"
call :run_section "ÍNDICE DE MANUTENIBILIDADE" "python -m radon mi src -s"
call :run_section "MÉTRICAS BRUTAS DO CÓDIGO" "python -m radon raw src -s"

>> "%REPORT_FILE%" echo.
if "!SUITE_STATUS!"=="0" (
    >> "%REPORT_FILE%" echo RESULTADO FINAL: APROVADO
    >> "%REPORT_FILE%" echo Cobertura mínima obrigatória: superior a 85%%.
) else (
    >> "%REPORT_FILE%" echo RESULTADO FINAL: REPROVADO
    >> "%REPORT_FILE%" echo Uma ou mais verificações falharam. Consulte as seções acima.
)

call deactivate >nul 2>nul
type "%REPORT_FILE%"
exit /b !SUITE_STATUS!

:run_section
set "SECTION_TITLE=%~1"
set "SECTION_COMMAND=%~2"
>> "%REPORT_FILE%" echo.
>> "%REPORT_FILE%" echo ============================================================
>> "%REPORT_FILE%" echo !SECTION_TITLE!
>> "%REPORT_FILE%" echo Comando: !SECTION_COMMAND!
>> "%REPORT_FILE%" echo ============================================================
call !SECTION_COMMAND! >> "%REPORT_FILE%" 2>&1
set "SECTION_EXIT_CODE=!ERRORLEVEL!"
>> "%REPORT_FILE%" echo Código de saída: !SECTION_EXIT_CODE!
if not "!SECTION_EXIT_CODE!"=="0" set "SUITE_STATUS=1"
exit /b 0

