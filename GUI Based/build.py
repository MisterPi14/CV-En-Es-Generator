import argparse
import contextlib
import copy
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Dict, List, Optional, Tuple

DEPENDENCY_IMPORT_ERROR: Optional[ModuleNotFoundError] = None
try:
    import yaml
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ModuleNotFoundError as dep_error:
    DEPENDENCY_IMPORT_ERROR = dep_error
    yaml = None  # type: ignore[assignment]
    Environment = None  # type: ignore[assignment]
    FileSystemLoader = None  # type: ignore[assignment]
    select_autoescape = None  # type: ignore[assignment]

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    TK_AVAILABLE = True
except Exception:
    TK_AVAILABLE = False

try:
    import ollama

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

OLLAMA_MODEL = "gemma3:4b"

try:
    from weasyprint import HTML  # type: ignore

    WEASYPRINT_AVAILABLE = True
    WEASYPRINT_IMPORT_ERROR = None
except Exception as e:
    WEASYPRINT_AVAILABLE = False
    WEASYPRINT_IMPORT_ERROR = e

try:
    from playwright.sync_api import sync_playwright  # type: ignore

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STYLE_FILE = STATIC_DIR / "style.css"

CV_FILE = BASE_DIR / "resume.yaml"
TRANSLATED_CV_FILE = BASE_DIR / "resume-translated.yaml"
OUTPUT_PREFIX = "resume_"

DEFAULT_NAME_FONT_SIZE = "40px"
DEFAULT_BODY_FONT_SIZE = "10px"
NAME_SIZE_OPTIONS = ["34px", "36px", "38px", "40px", "42px", "44px", "46px"]
BODY_SIZE_OPTIONS = ["9px", "9.5px", "10px", "10.5px", "11px", "11.5px", "12px"]

NAME_FONT_REGEX = re.compile(r"(h1\\.name\\s*\\{[^}]*?font-size:\\s*)([^;]+)(;)", re.S)
BODY_FONT_REGEX = re.compile(r"(body\\s*\\{[^}]*?font-size:\\s*)([^;]+)(;)", re.S)
HTML_BODY_FONT_REGEX = re.compile(r"(html\\s*,\\s*body\\s*\\{[^}]*?font-size:\\s*)([^;]+)(;)", re.S)

UI_STRINGS = {
    "es": {
        "section_summary": "Resumen Profesional",
        "section_experience": "Experiencia Profesional",
        "section_projects": "Proyectos",
        "section_education": "Educacion",
        "section_certifications": "Certificaciones",
        "section_courses": "Cursos",
        "section_skills": "Habilidades",
        "section_languages": "Lenguajes",
        "section_technologies": "Tecnologias",
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
    },
}

FORM_FIELDS = [
    {
        "key": "personal_info",
        "question": "1) Personal info (YAML object)",
        "mode": "dict",
        "height": 8,
    },
    {
        "key": "summary",
        "question": "2) Professional summary (plain text)",
        "mode": "text",
        "height": 8,
    },
    {
        "key": "work_experience",
        "question": "3) Work experience (YAML list)",
        "mode": "list",
        "height": 10,
    },
    {
        "key": "projects",
        "question": "4) Projects (YAML list)",
        "mode": "list",
        "height": 8,
    },
    {
        "key": "education",
        "question": "5) Education (YAML list)",
        "mode": "list",
        "height": 10,
    },
    {
        "key": "certifications",
        "question": "6) Certifications (YAML list or one item per line)",
        "mode": "list",
        "height": 6,
    },
    {
        "key": "courses",
        "question": "7) Courses (YAML list or one item per line)",
        "mode": "list",
        "height": 6,
    },
    {
        "key": "skills",
        "question": "8) Skills (YAML object)",
        "mode": "dict",
        "height": 8,
    },
]


def default_cv_data() -> Dict[str, Any]:
    return {
        "personal_info": {
            "name": "",
            "title": "",
            "phone": "",
            "email": "",
            "linkedin_url": "",
            "github_url": "",
        },
        "summary": "",
        "work_experience": [],
        "projects": [],
        "education": [],
        "certifications": [],
        "courses": [],
        "skills": {
            "programming_languages": [],
            "technologies_and_frameworks": [],
        },
    }


