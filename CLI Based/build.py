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

OLLAMA_MODEL = "gpt-oss:120b-cloud"
OLLAMA_THINK = "medium"   # 'low' | 'medium' | 'high' | False
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

# Archivos fuente estandarizados: mismo contenido y mismo esquema en dos
# idiomas. Elegir uno evita pasar por Ollama para ese idioma.
SOURCE_FILES = {
    "en": BASE_DIR / "resume.en.yaml",
    "es": BASE_DIR / "resume.es.yaml",
}
# Base historica de un solo idioma; se usa si no hay archivo estandarizado.
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
    # Derivado de 'generation', reordenado y ampliado para cubrir las cinco
    # secciones que exige ResumeShape.md (Capital One TDP).
    "capitalone": {
        "template": "capitalone.html.j2",
        "css": "capitalone.css",
        "margins": {"top": "12mm", "bottom": "10mm", "left": "13mm", "right": "13mm"},
        "fit_one_page": True,
        "base_font_px": 10.0,
        "min_font_px": 7.2,
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
    parser.add_argument('--source', choices=sorted(SOURCE_FILES.keys()), default=None,
                        help='YAML de origen: en -> resume.en.yaml, es -> resume.es.yaml '
                             '(si se omite, se pregunta en la terminal)')
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
        "label_portfolio": "Portafolio",
        # Encabezados propios del template 'capitalone' (nombres de ResumeShape.md)
        "section_technical_experience": "Experiencia Técnica",
        "section_technical_projects": "Proyectos Técnicos",
        "section_extracurriculars": "Extracurriculares",
        "label_languages": "Lenguajes",
        "label_frameworks": "Frameworks y Herramientas",
        "label_coursework": "Materias relevantes",
        "label_gpa": "Promedio",
        "label_hackathons": "Hackathones y Competencias",
        "label_academic_visits": "Visitas Académicas y de Investigación",
        "label_student_clubs": "Clubes Estudiantiles"
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
        "label_portfolio": "Portfolio",
        # Encabezados propios del template 'capitalone' (nombres de ResumeShape.md)
        "section_technical_experience": "Technical Experience",
        "section_technical_projects": "Technical Projects",
        "section_extracurriculars": "Extracurriculars",
        "label_languages": "Languages",
        "label_frameworks": "Frameworks & Tools",
        "label_coursework": "Relevant coursework",
        "label_gpa": "GPA",
        "label_hackathons": "Hackathons & Competitions",
        "label_academic_visits": "Academic & Research Visits",
        "label_student_clubs": "Student Clubs"
    }
}


def load_cv_data(path: Path = None):
    path = path or CV_FILE
    with path.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data


def resolve_source(preselected: str = None) -> tuple:
    """Elige el YAML de origen y devuelve (idioma, ruta).

    Con un archivo estandarizado el idioma base se conoce de antemano, asi que
    no hace falta preguntarselo a Ollama (`detect_language`).
    """
    available = {lang: p for lang, p in SOURCE_FILES.items() if p.exists()}

    if not available:
        print(f"[FUENTE] Sin archivos estandarizados; se usa {CV_FILE.name}.")
        return None, CV_FILE

    if preselected:
        if preselected in available:
            return preselected, available[preselected]
        print(f"[FUENTE][WARN] No existe {SOURCE_FILES[preselected].name}; se usa {CV_FILE.name}.")
        return None, CV_FILE

    names = sorted(available.keys())
    etiquetas = {"en": "inglés", "es": "español"}
    print("\nYAML de origen:")
    for i, lang in enumerate(names, start=1):
        print(f"{i}.- {available[lang].name:<18} ({etiquetas.get(lang, lang)})")
    print(f"{len(names) + 1}.- {CV_FILE.name:<18} (base histórica, idioma detectado)")

    choice = input(f"Elige una opción (1-{len(names) + 1}) [default 1]: ").strip()
    if choice.isdigit() and int(choice) == len(names) + 1:
        return None, CV_FILE
    if choice.isdigit() and 1 <= int(choice) <= len(names):
        lang = names[int(choice) - 1]
        return lang, available[lang]
    return names[0], available[names[0]]


