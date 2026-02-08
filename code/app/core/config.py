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
    }

    class Config:
        env_file = ".env"
        extra = "ignore" 

settings = Settings()
