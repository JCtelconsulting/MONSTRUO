-- Fundación — vistas SQL para los 5 reportes pedagógicos del correo de la
-- encargada (a/b/c/d/f). La lógica vive acá para que los endpoints solo hagan
-- SELECT * FROM v_xxx con filtros.

-- (a) Cobertura por dimensión — cuántos bloques de cada tipo + subtipo se
--     ejecutaron, por sede y rango de fechas.
CREATE OR REPLACE VIEW fundacion.v_cobertura_bloques AS
SELECT
    sd.sede_id,
    s.code                                              AS sede_code,
    s.nombre                                            AS sede_nombre,
    sd.fecha,
    bt.codigo                                           AS bloque_codigo,
    bt.nombre                                           AS bloque_nombre,
    bs.codigo                                           AS subtipo_codigo,
    bs.nombre                                           AS subtipo_nombre,
    COUNT(*) FILTER (WHERE sb.se_ejecuto)               AS ejecutados,
    COUNT(*) FILTER (WHERE NOT sb.se_ejecuto)           AS no_ejecutados,
    COUNT(*)                                            AS planificados
FROM fundacion.sesion_dia sd
JOIN fundacion.sedes s          ON s.id = sd.sede_id
JOIN fundacion.sesion_bloque sb ON sb.sesion_dia_id = sd.id
JOIN fundacion.bloque_tipos bt  ON bt.id = sb.bloque_tipo_id
LEFT JOIN fundacion.bloque_subtipos bs ON bs.id = sb.bloque_subtipo_id
GROUP BY sd.sede_id, s.code, s.nombre, sd.fecha, bt.codigo, bt.nombre, bs.codigo, bs.nombre;


-- (b) Competencias trabajadas — cuántas veces se trabajó cada competencia,
--     en qué nivel, por sede y rango. Una "vez" = una aparición en un bloque
--     que se ejecutó.
CREATE OR REPLACE VIEW fundacion.v_competencias_trabajadas AS
SELECT
    sd.sede_id,
    s.code                                              AS sede_code,
    s.nombre                                            AS sede_nombre,
    sd.fecha,
    c.codigo                                            AS competencia_codigo,
    c.descripcion                                       AS competencia_descripcion,
    d.codigo                                            AS dominio_codigo,
    d.nombre                                            AS dominio_nombre,
    bt.codigo                                           AS bloque_codigo,
    bt.nombre                                           AS bloque_nombre,
    COUNT(*) FILTER (WHERE sb.se_ejecuto)               AS veces_trabajada,
    COUNT(*) FILTER (WHERE NOT sb.se_ejecuto)           AS veces_planificada_no_ejecutada
FROM fundacion.sesion_dia sd
JOIN fundacion.sedes s                          ON s.id = sd.sede_id
JOIN fundacion.sesion_bloque sb                 ON sb.sesion_dia_id = sd.id
JOIN fundacion.sesion_bloque_competencias sbc   ON sbc.sesion_bloque_id = sb.id
JOIN fundacion.competencias c                   ON c.id = sbc.competencia_id
JOIN fundacion.competencia_dominios d           ON d.id = c.dominio_id
JOIN fundacion.bloque_tipos bt                  ON bt.id = sb.bloque_tipo_id
GROUP BY sd.sede_id, s.code, s.nombre, sd.fecha, c.codigo, c.descripcion,
         d.codigo, d.nombre, bt.codigo, bt.nombre;


-- (c) Materiales solicitados vs usados — agregado por producto/nombre, sede.
CREATE OR REPLACE VIEW fundacion.v_materiales_uso AS
SELECT
    sd.sede_id,
    s.code                                              AS sede_code,
    s.nombre                                            AS sede_nombre,
    sd.fecha,
    sbm.product_id,
    COALESCE(p.name, sbm.nombre_libre)                  AS material,
    p.sku                                               AS sku,
    SUM(COALESCE(sbm.cantidad_solicitada, 0))           AS total_solicitada,
    SUM(COALESCE(sbm.cantidad_usada, 0))                AS total_usada,
    SUM(COALESCE(sbm.cantidad_solicitada, 0) - COALESCE(sbm.cantidad_usada, 0)) AS diferencia,
    COUNT(*)                                            AS apariciones