def normalize_cv_data(data: Any) -> Dict[str, Any]:
    base = default_cv_data()
    if not isinstance(data, dict):
        return base

    normalized = copy.deepcopy(base)

    personal_info = data.get("personal_info")
    if isinstance(personal_info, dict):
        for key, value in personal_info.items():
            if isinstance(key, str):
                normalized["personal_info"][key] = value

    if isinstance(data.get("summary"), str):
        normalized["summary"] = data["summary"]

    for key in ["work_experience", "projects", "education", "certifications", "courses"]:
        if isinstance(data.get(key), list):
            normalized[key] = data[key]

    skills = data.get("skills")
    if isinstance(skills, dict):
        for key, value in skills.items():
            normalized["skills"][key] = value
        if not isinstance(normalized["skills"].get("programming_languages"), list):
            normalized["skills"]["programming_languages"] = []
        if not isinstance(normalized["skills"].get("technologies_and_frameworks"), list):
            normalized["skills"]["technologies_and_frameworks"] = []

    for key, value in data.items():
        if key not in normalized:
            normalized[key] = value

    return normalized


def load_yaml_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)

    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)

    if loaded is None:
        return copy.deepcopy(default)
    return loaded


def save_yaml_file(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_cv_data(allow_missing: bool = True) -> Dict[str, Any]:
    if not CV_FILE.exists() and allow_missing:
        return default_cv_data()
    if not CV_FILE.exists() and not allow_missing:
        raise FileNotFoundError(f"No se encontro {CV_FILE.name}")

    data = load_yaml_file(CV_FILE, default_cv_data())
    return normalize_cv_data(data)


def save_cv_data(data: Dict[str, Any]) -> None:
    save_yaml_file(CV_FILE, normalize_cv_data(data))


def get_summary_seed(data: Dict[str, Any]) -> str:
    summary_text = data.get("summary", "")
    if summary_text:
        return summary_text

    work = data.get("work_experience", [])
    if work and isinstance(work[0], dict):
        return str(work[0].get("description", ""))

    edu = data.get("education", [])
    if edu and isinstance(edu[0], dict):
        return str(edu[0].get("degree", ""))

    return ""


def heuristic_language(text: str) -> str:
    t = f" {text.lower()} "
    en_indicators = [" the ", " and ", " of ", " with ", " for ", " developed "]
    if any(indicator in t for indicator in en_indicators):
        return "en"
    return "es"


def markdown_links(text: str) -> str:
    if not isinstance(text, str):
        return text
    return re.sub(r"\\[([^\\]]+)\\]\\s*\\((https?://[^\\)]+)\\)", r'<a href="\\2" target="_blank">\\1</a>', text)


def _playwright_pdf(html_content: str, output_file: Path, base_dir: Path) -> bool:
    if not PLAYWRIGHT_AVAILABLE:
        print("[PLAYWRIGHT] No disponible. Instala: pip install playwright")
        return False

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8", dir=base_dir) as tmp:
        tmp.write(html_content)
        tmp_path = Path(tmp.name)

    try:
        with sync_playwright() as p:  # type: ignore
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(tmp_path.as_uri())
            page.wait_for_load_state("networkidle")
            page.pdf(
                path=str(output_file),
                format="A4",
                print_background=True,
                margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"},
            )
            browser.close()
        print(f"Generated {output_file.name} (Playwright)")
        return True
    except Exception as e:
        print(f"[PLAYWRIGHT][ERROR] {e}")
        print("Si es la primera vez: python -m playwright install chromium")
        return False
    finally:
        with contextlib.suppress(Exception):
            tmp_path.unlink()


def render_to_pdf(data: Dict[str, Any], lang: str, output_name: Optional[str] = None) -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html", "xml"]))
    env.filters["markdown_links"] = markdown_links
    template = env.get_template("template.html.j2")

    html_content = template.render(lang=lang, ui=UI_STRINGS[lang], **data)

    if output_name:
        output_file = BASE_DIR / output_name
    else:
        output_file = BASE_DIR / f"{OUTPUT_PREFIX}{lang}.pdf"

    if WEASYPRINT_AVAILABLE:
        try:
            HTML(string=html_content, base_url=str(BASE_DIR)).write_pdf(str(output_file))
            print(f"Generated {output_file.name} (WeasyPrint)")
            return
        except Exception:
            print("[WARN] WeasyPrint fallo. Intentando Playwright...")
            traceback.print_exc()

    if _playwright_pdf(html_content, output_file, BASE_DIR):
        return

    fallback_html = BASE_DIR / f"{OUTPUT_PREFIX}{lang}.html"
    fallback_html.write_text(html_content, encoding="utf-8")
    if not WEASYPRINT_AVAILABLE:
        print(f"[WARN] WeasyPrint no disponible: {WEASYPRINT_IMPORT_ERROR!r}")
    print(f"[WARN] No se pudo generar PDF. Fallback HTML: {fallback_html.name}")


def get_current_font_sizes() -> Tuple[str, str]:
    if not STYLE_FILE.exists():
        return DEFAULT_NAME_FONT_SIZE, DEFAULT_BODY_FONT_SIZE

    text = STYLE_FILE.read_text(encoding="utf-8")

    name_size = DEFAULT_NAME_FONT_SIZE
    body_size = DEFAULT_BODY_FONT_SIZE

    name_match = NAME_FONT_REGEX.search(text)
    if name_match:
        name_size = name_match.group(2).strip()

    body_match = BODY_FONT_REGEX.search(text)
    if body_match:
        body_size = body_match.group(2).strip()
    else:
        html_body_match = HTML_BODY_FONT_REGEX.search(text)
        if html_body_match:
            body_size = html_body_match.group(2).strip()

    return name_size, body_size


def update_style_font_sizes(name_size: str, body_size: str) -> None:
    if not STYLE_FILE.exists():
        raise FileNotFoundError(f"No se encontro {STYLE_FILE}")

    text = STYLE_FILE.read_text(encoding="utf-8")

    updated_text, name_count = NAME_FONT_REGEX.subn(
        lambda m: f"{m.group(1)}{name_size}{m.group(3)}", text, count=1
    )

    if name_count == 0:
        raise ValueError("No se encontro h1.name font-size en static/style.css")

    updated_text, body_count = BODY_FONT_REGEX.subn(
        lambda m: f"{m.group(1)}{body_size}{m.group(3)}", updated_text, count=1
    )

    if body_count == 0:
        updated_text, html_body_count = HTML_BODY_FONT_REGEX.subn(
            lambda m: f"{m.group(1)}{body_size}{m.group(3)}", updated_text, count=1
        )
        if html_body_count == 0:
            raise ValueError("No se encontro body font-size en static/style.css")

    STYLE_FILE.write_text(updated_text, encoding="utf-8")
    print(f"[STYLE] h1.name={name_size} | body={body_size}")


def get_ollama_models(default_model: str) -> List[str]:
    models: List[str] = []

    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            for line in lines[1:]:
                cols = line.split()
                if cols:
                    model_name = cols[0]
                    if model_name.lower() != "name":
                        models.append(model_name)
        else:
            stderr_msg = result.stderr.strip() if result.stderr else "sin detalle"
            print(f"[WARN] ollama list devolvio error: {stderr_msg}")
    except FileNotFoundError:
        print("[WARN] No se encontro el comando 'ollama'.")
    except Exception as e:
        print(f"[WARN] No se pudo obtener modelos de Ollama: {e}")

    ordered: List[str] = []
    for model in [default_model] + models:
        if model and model not in ordered:
            ordered.append(model)

    return ordered if ordered else [default_model]


def detect_language(text: str, model: str) -> str:
    if not text:
        return "es"

    if not OLLAMA_AVAILABLE:
        print("[WARN] ollama (python package) no esta instalado. Usando heuristica.")
        return heuristic_language(text)

    prompt = (
        "You are a language detector. Respond with exactly 'es' if the text is Spanish, "
        f"or 'en' if the text is English. Text: {text}"
    )
    print(f"[Ollama] Detectando idioma con modelo {model}...")

    try:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        content = response["message"]["content"].strip().lower()
        if content.startswith("en"):
            return "en"
        if content.startswith("es"):
            return "es"
        if re.search(r"\\ben\\b", content) and not re.search(r"\\bes\\b", content):
            return "en"
        if re.search(r"\\bes\\b", content) and not re.search(r"\\ben\\b", content):
            return "es"
        return heuristic_language(text)
    except Exception as e:
        print(f"[Ollama][ERROR] No se pudo detectar idioma: {e}")
        return heuristic_language(text)


def translate_text(text: str, target_lang: str, model: str) -> str:
    if not OLLAMA_AVAILABLE:
        return text

    lang_name = "Professional English" if target_lang == "en" else "Professional Spanish"
    if target_lang == "en":
        example_in = "Desarrolle APIs REST para clientes enterprise."
        example_out = "Developed REST APIs for enterprise clients."
    else:
        example_in = "Developed REST APIs for enterprise clients."
        example_out = "Desarrolle APIs REST para clientes enterprise."

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

    print(f"[Ollama] Traduciendo bloque a {target_lang} con modelo {model}...")
    try:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"[Ollama][ERROR] Falla en traduccion: {e}")
        return text