# --- Filtro de contenido por vacante ---------------------------------------
# resume.yaml es la base completa del historial tecnico; cada vacante imprime un
# subconjunto. Cada elemento de lista lleva `include: true` explicito para que se
# vea el interruptor al abrir el archivo; basta cambiarlo a false para apagarlo
# sin borrar el contenido. La ausencia de la clave equivale a true.
INCLUDE_KEY = 'include'


def _label(item: dict) -> str:
    """Nombre legible de un elemento, para el log de lo que se oculto."""
    for key in ('title', 'name', 'role', 'degree', 'company', 'language',
                'exp', 'institution'):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return strip_markdown_links(value)[:45]
    return '?'


def prune_hidden(node, hidden: list):
    """Elimina recursivamente todo lo marcado con `include: false`.

    Se aplica ANTES de traducir y de renderizar, asi que lo oculto tampoco se
    envia al modelo: apagar contenido reduce las llamadas a Ollama.
    """
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key == INCLUDE_KEY:
                continue  # marca de control: no debe llegar al template
            if isinstance(value, dict) and value.get(INCLUDE_KEY) is False:
                hidden.append(key)
                continue
            out[key] = prune_hidden(value, hidden)
        return out

    if isinstance(node, list):
        kept = []
        for item in node:
            if isinstance(item, dict) and item.get(INCLUDE_KEY) is False:
                hidden.append(_label(item))
                continue
            kept.append(prune_hidden(item, hidden))
        return kept

    return node


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


# --- Capa de proteccion de PII -------------------------------------------
# Regla: la informacion que identifica al candidato NUNCA viaja al modelo.
# Los campos puramente identificatorios (name, email, phone, gpa, *_url) no
# estan en translate_cv_data, asi que jamas se envian. Pero un `summary` o una
# `description` puede mencionar un correo, una URL o el propio nombre: para eso
# esta este enmascarado, que sustituye cada aparicion por un centinela [[Pn]],
# traduce el texto ya anonimizado y reinserta el valor original al volver.
# Efecto secundario buscado: las URLs de los enlaces Markdown quedan intactas,
# el modelo ya no puede reescribirlas.

PII_SENTINEL_RE = re.compile(r'\[\[P\d+\]\]')

# Claves que se copian tal cual y que ninguna funcion debe mandar a Ollama.
NEVER_SENT_KEYS = frozenset({
    'name', 'email', 'phone', 'gpa', 'github_url', 'linkedin_url',
    'portfolio_url', 'url', 'issuer_url',
    'certificate_url', 'year',
})

_PII_TERMS: tuple = ()


def _collect_pii_terms(data: dict) -> tuple:
    """Terminos identificatorios a enmascarar dondequiera que aparezcan."""
    info = data.get('personal_info') or {}
    terms = set()
    for key in ('name', 'email', 'phone'):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            terms.add(value.strip())
    # Partes del nombre: "PIÑA" o "Diego" sueltos tambien identifican.
    name = info.get('name') or ''
    terms.update(part for part in re.split(r'\s+', name) if len(part) > 3)
    # Handles de las URLs (usuario de github/linkedin, subdominio del portafolio).
    for key in ('github_url', 'linkedin_url', 'portfolio_url'):
        url = info.get(key)
        if isinstance(url, str):
            terms.update(seg for seg in re.split(r'[/.]', url)
                         if len(seg) > 3 and seg not in
                         ('https:', 'http:', 'www', 'com', 'org', 'github', 'linkedin', 'github.io'))
    return tuple(sorted(terms, key=len, reverse=True))


