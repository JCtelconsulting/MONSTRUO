#!/bin/bash
# Script de migración automática a la nueva VM de Desarrollo (.8)
# Diseñado por Cline para ejecutarse desde la máquina actual (.5)

echo "=========================================================="
echo "  INICIANDO MIGRACIÓN AUTOMÁTICA A MONSTRUO DEV (.8)  "
echo "=========================================================="
echo ""
echo "Paso 1: Autorizando conexión a 192.168.60.8..."
echo "-> Se te pedirá la contraseña '1234' de la máquina .8"
ssh-copy-id -o StrictHostKeyChecking=no juan@192.168.60.8

echo ""
echo "Paso 2: Sincronizando código fuente y bases de datos locales..."
echo "-> Copiando /srv/monstruo_dev a la nueva máquina..."
# Excluimos .git para ahorrar tiempo, y carpetas pycache basura
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude 'node_modules' /srv/monstruo_dev/ juan@192.168.60.8:/home/juan/monstruo_dev/

echo ""
echo "Paso 3: Levantando contenedores en la nueva VM .8..."
ssh juan@192.168.60.8 "cd /home/juan/monstruo_dev && docker-compose --env-file plataforma/ops/env/.env.server.dev up -d gateway ticketera"

echo ""
echo "=========================================================="
echo "  ¡MIGRACIÓN A LA .8 COMPLETADA!  "
echo "=========================================================="
echo ""
echo "PASO FINAL MANUAL EN EL NGINX EXTERNO (.6):"
echo "Conéctate por SSH a la máquina 192.168.60.6 y edita tu archivo:"
echo "nano /etc/nginx/snippets/monstruo_dev_locations.conf"
echo ""
echo "Busca estas líneas y cambia la IP de .5 a .8, apuntando al puerto 9001 directo:"
echo "location /dev/ {"
echo "    proxy_pass http://192.168.60.8:9001;"
echo "    ..."
echo "}"
echo ""
echo "Luego reinicia Nginx: systemctl reload nginx"
echo "=========================================================="
