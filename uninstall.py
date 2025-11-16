#!/usr/bin/env python3
import shutil
from pathlib import Path

def main():
    print("=== CV Translator - Desinstalador ===\n")
    
    # Definir ruta del venv
    venv_path = Path.home() / ".python-envs" / "cvTranslator"
    
    if not venv_path.exists():
        print(f"✓ No se encontró entorno virtual en: {venv_path}")
        print("No hay nada que desinstalar.")
        return
    
    # Confirmar eliminación
    print(f"Se eliminará el entorno virtual: {venv_path}")
    confirm = input("¿Continuar? (s/n): ").lower().strip()
    
    if confirm != 's':
        print("Desinstalación cancelada.")
        return
    
    # Eliminar venv
    try:
        shutil.rmtree(venv_path)
        print(f"\n✓ Entorno virtual eliminado correctamente")
    except Exception as e:
        print(f"✗ Error al eliminar entorno virtual: {e}")
        return
    
    print("\n=== Desinstalación completada ===")

if __name__ == "__main__":
    main()
