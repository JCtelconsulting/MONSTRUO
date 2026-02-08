from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
import subprocess
import time
import shutil
import os
from app.core import deps

router = APIRouter(prefix="/api/bancos", tags=["bancos"])

# --- IM-MEMORY STATE FOR LOCK ---
# In a clustered environment, use Redis/DB. For now, simplistic global var.
current_lock = {"user": None, "timestamp": 0.0, "expires_at": 0.0}

LOCK_TTL = 600.0  # 10 minutes


class InputCommand(BaseModel):
    keycode: int


@router.get("/session")
def get_session_status(sess: dict = Depends(deps.require_session_hybrid)):
    now = time.time()

    # Check expiry
    if current_lock["user"] and now > current_lock["expires_at"]:
        # Auto-release
        current_lock["user"] = None
        current_lock["timestamp"] = 0.0
        current_lock["expires_at"] = 0.0

    is_locked = current_lock["user"] is not None
    user_name = sess.get("username")
    is_mine = is_locked and current_lock["user"] == user_name

    return {
        "locked": is_locked,
        "owner": current_lock["user"],
        "is_mine": is_mine,
        "expires_in": int(current_lock["expires_at"] - now) if is_locked else 0,
    }


@router.post("/session/acquire")
def acquire_session(sess: dict = Depends(deps.require_session_hybrid)):
    now = time.time()
    user = sess["username"]

    # Check if locked by someone else
    if current_lock["user"] and current_lock["user"] != user:
        if now < current_lock["expires_at"]:
            raise HTTPException(
                status_code=409, detail=f"Terminal ocupado por {current_lock['user']}"
            )
        # Else expired, can take over

    current_lock["user"] = user
    current_lock["timestamp"] = now
    current_lock["expires_at"] = now + LOCK_TTL

    return {"status": "acquired", "expires_at": current_lock["expires_at"]}


@router.post("/session/release")
def release_session(sess: dict = Depends(deps.require_session_hybrid)):
    user = sess["username"]

    if current_lock["user"] == user:
        current_lock["user"] = None
        current_lock["timestamp"] = 0.0
        current_lock["expires_at"] = 0.0
        return {"status": "released"}

    return {"status": "ignored"}


@router.post("/input")
def send_input(cmd: InputCommand, sess: dict = Depends(deps.require_session_hybrid)):
    # Verify Lock
    user = sess["username"]
    now = time.time()

    if current_lock["user"] != user or now > current_lock["expires_at"]:
        raise HTTPException(status_code=403, detail="No tienes el control del terminal")

    # Extend Lock (keep alive)
    current_lock["expires_at"] = now + LOCK_TTL

    # Send Command to Docker
    # docker exec monstruo-bancos-01 adb shell input keyevent <keycode>
    try:
        # 3 = HOME, 4 = BACK, 187 = APP_SWITCH
        subprocess.run(
            [
                "docker",
                "exec",
                "monstruo-bancos-01",
                "adb",
                "shell",
                "input",
                "keyevent",
                str(cmd.keycode),
            ],
            check=True,
            timeout=5,
        )
        return {"status": "ok"}
    except Exception as e:
        print(f"ADB Error: {e}")
        raise HTTPException(status_code=500, detail="Error de comunicación con Android")


@router.post("/install-apk")
async def install_apk(
    file: UploadFile = File(...), sess: dict = Depends(deps.require_session_hybrid)
):
    """
    Recibe un archivo APK y lo instala en el emulador vía ADB.
    """
    # 1. Verificar Lock
    if current_lock["user"] != sess["username"]:
        raise HTTPException(status_code=403, detail="No tienes el control del banco")

    # 2. Guardar temporalmente
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # 3. Copiar al contenedor
        # Usamos docker cp desde el host
        cmd_cp = f"docker cp {temp_path} monstruo-bancos-01:/tmp/installer.apk"
        ret_cp = os.system(cmd_cp)
        if ret_cp != 0:
            raise Exception("Error copiando APK al contenedor")

        # 4. Instalar
        cmd_install = "docker exec monstruo-bancos-01 adb install -r /tmp/installer.apk"
        ret_install = os.system(cmd_install)

        if ret_install != 0:
            raise Exception("Error al ejecutar adb install")

        return {"status": "ok", "message": f"Instalado {file.filename} correctamente"}

    except Exception as e:
        print(f"Error instalando APK: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)
