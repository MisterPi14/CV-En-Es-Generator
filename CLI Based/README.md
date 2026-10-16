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

Los textos de cada PDF se editan en su YAML. Los dos archivos actuales incluyen al
final un bloque `ui` con los encabezados, etiquetas, textos de enlaces y título del
documento. Cambia los **valores**, conservando las claves y la indentación:

```yaml
ui:
  section_experience: "Experiencia Técnica"          # legacy
  section_work: "Experiencia Técnica"                # generation
  section_technical_experience: "Experiencia Técnica" # capitalone
  section_profile: "Acerca de mí"
  section_education_gen: "Formación académica"
  label_gpa: "Promedio"
  label_linkedin: "Mi perfil profesional"
  label_github: "Mis repositorios"
  label_portfolio: "Mis trabajos"
  label_certificate: "Ver certificado"
  document_title: "Mi currículum"                     # título/metadatos
```

Edita el bloque existente; no agregues un segundo `ui`. El texto se imprime tal
cual, independientemente del idioma deducido del nombre del archivo. Para el YAML
en inglés puedes escribir `Technical Experience`. Los nombres internos de datos
como `work_experience`, `education` y `personal_info` siguen siendo los mismos.
El contenido de esas secciones, nombres, fechas, enlaces, descripciones y listas
se edita en sus campos habituales del YAML.

Opcionalmente, `ui_templates` permite que un mismo YAML tenga textos diferentes
según el diseño elegido:

```yaml
ui_templates:
  generation:
    section_work: "Experiencia en ingeniería"
  capitalone:
    section_technical_experience: "Technical Experience"
```

El orden de prioridad es: valores predeterminados del idioma y template → `ui` →
`ui_templates.<template>`. Los YAML actuales conservan los textos particulares de
los enlaces de `legacy` y `generation` en `ui_templates`; edítalos ahí para cambiarlos.
Si omites una clave, se usa su valor predeterminado. `""` deja el texto vacío;
no uses `null` ni dejes la clave sin valor. Las claves desconocidas producen un
error que indica dónde corregirlas. Las etiquetas se interpretan como texto,
no como HTML.

Solo aparecen los campos que ya utiliza el template elegido: cambiar una etiqueta
no agrega una sección. El orden, la disposición, los estilos, iconos y separadores
permanecen definidos por el template. Los textos largos pueden ocupar más espacio
y activar el ajuste de tamaño existente.

El modo `translate` también traduce `ui` y `ui_templates` y los guarda en el YAML
de destino; después puedes afinarlos manualmente. El modo `pdf` los usa sin
traducir ni modificar el archivo.

Pruebas de edición de textos (sin navegador ni llamadas al modelo):

```powershell
./.venv/cvtranslator/Scripts/python.exe -m unittest discover -s tests -v
```
