# Módulo: Fundación 🏫

## Propósito
Gestión social y educativa de la Fundación Telconsulting: sedes, membresías por
sede, roles del organigrama (directora social, jefa pedagógica, coordinadora
territorial, líder educativo, gestora educativa, ejecutiva) y sincronización con
Google Drive. Corre aislado en su carpeta (mismo repo), con routing por dominio
de correo.

## Estructura Local
- `backend/main.py`: API del módulo (prefijo `/api/fundacion`).
- `backend/router.py` + `backend/routers/{reportes,sesiones,sync}.py`: endpoints.
- `backend/services/`: `drive_sync`, membresías, sedes.
- `ui/`: vistas del módulo.
- `migrations/`: migraciones SQL versionadas.

## Configuración Canónica
- **Puerto Dev:** 9006

## Documentación
- Reglas de negocio: [docs/REGLAS_NEGOCIO.md](docs/REGLAS_NEGOCIO.md).
- Estado del módulo: [ESTADO.md](ESTADO.md).

---
*Referencia: Se rige por la [Guía Maestra](../plataforma/docs/GUIA_MAESTRA.md).*
