import os
import shutil
import base64
import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, UploadFile, File, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
import random
import string

from app.database import get_db
from app.models.models import Usuario, DatosPersonales, Documento
from app.utils.security import verify_password, get_password_hash, create_access_token
from app.utils.dependencies import get_current_user
from app.services.email_service import EmailService
from app.utils.file_manager import save_document_file
from app.services.ocr_service import OCRService
from app.services.face_service import FaceService

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginJSON(BaseModel):
    dni: str
    password: str

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str

class RecoveryRequest(BaseModel):
    dni: str
    email: EmailStr

class ImageBase64Request(BaseModel):
    image_base64: str  # Imagen codificada en base64 (sin el prefijo data:image/...;base64,)
    filename: str = "camara.jpg"  # Nombre de referencia con extensión

def generate_temp_password(length=8) -> str:
    """Genera una contraseña temporal aleatoria."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(length))

@router.post("/login")
def login(login_data: LoginJSON, db: Session = Depends(get_db)):
    """Inicia sesión con DNI y contraseña. Retorna un token JWT."""
    user = db.query(Usuario).filter(Usuario.dni == login_data.dni).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="DNI o contraseña incorrectos"
        )
    
    if not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="DNI o contraseña incorrectos"
        )
        
    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo"
        )
        
    # Crear token JWT
    access_token = create_access_token(data={"sub": user.dni})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "dni": user.dni,
            "nombre": user.nombre,
            "apellido": user.apellido,
            "email": user.email,
            "rol": user.rol,
            "primer_ingreso": user.primer_ingreso,
            "carrera": user.carrera,
            "sede": user.sede
        }
    }

@router.post("/change-password")
def change_password(
    data: PasswordChangeRequest, 
    current_user: Usuario = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    """Permite al usuario cambiar su contraseña actual y remueve la bandera de primer_ingreso."""
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña anterior es incorrecta"
        )
        
    current_user.password_hash = get_password_hash(data.new_password)
    current_user.primer_ingreso = False
    db.commit()
    return {"message": "Contraseña cambiada exitosamente"}

@router.post("/recovery")
def recover_password(
    data: RecoveryRequest, 
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Recupera la cuenta validando DNI y email, generando una nueva clave temporal."""
    user = db.query(Usuario).filter(Usuario.dni == data.dni, Usuario.email == data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró un usuario registrado con los datos provistos"
        )
        
    temp_pass = generate_temp_password()
    user.password_hash = get_password_hash(temp_pass)
    user.primer_ingreso = True  # Obligar cambio al volver a entrar
    db.commit()
    
    # Enviar email de recuperación
    EmailService.send_account_created(
        background_tasks=background_tasks,
        to_email=user.email,
        nombre=f"{user.nombre} {user.apellido}",
        dni=user.dni,
        temp_password=temp_pass
    )
    
    return {"message": "Se ha generado una nueva contraseña temporal y enviado a su correo electrónico."}

