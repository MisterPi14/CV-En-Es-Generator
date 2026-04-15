import customtkinter as ctk
from tkinter import messagebox, filedialog
import yaml
import subprocess
import sys
import os
import threading
from pathlib import Path

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

BASE_DIR = Path(__file__).parent
CV_FILE = BASE_DIR / "resume.yaml"
TRANSLATED_FILE = BASE_DIR / "resume-translated.yaml"
BUILD_SCRIPT = BASE_DIR / "build.py"
SETUP_SCRIPT = BASE_DIR / "setup_env.sh"
CSS_FILE = BASE_DIR / "static" / "style.css"

DEFAULT_NAME_SIZE = "40px"
DEFAULT_BODY_SIZE = "10px"
DEFAULT_MODEL = "gemma3:4b"

NAME_SIZE_OPTIONS = [f"{i}px" for i in range(20, 61, 2)]
BODY_SIZE_OPTIONS = [f"{i}px" for i in [8, 8.5, 9, 9.5, 10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5, 15, 15.5, 16]]


def get_ollama_models():
    try:
        result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, shell=True)
        if result.returncode != 0:
            return [DEFAULT_MODEL]
        
        lines = result.stdout.strip().split('\n')[1:]
        models = []
        for line in lines:
            if line.strip():
                parts = line.split()
                if parts:
                    models.append(parts[0])
        
        return models if models else [DEFAULT_MODEL]
    except Exception:
        return [DEFAULT_MODEL]


def load_yaml_data(file_path: Path) -> dict:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load YAML: {e}")
        return {}


def save_yaml_data(data: dict, file_path: Path):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save YAML: {e}")
        return False


def run_setup_and_build(model: str, name_size: str, body_size: str, yaml_file: Path, lang: str, no_translate: bool = False, callback=None, stream_callback=None):
    def thread_target():
        try:
            setup_cmd = f'bash "{SETUP_SCRIPT}"' if os.name != 'nt' else f'cmd /c "{SETUP_SCRIPT}"'
            
            if stream_callback:
                proc = subprocess.Popen(setup_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(BASE_DIR))
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        stream_callback(line.rstrip())
                    if proc.poll() is not None:
                        break
                proc.wait()
                if proc.returncode != 0:
                    err = proc.stderr.read()
                    callback(f"Setup error: {err}", True) if callback else None
                    return
            else:
                result = subprocess.run(setup_cmd, shell=True, capture_output=True, text=True, cwd=str(BASE_DIR))
                if result.returncode != 0:
                    if callback:
                        callback(f"Setup error: {result.stderr}", True)
                    return
            
            build_cmd = [
                sys.executable,
                str(BUILD_SCRIPT),
                f"--model={model}",
                f"--name-size={name_size}",
                f"--body-size={body_size}",
                f"--yaml-file={str(yaml_file)}",
                f"--lang={lang}"
            ]
            
            if no_translate:
                build_cmd.append("--no-translate")
            
            if stream_callback:
                proc = subprocess.Popen(build_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(BASE_DIR))
                for line in iter(proc.stdout.readline, ''):
                    if line:
                        stream_callback(line.rstrip())
                    if proc.poll() is not None:
                        break
                proc.wait()
                if proc.returncode != 0:
                    err = proc.stderr.read()
                    callback(f"Build error: {err}", True) if callback else None
                    return
                
                if callback:
                    callback("Generación completada", False)
            else:
                result = subprocess.run(build_cmd, capture_output=True, text=True, cwd=str(BASE_DIR))
                
                if result.returncode != 0:
                    if callback:
                        callback(f"Build error: {result.stderr}", True)
                    return
                
                if callback:
                    callback(result.stdout, False)
                
        except Exception as e:
            if callback:
                callback(f"Error: {str(e)}", True)
    
    thread = threading.Thread(target=thread_target)
    thread.start()
    return thread


