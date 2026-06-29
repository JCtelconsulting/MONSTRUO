from pydantic_settings import BaseSettings
from typing import List, Dict
import os
from pathlib import Path

from plataforma.core.env_loader import load_runtime_env

load_runtime_env(Path(__file__).resolve())

class Settings(BaseSettings):
    PROJECT_NAME: str = "Monstruo"
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120 
    
    # OAuth2 Google
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_AUTO_PROVISION_ALLOWLIST: str = ""
    GOOGLE_OAUTH_STATE_TTL_SECONDS: int = 600
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS: int = 10
    
    # Configuración de Ticketera y Entorno
    TICKET_AUTO_REPLY_ENABLED: bool = False
    TICKET_AUTO_REPLY_DELAY_MINUTES: int = 30
    TICKET_AUTO_REPLY_ALLOWLIST_EMAILS: str = ""
    TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS: str = ""
    TICKET_AUTO_REPLY_REQUIRE_ALLOWLIST: bool = True
    TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS: str = "noreply,no-reply,mailer-daemon,postmaster"
    ENV_TYPE: str = "dev"  # dev, prod, staging
    MAIL_SANDBOX: bool = False  # True en DEV: simula envíos, no llega a clientes
    COMPLIANCE_EXPORT_DIR: str = ""
    COMPLIANCE_TZ: str = "America/Santiago"
    COMPLIANCE_EXPORT_HOUR: int = 2
    COMPLIANCE_PURGE_HOUR: int = 2
    COMPLIANCE_PURGE_GRACE_DAYS: int = 30
    TICKET_RETENTION_PUBLIC_DAYS: int = 365
    TICKET_RETENTION_INTERNAL_DAYS: int = 1095
    TICKET_RETENTION_RESTRICTED_DAYS: int = 1825
    CHANNELS_ENABLED: bool = False
    GOOGLE_CHAT_ADAPTER_MODE: str = "disabled"  # disabled | dry_run | live
    GOOGLE_CHAT_SPACE_WEBHOOK: str = ""
    GOOGLE_CHAT_BOT_TOKEN: str = ""
    GOOGLE_CHAT_TIMEOUT_SECONDS: int = 10
    CHANNELS_MAX_ATTEMPTS: int = 3
    CHANNELS_RETRY_BASE_SECONDS: int = 60
    CHANNELS_RETRY_MAX_SECONDS: int = 900
    TICKET_SLA_MODE: str = "24x7"  # 24x7 | business_hours
    TICKET_SLA_BUSINESS_TZ_OFFSET: str = "-03:00"  # Formato ±HH:MM
    TICKET_SLA_BUSINESS_DAYS: str = "0,1,2,3,4"  # 0=lunes ... 6=domingo
    TICKET_SLA_BUSINESS_START_HOUR: int = 9
    TICKET_SLA_BUSINESS_END_HOUR: int = 18
    TICKET_SLA_ESCALATION_WINDOWS_PCT: str = "80,100"  # Ej: 50,80,100
    JOBS_STALE_RUNNING_MINUTES: int = 20
    SYS_JOBS_RETENTION_DAYS: int = 14
    TKS_SLA_EVAL_LIMIT: int = 500
    
    # Ticketera Attachments
    # Mantener vacío permite fallback automático por entorno en tickets_service.
    TICKET_ATTACHMENTS_DIR: str = ""
    TICKET_PUBLIC_CODE_START: int = 2154
    TICKET_MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB
    TICKET_ALLOWED_EXTENSIONS: List[str] = [
        ".jpg", ".jpeg", ".png", ".gif", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".csv", ".zip"
    ] 

    # Módulos visibles en la UI. Fuente única de verdad.
    UI_MODULES: List[Dict[str, str]] = [
        {"id": "dashboard", "label": "Dashboard"},
        {"id": "tks", "label": "Ticketera"},
        {"id": "erp", "label": "ERP & Finanzas"},
        {"id": "crm", "label": "CRM"},
        {"id": "bodega", "label": "Bodega"},
        {"id": "terreneitor", "label": "Terreneitor"},
        {"id": "config", "label": "Configuracion"},
        {"id": "gta", "label": "GTA"},
    ]

    # Mapeo de prefijo de permiso a módulo de UI.
    PERMISSION_TO_MODULE_MAP: Dict[str, str] = {
        "dashboard": "dashboard",
        "tickets": "tks",
        "invoice": "erp",
        "payment": "erp",
        "finanzas": "erp",
        "crm": "crm",
        "bodega": "bodega",
        "terreneitor": "terreneitor",
        "admin.settings": "config",
        "gta": "gta",
    }
    
    # Roles permitidos: admin, encargado_mesa, ops, finance, warehouse
    # Modelo: el ROL de una persona ES su ÁREA (catálogo organigrama.AREAS), salvo los 2
    # roles de GESTIÓN transversales (admin, encargado_mesa) que no son un área.
    ROLE_PERMISSIONS: Dict[str, List[str]] = {
        # ── Gestión (transversales, no son área) ──
        "admin": ["*"],
        "encargado_mesa": [
            "dashboard:read",
            "tickets:read",
            "tickets:write",
            "tickets:compliance",
            "audit:read",
        ],
        # ── Roles de ÁREA (= plataforma.core.organigrama.AREAS) ──
        "gerencia": [
            "dashboard:read",
            "tickets:read",
            "tickets:write",
            "finanzas:read",
            "audit:read",
            "reports:read",
        ],
        "comercial": ["dashboard:read", "crm:read", "crm:write"],
        "preventa": ["dashboard:read", "crm:read"],
        # pmo = gestión de proyectos (absorbe los antiguos 'implementaciones' y 'ops').
        "pmo": [
            "dashboard:read",
            "tickets:read",
            "tickets:write",
            "gta:read",
            "gta:write",
            "reports:read",
        ],
        "sistemas": ["dashboard:read", "tickets:read", "tickets:write", "admin.settings"],
        "redes": ["dashboard:read", "tickets:read", "tickets:write"],
        # bodega = antiguo 'warehouse'.
        "bodega": ["dashboard:read", "bodega:read", "bodega:write"],
        "proveedores": ["dashboard:read", "bodega:read"],
        # finanzas = antiguo 'finance'.
        "finanzas": [
            "dashboard:read",
            "invoice:read",
            "invoice:write",
            "invoice:void",
            "payment:write",
            "crm:read",
            "audit:export",
        ],
        "capital_humano": ["dashboard:read"],
    }

    class Config:
        env_file = ".env"
        extra = "ignore" 

settings = Settings()
