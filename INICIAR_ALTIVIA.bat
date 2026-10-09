@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title ALTIVIA - Gestion Inteligente de Facturas
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 launcher.py
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python launcher.py
  ) else (
    echo.
    echo ERROR: No se encontro Python. Instala Python 3.11 o superior desde python.org
    echo Marca "Add python.exe to PATH" durante la instalacion.
  )
)
echo.
echo El servidor ALTIVIA se ha detenido o produjo un error.
pause
