import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict


class JsonFormatter(logging.Formatter):
    """
    Formateador de logs que emite JSON para ser ingerido por herramientas de monitoreo (Datadog, CloudWatch, etc).
    """

    def format(self, record: logging.LogRecord) -> str:
        log_record: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        # Si hay excepcion, agregar info
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Si hay extra fields (ej: request_id), agregarlos
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id  # type: ignore

        return json.dumps(log_record)


def configurar_logger(nombre_app: str = "terreneitor") -> logging.Logger:
    """
    Configura y devuelve un logger robusto.
    """
    logger = logging.getLogger(nombre_app)

    # Evitar duplicados si se llama multiples veces
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Handler para consola
    handler = logging.StreamHandler(sys.stdout)

    # Usar JSON Formatter
    formatter = JsonFormatter()
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    return logger


# Instancia global lista para importar
log = configurar_logger()
