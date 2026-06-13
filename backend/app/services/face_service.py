import os
import cv2
import logging

logger = logging.getLogger("FaceService")

class FaceService:
    @staticmethod
    def detect_face(image_path: str) -> dict:
        """
        Detecta rostros en una imagen en la ruta dada utilizando Haar Cascades de OpenCV.
        Retorna un diccionario con los resultados del análisis.
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                logger.error(f"No se pudo cargar la imagen desde la ruta: {image_path}")
                return {"has_face": False, "face_count": 0, "error": "No se pudo leer el archivo de imagen."}
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
            if not os.path.exists(cascade_path):
                logger.error(f"Archivo Haar Cascade no encontrado en: {cascade_path}")
                return {"has_face": False, "face_count": 0, "error": "Clasificador facial no disponible en el servidor."}
                
            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(30, 30)
            )
            
            face_count = len(faces)
            logger.info(f"Detección facial finalizada. Se encontraron {face_count} rostros en la imagen.")
            
            return {
                "has_face": face_count > 0,
                "face_count": face_count,
                "error": None
            }
        except Exception as e:
            logger.error(f"Excepción en detección facial: {str(e)}")
            return {
                "has_face": False,
                "face_count": 0,
                "error": str(e)
            }
