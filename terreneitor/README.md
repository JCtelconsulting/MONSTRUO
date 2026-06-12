# Terreneitor

Sistema de Gestión Operativa (Libro de Obras Digital).

## 🚀 Inicio Rápido

### En Producción (Servidor con Proxy Inverso)
El servidor utiliza Nginx como proxy para SSL y balanceo.
```bash
./start.sh
```

### En Desarrollo Local (Tu PC sin Proxy)
Si quieres trabajar en tu laptop sin complicaciones de red:
```bash
# Iniciar App + DB + AI directamente
docker compose -f docker/docker-compose.dev.yml up -d --build
```
La aplicación estará disponible en: [http://localhost:8000](http://localhost:8000)

## 📚 Documentación
- **[Plan Maestro](docs/PLAN_MAESTRO.md)**: Visión, Roadmap y Reglas de Oro.
- **[Contexto Proyecto](docs/PROYECTO_CONTEXTO.md)**: Bitácora de sesiones y decisiones técnicas.
- **[Handover Técnico](docs/HANDOVER_TECNICO.md)**: Guía para desarrolladores y mantenimiento.

### Manuales de Usuario
- [Manual Terreno](docs/manuales/usuario_terreno.md)
- [Manual Supervisor](docs/manuales/usuario_supervisor.md)
- [Manual Gerencia](docs/manuales/usuario_gerencia.md)
- [Manual Portal/Admin](docs/manuales/usuario_portal.md)

## 📂 Organización del Proyecto
*   **`code/`**: Backend FastAPI y Frontend Modular.
*   **`docker/`**: Configuraciones de despliegue (Prod y Dev).
*   **`ops/scripts/`**: Automatización (Backup, Mantenimiento, Estructura).
*   **`data/`**: Persistencia (SQLite y Fotos).
*   **`docs/`**: Documentación técnica.
*   **`logs/`**: Registros centralizados.
# Trigger workflow con permisos sudo configurados
# Test sudo
# Re-test workflow
