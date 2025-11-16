# Plantillas Word para CV Translator

## Cómo crear una plantilla Word

1. **Crea un documento Word** (.docx) con el diseño que desees
2. **Usa marcadores de posición** con doble llaves para los datos del CV:

### Marcadores disponibles:

**Información Personal:**
- `{{personal_name}}` - Nombre completo
- `{{personal_email}}` - Email
- `{{personal_phone}}` - Teléfono
- `{{personal_location}}` - Ubicación
- `{{personal_linkedin}}` - LinkedIn

**Contenido:**
- `{{summary}}` - Resumen profesional

**Experiencia (hasta 3 trabajos):**
- `{{exp1_title}}`, `{{exp1_company}}`, `{{exp1_duration}}`, `{{exp1_description}}`
- `{{exp2_title}}`, `{{exp2_company}}`, `{{exp2_duration}}`, `{{exp2_description}}`
- `{{exp3_title}}`, `{{exp3_company}}`, `{{exp3_duration}}`, `{{exp3_description}}`

**Educación (hasta 2 entradas):**
- `{{edu1_degree}}`, `{{edu1_institution}}`, `{{edu1_year}}`
- `{{edu2_degree}}`, `{{edu2_institution}}`, `{{edu2_year}}`

**Listas:**
- `{{skills}}` - Habilidades (separadas por comas)
- `{{languages}}` - Idiomas (separados por comas)
- `{{certifications}}` - Certificaciones (separadas por comas)

## Ejemplo de uso en Word:

```
{{personal_name}}
{{personal_email}} | {{personal_phone}}
{{personal_location}}

RESUMEN PROFESIONAL
{{summary}}

EXPERIENCIA PROFESIONAL
{{exp1_title}} - {{exp1_company}}
{{exp1_duration}}
{{exp1_description}}

HABILIDADES
{{skills}}
```

## Instrucciones:

1. Guarda tu plantilla como archivo .docx en esta carpeta
2. El nombre del archivo será el nombre de la plantilla
3. Usa el comando: `python main.py translate cv.pdf --template word --template-name tu_plantilla`