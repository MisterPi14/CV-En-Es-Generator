import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import argparse
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

OLLAMA_MODEL = "gemma4:cloud"
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

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

CV_FILE = BASE_DIR / "resume.yaml"
OUTPUT_PREFIX = "resume_"

# Registro de templates ------------------------------------------------------
# Cada entrada concentra plantilla Jinja, hoja de estilo, márgenes de impresión
# y la política de ajuste a una sola página.
TEMPLATES = {
    "legacy": {
        "template": "legacy.html.j2",
        "css": "legacy.css",
        "margins": {"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"},
        "fit_one_page": False,
    },
    "generation": {
        "template": "generation.html.j2",
        "css": "generation.css",
        "margins": {"top": "12mm", "bottom": "10mm", "left": "13mm", "right": "13mm"},
        "fit_one_page": True,
        "base_font_px": 10.0,
        "min_font_px": 7.6,
        "step_px": 0.2,
    },
}
DEFAULT_TEMPLATE = "legacy"

# A4 a 96 dpi (px CSS) y factor mm -> px, usados por el auto-ajuste.
A4_WIDTH_PX = 794
A4_HEIGHT_PX = 1123
MM_TO_PX = 96 / 25.4


def parse_args():
    parser = argparse.ArgumentParser(description='Genera el CV en PDF a partir de resume.yaml')
    parser.add_argument('--template', choices=sorted(TEMPLATES.keys()), default=None,
                        help='Template a usar (si se omite, se pregunta en la terminal)')
    parser.add_argument('--lang', choices=['es', 'en', 'both'], default=None,
                        help='Idioma(s) a generar')
    parser.add_argument('--no-translate', action='store_true',
                        help='No usar Ollama: renderiza el YAML tal cual esta')
    return parser.parse_args()


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
        "section_technologies": "Tecnologías",
        # Encabezados propios del template 'generation'
        "section_profile": "Perfil Profesional",
        "section_technical_skills": "Habilidades Técnicas",
        "section_soft_skills": "Habilidades Blandas",
        "section_academic_project": "Proyecto Académico",
        "section_work": "Experiencia Laboral",
        "section_education_gen": "Formación Educativa",
        "section_courses_certs": "Cursos y Certificaciones",
        "section_spoken_languages": "Idiomas",
        "label_portfolio": "Portafolio"
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
        "section_technologies": "Technologies",
        # Encabezados propios del template 'generation'
        "section_profile": "Professional Profile",
        "section_technical_skills": "Technical Skills",
        "section_soft_skills": "Soft Skills",
        "section_academic_project": "Academic Project",
        "section_work": "Work Experience",
        "section_education_gen": "Education",
        "section_courses_certs": "Courses and Certifications",
        "section_spoken_languages": "Languages",
        "label_portfolio": "Portfolio"
    }
}


def load_cv_data():
    with CV_FILE.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data


