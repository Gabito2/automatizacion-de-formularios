import os
import logging
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from fastapi import UploadFile
import io

logger = logging.getLogger("DriveService")

# Scopes necesarios para Google Drive API
SCOPES = ['https://www.googleapis.com/auth/drive']

class DriveService:
    _instance = None
    _service = None
    _root_folder_id = None
    _folder_cache = {}  # cache de carpetas creadas: {path: folder_id}

    @classmethod
    def get_instance(cls):
        """Singleton pattern para el servicio de Drive."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._load_config()

    def _load_config(self):
        """Carga la configuración desde variables de entorno."""
        self._root_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "19_J3nWnExucoA2pmdZk1KfJbxVPQ723f")
        credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        
        # Ruta absoluta al archivo de credenciales (relativo al backend/)
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self._credentials_path = os.path.join(backend_dir, credentials_file)
        
        # Intentar autenticar
        self._authenticate()

    def _authenticate(self):
        """Autentica con Google Drive usando Service Account."""
        try:
            if not os.path.exists(self._credentials_path):
                logger.warning(f"Archivo de credenciales no encontrado: {self._credentials_path}")
                logger.warning("Google Drive NO está configurado. Los archivos se guardarán solo en disco local.")
                self._service = None
                return

            creds = service_account.Credentials.from_service_account_file(
                self._credentials_path, 
                scopes=SCOPES
            )
            self._service = build('drive', 'v3', credentials=creds)
            logger.info("Google Drive autenticado correctamente.")
        except Exception as e:
            logger.error(f"Error al autenticar con Google Drive: {e}")
            self._service = None

    def is_available(self) -> bool:
        """Verifica si el servicio de Drive está disponible."""
        return self._service is not None

    def _get_or_create_folder(self, folder_name: str, parent_id: str) -> str:
        """
        Obtiene el ID de una carpeta existente o la crea si no existe.
        Usa cache para evitar queries repetidas.
        """
        cache_key = f"{parent_id}/{folder_name}"
        
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        try:
            # Buscar si la carpeta ya existe
            query = (
                f"name='{folder_name}' and "
                f"'{parent_id}' in parents and "
                f"mimeType='application/vnd.google-apps.folder' and "
                f"trashed=false"
            )
            results = self._service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()
            
            files = results.get('files', [])
            
            if files:
                folder_id = files[0]['id']
            else:
                # Crear la carpeta
                file_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [parent_id]
                }
                folder = self._service.files().create(
                    body=file_metadata,
                    fields='id'
                ).execute()
                folder_id = folder['id']
                logger.info(f"Carpeta creada en Drive: {folder_name} (ID: {folder_id})")

            self._folder_cache[cache_key] = folder_id
            return folder_id

        except Exception as e:
            logger.error(f"Error al buscar/crear carpeta '{folder_name}': {e}")
            raise

    def create_student_folder(self, carrera: str, dni: str) -> str:
        """
        Crea la estructura de carpetas: Carrera/DNI/
        Retorna el ID de la carpeta del estudiante.
        """
        if not self.is_available():
            raise Exception("Google Drive no está configurado")

        # Crear carpeta de carrera
        carrera_folder_id = self._get_or_create_folder(carrera, self._root_folder_id)
        
        # Crear carpeta del estudiante (DNI)
        student_folder_id = self._get_or_create_folder(dni, carrera_folder_id)
        
        return student_folder_id

    def upload_file(
        self, 
        file: UploadFile, 
        carrera: str, 
        dni: str, 
        tipo_documento: str,
        file_bytes: bytes = None
    ) -> dict:
        """
        Sube un archivo a Google Drive en la estructura: Carrera/DNI/tipo_documento.ext
        
        Retorna: {
            "drive_file_id": str,
            "drive_url": str,  # URL de visualización
            "download_url": str,  # URL de descarga directa
            "path": str  # Ruta lógica en Drive
        }
        """
        if not self.is_available():
            raise Exception("Google Drive no está configurado")

        # Crear estructura de carpetas
        student_folder_id = self.create_student_folder(carrera, dni)

        # Determinar nombre del archivo
        filename = file.filename
        _, ext = os.path.splitext(filename)
        if not ext:
            ext = ".jpg"
        new_filename = f"{tipo_documento}{ext.lower()}"

        # Preparar el contenido del archivo
        if file_bytes:
            media = MediaIoBaseUpload(
                io.BytesIO(file_bytes),
                mimetype=file.content_type or 'application/octet-stream',
                resumable=True
            )
        else:
            file.file.seek(0)
            media = MediaFileUpload(
                file.file,
                mimetype=file.content_type or 'application/octet-stream',
                resumable=True
            )

        # Subir archivo
        file_metadata = {
            'name': new_filename,
            'parents': [student_folder_id]
        }

        uploaded_file = self._service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink, webContentLink'
        ).execute()

        drive_file_id = uploaded_file['id']
        
        # Construir URLs
        drive_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
        download_url = f"https://drive.google.com/uc?export=download&id={drive_file_id}"
        
        # Ruta lógica
        logical_path = f"drive:{carrera}/{dni}/{new_filename}"

        logger.info(f"Archivo subido a Drive: {new_filename} (ID: {drive_file_id})")

        return {
            "drive_file_id": drive_file_id,
            "drive_url": drive_url,
            "download_url": download_url,
            "path": logical_path
        }

    def delete_file(self, drive_file_id: str) -> bool:
        """Elimina un archivo de Google Drive."""
        if not self.is_available():
            return False
        
        try:
            self._service.files().delete(fileId=drive_file_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error al eliminar archivo {drive_file_id}: {e}")
            return False

    def get_file_url(self, drive_file_id: str) -> str:
        """Obtiene la URL de visualización de un archivo."""
        return f"https://drive.google.com/file/d/{drive_file_id}/view"


# Instancia global del servicio
drive_service = DriveService.get_instance()
