# CV Translator - Traductor de Currículums con IA Local

Herramienta para capturar, estructurar y traducir currículums vitae usando modelos de lenguaje locales con Ollama.

## Requisitos Previos

1. **Python 3.8+** instalado
2. **Ollama** instalado y ejecutándose ([https://ollama.ai](https://ollama.ai))
3. Al menos un modelo descargado en Ollama (ej: `ollama pull llama3.2`)
4. **Microsoft Word** (solo si usas plantillas Word para generar PDFs)

## Instalación

```bash
python install.py
```

Esto creará un entorno virtual en `~/.python-envs/cvTranslator` e instalará todas las dependencias automáticamente.

### Desinstalación

```bash
python uninstall.py
```

## Uso

**Nota**: El entorno virtual se activa automáticamente al ejecutar `main.py`.

### 1. Importar CV mediante formulario interactivo

```bash
python main.py import-cv
```

Esto abrirá un formulario interactivo donde podrás ingresar:
- Información personal (nombre, email, teléfono, ubicación, LinkedIn)
- Resumen profesional
- Experiencia laboral (múltiples entradas)
- Educación (múltiples entradas)
- Habilidades
- Idiomas
- Certificaciones

El CV se guardará automáticamente en formato JSON.

### 2. Ver modelos disponibles

```bash
python main.py models
```

### 3. Traducir un CV

```bash
python main.py translate --lang english
```

El comando mostrará una lista de CVs disponibles en `resumes_loaded/` para que selecciones cuál traducir.

Opciones:
- `--lang` o `-l`: Idioma destino (english, spanish, french, german, etc.)
- `--model` o `-m`: Modelo específico de Ollama a usar
- `--format` o `-f`: Formato de salida (json, pdf)
- `--template` o `-t`: Tipo de plantilla (html, word) - solo para formato PDF
- `--template-name` o `-tn`: Nombre de plantilla específica

Ejemplos:

```bash
# Traducir a inglés (JSON) - selección interactiva
python main.py translate --lang english

# Traducir a francés y generar PDF con plantilla HTML
python main.py translate --lang french --format pdf --template html

# Traducir a alemán usando plantilla Word específica
python main.py translate --lang german --format pdf --template word --template-name sample
```

### 4. Extraer y estructurar un CV desde PDF (sin traducir)

```bash
python main.py extract mi_cv.pdf
```

**Nota**: Este comando usa IA para estructurar el PDF. Se recomienda usar `import-cv` en su lugar para mayor precisión.

### 5. Ver plantillas disponibles

```bash
python main.py templates
```

## Estructura del Proyecto

```
CvTranslator/
├── install.py              # Script de instalación (crea venv e instala dependencias)
├── uninstall.py            # Script de desinstalación (elimina venv)
├── main.py                 # Script principal con CLI (activa venv automáticamente)
├── cv_importer.py          # Formulario interactivo para importar CVs
├── pdf_extractor.py        # Extracción de texto de PDFs (legacy)
├── ollama_client.py        # Cliente para comunicación con Ollama
├── cv_structure.py         # Modelos de datos del CV (Pydantic)
├── pdf_generator.py        # Generación de PDFs con plantillas
├── resumes_loaded/         # CVs importados (JSON)
├── templates/              # Plantillas para PDFs
│   ├── html/              # Plantillas HTML
│   │   ├── modern.html    # Plantilla moderna
│   │   └── classic.html   # Plantilla clásica
│   └── word/              # Plantillas Word
│       ├── sample.docx    # Plantilla de ejemplo
│       └── README.md      # Instrucciones para crear plantillas
├── requirements.txt        # Dependencias
└── README.md              # Este archivo
```

## Formato JSON del CV

El CV se estructura en el siguiente formato:

```json
{
  "personal_info": {
    "name": "Nombre Completo",
    "email": "email@ejemplo.com",
    "phone": "+1234567890",
    "location": "Ciudad, País",
    "linkedin": "linkedin.com/in/usuario"
  },
  "summary": "Resumen profesional...",
  "experience": [
    {
      "title": "Cargo",
      "company": "Empresa",
      "duration": "2020-2023",
      "description": "Descripción del rol..."
    }
  ],
  "education": [
    {
      "degree": "Título",
      "institution": "Universidad",
      "year": "2020"
    }
  ],
  "skills": ["Python", "AWS", "Docker"],
  "languages": ["Español", "Inglés"],
  "certifications": ["AWS Certified"]
}
```

## Modelos Recomendados

- **llama3.2** (3B): Rápido y eficiente para traducción
- **mistral** (7B): Buen balance entre velocidad y calidad
- **gemma2** (9B): Excelente para múltiples idiomas
- **qwen2.5** (7B): Muy bueno en estructuración de datos

Para descargar un modelo:
```bash
ollama pull llama3.2
```

## Plantillas

### Plantillas HTML
Incluidas por defecto:
- **modern**: Diseño moderno con colores y etiquetas
- **classic**: Diseño clásico estilo académico

### Plantillas Word
Puedes crear tus propias plantillas Word:
1. Crea un archivo .docx con tu diseño
2. Usa marcadores como `{{personal_name}}`, `{{summary}}`, etc.
3. Guárdalo en `templates/word/`
4. Consulta `templates/word/README.md` para la lista completa de marcadores

## Flujo de Trabajo Recomendado

1. **Importar CV**: `python main.py import-cv`
   - Completa el formulario interactivo
   - El CV se guarda en `resumes_loaded/`

2. **Editar JSON** (opcional): Abre el archivo JSON y ajusta cualquier dato

3. **Traducir**: `python main.py translate --lang english --format pdf`
   - Selecciona el CV de la lista
   - Elige modelo y plantilla
   - Obtén tu CV traducido

## Solución de Problemas

### No se encuentran CVs para traducir
- Asegúrate de haber importado al menos un CV con `python main.py import-cv`
- Verifica que exista la carpeta `resumes_loaded/` con archivos JSON

### No se encuentran plantillas
- Verifica que existan archivos en `templates/html/` o `templates/word/`
- Para Word: consulta `templates/word/README.md` para crear plantillas

### Error: "No se encontraron modelos en Ollama"
- Asegúrate de que Ollama esté ejecutándose: `ollama serve`
- Descarga al menos un modelo: `ollama pull llama3.2`

### Error al extraer texto del PDF
- Verifica que el PDF no esté protegido o encriptado
- Asegúrate de que el PDF contenga texto (no solo imágenes)

### Error al generar PDF
- Para plantillas Word: Asegúrate de tener Microsoft Word instalado
- Para plantillas HTML: Verifica que WeasyPrint esté instalado correctamente

### La traducción no es precisa
- Prueba con un modelo más grande (ej: mistral, gemma2)
- Verifica que el idioma destino esté bien especificado

## Licencia

MIT