def markdown_links(text: str) -> str:
    if not isinstance(text, str):
        return text
    return re.sub(r'\[([^\]]+)\]\s*\((https?://[^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)


def strip_markdown_links(text: str) -> str:
    """Devuelve solo el texto de un enlace Markdown, descartando la URL."""
    if not isinstance(text, str):
        return text
    return re.sub(r'\[([^\]]+)\]\s*\((https?://[^\)]+)\)', r'\1', text)


def _usable_page_px(margins: dict) -> tuple:
    """Area imprimible de una A4 en px CSS, descontando los margenes del registro."""
    def mm(value: str) -> float:
        return float(str(value).replace('mm', '').strip()) * MM_TO_PX

    width = A4_WIDTH_PX - mm(margins['left']) - mm(margins['right'])
    height = A4_HEIGHT_PX - mm(margins['top']) - mm(margins['bottom'])
    return int(width), int(height)


def _fit_to_one_page(page, cfg: dict) -> None:
    """Reduce la escala tipografica hasta que el contenido quepa en una pagina.

    El template expone `--fit-font` en :root y todo lo demas usa unidades
    relativas, asi que mover esa unica variable reescala el documento completo.
    """
    usable_w, usable_h = _usable_page_px(cfg['margins'])
    page.set_viewport_size({"width": usable_w, "height": usable_h})
    with contextlib.suppress(Exception):
        page.emulate_media(media="print")

    base = cfg.get('base_font_px', 10.0)
    minimum = cfg.get('min_font_px', 7.6)
    step = cfg.get('step_px', 0.2)

    size = base
    attempt = 0
    while size >= minimum - 1e-9:
        attempt += 1
        page.evaluate(
            "(s) => document.documentElement.style.setProperty('--fit-font', s + 'px')",
            round(size, 2)
        )
        height = page.evaluate("() => document.body.scrollHeight")
        ratio = height / usable_h
        status = "OK" if height <= usable_h else ""
        print(f"[FIT] intento {attempt}: {round(size, 2)}px -> {height}px ({ratio:.2f} paginas) {status}".rstrip())
        if height <= usable_h:
            return
        size -= step

    print(f"[FIT][WARN] Ni con el minimo legible ({minimum}px) el contenido cabe en una pagina.")
    print("[FIT][WARN] Recorta contenido del YAML (proyectos o cursos antiguos) o baja 'min_font_px'.")


def _count_pdf_pages(pdf_path: Path) -> int:
    """Conteo aproximado de paginas leyendo los objetos /Type /Page del PDF."""
    try:
        raw = pdf_path.read_bytes()
        return len(re.findall(rb'/Type\s*/Page[^s]', raw))
    except Exception:
        return -1


def _playwright_pdf(html_content: str, output_file: Path, base_dir: Path, cfg: dict) -> bool:
    """Intentar generar PDF usando Playwright Chromium.

    Devuelve True si tuvo éxito, False si no se pudo (imprime causa).
    Requiere que el usuario haya ejecutado:  python -m playwright install chromium
    """
    if not PLAYWRIGHT_AVAILABLE:
        print("[PLAYWRIGHT] No disponible el paquete. Instala con: pip install playwright")
        return False
    # Escribir HTML temporal DENTRO de base_dir: el template enlaza static/<css>
    # por ruta relativa, asi que el temporal debe quedar junto a static/.
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

            if cfg.get('fit_one_page'):
                _fit_to_one_page(page, cfg)

            page.pdf(
                path=str(output_file),
                format='A4',
                print_background=True,
                margin=cfg['margins']
            )
            browser.close()
        print(f"Generated {output_file.name} (Playwright)")

        if cfg.get('fit_one_page'):
            pages = _count_pdf_pages(output_file)
            if pages > 1:
                print(f"[FIT][WARN] El PDF final tiene {pages} paginas, no 1. Revisa el contenido del YAML.")
        return True
    except Exception as e:  # noqa
        print(f"[PLAYWRIGHT][ERROR] {e}")
        print("Si es la primera vez, instala navegador: python -m playwright install chromium")
        return False
    finally:
        with contextlib.suppress(Exception):
            tmp_path.unlink()


def render_to_pdf(data: dict, lang: str, output_name: str = None, template_name: str = DEFAULT_TEMPLATE):
    """Renderiza el CV a PDF (si WeasyPrint funciona) o genera fallback HTML.

    Si WeasyPrint no está disponible (falta libgobject/pango en Windows u otra dependencia),
    se genera un archivo HTML para inspección manual y se muestra una guía breve.
    """
    cfg = TEMPLATES[template_name]

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(['html', 'xml'])
    )
    env.filters['markdown_links'] = markdown_links
    env.filters['strip_links'] = strip_markdown_links
    template = env.get_template(cfg['template'])

    html_content = template.render(
        lang=lang,
        ui=UI_STRINGS[lang],
        css=cfg['css'],
        **data
    )

    if output_name:
        output_file = BASE_DIR / output_name
    else:
        output_file = BASE_DIR / f"{OUTPUT_PREFIX}{template_name}_{lang}.pdf"

    # WeasyPrint no soporta el auto-ajuste: medir requiere un navegador vivo.
    if WEASYPRINT_AVAILABLE and not cfg.get('fit_one_page'):
        try:
            HTML(string=html_content, base_url=str(BASE_DIR)).write_pdf(str(output_file))
            print(f"Generated {output_file.name} (WeasyPrint)")
            return
        except Exception:
            print("[WARN] WeasyPrint falló en tiempo de ejecución. Intentando Playwright...")
            traceback.print_exc()

    # Si no disponible WeasyPrint o falló, usar Playwright
    if _playwright_pdf(html_content, output_file, BASE_DIR, cfg):
        return

    # Último fallback: guardar HTML
    fallback_html = BASE_DIR / f"{OUTPUT_PREFIX}{template_name}_{lang}.html"
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

    if 'personal_info' in translated:
        if 'title' in translated['personal_info']:
            translated['personal_info']['title'] = t(translated['personal_info']['title'])
        if 'location' in translated['personal_info']:
            translated['personal_info']['location'] = t(translated['personal_info']['location'])

    if 'summary' in translated:
        translated['summary'] = t(translated['summary'])

    for exp in translated.get('work_experience', []):
        if 'role' in exp: exp['role'] = t(exp['role'])
        if 'company' in exp: exp['company'] = t(exp['company'])
        if 'description' in exp: exp['description'] = t(exp['description'])
        if 'location' in exp: exp['location'] = t(exp['location'])
        if 'period' in exp: exp['period'] = t(exp['period'])

    for proj in translated.get('projects', []):
        if 'title' in proj: proj['title'] = t(proj['title'])
        if 'description' in proj: proj['description'] = t(proj['description'])
        if 'period' in proj: proj['period'] = t(proj['period'])

    for edu in translated.get('education', []):
        if 'degree' in edu: edu['degree'] = t(edu['degree'])
        if 'institution' in edu: edu['institution'] = t(edu['institution'])
        if 'period' in edu: edu['period'] = t(edu['period'])
        if 'Relevant subjects' in edu: edu['Relevant subjects'] = t(edu['Relevant subjects'])
        if 'Extracurricular activities' in edu:
            edu['Extracurricular activities'] = [t(c) for c in edu['Extracurricular activities']]
        if 'Relevant projects' in edu:
            edu['Relevant projects'] = [t(c) for c in edu['Relevant projects']]

    def translate_credential(item):
        """Cursos y certificaciones: string plano o mapping {name, issuer, year, url}.

        Solo se traduce 'name'; 'issuer', 'year' y 'url' son nombres propios o datos.
        """
        if isinstance(item, dict):
            out = copy.deepcopy(item)
            if 'name' in out: out['name'] = t(out['name'])
            return out
        return t(item)

    if 'certifications' in translated:
        translated['certifications'] = [translate_credential(c) for c in translated['certifications']]

    if 'courses' in translated:
        translated['courses'] = [translate_credential(c) for c in translated['courses']]

    # Las habilidades blandas sí se traducen; las técnicas no.
    if 'skills' in translated and 'soft_skills' in translated['skills']:
        translated['skills']['soft_skills'] = [t(s) for s in translated['skills']['soft_skills']]

    # Idiomas hablados: se traduce el nombre del idioma, no el nivel (B2, C1...).
    for spoken in translated.get('spoken_languages', []):
        if isinstance(spoken, dict) and 'language' in spoken:
            spoken['language'] = t(spoken['language'])

    # Tecnologías (skills) no se traducen.

    print("--- Traducción finalizada ---")
    return translated


