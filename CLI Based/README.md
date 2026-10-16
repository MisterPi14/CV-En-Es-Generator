# Generador de CV (CLI)

Genera PDF con los templates `legacy`, `generation` y `capitalone`, o traduce
un YAML para reutilizarlo después al generar documentos.

En Windows, abre **`run.bat` con doble clic**. También puedes ejecutarlo desde
PowerShell con `./run.bat`. El menú permite elegir la operación, el YAML y el
template. Al terminar sin argumentos, espera una tecla para poder leer el resultado.

El lanzador activa `.venv\cvtranslator` para su proceso, comprueba las dependencias,
instala las que falten y prepara el Chromium que necesita Playwright. Utiliza rutas
relativas al proyecto: funciona aunque cambies la carpeta de ubicación o lo abras
desde otro directorio. No hace falta ejecutar `setup_env.sh` ni activar el entorno
manualmente. Si el entorno no existe, lo crea con Python instalado en Windows.
La primera instalación requiere Internet; los siguientes arranques reutilizan los
paquetes y el navegador existentes. Las fuentes de los templates se cargan desde CDN;
si la carga tarda demasiado, el PDF usa los recursos disponibles y fuentes del sistema.

También admite todos los argumentos de `build.py`:

```powershell
./run.bat --help
./run.bat --mode pdf --input resume.en.gpt-oss-20b-cloud.yaml --template capitalone
./run.bat --mode translate --input resume.es.yaml --to en
```

Usa como entrada un YAML existente. La traducción requiere además Ollama disponible
y acceso al modelo configurado en `build.py`; generar PDF no llama al modelo.

De los dos entornos trasladados, `cvtranslator` contiene las dependencias de esta
aplicación. `cvTranslator2` no se utiliza. Los antiguos scripts `activate` guardan
rutas de antes del traslado; `run.bat` establece la activación con la ruta actual y
ejecuta siempre el Python del entorno elegido. Una mudanza a otro equipo requiere
que también esté instalado el Python base indicado en `pyvenv.cfg` o recrear el entorno.
