import os
import re
import cv2
import numpy as np
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OCRService")

# ── MOTOR PRIMARIO: EasyOCR (instalable con pip, sin ejecutable externo) ──────
try:
    import easyocr
    _easyocr_reader = None  # Lazy initialization para evitar cargar modelos al importar

    def _get_easyocr_reader():
        global _easyocr_reader
        if _easyocr_reader is None:
            logger.info("Inicializando EasyOCR (primera carga de modelos, puede tardar unos segundos)...")
            _easyocr_reader = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
            logger.info("EasyOCR inicializado correctamente.")
        return _easyocr_reader

    EASYOCR_AVAILABLE = True
    logger.info("EasyOCR importado correctamente como motor OCR primario.")
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.warning("EasyOCR no disponible. Se intentará usar PyTesseract como fallback.")

# ── MOTOR SECUNDARIO: PyTesseract (requiere instalación manual del ejecutable) ──
try:
    import pytesseract
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if os.path.exists(TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        TESSERACT_AVAILABLE = True
        logger.info(f"PyTesseract configurado en: {TESSERACT_CMD}")
    else:
        # Verificar si está en el PATH del sistema
        try:
            pytesseract.get_tesseract_version()
            TESSERACT_AVAILABLE = True
            logger.info("PyTesseract encontrado en el PATH del sistema.")
        except Exception:
            TESSERACT_AVAILABLE = False
            logger.warning("Tesseract no encontrado. Solo se usará EasyOCR.")
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("PyTesseract no instalado.")


class OCRService:
    @staticmethod
    def preprocess_image(image_path: str):
        """
        Lee una imagen, aplica preprocesamiento con OpenCV para mejorar el OCR y
        retorna la imagen procesada lista para extracción de texto, junto con métricas
        de calidad de imagen.
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"No se pudo cargar la imagen desde la ruta: {image_path}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 1. Validaciones de calidad con OpenCV
        # A. Detección de borrosidad usando varianza de Laplace
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        is_blurry = laplacian_var < 80.0

        # B. Detección de brillo
        mean_brightness = np.mean(gray)
        is_too_dark = mean_brightness < 45.0
        is_too_bright = mean_brightness > 235.0

        # C. Densidad de bordes para verificar si el documento tiene contenido
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / (gray.shape[0] * gray.shape[1])
        is_incomplete = edge_density < 0.01

        # 2. Preprocesamiento para mejorar el OCR
        height, width = gray.shape
        if width < 1000:
            scale = 200
            new_w = int(width * scale / 100)
            new_h = int(height * scale / 100)
            gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        # Filtro bilateral para remover ruido preservando bordes
        filtered = cv2.bilateralFilter(gray, 9, 75, 75)

        # Umbralización adaptativa para separar texto del fondo
        thresh = cv2.adaptiveThreshold(
            filtered, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        quality_report = {
            "blur_score": float(laplacian_var),
            "brightness_score": float(mean_brightness),
            "edge_density": float(edge_density),
            "is_blurry": bool(is_blurry),
            "is_too_dark": bool(is_too_dark),
            "is_too_bright": bool(is_too_bright),
            "is_incomplete": bool(is_incomplete),
            "legible": not (is_blurry or is_too_dark or is_too_bright)
        }

        return thresh, quality_report

    @staticmethod
    def _extract_with_easyocr(image_path: str) -> str:
        """Extrae texto de una imagen usando EasyOCR."""
        reader = _get_easyocr_reader()
        # EasyOCR acepta ruta de archivo directamente
        results = reader.readtext(image_path, detail=0, paragraph=True)
        text = "\n".join(results)
        logger.info(f"[EasyOCR] Texto extraído ({len(text)} caracteres).")
        return text

    @staticmethod
    def _extract_with_tesseract(processed_img) -> str:
        """Extrae texto de una imagen preprocesada usando PyTesseract."""
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(processed_img, lang="spa", config=custom_config)
        logger.info(f"[Tesseract] Texto extraído ({len(text)} caracteres).")
        return text

    @staticmethod
    def extract_text(image_path: str, user_info: dict = None) -> tuple[str, dict]:
        """
        Extrae el texto de la imagen usando EasyOCR (primario) o Tesseract (fallback).

        Si ninguno está disponible, retorna texto vacío (ya no simula datos ficticios).

        Retorna:
        - extracted_text (str): Texto extraído (puede ser vacío si falla)
        - quality_report (dict): Métricas de calidad de imagen
        """
        try:
            processed_img, quality_report = OCRService.preprocess_image(image_path)
            extracted_text = ""

            # ── Intentar EasyOCR (primario) ───────────────────────────────────
            if EASYOCR_AVAILABLE:
                try:
                    extracted_text = OCRService._extract_with_easyocr(image_path)
                    quality_report["ocr_engine"] = "easyocr"
                except Exception as easy_err:
                    logger.warning(f"[EasyOCR] Error: {easy_err}. Intentando Tesseract...")

            # ── Intentar Tesseract (fallback) ─────────────────────────────────
            if not extracted_text and TESSERACT_AVAILABLE:
                try:
                    extracted_text = OCRService._extract_with_tesseract(processed_img)
                    quality_report["ocr_engine"] = "tesseract"
                except Exception as tess_err:
                    logger.warning(f"[Tesseract] Error: {tess_err}.")

            # ── Ningún motor disponible o ambos fallaron ──────────────────────
            if not extracted_text:
                logger.warning("Ningún motor OCR pudo extraer texto de la imagen.")
                quality_report["ocr_engine"] = "none"
                quality_report["ocr_error"] = "Ningún motor OCR disponible o la imagen no contiene texto legible."

            return extracted_text, quality_report

        except Exception as e:
            logger.error(f"Error procesando imagen para OCR: {str(e)}")
            return "", {
                "blur_score": 0.0,
                "brightness_score": 0.0,
                "edge_density": 0.0,
                "is_blurry": True,
                "is_too_dark": False,
                "is_too_bright": False,
                "is_incomplete": True,
                "legible": False,
                "ocr_engine": "none",
                "error": str(e)
            }

    @staticmethod
    def validate_dni_data(extracted_text: str, declared_data: dict) -> dict:
        """
        Compara el texto extraído del OCR con los datos declarados por el estudiante.
        Si el texto extraído está vacío, retorna overall_match: False.
        """
        # Si el texto está vacío, no podemos validar
        if not extracted_text or not extracted_text.strip():
            return {
                "dni_match": False,
                "name_match": False,
                "lastname_match": False,
                "dob_match": False,
                "overall_match": False,
                "text_empty": True
            }

        def normalize(text: str) -> str:
            if not text:
                return ""
            text = text.upper()
            replacements = {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N"}
            for orig, rep in replacements.items():
                text = text.replace(orig, rep)
            return re.sub(r'[^A-Z0-9\s]', '', text)

        norm_ocr = normalize(extracted_text)

        # 1. Validar DNI
        declared_dni = str(declared_data.get("dni") or "").strip()
        norm_ocr_clean = norm_ocr.replace(" ", "")
        dni_match = False
        if declared_dni:
            dni_match = declared_dni in norm_ocr_clean
            # También buscar con formato XX.XXX.XXX
            if not dni_match and len(declared_dni) == 8:
                dni_formated = f"{declared_dni[:2]}{declared_dni[2:5]}{declared_dni[5:]}"
                dni_match = dni_formated in norm_ocr_clean

        # 2. Validar Nombre y Apellido
        declared_name = str(declared_data.get("nombre") or "").strip()
        declared_lastname = str(declared_data.get("apellido") or "").strip()

        norm_name = normalize(declared_name)
        norm_lastname = normalize(declared_lastname)

        name_match = False
        lastname_match = False

        if norm_name:
            words = [w for w in norm_name.split() if len(w) > 2]
            name_match = any(word in norm_ocr for word in words) if words else norm_name in norm_ocr

        if norm_lastname:
            words = [w for w in norm_lastname.split() if len(w) > 2]
            lastname_match = any(word in norm_ocr for word in words) if words else norm_lastname in norm_ocr

        # 3. Validar Fecha de Nacimiento
        declared_dob = str(declared_data.get("fecha_nacimiento") or "").strip()
        dob_match = False

        if declared_dob:
            try:
                parts = declared_dob.split("-")
                if len(parts) == 3:
                    year, month, day = parts[0], parts[1], parts[2]
                    fmt1 = f"{day}{month}{year}"
                    fmt2 = f"{day}/{month}/{year}"
                    fmt3 = f"{day}-{month}-{year}"
                    fmt4 = f"{day}/{month}/{year[2:]}"
                    ocr_no_spaces = norm_ocr.replace(" ", "").replace("/", "").replace("-", "")
                    if (fmt1 in ocr_no_spaces or
                        fmt2.replace("/", "") in ocr_no_spaces or
                        fmt3.replace("-", "") in ocr_no_spaces or
                        fmt4.replace("/", "") in ocr_no_spaces):
                        dob_match = True
            except Exception:
                pass

        return {
            "dni_match": bool(dni_match),
            "name_match": bool(name_match),
            "lastname_match": bool(lastname_match),
            "dob_match": bool(dob_match),
            "overall_match": bool(dni_match and (name_match or lastname_match)),
            "text_empty": False
        }

    @staticmethod
    def parse_dni_text(extracted_text: str) -> dict:
        """
        Intenta parsear DNI, Apellido, Nombre y Fecha de Nacimiento
        a partir del texto extraído del DNI argentino.
        """
        if not extracted_text or not extracted_text.strip():
            return {"dni": "", "nombre": "", "apellido": "", "fecha_nacimiento": ""}

        lines = [line.strip() for line in extracted_text.split('\n') if line.strip()]

        # 1. Buscar DNI (7-8 dígitos, con o sin puntos)
        dni = ""
        dni_match = re.search(r'\b\d{1,2}\.?\d{3}\.?\d{3}\b', extracted_text)
        if dni_match:
            dni = dni_match.group(0).replace(".", "")

        # 2. Buscar Apellido y Nombres
        apellido = ""
        nombre = ""
        for i, line in enumerate(lines):
            line_upper = line.upper()
            if "APELLIDO" in line_upper:
                if ":" in line:
                    apellido = line.split(":", 1)[1].strip()
                elif i + 1 < len(lines):
                    next_line = lines[i + 1]
                    # Evitar capturar líneas que son títulos (todo mayúsculas con palabras clave)
                    if "NOMBRE" not in next_line.upper() and "DOCUMENTO" not in next_line.upper():
                        apellido = next_line
            elif "NOMBRE" in line_upper and "APELLIDO" not in line_upper:
                if ":" in line:
                    nombre = line.split(":", 1)[1].strip()
                elif i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if "APELLIDO" not in next_line.upper() and "DOCUMENTO" not in next_line.upper():
                        nombre = next_line

        def clean_field(text: str) -> str:
            """Normaliza un campo de texto eliminando caracteres extraños."""
            if not text:
                return ""
            replacements = {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N"}
            cleaned = text.upper()
            for orig, rep in replacements.items():
                cleaned = cleaned.replace(orig, rep)
            return re.sub(r'[^A-Z\s]', '', cleaned).strip()

        apellido = clean_field(apellido)
        nombre = clean_field(nombre)

        # 3. Buscar Fecha de Nacimiento
        fecha_nacimiento = ""
        dob_match = re.search(r'\b(\d{2})[/\-](\d{2})[/\-](\d{4})\b', extracted_text)
        if dob_match:
            day, month, year = dob_match.groups()
            fecha_nacimiento = f"{year}-{month}-{day}"
        else:
            dob_match_2 = re.search(r'\b(\d{2})[/\-](\d{2})[/\-](\d{2})\b', extracted_text)
            if dob_match_2:
                day, month, year_2 = dob_match_2.groups()
                year = f"20{year_2}" if int(year_2) < 30 else f"19{year_2}"
                fecha_nacimiento = f"{year}-{month}-{day}"

        return {
            "dni": dni,
            "nombre": nombre,
            "apellido": apellido,
            "fecha_nacimiento": fecha_nacimiento
        }
