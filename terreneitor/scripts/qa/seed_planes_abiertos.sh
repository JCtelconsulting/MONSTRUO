#!/usr/bin/env bash
# Deja en DEV los 7 planes ABIERTOS (pool de "tomar un trabajo") alineados a los
# 7 casos de Diego, limpios (sin nadie asignado). Idempotente: borra los que ya
# existan con esos nombres y los recrea. Uso: bash scripts/qa/seed_planes_abiertos.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
SUPV="https://supervisor.telconsulting.cl/dev"
DB="data/db/terreneitor.db"

CASOS=(
  "Instalacion de servicio - Domicilio"
  "Retiro de equipamiento - Grupo CGE"
  "Traslado de servicio - Sitio cliente"
  "Despacho de equipamiento - Bodega central"
  "Reportabilidad EPP - Cuadrilla terreno"
  "Avance del dia - Proyecto en curso"
  "Visita tecnica / preventa - Levantamiento"
)

echo "### borrando planes de caso previos (para recrear limpios)"
python3 - "${CASOS[@]}" <<PYEOF
import sqlite3, sys
casos = sys.argv[1:]
c = sqlite3.connect("$DB")
q = "select id from planes_trabajo where " + " or ".join(["descripcion=?"]*len(casos))
ids = [r[0] for r in c.execute(q, casos)]
for pid in ids:
    aids = [r[0] for r in c.execute("select id from asignaciones_plan where plan_id=?", (pid,))]
    for aid in aids:
        c.execute("delete from asignacion_usuarios where asignacion_id=?", (aid,))
    c.execute("delete from asignaciones_plan where plan_id=?", (pid,))
    c.execute("delete from planes_trabajo where id=?", (pid,))
c.commit()
print("  borrados:", ids)
PYEOF

echo "### login supervisor"
curl -s -m8 -c /tmp/seedsup.txt -o /dev/null -X POST "$SUPV/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"qa.supervisor@telconsulting.cl","password":"QaSup2026!"}'

mapfile -t ITS < <(python3 -c "import sqlite3;[print(r[0]) for r in sqlite3.connect('$DB').execute('select id from items order by id limit 40')]")
i=0
n() { echo "${ITS[$((i++ % ${#ITS[@]}))]},${ITS[$((i++ % ${#ITS[@]}))]},${ITS[$((i++ % ${#ITS[@]}))]}"; }

echo "### creando 7 planes abiertos (sin asignar)"
for caso in "${CASOS[@]}"; do
  curl -s -m10 -b /tmp/seedsup.txt -X POST "$SUPV/api/planes-trabajo/" \
    -H "Content-Type: application/json" \
    -d "{\"descripcion\":\"$caso\",\"item_ids\":[$(n)],\"usuario_ids\":[]}" -o /dev/null
  echo "  + $caso"
done
rm -f /tmp/seedsup.txt
echo "### LISTO (7 planes abiertos para tomar)"
