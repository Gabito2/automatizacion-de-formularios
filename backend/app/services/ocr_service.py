import os
import re
import shutil
import tempfile
import cv2
import numpy as np
import logging

try:
    import fitz  # PyMuPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import mediapipe as mp
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    MEDIAPIPE_AVAILABLE = False

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OCRService")

# Umbral de confianza mínima para aceptar texto de cada motor
MIN_CONFIDENCE = 0.75

# ── MOTOR PRIMARIO: PaddleOCR ──────────────────────────────────────────────────
try:
    from paddleocr import PaddleOCR
    _paddleocr_reader = None

    def _get_paddleocr_reader():
        global _paddleocr_reader
        if _paddleocr_reader is None:
            logger.info("Inicializando PaddleOCR (primera carga, puede tardar)...")
            _paddleocr_reader = PaddleOCR(use_angle_cls=True, lang='es', show_log=False)
            logger.info("PaddleOCR listo.")
        return _paddleocr_reader

    PADDLEOCR_AVAILABLE = True
    logger.info("PaddleOCR disponible (motor primario).")
except ImportError:
    PADDLEOCR_AVAILABLE = False
    logger.warning("PaddleOCR no disponible.")

# ── MOTOR SECUNDARIO: EasyOCR ──────────────────────────────────────────────────
try:
    import easyocr
    _easyocr_reader = None

    def _get_easyocr_reader():
        global _easyocr_reader
        if _easyocr_reader is None:
            logger.info("Inicializando EasyOCR...")
            _easyocr_reader = easyocr.Reader(['es', 'en'], gpu=False, verbose=False)
            logger.info("EasyOCR listo.")
        return _easyocr_reader

    EASYOCR_AVAILABLE = True
    logger.info("EasyOCR disponible (motor secundario).")
except ImportError:
    EASYOCR_AVAILABLE = False
    logger.warning("EasyOCR no disponible.")

