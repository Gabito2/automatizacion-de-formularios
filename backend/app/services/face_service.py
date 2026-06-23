import os
import cv2
import logging

logger = logging.getLogger("FaceService")

# Intentar importar MediaPipe (disponible via pip install mediapipe)
try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
    logger.info("MediaPipe cargado correctamente como detector facial primario.")
except ImportError:
    MEDIAPIPE_AVAILABLE = False
    logger.warning("MediaPipe no disponible. Se usará Haar Cascades como detector facial.")


class FaceService:
    @staticmethod
    def detect_face(image_path: str) -> dict:
        """
        Detecta rostros en una imagen usando MediaPipe como detector primario
        y Haar Cascades de OpenCV como fallback.

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

            # ── DETECTOR PRIMARIO: MediaPipe Face Detection ──────────────────
            if MEDIAPIPE_AVAILABLE:
                try:
                    mp_face = mp.solutions.face_detection
                    with mp_face.FaceDetection(
                        model_selection=1,       # 1 = modelo para rango completo (hasta ~5m)
                        min_detection_confidence=0.4
                    ) as detector:
                        # MediaPipe requiere RGB
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        results = detector.process(img_rgb)

                        if results.detections:
                            face_count = len(results.detections)
                            # Tomar el score de confianza del mejor detection
                            best_confidence = max(
                                d.score[0] for d in results.detections
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
                        else:
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
