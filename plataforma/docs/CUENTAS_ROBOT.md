# Cuentas robot (service accounts)

Registro central de cuentas de servicio usadas por las apps de Monstruo.
**Regla:** toda cuenta robot creada debe quedar listada acá, con su propósito y dónde está el JSON de credenciales. Si no está acá, no existe.

---

## Formato de cada entrada

- **Email:** el correo de la cuenta (`xxx@yyy.iam.gserviceaccount.com`)
- **Proyecto Google Cloud:** dónde vive
- **Propósito:** para qué se usa, qué app
- **Recursos compartidos:** qué planillas / carpetas / APIs tiene acceso
- **Credenciales:** path del JSON en el server
- **Creada:** fecha (YYYY-MM-DD)
- **Estado:** activa / suspendida / eliminada

---

## Activas

### `monstruo-fundacion`

- **Email:** `monstruo-fundacion@monstruo-488320.iam.gserviceaccount.com`
- **Proyecto Google Cloud:** `monstruo-488320`
- **Propósito:** Leer las planillas de matrícula y asistencia de las 7 sedes de Fundación desde Google Sheets, para sincronizarlas a la DB de Monstruo todos los días.
- **Recursos compartidos (planillas con permiso de lector):**
  - Sede El Buen Camino — Matrículas y Asistencia 2026 ✅ validada
  - Liceo Francisco Mery — Matrículas y Asistencia 2026
  - Instituto Padre Hurtado — Matrículas y Asistencia 2026
  - Escuela Básica Las Palmas — Matrículas y Asistencia 2026
  - Escuela Domingo Santa María — Matrículas y Asistencia 2026
  - Colegio San Sebastián — Matrículas y Asistencia 2026
  - Colegio CREE — Matrículas y Asistencia 2026
- **APIs habilitadas:** Google Sheets API, Google Drive API
- **Credenciales:** `/srv/monstruo_dev/plataforma/ops/secrets/monstruo-fundacion-drive.json` (permisos `600`, ignorada por git vía `plataforma/ops/secrets/`)
- **Creada:** 2026-05-11
- **Estado:** activa, lectura de planilla "El Buen Camino" probada y funcionando
- **Pendiente:** confirmar que las otras 6 planillas estén compartidas con la SA

---

## Suspendidas / eliminadas

Ninguna por ahora.
