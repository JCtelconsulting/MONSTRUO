#!/usr/bin/env bash
# Deja el entorno DEV con datos de DEMO en TODOS los estados del proceso, con
# fotos reales (con y sin EXIF, varios formatos), proyectos en distintos estados
# y varios informes. Para revisar cada vista/modal con contenido.
# Uso: bash scripts/qa/demo_flujo_completo.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
DEV="https://terreneitor.telconsulting.cl/dev"
SUPV="https://supervisor.telconsulting.cl/dev"
DB="data/db/terreneitor.db"
j() { python3 -c "import sys,json;print(json.load(sys.stdin)$1)" 2>/dev/null; }

echo "### 1) Reseed limpio"
docker exec -i monstruo-dev-terreneitor python - < scripts/qa/seed_dev.py 2>&1 | grep -i "seed ok"

echo "### 2) Generar fotos demo (con/sin EXIF, formatos)"
docker exec -i monstruo-dev-terreneitor python - <<'PYEOF' 2>&1 | grep -i "fotos demo"
import os
from PIL import Image, ImageDraw
import piexif, pillow_heif
pillow_heif.register_heif_opener()
OUT="/app/data/_demo_fotos"; os.makedirs(OUT, exist_ok=True)
def mk(t,c):
    im=Image.new("RGB",(1200,900),c); d=ImageDraw.Draw(im)
    d.rectangle([30,30,1170,870],outline=(255,255,255),width=6); d.text((70,90),t,fill=(255,255,255)); return im
def exif(dt):
    return piexif.dump({"0th":{},"Exif":{piexif.ExifIFD.DateTimeOriginal:dt.encode()},"GPS":{},"1st":{},"thumbnail":None})
mk("CON EXIF 1",(30,120,60)).save(f"{OUT}/con1.jpg","JPEG",exif=exif("2026:06:10 09:00:00"))
mk("CON EXIF 2",(30,90,140)).save(f"{OUT}/con2.jpg","JPEG",exif=exif("2026:06:10 10:30:00"))
mk("CON EXIF 3",(120,60,150)).save(f"{OUT}/con3.jpg","JPEG",exif=exif("2026:06:10 12:15:00"))
mk("SIN EXIF 1",(160,60,60)).save(f"{OUT}/sin1.jpg","JPEG")
mk("SIN EXIF PNG",(60,150,150)).save(f"{OUT}/sin2.png","PNG")
pillow_heif.from_pillow(mk("HEIC SIN EXIF",(200,120,40))).save(f"{OUT}/sin3.heic")
print("fotos demo:", sorted(os.listdir(OUT)))
PYEOF

echo "### 3) Proyectos en distintos estados (1 PAUSADO, 1 CERRADO)"
python3 - <<PYEOF
import sqlite3
c=sqlite3.connect("$DB")
ids=[r[0] for r in c.execute("select id from proyectos order by id")]
if len(ids)>=3:
    c.execute("update proyectos set estado_proyecto='PAUSADO' where id=?",(ids[-1],))
    c.execute("update proyectos set estado_proyecto='CERRADO' where id=?",(ids[-2],))
c.commit();print("  pausado/cerrado set")
c.close()
PYEOF

echo "### 4) Login supervisor + terreno"
curl -s -m8 -c /tmp/d_sup.txt -o /dev/null -X POST "$SUPV/api/auth/login" -H "Content-Type: application/json" -d '{"email":"qa.supervisor@telconsulting.cl","password":"QaSup2026!"}'
curl -s -m8 -c /tmp/d_terr.txt -o /dev/null -X POST "$DEV/api/auth/login" -H "Content-Type: application/json" -d '{"email":"qa.terreno@telconsulting.cl","password":"QaTerr2026!"}'
TID=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute(\"select id from users where role='TERRENO'\").fetchone()[0])")

