import os
import re
import logging
from fastapi import UploadFile

logger = logging.getLogger("FileManager")

# Carpeta base para guardar los archivos (backup local)
BASE_LEGAJOS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legajos"))

# Cargar variables de entorno de forma segura
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
except Exception:
    pass

# Flag para decidir dónde guardar
SAVE_LOCAL_BACKUP = os.getenv("SAVE_LOCAL_BACKUP", "True").lower() == "true"


def _get_drive_service():
    """Obtiene el servicio de Drive de forma lazy (solo cuando se necesita)."""
    try:
        from app.services.drive_service import drive_service
        return drive_service
    except Exception as e:
        logger.warning(f"No se pudo cargar el servicio de Drive: {e}")
        return None


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


def _save_local(carrera: str, dni: str, tipo_documento: str, file: UploadFile) -> str:
    """Guarda archivo en disco local (función original)."""
    carrera_slug = slugify(carrera)
    
    # Crear directorio del legajo
    user_dir = os.path.join(BASE_LEGAJOS_DIR, carrera_slug, str(dni))
    os.makedirs(user_dir, exist_ok=True)
    
    # Obtener extensión original
    filename = file.filename
    _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".jpg"
        
    # Nombre final del archivo
    new_filename = f"{tipo_documento}{ext.lower()}"
    file_path = os.path.join(user_dir, new_filename)
    
    # Guardar archivo en disco
    with open(file_path, "wb") as buffer:
        file.file.seek(0)
        buffer.write(file.file.read())
        
    # Retornar ruta relativa
    relative_path = os.path.relpath(file_path, os.path.abspath(os.path.join(BASE_LEGAJOS_DIR, "..")))
    return relative_path.replace("\\", "/")


def _save_local_bytes(carrera: str, dni: str, tipo_documento: str, file_bytes: bytes, ext: str = ".jpg") -> str:
    """Guarda bytes en disco local."""
    carrera_slug = slugify(carrera)
    user_dir = os.path.join(BASE_LEGAJOS_DIR, carrera_slug, str(dni))
    os.makedirs(user_dir, exist_ok=True)
    
    new_filename = f"{tipo_documento}{ext.lower()}"
    file_path = os.path.join(user_dir, new_filename)
    
    with open(file_path, "wb") as buffer:
        buffer.write(file_bytes)
    
    relative_path = os.path.relpath(file_path, os.path.abspath(os.path.join(BASE_LEGAJOS_DIR, "..")))
    return relative_path.replace("\\", "/")


def save_document_file(carrera: str, dni: str, tipo_documento: str, file: UploadFile) -> str:
    """
    Guarda un documento cargado.
    - Si Google Drive está configurado: sube a Drive y retorna la URL de Drive
    - Si no: guarda en disco local y retorna la ruta relativa
    """
    drive = _get_drive_service()
    
    if drive and drive.is_available():
        try:
            result = drive.upload_file(file, carrera, dni, tipo_documento)
            # Guardar backup local si está habilitado
            if SAVE_LOCAL_BACKUP:
                try:
                    _save_local(carrera, dni, tipo_documento, file)
                except Exception as e:
                    logger.warning(f"Error al guardar backup local: {e}")
            return result["drive_url"]
        except Exception as e:
            logger.error(f"Error al subir a Drive, guardando localmente: {e}")
            # Fallback a disco local
    
    # Guardar en disco local
    return _save_local(carrera, dni, tipo_documento, file)


