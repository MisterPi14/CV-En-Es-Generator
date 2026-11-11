@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Rutas relativas al lanzador, incluso si se abre desde otra carpeta.
pushd "%~dp0"
if errorlevel 1 exit /b 1

set "VIRTUAL_ENV=%~dp0.venv\cvtranslator"
set "APP_PYTHON=%VIRTUAL_ENV%\Scripts\python.exe"
set "PYTHONHOME="
set "PYTHONUTF8=1"

if exist "%APP_PYTHON%" goto activate
echo [run] Creando el entorno .venv\cvtranslator...
py -3 -m venv "%VIRTUAL_ENV%"
if not errorlevel 1 goto activate
python -m venv "%VIRTUAL_ENV%"
if errorlevel 1 goto setup_error

:activate
rem Activacion equivalente a activate.bat, sin sus rutas absolutas antiguas.
set "PATH=%VIRTUAL_ENV%\Scripts;%PATH%"
set "VIRTUAL_ENV_PROMPT=cvtranslator"
set "PROMPT=(cvtranslator) %PROMPT%"
"%APP_PYTHON%" -c "import sys; print('[run] Python: ' + sys.executable)"
if errorlevel 1 goto python_error

"%APP_PYTHON%" -c "import yaml, jinja2, ollama; from playwright.sync_api import sync_playwright" >nul 2>&1
if not errorlevel 1 goto browser
echo [run] Instalando dependencias de requirements.txt...
"%APP_PYTHON%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto setup_error

:browser
rem Playwright solo descarga los componentes que faltan para su version.
echo [run] Verificando Chromium para generar PDF...
"%APP_PYTHON%" -m playwright install chromium
if errorlevel 1 goto setup_error

"%APP_PYTHON%" "%~dp0build.py" %*
set "APP_EXIT_CODE=%ERRORLEVEL%"
goto finish

:python_error
echo [run][ERROR] El Python del entorno no funciona. Comprueba la instalacion
echo de Python indicada en .venv\cvtranslator\pyvenv.cfg.
set "APP_EXIT_CODE=1"
goto finish

:setup_error
echo [run][ERROR] No se pudo preparar el entorno. Revisa el error anterior.
echo Se requiere Python instalado y acceso a Internet si faltan dependencias.
set "APP_EXIT_CODE=1"

:finish
rem El menu vuelve a si mismo tras cada operacion y solo termina con
rem "0.- Salir". Se pausa unicamente si algo fallo (p. ej. al preparar el
rem entorno), para que el error siga visible al abrir con doble clic.
if "%~1"=="" if not "%APP_EXIT_CODE%"=="0" pause
popd
exit /b %APP_EXIT_CODE%
