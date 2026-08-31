import os
import re
import logging
import io
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from sqlalchemy.orm import joinedload
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

class ObservacionMasivaSchema(BaseModel):
    mensaje: str
    destino: str  # "todos", "deudores", "especifico"
    usuario_id: int | None = None  # Solo requerido cuando destino == "especifico"

class RegistroIndividualSchema(BaseModel):
    dni: str
    nombre: str
    apellido: str
    email: str
    carrera: str
    telefono: str | None = None
    direccion: str | None = None
    localidad: str | None = None
    provincia: str | None = None
    fecha_nacimiento: str | None = None

@router.post("/registrar-estudiante")
def registrar_estudiante_individual(
    data: RegistroIndividualSchema,
    background_tasks: BackgroundTasks,
    current_admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Registra un estudiante de forma individual desde el panel de administración.
    La contraseña por defecto es el DNI del estudiante.
    """
    # Validar DNI
    dni_limpio = re.sub(r'\D', '', data.dni)
    if not dni_limpio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El DNI ingresado no es válido."
        )

    # Verificar si el DNI ya existe
    existing_user = db.query(Usuario).filter(Usuario.dni == dni_limpio).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El número de DNI ingresado ya se encuentra registrado."
        )

    # Verificar si el email ya está en uso
    existing_email = db.query(Usuario).filter(Usuario.email == data.email.strip()).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ingresado ya se encuentra registrado."
        )

    # Crear usuario
    temp_pass = dni_limpio
    new_user = Usuario(
        dni=dni_limpio,
        nombre=data.nombre.strip(),
        apellido=data.apellido.strip(),
        email=data.email.strip(),
        password_hash=get_password_hash(temp_pass),
        rol="estudiante",
        activo=True,
        primer_ingreso=False,
        carrera=data.carrera.strip(),
        sede="Sede Los Sarmientos"
    )
    db.add(new_user)

    # Crear datos personales si se proporcionaron (en la misma transacción)
    if data.telefono or data.direccion or data.localidad:
        datos_pers = DatosPersonales(
            usuario_id=new_user.id,
            telefono=data.telefono,
            direccion=data.direccion,
            localidad=data.localidad,
            provincia=data.provincia,
            fecha_nacimiento=data.fecha_nacimiento,
            secundario_completo=False,
            titulo_secundario=""
        )
        db.add(datos_pers)

    db.commit()
    db.refresh(new_user)

    # Enviar correo de notificación
    EmailService.send_account_created(
        background_tasks=background_tasks,
        to_email=data.email.strip(),
        nombre=f"{data.nombre.strip()} {data.apellido.strip()}",
        dni=dni_limpio,
        temp_password=temp_pass
    )

    return {
        "message": f"Estudiante {data.nombre} {data.apellido} registrado exitosamente. La contraseña por defecto es el DNI: {dni_limpio}",
        "usuario_id": new_user.id
    }


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
    required_cols = {"nombre", "apellido", "dni", "email", "carrera"}
    df.columns = [col.lower().strip() for col in df.columns]
    
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El archivo no contiene las columnas requeridas: {', '.join(missing_cols)}"
        )
        
    # --- Fase 1: Validar y preparar TODOS los usuarios en memoria ---
    # Esto evita 150+ queries individuales a la DB y 150+ commits.
    usuarios_a_crear = []  # Lista de dicts con datos + temp_pass
    emails_a_enviar = []   # Lista de (email, nombre, dni, temp_pass) para envío async
    errores = []

    # Precargar DNIs existentes en un set para verificación O(1)
    dnis_existentes = {u.dni for u in db.query(Usuario.dni).all()}

    for idx, row in df.iterrows():
        try:
            dni_raw = row['dni']
            if isinstance(dni_raw, float) and dni_raw.is_integer():
                dni_raw = int(dni_raw)
            elif pd.isna(dni_raw):
                dni_raw = ""
            dni = re.sub(r'\D', '', str(dni_raw))
            email = str(row['email']).strip()
            nombre = str(row['nombre']).strip()
            apellido = str(row['apellido']).strip()
            carrera = str(row['carrera']).strip()
            sede = "Sede Los Sarmientos"

            if not dni or not email or not nombre or not apellido:
                errores.append(f"Fila {idx+2}: Faltan campos obligatorios (DNI, Nombre, Apellido, Email).")
                continue

            if dni in dnis_existentes:
                errores.append(f"Fila {idx+2}: El DNI {dni} ya se encuentra registrado.")
                continue

            # La contraseña por defecto es el mismo DNI del estudiante
            usuarios_a_crear.append({
                "dni": dni, "nombre": nombre, "apellido": apellido,
                "email": email, "carrera": carrera, "sede": sede,
                "temp_pass": dni,
            })
            emails_a_enviar.append((email, f"{nombre} {apellido}", dni, dni))
            dnis_existentes.add(dni)  # Evitar duplicados dentro del mismo CSV
        except Exception as ex:
            errores.append(f"Fila {idx+2}: Error inesperado: {str(ex)}")

    # --- Fase 2: Insertar todos los usuarios de una sola vez ---
    creados = 0
    if usuarios_a_crear:
        try:
            # Crear objetos Usuario y agregar todos de golpe
            nuevos_usuarios = []
            for u in usuarios_a_crear:
                user = Usuario(
                    dni=u["dni"],
                    nombre=u["nombre"],
                    apellido=u["apellido"],
                    email=u["email"],
                    password_hash=get_password_hash(u["temp_pass"]),
                    rol="estudiante",
                    activo=True,
                    primer_ingreso=False,
                    carrera=u["carrera"],
                    sede=u["sede"]
                )
                nuevos_usuarios.append(user)

            db.add_all(nuevos_usuarios)
            db.commit()
            creados = len(nuevos_usuarios)
        except Exception as ex:
            db.rollback()
            errores.append(f"Error al insertar en lote: {str(ex)}")
            creados = 0

    # --- Fase 3: Enviar correos en background (no bloquea la respuesta) ---
    for email, nombre, dni, temp_pass in emails_a_enviar:
        EmailService.send_account_created(
            background_tasks=background_tasks,
            to_email=email,
            nombre=nombre,
            dni=dni,
            temp_password=temp_pass
        )

    return {
        "message": f"Importación finalizada. {creados} estudiantes creados exitosamente.",
        "creados": creados,
        "errores": errores
    }

@router.get("/stats")
def get_stats(
    current_validator: Usuario = Depends(get_current_validator),
    db: Session = Depends(get_db)
):
    """
    Retorna estadísticas globales del dashboard (total, aprobados, observados, pendientes, incompletos)
    en una sola query. Evita que el frontend haga una segunda llamada a /legajos sin filtros.
    """
    # Obtener todos los estudiantes con documentos eager-loaded
    students = (
        db.query(Usuario)
        .options(joinedload(Usuario.documentos))
        .filter(Usuario.rol == "estudiante")
        .all()
    )
    
    tipos_obligatorios = [
        "dni_frente", "dni_dorso", "foto_4x4",
        "analitico_secundario", "partida_nacimiento", "formulario_inscripcion"
    ]
    
    total = len(students)
    aprobados = 0
    observados = 0
    pendientes = 0
    incompletos = 0
    
    for s in students:
        docs = s.documentos
        docs_uploaded = {doc.tipo_documento for doc in docs}
        todo_subido = all(t in docs_uploaded for t in tipos_obligatorios)
        estados_cargados = [doc.estado for doc in docs]
        
        if "rechazado" in estados_cargados or "observado" in estados_cargados:
            observados += 1
        elif not todo_subido:
            incompletos += 1
        elif "pendiente" in estados_cargados:
            pendientes += 1
        else:
            aprobados += 1
    
    return {
        "total": total,
        "aprobados": aprobados,
        "observados": observados,
        "pendientes": pendientes,
        "incompletos": incompletos
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
    # Consulta base para estudiantes con eager loading de documentos y datos_personales
    q = (
        db.query(Usuario)
        .options(joinedload(Usuario.documentos), joinedload(Usuario.datos_personales))
        .filter(Usuario.rol == "estudiante")
    )
    
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
        
        # Calcular estado general del legajo.
        # "todo_subido" verifica que estén presentes TODOS los tipos obligatorios,
        # no que la cantidad de archivos coincida (un documento extra rompía el conteo).
        todo_subido = all(tipo in docs_uploaded for tipo in tipos_obligatorios)
        estados_cargados = [doc.estado for doc in docs]
        
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
    # Verificar que estén todos los obligatorios y que estén aprobados
    tipos_presentes = {d.tipo_documento for d in all_docs}
    obligatorios_aprobados = [
        d for d in all_docs if d.tipo_documento in tipos_obligatorios and d.estado == "aprobado"
    ]
    todo_aprobado = (
        all(t in tipos_presentes for t in tipos_obligatorios)
        and len(obligatorios_aprobados) == len(tipos_obligatorios)
    )
    
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

@router.post("/enviar-observacion")
def enviar_observacion(
    data: ObservacionMasivaSchema,
    background_tasks: BackgroundTasks,
    current_admin: Usuario = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Envía una observación/comunicación general a estudiantes.
    - destino='todos': a todos los estudiantes activos.
    - destino='deudores': a estudiantes con legajo incompleto o con documentos observados.
    - destino='especifico': solo al estudiante con usuario_id indicado.
    """
    if not data.mensaje or not data.mensaje.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El mensaje de observación no puede estar vacío."
        )

    # Construir query base: solo estudiantes activos
    q = db.query(Usuario).filter(Usuario.rol == "estudiante", Usuario.activo == True)

    tipos_obligatorios = [
        "dni_frente", "dni_dorso", "foto_4x4",
        "analitico_secundario", "partida_nacimiento", "formulario_inscripcion"
    ]

    if data.destino == "especifico":
        if not data.usuario_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe especificar el usuario_id para envío a un estudiante específico."
            )
        target_user = db.query(Usuario).filter(
            Usuario.id == data.usuario_id,
            Usuario.rol == "estudiante"
        ).first()
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Estudiante no encontrado."
            )
        estudiantes = [target_user]

    elif data.destino == "deudores":
        all_students = q.all()
        estudiantes = []
        for s in all_students:
            docs = s.documentos
            docs_map = {d.tipo_documento for d in docs}
            # Incompleto: le faltan documentos obligatorios
            falta_docs = not all(t in docs_map for t in tipos_obligatorios)
            # Con documentos observados
            tiene_obs = any(d.estado == "observado" for d in docs)
            if falta_docs or tiene_obs:
                estudiantes.append(s)

    elif data.destino == "todos":
        estudiantes = q.all()

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Destino no válido. Use 'todos', 'deudores' o 'especifico'."
        )

    if not estudiantes:
        return {
            "message": "No se encontraron estudiantes que cumplan con el criterio seleccionado.",
            "enviados": 0
        }

    # Enviar correos y registrar observación en la DB para cada estudiante
    enviados = 0
    for est in estudiantes:
        # Registrar observación general en la tabla observaciones (ligada al usuario)
        obs = Observacion(
            usuario_id=est.id,
            documento_id=None,  # Observación general, no asociada a un documento específico
            mensaje=f"[Observación General] {data.mensaje.strip()}"
        )
        db.add(obs)

        # Enviar correo de notificación
        EmailService.send_general_observation(
            background_tasks=background_tasks,
            to_email=est.email,
            nombre=f"{est.nombre} {est.apellido}",
            observacion=data.mensaje.strip()
        )
        enviados += 1

    db.commit()

    return {
        "message": f"Observación enviada exitosamente a {enviados} estudiante(s).",
        "enviados": enviados
    }
