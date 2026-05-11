# Fundación — Reglas de negocio

Diccionarios, fórmulas y reglas operativas que vienen del trabajo real de la
Fundación. Fuente: hoja **"Gobernanza de Datos"** de las planillas de
matrícula y asistencia que cada sede mantiene en Google Drive.

Si las reglas cambian en las planillas, este doc debe actualizarse y el código
que las implementa también.

---

## Sedes

Una **sede** es un **establecimiento educacional**. La Fundación opera hoy en 7:

| Code (slug) | Nombre | Cupos |
|---|---|---|
| `el-buen-camino` | Sede El Buen Camino | 60 |
| `liceo-francisco-mery` | Liceo Francisco Mery | — |
| `instituto-padre-hurtado` | Instituto Padre Hurtado | 30 |
| `escuela-basica-las-palmas` | Escuela Básica Las Palmas | — |
| `escuela-domingo-santa-maria` | Escuela Domingo Santa María | — |
| `colegio-san-sebastian` | Colegio San Sebastián | — |
| `colegio-cree` | Colegio CREE | — |

**Pendiente:** códigos cortos oficiales (EBC, IPH son los únicos confirmados),
comuna y cupos de las 5 sedes sin completar.

---

## Códigos de asistencia

Cada celda de la planilla de Asistencia (una columna por día) usa uno de estos
códigos:

| Código | Significado | ¿Asistió? | ¿Cuenta para el denominador del % de asistencia? |
|---|---|---|---|
| **P** | Presente | Sí | Sí |
| **A** | Ausente | No | Sí |
| **AJ** | Ausente Justificado | No | Sí |
| **F/V** | Feriado o Vacaciones | No | **No** |
| **ST** | Suspensión de Taller | No | **No** |
| **NM** | No Matriculado (aún) | No | **No** |
| **FLEX** | Plan flexible — día que no le toca venir | No | **No** |

### Fórmula del % de asistencia

```
% asistencia = P / (P + A + AJ)
```

Los códigos `F/V`, `ST`, `NM` y `FLEX` **no se cuentan** ni en el numerador ni
en el denominador.

---

## Niveles de riesgo de deserción

Se calculan a partir del % de asistencia acumulado del alumno:

| Nivel | Rango |
|---|---|
| **Alto** | < 50% |
| **Medio** | 50% — 75% |
| **Bajo** | ≥ 75% |

---

## Roles operativos (planilla)

Coinciden con los roles ya modelados en la app (ver
`fundacion_roles_organigrama`).

| Rol | Responsabilidad en planillas | Supervisado por |
|---|---|---|
| Gestora Educativa | Rellena matrícula y asistencia | Líder Educativa |
| Líder Educativa | Rellena + supervisa + recuerda relleno + resuelve dudas | Coordinadora Territorial |
| Coordinadora Territorial | Supervisión territorial | Directora Social / Jefa Pedagógica |
| Directora Social | Nivel de dirección | — |
| Jefa Pedagógica | Nivel de jefatura técnica | — |

---

## Hojas de cada planilla por sede

Cada planilla de Google Sheets tiene esta estructura (7 hojas):

| Hoja | Contiene |
|---|---|
| Gobernanza de Datos | Diccionario (lo de arriba), códigos de sede, cupos, roles |
| Matriculas | Datos de los alumnos (44 columnas: niño, cuidador, estado, fechas) |
| Asistencia | Una fila por alumno, una columna por día (códigos de arriba) |
| Consolidado Asistencia | Agregado calculado a partir de Asistencia |
| Gestión de Riesgos | Acciones registradas para niños/as con riesgo alto |
| KPI's Asistencia | % asistencia mensual / semestral / anual |
| Tabulados Matriculas | Cortes para análisis |

La app debe **leer** las dos primeras (Matriculas, Asistencia) y **recalcular**
todo lo demás. Los KPIs y consolidados de la planilla son referencia, no fuente.
