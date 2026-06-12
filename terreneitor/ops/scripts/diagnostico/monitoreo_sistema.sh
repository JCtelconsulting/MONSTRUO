#!/usr/bin/env bash
# monitoreo_sistema.sh - Diagnostico rapido de Terreneitor
set -u

echo "=========================================================="
echo "    TERRENEITOR - REPORTE DE MONITOREO SISTEMA"
echo "    Fecha: $(date)"
echo "=========================================================="
echo ""

# 1. ESTADO DE SERVICIOS
echo ">>> ESTADO DE SERVICIOS SYSTEMD:"
for svc in "terreneitor" "terreneitor-dev" "nginx"; do
    if systemctl is-active --quiet "$svc"; then
        echo -e "[ OK ] $svc esta corriendo."
    else
        echo -e "[Borrador] $svc esta DETENIDO o con fallas."
    fi
done
echo ""

# 2. ESPACIO EN DISCO
echo ">>> ESPACIO EN DISCO (SRV):"
df -h /srv | awk 'NR==2 {print "Uso: " $3 "/" $2 " (" $5 ") | Disponible: " $4}'
echo ""

# 3. ULTIMOS ERRORES EN LOGS (Backend)
echo ">>> BUSCANDO ERRORES RECIENTES EN LOGS (ultimas 20 lineas):"
for env in "terreneitor" "terreneitor_dev"; do
    LOG_DIR="/srv/$env/logs"
    echo "[$env]:"
    if [ -d "$LOG_DIR" ]; then
        grep -rhE "ERROR|Exception|Internal Server Error" "$LOG_DIR" | tail -n 20 || echo "Sin errores criticos detectados."
    else
        echo "Directorio de logs no encontrado."
    fi
done
echo ""

# 4. ESTADO DE BACKUPS
echo ">>> ESTADO DE BACKUPS (DEV):"
BACKUP_DIR="/srv/terreneitor_dev_backups/db_snapshots"
if [ -d "$BACKUP_DIR" ]; then
    LAST_BK=$(ls -t "$BACKUP_DIR"/proyectos_dev_*.db.gz 2>/dev/null | head -n 1)
    if [ -n "$LAST_BK" ]; then
        echo "Ultimo backup local: $(basename "$LAST_BK") ($(date -r "$LAST_BK"))"
    else
        echo "No se encontraron backups locales."
    fi
else
    echo "Carpeta de backups dev no existe."
fi
echo ""

# 5. CARGA DEL SISTEMA
echo ">>> CARGA PROCESADOR / MEMORIA:"
uptime | awk -F'load average:' '{ print "Load avg: " $2 }'
free -h | awk '/^Mem:/ { print "Memoria Uso: " $3 "/" $2 " (" $7 " libre)" }'

echo ""
echo "=========================================================="
echo "    FIN DEL REPORTE"
echo "=========================================================="
