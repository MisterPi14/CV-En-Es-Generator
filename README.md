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

### 1. Ver modelos disponibles

```bash
python main.py models
```

### 2. Extraer y estructurar un CV (sin traducir)

```bash
python main.py extract mi_cv.pdf
```

Esto generará un archivo `mi_cv_structured.json` con el CV estructurado.

### 3. Traducir un CV

```bash
python main.py translate mi_cv.pdf --lang spanish
```

Opciones:
- `--lang` o `-l`: Idioma destino (english, spanish, french, german, etc.)
- `--model` o `-m`: Modelo específico de Ollama a usar
- `--format` o `-f`: Formato de salida (por defecto: json)

Ejemplos:

```bash
# Traducir a inglés
python main.py translate mi_cv.pdf --lang english

# Traducir a francés usando un modelo específico
python main.py translate mi_cv.pdf --lang french --model llama3.2

# Traducir a alemán
python main.py translate mi_cv.pdf --lang german
```

## Estructura del Proyecto

```
AWS CV/
├── main.py                 # Script principal con CLI
├── pdf_extractor.py        # Extracción de texto de PDFs
├── ollama_client.py        # Cliente para comunicación con Ollama
├── cv_structure.py         # Modelos de datos del CV
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

## Solución de Problemas

### Error: "No se encontraron modelos en Ollama"
- Asegúrate de que Ollama esté ejecutándose: `ollama serve`
- Descarga al menos un modelo: `ollama pull llama3.2`

### Error al extraer texto del PDF
- Verifica que el PDF no esté protegido o encriptado
- Asegúrate de que el PDF contenga texto (no solo imágenes)

### La traducción no es precisa
- Prueba con un modelo más grande (ej: mistral, gemma2)
- Verifica que el idioma destino esté bien especificado

## Licencia

MIT
