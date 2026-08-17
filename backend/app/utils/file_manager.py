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
    
    # Guardar archivo en disco (rebobinar el stream para leer desde el inicio)
    with open(file_path, "wb") as buffer:
        file.file.seek(0)
        buffer.write(file.file.read())
        
    # Retornar ruta relativa desde el directorio backend/ para acceso estático o descarga
    relative_path = os.path.relpath(file_path, os.path.abspath(os.path.join(BASE_LEGAJOS_DIR, "..")))
    # Usar separadores de URL barra diagonal
    return relative_path.replace("\\", "/")


def save_composite_documents(carrera: str, dni: str, documents: list[dict], original_file: UploadFile = None) -> dict:
    """
    Guarda los documentos extraídos de un archivo compuesto en la estructura de legajos.
    
    documents: lista de dicts con {"type": "dni_frente"|"dni_dorso"|"foto_perfil", 
                                    "image_path": "ruta_temporal.png",
                                    "region": [x,y,w,h]}
    original_file: archivo original subido por el usuario (opcional, para guardarlo también)
    
    Retorna: {"dni_frente": "path/...", "dni_dorso": "path/...", "foto_4x4": "path/...", "original": "path/..."}
    """
    carrera_slug = slugify(carrera)
    user_dir = os.path.join(BASE_LEGAJOS_DIR, carrera_slug, str(dni))
    os.makedirs(user_dir, exist_ok=True)
    
    saved_paths = {}
    
    # Mapear tipos del sistema de clasificación a tipos de legajo
    type_mapping = {
        "dni_frente": "dni_frente",
        "dni_dorso": "dni_dorso",
        "foto_perfil": "foto_4x4",
    }
    
    for doc in documents:
        doc_type = doc.get("type", "")
        image_path = doc.get("image_path", "")
        
        if doc_type in type_mapping and image_path and os.path.exists(image_path):
            legajo_type = type_mapping[doc_type]
            
            # Determinar extensión del archivo
            _, ext = os.path.splitext(image_path)
            if not ext:
                ext = ".jpg"
            
            new_filename = f"{legajo_type}{ext.lower()}"
            file_path = os.path.join(user_dir, new_filename)
            
            # Copiar archivo desde la ruta temporal
            import shutil
            shutil.copy2(image_path, file_path)
            
            relative_path = os.path.relpath(file_path, os.path.abspath(os.path.join(BASE_LEGAJOS_DIR, "..")))
            saved_paths[legajo_type] = relative_path.replace("\\", "/")
    
    # Guardar archivo original si se proporcionó
    if original_file:
        _, ext = os.path.splitext(original_file.filename)
        if not ext:
            ext = ".jpg"
        original_filename = f"original_compuesto{ext.lower()}"
        original_path = os.path.join(user_dir, original_filename)
        
        original_file.file.seek(0)
        with open(original_path, "wb") as buffer:
            buffer.write(original_file.file.read())
        
        relative_path = os.path.relpath(original_path, os.path.abspath(os.path.join(BASE_LEGAJOS_DIR, "..")))
        saved_paths["original"] = relative_path.replace("\\", "/")
    
    return saved_paths


def save_bytes_to_legajo(carrera: str, dni: str, tipo_documento: str, file_bytes: bytes, ext: str = ".jpg") -> str:
    """
    Guarda bytes directamente en la estructura de legajos.
    Útil para guardar imágenes procesadas desde memoria.
    """
    carrera_slug = slugify(carrera)
    user_dir = os.path.join(BASE_LEGAJOS_DIR, carrera_slug, str(dni))
    os.makedirs(user_dir, exist_ok=True)
    
    new_filename = f"{tipo_documento}{ext.lower()}"
    file_path = os.path.join(user_dir, new_filename)
    
    with open(file_path, "wb") as buffer:
        buffer.write(file_bytes)
    
    relative_path = os.path.relpath(file_path, os.path.abspath(os.path.join(BASE_LEGAJOS_DIR, "..")))
    return relative_path.replace("\\", "/")
