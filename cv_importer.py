import json
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
from typing import Dict, Any, List

console = Console()

def import_cv_interactive(output_file: str = None) -> Dict[Any, Any]:
    """Formulario interactivo para capturar datos del CV"""
    
    console.print("\n[bold cyan]═══ IMPORTAR CV - FORMULARIO INTERACTIVO ═══[/bold cyan]\n")
    
    cv_data = {}
    
    # Personal Info
    console.print("[yellow]INFORMACIÓN PERSONAL[/yellow]")
    cv_data["personal_info"] = {
        "name": Prompt.ask("Nombre completo"),
        "email": Prompt.ask("Email"),
        "phone": Prompt.ask("Teléfono"),
        "location": Prompt.ask("Ubicación (Ciudad, País)"),
        "linkedin": Prompt.ask("LinkedIn (opcional)", default="")
    }
    
    # Summary
    console.print("\n[yellow]RESUMEN PROFESIONAL[/yellow]")
    cv_data["summary"] = Prompt.ask("Resumen profesional (breve descripción)")
    
    # Experience
    console.print("\n[yellow]EXPERIENCIA LABORAL[/yellow]")
    cv_data["experience"] = []
    add_more = True
    
    while add_more:
        exp_num = len(cv_data["experience"]) + 1
        console.print(f"\n[cyan]Experiencia #{exp_num}[/cyan]")
        
        experience = {
            "title": Prompt.ask("  Cargo/Puesto"),
            "company": Prompt.ask("  Empresa"),
            "duration": Prompt.ask("  Período (ej: 2020-2023)"),
            "description": Prompt.ask("  Descripción del puesto")
        }
        cv_data["experience"].append(experience)
        
        add_more = Confirm.ask("¿Agregar otra experiencia?", default=False)
    
    # Education
    console.print("\n[yellow]EDUCACIÓN[/yellow]")
    cv_data["education"] = []
    add_more = True
    
    while add_more:
        edu_num = len(cv_data["education"]) + 1
        console.print(f"\n[cyan]Educación #{edu_num}[/cyan]")
        
        education = {
            "degree": Prompt.ask("  Título/Grado"),
            "institution": Prompt.ask("  Institución"),
            "year": Prompt.ask("  Año (ej: 2020)")
        }
        cv_data["education"].append(education)
        
        add_more = Confirm.ask("¿Agregar otra educación?", default=False)
    
    # Skills
    console.print("\n[yellow]HABILIDADES[/yellow]")
    console.print("[dim]Ingresa habilidades separadas por comas[/dim]")
    skills_input = Prompt.ask("Habilidades")
    cv_data["skills"] = [s.strip() for s in skills_input.split(",") if s.strip()]
    
    # Languages
    console.print("\n[yellow]IDIOMAS[/yellow]")
    console.print("[dim]Ingresa idiomas separados por comas[/dim]")
    languages_input = Prompt.ask("Idiomas")
    cv_data["languages"] = [l.strip() for l in languages_input.split(",") if l.strip()]
    
    # Certifications
    console.print("\n[yellow]CERTIFICACIONES[/yellow]")
    console.print("[dim]Ingresa certificaciones separadas por comas (opcional)[/dim]")
    certs_input = Prompt.ask("Certificaciones", default="")
    cv_data["certifications"] = [c.strip() for c in certs_input.split(",") if c.strip()]
    
    # Save to file
    resumes_dir = Path("resumes_loaded")
    resumes_dir.mkdir(exist_ok=True)
    
    if not output_file:
        name_slug = cv_data["personal_info"]["name"].lower().replace(" ", "_")
        output_file = f"{name_slug}_cv.json"
    
    output_path = resumes_dir / output_file
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(cv_data, f, ensure_ascii=False, indent=2)
    
    console.print(f"\n[bold green]✓ CV guardado en: {output_path}[/bold green]")
    
    return cv_data
