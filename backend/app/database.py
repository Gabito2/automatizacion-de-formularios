import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Ruta de la base de datos SQLite.
# Ruta ABSOLUTA para que no dependa del directorio desde donde se lanza el servidor
# (antes "sqlite:///./legajos.db" creaba el archivo en el CWD, en cualquier lugar).
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = "sqlite:///" + os.path.join(_BACKEND_DIR, "..", "legajos.db").replace("\\", "/")

# Crear motor de base de datos
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

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
