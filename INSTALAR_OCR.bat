@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title ALTIVIA - Activar lectura automatica de facturas

echo ================================================================
echo  ALTIVIA - INSTALACION DEL RECONOCIMIENTO DE FACTURAS (OCR)
echo ================================================================
echo.
echo Paso 1: instalar bibliotecas de lectura de fotos y PDF.
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m pip install --upgrade -r requirements-ocr.txt
) else (
  python -m pip install --upgrade -r requirements-ocr.txt
)
if errorlevel 1 (
  echo ERROR: No se instalaron todas las dependencias Python.
  pause
  exit /b 1
)
echo.
echo Paso 2: verificar Tesseract OCR (motor gratuito de reconocimiento).
where tesseract >nul 2>nul
if %errorlevel%==0 goto check
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" goto check
if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" goto check

echo Tesseract no parece instalado.
echo.
echo Intentando instalar Tesseract con winget (administrador de Windows)...
where winget >nul 2>nul
if errorlevel 1 goto manual
winget install --id UB-Mannheim.TesseractOCR --exact --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto manual
echo.
echo Instalador de Tesseract ejecutado. Puede ser necesario reiniciar la app.
goto check
:manual
echo.
echo INSTALACION MANUAL:
echo Busca "UB Mannheim Tesseract OCR Windows installer" en su repositorio oficial de GitHub.
echo Instala Tesseract en C:\Program Files\Tesseract-OCR y selecciona espanol (spa) e ingles (eng).
echo La plataforma usa automaticamente esa carpeta, aun cuando no este en PATH.
:check
echo.
echo Paso 3: comprobacion final.
where py >nul 2>nul
if %errorlevel%==0 (py -3 VERIFICAR_OCR.py) else (python VERIFICAR_OCR.py)
echo.
echo Abre de nuevo ALTIVIA con INICIAR_ALTIVIA.bat.
pause
