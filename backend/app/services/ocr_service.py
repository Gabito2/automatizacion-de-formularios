import os
import re
import cv2
import numpy as np
import logging

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
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if os.path.exists(TESSERACT_CMD):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        TESSERACT_AVAILABLE = True
        logger.info(f"Tesseract configurado en: {TESSERACT_CMD}")
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
        Preprocesamiento avanzado con OpenCV:
        - Escala a mínimo 1500px de ancho
        - Corrección leve de inclinación (deskew)
        - Filtro bilateral + CLAHE + Sharpening
        - Umbralización adaptativa
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

        # Filtro bilateral → CLAHE → Sharpening → Umbralización
        filtered = cv2.bilateralFilter(gray, 9, 75, 75)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(filtered)
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(enhanced, -1, kernel)
        thresh = cv2.adaptiveThreshold(
            sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 4
        )

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
        return thresh, quality_report

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

        if PADDLEOCR_AVAILABLE:
            try:
                text, conf = OCRService._extract_with_paddleocr(image_path)
                if text.strip():
                    results.append({"engine": "paddleocr", "text": text, "confidence": conf})
            except Exception as e:
                logger.warning(f"[Voting] PaddleOCR falló: {e}")

        if EASYOCR_AVAILABLE:
            try:
                text, conf = OCRService._extract_with_easyocr(image_path)
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
    # Extracción principal con voting
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def extract_text(image_path: str, user_info: dict = None) -> tuple[str, dict]:
        """
        Extrae texto ejecutando TODOS los motores disponibles y eligiendo el mejor
        mediante voting ponderado sobre el número de DNI detectado.

        Retorna (extracted_text, quality_report).
        """
        try:
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

            logger.info(
                f"[OCR Final] Motor ganador: {winning_engine}, "
                f"confianza: {confidence_avg:.2f}, texto: {len(extracted_text)} chars"
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

        # 1. DNI
        declared_dni = str(declared_data.get("dni") or "").strip()
        norm_ocr_clean = norm_ocr.replace(" ", "")
        dni_match = False
        if declared_dni:
            dni_match = declared_dni in norm_ocr_clean
            if not dni_match and len(declared_dni) == 8:
                dni_fmt = f"{declared_dni[:2]}{declared_dni[2:5]}{declared_dni[5:]}"
                dni_match = dni_fmt in norm_ocr_clean

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
                    ocr_no_spaces = norm_ocr.replace(" ", "").replace("/", "").replace("-", "")
                    if f"{day}{month}{year}" in ocr_no_spaces or f"{day}{month}{year[2:]}" in ocr_no_spaces:
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

        # 2. Apellido y Nombre
        apellido, nombre = "", ""
        for i, line in enumerate(lines):
            lu = line.upper()
            if "APELLIDO" in lu:
                if ":" in line:
                    apellido = line.split(":", 1)[1].strip()
                elif i + 1 < len(lines):
                    nxt = lines[i + 1]
                    if "NOMBRE" not in nxt.upper() and "DOCUMENTO" not in nxt.upper():
                        apellido = nxt
            elif "NOMBRE" in lu and "APELLIDO" not in lu:
                if ":" in line:
                    nombre = line.split(":", 1)[1].strip()
                elif i + 1 < len(lines):
                    nxt = lines[i + 1]
                    if "APELLIDO" not in nxt.upper() and "DOCUMENTO" not in nxt.upper():
                        nombre = nxt

        def clean_field(text: str) -> str:
            if not text:
                return ""
            cleaned = text.upper()
            for orig, rep in {"Á": "A", "É": "E", "Í": "I", "Ó": "O", "Ú": "U", "Ñ": "N"}.items():
                cleaned = cleaned.replace(orig, rep)
            return re.sub(r'[^A-Z\s]', '', cleaned).strip()

        apellido = clean_field(apellido)
        nombre = clean_field(nombre)

        # 3. Fecha de nacimiento
        fecha_nacimiento = ""
        dm = re.search(r'\b(\d{2})[/\-](\d{2})[/\-](\d{4})\b', corrected_text)
        if dm:
            day, month, year = dm.groups()
            fecha_nacimiento = f"{year}-{month}-{day}"
        else:
            dm2 = re.search(r'\b(\d{2})[/\-](\d{2})[/\-](\d{2})\b', corrected_text)
            if dm2:
                day, month, y2 = dm2.groups()
                year = f"20{y2}" if int(y2) < 30 else f"19{y2}"
                fecha_nacimiento = f"{year}-{month}-{day}"

        return {
            "dni": dni,
            "nombre": nombre,
            "apellido": apellido,
            "fecha_nacimiento": fecha_nacimiento,
        }
