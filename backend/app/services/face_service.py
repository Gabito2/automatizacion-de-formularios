import os
import cv2
import logging

logger = logging.getLogger("FaceService")

# Ruta del modelo de MediaPipe Tasks. En versiones recientes (0.10.x) la API
# legacy `mediapipe.solutions` fue removida y se usa `mediapipe.tasks` con un
# modelo .tflite descargado.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MP_FACE_MODEL = os.getenv(
    "MP_FACE_MODEL",
    os.path.join(BASE_DIR, "models", "blaze_face_short_range.tflite"),
)

# Intentar importar MediaPipe Tasks (API nueva)
try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_tasks_python
    from mediapipe.tasks.python import vision as mp_vision

    MEDIAPIPE_AVAILABLE = os.path.exists(MP_FACE_MODEL)
    if MEDIAPIPE_AVAILABLE:
        logger.info("MediaPipe Tasks disponible como detector facial primario.")
    else:
        logger.warning(
            f"Modelo de MediaPipe no encontrado en: {MP_FACE_MODEL}. Se usará Haar Cascades como detector facial."
        )
except ImportError:
    mp = None
    mp_tasks_python = None
    mp_vision = None
    MEDIAPIPE_AVAILABLE = False
    logger.warning("MediaPipe no disponible. Se usará Haar Cascades como detector facial.")

_mp_face_detector = None


def _get_mp_face_detector():
    """Crea (una sola vez) el detector facial de MediaPipe Tasks."""
    global _mp_face_detector
    if _mp_face_detector is None:
        base_options = mp_tasks_python.BaseOptions(model_asset_path=MP_FACE_MODEL)
        options = mp_vision.FaceDetectorOptions(
            base_options=base_options,
            min_detection_confidence=0.4,
        )
        _mp_face_detector = mp_vision.FaceDetector.create_from_options(options)
        logger.info("MediaPipe FaceDetector listo.")
    return _mp_face_detector


class FaceService:
    @staticmethod
    def detect_face(image_path: str) -> dict:
        """
        Detecta rostros en una imagen usando MediaPipe Tasks (API nueva) como
        detector primario y Haar Cascades de OpenCV como fallback.

        Retorna un diccionario con:
        - has_face (bool): Si se detectó al menos un rostro
        - face_count (int): Cantidad de rostros detectados
        - confidence (float): Score de confianza del detector (0.0–1.0)
        - method_used (str): "mediapipe" | "haar_cascade" | "none"
        - error (str | None): Descripción del error si ocurrió
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                logger.error(f"No se pudo cargar la imagen desde la ruta: {image_path}")
                return {
                    "has_face": False,
                    "face_count": 0,
                    "confidence": 0.0,
                    "method_used": "none",
                    "error": "No se pudo leer el archivo de imagen."
                }

            # ── DETECTOR PRIMARIO: MediaPipe Tasks ───────────────────────────
            if MEDIAPIPE_AVAILABLE:
                try:
                    detector = _get_mp_face_detector()
                    # MediaPipe requiere RGB
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
                    results = detector.detect(mp_image)

                    if results.detections:
                        face_count = len(results.detections)
                        best_confidence = max(
                            d.categories[0].score for d in results.detections
                        )
                        logger.info(
                            f"[MediaPipe] Rostros detectados: {face_count}, "
                            f"confianza máx: {best_confidence:.2f}"
                        )
                        return {
                            "has_face": True,
                            "face_count": face_count,
                            "confidence": float(best_confidence),
                            "method_used": "mediapipe",
                            "error": None
                        }
                    logger.info("[MediaPipe] No se detectaron rostros.")
                    # MediaPipe no detectó → intentar con Haar como confirmación
                except Exception as mp_err:
                    logger.warning(f"[MediaPipe] Error durante detección: {mp_err}. Usando Haar Cascades.")

            # ── FALLBACK: OpenCV Haar Cascades ───────────────────────────────
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")

            if not os.path.exists(cascade_path):
                logger.error(f"Haar Cascade no encontrado en: {cascade_path}")
                return {
                    "has_face": False,
                    "face_count": 0,
                    "confidence": 0.0,
                    "method_used": "none",
                    "error": "Clasificador facial no disponible en el servidor."
                }

            face_cascade = cv2.CascadeClassifier(cascade_path)
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.05,     # más fino para detectar más caras
                minNeighbors=3,       # menos estricto (menos falsos negativos)
                minSize=(40, 40)
            )

            face_count = len(faces)
            logger.info(f"[Haar] Rostros detectados: {face_count}")

            # Haar Cascades no da score; asignamos 0.6 si detecta (confianza media)
            confidence = 0.6 if face_count > 0 else 0.0

            return {
                "has_face": face_count > 0,
                "face_count": face_count,
                "confidence": confidence,
                "method_used": "haar_cascade",
                "error": None
            }

        except Exception as e:
            logger.error(f"Excepción en detección facial: {str(e)}")
            return {
                "has_face": False,
                "face_count": 0,
                "confidence": 0.0,
                "method_used": "none",
                "error": str(e)
            }