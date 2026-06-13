from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Usuario
from app.utils.security import verify_access_token

# URL donde el cliente se autentica para obtener el token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Usuario:
    """Extrae el usuario autenticado a partir del token JWT en las cabeceras HTTP."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales de acceso no válidas o expiradas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        # Intentar obtener el token de cabecera 'Authorization' manualmente si no se cargó por cabeceras estándar
        raise credentials_exception

    payload = verify_access_token(token)
    if payload is None:
        raise credentials_exception
    
    dni: str = payload.get("sub")
    if dni is None:
        raise credentials_exception
        
    user = db.query(Usuario).filter(Usuario.dni == dni).first()
    if user is None:
        raise credentials_exception
        
    if not user.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario inactivo en el sistema"
        )
        
    return user

def require_role(roles: list[str]):
    """Genera una dependencia que valida si el usuario actual posee alguno de los roles indicados."""
    def dependency(current_user: Usuario = Depends(get_current_user)):
        if current_user.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requiere uno de los siguientes roles: {', '.join(roles)}"
            )
        return current_user
    return dependency

# Roles específicos
get_current_student = require_role(["estudiante"])
get_current_validator = require_role(["validador", "administrador"])
get_current_admin = require_role(["administrador"])
