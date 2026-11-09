@echo off
chcp 65001 >nul
set PYTHONUTF8=1
title Leitor de Artigos
cd /d "%~dp0"

rem
set "PY="
where py >nul 2>nul && py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python nao encontrado. Instale a versao 3.10 ou superior em python.org, marcando "Add python.exe to PATH".
    pause
    exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 (
    echo Necessário Python 3.10 ou superior. Versao encontrada:
    %PY% --version
    pause
    exit /b 1
)

%PY% -m article_reader
if errorlevel 1 pause
