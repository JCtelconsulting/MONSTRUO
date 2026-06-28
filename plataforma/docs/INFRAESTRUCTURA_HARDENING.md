# Infraestructura y Hardening — Monstruo / Telconsulting

> **Propósito de este doc:** que cualquier agente (o persona) que llegue al proyecto sepa
> cómo está montada la infraestructura, qué endurecimiento de seguridad se aplicó, y cómo
> operar/rescatar cada máquina. Refleja la auditoría completa del **2026-06-28**.
>
> Mantener actualizado al hacer cambios de infra. Detalle granular vivo en la memoria del
> agente (`auditoria-vm-2026-06`).

---

## 1. Las 3 máquinas

| Host | IP (privada) | Rol | OS | Tipo | Acceso |
|------|--------------|-----|-----|------|--------|
| **desarrollo** | 192.168.60.8 | DEV — `monstruo_dev` | Debian 13 (trixie) | VM KVM | `juan` (sudo) |
| **TERRENEITOR** | 192.168.60.5 | PROD — `monstruo` + terreneitor | Debian 13 (trixie) | VM KVM | `juan` (sudo); usuarios `deploy`, `sgapp` |
| **PROXYSSL** | 192.168.60.6 | Proxy inverso (borde) | Debian 12 (bookworm) | **LXC container** Proxmox | `root` directo |

- **Hipervisor:** Proxmox. Dev/Prod son VMs KVM; el **proxy es un container LXC** (kernel `pve` compartido, swap gestionado por el host).
- Las 3 tienen **solo IP privada** en la LAN `192.168.60.0/24`. Hay accesos de administración también desde `192.168.20.0/24`, una VPN `10.x` y `192.168.254.1`.

## 2. Arquitectura de red / borde

