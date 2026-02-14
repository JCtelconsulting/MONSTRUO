import os
import re
from datetime import datetime

CTX_FILE = "/srv/monstruo_dev/docs/PROYECTO_CONTEXTO.md"
OUT_FILE = "/srv/monstruo_dev/docs/PROMPT_CHAT_UNIVERSAL.md"

def get_section_text(content, header_pattern):
    # Search for header line
    # Match header line, then capture everything non-greedy until:
    # 1. Next Header (# Digit.)
    # 2. History Separator (===)
    # 3. End of string
    regex = re.compile(rf"^{header_pattern}.*?\n(.*?)(?=\n# \d|\n===|\Z)", re.DOTALL | re.MULTILINE)
    match = regex.search(content)
    if match:
        return match.group(1).strip()
    return ""

def main():
    if not os.path.exists(CTX_FILE):
        print("Error: Context file not found")
        return

    with open(CTX_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    stack = get_section_text(content, r"# 1\.")
    state = get_section_text(content, r"# 4\.")
    history = get_section_text(content, r"# 6\.")
    roadmap = get_section_text(content, r"# 7\.")

    universal_prompt = f"""
# PROMPT DE CONTEXTO UNIVERSAL: PROYECTO MONSTRUO
**Fecha Generación:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Objetivo:** Restaurar contexto inmediato en una nueva sesión de IA.

---

## 1. RESUMEN EJECUTIVO
Estás trabajando en **MONSTRUO**, un middleware de integración ERP para Telconsulting.
Tu rol es: **Developer Senior Fullstack (Python/FastAPI) + DevOps**.
**Regla de Oro:** Todo cambio se registra en `docs/PROYECTO_CONTEXTO.md`.
**Idioma:** Híbrido Español/Inglés (Spanish/English) en artefactos y explicaciones para fines educativos.

## 2. STACK TÉCNICO
{stack}

## ENTORNO DE EJECUCION Y ACCESO (IMPORTANTE)

### Estado actual (Laboratorio)
- MONSTRUO esta corriendo en mi PC como entorno de laboratorio.
- Acceso: actualmente soy el unico usuario con acceso (no hay otros clientes/usuarios concurrentes).
- Implicancia: problemas de cache de assets, concurrencia multiusuario y efectos "clientes con JS viejo" NO aplican en esta fase (solo yo consumo la UI/API).

### Estado futuro (Servidor / Produccion)
- Al migrar al servidor, habra multiples usuarios accediendo al sistema.
- Implicancia: antes del pase a servidor se debe ejecutar hardening para multiusuario:
  - Control de cache/versionado de assets (cache-bust o versionado de static) para evitar clientes desfasados.
  - Autenticacion/autorizacion consistente en endpoints criticos.
  - Observabilidad (logs/metricas) y alertas para errores 4xx/5xx.
  - Procedimiento de despliegue con rollback + verificacion (systemd + curls + DB backup).

Regla: cualquier decision que dependa de multiples clientes (cache-bust, sesiones, rate limits, locks) se evalua y se activa obligatoriamente en la etapa "Servidor/Produccion", no en laboratorio local.

## 3. ESTADO ACTUAL DEL PROYECTO
{state}

## 4. BITÁCORA RECIENTE (Hitos Críticos)
{history}

## 5. ROADMAP INMEDIATO (Lo que sigue)
{roadmap}

## 6. COMANDOS OPERATIVOS CLAVE
*   **Root:** `/srv/monstruo`
*   **Run Backend:** `sudo systemctl start monstruo-api`
*   **Run Pipeline:** `cd code && ./scripts/integracion/run_pipeline.sh`
*   **Logs:** `journalctl -u monstruo-api -f`
*   **Regenerar este Prompt:** `python3 ops/herramientas/generate_universal_prompt.py`

---
**INSTRUCCIÓN PARA EL AGENTE:**
1.  Asume el rol técnico descrito.
2.  Analiza el ESTADO y ROADMAP para situarte.
3.  Tu primera respuesta debe ser un breve acuse de recibo confirmando el último hito y el siguiente paso pendiente.
"""

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(universal_prompt.strip())
    
    print(f"✅ Prompt Universal generado en: {OUT_FILE}")

if __name__ == "__main__":
    main()
