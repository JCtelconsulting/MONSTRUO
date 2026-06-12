import io
import os
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import piexif
from PIL import Image
from sqlalchemy.orm import Session

from backend import modelos, nucleo

# Registrar el opener HEIF/HEIC para que PIL pueda abrir fotos de iPhone
# (formato por defecto). Sin esto, las HEIC daban UnidentifiedImageError y las
# miniaturas/visualizacion salian rotas ("no se ven por formato").
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover - si la lib no esta, seguimos sin HEIC
    pass

# Formatos que el navegador NO renderiza nativo: se sirven convertidos a JPEG.
NAVEGADOR_NO_SOPORTA = {".heic", ".heif", ".tif", ".tiff", ".bmp"}


def to_browser_jpeg(image_path: str):
    """BytesIO JPEG de una imagen en formato no-web (HEIC/TIFF/...), respetando
    orientacion EXIF. None si no se puede abrir."""
    try:
        from PIL import ImageOps

        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        buf.seek(0)
        return buf
    except Exception:
        return None


PHOTO_NAME_RE = re.compile(
    r"^(?P<prefix>PENDIENTE_)?(?P<project>[A-Za-z0-9_-]+)_P(?P<plan>\d+)_(?P<ts>\d{8}_\d{6})(?:_(?P<dup>\d+))?(?P<ext>\.[A-Za-z0-9]+)$",
    re.IGNORECASE,
)


def apply_manual_exif(db: Session, ruta_foto_mala: str, fecha_hora_manual: str) -> dict:
    """Aplica una fecha+hora manual a una foto sin EXIF: la mueve a _VALIDAR
    con el nombre normalizado (timestamp inyectado), inserta el EXIF si la
    extension lo permite, y vuelve a poner la asignacion en COMPLETADA_TERRENO.

    Lanza FileNotFoundError si la foto no existe.
    Lanza ValueError si el formato de fecha es invalido.
    """
    if not os.path.exists(ruta_foto_mala):
        raise FileNotFoundError("Foto no encontrada")

    try:
        dt = datetime.fromisoformat(fecha_hora_manual)
    except ValueError as e:
        raise ValueError(f"Formato de fecha invalido: {e}") from e

    p = Path(ruta_foto_mala)
    ext = p.suffix.lower()
    parent = p.parent.parent
    dest = parent / nucleo.VALIDATION_DIR_NAME
    os.makedirs(dest, exist_ok=True, mode=0o775)
    nombre_limpio = p.name.replace("PENDIENTE_", "")

    def _build_name(ts_dt: datetime) -> str:
        nuevo_timestamp = ts_dt.strftime("%Y%m%d_%H%M%S")
        nombre_final = re.sub(r"_\d{8}_\d{6}", f"_{nuevo_timestamp}", nombre_limpio)
        if nombre_final == nombre_limpio:
            stem = Path(nombre_limpio).stem
            suffix = Path(nombre_limpio).suffix
            nombre_final = f"{stem}_{nuevo_timestamp}{suffix}"
        return nombre_final

    # Buscar nombre destino libre desplazando timestamps si colisiona.
    offset_seconds = 0
    dt_final = dt
    dest_path = dest / _build_name(dt_final)
    while dest_path.exists():
        offset_seconds += 1
        dt_final = dt + timedelta(seconds=offset_seconds)
        dest_path = dest / _build_name(dt_final)

    # Inyectar EXIF (best-effort).
    if ext in (".jpg", ".jpeg", ".tif", ".tiff"):
        exif_date = dt_final.strftime("%Y:%m:%d %H:%M:%S")
        exif_dict = {
            "0th": {},
            "Exif": {36867: exif_date.encode("utf-8")},
            "GPS": {},
            "1st": {},
            "thumbnail": None,
        }
        try:
            piexif.insert(piexif.dump(exif_dict), ruta_foto_mala)
        except Exception:
            pass

    shutil.move(ruta_foto_mala, str(dest_path))
    try:
        os.chmod(str(dest_path), 0o664)
    except Exception:
        pass
    try:
        ts = dt_final.timestamp()
        os.utime(str(dest_path), (ts, ts))
    except Exception:
        pass

    # Pasar todas las asignaciones del item de PENDIENTE_EXIF a COMPLETADA_TERRENO.
    item = db.query(modelos.Item).filter(modelos.Item.ruta_item == str(parent)).first()
    if item:
        asigs = (
            db.query(modelos.AsignacionPlan)
            .filter(
                modelos.AsignacionPlan.item_id == item.id,
                modelos.AsignacionPlan.estado == modelos.EstadoItemEnum.PENDIENTE_EXIF,
            )
            .all()
        )
        for a in asigs:
            a.estado = modelos.EstadoItemEnum.COMPLETADA_TERRENO
            a.fecha_completado_terreno = datetime.now()
        db.commit()

    return {"status": "ok"}


def generate_thumbnail(image_path: str, max_size=(400, 400), quality=60):
    try:
        img = Image.open(image_path)
        try:
            exif = img._getexif()
            if exif:
                o = exif.get(0x0112)
                if o == 3:
                    img = img.rotate(180, expand=True)
                elif o == 6:
                    img = img.rotate(270, expand=True)
                elif o == 8:
                    img = img.rotate(90, expand=True)
        except Exception:
            pass
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail(max_size)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        buf.seek(0)
        return buf
    except Exception:
        return None


def normalize_duplicate_names(dir_path: Path):
    if not dir_path.exists():
        return
    groups = {}
    for f in dir_path.iterdir():
        if not f.is_file():
            continue
        m = PHOTO_NAME_RE.match(f.name)
        if not m:
            continue
        prefix = "PENDIENTE_" if m.group("prefix") else ""
        project = m.group("project")
        plan = m.group("plan")
        ts = m.group("ts")
        dup = m.group("dup")
        ext = m.group("ext").upper()
        key = (prefix, project, plan, ext)
        entry = {
            "file": f,
            "prefix": prefix,
            "project": project,
            "plan": plan,
            "ts": ts,
            "dup": int(dup) if dup else None,
            "ext": ext,
        }
        groups.setdefault(key, {}).setdefault(ts, []).append(entry)
    for key, ts_groups in groups.items():
        occupied = set(ts_groups.keys())
        for ts in sorted(ts_groups.keys()):
            items = ts_groups[ts]
            items.sort(
                key=lambda x: (x["dup"] is not None, x["dup"] or -1, x["file"].name)
            )
            base = items[0]
            base_name = (
                f"{base['prefix']}{base['project']}_P{base['plan']}_{ts}{base['ext']}"
            )
            if base["file"].name != base_name:
                base_dest = dir_path / base_name
                if not base_dest.exists():
                    try:
                        os.replace(base["file"], base_dest)
                        base["file"] = base_dest
                    except Exception:
                        pass
            if len(items) == 1:
                continue
            base_dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
            for dup_item in items[1:]:
                offset = 1
                while True:
                    candidate_dt = base_dt + timedelta(seconds=offset)
                    candidate_ts = candidate_dt.strftime("%Y%m%d_%H%M%S")
                    if candidate_ts not in occupied:
                        break
                    offset += 1
                occupied.add(candidate_ts)
                new_name = f"{dup_item['prefix']}{dup_item['project']}_P{dup_item['plan']}_{candidate_ts}{dup_item['ext']}"
                if dup_item["file"].name == new_name:
                    continue
                new_path = dir_path / new_name
                if new_path.exists():
                    continue
                try:
                    os.replace(dup_item["file"], new_path)
                except Exception:
                    pass