FROM fundacion.sesion_dia sd
JOIN fundacion.sedes s                          ON s.id = sd.sede_id
JOIN fundacion.sesion_bloque sb                 ON sb.sesion_dia_id = sd.id
JOIN fundacion.sesion_bloque_materiales sbm     ON sbm.sesion_bloque_id = sb.id
LEFT JOIN bodega.products p                     ON p.id = sbm.product_id
GROUP BY sd.sede_id, s.code, s.nombre, sd.fecha, sbm.product_id,
         COALESCE(p.name, sbm.nombre_libre), p.sku;


-- (d) Adaptaciones realizadas — listado de adaptaciones por bloque.
CREATE OR REPLACE VIEW fundacion.v_adaptaciones AS
SELECT
    sd.sede_id,
    s.code                                              AS sede_code,
    s.nombre                                            AS sede_nombre,
    sd.fecha,
    sb.id                                               AS sesion_bloque_id,
    bt.codigo                                           AS bloque_codigo,
    bt.nombre                                           AS bloque_nombre,
    sb.nombre_actividad,
    sb.se_ejecuto,
    sb.motivo_no_ejecucion,
    sb.adaptacion
FROM fundacion.sesion_dia sd
JOIN fundacion.sedes s                          ON s.id = sd.sede_id
JOIN fundacion.sesion_bloque sb                 ON sb.sesion_dia_id = sd.id
JOIN fundacion.bloque_tipos bt                  ON bt.id = sb.bloque_tipo_id
WHERE (sb.adaptacion IS NOT NULL AND length(trim(sb.adaptacion)) > 0)
   OR NOT sb.se_ejecuto;


-- (f) Clima y convivencia — clima por día, sede.
CREATE OR REPLACE VIEW fundacion.v_clima_dia AS
SELECT
    sd.sede_id,
    s.code                                              AS sede_code,
    s.nombre                                            AS sede_nombre,
    sd.fecha,
    co.codigo                                           AS clima_codigo,
    co.nombre                                           AS clima_nombre,
    co.color                                            AS clima_color,
    sd.situaciones_relevantes,
    sd.estrategias_aplicadas,
    sd.notas
FROM fundacion.sesion_dia sd
JOIN fundacion.sedes s                          ON s.id = sd.sede_id
LEFT JOIN fundacion.clima_opciones co           ON co.id = sd.clima_opcion_id;


-- Dashboard pedagógico semanal/mensual — combina actividades ejecutadas vs
-- planificadas. Sirve para el reporte (e) del correo.
CREATE OR REPLACE VIEW fundacion.v_actividad_periodo AS
SELECT
    sd.sede_id,
    s.code                                              AS sede_code,
    s.nombre                                            AS sede_nombre,
    sd.fecha,
    EXTRACT(YEAR FROM sd.fecha)::int                    AS anio,
    EXTRACT(MONTH FROM sd.fecha)::int                   AS mes_num,
    EXTRACT(WEEK FROM sd.fecha)::int                    AS semana_num,
    COUNT(sb.id)                                        AS bloques_planificados,
    COUNT(sb.id) FILTER (WHERE sb.se_ejecuto)           AS bloques_ejecutados,
    COUNT(DISTINCT sb.bloque_tipo_id)                   AS tipos_bloque_distintos
FROM fundacion.sesion_dia sd
JOIN fundacion.sedes s                          ON s.id = sd.sede_id
LEFT JOIN fundacion.sesion_bloque sb            ON sb.sesion_dia_id = sd.id
GROUP BY sd.sede_id, s.code, s.nombre, sd.fecha;