def translate_cv_data(data: Dict[str, Any], target_lang: str, model: str) -> Dict[str, Any]:
    translated = copy.deepcopy(data)

    def t(text: Any) -> Any:
        if not text or not isinstance(text, str):
            return text
        return translate_text(text, target_lang, model)

    print(f"--- Iniciando traduccion del CV completo a '{target_lang}' ---")

    if "personal_info" in translated and isinstance(translated["personal_info"], dict):
        if "title" in translated["personal_info"]:
            translated["personal_info"]["title"] = t(translated["personal_info"]["title"])

    if "summary" in translated:
        translated["summary"] = t(translated["summary"])

    for exp in translated.get("work_experience", []):
        if not isinstance(exp, dict):
            continue
        if "role" in exp:
            exp["role"] = t(exp["role"])
        if "company" in exp:
            exp["company"] = t(exp["company"])
        if "description" in exp:
            exp["description"] = t(exp["description"])
        if "location" in exp:
            exp["location"] = t(exp["location"])
        if "period" in exp:
            exp["period"] = t(exp["period"])

    for proj in translated.get("projects", []):
        if not isinstance(proj, dict):
            continue
        if "title" in proj:
            proj["title"] = t(proj["title"])
        if "description" in proj:
            proj["description"] = t(proj["description"])
        if "period" in proj:
            proj["period"] = t(proj["period"])

    for edu in translated.get("education", []):
        if not isinstance(edu, dict):
            continue
        if "degree" in edu:
            edu["degree"] = t(edu["degree"])
        if "institution" in edu:
            edu["institution"] = t(edu["institution"])
        if "period" in edu:
            edu["period"] = t(edu["period"])
        if "Relevant subjects" in edu:
            edu["Relevant subjects"] = t(edu["Relevant subjects"])
        if "Extracurricular activities" in edu and isinstance(edu["Extracurricular activities"], list):
            edu["Extracurricular activities"] = [t(c) for c in edu["Extracurricular activities"]]
        if "Relevant projects" in edu and isinstance(edu["Relevant projects"], list):
            edu["Relevant projects"] = [t(c) for c in edu["Relevant projects"]]

    if "certifications" in translated and isinstance(translated["certifications"], list):
        translated["certifications"] = [t(c) for c in translated["certifications"]]

    if "courses" in translated and isinstance(translated["courses"], list):
        translated["courses"] = [t(c) for c in translated["courses"]]

    print("--- Traduccion finalizada ---")
    return translated