def extract_form_fields(data: dict) -> list:
    fields = []
    
    if 'personal_info' in data:
        pi = data['personal_info']
        fields.append({'section': 'Personal Info', 'key': 'name', 'label': 'Name', 'value': pi.get('name', '')})
        fields.append({'section': 'Personal Info', 'key': 'title', 'label': 'Title', 'value': pi.get('title', '')})
        fields.append({'section': 'Personal Info', 'key': 'phone', 'label': 'Phone', 'value': pi.get('phone', '')})
        fields.append({'section': 'Personal Info', 'key': 'email', 'label': 'Email', 'value': pi.get('email', '')})
    
    fields.append({'section': 'Summary', 'key': 'summary', 'label': 'Summary', 'value': data.get('summary', '')})
    
    for i, exp in enumerate(data.get('work_experience', [])):
        fields.append({'section': 'Work Experience', 'key': f'exp_{i}_role', 'label': f'Role (Job {i+1})', 'value': exp.get('role', '')})
        fields.append({'section': 'Work Experience', 'key': f'exp_{i}_company', 'label': f'Company (Job {i+1})', 'value': exp.get('company', '')})
        fields.append({'section': 'Work Experience', 'key': f'exp_{i}_description', 'label': f'Description (Job {i+1})', 'value': exp.get('description', '')})
        fields.append({'section': 'Work Experience', 'key': f'exp_{i}_period', 'label': f'Period (Job {i+1})', 'value': exp.get('period', '')})
    
    for i, proj in enumerate(data.get('projects', [])):
        fields.append({'section': 'Projects', 'key': f'proj_{i}_title', 'label': f'Title (Project {i+1})', 'value': proj.get('title', '')})
        fields.append({'section': 'Projects', 'key': f'proj_{i}_description', 'label': f'Description (Project {i+1})', 'value': proj.get('description', '')})
        fields.append({'section': 'Projects', 'key': f'proj_{i}_period', 'label': f'Period (Project {i+1})', 'value': proj.get('period', '')})
    
    for i, edu in enumerate(data.get('education', [])):
        fields.append({'section': 'Education', 'key': f'edu_{i}_degree', 'label': f'Degree (Education {i+1})', 'value': edu.get('degree', '')})
        fields.append({'section': 'Education', 'key': f'edu_{i}_institution', 'label': f'Institution (Education {i+1})', 'value': edu.get('institution', '')})
        fields.append({'section': 'Education', 'key': f'edu_{i}_period', 'label': f'Period (Education {i+1})', 'value': edu.get('period', '')})
    
    fields.append({'section': 'Certifications', 'key': 'certifications', 'label': 'Certifications', 'value': '\n'.join(data.get('certifications', []))})
    fields.append({'section': 'Courses', 'key': 'courses', 'label': 'Courses', 'value': '\n'.join(data.get('courses', []))})
    
    return fields


def rebuild_data_from_fields(fields: list) -> dict:
    data = {}
    
    for field in fields:
        section = field.get('section', '')
        key = field.get('key', '')
        value = field.get('value', '')
        
        if section == 'Personal Info':
            if 'personal_info' not in data:
                data['personal_info'] = {}
            
            if key == 'name':
                data['personal_info']['name'] = value
            elif key == 'title':
                data['personal_info']['title'] = value
            elif key == 'phone':
                data['personal_info']['phone'] = value
            elif key == 'email':
                data['personal_info']['email'] = value
        
        elif key == 'summary':
            data['summary'] = value
        
        elif key.startswith('exp_'):
            if 'work_experience' not in data:
                data['work_experience'] = []
            
            parts = key.split('_')
            idx = int(parts[1])
            
            while len(data['work_experience']) <= idx:
                data['work_experience'].append({})
            
            if 'role' in key:
                data['work_experience'][idx]['role'] = value
            elif 'company' in key:
                data['work_experience'][idx]['company'] = value
            elif 'description' in key:
                data['work_experience'][idx]['description'] = value
            elif 'period' in key:
                data['work_experience'][idx]['period'] = value
        
        elif key.startswith('proj_'):
            if 'projects' not in data:
                data['projects'] = []
            
            parts = key.split('_')
            idx = int(parts[1])
            
            while len(data['projects']) <= idx:
                data['projects'].append({})
            
            if 'title' in key:
                data['projects'][idx]['title'] = value
            elif 'description' in key:
                data['projects'][idx]['description'] = value
            elif 'period' in key:
                data['projects'][idx]['period'] = value
        
        elif key.startswith('edu_'):
            if 'education' not in data:
                data['education'] = []
            
            parts = key.split('_')
            idx = int(parts[1])
            
            while len(data['education']) <= idx:
                data['education'].append({})
            
            if 'degree' in key:
                data['education'][idx]['degree'] = value
            elif 'institution' in key:
                data['education'][idx]['institution'] = value
            elif 'period' in key:
                data['education'][idx]['period'] = value
        
        elif key == 'certifications':
            data['certifications'] = [c.strip() for c in value.split('\n') if c.strip()]
        
        elif key == 'courses':
            data['courses'] = [c.strip() for c in value.split('\n') if c.strip()]
    
    return data