def _protect_pii(text: str) -> tuple:
    """Devuelve (texto_enmascarado, tokens) listo para enviar al modelo."""
    tokens = {}

    def stash(value: str) -> str:
        key = f"[[P{len(tokens) + 1}]]"
        tokens[key] = value
        return key

    # 1. URL dentro de un enlace Markdown: se oculta la URL, el texto visible
    #    sigue siendo traducible.
    out = re.sub(r'(\[[^\]]+\]\s*\()(https?://[^\)]+)(\))',
                 lambda m: m.group(1) + stash(m.group(2)) + m.group(3), text)
    # 2. URLs sueltas, correos y telefonos.
    out = re.sub(r'https?://\S+', lambda m: stash(m.group(0)), out)
    out = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+', lambda m: stash(m.group(0)), out)
    out = re.sub(r'\+?\d[\d\s\-()]{7,}\d', lambda m: stash(m.group(0)), out)
    # 3. Nombre del candidato y handles.
    for term in _PII_TERMS:
        if term and term in out:
            out = out.replace(term, stash(term))
    return out, tokens


def _restore_pii(text: str, tokens: dict) -> str:
    for key, value in tokens.items():
        text = text.replace(key, value)
    return text


def detect_language(text: str) -> str:
    if not OLLAMA_AVAILABLE:
        print("[WARN] Ollama no está instalado. Usando 'es' por defecto.")
        return "es"

    # Aunque solo se detecte idioma, el texto sale del proceso: se enmascara.
    masked, _ = _protect_pii(text)
    prompt = (
        "<task>Identify the language of the text inside <sample>.</task>\n"
        "<output_contract>Reply with exactly one token: 'es' for Spanish or "
        "'en' for English. No punctuation, no explanation.</output_contract>\n"
        f"<sample>\n{masked}\n</sample>"
    )
    print("[Ollama] Detectando idioma...")
    try:
        # think=False a proposito: identificar un idioma no requiere razonamiento.
        response = ollama.chat(model=OLLAMA_MODEL,
                               messages=[{'role': 'user', 'content': prompt}],
                               think=False)
        content = response['message']['content'].strip().lower()
        token = re.sub(r'[^a-z]', '', content)[:2]
        return 'en' if token == 'en' else 'es'
    except Exception as e:
        print(f"[Ollama][ERROR] No se pudo detectar idioma: {e}")
        return "es"


# --- Prompt del traductor -------------------------------------------------
# Estructura segun "Peticion Robusta": rol y contexto de dominio en el mensaje
# de sistema; instruccion, datos delimitados e indicador de salida en el de
# usuario. Los datos van dentro de <source_text> para que el modelo distinga
# el contenido a traducir de las instrucciones (y no obedezca texto del CV).

TRANSLATOR_SYSTEM_PROMPT = """<role>
You are a senior bilingual (Spanish/English) translator and resume editor. You
specialize in software engineering resumes for technical recruiters and ATS
systems in Mexico and the United States.
</role>

<domain_context>
- The text comes from a single-source CV rendered to PDF. It is a fragment, not
  a whole document: it may be one line, one bullet, or one noun phrase.
- Register is professional, concise, resume-grade. Never conversational.
- The document must stay ATS-parseable: no emoji, no decorative characters, no
  Markdown headings, no bold or italic markers.
</domain_context>

<invariants>
These are absolute. Violating any one makes the output unusable.
1. Preserve the exact line structure. If the input has N lines, output N lines,
   in the same order. Never merge, split, reorder, add or drop a line.
2. Copy every [[Pn]] token verbatim, in its original position. These are
   redacted values that the program reinserts later. Never translate, renumber,
   reword, space out or remove them.
3. Preserve Markdown link syntax [visible text](target) exactly. Translate only
   the visible text; leave whatever is inside the parentheses untouched.
4. Do not translate proper nouns, brand or product names, technologies,
   programming languages, frameworks, tools, certifications, degrees awarded
   under an official name, or acronyms (AWS, IPN, SQL, .NET, Kali Linux).
5. Do not invent, infer, embellish or omit facts. No new metrics, no new
   technologies, no new achievements. The claims in the output must be exactly
   the claims in the input.
6. Keep numbers, dates, percentages and units exactly as given.
7. Every achievement or responsibility statement, anywhere in the CV, opens with
   an action verb in the SIMPLE PAST tense - bullets, project descriptions,
   extracurricular blurbs, research focus lines, summary clauses alike. This
   holds even for ongoing or current roles: the resume voice is uniformly past
   ("Developed", "Led", "Automated" / "Desarrolle", "Lidere", "Automatice"),
   never present, never gerund ("Developing", "Desarrollando"), never a
   noun-phrase or passive opener ("Responsible for", "Encargado de"). If the
   source violates this, recast the opening verb while preserving the meaning
   and every fact; do not rewrite anything else to accommodate the change.
</invariants>

<output_contract>
Return ONLY the translated text. No preamble, no explanation, no notes, no
quotation marks around the result, no "Here is the translation", no XML tags,
no Markdown fences. The very first character of your reply is the first
character of the translation.
</output_contract>"""

