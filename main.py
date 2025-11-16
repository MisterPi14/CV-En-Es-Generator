import typer
import json
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from pdf_extractor import extract_text_from_pdf
from ollama_client import list_available_models, structure_cv_with_llm, translate_cv
from pdf_generator import PDFGenerator
from cv_importer import import_cv_interactive

app = typer.Typer()
console = Console()

@app.command()
def translate(
    target_lang: str = typer.Option("english", "--lang", "-l", help="Idioma destino (ej: english, spanish, french)"),
    output_format: str = typer.Option("json", "--format", "-f", help="Formato de salida (json, pdf)"),
    model: str = typer.Option(None, "--model", "-m", help="Modelo de Ollama a usar"),
    template_type: str = typer.Option(None, "--template", "-t", help="Tipo de plantilla (html, word)"),
    template_name: str = typer.Option(None, "--template-name", "-tn", help="Nombre de la plantilla específica")
):
    """Traduce un currículum vitae desde JSON al idioma especificado."""
    
    # Listar CVs disponibles en resumes_loaded
    resumes_dir = Path("resumes_loaded")
    
    if not resumes_dir.exists() or not any(resumes_dir.glob("*.json")):
        console.print("[red]No se encontraron CVs en resumes_loaded/[/red]")
        console.print("[yellow]Usa 'python main.py import-cv' para crear un CV primero[/yellow]")
        raise typer.Exit(1)
    
    # Obtener lista de CVs
    cv_files = list(resumes_dir.glob("*.json"))
    
    # Mostrar tabla de CVs disponibles
    table = Table(title="CVs Disponibles")
    table.add_column("Nº", style="cyan")
    table.add_column("Archivo", style="green")
    
    for idx, cv_file in enumerate(cv_files, 1):
        table.add_row(str(idx), cv_file.name)
    
    console.print("\n")
    console.print(table)
    
    # Seleccionar CV
    selection = Prompt.ask(
        "\n[yellow]Selecciona el número del CV a traducir[/yellow]",
        default="1"
    )
    
    try:
        selected_cv = cv_files[int(selection) - 1]
    except (ValueError, IndexError):
        console.print("[red]Selección inválida[/red]")
        raise typer.Exit(1)
    
    console.print(f"\n[green]✓ CV seleccionado: {selected_cv.name}[/green]")
    file_path_obj = selected_cv
    
    # Listar modelos disponibles
    console.print("\n[cyan]Obteniendo modelos disponibles en Ollama...[/cyan]")
    models = list_available_models()
    
    if not models:
        console.print("[red]No se encontraron modelos en Ollama. Asegúrate de tener Ollama ejecutándose.[/red]")
        raise typer.Exit(1)
    
    # Mostrar modelos disponibles
    table = Table(title="Modelos Disponibles")
    table.add_column("Nº", style="cyan")
    table.add_column("Modelo", style="green")
    
    for idx, model_name in enumerate(models, 1):
        table.add_row(str(idx), model_name)
    
    console.print(table)
    
    # Seleccionar modelo
    if model and model in models:
        selected_model = model
    else:
        selection = Prompt.ask(
            "\n[yellow]Selecciona el número del modelo a usar[/yellow]",
            default="1"
        )
        try:
            selected_model = models[int(selection) - 1]
        except (ValueError, IndexError):
            console.print("[red]Selección inválida[/red]")
            raise typer.Exit(1)
    
    console.print(f"\n[green]✓ Modelo seleccionado: {selected_model}[/green]")
    
    # Cargar JSON directamente
    console.print("\n[cyan]Cargando CV desde JSON...[/cyan]")
    with open(file_path_obj, 'r', encoding='utf-8') as f:
        cv_data = json.load(f)
    console.print("[green]✓ CV cargado correctamente[/green]")
    
    # ============================================================================
    # FUNCIONALIDAD PDF COMENTADA - PENDIENTE DE IMPLEMENTACIÓN
    # ============================================================================
    # La extracción desde PDF está temporalmente deshabilitada porque:
    # 1. Requiere usar IA para estructurar (no determinístico)
    # 2. El flujo recomendado es: import-cv → editar JSON → translate
    # 3. Mantener código para futura implementación con parser determinístico
    #
    # Para habilitar en el futuro:
    # - Descomentar el código siguiente
    # - Agregar parámetro file_path como Argument opcional
    # - Implementar detección automática de tipo de archivo
    # ============================================================================
    #
    # # Determinar si es JSON o PDF
    # if file_path_obj.suffix.lower() == '.json':
    #     # Cargar JSON directamente
    #     console.print("\n[cyan]Cargando CV desde JSON...[/cyan]")
    #     with open(file_path_obj, 'r', encoding='utf-8') as f:
    #         cv_data = json.load(f)
    #     console.print("[green]✓ CV cargado correctamente[/green]")
    # else:
    #     # Extraer texto del PDF
    #     with Progress(
    #         SpinnerColumn(),
    #         TextColumn("[progress.description]{task.description}"),
    #         console=console
    #     ) as progress:
    #         task = progress.add_task("[cyan]Extrayendo texto del PDF...", total=None)
    #         text = extract_text_from_pdf(str(file_path_obj))
    #         progress.update(task, completed=True)
    #     
    #     if not text:
    #         console.print("[red]No se pudo extraer texto del PDF[/red]")
    #         raise typer.Exit(1)
    #     
    #     console.print(f"[green]✓ Texto extraído: {len(text)} caracteres[/green]")
    #     
    #     # Estructurar CV con LLM
    #     with Progress(
    #         SpinnerColumn(),
    #         TextColumn("[progress.description]{task.description}"),
    #         console=console
    #     ) as progress:
    #         task = progress.add_task("[cyan]Estructurando CV con IA...", total=None)
    #         cv_data = structure_cv_with_llm(text, selected_model)
    #         progress.update(task, completed=True)
    #     
    #     if not cv_data:
    #         console.print("[red]No se pudo estructurar el CV[/red]")
    #         raise typer.Exit(1)
    #     
    #     console.print("[green]✓ CV estructurado correctamente[/green]")
    
    # Traducir CV
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task(f"[cyan]Traduciendo CV a {target_lang}...", total=None)
        translated_cv = translate_cv(cv_data, target_lang, selected_model)
        progress.update(task, completed=True)
    
    console.print(f"[green]✓ CV traducido a {target_lang}[/green]")
    
    # Guardar resultado
    file_name = file_path_obj.stem
    
    if output_format == "pdf":
        # Generate PDF using templates
        pdf_generator = PDFGenerator()
        
        # Select template type if not specified
        if not template_type:
            template_type = Prompt.ask(
                "\n[yellow]Selecciona el tipo de plantilla[/yellow]",
                choices=["html", "word"],
                default="html"
            )
        
        # List available templates
        available_templates = pdf_generator.list_available_templates(template_type)
        
        if not available_templates:
            console.print(f"[red]No se encontraron plantillas {template_type}. Revisa la carpeta templates/{template_type}/[/red]")
            if template_type == "word":
                console.print("[yellow]Consulta templates/word/README.md para crear plantillas Word[/yellow]")
            raise typer.Exit(1)
        
        # Show available templates
        table = Table(title=f"Plantillas {template_type.upper()} Disponibles")
        table.add_column("Nº", style="cyan")
        table.add_column("Plantilla", style="green")
        
        for idx, template in enumerate(available_templates, 1):
            table.add_row(str(idx), template)
        
        console.print(table)
        
        # Select template
        if template_name and template_name in available_templates:
            selected_template = template_name
        else:
            selection = Prompt.ask(
                "\n[yellow]Selecciona el número de la plantilla[/yellow]",
                default="1"
            )
            try:
                selected_template = available_templates[int(selection) - 1]
            except (ValueError, IndexError):
                console.print("[red]Selección inválida[/red]")
                raise typer.Exit(1)
        
        console.print(f"\n[green]✓ Plantilla seleccionada: {selected_template}[/green]")
        
        # Generate PDF
        output_file = f"{file_name}_{target_lang}.pdf"
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]Generando PDF con plantilla {template_type}...", total=None)
            
            if template_type == "html":
                success = pdf_generator.generate_pdf_from_html(translated_cv, selected_template, output_file)
            else:  # word
                success = pdf_generator.generate_pdf_from_word(translated_cv, selected_template, output_file)
            
            progress.update(task, completed=True)
        
        if success:
            console.print(f"\n[bold green]✓ PDF generado exitosamente![/bold green]")
            console.print(f"[cyan]Archivo guardado en: {output_file}[/cyan]")
        else:
            console.print(f"\n[red]Error al generar el PDF[/red]")
            raise typer.Exit(1)
    
    else:
        # Save as JSON
        output_file = f"{file_name}_{target_lang}.{output_format}"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(translated_cv, f, ensure_ascii=False, indent=2)
        
        console.print(f"\n[bold green]✓ Traducción completada![/bold green]")
        console.print(f"[cyan]Archivo guardado en: {output_file}[/cyan]")