class FormWindow(ctk.CTkToplevel):
    def __init__(self, title: str, fields: list, ollama_models: list, default_model: str, 
                 default_name_size: str, default_body_size: str, is_translated: bool = False):
        super().__init__()
        
        self.title(title)
        self.geometry("900x700")
        self.fields = fields
        self.ollama_models = ollama_models
        self.is_translated = is_translated
        
        self.result = None
        self.selected_model = default_model
        self.selected_name_size = default_name_size
        self.selected_body_size = default_body_size
        
        self.field_widgets = {}
        
        main_frame = ctk.CTkScrollableFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        settings_frame = ctk.CTkFrame(main_frame)
        settings_frame.pack(fill="x", pady=(0, 10))
        
        ctk.CTkLabel(settings_frame, text="Modelo Ollama:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.model_combo = ctk.CTkComboBox(settings_frame, values=ollama_models, state="readonly")
        self.model_combo.set(default_model)
        self.model_combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ctk.CTkLabel(settings_frame, text="Tamaño nombre:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.name_size_combo = ctk.CTkComboBox(settings_frame, values=NAME_SIZE_OPTIONS, state="readonly")
        self.name_size_combo.set(default_name_size)
        self.name_size_combo.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        
        ctk.CTkLabel(settings_frame, text="Tamaño body:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.body_size_combo = ctk.CTkComboBox(settings_frame, values=BODY_SIZE_OPTIONS, state="readonly")
        self.body_size_combo.set(default_body_size)
        self.body_size_combo.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        self.fields_frame = ctk.CTkFrame(main_frame)
        self.fields_frame.pack(fill="both", expand=True)
        
        current_section = ""
        row = 0
        
        for field in fields:
            section = field.get('section', '')
            
            if section != current_section:
                ctk.CTkLabel(self.fields_frame, text=section, font=ctk.CTkFont(weight="bold", size=14)).grid(
                    row=row, column=0, columnspan=2, padx=5, pady=(10, 5), sticky="w")
                row += 1
                current_section = section
            
            label = field.get('label', '')
            value = field.get('value', '')
            
            ctk.CTkLabel(self.fields_frame, text=label, font=ctk.CTkFont(size=11)).grid(
                row=row, column=0, padx=5, pady=3, sticky="nw")
            
            is_large_field = 'description' in label.lower() or 'summary' in label.lower()
            is_medium_field = 'degree' in label.lower() or 'role' in label.lower() or 'title' in label.lower()
            text_height = 150 if is_large_field else (80 if is_medium_field else 50)
            text_box = ctk.CTkTextbox(self.fields_frame, height=text_height,
                                   wrap="word" if is_large_field or is_medium_field else None)
            text_box.insert("1.0", value)
            text_box.grid(row=row, column=1, padx=5, pady=3, sticky="ew")
            
            self.field_widgets[field['key']] = text_box
            row += 1
        
        self.fields_frame.columnconfigure(1, weight=1)
        
        button_frame = ctk.CTkFrame(main_frame)
        button_frame.pack(fill="x", pady=10)
        
        ctk.CTkButton(button_frame, text="Cancelar", command=self.cancel, fg_color="gray").pack(side="left", padx=5)
        ctk.CTkButton(button_frame, text="Continuar", command=self.submit).pack(side="right", padx=5)
        
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        
        self.grab_set()
        self.focus_set()
    
    def submit(self):
        self.selected_model = self.model_combo.get()
        self.selected_name_size = self.name_size_combo.get()
        self.selected_body_size = self.body_size_combo.get()
        
        for key, widget in self.field_widgets.items():
            value = widget.get("1.0", "end").strip()
            for field in self.fields:
                if field['key'] == key:
                    field['value'] = value
                    break
        
        self.result = {
            'model': self.selected_model,
            'name_size': self.selected_name_size,
            'body_size': self.selected_body_size,
            'fields': self.fields
        }
        
        self.destroy()
    
    def cancel(self):
        self.result = None
        self.destroy()


class ProgressWindow(ctk.CTkToplevel):
    def __init__(self, title: str):
        super().__init__()
        
        self.title(title)
        self.geometry("500x300")
        self.grab_set()
        
        self.log_text = ctk.CTkTextbox(self, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.close_button = ctk.CTkButton(self, text="Cerrar", command=self.destroy, state="disabled")
        self.close_button.pack(pady=10)
    
    def append_log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
    
    def enable_close(self):
        self.close_button.configure(state="normal")


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Resume PDF Builder")
        self.geometry("600x500")
        
        self.ollama_models = get_ollama_models()
        
        title_label = ctk.CTkLabel(self, text="Generador de CV PDF", font=ctk.CTkFont(weight="bold", size=24))
        title_label.pack(pady=20)
        
        options_frame = ctk.CTkFrame(self)
        options_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        opt1_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        opt1_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(opt1_frame, text="Opción 1: Sin traducción", font=ctk.CTkFont(weight="bold", size=14)).pack(anchor="w")
        ctk.CTkLabel(opt1_frame, text="Genera resume.pdf usando el YAML actual sin traducir", text_color="gray").pack(anchor="w")
        
        ctk.CTkButton(opt1_frame, text="Ejecutar Opción 1", command=self.run_option_1).pack(pady=5)
        
        separator = ctk.CTkFrame(options_frame, height=2, fg_color="gray")
        separator.pack(fill="x", padx=10, pady=10)
        
        opt2_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        opt2_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(opt2_frame, text="Opción 2: Con traducción", font=ctk.CTkFont(weight="bold", size=14)).pack(anchor="w")
        ctk.CTkLabel(opt2_frame, text="Traduce el CV usando Ollama, permite editar el YAML, genera resume_es.pdf y resume_en.pdf", text_color="gray").pack(anchor="w")
        
        ctk.CTkButton(opt2_frame, text="Ejecutar Opción 2", command=self.run_option_2).pack(pady=5)
        
        separator2 = ctk.CTkFrame(options_frame, height=2, fg_color="gray")
        separator2.pack(fill="x", padx=10, pady=10)
        
        opt3_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        opt3_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(opt3_frame, text="Opción 3: Editar documento traducido", font=ctk.CTkFont(weight="bold", size=14)).pack(anchor="w")
        ctk.CTkLabel(opt3_frame, text="Edita el YAML previamente traducido (usa resume-translated.yaml), NO usa Ollama, regenera PDFs", text_color="gray").pack(anchor="w")
        
        ctk.CTkButton(opt3_frame, text="Ejecutar Opción 3", command=self.run_option_3).pack(pady=5)
        
        info_label = ctk.CTkLabel(self, text="Modelos Ollama disponibles: " + ", ".join(self.ollama_models), 
                                  text_color="gray", font=ctk.CTkFont(size=10))
        info_label.pack(pady=10)
    
    def run_option_1(self):
        data = load_yaml_data(CV_FILE)
        if not data:
            return
        
        progress = ProgressWindow("Generando PDF - Opción 1")
        progress.append_log("Iniciando generación...")
        
        def on_complete(output: str, error: bool):
            progress.append_log(output)
            if error:
                messagebox.showerror("Error", output)
            else:
                messagebox.showinfo("Éxito", "PDF generado correctamente")
            progress.enable_close()
        
        thread = run_setup_and_build(
            model=DEFAULT_MODEL,
            name_size=DEFAULT_NAME_SIZE,
            body_size=DEFAULT_BODY_SIZE,
            yaml_file=CV_FILE,
            lang='es',
            no_translate=True,
            callback=on_complete,
            stream_callback=progress.append_log
        )
        
        def check_thread():
            if thread.is_alive():
                self.after(100, check_thread)
            else:
                progress.append_log("Completado")
        
        check_thread()
    
    def run_option_2(self):
        data = load_yaml_data(CV_FILE)
        if not data:
            return
        
        fields = extract_form_fields(data)
        
        form = FormWindow(
            title="Editar CV - Opción 2",
            fields=fields,
            ollama_models=self.ollama_models,
            default_model=DEFAULT_MODEL,
            default_name_size=DEFAULT_NAME_SIZE,
            default_body_size=DEFAULT_BODY_SIZE,
            is_translated=False
        )
        
        self.wait_window(form)
        
        if form.result is None:
            return
        
        progress = ProgressWindow("Generando PDF - Opción 2")
        progress.append_log("Iniciando generación con traducción...")
        
        modified_data = rebuild_data_from_fields(form.result['fields'])
        
        temp_yaml = BASE_DIR / "resume_temp.yaml"
        save_yaml_data(modified_data, temp_yaml)
        
        def on_complete(output: str, error: bool):
            progress.append_log(output)
            
            if not error:
                save_yaml_data(modified_data, TRANSLATED_FILE)
                progress.append_log(f"Traducción guardada en {TRANSLATED_FILE}")
            
            if temp_yaml.exists():
                temp_yaml.unlink()
            
            if error:
                messagebox.showerror("Error", output)
            else:
                messagebox.showinfo("Éxito", "PDFs generados correctamente")
            
            progress.enable_close()
        
        thread = run_setup_and_build(
            model=form.result['model'],
            name_size=form.result['name_size'],
            body_size=form.result['body_size'],
            yaml_file=CV_FILE,
            lang='both',
            no_translate=False,
            callback=on_complete,
            stream_callback=progress.append_log
        )
        
        def check_thread():
            if thread.is_alive():
                self.after(100, check_thread)
            else:
                progress.append_log("Completado")
        
        check_thread()
    
    def run_option_3(self):
        if not TRANSLATED_FILE.exists():
            messagebox.showwarning("Advertencia", 
                "No se encuentra resume-translated.yaml.\nEjecuta primero la Opción 2 para generar la traducción.")
            return
        
        data = load_yaml_data(TRANSLATED_FILE)
        if not data:
            return
        
        fields = extract_form_fields(data)
        
        form = FormWindow(
            title="Editar CV Traducido - Opción 3",
            fields=fields,
            ollama_models=self.ollama_models,
            default_model=DEFAULT_MODEL,
            default_name_size=DEFAULT_NAME_SIZE,
            default_body_size=DEFAULT_BODY_SIZE,
            is_translated=True
        )
        
        self.wait_window(form)
        
        if form.result is None:
            return
        
        progress = ProgressWindow("Generando PDF - Opción 3")
        progress.append_log("Iniciando generación desde traducción existente...")
        
        modified_data = rebuild_data_from_fields(form.result['fields'])
        
        temp_translated = BASE_DIR / "resume_translated_temp.yaml"
        save_yaml_data(modified_data, temp_translated)
        
        def on_complete(output: str, error: bool):
            progress.append_log(output)
            
            if not error:
                save_yaml_data(modified_data, TRANSLATED_FILE)
                messagebox.showinfo("Éxito", "PDFs regenerados correctamente")
            else:
                messagebox.showerror("Error", output)
            
            if temp_translated.exists():
                temp_translated.unlink()
            
            progress.enable_close()
        
        thread = run_setup_and_build(
            model=form.result['model'],
            name_size=form.result['name_size'],
            body_size=form.result['body_size'],
            yaml_file=temp_translated,
            lang='es',
            no_translate=True,
            callback=on_complete,
            stream_callback=progress.append_log
        )
        
        def check_thread():
            if thread.is_alive():
                self.after(100, check_thread)
            else:
                progress.append_log("Completado")
        
        check_thread()


if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()