import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import argparse
import sys
import traceback
import tempfile
import contextlib
import copy
import json
import math
import re

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

# Modelo del traductor. El valor por defecto se usa hasta que el menu
# "Configuracion" de run.bat guarde otro en settings.json (junto a build.py).
DEFAULT_OLLAMA_MODEL = "gpt-oss:20b-cloud"
SETTINGS_FILE = Path(__file__).parent / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[CONFIG][WARN] settings.json ilegible ({e}); se usan los valores por defecto.")
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding='utf-8')


_SETTINGS = load_settings()
OLLAMA_MODEL = _SETTINGS.get('ollama_model') or DEFAULT_OLLAMA_MODEL
OLLAMA_THINK = "low"   # 'low' | 'medium' | 'high' | False
# Solo los modelos con capacidad 'thinking' aceptan `think`; a los demas
# Ollama les rechaza la llamada. Se guarda al elegir el modelo.
OLLAMA_SUPPORTS_THINK = _SETTINGS.get('ollama_thinking', True)


def _think_arg(value):
    """`think` solo si el modelo razona; si no, se omite (None)."""
    return value if OLLAMA_SUPPORTS_THINK else None
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
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError  # type: ignore
    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# Cualquier *.yaml del directorio es una fuente valida: los escritos a mano
# (resume.es.yaml, resume.en.yaml) y los derivados que escribe el modo
# translate (resume.<lang>.<modelo>.yaml). `discover_yamls()` los lista.
CV_FILE = BASE_DIR / "resume.yaml"   # default de load_cv_data si no se pasa ruta
OUTPUT_PREFIX = "resume_"            # solo para nombres de salida sin --output

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
        "warn_font_px": 6.0,   # no es un minimo: solo avisa por debajo de esto
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
        "warn_font_px": 6.0,   # no es un minimo: solo avisa por debajo de esto
        "step_px": 0.2,
    },
}
DEFAULT_TEMPLATE = "legacy"

# A4 a 96 dpi (px CSS) y factor mm -> px, usados por el auto-ajuste.
A4_WIDTH_PX = 794
A4_HEIGHT_PX = 1123
MM_TO_PX = 96 / 25.4


def parse_args():
    parser = argparse.ArgumentParser(
        description='Genera YAMLs traducidos del CV, o PDFs a partir de cualquiera de ellos')
    parser.add_argument('--mode', choices=['translate', 'pdf', 'config'], default=None,
                        help="'translate' escribe un YAML nuevo traducido; 'pdf' renderiza "
                             "uno existente; 'config' abre los ajustes (si se omite, se "
                             'pregunta en la terminal)')
    parser.add_argument('--input', default=None,
                        help='YAML de entrada: nombre o ruta. Si se omite, se listan los '
                             'del directorio para elegir')
    parser.add_argument('--from', dest='from_lang', choices=['es', 'en'], default=None,
                        help='Idioma del YAML de entrada (si se omite, se deduce del nombre)')
    parser.add_argument('--to', dest='to_lang', choices=['es', 'en'], default=None,
                        help='modo translate: idioma destino de la traduccion')
    parser.add_argument('--template', choices=sorted(TEMPLATES.keys()), default=None,
                        help='modo pdf: template a usar')
    parser.add_argument('--output', default=None,
                        help='Nombre del archivo de salida (si se omite, se deriva del '
                             'YAML de entrada)')
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
        "section_work": "Experiencia Técnica",
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
        "label_relevant_subjects": "Materias relevantes",
        "label_gpa": "Promedio",
        "label_hackathons": "Hackathones y Competencias",
        "section_academic_visits": "Visitas Académicas y de Investigación",
        "label_student_clubs": "Clubes Estudiantiles",
        "label_extracurricular_activities": "Actividades extracurriculares",
        "label_relevant_projects": "Proyectos relevantes",
        "label_linkedin": "LinkedIn",
        "label_github": "GitHub",
        "label_certificate": "Certificaciones",
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
        "label_relevant_subjects": "Relevant subjects",
        "label_gpa": "GPA",
        "label_hackathons": "Hackathons & Competitions",
        "section_academic_visits": "Academic & Research Visits",
        "label_student_clubs": "Student Clubs",
        "label_extracurricular_activities": "Extracurricular activities",
        "label_relevant_projects": "Relevant projects",
        "label_linkedin": "LinkedIn",
        "label_github": "GitHub",
        "label_certificate": "Certifications",
    }
}


def validate_ui(data: dict) -> None:
    """Detecta errores de edición antes de renderizar o llamar al traductor."""
    allowed = set(UI_STRINGS['es']) | {'document_title'}

    def check_labels(labels, path):
        if not isinstance(labels, dict):
            raise ValueError(f"{path} debe ser un mapping de claves y textos.")
        for key, value in labels.items():
            if key not in allowed:
                raise ValueError(f"Clave de texto desconocida: {path}.{key}")
            if not isinstance(value, str):
                raise ValueError(f'{path}.{key} debe ser texto entre comillas; usa "" para dejarlo vacío.')

    check_labels(data.get('ui', {}), 'ui')
    overrides = data.get('ui_templates', {})
    if not isinstance(overrides, dict):
        raise ValueError('ui_templates debe ser un mapping de nombres de template.')
    for name, labels in overrides.items():
        if name not in TEMPLATES:
            raise ValueError(f'Template desconocido en ui_templates: {name}')
        check_labels(labels, f'ui_templates.{name}')


def resolve_ui(data: dict, lang: str, template_name: str) -> dict:
    """Predeterminados por idioma/template < ui del YAML < ui_templates."""
    validate_ui(data)
    labels = dict(UI_STRINGS[lang])
    info = data.get('personal_info') or {}
    labels['document_title'] = f"{info.get('name', '')} - CV"
    # Conservar la presentación de los archivos anteriores, sin ui.
    if template_name == 'legacy':
        labels['label_linkedin'] = (info.get('name') or '').title()
        labels['label_github'] = (info.get('github_url') or '').split('/')[-1]
    elif template_name == 'generation':
        labels['label_github'] = 'Github'
    labels.update(data.get('ui', {}))
    labels.update(data.get('ui_templates', {}).get(template_name, {}))
    return labels


def load_cv_data(path: Path = None):
    path = path or CV_FILE
    with path.open('r', encoding='utf-8') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            # Sin esto el fallo sale como traceback de PyYAML y no dice ni el
            # archivo ni la causa tipica (un valor con `[...]` sin comillas).
            mark = getattr(e, 'problem_mark', None)
            where = f" (linea {mark.line + 1}, columna {mark.column + 1})" if mark else ""
            print(f"[YAML][ERROR] '{path.name}' no es YAML valido{where}: {e}")
            print("[YAML][ERROR] Revisa la indentación y las claves cercanas a esa línea; "
                  "los valores que empiezan con '[' deben ir entre comillas.")
            sys.exit(1)
    return data


