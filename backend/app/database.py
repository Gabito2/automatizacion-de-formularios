import os
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Ruta de la base de datos SQLite.
# Ruta ABSOLUTA para que no dependa del directorio desde donde se lanza el servidor
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = "sqlite:///" + os.path.join(_BACKEND_DIR, "..", "legajos.db").replace("\\", "/")

# Crear motor de base de datos con pragmas de rendimiento para SQLite
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# --- Tuning de SQLite para rendimiento ---
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    # WAL permite lecturas concurrentes y escrituras más rápidas
    cursor.execute("PRAGMA journal_mode=WAL")
    # Aumentar cache a 64MB (default ~2MB)
    cursor.execute("PRAGMA cache_size=-65536")
    # Sincronización reducida (seguro con WAL)
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Buckets más grandes para temp tables
    cursor.execute("PRAGMA temp_store=MEMORY")
    # Protección contra corrupción
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

# Sesión local para interactuar con la base de datos
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para los modelos
Base = declarative_base()

# Dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