# Reglas por tipo de campo. Descomposicion de la tarea: cada tipo de campo es
# una subtarea con su propio criterio de calidad.
FIELD_RULES = {
    'prose': """<field_type>Professional summary paragraph.</field_type>
<style_rules>
- Keep it a single flowing paragraph. Do not turn it into bullets.
- Impersonal professional register, no subject pronouns ("Computer engineer
  focused on..." not "I am a computer engineer who...").
- Preserve the original sentence count.
</style_rules>""",
    'bullets': """<field_type>Resume bullet points, one per line.</field_type>
<style_rules>
- Each line is an independent bullet. Translate each line on its own.
- Start every bullet with a strong action verb in the SIMPLE PAST tense
  (Developed, Implemented, Built, Designed, Reduced, Automated / Desarrolle,
  Implemente, Construi, Disene, Reduje, Automatice). If the source line opens
  with a noun phrase or a gerund, recast it so it opens with that past-tense
  verb, but change nothing else about its meaning.
- Never open a bullet with "Responsible for", "Worked on", "Encargado de" or
  "Participe en".
- Do not add a leading dash, bullet glyph or number: the template draws those.
- Keep each bullet on one line and close to the source length. This CV is
  constrained to one printed page.
</style_rules>""",
    'short': """<field_type>Short label: a job title, company, institution, degree or date range.</field_type>
<style_rules>
- Output a noun phrase, not a sentence. No trailing period.
- Translate month names and connector words in date ranges ("Present"/"Actual",
  "June 2026 - September 2026"). Never alter the numbers.
- If the label is already a proper name or is identical in both languages,
  return it unchanged.
</style_rules>""",
    'list_item': """<field_type>Single skill or list entry.</field_type>
<style_rules>
- Return the direct equivalent term only. Three words at most.
- No article, no explanation, no trailing period.
</style_rules>""",
}


def _build_translation_messages(text: str, target_lang: str, kind: str) -> list:
    lang_name = "Professional English" if target_lang == "en" else "Professional Spanish"
    if target_lang == "en":
        example_in = "Desarrolle APIs REST para clientes enterprise usando [el SDK]([[P1]])."
        example_out = "Developed REST APIs for enterprise clients using [the SDK]([[P1]])."
    else:
        example_in = "Developed REST APIs for enterprise clients using [the SDK]([[P1]])."
        example_out = "Desarrolle APIs REST para clientes enterprise usando [el SDK]([[P1]])."

    rules = FIELD_RULES.get(kind, FIELD_RULES['short'])
    user = f"""<task>
Translate the text inside <source_text> into {lang_name}.
</task>

{rules}

<example>
<input>{example_in}</input>
<output>{example_out}</output>
</example>

<source_text>
{text}
</source_text>

Now output the {lang_name} translation of <source_text>, and nothing else."""

    return [
        {'role': 'system', 'content': TRANSLATOR_SYSTEM_PROMPT},
        {'role': 'user', 'content': user},
    ]


_PREAMBLE_RE = re.compile(
    r"^(here is the translation|here's the translation|translation|traduccion|"
    r"traduccion al [a-zA-Z]+)\s*[:\-]\s*", re.IGNORECASE)