def dump_cv_data(data: dict, path: Path) -> None:
    """Escribe el CV traducido como YAML legible y editable a mano.

    Los `description` multilinea se emiten como bloque literal (`|`) para que el
    archivo derivado se lea igual que los escritos a mano; con el estilo por
    defecto saldrian como una sola linea con `\\n` incrustados.
    """
    class _Dumper(yaml.SafeDumper):
        pass

    def _str_representer(dumper, value):
        style = '|' if '\n' in value else None
        return dumper.represent_scalar('tag:yaml.org,2002:str', value, style=style)

    _Dumper.add_representer(str, _str_representer)

    header = (f"# Generado por build.py --mode translate\n"
              f"# Modelo traductor: {OLLAMA_MODEL}\n"
              f"# NO editar a mano esperando que se regenere igual: cada corrida\n"
              f"# del modelo produce una redaccion ligeramente distinta.\n\n")
    body = yaml.dump(data, Dumper=_Dumper, allow_unicode=True,
                     sort_keys=False, default_flow_style=False, width=4096)

    # Guarda de ida y vuelta: el derivado es la ENTRADA del modo pdf, asi que
    # un YAML invalido no se descubre aqui sino con un traceback de PyYAML en
    # la corrida siguiente, despues de haber pagado la traduccion completa.
    # El caso que la motiva: un valor como `[Texto](url)` sin comillas se lee
    # como secuencia de flujo y rompe el bloque entero.
    try:
        yaml.safe_load(header + body)
    except yaml.YAMLError as e:
        print(f"[YAML][ERROR] El archivo generado NO es YAML valido: {e}")
        print("[YAML][ERROR] Se escribe igual para poder inspeccionarlo, pero "
              "'--mode pdf' fallara hasta corregirlo a mano.")

    with path.open('w', encoding='utf-8') as f:
        f.write(header)
        f.write(body)


# --- Descubrimiento y seleccion de archivos --------------------------------
# Cualquier *.yaml del directorio sirve de entrada, tanto los escritos a mano
# como los derivados que produce el modo translate.
LANG_LABELS = {"es": "español", "en": "inglés"}


def discover_yamls() -> list:
    return sorted(BASE_DIR.glob('*.yaml'), key=lambda p: p.name)


def lang_from_name(path: Path):
    """Deduce el idioma del nombre: resume.en.<lo-que-sea>.yaml -> 'en'."""
    for part in path.name.lower().split('.'):
        if part in LANG_LABELS:
            return part
    return None


def model_slug(model: str = None) -> str:
    """Tag de Ollama apto para nombre de archivo: 'gpt-oss:20b-cloud' -> 'gpt-oss-20b-cloud'.

    Se conserva el tag completo, sufijo de transporte incluido, para poder
    distinguir una traduccion hecha en local de una hecha en la nube.
    """
    return re.sub(r'[^A-Za-z0-9._-]+', '-', (model or OLLAMA_MODEL)).strip('-')


def source_stem(path: Path) -> str:
    """Nombre base del YAML de origen, sin idioma ni modelo.

    Se conserva para que el derivado quede junto a su fuente y no la pise:
    `resume2.es.yaml` produce `resume2.en.<modelo>.yaml`, no `resume.en...`.
    Se corta en el primer token de idioma, asi que retraducir un derivado
    (`resume.en.gpt-oss.yaml`) vuelve a `resume`, en vez de encadenar modelos.
    """
    tokens = path.stem.split('.')
    base = []
    for token in tokens:
        if token.lower() in LANG_LABELS:
            break
        base.append(token)
    return '.'.join(base) or tokens[0]


def derived_yaml_name(src_path: Path, dst_lang: str, model: str = None) -> str:
    return f"{source_stem(src_path)}.{dst_lang}.{model_slug(model)}.yaml"


