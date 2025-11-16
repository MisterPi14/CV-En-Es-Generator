import ollama
import json
from typing import List, Dict

def list_available_models() -> List[str]:
    """Lista todos los modelos disponibles en Ollama."""
    try:
        models = ollama.list()
        return [model['name'] for model in models['models']]
    except Exception as e:
        print(f"Error al listar modelos: {e}")
        return []

def structure_cv_with_llm(text: str, model: str) -> Dict:
    """Usa el LLM para estructurar el texto del CV en formato JSON."""
    prompt = f"""Analiza el siguiente currículum vitae y extrae la información en formato JSON con esta estructura:
{{
  "personal_info": {{
    "name": "nombre completo",
    "email": "correo",
    "phone": "teléfono",
    "location": "ubicación",
    "linkedin": "perfil linkedin"
  }},
  "summary": "resumen profesional",
  "experience": [
    {{
      "title": "cargo",
      "company": "empresa",
      "duration": "periodo",
      "description": "descripción"
    }}
  ],
  "education": [
    {{
      "degree": "título",
      "institution": "institución",
      "year": "año"
    }}
  ],
  "skills": ["habilidad1", "habilidad2"],
  "languages": ["idioma1", "idioma2"],
  "certifications": ["certificación1"]
}}

Texto del CV:
{text}

Responde ÚNICAMENTE con el JSON, sin texto adicional."""

    try:
        response = ollama.generate(model=model, prompt=prompt)
        json_text = response['response'].strip()
        
        # Limpiar markdown si existe
        if json_text.startswith('```'):
            json_text = json_text.split('```')[1]
            if json_text.startswith('json'):
                json_text = json_text[4:]
        
        return json.loads(json_text)
    except Exception as e:
        print(f"Error al estructurar CV: {e}")
        return {}

def translate_text(text: str, target_lang: str, model: str) -> str:
    """Traduce un texto simple al idioma objetivo."""
    prompt = f"""Traduce el siguiente texto al idioma: {target_lang}
Responde ÚNICAMENTE con la traducción, sin explicaciones ni texto adicional.

Texto:
{text}"""

    try:
        response = ollama.generate(model=model, prompt=prompt)
        return response['response'].strip()
    except Exception as e:
        print(f"Error al traducir texto: {e}")
        return text

def translate_cv(cv_data: Dict, target_lang: str, model: str, progress=None, task=None) -> Dict:
    """Traduce el contenido del CV al idioma objetivo manteniendo estructura."""
    translated_cv = {}
    
    def update_progress():
        if progress and task:
            progress.advance(task, 1)
    
    # Personal info - NO traducir (son datos personales)
    translated_cv['personal_info'] = cv_data.get('personal_info', {}).copy()
    
    # Summary - traducir
    if cv_data.get('summary'):
        translated_cv['summary'] = translate_text(cv_data['summary'], target_lang, model)
        update_progress()
    else:
        translated_cv['summary'] = ''
        update_progress()
    
    # Experience - traducir title, company, description (NO duration)
    translated_cv['experience'] = []
    for exp in cv_data.get('experience', []):
        translated_exp = {
            'title': translate_text(exp.get('title', ''), target_lang, model),
            'company': exp.get('company', ''),  # NO traducir nombre de empresa
            'duration': exp.get('duration', ''),  # NO traducir fechas
            'description': translate_text(exp.get('description', ''), target_lang, model)
        }
        translated_cv['experience'].append(translated_exp)
        update_progress()  # title
        update_progress()  # description
    
    # Education - traducir degree (NO institution, year)
    translated_cv['education'] = []
    for edu in cv_data.get('education', []):
        translated_edu = {
            'degree': translate_text(edu.get('degree', ''), target_lang, model),
            'institution': edu.get('institution', ''),  # NO traducir nombre de institución
            'year': edu.get('year', '')  # NO traducir año
        }
        translated_cv['education'].append(translated_edu)
        update_progress()
    
    # Skills - traducir cada habilidad
    translated_cv['skills'] = []
    for skill in cv_data.get('skills', []):
        translated_cv['skills'].append(translate_text(skill, target_lang, model))
        update_progress()
    
    # Languages - traducir nombres de idiomas
    translated_cv['languages'] = []
    for lang in cv_data.get('languages', []):
        translated_cv['languages'].append(translate_text(lang, target_lang, model))
        update_progress()
    
    # Certifications - NO traducir (son nombres propios)
    translated_cv['certifications'] = cv_data.get('certifications', []).copy()
    
    return translated_cv
