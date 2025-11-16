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

def translate_cv(cv_data: Dict, target_lang: str, model: str) -> Dict:
    """Traduce el contenido del CV al idioma objetivo."""
    prompt = f"""Traduce el siguiente currículum vitae al idioma: {target_lang}
Mantén EXACTAMENTE la misma estructura JSON, solo traduce los valores de texto.
NO traduzcas nombres propios, correos, teléfonos, URLs.

CV en JSON:
{json.dumps(cv_data, ensure_ascii=False, indent=2)}

Responde ÚNICAMENTE con el JSON traducido, sin texto adicional."""

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
        print(f"Error al traducir CV: {e}")
        return cv_data
