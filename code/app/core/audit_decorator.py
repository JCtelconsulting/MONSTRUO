from functools import wraps
from fastapi import Request, BackgroundTasks
from typing import Callable, Optional
from app.core import audit

def audit_action(action_name: str, severity: str = "info", target_extractor: Optional[Callable] = None):
    """
    Decorador para auditar endpoints.
    Requiere que el endpoint acepte 'request: Request' y 'background_tasks: BackgroundTasks'.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 1. Ejecutar función original
            try:
                # Buscamos Request y BackgroundTasks en kwargs
                request: Request = kwargs.get('request')
                bg_tasks: BackgroundTasks = kwargs.get('background_tasks')
                
                # Si no están, intentamos buscarlos en args (dificil en FastAPI, suelen ser kwargs)
                # Ojo: FastAPI inyecta dependencias, pero el decorador envuelve la función *después* de la inyección.
                
                result = await func(*args, **kwargs)
                
                # 2. LOG SUCCESS (Post-execution)
                if request and bg_tasks:
                    actor = "unknown"
                    if hasattr(request, "state") and getattr(request.state, "user", None):
                        actor = request.state.user.get("username", "unknown")
                    # Fallback jwt decoding here? Mejor usar middleware q inyecte user en state.
                    
                    # Target extraction
                    target = ""
                    if target_extractor:
                        try:
                            # Pasamos el resultado y/o kwargs al extractor
                            target = target_extractor(result, kwargs)
                        except:
                            pass
                            
                    ip = request.client.host if request.client else ""
                    
                    bg_tasks.add_task(
                        audit.log_audit, 
                        actor=actor, 
                        action=action_name, 
                        target=target, 
                        ip=ip, 
                        severity=severity,
                        metadata={"status": "success"}
                    )
                
                return result
                
            except Exception as e:
                # 3. LOG FAILURE
                request: Request = kwargs.get('request')
                bg_tasks: BackgroundTasks = kwargs.get('background_tasks')
                
                if request and bg_tasks:
                    ip = request.client.host if request.client else ""
                    bg_tasks.add_task(
                        audit.log_audit, 
                        actor="unknown", # Dificil saber user si falló la auth, pero si falló lógica sí se sabe
                        action=action_name, 
                        target=f"ERROR: {str(e)}", 
                        ip=ip, 
                        severity="error",
                        metadata={"status": "failed"}
                    )
                raise e
                
        return wrapper
    return decorator
