#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

def main():
    print("=== CV Translator - Instalador ===\n")
    
    # Definir ruta del venv
    venv_path = Path.home() / ".python-envs" / "cvTranslator"
    
    # Crear directorio si no existe
    venv_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Crear venv
    print(f"Creando entorno virtual en: {venv_path}")
    try:
        subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
        print("✓ Entorno virtual creado\n")
    except subprocess.CalledProcessError as e:
        print(f"✗ Error al crear entorno virtual: {e}")
        sys.exit(1)
    
    # Determinar ruta del pip en el venv
    if sys.platform == "win32":
        pip_path = venv_path / "Scripts" / "pip.exe"
    else:
        pip_path = venv_path / "bin" / "pip"
    
    # Instalar dependencias
    print("Instalando dependencias desde requirements.txt...")
    try:
        subprocess.run([str(pip_path), "install", "-r", "requirements.txt"], check=True)
        print("\n✓ Dependencias instaladas correctamente\n")
    except subprocess.CalledProcessError as e:
        print(f"✗ Error al instalar dependencias: {e}")
        sys.exit(1)
    
    print("=== Instalación completada ===")
    print(f"\nEntorno virtual: {venv_path}")
    print("\nPara usar la aplicación, ejecuta:")
    print("  python main.py <comando>")

if __name__ == "__main__":
    main()