def choose_yaml(preselected: str = None, prompt: str = "YAML de entrada") -> Path:
    """Elige un YAML del directorio: por flag o listando los disponibles."""
    if preselected:
        candidate = Path(preselected)
        if not candidate.is_absolute():
            candidate = BASE_DIR / preselected
        if not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate

    files = discover_yamls()
    if not files:
        raise FileNotFoundError(f"No hay ningun *.yaml en {BASE_DIR}")

    print(f"\n{prompt}:")
    for i, path in enumerate(files, start=1):
        lang = lang_from_name(path)
        etiqueta = LANG_LABELS.get(lang, "idioma sin declarar")
        print(f"{i}.- {path.name:<40} ({etiqueta})")

    choice = input(f"Elige una opción (1-{len(files)}) [default 1]: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(files):
        return files[int(choice) - 1]
    return files[0]


def choose_lang(prompt: str, default: str = None) -> str:
    names = sorted(LANG_LABELS.keys())
    default = default if default in names else names[0]
    print(f"\n{prompt}:")
    for i, lang in enumerate(names, start=1):
        marca = "  [default]" if lang == default else ""
        print(f"{i}.- {lang}  ({LANG_LABELS[lang]}){marca}")
    choice = input(f"Elige una opción (1-{len(names)}) [default {names.index(default) + 1}]: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(names):
        return names[int(choice) - 1]
    return default


def choose_mode(preselected: str = None) -> str:
    if preselected:
        return preselected
    print("\nQué quieres hacer:")
    print("1.- Traducir un YAML y guardar el resultado como otro YAML")
    print("2.- Generar un PDF a partir de un YAML existente")
    print("3.- Configuración")
    print("0.- Salir")
    choice = input("Elige una opción (0-3) [default 2]: ").strip()
    return {'1': 'translate', '3': 'config', '0': 'exit'}.get(choice, 'pdf')


# --- Configuracion ------------------------------------------------------------
# Ajustes que se guardan en settings.json y se aplican en las corridas
# siguientes. Para agregar un ajuste: una funcion configure_<x>() y una linea
# en CONFIG_OPTIONS.
EMBEDDING_FAMILIES = frozenset({'bert', 'nomic-bert', 'jina-bert', 'xlm-roberta'})


def _is_cloud_model(name: str, entry=None) -> bool:
    """Los modelos de la nube de Ollama llevan el sufijo 'cloud' en el tag."""
    tag = name.split(':', 1)[-1].lower()
    return tag == 'cloud' or tag.endswith('-cloud') or bool(getattr(entry, 'remote_host', None))


def list_llm_models() -> list:
    """Modelos de lenguaje del Ollama local, incluidos los de la nube.

    Se descartan los de embeddings: primero por las capacidades que reporta
    `ollama show` ('completion' vs 'embedding'); si esta version no las
    reporta, por familia o nombre. Devuelve [{name, cloud, thinking, size}].
    """
    response = ollama.list()
    models = []
    for entry in response.models:
        name = entry.model
        caps = None
        with contextlib.suppress(Exception):
            caps = ollama.show(name).capabilities
        if caps:
            if 'completion' not in caps:
                continue
            thinking = 'thinking' in caps
        else:
            family = (getattr(entry.details, 'family', '') or '').lower()
            if family in EMBEDDING_FAMILIES or 'embed' in name.lower():
                continue
            thinking = True   # sin datos: se intenta y, si falla, se desactiva
        size = getattr(entry, 'size', None) or 0
        models.append({'name': name, 'cloud': _is_cloud_model(name, entry),
                       'thinking': thinking, 'size': size})
    return sorted(models, key=lambda m: (m['cloud'], m['name']))


# Catalogo publico de modelos de la nube de Ollama (no requiere sesion para
# listarlos; si para usarlos: `ollama signin` y creditos en la cuenta).
CLOUD_CATALOG_URL = "https://ollama.com/api/tags"
CLOUD_PAGE_SIZE = 10


def cloud_local_name(name: str) -> str:
    """Nombre del catalogo -> tag que acepta el Ollama local.

    'gpt-oss:20b' -> 'gpt-oss:20b-cloud'; 'kimi-k2.6' -> 'kimi-k2.6:cloud'.
    """
    if _is_cloud_model(name):
        return name
    return f"{name}-cloud" if ':' in name else f"{name}:cloud"


def list_cloud_models() -> list:
    """Modelos de lenguaje del catalogo de la nube, del mas reciente al mas antiguo.

    Solo los que declaran la capacidad 'completion' (se descartan embeddings y
    otros usos). Devuelve [{name, cloud, thinking, vision, size, date}].
    """
    import urllib.request
    request = urllib.request.Request(CLOUD_CATALOG_URL, headers={'User-Agent': 'cv-cli'})
    with urllib.request.urlopen(request, timeout=10) as response:
        catalog = json.load(response).get('models', [])
    models = []
    for entry in catalog:
        caps = entry.get('capabilities') or []
        if 'completion' not in caps:
            continue
        models.append({'name': cloud_local_name(entry.get('model') or entry['name']),
                       'cloud': True, 'thinking': 'thinking' in caps,
                       'vision': 'vision' in caps, 'size': entry.get('size') or 0,
                       'date': (entry.get('modified_at') or '')[:10]})
    return sorted(models, key=lambda m: m['date'], reverse=True)


def _save_model(settings: dict, name: str, thinking: bool) -> None:
    global OLLAMA_MODEL, OLLAMA_SUPPORTS_THINK
    settings['ollama_model'] = name
    settings['ollama_thinking'] = thinking
    save_settings(settings)
    OLLAMA_MODEL, OLLAMA_SUPPORTS_THINK = name, thinking
    print(f"Modelo guardado: {OLLAMA_MODEL}. Los YAML traducidos llevarán '{model_slug()}' en el nombre.")


def _pick_local(settings: dict) -> None:
    try:
        models = [m for m in list_llm_models() if not m['cloud']]
    except Exception as e:
        print(f"[CONFIG][ERROR] No se pudo consultar Ollama: {e}")
        print("Abre Ollama (o ejecuta 'ollama serve') y vuelve a intentarlo.")
        return
    if not models:
        print("[CONFIG] No hay modelos de lenguaje locales. Descarga uno con 'ollama pull <modelo>'.")
        return
    print("\nModelos locales:")
    for i, m in enumerate(models, start=1):
        mark = "  [actual]" if m['name'] == OLLAMA_MODEL else ""
        think = "razona" if m['thinking'] else ""
        print(f"{i:>2}.- {m['name']:<28} {m['size'] / 1e9:>5.1f} GB  {think}{mark}")
    choice = input(f"Elige una opción (1-{len(models)}) [Enter = volver]: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(models):
        chosen = models[int(choice) - 1]
        _save_model(settings, chosen['name'], chosen['thinking'])


def _pick_cloud(settings: dict) -> None:
    try:
        models = list_cloud_models()
    except Exception as e:
        print(f"[CONFIG][ERROR] No se pudo leer el catálogo de la nube ({e}).")
        print("Revisa la conexión a Internet; los modelos locales siguen disponibles.")
        return
    installed = set()
    with contextlib.suppress(Exception):
        installed = {m.model for m in ollama.list().models}
    print("\nPara usar un modelo de la nube, Ollama debe tener sesión iniciada "
          "('ollama signin') y la cuenta, créditos o suscripción.")

    query, page = '', 0
    while True:
        shown = [m for m in models if query.lower() in m['name'].lower()]
        pages = max(1, -(-len(shown) // CLOUD_PAGE_SIZE))
        page = min(page, pages - 1)
        start = page * CLOUD_PAGE_SIZE
        title = f" que contienen '{query}'" if query else ""
        print(f"\nModelos de la nube{title} (página {page + 1} de {pages}):")
        if not shown:
            print("  (ninguno)")
        for i, m in enumerate(shown[start:start + CLOUD_PAGE_SIZE], start=start + 1):
            size = f"{m['size'] / 1e9:>5.0f} GB" if m['size'] else "    —   "
            tags = " · ".join(t for t, on in (("razona", m['thinking']), ("visión", m['vision'])) if on)
            marks = ("  [actual]" if m['name'] == OLLAMA_MODEL else "") + \
                    ("  [instalado]" if m['name'] in installed else "")
            print(f"{i:>2}.- {m['name']:<30} {size}  {tags:<15} {m['date']}{marks}")
        choice = input("Número para elegir · m = más · texto para filtrar · Enter = volver: ").strip()
        if not choice:
            if query:          # Enter con filtro activo: lo quita
                query, page = '', 0
                continue
            return
        if choice.lower() == 'm':
            page = (page + 1) % pages
        elif choice.isdigit():
            n = int(choice)
            if 1 <= n <= len(shown):
                chosen = shown[n - 1]
                _save_model(settings, chosen['name'], chosen['thinking'])
                return
            print("Número fuera de la lista.")
        else:
            query, page = choice, 0


def _pick_manual(settings: dict) -> None:
    name = input("Nombre del modelo tal como lo acepta Ollama (ej. gemma4:12b, kimi-k2.6:cloud): ").strip()
    if not name:
        return
    thinking = True
    try:
        caps = ollama.show(name).capabilities or []
        if caps and 'completion' not in caps:
            print(f"[CONFIG][ERROR] '{name}' no es un modelo de lenguaje (capacidades: {', '.join(caps)}).")
            return
        thinking = 'thinking' in caps if caps else True
    except Exception as e:
        # Un modelo de la nube no descargado puede no responder a `show`:
        # se guarda igual y la primera traduccion confirma si funciona.
        print(f"[CONFIG][WARN] Ollama no reconoce '{name}' todavía ({e}); se guarda igualmente.")
    _save_model(settings, name, thinking)


def configure_model(settings: dict) -> None:
    if not OLLAMA_AVAILABLE:
        print("[CONFIG][ERROR] Falta el paquete 'ollama' en el entorno.")
        return
    local_count = cloud_count = '?'
    with contextlib.suppress(Exception):
        local_count = len([m for m in list_llm_models() if not m['cloud']])
    with contextlib.suppress(Exception):
        cloud_count = len(list_cloud_models())
    print(f"\nModelo de traducción (actual: {OLLAMA_MODEL})")
    print(f"1.- Locales ({local_count})")
    print(f"2.- Nube ({cloud_count})")
    print("3.- Escribir el nombre a mano")
    print("0.- Volver")
    choice = input("Elige una opción (0-3) [default 0]: ").strip()
    {'1': _pick_local, '2': _pick_cloud, '3': _pick_manual}.get(choice, lambda s: None)(settings)


CONFIG_OPTIONS = [
    ("Modelo de traducción (Ollama)", configure_model),
]


def run_config() -> None:
    """Submenu de ajustes. Vuelve al menu principal al terminar."""
    settings = load_settings()
    while True:
        print("\nConfiguración:")
        for i, (label, _) in enumerate(CONFIG_OPTIONS, start=1):
            print(f"{i}.- {label}")
        print("0.- Volver")
        choice = input(f"Elige una opción (0-{len(CONFIG_OPTIONS)}) [default 0]: ").strip()
        if not (choice.isdigit() and 1 <= int(choice) <= len(CONFIG_OPTIONS)):
            return
        CONFIG_OPTIONS[int(choice) - 1][1](settings)


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


# --- Secciones: orden, titulos en la clave y secciones nuevas ---------------
# Tres reglas, todas resueltas solo con el YAML:
#  1. Las secciones se imprimen en el orden de sus claves en el YAML.
#  2. `clave(Titulo)` renombra una seccion conocida sin cambiar su formato.
#  3. Una clave desconocida es una seccion nueva con formato generico; su
#     titulo es el texto entre parentesis o, si no lo hay, la clave misma.
SECTION_KEY_RE = re.compile(r'^(?P<base>.*?)\s*\((?P<title>[^()]*)\)\s*$')

# Claves de control o de cabecera: nunca son secciones ni admiten titulo.
NON_SECTION_KEYS = frozenset({'personal_info', 'ui', 'ui_templates'})

# Por template: clave del YAML -> bloques del template que dibuja, en orden.
# Un bloque compartido por varias claves (la rejilla de `legacy`, los
# extracurriculares de `capitalone`) se imprime donde aparece la primera.
SECTION_BLOCKS = {
    "legacy": {
        "education": ["education"], "work_experience": ["experience"],
        "projects": ["projects"], "skills": ["grid"], "courses": ["grid"],
        "certifications": ["grid"],
    },
    "generation": {
        "summary": ["summary"], "skills": ["technical_skills", "soft_skills"],
        "projects": ["projects"], "work_experience": ["experience"],
        "education": ["education"], "courses": ["credentials"],
        "certifications": ["credentials"], "spoken_languages": ["spoken_languages"],
    },
    "capitalone": {
        "summary": ["summary"], "education": ["education"],
        "work_experience": ["experience"], "projects": ["projects"],
        "skills": ["technical_skills", "soft_skills"],
        "certifications": ["certifications"], "courses": ["courses"],
        "academic_visits": ["academic_visits"],
        "extracurriculars": ["extracurriculars"], "hackathons": ["extracurriculars"],
        "spoken_languages": ["spoken_languages"],
    },
}

# Por template: clave del YAML -> etiqueta `ui` que `clave(Titulo)` reemplaza.
SECTION_TITLE_LABELS = {
    "legacy": {
        "education": "section_education", "work_experience": "section_experience",
        "projects": "section_projects", "courses": "section_courses",
        "certifications": "section_certifications",
    },
    "generation": {
        "summary": "section_profile", "skills": "section_technical_skills",
        "projects": "section_academic_project", "work_experience": "section_work",
        "education": "section_education_gen", "courses": "section_courses_certs",
        "certifications": "section_courses_certs",
        "spoken_languages": "section_spoken_languages",
    },
    "capitalone": {
        "summary": "section_profile", "education": "section_education_gen",
        "work_experience": "section_technical_experience",
        "projects": "section_technical_projects", "skills": "section_technical_skills",
        "certifications": "section_certifications", "courses": "section_courses",
        "academic_visits": "section_academic_visits",
        "extracurriculars": "section_extracurriculars", "hackathons": "label_hackathons",
        "spoken_languages": "section_spoken_languages",
    },
}

# Union de lo que algun template sabe dibujar: lo demas es seccion nueva.
KNOWN_SECTION_KEYS = frozenset(k for blocks in SECTION_BLOCKS.values() for k in blocks)

# Campos de una entrada de seccion nueva, por papel (el primero presente gana).
CUSTOM_TITLE_FIELDS = ('name', 'title', 'exp', 'role', 'degree', 'company', 'institution', 'language')
CUSTOM_PERIOD_FIELDS = ('period', 'date', 'year')
CUSTOM_TEXT_FIELDS = ('description', 'desc', 'focus', 'event', 'achievement')


def split_section_key(key) -> tuple:
    """'extracurriculars(Actividades)' -> ('extracurriculars', 'Actividades').

    Sin parentesis, o con parentesis vacios, el titulo es None.
    """
    if not isinstance(key, str):
        return key, None
    match = SECTION_KEY_RE.match(key)
    if not match or not match.group('base').strip():
        return key.strip(), None
    title = match.group('title').strip()
    return match.group('base').strip(), (title or None)


def _has_content(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def normalize_sections(data: dict) -> dict:
    """Separa las claves del YAML en datos, orden, titulos y secciones nuevas.

    Devuelve `data` (claves conocidas sin parentesis), `order` (claves base en
    el orden del YAML), `titles` (titulo entre parentesis de cada clave) y
    `custom` (secciones nuevas: {'key', 'title', 'content'}).
    """
    clean, order, titles, custom = {}, [], {}, []
    for raw_key, value in data.items():
        base, title = split_section_key(raw_key)
        if base in NON_SECTION_KEYS:
            if base in clean:
                raise ValueError(f"La clave '{base}' aparece dos veces en el YAML.")
            clean[base] = value
            continue
        if base in KNOWN_SECTION_KEYS:
            if base in clean:
                raise ValueError(f"La seccion '{base}' aparece dos veces en el YAML "
                                 f"(revisa '{raw_key}').")
            clean[base] = value
            order.append(base)
            if title:
                titles[base] = title
            continue
        # Seccion nueva: solo se imprime si tiene contenido.
        if _has_content(value):
            custom.append({'key': base, 'title': title or base, 'content': value})
            order.append(('custom', len(custom) - 1))
    return {'data': clean, 'order': order, 'titles': titles, 'custom': custom}


def section_sequence(order: list, template_name: str, data: dict) -> list:
    """Bloques del template en el orden del YAML, sin repetir los compartidos."""
    blocks = SECTION_BLOCKS[template_name]
    sequence, seen = [], set()
    for entry in order:
        if isinstance(entry, tuple):
            sequence.append(f"custom:{entry[1]}")
            continue
        for block in blocks.get(entry, []):
            if block not in seen:
                seen.add(block)
                sequence.append(block)
    # Los clubes de `capitalone` salen de education[].Extracurricular activities:
    # si no hay clave extracurriculars ni hackathons, el bloque va tras educacion.
    if template_name == 'capitalone' and 'extracurriculars' not in seen:
        has_clubs = any((edu or {}).get('Extracurricular activities')
                        for edu in data.get('education') or [] if isinstance(edu, dict))
        if has_clubs and 'education' in sequence:
            sequence.insert(sequence.index('education') + 1, 'extracurriculars')
    return sequence


def custom_entries(content) -> dict:
    """Normaliza el contenido de una seccion nueva para la plantilla generica.

    Formas admitidas: un texto (parrafo), una lista de textos o de entradas
    {name/title/..., period/date, description/desc/..., url}, o un mapping
    clave -> valor que se imprime como lineas 'Clave: valor'.
    """
    if isinstance(content, str):
        return {'paragraph': content.strip(), 'items': []}
    if isinstance(content, dict):
        lines = []
        for key, value in content.items():
            if isinstance(value, list):
                value = ' | '.join(str(v) for v in value)
            if _has_content(value):
                lines.append({'label': str(key), 'text': str(value)})
        return {'paragraph': None, 'items': [], 'lines': lines}
    items = []
    for item in content or []:
        if isinstance(item, dict):
            title = next((item[f] for f in CUSTOM_TITLE_FIELDS if _has_content(item.get(f))), None)
            period = next((item[f] for f in CUSTOM_PERIOD_FIELDS if _has_content(item.get(f))), None)
            text = next((item[f] for f in CUSTOM_TEXT_FIELDS if _has_content(item.get(f))), None)
            bullets = [line.strip() for line in str(text).split('\n') if line.strip()] if text else []
            items.append({'title': title, 'period': period, 'url': item.get('url'),
                          'bullets': bullets})
        elif _has_content(item):
            items.append({'title': None, 'period': None, 'url': None, 'bullets': [str(item)]})
    return {'paragraph': None, 'items': items}


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


# Ningun contenido se recorta para caber: la letra baja lo necesario. Este
# piso solo existe para que el bucle termine; por debajo de `warn_font_px`
# se avisa de que la impresion sera dificil de leer.
FIT_ABSOLUTE_FLOOR_PX = 2.0


FIT_CEILING_PX = 300.0     # tope de crecimiento: basta para llenar con muy poco contenido
FIT_PRECISION_PX = 0.01    # resolucion de la busqueda binaria

# Mide con el body ya como columna flexible: asi la altura medida es la misma
# que tendra al final, cuando el sobrante se reparte entre secciones.
_FIT_MEASURE_JS = """(s) => {
  document.documentElement.style.setProperty('--fit-font', s + 'px');
  const b = document.body.style;
  b.display = 'flex'; b.flexDirection = 'column';
  b.height = 'auto'; b.justifyContent = 'flex-start';
  return document.body.scrollHeight;
}"""

# Reparte el sobrante (menos de una linea, tras la busqueda) entre secciones:
# la cabecera queda arriba y la ultima seccion termina en el margen inferior.
_FIT_FILL_JS = """(h) => {
  const b = document.body.style;
  b.height = h + 'px'; b.justifyContent = 'space-between';
  const last = document.body.lastElementChild;
  return last ? last.getBoundingClientRect().bottom : 0;
}"""

# Ultimo ajuste aplicado, para diagnostico y para las pruebas de llenado.
LAST_FIT = {}


def _fit_to_one_page(page, cfg: dict, max_px: float = None) -> float:
    """Ajusta la letra para que el contenido llene exactamente una pagina.

    Busca por biseccion el MAYOR tamano de `--fit-font` con el que todo cabe:
    crece si sobra espacio y reduce si no cabe. El template expone esa
    variable en :root y el resto usa unidades relativas, asi que mueve el
    documento completo. Despues reparte el sobrante entre secciones para que
    la pagina quede llena al 100 %. Devuelve el tamano aplicado.
    """
    usable_w, usable_h = _usable_page_px(cfg['margins'])
    page.set_viewport_size({"width": usable_w, "height": usable_h})
    with contextlib.suppress(Exception):
        page.emulate_media(media="print")
    # 1 px de holgura: el redondeo de Chromium al paginar no debe abrir una
    # segunda pagina con una linea vacia.
    target = usable_h - 1

    def measure(size):
        return page.evaluate(_FIT_MEASURE_JS, round(size, 3))

    ceiling = min(FIT_CEILING_PX, max_px) if max_px else FIT_CEILING_PX
    base = min(cfg.get('base_font_px', 10.0), ceiling)
    if measure(base) <= target:
        lo, hi = base, ceiling
        if measure(hi) <= target:
            lo = hi
    else:
        lo, hi = FIT_ABSOLUTE_FLOOR_PX, base

    while hi - lo > FIT_PRECISION_PX:
        mid = (lo + hi) / 2
        if measure(mid) <= target:
            lo = mid
        else:
            hi = mid

    # Se redondea HACIA ABAJO y se verifica: el tamano redondeado al alza
    # puede pasar el margen por 1-2 px y abrir una segunda pagina.
    LAST_FIT.clear()
    size = math.floor(lo * 100) / 100
    height = measure(size)
    while height > target and size - 0.01 >= FIT_ABSOLUTE_FLOOR_PX:
        size = round(size - 0.01, 2)
        height = measure(size)
    if height > target:
        print(f"[FIT][WARN] Ni con {size}px cabe en una pagina ({height}px de {target}px).")
        return size
    bottom = page.evaluate(_FIT_FILL_JS, target)
    LAST_FIT.clear()
    LAST_FIT.update(size=size, content=height, target=target, bottom=bottom)
    print(f"[FIT] {size}px: contenido {height}px de {target}px "
          f"({height / target:.1%}); el sobrante se reparte entre secciones -> 100%")
    return size


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
            page.goto(file_url, wait_until='domcontentloaded')
            # Las fuentes/iconos de CDN son opcionales: una red lenta no debe
            # impedir imprimir el HTML y CSS locales.
            try:
                page.wait_for_load_state('networkidle', timeout=10_000)
            except PlaywrightTimeoutError:
                page.evaluate('window.stop()')
                print('[WARN] Recursos externos lentos; se imprime con los recursos disponibles.')

            def print_pdf():
                page.pdf(path=str(output_file), format='A4',
                         print_background=True, margin=cfg['margins'])

            if cfg.get('fit_one_page'):
                size = _fit_to_one_page(page, cfg)
                print_pdf()
                # La altura medida y la paginacion real pueden diferir (saltos
                # de pagina evitados, redondeos): se cuenta el PDF y, si salio
                # mas de una pagina, se sigue reduciendo y se reimprime.
                step = cfg.get('step_px', 0.2)
                while _count_pdf_pages(output_file) > 1 and size - step >= FIT_ABSOLUTE_FLOOR_PX:
                    print(f"[FIT] El PDF salio con {_count_pdf_pages(output_file)} paginas; se reduce y reimprime.")
                    size = _fit_to_one_page(page, cfg, max_px=size - step)
                    print_pdf()
                pages = _count_pdf_pages(output_file)
                if pages > 1:
                    print(f"[FIT][WARN] Ni con {size}px cabe en una pagina: el PDF tiene {pages}.")
                warn = cfg.get('warn_font_px', 6.0)
                if size < warn:
                    print(f"[FIT][WARN] Letra a {size}px, por debajo de {warn}px: todo cabe, "
                          "pero impreso sera dificil de leer.")
            else:
                print_pdf()
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


def render_to_pdf(data: dict, lang: str, output_name: str = None, template_name: str = DEFAULT_TEMPLATE) -> bool:
    """Renderiza el CV a PDF y devuelve si se genero correctamente.

    Si WeasyPrint no está disponible (falta libgobject/pango en Windows u otra dependencia),
    se genera un archivo HTML para inspección manual y se muestra una guía breve.
    """
    cfg = TEMPLATES[template_name]

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(['html', 'xml', 'j2'])
    )
    env.filters['markdown_links'] = markdown_links
    env.filters['strip_links'] = strip_markdown_links
    template = env.get_template(cfg['template'])

    sections = normalize_sections(data)
    data = sections['data']

    # `clave(Titulo)` gana sobre ui/ui_templates. En `generation`, cursos y
    # certificaciones comparten encabezado: manda la primera con titulo.
    ui = resolve_ui(data, lang, template_name)
    title_labels = SECTION_TITLE_LABELS[template_name]
    applied = set()
    for key in sections['order']:
        if isinstance(key, tuple) or key not in sections['titles'] or key not in title_labels:
            continue
        label = title_labels[key]
        if label not in applied:
            ui[label] = sections['titles'][key]
            applied.add(label)

    # Las claves de configuración no pueden colisionar con los argumentos Jinja.
    context = {key: value for key, value in data.items()
               if key not in {'ui', 'ui_templates'}}
    context.update(
        lang=lang, ui=ui, css=cfg['css'],
        section_sequence=section_sequence(sections['order'], template_name, data),
        custom_sections=[dict(section, **custom_entries(section['content']))
                         for section in sections['custom']],
    )
    html_content = template.render(**context)

    if output_name:
        output_file = BASE_DIR / output_name
    else:
        output_file = BASE_DIR / f"{OUTPUT_PREFIX}{template_name}_{lang}.pdf"

    # WeasyPrint no soporta el auto-ajuste: medir requiere un navegador vivo.
    if WEASYPRINT_AVAILABLE and not cfg.get('fit_one_page'):
        try:
            HTML(string=html_content, base_url=str(BASE_DIR)).write_pdf(str(output_file))
            print(f"Generated {output_file.name} (WeasyPrint)")
            return True
        except Exception:
            print("[WARN] WeasyPrint falló en tiempo de ejecución. Intentando Playwright...")
            traceback.print_exc()

    # Si no disponible WeasyPrint o falló, usar Playwright
    if _playwright_pdf(html_content, output_file, BASE_DIR, cfg):
        return True

    # Último fallback: guardar HTML
    fallback_html = output_file.with_suffix('.html')
    fallback_html.write_text(html_content, encoding='utf-8')
    if not WEASYPRINT_AVAILABLE:
        print(f"[WARN] WeasyPrint no disponible: {WEASYPRINT_IMPORT_ERROR!r}")
    print(f"[WARN] No se pudo generar PDF. Fallback HTML: {fallback_html.name}")
    print("Para Playwright: pip install playwright && python -m playwright install chromium")
    print("Para WeasyPrint (dependencias nativas): https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation")
    return False


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

# Enlaces Markdown. El target admite [[Pn]] porque _protect_pii ya sustituyo
# la URL por un centinela antes de que el texto llegue al modelo.
MD_LINK_RE = re.compile(r'\[([^\[\]\n]+)\]\(([^()\s]+)\)')
# Centinela de enlace COMPLETO: ultimo recurso cuando el modelo insiste en
# romper la sintaxis. El enlace lo reconstruye el codigo, no el modelo.
LINK_SENTINEL_RE = re.compile(r'\[\[L\d+\]\]')


def _link_signature(text: str) -> list:
    """Targets de los enlaces Markdown BIEN FORMADOS que contiene el texto.

    Comparar la firma de entrada contra la de salida detecta el fallo real
    observado: el modelo conserva el centinela [[Pn]] (asi que la validacion
    de PII pasa) pero se come los corchetes, dejando `texto.([[P1]])`. Al
    reinsertar la URL eso deja de ser un enlace y el template imprime la URL
    cruda en vez de renderizar un <a>.
    """
    return sorted(m.group(2) for m in MD_LINK_RE.finditer(text))


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
                               think=_think_arg(False))
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
2. Copy every [[Pn]] and [[Ln]] token verbatim, in its original position. These
   are redacted values that the program reinserts later. Never translate,
   renumber, reword, space out or remove them.
3. Preserve Markdown link syntax [visible text](target) exactly. Translate only
   the visible text; leave whatever is inside the parentheses untouched. The
   square brackets are part of the syntax: never drop them, never merge them
   into the sentence, and never put any character (a period, a space, a comma)
   between ']' and '('. "Subject A, Subject B([[P1]])" is broken output;
   "[Subject A, Subject B]([[P1]])" is correct.
4. Do not translate proper nouns, brand or product names, technologies,
   programming languages, frameworks, tools, certifications, degrees awarded
   under an official name, or acronyms (AWS, IPN, SQL, .NET, Kali Linux).
5. Do not invent, infer, embellish or omit facts. No new metrics, no new
   technologies, no new achievements. The claims in the output must be exactly
   the claims in the input.
6. Keep numbers, dates, percentages and units exactly as given.
7. Every achievement or responsibility statement, anywhere in the CV, opens with
   an action verb in the SIMPLE PAST tense - bullets, project descriptions,
   extracurricular blurbs and research focus lines. The professional summary is
   the ONE exception: it is a profile, not a list of achievements, so it opens
   with an impersonal noun phrase naming the role ("Computer engineer focused
   on...") and never with a past-tense verb. This
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
- OPEN with an impersonal noun phrase naming the professional identity
  ("Computer engineer focused on...", "Ingeniero en computacion enfocado
  en..."). Never open with a past-tense verb: invariant 7 does NOT apply to
  this field, which is a profile and not a list of achievements.
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


def _ollama_translate(masked: str, target_lang: str, kind: str, correction: str = None):
    """Una sola llamada al modelo. Devuelve el texto limpio o None si fallo."""
    messages = _build_translation_messages(masked, target_lang, kind)
    if correction:
        # Reintento: se le dice al modelo exactamente que invariante rompio.
        messages[-1]['content'] += (
            "\n\n<correction>Your previous answer was rejected. "
            + correction +
            " Produce the translation again, obeying that rule exactly.</correction>")
    global OLLAMA_SUPPORTS_THINK
    try:
        response = ollama.chat(model=OLLAMA_MODEL, messages=messages, think=_think_arg(OLLAMA_THINK))
    except Exception as e:
        # Modelo elegido a mano sin capacidad 'thinking': Ollama rechaza
        # `think`. Se desactiva para el resto de la corrida y se reintenta.
        if OLLAMA_SUPPORTS_THINK and 'think' in str(e).lower():
            OLLAMA_SUPPORTS_THINK = False
            return _ollama_translate(masked, target_lang, kind, correction)
        print(f"[Ollama][ERROR] Falla en traduccion: {e}")
        return None
    return _clean_model_output(response['message']['content']) or None


def _validate_translation(masked: str, result: str, tokens: dict, kind: str):
    """Devuelve (motivo, correccion) o (None, None) si la respuesta es usable.

    'motivo' es un codigo estable ('sentinel' | 'link' | 'lines') que decide a
    que degradacion recurrir; 'correccion' es el texto que se le devuelve al
    modelo en el reintento.
    """
    missing = [k for k in tokens if k not in result]
    if missing:
        return ('sentinel',
                f"You dropped the redaction tokens {missing}. Every [[Pn]] token in "
                "the input must appear verbatim in the output, in the same place.")

    unknown = [m for m in PII_SENTINEL_RE.findall(result) if m not in tokens]
    if unknown:
        return ('sentinel',
                f"You invented the tokens {unknown}. Copy only the [[Pn]] tokens that "
                "appear in the input; never create new ones.")

    # Centinelas de enlace completo (_translate_with_link_sentinels).
    link_missing = [m for m in LINK_SENTINEL_RE.findall(masked) if m not in result]
    if link_missing:
        return ('sentinel',
                f"You dropped the placeholders {link_missing}. Copy every [[Ln]] "
                "placeholder verbatim, in its original position.")

    # El fallo real observado: el modelo conserva [[Pn]] pero se come los
    # corchetes del enlace, dejando `texto.([[P1]])`. Al reinsertar la URL eso
    # deja de ser un enlace y el template imprime la URL cruda.
    if _link_signature(masked) != _link_signature(result):
        return ('link',
                "You broke the Markdown link syntax. Every link must stay exactly "
                "[visible text](target): keep the square brackets around the visible "
                "text and the parentheses around the target, with no character "
                "between ']' and '('. Translate only the visible text.")

    if kind == 'bullets':
        expected = masked.strip().count('\n') + 1
        got = result.strip().count('\n') + 1
        if expected != got:
            return ('lines',
                    f"The input has {expected} lines and your answer had {got}. "
                    "Output exactly one line per input line, in the same order, "
                    "with no blank lines added or removed.")

    return (None, None)


def _translate_bullets_linewise(text: str, target_lang: str, depth: int) -> str:
    """Degradacion para 'bullets': cada linea se traduce por separado.

    Una linea suelta no puede desalinear el conteo de lineas del bloque, asi
    que este camino siempre produce una estructura correcta. Antes, un solo
    desajuste tiraba la traduccion del bloque entero y la seccion se quedaba
    en el idioma original: le pasaba a las descripciones densas, sin lineas en
    blanco entre vinetas, donde el modelo tiende a agregar separacion.
    """
    print("[Ollama] Reintentando el bloque vineta por vineta...")
    out = []
    for line in text.split('\n'):
        out.append(line if not line.strip()
                   else _translate_text(line, target_lang, 'bullets', depth + 1))
    return '\n'.join(out)


def _translate_with_link_sentinels(text: str, target_lang: str, kind: str, depth: int):
    """Degradacion para enlaces: el enlace lo rearma el codigo, no el modelo.

    Cada `[visible](target)` se sustituye por `[[Ln]]` antes de traducir, de
    modo que el modelo no tiene corchetes que perder; el texto visible se
    traduce en una llamada aparte y el enlace se reconstruye aqui. Devuelve
    None si no habia enlaces (no hay nada que degradar).
    """
    links = []

    def stash(m):
        links.append((m.group(1), m.group(2)))
        return f"[[L{len(links)}]]"

    carrier = MD_LINK_RE.sub(stash, text)
    if not links:
        return None

    print(f"[Ollama] Reintentando con {len(links)} enlace(s) fuera del alcance del modelo...")
    carrier = _translate_text(carrier, target_lang, kind, depth + 1)
    for i, (visible, target) in enumerate(links, start=1):
        # Un texto visible de una sola palabra es un nombre propio (invariante
        # 4 del prompt): no se traduce y se ahorra la llamada.
        if re.search(r'\s', visible.strip()):
            visible = _translate_text(visible, target_lang, 'short', depth + 1)
        carrier = carrier.replace(f"[[L{i}]]", f"[{visible}]({target})")
    return carrier


def _translate_text(text: str, target_lang: str, kind: str, depth: int) -> str:
    if not OLLAMA_AVAILABLE:
        return text

    # La PII se enmascara ANTES de que el texto salga del proceso.
    masked, tokens = _protect_pii(text)

    print(f"[Ollama] Traduciendo bloque ({kind}) a {target_lang}...")
    result = _ollama_translate(masked, target_lang, kind)
    if result is None:
        print("[Ollama][WARN] Respuesta vacia o con error; se conserva el texto original.")
        return text

    reason, correction = _validate_translation(masked, result, tokens, kind)
    if reason:
        # 1er remedio: pedirlo otra vez nombrando la regla rota. Barato y suele
        # bastar; antes cualquier violacion se resolvia dejando el original.
        print(f"[Ollama][WARN] Respuesta invalida ({reason}); reintentando una vez.")
        retry = _ollama_translate(masked, target_lang, kind, correction)
        if retry is not None:
            reason_retry, _ = _validate_translation(masked, retry, tokens, kind)
            if not reason_retry:
                return _restore_pii(retry, tokens)
            reason = reason_retry

    if reason and depth == 0:
        # 2o remedio: quitarle al modelo la parte que rompe. Solo en la llamada
        # de nivel superior, para que las degradaciones no se reentren.
        if reason == 'link':
            repaired = _translate_with_link_sentinels(text, target_lang, kind, depth)
            if repaired is not None:
                return repaired
        elif reason == 'lines':
            return _translate_bullets_linewise(text, target_lang, depth)

    if reason:
        print(f"[Ollama][WARN] No se pudo obtener una traduccion valida ({reason}); "
              "se conserva el texto original.")
        return text

    return _restore_pii(result, tokens)


def translate_text(text: str, target_lang: str, kind: str = 'short') -> str:
    """Traduce un fragmento del CV.

    Contrato: nunca devuelve un dato corrompido. Si el modelo rompe una
    invariante (centinela de PII, sintaxis de enlace, numero de lineas) se
    reintenta una vez nombrando la regla, luego se degrada a una estrategia
    que hace imposible ese fallo concreto, y solo si todo falla se devuelve el
    texto original sin traducir.
    """
    return _translate_text(text, target_lang, kind, 0)


def _translate_relevant_project(item, t):
    """'Relevant projects' admite string plano o mapping {title, subitems}."""
    if isinstance(item, dict):
        out = copy.deepcopy(item)
        if 'title' in out: out['title'] = t(out['title'], 'short')
        if out.get('subitems'): out['subitems'] = [t(x, 'bullets') for x in out['subitems']]
        return out
    return t(item, 'bullets')


def _translate_custom_content(content, t):
    """Contenido de una seccion nueva: mismas formas que acepta `custom_entries`.

    Se traducen titulos, periodos y descripciones; `url`, `year` e `include`
    pasan intactos.
    """
    if isinstance(content, str):
        return t(content, 'bullets' if '\n' in content.strip() else 'prose')
    if isinstance(content, dict):
        out = {}
        for key, value in content.items():
            if isinstance(value, list):
                value = [t(v, 'list_item') if isinstance(v, str) else v for v in value]
            elif isinstance(value, str):
                value = t(value, 'short')
            out[t(key, 'short') if isinstance(key, str) else key] = value
        return out
    out = []
    for item in content or []:
        if isinstance(item, dict):
            item = copy.deepcopy(item)
            for field in CUSTOM_TITLE_FIELDS + ('period', 'date'):
                if isinstance(item.get(field), str):
                    item[field] = t(item[field], 'short')
            for field in CUSTOM_TEXT_FIELDS:
                if isinstance(item.get(field), str):
                    item[field] = t(item[field], 'bullets')
            out.append(item)
        else:
            out.append(t(item, 'short') if isinstance(item, str) else item)
    return out


def translate_cv_data(data: dict, target_lang: str) -> dict:
    """Traduce el CV conservando el orden de las claves del YAML.

    Las claves `clave(Titulo)` se traducen solo dentro del parentesis; las
    secciones nuevas traducen su titulo (la clave, si no hay parentesis) y su
    contenido.
    """
    validate_ui(data)
    layout, known, custom = [], {}, {}
    for raw_key, value in data.items():
        base, title = split_section_key(raw_key)
        if base in NON_SECTION_KEYS or base in KNOWN_SECTION_KEYS:
            if base in known:
                raise ValueError(f"La seccion '{base}' aparece dos veces en el YAML (revisa '{raw_key}').")
            known[base] = value
            layout.append(('known', base, title))
        else:
            custom[raw_key] = value
            layout.append(('custom', base, title, raw_key))

    translated = _translate_known_sections(known, target_lang)

    def t(text, kind='short'):
        if not text or not isinstance(text, str): return text
        return translate_text(text, target_lang, kind)

    out = {}
    for entry in layout:
        if entry[0] == 'known':
            _, base, title = entry
            out[f"{base}({t(title)})" if title else base] = translated[base]
        else:
            _, base, title, raw_key = entry
            key = f"{base}({t(title)})" if title else t(base)
            out[key] = _translate_custom_content(custom[raw_key], t)
    print("--- Traducción finalizada ---")
    return out


def _translate_known_sections(data: dict, target_lang: str) -> dict:
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

    # Los textos personalizados también pertenecen al documento traducido.
    # Pasan por la misma protección de PII que el resto del contenido.
    label_maps = [translated.get('ui', {})]
    label_maps.extend(translated.get('ui_templates', {}).values())
    for labels in label_maps:
        for key, value in labels.items():
            labels[key] = t(value, 'short')

    if 'personal_info' in translated:
        # name, email, phone, gpa y *_url NO se envian nunca (NEVER_SENT_KEYS).
        if 'title' in translated['personal_info']:
            translated['personal_info']['title'] = t(translated['personal_info']['title'], 'short')
        if 'location' in translated['personal_info']:
            translated['personal_info']['location'] = t(translated['personal_info']['location'], 'short')

    if 'summary' in translated:
        translated['summary'] = t(translated['summary'], 'prose')

    for exp in translated.get('work_experience') or []:
        if 'role' in exp: exp['role'] = t(exp['role'])
        if 'company' in exp: exp['company'] = t(exp['company'])
        if 'description' in exp: exp['description'] = t(exp['description'], 'bullets')
        if 'location' in exp: exp['location'] = t(exp['location'])
        if 'period' in exp: exp['period'] = t(exp['period'])

    for proj in translated.get('projects') or []:
        if 'title' in proj: proj['title'] = t(proj['title'])
        if 'description' in proj: proj['description'] = t(proj['description'], 'bullets')
        if 'period' in proj: proj['period'] = t(proj['period'])

    for edu in translated.get('education') or []:
        if 'degree' in edu: edu['degree'] = t(edu['degree'])
        if 'institution' in edu: edu['institution'] = t(edu['institution'])
        if 'period' in edu: edu['period'] = t(edu['period'])
        # 'gpa' se copia tal cual: es un dato identificatorio y numerico.
        if 'Relevant subjects' in edu: edu['Relevant subjects'] = t(edu['Relevant subjects'], 'prose')
        # `or []`: una clave escrita en el YAML pero sin valor se carga como
        # None, y `in edu` es cierto igual. Sin esto, iterar revienta con
        # TypeError y aborta la traduccion completa a media corrida.
        if edu.get('Extracurricular activities'):
            edu['Extracurricular activities'] = [t(c, 'bullets') for c in edu['Extracurricular activities']]
        if edu.get('Relevant projects'):
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

    if translated.get('certifications'):
        translated['certifications'] = [translate_credential(c) for c in translated['certifications']]

    if translated.get('courses'):
        translated['courses'] = [translate_credential(c) for c in translated['courses']]

    # Secciones de logros del template 'capitalone'. Sin esto pasarian en el
    # idioma original: translate_cv_data recorre una lista fija de campos.
    for item in translated.get('extracurriculars') or []:
        if not isinstance(item, dict):
            continue
        if 'exp' in item: item['exp'] = t(item['exp'], 'short')
        if 'desc' in item: item['desc'] = t(item['desc'], 'prose')
        if 'event' in item: item['event'] = t(item['event'], 'prose')
        if 'date' in item: item['date'] = t(item['date'], 'short')

    for item in translated.get('hackathons') or []:
        if not isinstance(item, dict):
            continue
        if 'achievement' in item: item['achievement'] = t(item['achievement'], 'short')
        if 'period' in item: item['period'] = t(item['period'], 'short')
        # 'name' es nombre propio del evento: no se traduce.

    for item in translated.get('academic_visits') or []:
        if not isinstance(item, dict):
            continue
        if 'focus' in item: item['focus'] = t(item['focus'], 'bullets')
        if 'period' in item: item['period'] = t(item['period'], 'short')
        if 'institution' in item: item['institution'] = t(item['institution'], 'short')

    # Las habilidades blandas sí se traducen; las técnicas no.
    if (translated.get('skills') or {}).get('soft_skills'):
        translated['skills']['soft_skills'] = [t(s, 'list_item') for s in translated['skills']['soft_skills']]

    # Idiomas hablados: se traduce el nombre del idioma, no el nivel (B2, C1...).
    for spoken in translated.get('spoken_languages') or []:
        if isinstance(spoken, dict) and 'language' in spoken:
            spoken['language'] = t(spoken['language'], 'list_item')

    # Tecnologías (skills) no se traducen.
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


def resolve_input_lang(path: Path, preselected: str = None) -> str:
    """Idioma del YAML de entrada: flag, nombre del archivo, o pregunta.

    Se prefiere el nombre a `detect_language()` porque no cuesta una llamada al
    modelo; el usuario decide solo cuando el nombre no lo declara.
    """
    if preselected:
        return preselected
    from_name = lang_from_name(path)
    if from_name:
        print(f"Idioma de {path.name}: {from_name} (declarado en el nombre)")
        return from_name
    return choose_lang(f"{path.name} no declara idioma en su nombre. ¿En qué idioma está?")


def check_model_ready() -> str:
    """Prueba el modelo con una llamada minima. Devuelve el problema o ''."""
    if not OLLAMA_AVAILABLE:
        return "Falta el paquete 'ollama' en el entorno."
    try:
        ollama.chat(model=OLLAMA_MODEL, messages=[{'role': 'user', 'content': 'Reply: ok'}],
                    options={'num_predict': 8})
        return ''
    except Exception as e:
        text = str(e)
        status = getattr(e, 'status_code', None)
        if status == 402 or 'credits' in text.lower():
            return (f"El modelo de la nube '{OLLAMA_MODEL}' requiere créditos o suscripción "
                    f"en la cuenta de Ollama: {text}")
        if status in (401, 403):
            return f"Ollama no tiene sesión iniciada para la nube; ejecuta 'ollama signin'. ({text})"
        if status == 404 or 'not found' in text.lower():
            return f"Ollama no encuentra el modelo '{OLLAMA_MODEL}'. ({text})"
        if isinstance(e, ConnectionError) or 'connect' in text.lower():
            return "No se pudo conectar con Ollama; ábrelo (o ejecuta 'ollama serve')."
        return f"El modelo '{OLLAMA_MODEL}' no respondió: {text}"


def run_translate(args) -> None:
    """Traduce un YAML completo y lo guarda como un YAML nuevo."""
    src_path = choose_yaml(args.input, "YAML base a traducir")
    src_lang = resolve_input_lang(src_path, args.from_lang)

    other = 'en' if src_lang == 'es' else 'es'
    dst_lang = args.to_lang or choose_lang("Idioma destino de la traducción", default=other)
    if dst_lang == src_lang:
        print(f"[ERROR] El origen ya está en '{src_lang}'; elige otro idioma destino.")
        sys.exit(1)

    out_path = BASE_DIR / (args.output or derived_yaml_name(src_path, dst_lang))
    if out_path.resolve() == src_path.resolve():
        print(f"[ERROR] El destino coincide con el origen ({src_path.name}); usa --output.")
        sys.exit(1)
    if out_path.exists():
        print(f"[WARN] {out_path.name} ya existe y se va a sobrescribir.")

    print(f"\nOrigen : {src_path.name} ({src_lang})")
    print(f"Destino: {out_path.name} ({dst_lang})")
    print(f"Modelo : {OLLAMA_MODEL}")

    # Una llamada de prueba antes de las ~95 reales: si el modelo no responde
    # (Ollama apagado, modelo inexistente, nube sin creditos), cada campo
    # fallaria por separado y el YAML saldria sin traducir.
    problem = check_model_ready()
    if problem:
        print(f"[ERROR] {problem}")
        print("Elige otro modelo en el menú Configuración → Modelo de traducción.")
        sys.exit(1)

    # A diferencia del modo pdf, aqui NO se aplica prune_hidden: el archivo
    # derivado debe ser un espejo fiel del base, con sus marcas `include`
    # intactas, para poder filtrarlo despues al generar cada PDF.
    data = load_cv_data(src_path)
    translated = translate_cv_data(data, dst_lang)
    dump_cv_data(translated, out_path)
    print(f"Escrito {out_path.name}")


def run_pdf(args) -> None:
    """Renderiza a PDF cualquier YAML del directorio."""
    src_path = choose_yaml(args.input, "YAML a renderizar")
    lang = resolve_input_lang(src_path, args.from_lang)
    template_name = choose_template(args.template)
    print(f"Template seleccionado: {template_name}")

    data = load_cv_data(src_path)

    # Se filtra al renderizar, no al traducir: cada PDF decide que imprime.
    hidden = []
    data = prune_hidden(data, hidden)
    if hidden:
        print(f"[FILTRO] {len(hidden)} elementos ocultos (include: false): {', '.join(hidden)}")

    # El nombre del PDF arrastra el del YAML para no perder de vista con que
    # fuente (y con que modelo, si es derivado) se genero.
    output_name = args.output or f"{src_path.stem}.{template_name}.pdf"
    print(f"Generando {output_name}...")
    if not render_to_pdf(data, lang, output_name, template_name):
        sys.exit(1)


RUNNERS = {'translate': lambda args: run_translate(args),
           'pdf': lambda args: run_pdf(args),
           'config': lambda args: run_config()}


def run_once(mode: str, args) -> bool:
    """Ejecuta una operacion del menu. Devuelve False si fallo.

    Atrapa tambien SystemExit: run_pdf/run_translate terminan con sys.exit(1)
    ante un error, y en el menu eso no debe cerrar la ventana.
    """
    try:
        RUNNERS[mode](args)
        return True
    except SystemExit as e:
        return not e.code
    except FileNotFoundError as fnf:
        print(f"[ERROR] Archivo no encontrado: {fnf}")
    except Exception:
        print("[ERROR] Ejecución inesperada:")
        traceback.print_exc()
    return False


def main() -> int:
    args = parse_args()
    # Con --mode (uso desde scripts) se ejecuta una vez y se sale con su codigo.
    if args.mode:
        return 0 if run_once(args.mode, args) else 1

    # Menu interactivo: tras cada operacion, con exito o error, se vuelve al
    # menu principal. Solo '0.- Salir' (o Ctrl+C) lo cierra.
    while True:
        try:
            mode = choose_mode()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        if mode == 'exit':
            return 0
        try:
            if not run_once(mode, args):
                print("[MENU] La operación terminó con error; vuelves al menú principal.")
        except KeyboardInterrupt:
            print("\n[MENU] Operación cancelada; vuelves al menú principal.")


if __name__ == "__main__":
    sys.exit(main())
