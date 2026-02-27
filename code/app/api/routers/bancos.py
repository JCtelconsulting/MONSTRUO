from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
import subprocess
import time
import tempfile
import uuid
import os
from app.core import deps


MAX_APK_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB

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
    now = time.time()
    if current_lock["user"] != sess["username"] or now > current_lock["expires_at"]:
        raise HTTPException(status_code=403, detail="No tienes el control del banco")

    # Keep-alive del lock para mantener comportamiento de sesión activa
    current_lock["expires_at"] = now + LOCK_TTL

    # Validación opcional de extensión declarada
    if file.filename and not file.filename.lower().endswith(".apk"):
        raise HTTPException(status_code=400, detail="El archivo debe tener extensión .apk")

    # 2. Guardar temporalmente de forma segura (ignora filename del usuario)
    temp_path: str | None = None
    bytes_written = 0

    try:
        unique_name = f"installer-{uuid.uuid4().hex}.apk"
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=unique_name + "-", suffix=".apk", delete=False
        ) as tmp:
            temp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_APK_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "APK excede tamaño máximo permitido "
                            f"({MAX_APK_SIZE_BYTES // (1024 * 1024)} MB)"
                        ),
                    )
                tmp.write(chunk)

        if bytes_written == 0:
            raise HTTPException(status_code=400, detail="APK vacío")

        # 3. Copiar al contenedor
        subprocess.run(
            ["docker", "cp", temp_path, "monstruo-bancos-01:/tmp/installer.apk"],
            check=True,
            timeout=30,
        )

        # 4. Instalar
        subprocess.run(
            [
                "docker",
                "exec",
                "monstruo-bancos-01",
                "adb",
                "install",
                "-r",
                "/tmp/installer.apk",
            ],
            check=True,
            timeout=120,
        )

        return {"status": "ok", "message": "APK instalado correctamente"}

    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout instalando APK")
    except subprocess.CalledProcessError as e:
        print(f"Error instalando APK (subprocess): {e}")
        raise HTTPException(status_code=500, detail="Error al instalar APK")
    except Exception as e:
        print(f"Error instalando APK: {e}")
        raise HTTPException(status_code=500, detail="Error interno instalando APK")
    finally:
        await file.close()
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
