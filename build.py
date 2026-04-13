import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import sys
import traceback
import tempfile
import contextlib
import copy
import re

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

OLLAMA_MODEL = "gemma3:4b"
# Intento de importación de WeasyPrint con manejo de errores para dependencias nativas faltantes
try:
    from weasyprint import HTML  # type: ignore
    WEASYPRINT_AVAILABLE = True
    WEASYPRINT_IMPORT_ERROR = None
except Exception as e:  # Captura ImportError / OSError (librerías GTK/Pango faltantes, etc.)
    WEASYPRINT_AVAILABLE = False
    WEASYPRINT_IMPORT_ERROR = e

# Playwright (fallback sin dependencias nativas similares) -------------------
try:
    from playwright.sync_api import sync_playwright  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

def _playwright_pdf(html_content: str, output_file: Path, base_dir: Path) -> bool:
    """Intentar generar PDF usando Playwright Chromium.

    Devuelve True si tuvo éxito, False si no se pudo (imprime causa).
    Requiere que el usuario haya ejecutado:  python -m playwright install chromium
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("[PLAYWRIGHT] No disponible el paquete. Instala con: pip install playwright")
        return False
    # Escribir HTML temporal
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False, encoding='utf-8', dir=base_dir) as tmp:
        tmp.write(html_content)
        tmp_path = Path(tmp.name)
    file_url = tmp_path.as_uri()
    try:
        with sync_playwright() as p:  # type: ignore
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(file_url)
            # Asegurar que fuentes remotas intenten cargarse
            page.wait_for_load_state('networkidle')
            page.pdf(
                path=str(output_file),
                format='A4',
                print_background=True,
                margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"}
            )
            browser.close()
        print(f"Generated {output_file.name} (Playwright)")
        return True
    except Exception as e:  # noqa
        print(f"[PLAYWRIGHT][ERROR] {e}")
        print("Si es la primera vez, instala navegador: python -m playwright install chromium")
        return False
    finally:
        with contextlib.suppress(Exception):
            tmp_path.unlink()

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

CV_FILE = BASE_DIR / "resume.yaml"
OUTPUT_PREFIX = "resume_"

UI_STRINGS = {
    "es": {
        "section_summary": "Resumen Profesional",
        "section_experience": "Experiencia Profesional",
        "section_projects": "Proyectos",
        "section_education": "Educación",
        "section_certifications": "Certificaciones",
        "section_courses": "Cursos",
        "section_skills": "Habilidades",
        "section_languages": "Lenguajes",
        "section_technologies": "Tecnologías"
    },
    "en": {
        "section_summary": "Professional Summary",
        "section_experience": "Work Experience",
        "section_projects": "Projects",
        "section_education": "Education",
        "section_certifications": "Certifications",
        "section_courses": "Courses",
        "section_skills": "Skills",
        "section_languages": "Languages",
        "section_technologies": "Technologies"
    }
}

def load_cv_data():
    with CV_FILE.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data

def markdown_links(text: str) -> str:
    if not isinstance(text, str):
        return text
    return re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)

def render_to_pdf(data: dict, lang: str):
    """Renderiza el CV a PDF (si WeasyPrint funciona) o genera fallback HTML.

    Si WeasyPrint no está disponible (falta libgobject/pango en Windows u otra dependencia),
    se genera un archivo HTML para inspección manual y se muestra una guía breve.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(['html', 'xml'])
    )
    env.filters['markdown_links'] = markdown_links
    template = env.get_template('template.html.j2')

    html_content = template.render(
        lang=lang,
        ui=UI_STRINGS[lang],
        **data
    )

    output_file = BASE_DIR / f"{OUTPUT_PREFIX}{lang}.pdf"

    if WEASYPRINT_AVAILABLE:
        try:
            HTML(string=html_content, base_url=str(BASE_DIR)).write_pdf(str(output_file))
            print(f"Generated {output_file.name} (WeasyPrint)")
            return
        except Exception:
            print("[WARN] WeasyPrint falló en tiempo de ejecución. Intentando Playwright...")
            traceback.print_exc()

    # Si no disponible WeasyPrint o falló, usar Playwright
    if _playwright_pdf(html_content, output_file, BASE_DIR):
        return

    # Último fallback: guardar HTML
    fallback_html = BASE_DIR / f"{OUTPUT_PREFIX}{lang}.html"
    fallback_html.write_text(html_content, encoding='utf-8')
    if not WEASYPRINT_AVAILABLE:
        print(f"[WARN] WeasyPrint no disponible: {WEASYPRINT_IMPORT_ERROR!r}")
    print(f"[WARN] No se pudo generar PDF. Fallback HTML: {fallback_html.name}")
    print("Para Playwright: pip install playwright && python -m playwright install chromium")
    print("Para WeasyPrint (dependencias nativas): https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation")

