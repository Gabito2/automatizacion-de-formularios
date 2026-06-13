import os
import re
from fastapi import UploadFile

# Carpeta base para guardar los archivos
BASE_LEGAJOS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legajos"))

def slugify(text: str) -> str:
    """Convierte un texto (ej: nombre de carrera) a un formato apto para carpetas."""
    if not text:
        return "sin_carrera"
    text = text.lower().strip()
    # Reemplazar acentos
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)
    # Reemplazar caracteres no alfanuméricos por guiones
    text = re.sub(r'[^a-z0-9_]', '_', text)
    # Evitar guiones bajos repetidos
    text = re.sub(r'_+', '_', text)
    return text.strip('_')

def save_document_file(carrera: str, dni: str, tipo_documento: str, file: UploadFile) -> str:
    """
    Guarda un documento cargado en la estructura de legajos institucional:
    legajos/{carrera_slug}/{dni}/{tipo_documento}.{extension}
    """
    carrera_slug = slugify(carrera)
    
    # Crear directorio del legajo
    user_dir = os.path.join(BASE_LEGAJOS_DIR, carrera_slug, str(dni))
    os.makedirs(user_dir, exist_ok=True)
    
    # Obtener extensión original
    filename = file.filename
    _, ext = os.path.splitext(filename)
    if not ext:
        # Fallback de extensión
        ext = ".jpg"
        
    # Nombre final del archivo
    new_filename = f"{tipo_documento}{ext.lower()}"
    file_path = os.path.join(user_dir, new_filename)
    
    # Guardar archivo en disco
    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())
        
    # Retornar ruta relativa desde el directorio backend/ para acceso estático o descarga
    relative_path = os.path.relpath(file_path, os.path.abspath(os.path.join(BASE_LEGAJOS_DIR, "..")))
    # Usar separadores de URL barra diagonal
    return relative_path.replace("\\", "/")
