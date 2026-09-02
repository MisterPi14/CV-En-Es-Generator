"""Auditoria: intercepta ollama.chat y muestra TODO lo que saldria al modelo,
sin llamar realmente al modelo. Falla si detecta PII en el payload."""
import sys, re, io
from pathlib import Path

# La raiz se deduce de la ubicacion de este archivo: antes estaba escrita a
# mano y mover el repo rompia la auditoria.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build

# El YAML a auditar: el que se pase por argumento, o la primera fuente escrita
# a mano. `resume.yaml` (el default de load_cv_data) ya no existe en el repo
# desde que las fuentes declaran el idioma en el nombre, asi que sin esto la
# auditoria fallaba con FileNotFoundError antes de auditar nada.
if len(sys.argv) > 1:
    SOURCE = Path(sys.argv[1])
    if not SOURCE.is_absolute():
        SOURCE = build.BASE_DIR / SOURCE
else:
    DERIVED_RE = re.compile(r'\.(es|en)\.[^.]+\.yaml$')
    SOURCE = next((p for p in build.discover_yamls() if not DERIVED_RE.search(p.name)), None)
    if SOURCE is None:
        sys.exit("[AUDIT] No hay ninguna fuente *.yaml que auditar en el directorio.")
print(f"[AUDIT] Fuente: {SOURCE.name}")

DATA = build.load_cv_data(SOURCE)
info = DATA.get('personal_info', {})

sent = []


def fake_chat(model=None, messages=None, **kw):
    payload = "\n".join(m['content'] for m in messages)
    sent.append(payload)
    # Devuelve el <source_text> tal cual, simulando un modelo perfecto.
    m = re.search(r'<source_text>\n(.*)\n</source_text>', payload, re.S)
    return {'message': {'content': m.group(1) if m else 'en'}}


build.ollama = type('X', (), {'chat': staticmethod(fake_chat)})
build.OLLAMA_AVAILABLE = True

out = build.translate_cv_data(DATA, 'es')

blob = "\n".join(sent)
print("\n" + "=" * 60)
print(f"Llamadas al modelo: {len(sent)}   |   caracteres enviados: {len(blob)}")

needles = {
    'nombre completo': info.get('name', ''),
    'email': info.get('email', ''),
    'telefono': info.get('phone', ''),
    'github_url': info.get('github_url', ''),
    'linkedin_url': info.get('linkedin_url', ''),
    'portfolio_url': info.get('portfolio_url', ''),
}
leaks = 0
for label, needle in needles.items():
    if needle and needle in blob:
        print(f"  [FUGA] {label}: {needle!r}")
        leaks += 1
    else:
        print(f"  [ok]   {label} no aparece en el payload")

for pat, label in [(r'https?://', 'cualquier URL'),
                   (r'[\w.+-]+@[\w-]+\.\w+', 'cualquier correo'),
                   (r'\b\d\.\d{1,2}/10\b', 'GPA')]:
    hits = re.findall(pat, blob)
    if hits:
        print(f"  [FUGA] {label}: {sorted(set(hits))[:5]}")
        leaks += 1
    else:
        print(f"  [ok]   {label} no aparece en el payload")

# Round-trip: con un modelo perfecto el resultado debe ser identico al origen.
def walk(a, b, path=""):
    diffs = []
    if isinstance(a, dict):
        for k in a:
            diffs += walk(a[k], b.get(k), f"{path}.{k}")
    elif isinstance(a, list):
        for i, x in enumerate(a):
            diffs += walk(x, b[i] if i < len(b) else None, f"{path}[{i}]")
    elif a != b:
        diffs.append((path, a, b))
    return diffs

diffs = walk(DATA, out)
print(f"\nRound-trip (modelo ideal): {len(diffs)} campos alterados"
      + ("" if not diffs else f" -> {diffs[:3]}"))
print("=" * 60)
print("RESULTADO:", "FUGAS DETECTADAS" if leaks else "SIN FUGAS DE PII")
sys.exit(1 if leaks else 0)
