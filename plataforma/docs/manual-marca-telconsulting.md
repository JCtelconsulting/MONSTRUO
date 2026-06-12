# Manual de Marca — Telconsulting

> Guía oficial para mantener consistencia visual en todos los materiales: web, firmas de correo, brochures, presentaciones, redes sociales y papelería.
>
> **Autorización:** Diego aprobó el 2026-05-28 que Juan tiene autoridad total para revisar y aplicar cambios de imagen corporativa en todos los materiales.
>
> **Concepto rector:** "Premium Gold" sobre fondo oscuro. Tono corporativo serio, conectividad resiliente, con detalles dorados que aportan calidez sin ser ostentosos.
>
> Última actualización: 2026-06-02

---

## 1. Paleta de colores

| Nombre | HEX | RGB | Uso principal |
|---|---|---|---|
| Dorado Premium | `#D4A843` | 212, 168, 67 | Acento principal: CTAs, badges, bordes, hovers |
| Azul Corporativo | `#0B111F` | 11, 17, 31 | Detalles mínimos únicamente (no como fondo principal) |
| Fondo Oscuro | `#050505` | 5, 5, 5 | Fondo principal |
| Blanco | `#FFFFFF` | 255, 255, 255 | Texto principal sobre fondo oscuro |
| Negro | `#000000` | 0, 0, 0 | Sombras |

**Variaciones del dorado (transparencias):**

| Token | Valor | Uso |
|---|---|---|
| Glow suave | `rgba(212, 168, 67, 0.6)` | Resplandor en hovers |
| Glow intenso | `rgba(212, 168, 67, 0.9)` | Resplandor en CTAs principales |
| Borde sutil | `rgba(212, 168, 67, 0.2)` | Borde de tarjetas y secciones |
| Vidrio | `rgba(5, 5, 5, 0.75)` | Overlays sobre imágenes |

### Reglas de uso del color

- **Fondo siempre oscuro.** Usar Fondo Oscuro `#050505` o negro. No usar fondos blancos ni claros.
- **Azul casi no se usa.** Solo para detalles mínimos (íconos chicos, líneas decorativas). NO como fondo principal de secciones.
- **Texto principal blanco.** Nunca negro o gris bajo contraste sobre fondo oscuro.
- **Dorado con moderación.** Solo para acentos: CTAs, bordes activos, hovers, badges. Nunca como fondo plano de un bloque entero.
- **No inventar colores.** Si necesitas estados (éxito, error, advertencia), consultar antes.

> **Nota de aplicación en Terreneitor (app interna):** la app necesita colores
> funcionales de estado para usabilidad. Mapeo aplicado: positivo/hecho = dorado,
> error/rechazo = rojo, advertencia = naranjo, neutro/pendiente = gris. Pendiente
> confirmar con Diego si quiere colores de estado específicos de marca.

---

## 2. Tipografía

### Familias

- **MADE TOMMY** — Light, Regular, Bold — identidad principal
- **Dosis** — 400, 700 — fallback / web (Google Fonts)

### Jerarquía

| Uso | Familia | Tamaño |
|---|---|---|
| Título hero | MADE TOMMY Bold | Grande, escalable |
| Subtítulo sección | MADE TOMMY Bold | Mediano |
| Body | MADE TOMMY Regular | Normal |
| Subtítulo sutil | MADE TOMMY Light | Pequeño |

**Patrón típico:** la palabra clave del título va destacada en dorado (`<b>` en HTML, negrita en otros formatos).

---

## 3. Logo

> **Logo oficial (2026):** cubo hexagonal dorado metálico + wordmark "TELCONSULTING". Reemplaza al antiguo logo verde (retirado). Todas las variantes oficiales viven en `Proyectos/Branding/Logo/`.

### Variantes oficiales (resumen)

- **Completo dorado** (PNG, transparente): principal sobre fondo oscuro (web, firmas, slides).
- **Completo blanco / negro:** monocromo sobre foto / fondo claro o 1 tinta.
- **Isotipo (solo cubo):** favicon, avatar, marca de agua, espacios chicos.
- **SVG (dorado/blanco/negro):** gran formato/impresión (silueta plana `#D4A843`; el degradado metálico solo existe en PNG).

### Reglas

- Espacio mínimo alrededor = altura del cubo. Fondo preferente oscuro.
- Usar solo variantes oficiales — no recolorear/deformar/rotar/sombrear.
- **Logo verde antiguo: RETIRADO.** No usar en materiales nuevos.

---

## 6. Don'ts (qué NO hacer)

- ❌ Hardcodear colores fuera de la paleta oficial
- ❌ Usar `px` para tipografía en web (usar `rem`)
- ❌ Crear nuevos botones sin revisar los existentes
- ❌ Agregar fuentes nuevas — la identidad es MADE TOMMY
- ❌ Backgrounds claros / blancos
- ❌ Logo verde antiguo (RETIRADO)
- ❌ Voseo / chilenismos en comunicación oficial
- ❌ Mezclar estilos fotográficos

---

> Manual completo (con secciones 4 imágenes, 5 aplicaciones por canal, firmas,
> brochure, presentaciones, redes, papelería) provisto por Juan el 2026-06-11.
> Aquí se conserva lo relevante para el recoloreo de la app. Referencia web:
> `~/Documentos/WEB Telconsulting/web-telconsulting-frontend/docs/design.md`.
