import os
import re
import json
from datetime import datetime

# CONFIGURACIÓN
PROJECT_ROOT = "/srv/monstruo"
CTX_FILE = os.path.join(PROJECT_ROOT, "docs/PROYECTO_CONTEXTO.md")
UNIVERSAL_PROMPT_FILE = os.path.join(PROJECT_ROOT, "docs/PROMPT_CHAT_UNIVERSAL.md")
AI_REPO = "/srv/inteligencia_artificial"
DATASET_FILE = os.path.join(AI_REPO, "datos/fine_tuning/global_dataset.jsonl")
PROMPTS_HISTORY_DIR = os.path.join(AI_REPO, "prompts/history")

def get_last_milestone(content):
    """Extrae el último hito de la Bitácora."""
    # Busca la sección de Bitácora (asumiendo formato estándar # 6. o similar)
    # y toma la última entrada de la tabla o lista.
    # Por simplicidad y robustez, buscaremos el patrón de fecha YYYY-MM-DD más reciente.
    
    # Regex para buscar líneas de tabla: | **YYYY-MM-DD** | **Tema** | Detalle |
    regex = re.compile(r"\|\s*\*\*(\d{4}-\d{2}-\d{2})\*\*\s*\|\s*\*\*(.*?)\*\*\s*\|\s*(.*?)\s*\|")
    matches = regex.findall(content)
    
    if matches:
        return matches[-1] # (Fecha, Tema, Detalle)
    return None

def main():
    if not os.path.exists(CTX_FILE):
        print(f"❌ Error: No existe {CTX_FILE}")
        return

    # 1. Leer Contexto
    with open(CTX_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # 2. Extraer último hito
    last_milestone = get_last_milestone(content)
    if not last_milestone:
        print("⚠️ No se detectaron hitos recientes en el formato estándar.")
        return

    date, topic, detail = last_milestone
    print(f"✅ Hito Detectado: [{date}] {topic}")

    # 3. Construir Objeto de Entrenamiento (Alpaca/JSONL format)
    training_entry = {
        "instruction": f"Generar código o solución para el hito: {topic}",
        "input": f"Contexto: Proyecto Monstruo. Detalle tarea: {detail}",
        "output": "Ver cambios en codebase asociado commit/fecha." # Idealmente diff, por ahora placeholder ref
    }
    
    # NOTA: En una versión V2, aquí haríamos 'git diff' para capturar el código real.
    # Por ahora, capturamos la INTENCIÓN y el RESULTADO descritos.

    # 4. Guardar en Dataset Central
    with open(DATASET_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(training_entry, ensure_ascii=False) + "\n")
    print(f"💾 Guardado en Dataset: {DATASET_FILE}")

    # 5. Snapshot del Prompt Universal (Contexto del momento)
    if os.path.exists(UNIVERSAL_PROMPT_FILE):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"PROMPT_MONSTRUO_{timestamp}_{topic.replace(' ', '_')}.md"
        snapshot_path = os.path.join(PROMPTS_HISTORY_DIR, snapshot_name)
        
        with open(UNIVERSAL_PROMPT_FILE, "r", encoding="utf-8") as src:
            prompt_content = src.read()
            
        with open(snapshot_path, "w", encoding="utf-8") as dst:
            dst.write(prompt_content)
            
        print(f"📸 Snapshot de Contexto: {snapshot_path}")
    else:
        print("⚠️ No se encontró PROMPT_CHAT_UNIVERSAL.md para snapshot.")

if __name__ == "__main__":
    main()
