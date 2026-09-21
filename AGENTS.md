# AGENTS.md

Sistema de preinscripción + legajos digitales UNdeC. Frontend React 19 + Vite (`src/`), backend FastAPI (`backend/app/`), base SQLite. Sin test suite; solo `npm run lint` (eslint frontend).

## Comandos
- Frontend: `npm run dev` (usa `src/services/api.js`, `VITE_API_URL` default `http://localhost:8000`)
- Backend: desde `backend/` con su venv activado: `uvicorn app.main:app --reload --port 8000`
- Test de carga masiva: `python test_carga_masiva.py` (necesita el server corriendo; admin por defecto DNI `10000000` / `admin123`, sembrado en `main.py`)
- No hay backend de tests ni conftest.

## Arquitectura / gotchas
- La DB SQLite real es `backend/legajos.db` (ruta absoluta calculada en `app/database.py`). Hay copias viejas trackeadas (`backend/app/legajos.db`, `legajos.db` en raíz) y archivos legajos commiteados por error pese al `.gitignore` — la única fuente de verdad es `backend/legajos.db`.
- Los documentos subidos se guardan en `backend/legajos/<carrera>/<dni>/` salvo que haya `backend/credentials.json` + `.env` (Google Drive opcional).
- Autenticación JWT; dependencias `get_current_user` / `get_current_student` en `app/utils/dependencies.py`. Rutas: `/auth`, `/estudiante`, `/admin`.
- `/auth/register` exige o bien archivos individuales (`dni_frente` + `dni_dorso`) o bien `archivo_compuesto`.

## OCR de DNI (núcleo del proyecto) — `app/services/ocr_service.py`
- 3 motores con readers globales lazy (la PRIMERA request paga la carga de modelos): PaddleOCR (primario), EasyOCR (secundario), Tesseract (terciario, necesita `TESSERACT_CMD` o tesseract en PATH).
- API PaddleOCR **3.x** (PaddleX): `predict()` → `rec_texts` / `rec_scores`. Pinned `<4.0.0` en `requirements.txt`: no subir a v4 (API cambia). `enable_mkldnn=False` es obligatorio (evita crash oneDNN de paddle 3.x).
- Dos rutas: `extract_text_fast` (solo PaddleOCR, para frente de DNI) y `extract_text` (todos los motores + voting, para PDFs y compuestos). El fast path hace fallback a voting completo si PaddleOCR no devuelve texto — puede tardar 30-60s.
- `preprocess_image(fast=True)` no se usa para Paddle/EasyOCR (leen la imagen original); su salida solo la usa Tesseract.
- `validate_dni_data` requiere `is_dni_document` + `dni` + `nombre` + `apellido` para `overall_match` (la fecha de nacimiento es opcional y no bloquea).
- Caché en memoria de extracciones OCR por SHA-256 del contenido (`_ocr_cache_get/_ocr_cache_set`, TTL 600s): `Preinscripcion.jsx` pre-analiza el DNI con `/auth/analizar-dni` y luego `/auth/register` vuelve a llamar al OCR sobre el mismo archivo; la segunda llamada es instantánea. Aplica a los 3 puntos de extracción (`extract_text_fast`, `extract_text`, `_extract_from_single_image`). Al tocar esto, no romper el flujo de validación.