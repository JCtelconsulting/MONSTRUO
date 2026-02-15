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
    TICKET_AUTO_REPLY_DELAY_MINUTES: int = 15
    TICKET_AUTO_REPLY_ALLOWLIST_EMAILS: str = ""
    TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS: str = ""
    TICKET_AUTO_REPLY_REQUIRE_ALLOWLIST: bool = True
    TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS: str = "noreply,no-reply,mailer-daemon,postmaster"
    ENV_TYPE: str = "dev"  # dev, prod, staging
    COMPLIANCE_EXPORT_DIR: str = ""
    COMPLIANCE_TZ: str = "America/Santiago"
    COMPLIANCE_EXPORT_HOUR: int = 2
    COMPLIANCE_PURGE_HOUR: int = 2
    COMPLIANCE_PURGE_GRACE_DAYS: int = 30
    TICKET_RETENTION_PUBLIC_DAYS: int = 365
    TICKET_RETENTION_INTERNAL_DAYS: int = 1095
    TICKET_RETENTION_RESTRICTED_DAYS: int = 1825
    CHANNELS_ENABLED: bool = False
    WHATSAPP_ADAPTER_MODE: str = "disabled"  # disabled | dry_run | live
    THREECX_ADAPTER_MODE: str = "disabled"  # disabled | dry_run | live
    WHATSAPP_BASE_URL: str = ""
    WHATSAPP_AUTH_TOKEN: str = ""
    WHATSAPP_TIMEOUT_SECONDS: int = 10
    THREECX_BASE_URL: str = ""
    THREECX_AUTH_TOKEN: str = ""
    THREECX_TIMEOUT_SECONDS: int = 10
    CHANNELS_MAX_ATTEMPTS: int = 3
    CHANNELS_RETRY_BASE_SECONDS: int = 60
    CHANNELS_RETRY_MAX_SECONDS: int = 900
    JIRA_BASE_URL: str = ""
    JIRA_USER: str = ""
    JIRA_API_TOKEN: str = ""
    JIRA_PROJECT_KEYS: str = ""
    JIRA_SYNC_ENABLED: bool = False
    JIRA_SYNC_DAILY_HOUR: int = 3
    JIRA_SYNC_TZ: str = "America/Santiago"
    TICKET_SLA_MODE: str = "24x7"  # 24x7 | business_hours
    TICKET_SLA_BUSINESS_TZ_OFFSET: str = "-03:00"  # Formato ±HH:MM
    TICKET_SLA_BUSINESS_DAYS: str = "0,1,2,3,4"  # 0=lunes ... 6=domingo
    TICKET_SLA_BUSINESS_START_HOUR: int = 9
    TICKET_SLA_BUSINESS_END_HOUR: int = 18
    TICKET_SLA_ESCALATION_WINDOWS_PCT: str = "80,100"  # Ej: 50,80,100
    
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
            "tickets:compliance",
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