@app.command()
def extract(
    pdf_path: str = typer.Argument(..., help="Ruta al archivo PDF del CV"),
    model: str = typer.Option(None, "--model", "-m", help="Modelo de Ollama a usar")
):
    """Extrae y estructura un CV sin traducir."""
    
    if not Path(pdf_path).exists():
        console.print(f"[red]Error: El archivo {pdf_path} no existe[/red]")
        raise typer.Exit(1)
    
    # Listar y seleccionar modelo
    console.print("\n[cyan]Obteniendo modelos disponibles en Ollama...[/cyan]")
    models = list_available_models()
    
    if not models:
        console.print("[red]No se encontraron modelos en Ollama.[/red]")
        raise typer.Exit(1)
    
    table = Table(title="Modelos Disponibles")
    table.add_column("Nº", style="cyan")
    table.add_column("Modelo", style="green")
    
    for idx, model_name in enumerate(models, 1):
        table.add_row(str(idx), model_name)
    
    console.print(table)
    
    if model and model in models:
        selected_model = model
    else:
        selection = Prompt.ask("\n[yellow]Selecciona el número del modelo[/yellow]", default="1")
        try:
            selected_model = models[int(selection) - 1]
        except (ValueError, IndexError):
            console.print("[red]Selección inválida[/red]")
            raise typer.Exit(1)
    
    console.print(f"\n[green]✓ Modelo seleccionado: {selected_model}[/green]")
    
    # Extraer y estructurar
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]Extrayendo texto del PDF...", total=None)
        text = extract_text_from_pdf(pdf_path)
        progress.update(task, completed=True)
    
    console.print(f"[green]✓ Texto extraído: {len(text)} caracteres[/green]")
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]Estructurando CV con IA...", total=None)
        cv_data = structure_cv_with_llm(text, selected_model)
        progress.update(task, completed=True)
    
    # Guardar
    pdf_name = Path(pdf_path).stem
    output_file = f"{pdf_name}_structured.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cv_data, f, ensure_ascii=False, indent=2)
    
    console.print(f"\n[bold green]✓ Extracción completada![/bold green]")
    console.print(f"[cyan]Archivo guardado en: {output_file}[/cyan]")

