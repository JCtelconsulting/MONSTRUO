-- Fundación — vistas para reportes y dashboard.
--
-- Centralizamos el cálculo de % de asistencia y nivel de riesgo acá para que
-- la regla quede en UN solo lugar. Si cambian los códigos válidos o la
-- fórmula, se modifica esta migración.

-- Fórmula oficial (ver fundacion/docs/REGLAS_NEGOCIO.md):
--   % asistencia = P / (P + A + AJ)
--   Riesgo: <50% = alto, 50–75% = medio, ≥75% = bajo
--   F/V, ST, NM, FLEX se ignoran en el cálculo.

CREATE OR REPLACE VIEW fundacion.v_alumno_kpi AS
SELECT
    a.id                                                            AS alumno_id,
    a.sede_id,
    a.correlativo,
    a.nombre_completo,
    a.rut,
    a.curso_after,
    a.plan,
    a.gestora_a_cargo,
    a.estado_alumno,
    a.estado_matricula,
    a.matricula_activa,
    a.riesgo_desercion                                              AS riesgo_planilla,
    a.presente_en_planilla,
    -- contadores
    COUNT(ad.id) FILTER (WHERE ad.codigo = 'P')                     AS dias_presente,
    COUNT(ad.id) FILTER (WHERE ad.codigo = 'A')                     AS dias_ausente,
    COUNT(ad.id) FILTER (WHERE ad.codigo = 'AJ')                    AS dias_justificado,
    COUNT(ad.id) FILTER (WHERE ad.codigo = 'F/V')                   AS dias_feriado,
    COUNT(ad.id) FILTER (WHERE ad.codigo = 'ST')                    AS dias_suspendido,
    COUNT(ad.id) FILTER (WHERE ad.codigo = 'NM')                    AS dias_no_matriculado,
    COUNT(ad.id) FILTER (WHERE ad.codigo = 'FLEX')                  AS dias_flex,
    COUNT(ad.id) FILTER (WHERE ad.codigo_conocido = FALSE)          AS dias_desconocido,
    COUNT(ad.id) FILTER (WHERE ad.codigo IN ('P','A','AJ'))         AS dias_contables,
    -- % asistencia (NULL si no hay días contables)
    ROUND(
        100.0 * COUNT(ad.id) FILTER (WHERE ad.codigo = 'P')
              / NULLIF(COUNT(ad.id) FILTER (WHERE ad.codigo IN ('P','A','AJ')), 0),
        1
    )                                                               AS pct_asistencia,
    -- Nivel de riesgo según asistencia (NULL si no hay datos suficientes)
    CASE
        WHEN COUNT(ad.id) FILTER (WHERE ad.codigo IN ('P','A','AJ')) = 0 THEN NULL
        WHEN 100.0 * COUNT(ad.id) FILTER (WHERE ad.codigo = 'P')
                   / COUNT(ad.id) FILTER (WHERE ad.codigo IN ('P','A','AJ')) < 50 THEN 'alto'
        WHEN 100.0 * COUNT(ad.id) FILTER (WHERE ad.codigo = 'P')
                   / COUNT(ad.id) FILTER (WHERE ad.codigo IN ('P','A','AJ')) < 75 THEN 'medio'
        ELSE 'bajo'
    END                                                             AS nivel_riesgo
FROM fundacion.alumnos a
LEFT JOIN fundacion.asistencia_diaria ad ON ad.alumno_id = a.id
GROUP BY a.id;


CREATE OR REPLACE VIEW fundacion.v_sede_kpi AS
SELECT
    s.id                                                            AS sede_id,
    s.code                                                          AS sede_code,
    s.nombre                                                        AS sede_nombre,
    s.cupos,
    COUNT(DISTINCT a.id)                                            AS alumnos_total,
    COUNT(DISTINCT a.id) FILTER (WHERE a.matricula_activa)          AS alumnos_activos,
    COUNT(DISTINCT a.id) FILTER (
        WHERE a.matricula_activa AND a.presente_en_planilla
    )                                                               AS alumnos_visibles,
    -- Asistencia agregada de toda la sede
    SUM(CASE WHEN ad.codigo = 'P' THEN 1 ELSE 0 END)                AS p_total,
    SUM(CASE WHEN ad.codigo IN ('P','A','AJ') THEN 1 ELSE 0 END)    AS contables_total,
    ROUND(
        100.0 * SUM(CASE WHEN ad.codigo = 'P' THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN ad.codigo IN ('P','A','AJ') THEN 1 ELSE 0 END), 0),
        1
    )                                                               AS pct_asistencia_sede
FROM fundacion.sedes s
LEFT JOIN fundacion.alumnos a ON a.sede_id = s.id
LEFT JOIN fundacion.asistencia_diaria ad ON ad.alumno_id = a.id
WHERE s.activo = TRUE
GROUP BY s.id, s.code, s.nombre, s.cupos, s.orden
ORDER BY s.orden, s.code;


-- Asistencia agregada por sede y mes — para gráfico temporal del dashboard.
CREATE OR REPLACE VIEW fundacion.v_asistencia_mensual AS
SELECT
    s.id                                                            AS sede_id,
    s.code                                                          AS sede_code,
    s.nombre                                                        AS sede_nombre,
    date_trunc('month', ad.fecha)::date                             AS mes,
    EXTRACT(YEAR FROM ad.fecha)::int                                AS anio,
    EXTRACT(MONTH FROM ad.fecha)::int                               AS mes_num,
    COUNT(*) FILTER (WHERE ad.codigo = 'P')                         AS p_total,
    COUNT(*) FILTER (WHERE ad.codigo IN ('P','A','AJ'))             AS contables_total,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE ad.codigo = 'P')
              / NULLIF(COUNT(*) FILTER (WHERE ad.codigo IN ('P','A','AJ')), 0),
        1
    )                                                               AS pct_asistencia
FROM fundacion.sedes s
JOIN fundacion.alumnos a ON a.sede_id = s.id
JOIN fundacion.asistencia_diaria ad ON ad.alumno_id = a.id
WHERE s.activo = TRUE
GROUP BY s.id, s.code, s.nombre, date_trunc('month', ad.fecha),
         EXTRACT(YEAR FROM ad.fecha), EXTRACT(MONTH FROM ad.fecha)
ORDER BY s.orden, mes;