def save_translated_snapshot(source_lang: str, translated_lang: str, translated_data: Dict[str, Any], model: str) -> None:
    payload = {
        "source_lang": source_lang,
        "translated_lang": translated_lang,
        "model": model,
        "translated_data": normalize_cv_data(translated_data),
    }
    save_yaml_file(TRANSLATED_CV_FILE, payload)
    print(f"[OK] Traduccion guardada en {TRANSLATED_CV_FILE.name}")


def load_translated_snapshot() -> Tuple[str, str, Dict[str, Any]]:
    if not TRANSLATED_CV_FILE.exists():
        raise FileNotFoundError(
            f"No existe {TRANSLATED_CV_FILE.name}. Ejecuta primero la opcion 2 (traduccion)."
        )

    payload = load_yaml_file(TRANSLATED_CV_FILE, {})
    if not isinstance(payload, dict):
        raise ValueError(f"{TRANSLATED_CV_FILE.name} tiene formato invalido")

    source_lang = payload.get("source_lang")
    translated_lang = payload.get("translated_lang")
    translated_data = payload.get("translated_data")

    if source_lang not in {"es", "en"} or translated_lang not in {"es", "en"}:
        raise ValueError(f"{TRANSLATED_CV_FILE.name} no contiene idiomas validos")

    return source_lang, translated_lang, normalize_cv_data(translated_data)


