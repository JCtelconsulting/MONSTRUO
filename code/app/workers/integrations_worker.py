import logging
import asyncio
from app.core.config import settings

logger = logging.getLogger(__name__)

async def send_whatsapp_notification(payload: dict):
    """
    Envía una notificación por WhatsApp.
    En DEV solo loguea.
    Payload esperado: {"phone": "+569...", "message": "..."}
    """
    phone = payload.get("phone")
    message = payload.get("message")
    
    if settings.ENV_TYPE != "prod":
        logger.info(f"[WHATSAPP_MOCK] Would send to {phone}: {message}")
        return

    # Aquí iría la implementación real con Twilio/Meta API
    logger.info(f"[WHATSAPP_PROD] Sending to {phone}: {message}")
    # await twilio_client.send(...) 
    # TODO: Implementar integración real cuando se tengan credenciales

async def send_3cx_call(payload: dict):
    """
    Inicia una llamada automática por 3CX.
    En DEV solo loguea.
    Payload esperado: {"phone": "+569...", "audio_msg": "..."}
    """
    phone = payload.get("phone")
    
    if settings.ENV_TYPE != "prod":
        logger.info(f"[3CX_MOCK] Would call {phone}")
        return

    # Aquí iría la implementación real con 3CX API
    logger.info(f"[3CX_PROD] Calling {phone}")
    # await 3cx_client.make_call(...)
    # TODO: Implementar integración real cuando se tengan credenciales
