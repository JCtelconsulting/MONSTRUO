# Gateway Perimetral (Monstruo OS)

Este servicio es el "Portero" o Fachada de toda la plataforma MONSTRUO. Actúa como un API Gateway, un servidor de archivos estáticos para la interfaz de usuario, y el gestor centralizado de autenticación.

## Objetivo
Unificar el punto de entrada para los usuarios, manejar la seguridad perimetral (autenticación y sesiones) y enrutar las peticiones al microservicio correspondiente.

## Arquitectura y Módulos Principales
Sigue el patrón **Package-by-Feature**, estructurado en:

*   `backend/`: La aplicación FastAPI responsable de la seguridad y el ruteo inverso.
*   `frontend/`: Los archivos estáticos compartidos y las vistas transversales del sistema (HTML/CSS/JS).

## Funciones Clave del Backend

1.  **Proxy Inverso (Ruteo):**
    *   Recibe todas las peticiones desde el exterior (tras pasar por Nginx) en el puerto `9001`.
    *   Enruta dinámicamente las llamadas API (`/api/{service}/*`) hacia el contenedor del servicio interno adecuado (ej. `ticketera`, `erp`, `bodega`) usando `SERVICES_MAP`.
2.  **Autenticación Centralizada (Login):**
    *   Provee el endpoint `/api/auth/login` y emite JWT en cookies seguras (`Secure`, `HttpOnly`, `SameSite=Lax`).
    *   Utiliza el SDK de `plataforma/core` para verificar las contraseñas y roles de la base de datos.
3.  **Gestión de Roles y Permisos (RBAC):**
    *   Controla el acceso a las rutas (Middleware `AuthIdentityMiddleware`). Ningún servicio es accesible si el token no es válido o si falta el scope necesario.
4.  **Servidor de Archivos Estáticos:**
    *   Se encarga de servir las interfaces de usuario (HTML) y calcular el ruteo según el subdominio de entrada (`ticketera.telconsulting.cl` vs `login.telconsulting.cl`).

## Componentes del Frontend (UI)

El frontend del Gateway contiene las vistas que no pertenecen a un módulo específico:

*   **Login:** La página de inicio de sesión (`frontend/login`).
*   **Dashboard de Operaciones:** El tablero principal que consolida KPIs (`frontend/dashboard`).
*   **Configuración:** Panel administrativo para gestionar usuarios y roles (`frontend/configuracion`).
*   **Shared (El Estándar Visual):** La carpeta `frontend/shared/ui/` es la **fuente canónica de recursos compartidos** (estilos base `monstruo.css`, scripts comunes `sidebar.js`, `admin.js`, utilidades). Todas las demás aplicaciones (ej. `ticketera`) apuntan a esta carpeta compartida para cargar la shell común (sidebar + topbar) y mantener la coherencia visual.