from pydantic_settings import BaseSettings
from typing import List, Dict
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Monstruo"
    SECRET_KEY: str = "CAMBIAME_ESTO_ES_INSEGURO_F8A9"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120 
    
    # Configuración de Ticketera y Entorno
    TICKET_AUTO_REPLY_ENABLED: bool = False
    ENV_TYPE: str = "dev"  # dev, prod, staging
    
    # Ticketera Attachments
    TICKET_ATTACHMENTS_DIR: str = "/srv/monstruo/data/tickets"
    TICKET_MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB
    TICKET_ALLOWED_EXTENSIONS: List[str] = [
        ".jpg", ".jpeg", ".png", ".gif", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv", ".zip"
    ] 

    # Roles permitidos: admin, ops, finance, warehouse
    ROLE_PERMISSIONS: Dict[str, List[str]] = {
        "admin": ["*"],
        "ops": [
            "dashboard:read",
            "invoice:read",
            "invoice:sync",
            "bodega:read",
            "tickets:read",
            "tickets:write",
            "crm:read",
            "crm:write",
            "audit:read",
            "admin.settings",
        ],
        "finance": [
            "dashboard:read",
            "invoice:read",
            "invoice:write",
            "invoice:void",
            "payment:write",
            "crm:read",
            "crm:write",
            "audit:export",
        ],
        "warehouse": ["bodega:read", "bodega:write"],
        # Nuevos roles tecnicos
        "redes": ["tickets:read", "tickets:write", "dashboard:read"],
        "sistemas": ["tickets:read", "tickets:write", "dashboard:read"],
        "implementaciones": ["tickets:read", "tickets:write", "dashboard:read", "pmo:read", "pmo:write"],
        # Rol gerencial (solo lectura global + reportes)
        "gerencia": [
            "dashboard:read", 
            "tickets:read", 
            "pmo:read", 
            "finanzas:read", 
            "audit:read",
            "reports:read"
        ],
    }

    class Config:
        env_file = ".env"
        extra = "ignore" 

settings = Settings()
