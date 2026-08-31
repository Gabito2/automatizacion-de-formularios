import os
import base64
import random
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from sqlalchemy.orm import joinedload
from app.database import get_db
from app.models.models import Usuario, DatosPersonales, Documento, Observacion
from app.utils.dependencies import get_current_student
from app.utils.file_manager import save_document_file
from app.services.ocr_service import OCRService

router = APIRouter(prefix="/estudiante", tags=["estudiante"])
logger = logging.getLogger("EstudianteRouter")

# Tipos de documento válidos del legajo. Se valida estrictamente para evitar
# path traversal cuando el valor de tipo_documento se usa en rutas/nombres de archivo.
TIPOS_DOCUMENTO_VALIDOS = {
    "dni_frente", "dni_dorso", "foto_4x4",
    "analitico_secundario", "partida_nacimiento", "formulario_inscripcion",
}

class ImageBase64Request(BaseModel):
    tipo_documento: str
    image_base64: str  # Imagen codificada en base64
    filename: str = "camara.jpg"

class DatosPersonalesSchema(BaseModel):
    telefono: str
    direccion: str
    localidad: str
    provincia: str
    fecha_nacimiento: str  # YYYY-MM-DD
    secundario_completo: bool
    titulo_secundario: str

@router.get("/datos-personales")
def get_datos_personales(
    current_student: Usuario = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """Obtiene los datos personales del estudiante autenticado."""
    datos = current_student.datos_personales
    if not datos:
        return {}
    return {
        "telefono": datos.telefono,
        "direccion": datos.direccion,
        "localidad": datos.localidad,
        "provincia": datos.provincia,
        "fecha_nacimiento": datos.fecha_nacimiento,
        "secundario_completo": datos.secundario_completo,
        "titulo_secundario": datos.titulo_secundario
    }

@router.post("/datos-personales")
def save_datos_personales(
    datos_in: DatosPersonalesSchema,
    current_student: Usuario = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """Guarda o actualiza los datos personales del estudiante."""
    datos = current_student.datos_personales
    if not datos:
        datos = DatosPersonales(usuario_id=current_student.id)
        db.add(datos)
        
    datos.telefono = datos_in.telefono
    datos.direccion = datos_in.direccion
    datos.localidad = datos_in.localidad
    datos.provincia = datos_in.provincia
    datos.fecha_nacimiento = datos_in.fecha_nacimiento
    datos.secundario_completo = datos_in.secundario_completo
    datos.titulo_secundario = datos_in.titulo_secundario
    
    db.commit()
    return {"message": "Datos personales actualizados exitosamente"}

class ActualizarDatosDniSchema(BaseModel):
    dni: str
    nombre: str
    apellido: str
    fecha_nacimiento: str  # YYYY-MM-DD

@router.post("/actualizar-datos-dni")
def actualizar_datos_dni(
    datos_in: ActualizarDatosDniSchema,
    current_student: Usuario = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    Permite al estudiante corregir sus datos de identidad (DNI, nombre, apellido, fecha de nacimiento)
    si los ingresados originalmente estaban mal tras validarlos con el OCR.
    Luego de la modificación, si ya existía un DNI frente subido, se re-evalúa la validación.
    """
    # 1. Verificar si el DNI cambió y si el nuevo ya existe
    if datos_in.dni != current_student.dni:
        existente = db.query(Usuario).filter(Usuario.dni == datos_in.dni).first()
        if existente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de DNI ingresado ya está registrado por otro estudiante."
            )
            
    # 2. Actualizar Usuario
    current_student.dni = datos_in.dni
    current_student.nombre = datos_in.nombre
    current_student.apellido = datos_in.apellido
    
    # 3. Actualizar Datos Personales (Fecha Nacimiento)
    datos = current_student.datos_personales
    if not datos:
        datos = DatosPersonales(usuario_id=current_student.id)
        db.add(datos)
    datos.fecha_nacimiento = datos_in.fecha_nacimiento
    
    db.commit()
    
    # 4. Re-evaluar OCR del DNI Frente si existe cargado
    dni_frente_doc = db.query(Documento).filter(
        Documento.usuario_id == current_student.id,
        Documento.tipo_documento == "dni_frente"
    ).first()
    
    if dni_frente_doc:
        # Resolver ruta física absoluta
        absolute_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", dni_frente_doc.archivo_url))
        _, ext = os.path.splitext(dni_frente_doc.archivo_url)
        is_image = ext.lower() in {".jpg", ".jpeg", ".png"}
        
        if is_image and os.path.exists(absolute_path):
            user_info = {
                "dni": current_student.dni,
                "nombre": current_student.nombre,
                "apellido": current_student.apellido,
                "fecha_nacimiento": current_student.datos_personales.fecha_nacimiento
            }
            try:
                extracted_text, quality_report = OCRService.extract_text(absolute_path, user_info)
                ocr_results = OCRService.validate_dni_data(extracted_text, user_info)
                
                # Eliminar observaciones antiguas asociadas a este documento que sean de validación automática
                db.query(Observacion).filter(
                    Observacion.documento_id == dni_frente_doc.id,
                    Observacion.mensaje.like("Validación automática:%")
                ).delete(synchronize_session=False)
                
                if quality_report.get("is_blurry") or quality_report.get("is_too_dark") or quality_report.get("is_too_bright"):
                    dni_frente_doc.estado = "observado"
                    dni_frente_doc.observacion = "El sistema detectó baja calidad de imagen (imagen borrosa o con iluminación deficiente). Por favor, cargue una imagen clara."
                    
                    obs = Observacion(
                        documento_id=dni_frente_doc.id,
                        mensaje="Validación automática: La imagen presenta baja legibilidad (borrosa o mala iluminación)."
                    )
                    db.add(obs)
                elif ocr_results:
                    if ocr_results.get("overall_match"):
                        dni_frente_doc.estado = "aprobado"
                        dni_frente_doc.observacion = None
                    elif not ocr_results.get("dni_match"):
                        dni_frente_doc.estado = "observado"
                        dni_frente_doc.observacion = "El DNI extraído del documento no coincide con el DNI declarado."
                        obs = Observacion(
                            documento_id=dni_frente_doc.id,
                            mensaje="Validación automática: El número de documento extraído por OCR no coincide con el declarado en la inscripción."
                        )
                        db.add(obs)
                    else:
                        # DNI coincide pero falta algún nombre/apellido (por ejemplo, pendiente)
                        dni_frente_doc.estado = "pendiente"
                        dni_frente_doc.observacion = None
                        
                db.commit()
            except Exception as e:
                # Si falla la re-validación, loguear para diagnóstico
                logger.warning(f"Error al re-evaluar OCR tras actualizar datos de DNI: {e}")

    return {
        "message": "Datos de identidad actualizados correctamente y validación de DNI re-evaluada.",
        "user": {
            "dni": current_student.dni,
            "nombre": current_student.nombre,
            "apellido": current_student.apellido,
            "fecha_nacimiento": current_student.datos_personales.fecha_nacimiento if current_student.datos_personales else None
        }
    }

@router.post("/documentos")
def upload_document(
    tipo_documento: str = Form(...),
    file: UploadFile = File(...),
    current_student: Usuario = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    Sube un documento obligatorio para la conformación del legajo digital.
    Realiza validaciones de tamaño y extensión, y ejecuta el OCR si es DNI.
    """
    # 0. Validar tipo de documento (evita path traversal al usarse en rutas)
    if tipo_documento not in TIPOS_DOCUMENTO_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de documento no válido."
        )

    # 1. Validaciones básicas de archivo
    allowed_extensions = {".pdf", ".jpg", ".jpeg", ".png"}
    filename = file.filename
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de archivo no permitido. Solo se aceptan archivos PDF, JPG y PNG."
        )
        
    # Validar tamaño (máximo 10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    # Para leer el tamaño sin consumir el stream de forma permanente, medimos y luego rebobinamos
    file_content = file.file.read()
    file_size = len(file_content)
    file.file.seek(0)  # Rebobinar stream
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo supera el tamaño máximo permitido de 10MB."
        )

    # 2. Guardar el archivo en la estructura de legajos institucional
    # Usamos los datos del usuario para el folder
    carrera = current_student.carrera or "sin_carrera"
    dni = current_student.dni
    
    try:
        saved_path = save_document_file(carrera, dni, tipo_documento, file)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar el archivo: {str(e)}"
        )

    # 3. Registrar o actualizar en la base de datos
    doc_record = db.query(Documento).filter(
        Documento.usuario_id == current_student.id,
        Documento.tipo_documento == tipo_documento
    ).first()
    
    if not doc_record:
        doc_record = Documento(
            usuario_id=current_student.id,
            tipo_documento=tipo_documento,
            archivo_url=saved_path,
            estado="pendiente"
        )
        db.add(doc_record)
    else:
        doc_record.archivo_url = saved_path
        doc_record.estado = "pendiente"
        doc_record.observacion = None  # Limpiar observaciones previas al subir nueva versión
        
    db.commit()
    db.refresh(doc_record)

    # 4. Procesamiento Inteligente / OCR (Solo para DNI frente — imágenes y PDFs)
    # DNI dorso y foto 4x4 se suben sin análisis.
    ocr_results = None
    quality_report = None
    ocr_extracted_fields = None
    
    isprocessable = ext in {".jpg", ".jpeg", ".png", ".pdf"}
    
    if tipo_documento == "dni_frente" and isprocessable:
        # Resolver ruta física absoluta
        absolute_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", saved_path))
        
        # Datos del estudiante para matching
        user_info = {
            "dni": current_student.dni,
            "nombre": current_student.nombre,
            "apellido": current_student.apellido,
            "fecha_nacimiento": current_student.datos_personales.fecha_nacimiento if current_student.datos_personales else None
        }
        
        try:
            extracted_text, quality_report = OCRService.extract_text_fast(absolute_path)

            # Validar coincidencia de datos
            ocr_results = OCRService.validate_dni_data(extracted_text, user_info)
            ocr_extracted_fields = OCRService.parse_dni_text(extracted_text)
        except Exception as e:
            logger.warning(f"Error en OCR al subir documento {tipo_documento}: {e}")
            quality_report = None
            ocr_results = None
            ocr_extracted_fields = None

        # Guardar resultados o reportar directo al estudiante
        # Si la calidad de imagen es pésima (ej: muy borroso o muy oscuro), podemos marcarlo de forma asistida
        if quality_report and (quality_report.get("is_blurry") or quality_report.get("is_too_dark") or quality_report.get("is_too_bright")):
            doc_record.estado = "observado"
            doc_record.observacion = "El sistema detectó baja calidad de imagen (imagen borrosa o con iluminación deficiente). Por favor, cargue una imagen clara."
            
            # Guardar observación en la tabla
            obs = Observacion(
                documento_id=doc_record.id,
                mensaje="Validación automática: La imagen presenta baja legibilidad (borrosa o mala iluminación)."
            )
            db.add(obs)
            db.commit()
        elif ocr_results and tipo_documento == "dni_frente":
            # Si el DNI no coincide en absoluto en el frente
            if not ocr_results.get("dni_match"):
                doc_record.estado = "observado"
                doc_record.observacion = "El DNI extraído del documento no coincide con el DNI declarado."
                obs = Observacion(
                    documento_id=doc_record.id,
                    mensaje="Validación automática: El número de documento extraído por OCR no coincide con el declarado en la inscripción."
                )
                db.add(obs)
                db.commit()
    
    return {
        "message": "Archivo cargado correctamente",
        "documento": {
            "id": doc_record.id,
            "tipo_documento": doc_record.tipo_documento,
            "archivo_url": doc_record.archivo_url,
            "estado": doc_record.estado,
            "observacion": doc_record.observacion,
            "fecha_subida": doc_record.fecha_subida
        },
        "ocr_analizado": ocr_results is not None,
        "ocr_resultados": ocr_results,
        "ocr_datos_extraidos": ocr_extracted_fields,
        "calidad_reporte": quality_report
    }