def save_composite_documents(carrera: str, dni: str, documents: list[dict], original_file: UploadFile = None) -> dict:
    """
    Guarda los documentos extraídos de un archivo compuesto.
    Retorna: {"dni_frente": "url_or_path", "dni_dorso": "url_or_path", "foto_4x4": "url_or_path", ...}
    """
    carrera_slug = slugify(carrera)
    saved_paths = {}
    
    # Mapear tipos del sistema de clasificación a tipos de legajo
    type_mapping = {
        "dni_frente": "dni_frente",
        "dni_dorso": "dni_dorso",
        "foto_perfil": "foto_4x4",
    }
    
    drive = _get_drive_service()
    
    for doc in documents:
        doc_type = doc.get("type", "")
        image_path = doc.get("image_path", "")
        
        if doc_type in type_mapping and image_path and os.path.exists(image_path):
            legajo_type = type_mapping[doc_type]
            
            # Determinar extensión del archivo
            _, ext = os.path.splitext(image_path)
            if not ext:
                ext = ".jpg"
            
            if drive and drive.is_available():
                try:
                    # Leer bytes del archivo temporal
                    with open(image_path, "rb") as f:
                        file_bytes = f.read()
                    
                    # Crear un UploadFile mock para Drive
                    class MockFile:
                        def __init__(self, bytes_data, filename):
                            self.file = io.BytesIO(bytes_data)
                            self.filename = filename
                            self.content_type = "image/jpeg"
                        
                        def read(self):
                            return self.file.read()
                    
                    mock = MockFile(file_bytes, f"{legajo_type}{ext}")
                    result = drive.upload_file(mock, carrera, dni, legajo_type)
                    saved_paths[legajo_type] = result["drive_url"]
                    
                    # Backup local
                    if SAVE_LOCAL_BACKUP:
                        try:
                            _save_local_bytes(carrera, dni, legajo_type, file_bytes, ext)
                        except Exception:
                            pass
                    continue
                except Exception as e:
                    logger.error(f"Error al subir compuesto a Drive: {e}")
            
            # Fallback: guardar localmente
            user_dir = os.path.join(BASE_LEGAJOS_DIR, carrera_slug, str(dni))
            os.makedirs(user_dir, exist_ok=True)
            
            new_filename = f"{legajo_type}{ext.lower()}"
            file_path = os.path.join(user_dir, new_filename)
            
            import shutil
            shutil.copy2(image_path, file_path)
            
            relative_path = os.path.relpath(file_path, os.path.abspath(os.path.join(BASE_LEGAJOS_DIR, "..")))
            saved_paths[legajo_type] = relative_path.replace("\\", "/")
    
    # Guardar archivo original si se proporcionó
    if original_file:
        _, ext = os.path.splitext(original_file.filename)
        if not ext:
            ext = ".jpg"
        
        if drive and drive.is_available():
            try:
                result = drive.upload_file(original_file, carrera, dni, "original_compuesto")
                saved_paths["original"] = result["drive_url"]
            except Exception as e:
                logger.error(f"Error al subir original compuesto a Drive: {e}")
        else:
            original_filename = f"original_compuesto{ext.lower()}"
            user_dir = os.path.join(BASE_LEGAJOS_DIR, carrera_slug, str(dni))
            os.makedirs(user_dir, exist_ok=True)
            original_path = os.path.join(user_dir, original_filename)
            
            original_file.file.seek(0)
            with open(original_path, "wb") as buffer:
                buffer.write(original_file.file.read())
            
            relative_path = os.path.relpath(original_path, os.path.abspath(os.path.join(BASE_LEGAJOS_DIR, "..")))
            saved_paths["original"] = relative_path.replace("\\", "/")
    
    return saved_paths


def save_bytes_to_legajo(carrera: str, dni: str, tipo_documento: str, file_bytes: bytes, ext: str = ".jpg") -> str:
    """
    Guarda bytes directamente en legajos.
    """
    drive = _get_drive_service()
    
    if drive and drive.is_available():
        try:
            import io
            
            class MockFile:
                def __init__(self, bytes_data, filename):
                    self.file = io.BytesIO(bytes_data)
                    self.filename = filename
                    self.content_type = "application/octet-stream"
                
                def read(self):
                    return self.file.read()
            
            mock = MockFile(file_bytes, f"{tipo_documento}{ext}")
            result = drive.upload_file(mock, carrera, dni, tipo_documento)
            
            if SAVE_LOCAL_BACKUP:
                try:
                    _save_local_bytes(carrera, dni, tipo_documento, file_bytes, ext)
                except Exception:
                    pass
            
            return result["drive_url"]
        except Exception as e:
            logger.error(f"Error al subir bytes a Drive: {e}")
    
    # Fallback: guardar localmente
    return _save_local_bytes(carrera, dni, tipo_documento, file_bytes, ext)