def _clean_model_output(raw: str) -> str:
    """Quita los adornos tipicos que el modelo agrega pese al contrato."""
    out = raw.strip()
    out = re.sub(r'^```[a-zA-Z]*\n?', '', out)
    out = re.sub(r'\n?```$', '', out).strip()
    out = re.sub(r'^</?(source_text|output|translation)>\s*', '', out)
    out = re.sub(r'\s*</(source_text|output|translation)>$', '', out)
    out = _PREAMBLE_RE.sub('', out)
    return out.strip()


def translate_text(text: str, target_lang: str, kind: str = 'short') -> str:
    if not OLLAMA_AVAILABLE:
        return text

    # La PII se enmascara ANTES de que el texto salga del proceso.
    masked, tokens = _protect_pii(text)

    print(f"[Ollama] Traduciendo bloque ({kind}) a {target_lang}...")
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=_build_translation_messages(masked, target_lang, kind),
            think=OLLAMA_THINK)
        result = _clean_model_output(response['message']['content'])
    except Exception as e:
        print(f"[Ollama][ERROR] Falla en traduccion: {e}")
        return text

    if not result:
        print("[Ollama][WARN] Respuesta vacia; se conserva el texto original.")
        return text

    # Si el modelo perdio o invento un centinela, reinsertar corromperia el
    # dato: ante la duda se conserva el original sin traducir.
    missing = [k for k in tokens if k not in result]
    if missing:
        print(f"[Ollama][WARN] El modelo altero los marcadores {missing}; se conserva el original.")
        return text
    unknown = [m for m in PII_SENTINEL_RE.findall(result) if m not in tokens]
    if unknown:
        print(f"[Ollama][WARN] El modelo invento marcadores {unknown}; se conserva el original.")
        return text

    # Invariante de estructura: una linea de entrada, una linea de salida.
    if kind == 'bullets' and text.strip().count('\n') != result.count('\n'):
        print("[Ollama][WARN] Cambio el numero de vinetas del bloque; se conserva el original.")
        return text

    return _restore_pii(result, tokens)


def _translate_relevant_project(item, t):
    """'Relevant projects' admite string plano o mapping {title, subitems}."""
    if isinstance(item, dict):
        out = copy.deepcopy(item)
        if 'title' in out: out['title'] = t(out['title'], 'short')
        if 'subitems' in out: out['subitems'] = [t(x, 'bullets') for x in out['subitems']]
        return out
    return t(item, 'bullets')


