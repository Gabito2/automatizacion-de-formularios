import sys
import os
# Asegurar que el directorio base 'backend' esté en el path para resolver la importación de 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import engine, Base, SessionLocal
from app.models.models import Usuario
from app.utils.security import get_password_hash
from app.routers import auth, estudiante, admin

# Crear las tablas de la base de datos al iniciar si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sistema de Legajos Digitales UNdeC",
    description="API para la gestión y validación asistida de legajos de estudiantes preinscriptos.",
    version="1.0.0"
)

# Configurar CORS para permitir comunicación con el frontend de React
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, restringir a los dominios autorizados
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Asegurar que el directorio de legajos existe
LEGAJOS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "legajos"))
os.makedirs(LEGAJOS_DIR, exist_ok=True)

# Montar carpeta de legajos como recursos estáticos
app.mount("/legajos", StaticFiles(directory=LEGAJOS_DIR), name="legajos")

# Registrar Routers
app.include_router(auth.router)
app.include_router(estudiante.router)
app.include_router(admin.router)

# Evento de inicio: Semilla para crear el usuario administrador por defecto
@app.on_event("startup")
def seed_admin_user():
    db: Session = SessionLocal()
    try:
        # Verificar si ya existe un administrador
        admin_user = db.query(Usuario).filter(Usuario.rol == "administrador").first()
        if not admin_user:
            # Crear administrador inicial por defecto
            default_admin = Usuario(
                dni="10000000",
                nombre="Administrador",
                apellido="Institucional",
                email="admin@undec.edu.ar",
                password_hash=get_password_hash("admin123"),
                rol="administrador",
                activo=True,
                primer_ingreso=False,  # No forzar cambio al admin inicial
                carrera="Administración Central",
                sede="Sede Los Sarmientos"
            )
            db.add(default_admin)
            db.commit()
            print("=========================================================")
            print("SEMILLA: Usuario administrador inicial creado con éxito.")
            print("DNI (Usuario): 10000000")
            print("Contraseña: admin123")
            print("=========================================================")
    except Exception as e:
        print(f"Error al sembrar usuario administrador: {str(e)}")
    finally:
        db.close()

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "UNdeC Legajos Digitales API",
        "documentation": "/docs"
    }