@router.post("/analizar-dni")
def analizar_dni(
    file: UploadFile = File(...),
):
    """
    Recibe una imagen o PDF de DNI (frente) y extrae sus datos
    (DNI, Nombre, Apellido, Fecha de Nacimiento) mediante OCR.
    """
    allowed_extensions = {".jpg", ".jpeg", ".png", ".pdf"}
    filename = file.filename
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de archivo no permitido. Solo se aceptan imágenes JPG, PNG y PDFs."
        )
        
    # Guardar temporalmente en un archivo para que OCRService pueda leerlo
    temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legajos", "temp"))
    os.makedirs(temp_dir, exist_ok=True)
    
    temp_path = os.path.join(temp_dir, f"temp_ocr_{random.randint(1000, 9999)}{ext}")
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Extraer texto de la imagen
        extracted_text, quality_report = OCRService.extract_text(temp_path)
        
        # Parsear los campos estructurados
        extracted_fields = OCRService.parse_dni_text(extracted_text)
        
        return {
            "extracted_text": extracted_text,
            "extracted_fields": extracted_fields,
            "calidad_reporte": quality_report
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar el DNI: {str(e)}"
        )
    finally:
        # Limpiar archivo temporal si existe
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/analizar-dni-camara")
def analizar_dni_camara(
    data: ImageBase64Request,
):
    """
    Recibe una imagen de DNI (frente) codificada en base64 capturada desde la cámara
    y extrae sus datos (DNI, Nombre, Apellido, Fecha de Nacimiento) mediante OCR.
    """
    allowed_extensions = {".jpg", ".jpeg", ".png"}
    _, ext = os.path.splitext(data.filename)
    ext = ext.lower() or ".jpg"

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de archivo no permitido. Solo se aceptan imágenes JPG y PNG."
        )

    # Decodificar base64
    try:
        # Quitar posible prefijo data:image/...;base64,
        raw_b64 = data.image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        image_bytes = base64.b64decode(raw_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La imagen base64 recibida no tiene un formato válido."
        )

    temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legajos", "temp"))
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"temp_ocr_cam_{random.randint(1000, 9999)}{ext}")

    try:
        with open(temp_path, "wb") as f:
            f.write(image_bytes)

        extracted_text, quality_report = OCRService.extract_text(temp_path)
        extracted_fields = OCRService.parse_dni_text(extracted_text)

        return {
            "extracted_text": extracted_text,
            "extracted_fields": extracted_fields,
            "calidad_reporte": quality_report
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar la imagen de DNI desde cámara: {str(e)}"
        )
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/analizar-foto")
def analizar_foto(
    file: UploadFile = File(...),
):
    """
    Recibe una imagen de foto personal (selfie/carnet) y verifica si contiene
    un rostro humano visible. Usado para validación previa en el formulario
    de preinscripción antes del envío final.
    """
    allowed_extensions = {".jpg", ".jpeg", ".png"}
    filename = file.filename
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de archivo no permitido. Solo se aceptan imágenes JPG y PNG."
        )

    # Guardar temporalmente para que FaceService pueda leerlo
    temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legajos", "temp"))
    os.makedirs(temp_dir, exist_ok=True)

    temp_path = os.path.join(temp_dir, f"temp_face_{random.randint(1000, 9999)}{ext}")
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        face_result = FaceService.detect_face(temp_path)

        if face_result.get("has_face"):
            message = (
                f"Rostro detectado correctamente (confianza: {face_result['confidence']:.0%})."
            )
        else:
            message = "No se detectó un rostro humano visible en la imagen. Asegúrese de que su cara esté centrada y bien iluminada."

        return {
            "has_face": face_result["has_face"],
            "face_count": face_result["face_count"],
            "confidence": face_result["confidence"],
            "method_used": face_result.get("method_used", "unknown"),
            "message": message,
            "error": face_result.get("error")
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar la foto: {str(e)}"
        )
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/analizar-foto-camara")
def analizar_foto_camara(
    data: ImageBase64Request,
):
    """
    Recibe una imagen de foto personal capturada desde la cámara (base64)
    y verifica si contiene un rostro humano visible.
    """
    allowed_extensions = {".jpg", ".jpeg", ".png"}
    _, ext = os.path.splitext(data.filename)
    ext = ext.lower() or ".jpg"

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no permitido. Solo se aceptan imágenes JPG y PNG."
        )

    try:
        raw_b64 = data.image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        image_bytes = base64.b64decode(raw_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La imagen base64 recibida no tiene un formato válido."
        )

    temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legajos", "temp"))
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"temp_face_cam_{random.randint(1000, 9999)}{ext}")

    try:
        with open(temp_path, "wb") as f:
            f.write(image_bytes)

        face_result = FaceService.detect_face(temp_path)

        if face_result.get("has_face"):
            message = f"Rostro detectado correctamente (confianza: {face_result['confidence']:.0%})."
        else:
            message = "No se detectó un rostro humano visible. Asegúrese de que su cara esté centrada y bien iluminada."

        return {
            "has_face": face_result["has_face"],
            "face_count": face_result["face_count"],
            "confidence": face_result["confidence"],
            "method_used": face_result.get("method_used", "unknown"),
            "message": message,
            "error": face_result.get("error")
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar la foto desde cámara: {str(e)}"
        )
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.post("/register")
def register_student(
    dni: str = Form(...),
    nombre: str = Form(...),
    apellido: str = Form(...),
    email: str = Form(...),
    carrera: str = Form(...),
    sede: str = Form(...),
    telefono: str = Form(...),
    direccion: str = Form(...),
    localidad: str = Form(...),
    provincia: str = Form(...),
    fecha_nacimiento: str = Form(...),
    secundario_completo: str = Form(...),
    titulo_secundario: str = Form(...),
    password: str = Form(...),
    dni_frente: UploadFile = File(None),
    dni_dorso: UploadFile = File(None),
    foto_persona: UploadFile = File(None),
    archivo_compuesto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    """
    Registra/preinscribe un nuevo estudiante.
    Acepta archivos individuales (dni_frente, dni_dorso, foto_persona) O un archivo compuesto
    que contiene todos los documentos. Realiza validación OCR en el DNI frontal.
    """
    # 1. Verificar si el DNI ya existe
    existing_user = db.query(Usuario).filter(Usuario.dni == dni).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El número de DNI ingresado ya se encuentra registrado."
        )

    # 2. Validar que se haya proporcionado al menos un método de carga
    has_compuesto = archivo_compuesto is not None
    has_individual = dni_frente is not None and dni_dorso is not None

    if not has_compuesto and not has_individual:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar los archivos individuales (DNI frente y dorso) o un archivo compuesto."
        )

    # 3. Validar extensiones de archivo
    image_exts = {".jpg", ".jpeg", ".png"}
    dni_exts = {".pdf", ".jpg", ".jpeg", ".png"}

    # Variables para guardar paths
    saved_frente = None
    saved_dorso = None
    saved_persona = None
    saved_paths_compuesto = None

    if has_compuesto:
        # Validar extensión del archivo compuesto
        _, ext = os.path.splitext(archivo_compuesto.filename)
        ext = ext.lower()
        if ext not in dni_exts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato no permitido para el archivo compuesto. Solo se aceptan PDFs e imágenes."
            )

        # Procesar archivo compuesto
        temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legajos", "temp"))
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"temp_compuesto_{random.randint(1000, 9999)}{ext}")

        try:
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(archivo_compuesto.file, buffer)

            # Analizar archivo compuesto
            composite_result = OCRService.analyze_composite_file(temp_path)

            # Guardar documentos extraídos
            if composite_result.get("documents"):
                from app.utils.file_manager import save_composite_documents
                saved_paths_compuesto = save_composite_documents(
                    carrera, dni, composite_result["documents"], archivo_compuesto
                )
                saved_frente = saved_paths_compuesto.get("dni_frente")
                saved_dorso = saved_paths_compuesto.get("dni_dorso")
                saved_persona = saved_paths_compuesto.get("foto_4x4")
            else:
                # Si no se detectaron documentos, guardar el archivo original como dni_frente
                saved_frente = save_document_file(carrera, dni, "dni_frente", archivo_compuesto)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al procesar el archivo compuesto: {str(e)}"
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    else:
        # Modo individual: validar extensiones
        for file_item, label in [(dni_frente, "DNI Frente"), (dni_dorso, "DNI Dorso")]:
            _, ext = os.path.splitext(file_item.filename)
            ext = ext.lower()
            if ext not in dni_exts:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Formato no permitido para {label}. Solo se aceptan PDFs e imágenes."
                )

        if foto_persona is not None:
            _, ext = os.path.splitext(foto_persona.filename)
            ext = ext.lower()
            if ext not in image_exts:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="La foto personal debe ser una imagen (.jpg, .jpeg, .png)."
                )

        # Guardar archivos individuales
        try:
            saved_frente = save_document_file(carrera, dni, "dni_frente", dni_frente)
            saved_dorso = save_document_file(carrera, dni, "dni_dorso", dni_dorso)
            if foto_persona is not None:
                saved_persona = save_document_file(carrera, dni, "foto_4x4", foto_persona)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al guardar los archivos de la preinscripción: {str(e)}"
            )

    # Obtener rutas físicas absolutas para procesamiento
    absolute_frente = None
    user_dir = None
    if saved_frente:
        absolute_frente = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", saved_frente))
        user_dir = os.path.dirname(absolute_frente)

    # 4. Validación Facial en la foto personal (solo si se subió)
    face_check = {"has_face": False, "confidence": 0.0, "method_used": "none"}
    if saved_persona:
        absolute_persona = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", saved_persona))
        # Determinar extensión de la foto
        if foto_persona:
            _, persona_ext = os.path.splitext(foto_persona.filename)
        elif has_compuesto:
            persona_ext = ".jpg"  # Default para fotos extraídas de compuesto
        else:
            persona_ext = ".jpg"
        if persona_ext.lower() in image_exts:
            face_check = FaceService.detect_face(absolute_persona)
            if not face_check.get("has_face") and user_dir and os.path.exists(user_dir):
                shutil.rmtree(user_dir)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Detección facial fallida: No se encontró un rostro humano visible en la foto de perfil subida. "
                        "Asegúrese de que su cara esté centrada, bien iluminada y sin obstrucciones."
                    )
                )

    # 5. Validación OCR del DNI Frente (imágenes Y PDFs)
    ocr_results = None
    quality_report = None
    ocr_dni_observado = False
    ocr_observacion_msg = None

    ocr_extensions = {".jpg", ".jpeg", ".png", ".pdf"}

    # Determinar qué archivo usar para OCR
    ocr_file_path = absolute_frente
    ocr_file_ext = None
    if ocr_file_path:
        _, ocr_file_ext = os.path.splitext(ocr_file_path)

    if ocr_file_path and ocr_file_ext and ocr_file_ext.lower() in ocr_extensions:
        user_info = {
            "dni": dni,
            "nombre": nombre,
            "apellido": apellido,
            "fecha_nacimiento": fecha_nacimiento
        }
        try:
            extracted_text, quality_report = OCRService.extract_text(ocr_file_path, user_info)
            ocr_results = OCRService.validate_dni_data(extracted_text, user_info)

            if quality_report and (quality_report.get("is_blurry") or quality_report.get("is_too_dark") or quality_report.get("is_too_bright")):
                # Imagen de baja calidad → observado para revisión manual
                ocr_dni_observado = True
                ocr_observacion_msg = "El sistema detectó baja calidad en la imagen del DNI (borrosa o con mala iluminación). Requiere revisión manual."
            elif ocr_results and not ocr_results.get("overall_match"):
                # Datos no coinciden o texto vacío → observado para revisión manual
                ocr_dni_observado = True
                if ocr_results.get("text_empty"):
                    ocr_observacion_msg = "No se pudo extraer texto del DNI (imagen ilegible). El documento requiere revisión manual."
                elif not ocr_results.get("is_dni_document"):
                    ocr_observacion_msg = "La imagen subida no parece ser un DNI argentino. Por favor suba una foto clara del frente de su DNI."
                elif not ocr_results.get("dni_match"):
                    ocr_observacion_msg = "El número de DNI extraído del documento no coincide con el DNI declarado en el formulario. Requiere revisión manual."
                elif not ocr_results.get("name_match") or not ocr_results.get("lastname_match"):
                    ocr_observacion_msg = "El nombre o apellido extraído del DNI no coincide con los datos ingresados. Requiere revisión manual."
                else:
                    ocr_observacion_msg = "Los datos extraídos del DNI no coinciden completamente con los ingresados. Requiere revisión manual."
        except Exception as e:
            logger_auth = logging.getLogger("AuthRouter")
            logger_auth.warning(f"Error en OCR durante registro: {e}")
            ocr_dni_observado = True
            ocr_observacion_msg = "Error al procesar el DNI automáticamente. Requiere revisión manual."

    # 6. Registrar en la base de datos
    try:
        # A. Crear Usuario Estudiante
        new_user = Usuario(
            dni=dni,
            nombre=nombre,
            apellido=apellido,
            email=email,
            password_hash=get_password_hash(password),
            rol="estudiante",
            activo=True,
            primer_ingreso=False,
            carrera=carrera,
            sede=sede
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # B. Crear Ficha de Datos Personales
        secundario_bool = str(secundario_completo).lower() in ("true", "1")
        datos_pers = DatosPersonales(
            usuario_id=new_user.id,
            telefono=telefono,
            direccion=direccion,
            localidad=localidad,
            provincia=provincia,
            fecha_nacimiento=fecha_nacimiento,
            secundario_completo=secundario_bool,
            titulo_secundario=titulo_secundario
        )
        db.add(datos_pers)

        # C. Registrar Documentos en DB
        # Estado del DNI frente según resultado OCR
        if ocr_results and ocr_results.get("overall_match"):
            estado_frente = "aprobado"
            obs_frente = None
        elif ocr_dni_observado:
            estado_frente = "observado"
            obs_frente = ocr_observacion_msg
        else:
            estado_frente = "pendiente"
            obs_frente = None

        # Registrar DNI Frente (si existe)
        if saved_frente:
            doc_frente = Documento(
                usuario_id=new_user.id,
                tipo_documento="dni_frente",
                archivo_url=saved_frente,
                estado=estado_frente,
                observacion=obs_frente
            )
            db.add(doc_frente)

        # Registrar DNI Dorso (si existe)
        if saved_dorso:
            doc_dorso = Documento(
                usuario_id=new_user.id,
                tipo_documento="dni_dorso",
                archivo_url=saved_dorso,
                estado="pendiente"
            )
            db.add(doc_dorso)

        # Foto personal (opcional)
        if saved_persona is not None:
            confidence = face_check.get("confidence", 0.0)
            estado_foto = "aprobado" if confidence >= 0.5 else "pendiente"
            obs_foto = None if confidence >= 0.5 else f"Detección facial con baja confianza ({confidence:.0%}). Requiere revisión manual."

            doc_persona = Documento(
                usuario_id=new_user.id,
                tipo_documento="foto_4x4",
                archivo_url=saved_persona,
                estado=estado_foto,
                observacion=obs_foto
            )
            db.add(doc_persona)

        db.commit()

        # Mensaje de respuesta según estado de validaciones
        warnings = []
        if ocr_dni_observado:
            warnings.append("El DNI frontal quedó marcado para revisión manual.")
        if saved_persona is None:
            warnings.append("No se adjuntó foto personal. Podrá subirla más tarde desde su panel.")

        msg = "Preinscripción realizada con éxito. Ahora puede iniciar sesión con su DNI y contraseña."
        if warnings:
            msg += " Nota: " + " ".join(warnings)

        return {"message": msg}

    except Exception as ex:
        db.rollback()
        # Limpiar archivos si falló la base de datos
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar la preinscripción en el sistema: {str(ex)}"
        )


@router.post("/analizar-archivo-compuesto")
def analizar_archivo_compuesto(
    file: UploadFile = File(...),
):
    """
    Analiza un archivo (imagen o PDF) que puede contener múltiples documentos
    (DNI frontal, dorso, foto de perfil) en un solo archivo.
    
    Retorna los documentos encontrados y los datos extraídos del DNI frontal.
    Útil cuando el alumno sube una foto donde se ven todos los documentos juntos,
    o un PDF multi-página con cada documento en una página diferente.
    """
    allowed_extensions = {".jpg", ".jpeg", ".png", ".pdf"}
    filename = file.filename
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de archivo no permitido. Solo se aceptan imágenes JPG, PNG y PDFs."
        )

    temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legajos", "temp"))
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"temp_composite_{random.randint(1000, 9999)}{ext}")

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        result = OCRService.analyze_composite_file(temp_path)

        return {
            "documents": result.get("documents", []),
            "dni_data": result.get("dni_data"),
            "confidence": result.get("confidence", 0.0),
            "needs_manual_review": result.get("needs_manual_review", True),
            "error": result.get("error"),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar el archivo compuesto: {str(e)}"
        )
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