echo "### 5) Crear plan 'Demostracion Estados' con 6 items (de un proyecto ACTIVO)"
ITEMS=$(python3 -c "
import sqlite3;c=sqlite3.connect('$DB')
# items de proyectos ACTIVOS, sin asignar
asig=set(x[0] for x in c.execute('select item_id from asignaciones_plan'))
q='''select i.id from items i join categorias k on i.categoria_id=k.id join proyectos p on k.proyecto_id=p.id where p.estado_proyecto=\"ACTIVO\"'''
libres=[x[0] for x in c.execute(q) if x[0] not in asig][:6]
print(','.join(map(str,libres)))
")
echo "  items: $ITEMS"
PLAN=$(curl -s -m10 -b /tmp/d_sup.txt -X POST "$SUPV/api/planes-trabajo/" -H "Content-Type: application/json" -d "{\"descripcion\":\"Demostracion Estados\",\"item_ids\":[$ITEMS],\"usuario_ids\":[$TID]}" | j "['plan_id']")
echo "  plan_id=$PLAN"
# asignaciones del plan en orden
mapfile -t A < <(python3 -c "import sqlite3;[print(r[0]) for r in sqlite3.connect('$DB').execute('select id from asignaciones_plan where plan_id=? order by id',($PLAN,))]")
echo "  asignaciones: ${A[*]}"

up() { curl -s -m20 -b /tmp/d_terr.txt -X POST "$DEV/api/asignaciones/$1/upload-multiple/" -F "files=@$2" -o /dev/null; }
waitstate() { for i in $(seq 1 12); do s=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select estado from asignaciones_plan where id=?',($1,)).fetchone()[0])"); [ "$s" != "EN_PROGRESO" ] && [ "$s" != "ASIGNADA" ] && break; curl -s -m2 -o /dev/null http://127.0.0.1:8005/health; done; }

echo "### 6) Producir estados con fotos reales"
# A[0] ASIGNADA: sin subir (queda ASIGNADA)
# A[1] COMPLETADA_TERRENO: con EXIF, NO validar
up "${A[1]}" "data/_demo_fotos/con1.jpg"; up "${A[1]}" "data/_demo_fotos/con2.jpg"; waitstate "${A[1]}"
# A[2] PENDIENTE_EXIF: sin EXIF (cuarentena)
up "${A[2]}" "data/_demo_fotos/sin1.jpg"; up "${A[2]}" "data/_demo_fotos/sin3.heic"; waitstate "${A[2]}"
# A[3] VALIDADA: con EXIF + validar
up "${A[3]}" "data/_demo_fotos/con3.jpg"; waitstate "${A[3]}"
curl -s -m15 -b /tmp/d_sup.txt -X POST "$SUPV/api/asignaciones/${A[3]}/validar/" -o /dev/null
# A[4] RECHAZADA: con EXIF + rechazar
up "${A[4]}" "data/_demo_fotos/con1.jpg"; waitstate "${A[4]}"
curl -s -m15 -b /tmp/d_sup.txt -X POST "$SUPV/api/asignaciones/${A[4]}/rechazar/" -H "Content-Type: application/json" -d '{"comentario":"Foto fuera de foco, repetir con mejor luz"}' -o /dev/null
# A[5] EN_PROGRESO: forzar en DB
python3 -c "import sqlite3;c=sqlite3.connect('$DB');c.execute(\"update asignaciones_plan set estado='EN_PROGRESO' where id=${A[5]}\");c.commit()"

echo "### 7) Generar 3 informes"
for t in diario semanal personalizado; do
  curl -s -m12 -b /tmp/d_sup.txt -X POST "$DEV/api/reportes/generar" -H "Content-Type: application/json" -d "{\"tipo\":\"$t\",\"fecha_inicio\":\"2026-06-09\",\"fecha_fin\":\"2026-06-15\"}" -o /dev/null
done
for i in $(seq 1 15); do curl -s -m2 -o /dev/null http://127.0.0.1:8005/health; done

echo "### 8) Resumen de estados"
python3 - <<PYEOF
import sqlite3;c=sqlite3.connect("$DB")
print("  Asignaciones por estado:")
for r in c.execute("select estado,count(*) from asignaciones_plan group by estado"): print("   ",r)
print("  Proyectos por estado:", dict(c.execute("select estado_proyecto,count(*) from proyectos group by estado_proyecto")))
print("  Planes:",c.execute("select count(*) from planes_trabajo").fetchone()[0],"| Informes:",c.execute("select count(*) from reportes_historial").fetchone()[0])
c.close()
PYEOF
rm -f /tmp/d_sup.txt /tmp/d_terr.txt
echo "### DEMO LISTA"
