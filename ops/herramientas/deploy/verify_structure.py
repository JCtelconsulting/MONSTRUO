#!/usr/bin/env python3
import os
import sys
import fnmatch

def verify_structure(root_dir):
    """
    Recorre los directorios y verifica que los archivos existencias coincidan con el .README.md (si existe).
    """
    violations = []
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip hidden dirs (except root if needed) and __pycache__
        dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != "__pycache__" and d != "venv"]
        
        readme_path = os.path.join(dirpath, ".README.md")
        if not os.path.exists(readme_path):
            continue
            
        with open(readme_path, 'r') as f:
            content = f.read()
            
        # Parse allowlist from content
        # Asumimos que todo lo que sigue a "## Estructura Permitida" o lista con "- " es parte de la allowlist
        # Para simplificar, buscamos lineas que empiecen con "- "
        allowed_patterns = []
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- "):
                # Remove "- " and trailing chars like "/" or comments
                item = line[2:].split('#')[0].strip()
                # Remove trailing / for directory patterns
                if item.endswith('/'):
                    item = item[:-1]
                allowed_patterns.append(item)
        
        # Check files and dirs
        current_items = set(filenames + dirnames)
        # remove ignored
        current_items = {i for i in current_items if not i.startswith('.') and i != "__pycache__"}
        
        for item in current_items:
            # Check if item matches any pattern (exact or wildcard)
            matched = False
            for pattern in allowed_patterns:
                if fnmatch.fnmatch(item, pattern):
                    matched = True
                    break
            
            if not matched:
                violations.append(f"[VIOLACION] {os.path.join(dirpath, item)} no está en .README.md")

    return violations

if __name__ == "__main__":
    root = "/srv/monstruo"
    print(f"Verificando estructura en {root}...")
    errors = verify_structure(root)
    
    if errors:
        print(f"Se encontraron {len(errors)} violaciones de estructura:")
        for err in errors:
            print(err)
        sys.exit(1)
    else:
        print("Estructura OK. Coincide con manifiestos estrictos.")
        sys.exit(0)