def detect_language(text: str) -> str:
    if not OLLAMA_AVAILABLE:
        print("[WARN] Ollama no está instalado. Usando 'es' por defecto.")
        return "es"
    
    prompt = f"You are a language detector. Respond with exactly 'es' if the text is Spanish, or 'en' if the text is English. Text: {text}"
    print("[Ollama] Detectando idioma...")
    try:
        response = ollama.chat(model=OLLAMA_MODEL, messages=[{'role': 'user', 'content': prompt}])
        content = response['message']['content'].strip().lower()
        if 'en' in content:
            return 'en'
        return 'es'
    except Exception as e:
        print(f"[Ollama][ERROR] No se pudo detectar idioma: {e}")
        return "es"

def translate_text(text: str, target_lang: str) -> str:
    if not OLLAMA_AVAILABLE:
        return text
    
    lang_name = "Professional English" if target_lang == "en" else "Professional Spanish"
    if target_lang == "en":
        example_in = "Desarrollé APIs REST para clientes enterprise."
        example_out = "Developed REST APIs for enterprise clients."
    else:
        example_in = "Developed REST APIs for enterprise clients."
        example_out = "Desarrollé APIs REST para clientes enterprise."
        
    prompt = f"""Role: You are an expert professional translator specializing in software engineering resumes.
Task: Translate the following text into {lang_name}.
Limits:
- DO NOT add any extra information.
- DO NOT provide explanations, notes, or conversational text.
- RETURN ONLY the translated text. Maintain formatting if any (like newlines).
Example Input: {example_in}
Example Output: {example_out}

Text to translate:
{text}"""

    print(f"[Ollama] Traduciendo bloque a {target_lang}...")
    try:
        response = ollama.chat(model=OLLAMA_MODEL, messages=[{'role': 'user', 'content': prompt}])
        return response['message']['content'].strip()
    except Exception as e:
        print(f"[Ollama][ERROR] Falla en traducción: {e}")
        return text

def translate_cv_data(data: dict, target_lang: str) -> dict:
    translated = copy.deepcopy(data)
    
    def t(text: str) -> str:
        if not text or not isinstance(text, str): return text
        return translate_text(text, target_lang)

    print(f"--- Iniciando traducción del CV completo a '{target_lang}' ---")
    
    if 'personal_info' in translated and 'title' in translated['personal_info']:
        translated['personal_info']['title'] = t(translated['personal_info']['title'])
        
    if 'summary' in translated:
        translated['summary'] = t(translated['summary'])
        
    for exp in translated.get('work_experience', []):
        if 'role' in exp: exp['role'] = t(exp['role'])
        if 'company' in exp: exp['company'] = t(exp['company'])
        if 'description' in exp: exp['description'] = t(exp['description'])

    for proj in translated.get('projects', []):
        if 'title' in proj: proj['title'] = t(proj['title'])
        if 'description' in proj: proj['description'] = t(proj['description'])
            
    for edu in translated.get('education', []):
        if 'degree' in edu: edu['degree'] = t(edu['degree'])
        if 'institution' in edu: edu['institution'] = t(edu['institution'])
        if 'Relevant subjects' in edu: edu['Relevant subjects'] = t(edu['Relevant subjects'])
        if 'Extracurricular activities' in edu:
            edu['Extracurricular activities'] = [t(c) for c in edu['Extracurricular activities']]
        if 'Relevant projects' in edu:
            edu['Relevant projects'] = [t(c) for c in edu['Relevant projects']]

    if 'certifications' in translated:
        translated['certifications'] = [t(c) for c in translated['certifications']]

    if 'courses' in translated:
        translated['courses'] = [t(c) for c in translated['courses']]
        
    # Tecnologías (skills) no se traducen.
    
    print("--- Traducción finalizada ---")
    return translated

def main():
    data = load_cv_data()
    
    summary_text = data.get('summary', '')
    if not summary_text:
        work = data.get('work_experience', [])
        summary_text = work[0].get('description', '') if work else ''
    if not summary_text:
        edu = data.get('education', [])
        summary_text = edu[0].get('degree', '') if edu else 'es'

    source_lang = detect_language(summary_text)
    print(f"Idioma base detectado: {source_lang}")

    for lang in ["es", "en"]:
        if lang == source_lang:
            data_lang = data
        else:
            data_lang = translate_cv_data(data, lang)
            
        render_to_pdf(data_lang, lang)

if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as fnf:
        print(f"[ERROR] Archivo no encontrado: {fnf}")
        sys.exit(1)
    except Exception as ex:
        print("[ERROR] Ejecución inesperada:")
        traceback.print_exc()
        sys.exit(1)
