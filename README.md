# CV Translator - Traductor de Currículums con IA Local

Herramienta para extraer, estructurar y traducir currículums vitae en PDF usando modelos de lenguaje locales con Ollama.

## Requisitos Previos

1. **Python 3.8+** instalado
2. **Ollama** instalado y ejecutándose ([https://ollama.ai](https://ollama.ai))
3. Al menos un modelo descargado en Ollama (ej: `ollama pull llama3.2`)

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

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

### 3. Extraer y estructurar un CV desde PDF (sin traducir)

```bash
python main.py extract mi_cv.pdf
```

Esto generará un archivo `mi_cv_structured.json` con el CV estructurado.

### 4. Traducir un CV

```bash
python main.py translate mi_cv.pdf --lang spanish
```

Opciones:
- `--lang` o `-l`: Idioma destino (english, spanish, french, german, etc.)
- `--model` o `-m`: Modelo específico de Ollama a usar
- `--format` o `-f`: Formato de salida (json, pdf)
- `--template` o `-t`: Tipo de plantilla (html, word)
- `--template-name` o `-tn`: Nombre de plantilla específica

Ejemplos:

```bash
# Traducir a inglés (JSON)
python main.py translate mi_cv.pdf --lang english

# Traducir a francés y generar PDF con plantilla HTML
python main.py translate mi_cv.pdf --lang french --format pdf --template html

# Traducir a alemán usando plantilla Word específica
python main.py translate mi_cv.pdf --lang german --format pdf --template word --template-name mi_plantilla
```

### 5. Ver plantillas disponibles

```bash
python main.py templates
```

## Estructura del Proyecto

```
CvTranslator/
├── main.py                 # Script principal con CLI
├── pdf_extractor.py        # Extracción de texto de PDFs
├── ollama_client.py        # Cliente para comunicación con Ollama
├── cv_structure.py         # Modelos de datos del CV
├── pdf_generator.py        # Generación de PDFs con plantillas
├── templates/              # Plantillas para PDFs
│   ├── html/              # Plantillas HTML
│   │   ├── modern.html    # Plantilla moderna
│   │   └── classic.html   # Plantilla clásica
│   └── word/              # Plantillas Word
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

## Solución de Problemas

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
