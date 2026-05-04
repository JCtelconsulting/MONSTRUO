# Plantillas de Entorno

Directorio unico para plantillas de variables de entorno.
La raiz del repo queda reservada para archivos operativos.

Archivos:
- `env.base.example`: base generica.
- `env.local.example`: desarrollo local.
- `env.server.example`: servidor productivo.
- `env.server.dev.example`: servidor DEV (staging interno).

Uso rapido:
```bash
cp docs/deploy/plantillas_env/env.local.example .env.local
cp docs/deploy/plantillas_env/env.server.example .env.server
cp docs/deploy/plantillas_env/env.server.dev.example .env.server.dev
```
