---
description: Rebuild + smoke test de containers DEV. Uso. /deploy-dev gateway gta
argument-hint: <containers separados por espacio, o vacío para rebuild full-stack>
allowed-tools: Bash
---

# /deploy-dev

Rebuildea los containers DEV indicados con `ASSET_VERSION` igual al SHA actual y verifica `/health` de cada uno. Si no se especifica ningún container, rebuildea todo el stack.

## Args

`$ARGUMENTS` = lista de containers separados por espacio (`gateway`, `gta`, `ticketera`, `fundacion`, `crm`, `erp`, `bodega`).

## Pasos

1. Determinar SHA actual: `SHA=$(git -C /srv/monstruo_dev rev-parse --short HEAD)`.
2. Validar que el repo no tiene cambios sin commitear que pueden romper el build (avisar pero no bloquear).
3. Ejecutar el rebuild:
   ```bash
   ASSET_VERSION="$SHA" \
     APP_UID=$(id -u) APP_GID=$(id -g) \
     docker compose --env-file /srv/monstruo_dev/plataforma/ops/env/.env.server.dev \
     up -d --build $ARGUMENTS
   ```
   Si `$ARGUMENTS` está vacío, rebuildea todo.
4. Esperar 3 segundos para health checks.
5. Para cada container rebuildeado, hacer `curl -fsS http://127.0.0.1:<puerto>/health` y reportar:
   - PASS/FAIL por servicio
   - Tiempo total

## Mapa de puertos (para los curl)

| Container | Puerto |
|---|---|
| gateway | 9001 |
| ticketera | 9005 |
| fundacion | 9006 |
| bodega | 9007 |
| crm | 9008 |
| erp | 9009 |
| gta | 9012 |

## Salida esperada

Reporte corto, una línea por container:

```text
gateway: rebuild OK, /health 200 (320ms)
gta:     rebuild OK, /health 200 (180ms)
TOTAL:   2/2 PASS en 41s
```

Si algo falla, mostrar las últimas 20 líneas de `docker logs <container>` del que falló.
