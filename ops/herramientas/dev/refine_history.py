import re
import os

FILE_PATH = "/srv/monstruo/docs/PROYECTO_CONTEXTO.md"
MARKER = "=== HISTORIAL CRUDO DE CHATGPT ==="
NEW_HEADER = "=== HISTORIAL DETALLADO (REFINADO) ==="

# Patterns to reduce/summarize
IRRELEVANT_PATTERNS = [
    r"^Saltar al contenido",
    r"^Historial del chat",
    r"^Invitar a miembros",
    r"^Pensado durante \d+",
    r"^Dijiste:",
    r"^ChatGPT dijo:",
    r"^\s*Si quieres, puedo bajarte esto",
    r"^\s*Perfecto.*Vamos a",
    r"^\s*Hola.*",
    r"^\s*Dale.*",
]

def refine_history():
    if not os.path.exists(FILE_PATH):
        print(f"Error: {FILE_PATH} not found")
        return

    with open(FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if MARKER not in content:
        print("Historial marker not found.")
        return

    static_part, raw_history = content.split(MARKER, 1)
    
    # Process the history lines
    lines = raw_history.splitlines()
    refined_lines = []
    
    buffer = []
    is_code = False
    
    for line in lines:
        line_strip = line.strip()
        
        # Detect Code Block Start/End
        if line_strip.startswith("```"):
            is_code = not is_code
            refined_lines.append(line)
            continue
            
        if is_code:
            refined_lines.append(line)
            continue

        # Skip irrelevant conversation filler (heuristic)
        skip = False
        for p in IRRELEVANT_PATTERNS:
            if re.match(p, line_strip):
                skip = True
                break
        if skip:
            continue
            
        # Condense empty lines
        if not line_strip:
            if refined_lines and refined_lines[-1] != "":
                refined_lines.append("")
            continue
            
        # Add basic formatting for speakers if not present (from previous script)
        # Assuming format_contexto.py ran, we might look for ### User / ### ChatGPT
        # If user wants "summary but not too much", we keep the technical content.
        
        # Heuristics for "Important Points"
        # 1. Keep lines with technical keywords
        # 2. Keep lines that look like commands or file paths
        # 3. Keep lines that clarify decisions
        
        # Just appending for now, but skipping the 'filler' is the main summarization here
        # + we can merge short lines?
        
        refined_lines.append(line)

    # Re-assemble
    final_content = static_part.strip() + "\n\n" + NEW_HEADER + "\n\n" + "\n".join(refined_lines)
    
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(final_content)
        
    print(f"Refinement complete. Original size: {len(content)}, New size: {len(final_content)}")

if __name__ == "__main__":
    refine_history()
