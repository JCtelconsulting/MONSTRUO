# ========================= rutas_health.py =========================
import asyncio
import os

from fastapi import APIRouter, Depends

from backend import dependencias

router = APIRouter(
    tags=["Health"],
    dependencies=[Depends(dependencias.require_admin)],
)


@router.get("/api/status/drive")
async def get_drive_status():
    """
    Verifica la conexión con Google Drive usando rclone.
    """
    try:
        # Usamos lsf con un timeout para no colgar el portal
        process = await asyncio.create_subprocess_exec(
            "rclone",
            "lsf",
            "Terreneitor:",
            "--max-depth",
            "1",
            "--contimeout",
            "5s",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            return {"connected": True, "msg": "Unidad compartida operativa"}
        else:
            error_msg = stderr.decode().strip() or "Error de rclone"
            return {"connected": False, "msg": f"Desconectado: {error_msg}"}
    except Exception as e:
        return {"connected": False, "msg": f"Error de sistema: {str(e)}"}


@router.get("/api/system/backup-status")
async def get_backup_and_temp_status():
    """
    Retorna el estado de los backups y la temperatura del servidor.
    """
    temp_c = None
    status = "ok"
    message = "Sensor no detectado (VM)"

    # 1. Intentar leer temperatura del sistema
    thermal_paths = [
        "/sys/class/thermal/thermal_zone0/temp",
        "/sys/class/hwmon/hwmon0/temp1_input",
        "/sys/class/hwmon/hwmon1/temp1_input",
    ]

    for p in thermal_paths:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    raw = f.read().strip()
                    temp_c = float(raw) / 1000.0
                    break
            except Exception:
                continue

    if temp_c is not None:
        if temp_c < 75:
            status = "ok"
            message = "Temperatura normal"
        elif temp_c < 85:
            status = "warning"
            message = "Temperatura elevada"
        else:
            status = "error"
            message = "CRÍTICO: Sobrecalentamiento"
    else:
        # Fallback estandarizado para VMs sin sensor termico (evita el '-- C' que parece un error)
        temp_c = 40.0

    backup_timer_active = False
    backup_service_failed = False
    backup_status_msg = "Estado no disponible"

    try:
        timer_proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "is-active",
            "terreneitor-backup.timer",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timer_stdout, _ = await timer_proc.communicate()
        backup_timer_active = timer_proc.returncode == 0 and (
            timer_stdout.decode().strip() == "active"
        )

        failed_proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "is-failed",
            "terreneitor-backup.service",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        failed_stdout, _ = await failed_proc.communicate()
        backup_service_failed = failed_stdout.decode().strip() == "failed"

        if backup_timer_active and not backup_service_failed:
            backup_status_msg = "Timer activo y ultimo respaldo sin falla conocida"
        elif backup_timer_active and backup_service_failed:
            backup_status_msg = "Timer activo, pero el ultimo respaldo fallo"
        elif backup_service_failed:
            backup_status_msg = "Servicio de respaldo en fallo"
        else:
            backup_status_msg = "Timer de respaldo inactivo"
    except Exception:
        backup_status_msg = "No fue posible consultar systemd"

    # 2. Estructura compatible con portal.js
    return {
        "server_temperature": {"celsius": temp_c, "status": status, "message": message},
        "server_temperature_c": temp_c,
        "server_temperature_status": status,
        "server_temperature_message": message,
        "backup_active": backup_timer_active and not backup_service_failed,
        "backup_timer_active": backup_timer_active,
        "backup_service_failed": backup_service_failed,
        "backup_status_message": backup_status_msg,
    }
