import re
import os

FILE_PATH = "/srv/monstruo_dev/docs/PROYECTO_CONTEXTO.md"
MARKER = "=== HISTORIAL CRUDO DE CHATGPT ==="

def clean_history():
    if not os.path.exists(FILE_PATH):
        print(f"Error: {FILE_PATH} not found")
        return

    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if MARKER not in content:
        print("Marker not found.")
        return

    # Split content
    preable, raw_data = content.split(MARKER, 1)
    
    # Process raw_data
    lines = raw_data.split('\n')
    processed_lines = []
    
    in_code_block = False
    
    for line in lines:
        line_stripped = line.strip()
        
        # Skip noise
        if line_stripped in ["Saltar al contenido", "Historial del chat", "Invitar a miembros del equipo"]:
            continue
        if line_stripped.startswith("Pensado durante"):
            continue
            
        # Format Headers
        if line_stripped == "Dijiste:":
            processed_lines.append("\n---\n### 👤 User")
            continue
        if line_stripped == "ChatGPT dijo:":
            processed_lines.append("\n---\n### 🤖 ChatGPT")
            continue
            
        # Attempt to format code blocks generally (simple heuristic)
        # If line starts with "cat >" or "#!/usr/bin", it's likely code start
        # If line is "EOF", it's likely code end
        # This is rough but better than nothing for raw text
        
        # Heuristic for code blocks if they are not fenced
        if line_stripped.startswith("cat >") or line_stripped.startswith("python3 ") or line_stripped.startswith("pip install"):
             if not in_code_block:
                 processed_lines.append("\n```bash")
                 in_code_block = True
        
        # Specific fix for EOF in cat blocks
        if line_stripped == "EOF" and in_code_block:
            processed_lines.append(line)
            processed_lines.append("```\n")
            in_code_block = False
            continue
            
        processed_lines.append(line)

    # Reconstruct
    new_content = preable + MARKER + "\n" + "\n".join(processed_lines)
    
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print("Formatting complete.")

if __name__ == "__main__":
    clean_history()
