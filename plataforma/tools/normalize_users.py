# /tmp/normalize_users.py
import json
import os
import sys
from pathlib import Path

# --- Setup sys.path para poder importar 'core' ---
# Asumimos que este script se ejecuta desde /srv/monstruo_dev/gateway/
# o que el CWD está configurado para que 'core' sea importable.
# La forma más robusta es añadir el directorio del proyecto al path.
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

try:
    from core import db
    from core.config import settings as app_settings
except ImportError as e:
    print(f"Error: No se pudieron importar los módulos de la aplicación. Asegúrate de que el script se ejecute desde el directorio correcto y que el entorno virtual esté activo si es necesario. {e}")
    sys.exit(1)

def calculate_effective_modules(user_roles: list) -> list:
    """
    Calcula los módulos efectivos para una lista de roles, usando la lógica
    centralizada en app_settings.
    """
    if not user_roles:
        return []

    # Caso especial para admin
    if "admin" in user_roles:
        return [module["id"] for module in app_settings.UI_MODULES]

    effective_modules = set()
    all_permissions = set()

    for role in user_roles:
        permissions_for_role = app_settings.ROLE_PERMISSIONS.get(role, [])
        all_permissions.update(permissions_for_role)
    
    if "*" in all_permissions:
        return [module["id"] for module in app_settings.UI_MODULES]

    for perm in all_permissions:
        key = perm.split(":")[0] if ":" in perm else perm
        module_id = app_settings.PERMISSION_TO_MODULE_MAP.get(key)
        if module_id:
            effective_modules.add(module_id)

    module_order = {module["id"]: i for i, module in enumerate(app_settings.UI_MODULES)}
    return sorted(list(effective_modules), key=lambda m: module_order.get(m, 999))


def main():
    print("Iniciando script de normalización de usuarios...")
    conn = None
    try:
        conn = db.get_conn()
        print("Conexión a la base de datos exitosa.")

        users = conn.execute("SELECT id, username, role, secondary_roles, allowed_modules FROM auth.users ORDER BY username").fetchall()
        
        if not users:
            print("No se encontraron usuarios en la tabla auth.users.")
            return

        print(f"Se encontraron {len(users)} usuarios. Procesando...")
        print("-" * 30)

        update_count = 0
        skipped_count = 0

        for user in users:
            user_id = user["id"]
            username = user["username"]
            primary_role = user["role"]
            
            try:
                secondary_roles = json.loads(user["secondary_roles"] or '[]')
                if not isinstance(secondary_roles, list):
                    secondary_roles = []
            except (json.JSONDecodeError, TypeError):
                secondary_roles = []

            all_roles = sorted(list(set([r for r in [primary_role] + secondary_roles if r])))

            try:
                current_modules_str = user["allowed_modules"]
                current_modules = json.loads(current_modules_str or '[]')
                if not isinstance(current_modules, list):
                    current_modules = []
            except (json.JSONDecodeError, TypeError):
                current_modules = []

            # Si el usuario ya tiene módulos asignados, es un override manual. Lo respetamos.
            if current_modules:
                print(f"  - Usuario '{username}': Omitido (ya tiene {len(current_modules)} módulos explícitos).")
                skipped_count += 1
                continue

            # Si no tiene módulos, los calculamos.
            print(f"  - Usuario '{username}': Módulos vacíos. Calculando desde roles: {all_roles}")
            new_modules = calculate_effective_modules(all_roles)
            
            if not new_modules:
                print(f"    -> No se pudieron derivar módulos. Se dejará vacío.")
                continue

            print(f"    -> Módulos calculados: {new_modules}")
            
            new_modules_json = json.dumps(new_modules)
            
            try:
                conn.execute(
                    "UPDATE auth.users SET allowed_modules = %s WHERE id = %s",
                    (new_modules_json, user_id)
                )
                print(f"    -> ¡ACTUALIZADO!")
                update_count += 1
            except Exception as e:
                print(f"    -> ERROR al actualizar: {e}")


        print("-" * 30)
        print("Proceso finalizado.")
        print(f"Usuarios actualizados: {update_count}")
        print(f"Usuarios omitidos: {skipped_count}")
        
        conn.commit()
        print("Cambios guardados en la base de datos.")

    except Exception as e:
        print(f"\\nERROR FATAL durante la ejecución: {e}")
        if conn:
            try:
                conn.rollback()
                print("Se ha hecho rollback de la transacción.")
            except Exception as rb_e:
                print(f"Error al intentar hacer rollback: {rb_e}")
    finally:
        if conn:
            conn.close()
            print("Conexión a la base de datos cerrada.")

if __name__ == "__main__":
    main()
