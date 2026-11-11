# Generador de CV (CLI)

Un YAML con tu CV → PDF con tres diseños (`legacy`, `generation`, `capitalone`),
y traducción ES↔EN con un modelo de Ollama.

## Arrancar

| Desde | Comando |
|---|---|
| Explorador de Windows | doble clic en **`run.bat`** |
| PowerShell / Git Bash | `./run.bat` (sin espacio: `. run.bat` lo ejecuta como script de Bash y falla) |
| Sin menú | `./run.bat --mode pdf --input "mi-cv.en.yaml" --template capitalone` |

`run.bat` prepara solo el entorno `.venv\cvtranslator`, las dependencias y Chromium.
No ejecutes `python build.py` directamente: puede tomar otro Python sin Playwright y
generar un `.html` en vez del PDF.

## Menú

| Opción | Qué hace |
|---|---|
| **1. Traducir** | Lee un YAML y escribe otro traducido: `<nombre>.<idioma>.<modelo>.yaml`. Requiere Ollama. |
| **2. Generar PDF** | Elige YAML y template → `<nombre-del-yaml>.<template>.pdf`. No usa el modelo. |
| **3. Configuración** | Ajustes que se guardan en `settings.json`. |
| **0. Salir** | Cierra el programa. |

Al terminar cada operación, con éxito o con error, el menú vuelve a aparecer: la
ventana solo se cierra con **0. Salir**. Con argumentos (`--mode …`) se ejecuta una
vez y termina.

**Configuración → Modelo de traducción** (los modelos de embeddings nunca aparecen):

| Opción | Qué muestra |
|---|---|
| Locales | Los modelos descargados en tu Ollama, con su tamaño. |
| Nube | El catálogo de la nube de Ollama, del más reciente al más antiguo, 10 por página. Escribe `m` para la siguiente página, un texto para filtrar (`glm`) o un número para elegir. Requiere `ollama signin` y créditos o suscripción en la cuenta. |
| Escribir el nombre | Cualquier nombre que acepte Ollama (`gemma4:12b`, `kimi-k2.6:cloud`). |

El modelo elegido se usa en las traducciones siguientes y su nombre queda en el del
YAML traducido. Antes de traducir se prueba con una llamada: si no responde (Ollama
cerrado, modelo inexistente, nube sin créditos), la traducción no empieza y se
explica por qué.

## Editar el CV (solo el YAML)

### Mostrar u ocultar

```yaml
projects:
- title: Mi proyecto
  include: false        # no sale en el PDF; el contenido se conserva
```

`include: false` sirve en cualquier elemento de lista y en secciones enteras.
Los elementos sueltos de `skills` no lo admiten: comenta la línea con `#`.

### Orden de las secciones

Las secciones se imprimen **en el orden de sus claves en el YAML**. Para mover una,
mueve su bloque. La cabecera (`personal_info`) va siempre arriba.

### Cambiar el título de una sección

Escribe el título entre paréntesis después de la clave. El formato no cambia:

```yaml
extracurriculars(Actividades):
- exp: ...
```

No cambies la clave en sí (`extracurricularsed:`): la sección dejaría de
reconocerse. Si el título lleva `:` o `#`, pon la clave entre comillas:
`"awards(Premios: 2025)":`.

### Agregar una sección nueva

Cualquier clave que el programa no conoce es una sección nueva. El título es el
texto entre paréntesis o, si no lo hay, la clave tal cual:

```yaml
Volunteer Work:                       # título: "Volunteer Work"
- name: Banco de alimentos            # también: title, exp, role, institution
  period: 2025                        # también: date, year
  url: https://ejemplo.org            # opcional: enlaza el título
  description: |-                     # también: desc, focus; cada línea es una viñeta
    Organicé la recolección.
    Coordiné a 10 voluntarios.
- Un elemento de texto simple

awards(Premios): Un párrafo de texto.

tools(Herramientas):
  Editores: [Vim, VS Code]            # se imprime "Editores: Vim | VS Code"
```

Una sección vacía no se imprime. Las nuevas se traducen igual que el resto.

### Textos fijos (opcional)

El bloque `ui` del final cambia rótulos que no son títulos de sección (`label_gpa`,
`label_github`, `document_title`…). Edita solo el valor, nunca la clave.
`ui_templates.<template>` aplica un texto solo a ese diseño. Un título entre
paréntesis gana sobre `ui`.

## Una página exacta (`generation`, `capitalone`)

El tamaño de letra se ajusta solo: **crece** si hay poco contenido y **se reduce**
si hay mucho, hasta llenar la página al 100 %. Nunca se recorta contenido: solo
desaparece lo marcado con `include: false`. Si la letra baja de 6 px, la consola
avisa que impreso será difícil de leer. `legacy` ocupa las páginas que necesite.

## Traducción

Traduce títulos, descripciones, títulos entre paréntesis, secciones nuevas y textos
`ui`. No envía al modelo nombre, correo, teléfono, URLs ni promedio. Revisa el YAML
traducido antes de imprimir: el modelo puede variar la redacción entre corridas.

## Pruebas

```powershell
./.venv/cvtranslator/Scripts/python.exe -m unittest discover -s tests -v
```

`test_fit_pages` abre Chromium y comprueba que poco, mediano y mucho contenido
quepan en una página llena; las demás no usan navegador ni modelo.
