import os
import re
import logging
import io
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.models import Usuario, DatosPersonales, Documento, Observacion
from app.utils.dependencies import get_current_admin, get_current_validator
from app.utils.security import get_password_hash
from app.routers.auth import generate_temp_password
from app.services.email_service import EmailService

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("AdminRouter")

class RechazoSchema(BaseModel):
    mensaje: str

@router.post("/importar-estudiantes")
def importar_estudiantes(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Importa masivamente estudiantes desde un archivo Excel (XLSX) o CSV.
    Crea usuarios con contraseñas temporales y les envía correos electrónicos.
    """
    filename = file.filename
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    if ext not in [".csv", ".xlsx", ".xls"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de archivo no soportado. Debe ser CSV o Excel (XLSX/XLS)."
        )
        
    try:
        # Leer archivo usando pandas
        contents = file.file.read()
        if ext == ".csv":
            # Intentar decodificar como UTF-8 o latin-1 y auto-detectar separador
            try:
                df = pd.read_csv(io.BytesIO(contents), sep=None, engine='python', encoding='utf-8')
            except Exception:
                df = pd.read_csv(io.BytesIO(contents), sep=None, engine='python', encoding='latin-1')
        else:
            df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al leer el archivo estructurado: {str(e)}"
        )
        
    # Validar columnas requeridas
    required_cols = {"nombre", "apellido", "dni", "email", "carrera", "sede"}
    df.columns = [col.lower().strip() for col in df.columns]
    
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo no contiene las columnas requeridas: {', '.join(missing_cols)}"
        )
        
    creados = 0
    errores = []
    
    for idx, row in df.iterrows():
        try:
            # Sanitizar valores de la fila
            dni_raw = str(row['dni']).split('.')[0].strip()  # Evitar que floats de excel pongan decimales
            # Eliminar espacios extras del DNI
            dni = re.sub(r'\D', '', dni_raw)
            email = str(row['email']).strip()
            nombre = str(row['nombre']).strip()
            apellido = str(row['apellido']).strip()
            carrera = str(row['carrera']).strip()
            sede = str(row['sede']).strip()
            
            if not dni or not email or not nombre or not apellido:
                errores.append(f"Fila {idx+2}: Faltan campos obligatorios (DNI, Nombre, Apellido, Email).")
                continue
                
            # Verificar si ya existe
            user_exists = db.query(Usuario).filter(Usuario.dni == dni).first()
            if user_exists:
                errores.append(f"Fila {idx+2}: El DNI {dni} ya se encuentra registrado.")
                continue
                
            # Crear usuario estudiante
            temp_pass = generate_temp_password()
            new_user = Usuario(
                dni=dni,
                nombre=nombre,
                apellido=apellido,
                email=email,
                password_hash=get_password_hash(temp_pass),
                rol="estudiante",
                activo=True,
                primer_ingreso=True,
                carrera=carrera,
                sede=sede
            )
            db.add(new_user)
            db.commit()
            
            # Enviar correo de bienvenida
            EmailService.send_account_created(
                background_tasks=background_tasks,
                to_email=email,
                nombre=f"{nombre} {apellido}",
                dni=dni,
                temp_password=temp_pass
            )
            
            creados += 1
        except Exception as ex:
            db.rollback()
            errores.append(f"Fila {idx+2}: Error inesperado: {str(ex)}")
            
    return {
        "message": f"Importación finalizada. {creados} estudiantes creados exitosamente.",
        "creados": creados,
        "errores": errores
    }

@router.get("/legajos")
def get_legajos(
    carrera: str = None,
    estado: str = None,
    query: str = None,
    current_validator: Usuario = Depends(get_current_validator),
    db: Session = Depends(get_db)
):
    """
    Obtiene el listado de legajos de estudiantes con filtros avanzados.
    Permite filtrar por carrera, estado general y búsqueda libre (DNI, nombre o apellido).
    """
    # Consulta base para estudiantes
    q = db.query(Usuario).filter(Usuario.rol == "estudiante")
    
    if carrera:
        q = q.filter(Usuario.carrera == carrera)
        
    if query:
        search = f"%{query}%"
        q = q.filter((Usuario.dni.like(search)) | (Usuario.nombre.like(search)) | (Usuario.apellido.like(search)))
        
    students = q.all()
    
    legajos_reporte = []
    tipos_obligatorios = [
        "dni_frente", "dni_dorso", "foto_4x4", 
        "analitico_secundario", "partida_nacimiento", "formulario_inscripcion"
    ]
    
    for s in students:
        docs = s.documentos
        docs_uploaded = {doc.tipo_documento: doc for doc in docs}
        
        # Calcular estado general del legajo
        estados_cargados = [doc.estado for doc in docs]
        todo_subido = len(docs) == len(tipos_obligatorios)
        
        if "rechazado" in estados_cargados or "observado" in estados_cargados:
            estado_general = "observado"
        elif not todo_subido:
            estado_general = "incompleto"
        elif "pendiente" in estados_cargados:
            estado_general = "pendiente"
        else:
            estado_general = "aprobado"
            
        # Filtrar por estado general si se requiere
        if estado and estado_general != estado:
            continue
            
        legajos_reporte.append({
            "usuario_id": s.id,
            "dni": s.dni,
            "nombre": s.nombre,
            "apellido": s.apellido,
            "email": s.email,
            "carrera": s.carrera,
            "sede": s.sede,
            "estado_general": estado_general,
            "total_documentos": len(docs),
            "tiene_datos_personales": s.datos_personales is not None,
            "documentos": [
                {
                    "id": d.id,
                    "tipo_documento": d.tipo_documento,
                    "archivo_url": d.archivo_url,
                    "estado": d.estado,
                    "observacion": d.observacion,
                    "fecha_subida": d.fecha_subida
                } for d in docs
            ],
            "datos_personales": {
                "telefono": s.datos_personales.telefono,
                "direccion": s.datos_personales.direccion,
                "localidad": s.datos_personales.localidad,
                "provincia": s.datos_personales.provincia,
                "fecha_nacimiento": s.datos_personales.fecha_nacimiento,
                "secundario_completo": s.datos_personales.secundario_completo,
                "titulo_secundario": s.datos_personales.titulo_secundario
            } if s.datos_personales else None
        })
        
    return legajos_reporte

@router.put("/documento/{id}/aprobar")
def aprobar_documento(
    id: int,
    background_tasks: BackgroundTasks,
    current_validator: Usuario = Depends(get_current_validator),
    db: Session = Depends(get_db)
):
    """Aprueba un documento específico y verifica si completa el legajo total."""
    doc = db.query(Documento).filter(Documento.id == id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
        
    doc.estado = "aprobado"
    doc.observacion = None
    db.commit()
    
    # Verificar si el legajo está completo y aprobado al 100%
    student = doc.usuario
    tipos_obligatorios = [
        "dni_frente", "dni_dorso", "foto_4x4", 
        "analitico_secundario", "partida_nacimiento", "formulario_inscripcion"
    ]
    
    all_docs = student.documentos
    todo_aprobado = len(all_docs) == len(tipos_obligatorios) and all(d.estado == "aprobado" for d in all_docs)
    
    if todo_aprobado:
        # Notificar al estudiante que su legajo ha sido aprobado completamente
        EmailService.send_legajo_approved(
            background_tasks=background_tasks,
            to_email=student.email,
            nombre=f"{student.nombre} {student.apellido}"
        )
        
    return {"message": "Documento aprobado correctamente", "todo_aprobado": todo_aprobado}

@router.put("/documento/{id}/rechazar")
def rechazar_documento(
    id: int,
    data: RechazoSchema,
    background_tasks: BackgroundTasks,
    current_validator: Usuario = Depends(get_current_validator),
    db: Session = Depends(get_db)
):
    """Rechaza / observa un documento específico adjuntando el motivo."""
    doc = db.query(Documento).filter(Documento.id == id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
        
    doc.estado = "observado"
    doc.observacion = data.mensaje
    
    # Crear registro en el historial de observaciones
    obs = Observacion(
        documento_id=doc.id,
        mensaje=data.mensaje
    )
    db.add(obs)
    db.commit()
    
    # Notificar al estudiante por correo electrónico sobre el documento observado
    student = doc.usuario
    EmailService.send_document_observed(
        background_tasks=background_tasks,
        to_email=student.email,
        nombre=f"{student.nombre} {student.apellido}",
        tipo_doc=doc.tipo_documento,
        observacion=data.mensaje
    )
    
    return {"message": "Documento observado/rechazado e historial registrado correctamente"}