# ── MOTOR TERCIARIO: PyTesseract ───────────────────────────────────────────────
try:
    import pytesseract
    _tesseract_cmd = os.getenv("TESSERACT_CMD")
    if not _tesseract_cmd:
        _tesseract_cmd = shutil.which("tesseract")
    if _tesseract_cmd and os.path.exists(_tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd
        TESSERACT_AVAILABLE = True
        logger.info(f"Tesseract configurado en: {_tesseract_cmd}")
    else:
        try:
            pytesseract.get_tesseract_version()
            TESSERACT_AVAILABLE = True
            logger.info("Tesseract encontrado en PATH.")
        except Exception:
            TESSERACT_AVAILABLE = False
            logger.warning("Tesseract no encontrado.")
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("PyTesseract no instalado.")

# ── Keywords del DNI argentino ─────────────────────────────────────────────────
DNI_KEYWORDS = [
    "REPUBLICA ARGENTINA", "ARGENTINA",
    "DOCUMENTO NACIONAL DE IDENTIDAD", "DOCUMENTO NACIONAL",
    "IDENTIDAD", "APELLIDO", "NOMBRE", "NACIMIENTO",
    "SEXO", "NACIONALIDAD", "EJEMPLAR", "TRAMITE",
]
DNI_MIN_KEYWORDS = 2

# ── Tabla de corrección de caracteres similares ────────────────────────────────
DIGIT_CONFUSION_MAP = {
    'O': '0', 'o': '0',
    'I': '1', 'l': '1',
    'S': '5', 's': '5',
    'B': '8',
    'Z': '2', 'z': '2',
    'G': '6',
    'q': '9',
}


def _fix_digits_in_number(raw: str) -> str:
    """Reemplaza caracteres visualmente similares a dígitos en una cadena numérica."""
    result = []
    for ch in raw:
        if ch.isdigit():
            result.append(ch)
        elif ch in DIGIT_CONFUSION_MAP:
            result.append(DIGIT_CONFUSION_MAP[ch])
    return ''.join(result)


def _apply_digit_correction_to_text(text: str) -> str:
    """
    Aplica corrección de caracteres similares a dígitos solo en tokens
    que ya contienen al menos un dígito real (evita modificar texto alfabético).
    """
    if not text:
        return text

    def fix_token(token: str) -> str:
        has_digit = any(c.isdigit() for c in token)
        if not has_digit:
            return token
        return _fix_digits_in_number(token)

    tokens = re.split(r'(\s+)', text)
    corrected_tokens = []
    for token in tokens:
        if token.strip() and re.search(r'[\d]', token):
            corrected_tokens.append(fix_token(token))
        else:
            corrected_tokens.append(token)
    return ''.join(corrected_tokens)


class OCRService:

    # ─────────────────────────────────────────────────────────────────────────
    # Preprocesamiento de imagen
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def preprocess_image(image_path: str):
        """
        Preprocesamiento de imagen con OpenCV:
        - Escala a mínimo 1500px de ancho
        - Corrección leve de inclinación (deskew)
        - Filtro bilateral + CLAHE + Sharpening leve
        Retorna (imagen_procesada, quality_report).
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"No se pudo cargar la imagen: {image_path}")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Métricas de calidad
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        is_blurry = laplacian_var < 80.0
        mean_brightness = np.mean(gray)
        is_too_dark = mean_brightness < 45.0
        is_too_bright = mean_brightness > 235.0
        edges_q = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges_q > 0) / (gray.shape[0] * gray.shape[1])
        is_incomplete = edge_density < 0.01

        # Escalar a mínimo 1500px de ancho
        height, width = gray.shape
        TARGET_WIDTH = 1500
        if width < TARGET_WIDTH:
            sf = TARGET_WIDTH / width
            gray = cv2.resize(gray, (int(width * sf), int(height * sf)), interpolation=cv2.INTER_LANCZOS4)

        # Deskew leve
        try:
            e = cv2.Canny(gray, 50, 150, apertureSize=3)
            lines = cv2.HoughLines(e, 1, np.pi / 180, threshold=100)
            if lines is not None:
                angles = []
                for line in lines[:20]:
                    rho, theta = line[0]
                    angle = (theta * 180 / np.pi) - 90
                    if abs(angle) < 10:
                        angles.append(angle)
                if angles:
                    median_angle = np.median(angles)
                    if abs(median_angle) > 0.5:
                        h, w = gray.shape
                        M = cv2.getRotationMatrix2D((w // 2, h // 2), median_angle, 1.0)
                        gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        except Exception:
            pass

        # Filtro bilateral → CLAHE → Sharpening leve
        filtered = cv2.bilateralFilter(gray, 9, 75, 75)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(filtered)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)

        quality_report = {
            "blur_score": float(laplacian_var),
            "brightness_score": float(mean_brightness),
            "edge_density": float(edge_density),
            "is_blurry": bool(is_blurry),
            "is_too_dark": bool(is_too_dark),
            "is_too_bright": bool(is_too_bright),
            "is_incomplete": bool(is_incomplete),
            "legible": not (is_blurry or is_too_dark or is_too_bright),
        }
        return sharpened, quality_report

    # ─────────────────────────────────────────────────────────────────────────
    # Detección de documento DNI argentino
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _is_dni_document(text: str) -> bool:
        """
        Verifica si el texto extraído corresponde a un DNI argentino
        buscando keywords características del documento.
        """
        if not text or not text.strip():
            return False

        def normalize(t: str) -> str:
            t = t.upper()
            for orig, rep in {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N"}.items():
                t = t.replace(orig, rep)
            return t

        norm_text = normalize(text)
        found = sum(1 for kw in DNI_KEYWORDS if kw in norm_text)
        logger.info(f"[DNI-Check] Keywords encontradas: {found}/{len(DNI_KEYWORDS)} (mínimo: {DNI_MIN_KEYWORDS})")
        return found >= DNI_MIN_KEYWORDS

    # ─────────────────────────────────────────────────────────────────────────
    # Extracción por motor individual
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_with_paddleocr(image_path: str) -> tuple[str, float]:
        """Extrae texto con PaddleOCR filtrando por confianza mínima."""
        reader = _get_paddleocr_reader()
        result = reader.ocr(image_path, cls=True)
        lines, confidences = [], []
        if result and result[0]:
            for line in result[0]:
                if len(line) < 2:
                    continue
                text, confidence = line[1]
                confidence = float(confidence)
                if confidence >= MIN_CONFIDENCE:
                    lines.append(str(text).strip())
                    confidences.append(confidence)
                else:
                    logger.debug(f"[PaddleOCR] Descartado (conf={confidence:.2f}): '{text}'")
        extracted_text = "\n".join(lines)
        avg_confidence = float(np.mean(confidences)) if confidences else 0.0
        logger.info(f"[PaddleOCR] {len(lines)} bloques aceptados (conf_avg={avg_confidence:.2f}).")
        return extracted_text, avg_confidence

    @staticmethod
    def _extract_with_easyocr(image_path: str) -> tuple[str, float]:
        """Extrae texto con EasyOCR filtrando por confianza mínima."""
        reader = _get_easyocr_reader()
        results = reader.readtext(image_path, detail=1, paragraph=False)
        lines, confidences = [], []
        for (_, text, confidence) in results:
            confidence = float(confidence)
            if confidence >= MIN_CONFIDENCE:
                lines.append(str(text).strip())
                confidences.append(confidence)
            else:
                logger.debug(f"[EasyOCR] Descartado (conf={confidence:.2f}): '{text}'")
        extracted_text = "\n".join(lines)
        avg_confidence = float(np.mean(confidences)) if confidences else 0.0
        logger.info(f"[EasyOCR] {len(lines)} bloques aceptados (conf_avg={avg_confidence:.2f}).")
        return extracted_text, avg_confidence

    @staticmethod
    def _extract_with_tesseract(processed_img, for_digits: bool = False) -> tuple[str, float]:
        """
        Extrae texto con Tesseract.
        Si for_digits=True usa PSM 7 con whitelist numérica.
        """
        custom_config = (
            r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789'
            if for_digits
            else r'--oem 3 --psm 6 -l spa'
        )
        text = pytesseract.image_to_string(processed_img, config=custom_config)
        logger.info(f"[Tesseract] {len(text)} chars. for_digits={for_digits}")
        return text, 0.70

    # ─────────────────────────────────────────────────────────────────────────
    # Voting entre motores
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _run_all_engines(image_path: str, processed_img) -> list[dict]:
        """Ejecuta todos los motores disponibles y retorna sus resultados."""
        results = []

        # Guardar imagen preprocesada a disco temporal para que todos los motores la usen
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".png")
        try:
            os.close(tmp_fd)
            cv2.imwrite(tmp_path, processed_img)

            if PADDLEOCR_AVAILABLE:
                try:
                    text, conf = OCRService._extract_with_paddleocr(tmp_path)
                    if text.strip():
                        results.append({"engine": "paddleocr", "text": text, "confidence": conf})
                except Exception as e:
                    logger.warning(f"[Voting] PaddleOCR falló: {e}")

            if EASYOCR_AVAILABLE:
                try:
                    text, conf = OCRService._extract_with_easyocr(tmp_path)
                    if text.strip():
                        results.append({"engine": "easyocr", "text": text, "confidence": conf})
                except Exception as e:
                    logger.warning(f"[Voting] EasyOCR falló: {e}")

            if TESSERACT_AVAILABLE:
                try:
                    text, conf = OCRService._extract_with_tesseract(processed_img, for_digits=False)
                    if text.strip():
                        results.append({"engine": "tesseract", "text": text, "confidence": conf})
                except Exception as e:
                    logger.warning(f"[Voting] Tesseract falló: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        return results

    @staticmethod
    def _vote_best_result(results: list[dict]) -> tuple[str, str, float]:
        """
        Elige el mejor resultado mediante voting ponderado sobre el número de DNI.

        Estrategia:
        1. Extrae candidatos de DNI (7-8 dígitos) de cada motor aplicando corrección
        2. El candidato más votado (aparece en más motores) gana
        3. En empate, gana el de mayor confianza acumulada
        4. Retorna el texto completo del motor con el DNI ganador
        """
        if not results:
            return "", "none", 0.0
        if len(results) == 1:
            r = results[0]
            return _apply_digit_correction_to_text(r["text"]), r["engine"], r["confidence"]

        DNI_PATTERN = re.compile(r'\b\d{7,8}\b')

        motor_data = {}
        for r in results:
            corrected_text = _apply_digit_correction_to_text(r["text"])
            candidates = DNI_PATTERN.findall(corrected_text)
            eight_digit = [c for c in candidates if len(c) == 8]
            seven_digit = [c for c in candidates if len(c) == 7]
            best = eight_digit if eight_digit else seven_digit
            motor_data[r["engine"]] = {
                "first_dni": best[0] if best else None,
                "corrected_text": corrected_text,
                "confidence": r["confidence"],
            }

        logger.info(f"[Voting] Candidatos DNI: { {k: v['first_dni'] for k, v in motor_data.items()} }")

        vote_count: dict[str, int] = {}
        vote_confidence: dict[str, float] = {}
        for engine, data in motor_data.items():
            if data["first_dni"]:
                dni_val = data["first_dni"]
                vote_count[dni_val] = vote_count.get(dni_val, 0) + 1
                vote_confidence[dni_val] = vote_confidence.get(dni_val, 0.0) + data["confidence"]

        if vote_count:
            winning_dni = max(vote_count, key=lambda k: (vote_count[k], vote_confidence[k]))
            logger.info(
                f"[Voting] DNI ganador: {winning_dni} "
                f"(votos={vote_count[winning_dni]}, conf_sum={vote_confidence[winning_dni]:.2f})"
            )
            candidates_with_winner = [
                (engine, data)
                for engine, data in motor_data.items()
                if data["first_dni"] == winning_dni
            ]
            if candidates_with_winner:
                best_engine, best_data = max(candidates_with_winner, key=lambda x: x[1]["confidence"])
                return best_data["corrected_text"], best_engine, best_data["confidence"]

        # Fallback: mayor confianza
        best = max(results, key=lambda r: r["confidence"])
        logger.info(f"[Voting] Fallback: {best['engine']} ({best['confidence']:.2f})")
        return _apply_digit_correction_to_text(best["text"]), best["engine"], best["confidence"]

    # ─────────────────────────────────────────────────────────────────────────
    # Conversión de PDF a imágenes
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _pdf_to_images(pdf_path: str, dpi: int = 300) -> list[str]:
        """
        Convierte cada página de un PDF a una imagen PNG temporal.
        Retorna una lista de rutas a las imágenes generadas.
        """
        if not PDF_AVAILABLE:
            raise ValueError("PyMuPDF no está instalado. No se puede procesar PDFs.")

        temp_dir = tempfile.mkdtemp(prefix="ocr_pdf_")
        image_paths = []

        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            # Renderizar a pixmap con la resolución especificada
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            img_path = os.path.join(temp_dir, f"page_{page_num + 1}.png")
            pix.save(img_path)
            image_paths.append(img_path)
            logger.info(f"[PDF] Página {page_num + 1} convertida a imagen: {pix.width}x{pix.height}px")

        doc.close()
        return image_paths

    @staticmethod
    def _cleanup_temp_images(image_paths: list[str]):
        """Limpia imágenes temporales generadas desde PDFs."""
        for path in image_paths:
            temp_dir = os.path.dirname(path)
            if os.path.exists(path):
                os.remove(path)
        # Eliminar directorio temporal si queda vacío
        if image_paths:
            temp_dir = os.path.dirname(image_paths[0])
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)

    # ─────────────────────────────────────────────────────────────────────────
    # Extracción principal con voting
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_from_single_image(image_path: str) -> tuple[str, dict]:
        """
        Extrae texto de una sola imagen (sin conversión PDF).
        Retorna (extracted_text, quality_report).
        """
        processed_img, quality_report = OCRService.preprocess_image(image_path)
        all_results = OCRService._run_all_engines(image_path, processed_img)

        if not all_results:
            logger.warning("Ningún motor OCR pudo extraer texto.")
            quality_report["ocr_engine"] = "none"
            quality_report["ocr_error"] = "Ningún motor OCR disponible o imagen ilegible."
            quality_report["confidence_avg"] = 0.0
            return "", quality_report

        extracted_text, winning_engine, confidence_avg = OCRService._vote_best_result(all_results)

        quality_report["ocr_engine"] = winning_engine
        quality_report["ocr_engines_used"] = [r["engine"] for r in all_results]
        quality_report["confidence_avg"] = round(confidence_avg, 3)

        return extracted_text, quality_report

    @staticmethod
    def extract_text(file_path: str, user_info: dict = None) -> tuple[str, dict]:
        """
        Extrae texto de una imagen O PDF ejecutando TODOS los motores OCR disponibles.

        Si el archivo es un PDF, extrae cada página como imagen y ejecuta OCR
        sobre cada una, retornando el texto combinado de todas las páginas.

        Retorna (extracted_text, quality_report).
        """
        try:
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()

            # ── Caso PDF: convertir páginas a imágenes y procesar cada una ──
            if ext == ".pdf":
                if not PDF_AVAILABLE:
                    logger.warning("PDF subido pero PyMuPDF no disponible. No se puede procesar.")
                    return "", {
                        "blur_score": 0.0, "brightness_score": 0.0, "edge_density": 0.0,
                        "is_blurry": False, "is_too_dark": False, "is_too_bright": False,
                        "is_incomplete": True, "legible": False,
                        "ocr_engine": "none", "confidence_avg": 0.0,
                        "ocr_error": "PyMuPDF no instalado. No se puede procesar PDFs.",
                        "pages_processed": 0,
                    }

                logger.info(f"[OCR] Detectado PDF, extrayendo páginas: {file_path}")
                page_images = OCRService._pdf_to_images(file_path)

                if not page_images:
                    return "", {
                        "blur_score": 0.0, "brightness_score": 0.0, "edge_density": 0.0,
                        "is_blurry": False, "is_too_dark": False, "is_too_bright": False,
                        "is_incomplete": True, "legible": False,
                        "ocr_engine": "none", "confidence_avg": 0.0,
                        "ocr_error": "El PDF no contiene páginas procesables.",
                        "pages_processed": 0,
                    }

                try:
                    all_text_parts = []
                    best_quality = None
                    best_confidence = 0.0
                    best_engine = "none"
                    engines_used = set()

                    for i, page_img in enumerate(page_images):
                        logger.info(f"[OCR] Procesando página {i + 1}/{len(page_images)} del PDF")
                        text, qreport = OCRService._extract_from_single_image(page_img)

                        if text.strip():
                            all_text_parts.append(text)

                        # Conservar el reporte de calidad de la página con mayor confianza
                        conf = qreport.get("confidence_avg", 0.0)
                        if conf > best_confidence or best_quality is None:
                            best_quality = qreport
                            best_confidence = conf
                            best_engine = qreport.get("ocr_engine", "none")

                        if qreport.get("ocr_engines_used"):
                            engines_used.update(qreport["ocr_engines_used"])

                    combined_text = "\n".join(all_text_parts)

                    if best_quality is None:
                        best_quality = {
                            "blur_score": 0.0, "brightness_score": 0.0, "edge_density": 0.0,
                            "is_blurry": False, "is_too_dark": False, "is_too_bright": False,
                            "is_incomplete": True, "legible": False,
                        }

                    best_quality["ocr_engine"] = best_engine
                    best_quality["ocr_engines_used"] = list(engines_used)
                    best_quality["confidence_avg"] = round(best_confidence, 3)
                    best_quality["pages_processed"] = len(page_images)

                    logger.info(
                        f"[OCR Final PDF] {len(page_images)} páginas, "
                        f"motor: {best_engine}, confianza: {best_confidence:.2f}, "
                        f"texto total: {len(combined_text)} chars"
                    )
                    return combined_text, best_quality

                finally:
                    OCRService._cleanup_temp_images(page_images)

            # ── Caso imagen: procesar directamente ──
            extracted_text, quality_report = OCRService._extract_from_single_image(file_path)

            logger.info(
                f"[OCR Final] Motor ganador: {quality_report.get('ocr_engine', 'none')}, "
                f"confianza: {quality_report.get('confidence_avg', 0):.2f}, "
                f"texto: {len(extracted_text)} chars"
            )
            return extracted_text, quality_report

        except Exception as e:
            logger.error(f"Error en OCR: {str(e)}")
            return "", {
                "blur_score": 0.0, "brightness_score": 0.0, "edge_density": 0.0,
                "is_blurry": True, "is_too_dark": False, "is_too_bright": False,
                "is_incomplete": True, "legible": False,
                "ocr_engine": "none", "confidence_avg": 0.0, "error": str(e),
            }

    # ─────────────────────────────────────────────────────────────────────────
    # Validación de datos del DNI
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def validate_dni_data(extracted_text: str, declared_data: dict) -> dict:
        """
        Compara el texto OCR con los datos declarados por el estudiante.

        Criterios de aprobación (todos obligatorios):
        - La imagen es un DNI argentino (keywords)
        - El número de DNI coincide
        - El nombre coincide (todas las palabras de >2 letras)
        - El apellido coincide (todas las palabras de >2 letras)
        """
        if not extracted_text or not extracted_text.strip():
            return {
                "is_dni_document": False, "dni_match": False,
                "name_match": False, "lastname_match": False,
                "dob_match": False, "overall_match": False,
                "fields_matched": [], "text_empty": True,
            }

        def normalize(text: str) -> str:
            if not text:
                return ""
            text = text.upper()
            for orig, rep in {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N"}.items():
                text = text.replace(orig, rep)
            return re.sub(r'[^A-Z0-9\s]', '', text)

        norm_ocr = normalize(extracted_text)

        # 0. ¿Es un DNI argentino?
        is_dni_doc = OCRService._is_dni_document(extracted_text)

        # 1. DNI — match exacto como número independiente (7 u 8 dígitos)
        declared_dni = str(declared_data.get("dni") or "").strip()
        dni_match = False
        if declared_dni:
            dni_pattern = re.compile(rf'(?<!\d){re.escape(declared_dni)}(?!\d)')
            dni_match = bool(dni_pattern.search(norm_ocr.replace(" ", "")))

        # 2. Nombre
        declared_name = str(declared_data.get("nombre") or "").strip()
        norm_name = normalize(declared_name)
        name_match = False
        name_words_checked = []
        if norm_name:
            words = [w for w in norm_name.split() if len(w) > 2]
            if words:
                name_words_checked = words
                name_match = all(word in norm_ocr for word in words)
            else:
                name_match = norm_name in norm_ocr

        # 3. Apellido
        declared_lastname = str(declared_data.get("apellido") or "").strip()
        norm_lastname = normalize(declared_lastname)
        lastname_match = False
        lastname_words_checked = []
        if norm_lastname:
            words = [w for w in norm_lastname.split() if len(w) > 2]
            if words:
                lastname_words_checked = words
                lastname_match = all(word in norm_ocr for word in words)
            else:
                lastname_match = norm_lastname in norm_ocr

        # 4. Fecha de nacimiento
        declared_dob = str(declared_data.get("fecha_nacimiento") or "").strip()
        dob_match = False
        if declared_dob:
            try:
                parts = declared_dob.split("-")
                if len(parts) == 3:
                    year, month, day = parts
                    ocr_no_spaces = norm_ocr.replace(" ", "").replace("/", "").replace("-", "").replace(".", "")
                    dob_4y = f"{day}{month}{year}"
                    dob_2y = f"{day}{month}{year[2:]}"
                    if dob_4y in ocr_no_spaces or dob_2y in ocr_no_spaces:
                        dob_match = True
                    elif len(month) == 1 and len(day) == 1:
                        dob_4y_sl = f"{day.zfill(2)}{month.zfill(2)}{year}"
                        if dob_4y_sl in ocr_no_spaces:
                            dob_match = True
            except Exception:
                pass

        # 5. Resultado
        fields_matched = []
        if is_dni_doc:
            fields_matched.append("is_dni_document")
        if dni_match:
            fields_matched.append("dni")
        if name_match:
            fields_matched.append("nombre")
        if lastname_match:
            fields_matched.append("apellido")
        if dob_match:
            fields_matched.append("fecha_nacimiento")

        overall_match = bool(is_dni_doc and dni_match and name_match and lastname_match)

        logger.info(
            f"[Validación DNI] is_dni={is_dni_doc}, dni={dni_match}, "
            f"nombre={name_match} {name_words_checked}, "
            f"apellido={lastname_match} {lastname_words_checked}, "
            f"overall={overall_match}"
        )

        return {
            "is_dni_document": bool(is_dni_doc),
            "dni_match": bool(dni_match),
            "name_match": bool(name_match),
            "lastname_match": bool(lastname_match),
            "dob_match": bool(dob_match),
            "overall_match": overall_match,
            "fields_matched": fields_matched,
            "text_empty": False,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Parser de campos del DNI
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def parse_dni_text(extracted_text: str) -> dict:
        """
        Parsea DNI, Apellido, Nombre y Fecha de Nacimiento del texto extraído.
        Aplica corrección de dígitos antes de parsear.
        Prioriza números de 8 dígitos sobre 7.
        """
        if not extracted_text or not extracted_text.strip():
            return {"dni": "", "nombre": "", "apellido": "", "fecha_nacimiento": ""}

        corrected_text = _apply_digit_correction_to_text(extracted_text)
        lines = [line.strip() for line in corrected_text.split('\n') if line.strip()]

        # 1. DNI: 8 dígitos exactos primero, luego 7
        dni = ""
        m8 = re.search(r'(?<!\d)(\d{8})(?!\d)', corrected_text)
        if m8:
            dni = m8.group(1)
        else:
            m7 = re.search(r'(?<!\d)(\d{7})(?!\d)', corrected_text)
            if m7:
                dni = m7.group(1)
        if not dni:
            mfmt = re.search(r'\b(\d{1,2})[.\s](\d{3})[.\s](\d{3})\b', corrected_text)
            if mfmt:
                dni = mfmt.group(1) + mfmt.group(2) + mfmt.group(3)

        # 2. Apellido y Nombre — búsqueda robusta
        apellido, nombre = "", ""

        def _extract_value_after_label(line: str, label: str) -> str:
            """Extrae el valor después de un label, sea con ':' o en la línea siguiente."""
            upper_line = line.upper()
            if label not in upper_line:
                return ""
            # Caso 1: "APELLIDO: GARCIA"
            if ":" in line:
                after = line.split(":", 1)[1].strip()
                # Limpiar labels pegados (ej: "APELLIDO:GARCIA" → "GARCIA")
                if after:
                    return after
            # Caso 2: el label está solo, el valor viene en la siguiente línea
            return "__NEXT_LINE__"

        for i, line in enumerate(lines):
            upper_line = line.upper()

            # Buscar APELLIDO
            if "APELLIDO" in upper_line and "DOCUMENTO" not in upper_line:
                result = _extract_value_after_label(line, "APELLIDO")
                if result == "__NEXT_LINE__":
                    if i + 1 < len(lines):
                        nxt = lines[i + 1].upper()
                        if "NOMBRE" not in nxt and "DOCUMENTO" not in nxt and "APELLIDO" not in nxt:
                            apellido = lines[i + 1]
                elif result:
                    apellido = result

            # Buscar NOMBRE (excluir "APELLIDO Y NOMBRE" si aparece junto)
            elif "NOMBRE" in upper_line and "APELLIDO" not in upper_line:
                result = _extract_value_after_label(line, "NOMBRE")
                if result == "__NEXT_LINE__":
                    if i + 1 < len(lines):
                        nxt = lines[i + 1].upper()
                        if "APELLIDO" not in nxt and "DOCUMENTO" not in nxt and "NOMBRE" not in nxt:
                            nombre = lines[i + 1]
                elif result:
                    nombre = result

        def clean_field(text: str) -> str:
            if not text:
                return ""
            cleaned = text.upper()
            for orig, rep in {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N"}.items():
                cleaned = cleaned.replace(orig, rep)
            return re.sub(r'[^A-Z\s]', '', cleaned).strip()

        apellido = clean_field(apellido)
        nombre = clean_field(nombre)

        # 3. Fecha de nacimiento — soporta DD/MM/YYYY, DD.MM.YYYY, DD-MM-YYYY, DD/MM/YY
        fecha_nacimiento = ""
        # Formato con separadores: / . o -
        dm = re.search(r'\b(\d{2})[/\-.](\d{2})[/\-.](\d{4})\b', corrected_text)
        if dm:
            day, month, year = dm.groups()
            fecha_nacimiento = f"{year}-{month}-{day}"
        else:
            dm2 = re.search(r'\b(\d{2})[/\-.](\d{2})[/\-.](\d{2})\b', corrected_text)
            if dm2:
                day, month, y2 = dm2.groups()
                y2_int = int(y2)
                # DNIs argentinos: personas en edad universitaria (~17-70 años)
                # 00-30 → 2000s, 31-99 → 1900s
                year = f"20{y2}" if y2_int <= 30 else f"19{y2}"
                fecha_nacimiento = f"{year}-{month}-{day}"

        return {
            "dni": dni,
            "nombre": nombre,
            "apellido": apellido,
            "fecha_nacimiento": fecha_nacimiento,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Clasificación de tipo de documento en una imagen
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def classify_document_type(image_path: str) -> dict:
        """
        Determina si una imagen contiene un DNI frontal, dorso, foto de perfil u otro documento.
        Retorna: {"type": "dni_frente"|"dni_dorso"|"foto_perfil"|"desconocido",
                  "confidence": 0.0-1.0, "region": [x,y,w,h] o None}
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"type": "desconocido", "confidence": 0.0, "region": None}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            total_pixels = h * w

            # Preprocesamiento básico
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)

            # Densidad de bordes
            edge_density = np.sum(edges > 0) / total_pixels

            # Análisis de color (fondo del DNI argentino)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            mean_hue = np.mean(hsv[:, :, 0])
            mean_saturation = np.mean(hsv[:, :, 1])

            # 1. Verificar si es DNI frontal (keywords en OCR rápido)
            is_dni_front = False
            dni_confidence = 0.0
            try:
                temp_text, temp_conf = OCRService._extract_with_paddleocr(image_path)
                if temp_text:
                    dni_keywords_found = sum(1 for kw in ["APELLIDO", "NOMBRE", "NACIMIENTO", "DNI", "REPUBLICA"] 
                                             if kw in temp_text.upper())
                    if dni_keywords_found >= 2:
                        is_dni_front = True
                        dni_confidence = min(0.95, 0.6 + (dni_keywords_found * 0.1))
            except Exception:
                pass

            if is_dni_front:
                return {"type": "dni_frente", "confidence": dni_confidence, "region": None}

            # 2. Verificar si es DNI dorso (código de barras + sin keywords de frente)
            has_barcode = False
            try:
                # Detectar líneas horizontales densas (código de barras)
                horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
                detected_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, horizontal_kernel)
                line_density = np.sum(detected_lines > 0) / total_pixels
                has_barcode = line_density > 0.03
            except Exception:
                pass

            if has_barcode and not is_dni_front:
                return {"type": "dni_dorso", "confidence": 0.7, "region": None}

            # 3. Verificar si es foto de perfil (rostro detectado + relación de aspecto)
            has_face = False
            if MEDIAPIPE_AVAILABLE:
                try:
                    mp_face = mp.solutions.face_detection
                    with mp_face.FaceDetection(model_selection=1, min_detection_confidence=0.4) as detector:
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        results = detector.process(img_rgb)
                        if results.detections and len(results.detections) == 1:
                            has_face = True
                except Exception:
                    pass

            if not has_face and MEDIAPIPE_AVAILABLE:
                try:
                    face_cascade = cv2.CascadeClassifier(
                        os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
                    )
                    faces = face_cascade.detectMultiScale(gray, 1.1, 3, minSize=(40, 40))
                    if len(faces) == 1:
                        has_face = True
                except Exception:
                    pass

            aspect_ratio = w / h if h > 0 else 0
            is_photo_aspect = 0.6 < aspect_ratio < 0.9 or 1.1 < aspect_ratio < 1.5

            if has_face and is_photo_aspect:
                return {"type": "foto_perfil", "confidence": 0.8, "region": None}

            return {"type": "desconocido", "confidence": 0.3, "region": None}

        except Exception as e:
            logger.warning(f"[classify] Error clasificando documento: {e}")
            return {"type": "desconocido", "confidence": 0.0, "region": None}

    # ─────────────────────────────────────────────────────────────────────────
    # Separación de imagen con múltiples documentos
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def split_composite_image(image_path: str) -> list[dict]:
        """
        Detecta si una imagen contiene múltiples documentos y los separa.
        Retorna: [{"type": "dni_frente", "image_path": "temp_crop.png", "region": [x,y,w,h]}, ...]
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return []

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            total_pixels = h * w

            # Preprocesamiento para detectar regiones
            blurred = cv2.GaussianBlur(gray, (7, 7), 0)
            _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Detectar bordes
            edges = cv2.Canny(thresh, 30, 100)

            # Dilatar para cerrar gaps en bordes
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
            dilated = cv2.dilate(edges, kernel, iterations=3)

            # Encontrar contornos
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Filtrar contornos por área mínima (al menos 5% del área total)
            min_area = total_pixels * 0.05
            candidates = []
            for contour in contours:
                x, y, cw, ch = cv2.boundingRect(contour)
                area = cw * ch
                if area >= min_area and cw > 50 and ch > 50:
                    candidates.append((x, y, cw, ch))

            # Si no hay candidatos claros, intentar con grid 2x2
            if len(candidates) < 2:
                # Dividir la imagen en 4 cuadrantes
                mid_h, mid_w = h // 2, w // 2
                candidates = [
                    (0, 0, mid_w, mid_h),
                    (mid_w, 0, w - mid_w, mid_h),
                    (0, mid_h, mid_w, h - mid_h),
                    (mid_w, mid_h, w - mid_w, h - mid_h),
                ]

            # Clasificar cada región
            documents = []
            temp_dir = tempfile.mkdtemp(prefix="split_")

            for i, (x, y, cw, ch) in enumerate(candidates):
                crop = img[y:y+ch, x:x+cw]
                crop_path = os.path.join(temp_dir, f"region_{i}.png")
                cv2.imwrite(crop_path, crop)

                # Clasificar la región
                classification = OCRService.classify_document_type(crop_path)

                if classification["type"] != "desconocido" and classification["confidence"] >= 0.5:
                    documents.append({
                        "type": classification["type"],
                        "image_path": crop_path,
                        "region": [x, y, cw, ch],
                        "confidence": classification["confidence"],
                        "temp_dir": temp_dir,
                    })

            # Si no se clasificó nada, al menos devolver la imagen completa
            if not documents:
                classification = OCRService.classify_document_type(image_path)
                documents.append({
                    "type": classification["type"],
                    "image_path": image_path,
                    "region": [0, 0, w, h],
                    "confidence": classification["confidence"],
                    "temp_dir": None,
                })

            return documents

        except Exception as e:
            logger.warning(f"[split] Error separando imagen: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Pipeline completo de extracción desde archivo compuesto
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def extract_from_composite(file_path: str) -> dict:
        """
        Pipeline completo:
        1. Si es PDF → convertir a imágenes
        2. Para cada imagen → clasificar tipo
        3. Si imagen compuesta → separar
        4. En DNI frontal → extraer datos
        Retorna: {
            "documents_found": [...],
            "dni_data": {"dni": "...", "nombre": "...", ...},
            "confidence": 0.92,
            "needs_manual_review": False
        }
        """
        try:
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()

            all_documents = []

            # Caso PDF: procesar cada página
            if ext == ".pdf":
                if not PDF_AVAILABLE:
                    return {
                        "documents_found": [],
                        "dni_data": None,
                        "confidence": 0.0,
                        "needs_manual_review": True,
                        "error": "PyMuPDF no instalado"
                    }

                page_images = OCRService._pdf_to_images(file_path)
                try:
                    for i, page_img in enumerate(page_images):
                        classification = OCRService.classify_document_type(page_img)
                        all_documents.append({
                            "type": classification["type"],
                            "image_path": page_img,
                            "page": i + 1,
                            "confidence": classification["confidence"],
                        })
                finally:
                    OCRService._cleanup_temp_images(page_images)

            # Caso imagen
            else:
                # Primero intentar separar si parece compuesta
                split_docs = OCRService.split_composite_image(file_path)

                if len(split_docs) > 1:
                    # Imagen compuesta con múltiples documentos
                    all_documents = split_docs
                else:
                    # Imagen simple
                    classification = OCRService.classify_document_type(file_path)
                    all_documents.append({
                        "type": classification["type"],
                        "image_path": file_path,
                        "region": None,
                        "confidence": classification["confidence"],
                    })

            # Buscar el DNI frontal para extraer datos
            dni_data = None
            dni_confidence = 0.0
            dni_doc = None

            for doc in all_documents:
                if doc["type"] == "dni_frente":
                    try:
                        extracted_text, quality_report = OCRService._extract_from_single_image(doc["image_path"])
                        if extracted_text.strip():
                            dni_data = OCRService.parse_dni_text(extracted_text)
                            dni_confidence = quality_report.get("confidence_avg", 0.0)
                            dni_doc = doc
                            break
                    except Exception as e:
                        logger.warning(f"[composite] Error extrayendo DNI de {doc['image_path']}: {e}")

            # Determinar si necesita revisión manual
            needs_manual_review = False
            if dni_data:
                if not dni_data.get("dni") or not dni_data.get("nombre"):
                    needs_manual_review = True
                elif dni_confidence < 0.6:
                    needs_manual_review = True

            return {
                "documents_found": [
                    {
                        "type": d["type"],
                        "region": d.get("region"),
                        "confidence": d.get("confidence", 0.0),
                        "page": d.get("page"),
                    } for d in all_documents
                ],
                "dni_data": dni_data,
                "confidence": dni_confidence,
                "needs_manual_review": needs_manual_review,
            }

        except Exception as e:
            logger.error(f"[composite] Error en pipeline: {e}")
            return {
                "documents_found": [],
                "dni_data": None,
                "confidence": 0.0,
                "needs_manual_review": True,
                "error": str(e),
            }

    # ─────────────────────────────────────────────────────────────────────────
    # Pipeline para análisis de archivo compuesto (endpoint dedicado)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def analyze_composite_file(file_path: str) -> dict:
        """
        Analiza un archivo (imagen o PDF) que puede contener múltiples documentos.
        Retorna los documentos encontrados y los datos extraídos del DNI.
        """
        result = OCRService.extract_from_composite(file_path)

        # Agregar previews de cada documento encontrado
        documents_with_preview = []
        for doc in result.get("documents_found", []):
            doc_info = {
                "type": doc["type"],
                "region": doc.get("region"),
                "confidence": doc.get("confidence", 0.0),
                "page": doc.get("page"),
            }
            documents_with_preview.append(doc_info)

        return {
            "documents": documents_with_preview,
            "dni_data": result.get("dni_data"),
            "confidence": result.get("confidence", 0.0),
            "needs_manual_review": result.get("needs_manual_review", True),
            "error": result.get("error"),
        }
