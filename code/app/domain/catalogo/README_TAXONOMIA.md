# Manual de Taxonomía y Clasificación (Módulo Bodega)

Este documento define la **Fuente de Verdad** para la clasificación de inventario en el módulo de Bodega de Monstruo.
Cualquier script de clasificación automática (IA) o proceso manual debe adherirse estrictamente a estas reglas.

---

## 1. Estructura del Árbol de Categorías

La jerarquía tiene una profundidad máxima recomendada de 4 niveles.
La raíz siempre es **Bodega**.

### A. Equipos de Red (Networking)
Reglas estrictas para Switches y Routers. La profundidad depende de la capacidad física (puertos).

*   **Nivel 1:** Bodega
*   **Nivel 2:** Equipos
*   **Nivel 3:** Switches | Routers
*   **Nivel 4:** (Según cantidad de puertos detectada)
    *   `48 Puertos` (si nombre/descripción tiene "48")
    *   `24 Puertos` (si nombre/descripción tiene "24")
    *   `16 Puertos` (si nombre/descripción tiene "16")
    *   `8 Puertos` (si nombre/descripción tiene "8")
    *   `4-5 Puertos` (si nombre/descripción tiene "5" o "4")

**Ejemplo:**
> Item: "Switch Mikrotik CRS326-24G"
> Ruta: `['Bodega', 'Equipos', 'Switches', '24 Puertos']`

### B. Materiales y Cables
Para insumos de conectividad.

*   **Nivel 1:** Bodega
*   **Nivel 2:** Materiales
*   **Nivel 3:** Cables
*   **Nivel 4:** Tipo específico
    *   `Fibra Optica`
    *   `UTP Exterior`
    *   `HDMI`
    *   `Patch Cord`

### C. Categorías Generales (Otros)
Para todo lo que no es networking activo ni cableado estructurado.

*   **Nivel 1:** Bodega
*   **Nivel 2:** (Elegir UNA)
    *   `Ferreteria`
    *   `Herramientas`
    *   `Seguridad` (Cámaras, sensores)
    *   `Energia` (UPS, fuentes de poder)
    *   `Otros`
*   **Nivel 3:** Nombre específico del sub-tipo (ej. Tornillos, Taladros, Cascos).

---

## 2. Reglas de Normalización

Todo ítem debe procesarse para extraer atributos estructurados y limpiar su nombre visual.

### Atributos Obligatorios (JSON)
*   `marca`: Extraer siempre. Si no existe, usar "".
*   `modelo`: Extraer si es visible.
*   `puertos`: (Solo Networking) Número entero.
*   `color`: (Solo Cables/Materiales) Si aplica.

### Nombre Canónico
*   Usar **Title Case** (Mayúscula inicial).
*   Mantener Marca y Modelo.
*   **ELIMINAR** palabras de relleno: "Unidad", "Caja", "Pack".

---

## 3. Criterios de Decisión (Humano vs IA)

1.  **Certeza:** Si la IA tiene duda (< 50% confidence), debe clasificar como `['Bodega', 'Sin Clasificar', 'Pendiente']`.
2.  **Duplicados:** La IA puede *sugerir* duplicados, pero **NUNCA** fusionar (merge) automáticamente sin confirmación humana explícita.
3.  **Prioridad:** Si existe una clasificación manual previa para un SKU, esta prevalece sobre la sugerencia automática.

---

## 4. Referencia Técnica

La lógica de clasificación automática actual reside en:
`code/backend/domain/catalogo/catalogo_seed_ai.py`
(Función `BASE_SYSTEM_PROMPT`).

---
**Última actualización:** 27 Enero 2026