- **El proxy (60.6) es el ÚNICO con cara a Internet.** El router hace NAT de **80/443 → proxy**. nginx (bare-metal, 1.22) rutea por dominio a los upstreams (prod 60.5, dev 60.8).
- **El puerto 22 (SSH) del proxy NO está NATeado a Internet** (verificado: 0 IPs públicas en los logs de SSH; si estuviera expuesto habría cientos de intentos de bots). Solo accesible desde LAN/VPN.
- Dev y Prod **no se exponen directamente**: todo el tráfico externo pasa por el proxy.
- Dominios servidos por el proxy (Let's Encrypt): `login` `portal` `ticketera`(implícito) `terreneitor` `terreno` `supervisor` `gerencial` `sapa`(Home Assistant) `config` `ia` ... `.telconsulting.cl`. `sapa` = Home Assistant (60.4:8123), se mantiene.

## 3. Hardening aplicado (2026-06-28)

### Común a las 3 máquinas
- **SSH endurecido**: `PermitRootLogin` off / prohibit-password, `PasswordAuthentication no` (acceso solo por llave), `X11Forwarding no`.
- **fail2ban** (jail sshd). En el proxy (Debian 12, sin `/var/log/auth.log`) se usa **`backend = systemd`**.
- **unattended-upgrades** (solo security, `Automatic-Reboot "false"`, Docker en blacklist donde aplica).
- **journald** con tope de tamaño; **hora** sincronizada (NTP) en **America/Santiago**.
- 0 paquetes pendientes, 0 servicios `failed`, sistemas `running`.

### Dev (60.8) y Prod (60.5) — VMs
- Kernel nuevo instalado y **reiniciadas** (dev 6.12.86, prod 6.12.94). El kernel anterior queda como fallback en GRUB.
- **LLMNR/mDNS** desactivado en dev (puerto 5355). `SUDO_PASS` removido de los `.env`.
- **Swap**: dev `/swapfile` 4 GB, prod `/swapfile` 8 GB (`nofail`, `swappiness=10`).
- **Backups de DB (PROD)**: cron diario `backup-db.sh` + sistema robusto en `/srv/monstruo/.ops/backup/` (`backup_full.sh` 03:30 + `restore_test_weekly.sh` domingos). Verificado OK.
- Limpieza: Samba **purgado** en prod (ya no se usa, se accede por VS Code remoto), terreneitor **legacy** (`/srv/terreneitor*`) eliminado — el oficial vive en Docker dentro de monstruo.

### Proxy (60.6) — borde
- **Firewall nftables** (ver §4).
- **nginx**: `server_tokens off`, **`default_server` catch-all → 444** (Host/SNI desconocido se cierra), headers de seguridad (HSTS / X-Frame-Options / X-Content-Type-Options / Referrer-Policy) en los sites de monstruo vía `/etc/nginx/snippets/security-headers.conf`.
- **Sacados del borde**: `ultron` (Vite dev server ajeno) y `ia.telconsulting.cl/dev/` (→ subred IA 20.228, ahora 503). `sapa` (Home Assistant) **se mantiene**.
- **Certs**: borrados los vencidos `gpsjuan`/`pruebagps.duckdns`; certbot fuera de `failed`; cron certbot duplicado removido. Renovación automática por `certbot.timer`.
- **Disco** (era 100%): liberado limpiando caches de IDEs remotos (Antigravity, Codex, etc.). **VS Code server (`/root/.vscode-server`) se respeta.** Decisión: no usar IDEs pesados en el proxy (editar configs desde otra máquina).
- **Swap**: es LXC → el swap (512 MB) lo asigna el **host Proxmox**. Para más, ajustar en Proxmox (container → Memory/Swap), no internamente.
- **Backup de configs** (nuevo): `/usr/local/bin/backup-proxy-configs.sh` + cron 04:30 (tar de nginx/letsencrypt/nftables/fail2ban/ssh en `/root/config-backups/`, retención 14 d).

## 4. Firewall del proxy (nftables) — `/etc/nftables.conf`

Familia `inet`, **política input = DROP**. Permite:
- `established,related` y loopback.
- **Todo desde `192.168.60.0/24`** (LAN de servidores — anti-lockout).
- ICMP v4/v6 (ping/diagnóstico).
- **80/443 desde cualquiera** (web pública).
- **22 desde `192.168.0.0/16` + `10.0.0.0/8`** (redes privadas/VPN de administración).
- Todo lo demás: **rechazado**.

`nftables` está `enabled` (persiste en reboot). Probado en caliente sin lockout.

## 5. Comandos de rescate / operación

| Situación | Qué hacer |
|-----------|-----------|
| Firewall del proxy me deja afuera | Por **consola Proxmox** del container: `nft flush ruleset` (borra todas las reglas) |
| nginx no arranca tras cambios | `nginx -t` (validar); si OK pero `failed`, matar procesos viejos (`pkill nginx`) y `systemctl start nginx` |
| Revertir config del proxy | Backups en `proxy:/root/audit_backup_20260628/` y `proxy:/root/config-backups/` |
| Necesito sudo sin password (dev/prod) | Pedir a Juan que ponga `/etc/sudoers.d/99-juan-temp` con NOPASSWD; **quitarlo al terminar** |
| Subir cambios a una VM | `dev-rebuild.sh` para containers; ediciones de config validar antes de recargar |

## 6. Pendientes / notas

- **Apps (otra sesión, NO infra):** hallazgos de seguridad de código sin tocar — GTA usa `gta:read` en endpoints de escritura (debería ser `gta:write`), login del gateway sin rate-limit, secretos hardcodeados en `terreneitor` `SEED_USERS`, deps de terreneitor con CVE. Detalle en la memoria del agente.
- **Proxy swap**: si se necesita más, ajustar en Proxmox (es LXC).
- **Proxy disco**: chico (7.4 GB); no instalar IDEs pesados ahí.
- **Backup del container proxy**: idealmente configurar **vzdump** en Proxmox (respaldo del container completo), complementario al backup de configs interno.

---
*Última actualización: 2026-06-28 — auditoría y hardening de las 3 máquinas (dev, prod, proxy).*