def _extract_shell_var(content: str, var_name: str) -> Optional[str]:
    pattern = rf"^{var_name}\s*=\s*([\"']?)([^\n\"']+)\1\s*$"
    match = re.search(pattern, content, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(2).strip()


def _expand_shell_path(value: str, env_home: str, env_name: str) -> str:
    home = str(Path.home())
    expanded = value
    replacements = {
        "${HOME}": home,
        "$HOME": home,
        "${ENV_HOME}": env_home,
        "$ENV_HOME": env_home,
        "${ENV_NAME}": env_name,
        "$ENV_NAME": env_name,
    }
    for token, token_value in replacements.items():
        expanded = expanded.replace(token, token_value)
    return expanded


def resolve_python_from_setup_script() -> str:
    setup_script = BASE_DIR / "setup_env.sh"
    default_env_home = str(Path.home() / ".python-envs")
    default_env_name = "cvtranslator"

    env_home = default_env_home
    env_name = default_env_name
    env_path: Optional[str] = None

    if setup_script.exists():
        content = setup_script.read_text(encoding="utf-8")
        env_home = _extract_shell_var(content, "ENV_HOME") or default_env_home
        env_name = _extract_shell_var(content, "ENV_NAME") or default_env_name
        env_path = _extract_shell_var(content, "ENV_PATH")

    expanded_env_home = _expand_shell_path(env_home, env_home, env_name)
    if env_path:
        env_root = Path(_expand_shell_path(env_path, expanded_env_home, env_name)).expanduser()
    else:
        env_root = Path(expanded_env_home).expanduser() / env_name

    candidates = [env_root / "Scripts" / "python.exe", env_root / "bin" / "python"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(
        "No se encontro el ejecutable de Python del entorno definido en setup_env.sh "
        f"(ruta esperada base: {env_root})."
    )


def ensure_dependencies_with_setup_env() -> None:
    if DEPENDENCY_IMPORT_ERROR is None:
        return

    target_python = resolve_python_from_setup_script()
    current_python = str(Path(sys.executable).resolve())
    resolved_target = str(Path(target_python).resolve())

    if current_python.lower() == resolved_target.lower():
        missing_name = DEPENDENCY_IMPORT_ERROR.name or "dependencias"
        raise ModuleNotFoundError(
            f"Faltan dependencias ({missing_name}) en el entorno configurado por setup_env.sh. "
            "Ejecuta setup_env.sh para instalar dependencias y vuelve a intentar."
        ) from DEPENDENCY_IMPORT_ERROR

    result = subprocess.run(
        [target_python, str(BASE_DIR / "build.py"), *sys.argv[1:]],
        cwd=str(BASE_DIR),
        check=False,
    )
    sys.exit(result.returncode)


def run_build_after_setup(payload: Dict[str, Any]) -> None:
    payload_file = BASE_DIR / ".build_payload.yaml"
    save_yaml_file(payload_file, payload)

    try:
        python_exec = resolve_python_from_setup_script()
        result = subprocess.run(
            [python_exec, str(BASE_DIR / "build.py"), "--run-payload", str(payload_file)],
            cwd=str(BASE_DIR),
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(f"build.py fallo con codigo {result.returncode}")
    finally:
        with contextlib.suppress(Exception):
            payload_file.unlink()


def run_option_1(payload: Dict[str, Any]) -> None:
    del payload
    data = load_cv_data(allow_missing=False)
    summary_seed = get_summary_seed(data)
    source_lang = heuristic_language(summary_seed) if summary_seed else "es"
    print("Generando resume.pdf sin traducir...")
    render_to_pdf(data, source_lang, "resume.pdf")


def run_option_2(payload: Dict[str, Any]) -> None:
    cv_data = normalize_cv_data(payload.get("cv_data", {}))
    model = str(payload.get("model", OLLAMA_MODEL)).strip() or OLLAMA_MODEL
    name_size = str(payload.get("name_font_size", DEFAULT_NAME_FONT_SIZE)).strip() or DEFAULT_NAME_FONT_SIZE
    body_size = str(payload.get("body_font_size", DEFAULT_BODY_FONT_SIZE)).strip() or DEFAULT_BODY_FONT_SIZE

    save_cv_data(cv_data)
    update_style_font_sizes(name_size, body_size)

    source_lang = detect_language(get_summary_seed(cv_data), model)
    target_lang = "en" if source_lang == "es" else "es"

    translated_data = translate_cv_data(cv_data, target_lang, model)
    data_by_lang = {source_lang: cv_data, target_lang: translated_data}

    if "es" not in data_by_lang or "en" not in data_by_lang:
        raise RuntimeError("No se pudo determinar correctamente los datos para es/en")

    print("Generando resume_es.pdf y resume_en.pdf...")
    render_to_pdf(data_by_lang["es"], "es")
    render_to_pdf(data_by_lang["en"], "en")

    save_translated_snapshot(source_lang, target_lang, translated_data, model)


def run_option_3(payload: Dict[str, Any]) -> None:
    name_size = str(payload.get("name_font_size", DEFAULT_NAME_FONT_SIZE)).strip() or DEFAULT_NAME_FONT_SIZE
    body_size = str(payload.get("body_font_size", DEFAULT_BODY_FONT_SIZE)).strip() or DEFAULT_BODY_FONT_SIZE

    update_style_font_sizes(name_size, body_size)

    source_data = load_cv_data(allow_missing=False)
    source_lang, translated_lang, translated_data = load_translated_snapshot()

    data_by_lang = {source_lang: source_data, translated_lang: translated_data}
    if "es" not in data_by_lang or "en" not in data_by_lang:
        raise RuntimeError("resume-translated.yaml no contiene combinacion valida de idiomas")

    print("Regenerando resume_es.pdf y resume_en.pdf sin usar traduccion...")
    render_to_pdf(data_by_lang["es"], "es")
    render_to_pdf(data_by_lang["en"], "en")


def execute_payload(payload: Dict[str, Any]) -> None:
    option = str(payload.get("option", "2"))
    if option == "1":
        run_option_1(payload)
    elif option == "2":
        run_option_2(payload)
    elif option == "3":
        run_option_3(payload)
    else:
        raise ValueError(f"Opcion no soportada: {option}")


def value_to_form_text(key: str, value: Any) -> str:
    if key == "summary":
        return value if isinstance(value, str) else ""

    if value is None:
        if key in {"personal_info", "skills"}:
            return "{}"
        return "[]"

    if isinstance(value, (dict, list)):
        text = yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
        return text.strip()

    return str(value)


def lines_to_list(raw_text: str) -> List[str]:
    items: List[str] = []
    for line in raw_text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^[-*]\\s*", "", cleaned)
        items.append(cleaned)
    return items


def parse_dict_field(raw_text: str, field_name: str) -> Dict[str, Any]:
    if not raw_text.strip():
        return {}
    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as e:
        raise ValueError(f"{field_name}: YAML invalido ({e})") from e

    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name}: debe ser un objeto YAML")
    return parsed


def parse_list_field(raw_text: str, field_name: str) -> List[Any]:
    if not raw_text.strip():
        return []

    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError:
        parsed = None

    if isinstance(parsed, list):
        return parsed

    if field_name in {"certifications", "courses"}:
        fallback = lines_to_list(raw_text)
        if fallback:
            return fallback

    raise ValueError(f"{field_name}: debe ser una lista YAML")


def ask_option_popup() -> Optional[str]:
    if not TK_AVAILABLE:
        return None

    result: Dict[str, str] = {}
    root = tk.Tk()
    root.title("Resume Generator")
    root.geometry("520x320")
    root.configure(bg="#f4f6fb")

    container = tk.Frame(root, bg="#f4f6fb", padx=20, pady=18)
    container.pack(fill="both", expand=True)

    tk.Label(
        container,
        text="Selecciona el flujo",
        font=("Segoe UI", 14, "bold"),
        bg="#f4f6fb",
        fg="#1f2937",
    ).pack(anchor="w", pady=(0, 10))

    option_var = tk.StringVar(value="2")

    options = [
        ("1", "1) Continuar sin traducir (genera resume.pdf)"),
        ("2", "2) Continuar con traduccion (formulario + resume_es/resume_en)"),
        ("3", "3) Editar documento traducido (solo tamanos, sin traducir)"),
    ]

    for value, text in options:
        card = tk.Frame(container, bg="white", bd=1, relief="solid", padx=10, pady=8)
        card.pack(fill="x", pady=5)
        tk.Radiobutton(
            card,
            text=text,
            variable=option_var,
            value=value,
            bg="white",
            anchor="w",
            font=("Segoe UI", 10),
            selectcolor="white",
            activebackground="white",
        ).pack(fill="x")

    button_row = tk.Frame(container, bg="#f4f6fb")
    button_row.pack(fill="x", pady=(14, 0))

    def on_continue() -> None:
        result["option"] = option_var.get()
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    tk.Button(button_row, text="Cancelar", command=on_cancel, padx=10, pady=6).pack(side="right")
    tk.Button(
        button_row,
        text="Continuar",
        command=on_continue,
        padx=12,
        pady=6,
        bg="#1a73e8",
        fg="white",
    ).pack(side="right", padx=(0, 8))

    root.mainloop()
    return result.get("option")


def ask_font_size_popup(title: str) -> Optional[Dict[str, str]]:
    if not TK_AVAILABLE:
        return None

    current_name, current_body = get_current_font_sizes()

    result: Dict[str, Dict[str, str]] = {}
    root = tk.Tk()
    root.title(title)
    root.geometry("520x240")
    root.configure(bg="#f4f6fb")

    container = tk.Frame(root, bg="#f4f6fb", padx=20, pady=18)
    container.pack(fill="both", expand=True)

    tk.Label(container, text=title, font=("Segoe UI", 13, "bold"), bg="#f4f6fb").pack(anchor="w", pady=(0, 10))

    name_var = tk.StringVar(value=current_name if current_name in NAME_SIZE_OPTIONS else DEFAULT_NAME_FONT_SIZE)
    body_var = tk.StringVar(value=current_body if current_body in BODY_SIZE_OPTIONS else DEFAULT_BODY_FONT_SIZE)

    form_card = tk.Frame(container, bg="white", bd=1, relief="solid", padx=12, pady=12)
    form_card.pack(fill="x")

    tk.Label(form_card, text="Tamano nombre (h1.name):", bg="white", anchor="w").grid(row=0, column=0, sticky="w", pady=5)
    ttk.Combobox(form_card, textvariable=name_var, values=NAME_SIZE_OPTIONS, state="readonly", width=12).grid(
        row=0, column=1, sticky="w", padx=10, pady=5
    )

    tk.Label(form_card, text="Tamano body:", bg="white", anchor="w").grid(row=1, column=0, sticky="w", pady=5)
    ttk.Combobox(form_card, textvariable=body_var, values=BODY_SIZE_OPTIONS, state="readonly", width=12).grid(
        row=1, column=1, sticky="w", padx=10, pady=5
    )

    button_row = tk.Frame(container, bg="#f4f6fb")
    button_row.pack(fill="x", pady=(14, 0))

    def on_continue() -> None:
        result["payload"] = {
            "name_font_size": name_var.get().strip() or DEFAULT_NAME_FONT_SIZE,
            "body_font_size": body_var.get().strip() or DEFAULT_BODY_FONT_SIZE,
        }
        root.destroy()

    def on_cancel() -> None:
        root.destroy()

    tk.Button(button_row, text="Cancelar", command=on_cancel, padx=10, pady=6).pack(side="right")
    tk.Button(
        button_row,
        text="Generar",
        command=on_continue,
        padx=12,
        pady=6,
        bg="#1a73e8",
        fg="white",
    ).pack(side="right", padx=(0, 8))

    root.mainloop()
    return result.get("payload")


def ask_translation_form_popup(cv_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not TK_AVAILABLE:
        return None

    models = get_ollama_models(OLLAMA_MODEL)
    current_name, current_body = get_current_font_sizes()

    result: Dict[str, Dict[str, Any]] = {}
    root = tk.Tk()
    root.title("Formulario de edicion de CV")
    root.geometry("1040x800")
    root.configure(bg="#eef2ff")

    shell = tk.Frame(root, bg="#eef2ff", padx=16, pady=14)
    shell.pack(fill="both", expand=True)

    tk.Label(
        shell,
        text="Resume Form Builder",
        font=("Segoe UI", 16, "bold"),
        bg="#eef2ff",
        fg="#111827",
    ).pack(anchor="w")
    tk.Label(
        shell,
        text="Pega o edita el contenido por cada key YAML. Luego continua para generar PDFs.",
        font=("Segoe UI", 10),
        bg="#eef2ff",
        fg="#374151",
    ).pack(anchor="w", pady=(2, 10))

    config_card = tk.Frame(shell, bg="white", bd=1, relief="solid", padx=12, pady=10)
    config_card.pack(fill="x", pady=(0, 10))

    model_var = tk.StringVar(value=OLLAMA_MODEL)
    name_var = tk.StringVar(value=current_name if current_name in NAME_SIZE_OPTIONS else DEFAULT_NAME_FONT_SIZE)
    body_var = tk.StringVar(value=current_body if current_body in BODY_SIZE_OPTIONS else DEFAULT_BODY_FONT_SIZE)

    tk.Label(config_card, text="Modelo Ollama:", bg="white", anchor="w").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Combobox(config_card, textvariable=model_var, values=models, state="readonly", width=32).grid(
        row=0, column=1, sticky="w", padx=8, pady=4
    )

    tk.Label(config_card, text="Tamano nombre (h1.name):", bg="white", anchor="w").grid(row=1, column=0, sticky="w", pady=4)
    ttk.Combobox(config_card, textvariable=name_var, values=NAME_SIZE_OPTIONS, state="readonly", width=14).grid(
        row=1, column=1, sticky="w", padx=8, pady=4
    )

    tk.Label(config_card, text="Tamano body:", bg="white", anchor="w").grid(row=2, column=0, sticky="w", pady=4)
    ttk.Combobox(config_card, textvariable=body_var, values=BODY_SIZE_OPTIONS, state="readonly", width=14).grid(
        row=2, column=1, sticky="w", padx=8, pady=4
    )

    canvas = tk.Canvas(shell, bg="#eef2ff", highlightthickness=0)
    scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    form_frame = tk.Frame(canvas, bg="#eef2ff")
    canvas_window = canvas.create_window((0, 0), window=form_frame, anchor="nw")

    def on_canvas_configure(event: tk.Event) -> None:
        canvas.itemconfigure(canvas_window, width=event.width)

    def on_form_configure(_: tk.Event) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    canvas.bind("<Configure>", on_canvas_configure)
    form_frame.bind("<Configure>", on_form_configure)

    widgets: Dict[str, ScrolledText] = {}

    for field in FORM_FIELDS:
        key = field["key"]
        card = tk.Frame(form_frame, bg="white", bd=1, relief="solid", padx=12, pady=10)
        card.pack(fill="x", pady=7)

        tk.Label(card, text=field["question"], bg="white", fg="#111827", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        text_box = ScrolledText(card, height=field["height"], wrap="word", font=("Consolas", 10))
        text_box.pack(fill="x", pady=(6, 2))
        text_box.insert("1.0", value_to_form_text(key, cv_data.get(key)))
        widgets[key] = text_box

    button_row = tk.Frame(form_frame, bg="#eef2ff")
    button_row.pack(fill="x", pady=12)

    def on_submit() -> None:
        parsed: Dict[str, Any] = {}
        try:
            for field in FORM_FIELDS:
                key = field["key"]
                mode = field["mode"]
                raw = widgets[key].get("1.0", "end").strip()

                if mode == "text":
                    parsed[key] = raw
                elif mode == "dict":
                    parsed[key] = parse_dict_field(raw, key)
                elif mode == "list":
                    parsed[key] = parse_list_field(raw, key)
                else:
                    raise ValueError(f"Modo de campo no soportado: {mode}")

            parsed = normalize_cv_data(parsed)

            result["payload"] = {
                "option": "2",
                "cv_data": parsed,
                "model": model_var.get().strip() or OLLAMA_MODEL,
                "name_font_size": name_var.get().strip() or DEFAULT_NAME_FONT_SIZE,
                "body_font_size": body_var.get().strip() or DEFAULT_BODY_FONT_SIZE,
            }
            root.destroy()
        except ValueError as e:
            messagebox.showerror("Formulario invalido", str(e), parent=root)

    def on_cancel() -> None:
        root.destroy()

    tk.Button(button_row, text="Cancelar", command=on_cancel, padx=10, pady=6).pack(side="right")
    tk.Button(
        button_row,
        text="Continuar y generar",
        command=on_submit,
        padx=12,
        pady=6,
        bg="#1a73e8",
        fg="white",
    ).pack(side="right", padx=(0, 8))

    root.mainloop()
    return result.get("payload")


def collect_payload_gui() -> Optional[Dict[str, Any]]:
    selected_option = ask_option_popup()
    if not selected_option:
        return None

    if selected_option == "1":
        return {"option": "1"}

    if selected_option == "2":
        initial_data = load_cv_data(allow_missing=True)
        return ask_translation_form_popup(initial_data)

    if selected_option == "3":
        font_payload = ask_font_size_popup("Editar documento traducido")
        if not font_payload:
            return None
        font_payload["option"] = "3"
        return font_payload

    raise ValueError(f"Opcion invalida: {selected_option}")


def collect_payload_cli() -> Optional[Dict[str, Any]]:
    print("\nOpciones:")
    print("1.- Continuar sin traducir (resume.pdf)")
    print("2.- Continuar con traduccion")
    print("3.- Editar documento traducido (solo tamanos)")
    option = input("Elige una opcion (1, 2 o 3) [default 2]: ").strip() or "2"

    if option == "1":
        return {"option": "1"}

    if option == "2":
        cv_data = load_cv_data(allow_missing=False)
        models = get_ollama_models(OLLAMA_MODEL)
        print("\nModelos disponibles:")
        for idx, model in enumerate(models, start=1):
            print(f"{idx}. {model}")
        selected = input(f"Selecciona modelo [default {OLLAMA_MODEL}]: ").strip()
        model = selected if selected else OLLAMA_MODEL

        name_default, body_default = get_current_font_sizes()
        name_size = input(f"Tamano nombre h1.name [default {name_default}]: ").strip() or name_default
        body_size = input(f"Tamano body [default {body_default}]: ").strip() or body_default

        return {
            "option": "2",
            "cv_data": cv_data,
            "model": model,
            "name_font_size": name_size,
            "body_font_size": body_size,
        }

    if option == "3":
        name_default, body_default = get_current_font_sizes()
        name_size = input(f"Tamano nombre h1.name [default {name_default}]: ").strip() or name_default
        body_size = input(f"Tamano body [default {body_default}]: ").strip() or body_default
        return {
            "option": "3",
            "name_font_size": name_size,
            "body_font_size": body_size,
        }

    print("Opcion invalida.")
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resume generator with GUI workflow")
    parser.add_argument(
        "--run-payload",
        type=str,
        default="",
        help="Ruta al payload YAML para ejecutar una corrida interna sin interfaz.",
    )
    return parser.parse_args()


def main() -> None:
    ensure_dependencies_with_setup_env()
    args = parse_args()

    if args.run_payload:
        payload_path = Path(args.run_payload)
        payload = load_yaml_file(payload_path, {})
        if not isinstance(payload, dict):
            raise ValueError("Payload invalido para --run-payload")
        execute_payload(payload)
        return

    if TK_AVAILABLE:
        payload = collect_payload_gui()
    else:
        print("[WARN] Tkinter no disponible. Se usara modo CLI.")
        payload = collect_payload_cli()

    if not payload:
        print("Operacion cancelada por el usuario.")
        return

    run_build_after_setup(payload)


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as fnf:
        print(f"[ERROR] Archivo no encontrado: {fnf}")
        sys.exit(1)
    except Exception:
        print("[ERROR] Ejecucion inesperada:")
        traceback.print_exc()
        sys.exit(1)