@router.get("/estado")
def get_estado_legajo(
    current_student: Usuario = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    Obtiene el estado de carga documental, las observaciones activas y el
    estado general del trámite del estudiante preinscripto.
    """
    docs = (
        db.query(Documento)
        .filter(Documento.usuario_id == current_student.id)
        .options(joinedload(Documento.observaciones))
        .all()
    )
    
    # Documentos obligatorios del legajo
    tipos_obligatorios = [
        "dni_frente", "dni_dorso", "foto_4x4", 
        "analitico_secundario", "partida_nacimiento", "formulario_inscripcion"
    ]
    
    docs_uploaded = {doc.tipo_documento: doc for doc in docs}
    
    # Armar reporte detallado
    reporte_docs = []
    for tipo in tipos_obligatorios:
        doc = docs_uploaded.get(tipo)
        if doc:
            reporte_docs.append({
                "tipo_documento": tipo,
                "cargado": True,
                "id": doc.id,
                "archivo_url": doc.archivo_url,
                "estado": doc.estado,
                "observacion": doc.observacion,
                "fecha_subida": doc.fecha_subida
            })
        else:
            reporte_docs.append({
                "tipo_documento": tipo,
                "cargado": False,
                "estado": "faltante"
            })
            
    # Determinar estado general del trámite
    # Si falta algún documento obligatorio -> "incompleto"
    # Si hay alguno observado/rechazado -> "observado"
    # Si están todos subidos pero hay pendientes -> "pendiente"
    # Si están todos aprobados -> "aprobado"
    
    estados_cargados = [doc.estado for doc in docs]
    # "todo_subido" verifica presencia de TODOS los tipos obligatorios, no el conteo.
    todo_subido = all(tipo in docs_uploaded for tipo in tipos_obligatorios)
    
    if "rechazado" in estados_cargados or "observado" in estados_cargados:
        estado_general = "observado"
    elif not todo_subido:
        estado_general = "incompleto"
    elif "pendiente" in estados_cargados:
        estado_general = "pendiente"
    else:
        estado_general = "aprobado"
        
    # Obtener observaciones de documentos (ligadas al estudiante)
    obs_docs = (
        db.query(Observacion)
        .join(Documento, Observacion.documento_id == Documento.id)
        .filter(Documento.usuario_id == current_student.id)
        .all()
    )

    # Obtener observaciones generales del admin (no ligadas a ningún documento)
    obs_generales = (
        db.query(Observacion)
        .filter(
            Observacion.usuario_id == current_student.id,
            Observacion.documento_id == None
        )
        .all()
    )

    # Unificar y ordenar por fecha descendente
    todas_observaciones = obs_docs + obs_generales
    todas_observaciones.sort(key=lambda o: o.fecha or datetime.min, reverse=True)

    reporte_observaciones = []
    for obs in todas_observaciones:
        item = {
            "id": obs.id,
            "documento_id": obs.documento_id,
            "mensaje": obs.mensaje,
            "fecha": obs.fecha,
        }
        if obs.documento_id and obs.documento:
            item["tipo_documento"] = obs.documento.tipo_documento
        else:
            item["tipo_documento"] = "general"
        reporte_observaciones.append(item)
    
    # Validar si tiene completo el formulario de datos personales
    tiene_datos_personales = current_student.datos_personales is not None
    
    return {
        "dni": current_student.dni,
        "nombre": current_student.nombre,
        "apellido": current_student.apellido,
        "carrera": current_student.carrera,
        "sede": current_student.sede,
        "datos_personales_completos": tiene_datos_personales,
        "estado_general": estado_general,
        "documentos": reporte_docs,
        "observaciones": reporte_observaciones
    }


@router.post("/documentos-camara")
def upload_document_camara(
    data: ImageBase64Request,
    current_student: Usuario = Depends(get_current_student),
    db: Session = Depends(get_db)
):
    """
    Sube un documento desde captura de cámara (imagen base64).
    El procesamiento de OCR y guardado es idéntico al endpoint de subida de archivo.
    """
    tipo_documento = data.tipo_documento

    # Validar tipo de documento (evita path traversal al usarse en rutas)
    if tipo_documento not in TIPOS_DOCUMENTO_VALIDOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tipo de documento no válido."
        )

    allowed_extensions = {".jpg", ".jpeg", ".png"}
    _, ext = os.path.splitext(data.filename)
    ext = ext.lower() or ".jpg"

    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan imágenes JPG y PNG desde cámara."
        )

    # Decodificar base64
    try:
        raw_b64 = data.image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        file_content = base64.b64decode(raw_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La imagen base64 recibida no tiene un formato válido."
        )

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    if len(file_content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo supera el tamaño máximo permitido de 10MB."
        )

    # Guardar archivo en el sistema de legajos
    carrera = current_student.carrera or "sin_carrera"
    dni = current_student.dni

    legajos_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "legajos"))
    student_dir = os.path.join(legajos_dir, carrera, dni)
    os.makedirs(student_dir, exist_ok=True)
    safe_tipo = tipo_documento.replace("/", "_")
    filename_out = f"{safe_tipo}{ext}"
    saved_full_path = os.path.join(student_dir, filename_out)

    try:
        with open(saved_full_path, "wb") as f:
            f.write(file_content)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar el archivo: {str(e)}"
        )

    # Ruta relativa para guardar en BD (igual que save_document_file)
    saved_path = os.path.join("legajos", carrera, dni, filename_out)

    # Registrar o actualizar en la base de datos
    doc_record = db.query(Documento).filter(
        Documento.usuario_id == current_student.id,
        Documento.tipo_documento == tipo_documento
    ).first()

    if not doc_record:
        doc_record = Documento(
            usuario_id=current_student.id,
            tipo_documento=tipo_documento,
            archivo_url=saved_path,
            estado="pendiente"
        )
        db.add(doc_record)
    else:
        doc_record.archivo_url = saved_path
        doc_record.estado = "pendiente"
        doc_record.observacion = None

    db.commit()
    db.refresh(doc_record)

    # Procesamiento OCR (solo para DNI frente)
    ocr_results = None
    quality_report = None
    ocr_extracted_fields = None

    if tipo_documento == "dni_frente":
        absolute_path = saved_full_path
        user_info = {
            "dni": current_student.dni,
            "nombre": current_student.nombre,
            "apellido": current_student.apellido,
            "fecha_nacimiento": current_student.datos_personales.fecha_nacimiento if current_student.datos_personales else None
        }
        try:
            extracted_text, quality_report = OCRService.extract_text(absolute_path, user_info)
            ocr_results = OCRService.validate_dni_data(extracted_text, user_info)
            ocr_extracted_fields = OCRService.parse_dni_text(extracted_text)
        except Exception as e:
            logger.warning(f"Error en OCR al subir documento de cámara {tipo_documento}: {e}")
            quality_report = None
            ocr_results = None
            ocr_extracted_fields = None

        if quality_report and (quality_report.get("is_blurry") or quality_report.get("is_too_dark") or quality_report.get("is_too_bright")):
            doc_record.estado = "observado"
            doc_record.observacion = "El sistema detectó baja calidad de imagen. Por favor, capture una imagen más clara."
            obs = Observacion(
                documento_id=doc_record.id,
                mensaje="Validación automática: La imagen capturada presenta baja legibilidad."
            )
            db.add(obs)
            db.commit()
        elif ocr_results and tipo_documento == "dni_frente":
            if not ocr_results.get("dni_match"):
                doc_record.estado = "observado"
                doc_record.observacion = "El DNI extraído del documento no coincide con el DNI declarado."
                obs = Observacion(
                    documento_id=doc_record.id,
                    mensaje="Validación automática: El número de documento extraído por OCR no coincide con el declarado."
                )
                db.add(obs)
                db.commit()

    return {
        "message": "Imagen de cámara cargada correctamente",
        "documento": {
            "id": doc_record.id,
            "tipo_documento": doc_record.tipo_documento,
            "archivo_url": doc_record.archivo_url,
            "estado": doc_record.estado,
            "observacion": doc_record.observacion,
            "fecha_subida": doc_record.fecha_subida
        },
        "ocr_analizado": ocr_results is not None,
        "ocr_resultados": ocr_results,
        "ocr_datos_extraidos": ocr_extracted_fields,
        "calidad_reporte": quality_report
    }
