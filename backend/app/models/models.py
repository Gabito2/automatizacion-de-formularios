from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    dni = Column(String, unique=True, index=True, nullable=False)
    nombre = Column(String, nullable=False)
    apellido = Column(String, nullable=False)
    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    rol = Column(String, default="estudiante", nullable=False)  # "estudiante", "administrador", "validador"
    activo = Column(Boolean, default=True)
    primer_ingreso = Column(Boolean, default=True)
    carrera = Column(String, nullable=True)  # Se importa de CSV
    sede = Column(String, nullable=True)     # Se importa de CSV

    # Relaciones
    datos_personales = relationship("DatosPersonales", back_populates="usuario", uselist=False, cascade="all, delete-orphan")
    documentos = relationship("Documento", back_populates="usuario", cascade="all, delete-orphan")


class DatosPersonales(Base):
    __tablename__ = "datos_personales"

    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True)
    telefono = Column(String, nullable=True)
    direccion = Column(String, nullable=True)
    localidad = Column(String, nullable=True)
    provincia = Column(String, nullable=True)
    fecha_nacimiento = Column(String, nullable=True)  # Guardado como string YYYY-MM-DD
    secundario_completo = Column(Boolean, default=False)
    titulo_secundario = Column(String, nullable=True)

    # Relación
    usuario = relationship("Usuario", back_populates="datos_personales")


class Documento(Base):
    __tablename__ = "documentos"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    tipo_documento = Column(String, nullable=False)  # "dni_frente", "dni_dorso", "foto_4x4", "analitico_secundario", "partida_nacimiento", "formulario_inscripcion"
    archivo_url = Column(String, nullable=False)     # Ruta del archivo guardado
    estado = Column(String, default="pendiente")     # "pendiente", "aprobado", "rechazado", "observado"
    observacion = Column(String, nullable=True)      # Observación más reciente
    fecha_subida = Column(DateTime, default=datetime.utcnow)

    # Relaciones
    usuario = relationship("Usuario", back_populates="documentos")
    observaciones = relationship("Observacion", back_populates="documento", cascade="all, delete-orphan")


class Observacion(Base):
    __tablename__ = "observaciones"

    id = Column(Integer, primary_key=True, index=True)
    documento_id = Column(Integer, ForeignKey("documentos.id", ondelete="CASCADE"), nullable=False)
    mensaje = Column(Text, nullable=False)
    fecha = Column(DateTime, default=datetime.utcnow)

    # Relación
    documento = relationship("Documento", back_populates="observaciones")