def choose_template(preselected: str = None) -> str:
    if preselected:
        return preselected

    names = sorted(TEMPLATES.keys(), key=lambda n: 0 if n == "legacy" else 1)
    descriptions = {
        "legacy": "diseño actual (barra de contacto negra, bloques inferiores)",
        "generation": "formato de una sola página, estilo Generation",
    }
    default_index = names.index(DEFAULT_TEMPLATE) + 1

    print("\nTemplate:")
    for i, name in enumerate(names, start=1):
        print(f"{i}.- {name:<12} ({descriptions.get(name, '')})")
    choice = input(f"Elige una opción (1-{len(names)}) [default {default_index}]: ").strip()

    if choice.isdigit() and 1 <= int(choice) <= len(names):
        return names[int(choice) - 1]
    return DEFAULT_TEMPLATE


def main():
    args = parse_args()
    data = load_cv_data()

    template_name = choose_template(args.template)
    print(f"Template seleccionado: {template_name}")

    # Modo no interactivo cuando vienen flags de idioma o traducción.
    if args.no_translate or args.lang:
        translate = not args.no_translate
        languages = ['es', 'en'] if args.lang in (None, 'both') else [args.lang]
    else:
        print("\nOpciones:")
        print("1.- Continuar sin traducir (generar PDF solo en idioma base)")
        print("2.- Continuar con traducción (generar PDFs en español e inglés)")
        opcion = input("Elige una opción (1 o 2) [default 2]: ").strip()
        translate = opcion != '1'
        languages = ['es', 'en']

    summary_text = data.get('summary', '')
    if not summary_text:
        work = data.get('work_experience', [])
        summary_text = work[0].get('description', '') if work else ''
    if not summary_text:
        edu = data.get('education', [])
        summary_text = edu[0].get('degree', '') if edu else 'es'

    if not translate:
        print(f"Generando {OUTPUT_PREFIX}{template_name}.pdf sin traducir...")
        # Heurística rápida interna solo para cargar la interfaz web en jinja2
        en_indicators = [" the ", " and ", " of ", " with ", " for "]
        source_lang = "en" if any(ind in f" {summary_text.lower()} " for ind in en_indicators) else "es"
        render_to_pdf(data, source_lang, f"{OUTPUT_PREFIX}{template_name}.pdf", template_name)
    else:
        source_lang = detect_language(summary_text)
        print(f"Idioma base detectado: {source_lang}")

        for lang in languages:
            if lang == source_lang:
                data_lang = data
            else:
                data_lang = translate_cv_data(data, lang)

            render_to_pdf(data_lang, lang, None, template_name)


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