@app.command()
def models():
    """Lista todos los modelos disponibles en Ollama."""
    console.print("\n[cyan]Modelos disponibles en Ollama:[/cyan]\n")
    models_list = list_available_models()
    
    if not models_list:
        console.print("[red]No se encontraron modelos. Asegúrate de tener Ollama ejecutándose.[/red]")
        return
    
    for model in models_list:
        console.print(f"  • [green]{model}[/green]")
    console.print()

@app.command()
def import_cv(
    output: str = typer.Option(None, "--output", "-o", help="Nombre del archivo JSON de salida")
):
    """Importa un CV mediante formulario interactivo y lo guarda en JSON."""
    import_cv_interactive(output)

@app.command()
def templates():
    """Lista las plantillas disponibles para generar PDFs."""
    pdf_generator = PDFGenerator()
    
    console.print("\n[cyan]Plantillas disponibles:[/cyan]\n")
    
    # HTML templates
    html_templates = pdf_generator.list_available_templates("html")
    if html_templates:
        console.print("[green]Plantillas HTML:[/green]")
        for template in html_templates:
            console.print(f"  • {template}")
    else:
        console.print("[yellow]No hay plantillas HTML disponibles[/yellow]")
    
    console.print()
    
    # Word templates
    word_templates = pdf_generator.list_available_templates("word")
    if word_templates:
        console.print("[green]Plantillas Word:[/green]")
        for template in word_templates:
            console.print(f"  • {template}")
    else:
        console.print("[yellow]No hay plantillas Word disponibles[/yellow]")
        console.print("[cyan]Consulta templates/word/README.md para crear plantillas Word[/cyan]")
    
    console.print()

if __name__ == "__main__":
    app()
