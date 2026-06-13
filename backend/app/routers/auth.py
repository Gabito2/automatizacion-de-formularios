import os
import shutil
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
    Recibe una imagen de DNI (frente) y extrae sus datos
    (DNI, Nombre, Apellido, Fecha de Nacimiento) mediante OCR.
    """
    allowed_extensions = {".jpg", ".jpeg", ".png"}
    filename = file.filename
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de archivo no permitido. Solo se aceptan imágenes JPG y PNG para procesamiento OCR directo."
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
        # Limpiar también la imagen preprocesada si se generó
        prep_path = temp_path.replace(".", "_preprocessed.")
        if os.path.exists(prep_path):
            os.remove(prep_path)

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
    dni_frente: UploadFile = File(...),
    dni_dorso: UploadFile = File(...),
    foto_persona: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Registra/preinscribe un nuevo estudiante.
    Realiza detección facial en la foto personal y validación OCR en el DNI frontal.
    """
    # 1. Verificar si el DNI ya existe
    existing_user = db.query(Usuario).filter(Usuario.dni == dni).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El número de DNI ingresado ya se encuentra registrado."
        )

    # 2. Validar extensiones de archivo
    allowed_extensions = {".jpg", ".jpeg", ".png"}
    for file_item, label in [(dni_frente, "DNI Frente"), (dni_dorso, "DNI Dorso"), (foto_persona, "Foto Personal")]:
        _, ext = os.path.splitext(file_item.filename)
        ext = ext.lower()
        if label == "Foto Personal" and ext not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La foto personal debe ser una imagen (.jpg, .jpeg, .png) para realizar la detección facial."
            )
        # Para DNI, también se admite PDF en otros flujos, pero para OCR directo de imagen necesitamos imagen
        if ext not in {".pdf", ".jpg", ".jpeg", ".png"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Formato no permitido para {label}. Solo se aceptan PDFs e imágenes."
            )

    # 3. Guardar archivos temporalmente en el legajo antes de validar
    try:
        saved_frente = save_document_file(carrera, dni, "dni_frente", dni_frente)
        saved_dorso = save_document_file(carrera, dni, "dni_dorso", dni_dorso)
        saved_persona = save_document_file(carrera, dni, "foto_4x4", foto_persona)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar los archivos de la preinscripción: {str(e)}"
        )

    # Obtener rutas físicas absolutas para procesamiento
    absolute_frente = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", saved_frente))
    absolute_persona = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", saved_persona))
    user_dir = os.path.dirname(absolute_frente)

    # 4. Validación Facial en la foto personal (Selfie)
    # Debe ser una imagen para poder correr la detección facial
    _, persona_ext = os.path.splitext(foto_persona.filename)
    if persona_ext.lower() in allowed_extensions:
        face_check = FaceService.detect_face(absolute_persona)
        if not face_check.get("has_face"):
            # Limpieza de archivos cargados por error
            if os.path.exists(user_dir):
                shutil.rmtree(user_dir)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Detección facial fallida: No se encontró un rostro humano visible en la foto de perfil subida."
            )

    # 5. Validación OCR del DNI Frente
    # Debe ser una imagen para procesar con OCR de OpenCV
    _, frente_ext = os.path.splitext(dni_frente.filename)
    ocr_results = None
    if frente_ext.lower() in allowed_extensions:
        user_info = {
            "dni": dni,
            "nombre": nombre,
            "apellido": apellido,
            "fecha_nacimiento": fecha_nacimiento
        }
        try:
            extracted_text, quality_report = OCRService.extract_text(absolute_frente, user_info)
            ocr_results = OCRService.validate_dni_data(extracted_text, user_info)
            
            # Verificar si coincide el número de DNI
            if not ocr_results.get("dni_match"):
                if os.path.exists(user_dir):
                    shutil.rmtree(user_dir)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="El DNI extraído del documento frontal no coincide con el DNI ingresado en el formulario."
                )
        except HTTPException:
            raise
        except Exception as e:
            # En caso de error crítico de OCR (por ejemplo, Tesseract roto), dejamos registrar si la foto de persona es válida
            pass

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
        doc_frente = Documento(
            usuario_id=new_user.id,
            tipo_documento="dni_frente",
            archivo_url=saved_frente,
            estado="aprobado" if (ocr_results and ocr_results.get("overall_match")) else "pendiente"
        )
        db.add(doc_frente)

        doc_dorso = Documento(
            usuario_id=new_user.id,
            tipo_documento="dni_dorso",
            archivo_url=saved_dorso,
            estado="pendiente"
        )
        db.add(doc_dorso)

        doc_persona = Documento(
            usuario_id=new_user.id,
            tipo_documento="foto_4x4",
            archivo_url=saved_persona,
            estado="aprobado"  # validado previamente en la detección facial
        )
        db.add(doc_persona)

        db.commit()
        return {"message": "Preinscripción realizada con éxito. Ahora puede iniciar sesión con su DNI y contraseña."}

    except Exception as ex:
        db.rollback()
        # Limpiar archivos si falló la base de datos
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al registrar la preinscripción en el sistema: {str(ex)}"
        )
