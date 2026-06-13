#!/bin/bash
# Script de Configuración Automática para Tunel IA (Usuario ia_tunel)
# Ejecutar con permisos de sudo: sudo ./instalar_tunel.sh

set -e

echo "=== INICIANDO CONFIGURACIÓN DE TUNEL IA ==="

# 1. Crear Usuario
if id "ia_tunel" &>/dev/null; then
    echo "El usuario 'ia_tunel' ya existe."
else
    echo "Creando usuario 'ia_tunel'..."
    adduser --disabled-password --gecos "" ia_tunel
    usermod -s /usr/sbin/nologin ia_tunel
fi

# 2. Configurar Directorio SSH
echo "Configurando permisos SSH..."
mkdir -p /home/ia_tunel/.ssh
chmod 700 /home/ia_tunel/.ssh
touch /home/ia_tunel/.ssh/authorized_keys
chmod 600 /home/ia_tunel/.ssh/authorized_keys
chown -R ia_tunel:ia_tunel /home/ia_tunel/.ssh

# 3. Agregar Clave Pública
echo "Instalando clave pública..."
# Clave provista por Juan
KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ+el1SUulGxSyauSOz7LjlkyXezZ/45Oe8ORgX77u3h juan@PCJuanLopez"

# Verificar si la clave ya existe para no duplicarla
if grep -qF "$KEY" /home/ia_tunel/.ssh/authorized_keys; then
    echo "La clave ya está autorizada."
else
    echo "$KEY" >> /home/ia_tunel/.ssh/authorized_keys
    echo "Clave agregada correctamente."
fi

# 4. Configurar Restricciones SSHD
echo "Aplicando restricciones de seguridad SSH..."
CONFIG_FILE="/etc/ssh/sshd_config.d/ia_tunel.conf"

cat > "$CONFIG_FILE" <<EOF
Match User ia_tunel
  AllowTcpForwarding remote
  GatewayPorts no
  PermitTTY no
  X11Forwarding no
  PermitTunnel no
EOF

# 5. Reiniciar Servicio SSH
echo "Recargando servicio SSH..."
if systemctl is-active --quiet ssh; then
    systemctl reload ssh
elif systemctl is-active --quiet sshd; then
    systemctl reload sshd
else
    echo "ADVERTENCIA: No se pudo encontrar servicio ssh o sshd activo."
fi

echo "=== CONFIGURACIÓN COMPLETADA CON ÉXITO ==="
echo "Usuario 'ia_tunel' listo."
echo "Clave instalada."
echo "Restricciones aplicadas."
