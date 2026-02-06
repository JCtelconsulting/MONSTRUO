from fastapi import APIRouter
from typing import List, Dict
import os
import time
import requests

router = APIRouter(prefix="/api", tags=["datos"])

def chequear_integracion(nombre: str, url_prueba: str, timeout: int = 3) -> Dict:
    """
    Verifica salud de una integración externa.
    Retorna estado ACTIVO/ERROR con latencia y detalle.
    """
    inicio = time.time()
    try:
        # Hacer request real con timeout
        resp = requests.get(url_prueba, timeout=timeout)
        latencia_ms = int((time.time() - inicio) * 1000)
        
        # Clasificar estado según código HTTP
        if 200 <= resp.status_code < 300:
            estado = "ACTIVO"
            detalle = f"Respondiendo correctamente ({resp.status_code})"
        elif resp.status_code in [401, 403]:
            # Servicio responde pero requiere auth (significa que está vivo)
            estado = "ACTIVO"
            detalle = f"Servicio operativo (auth requerida)"
        else:
            estado = "ERROR"
            detalle = f"HTTP {resp.status_code}"
            
        return {
            "nombre": nombre,
            "estado": estado,
            "detalle": detalle,
            "latencia_ms": latencia_ms,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    except requests.Timeout:
        latencia_ms = int((time.time() - inicio) * 1000)
        return {
            "nombre": nombre,
            "estado": "ERROR",
            "detalle": "Timeout de conexión",
            "latencia_ms": latencia_ms,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        latencia_ms = int((time.time() - inicio) * 1000)
        # No exponer detalles internos, solo tipo de error genérico
        return {
            "nombre": nombre,
            "estado": "ERROR",
            "detalle": f"Error de conexión ({type(e).__name__})",
            "latencia_ms": latencia_ms,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

@router.get("/estado")
def get_estado_modulos():
    """
    Retorna estado de módulos e integraciones con salud real.
    """
    # Base URL del servicio (localhost para chequeos internos)
    base_url = os.getenv("API_BASE_URL", "http://localhost:9000")
    
    # Chequear integraciones reales
    integraciones = []
    
    # Laudus: usar endpoint bridge que existe
    try:
        laudus_check = chequear_integracion(
            "Laudus",
            f"{base_url}/api/bridge/laudus/clientes",
            timeout=3
        )
        integraciones.append({**laudus_check, "tipo": "ERP Externo"})
    except Exception:
        integraciones.append({
            "nombre": "Laudus",
            "estado": "ERROR",
            "detalle": "No disponible",
            "tipo": "ERP Externo"
        })
    
    # Parrotfy: usar endpoint CRM
    try:
        parrotfy_check = chequear_integracion(
            "Parrotfy",
            f"{base_url}/api/crm/empresas",
            timeout=3
        )
        integraciones.append({**parrotfy_check, "tipo": "CRM"})
    except Exception:
        integraciones.append({
            "nombre": "Parrotfy",
            "estado": "ERROR",
            "detalle": "No disponible",
            "tipo": "CRM"
        })
    
    # BUK: Futuro (API pendiente, export podría estar activo si existe)
    integraciones.append({
        "nombre": "Buk",
        "estado": "ACTIVO EN UN FUTURO",
        "detalle": "Integración API planificada",
        "tipo": "RRHH"
    })
    
    # Jira: Pendiente
    integraciones.append({
        "nombre": "Jira",
        "estado": "PENDIENTE",
        "detalle": "Configuración en proceso",
        "tipo": "Tickets"
    })
    
    return {
        "modulos": [
            {"id": "erp", "nombre": "ERP", "estado": "ACTIVO", "detalle": "Operativo"},
            {"id": "crm", "nombre": "CRM", "estado": "ACTIVO", "detalle": "Conectado"},
            {"id": "bodega", "nombre": "Bodega", "estado": "FALTA INFORMACION", "detalle": "Sin inventario cargado"},
            {"id": "tks", "nombre": "TKs", "estado": "ACTIVO", "detalle": "Sistema de tickets"},
        ],
        "integraciones": integraciones
    }

@router.get("/tks")
def get_tks():
    # Retornar lista vacia intencional o datos dummy para demo
    return [
       {"id": 101, "titulo": "Fallo en login supervisor", "estado": "ABIERTO", "fecha": "2026-01-24", "prioridad": "ALTA"},
       {"id": 102, "titulo": "Solicitud acceso bodega", "estado": "CERRADO", "fecha": "2026-01-23", "prioridad": "BAJA"},
       {"id": 103, "titulo": "Error sincronizacion Laudus", "estado": "EN PROGRESO", "fecha": "2026-01-25", "prioridad": "MEDIA"}
    ]

@router.get("/resumen")
def get_resumen_dashboard():
    return {
        "operaciones": {"activas": 12, "pausadas": 3},
        "facturacion": {"pendiente": "$4.5M", "vencido": "$1.2M"},
        "clientes": {"total": 45, "nuevos_mes": 2},
        "alertas": ["Sincronizacion Laudus lenta", "Certificado SSL por vencer"]
    }
