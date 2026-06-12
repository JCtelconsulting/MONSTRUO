# Guía de diseño — Ecosistema Monstruo

> Fuente única de la línea visual. Reemplaza a la "Guía Visual de la App" que
> vivía al final del Dashboard (retirada el 2026-06-12). Las **reglas de marca**
> (colores oficiales, logo, tipografía, don'ts) viven en
> [manual-marca-telconsulting.md](manual-marca-telconsulting.md) — ese manual
> manda; esta guía lo aterriza a la app.

## Identidad: Premium Gold

Desde 2026-06-12 todo el ecosistema (Monstruo + Terreneitor) usa la identidad
**Premium Gold** del manual de marca:

| Token | Valor | Uso |
|---|---|---|
| Acento (`--neon`) | `#D4A843` | CTAs, badges, bordes activos, hovers, íconos de la barra |
| Fondo (`--bg-deep`) | `#050505` | Fondo principal (nunca claro/blanco) |
| Texto | `#F5F7F8` / `--text-soft #A5ADB4` | Principal / secundario |
| Error (`--danger`) | `#FF3333` | Errores, rechazos, salir |
| Aviso (`--warning`) | `#FFCC00` | Advertencias |
| Glow | `rgba(212,168,67, .2/.6/.9)` | Borde sutil / hover / CTA |

- **Marca de agua**: el cubo Telconsulting va de fondo en todos los módulos
  (`body::after`, opacity .05, en `monstruo.css`); el login y el hub de
  Terreneitor usan el logo completo (.09–.10). No subir esas opacidades.
- **Dorado con moderación**: nunca como fondo plano de un bloque.
- Estados funcionales tipo semáforo se mantienen (hecho=dorado/ok, error=rojo,
  aviso=naranjo/amarillo, neutro=gris). No inventar colores nuevos.

## Fuente oficial de UX: patrones PMO + ERP

PMO y ERP son la referencia canónica de UX para Monstruo. No se aceptan
variantes visuales paralelas.

| Pieza | Patrón |
|---|---|
| Layout | `section-block` + `section-header` (contenedor principal SIN cuadro de fondo) |
| Navegación | `tab-bar` + `tab-btn` |
| Datos | `monstruo-table` / `erp-table` |
| Acción | `btn-primary` sobre superficie oscura |
| Barra lateral | `#dynamic-sidebar` + `shared/js/sidebar.js` (NO copiarla: cargarla; Terreneitor la consume vía proxy `/shared/*`) |

## Contrato de componentes

Composición mínima uniforme para que cualquier agente intervenga sin romper
consistencia:

```
div.main-inner.module-shell
  div.section-header.module-tabs-header.module-shell-header
  div.tab-bar (si aplica)
  section.section-block.module-shell-content
```

- Botones: padding/font-size/min-height viven SOLO en `monstruo.css` bloque
  BOTONES. No inventar estilos inline.
- Tablas y modales en superficie oscura consistente.

## Estados y feedback

Toda pantalla debe comunicar **carga, éxito y error** sin cajas blancas ni
estilos nativos del navegador (toasts oscuros, skeletons, badges de estado).

## Checklist obligatorio antes de cerrar un cambio de UI

1. Paleta Premium Gold (`--neon` dorado, `--danger`, `--warning`) — sin verdes
   del tema antiguo (#00ff41/#00f3ff: RETIRADOS).
2. Sin cajas blancas ni inputs nativos sin tema (ojo: `<option>` de selects
   necesita fondo oscuro explícito).
3. Contenedor principal sin cuadro (transparente).
4. Tablas/modales en superficie oscura consistente.
5. Evitar inline style salvo excepción justificada.
6. No romper contratos públicos del módulo.
7. Tipografía: la identidad es MADE TOMMY (impresos) / Dosis (web). No agregar
   fuentes nuevas.
8. Verificar en navegador real (Playwright) y MIRAR el screenshot antes de dar
   por cerrado (0 errores de consola, 0 imágenes rotas).

## Referencias

- Reglas de marca completas: [manual-marca-telconsulting.md](manual-marca-telconsulting.md)
- Logos oficiales: `gateway/frontend/shared/ui/img/` (ecosistema) y
  `terreneitor/frontend/modulos/_compartido/img/logo/` (set completo)
- Estándares de código: [ESTANDARES.md](ESTANDARES.md)
