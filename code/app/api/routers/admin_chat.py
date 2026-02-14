from fastapi import APIRouter, Body
from app.core import db
import os
import json
from app.utils import ai_local_openai_compat

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.post("/chat")
@router.post("/chat")
def admin_chat(body: dict = Body(...)):
    # body: { message: str, context: object }
    user_msg = body.get("message")
    
    # Dynamic root path resolution
    from pathlib import Path
    root_dir = Path(__file__).resolve().parents[4]

    # 1. Load Admin Prompt
    try:
        with open(root_dir / "prompts/admin_rules.txt", "r") as f:
            admin_prompt = f.read()
    except:
        admin_prompt = "You are the system admin."
        
    try:
        with open(root_dir / "prompts/global_context.txt", "r") as f:
            global_context = f.read()
    except:
        global_context = ""
    
    # Construct System Prompt
    system_content = f"{admin_prompt}\n\nCONTEXT:\n{global_context}"
    system_content += """
    
TOOLS:
1. read_prompt_file(filename): To see the current content of a rule or code file.
   JSON: `{"tool_calls": [{"name": "read_prompt_file", "args": {"filename": "..."}}]}`

2. update_prompt_file(filename, content): To OVERWRITE a rule or code file.
   JSON: `{"tool_calls": [{"name": "update_prompt_file", "args": {"filename": "...", "content": "..."}}]}`

Valid filenames: 
- Prompts: categ_rules.txt, duplicates_rules.txt, instructor_rules.txt, auto_resolve_rules.txt, global_context.txt
- Code (SAFE TO EDIT): ../code/static/js/bodega_ui.js, ../code/static/js/bodega_ai.js

BEST PRACTICE: 
- ALWAYS read the file first.
- If editing code, maintain valid syntax.
- DO NOT edit core files or api files.
"""

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_msg}
    ]
    
    # 2. Call LLM
    resp = ai_local_openai_compat.chat(messages, temperature=0.1)
    
    # 3. Parse Response for Tool Calls
    response_text = resp
    tool_status = ""
    
    if "```json" in resp:
        try:
            json_str = resp.split("```json")[1].split("```")[0].strip()
            data = json.loads(json_str) 
            
            if "tool_calls" in data:
                 valid_files = [
                    "categ_rules.txt", "duplicates_rules.txt", "instructor_rules.txt", 
                    "auto_resolve_rules.txt", "global_context.txt",
                    "../code/static/js/bodega_ui.js", "../code/static/js/bodega_ai.js"
                 ]
                 
                 for call in data["tool_calls"]:
                     name = call["name"]
                     fname = call["args"].get("filename")
                     
                     if fname not in valid_files:
                         tool_status += f"\n[Error: Invalid file {fname}]"
                         continue

                     # Resolve Path
                     if fname.endswith(".js"):
                         path = root_dir / f"code/static/js/{fname.split('/')[-1]}"
                     else:
                         path = root_dir / f"prompts/{fname}"
                     
                     if name == "read_prompt_file":
                         try:
                             with open(path, "r") as f:
                                 content = f.read()
                             tool_status += f"\n[System: Contenido de {fname}:]\n```\n{content[:2000]}...\n```(Truncated)"
                         except Exception as e:
                             tool_status += f"\n[Error leyendo {fname}: {e}]"
                             
                     elif name == "update_prompt_file":
                         content = call["args"].get("content")
                         try:
                             with open(path, "w") as f:
                                 f.write(content)
                             tool_status += f"\n✅ Archivo {fname} actualizado exitosamente."
                         except Exception as e:
                             tool_status += f"\n[Error escribiendo {fname}: {e}]"

                 # Clean up response for user (hide JSON)
                 parts = resp.split("```json")
                 response_text = parts[0].strip() + f"\n\n_{tool_status}_"
                 
        except Exception as e:
            tool_status = f"Error integrando herramienta: {e}"
            response_text += f"\n\n[System Error: {tool_status}]"
            
    return {"reply": response_text}

