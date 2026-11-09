@echo off
chcp 65001 >nul
set PYTHONUTF8=1
title Leitor de artigos
cd /d "%~dp0"
where python >nul 2>nul || (echo Python nao encontrado. Instale em python.org marcando "Add python.exe to PATH". & pause & exit /b 1)
python -m article_reader
if errorlevel 1 pause