def translate_cv_data(data: dict, target_lang: str) -> dict:
    global _PII_TERMS
    translated = copy.deepcopy(data)

    # Terminos identificatorios que se enmascararan en CADA llamada al modelo.
    _PII_TERMS = _collect_pii_terms(data)
    if _PII_TERMS:
        print(f"[PII] {len(_PII_TERMS)} terminos identificatorios se enmascararan antes de salir al modelo.")

    def t(text: str, kind: str = 'short') -> str:
        if not text or not isinstance(text, str): return text
        return translate_text(text, target_lang, kind)

    print(f"--- Iniciando traducción del CV completo a '{target_lang}' ---")

    if 'personal_info' in translated:
        # name, email, phone, gpa y *_url NO se envian nunca (NEVER_SENT_KEYS).
        if 'title' in translated['personal_info']:
            translated['personal_info']['title'] = t(translated['personal_info']['title'], 'short')
        if 'location' in translated['personal_info']:
            translated['personal_info']['location'] = t(translated['personal_info']['location'], 'short')

    if 'summary' in translated:
        translated['summary'] = t(translated['summary'], 'prose')

    for exp in translated.get('work_experience', []):
        if 'role' in exp: exp['role'] = t(exp['role'])
        if 'company' in exp: exp['company'] = t(exp['company'])
        if 'description' in exp: exp['description'] = t(exp['description'], 'bullets')
        if 'location' in exp: exp['location'] = t(exp['location'])
        if 'period' in exp: exp['period'] = t(exp['period'])

    for proj in translated.get('projects', []):
        if 'title' in proj: proj['title'] = t(proj['title'])
        if 'description' in proj: proj['description'] = t(proj['description'], 'bullets')
        if 'period' in proj: proj['period'] = t(proj['period'])

    for edu in translated.get('education', []):
        if 'degree' in edu: edu['degree'] = t(edu['degree'])
        if 'institution' in edu: edu['institution'] = t(edu['institution'])
        if 'period' in edu: edu['period'] = t(edu['period'])
        # 'gpa' se copia tal cual: es un dato identificatorio y numerico.
        if 'Relevant subjects' in edu: edu['Relevant subjects'] = t(edu['Relevant subjects'], 'prose')
        if 'Extracurricular activities' in edu:
            edu['Extracurricular activities'] = [t(c, 'bullets') for c in edu['Extracurricular activities']]
        if 'Relevant projects' in edu:
            edu['Relevant projects'] = [_translate_relevant_project(c, t) for c in edu['Relevant projects']]

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

    # Secciones de logros del template 'capitalone'. Sin esto pasarian en el
    # idioma original: translate_cv_data recorre una lista fija de campos.
    for item in translated.get('extracurriculars', []):
        if not isinstance(item, dict):
            continue
        if 'exp' in item: item['exp'] = t(item['exp'], 'short')
        if 'desc' in item: item['desc'] = t(item['desc'], 'prose')
        if 'event' in item: item['event'] = t(item['event'], 'prose')
        if 'date' in item: item['date'] = t(item['date'], 'short')

    for item in translated.get('hackathons', []):
        if not isinstance(item, dict):
            continue
        if 'achievement' in item: item['achievement'] = t(item['achievement'], 'short')
        if 'period' in item: item['period'] = t(item['period'], 'short')
        # 'name' es nombre propio del evento: no se traduce.

    for item in translated.get('academic_visits', []):
        if not isinstance(item, dict):
            continue
        if 'focus' in item: item['focus'] = t(item['focus'], 'bullets')
        if 'period' in item: item['period'] = t(item['period'], 'short')
        if 'institution' in item: item['institution'] = t(item['institution'], 'short')

    # Las habilidades blandas sí se traducen; las técnicas no.
    if 'skills' in translated and 'soft_skills' in translated['skills']:
        translated['skills']['soft_skills'] = [t(s, 'list_item') for s in translated['skills']['soft_skills']]

    # Idiomas hablados: se traduce el nombre del idioma, no el nivel (B2, C1...).
    for spoken in translated.get('spoken_languages', []):
        if isinstance(spoken, dict) and 'language' in spoken:
            spoken['language'] = t(spoken['language'], 'list_item')

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
        "capitalone": "una página, secciones de ResumeShape.md (Capital One TDP)",
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

    # El archivo estandarizado ya declara su idioma: no hay que detectarlo.
    known_lang, cv_path = resolve_source(args.source)
    print(f"Origen: {cv_path.name}" + (f" (idioma {known_lang})" if known_lang else ""))
    data = load_cv_data(cv_path)

    # Se filtra antes de traducir: lo apagado no se envia al modelo.
    hidden = []
    data = prune_hidden(data, hidden)
    if hidden:
        print(f"[FILTRO] {len(hidden)} elementos ocultos (include: false): {', '.join(hidden)}")

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
        if known_lang:
            source_lang = known_lang
        else:
            # Heurística rápida interna solo para cargar la interfaz web en jinja2
            en_indicators = [" the ", " and ", " of ", " with ", " for "]
            source_lang = "en" if any(ind in f" {summary_text.lower()} " for ind in en_indicators) else "es"
        render_to_pdf(data, source_lang, f"{OUTPUT_PREFIX}{template_name}.pdf", template_name)
    else:
        # Con un archivo estandarizado el idioma ya se conoce: se ahorra la
        # llamada a Ollama de detect_language.
        source_lang = known_lang or detect_language(summary_text)
        print(f"Idioma base: {source_lang}")

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
