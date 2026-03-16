import os
import json
import logging
import requests
from typing import List, Dict, Optional, Any

from pathlib import Path

from app.core.env_loader import load_runtime_env

load_runtime_env(Path(__file__).resolve())

# Configure simple ascii logger
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# CONFIG
BASE_URL = os.getenv("ULTRON_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
MODEL = os.getenv("ULTRON_LLM_MODEL", "local-model")
TIMEOUT = int(os.getenv("ULTRON_LLM_TIMEOUT_SEC", "30"))
ENABLED = os.getenv("ULTRON_LLM_ENABLED", "0") == "1"

def is_enabled() -> bool:
    return ENABLED

def check_status() -> Dict[str, Any]:
    if not ENABLED:
        return {"enabled": False, "ok": False, "msg": "Disabled by env"}
    
    try:
        # Some OpenAI-compat servers support /models
        res = requests.get(f"{BASE_URL}/models", timeout=3)
        if res.status_code == 200:
            return {"enabled": True, "ok": True, "model": MODEL, "base_url": BASE_URL}
        else:
            return {"enabled": True, "ok": False, "msg": f"HTTP {res.status_code}"}
    except Exception as e:
        return {"enabled": True, "ok": False, "msg": str(e)}

def chat(messages: List[Dict[str, str]], temperature: float = 0.2) -> Optional[str]:
    if not ENABLED:
        logger.info("LLM Disabled")
        return None

    url = f"{BASE_URL}/chat/completions"
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False
    }

    try:
        res = requests.post(url, json=payload, timeout=TIMEOUT)
        if res.status_code != 200:
            logger.error(f"LLM Error {res.status_code}: {res.text}")
            return None
        
        data = res.json()
        content = data["choices"][0]["message"]["content"]
        return content
    except Exception as e:
        logger.error(f"LLM Exception: {e}")
        return None
