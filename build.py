import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
import sys
import traceback
import tempfile
import contextlib

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

CV_FILE = BASE_DIR / "cv.yaml"
OUTPUT_PREFIX = "cv_"

UI_STRINGS = {
    "es": {
        "section_summary": "Resumen Profesional",
        "section_experience": "Experiencia Profesional",
        "section_education": "Educación",
        "section_skills": "Habilidades"
    },
    "en": {
        "section_summary": "Professional Summary",
        "section_experience": "Work Experience",
        "section_education": "Education",
        "section_skills": "Skills"
    }
}

def load_cv_data():
    with CV_FILE.open('r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data

def render_to_pdf(data: dict, lang: str):
    """Renderiza el CV a PDF (si WeasyPrint funciona) o genera fallback HTML.

    Si WeasyPrint no está disponible (falta libgobject/pango en Windows u otra dependencia),
    se genera un archivo HTML para inspección manual y se muestra una guía breve.
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(['html', 'xml'])
    )
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

def main():
    data = load_cv_data()

    for lang in ["es", "en"]:
        if lang == "es":
            data_lang = data
        else:
            # TODO: Implement translation logic here
            data_lang = data
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
